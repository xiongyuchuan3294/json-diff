# !coding:utf-8
# !@Time         :2023/2/20 11:00
# !@Author       :v_xjxu
# !@Email        :v_xjxu@webank.com
# !@File         :config.py
import configparser
import os


def load_config(cfg):
    config = configparser.ConfigParser()
    config.read(cfg, encoding='utf-8')
    return config


def get_config(conf_name, conf_header='mysql', conf_file='aml_conf.conf'):
    current_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), conf_file)
    return load_config(current_path).get(conf_header, conf_name)


if __name__ == '__main__':
    print(get_config("aml_new3"))
