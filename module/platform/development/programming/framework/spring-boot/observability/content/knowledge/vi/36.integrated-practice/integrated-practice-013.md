# Checklist production readiness

Observability chỉ thực sự có ích trong production khi đội vận hành có thể phát hiện bất thường, xác định phạm vi ảnh hưởng và lần theo nguyên nhân mà không làm ứng dụng mất ổn định. Một ứng dụng có endpoint metrics hoặc có trace gửi lên backend chưa đủ để được xem là sẵn sàng. Cần kiểm tra đồng thời chất lượng dữ liệu, khả năng export, quyền truy cập, chi phí cardinality, sampling, cảnh báo và quy trình xử lý sự cố.

Bài này cung cấp checklist production readiness cho ứng dụng Spring Boot sử dụng Micrometer Observation, metrics, logs và distributed tracing. Hãy áp dụng checklist trong review trước release, kiểm tra lại sau khi triển khai và lưu bằng chứng cho từng mục quan trọng. Những giá trị như sampling rate, retention, ngưỡng cảnh báo và ngân sách cardinality phải được chọn theo lưu lượng, SLO và năng lực hạ tầng của từng service.

Bài học thuộc chương **Thực hành tổng hợp** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; checklist này tổng hợp propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu thành một cổng kiểm tra có thể dùng trước khi vận hành thực tế.

## Mục tiêu

Sau bài này, bạn có thể:

- Đánh giá mức độ đầy đủ và hữu ích của metrics, logs và traces trước khi release.
- Kiểm tra instrumentation, context propagation, cardinality và sampling.
- Xác nhận exporter, collector và backend hoạt động ổn định khi có lỗi mạng hoặc khi ứng dụng shutdown.
- Bảo vệ endpoint quản trị và loại bỏ dữ liệu nhạy cảm khỏi telemetry.
- Thiết kế dashboard, SLO và alert gắn với hành động vận hành.
- Lập bằng chứng kiểm tra và đưa ra quyết định GO/NO-GO có căn cứ.

## Cách sử dụng checklist

Thực hiện kiểm tra trên cấu hình gần với production nhất có thể. Với mỗi mục, ghi một trong ba trạng thái:

| Trạng thái | Ý nghĩa | Cách xử lý |
|---|---|---|
| PASS | Có bằng chứng kiểm tra và kết quả đáp ứng tiêu chí | Có thể đưa vào release evidence |
| FAIL | Thiếu dữ liệu, cấu hình sai hoặc không đạt tiêu chí | Sửa và kiểm tra lại trước khi release nếu là điều kiện bắt buộc |
| N/A | Không áp dụng cho kiến trúc service này | Ghi lý do và người xác nhận |

Không đánh dấu PASS chỉ vì file cấu hình tồn tại. Cần có bằng chứng runtime như metric xuất hiện, trace được backend nhận, log có correlation fields, endpoint được bảo vệ và alert được thử nghiệm. Nếu một mục N/A, hãy ghi rõ service không sử dụng thành phần tương ứng, ví dụ không có messaging consumer.

## 1. Danh tính service và quyền sở hữu

Telemetry phải cho biết dữ liệu đến từ service nào, môi trường nào và phiên bản triển khai nào. Thiếu resource identity sẽ khiến trace và metrics khó phân biệt giữa các instance hoặc môi trường.

| Hạng mục | Tiêu chí production-ready | Bằng chứng nên lưu |
|---|---|---|
| Service name | Tên ổn định, duy nhất theo service, ví dụ `orders-service` | Resource attributes trong trace và nhãn service ở backend |
| Environment | Phân biệt rõ `dev`, `staging`, `production` | Resource attribute hoặc nhãn triển khai |
| Service version | Có thể xác định build/release đang phát telemetry | Image tag, Git SHA hoặc version attribute |
| Instance identity | Có thể phân biệt instance khi điều tra lỗi cục bộ | Pod/container/instance metadata do nền tảng cung cấp |
| Ownership | Có team hoặc on-call chịu trách nhiệm dashboard, alert và runbook | Service catalog hoặc thông tin ownership trong hệ thống vận hành |
| Time synchronization | Host/container dùng đồng hồ đồng bộ; timestamp log và span không lệch bất thường | Cấu hình NTP/clock sync và kiểm tra timestamp thực tế |

Trong Spring Boot, `spring.application.name` là điểm bắt đầu để đặt tên ứng dụng. Environment, version và instance metadata có thể được bổ sung qua cấu hình resource của nền tảng hoặc OpenTelemetry. Tránh dùng tên pod làm service name vì mỗi lần scale hoặc rollout có thể tạo danh tính service mới.

Ví dụ cấu hình cơ bản:

```yaml
spring:
  application:
    name: orders-service
```

Tên resource cần nhất quán giữa metrics, logs và traces. Nếu metrics ghi `orders`, trace ghi `orders-service`, còn dashboard dùng `order-api`, đội vận hành sẽ phải duy trì nhiều cách gọi cho cùng một service.

## 2. Độ bao phủ instrumentation

Instrumentation cần bao phủ những ranh giới giúp trả lời câu hỏi vận hành. Hãy rà soát theo luồng xử lý thực tế thay vì chỉ đếm số Observation đã tạo.

| Boundary | Điều cần quan sát | Tiêu chí kiểm tra |
|---|---|---|
| HTTP server | Lưu lượng, latency, status và route | Có server metrics; route dùng template ổn định; request lỗi có thể nhận diện |
| Application/use case | Thời gian và kết quả nghiệp vụ quan trọng | Có Observation cho use case cần theo dõi; tên ổn định và tag bounded |
| HTTP/RPC client | Latency, lỗi và dependency được gọi | Có client instrumentation hoặc Observation tương đương; trace context được truyền |
| Database | Query latency, lỗi và pool saturation | Có metrics/tracing cho driver hoặc pool phù hợp; không đưa SQL động vào tag |
| Messaging | Publish, consume, retry và xử lý lỗi | Có boundary producer/consumer; context được truyền qua message headers khi hỗ trợ |
| Background job | Thời gian, kết quả và lần chạy | Có một Observation cho đơn vị công việc phù hợp; lỗi job được ghi nhận |
| Runtime | JVM, memory, GC, thread và connection pool | Có các meter cần thiết để phân biệt lỗi ứng dụng với thiếu tài nguyên |

Không instrument mọi method. Một getter hoặc mapper nhỏ thường không tạo thêm thông tin vận hành. Cũng không tạo Observation thủ công quanh HTTP client hoặc JDBC đã được auto instrumentation bao phủ nếu span mới không bổ sung ngữ cảnh. Kiểm tra trace để phát hiện span trùng, span quá nhỏ hoặc boundary quá rộng.

Với mỗi Observation tự tạo, cần trả lời được ba câu hỏi: hoạt động nào đang được đo, điểm bắt đầu/kết thúc ở đâu và người trực production sẽ làm gì khi metric hoặc span cho thấy bất thường?

## 3. Metrics: độ hữu ích và cardinality

Metrics phải cho thấy xu hướng tổng thể và hỗ trợ cảnh báo. Kiểm tra tối thiểu bốn nhóm tín hiệu: traffic, errors, latency và saturation. Bổ sung business metrics khi chúng gắn với một quyết định vận hành cụ thể.

### Các nhóm metrics cần rà soát

| Nhóm | Ví dụ | Câu hỏi vận hành |
|---|---|---|
| HTTP traffic | Request count theo route/method | Lưu lượng có tăng hoặc giảm bất thường không? |
| HTTP errors | Response 5xx, exception count | Tỷ lệ lỗi có vượt SLO không? |
| HTTP latency | Duration histogram, p95/p99 từ histogram | Người dùng có đang gặp request chậm không? |
| Dependency | HTTP client duration/error, DB query duration | Dependency nào đang làm request chậm? |
| Saturation | CPU, heap, GC pause, thread pool, connection pool | Service có gần cạn tài nguyên không? |
| Messaging | Queue depth, consumer lag, retry/failure | Công việc có bị ùn tắc không? |
| Business | Checkout accepted/rejected, payment outcome | Hoạt động nghiệp vụ có suy giảm dù HTTP vẫn trả 200 không? |

Không phải service nào cũng cần mọi meter trong bảng. Chọn nhóm phù hợp với kiến trúc, nhưng cần xác nhận các dependency quan trọng có đủ dữ liệu để phát hiện nghẽn.

### Kiểm soát cardinality

Với mỗi metric, liệt kê tag keys và tập giá trị dự kiến. Ước lượng số tổ hợp bằng tích cardinality của các tag. Ví dụ 4 method × 6 status group × 20 route × 3 region có thể tạo tối đa 1.440 tổ hợp cho một metric trước khi tính thêm các chiều khác.

Các tiêu chí bắt buộc:

- Tag key ổn định và có cùng ý nghĩa giữa các endpoint.
- Tag values thuộc tập hữu hạn hoặc được chuẩn hóa bằng allowlist.
- HTTP URI dùng route template như `/orders/{orderId}`.
- Không đưa `userId`, `orderId`, `requestId`, `traceId`, email, token, raw query string hoặc exception message vào metric tags.
- Không tạo tên metric hay tag key động từ dữ liệu request.
- Có ngân sách cardinality cho metric quan trọng và cách phát hiện khi số series tăng đột biến.

ID có thể cần trong trace hoặc log để điều tra một request cụ thể, nhưng không phải chiều phân loại cho metrics. Hãy dùng low-cardinality key values của Micrometer Observation cho metrics; high-cardinality attributes chỉ được thêm vào trace khi có nhu cầu, được phép theo chính sách dữ liệu và có giới hạn lưu trữ phù hợp.

### Histogram và latency

Nếu dashboard cần tính phân vị latency tổng hợp từ nhiều instance, kiểm tra histogram đã được bật và backend nhận đủ bucket. Client-side percentile không phải lúc nào cũng có thể tổng hợp chính xác giữa các instance. Chọn bucket boundaries phù hợp với SLO và độ phân giải cần thiết; mỗi bucket cũng làm tăng số series.

Ví dụ cấu hình cho HTTP server timer trong Spring Boot:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

Không bật histogram rộng rãi cho mọi meter mà chưa ước lượng chi phí. Kiểm tra số series trước và sau khi bật, sau đó xác nhận truy vấn p95/p99 hoạt động trên dữ liệu từ nhiều instance.

## 4. Distributed tracing và context propagation

Trace phải thể hiện được hành trình của request qua các boundary quan trọng. Kiểm tra một request đi qua ít nhất một luồng thành công và một luồng lỗi.

Checklist tracing:

- [ ] HTTP server span được tạo với service/resource identity chính xác.
- [ ] HTTP client span xuất hiện cho dependency được instrument.
- [ ] Parent/child relationship hợp lý; không có span trùng cho cùng một lời gọi.
- [ ] W3C Trace Context (`traceparent`) được truyền qua HTTP khi cấu hình dùng chuẩn này.
- [ ] Messaging context được inject/extract qua message headers nếu service dùng broker.
- [ ] Async executor, `@Async` hoặc callback giữ được context theo cơ chế propagation đã cấu hình.
- [ ] Lỗi kỹ thuật được đánh dấu đúng trên span và có exception event phù hợp.
- [ ] Span names và attributes không chứa dữ liệu đầu vào không giới hạn hoặc dữ liệu nhạy cảm.
- [ ] Trace có thể tìm bằng service name, operation và khoảng thời gian.

Context propagation cần được kiểm tra ở các ranh giới thread và process. Scope đang mở trong một thread không được giữ rồi đóng tùy tiện từ thread khác. Với công việc bất đồng bộ, dùng cơ chế context propagation và executor được hỗ trợ trong stack Spring/Micrometer. Với messaging, producer và consumer có vòng đời riêng; liên kết bằng trace context trong message thay vì giữ scope mở trong thời gian chờ message.

Không phải mọi span đều cần payload. Chỉ lưu attributes có giá trị điều tra như operation, dependency, status hoặc nhóm lỗi. Baggage được truyền xuyên dịch vụ cần allowlist, giới hạn kích thước và chính sách dữ liệu rõ ràng.

## 5. Sampling và khả năng tìm thấy trace

Sampling ảnh hưởng đến trace được export, không phải metrics. Một service có thể tiếp tục tăng HTTP request count trong khi một phần request không có trace vì head sampling đã loại chúng.

Kiểm tra:

- Sampling probability được cấu hình theo môi trường và lưu lượng thực tế.
- Môi trường local/test có thể dùng sampling cao để dễ debug; production cần ngân sách rõ ràng.
- Các service trong cùng trace tôn trọng sampling decision và propagation headers.
- Có cách điều tra khi trace không được lấy mẫu, ví dụ dựa vào metrics, logs và request correlation theo chính sách.
- Nếu cần giữ trace chậm/lỗi, đã đánh giá tail-based sampling và giới hạn bộ nhớ/buffer của collector.
- Tỷ lệ trace nhận được và tỷ lệ export lỗi được theo dõi ở collector/backend nếu có thể.

Head sampling quyết định sớm tại SDK. Collector không thể giữ lại một trace mà ứng dụng đã không gửi. Tail-based sampling chỉ có thể quyết định dựa trên span đã tới collector và cần buffer đủ để chờ toàn bộ trace hoặc cửa sổ quyết định.

Không dùng trace ID làm metric tag để bù cho sampling. Dùng metrics để nhìn xu hướng toàn cục, logs để ghi sự kiện có correlation context và traces để phân tích những request được giữ.

## 6. Logs và liên kết tín hiệu

Logs phải hỗ trợ điều tra sự kiện cụ thể, đồng thời có thể nối với trace khi context tồn tại.

| Hạng mục | Tiêu chí production-ready |
|---|---|
| Structured logging | Log ở định dạng có thể parse, ưu tiên JSON trong môi trường tập trung |
| Correlation | Có trace ID/span ID khi request đang nằm trong tracing context |
| Severity | Dùng level nhất quán; lỗi có thể hành động không bị ghi ở DEBUG |
| Error details | Có loại exception và stack trace khi cần; message không làm lộ secret hoặc payload |
| Volume | Không log toàn bộ payload hoặc log thành công ở mức quá chi tiết gây bão log |
| Retention | Có thời gian lưu và quyền truy cập phù hợp với mục đích điều tra |
| Redaction | Password, token, cookie, dữ liệu thanh toán và thông tin cá nhân được loại bỏ hoặc che |

Kiểm tra logging pattern hoặc JSON encoder để bảo đảm MDC fields như `traceId` và `spanId` được xuất ra. Tên field thực tế có thể là `trace_id`, `traceId` hoặc theo schema của nền tảng; thống nhất schema giữa các service để tìm kiếm dễ dàng.

Không giả định log sẽ tự động có trace ID khi request không được sampled hoặc không có tracing context. Trong tình huống đó, log vẫn cần timestamp, service, level, operation và thông tin lỗi đủ để xử lý mà không tiết lộ dữ liệu nhạy cảm.

## 7. Exporter, collector và backend

Telemetry pipeline là một phần của production system. Cấu hình exporter đúng chưa đủ; cần kiểm tra đường truyền, retry, queue, giới hạn và hành vi khi backend ngừng hoạt động.

| Thành phần | Tiêu chí kiểm tra |
|---|---|
| Metrics registry | Meter được đăng ký và scrape thành công; scrape endpoint không bị mở công khai |
| Prometheus hoặc metrics backend | Scrape target healthy, timestamp và labels đúng, ingestion không bị drop |
| Tracing exporter | Endpoint/protocol OTLP đúng với receiver; service/resource attributes được giữ |
| OpenTelemetry Collector | Receiver, processor, exporter và pipeline được bật; queue/retry có giới hạn |
| Trace backend | Trace tìm được theo service và thời gian; retention và quyền truy cập phù hợp |
| Network | DNS, routing, firewall, TLS và authentication hoạt động từ môi trường triển khai |
| Failure behavior | Export timeout hoặc backend unavailable không làm request nghiệp vụ treo vô hạn |
| Shutdown | Ứng dụng có thời gian flush telemetry phù hợp trước khi process kết thúc |

Đối với OTLP, endpoint và protocol phải khớp. OTLP/HTTP thường dùng endpoint dạng `/v1/traces`; OTLP/gRPC thường dùng địa chỉ receiver gRPC theo cấu hình collector. Không ghép nhầm HTTP endpoint với gRPC exporter.

Nếu exporter có batch processor, đặt queue size, batch size, timeout và retry theo năng lực của service và backend. Queue không giới hạn có thể làm tăng memory khi backend lỗi kéo dài. Queue quá nhỏ có thể làm rơi telemetry trong đợt tải cao. Theo dõi exporter failures, dropped spans, queue utilization và collector exporter errors nếu các thành phần cung cấp metrics đó.

Ứng dụng cần graceful shutdown để flush phần telemetry đang chờ trong giới hạn thời gian termination của nền tảng. Hãy kiểm thử rollout/restart khi có traffic; đừng giả định mọi span trong buffer đều được gửi nếu process bị kill ngay lập tức.

## 8. Bảo mật endpoint và dữ liệu telemetry

Actuator và telemetry có thể tiết lộ cấu trúc nội bộ, route, lưu lượng, lỗi và thông tin môi trường. Chỉ expose endpoint cần thiết và giới hạn quyền truy cập.

- Chỉ expose `health` và endpoint metrics cần cho hệ thống scrape; không expose toàn bộ Actuator theo mặc định production.
- Giới hạn `/actuator/prometheus`, `/actuator/metrics` và endpoint quản trị bằng network policy, authentication hoặc Spring Security.
- Health detail chỉ hiển thị cho nhóm được phép; readiness/liveness phải phản ánh trạng thái phục vụ thực tế.
- Bảo vệ OTLP receiver/exporter bằng network policy, TLS và xác thực theo hạ tầng.
- Loại bỏ token, cookie, authorization header, payload thanh toán và dữ liệu cá nhân khỏi log/span attributes.
- Không nhận baggage từ nguồn không tin cậy nếu chưa có allowlist và giới hạn kích thước.
- Quy định retention, quyền truy cập và quy trình xóa dữ liệu cho metrics, logs và traces.
- Kiểm tra dashboard và query có vô tình hiển thị dữ liệu nhạy cảm không.

Không đưa nội dung request/response đầy đủ vào span chỉ để tăng ngữ cảnh. Hãy chọn attributes cần thiết và dùng redaction trước khi export.

## 9. SLO, dashboard và alert

Dashboard cần giúp trả lời câu hỏi “service có đang đáp ứng kỳ vọng của người dùng không?” Alert cần chỉ ra hành động tiếp theo. Một dashboard chỉ có nhiều biểu đồ nhưng không gắn với SLO hoặc quyết định vận hành sẽ khó sử dụng khi incident xảy ra.

Kiểm tra dashboard có các góc nhìn sau khi phù hợp:

- Request rate và traffic theo route hoặc operation quan trọng.
- Error rate, đặc biệt là lỗi 5xx và lỗi nghiệp vụ quan trọng.
- Latency p50/p95/p99 theo SLO và theo endpoint chính.
- Dependency latency/error cho database, payment, identity hoặc dịch vụ ngoài.
- Saturation: CPU, heap, GC, thread pool, connection pool và queue depth.
- Business outcome như checkout success hoặc payment failure nếu đây là chỉ số cốt lõi.
- Telemetry pipeline health: scrape failures, exporter failures, dropped spans hoặc collector queue.

Alert nên có owner, severity, điều kiện kích hoạt, link dashboard và runbook. Ưu tiên alert dựa trên SLO/error budget hoặc triệu chứng ảnh hưởng người dùng. Tránh cảnh báo chỉ vì một instance có CPU tăng trong thời gian ngắn nếu chưa chứng minh đó là dấu hiệu ảnh hưởng dịch vụ.

Với histogram, kiểm tra truy vấn p95/p99 dùng bucket và aggregation đúng. Với nhiều instance, cần tổng hợp histogram trước khi tính quantile theo cách backend hỗ trợ. Không cộng trực tiếp các giá trị percentile đã tính riêng ở từng instance.

Mỗi alert production nên được thử nghiệm bằng cách tạo tình huống tương ứng trong staging hoặc môi trường kiểm thử an toàn. Xác nhận notification đến đúng kênh/on-call và runbook có thể thực hiện được.

## 10. Kiểm thử và diễn tập trước release

Chạy kiểm tra trên build và cấu hình sẽ được triển khai. Bộ kiểm tra tối thiểu gồm:

1. **Happy path:** Gửi request thành công, xác nhận HTTP metrics tăng, trace được tạo theo sampling policy và log có correlation fields.
2. **Error path:** Tạo lỗi có kiểm soát, xác nhận status/error metric, span error và log chứa thông tin đủ điều tra.
3. **Slow dependency:** Làm dependency phản hồi chậm trong môi trường test, xác nhận latency xuất hiện ở đúng client span và dashboard.
4. **Cardinality:** Gửi nhiều request với ID khác nhau, xác nhận số metric series không tăng theo từng ID.
5. **Context propagation:** Gọi qua HTTP client, async executor hoặc message broker và kiểm tra trace liên kết qua boundary.
6. **Exporter unavailable:** Tạm ngắt collector/backend trong môi trường test, xác nhận request nghiệp vụ vẫn có timeout hữu hạn và ứng dụng không tăng memory vô hạn.
7. **Restart/rollout:** Restart ứng dụng có traffic, kiểm tra graceful shutdown và mức telemetry bị mất trong giới hạn chấp nhận.
8. **Access control:** Thử truy cập endpoint Actuator từ mạng/người dùng không được phép và xác nhận bị từ chối.
9. **Alert test:** Kích hoạt điều kiện cảnh báo đã định nghĩa và xác nhận đúng người nhận, đúng runbook.

Có thể dùng `ObservationRegistry` test handler và meter registry trong automated tests để xác nhận tên/tag. Dùng integration test để kiểm tra export hoặc propagation thực tế khi cần. Unit test hàm normalize tag không thay thế kiểm thử backend nhận được telemetry.

## 11. Cấu hình production tham khảo

Ví dụ dưới đây minh họa cách tách các giá trị thay đổi theo môi trường ra environment variables. Đây không phải cấu hình hoàn chỉnh cho mọi service; endpoint, sampling rate và exposure phải được điều chỉnh theo nền tảng triển khai.

```yaml
spring:
  application:
    name: orders-service

management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      probes:
        enabled: true
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
  tracing:
    sampling:
      probability: ${TRACING_SAMPLING_PROBABILITY:0.1}
  otlp:
    tracing:
      endpoint: ${OTEL_EXPORTER_OTLP_TRACES_ENDPOINT:http://otel-collector:4318/v1/traces}
```

Trong cấu hình này, `0.1` chỉ là giá trị minh họa cho môi trường có lưu lượng vừa phải; hãy chọn theo chính sách sampling và dung lượng trace thực tế. `health` và `prometheus` chỉ được expose qua mạng quản trị hoặc endpoint được bảo vệ. Nếu service không dùng Prometheus scrape, thay endpoint theo mô hình export metrics của nền tảng.

Không commit credential hoặc token exporter vào file cấu hình. Lấy secret từ secret manager hoặc cơ chế secret injection của nền tảng. Với nhiều profile Spring, kiểm tra giá trị cuối cùng sau khi profile và environment variables được áp dụng, tránh vô tình dùng sampling 100% hoặc expose endpoint rộng trong production.

## 12. Cổng quyết định GO/NO-GO

Trước release, phân loại các mục sau thành điều kiện bắt buộc hoặc điều kiện có thể chấp nhận theo rủi ro đã được owner phê duyệt.

| Nhóm | Điều kiện GO |
|---|---|
| Identity | Service, environment và version có thể xác định rõ |
| Metrics | Request/error/latency và saturation quan trọng có dữ liệu; cardinality trong ngân sách |
| Tracing | Trace cho các luồng trọng yếu được tạo, export và liên kết qua dependency theo sampling policy |
| Logs | Log đủ thông tin điều tra, có correlation khi context tồn tại và không lộ secret |
| Export pipeline | Endpoint, protocol, collector và backend được kiểm tra; failure behavior có giới hạn |
| Security | Actuator, OTLP và backend telemetry có quyền truy cập phù hợp |
| SLO/alert | Dashboard, alert, owner và runbook đã được xác nhận |
| Validation | Happy path, error path, propagation, exporter failure và rollout đã được kiểm tra |

Chọn **NO-GO** nếu thiếu dữ liệu khiến đội trực không thể phát hiện hoặc điều tra lỗi nghiêm trọng, endpoint nhạy cảm bị mở ngoài ý muốn, cardinality có nguy cơ làm cạn backend, hoặc export failure có thể ảnh hưởng request nghiệp vụ. Với mục chưa áp dụng, ghi N/A và lý do. Với rủi ro được chấp nhận, ghi owner, thời hạn khắc phục và người phê duyệt.

## Checklist tổng hợp

### Service và instrumentation

- [ ] Service name, environment, version và owner đã rõ.
- [ ] HTTP server, client, database, messaging và job boundary quan trọng đã được rà soát.
- [ ] Không có instrumentation trùng lặp hoặc span không mang giá trị vận hành.
- [ ] Tên Observation ổn định và mô tả hoạt động có ý nghĩa.

### Metrics và traces

- [ ] Traffic, errors, latency, saturation và business metrics quan trọng có dữ liệu.
- [ ] Tag values bounded; URI dùng route template; cardinality có ngân sách.
- [ ] Histogram/bucket phù hợp với truy vấn SLO và chi phí series.
- [ ] Trace context truyền qua HTTP, async và messaging theo kiến trúc.
- [ ] Sampling policy và trace retention đã được xác nhận.

### Logs, export và security

- [ ] Logs có cấu trúc, correlation fields và redaction.
- [ ] Metrics registry, OTLP exporter, collector và backend đã được kiểm tra.
- [ ] Queue/retry/timeout và graceful shutdown có giới hạn.
- [ ] Actuator, OTLP và telemetry backend được bảo vệ.
- [ ] Baggage/span attributes không chứa dữ liệu nhạy cảm không cần thiết.

### Vận hành và release

- [ ] Dashboard và SLO phản ánh trải nghiệm người dùng.
- [ ] Alert có owner, severity, notification và runbook.
- [ ] Happy path, error path, slow dependency, exporter failure và rollout đã được thử.
- [ ] Bằng chứng PASS/FAIL/N/A được lưu cùng release.
- [ ] Các rủi ro còn lại có owner và quyết định chấp nhận rõ ràng.

## Kết luận

Production readiness của observability là khả năng phát hiện, giải thích và xử lý bất thường trong điều kiện vận hành thật. Hãy xác minh cả ba tín hiệu metrics, logs và traces; kiểm soát cardinality, propagation, sampling và dữ liệu nhạy cảm; kiểm tra exporter cùng hành vi khi backend lỗi; cuối cùng gắn dashboard và alert với SLO, owner và runbook. Chỉ đánh dấu sẵn sàng khi có bằng chứng runtime cho các luồng quan trọng và những rủi ro còn lại đã được người chịu trách nhiệm chấp nhận.
