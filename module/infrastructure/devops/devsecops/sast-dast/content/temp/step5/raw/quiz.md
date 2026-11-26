Câu 1: Pipeline chưa triển khai ứng dụng; cần lần đường dữ liệu từ HTTP input đến câu SQL ghép chuỗi. Kỹ thuật nào phù hợp?
A. Dùng ZAP active scan trên endpoint SQL của production.
B. Dùng DAST crawl các đường dẫn ở staging.
C. Dùng SAST phân tích taint flow trong mã ứng dụng.
D. Dùng kiểm thử tải để theo dõi truy vấn SQL.
Đáp án đúng: C

Câu 2: Nhóm muốn viết kiểm tra Semgrep tìm mẫu gọi API nguy hiểm trong pull request. Cách nào đúng?
A. Khai báo URL để ZAP crawl trên môi trường test của PR.
B. Viết rule YAML với pattern và chạy Semgrep trong CI.
C. Dùng CodeQL queries cho dòng dữ liệu trước khi build.
D. Sửa cấu hình scanner để đọc log HTTP của app.
Đáp án đúng: B

Câu 3: Trong CodeQL, để phân tích dữ liệu không tin cậy tới hàm thực thi lệnh shell, cần mô hình gì?
A. Mô hình truy vấn chỉ dựa trên call graph tổng thể.
B. Mô hình source, sink và luồng dữ liệu/taint.
C. Mô hình khớp literal URL trong file cấu hình.
D. Mô hình thời gian phản hồi HTTP khi chạy app.
Đáp án đúng: B

Câu 4: ZAP Baseline Scan chạy xong không thấy cảnh báo. Kết luận nào hợp lý?
A. Ứng dụng đã được xác nhận không còn SQL injection.
B. Có thể bỏ mọi bước kiểm thử chủ động ở staging.
C. Đã kiểm chứng toàn bộ endpoint có phân quyền đúng.
D. Chưa đủ để loại trừ lỗ hổng cần active testing.
Đáp án đúng: D

Câu 5: Semgrep báo command injection, nhưng dev cho rằng đường input đã được lọc. Trước khi đóng finding, cần gì?
A. Chỉ xác nhận severity trong báo cáo scanner đang ở mức low.
B. Chỉ dựa vào test CI xanh mà không cần xem đường gọi.
C. Chỉ kiểm tra payload mẫu có chạy được trên localhost.
D. Truy vết đầu vào, biến đổi dữ liệu và sink liên quan.
Đáp án đúng: D

Câu 6: ZAP quét ứng dụng có màn hình quản trị yêu cầu login nhưng không phát hiện `/admin`. Nên làm gì?
A. Cấu hình context, xác thực và user cho phiên quét.
B. Tăng thời gian chờ phản hồi của scan request.
C. Đổi mức cảnh báo từ low lên high trong rule.
D. Chỉ tăng số luồng quét cho endpoint công khai.
Đáp án đúng: A

Câu 7: Muốn kiểm tra khả năng reflected XSS trên bản build đang chạy trong staging, phương án nào đúng?
A. Chạy Semgrep đối chiếu quy tắc cú pháp Java có xử lý input.
B. Chạy CodeQL để tạo đồ thị hàm gọi Java ở server.
C. Thử payload qua HTTP và quan sát thực thi trình duyệt.
D. Đọc SBOM để suy ra phản hồi HTML có escaping.
Đáp án đúng: C

Câu 8: Ứng dụng staging có endpoint xóa dữ liệu; muốn active DAST an toàn. Nên thiết kế thế nào?
A. Dùng dữ liệu thử, cô lập môi trường và giới hạn phạm vi quét.
B. Dùng dữ liệu thật, chạy trên production ngoài giờ.
C. Dùng token quản trị thật và quét toàn bộ dữ liệu.
D. Dùng mọi endpoint trong production rồi chỉ lưu báo cáo kết quả.
Đáp án đúng: A

Câu 9: ZAP không thấy API chỉ xuất hiện sau khi JavaScript tải trang. Điều chỉnh nào hợp lý?
A. Chỉ quét các URL cố định trong sitemap XML thay vì dùng browser.
B. Dùng AJAX Spider hoặc browser crawl và kiểm coverage.
C. Tăng alert threshold của passive scanner lên high.
D. Chạy SAST trên cache asset của trình duyệt để tìm API.
Đáp án đúng: B

Câu 10: Cảnh báo DAST cho rằng XSS tồn tại vì tham số được phản chiếu trong HTML. Làm gì để xác minh?
A. Kiểm tra context và việc payload thực thi ở trình duyệt.
B. Chỉ căn cứ vào HTTP 200 và chuỗi payload có xuất hiện trong HTML.
C. Chỉ đọc tên alert mà không thử tái hiện hành vi.
D. Tắt escaping để so sánh response trong lần scan.
Đáp án đúng: A

Câu 11: Pipeline SAST đang tạo lại hàng trăm finding cũ mỗi PR. Cách kiểm soát nhiễu hợp lý?
A. So findings với baseline được quản lý, ưu tiên lỗi mới.
B. Bỏ quét những module có quá nhiều kết quả lịch sử.
C. Chỉ chuyển các báo cáo sang dạng text để giảm log.
D. Bỏ toàn bộ cảnh báo severity trung bình trong CI.
Đáp án đúng: A

Câu 12: Muốn phát hiện cookie session thực tế thiếu cờ HttpOnly trên phản hồi đã triển khai, nên dùng phép kiểm tra nào?
A. Đọc code xây cookie mà không chạy ứng dụng.
B. Quét dependency của framework theo danh sách CVE.
C. Dùng DAST/HTTP kiểm tra header `Set-Cookie` trả về.
D. Chạy parser Semgrep trên file cấu hình build.
Đáp án đúng: C

Câu 13: Nhóm muốn gate SAST và DAST trong pipeline theo điểm mạnh của từng kỹ thuật. Cách bố trí nào đúng?
A. Chạy DAST trước khi build, SAST sau khi deploy prod.
B. Chỉ chạy SAST sau khi release để tránh chặn PR.
C. Thay cả hai bằng kiểm tra dependency ở giai đoạn build.
D. Chạy SAST trên PR, DAST ở staging và gate theo policy.
Đáp án đúng: D

Câu 14: Finding Semgrep được xác nhận là false positive sau review. Cách quản lý ngoại lệ nào tốt nhất?
A. Tắt rule đó cho mọi repository để giảm cảnh báo.
B. Ghi căn cứ, phạm vi hẹp, owner và ngày xem lại.
C. Xóa đoạn mã liên quan khỏi quá trình scan mà không ghi lý do.
D. Bỏ mọi alert tương tự khi xuất hiện tại repository khác.
Đáp án đúng: B

Câu 15: Nhóm xây rule SAST riêng phát hiện API nguy hiểm. Trước khi bật gate bắt buộc, nên kiểm gì?
A. Chỉ chạy rule trên một commit có lỗi đã biết.
B. Chỉ kiểm tra cú pháp rule mà không xem kết quả.
C. So số cảnh báo mới với số commit trong nhánh.
D. Thử bộ ví dụ có/không có lỗi, đo false positive.
Đáp án đúng: D

Câu 16: DAST trả hàng loạt HTTP 403 ở trang quản trị. Có thể kết luận phần đó không có lỗ hổng không?
A. Có, vì HTTP 403 chứng minh mọi API đã được chặn khi scan.
B. Có, vì mọi phép thử DAST đều hoàn tất đúng quy trình.
C. Không; cần xác minh đăng nhập, quyền và coverage quét.
D. Không; chỉ cần tăng scan strength là có đủ kết quả.
Đáp án đúng: C
