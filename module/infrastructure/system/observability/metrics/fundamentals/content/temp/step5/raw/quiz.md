Câu 1. Counter phù hợp nhất để đo đại lượng nào?
A. Tổng số sự kiện đã xảy ra kể từ khi chạy
B. Số tác vụ hiện đang chờ xử lý
C. Thời lượng của từng request được ghi nhận
D. Giá trị hiện tại của hàng đợi
Đáp án đúng: A

Câu 2. Tính chất nào đúng với Counter đơn điệu?
A. Chỉ tăng trong vòng đời tiến trình
B. Giá trị luôn bằng số tác vụ đang chạy
C. Giá trị biểu diễn thời gian mỗi thao tác
D. Giá trị tăng hoặc giảm theo trạng thái
Đáp án đúng: A

Câu 3. Gauge phù hợp với loại đại lượng nào?
A. Phân bố thời lượng qua các bucket tích lũy
B. Tổng số sự kiện chỉ tăng dần theo thời gian
C. Tốc độ tăng counter trên một cửa sổ thời gian
D. Giá trị thay đổi theo trạng thái hiện tại
Đáp án đúng: D

Câu 4. Đại lượng nào thường được instrument bằng Gauge?
A. Tổng số request hoàn tất kể từ khi chạy
B. Số lỗi tích lũy kể từ lần khởi động
C. Tổng thời lượng của các request hoàn tất
D. Số request đang xử lý tại thời điểm đo
Đáp án đúng: D

Câu 5. Histogram chủ yếu ghi nhận thông tin nào?
A. Số instance đang được scrape
B. Phân bố các quan sát qua nhiều bucket
C. Một quantile duy nhất tại mỗi instance
D. Từng quan sát dưới dạng nhãn riêng
Đáp án đúng: B

Câu 6. Trong classic histogram, bucket có nhãn `le="0.5"` biểu thị điều gì?
A. Số quan sát có giá trị lớn hơn hoặc bằng 0.5
B. Số quan sát có giá trị đúng bằng 0.5
C. Số quan sát không vượt quá ngưỡng 0.5
D. Tổng thời gian của các quan sát vượt 0.5
Đáp án đúng: C

Câu 7. Summary thường cung cấp loại kết quả nào bên cạnh count và sum?
A. Giá trị gauge hiện tại của từng instance
B. Tỷ lệ tăng counter trên một cửa sổ
C. Bucket tích lũy có thể cộng qua mọi instance
D. Quantile tính tại nơi ghi nhận quan sát
Đáp án đúng: D

Câu 8. Vì sao quantile của Summary khó tổng hợp giữa nhiều instance?
A. Summary không ghi nhận số lượng quan sát
B. Count và sum không thể cộng qua các instance
C. Quantile riêng lẻ không thể cộng gộp chính xác
D. Mỗi quantile luôn đại diện toàn bộ cluster
Đáp án đúng: C

Câu 9. Một time series thường được định danh bởi thành phần nào?
A. Tên metric cùng đơn vị đo của ứng dụng
B. Tên metric cùng kiểu dữ liệu gốc của host
C. Tên metric cùng timestamp của mẫu gần nhất
D. Tên metric cùng toàn bộ tập nhãn của nó
Đáp án đúng: D

Câu 10. Label trong mô hình metrics thường dùng để làm gì?
A. Đặt chu kỳ scrape cho từng exporter
B. Phân chiều dữ liệu thành các chuỗi riêng biệt
C. Lưu mọi sample lịch sử bên trong một chuỗi
D. Thay thế timestamp trên từng điểm dữ liệu
Đáp án đúng: B

Câu 11. Cardinality của metric tăng khi nào?
A. Khi một metric có nhiều sample theo thời gian
B. Khi chu kỳ scrape dài hơn giữa các lần lấy mẫu
C. Khi số tổ hợp tên metric và giá trị nhãn tăng
D. Khi một dashboard có thêm nhiều biểu đồ
Đáp án đúng: C

Câu 12. Vì sao `user_id` thường là label rủi ro cho request metric?
A. Giá trị user thay đổi lớn làm tăng số time series
B. Label user làm counter tự giảm sau mỗi scrape
C. Giá trị user khiến timestamp bị xóa khỏi sample
D. Prometheus chỉ chấp nhận label chứa chữ số
Đáp án đúng: A

Câu 13. Một sample Prometheus thông thường gồm thành phần nào?
A. Tên dashboard và khoảng thời gian truy vấn
B. Giá trị số và timestamp gắn với time series
C. Địa chỉ exporter và cổng TCP đang mở
D. Trạng thái alert và tên receiver đích
Đáp án đúng: B

Câu 14. Scrape interval quá ngắn thường gây đánh đổi nào?
A. Loại bỏ hoàn toàn các đợt spike ngắn
B. Giảm số lần evaluation của alert rule
C. Giảm cardinality của mọi metric tự động
D. Tăng chi phí thu thập và lưu trữ mẫu
Đáp án đúng: D

Câu 15. `rate(requests_total[5m])` thường trả về đại lượng nào?
A. Phân vị request trong năm phút vừa qua
B. Tốc độ tăng counter trung bình mỗi giây
C. Tổng request tuyệt đối trong toàn bộ vòng đời
D. Giá trị request hiện tại tại lần scrape cuối
Đáp án đúng: B

Câu 16. Vì sao thường áp dụng `rate()` trước phép `sum()` trên counter?
A. Để cộng timestamp trước khi chuẩn hóa đơn vị
B. Để chuyển mọi gauge thành counter tích lũy
C. Để xử lý reset riêng từng chuỗi trước khi cộng
D. Để loại bỏ label trước khi tính tốc độ
Đáp án đúng: C

Câu 17. `increase(errors_total[1h])` chủ yếu ước lượng điều gì?
A. Số chuỗi time series mới trong một giờ
B. Tốc độ counter tăng tại một giây cuối
C. Giá trị gauge trung bình trong một giờ
D. Lượng counter tăng trong một giờ
Đáp án đúng: D

Câu 18. Hàm `rate()` xử lý counter reset trong cửa sổ thế nào?
A. Coi phần giảm là lượng sự kiện âm thực tế
B. Loại bỏ toàn bộ mẫu sau lần reset đầu
C. Điều chỉnh phép tính khi phát hiện counter giảm
D. Chuyển chuỗi counter thành gauge tạm thời
Đáp án đúng: C

Câu 19. `irate(counter[5m])` khác `rate(counter[5m])` chủ yếu ở điểm nào?
A. `irate` trả tổng counter từ lúc khởi động
B. `irate` dùng hai mẫu gần nhất trong cửa sổ
C. `irate` tính trung bình của mọi gauge
D. `irate` cộng toàn bộ mẫu trong cửa sổ
Đáp án đúng: B

Câu 20. `avg_over_time(queue_depth[10m])` phù hợp để tính gì?
A. Phân vị p95 của histogram trong mười phút
B. Giá trị trung bình của gauge trong mười phút
C. Lượng tăng của counter trong mười phút
D. Tốc độ scrape trung bình trong mười phút
Đáp án đúng: B

Câu 21. `sum by (service) (rate(requests_total[5m]))` nhóm kết quả theo gì?
A. Giữ timestamp và cộng các tên metric
B. Giữ mọi nhãn và tách từng chuỗi riêng
C. Giữ nhãn service và cộng các chiều còn lại
D. Giữ nhãn instance và bỏ nhãn service
Đáp án đúng: C

Câu 22. Vì sao phép so sánh `queue_depth == 0` không phát hiện metric bị mất?
A. Chuỗi không tồn tại vẫn giữ giá trị gần nhất
B. Chuỗi không tồn tại tạo kết quả rỗng
C. Chuỗi không tồn tại luôn được coi là số không
D. Chuỗi không tồn tại tự sinh một sample mới
Đáp án đúng: B

Câu 23. Hàm `absent(metric_name)` hữu ích trong trường hợp nào?
A. Phát hiện chuỗi có giá trị bằng không
B. Phát hiện counter vừa giảm sau reset
C. Phát hiện gauge vượt ngưỡng cấu hình
D. Phát hiện không có chuỗi nào khớp biểu thức
Đáp án đúng: D

Câu 24. Khi dùng `histogram_quantile`, nhãn nào cần giữ để tính classic histogram?
A. Nhãn `le` biểu thị ranh giới của bucket
B. Nhãn `job` biểu thị tên của exporter
C. Nhãn `version` biểu thị bản phát hành ứng dụng
D. Nhãn `instance` biểu thị máy đang scrape
Đáp án đúng: A

Câu 25. Vì sao bucket histogram có thể tổng hợp qua nhiều instance?
A. Bucket cùng ranh giới có thể cộng số đếm
B. Quantile đã tính sẵn có thể cộng trực tiếp
C. Mỗi bucket luôn chứa đúng một quan sát
D. Bucket lưu danh sách ID của từng instance
Đáp án đúng: A

Câu 26. Điều nào đúng khi tổng hợp quantile đã xuất từ Summary?
A. Quantile per-instance luôn có cùng phân bố
B. Quantile per-instance không thể gộp chính xác
C. Quantile per-instance chính là bucket tích lũy
D. Quantile per-instance cộng lại thành quantile cụm
Đáp án đúng: B

Câu 27. Bucket `+Inf` trong classic histogram có vai trò nào?
A. Chứa tổng thời gian của mọi quan sát
B. Đếm mọi quan sát, kể cả giá trị lớn nhất
C. Đếm riêng quan sát có giá trị vô cực
D. Đánh dấu số quan sát bị loại khỏi histogram
Đáp án đúng: B

Câu 28. Hai chuỗi `_count` và `_sum` của histogram lần lượt thể hiện gì?
A. Số bucket và số instance đang hoạt động
B. Giá trị lớn nhất và nhỏ nhất từng quan sát
C. Quantile cao nhất và quantile thấp nhất
D. Số quan sát và tổng các giá trị quan sát
Đáp án đúng: D

Câu 29. Metric tên `http_request_duration_seconds` thể hiện đơn vị nào?
A. Kích thước request tính bằng byte
B. Thời lượng request tính bằng mili giây
C. Số request được xử lý trong một giây
D. Thời lượng request tính bằng giây
Đáp án đúng: D

Câu 30. Để đếm request hoàn tất và đo latency, cách instrument nào hợp lý?
A. Dùng counter cho số lần và histogram cho thời lượng
B. Dùng gauge cho số lần và counter cho thời lượng
C. Dùng summary cho số lần và gauge cho thời lượng
D. Dùng histogram cho số lần và counter cho thời lượng
Đáp án đúng: A

Câu 31. SLI availability dựa trên request thường được tính thế nào?
A. Tổng request chia số phút trong kỳ đo
B. Số instance healthy chia số lần scrape
C. Số request lỗi chia số instance đang chạy
D. Số request tốt chia tổng request hợp lệ
Đáp án đúng: D

Câu 32. Một latency SLI theo ngưỡng 300 ms thường đo tỷ lệ nào?
A. Request hoàn tất trong 300 ms chia tổng request
B. Số request đang chạy chia tổng request hoàn tất
C. Request vượt 300 ms chia số instance healthy
D. Trung bình latency chia p99 latency của request
Đáp án đúng: A

Câu 33. SLO 99.9% trong 30 ngày xác định điều gì?
A. Chu kỳ scrape bắt buộc là 30 ngày một lần
B. Mục tiêu tỷ lệ SLI đạt chuẩn trong 30 ngày
C. Tỷ lệ sample phải lưu đúng bằng 30 ngày
D. Mức tối đa 99.9 request được phép mỗi ngày
Đáp án đúng: B

Câu 34. Với availability SLO 99.9%, error budget cho phép là bao nhiêu?
A. 9.9% tổng cơ hội phục vụ trong kỳ đo
B. 0.9% tổng cơ hội phục vụ trong kỳ đo
C. 0.1% tổng cơ hội phục vụ trong kỳ đo
D. 1.0% tổng cơ hội phục vụ trong kỳ đo
Đáp án đúng: C

Câu 35. Burn rate bằng 4 cho một SLO biểu thị điều gì?
A. Budget bị tiêu nhanh gấp bốn lần mức chuẩn
B. Còn lại bốn phần trăm error budget ban đầu
C. Có đúng bốn request lỗi trong cửa sổ đo
D. Đạt SLO bốn lần trong một chu kỳ scrape
Đáp án đúng: A

Câu 36. Vì sao SLO alert có thể kết hợp cửa sổ dài và ngắn?
A. Đảm bảo mọi spike ngắn đều tạo page alert
B. Giữ nguyên một ngưỡng cho mọi kỳ lưu trữ
C. Giảm nhiễu mà vẫn phát hiện sự cố đang tăng
D. Thay thế nhu cầu xác định SLI có ý nghĩa
Đáp án đúng: C

Câu 37. Số chuỗi time series tiềm năng tăng nhanh nhất khi thêm label nào?
A. Label có nhiều giá trị độc lập và kết hợp
B. Label boolean chỉ có hai giá trị ổn định theo thiết kế
C. Label service có danh sách nhỏ cố định
D. Label region có vài vùng triển khai chuẩn
Đáp án đúng: A

Câu 38. Với HTTP metrics, label route nên dùng giá trị nào?
A. Template `/orders/{id}` có tập giá trị hữu hạn
B. Raw query string có token và tham số người dùng
C. Request ID ngẫu nhiên tạo riêng cho mỗi lần gọi
D. URL `/orders/8391` thay đổi theo từng request
Đáp án đúng: A

Câu 39. Chọn ranh giới bucket histogram latency nên dựa vào đâu?
A. Chu kỳ refresh dashboard mà người dùng chọn
B. Số lượng nhãn instance hiện có trong cluster
C. Ngưỡng vận hành và mục tiêu SLO cần quan sát
D. Tên package Java tạo ra metric đầu tiên
Đáp án đúng: C

Câu 40. Exemplar trong hệ metrics có thể hỗ trợ việc gì?
A. Thêm trace ID thành label cho mọi time series
B. Thay thế bucket histogram bằng log văn bản
C. Giữ toàn bộ payload request trong metric sample
D. Liên kết một quan sát với trace mẫu liên quan
Đáp án đúng: D

Câu 41. Đơn vị cơ sở thường phù hợp khi ghi thời lượng trong metric là gì?
A. Số tick CPU cho mọi ứng dụng Java
B. Giây để biểu diễn thời lượng đã đo
C. Mili giây cho mọi backend không ngoại lệ
D. Phút để biểu diễn thời lượng đã đo
Đáp án đúng: B

Câu 42. Ước lượng quantile từ histogram classic có đặc điểm nào?
A. Luôn trả đúng giá trị của từng quan sát gốc
B. Không phụ thuộc cách chọn ranh giới bucket
C. Nội suy giữa các ranh giới bucket đã chọn
D. Chỉ dùng được khi mỗi bucket có một sample
Đáp án đúng: C

Câu 43. Khi kiểm thử instrumentation cho counter, điều gì nên được xác minh?
A. Counter đổi tên theo từng request mô phỏng
B. Counter sinh label mới theo mỗi payload mô phỏng
C. Counter tăng đúng sau số sự kiện mô phỏng
D. Counter giảm khi số sự kiện mô phỏng tăng
Đáp án đúng: C

Câu 44. Khi review metric mới, kiểm tra cardinality nên tập trung vào đâu?
A. Số tổ hợp nhãn có thể sinh ra ở tải thực
B. Số chữ trong tên metric và phần mô tả
C. Số dòng code dùng để đăng ký meter trong app
D. Số dashboard người dùng có thể mở đồng thời
Đáp án đúng: A
