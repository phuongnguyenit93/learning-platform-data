Câu 1. Một developer thay đổi file workflow để thêm lệnh shell chạy trước bước deploy. Kiểm soát nào giúp bảo vệ định nghĩa pipeline trước khi merge?
A. Yêu cầu runner phát hành chạy sau mọi job và bước kiểm thử pipeline.
B. Yêu cầu chủ sở hữu workflow duyệt thay đổi trước merge.
C. Đặt thời hạn cache cho các job dùng file workflow.
D. Khóa tag image của job deploy ở phiên bản cố định.
Đáp án đúng: B

Câu 2. Pipeline nhận merge request từ fork không tin cậy. Cách nào giảm nguy cơ mã của fork lấy được secret production?
A. Cho fork dùng runner chung với secret đã bật masking.
B. Cho fork chạy deploy manual sau khi job kiểm thử đạt.
C. Đặt token deploy vào variable mọi nhánh rồi giới hạn log.
D. Chạy job fork ít quyền, không cấp secret triển khai.
Đáp án đúng: D

Câu 3. Workflow gọi action của bên thứ ba đang tham chiếu tag `v2`. Thay đổi nào giảm rủi ro khi nội dung tag bị thay thế?
A. Chọn tag version `v2` được tác giả action duy trì.
B. Theo dõi nhánh `main` của action sau mỗi pipeline.
C. Đặt giới hạn timeout cho bước chạy action từ xa.
D. Pin commit SHA bất biến và kiểm tra nguồn action.
Đáp án đúng: D

Câu 4. Pipeline cần truy cập cloud bằng quyền tạm thời, không lưu access key dài hạn. Cơ chế nào phù hợp?
A. Dùng OIDC lấy token ngắn hạn theo trust policy.
B. Lưu access key dài hạn trong CI variable được masked.
C. Đặt access key vào file mã hóa rồi giải mã ở runner.
D. Cấp một access key dùng chung cho mọi repo deploy.
Đáp án đúng: A

Câu 5. Runner tự quản lý đang xử lý cả mã từ fork và job phát hành production. Kiến trúc nào bảo vệ ranh giới tin cậy tốt nhất?
A. Xóa workspace giữa các job trên cùng runner lâu dài.
B. Giới hạn thời gian chạy mỗi job trên runner dùng chung.
C. Dùng runner tạm thời, cách ly job theo mức tin cậy.
D. Bật cache dùng chung giữa job fork và job release.
Đáp án đúng: C

Câu 6. Một nhánh không tin cậy có thể ghi cache mà job release cũng đọc từ cache đó. Cách nào giảm nguy cơ cache poisoning?
A. Dùng một cache key toàn project để tăng tỷ lệ cache hit.
B. Cho nhánh fork ghi cache mà release vẫn luôn đọc lại.
C. Chỉ so sánh dung lượng cache trước khi giải nén.
D. Phân tách cache theo mức tin cậy và kiểm chứng đầu vào.
Đáp án đúng: D

Câu 7. CI tải dependency từ registry để build artifact. Cách nào tăng khả năng tái lập và giảm rủi ro nội dung gói bị thay?
A. Pin dải version trong manifest và quét dependency sau build.
B. Cho build tải phiên bản mới nhất ở mỗi lần chạy.
C. Chỉ quét SBOM từ lần phát hành trước để kiểm tra.
D. Khóa phiên bản phụ thuộc và xác minh hash gói tải về.
Đáp án đúng: D

Câu 8. Nhóm đã bật masking cho CI variable chứa token, nhưng pipeline chạy lệnh từ contributor chưa tin cậy. Kiểm soát nào hiệu quả nhất?
A. Bật masking rồi cho mọi job đọc variable chứa token.
B. Chỉ cấp token cho job tin cậy, có đúng quyền cần dùng.
C. Ghi token vào artifact với thời hạn sử dụng cực ngắn.
D. Chuyển token sang cache và bật bảo vệ lịch sử job.
Đáp án đúng: B

Câu 9. Security scanner phát hiện lỗi nghiêm trọng vi phạm policy trước release. Cách thiết kế gate nào phù hợp?
A. Dừng phát hành theo policy, cho ngoại lệ có phê duyệt.
B. Bật allow_failure cho scanner để pipeline luôn thành công.
C. Cho scanner chạy sau deploy để giảm thời gian chờ.
D. Xóa finding khỏi kết quả nếu build và unit test đều đạt.
Đáp án đúng: A

Câu 10. Để tra cứu CVE ảnh hưởng đến đúng artifact đã phát hành, SBOM cần được quản lý theo cách nào?
A. Ghi SBOM khi lập kế hoạch theo tệp dependency gốc.
B. Gắn SBOM của bản build với digest artifact phát hành.
C. Dùng SBOM của nhánh main trong lần quét gần nhất cho release.
D. Đặt version ứng dụng giống version của dependency.
Đáp án đúng: B

Câu 11. Bộ phận vận hành phải xác nhận artifact đúng do builder được duyệt tạo từ source commit đã chọn. Bằng chứng nào phù hợp?
A. Xác minh attestation ký số gắn digest, commit và builder.
B. Đối chiếu checksum do chính pipeline ghi và công bố với artifact.
C. So tên tag release với nhánh nguồn của job build.
D. Chỉ xem unit test và báo cáo coverage của pipeline.
Đáp án đúng: A

Câu 12. Hai finding có cùng CVSS, nhưng một lỗi khai thác được trên API công khai và ảnh hưởng dữ liệu quan trọng. Nên ưu tiên theo gì?
A. Xét khả năng khai thác, bề mặt phơi lộ và tác động.
B. Ưu tiên theo thứ tự finding do scanner phát hiện.
C. Chỉ so điểm CVSS và bỏ qua ngữ cảnh triển khai.
D. Ưu tiên lỗi trong job đầu tiên của pipeline.
Đáp án đúng: A

Câu 13. Quyền ghi vào kho artifact chỉ cần ở job publish sau khi test và kiểm tra chính sách đạt. Nên cấp quyền như thế nào?
A. Dùng token quản trị registry chung cho mọi pipeline.
B. Cho phép job chạy từ fork xuất bản sau khi test đạt.
C. Chỉ cấp publish credential cho job release được duyệt.
D. Cho job build ghi đè release nếu cùng version.
Đáp án đúng: C

Câu 14. Deploy production cần người có thẩm quyền phê duyệt, kể cả khi pipeline đã vượt toàn bộ bài kiểm thử. Kiểm soát nào phù hợp?
A. Cho deploy manual, ai chạy pipeline cũng được bấm.
B. Dùng protected environment, phân quyền phê duyệt deploy.
C. Dùng runner tag production để xác định người được phép deploy.
D. Gắn Git tag release rồi cho mọi job tự deploy.
Đáp án đúng: B

Câu 15. Admission policy cần bảo đảm image chạy production có nguồn gốc được chấp thuận. Điều kiện kiểm tra nào đáng tin cậy nhất?
A. Chỉ đối chiếu tên image và tag với manifest deploy.
B. Đọc checksum từ registry mà không xác minh người tạo.
C. Xác thực chữ ký, provenance và policy cho digest image.
D. Chấp nhận image nếu có SBOM dù chưa xác thực.
Đáp án đúng: C

Câu 16. Sau sự cố triển khai, nhóm muốn kiểm toán ai cho phép phát hành và đúng binary nào đã chạy. Log triển khai nên chứa gì?
A. Log test, tên nhánh, thời gian build và CPU runner.
B. Changelog, coverage, bộ test và tên người review.
C. Digest, Git SHA, người phê duyệt, môi trường và thời gian.
D. Tên job, cache key, kích thước image và ID pipeline đang chạy.
Đáp án đúng: C
