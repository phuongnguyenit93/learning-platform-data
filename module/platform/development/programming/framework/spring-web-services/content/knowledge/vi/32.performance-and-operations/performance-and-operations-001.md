# Đo độ trễ theo từng lớp: transport, XML, bảo mật và nghiệp vụ

Một lời gọi SOAP mất 1,8 giây không cho biết phải sửa ở đâu. Thời gian có thể nằm trong hàng đợi kết nối HTTP, DNS/TLS, serialize XML, parse và validate XSD, marshal/unmarshal JAXB, xác minh chữ ký WS-Security, chờ database hoặc xử lý nghiệp vụ. Nếu chỉ đo tổng thời gian `WebServiceTemplate.marshalSendAndReceive`, đội vận hành biết request chậm nhưng chưa biết lớp nào gây chậm và lớp nào chỉ chờ lớp khác.

Giải pháp là **đo theo từng lớp và gắn các phép đo vào cùng một trace**. Bắt đầu bằng latency tổng từ góc nhìn caller; tiếp tục tách thời gian ở client transport, server transport, XML processing, security và business; sau đó đối chiếu với queue, connection pool, CPU, GC và lỗi. Phép đo cần dùng đồng hồ monotonic cho duration, histogram cho phân phối, tag có cardinality kiểm soát và trace context để nối các span qua nhiều dịch vụ.

Bài này thuộc chương **Hiệu năng và vận hành** của module **SPRING_WEB_SERVICES**. Module học phát triển SOAP contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB, endpoint và SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tích hợp doanh nghiệp. Bài tập trung cách đo và chẩn đoán độ trễ xuyên suốt các lớp transport, XML, security và nghiệp vụ để có bằng chứng khi tối ưu.

## 1. Xác định chính xác độ trễ đang đo

Trước khi tạo metric, phải định nghĩa điểm bắt đầu và kết thúc:

| Góc nhìn | Bắt đầu | Kết thúc | Ý nghĩa |
| --- | --- | --- | --- |
| **Caller end-to-end** | Trước khi gọi SOAP client | Client nhận response hoặc exception | Thời gian caller thực sự chờ |
| **Client transport** | Bắt đầu gửi qua message sender | Nhận đủ response từ transport | Kết nối, ghi request, chờ server, đọc response |
| **Server processing** | Server nhận message sau transport | Server hoàn tất tạo response | Phần server nhìn thấy trong request lifecycle |
| **Endpoint/business** | Trước endpoint handler/domain call | Sau khi business result sẵn sàng | Thời gian xử lý nghiệp vụ |
| **XML** | Bắt đầu parse/unmarshal/validate | Hoàn tất từng bước | Chi phí biểu diễn và kiểm tra XML |
| **Security** | Bắt đầu security processing | Hoàn tất verify/decrypt/sign/encrypt | Chi phí mật mã và policy |

Các con số trên có thể **lồng nhau**. Ví dụ client round-trip bao gồm thời gian chờ server; server processing lại chứa XML, security và business. Không cộng tất cả span duration với nhau như các khoảng độc lập. Khi xây breakdown, chỉ cộng các đoạn **exclusive** không chồng lấn, hoặc trình bày span cha/con riêng.

### 1.1. Timeline một request SOAP

~~~mermaid
flowchart LR
    A["Caller starts"] --> B["Client marshal"]
    B --> C["Pool / connect / TLS"]
    C --> D["Send request"]
    D --> E["Server receives"]
    E --> F["Parse SOAP / XML"]
    F --> G["WS-Security verify / decrypt"]
    G --> H["XSD validation / unmarshal"]
    H --> I["Endpoint / business / DB"]
    I --> J["Marshal response"]
    J --> K["Sign / encrypt response"]
    K --> L["HTTP write"]
    L --> M["Client reads / unmarshal"]
    M --> N["Caller completes"]
~~~

Sơ đồ cho thấy các bước khái niệm; thứ tự thực tế phụ thuộc transport, interceptor chain, validation và security configuration. Có hệ thống validate trước hoặc sau một số bước; MTOM, streaming và custom interceptors cũng thay đổi đường đi. Hãy đo trên pipeline thật và ghi rõ ranh giới span.

### 1.2. Latency, throughput và saturation là ba góc nhìn khác nhau

- **Latency**: một request mất bao lâu.
- **Throughput**: số request hoàn tất trong một đơn vị thời gian.
- **Saturation**: tài nguyên gần hết khả năng phục vụ, ví dụ worker threads, pool connections, CPU hoặc queue capacity.

Throughput có thể tăng trong khi p99 xấu đi vì hệ thống bắt đầu xếp hàng. Ngược lại, p50 thấp không chứng minh hệ thống khỏe nếu một nhóm request hiếm nhưng quan trọng bị chậm. Luôn xem latency cùng traffic, error rate và resource saturation.

## 2. Chọn công cụ đo và mô hình telemetry

Trong Java, dùng `System.nanoTime()` cho khoảng thời gian trong cùng process. Không dùng `System.currentTimeMillis()` để tính duration vì clock wall-time có thể bị chỉnh bởi NTP hoặc hệ điều hành. Lưu timestamp lịch để đối chiếu log; dùng monotonic clock để tính elapsed time.

### 2.1. Ba loại telemetry bổ sung cho nhau

| Loại | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Metric** | Lớp nào đang chậm theo thời gian? | Timer p50/p95/p99, error count, pool active |
| **Trace/span** | Request cụ thể đã đi qua đâu và chờ ở đâu? | client span → server span → DB span |
| **Log/event** | Điều gì xảy ra trong lần gọi này? | SOAP Fault code, timeout class, partner code |

Metric giúp thấy xu hướng và SLO; trace tìm đường đi của một request; log giải thích chi tiết sự kiện. Đặt cùng trace ID/correlation ID nhưng tránh ghi raw SOAP XML, credential, token, chữ ký hoặc dữ liệu khách hàng vào telemetry.

### 2.2. Micrometer Timer cho duration

Micrometer `Timer` được thiết kế để đo thời lượng ngắn và tần suất event; nó ghi count và total time, đồng thời có thể xuất max, percentiles hoặc histogram tùy registry/configuration. Timer hỗ trợ đo bằng `record(Duration)`, `record(Runnable)` và các overload callable. [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)

Ví dụ ghi thời gian client round-trip:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.Callable;

public final class TimedOrderClient {
    private final OrderSoapClient delegate;
    private final Timer roundTrip;

    public TimedOrderClient(
            OrderSoapClient delegate,
            MeterRegistry registry) {
        this.delegate = delegate;
        this.roundTrip = Timer.builder("soap.client.roundtrip")
                .description("SOAP client end-to-end duration")
                .tag("operation", "get-order")
                .register(registry);
    }

    public OrderResponse getOrder(OrderRequest request) {
        return roundTrip.record(() -> delegate.getOrder(request));
    }
}
~~~

Đây là phép đo caller round-trip: nó bao gồm marshal, transport, thời gian server xử lý và unmarshal trong phạm vi delegate. Nó không phải metric riêng của HTTP socket hay server. Ghi duration cả khi Callable ném exception; phân loại error bằng metric riêng hoặc tag có tập giá trị hữu hạn, không đưa exception message vào tag.

### 2.3. Timer.Sample khi cần gắn outcome lúc kết thúc

`Timer.Sample` cho phép bắt đầu ở đầu flow và chọn Timer lúc dừng, ví dụ chọn outcome success/fault/error ở cuối. Mẫu:

~~~java
Timer.Sample sample = Timer.start(registry);
String outcome = "success";
try {
    return invokePartner();
} catch (SoapFaultClientException ex) {
    outcome = "soap_fault";
    throw ex;
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    Timer timer = Timer.builder("soap.client.call")
            .tag("operation", "get-order")
            .tag("outcome", outcome)
            .register(registry);
    sample.stop(timer);
}
~~~

Không gắn message Fault hoặc tên exception đầy đủ vào tag; những giá trị đó tạo cardinality không giới hạn và có thể chứa dữ liệu nhạy cảm. Chọn `outcome` từ một enum nhỏ đã chuẩn hóa. Phần exception cụ thể cần thiết cho chẩn đoán có thể ghi log đã lọc hoặc span event.

## 3. Phân rã transport latency

Transport latency có thể gồm nhiều pha:

1. Chờ connection từ pool.
2. DNS lookup và mở TCP connection khi cần connection mới.
3. TLS handshake, certificate validation và hostname verification.
4. Ghi request bytes và chờ response bytes.
5. Đọc response body; có thể bao gồm server processing và network transit.
6. Đóng hoặc trả connection về pool.

Một connection persistent được reuse không trả chi phí DNS/TCP/TLS ở mỗi call. Vì thế đừng mặc định mỗi request đều có handshake. Cần phân biệt **pool wait**, **new connection**, **TLS handshake** và **time to first byte/response read**.

### 3.1. Những phép đo hữu ích ở client

| Measurement | Diễn giải khi tăng |
| --- | --- |
| Pool pending/acquire wait | Pool cạn, connection bị giữ lâu hoặc giới hạn quá thấp |
| New connection rate | Reuse kém, keep-alive bị đóng hoặc endpoint thay đổi |
| DNS/TCP connect | DNS hoặc mạng có vấn đề |
| TLS handshake duration/failure | Certificate chain, cipher negotiation, remote load hoặc full handshake |
| Request write duration | Payload lớn, socket backpressure hoặc network congestion |
| Time to first byte | Server chậm, queue hoặc network path |
| Response read duration | Response lớn, server stream chậm hoặc downstream link |
| Client timeout count | Timeout budget quá ngắn hoặc có saturation |

Không phải mọi `WebServiceMessageSender` đều expose đầy đủ các pha này. Hãy chọn HTTP client/connection manager có metric hoặc event instrumentation phù hợp; khi cần, instrument ở transport implementation thay vì suy ra các pha từ tổng `marshalSendAndReceive`.

### 3.2. Connection pool và keep-alive

Theo dõi tối thiểu:

- Tổng connections, leased/active, available/idle và pending acquisition.
- Max connections toàn pool và per route/host.
- Connection TTL/idle eviction, reuse rate và connection churn.
- Timeout lấy connection, connect timeout và response/read timeout.

Pool nhỏ tạo queue wait ngay cả khi server còn rảnh. Pool quá lớn có thể tạo áp lực lên partner, file descriptors, TLS contexts và server concurrency. Tune theo tải, số host, thời gian giữ connection và quota đối tác; không tăng max pool chỉ để làm biến mất queue mà không xem saturation phía server.

### 3.3. Tách timeout theo pha và deadline tổng

Các timeout phải có nghĩa riêng:

| Timeout | Giới hạn |
| --- | --- |
| Connection request/acquire | Chờ connection trong pool |
| Connect | Mở TCP socket |
| TLS handshake | Hoàn tất thương lượng TLS (nếu client expose riêng) |
| Response/read | Chờ dữ liệu phản hồi |
| Application deadline | Toàn bộ call gồm marshal, queue, transport, xử lý và parse |

Một request có thể chờ pool 500 ms, connect 1 s, response 2 s rồi vượt deadline caller. Thiết lập budget phân cấp để các tầng bên trong dừng trước hoặc tại deadline tổng, có phần dự phòng cho serialize/cleanup. Không đặt mọi timeout cùng một số tùy tiện; xác định rõ timeout nào được tính vào budget nào.

### 3.4. Đo server ingress/egress

Server-side timing bắt đầu khi container/transport đã nhận message và kết thúc khi message được serialize/ghi ra. Nó không bao gồm toàn bộ thời gian mạng từ caller. So sánh:

- Client round-trip span.
- Server request-processing span.
- Server response-write/transport metrics nếu có.
- Gateway/proxy duration nếu request đi qua nhiều hop.

Khoảng chênh giữa client và server có thể là network transit, proxy queue, pool wait ở caller hoặc thời gian trước/sau vùng instrumentation. Không gán phần chênh cho “network” nếu chưa loại các pha khác.

## 4. Phân rã chi phí XML và JAXB/OXM

Một SOAP Body có thể tiêu tốn CPU và allocation ở các bước parse XML, tạo object tree, kiểm XSD, unmarshal JAXB, xử lý payload, marshal response và serialize bytes. Payload càng lớn hoặc có nested collection sâu thì chi phí CPU/memory càng rõ.

### 4.1. Những pha XML nên đo riêng

| Pha | Đơn vị đo gợi ý | Chỉ báo liên quan |
| --- | --- | --- |
| SOAP envelope parse | ms/message | XML bytes, element count |
| XSD validation | ms/message | Schema complexity, validation failures |
| JAXB/OXM unmarshal | ms/message | Payload bytes, object count, allocations |
| Endpoint payload transform/XSLT | ms/message | Input/output bytes, transform errors |
| JAXB/OXM marshal | ms/message | Response object size/collection count |
| XML serialization | ms/message | Output bytes, compression |

Không instrument từng node XML hoặc từng field nếu overhead lớn. Chọn ranh giới đủ để xác định bước gây chi phí và đo trên workload đại diện.

### 4.2. Kích thước payload và thời gian không luôn tuyến tính

XML payload gấp đôi không nhất thiết làm latency gấp đôi. Schema validation có thể chịu ảnh hưởng cấu trúc; JAXB tạo nhiều object hơn số byte; XPath/XSLT có thể duyệt cây nhiều lần; GC có thể tăng theo allocation. Theo dõi đồng thời:

- Bytes request/response (bucket hóa nếu cần).
- Số item/record trong collection.
- Độ sâu và số element nếu ứng dụng có thể đo rẻ.
- Thời gian parse/validate/marshal.
- Allocation rate, GC pause và heap occupancy.

Tránh tag exact payload size hoặc ID từng request. Dùng histogram/bucket size hoặc log theo sampling.

### 4.3. Giảm chi phí bằng cách tối ưu có bằng chứng

- Dùng schema/JAXB context đã khởi tạo và tái sử dụng đúng thread-safety contract; tránh compile schema/context cho mỗi request.
- Tránh unmarshal cùng payload nhiều lần trong các interceptor.
- Không serialize rồi parse lại XML nếu có thể truyền payload/object đã có.
- Dùng streaming/ StAX khi payload lớn và processing model cho phép; xác minh attachment/MTOM handling.
- Giữ XSLT stylesheet và compiled template được quản lý theo lifecycle phù hợp; đo processor và memory thực tế.
- Chỉ tắt XSD validation ở runtime khi đã có quyết định hợp đồng/risk rõ ràng; validation có thể là ranh giới correctness/security, không chỉ overhead.

## 5. Đo WS-Security và chi phí chứng chỉ

WS-Security có thể thực hiện UsernameToken validation, timestamp checks, signature verification, decryption, signing và encryption. Những bước này thường tốn CPU hơn khi message lớn, có nhiều signed references, certificate chain phức tạp hoặc khóa bất đối xứng nặng.

### 5.1. Tách inbound và outbound security

| Pha | Thành phần | Metric gợi ý |
| --- | --- | --- |
| Inbound credential processing | UsernameToken/callback/password validation | Duration, reject count |
| Timestamp/replay checks | Clock skew, replay cache/store | Duration, expired/replay count |
| Signature verification | Canonicalization, digest, public-key verify | Duration, signature failure |
| Decryption | Key lookup, private-key operation, XML decrypt | Duration, decrypt failure |
| Outbound signing | Canonicalization, digest, private-key sign | Duration, sign failure |
| Outbound encryption | Key wrapping, content encryption | Duration, encrypt failure |

Đừng gộp mọi lỗi vào một metric `security.failed` nếu cần phân biệt certificate/trust, signature, timestamp và decryption. Tuy vậy, tag chỉ nên dùng error category hữu hạn; chi tiết certificate subject/serial nên log có kiểm soát, không biến thành tag metric.

### 5.2. Certificate/key lookup và cache

Độ trễ có thể nằm ở:

- Đọc keystore hoặc parse certificate chain.
- Trust path construction và revocation checks (nếu bật).
- Lookup key alias/partner identity.
- Truy cập remote HSM/KMS hoặc signing service.
- Key rotation/cache miss.

Đo cold start riêng với steady state. Không cache quyết định trust/revocation quá thời hạn policy chỉ để giảm latency. Theo dõi thời gian key operation và lỗi HSM/KMS tách khỏi CPU cryptography trong JVM.

### 5.3. Bảo mật và hiệu năng phải cùng tồn tại

Không bỏ signature verification, timestamp, replay defense, encryption hay certificate validation chỉ vì chúng làm chậm p99. Trước tiên đo từng pha, giảm lookup lặp, tối ưu cache theo policy, chọn key/provider phù hợp và giới hạn message complexity. Mọi thay đổi security policy phải được kiểm thử interoperability và threat model.

## 6. Đo endpoint và nghiệp vụ

Business time thường bao gồm nhiều đoạn: validate dữ liệu nghiệp vụ, authorize resource, đọc/ghi database, gọi service khác, publish event và áp dụng transaction. Đo một timer quanh endpoint chỉ biết tổng thời gian của handler; để tìm nguyên nhân, thêm child spans/timers ở các dependency quan trọng.

~~~mermaid
flowchart TD
    A["SOAP endpoint span"] --> B["Request mapping / validation"]
    B --> C["Authorization"]
    C --> D["Application service"]
    D --> E["Database query"]
    D --> F["Downstream service"]
    D --> G["Transaction commit"]
    G --> H["Build response"]
~~~

Các span con có thể chồng lấn nếu service gọi song song. Thời gian wall-clock của application service không bằng tổng thời gian các dependency khi chúng chạy đồng thời. Trace thể hiện quan hệ cha/con và song song; breakdown exclusive time mới trả lời đoạn nào chiếm phần còn lại.

### 6.1. Những timer hữu ích ở tầng nghiệp vụ

| Metric | Mục đích |
| --- | --- |
| `soap.server.endpoint` | Tổng thời gian từ endpoint invocation đến khi handler trả kết quả |
| `soap.business.validation` | Kiểm tra rule nghiệp vụ |
| `soap.business.authorization` | Kiểm tra quyền |
| `soap.business.database` | Đo repository/query hoặc transaction segment |
| `soap.business.downstream` | Đo call dịch vụ phụ thuộc |
| `soap.business.transaction` | Thời gian commit/rollback nếu đo được đúng ranh giới |

Không tạo timer riêng cho từng order/customer/partner ID. Dùng tags hữu hạn như operation, outcome, error category và dependency name đã chuẩn hóa.

### 6.2. Tách queue wait khỏi execution time

Khi xử lý async hoặc qua JMS, tổng thời gian business completion có thể gồm:

- Thời gian message nằm trong queue.
- Thời gian chờ consumer/worker.
- Thời gian xử lý endpoint/business.
- Thời gian gửi reply và client nhận reply.

Gắn enqueue timestamp hoặc messaging trace context vào message để tính queue age; ghi execution timer riêng khi consumer bắt đầu. Với request-response qua JMS, đo cả send-to-reply round-trip ở caller và consumer processing. Không gán toàn bộ queue delay cho endpoint code.

### 6.3. Ví dụ đo một dependency

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class TimedOrderRepository {
    private final OrderRepository delegate;
    private final Timer queryTimer;

    public TimedOrderRepository(
            OrderRepository delegate,
            MeterRegistry registry) {
        this.delegate = delegate;
        this.queryTimer = Timer.builder("soap.business.database")
                .description("Database duration for SOAP operations")
                .tag("repository", "order-by-id")
                .register(registry);
    }

    public Order findById(String id) {
        return queryTimer.record(() -> delegate.findById(id));
    }
}
~~~

Đây là wrapper minh họa; nếu repository trả `Optional<Order>`, `CompletableFuture` hoặc publisher, chọn overload/wrapper đo đúng thời điểm completion. Không dừng timer ngay khi chỉ tạo ra future/publisher, vì khi đó công việc thực tế chưa hoàn thành.

## 7. Nối metrics với distributed tracing

Metrics chỉ cho phân phối aggregate; trace cho phép chọn một request cụ thể và nhìn các pha của nó. Với SOAP qua HTTP, có thể propagate W3C Trace Context bằng `traceparent` và `tracestate` khi cả hai bên hỗ trợ và trust policy cho phép. W3C Trace Context định nghĩa header và format để các hệ thống chia sẻ context tracing qua HTTP. [W3C Trace Context](https://www.w3.org/TR/trace-context/)

SOAP có thể chạy trên HTTP, JMS hoặc transport khác. `traceparent` là HTTP header; không tự giả định nó sẽ xuất hiện trong SOAP Header hoặc JMS message. Với transport không phải HTTP, dùng propagator tương ứng của tracing framework hoặc một SOAP header correlation được contract hóa; xác định ranh giới tin cậy và validate incoming context.

### 7.1. Mô hình span đề xuất

~~~text
soap.client get-order                 [client span]
  ├─ soap.client.marshal              [internal]
  ├─ http.connection.acquire          [internal]
  ├─ http.client request              [client/transport]
  │    └─ soap.server request         [server span]
  │         ├─ soap.xml.parse
  │         ├─ soap.security.verify
  │         ├─ soap.xml.validate
  │         └─ soap.endpoint get-order
  │              ├─ business.authorize
  │              ├─ db.query
  │              └─ downstream.inventory
  │         ├─ soap.security.sign
  │         └─ soap.response.serialize
  └─ soap.client.unmarshal
~~~

Tên span trên là convention nội bộ gợi ý, không phải tên chuẩn bắt buộc của OpenTelemetry. Không tạo span cho mọi field hoặc từng XML node; chọn spans có thể hành động được và tránh tạo quá nhiều span trong loop lớn.

### 7.2. Propagation, sampling và privacy

- Tạo một trace ID cho logical request; mỗi hop tạo span ID riêng.
- Không tự lấy customer ID/order ID/username làm trace ID.
- Không coi trace context từ Internet/partner là đáng tin tuyệt đối; có thể restart trace ở trust boundary theo policy.
- Sampling phải giữ đủ lỗi và request chậm để điều tra, nhưng kiểm soát volume.
- Không đặt PII, token, credential hoặc dữ liệu business nhạy cảm vào \`tracestate\`, baggage hay span attributes.
- Không log toàn bộ SOAP Body/WS-Security header để “tăng khả năng trace”; dùng identifiers đã lọc và payload hash khi thực sự cần.

W3C nêu rõ trace context không được dùng để mang thông tin cá nhân; các trường trace phục vụ correlation. [W3C Trace Context — Privacy Considerations](https://www.w3.org/TR/trace-context/#privacy-considerations)

## 8. Histogram, percentiles và SLO

Một mean 120 ms có thể che p99 3 giây. Với dịch vụ SOAP phục vụ đối tác, theo dõi latency distribution theo operation và outcome:

- **p50**: trải nghiệm thường gặp.
- **p95**: phần đuôi ảnh hưởng đáng kể người dùng.
- **p99**: tail latency; quan trọng với timeout và batch orchestration.
- **Max**: hữu ích như tín hiệu, nhưng nhạy với outlier và thời gian cửa sổ.
- **SLO buckets**: tỷ lệ request hoàn tất trong các ngưỡng cụ thể.

Micrometer Timer có thể phát histogram/percentile tùy backend. Histograms cho phép backend tổng hợp bucket; client-side percentiles thường được tính riêng ở từng instance và không nhất thiết gộp chính xác được giữa replicas. Chọn cách xuất theo khả năng backend và nhu cầu aggregation. [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)

### 8.1. Cấu hình histogram và SLO trong Spring Boot

Ví dụ cấu hình cho timer `soap.client.roundtrip`:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        soap.client.roundtrip: true
      slo:
        soap.client.roundtrip: 100ms,250ms,500ms,1s,2s
~~~

Đây là cấu hình minh họa; xác nhận prefix/property format đúng với Spring Boot version của ứng dụng và backend registry. Spring Boot hỗ trợ cấu hình per-meter histogram/percentile/SLO và endpoint metrics để xem meter đã đăng ký. [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)

### 8.2. Cardinality có thể trở thành sự cố vận hành

Không đưa các giá trị sau vào tag metric:

- Request ID, trace ID, order ID, customer ID.
- Raw endpoint URL chứa path/query biến đổi.
- SOAP Fault message hoặc exception message.
- Certificate serial/subject nếu mỗi partner/cert rotation tạo giá trị mới không kiểm soát.
- Payload QName từ dữ liệu chưa được allowlist.

Ưu tiên `operation=get-order`, `transport=http`, `outcome=soap_fault`, `error_category=signature`. Partner tag chỉ nên dùng nếu số partner bounded và được quản lý. Dùng trace/log để tìm request cá biệt.

### 8.3. Định nghĩa latency SLO đúng population

Ví dụ: “99% request `GetOrder` hợp lệ hoàn tất dưới 800 ms trong cửa sổ 30 ngày.” Cần làm rõ:

- Đo caller end-to-end hay server processing?
- Có tính timeout, retry và SOAP Fault không?
- Exclude health checks/batch polling hay không?
- Tách theo operation hay gộp mọi operation?
- Request được tính tại lần thử hay logical operation sau retry?

Đừng loại mọi request lỗi khỏi latency denominator nếu lỗi/timeout chính là trải nghiệm caller. Có thể có SLI riêng cho successful latency và availability, nhưng phải công bố quy tắc đếm rõ.

## 9. Đọc dấu hiệu để tìm bottleneck

| Quan sát | Nguyên nhân khả dĩ | Kiểm tra tiếp |
| --- | --- | --- |
| Client p99 tăng, server processing ổn định | Pool wait, proxy/network, client marshal/unmarshal | Pool metrics, client spans, gateway duration |
| Server p99 tăng, endpoint/business timer tăng | DB, downstream hoặc lock contention | Child spans, query latency, thread dump |
| XML timer tăng cùng payload bytes | Parse/validation/JAXB/XSLT | Payload size buckets, allocation, schema |
| Security timer tăng, CPU cao | Signature/canonicalization/encryption | WSS4J phases, key provider, message complexity |
| Security latency tăng nhưng CPU thấp | Remote HSM/KMS, trust lookup, revocation/OCSP | Dependency span, cache hit/miss |
| Pool pending tăng và server rảnh | Pool sizing/connection leak/slow read | Leased count, response close, timeout |
| p50 ổn nhưng p99 xấu | Tail dependencies, queueing, GC pause, noisy neighbor | Histograms, trace exemplars, GC/thread metrics |
| Throughput không tăng dù CPU thấp | Blocking I/O, bounded pool, semaphore, downstream quota | Thread dump, pending queue, pool metrics |
| Timeout nhiều nhưng timer server thấp | Caller deadline/pool/connect/network hoặc server work bị cắt ở điểm khác | Timeout phase, cancellation, matching trace |
| SOAP Fault tăng cùng security time | Cert/token/signature rejection hoặc partner drift | Fault categories, cert expiration, algorithm |

Một correlation không phải bằng chứng nguyên nhân. Ví dụ security latency và CPU cùng tăng có thể do payload lớn hơn, không phải thuật toán crypto chậm đi; hãy kiểm size và cấu hình đồng thời.

## 10. Load test và benchmark có thể so sánh

Đo trong môi trường rảnh một lần không đủ để dự đoán production. Cần workload phản ánh phân phối request thật:

1. Chọn operations, kích thước XML, SOAP version, số headers/attachments và tỷ lệ Fault hợp lý.
2. Dùng test certificates/security policy tương đương production; không bỏ security để benchmark nếu production bật nó.
3. Chạy warm-up để JIT, class loading, schema/JAXB initialization và connection pool ổn định.
4. Tăng concurrency theo từng bậc; ghi throughput, p50/p95/p99, errors, pool pending, CPU, heap/GC và dependency latency.
5. Giữ đủ thời gian steady-state để histogram có mẫu; chạy soak test để tìm leak/cache expiry/certificate refresh.
6. Lặp lại với cùng version/configuration/dataset và ghi environment.

### 10.1. Ma trận workload

| Workload | Mục tiêu |
| --- | --- |
| Small payload, warm connection | Baseline overhead |
| Large payload/nested XML | Parse, validate, allocation |
| Signature + encryption enabled | WS-Security CPU/key cost |
| Cold connections/TLS handshake | Connection establishment |
| Slow downstream database | Business wait propagation |
| High concurrency | Pool saturation/queueing |
| Error/Fault burst | Exception/resolver/logging overhead |
| Long-running soak | Memory leak, connection leak, stale cert/cache |

### 10.2. Open-loop và closed-loop load

Closed-loop load generator gửi request mới sau khi request trước hoàn tất; khi server chậm, generator tự giảm tốc và có thể che hiện tượng queueing. Open-loop tạo arrival rate độc lập với completion; phù hợp tìm điểm saturation nhưng dễ tạo backlog lớn. Báo rõ mô hình và giới hạn queue để không nhầm kết quả.

### 10.3. Tránh coordinated omission

Nếu load generator không ghi nhận thời gian mà request đáng lẽ đã được gửi trong khi nó đang chờ response, percentile có thể đánh giá thấp tail latency. Chọn tool/configuration có cách xử lý coordinated omission phù hợp. Micrometer mô tả pause detection/compensation cho một số histogram implementations; đó không thay thế thiết kế load generator và test workload đúng. [Micrometer Timers — Pause Detection](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)

## 11. Quy trình điều tra một SOAP operation chậm

Ví dụ `GetOrder` tăng từ p95 400 ms lên 1,6 giây:

**Bước 1 — Xác nhận population và thay đổi.** Xem latency theo operation, partner/transport bounded, outcome và version release; phân biệt một operation bị ảnh hưởng với toàn dịch vụ.

**Bước 2 — So client/server spans.** Nếu caller tăng nhưng server không tăng, tìm connection pool, DNS/TLS, proxy, response read hoặc client unmarshal. Nếu server span tăng, tiếp tục.

**Bước 3 — So lớp XML và security.** Kiểm tra request/response bytes, parse/validation/marshal và WS-Security verification/signature. Quan sát CPU/allocation và lỗi cùng pha.

**Bước 4 — Xem business dependencies.** Mở child spans cho database, remote API, lock và transaction. Kiểm pool pending/query plan/connection wait thay vì chỉ nhìn total database timer.

**Bước 5 — Kiểm saturation và queue.** Thread pool active/queued, HTTP pool pending, JMS age, CPU throttling, GC pause, heap và file descriptors.

**Bước 6 — Tạo giả thuyết và thử có kiểm soát.** Chỉ thay một yếu tố, chạy workload có thể tái hiện, so p95/p99/throughput/errors và kiểm correctness/security.

**Bước 7 — Xác nhận sau triển khai.** So cùng SLI trước/sau, kiểm error budget, rollback threshold và theo dõi ít nhất một chu kỳ tải đại diện.

## 12. Ví dụ cấu trúc metric và trace

Tên metric gợi ý:

~~~text
soap.client.roundtrip
soap.client.marshal
soap.client.transport.acquire
soap.client.transport.connect
soap.client.transport.response
soap.server.processing
soap.server.xml.parse
soap.server.xml.validation
soap.server.jaxb.unmarshal
soap.server.jaxb.marshal
soap.server.security.verify
soap.server.security.sign
soap.server.endpoint
soap.business.database
soap.business.downstream
soap.server.faults
~~~

Không nhất thiết mọi lớp đều có thể đo riêng từ Spring-WS interceptor mặc định. Một số pha nằm sâu trong HTTP client, XML provider hoặc WSS4J; instrument qua extension point phù hợp, wrapper, Observation instrumentation hoặc exporter của thư viện. Nếu chỉ có total timer, ghi tên đúng là total; không đặt nhãn “transport” hoặc “XML” cho thời gian bao gồm cả server.

Tags gợi ý: `operation`, `soap_version`, `transport`, `outcome`, `error_category`, `client_name` (bounded). Attributes của trace có thể chi tiết hơn metric tags, nhưng cũng phải giới hạn dữ liệu nhạy cảm và kích thước.

## 13. Vận hành dashboards và cảnh báo

Dashboard theo operation nên hiển thị cùng hàng:

- Request rate, error/Fault rate và timeout rate.
- p50/p95/p99 latency của caller và server.
- SLO compliance và error budget burn.
- Active/pending HTTP connections và pool acquire wait.
- XML bytes/validation failures và security verify/sign latency.
- Endpoint/business/database/downstream spans.
- CPU throttling, GC pause, heap, worker threads/queue.

Alert nên phản ánh triệu chứng caller hoặc saturation kéo dài, không cảnh báo chỉ vì một request chạm max. Ví dụ: p99 vượt SLO trong vài cửa sổ liên tiếp, pool pending tăng kèm latency, hoặc Fault rate/security rejection vượt baseline. Đặt threshold theo SLO, traffic và error budget của dịch vụ.

## 14. Các lỗi đo lường thường gặp

| Sai lầm | Hệ quả | Cách tránh |
| --- | --- | --- |
| Dùng currentTimeMillis cho duration | Clock adjustment làm số đo méo | nanoTime hoặc Timer |
| Cộng span cha và con | Đếm một thời gian nhiều lần | Exclusive time hoặc xem hierarchy |
| Đo chỉ p50 | Bỏ qua tail latency | p50 + p95/p99 + histogram |
| Gắn request ID vào metric tag | Cardinality bùng nổ | Trace ID trong tracing/log, không metric |
| Đo timer chỉ khi success | Che chậm/error path | Record mọi outcome |
| Timeout cắt request trước khi server ghi xong | Caller/server số liệu khác nhau | Correlate timeout và server spans |
| Dùng mock server để benchmark TLS | Không đo TLS/real transport | Load test HTTP/TLS thật |
| Benchmark không warm-up | Đo class loading/JIT/cold cache | Warm-up và cold-start test riêng |
| Giảm security để tăng throughput | So sánh không đúng production | Giữ policy tương đương |
| Log full SOAP message | Rò PII/secret, tăng I/O | Structured metadata đã lọc |
| Mỗi partner/URL tùy ý thành tag | Cardinality tăng theo dữ liệu | Allowlist bounded tags |
| Chỉ xem server CPU | Bỏ lỡ queue/remote dependency | Trace và pool/queue metrics |

## 15. Bài tập thực hành

1. Bọc một `WebServiceTemplate` call bằng Micrometer Timer; ghi count, total time và p95 histogram.
2. Đo riêng marshal/unmarshal JAXB bằng wrapper quanh marshaller/unmarshaller đã cấu hình.
3. Thêm timer quanh endpoint/business handler; so với caller round-trip và giải thích các khoảng chênh.
4. Bật XSD validation và đo chi phí khi schema đơn giản/phức tạp, payload nhỏ/lớn.
5. Đo WS-Security verify/sign với nhiều cỡ payload và test certificate.
6. Theo dõi pool active/pending/acquire wait; cố tình tạo pool saturation trong lab.
7. Tạo trace cha/con cho SOAP client → SOAP server → database; không cộng span lồng nhau.
8. Cấu hình histogram/SLO bucket cho một operation và dựng dashboard p95/p99.
9. Chạy closed-loop và open-loop load test; so latency tail và backlog.
10. Mô phỏng downstream chậm, xác định phần latency nằm ở queue, dependency hay endpoint.
11. Tạo Fault burst và xác định chi phí logging/exception mapping.
12. Viết runbook điều tra p99 tăng gồm client/server spans, transport, XML, security, business và saturation.

## 16. Checklist triển khai đo lường

| Hạng mục | Điều kiện đạt |
| --- | --- |
| **Boundary** | Định nghĩa caller, transport, server, XML, security và business timing |
| **Clock** | Duration dùng monotonic clock |
| **Metrics** | Timer/histogram theo operation/outcome bounded |
| **Tracing** | Trace context qua transport được hỗ trợ và trust policy rõ |
| **XML** | Parse, validation, JAXB, XSLT/serialization được đo khi có thể |
| **Security** | Verify/decrypt/sign/encrypt và key lookup có ranh giới đo |
| **Business** | DB, downstream, transaction và queue wait tách biệt |
| **Percentiles** | Có p50/p95/p99/histogram và SLO rõ population |
| **Cardinality** | Không tag request ID, payload, fault message hoặc PII |
| **Pool/queue** | Có active, pending, wait, age, timeout và saturation metrics |
| **Load test** | Có warm-up, workload đại diện, concurrency và soak |
| **Privacy** | Không xuất raw SOAP/XML, security token hoặc certificate secret |
| **Runbook** | Có quy trình điều tra từ caller span đến dependency |

## 17. Tài liệu tham khảo

- [Spring-WS Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): client/server architecture, \`WebServiceTemplate\`, message senders, endpoint interceptor và transport configuration.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): timer count/total time, histogram, percentiles, SLO và pause detection.
- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics endpoint và tích hợp Micrometer Observation.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): chuẩn hóa \`traceparent\` và \`tracestate\` để propagate distributed trace context qua HTTP.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): mô hình Observation liên kết metrics và tracing instrumentation.

**Kết luận:** Đo độ trễ SOAP hiệu quả bắt đầu bằng một latency tổng đúng ranh giới caller, sau đó phân rã theo transport, XML/JAXB, WS-Security và nghiệp vụ. Micrometer Timer/histogram cho xu hướng và tail latency; tracing cho request cụ thể; pool/queue/CPU/GC metrics giúp phân biệt chờ tài nguyên với thời gian thực thi. Phải tránh cộng duration của span lồng nhau, giới hạn cardinality, bảo vệ dữ liệu SOAP nhạy cảm và benchmark với cùng security policy/workload production. Khi từng phép đo có boundary rõ, đội vận hành có thể chỉ ra lớp gây p95/p99 tăng và kiểm chứng cải thiện bằng dữ liệu thay vì phỏng đoán.
