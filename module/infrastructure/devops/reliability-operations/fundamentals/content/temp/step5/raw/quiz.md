Dịch vụ thanh toán có các Pod đều Ready nhưng khách hàng vẫn không hoàn tất giao dịch; SLI nào phản ánh trực tiếp tác động này nhất?
A. Tỷ lệ Pod thanh toán đạt trạng thái Ready trong ngày.
B. Tỷ lệ giao dịch hoàn tất thành công theo góc nhìn khách hàng.
C. Tỷ lệ API thanh toán trả HTTP 2xx trước khi xác nhận giao dịch.
D. Tỷ lệ máy chủ thanh toán còn đủ CPU để nhận thêm tải.
Đáp án đúng: B

Với API tìm kiếm, cách đo SLI độ trễ nào phù hợp nhất để phản ánh thời gian người dùng phải chờ?
A. Lấy độ trễ trung bình mọi yêu cầu kể cả tác vụ nền theo giờ.
B. Lấy độ trễ tại load balancer của một lần kiểm tra sức khỏe.
C. Đo tỷ lệ tìm kiếm hợp lệ đạt ngưỡng độ trễ đã đặt.
D. Lấy thời gian CPU xử lý một request trên máy chủ trung bình.
Đáp án đúng: C

Phân biệt nào đúng khi nhóm SRE thiết lập SLO còn doanh nghiệp ký SLA cho một dịch vụ trực tuyến?
A. SLO là mức phạt hợp đồng, SLA là ngưỡng cảnh báo nội bộ.
B. SLO mô tả CPU mục tiêu, SLA mô tả tài nguyên dự phòng.
C. SLO đặt mục tiêu tin cậy, SLA nêu cam kết với khách hàng.
D. SLO chỉ dùng khi có hợp đồng, SLA chỉ dùng cho nhóm nội bộ.
Đáp án đúng: C

Khi dịch vụ tiêu thụ error budget quá nhanh trong kỳ SLO, chính sách phát hành nào phù hợp tư duy SRE?
A. Giảm nhịp phát hành rủi ro khi ngân sách lỗi tiêu hao quá nhanh.
B. Tăng thời gian quan sát SLO để các lỗi cũ bị làm mờ dần.
C. Loại các lỗi trong khung cao điểm khỏi ngân sách lỗi của kỳ.
D. Cố định lịch phát hành dù tỷ lệ lỗi và ngân sách kỳ này biến động.
Đáp án đúng: A

Cảnh báo tốc độ tiêu hao error budget qua nhiều cửa sổ thời gian có ưu điểm nào so với chỉ cảnh báo CPU cao?
A. Dùng chỉ số CPU của toàn cluster để suy ra ngân sách lỗi còn sử dụng.
B. Chỉ cảnh báo khi trung bình cả tháng đã vượt ngân sách lỗi.
C. Thay tỷ lệ lỗi bằng tổng số lần autoscaler thêm replica mới.
D. Phát hiện cả tốc độ đốt lỗi đột biến và lỗi kéo dài khó thấy.
Đáp án đúng: D

Dashboard chỉ có CPU và bộ nhớ của máy chủ; bộ chỉ số nào cần bổ sung để theo dõi bốn golden signals của dịch vụ?
A. Độ trễ, lưu lượng, tỷ lệ lỗi và độ bão hòa ở mức dịch vụ.
B. Số node, số Pod, dung lượng ổ đĩa và trạng thái scheduler.
C. Số lần deploy, commit mỗi ngày, tỷ lệ review và thời gian build.
D. Số bản backup, thời gian restore, số snapshot và tuổi dữ liệu.
Đáp án đúng: A

Sau triển khai, p95 latency tăng nhưng CPU vẫn ổn định; cách kết hợp telemetry nào giúp tìm điểm nghẽn qua nhiều dịch vụ?
A. Kiểm tra mức dùng CPU rồi thêm replica cho mọi dịch vụ liên quan.
B. Đọc access log của ingress rồi tăng timeout cho toàn bộ upstream.
C. Tổng hợp request toàn cluster rồi tăng worker theo cùng một tỷ lệ.
D. Đối chiếu latency theo dịch vụ, trace spans và log theo request.
Đáp án đúng: D

Khi nhiều nhóm cùng nhận cảnh báo về một sự cố nghiêm trọng, cách phối hợp nào giúp giảm xung đột thao tác?
A. Cho các nhóm phân tích riêng và chỉ tổng hợp sau khi xử lý.
B. Chỉ định điều phối, phân vai và dùng chung kênh cập nhật.
C. Đợi xác định nguyên nhân gốc rồi mới thông báo tình trạng.
D. Cho nhiều người cùng thay đổi production để giảm thời gian lỗi.
Đáp án đúng: B

Khi triển khai canary, dấu hiệu nào đáng dùng để tạm dừng tăng tỷ lệ lưu lượng vào phiên bản mới?
A. Image canary nhỏ hơn và tải lên registry nhanh hơn bản cũ.
B. Canary tăng tỷ lệ lỗi hoặc độ trễ so với ngưỡng đã đặt.
C. Pipeline build canary thành công và không có cảnh báo bảo mật.
D. Số Pod canary tăng đều trong khi lượng request đang ổn định.
Đáp án đúng: B

Dịch vụ phụ thuộc liên tục timeout; cách thiết kế retry nào hạn chế khuếch đại sự cố cho downstream?
A. Thử lại theo chu kỳ cố định cho đến khi upstream đáp ứng.
B. Dồn mọi request timeout vào hàng đợi để xử lý một lúc.
C. Tăng số request retry khi tỷ lệ timeout của upstream tăng.
D. Giới hạn lượt retry, dùng backoff có jitter và xét idempotency.
Đáp án đúng: D

Khi downstream liên tiếp trả lỗi, circuit breaker bảo vệ dịch vụ gọi bằng cơ chế nào?
A. Tăng timeout của request mỗi lần downstream trả lỗi.
B. Tạm ngừng gửi request khi lỗi vượt ngưỡng rồi thử phục hồi.
C. Khởi động lại Pod downstream sau mỗi lần gặp lỗi mạng.
D. Chuyển mọi request lỗi sang bộ nhớ đệm trong cùng tiến trình.
Đáp án đúng: B

Trong kế hoạch phục hồi sau thảm họa, hai mục tiêu RPO và RTO lần lượt giới hạn điều gì?
A. Độ tuổi dữ liệu có thể mất và thời gian tối đa để khôi phục dịch vụ.
B. Mức sẵn sàng của vùng chính và giới hạn CPU trong quá trình failover.
C. Số bản sao lưu cần giữ và dung lượng bản snapshot mới nhất.
D. Độ trễ replication và tỷ lệ request lỗi cho phép mỗi tháng.
Đáp án đúng: A

Dịch vụ đề xuất sản phẩm bị chậm trong giờ cao điểm; giải pháp nào giúp giữ luồng mua hàng cốt lõi?
A. Giới hạn chờ dịch vụ đề xuất và trả kết quả dự phòng khi quá hạn.
B. Cho giao dịch chờ đề xuất trả đủ dữ liệu trước khi tiếp tục.
C. Giảm tài nguyên dịch vụ mua hàng nhằm tăng CPU cho xử lý đề xuất.
D. Dừng thanh toán khi đề xuất chưa đáp ứng ngưỡng độ trễ.
Đáp án đúng: A

Sau sự cố do thay đổi cấu hình, cách viết postmortem nào tạo nền tảng cải tiến bền vững theo SRE?
A. Ghi người phê duyệt rồi bổ sung bước xác nhận thủ công ở lần sau.
B. Tổng hợp số phút gián đoạn và yêu cầu tăng thời gian review.
C. Lập timeline, phân tích yếu tố hệ thống, gắn chủ sở hữu cải tiến.
D. Chốt tên nhóm gây lỗi rồi bổ sung bước kiểm tra thủ công.
Đáp án đúng: C

Công việc nào nên được ưu tiên tự động hóa để giảm toil theo tư duy vận hành SRE?
A. Thiết kế giới hạn chịu lỗi cho một hệ thống mới chưa rõ tải.
B. Phân tích nguyên nhân gốc từ tín hiệu của một sự cố mới.
C. Đàm phán mức SLO dịch vụ với nhóm sản phẩm và khách hàng.
D. Khởi chạy tác vụ bảo trì thủ công theo checklist mỗi ngày.
Đáp án đúng: D

Để hạn chế alert fatigue trong ca trực SRE, cảnh báo nào phù hợp nhất để đánh thức người trực?
A. Log debug tăng dù người dùng không nhận thấy bất kỳ lỗi nào.
B. CPU một node tăng nhẹ trong khi độ trễ API vẫn ổn định.
C. Error budget bị đốt nhanh và có runbook giảm thiểu rõ ràng.
D. HPA tăng số replica trong lúc lưu lượng thực tế đi lên.
Đáp án đúng: C
