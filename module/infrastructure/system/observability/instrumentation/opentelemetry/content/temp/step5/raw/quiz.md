Câu 1. Khi muốn theo dõi một request đi qua nhiều dịch vụ Spring Boot, OpenTelemetry giúp điều gì?
A. Gộp các request khác nhau thành cùng một metric duy nhất.
B. Chỉ đo mức CPU theo tiến trình, không cần request context.
C. Thu thập các span liên kết theo cùng trace xuyên dịch vụ.
D. Thay các lời gọi HTTP thật bằng sự kiện log tổng hợp.
Đáp án đúng: C

Câu 2. Khi dùng OpenTelemetry Java agent, cách khởi chạy ứng dụng nào thường phù hợp?
A. Thêm tham số JVM `-classpath:opentelemetry-javaagent.jar`.
B. Thêm tham số JVM `-Xbootclasspath:otel-collector.jar`.
C. Thêm tham số JVM `-Dspring.agent=otel-collector.jar`.
D. Chạy JVM với `-javaagent:/path/opentelemetry-javaagent.jar`.
Đáp án đúng: D

Câu 3. Lợi ích chính của auto-instrumentation trong ứng dụng Java là gì?
A. Tự ghi spans cho nhiều framework và thư viện được hỗ trợ.
B. Loại bỏ hoàn toàn việc đặt tên service và cấu hình exporter.
C. Bảo đảm mọi nghiệp vụ riêng đều có span đủ chi tiết.
D. Thay thế tất cả retry và timeout trong HTTP client.
Đáp án đúng: A

Câu 4. Spring Boot starter OpenTelemetry khác cách dùng Java agent ở khía cạnh nào?
A. Starter luôn chạy bên ngoài JVM như một sidecar độc lập.
B. Starter buộc viết lại toàn bộ controller để tạo span.
C. Tích hợp bằng dependency và cấu hình của ứng dụng.
D. Starter chỉ gửi dữ liệu qua Syslog, không hỗ trợ OTLP.
Đáp án đúng: C

Câu 5. `service.name` trong OpenTelemetry Resource chủ yếu phục vụ việc gì?
A. Định danh từng HTTP request để thay cho trace_id.
B. Định danh từng endpoint backend để thay cho route.
C. Tên dịch vụ phát telemetry, dùng để phân nhóm dữ liệu.
D. Định danh từng user trong nhãn metric của hệ thống.
Đáp án đúng: C

Câu 6. Cách cấu hình thông dụng để đặt service name khi chạy Java agent là gì?
A. Đặt `OTEL_TRACE_ID` bằng tên service khi khởi động JVM.
B. Đặt `OTEL_SERVICE_NAME` hoặc resource attribute tương ứng.
C. Đặt `OTEL_SPAN_ID` bằng tên namespace của Kubernetes.
D. Đặt `OTEL_SAMPLER` bằng địa chỉ host ứng dụng backend.
Đáp án đúng: B

Câu 7. Khi auto-instrumentation đã tạo span HTTP, lúc nào nên thêm manual span?
A. Khi muốn ghi lại bản sao của mọi span HTTP đã có sẵn.
B. Tạo span cho bước nghiệp vụ chưa được theo dõi tự động.
C. Khi cần đổi tất cả span đang chạy thành loại SERVER.
D. Khi muốn tránh phải truyền trace context qua HTTP.
Đáp án đúng: B

Câu 8. API nào phù hợp để bắt đầu một span thủ công trong Java?
A. Gọi `Span.current().newTrace("step")` để tạo span.
B. Gọi `Context.global().openSpan("step")` để tạo span.
C. Tạo span qua `tracer.spanBuilder("step").startSpan()`.
D. Gọi `SdkTracerProvider.createSpan("step")` để tạo span.
Đáp án đúng: C

Câu 9. Tác dụng của `span.makeCurrent()` trong OpenTelemetry Java là gì?
A. Đóng span hiện tại và gửi ngay tới backend telemetry.
B. Đưa span vào Context hiện hành để tạo span con phù hợp.
C. Chuyển span thành metrics Counter theo tên thao tác.
D. Thay trace_id của tất cả request đang chạy trong JVM.
Đáp án đúng: B

Câu 10. Khi tạo span thủ công, nên gọi `span.end()` trong khối `finally` vì sao?
A. Đảm bảo exporter luôn gửi dữ liệu bất kể bị mất mạng.
B. Đảm bảo span kết thúc dù thao tác ném exception.
C. Đảm bảo sampler giữ toàn bộ các span đang tạo.
D. Đảm bảo response HTTP luôn trả về status 200.
Đáp án đúng: B

Câu 11. Khi tạo span mới trong Context có span cha hiện hành, quan hệ thường là gì?
A. Span mới tự sinh trace_id độc lập cho mỗi lần gọi.
B. Span mới luôn được đánh dấu root dù có Context.
C. Span mới tự kết thúc cùng thời điểm span cha.
D. Span mới lấy parent từ Context đang được kích hoạt.
Đáp án đúng: D

Câu 12. Sự khác biệt giữa span attribute và span event là gì?
A. Attribute luôn là số; event chỉ được phép chứa chuỗi.
B. Attribute thay trace_id; event thay span_id của span.
C. Attribute mô tả dữ liệu; event đánh dấu thời điểm.
D. Attribute chỉ có ở log; event chỉ có ở metrics.
Đáp án đúng: C

Câu 13. Khi muốn ghi dấu thời điểm cache miss trong một span, cách nào phù hợp?
A. Thay trace_id của span thành chuỗi `cache.miss`.
B. Chuyển trạng thái span thành ERROR ngay khi cache miss.
C. Xóa tất cả span attribute để lưu thông tin cache miss.
D. Thêm event `cache.miss` vào span tại thời điểm xảy ra.
Đáp án đúng: D

Câu 14. Khi Java code bắt một exception, `span.recordException(e)` chủ yếu làm gì?
A. Tự biến exception thành một trace độc lập ngay lập tức.
B. Tự retry thao tác lỗi với backoff và jitter mặc định.
C. Ghi exception thành event của span để tìm nguyên nhân.
D. Tự trả HTTP 500 và kết thúc response từ controller.
Đáp án đúng: C

Câu 15. Nếu một span phản ánh thao tác thất bại, thao tác nào đánh dấu lỗi phù hợp?
A. Gọi `span.setStatus(StatusCode.OK)` để xác nhận thất bại.
B. Gọi `span.setAttribute("span_id", "ERROR")` để sửa ID.
C. Gọi `span.setStatus(StatusCode.ERROR)` để đặt status lỗi.
D. Gọi `span.end(StatusCode.ERROR)` để thay đổi trạng thái.
Đáp án đúng: C

Câu 16. Span kind `CLIENT` trong distributed tracing thường biểu thị điều gì?
A. Thao tác server đang nhận và xử lý request từ client.
B. Thao tác nội bộ của JVM không liên quan hệ thống khác.
C. Thao tác service đang nhận một message từ queue.
D. Thao tác phía client gửi lời gọi tới dịch vụ khác.
Đáp án đúng: D

Câu 17. Khi một service nhận HTTP request và tạo server span, kind phù hợp là gì?
A. `SpanKind.CLIENT` cho bước xử lý request đầu vào.
B. `SpanKind.PRODUCER` cho bước xử lý request đầu vào.
C. `SpanKind.SERVER` cho bước xử lý request đầu vào.
D. `SpanKind.INTERNAL` cho bước xử lý request đầu vào.
Đáp án đúng: C

Câu 18. Khi chạy tác vụ trên thread pool, vì sao có thể mất liên kết trace?
A. Span ID bắt buộc được đổi theo từng worker thread Java.
B. Trace ID không thể đi qua phương thức bất đồng bộ nào.
C. Exporter chỉ gửi telemetry từ thread chính của JVM.
D. Context có thể mất khi tác vụ chạy trên thread khác.
Đáp án đúng: D

Câu 19. Với `CompletableFuture` chạy ở executor khác, cách giữ trace context nào phù hợp?
A. Đổi tất cả span mới thành root span để tránh lỗi parent.
B. Ghi trace_id vào metric label của mỗi task rồi đọc lại.
C. Mang Context sang thread chạy callback rồi kích hoạt.
D. Tắt sampler ở callback để tự nối span về trace trước.
Đáp án đúng: C

Câu 20. W3C Trace Context dùng HTTP header nào để truyền trace identifiers?
A. `traceparent` mang trace ID, parent ID và trace flags.
B. `baggage` mang trace ID, parent ID và trace flags.
C. `authorization` mang trace ID, parent ID và trace flags.
D. `content-type` mang trace ID, parent ID và trace flags.
Đáp án đúng: A

Câu 21. Trong propagation, `tracestate` thường dùng cho nhu cầu nào?
A. Truyền trạng thái W3C dùng trong tracing qua service.
B. Chuyển mật khẩu exporter qua tất cả request HTTP.
C. Chuyển bucket boundaries của metric latency về client.
D. Chuyển cấu hình sampler của Collector thành JVM args.
Đáp án đúng: A

Câu 22. Baggage trong OpenTelemetry khác span attributes ở điểm nào?
A. Span attributes tự truyền sang mọi span ở service sau.
B. Baggage chỉ được ghi trong span và không truyền tiếp.
C. Span attributes luôn chứa cùng dữ liệu với Baggage.
D. Baggage có thể được truyền giữa service qua Context.
Đáp án đúng: D

Câu 23. Khi sử dụng Baggage cho request, nguyên tắc bảo mật nào phù hợp?
A. Không truyền secrets hoặc PII vì Baggage có thể lan rộng.
B. Đặt access token vào Baggage để Collector tự xác thực.
C. Đặt mật khẩu vào Baggage để backend đọc khi cần debug.
D. Giữ toàn bộ cookie người dùng trong Baggage dài hạn.
Đáp án đúng: A

Câu 24. Để tương quan log của Spring Boot với trace, nên bổ sung trường nào?
A. `trace_id` và `span_id` vào log record khi có Context.
B. `trace_id` và `span_id` vào đường dẫn HTTP request.
C. `trace_id` và `span_id` thành metric label mỗi request.
D. `trace_id` và `span_id` vào tên thread cố định của JVM.
Đáp án đúng: A

Câu 25. Vì sao gắn từng `request_id` thành label của Counter là ý tưởng không tốt?
A. Nhãn tự động khiến trace context bị mất khỏi HTTP.
B. Nhãn làm thay đổi kết quả StatusCode của các spans.
C. Nhãn khiến Collector không thể xuất logs qua OTLP.
D. Tránh label từng request vì cardinality tăng rất cao.
Đáp án đúng: D

Câu 26. Loại metric nào phù hợp để đo thời gian xử lý request trong ứng dụng?
A. Counter chỉ ghi nhãn tên request cho từng request mới.
B. Histogram ghi các quan sát latency để phân tích phân phối.
C. Gauge chỉ ghi số request đã hoàn tất từ lúc khởi động.
D. ObservableGauge chỉ ghi tổng số lỗi HTTP đã tích lũy.
Đáp án đúng: B

Câu 27. Theo OpenTelemetry semantic conventions, thuộc tính HTTP nào ghi method?
A. `http.request.method` biểu diễn phương thức của HTTP request.
B. `http.response.method` biểu diễn phương thức của HTTP request.
C. `http.target.method` biểu diễn phương thức của HTTP request.
D. `http.status.method` biểu diễn phương thức của HTTP request.
Đáp án đúng: A

Câu 28. Trong HTTP server telemetry, ý nghĩa của `http.route` là gì?
A. Query string đầy đủ của người dùng trong mọi request.
B. Route template như `/orders/{id}` thay cho path cụ thể.
C. IP của Pod đang xử lý request trên Kubernetes cluster.
D. Đường dẫn file hệ thống chứa access log của service.
Đáp án đúng: B

Câu 29. Head sampling trong tracing quyết định giữ trace khi nào?
A. Quyết định sớm khi trace hoặc span bắt đầu được tạo.
B. Quyết định sau khi toàn bộ spans đã tới Collector.
C. Quyết định sau khi dashboard tính xong p99 latency.
D. Quyết định khi log ERROR đầu tiên đã được lưu.
Đáp án đúng: A

Câu 30. Ý nghĩa của `ParentBased` sampler thường là gì?
A. Luôn sample mọi child span ngay cả khi parent không sampled.
B. Tôn trọng sampling decision của parent khi parent hợp lệ.
C. Chỉ giữ span không có parent thuộc cùng một Java process.
D. Buộc Collector sửa trace ID của mọi span đã nhận.
Đáp án đúng: B

Câu 31. Ưu điểm của tail sampling tại Collector trong việc tìm lỗi là gì?
A. Chọn span trước khi request hoàn tất tại thread gọi HTTP.
B. Chọn trace sau khi xét kết quả hoặc độ trễ của các span.
C. Chọn metric series theo label trước khi thu thập request.
D. Chọn profile CPU chỉ dựa vào timeout của HTTP client.
Đáp án đúng: B

Câu 32. Nếu một trace không được lấy mẫu, cần hiểu về dữ liệu metric thế nào?
A. Toàn bộ Counter và Histogram cùng request đều phải mất.
B. Ứng dụng sẽ tự vô hiệu hóa metrics SDK khi trace bị bỏ.
C. Collector sẽ đổi toàn bộ metrics thành unsampled spans.
D. Metrics vẫn được xuất qua pipeline độc lập với trace.
Đáp án đúng: D

Câu 33. OTLP là gì trong kiến trúc OpenTelemetry?
A. Cấu trúc database chỉ dành cho việc lưu CPU flame graph.
B. Giao thức trao đổi telemetry giữa SDK, Collector và backend.
C. Định dạng HTTP cookie truyền danh tính người dùng cuối.
D. Bộ điều phối task của Java dùng để phát trace bất đồng bộ.
Đáp án đúng: B

Câu 34. Trong cấu hình Java agent, biến `OTEL_EXPORTER_OTLP_ENDPOINT` thường đặt gì?
A. Tên của span đầu tiên khi ứng dụng Spring Boot chạy.
B. Địa chỉ đích OTLP để gửi telemetry đến Collector.
C. Số lượng log record tối đa trước khi JVM kết thúc.
D. Danh sách những URL ứng dụng được phép gọi HTTP.
Đáp án đúng: B

Câu 35. Trong Collector, `receivers` có nhiệm vụ chính nào?
A. Nhận telemetry do SDK và agent gửi đến Collector.
B. Xuất telemetry ra backend phân tích hoặc lưu trữ.
C. Lọc PII và gom batch trước khi xuất telemetry.
D. Quy định quyền truy cập database của ứng dụng.
Đáp án đúng: A

Câu 36. Trong Collector, `processors` thường được dùng vào việc gì?
A. Khởi động ứng dụng Spring Boot từ file JAR.
B. Phân giải các DNS record của server ứng dụng.
C. Chỉ tạo endpoint nhận request HTTP từ client.
D. Processors lọc, biến đổi hoặc batch telemetry.
Đáp án đúng: D

Câu 37. Trong Collector, `exporters` thực hiện công việc nào?
A. Chuyển telemetry đã xử lý đến hệ thống đích.
B. Nhận HTTP request từ controller Spring Boot.
C. Tự instrument toàn bộ thư viện Java trong JVM.
D. Khởi tạo tất cả Resource attributes của SDK.
Đáp án đúng: A

Câu 38. Khi Java agent gửi OTLP/gRPC tới Collector, cổng thông dụng nào nên kiểm tra?
A. Cổng 4317 nếu Collector bật OTLP/gRPC receiver.
B. Cổng 4318 của receiver OTLP/gRPC nếu đã được bật.
C. Cổng 9090 của receiver OTLP/gRPC nếu đã được bật.
D. Cổng 9411 của receiver OTLP/gRPC nếu đã được bật.
Đáp án đúng: A

Câu 39. Nếu trace của một request mất span ở service kế tiếp, hướng điều tra nào hợp lý?
A. Tăng timeout JVM mà không xem headers giữa các dịch vụ.
B. Xóa mọi span được ghi bởi HTTP server rồi thử lại.
C. Kiểm tra propagation headers, Context và sampling ở hai đầu.
D. Đổi route của mọi HTTP request sang một backend duy nhất.
Đáp án đúng: C

Câu 40. Khi pipeline logs/traces có thể chứa token, nên xử lý telemetry thế nào?
A. Xuất nguyên Authorization header để tiện truy vấn lâu dài.
B. Gắn access token vào Baggage để tìm được mọi trace.
C. Thêm mật khẩu người dùng vào tất cả span attributes.
D. Redact dữ liệu nhạy cảm và giới hạn quyền cùng retention.
Đáp án đúng: D
