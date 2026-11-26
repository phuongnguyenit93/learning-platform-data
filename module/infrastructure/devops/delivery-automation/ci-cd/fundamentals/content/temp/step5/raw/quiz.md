Câu 1: Khi mở pull request vào nhánh chính, hành động CI nào phù hợp để phát hiện lỗi sớm?
A. Triển khai bản thay đổi lên production trước khi merge.
B. Chỉ chạy kiểm thử sau khi thay đổi được gộp nhánh.
C. Chạy build và test cho thay đổi trước khi gộp nhánh.
D. Tạo tag phát hành trước khi chạy pipeline kiểm tra.
Đáp án đúng: C

Câu 2: Lợi ích thực tế của pipeline-as-code được lưu cùng repository là gì?
A. Cấu hình pipeline được version và review cùng mã.
B. Pipeline tự lấy quyền truy cập production từ Git.
C. Thao tác build không cần khai báo môi trường runner.
D. Mỗi lần chạy sẽ tự sửa file pipeline trong nhánh.
Đáp án đúng: A

Câu 3: Trong CI, thao tác nào tăng khả năng tái tạo cùng kết quả build giữa các runner?
A. Khóa phiên bản dependency và toolchain sử dụng khi build.
B. Tải phiên bản mới nhất của mọi dependency mỗi lần build.
C. Sử dụng cache chung và bỏ qua kiểm tra checksum.
D. Biên dịch bằng toolchain có sẵn tùy theo runner.
Đáp án đúng: A

Câu 4: Trong pipeline có ngân sách runner hạn chế, cách nào giúp phản hồi lỗi nhanh hơn?
A. Ưu tiên test đòi môi trường đầy đủ trước các test đơn vị.
B. Ưu tiên test chậm nhất trước để kết thúc toàn bộ sớm.
C. Ưu tiên test end-to-end trước để tiết kiệm lượt chạy.
D. Ưu tiên test nhanh, ít phụ thuộc trước test tích hợp.
Đáp án đúng: D

Câu 5: Cách nào giữ bản production là chính artifact đã vượt qua kiểm thử staging?
A. Build lại cùng commit trên runner của production.
B. Promote đúng artifact theo digest của bản đã test.
C. Build lại mã từ nhánh main và gắn tag của release.
D. Cài lại dependency và đóng gói theo version cũ.
Đáp án đúng: B

Câu 6: Một job test bắt buộc thất bại. Bước deploy phụ thuộc vào job này nên xử lý thế nào?
A. Tiếp tục deploy nếu bước build trước đó thành công.
B. Bỏ qua test và đánh dấu deploy thành công có điều kiện.
C. Chặn deploy cho đến khi test được chạy lại và đạt.
D. Tạo release tag trước rồi báo lỗi ở môi trường đích.
Đáp án đúng: C

Câu 7: Một bài test đôi khi fail trên cùng commit rồi pass khi rerun. Đội CI nên xử lý thế nào?
A. Tắt hẳn test để pipeline ổn định số liệu.
B. Điều tra nguyên nhân flaky, sửa test và theo dõi.
C. Đặt job luôn thành công để không ảnh hưởng deploy.
D. Tăng số lượt rerun và coi pass một lần là đủ.
Đáp án đúng: B

Câu 8: Job triển khai cần truy cập cloud trong vài phút. Cách cấp xác thực nào giảm rủi ro lộ secret?
A. Đưa access key dài hạn vào biến YAML của pipeline.
B. Đưa token vào tên artifact để runner có thể tải.
C. Lưu access key dùng chung trong file cấu hình của repo.
D. Dùng OIDC để đổi lấy credential ngắn hạn theo job.
Đáp án đúng: D

Câu 9: Cổng chất lượng trước release có ngưỡng lỗ hổng nghiêm trọng. Job quét báo vượt ngưỡng thì làm gì?
A. Cho deploy và lên lịch sửa ở chu kỳ kế tiếp.
B. Chỉ đánh dấu warning nhưng vẫn publish artifact.
C. Bỏ kết quả quét nếu build và unit test đã pass.
D. Chặn release và báo kết quả vi phạm chính sách.
Đáp án đúng: D

Câu 10: Để truy vết artifact đang chạy tới mã nguồn và job CI, metadata nào hữu ích nhất?
A. Commit SHA, build run ID và digest artifact đã deploy.
B. Tên người merge, thời gian build và tag `latest`.
C. Tên nhánh, thời gian server khởi động và build log.
D. Tên release, thời gian tải và trạng thái runner.
Đáp án đúng: A

Câu 11: Vì sao production thường yêu cầu approval cho bước promote sau staging?
A. Để thay thế hoàn toàn kết quả kiểm thử của CI.
B. Để bỏ yêu cầu xác thực với môi trường production.
C. Để xác nhận quyền và thời điểm phát hành lên production.
D. Để build lại artifact bằng quyền của người phê duyệt.
Đáp án đúng: C

Câu 12: Một thư viện hỗ trợ hai phiên bản JDK. Cách kiểm thử CI nào giúp xác minh khả năng tương thích?
A. Chạy test trên JDK mặc định rồi phát hành cả hai profile.
B. Build một lần rồi đổi nhãn JDK của artifact đóng gói.
C. Chạy test theo ma trận với từng phiên bản JDK hỗ trợ.
D. Chạy unit test trên môi trường có JDK mới nhất.
Đáp án đúng: C

Câu 13: Khi rollout canary, điều kiện nào nên dẫn tới mở rộng lưu lượng sang phiên bản mới?
A. Image đã được push lên registry và tag hợp lệ.
B. Chỉ số lỗi, độ trễ và sức khỏe canary đạt ngưỡng.
C. Bước deploy ban đầu đã ghi log không có exception.
D. Tất cả pod đã được cấp phát dù request còn lỗi.
Đáp án đúng: B

Câu 14: Sau deploy, cách nào phát hiện lỗi mà smoke test đơn giản có thể bỏ sót?
A. Chỉ xác nhận container đã kéo image thành công.
B. Chỉ kiểm tra job CI kết thúc với mã thoát 0.
C. Chỉ xem deployment tool báo trạng thái thành công.
D. Theo dõi tỷ lệ lỗi, độ trễ và chỉ số nghiệp vụ.
Đáp án đúng: D

Câu 15: Nếu bản vừa deploy gây tăng lỗi, rollback nên dựa vào thông tin nào?
A. Digest của artifact phát hành trước đã được xác minh.
B. Tag `latest` được resolve lại tại thời điểm rollback.
C. Commit trên nhánh main tại thời điểm rollback.
D. Image mới nhất theo thời gian push vào registry.
Đáp án đúng: A

Câu 16: Vì sao thay đổi schema DB không tương thích có thể làm rollback ứng dụng thất bại?
A. Bởi pipeline có thể bỏ qua bước smoke test ở staging.
B. Bởi mã cũ không còn đọc được dữ liệu theo schema mới.
C. Bởi artifact rollback mất chữ ký khi chạy phiên bản cũ.
D. Bởi tag phiên bản cũ có thể trỏ đến digest mới.
Đáp án đúng: B
