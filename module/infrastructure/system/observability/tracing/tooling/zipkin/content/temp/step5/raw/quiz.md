Câu 1. Distributed tracing giúp người vận hành hiểu điều gì trong kiến trúc nhiều dịch vụ?
A. Tổng số request mà từng máy chủ nhận trong một khoảng thời gian.
B. Đường đi và thời gian xử lý của một request qua nhiều dịch vụ.
C. Trạng thái cấu hình và phiên bản triển khai của từng service.
D. Mức sử dụng CPU và bộ nhớ của mọi container trong cụm.
Đáp án đúng: B

Câu 2. Một trace trong Zipkin thường gồm những thành phần nào?
A. Nhiều metric series có chung tên service và instance.
B. Một log record duy nhất chứa toàn bộ request payload.
C. Nhiều span liên quan cùng mô tả một luồng công việc.
D. Các dependency được suy ra từ tên host và port.
Đáp án đúng: C

Câu 3. Một span trong distributed tracing đại diện cho điều gì?
A. Một operation có thời điểm bắt đầu và thời lượng.
B. Một nhóm metric được tổng hợp theo service và endpoint.
C. Một bản ghi log bất kỳ được gửi từ ứng dụng nguồn.
D. Một kết nối TCP tồn tại trong toàn bộ vòng đời ứng dụng.
Đáp án đúng: A

Câu 4. Trường `traceId` trong các span liên quan có vai trò gì?
A. Xác định duy nhất service tạo ra span đầu tiên.
B. Liên kết các span thuộc cùng một trace.
C. Biểu diễn quan hệ trực tiếp giữa span cha và span con.
D. Lưu thời gian bắt đầu của request xuyên dịch vụ.
Đáp án đúng: B

Câu 5. Trường `parentId` của span thường biểu thị điều gì?
A. ID của service nhận request tiếp theo trong chuỗi.
B. ID của trace gốc được tạo ở gateway.
C. ID của span cha trực tiếp trong cùng trace.
D. ID của exporter gửi span tới Zipkin collector.
Đáp án đúng: C

Câu 6. Một root span trong trace thường có đặc điểm nào?
A. Không có `parentId` vì nó khởi đầu trace.
B. Có `parentId` trỏ tới chính `traceId` của nó.
C. Luôn có kind là `SERVER` bất kể vị trí xử lý.
D. Không có timestamp hoặc duration trong dữ liệu.
Đáp án đúng: A

Câu 7. Quan hệ cha-con giữa các span giúp ích gì khi xem trace?
A. Thể hiện thứ tự gọi lồng nhau giữa các operation.
B. Tự động chứng minh mọi span con chạy tuần tự.
C. Thay thế việc truyền trace context giữa các dịch vụ.
D. Gộp thời gian các span thành một metric duy nhất.
Đáp án đúng: A

Câu 8. Trường `kind` trong mô hình span Zipkin thường mô tả điều gì?
A. Mức độ nghiêm trọng của lỗi trong service tạo span.
B. Định dạng lưu trữ được dùng cho span trong backend.
C. Chính sách retention áp dụng cho trace hiện tại.
D. Vai trò span như CLIENT, SERVER, PRODUCER hoặc CONSUMER.
Đáp án đúng: D

Câu 9. `localEndpoint` của span Zipkin thường chứa thông tin nào?
A. Địa chỉ backend lưu trữ span và cổng truy vấn.
B. Tên operation cùng thời lượng đã được chuẩn hóa.
C. Danh sách service con được gọi trong trace.
D. Thông tin service và host của phía local.
Đáp án đúng: D

Câu 10. `remoteEndpoint` thường giúp xác định điều gì?
A. Peer hoặc endpoint ở phía bên kia của lời gọi.
B. Process ID và phiên bản JVM của service hiện tại.
C. Trace ID và parent ID của span đang hiển thị.
D. Địa chỉ nơi Zipkin UI được triển khai.
Đáp án đúng: A

Câu 11. Trong mô hình Zipkin v2, `timestamp` và `duration` thường dùng đơn vị nào?
A. Millisecond cho thời điểm và nanosecond cho duration.
B. Microsecond cho thời điểm và thời lượng span.
C. Second cho thời điểm và millisecond cho duration.
D. Nanosecond cho cả timestamp và duration.
Đáp án đúng: B

Câu 12. Trong span Zipkin v2, `annotations` thường biểu diễn dữ liệu gì?
A. Các cặp key-value mô tả thuộc tính ổn định của service.
B. Các sự kiện gắn với timestamp và giá trị mô tả.
C. Các metric histogram được thu thập trong span.
D. Các quy tắc sampling đã áp dụng cho trace.
Đáp án đúng: B

Câu 13. Trường `tags` trong span Zipkin thường dùng để lưu gì?
A. Danh sách span con và thứ tự thực hiện của chúng.
B. Timestamp bắt đầu và duration của span.
C. Địa chỉ IP cùng port của storage backend.
D. Metadata dạng key-value gắn với span.
Đáp án đúng: D

Câu 14. Một cách phổ biến để ghi nhận thông tin lỗi trên span Zipkin là gì?
A. Đặt `traceId` thành chuỗi `error` để đánh dấu trace.
B. Gắn tag `error` cùng thông tin lỗi phù hợp.
C. Đổi `parentId` thành ID của service gây lỗi.
D. Xóa duration để UI nhận diện span thất bại.
Đáp án đúng: B

Câu 15. B3 multi-header propagation thường dùng nhóm header nào?
A. `traceparent`, `tracestate` và `baggage` theo W3C.
B. Các header B3 như TraceId, SpanId và Sampled.
C. `X-Request-Id`, `X-Session-Id` và `X-User-Id`.
D. `Zipkin-Trace`, `Zipkin-Span` và `Zipkin-Parent`.
Đáp án đúng: B

Câu 16. B3 single-header format truyền context bằng cách nào?
A. Đưa toàn bộ span JSON vào header `b3` của request.
B. Chỉ truyền trace ID, còn span ID luôn được tạo ở server.
C. Mã hóa service name và duration trong một header duy nhất.
D. Gói trace ID, span ID và sampling state trong header `b3`.
Đáp án đúng: D

Câu 17. Header W3C `traceparent` chứa thông tin nào?
A. Trace ID, service name, span name và duration.
B. Sampling probability, baggage và địa chỉ collector.
C. Phiên bản, định danh trace/span cha và flags.
D. Parent ID, endpoint IP, port và timestamp của span.
Đáp án đúng: C

Câu 18. Propagator trong tracing SDK có nhiệm vụ chính nào?
A. Lưu span vào backend và truy vấn trace theo ID.
B. Inject context vào carrier và extract từ carrier.
C. Tính latency giữa các service từ timestamp của log.
D. Chọn index hoặc table để lưu span trong Zipkin.
Đáp án đúng: B

Câu 19. Khi request chuyển qua HTTP client sang service khác, context propagation giúp điều gì?
A. Service nhận luôn tạo trace ID mới và tách khỏi request gốc.
B. Service nhận tiếp tục trace hiện tại với quan hệ span phù hợp.
C. Client truyền toàn bộ log history để server dựng lại trace.
D. Collector tự suy ra parent span từ địa chỉ IP của client.
Đáp án đúng: B

Câu 20. Khi công việc được chuyển sang thread hoặc executor bất đồng bộ, cần chú ý điều gì?
A. Tạo một Zipkin server riêng cho từng thread trong ứng dụng.
B. Dùng chung một span object mutable cho mọi request đồng thời.
C. Truyền hoặc khôi phục tracing context trên luồng thực thi mới.
D. Tắt propagation vì thread mới không thể thuộc trace cũ.
Đáp án đúng: C

Câu 21. Baggage trong tracing thường được dùng để làm gì?
A. Thay thế trace ID và span ID trong mọi protocol.
B. Lưu toàn bộ span đã hoàn tất trước khi export.
C. Mô tả cấu trúc index của storage backend.
D. Truyền metadata theo context qua các dịch vụ.
Đáp án đúng: D

Câu 22. Vì sao không nên đưa token hoặc dữ liệu cá nhân nhạy cảm vào baggage?
A. Baggage chỉ được lưu cục bộ nên không thể bảo vệ bằng TLS.
B. Zipkin tự động mã hóa mọi baggage trước khi hiển thị.
C. Baggage chỉ chứa số liệu nên không thể mang dữ liệu nhạy cảm.
D. Baggage có thể lan truyền rộng và bị ghi nhận ở nhiều hệ thống.
Đáp án đúng: D

Câu 23. Sampling trong distributed tracing nhằm mục đích gì?
A. Giảm số trace để cân bằng chi phí và quan sát.
B. Giảm số span trong một trace nhưng luôn giữ mọi trace ID.
C. Nén payload span trước khi truyền tới collector.
D. Chọn service nào được phép gửi request qua gateway.
Đáp án đúng: A

Câu 24. Head-based sampling thường đưa ra quyết định khi nào?
A. Sớm khi trace bắt đầu hoặc span đầu tiên được tạo.
B. Sau khi toàn bộ trace hoàn tất và mọi span đã đến storage.
C. Sau khi Zipkin UI tính được latency của từng service.
D. Chỉ khi Elasticsearch từ chối lưu một số span.
Đáp án đúng: A

Câu 25. Tail-based sampling khác head-based sampling ở điểm nào?
A. Luôn quyết định trước khi span đầu tiên được tạo.
B. Chỉ chọn span theo tên service mà không xét trace.
C. Được thực hiện duy nhất trong trình duyệt Zipkin UI.
D. Quyết định sau khi có dữ liệu của toàn trace.
Đáp án đúng: D

Câu 26. Tail sampling trong hệ sinh thái OpenTelemetry thường được triển khai ở đâu?
A. Dùng tail-sampling processor trong OTel Collector.
B. Trong Zipkin UI bằng cách ẩn span sau khi truy vấn.
C. Trong Elasticsearch mapping khi document được index.
D. Trong HTTP client trước khi inject trace context.
Đáp án đúng: A

Câu 27. Khi một trace không được sampled, điều gì vẫn có thể được thực hiện?
A. Luôn export toàn bộ span nhưng bỏ qua trace ID.
B. Xóa mọi trace header khỏi request tiếp theo.
C. Tự đổi sampling decision thành sampled ở mỗi service.
D. Vẫn propagate context dù không export span.
Đáp án đúng: D

Câu 28. Zipkin collector chịu trách nhiệm chính nào?
A. Tạo metric hệ thống cho từng JVM đang chạy.
B. Phát trace context vào mọi request outbound của ứng dụng.
C. Nhận span đã instrument rồi chuyển tiếp tới storage.
D. Hiển thị biểu đồ waterfall và form tìm kiếm cho người dùng.
Đáp án đúng: C

Câu 29. Thành phần storage trong kiến trúc Zipkin có vai trò gì?
A. Lưu span để có thể truy vấn sau khi collector nhận dữ liệu.
B. Tạo span trong ứng dụng trước khi HTTP request bắt đầu.
C. Inject B3 header vào request giữa các service.
D. Tự quyết định lỗi nào được gắn vào span.
Đáp án đúng: A

Câu 30. Zipkin query service và UI chủ yếu phục vụ mục đích nào?
A. Thu nhận span trực tiếp từ mọi ứng dụng instrumented.
B. Thay thế SDK để tự tạo span trong JVM.
C. Cấu hình firewall và TLS cho các service trong hệ thống.
D. Tìm trace, xem span và phân tích quan hệ cùng thời lượng.
Đáp án đúng: D

Câu 31. HTTP endpoint `POST /api/v2/spans` của Zipkin thường dùng để làm gì?
A. Trả danh sách service đã được ghi nhận.
B. Truy vấn trace theo service và khoảng thời gian.
C. Nhận dữ liệu span gửi tới collector.
D. Tạo dependency graph từ các span đã lưu.
Đáp án đúng: C

Câu 32. API `GET /api/v2/traces` thường phục vụ thao tác nào?
A. Truy vấn các trace phù hợp với tham số tìm kiếm.
B. Gửi batch span mới từ ứng dụng vào collector.
C. Cập nhật sampling probability của mọi service.
D. Xóa các span đã quá thời hạn retention.
Đáp án đúng: A

Câu 33. Zipkin API `GET /api/v2/services` thường trả về dữ liệu gì?
A. Danh sách trace ID còn đang nằm trong collector queue.
B. Danh sách exporter và receiver trong OpenTelemetry Collector.
C. Danh sách service name được biết tới trong storage.
D. Danh sách index cùng shard của Elasticsearch.
Đáp án đúng: C

Câu 34. Endpoint dependencies của Zipkin thường được dùng để làm gì?
A. Truy vấn quan hệ service theo thời gian.
B. Liệt kê các span con của một trace cụ thể.
C. Đọc baggage đã được inject vào request.
D. Tính sampling rate cho từng endpoint HTTP.
Đáp án đúng: A

Câu 35. Vì sao storage in-memory phù hợp hơn cho demo hoặc thử nghiệm?
A. Tự mở rộng qua nhiều node mà không cần cấu hình.
B. Dữ liệu thử nghiệm mất sau khi tiến trình dừng.
C. Bảo đảm retention dài hạn và backup tự động.
D. Tối ưu cho truy vấn lịch sử lớn trên production.
Đáp án đúng: B

Câu 36. Khi triển khai Zipkin production, retention thường được kiểm soát ở đâu?
A. Trong trường `parentId` của từng span.
B. Trong B3 header được gửi từ ứng dụng.
C. Retention do backend lưu trữ cấu hình.
D. Trong refresh interval của Zipkin UI.
Đáp án đúng: C

Câu 37. Một trace thiếu span giữa hai service thường nên được điều tra từ đâu?
A. Tăng độ rộng waterfall trong UI để hiện span bị ẩn.
B. Kiểm tra context, quyết định sample và luồng gửi.
C. Đổi trace ID của service downstream cho trùng upstream.
D. Xóa storage index rồi khởi động lại toàn bộ ứng dụng.
Đáp án đúng: B

Câu 38. Clock skew giữa các máy có thể gây ảnh hưởng gì khi xem trace?
A. Trace ID bị thay đổi mỗi khi request đi qua máy khác.
B. Sampling decision tự đổi từ sampled sang not sampled.
C. Zipkin tự loại mọi span có timestamp ở máy khác.
D. Timeline có thể lệch do timestamp giữa các host.
Đáp án đúng: D

Câu 39. Micrometer Tracing trong Spring Boot đóng vai trò nào?
A. Thay thế Zipkin storage bằng registry metrics trong JVM.
B. Chỉ thu thập log và chuyển chúng thành trace khi lỗi.
C. API tracing và bridge tới tracer triển khai.
D. Tạo dashboard Zipkin mà không cần instrument ứng dụng.
Đáp án đúng: C

Câu 40. Khi dùng OpenTelemetry Java với Zipkin exporter, exporter có nhiệm vụ gì?
A. Tạo HTTP server span cho mọi request mà không cần instrumentation.
B. Chuyển span đến Jaeger collector theo giao thức OTLP.
C. Chuyển các span đã kết thúc tới Zipkin collector theo định dạng hỗ trợ.
D. Chuyển span thành metric rồi gửi tới Prometheus backend.
Đáp án đúng: C
