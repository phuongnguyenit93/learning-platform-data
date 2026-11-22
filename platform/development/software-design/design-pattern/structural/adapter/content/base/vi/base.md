# Software Design Design Pattern Structural Adapter

**Adapter Pattern** là mẫu thiết kế cấu trúc giúp các đối tượng có interface không tương thích làm việc cùng nhau. Thay vì sửa một thư viện cũ, SDK bên ngoài hoặc mã nghiệp vụ đang ổn định, ta tạo một lớp chuyển đổi để client sử dụng hợp đồng mà nó đã biết. Mục tiêu chính của Adapter là giải quyết sự không khớp giữa các interface, không phải bổ sung hành vi mới cho đối tượng.

Lộ trình gồm tám mốc: xác định vấn đề interface, nhận diện các vai trò Client–Target–Adaptee–Adapter, triển khai Object Adapter bằng composition, tìm hiểu Class Adapter dựa trên kế thừa, ánh xạ dữ liệu và lỗi, tích hợp hệ thống legacy, phân biệt với Facade/Decorator/Proxy, rồi kiểm thử và bảo trì. Ví dụ Java giúp người học quan sát trực tiếp cách lời gọi được chuyển tiếp qua Adapter mà không làm client phụ thuộc vào triển khai cũ.

Module phù hợp với lập trình viên đã hiểu class, interface, kế thừa và composition trong Java. Sau khi hoàn thành, bạn có thể thiết kế một Adapter nhỏ, chọn cách triển khai phù hợp với giới hạn của Java, kiểm thử hợp đồng chuyển đổi và đánh giá khi nào việc thêm lớp trung gian thật sự mang lại lợi ích.