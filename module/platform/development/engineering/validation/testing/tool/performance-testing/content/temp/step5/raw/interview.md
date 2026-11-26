Bạn phân biệt mục tiêu kiểm thử hiệu năng với kiểm thử chức năng khi đánh giá chất lượng một hệ thống như thế nào?
Bạn xác định các yêu cầu phi chức năng về latency, throughput và error rate từ nhu cầu người dùng thực tế ra sao?
Bạn lựa chọn hành trình nghiệp vụ nào làm kịch bản phát tải khi hệ thống có nhiều endpoint và nguồn lực kiểm thử hạn chế?
Bạn biến số liệu truy cập production thành phân bố loại request, số người dùng và thời điểm cao điểm như thế nào?
Bạn phân biệt concurrent users, requests per second và transactions per second để tránh mô hình hóa tải sai ra sao?
Bạn so sánh open workload với closed workload và giải thích hệ quả của mỗi mô hình khi thời gian đáp ứng tăng như thế nào?
Bạn lựa chọn arrival rate và think time phù hợp để mô phỏng hành vi thật mà không tạo tải phi thực tế ra sao?
Bạn thiết kế các pha warm-up, ramp-up, steady-state và ramp-down để kết quả có thể giải thích như thế nào?
Bạn phân biệt load test, stress test, spike test và soak test qua câu hỏi thực nghiệm mà mỗi loại cần trả lời ra sao?
Bạn chọn mức tải mục tiêu và các bước tăng tải để phát hiện điểm bão hòa mà không làm hỏng môi trường dùng chung như thế nào?
Bạn lập kịch bản có hỗn hợp đọc, ghi và tìm kiếm để phản ánh đúng phân bố công việc thay vì chỉ gọi một API ra sao?
Bạn quyết định tỉ lệ dữ liệu mới, dữ liệu lặp và dữ liệu không tồn tại khi chuẩn bị bài kiểm thử truy vấn như thế nào?
Bạn xây dựng dữ liệu thử đủ lớn để tránh kết quả bị lệch vì mọi thứ đều nằm trong cache như thế nào?
Bạn bảo đảm mỗi virtual user dùng token, giỏ hàng hoặc trạng thái phiên riêng để không tạo tranh chấp ngoài ý muốn ra sao?
Bạn xử lý đăng nhập và làm mới token trong công cụ phát tải mà không để chi phí xác thực làm sai mục tiêu đo như thế nào?
Bạn chọn dùng JMeter, k6 hoặc Gatling dựa trên nhu cầu scripting, chạy CI, khả năng mở rộng và kỹ năng nhóm như thế nào?
Bạn thiết kế script phát tải có thể tái sử dụng, tham số hóa và kiểm soát phiên bản cùng mã ứng dụng ra sao?
Bạn kiểm tra công cụ phát tải có thực sự đạt target throughput hay chính nó đã trở thành nút thắt như thế nào?
Bạn quyết định khi nào phải phân tán load generator sang nhiều máy và đồng bộ thời gian giữa chúng ra sao?
Bạn phân biệt thời gian phía client quan sát được với thời gian xử lý nội bộ của server bằng các phép đo nào?
Bạn giải thích vì sao average latency có thể che giấu trải nghiệm xấu của nhóm request chậm như thế nào?
Bạn đọc p50, p90, p95 và p99 latency để xác định mức độ phân tán độ trễ và các ngoại lệ như thế nào?
Bạn xác định cỡ mẫu, thời lượng đo và số lần lặp để percentile ít bị dao động ngẫu nhiên như thế nào?
Bạn xử lý request timeout hoặc thất bại khi tính latency để không có báo cáo nhanh giả tạo do chỉ lấy các request thành công ra sao?
Bạn xây dựng tiêu chí đạt dựa trên đồng thời latency percentile, throughput và tỷ lệ lỗi thay vì nhìn một chỉ số đơn lẻ như thế nào?
Bạn phát hiện coordinated omission khi load generator giảm tốc do server chậm và điều chỉnh cách đo như thế nào?
Bạn phân tích hiện tượng throughput không tăng nhưng latency tăng mạnh khi thêm virtual user để xác định ngưỡng bão hòa ra sao?
Bạn phân biệt lỗi HTTP 4xx, 5xx, timeout và lỗi kết nối trong báo cáo tải theo ý nghĩa nghiệp vụ như thế nào?
Bạn xác minh một request trả HTTP 200 nhưng dữ liệu sai vẫn phải được tính là lỗi kịch bản bằng cách nào?
Bạn thiết kế quy tắc kiểm tra response đủ mạnh để phát hiện lỗi dưới tải mà không khiến load generator tốn quá nhiều CPU ra sao?
Bạn thiết lập correlation ID và log sampling để nối các request chậm với trace phía server như thế nào?
Bạn giám sát CPU, bộ nhớ, garbage collection, thread pool và connection pool khi tải tăng theo những tín hiệu nào?
Bạn phân biệt CPU saturation với thời gian chờ I/O khi latency tăng mà CPU không cao như thế nào?
Bạn đọc metric của database như số connection, lock wait, truy vấn chậm và hàng đợi ghi để tìm nút thắt như thế nào?
Bạn kiểm tra ảnh hưởng của cache hit ratio và cache eviction đến p95 latency dưới tải có dữ liệu đa dạng ra sao?
Bạn nhận diện tình huống một downstream service chậm làm hàng đợi request phình to và gây lỗi dây chuyền như thế nào?
Bạn phân tích việc tăng thread pool có thể làm tình trạng tranh chấp tài nguyên tệ hơn trong điều kiện nào?
Bạn đánh giá hiệu ứng của rate limiting và backpressure khi hệ thống vượt quá khả năng xử lý theo tiêu chí nào?
Bạn kiểm thử hiệu năng cơ chế retry khi một số request thất bại để phát hiện khuếch đại tải ngoài ý muốn ra sao?
Bạn đo ảnh hưởng của database transaction kéo dài hoặc lock contention lên tail latency bằng cách nào?
Bạn thiết kế soak test để phát hiện rò rỉ bộ nhớ, kết nối hoặc suy giảm thông lượng theo thời gian như thế nào?
Bạn xử lý tác động của autoscaling, cache warm-up và background job lên độ ổn định của phép đo ra sao?
Bạn mô tả cách thực hiện một baseline đáng tin cậy trước khi thay đổi index hoặc thuật toán để có cơ sở so sánh như thế nào?
Bạn giữ ổn định dữ liệu, cấu hình máy, phiên bản phần mềm và điều kiện mạng khi chạy phép thử trước và sau thay đổi ra sao?
Bạn dùng nhiều lần đo để xác nhận cải thiện hiệu năng sau tối ưu và phân biệt với biến thiên ngẫu nhiên ra sao?
Bạn kiểm tra trường hợp tối ưu p95 latency nhưng làm tăng tỷ lệ lỗi hoặc dùng nhiều tài nguyên hơn bằng cách nào?
Bạn nhận diện giới hạn của môi trường staging nhỏ hơn production và diễn giải mức độ chuyển giao kết quả như thế nào?
Bạn chọn những kịch bản kiểm thử hiệu năng nhẹ phù hợp chạy trên pull request và kịch bản nặng nên chạy theo lịch như thế nào?
Bạn tích hợp công cụ phát tải vào CI để lưu kết quả, so sánh baseline và tạo báo cáo tự động ra sao?
Bạn thiết kế ngưỡng cảnh báo hồi quy hiệu năng trong CI để tránh fail liên tục do nhiễu từ môi trường chia sẻ như thế nào?
Bạn thu thập artefact như script, commit, biểu đồ latency, log và cấu hình để một lần kiểm thử có thể tái lập ra sao?
Những tín hiệu nào cho thấy cần dừng một đợt stress test để tránh ảnh hưởng đến hệ thống dùng chung?
Bạn trình bày đồ thị tải, latency, throughput, lỗi và tài nguyên theo cùng trục thời gian để giải thích bottleneck ra sao?
Bạn ưu tiên xử lý nút thắt ở ứng dụng, database hoặc hạ tầng bằng chứng nào thay vì điều chỉnh cấu hình theo cảm tính?
Bạn đề xuất kế hoạch kiểm thử lặp lại sau mỗi lần tối ưu để xác nhận cải thiện và tránh dịch chuyển nút thắt sang thành phần khác như thế nào?
