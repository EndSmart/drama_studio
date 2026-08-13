"""
紧急重置管理员密码（无需登录）。

用法：
    python reset_admin.py                 # 将 admin 密码重置为 admin123
    python reset_admin.py 新密码          # 将 admin 密码重置为「新密码」

原理：直接改写 data/users.json 中 admin 的密码哈希，重启服务后即可用新密码登录。
"""
import sys

from backend import auth


def main():
    new_pw = sys.argv[1] if len(sys.argv) > 1 else "admin123"
    if not new_pw:
        print("密码不能为空")
        sys.exit(1)
    try:
        auth.set_password("admin", new_pw)
        print(f"✅ 已将 admin 密码重置为：{new_pw}")
        print("请重启服务后用新密码登录（前端无需改动）。")
    except ValueError:
        # admin 不存在时直接创建
        auth.create_user("admin", new_pw, "admin")
        print(f"✅ 已创建 admin 账户，密码：{new_pw}")


if __name__ == "__main__":
    main()
