# Profiling API response

Một endpoint Spring HATEOAS có thể trả cùng dữ liệu đơn hàng nhưng thời gian phản hồi khác nhau đáng kể khi collection lớn hơn, có nhiều link hơn hoặc representation được nhúng sâu hơn. Nếu chỉ nhìn tổng thời gian HTTP, khó biết chi phí nằm ở truy vấn dữ liệu, mapping DTO, tạo link, kiểm tra quyền, serialize HAL hay truyền payload qua mạng.

Profiling API response là quá trình đo và phân tích một request thực tế để tìm đoạn đang tiêu tốn thời gian, CPU, bộ nhớ hoặc băng thông. Với Spring HATEOAS, cần đo toàn bộ vòng đời response và tách riêng các giai đoạn quan trọng như assembler, hypermedia enrichment và serialization. Mục tiêu là xác định bottleneck bằng dữ liệu có thể lặp lại, sau đó thay đổi một yếu tố và đo lại.

## Profiling cần trả lời câu hỏi nào?

Trước khi mở profiler, hãy mô tả triệu chứng và câu hỏi cần xác minh. Ví dụ:

- `GET /api/orders` có p95 cao khi trả 100 item hay không?
- Việc thêm self link và action link làm response tăng bao nhiêu byte?
- CPU có tập trung trong assembler, Jackson/HAL serializer hay business service?
- Thời gian chờ database/remote service chiếm bao nhiêu phần của request?
- Một request tạo ra bao nhiêu object và allocation rate có làm GC tăng không?
- Payload lớn làm tăng thời gian serialize, nén hoặc truyền qua mạng đến mức nào?

Một request HATEOAS thường đi qua nhiều lớp:

```text
HTTP request
    |
    v
Spring MVC / filters / security
    |
    v
Controller
    |
    v
Service / repository / remote calls
    |
    v
DTO mapping / representation assembler
    |
    v
Link building / affordances / authorization checks
    |
    v
HAL or other hypermedia serialization
    |
    v
Compression / servlet container / network
    |
    v
HTTP response
```

Tổng thời gian response là kết quả của các giai đoạn này cùng với scheduling, contention và I/O. Không mặc định `WebMvcLinkBuilder`, `methodOn()` hoặc việc tạo đối tượng `Link` là nguyên nhân gây chậm. Cần quan sát stack trace và thời gian thực tế trước khi kết luận.

## Phân biệt các loại thời gian

Các công cụ có thể đo những khoảng thời gian khác nhau. Không so sánh các con số nếu chưa hiểu phạm vi đo.

| Chỉ số | Đo phần nào? | Công cụ thường dùng |
| --- | --- | --- |
| Client end-to-end latency | Từ lúc client gửi request đến khi nhận đủ response. Có thể gồm DNS, TCP/TLS, proxy và mạng. | k6, Gatling, JMeter, browser/RUM hoặc HTTP client. |
| Server request duration | Thời gian xử lý request trong Spring MVC/server instrumentation. | Spring Boot Actuator, Micrometer. |
| Span duration | Thời gian một đoạn cụ thể như controller, service hoặc DB call. | Distributed tracing, Micrometer Observation, OpenTelemetry. |
| CPU time / execution samples | Method và thread tiêu tốn CPU. | Java Flight Recorder, JDK Mission Control, async-profiler. |
| Allocation / GC | Object được tạo, heap pressure và thời gian garbage collection. | JFR, JMC, JVM metrics. |
| Response size | Số byte body hoặc số byte thực truyền trên mạng. | HTTP client, gateway/proxy metrics, benchmark harness. |

Ví dụ, server duration thấp nhưng client latency cao có thể chỉ ra network, TLS, gateway hoặc client-side delay. Ngược lại, server duration cao nhưng CPU thấp có thể do database, socket hoặc lock wait.

## Bắt đầu bằng baseline có thể tái lập

Profiling chỉ có ý nghĩa khi có baseline. Ghi lại cấu hình và workload trước khi thay đổi code.

Một baseline tốt cần cố định:

1. Phiên bản JDK, Spring Boot, Spring Framework và Spring HATEOAS.
2. CPU, RAM, container limit, heap size và cấu hình GC.
3. Database, dataset, index, network và cache state.
4. Endpoint, media type, page size, sort/filter và loại người dùng.
5. Số client đồng thời, thời gian warm-up, thời lượng đo và số lần lặp.
6. Các feature đang bật như security, compression, tracing và caching.

Không đo ngay sau khi JVM vừa khởi động rồi dùng kết quả đó làm đại diện cho steady state. Hãy warm up ứng dụng và workload để JIT compiler, connection pool và cache đạt trạng thái ổn định. Nếu vấn đề chỉ xuất hiện ở cold start, hãy tạo một bài đo riêng cho cold start.

### Chọn kịch bản đại diện

Với API quản lý đơn hàng, có thể lập ma trận:

| Kịch bản | Kích thước | Nội dung cần quan sát |
| --- | --- | --- |
| Đọc một item | 1 item | Chi phí nền của DTO, self link và serializer. |
| Collection nhỏ | 10 item | Chi phí assembler và số link trên mỗi item. |
| Collection vừa | 50–100 item | Tăng trưởng CPU, allocation và payload. |
| Collection lớn | Page size tối đa được hỗ trợ | Chi phí giới hạn trên và hành vi pagination. |
| Representation nhúng | Có customer/line items | Chi phí embedded mapping và serialization. |
| Nhiều affordance | Có các action links theo quyền/trạng thái | Chi phí policy check và link enrichment. |
| Nhiều media type | HAL và media type khác được hỗ trợ | Chi phí serializer và kích thước từng format. |

Chỉ tăng một biến tại một thời điểm khi muốn xác định nguyên nhân. Ví dụ, giữ dataset và quyền cố định, thay page size từ 10 lên 50 rồi đo lại.

## Đọc latency đúng cách

Đừng chỉ nhìn average. Trung bình có thể che giấu một nhóm request rất chậm.

| Thống kê | Cách đọc |
| --- | --- |
| p50 | Một request điển hình ở giữa phân phối. |
| p90 | 90% request hoàn thành không chậm hơn giá trị này. |
| p95 | Hữu ích để đánh giá phần đuôi latency thường gặp. |
| p99 | Cho thấy nhóm request chậm nhất và vấn đề tail latency. |
| Throughput | Số request xử lý mỗi giây ở mức tải đã chọn. |
| Error rate | Tỷ lệ request lỗi hoặc timeout trong workload. |

Ghi nhận p50/p95/p99 cùng throughput và error rate. Một thay đổi có thể giảm p95 nhưng làm throughput giảm hoặc error rate tăng; khi đó chưa thể xem là tối ưu.

## Dùng Spring Boot Actuator và Micrometer

Spring Boot tự động instrument request Spring MVC khi Actuator/Micrometer được cấu hình phù hợp. Metric mặc định có tên `http.server.requests`; các tag thường gồm method, status, outcome và URI template. URI template như `/api/orders/{id}` có cardinality thấp hơn URI chứa ID thật.

Thêm Actuator và một registry phù hợp với backend metrics của hệ thống. Có thể bật endpoint chẩn đoán trong môi trường nội bộ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Không công khai actuator endpoints ra Internet nếu chưa có authentication, authorization và network policy phù hợp. Endpoint `metrics` có thể tiết lộ cấu trúc ứng dụng và hoạt động nội bộ.

Nếu backend hỗ trợ histogram, cấu hình bucket/SLO cho request duration để theo dõi phân vị ở hệ thống monitoring:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms,250ms,500ms,1s
```

Các bucket phải phù hợp với SLO thực tế. Histogram làm tăng số time series và chi phí lưu trữ, vì vậy chỉ bật cho những metric cần thiết. Percentile được tính từ histogram có thể là xấp xỉ tùy backend và cấu hình.

Có thể xem metric qua endpoint nội bộ:

```http
GET /actuator/metrics/http.server.requests?tag=method:GET&tag=status:200
```

Thêm tag `uri` theo URI template nếu cần phân tích một endpoint cụ thể. Tên metric dùng trong `/actuator/metrics` là tên gốc Micrometer, không nhất thiết giống tên đã chuẩn hóa khi gửi sang Prometheus hoặc backend khác.

### Chọn tag có cardinality thấp

Metric tag phải có số lượng giá trị hữu hạn và kiểm soát được. Các giá trị như HTTP method, status, outcome, URI template và loại representation thường phù hợp. Tránh dùng các giá trị thay đổi theo từng request:

- Order ID, customer ID, user ID hoặc tenant ID.
- Full URL có query parameter.
- `href` của từng link.
- Trace ID, request ID hoặc session ID.
- Search term hoặc dữ liệu do người dùng gửi.

High-cardinality data có thể dùng trong trace/log có kiểm soát, nhưng không nên tạo một time series riêng cho từng ID trong metrics. Điều đó làm tăng bộ nhớ, chi phí truy vấn và có thể lộ dữ liệu cá nhân.

## Đo riêng chi phí của assembler

Metric tổng `http.server.requests` cho biết endpoint chậm, nhưng chưa cho biết assembler mất bao lâu. Có thể thêm Micrometer `Timer` quanh bước chuyển entity sang representation model.

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

@Component
class TimedOrderAssembler {

    private final OrderModelAssembler delegate;
    private final Timer assemblyTimer;

    TimedOrderAssembler(
            OrderModelAssembler delegate,
            MeterRegistry meterRegistry) {
        this.delegate = delegate;
        this.assemblyTimer = Timer.builder("hateoas.assembly")
            .description("Time spent assembling an order representation")
            .tag("model", "order")
            .register(meterRegistry);
    }

    EntityModel<OrderView> toModel(Order order) {
        return assemblyTimer.record(() -> delegate.toModel(order));
    }
}
```

Timer trên chỉ đo phần gọi `delegate.toModel(...)`. Nếu assembler thực hiện policy check hoặc gọi service, các chi phí đó cũng nằm trong khoảng đo này. Không gắn order ID hoặc user ID làm tag. Có thể tạo timer khác cho collection assembly nếu cần phân biệt hai workload.

Đừng bọc cùng một method bằng nhiều `@Timed`/`@Observed` một cách máy móc. Spring MVC đã instrument request; bật thêm annotation instrumentation cho cùng một thao tác có thể tạo observation trùng. Hãy đặt ranh giới rõ ràng giữa request tổng thể và stage nội bộ.

## Dùng distributed tracing để tìm stage chậm

Metrics cho biết xu hướng trên nhiều request; trace cho biết một request cụ thể đi qua những service và stage nào. Một trace có thể có các span:

```text
HTTP GET /api/orders
  ├── order.search
  │    └── database SELECT
  ├── order.toView
  ├── hateoas.collectionAssembly
  │    ├── order.itemAssembly
  │    └── authorization.check
  └── http.responseSerialization
```

Tên span ở đây là ví dụ do ứng dụng định nghĩa. Trace giúp trả lời service/database nào chậm, assembler nào chiếm thời gian và remote call nào kéo dài request. Không ghi payload, token, email hoặc toàn bộ `href` có query nhạy cảm vào span attributes.

Spring Boot dùng Micrometer Observation cho metrics và tracing. Spring MVC request được instrument tự động khi observability được cấu hình. Các stage nghiệp vụ có thể được instrument bằng Observation hoặc tracing API phù hợp với stack hiện tại. Dùng low-cardinality key values cho metrics; giá trị high-cardinality chỉ thêm vào trace khi có lý do và không chứa dữ liệu nhạy cảm.

## Profiling CPU và allocation bằng Java Flight Recorder

Khi metrics cho thấy endpoint tiêu tốn CPU hoặc allocation cao, Java Flight Recorder (JFR) giúp tìm method và call stack gây ra chi phí. JFR thu thập event về execution samples, allocation, GC, thread, lock và I/O. Có thể dùng JDK Mission Control (JMC) để xem recording hoặc dùng `jfr` command line.

### Ghi một profile ngắn

Tìm PID của JVM rồi chạy recording có thời lượng giới hạn:

```bash
jcmd <pid> JFR.start name=orders-api settings=profile duration=2m filename=orders-api.jfr
```

`profile` thu thập nhiều dữ liệu hơn cấu hình mặc định và có overhead lớn hơn. Chỉ ghi trong khoảng ngắn, dưới workload đại diện. Với recording liên tục hoặc production cần overhead thấp, xem xét `default.jfc` và chính sách vận hành phù hợp.

Đọc summary và một số event:

```bash
jfr summary orders-api.jfr
jfr print --events jdk.ExecutionSample,jdk.ObjectAllocationSample,jdk.GarbageCollection orders-api.jfr
```

JMC giúp mở file `.jfr`, xem hot methods, call tree, allocation profile, GC và thread/lock events. Đừng kết luận chỉ từ một stack sample; xác nhận bằng nhiều lần capture và so sánh với request metrics.

### Đọc kết quả theo giả thuyết

| Dấu hiệu trong recording | Có thể chỉ ra | Hướng kiểm tra tiếp |
| --- | --- | --- |
| Nhiều CPU samples ở Jackson/HAL serializer | Serialize body hoặc hypermedia model tốn CPU. | So sánh payload size, link count, embedded depth và media type. |
| Nhiều samples trong assembler/mapping | Mapping DTO, tạo affordance hoặc policy evaluation tốn CPU. | Đo stage timer và kiểm tra logic lặp trong assembler. |
| Allocation cao ở `Link`, collection, map hoặc string | Request tạo nhiều object khi dựng representation. | Đo allocation/request, kiểm tra số item/link và cấu trúc trung gian. |
| GC pause tăng cùng allocation rate | Heap pressure làm tail latency tăng. | Kiểm tra allocation profile, object lifetime và heap usage. |
| Thread chờ monitor/lock | Contention hoặc critical section tuần tự. | Xem lock owner, synchronized code và shared mutable state. |
| Thread chờ socket/database | I/O hoặc downstream service chậm. | Xem DB query, connection pool, remote call và network. |

Execution samples chỉ lấy mẫu thread đang chạy code. Nếu thread chờ I/O, lock hoặc socket, cần xem thêm event chờ/blocked thay vì chỉ nhìn hot methods.

## Đo response size và link density

Hypermedia thêm metadata vào payload. Một collection 100 item có thể chứa 100 self links và nhiều action links. Kích thước body phụ thuộc số item, số link, độ dài URI, link title, embedded resource và JSON structure.

Theo dõi tối thiểu:

- Body bytes trước và sau compression.
- Số item được trả về.
- Số link trung bình trên mỗi item và ở cấp collection.
- Độ sâu và số lượng embedded resource.
- Số affordance/action link được công bố.
- Thời gian serialize và thời gian truyền response.

`Content-Length` có thể không xuất hiện nếu response dùng chunked transfer hoặc được nén ở proxy. Gateway metrics thường phản ánh số byte thực truyền tốt hơn; application metrics có thể đo số byte serialized trước compression. Hãy phân biệt hai con số này.

Không thêm filter buffer toàn bộ response chỉ để đo byte trong production mà chưa đánh giá tác động. Cách dùng `ContentCachingResponseWrapper` có thể giữ toàn bộ body trong memory và làm thay đổi hành vi streaming. Trong benchmark hoặc test có kiểm soát, có thể đo byte từ HTTP client sau khi nhận response.

### So sánh payload có và không có hypermedia

Nếu cần hiểu overhead của link, tạo các biến thể workload có cùng data fields và page size:

1. DTO JSON thuần làm baseline.
2. HAL với collection self link và item self links.
3. HAL với các action links theo trạng thái.
4. HAL với embedded resource.

So sánh response bytes, serialization time, allocation/request và end-to-end latency. Đây là phép đo chi phí của các tính năng hypermedia trong workload cụ thể; không phải lý do để xóa link cần thiết cho hợp đồng API.

## Phân biệt chi phí tạo link với chi phí truy vấn dữ liệu

Việc gọi `linkTo(...)` hoặc `methodOn(...)` không tự động thực hiện SQL query. Nếu profile cho thấy database chiếm phần lớn thời gian, kiểm tra repository, lazy association, service và authorization lookup. Nếu CPU tập trung trong serializer hoặc assembler, tập trung đo những stage đó.

Với collection, số item tăng thường kéo theo số lần mapping và số link tăng. Hãy đo theo page size và xác định chi phí tăng tuyến tính hay tăng nhanh hơn dự kiến. Nếu số query tăng theo item, đó là vấn đề truy cập dữ liệu cần được xử lý ở repository/service layer; không kết luận rằng Link builder gây N+1 chỉ vì vấn đề xuất hiện trong request HATEOAS.

## Thiết kế benchmark có kiểm soát

Một quy trình benchmark endpoint có thể thực hiện như sau:

1. Chuẩn bị môi trường gần production về JDK, container limit, DB, proxy và compression.
2. Nạp dataset cố định, xác định cache warm/cold state.
3. Chọn endpoint và media type cụ thể.
4. Warm up bằng tải thấp trong một khoảng đã định.
5. Chạy các mức concurrency và duration giống nhau cho mỗi phiên bản.
6. Ghi latency percentiles, throughput, error rate, CPU, heap, GC, DB latency và response bytes.
7. Capture JFR trong một lần chạy đại diện.
8. Lặp lại nhiều lần và so sánh phân phối, không chọn lần chạy đẹp nhất.
9. Thay một yếu tố, chạy lại đúng workload và xác nhận cải thiện không làm giảm tính đúng đắn.

Giữ nguyên request mix. Ví dụ, không so sánh bản cũ chỉ có GET item với bản mới có GET collection và embedded customer. Kiểm soát cả data distribution, auth role, sort, filter và compression.

### JMH hay load test HTTP?

| Công cụ | Dùng khi nào? | Không trả lời được một mình |
| --- | --- | --- |
| JMH | Đo một method thuần như mapper, converter hoặc hàm tạo relation trong JVM. | Không đại diện đầy đủ cho servlet, network, DB và end-to-end HTTP. |
| Load test HTTP | Đo endpoint qua server/container với concurrency, network và serializer thực tế. | Không tự xác định method nào trong JVM gây chậm. |
| JFR/JMC | Tìm CPU hot path, allocation, GC, lock và I/O wait trong lúc workload chạy. | Không thay thế workload tái lập và latency metrics. |
| Distributed tracing | Tách thời gian theo service/span và downstream calls. | Không thay thế CPU/allocation profiling ở mức method. |

Kết hợp các công cụ theo câu hỏi. JMH không phải cách thay thế load test API; JFR không phải công cụ tạo tải.

## Diễn giải bottleneck và chọn hướng tối ưu

Sau khi profiling, đối chiếu dấu hiệu với hướng xử lý:

| Bottleneck đã xác nhận | Hướng xử lý có thể thử |
| --- | --- |
| Database/query time cao | Tối ưu query/index, projection, batch fetch hoặc giảm dữ liệu cần đọc. |
| Mapping/assembler CPU cao | Loại bỏ mapping lặp, tránh tính toán lại cùng metadata trong một request, dùng DTO rõ ràng. |
| Policy/authorization checks cao | Gom quyền theo batch hoặc cache quyết định trong phạm vi request nếu semantics cho phép. |
| HAL serialization cao | Giảm embedded payload không cần thiết, kiểm soát page size, tránh object graph quá sâu và đánh giá serializer config. |
| Response bytes lớn | Dùng pagination, DTO gọn, compression phù hợp và loại bỏ field không cần công bố. |
| Allocation/GC cao | Giảm object trung gian, collection tạm và string tạo lặp; xác nhận bằng allocation profile. |
| Network/downstream wait cao | Kiểm tra connection pool, timeout, DNS, proxy, remote service và payload size. |
| Tail latency do lock contention | Giảm critical section, tránh khóa dùng chung trong request path và kiểm tra thread dump/JFR lock events. |

Không tối ưu chỉ vì một method xuất hiện nhiều trong profile. Một method có nhiều sample có thể chỉ đơn giản được gọi nhiều lần; cần tính chi phí mỗi request và số lần gọi. Nếu `toModel()` mất 0,1 ms nhưng được gọi 500 lần, tổng chi phí khác với một lần gọi mất 10 ms.

## Những lỗi profiling thường gặp

| Lỗi | Vì sao gây hiểu sai | Cách làm tốt hơn |
| --- | --- | --- |
| Chỉ đo average latency | Che giấu tail latency. | Ghi p50, p95, p99 cùng throughput và error rate. |
| Profile ngay sau startup | JIT, connection pool và cache chưa warm. | Tách cold-start test và steady-state test. |
| Chỉ dùng MockMvc để kết luận network performance | MockMvc không đi qua socket/network thực như client bên ngoài. | Dùng embedded/production-like server và HTTP load test. |
| Dùng JMH để kết luận endpoint nhanh hơn | JMH bỏ qua HTTP, DB, container và network. | Dùng JMH cho method; dùng load test cho endpoint. |
| Gắn ID vào metric tag | Tạo cardinality rất lớn và có thể lộ dữ liệu. | Dùng URI template và low-cardinality tags. |
| Bật profiler nặng trong thời gian dài | Instrumentation có thể làm thay đổi hành vi hệ thống. | Dùng recording ngắn, ghi rõ profiler settings và overhead. |
| Chỉ nhìn CPU hot methods | Bỏ qua I/O wait, lock và DB latency. | Kết hợp JFR, trace và database metrics. |
| Đo payload trước compression nhưng gọi đó là wire bytes | Không phản ánh số byte thực truyền. | Ghi rõ serialized bytes và transmitted bytes. |
| Cache assembled model theo key thiếu context | Có thể trả link/affordance sai user, host hoặc tenant. | Chỉ cache khi key bao phủ mọi biến ảnh hưởng và semantics an toàn. |
| Tối ưu trước khi có baseline | Không biết thay đổi có cải thiện hay không. | Đo trước, đổi một yếu tố, đo lại cùng workload. |

## Checklist trước và sau khi tối ưu

**Trước khi thay đổi:**

- [ ] Chọn endpoint, media type và request mix.
- [ ] Ghi phiên bản runtime, cấu hình và dataset.
- [ ] Warm up và chạy workload ổn định.
- [ ] Ghi p50/p95/p99, throughput, error rate và response bytes.
- [ ] Xem trace và JFR để xác định stage/method nghi ngờ.
- [ ] Đưa ra giả thuyết có thể kiểm chứng.

**Sau khi thay đổi:**

- [ ] Chạy lại cùng workload và điều kiện.
- [ ] So sánh phân phối latency, throughput và lỗi.
- [ ] So sánh CPU, allocation, GC và response bytes.
- [ ] Kiểm tra HAL links, relations, affordances và dữ liệu vẫn đúng.
- [ ] Kiểm tra authorization và tenant isolation.
- [ ] Ghi lại thay đổi, số đo và giới hạn của kết quả.

## Ghi nhớ

- Profiling phải bắt đầu từ một câu hỏi và baseline có thể tái lập.
- Phân biệt client latency, server duration, span duration, CPU, allocation và response bytes.
- Spring Boot Actuator/Micrometer cung cấp `http.server.requests` để quan sát Spring MVC request.
- Dùng timer riêng cho assembler hoặc stage quan trọng; không gắn ID vào metric tags.
- Distributed tracing giúp chia request thành các stage và xác định downstream wait.
- JFR/JMC giúp tìm hot methods, allocation, GC, lock contention và I/O wait.
- Đo link count, embedded depth và payload bytes để hiểu overhead của hypermedia.
- Dùng load test cho endpoint HTTP; dùng JMH cho method thuần; dùng JFR để tìm nguyên nhân trong JVM.
- Thay đổi một yếu tố và so sánh cùng workload trước/sau.
- Giữ tính đúng đắn của links, affordances, authorization và representation khi tối ưu hiệu năng.

## Tài liệu tham khảo

- [Spring Boot Reference – Metrics and Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Reference – Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Framework Reference – Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [Oracle Java 26 – Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK – jcmd Command](https://docs.oracle.com/en/java/javase/23/docs/specs/man/jcmd.html)
