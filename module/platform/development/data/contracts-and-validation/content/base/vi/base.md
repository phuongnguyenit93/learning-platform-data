# Data Contracts And Validation

Data contract là thỏa thuận rõ ràng giữa bên cung cấp và bên sử dụng dữ liệu về cấu trúc, ý nghĩa, chất lượng và điều kiện sử dụng. Validation là bước kiểm tra dữ liệu có tuân thủ thỏa thuận đó hay không, giúp phát hiện sai lệch từ sớm và giảm lỗi lan truyền qua API, luồng sự kiện hoặc pipeline dữ liệu.

Module này dành cho người học Data Engineering và lập trình viên cần thiết kế giao diện dữ liệu ổn định. Bạn sẽ xác định phạm vi và trách nhiệm, mô tả schema bằng YAML/JSON, đặt quy tắc kiểm tra cấu trúc và nghiệp vụ, thực thi validation, quản lý phiên bản và tương thích, rồi triển khai contract testing và kiểm soát trong CI/CD.

Hãy thực hành với một bộ dữ liệu đơn hàng nhỏ: định nghĩa các trường bắt buộc, giới hạn giá trị, tạo ví dụ dữ liệu đúng/sai và kiểm tra phản ứng của hệ thống. Kết thúc lộ trình, bạn có thể xây dựng hợp đồng dữ liệu đơn giản, nhận biết breaking changes và giám sát vi phạm hợp đồng khi vận hành.