import configparser
import importlib


class ConfiguredConnector(object):

    def __init__(self, name, clazz, section):
        self.name = name
        self.clazz = clazz
        self.section = section

    def create(self):
        instance = self.clazz()
        instance.configure(self.name, self.section)
        return instance


class Workflow(object):

    def __init__(self, name, source, targets):
        self.name = name
        self.source = source
        self.targets = targets


class Config(object):

    def __init__(self, workflows):
        self.workflows = workflows


class ConfigurationError(RuntimeError):
    pass


def parse_connector(section, name):
    if 'class' not in section:
        raise ConfigurationError(
            'Section "{}" lacks a "class".'.format(section))
    clazz = section['class']
    try:
        parts = clazz.rsplit('.', 1)
        klass = getattr(importlib.import_module(parts[0]), parts[1])
    except KeyError:
        raise ConfigurationError(
            'There is no connector class "{}"'.format(clazz))

    return ConfiguredConnector(name, klass, section)


def parse_workflows(config):

    workflows = {}

    # first, find which workflows do exist
    workflow_names = list(set([w.split('.')[1]
                               for w in config.sections()
                               if len(w.split('.')) >= 2
                               and w.split('.')[0] == 'workflow']))

    # then, parse all workflows
    for workflow_name in workflow_names:

        # parse the source
        source_section = 'workflow.{}.source'.format(workflow_name)
        if source_section not in config.sections():
            raise ConfigurationError(
                'Workflow {} lacks source'.format(workflow_name))
        source = parse_connector(config[source_section], 'source')

        # parse targets
        target_sections = list(set([
            s for s in config.sections()
            if len(s.split('.')) == 4
            and s.startswith('workflow.{}.target.'.format(workflow_name))
            and s.split('.')[3]]))

        if not target_sections:
            raise ConfigurationError(
                'Workflow {} lacks targets'.format(workflow_name))

        targets = [parse_connector(config[section], section.split('.')[3])
                   for section in target_sections]

        workflows[workflow_name] = Workflow(workflow_name, source, targets)

    return workflows


def parse_config(config_file):
    config = configparser.ConfigParser()
    config.read_file(config_file)
    workflows = parse_workflows(config)
    return Config(workflows)
