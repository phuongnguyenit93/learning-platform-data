Bạn xác định mục tiêu kiểm thử hiệu năng của một API Java dựa trên trải nghiệm người dùng và yêu cầu nghiệp vụ như thế nào?
Độ trễ trung bình, trung vị, p95 và p99 phản ánh những khía cạnh khác nhau của hệ thống ra sao?
Khi p99 tăng mạnh nhưng p50 gần như không đổi, bạn sẽ xây dựng giả thuyết điều tra nào?
Bạn phân biệt thông lượng, số người dùng đồng thời và tốc độ yêu cầu đến hệ thống như thế nào?
Bạn sẽ lựa chọn các chỉ số lỗi, timeout và độ ổn định đi kèm chỉ số thời gian phản hồi ra sao?
Một mức p95 tốt trong điều kiện tải nhẹ có thể che giấu vấn đề nào khi lưu lượng tăng?
Bạn xây dựng workload model từ log truy cập và phân bố thao tác thực tế như thế nào?
Khi có cả thao tác đọc và ghi, bạn xác định tỷ trọng yêu cầu để tránh mô phỏng sai hành vi người dùng ra sao?
Bạn phân biệt mô hình tải mở theo arrival rate với mô hình đóng theo số virtual user như thế nào?
Think time và thời gian chờ giữa các bước nghiệp vụ ảnh hưởng thế nào đến kết quả mô phỏng tải?
Bạn sẽ phân biệt kiểm thử load, stress, spike và soak dựa trên mục tiêu cần xác minh như thế nào?
Khi triển khai tính năng mới, bạn thiết kế bài test baseline và ngưỡng chấp nhận ban đầu như thế nào?
Bạn lựa chọn thời gian warm-up, thời lượng giữ tải và giai đoạn giảm tải theo tiêu chí nào?
Nếu số mẫu ở mức tải cao quá ít, bạn đánh giá độ tin cậy của p99 bằng cách nào?
Bạn phát hiện tình trạng coordinated omission hoặc trình tạo tải không đạt tốc độ yêu cầu mục tiêu như thế nào?
Bạn sẽ xác minh máy tạo tải không trở thành nút thắt cổ chai bằng các tín hiệu nào?
Bạn thiết kế dữ liệu kiểm thử để các virtual user không tranh chấp cùng một tài khoản hoặc bản ghi ra sao?
Khi hệ thống có cache, bạn tách phép đo cold cache và warm cache bằng cách nào?
Bạn kiểm soát khác biệt về dữ liệu, cấu hình và tài nguyên giữa môi trường thử nghiệm và production như thế nào?
Nếu phụ thuộc bên ngoài không thể chịu tải kiểm thử, bạn sử dụng mô phỏng phụ thuộc sao cho kết luận còn đáng tin cậy như thế nào?
Bạn tổ chức test plan trong JMeter để mô phỏng chuỗi xác thực, truy vấn và cập nhật dữ liệu ra sao?
Bạn lựa chọn Thread Group, timer và assertion trong JMeter theo yêu cầu tải nào?
Khi báo cáo JMeter cho thấy lỗi tăng đột ngột, bạn sẽ phân biệt lỗi nghiệp vụ với lỗi mạng ra sao?
Bạn diễn đạt kịch bản Gatling bằng DSL và kiểm soát tốc độ injection như thế nào?
Bạn sẽ dùng check và feeder trong Gatling để xác nhận phản hồi và thay đổi dữ liệu đầu vào ra sao?
Bạn tổ chức kịch bản k6 với scenario, executor và threshold theo tiêu chí nghiệm thu như thế nào?
Bạn sử dụng checks, tags và custom metrics trong k6 để phân tích riêng từng hành trình người dùng ra sao?
Khi cùng một workload chạy trên JMeter, Gatling và k6 cho kết quả khác nhau, bạn kiểm tra những sai lệch thiết lập nào?
Bạn sẽ dùng HTTP keep-alive, kết nối TLS và thời gian thiết lập kết nối trong mô hình tải như thế nào?
Bạn đọc biểu đồ response-time histogram để phát hiện hai nhóm yêu cầu có hành vi khác nhau ra sao?
Bạn đối chiếu p95 theo endpoint với p95 toàn hệ thống để tránh kết luận sai như thế nào?
Khi thông lượng dừng tăng dù số người dùng tiếp tục tăng, bạn sẽ xác định điểm bão hòa ra sao?
Bạn áp dụng mối quan hệ giữa số yêu cầu đồng thời, thông lượng và thời gian đáp ứng để kiểm tra tính hợp lý của số liệu như thế nào?
Bạn chọn chỉ số CPU, heap, garbage collection và thread pool để ghép với thời điểm độ trễ tăng ra sao?
Trong Java Flight Recorder, bạn sẽ tìm bằng chứng nào để xác định điểm nóng CPU hoặc allocation?
Bạn phân biệt dấu hiệu nghẽn lock với nghẽn I/O qua JFR, thread dump và metrics như thế nào?
Bạn phát hiện connection pool tới database bị cạn hoặc truy vấn chậm bằng những tín hiệu nào?
Khi tỷ lệ timeout tăng cùng độ dài hàng đợi, bạn đánh giá vai trò của backpressure và giới hạn đồng thời ra sao?
Bạn sử dụng distributed tracing ra sao để xác định bước xử lý gây tăng độ trễ cuối chuỗi?
Khi p99 xấu đi sau một thay đổi GC hoặc cấu hình JVM, bạn sẽ thiết kế thử nghiệm đối chứng ra sao?
Bạn so sánh hai phiên bản ứng dụng như thế nào để tránh nhiễu do khác cấu hình, cỡ mẫu và thời điểm đo?
Bạn xác định ý nghĩa thống kê và ý nghĩa nghiệp vụ của một thay đổi độ trễ nhỏ bằng cách nào?
Bạn sẽ điều tra ảnh hưởng của autoscaling, tải nền và hạn mức container lên kết quả kiểm thử ra sao?
Khi kiểm thử chạy dài hạn phát hiện bộ nhớ tăng đều, bạn phân biệt leak với cache hoặc trạng thái tích lũy như thế nào?
Bạn lựa chọn tiêu chí dừng bài stress test khi hệ thống bắt đầu có nguy cơ ảnh hưởng tới tài nguyên dùng chung ra sao?
Bạn sẽ đưa kiểm thử hiệu năng định kỳ vào CI mà vẫn quản lý chi phí và độ biến động của kết quả như thế nào?
Khi một bản build vượt ngưỡng p95 nhưng kết quả không ổn định, bạn kiểm tra lại trước khi quyết định chặn phát hành ra sao?
Bạn trình bày báo cáo hiệu năng với tải, phiên bản, lỗi, p95/p99 và bằng chứng nút thắt như thế nào?
Sau khi tối ưu truy vấn hoặc cache, bạn xác minh cải thiện có giữ được dưới nhiều mức tải như thế nào?
Bạn thiết kế bộ tiêu chí phát hành kết hợp thông lượng, độ trễ đuôi, tỷ lệ lỗi và mức tiêu thụ tài nguyên ra sao?
