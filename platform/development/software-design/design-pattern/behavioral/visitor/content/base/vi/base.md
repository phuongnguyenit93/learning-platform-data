# Software Design Design Pattern Behavioral Visitor

Visitor là mẫu thiết kế hành vi giúp tách một nhóm thao tác khỏi các lớp phần tử mà chúng xử lý. Thay vì thêm chức năng như xuất dữ liệu, thống kê hoặc kiểm tra vào từng loại đối tượng, ứng dụng đặt chúng trong các `ConcreteVisitor` riêng. Mẫu này đặc biệt hữu ích khi có nhiều loại phần tử tương đối ổn định nhưng thường xuyên cần thêm thao tác mới. Module phù hợp với người học Java đã nắm interface, kế thừa, đa hình và method overloading.

Lộ trình bắt đầu từ bài toán và các vai trò `Element`, `Visitor`, `ConcreteElement`, `ConcreteVisitor`; sau đó giải thích cơ chế *double dispatch* qua lời gọi `element.accept(visitor)`. Người học sẽ tự cài đặt ví dụ Java, bổ sung nhiều visitor cho cùng hệ phần tử, áp dụng lên tập đối tượng hoặc cây Composite, rồi xử lý việc gom trạng thái và kết quả. Các phần thực hành ưu tiên quan sát đúng phương thức `visit` được gọi thay vì chỉ học thuộc sơ đồ lớp.

Kết thúc module, bạn có thể nhận diện tình huống nên dùng Visitor, triển khai và kiểm thử một visitor theo nhiều loại phần tử, đồng thời đánh giá đánh đổi cốt lõi: thêm thao tác thường dễ, nhưng thêm loại phần tử mới có thể buộc sửa mọi visitor.