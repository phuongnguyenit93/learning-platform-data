# Test accepted, rejected và malformed message

## 1. Tại sao phải kiểm thử ba nhóm message riêng biệt?

Trong **Enterprise Integration Patterns (EIP)**, **Message Filter** quyết định một message **được đi tiếp hay không** bằng một điều kiện (predicate). Trong Spring Integration, filter thường được đặt trước Router, Transformer, Gateway, Service Activator hoặc outbound adapter, nhằm ngăn những message không đủ điều kiện đi sâu vào hệ thống.

Một sai lầm dễ gặp là chỉ viết hai bài test “predicate trả `true`” và “predicate trả `false`”. Thực tế, còn trường hợp thứ ba rất quan trọng: **message bị lỗi cấu trúc hoặc dữ liệu không thể diễn giải**. Ví dụ:

- **Accepted:** đơn hợp lệ, tổng tiền đủ ngưỡng để đi vào kênh xử lý.
- **Rejected:** đơn *đúng định dạng*, nhưng không đáp ứng chính sách tiếp nhận.
- **Malformed:** đơn thiếu mã đơn, số tiền `null`, định dạng JSON sai hoặc payload không phải kiểu hệ thống mong đợi.

Ba kết quả này **không đồng nghĩa** và cần đường đi/test khác nhau. Đưa một message malformed vào nhánh “rejected theo nghiệp vụ” có thể che lỗi producer, che sự cố schema sau khi nâng cấp hoặc khiến hệ thống ghi thống kê sai.

~~~mermaid
flowchart TD
    I[Inbound message] --> P{Parse / schema / type hợp lệ?}
    P -->|Không| M[Malformed / validation error]
    P -->|Có| F{Message Filter predicate}
    F -->|true| A[(orders.accepted)]
    F -->|false| R[(orders.rejected)]
    A --> AH[Accepted Handler]
    R --> RH[Rejected Handler]
    M --> E[Error / quarantine / response]
~~~

Sơ đồ thể hiện **một hợp đồng thiết kế đề xuất**, không phải ba nhánh mặc định do mọi filter của Spring Integration tự tạo. Filter nguyên bản có kết quả cho phép hoặc loại; muốn xem “malformed” là nhóm độc lập, ứng dụng phải định nghĩa **validation, exception hoặc error flow** rõ ràng.

Bài học nằm trong chương **Filter** của module `SPRING_INTEGRATION_PATTERN`, nơi ta thực hành các EIP bằng Spring Integration để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Các kỹ thuật Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation và quan sát nhánh đều có thể dùng chung trong luồng kiểm thử này.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `accepted`, `rejected` và `malformed` theo **ngữ nghĩa nghiệp vụ và kỹ thuật**.
2. Viết predicate của Message Filter mà không vô tình biến lỗi schema thành kết quả `false`.
3. Cấu hình `IntegrationFlow.filter(...)`, `discardChannel` và `throwExceptionOnRejection` theo hợp đồng đã chọn.
4. Viết unit test cho điều kiện biên và integration test cho channel, handler, lỗi.
5. Phân biệt reject/discard của Filter với lỗi parse ở inbound adapter và exception downstream.
6. Kiểm thử đồng bộ/bất đồng bộ, request–reply Gateway, error channel, retry, idempotency và khả năng quan sát.

## 2. Ba nhóm message phải có hợp đồng rõ ràng

### 2.1. Accepted là một quyết định của Filter

Message **accepted** khi:

1. Nó đi qua ranh giới parse/validation thành công.
2. Predicate của Filter trả `true`.
3. Filter cho phép message chuyển sang output channel hoặc endpoint tiếp theo.

**Accepted không đồng nghĩa “nghiệp vụ downstream đã thành công”.** Với `DirectChannel` đồng bộ, handler có thể được gọi trong cùng chuỗi dispatch; với `QueueChannel` hoặc `ExecutorChannel`, message có thể mới được chấp nhận để xử lý sau. Nếu downstream thất bại, đó là **processing error sau Filter**, không phải Filter đổi ý và “reject” message.

### 2.2. Rejected là message hợp lệ nhưng không đạt chính sách

Message **rejected** khi payload/schema đủ tốt để đánh giá nhưng predicate trả `false`. Ví dụ một đơn hợp lệ có tổng tiền 2 triệu trong flow chỉ tiếp nhận đơn từ 5 triệu để xử lý ưu tiên.

Tùy cấu hình, Filter có thể:

- **Discard** (loại khỏi tuyến chính) và không gửi sang một channel thay thế.
- **Gửi tới discard channel** đã cấu hình để ghi nhận/từ chối có kiểm soát.
- **Ném exception khi bị loại** nếu bật `throwExceptionOnRejection(true)`.

Không thể coi `false` lúc nào cũng “thành công” hay “lỗi”: business policy quyết định liệu rejected cần được ghi audit, trả lý do cho caller, hay được bỏ qua có chủ đích.

### 2.3. Malformed là lỗi khi không thể đánh giá đúng

Message **malformed** có thể xuất hiện ở nhiều tầng:

| Vị trí phát hiện | Ví dụ | Quan hệ với Filter |
|---|---|---|
| HTTP/Kafka/JMS inbound conversion | JSON thiếu dấu ngoặc, sai encoding, schema không parse được. | Có thể lỗi **trước khi tạo được `Message<OrderEvent>`**; Filter không được gọi. |
| Spring payload type/converter | Handler mong `OrderEvent` nhưng nhận `String` không chuyển đổi được. | Có thể ném conversion/type exception khi dispatch tới Filter. |
| Validation trước Filter | `orderId` trống, `amountVnd` null hoặc âm. | Validator chặn trước predicate. |
| Predicate tự validation | Có payload `OrderEvent` nhưng trường bắt buộc không hợp lệ. | Predicate **ném exception** thay vì trả `false`. |
| Custom Transformer sau Filter | Dữ liệu đã accepted nhưng phép biến đổi không hỗ trợ. | Là lỗi downstream, không đổi classification Filter đã thực hiện. |

Một thông điệp không có `amountVnd` không thể được phân loại hợp lệ là “dưới ngưỡng 5 triệu”. Nếu viết `amount == null || amount < threshold` rồi trả `false`, test rejected có thể vẫn PASS nhưng che mất lỗi dữ liệu.

## 3. Xác định nghiệp vụ và tiêu chí kiểm thử

### 3.1. Chính sách ví dụ

Một service tiếp nhận `OrderEvent` cho pipeline xử lý đơn hàng ưu tiên. Mô hình:

~~~java
import java.math.BigDecimal;

record OrderEvent(
        String orderId,
        BigDecimal amountVnd,
        String currency) {}
~~~

Các điều kiện:

1. `orderId` bắt buộc, không được trống/whitespace.
2. `amountVnd` bắt buộc, phải lớn hơn 0.
3. `currency` phải là `VND` trong **hợp đồng của ví dụ**; những currency khác cần được quy đổi hoặc từ chối schema ở biên, không đem so sánh trực tiếp với một ngưỡng VND.
4. Với dữ liệu hợp lệ: `amountVnd >= 5_000_000` thì **accepted**, thấp hơn là **rejected**.
5. Với dữ liệu sai hợp đồng: phát **malformed error**, không đi accepted/rejected channel.

Đây là chính sách học thuật để hiểu cơ chế Filter; không phải quy định thương mại phổ quát.

### 3.2. Bảng chân trị đầy đủ

| `orderId` | `amountVnd` | `currency` | Kết quả | Giải thích |
|---|---:|---|---|---|
| `O-1` | 5.000.000 | VND | **Accepted** | Bằng ngưỡng cũng được nhận. |
| `O-2` | 8.500.000 | VND | **Accepted** | Lớn hơn ngưỡng. |
| `O-3` | 4.999.999 | VND | **Rejected** | Hợp lệ nhưng ngay dưới ngưỡng. |
| `O-4` | 1 | VND | **Rejected** | Hợp lệ, số tiền dương nhưng dưới ngưỡng. |
| `O-5` | 0 | VND | **Malformed** | Sai điều kiện dữ liệu hợp lệ, không phải reject hợp lệ. |
| `O-6` | -100 | VND | **Malformed** | Số tiền âm không được phép. |
| `O-7` | `null` | VND | **Malformed** | Không có dữ liệu để so sánh. |
| `"   "` | 6.000.000 | VND | **Malformed** | Mã đơn trống. |
| `O-9` | 6.000.000 | USD | **Malformed** | Sai hợp đồng currency của flow này. |
| Payload không phải `OrderEvent` | — | — | **Malformed/type error** | Không thể đánh giá predicate typed một cách hợp lệ. |

**Giá trị biên** 4.999.999 / 5.000.000 / 5.000.001 đặc biệt quan trọng để phát hiện nhầm `>` với `>=`. Với `BigDecimal`, dùng `compareTo` khi so sánh giá trị số; `equals` có thể trả khác nhau cho hai số bằng giá trị nhưng khác scale (ví dụ `5.0` và `5.00`).

## 4. Vị trí Filter trong integration flow

### 4.1. Filter trước Router

~~~text
HTTP / Kafka / Gateway
   -> Parse + normalize
   -> Validate required fields
   -> Filter eligibility
       -> accepted -> Router/Transformer/Handler
       -> rejected -> discard / rejection handler
       -> malformed -> exception / error flow
~~~

Mục đích của Filter là cho message phù hợp đi tiếp. Việc **gửi tới nhánh nào** là trách nhiệm Router, còn **đổi biểu diễn payload** là trách nhiệm Transformer. Có thể tách validation thành endpoint riêng trước Filter khi schema phức tạp; trong ví dụ dưới đây, để tập trung vào ba kết quả, validation được thực hiện trong policy trước khi đánh giá eligibility.

### 4.2. Đừng nhầm loại bỏ với định tuyến nhiều nhánh

Nếu message đi qua Filter trả `false`, nó **không đi tiếp trên tuyến chính**. Đừng viết:

~~~text
Filter(amount >= 5 triệu)
    -> Filter(amount < 5 triệu)
    -> rejectedHandler
~~~

rồi mong một đơn bị loại ở Filter đầu vẫn đến Filter thứ hai. Đó là các endpoint nối tiếp, không phải hai đường độc lập. Muốn xử lý rejection, dùng `discardChannel` hoặc một Router có mapping/nhánh đúng nghĩa.

### 4.3. Các hợp đồng khác nhau cho rejection

| Chế độ | Message rejected xảy ra gì? | Khi nào phù hợp? |
|---|---|---|
| Discard im lặng | Không đi tuyến chính và không có handler nhận riêng. | Chỉ khi việc bỏ qua là chủ đích, có thể chấp nhận. |
| `discardChannel` | Gửi rejected message tới channel được chỉ định. | Muốn đo lường, lưu lý do, quarantine hoặc xử lý nhánh riêng. |
| `throwExceptionOnRejection(true)` | Báo rejection bằng exception trong ngữ cảnh Filter. | Caller cần nhận lỗi đồng bộ hoặc error flow xử lý riêng. |

Không gộp ba cấu hình vào một flow mà giả định sẽ đồng thời discard và ném exception theo một thứ tự mong muốn; chọn **một hợp đồng chính**, rồi kiểm thử đúng hành vi cấu hình đó. Mọi nhánh discard cũng phải có consumer/poller nếu muốn dữ liệu thực sự được xử lý.

## 5. Java DSL: Filter với accepted/rejected/malformed rõ ràng

### 5.1. Chính sách validation và eligibility

Ví dụ hướng tới **Java 17+, Spring Boot 3.x và Spring Integration 6.x**, với `spring-boot-starter-integration`. Các record/class đặt cùng package trong bài; khi triển khai, tách các type `public` ra file riêng theo quy tắc Java.

~~~java
import java.math.BigDecimal;

record OrderEvent(
        String orderId,
        BigDecimal amountVnd,
        String currency) {}

final class OrderEligibilityPolicy {
    private static final BigDecimal MINIMUM =
            new BigDecimal("5000000");

    boolean eligible(OrderEvent order) {
        if (order == null
                || order.orderId() == null
                || order.orderId().isBlank()) {
            throw new IllegalArgumentException(
                    "MALFORMED_ORDER_ID");
        }

        if (order.amountVnd() == null
                || order.amountVnd().signum() <= 0) {
            throw new IllegalArgumentException(
                    "MALFORMED_ORDER_AMOUNT");
        }

        if (!"VND".equals(order.currency())) {
            throw new IllegalArgumentException(
                    "MALFORMED_ORDER_CURRENCY");
        }

        return order.amountVnd().compareTo(MINIMUM) >= 0;
    }
}
~~~

Ở đây `eligible` có ba trạng thái logic: **trả `true`, trả `false`, hoặc ném exception**. Exception không phải trạng thái boolean thứ ba của framework, mà là cách ứng dụng **không cho dữ liệu sai hợp đồng bị hiểu là reject hợp lệ**.

Lý do không viết `return order.amountVnd() != null && order.amountVnd().compareTo(MINIMUM) >= 0;` là nó sẽ trả `false` cho `null` và làm biến mất phân biệt giữa malformed và rejected.

### 5.2. Cấu hình hai kênh kết quả và một filter

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

final class FilterOutcomeProbe {
    final AtomicInteger accepted = new AtomicInteger();
    final AtomicInteger rejected = new AtomicInteger();
}

@Configuration
@EnableIntegration
class OrderFilterConfiguration {

    @Bean(name = "orders.input")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.accepted")
    MessageChannel accepted() {
        return new DirectChannel();
    }

    @Bean(name = "orders.rejected")
    MessageChannel rejected() {
        return new DirectChannel();
    }

    @Bean
    OrderEligibilityPolicy orderEligibilityPolicy() {
        return new OrderEligibilityPolicy();
    }

    @Bean
    FilterOutcomeProbe filterOutcomeProbe() {
        return new FilterOutcomeProbe();
    }

    @Bean
    IntegrationFlow filterOrders(OrderEligibilityPolicy policy) {
        return IntegrationFlow.from("orders.input")
                .filter(OrderEvent.class,
                        policy::eligible,
                        spec -> spec
                                .discardChannel("orders.rejected")
                                .throwExceptionOnRejection(false))
                .channel("orders.accepted")
                .get();
    }

    @Bean
    IntegrationFlow handleAccepted(FilterOutcomeProbe probe) {
        return IntegrationFlow.from("orders.accepted")
                .handle(OrderEvent.class, (order, headers) -> {
                    probe.accepted.incrementAndGet();
                    return null; // One-way terminal handler.
                })
                .get();
    }

    @Bean
    IntegrationFlow handleRejected(FilterOutcomeProbe probe) {
        return IntegrationFlow.from("orders.rejected")
                .handle(OrderEvent.class, (order, headers) -> {
                    probe.rejected.incrementAndGet();
                    return null;
                })
                .get();
    }
}
~~~

**Diễn giải:**

- `orders.input` là đầu vào.
- `OrderEligibilityPolicy` phân loại message; với dữ liệu malformed, policy ném exception và không gửi sang hai kênh kết quả.
- `discardChannel("orders.rejected")` nhận những message **hợp lệ nhưng predicate trả `false`**.
- `throwExceptionOnRejection(false)` cho phép thử tuyến discard theo cấu hình; đây không phải chế độ “báo lỗi cho caller trên mỗi rejection”.
- `orders.accepted` chỉ nhận message được Filter cho qua.
- Các handler chỉ tăng counter để test; trong production, handler phải xử lý dữ liệu, ghi kết quả, có chính sách lỗi riêng.

**Vì sao dùng `DirectChannel`?** Ví dụ kiểm thử dễ xác nhận handler đồng bộ đã chạy trước khi `send` trở về. Nếu đổi sang executor, queue hoặc broker, test phải chờ tín hiệu xử lý và phân biệt enqueue với hoàn tất.

### 5.3. Gửi message đến Filter

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

// input là bean MessageChannel có tên "orders.input".
boolean sent = input.send(
        MessageBuilder.withPayload(
                new OrderEvent(
                        "ORD-1001",
                        new java.math.BigDecimal("7500000"),
                        "VND"))
                .setHeader("traceId", "trace-ORD-1001")
                .build(),
        1_000);
~~~

`sent` chỉ phản ánh thao tác gửi message theo semantics của channel và endpoint. Nó **không** là cờ nghiệp vụ “accepted by Filter”: trong cấu hình này, message hợp lệ bị reject có thể vẫn được gửi thành công tới **discard channel** và được handler rejection ghi nhận. Test cần nhìn đúng **kênh nào nhận**, không suy luận từ mỗi giá trị `send(...)`.

## 6. Unit test predicate: kiểm tra logic trước Spring context

### 6.1. Kiểm tra accepted và rejected ở ngưỡng

Đầu tiên, test `OrderEligibilityPolicy` như một Java object bình thường:

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderEligibilityPolicyTest {
    private final OrderEligibilityPolicy policy =
            new OrderEligibilityPolicy();

    private static OrderEvent order(String id, String amount) {
        return new OrderEvent(id, new BigDecimal(amount), "VND");
    }

    @Test
    void amountJustBelowThresholdIsRejected() {
        assertFalse(policy.eligible(order("O-1", "4999999")));
    }

    @Test
    void amountExactlyAtThresholdIsAccepted() {
        assertTrue(policy.eligible(order("O-2", "5000000")));
    }

    @Test
    void amountAboveThresholdIsAccepted() {
        assertTrue(policy.eligible(order("O-3", "5000001")));
    }

    @Test
    void decimalScaleDoesNotChangeEligibility() {
        assertTrue(policy.eligible(order("O-4", "5000000.00")));
    }

    @Test
    void tinyButPositiveAmountIsValidAndRejected() {
        assertFalse(policy.eligible(order("O-5", "0.01")));
    }
}
~~~

Các test chỉ xác minh logic quyết định. **Chúng chưa xác nhận** `IntegrationFlow` đã chuyển message tới channel đúng và cũng chưa kiểm tra converter, error flow hoặc consumer lifecycle.

Nếu ngưỡng có thể thay đổi trong production, không nên hardcode expected theo một policy chưa được review. Có thể inject ngưỡng vào policy, viết test cho ngưỡng được cấu hình và kiểm tra version/nguồn cấu hình. Bài học này cố định ngưỡng để tập trung vào ba trạng thái message.

### 6.2. Malformed phải gây lỗi rõ ràng

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderEligibilityMalformedTest {
    private final OrderEligibilityPolicy policy =
            new OrderEligibilityPolicy();

    @Test
    void missingAmountIsMalformedNotRejected() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class, () ->
                        policy.eligible(
                                new OrderEvent("O-1", null, "VND")));

        assertEquals("MALFORMED_ORDER_AMOUNT", error.getMessage());
    }

    @Test
    void zeroAmountIsMalformedNotRejected() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class, () ->
                        policy.eligible(new OrderEvent(
                                "O-2", BigDecimal.ZERO, "VND")));

        assertEquals("MALFORMED_ORDER_AMOUNT", error.getMessage());
    }

    @Test
    void negativeAmountIsMalformed() {
        assertThrows(IllegalArgumentException.class, () ->
                policy.eligible(new OrderEvent(
                        "O-3", new BigDecimal("-25"), "VND")));
    }

    @Test
    void blankOrderIdIsMalformed() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class, () ->
                        policy.eligible(new OrderEvent(
                                "   ", new BigDecimal("6000000"), "VND")));

        assertEquals("MALFORMED_ORDER_ID", error.getMessage());
    }

    @Test
    void wrongCurrencyIsMalformed() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class, () ->
                        policy.eligible(new OrderEvent(
                                "O-5", new BigDecimal("6000000"), "USD")));

        assertEquals("MALFORMED_ORDER_CURRENCY", error.getMessage());
    }

    @Test
    void nullOrderIsMalformed() {
        assertThrows(IllegalArgumentException.class, () ->
                policy.eligible(null));
    }
}
~~~

**Vì sao assert mã lỗi?** Khi lỗi dữ liệu bị gộp vào `false`, luồng vẫn có vẻ xử lý “thành công” nếu discard được cấu hình. Assertion vào `MALFORMED_ORDER_AMOUNT` chứng minh policy cố tình **tách lỗi schema với business rejection**.

Trong production, nên có exception/error object mang **mã ổn định** thay vì phụ thuộc hoàn toàn vào chuỗi mô tả. Với bài học, chuỗi mã giúp dễ nhìn; khi thiết kế contract HTTP/gRPC/broker cần chuyển mã nội bộ thành status hoặc error payload được cho phép.

## 7. Integration test: chứng minh đúng channel nhận message

### 7.1. Dùng Spring Test để khởi tạo flow thực

Từ `OrderFilterConfiguration`, viết test với `@SpringJUnitConfig`. Mỗi test dùng Spring context riêng nhờ `@DirtiesContext` để tránh counter mutable từ test trước ảnh hưởng kết quả.

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(OrderFilterConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class OrderFilterRoutingTest {

    @Autowired
    @Qualifier("orders.input")
    private MessageChannel input;

    @Autowired
    private FilterOutcomeProbe probe;

    private void send(String id, String amount) {
        boolean sent = input.send(
                MessageBuilder.withPayload(new OrderEvent(
                        id, new BigDecimal(amount), "VND"))
                        .build(),
                1_000);
        assertTrue(sent);
    }

    @Test
    void acceptedMessageReachesOnlyAcceptedHandler() {
        send("O-100", "5000000");

        assertEquals(1, probe.accepted.get());
        assertEquals(0, probe.rejected.get());
    }

    @Test
    void validButIneligibleMessageReachesOnlyDiscardHandler() {
        send("O-101", "4999999");

        assertEquals(0, probe.accepted.get());
        assertEquals(1, probe.rejected.get());
    }

    @Test
    void multipleMessagesAreCountedPerOutcome() {
        send("O-1", "6000000");
        send("O-2", "2000000");
        send("O-3", "8000000");

        assertEquals(2, probe.accepted.get());
        assertEquals(1, probe.rejected.get());
    }
}
~~~

Trong cấu hình ví dụ, `orders.input`, `orders.accepted` và `orders.rejected` đều là `DirectChannel`; các terminal handler đồng bộ cập nhật probe. Vì vậy test có thể kiểm tra counter ngay sau `send` **trong phạm vi demo này**.

Đối với test production có database, email, outbound gateway hoặc xử lý async, phải xác minh mốc **business outcome** riêng, không dùng counter demo thay cho bằng chứng commit.

### 7.2. Integration test malformed không đi bất kỳ kênh kết quả

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(OrderFilterConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class OrderFilterMalformedFlowTest {

    @Autowired
    @Qualifier("orders.input")
    private MessageChannel input;

    @Autowired
    private FilterOutcomeProbe probe;

    private static boolean hasCauseText(
            Throwable error, String expected) {
        for (Throwable cause = error;
                cause != null; cause = cause.getCause()) {
            if (cause.getMessage() != null
                    && cause.getMessage().contains(expected)) {
                return true;
            }
        }
        return false;
    }

    @Test
    void missingAmountDoesNotBecomeOrdinaryRejection() {
        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> input.send(MessageBuilder.withPayload(
                        new OrderEvent("O-BAD", null, "VND"))
                        .build(), 1_000));

        assertTrue(hasCauseText(error, "MALFORMED_ORDER_AMOUNT"));
        assertEquals(0, probe.accepted.get());
        assertEquals(0, probe.rejected.get());
    }

    @Test
    void invalidCurrencyDoesNotReachAcceptedOrRejected() {
        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> input.send(MessageBuilder.withPayload(
                        new OrderEvent(
                                "O-USD", new BigDecimal("6000000"), "USD"))
                        .build(), 1_000));

        assertTrue(hasCauseText(error, "MALFORMED_ORDER_CURRENCY"));
        assertEquals(0, probe.accepted.get());
        assertEquals(0, probe.rejected.get());
    }
}
~~~

**Vì sao không bắt cứng `IllegalArgumentException` ở integration test?** Khi exception phát sinh trong endpoint Spring Integration, framework có thể bọc nó trong `MessageHandlingException` hoặc một exception cấp messaging. Test kiểm tra **cause chain** và sự vắng mặt trên hai kênh kết quả để chứng minh đúng mục đích, thay vì ràng buộc quá chặt vào một loại wrapper có thể khác giữa các phiên bản.

### 7.3. Test payload sai kiểu

Một trường hợp khác là inbound channel nhận `Message<String>` thay vì `Message<OrderEvent>`:

~~~java
// Trong context chỉ hỗ trợ OrderEvent,
// gửi payload không thể convert sang OrderEvent:
RuntimeException error = assertThrows(
        RuntimeException.class,
        () -> input.send(
                MessageBuilder.withPayload("not-an-OrderEvent")
                        .build(), 1_000));
~~~

Điểm kiểm tra: **không được để message sai kiểu được biến thành một rejection nghiệp vụ hợp lệ**. Tuy nhiên, **kiểu exception và thời điểm thất bại** có thể phụ thuộc `MessageConverter`/integration infrastructure được đăng ký. Khi ứng dụng có converter tự động từ `String` sang `OrderEvent`, cần đưa một input chắc chắn không thể chuyển và kiểm tra kết quả tại ranh giới converter cụ thể; không khẳng định mọi `String` đều luôn ném lỗi.

**Đừng tạo `MessageBuilder.withPayload(null)` để test malformed**: Spring message payload không được phép là `null` theo builder thông thường, lỗi sẽ xảy ra ngay khi tạo message, trước khi Filter chạy. Để kiểm tra field null trong payload, dùng record chứa trường `null` như test ở trên.

## 8. Malformed tại inbound adapter có thể không đi qua Filter

### 8.1. JSON sai cú pháp và JSON hợp lệ nhưng sai schema

Hai request sau khác nhau về cấp độ lỗi:

~~~http
POST /orders
Content-Type: application/json

{"orderId":"O-1","amountVnd":
~~~

Đây là **JSON không thể parse**. HTTP adapter/controller/Jackson có thể từ chối ngay trước khi tạo được DTO và Spring message cho integration flow.

Trong khi đó:

~~~json
{
  "orderId": "O-2",
  "amountVnd": null,
  "currency": "VND"
}
~~~

Đây là JSON **đúng cú pháp** nhưng vi phạm hợp đồng trường bắt buộc. Tùy cách bind/validate, nó có thể bị từ chối ở tầng bean validation hoặc có thể tạo `OrderEvent` với amount `null`, rồi được policy ném exception như ở phần 5.

Hai trường hợp đều cần nằm trong **ma trận kiểm thử malformed**, nhưng không được áp đặt rằng mọi lỗi đều do `MessageFilter` phát hiện.

### 8.2. Test đúng điểm vào

| Test level | Input gửi vào đâu? | Đường đi nào được kiểm tra? |
|---|---|---|
| Unit test policy | Gọi `eligible(OrderEvent)` trực tiếp. | Rule và validation tại policy. |
| Integration test channel | Gửi `Message<OrderEvent>` vào `orders.input`. | Filter, discard channel, subscriber. |
| Adapter-level test | Gửi HTTP/Kafka/JMS payload thực. | Parse, schema conversion, header mapping, error handling trước Filter. |
| End-to-end test | Qua biên thật đến downstream. | Delivery, transaction, timeout và business outcome. |

Trong HTTP ingress, ứng dụng có thể ánh xạ malformed thành **400 Bad Request** cho sai cú pháp hoặc trường bắt buộc; một rejection nghiệp vụ có thể là phản hồi có mã/domain status riêng. Đừng bắt buộc dùng một HTTP status cho mọi trường hợp nếu hợp đồng API có semantics khác. Với Kafka/broker, malformed có thể cần quarantine/DLQ và commit-offset policy riêng; HTTP response không phải là lời giải cho asynchronous consumer.

### 8.3. Hạn chế lỗi malformed ảnh hưởng message khác

Một consumer nhận batch/event stream có thể gặp một record lỗi. Không nên mặc định retry vô hạn nguyên batch vì một bản ghi sai JSON cố định. Xem xét:

1. Ghi một **mã lỗi ổn định** và source/partition/offset hoặc message reference cần thiết.
2. Lưu/quarantine payload một cách có bảo vệ, tuân thủ chính sách dữ liệu nhạy cảm.
3. Xác định có thể bỏ qua record lỗi và tiếp tục hay phải dừng partition/batch.
4. Cấu hình retry chỉ cho lỗi tạm thời; sai schema cố định thường cần sửa producer hoặc dữ liệu.
5. Test replay sau khi sửa schema và kiểm tra chống duplicate.

Không suy từ tên `errorChannel` rằng mọi adapter sẽ tự động DLQ hoặc không mất dữ liệu: hành vi phụ thuộc transport, error flow, acknowledgment và cấu hình cụ thể.

## 9. Rejected qua discard channel khác rejection bằng exception

### 9.1. Chọn một chính sách có chủ đích

Flow `OrderFilterConfiguration` dùng:

~~~java
.filter(OrderEvent.class,
        policy::eligible,
        spec -> spec
                .discardChannel("orders.rejected")
                .throwExceptionOnRejection(false))
~~~

Đây là đường **rejected message → rejection handler**, không phải yêu cầu hạ tầng ném exception cho mỗi message bị loại.

Nếu một API cần **thất bại ngay** khi message không đạt điều kiện, một cấu hình **thay thế** có thể là:

~~~java
// Fragment thay thế Filter ở flow riêng; không phải nối tiếp
// với cấu hình discard của ví dụ chính.
.filter(OrderEvent.class,
        policy::eligible,
        spec -> spec.throwExceptionOnRejection(true))
~~~

Trong chế độ này, kết quả `false` được biến thành **rejection exception** theo cơ chế Filter; nó không còn là một message bình thường được xử lý ở `orders.rejected` như cấu hình demo. Nên có test riêng xác nhận loại lỗi và đường phản hồi khi sử dụng với `@MessagingGateway` hoặc HTTP inbound.

### 9.2. Tại sao Gateway có thể bị treo khi Filter loại message?

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as MessagingGateway
    participant F as Filter
    participant D as Discard Handler
    C->>G: submit(OrderEvent)
    G->>F: Message + replyChannel
    F->>D: predicate=false
    D-->>F: kết thúc một chiều
    Note over G: Không có reply nghiệp vụ
    G-->>C: Timeout (nếu chờ reply)
~~~

Nếu caller gọi **Gateway request–reply** nhưng Filter discard và handler discard **không trả reply**, Gateway có thể chờ đến timeout. Đó không nhất thiết là lỗi trong predicate; đó là lỗi **hợp đồng phản hồi**.

Có các cách thiết kế:

| Hợp đồng caller | Cách triển khai phù hợp |
|---|---|
| **Chỉ phát sự kiện một chiều** | Fire-and-forget với discard handler, metrics và recovery nếu cần. |
| **Caller cần biết accepted/rejected ngay** | Thiết kế reply cho **cả nhánh accepted lẫn rejected**; có thể dùng Router/handler trả business response thay vì Filter discard im lặng. |
| **Caller coi rejected là lỗi** | Filter cấu hình `throwExceptionOnRejection(true)` hoặc validation/service ném domain exception được ánh xạ thành API error. |
| **Caller muốn xử lý bất đồng bộ** | Trả acknowledgment đã tiếp nhận và cung cấp status/event kết quả sau; không giả vờ pipeline đã xử lý xong. |

Đặc biệt, **`accepted=true` ở Filter** không đồng nghĩa Gateway chắc chắn có reply: nếu downstream chỉ là adapter một chiều, request–reply vẫn cần hợp đồng khác.

### 9.3. Discard thành công có bảo đảm message được lưu bền vững?

Không. Trong demo, discard channel là `DirectChannel` và handler chỉ tăng counter. Nếu production cần lưu các rejection để điều tra hoặc replay:

- Đưa rejection vào một **store/broker** có durability và retention được cấu hình.
- Ghi **reason code** hoặc metadata phân loại do ứng dụng tạo; raw `MessageFilter` chỉ biết predicate trả `false`, không tự suy luận lý do nghiệp vụ chi tiết.
- Gắn business/event ID để tránh ghi trùng khi producer retry.
- Không log/ghi lại toàn payload nhạy cảm nếu không thật sự cần.
- Có cảnh báo khi tỷ lệ rejection tăng bất thường vì có thể là thay đổi dữ liệu nguồn hoặc policy.

Nếu business rejection không cần lưu nhưng vẫn phải trả một business response, thiết kế nhánh discard/reply rõ ràng hơn là tự động thêm một queue không có consumer.

## 10. Xử lý lỗi đồng bộ và bất đồng bộ

### 10.1. Lỗi từ Filter đồng bộ

Với `DirectChannel`, khi `OrderEligibilityPolicy.eligible(...)` ném `IllegalArgumentException`, exception có thể đi ngược call stack tới `MessageChannel.send(...)` hoặc Gateway thông qua wrapper của framework. Đây là lý do integration test malformed ở phần 7 bắt một `RuntimeException` rồi kiểm tra cause chain.

Đừng giả định rằng khi có `errorChannel` bean toàn cục thì mọi call đồng bộ sẽ bỏ qua exception và chuyển hoàn toàn sang channel đó. Cách gửi `ErrorMessage` phụ thuộc ngữ cảnh handler/adapter và cấu hình error handling.

### 10.2. Lỗi khi Filter chạy trên một thread khác

Khi đặt một `ExecutorChannel` hoặc `QueueChannel`/poller trước Filter:

~~~text
Publisher
    |
    v
Async Channel / Queue
    |
    v
Filter
    | accepted -> Handler
    | rejected -> Discard
    | malformed -> exception -> Error handling context
~~~

Publisher có thể đã nhận kết quả **accepted/enqueued** trước khi Filter thực sự chạy. Malformed exception được tạo ở **worker/poller thread**, không mặc định ném trở lại thread gửi ban đầu.

Việc kiểm thử cần chia làm hai phần:

1. **Producer-level:** message đã enqueue/chấp nhận theo contract chưa; queue full, send timeout, executor rejection ra sao?
2. **Consumer-level:** Filter đánh giá gì, handler nào nhận, error flow nào ghi nhận malformed, retry/ack ra sao?

### 10.3. `ErrorMessage` và thông tin failed message

Trong những bối cảnh xử lý lỗi bất đồng bộ có hỗ trợ, Spring Integration có thể tạo `ErrorMessage` mang `Throwable`; nếu Throwable là `MessagingException`, có thể tra được `failedMessage`. Tuy nhiên:

- Không phải exception nào cũng mang đầy đủ message gốc.
- Không phải adapter/poller nào cũng có chung `errorChannel`.
- Lỗi **decode JSON ở ingress** có thể phát sinh trước khi có `Message<OrderEvent>`, nên cần thiết kế nơi lưu correlation/request ID từ transport.
- Nếu error flow của malformed lại ném exception mà không có recovery, transport có thể retry/redeliver theo chính sách riêng.

Phải test bằng **adapter thực tế** khi quyết định offset acknowledgment, DLQ, broker retry hoặc transactional behavior. Một unit test Filter không thể chứng minh delivery guarantee của Kafka/JMS/AMQP.

### 10.4. Ma trận lỗi, retry và idempotency

| Tình huống | Có nên retry cùng message ngay? | Hành động đề xuất |
|---|---|---|
| Accepted, downstream tạm timeout | Có thể, nếu an toàn. | Bounded retry, backoff và idempotency. |
| Accepted, downstream đã commit nhưng reply mất | Cần xác minh trạng thái. | Reconcile, không tạo side effect lần hai. |
| Rejected theo business rule | Thường không. | Business response/discard/audit theo contract. |
| Malformed JSON cố định | Không nên retry vô hạn. | Reject/quarantine, sửa producer/schema. |
| Malformed vì currency không hỗ trợ | Không retry cùng payload để mong rule tự đổi. | Validation/rejection và quy trình chuyển đổi phù hợp. |
| Parse lỗi do hệ thống schema registry tạm unavailable | Có thể là lỗi hạ tầng phục hồi được. | Retry có giới hạn, phân loại riêng với dữ liệu thật sự malformed. |
| Filter output channel không có subscriber | Retry có thể không giúp nếu cấu hình sai. | Khắc phục deployment/lifecycle, test readiness. |
| Executor queue đầy | Có thể áp dụng backpressure. | Bounded retry/overload response, scale hợp lý. |

Một message bị Filter **rejected hợp lệ** không nên được gửi lại như lỗi kỹ thuật và làm tăng tải vô ích. Khi retry message accepted sau lỗi downstream, cần giữ event/operation ID ổn định để handler đích có thể deduplicate.

## 11. Bảng test coverage theo tầng

| ID | Input | Điểm kiểm tra | Expected outcome | Negative assertion |
|---|---|---|---|---|
| F-01 | Amount 5.000.000 VND | Unit + Flow | Accepted | Rejected count = 0 |
| F-02 | Amount 5.000.001 VND | Unit | Accepted | Không throw validation |
| F-03 | Amount 4.999.999 VND | Unit + Flow | Rejected, tới discard | Accepted count = 0 |
| F-04 | Amount 1 VND | Unit | Rejected | Không bị malformed |
| F-05 | Amount 0 VND | Unit + Flow | Malformed error | Cả hai channel count = 0 |
| F-06 | Amount -1 VND | Unit | Malformed error | Không route accepted/rejected |
| F-07 | Amount `null` | Unit + Flow | Malformed amount | Rejected không nhận |
| F-08 | `orderId` trắng | Unit | Malformed ID | Không nhầm business reject |
| F-09 | Currency USD | Unit + Flow | Malformed currency theo contract | Không áp dụng ngưỡng VND |
| F-10 | Payload `String` không thể convert | Flow/Converter | Conversion/type error | Không nhận như `OrderEvent` hợp lệ |
| F-11 | JSON không thể parse | Adapter | Lỗi ingress trước Filter | Không tăng accepted/rejected count |
| F-12 | JSON hợp lệ, thiếu field | Adapter/Flow | Validation hoặc malformed | Không âm thầm discard |
| F-13 | Rejected + `discardChannel` | Flow | Discard handler nhận | Accepted handler không nhận |
| F-14 | Rejected + `throwExceptionOnRejection(true)` | Flow khác | Rejection exception | Không kiểm thử như discard thành công |
| F-15 | Malformed trên async consumer | Async integration | Error/recovery theo context | Producer ack không được coi processed |
| F-16 | Output channel không có consumer | Integration | Dispatch error/timeout theo channel | Không báo business success |
| F-17 | Downstream accepted rồi lỗi | Integration | Processing error | Không tính là Filter rejected |
| F-18 | Gateway có Filter discard one-way | Gateway integration | Timeout/contract fail được ghi nhận | Không khẳng định có reply |
| F-19 | Redelivery cùng event ID | End-to-end | Idempotency/recovery đúng | Không tạo side effect trùng |
| F-20 | Số lượng message lớn | Load test | Metrics, throughput, backpressure | Không silent drop |

Test suite không nhất thiết chạy toàn bộ kịch bản qua adapter thật ở mỗi commit. Tuy nhiên cần **phân rõ cấp độ unit / integration / end-to-end** và bảo đảm những tình huống quan trọng được kiểm thử ở cấp có thể phát hiện lỗi thực sự.

## 12. Quan sát accepted, rejected và malformed đúng cách

### 12.1. Tách log quyết định Filter khỏi outcome downstream

Một bộ sự kiện gợi ý:

~~~text
event=FILTER_EVALUATED orderId=O-100 traceId=T-100
  filter=priorityOrderFilter outcome=ACCEPTED
  policyVersion=priority-v1

event=FILTER_EVALUATED orderId=O-101 traceId=T-101
  filter=priorityOrderFilter outcome=REJECTED
  reasonCode=BELOW_THRESHOLD

event=FILTER_VALIDATION_FAILED orderId=O-BAD traceId=T-102
  filter=priorityOrderFilter outcome=MALFORMED
  reasonCode=MALFORMED_ORDER_AMOUNT

event=BRANCH_PROCESSING_FAILED orderId=O-100 traceId=T-100
  branch=orders.accepted reasonCode=OUTBOUND_TIMEOUT
~~~

Đây là **schema log do ứng dụng đề xuất**, không phải log mặc định của Spring Integration. `FILTER_EVALUATED=ACCEPTED` không đồng nghĩa `BRANCH_COMPLETED`. Với malformed phát sinh trước khi bind payload, có thể không có `orderId`; nên dùng request/transport ID an toàn để truy vết, không bịa một business ID.

### 12.2. Chỉ số cần theo dõi

| Metric | Ý nghĩa |
|---|---|
| `filter_accepted_total` | Số message Filter cho đi tiếp. |
| `filter_rejected_total` | Số message hợp lệ bị chính sách loại. |
| `filter_malformed_total` | Số message lỗi schema/validation được quan sát ở đúng tầng. |
| `inbound_decode_failed_total` | Payload lỗi trước khi đến Filter. |
| `discard_handler_failed_total` | Nhánh rejected có consumer/side effect bị lỗi. |
| `accepted_branch_completed_total` | Phân biệt accepted với downstream hoàn tất. |
| `accepted_branch_failed_total` | Lỗi downstream sau Filter. |
| `error_channel_messages_total` | Khối lượng ErrorMessage trong error flow đã cấu hình. |
| `queue_depth` / `oldest_message_age` | Nhánh bất đồng bộ có backlog không. |

Các tên trên là **metric ứng dụng minh họa**. Nếu Spring Integration/Micrometer đã cung cấp meter mặc định cho thành phần tương ứng, hãy đối chiếu semantics trước khi gộp hoặc đổi tên.

Không dùng `orderId`, `traceId` hoặc nguyên payload làm label metric: số giá trị khác nhau quá lớn và có thể lộ dữ liệu nhạy cảm. Dùng những ID đó trong log/tracing có quyền truy cập và retention phù hợp.

### 12.3. Correlation và Message History

Qua Filter, message accepted/rejected có thể được quan sát bằng Message History khi bật tracking, nhưng Message History **không tự ghi business outcome, lý do rejection hay đầy đủ các lỗi decode ở biên**. Với Splitter/Aggregator:

- Message có `correlationId` và sequence metadata cần được giữ theo contract khi qua Filter/adapter.
- Nếu một phần bị reject, Aggregator có thể **không nhận đủ số phần** như ban đầu. Phải có release/timeout policy biết rõ phần nào bị loại.
- Nếu message malformed bị đưa vào quarantine, cần lưu business/group context một cách có kiểm soát để tìm được nhóm bị ảnh hưởng.
- Không tự tăng `sequenceSize` hoặc đặt correlation mới vô cớ tại mỗi Filter: có thể làm group bị kẹt hoặc gom nhầm.

### 12.4. Phân biệt số liệu Filter với số liệu consumer

Với channel bất đồng bộ, ta có thể thấy:

~~~text
filter_accepted_total = 1_000
accepted_branch_completed_total = 950
accepted_branch_failed_total = 20
accepted_branch_pending = 30  (theo trạng thái do app theo dõi)
~~~

Số trên **chỉ để minh họa** sự khác biệt giữa “được Filter cho qua” và “đã xử lý”. Không tự suy luận `pending = accepted - completed - failed` trong mọi mô hình nếu có retry, duplicate, multi-recipient hoặc chênh lệch kỳ đo; phải định nghĩa cách đếm và correlation trước.

## 13. Chẩn đoán khi test hoặc hệ thống báo sai kết quả

### 13.1. Rejected lại bị đếm thành accepted

**Triệu chứng:** message có amount 4.999.999 được ghi nhận ở `orders.accepted`.

**Điều tra:**

1. Kiểm tra điều kiện `compareTo(MINIMUM) >= 0` và đơn vị tiền.
2. Kiểm tra không có một flow khác publish trực tiếp vào `orders.accepted`, bypass Filter.
3. Kiểm tra predicate có đọc đúng payload hay một header giá trị cũ.
4. Kiểm tra routing key và consumer subscription khi sau Filter còn Router.
5. Nếu policy động, ghi version của policy lúc đánh giá và test giá trị biên.

Đừng chữa bằng cách chỉ sửa counter trong test. Hãy xác minh **đường gửi message và policy thực sự được đăng ký**.

### 13.2. Malformed lại xuất hiện ở discard channel

**Triệu chứng:** `amountVnd=null` nhưng rejected handler vẫn nhận message.

Nguyên nhân thường gặp là predicate viết kiểu:

~~~java
// Sai hợp đồng nếu null amount được quy định là malformed:
return order.amountVnd() != null
        && order.amountVnd().compareTo(MINIMUM) >= 0;
~~~

Biểu thức này trả `false` khi số tiền `null`. Filter không thể tự đoán đó là lỗi schema, nên coi đó là rejection thông thường. Sửa bằng cách validate trước:

~~~java
if (order.amountVnd() == null) {
    throw new IllegalArgumentException("MALFORMED_ORDER_AMOUNT");
}
return order.amountVnd().compareTo(MINIMUM) >= 0;
~~~

Với dữ liệu đến từ bên ngoài, có thể tốt hơn là **validate ở inbound boundary** trước Filter, nhưng vẫn giữ test chứng minh Filter không nhận message sai hợp đồng.

### 13.3. Filter không được gọi dù input đã gửi

Cần phân biệt các lớp:

~~~mermaid
flowchart TD
    A[Producer / adapter] --> B{Tạo Message thành công?}
    B -->|Không| C[Parse / conversion error]
    B -->|Có| D{Input channel dispatch?}
    D -->|Không| E[Channel / lifecycle / subscriber error]
    D -->|Có| F{Filter đánh giá?}
    F -->|true| G[Accepted output]
    F -->|false| H[Discard output / throw policy]
    F -->|exception| I[Malformed / evaluation error]
    G --> J{Downstream xử lý?}
    H --> K{Discard handler xử lý?}
    J -->|Lỗi| L[Processing error]
    K -->|Lỗi| M[Discard processing error]
~~~

Nếu lỗi xảy ra ở inbound JSON converter, **Filter chưa nhận message**. Nếu channel không có subscriber, lỗi xảy ra trước predicate. Nếu handler accepted nhận rồi thất bại, **predicate đã hoàn tất** và lỗi nằm ở downstream. Các nhóm cần được log và test riêng.

### 13.4. Test thất bại không ổn định trên CI

Các nguyên nhân điển hình:

- Dùng state bean chung giữa các test, không reset hoặc không cô lập Spring context.
- Dùng `Thread.sleep` để đoán lúc nào handler async chạy xong.
- Test không kiểm tra một message bị gửi vào **đúng channel** mà chỉ xem kết quả trả từ một handler có thể bị mock sai.
- Gửi hai message với cùng business ID rồi đếm không phân biệt retry/duplicate.
- Dựa vào chuỗi exception message của Spring Integration thay vì mã lỗi ở cause chain/domain exception.
- Giả định payload `String` không bao giờ có converter sang DTO.

**Cách khắc phục:** dùng test dữ liệu độc lập, `@DirtiesContext`/reset có chủ đích, latch/await với timeout cho async, matcher cho cause code, và stub rõ các hệ thống bên ngoài. Không làm test “xanh” bằng cách bỏ qua exception hoặc giảm số assertion quan trọng.

## 14. Những sai lầm thường gặp khi thiết kế Filter test

| Sai lầm | Hệ quả | Thiết kế tốt hơn |
|---|---|---|
| Chỉ test message accepted | Không phát hiện reject sai nhánh hoặc silent drop. | Có positive, negative và malformed suites. |
| Coi `null` là `false` | Lỗi producer bị tính thành rejection nghiệp vụ. | Validation/error riêng. |
| Dùng `BigDecimal.equals` so ngưỡng | Kết quả khác nhau theo scale. | Dùng `compareTo` cho so sánh số. |
| Coi `send=true` nghĩa là accepted | Rejected có discard handler vẫn có thể được send thành công. | Assert đúng channel/counter. |
| Rejected mà không có discard consumer | Không thể kiểm chứng nhánh xử lý hay phục hồi. | Cấu hình handler/poller theo contract. |
| Đồng thời mong discard và exception mà không kiểm tra cấu hình | Hành vi thất bại không như kỳ vọng. | Chọn rõ một chế độ và test riêng. |
| Gateway request–reply đi qua Filter bỏ message im lặng | Caller timeout dù predicate đúng. | Thiết kế business reply/error cho mọi outcome. |
| Gộp parse error với Filter rejection | HTTP 400, business reject và downstream error bị lẫn. | Phân loại theo tầng phát sinh. |
| Test malformed bằng `MessageBuilder.withPayload(null)` | Lỗi tạo message trước Filter, không test được policy. | Dùng field null hoặc adapter payload không thể parse. |
| Tin type conversion luôn xảy ra giống nhau | Test sai giữa các phiên bản/converter. | Kiểm tra converter trong context thật. |
| Filter accepted xong thì coi downstream commit | Công bố thành công quá sớm. | Theo dõi accepted, started, completed, failed riêng. |
| Dùng retry vô hạn cho sai JSON | Poison message làm nghẽn consumer. | Bounded retry, quarantine/DLQ theo transport. |
| Không giữ correlation khi Filter nằm giữa Splitter/Aggregator | Group không được release hoặc dữ liệu bị ghép sai. | Thiết kế missing-part policy và metadata propagation. |
| Log toàn payload malformed | Rò rỉ dữ liệu hoặc tạo log quá lớn. | Log mã lỗi + ID/metadata tối thiểu. |
| Một test vừa gọi API thật vừa phụ thuộc email thật | Dễ flaky, side effect ngoài ý muốn. | Mock/stub; tách E2E có kiểm soát. |

## 15. Bài thực hành

1. **Ba luồng đầu ra:** dùng `OrderFilterConfiguration`. Gửi một message amount bằng ngưỡng, một dưới ngưỡng và một amount `null`. Xác minh accepted=1, rejected=1 và message malformed không làm tăng cả hai số đếm.
2. **Kiểm tra giới hạn:** test 4.999.999, 5.000.000, 5.000.001, 5.000.000.00. Giải thích vì sao dùng `compareTo`.
3. **Tách validation:** chuyển kiểm tra `orderId`, currency và amount sang một validator endpoint trước Filter; giữ nguyên kết quả của ba nhóm khi chạy integration test.
4. **Discard vs exception:** tạo hai `IntegrationFlow` test riêng — một dùng `discardChannel`, một dùng `throwExceptionOnRejection(true)` — rồi so sánh phản hồi caller và số message ở rejection handler.
5. **Gateway request–reply:** tạo `@MessagingGateway` trả `FilterResult(orderId, status)`. Đảm bảo accepted và rejected có business reply hợp lệ, malformed trả lỗi theo contract. Tránh Gateway chờ reply vô hạn.
6. **JSON nhập lỗi:** dùng một HTTP inbound test gửi JSON sai cú pháp và JSON đúng cú pháp nhưng `amountVnd=null`. Ghi rõ lỗi phát sinh ở converter, validator hay Filter.
7. **Payload sai type:** gửi `Message<String>` vào flow typed và quan sát conversion/type error. Bổ sung converter test nếu ứng dụng hỗ trợ DTO binding.
8. **Async:** thay `orders.input` bằng executor/queue trước Filter và tạo test latch. Chứng minh producer được accept không đồng nghĩa accepted handler đã hoàn tất.
9. **Lỗi discard handler:** cho rejected handler ném exception và phân biệt lỗi này với Filter predicate trả `false`. Xây dựng recovery theo execution model.
10. **Downstream timeout:** cho accepted handler gọi một mock HTTP gateway bị timeout. Chứng minh message vẫn đã được Filter accepted, nhưng business processing failed.
11. **Broker poison message:** mô phỏng một Kafka/JMS record không parse được. Thiết kế error channel/DLQ và quyết định acknowledgment/replay sau khi sửa producer.
12. **Correlation:** cho Splitter tạo ba item, Filter reject một item và gửi hai item tới Aggregator. Thiết kế release strategy hoặc thông tin loại phần tử để group không chờ sai.
13. **Observability:** ghi `FILTER_EVALUATED` và `FILTER_VALIDATION_FAILED` với business ID/trace ID; không log token hay payload nhạy cảm. Tạo dashboard đếm cả ba nhóm theo phiên bản policy.
14. **Property-based testing:** sinh các amount dương ngẫu nhiên và kiểm tra bất biến: dưới ngưỡng luôn rejected, từ ngưỡng trở lên luôn accepted; amount `null`, 0 hoặc âm luôn malformed.

### Câu hỏi tự kiểm tra

**Câu 1:** `amountVnd=4.999.999`, currency VND, orderId hợp lệ. Message thuộc nhóm nào? **Rejected**, vì dữ liệu đúng hợp đồng nhưng không đạt ngưỡng.

**Câu 2:** `amountVnd=null` có được coi là rejected hợp lệ không? **Không** trong chính sách ví dụ. Đây là malformed, phải đi đường lỗi/validation được định nghĩa.

**Câu 3:** `discardChannel` có nghĩa message bị discard chắc chắn đã được lưu bền vững không? **Không.** Nó chỉ quy định channel nhận rejected message; độ bền phụ thuộc channel/store/consumer.

**Câu 4:** `MessageChannel.send(...)` trả `true` có chứng minh Filter cho message đi accepted channel chưa? **Chưa.** Message có thể được gửi tới discard channel, hoặc với channel bất đồng bộ mới chỉ được enqueue.

**Câu 5:** JSON không thể parse có chắc được Filter đếm là malformed không? **Không.** Lỗi có thể xảy ra trước khi tạo Spring Message; phải theo dõi inbound converter/adapter.

**Câu 6:** Gateway không nhận reply khi Filter discard one-way. Lỗi chắc chắn do predicate sai không? **Không.** Hợp đồng request–reply có thể chưa định nghĩa phản hồi cho rejection.

**Câu 7:** Accepted message bị downstream HTTP timeout. Nên tăng metric Filter rejected không? **Không.** Filter accepted là sự kiện riêng; downstream processing failed là lỗi xảy ra sau đó.

**Câu 8:** Filter nằm giữa Splitter và Aggregator loại một message con. Vì sao có thể xuất hiện group timeout? **Vì** Aggregator có thể còn chờ phần không bao giờ đến; cần release/timeout và correlation policy phù hợp.

**Câu 9:** Vì sao integration test cần assert cả accepted và rejected counters? **Để** chứng minh message không chỉ được handler mong đợi nhận, mà còn **không lọt sang nhánh đối diện**.

**Câu 10:** Vì sao malformed message không nên retry vô hạn? **Vì** lỗi schema cố định không được chữa bằng việc gửi lại cùng payload; retry vô hạn có thể làm tắc queue/consumer.

## 16. Kết luận

**Một bộ test Filter có giá trị phải phân biệt đúng ba nhóm: accepted, rejected và malformed.** Trong Spring Integration, Filter quyết định cho qua hay loại message dựa trên predicate; rejection có thể discard, gửi vào `discardChannel` hoặc ném exception theo cấu hình. Malformed là lỗi **không thể đánh giá hợp lệ** và có thể phát sinh trước Filter ở adapter/converter hoặc trong validation.

Hãy tổ chức kiểm thử theo nhiều tầng: **unit test predicate và validation**, **integration test channel/consumer**, **adapter test cho parse/schema**, rồi **end-to-end test** cho delivery, error channel và kết quả nghiệp vụ. Luôn kiểm tra cả đường đúng và những đường **không được phép** nhận message; phân biệt accepted với processed/committed; và xử lý Gateway timeout, retry, idempotency, correlation một cách có chủ đích.

Nhờ vậy, các flow trong `SPRING_INTEGRATION_PATTERN` dùng Router, Transformer, Splitter, Aggregator và Gateway sau Filter sẽ ít phụ thuộc hơn, có thể truy nguyên nguyên nhân bị loại, và không che một message hỏng dưới vẻ ngoài của một business rejection bình thường.
