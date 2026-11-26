Câu 01. Lợi ích cốt lõi của migration có phiên bản so với sửa schema thủ công là gì?
A. Thay đổi được lưu trong nhật ký ứng dụng và áp dụng khi đọc.
B. Thay đổi được gộp vào backup và áp dụng khi cần phục hồi.
C. Thay đổi được khai báo ở client và áp dụng mỗi khi đăng nhập.
D. Theo dõi thay đổi schema bằng các phiên bản trong mã nguồn.
Đáp án đúng: D

Câu 02. Vì sao lưu migration cùng repository của ứng dụng thường hữu ích?
A. Giúp tự đồng bộ cấu trúc DB mà không cần chạy công cụ deploy.
B. Giúp thay lệnh kiểm thử SQL bằng lịch sử commit của Git.
C. Giúp đối chiếu thay đổi schema với phiên bản mã ứng dụng.
D. Giúp buộc mọi thay đổi dữ liệu phải chạy trong một transaction.
Đáp án đúng: C

Câu 03. Bảng lịch sử migration của một công cụ thường phục vụ mục đích nào?
A. Ghi nhận mọi truy vấn SELECT thực hiện trong phiên ứng dụng.
B. Ghi nhận tất cả khóa đang giữ bởi các transaction đang chạy.
C. Ghi nhận toàn bộ nội dung từng hàng bị chỉnh sửa khi deploy.
D. Ghi nhận phiên bản hoặc changeset đã được áp dụng trong DB.
Đáp án đúng: D

Câu 04. Vì sao không nên sửa nội dung migration đã được áp dụng ở production?
A. File sửa khiến DB tự rollback các bảng đã tạo từ lần deploy trước.
B. File sửa có thể lệch checksum và làm môi trường khác khó đối chiếu.
C. File sửa khiến ứng dụng mất mọi kết nối đến database đang vận hành.
D. File sửa buộc mọi record cũ nhận giá trị mới ở lần truy vấn tiếp.
Đáp án đúng: B

Câu 05. Khi phát hiện thay đổi checksum của migration đã chạy, bước nào phù hợp?
A. Kiểm tra nguyên nhân khác biệt trước khi quyết định cách xử lý.
B. Xóa bảng lịch sử rồi để công cụ nhận toàn bộ script như mới.
C. Tự bỏ qua checksum nếu phiên bản ứng dụng hiện tại đã chạy được.
D. Chạy lại mọi migration từ đầu ngay trên database production.
Đáp án đúng: A

Câu 06. Khi đưa Flyway vào database đã có schema nhưng chưa có lịch sử, baseline dùng để làm gì?
A. Tự tìm mọi khác biệt schema và viết script chuyển đổi.
B. Hoàn tác các script đã chạy thủ công trước khi có Flyway.
C. Đánh dấu điểm xuất phát để quản lý các migration tiếp theo.
D. Tạo bản sao toàn bộ dữ liệu trước khi chạy migration mới.
Đáp án đúng: C

Câu 07. Schema drift giữa staging và production thường biểu hiện như thế nào?
A. Cùng script tạo bảng được kiểm tra lại trên hai môi trường.
B. Cùng phiên bản SQL được lưu nhất quán trong repository Git.
C. Cùng danh sách quyền tối thiểu được cấp cho ứng dụng.
D. Schema giữa các môi trường có thể lệch dù cùng phiên bản.
Đáp án đúng: D

Câu 08. Khi hai nhánh cùng tạo migration version trùng nhau, nên làm gì?
A. Đối chiếu thứ tự triển khai và giải quyết xung đột phiên bản.
B. Xóa lịch sử migration tại staging để hai file tự hợp nhất.
C. Giữ cả hai file cùng version để công cụ tự chọn script mới.
D. Sửa bất kỳ file đã chạy trước đó để ghép cả hai thay đổi.
Đáp án đúng: A

Câu 09. Vì sao cần phân biệt thứ tự migration và thứ tự deploy ứng dụng?
A. Phiên bản ứng dụng có thể yêu cầu schema đã mở rộng từ trước.
B. Mỗi migration phải phụ thuộc vào thời điểm build frontend mới.
C. Thứ tự migration chỉ có ý nghĩa khi server DB bị dừng hoàn toàn.
D. Schema luôn bắt buộc đổi sau khi toàn bộ ứng dụng đã nâng cấp.
Đáp án đúng: A

Câu 10. Đặc điểm nào giúp một data migration chạy lại an toàn sau gián đoạn?
A. Tăng giá trị mọi hàng theo số lần chạy để giữ tiến độ đã làm.
B. Luôn cập nhật toàn bảng không lọc để nhất quán giữa các lần.
C. Chỉ ghi log số hàng thay đổi và không kiểm tra bản ghi đầu vào.
D. Chỉ xử lý bản ghi còn thiếu và tránh biến đổi lặp dữ liệu.
Đáp án đúng: D

Câu 11. Trong chiến lược expand–migrate–contract, bước expand thường là gì?
A. Khóa toàn bộ luồng ghi cho tới khi hợp nhất dữ liệu xong.
B. Thêm cấu trúc mới tương thích trước khi bỏ cấu trúc cũ.
C. Xóa cấu trúc cũ ngay để bắt ứng dụng nâng cấp đồng thời.
D. Đổi tên mọi bảng đang dùng trước khi thêm cấu trúc mới.
Đáp án đúng: B

Câu 12. Khi thêm một cột mới vào bảng lớn đang phục vụ traffic, cách nào thường ít rủi ro?
A. Đổi toàn bộ bảng sang tên khác rồi buộc request chuyển hướng.
B. Thêm cột nullable rồi điền dữ liệu và siết ràng buộc sau.
C. Xóa bảng cũ rồi tạo bảng mới với cột cần bổ sung.
D. Thêm cột NOT NULL chưa có dữ liệu và bắt mọi hàng điền ngay.
Đáp án đúng: B

Câu 13. Trước khi đặt NOT NULL cho cột đã tồn tại, cần xác minh điều gì?
A. Không còn hàng có giá trị NULL và đường ghi mới đã phù hợp.
B. Mọi chỉ mục của bảng đã được xóa trước khi áp ràng buộc.
C. Mọi transaction của ứng dụng phải dùng isolation cao nhất.
D. Cột đó đã được đổi thành khóa chính trong mọi bảng liên quan.
Đáp án đúng: A

Câu 14. Khi cần đổi tên cột nhưng có hai phiên bản ứng dụng cùng chạy, cách nào phù hợp?
A. Tạo view mới rồi xóa cột cũ dù bản ứng dụng cũ còn dùng.
B. Đổi tên cột ngay rồi yêu cầu mọi phiên bản cũ tự đọc tên mới.
C. Duy trì truy cập cũ và mới rồi lần lượt chuyển ứng dụng.
D. Chỉ sửa câu SQL trong code mới, giữ schema không thay đổi.
Đáp án đúng: C

Câu 15. Thời điểm phù hợp để loại bỏ cột cũ trong quá trình contract là khi nào?
A. Không còn phiên bản ứng dụng hoặc job phụ thuộc vào cột đó.
B. Ngay khi migration thêm cột mới đã được commit thành công.
C. Ngay sau khi bảng được rebuild xong ở môi trường staging.
D. Ngay sau khi một pod mới khởi động thành công trên production.
Đáp án đúng: A

Câu 16. Mục tiêu của backward-compatible migration khi triển khai cuốn chiếu là gì?
A. Để mọi phiên bản ứng dụng dùng chung đúng một file nhị phân.
B. Để tránh hoàn toàn nhu cầu kiểm thử schema trên staging.
C. Đảm bảo bản ứng dụng cũ và mới cùng chạy khi chuyển tiếp.
D. Để tự động phục hồi dữ liệu đã xóa nếu phiên bản mới lỗi.
Đáp án đúng: C

Câu 17. Vì sao rollback riêng mã ứng dụng có thể không đủ sau migration?
A. Rollback ứng dụng đồng nghĩa DB phải kết thúc mọi giao dịch mở.
B. Schema mới có thể đã xóa cấu trúc mà mã cũ còn phụ thuộc.
C. Schema mới luôn tự phục hồi về bản cũ mỗi khi deploy thất bại.
D. Mã cũ luôn tương thích với mọi lần thay đổi tên cột hoặc bảng.
Đáp án đúng: B

Câu 18. Khi backfill hàng triệu bản ghi, vì sao nên chia thành nhiều batch?
A. Giới hạn thời gian giữ khóa, giao dịch và áp lực log.
B. Đảm bảo các batch luôn hoàn thành trong một transaction duy nhất.
C. Tránh việc phải ghi nhận trạng thái và số hàng đã xử lý.
D. Buộc mỗi batch tạo lại toàn bộ chỉ mục của bảng nguồn.
Đáp án đúng: A

Câu 19. Cơ chế resume nào thích hợp cho backfill có thể bị dừng giữa chừng?
A. Xóa dữ liệu đã chuyển rồi chạy lại toàn bộ bảng từ đầu.
B. Bỏ qua các batch có lỗi mà không lưu trạng thái lỗi.
C. Tăng giá trị cột chuyển đổi sau mỗi lần chạy lại batch.
D. Lưu checkpoint và cập nhật có điều kiện để chạy tiếp.
Đáp án đúng: D

Câu 20. Trong giai đoạn chuyển tiếp, khi ứng dụng vẫn ghi vào cột cũ, vấn đề nào cần giải quyết?
A. Chạy rollback dữ liệu sau mỗi yêu cầu ghi đến cột cũ.
B. Chỉ chuyển dữ liệu cũ một lượt rồi bỏ qua mọi bản ghi mới.
C. Giữ dữ liệu mới đồng bộ trong suốt quá trình backfill.
D. Giữ schema mới chỉ đọc cho đến khi xóa hẳn bảng cũ.
Đáp án đúng: C

Câu 21. Nếu thực hiện dual-write trong ứng dụng, nguy cơ quan trọng nào cần theo dõi?
A. Mỗi yêu cầu ghi sẽ tự động giảm độ trễ cho truy vấn đọc.
B. Mỗi lệnh ghi sẽ thay thế nhu cầu kiểm tra dữ liệu sau backfill.
C. Hai nơi lưu luôn đồng bộ nguyên tử dù giao dịch khác database.
D. Hai nơi lưu có thể lệch khi một ghi thành công còn ghi kia lỗi.
Đáp án đúng: D

Câu 22. Khi chuyển cột từ text sang kiểu số, cần kiểm tra trước điều gì?
A. Mọi cột khác trong bảng đều có thể chuyển sang số cùng lúc.
B. Kiểu cột mới tự sửa các giá trị sai mà không cần quy tắc.
C. Dữ liệu hiện có có parse được và quy tắc xử lý giá trị lỗi.
D. Mọi truy vấn đọc sẽ bỏ qua các hàng chưa chuyển được kiểu.
Đáp án đúng: C

Câu 23. Trước khi tạo UNIQUE constraint trên dữ liệu đã có, cần làm gì?
A. Chuyển tất cả khóa về NULL rồi tạo ràng buộc mặc định.
B. Phát hiện và xử lý khóa trùng theo quy tắc nghiệp vụ.
C. Chỉ tăng thời gian chờ khóa để câu lệnh luôn thành công.
D. Chỉ chạy migration nhiều lần để các hàng trùng tự mất.
Đáp án đúng: B

Câu 24. Khi tạo index trên bảng lớn đang ghi liên tục, điều gì cần tìm hiểu?
A. Tăng số session ghi để bỏ qua khóa của thao tác CREATE INDEX.
B. Giữ một transaction lớn để index nhất quán khi được tạo.
C. DB hỗ trợ cách xây dựng index giảm chặn ghi hay không.
D. Tăng timeout phía ứng dụng để tránh bị chặn khi DDL chạy.
Đáp án đúng: C

Câu 25. Vì sao thay đổi DDL có thể gây gián đoạn dù câu SQL rất ngắn?
A. DDL có thể cần khóa metadata và phải chờ giao dịch khác.
B. DDL luôn được chạy trên snapshot không giữ bất kỳ loại khóa.
C. DDL luôn bỏ qua transaction mở nên hoàn thành tức thì.
D. DDL tự tăng tốc mọi truy vấn đang giữ khóa trên bảng.
Đáp án đúng: A

Câu 26. Khi lập phương án rollback DDL, yếu tố nào phải xác minh theo hệ DB cụ thể?
A. DDL có hỗ trợ transaction và rollback tại thời điểm áp dụng.
B. Mọi DDL đều rollback được miễn công cụ lưu đủ checksum.
C. Mọi DDL đã commit có thể đảo ngược bằng một câu ALTER TABLE.
D. Rollback mã ứng dụng đủ để DB tự trả về schema cũ.
Đáp án đúng: A

Câu 27. Khi một migration vừa đổi schema vừa xử lý khối lượng dữ liệu lớn, cách tổ chức nào thường tốt hơn?
A. Giữ khóa bảng cho cả quá trình để application không đọc sai.
B. Tách thay đổi schema ngắn khỏi backfill dài có tiến độ riêng.
C. Xóa lịch sử migration trước khi chạy phần cập nhật dữ liệu.
D. Gộp mọi bước vào một giao dịch dài để dễ theo dõi bản ghi.
Đáp án đúng: B

Câu 28. Vai trò của timeout khi chạy migration tại production là gì?
A. Giới hạn thời gian chờ để phát hiện bước có nguy cơ nghẽn.
B. Đảm bảo schema có thể rollback sau mọi câu DDL đã commit.
C. Buộc DB dừng mọi transaction khác ngay khi migration bắt đầu.
D. Đảm bảo mọi lệnh index creation sẽ chạy nhanh hơn bình thường.
Đáp án đúng: A

Câu 29. Với migration phá hủy dữ liệu đã commit, rollback đáng tin cậy cần dựa vào gì?
A. Chỉ sửa checksum để công cụ chạy ngược những lệnh đã ghi.
B. Cần bản sao dữ liệu có thể khôi phục và đã thử restore.
C. Chỉ một lệnh ALTER TABLE đảo ngược tên cột vừa bị xóa.
D. Chỉ rollback ứng dụng để DB tự tái tạo các hàng đã mất.
Đáp án đúng: B

Câu 30. Vì sao backup cần được kiểm thử restore trước thay đổi lớn?
A. Việc restore luôn nhanh hơn thời gian tạo bản sao của database.
B. File backup tồn tại chưa chứng minh có thể phục hồi đúng hạn.
C. Backup thay thế được mọi bước kiểm thử compatibility của code.
D. Backup hợp lệ sẽ tự phát hiện mọi lỗi logic trong migration.
Đáp án đúng: B

Câu 31. Với Flyway, migration có phiên bản thường được đặt tên theo mẫu nào?
A. R<version>__<description>.sql, ví dụ R3__add_status.sql.
B. V<version>_<description>.sql, ví dụ V3_add_status.sql.
C. U<version>__<description>.sql, ví dụ U3__add_status.sql.
D. V<version>__<description>.sql, ví dụ V3__add_status.sql.
Đáp án đúng: D

Câu 32. Khi nào Flyway repeatable migration thường được thực thi lại?
A. Khi một bản ghi trong bảng lịch sử migration được truy vấn.
B. Khi mỗi request ứng dụng khởi tạo một kết nối database mới.
C. Khi số hàng của bất kỳ bảng nào trong database thay đổi.
D. Khi nội dung migration đổi và checksum không còn khớp.
Đáp án đúng: D

Câu 33. Lệnh Flyway repair phù hợp với mục đích nào?
A. Tự tái tạo những hàng dữ liệu đã xóa bởi migration cũ.
B. Tự chạy lại mọi migration đã áp dụng ở production.
C. Chỉnh metadata lịch sử sau khi sự cố đã được xử lý.
D. Tự hoàn tác mọi câu DDL đã commit của migration vừa lỗi.
Đáp án đúng: C

Câu 34. Liquibase phân biệt các changeset thông thường dựa vào gì?
A. Chỉ checksum SQL của thay đổi, không xét tác giả hay đường dẫn.
B. Chỉ id của changeset, không cần tên author hay đường dẫn.
C. Dựa trên id, author và vị trí changelog tương ứng.
D. Chỉ tag phiên bản release và tên schema được thay đổi.
Đáp án đúng: C

Câu 35. Một changelog Liquibase chủ yếu mô tả điều gì?
A. Tập SQL được công cụ suy diễn tự động từ schema hiện tại.
B. Bảng ghi lại các lần chạy SQL để đối chiếu lịch sử deploy.
C. Danh sách toàn bộ đối tượng DB sẽ được backup định kỳ.
D. Chuỗi changeset nhằm chuyển schema và dữ liệu có kiểm soát.
Đáp án đúng: D

Câu 36. Rollback trong Liquibase cần được đánh giá thế nào?
A. Kiểm tra hỗ trợ của từng change type hoặc khai báo rollback.
B. Rollback chỉ tác động source code mà không thay database thực.
C. Mọi câu SQL tự động có lệnh nghịch đảo tương ứng do Liquibase.
D. Mọi changeset đều có thể đảo ngược cả dữ liệu không cần backup.
Đáp án đúng: A

Câu 37. Trong Liquibase, precondition được dùng để làm gì?
A. Tự đánh dấu mọi changeset hoàn tất ngay khi mở changelog.
B. Xác định checksum mới trước khi DB áp dụng các changeset.
C. Bắt changeset chạy lại nếu schema khác trạng thái yêu cầu.
D. Kiểm tra trạng thái DB trước khi thực hiện thay đổi liên quan.
Đáp án đúng: D

Câu 38. Khi cấu hình Liquibase contexts hoặc labels, mục đích chính là gì?
A. Tự thực thi lại changeset khi tag release được thay đổi.
B. Chọn changeset theo môi trường và điều kiện triển khai.
C. Tự đảo ngược changeset khi context hiện tại không còn khớp.
D. Tự sắp xếp changeset theo mức ưu tiên của môi trường.
Đáp án đúng: B

Câu 39. Kiểm thử migration trong CI nên bao gồm bước nào?
A. Chỉ xác nhận mã Java biên dịch khi không kết nối database.
B. Tạo schema từ đầu và nâng cấp từ phiên bản cũ bằng migration.
C. Chỉ đo độ trễ trang web mà bỏ qua schema và dữ liệu.
D. Chỉ kiểm tra cú pháp JSON của file cấu hình ứng dụng.
Đáp án đúng: B

Câu 40. Khi triển khai migration trong CI/CD, điều kiện nào giúp giảm rủi ro?
A. Để mọi replica ứng dụng cùng tự đổi schema trong một thời điểm.
B. Chạy migration mới trực tiếp trên production không cần thử trước.
C. Đảm bảo một tiến trình áp dụng, kiểm tra kết quả và theo dõi lỗi.
D. Tiếp tục deploy mã mới dù migration chưa hoàn thành thành công.
Đáp án đúng: C
