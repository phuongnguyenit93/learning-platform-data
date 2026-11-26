1. Điểm khác nhau chủ yếu giữa phân tích tĩnh và kiểm thử động là gì?
A. Theo dõi ứng dụng đang chạy để quan sát các nhánh lỗi
B. Sinh dữ liệu đầu vào rồi thực thi toàn bộ bộ kiểm thử
C. Kiểm tra source hoặc bytecode mà không chạy ứng dụng
D. Đo độ trễ endpoint khi hệ thống nhận tải thực tế
Đáp án đúng: C

2. Trong control-flow graph, cạnh giữa hai basic block biểu diễn điều gì?
A. Quan hệ khai báo kiểu giữa các package trong dự án
B. Đường truyền dữ liệu giữa hai phiên bản của một JAR
C. Sự thay đổi giá trị của biến theo thời gian thực thi
D. Khả năng chuyển luồng điều khiển giữa hai basic block
Đáp án đúng: D

3. Phân tích dataflow thường xác định thuộc tính chương trình bằng cách nào?
A. Lan truyền thông tin qua CFG cho tới điểm hội tụ
B. Đo số lần gọi hàm khi ứng dụng chạy dưới tải
C. Đọc các mô tả API từ chú thích của lập trình viên
D. So sánh thời gian build của những phiên bản khác nhau
Đáp án đúng: A

4. Trong reaching definitions, thông tin cần tìm tại một điểm đọc biến là gì?
A. Những phép gán đã chạy trong mọi test tích hợp
B. Các phép gán có thể tới lúc đọc mà chưa bị ghi đè
C. Những biến còn sống sau mọi lần gọi phương thức
D. Những khai báo public được module khác import
Đáp án đúng: B

5. Khi phân tích liveness, một biến được xem là còn sống nếu điều gì có thể xảy ra?
A. Biến được khai báo trong cùng một basic block
B. Kiểu của biến được export qua module descriptor
C. Biến được cấp phát trên heap thay vì stack
D. Giá trị còn được đọc trước lần gán tiếp theo
Đáp án đúng: D

6. Trong may analysis, phát biểu nào mô tả ý nghĩa của một kết quả có thể xảy ra?
A. Mọi đường đi khả thi đều thỏa điều kiện xét
B. Có ít nhất một đường đi thỏa điều kiện xét
C. Chỉ những đường đi đã được chạy mới được xét
D. Điều kiện chỉ đúng khi build ở chế độ debug
Đáp án đúng: B

7. Abstract interpretation thường giảm độ phức tạp không gian trạng thái bằng cách nào?
A. Thay mọi lời gọi phương thức bằng dữ liệu đo hiệu năng
B. Liệt kê đầy đủ mọi đầu vào có thể có của chương trình
C. Chạy chương trình với tất cả cấu hình môi trường
D. Gom trạng thái cụ thể vào một miền trừu tượng
Đáp án đúng: D

8. Miền trừu tượng interval `[2, 8]` của một biến số thường có ý nghĩa gì?
A. Giá trị của biến luân phiên chính xác giữa 2 và 8
B. Biến chỉ được sử dụng tại dòng lệnh số 2 và số 8
C. Biến phải được gán đúng 8 lần rồi đọc đúng 2 lần
D. Biến có thể nhận các giá trị từ 2 đến 8
Đáp án đúng: D

9. Trong dataflow analysis, phép `join` ở điểm hợp nhánh thường làm gì?
A. Gộp dữ kiện các nhánh đến theo miền trừu tượng
B. Xóa toàn bộ dữ liệu của nhánh có cảnh báo trước đó
C. Gộp các module JAR thành một file để biên dịch
D. Chọn đường chạy có thời gian thực thi ngắn nhất
Đáp án đúng: A

10. Vì sao phân tích dataflow trên vòng lặp thường phải lặp tới fixpoint?
A. Mọi nhánh cần được đo thời gian chạy như nhau
B. Mỗi phép gán cần được thực thi đúng một lần
C. Cập nhật trạng thái nút cho đến khi ổn định
D. Số vòng lặp thực tế luôn biết trước lúc phân tích
Đáp án đúng: C

11. Tình huống nào là false positive từ công cụ phân tích tĩnh?
A. Công cụ không cảnh báo dù đường chạy có lỗi thật
B. Công cụ tìm đúng lỗi được tái hiện qua kiểm thử
C. Báo lỗi dù mọi đường chạy thực tế đều an toàn
D. Công cụ báo thành công khi build hoàn tất bình thường
Đáp án đúng: C

12. Tình huống nào là false negative trong báo cáo phân tích tĩnh?
A. Có cảnh báo dù mọi đường thực thi đều an toàn
B. Có cảnh báo bị loại vì đã được review và sửa lỗi
C. Có cảnh báo đúng ở một đường thực thi khả thi
D. Có lỗi thật nhưng công cụ không đưa ra cảnh báo
Đáp án đúng: D

13. Nếu giảm phạm vi rule để hạn chế cảnh báo sai, rủi ro thường gặp là gì?
A. Công cụ tự động bỏ qua mọi file Java mới thêm
B. Tất cả cảnh báo đúng sẽ tự biến thành cảnh báo sai
C. Bỏ sót lỗi thật ngoài phạm vi rule được bật
D. Các kiểm thử runtime mất khả năng thực thi trên CI
Đáp án đúng: C

14. Điều gì phân biệt phân tích path-sensitive với phân tích bỏ qua điều kiện nhánh?
A. Chỉ dựa vào số lớp được biên dịch trong cùng module
B. Dùng điều kiện nhánh để loại đường đi không khả thi
C. Dùng thời gian chạy trung bình để xếp hạng cảnh báo
D. Chỉ đọc chữ ký phương thức mà không đọc phần thân
Đáp án đúng: B

15. Phân tích interprocedural thường khác intraprocedural ở phạm vi nào?
A. Theo dõi dữ liệu qua lời gọi giữa các phương thức
B. Chỉ phân tích bytecode của những class có annotation
C. Chỉ phân tích các phép gán trong cùng một basic block
D. Chỉ phân tích các nhánh thuộc một phương thức duy nhất
Đáp án đúng: A

16. Trong taint analysis, tham số truy vấn HTTP chưa tin cậy thường thuộc nhóm nào?
A. Sink nhận dữ liệu đã được kiểm tra và mã hóa
B. Sanitizer loại nguy cơ trước khi gọi API nhạy cảm
C. Source đánh dấu đầu vào từ nguồn chưa tin cậy
D. Summary mô tả tác dụng của phương thức an toàn
Đáp án đúng: C

17. Trong taint analysis, sink biểu diễn loại vị trí nào?
A. Điểm nhạy cảm nhận dữ liệu đã bị nhiễm taint
B. Bước chuyển một giá trị sang kiểu dữ liệu khác
C. Nguồn phát sinh dữ liệu người dùng chưa tin cậy
D. Tập nhánh điều khiển dùng để hợp nhất kết quả
Đáp án đúng: A

18. Một sanitizer hữu hiệu trong taint analysis cần đảm bảo điều gì?
A. Xử lý input theo đúng ngữ cảnh trước sink nhạy cảm
B. Đổi tên biến đầu vào trước khi truyền qua lớp service
C. Chuyển mọi chuỗi thành chữ thường trước khi nối SQL
D. Ghi log toàn bộ dữ liệu đầu vào trước khi sử dụng
Đáp án đúng: A

19. Mẫu code nào dễ bị rule bảo mật tĩnh gắn cảnh báo SQL injection?
A. Gán tham số SQL bằng phương thức `setString` có bind
B. Kiểm tra kiểu dữ liệu trước khi truyền vào mapper
C. Nối thẳng tham số request vào chuỗi lệnh SQL
D. Đọc kết quả truy vấn thông qua đối tượng ResultSet
Đáp án đúng: C

20. Khi nào công cụ có cơ sở cảnh báo khả năng NullPointerException?
A. Đối tượng đã được khởi tạo trên tất cả nhánh khả thi
B. Đối tượng nhận lời gọi có thể null trên nhánh khả thi
C. Phương thức có kiểu trả về primitive thay cho reference
D. Giá trị null chỉ xuất hiện trong chuỗi thông báo lỗi
Đáp án đúng: B

21. Vì sao AST thường phù hợp để kiểm tra quy ước cú pháp Java?
A. AST biểu diễn cấu trúc code như khai báo và câu lệnh
B. AST ghi lại giá trị heap trong từng lần chạy chương trình
C. AST mô tả phiên bản phụ thuộc được chọn bởi Maven
D. AST chứa thời gian thực thi của mỗi basic block Java
Đáp án đúng: A

22. Lợi thế nào khiến SpotBugs hữu ích với dự án Java đã biên dịch?
A. Thay đổi quy tắc định dạng của source khi người dùng lưu
B. Phân tích bug pattern từ bytecode dù thiếu source
C. Chạy fuzz testing trên các endpoint của ứng dụng
D. Đo tải bộ nhớ heap trực tiếp khi JVM đang hoạt động
Đáp án đúng: B

23. Error Prone phát hiện nhiều bug pattern Java vào thời điểm nào?
A. Khi JVM tải class rồi thực thi các phương thức
B. Khi Maven tải artifact vào bộ nhớ cache cục bộ
C. Khi trình duyệt gọi các REST endpoint của ứng dụng
D. Trong lúc `javac` biên dịch source bằng các checker
Đáp án đúng: D

24. Cách nào hợp lý để đưa phân tích tĩnh vào CI của dự án Java?
A. Chỉ lưu cảnh báo vào tài liệu khi sprint kết thúc
B. Chạy rule tự động và chặn build theo ngưỡng đã định
C. Chỉ phân tích mã vào lần đầu tạo kho Git mới
D. Chỉ xem cảnh báo bằng tay trên IDE của một thành viên
Đáp án đúng: B
