# Fallback khi backend telemetry lỗi

Telemetry giúp đội vận hành hiểu trạng thái ứng dụng, nhưng pipeline telemetry cũng có thể gặp sự cố. Collector có thể ngừng hoạt động, exporter không kết nối được, backend từ chối dữ liệu, mạng bị phân vùng hoặc quota lưu trữ bị đầy. Khi đó, ứng dụng Spring Boot vẫn cần xử lý nghiệp vụ trong giới hạn đã cam kết, đồng thời giảm mất mát telemetry và phục hồi có kiểm soát.

Thiết kế fallback cần trả lời ba câu hỏi: ứng dụng có tiếp tục phục vụ request không, tín hiệu nào còn được giữ lại và pipeline sẽ phục hồi như thế nào khi backend hoạt động trở lại. Với phần lớn hệ thống nghiệp vụ, lỗi telemetry là trạng thái suy giảm khả năng quan sát; nó không nên trở thành lỗi của giao dịch người dùng.

Bài này trình bày cách thiết kế fallback cho Micrometer Observation, metrics, logs và distributed tracing trong Spring Boot, từ ứng dụng đến OpenTelemetry Collector và backend.

## 1. Nhận diện vị trí xảy ra lỗi

Một pipeline phổ biến có các chặng:

1. Ứng dụng tạo Observation, meter, log event và span.
2. Micrometer registry hoặc tracing bridge ghi nhận tín hiệu trong tiến trình.
3. Exporter chuyển dữ liệu ra khỏi ứng dụng.
4. OpenTelemetry Collector hoặc agent nhận, xử lý và chuyển tiếp dữ liệu.
5. Backend tiếp nhận, lưu trữ, lập chỉ mục và cung cấp truy vấn.

Lỗi ở mỗi chặng có biểu hiện khác nhau. Không nên gộp tất cả thành một trạng thái “telemetry down”, vì cách khắc phục phụ thuộc vào nơi dữ liệu bị mất.

| Điểm lỗi | Biểu hiện | Rủi ro chính | Hướng fallback |
|---|---|---|---|
| Registry hoặc SDK trong ứng dụng | Không tạo được meter/span, cấu hình handler sai | Thiếu tín hiệu ngay từ nguồn | Giữ cấu hình tối thiểu, phát hiện lỗi cấu hình khi khởi động và có log chẩn đoán độc lập |
| Exporter hoặc kết nối mạng | Timeout, lỗi gửi, retry tăng | Queue đầy, mất tín hiệu hoặc chiếm tài nguyên | Export bất đồng bộ, timeout ngắn, retry có giới hạn và queue hữu hạn |
| Collector agent/sidecar | Ứng dụng không gửi được đến endpoint cục bộ | Dữ liệu chờ trong SDK rồi bị drop | Queue hữu hạn ở SDK, health check agent và đường gửi dự phòng nếu kiến trúc hỗ trợ |
| Collector gateway | Agent không chuyển tiếp được dữ liệu | Nhiều agent cùng tích lũy backlog | Queue/retry ở agent, nhiều gateway hoặc endpoint dự phòng |
| Backend ingest/storage | Collector gửi lỗi, quota hoặc storage cạn | Dữ liệu bị từ chối hoặc backlog tăng | Retry có giới hạn, persistent queue có quota, cảnh báo dung lượng và chính sách giảm tải |
| Query/UI | Dữ liệu đã ingest nhưng dashboard hoặc truy vấn lỗi | Đội trực tưởng rằng ứng dụng ngừng phát telemetry | Kiểm tra ingestion độc lập với query path; dùng API hoặc kiểm tra tín hiệu thay thế |

Phân biệt lỗi ingest và lỗi query rất quan trọng. Dashboard trống không chứng minh ứng dụng không phát telemetry. Có thể dữ liệu đã được nhận nhưng truy vấn hoặc giao diện đang lỗi. Hãy kiểm tra từ nguồn đến backend theo từng chặng.

## 2. Đặt nguyên tắc fallback trước khi chọn công nghệ

Một chiến lược fallback tốt có các nguyên tắc sau:

- **Không để telemetry giữ request nghiệp vụ.** Không thực hiện HTTP export đồng bộ trong controller, service hoặc Observation handler chạy trên request thread. Dùng registry/exporter và span processor có cơ chế xử lý bất đồng bộ phù hợp.
- **Giới hạn mọi tài nguyên.** Queue trong bộ nhớ, queue trên đĩa, số lần retry, thời gian timeout, số worker và thời gian flush đều cần giới hạn.
- **Chấp nhận mất một phần telemetry có kiểm soát.** Khi mọi đích nhận đều không khả dụng và buffer đã đầy, bỏ dữ liệu theo policy rõ ràng tốt hơn làm cạn heap hoặc treo ứng dụng.
- **Giữ tín hiệu có giá trị cao.** Duy trì metrics tổng hợp và các log vận hành cần thiết; sampling trace theo tải và ngân sách đã xác định.
- **Tách sức khỏe ứng dụng khỏi sức khỏe backend telemetry.** Lỗi backend không tự động biến ứng dụng thành unhealthy hoặc làm readiness thất bại.
- **Tự giám sát pipeline bằng kênh độc lập.** Không gửi duy nhất cảnh báo “exporter đang lỗi” qua chính exporter đang lỗi.
- **Phục hồi có kiểm soát.** Khi backend hoạt động lại, xả backlog theo tốc độ giới hạn để tránh tạo thêm một đợt quá tải.

Mục tiêu không phải bảo đảm mọi span và log đều được lưu trong mọi tình huống. Mục tiêu là giữ ứng dụng ổn định, biết rõ phần telemetry nào có thể mất và có thể xác định thời điểm pipeline trở lại bình thường.

## 3. Cô lập telemetry khỏi đường xử lý nghiệp vụ

Trong ứng dụng Spring Boot, việc ghi metric và tạo Observation thường diễn ra trong tiến trình, còn việc export nên được tách khỏi luồng xử lý nghiệp vụ. Khi ghi nhận một counter, ứng dụng cập nhật dữ liệu trong registry cục bộ. Với tracing, span processor theo batch có thể đưa span đã kết thúc vào queue rồi export ở worker riêng.

Không tự viết một Observation handler gọi HTTP đến backend mỗi khi Observation bắt đầu hoặc kết thúc. Cách làm này khiến độ trễ mạng, timeout và lỗi backend lan trực tiếp vào request nghiệp vụ. Handler tùy chỉnh nên thực hiện công việc cục bộ, nhanh và có giới hạn.

Kiến trúc tham khảo:

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["Micrometer Observation / MeterRegistry"]
    B --> C["Local SDK queues and exporters"]
    C --> D["Collector agent / sidecar"]
    D --> E["Bounded queue and retry"]
    E --> F["Collector gateway"]
    F --> G["Telemetry backend"]
    B --> H["Actuator metrics endpoint"]
    H --> I["Prometheus scraper"]
    A --> J["Structured stdout logs"]
    J --> K["Node or platform log collector"]
~~~

Collector agent đặt gần ứng dụng giúp ứng dụng gửi đến một endpoint trong mạng cục bộ. Agent chịu trách nhiệm batch, retry và chuyển tiếp đến gateway. Điều này giảm sự phụ thuộc trực tiếp của ứng dụng vào backend từ xa, nhưng không loại bỏ mọi lỗi: nếu agent ngừng hoạt động hoặc queue của agent đầy, SDK trong ứng dụng vẫn cần hành vi fallback có giới hạn.

Nếu dùng exporter push trực tiếp từ ứng dụng đến backend, cần kiểm tra kỹ timeout, lịch export, queue và retry của đúng exporter. Không giả định rằng mọi MeterRegistry, tracing bridge hoặc exporter đều có cùng cơ chế buffering.

## 4. Retry, timeout và queue phải có giới hạn

Retry hữu ích khi lỗi chỉ kéo dài trong thời gian ngắn, chẳng hạn gateway khởi động lại hoặc mạng mất kết nối trong vài giây. Retry liên tục không giới hạn có thể khiến backlog tăng mãi, chiếm heap, giữ thread và tạo áp lực lên backend khi nó vừa phục hồi.

Một cấu hình chịu lỗi cần xác định:

- **Timeout:** một lần export được phép chờ tối đa bao lâu. Timeout cần phù hợp với ngân sách của worker export, không kéo dài theo thời gian request nghiệp vụ.
- **Backoff:** khoảng nghỉ tăng dần giữa các lần retry, thường kết hợp jitter để nhiều instance không đồng loạt gửi lại.
- **Retry horizon:** tổng thời gian một batch được giữ để thử gửi trước khi bỏ hoặc chuyển sang chính sách khác.
- **Queue capacity:** số batch hoặc phần tử tối đa mà exporter/Collector có thể giữ.
- **Overflow policy:** hành vi khi queue đầy, ví dụ từ chối phần tử mới, loại phần tử cũ hoặc drop theo chính sách của processor.
- **Concurrency:** số worker export đồng thời, tránh tăng vô hạn khi backend chậm.
- **Payload size:** giới hạn kích thước batch và attribute để một phần tử không chiếm bộ nhớ bất thường.

Ví dụ, nếu một Collector có queue 5.000 batch và mỗi batch trung bình chiếm 80 KB trong bộ nhớ, riêng payload có thể cần khoảng 400 MB, chưa tính overhead của runtime và cấu trúc queue. Vì vậy, không chọn queue size chỉ dựa trên một con số mặc định; hãy đo kích thước batch và ngân sách bộ nhớ trong tải thực tế.

Một cấu hình queue đầy không phải lúc nào cũng làm ứng dụng dừng. Nếu exporter hoạt động bất đồng bộ và queue đã đầy, dữ liệu mới có thể bị drop. Hệ thống phải phát ra tín hiệu cho biết số phần tử bị drop để đội vận hành biết mức độ mất mát.

### Ví dụ cấu hình OpenTelemetry Collector

Đoạn cấu hình sau minh họa receiver OTLP, giới hạn bộ nhớ, batch, retry và queue ở exporter. Nó là ví dụ khởi đầu; cần đối chiếu tên component và schema với phiên bản Collector đang triển khai.

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  batch:
    timeout: 5s
    send_batch_size: 512

exporters:
  otlp:
    endpoint: telemetry-gateway.internal:4317
    timeout: 10s
    tls:
      ca_file: /etc/otel/certs/ca.pem
    sending_queue:
      enabled: true
      queue_size: 5000
    retry_on_failure:
      enabled: true
      initial_interval: 1s
      max_interval: 30s
      max_elapsed_time: 300s

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp]
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp]
~~~

Trong ví dụ, Collector giữ queue và thử gửi lại trong khoảng thời gian được cấu hình. Khi retry hết thời hạn hoặc queue đầy, dữ liệu vẫn có thể bị mất. `memory_limiter` bảo vệ tiến trình Collector trước áp lực bộ nhớ; nó không thay thế giới hạn queue, quota đĩa hay giám sát dung lượng.

Cấu hình này không tự tạo persistent queue. Queue trong bộ nhớ mất dữ liệu khi Collector bị restart hoặc process bị kill. Nếu yêu cầu khôi phục qua restart, cần cấu hình storage extension và persistent queue theo tài liệu của phiên bản Collector đang dùng, đồng thời cấp quota, quyền truy cập và chính sách retention cho volume lưu trữ.

Không đặt queue vô hạn để cố giữ mọi telemetry. Một queue hữu hạn với drop có quan sát được thường an toàn hơn một queue không giới hạn có thể làm Collector hoặc node hết tài nguyên.

## 5. Chọn fallback theo từng loại tín hiệu

Metrics, traces và logs có đặc điểm khác nhau. Một phương án phù hợp với metrics chưa chắc phù hợp với traces hoặc logs.

### Metrics: ưu tiên số liệu tổng hợp và scrape cục bộ

Metrics thường có giá trị trong việc theo dõi xu hướng, tỷ lệ và SLO. Nếu backend nhận metrics qua push bị lỗi, một endpoint scrape cục bộ có thể cung cấp đường thu thập thay thế khi hệ thống Prometheus hoặc scraper dự phòng vẫn hoạt động.

Với Spring Boot Actuator, khi ứng dụng có Prometheus registry phù hợp và endpoint được expose, cấu hình minh họa là:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Endpoint Prometheus của Actuator thường có đường dẫn /actuator/prometheus. Chỉ expose endpoint này trong mạng quản trị được kiểm soát và cấu hình authentication/network policy phù hợp. Cần có dependency Prometheus registry tương ứng; chỉ expose endpoint mà thiếu registry không tạo ra dữ liệu Prometheus.

Scrape endpoint không tự lưu trữ metrics. Nếu scraper cũng ngừng hoạt động, dữ liệu trong registry cục bộ có thể thay đổi hoặc mất khi process restart. Hãy coi đây là đường thu thập thay thế khi có scraper hoạt động, không phải kho lưu trữ bền vững.

Một số hệ thống dùng CompositeMeterRegistry hoặc thêm SimpleMeterRegistry để có registry cục bộ. Cách này có thể hữu ích cho kiểm thử hoặc quan sát trong tiến trình, nhưng không tự đồng bộ dữ liệu bị lỡ sang remote registry sau khi backend phục hồi. Counter và timer trong registry cục bộ cũng không phải hàng đợi bền vững. Chỉ thêm registry dự phòng khi đã xác định rõ ai scrape nó, dữ liệu được đọc ở đâu và cách tránh đếm trùng.

### Traces: queue hữu hạn, sampling và drop có chủ đích

Trace thường có kích thước lớn hơn một metric sample và có thể chứa nhiều span, attribute hoặc event. Khi collector/backend lỗi kéo dài:

- Giữ batch queue có giới hạn trong SDK hoặc Collector.
- Dùng timeout và retry có giới hạn.
- Duy trì head sampling ở mức phù hợp với ngân sách tài nguyên.
- Chấp nhận drop span khi queue đầy và đo số span bị drop.
- Chỉ dùng persistent queue nếu yêu cầu lưu trữ và chi phí cho phép.

Nếu hệ thống dựa vào tail sampling tại Collector để giữ trace lỗi hoặc trace chậm, cần lưu ý rằng chính Collector đó phải nhận đủ span và có đủ bộ nhớ để ra quyết định. Khi gateway không khả dụng, policy tail sampling ở gateway không thể tiếp tục hoạt động. Nếu cần giữ một phần trace trong thời gian gateway gián đoạn, hãy thiết kế local Collector hoặc policy head sampling dự phòng rõ ràng; không mặc định rằng trace lỗi sẽ luôn được giữ.

Không tăng sampling rate tự động khi backend đang lỗi. Làm vậy có thể tạo thêm dữ liệu vào queue vốn đã đầy và tăng tải đúng lúc pipeline đang suy giảm. Nếu cần thay đổi sampling, hãy dùng policy đã kiểm thử và theo dõi tác động lên bộ nhớ, CPU và dung lượng truyền.

### Logs: giữ đầu ra cục bộ có giới hạn

Với ứng dụng chạy trong container, structured logs thường được ghi ra stdout/stderr để runtime hoặc node agent thu thập. Nếu log backend lỗi, nền tảng có thể tiếp tục giữ log trên node trong giới hạn rotation và disk quota.

Không tự chuyển toàn bộ logs sang file không giới hạn trong container. Cần cấu hình rotation, giới hạn dung lượng và retention ở runtime/platform. Nếu node agent hoặc log pipeline cũng lỗi, log có thể bị mất khi container hoặc node bị thay thế.

Giữ các log vận hành có giá trị như lỗi khởi động, lỗi exporter, queue overflow, shutdown và recovery. Tránh ghi một dòng log cho mỗi lần retry liên tục vì chính fallback có thể tạo ra log storm. Dùng rate limit hoặc tổng hợp thông báo lỗi theo khoảng thời gian.

Không ghi trace payload hoặc toàn bộ Observation vào log để “backup” tracing. Cách này làm tăng kích thước log, có thể lộ dữ liệu nhạy cảm và gây khó khăn khi truy vấn.

## 6. Có nên làm ứng dụng unhealthy khi telemetry backend lỗi?

Trong đa số dịch vụ nghiệp vụ, câu trả lời là không. Readiness trả lời câu hỏi instance có đủ khả năng nhận traffic nghiệp vụ không. Liveness trả lời câu hỏi process có còn hoạt động và cần được restart không. Backend telemetry không phải dependency nghiệp vụ trực tiếp trong phần lớn kiến trúc.

Nếu readiness phụ thuộc vào khả năng gửi trace đến backend, một outage telemetry có thể khiến mọi instance bị loại khỏi load balancer. Khi đó, ứng dụng ngừng phục vụ dù database và các dependency nghiệp vụ vẫn khỏe mạnh. Nếu liveness phụ thuộc vào backend, orchestrator có thể liên tục restart instance trong khi nguyên nhân nằm ở một dịch vụ quan sát bên ngoài.

Nên tách các trạng thái:

| Trạng thái | Ý nghĩa | Hành vi |
|---|---|---|
| Application readiness | Ứng dụng có thể nhận request nghiệp vụ | Phụ thuộc vào các điều kiện cần cho nghiệp vụ, không mặc định phụ thuộc telemetry backend |
| Application liveness | Process còn hoạt động và không bị kẹt không thể phục hồi | Không restart chỉ vì exporter không kết nối được |
| Telemetry health | Exporter/Collector có gửi và nhận tín hiệu được không | Báo trạng thái suy giảm riêng, phục vụ dashboard và cảnh báo |
| Telemetry delivery quality | Có backlog, drop hoặc mất dữ liệu không | Theo dõi queue, retry, export failure và dung lượng lưu trữ |

Có thể tạo health indicator riêng hoặc health group riêng cho telemetry. Tuy nhiên, cần tránh đưa indicator đó vào readiness group nếu dịch vụ không có yêu cầu nghiệp vụ bắt buộc telemetry phải hoạt động mới được nhận traffic.

Ngoại lệ cần được xác định rõ: một số hệ thống có yêu cầu pháp lý hoặc hợp đồng mà việc ghi audit event là điều kiện bắt buộc để hoàn tất giao dịch. Khi đó, audit event phải được ghi qua một cơ chế bền vững và có bảo đảm phù hợp, chẳng hạn transactional outbox hoặc audit store. Không dùng trace exporter hay metric backend làm điều kiện duy nhất để ghi nhận giao dịch bắt buộc.

## 7. Tự giám sát telemetry bằng một kênh độc lập

Nếu exporter lỗi nhưng cảnh báo về exporter cũng chỉ được gửi qua exporter đó, đội trực có thể không biết pipeline đã ngừng gửi dữ liệu. Cần một kênh quan sát độc lập hoặc một phép kiểm tra từ bên ngoài.

Các tín hiệu cần theo dõi gồm:

- Số lần export thành công và thất bại.
- Thời gian export và số lần timeout.
- Queue size, queue utilization và tuổi của phần tử cũ nhất nếu component cung cấp.
- Số span, metric hoặc log bị drop.
- Số lần retry và thời gian retry.
- Collector receiver accepted/refused, exporter send failure và trạng thái memory limiter.
- Dung lượng persistent queue, disk usage và tốc độ tăng backlog.
- Thời gian từ lúc tín hiệu được tạo đến lúc có thể truy vấn ở backend.

Tên metric nội bộ của SDK và Collector thay đổi theo phiên bản, distro và exporter. Hãy kiểm tra telemetry nội bộ thực tế của component đang chạy thay vì hard-code dashboard dựa trên tên metric chưa xác minh.

Các cách tạo kênh giám sát độc lập:

1. Scrape health/metrics cục bộ của ứng dụng hoặc Collector từ một Prometheus độc lập.
2. Dùng log chẩn đoán có rate limit, gửi qua stdout để nền tảng thu thập.
3. Kiểm tra synthetic span hoặc heartbeat từ một thành phần bên ngoài pipeline chính.
4. Cảnh báo khi backend không nhận được tín hiệu trong khoảng thời gian dự kiến, kể cả khi không có alert nào phát ra từ backend.
5. Dùng monitoring của hạ tầng để theo dõi disk, memory, network và trạng thái pod/agent.

Một dead-man signal có thể giúp phát hiện trường hợp toàn bộ pipeline ngừng gửi dữ liệu. Ví dụ, một probe độc lập gửi heartbeat định kỳ và hệ thống giám sát bên ngoài cảnh báo khi heartbeat biến mất. Probe phải đi qua đường quan sát cần kiểm tra nhưng cảnh báo phải được phát qua một kênh khác.

## 8. Phục hồi backend mà không tạo đợt quá tải mới

Khi backend hoạt động trở lại, queue có thể chứa lượng dữ liệu lớn từ nhiều ứng dụng. Nếu tất cả agent đồng thời xả backlog với tốc độ tối đa, backend có thể lại quá tải và lặp lại sự cố.

Quá trình recovery nên có các bước:

1. Xác nhận backend nhận dữ liệu mới ổn định và quota/storage còn đủ.
2. Kiểm tra queue, số lần retry, drop count và tuổi của dữ liệu đang chờ.
3. Cho phép agent xả backlog theo batch và tốc độ có giới hạn.
4. Theo dõi ingest latency, backend CPU, memory, storage và lỗi từ chối.
5. Tăng tốc độ xả dần nếu backend còn dư năng lực.
6. Khi queue trở về mức bình thường, xác nhận export success và ingestion delay đã phục hồi.

Dữ liệu cũ có thể hết hạn về giá trị vận hành. Một trace từ nhiều giờ trước có thể không còn cần thiết để xử lý cảnh báo hiện tại; một metric sample trễ có thể làm dashboard sai cửa sổ thời gian. Vì vậy, persistent queue cần retention/TTL và policy xử lý dữ liệu quá hạn. Không giữ backlog vô thời hạn.

Retry có thể dẫn đến gửi lặp trong một số pipeline hoặc khi kết nối bị ngắt sau khi backend đã nhận nhưng trước khi client nhận acknowledgement. Không giả định telemetry delivery luôn exactly-once. Đây cũng là lý do metrics và traces không được dùng làm sổ cái hoặc nguồn dữ liệu chính xác tuyệt đối cho giao dịch.

## 9. Shutdown và restart trong lúc pipeline đang lỗi

Khi ứng dụng nhận tín hiệu shutdown, SDK có thể cố flush dữ liệu đang chờ. Việc flush phải có timeout rõ ràng. Nếu backend không phản hồi, ứng dụng cần kết thúc trong giới hạn thời gian shutdown của nền tảng thay vì chờ vô hạn.

Với Spring Boot, nên để integration và lifecycle được quản lý bởi framework hoặc SDK đã cấu hình. Nếu tự tạo exporter, processor hoặc registry, cần đóng tài nguyên đúng lifecycle và gọi flush/shutdown theo API của thư viện với thời hạn hữu hạn. Không gọi flush trên từng request và không tạo exporter mới mỗi lần xử lý nghiệp vụ.

Cần tính đến:

- Thời hạn shutdown của môi trường triển khai.
- Thời gian flush tối đa phải nhỏ hơn thời hạn shutdown còn lại.
- Queue trong bộ nhớ sẽ mất khi process kết thúc.
- Persistent queue chỉ tồn tại qua restart nếu storage được cấu hình bền vững và mount đúng.
- Nhiều instance restart đồng thời có thể làm tăng tải kết nối và tạo burst export sau khi khởi động.

Nếu telemetry backend đang lỗi, shutdown không thể bảo đảm mọi dữ liệu đã được gửi. Ghi nhận số phần tử chưa export và số phần tử bị bỏ nếu component hỗ trợ; đây là dữ liệu cần cho báo cáo sự cố.

## 10. Kịch bản kiểm thử fallback

Không nên chỉ kiểm tra pipeline trong trạng thái mọi thành phần đều hoạt động. Cần diễn tập lỗi để xác nhận ứng dụng giữ được giới hạn tài nguyên và đội trực nhận ra mức suy giảm.

| Kịch bản | Kết quả cần xác minh |
|---|---|
| Chặn kết nối từ ứng dụng đến Collector | Request nghiệp vụ vẫn xử lý; exporter timeout/retry theo giới hạn; queue không tăng vô hạn |
| Dừng Collector agent | Ứng dụng không bị treo; có cảnh báo agent/exporter; hành vi queue overflow đúng policy |
| Dừng gateway trong vài phút | Agent retry có backoff; queue tăng trong quota; backend không bị retry storm |
| Backend trả lỗi quota hoặc rate limit | Collector ghi nhận export failure; queue và retry bị giới hạn; có cảnh báo dung lượng |
| Làm đầy persistent queue | Collector thực hiện overflow policy đã định; ứng dụng và node không cạn disk |
| Khôi phục backend sau outage | Backlog được xả theo tốc độ giới hạn; backend không bị quá tải lần hai |
| Restart ứng dụng khi exporter lỗi | Shutdown hoàn tất trong timeout; dữ liệu mất hoặc được giữ đúng như thiết kế |
| Dừng log agent | stdout/file rotation giữ trong quota; node không hết disk; log storm không xuất hiện |
| Mất telemetry backend nhưng nghiệp vụ khỏe | Readiness/liveness không thất bại chỉ vì backend quan sát ngừng hoạt động |

Trong mỗi bài kiểm thử, đo cả hai phía: chất lượng telemetry và chất lượng phục vụ nghiệp vụ. Theo dõi latency p95/p99, error rate, CPU, heap, thread pool và throughput của ứng dụng. Một fallback chỉ được coi là đạt nếu nó giữ được giới hạn đã đặt ra trong điều kiện lỗi kéo dài.

## 11. Runbook khi telemetry backend không nhận dữ liệu

Khi dashboard hoặc alert cho thấy telemetry bị gián đoạn, đội trực có thể xử lý theo thứ tự:

1. **Xác nhận phạm vi:** một service, một node, một Collector hay toàn backend? So sánh nhiều nguồn và thời điểm để tránh kết luận từ một dashboard lỗi.
2. **Kiểm tra nguồn:** ứng dụng còn tạo metrics/traces/logs không? Actuator endpoint, log cục bộ và trạng thái SDK có hoạt động không?
3. **Kiểm tra exporter:** endpoint, DNS, TLS certificate, authentication, timeout, retry và lỗi kết nối.
4. **Kiểm tra Collector:** receiver có nhận dữ liệu không, memory limiter có từ chối dữ liệu không, queue có đầy không, exporter có lỗi không?
5. **Kiểm tra backend:** quota, ingestion rate, storage, tenant, authentication và trạng thái dịch vụ.
6. **Bảo vệ ứng dụng:** giữ queue trong quota, không tăng sampling hoặc retry vô hạn, xác nhận readiness/liveness không phụ thuộc telemetry ngoài yêu cầu nghiệp vụ.
7. **Theo dõi recovery:** xác nhận tín hiệu mới đã vào backend, xả backlog có giới hạn và ghi lại khoảng thời gian telemetry bị thiếu.

Không xóa queue hoặc restart hàng loạt Collector trước khi xác định liệu queue có chứa dữ liệu duy nhất cần giữ hay không. Nếu cần restart, ghi nhận queue size, storage state và chính sách mất dữ liệu trước khi thao tác.

## 12. Những lỗi thiết kế cần tránh

**Export đồng bộ trong request thread.** Backend chậm làm tăng latency và có thể biến sự cố telemetry thành outage nghiệp vụ. Dùng cơ chế export bất đồng bộ và kiểm tra thread/queue của exporter.

**Retry vô hạn.** Backlog tăng đến khi cạn bộ nhớ hoặc đĩa. Đặt retry horizon, backoff, quota và overflow policy.

**Queue không có giới hạn.** Buffer không giới hạn chỉ trì hoãn sự cố và làm tăng phạm vi ảnh hưởng. Đặt ngân sách tài nguyên cho từng queue.

**Đánh dấu ứng dụng unhealthy khi backend telemetry lỗi.** Orchestrator có thể loại bỏ hoặc restart các instance vẫn xử lý nghiệp vụ bình thường. Tách telemetry health khỏi readiness/liveness.

**Dùng SimpleMeterRegistry như kho lưu trữ dự phòng.** Registry này giữ dữ liệu trong bộ nhớ tiến trình và không tự replay sang backend. Xác định rõ đường scrape và giới hạn của nó.

**Tăng sampling khi backend đã quá tải.** Lượng span tăng khiến queue và network chịu thêm áp lực. Giữ sampling policy có ngân sách, chỉ thay đổi khi đã đánh giá tác động.

**Coi retry là bảo đảm không mất hoặc không trùng dữ liệu.** Kết nối có thể đứt tại thời điểm không rõ backend đã nhận batch hay chưa. Telemetry không thay thế audit store hoặc transaction record.

**Dùng chung một kênh để báo lỗi cho chính kênh đó.** Cần kiểm tra từ bên ngoài và một đường cảnh báo độc lập để phát hiện mất tín hiệu.

**Không diễn tập outage.** Cấu hình có queue và retry vẫn có thể sai khi chạy thực tế. Kiểm thử thời gian lỗi kéo dài, queue đầy, restart và recovery.

## 13. Quy ước vận hành nên thống nhất

Một dịch vụ Spring Boot có thể đưa các quyết định sau vào tiêu chuẩn triển khai:

1. Export telemetry bất đồng bộ; không để request nghiệp vụ chờ backend telemetry.
2. Đặt timeout, retry horizon, backoff, queue capacity và overflow policy cho từng chặng.
3. Ưu tiên Collector agent/gateway để gom, batch và kiểm soát export; chỉ dùng direct export khi có lý do vận hành rõ ràng.
4. Dùng scrape endpoint hoặc stdout làm đường thu thập thay thế khi hạ tầng tương ứng có khả năng tiếp nhận và lưu trữ.
5. Chỉ dùng persistent queue khi có yêu cầu giữ dữ liệu qua restart; đặt quota, retention, quyền truy cập và giám sát dung lượng.
6. Giữ readiness/liveness gắn với khả năng phục vụ nghiệp vụ; báo telemetry health riêng.
7. Theo dõi export failure, queue utilization, dropped data, ingest delay và tình trạng backend bằng kênh độc lập.
8. Giới hạn tốc độ recovery và diễn tập outage định kỳ.
9. Không dùng metrics, traces hoặc log pipeline làm kho audit hay sổ cái giao dịch.

Khi backend telemetry lỗi, ứng dụng nên chuyển sang trạng thái suy giảm có kiểm soát: tiếp tục phục vụ nghiệp vụ trong giới hạn tài nguyên, giữ những tín hiệu có thể giữ, ghi nhận phần dữ liệu bị mất và phục hồi pipeline theo tốc độ an toàn. Fallback chỉ đáng tin cậy khi queue, retry, health check và quy trình recovery đều được kiểm thử trong điều kiện lỗi thực tế.

