Bạn phân biệt concurrency và parallelism như thế nào, và trong trường hợp nào chương trình có concurrency dù chỉ chạy trên một lõi xử lý?
Bạn giải thích sự khác biệt giữa tiến trình, luồng và tác vụ bất đồng bộ khi tổ chức công việc đồng thời ra sao?
Bạn đánh giá những lợi ích và chi phí của việc chia một chương trình tuần tự thành nhiều tác vụ đồng thời như thế nào?
Bạn mô tả cách bộ lập lịch và việc chuyển ngữ cảnh có thể tác động đến thứ tự thực thi và kết quả của chương trình ra sao?
Khi hai lần chạy cùng một đầu vào cho kết quả khác nhau, bạn xác định vai trò của interleaving như thế nào?
Bạn phân biệt tính đúng đắn về safety và khả năng tiến triển về liveness bằng những ví dụ nào?
Bạn xác định các giả định về thứ tự thực thi nào khiến một chương trình có vẻ đúng khi chạy đơn luồng nhưng sai khi chạy đồng thời?
Bạn phân biệt data race và race condition về bản chất và hậu quả như thế nào?
Nếu nhiều luồng cùng tăng một biến đếm, bạn giải thích vì sao kết quả cuối có thể nhỏ hơn số lần tăng dự kiến?
Bạn xác định critical section trong một luồng xử lý có cập nhật nhiều trường dữ liệu liên quan như thế nào?
Bạn giải thích tính atomic của một thao tác khác gì so với tính atomic của cả một chuỗi thao tác như thế nào?
Khi một thao tác kiểm tra điều kiện rồi mới cập nhật dữ liệu, bạn phát hiện và khắc phục lỗi check-then-act ra sao?
Bạn giải thích vì sao một luồng có thể không nhìn thấy giá trị vừa được luồng khác cập nhật dù cả hai cùng dùng chung bộ nhớ?
Bạn phân tích tác động của việc sắp xếp lại lệnh bởi trình biên dịch hoặc bộ xử lý đối với chương trình đồng thời như thế nào?
Bạn vận dụng quan hệ happens-before để lập luận về tính hiển thị và thứ tự quan sát dữ liệu ra sao?
Khi một cờ trạng thái được nhiều luồng đọc và ghi, bạn quyết định cần đồng bộ bộ nhớ bằng cách nào?
Bạn lựa chọn phép toán nguyên tử thay cho lock trong những trường hợp nào và cần lưu ý giới hạn gì?
Bạn giải thích cơ chế compare-and-swap và phân tích tình huống ABA khi thiết kế cấu trúc dữ liệu đồng thời như thế nào?
Bạn phân biệt yêu cầu về memory ordering và yêu cầu về mutual exclusion khi chọn công cụ đồng bộ ra sao?
Bạn thiết kế phạm vi khóa để bảo vệ bất biến của dữ liệu dùng chung mà vẫn tránh giữ khóa quá lâu như thế nào?
Bạn đánh giá tác động của độ hạt khóa lên mức tranh chấp, độ phức tạp và khả năng mở rộng ra sao?
Bạn phân tích lợi ích và rủi ro của reentrant lock khi một lời gọi có thể đi qua nhiều method cùng sử dụng khóa như thế nào?
Nếu một tác vụ ném ngoại lệ khi đang giữ khóa, bạn thiết kế việc giải phóng tài nguyên và khôi phục trạng thái ra sao?
Bạn mô tả cách hình thành deadlock khi các tác vụ giữ nhiều khóa và chờ tài nguyên của nhau như thế nào?
Bạn áp dụng các điều kiện cần của deadlock để nhận diện điểm rủi ro trong một thiết kế cụ thể ra sao?
Bạn xây dựng và duy trì quy tắc thứ tự lấy khóa trong hệ thống có nhiều tài nguyên dùng chung như thế nào?
Bạn phân biệt deadlock, livelock và starvation qua biểu hiện khi chương trình chạy như thế nào?
Khi một tác vụ liên tục nhường quyền nhưng không hoàn thành, bạn điều tra và khắc phục vấn đề tiến triển ra sao?
Bạn đánh giá sự đánh đổi giữa tính công bằng khi cấp khóa và thông lượng xử lý của hệ thống như thế nào?
Nếu một luồng ưu tiên cao bị chặn bởi luồng ưu tiên thấp đang giữ khóa, bạn giải thích và xử lý priority inversion ra sao?
Bạn sử dụng condition variable hoặc cơ chế chờ-thông báo như thế nào để tránh missed signal và thức dậy giả?
Bạn thiết kế bài toán producer-consumer với bộ đệm hữu hạn để giữ đúng thứ tự và tránh mất dữ liệu như thế nào?
Bạn lựa chọn semaphore, mutex và barrier cho các yêu cầu phối hợp tác vụ khác nhau dựa trên tiêu chí nào?
Khi nhiều tác vụ phải hoàn thành một giai đoạn trước khi bước tiếp, bạn tổ chức cơ chế đồng bộ và xử lý tác vụ thất bại ra sao?
Bạn so sánh chia sẻ trạng thái có khóa với truyền thông điệp khi thiết kế các thành phần xử lý đồng thời như thế nào?
Bạn đánh giá các bảo đảm về thread safety của một queue đồng thời trước khi dùng nó để trao đổi công việc như thế nào?
Bạn tận dụng dữ liệu bất biến và sở hữu trạng thái theo từng tác vụ để giảm nhu cầu đồng bộ ra sao?
Khi một đối tượng được tạo trong một luồng rồi chia sẻ cho luồng khác, bạn bảo đảm việc công bố đối tượng an toàn như thế nào?
Bạn thiết kế cơ chế hủy tác vụ để tránh bỏ dở trạng thái nhất quán và không gây rò rỉ tài nguyên ra sao?
Nếu một tác vụ chờ khóa hoặc phản hồi quá lâu, bạn sử dụng timeout và chính sách thử lại theo nguyên tắc nào?
Bạn tổ chức quy trình shutdown để các tác vụ đang chạy có thể hoàn thành hoặc dừng an toàn như thế nào?
Bạn chọn kích thước thread pool và hàng đợi công việc dựa trên đặc điểm tác vụ CPU-bound hay I/O-bound ra sao?
Khi tốc độ tạo công việc vượt quá tốc độ xử lý, bạn thiết kế backpressure và giới hạn tải như thế nào?
Bạn xác định nguyên nhân tăng độ trễ khi số luồng tăng nhưng thông lượng không cải thiện ra sao?
Bạn quyết định phần nào của một thuật toán có thể chạy song song và phần nào bắt buộc giữ thứ tự dựa trên phụ thuộc dữ liệu như thế nào?
Bạn đánh giá lợi ích và rủi ro của thuật toán lock-free so với thiết kế sử dụng khóa truyền thống ra sao?
Khi một tác vụ trong nhóm tác vụ đồng thời thất bại, bạn xác định cách lan truyền lỗi và hủy các tác vụ liên quan như thế nào?
Bạn xây dựng stress test có khả năng phơi bày lỗi tranh chấp dữ liệu vốn ít xuất hiện trong chạy thử thông thường ra sao?
Bạn dùng điều khiển lịch thực thi, kiểm thử bất biến hoặc mô hình hóa trạng thái để tìm lỗi đồng thời như thế nào?
Khi hệ thống production thỉnh thoảng treo hoặc trả dữ liệu không nhất quán, bạn thu thập dấu vết và khoanh vùng vấn đề đồng thời ra sao?
