Câu 1: Một API đặt SLO theo tỷ lệ yêu cầu hợp lệ trả kết quả thành công. SLI nào đo trực tiếp mục tiêu này?
A. Số yêu cầu hợp lệ thành công chia cho tổng yêu cầu hợp lệ.
B. Tỷ lệ máy chủ có CPU thấp hơn ngưỡng trong mỗi chu kỳ giám sát.
C. Tổng số yêu cầu thành công tính trong mỗi ngày vận hành.
D. Thời gian hoạt động của VM so với thời gian trong tháng.
Đáp án đúng: A

Câu 2: API có SLO khả dụng 99,9% trong 30 ngày nhưng đã dùng 80% error budget ở tuần đầu. Quyết định phát hành nào phù hợp?
A. Nâng SLO giữa kỳ để lỗi vừa xảy ra không tính vào báo cáo.
B. Tăng replica và tiếp tục triển khai mọi thay đổi đã lên lịch.
C. Hạn chế thay đổi rủi ro, ưu tiên xử lý nguyên nhân gây lỗi.
D. Đặt lại error budget theo tuần để bỏ lỗi ở tuần trước.
Đáp án đúng: C

Câu 3: Ứng dụng chạy trên hai nhà cung cấp cloud; cần phát hiện suy giảm trải nghiệm API trước khi vi phạm SLO. Bộ tín hiệu nào phù hợp?
A. Theo dõi tỷ lệ lỗi, độ trễ và số yêu cầu của cùng dịch vụ.
B. Theo dõi CPU, kích thước VM và số phiên bản đã triển khai.
C. Theo dõi dung lượng đĩa, số bucket và ngày tạo tài nguyên.
D. Theo dõi hóa đơn, số tag và số vùng triển khai của dịch vụ.
Đáp án đúng: A

Câu 4: Nhân viên trực nhận hàng trăm cảnh báo CPU nhưng người dùng không bị ảnh hưởng. Cách điều chỉnh nào giảm nhiễu mà vẫn phát hiện sự cố?
A. Tăng độ nhạy của cảnh báo CPU cho tất cả máy chủ.
B. Tạo cảnh báo riêng cho mỗi lần container khởi động lại.
C. Gộp toàn bộ log cảnh báo vào một email gửi cuối tuần.
D. Ưu tiên cảnh báo burn rate SLO và loại cảnh báo trùng.
Đáp án đúng: D

Câu 5: Khi phát hành bản API mới, tỷ lệ HTTP 5xx tăng ở một phần người dùng. Kiểu triển khai nào cho phép kiểm chứng trước khi mở rộng?
A. Rolling update toàn bộ instance rồi xem lỗi cuối đợt phát hành.
B. Canary với một phần lưu lượng và rollback khi lỗi vượt ngưỡng.
C. Blue-green chuyển ngay toàn bộ lưu lượng sang môi trường mới.
D. Tắt kiểm tra sức khỏe để bản mới không bị gỡ khỏi cụm.
Đáp án đúng: B

Câu 6: Runbook xử lý sự cố tăng độ trễ gateway nên chứa nội dung nào để người trực hành động an toàn?
A. Danh sách tác giả tính năng và lịch sử các sprint gần đây.
B. Bảng tổng kết KPI của quý trước và kế hoạch ngân sách kỳ sau.
C. Danh sách máy chủ từng dùng trước khi hệ thống lên cloud.
D. Điều kiện kích hoạt, bước kiểm tra, rollback và cách leo thang.
Đáp án đúng: D

Câu 7: Khi thanh toán bị gián đoạn kéo dài và chưa rõ nguyên nhân, người điều phối sự cố nên tổ chức trao đổi ra sao?
A. Chờ xác định root cause rồi mới báo các nhóm liên quan.
B. Yêu cầu từng kỹ sư báo tình hình cho khách hàng theo kênh riêng.
C. Phân vai xử lý, cập nhật định kỳ và ghi lại mốc sự cố.
D. Tạm dừng giám sát để giảm cảnh báo trong quá trình sửa lỗi.
Đáp án đúng: C

Câu 8: Nhóm khắc phục xong sự cố mất dịch vụ do thay đổi cấu hình nhầm. Kết quả postmortem nào giúp ngăn tái diễn?
A. Nêu tên cá nhân thay đổi cấu hình và khóa tài khoản người đó.
B. Xác định yếu tố hệ thống và giao hành động phòng ngừa có chủ.
C. Chỉ ghi thời gian gián đoạn và xác nhận hệ thống hoạt động lại.
D. Xóa cảnh báo cũ để báo cáo vận hành không có sự cố lặp.
Đáp án đúng: B

Câu 9: Người dùng gặp lỗi checkout qua API gateway và ba microservice. Cách nào giúp theo dõi một yêu cầu xuyên hệ thống?
A. Dùng tên host và tổng số request theo giờ ở từng microservice.
B. Dùng mức CPU của gateway và trạng thái health check VM.
C. Dùng hóa đơn mạng và lưu lượng truyền dữ liệu theo ngày.
D. Gắn trace ID xuyên dịch vụ, liên kết span với log liên quan.
Đáp án đúng: D

Câu 10: Bản triển khai mới làm lỗi xác thực diện rộng; chưa rõ nguyên nhân. Hành động ưu tiên nào giảm tác động lên người dùng?
A. Rollback về bản ổn định rồi điều tra trong môi trường riêng.
B. Tiếp tục đẩy bản mới đến mọi vùng để tái hiện triệu chứng.
C. Tắt tạm kiểm soát truy cập để request vượt qua xác thực.
D. Tăng giới hạn retry cho mọi client trước khi phân tích lỗi.
Đáp án đúng: A

Câu 11: Ứng dụng có snapshot cơ sở dữ liệu hằng ngày nhưng chưa từng thử phục hồi. Cách nào xác nhận bản sao lưu hữu dụng?
A. Đếm số snapshot đã tạo và dung lượng ghi của mỗi ngày.
B. Kiểm tra tên file backup, thời điểm tạo và chữ ký số của bản lưu.
C. Phục hồi vào môi trường cô lập, kiểm tra dữ liệu và thời gian.
D. Giữ bản sao trên cùng ổ đĩa sản xuất để dễ truy cập.
Đáp án đúng: C

Câu 12: Dịch vụ cần RPO 10 phút và RTO 1 giờ nếu mất toàn bộ một vùng cloud. Phép thử nào xác nhận đồng thời hai yêu cầu?
A. Đo thời gian tạo snapshot và số bản sao mỗi giờ trong vùng.
B. Đo thời gian chạy lại pipeline CI và khả năng tải image.
C. Đo thời gian nhận cảnh báo và số lỗi ghi nhận trong tuần.
D. Diễn tập failover liên vùng, đo mất dữ liệu và thời gian hồi phục.
Đáp án đúng: D

Câu 13: Phát hiện secret của workload bị ghi vào hệ thống log tập trung. Biện pháp ứng phó nào cần ưu tiên?
A. Xóa log có secret rồi giữ nguyên khóa để tránh gián đoạn.
B. Thu hồi hoặc xoay secret, kiểm tra truy cập và ngăn ghi lộ.
C. Chỉ tăng thời gian lưu log để tiện truy vấn hành vi bất thường.
D. Đổi tên workload và chuyển log sang vùng lưu trữ khác.
Đáp án đúng: B

Câu 14: Đội vận hành thường sửa firewall trực tiếp trên console rồi quên cập nhật IaC. Quy trình nào giảm cấu hình trôi dạt?
A. Ghi thay đổi vào bảng tính cuối tháng rồi áp dụng tuần sau.
B. Đưa thay đổi qua pull request IaC, soát drift và phê duyệt.
C. Nhân bản cấu hình firewall hiện tại sang các tài khoản cloud.
D. Chấp nhận sửa trên console nếu từng kỹ sư có ghi chú.
Đáp án đúng: B

Câu 15: Nhiều VM trong môi trường test chạy cả cuối tuần dù không có job. Cách tối ưu chi phí nào có kiểm soát?
A. Đặt lịch tắt mở theo nhu cầu, đo tác động trước khi áp dụng.
B. Đổi VM sang loại lớn hơn để hoàn thành test nhanh mỗi tuần.
C. Mua gói cam kết dài hạn cho tất cả VM của môi trường test.
D. Chuyển VM sang vùng rẻ hơn mà không kiểm tra phụ thuộc.
Đáp án đúng: A

Câu 16: Khi kiểm toán thay đổi cấu hình trên hai nền tảng cloud, cần biết ai thay đổi, thời điểm và tài nguyên liên quan. Nên thu thập gì?
A. Số VM đang chạy theo từng vùng ở cả hai nền tảng cloud.
B. Tổng chi phí của từng tài khoản theo tháng trên hai cloud.
C. Audit log thay đổi có danh tính, thời gian và tài nguyên.
D. Metric CPU và mạng để suy ra thao tác của người quản trị.
Đáp án đúng: C
