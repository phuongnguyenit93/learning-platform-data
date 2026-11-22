# Software Design — Structural Proxy Pattern

Proxy là một design pattern thuộc nhóm *Structural*, cho phép đặt một đối tượng đại diện trước đối tượng thật để kiểm soát cách Client truy cập dịch vụ. Proxy thường cung cấp cùng giao diện với đối tượng gốc và chuyển tiếp lời gọi sau khi thực hiện xử lý cần thiết như trì hoãn khởi tạo, kiểm tra quyền hoặc ghi nhận truy cập. Cách này giúp Client ít phụ thuộc hơn vào chi tiết quản lý đối tượng thật.

Module phù hợp với người học đã nắm lập trình hướng đối tượng Java, interface và nguyên tắc ủy quyền (*delegation*). Lộ trình đi từ ý định và cấu trúc Subject–RealSubject–Proxy–Client đến luồng gọi và vòng đời đối tượng. Tiếp theo, bạn thực hành các biến thể Virtual Proxy, Protection Proxy, tìm hiểu Remote/Smart Proxy và cách hiện thực Proxy tĩnh hoặc JDK Dynamic Proxy với `InvocationHandler`.

Ở phần cuối, người học sẽ kiểm tra khả năng thay thế đối tượng thật bằng Proxy, xử lý các trường hợp lỗi hoặc bị từ chối truy cập và so sánh Proxy với Decorator, Adapter. Hoàn thành module, bạn có thể xác định lúc nào Proxy đem lại lợi ích, triển khai ví dụ Proxy trong Java và nhận biết chi phí bổ sung về độ phức tạp hoặc hiệu năng.