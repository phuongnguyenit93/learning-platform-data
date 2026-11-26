Câu 1: Ứng dụng chỉ khai báo trực tiếp `web-starter` nhưng SCA phát hiện CVE ở `http-core`. Nguyên nhân nào hợp lý nhất?
A. `http-core` chỉ có thể nằm trong plugin khi chạy build.
B. `http-core` là dependency của JDK nên không nằm trong POM.
C. `http-core` có thể được kéo vào qua phụ thuộc bắc cầu.
D. `http-core` chỉ được tạo ra trong cache của CI runner.
Đáp án đúng: C

Câu 2: Trong Maven, cách nào giúp lần ra chuỗi phụ thuộc dẫn tới thư viện đang có CVE?
A. Chạy `mvn dependency:tree` để xem cây phụ thuộc.
B. Chạy `mvn dependency:analyze` để kiểm tra khai báo.
C. Chạy `mvn dependency:resolve` để tải các artifact.
D. Chạy `mvn help:effective-pom` để xem cấu hình.
Đáp án đúng: A

Câu 3: Gradle nhận hai yêu cầu phiên bản khác nhau của cùng module. Cần biết bản được resolve và lý do chọn. Làm gì?
A. Đọc phiên bản khai báo trực tiếp trong `build.gradle` là đủ.
B. Xem tên module trong bản ghi publish của thư viện.
C. Chạy unit test rồi suy ra phiên bản từ kết quả.
D. Dùng `dependencyInsight` theo module và configuration.
Đáp án đúng: D

Câu 4: Hai lỗ hổng có CVSS gần nhau nhưng EPSS khác biệt. EPSS chủ yếu cho biết gì?
A. Mức tác động kỹ thuật của lỗ hổng nếu bị khai thác.
B. Tỷ lệ sử dụng thư viện trên các kho package công khai.
C. Xác suất lỗ hổng bị khai thác theo mô hình dự báo.
D. Mức độ tương thích của bản sửa lỗi với ứng dụng cũ.
Đáp án đúng: C

Câu 5: Một CVE mới xuất hiện sau khi ứng dụng đã phát hành. SBOM của bản phát hành giúp đội xử lý thế nào?
A. Xác nhận mọi thư viện đều an toàn tại lúc phát hành.
B. Tra thành phần và phiên bản để tìm release bị ảnh hưởng.
C. Chứng minh ứng dụng không gọi hàm chứa mã dễ lỗi.
D. Thay thế bước phân tích lỗ hổng trong pipeline CI.
Đáp án đúng: B

Câu 6: SCA báo CVE trong hàm parser nhưng nhóm chưa thấy ứng dụng gọi hàm này. Đánh giá nào phù hợp?
A. Kiểm reachability, dữ liệu đầu vào và kiểm soát giảm thiểu.
B. Tự đóng cảnh báo vì thư viện không được gọi trực tiếp trong mã.
C. Chỉ ưu tiên theo độ dài thông báo của advisory.
D. Loại dependency khỏi SBOM để không bị cảnh báo lại.
Đáp án đúng: A

Câu 7: Lỗ hổng nằm ở dependency bắc cầu của thư viện Maven. Hướng khắc phục nào có cơ sở?
A. Xóa thư viện khỏi cache Maven rồi build lại nguyên trạng.
B. Nâng thư viện cha hoặc ép bản đã vá, kiểm thử resolve.
C. Đổi tên artifact phát hành mà giữ dependency hiện tại.
D. Loại cảnh báo vì dependency không khai báo trực tiếp.
Đáp án đúng: B

Câu 8: Nhóm dùng Gradle dependency locking cho release. Giá trị chính của cơ chế này với SCA là gì?
A. Cho phép kéo bản mới nhất ở mỗi lần build CI.
B. Thay thế kiểm thử hồi quy khi nâng dependency trên CI.
C. Tự đảm bảo tất cả package có chữ ký hợp lệ.
D. Giữ ổn định phiên bản đã resolve giữa các lần quét.
Đáp án đúng: D

Câu 9: Đội muốn pipeline chặn rủi ro mới nhưng vẫn tôn trọng ngoại lệ được phê duyệt. Policy nào hợp lý?
A. Chặn mọi phát hiện cũ dù còn ngoại lệ hiệu lực.
B. Chỉ cảnh báo và luôn cho phép phát hành tiếp.
C. Chỉ chặn nếu phát hiện làm thay đổi version ứng dụng.
D. Chặn rủi ro mới vượt ngưỡng, xét ngoại lệ còn hạn.
Đáp án đúng: D

Câu 10: SCA ghép advisory cho package tên giống nhau ở hệ sinh thái khác. Nên làm gì trước khi kết luận?
A. Tăng mức nghiêm trọng để tránh bỏ sót các cảnh báo.
B. Chỉ kiểm tra tên file artifact trong registry nội bộ.
C. Đối chiếu hệ sinh thái, định danh gói và bản đã resolve.
D. Xóa kết quả scan vì tên thư viện đã trùng với advisory.
Đáp án đúng: C

Câu 11: Artifact vẫn cùng digest nhưng báo cáo SCA tuần này có thêm CVE. Giải thích nào đúng nhất?
A. Thư viện trong JAR tự đổi phiên bản sau khi publish.
B. Checksum của artifact biến đổi khi CSDL CVE cập nhật.
C. Advisory mới xuất hiện dù nội dung artifact không đổi.
D. Registry tự cài bản vá cho dependency trong image đã push.
Đáp án đúng: C

Câu 12: Maven báo lỗ hổng trong dependency dùng cho test. Muốn đánh giá tác động production, cần làm gì?
A. Mặc định coi mọi thư viện test đều chạy trong production.
B. Kiểm tra phạm vi runtime, artifact thực tế và đường gọi.
C. Bỏ qua mọi CVE ở test scope bất kể môi trường CI.
D. Chỉ căn cứ điểm CVSS mà không cần phân tích scope.
Đáp án đúng: B

Câu 13: CVE chưa có bản vá, nhóm muốn xin ngoại lệ có thời hạn. Hồ sơ nào cần được lưu?
A. CVE, package, căn cứ rủi ro, owner và hạn xem xét lại.
B. CVE, số lượt chạy pipeline, nhánh chính và thời gian build.
C. CVE, tên tác giả, số commit và tag release mới nhất.
D. CVE, tên mirror, cấu hình runner và lịch xóa cache.
Đáp án đúng: A

Câu 14: Hai CVE có CVSS tương tự. Trường hợp nào cần được ưu tiên xử lý dựa trên nguy cơ thực tế?
A. Lỗi chỉ nằm trong dependency test không có trên prod.
B. Lỗi có ngoại lệ được duyệt và vẫn còn thời hạn.
C. Lỗi nằm trong gói không có ở artifact đã triển khai.
D. Lỗi nằm trong KEV và có đường vào bị phơi lộ công khai.
Đáp án đúng: D

Câu 15: Muốn truy vết SBOM tới đúng bản đang chạy khi xuất hiện advisory mới, nên liên kết với gì?
A. Digest của artifact phát hành cùng danh sách thành phần.
B. Tên nhánh phát triển và giờ scan trên runner gần nhất.
C. Tag `latest` cùng tên job CI xây dựng bản hiện hành.
D. Người tạo pull request cùng ngày bắt đầu sprint.
Đáp án đúng: A

Câu 16: Sau khi nâng dependency để vá CVE, bước xác nhận nào tốt nhất trước khi merge?
A. Chỉ đổi khai báo version rồi giữ nguyên kết quả scan trước đó.
B. Quét đồ thị đã resolve, build và chạy kiểm thử hồi quy.
C. Chỉ đổi mã release và cập nhật biên bản ngoại lệ.
D. Xóa log scanner rồi dùng lại artifact chưa vá.
Đáp án đúng: B
