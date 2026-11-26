Nhóm đặt mục tiêu 99,95% giao dịch thành công trong 28 ngày và ghi trong hợp đồng mức bảo đảm 99,5% kèm bồi thường; cách phân loại nào chính xác?
A. Cả hai là SLI vì đều sử dụng tỷ lệ thành công làm phép đo dịch vụ.
B. Mục tiêu 99,95% là SLO, còn cam kết có điều khoản hợp đồng là SLA.
C. Mục tiêu 99,95% là SLA, còn mức bồi thường được gọi là SLO.
D. Cả hai là SLA vì đều dùng cùng dữ liệu để theo dõi chất lượng dịch vụ.
Đáp án đúng: B

Để đo độ khả dụng API thanh toán, nhóm đã xác định tập yêu cầu hợp lệ và coi lỗi nhập liệu của client là ngoài phạm vi; SLI nào phù hợp nhất?
A. Tỷ lệ yêu cầu hợp lệ xử lý thành công trên tổng yêu cầu hợp lệ nhận được.
B. Tỷ lệ HTTP 2xx trên mọi request, kể cả yêu cầu sai định dạng từ client.
C. Tỷ lệ phút máy chủ không khởi động lại trong tổng thời gian đo được.
D. Tỷ lệ request đã tới backend, bỏ qua timeout phát sinh tại proxy.
Đáp án đúng: A

Dịch vụ tìm kiếm đặt SLO 99% yêu cầu hợp lệ phản hồi thành công trong 300 ms; phương pháp đo nào bám sát mục tiêu này nhất?
A. Theo dõi độ trễ trung bình dưới 300 ms trong từng giờ vận hành.
B. Theo dõi p95 của mỗi pod dưới 300 ms tại thời điểm cuối kỳ.
C. Theo dõi tỷ lệ HTTP thành công trên 99% và tách riêng thời gian phản hồi.
D. Đếm tỷ lệ yêu cầu hợp lệ vừa thành công vừa hoàn tất trong 300 ms.
Đáp án đúng: D

Trong 30 ngày có đúng 2.000.000 yêu cầu hợp lệ, SLO độ khả dụng là 99,9%; ngân sách lỗi cho phép tối đa bao nhiêu yêu cầu không đạt?
A. Tối đa 200 yêu cầu không đạt trong tập hai triệu yêu cầu hợp lệ.
B. Tối đa 2.000 yêu cầu không đạt trong tập hai triệu yêu cầu hợp lệ.
C. Tối đa 20.000 yêu cầu không đạt trong tập hai triệu yêu cầu hợp lệ.
D. Tối đa 200.000 yêu cầu không đạt trong tập hai triệu yêu cầu hợp lệ.
Đáp án đúng: B

Một SLO được đánh giá theo cửa sổ trượt 28 ngày và cập nhật mỗi giờ; cách hiểu nào đúng về phạm vi dữ liệu được đánh giá?
A. Mỗi giờ tính lại trên 28 ngày liền trước, không đợi tới cuối tháng.
B. Mỗi giờ kiểm tra cùng một khoảng 28 ngày cố định đã chọn đầu tháng.
C. Tính SLO riêng từng ngày rồi lấy trung bình không trọng số của 28 ngày.
D. Đến cuối ngày thứ 28 mới tính, sau đó dùng kết quả ấy cho cả tháng.
Đáp án đúng: A

Đội vận hành thấy burn rate của SLO đạt mức 8 trong 15 phút; phát biểu nào diễn giải đúng ý nghĩa của chỉ số này?
A. Ngân sách lỗi đang tiêu hao nhanh gấp tám lần tốc độ cho phép theo SLO.
B. Thông lượng hiện tại đang cao gấp tám lần thông lượng mục tiêu của hệ thống.
C. Số yêu cầu thất bại đã bằng tám phần trăm của toàn bộ yêu cầu trong kỳ.
D. Ngân sách lỗi còn lại chỉ đủ cho tám phút hoạt động ở tải hiện tại.
Đáp án đúng: A

Một API có tỷ lệ thành công 99,99% nhưng người dùng thường chờ hơn 5 giây; cấu trúc mục tiêu nào phản ánh trải nghiệm đúng hơn?
A. Giữ SLO thành công vì thời gian phản hồi không thuộc chất lượng dịch vụ.
B. Thay SLO thành công bằng CPU utilization để phát hiện bão hòa sớm hơn.
C. Theo dõi độ trễ trung bình và bỏ SLO thành công để giảm số chỉ tiêu.
D. Dùng SLI/SLO riêng cho kết quả thành công và tỷ lệ phản hồi đúng hạn.
Đáp án đúng: D

Dịch vụ có nhiều pod với lưu lượng khác nhau; để tính p99 toàn dịch vụ từ Prometheus histogram, cách kết hợp nào phù hợp nhất?
A. Tính trung bình số học p99 của từng pod, rồi dùng làm p99 chung cho mọi request.
B. Gộp tốc độ bucket histogram tương thích qua các pod rồi ước lượng p99.
C. Lấy giá trị p99 lớn nhất của các pod để đại diện cho mọi request.
D. Cộng p99 từng pod rồi chia cho tổng số request trong cửa sổ đo.
Đáp án đúng: B

Hệ thống xử lý đơn hàng bất đồng bộ yêu cầu 99% sự kiện hợp lệ hoàn tất trong 60 giây; SLI nào phản ánh chính xác yêu cầu?
A. Tỷ lệ sự kiện được broker xác nhận tiếp nhận mà chưa cần xử lý xong.
B. Tỷ lệ sự kiện hợp lệ hoàn tất xử lý trong 60 giây kể từ khi nhận.
C. Tỷ lệ consumer còn kết nối broker trên tổng consumer đăng ký trong kỳ.
D. Độ sâu trung bình của queue trong giờ cao điểm so với giới hạn cấu hình.
Đáp án đúng: B

Khi backend treo, load balancer trả 504 cho client nhưng metric từ ứng dụng không ghi nhận các request đó; bạn nên cải thiện SLI ra sao?
A. Tính tỷ lệ lỗi dựa trên 5xx do ứng dụng xuất ra, giữ nguyên mẫu số.
B. Đo request đã vào handler để tránh nhiễu do hệ thống mạng trung gian.
C. Lấy số pod bị restart trong kỳ để suy ra tỷ lệ request có trải nghiệm lỗi.
D. Đo tại edge cả timeout và lỗi upstream, đối chiếu với kết quả phía client.
Đáp án đúng: D

Trong một cửa sổ SLO 30 ngày, dịch vụ đã tiêu hao 2% tổng error budget chỉ trong 1 giờ; burn rate trung bình của giờ đó gần bằng bao nhiêu?
A. Khoảng 0,6 lần nhịp tiêu hao error budget được phép trong cả kỳ.
B. Khoảng 7,2 lần nhịp tiêu hao error budget được phép trong cả kỳ.
C. Khoảng 14,4 lần nhịp tiêu hao error budget được phép trong cả kỳ.
D. Khoảng 72 lần nhịp tiêu hao error budget được phép trong cả kỳ.
Đáp án đúng: C

Đội trực muốn phát hiện việc tiêu hao error budget quá nhanh nhưng tránh báo động do vài request lỗi lẻ tẻ; chính sách cảnh báo nào hợp lý hơn?
A. Báo động khi CPU vượt ngưỡng trong 5 phút dù SLI chưa suy giảm.
B. Báo động theo số lỗi tuyệt đối mà không xét lưu lượng, ngân sách hoặc chu kỳ đo.
C. Kết hợp burn rate ở cửa sổ ngắn và dài với điều kiện tiêu hao budget.
D. Báo động sau khi cửa sổ SLO khép lại để loại bỏ nhiễu ngắn hạn.
Đáp án đúng: C

Error budget của SLO đã cạn nhưng nhóm muốn tiếp tục phát hành tính năng rủi ro cao; quyết định nào phù hợp chính sách quản trị độ tin cậy?
A. Tạm hạn chế release rủi ro, ưu tiên độ tin cậy và xét ngoại lệ có kiểm soát.
B. Tiếp tục rollout theo kế hoạch miễn là chưa vi phạm mức cam kết trong SLA.
C. Đổi sang SLI trong một tuần gần nhất để có thêm ngân sách cho đợt phát hành.
D. Đặt lại mốc bắt đầu cửa sổ SLO để đánh giá tính năng mới một cách độc lập.
Đáp án đúng: A

Canary 5% lưu lượng của phiên bản mới có tỷ lệ lỗi cao hơn bản ổn định nhưng SLO 30 ngày vẫn đang đạt; hành động phù hợp nhất là gì?
A. Tiếp tục rollout vì mức SLO tổng thể chưa bị vượt ngưỡng trong 30 ngày.
B. Đẩy nhanh rollout để hai phiên bản không phải chạy đồng thời quá lâu.
C. Đối chiếu SLI theo phiên bản, tạm rollout hoặc rollback theo ngưỡng canary.
D. Theo dõi CPU của phiên bản mới rồi quyết định vì lỗi có thể do tài nguyên.
Đáp án đúng: C

Khi xác lập SLO cho một dịch vụ mới, nhóm được đề xuất đặt 100% độ khả dụng dù chi phí vận hành có hạn; cách lựa chọn nào có cơ sở?
A. Chọn 100% vì tất cả dịch vụ production cần loại bỏ mọi ngân sách lỗi.
B. Chọn bằng đúng SLA vì SLO nội bộ không nên khác mức đã ký với khách hàng.
C. Chọn theo kết quả của một lần kiểm thử tải ở môi trường staging.
D. Chọn từ nhu cầu người dùng, baseline đo được và chi phí tăng độ tin cậy.
Đáp án đúng: D

Hành trình đặt hàng đi qua nhiều dịch vụ và một bước xử lý bất đồng bộ; SLI nào tốt nhất để đo độ tin cậy mà khách hàng cảm nhận?
A. Lấy trung bình số học SLO của mọi dịch vụ trong chuỗi xử lý đơn hàng.
B. Dùng uptime cơ sở dữ liệu vì đa số các bước cần ghi dữ liệu giao dịch.
C. Đo tỷ lệ đơn hàng hoàn tất đúng, đủ và đúng hạn từ đầu đến cuối.
D. Dùng tỷ lệ container đang hoạt động trên tổng container của hệ thống.
Đáp án đúng: C
