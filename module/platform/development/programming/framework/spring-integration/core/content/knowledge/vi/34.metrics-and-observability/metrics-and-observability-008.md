# Micrometer tags

Trong chương **Metrics và observability** của module **SPRING_INTEGRATION_CORE**, tags giúp phân tích hoạt động của luồng thông điệp theo những chiều như thành phần, nguồn gửi và kết quả xử lý. Bài học này tập trung vào việc chọn và sử dụng tags khi quan sát Message, MessageChannel, endpoint và luồng Java DSL.

Một tổng số lỗi của toàn ứng dụng chưa cho biết lỗi nằm ở bước kiểm tra đơn hàng hay ở bước gọi hệ thống thanh toán. Tags bổ sung ngữ cảnh để trả lời câu hỏi đó. Chúng cũng quyết định có bao nhiêu meter và chuỗi thời gian được tạo ra, vì vậy thiết kế tags là một phần của thiết kế luồng tích hợp.

## 1. Mục tiêu và phạm vi

Sau bài học, bạn có thể:

- Phân biệt tên metric, tag key, tag value và giá trị đo.
- Đọc tags do Spring Integration cung cấp và nhận biết khác biệt khi dùng Observation.
- Thiết kế tập tags hữu hạn cho một luồng xử lý thông điệp.
- Chuẩn hóa dữ liệu từ message header trước khi sử dụng làm tag.
- Áp dụng common tags và giới hạn đăng ký bằng MeterFilter.
- Đọc kết quả đo theo đúng ranh giới channel, handler và nghiệp vụ.

Ví dụ chính dùng Java 17 trở lên, Spring Integration 6.x và Micrometer do BOM phù hợp của dự án quản lý. Ví dụ cấu hình Spring thuần để thấy rõ nơi tạo registry; không phụ thuộc vào cơ chế tự cấu hình của Spring Boot. Các đoạn cấu hình Observation ở phần sau là phần mở rộng riêng.

## 2. Tags là gì và tham gia định danh meter như thế nào?

Một tag là cặp khóa–giá trị mô tả một chiều phân loại của phép đo:

```text
Tên meter: orders.validation

Tags:
  flow=orders
  stage=validate
  source=web
  outcome=success

Một phép đo:
  thời gian xử lý = 12 ms
```

Ở đây:

- `orders.validation` cho biết đang đo thao tác nào.
- `source=web` xác định nhóm thông điệp.
- `outcome=success` xác định kết quả.
- `12 ms` là giá trị quan sát, không phải tag.

Trong một registry, **tên và tập tags cùng định danh meter**. Các tổ hợp `source=web` và `source=mobile` là hai meter khác nhau dù dùng chung tên. Gọi đăng ký lại cùng tên, cùng tags và cùng loại meter thường lấy lại meter đã tồn tại. Không dùng chung định danh cho các loại đo có ý nghĩa khác nhau. Cơ sở của mô hình này được mô tả trong [Micrometer — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

Ví dụ:

```java
registry.counter("orders.rejected", "reason", "invalid").increment();
registry.counter("orders.rejected", "reason", "duplicate").increment();
registry.counter("orders.rejected", "reason", "invalid").increment();
```

Ba lời gọi trên tạo hai bộ đếm theo lý do, với giá trị lần lượt là 2 và 1. Đưa lý do vào tên như `orders.rejected.invalid` làm mất một chiều phân loại thuận tiện; dashboard sẽ phải xử lý nhiều tên thay vì lọc một tag.

Duy trì tên và tag key theo quy ước chữ thường, phân tách từ bằng dấu chấm khi cần. Registry có thể chuyển đổi chúng sang quy ước của backend; ví dụ một tên chứa dấu chấm có thể xuất hiện với dấu gạch dưới trong dữ liệu Prometheus. Xem [Micrometer — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

### Phân biệt tag với message header

Message header thuộc dữ liệu đi qua luồng. Tag thuộc dữ liệu quan sát được ghi vào registry. Hai tập này không tự động giống nhau.

```text
Header:
  source = WEB
  orderId = ORD-1928
  correlationId = c-8139

Tags do ứng dụng chủ động chọn:
  source = web
  flow = orders
  stage = validate
```

Chỉ `source` sau chuẩn hóa được chọn cho metric. Header `orderId` vẫn có thể phục vụ nghiệp vụ hoặc tương quan log, nhưng không vì thế mà trở thành tag.

## 3. Đọc tags có sẵn của Spring Integration

### 3.1. Metrics trực tiếp qua MeterRegistry

Ở cơ chế metrics trực tiếp, Spring Integration có timer `spring.integration.send` cho channel và handler. Những tags sau giúp phân biệt phép đo:

| Tag key | Ý nghĩa | Ví dụ |
|---|---|---|
| `type` | Loại thành phần | `channel`, `handler` |
| `name` | Tên thành phần | `ordersInput` |
| `result` | Kết quả thao tác | `success`, `failure` |
| `exception` | Tên lớp ngoại lệ hoặc không có | `none` |

Trường hợp `result=failure`, `exception=none` có thể xảy ra khi `send()` trả về `false`. Tài liệu chính thức trình bày schema này trong [Spring Integration — Micrometer Integration](https://docs.spring.io/spring-integration/reference/6.5/metrics.html#micrometer-integration).

Điểm cần nhớ: tag `name` là tên thành phần, không phải tên metric. Khi tìm trong registry, hãy lọc tên meter và các tag riêng biệt:

```java
registry.find("spring.integration.send")
        .tags("type", "channel", "name", "ordersInput")
        .timers()
        .forEach(timer -> System.out.println(timer.getId()));
```

Tên endpoint trong Java DSL và tên handler thực tế có thể khác nhau. Đặt tên rõ ràng cho endpoint giúp vận hành, nhưng vẫn nên xem `Meter.Id` thực tế trước khi cố định truy vấn theo `name`.

### 3.2. Metrics thông qua Observation

Spring Integration còn có cơ chế Observation, với các tên như `spring.integration.producer`, `spring.integration.handler` và `spring.integration.gateway`. Tags của các convention này dùng các khóa như `spring.integration.name`, `spring.integration.type`; gateway còn có `spring.integration.outcome`. Không áp nguyên truy vấn dùng `name`, `type`, `result` của cơ chế trực tiếp sang schema Observation. Xem phần [Micrometer Observation của Spring Integration](https://docs.spring.io/spring-integration/reference/metrics.html#micrometer-observation).

Khi xử lý sự cố “không tìm thấy metric”, hãy xác định cơ chế đang bật trước khi thêm tags hay thay đổi dashboard.

## 4. Chọn tags theo câu hỏi vận hành

Giả sử luồng nhận đơn hàng từ website, ứng dụng di động và đối tác. Bạn muốn biết:

1. Nguồn nào đang có nhiều đơn không hợp lệ?
2. Bước kiểm tra dữ liệu có chậm hơn bình thường không?
3. Lỗi kỹ thuật đang tăng trên môi trường nào?

Có thể đề xuất schema cho timer nghiệp vụ `orders.validation` như sau:

| Tag key | Phạm vi | Tập giá trị trong ví dụ |
|---|---|---|
| `application` | Toàn ứng dụng | `order-integration` |
| `environment` | Một lần triển khai | `lab` |
| `flow` | Luồng nghiệp vụ | `orders` |
| `stage` | Bước được đo | `validate` |
| `source` | Từng thông điệp sau chuẩn hóa | `web`, `mobile`, `partner`, `other`, `unknown` |
| `outcome` | Kết quả bước kiểm tra | `success`, `rejected`, `failure` |

Đây là schema do ứng dụng thiết kế, không phải bộ tags mặc định của Spring Integration.

Quy ước kết quả cần rõ nghĩa:

- `success`: dữ liệu hợp lệ và bước kiểm tra hoàn tất bình thường.
- `rejected`: dữ liệu không thỏa điều kiện nghiệp vụ.
- `failure`: gặp lỗi kỹ thuật khi thực hiện bước kiểm tra.

Một đơn bị từ chối đúng quy tắc không nhất thiết có cùng ý nghĩa vận hành với việc kết nối cơ sở dữ liệu bị lỗi. Giữ hai nhóm riêng giúp thiết lập cảnh báo phù hợp.

Không dùng common tag `name` để đặt tên ứng dụng vì khóa này đã có ý nghĩa ở metrics trực tiếp của Spring Integration. Dùng `application` giúp tránh tranh chấp khóa và làm truy vấn dễ hiểu hơn.

## 5. Cardinality: chi phí nằm ở số tổ hợp

Cardinality của một tag là số giá trị khác nhau mà tag có thể nhận. Giá trị không giới hạn như mã yêu cầu, thời điểm gửi hoặc nội dung tùy ý có thể làm số meter tăng liên tục. [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html) giải thích nguy cơ này đối với bộ nhớ và backend quan sát.

Với schema ví dụ:

```text
flow:     1 giá trị
stage:    1 giá trị
source:   5 giá trị
outcome:  3 giá trị

Giới hạn tổ hợp theo thiết kế:
1 × 1 × 5 × 3 = 15 meter cho orders.validation trong một registry
```

Đây là giới hạn tổ hợp có thể có; meter chưa từng được sử dụng có thể chưa xuất hiện.

Giả sử bạn mở rộng sang hai luồng, bốn bước và giữ năm nguồn, ba kết quả:

```text
2 × 4 × 5 × 3 = 120 tổ hợp
```

Nếu tiếp tục thêm `order.id` với 100.000 giá trị, giới hạn tích các chiều thành:

```text
120 × 100.000 = 12.000.000 tổ hợp
```

Không phải hệ thống nào cũng sinh đủ tích này, nhưng một chiều tăng theo dữ liệu nghiệp vụ đã phá vỡ tính hữu hạn của schema. Băm mã đơn hàng không giải quyết vấn đề: số giá trị khác nhau gần như vẫn giữ nguyên.

Cũng cần phân biệt **số meter** với **số chuỗi thời gian**. Timer xuất ra count và tổng thời gian; backend còn có thể xuất max, histogram buckets hoặc các thống kê khác. Do đó 15 timer không đồng nghĩa chỉ có 15 chuỗi thời gian. Khi bật histogram hoặc tăng số bản sao ứng dụng, hãy tính thêm chi phí tương ứng. Các đại lượng của timer được trình bày trong [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

## 6. Common tags và tags theo từng message

### Common tags

Dùng common tags cho những giá trị cố định trong vòng đời registry: tên ứng dụng, môi trường hoặc vùng triển khai. Cấu hình chúng trước khi đăng ký meter.

```java
registry.config().commonTags(
        "application", "order-integration",
        "environment", "lab");
```

### Tags theo từng message

Nguồn thông điệp và kết quả xử lý được quyết định ở điểm đo. Giá trị đầu vào cần đi qua một hàm chuẩn hóa có tập đầu ra hữu hạn:

```text
" WEB "       → web
"Mobile"      → mobile
"partner"     → partner
không có      → unknown
"campaign-17" → other
"campaign-18" → other
```

Không gọi `commonTags("source", currentSource)` mỗi lần nhận message. Common tags không phải bộ chứa ngữ cảnh thay đổi theo yêu cầu.

Tương tự, không dùng `MeterFilter.map()` để đọc message hiện tại từ ThreadLocal. Filter ánh xạ định danh lúc đăng ký meter; nó không phải interceptor được gọi một lần cho mỗi phép đo. Dữ liệu thay đổi theo request cần được xử lý tại instrumentation. Các nguyên tắc cấu hình này được nêu trong [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).

## 7. Ví dụ hoàn chỉnh với Java DSL

### 7.1. Luồng và ranh giới đo

Ví dụ sử dụng:

```text
Message<String>
    │
    ▼
ordersInput: DirectChannel
    │
    ▼
endpoint validateOrder
    │
    ▼
OrderValidator.validate(...)
    └── Timer orders.validation
        tags: flow, stage, source, outcome
```

Payload là chuỗi mã đơn minh họa. Chuỗi rỗng bị từ chối; chuỗi `simulate-error` dùng để minh họa lỗi kỹ thuật. Đây là dữ liệu giả lập để thấy hành vi tags.

Các thư viện cần có trên classpath:

- `org.springframework.integration:spring-integration-core`.
- `io.micrometer:micrometer-core`.
- Các dependency Spring Framework tương thích được quản lý qua BOM của dự án.

`SimpleMeterRegistry` chỉ lưu số liệu trong bộ nhớ để học và kiểm tra. Ví dụ này không mở HTTP endpoint và chưa xuất dữ liệu sang Prometheus.

### 7.2. Mã minh họa

Đặt các thành phần dưới đây trong một lớp `MicrometerTagsLesson` của ứng dụng thực hành:

```java
import java.util.Locale;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class MicrometerTagsLesson {

    @Bean
    public SimpleMeterRegistry meterRegistry() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        registry.config().commonTags(
                "application", "order-integration",
                "environment", "lab");

        registry.config().meterFilter(
                MeterFilter.maximumAllowableTags(
                        "orders.validation",
                        "source",
                        5,
                        MeterFilter.deny()));

        return registry;
    }

    @Bean
    public DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public OrderValidator orderValidator(MeterRegistry registry) {
        return new OrderValidator(registry);
    }

    @Bean
    public IntegrationFlow ordersFlow(OrderValidator validator) {
        return IntegrationFlow.from("ordersInput")
                .handle(validator, "validate",
                        endpoint -> endpoint.id("validateOrder"))
                .get();
    }

    public static final class OrderValidator {

        private final MeterRegistry registry;

        public OrderValidator(MeterRegistry registry) {
            this.registry = registry;
        }

        public void validate(Message<String> message) {
            String source = normalizeSource(
                    message.getHeaders().get("source"));

            Timer.Sample sample = Timer.start(this.registry);
            String outcome = "failure";

            try {
                String orderCode = message.getPayload();

                if (orderCode.isBlank()) {
                    outcome = "rejected";
                    throw new IllegalArgumentException(
                            "Order code must not be blank");
                }

                if ("simulate-error".equals(orderCode)) {
                    throw new IllegalStateException(
                            "Simulated technical failure");
                }

                // Bước kiểm tra dữ liệu đã hoàn tất.
                outcome = "success";
            }
            finally {
                Timer timer = this.registry.timer(
                        "orders.validation",
                        "flow", "orders",
                        "stage", "validate",
                        "source", source,
                        "outcome", outcome);

                sample.stop(timer);
            }
        }

        private static String normalizeSource(Object rawValue) {
            if (!(rawValue instanceof String text)) {
                return "unknown";
            }

            String value = text.strip().toLowerCase(Locale.ROOT);
            return switch (value) {
                case "web" -> "web";
                case "mobile" -> "mobile";
                case "partner" -> "partner";
                case "" -> "unknown";
                default -> "other";
            };
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             MicrometerTagsLesson.class)) {

            MessageChannel input =
                    context.getBean("ordersInput", MessageChannel.class);
            MeterRegistry registry =
                    context.getBean(MeterRegistry.class);

            send(input, "ORD-1", " WEB ", false);
            send(input, "", "mobile", true);
            send(input, "simulate-error", "partner", true);
            send(input, "ORD-2", null, false);

            for (int i = 0; i < 1_000; i++) {
                send(input, "ORD-" + (i + 3),
                        "untrusted-source-" + i, false);
            }

            registry.find("orders.validation").timers()
                    .forEach(timer -> System.out.printf(
                            "%s count=%d%n",
                            timer.getId().getTags(),
                            timer.count()));

            Timer otherSuccess = registry.get("orders.validation")
                    .tags("source", "other", "outcome", "success")
                    .timer();

            if (otherSuccess.count() != 1_000) {
                throw new AssertionError(
                        "Unexpected count for source=other");
            }

            if (registry.find("orders.validation").timers().size() > 15) {
                throw new AssertionError(
                        "Tag combinations exceeded the design limit");
            }
        }
    }

    private static void send(
            MessageChannel input,
            String payload,
            Object source,
            boolean expectFailure) {

        MessageBuilder<String> builder =
                MessageBuilder.withPayload(payload);

        if (source != null) {
            builder.setHeader("source", source);
        }

        try {
            if (!input.send(builder.build())) {
                throw new AssertionError("Message was not accepted");
            }
        }
        catch (MessagingException ex) {
            if (!expectFailure) {
                throw ex;
            }
            return;
        }

        if (expectFailure) {
            throw new AssertionError("Expected a handler failure");
        }
    }
}
```

### 7.3. Giải thích những quyết định trong ví dụ

**Chuẩn hóa trước khi đăng ký meter.** Một nghìn giá trị `untrusted-source-...` cùng được ánh xạ thành `other`. Không có meter riêng cho từng chuỗi đầu vào.

**Giữ nguyên tag keys ở mọi nhánh.** Cả thành công, từ chối và lỗi kỹ thuật đều có `flow`, `stage`, `source`, `outcome`. Không có nhánh nào bỏ hẳn `source` khi header vắng mặt.

**Chọn outcome khi kết thúc.** Khởi tạo `failure` bảo đảm ngoại lệ bất ngờ không bị gắn nhãn thành công. Nhánh dữ liệu rỗng chủ động đặt `rejected`. Cấu trúc `finally` bảo đảm cả đường thành công và đường ngoại lệ đều kết thúc sample.

**Đặt ranh giới thời gian rõ ràng.** Timer nghiệp vụ bắt đầu sau chuẩn hóa header và kết thúc sau bước kiểm tra. Nó không đo thời gian chờ ở một hàng đợi bên ngoài luồng này.

**Giữ dữ liệu chi tiết ở message.** Mã đơn chỉ dùng làm payload. Timer không có tag `order.id`, `message.id` hoặc chuỗi thông báo lỗi.

**Dùng cùng registry.** Meter nghiệp vụ và thành phần tích hợp cùng sử dụng bean registry trong ApplicationContext. Một registry tự tạo bên trong handler sẽ làm số liệu tách khỏi nơi cấu hình và xuất dữ liệu.

Ví dụ chọn meter lúc kết thúc sample để đưa kết quả cuối cùng vào tags, đúng với cách dùng [Timer.Sample](https://docs.micrometer.io/micrometer/reference/concepts/timers.html#_storing_start_state_in_timer_sample).

### 7.4. Kết quả mong đợi

Trong một ApplicationContext mới, chỉ các tổ hợp đã gặp mới được tạo:

| source | outcome | count |
|---|---|---:|
| `web` | `success` | 1 |
| `mobile` | `rejected` | 1 |
| `partner` | `failure` | 1 |
| `unknown` | `success` | 1 |
| `other` | `success` | 1.000 |

Tổng số lần kiểm tra là 1.004; số timer nghiệp vụ thực tế là 5. Mỗi timer còn có các tags cố định `application`, `environment`, `flow`, `stage`. Thứ tự in tags không phải điều kiện kiểm tra.

Lỗi từ handler được đồng bộ truyền ngược qua DirectChannel và có thể được Spring Integration bọc trong MessagingException. Hàm `send` ở ví dụ chỉ nhận hai lỗi dự kiến để tiếp tục minh họa. Trong ứng dụng, chính sách xử lý lỗi cần phù hợp với gateway, error channel và mô hình đồng bộ hoặc bất đồng bộ đang sử dụng.

## 8. MeterFilter là giới hạn bảo vệ, không phải phép chuẩn hóa nghiệp vụ

Trong ví dụ:

```java
MeterFilter.maximumAllowableTags(
        "orders.validation", "source", 5, MeterFilter.deny())
```

Bộ lọc giới hạn số giá trị khác nhau của khóa `source` trên nhóm tên meter khớp tiền tố. Nó không giới hạn tổng số tổ hợp của mọi khóa và không tự xác định năm giá trị nào hợp lệ.

Nếu handler ghi trực tiếp một nghìn giá trị nguồn khác nhau, năm giá trị đầu có thể được giữ lại còn các giá trị tiếp theo bị từ chối đăng ký. Bạn vừa mất dữ liệu quan sát vừa không có cách phân nhóm hữu ích. Khi dùng deny, meter bị chặn là meter không ghi nhận số liệu; thao tác nghiệp vụ không tự thất bại vì điều đó. Xem [Meter Filters — Deny or Accept Meters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html#_deny_or_accept_meters).

Vì vậy, ví dụ kết hợp hai lớp:

1. Hàm `normalizeSource` quy định tập giá trị có ý nghĩa.
2. MeterFilter giới hạn đăng ký nếu có điểm ghi số liệu khác vi phạm thiết kế.

Nếu cần sửa một schema đã phát sinh quá nhiều giá trị, ưu tiên sửa điểm tạo tags. Loại bỏ một chiều bằng filter có thể khiến nhiều meter gộp vào cùng định danh; dashboard sẽ mất khả năng phân biệt chiều đó. Cũng không thể khôi phục dữ liệu chi tiết đã bị gộp chỉ bằng cách sửa câu truy vấn.

## 9. Observation: phân biệt low cardinality và high cardinality

Micrometer Observation phân loại metadata thành hai nhóm:

| Nhóm | Mục đích phù hợp | Ví dụ |
|---|---|---|
| Low cardinality | Phân nhóm số liệu với tập giá trị hữu hạn | `flow=orders`, `source=web` |
| High cardinality | Tương quan một lần xử lý cụ thể | `order.id=ORD-1928` |

Đánh dấu một giá trị là low cardinality không tự làm giảm số giá trị của nó. Nếu gắn mã đơn khác nhau vào low-cardinality key thì vấn đề cardinality vẫn còn. Khái niệm và API được mô tả trong [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).

Với handler metrics chuẩn của Observation, chỉ low-cardinality key-values trở thành meter tags. High-cardinality metadata có thể phục vụ tracing khi có handler và exporter tương ứng; chỉ tạo ObservationRegistry chưa làm tracing hoạt động. Xem [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) về phân biệt hai loại metadata.

### 9.1. Bật Observation cho thành phần Spring Integration

Trong một cấu hình Spring thuần dùng chung MeterRegistry đã có, có thể thêm cấu hình sau:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegrationManagement;

@Configuration
@EnableIntegrationManagement(observationPatterns = "*")
public class IntegrationObservationConfig {

    @Bean
    public ObservationRegistry observationRegistry(MeterRegistry registry) {
        ObservationRegistry observations = ObservationRegistry.create();
        observations.observationConfig()
                .observationHandler(
                        new DefaultMeterObservationHandler(registry));
        return observations;
    }
}
```

Cấu hình này cần được đăng ký vào ApplicationContext cùng cấu hình luồng. Trong ví dụ Spring thuần, có thể truyền cả hai lớp cấu hình vào constructor của AnnotationConfigApplicationContext.

`observationPatterns = "*"` chọn tất cả thành phần phù hợp để gắn ObservationRegistry. Mặc định của thuộc tính này không tự chọn tất cả; xem [EnableIntegrationManagement — observationPatterns](https://docs.spring.io/spring-integration/docs/6.2.6/api/org/springframework/integration/config/EnableIntegrationManagement.html#observationPatterns()).

Nếu ứng dụng Spring Boot đã cung cấp ObservationRegistry và handler metrics, sử dụng cấu hình hiện có để tránh đăng ký lặp. Cấu hình trên minh họa ứng dụng tự quản lý registry.

`DefaultMeterObservationHandler` tạo timer từ vòng đời Observation và sử dụng các low-cardinality key-values. Timer theo dõi tác vụ đang chạy có thể chỉ thấy tags đã tồn tại lúc bắt đầu, nên tags chỉ biết khi kết thúc không nhất thiết xuất hiện trên meter `.active`. Xem [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html).

### 9.2. Metadata cho một Observation nghiệp vụ

Đoạn dưới minh họa một phương thức nghiệp vụ riêng, đã được truyền ObservationRegistry và một mã đơn hợp lệ:

```java
void inspectOrder(ObservationRegistry observations, String orderId) {
    Observation.createNotStarted("orders.inspection", observations)
            .lowCardinalityKeyValue("flow", "orders")
            .lowCardinalityKeyValue("source", "web")
            .highCardinalityKeyValue("order.id", orderId)
            .observe(() -> {
                // Thực hiện nghiệp vụ cần quan sát.
            });
}
```

Đoạn này cần import `io.micrometer.observation.Observation`. Nó tạo observation nghiệp vụ mới; không tự bổ sung tags vào mọi observation nội bộ của Spring Integration.

Nếu muốn đổi tags của observation do framework tạo, cần convention phù hợp với loại thành phần và context đó. Giữ các khóa chuẩn cần thiết và chỉ bổ sung những chiều có tập giá trị đã xác định. Không dùng MeterFilter như công cụ đọc message context.

## 10. Đọc kết quả và xây dựng truy vấn đúng

### 10.1. Kiểm tra ngay trong registry

Sau khi gửi dữ liệu, liệt kê định danh thực tế:

```java
registry.find("orders.validation").timers()
        .forEach(timer -> {
            System.out.println(timer.getId().getName());
            System.out.println(timer.getId().getTags());
            System.out.println(timer.count());
        });
```

Một timer có sẵn count, vì vậy không cần thêm counter chỉ để đếm đúng cùng tập sự kiện mà timer đã đo. Có thể dùng counter riêng khi muốn đo một sự kiện khác, chẳng hạn thông điệp bị filter loại trước khi tới bước validation.

Khi kiểm tra metric có gắn tags, đừng chỉ xác nhận “tên này tồn tại”. Cần kiểm tra bộ khóa, giá trị sau chuẩn hóa và count của từng nhóm.

### 10.2. Khi xuất sang Prometheus

Để xuất dữ liệu cần registry Prometheus cùng điểm scrape; SimpleMeterRegistry không cung cấp chức năng đó. Ngoài ra, với PrometheusMeterRegistry cần giữ cùng tập tag keys cho các meter cùng tên. Dùng `unknown` khi thiếu nguồn thay vì bỏ khóa `source`. Cách tích hợp được trình bày trong [Micrometer — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html).

Nếu bản xuất thực tế của timer có series `orders_validation_seconds_count`, có thể tính lưu lượng theo nguồn:

```promql
sum by (source) (
  rate(orders_validation_seconds_count{
    application="order-integration",
    environment="lab",
    flow="orders",
    stage="validate"
  }[5m])
)
```

Tỷ lệ lỗi kỹ thuật trên tất cả lượt validation đã hoàn tất, theo cùng phạm vi:

```promql
sum(
  rate(orders_validation_seconds_count{
    application="order-integration",
    environment="lab",
    flow="orders",
    stage="validate",
    outcome="failure"
  }[5m])
)
/
sum(
  rate(orders_validation_seconds_count{
    application="order-integration",
    environment="lab",
    flow="orders",
    stage="validate"
  }[5m])
)
```

Hai truy vấn là ví dụ dựa trên schema đã thiết kế. Xác nhận tên series từ dữ liệu scrape trước khi sử dụng, vì quy ước tên và cấu hình registry có thể khác. Khi chưa có lưu lượng, mẫu số bằng không hoặc series chưa tồn tại; dashboard và cảnh báo cần thể hiện trạng thái đó theo mục đích vận hành.

Tỷ lệ `rejected` có thể được tính riêng để theo dõi chất lượng dữ liệu đầu vào. Không cộng `rejected` vào lỗi kỹ thuật nếu định nghĩa cảnh báo của bạn chỉ quan tâm lỗi hạ tầng hoặc lỗi thực thi.

## 11. Gắn tags đúng với ranh giới của EIP

Cùng một message có thể đi qua nhiều thành phần. Ý nghĩa phép đo phụ thuộc vào điểm bắt đầu và kết thúc.

| Thành phần hoặc mẫu tích hợp | Chiều phân loại có thể thiết kế | Điều cần định nghĩa |
|---|---|---|
| Transformer | `stage=normalize`, `outcome` hữu hạn | Đang đo mỗi lần chuyển đổi hay toàn luồng? |
| Router | `route=standard/priority/other` | Tên nhánh có cố định hay lấy thẳng từ dữ liệu? |
| Filter | `decision=accepted/rejected` | Thông điệp bị loại có tới timer phía sau không? |
| Aggregator | `release.reason=size/timeout/other` | Đếm từng message đầu vào hay từng nhóm được phát hành? |
| Gateway | `operation=submit/cancel` | Kết thúc khi có phản hồi hay mới gửi được message? |
| Retry | `outcome` hoặc `attempt.bucket=first/retried` | Đo mỗi lần thử hay kết quả cuối của một thao tác? |

Các chiều trong bảng là gợi ý nghiệp vụ do người thiết kế chọn, không phải tags tự động do framework cam kết cung cấp.

Với DirectChannel, thời gian gửi có thể bao gồm thời gian handler đồng bộ thực thi. Với channel chuyển giao bất đồng bộ, phép đo gửi thường không bao trùm toàn bộ xử lý phía sau. Vì vậy không gắn nhãn “độ trễ toàn luồng” cho mọi timer send.

Cũng không cộng count của channel với count của handler rồi gọi kết quả là “số đơn hàng”. Một lần xử lý có thể được quan sát ở cả hai điểm. Nếu muốn đo số đơn hoàn tất, đặt một metric nghiệp vụ tại đúng điểm hoàn tất, đồng thời xác định rõ chính sách đếm khi có retry hoặc giao lại thông điệp.

## 12. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Lấy mọi header làm tag | Số tổ hợp tăng theo dữ liệu đầu vào | Chọn khóa cần thiết và chuẩn hóa theo danh sách cho phép |
| Đưa orderId vào tên meter | Tạo vô số tên metric | Dùng một tên ổn định; tương quan đơn qua log hoặc trace |
| Dùng thông báo ngoại lệ làm tag | Mỗi nội dung lỗi có thể thành giá trị mới | Dùng nhóm lỗi hữu hạn hoặc tên lớp khi phù hợp |
| Chỉ thêm tag ở nhánh thành công | Schema không nhất quán | Giữ cùng bộ khóa và dùng giá trị thay thế đã quy ước |
| Đăng ký common tags sau khi đã tạo meter | Các meter có thể không đồng nhất | Cấu hình registry trước khi instrumentation hoạt động |
| Gắn outcome=success trước khi xử lý | Ngoại lệ có thể bị ghi nhãn sai | Chọn kết quả khi thao tác kết thúc |
| Chỉ dùng giới hạn tags mà không chuẩn hóa | Một phần phép đo bị loại bỏ | Chuẩn hóa tại nguồn rồi mới áp dụng giới hạn |
| Tin rằng lowCardinalityKeyValue tự giới hạn giá trị | Mã định danh vẫn làm tăng số meter | Tự thiết kế và thực thi tập giá trị hữu hạn |
| Đổi từ metrics trực tiếp sang Observation nhưng giữ nguyên truy vấn | Dashboard không tìm đúng tên hoặc khóa | Kiểm tra schema thực tế của cơ chế đang chạy |
| Dùng timer của bước giữa làm số liệu hoàn tất đơn | Bỏ sót các bước sau hoặc đếm nhầm retry | Đặt metric tại ranh giới nghiệp vụ cần đo |

## 13. Bài tập tự thực hành

1. Mở rộng hàm chuẩn hóa để nhận `" APP "` như bí danh của `mobile`. Dự đoán số timer có tăng không, rồi kiểm tra bằng danh sách Meter.Id.
2. Gửi 10.000 message có header nguồn khác nhau và payload hợp lệ. Kết quả cần có count tăng trong nhóm `other`, trong khi số giá trị `source` vẫn hữu hạn.
3. Thêm kết quả `duplicate` vào schema nghiệp vụ. Cập nhật định nghĩa, vị trí đặt kết quả và phép tính giới hạn tổ hợp trước khi viết thêm instrumentation.
4. Thay DirectChannel bằng một channel bất đồng bộ trong ứng dụng thực hành. Xác định timer nào đo việc chuyển giao, timer nào đo validation và cách chờ xử lý hoàn tất trước khi đọc số liệu.
5. Bổ sung một filter trước validator. Giải thích vì sao tổng message gửi vào có thể lớn hơn count của `orders.validation`, rồi chọn một điểm đo thích hợp cho số message bị loại.

Tiêu chí đạt: giải thích được ý nghĩa từng tag, xác định được tập giá trị đầu ra, và liên hệ được count với đúng sự kiện đã đo. Một schema tags tốt giúp trả lời câu hỏi vận hành cụ thể mà số meter vẫn nằm trong phạm vi dự kiến.
