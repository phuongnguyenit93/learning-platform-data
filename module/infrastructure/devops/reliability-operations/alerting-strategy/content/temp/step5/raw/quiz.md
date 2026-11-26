Câu 1: API có nhiều lỗi 5xx nhưng CPU các máy vẫn thấp. Tín hiệu nào nên ưu tiên cảnh báo để phản ánh tác động tới người dùng?
A. Theo dõi CPU trung bình của cụm dù yêu cầu vẫn thành công.
B. Theo dõi số lần pod khởi động lại mà không xét lỗi API.
C. Theo dõi tỷ lệ yêu cầu lỗi và kiểm tra lượng yêu cầu liên quan.
D. Theo dõi dung lượng ổ đĩa khi chưa có dấu hiệu bị đầy.
Đáp án đúng: C

Câu 2: Dịch vụ có SLO khả dụng theo tháng và đang dùng error budget quá nhanh. Cách cảnh báo nào phát hiện nguy cơ vượt SLO sớm?
A. Đo tốc độ tiêu hao error budget trên cả cửa sổ ngắn và dài.
B. Chỉ báo khi tỷ lệ lỗi tích lũy cả tháng đã vượt mục tiêu SLO.
C. Chỉ so số lỗi hôm nay với số lỗi trung bình tuần trước.
D. Đặt cảnh báo trên CPU bất kể số request thành công.
Đáp án đúng: A

Câu 3: API có mục tiêu 99% yêu cầu hợp lệ hoàn tất dưới 300 ms. SLI nào trực tiếp đo mức đáp ứng mục tiêu độ trễ?
A. Dùng độ trễ trung bình của mọi request trong năm phút.
B. Dùng tỷ lệ thời gian CPU nằm dưới mức 80% mỗi giờ.
C. Dùng tỷ lệ request hợp lệ hoàn tất dưới ngưỡng 300 ms.
D. Dùng số request thành công nhưng bỏ qua độ trễ thực tế.
Đáp án đúng: C

Câu 4: Cảnh báo hàng đợi bật tắt liên tục khi độ sâu dao động sát ngưỡng 500. Biện pháp nào giảm flapping mà vẫn phát hiện tăng tải?
A. Tăng ngưỡng sau mỗi lần firing mà không kiểm định nguyên nhân tăng tải.
B. Đặt ngưỡng mở và đóng khác nhau, kèm thời gian duy trì.
C. Thay mọi cảnh báo queue depth bằng cảnh báo CPU node.
D. Chỉ đánh giá ngưỡng một lần vào cuối ngày vận hành.
Đáp án đúng: B

Câu 5: Một lỗi kết nối khiến 40 replica phát cùng cảnh báo trong một phút. Cách cấu hình nào giảm trang gọi trùng mà vẫn giữ chi tiết?
A. Tạo một kênh thông báo riêng cho từng replica của dịch vụ.
B. Nhóm theo tên alert và dịch vụ, giữ chi tiết từng replica.
C. Tắt mọi cảnh báo của replica còn lại sau khi có một alert đầu tiên.
D. Giảm chu kỳ scrape của replica để làm ít cảnh báo hơn.
Đáp án đúng: B

Câu 6: Khi database mất kết nối, hàng chục API phụ thuộc báo lỗi theo sau. Muốn giữ cảnh báo database nhưng hạn chế paging thứ cấp, nên dùng gì?
A. Dùng grouping để gộp mọi cảnh báo mà không xét nguyên nhân.
B. Giảm độ nhạy của cảnh báo database tới khi API hồi phục.
C. Tạo silence không thời hạn cho tất cả API đang phụ thuộc.
D. Dùng inhibition theo nhãn phụ thuộc khi cảnh báo gốc firing.
Đáp án đúng: D

Câu 7: Hệ thống có nhiều nhóm trực; cảnh báo của dịch vụ thanh toán nghiêm trọng cần tới đúng nhóm phụ trách ngay. Cấu hình nào phù hợp?
A. Định tuyến theo nhãn service và severity tới lịch trực sở hữu.
B. Gửi về người phát hành phiên bản mới nhất dù họ không nằm trong lịch trực.
C. Gửi mọi cảnh báo đến hộp thư chung và chờ phân công.
D. Định tuyến theo tên node mà không gắn thông tin sở hữu.
Đáp án đúng: A

Câu 8: Dịch vụ đang đạt SLO, nhưng mức dùng ổ đĩa tăng chậm và dự báo đầy sau ba tuần. Nên xử lý cảnh báo mức độ ưu tiên ra sao?
A. Page đội trực ngay với cùng mức khẩn như dịch vụ ngừng chạy.
B. Bỏ qua tới khi ổ đĩa đã đầy để tránh thông báo không cần.
C. Định tuyến tới đội bảo mật vì mức dùng lưu trữ tăng dần.
D. Tạo ticket theo dõi xu hướng thay vì paging khẩn cấp.
Đáp án đúng: D

Câu 9: Một cảnh báo độ trễ API lặp lại vào ban đêm, nhưng người trực không biết kiểm tra từ đâu. Runbook cần bổ sung gì?
A. Các bước xác minh, giảm tác động và leo thang khi chưa xử lý.
B. Danh sách tất cả máy chủ từng được cấp trong dự án.
C. Các sơ đồ thành phần không kèm hướng dẫn phản ứng.
D. Báo cáo chi phí hạ tầng năm trước và tên nhà cung cấp.
Đáp án đúng: A

Câu 10: Đội SRE muốn xác nhận cảnh báo thực sự đi từ hệ thống đo lường tới người trực và cơ chế escalation. Thử nghiệm nào phù hợp?
A. Kiểm tra giao diện dashboard có biểu đồ và dữ liệu mới nhất bình thường.
B. Gửi tin nhắn trực tiếp cho on-call, bỏ qua pipeline alert.
C. Phát cảnh báo thử qua pipeline, kiểm tra nhận và escalation.
D. Xem cấu hình webhook trên Git mà không phát thông báo.
Đáp án đúng: C

Câu 11: Bộ giám sát bị mất kết nối nên không còn gửi cảnh báo khi dịch vụ lỗi. Cách nào phát hiện chính đường cảnh báo đang hỏng?
A. Giảm ngưỡng CPU của dịch vụ để số alert gửi nhiều hơn.
B. Chỉ kiểm tra log dịch vụ khi khách hàng báo không truy cập.
C. Tăng số dashboard để có thêm nơi quan sát tình trạng.
D. Gửi heartbeat định kỳ và báo khi hệ thống nhận bị mất tín hiệu.
Đáp án đúng: D

Câu 12: Trong giờ bảo trì có phê duyệt, một nhóm alert dự kiến firing nhưng các alert khác vẫn phải hoạt động. Cách nào phù hợp?
A. Xóa các alert rule liên quan rồi khôi phục khi bảo trì xong.
B. Tắt tất cả trang gọi của đội trực cho toàn bộ ca bảo trì.
C. Tạo silence giới hạn nhãn, thời hạn, lý do và người chịu trách nhiệm.
D. Đổi severity của mọi alert đang hoạt động thành thông tin.
Đáp án đúng: C

Câu 13: Tỷ lệ lỗi toàn cầu của API thấp nhưng riêng một region có gần 100% lỗi. Cách thiết kế cảnh báo nào tránh che khuất sự cố?
A. Chỉ giám sát tỷ lệ lỗi gộp của toàn bộ region theo cửa sổ dài.
B. Tách SLI và cảnh báo theo region để thấy nơi bị ảnh hưởng.
C. Chỉ theo dõi CPU vùng chính vì lưu lượng tập trung.
D. Đợi tổng lỗi toàn cầu vượt ngưỡng rồi mới phân vùng.
Đáp án đúng: B

Câu 14: Một exporter dừng gửi metric; biểu đồ trống nhưng không có cảnh báo CPU. Cần kiểm soát nào để phát hiện thiếu dữ liệu?
A. Xem mẫu metric bị thiếu như giá trị 0 rồi coi tất cả máy vẫn khỏe.
B. Bỏ nhãn instance khỏi metric để chuỗi dữ liệu ổn định.
C. Giảm số lần thu thập để metric không tạo khoảng trống.
D. Cảnh báo khi mất heartbeat hoặc không còn mẫu metric mong đợi.
Đáp án đúng: D

Câu 15: Số cảnh báo paging giảm sau khi đổi quy tắc, nhưng đội trực vẫn mất nhiều giờ xử lý cảnh báo vô ích. Chỉ số nào đánh giá chất lượng tốt hơn?
A. Đếm tổng số email và trang gọi được gửi thành công ở tất cả kênh.
B. Tỷ lệ page có hành động thực và tỷ lệ cảnh báo nhiễu.
C. Tổng số dashboard đã tạo trong tháng của từng nhóm.
D. Số metric mới đưa vào hệ thống giám sát hằng tuần.
Đáp án đúng: B

Câu 16: Lưu lượng batch tăng định kỳ vào nửa đêm làm ngưỡng CPU tĩnh báo động giả, trong khi SLO vẫn ổn. Hướng cải tiến nào phù hợp?
A. Dựa vào SLO và baseline theo giờ để hiệu chỉnh ngưỡng cảnh báo.
B. Bỏ hoàn toàn cảnh báo CPU vì chỉ số này không ảnh hưởng ứng dụng.
C. Tự nâng ngưỡng CPU sau mỗi lần cảnh báo không cần đánh giá.
D. Chỉ theo dõi CPU trung bình tháng để tránh đỉnh theo ngày.
Đáp án đúng: A
