# High-cardinality key value trong Micrometer Observation

> **Chương:** Cardinality và metadata  
> **Bài:** High-cardinality key value  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Tình huống mở đầu: từ biểu đồ lỗi đến một lần xử lý cụ thể

Hãy xét dịch vụ Spring Boot có API giữ hàng `POST /api/reservations`. Sau khi triển khai phiên bản mới, tỷ lệ lỗi tăng từ 0,2% lên 3% và p95 latency tăng từ 150 ms lên 900 ms. Dashboard metrics cho biết lỗi đang xảy ra trên toàn dịch vụ, nhưng người trực vận hành muốn biết **lần giữ hàng nào** gặp lỗi, request đó đi qua các dịch vụ nào và bước nào bị chậm.

Ta thường cần hai cấp metadata khác nhau:

- **Low-cardinality key–value** phân nhóm nhiều yêu cầu theo các chiều hữu hạn, chẳng hạn `operation=reserve`, `channel=web`, `outcome=error`. Đây là dữ liệu phù hợp cho metrics tags.
- **High-cardinality key–value** định vị một sự kiện hoặc thực thể cụ thể, chẳng hạn `reservation.attempt_id=4d8b...`. Số giá trị khác nhau có thể lớn đến mức mỗi request mang một giá trị riêng. Thông tin này thích hợp hơn cho một span được chọn để điều tra, khi chính sách dữ liệu cho phép.

Trong Micrometer Observation, API là:

~~~java
observation.highCardinalityKeyValue("reservation.attempt_id", attemptId);
~~~

Lệnh trên bổ sung một cặp key–value vào **context của observation**. Nó không trực tiếp xuất metrics, logs hay traces. Để giá trị xuất hiện trên span, cần tracing handler và pipeline tracing được cấu hình phù hợp. Nếu trace không được lấy mẫu hoặc không được xuất, bạn có thể không tìm thấy giá trị này trên backend dù mã đã gắn thành công.

**Mục tiêu của bài:** biết khi nào dùng high-cardinality key–value, gắn nó đúng cách vào Observation trong Spring Boot, đọc được tác dụng và giới hạn của nó với metrics/traces/logs, và tránh các sai lầm gây bùng nổ dữ liệu hoặc lộ thông tin nhạy cảm.

## 2. Cardinality là gì? Vì sao “high” không đồng nghĩa “quan trọng”?

**Cardinality** là số lượng giá trị phân biệt có thể xuất hiện cho một key trong tập dữ liệu quan sát. Ví dụ:

| Key–value ví dụ | Quy mô giá trị có thể có | Phân loại thường gặp | Mục đích |
| --- | --- | --- | --- |
| `http.method=GET` hoặc `POST` | Một nhóm nhỏ | Low | Chia metric theo phương thức |
| `outcome=success/error/rejected` | 3 giá trị | Low | Đo tỷ lệ kết quả |
| `region=ap-southeast-1` | Vài region được phép | Low | So sánh địa lý triển khai |
| `reservation.attempt_id=...` | Một ID gần như cho mỗi lần thử | High | Điều tra một thao tác riêng |
| `request.id=...` | Một ID gần như cho mỗi request | High | Tìm sự kiện cụ thể |
| `user.id=...` | Có thể hàng triệu giá trị | High | Chỉ xem xét khi có mục đích, quyền và chính sách bảo vệ dữ liệu rõ ràng |

Đừng đánh giá bằng **độ dài chuỗi**. `outcome=success` dài hơn nhiều mã ngắn, nhưng giá trị của `outcome` vẫn bị giới hạn. Một mã 6 ký tự được sinh ngẫu nhiên theo từng request lại có thể tạo hàng triệu giá trị.

### Cardinality đối với metrics

Một chuỗi thời gian trong hệ thống như Prometheus thường được nhận diện bởi **tên metric + tổ hợp labels**. Giả sử metric HTTP có 4 method, 10 route template, 5 nhóm status và 8 instance. Nếu các tổ hợp đều tồn tại, có thể có tới:

~~~text
4 method × 10 route × 5 status × 8 instance = 1.600 series
~~~

Nếu thêm `request.id` có 100.000 giá trị, số tổ hợp *tiềm năng* tăng cực mạnh. Không phải mọi tích Descartes đều xuất hiện trên dữ liệu thực, nhưng chỉ cần gần một series mới mỗi request cũng đủ làm tăng chi phí lưu trữ, bộ nhớ và truy vấn. Histogram còn tạo nhiều chuỗi `_bucket` cho cùng bộ nhãn.

### Cardinality đối với traces

Trace thường ghi nhận **từng lần thực thi** bằng các spans. Một span có thể mang thuộc tính riêng của chính lần thực thi đó; vì vậy một khóa có nhiều giá trị **không tự động tạo ra time series mới**. Dù vậy, giá trị high-cardinality vẫn tốn dung lượng truyền/lưu, có thể làm chỉ mục tìm kiếm lớn và gây rủi ro bảo mật. Hãy chỉ thêm những giá trị cần thiết cho điều tra, có kiểm soát kích thước và retention.

**High-cardinality** mô tả số giá trị phân biệt, không khẳng định dữ liệu quan trọng hơn low-cardinality. `outcome` thường có giá trị vận hành cao hơn `request.id` trong cảnh báo, dù cardinality thấp.

## 3. High-cardinality key value nằm ở đâu trong kiến trúc Observation?

Micrometer Observation tách **instrumentation** khỏi cách xuất dữ liệu. Mã ứng dụng tạo một `Observation`, gắn metadata vào `Observation.Context`, sau đó các `ObservationHandler` phản ứng theo vòng đời.

~~~mermaid
flowchart TD
    A["ReservationService"] --> B["Observation: orders.reserve"]
    B --> C["Context"]
    C --> D["Low cardinality: operation, outcome, channel"]
    C --> E["High cardinality: reservation.attempt_id"]
    B --> F["ObservationRegistry + handlers"]
    F --> G["Meter ObservationHandler"]
    F --> H["Tracing ObservationHandler"]
    G --> I["MeterRegistry → metrics exporter"]
    H --> J["Tracer → sampler / tracing exporter"]
    D --> I
    D --> J
    E --> J
~~~

Theo cách dùng chuẩn:

1. `Observation.lowCardinalityKeyValue(k, v)` bổ sung metadata có tập giá trị hữu hạn, phù hợp để meter handler dùng như metric tags.
2. `Observation.highCardinalityKeyValue(k, v)` bổ sung metadata có thể phân biệt từng thao tác, thường được tracing handler sử dụng để đưa vào span attributes.
3. `Observation.Context` giữ các key–value và trạng thái vòng đời; handler nhận context khi `onStart`, `onError`, `onStop`, v.v.
4. `MeterRegistry` và tracing exporter có đường đi độc lập; sampler của tracing không có nghĩa là chỉ các request được sample mới đóng góp vào Timer.

**Lưu ý:** đây là hành vi của các handler tiêu chuẩn. Một custom handler vẫn có thể đọc high-cardinality metadata và đưa nó vào metric label bằng mã tự viết. API không thể tự ngăn hành vi đó; developer phải giữ đúng ranh giới dữ liệu.

## 4. Cách sử dụng API trong Java

### 4.1. Gắn một giá trị

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

Observation observation = Observation.createNotStarted(
        "orders.reserve", observationRegistry)
    .lowCardinalityKeyValue("operation", "reserve")
    .highCardinalityKeyValue(
        "reservation.attempt_id", "demo-attempt-001")
    .start();

try (Observation.Scope scope = observation.openScope()) {
    performReservation();
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

Trong đoạn code minh họa này:

- `operation=reserve` có tập giá trị giới hạn, có thể dùng để phân nhóm metric.
- `reservation.attempt_id=demo-attempt-001` là ID của **một lần thử**, nên thuộc nhóm high-cardinality.
- `start()` và `stop()` mở/đóng vòng đời observation; `openScope()` làm observation trở thành current trong ngữ cảnh thực thi liên quan.
- `error(ex)` báo lỗi cho handler; không được thay bằng việc chỉ gắn metadata `status=failed`.

Hai key được thêm **trước `start()`** vì ta đã biết chúng từ đầu. Việc xử lý key bởi tracing handler có thể diễn ra ở các callback khác nhau tùy implementation; cung cấp metadata sớm giúp tránh phụ thuộc vào thời điểm kết thúc để đưa attribute lên span.

### 4.2. Gắn giá trị sau khi có kết quả

Không phải mọi thông tin đều có sẵn khi bắt đầu. Ví dụ ID tác vụ do hệ thống lưu trữ trả về chỉ xuất hiện sau khi ghi thành công.

~~~java
Observation observation = Observation.createNotStarted(
        "inventory.reserve", observationRegistry)
    .lowCardinalityKeyValue("operation", "reserve")
    .start();

try (Observation.Scope scope = observation.openScope()) {
    Reservation reservation = inventory.reserve();
    observation.highCardinalityKeyValue(
        "reservation.reference", reservation.reference());
    observation.lowCardinalityKeyValue("outcome", "success");
} catch (RuntimeException ex) {
    observation.lowCardinalityKeyValue("outcome", "error");
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

Ở đây `Reservation` và `inventory` là các kiểu nghiệp vụ giả định. Không có yêu cầu phải đưa mọi ID trả về vào trace: cần xem xét **lợi ích truy vấn, quyền truy cập dữ liệu, độ dài giá trị** trước khi thêm `reservation.reference`.

Metadata bổ sung sau `start` có thể được một số tracing handler đưa lên span ở giai đoạn kết thúc; hành vi cụ thể tùy Micrometer/bridge/version. Vì vậy, khi xây tính năng bắt buộc dựa trên một attribute động, hãy xác minh trên tracer và exporter đang dùng; **đừng giả định mọi backend đều hiển thị attribute được gắn sau khi span kết thúc**.

### 4.3. Cách đọc metadata ở Context

~~~java
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;

Observation.Context context = observation.getContext();

KeyValues low = context.getLowCardinalityKeyValues();
KeyValues high = context.getHighCardinalityKeyValues();
~~~

Hai tập dữ liệu được giữ tách biệt. Đọc `high` trong code không tự động truyền nó sang log hoặc metrics. Nếu dùng custom handler, hãy chỉ lấy các trường đã được phê duyệt, tránh ghi toàn bộ context vì trong context có thể có đối tượng nghiệp vụ hoặc dữ liệu nhạy cảm.

## 5. Ví dụ Spring Boot: ID của một lần thử giữ hàng

Ta muốn theo dõi thao tác `inventory.reserve`. Mỗi lần thử được gắn một **ID kỹ thuật do ứng dụng sinh ra**, khác nhau giữa các lần thực thi, nhằm liên kết một span với một dòng log kỹ thuật khi cần. ID này không chứa email, token, nội dung đơn hàng hay thông tin người dùng.

### 5.1. Dependencies

Với Spring Boot 3.x, starter Actuator cung cấp tích hợp Micrometer Observation:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Để **xuất trace** tới backend cần bổ sung tracing bridge và exporter tương ứng với stack đang dùng, chẳng hạn Micrometer Tracing với OpenTelemetry và OTLP. Tên dependency, property và mức hỗ trợ tùy phiên bản Spring Boot; riêng `spring-boot-starter-actuator` không đảm bảo một trace sẽ tự được gửi tới một hệ thống từ xa.

### 5.2. Service ghi low và high cardinality

~~~java
package example.inventory;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final ObservationRegistry registry;

    public InventoryService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void reserve(String incomingChannel, Runnable action) {
        String channel = normalizeChannel(incomingChannel);
        String attemptId = UUID.randomUUID().toString();

        Observation observation = Observation.createNotStarted(
                "inventory.reserve", registry)
            .contextualName("reserve inventory")
            .lowCardinalityKeyValue("channel", channel)
            .highCardinalityKeyValue(
                "inventory.reservation_attempt_id", attemptId)
            .start();

        try (Observation.Scope scope = observation.openScope()) {
            action.run();
            observation.lowCardinalityKeyValue(
                    "outcome", "success");
        } catch (RuntimeException ex) {
            observation.lowCardinalityKeyValue(
                    "outcome", "error");
            observation.error(ex);
            throw ex;
        } finally {
            observation.stop();
        }
    }

    private static String normalizeChannel(String value) {
        if ("web".equals(value)) return "web";
        if ("mobile".equals(value)) return "mobile";
        if ("partner".equals(value)) return "partner";
        return "other";
    }
}
~~~

Mỗi lần `reserve(...)` được gọi:

1. `channel` được chuẩn hóa về bốn giá trị `web/mobile/partner/other`, bảo đảm cardinality thấp.
2. `attemptId` được sinh từ `UUID` nên rất có thể là giá trị mới ở mỗi lần gọi. Nó thuộc **high cardinality**, không được đưa vào metric labels.
3. Một observation `inventory.reserve` được tạo và start. Nếu Meter ObservationHandler hoạt động, Timer nghiệp vụ có thể được ghi khi stop.
4. Nếu tracing được bật và span được sample/export, tracing handler có thể gắn `inventory.reservation_attempt_id` lên span.
5. `outcome` được thêm sau khi biết kết quả. `error(ex)` báo trạng thái lỗi cho các handler, còn `finally` bảo đảm kết thúc observation.
6. `try-with-resources` đóng scope đúng cách dù hành động thành công hay lỗi.

Ví dụ dùng `Runnable` để tập trung vào phần observability, không mô tả giao dịch tồn kho đầy đủ. Nếu hệ thống có nhiều loại exception, cơ chế retry hoặc xử lý bất đồng bộ, cần điều chỉnh cách phân loại outcome và vòng đời observation cho đúng semantics.

**Lưu ý thiết kế:** sinh thêm `attemptId` chỉ có ích khi có nhu cầu đối chiếu ID đó với dữ liệu kỹ thuật khác. Nếu trace ID hiện có đã đủ cho điều tra, không cần tạo một ID trùng mục đích vì mỗi attribute đều làm tăng lượng dữ liệu.

## 6. High cardinality không đồng nghĩa metric tag

Lỗi nghiêm trọng là vô tình chuyển ID riêng lẻ vào hệ thống metrics. Xem hai đoạn code:

~~~java
// Sai đối với metrics có traffic lớn:
meterRegistry.counter(
        "inventory.reservations",
        "reservation_attempt_id", attemptId
).increment();

// Đúng khi muốn tổng hợp theo outcome hữu hạn:
meterRegistry.counter(
        "inventory.reservations",
        "outcome", "success"
).increment();
~~~

Ở ví dụ đầu, một `Counter` có thể sinh một tổ hợp label mới gần như trên mỗi lần thử, khiến backend lưu rất nhiều time series. Mỗi series có thể chỉ chứa một điểm thay đổi rồi không còn được sử dụng, nhưng vẫn phát sinh chi phí.

Ở ví dụ sau, `outcome` chỉ có nhóm giá trị hữu hạn. Dashboard có thể tính số lần thành công/lỗi mỗi phút bằng các phép `rate()` hoặc `increase()` mà không phải giữ riêng từng ID.

| Vị trí dữ liệu | Có nên đưa attempt ID? | Giải thích |
| --- | --- | --- |
| `Observation.highCardinalityKeyValue` | Có điều kiện | Khi ID không nhạy cảm, cần điều tra và tracing pipeline chấp nhận |
| Span attribute | Có điều kiện | Dùng để tìm span một lần thử được sample/export |
| `Observation.lowCardinalityKeyValue` | Không | Có nguy cơ trở thành metrics label |
| `MeterRegistry.counter(..., "attempt_id", ...)` | Không | Mỗi ID có thể tạo time series mới |
| Prometheus common tag hoặc histogram tag | Không | Nhân chi phí series, bucket và instance |
| Log kỹ thuật có kiểm soát | Có điều kiện | Khi có chính sách logging, retention và quyền truy cập tương ứng |

**Nguyên tắc kiểm soát:** phân loại theo **nguồn tiêu thụ cuối cùng**, không chỉ dựa trên tên API. Nếu custom handler chuyển high-cardinality key-values thành metric tags, vấn đề vẫn tồn tại dù ban đầu gọi API high-cardinality.

## 7. Phân biệt high-cardinality attribute, trace ID và baggage

Các khái niệm này có thể cùng xuất hiện trong một hệ thống distributed tracing, nhưng phục vụ mục đích khác nhau.

| Khái niệm | Ví dụ | Ai tạo hoặc truyền? | Tác dụng |
| --- | --- | --- | --- |
| **High-cardinality key–value** | `inventory.reservation_attempt_id=...` | Mã instrument; tracing handler đưa lên span nếu hỗ trợ | Bổ sung chi tiết cho span |
| **Trace ID / Span ID** | Định danh do tracer cấp | Tracing stack | Nhận diện trace và span, kết nối cha–con |
| **Trace context** | Header `traceparent`, tùy cấu hình có `tracestate` | Propagator/instrumentation | Truyền mối quan hệ tracing qua ranh giới dịch vụ |
| **Baggage** | Một key nghiệp vụ cần đi cùng ngữ cảnh tới dịch vụ khác | Cơ chế baggage và propagator được cấu hình | Truyền một số thông tin ngữ cảnh được phép giữa các dịch vụ |
| **Log correlation** | `traceId`, `spanId` trong log | Logging/tracing integration | Từ một log có thể tìm lại trace tương ứng |

**High-cardinality key–value đặt trên observation không mặc nhiên được gửi tới dịch vụ downstream.** Một span attribute chỉ mô tả span đó. Để gửi metadata sang dịch vụ khác, cần API và cấu hình propagation/baggage tương ứng, hoặc truyền giá trị qua hợp đồng nghiệp vụ. Việc đưa ID vào baggage là quyết định riêng: nó làm tăng kích thước headers và có thể chia sẻ thông tin tới nhiều dịch vụ hoặc bên thứ ba.

Ví dụ một request đi qua `order-api` → `inventory-api`:

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-api
    participant Inventory as inventory-api
    participant Collector as Tracing backend
    Client->>Order: POST /orders
    Note over Order: Observation có order.attempt_id = A1
    Order->>Inventory: HTTP + traceparent nếu propagation bật
    Note over Inventory: Tracer tiếp nối trace context
    Inventory-->>Order: 200 OK
    Order-->>Client: Response
    Order-->>Collector: Export span với attribute A1 nếu được sample
    Inventory-->>Collector: Export child span nếu được sample
~~~

Trong sơ đồ, `inventory-api` có thể nối được trace dù **không nhìn thấy `order.attempt_id=A1`**. Muốn dịch vụ đó biết A1, hãy xác định rõ yêu cầu nghiệp vụ và kênh truyền phù hợp; đừng giả định span attribute tự động lan truyền.

Đôi khi một câu hỏi điều tra được giải quyết tốt hơn bằng trace ID trong logs mà không phải thêm ID nghiệp vụ vào mọi span. Luôn cân nhắc tín hiệu đã có trước khi bổ sung metadata.

## 8. Thời điểm gắn giá trị trong vòng đời Observation

Một observation thường đi qua các pha:

~~~mermaid
flowchart LR
    A["createNotStarted"] --> B["Gắn metadata biết trước"]
    B --> C["start"]
    C --> D["openScope"]
    D --> E["Thực hiện công việc"]
    E --> F["Gắn metadata phát sinh, event/error"]
    F --> G["closeScope"]
    G --> H["stop"]
    H --> I["Handlers hoàn tất / exporter xử lý"]
~~~

| Thời điểm | Thông tin thường có | Lưu ý |
| --- | --- | --- |
| Trước `start()` | Tên thao tác, kênh, ID thử xử lý đã tạo | Phù hợp khi muốn tracing handler đọc attribute ngay từ lúc bắt đầu |
| Sau `start()`, trước `stop()` | ID được downstream trả về, outcome, loại bước thất bại | Handler có thể đọc dữ liệu ở pha cuối; xác minh theo implementation |
| Sau `error(ex)` | Thông tin lỗi đã thông báo cho observation | Không tự động biến mọi thông báo exception thành attribute |
| Sau `stop()` | Observation đã hoàn tất | Không dựa vào việc gắn key muộn để sửa span đã export |
| Khi chuyển thread | Ngữ cảnh scope/current observation có thể thay đổi | Cần context propagation đúng với executor/Reactor |

Thứ tự callback **không được quyết định bởi tên key**. Một handler metrics và một handler tracing có thể tiêu thụ metadata ở các thời điểm khác nhau. Đừng xây business logic dựa trên giả định rằng thêm key ở bất kỳ đâu sẽ “cập nhật tức thì mọi backend”.

Khi instrument thủ công, dùng `try-with-resources` cho scope và `finally` cho `stop()`. Nếu thao tác trả về `CompletableFuture`, không nên stop ngay sau khi submit, vì công việc có thể chưa hoàn tất; cần kết thúc observation tại thời điểm kết quả thực sự đến và truyền ngữ cảnh theo cơ chế của framework.

## 9. Bảo mật và quyền riêng tư: high cardinality không có nghĩa được phép ghi mọi dữ liệu

High-cardinality fields thường chứa định danh; đây là lý do cần xem xét **nội dung** và **quyền truy cập**, không chỉ lượng dữ liệu.

**Những giá trị không nên đưa trực tiếp vào span attributes hoặc logs:** mật khẩu, access token, API key, cookie phiên, số thẻ thanh toán, chuỗi ủy quyền, thông tin nhạy cảm của người dùng, nội dung request/response có dữ liệu riêng tư, SQL chứa dữ liệu nhạy cảm hoặc full URL có query parameters.

Với `user.id`, `customer.email`, `order.id`, `device.id` và những giá trị định danh khác, việc cho phép dùng hay không phụ thuộc phân loại dữ liệu, mục đích điều tra, pháp luật và chính sách của tổ chức. **Không coi tracing là nơi lưu dữ liệu vô hạn.** Những giá trị cần thiết có thể được giả danh, rút gọn, mã hóa/băm phù hợp hoặc thay bằng một opaque correlation ID; cần đảm bảo cách xử lý tương thích với yêu cầu truy vấn thực tế.

Ví dụ thiết kế theo hướng giảm thiểu dữ liệu:

~~~java
// ID kỹ thuật mới, không chứa thông tin cá nhân:
String attemptId = UUID.randomUUID().toString();

observation.highCardinalityKeyValue(
        "inventory.reservation_attempt_id", attemptId);

// Không đưa một dữ liệu xác thực vào observation:
// observation.highCardinalityKeyValue("auth.token", bearerToken);
~~~

Trong production nên có quy định thống nhất:

1. **Allowlist keys:** chỉ một số key được phép xuất; không thêm attribute tùy hứng từ HTTP headers.
2. **Giới hạn kích thước:** kiểm soát độ dài và dạng giá trị; tránh đính kèm payload hoặc stack trace dài.
3. **Phạm vi truy cập:** tracing backend có quyền truy cập, retention và chính sách audit phù hợp.
4. **Sampling và chi phí:** xác định volume, mức lấy mẫu, số attributes/span và chính sách lưu trữ.
5. **Vòng đời dữ liệu:** biết cách xóa/ẩn thông tin khi cần theo quy trình tổ chức.

Việc băm dữ liệu không mặc nhiên biến nó thành vô hại: một giá trị băm ổn định vẫn có thể là định danh người dùng và vẫn có cardinality cao.

## 10. Kết hợp metrics, logs và traces để điều tra sự cố

Giả sử 3% yêu cầu giữ hàng bị timeout. Ta không cần đặt `reservation.attempt_id` vào metric label để tìm từng request lỗi.

**Bước 1 — phát hiện qua metrics.** Timer `inventory.reserve` có low-cardinality tags như `outcome=error` và `channel=mobile`. Dashboard cho thấy thời điểm lỗi tăng và kênh ảnh hưởng.

**Bước 2 — chọn một trace.** Dựa trên thời gian, service, operation và thời lượng, chọn một trace được sample trong backend. Span chứa high-cardinality `inventory.reservation_attempt_id` nếu pipeline đã ghi/giữ attribute.

**Bước 3 — tìm log liên quan.** Dùng `traceId/spanId` nếu cấu hình log correlation; có thể dùng attempt ID ở log kỹ thuật nếu chính sách cho phép và log đã ghi giá trị đó. Việc chỉ thêm high-cardinality key vào Observation **không tự động viết một dòng log**.

**Bước 4 — phân tích call path.** Xem span HTTP client, database hoặc queue để xác định đoạn chậm. Trace context phải được propagate giữa dịch vụ để các span có quan hệ cha–con.

**Bước 5 — xác nhận bằng metrics.** Sau khi khắc phục, kiểm tra p95 latency, error rate và throughput hồi phục trong một khoảng thời gian đủ dài. Một trace riêng chỉ cung cấp bằng chứng cho một luồng thực thi; metrics mới cho thấy tác động toàn hệ thống.

~~~mermaid
flowchart TD
    A["Metrics: error rate & p95 tăng"] --> B["Khoanh vùng theo low-cardinality tags"]
    B --> C["Chọn trace được sample"]
    C --> D["Span high-cardinality attributes"]
    C --> E["Logs theo traceId/spanId"]
    D --> F["Phân tích downstream/DB"]
    E --> F
    F --> G["Khắc phục và kiểm chứng lại metrics"]
~~~

**Exemplar** là một cơ chế riêng, có thể liên kết một mẫu metric tới trace ID khi registry/exporter/backend hỗ trợ. Đây là hướng nối metrics với tracing mà không cần biến request ID thành metric label. Không phải mọi phiên bản hoặc backend đều bật exemplar mặc định.

## 11. Sampling, exporter và context propagation: vì sao không thấy high-cardinality attribute?

Gắn key vào Observation chỉ là **một chặng** của pipeline:

~~~text
Code instrument
  -> Observation.Context (high-cardinality key)
  -> tracing ObservationHandler
  -> Tracer/Span
  -> Sampling decision
  -> Reporter/Exporter
  -> Collector/Tracing backend
  -> Index/search/UI
~~~

Các tình huống phổ biến:

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Attribute có trong context nhưng không hiện trên span | Handler không xử lý high keys, thêm sau khi span kết thúc, bridge/version khác kỳ vọng | Kiểm tra tracer/span đang tạo, thời điểm gắn key |
| Có span trong ứng dụng nhưng không tìm thấy trace trên backend | Sampler không chọn trace; exporter/collector lỗi | Kiểm tra cấu hình sampling, exporter và collector |
| Chỉ một số request có attribute | Metadata chỉ có trên một số code path hoặc một số instance | Đối chiếu nhánh xử lý và phiên bản đang chạy |
| Span không nối đúng qua hai dịch vụ | Thiếu propagation cho HTTP/messaging hoặc mất context khi chuyển thread | Kiểm tra trace headers và instrumentation ở client/server |
| Metadata không xuất hiện trong log | Không có cơ chế logging correlation hoặc code chưa log field | Kiểm tra `traceId/spanId` và cấu hình logging riêng |
| Metric không có high key | Đây thường là hành vi mong muốn của meter handler | Kiểm tra low-cardinality tags thay vì đưa ID vào metrics |
| Trace bị quá tải hoặc bị cắt attributes | Quá nhiều attributes, giá trị quá dài hoặc limit của SDK/backend | Kiểm tra giới hạn attribute count/value và chi phí |

**Không suy luận “Observation không chạy” chỉ từ việc thiếu trace.** Timer có thể ghi nhận mọi request trong khi tracing bị sampling. Một số span còn có thể bị bỏ do tail sampling hoặc chính sách lưu dữ liệu tại collector/backend.

Ngược lại, **đừng tăng sampling lên 100% trên production chỉ để tìm một attribute** mà chưa đánh giá chi phí. Có thể tái hiện lỗi trên môi trường test hoặc sử dụng sampling/chẩn đoán có kiểm soát.

## 12. Kiểm chứng key-values mà không phụ thuộc exporter

Trong ví dụ học tập, có thể đăng ký một handler đơn giản vào một `ObservationRegistry` độc lập và xác nhận context chứa đúng low/high key-values. Điều này giúp phân biệt lỗi ở **mã instrument** với lỗi ở **pipeline tracing**.

~~~java
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.concurrent.atomic.AtomicReference;

public final class MetadataDemo {
    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();

        AtomicReference<KeyValues> capturedHigh =
                new AtomicReference<>();

        registry.observationConfig().observationHandler(
                new ObservationHandler<Observation.Context>() {
                    @Override
                    public boolean supportsContext(
                            Observation.Context context) {
                        return true;
                    }

                    @Override
                    public void onStop(
                            Observation.Context context) {
                        capturedHigh.set(
                                context.getHighCardinalityKeyValues());
                    }
                }
        );

        Observation.createNotStarted("demo.reserve", registry)
                .lowCardinalityKeyValue("outcome", "success")
                .highCardinalityKeyValue(
                        "reservation.attempt_id", "demo-123")
                .observe(() -> {
                    // Công việc giả lập
                });

        if (capturedHigh.get() == null) {
            throw new IllegalStateException(
                    "High-cardinality context was not captured");
        }

        System.out.println(capturedHigh.get());
    }
}
~~~

Kết quả kỳ vọng: handler nhận `onStop` và đọc được `reservation.attempt_id=demo-123` trong tập high-cardinality metadata. Đây là kiểm tra **context và callback**, chưa chứng minh span được tạo hay attribute đã được gửi lên collector.

Trong ứng dụng Spring Boot thật, sử dụng `ObservationRegistry` được framework cung cấp. Tạo registry mới trong service chỉ để test có thể khiến observation không gắn với meter/tracing handler đang chạy, gây nhầm lẫn về việc xuất dữ liệu.

### Kiểm tra với Actuator và tracing backend

Khi có Actuator và registry metrics phù hợp:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/inventory.reserve
~~~

Đối với metric `inventory.reserve`, có thể thấy low-cardinality `channel` và `outcome` (tùy instrumentation/handler). **Không tìm `reservation.attempt_id` trong `availableTags` như một tiêu chí thành công.** Để kiểm tra high attribute, mở một trace được sample trên backend và tìm span `inventory.reserve`.

Nếu endpoint metrics không có meter, cần kiểm tra Meter ObservationHandler và quan sát đã `stop()`; nếu backend tracing không có span, kiểm tra tracing bridge, sampling, exporter và propagation trước khi kết luận lỗi nằm ở API high-cardinality.

## 13. Quy ước đặt tên và giới hạn metadata

Tên key nên diễn tả ý nghĩa ổn định của attribute và dễ phân biệt với metrics label. Ví dụ:

| Tên đề xuất | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `inventory.reservation_attempt_id` | ID kỹ thuật của lần thử giữ hàng | High; kiểm soát retention |
| `orders.operation` | Nhóm thao tác nghiệp vụ | Low khi giá trị hữu hạn |
| `orders.outcome` | Kết quả logic thành công/từ chối/lỗi | Low |
| `messaging.message_id` | ID thông điệp riêng | High; xem xét dữ liệu nhạy cảm |
| `http.route` | Route template, không chứa ID thực | Low |
| `http.target` với query string tự do | Có thể lộ dữ liệu và có nhiều giá trị | Tránh đưa nguyên văn vào tags |

Trước khi thêm một high-cardinality key, trả lời:

1. **Câu hỏi điều tra nào cần key này?** Nếu trace ID đã giải quyết được, không phải thêm.
2. **Key xuất hiện trên những span nào?** Tránh đính kèm vào mọi span nếu chỉ có ý nghĩa với bước nghiệp vụ cụ thể.
3. **Giá trị có nhạy cảm không?** Nếu có, cần chính sách dữ liệu/kiểm soát hoặc lựa chọn ID thay thế.
4. **Giá trị dài bao nhiêu?** Có thể giới hạn cấu trúc và độ dài ngay tại nguồn.
5. **Lượng trace được giữ là bao nhiêu?** Dựa trên traffic, sampling và retention để ước tính chi phí.
6. **Có ai vô tình đưa key vào metrics không?** Rà soát meter custom và conventions.

Khi tất cả key đều được thêm tùy hứng từ exception/request headers, một ứng dụng có thể tạo ra span attributes khó quản lý. Nên có danh mục metadata dùng chung cho service, đồng thời cho phép mở rộng có chủ đích theo tình huống nghiệp vụ.

## 14. Bài thực hành: điều tra một lần lỗi bằng high-cardinality key value

**Bối cảnh:** ứng dụng `booking-service` xử lý tạo booking. Bạn có Timer nghiệp vụ `bookings.create` và tracing đã hoạt động. Mục tiêu là biết request nào gặp lỗi mà không làm tăng cardinality của metric.

**Nhiệm vụ A — thiết kế metadata**

Hãy chọn:

- Low cardinality: `channel=web/mobile`, `outcome=success/rejected/error`.
- High cardinality: `booking.attempt_id`, một ID kỹ thuật không chứa thông tin nhạy cảm, thay đổi theo lần thử.
- Không dùng `booking.attempt_id` làm label cho Timer hoặc Counter.

Giả sử có 2 kênh, 3 trạng thái kết quả và 6 instance, hãy tính số tổ hợp tags tối đa cho mỗi phép đo theo ba chiều này: **2 × 3 × 6 = 36**. Nếu thêm attempt ID cho 50.000 lần xử lý, ước tính vì sao mỗi lần thử có thể phát sinh thêm một tổ hợp mới, khiến chi phí series tăng theo traffic.

**Nhiệm vụ B — instrument code**

Viết một service dùng `ObservationRegistry`, tạo `Observation.createNotStarted("bookings.create", registry)` và gắn `booking.attempt_id` bằng `highCardinalityKeyValue(...)`. Dùng `try-with-resources` cho scope, `observation.error(ex)` khi lỗi và `finally` cho `stop()`.

**Nhiệm vụ C — kiểm chứng**

Chạy một số request thành công và thất bại ở môi trường thử nghiệm:

1. Xem Timer `bookings.create` qua Actuator và kiểm tra chỉ có những low-cardinality tags mong muốn.
2. Mở một trace có span booking; tìm `booking.attempt_id` trong span attributes nếu trace được sample và exporter giữ attribute.
3. Từ log có trace ID, tra lại trace; xác định các bước HTTP client/database gây chậm hoặc lỗi.
4. Tắt tracing exporter trong môi trường test và quan sát: Observation vẫn có context metadata, nhưng backend không nhận trace; metrics có thể tiếp tục được ghi độc lập.
5. Giải thích vì sao high-cardinality attribute không mặc định xuất hiện trên các span của dịch vụ khác.

**Câu hỏi tự kiểm tra:**

1. High-cardinality được định nghĩa theo độ dài chuỗi hay số giá trị phân biệt?
2. Vì sao `request.id` không phù hợp cho metric label dù hữu ích trong truy vết?
3. `highCardinalityKeyValue(...)` có tự động truyền giá trị qua HTTP headers không?
4. Nếu high attribute có trong context nhưng không thấy trên tracing UI, cần kiểm tra các bước nào?
5. Sampling ảnh hưởng thế nào đến số trace và số lần ghi Timer?
6. Vì sao vẫn phải kiểm soát bảo mật dù value đã được gắn dưới nhóm “high”?
7. Trace ID, baggage và high-cardinality span attribute khác nhau về mục tiêu và propagation như thế nào?
8. Một custom handler tự đưa high key vào MeterRegistry có thể tạo hậu quả gì?

**Tiêu chí hoàn thành:** giải thích được high-cardinality và chi phí; dùng đúng API của Micrometer Observation; phân biệt low/high/context/trace ID/baggage; kiểm tra được đường đi từ Observation đến span; tránh đưa ID vào metrics và chú ý bảo mật, sampling, exporter, propagation.

## Ghi nhớ

- `highCardinalityKeyValue(key, value)` lưu metadata có thể có rất nhiều giá trị vào `Observation.Context`; tracing handler có thể chuyển chúng thành **span attributes**, tùy pipeline và sampling.
- **Không dùng ID của từng request hoặc đối tượng riêng làm metric tags.** Metrics phục vụ tổng hợp theo low-cardinality dimensions, còn tracing phục vụ phân tích từng đường thực thi.
- High-cardinality key–value **không phải** trace ID hay baggage và **không tự động được propagate** sang dịch vụ khác.
- Tracing chỉ mang lại kết quả có thể tìm kiếm khi bridge, handler, sampler, exporter và backend được cấu hình tương thích; log correlation cũng có đường cấu hình riêng.
- Chỉ ghi metadata phục vụ nhu cầu rõ ràng, tránh dữ liệu nhạy cảm, giới hạn giá trị và có retention/quyền truy cập phù hợp.
- Khi điều tra sự cố: dùng metrics phát hiện xu hướng, traces xác định bước chậm, logs cung cấp sự kiện và kiểm chứng lại cải tiến trên metrics.

## Tài liệu tham khảo

- [Micrometer — Observation introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer — Observation components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OpenTelemetry — Semantic conventions](https://opentelemetry.io/docs/specs/semconv/)

