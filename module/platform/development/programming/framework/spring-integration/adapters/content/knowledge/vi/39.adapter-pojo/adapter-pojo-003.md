# MethodInvokingMessageSource: biến phương thức POJO thành nguồn message

## 1. Vấn đề cần giải quyết

Giả sử ứng dụng đang có một lớp Java thuần (POJO) cung cấp đơn hàng mới thông qua phương thức `nextOrder()`. Lớp này không biết gì về `Message`, `MessageChannel` hay Spring Integration. Ta muốn **cứ sau một khoảng thời gian lại gọi phương thức đó**, lấy kết quả và đưa vào luồng xử lý message, chẳng hạn kiểm tra đơn, ghi cơ sở dữ liệu hoặc gửi sang Kafka.

Trong module **SPRING_INTEGRATION_ADAPTERS**, các adapter kết nối hệ thống ngoài với luồng `MessageChannel`: file, SFTP, HTTP, JMS, AMQP, Kafka, database hoặc một API Java sẵn có. Với trường hợp nguồn dữ liệu là **một phương thức Java không có tham số**, Spring Integration cung cấp `MethodInvokingMessageSource` để gọi phương thức đó và chuyển giá trị trả về thành message. Ta có thể dùng trực tiếp lớp này hoặc dùng annotation `@InboundChannelAdapter` để framework tạo nó.

Sau bài này, bạn có thể:

- Phân biệt `MethodInvokingMessageSource`, `SourcePollingChannelAdapter`, `Poller` và `MessageChannel`.
- Tạo inbound adapter từ phương thức POJO bằng annotation hoặc Java DSL.
- Hiểu ý nghĩa của giá trị trả về `null`, `Message<?>`, lỗi khi gọi phương thức và số lần poll.
- Chọn cấu hình và cách kiểm thử phù hợp khi lấy dữ liệu từ một API Java hiện hữu.

## 2. Vị trí trong kiến trúc Spring Integration

`MethodInvokingMessageSource` nằm trong package `org.springframework.integration.endpoint`, kế thừa `AbstractMessageSource<Object>` và triển khai hợp đồng `MessageSource<Object>`.

Một `MessageSource` trả lời câu hỏi **“lần nhận tiếp theo có dữ liệu nào?”** thông qua `receive()`. Bản thân `MethodInvokingMessageSource` **không tự đặt lịch**. Thành phần `SourcePollingChannelAdapter` kết hợp nó với poller, thực hiện việc gọi `receive()` và gửi message đến channel.

```mermaid
flowchart LR
    T[Poller / lịch lấy dữ liệu] --> E[SourcePollingChannelAdapter]
    E -->|receive()| S[MethodInvokingMessageSource]
    S -->|gọi nextOrder()| P[POJO nguồn dữ liệu]
    P -->|Order hoặc null| S
    S -->|Message hoặc null| E
    E -->|Message khi có dữ liệu| C[MessageChannel]
    C --> H[Service Activator / Flow / Adapter khác]
```

| Thành phần | Trách nhiệm | Điều không tự làm |
|---|---|---|
| **POJO** | Cài đặt nghiệp vụ lấy một đơn vị dữ liệu khi được gọi. | Không cần biết channel, poller hay cấu trúc Spring Integration. |
| **`MethodInvokingMessageSource`** | Gọi phương thức POJO **không tham số**, biến kết quả thành `Message` khi `receive()` được gọi. | Không tự lên lịch, không tự gửi đến channel. |
| **`SourcePollingChannelAdapter`** | Nhận tín hiệu từ poller, gọi `MessageSource.receive()` và gửi message ra channel. | Không quyết định dữ liệu nghiệp vụ được lấy bằng cách nào. |
| **Poller** | Quy định chu kỳ, số lần nhận tối đa mỗi chu kỳ và một số chính sách khi polling. | Không tự cung cấp dữ liệu hay triển khai logic nghiệp vụ. |
| **`MessageChannel`** | Chuyển message sang handler hoặc bước tiếp theo trong flow. | Không tự gọi `nextOrder()` trên POJO. |

Một chu kỳ bình thường diễn ra như sau:

1. Poller kích hoạt inbound endpoint.
2. Endpoint gọi `messageSource.receive()`; source gọi phương thức POJO đã cấu hình.
3. Nếu phương thức trả về một đối tượng, Spring Integration tạo message với đối tượng đó làm payload (hoặc dùng message do phương thức trả về).
4. Endpoint gửi message đến channel; handler phía sau nhận và xử lý.
5. Nếu phương thức trả về `null`, lần nhận đó không tạo message để gửi; poller tiếp tục theo chính sách đã cấu hình.

**Phân biệt hướng dữ liệu:** `MethodInvokingMessageSource` là **inbound**: framework chủ động gọi POJO để *lấy* dữ liệu vào flow. Ngược lại, `@ServiceActivator` hoặc một outbound adapter nhận message *từ* flow để gọi nghiệp vụ hoặc đẩy ra hệ thống khác.

## 3. Hợp đồng của phương thức được gọi

Phương thức POJO dùng làm message source có một số đặc điểm quan trọng:

| Hợp đồng | Giải thích |
|---|---|
| **Không có tham số** | Poller không cung cấp payload đầu vào; method kiểu `nextOrder()` hợp lệ, còn `nextOrder(String id)` không phù hợp. |
| **Có giá trị trả về** | Có thể trả về POJO, `String`, bản ghi (`record`), `Message<?>`...; không dùng method `void`. |
| **`null` nghĩa là không có dữ liệu** | Kết quả `null` cho biết lần đọc này không có message. `null` không phải là payload hợp lệ để gửi. |
| **Một lần gọi, một kết quả** | Trả về `List<Order>` tạo một message có payload là danh sách; không tự tách thành nhiều message. Muốn tách, thêm `Splitter` ở downstream hoặc trả về từng `Order`. |
| **Phải an toàn theo lịch poll** | Phương thức có thể được gọi nhiều lần theo thời gian; việc đọc/xóa bản ghi, đồng thời và xử lý lại cần được thiết kế chủ động. |
| **Có thể trả về `Message<?>`** | Dùng khi cần chủ động đặt header, chẳng hạn mã hệ thống nguồn hoặc khóa đối chiếu. |

Ví dụ nguồn đơn giản:

```java
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

public final class PendingOrderStore {
    private final Queue<String> ids = new ConcurrentLinkedQueue<>();

    public void add(String orderId) {
        ids.add(orderId);
    }

    public String nextOrderId() {
        return ids.poll(); // Có giá trị khi còn dữ liệu; null khi hàng đợi rỗng.
    }
}
```

Ở đây `nextOrderId()` có thể được gọi theo lịch mà không cần tham số. `ConcurrentLinkedQueue` giúp thao tác hàng đợi an toàn khi có luồng khác thêm dữ liệu, nhưng ví dụ này chỉ mô phỏng nguồn trong bộ nhớ; nó **không đảm bảo lưu bền** hay giao dịch với hệ thống phía sau.

## 4. Cách 1 — Dùng `@InboundChannelAdapter` trên POJO

Đây là cách ngắn gọn khi chúng ta kiểm soát được lớp Java và có thể đặt annotation trực tiếp lên phương thức. Spring Integration phát hiện annotation trên một Spring bean, tự tạo `MethodInvokingMessageSource` cùng polling endpoint cần thiết.

Ví dụ dùng **Java 17+, Spring Boot 3.x và Spring Integration 6.x**. Trong dự án Spring Boot, thêm starter:

```groovy
// build.gradle (đoạn dependencies)
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
}
```

Tạo ứng dụng demo trong cùng package `com.example.orders` (có thể đặt các lớp ở những file Java riêng):

```java
package com.example.orders;

import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;

@SpringBootApplication
@EnableIntegration
public class OrderDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderDemoApplication.class, args);
    }

    @Bean
    Queue<PendingOrder> pendingOrders() {
        Queue<PendingOrder> orders = new ConcurrentLinkedQueue<>();
        orders.add(new PendingOrder("ORD-101", 150_000));
        orders.add(new PendingOrder("ORD-102", 290_000));
        orders.add(new PendingOrder("ORD-103", 175_000));
        return orders;
    }

    @Bean
    MessageChannel pendingOrderChannel() {
        return new DirectChannel();
    }
}

record PendingOrder(String id, long amountVnd) { }
```

Phương thức POJO được đăng ký làm **nguồn**:

```java
package com.example.orders;

import java.util.Queue;

import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.stereotype.Component;

@Component
public class PendingOrderSource {
    private final Queue<PendingOrder> orders;

    public PendingOrderSource(Queue<PendingOrder> orders) {
        this.orders = orders;
    }

    @InboundChannelAdapter(
        channel = "pendingOrderChannel",
        poller = @Poller(fixedDelay = "2000", maxMessagesPerPoll = "2")
    )
    public PendingOrder nextOrder() {
        return orders.poll();
    }
}
```

Định nghĩa consumer:

```java
package com.example.orders;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class PendingOrderConsumer {
    @ServiceActivator(inputChannel = "pendingOrderChannel")
    public void process(PendingOrder order) {
        System.out.printf("Processed %s: %d VND%n", order.id(), order.amountVnd());
    }
}
```

Khi chạy ứng dụng, `@InboundChannelAdapter` tạo polling endpoint phát message sang `pendingOrderChannel`. Với `maxMessagesPerPoll = "2"`, mỗi lần poll có thể nhận **tối đa hai** phần tử; sau vài chu kỳ, ba đơn demo được in ra. Khi queue rỗng, `nextOrder()` trả `null`, vì thế không phát thêm message. `fixedDelay = "2000"` đặt khoảng trễ khoảng 2 giây giữa các lần thực thi polling (theo đơn vị mili giây); số lần gọi và thời điểm in thực tế còn phụ thuộc thời gian xử lý và scheduler.

Chú ý ba điểm trong cấu hình:

1. `PendingOrderSource` là Spring bean (`@Component`) để annotation được framework xử lý.
2. `@InboundChannelAdapter` nằm trên **method không tham số và không `void`**. Không gắn `@Poller` riêng lên một method thường rồi mong Spring tự tạo adapter.
3. `@ServiceActivator` là phía **tiêu thụ** message. `DirectChannel` chuyển tiếp đồng bộ, nên thời gian xử lý consumer có thể kéo dài chu kỳ poll.

> **Đừng đăng ký thêm một `IntegrationFlow.from(...)` cho chính nguồn ở ví dụ này.** Annotation đã tạo inbound endpoint; tạo endpoint thứ hai trên cùng nguồn có thể khiến phương thức được đọc bằng hai poller khác nhau.

## 5. Cách 2 — Khai báo `MethodInvokingMessageSource` trực tiếp bằng Java DSL

Nếu POJO đến từ thư viện, không sửa được source code hoặc muốn cấu hình method ở lớp `@Configuration`, ta có thể tự tạo đối tượng `MethodInvokingMessageSource` rồi truyền nó cho `IntegrationFlow.from(...)`.

Ví dụ dưới đây là **phương án độc lập** với ví dụ annotation ở mục 4:

```java
package com.example.legacy;

import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.endpoint.MethodInvokingMessageSource;

@Configuration
@EnableIntegration
public class LegacyInboxIntegrationConfig {

    @Bean
    LegacyInbox legacyInbox() {
        return new LegacyInbox();
    }

    @Bean
    MethodInvokingMessageSource legacyInboxSource(LegacyInbox legacyInbox) {
        MethodInvokingMessageSource source = new MethodInvokingMessageSource();
        source.setObject(legacyInbox);       // Bean có phương thức cần gọi.
        source.setMethodName("takeNext");    // Tên method không tham số.
        return source;
    }

    @Bean
    IntegrationFlow legacyInboxFlow(MethodInvokingMessageSource legacyInboxSource) {
        return IntegrationFlow.from(
                    legacyInboxSource,
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(2000).maxMessagesPerPoll(3)))
                .handle(message -> System.out.println("Received: " + message.getPayload()))
                .get();
    }
}

final class LegacyInbox {
    private final Queue<String> messages =
            new ConcurrentLinkedQueue<>(java.util.List.of("A", "B", "C"));

    public String takeNext() {
        return messages.poll();
    }
}
```

Giải thích:

- `setObject(legacyInbox)` giữ tham chiếu đến bean cần gọi; `setMethodName("takeNext")` chỉ rõ phương thức được thực thi. API còn có `setMethod(Method)` nếu cần cung cấp đối tượng phản chiếu Java `Method` trực tiếp.
- `IntegrationFlow.from(legacyInboxSource, ...)` tạo điểm bắt đầu flow từ `MessageSource`; lambda cấu hình polling endpoint.
- `Pollers.fixedDelay(2000).maxMessagesPerPoll(3)` thiết lập khoảng trễ poll và tối đa ba lần nhận trong một lần kích hoạt.
- `.handle(...)` xử lý message ngay trong DSL. Khi xây dựng ứng dụng thực tế, có thể thay bằng `.channel(...)`, `.transform(...)`, `.route(...)` hoặc handler chuyên trách.

Nếu chỉ khai báo `@Bean MethodInvokingMessageSource` mà **không** có `SourcePollingChannelAdapter`, `IntegrationFlow.from(...)` hay endpoint tương đương, phương thức `takeNext()` sẽ không tự chạy theo lịch. Tương tự, chỉ gọi `setObject`/`setMethodName` là cấu hình nguồn, chưa phải cấu hình scheduler.

### Khi nào chọn cách nào?

| Tiêu chí | `@InboundChannelAdapter` | Tạo `MethodInvokingMessageSource` + DSL |
|---|---|---|
| Sở hữu code POJO | Thuận tiện khi có thể sửa method | Phù hợp cả khi POJO là bean thư viện có sẵn |
| Độ gọn | Ít lớp cấu hình, dễ đọc | Tường minh cách tạo source và endpoint |
| Cấu hình pipeline | Kết hợp annotation cho các bước downstream | Viết trọn flow bằng Java DSL |
| Kiểm soát source | Framework tạo source từ method được đánh dấu | Có thể cấu hình `setObject`, `setMethodName` hoặc `setMethod` |

Hai cách đưa dữ liệu vào Spring Integration theo **cùng một mô hình**: poller → message source → channel/flow.

## 6. Kết quả trả về và message headers

Mặc định, nếu `nextOrder()` trả về `new PendingOrder(...)`, Spring Integration tạo `Message` có payload là `PendingOrder`. Khi cần bổ sung thông tin cho downstream, hãy trả về một `Message<PendingOrder>` thay vì chỉ trả POJO.

Ví dụ **thay thế method `nextOrder()` ở mục 4** bằng phiên bản sau (không khai báo đồng thời hai inbound method trên cùng dữ liệu):

```java
import org.springframework.messaging.Message;
import org.springframework.integration.support.MessageBuilder;

@InboundChannelAdapter(
    channel = "pendingOrderChannel",
    poller = @Poller(fixedDelay = "2000")
)
public Message<PendingOrder> nextOrderMessage() {
    PendingOrder order = orders.poll();
    if (order == null) {
        return null;
    }

    return MessageBuilder.withPayload(order)
            .setHeader("sourceSystem", "legacy-order-queue")
            .setHeader("businessKey", order.id())
            .build();
}
```

Consumer có thể đọc:

```java
@ServiceActivator(inputChannel = "pendingOrderChannel")
public void process(
        PendingOrder order,
        @org.springframework.messaging.handler.annotation.Header("businessKey") String key) {
    System.out.println("Process " + key + " / " + order.amountVnd());
}
```

Ở đây `businessKey` là khóa nghiệp vụ giúp đối chiếu hoặc chống xử lý trùng. Header `id` và `timestamp` của Spring Message phục vụ định danh/quan sát message; **không** tự thay thế khóa định danh bền vững của đơn hàng. Tránh đặt thông tin bí mật vào header vì header có thể được ghi log hoặc chuyển tiếp qua các adapter.

Nếu method trả về một `List<Order>`, downstream nhận **một** message chứa `List<Order>`. Có thể đặt `.split()` hoặc `@Splitter` để phân tách thành từng message; `MethodInvokingMessageSource` không tự suy ra ý định tách danh sách.

## 7. Hiểu đúng hành vi của poller

Poller là nơi kiểm soát thời điểm và nhịp đọc nguồn. Hai tham số hay dùng:

| Cấu hình | Ý nghĩa thực tế | Khi cân nhắc dùng |
|---|---|---|
| `fixedDelay = "2000"` | Chờ khoảng 2 giây sau khi một lần thực thi polling kết thúc rồi chạy lần tiếp. | Hạn chế các chu kỳ chồng lấn; phù hợp khi thời gian xử lý biến thiên. |
| `fixedRate = "2000"` | Đặt nhịp kích hoạt theo chu kỳ 2 giây, tùy scheduler và tài nguyên. | Khi cần nhịp tương đối ổn định; vẫn cần xét trường hợp xử lý chậm. |
| `maxMessagesPerPoll = "1"` | Tối đa một lần nhận message mỗi lần poll. | Dữ liệu ít, cần hạn chế số phần tử xử lý. |
| `maxMessagesPerPoll = "10"` | Có thể thử nhận liên tiếp tối đa mười message mỗi lần poll; dừng sớm nếu source trả `null`. | Muốn lấy nhiều phần tử có sẵn trong cùng chu kỳ. |

**Không nhầm `maxMessagesPerPoll` với kích thước batch của payload.** Giá trị `10` không yêu cầu method trả danh sách mười phần tử; nó cho phép endpoint gọi `receive()` nhiều lần trong một chu kỳ, mỗi lần nhận một message. Nếu lần nhận đầu tiên trả `null`, poller không phát ra mười message rỗng.

Những yếu tố cần tính toán khi vận hành:

- **Tải nguồn:** mỗi lời gọi method có thể mở kết nối hoặc đọc database; poll quá dày làm tăng tải và số truy vấn rỗng.
- **Độ trễ:** poll thưa giúp giảm tải nhưng dữ liệu mới cần lâu hơn để vào flow.
- **Thời gian xử lý downstream:** với `DirectChannel`, handler chạy đồng bộ theo luồng gửi; một handler chậm ảnh hưởng nhịp lấy dữ liệu.
- **Đồng thời:** nếu source không chịu được nhiều lời gọi đồng thời, cần kiểm soát scheduler/endpoint và tránh cấu hình nhiều endpoint cùng quét một nguồn.
- **Dừng/khởi động:** lifecycle của endpoint (`start()`/`stop()`) quyết định luồng được poll hay không; tắt poller không có nghĩa là xóa dữ liệu đang nằm trong nguồn.

Đối với nguồn không có cơ chế báo khi xuất hiện dữ liệu (một phương thức Java đọc kho dữ liệu cũ, bảng staging hoặc queue nội bộ), polling rất phù hợp. Với nguồn đẩy sự kiện chủ động (callback, listener, Kafka consumer...), thường nên dùng adapter hỗ trợ cơ chế sự kiện tương ứng thay vì viết vòng polling thủ công.

## 8. Lỗi, giao dịch và tính tin cậy

`MethodInvokingMessageSource` chỉ biết gọi method. Nó **không tự đảm bảo** delivery exactly-once, retry vô hạn, transaction hoặc deduplication. Các đảm bảo này phụ thuộc nguồn dữ liệu, cách lấy dữ liệu và các thành phần downstream.

### Trường hợp nguy hiểm: lấy rồi mất

Trong ví dụ `Queue.poll()`, một phần tử bị lấy khỏi queue **trước khi** handler nhận/xử lý thành công:

```text
nextOrder() lấy ORD-101 khỏi queue
    -> message được tạo
    -> handler gặp exception
    -> queue trong bộ nhớ không còn ORD-101
```

Nếu đây là đơn hàng thật, cần thay cơ chế lấy dữ liệu bằng nguồn có trạng thái bền và quy trình xác nhận, chẳng hạn `NEW → PROCESSING → DONE`, lease có thời hạn, transaction khi phù hợp, hoặc message broker có acknowledgment. Với dữ liệu đọc từ database, thiết kế khóa/idempotency và phương án khôi phục bản ghi đang xử lý dở.

### Khi method ném exception

Ví dụ method gặp lỗi kết nối database và ném `RuntimeException`: lỗi lan ra lúc polling endpoint gọi nguồn; quá trình xử lý lỗi của poller/scheduler quyết định ghi log, chuyển đến error channel hoặc áp dụng advice phù hợp. Không nên giả định ngoại lệ sẽ tự được retry thành công. Cần cấu hình chính sách lỗi tại endpoint hoặc lớp kết nối và theo dõi thất bại.

Nguyên tắc triển khai:

1. **Đảm bảo idempotency** ở handler bằng khóa nghiệp vụ, nhất là khi có retry hoặc dữ liệu nguồn có thể được đọc lại.
2. **Phân biệt “không có dữ liệu” và “không đọc được dữ liệu”**: trả `null` khi hết dữ liệu; ném exception khi hệ thống nguồn lỗi, để lỗi quan sát được.
3. **Giới hạn thời gian gọi nguồn** bằng timeout thích hợp nếu method thực hiện I/O; poller không thể tự sửa một lời gọi treo vô hạn.
4. **Cảnh báo và quan sát** các số đo như số lần polling lỗi, độ trễ nguồn, số message thành công/thất bại và backlog.
5. **Chủ động kiểm soát backpressure**: điều chỉnh `maxMessagesPerPoll`, tốc độ poll, capacity của channel và năng lực downstream.

## 9. Kiểm thử nguồn và flow

Nên kiểm thử hai tầng: **hợp đồng `MessageSource`** (gọi method, trả message hoặc `null`) và **flow tích hợp** (poller chạy, channel chuyển message, handler nhận đúng payload/header).

Ví dụ kiểm thử tối thiểu cho source, không cần chờ scheduler:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.junit.jupiter.api.Test;
import org.springframework.integration.endpoint.MethodInvokingMessageSource;
import org.springframework.messaging.Message;

class MethodSourceTest {
    static class Inbox {
        private final Queue<String> items = new ConcurrentLinkedQueue<>();

        public String next() {
            return items.poll();
        }
    }

    @Test
    void receiveReturnsMessageThenNull() {
        Inbox inbox = new Inbox();
        inbox.items.add("ORDER-1");

        MethodInvokingMessageSource source = new MethodInvokingMessageSource();
        source.setObject(inbox);
        source.setMethodName("next");
        source.afterPropertiesSet(); // Khởi tạo source như vòng đời Spring bean.

        Message<?> first = source.receive();
        assertNotNull(first);
        assertEquals("ORDER-1", first.getPayload());
        assertNull(source.receive());
    }
}
```

Kiểm thử trên xác nhận source gọi đúng method và chuyển kết quả thành message, nhưng **chưa chứng minh** lịch poll hoặc downstream chạy đúng. Với bài kiểm thử tích hợp, khởi tạo Spring context có `@EnableIntegration`, cấu hình poller ngắn và dùng channel/handler kiểm thử để chờ đúng số message. Dùng cơ chế chờ có timeout (ví dụ `CountDownLatch`) thay cho `Thread.sleep()` cố định để tránh test chập chờn.

### Một số lỗi thường gặp

| Hiện tượng | Nguyên nhân đáng kiểm tra | Cách khắc phục |
|---|---|---|
| Method không được gọi | POJO chưa thành bean, thiếu endpoint hoặc chưa cấu hình poller. | Xác nhận Spring quét bean, có `@InboundChannelAdapter` hoặc `IntegrationFlow.from(...)`, endpoint đang chạy. |
| Lỗi khởi tạo liên quan method | Tên method sai, có tham số, method không phù hợp hoặc cấu hình chồng chéo. | Dùng method `public`, không tham số, trả giá trị; kiểm tra `setMethodName`. |
| Không thấy message ở handler | Source luôn trả `null`, sai tên channel hoặc handler chưa được đăng ký. | Kiểm tra dữ liệu đầu vào, channel và subscription; log giá trị nhận ở mức phù hợp. |
| Một đối tượng `List` được nhận thay vì nhiều phần tử | Method trả danh sách làm một payload. | Trả từng phần tử hoặc thêm Splitter trong flow. |
| Message bị xử lý chậm | Poller thưa, `DirectChannel` đồng bộ với handler nặng hoặc nguồn trả dữ liệu chậm. | Đo thời gian từng bước, điều chỉnh lịch và cân nhắc tách xử lý bất đồng bộ có kiểm soát. |
| Dữ liệu trùng hoặc thiếu khi retry | Nguồn không có xác nhận/transaction, nhiều poller hoặc handler không idempotent. | Thiết kế lại ack, retry, checkpoint và khóa nghiệp vụ theo loại nguồn. |

## 10. Bài tập tự thực hành

1. Sửa `PendingOrderSource` để chỉ lấy tối đa **một** đơn mỗi chu kỳ `fixedDelay = "1000"`; quan sát thời gian xuất hiện của ba đơn.
2. Thay `PendingOrder` bằng `Message<PendingOrder>`, thêm `sourceSystem` và `businessKey`, sau đó đọc các header tại `@ServiceActivator`.
3. Thử để `nextOrder()` luôn trả `null`. Kiểm tra rằng ứng dụng vẫn chạy theo lịch nhưng handler không nhận message.
4. Chuyển bài demo từ annotation sang cấu hình trực tiếp với `MethodInvokingMessageSource` và Java DSL. Đảm bảo chỉ có một endpoint poll nguồn.
5. Giả lập lỗi downstream sau khi lấy một đơn. Giải thích vì sao dùng `Queue.poll()` thuần có thể gây mất dữ liệu và đề xuất cách khắc phục bằng nguồn bền + xác nhận xử lý.

## 11. Ghi nhớ

- **`MethodInvokingMessageSource` = gọi một method POJO không tham số để lấy một kết quả cho lần `receive()`**.
- **`SourcePollingChannelAdapter` + poller = quyết định khi nào gọi source và gửi message đến channel**.
- **`@InboundChannelAdapter`** là cách khai báo ngắn; framework tạo các thành phần này dựa trên method được đánh dấu.
- **`IntegrationFlow.from(source, ...)`** là cách tường minh khi muốn tự cấu hình `MethodInvokingMessageSource` hoặc tích hợp với lớp Java cũ.
- `null` là **không có message**, `Message<?>` cho phép đặt header; danh sách không tự được tách phần tử.
- Polling và chuyển message không tự cung cấp exactly-once, retry hay transaction. Tính tin cậy phải được thiết kế trên cả nguồn lẫn nơi tiêu thụ.

### Tài liệu tham khảo

- [Spring Integration — Annotation Support: `@InboundChannelAdapter` và `@Poller`](https://docs.spring.io/spring-integration/reference/configuration/annotations.html)
- [Spring Integration — Java DSL Inbound Channel Adapters](https://docs.spring.io/spring-integration/reference/6.3/dsl/java-inbound-adapters.html)
- [API: `MethodInvokingMessageSource`](https://docs.spring.io/spring-integration/docs/6.2.6/api/org/springframework/integration/endpoint/MethodInvokingMessageSource.html)
- [Spring Integration — Overview of Polling Inbound Endpoints](https://docs.spring.io/spring-integration/reference/overview.html)
