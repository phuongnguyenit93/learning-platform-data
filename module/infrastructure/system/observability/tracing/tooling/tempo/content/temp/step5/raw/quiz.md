Câu 01. Vai trò chính của Grafana Tempo trong observability là gì?
A. Lưu trữ và truy vấn distributed traces từ các ứng dụng.
B. Thu thập metrics hệ điều hành và lưu thành time series.
C. Lập chỉ mục toàn văn log rồi cung cấp LogQL.
D. Phân tích CPU profiles và tạo flame graph cho process.
Đáp án đúng: A

Câu 02. Tempo có thể tiếp nhận trace qua những giao thức phổ biến nào?
A. Tempo nhận OTLP, Jaeger và Zipkin trace protocols.
B. SQL, Jaeger và Prometheus exposition.
C. Prometheus Remote Write, OTLP và syslog.
D. Loki Push API, Graphite và StatsD.
Đáp án đúng: A

Câu 03. Collector thường gửi trace tới Tempo bằng cách nào?
A. Dùng Loki push exporter qua HTTP hoặc syslog.
B. Dùng Zipkin query API để Tempo kéo trace về.
C. Dùng OTLP exporter qua gRPC hoặc HTTP.
D. Dùng Prometheus remote_write exporter qua HTTP.
Đáp án đúng: C

Câu 04. Trong triển khai production, vì sao Collector exporter nên có retry và queue?
A. Giữ dữ liệu tạm khi Tempo hoặc mạng gián đoạn ngắn.
B. Giảm số span được instrument trong ứng dụng nguồn.
C. Thay thế retention và compaction ở Tempo backend.
D. Đảm bảo mọi trace luôn được lưu vô thời hạn.
Đáp án đúng: A

Câu 05. Tempo dùng backend nào làm nơi lưu trace dài hạn?
A. Bộ nhớ RAM của distributor và query frontend.
B. Object storage như S3, GCS hoặc Azure Blob.
C. Prometheus TSDB trên từng node querier.
D. Loki index store dùng chung cho mọi log stream.
Đáp án đúng: B

Câu 06. Local filesystem backend của Tempo phù hợp nhất với tình huống nào?
A. Chia sẻ dữ liệu giữa nhiều tenant qua nhiều cluster.
B. Thay object storage cho hệ thống có retention dài.
C. Lưu trữ production đa vùng với khả năng mở rộng cao.
D. Phát triển và kiểm thử trên môi trường đơn giản.
Đáp án đúng: D

Câu 07. Trong Tempo 3 microservices mode, write path cơ bản đi theo luồng nào?
A. Distributor, querier, query frontend rồi object storage.
B. Query frontend, Kafka, live-store rồi distributor.
C. Distributor, Kafka, block-builder rồi object storage.
D. Block-builder, distributor, querier rồi live-store.
Đáp án đúng: C

Câu 08. Trong Tempo monolithic mode, distributor chuyển trace mới tới đâu?
A. Đẩy tới backend worker để compaction ngay lập tức.
B. Ghi vào Kafka rồi chờ block-builder xử lý.
C. Đẩy trực tiếp tới live-store trong cùng tiến trình.
D. Gửi trace sang query frontend để lập chỉ mục.
Đáp án đúng: C

Câu 09. Live-store trong kiến trúc Tempo phục vụ loại dữ liệu nào?
A. Trace gần đây chưa được đọc từ block lưu dài hạn.
B. Metric RED đã được remote-write sang Prometheus.
C. Metadata tenant và cấu hình runtime overrides.
D. Trace lịch sử đã hết retention trong object storage.
Đáp án đúng: A

Câu 10. Query frontend trong Tempo có nhiệm vụ nào?
A. Nhận span ingest, kiểm tra giới hạn và ghi vào Kafka.
B. Nhận truy vấn, chia nhỏ công việc và hợp nhất kết quả.
C. Tạo Parquet block rồi tải dữ liệu lên object storage.
D. Xóa block hết hạn và cập nhật chính sách tenant.
Đáp án đúng: B

Câu 11. Querier lấy dữ liệu từ đâu để trả kết quả truy vấn?
A. Từ Alloy local cache và file positions trên node.
B. Chỉ từ Kafka vì object storage không thể được truy vấn.
C. Chỉ từ Prometheus vì Tempo không giữ trace gốc.
D. Live-store cho dữ liệu mới và object storage cho dữ liệu lịch sử.
Đáp án đúng: D

Câu 12. Backend scheduler và worker đảm nhiệm nhóm công việc nào?
A. Compaction, retention và duy trì blocklist.
B. Instrument ứng dụng, tạo span và truyền context.
C. Xử lý log multiline và tạo Loki stream labels.
D. Scrape exporter, relabel target và gửi metrics.
Đáp án đúng: A

Câu 13. Trong Tempo hiện đại, backend scheduler có đặc điểm vận hành nào?
A. Mỗi worker phải chạy một scheduler riêng biệt.
B. Chạy stateless và tự nhận job không cần điều phối.
C. Chạy một instance điều phối các job backend.
D. Chỉ hoạt động khi Grafana query một trace ID.
Đáp án đúng: C

Câu 14. Backend workers được mở rộng theo cách nào?
A. Tăng số query frontend để chạy compaction.
B. Tăng số scheduler để chia sẻ cùng một work cache.
C. Thêm worker để xử lý nhiều job backend song song.
D. Tạo một object storage bucket riêng cho mỗi worker.
Đáp án đúng: C

Câu 15. Compaction giúp cải thiện hệ thống Tempo chủ yếu ra sao?
A. Chuyển trace thành metric trước khi lưu object storage.
B. Xóa index để giảm thời gian truy vấn theo trace ID.
C. Chia block lớn thành nhiều block nhỏ để tăng song song.
D. Gộp block nhỏ để querier phải quét ít block hơn.
Đáp án đúng: D

Câu 16. Retention trong Tempo có tác dụng gì?
A. Giữ block lâu hơn khi có nhiều query cùng lúc.
B. Giảm sampling rate khi storage sắp đầy.
C. Xóa block đã vượt quá thời hạn lưu cấu hình.
D. Chuyển block cũ sang live-store để truy cập nhanh.
Đáp án đúng: C

Câu 17. Để các span từ nhiều service Java thuộc cùng distributed trace, cần làm gì?
A. Gửi span của các service vào cùng bucket lưu trữ.
B. Truyền trace context qua từng lời gọi liên service.
C. Đặt cùng service.name cho mọi ứng dụng trong hệ thống.
D. Đồng bộ đồng hồ các host trước mỗi lần gọi HTTP.
Đáp án đúng: B

Câu 18. Trace block mặc định của Tempo sử dụng định dạng lưu trữ nào?
A. Apache Parquet, định dạng dữ liệu lưu trữ theo cột.
B. Prometheus TSDB, định dạng chunk theo thời gian.
C. Loki chunk, dữ liệu log nén theo stream labels.
D. JSON Lines, định dạng văn bản cho từng bản ghi.
Đáp án đúng: A

Câu 19. TraceQL được thiết kế chủ yếu để truy vấn gì?
A. Metric samples theo label và khoảng scrape.
B. Span và trace theo thuộc tính, thời gian và cấu trúc.
C. Log lines theo chuỗi, regex và parser stages.
D. CPU samples theo stack frame và process name.
Đáp án đúng: B

Câu 20. Trong TraceQL, resource attribute khác span attribute ở đâu?
A. Resource mô tả thực thể phát sinh span; span mô tả thao tác.
B. Resource chỉ dùng cho logs; span chỉ dùng cho metrics.
C. Resource chỉ chứa duration; span chỉ chứa service name.
D. Resource là thuộc tính của trace storage; span của Grafana.
Đáp án đúng: A

Câu 21. TraceQL có thể chọn trace dựa trên yếu tố nào?
A. Thuộc tính span, thời lượng và quan hệ giữa các span.
B. Chỉ tên tenant và kích thước Parquet block.
C. Chỉ trạng thái exporter và số lần retry OTLP.
D. Chỉ trace ID và bucket lưu block tương ứng.
Đáp án đúng: A

Câu 22. TraceQL structural query hữu ích nhất khi muốn làm gì?
A. Tìm metric series có cùng bộ label giữa hai service.
B. Tìm quan hệ parent-child giữa các span trong một trace.
C. Tìm log line có cùng timestamp trong nhiều tenant.
D. Tìm block object storage có cùng thời điểm compaction.
Đáp án đúng: B

Câu 23. Tìm trace theo Trace ID khác TraceQL search tổng quát thế nào?
A. Tìm tenant dựa trên header của truy vấn Grafana.
B. Tìm nhiều trace dựa trên điều kiện span và cấu trúc.
C. Tra cứu trực tiếp một trace đã biết định danh.
D. Tổng hợp request rate từ tất cả span đã ingest.
Đáp án đúng: C

Câu 24. TraceQL metrics cho phép thực hiện việc gì?
A. Tạo service graph mà không cần quan hệ giữa các span.
B. Thay thế object storage bằng metric backend.
C. Ghi mọi trace thành time series lâu dài trong Prometheus.
D. Tính toán metric trực tiếp từ trace data bằng truy vấn.
Đáp án đúng: D

Câu 25. Metrics-generator của Tempo là thành phần gì?
A. Thành phần tùy chọn tạo metrics từ các span được ingest.
B. Thành phần bắt buộc nhận mọi trace trước distributor.
C. Thành phần lưu Parquet block và phục vụ TraceQL query.
D. Thành phần xác thực tenant và kiểm tra quyền đọc.
Đáp án đúng: A

Câu 26. Span metrics processor thường tạo nhóm metric nào?
A. Request count, duration và kích thước span đã ingest.
B. Trace ID count, tenant count và số block đã compaction.
C. CPU utilization, memory usage và disk I/O của host.
D. Log volume, số label và thời gian ingest.
Đáp án đúng: A

Câu 27. Span metrics có thể tăng cardinality vì lý do nào?
A. Mỗi trace ID bị tự động biến thành một label bắt buộc.
B. Mỗi querier replica tạo một metric series cho mỗi query.
C. Mỗi tổ hợp dimension được bật có thể tạo series riêng.
D. Mỗi block Parquet luôn tạo đúng một metric series.
Đáp án đúng: C

Câu 28. Service graph được xây dựng từ tín hiệu nào trong trace?
A. Tên bucket và block ID trong object storage.
B. Metric labels của Prometheus và Loki stream.
C. Các lần retry của OTLP exporter trong Collector.
D. Quan hệ parent-child giữa span của các service.
Đáp án đúng: D

Câu 29. Để hiển thị Service Graph trong Grafana, cần kết nối thành phần nào?
A. Tempo data source với Grafana dashboard JSON archive.
B. Loki data source với object storage bucket Tempo.
C. Pyroscope data source với Prometheus remote write.
D. Metrics backend Prometheus với Tempo data source.
Đáp án đúng: D

Câu 30. Khi trace bị sample bỏ trước khi đến Tempo, metrics-generator sẽ thấy gì?
A. Chỉ các span lỗi do Tempo tự áp dụng tail sampling.
B. Chỉ các span còn lại sau sampling ở collector.
C. Không span nào vì sampling chỉ áp dụng ở query time.
D. Toàn bộ request gốc vì Tempo tái tạo span đã bị bỏ.
Đáp án đúng: B

Câu 31. Nếu cần metrics phản ánh traffic trước sampling, nên cân nhắc đặt generator ở đâu?
A. Trong Tempo sau khi chỉ các trace đã sample được ingest.
B. Trong Grafana sau khi người dùng mở service graph.
C. Trong object storage khi compactor gộp các block.
D. Trong collector pipeline trước bước sampling loại span.
Đáp án đúng: D

Câu 32. Tempo bật multi-tenancy nhận tenant ID qua cơ chế nào?
A. Query parameter trace_id trên mọi request.
B. Label service.name trong mỗi span resource.
C. Tên bucket S3 gắn với endpoint OTLP.
D. Header X-Scope-OrgID trên request.
Đáp án đúng: D

Câu 33. Khi bật multitenancy_enabled, yêu cầu nào được áp dụng?
A. Chỉ Grafana cần tenant; collector không cần gửi.
B. Tempo tự suy ra tenant từ service.name trong span.
C. Các request phải cung cấp X-Scope-OrgID hợp lệ.
D. Chỉ write request cần tenant; query có thể bỏ qua.
Đáp án đúng: C

Câu 34. Để tenant isolation hoạt động trên cả ingest và query, cần cấu hình gì?
A. Chỉ gắn tenant tag trên dashboard Grafana.
B. Cùng tenant context trên exporter và Tempo data source.
C. Chỉ cấu hình tenant trong object storage bucket policy.
D. Chỉ thêm tenant ID vào span name ở ứng dụng.
Đáp án đúng: B

Câu 35. Vì sao không nên tin tenant header do client không xác thực tự chọn?
A. Header được mã hóa tự động bởi OTLP nên không thể giả.
B. Header chỉ quyết định compression nên không ảnh hưởng cách ly.
C. Client có thể giả tenant và ghi hoặc đọc sai phạm vi.
D. Tempo luôn bỏ qua tenant header từ request bên ngoài.
Đáp án đúng: C

Câu 36. Per-tenant overrides trong Tempo thường dùng để điều chỉnh gì?
A. Port listener, TLS certificate và tên process hệ điều hành.
B. Giới hạn ingest, retention và cấu hình metrics-generator.
C. Sampling SDK, log level và số thread của ứng dụng.
D. Màu dashboard, tên datasource và biến Grafana.
Đáp án đúng: B

Câu 37. Khi ingest bị rate limited, nên kiểm tra thông số nào trước?
A. Query timeout, blocklist polling và số dashboard panel.
B. TraceQL syntax, Grafana folder và Prometheus scrape interval.
C. Object storage lifecycle và số lượng tenant trong header.
D. Rate limit, burst allowance và kích thước trace tối đa.
Đáp án đúng: D

Câu 38. Object storage cost của Tempo thường chịu ảnh hưởng bởi yếu tố nào?
A. Số service name được gắn vào resource attributes.
B. Số dashboard Grafana và số lần người dùng refresh.
C. Số trace ID đã được tìm kiếm trong query frontend.
D. Dung lượng giữ lại và số thao tác GET, PUT, LIST.
Đáp án đúng: D

Câu 39. Query đọc object storage chậm có thể được cải thiện bằng cách nào?
A. Giảm blocklist polling xuống mức thấp nhất bất kể nhu cầu.
B. Cache bloom filters, Parquet pages và metadata cần thiết.
C. Ghi thêm span attributes vào mọi trace cũ trong bucket.
D. Tắt compaction để querier đọc nhiều block nhỏ hơn.
Đáp án đúng: B

Câu 40. Service graph hiển thị rỗng dù trace đã vào Tempo. Cần kiểm tra điều gì?
A. TraceQL datasource đã bật log pipeline multiline.
B. Metrics generation và Prometheus datasource được liên kết.
C. Object storage bucket có quyền ghi từ Grafana frontend.
D. Querier đã bật Prometheus scrape cho mọi ứng dụng.
Đáp án đúng: B
