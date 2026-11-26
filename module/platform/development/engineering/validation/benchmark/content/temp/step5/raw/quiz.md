Câu 1: Khi thiết kế workload benchmark, tiêu chí quan trọng nhất là gì?
A. Chỉ dùng đầu vào nhỏ nhất để giảm thời gian đo
B. Phản ánh kiểu dữ liệu và tần suất thao tác cần đánh giá
C. Chỉ dùng trường hợp nhanh nhất để tránh nhiễu kết quả
D. Chỉ dùng một loại yêu cầu bất kể đặc điểm hệ thống
Đáp án đúng: B

Câu 2: JMH microbenchmark thích hợp nhất cho mục tiêu nào?
A. Đo trải nghiệm người dùng trên toàn mạng nhiều vùng
B. Đo toàn bộ giao dịch web qua trình duyệt và database
C. Đo chi phí một thao tác Java nhỏ được cô lập
D. Đo khả năng phục hồi của cụm server sau mất điện
Đáp án đúng: C

Câu 3: Vì sao cần warmup trước khi đo code Java trên JVM?
A. Cho JVM tối ưu bằng JIT và ổn định trạng thái chạy
B. Cho JVM xóa toàn bộ bytecode của các phương thức
C. Cho JVM vô hiệu hóa garbage collector trong lần đo
D. Cho JVM dùng chính xác một core CPU cho mọi phép đo
Đáp án đúng: A

Câu 4: Trong JMH, annotation nào đánh dấu phương thức cần đo?
A. @Setup trên phương thức thực hiện tác vụ
B. @State trên phương thức thực hiện tác vụ
C. @Benchmark trên phương thức thực hiện tác vụ
D. @Fork trên phương thức thực hiện tác vụ
Đáp án đúng: C

Câu 5: Vì sao kết quả benchmark có thể sai nếu giá trị tính ra không được dùng?
A. JIT luôn chặn biên dịch mọi phương thức không có return
B. JIT có thể loại bỏ phần tính toán không ảnh hưởng kết quả
C. JVM luôn ghi kết quả bị bỏ vào file log benchmark
D. JVM luôn tăng số luồng để tính lại cùng biểu thức
Đáp án đúng: B

Câu 6: Blackhole trong JMH giúp giảm nguy cơ nào?
A. Đồng bộ kết nối mạng giữa các tiến trình load test
B. Bỏ qua bước warmup dù code có nhánh được JIT tối ưu
C. Tối ưu loại bỏ kết quả tính toán khi không được tiêu thụ
D. Tự phân phối request đến nhiều vùng của hệ thống
Đáp án đúng: C

Câu 7: Trong JMH, vì sao dùng nhiều @Fork hữu ích?
A. Tăng số thread trong cùng JVM mà không cần cấu hình
B. Thay đổi source của phương thức trước mỗi lượt đo
C. Lặp thao tác trong cùng iteration mà không reset state
D. Có các lần đo trên JVM riêng để giảm lệch do trạng thái
Đáp án đúng: D

Câu 8: @Measurement trong JMH khác @Warmup ở mục đích nào?
A. Biên dịch lại mọi class để chuẩn bị chạy application
B. Ghi các lượt dùng làm số liệu sau giai đoạn làm nóng
C. Xóa mọi object còn sống trước khi chạy mỗi iteration
D. Thay thế tất cả JVM fork bằng vòng đo duy nhất
Đáp án đúng: B

Câu 9: Dùng @State(Scope.Thread) trong JMH có ý nghĩa nào?
A. Mỗi thread benchmark nhận trạng thái riêng của nó
B. Mọi thread dùng chung một object trạng thái toàn cục
C. Mỗi invocation tự sinh thread và gọi phép đo một lần
D. Mỗi benchmark khởi chạy tiến trình JVM riêng cho state
Đáp án đúng: A

Câu 10: Nếu dùng @Setup(Level.Trial), thiết lập được gọi khi nào?
A. Mỗi lần gọi phương thức @Benchmark trên cùng trial
B. Một lần cho mỗi trial của trạng thái tương ứng
C. Sau mỗi measurement iteration của cùng trial
D. Sau khi tất cả trial đã kết thúc hoàn toàn
Đáp án đúng: B

Câu 11: Trong JMH, @Param thường được dùng để làm gì?
A. Đổi kết quả tính toán của phép đo thành một hằng số
B. Tự thay đổi tốc độ CPU trước từng JVM fork
C. Chạy phép đo với nhiều cấu hình giá trị đầu vào
D. Ghi toàn bộ log ứng dụng vào file báo cáo kết quả
Đáp án đúng: C

Câu 12: Trong JMH, Mode.Throughput thể hiện đại lượng gì?
A. Số thao tác hoàn thành trên một đơn vị thời gian
B. Thời gian trung bình của mỗi thao tác đã hoàn thành
C. Dung lượng bộ nhớ lớn nhất của toàn bộ JVM
D. Tỷ lệ lỗi của mọi request trong một lượt phát tải
Đáp án đúng: A

Câu 13: Với cùng workload, AvgTime nhỏ hơn thường thể hiện điều gì?
A. Số thao tác hoàn thành mỗi giây nhất định cao hơn
B. Tỷ lệ lỗi request nhất định thấp hơn ở mọi tải
C. Mức sử dụng bộ nhớ nhất định thấp hơn khi chạy
D. Thời gian trung bình để hoàn thành thao tác thấp hơn
Đáp án đúng: D

Câu 14: Khi cần xem phân bố độ trễ thao tác, JMH có chế độ nào?
A. Mode.SampleTime lấy mẫu thời gian thực hiện thao tác
B. Mode.Throughput lấy mẫu kích thước heap mỗi giây
C. Mode.SingleShotTime tự xuất ra phân phối request
D. Mode.AverageTime tự lưu lịch sử mọi request
Đáp án đúng: A

Câu 15: Trong JMH, @OutputTimeUnit dùng để điều chỉnh điều gì?
A. Đơn vị hiển thị của kết quả thời gian đo
B. Đơn vị tính chính xác tuyệt đối của bộ hẹn giờ
C. Đơn vị kích thước bộ nhớ của phương thức được đo
D. Đơn vị nhiệt độ CPU trong báo cáo benchmark
Đáp án đúng: A

Câu 16: Nếu phương thức đo có truy cập file hay network ngoài mục tiêu đo, rủi ro nào xuất hiện?
A. Thời gian đo luôn giảm vì hệ điều hành cache mọi I/O
B. JIT luôn thay mọi thao tác I/O bằng giá trị cố định
C. Benchmark tự đổi sang kiểm tra chức năng khi có I/O
D. Chi phí I/O che khuất chi phí thao tác đang cần đo
Đáp án đúng: D

Câu 17: Muốn đánh giá thời gian đáp ứng API gồm cả tầng database, nên chọn phép đo nào?
A. Microbenchmark một hàm chuyển đổi chuỗi không gọi DB
B. Bài kiểm tra linter của repository không chạy API
C. Bài kiểm tra end-to-end với tải và dữ liệu đại diện
D. Phép đo riêng tốc độ vòng lặp trong compiler JIT
Đáp án đúng: C

Câu 18: Với workload open-loop của công cụ phát tải, điều nào đúng?
A. Yêu cầu được lên lịch theo tốc độ đến độc lập phản hồi
B. Yêu cầu mới chỉ gửi khi yêu cầu trước đã hoàn tất
C. Số yêu cầu đến bằng số thread hoàn thành trong mọi giây
D. Tốc độ đến tự giảm về không khi server đáp ứng chậm
Đáp án đúng: A

Câu 19: Với workload closed-loop, lưu lượng mới phụ thuộc vào điều gì?
A. Số client đang chờ phản hồi và thời gian xử lý
B. Lịch đến độc lập mọi phản hồi của service đang đo
C. Băng thông tải lên chỉ do cấu hình DNS quyết định
D. Kích thước heap của load generator sau warmup
Đáp án đúng: A

Câu 20: Coordinated omission khi phát tải có thể gây sai lệch nào?
A. Ghi nhận quá nhiều lỗi compile của mã trong IDE
B. Tự thêm khoảng thời gian JIT không thuộc workload
C. Ghi số lượng request lớn hơn số request thực gửi
D. Không ghi nhận đủ các chờ đợi khi hệ thống ngừng đáp ứng
Đáp án đúng: D

Câu 21: Khi báo cáo p99 latency, giá trị đó thường có nghĩa gì?
A. Khoảng 99% CPU core luôn bận trong thời gian đo
B. Khoảng 99% bộ nhớ heap đã được cấp phát
C. Khoảng 99% request đều có độ trễ bằng giá trị đó
D. Khoảng 99% request có độ trễ không vượt quá ngưỡng
Đáp án đúng: D

Câu 22: Vì sao kết quả phát tải cần báo cả tỷ lệ lỗi bên cạnh latency?
A. Tỷ lệ lỗi luôn bằng tỷ lệ cache miss trong mọi trường hợp
B. Tỷ lệ lỗi quyết định trực tiếp phiên bản JDK được dùng
C. Độ trễ thấp có thể do request lỗi hoặc bị từ chối
D. Độ trễ đã tự biểu thị toàn bộ số request không thành công
Đáp án đúng: C

Câu 23: Khi tăng concurrent clients, vì sao throughput có thể không tăng tiếp?
A. Số client luôn làm CPU tự vô hiệu hóa JIT optimization
B. Nút thắt tài nguyên làm hệ thống bão hòa và tăng chờ
C. Throughput được cố định bởi số lượng source file Java
D. Các request mới luôn chạy song song mà không tranh chấp
Đáp án đúng: B

Câu 24: Muốn so sánh baseline với bản code mới, điều kiện nào quan trọng?
A. Đổi cả phần cứng lẫn dataset để thử nhiều tình huống
B. Chỉ đo nhánh mới với tải thấp hơn baseline
C. Chỉ chọn lần chạy nhanh nhất của mỗi phiên bản
D. Giữ tải, dữ liệu và cấu hình môi trường tương đương
Đáp án đúng: D

Câu 25: Vì sao nên đo nhiều fork hoặc nhiều lần chạy độc lập?
A. Loại bỏ hoàn toàn jitter từ scheduler và GC ở mọi lần
B. Ước lượng dao động và giảm lệ thuộc một kết quả đơn
C. Bảo đảm mọi lần chạy luôn có chính xác cùng latency
D. Làm JVM tối ưu code giống nhau bất kể phần cứng
Đáp án đúng: B

Câu 26: Nguồn nhiễu nào thường khiến benchmark JVM thiếu ổn định?
A. Tên thư mục mã nguồn và số commit trong Git log
B. Định dạng file README và màu giao diện IDE
C. Độ dài tên package và thứ tự các import Java
D. JIT, GC và thay đổi xung CPU hoặc tải nền
Đáp án đúng: D

Câu 27: Để đo tác động cấp phát object, phép đo bổ sung nào hữu ích?
A. Đếm số file source được thêm trong nhánh hiện tại
B. Theo dõi allocation rate và thời gian GC khi đo
C. Đếm số mục TODO trong các bài unit test
D. Đếm số ký tự đã đổi trong Git diff trước release
Đáp án đúng: B

Câu 28: Khi phát hiện regression nhỏ hơn dao động giữa các lần đo, nên làm gì?
A. Kết luận đã chậm dù các phép đo chưa phân biệt được
B. Bỏ mọi kết quả chậm và giữ lần chạy nhanh nhất
C. Thu thêm mẫu và xét độ bất định trước khi kết luận
D. Tăng concurrency tùy ý rồi thay baseline cũ
Đáp án đúng: C
