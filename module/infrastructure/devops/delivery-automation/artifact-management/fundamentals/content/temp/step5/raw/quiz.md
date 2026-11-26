Câu 1. Sau khi kiểm thử image `registry/app:1.4`, đội triển khai cần chắc chắn staging và production dùng đúng nội dung đã kiểm thử. Nên lưu tham chiếu nào?
A. Tên repository và tag `1.4` đã được gắn lúc build.
B. Tên repository và thời điểm image được đẩy vào registry.
C. Tên repository kèm digest `sha256:...` của image đã kiểm thử.
D. Tên repository kèm số pipeline đã chạy thành công.
Đáp án đúng: C

Câu 2. Một bản JAR được xuất bản vào Maven repository. Bộ thông tin nào định danh tọa độ dependency để build tool truy xuất đúng phiên bản?
A. `groupId`, `artifactId` và `version` đã công bố.
B. `groupId`, `packaging` và checksum của tệp JAR.
C. `artifactId`, tên job và thời điểm build hoàn tất.
D. `version`, tên nhánh và hash commit của dự án.
Đáp án đúng: A

Câu 3. Trong repository đã bật chính sách release bất biến, pipeline cố xuất bản một JAR khác vào cùng `groupId:artifactId:version`. Hành vi nào phù hợp?
A. Ghi đè JAR cũ rồi giữ nguyên số phiên bản release.
B. Thay JAR mới và chỉ cập nhật checksum cho phiên bản.
C. Chấp nhận JAR mới nếu pipeline lần này chạy thành công.
D. Từ chối ghi đè và yêu cầu xuất bản một phiên bản mới.
Đáp án đúng: D

Câu 4. Một hệ CI cần giới hạn quyền ghi vào kho artifact. Khi nào nên cấp quyền publish cho job phát hành release?
A. Sau khi build và kiểm thử đạt, qua job phát hành có quyền riêng.
B. Ngay khi checkout mã nguồn, trước mọi bước kiểm thử.
C. Khi developer push commit, bằng token ghi dùng cho mọi job.
D. Ngay lúc pipeline khởi tạo, dùng chung token trong runner.
Đáp án đúng: A

Câu 5. Hai tệp `app.jar` có cùng tên và version nhưng checksum SHA-256 khác nhau. Kết luận nào được hỗ trợ trực tiếp?
A. Hai tệp chắc chắn được tạo từ hai commit nguồn khác nhau.
B. Nội dung byte của hai tệp không hoàn toàn giống nhau.
C. Một tệp chắc chắn đã bị chỉnh sửa sau khi ký số.
D. Một tệp chắc chắn có lỗ hổng phụ thuộc nghiêm trọng.
Đáp án đúng: B

Câu 6. Registry cung cấp checksum và chữ ký cho artifact. Xác thực chữ ký bổ sung điều gì so với chỉ đối chiếu checksum?
A. Xác định artifact dùng phiên bản phụ thuộc mới nhất.
B. Xác định artifact đã vượt toàn bộ kiểm thử hiệu năng.
C. Xác định artifact luôn tương thích với môi trường chạy.
D. Xác định artifact được ký bằng danh tính hoặc khóa tin cậy.
Đáp án đúng: D

Câu 7. Đội bảo mật muốn tìm image đang chứa bản thư viện có CVE vừa công bố. Dữ liệu nào giúp tra cứu thành phần phụ thuộc hiệu quả nhất?
A. Nhật ký triển khai của từng image, gắn với tên môi trường.
B. SBOM của từng image, liên kết với đúng digest phát hành.
C. Lịch sử tag của từng image, ghi thời điểm đẩy lên registry.
D. Báo cáo kiểm thử của từng image, ghi số lượng test đã chạy.
Đáp án đúng: B

Câu 8. Một đội đã kiểm thử image ở staging và muốn đưa nó lên production mà tránh khác biệt do build lại. Cách promotion nào phù hợp?
A. Build lại từ nhánh chính, giữ nguyên tag đã kiểm thử.
B. Build lại từ commit cũ, dùng cùng biến môi trường.
C. Đưa chính image theo digest đã kiểm thử sang kênh production.
D. Đẩy lại Dockerfile, yêu cầu môi trường tự build image.
Đáp án đúng: C

Câu 9. Kho lưu trữ dọn artifact cũ theo số ngày. Một bản release đang phục vụ production có nguy cơ bị xóa. Quy tắc retention nào phù hợp?
A. Xóa các artifact quá hạn, không xét môi trường hiện đang sử dụng.
B. Xóa các artifact chưa tải gần đây, kể cả bản đang chạy.
C. Chỉ giữ artifact của pipeline mới nhất trên mỗi nhánh.
D. Giữ các bản đang được dùng và mốc rollback theo chính sách.
Đáp án đúng: D

Câu 10. Một tag `service:stable` hiện trỏ tới digest mới sau đợt phát hành. Đặc tính nào cần tính đến khi viết manifest triển khai?
A. Tag có thể đổi đích; pin digest để giữ đúng image.
B. Tag luôn bất biến; pin tên tag là đủ để tái tạo.
C. Tag chứa checksum; registry tự xác minh từng container.
D. Tag gắn với commit; cùng tag luôn sinh cùng binary.
Đáp án đúng: A

Câu 11. Pipeline tải package từ kho nội bộ có proxy lên kho công khai. Kiểm soát nào giảm rủi ro nhận nhầm package trùng tên từ nguồn không tin cậy?
A. Cho các repo cùng ưu tiên, chọn package có phản hồi nhanh nhất.
B. Chọn phiên bản có số lớn nhất ở bất kỳ repo nào.
C. Ưu tiên namespace/kho được phép, khóa nguồn và phiên bản.
D. Chọn bản có ngày phát hành gần nhất, bất kể nguồn repo.
Đáp án đúng: C

Câu 12. Khi kiểm tra nguồn gốc một image, đội vận hành cần nối artifact về commit và quy trình đã tạo ra nó. Loại bằng chứng nào phù hợp nhất?
A. Bản kê dung lượng image, các layer và lịch sử tải.
B. Attestation provenance ghi source commit, builder và digest.
C. Danh sách tag image cùng thời gian registry nhận.
D. Báo cáo coverage của test suite sau bước build.
Đáp án đúng: B

Câu 13. Một quy trình tạo SBOM rồi build lại image trước khi deploy. Vì sao cách này có thể làm mất giá trị đối soát của SBOM?
A. SBOM đã tạo có thể lệch thành phần của image đem chạy.
B. SBOM đã tạo có thể thiếu tên nhãn release trong registry.
C. SBOM đã tạo có thể có ít trường hơn báo cáo kiểm thử.
D. SBOM đã tạo có thể thiếu tên môi trường sẽ triển khai.
Đáp án đúng: A

Câu 14. Một hệ thống xác minh artifact trước deploy. Vì sao cần kiểm tra cả digest lẫn provenance đã được xác thực?
A. Digest cho biết ai build; provenance cho biết kích thước file artifact.
B. Digest kiểm tra lỗ hổng; provenance kiểm tra hiệu năng.
C. Digest xác nhận byte; provenance nối byte với build tin cậy.
D. Digest cấp quyền truy cập; provenance khóa phiên bản.
Đáp án đúng: C

Câu 15. Nhóm dùng một kho chứa snapshot/dev build và release chính thức. Cấu hình nào giảm rủi ro thay nhầm bản release?
A. Cho phép ghi đè mọi phiên bản, kể cả release đã ký.
B. Tách chính sách snapshot và khóa ghi đè bản release.
C. Dùng chung tag latest cho snapshot và release ổn định.
D. Giữ release theo ngày, xóa snapshot sau mỗi lần build.
Đáp án đúng: B

Câu 16. Deployment manifest đã pin digest `sha256:...`, nhưng image đến từ nguồn chưa xác thực. Trước khi cho phép chạy, cổng policy nên làm gì?
A. Tin cậy image vì digest bất biến, bỏ qua xuất xứ bản build.
B. Chỉ tra tên tag cho dễ đọc rồi xác nhận thủ công.
C. Chạy smoke test là đủ, không cần kiểm tra danh tính.
D. Xác thực chữ ký/provenance và đối chiếu policy nguồn build.
Đáp án đúng: D
