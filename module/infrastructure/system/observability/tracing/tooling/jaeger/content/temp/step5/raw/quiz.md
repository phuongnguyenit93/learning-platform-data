1. Đặc điểm kiến trúc nào mô tả đúng Jaeger v2?
A. Jaeger v2 chỉ là giao diện truy vấn và phải dùng collector v1.
B. Jaeger v2 dựa trên OTel Collector và hỗ trợ nhiều role.
C. Jaeger v2 thay thế OpenTelemetry SDK để tự instrument ứng dụng.
D. Jaeger v2 chỉ chạy như một agent sidecar cố định.
Đáp án đúng: B

2. Trong kiến trúc Jaeger, collector và query đảm nhiệm hai nhiệm vụ nào?
A. Collector dựng service map; query nhận OTLP và ghi spans vào storage.
B. Collector nhận và lưu spans; query cung cấp API cùng Jaeger UI.
C. Collector quản lý SDK sampling; query tự instrument các ứng dụng.
D. Collector lưu metrics; query chuyển logs thành các trace liên quan.
Đáp án đúng: B

3. All-in-one Jaeger v2 dùng in-memory storage phù hợp nhất với trường hợp nào?
A. Thử nghiệm và phát triển vì dữ liệu mất khi Jaeger restart.
B. Production nhiều node vì bộ nhớ được tự động chia sẻ giữa các replica.
C. Lưu trace dài hạn vì bộ nhớ tự ghi snapshot xuống object storage.
D. Triển khai đa vùng vì query có thể tái tạo trace từ SDK.
Đáp án đúng: A

4. Vì sao một hệ thống production có thể tách collector và query thành các role riêng?
A. Bắt buộc phải chạy hai loại database cho cùng một trace.
B. Chỉ role query mới có thể ghi dữ liệu vào storage backend.
C. Tách role giúp bỏ qua yêu cầu về storage bền vững.
D. Mở rộng độc lập collector write path và query read path.
Đáp án đúng: D

5. Ứng dụng gửi OTLP tới Jaeger bằng gRPC và HTTP thường dùng cặp cổng nào?
A. OTLP gRPC mặc định 4317; OTLP HTTP mặc định 4318.
B. Jaeger query gRPC dùng 16685; Jaeger UI HTTP dùng 16686.
C. Legacy Jaeger gRPC dùng 14250; legacy Thrift HTTP dùng 14268.
D. Remote sampling gRPC dùng 5779; sampling HTTP endpoint dùng 5778.
Đáp án đúng: A

6. Jaeger v2 nhận loại tín hiệu nào qua OTLP receiver?
A. Nhận đồng thời metrics, logs và traces rồi lưu cả ba trong Jaeger.
B. Nhận metrics; trace data phải được đổi thành log trước khi gửi.
C. Chỉ nhận trace data; metrics và logs cần backend khác.
D. Nhận logs và span events; span chính được lưu ở SDK.
Đáp án đúng: C

7. Jaeger v2 khác cách cấu hình Jaeger v1 ở điểm nào?
A. Đọc YAML pipeline qua --config; file hỗ trợ nội suy biến môi trường.
B. Đọc biến môi trường v1 trực tiếp và không cần file YAML.
C. Chỉ nhận command-line flags và không nhận file cấu hình YAML.
D. Dùng JSON riêng cho mỗi receiver, không khai báo pipeline.
Đáp án đúng: A

8. Trong cấu hình Collector-style, receiver, processor và exporter lần lượt có vai trò nào?
A. Receiver nhận data, processor biến đổi, exporter gửi tới đích.
B. Receiver nhận telemetry, lưu schema và cung cấp giao diện truy vấn.
C. Xác thực người dùng, chọn tenant và tạo service dependency graph.
D. Mở cổng mạng, cấp chứng thư và điều khiển lịch nâng cấp.
Đáp án đúng: A

9. Jaeger v2 có jaeger_storage extension để giải quyết nhu cầu nào?
A. Tạo một queue bền vững giữa SDK và mọi collector replica.
B. Tự động instrument ứng dụng và truyền trace context qua HTTP.
C. Tổng hợp metrics từ spans và xuất chúng thành dashboard.
D. Đăng ký backend có tên để writer và query cùng tham chiếu.
Đáp án đúng: D

10. jaeger_storage_exporter thường được cấu hình để làm nhiệm vụ gì?
A. Ghi spans vào backend đã đăng ký trong storage extension.
B. Nhận OTLP từ ứng dụng và tự phục vụ Jaeger Web UI.
C. Đọc traces từ backend và tính toán sampling probability.
D. Chuyển spans thành metrics rồi xuất tới Prometheus remote storage.
Đáp án đúng: A

11. jaeger_query extension cung cấp chức năng nào?
A. Nhận OTLP spans rồi chuyển tiếp chúng vào Kafka topic.
B. Cung cấp query APIs và Jaeger UI dùng storage đã cấu hình.
C. Tính adaptive sampling và cung cấp policy cho SDK.
D. Tạo index backend và compact trace blocks theo lịch.
Đáp án đúng: B

12. Khi cần một Jaeger binary chỉ chứa những component được tổ chức sử dụng, nên tiếp cận thế nào?
A. Sửa trực tiếp binary phát hành và loại bỏ component lúc chạy.
B. Cài một Jaeger agent riêng cho từng receiver cần sử dụng.
C. Tạo bản Jaeger tùy biến bằng OTel Collector Builder.
D. Chép exporter từ Jaeger v1 vào query extension của v2.
Đáp án đúng: C

13. Collector ghi thẳng vào storage nhưng lưu lượng tăng đột biến kéo dài. Rủi ro nào cần dự phòng?
A. Storage phải chịu tải đỉnh; queue RAM chỉ hấp thụ spike ngắn hạn.
B. Query tự động tăng số replica và giữ mọi spans trong RAM vô hạn.
C. Collector chuyển trace chưa ghi thành metrics để tránh mất dữ liệu.
D. Storage sẽ tự điều chỉnh sampling rate của SDK về một trăm phần trăm.
Đáp án đúng: A

14. Trong kiến trúc dùng Kafka làm buffer giữa collector và storage, luồng thành phần nào phù hợp?
A. Ingester nhận OTLP trực tiếp; collector đọc Kafka và phục vụ query.
B. Query xuất spans vào Kafka; collector đọc topic và tạo UI.
C. SDK ghi thẳng vào Kafka; query chuyển từng span sang storage.
D. Collector gửi spans vào Kafka; ingester đọc rồi ghi storage.
Đáp án đúng: D

15. Khi cần biết chắc span đã được ghi bền vững trước khi xác nhận thành công, điều kiện nào quan trọng?
A. Queue lớn khiến exporter xác nhận ngay khi enqueue.
B. Storage báo lỗi ghi; pipeline chờ kết quả trước khi ACK.
C. Batch processor trả success trước khi exporter ghi xong.
D. Tăng retry count mà không xét thời điểm acknowledge.
Đáp án đúng: B

16. Một Jaeger storage queue acknowledge ngay sau khi enqueue. Cấu hình nào giúp caller nhận kết quả ghi thực tế?
A. Tăng queue_size để mọi batch được xem là đã lưu thành công.
B. Tắt retry_on_failure để exporter không phải chờ backend.
C. Bật wait_for_result để chờ kết quả ghi từ storage backend.
D. Thêm batch processor trước exporter để đợi flush hoàn tất.
Đáp án đúng: C

17. Trong các backend phân tán được Jaeger hỗ trợ chính, lựa chọn nào đúng?
A. Redis, MySQL và MongoDB là các backend phân tán chính.
B. Prometheus, Loki và Tempo là các backend trace chính.
C. Cassandra, Elasticsearch và OpenSearch là backend chính.
D. SQLite, PostgreSQL và Memcached là các backend mặc định.
Đáp án đúng: C

18. Badger storage trong Jaeger phù hợp với đặc tính triển khai nào?
A. Cụm nhiều node cần phân mảnh dữ liệu và cân bằng tải tự động.
B. Badger dùng cho quy mô vừa, single instance, không scale ngang.
C. Cloud-native đa vùng cần replication tự động giữa các region.
D. Backend quy mô lớn cần scale ngang qua nhiều shard.
Đáp án đúng: B

19. Một tổ chức muốn kết nối Jaeger với storage tự phát triển qua gRPC. Backend cần triển khai những service nào?
A. Cần TraceReader, DependencyReader và TraceService.
B. CollectorService, QueryService và SamplingManager của Jaeger API.
C. Receiver, Processor và Exporter theo giao diện OTLP HTTP.
D. IndexReader, SpanWriter và MetricsQuery theo Prometheus API.
Đáp án đúng: A

20. Jaeger primary storage và archive storage khác nhau thế nào?
A. Primary chỉ giữ trace lỗi; archive tự nhận trace thành công.
B. Primary nhận trace ingest; archive giữ trace được người dùng lưu riêng.
C. Primary phục vụ query; archive nhận dữ liệu từ collector.
D. Primary lưu metrics; archive chứa logs đã chuẩn hóa.
Đáp án đúng: B

21. Head-based sampling quyết định giữ trace vào thời điểm nào?
A. Quyết định sau khi backend đã nhận đủ mọi span của trace.
B. Quyết định khi query API nhận yêu cầu mở trace trên UI.
C. Quyết định sau khi storage compaction hoàn tất một chu kỳ.
D. Quyết định ở đầu trace, thường tại SDK khi trace bắt đầu.
Đáp án đúng: D

22. Tail-based sampling khác head-based sampling ở điểm nào?
A. Chọn sau khi đã thu thập các spans trong trace.
B. Chọn trước khi ứng dụng tạo span đầu tiên.
C. Chọn theo tên index khi truy vấn storage.
D. Mỗi service tự quyết định sampling độc lập.
Đáp án đúng: A

23. Jaeger tail sampling processor hữu ích khi muốn giữ trace theo tiêu chí nào?
A. Giữ ngẫu nhiên một tỷ lệ spans mà không xét trace hoàn chỉnh.
B. Giữ mọi span của service có nhiều request nhất trong ngày.
C. Giữ trace lỗi hoặc chậm sau khi quan sát toàn trace.
D. Giữ trace theo thời điểm người dùng mở Jaeger UI.
Đáp án đúng: C

24. Jaeger remote sampling extension phục vụ mục đích gì?
A. Cung cấp sampling policy tập trung cho SDK hỗ trợ remote.
B. Nhận trace đã sample và ghi trực tiếp vào archive storage.
C. Phân tích service map rồi tự sửa instrumentation của ứng dụng.
D. Cấp quyền truy vấn trace theo service name cho người dùng.
Đáp án đúng: A

25. Adaptive sampling điều chỉnh sampling probability dựa trên cơ sở nào?
A. Đếm số người dùng mở UI và giới hạn số query mỗi phút.
B. Quan sát service/endpoint để đạt target traces mỗi giây.
C. Đo dung lượng storage còn trống rồi đặt xác suất chung cho mọi service.
D. Theo dõi số lỗi của collector và luôn tăng xác suất khi có lỗi.
Đáp án đúng: B

26. Vì sao quyết định head sampling nên được truyền theo trace context giữa các service?
A. Mỗi service chọn tỷ lệ riêng nhằm tăng số trace hoàn chỉnh.
B. Query service biết endpoint nào đã được instrument trong SDK.
C. Downstream tuân theo quyết định chung để giữ trace nhất quán.
D. Storage backend tự suy ra sampling decision từ span duration.
Đáp án đúng: C

27. Khi triển khai tail sampling trên nhiều collector replica, yêu cầu định tuyến nào quan trọng?
A. Mỗi span cần tới một replica khác nhau để phân tán tải đều.
B. Root span tới query replica còn child spans gửi vào storage.
C. Mọi span phải được gửi tới tất cả collector replica cùng lúc.
D. Các spans cùng trace phải tới cùng shard để sampler đủ ngữ cảnh.
Đáp án đúng: D

28. Khi điều tra vì sao một trace không xuất hiện trong Jaeger, kiểm tra nào nên làm sớm?
A. Tăng số replica query để tự khôi phục spans chưa được gửi.
B. Kiểm tra SDK có record và sample trace trước khi soi storage.
C. Xóa index cũ để Jaeger tạo lại dữ liệu trace đang thiếu.
D. Tắt toàn bộ processor để Jaeger tự sinh trace thay thế.
Đáp án đúng: B

29. SDK gửi OTLP bằng HTTP nhưng collector chỉ mở receiver gRPC. Triệu chứng nào có thể xảy ra?
A. Trace được lưu nhưng query API tự đổi service name.
B. Jaeger tự chuyển HTTP request sang gRPC dù không có listener.
C. Chỉ span attributes bị mất còn dữ liệu trace vẫn được ghi.
D. Export lỗi vì HTTP/gRPC protocol hoặc endpoint không khớp.
Đáp án đúng: D

30. Một processor filter loại bỏ child spans theo điều kiện quá rộng. Tác động nào cần lưu ý?
A. Jaeger tự tạo lại child spans từ parent span khi query.
B. Storage tự suy luận các spans bị lọc từ service dependency graph.
C. Chỉ metrics bị ảnh hưởng vì filter không tác động trace pipeline.
D. Trace có thể mất quan hệ cha-con và khó phân tích khi query.
Đáp án đúng: D

31. Memory limiter trong pipeline Jaeger/Collector giúp xử lý tình huống nào?
A. Tăng retention và tự nén dữ liệu trace đã ghi.
B. Phát sampling probability cho endpoint theo remote policy.
C. Giới hạn heap và tạo back-pressure khi bộ nhớ gần cạn.
D. Đẩy query nặng sang Kafka để giảm tải backend.
Đáp án đúng: C

32. Attributes processor có thể hỗ trợ công việc nào trong pipeline trace?
A. Tạo parent-child relationship và sửa trace ID cho spans.
B. Làm giàu resource attributes và redact trường nhạy cảm.
C. Tạo index storage và tự động xóa spans hết hạn.
D. Cấp remote sampling policy và xác minh chữ ký của SDK.
Đáp án đúng: B

33. Jaeger UI cần service dependency graph nhưng dữ liệu quan hệ chưa được tạo. Thành phần nào thường bổ sung việc này?
A. Query extension tự tạo service graph khi mở UI.
B. OTLP receiver tạo graph ngay khi nhận request.
C. Storage exporter tự chuyển span events thành dependency links.
D. Spark dependencies job tổng hợp spans thành dependency links.
Đáp án đúng: D

34. Service Performance Monitoring của Jaeger cần thêm loại backend nào?
A. Kafka topic để lưu histogram latency của từng endpoint.
B. Object storage để giữ metric samples cạnh trace blocks.
C. Jaeger archive storage để tính RED metrics khi người dùng query.
D. Dùng Prometheus-compatible storage để lưu metrics cho SPM.
Đáp án đúng: D

35. Muốn tra cứu một trace trong Jaeger UI, bộ lọc nào thường giúp thu hẹp kết quả?
A. Pod restart count, dung lượng image và trạng thái node Kubernetes.
B. Lọc theo service, operation, time range và các tag phù hợp.
C. Sampling probability, queue size và số consumer của Kafka.
D. Tên storage extension, phiên bản binary và số query replica.
Đáp án đúng: B

36. Jaeger query extension điều chỉnh clock skew giữa các spans nhằm mục đích gì?
A. Đồng bộ đồng hồ hệ điều hành trên tất cả host đang phát spans.
B. Sửa timestamp gốc trong storage để thay đổi thời gian thực tế.
C. Giảm lệch timestamp tương đối và hiển thị cảnh báo điều chỉnh.
D. Loại bỏ spans có timestamp nằm ngoài khoảng của parent.
Đáp án đúng: C

37. Khi chạy Jaeger v2 trên Kubernetes với cấu hình tùy chỉnh, cách cung cấp config nào phù hợp?
A. Mount YAML config vào container và chạy Jaeger với --config.
B. Đặt mọi pipeline trong annotation của Pod để Jaeger tự đọc.
C. Chỉ đặt biến môi trường v1 vì v2 không cần config file.
D. Lưu config trong Jaeger UI và để collector tự tải lúc startup.
Đáp án đúng: A

38. Cổng health check mặc định của Jaeger v2 healthcheckv2 extension là gì?
A. HTTP 16686 với endpoint /api/v3 để tra cứu trace.
B. gRPC 16685 với endpoint QueryService cho client.
C. Dùng healthcheckv2 qua HTTP 13133 tại endpoint /status.
D. HTTP 4318 với endpoint /v1/traces để nhận OTLP.
Đáp án đúng: C

39. Khi bảo vệ kết nối từ OpenTelemetry SDK tới Jaeger collector, cơ chế nào được hỗ trợ?
A. Basic authentication qua UDP legacy collector.
B. Mã hóa payload ở SDK nhưng không bảo vệ transport.
C. TLS hoặc mTLS trên cả OTLP gRPC lẫn OTLP HTTP.
D. mTLS chỉ bảo vệ kết nối query tới storage.
Đáp án đúng: C
