# Filter event trước khi đưa vào flow trong Spring Integration

## Mục tiêu bài học

Trong chương **Adapter sự kiện** của module **SPRING_INTEGRATION_ADAPTERS**, `ApplicationEventListeningMessageProducer` đưa **Spring ApplicationEvent** vào một `MessageChannel` để các thành phần Spring Integration tiếp tục xử lý. Mặc định, một ứng dụng có thể phát nhiều sự kiện không liên quan tới nghiệp vụ đang tích hợp, chẳng hạn `ContextRefreshedEvent`, `ContextClosedEvent` hoặc sự kiện của các module khác. Nếu đưa mọi sự kiện vào cùng một flow, handler phải tự kiểm tra kiểu, tăng nguy cơ lỗi chuyển kiểu và tạo vòng lặp khi kết hợp adapter phát/nhận sự kiện.

Bài này hướng dẫn **lọc event trước khi đưa vào flow**, đồng thời làm rõ phần việc phải thực hiện *sau* điểm tiếp nhận:

- Chọn đúng **event type** tại inbound adapter bằng `setEventTypes(...)`.
- Phân biệt lọc theo loại sự kiện với lọc theo **payload, header và điều kiện nghiệp vụ** bằng `Filter`.
- Thiết kế các nhánh **accept**, **discard** và **error** rõ ràng.
- Phòng tránh nhận nhầm sự kiện vòng đời, sự kiện nội bộ và sự kiện do chính outbound adapter phát.
- Kiểm thử rằng event không phù hợp **không vào channel**, còn event hợp lệ đi đúng luồng.

Phạm vi là **Spring ApplicationEvent trong cùng ApplicationContext**. Các adapter HTTP, JMS, AMQP, Kafka, file, SFTP và database của Spring Integration có thể dùng cùng các `Filter` ở cấp message, nhưng không dùng `eventTypes` của event adapter để lọc record Kafka hoặc message từ HTTP.

## 1. Lọc event tại đâu trong đường đi dữ liệu?

~~~mermaid
flowchart LR
    A["ApplicationEventPublisher"] --> B["Spring event multicaster"]
    B --> C{"Inbound event adapter\nmatch eventTypes?"}
    C -->|"Không"| D["Bỏ qua event"]
    C -->|"Có"| E["Tạo/giữ Message<?>"]
    E --> F["input MessageChannel"]
    F --> G{"@Filter\nđiều kiện nghiệp vụ?"}
    G -->|"Đạt"| H["Flow xử lý"]
    G -->|"Không đạt"| I["Discard channel\nhoặc bỏ message"]
~~~

Hai điểm lọc trong sơ đồ **không thay thế cho nhau**.

| Vị trí | Tiêu chí thường dùng | Tác dụng | Đã tạo message vào flow? |
| --- | --- | --- | --- |
| `ApplicationEventListeningMessageProducer.setEventTypes(...)` | Loại Spring event: `InvoicePaidEvent.class` | Chặn các event không thuộc hợp đồng inbound | **Chưa**; event không khớp không được gửi vào output channel |
| `@Filter` / `MessageFilter` sau channel | Thuộc tính payload, giá trị header, điều kiện nghiệp vụ | Cho message hợp lệ đi tiếp; loại hoặc chuyển message bị từ chối | **Rồi**; message đã qua inbound adapter |
| `@Router` / router trong flow | Loại payload, trạng thái nghiệp vụ, header điều hướng | Chọn một hay nhiều nhánh xử lý | **Rồi**; mục đích chính là định tuyến |
| Validation trong service activator / transformer | Contract, trường bắt buộc, ràng buộc dữ liệu | Báo lỗi hoặc chuyển đổi dữ liệu | **Rồi**; lỗi validation khác với việc event bị lọc theo type |

**Nguyên tắc:** nếu flow chỉ dành cho một số loại application event, hãy lọc tại **inbound adapter trước**, sau đó thêm `Filter` nếu còn điều kiện nghiệp vụ. Bộ lọc theo `eventTypes` không thay thế validation hay phân quyền.

## 2. Event type là gì?

Đối với Spring event truyền thống, type là lớp kế thừa `ApplicationEvent`:

~~~java
public final class InvoicePaidEvent extends ApplicationEvent {

    private final String invoiceId;

    public InvoicePaidEvent(Object source, String invoiceId) {
        super(source);
        this.invoiceId = invoiceId;
    }

    public String getInvoiceId() {
        return invoiceId;
    }
}
~~~

Khi gọi:

~~~java
publisher.publishEvent(new InvoicePaidEvent(this, "INV-1001"));
~~~

Spring multicaster phân phối sự kiện đến các listener phù hợp. Inbound adapter cũng là một listener Spring và có thể chỉ tiếp nhận `InvoicePaidEvent` bằng cách cấu hình:

~~~java
adapter.setEventTypes(InvoicePaidEvent.class);
~~~

Sự kiện thuộc kiểu khác không được gửi vào `MessageChannel` của adapter này. Đây là **bộ lọc theo class**, không đọc `invoiceId` hoặc trạng thái thanh toán.

### Có nên chấp nhận mọi loại ApplicationEvent?

Cấu hình không giới hạn có thể đưa cả sự kiện vòng đời của Spring hoặc sự kiện do module khác phát vào flow. Nếu cần hỗ trợ nhiều loại, hãy chỉ rõ danh sách:

~~~java
adapter.setEventTypes(
        InvoicePaidEvent.class,
        InvoiceCancelledEvent.class);
~~~

Ở đây `InvoiceCancelledEvent` là một lớp sự kiện nghiệp vụ khác do ứng dụng định nghĩa; đoạn mã là minh họa cho cách khai báo nhiều type. Nếu hai loại có cấu trúc dữ liệu khác nhau, bước tiếp theo phải **route/transform** theo type thay vì ép tất cả thành `InvoicePaidEvent`.

Khi các event kế thừa một base class, cần hiểu semantics khớp kiểu trong phiên bản Spring Integration đang dùng, đặc biệt với subclass, interface và POJO được Spring bọc vào `PayloadApplicationEvent`. Để hợp đồng rõ và dễ kiểm thử, ưu tiên type cụ thể ở ranh giới adapter.

## 3. Ví dụ hoàn chỉnh: nhận đúng event, rồi kiểm tra nghiệp vụ

Bài toán: hệ thống có nhiều event, nhưng flow kế toán chỉ nhận `InvoicePaidEvent`. Trong các event đã nhận, chỉ hóa đơn có số tiền **lớn hơn 0** được chuyển sang bước tạo bút toán. Event đúng type nhưng số tiền không hợp lệ đi vào nhánh discard để audit.

Ví dụ dùng Java 17+, Spring Boot và Spring Integration.

**Dependency Gradle:**

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.integration:spring-integration-event")
}
~~~

Với Spring Boot, để dependency management của Boot chọn phiên bản Spring Integration tương thích. Những đoạn mã dưới đây minh họa đường đi application event trong cùng JVM, chưa gọi tới hệ thống kế toán ngoài.

### 3.1. Tạo Spring event

`InvoicePaidEvent.java`:

~~~java
package com.example.billing;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import org.springframework.context.ApplicationEvent;

public final class InvoicePaidEvent extends ApplicationEvent {

    private final String invoiceId;
    private final BigDecimal amount;
    private final Instant occurredAt;

    public InvoicePaidEvent(
            Object source,
            String invoiceId,
            BigDecimal amount,
            Instant occurredAt) {
        super(source);
        this.invoiceId = Objects.requireNonNull(invoiceId);
        this.amount = Objects.requireNonNull(amount);
        this.occurredAt = Objects.requireNonNull(occurredAt);
    }

    public String getInvoiceId() {
        return invoiceId;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public Instant getOccurredAt() {
        return occurredAt;
    }
}
~~~

Đặt dữ liệu cần trao đổi trực tiếp trong event giúp hợp đồng rõ ràng. `ApplicationEvent.getSource()` cho biết đối tượng phát event; không nên mặc định coi nó là mã hóa đơn hay payload nghiệp vụ.

### 3.2. Khai báo inbound adapter và các channel

`InvoiceEventAdapterConfig.java`:

~~~java
package com.example.billing;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.event.inbound.ApplicationEventListeningMessageProducer;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class InvoiceEventAdapterConfig {

    @Bean
    public MessageChannel rawInvoiceEvents() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel validInvoiceEvents() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel discardedInvoiceEvents() {
        return new DirectChannel();
    }

    @Bean
    public ApplicationEventListeningMessageProducer invoiceEventInbound(
            @Qualifier("rawInvoiceEvents") MessageChannel outputChannel) {

        var adapter = new ApplicationEventListeningMessageProducer();

        // Chỉ nhận loại event thuộc hợp đồng của flow kế toán.
        adapter.setEventTypes(InvoicePaidEvent.class);

        // Chỉ event đã qua bộ lọc type mới đi tới channel này.
        adapter.setOutputChannel(outputChannel);

        return adapter;
    }
}
~~~

Ở đây, `rawInvoiceEvents` là ranh giới giữa Spring application events và Spring Integration. Nếu Spring phát `ContextRefreshedEvent`, hoặc một event nghiệp vụ khác, chúng không đi vào `rawInvoiceEvents` thông qua adapter này.

### 3.3. Lọc số tiền và phân nhánh accept/discard

`InvoiceEventEndpoints.java`:

~~~java
package com.example.billing;

import java.math.BigDecimal;
import org.springframework.integration.annotation.Filter;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class InvoiceEventEndpoints {

    @Filter(
            inputChannel = "rawInvoiceEvents",
            outputChannel = "validInvoiceEvents",
            discardChannel = "discardedInvoiceEvents")
    public boolean hasPositiveAmount(InvoicePaidEvent event) {
        return event.getAmount().compareTo(BigDecimal.ZERO) > 0;
    }

    @ServiceActivator(inputChannel = "validInvoiceEvents")
    public void createAccountingEntry(InvoicePaidEvent event) {
        System.out.println("ACCEPT " + event.getInvoiceId());
    }

    @ServiceActivator(inputChannel = "discardedInvoiceEvents")
    public void auditRejectedEvent(InvoicePaidEvent event) {
        System.out.println("DISCARD " + event.getInvoiceId());
    }
}
~~~

`@Filter` gọi phương thức predicate với payload từ message. Nếu trả về `true`, message được gửi đến `validInvoiceEvents`. Nếu trả về `false`, message được gửi sang `discardedInvoiceEvents` vì đã cấu hình `discardChannel`. Nếu không cấu hình discard channel, message bị từ chối thường bị bỏ đi theo chính sách filter mặc định; có thể cấu hình ném exception khi từ chối nếu nghiệp vụ yêu cầu.

**Lưu ý:** đây là **lọc sau khi event đã được đưa vào flow**. Nó kiểm tra thuộc tính `amount` mà bộ lọc `eventTypes` không thực hiện được.

### 3.4. Phát event từ service

`InvoicePaymentService.java`:

~~~java
package com.example.billing;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class InvoicePaymentService {

    private final ApplicationEventPublisher publisher;

    public InvoicePaymentService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void announcePaid(String invoiceId, BigDecimal amount) {
        publisher.publishEvent(
                new InvoicePaidEvent(
                        this,
                        invoiceId,
                        amount,
                        Instant.now()));
    }
}
~~~

Gọi thử:

~~~java
paymentService.announcePaid(
        "INV-1001", new BigDecimal("150.00"));

paymentService.announcePaid(
        "INV-1002", BigDecimal.ZERO);
~~~

Kết quả kỳ vọng với multicaster mặc định đồng bộ và các `DirectChannel`:

~~~text
ACCEPT INV-1001
DISCARD INV-1002
~~~

Một event không đúng type như `ContextRefreshedEvent` hoặc `InvoiceCancelledEvent` không xuất hiện trong hai dòng này vì không qua inbound type filter.

Ví dụ trên sử dụng **một** inbound adapter cho `rawInvoiceEvents`. Nếu thêm một adapter khác cùng trỏ tới channel này và nhận trùng event type, bạn có thể tạo hai lần chuyển message từ một event; vì thế phải xem xét toàn bộ topology của context khi quan sát số lần consumer được gọi.

## 4. Tại sao không chỉ lọc bằng @Filter?

Bạn có thể cho inbound adapter nhận tất cả event rồi dùng `@Filter` với điều kiện `instanceof`. Tuy nhiên cách đó biến một flow chuyên xử lý hóa đơn thành nơi tiếp nhận nhiều event không liên quan, kể cả Spring framework events. Hệ quả:

- Channel và filter phải xử lý thêm lưu lượng không cần thiết.
- Nếu chữ ký `@Filter` chờ `InvoicePaidEvent` nhưng event khác được đưa vào, việc chuyển kiểu payload có thể gây lỗi trước khi predicate trả về `false`.
- Nếu flow có nhiều subscriber hoặc một `WireTap`, event không liên quan có thể bị chuyển tới thành phần khác trước khi filter nghiệp vụ quyết định.
- Khi có inbound và outbound event adapter trong cùng ứng dụng, nhận rộng làm tăng rủi ro phát lại cùng event thành vòng lặp.

Vì thế, **lọc type tại nguồn nhận** và **lọc thuộc tính sau khi đã vào flow** là cách tách trách nhiệm rõ ràng.

Nếu cần một flow nhận nhiều loại event cho nhiều tác vụ, dùng nhiều inbound adapter/output channel chuyên biệt hoặc thêm `Router` với contract rõ ràng. Không nên ép mọi sự kiện về một payload type chỉ để tiết kiệm số channel.

## 5. Bản chất của event type, payload và header

Một event có thể được thể hiện theo các dạng khác nhau ở ranh giới Spring và Spring Integration:

| Dạng phát sự kiện | Loại event ở Spring | Nội dung khi thành message | Hệ quả khi filter |
| --- | --- | --- | --- |
| `publishEvent(new InvoicePaidEvent(...))` | `InvoicePaidEvent` | Thường là chính đối tượng `InvoicePaidEvent` | Lọc theo `InvoicePaidEvent.class` phù hợp cho ví dụ chính |
| `publishEvent(new InvoicePaidPayload(...))` với một POJO/record | Spring bọc thành `PayloadApplicationEvent<InvoicePaidPayload>` | Inbound event adapter có thể giải nén thành `InvoicePaidPayload` | Phải kiểm tra cách match theo kiểu payload/`PayloadApplicationEvent` của phiên bản; không mặc nhiên coi wrapper và POJO cùng một class |
| Phát `MessagingEvent` bao một `Message<?>` | `MessagingEvent` | Adapter có thể chuyển thẳng message gốc cùng headers | Lọc theo `MessagingEvent.class` nhận nhiều loại payload, nên có thể cần thêm filter payload sau channel |
| Phát event framework như `ContextRefreshedEvent` | `ContextRefreshedEvent` | Event framework nếu adapter được cấu hình nhận | Không nên để lọt vào flow nghiệp vụ nếu không có use case |

Điểm mấu chốt: **event type trước inbound adapter** và **payload type sau inbound adapter** có thể khác nhau. Với POJO event, Spring dùng `PayloadApplicationEvent` để mang payload; với `MessagingEvent`, Spring Integration có thể giữ nguyên `Message<?>` (payload, headers, metadata).

### Khi nguồn phát là POJO

Định nghĩa payload nghiệp vụ:

~~~java
public record InvoicePaidPayload(
        String invoiceId, BigDecimal amount) {
}
~~~

và phát:

~~~java
publisher.publishEvent(
        new InvoicePaidPayload("INV-2001", new BigDecimal("80.00")));
~~~

Spring Framework hỗ trợ POJO events thông qua `PayloadApplicationEvent`. Đừng sao chép cấu hình ví dụ `InvoicePaidEvent.class` rồi kỳ vọng nó bắt sự kiện POJO, vì Spring event và payload có class khác nhau.

Nếu chọn POJO làm contract, hãy đối chiếu chức năng lọc `eventTypes` trong phiên bản Spring Integration đang dùng và viết test xác nhận chính xác. Một phương án rõ ràng khác là sử dụng lớp `ApplicationEvent` chuyên biệt cho đầu vào, rồi chuyển thành record nghiệp vụ ở `@Transformer` sau inbound adapter. Cách này cho phép giới hạn type tại adapter mà không nhập nhằng wrapper.

### Khi cần giữ header

Nếu event được phát từ một outbound adapter với `publishPayload=false`, payload POJO có thể được bọc bằng `MessagingEvent`. Đầu nhận có thể nhận toàn bộ message chứa các header như `correlationId`, `traceId`:

~~~java
import org.springframework.integration.event.core.MessagingEvent;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<InvoicePaidPayload> original = MessageBuilder
        .withPayload(new InvoicePaidPayload(
                "INV-2002", new BigDecimal("99.00")))
        .setHeader("correlationId", "corr-2002")
        .build();

publisher.publishEvent(new MessagingEvent(original));
~~~

Nếu inbound adapter nhận `MessagingEvent` và chuyển message gốc, predicate sau channel nên kiểm tra **payload type** và header cần thiết; `setEventTypes(MessagingEvent.class)` một mình không phân biệt `InvoicePaidPayload` với các payload khác.

Ngược lại, nếu phát POJO trực tiếp hoặc cấu hình `publishPayload=true` ở outbound handler, headers của `Message<?>` không tự thành thuộc tính của POJO event. Để bảo đảm truy vết, hãy thiết kế event contract mang `correlationId` hoặc giữ nguyên message bằng dạng event phù hợp.

## 6. Lọc dựa trên payloadExpression: chọn dữ liệu trước khi filter

`ApplicationEventListeningMessageProducer` có thể dùng `payloadExpression` để trích dữ liệu từ application event khi tạo payload message. Ví dụ đối với `InvoicePaidEvent`, nếu downstream chỉ cần mã hóa đơn, có thể cấu hình:

~~~java
import org.springframework.expression.spel.standard.SpelExpressionParser;

adapter.setPayloadExpression(
        new SpelExpressionParser().parseExpression("invoiceId"));
~~~

Khi đó payload của message đầu ra từ inbound adapter là `String` như `"INV-1001"` thay vì đối tượng `InvoicePaidEvent`. **Các method `@Filter` và `@ServiceActivator` sau channel phải đổi chữ ký tương ứng**.

Có thể kết hợp:

1. `eventTypes`: loại các event khác `InvoicePaidEvent`.
2. `payloadExpression`: trích `invoiceId` hoặc thuộc tính cần thiết của event hợp lệ.
3. `@Filter`: kiểm tra giá trị của payload đã trích.

Tuy nhiên, nếu chỉ trích `invoiceId`, thông tin `amount` không còn nằm trong payload để predicate kiểm tra. Hãy chọn thứ tự mapping/phương án DTO phù hợp, tránh đánh mất trường cần cho nghiệp vụ.

Đối với một số event đặc biệt như `MessagingEvent` có nguồn là `Message<?>`, inbound adapter có quy tắc giữ nguyên message gốc; không nên mặc định rằng biểu thức trích payload được áp dụng giống hệt mọi kiểu event. Cần kiểm thử mapping thực tế trước khi gắn validation với một biểu thức.

## 7. Cấu hình lọc event bằng XML

Trong dự án Spring Integration sử dụng XML namespace, có thể giới hạn loại sự kiện ngay tại inbound adapter:

~~~xml
<int:channel id="rawInvoiceEvents"/>

<int-event:inbound-channel-adapter
    channel="rawInvoiceEvents"
    event-types="com.example.billing.InvoicePaidEvent"/>
~~~

Đây là đoạn minh họa nằm trong tài liệu XML đã khai báo namespace `int` và `int-event` cùng schema tương ứng. Thuộc tính `event-types` tương đương mục đích với cấu hình Java `setEventTypes(...)`.

Nếu downstream còn cần kiểm tra `amount > 0`, hãy bổ sung filter trong flow; `event-types` chỉ quyết định **loại event**. Trong các ứng dụng dùng cấu hình Java annotation như mục 3, hai kiểu cấu hình chỉ là lựa chọn thay thế, không khai báo trùng adapter ở cả XML và Java cho cùng luồng nếu không chủ đích nhân đôi xử lý.

## 8. Khi từ chối event: im lặng, discard hay lỗi?

Không phải mọi tình huống đều nên xử lý như một lỗi.

| Tình huống | Kết quả phù hợp | Lý do |
| --- | --- | --- |
| Spring phát `ContextRefreshedEvent` nhưng flow chỉ nhận `InvoicePaidEvent` | Inbound type filter bỏ qua | Đây là event khác hợp đồng, không phải lỗi nghiệp vụ |
| Event đúng type nhưng `amount == 0` và quy tắc không xử lý | `@Filter` từ chối, gửi `discardChannel` nếu cần audit | Loại theo điều kiện nghiệp vụ |
| Event đúng type nhưng thiếu trường bắt buộc | Validation có thông báo lỗi rõ ràng | Có thể là lỗi contract; chỉ discard im lặng sẽ che giấu vấn đề |
| Predicate ném exception khi đọc dữ liệu | Cơ chế exception / error flow của endpoint | Exception **khác** kết quả boolean `false` |
| Downstream HTTP/Kafka/JMS thất bại sau khi event đã qua filter | Xử lý lỗi adapter/transport và retry theo yêu cầu | Bộ lọc event không chịu trách nhiệm xác nhận giao hàng |

`discardChannel` nhận **message bị từ chối**, thuận tiện cho audit hoặc metric. Nếu bỏ hoàn toàn message, nên có metric đếm theo event type hoặc rejection reason khi lưu lượng cao.

Để ném exception thay vì discard mặc định khi điều kiện sai, `@Filter` có thuộc tính `throwExceptionOnRejection`. Sử dụng khi event bị từ chối được xem là lỗi nghiêm trọng và bên phát phải biết, nhưng hãy xác định đường đi exception trước khi bật, nhất là trong cấu hình bất đồng bộ.

## 9. Đồng bộ, async và error channel

Theo mặc định, `SimpleApplicationEventMulticaster` của Spring và `DirectChannel` của Spring Integration đều hoạt động đồng bộ. Khi service gọi `publisher.publishEvent(...)`, adapter có thể lập tức nhận event, chuyển message vào channel và gọi `@Filter`/service activator trong **cùng thread**.

Điều này có nghĩa:

- Predicate hoặc consumer chậm có thể làm chậm thread đang publish.
- Một exception từ filter/handler có thể lan ngược về publisher, tùy cấu hình error handler và endpoint.
- Nếu event được phát trong một transaction, xử lý đồng bộ tại filter có thể chạy **trước commit**, mặc dù điều kiện type hợp lệ.

Khi sử dụng `ExecutorChannel`, `@Async` hoặc cấu hình executor cho multicaster, thread thực thi và đường đi của lỗi thay đổi. Một `send(...)` thành công hoặc `publishEvent(...)` trả về không có nghĩa tất cả consumer bất đồng bộ đã hoàn tất.

Với event chỉ được xử lý **sau transaction commit**, không thể giải quyết yêu cầu đó bằng `eventTypes`. Hãy dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` làm cầu nối sau commit, hoặc thiết kế outbox nếu cần đảm bảo phát message tới hệ thống ngoài. Nếu chuyển sang executor trước khi đăng ký transaction-bound listener, transaction context dựa trên thread có thể không còn hiện diện.

**Lưu ý về độ tin cậy:** lọc type trước flow giảm tải và hạn chế xử lý sai, nhưng Spring application events vẫn là cơ chế nội bộ, không mặc định có durable persistence, retry xuyên restart hay dead-letter queue.

## 10. Ngăn vòng lặp giữa inbound và outbound event adapter

Khi cùng một ứng dụng vừa nhận vừa phát Spring event, có thể xảy ra vòng lặp:

~~~mermaid
flowchart LR
    I["Inbound event adapter"] --> F["Integration flow"]
    F --> O["Outbound event publisher"]
    O -->|"Phát lại cùng event type"| I
~~~

Ví dụ inbound adapter nghe `InvoicePaidEvent.class`, flow xử lý rồi outbound handler lại phát đúng `InvoicePaidEvent` sang Spring context. Nếu inbound adapter vẫn nghe sự kiện đó, mỗi lần phát sẽ tạo một vòng mới.

Giảm rủi ro bằng cách:

- Giới hạn inbound `eventTypes` đến **đúng các loại event đầu vào** của flow.
- Tách rõ sự kiện **đầu vào** và **đầu ra** về type hoặc cấu trúc contract, nếu chúng có ý nghĩa nghiệp vụ khác nhau.
- Chỉ phát sự kiện mới sau khi đã chuyển trạng thái nghiệp vụ cần thiết; không phát lại event nhận được như một thao tác mặc định.
- Nếu logic bắt buộc nhận lại cùng type, cần điều kiện dừng hoặc chống trùng rõ ràng, chẳng hạn `eventId` đã xử lý.
- Xem xét toàn bộ Spring context vì event có thể đi đến nhiều listener ngoài flow bạn vừa viết.

**Không dùng mỗi type filter để ngăn vòng lặp nếu outbound lại phát chính type đã được inbound cho phép**. Khi đó phải thay topology hoặc thiết kế điều kiện dừng.

## 11. Kiểm thử bộ lọc ở đúng ranh giới

Một bộ test tốt nên quan sát **ba điểm riêng biệt**: số message vào `rawInvoiceEvents`, số message đi tới `validInvoiceEvents`, và số message bị gửi đến `discardedInvoiceEvents`.

| Test | Sự kiện phát | Sau `eventTypes` | Sau `@Filter` |
| --- | --- | --- | --- |
| T1 | `InvoicePaidEvent("INV-01", 100.00)` | Có message vào `rawInvoiceEvents` | Chỉ vào `validInvoiceEvents` |
| T2 | `InvoicePaidEvent("INV-02", 0.00)` | Có message vào `rawInvoiceEvents` | Chỉ vào `discardedInvoiceEvents` |
| T3 | `InvoicePaidEvent("INV-03", -5.00)` | Có message vào `rawInvoiceEvents` | Chỉ vào `discardedInvoiceEvents` |
| T4 | `ContextRefreshedEvent` | Không có message từ adapter chuyên InvoicePaid | Không consumer nào của ví dụ xử lý |
| T5 | `InvoiceCancelledEvent` | Không có message từ adapter chuyên InvoicePaid | Không consumer nào của ví dụ xử lý |
| T6 | `MessagingEvent` có payload `InvoicePaidPayload`, nhưng inbound chỉ nghe `InvoicePaidEvent.class` | Không có message từ adapter chuyên InvoicePaid | Không consumer nào của ví dụ xử lý |
| T7 | Đổi cấu hình sang nhận `MessagingEvent.class` | Có message mang payload/header gốc | Phải đổi predicate/consumer theo payload type mới |

Cách kiểm thử:

1. Trong test Spring context, thay consumer ví dụ bằng **probe** ghi nhận ID sự kiện và tên channel; sử dụng `CopyOnWriteArrayList` hoặc cấu trúc thread-safe nếu có executor.
2. Phát riêng từng event qua `ApplicationEventPublisher`; reset probe sau mỗi ca.
3. Assert đúng nhánh và đúng số lần nhận, tránh chỉ kiểm tra console log.
4. Khi dùng `DirectChannel` và multicaster đồng bộ, kết quả có thể assert ngay sau khi `publishEvent(...)` trả về.
5. Khi chuyển sang async, dùng `CountDownLatch`/`Awaitility` với timeout hợp lý; không chỉ dựa vào `Thread.sleep(...)`.
6. Thêm một ca kiểm thử event cùng type nhưng có subclass nếu contract muốn chấp nhận subclass, để khẳng định hành vi lọc đúng theo phiên bản đang dùng.

**Thử nghiệm lỗi kiểu dữ liệu:** tạm bỏ `setEventTypes(...)` nhưng giữ predicate nhận `InvoicePaidEvent`. Phát một event framework và quan sát chỗ lỗi xảy ra. Sau đó phục hồi type filter và xác nhận event framework không đi vào flow. Thử nghiệm này giúp phân biệt "event đã bị chặn đúng từ đầu" với "event vào flow rồi bị lỗi xử lý".

## 12. Checklist thiết kế

Trước khi triển khai flow event vào production, cần trả lời rõ:

| Câu hỏi | Quyết định cần ghi trong thiết kế |
| --- | --- |
| Flow nhận **những event type** nào? | Danh sách explicit ở `setEventTypes(...)` |
| Event do framework hay module khác có thể xuất hiện không? | Giới hạn type và test event ngoài hợp đồng |
| Sau inbound, **payload type thực tế** là gì? | Contract của `@Filter`, `@Transformer` và service activator |
| Có cần header `correlationId`, `traceId` không? | Dùng event DTO có metadata hoặc dạng message phù hợp |
| Điều kiện nghiệp vụ nào cần loại tiếp? | Predicate sau inbound, discard/metric |
| Từ chối event có phải lỗi không? | Drop, discard channel hoặc throw exception |
| Consumer có chạy trước commit không? | Transaction-bound listener hoặc outbox khi cần |
| Có thể tạo vòng lặp inbound/outbound không? | Phân tách event type và điều kiện dừng |
| Hệ thống ngoài cần xác nhận giao hàng không? | Chọn outbound adapter và retry/durable transport riêng |

## 13. Bài tập thực hành

**Bài tập 1 — Lọc chính xác event type.** Viết ba loại sự kiện `InvoicePaidEvent`, `InvoiceCancelledEvent` và `InventoryUpdatedEvent`. Cấu hình inbound chỉ cho `InvoicePaidEvent` và kiểm tra rằng hai loại còn lại không xuất hiện trên `rawInvoiceEvents`.

**Bài tập 2 — Discard và audit.** Mở rộng `InvoicePaidEvent` thêm `currency`. Chỉ chấp nhận event có `amount > 0` và `currency == "VND"`, gửi các message bị từ chối vào `discardedInvoiceEvents` để ghi lý do loại bỏ.

**Bài tập 3 — Payload mapping.** Cấu hình `payloadExpression` trả về `invoiceId`; sửa transformer hoặc consumer để nhận kiểu `String`, rồi giải thích vì sao filter cũ dựa trên `amount` không còn dùng nguyên xi được.

**Bài tập 4 — Giữ metadata.** Phát một `MessagingEvent` có message header `correlationId`, cấu hình adapter tương ứng và kiểm tra header còn tồn tại sau ranh giới event. So sánh với việc phát POJO trực tiếp.

**Bài tập 5 — Ngăn vòng lặp.** Tạo flow có cả inbound và outbound event adapter. Chứng minh một topology phát lại cùng event type có nguy cơ lặp, rồi sửa bằng cách tách type cho sự kiện đầu ra hoặc sử dụng cơ chế chống trùng.

**Bài tập 6 — Kết nối hệ thống ngoài.** Sau nhánh `validInvoiceEvents`, nối một outbound adapter phù hợp để phát sự kiện hóa đơn đã được lọc sang Kafka/JMS hoặc HTTP. Phân biệt lỗi contract, lỗi filter và lỗi giao hàng ở endpoint ngoài; xác định vị trí retry và idempotency.

## Tài liệu tham khảo

- [Spring Integration — Spring ApplicationEvent Support](https://docs.spring.io/spring-integration/reference/event.html).
- [Spring Integration API — ApplicationEventListeningMessageProducer](https://docs.spring.io/spring-integration/api/org/springframework/integration/event/inbound/ApplicationEventListeningMessageProducer.html).
- [Spring Integration — Message Filter](https://docs.spring.io/spring-integration/reference/filter.html).
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html).
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events).
