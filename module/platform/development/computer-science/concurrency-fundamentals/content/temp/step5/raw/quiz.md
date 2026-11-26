Sự khác biệt cốt lõi giữa concurrency và parallelism là gì?
A. Concurrency buộc các tác vụ chạy trên nhiều lõi
B. Concurrency cho phép tác vụ tiến triển xen kẽ
C. Concurrency bảo đảm mọi tác vụ hoàn tất đúng thứ tự
D. Concurrency yêu cầu mỗi tác vụ có một máy riêng
Đáp án đúng: B

Hai thread cùng thực hiện counter++ trên biến int thường có thể mất lượt tăng vì sao?
A. Các bước đọc, cộng, ghi không diễn ra nguyên tử
B. CPU luôn ưu tiên thread được khởi tạo đầu tiên
C. Biến int của các thread luôn tách biệt hoàn toàn
D. Phép tăng chỉ được thực thi sau khi thread join
Đáp án đúng: A

Tình huống nào biểu hiện race condition trên dữ liệu dùng chung?
A. Hai thread cùng đọc một cấu hình bất biến
B. Hai thread xử lý dữ liệu riêng không giao nhau
C. Kết quả phụ thuộc thứ tự ghi đọc thiếu đồng bộ
D. Một thread chờ tác vụ khác kết thúc rồi mới ghi
Đáp án đúng: C

Trong Java, synchronized trên cùng monitor cung cấp bảo đảm nào?
A. Mọi thao tác trên mọi object đều thành nguyên tử
B. Các thread bị ép chạy tuần tự trên cùng lõi
C. Loại trừ lẫn nhau và bảo đảm hiển thị bộ nhớ
D. Deadlock không thể xuất hiện trong khối đồng bộ
Đáp án đúng: C

Một biến chia sẻ được khai báo volatile trong Java có tác dụng nào?
A. Đồng bộ chuỗi read-modify-write trên nhiều biến
B. Biến mọi thao tác tăng biến thành nguyên tử
C. Ngăn thread khác cập nhật giá trị của biến
D. Bảo đảm visibility nhưng không làm ++ nguyên tử
Đáp án đúng: D

Muốn tăng bộ đếm từ nhiều thread mà không tự quản lý lock, cách nào đúng?
A. Dùng AtomicInteger với thao tác tăng nguyên tử
B. Dùng int thường rồi kiểm tra giá trị sau join
C. Chỉ đánh dấu getter của counter synchronized
D. Dùng volatile int và thực hiện phép counter++
Đáp án đúng: A

Phương thức join() của Thread thường dùng để làm gì?
A. Hủy thread hiện tại dù công việc chưa xong
B. Chờ một thread kết thúc trước khi tiếp tục
C. Buộc thread chạy lại trên một CPU khác
D. Chuyển lock đang giữ sang thread đang chờ
Đáp án đúng: B

Thread 1 giữ A rồi đợi B; thread 2 giữ B rồi đợi A. Đây là hiện tượng gì?
A. Livelock do các thread liên tục nhường nhau
B. Starvation do một thread mãi bị bỏ qua
C. Race condition do hai thread cùng đọc biến
D. Deadlock do chu trình chờ khóa lẫn nhau
Đáp án đúng: D

Khi một thao tác cần nhiều lock, biện pháp nào giảm nguy cơ deadlock?
A. Thêm sleep giữa các lần lấy khóa được yêu cầu
B. Đảo thứ tự lấy khóa tùy vào thread thực thi
C. Dùng thêm thread chỉ để đếm số khóa đang giữ
D. Lấy các khóa theo một thứ tự chung nhất quán
Đáp án đúng: D

Trong mô hình producer-consumer, BlockingQueue hỗ trợ điều gì?
A. Chờ khi hàng đợi rỗng hoặc không còn chỗ chứa
B. Cho phép đọc trước khi phần tử được đưa vào
C. Buộc mỗi producer chạy trên một lõi riêng biệt
D. Tự tạo thứ tự ưu tiên cho mọi công việc
Đáp án đúng: A

Khi một thread cần thấy dữ liệu do thread khác công bố, điều kiện nào quan trọng?
A. Hai thread được gán cùng độ ưu tiên ở JVM
B. Mỗi thread tạo logger riêng cho mọi truy cập
C. Có quan hệ happens-before phù hợp giữa hai bên
D. Các phương thức đọc ghi ở cùng một package
Đáp án đúng: C

Vì sao đối tượng bất biến được công bố an toàn thuận lợi cho đọc đồng thời?
A. Có thể đọc trạng thái đó mà không cần khóa bổ sung
B. Có thể sửa bất kỳ field nào mà không cần khóa
C. Tất cả thao tác với object sẽ luôn chạy song song
D. Các phương thức I/O mặc định trở thành non-blocking
Đáp án đúng: A

Khác biệt chính giữa deadlock và livelock là gì?
A. Deadlock luôn tiêu thụ CPU nhiều hơn livelock
B. Livelock vẫn đổi trạng thái nhưng không tiến triển
C. Livelock chỉ xảy ra khi dùng khóa reentrant
D. Deadlock chỉ xuất hiện khi nhiều thread cùng đọc
Đáp án đúng: B

Tại sao chạy test đồng thời thành công một lần chưa chứng minh chương trình đúng?
A. JVM luôn giữ một lịch chạy cố định cho mọi lần
B. Data race chỉ xuất hiện ngoài môi trường kiểm thử
C. Lỗi đồng thời nhất thiết biểu hiện ở mỗi lần chạy
D. Lịch thực thi khác có thể phơi bày lỗi hiếm gặp
Đáp án đúng: D

Một tác vụ luôn bị trì hoãn vì các tác vụ khác giành tài nguyên trước. Đây là gì?
A. Deadlock vì hình thành chu trình chờ nhiều khóa
B. Livelock vì các tác vụ liên tục đổi trạng thái
C. Starvation vì không nhận đủ cơ hội thực thi
D. Contention vì tất cả tác vụ đều chậm như nhau
Đáp án đúng: C

Khi kết thúc ExecutorService sau xử lý, hướng tiếp cận nào hợp lý?
A. Thoát main ngay dù các worker chưa hoàn thành
B. Ngừng nhận job mới rồi chờ job còn lại hoàn tất
C. Gọi Thread.stop() trên toàn bộ thread của pool
D. Giữ pool mở đến khi tiến trình tự động thoát
Đáp án đúng: B
