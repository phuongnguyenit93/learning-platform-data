Câu 1: Một JAR đã phát hành cần tra thư viện chịu ảnh hưởng bởi CVE mới. Dữ liệu nào hữu ích nhất?
A. Report SAST ghi vị trí mã và luồng dữ liệu cần rà soát.
B. Build provenance ghi builder và thông số build.
C. SBOM liệt kê package và phiên bản của bản phát hành.
D. Báo cáo kiểm thử ghi tổng số testcase đạt.
Đáp án đúng: C

Câu 2: Cần chứng minh một JAR do builder nào tạo từ commit nào và ràng buộc với file phát hành. Dùng gì?
A. Bản SBOM ghi các thư viện có trong JAR.
B. Attestation ghi builder, commit và digest JAR.
C. Checksum ghi SHA-256 của JAR được upload.
D. Log kiểm thử ghi job đạt và thời điểm chạy.
Đáp án đúng: B

Câu 3: CI resolve gói nội bộ nhưng kho công khai có gói trùng định danh được ưu tiên hơn. Rủi ro chính nào?
A. Resolver tải gói giả mạo công khai thay gói nội bộ.
B. Registry nội bộ tự cấp quyền ghi cho account ngoài.
C. Build runner tự đổi checksum của gói đã tải.
D. SBOM tự ẩn phụ thuộc bắc cầu khi xuất bản lên registry.
Đáp án đúng: A

Câu 4: Pipeline gọi action bên thứ ba có tag phát hành có thể bị gán lại. Cách tham chiếu nào hạn chế thay mã?
A. Ghim action theo tag `v1` do tác giả quản lý.
B. Ghim action theo SHA commit đầy đủ đã duyệt.
C. Ghim action theo nhánh `main` của tác giả.
D. Ghim action theo nhãn `latest` đang phát hành.
Đáp án đúng: B

Câu 5: Nhóm áp dụng SLSA vào quy trình phát hành. Mục tiêu trọng tâm nào đúng nhất?
A. Đảm bảo tất cả dependency hết lỗ hổng CVE.
B. Tự loại mọi package có giấy phép không phù hợp khỏi JAR.
C. Bảo đảm mã ứng dụng đã qua unit test đầy đủ.
D. Tăng bảo đảm về nguồn và quá trình build artifact.
Đáp án đúng: D

Câu 6: Build runner dùng chung giữ lại workspace giữa các project. Biện pháp nào giảm nguy cơ nhiễm chéo?
A. Tái dùng workspace chung giữa các job liên tục.
B. Chạy mọi build với quyền quản trị trên agent.
C. Dùng runner tạm thời, cô lập từng lần build.
D. Giữ token publish trên runner giữa các lần chạy.
Đáp án đúng: C

Câu 7: Attestation có chữ ký đúng nhưng danh tính người ký nằm ngoài tập tin cậy. Cổng triển khai nên làm gì?
A. Chấp nhận vì chữ ký đã khớp payload và dùng TLS.
B. Chấp nhận nếu registry cho phép tải image.
C. Chỉ kiểm SHA-256 rồi bỏ qua người ký.
D. Từ chối vì người ký không thuộc tập tin cậy.
Đáp án đúng: D

Câu 8: CI muốn ký artifact không lưu khóa riêng dài hạn. Cơ chế keyless signing dựa vào gì?
A. Dùng OIDC lấy chứng chỉ ký ngắn hạn theo job.
B. Lưu khóa PGP dùng chung trong repository private.
C. Dùng tag Git đã ký thay cho chữ ký artifact.
D. Dựa vào chứng chỉ TLS của registry để ký JAR.
Đáp án đúng: A

Câu 9: Một tag release có thể bị ghi đè ở registry. Tham chiếu nào giữ đúng image đã duyệt?
A. Dùng tag `stable` vì tag mặc định không đổi.
B. Dùng ngày push gần nhất trong registry.
C. Dùng tên branch release của source code.
D. Dùng digest artifact đã được xác minh trước.
Đáp án đúng: D

Câu 10: Provenance được ký cho digest A nhưng image dự định deploy có digest B. Hệ thống nên làm gì?
A. Cho deploy nếu cả hai có cùng tag release.
B. Cho deploy nếu image đã scan không có CVE nghiêm trọng.
C. Chặn vì subject digest không khớp image cần chạy.
D. Chỉ ghi cảnh báo nếu image nằm ở registry riêng.
Đáp án đúng: C

Câu 11: SBOM chỉ liệt kê dependency khai báo trực tiếp, bỏ qua gói bắc cầu. Cách cải thiện nào đúng?
A. Lấy đồ thị dependency đã resolve, gồm gói bắc cầu.
B. Chỉ dùng khai báo trực tiếp trong tệp build.
C. Bỏ dependency không có entry trong license file.
D. Chỉ quét manifest mà không kiểm bản đã resolve.
Đáp án đúng: A

Câu 12: Job test chỉ đọc source, job phát hành cần push artifact lên registry. Cách cấp quyền nào đúng?
A. Phân quyền từng job; chỉ release có quyền push.
B. Cấp quyền push toàn workflow để test tái dùng.
C. Gửi token push qua output của job test sang job phát hành.
D. Dùng token quản trị chung cho build và deploy.
Đáp án đúng: A

Câu 13: Người lạ gửi thay đổi sửa pipeline build ở nhánh chính. Kiểm soát nào giảm rủi ro can thiệp?
A. Chỉ giảm thời hạn lưu artifact trên registry.
B. Bảo vệ nhánh, bắt buộc review thay đổi pipeline.
C. Chỉ chạy thêm SCA sau mỗi lần triển khai để kiểm pipeline.
D. Chỉ ký tag release khi hoàn thành build.
Đáp án đúng: B

Câu 14: Hai bên build độc lập với cùng source, dependency và toolchain. Reproducible build giúp kiểm gì?
A. Mỗi lần build tự lấy dependency mới nhất.
B. Hai lần build luôn dùng runner cùng hostname.
C. Bản build mặc định không còn lỗ hổng phụ thuộc.
D. Đầu ra giống nhau đến từng byte để đối chiếu.
Đáp án đúng: D

Câu 15: Policy trước deploy yêu cầu builder đáng tin, source đúng repo và digest khớp. Nếu một mục sai, làm gì?
A. Cho deploy nếu chữ ký tồn tại, không xét người ký.
B. Cho deploy khi tag trong registry có tên release.
C. Chặn nếu builder, source hoặc digest không khớp.
D. Chỉ quét CVE và bỏ qua xuất xứ của artifact.
Đáp án đúng: C

Câu 16: Đội phát hiện credential của builder bị lộ sau nhiều bản phát hành. Bước ứng phó nào phù hợp?
A. Chỉ xóa artifact cũ khỏi dashboard để ẩn cảnh báo.
B. Thu hồi quyền, khoanh vùng release và build lại an toàn.
C. Chỉ đổi tag cho các release mà không đổi chữ ký.
D. Chỉ chạy lại unit test trên artifact đã phát hành.
Đáp án đúng: B
