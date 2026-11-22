# Filter và business validation

## 1. Mục tiêu và bối cảnh

Trong một luồng Spring Integration, việc nhận được thông điệp chưa có nghĩa yêu cầu được phép thực hiện. Một yêu cầu đặt hàng có thể đọc được, đủ trường dữ liệu, nhưng vẫn vi phạm quy tắc nghiệp vụ: đơn đã hủy, tổng tiền vượt giới hạn hoặc loại tiền chưa được hỗ trợ.

Bài học thuộc chương **Filter** của module **SPRING_INTEGRATION_CORE**. Trọng tâm là dùng `Message`, `MessageChannel`, endpoint và Java DSL để đặt cổng kiểm tra trước bước xử lý nghiệp vụ. Ta kết hợp transformer để tạo kết quả kiểm tra, filter để quyết định cho đi tiếp, và một luồng riêng để xử lý yêu cầu bị từ chối. Từ đó, người học có thể:

- Phân biệt dữ liệu sai cấu trúc, yêu cầu không hợp lệ về nghiệp vụ và lỗi hạ tầng.
- Chọn chính sách từ chối phù hợp với hợp đồng của luồng.
- Giữ lại mã lỗi, lý do và thông tin tương quan của từng yêu cầu.
- Viết kiểm thử cho nhánh được chấp nhận và nhánh bị từ chối.
- Nhận ra giới hạn của việc kiểm tra trước các thao tác cập nhật dữ liệu.

Ví dụ xuyên suốt là tiếp nhận yêu cầu gửi đơn hàng. **Được filter chấp nhận** trong bài chỉ có nghĩa vượt qua bộ quy tắc tiếp nhận; việc ghi đơn, giữ hàng hoặc thanh toán thuộc các bước tiếp theo.

## 2. Đặt filter đúng vai trò

### 2.1. Ba câu hỏi khác nhau

| Lớp kiểm tra | Câu hỏi | Ví dụ | Kết quả cần thiết kế |
|---|---|---|---|
| Cấu trúc và ràng buộc đầu vào | Có đủ dữ liệu để hiểu yêu cầu không? | Thiếu `orderId`, `total` bằng `null`, JSON sai định dạng | Phản hồi dữ liệu sai hoặc chuyển sang nhánh tiếp nhận lỗi |
| Quy tắc nghiệp vụ | Với dữ liệu và trạng thái hiện có, yêu cầu có được phép tiếp tục không? | Đơn không còn ở trạng thái nháp, tổng tiền vượt mức tiếp nhận | Kết quả từ chối có mã và lý do |
| Khả năng thực thi kỹ thuật | Hệ thống có hoàn thành được việc kiểm tra hoặc xử lý không? | Mất kết nối cơ sở dữ liệu, dịch vụ hạn mức bị timeout | Cơ chế lỗi kỹ thuật, retry có điều kiện hoặc xử lý vận hành |

Các lớp này không bị ràng buộc vào một API duy nhất. Bean Validation có thể diễn tả cả quy tắc nghiệp vụ bằng constraint tùy chỉnh. Ngược lại, một phương thức Java thông thường cũng có thể kiểm tra trường bắt buộc. Cách phân chia ở đây giúp xác định ý nghĩa của kết quả và cách xử lý tiếp theo.

JSON không đọc được cần được xử lý ở biên nhận hoặc bước chuyển đổi. Filter nhận `OrderSubmission` không tự biến một chuỗi JSON lỗi thành một kết quả validation.

### 2.2. Selector trả lời có hoặc không

Một filter ủy quyền quyết định cho selector. Giao diện cốt lõi là:

~~~java
boolean accept(Message<?> message);
~~~

`true` cho phép message đi tiếp; `false` đi vào chính sách từ chối. Filter không dùng giá trị boolean làm payload đầu ra. [Tài liệu Filter](https://docs.spring.io/spring-integration/reference/filter.html) mô tả hợp đồng này.

Đối với bài toán đặt hàng, câu hỏi phù hợp là:

> Yêu cầu này có đủ điều kiện đi vào nhánh xử lý đơn hàng không?

Các tác vụ như lưu đơn, trừ tồn kho và gọi cổng thanh toán nên nằm ở endpoint thực thi phía sau. Nếu đặt chúng trong selector, việc đánh giá lại điều kiện có thể lặp tác dụng phụ.

### 2.3. Filter, transformer và router phối hợp thế nào?

| Thành phần | Trách nhiệm trong ví dụ |
|---|---|
| Transformer trước filter | Đánh giá quy tắc và tạo `CheckedOrder` chứa yêu cầu cùng các vi phạm |
| Filter | Đọc kết quả đã đánh giá để quyết định cho đi tiếp |
| Transformer nhánh được chấp nhận | Lấy lại `OrderSubmission` để bước sau không phụ thuộc mô hình validation |
| Nhánh discard | Chuyển kết quả không hợp lệ thành `OrderRejected` |
| Router, khi cần | Chọn giữa nhiều kết quả nghiệp vụ như chấp nhận, yêu cầu duyệt thủ công và từ chối |

Với một cổng đi tiếp hoặc từ chối, filter diễn tả ý định rõ ràng. Khi có nhiều đích nghiệp vụ ngang hàng, mô hình kết quả cùng router thường dễ đọc hơn một chuỗi filter lồng nhau.

## 3. Chọn hợp đồng khi bị từ chối

### 3.1. Các chính sách cơ bản

Bảng sau áp dụng khi selector trả `false` và việc gửi sang discard channel, nếu có, hoàn tất bình thường:

| `discardChannel` | `throwExceptionOnRejection` | Hành vi |
|---|---|---|
| Không cấu hình | `false`, mặc định | Không chuyển tiếp message |
| Có cấu hình | `false` | Gửi message sang discard channel |
| Không cấu hình | `true` | Ném `MessageRejectedException` |
| Có cấu hình | `true` | Gửi sang discard channel, sau đó ném `MessageRejectedException` |

`discardChannel` và `throwExceptionOnRejection` là hai tùy chọn độc lập; cấu hình cả hai không làm mất hành vi ném lỗi. [API FilterEndpointSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/FilterEndpointSpec.html) mô tả thứ tự này.

Trong cấu hình mặc định không có discard channel, Spring Integration từ 6.1 ghi cảnh báo cho message bị loại. Cảnh báo trong log không thay thế phản hồi nghiệp vụ hay nơi lưu yêu cầu bị từ chối. [Tài liệu Filter](https://docs.spring.io/spring-integration/reference/filter.html)

Trong ví dụ chính, yêu cầu không hợp lệ là một kết quả đã dự kiến. Ta chọn **discard channel và không ném exception** để lưu được lý do mà không đưa tất cả trường hợp từ chối vào cơ chế lỗi kỹ thuật.

### 3.2. False khác với exception trong selector

Nếu validator trả kết quả có vi phạm rồi selector trả `false`, đó là một lần từ chối theo chính sách filter.

Nếu validator gọi dịch vụ ngoài và nhận timeout, hoặc selector gặp `NullPointerException`, việc xử lý thất bại bằng exception. Filter không tự chuyển exception đó thành `false` và cũng không tự tạo danh sách vi phạm. Cơ chế rejection chỉ điều khiển nhánh selector không chấp nhận message. [API MessageFilter](https://docs.spring.io/spring-integration/api/org/springframework/integration/filter/MessageFilter.html)

Vì vậy, tránh viết:

~~~java
// Không phân biệt được yêu cầu sai với hệ thống không kiểm tra được.
try {
    return customerService.canPlaceOrder(order.customerId());
} catch (Exception ex) {
    return false;
}
~~~

Một timeout không đủ bằng chứng để kết luận khách hàng không đủ điều kiện. Hãy để lỗi kỹ thuật đi vào chính sách xử lý lỗi thích hợp hoặc biểu diễn trạng thái chưa kiểm tra được một cách tường minh.

## 4. Thiết kế bộ quy tắc cho ví dụ

Giả sử nghiệp vụ tiếp nhận đơn quy định:

1. `orderId`, `customerId`, `currency` không được để trống; `total` và `status` phải tồn tại.
2. Chỉ tiếp nhận đơn có trạng thái `DRAFT`.
3. `total` phải lớn hơn 0 và không vượt quá 50.000.000.
4. Chỉ hỗ trợ `VND`.

Đây là các quy tắc minh họa cho một dịch vụ cụ thể, không phải giới hạn có sẵn của Spring Integration. Dữ liệu đầu vào đã được chuyển thành đối tượng Java trước khi đi vào flow.

### 4.1. Đánh giá một lần, sử dụng kết quả ở cả hai nhánh

Nếu selector chỉ trả boolean, nhánh từ chối thường không biết lỗi nào đã xảy ra. Gọi lại validator ở nhánh đó có thể làm tăng chi phí và tạo kết quả khác nếu điều kiện bên ngoài đã thay đổi.

Trong bài, ta tạo một đối tượng bao:

~~~text
CheckedOrder
├── order: OrderSubmission
└── validation: ValidationResult
    └── violations: List<Violation>
~~~

Filter đọc `validation.valid()`. Nhánh từ chối dùng chính danh sách vi phạm đã có. Không lưu kết quả “lần kiểm tra gần nhất” vào một field của singleton bean; nhiều message có thể được xử lý đồng thời.

Mỗi vi phạm gồm:

| Thuộc tính | Mục đích |
|---|---|
| `code` | Mã ổn định để phía gọi, kiểm thử và thống kê sử dụng |
| `field` | Trường hoặc phạm vi liên quan tới lỗi |
| `message` | Diễn giải dành cho người đọc |

Chẳng hạn, `TOTAL_LIMIT_EXCEEDED` ổn định hơn việc kiểm thử chuỗi “Tổng tiền vượt giới hạn tiếp nhận”, vì nội dung diễn giải có thể được dịch hoặc sửa.

### 4.2. Luồng thông điệp

~~~mermaid
flowchart TD
    A["ordersIn: OrderSubmission"] --> B["Transformer: đánh giá quy tắc"]
    B --> C["CheckedOrder"]
    C --> D{"Filter: validation.valid()"}
    D -->|true| E["Transformer: lấy OrderSubmission"]
    E --> F["ordersAccepted"]
    D -->|false| G["ordersRejected: CheckedOrder"]
    G --> H["Transformer: tạo OrderRejected"]
    H --> I["rejectionEvents"]
~~~

Tên `ordersAccepted` biểu thị đã qua kiểm tra tiếp nhận. Nó chưa biểu thị đơn đã được ghi thành công hoặc đã thanh toán.

## 5. Cài đặt bằng Java DSL

### 5.1. Điều kiện sử dụng ví dụ

Ví dụ dùng cú pháp Java 17 trở lên, Spring Context và Spring Integration Core có API `IntegrationFlow.from(...)`. Các phụ thuộc nền tảng cần có:

- `org.springframework:spring-context`.
- `org.springframework.integration:spring-integration-core`.
- `org.junit.jupiter:junit-jupiter` cho đoạn kiểm thử ở phần sau.

Chọn các phiên bản tương thích theo nền tảng quản lý dependency của dự án. Nếu dùng Spring Boot, có thể nhận các phụ thuộc chính qua starter Integration. Ví dụ không yêu cầu broker, cơ sở dữ liệu hay dịch vụ bên ngoài.

### 5.2. Cấu hình, mô hình và validator

Đoạn dưới là một lớp hoàn chỉnh; các kiểu dữ liệu được đặt lồng trong lớp cấu hình để dễ theo dõi một ví dụ tự chứa:

~~~java
package example.integration;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderValidationConfig {

    public enum OrderStatus {
        DRAFT, SUBMITTED, CANCELLED
    }

    public record OrderSubmission(
            String orderId,
            String customerId,
            BigDecimal total,
            String currency,
            OrderStatus status) {
    }

    public record Violation(
            String code,
            String field,
            String message) {
    }

    public record ValidationResult(List<Violation> violations) {

        public ValidationResult {
            violations = List.copyOf(violations);
        }

        public boolean valid() {
            return violations.isEmpty();
        }
    }

    public record CheckedOrder(
            OrderSubmission order,
            ValidationResult validation) {
    }

    public record OrderRejected(
            String orderId,
            List<Violation> violations) {

        public OrderRejected {
            violations = List.copyOf(violations);
        }
    }

    public static class OrderPolicy {

        private static final BigDecimal MAX_TOTAL =
                new BigDecimal("50000000");

        public ValidationResult validate(OrderSubmission order) {
            List<Violation> violations = new ArrayList<>();

            if (blank(order.orderId())) {
                violations.add(new Violation(
                        "MISSING_ORDER_ID", "orderId",
                        "Cần cung cấp mã đơn hàng"));
            }
            if (blank(order.customerId())) {
                violations.add(new Violation(
                        "MISSING_CUSTOMER_ID", "customerId",
                        "Cần cung cấp mã khách hàng"));
            }
            if (order.total() == null) {
                violations.add(new Violation(
                        "MISSING_TOTAL", "total",
                        "Cần cung cấp tổng tiền"));
            }
            if (blank(order.currency())) {
                violations.add(new Violation(
                        "MISSING_CURRENCY", "currency",
                        "Cần cung cấp loại tiền"));
            }
            if (order.status() == null) {
                violations.add(new Violation(
                        "MISSING_STATUS", "status",
                        "Cần cung cấp trạng thái đơn hàng"));
            }

            // Chỉ đánh giá quy tắc nghiệp vụ khi có đủ dữ liệu.
            if (!violations.isEmpty()) {
                return new ValidationResult(violations);
            }

            if (order.status() != OrderStatus.DRAFT) {
                violations.add(new Violation(
                        "ORDER_NOT_DRAFT", "status",
                        "Chỉ tiếp nhận đơn hàng ở trạng thái nháp"));
            }
            if (order.total().signum() <= 0) {
                violations.add(new Violation(
                        "TOTAL_NOT_POSITIVE", "total",
                        "Tổng tiền phải lớn hơn 0"));
            }
            if (order.total().compareTo(MAX_TOTAL) > 0) {
                violations.add(new Violation(
                        "TOTAL_LIMIT_EXCEEDED", "total",
                        "Tổng tiền vượt giới hạn tiếp nhận"));
            }
            if (!"VND".equals(order.currency())) {
                violations.add(new Violation(
                        "CURRENCY_NOT_SUPPORTED", "currency",
                        "Dịch vụ chỉ tiếp nhận đơn hàng bằng VND"));
            }

            return new ValidationResult(violations);
        }

        private boolean blank(String value) {
            return value == null || value.isBlank();
        }
    }

    @Bean
    public OrderPolicy orderPolicy() {
        return new OrderPolicy();
    }

    @Bean
    public MessageChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel ordersRejected() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel ordersAccepted() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel rejectionEvents() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow orderValidationFlow(OrderPolicy orderPolicy) {
        return IntegrationFlow.from("ordersIn")
                .transform(OrderSubmission.class,
                        order -> new CheckedOrder(
                                order, orderPolicy.validate(order)))
                .filter(CheckedOrder.class,
                        checked -> checked.validation().valid(),
                        endpoint -> endpoint
                                .id("businessValidationFilter")
                                .discardChannel("ordersRejected")
                                .throwExceptionOnRejection(false))
                .transform(CheckedOrder.class, CheckedOrder::order)
                .channel("ordersAccepted")
                .get();
    }

    @Bean
    public IntegrationFlow rejectedOrdersFlow() {
        return IntegrationFlow.from("ordersRejected")
                .transform(CheckedOrder.class,
                        checked -> new OrderRejected(
                                checked.order().orderId(),
                                checked.validation().violations()))
                .channel("rejectionEvents")
                .get();
    }
}
~~~

### 5.3. Đọc ví dụ theo trách nhiệm

`OrderPolicy` không phụ thuộc API messaging. Nó tạo một danh sách vi phạm riêng cho mỗi lần gọi. `List.copyOf(...)` giúp các nhánh không sửa danh sách kết quả sau khi đánh giá. Phép so sánh tiền dùng `BigDecimal.compareTo(...)`; không dùng `equals(...)` để so sánh giá trị vì scale có thể khác nhau.

Validator thu thập các lỗi cấu trúc trước. Khi có lỗi ở lớp này, nó trả về ngay, tránh đọc thuộc tính chưa tồn tại. Khi đủ dữ liệu, nó thu thập toàn bộ vi phạm nghiệp vụ của ví dụ, giúp bên gửi sửa nhiều vấn đề trong một lượt.

`ordersIn` và `ordersRejected` là `DirectChannel`. Hai `QueueChannel` cuối flow giữ kết quả để kiểm thử đọc ra; việc gửi vào chúng chưa khởi chạy một bước nghiệp vụ tiếp theo. Một endpoint tiêu thụ queue về sau sẽ cần poller phù hợp. Queue mặc định trong cấu hình này lưu trong bộ nhớ, không phải nơi lưu bền vững. [Các loại MessageChannel](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Dung lượng 100 chỉ phục vụ ví dụ nhỏ. Khi không có consumer và queue đầy, việc gửi có thể chờ; trong triển khai thật cần thiết kế consumer, giới hạn chờ và chính sách khi đầu ra quá tải.

### 5.4. Payload trên discard channel là gì?

Ở vị trí filter, payload đang là `CheckedOrder`. Vì vậy `ordersRejected` nhận mô hình này, không phải `OrderSubmission` ban đầu và cũng không phải `ErrorMessage`. Transformer của nhánh từ chối chủ động tạo `OrderRejected` từ kết quả đã đánh giá.

Filter không bổ sung sẵn các mã như `ORDER_NOT_DRAFT`. Chúng là một phần của mô hình nghiệp vụ do ứng dụng định nghĩa.

## 6. Kiểm thử hợp đồng của hai nhánh

### 6.1. Những điều cần chứng minh

Chỉ kiểm tra `ordersIn.send(...)` trả `true` là chưa đủ. Kết quả gửi thành công không đồng nghĩa yêu cầu hợp lệ về nghiệp vụ: một message bị filter từ chối vẫn có thể được xử lý bình thường ở discard flow.

Với ví dụ này, mỗi kiểm thử cần quan sát đầu ra:

| Tình huống | `ordersAccepted` | `rejectionEvents` |
|---|---|---|
| Đơn nháp, VND, tổng tiền dương trong giới hạn | Một `OrderSubmission` | Không có |
| Đúng ngưỡng 50.000.000 | Một `OrderSubmission` | Không có |
| Đơn bị hủy, vượt giới hạn, loại tiền USD | Không có | Một `OrderRejected` với ba mã vi phạm |
| Thiếu `total` | Không có | Một `OrderRejected` với `MISSING_TOTAL` |

Với các quy tắc thuần dữ liệu, nên bổ sung trường hợp tổng tiền bằng 0, tổng tiền âm, vượt ngưỡng một đơn vị, ID chỉ chứa khoảng trắng và trạng thái `null`. Không cần dựng toàn bộ flow để kiểm thử từng phép so sánh của `OrderPolicy`.

### 6.2. Ví dụ kiểm thử bằng JUnit Jupiter

Lớp sau dùng các kiểu lồng trong `OrderValidationConfig`. Mỗi test tạo context riêng, nhờ đó message của test trước không còn nằm trong queue của test sau:

~~~java
package example.integration;

import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import example.integration.OrderValidationConfig.OrderRejected;
import example.integration.OrderValidationConfig.OrderStatus;
import example.integration.OrderValidationConfig.OrderSubmission;
import example.integration.OrderValidationConfig.Violation;

import static org.junit.jupiter.api.Assertions.*;

class OrderValidationFlowTest {

    private AnnotationConfigApplicationContext context;
    private MessageChannel input;
    private QueueChannel accepted;
    private QueueChannel rejected;

    @BeforeEach
    void setUp() {
        context = new AnnotationConfigApplicationContext(
                OrderValidationConfig.class);
        input = context.getBean("ordersIn", MessageChannel.class);
        accepted = context.getBean("ordersAccepted", QueueChannel.class);
        rejected = context.getBean("rejectionEvents", QueueChannel.class);
    }

    @AfterEach
    void tearDown() {
        context.close();
    }

    @Test
    void acceptsOrderAtUpperLimitAndPreservesRequestId() {
        var order = new OrderSubmission(
                "ORD-1001", "CUS-01",
                new BigDecimal("50000000"),
                "VND", OrderStatus.DRAFT);

        boolean sent = input.send(MessageBuilder.withPayload(order)
                .setHeader("requestId", "REQ-1001")
                .build());

        assertTrue(sent);
        Message<?> message = accepted.receive(0);
        assertNotNull(message);
        assertEquals(order, message.getPayload());
        assertEquals("REQ-1001",
                message.getHeaders().get("requestId"));
        assertNull(accepted.receive(0));
        assertNull(rejected.receive(0));
    }

    @Test
    void rejectsOrderWithAllBusinessViolations() {
        var order = new OrderSubmission(
                "ORD-1002", "CUS-02",
                new BigDecimal("60000000"),
                "USD", OrderStatus.CANCELLED);

        assertTrue(input.send(MessageBuilder.withPayload(order).build()));

        Message<?> message = rejected.receive(0);
        assertNotNull(message);
        OrderRejected event = assertInstanceOf(
                OrderRejected.class, message.getPayload());
        assertEquals("ORD-1002", event.orderId());
        assertEquals(3, event.violations().size());
        Set<String> codes = event.violations().stream()
                .map(Violation::code)
                .collect(Collectors.toSet());
        assertEquals(Set.of(
                "ORDER_NOT_DRAFT",
                "TOTAL_LIMIT_EXCEEDED",
                "CURRENCY_NOT_SUPPORTED"), codes);
        assertNull(accepted.receive(0));
        assertNull(rejected.receive(0));
    }

    @Test
    void turnsMissingTotalIntoValidationResult() {
        var order = new OrderSubmission(
                "ORD-1003", "CUS-03",
                null, "VND", OrderStatus.DRAFT);

        assertTrue(input.send(MessageBuilder.withPayload(order).build()));

        Message<?> message = rejected.receive(0);
        assertNotNull(message);
        OrderRejected event = assertInstanceOf(
                OrderRejected.class, message.getPayload());
        assertEquals(1, event.violations().size());
        assertEquals("MISSING_TOTAL",
                event.violations().get(0).code());
        assertNull(accepted.receive(0));
        assertNull(rejected.receive(0));
    }
}
~~~

`receive(0)` không chờ. Nó phù hợp ở đây vì quá trình đánh giá và đưa kết quả vào queue chạy đồng bộ qua các `DirectChannel`, trước khi `send(...)` trả về. Nếu thay luồng bằng xử lý qua executor hoặc broker, cần thời gian chờ hữu hạn phù hợp; không giữ nguyên giả định đồng bộ. [Các loại MessageChannel](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Test nhánh bị từ chối kiểm tra cả mã lỗi lẫn sự vắng mặt của message ở nhánh được chấp nhận. Cách này phát hiện lỗi cấu hình cho message không hợp lệ đi tiếp, thay vì chỉ xác nhận có phát sự kiện từ chối.

## 7. Khi kết hợp với Bean Validation

Trong ví dụ đầy đủ, các trường bắt buộc được kiểm tra bằng Java để không cần provider bổ sung. Nếu dự án đã dùng Jakarta Bean Validation, có thể thay phần kiểm tra cấu trúc bằng constraint trên một DTO đầu vào:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import example.integration.OrderValidationConfig.OrderStatus;

public record OrderInput(
        @NotBlank String orderId,
        @NotBlank String customerId,
        @NotNull BigDecimal total,
        @NotBlank String currency,
        @NotNull OrderStatus status) {
}
~~~

Spring có `LocalValidatorFactoryBean` để cung cấp `jakarta.validation.Validator` khi có một Bean Validation provider tương thích trong classpath. Các constraint chỉ được đánh giá khi validation được kích hoạt, chẳng hạn bằng lời gọi `validator.validate(input)` trong bước đầu flow. [Java Bean Validation trong Spring](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)

Một cách tổ chức là:

~~~text
OrderInput
  -> validator.validate(input)
  -> có constraint violation: tạo kết quả dữ liệu sai
  -> không có violation: chuyển thành OrderSubmission
  -> đánh giá quy tắc tiếp nhận
  -> filter
~~~

Không mặc định rằng `@Valid` trên một đối tượng bất kỳ sẽ khiến mọi message đi qua Java DSL tự được kiểm tra. Nếu dùng method validation qua proxy hoặc cơ chế validation ở biên HTTP, cần xác định rõ đường gọi nào thực sự kích hoạt nó.

Khi chuyển constraint violation thành `Violation` của ứng dụng:

- Ánh xạ sang mã lỗi ổn định theo hợp đồng; không lấy thông báo đã dịch làm mã.
- Không phụ thuộc thứ tự duyệt tập violation; sắp xếp nếu phản hồi cần thứ tự ổn định.
- Tránh đưa giá trị đầu vào nhạy cảm vào thông báo hoặc sự kiện từ chối.

Sau bước này, vẫn có thể dùng cùng mô hình `ValidationResult` và cùng cách xử lý nhánh bị từ chối. Không cần sao chép quy tắc bắt buộc trường sang cả Bean Validation lẫn `OrderPolicy`.

## 8. Trường hợp muốn ném exception khi bị từ chối

Một số hợp đồng yêu cầu caller nhận lỗi ngay khi yêu cầu bị chặn. Khi đó, có thể thay phần cấu hình filter bằng đoạn minh họa sau:

~~~java
.filter(CheckedOrder.class,
        checked -> checked.validation().valid(),
        endpoint -> endpoint
                .id("strictBusinessValidationFilter")
                .throwExceptionOnRejection(true))
~~~

Đây là **cấu hình thay thế**, không phải filter thứ hai cần nối vào ví dụ chính. Nó tạo `MessageRejectedException` khi selector trả `false`; exception đó không tự trở thành phản hồi HTTP có mã trạng thái và danh sách vi phạm do ứng dụng định nghĩa.

Nếu cần truyền lỗi nghiệp vụ chi tiết bằng exception, có thể thiết kế một exception riêng chứa `ValidationResult` tại một bước xử lý phù hợp, rồi ánh xạ tại biên. Hãy chọn rõ một hợp đồng: phản hồi kết quả, sự kiện từ chối hoặc exception.

### 8.1. Đường đi của exception phụ thuộc cách thực thi

Gửi trực tiếp qua `DirectChannel` thực thi handler trên thread của caller; exception có thể truyền về lời gọi gửi, có thể được framework bao trong messaging exception. Với tác vụ bất đồng bộ, chẳng hạn poller, lỗi thường được công bố dưới dạng `ErrorMessage` qua cơ chế error handler. Không thể xem header `errorChannel` là một lệnh luôn bắt mọi lỗi đồng bộ. [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)

`ordersRejected` trong ví dụ là kênh nghiệp vụ. `errorChannel` là một phần của cơ chế xử lý exception. Dù cả hai đều có thể dẫn đến việc ghi nhận sự cố, payload và ý nghĩa hợp đồng của chúng khác nhau.

### 8.2. Retry cần hiểu việc đang được lặp

Gửi lại nguyên một đơn đã hủy không làm đơn trở thành hợp lệ. Lỗi quy tắc cố định nên kết thúc bằng kết quả từ chối; lỗi kỹ thuật tạm thời mới là ứng viên cho retry có giới hạn.

Nếu đặt retry advice quanh filter, mặc định hành động discard nằm trong phạm vi advice. Lỗi ở nhánh discard hoặc rejection exception có thể khiến xử lý được lặp. Có thể cấu hình `discardWithinAdvice(false)` để chuyển hành động discard ra ngoài advice đó, nhưng vẫn phải thiết kế riêng độ tin cậy của nhánh từ chối. [Advising Filters](https://docs.spring.io/spring-integration/reference/handler-advice/advising-filters.html)

Ví dụ, ghi một bản ghi audit rồi ném exception có thể tạo nhiều bản ghi nếu toàn bộ đoạn được retry. Hãy xác định định danh yêu cầu và cách chống lặp cho các tác vụ có tác dụng phụ.

## 9. Gateway request-reply cần phản hồi cho mọi kết quả

Flow mẫu kết thúc ở các queue đầu ra để minh họa tiếp nhận và quan sát kết quả. Nó không được cấu hình làm một API request-reply hoàn chỉnh.

Giả sử gateway khai báo:

~~~java
OrderReply submit(OrderSubmission order);
~~~

Nếu nhánh thành công tạo `OrderReply` nhưng nhánh từ chối chỉ ghi log rồi kết thúc, caller không có phản hồi nghiệp vụ cho trường hợp bị chặn. Caller có thể chờ tới giới hạn reply timeout hoặc nhận kết quả không có reply tùy cấu hình.

Gateway sử dụng reply channel để nhận câu trả lời; việc message được đưa vào discard channel riêng không tự bảo đảm câu trả lời quay về caller. Cần nối rõ nhánh phản hồi và cấu hình timeout theo hợp đồng. [Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)

Ba lựa chọn thường gặp:

| Hợp đồng | Thiết kế phù hợp |
|---|---|
| Gửi một chiều, nhận kết quả sau | Gateway `void` hoặc producer một chiều; phát sự kiện chấp nhận/từ chối có thông tin tương quan |
| Trả kết quả ngay cho cả hai trường hợp | Mô hình `OrderReply` có trạng thái và mã lỗi; bảo đảm hai nhánh đều tạo reply |
| Caller xử lý lỗi bằng exception | Cấu hình rejection exception và ánh xạ lỗi rõ ràng tại biên |

Với yêu cầu trả kết quả ngay, có thể dùng transformer đánh giá rồi router chọn nhánh tạo reply. Filter vẫn hữu ích cho cổng kiểm soát, nhưng boolean của selector không phải một phản hồi nghiệp vụ.

Nếu dùng discard subflow để tạo phản hồi, cần kiểm thử rằng message thực sự đến reply channel của gateway. Việc có một giá trị trả về từ handler trong một nhánh bất kỳ chưa đủ để chứng minh toàn bộ hợp đồng request-reply đúng.

## 10. Giới hạn khi quy tắc phụ thuộc trạng thái bên ngoài

### 10.1. Kiểm tra sớm chưa bảo đảm thao tác sau đó thành công

Ví dụ đã đọc `status` từ chính yêu cầu gửi vào để đơn giản hóa. Trong hệ thống thật, trạng thái hiện tại cần được lấy từ nguồn có thẩm quyền, chẳng hạn cơ sở dữ liệu; không tin trạng thái do caller tự khai báo để quyết định một chuyển trạng thái quan trọng.

Ngay cả khi đã đọc đúng nguồn, hai thời điểm vẫn có thể khác nhau:

~~~text
T1: Validator đọc đơn ORD-2001 đang ở trạng thái DRAFT.
T2: Một luồng khác hủy đơn ORD-2001.
T3: Yêu cầu cũ vượt qua filter dựa trên kết quả tại T1.
T4: Endpoint thực thi thử chuyển đơn sang SUBMITTED.
~~~

Filter ở T3 không thể thay thế việc bảo vệ điều kiện tại T4. Bước ghi cần kiểm tra lại trong cơ chế nhất quán phù hợp: khóa lạc quan theo version, khóa trong transaction hoặc câu lệnh cập nhật có điều kiện.

Ví dụ minh họa thao tác cập nhật:

~~~sql
UPDATE orders
SET status = 'SUBMITTED',
    version = version + 1
WHERE id = :orderId
  AND status = 'DRAFT'
  AND version = :expectedVersion;
~~~

Nếu không có dòng nào được cập nhật, bước thực thi phải phân loại kết quả: trạng thái đã đổi, version không còn khớp hoặc không có đơn tương ứng. Không được kết luận thành công chỉ vì filter trước đó đã chấp nhận.

Đối với tồn kho hoặc hạn mức chi tiêu, việc kiểm tra và giữ nguồn lực cũng cần được thiết kế tại nơi quản lý nguồn lực đó. Một phép đọc “còn đủ” rồi cập nhật rời rạc có thể cho nhiều yêu cầu cùng vượt qua.

### 10.2. Quy tắc tĩnh và quy tắc cần tra cứu

| Quy tắc | Đặc điểm | Cách tổ chức nên cân nhắc |
|---|---|---|
| Tổng tiền dương, loại tiền được hỗ trợ | Đánh giá từ dữ liệu đã có | Validator thuần dữ liệu như ví dụ |
| Khách hàng đang được phép giao dịch | Phụ thuộc trạng thái bên ngoài | Bước lấy trạng thái có timeout, sau đó đánh giá chính sách |
| Giá áp dụng tại thời điểm nhận | Phụ thuộc thời gian và phiên bản quy tắc | Ghi rõ thời điểm và phiên bản được dùng để đánh giá |
| Không vượt tồn kho hoặc hạn mức dùng chung | Có tranh chấp giữa nhiều yêu cầu | Kiểm tra và giữ/cập nhật bằng cơ chế nhất quán phù hợp |

Khi cần đọc thời gian, truyền `Clock` vào validator thay vì gọi thời gian hệ thống rải rác. Kiểm thử có thể cố định đồng hồ để xác minh đúng thời điểm biên.

Nếu phải gọi dịch vụ ngoài, nên có bước lấy dữ liệu rõ ràng trước validator để tách lỗi gọi dịch vụ khỏi kết quả quy tắc. Kết quả đánh giá nên cho biết nó dựa trên dữ liệu nào nếu cần truy vết hoặc xử lý lại.

### 10.3. Không đồng nhất validation và chống xử lý lặp

Một yêu cầu hợp lệ có thể được gửi nhiều lần. Filter kiểm tra tổng tiền và trạng thái không tự bảo đảm thao tác lưu đơn hoặc thanh toán chỉ diễn ra một lần.

Nếu có retry hoặc broker có thể giao lại message, bước có tác dụng phụ cần cơ chế chống lặp theo định danh nghiệp vụ, chẳng hạn request ID được quản lý nhất quán hoặc ràng buộc duy nhất phù hợp. `MessageHeaders.ID` không nên được dùng như một định danh nghiệp vụ ổn định qua mọi lần gửi lại.

## 11. Thiết kế nhánh từ chối có thể vận hành

### 11.1. Thông tin cần giữ

Trong ứng dụng thật, một kết quả từ chối thường cần những thông tin sau, tùy hợp đồng:

| Thông tin | Công dụng |
|---|---|
| Request ID hoặc correlation ID | Liên kết yêu cầu, log và phản hồi |
| Order ID nếu có | Tra cứu đối tượng nghiệp vụ liên quan |
| Danh sách mã vi phạm | Giúp caller sửa dữ liệu, thống kê nguyên nhân |
| Thời điểm đánh giá | Giải thích kết quả khi quy tắc phụ thuộc thời gian |
| Phiên bản quy tắc | Xác định chính sách được sử dụng nếu chính sách có thay đổi |
| Định danh sự kiện hoặc khóa chống lặp | Hạn chế ghi nhận hoặc xử lý trùng |

Request ID đặc biệt hữu ích khi chính `orderId` bị thiếu. Trong ví dụ, custom header `requestId` được giữ qua các bước chuyển đổi payload thông thường và được kiểm tra ở nhánh được chấp nhận. Có thể bổ sung kiểm thử tương tự cho nhánh từ chối.

Nếu cần đưa kết quả lên broker hoặc lưu lâu dài, nên đưa các thông tin tương quan cần thiết vào hợp đồng sự kiện hoặc bộ header được hỗ trợ. Không giả định mọi đối tượng header nội bộ đều có thể tuần tự hóa và truyền qua biên hệ thống.

### 11.2. Phân biệt số message và số vi phạm

Một đơn có thể vi phạm ba quy tắc. Khi quan sát hệ thống, nên phân biệt:

- Số yêu cầu đã đánh giá.
- Số yêu cầu được chấp nhận.
- Số yêu cầu bị từ chối.
- Số lần xuất hiện của từng mã vi phạm.
- Số lần không đánh giá được vì lỗi kỹ thuật.

Ba vi phạm trên một đơn vẫn chỉ tương ứng với một yêu cầu bị từ chối. Có thể dùng mã vi phạm làm nhãn thống kê hữu hạn; tránh dùng từng order ID hoặc request ID làm nhãn metric.

Giữ log vừa đủ để truy vết theo định danh. Không cần ghi toàn bộ payload nếu nó chứa thông tin cá nhân hoặc dữ liệu thanh toán.

### 11.3. Discard channel không bảo đảm lưu bền vững

Trong ví dụ, `rejectionEvents` là queue trong bộ nhớ. Việc đưa một kết quả vào queue này không đồng nghĩa đã lưu được kết quả qua sự cố khởi động lại. Khi kết quả từ chối là dữ liệu cần bảo toàn, phải bổ sung nơi lưu bền vững hoặc cơ chế xuất sự kiện phù hợp.

Nếu nhánh discard gửi thất bại, luồng có thể phát sinh lỗi kỹ thuật. Cấu hình `throwExceptionOnRejection(false)` chỉ tắt rejection exception chủ động, không bỏ qua mọi exception của các endpoint khác.

Nếu cần cập nhật dữ liệu và phát sự kiện nhất quán, hãy thiết kế ranh giới transaction hoặc cơ chế như outbox tại nơi thực hiện các thao tác đó. Một discard channel đơn thuần không tự tạo tính nguyên tử giữa cơ sở dữ liệu và broker.

## 12. Các lỗi thiết kế thường gặp

| Cách làm | Vấn đề phát sinh | Cách sửa |
|---|---|---|
| Chỉ kiểm tra `send(...) == true` | Không biết yêu cầu được chấp nhận hay đã đi vào nhánh từ chối | Kiểm tra đầu ra và hợp đồng phản hồi |
| Selector chỉ trả `false`, không lưu lý do | Caller và người vận hành không biết quy tắc nào bị vi phạm | Đánh giá thành `ValidationResult` trước filter |
| Gọi lại validator ở nhánh discard | Tăng chi phí, có thể nhận kết quả khác lần đầu | Mang kết quả đánh giá theo từng message |
| Lưu lỗi vào field của singleton validator | Kết quả giữa các message có thể ghi đè nhau | Dùng biến cục bộ và đối tượng kết quả bất biến |
| Ghi dữ liệu hoặc thanh toán trong selector | Việc kiểm tra có tác dụng phụ và khó lặp an toàn | Đặt thao tác thực thi sau cổng kiểm tra |
| Biến mọi exception thành `false` | Lỗi hạ tầng bị báo thành lỗi nghiệp vụ | Tách kết quả từ chối và lỗi không thực hiện được việc kiểm tra |
| Đọc `status` từ request rồi tin hoàn toàn | Caller có thể cung cấp trạng thái không đúng | Đọc trạng thái từ nguồn có thẩm quyền và bảo vệ khi ghi |
| Bật retry cho mọi lần bị từ chối | Lặp yêu cầu sai mà không thay đổi kết quả | Retry có giới hạn cho lỗi có khả năng phục hồi |
| Dùng flow mẫu làm request-reply ngay | Nhánh từ chối không có reply cho caller | Thiết kế và kiểm thử đường phản hồi cho mọi kết quả |
| Xem queue trong bộ nhớ là nơi lưu lỗi cuối cùng | Mất dữ liệu khi tiến trình dừng | Chọn cơ chế lưu bền vững nếu hợp đồng yêu cầu |

## 13. Vận dụng vào một luồng mới

Khi thêm business validation cho một luồng thông điệp, bắt đầu từ hợp đồng của yêu cầu:

1. Xác định kết quả mà caller cần nhận: phản hồi ngay, sự kiện sau hay exception.
2. Liệt kê quy tắc tiếp nhận và tách lỗi dữ liệu khỏi lỗi không kiểm tra được.
3. Tạo kết quả đánh giá có mã vi phạm, không chỉ một boolean.
4. Đặt filter trước bước có tác dụng phụ và định nghĩa rõ nhánh từ chối.
5. Bảo vệ lại các điều kiện có thể thay đổi tại bước cập nhật thực tế.
6. Kiểm thử hai nhánh, các giá trị biên và cách giữ thông tin tương quan.
7. Xác định nơi lưu kết quả từ chối và hành vi khi nơi đó không sẵn sàng.

Với luồng tiếp nhận đơn trong bài, phần mở rộng thực hành hợp lý là thêm quy tắc “khách hàng được phép giao dịch”. Tạo hai tình huống riêng: dịch vụ khách hàng trả kết quả không được phép và dịch vụ khách hàng bị timeout. Tình huống đầu phải có mã từ chối nghiệp vụ; tình huống sau phải giữ được ý nghĩa lỗi kỹ thuật. Bài thực hành này giúp xác nhận rằng filter đang kiểm soát điều kiện đi tiếp, còn cơ chế xử lý lỗi vẫn phản ánh đúng khả năng thực thi của hệ thống.


