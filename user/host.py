# -*- coding:utf-8 -*-
from flask_restful import Resource, reqparse, request
from flask import g
from common.log import Logger
from common.audit_log import audit_log
from common.db import DB
from common.utility import uuid_prefix
from common.sso import access_required
from common.utility import salt_api_for_product
import json
from common.const import role_dict

logger = Logger()

parser = reqparse.RequestParser()
parser.add_argument("group_id", type=str, default=[], action="append")
parser.add_argument("product_id", type=str, required=True, trim=True)
parser.add_argument("minion_id", type=str, required=True, trim=True)
# 不必填写的字段一定要指定默认值为""，否则无法转换成字典
parser.add_argument("tag", type=str, default="", required=True)


class Host(Resource):
    @access_required(role_dict["common_user"])
    def get(self, host_id):
        db = DB()
        status, result = db.select_by_id("host", host_id)
        db.close_mysql()
        if status is True:
            if result:
                try:
                    host = eval(result[0][0])
                except Exception as e:
                    return {"status": False, "message": str(e)}, 500
            else:
                return {"status": False, "message": "%s does not exist" % host_id}, 404
        else:
            return {"status": False, "message": result}, 500
        return {"host": host, "status": True, "message": ""}, 200

    @access_required(role_dict["common_user"])
    def delete(self, host_id):
        user = g.user_info["username"]
        db = DB()
        status, result = db.delete_by_id("host", host_id)
        db.close_mysql()
        if status is not True:
            logger.error("Delete host error: %s" % result)
            return {"status": False, "message": result}, 500
        if result is 0:
            return {"status": False, "message": "%s does not exist" % host_id}, 404
        audit_log(user, host_id, "", "host", "delete")
        return {"status": True, "message": ""}, 200

    @access_required(role_dict["common_user"])
    def put(self, host_id):
        user = g.user_info["username"]
        args = parser.parse_args()
        args["id"] = host_id
        host = args
        db = DB()
        # 判断是否存在
        select_status, select_result = db.select_by_id("host", host_id)
        if select_status is False:
            db.close_mysql()
            logger.error("Modify host error: %s" % select_result)
            return {"status": False, "message": select_result}, 500
        if select_result:
            for i in select_result:
                try:
                    host = eval(i[0])
                    host["group_id"] = args["group_id"]
                    host["tag"] = args["tag"]
                except Exception as e:
                    db.close_mysql()
                    logger.error("Modify %s host error: %s" % (host_id, e))
                    return {"status": False, "message": str(e)}, 500
        status, result = db.update_by_id("host", json.dumps(host, ensure_ascii=False), host_id)
        db.close_mysql()
        if status is not True:
            logger.error("Modify host error: %s" % result)
            return {"status": False, "message": result}, 500
        audit_log(user, args["id"], args["product_id"], "host", "edit")
        return {"status": True, "message": ""}, 200


class HostList(Resource):
    @access_required(role_dict["common_user"])
    def get(self):
        product_id = request.args.get("product_id")
        db = DB()
        status, result = db.select("host", "where data -> '$.product_id'='%s'" % product_id)
        db.close_mysql()
        host_list = []
        if status is True:
            if result:
                for i in result:
                    try:
                        host_list.append(eval(i[0]))
                    except Exception as e:
                        return {"status": False, "message": str(e)}, 500
            else:
                return {"status": False, "message": "Host does not exist"}, 404
        else:
            return {"status": False, "message": result}, 500
        return {"hosts": {"host": host_list}, "status": True, "message": ""}, 200

    @access_required(role_dict["common_user"])
    def post(self):
        args = parser.parse_args()
        args["id"] = uuid_prefix("h")
        user = g.user_info["username"]
        host = args
        db = DB()
        print(args)
        status, result = db.select("host", "where data -> '$.minion_id'='%s'" % args["minion_id"])
        if status is True:
            if len(result) == 0:
                insert_status, insert_result = db.insert("host", json.dumps(host, ensure_ascii=False))
                db.close_mysql()
                if insert_status is not True:
                    logger.error("Add host error: %s" % insert_result)
                    return {"status": False, "message": insert_result}, 500
                audit_log(user, args["id"], args["product_id"], "host", "add")
                return {"status": True, "message": ""}, 201
            else:
                db.close_mysql()
                return {"status": False, "message": "The host name already exists"}, 200
        else:
            db.close_mysql()
            logger.error("Select host name error: %s" % result)
            return {"status": False, "message": result}, 500


class DifferenceHost(Resource):
    @access_required(role_dict["common_user"])
    def get(self):
        args = parser.parse_args()
        salt_api = salt_api_for_product(args["product_id"])
        if isinstance(salt_api, dict):
            return salt_api, 500
        else:
            result = salt_api.list_all_key()
            result_dict = eval(result)
            result_dict.get("minions").extend(result_dict.get("minions_rejected"))
            all_minion = result_dict.get("minions")


class Hosts(object):
    @staticmethod
    def add_host(minion_list, product_id, user):
        db = DB()
        for minion_id in minion_list:
            select_status, select_result = db.select("host", "where data -> '$.minion_id'='%s'" % minion_id)
            if select_status is False:
                logger.error("Add % host error: %s" % (minion_id, select_result))
                continue
            if not select_result:
                id = uuid_prefix("h")
                host = {
                    "id": id,
                    "minion_id": minion_id,
                    "product_id": product_id,
                    "group_id": [],
                    "tag": ""
                }
                insert_status, insert_result = db.insert("host", json.dumps(host, ensure_ascii=False))
                if insert_status is False:
                    logger.error("Add % host error: %s" % (minion_id, insert_result))
                else:
                    audit_log(user, id, product_id, "host", "add")
        db.close_mysql()

    @staticmethod
    def delete_host(minion_list, product_id, user):
        db = DB()
        for minion_id in minion_list:
            select_status, select_result = db.select("host", "where data -> '$.minion_id'='%s'" % minion_id)
            if select_status is False:
                logger.error("Delete % host error: %s" % (minion_id, select_result))
            if select_result:
                for i in select_result:
                    try:
                        host = eval(i[0])
                        status, result = db.delete_by_id("host", host["id"])
                        if status is False:
                            logger.error("Delete % host error: %s" % (minion_id, result))
                        else:
                            audit_log(user, host["id"], product_id, "host", "delete")
                    except Exception as e:
                        logger.error("Delete % host error: %s" % (minion_id, e))
            else:
                logger.error("Select %s host does not exist" % minion_id)
        db.close_mysql()

    @staticmethod
    def reject_host(minion_list, product_id, user):
        db = DB()
        for minion_id in minion_list:
            select_status, select_result = db.select("host", "where data -> '$.minion_id'='%s'" % minion_id)
            if select_status is False:
                logger.error("Reject % host error: %s" % (minion_id, select_result))
            if select_result:
                for i in select_result:
                    try:
                        host = eval(i[0])
                        host["tag"] = "reject"
                        status, result = db.update_by_id("host", json.dumps(host, ensure_ascii=False), host["id"])
                        if status is False:
                            logger.error("Reject % host error: %s" % (minion_id, result))
                        else:
                            audit_log(user, host["id"], product_id, "host", "reject")
                    except Exception as e:
                        logger.error("Reject % host error: %s" % (minion_id, e))
            else:
                logger.error("Select %s host does not exist" % minion_id)
        db.close_mysql()
