import sys
import os
from Tkinter import *
import tkMessageBox
import datetime
import time
import subprocess
import shutil
import threading


def rf_process_control(mode):
    global config_file_variables

    # Get serial number for device under test.
    # Currently this is manually entered or scanned in by operator
    # Will update function to get information directly from JabilTest in future
    serial_number = get_serial_number()
    print 'serial number for device under test is', serial_number
    # Validation takes place now consisting of:
        # F1C xml file generation
        # Watch for response from F1C service
        # Interpret the F1C response
    next_instruction = rf_validate(mode, serial_number)
    #print next_instruction
    while next_instruction in ['LaunchRF', 'LaunchDSN', 'TIMEOUT']:
        # Launching RF will:
            # Run test software
            # Wait for log file to be generated
            # Interpret test result
            # Update config file for next stage status
            # Update config file with notes for detailed failures
        if next_instruction == 'LaunchRF':
            next_instruction = rf_test_software(mode, serial_number)
        elif next_instruction == 'LaunchDSN':
            next_instruction = dsn_test_software(mode, serial_number)
        # Timeout takes place now consisting of:
            # F1C xml file generation
            # Watch for response from F1C service
            # Interpret the F1C response
        elif next_instruction == 'TIMEOUT':
            next_instruction = rf_timeout(mode, serial_number)
        print 'Next instruction is to %s' % next_instruction
    if next_instruction == 'ERROR':
        message = 'DUT is not validated as being in the correct work center'
        print message
        tkMessageBox.showerror('Error', message)
    if next_instruction == 'TO_ERROR':
        message = 'DUT did not complete process correctly; '
        message += 'please notify engineering for review'
        print message
        tkMessageBox.showerror('Error', message)
    elif next_instruction == 'MANUAL':
        message = 'DUT has completed test process '
        message += 'but has not been auto-timed out'
        message += '\nManual timeout required'
        print message
        tkMessageBox.showwarning('Information', message)
    elif next_instruction == 'DONE':
        message = 'DUT has completed test process '
        message += 'and has been auto-timed out to next stage'
        print message
        tkMessageBox.showinfo('Complete', message)


def rf_validate(mode, serial_number):
    print 'validating...'
    #print 'Current mode is', mode
    # Create XML file to be passed to F1C service
    name_of_file_generated, f1c_type = rf_generate_xml(serial_number)
    print '%s has been written to %s' % (
        name_of_file_generated, submitted_path_name)
    #print f1c_type, 'is the current Field1Click type'
    # Get the response from the IT service for the xml file created
    # 0 = Missing | 1 = Success | 2 = Failed | 3 = DSN
    response = watch_for_response(name_of_file_generated)
    # Based on the response, figure out how to proceed
    #'LaunchDSN' | 'ERROR' | 'TIMEOUT' | 'DONE'
    next_step = interpret_response(name_of_file_generated, response, f1c_type)
    return next_step


def rf_test_software(mode, serial_number):
    print 'launching rf test software...'
    launch_rf()
    test_log_name = wait_for_rf(serial_number)
    print 'RF testing has completed'
    print '%s has been written to %s' % (
        test_log_name, local_dsn_xml_path_name)
    next_step = interpret_response(test_log_name, 3, 'RF')
    print 'Proceeding to', next_step
    time.sleep(5)
    return next_step


def dsn_test_software(mode, serial_number):
    print 'This function has been removed'
    return 'FINAL'


def rf_timeout(mode, serial_number):
    print 'timing out...'
    name_of_file_generated, f1c_type = rf_generate_xml(serial_number)
    print '%s has been written to %s' % (
        name_of_file_generated, submitted_path_name)
    #print f1c_type, 'is the current Field1Click type'
    # Get the response from the IT service for the xml file created
    # 0 = Missing | 1 = Success | 2 = Failed | 3 = DSN
    response = watch_for_response(name_of_file_generated)
    # Based on the response, figure out how to proceed
    #'LaunchDSN' | 'ERROR' | 'TIMEOUT' | 'DONE'
    next_step = interpret_response(name_of_file_generated, response, f1c_type)
    return next_step


def rf_generate_xml(sn):
    global submitted_path_name
    config_file_variables = config_file_parsing()
    xml_data = open_file_return_contents(path_name, 'F1Click_template.xml')
    if mode in ['test', 'devtest']:
        timestamp = '1900-01-01 12-00'
    else:
        now = datetime.datetime.now()
        timestamp = '%s-%s-%s %s-%s' % (
            now.year, now.month, now.day, now.hour, now.minute)
    config_file_variables['<SerialNumber>'] = sn
    site = config_file_variables['<Location>']
    stage_names = find_stage_names(site)
    tags_to_write = [
        '<Location>', '<Client>', '<Contract>', '<ProcessType>',
        '<WorkCenter>', '<UserName>', '<UserPassword>', '<OrderProcessType>',
        '<HostName>', '<SerialNumber>']
    for each in tags_to_write:
        position = xml_data.find(each) + len(each)
        # Making everything upper case except for:
        # user name, user password, and host name
        # Not really sure if those are appropriate to remain as is?
        if each in ['<UserPassword>', '<UserName>', '<HostName>']:
            xml_data = data_insert(
                xml_data, str(config_file_variables[each]), position)
        else:
            xml_data = data_insert(
                xml_data, str.upper(config_file_variables[each]), position)
    #print config_file_variables['<ProcessType>']
    if config_file_variables['<ProcessType>'] == 'F1C_VALIDATION':
        f1c_type = 'VALIDATE'
    elif config_file_variables['<ProcessType>'] == 'F1C_TIMEOUT':
        f1c_type = 'TIMEOUT'
        for stage in stage_names:
            if stage == config_file_variables['<WorkCenter>']:
                position = xml_data.find('<ResultCode>') + len('<ResultCode>')
                xml_data = data_insert(xml_data, stage_names[stage], position)
                position = xml_data.find('<Notes>', position) + len('<Notes>')
            #    print 'writing', config_file_variables['<Notes>'], 'to xml'
                xml_data = data_insert(
                    xml_data, 'notes from JPC for %s success\n%s', position
                ) % (stage, config_file_variables['<Notes>'])
    else:
        f1c_type = 'UNKNOWN'
        print 'Unknown type of <ProcessType> in REY.config file'
    with open(
        os.path.join(submitted_path_name, '%s-%s %s.xml') %
        (sn, f1c_type, timestamp), 'wb'
    ) as xml_file:
        xml_file.write(xml_data)
    return ['%s-%s %s.xml' % (
        sn, f1c_type, timestamp), f1c_type]


def get_serial_number():
    popup = GetSerialNumber()
    if popup.command():
        return popup.command()
    else:
        message = 'Serial number window was closed without entry.'
        message += '\nNow exiting...'
        tkMessageBox.showerror('Error', message)
        sys.exit(1)


class GetSerialNumber:
    def __init__(self, default_sn=''):
        self.master = Tk()
        self.master.wm_title('DUT serial number')
        self.master.iconbitmap(default='favicon.ico')
        l_text = 'Please scan or enter serial number for device under test'
        self.label = Label(self.master, text=l_text)
        self.label.pack()
        self.entry = Entry(self.master, width=50)
        self.entry.focus_set()
        self.entry.pack()
        self.button = Button(
            self.master, text="OK", command=self.command, default=ACTIVE)
        self.button.pack()
        self.master.bind('<Return>', self.command)
        self.master.mainloop()

    def command(self, event=None):
        y = self.entry.get()
        if y == '':
            title = 'Invalid SN'
            message = 'No serial number entered'
            tkMessageBox.showerror(title, message)
        else:
            self.master.withdraw()
            self.master.quit()
            return y


class CancelButton(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.window = Tk()
        self.window.geometry('+0+0')
        self.window.wm_attributes('-topmost', 1)
        self.window.overrideredirect(1)
        self.button2 = Button(
            self.window, text='Cancel Auto-timeout Process', command=self.cancel)
        self.button2.configure(background='red')
        self.button2.pack()

    def cancel(self):
        sys.exit()


def config_file_parsing():
    global path_name
    config_filename = 'REY.config'
    interesting_tags = [
        '<Location>', '<Client>', '<Contract>', '<ProcessType>', '<Notes>',
        '<WorkCenter>', '<UserName>', '<UserPassword>', '<OrderProcessType>',
        '<HostName>', '<LogPath>', '<DSNLocalLogPath>', '<DSNRemoteLogPath>',
        '<TestProgram>', '<TestCommand>']
    config_information = {}
    config_file_data = open_file_return_contents(path_name, config_filename)
    if config_file_data:
        for each in interesting_tags:
            config_information[each] = parse(config_file_data, each)
        #    print config_information[each], each
        #find all scripts that included between the <TimeoutScriptsAllowed> tag
        timeout_data = between_the_tags(
            config_file_data, 'TimeoutScriptsAllowed', 0)
        config_information['<TimeoutScriptsAllowed>'] = multi_parse(
            timeout_data, '<Script>')
    return config_information


def open_file_return_contents(pathname, filename):
    try:
        with open(os.path.join(pathname, filename)) as f:
            return f.read()
    except IOError:
        print filename, 'is not present in directory:\n    ', pathname


def parse(data, tag, initial_pos=0):
    tag_information_start = data.find(tag, initial_pos) + len(tag)
    tag_information_end = data.find('<', tag_information_start)
    tag_information = data[tag_information_start:tag_information_end]
    return tag_information


def multi_parse(data, tag, initial_pos=0):
    list_of_found_items = []
    for each in range(data.count(tag)):
        list_of_found_items.append(parse(data, tag))
        data = data[data.find(tag) + len(tag):]
    return list_of_found_items


def between_the_tags(data, tag, start_pos=0):
    tag_start = data.find('<' + tag + '>', start_pos) + len(tag + '<>')
    tag_end = data.find('</' + tag + '>', tag_start+1)
    return data[tag_start:tag_end]


def beginning_and_end_tags(data, tag, start_pos):
    start = data.find('<'+tag, start_pos) + len('<'+tag)
    end = data.find('</'+tag, start)
    return start, end


def data_insert(original, new, pos):
    return original[:pos] + new + original[pos:]


def data_remove(original, pos1, pos2):
    return original[:pos1] + original[pos2:]


def find_stage_names(site):
    # Check to see if status has been written to config file
    contents = open_file_return_contents(path_name, 'REY.config')
    if contents.count('<StageStatus'):
        return {config_file_variables['<WorkCenter>']: between_the_tags(contents, 'StageStatus')}
    if site == 'JGS MEMPHIS':
        return {
            'WUR_REPAIR': 'TO_FI',
            'WUR_FI': 'TO_QA',
            'WUR_QA': None, }
    elif site == 'BYDGOSZCZ':
        return {
            'REF_BURN_IN': 'PASS',
            'REF_DEBUG': None, }
    elif site == 'REYNOSA':
        return {
            'RF-TEST-BET': 'PASS',
            'FAKE_WORK_CENTER': 'TO_NEXT_FAKE',
            'FAKE_WORK_CENTER2': None, }
    else:
        print 'Process Control Engine has not been setup for this location yet'
        return {}


def watch_for_response(filename, timeout=60):
    global response_path_name, failed_path_name
    t0 = time.time()
    path = os.path.join(response_path_name, filename)
    print 'Waiting for', filename
    if os.path.exists(path):
        print 'Response file %s is already in %s' % (filename, path)
        return 1
    while time.time() - t0 < timeout:
        time.sleep(3)
        print '.',
        sys.stdout.flush()
        if os.path.exists(path):
            print '\nReceived response file %s' % filename
            return 1
    print '\nResponse file not received after 60 seconds'
    filename = filename.replace('.xml', '-ERROR.xml')
    err_path = os.path.join(failed_path_name, filename)
    if os.path.exists(err_path):
        print 'Found response file in %s' % err_path
        return 2
    else:
        print 'Nothing found'
        return 0


def interpret_response(file_name, response_type, type):
    global config_file_variables
    site = config_file_variables['<Location>']
    if type == 'VALIDATE':
        if response_type == 2:
            file_name = file_name.replace('.xml', '-ERROR.xml')
        if response_type == 1 or response_type == 2:
            IT_result = parse_response_file(
                file_name, response_type, '<ResultMessage>')
            if IT_result == 'SUCCESS':
                print 'F1C has validated that unit is in correct work center.'
                if site == 'REYNOSA':
                    return 'LaunchRF'
                else:
                    return 'LaunchDSN'
            elif 'Invalid Workcenter.' in IT_result:
                print 'SYSTEM IS IN THE WRONG WORK CENTER.'
                print IT_result
                return 'ERROR'
            elif IT_result == 'ITEM NOT FOUND.':
                print 'SYSTEM SERIAL NUMBER DOES NOT EXIST IN SL.'
                return 'ERROR'
            elif IT_result == '':
                print 'IT SERVICE RETURNED AN EMPTY RESPONSE'
                return 'ERROR'
            else:
                print 'UNKNOWN STATUS FOR THIS UNIT.',
                print ' PLEASE REPORT FOR INVESTIGATION.'
                return 'ERROR'
        else:
            print 'No response file in /FROM or /FAILED folder after 60 secs'
            print 'IT IS POSSIBLE THAT NETWORK CONNECTION HAS DROPPED'
            return 'ERROR'
    elif type == 'TIMEOUT':
        if response_type == 2:
            file_name = file_name.replace('.xml', '-ERROR.xml')
        if response_type == 1 or response_type == 2:
            IT_result = parse_response_file(
                file_name, response_type, '<Result>')
            if IT_result == 'SUCCESS':
                print 'UNIT HAS SUCCESSFULLY TIMED OUT',
                print 'AND IS READY TO MOVE TO NEXT STAGE'
                return 'DONE'
            elif IT_result == 'ERROR':
                error_reported = parse_response_file(
                    file_name, response_type, '<ResultMessage>')
                if 'is at work center' in error_reported:
                    print 'SYSTEM IN WRONG WORK CENTER'
                    print error_reported
                    return 'TO_ERROR'
                elif 'Content is not allowed' in error_reported:
                    print 'SYSTEM MISSING RESULTS INFORMATION'
                    print error_reported
                    return 'TO_ERROR'
                elif 'Serial Number does not exist' in error_reported:
                    print 'SYSTEM SERIAL NUMBER DOES NOT EXIST IN SL'
                    return 'TO_ERROR'
                else:
                    print 'UNKNOWN ERROR FOR THIS UNIT.',
                    print ' PLEASE REPORT FOR INVESTIGATION'
                    return 'TO_ERROR'
            else:
                print 'UNKNOWN STATUS RETURNED FOR THIS UNIT.',
                print ' PLEASE REPORT FOR INVESTIGATION'
                return 'TO_ERROR'
        else:
            print 'No response file received in /FROM or /FAILED folders'
            return 'TO_ERROR'
    elif type == 'DSN':
        DSN_result = parse_response_file(
            file_name, response_type, '<ScriptStatus>')
        DSN_script_name = parse_response_file(
            file_name, response_type, '<ScriptName>')
        print 'DSN has', DSN_result, 'the script named', DSN_script_name
        if site == 'JGS MEMPHIS':
            timeout_candidate = False
            timeout_scripts = config_file_variables['<TimeoutScriptsAllowed>']
            for each in timeout_scripts:
                if each in DSN_script_name:
                    timeout_candidate = True
            #copy from local dsn location to remote dsn location
            shutil.copy(
                os.path.join(local_dsn_xml_path_name, file_name),
                os.path.join(remote_dsn_xml_path_name, file_name))
            if DSN_result == 'PASSED' and timeout_candidate is True:
                update_configuration_file()
                return 'TIMEOUT'
            elif DSN_result == 'PASSED' and timeout_candidate is False:
                return 'MANUAL'
            elif DSN_result == 'FAILED':
                return 'ERROR'
            else:
                print 'Unknown Process Type'
                return 'ERROR'
        elif site == 'BYDGOSZCZ':
            timeout_candidate = False
            #copy from local dsn location to remote dsn location
            shutil.copy(
                os.path.join(local_dsn_xml_path_name, file_name),
                os.path.join(remote_dsn_xml_path_name, file_name))
            #LOGIC FOR BYDGOSCZC AUTO-TIMEOUT IS HERE
            if DSN_result == 'PASSED':
                update_configuration_file()
                return 'TIMEOUT'
            elif DSN_result == 'FAILED':
                dsn_log_contents = open_file_return_contents(
                    local_dsn_xml_path_name, file_name)
                notes_to_save = find_dsn_fails(dsn_log_contents)
                failed_sl_codes = lookup_sl_fail_codes(notes_to_save)
                print failed_sl_codes
                update_configuration_file(notes=notes_to_save)
                return 'TIMEOUT'
            shutil.copy(
                os.path.join(local_dsn_xml_path_name, file_name),
                os.path.join(remote_dsn_xml_path_name, file_name))
        else:
            print 'Unknown dsn result routing rules for this location'
    elif type == 'RF':
        site = config_file_variables['<Location>']
        total_failures, full_log = parse_rf_results(
            local_dsn_xml_path_name, file_name)
        if total_failures == '0':
            test_status = 'PASSED'
        else:
            test_status = 'FAILED'
        print 'RF test has %s testing' % test_status
        if site == 'REYNOSA':
            timeout_candidate = False
            # copy from local log location to remote log location
            shutil.copy(
                os.path.join(local_dsn_xml_path_name, file_name),
                os.path.join(remote_dsn_xml_path_name, file_name))
            # LOGIC FOR REYNOSA RF TEST AUTO-TIMEOUT
            if test_status == 'PASSED':
                update_configuration_file()
                lazy_update(test_status)
                return 'TIMEOUT'
            elif test_status == 'FAILED':
                notes_to_save = find_rf_failures(full_log)
                update_configuration_file(notes=notes_to_save)
                lazy_update(test_status)
                return 'TIMEOUT'


def parse_rf_results(log_path, filename):
    entire_contents = open_file_return_contents(log_path, filename)
    total_failures = between_the_tags(entire_contents, 'total_failed', 0)
    return total_failures, entire_contents


def parse_response_file(file_name, location, tag):
    # start from beginning of file unless overwritten later
    start_searching_from = 0
    if location == 1:
        file_location = response_path_name
    if location == 2:
        file_location = failed_path_name
    if location == 3:
        file_location = local_dsn_xml_path_name
    response_file_data = open_file_return_contents(file_location, file_name)
    if location == 1 or location == 2:
        x = '<ProcessResult>'
        start_searching_from = response_file_data.find(x) + len(x)
    results = parse(response_file_data, tag, start_searching_from)
    return results


def wait_for_rf(serial_number):
    before = [f for f in os.listdir(local_dsn_xml_path_name)]
    print '...waiting for new_file log file for dut %s in %s' % (
        serial_number, local_dsn_xml_path_name)
    while True:
        time.sleep(15)
        after = [f for f in os.listdir(local_dsn_xml_path_name)]
        added = [f for f in after if not f in before]
        if added:
            for new_file in added:
                if sn_look_up_and_match(local_dsn_xml_path_name, new_file, serial_number):
                    print 'found file %s with serial number %s' % (new_file, serial_number)
                    return new_file
        before = after


def sn_look_up_and_match(logpath, filename, serialnumber):
    if '.xml' in filename:
        data = open_file_return_contents(logpath, filename)
        sn_from_log = between_the_tags(data, 'dut_serial_number', 0)
        print 'detected serial number %s from new log file' % (sn_from_log)
        if sn_from_log == serialnumber:
            return True
    return False


def launch_rf():
    try:
        os.startfile(rf_test_program, rf_test_command)
    except WindowsError:
        subprocess.call([rf_test_program, rf_test_command])


def find_rf_failures(entire_contents):
    result = ''
    failed_tests = []
    results_start, results_end = beginning_and_end_tags(
        entire_contents, 'test_results>', 0)
    count = entire_contents.count('<test>', results_start, results_end)
    result += 'Detected Failure'
    result += '\nTests run: '+str(count-2)
    result += '\nFailures include:'
    start = results_start
    for i in range(count-2):
        test_start, test_end = beginning_and_end_tags(
            entire_contents, 'test>', start)
        test_step_start, test_step_end = beginning_and_end_tags(
            entire_contents, 'test_step>', start)
        test_step = entire_contents[test_step_start:test_step_end]
        title_start, title_end = beginning_and_end_tags(
            entire_contents, 'title>', start)
        title = entire_contents[title_start:title_end]
        pass_fail_start, pass_fail_end = beginning_and_end_tags(
            entire_contents, 'pass_fail>', start)
        pass_fail_status = entire_contents[pass_fail_start:pass_fail_end]
        if pass_fail_status != 'Pass':
           # result += '\n'+'-'*80
            result += '\n%s: %s: %s' % (test_step, title, pass_fail_status)
            failed_tests.append(title)
        start = test_end
    result += '\n'+'-'*80
    result += '\nFail Code(s): '+str(failcode_lookup(failed_tests))
    return result


def failcode_lookup(list_of_tests):
    unit_fc = []
    failcodes = {'Phase Error': 33.2,
                 'Frequency Error': 33.2,
                 'EVM': 33.2,
                 'Magnitude Error': 33.2,
                 'Peak Code Domain Error': 33.2,
                 'Sensitivity FER @-104dBm': 33.2,
                 'Rho': 33.2,
                 'CDMA Voice Quality': 37.2,
                 'WCDMA Change Channel': 33.2,
                 'BER Ratio': 33.2,
                 'CDMA Origination': 33.2,
                 'Carrier Feedthrough': 33.2,
                 'RX Level': 33.2,
                 'Frequency Error in Hz': 33.2,
                 'Time Error': 33.2,
                 'Frequency Error in ppm': 33.2,
                 'Origin Offset': 33.2,
                 'GSM Base Station Initiated Call Successful': 33.2,
                 'Peak Phase Error': 33.2,
                 'GSM Handover Successful': 33.2,
                 'Ref Sensitivity BER @-104 dBm': 33.2,
                 'GSM Voice Quality': 37.2,
                 'RMS Phase Error': 33.2,
                 'Handoff': 33.2,
                 'RX Quality': 33.2,
                 'Instrument IDN': 33.2,
                 'Static Timing Offset': 33.2,
                 'WCDMA Page': 33.2,
                 'TX Power': 33.2,
                 'BER': 33.2,
                 'CDMA Registration': 33.2,
                 'Maximum RF Output Power': 33.2,
                 'Maximum Output Power': 33.2,
                 'No Log Created': 32.2, }
    for failure in list_of_tests:
        if failure in failcodes:
            if failcodes[failure] not in unit_fc:
                unit_fc.append(failcodes[failure])
        else:
            unit_fc.append('Invalid')
    return str(unit_fc)


def update_configuration_file(notes=None):
    #This function modifies the configuration file stored on the local machine
    #This leaves the file on the server alone
    config_filename = 'REY.config'
    config_file_data = open_file_return_contents(path_name, config_filename)
    pos_a1 = config_file_data.find('<ProcessType>') + len('<ProcessType>')
    pos_a2 = config_file_data.find('</ProcessType>')
    config_file_data = data_remove(config_file_data, pos_a1, pos_a2)
    pos_a = config_file_data.find('<ProcessType>') + len('<ProcessType>')
    config_file_data = data_insert(config_file_data, 'F1C_TIMEOUT', pos_a)
    if notes:
        pos_b1 = config_file_data.find('<Notes>') + len('<Notes>')
        pos_b2 = config_file_data.find('</Notes>')
        config_file_data = data_remove(config_file_data, pos_b1, pos_b2)
        pos_b = config_file_data.find('<Notes>') + len('<Notes>')
        config_file_data = data_insert(config_file_data, notes, pos_b)
    with open(os.path.join(path_name, config_filename), 'wb') as f:
        f.write(config_file_data)
    #    print 'updated config file JPC.config to be', config_file_data


def lazy_update(status):
    config_filename = 'REY.config'
    with open(os.path.join(path_name, config_filename), 'ab') as f:
        f.write('<StageStatus>%s</StageStatus>' % (status))


def usage():
    print '''
        Accepted arguments include:
        'test' (without quotes) = test mode

        Configuaration file variables (REY.config)
        must reside in same directory as script

        XML template (F1Click_template.xml)
        must reside in same directory as script
        '''

if __name__ == "__main__":
    arguments = []
    dut_serial_number = ''
    mode = 'NOT test'
    for arg in sys.argv[1:]:
        x = ['help', '-help', '--help', 'h', '-h', '--h', '?', '-?', '--?']
        if arg in x:
            usage()
            sys.exit()
        elif arg in ['test', '-test']:
            print 'mode set to test'
            mode = 'test'
        else:
            arguments.append(arg)
            usage()
            sys.exit()
    try:
        if os.environ['COMPUTERNAME'] == 'JGLOF061':
            mode = 'devtest'
    except KeyError:
        pass
    path_name = os.getcwd()
    # Always start process with a fresh copy of the config file
    shutil.copy(
        os.path.join(path_name, 'REY - Master.config'),
        os.path.join(path_name, 'REY.config'))
    #Variables pulled from REY.config file
    config_file_variables = config_file_parsing()
    if config_file_variables:
        path_name = os.getcwd()
        log_path_name = config_file_variables['<LogPath>']
        submitted_path_name = os.path.join(log_path_name, 'To')
        response_path_name = os.path.join(log_path_name, 'From')
        failed_path_name = os.path.join(log_path_name, 'Failed')
#        command = '"sudo /usr/local/bin/dcp/startdsn ; bash"'
#        dsn_launcher = 'gnome-terminal -x bash -c %s' % (command)
#        oct_path = 'C:\Users\schroedb\Documents\Process Control Engine\Octopus\sd\sd\\'
#        octopus_command = 'Octopus_COMM_start.CMD'
#        rf_test_program = 'C:\\Program Files (x86)\\Notepad++\\notepad++.exe'
#        rf_test_command = os.path.join(path_name, 'test_software.txt')
        rf_test_program = config_file_variables['<TestProgram>']
        rf_test_command = config_file_variables['<TestCommand>']

        local_dsn_xml_path_name = config_file_variables['<DSNLocalLogPath>']
        remote_dsn_xml_path_name = config_file_variables['<DSNRemoteLogPath>']
        if mode == 'devtest':
            submitted_path_name = 'P:\logs\Client\To'
            response_path_name = 'P:\logs\Client\From'
            failed_path_name = 'P:\logs\Client\Failed'
        pass
    else:
        print 'REY.config appears to be empty'
        sys.exit()

    cancelbutton = CancelButton()
    cancelbutton.start()
    #t2 = threading.Thread(target=rf_process_control, args=(mode, ))
    t2 = threading.Thread(target=rf_process_control(mode))
    t2.start()
    #t2.join()
    #rf_process_control(mode)
