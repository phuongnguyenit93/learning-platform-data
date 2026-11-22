# Điều kiện route thuần và có thể kiểm thử

Trong **Spring Integration**, **Content-Based Router** quyết định một message sẽ đi tới channel nào dựa trên nội dung của message: payload, headers, hoặc cả hai. Router là một điểm then chốt của mô hình **Enterprise Integration Patterns (EIP)** vì nó tách **quyết định chọn đường xử lý** khỏi các handler thực hiện công việc. Một hệ thống xử lý đơn hàng có thể định tuyến đơn rủi ro cao tới nhóm duyệt thủ công, đơn ưu tiên tới luồng nhanh và những đơn còn lại tới luồng tiêu chuẩn.

Bài này thuộc chương **Content-based router** trong module **SPRING_INTEGRATION_PATTERN**. Mục tiêu của module là xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation; đồng thời biết kiểm thử, quan sát và xử lý lỗi ở từng nhánh.

Chủ đề chính là **điều kiện route thuần và có thể kiểm thử**. Thay vì đặt cả truy vấn database, đọc thời gian hiện tại và gửi message vào một phương thức router, ta tách một **chính sách định tuyến thuần** thành hàm Java nhận dữ liệu đầu vào và trả về **quyết định định tuyến**, sau đó để Spring Integration thực hiện việc chuyển message đến channel tương ứng.

## 1. Bạn sẽ học được gì?

Sau bài này, bạn có thể:

1. Giải thích Content-Based Router và phân biệt nó với Filter, Transformer, Publish–Subscribe Channel và Recipient List Router.
2. Viết điều kiện route như một hàm thuần: cùng đầu vào cho cùng kết quả, không phụ thuộc trạng thái ẩn và không tạo side effect.
3. Tách chính sách nghiệp vụ (`RoutingPolicy`) khỏi việc ánh xạ kết quả sang tên channel.
4. Tích hợp chính sách với `@Router` của Spring Integration và chuẩn bị đầy đủ channel đích.
5. Kiểm tra các trường hợp biên, giá trị không hợp lệ, thứ tự ưu tiên quy tắc và tính tất định bằng JUnit 5.
6. Kiểm thử toàn bộ flow để xác nhận message đến đúng channel, metadata được giữ và các nhánh khác không nhận message.
7. Thiết kế đường xử lý lỗi, fallback, logging và correlation mà không đưa I/O vào hàm quyết định.

## 2. Content-Based Router làm việc như thế nào?

Router nhận một message, đánh giá nội dung và trả một hoặc nhiều địa chỉ channel mà framework có thể sử dụng để chuyển message tiếp. Với router **chọn một đích**, giá trị trả về thường là tên của một channel duy nhất.

~~~mermaid
flowchart LR
    I["Inbound: OrderCreated"] --> V["Validate / Normalize"]
    V --> R{"Content-Based Router"}
    R -->|"riskScore >= 80"| H["orders.review"]
    R -->|"VIP && total >= 500"| P["orders.priority"]
    R -->|"còn lại"| S["orders.standard"]
    H --> HA["Manual review handler"]
    P --> PA["Priority handler"]
    S --> SA["Standard handler"]
~~~

Trật tự ví dụ trên rất có ý nghĩa: khi một đơn vừa có mức rủi ro cao vừa thuộc diện VIP, quy tắc **duyệt thủ công** phải thắng. Nếu thay thứ tự `if`, đơn rủi ro cao có thể bị gửi thẳng vào nhánh ưu tiên.

Một message có thể chứa:

~~~text
payload:
  orderId: order-1001
  total: 750.00
  vip: true
  riskScore: 85

headers:
  traceId: trace-1001
  tenantId: shop-a
  businessCorrelationId: order-1001
~~~

Trong trường hợp này, chính sách phải chọn `REVIEW` vì `riskScore=85`, kể cả khi `vip=true` và `total=750`.

### Router quyết định, channel chuyển và handler xử lý

| Thành phần | Trách nhiệm | Điều không nên làm |
|---|---|---|
| **Routing policy** | Tính quyết định `REVIEW` / `PRIORITY` / `STANDARD` từ dữ liệu | Gọi DB/API, gửi email, tự gửi vào channel |
| **Spring Integration Router** | Chuyển quyết định thành tên channel đích | Chứa nhiều quy tắc nghiệp vụ khó kiểm thử |
| **MessageChannel** | Vận chuyển message tới endpoint | Suy diễn lại quy tắc rủi ro/ưu tiên |
| **Handler ở nhánh đích** | Thực hiện xử lý cụ thể | Tự kiểm tra lại toàn bộ điều kiện route nếu cùng hợp đồng tin cậy |
| **Filter / validator** | Chấp nhận, từ chối hoặc báo lỗi đầu vào không đúng hợp đồng | Âm thầm biến dữ liệu sai thành một route hợp lệ |

Trong thiết kế EIP, router thường thuộc mô hình *content-based routing*, còn các handler của nhánh sau có thể là Service Activator, Transformer, Gateway hoặc một integration flow lớn hơn.

## 3. Điều kiện route "thuần" nghĩa là gì?

Một hàm định tuyến lý tưởng có dạng:

~~~text
decision = route(payload, trustedContext, immutableRules)
~~~

Hàm được gọi là **thuần** khi:

- **Tất định (deterministic):** cùng payload, cùng context và cùng bộ quy tắc thì trả cùng kết quả.
- **Không side effect:** không ghi DB, không gọi HTTP, không gửi email, không publish message, không sửa payload hay headers.
- **Không đọc trạng thái ẩn:** không tự gọi `Instant.now()`, `Math.random()`, cấu hình có thể thay đổi bất ngờ hay cache mutable trong quá trình quyết định.
- **Có hợp đồng đầu vào rõ:** trường nào được phép thiếu, kiểu dữ liệu nào hợp lệ và xử lý bất thường ra sao đều được định nghĩa.
- **Có tập kết quả đóng:** ưu tiên enum `REVIEW`, `PRIORITY`, `STANDARD` hơn các chuỗi channel rải rác ở nhiều câu lệnh `if`.

Một hàm thuần vẫn có thể **ném exception một cách tất định** cho dữ liệu vi phạm hợp đồng. Tuy nhiên, nếu message lỗi cần được phân nhánh riêng, ta nên có Filter/validation trước router hoặc một quyết định `REJECT` được thiết kế tường minh.

### 3.1. Tại sao tính thuần hỗ trợ kiểm thử?

Với hàm không phụ thuộc Spring context, JUnit có thể gọi trực tiếp:

~~~java
assertEquals(
    Decision.REVIEW,
    policy.decide(orderWithRiskScore85));
~~~

Không cần khởi động broker, không cần tạo database giả và không cần chờ task async. Các trường hợp biên dễ đọc: 79 hay 80 điểm, tổng tiền 499.99 hay 500.00, khách VIP hay thường.

**Nhưng unit test policy chưa đủ:** nó xác nhận *quyết định nghiệp vụ*, chưa chứng minh Spring đã resolve đúng channel và chuyển message đến đúng handler. Ta sẽ kết hợp thêm một integration test ở phần sau.

### 3.2. Ví dụ cách viết gây khó kiểm thử

~~~java
// Minh họa ANTI-PATTERN; không dùng làm router thực tế.
public String badRoute(OrderCandidate order) {
    int score = riskApi.fetchCurrentScore(order.orderId());
    boolean flashSale = LocalDate.now().getDayOfWeek()
            == DayOfWeek.FRIDAY;
    metrics.increment("router_invoked");

    if (score >= 80) {
        notificationService.sendRiskAlert(order.orderId());
        return "orders.review";
    }
    return flashSale ? "orders.priority" : "orders.standard";
}
~~~

Các sự phụ thuộc ở đây gây vấn đề:

- API có thể timeout hoặc trả giá trị khác giữa hai lần cùng một đơn.
- Kết quả thay đổi theo ngày trên máy chạy.
- Một lần kiểm thử có thể thực sự gửi cảnh báo.
- Retry router có thể nhân đôi side effect `sendRiskAlert`.
- Đơn không thể replay với quyết định cũ khi cấu hình hoặc trạng thái ngoài đã thay đổi.

Chỉ nên lấy dữ liệu cần thiết ở một **bước riêng trước router**, đóng gói dữ liệu đó thành payload hoặc một context bất biến và truyền vào chính sách. Điều này không loại bỏ lỗi ở bước enrich/risk lookup; nó giúp **phạm vi lỗi, retry và trách nhiệm** rõ ràng.

## 4. Thiết kế chính sách định tuyến bằng Java thuần

Ta xây một chính sách nhất quán cho đơn hàng. Có ba nhánh:

1. `REVIEW`: điểm rủi ro từ **80** trở lên, ưu tiên cao nhất.
2. `PRIORITY`: không thuộc nhóm review, là khách VIP **và** tổng tiền từ **500.00** trở lên.
3. `STANDARD`: tất cả đơn hợp lệ còn lại.

Ngưỡng ở đây là dữ liệu minh họa cho bài học, không phải một quy tắc nghiệp vụ phổ quát.

### 4.1. Định nghĩa payload bất biến

~~~java
import java.math.BigDecimal;

public record OrderCandidate(
        String orderId,
        BigDecimal total,
        boolean vip,
        int riskScore
) {}
~~~

`record` thuận tiện vì không sinh setter. `String` và `BigDecimal` là các kiểu giá trị bất biến, còn `boolean` và `int` là primitive. Do vậy, payload trên không có field mutable chia sẻ giữa các nhánh. Trong ứng dụng thật, có thể thêm currency, source, metadata xác thực và schema version theo hợp đồng.

Đầu vào của policy được giả định đã có dữ liệu đầy đủ, sau khi bước decode/validation/enrichment cung cấp điểm rủi ro đáng tin cậy.

### 4.2. Định nghĩa kết quả bằng enum

~~~java
public enum RouteDecision {
    REVIEW,
    PRIORITY,
    STANDARD
}
~~~

Enum giúp compiler buộc người viết xử lý những quyết định đã khai báo. Nó cũng tách từ vựng nghiệp vụ khỏi tên channel thực tế: `PRIORITY` là ý nghĩa xử lý; `orders.priority` là địa chỉ channel hiện tại. Đổi tên channel không cần thay quy tắc tính điểm ưu tiên.

### 4.3. Viết một policy thuần

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public final class OrderRoutingPolicy {

    private static final int REVIEW_RISK_THRESHOLD = 80;
    private static final BigDecimal PRIORITY_MIN_TOTAL =
            new BigDecimal("500.00");

    public RouteDecision decide(OrderCandidate order) {
        Objects.requireNonNull(order, "order");

        if (order.orderId() == null || order.orderId().isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        if (order.total() == null || order.total().signum() < 0) {
            throw new IllegalArgumentException(
                    "total must be non-negative");
        }
        if (order.riskScore() < 0 || order.riskScore() > 100) {
            throw new IllegalArgumentException(
                    "riskScore must be between 0 and 100");
        }

        // Chính sách ưu tiên: review thắng mọi quyết định khác.
        if (order.riskScore() >= REVIEW_RISK_THRESHOLD) {
            return RouteDecision.REVIEW;
        }

        if (order.vip()
                && order.total().compareTo(PRIORITY_MIN_TOTAL) >= 0) {
            return RouteDecision.PRIORITY;
        }

        return RouteDecision.STANDARD;
    }
}
~~~

Chính sách trên không biết Spring Integration, channel, bean name hay database. Nó có thể được dùng trong JUnit, console app hoặc adapter khác. Vì class không giữ trạng thái thay đổi và toàn bộ input là giá trị bất biến, một instance có thể được gọi an toàn bởi nhiều thread.

**Vì sao dùng `compareTo` thay `equals` cho `BigDecimal`?** `new BigDecimal("500.0").equals(new BigDecimal("500.00"))` trả `false` vì khác scale; `compareTo` kiểm tra thứ tự giá trị số. Khi so ngưỡng tiền, `compareTo(...) >= 0` đúng với ý nghĩa “từ 500 trở lên”.

**Vì sao validate ngay trong policy khi đã có validation ở đầu vào?** Các kiểm tra ngắn này bảo vệ hợp đồng của hàm thuần trước mọi caller. Ở flow thật, validation tại ingress vẫn cần xử lý lỗi thân thiện cho nguồn gửi và bảo vệ ranh giới tin cậy. Chúng đảm nhận hai vai trò khác nhau.

### 4.4. Bảng quyết định

| Risk score | VIP | Total | Kết quả | Lý do |
|---:|---|---:|---|---|
| 85 | Có | 750.00 | `REVIEW` | Rủi ro cao được ưu tiên trước |
| 80 | Không | 10.00 | `REVIEW` | Đúng ngưỡng rủi ro |
| 79 | Có | 500.00 | `PRIORITY` | VIP và đạt ngưỡng |
| 79 | Có | 499.99 | `STANDARD` | Chưa đạt ngưỡng tổng tiền |
| 0 | Không | 900.00 | `STANDARD` | Không VIP |
| 0 | Có | 500.0 | `PRIORITY` | So sánh giá trị, không so scale |
| 101 | Có | 900.00 | Exception | Vi phạm hợp đồng score |
| 50 | Có | -1.00 | Exception | Tổng tiền âm |

Bảng này có thể được dịch gần như trực tiếp thành test parameterized.

## 5. Tích hợp policy vào Spring Integration Router

Bước tiếp theo là viết một adapter nhỏ để Spring gọi policy, sau đó ánh xạ `RouteDecision` sang channel name.

### 5.1. Router chỉ ánh xạ kết quả

~~~java
import org.springframework.integration.annotation.Router;

public final class OrderRouter {

    private final OrderRoutingPolicy policy;

    public OrderRouter(OrderRoutingPolicy policy) {
        this.policy = policy;
    }

    @Router(inputChannel = "orders.toRoute")
    public String select(OrderCandidate order) {
        return switch (policy.decide(order)) {
            case REVIEW   -> "orders.review";
            case PRIORITY -> "orders.priority";
            case STANDARD -> "orders.standard";
        };
    }
}
~~~

Spring Integration cung cấp payload của message cho tham số `OrderCandidate order` theo cơ chế method invocation của endpoint. Phương thức `select` trả một `String` là **tên channel đích**, để framework tìm channel tương ứng rồi gửi **message đầu vào** sang đó.

Router ở trên không gửi message thủ công, không thay đổi headers, không gọi handler bên dưới và không ném lỗi cho các đơn hợp lệ. Quy tắc nghiệp vụ vẫn nằm duy nhất trong `OrderRoutingPolicy`.

### 5.2. Khai báo các channel và bean

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OrderRoutingConfiguration {

    @Bean(name = "orders.toRoute")
    public MessageChannel ordersToRoute() {
        return new DirectChannel();
    }

    // Dùng QueueChannel để dễ nhận và kiểm thử.
    @Bean(name = "orders.review")
    public PollableChannel reviewQueue() {
        return new QueueChannel();
    }

    @Bean(name = "orders.priority")
    public PollableChannel priorityQueue() {
        return new QueueChannel();
    }

    @Bean(name = "orders.standard")
    public PollableChannel standardQueue() {
        return new QueueChannel();
    }

    @Bean
    public OrderRoutingPolicy orderRoutingPolicy() {
        return new OrderRoutingPolicy();
    }

    @Bean
    public OrderRouter orderRouter(OrderRoutingPolicy policy) {
        return new OrderRouter(policy);
    }
}
~~~

Trong ứng dụng thực tế, ba output channel thường nối tiếp đến service activator hoặc subflow để xử lý; ở đây `QueueChannel` được dùng để quan sát kết quả routing. Queue mặc định là in-memory, **không phải hàng đợi bền vững qua restart**.

`@EnableIntegration` bật hạ tầng xử lý annotation/endpoint cần thiết cho cấu hình thuần Spring. Với Spring Boot và starter Integration phù hợp, có thể có cơ chế tự cấu hình tương đương; cần chọn một cách nhất quán theo dự án.

### 5.3. Producer gửi một message

~~~java
import java.math.BigDecimal;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

void submit(MessageChannel ordersToRoute) {
    OrderCandidate candidate = new OrderCandidate(
            "order-1001",
            new BigDecimal("750.00"),
            true,
            85);

    Message<OrderCandidate> message = MessageBuilder
            .withPayload(candidate)
            .setHeader("traceId", "trace-1001")
            .setHeader("businessCorrelationId", "order-1001")
            .build();

    boolean accepted = ordersToRoute.send(message);
}
~~~

Trong ví dụ, message sẽ được định tuyến tới `orders.review`. Header `traceId` và `businessCorrelationId` ở lại trên **message được chuyển tiếp**. `accepted=true` cho biết lời gọi send đã được chấp nhận ở tầng messaging theo topology, **không** tự chứng minh đơn hàng đã được duyệt hay ghi thành công.

Các đoạn `OrderCandidate`, `RouteDecision`, `OrderRoutingPolicy`, `OrderRouter` và `OrderRoutingConfiguration` ở mục 4–5 tạo thành một ví dụ; đặt chúng trong package ứng dụng phù hợp và import từ package đó.

## 6. Kiểm thử policy hoàn toàn không cần Spring

Tính thuần bộc lộ rõ nhất qua unit test: khởi tạo class Java trực tiếp, xác định đầu vào, xác nhận kết quả. Không cần `ApplicationContext`, broker, network hoặc clock.

### 6.1. Parameterized test cho bảng quyết định

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class OrderRoutingPolicyTest {

    private final OrderRoutingPolicy policy =
            new OrderRoutingPolicy();

    static Stream<Arguments> routes() {
        return Stream.of(
                Arguments.of(85, true, "750.00",
                        RouteDecision.REVIEW),
                Arguments.of(80, false, "10.00",
                        RouteDecision.REVIEW),
                Arguments.of(79, true, "500.00",
                        RouteDecision.PRIORITY),
                Arguments.of(79, true, "499.99",
                        RouteDecision.STANDARD),
                Arguments.of(0, false, "900.00",
                        RouteDecision.STANDARD),
                Arguments.of(0, true, "500.0",
                        RouteDecision.PRIORITY));
    }

    @ParameterizedTest
    @MethodSource("routes")
    void decidesExpectedRoute(
            int riskScore,
            boolean vip,
            String total,
            RouteDecision expected) {

        OrderCandidate order = new OrderCandidate(
                "order-1001",
                new BigDecimal(total),
                vip,
                riskScore);

        assertEquals(expected, policy.decide(order));
    }
}
~~~

Test này bao phủ các ranh giới **79/80** và **499.99/500.00**, đồng thời chứng minh rằng rủi ro cao thắng điều kiện VIP. Nếu đội ngũ đổi ngưỡng hoặc thứ tự ưu tiên, test sẽ phát hiện tác động lên contract.

### 6.2. Kiểm thử đầu vào không hợp lệ

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class RoutingPolicyValidationTest {

    private final OrderRoutingPolicy policy =
            new OrderRoutingPolicy();

    @Test
    void rejectsRiskOutsideAllowedRange() {
        OrderCandidate invalid = new OrderCandidate(
                "order-1001",
                new BigDecimal("100.00"),
                true,
                101);

        assertThrows(IllegalArgumentException.class,
                () -> policy.decide(invalid));
    }

    @Test
    void rejectsNegativeTotal() {
        OrderCandidate invalid = new OrderCandidate(
                "order-1001",
                new BigDecimal("-1.00"),
                false,
                10);

        assertThrows(IllegalArgumentException.class,
                () -> policy.decide(invalid));
    }

    @Test
    void rejectsMissingOrderId() {
        OrderCandidate invalid = new OrderCandidate(
                "  ",
                new BigDecimal("100.00"),
                false,
                10);

        assertThrows(IllegalArgumentException.class,
                () -> policy.decide(invalid));
    }
}
~~~

Những test này xác nhận policy **không tự biến lỗi dữ liệu thành route tiêu chuẩn**. Để trả thông báo thân thiện cho bên gọi, endpoint trước router nên sử dụng validation/filter hoặc cơ chế báo lỗi có cấu trúc.

### 6.3. Kiểm tra cùng đầu vào luôn cho cùng kết quả

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class RoutingDeterminismTest {

    @Test
    void repeatsSameDecisionForSameInput() {
        OrderRoutingPolicy policy = new OrderRoutingPolicy();

        OrderCandidate order = new OrderCandidate(
                "order-1001",
                new BigDecimal("700.00"),
                true,
                10);

        RouteDecision expected = policy.decide(order);

        for (int i = 0; i < 100; i++) {
            assertEquals(expected, policy.decide(order));
        }
    }
}
~~~

Đây là smoke test cho tính tất định, **không phải chứng minh toán học** rằng code hoàn toàn không có side effect. Code review và thiết kế không I/O/trạng thái ẩn vẫn quan trọng.

## 7. Kiểm thử Spring Integration Router qua channel

Unit test của policy không xác nhận những yếu tố vận hành như:

- Router bean đã được Spring đăng ký hay chưa.
- Tên channel trả về có resolve được không.
- Một message được chuyển đúng tới channel đích nào.
- Header `traceId` có đi theo message qua router không.
- Không có message bị gửi nhầm sang các channel khác.

Để kiểm chứng, ta có thể dùng Spring Test, JUnit 5 và các `QueueChannel` đã khai báo.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = OrderRoutingConfiguration.class)
class OrderRoutingFlowTest {

    @Autowired
    @Qualifier("orders.toRoute")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.review")
    PollableChannel review;

    @Autowired
    @Qualifier("orders.priority")
    PollableChannel priority;

    @Autowired
    @Qualifier("orders.standard")
    PollableChannel standard;

    @Test
    void highRiskOrderGoesOnlyToReview() {
        OrderCandidate order = new OrderCandidate(
                "order-1001",
                new BigDecimal("750.00"),
                true,
                85);

        assertTrue(input.send(
                MessageBuilder.withPayload(order)
                        .setHeader("traceId", "trace-1001")
                        .build()));

        Message<?> routed = review.receive(1000);

        assertNotNull(routed);
        assertEquals(order, routed.getPayload());
        assertEquals("trace-1001",
                routed.getHeaders().get("traceId"));

        assertNull(priority.receive(0));
        assertNull(standard.receive(0));
    }

    @Test
    void eligibleVipOrderGoesToPriority() {
        OrderCandidate order = new OrderCandidate(
                "order-1002",
                new BigDecimal("500.00"),
                true,
                79);

        assertTrue(input.send(
                MessageBuilder.withPayload(order).build()));

        Message<?> routed = priority.receive(1000);

        assertNotNull(routed);
        assertEquals(order, routed.getPayload());

        assertNull(review.receive(0));
        assertNull(standard.receive(0));
    }

    @Test
    void nonVipOrderGoesToStandard() {
        OrderCandidate order = new OrderCandidate(
                "order-1003",
                new BigDecimal("900.00"),
                false,
                0);

        assertTrue(input.send(
                MessageBuilder.withPayload(order).build()));

        Message<?> routed = standard.receive(1000);

        assertNotNull(routed);
        assertEquals(order, routed.getPayload());

        assertNull(review.receive(0));
        assertNull(priority.receive(0));
    }
}
~~~

Đây là kiểm thử **qua message channel**, vì message đi vào `orders.toRoute` và ra một trong ba output channel do `@Router` quyết định.

Để tránh phụ thuộc giữa các test nếu chạy chung Spring context, mỗi test phải tiêu thụ message của chính nó và xác nhận các queue khác trống; với test suite lớn, có thể tạo context riêng hoặc clear test fixture theo cách đã kiểm soát. `receive(1000)` là thời gian chờ phục vụ test, không phải SLA của hệ thống.

### 7.1. Không nên chỉ test phương thức `select(...)`

~~~java
String channelName = new OrderRouter(new OrderRoutingPolicy())
        .select(order);
~~~

Đoạn trên kiểm tra ánh xạ `Decision → channel name`, nhưng **không biết** `orders.review` có thực sự tồn tại trong Spring container hay không. Cần một integration test như trên để phát hiện lỗi cấu hình channel name hoặc endpoint chưa được start.

## 8. Bốn nhóm ca biên thường bị bỏ sót

### 8.1. Quy tắc chồng lấn

Một order có thể đồng thời có `vip=true`, `total=900` và `riskScore=95`. Nếu điều kiện VIP được xét trước, route sẽ sai so với chính sách review-ưu-tiên.

~~~java
// Đúng với hợp đồng ví dụ:
if (order.riskScore() >= 80) {
    return RouteDecision.REVIEW;
}
if (order.vip() && order.total().compareTo(MIN_TOTAL) >= 0) {
    return RouteDecision.PRIORITY;
}
~~~

Dùng một bảng quyết định nêu rõ **ưu tiên** giữa các điều kiện. Không viết nhiều nhánh `if` độc lập cùng gán biến route vì người đọc khó biết điều kiện cuối cùng nào sẽ thắng.

### 8.2. Giá trị sát ngưỡng

Cần kiểm tra đúng ngưỡng và hai phía của ngưỡng: `79`, `80`; `499.99`, `500.00`. Tránh dùng `double` cho số tiền nếu cần chính xác trong chính sách, và xác định rõ cách làm tròn nếu dữ liệu đến từ một hệ thống khác.

### 8.3. Dữ liệu không đầy đủ hoặc sai kiểu

Các trường `total=null`, `orderId="   "`, `riskScore=-1`, `riskScore=101` nên có hành vi định nghĩa rõ. Với message nhận từ ngoài, phân loại lỗi tại ingress:

~~~mermaid
flowchart LR
    IN["Raw input"] --> DEC["Decode / schema"]
    DEC -->|Fail| ERR["Parse error"]
    DEC -->|OK| VAL{"Validate"}
    VAL -->|Fail| REJ["Reject / validation error"]
    VAL -->|Pass| ENR["Enrich trusted data"]
    ENR --> ROUTE{"Pure routing policy"}
    ROUTE --> DEST["Destination channel"]
~~~

Nếu router còn phải tự parse JSON, kiểm tra email và gọi API để lấy risk score, ranh giới trách nhiệm đang bị trộn. Hãy chuẩn hóa và enrichment ở bước trước router, rồi đưa message có hợp đồng rõ ràng vào policy.

### 8.4. Đích route không tồn tại

Nếu router trả `"orders.prority"` thay vì `"orders.priority"`, hoặc channel bean chưa được khai báo, framework có thể không resolve được đích và phát sinh lỗi dispatch theo cấu hình router. Unit test policy không phát hiện sai tên bean; integration test có thể phát hiện.

Có thể dùng một **default output channel** khi nghiệp vụ cho phép fallback rõ ràng, hoặc cấu hình router theo hướng phát lỗi khi đích không được resolve. **Đừng dùng default output chỉ để che lỗi chính tả channel name hoặc lỗi cấu hình.** Hãy phân biệt:

- **Fallback nghiệp vụ:** message hợp lệ nhưng không thuộc nhánh chuyên biệt → `STANDARD`.
- **Reject dữ liệu:** message không đáp ứng hợp đồng → reject/error flow.
- **Lỗi cấu hình:** routing đến channel không tồn tại → báo lỗi để sửa deployment.

## 9. Route theo payload hay theo header?

Spring Integration router có thể dựa trên payload, header hoặc expression. Cách chọn ảnh hưởng tới **nguồn tin cậy** của dữ liệu.

### 9.1. Route theo payload đã chuẩn hóa

Đây là cách trong `OrderRoutingPolicy`: điểm rủi ro, trạng thái VIP và tổng tiền nằm trong một DTO có kiểu. Trước router, validation và enrichment đã xác định contract.

Ưu điểm: dễ kiểm thử, xem lại quyết định nghiệp vụ và hạn chế ép kiểu từ `Map<String, Object>`.

### 9.2. Route theo header đáng tin cậy

Ví dụ muốn chọn hệ thống xử lý theo khu vực mà inbound adapter đã chuẩn hóa:

~~~java
import java.util.Locale;

import org.springframework.integration.annotation.Router;
import org.springframework.messaging.handler.annotation.Header;

public class RegionRouter {

    @Router(inputChannel = "orders.byRegion")
    public String route(
            @Header("trustedRegion") String region) {

        String normalized = region.trim()
                .toUpperCase(Locale.ROOT);

        return switch (normalized) {
            case "NORTH" -> "orders.north";
            case "SOUTH" -> "orders.south";
            default -> "orders.regionReview";
        };
    }
}
~~~

Đoạn trên minh họa một router **thay thế** cho policy đơn hàng ở trên, không cần thêm vào cùng flow. Bean channel cho cả ba kết quả phải tồn tại.

Header có nguồn gốc client như `tenantId`, `priority` hoặc `trustedRegion` chỉ được xem là đáng tin sau khi tầng ingress/authentication hoặc enrichment **xác minh và gắn lại**. Không cho client gửi tên channel trực tiếp rồi dùng giá trị đó như kết quả router; điều đó tạo khả năng gửi message đến các channel nội bộ không dự tính.

### 9.3. Nếu điều kiện phụ thuộc cả payload và headers?

Tạo một context kiểu dữ liệu rõ ràng:

~~~java
public record RoutingContext(
        OrderCandidate order,
        String authenticatedTenant,
        boolean priorityFeatureEnabled
) {}
~~~

Sau đó định nghĩa:

~~~java
RouteDecision decide(RoutingContext context)
~~~

Một adapter của Spring Integration có thể đọc payload và những header đã được kiểm chứng để xây `RoutingContext`, sau đó gọi chính sách thuần. Không cần để policy biết `Message<?>` hoặc `MessageHeaders` nếu điều đó làm logic domain bị phụ thuộc framework.

Khi policy phụ thuộc feature flag hoặc ngưỡng cấu hình, truyền một **snapshot bất biến** làm input hoặc tạo policy với immutable configuration. Như vậy, mỗi lần quyết định có thể được tái hiện nếu lưu lại phiên bản rules.

## 10. Định tuyến theo cấu hình thay đổi mà vẫn kiểm thử được

Trong thực tế, ngưỡng rủi ro hay ưu tiên không nhất thiết phải hard-code. Có thể định nghĩa một bộ quy tắc bất biến:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record RoutingRules(
        int reviewRiskThreshold,
        BigDecimal priorityMinTotal
) {
    public RoutingRules {
        if (reviewRiskThreshold < 0 || reviewRiskThreshold > 100) {
            throw new IllegalArgumentException(
                    "Invalid review threshold");
        }
        Objects.requireNonNull(priorityMinTotal);
        if (priorityMinTotal.signum() < 0) {
            throw new IllegalArgumentException(
                    "Invalid priority minimum");
        }
    }
}
~~~

Với cách này, policy có thể nhận `RoutingRules` trong constructor. Tác dụng:

- Unit test tạo `RoutingRules(80, new BigDecimal("500.00"))` một cách tường minh.
- Thay đổi cấu hình có kiểm soát, không phụ thuộc mutable global state.
- Khi cần giải thích quyết định của một sự kiện, hệ thống có thể lưu **rules version**.
- Không có race khi một thread cập nhật ngưỡng giữa chừng trong lúc policy đang tính kết quả.

Đối với rules động, có thể tạo **snapshot mới** rồi thay cấu hình ở ranh giới thích hợp. Nếu toàn bộ router trong thời gian ngắn phải dùng cùng phiên bản, hãy đưa `rulesVersion` vào message hoặc tracking context. Không nên đọc cấu hình biến đổi giữa các câu lệnh `if` của cùng một lần routing.

### 10.1. Quy tắc phụ thuộc thời gian

Một ví dụ có điều kiện “chỉ nhận route priority trong giờ làm việc” dễ sai nếu policy gọi `LocalDateTime.now()` trong method. Chuyển **thời gian tham chiếu** thành input:

~~~java
import java.time.Instant;

public record RoutingEvaluation(
        OrderCandidate order,
        Instant evaluatedAt
) {}
~~~

Một bước ở ranh giới gọi có trách nhiệm ghi `evaluatedAt` và timezone/business calendar phù hợp. Policy dùng **giá trị đầu vào cố định**, do đó test được ở các mốc thời gian, ranh giới ngày và chuyển múi giờ mà không phụ thuộc đồng hồ máy chạy.

## 11. Router với Filter, Transformer và Recipient List Router

Các pattern này có thể cùng xuất hiện nhưng không thay thế lẫn nhau.

### 11.1. Filter trước Router

Filter quyết định message có đủ điều kiện đi tiếp hay không. Router sau đó chọn nhánh phù hợp cho message **đã hợp lệ**.

~~~mermaid
flowchart LR
    IN["Input"] --> FILT{"Filter / validation"}
    FILT -->|Valid| ROUTE{"Router"}
    FILT -->|Invalid| REJECT["Reject"]
    ROUTE --> A["Branch A"]
    ROUTE --> B["Branch B"]
    ROUTE --> C["Branch C"]
~~~

Nếu một trường thiếu làm policy ném `IllegalArgumentException`, có thể cấu hình validation gần nơi nhận dữ liệu để chuyển message sang reject flow với mã lỗi cụ thể. Tránh dùng route `STANDARD` làm nơi “nuốt” dữ liệu không thể kiểm tra.

### 11.2. Transformer trước Router

Nếu payload từ nhiều nguồn có tên trường hoặc đơn vị khác nhau, Transformer nên chuẩn hóa trước khi policy chạy:

~~~text
RawOrder JSON / MQ payload
    -> Decode + Validate
    -> Transformer (NormalizedOrder)
    -> Risk enrichment (nguồn tin cậy)
    -> Pure routing policy
    -> Content-Based Router
    -> Channel đích
~~~

Transformer làm việc chuẩn hóa, Router làm việc lựa chọn. Khi transformer trả full `Message`, phải bảo toàn `traceId`, `businessCorrelationId` và các metadata cần thiết cho downstream; không giả định mọi header tự được truyền.

### 11.3. Khi cần nhiều đích, có thể là Recipient List Router

**Content-Based Router chọn một đích** như ví dụ có thể là quyết định chính của nghiệp vụ. Nếu một message phải đến đồng thời audit, analytics và notification, hãy xem xét **PublishSubscribeChannel** hoặc **Recipient List Router**.

| Tình huống | Pattern gợi ý |
|---|---|
| Chọn đúng một nhánh theo điểm rủi ro | Content-Based Router |
| Gửi mọi message tới tất cả subscriber | Publish–Subscribe |
| Chọn **tập đích** thay đổi theo điều kiện | Recipient List Router |
| Loại message không đạt điều kiện | Filter |
| Tách một đơn thành nhiều dòng hàng | Splitter |

Đừng trộn quyết định chọn **một route xử lý chính** với nhu cầu **phát event cho nhiều observer**. Có thể tách thành hai bước nếu thực sự cần cả hai.

## 12. Correlation, retry và side effect

Chính sách route thuần đặc biệt có lợi khi message bị gửi lại hoặc phải replay.

### 12.1. Correlation ID khác Message ID

- `MessageHeaders.ID` định danh **message instance**; khi tạo message khác, ID có thể đổi.
- `businessCorrelationId` liên kết nhiều bước của một đơn hàng, ví dụ `order-1001`.
- `traceId` theo dõi đường đi qua các handler và service.
- `correlationId` của Splitter/Aggregator phục vụ nhóm các phần, cần được bảo toàn khi các nhánh còn phụ thuộc vào nó.

Router thông thường chuyển tiếp message đầu vào tới channel đích, vì vậy metadata đi theo. Nếu trong nhánh có Transformer trả `Message<?>` mới, cần kiểm tra các header cần giữ. Tránh xây chính sách dựa trên message ID nếu mục tiêu là quyết định ổn định xuyên lần phát lại.

### 12.2. Retry không nên lặp side effect của router

Nếu route quyết định `REVIEW` cho một đơn, retry cùng input và cùng rules nên tiếp tục quyết định `REVIEW`. Nhưng gửi message tới handler thực hiện side effect **có thể** khiến thao tác đó được thực hiện lại. Vì vậy:

- Policy là pure function nên việc tính lại không tự tạo side effect.
- Handler ở nhánh đích cần idempotency nếu hệ thống có retry/replay.
- Không phát email hoặc gọi thanh toán bên trong route predicate.
- Khi một lần replay cần tái hiện quyết định lịch sử, lưu phiên bản rule/context quan trọng hoặc decision đã được phát hành theo hợp đồng.

### 12.3. Lỗi policy và lỗi ở handler

Hai loại lỗi có cách xử lý khác nhau:

| Lỗi | Ví dụ | Vị trí xử lý |
|---|---|---|
| Input vi phạm contract | `riskScore=101` | Validation/reject tại ingress hoặc lỗi chính sách |
| Đích không tồn tại | Channel bean sai tên | Cấu hình routing và startup/integration test |
| External API timeout | Handler sau route gọi đối tác | Retry/error channel phù hợp ở nhánh đó |
| Message trùng do replay | Consumer thấy cùng event ID | Idempotency ở handler hoặc adapter |
| Đổi config gây kết quả khác | Rules version mới | Quản lý phiên bản và chính sách replay |

Error channel trong Spring Integration cần được cấu hình theo topology. Ở flow đồng bộ, exception có thể truyền về caller; ở flow bất đồng bộ, hệ thống có thể phát `ErrorMessage` tới error channel theo cơ chế cấu hình. Không suy rằng có header `errorChannel` là mọi exception của router sẽ tự đi qua channel này trong mọi trường hợp.

## 13. Quan sát các quyết định route mà vẫn giữ policy thuần

Logging và metrics cần thiết, nhưng đặt trực tiếp vào `decide` làm hàm có side effect. Một phương án rõ ràng là:

1. Chính sách tính `RouteDecision`.
2. Adapter router hoặc bước quan sát ghi metric/log **bên ngoài** hàm thuần.
3. Hệ thống mang `traceId`, `businessCorrelationId`, rules version và tên đích trong sự kiện chẩn đoán nếu cần.

Ví dụ giả lập một facade tách hai trách nhiệm:

~~~java
public final class ObservedRoutingService {

    private final OrderRoutingPolicy policy;
    private final RoutingObserver observer;

    public ObservedRoutingService(
            OrderRoutingPolicy policy,
            RoutingObserver observer) {
        this.policy = policy;
        this.observer = observer;
    }

    public RouteDecision route(
            OrderCandidate order,
            String correlationId) {
        RouteDecision decision = policy.decide(order);

        // Side effect chỉ nằm trong lớp phối hợp/quan sát.
        observer.record(correlationId, decision);

        return decision;
    }
}

// Abstraction của tầng observability:
interface RoutingObserver {
    void record(String correlationId, RouteDecision decision);
}
~~~

Nếu observability mất kết nối, cần quy định liệu lỗi ghi metric có được phép làm route thất bại hay không. Trong nhiều trường hợp, hoạt động business không nên phụ thuộc vào việc gửi metric, nhưng quyết định cuối cùng cần theo SLO và chính sách vận hành của ứng dụng.

Tránh log toàn bộ payload hoặc thông tin khách hàng để chứng minh route; ghi **quyết định**, **rule version**, **correlation**, **source** và một số trường chẩn đoán an toàn thường đủ.

### 13.1. Nên đo những gì?

| Metric/trace | Ý nghĩa | Ghi chú |
|---|---|---|
| `routing_decisions_total{decision=...}` | Số message theo từng route | Label `decision` có cardinality thấp |
| `routing_rejections_total{reason=...}` | Số input bị reject | Mã lỗi ổn định, không đặt order ID vào label |
| `routing_failures_total{type=...}` | Lỗi policy hoặc resolve channel | Tách lỗi code/cấu hình khỏi lỗi dữ liệu |
| Thời gian chặng route | Theo dõi latency khi tải tăng | Đo tại endpoint thay vì trong business policy |
| Trace span với correlation | Theo dõi đường đi giữa các nhánh | Không đưa secret hoặc PII vào tag |

Policy thuần nhanh không bảo đảm toàn flow nhanh: latency có thể đến từ enrichment, channel async, broker hoặc handler downstream.

## 14. Những lỗi thiết kế thường gặp

### Lỗi 1 — Router gọi API để quyết định route

**Hiện tượng:** route chậm, flakey, unit test phải mock HTTP client và retry gọi lại API.

**Khắc phục:** đặt bước enrichment trước router, tạo input có kiểu, chạy policy thuần. Nếu trạng thái bên ngoài cần kiểm tra gần transaction, giữ logic đó tại handler tương ứng.

### Lỗi 2 — Route phụ thuộc giờ hiện tại hoặc random bên trong

**Hiện tượng:** cùng event sáng và chiều đi hai nhánh khác nhau, test chạy lúc đúng lúc sai.

**Khắc phục:** truyền `evaluatedAt` hoặc một snapshot rule/context có thể tái hiện. Các tham số này là **đầu vào** của hàm quyết định.

### Lỗi 3 — Không xác định thứ tự ưu tiên điều kiện

**Hiện tượng:** đơn risk cao nhưng VIP được gửi nhánh nhanh.

**Khắc phục:** viết bảng quyết định, test input thỏa **nhiều điều kiện cùng lúc** và nêu ưu tiên trong policy.

### Lỗi 4 — Trộn channel name với thuật ngữ nghiệp vụ

**Hiện tượng:** thay tên bean channel đòi sửa logic nhiều nơi.

**Khắc phục:** chính sách trả enum; lớp adapter duy nhất ánh xạ enum sang channel bean. Kiểm thử cả unit policy và integration wiring.

### Lỗi 5 — Sử dụng dữ liệu headers chưa xác thực

**Hiện tượng:** client gửi `priority=true` hoặc tên một channel nội bộ để tự chọn luồng ưu tiên.

**Khắc phục:** xác minh principal/tenant và dữ liệu được phép sử dụng tại ingress; chuẩn hóa thành `trustedContext`. Không lấy chuỗi tùy ý từ client làm channel name.

### Lỗi 6 — Mặc định mọi dữ liệu lỗi đi nhánh STANDARD

**Hiện tượng:** một risk score âm hoặc null vẫn lọt sang xử lý thông thường.

**Khắc phục:** định nghĩa rõ dữ liệu hợp lệ, có reject/error flow; fallback `STANDARD` chỉ dành cho **đơn hợp lệ** không trúng quy tắc chuyên biệt.

### Lỗi 7 — Chỉ kiểm thử return value của policy

**Hiện tượng:** unit test xanh nhưng deployment không có bean `orders.priority`.

**Khắc phục:** integration test gửi vào `orders.toRoute` và nhận từ các output channels, xác minh chỉ nhánh mong muốn có message.

### Lỗi 8 — Payload mutable và chính sách phụ thuộc vào việc nhánh khác đã sửa gì

**Hiện tượng:** route thay đổi theo lịch chạy thread.

**Khắc phục:** payload DTO bất biến, defensive copy với collection; không mutate input. Một `MessageHeaders` read-only không tự làm object nằm trong payload/header bất biến sâu.

### Lỗi 9 — Tưởng route thành công là nghiệp vụ đã hoàn thành

**Hiện tượng:** `send()` trả `true` nhưng downstream bị lỗi hoặc đang xử lý bất đồng bộ.

**Khắc phục:** xác định rõ contract giữa routing và business outcome. Với request–reply, dùng Gateway/reply flow phù hợp; với event, cần quan sát trạng thái xử lý từng nhánh hoặc ack/broker theo yêu cầu.

## 15. Bài thực hành: chính sách chuyển đơn đến đúng nhánh

**Bối cảnh:** nền tảng thương mại điện tử nhận message `OrderCandidate` gồm `orderId`, `total`, `vip` và `riskScore`. Hệ thống cần xử lý đơn rủi ro cao thủ công, đơn VIP giá trị lớn nhanh, còn lại bình thường.

### 15.1. Yêu cầu triển khai

1. Tạo `OrderCandidate` bất biến và `RouteDecision` gồm `REVIEW`, `PRIORITY`, `STANDARD`.
2. Viết `OrderRoutingPolicy.decide(...)` thuần Java với các ngưỡng và thứ tự ưu tiên đã nêu.
3. Dùng JUnit parameterized test cho bảng quyết định, đặc biệt các ngưỡng `79/80` và `499.99/500`.
4. Viết `@Router` nhận payload, gọi policy và trả tên channel tương ứng.
5. Khai báo ba output channels và gửi event có header `traceId` vào flow.
6. Kiểm thử mọi message đến **đúng một** queue đích, giữ payload và `traceId`, hai queue còn lại trống.
7. Thêm bước validation/reject trước router để lỗi dữ liệu không lọt vào `STANDARD`.
8. Thử đổi một channel name trong adapter và kiểm chứng integration test phát hiện cấu hình sai.
9. Tình huống nâng cao: biến ngưỡng hard-code thành `RoutingRules` snapshot, viết test với hai phiên bản cấu hình và so sánh kết quả.
10. Tình huống nâng cao: tạo `RoutingObserver` bên ngoài policy để đo số route, bảo đảm test thuần của policy vẫn không phụ thuộc hệ thống metrics.

### 15.2. Tiêu chí hoàn thành

- Với một input hợp lệ, policy **luôn trả đúng một** quyết định được định nghĩa.
- Quy tắc review được ưu tiên khi đồng thời thỏa điều kiện VIP.
- Policy không gọi network, database, clock hay channel.
- Dữ liệu không hợp lệ có hành vi rõ ràng và không bị gửi nhầm sang nhánh nghiệp vụ.
- Spring Integration resolve đúng tên channel và gửi message đến nhánh đã chọn.
- Metadata dùng để truy vết được giữ qua router.
- Các ca biên và lỗi cấu hình được phát hiện bằng test có ý nghĩa.

### 15.3. Câu hỏi tự kiểm tra

1. Vì sao nên để `OrderRoutingPolicy` trả enum thay vì trả trực tiếp tên channel?
2. Chính sách có còn thuần nếu method gọi `Instant.now()` hoặc đọc một biến global có thể thay đổi không?
3. Đơn VIP tổng `900.00` nhưng `riskScore=90` phải đi đâu và vì sao?
4. Tại sao `BigDecimal.compareTo` phù hợp hơn `equals` khi so sánh ngưỡng tổng tiền?
5. Vì sao test policy bằng JUnit thuần chưa chứng minh channel `orders.review` tồn tại?
6. Trường hợp nào là fallback hợp lệ, trường hợp nào là lỗi validation?
7. Nếu risk score được tải từ hệ thống ngoài, nên gọi API ở bước nào?
8. Vì sao router không nên gửi email ngay khi quyết định `REVIEW`?
9. Nếu triển khai async, `send()==true` bảo đảm điều gì và không bảo đảm điều gì?
10. Làm sao replay một event trong tương lai mà vẫn giải thích được quyết định route lịch sử?

## 16. Checklist thiết kế trước khi triển khai

- [ ] Chính sách được viết thành hàm Java thuần, có tên mô tả đúng mục đích.
- [ ] Dữ liệu đầu vào có kiểu rõ, bất biến hoặc có defensive copy khi cần.
- [ ] Mọi nguồn header đáng tin cậy đã được xác minh trước router.
- [ ] Bảng quyết định làm rõ **ưu tiên** khi các điều kiện chồng lấn.
- [ ] Các ngưỡng được kiểm tra ở đúng ranh giới bằng parameterized tests.
- [ ] Dữ liệu không hợp lệ có reject/error flow riêng; không fallback âm thầm.
- [ ] Chính sách trả `RouteDecision`; adapter ánh xạ decision sang channel.
- [ ] Mọi channel đích đã được khai báo, khởi động và kiểm thử qua flow.
- [ ] Header trace/correlation cần thiết được giữ khi chuyển tiếp và transform.
- [ ] Không có side effect, network call hay truy vấn DB trong `decide`.
- [ ] Retry và idempotency của mỗi handler được thiết kế độc lập với quyết định route.
- [ ] Logging/metrics được đặt ngoài policy và không tiết lộ dữ liệu nhạy cảm.
- [ ] Nếu ngưỡng thay đổi theo thời gian, có rules snapshot/version để chẩn đoán và replay.

## 17. Tổng kết

Một **Content-Based Router** dễ bảo trì có hai phần: **policy thuần** quyết định *message nên đi đâu* và **Spring Integration adapter** kết nối quyết định đó với *channel thực tế*. Khi policy nhận DTO/metadata đáng tin và trả enum, nó có thể được kiểm thử nhanh, tất định, không phụ thuộc framework; còn integration test sẽ xác nhận route thực sự hoạt động trong luồng.

Trong module **SPRING_INTEGRATION_PATTERN**, đây là nền tảng để kết hợp Router với Filter, Transformer, Splitter/Aggregator, Gateway, retry và error channel. Validation ở gần ingress giúp policy chỉ nhận message hợp lệ; enrichment cung cấp dữ liệu đã xác thực; handler ở các nhánh chịu trách nhiệm về side effect và idempotency; tracing/correlation giúp quan sát toàn bộ đường đi. Một quyết định route rõ ràng, thuần và có kiểm thử làm flow ít phụ thuộc hơn và giảm lỗi khó tìm trong môi trường production.

### Tài liệu tham khảo

- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — `@Router`: https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Router.html
- Spring Integration Reference — Channel implementations: https://docs.spring.io/spring-integration/reference/channel/implementations.html
- JUnit 5 User Guide — Parameterized Tests: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests

