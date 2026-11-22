# Software Design Design Pattern Structural Facade

Facade là mẫu thiết kế cấu trúc (Structural Design Pattern) cung cấp một giao diện đơn giản để client làm việc với hệ thống con gồm nhiều lớp hoặc API phức tạp. Thay vì tự khởi tạo nhiều đối tượng và gọi các bước theo đúng thứ tự, client có thể dùng một điểm vào mức cao để thực hiện tác vụ quen thuộc. Mục tiêu của Facade là giảm phụ thuộc vào chi tiết subsystem, không phải thay thế toàn bộ chức năng hay cấm truy cập trực tiếp khi thật sự cần.

Module dành cho người đã biết Java hướng đối tượng, interface, composition và cách phân chia trách nhiệm giữa các lớp. Lộ trình bắt đầu từ bài toán và cấu trúc Facade, sau đó thiết kế API rõ ý nghĩa, triển khai delegation trong Java và quản lý vòng đời dependency. Người học tiếp tục thực hành gọi Facade từ client, viết kiểm thử, phân biệt Facade với Adapter, Decorator, Mediator và nhận diện các đánh đổi thiết kế.

Sau khi hoàn thành, bạn có thể xác định đúng tình huống cần Facade, thiết kế và triển khai một lớp bao đơn giản cho nhiều thành phần, kiểm chứng hành vi bằng test và refactor hệ thống hiện có mà không tạo thêm một “god object”.