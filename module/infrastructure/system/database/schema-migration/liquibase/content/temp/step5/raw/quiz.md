Câu 1. Trong Liquibase, changelog có vai trò chính nào?
A. Lưu toàn bộ bản sao dữ liệu ở từng lần chạy migration.
B. Lưu danh sách kết nối JDBC đang hoạt động trên server.
C. Ghi thứ tự thay đổi schema và dữ liệu để triển khai.
D. Thay thế mọi transaction cho các thay đổi SQL đã chạy.
Đáp án đúng: C

Câu 2. Một changeset trong Liquibase thường được định danh duy nhất bằng tổ hợp nào?
A. `id`, `context` và checksum SQL sau khi chạy.
B. `id`, `author` và đường dẫn changelog chứa nó.
C. `author`, `label` và timestamp của lần thực thi.
D. `filename`, `dbms` và tên tài khoản chạy update.
Đáp án đúng: B

Câu 3. Nếu một changeset đã được thực thi thành công và không có cờ đặc biệt, lần `update` sau sẽ làm gì?
A. Chạy lại changeset nếu database đã có dữ liệu mới.
B. Chạy lại changeset mỗi khi ứng dụng được khởi động.
C. Bỏ qua changeset đã được ghi trong lịch sử triển khai.
D. Rollback changeset rồi chạy lại để kiểm tra checksum.
Đáp án đúng: C

Câu 4. Bảng `DATABASECHANGELOG` của Liquibase chủ yếu lưu thông tin nào?
A. Nội dung snapshot toàn bộ bảng trước mỗi lần migration.
B. Lưu changeset đã chạy cùng checksum và metadata.
C. Trạng thái các connection JDBC của migration đang mở.
D. Lịch của mọi job CI/CD được cấu hình ngoài database.
Đáp án đúng: B

Câu 5. Vai trò chính của bảng `DATABASECHANGELOGLOCK` là gì?
A. Khóa migration để tránh hai tiến trình chạy đồng thời.
B. Lưu từng câu SQL trước khi thay đổi được thực thi.
C. Thay thế cơ chế khóa bản ghi của database giao dịch.
D. Ghi lịch sử checksum của mọi lần chỉnh sửa changeset.
Đáp án đúng: A

Câu 6. Nếu hai instance cùng chạy Liquibase `update` trên một database, điều gì giúp giảm xung đột?
A. Mỗi instance chọn ngẫu nhiên một changeset để cập nhật.
B. Lock khiến một tiến trình đợi khi tiến trình kia chạy.
C. Hai instance tự chia đôi tập changeset rồi cùng commit.
D. Mỗi instance chỉ kiểm tra checksum rồi bỏ qua locking.
Đáp án đúng: B

Câu 7. Điều gì thường xảy ra khi nội dung changeset đã chạy bị sửa và checksum không còn khớp?
A. Liquibase luôn âm thầm chạy lại phần mới được chỉnh sửa.
B. Liquibase có thể báo lỗi xác thực checksum khi chạy.
C. Liquibase tự xóa lịch sử changeset cũ khỏi database.
D. Liquibase luôn rollback thành công mọi DDL trước đó.
Đáp án đúng: B

Câu 8. `clearCheckSums` trong Liquibase có tác dụng chủ yếu nào?
A. Chạy lại toàn bộ SQL của changeset đã được ghi nhận.
B. Xóa mọi dòng lịch sử trong bảng `DATABASECHANGELOG`.
C. Xóa checksum lưu để lần sau tính lại khi cập nhật.
D. Hủy mọi khóa còn tồn tại trên các bảng của ứng dụng.
Đáp án đúng: C

Câu 9. `runOnChange` phù hợp với loại changeset nào?
A. Changeset cần chạy lại nếu nội dung hợp lệ được sửa đổi.
B. Changeset cần chạy lại ở mọi lần update dù không đổi.
C. Changeset chỉ chạy trong lần khởi tạo database đầu tiên.
D. Changeset bắt buộc chạy ở mỗi môi trường một lần duy nhất.
Đáp án đúng: A

Câu 10. Khác biệt cốt lõi của `runAlways` so với changeset thường là gì?
A. Chỉ chạy khi checksum khác checksum đã lưu trong lịch sử.
B. Chạy mỗi lần `update`, kể cả khi nội dung không đổi.
C. Chỉ chạy nếu database vừa được tạo ở lần đầu tiên.
D. Được chạy một lần cho mỗi connection JDBC được khởi tạo.
Đáp án đúng: B

Câu 11. Khi một changeset đã triển khai và cần chỉnh logic mới, cách tổ chức lịch sử nào an toàn hơn?
A. Sửa changeset cũ và xoá checksum ở mọi môi trường.
B. Đổi id changeset cũ mà không ghi lại lịch sử triển khai.
C. Thêm changeset mới thay vì sửa trực tiếp changeset cũ.
D. Xóa bảng `DATABASECHANGELOG` trước lần chạy tiếp theo.
Đáp án đúng: C

Câu 12. Liquibase hỗ trợ định dạng changelog nào trong các lựa chọn sau?
A. Chỉ XML; mọi định dạng khác cần viết plugin riêng.
B. Changelog có thể dùng XML, YAML, JSON và SQL.
C. Chỉ JSON và SQL thuần không có chú thích changeset.
D. Chỉ YAML và các tệp SQL không thể chứa rollback.
Đáp án đúng: B

Câu 13. Thẻ `include` trong changelog giúp thực hiện việc nào?
A. Tham chiếu mọi file trong folder mà không cần đường dẫn.
B. Tham chiếu một changelog con vào chuỗi thay đổi chung.
C. Tự tạo một checksum chung cho mọi changeset con.
D. Gộp mọi changeset thành duy nhất một giao dịch trên DB.
Đáp án đúng: B

Câu 14. Khi dùng `includeAll` với một thư mục changelog, cần lưu ý điều gì?
A. Chỉ file mới nhất theo timestamp mới được đưa vào chạy.
B. Tất cả changeset trong folder đều được chạy song song.
C. Các file được đưa vào theo thứ tự sắp xếp tên file.
D. Mọi file được đổi id changeset theo tên bảng sẽ tạo.
Đáp án đúng: C

Câu 15. Tùy chọn `relativeToChangelogFile` giúp xác định đường dẫn `include` như thế nào?
A. Giải đường dẫn dựa trên thư mục hiện hành của máy chạy.
B. Giải đường dẫn dựa trên schema mặc định của database.
C. Giải đường dẫn dựa trên thư mục cài đặt Java Runtime.
D. Giải đường dẫn theo vị trí file changelog chứa khai báo.
Đáp án đúng: D

Câu 16. Trong formatted SQL changelog, dòng nào thường mở đầu một changeset?
A. `--rollback author:id` để khai báo danh tính thay đổi.
B. `--include context:id` để khai báo danh tính thay đổi.
C. `--validate label:id` để khai báo danh tính thay đổi.
D. `--changeset author:id` khai báo định danh của thay đổi.
Đáp án đúng: D

Câu 17. Precondition trong Liquibase giúp kiểm tra điều gì trước một changeset?
A. Điều kiện về trạng thái database trước khi thực thi.
B. Khả năng khôi phục dữ liệu sau khi transaction đã commit.
C. Số tiến trình CI/CD được chạy đồng thời trong pipeline.
D. Khả năng tăng cỡ connection pool của JDBC khi quá tải.
Đáp án đúng: A

Câu 18. Với precondition `onFail="HALT"`, điều gì xảy ra nếu điều kiện không đạt?
A. Changeset được đánh dấu đã chạy dù chưa thực hiện SQL.
B. Changeset bị bỏ qua và sẽ được thử ở lần update tới.
C. Liquibase tự tạo đối tượng còn thiếu rồi tiếp tục chạy.
D. Báo lỗi và dừng update nếu điều kiện không thỏa.
Đáp án đúng: D

Câu 19. Với precondition thất bại và `onFail="MARK_RAN"`, kết quả thường là gì?
A. Dừng update, giữ changeset chưa chạy để thử lại sau.
B. Chạy changeset rồi đánh dấu lỗi sau khi commit SQL.
C. Đánh dấu đã chạy và bỏ qua các thay đổi của changeset.
D. Rollback changeset khác và bắt đầu thử lại precondition.
Đáp án đúng: C

Câu 20. Với precondition thất bại và `onFail="CONTINUE"`, hành vi chính là gì?
A. Đánh dấu changeset đã chạy dù không thực hiện thay đổi.
B. Dừng ngay toàn bộ changelog và không cho chạy lần sau.
C. Bỏ qua precondition rồi thực hiện changeset như bình thường.
D. Bỏ qua changeset lúc này, có thể thử lại lần cập nhật sau.
Đáp án đúng: D

Câu 21. Khi dùng `context` trong Liquibase, mục tiêu phổ biến là gì?
A. Xác định database vendor duy nhất cho mỗi câu truy vấn.
B. Đặt transaction isolation cho mọi kết nối của ứng dụng.
C. Quy định thứ tự chạy mọi câu SELECT trong changeset.
D. Lọc changeset theo môi trường hoặc nhóm triển khai.
Đáp án đúng: D

Câu 22. `labels` trong changeset thường hữu ích cho mục tiêu nào?
A. Đánh số tự tăng cho changeset đã chạy theo thứ tự.
B. Gán giá trị khóa chính cho bảng mới khi khởi tạo.
C. Chọn tập thay đổi theo biểu thức label lúc triển khai.
D. Đặt giới hạn bộ nhớ sử dụng cho câu SQL trong changelog.
Đáp án đúng: C

Câu 23. Precondition `sqlCheck` thích hợp khi nào?
A. Dùng kết quả SQL kiểm tra trước khi thực thi thay đổi.
B. Cần tự động phát sinh SQL rollback cho mọi changeset.
C. Cần giới hạn số connection khi chạy script migration.
D. Cần chuyển mọi câu SELECT thành constraint của bảng.
Đáp án đúng: A

Câu 24. Với changeset dùng SQL tùy chỉnh không thể tự đảo, việc chuẩn bị rollback nên làm gì?
A. Tự viết lệnh rollback và kiểm thử trên môi trường staging.
B. Dùng `clearCheckSums` thay cho script rollback hoàn chỉnh.
C. Chỉ chạy lại câu SQL với thứ tự ngược của các dòng.
D. Đặt `runAlways` để tự hoàn tác mọi câu lệnh đã chạy.
Đáp án đúng: A

Câu 25. Nếu migration `DROP COLUMN` xóa cả dữ liệu cột, rủi ro rollback chính là gì?
A. Việc tạo lại cột luôn phục hồi nguyên dữ liệu ban đầu.
B. Rollback luôn xóa mọi bảng liên quan trước khi tạo cột.
C. Liquibase không hỗ trợ khai báo rollback cho thay đổi này.
D. Việc tạo lại cột không tự phục hồi được giá trị đã mất.
Đáp án đúng: D

Câu 26. Lệnh rollback theo tag của Liquibase thường nhằm mục đích nào?
A. Đảo các changeset đã chạy sau mốc tag được chọn.
B. Đánh dấu mọi changeset chưa chạy là đã triển khai.
C. Chạy lại tất cả changeset được gắn label của tag.
D. Chuyển toàn bộ changelog sang database dự phòng.
Đáp án đúng: A

Câu 27. Lệnh `update-sql` hữu ích trong quy trình review vì sao?
A. Chạy SQL trên database rồi đảo bằng transaction tự động.
B. Xóa checksum đã lưu để xác thực nội dung từng changeset.
C. Đánh dấu mọi changeset là đã chạy, không thực thi SQL.
D. Hiển thị SQL dự kiến mà không áp dụng migration lên DB.
Đáp án đúng: D

Câu 28. Lệnh `rollback-sql` có công dụng nào khi chuẩn bị phương án phục hồi?
A. Khôi phục schema ngay và không cần quyền thay đổi dữ liệu.
B. Đánh dấu các changeset là đã chạy mà không thực thi.
C. Đồng bộ snapshot hai database và thêm bảng bị thiếu.
D. Xem trước các lệnh SQL dự kiến cho thao tác rollback.
Đáp án đúng: D

Câu 29. `liquibase validate` thường được dùng để thực hiện việc gì?
A. Kiểm tra cấu trúc và định nghĩa changelog trước update.
B. Chạy đầy đủ các changeset chưa có trong lịch sử database.
C. Đo tải SQL thực tế khi toàn bộ migration được chạy.
D. Khôi phục bảng lịch sử sau khi đã xóa changelog.
Đáp án đúng: A

Câu 30. Lệnh `status` của Liquibase thường giúp trả lời câu hỏi nào?
A. Liệt kê các changeset chưa chạy trên database hiện tại.
B. Những transaction nào đang chờ khóa bảng ứng dụng.
C. Những kết nối JDBC nào đang idle trong pool ứng dụng.
D. Những file backup nào đã được upload vào kho lưu trữ.
Đáp án đúng: A

Câu 31. Khi dùng `generateChangelog` từ database hiện hữu, quy trình an toàn cần bổ sung điều gì?
A. Chạy kết quả trực tiếp trên production mà bỏ qua review.
B. Review changelog sinh ra trước khi đưa vào version control.
C. Xóa toàn bộ lịch sử cũ trước khi generate changelog.
D. Dùng output làm bản sao lưu dữ liệu giao dịch đầy đủ.
Đáp án đúng: B

Câu 32. `changelogSync` phù hợp với nhu cầu nào?
A. Ghi nhận đã chạy mà không thực thi thay đổi schema.
B. Thực thi toàn bộ changeset bất kể lịch sử hiện có.
C. Đảo mọi thay đổi rồi ghi lại checksum của từng lệnh.
D. Xóa toàn bộ lịch sử deploy trước khi cập nhật tiếp.
Đáp án đúng: A

Câu 33. Với migration thêm cột `NOT NULL` vào bảng lớn đang có dữ liệu, bước nào giảm rủi ro?
A. Thêm `NOT NULL` ngay và đợi DB tự sinh mọi giá trị cũ.
B. Xóa các hàng thiếu giá trị mới trước khi thay đổi cột.
C. Thêm cột nullable, backfill, rồi siết ràng buộc sau.
D. Đổi bảng sang chế độ chỉ đọc vĩnh viễn rồi thêm cột.
Đáp án đúng: C

Câu 34. Khi nâng cấp schema cùng lúc có hai phiên bản ứng dụng, chiến lược nào hữu ích?
A. Drop cột cũ trước khi deploy bản mới lên một instance.
B. Đổi tên bảng trực tiếp và yêu cầu mọi client cập nhật tức thì.
C. Expand trước để tương thích, contract sau khi app cũ rời đi.
D. Đóng mọi connection và thay schema không cần kiểm tra.
Đáp án đúng: C

Câu 35. Trong Spring Boot, thuộc tính nào chọn changelog Liquibase cần chạy?
A. `spring.datasource.schema` chỉ đường dẫn changelog.
B. `spring.jpa.hibernate.ddl-auto` chỉ đường dẫn changelog.
C. `spring.liquibase.enabled` chỉ đường dẫn changelog.
D. `spring.liquibase.change-log` chỉ đường dẫn changelog.
Đáp án đúng: D

Câu 36. Trong Spring Boot, thuộc tính nào dùng để bật hoặc tắt Liquibase tự chạy?
A. `spring.liquibase.contexts` điều khiển chạy migration.
B. `spring.datasource.url` điều khiển chạy migration.
C. `spring.liquibase.enabled` điều khiển chạy migration.
D. `spring.jpa.show-sql` điều khiển chạy migration.
Đáp án đúng: C

Câu 37. Để lọc Liquibase changeset theo context khi dùng Spring Boot, thuộc tính nào phù hợp?
A. `spring.liquibase.default-schema` chọn context thực thi.
B. `spring.liquibase.contexts` chọn context khi thực thi.
C. `spring.jpa.properties.contexts` chọn context thực thi.
D. `spring.datasource.hikari.contexts` chọn context thực thi.
Đáp án đúng: B

Câu 38. Vì sao không thể mặc định coi mọi DDL migration là một transaction có thể rollback?
A. Liquibase không thể chạy bất kỳ statement nào trong transaction.
B. Mỗi DB có cơ chế commit và DDL transaction khác nhau.
C. Mọi câu ALTER TABLE đều chỉ hỗ trợ commit theo từng hàng.
D. Mọi database đều tự rollback DDL khi ứng dụng bị đóng.
Đáp án đúng: B

Câu 39. Trong CI/CD, bước nào giúp ngăn migration không hợp lệ đến production?
A. Chạy thẳng production để lấy lỗi thực tế rồi mới test.
B. Xóa `DATABASECHANGELOG` để mọi changeset chạy lại.
C. Thay đổi checksum sau deploy nhằm tránh các bước review.
D. Validate, xem SQL và thử update/rollback trên DB staging.
Đáp án đúng: D

Câu 40. Khi triển khai migration trên nhiều môi trường, cách quản lý nào đáng tin cậy?
A. Version control changelog, cấu hình riêng từng môi trường.
B. Chỉnh changelog đã chạy trực tiếp trên từng server độc lập.
C. Dùng chung một mật khẩu admin cố định cho mọi môi trường.
D. Xóa lịch sử migration khi chuyển từ staging sang production.
Đáp án đúng: A
