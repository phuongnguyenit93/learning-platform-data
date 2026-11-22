# Spring Vault

Spring Vault là thư viện của Spring giúp ứng dụng Java kết nối với HashiCorp Vault để truy cập, lưu trữ và quản lý bí mật như API key, mật khẩu và thông tin đăng nhập dịch vụ. Thay vì đặt secret trực tiếp trong mã nguồn hoặc file cấu hình được commit, ứng dụng sử dụng các abstraction như `VaultTemplate` và các cơ chế xác thực của Vault để truy cập dữ liệu được cấp quyền.

Lộ trình giới thiệu mô hình Vault, cấu hình kết nối an toàn, xác thực bằng token hoặc các phương thức dành cho workload, sau đó thực hành với KV secret engine và `@VaultPropertySource`. Người học tiếp tục tìm hiểu secret động và lease, cách sử dụng Transit để mã hóa dữ liệu, cùng ACL policy, xử lý lỗi và kiểm thử. Spring Vault tập trung vào API client; việc tự động nhập cấu hình ứng dụng từ Vault qua Spring Cloud Vault là chủ đề liên quan nhưng có phạm vi riêng.

Module dành cho developer Java/Spring đã biết dependency injection, cấu hình Spring và HTTP cơ bản. Sau khi hoàn thành, bạn có thể đọc và ghi bí mật qua Spring Vault, chọn cơ chế xác thực, kiểm soát quyền theo nguyên tắc tối thiểu và xử lý vòng đời secret khi ứng dụng vận hành.