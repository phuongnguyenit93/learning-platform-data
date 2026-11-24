# Span error trong distributed tracing: ghi nhận lỗi và diễn giải đúng trạng thái

> **Chương:** Tracing  
> **Bài:** Span error  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Tình huống: HTTP 200 nhưng một span bên trong bị lỗi

Dịch vụ `order-api` xử lý yêu cầu tạo đơn hàng và gọi `inventory-api` để giữ hàng. Khi inventory gặp timeout, `order-api` có thể sử dụng kết quả dự phòng và trả HTTP 200 cho khách hàng, nhưng một thao tác nội bộ thực sự đã thất bại. Nếu chỉ nhìn status code của HTTP response, người trực vận hành có thể bỏ sót vấn đề.

Một trace mẫu:

~~~text
Trace: POST /orders                             210 ms    HTTP 200
└── Span: orders.create                         205 ms    UNSET
    ├── Span: inventory.reserve                 180 ms    ERROR
    │   └── Event: exception (TimeoutException)
    └── Span: orders.fallback                     8 ms    UNSET
~~~

**Span error** giúp đánh dấu **thất bại của một hoạt động được quan sát**, thay vì suy lỗi từ trạng thái cuối của toàn bộ request. Thông thường ta muốn biết:

- Thao tác nào thất bại, vào lúc nào và kéo dài bao lâu?
- Span có trạng thái `ERROR`, có exception event, hay chỉ có một tag nghiệp vụ nói “failed”?
- Vì sao một child span lỗi nhưng parent span vẫn thành công hoặc không có trạng thái lỗi?
- Khi dùng Micrometer Observation trong Spring Boot, lời gọi `observation.error(ex)` được tracing handler xử lý ra sao?
- Vì sao metric báo lỗi nhưng tracing backend không thấy một span lỗi tương ứng?
- Cần ghi thuộc tính, log và context propagation như thế nào để điều tra mà không rò rỉ thông tin?

Bài học tập trung vào **ngữ nghĩa của lỗi trên span**, cách instrument an toàn và cách kiểm chứng qua một hệ thống Spring Boot có Micrometer Observation/Tracing.

## 2. Span, trace và trạng thái lỗi là những khái niệm khác nhau

Trong distributed tracing, một **trace** biểu diễn đường thực thi của một tác vụ xuyên qua nhiều thành phần. Mỗi **span** biểu diễn một hoạt động có mốc bắt đầu/kết thúc, tên, span kind, parent, attributes, events và status.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `traceId` | Kết nối các span thuộc cùng một trace | Một request đi qua ba dịch vụ |
| `spanId` | Định danh một span | Bước gọi inventory cụ thể |
| `parentSpanId` | Mối quan hệ cha–con | Span HTTP client là con của nghiệp vụ order |
| `span.kind` | Vai trò của span | SERVER, CLIENT, INTERNAL, PRODUCER, CONSUMER |
| `span.status` | Trạng thái kết luận của **span này** | UNSET, ERROR hoặc OK |
| `span.attributes` | Metadata mô tả hoạt động | `http.request.method=POST`, `server.address=...` |
| `span.events` | Các sự kiện xảy ra trong thời gian span hoạt động | Event ghi nhận exception |
| `span.duration` | Khoảng thời gian từ start đến end | 180 ms |

Một span không phải một log, và một trace cũng không phải metric Counter. Span cung cấp cấu trúc nguyên nhân–thời gian của một lần thực thi; metric giúp tổng hợp tỷ lệ lỗi/độ trễ trên nhiều lần, còn log bổ sung nội dung sự kiện. Ba tín hiệu có thể được liên kết qua thời gian và trace context nếu cấu hình phù hợp.

**Đừng đồng nhất “trace có lỗi” với “mọi span trong trace đều lỗi”.** Mỗi span có status riêng. Một span có thể lỗi được xử lý ở tầng trên, hoặc parent span có thể thất bại vì logic riêng mà child span hoàn thành bình thường.

## 3. OpenTelemetry Span Status: UNSET, OK và ERROR

Trong OpenTelemetry, trạng thái span thường có ba mã:

| Status code | Ý nghĩa thực tế | Ví dụ |
| --- | --- | --- |
| `UNSET` | Không có trạng thái lỗi/thành công được đặt tường minh; trạng thái mặc định | Một span xử lý bình thường mà SDK/instrumentation không đánh dấu `OK` |
| `OK` | Thành công được đặt tường minh | Một instrumentation thực sự quyết định hoạt động thành công |
| `ERROR` | Hoạt động bị coi là thất bại | Timeout khi gọi dịch vụ phụ thuộc, lỗi kỹ thuật không xử lý được trong phạm vi thao tác |

**`UNSET` không đồng nghĩa “chưa chạy” hoặc “thiếu dữ liệu”.** Nhiều span hoàn tất thành công vẫn giữ `UNSET` vì hệ thống chỉ cần báo rõ những hoạt động thất bại. Khi đọc dashboard, không tính mọi `UNSET` là lỗi.

`ERROR` có thể có một mô tả trạng thái không chứa thông tin nhạy cảm; không nên copy toàn bộ exception message tùy ý vào mô tả. Tùy instrumentation và backend, giao diện có thể hiển thị các trường ở cách khác nhau.

Ví dụ khi dùng OpenTelemetry API trực tiếp:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;

Span span = Span.current();

try {
    callInventory();
} catch (RuntimeException ex) {
    span.recordException(ex);
    span.setStatus(StatusCode.ERROR, "inventory call failed");
    throw ex;
}
~~~

**Điểm quan trọng:** `recordException(ex)` ghi một **event liên quan đến exception**, còn `setStatus(StatusCode.ERROR, ...)` là thao tác đặt **span status**. Trong API OpenTelemetry, không nên giả định chỉ ghi event thì span chắc chắn được đánh dấu `ERROR`. Một instrumentation cấp cao có thể tự thực hiện cả hai, nhưng đó là trách nhiệm của chính instrumentation.

`Span.current()` chỉ hữu ích khi có **span hiện hành** trong context; nếu không có tracing context phù hợp, nó có thể là no-op span. Ngoài ra, chỉ nên gọi API trực tiếp kiểu này khi ứng dụng thực sự dùng OpenTelemetry API và đã chọn ranh giới instrument thích hợp. Không tạo thêm span mới cho đúng hoạt động đã được Micrometer Observation instrument.

## 4. Span status, exception event và outcome tag khác nhau thế nào?

Ba loại dữ liệu thường xuất hiện cạnh nhau nhưng trả lời những câu hỏi khác nhau:

| Dữ liệu | Nằm ở đâu? | Diễn giải |
| --- | --- | --- |
| **Span status** | Trường status của span | Hoạt động có bị kết luận là lỗi theo chính sách instrumentation không? |
| **Exception event** | Danh sách span events | Có một exception cụ thể xảy ra; thường có kiểu lỗi và một số chi tiết đã được kiểm soát |
| **Outcome attribute** | Span attribute hoặc Micrometer low-cardinality key–value | Kết quả nghiệp vụ: `success`, `rejected`, `error` |
| **HTTP status code** | Attribute của HTTP client/server span | Giao thức trả về 200, 404, 500… |
| **Log level** | Bản ghi log | Mức độ ưu tiên/sự kiện trong logging pipeline |

Có thể tồn tại các tổ hợp hợp lệ:

1. Span có `ERROR` và exception event: lỗi kỹ thuật kèm thông tin exception được ghi nhận.
2. Span `ERROR` nhưng không có exception event: một lời gọi HTTP trả trạng thái lỗi hoặc thao tác bị đánh dấu thất bại mà không có exception Java.
3. Span `UNSET` nhưng có exception event: exception được bắt và xử lý phục hồi, hoặc instrumentation ghi event mà không đặt status.
4. Span `UNSET` và `outcome=rejected`: quy tắc nghiệp vụ từ chối hợp lệ, không nhất thiết là lỗi hạ tầng.
5. HTTP 200 nhưng một child span `ERROR`: có cơ chế fallback hoặc xử lý lỗi nội bộ.
6. HTTP 500 nhưng không có exception event: server trả lỗi theo trạng thái mà không ném exception từ code.

Vì vậy **không xác định tình trạng thất bại chỉ bằng sự hiện diện của exception event, log ERROR hay một giá trị HTTP status đơn lẻ**. Phải đối chiếu span kind, semantics của operation và chính sách instrumentation.

## 5. Micrometer Observation.error(ex): đường đi từ lỗi Java đến tracing

Spring Boot thường dùng **Micrometer Observation** làm lớp instrument chung để kết nối metrics và tracing. Khi mã nghiệp vụ phát hiện exception cần báo lỗi cho observation, API thông dụng là:

~~~java
observation.error(ex);
~~~

Về mặt khái niệm, vòng đời có thể diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant App as PaymentService
    participant Obs as Observation
    participant Registry as ObservationRegistry
    participant Handler as Tracing ObservationHandler
    participant Tracer as Tracer/Span
    App->>Obs: createNotStarted(...)
    App->>Obs: start()
    Obs->>Handler: onStart(context)
    Handler->>Tracer: tạo/bắt đầu span khi được cấu hình
    App->>Obs: openScope()
    Note over App: thao tác nghiệp vụ ném exception
    App->>Obs: error(exception)
    Obs->>Handler: onError(context)
    Handler->>Tracer: ghi lỗi trên span theo bridge/handler
    App->>Obs: closeScope()
    App->>Obs: stop()
    Obs->>Handler: onStop(context)
    Handler->>Tracer: kết thúc span
~~~

Các điểm cần phân biệt:

- `observation.error(ex)` **thông báo exception cho Observation** để handlers nhận callback tương ứng và truy cập lỗi trong context. Nó không tự ghi log ứng dụng.
- Một **Tracing ObservationHandler** phù hợp có thể ghi exception và/hoặc đánh dấu lỗi cho span qua bridge Micrometer Tracing–OpenTelemetry/Brave. Hành vi chi tiết và thuộc tính xuất ra cần xác minh theo phiên bản, handler và exporter.
- Một **Meter ObservationHandler** có thể dùng metadata/outcome để tạo Time series phù hợp; chỉ gọi `error(ex)` không đồng nghĩa mọi Timer tự động có tag `outcome=error` theo hợp đồng nghiệp vụ của bạn.
- `observation.stop()` vẫn cần được gọi để kết thúc phép quan sát. Lỗi xảy ra mà không stop có thể khiến phép đo duration/span không hoàn tất đúng.
- `openScope()` thiết lập ngữ cảnh hiện hành cho thread/chuỗi thực thi liên quan; không phải điều kiện tự động để mọi exception được bắt và truyền qua toàn bộ hệ thống.

Nếu một framework đã tự instrument và đã ghi exception trên cùng observation, việc tự ghi lỗi lần nữa có thể tạo event trùng. Cần xác định ai sở hữu instrumentation ở ranh giới này.

## 6. Mẫu code Spring Boot: instrument lỗi kỹ thuật một lần

Tình huống: dịch vụ ủy quyền thanh toán đo một lần gọi `payments.authorize`. Một exception từ gateway là **lỗi kỹ thuật**; một quyết định từ chối thanh toán có thể là **kết quả nghiệp vụ dự kiến**.

~~~java
package example.payment;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.function.Supplier;
import org.springframework.stereotype.Service;

@Service
public class PaymentAuthorizationService {
    private final ObservationRegistry observationRegistry;

    public PaymentAuthorizationService(
            ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public <T> T authorize(String incomingChannel, Supplier<T> operation) {
        Observation observation = Observation.createNotStarted(
                "payments.authorize", observationRegistry)
            .contextualName("authorize payment")
            .lowCardinalityKeyValue(
                "channel", normalizeChannel(incomingChannel))
            .start();

        try (Observation.Scope scope = observation.openScope()) {
            T result = operation.get();
            observation.lowCardinalityKeyValue("outcome", "success");
            return result;
        } catch (BusinessDeclinedException ex) {
            // Từ chối dự kiến: phân loại nghiệp vụ, không tự coi là
            // lỗi hệ thống của span này.
            observation.lowCardinalityKeyValue("outcome", "declined");
            throw ex;
        } catch (RuntimeException ex) {
            observation.lowCardinalityKeyValue("outcome", "error");
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }

    private static String normalizeChannel(String input) {
        if ("web".equals(input)) return "web";
        if ("mobile".equals(input)) return "mobile";
        if ("partner".equals(input)) return "partner";
        return "other";
    }

    public static final class BusinessDeclinedException
            extends RuntimeException {
        public BusinessDeclinedException(String message) {
            super(message);
        }
    }
}
~~~

Trong ví dụ:

- `payments.authorize` là **tên observation nghiệp vụ**, không phải metric HTTP server.
- `outcome=success/declined/error` là low-cardinality metadata cho phân nhóm metrics; không dùng exception message, user ID hoặc order ID làm metric tag.
- Khi lỗi kỹ thuật, `observation.error(ex)` thông báo lỗi để tracing handler xử lý; `throw ex` giữ nguyên luồng ngoại lệ của ứng dụng.
- `finally` bảo đảm `stop()`, và `try-with-resources` đóng scope trên nhánh thành công/lỗi.
- Với từ chối nghiệp vụ, đoạn mã chỉ gắn `outcome=declined`. Nó **không tự** đánh dấu business span là `ERROR`; đây là lựa chọn chính sách, cần được thống nhất với yêu cầu thực tế.
- Nếu `BusinessDeclinedException` được ném ra ngoài controller và biến thành HTTP 500, instrumentation HTTP server ở tầng ngoài vẫn có thể đánh dấu **server span** là lỗi. Hãy ánh xạ từ chối dự kiến thành response phù hợp (ví dụ HTTP 409/422 tùy hợp đồng API) để giữ semantics nhất quán.

Đây là ví dụ **đồng bộ**. Với futures hoặc Reactor, phải kiểm tra thời điểm lỗi xảy ra thực tế và cách propagation ngữ cảnh, không gọi `stop()` ngay sau khi chỉ submit công việc.

### 6.1. Tại sao không đặt “error” ngay khi bắt đầu?

Không thể biết một thao tác thành công hay thất bại từ trước khi chạy. Viết `outcome=error` lúc `start()` rồi không thay đổi sẽ làm mọi lần đo đều bị gắn lỗi. Khi có kết quả, hãy gắn outcome **trước `stop()`**. Trong một số handler, metadata đọc ở `onStart` khác metadata đọc ở `onStop`; nếu một attribute bắt buộc phải có từ đầu, chỉ gắn những giá trị đã biết trước, không đoán outcome.

## 7. Cấu hình Spring Boot để nhận được span error trên backend

Ví dụ dưới dành cho hệ Spring Boot 3.x dùng Micrometer Tracing bridge tới OpenTelemetry. Bộ dependency và property cụ thể có thể khác theo minor version, backend và lựa chọn exporter của dự án.

### 7.1. Maven dependencies minh họa

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
</dependencies>
~~~

Khi dự án dùng Spring Boot BOM/parent tương thích, phiên bản của các dependency thường được quản lý. Chỉ thêm Actuator không mặc nhiên bảo đảm một trace được gửi tới Collector: cần tracing bridge, SDK/exporter phù hợp và endpoint đích.

### 7.2. application.yml cho môi trường học tập

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

- `management.tracing.sampling.probability=1.0` minh họa việc giữ gần như mọi trace trong môi trường test để dễ quan sát. **Không mặc định dùng 100% sampling ở production** khi chưa đánh giá traffic, giá trị dữ liệu và chi phí.
- `management.otlp.tracing.endpoint` là điểm đến OTLP traces theo cấu hình minh họa của Spring Boot 3.x. Kiểm tra namespace và cấu hình thực tế của phiên bản đang chạy.
- Trong Docker/Kubernetes, `localhost` trỏ tới môi trường mạng hiện tại. Nếu Collector là service khác, dùng hostname/địa chỉ truy cập đúng của môi trường triển khai.
- `/actuator/metrics` là endpoint metrics, **không phải endpoint xem trace**. Trace thường được tìm trong hệ thống nhận OTLP như Jaeger/Tempo hoặc backend thương mại tương ứng.

Nếu ứng dụng dùng Brave bridge hoặc exporter khác, cách export và propagation có thể khác. Mục đích bài này là **hiểu span error**, không buộc mọi hệ thống phải dùng một backend cố định.

## 8. HTTP status và span error: không được ánh xạ máy móc

HTTP status cho biết kết quả giao thức; span status cho biết lỗi của hoạt động được quan sát theo quy tắc instrumentation. Quy tắc có thể phụ thuộc **span kind** và semantic conventions.

| Tình huống | HTTP status | Cách nhìn thường hợp lý | Lưu ý |
| --- | --- | --- | --- |
| Server xử lý thành công | 200/201/204 | Server span thường không lỗi | Không cần tự đặt `OK` cho mọi lần gọi |
| Client gửi request không hợp lệ | 400 | Server có thể coi là phản hồi dự kiến, không phải lỗi nội bộ | Client span có thể đánh giá khác tùy semantic conventions |
| Resource không tồn tại | 404 | Có thể là kết quả nghiệp vụ hoặc lỗi phía client | Xem hợp đồng endpoint và loại span |
| Server lỗi không xử lý được | 500/503 | Server span thường được đánh dấu `ERROR` | Có thể không có exception event |
| Gateway timeout | 504 hoặc exception ở client | Client span có thể `ERROR` | Kiểm tra timeout, retry, propagation |
| HTTP 200 nhờ fallback sau lỗi downstream | 200 | Server span có thể không lỗi, child span có thể `ERROR` | Không tự suy toàn trace thành công hoàn toàn |
| Business rejection được ánh xạ thành 409/422 | 409/422 | Có thể là kết quả nghiệp vụ dự kiến | Phân biệt `outcome=declined` với lỗi kỹ thuật |

OpenTelemetry HTTP semantic conventions có quy tắc và phiên bản riêng về đánh dấu status cho client/server spans. Một hướng dẫn chung là: **server-side 5xx thường là lỗi**, còn **4xx trên server không được mặc định đánh đồng với lỗi nội bộ**; việc phân loại ở client có thể khác. Vì vậy hãy đối chiếu instrumentation và semantic conventions đang dùng thay vì tự đặt `ERROR` cho mọi status từ 400 trở lên.

### 8.1. Một lỗi nghiệp vụ có bắt buộc là span error không?

Không. Một thao tác “kiểm tra hạn mức” trả `insufficient_funds` có thể hoạt động **đúng hợp đồng** dù yêu cầu thanh toán không được chấp thuận. Nếu mục tiêu vận hành là theo dõi tỷ lệ từ chối, gắn một tag hữu hạn như `outcome=declined` thường hữu ích hơn việc coi tất cả từ chối là lỗi hệ thống.

Tuy nhiên, nếu một bước được định nghĩa là “thực hiện một yêu cầu thanh toán thành công” thì trạng thái không đạt mục tiêu có thể được phân loại lỗi theo hợp đồng khác. **Quy tắc phải nhất quán**, được document và phù hợp với dashboard/SLO; không nên mỗi service tự suy theo tên exception.

## 9. Parent và child span: lỗi không tự lan truyền trạng thái

Hãy xét đường đi ba dịch vụ:

~~~mermaid
flowchart TD
    A["order-api: HTTP SERVER, UNSET"] --> B["orders.create: INTERNAL, UNSET"]
    B --> C["inventory-api call: CLIENT, ERROR"]
    C --> D["inventory-api: HTTP SERVER, ERROR"]
    B --> E["fallback: INTERNAL, UNSET"]
    E --> F["order-api trả kết quả dự phòng"]
~~~

Trong một trace được propagate đúng, các span liên kết nhờ trace context như `traceparent`, cùng trace ID và các quan hệ parent–child. Nhưng:

- **Status không phải trường “kế thừa tự động”** từ child sang parent. Child span lỗi không buộc parent span phải có `ERROR`.
- Một parent có thể **phục hồi lỗi** và hoàn tất bình thường; giữ `UNSET`/OK ở parent là hợp lý khi hợp đồng công việc đạt yêu cầu.
- Ngược lại, parent có thể `ERROR` do business invariant bị phá vỡ dù mọi lời gọi phụ trợ riêng lẻ thành công.
- Span ở service downstream có thể có status khác client span vì chúng quan sát **hai phía của cùng cuộc trao đổi**, theo instrumentation và ngữ nghĩa của từng phía.
- Mất trace context khiến các span thành những trace rời rạc; đây là lỗi **propagation**, không nhất thiết lỗi đánh dấu status.

Khi điều tra, nên xem **toàn bộ waterfall** và vị trí span `ERROR` thay vì chỉ nhìn biểu tượng lỗi ở root trace hoặc đếm số span đỏ.

## 10. Exception event: nội dung nào nên ghi?

Một exception event có thể mang các trường mô tả như kiểu exception, message, stack trace hoặc những metadata khác tùy tracing SDK, semantic conventions và cấu hình instrumentation. Không phải backend nào cũng hiển thị đầy đủ các trường, và không phải mọi loại lỗi đều có stack trace Java.

Ví dụ một sự kiện:

~~~text
span: inventory.reserve
status: ERROR
event.name: exception
exception.type: java.util.concurrent.TimeoutException
exception.message: downstream call timed out
event.time: 2026-11-22T...
~~~

Đây là ví dụ **minh họa cấu trúc**, không phải lược đồ JSON bắt buộc hay đầu ra chắc chắn của mọi exporter.

### Nguyên tắc an toàn

- Không gửi access token, session cookie, số thẻ, mật khẩu, khóa bí mật hoặc nguyên payload request/response vào span attributes/events.
- Không tự động gắn exception message đầy đủ thành **low-cardinality metrics tag**: message có thể khác từng request, gây bùng nổ series và rò rỉ dữ liệu.
- Khi cần phân nhóm lỗi, dùng loại lỗi hữu hạn như `error.type=timeout`, `outcome=error` hoặc tên exception đã chuẩn hóa và được phép công bố.
- Nếu cần stack trace, dùng mức lấy mẫu và retention phù hợp; stack trace có thể dài và chứa chi tiết nội bộ.
- Không đặt ID từng đơn hàng hoặc request ID vào metric label. Định danh kỹ thuật có thể nằm trong log/trace attribute theo chính sách bảo mật khi cần truy vấn.
- Hạn chế ghi cùng exception ở nhiều span khi không có lý do: một exception đi xuyên các lớp có thể sinh nhiều events/log records, tạo nhiễu và tăng chi phí.

**Quan trọng:** mục tiêu là để người điều tra hiểu điều gì thất bại, không phải thu thập toàn bộ dữ liệu của từng exception một cách không kiểm soát.

## 11. Tại sao có status ERROR mà không có exception event?

Có nhiều trường hợp hoàn toàn bình thường:

1. **Lỗi ở tầng giao thức:** HTTP client nhận 503 hoặc gRPC trả status lỗi, nhưng không nhất thiết có exception Java được ném tại ranh giới instrument.
2. **Hệ thống tự đặt trạng thái:** code gọi `setStatus(ERROR)` vì một điều kiện thất bại, nhưng không gọi `recordException`.
3. **Instrumentation chỉ ghi một phần thông tin:** bridge/handler/backend có thể biểu diễn lỗi bằng status và attributes mà không tạo exception event.
4. **Một số sự kiện bị lọc hoặc giới hạn:** trace SDK/backend có giới hạn event count/size, hoặc pipeline lọc metadata.
5. **Span được tạo từ tầng ngoài:** framework đánh dấu HTTP server span lỗi khi trả HTTP 500, dù exception nội bộ đã bị chuyển thành response.

Và chiều ngược lại: có event exception không nhất thiết status `ERROR`. Ví dụ một exception được catch rồi retry thành công; instrumentation có thể ghi event của lần thử lỗi trên một span nhưng giữ kết quả cuối phù hợp với hợp đồng của span đó.

**Cách kiểm tra:** tìm status code, exception events, `http.response.status_code` (hoặc attribute tương ứng với semantic conventions đang dùng), span kind và tên operation. Không dùng duy nhất một dấu hiệu để suy luận gốc rễ.

## 12. Chẩn đoán qua metrics, logs và traces

Trong ứng dụng Spring Boot, ba tín hiệu có những vai trò khác nhau:

~~~mermaid
flowchart LR
    A["Metrics: 5xx rate, latency tăng"] --> B["Chọn service / route / thời gian"]
    B --> C["Traces: các span ERROR và child spans"]
    C --> D["Logs: traceId/spanId, exception"]
    C --> E["Span attributes: dependency, HTTP status"]
    D --> F["Giả thuyết gốc lỗi"]
    E --> F
    F --> G["Khắc phục và xác nhận trên metrics"]
~~~

### 12.1. Metrics: phát hiện và định lượng

Ví dụ Timer HTTP server xuất ra Prometheus với tên series phổ biến `http_server_requests_seconds_count`. Nếu có tag `outcome=SERVER_ERROR` và nó đúng với dữ liệu thực, truy vấn minh họa tỷ lệ lỗi:

~~~promql
sum(rate(http_server_requests_seconds_count{
  outcome="SERVER_ERROR"
}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
~~~

Kết quả là một tỷ lệ 0–1 khi mẫu số dương. Đây là **HTTP server error rate theo convention**, không tự đồng nghĩa tỷ lệ những span có status `ERROR`, cũng không gồm mọi lỗi đã được fallback thành 200.

Để đo lỗi nghiệp vụ, tạo metric có semantics rõ ràng, chẳng hạn `payments.authorize` với `outcome=error/declined/success`. Đừng giả định `observation.error(ex)` sẽ tự thiết lập một bộ labels theo đúng SLI của bạn.

### 12.2. Logs: chứng cứ chi tiết

Khi tracing integration và logging pattern/MDC được cấu hình, log có thể chứa `traceId` và `spanId`. Ví dụ minh họa:

~~~text
WARN [traceId=8b... spanId=7f...] Inventory timeout after 180 ms
~~~

Log không tự được sinh chỉ vì span có status `ERROR`. Một handler có thể ghi exception event nhưng không log; ngược lại ứng dụng có thể log một lỗi nhưng không báo lỗi cho Observation. Giữ log correlation nhất quán giúp liên kết hai tín hiệu.

### 12.3. Traces: nơi thất bại và đường lan truyền

Mở một trace đã được sample/export, tìm span `ERROR` xuất hiện **sớm nhất theo đường đi có liên quan**, xem các call spans phía trước và phía sau, exception event, deadline/timeout, retry và fallback. “Span lỗi sớm nhất” không luôn là root cause, nhưng là điểm khởi đầu hợp lý để lập giả thuyết.

Ví dụ một request có hai lần retry, một lần lỗi và lần cuối thành công: có thể có hai client spans (một `ERROR`, một `UNSET`), trong khi parent nghiệp vụ thành công. **Đếm số span lỗi không bằng số request lỗi** trong tình huống có retry.

## 13. Sampling, exporter và vì sao trace có lỗi có thể không xuất hiện

Một pipeline điển hình:

~~~text
Observation / instrumentation
  → Tracing ObservationHandler
  → Tracer + Span
  → Sampling decision
  → Span processor / exporter
  → OTLP Collector
  → Tracing backend
  → Search / UI / retention
~~~

Một số nguyên nhân khiến bạn không thấy span lỗi:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Metrics có lỗi nhưng tracing UI không có trace tương ứng | Head sampling không chọn trace; khác pipeline dữ liệu | Kiểm tra sampling probability và tracing backend |
| Trace có root span nhưng thiếu child client span | HTTP client chưa instrument, context bị mất, instrumentation khác | Kiểm tra builder/client, propagation và span kind |
| Trace tồn tại nhưng span status không là ERROR | Không gọi `error(ex)`, handler không ghi error, hoặc policy phân loại khác | Kiểm tra Observation lifecycle và mapper status |
| Span ERROR có trong SDK nhưng không có backend | Exporter, Collector, filter, retention hoặc ingest lỗi | Kiểm tra telemetry của exporter/Collector |
| Một số spans có exception event nhưng thiếu status ERROR | Ghi event nhưng không đặt status theo chính sách | Đối chiếu API và tracing bridge |
| Parent và child là hai trace khác nhau | Mất hoặc không inject/extract trace context | Kiểm tra headers và current span |
| Span bị ngắn bất thường | Stop/end quá sớm ở luồng async | Đo lúc công việc thực sự hoàn tất |
| Logs thiếu traceId/spanId | MDC/pattern chưa cấu hình hoặc mất context khi chuyển thread | Kiểm tra logging correlation và propagation |

**Head sampling** thường đưa ra quyết định sớm, trước khi toàn bộ request hoàn tất. Vì vậy **không thể mặc định rằng một span trở thành `ERROR` thì sẽ được giữ lại**, nếu trace ban đầu đã không được sample. Tail sampling ở collector có thể cân nhắc trạng thái/error sau khi nhận spans, nhưng vẫn có giới hạn tài nguyên, điều kiện thời gian và phụ thuộc cấu hình.

Không tự đặt sampling xác suất 100% ở production chỉ để tìm một lỗi. Khi cần điều tra, dùng môi trường tái hiện, thời gian quan sát có kiểm soát hoặc sampling policy đã được thiết kế; kết hợp metrics/logs để không bỏ sót tỷ lệ lỗi tổng thể.

## 14. Xử lý bất đồng bộ: lỗi xảy ra sau khi method trả về

Trong code đồng bộ, `try/catch/finally` bao quanh một thao tác là đủ để báo lỗi và stop Observation. Trong code bất đồng bộ, có thể xảy ra tình huống:

~~~java
Observation observation = Observation.createNotStarted(
        "inventory.reserve.async", registry).start();

try {
    return executor.submit(() -> reserveInventory());
} finally {
    observation.stop(); // Quá sớm nếu cần đo tới lúc task thực sự kết thúc.
}
~~~

Mẫu này dừng Observation khi submit xong, không phải khi `reserveInventory()` hoàn tất. Exception phát sinh ở worker thread sau đó không được báo cho Observation theo cách mong muốn; span có thể kết thúc trước khi lỗi xảy ra.

Một phương án minh họa với `CompletionStage`:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.CompletionStage;
import java.util.function.Supplier;

public final class AsyncObservationMonitor {
    private final ObservationRegistry registry;

    public AsyncObservationMonitor(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> CompletionStage<T> monitor(
            Supplier<CompletionStage<T>> submit) {

        Observation observation = Observation.createNotStarted(
                "inventory.reserve.async", registry).start();

        try {
            CompletionStage<T> stage = submit.get();
            return stage.whenComplete((result, error) -> {
                try {
                    if (error != null) {
                        observation.error(error);
                        observation.lowCardinalityKeyValue(
                                "outcome", "error");
                    } else {
                        observation.lowCardinalityKeyValue(
                                "outcome", "success");
                    }
                } finally {
                    observation.stop();
                }
            });
        } catch (RuntimeException | Error ex) {
            observation.error(ex);
            observation.stop();
            throw ex;
        }
    }
}
~~~

Trong ví dụ, `error` ở callback có thể là wrapper của exception gốc (chẳng hạn `CompletionException`). Nếu ứng dụng cần phân loại theo root cause, hãy xử lý unwrap an toàn và nhất quán. Quan trọng hơn, callback kết thúc observation sau khi stage hoàn tất.

**Cảnh báo về context propagation:** ví dụ chỉ trình bày **vòng đời báo lỗi và stop**; nó **chưa tự bảo đảm current observation/trace scope đi tới worker thread**. Khi dùng executor hoặc Reactor, cần cơ chế context propagation phù hợp (ví dụ context snapshot hoặc hỗ trợ tích hợp của Spring) nếu muốn downstream spans trở thành con đúng của trace. Không mở một `Observation.Scope` trên thread A rồi cố đóng nó trên thread B.

## 15. Những lỗi thiết kế thường gặp khi ghi span error

| Anti-pattern | Vì sao có vấn đề? | Hướng thay thế |
| --- | --- | --- |
| Ghi `status=ERROR` cho mọi HTTP 4xx trên server | Nhiều 4xx là kết quả hợp lệ theo hợp đồng API | Tôn trọng semantic conventions, phân loại lỗi kỹ thuật và business |
| Chỉ gọi `recordException` rồi mặc định status luôn là `ERROR` | Exception event và span status là hai trường khác nhau | Đặt status tường minh nếu dùng OTel API trực tiếp và cần ERROR |
| Chỉ gọi `log.error(...)` rồi mong có exception event trên span | Logging và tracing là pipeline riêng | Báo lỗi cho Observation hoặc instrument span đúng cách |
| Đặt `outcome=error` nhưng không báo exception cho Observation | Metrics có thể phân loại được nhưng trace thiếu ngữ nghĩa lỗi | Gọi `observation.error(ex)` cho lỗi kỹ thuật phù hợp |
| Gọi `error(ex)` nhưng không `stop()` | Span/Timer có thể không kết thúc đúng | Luôn stop ở đúng ranh giới, dùng `finally`/callback |
| Ghi error ở parent lẫn mọi child vô điều kiện | Tạo nhiễu và đếm số lỗi trùng | Đánh dấu từng hoạt động theo semantics riêng |
| Gắn exception message, URL chứa ID, userId làm metric label | Cardinality cao, rủi ro lộ dữ liệu | Dùng low-cardinality outcome/type, giữ chi tiết trong logs/traces phù hợp |
| Tạo một span thủ công bọc cùng HTTP request đã auto-instrument | Có thể tạo span trùng, khó giải thích waterfall | Dùng instrumentation có sẵn; custom chỉ cho bước nghiệp vụ mới |
| Dừng observation trước khi callback async báo lỗi | Không phản ánh thời gian và lỗi thật | Dừng khi công việc hoàn tất |
| Coi trace vắng mặt là không có lỗi | Sampling/exporter có thể bỏ trace | Đối chiếu metrics, logs và pipeline |
| Coi HTTP 200 là không có downstream error | Fallback/retry có thể che lỗi nội bộ | Xem child spans và metrics downstream |

Nếu hệ thống có custom `ObservationHandler`, nên để `supportsContext` chọn đúng loại context và tránh đăng ký handler hai lần vào registry. Hai tracing handlers làm cùng trách nhiệm trên một observation có thể tạo span hoặc error events trùng; đây là vấn đề khác với hai lần retry thật.

## 16. Tình huống điều tra: timeout inventory làm checkout chậm

**Bối cảnh.** Sau khi thay đổi cấu hình HTTP client, `order-api` xuất hiện p95 latency tăng từ 180 ms lên 950 ms, tỷ lệ HTTP 5xx chỉ tăng nhẹ, nhưng logs có nhiều timeout tới `inventory-api`.

### Bước 1 — khoanh vùng bằng metrics

Trên dashboard, lọc theo route `POST /api/orders`, instance, response status và khoảng thời gian bắt đầu lỗi. Kiểm tra RPS, error rate, p95 latency và một metric nghiệp vụ cho kết quả `outcome=success/fallback/error` nếu ứng dụng đã instrument.

Không suy từ việc chỉ 1% HTTP 5xx rằng chỉ 1% lần gọi inventory thất bại: fallback có thể trả 200 cho nhiều request.

### Bước 2 — xem trace được sample

Một trace có thể như sau:

~~~text
POST /api/orders (SERVER)      820 ms  UNSET    response=200
  orders.create (INTERNAL)     800 ms  UNSET    outcome=fallback
    inventory.reserve (CLIENT) 700 ms  ERROR    timeout
    orders.fallback (INTERNAL)  40 ms  UNSET
~~~

Child span `inventory.reserve` có status `ERROR` dù parent trả thành công. Xem exception event có thể cho thấy `TimeoutException`. Dù vậy, **chưa chắc inventory server xử lý request rồi trả lỗi**: timeout có thể xảy ra trước khi kết nối, trong lúc chờ phản hồi hoặc vì network. Cần đối chiếu logs của client, trace propagation và metrics phía inventory.

### Bước 3 — kiểm tra API tracing và instrumentation

- Có dùng HTTP client đã được Spring Boot cấu hình/instrument đúng không?
- Span client có mang thông tin method, URL route/peer an toàn và status/exception không?
- Nếu lỗi được bắt rồi fallback, instrumentation ở client có báo error trước khi xử lý không?
- Có tạo Observation thủ công khác bọc cùng client HTTP call và gây span trùng không?
- Trace context có được truyền sang `inventory-api` qua headers khi request thực sự tới được server không?
- Sampling/exporter có bỏ một số trace không? Có thể dựa vào metrics để biết tỷ lệ lỗi tổng.

### Bước 4 — khắc phục và xác nhận

Điều chỉnh timeout, connection pool hoặc logic retry theo nguyên nhân đã kiểm chứng. Sau đó theo dõi:

- Tỷ lệ timeout của HTTP client giảm?
- p95 latency của checkout cải thiện?
- Số lần fallback và 5xx trở về ngưỡng chấp nhận?
- Trace mẫu còn child spans `ERROR` bất thường không?
- Logs có cùng trace IDs, events đúng, không lộ token hay dữ liệu nhạy cảm?

**Bài học:** span error nói **hoạt động nào** thất bại và ở đâu trong đường đi; tỷ lệ lỗi thực tế phải được lượng hóa bằng metrics. Một trace riêng không chứng minh ảnh hưởng toàn hệ thống.

## 17. Thực hành và câu hỏi tự kiểm tra

### Bài tập A — phân loại trạng thái

Cho các trường hợp sau, hãy quyết định liệu span tương ứng thường nên `ERROR`, `UNSET` hay cần xem hợp đồng:

1. HTTP server trả 200 khi gọi thanh toán thành công.
2. HTTP server trả 404 cho tài nguyên không tồn tại, đây là kết quả dự kiến.
3. HTTP client bị `SocketTimeoutException`.
4. Một bước nghiệp vụ phát hiện thanh toán bị từ chối hợp lệ.
5. Child span gọi downstream bị lỗi nhưng parent xử lý fallback thành công.
6. Một exception bị bắt và retry thành công trong một thao tác.

**Gợi ý:** không áp một mã duy nhất cho cả trace; xem span kind, ranh giới công việc và ý nghĩa thất bại. `UNSET` có thể là trạng thái hợp lý khi hoạt động hoàn tất bình thường mà không cần đặt `OK` tường minh.

### Bài tập B — instrument bằng Micrometer Observation

Tạo một `InventoryService` với method `reserve(...)`:

- Sử dụng `ObservationRegistry` được Spring Boot inject.
- Tạo observation `inventory.reserve` và gắn `channel` low-cardinality.
- Khi thành công, gắn `outcome=success`.
- Khi timeout, gắn `outcome=error`, gọi `observation.error(ex)` rồi ném lại lỗi.
- Đóng scope và gọi `stop()` trên mọi đường thực thi.
- Giải thích vì sao không đặt ID đơn hàng thành metrics tag.

### Bài tập C — phân biệt event và status

Với một đoạn code OpenTelemetry trực tiếp, thực hiện cả `span.recordException(ex)` và `span.setStatus(StatusCode.ERROR, "dependency failed")`. Sau đó giải thích giá trị độc lập của mỗi thao tác; không giả định `recordException` luôn đặt status.

### Bài tập D — cấu hình và xác nhận trace

Trong môi trường thử nghiệm có tracing bridge/exporter hoạt động:

1. Tạo một yêu cầu thành công và một yêu cầu có lỗi kỹ thuật.
2. Tìm hai trace trong backend khi sampling cho phép.
3. Kiểm tra span name, span kind, status, exception event và thời lượng.
4. Xem `traceId/spanId` có xuất hiện trong logs khi logging correlation được cấu hình.
5. So sánh HTTP server span với client/downstream spans; giải thích khi status khác nhau.
6. Giảm sampling ở môi trường test và giải thích vì sao một số trace biến mất trong khi metrics vẫn đếm requests.

### Bài tập E — phát hiện lỗi async

Một method tạo Observation, submit `CompletableFuture` rồi gọi `observation.stop()` ngay. Hãy chỉnh lại để lỗi và stop xảy ra khi future hoàn tất. Giải thích context propagation cần bổ sung gì khi callback chạy trên thread khác.

### Câu hỏi tự kiểm tra

1. `UNSET` trong OpenTelemetry có phải là lỗi không? Có phải span chưa kết thúc không?
2. Span status `ERROR` khác exception event ở điểm nào?
3. Trong Micrometer, `observation.error(ex)` có tự động viết một log `ERROR` không?
4. Vì sao một parent span có thể không lỗi dù child span `ERROR`?
5. Tại sao mọi HTTP 4xx trên server không nên bị mặc định xem như lỗi hạ tầng?
6. Nếu span `ERROR` vắng mặt trên backend, cần kiểm tra sampling/exporter ở đâu?
7. Vì sao exception message hoặc ID riêng không nên là metric label?
8. Khi một retry thất bại rồi lần tiếp theo thành công, số span lỗi có đồng nghĩa số request lỗi không?
9. Khi nào lỗi cần được đánh dấu ở client span, khi nào ở server span?
10. Lỗi xảy ra sau khi Future được trả về: vì sao `finally { observation.stop(); }` của method submit có thể quá sớm?

**Tiêu chí hoàn thành:** mô tả đúng status codes, phân biệt span error với exception event và outcome; tự instrument một lỗi kỹ thuật bằng Observation, đóng lifecycle đúng; hiểu HTTP/server/client semantics, propagation, sampling và exporter; biết dùng metrics/logs để xác định tác động của span error và xử lý metadata an toàn.

## 18. Ghi nhớ

- **Span status** phản ánh kết luận về **một hoạt động**. `UNSET` thường là mặc định; `ERROR` biểu thị hoạt động bị coi là lỗi; `OK` là thành công tường minh.
- **Exception event không thay thế status.** Khi dùng OpenTelemetry API trực tiếp và cần hai thông tin, ghi exception event và đặt `ERROR` có chủ đích.
- Trong Micrometer, dùng `observation.error(ex)` khi cần báo lỗi cho handlers, và **luôn stop observation** ở thời điểm công việc thật sự kết thúc.
- Lỗi nghiệp vụ được dự kiến có thể cần `outcome=declined` thay vì đánh dấu mọi span `ERROR`. Quy tắc phải nhất quán và tách khỏi định nghĩa HTTP 5xx.
- **Child span lỗi không tự làm parent span lỗi.** Phân tích waterfall, retry, fallback và trace context trước khi suy gốc sự cố.
- Metrics đo tỷ lệ lỗi và tác động tổng thể; logs mô tả sự kiện; traces định vị bước lỗi. Sampling/exporter/propagation có thể khiến một trace không hiển thị.
- Giữ metadata an toàn: tags metrics có cardinality thấp; không ghi token, payload nhạy cảm hoặc exception message tự do vào metric labels.
- Với tác vụ async, truyền ngữ cảnh và đánh dấu error/stop ở callback hoàn tất; đừng dừng span ngay sau khi submit.

## Tài liệu tham khảo

- [Micrometer Reference — Observation introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer Reference — Observation components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OpenTelemetry Specification — Traces API](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [OpenTelemetry Specification — HTTP spans semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-spans/)
- [OpenTelemetry Java — Record exceptions](https://opentelemetry.io/docs/languages/java/api/#record-exceptions)

