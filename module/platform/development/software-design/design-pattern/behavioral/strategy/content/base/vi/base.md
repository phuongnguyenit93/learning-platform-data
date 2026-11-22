# Software Design Design Pattern Behavioral Strategy

**Strategy** là một design pattern thuộc nhóm hành vi (behavioral), cho phép định nghĩa nhiều cách thực hiện cùng một công việc, đóng gói từng thuật toán sau một giao diện chung và thay thế chúng mà không phải sửa logic sử dụng. Pattern này hữu ích khi hệ thống có các biến thể xử lý như tính phí, chọn tuyến đường, định dạng dữ liệu hoặc sắp xếp, đặc biệt khi các nhánh điều kiện ngày càng phức tạp.

Lộ trình gồm **8 mốc**, từ nhận diện hành vi cần thay đổi, thiết kế Strategy interface, triển khai các Concrete Strategies, xây dựng Context dựa trên composition và lựa chọn strategy lúc chạy, đến áp dụng lambda/Comparator trong Java, refactor mã cũ và kiểm thử. Cuối cùng, người học đánh giá ưu nhược điểm và phân biệt Strategy với State hay Template Method.

Học phần dành cho người đã biết lập trình hướng đối tượng Java và muốn cải thiện khả năng thiết kế mã dễ thay đổi. Sau khi hoàn thành, bạn có thể tách các thuật toán khỏi Context, bổ sung phương án xử lý mới mà ít ảnh hưởng mã hiện có, kiểm thử từng biến thể và quyết định khi nào nên dùng Strategy thay vì các phương án đơn giản hơn.