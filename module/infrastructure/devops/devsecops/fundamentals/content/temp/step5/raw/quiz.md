Câu 1. Một tổ chức muốn áp dụng DevSecOps thay vì chỉ kiểm tra bảo mật khi chuẩn bị release. Cách phân công nào thể hiện trách nhiệm chung?
A. Đội bảo mật chịu mọi kiểm soát, còn CI chỉ quản lý build.
B. Đội vận hành chịu mọi cảnh báo, lập trình viên chỉ sửa lỗi.
C. Đội kiểm thử nhận toàn bộ lỗ hổng ngay trước triển khai.
D. Các nhóm cùng tích hợp kiểm soát bảo mật trong vòng đời.
Đáp án đúng: D

Câu 2. API chấp nhận header `X-User` do client tự gửi làm danh tính đã xác thực. Theo STRIDE, mối đe dọa nổi bật là gì?
A. Tampering: kẻ tấn công sửa nội dung dữ liệu đã lưu.
B. Spoofing: kẻ tấn công tự mạo nhận người dùng khác.
C. Repudiation: người dùng phủ nhận thao tác đã ghi log.
D. Disclosure: kẻ tấn công đọc dữ liệu trong hệ thống.
Đáp án đúng: B

Câu 3. Trước khi chạy ứng dụng, nhóm cần tìm luồng dữ liệu đầu vào đi tới câu SQL ghép chuỗi trong mã nguồn. Công cụ nào phù hợp nhất?
A. DAST, gửi payload vào API staging đang vận hành.
B. SAST, phân tích mã và luồng dữ liệu chưa cần chạy.
C. SCA, đối chiếu phiên bản thư viện với cơ sở CVE.
D. IaC scanner, rà cấu hình quyền trên hạ tầng cloud.
Đáp án đúng: B

Câu 4. Nhóm muốn kiểm thử xác thực và phản hồi HTTP của ứng dụng staging đang chạy bằng các request mô phỏng tấn công. Nên dùng gì?
A. DAST có thông tin đăng nhập để thử các luồng ứng dụng.
B. SAST phân tích cấu trúc code mà không khởi chạy app.
C. SCA rà thành phần phụ thuộc được đóng gói trong bản build.
D. Secret scanner rà access key vô tình có trong repository.
Đáp án đúng: A

Câu 5. Bản build chứa thư viện phụ thuộc trực tiếp và bắc cầu. Để phát hiện phiên bản có lỗ hổng đã công bố, nên dùng gì?
A. SCA đọc cây phụ thuộc và đối chiếu dữ liệu lỗ hổng.
B. SAST dựa trên luồng dữ liệu và biểu thức trong source.
C. DAST thử các endpoint đang chạy qua HTTP request.
D. Secret scanning tìm token trùng mẫu trong source code.
Đáp án đúng: A

Câu 6. Khi lập sơ đồ luồng dữ liệu cho một dịch vụ web, vị trí nào điển hình là ranh giới tin cậy cần phân tích?
A. Giữa hai hàm trong cùng tiến trình và cùng mức đặc quyền.
B. Giữa hai bảng dữ liệu do một tài khoản sở hữu chung.
C. Nơi request từ client không tin cậy đi vào API nội bộ.
D. Giữa hai bước build liên tiếp trên cùng một runner CI.
Đáp án đúng: C

Câu 7. Một access token thật bị commit nhầm vào Git rồi đẩy lên remote. Phản ứng ban đầu nào giảm rủi ro thực tế tốt nhất?
A. Chỉ xóa chuỗi token ở commit mới vì bản cũ sẽ ít truy cập.
B. Chỉ chuyển token sang masked variable vì log sẽ che giá trị.
C. Thu hồi token cũ, cấp token mới và xử lý phạm vi lộ lọt.
D. Chỉ đổi tên biến token trong repository để tránh tìm kiếm.
Đáp án đúng: C

Câu 8. Pipeline chạy merge request từ fork không tin cậy. Cách nào giúp chặn job đó truy cập credential triển khai production?
A. Chỉ bật masked variable cho credential ở mọi pipeline.
B. Đặt `when: manual` cho deploy nhưng vẫn cấp credential.
C. Chuyển credential thành artifact hết hạn sau pipeline.
D. Giới hạn secret ở protected ref và job deploy tin cậy.
Đáp án đúng: D

Câu 9. Khi có CVE mới trong một thư viện, đội cần xác định các image release bị ảnh hưởng. Dữ liệu nào trực tiếp hỗ trợ truy vết?
A. Thời gian chạy các test suite trong từng pipeline.
B. Bảng tổng hợp kích thước image sau khi nén layer.
C. SBOM chứa dependency, gắn với digest từng image.
D. Lịch sử tag được đổi tên trong container registry.
Đáp án đúng: C

Câu 10. Đội muốn xác minh artifact được tạo từ commit đã duyệt bởi builder đáng tin cậy, ngoài kiểm tra checksum. Bằng chứng nào phù hợp?
A. Attestation provenance gắn digest với commit và builder.
B. Biên bản chạy unit test có số lượng test đã vượt qua.
C. Changelog mô tả tính năng được thêm trong phiên bản.
D. Báo cáo dung lượng artifact và số lần tải từ registry.
Đáp án đúng: A

Câu 11. Bộ quét SAST báo lỗ hổng ở một luồng dữ liệu nhưng developer cho rằng false positive. Cách xử lý nào phù hợp?
A. Kiểm tra bằng chứng và luồng khai thác, ghi nhận kết quả.
B. Tắt toàn bộ rule quét vì developer đã phủ nhận kết quả.
C. Đẩy finding thành đã xử lý ngay khi MR được phê duyệt.
D. Chặn vĩnh viễn mọi release dù chưa xem xét dữ liệu.
Đáp án đúng: A

Câu 12. Một dependency gián tiếp có CVE và có bản vá tương thích. Thay đổi nào giúp khắc phục có kiểm chứng trong CI?
A. Chỉ tắt cảnh báo CVE khi ứng dụng chưa từng báo lỗi.
B. Nâng phiên bản phụ thuộc và lockfile rồi chạy kiểm thử.
C. Chỉ đổi số version ứng dụng mà giữ nguyên dependency.
D. Chỉ cập nhật tài liệu release mà không xây dựng lại.
Đáp án đúng: B

Câu 13. Một workload Kubernetes cần đọc đúng một Secret, nhưng service account đang có quyền đọc mọi Secret trong namespace. Nên làm gì?
A. Giữ RBAC rộng để không lỗi khi workload mở rộng sau này.
B. Đặt quyền đọc rộng ở job CI rồi chia sẻ cho runtime.
C. Chỉ đổi tên Secret hiện tại để giảm xác suất bị đoán.
D. Thu hẹp quyền RBAC và danh tính theo nhu cầu workload.
Đáp án đúng: D

Câu 14. Sau khi phát hiện hành vi khai thác lỗ hổng mới trên production, cách nào đưa phản hồi vận hành vào vòng DevSecOps?
A. Chỉ tăng tần suất triển khai mà bỏ qua nguyên nhân sự cố.
B. Bổ sung kiểm thử hồi quy và cải thiện giám sát từ sự cố.
C. Chỉ lưu log sự cố để dùng khi có đợt kiểm toán tiếp theo.
D. Chỉ thay người trực vận hành mà giữ nguyên luồng phát hành.
Đáp án đúng: B

Câu 15. Có hai CVE cùng điểm CVSS, nhưng chỉ một CVE có exploit đang hoạt động trên API công khai chứa dữ liệu quan trọng. Nên ưu tiên thế nào?
A. Ưu tiên bản vá của package có kích thước cài đặt lớn hơn.
B. Ưu tiên CVE được tạo ticket sớm hơn trong cùng sprint.
C. Xếp thứ tự ngẫu nhiên vì hai CVE có cùng điểm CVSS.
D. Ưu tiên theo khả năng khai thác, mức phơi lộ và tác động.
Đáp án đúng: D

Câu 16. Một merge request thay đổi Terraform để public hóa kho lưu trữ dữ liệu. Kiểm soát nào phù hợp trước khi chạy `apply`?
A. Chỉ chạy SCA để rà phiên bản dependency ứng dụng có CVE mới.
B. Chỉ chạy DAST với staging dù resource chưa tạo ra.
C. Quét IaC/plan và kiểm tra policy truy cập trước apply.
D. Chỉ chạy secret scanner để tìm access key trong mã.
Đáp án đúng: C
