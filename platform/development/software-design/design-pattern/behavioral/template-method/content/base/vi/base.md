# Software Design Design Pattern Behavioral Template Method

Template Method là mẫu thiết kế hành vi giúp định nghĩa bộ khung của một thuật toán trong lớp cơ sở, đồng thời cho phép các lớp con tùy biến một số bước mà không làm thay đổi trình tự chung. Mẫu này hữu ích khi nhiều biến thể của một quy trình chia sẻ cấu trúc xử lý nhưng khác nhau ở vài thao tác cụ thể.

Module phù hợp với người đã nắm Java hướng đối tượng, kế thừa, đa hình và ghi đè phương thức. Bạn sẽ học cách nhận diện thuật toán trùng lặp, phân rã thành các bước, thiết kế abstract class và template method, cài các primitive operations bắt buộc, bước mặc định và hook tùy chọn. Tiếp theo là xây dựng nhiều concrete subclass và tái cấu trúc mã nguồn có logic trùng nhau.

Sau khi hoàn thành, bạn có thể triển khai một quy trình Java có thứ tự ổn định nhưng hỗ trợ các biến thể, viết kiểm thử để bảo vệ thứ tự thực thi và lựa chọn giữa Template Method dựa trên kế thừa với Strategy dựa trên composition. Trọng tâm là mở rộng có kiểm soát, tránh lạm dụng hệ phân cấp lớp và giảm chi phí bảo trì.