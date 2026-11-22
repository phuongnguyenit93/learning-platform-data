# Giới hạn số lượng giá trị nhãn và tránh đưa định danh người dùng vào metric

## Mục tiêu

Metric giúp trả lời các câu hỏi vận hành như: hệ thống xử lý bao nhiêu message mỗi giây, tỷ lệ lỗi tăng hay giảm, độ trễ của handler thay đổi thế nào và channel nào đang bị nghẽn. Để phân tích, metric thường có các nhãn (label hoặc tag) như destination, protocol, outcome và region.

Mỗi tổ hợp tên metric cùng các cặp nhãn tạo ra một time series riêng. Nếu đưa userId, email, sessionId hoặc requestId vào nhãn, số time series có thể tăng theo số người dùng hoặc số request. Hệ quả là bộ nhớ, CPU, dung lượng lưu trữ và chi phí truy vấn của hệ thống monitoring tăng nhanh; dashboard và alert cũng khó tổng hợp hơn.

Bài này giải thích cardinality, cách thiết kế nhãn có tập giá trị hữu hạn, cách xử lý định danh người dùng trong metrics và cách dùng Micrometer Observation/MeterFilter để giữ cardinality trong giới hạn.

Sau bài này, bạn có thể:

- Giải thích cardinality và mối quan hệ giữa nhãn với time series.
- Ước tính số series từ các chiều dữ liệu của một metric.
- Nhận diện các nhãn có nguy cơ tăng không giới hạn.
- Chọn giá trị thay thế có ý nghĩa như route template, enum, nhóm trạng thái hoặc nhóm lỗi.
- Phân biệt low-cardinality và high-cardinality key values trong Micrometer Observation.
- Dùng MeterFilter để đặt giới hạn bảo vệ cho MeterRegistry.
- Chuyển dữ liệu định danh sang log hoặc trace có kiểm soát và kiểm thử schema metric.

## 1. Cardinality là gì?

Cardinality là số lượng giá trị khác nhau mà một chiều dữ liệu có thể nhận. Với metric, cần quan tâm đến hai cấp:

- **Cardinality của một nhãn**: số giá trị khác nhau của một tag key, ví dụ outcome có ba giá trị success, rejected và error.
- **Cardinality của một metric**: số tổ hợp labelset khác nhau của tất cả tag keys trên cùng tên metric. Mỗi tổ hợp đã xuất hiện tạo thành một time series.

Ví dụ metric messaging.messages.total có hai nhãn:

~~~text
destination = orders.create | orders.cancel
outcome     = success | rejected | error
~~~

Tối đa có:

~~~text
2 destination × 3 outcome = 6 time series
~~~

Mỗi khi có một tổ hợp mới, hệ thống monitoring phải lưu thêm một series. Giá trị counter của từng series tăng theo thời gian, nhưng mỗi labelset vẫn là một chuỗi dữ liệu độc lập.

Một cách tính tổng quát:

~~~text
Số series tối đa của một metric
    ≈ số giá trị khác nhau của tag 1
      × số giá trị khác nhau của tag 2
      × ...
      × số giá trị khác nhau của tag N
~~~

Đây là giới hạn trên khi mọi tổ hợp đều xuất hiện. Số series thực tế có thể thấp hơn nếu một số tổ hợp không xảy ra. Các nhãn do backend thêm như job, instance, pod hoặc region cũng làm tăng tổng số series trên toàn hệ thống.

## 2. Vì sao cardinality tăng nhanh?

### 2.1. Nhãn có tập giá trị không giới hạn

Các giá trị như status, protocol hoặc operation thường có tập lựa chọn nhỏ. Ngược lại, định danh của từng người dùng hoặc từng request có thể tạo ra giá trị mới liên tục.

| Tag key | Ví dụ giá trị | Đánh giá |
|---|---|---|
| protocol | rsocket, stomp | Thường thấp |
| outcome | success, rejected, error | Thấp |
| error_category | connection, protocol, conversion, business, other | Thấp nếu dùng enum cố định |
| destination | orders.create, orders.cancel | Thấp nếu route được giới hạn |
| region | ap-southeast-1, eu-west-1 | Có thể kiểm soát nếu danh sách region hữu hạn |
| user_id | u-10001, u-10002, ... | Cao, tăng theo số người dùng |
| email | a@example.com, b@example.com | Cao và chứa dữ liệu cá nhân |
| request_id | UUID cho từng request | Gần như mỗi request một giá trị |
| session_id | UUID cho từng phiên | Cao, thay đổi theo phiên |
| trace_id | Trace ID duy nhất | Cao |
| order_id | ID của từng đơn hàng | Cao |
| exception_message | Nội dung exception tự do | Cao, khó dự đoán |
| raw_url | /orders/10001, /orders/10002 | Cao nếu chứa ID động |

Không chỉ định danh người dùng mới nguy hiểm. Bất kỳ giá trị nào được tạo từ dữ liệu tự do hoặc ID duy nhất đều có thể làm cardinality tăng: SQL query, tên file, URL đầy đủ, IP, mã giao dịch, chuỗi lỗi và header tùy ý.

### 2.2. Hiệu ứng nhân giữa các nhãn

Giả sử một metric messaging có:

- 4 destination.
- 2 protocol.
- 3 outcome.
- 3 region.

Số tổ hợp tối đa là:

~~~text
4 × 2 × 3 × 3 = 72 series
~~~

Nếu thêm user_id có 100.000 giá trị khác nhau, giới hạn trên trở thành:

~~~text
72 × 100.000 = 7.200.000 series
~~~

Chỉ thêm một nhãn đã biến một metric dễ kiểm soát thành hàng triệu series. Nếu metric là histogram, mỗi labelset còn tạo thêm các series cho bucket, sum và count; chi phí có thể tăng tiếp.

Không nên đánh giá tag chỉ bằng số lượng giá trị hiện tại trong môi trường dev. Một tag có 20 giá trị hôm nay nhưng được lấy từ user ID, request ID hoặc tenant ID vẫn có thể tăng lên hàng trăm nghìn khi tải thật tăng.

### 2.3. Tác động tới hệ thống

Cardinality cao gây ra nhiều chi phí:

- **Bộ nhớ và CPU**: mỗi series cần metadata, trạng thái và thao tác cập nhật riêng.
- **Dung lượng lưu trữ**: mỗi series có các sample theo thời gian; nhiều series làm tăng dung lượng và chi phí retention.
- **Truy vấn chậm**: PromQL hoặc truy vấn tương đương phải xử lý nhiều series hơn.
- **Dashboard khó đọc**: một biểu đồ bị chia thành quá nhiều đường hoặc nhóm.
- **Alert khó quản lý**: rule có thể tạo nhiều alert instance, làm nhiễu cảnh báo.
- **Chi phí nền tảng**: dịch vụ monitoring tính phí theo series, sample hoặc dung lượng có thể tăng chi phí đáng kể.
- **Rủi ro dữ liệu cá nhân**: email, số điện thoại hoặc user ID có thể bị phát tán tới hệ thống metrics với quyền truy cập rộng hơn dự kiến.

Cardinality là vấn đề thiết kế instrumentation từ đầu. Khi đã xuất một metric có nhãn động, việc loại bỏ nhãn có thể cần thay đổi code, dashboard, alert và quy trình triển khai.

## 3. Nguyên tắc thiết kế nhãn có cardinality thấp

### 3.1. Dùng tập giá trị hữu hạn

Một tag tốt có tập giá trị đã biết hoặc có thể giới hạn bằng enum/allowlist.

Ví dụ phù hợp cho messaging:

| Tag key | Tập giá trị đề xuất |
|---|---|
| protocol | rsocket, stomp, jms, other |
| destination | orders.create, orders.cancel, notifications.send, other |
| outcome | success, rejected, error |
| error_category | connection, protocol, conversion, business, other |
| consumer_group | Tên nhóm consumer đã khai báo trong cấu hình |
| environment | local, test, staging, production |

Không lấy trực tiếp giá trị từ header client nếu không có kiểm soát. Client có thể gửi route, event type hoặc tenant name tùy ý. Hãy chuyển giá trị đầu vào thành một enum hoặc nhóm đã được server định nghĩa.

Ví dụ, thay vì ghi raw destination, hãy chuẩn hóa:

~~~java
enum MetricDestination {
    ORDERS_CREATE("orders.create"),
    ORDERS_CANCEL("orders.cancel"),
    NOTIFICATIONS_SEND("notifications.send"),
    OTHER("other");

    private final String tagValue;

    MetricDestination(String tagValue) {
        this.tagValue = tagValue;
    }

    String tagValue() {
        return tagValue;
    }

    static MetricDestination from(String destination) {
        return switch (destination) {
            case "orders.create" -> ORDERS_CREATE;
            case "orders.cancel" -> ORDERS_CANCEL;
            case "notifications.send" -> NOTIFICATIONS_SEND;
            default -> OTHER;
        };
    }
}
~~~

Route không được nhận diện sẽ được gom vào other. Nhờ đó, một client gửi destination bất thường không thể tạo thêm một time series cho mỗi giá trị.

### 3.2. Dùng route template thay cho URL đầy đủ

URL có ID động:

~~~text
/orders/12345
/orders/12346
/orders/12347
~~~

Nên chuẩn hóa thành route template:

~~~text
/orders/{orderId}
~~~

Trong messaging, dùng destination logic cố định như orders.find hoặc orders.update thay cho chuỗi ghép chứa orderId. Route template vẫn cho biết loại thao tác cần theo dõi nhưng không tạo series theo từng tài nguyên.

Không dùng raw URL, query string hoặc tên file trong metric. Nếu cần tìm request cụ thể, hãy dùng log hoặc trace.

### 3.3. Dùng nhóm lỗi thay cho exception message

Không nên dùng:

~~~java
counterBuilder.tag("exception", exception.getMessage());
~~~

Thông báo lỗi có thể chứa SQL, ID, tên file, URL hoặc nội dung đầu vào. Hai lần lỗi cùng loại cũng có thể tạo hai giá trị khác nhau.

Hãy phân loại vào tập hữu hạn:

~~~java
enum ErrorCategory {
    CONNECTION,
    PROTOCOL,
    CONVERSION,
    BUSINESS,
    OTHER
}
~~~

Nếu cần biết exception class cụ thể, có thể ghi trong log hoặc trace. Chỉ đưa exception class vào metric khi tập class được kiểm soát và có lý do phân tích rõ ràng; không đưa message tự do của exception vào tag.

### 3.4. Đặt ngân sách cardinality trước khi thêm tag

Trước khi thêm một tag, hãy trả lời:

1. Tag có bao nhiêu giá trị tối đa?
2. Giá trị có được tạo từ ID hoặc input tự do không?
3. Có thể gom nhóm thành enum hoặc template không?
4. Người trực vận hành có thực sự cần lọc metric theo chiều này không?
5. Tổ hợp của tag mới với các tag hiện có tạo ra bao nhiêu series?
6. Tag có chứa dữ liệu cá nhân, bí mật hoặc định danh nhạy cảm không?

Không có một ngưỡng chung phù hợp cho mọi backend. Prometheus đưa ra hướng dẫn thực hành giữ cardinality của phần lớn metric ở mức thấp; các metric có cardinality lớn hơn cần được xem xét kỹ và tìm cách giảm chiều dữ liệu. Các con số hướng dẫn không phải giới hạn kỹ thuật cứng của mọi hệ thống.

## 4. Không đưa định danh người dùng vào metric

### 4.1. Các định danh cần tránh

Không sử dụng các giá trị sau làm metric tag trong instrumentation thông thường:

- user_id, account_id, customer_id.
- Email, số điện thoại hoặc username.
- session_id, cookie hoặc access token.
- request_id, correlation_id, trace_id, message_id.
- order_id, payment_id, transaction ID.
- IP address hoặc URL chứa thông tin định danh.
- Tenant ID nếu số tenant lớn hoặc có thể tăng không giới hạn.

Một số hệ thống B2B có số tenant nhỏ, cố định và được quản trị. Trong trường hợp đặc biệt đó, tag tenant chỉ nên được dùng sau khi có ngân sách cardinality, kiểm soát quyền truy cập và lý do vận hành cụ thể. Không giả định tenant ID luôn có cardinality thấp.

### 4.2. Dùng metric để đo xu hướng, không để tra cứu từng người dùng

Metrics phù hợp với câu hỏi tổng hợp:

- Bao nhiêu message được xử lý trong một phút?
- Tỷ lệ thành công theo destination là bao nhiêu?
- Độ trễ p95 của handler orders.create là bao nhiêu?
- Nhóm lỗi connection hay conversion đang tăng?
- Consumer group nào có backlog hoặc processing time cao?

Metrics không phải cơ sở dữ liệu để trả lời trực tiếp:

- User nào tạo request này?
- Request UUID nào thất bại?
- Email nào bị từ chối?
- Đơn hàng cụ thể nào đang chờ xử lý?

Với câu hỏi theo từng thực thể, dùng log có cấu trúc, trace hoặc hệ thống lưu trữ nghiệp vụ phù hợp. Metrics giữ các chiều tổng hợp; log/trace giữ ngữ cảnh của một lần xử lý cụ thể.

### 4.3. Phân chia dữ liệu giữa metrics, logs và traces

| Loại dữ liệu | Nơi phù hợp | Ví dụ |
|---|---|---|
| Số lượng và xu hướng tổng hợp | Metrics | destination=orders.create, outcome=error |
| Chi tiết một sự kiện | Structured logs | messageId, requestId, userId nếu policy cho phép |
| Đường đi của một request qua nhiều service | Distributed traces | traceId, span ID, operation, các attribute cần điều tra |
| Trạng thái nghiệp vụ chính thức | Database hoặc event store | order ID, payment ID, trạng thái giao dịch |

Dữ liệu định danh trong log và trace vẫn cần chính sách bảo vệ. Không phải cứ chuyển một trường khỏi metric là có thể ghi nó ở mọi nơi. Cần cân nhắc mục đích sử dụng, phân quyền, che dữ liệu, retention, sampling và yêu cầu bảo vệ dữ liệu cá nhân.

Trace ID hoặc message ID có thể giúp nối các sự kiện liên quan. Chúng không nên trở thành metric label. Nếu backend hỗ trợ exemplars, một sample metric có thể liên kết tới trace đại diện mà không cần tạo một time series cho mỗi trace ID.

## 5. Low-cardinality và high-cardinality trong Micrometer Observation

Micrometer Observation phân biệt hai loại key value:

- **Low-cardinality key values**: tập giá trị nhỏ và có giới hạn; được đưa vào metrics và traces.
- **High-cardinality key values**: tập giá trị không giới hạn hoặc rất lớn; được đưa vào traces, không được dùng làm meter tags.

Đây là ranh giới hữu ích để instrumentation thể hiện rõ dữ liệu nào được phép tham gia tạo time series.

Ví dụ:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public class MessageProcessor {

    private final ObservationRegistry observationRegistry;
    private final OrderService orderService;

    public MessageProcessor(
            ObservationRegistry observationRegistry,
            OrderService orderService) {
        this.observationRegistry = observationRegistry;
        this.orderService = orderService;
    }

    public void process(
            OrderCommand command,
            String userId,
            String messageId) {

        Observation.createNotStarted(
                        "messaging.process",
                        observationRegistry)
                .lowCardinalityKeyValue(
                        "messaging.destination",
                        "orders.create")
                .lowCardinalityKeyValue(
                        "messaging.protocol",
                        "rsocket")
                .highCardinalityKeyValue(
                        "user.id",
                        userId)
                .highCardinalityKeyValue(
                        "messaging.message.id",
                        messageId)
                .observe(() -> orderService.process(command));
    }
}
~~~

messaging.destination và messaging.protocol có tập giá trị hữu hạn, nên có thể được dùng làm meter tags. user.id và messaging.message.id có thể thay đổi ở mỗi lần xử lý; chúng được đánh dấu high-cardinality để phục vụ trace mà không tạo series riêng trong metrics.

Ví dụ giả định ứng dụng có OrderCommand và OrderService riêng. Cấu hình ObservationRegistry phải có ObservationHandler tương ứng để xuất metrics hoặc traces. Nếu không có handler phù hợp, tạo Observation không tự bảo đảm dữ liệu sẽ được gửi tới backend.

**Chú ý bảo mật:** high-cardinality không đồng nghĩa với dữ liệu được phép ghi. Nếu userId có thể nhận diện một cá nhân hoặc thuộc nhóm dữ liệu hạn chế, hãy cân nhắc bỏ hẳn khỏi trace, dùng định danh giả/pseudonymous, hạn chế quyền truy cập và đặt retention phù hợp. Email, số điện thoại, token và dữ liệu xác thực không nên được thêm chỉ vì API cho phép.

### 5.1. Custom ObservationConvention

Khi instrumentation cần trích xuất tag từ context, có thể tạo ObservationConvention. Convention tách rõ các giá trị thấp và cao:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.http.server.observation.ServerRequestObservationContext;
import org.springframework.http.server.observation.ServerRequestObservationConvention;

public class CustomRequestConvention
        implements ServerRequestObservationConvention {

    @Override
    public String getName() {
        return "http.server.requests";
    }

    @Override
    public String getContextualName(
            ServerRequestObservationContext context) {
        return "http request";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ServerRequestObservationContext context) {
        return KeyValues.of(
                KeyValue.of(
                        "request.method",
                        context.getCarrier().getMethod()));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(
            ServerRequestObservationContext context) {
        return KeyValues.empty();
    }
}
~~~

Ví dụ này minh họa cách tổ chức convention: method HTTP có tập giá trị nhỏ. Trong ứng dụng thực tế, nên mở rộng convention mặc định của Spring để giữ lại các tag chuẩn như status, outcome và exception; không thay toàn bộ convention nếu không chủ ý thay đổi schema metric.

Với HTTP path, chỉ dùng route template hoặc giá trị đã chuẩn hóa trong low-cardinality tags. Đường dẫn thực tế chứa ID không nên đưa vào metrics. Nếu muốn lưu URI đầy đủ cho chẩn đoán, dùng high-cardinality trace attribute theo chính sách dữ liệu.

## 6. Ghi metric tùy chỉnh với tập tag được kiểm soát

Nếu không cần Observation, có thể tạo Counter hoặc Timer trực tiếp từ Micrometer. Giá trị tag cần được chuẩn hóa trước khi đăng ký meter.

Ví dụ:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public class MessagingMetrics {

    private final MeterRegistry registry;

    public MessagingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordProcessed(
            String rawDestination,
            MessageOutcome outcome) {

        String destination =
                MetricDestination.from(rawDestination).tagValue();

        Counter.builder("messaging.messages.processed")
                .description("Number of processed messages")
                .tag("destination", destination)
                .tag("outcome", outcome.tagValue())
                .register(registry)
                .increment();
    }

    enum MessageOutcome {
        SUCCESS("success"),
        REJECTED("rejected"),
        ERROR("error");

        private final String tagValue;

        MessageOutcome(String tagValue) {
            this.tagValue = tagValue;
        }

        String tagValue() {
            return tagValue;
        }
    }
}
~~~

Đoạn code dùng enum MetricDestination đã khai báo ở phần trước. Mỗi lần gọi, destination đầu vào được ánh xạ vào một tập giá trị cố định; outcome cũng chỉ có ba lựa chọn. User ID, message ID và request ID không tham gia meter ID.

Nếu cần đếm lỗi theo nhóm, thêm một tag enum error_category với các giá trị hữu hạn. Không dùng exception message làm tag. Với Timer, áp dụng cùng quy tắc vì mỗi tổ hợp tag vẫn tạo một meter riêng.

## 7. Đặt giới hạn bảo vệ bằng MeterFilter

Thiết kế nhãn tốt là lớp bảo vệ đầu tiên. Có thể thêm MeterFilter để giới hạn số giá trị tag hoặc tổng số meter được đăng ký.

Ví dụ:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;

public final class MetricsConfiguration {

    public static void configure(MeterRegistry registry) {
        registry.config()
                .meterFilter(
                        MeterFilter.maximumAllowableTags(
                                "messaging.messages",
                                "destination",
                                20,
                                MeterFilter.deny()))
                .meterFilter(
                        MeterFilter.maximumAllowableMetrics(10_000));
    }
}
~~~

Ý nghĩa:

- Filter thứ nhất áp dụng cho các meter có tên bắt đầu bằng messaging.messages.
- Với tag key destination, chỉ cho phép tối đa 20 giá trị khác nhau.
- Khi vượt giới hạn, MeterFilter.deny() từ chối đăng ký meter mới có giá trị vượt ngưỡng.
- Filter thứ hai đặt giới hạn tổng số meter theo registry.

Các số 20 và 10.000 chỉ là giá trị minh họa; phải chọn dựa trên ngân sách series của hệ thống. maximumAllowableMetrics là chốt bảo vệ toàn cục, không phân biệt metric nào quan trọng hơn. Nếu cấu hình quá thấp, các meter cần thiết cũng có thể bị từ chối.

maximumAllowableTags không tự gom mọi giá trị mới vào other; với deny() nó từ chối meter vượt giới hạn. Vì vậy, hãy chuẩn hóa giá trị trước khi đăng ký meter. Filter là lớp phòng vệ khi có lỗi instrumentation, không thay thế việc thiết kế schema.

### 7.1. Bỏ tag không an toàn trong giai đoạn chuyển đổi

Micrometer có MeterFilter.ignoreTags(...) để loại bỏ tag key khỏi meter. Có thể dùng tạm thời khi cần ngăn một tag nguy hiểm tiếp tục được xuất trong lúc sửa các điểm instrumentation.

Ví dụ:

~~~java
registry.config().meterFilter(
        MeterFilter.ignoreTags(
                "userId",
                "user_id",
                "requestId",
                "sessionId"));
~~~

Filter này có phạm vi rộng trên registry; không dùng tùy tiện nếu một meter hợp lệ cần tag đó. Nó cũng không biến dữ liệu đã xuất trước đây thành dữ liệu an toàn và không thay thế việc xóa/sửa instrumentation nguồn. Sau khi triển khai, cần kiểm tra schema meter thực tế và dashboard phụ thuộc vào tag.

## 8. Đo cardinality và kiểm tra schema metric

### 8.1. Kiểm tra trước khi phát hành

Với mỗi metric tùy chỉnh, lập bảng schema:

| Metric | Tag key | Tập giá trị tối đa | Nguồn |
|---|---|---:|---|
| messaging.messages.processed | destination | 4 | Enum server |
| messaging.messages.processed | outcome | 3 | Enum server |
| messaging.messages.processed | protocol | 3 | Cấu hình adapter |
| messaging.process.duration | error_category | 5 | Nhóm lỗi cố định |

Từ đó tính giới hạn trên của tổ hợp. Nếu một tag không thể liệt kê tập giá trị, đó là dấu hiệu cần xem xét lại thiết kế trước khi phát hành.

### 8.2. Unit test bảo đảm không có định danh trong meter tags

Có thể dùng SimpleMeterRegistry để kiểm tra các meter được tạo ra. Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MessagingMetricsTests {

    @Test
    void meterTagsDoNotContainUserOrRequestIdentifiers() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        MessagingMetrics metrics = new MessagingMetrics(registry);

        for (int i = 0; i < 1_000; i++) {
            metrics.recordProcessed(
                    "orders.create",
                    MessagingMetrics.MessageOutcome.SUCCESS);
        }

        assertFalse(registry.getMeters().isEmpty());

        assertTrue(registry.getMeters().stream().allMatch(meter -> {
            Meter.Id id = meter.getId();

            return id.getTag("userId") == null
                    && id.getTag("user_id") == null
                    && id.getTag("requestId") == null
                    && id.getTag("sessionId") == null;
        }));

        assertTrue(registry.getMeters().size() <= 2);
    }
}
~~~

Test này tạo cùng một tổ hợp destination/outcome 1.000 lần. Số meter vẫn bị giới hạn vì giá trị tag không thay đổi theo từng lần gọi. Assertion kiểm tra các khóa định danh không xuất hiện trong meter tags.

Để kiểm tra cả trường hợp đầu vào có giá trị lạ, hãy gửi nhiều destination không nằm trong enum và xác nhận chúng đều được gom vào other. Khi đó số giá trị tag vẫn không tăng theo số chuỗi đầu vào.

### 8.3. Theo dõi cardinality ở backend

Ở Prometheus, có thể dùng truy vấn để xem số series theo tên metric, ví dụ:

~~~promql
count by (__name__) ({__name__=~"messaging_.*"})
~~~

Truy vấn trên đếm số series cho từng metric có tên phù hợp. Tùy phiên bản Prometheus và naming convention của registry, tên metric xuất ra có thể khác tên Micrometer ban đầu. Cần kiểm tra metric thực tế trong endpoint scrape trước khi viết dashboard hoặc alert.

Có thể theo dõi thêm:

- Số series mới xuất hiện trong một khoảng thời gian.
- Số meter đang đăng ký trong từng MeterRegistry.
- Số lần filter từ chối meter vì vượt giới hạn.
- Số lượng tag values của các metric quan trọng.
- Chi phí và thời gian truy vấn ở backend monitoring.

Không chỉ nhìn tổng số series. Một metric tăng đột biến có thể gây cardinality explosion ngay cả khi tổng series toàn hệ thống vẫn chưa chạm ngưỡng cảnh báo.

## 9. Logs, traces và exemplars cho truy vấn chi tiết

### 9.1. Structured logs

Log có cấu trúc phù hợp để điều tra một lần xử lý cụ thể. Có thể ghi các trường như messageId, requestId, correlationId hoặc userId nếu policy cho phép và đã kiểm soát dữ liệu.

Ví dụ minh họa:

~~~json
{
  "event": "message.processing.failed",
  "destination": "orders.create",
  "messageId": "msg-7f31",
  "requestId": "req-91a2",
  "userId": "user-204",
  "errorCategory": "business"
}
~~~

Các trường định danh ở đây phục vụ tìm kiếm một sự kiện cụ thể. Chúng không phải metric labels. Hệ thống log vẫn cần kiểm soát truy cập, mã hóa, retention và che dữ liệu cá nhân; không ghi token, mật khẩu hoặc nội dung nhạy cảm chỉ để tiện debug.

### 9.2. Distributed tracing

Trace liên kết các span của cùng một request qua nhiều service. High-cardinality attributes có thể giúp tìm một lần xử lý cụ thể, nhưng cần cân nhắc chi phí lưu trữ, sampling, quyền truy cập và dữ liệu nhạy cảm.

Một trace có thể chứa:

- Operation: orders.create.
- Protocol: rsocket.
- Destination: route đã chuẩn hóa.
- Message ID: nếu cần liên kết với log và được policy cho phép.
- User ID giả danh: chỉ khi có nhu cầu điều tra hợp lệ và kiểm soát truy cập.

Không đặt traceId thành tag của metric. Trace ID được sinh riêng cho từng trace; đưa nó vào metric sẽ tạo một series mới cho mỗi trace.

### 9.3. Exemplars

Exemplar là tham chiếu mẫu gắn với một sample metric, thường được dùng để liên kết metric với trace. Khi backend và registry hỗ trợ, người vận hành có thể từ một điểm bất thường trên histogram hoặc counter mở trace đại diện.

Exemplar giúp điều tra chi tiết mà không cần đưa trace ID vào labelset của metric. Khả năng hỗ trợ và cấu hình phụ thuộc registry, exporter và backend; cần kiểm tra stack observability đang dùng.

## 10. Quy trình xử lý khi phát hiện metric có cardinality cao

Khi dashboard hoặc backend cho thấy số series tăng nhanh:

1. Xác định metric nào tạo ra nhiều series nhất.
2. Xem các tag keys và đếm số giá trị khác nhau của từng key.
3. Tìm tag có giá trị giống UUID, email, ID, timestamp, URL hoặc chuỗi tự do.
4. Xác định nơi tạo tag: ObservationConvention, MeterFilter, Counter/Timer builder, interceptor hoặc instrumentation của thư viện.
5. Thay giá trị động bằng enum, route template hoặc nhóm other có giới hạn.
6. Chuyển dữ liệu cần truy vấn từng request sang log/trace với policy bảo vệ phù hợp.
7. Thêm test để xác nhận tag schema và số meter không tăng theo số user/request.
8. Triển khai filter bảo vệ nếu cần, theo dõi meter bị từ chối và cập nhật dashboard/alert.
9. Kiểm tra backend sau triển khai; dữ liệu time series cũ có thể còn tồn tại đến khi hết retention.

Không chỉ thêm MeterFilter.deny() rồi coi vấn đề đã được giải quyết. Nếu filter liên tục từ chối meter quan trọng, dashboard có thể thiếu dữ liệu mà ứng dụng vẫn chạy bình thường. Cần cảnh báo về số meter bị từ chối và sửa nguồn tạo tag.

## 11. Ghi nhớ

- Mỗi tổ hợp tên metric và labelset là một time series.
- Cardinality của metric tăng theo tích số giá trị của các tag keys.
- User ID, email, session ID, request ID, trace ID và các ID duy nhất không phù hợp làm metric tags.
- Dùng route template, enum, outcome và nhóm lỗi hữu hạn để tạo chiều phân tích.
- Micrometer Observation đưa low-cardinality key values vào metrics và traces; high-cardinality key values chỉ vào traces.
- High-cardinality trong trace vẫn cần kiểm soát quyền truy cập, retention và dữ liệu cá nhân.
- MeterFilter.maximumAllowableTags và maximumAllowableMetrics là guardrail; chúng không thay thế schema nhãn tốt.
- Dùng logs, traces và exemplars để điều tra request cụ thể; dùng metrics để quan sát xu hướng và SLO tổng hợp.
- Kiểm thử meter tags và cardinality trong CI để tránh vô tình đưa ID động vào instrumentation.

Thiết kế metric tốt giữ được khả năng tổng hợp và so sánh theo thời gian. Khi cần biết một người dùng hoặc request cụ thể, hãy lần theo log/trace có kiểm soát thay vì biến mỗi định danh thành một time series.

## Tài liệu tham khảo

- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html)
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html)
- [MeterFilter — Micrometer 1.13 API](https://javadoc.io/doc/io.micrometer/micrometer-core/1.13.14/io/micrometer/core/instrument/config/MeterFilter.html)
- [Prometheus — Metric and Label Naming](https://prometheus.io/docs/practices/naming/)
- [Prometheus — Instrumentation Practices](https://prometheus.io/docs/practices/instrumentation/)
- [Prometheus — The Zen of Prometheus](https://prometheus.io/docs/practices/the_zen/)
