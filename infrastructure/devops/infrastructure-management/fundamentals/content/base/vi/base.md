# DevOps Infrastructure Management Fundamentals

Infrastructure Management trong DevOps là việc quản lý máy chủ, mạng, lưu trữ, quyền truy cập và cấu hình vận hành theo cách nhất quán, có thể kiểm tra và tái lập. Thay vì dựa vào thao tác thủ công khó truy vết, nhóm sử dụng quy ước môi trường, hạ tầng dưới dạng mã (Infrastructure as Code), quản lý cấu hình và lịch sử thay đổi để giảm sai lệch giữa các hệ thống.

Module dành cho người đã nắm kiến thức cơ bản về Linux, mạng, Git và quy trình triển khai ứng dụng. Lộ trình bắt đầu từ kiểm kê tài nguyên, phân tách môi trường, xác định trạng thái mong muốn và làm quen quy trình IaC. Tiếp đó là cấu hình có tính idempotent, quản lý mạng/IAM/secrets, kiểm soát thay đổi qua Git và nhận diện configuration drift bằng giám sát.

Sau khi hoàn thành, bạn có thể mô tả và quản lý một môi trường hạ tầng thử nghiệm, áp dụng quy trình review trước khi thay đổi, kiểm tra cảnh báo và chuẩn bị runbook, backup/restore cùng theo dõi chi phí. Trọng tâm là an toàn, khả năng tái lập và vận hành ổn định; các công cụ như Terraform và Ansible được dùng để minh họa nguyên tắc chung.