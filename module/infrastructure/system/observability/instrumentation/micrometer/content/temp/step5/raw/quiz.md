Câu 1. Micrometer đóng vai trò nào trong ứng dụng Java cần quan sát metrics?
A. Thay thế toàn bộ hệ thống lưu trữ time series
B. Thực thi truy vấn PromQL tại tiến trình Java
C. Cung cấp API đo lường độc lập với backend giám sát
D. Đảm nhiệm gửi cảnh báo trực tiếp tới on-call
Đáp án đúng: C

Câu 2. Vai trò chính của `MeterRegistry` trong Micrometer là gì?
A. Đăng ký, tra cứu và quản lý các meter của ứng dụng
B. Khởi tạo mọi span tracing trong hệ phân tán
C. Lưu vĩnh viễn các metric vào ổ đĩa cục bộ
D. Định tuyến mọi HTTP request của ứng dụng Java
Đáp án đúng: A

Câu 3. Khi đếm số lần xử lý một đơn hàng thành công, nên dùng meter nào?
A. `LongTaskTimer` để tăng số sự kiện đã xảy ra
B. `Counter` để tăng số sự kiện đã xảy ra
C. `Gauge` để tăng số sự kiện đã xảy ra
D. `Timer` để tăng số sự kiện đã xảy ra
Đáp án đúng: B

Câu 4. Tính chất nào đúng với `Counter` của Micrometer?
A. Giá trị chỉ tăng khi ghi nhận số dương
B. Giá trị có thể tăng và giảm tùy phép đo
C. Giá trị luôn trở về không sau mỗi scrape
D. Giá trị luôn bằng số request đang xử lý
Đáp án đúng: A

Câu 5. Để hiển thị số phần tử hiện tại trong một hàng đợi, nên dùng gì?
A. `DistributionSummary` quan sát độ dài hàng đợi
B. `Counter` quan sát kích thước hàng đợi hiện tại
C. `Gauge` quan sát kích thước hàng đợi hiện tại
D. `Timer` quan sát kích thước hàng đợi hiện tại
Đáp án đúng: C

Câu 6. Khi gắn `Gauge` vào một object, điều gì cần chú ý về vòng đời object?
A. Xóa object ngay sau khi đăng ký meter xong
B. Giữ object chỉ trong một hàm static cục bộ
C. Buộc object thành chuỗi trước khi tạo Gauge
D. Giữ tham chiếu mạnh nếu cần object tồn tại
Đáp án đúng: D

Câu 7. Tính năng nào mô tả đúng `Timer` trong Micrometer?
A. Đo số lượng tác vụ hiện vẫn đang chạy
B. Đo giá trị hiện tại của một biến trong heap
C. Đo số lần và tổng số byte của các payload
D. Đo số lần và tổng thời lượng các thao tác
Đáp án đúng: D

Câu 8. Cách sử dụng `Timer` nào phù hợp để đo một đoạn xử lý?
A. Gọi `registry.clear` trước công việc cần đo
B. Gọi `counter.increment` với thời lượng đo
C. Gọi `timer.record` với công việc cần đo
D. Gọi `gauge.value` với công việc cần đo
Đáp án đúng: C

Câu 9. `Timer.Sample` phù hợp với trường hợp nào khi ghi duration?
A. Bắt đầu đo rồi chọn timer gắn nhãn khi dừng
B. Bắt đầu đo rồi tự động xóa mọi meter khi dừng
C. Bắt đầu đo rồi tự tạo PromQL rule khi dừng
D. Bắt đầu đo rồi đổi thành gauge sau khi dừng
Đáp án đúng: A

Câu 10. Muốn đo phân bố kích thước payload theo byte thay vì thời lượng, nên dùng gì?
A. `DistributionSummary` ghi các kích thước payload
B. `LongTaskTimer` ghi các kích thước payload
C. `Timer` ghi các kích thước payload
D. `Counter` ghi các kích thước payload
Đáp án đúng: A

Câu 11. `LongTaskTimer` khác `Timer` ở nhu cầu quan sát nào?
A. Theo dõi tổng số byte phản hồi đã ghi
B. Theo dõi bộ nhớ heap còn trống hiện tại
C. Theo dõi tác vụ kéo dài còn đang chạy
D. Theo dõi số kết nối TCP đã từng mở
Đáp án đúng: C

Câu 12. Khi đo kích thước message bằng `DistributionSummary`, base unit phù hợp là gì?
A. Chọn `requests` cho kích thước message
B. Chọn `threads` cho kích thước message
C. Chọn `bytes` cho kích thước message
D. Chọn `seconds` cho kích thước message
Đáp án đúng: C

Câu 13. Một tag trong Micrometer được biểu diễn theo hình thức nào?
A. Cặp timestamp–sample của một counter
B. Cặp endpoint–port trong bảng route
C. Cặp start–stop của một Timer.Sample
D. Cặp tên–giá trị gắn cùng một meter
Đáp án đúng: D

Câu 14. Bộ tag nào phù hợp nhất để kiểm soát cardinality cho HTTP metrics?
A. Trace ID và timestamp đổi theo từng lần gọi
B. Raw URL kèm query token đổi theo từng người dùng
C. Method và route template có tập giá trị hữu hạn
D. User ID và request ID thay đổi liên tục từng lần
Đáp án đúng: C

Câu 15. Tại sao không nên dùng `userId` làm tag của request counter?
A. Nhiều giá trị tag tạo số chuỗi metric tăng mạnh
B. Counter không được phép dùng bất kỳ tag nào
C. Tag chỉ hỗ trợ giá trị số thay vì chuỗi ký tự
D. Prometheus luôn gộp mọi giá trị userId làm một
Đáp án đúng: A

Câu 16. Với route `/orders/{id}`, chọn giá trị tag `uri` nào nên dùng?
A. Đường dẫn thực `/orders/8391` của request
B. Mẫu đường dẫn `/orders/{id}` của endpoint
C. Toàn bộ URL có access token trong query
D. Mã định danh request biến đổi mỗi lần gọi
Đáp án đúng: B

Câu 17. `commonTags` trên registry dùng cho nhu cầu nào?
A. Thêm tập HTTP header vào mỗi lần exporter scrape
B. Thêm tập tag chung vào các meter được đăng ký
C. Thêm tập mẫu dữ liệu vào các counter đang tồn tại
D. Thêm tập alert rule vào file Prometheus cấu hình
Đáp án đúng: B

Câu 18. `MeterFilter.deny` thường dùng để thực hiện việc gì?
A. Thay đổi dữ liệu lịch sử của mọi meter đã xuất
B. Tự động kéo dài mọi timer vượt một ngưỡng
C. Chuyển metric sang một hệ lưu trữ khác
D. Ngăn đăng ký những meter khớp chính sách lọc
Đáp án đúng: D

Câu 19. Khi một tag có quá nhiều giá trị, `MeterFilter.maximumAllowableTags` giúp gì?
A. Đổi mọi counter sang gauge khi vượt cardinality
B. Giới hạn lượng giá trị tag được chấp nhận
C. Giảm trực tiếp số request HTTP tại gateway
D. Tự gom các nhãn thành một time series duy nhất
Đáp án đúng: B

Câu 20. Hai meter có cùng tên và cùng tập tag trong một registry thường thế nào?
A. Luôn biến thành hai dạng type khác nhau
B. Tham chiếu tới cùng một meter đã đăng ký
C. Luôn tạo hai meter tách biệt với cùng ID
D. Luôn ghi một bản ghi metric mới cho mỗi lần gọi
Đáp án đúng: B

Câu 21. Bật histogram cho `Timer` thường phục vụ mục tiêu nào?
A. Thu số thread để tính active task count
B. Thu packet loss để đánh giá đường truyền
C. Thu payload byte để gán thành histogram
D. Thu bucket để tổng hợp phân bố latency
Đáp án đúng: D

Câu 22. Ưu điểm của histogram bucket so với percentile tính sẵn từng instance là gì?
A. Percentile riêng luôn có độ phân giải tốt hơn
B. Percentile riêng có thể cộng trực tiếp không sai
C. Bucket không làm tăng số time series metric
D. Bucket có thể cộng gộp giữa nhiều instance
Đáp án đúng: D

Câu 23. Đánh đổi chính khi bật nhiều histogram bucket là gì?
A. Giảm số chuỗi thời gian và bộ nhớ sử dụng
B. Loại bỏ hoàn toàn chi phí tính toán metrics
C. Tăng số chuỗi thời gian và chi phí lưu trữ
D. Đổi mọi Counter đang có thành Gauge tự động
Đáp án đúng: C

Câu 24. `publishPercentileHistogram()` trong cấu hình phân phối có tác dụng gì?
A. Cho phép tự tạo Alertmanager receiver mới
B. Cho phép xuất bucket dùng ước lượng quantile
C. Cho phép ghi sample thành log có cấu trúc
D. Cho phép tạo bản ghi tracing cho mọi request
Đáp án đúng: B

Câu 25. Các ngưỡng SLO cấu hình cho `Timer` hỗ trợ việc gì?
A. Đổi timeout HTTP cho mọi endpoint liên quan
B. Đổi điều kiện pending của alert rule Prometheus
C. Đếm mẫu thời lượng nằm trong các bucket ngưỡng
D. Đếm số người dùng duy nhất theo mỗi service
Đáp án đúng: C

Câu 26. Trong Spring Boot, endpoint Actuator nào thường hiển thị danh sách metric và số đo?
A. `/actuator/env` cung cấp thông tin metric
B. `/actuator/metrics` cung cấp thông tin metric
C. `/actuator/beans` cung cấp thông tin metric
D. `/actuator/health` cung cấp thông tin metric
Đáp án đúng: B

Câu 27. Để Prometheus scrape Spring Boot Actuator, endpoint nào thường được dùng?
A. `/actuator/prometheus` để xuất định dạng scrape
B. `/actuator/info` để xuất định dạng scrape
C. `/actuator/metrics` để xuất định dạng scrape
D. `/actuator/health` để xuất định dạng scrape
Đáp án đúng: A

Câu 28. Thư viện nào thường cần cho ứng dụng Spring Boot xuất metrics sang Prometheus?
A. Dependency `micrometer-registry-influx`
B. Dependency `micrometer-registry-statsd`
C. Dependency `micrometer-registry-jmx`
D. Dependency `micrometer-registry-prometheus`
Đáp án đúng: D

Câu 29. Nếu endpoint Prometheus của Actuator chưa được web expose, cấu hình nào phù hợp?
A. `management.endpoints.web.exposure.include=info`
B. `management.endpoints.web.exposure.include=metrics`
C. `management.endpoints.web.exposure.include=health`
D. `management.endpoints.web.exposure.include=prometheus`
Đáp án đúng: D

Câu 30. Khi dùng Prometheus pull model với Micrometer registry, dữ liệu được lấy như thế nào?
A. Ứng dụng luôn push từng counter tới Prometheus
B. Prometheus chủ động scrape endpoint metrics
C. Alertmanager chủ động scrape ứng dụng Java
D. Spring Boot bắt buộc gửi metric qua UDP socket
Đáp án đúng: B

Câu 31. Tên metric `http.server.requests` khi xuất qua Prometheus thường được chuẩn hóa thế nào?
A. Dấu chấm được đổi thành dấu gạch ngang
B. Dấu chấm được đổi thành dấu gạch dưới
C. Dấu chấm được đổi thành dấu hai chấm
D. Dấu chấm được giữ nguyên ở tên metric
Đáp án đúng: B

Câu 32. Counter xuất theo quy ước Prometheus thường có hậu tố nào?
A. Hậu tố `_total` cho số đếm tích lũy
B. Hậu tố `_created` cho số đếm tích lũy
C. Hậu tố `_bucket` cho số đếm tích lũy
D. Hậu tố `_sum` cho số đếm tích lũy
Đáp án đúng: A

Câu 33. Trong histogram Prometheus dạng classic, chuỗi `_bucket` mô tả điều gì?
A. Số mẫu tích lũy không vượt quá ranh giới bucket
B. Tổng thời lượng đo của tất cả các request
C. Tổng số lần metric bị reset kể từ lúc chạy
D. Số mẫu hiện có đúng trong duy nhất một bucket
Đáp án đúng: A

Câu 34. `Timer` có thể xuất count và sum để tính trung bình thời lượng bằng cách nào?
A. Lấy số label chia cho tổng số phép đo
B. Lấy tổng duration chia cho tổng số phép đo
C. Lấy tổng duration nhân với tổng số phép đo
D. Lấy số bucket chia cho tổng số phép đo
Đáp án đúng: B

Câu 35. Khi xem counter Prometheus, vì sao thường dùng `rate()` thay cho giá trị thô?
A. Để ước lượng tốc độ tăng theo thời gian
B. Để xem kích thước hiện tại của hàng đợi
C. Để lấy giá trị trung bình của gauge tức thời
D. Để đếm số label hiện có trên từng target
Đáp án đúng: A

Câu 36. `rate(counter[5m])` trong PromQL xử lý restart làm counter reset như thế nào?
A. Luôn bỏ qua tất cả sample trước lần restart
B. Luôn đổi counter thành gauge trước khi tính
C. Ước lượng tốc độ có xét trường hợp counter reset
D. Coi mọi giá trị giảm là một sự kiện âm thực tế
Đáp án đúng: C

Câu 37. Vì sao Gauge không thích hợp thay Counter để đếm mọi sự kiện đã xảy ra?
A. Gauge giữ tổng tích lũy của mọi sự kiện
B. Gauge phản ánh trạng thái tại lúc lấy mẫu
C. Gauge chỉ tăng và không bao giờ được giảm
D. Gauge luôn lưu đầy đủ lịch sử từng sự kiện
Đáp án đúng: B

Câu 38. Để đo riêng số lần gọi và latency của cùng thao tác, nên bắt đầu với meter nào?
A. `Counter` có cả count và thời lượng của thao tác
B. `FunctionCounter` có cả count và thời lượng
C. `Gauge` có cả count và thời lượng của thao tác
D. `Timer` có cả count và thời lượng của thao tác
Đáp án đúng: D

Câu 39. Khi chọn tag cho metric lỗi API, tổ hợp nào thường dễ vận hành nhất?
A. Raw URL và timestamp chính xác từng request
B. Nội dung stack trace và request ID ngẫu nhiên
C. Email người dùng và access token thực tế
D. Loại lỗi hữu hạn và tên service ổn định
Đáp án đúng: D

Câu 40. Trong test instrumentation, `SimpleMeterRegistry` hữu ích ở điểm nào?
A. Khởi động hẳn một Prometheus server test
B. Chạy toàn bộ truy vấn PromQL trong unit test
C. Đọc meter và số đo ngay trong unit test
D. Tự cấu hình Alertmanager receiver giả lập
Đáp án đúng: C

Câu 41. Muốn xác minh `Counter` tăng hai lần trong test, nên assert dữ liệu nào?
A. Giá trị `count()` sau hai lần increment
B. Giá trị `activeTasks()` sau hai lần increment
C. Giá trị `totalTime()` sau hai lần increment
D. Giá trị `max()` sau hai lần increment
Đáp án đúng: A

Câu 42. Muốn test `Timer` đã ghi một lần đo thành công, nên kiểm tra gì?
A. `count()` tăng và `totalTime()` có giá trị
B. `count()` giảm và `totalTime()` giữ nguyên
C. `count()` giữ nguyên và `activeTasks()` tăng
D. `count()` về không và `max()` chưa được tạo
Đáp án đúng: A

Câu 43. Khi thêm metric mới vào ứng dụng, kiểm thử cardinality nên tập trung vào điều gì?
A. Số lượng response header trên HTTP client
B. Số dòng cấu hình được khai báo trong YAML
C. Số bộ giá trị tag sinh ra khi tải thực thay đổi
D. Độ dài chuỗi tên biến Java trong từng lớp
Đáp án đúng: C

Câu 44. Khi latency p99 xấu nhưng latency trung bình ổn, nên diễn giải thế nào?
A. Tất cả histogram bucket đều đã bị xóa
B. Toàn bộ request đều chậm tương đương nhau
C. Các counter chắc chắn bị reset khi server chạy
D. Một nhóm nhỏ request chậm bị trung bình che khuất
Đáp án đúng: D
