Câu 1. Prometheus thu thập metrics từ target theo mô hình nào trong cấu hình scrape thông thường?
A. Target chủ động gửi từng sample vào server qua HTTP push.
B. Prometheus định kỳ lấy metrics từ endpoint của target.
C. Grafana định kỳ đọc trực tiếp metric từ process ứng dụng.
D. Collector phải chuyển mọi metric thành log trước khi lưu.
Đáp án đúng: B

Câu 2. Một ứng dụng muốn Prometheus scrape metrics thường cần cung cấp điều gì?
A. Endpoint HTTP trả metrics theo định dạng Prometheus.
B. Một dashboard Grafana có quyền truy cập vào ứng dụng.
C. Một webhook để Prometheus nhận từng sự kiện runtime.
D. Một file SQL chứa các giá trị metric đã tổng hợp.
Đáp án đúng: A

Câu 3. Trong cấu hình scrape, cặp nhãn `job` và `instance` thường biểu thị điều gì?
A. Tên metric và đơn vị đo của từng sample được lưu.
B. Tên dashboard và người sở hữu panel Grafana.
C. Tên rule và trạng thái alert của target hiện tại.
D. Nhóm công việc scrape và địa chỉ target được scrape.
Đáp án đúng: D

Câu 4. `scrape_interval` trong một job Prometheus quy định điều gì?
A. Thời gian tối đa Prometheus chờ một query hoàn tất.
B. Khoảng thời gian giữa hai lần scrape target liên tiếp.
C. Thời gian lưu mỗi sample trong bộ nhớ trước khi ghi WAL.
D. Khoảng thời gian Grafana làm mới dashboard sau mỗi lần mở.
Đáp án đúng: B

Câu 5. Giá trị `scrape_timeout` cần tuân theo ràng buộc nào?
A. Luôn dài hơn thời gian retention của TSDB.
B. Không vượt quá `scrape_interval` của job tương ứng.
C. Phải bằng thời gian evaluation của mọi recording rule.
D. Luôn ngắn hơn timeout kết nối của exporter.
Đáp án đúng: B

Câu 6. Metric `up` do Prometheus tạo có ý nghĩa gì?
A. Bằng số sample target xuất ra trong lần scrape gần nhất.
B. Bằng số request HTTP thành công của ứng dụng được scrape.
C. Bằng 1 khi lần scrape gần nhất thành công, ngược lại bằng 0.
D. Bằng 1 khi target được phát hiện, kể cả scrape thất bại.
Đáp án đúng: C

Câu 7. Kubernetes service discovery trong Prometheus giúp thực hiện việc gì?
A. Tự tạo Service và Deployment mới cho mọi exporter.
B. Tự cài Prometheus Operator lên từng worker node.
C. Tự phát hiện target từ tài nguyên Kubernetes phù hợp.
D. Tự thay đổi label nghiệp vụ trong mọi HTTP request.
Đáp án đúng: C

Câu 8. `relabel_configs` được áp dụng chủ yếu ở giai đoạn nào?
A. Biến đổi hoặc lọc target labels trước khi scrape.
B. Biến đổi từng sample sau khi đã được ghi vào TSDB.
C. Đổi tên dashboard và panel trong Grafana khi tải trang.
D. Nén WAL segment sau khi TSDB hoàn tất compaction.
Đáp án đúng: A

Câu 9. `metric_relabel_configs` tác động lên dữ liệu ở giai đoạn nào?
A. Chọn địa chỉ IP target trước khi Prometheus mở kết nối.
B. Đổi nhãn của alert sau khi rule đã firing.
C. Lọc sample sau scrape, trước khi lưu TSDB.
D. Thay đổi cấu hình discovery trước khi tìm target.
Đáp án đúng: C

Câu 10. Nhãn nội bộ `__address__` trong pipeline target relabeling thường dùng để làm gì?
A. Chỉ địa chỉ host và port mà Prometheus sẽ scrape.
B. Chỉ tên metric mà exporter sẽ xuất trong response.
C. Chỉ đường dẫn file cấu hình đang được Prometheus đọc.
D. Chỉ địa chỉ datasource Grafana dùng để truy vấn.
Đáp án đúng: A

Câu 11. Khi target tự cung cấp label trùng với label do Prometheus gán, `honor_labels` ảnh hưởng điều gì?
A. Quyết định cách xử lý xung đột giữa target labels và server labels.
B. Quyết định có giữ sample trong WAL sau khi scrape thành công.
C. Quyết định có xác thực TLS cho kết nối đến exporter hay không.
D. Quyết định cách Grafana hiển thị legend trong biểu đồ.
Đáp án đúng: A

Câu 12. Nếu scrape vượt `sample_limit` được cấu hình cho job, hành vi nào có thể xảy ra?
A. Prometheus tự tăng giới hạn để nhận đủ sample của target.
B. Scrape bị xem là lỗi khi số sample vượt giới hạn.
C. TSDB tự xóa các series cũ nhất rồi nhận phần còn lại.
D. Grafana tự giảm số panel để phù hợp số sample trả về.
Đáp án đúng: B

Câu 13. Khi instrument ứng dụng bằng Prometheus client library, metric nên phản ánh điều gì?
A. Mọi biến cục bộ trong từng method để tránh thiếu dữ liệu.
B. Sự kiện và trạng thái cần quan sát của ứng dụng.
C. Toàn bộ request body để tái tạo nghiệp vụ từ metrics.
D. Một label riêng cho mỗi người dùng và mỗi request.
Đáp án đúng: B

Câu 14. Counter trong Prometheus phù hợp nhất với loại dữ liệu nào?
A. Giá trị hiện tại có thể tăng hoặc giảm trong suốt vòng đời.
B. Phân phối quan sát được chia vào các bucket theo ngưỡng.
C. Bộ đếm sự kiện tăng dần, có thể reset khi process restart.
D. Giá trị quantile được tính riêng trong từng process.
Đáp án đúng: C

Câu 15. Gauge khác Counter ở đặc điểm nào?
A. Gauge biểu diễn giá trị hiện tại có thể tăng hoặc giảm.
B. Gauge chỉ tăng cho đến khi process khởi động lại.
C. Gauge lưu mọi quan sát vào bucket có biên cố định.
D. Gauge chỉ biểu diễn quantile tính toán phía client.
Đáp án đúng: A

Câu 16. Histogram trong Prometheus thường tạo ra nhóm series nào?
A. Các series `_min`, `_max` và `_median` cho quan sát.
B. Các series `_rate`, `_delta` và `_reset` cho quan sát.
C. Các series `_bucket`, `_sum` và `_count` cho quan sát.
D. Các series `_trace`, `_span` và `_event` cho quan sát.
Đáp án đúng: C

Câu 17. Vì sao Summary quantile thường khó tổng hợp chính xác qua nhiều instance?
A. Summary chỉ lưu số đếm, không lưu tổng các quan sát.
B. Summary luôn có bucket giống nhau trên mọi instance.
C. Prometheus loại bỏ mọi sample Summary trước khi lưu TSDB.
D. Quantile phía client khó gộp chính xác giữa instance.
Đáp án đúng: D

Câu 18. Một instant vector selector trong PromQL trả về loại dữ liệu nào?
A. Toàn bộ sample của mỗi series trong một khoảng thời gian dài.
B. Một giá trị scalar duy nhất sau khi cộng mọi series.
C. Sample mới nhất của các series khớp selector.
D. Một ma trận các span theo quan hệ cha con giữa dịch vụ.
Đáp án đúng: C

Câu 19. Biểu thức `http_requests_total[5m]` trong PromQL biểu diễn điều gì?
A. Instant vector chứa sample mới nhất trong năm phút gần nhất.
B. Scalar là tổng request của toàn bộ hệ thống trong năm phút.
C. Một histogram đã tính p95 cho request trong năm phút.
D. Range vector chứa sample của series trong năm phút gần nhất.
Đáp án đúng: D

Câu 20. Khi muốn tính tốc độ request từ Counter theo cửa sổ thời gian, hàm nào thường phù hợp?
A. `sum()` chuyển Counter tích lũy thành tốc độ mỗi giây.
B. `rate()` ước tính tốc độ tăng trung bình mỗi giây.
C. `count()` đếm số series và coi đó là request mỗi giây.
D. `label_replace()` đổi nhãn thành giá trị request mỗi giây.
Đáp án đúng: B

Câu 21. Vì sao thường áp dụng `rate()` trước khi `sum()` các Counter theo nhóm?
A. Để giữ nguyên mọi label riêng lẻ sau khi phép cộng hoàn tất.
B. Để chuyển các series Counter thành Gauge trước khi scrape.
C. Để nhận diện reset Counter riêng từng series trước khi cộng.
D. Để tránh Prometheus đọc timestamp của sample trong TSDB.
Đáp án đúng: C

Câu 22. Với Histogram tên `request_duration_seconds`, cách tính p95 tổng hợp thường dùng gì?
A. `quantile` trên `_sum`, nhóm theo `instance` và `job`.
B. `rate` trên `_count`, rồi lấy giá trị lớn nhất theo `le`.
C. `histogram_quantile` dùng bucket rate, nhóm theo `le`.
D. `avg_over_time` trên `_bucket`, nhóm theo `status`.
Đáp án đúng: C

Câu 23. Có thể ước tính latency trung bình từ Histogram bằng biểu thức nào?
A. Tỷ lệ `rate(_count)` chia cho `rate(_sum)` tương ứng.
B. Lấy trung bình các bucket rồi nhân với số instance.
C. Lấy p95 của từng instance rồi tính trung bình các p95.
D. Tỷ lệ `rate(_sum)` chia cho `rate(_count)` tương ứng.
Đáp án đúng: D

Câu 24. Trong PromQL, `sum by (job)` thực hiện phép tổng hợp nào?
A. Cộng các series và giữ lại nhãn `job` trong kết quả.
B. Cộng các series và loại bỏ nhãn `job` khỏi kết quả.
C. Chọn series có giá trị lớn nhất cho mỗi nhãn `job`.
D. Đếm số lần scrape thành công của từng nhãn `job`.
Đáp án đúng: A

Câu 25. Matcher `status=~"5.."` trong PromQL chọn những series nào?
A. Series có nhãn status bằng chính xác chuỗi `5..`.
B. Series có tên metric bắt đầu bằng chuỗi `status`.
C. Series không có nhãn status hoặc có giá trị rỗng.
D. Series có nhãn status khớp biểu thức chính quy `5..`.
Đáp án đúng: D

Câu 26. Trong phép nối vector, từ khóa `on(instance)` dùng để làm gì?
A. Giữ duy nhất nhãn `instance` trong mọi metric được scrape.
B. Sắp xếp kết quả theo thứ tự tên instance tăng dần.
C. Lọc mọi series không có sample từ instance hiện tại.
D. Đối sánh hai vector dựa trên giá trị nhãn `instance`.
Đáp án đúng: D

Câu 27. Modifier `group_left` thường cần trong trường hợp nào?
A. Nối vector khi phía trái có nhiều series khớp một series phía phải.
B. Nối hai vector chỉ khi mỗi bên có đúng một series tổng thể.
C. Giữ các series bên phải và loại mọi series bên trái.
D. Gộp mọi nhãn thành một chuỗi trước khi thực hiện phép nối.
Đáp án đúng: A

Câu 28. Modifier `offset 1h` trong PromQL có tác dụng gì?
A. Dịch timestamp của sample mới thêm một giờ về phía trước.
B. Đánh giá selector trên dữ liệu cách hiện tại một giờ.
C. Đặt chu kỳ scrape của job dài thêm một giờ.
D. Trì hoãn evaluation của recording rule thêm một giờ.
Đáp án đúng: B

Câu 29. Recording rule trong Prometheus thường được dùng để làm gì?
A. Lưu kết quả PromQL thành series mới để dùng lại.
B. Gửi thông báo trực tiếp tới người trực khi query có kết quả.
C. Thay đổi target discovery trước khi Prometheus scrape.
D. Xóa series có cardinality cao khỏi dữ liệu đã lưu.
Đáp án đúng: A

Câu 30. Trong alerting rule, trường `for: 5m` thường có ý nghĩa nào?
A. Chờ điều kiện đúng liên tục năm phút mới firing.
B. Alert tự động đóng sau năm phút kể từ lúc firing.
C. Prometheus chỉ đánh giá rule một lần mỗi năm phút.
D. Alert chỉ gửi notification trong năm phút đầu của ngày.
Đáp án đúng: A

Câu 31. Một rule group trong Prometheus thường đảm nhiệm việc gì?
A. Nhóm các target có cùng địa chỉ IP để scrape cùng lúc.
B. Nhóm recording và alerting rules được đánh giá theo lịch chung.
C. Nhóm dashboard Grafana thành một thư mục có quyền riêng.
D. Nhóm WAL segment theo dung lượng trước khi nén TSDB.
Đáp án đúng: B

Câu 32. Prometheus nhận diện một time series duy nhất dựa trên yếu tố nào?
A. Tên job cùng timestamp của lần scrape đầu tiên.
B. Tên metric cùng toàn bộ tập nhãn của series.
C. Tên exporter cùng địa chỉ IP của máy chủ lưu TSDB.
D. Tên dashboard cùng biểu thức PromQL đang hiển thị.
Đáp án đúng: B

Câu 33. Cardinality tăng mạnh thường gây hệ quả nào cho Prometheus?
A. Giảm số lần scrape vì Prometheus tự gộp mọi nhãn.
B. Tăng độ chính xác của quantile mà không tốn thêm tài nguyên.
C. Tăng số series, bộ nhớ, lưu trữ và chi phí truy vấn.
D. Giảm kích thước WAL do mỗi series có nhiều nhãn hơn.
Đáp án đúng: C

Câu 34. Trong TSDB của Prometheus, WAL chủ yếu phục vụ mục đích nào?
A. Lưu dashboard và cấu hình datasource của Grafana.
B. Lưu lịch sử alert notification đã gửi đến người trực.
C. Nén toàn bộ block cũ thành một file archive duy nhất.
D. Ghi nhận sample mới để hỗ trợ khôi phục sau sự cố.
Đáp án đúng: D

Câu 35. Compaction trong Prometheus TSDB thường thực hiện việc gì?
A. Xóa mọi sample mới hơn lần scrape gần nhất của target.
B. Đổi tên label để giảm số lượng series trong mỗi job.
C. Gộp các block dữ liệu nhỏ thành block lớn hơn theo thời gian.
D. Chuyển toàn bộ time series thành log dạng văn bản.
Đáp án đúng: C

Câu 36. Retention trong Prometheus TSDB kiểm soát điều gì?
A. Khoảng cách giữa các lần scrape của từng target.
B. Thời gian chờ trước khi alert chuyển sang firing.
C. Số lượng label tối đa được phép trên mỗi dashboard.
D. Giới hạn thời gian hoặc dung lượng lưu dữ liệu TSDB.
Đáp án đúng: D

Câu 37. Khi một series biến mất khỏi lần scrape mới, Prometheus biểu diễn trạng thái này ra sao?
A. Tự đặt giá trị sample cuối cùng bằng 0 trong mọi truy vấn.
B. Đánh dấu series đã biến mất bằng staleness marker.
C. Xóa ngay toàn bộ block chứa series khỏi TSDB.
D. Đổi tên series thành `stale` và tiếp tục scrape nó.
Đáp án đúng: B

Câu 38. `remote_write` trong Prometheus thường dùng để làm gì?
A. Nhận sample từ exporter thay cho cơ chế scrape thông thường.
B. Đồng bộ dashboard và panel từ Prometheus sang Grafana.
C. Chuyển alert rule thành webhook gọi ngược tới exporter.
D. Gửi sample đã scrape tới hệ thống lưu trữ từ xa tương thích.
Đáp án đúng: D

Câu 39. Khi target hiển thị `DOWN` trên trang `/targets`, nên kiểm tra gì trước?
A. Chỉ query Grafana dashboard và tăng refresh interval.
B. Xóa TSDB block cũ rồi khởi động lại Prometheus server.
C. Thay toàn bộ metric labels trước khi xem lỗi scrape.
D. Lỗi scrape, endpoint, đường mạng và cấu hình target.
Đáp án đúng: D

Câu 40. Grafana tích hợp Prometheus datasource chủ yếu theo cách nào?
A. Gửi PromQL queries tới Prometheus để dựng panel và dashboard.
B. Nhận push sample trực tiếp từ exporter qua giao thức scrape.
C. Đăng ký MBean vào JVM để Prometheus đọc dữ liệu JMX.
D. Thay Prometheus TSDB bằng database riêng của từng dashboard.
Đáp án đúng: A
