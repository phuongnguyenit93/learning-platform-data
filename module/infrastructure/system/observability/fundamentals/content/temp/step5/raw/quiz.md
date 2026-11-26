Câu 1. Observability khác với chỉ kiểm tra health check định kỳ ở điểm cốt lõi nào?
A. Chỉ phát hiện process còn chạy qua một endpoint kiểm tra.
B. Suy luận trạng thái nội bộ từ nhiều tín hiệu của hệ thống.
C. Chỉ dựa vào số lần container được Kubernetes khởi động.
D. Chỉ tổng hợp số máy chủ đang bật trong từng môi trường.
Đáp án đúng: B

Câu 2. Trong bộ tín hiệu observability, metrics phù hợp nhất để lưu thông tin gì?
A. Sự kiện chi tiết từng dòng gắn với message và request.
B. Cây các span mô tả đường đi qua nhiều dịch vụ.
C. Mẫu stack trace thể hiện CPU tiêu thụ trong hàm.
D. Chuỗi số liệu theo thời gian để theo dõi xu hướng.
Đáp án đúng: D

Câu 3. Khi điều tra một lần request bị từ chối với lỗi cụ thể, logs có ưu thế nào?
A. Cung cấp phân phối latency của mọi request trong cả cụm.
B. Cung cấp sự kiện và ngữ cảnh chi tiết tại thời điểm lỗi.
C. Cung cấp flame graph CPU của toàn bộ process đang chạy.
D. Cung cấp tỷ lệ thành công tổng hợp theo khoảng một giờ.
Đáp án đúng: B

Câu 4. Distributed trace giúp trả lời câu hỏi nào trong hệ microservices?
A. CPU của mọi thread tiêu thụ bao nhiêu chu kỳ mỗi ngày.
B. Số lỗi tích lũy toàn hệ qua nhiều tuần triển khai.
C. Request đi qua những span nào và thời gian ở từng đoạn.
D. File cấu hình nào đã bị thay đổi giữa hai bản release.
Đáp án đúng: C

Câu 5. Continuous profiling thường cung cấp góc nhìn nào về ứng dụng?
A. Những client nào tạo nhiều mã HTTP 429 theo thời gian.
B. Những request nào có trace ID giống nhau giữa dịch vụ.
C. Những hàm và stack sử dụng CPU hoặc bộ nhớ nhiều nhất.
D. Những host nào đang có số lượng kết nối TCP lớn nhất.
Đáp án đúng: C

Câu 6. Metric dạng Counter thường thích hợp để ghi nhận loại dữ liệu nào?
A. Số kết nối đang mở có thể lên xuống từng giây.
B. Tổng số request đã xử lý, chỉ tăng trừ lúc reset.
C. Dung lượng RAM khả dụng thay đổi cả tăng lẫn giảm.
D. Nhiệt độ CPU biến đổi liên tục theo thời gian.
Đáp án đúng: B

Câu 7. Metric dạng Gauge có đặc điểm nào cần lưu ý?
A. Giá trị có thể tăng hoặc giảm như số kết nối hiện tại.
B. Giá trị chỉ tăng và không bao giờ giảm khi process sống.
C. Giá trị luôn biểu diễn tỷ lệ thành công qua một phút.
D. Giá trị luôn là tổng số sự kiện tính từ lúc boot.
Đáp án đúng: A

Câu 8. Vì sao dùng `rate()` trên Counter request thường hữu ích hơn số tích lũy?
A. Khôi phục từng log request đã bị xoá khỏi hệ thống ghi log.
B. Ước tính tốc độ phát sinh request trong một cửa sổ thời gian.
C. Loại bỏ hoàn toàn nhu cầu lưu timestamp của từng sample.
D. Biến số request tích lũy thành thời gian xử lý của một span.
Đáp án đúng: B

Câu 9. Histogram latency giúp ích gì khi theo dõi hiệu năng nhiều instance?
A. Giữ riêng toàn bộ body của mỗi request trong từng bucket.
B. Thay thế trace context khi một request đi qua nhiều service.
C. Đảm bảo latency p99 bằng trung bình các p99 của từng pod.
D. Gom phân phối qua bucket để ước lượng quantile tổng hợp.
Đáp án đúng: D

Câu 10. Vì sao không nên lấy trung bình p99 của từng Pod để suy ra p99 toàn hệ?
A. Quantile toàn hệ luôn bằng p99 của Pod có throughput thấp nhất.
B. Mỗi Pod thường chỉ ghi nhận request thành công khi đo quantile.
C. p99 toàn hệ luôn bằng trung bình latency của tất cả request.
D. Quantile riêng lẻ không cộng gộp chính xác bằng phép trung bình.
Đáp án đúng: D

Câu 11. Nhóm chỉ số RED cho dịch vụ HTTP thường gồm những gì?
A. RAM, Entropy và Disk I/O của hệ điều hành.
B. Retries, Events và Deployments của pipeline.
C. Rate, Errors và Duration của các request dịch vụ.
D. Requests, Endpoints và Dependencies của API.
Đáp án đúng: C

Câu 12. Mô hình USE thích hợp để kiểm tra tài nguyên theo ba góc nào?
A. Uptime, Security và Efficiency của ứng dụng.
B. Users, Sessions và Events của trình duyệt.
C. Updates, Signals và Exceptions của service.
D. Utilization, Saturation, Errors của tài nguyên.
Đáp án đúng: D

Câu 13. Gán `user_id` khác nhau cho mỗi series HTTP request có rủi ro gì?
A. Làm histogram tự động hợp nhất hết các giá trị user_id.
B. Giảm độ phân giải metric xuống một sample mỗi ngày.
C. Tăng cardinality nhãn và chi phí lưu trữ hoặc truy vấn.
D. Buộc Collector chuyển toàn bộ metric thành log dạng text.
Đáp án đúng: C

Câu 14. Nhãn nào phù hợp hơn cho metric lỗi HTTP có cardinality giới hạn?
A. `request_id` duy nhất của mỗi lần gọi vào endpoint.
B. `session_token` của từng người dùng đang đăng nhập.
C. `raw_url` có query string mang dữ liệu riêng từng lần.
D. `status_class` với các nhóm như `2xx`, `4xx`, `5xx`.
Đáp án đúng: D

Câu 15. Khi process restart làm Counter về 0, truy vấn tốc độ cần xử lý gì?
A. Xóa tất cả sample trước restart để đảm bảo không lệch.
B. Nhận diện reset Counter thay vì coi đó là lượng request âm.
C. Chuyển Counter thành Gauge không cần phân tích reset.
D. Coi giá trị reset là request thất bại của toàn hệ.
Đáp án đúng: B

Câu 16. Structured logging với JSON thường hữu ích hơn log text tự do vì sao?
A. Log JSON tự động bảo đảm không thể chứa dữ liệu nhạy cảm.
B. Các trường như service, level và trace_id dễ lọc, tổng hợp.
C. Log JSON tự động sinh trace xuyên dịch vụ không cần context.
D. Log JSON luôn ít chi phí hơn mọi loại metric time series.
Đáp án đúng: B

Câu 17. Một log event ở level ERROR nên được dùng khi nào?
A. Khi có lỗi cần điều tra, kèm ngữ cảnh và mức tác động.
B. Khi ghi mọi request thành công để lập biểu đồ throughput.
C. Khi ghi định kỳ mọi giá trị Gauge mỗi giây trong service.
D. Khi mô tả hoạt động bình thường không cần xem xét gì thêm.
Đáp án đúng: A

Câu 18. Thông tin nào nên tránh ghi trực tiếp trong log sản xuất?
A. Token đăng nhập, mật khẩu hoặc dữ liệu riêng tư thô.
B. Trace ID được tạo theo quy tắc không chứa thông tin mật.
C. Tên service và phiên bản release dùng để đối chiếu lỗi.
D. HTTP status cùng thời gian xử lý của request đã hoàn tất.
Đáp án đúng: A

Câu 19. Để nối log cùng một request qua nhiều service, cần duy trì gì?
A. Một request ID mới không liên quan ở từng service.
B. Giá trị CPU giống nhau trên mọi instance xử lý.
C. Correlation ID hoặc trace ID nhất quán trong các bước.
D. Một timestamp tuyệt đối giống hệt nhau ở mọi dòng log.
Đáp án đúng: C

Câu 20. Trong distributed tracing, span thường đại diện cho điều gì?
A. Toàn bộ những metric thuộc cùng một namespace Kubernetes.
B. Một dòng log text hoàn chỉnh của mọi server đang chạy.
C. Một thao tác có thời gian bắt đầu, kết thúc và thuộc tính.
D. Một đợt deploy chứa tất cả commit của ứng dụng trong ngày.
Đáp án đúng: C

Câu 21. Trace ID và Span ID khác nhau thế nào trong một distributed trace?
A. Trace ID chỉ nhận diện Pod; Span ID chỉ nhận diện namespace.
B. Trace ID liên kết toàn trace; Span ID nhận diện từng span.
C. Trace ID luôn thay ở mỗi service; Span ID giữ nguyên toàn bộ.
D. Trace ID dùng cho metric; Span ID dùng riêng cho CPU profile.
Đáp án đúng: B

Câu 22. Vì sao cần truyền trace context qua HTTP header hoặc metadata RPC?
A. Để giảm TTL DNS của mọi request truyền qua service mesh.
B. Để buộc mọi RPC chạy cùng luồng CPU với lời gọi trước.
C. Để span tại dịch vụ kế tiếp liên hệ đúng trace đang chạy.
D. Để loại bỏ hoàn toàn nhu cầu lấy mẫu trace ở backend.
Đáp án đúng: C

Câu 23. Đâu là khác biệt giữa head sampling và tail sampling cho traces?
A. Head luôn giữ request lỗi; tail luôn chỉ giữ request nhanh.
B. Head dùng profiler CPU; tail dùng histogram latency.
C. Head quyết định sớm; tail quyết định sau khi có dữ liệu.
D. Head chỉ áp dụng log; tail chỉ áp dụng Gauge trong metric.
Đáp án đúng: C

Câu 24. Khi tăng tỷ lệ lấy mẫu traces, đánh đổi điển hình là gì?
A. Giảm số lượng request đi qua gateway ở tầng dữ liệu mạng.
B. Thêm dữ liệu điều tra và tốn nhiều tài nguyên lưu trữ.
C. Loại bỏ nhu cầu instrument ứng dụng và propagate trace.
D. Giảm dung lượng log mà không đổi cấu hình của logging.
Đáp án đúng: B

Câu 25. Exemplar gắn với metric latency thường hỗ trợ điều tra bằng cách nào?
A. Liên kết điểm đo hoặc bucket với trace mẫu có liên quan.
B. Thay toàn bộ trace storage bằng một giá trị latency trung bình.
C. Làm Counter biến thành Gauge mà không mất nhãn hiện có.
D. Thay đổi timeout của upstream dựa vào một điểm đo chậm.
Đáp án đúng: A

Câu 26. OpenTelemetry SDK trong ứng dụng thường dùng để làm gì?
A. Điều phối tất cả Pod thay cho Kubernetes scheduler.
B. Tạo và phát telemetry từ mã đã được instrument.
C. Tự thiết lập database phân tích log trên mọi node.
D. Thay thế toàn bộ endpoint mạng của reverse proxy.
Đáp án đúng: B

Câu 27. Trong OpenTelemetry Collector, ba nhóm thành phần pipeline thường là gì?
A. Receivers nhận, processors xử lý, exporters gửi.
B. Resolvers nhận, schedulers xử lý và routers gửi.
C. Reporters nhận, serializers xử lý và loaders gửi.
D. Readers nhận, publishers xử lý và indexes gửi.
Đáp án đúng: A

Câu 28. Vì sao nên thêm resource attributes như `service.name` vào telemetry?
A. Để thay giao thức RPC thành HTTP trên toàn bộ ứng dụng.
B. Để đảm bảo mọi sample có timestamp giống hệt nhau.
C. Để tự mã hóa mọi trace payload không cần xác thực.
D. Phân nhóm telemetry nhất quán theo từng service.
Đáp án đúng: D

Câu 29. Nếu Collector bị nghẽn khi backend telemetry chậm, điều gì cần quan sát?
A. Queue, retry, dropped data và tải tài nguyên Collector.
B. Chỉ tỷ lệ cache hit của DNS mà không xem pipeline.
C. Chỉ thông lượng ứng dụng khi không có dữ liệu ingest.
D. Chỉ số certificate trong trust store của web client.
Đáp án đúng: A

Câu 30. SLI cho availability của API có thể được xác định theo cách nào?
A. Tổng số Pod đang chạy bất kể request có lỗi.
B. Thời gian trung bình người dùng mở trang dashboard.
C. Số lượt deploy thành công trong kho mã nguồn.
D. Tỷ lệ request hợp lệ đáp ứng tiêu chí thành công.
Đáp án đúng: D

Câu 31. SLO 99,9% request thành công trong 30 ngày nói lên điều gì?
A. Tối đa 0,1% request đo được phép không thành công.
B. Mục tiêu mọi request có latency dưới đúng 0,1 giây.
C. Mục tiêu tổng số request phải tăng ít nhất 99,9%.
D. Mục tiêu uptime của từng máy chủ đều phải là 100%.
Đáp án đúng: A

Câu 32. Error budget trong quản trị SLO được hiểu thế nào?
A. Tổng dung lượng ổ đĩa dành riêng cho access log.
B. Số lượng exception tối đa một Pod được phép ghi.
C. Khoản ngân sách mua thêm máy chủ để tăng throughput.
D. Phần sai lệch được phép so với mục tiêu độ tin cậy.
Đáp án đúng: D

Câu 33. Vì sao cảnh báo theo burn rate của error budget thường hữu ích?
A. Cảnh báo mọi log WARN kể cả khi người dùng không bị ảnh hưởng.
B. Phát hiện tốc độ tiêu hao ngân sách lỗi vượt ngưỡng.
C. Đếm mọi request thành công để luôn giữ tỷ lệ alert cố định.
D. Phát hiện duy nhất tình trạng ổ đĩa sắp hết dung lượng.
Đáp án đúng: B

Câu 34. Dùng cửa sổ ngắn và dài cùng lúc khi cảnh báo SLO giúp gì?
A. Bắt lỗi nhanh nhưng giảm nhiễu từ biến động ngắn hạn.
B. Bỏ qua mọi sự cố kéo dài hơn một lần scrape metrics.
C. Đảm bảo tất cả cảnh báo đều chỉ kích hoạt sau một tháng.
D. Tự phân tích root cause mà không cần logs hoặc traces.
Đáp án đúng: A

Câu 35. Cảnh báo nào có xu hướng gắn trực tiếp với tác động người dùng?
A. Một Pod từng restart nhưng toàn bộ request vẫn tốt.
B. Số lượng container image cũ còn nằm trên worker node.
C. Một dòng log DEBUG được ghi khi ứng dụng khởi động.
D. Tỷ lệ lỗi API vượt SLO trong một khoảng thời gian.
Đáp án đúng: D

Câu 36. Dashboard dành cho on-call nên ưu tiên nhóm thông tin nào?
A. Traffic, error rate, latency, saturation, mốc deploy.
B. Tên từng session người dùng và toàn bộ request body.
C. Chỉ số lượt đăng nhập dashboard của người quản trị.
D. Chỉ thông tin CPU của một pod dù hệ có nhiều dịch vụ.
Đáp án đúng: A

Câu 37. Khi p99 latency tăng nhưng trung bình gần như không đổi, nên suy ra gì?
A. Không có request nào bị chậm vì giá trị trung bình ổn.
B. Độ trễ đo được chắc chắn do trình duyệt dùng DNS cũ.
C. Đuôi phân phối có request chậm dù trung bình vẫn ổn.
D. Phần lớn request đã chuyển sang một protocol mới.
Đáp án đúng: C

Câu 38. Muốn tìm nguyên nhân độ trễ tăng sau release, thứ tự điều tra nào hợp lý?
A. Xóa toàn bộ dashboard trước để tránh bias khi điều tra.
B. Khởi động lại tất cả Pod trước khi chụp dữ liệu hoạt động.
C. Tăng timeout toàn hệ rồi mặc định lỗi đã được giải quyết.
D. Xem SLI, mốc deploy, trace chậm rồi log liên quan.
Đáp án đúng: D

Câu 39. Khi một span thiếu liên hệ với trace cha, nguyên nhân kỹ thuật nào đáng kiểm tra?
A. Kiểm tra trace context truyền giữa các service.
B. Thời gian scrape metrics lớn hơn TTL của bản ghi DNS.
C. Thư mục chứa profile CPU không có quyền ghi mới.
D. Histogram latency có bucket không cùng độ rộng.
Đáp án đúng: A

Câu 40. Với telemetry có dữ liệu nhạy cảm và chi phí lưu lớn, thiết kế nào phù hợp?
A. Bật ghi toàn bộ header và payload mà không giới hạn.
B. Gắn user ID duy nhất vào mọi metric để dễ phân tích.
C. Lọc dữ liệu mật và giới hạn thời gian lưu telemetry.
D. Đẩy tất cả trace thô vào log tập trung vô thời hạn.
Đáp án đúng: C
