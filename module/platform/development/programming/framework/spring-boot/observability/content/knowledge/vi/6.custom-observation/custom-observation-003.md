# Tên observation ổn định

Trong một dịch vụ Spring Boot, hai yêu cầu cùng thực hiện chức năng thanh toán có thể thuộc hai người dùng khác nhau, mang mã đơn hàng khác nhau và chạy trên những instance khác nhau. Tuy nhiên, cả hai vẫn thực hiện **cùng một loại công việc**: xác thực một lần thanh toán. Đối với Micrometer Observation, chúng nên có **cùng tên observation**. Những khác biệt giữa hai lần gọi được biểu diễn bằng tag hoặc ngữ cảnh, trong phạm vi và mức độ chi tiết phù hợp.

Ví dụ:

```text
Yêu cầu A: checkout.authorize
  channel=web, payment.method=card, order.id=O-123

Yêu cầu B: checkout.authorize
  channel=mobile, payment.method=wallet, order.id=O-987

Tên observation chung: checkout.authorize
Low-cardinality tags: channel, payment.method
High-cardinality trace attribute (nếu được phép): order.id
```

Ngược lại, nếu đặt tên `checkout.authorize.O-123` và `checkout.authorize.O-987`, mỗi đơn hàng trở thành một loại phép đo khác nhau. Metrics khó tổng hợp, số series tăng, dashboard phải liên tục thay đổi và việc so sánh trước/sau triển khai mất tính nhất quán.

Bài **Tên observation ổn định** thuộc chương **Custom observation** của module **SPRING_BOOT_OBSERVABILITY**. Mục tiêu của module là thiết lập observability cho Spring Boot bằng **Micrometer Observation, metrics, logs và distributed tracing**, đồng thời học về propagation ngữ cảnh, tag/cardinality, exporter, sampling và cách liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng thực tế. Bài này tập trung vào một quyết định nền tảng: **thiết kế tên của mỗi loại hoạt động như một hợp đồng dữ liệu lâu dài**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao nhiều lần chạy cùng một hoạt động phải chia sẻ tên observation.
2. Phân biệt `Observation name`, `contextualName`, metric name sau exporter, tên span và key-value của observation.
3. Thiết kế bộ tên ngắn gọn, có ý nghĩa nghiệp vụ, ổn định qua request, instance và phiên bản ứng dụng.
4. Viết một custom observation trong Spring Boot với tên cố định và các tag có cardinality được kiểm soát.
5. Sử dụng `ObservationConvention` để tập trung hóa cách đặt tên và metadata.
6. Phát hiện tên biến động bằng kiểm thử, metrics endpoint hoặc truy vấn trên backend.
7. Lập kế hoạch đổi tên an toàn khi dashboard, alert, SLO và các hệ thống truy vấn đã phụ thuộc vào tên cũ.

## 2. Tên observation là gì và ai sử dụng?

**Observation** mô tả một hoạt động đang diễn ra, có vòng đời bắt đầu, mở scope, ghi nhận lỗi/sự kiện và kết thúc. `ObservationRegistry` chuyển các sự kiện vòng đời đến những `ObservationHandler` tương ứng. Với cấu hình phù hợp, một observation có thể tạo **timer metric** và **span trace**; bản thân observation không tự tạo mọi dòng log.

Ba khái niệm tên cần tách rõ:

| Khái niệm | Ví dụ | Tác dụng chính |
|---|---|---|
| **Observation name** | `checkout.authorize` | Tên nhận diện **loại hoạt động**. Meter handler dùng làm tên timer chuẩn trước khi registry chuyển đổi theo backend. |
| **Contextual name** | `authorize checkout` | Tên dễ đọc cho hoạt động trong **ngữ cảnh tracing**; tracing handler có thể dùng làm tên span. |
| **Key-values / attributes** | `channel=web`, `payment.method=card` | Các chiều thông tin để lọc/nhóm các lần chạy của một hoạt động. Chúng không nên làm tên hoạt động thay đổi. |

Như vậy, thiết kế này hợp lý:

```java
Observation.createNotStarted("checkout.authorize", observationRegistry)
        .contextualName("authorize checkout")
        .lowCardinalityKeyValue("channel", "web")
        .lowCardinalityKeyValue("payment.method", "card")
        .observe(() -> {
            // Thực hiện một lần xác thực thanh toán.
        });
```

Còn thiết kế sau không hợp lý:

```java
// Không làm thế này: một tên mới cho mỗi lần gọi.
String name = "checkout.authorize." + orderId;

Observation.createNotStarted(name, observationRegistry)
        .observe(() -> {
            // Xử lý đơn hàng tương ứng.
        });
```

### 2.1 Tên trong mã Java không nhất thiết giống tên ở backend

Micrometer đề xuất tên chuẩn **chữ thường, các phần cách nhau bằng dấu chấm**. Ví dụ `checkout.authorize` hoặc `http.server.requests`. Khi xuất sang Prometheus, registry có thể chuẩn hóa dấu chấm thành dấu gạch dưới và bổ sung hậu tố về đơn vị/loại metric.

```text
Trong code:          checkout.authorize
Tên timer Micrometer: checkout.authorize

Ví dụ trên Prometheus (tùy registry và cấu hình):
  checkout_authorize_seconds_count
  checkout_authorize_seconds_sum
  checkout_authorize_seconds_bucket  (chỉ khi histogram phù hợp được bật)

Tên span tracing:
  authorize checkout  (nếu đặt contextualName và handler sử dụng)
```

Không hard-code tên Prometheus bằng cách tự thêm `_seconds_count` vào `Observation.createNotStarted(...)`. Đây là tên **sau khi exporter chuyển đổi**, không phải hợp đồng tên observation ở tầng ứng dụng.

Lưu ý: từng phiên bản và semantic convention có thể đổi tên metric mặc định hoặc cách chuyển đổi. Hãy xác minh output thực tế của `/actuator/metrics` và `/actuator/prometheus` trước khi chốt truy vấn dashboard.

### 2.2 Tại sao không đặt mọi hoạt động bằng tên chung `operation`?

Tên phải **ổn định nhưng vẫn đủ phân biệt**. Nếu mọi nghiệp vụ đều dùng `operation`, dashboard không thể biết số liệu thuộc checkout, xác thực token hay nhập hàng trừ khi luôn dựa vào tag bổ sung. Đó là một hợp đồng yếu và làm việc truy vấn/phân quyền theo loại hoạt động trở nên khó.

Tên tốt mô tả một **ranh giới đo đạc có ý nghĩa**. Ví dụ:

- `checkout.authorize`: từ lúc bắt đầu xác thực thanh toán đến khi có kết quả.
- `inventory.reserve`: thời gian xử lý một lần giữ hàng.
- `report.generate`: thời gian tạo một báo cáo.
- `catalog.index.rebuild`: quá trình xây dựng lại chỉ mục.
- `invoice.publish`: công việc gửi một hóa đơn đến hệ thống ngoài.

Nếu hai đoạn mã đo những việc có ý nghĩa khác nhau, nên có tên khác nhau. Không gộp tất cả vào một tên chỉ vì chúng cùng nằm trong một lớp Java.

## 3. Hệ quả khi tên thay đổi theo dữ liệu đầu vào

Xem một API:

```text
POST /api/orders/101/checkout
POST /api/orders/102/checkout
POST /api/orders/103/checkout
```

Nếu mã dùng `"checkout." + orderId`, số observation names tăng gần bằng số đơn hàng. Điều đó gây ra nhiều vấn đề:

1. **Số lượng metrics**: một timer có nhiều tổ hợp tag; mỗi tên động lại tạo một nhóm meter độc lập. Bộ nhớ registry, lưu trữ và truy vấn có thể tăng theo số đơn.
2. **Thiếu khả năng tổng hợp**: truy vấn `checkout_authorize_seconds_count` không xuất hiện vì dữ liệu bị chia thành vô số tên khác nhau.
3. **Dashboard và alert kém ổn định**: một dashboard lọc đúng một tên hôm nay có thể không hiển thị yêu cầu ngày mai.
4. **Không so sánh được lịch sử**: khi triển khai code mới đổi cách ghép tên, dữ liệu trông như đã “biến mất”, dù ứng dụng vẫn chạy.
5. **Traces khó phân tích**: nếu span name cũng chứa ID, backend thấy quá nhiều operation names, khiến nhóm những trace cùng loại khó hơn.
6. **Chính sách telemetry kém hiệu quả**: quy tắc bật/tắt, sampling, retention hoặc filtering theo tên khó áp dụng nhất quán.

Số series metrics thường tăng theo tổ hợp giữa **tên meter và các nhãn**. Ví dụ nếu có 3 giá trị `channel` × 4 giá trị `payment.method` × 5 kết quả, một metric có thể có đến 60 tổ hợp nhãn hữu ích. Nếu thêm 100.000 `orderId` làm tên hoặc tag, tổng số chuỗi tiềm năng có thể tăng khoảng 100.000 lần. Con số thực tế tùy tập nhãn có cùng xuất hiện và cách exporter lưu trữ, nhưng rủi ro cardinality là có thật.

**Tên động cũng là một dạng cardinality cao**, kể cả khi mọi tag đều có tập giá trị nhỏ.

## 4. Sáu nguyên tắc thiết kế tên ổn định

### 4.1 Tên mô tả loại công việc, không mô tả một lần chạy

Ưu tiên `domain.action` hoặc `subsystem.operation`:

```text
checkout.authorize
inventory.reserve
report.generate
message.consumer.process
```

Tránh ID thực thể, UUID, mã người dùng, timestamp, số thứ tự retry, stack trace hoặc request path thực tế trong tên.

### 4.2 Giữ quy tắc tên thống nhất

Micrometer khuyến nghị **lowercase dot notation**. Nên chọn trước một quy ước nội bộ, chẳng hạn:

- Danh từ lĩnh vực/đối tượng trước, động từ hoặc thao tác sau: `inventory.reserve`.
- Dùng dấu chấm phân cấp; không trộn tùy ý `checkout-authorize`, `checkoutAuthorize` và `checkout.authorize`.
- Tên đủ cụ thể để hiểu khi nhìn vào dashboard, nhưng không dài đến mức chứa cả mô tả request.
- Không thêm đơn vị `seconds` hoặc `milliseconds` vào tên của một `Observation` vốn sẽ được meter handler đo bằng timer và đổi đơn vị theo backend.

Đây là **quy ước thiết kế**, không phải một ngữ pháp bắt buộc duy nhất của Micrometer. Nếu một dự án đã tuân thủ semantic convention chính thức, nên ưu tiên tính tương thích của convention đó.

### 4.3 Ổn định qua các môi trường và lần triển khai

Tên `checkout.authorize` không nên trở thành:

```text
checkout.authorize.dev
checkout.authorize.prod
checkout.authorize.node-8
checkout.authorize.v42
```

Môi trường, vùng triển khai và phiên bản nên được biểu diễn bằng **resource attributes hoặc nhãn chung được kiểm soát** khi cần. Trong Spring Boot có thể cấu hình common low-cardinality key-values như `region=ap-southeast-1` hoặc `stack=prod`. Với môi trường có nhiều instance, cần đánh giá cardinality của nhãn instance và cách backend quản lý resource identity.

Một lần gọi cùng loại trên hai instance vẫn có cùng observation name. Điều đó giúp cộng gộp metrics và so sánh hành vi trước/sau rollout.

### 4.4 Cùng tên phải giữ cùng ngữ nghĩa

Giả sử `report.generate` từng đo quá trình tạo file PDF, nhưng code mới chỉ đo thao tác lấy dữ liệu từ cache. Nếu vẫn giữ tên, đường biểu diễn độ trễ lịch sử trở nên không còn so sánh được. **Ổn định về chuỗi ký tự chưa đủ; ranh giới đo và ý nghĩa nghiệp vụ cũng phải ổn định.**

Khi thay đổi đáng kể phạm vi:

- Xác định liệu có phải loại công việc mới thực sự không.
- Đặt tên mới nếu semantics khác.
- Nếu vẫn cùng loại công việc, giữ tên và dùng một chiều dữ liệu có tập giá trị giới hạn để phân tích sự thay đổi, khi phù hợp.
- Ghi nhận tác động lên dashboard, alert và SLO.

### 4.5 Tên không chứa dữ liệu nhạy cảm

Ngay cả khi một giá trị không xuất hiện trong metrics, span names vẫn có thể đi vào hệ thống tracing và được nhiều người tìm kiếm. Tránh đưa token, email, số tài khoản, tên khách hàng hoặc dữ liệu riêng tư vào **observation name** lẫn **contextualName**.

### 4.6 Tên có chủ sở hữu và được tài liệu hóa

Với mỗi custom observation quan trọng, đội phát triển nên có hợp đồng ngắn:

```yaml
# Ví dụ tài liệu hợp đồng; không phải cấu hình Spring Boot tự động.
observation: checkout.authorize
purpose: "Đo một lần xác thực thanh toán với payment provider"
boundary: "Từ lúc bắt đầu gọi provider đến khi có kết quả cuối"
contextualName: "authorize checkout"
lowCardinality:
  channel: ["web", "mobile", "partner", "other"]
  payment.method: ["card", "wallet", "bank_transfer", "other"]
owner: "checkout team"
consumers: ["checkout dashboard", "payment latency alert"]
```

Hợp đồng còn nên nói rõ khi nào coi là error, kiểu dữ liệu của thời lượng, nguồn cung cấp instrumentation và trách nhiệm kiểm thử khi thay đổi tên. Đây là tài liệu mô tả chứ không phải file metadata STEP 4 của module.

## 5. Tách tên khỏi dữ liệu biến thiên

Một quy tắc thực tế là **tên observation trả lời “đang làm việc gì?”, tags trả lời “loại nào?”, trace attributes giúp biết “lần nào?”**.

| Thông tin | Đặt ở đâu? | Ví dụ |
|---|---|---|
| Loại công việc ổn định | Observation name | `checkout.authorize` |
| Tên operation dễ đọc | `contextualName` | `authorize checkout` |
| Phương thức thanh toán thuộc tập hữu hạn | Low-cardinality key-value | `payment.method=card` |
| Kênh truy cập đã chuẩn hóa | Low-cardinality key-value | `channel=mobile` |
| Kết quả theo tập hữu hạn | Low-cardinality key-value | `outcome=approved` |
| ID đơn hàng gần như duy nhất | Chỉ cân nhắc high-cardinality trace attribute khi được phép | `order.id=O-123` |
| ID yêu cầu/trace | Trace context hoặc log correlation có kiểm soát | `traceId=...` |
| Tên pod hoặc triển khai cụ thể | Resource metadata/nhãn hệ thống tùy backend | `service.instance.id=...` |
| Route HTTP dạng template | Low-cardinality tag của HTTP observation | `uri=/orders/{id}` |
| URL chứa ID thật | Không dùng làm metric tag/name | `/orders/101` |

Micrometer Observation dùng **low-cardinality key-values** cho metrics và traces. High-cardinality key-values phù hợp hơn với tracing vì chúng không được đưa vào meter tags mặc định; tuy vậy chúng **không tự động an toàn**. Cần kiểm soát dữ liệu nhạy cảm, retention và chi phí backend.

Cần làm rõ: **high-cardinality attribute không phải cách chữa việc dùng dữ liệu nhạy cảm**. Nếu không có nhu cầu điều tra hợp lệ, đừng thu thập ID cụ thể.

### 5.1 Không nhúng nhãn vào tên

Sai:

```java
String name = "checkout.authorize." + paymentMethod + "." + region;
```

Đúng hơn:

```java
Observation.createNotStarted("checkout.authorize", registry)
        .lowCardinalityKeyValue("payment.method", methodTag)
        .lowCardinalityKeyValue("region", regionTag)
        .observe(this::authorizePayment);
```

Ở đây `methodTag` và `regionTag` phải được chuẩn hóa về một tập giá trị có giới hạn. Nếu `region` nhận một chuỗi tùy ý từ request, nó cũng có thể tạo cardinality quá cao dù đã tách khỏi tên.

## 6. Ví dụ Spring Boot: dùng tên cố định trong service

Giả sử hệ thống cần đo thời gian xác thực thanh toán ở service nghiệp vụ. Chỉ cần inject `ObservationRegistry` đã được Spring Boot/Actuator cấu hình. Ví dụ Java 17+:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CheckoutApplicationService {
    private static final Logger log =
            LoggerFactory.getLogger(CheckoutApplicationService.class);

    // Một hằng số cho một loại hoạt động nghiệp vụ.
    public static final String AUTHORIZE_OBSERVATION = "checkout.authorize";

    private final ObservationRegistry observations;
    private final PaymentGateway gateway;

    public CheckoutApplicationService(ObservationRegistry observations,
                                      PaymentGateway gateway) {
        this.observations = observations;
        this.gateway = gateway;
    }

    public boolean authorize(PaymentChannel channel, PaymentCommand command) {
        // Enum bảo đảm tập giá trị tag hữu hạn.
        String channelTag = switch (channel) {
            case WEB -> "web";
            case MOBILE -> "mobile";
            case PARTNER -> "partner";
        };

        Observation observation = Observation
                .createNotStarted(AUTHORIZE_OBSERVATION, observations)
                .contextualName("authorize checkout")
                .lowCardinalityKeyValue("channel", channelTag);

        return observation.observe(() -> {
            boolean approved = gateway.authorize(command);
            if (!approved) {
                log.info("Payment authorization declined; channel={}",
                         channelTag);
            }
            return approved;
        });
    }
}

// Các kiểu nghiệp vụ cần được triển khai/bổ sung trong ứng dụng thực tế.
enum PaymentChannel { WEB, MOBILE, PARTNER }

record PaymentCommand(String orderReference) {}

interface PaymentGateway {
    boolean authorize(PaymentCommand command);
}
```

Mã ví dụ mô tả cách instrument service; để chạy thành ứng dụng Spring Boot, cần có bean triển khai `PaymentGateway` và một thành phần gọi phương thức `authorize(...)`. Không nhất thiết phải tạo controller chỉ để đo observation.

Các điểm quan trọng:

- Hằng số `AUTHORIZE_OBSERVATION` **không phụ thuộc** `channel`, `orderReference`, thread hay HTTP request.
- `contextualName("authorize checkout")` cho tên span dễ hiểu nhưng vẫn không chứa ID cụ thể.
- `channel` có đúng ba giá trị được định nghĩa bởi enum.
- `PaymentCommand.orderReference` là dữ kiện nghiệp vụ, **không được đưa vào tên observation** và cũng không cần log trong ví dụ.
- `observation.observe(...)` quản lý start, mở scope, ghi nhận exception được ném ra, đóng scope và stop. Nếu callback ném exception, handler có thể ghi error trong metric/span theo cấu hình.
- Trường hợp provider từ chối thanh toán nhưng trả kết quả `false` **không nhất thiết là exception**. Nếu cần đo tỷ lệ từ chối theo nghiệp vụ, thiết kế thêm kết quả `outcome` với tập giá trị hữu hạn hoặc một counter nghiệp vụ; không đổi tên thành `checkout.authorize.declined` mỗi lần bị từ chối.

Spring Boot sử dụng Micrometer Observation để kết nối các phép đo metrics/traces. Muốn thấy timer trên `/actuator/metrics` cần Actuator và meter handler tương ứng; muốn thấy trace phải bổ sung tracing implementation, exporter và backend phù hợp. Một `ObservationRegistry` tồn tại không bảo đảm mọi tín hiệu tự xuất hiện ở hệ thống giám sát.

### 6.1 Dependency tối thiểu để kiểm tra metrics

Nếu dự án đã dùng Spring Boot dependency management phù hợp với phiên bản và chỉ muốn kiểm tra custom metrics:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Đối với Spring Boot 3.x và 4.x, tên starter/tracing dependency có thể khác. Ví dụ ở đây chỉ thêm Actuator và Prometheus registry; cách tích hợp tracing/exporter cần chọn theo **phiên bản đang dùng**.

Cấu hình dành cho môi trường học tập:

```yaml
spring:
  application:
    name: checkout-service

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
```

Chỉ mở những endpoint cần thiết trong môi trường tin cậy. Ở production, bảo vệ management endpoints bằng giới hạn mạng và cơ chế phân quyền thích hợp.

### 6.2 Quan sát kết quả

Sau khi gọi `authorize(...)` qua ứng dụng:

```bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/checkout.authorize
curl "http://localhost:8080/actuator/metrics/checkout.authorize?tag=channel:web"
curl http://localhost:8080/actuator/prometheus
```

Nếu meter handler hoạt động, tên ở endpoint `metrics` thường là `checkout.authorize`. Các phép gọi với channel khác nhau cùng đóng góp vào **một loại meter**, phân chia bằng tag `channel`. Hãy xác minh kết quả `COUNT` và `TOTAL_TIME`, đồng thời tìm các series được chuyển đổi trong Prometheus output.

Ví dụ PromQL nếu Prometheus registry xuất tên dạng `checkout_authorize_seconds_count`:

```promql
# Số lần xác thực thanh toán mỗi giây theo kênh
sum by (channel) (
  rate(checkout_authorize_seconds_count[5m])
)

# Thời gian trung bình (giây) của các lần xử lý trong cửa sổ 5 phút
sum(rate(checkout_authorize_seconds_sum[5m]))
/
sum(rate(checkout_authorize_seconds_count[5m]))
```

Chỉ dùng tên truy vấn minh họa sau khi đã kiểm tra tên thực tế của exporter. Khi cần p95 trên Prometheus, phải bật các histogram buckets phù hợp và dùng `histogram_quantile`; chỉ có `_sum` và `_count` chưa đủ để dựng phân phối p95.

## 7. Dùng ObservationConvention khi nhiều nơi cùng tạo observation

Một string literal trong một service nhỏ có thể đủ. Tuy nhiên, nếu cùng nghiệp vụ được instrument ở nhiều class hoặc thư viện dùng chung, tên và tag dễ bị lệch:

```text
checkout.authorize
checkout.authorization
checkout.authorise
payment.authorize
```

Khi những điểm instrument thực sự cùng đo một loại công việc, nên thống nhất chúng trong một **ObservationConvention**. Nó tách cách đặt tên/metadata khỏi logic start/stop.

Micrometer hỗ trợ `ObservationConvention<T extends Observation.Context>`. Một context riêng chứa metadata về hoạt động, còn convention khai báo tên chuẩn và các key-values.

Ví dụ độc lập (Java 17+):

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;
import io.micrometer.observation.ObservationRegistry;

final class AuthorizationContext extends Observation.Context {
    private final String channel;

    AuthorizationContext(String channel) {
        this.channel = channel;
    }

    String channel() {
        return channel;
    }
}

final class AuthorizationObservationConvention
        implements ObservationConvention<AuthorizationContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof AuthorizationContext;
    }

    @Override
    public String getName() {
        return "checkout.authorize";    // Hợp đồng metric ổn định.
    }

    @Override
    public String getContextualName(AuthorizationContext context) {
        return "authorize checkout";   // Tên span dễ đọc và ổn định.
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(AuthorizationContext context) {
        return KeyValues.of(
                KeyValue.of("channel", context.channel())
        );
    }
}

final class AuthorizationInstrumenter {
    private static final AuthorizationObservationConvention CONVENTION =
            new AuthorizationObservationConvention();

    private final ObservationRegistry registry;

    AuthorizationInstrumenter(ObservationRegistry registry) {
        this.registry = registry;
    }

    void record(String normalizedChannel, Runnable task) {
        AuthorizationContext context =
                new AuthorizationContext(normalizedChannel);

        Observation.createNotStarted(CONVENTION, () -> context, registry)
                .observe(task);
    }
}
```

`normalizedChannel` phải đến từ tập giá trị đã được chuẩn hóa trước khi đi vào context. Trong dự án thực, có thể đưa convention và instrumenter thành các thành phần dùng chung của module nghiệp vụ, hoặc xây dựng `ObservationDocumentation` để định nghĩa hợp đồng đầy đủ và sinh tài liệu.

**Khi nào cần convention?**

- Khi nhiều lời gọi cần dùng đúng cùng tên và tập tag.
- Khi cần thay đổi các nhãn mà không chỉnh logic nghiệp vụ ở mọi nơi.
- Khi thư viện/module muốn cung cấp default convention và cho phép ứng dụng tùy biến.
- Khi cần thống nhất hợp đồng với đội vận hành và tài liệu hóa nó.

**Khi nào chưa cần?** Nếu chỉ có một observation đơn giản, dùng hằng số tên và `createNotStarted(...)` có thể rõ ràng hơn. Đừng thêm abstraction chỉ để tránh viết một literal một lần.

### 7.1 Global convention, filter và predicate khác gì nhau?

| Công cụ | Nhiệm vụ | Liên quan tới tên ổn định |
|---|---|---|
| `ObservationConvention` | Định nghĩa tên, contextual name và key-values cho loại context cụ thể. | Nơi tốt để kiểm soát hợp đồng tên theo loại công việc. |
| `GlobalObservationConvention` | Áp dụng convention cho các context hỗ trợ trong registry khi không có convention tùy chọn ưu tiên hơn. | Cần kiểm soát `supportsContext` và phạm vi áp dụng, tránh đổi tên observation ngoài ý muốn. |
| `ObservationFilter` | Có thể sửa `Observation.Context`, như thêm/bớt key-values, trước `onStop`. | Hữu ích cho metadata chung; không phải lựa chọn mặc định để tổ chức toàn bộ naming nghiệp vụ. |
| `ObservationPredicate` | Quyết định một observation có được tạo/ghi nhận hay trở thành no-op hay không. | Có thể lọc theo tên; tên động dễ làm quy tắc lọc kém nhất quán. |
| `ObservationDocumentation` | Mô tả các observation, convention và key names thuộc một miền. | Giúp công khai hợp đồng tên/tag cho nhiều service và hỗ trợ sinh tài liệu. |

Các thành phần này **không có cùng vai trò**. Đặc biệt, `ObservationFilter` có thể sửa tên trong context nhưng chạy ở giai đoạn khác với predicate và callback start; không nên coi việc đổi tên tại thời điểm stop là thay thế đầy đủ cho convention được thiết kế từ đầu.

## 8. Phân biệt Observation name với tracing span name

Một trace mô tả nhiều hoạt động:

```text
traceId = T
└─ span "POST /checkout" (HTTP server)
   ├─ span "authorize checkout"
   └─ span "reserve inventory"
```

Trong mã, các span nghiệp vụ có thể xuất phát từ:

```text
checkout.authorize -> contextualName = "authorize checkout"
inventory.reserve  -> contextualName = "reserve inventory"
```

Tại tầng tracing, **span name** dùng để nhóm và tra cứu các loại hoạt động. Giữ nó ngắn, dễ hiểu và ổn định cũng quan trọng, nhưng tên span **không nhất thiết trùng** với tên metric timer. Điều đó phụ thuộc convention và tracing handler.

Không làm thế này:

```java
observation.contextualName("authorize order " + orderId);
```

Một span riêng đã có trace ID và span ID. Nếu có nhu cầu hợp lệ để đối chiếu một đơn hàng, xem xét thêm attribute có kiểm soát hoặc correlation context ở logs. Đưa ID vào tên span thường làm backend khó thống kê theo operation, đồng thời tiềm ẩn rủi ro bảo mật.

### 8.1 Tên ổn định không tự bảo đảm trace liên dịch vụ

Dù Order Service và Payment Service cùng đặt tên nhất quán, trace liên dịch vụ vẫn cần **context propagation**. HTTP client được Spring quản lý và tracing instrumentation phù hợp sẽ truyền trace context qua header. Với `@Async`, custom executor hoặc reactive pipeline, cần cấu hình propagation tương ứng.

Khi propagation đứt, hai span có thể mang tên rất tốt nhưng thuộc **hai trace ID khác nhau**. Ngược lại, khi sampling bỏ qua một trace, metrics cùng tên vẫn có thể được ghi. Đừng nhầm việc không thấy trace với việc observation không chạy.

## 9. Tên observation trong auto-instrumentation Spring Boot

Spring Framework đã có nhiều observation name được công bố, ví dụ:

| Hoạt động | Tên thông dụng trong convention Micrometer | Nên làm gì? |
|---|---|---|
| Request vào Spring MVC/WebFlux | `http.server.requests` | Giữ convention mặc định nếu không có lý do tích hợp phải đổi. |
| HTTP client như `RestClient` hoặc `WebClient` | `http.client.requests` | Dùng Spring-managed builder để nhận auto-instrumentation khi phù hợp. |
| Thực thi `@Scheduled` | `tasks.scheduled.execution` | Kiểm tra stack/phiên bản để biết instrumentation được bật. |
| Nghiệp vụ riêng của ứng dụng | `checkout.authorize`, `inventory.reserve` | Tạo custom observation với tên ổn định, tag phù hợp. |

Tên của instrumentation framework có thể đổi khi ứng dụng chọn **OpenTelemetry semantic conventions** thay vì Micrometer conventions. Spring Boot phiên bản mới hỗ trợ chọn bộ convention qua cấu hình; khi đổi bộ convention phải coi đó là một thay đổi có tác động đến dashboard và alerts, kể cả khi không đổi mã nghiệp vụ.

**Đừng tự đặt một custom observation trùng `http.server.requests`** để đo một thao tác nghiệp vụ. Hai phép đo có semantics khác nhau sẽ bị trộn lẫn dưới cùng một tên và gây khó diễn giải.

### 9.1 Dùng `@Observed`: tên vẫn cần được thiết kế

Micrometer hỗ trợ annotation dạng:

```java
@Observed(name = "checkout.authorize", contextualName = "authorize checkout")
public void authorizeCheckout() {
    // ...
}
```

Để annotation hoạt động với Spring Boot, cần cấu hình annotation scanning/AOP và dependency hỗ trợ tương ứng với phiên bản. Spring Boot 4.x có thuộc tính `management.observations.annotations.enabled=true` và tích hợp AspectJ thích hợp.

Đoạn mã chỉ minh họa naming; không tự giả định annotation sẽ được kích hoạt trong mọi dự án. Cần tránh instrument **trùng** một controller hoặc method đã được Spring Framework tự đo. Với những đoạn nghiệp vụ nhỏ, direct `Observation` API có thể dễ kiểm soát hơn.

Nếu đổi tên phương thức Java `authorizeCheckout` thành `execute`, giá trị `name` cố định của annotation vẫn giữ hợp đồng. Dựa hoàn toàn vào tên class/method được suy ra ngầm có thể khiến telemetry thay đổi ngoài ý muốn trong một lần refactor.

## 10. Đổi tên observation: coi là thay đổi giao diện telemetry

Giả sử đội muốn đổi `checkout.process` thành `checkout.authorize` vì tên cũ quá rộng. Dù logic nghiệp vụ không đổi, thay đổi này có thể làm:

- Series Prometheus mới xuất hiện, trong khi series cũ ngừng có dữ liệu.
- Dashboard tìm `checkout_process_seconds_count` trả về 0 dữ liệu mới.
- Alert và SLO theo tên cũ mất tín hiệu hoặc báo sai.
- Truy vấn trace operation name không còn khớp khi contextual name cũng đổi.
- Quy tắc filter, sampling hoặc retention theo observation name cần cập nhật.
- Runbook, tài liệu và tests phụ thuộc tên cũ trở nên lỗi thời.

Để đổi tên có kiểm soát:

1. **Xác định lý do và ngữ nghĩa**: chỉ đổi khi tên cũ thực sự gây nhầm lẫn, hoặc ranh giới đo đã khác.
2. **Liệt kê nơi tiêu thụ**: dashboard, alert, recording rules, SLO, reports, trace queries, saved searches, tài liệu, phép kiểm thử, cấu hình filtering.
3. **Định nghĩa hợp đồng mới**: tên mới, key/value set, khoảng đo, owner và ngày áp dụng.
4. **Cập nhật consumer trước hoặc cùng với rollout**: dùng truy vấn tạm hỗ trợ cả tên cũ và tên mới, nhưng phải **tránh cộng trùng** nếu cùng một lần xử lý bị đo hai lần.
5. **Triển khai và quan sát**: kiểm tra tên mới có dữ liệu, tên cũ giảm theo lộ trình và alert vẫn phản ánh sự cố.
6. **Kết thúc chuyển đổi**: sau khi toàn bộ service đã chuyển và retention lịch sử phù hợp, loại bỏ truy vấn/alert cũ.

Ví dụ truy vấn tương thích giai đoạn rollout (minh họa):

```promql
# Chỉ sử dụng cách cộng hai tên khi mỗi sự kiện được ghi bởi đúng
# một trong hai instrumentation, tránh đếm cùng request hai lần.
sum(rate(checkout_process_seconds_count[5m]))
+
sum(rate(checkout_authorize_seconds_count[5m]))
```

Nếu một phiên bản code tạm thời tạo **hai Observation cho cùng một lần gọi**, việc cộng này sẽ nhân đôi traffic. Trong thực tế nên ưu tiên **chuyển nguồn metric theo deployment, rồi cập nhật consumer có kiểm soát**, thay vì nhân đôi instrumentation tràn lan.

### 10.1 Đổi tên không phải lúc nào cũng cần thiết

Nếu chỉ muốn tách kết quả `approved` và `declined`, phần lớn trường hợp bạn nên **thêm tag `outcome` hữu hạn** hoặc metric nghiệp vụ riêng, thay vì đổi tên thành `checkout.authorize.approved` và `checkout.authorize.declined`.

Nhưng nếu trước đây `checkout.process` đo toàn bộ checkout, còn giờ chỉ đo lệnh gọi provider, ranh giới đã thay đổi đáng kể; một tên mới có thể cần thiết để giữ tính trung thực của số liệu lịch sử.

## 11. Kịch bản điều tra lỗi do đặt tên không ổn định

**Tình huống:** Sau đợt triển khai, dashboard “checkout latency” không còn dữ liệu, trong khi ứng dụng vẫn xử lý thành công.

Các bước kiểm tra:

1. **Xem output ứng dụng**: gọi `/actuator/metrics`, tìm những tên gần `checkout`. Nếu xuất hiện nhiều `checkout.authorize.<id>` thay vì một `checkout.authorize`, nguồn sai nằm ở instrumentation.
2. **Xem Prometheus exposition**: tìm series `checkout_authorize_seconds_*`. Nếu tên registry thay đổi do exporter hoặc semantic convention, kiểm tra quy tắc chuyển đổi.
3. **Đối chiếu trước/sau deployment**: xem diff về tên observation, `ObservationConvention`, annotation và các property liên quan.
4. **Kiểm tra tags**: ngay cả khi tên giống nhau, tag key `payment.method` đổi thành `method` cũng có thể làm PromQL cũ không còn khớp.
5. **Xem traces**: nếu contextual name đổi hoặc span names chứa ID, giao diện tracing có thể phân mảnh theo operation; kiểm tra trace ID và thời gian thực tế để loại trừ lỗi propagation/sampling.
6. **Xác nhận phục hồi**: đo tiếp lưu lượng thực tế, kiểm tra count/rate, latency, alert và tỷ lệ lỗi sau khi sửa; đừng chỉ kiểm tra dashboard “có đường” là đủ.

Một ngộ nhận phổ biến là “Prometheus bị lỗi” khi truy vấn cũ trở nên trống. Cần phân biệt **không có traffic**, **scrape bị lỗi**, **meter chưa được tạo**, **tên thay đổi** và **bộ lọc label không khớp** bằng dữ kiện độc lập.

## 12. Bảo đảm tính ổn định bằng kiểm thử

Với naming, kiểm thử có giá trị nhất là kiểm tra **hợp đồng quan sát được**, không chỉ tìm một literal trong source.

### 12.1 Ví dụ kiểm tra timer qua `SimpleMeterRegistry`

Đoạn mã độc lập dưới đây kiểm tra **cùng một tên meter** được dùng cho hai kênh. Nó chạy với Micrometer core + observation; không cần backend Prometheus hoặc Zipkin.

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;

public class ObservationNamingCheck {
    public static void main(String[] args) {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();

        observations.observationConfig()
                .observationHandler(
                        DefaultMeterObservationHandler.builder(meters).build());

        Observation.createNotStarted("checkout.authorize", observations)
                .lowCardinalityKeyValue("channel", "web")
                .observe(() -> {});

        Observation.createNotStarted("checkout.authorize", observations)
                .lowCardinalityKeyValue("channel", "mobile")
                .observe(() -> {});

        long webCount = meters.get("checkout.authorize")
                .tag("channel", "web")
                .timer()
                .count();

        long mobileCount = meters.get("checkout.authorize")
                .tag("channel", "mobile")
                .timer()
                .count();

        if (webCount != 1 || mobileCount != 1) {
            throw new AssertionError("Unexpected observation counts");
        }

        System.out.println("Stable name verified for both channels");
        meters.close();
    }
}
```

Tùy phiên bản Micrometer, vị trí lớp `DefaultMeterObservationHandler` và builder API cần đối chiếu với dependency đã khóa của dự án; ví dụ trên dùng API được mô tả trong Micrometer Observation hiện hành. Trong code thật, bỏ import không sử dụng và chuyển đoạn xác minh thành unit test thích hợp.

**Điều cần xác minh:**

- Hai lần gọi dùng **một tên chuẩn** `checkout.authorize`, với hai giá trị tag.
- Không có meter `checkout.authorize.web` hoặc `checkout.authorize.mobile`.
- Timer chỉ ghi dữ liệu sau khi observation kết thúc.
- Khi có tracing, tên span không thay đổi theo ID hoặc input tùy ý.

### 12.2 Kiểm tra ở mức ứng dụng

Với ứng dụng Spring Boot chạy local và đã phát sinh request:

```bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/checkout.authorize
curl http://localhost:8080/actuator/prometheus
```

Có thể bổ sung phép kiểm thử/CI:

- Chạy cùng nghiệp vụ với nhiều input khác nhau và xác nhận tập **observation names vẫn cố định**.
- Đối chiếu danh sách tên/tag với contract đã công bố.
- Giới hạn số giá trị của các tag thuộc nhóm `low-cardinality`.
- Kiểm thử khi đổi `ObservationConvention` hoặc semantic convention.
- Kiểm tra không tạo trùng observation ở ranh giới đã có auto-instrumentation.

**Đừng kiểm thử sai mục tiêu:** một test tìm chuỗi `"checkout.authorize"` trong code không phát hiện được việc production lại xây tên động ở một call site khác. Nên kiểm tra dữ liệu mà registry thực tế nhận được.

## 13. Những lỗi phổ biến về naming

| Biểu hiện | Nguyên nhân | Cách sửa |
|---|---|---|
| Mỗi request có một metric name mới | Ghép request ID/order ID vào name | Dùng tên cố định; đưa chi tiết hợp lệ sang trace attribute/log. |
| Một nghiệp vụ xuất hiện dưới nhiều tên gần giống | Các team đặt tên độc lập | Công bố contract chung; dùng hằng số hoặc `ObservationConvention`. |
| Dashboard trống sau refactor | Tên phụ thuộc class/method hoặc đã đổi convention | Kiểm tra tên cũ/mới và cập nhật consumer theo migration. |
| Traces có hàng nghìn operation names | Dùng ID/URL thực tế làm `contextualName` | Tên span cố định; trace ID và attributes phục vụ tra cứu lần gọi. |
| PromQL sai tên dù `/actuator/metrics` có dữ liệu | Backend đổi dấu chấm, đơn vị hoặc hậu tố | Xem output exporter; viết query theo metric name thực tế. |
| Metric vẫn có tên cũ dù một số code đã đổi | Còn call site khác hoặc worker phiên bản cũ | Tìm các nơi phát sinh, kiểm tra rollout và trách nhiệm owner. |
| Trùng số lần ghi metric | Instrument hai lần cùng một hoạt động | Chọn đúng một ranh giới; kiểm tra auto-instrumentation và custom instrumentation. |
| Tổng traffic bị méo sau rename | Cộng hai metric đo trùng dữ kiện | Chuyển đổi theo phiên bản/time window; tránh double counting. |
| Tên ổn định nhưng cardinality vẫn bùng nổ | Tag `userId`/`orderId` hoặc URL cụ thể | Giới hạn low-cardinality tags và dùng route template. |
| Metrics ổn nhưng trace không liên kết | Thiếu propagation, tracing/exporter/sampling | Kiểm tra trace context, scope và pipeline tracing. |
| Cùng tên đo hai khoảng thời gian khác nhau | Ranh giới nghiệp vụ thay đổi mà không cập nhật contract | Đánh giá rename/migration và tài liệu hóa semantics. |

## 14. Checklist thiết kế và review code

Trước khi chấp nhận một custom observation mới, tự trả lời:

- **Tên có mô tả loại hoạt động?** Ví dụ `checkout.authorize` rõ hơn `execute`.
- **Tên có thay đổi theo request, instance, môi trường hoặc dữ liệu người dùng không?** Nếu có, cần sửa.
- **Tên có đúng lowercase dot notation hoặc convention đã chọn không?**
- **Hai lần thực thi cùng loại có dùng cùng tên?** Những hoạt động khác ngữ nghĩa có bị gộp sai vào một tên không?
- **Tên contextual dành cho span có chứa ID, URL thật hoặc secret không?**
- **Các tag metrics có tập giá trị nhỏ và được chuẩn hóa không?** Có tag nào thực ra nên là trace attribute hoặc bị loại bỏ?
- **Đã biết ranh giới start/stop của observation?** Khi thay đổi ranh giới, số liệu lịch sử có còn so sánh được không?
- **Có auto-instrumentation tương đương chưa?** Nếu đã có, tránh đo trùng.
- **Tên/tag được ai sử dụng?** Dashboard, alert, SLO, truy vấn tracing và runbook đã được liệt kê chưa?
- **Có cách kiểm tra thực tế?** `/actuator/metrics`, Prometheus exporter hoặc test registry có xác nhận đúng tên không?

Nếu áp dụng naming contract ngay từ đầu, một service có thể thay đổi code, thêm exporter, bật tracing hay đổi môi trường chạy mà vẫn giữ đường truy vấn vận hành nhất quán.

## 15. Bài tập thực hành

### Bài 1: Chọn tên đúng

Trong ba cách đặt tên cho một lần giữ hàng, hãy chọn phương án phù hợp nhất:

```text
A. inventory.reserve.8ea4c01b
B. inventory.reserve
C. inventory.reserve.prod.pod-17
```

Giải thích vì sao hai cách còn lại gây rủi ro. Hãy đề xuất vị trí lưu kết quả `success/rejected` và mã đơn hàng khi thật sự cần tra cứu.

### Bài 2: Refactor telemetry sai

Đoạn mã sau có lỗi naming nào?

```java
String observationName = "payment." + customerId + "." + Instant.now();

Observation.createNotStarted(observationName, registry)
        .observe(() -> paymentGateway.authorize(command));
```

Viết lại với tên cố định, contextual name ổn định và `payment.method` đã được chuẩn hóa. Không đưa `customerId` vào metric tag.

### Bài 3: Điều tra dashboard mất dữ liệu

Sau deploy, `checkout_process_seconds_count` không còn tăng, nhưng `/actuator/metrics` có `checkout.authorize`. Hãy nêu các bước để tìm nguyên nhân và lập lộ trình chuyển dashboard/alert sang tên mới mà không đếm trùng.

### Bài 4: Cùng tên nhưng ngữ nghĩa khác

Trước đây `report.generate` đo toàn bộ thời gian tạo báo cáo; bây giờ tên ấy đo riêng bước lấy dữ liệu. Bạn nên giữ nguyên tên hay tạo tên mới? Vì sao việc bảo toàn chuỗi ký tự chưa đủ?

### Bài 5: Kiểm soát cardinality

Một service có một tên `order.submit` với các tag `channel` (3 giá trị), `status` (4 giá trị), `country` (10 giá trị), `orderId` (100.000 giá trị). Hãy ước lượng giới hạn tổ hợp và đề xuất cách sửa. Có thể giữ `country` không? Cần căn cứ vào chính sách dữ liệu và nhu cầu truy vấn nào?

**Gợi ý đáp án:** Bài 1 chọn B; outcome có thể là low-cardinality tag/counter nghiệp vụ, ID chỉ vào trace/log khi được phép. Bài 2 tên cố định `payment.authorize`. Bài 3 rà soát rename và cập nhật consumer trước/trong rollout. Bài 4 nên đánh giá tên mới vì semantics đã đổi. Bài 5 tối đa 3 × 4 × 10 × 100.000 = 12.000.000 tổ hợp tiềm năng; bỏ `orderId` khỏi tag metric và xem xét có thực sự cần chiều `country` hay không.

## 16. Tài liệu tham khảo chính thức

- [Micrometer — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html): lowercase dot notation, quy tắc đổi tên theo backend và an toàn cardinality.
- [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): vòng đời observation, name, low/high-cardinality key-values và `ObservationRegistry`.
- [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): `ObservationConvention`, `ObservationDocumentation`, handler, filter và predicate.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): ví dụ custom observation, common key-values, annotation instrumentation và context propagation.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metric names và HTTP observation conventions.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): tên observation mặc định như `http.server.requests` và cách tùy biến convention.
- [Micrometer Tracing — Configuring with Observation](https://docs.micrometer.io/tracing/reference/configuring.html): contextual name, span creation, low/high cardinality khi tracing.
- [Prometheus — Naming](https://prometheus.io/docs/practices/naming/): quy ước tên và đơn vị cho metric ở Prometheus.

**Ghi nhớ:** **Tên observation là tên của một loại công việc, không phải danh tính của một lần thực thi.** Hãy thiết kế tên ổn định và có nghĩa, giữ đúng ngữ nghĩa của ranh giới đo, dùng low-cardinality tag cho các nhóm hữu hạn, dùng trace context/attribute phù hợp để điều tra từng lần chạy, và coi việc đổi tên là một thay đổi hợp đồng telemetry cần kiểm tra tác động đến metrics, logs và traces.
