Câu 1. Docker Compose khởi chạy database trước ứng dụng; điều kiện nào xác nhận database đã sẵn sàng nhận kết nối?
A. Chỉ khai báo thứ tự khởi chạy của các dịch vụ
B. Chỉ chờ một khoảng thời gian cố định đủ dài
C. Chỉ chờ trạng thái container chuyển sang running
D. Dùng healthcheck và chờ trạng thái healthy
Đáp án đúng: D

Câu 2. Testcontainers ánh xạ cổng 5432 trong container; test Java nên lấy cổng kết nối qua đâu?
A. Luôn kết nối trực tiếp localhost:5432
B. Đọc mapped port thực tế từ container
C. Tự giả định cổng theo thứ tự các test
D. Lấy cổng trong file cấu hình production
Đáp án đúng: B

Câu 3. Tại sao WaitStrategy kiểm tra kết nối hoặc health endpoint tốt hơn sleep cố định?
A. Đợi tín hiệu sẵn sàng thay vì đoán thời gian
B. Không còn cần timeout cho thao tác khởi động
C. Đảm bảo dịch vụ luôn khởi động trong một giây
D. Tự thay thế dịch vụ thật thành một server giả
Đáp án đúng: A

Câu 4. Hai pipeline CI cùng chạy Docker Compose trên một host; cách nào giảm xung đột tên tài nguyên?
A. Cho cả hai dùng tên project giống nhau
B. Gán project name riêng cho mỗi lượt chạy
C. Cố định mọi host port bằng cùng một giá trị
D. Dùng chung thư mục dữ liệu đang có ghi
Đáp án đúng: B

Câu 5. Test tạo đơn cần trạng thái tồn kho xác định trước; cách chuẩn bị dữ liệu nào đáng tin cậy?
A. Tận dụng dữ liệu còn lại từ test trước đó
B. Đọc dữ liệu bất kỳ từ môi trường staging
C. Seed dữ liệu đầu vào đã biết trước mỗi ca
D. Giữ nguyên bản ghi tồn kho sau mọi lần chạy
Đáp án đúng: C

Câu 6. Một test khởi chạy container để kiểm tra API rồi kết thúc; thao tác nào giúp không rò tài nguyên?
A. Giữ container chạy để các test sau dùng tạm
B. Chỉ dọn container khi bài test bị thất bại
C. Ghi lại ID container mà không gọi hàm dừng
D. Dừng và xóa container sau khi test kết thúc
Đáp án đúng: D

Câu 7. Dùng container tái sử dụng giữa các test giúp nhanh hơn nhưng có rủi ro nào?
A. Ảnh container mất khả năng truy cập mạng nội bộ
B. Cấu hình image tự đổi theo mỗi lần khởi động
C. Trạng thái từ lượt chạy trước có thể còn lại
D. JUnit không thể khởi tạo test instance mới
Đáp án đúng: C

Câu 8. Mục tiêu chính khi dùng Testcontainers thay cho database giả lập đơn giản là gì?
A. Kiểm tra với dịch vụ thật chạy trong container
B. Không cần cấu hình kết nối mạng cho ứng dụng
C. Tự động thay mọi assertion bằng kết quả build
D. Không còn cần chạy database migration khi test
Đáp án đúng: A

Câu 9. Vì sao test tích hợp SQL với database thật có thể phát hiện lỗi mà repository mock bỏ sót?
A. Mock luôn chạy được mọi database migration mới
B. DB thật kiểm tra cú pháp SQL và constraint
C. Mock tự động đảm bảo transaction isolation đúng
D. DB thật không bao giờ cần chuẩn bị dữ liệu test
Đáp án đúng: B

Câu 10. Cần cấu hình password cho database thử nghiệm bằng Docker Compose; cách nào tiện thay giữa môi trường?
A. Ghi password cố định vào mã nguồn ứng dụng
B. Đặt cùng mật khẩu trong tất cả Docker images
C. Nhập tay mật khẩu khi từng test bắt đầu chạy
D. Truyền biến môi trường hoặc file cấu hình
Đáp án đúng: D

Câu 11. Test chạy trên host muốn kết nối container có mapped port động; thông tin kết nối nên xây dựng ra sao?
A. Dùng host và mapped port được cấp tại runtime
B. Dùng tên container và cổng nội bộ từ mọi host
C. Luôn dùng IP cố định của image đã build trước đó
D. Chỉ dựa vào cổng mặc định ghi trong tài liệu
Đáp án đúng: A

Câu 12. Database container có volume bền vững; điều gì có thể xảy ra khi xóa container mà giữ volume?
A. Schema trở về trạng thái chưa từng khởi tạo
B. Mọi bảng được tự động xóa sau khi container dừng
C. Dữ liệu mất theo bộ nhớ của tiến trình database
D. Volume vẫn giữ dữ liệu cho lượt chạy sau
Đáp án đúng: D

Câu 13. TCP port mở nhưng API vẫn đang chạy migration; kiểm tra nào xác nhận sẵn sàng hợp lý hơn?
A. Chỉ kiểm tra process đã xuất hiện trong docker ps
B. Chỉ kiểm tra rằng host port được cấp khác số không
C. Health endpoint phản ánh ứng dụng đã sẵn sàng
D. Chỉ kiểm tra tệp Dockerfile tồn tại trong repo
Đáp án đúng: C

Câu 14. Với JUnit Jupiter, thao tác reset fixture trước từng test thường đặt ở đâu?
A. Phương thức có annotation @AfterAll
B. Phương thức có annotation @BeforeEach
C. Phương thức có annotation @AfterEach
D. Phương thức có annotation @BeforeAll
Đáp án đúng: B

Câu 15. Khi chạy test song song trên cùng database server, kỹ thuật nào giảm việc test này ảnh hưởng dữ liệu test khác?
A. Cùng truy cập một bảng và tự tăng mọi ID
B. Cho mọi test dùng một tài khoản admin chung
C. Tách schema hoặc ID dữ liệu theo từng test
D. Chỉ đổi thứ tự khởi chạy trong pipeline CI
Đáp án đúng: C

Câu 16. Cố định port host cho mọi container kiểm thử cùng loại dễ gây gì trên CI song song?
A. Xung đột cổng; nên dùng mapped port động
B. Tăng chi phí parse JSON của ứng dụng test
C. Thay đổi transaction isolation trong database
D. Thay đổi thứ tự các assertion mà JUnit thực thi
Đáp án đúng: A

Câu 17. Test database thực hiện thay đổi trong một transaction riêng và rollback khi kết thúc; điều gì được kỳ vọng?
A. Ghi từ process ngoài transaction cũng bị hủy
B. Sự kiện đã gửi ra queue được tự động thu hồi
C. Các file ghi lên đĩa ngoài DB cũng được rollback
D. Ghi của transaction đó bị hủy sau rollback
Đáp án đúng: D

Câu 18. Môi trường test dùng chung với môi trường phát hành tiềm ẩn nguy cơ nào?
A. Test có thể ghi nhầm dữ liệu production
B. Test chạy chậm hơn do nhiều người dùng thực
C. Dữ liệu test sẽ bị xóa sau mỗi lần deploy
D. Container không thể cấu hình biến môi trường
Đáp án đúng: A

Câu 19. Test tích hợp phụ thuộc API Internet và thỉnh thoảng lỗi do mạng; cách giảm tính bất định nào phù hợp?
A. Chỉ kiểm tra startup mà không cần response
B. Stub các đường kiểm thử không cần API thật
C. Tăng timeout lên vô hạn rồi thử chạy lại
D. Chạy test thủ công ở máy có kết nối mạnh
Đáp án đúng: B

Câu 20. Logic hết hạn token dựa vào giờ hiện tại; cách nào giúp test tái lập ở các máy CI?
A. Tiêm clock cố định cho logic được kiểm thử
B. Buộc mọi test chạy vào đúng thời điểm nửa đêm
C. Chỉ tăng timeout cho các assertion thời gian
D. Chỉ chạy test nếu timezone của máy là UTC
Đáp án đúng: A

Câu 21. Dùng image tag latest cho database test có rủi ro gì và nên làm gì?
A. Tag latest luôn bị Docker từ chối khi chạy
B. Tag latest bảo đảm cùng phiên bản trên các máy
C. Phiên bản có thể đổi; nên ghim tag cụ thể
D. Tag latest chỉ sử dụng được với Docker Compose
Đáp án đúng: C

Câu 22. Trong CI, test bị lỗi trước khi vào bước assert; cách bảo đảm dọn tài nguyên phù hợp là gì?
A. Chỉ dọn container sau khi test thành công
B. Chỉ dọn khi nhánh thay đổi được merge lên main
C. Để job tiếp theo tìm và xóa container thừa
D. Dùng teardown chạy cả khi test thất bại
Đáp án đúng: D

Câu 23. Container đổi host/port mỗi lần chạy; test nên truyền JDBC URL vào ứng dụng thế nào?
A. Đổi JDBC URL bên trong JAR đã build xong
B. Tiêm URL từ container vào cấu hình test
C. Dùng URL cố định từ CI của lượt chạy trước
D. Sao chép URL của database production vào test
Đáp án đúng: B

Câu 24. Integration test ổn trên máy dev nhưng thất bại ngẫu nhiên ở CI; kiểm tra nền tảng nào hữu ích nhất?
A. Chỉ so số dòng code giữa hai môi trường
B. Xóa log để tất cả test chạy nhanh hơn
C. Xem readiness, dữ liệu và cô lập tài nguyên
D. Chỉ tăng số worker mà không đo nguyên nhân
Đáp án đúng: C
