Câu 1. Mục tiêu chính của Flyway trong dự án cơ sở dữ liệu là gì?
A. Tự điều chỉnh kế hoạch thực thi của câu truy vấn SQL
B. Áp dụng thay đổi lược đồ theo phiên bản đã quản lý
C. Tự cân bằng các replica giữa những node trong cluster
D. Sinh lớp entity từ kết quả truy vấn trên database
Đáp án đúng: B

Câu 2. Tên file nào tuân theo quy ước versioned SQL migration của Flyway?
A. `V3_add_customer_index.sql`
B. `V3__add_customer_index.sql`
C. `R3__add_customer_index.sql`
D. `V3--add_customer_index.sql`
Đáp án đúng: B

Câu 3. Tên file nào tuân theo quy ước repeatable SQL migration mặc định?
A. `V__refresh_reporting_view.sql`
B. `R4__refresh_reporting_view.sql`
C. `R_refresh_reporting_view.sql`
D. `R__refresh_reporting_view.sql`
Đáp án đúng: D

Câu 4. Với một versioned migration đã chạy thành công, Flyway thường xử lý ra sao ở lần migrate kế tiếp?
A. Chạy lại phiên bản đó mỗi lần ứng dụng khởi động
B. Bỏ qua phiên bản đó nếu lịch sử đã ghi nhận
C. Chạy lại phiên bản đó mỗi khi cấu trúc bảng đổi
D. Xóa phiên bản đó khỏi lịch sử sau mỗi lần chạy
Đáp án đúng: B

Câu 5. Điều gì khiến repeatable migration được thực thi lại trong lần migrate sau?
A. Nội dung thay đổi làm checksum của file đổi
B. Số lượng bản ghi của bảng được cập nhật tăng
C. Thời gian hệ thống vượt quá chu kỳ một ngày
D. Phiên bản của một migration khác được tăng
Đáp án đúng: A

Câu 6. Flyway dùng schema history để theo dõi thông tin nào?
A. Các kết nối đang hoạt động cùng thời điểm tạo
B. Các phiên giao dịch chưa commit trên các node
C. Các migration đã xử lý cùng trạng thái thực thi
D. Các truy vấn đọc chậm cùng kế hoạch tối ưu SQL
Đáp án đúng: C

Câu 7. Tên mặc định của bảng lưu schema history trong Flyway là gì?
A. `flyway_schema_history`
B. `flyway_schema_version`
C. `flyway_database_history`
D. `flyway_migration_state`
Đáp án đúng: A

Câu 8. Nếu sửa nội dung một versioned migration đã áp dụng, `validate` thường phát hiện điều gì?
A. Bảng schema history tự bị xóa khi chạy validate
B. Tất cả migration đã chạy đều được thực thi lại
C. Phiên bản file tự đổi sang repeatable migration
D. Checksum trong file khác checksum đã ghi lịch sử
Đáp án đúng: D

Câu 9. Lệnh `migrate` chủ yếu thực hiện thao tác nào?
A. Tự phục hồi toàn bộ database từ một bản snapshot
B. Xóa mọi bảng được tạo từ các migration đã chạy
C. Thay đổi checksum đã lưu mà không thực thi script
D. Áp dụng các migration còn chờ theo quy tắc Flyway
Đáp án đúng: D

Câu 10. Lệnh `info` hữu ích nhất khi cần xem điều gì?
A. Hiệu suất xử lý chỉ mục của mọi câu truy vấn
B. Trạng thái và thứ tự của các migration Flyway
C. Trạng thái bộ nhớ đệm của server cơ sở dữ liệu
D. Thời gian phản hồi của từng API đang vận hành
Đáp án đúng: B

Câu 11. Khi nhận một database có sẵn schema nhưng chưa quản lý Flyway, `baseline` làm gì?
A. Đánh dấu mốc khởi đầu vào schema history
B. Xóa schema hiện có rồi áp dụng lại từ phiên bản đầu
C. Tự sinh file SQL từ mọi bảng hiện có trên DB
D. Thực hiện mọi migration cũ theo thứ tự phiên bản
Đáp án đúng: A

Câu 12. Sau khi baseline ở version 5, migration version 4 thường được xem như thế nào?
A. Được áp dụng lại sau mỗi lần chạy validate
B. Thuộc sau mốc baseline và sẽ được chạy ngay
C. Thuộc trước mốc baseline và không được chạy
D. Được chuyển thành repeatable khi chạy migrate
Đáp án đúng: C

Câu 13. Rủi ro khi bật `baselineOnMigrate` không kiểm soát là gì?
A. Có thể tự đánh dấu baseline trên schema có sẵn
B. Có thể tự tạo bản backup trước khi mỗi migration
C. Có thể tự tăng version cho các migration bị trùng
D. Có thể tự chuyển mọi SQL script sang Java class
Đáp án đúng: A

Câu 14. `repair` nên được hiểu đúng theo phạm vi nào?
A. Khôi phục mọi thay đổi DDL đã chạy trên database
B. Phục hồi bản sao database trước khi chạy migrate
C. Sửa metadata lịch sử theo trạng thái migration
D. Tự tạo migration SQL thay thế các file bị mất
Đáp án đúng: C

Câu 15. Sau một lần `repair` thành công, điều nào vẫn cần kiểm tra?
A. Mức độ phân mảnh cache trên các application node
B. Phiên bản hệ điều hành trên toàn bộ build agent
C. Bộ nhớ trống của máy chạy chương trình quản trị
D. Trạng thái schema thực tế sau lỗi migration cũ
Đáp án đúng: D

Câu 16. Khi hai nhánh Git đều tạo `V7__...sql` khác nội dung, nên làm gì trước merge?
A. Chấp nhận cả hai vì Flyway dựa trên tên mô tả
B. Bỏ phần phiên bản để Flyway chạy song song
C. Đổi một version để tránh xung đột định danh
D. Đặt cả hai file vào thư mục riêng cùng location
Đáp án đúng: C

Câu 17. Flyway xử lý thứ tự `V2` và `V10` theo cách nào?
A. Sắp theo thời điểm tạo file trên hệ thống
B. Sắp theo dung lượng SQL script từ nhỏ đến lớn
C. Sắp theo version nên V2 được chạy trước V10
D. Sắp theo chuỗi tên nên V10 được chạy trước V2
Đáp án đúng: C

Câu 18. Trong Spring Boot, thư mục mặc định cho SQL migration thường là gì?
A. `classpath:sql/changes`
B. `classpath:db/migration`
C. `classpath:sql/migrate`
D. `classpath:db/schema`
Đáp án đúng: B

Câu 19. Thiết lập Spring Boot nào tắt việc tự chạy Flyway khi khởi động?
A. `spring.flyway.baseline=false`
B. `spring.flyway.locations=false`
C. `spring.flyway.validate=false`
D. `spring.flyway.enabled=false`
Đáp án đúng: D

Câu 20. Khi dùng Spring Boot với Flyway, migration thường được chạy lúc nào?
A. Khi JPA repository thực hiện lần ghi đầu tiên
B. Khi khởi tạo ứng dụng, trước khi dùng schema
C. Khi scheduler chạy cron định kỳ cuối ngày
D. Khi REST controller xử lý request đầu tiên
Đáp án đúng: B

Câu 21. Tại sao nên quản lý migration SQL chung với mã nguồn trong Git?
A. Để script luôn có thể chạy lại không giới hạn
B. Để Flyway tự tạo chỉ mục cho mọi truy vấn
C. Để thay đổi schema được review và truy vết
D. Để loại bỏ nhu cầu thử migration trên staging
Đáp án đúng: C

Câu 22. Trong CI, bước nào phát hiện sớm migration lỗi trên DB đích?
A. Chỉ khởi động ứng dụng mà không kết nối database
B. Chỉ kiểm tra cú pháp YAML của pipeline
C. Chạy migrate và validate trên DB thử nghiệm
D. Chỉ kiểm tra phiên bản JDK của build runner
Đáp án đúng: C

Câu 23. Vì sao nên thử migration với cùng loại DB và version gần production?
A. Vì cú pháp DDL và giao dịch có thể khác nhau
B. Vì Flyway chỉ hỗ trợ một loại DB mỗi dự án
C. Vì tên migration luôn khác theo mỗi môi trường
D. Vì checksum phụ thuộc vào phần cứng server
Đáp án đúng: A

Câu 24. Phương án nào giúp bổ sung trường mới mà vẫn hỗ trợ app phiên bản cũ?
A. Buộc mọi phiên bản app nâng cấp trong một giao dịch
B. Đổi tên cột cũ ngay khi deploy ứng dụng mới
C. Thêm cột nullable hoặc giá trị mặc định phù hợp
D. Xóa cột cũ trước khi code mới được triển khai
Đáp án đúng: C

Câu 25. Khi muốn bỏ cột mà ứng dụng cũ còn đọc, nên triển khai thế nào?
A. Xóa cột trước rồi cập nhật từng instance ứng dụng
B. Tắt validate để tránh lỗi ở ứng dụng phiên bản cũ
C. Ngừng dùng cột ở app trước rồi mới xóa schema
D. Chuyển cột thành repeatable để app cũ vẫn truy cập
Đáp án đúng: C

Câu 26. Chiến lược expand–migrate–contract hữu ích vì lý do nào?
A. Buộc toàn bộ ứng dụng đổi schema trong một thời điểm
B. Thay thế nhu cầu sao lưu trước khi thay đổi dữ liệu
C. Bỏ qua mọi quy tắc tương thích giữa các version
D. Cho phép chuyển dữ liệu qua nhiều đợt triển khai
Đáp án đúng: D

Câu 27. Trong migration cập nhật hàng triệu dòng, cách nào thường giảm rủi ro vận hành?
A. Chạy một câu UPDATE lớn trong giờ cao điểm
B. Chia backfill thành batch nhỏ có thể theo dõi
C. Khóa toàn bộ bảng đến khi mọi bản ghi xong
D. Tắt log truy vấn trong suốt thời gian cập nhật
Đáp án đúng: B

Câu 28. Trước khi chạy ALTER TABLE có thể khóa bảng, cần đánh giá điều gì?
A. Thời gian khóa và ảnh hưởng đến giao dịch thật
B. Thứ tự tên file SQL trong thư mục migration
C. Checksum của file migration trước khi chạy
D. Cấu hình baselineVersion đang áp dụng cho DB
Đáp án đúng: A

Câu 29. Với cơ sở dữ liệu hỗ trợ transactional DDL, lỗi migration thường được xử lý thế nào?
A. Transaction có thể rollback phần DDL chưa commit
B. Flyway luôn chạy một câu undo SQL ngay sau lỗi
C. Những migration cũ đều tự xóa khỏi schema history
D. Mọi bảng đều được backup tự động khi script lỗi
Đáp án đúng: A

Câu 30. Trên DB có DDL không rollback được, khi migration lỗi nên làm gì?
A. Xóa schema history để bỏ qua việc đối chiếu
B. Kiểm tra thay đổi còn sót trước khi chạy lại
C. Đổi file cũ sang repeatable rồi tiếp tục deploy
D. Gọi migrate liên tục mà không kiểm tra schema
Đáp án đúng: B

Câu 31. Tại sao không nên sửa tùy tiện migration đã chạy trên production?
A. Chỉ số phiên bản sẽ tự đổi về version thấp hơn
B. Database sẽ tự xóa các bản ghi vừa cập nhật
C. Flyway sẽ tự thêm khóa chính vào mọi bảng
D. Checksum lệch làm validate phát hiện bất nhất
Đáp án đúng: D

Câu 32. Khi cần thay đổi một view theo thời gian, nên cân nhắc loại migration nào?
A. Baseline migration dùng để ghi lại mọi view mới
B. Repair migration tự viết lại định nghĩa của view
C. Versioned migration luôn chạy lại mỗi lần deploy
D. Repeatable migration cho định nghĩa view cập nhật
Đáp án đúng: D

Câu 33. Flyway thường chạy repeatable migration tại thời điểm nào trong `migrate`?
A. Trước khi baseline được ghi cho một schema trống
B. Sau các versioned migration còn chờ của lần chạy
C. Trước toàn bộ versioned migration chưa được chạy
D. Ngay khi ứng dụng thực hiện query vào view bất kỳ
Đáp án đúng: B

Câu 34. Tùy chọn `outOfOrder` liên quan đến trường hợp nào?
A. Chạy migration version thấp xuất hiện muộn
B. Chạy nhiều migration cùng version trên một DB
C. Chạy mọi repeatable trước versioned theo tên
D. Chạy migration không có phiên bản từ file Java
Đáp án đúng: A

Câu 35. Khi bật `outOfOrder`, việc gì vẫn cần được đánh giá?
A. Tác động của migration đến schema đã nâng cấp
B. Số lần một repeatable migration chạy trong một ngày
C. Số bảng có tên dài hơn giới hạn của file system
D. Độ trễ mạng giữa IDE và hệ thống quản lý mã nguồn
Đáp án đúng: A

Câu 36. Cách nào phù hợp khi nhiều instance có thể khởi động cùng lúc?
A. Tạo một version trùng nhau cho mỗi instance chạy
B. Cho từng instance tạo riêng bảng schema history
C. Tắt validate ở mọi instance để khởi động nhanh
D. Điều phối migrate và giám sát khóa lịch sử schema
Đáp án đúng: D

Câu 37. Tác dụng của snapshot hoặc backup đã thử restore là gì?
A. Đảm bảo migration không bao giờ giữ khóa dài
B. Đảm bảo checksum không thay đổi giữa các môi trường
C. Có đường phục hồi khi thay đổi dữ liệu gây sự cố
D. Loại bỏ việc phải kiểm thử migration trước deploy
Đáp án đúng: C

Câu 38. Tại sao lệnh `clean` cần được kiểm soát chặt trên môi trường thật?
A. Vì buộc tất cả migration phải tăng version sau chạy
B. Vì có thể xóa các đối tượng trong schema quản lý
C. Vì thay đổi mọi migration versioned thành repeatable
D. Vì đặt lại mật khẩu của mọi tài khoản database
Đáp án đúng: B

Câu 39. Sau deploy migration, tín hiệu nào nên được theo dõi đầu tiên?
A. Số lượng commit trong Git của các thành viên
B. Số lượng file Java trong module kết nối database
C. Số lượng API mới được mô tả ở tài liệu thiết kế
D. Lỗi ứng dụng, latency và trạng thái migration
Đáp án đúng: D

Câu 40. Khi cần sửa dữ liệu đã migration sai trên production, hướng xử lý nào hợp lý?
A. Tạo migration bù hoặc khôi phục theo kế hoạch
B. Sửa file version cũ rồi bắt ứng dụng chạy lại
C. Xóa history để hệ thống tự tái tạo toàn bộ dữ liệu
D. Bật outOfOrder để hoàn tác mọi thay đổi đã làm
Đáp án đúng: A
