Câu 01. Datadog Agent trên host thường đảm nhiệm vai trò nào?
A. Chạy dashboard query trên host rồi gửi biểu đồ lên Datadog.
B. Thu thập metric và event rồi chuyển dữ liệu lên Datadog.
C. Đánh giá monitor và gửi thông báo khi metric vượt ngưỡng.
D. Lưu metric và trace dài hạn trên host để Grafana truy vấn.
Đáp án đúng: B

Câu 02. Trong kiến trúc Agent, Collector và Forwarder khác nhau thế nào?
A. Collector chạy checks; Forwarder gửi payload tới Datadog.
B. Collector tạo span; Forwarder tự instrument thư viện ứng dụng.
C. Collector gửi payload; Forwarder chạy checks trên host.
D. Collector đánh giá monitor; Forwarder gửi cảnh báo tới team.
Đáp án đúng: A

Câu 03. Khi muốn thu metric từ một database được Datadog hỗ trợ, thường cấu hình gì?
A. Bật core system check rồi mong nó thu metric database.
B. Tạo monitor log để Datadog tự sinh metric database.
C. Bật integration check phù hợp trong Datadog Agent.
D. Gắn database name thành host tag để Agent tự nhận diện.
Đáp án đúng: C

Câu 04. Datadog Autodiscovery trong Kubernetes giúp ích điều gì?
A. Tự cài sidecar riêng cho mỗi container được phát hiện.
B. Tạo monitor mới cho từng Kubernetes Service được phát hiện.
C. Chỉ gắn tag pod mà không áp cấu hình integration check.
D. Phát hiện workload và áp cấu hình integration phù hợp.
Đáp án đúng: D

Câu 05. Muốn Agent thu log từ host, cần chú ý cấu hình nào?
A. Tạo log monitor trước khi cấu hình Agent.
B. Bật log collection và khai báo nguồn log phù hợp.
C. Chỉ bật APM trace collection trong SDK ứng dụng.
D. Chỉ thêm tag service vào metric của host đó.
Đáp án đúng: B

Câu 06. DogStatsD thường được dùng để làm gì?
A. Phân tích file log và tự tạo index cho từng dòng.
B. Nhận custom metrics và events từ ứng dụng qua Agent.
C. Quản lý API key và quyền truy cập vào Datadog.
D. Lưu trace span rồi hiển thị service map cho APM.
Đáp án đúng: B

Câu 07. Một ứng dụng gửi gauge qua DogStatsD nên hiểu giá trị đó thế nào?
A. Tổng số sự kiện tích lũy từ lúc process khởi động.
B. Số request trung bình mỗi giây trong toàn bộ cluster.
C. Giá trị đo tại thời điểm gửi, như độ dài queue hiện tại.
D. Tỷ lệ phần trăm trace được giữ lại sau sampling.
Đáp án đúng: C

Câu 08. Unified Service Tagging thường dựa trên ba tag nào?
A. pod, container_id và span_id cho mọi metric.
B. host, region và request_id để phân biệt từng request.
C. team, dashboard và monitor để gom tài nguyên.
D. env, service và version để liên kết telemetry.
Đáp án đúng: D

Câu 09. Vì sao request_id thường không phù hợp làm metric tag?
A. Nó chỉ được hỗ trợ trong log, không có trong APM.
B. Nó khiến gauge bị chuyển thành counter khi ingest.
C. Nó bị Datadog loại bỏ khỏi mọi metric custom.
D. Giá trị thay đổi liên tục làm tăng số time series.
Đáp án đúng: D

Câu 10. Một custom metric time series được phân biệt chủ yếu bởi điều gì?
A. Tên dashboard cùng khoảng thời gian hiển thị dữ liệu.
B. Tên metric cùng tổ hợp giá trị tag của nó.
C. Địa chỉ IP Agent cùng phiên bản hệ điều hành.
D. Tên monitor cùng người nhận thông báo khi alert.
Đáp án đúng: B

Câu 11. Dùng cùng env, service và version trên metrics, logs, traces đem lại lợi ích gì?
A. Tự động gắn quyền truy cập giống nhau cho mọi người.
B. Giảm mọi metric cardinality về đúng một time series.
C. Dễ lọc và đối chiếu tín hiệu của cùng dịch vụ.
D. Đảm bảo tất cả log đều có trace tương ứng được giữ lại.
Đáp án đúng: C

Câu 12. Host-level tags trong Agent configuration thường có tác dụng nào?
A. Ghi đè mọi tag do ứng dụng gửi từ tất cả service.
B. Chỉ dùng để chọn Datadog site mà Agent sẽ kết nối.
C. Gắn metadata chung lên telemetry gửi từ host đó.
D. Chỉ thêm tag vào log, không áp dụng cho metric hay trace.
Đáp án đúng: C

Câu 13. Khi dùng custom metrics, vì sao cần theo dõi cardinality?
A. Nhiều tổ hợp tag tạo nhiều time series riêng biệt.
B. Cardinality cao làm timestamp của metric bị trễ hơn.
C. Cardinality chỉ ảnh hưởng kích thước log, không liên quan metric.
D. Cardinality quyết định số lần Agent restart mỗi giờ.
Đáp án đúng: A

Câu 14. Metrics without Limits giúp quản lý custom metric theo cách nào?
A. Chuyển custom metric thành log event để giảm chi phí.
B. Ngừng ingest metric khi một tag không còn được truy vấn.
C. Tự xóa mọi tag khỏi metric ở phía ứng dụng trước khi gửi.
D. Chọn tag nào còn queryable để kiểm soát indexed cardinality.
Đáp án đúng: D

Câu 15. Khi cần thống kê phân phối latency của request, metric type nào thường phù hợp?
A. Distribution để phân tích phân bố và percentile.
B. Count để lưu từng mẫu latency thành một log line.
C. Rate để lưu giá trị latency hiện tại của một request.
D. Gauge để cộng dồn mọi request từ lúc service khởi động.
Đáp án đúng: A

Câu 16. Trong Datadog APM, trace thường được cấu thành từ những gì?
A. Các monitor độc lập được nhóm theo trạng thái cảnh báo.
B. Các metric point được sắp xếp theo tên host.
C. Các log index được nối theo thứ tự ingest.
D. Các span liên kết thể hiện những chặng xử lý request.
Đáp án đúng: D

Câu 17. Trace context propagation có nhiệm vụ nào trong ứng dụng phân tán?
A. Đưa toàn bộ request body vào tag của span tiếp theo.
B. Truyền API key của Datadog qua mọi HTTP request.
C. Truyền trace và parent span identifiers giữa các service.
D. Đồng bộ đồng hồ của các host trong cùng một cluster.
Đáp án đúng: C

Câu 18. Datadog SDK tự động instrument thường hỗ trợ điều gì?
A. Tạo span và truyền trace context cho thư viện được hỗ trợ.
B. Tự lưu log file vào archive khi request trả về 500.
C. Tự cấu hình monitor và ngưỡng cảnh báo theo latency.
D. Tự tạo dashboard cho mọi route mà ứng dụng cung cấp.
Đáp án đúng: A

Câu 19. Log injection trong Datadog APM hỗ trợ việc gì?
A. Gắn API key vào log để xác định tài khoản gửi dữ liệu.
B. Chuyển log thành span và bỏ qua trace sampling.
C. Thay timestamp log bằng thời gian kết thúc trace.
D. Gắn trace_id và span_id vào log để liên kết trace.
Đáp án đúng: D

Câu 20. Log và trace đã cấu hình correlation nhưng một trace không tìm thấy. Lý do nào có thể xảy ra?
A. Correlation chỉ hoạt động khi trace được lưu trong dashboard.
B. Trace có thể không được ingest do sampling độc lập với log.
C. Trace ID trong log luôn bị đổi sau khi log được index.
D. Datadog chỉ liên kết log nếu mọi span đều có cùng timestamp.
Đáp án đúng: B

Câu 21. APM trace metrics về request count, error và latency thường có đặc điểm nào?
A. Chỉ tính khi log injection được bật cho tất cả service.
B. Chỉ tính các request đã tạo dashboard widget tương ứng.
C. Chỉ tính trên những trace đã được giữ trong retention filter.
D. Được tính từ traffic ứng dụng bất kể trace ingestion sampling.
Đáp án đúng: D

Câu 22. Service Map trong Datadog APM hữu ích nhất để hiểu điều gì?
A. Danh sách host được cấp API key trong cùng một organization.
B. Lịch sử thay đổi cấu hình monitor qua từng lần deploy.
C. Số lượng log archive đã được lưu theo từng tenant.
D. Hiển thị quan hệ service và tín hiệu hiệu năng liên quan.
Đáp án đúng: D

Câu 23. Khi sampling trace, mục tiêu chính thường là gì?
A. Đảm bảo mọi lỗi hiếm đều có trace được lưu lại.
B. Giảm trace ingest nhưng vẫn giữ các trace cần thiết.
C. Giảm số request thực sự được ứng dụng xử lý mỗi giây.
D. Thay thế metric request count bằng số span được lưu.
Đáp án đúng: B

Câu 24. Trong Datadog Logs, pipeline thường dùng để làm gì?
A. Tạo metric từ host checks trước khi Agent gửi dữ liệu.
B. Chọn dashboard folder và phân quyền người xem log.
C. Parse, enrich và chuẩn hóa log trước khi lưu trữ.
D. Lưu trace span và tính toán percentile latency của APM.
Đáp án đúng: C

Câu 25. Một Grok parser trong log pipeline thường có nhiệm vụ nào?
A. Trích xuất các field có cấu trúc từ log line dạng text.
B. Mã hóa toàn bộ log line trước khi gửi lên Datadog.
C. Tạo trace span từ mỗi từ khóa xuất hiện trong message.
D. Định tuyến log tới host Agent dựa trên giá trị severity.
Đáp án đúng: A

Câu 26. Khi Java stack trace bị tách thành nhiều log events, cần xử lý gì?
A. Gom các dòng cùng exception thành một log event.
B. Gắn từng dòng stack trace vào tag có cardinality cao.
C. Tạo một index riêng cho từng dòng stack trace.
D. Đổi mọi dòng continuation thành metric count của service.
Đáp án đúng: A

Câu 27. Log index và log archive khác nhau cơ bản thế nào?
A. Index chỉ chứa metrics; archive chỉ chứa trace span.
B. Index là nơi cấu hình Agent; archive là nơi tạo monitor.
C. Index giữ bản sao dài hạn; archive phục vụ tìm kiếm tức thời.
D. Index hỗ trợ tìm kiếm; archive lưu log để rehydrate.
Đáp án đúng: D

Câu 28. Nếu muốn giảm log volume được index, lựa chọn nào phù hợp?
A. Dùng exclusion filter để bỏ log ít cần tìm khỏi index.
B. Tắt Agent hoàn toàn để không còn log nào được thu thập.
C. Đổi mọi log thành DEBUG để giảm kích thước dữ liệu.
D. Thêm request_id vào mọi log để gom chúng thành một index.
Đáp án đúng: A

Câu 29. Khi log chứa access token, biện pháp nào nên áp dụng trước khi lưu?
A. Đưa token thành tag để chỉ admin có thể truy vấn.
B. Chỉ ẩn token khỏi dashboard nhưng vẫn index giá trị gốc.
C. Che token nhạy cảm trong pipeline trước khi lưu log.
D. Mã hóa token bằng Base64 trước khi gửi và lưu nguyên dạng.
Đáp án đúng: C

Câu 30. Facet trong Datadog Log Explorer thường hỗ trợ thao tác nào?
A. Tự sinh trace span cho từng giá trị thuộc tính.
B. Thay thế log index bằng metric time series.
C. Giữ bản sao archive của mọi log có cùng message.
D. Facet cho phép lọc và nhóm log theo field đã chọn.
Đáp án đúng: D

Câu 31. Log-based metric trong Datadog được tạo ra nhằm mục đích nào?
A. Gom log phù hợp thành metric để theo dõi service.
B. Lưu nguyên văn mọi log trong custom metric index.
C. Tạo trace từ các dòng log đã qua Grok parser.
D. Thay thế log archive bằng dashboard có thời hạn.
Đáp án đúng: A

Câu 32. Monitor metric thường đánh giá điều gì?
A. Trạng thái API key của Agent trên từng host.
B. Nội dung stack trace của mọi log trong archive.
C. Đánh giá metric theo truy vấn và khoảng thời gian.
D. Quan hệ cha-con của span trong một distributed trace.
Đáp án đúng: C

Câu 33. Khi monitor được group theo service và region, hệ quả nào thường có?
A. Monitor bỏ qua các tag không xuất hiện trong dashboard.
B. Metric query tự động chuyển thành truy vấn log.
C. Có thể tạo trạng thái cảnh báo riêng cho từng nhóm.
D. Mọi nhóm luôn gộp thành một alert duy nhất.
Đáp án đúng: C

Câu 34. No Data trên monitor cần được hiểu thế nào?
A. Giá trị metric bằng không và chắc chắn hệ thống khỏe.
B. Không có điểm dữ liệu phù hợp trong cửa sổ đánh giá.
C. Metric đã vượt ngưỡng warning nhưng chưa tới critical.
D. Agent đã xác nhận host bị tắt hoàn toàn.
Đáp án đúng: B

Câu 35. Composite monitor thường hữu ích khi muốn làm gì?
A. Cộng mọi log event thành một metric gauge.
B. Kết hợp kết quả các monitor theo điều kiện logic.
C. Gộp nhiều dashboard thành một màn hình duy nhất.
D. Ghép nhiều trace thành một request phân tán.
Đáp án đúng: B

Câu 36. Dashboard template variable giúp người xem thực hiện thao tác nào?
A. Đổi phạm vi dashboard theo giá trị tag env và service.
B. Tự sửa ngưỡng monitor khi người xem đổi time range.
C. Xóa log archive theo service đang được chọn.
D. Thay đổi API key của Agent mà không cần restart.
Đáp án đúng: A

Câu 37. Khi dashboard cần hiển thị nhiều tín hiệu, cách bố trí nào phù hợp?
A. Kết hợp widget metrics, logs và APM theo câu hỏi vận hành.
B. Chỉ dùng log table vì metrics và traces không thể cùng xem.
C. Tạo dashboard riêng cho từng tag value bất kể nhu cầu.
D. Đưa mọi log line vào widget metric query duy nhất.
Đáp án đúng: A

Câu 38. Muốn điều tra latency tăng ở một service, bước đầu nào có ích?
A. Đổi tag version để gom trace từ mọi bản triển khai.
B. Lọc APM theo env, service, version rồi xem trace chậm.
C. Tăng trace sampling trước khi xem request bị ảnh hưởng.
D. Xóa log index của service để giảm dữ liệu tìm kiếm.
Đáp án đúng: B

Câu 39. Khi chi phí custom metrics tăng đột biến, nên điều tra gì trước?
A. Số lần monitor gửi thông báo tới email mỗi ngày.
B. Xem số time series và tổ hợp tag tạo cardinality cao.
C. Dung lượng file cấu hình YAML trên các Agent host.
D. Số dashboard được người dùng mở cùng một thời điểm.
Đáp án đúng: B

Câu 40. Để kiểm soát chi phí quan sát mà vẫn giữ khả năng điều tra, nên làm gì?
A. Tắt metrics, logs và traces của mọi service ít traffic.
B. Giữ toàn bộ log và trace vô thời hạn để tránh mất dữ liệu.
C. Rà cardinality, log volume, retention và trace sampling.
D. Tạo thêm tag riêng cho từng request để dễ lọc chính xác.
Đáp án đúng: C
