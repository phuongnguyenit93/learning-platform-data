# DevOps Infrastructure Management Configuration Management Ansible

Ansible là công cụ tự động hóa hạ tầng và quản lý cấu hình theo hướng khai báo: thay vì thao tác thủ công trên từng máy, người vận hành mô tả trạng thái cần đạt trong playbook rồi thực thi từ một control node. Module **DevOps Infrastructure Management Configuration Management Ansible** giúp người học làm quen với inventory, module, tác vụ YAML và cách xây dựng quy trình cấu hình có thể chạy lại an toàn.

Lộ trình gồm tám mốc: nguyên lý Ansible và kết nối, quản lý inventory, viết playbook, sử dụng biến và Jinja2 templates, điều kiện và handlers, tái sử dụng roles/collections, bảo vệ bí mật với Vault, cuối cùng là kiểm chứng và vận hành. Trọng tâm là hiểu cách các thành phần kết hợp để cấu hình nhiều máy một cách nhất quán, có thể kiểm tra và đưa vào quản lý phiên bản.

Module phù hợp với người đã biết Linux, SSH, YAML và khái niệm dịch vụ hệ thống cơ bản. Sau khi hoàn thành, bạn có thể tạo inventory, viết playbook cấu hình đơn giản, tổ chức mã tự động hóa theo role, xử lý bí mật đúng cách và dùng check/diff mode để giảm rủi ro trước khi áp dụng thay đổi lên hệ thống thực.