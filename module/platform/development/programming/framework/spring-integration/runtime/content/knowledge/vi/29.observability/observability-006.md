# Message history và giới hạn kích thước history trong Spring Integration

## 1. Vì sao cần Message History khi vận hành message flow?

Trong **SPRING_INTEGRATION_RUNTIME**, một message có thể đi qua gateway, `MessageChannel`, transformer, router, filter, consumer endpoint, poller, executor, aggregator, retry advice và error flow. Các thành phần được thiết kế lỏng ghép: handler sau thường không biết message vừa qua những endpoint nào. Điều này giúp dễ thay đổi flow, nhưng khiến việc điều tra message thất lạc, đi nhầm nhánh hoặc xử lý chậm trở nên khó khăn.

**Message History** là cơ chế của Spring Integration giúp lưu một **danh sách những component được theo dõi mà message đã đi qua** trong một message header. Khi được bật, một component có tên/ID phù hợp có thể ghi thêm một entry về chính nó vào header `history`.

Chủ đề **Observability → Message history và giới hạn kích thước history** nhằm:

1. Hiểu định dạng header `history`, cách bật/tắt và đọc history ở runtime.
2. Phân biệt message history với distributed tracing, metrics, application logs và message store.
3. Giải thích vì sao history tăng kích thước ở loop/retry/replay hoặc flow dài.
4. Giới hạn **phạm vi theo dõi**, giới hạn **dữ liệu trình bày**, và khi thật sự cần thì **reset history tại một ranh giới được chọn**.
5. Hiểu thay đổi của Spring Integration 6.3 đối với append-only history và việc clone history khi fan-out.
6. Tích hợp quan sát với thread, poller, transaction, recovery, correlation và backend persistence.

**Quy tắc quan trọng:** `tracked-components` giới hạn **component được ghi**, không có nghĩa header `history` được đảm bảo tối đa N entries. Trong tài liệu/Javadoc Spring Integration đang được tham chiếu, không có một thuộc tính cấu hình công khai thống nhất như `maxHistorySize=20` dành cho `MessageHistoryConfigurer`. Khi muốn một *hard bound*, ứng dụng phải thiết kế rõ ranh giới/chiến lược của mình.

~~~mermaid
flowchart LR
    P["Producer"] --> C1["ordersIn"]
    C1 --> T["normalizeEndpoint"]
    T --> C2["normalized"]
    C2 --> H["ordersHandler"]
    H --> O["Downstream"]
    C1 -.-> X["Message header: history"]
    T -.-> X
    C2 -.-> X
    H -.-> X
    X --> D["Diagnostics / logs / metrics"]
~~~

Sơ đồ mang tính khái niệm: chỉ các **component trackable đã được chọn** mới góp entry; không có nghĩa mọi method Java trong flow đều được ghi tự động.

## 2. History là dữ liệu gì?

Spring Integration dùng `org.springframework.integration.history.MessageHistory` và header có tên do `MessageHistory.HEADER_NAME` định nghĩa (giá trị thường là `"history"`). `MessageHistory` triển khai `List<Properties>`. Mỗi phần tử thường chứa thông tin:

| Thuộc tính entry | Hằng số Java | Nội dung |
| --- | --- | --- |
| `name` | `MessageHistory.NAME_PROPERTY` | Tên/ID component được theo dõi |
| `type` | `MessageHistory.TYPE_PROPERTY` | Loại integration component |
| `timestamp` | `MessageHistory.TIMESTAMP_PROPERTY` | Thời điểm framework ghi dấu vết tại component |

Một ví dụ minh họa:

~~~text
history = [
  {name=ordersGateway, type=gateway,         timestamp=1795312800123},
  {name=normalizeEndpoint, type=transformer, timestamp=1795312800125},
  {name=ordersHandler, type=service-activator,timestamp=1795312800131}
]
~~~

**Đây là thông tin tuyến đường trong ứng dụng, không phải một bản audit giao dịch bất biến.** Chỉ những component được chọn và hỗ trợ tracking mới được ghi. Nếu có đoạn xử lý nằm ngoài hạ tầng component được theo dõi, hoặc adapter dựng lại message mà không giữ header, history có thể thiếu đoạn đó.

### Những gì history không đảm bảo

- Không tự chứa toàn bộ payload của từng hop.
- Không ghi thời gian bắt đầu/kết thúc xử lý của từng method.
- Không chứng minh một database transaction đã commit.
- Không bảo đảm event đã được ack từ broker.
- Không chứa một distributed span context tương đương OpenTelemetry.
- Không tự ghi toàn bộ `Thread.currentThread().getName()` hay mọi lần retry.
- Không bảo đảm bất biến/durable qua restart nếu message không được lưu bền vững.
- Không phải cơ chế phát message trở lại khi xử lý lỗi.

Timestamp của hai entries liền nhau có thể giúp ước lượng **khoảng cách giữa hai điểm tracking**. Hiệu của chúng không nhất thiết là handler duration: có thể gồm queue wait, polling interval, backoff, thread scheduling và I/O.

## 3. Bật tracking bằng Java hoặc XML

### Java configuration

Spring Integration hỗ trợ `@EnableMessageHistory`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableMessageHistory;

@Configuration
@EnableIntegration
@EnableMessageHistory
class MessageHistoryConfiguration {
}
~~~

Mặc định, cấu hình sẽ theo dõi **những component có tên/ID phù hợp** mà framework hỗ trợ. Để giảm phạm vi, khai báo các tên hoặc pattern:

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory({
        "ordersGateway",
        "normalize*",
        "*Outbound"
})
class FocusedHistoryConfiguration {
}
~~~

Các pattern ở trên chỉ là ví dụ; chúng phải khớp **component names** thực tế trong application context. Với bean/endpoint do DSL sinh tên tự động, cần xác minh tên ở runtime. Nếu pattern không khớp, history có thể trống hoặc thiếu entry dù flow chạy bình thường.

### XML namespace

~~~xml
<!-- Fragment XML: cần namespace int và schema Spring Integration phù hợp. -->
<int:message-history/>

<!-- Hoặc chỉ chọn một nhóm component: -->
<int:message-history
        tracked-components="ordersGateway, normalize*, *Outbound"/>
~~~

**Hai fragment là phương án thay thế**, không khai báo cả hai cùng lúc trong một application context để rồi kỳ vọng áp dụng hai bộ quy tắc độc lập.

Spring Integration khuyến nghị **một nguồn cấu hình message history** trong application context, qua `@EnableMessageHistory` hoặc `<int:message-history/>`. Không tự khai báo một generic `MessageHistoryConfigurer` bean để vòng qua cơ chế configuration registrar.

### Vì sao ID của endpoint quan trọng?

Giả sử có một handler `orderService.process()` nhưng endpoint của nó do annotation hoặc Java DSL sinh ra một tên khó dự đoán. Pattern `"orderService"` có thể **không khớp** component được ghi. Với DSL, hãy đặt ID rõ nếu muốn quan sát theo tên ổn định:

~~~java
// Đoạn Java DSL minh họa, cần bean OrderService và các imports thích hợp.
@Bean
IntegrationFlow orderFlow(OrderService orderService) {
    return IntegrationFlow.from("ordersIn")
        .handle(orderService, "process",
                e -> e.id("ordersHandlerEndpoint"))
        .get();
}
~~~

Trong ví dụ này, việc nhìn thấy entry với `ordersHandlerEndpoint` còn tùy loại component trackable và điểm framework ghi dấu; hãy kiểm tra history thực tế thay vì khẳng định mọi DSL step sinh đúng một entry.

## 4. Đọc history an toàn trong handler

API chính thức cung cấp `MessageHistory.read(Message<?>)`:

~~~java
import java.util.Properties;

import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;

static void logHistory(Message<?> message) {
    MessageHistory history = MessageHistory.read(message);

    if (history == null || history.isEmpty()) {
        System.out.println("NO_HISTORY");
        return;
    }

    System.out.println("HISTORY_ENTRIES=" + history.size());

    for (Properties entry : history) {
        String name = entry.getProperty(
                MessageHistory.NAME_PROPERTY, "unknown");
        String type = entry.getProperty(
                MessageHistory.TYPE_PROPERTY, "unknown");
        String timestamp = entry.getProperty(
                MessageHistory.TIMESTAMP_PROPERTY, "unknown");

        System.out.printf("HOP name=%s type=%s at=%s%n",
                name, type, timestamp);
    }
}
~~~

Đây là method Java độc lập, dùng trong consumer/diagnostics class. **Không gọi `history.toString()` bừa bãi** trong log production nếu history rất dài; định dạng này có thể tạo chuỗi lớn và áp lực GC.

Cách đọc từ header cũng hợp lệ:

~~~java
MessageHistory history = message.getHeaders().get(
        MessageHistory.HEADER_NAME, MessageHistory.class);
~~~

Nên xử lý được `null` vì tracking có thể tắt, message chưa qua component nào được chọn, hoặc một ranh giới đã loại header.

### Không sửa trực tiếp danh sách trong header

Trước Spring Integration 6.3, history được xử lý theo mô hình bất biến: mỗi lần ghi thêm hop thường phải tạo một history mới và message copy. Từ 6.3, framework dùng **append-only**: những lần `MessageHistory.write()` sau có thể thêm entry vào container history sẵn có, giảm tạo object và copy message.

Điều này **không cấp quyền** cho code nghiệp vụ tùy ý:

~~~java
// Không làm như vậy để "giới hạn history":
history.clear();
history.remove(0);
history.subList(0, 100).clear();
~~~

Tùy version và luồng nhiều consumer, thay đổi trực tiếp container có thể phá dấu vết của nhánh khác, gây race hoặc làm mất thông tin chẩn đoán. Khi cần bản rút gọn, hãy tạo **snapshot để quan sát** hoặc **dựng message mới tại một boundary rõ ràng**.

## 5. Ví dụ có thể chạy: ghi và đọc Message History

Ví dụ Java 17+, Spring Boot, Spring Integration core/starter phù hợp với Spring Boot. Đặt code vào một file `MessageHistoryDemoApplication.java` trong package `demo.integration`. `@EnableMessageHistory` sẽ bật tracking các component trackable có tên.

~~~java
package demo.integration;

import java.util.Properties;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableMessageHistory;
import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
@EnableMessageHistory
public class MessageHistoryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessageHistoryDemoApplication.class, args);
    }

    @Bean("ordersIn")
    MessageChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean("normalizedOrders")
    MessageChannel normalizedOrders() {
        return new DirectChannel();
    }

    @Bean
    ApplicationRunner send(
            @Qualifier("ordersIn") MessageChannel input) {

        return args -> input.send(MessageBuilder
                .withPayload(" order-42 ")
                .setHeader("eventId", "evt-42")
                .setHeader("traceId", "trace-42")
                .build());
    }
}

@MessageEndpoint
class HistoryDemoHandlers {

    @Transformer(
            inputChannel = "ordersIn",
            outputChannel = "normalizedOrders")
    public String normalize(String value) {
        return value.trim().toUpperCase();
    }

    @ServiceActivator(inputChannel = "normalizedOrders")
    public void inspect(Message<String> message) {
        MessageHistory history = MessageHistory.read(message);

        System.out.println("PAYLOAD=" + message.getPayload());
        System.out.println("EVENT_ID=" +
                message.getHeaders().get("eventId"));

        if (history == null) {
            System.out.println("NO_HISTORY");
            return;
        }

        System.out.println("HOPS=" + history.size());

        for (Properties entry : history) {
            System.out.printf("HOP name=%s type=%s at=%s%n",
                    entry.getProperty(MessageHistory.NAME_PROPERTY),
                    entry.getProperty(MessageHistory.TYPE_PROPERTY),
                    entry.getProperty(MessageHistory.TIMESTAMP_PROPERTY));
        }
    }
}
~~~

Kỳ vọng ổn định về **hành vi**, không cố định số entries:

~~~text
PAYLOAD=ORDER-42
EVENT_ID=evt-42
HOPS=<số lượng component đã được track>
HOP name=... type=... at=...
...
~~~

Bản in `HOP` cụ thể phụ thuộc tên/loại component được framework tạo và vị trí tracking của version đang dùng. Đừng viết test cứng rằng đúng ba entries chỉ vì sơ đồ có ba bước.

### Những điều ví dụ chứng minh

- Message có thể mang history khi đi qua channel/transformer/service activator.
- Handler đọc history mà không cần sửa method nghiệp vụ ở upstream.
- Header `eventId` được giữ để nối trace của message với nghiệp vụ.
- `@EnableMessageHistory` là cấu hình quan sát, không tự tạo message store hoặc transaction.
- `DirectChannel` đồng bộ giúp thấy thứ tự log rõ; khi đổi sang executor/poller, cần quan sát thêm thread, queue wait và error handling.

### Bật chọn lọc thay vì track tất cả

Nếu flow có hàng trăm thành phần, cân nhắc:

~~~java
@EnableMessageHistory({
        "ordersIn",
        "normalizedOrders",
        "*Endpoint"
})
~~~

Đây là cấu hình **thay thế** annotation không có tham số trong ví dụ. Tùy tên component thực tế, bạn có thể không nhìn thấy tất cả hop mong đợi; hãy điều chỉnh pattern dựa trên integration graph/beans đã xác minh.

## 6. Message History khác logs, metrics, tracing và audit thế nào?

| Cơ chế | Đơn vị quan sát | Thông tin chính | Phù hợp |
| --- | --- | --- | --- |
| **Message History** | Một header trên message | Tên, loại, timestamp của các tracked components | Xem một message đã đi qua đâu |
| **Structured logging** | Một log event | Context, exception, thread, business event ID | Điều tra sự cố cụ thể |
| **Micrometer metrics** | Counter/timer/distribution | Error rate, throughput, p95/p99 latency | Dashboard, alert và năng lực hệ thống |
| **Distributed tracing / OpenTelemetry** | Trace/span qua process/service | Span hierarchy, timing, context propagation | Debug nhiều service và asynchronous boundaries |
| **Message store** | Message hoặc message group được lưu | Payload, headers, state/correlation | Durability, aggregation, queue/replay |
| **Business audit/outbox** | Sự kiện nghiệp vụ durable | Ai/lúc nào/thay đổi gì, transaction state | Truy vết mang tính pháp lý/vận hành lâu dài |

Message history có thể hỗ trợ điều tra nhưng **không thay thế** distributed tracing hoặc audit bền vững. Ví dụ:

~~~text
history:
  ordersIn -> normalizeEndpoint -> shippingGateway

trace:
  service A span -> service B span HTTP 503 -> retry -> response

audit/outbox:
  eventId=evt-42, shipmentStatus=FAILED, committedAt=...
~~~

Cả ba phục vụ câu hỏi khác nhau. History thường không ghi tên thread; `timestamp` chỉ đánh dấu hop chứ không đủ phân biệt thời gian chờ trong executor với thời gian handler gọi HTTP.

## 7. Vì sao history có thể phát triển không giới hạn?

Một phần tử history không lớn theo bản chất, nhưng hệ thống có thể tạo **rất nhiều phần tử**.

### Flow dài và vòng lặp

~~~mermaid
flowchart LR
    IN["Input"] --> A["Transform"]
    A --> B["Router"]
    B --> C{"Đã hoàn tất?"}
    C -->|Chưa| R["Retry / requeue / loop"]
    R --> A
    C -->|Rồi| OUT["Output"]
~~~

Mỗi vòng qua những component được track có thể thêm entries vào message history nếu message vẫn giữ lịch sử. Sau N vòng, kích thước tăng xấp xỉ theo số lần track:

\[
H_{\text{entries}} \approx H_0 + N \cdot k
\]

Trong đó `H0` là số entries ban đầu, `k` là số component được track mỗi vòng. Đây là **ước lượng logic**, không phải công thức byte size chính xác.

### Fan-out và nhiều nhánh

Một splitter, `PublishSubscribeChannel`, router phát nhiều output hoặc wire tap có thể làm history được **sao chép/nhân theo nhánh**. Điều này làm tổng bộ nhớ dùng để giữ các history tăng theo số message/nhánh, dù độ dài history của từng message vẫn hợp lý.

### Message store và replay

Một `QueueChannel` dùng persistent message store hoặc aggregator lưu `MessageGroup` có thể phải serialize cả header `history`. Nếu history dài:

- Dữ liệu ghi vào DB/Redis/Mongo/broker lớn hơn.
- Serialize/deserialize và GC tăng chi phí.
- Số bytes trong queue, payload envelope hoặc database row tăng.
- Log nếu in cả headers trở nên dài và khó tìm lỗi.
- Khi restore/replay, toàn bộ các entry cũ có thể được mang tiếp rồi nối thêm entry mới.

**Không phải mọi adapter tự giữ header `history`.** Một số external adapter chuyển sang wire format riêng; history chỉ tồn tại nếu mapping header và serializer cho phép. Vì vậy phải kiểm tra trên chính đường đi production.

### Retry

Cần phân biệt:

- `RequestHandlerRetryAdvice` có thể gọi lại **cùng handler invocation** nhiều lần; không chắc mỗi attempt tạo message hoặc đi lại qua component tracking.
- Broker redelivery thường tạo một **delivery mới**, có thể tái sử dụng payload nhưng message headers/history được giữ hoặc tái tạo tùy adapter.
- Một vòng loop thực sự gửi message qua các channel được track nhiều lần có thể làm history tăng theo số vòng.

Vì vậy, **không** mặc định `history.size() == retryAttempts` hoặc deduce số broker deliveries từ lịch sử. Ghi attempt count/idempotency key ở một cơ chế riêng nếu cần.

## 8. Hai dạng "giới hạn kích thước" phải phân biệt

Có hai bài toán hoàn toàn khác nhau:

| Nhu cầu | Cách giải | Có làm giảm history header gốc? |
| --- | --- | --- |
| Chỉ hiển thị **N hops gần nhất** trên log/dashboard | Snapshot/read-only projection | **Không** |
| Gửi ít dữ liệu hơn sang hệ thống ngoài | Giữ một summary bounded, loại `history` tại boundary thích hợp | **Có**, tại boundary đó |
| Giảm tần suất thêm entries | `tracked-components` chọn ít component | Không giới hạn tuyệt đối số vòng |
| Không muốn production ghi history mọi lúc | Stop `MessageHistoryConfigurer` hoặc chỉ bật trong debug window | Những message đã có history vẫn giữ entries cũ |
| Giữ full trace nhưng không tăng kích thước message | External trace/log store theo `eventId`/`traceId` | Có thể bỏ history ở boundary, lưu dấu vết nơi khác |
| Hard cap mọi điểm trong flow | Cần chính sách nhiều ranh giới/thiết kế riêng | Không được cung cấp tự động bởi `@EnableMessageHistory` |

Đây là trung tâm của đề bài: **cắt log string** không cắt header. **Giảm tracked components** không đảm bảo số hop tối đa trong flow có vòng lặp. **Reset header tại một boundary** không giới hạn các hop mới được ghi về sau, trừ khi tiếp tục có policy tại những boundary tiếp theo.

## 9. Cách 1: chỉ giữ N hop gần nhất khi log

Nếu chỉ muốn log súc tích, không sửa message:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;

public final class HistoryProjection {

    private HistoryProjection() {
    }

    public static List<String> recentHopNames(
            Message<?> message, int maxEntries) {

        if (maxEntries < 1) {
            throw new IllegalArgumentException(
                    "maxEntries must be positive");
        }

        MessageHistory history = MessageHistory.read(message);
        if (history == null || history.isEmpty()) {
            return List.of();
        }

        // Read-only snapshot, không xóa/sửa header lịch sử gốc.
        List<Properties> snapshot = new ArrayList<>(history);

        int from = Math.max(0, snapshot.size() - maxEntries);
        List<String> result = new ArrayList<>();

        for (int i = from; i < snapshot.size(); i++) {
            Properties entry = snapshot.get(i);
            result.add(entry.getProperty(
                    MessageHistory.NAME_PROPERTY, "unknown"));
        }

        return List.copyOf(result);
    }
}
~~~

Dùng:

~~~java
List<String> lastFive =
        HistoryProjection.recentHopNames(message, 5);

logger.info("eventId={} historyTail={}",
        message.getHeaders().get("eventId"), lastFive);
~~~

Ưu điểm:

- Dễ hiểu, ít ảnh hưởng flow.
- Không phá correlation, reply/error headers, hoặc bất kỳ branch nào.
- Có thể chọn `maxEntries` theo từng log view.
- Hữu ích khi một message có nhiều hop nhưng người vận hành chỉ cần biết đoạn cuối.

**Giới hạn:** `MessageHistory` đầy đủ **vẫn nằm trong header**. Memory, serialization và network overhead của history không giảm; phương án này chỉ giới hạn dữ liệu **hiển thị**.

### Giới hạn ký tự khác giới hạn số entries

Nếu một component name dài hoặc dữ liệu log bị formatter mở rộng, năm hops vẫn có thể tạo log lớn. Có thể áp thêm giới hạn số ký tự:

~~~java
String joined = String.join(" > ", lastFive);
int maxChars = 300;

String bounded = joined.length() <= maxChars
        ? joined
        : "..." + joined.substring(
                joined.length() - (maxChars - 3));
~~~

Đây là **string presentation budget**, không phải cap trên bytes đã serialize. Với Unicode/UTF-8, 300 Java chars không đồng nghĩa 300 bytes. Khi cần ngân sách network/broker, phải đo **encoded byte size thực**.

## 10. Cách 2: chọn ít tracked components

Cách ít xâm lấn nhất để giảm tăng trưởng thường là giới hạn danh sách component được track:

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory({
        "ordersGateway",
        "payment*",
        "shippingOutbound"
})
class HistoryOnlyForCriticalPath {
}
~~~

Hoặc:

~~~xml
<int:message-history
        tracked-components="ordersGateway, payment*, shippingOutbound"/>
~~~

Gợi ý chọn:

1. **Ingress**: gateway/inbound adapter để thấy message vào từ đâu.
2. **Điểm phân nhánh**: router, filter hoặc splitter quyết định đường đi.
3. **Ranh giới I/O quan trọng**: HTTP/JMS/JDBC outbound gateway.
4. **Điểm hoàn tất**: handler có business commit, trước khi trả reply/ack.
5. **Điểm recovery**: error route hoặc endpoint ghi DLQ nếu có thể theo dõi.

Không nhất thiết track mọi transformer hoặc channel trung gian khi mục tiêu là debug định tuyến. Tuy nhiên hãy bảo đảm ID component ổn định qua deploy và pattern đúng với integration configuration.

### Runtime thay đổi pattern qua MessageHistoryConfigurer

`MessageHistoryConfigurer` có lifecycle và quản trị qua JMX (khi `IntegrationMBeanExporter` xuất MBean tương ứng). Javadoc chỉ rõ **không được đổi pattern trong khi configurer đang chạy**: cần stop trước.

~~~java
// Minh họa code vận hành nội bộ, có bean được Spring quản lý.
MessageHistoryConfigurer configurer = ...;

configurer.stop();
try {
    configurer.setComponentNamePatternsString(
            "ordersGateway,payment*,shippingOutbound");
}
finally {
    configurer.start();
}
~~~

Đây là snippet quản trị, không phải cấu hình bean thủ công; framework nên tạo configurer qua `@EnableMessageHistory` hoặc XML namespace. Trước khi dùng trong production, phải xác minh hành vi trên Spring Integration version đang chạy và cơ chế bảo vệ quyền quản trị.

Trong khoảng configurer đang stop, các message **không được ghi thêm** entry mới tại các component đó; các entries cũ không tự biến mất. Nếu bạn đổi pattern trong lúc còn in-flight messages, dấu vết của cùng một message có thể chỉ ghi một phần tuyến đường.

### JMX và Control Bus

MBean được tài liệu mô tả với dạng tên:

~~~text
<domain>:name=messageHistoryConfigurer,type=MessageHistoryConfigurer
~~~

Domain tùy cấu hình exporter. Có thể dùng công cụ JMX hoặc API nội bộ để stop, đổi pattern, start. Đừng mở Control Bus/JMX write operations cho client không tin cậy. Đổi settings quan sát nên có audit: ai thay, lúc nào, lý do, pattern cũ/mới.

## 11. Cách 3: tóm tắt và loại history tại ranh giới đã chọn

Khi có **ngân sách bytes nghiêm ngặt** trước broker, persistent store hoặc HTTP, có thể thiết kế một điểm chuyển tiếp:

1. Đọc history từ message hiện tại.
2. Ghi một **summary bounded** vào log/trace store hoặc header ứng dụng nhỏ.
3. Dựng message mới không chứa header `MessageHistory.HEADER_NAME`.
4. Cho downstream tạo history mới nếu tracking còn bật.

Đây là **chính sách ứng dụng**, không phải property có sẵn của `MessageHistoryConfigurer`.

### Ví dụ Java: reset history và giữ preview tối đa 5 hop/200 ký tự

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class HistoryBoundary {

    private HistoryBoundary() {
    }

    public static <T> Message<T> compactBeforePersistence(
            Message<T> input, int keepLastEntries, int maxChars) {

        if (keepLastEntries < 1 || maxChars < 4) {
            throw new IllegalArgumentException("Invalid history limits");
        }

        MessageHistory history = MessageHistory.read(input);
        if (history == null || history.isEmpty()) {
            return input;
        }

        // Copy để đọc; không mutate MessageHistory shared của input.
        List<Properties> snapshot = new ArrayList<>(history);
        int from = Math.max(0, snapshot.size() - keepLastEntries);

        List<String> names = new ArrayList<>();
        for (int i = from; i < snapshot.size(); i++) {
            names.add(snapshot.get(i).getProperty(
                    MessageHistory.NAME_PROPERTY, "unknown"));
        }

        String summary = String.join(" > ", names);
        if (summary.length() > maxChars) {
            summary = "..." + summary.substring(
                    summary.length() - (maxChars - 3));
        }

        return MessageBuilder.fromMessage(input)
                .removeHeader(MessageHistory.HEADER_NAME)
                .setHeader("historyPreview", summary)
                .setHeader("historyDroppedEntries",
                        snapshot.size() - names.size())
                .build();
    }
}
~~~

**Ý nghĩa chính xác:**

- `historyPreview` là **header ứng dụng** có giới hạn; nó **không phải** một `MessageHistory` chuẩn.
- Header `"history"` gốc bị loại khỏi **message mới** đi qua boundary.
- Sau boundary, một component được track có thể khởi tạo `MessageHistory` mới và thêm entries tiếp. Giới hạn này chỉ áp tại **vị trí gọi hàm**, không áp toàn bộ downstream.
- `historyDroppedEntries` là số entries ngoài phần preview được giữ theo **đếm entry**, không phải số bytes bị tiết kiệm.
- Dùng loại header/string mà serializer của broker/store hiểu; nếu lưu bền vững, kiểm tra compatibility và retention.

Không thực hiện thủ thuật `history.subList(...).clear()` rồi tiếp tục dùng chung message. Với Spring Integration 6.3+, history có thể là container append-only được chia sẻ trong một số tình huống custom fan-out; mutate trực tiếp làm sai dấu vết của nhánh khác.

### Gắn boundary vào flow

Một mô hình flow rõ ràng:

~~~text
source -> tracked handlers -> boundary transformer
       -> persistent QueueChannel / outbound adapter
       -> downstream handlers -> new tracking segment
~~~

Ở điểm `boundary transformer`, message được xây dựng lại bằng `HistoryBoundary.compactBeforePersistence(...)`. Nếu component này hoặc channel sau nó được track, một vài entries **mới** có thể xuất hiện trước khi message được store. Muốn kiểm soát header **tại thời điểm ghi store**, phải xác nhận chính xác vị trí component ghi history và adapter header mapper.

Nếu cần strict byte ceiling trên **wire**, áp rule ngay tại serialization/header-mapping boundary và kiểm tra payload + headers **sau encoding**. Một `maxChars` cho preview chỉ là một phần của tổng ngân sách bytes.

### Không nên reset history tại mọi endpoint

Nếu bỏ header quá sớm hoặc ở mỗi bước:

- Bạn mất tuyến đường đầy đủ cần điều tra.
- Các lỗi ở downstream không còn biết các hop đầu.
- Trace giữa hai hệ thống khó nối hơn nếu thiếu `traceId`/`eventId`.
- Một splitter/aggregator dựa vào headers khác vẫn có thể hoạt động, nhưng việc rebuild message thiếu sót có thể làm mất correlation/sequence/reply/error headers.

Nên đặt boundary có chủ đích: trước broker/store, giữa hai domain, trước network egress, hoặc tại điểm chuyển từ full diagnostics sang compact trace. **Giữ logical event ID và correlation headers** khi dựng message mới.

## 12. Cách 4: xuất trace ra hệ thống ngoài rồi giữ header nhỏ

Nếu cần tra cứu **toàn bộ tuyến đường** mà message không mang lịch sử dài:

~~~mermaid
flowchart LR
    M["Message(eventId, traceId)"] --> T["Flow components"]
    T --> O["Observation/log/trace records"]
    O --> S[("Trace/log backend")]
    T --> B["Compact message: eventId + traceId"]
    B --> D["Broker / persistent store"]
    D --> T2["Downstream"]
    T2 --> S
~~~

Các span/log records ở ngoài có thể mang `eventId`, `traceId`, endpoint, start/end time, outcome và exception. Khi cần điều tra, người vận hành truy vấn theo ID. Đây là một lựa chọn kiến trúc khác với `MessageHistory` header — không phải tự động chuyển toàn bộ history của framework thành distributed trace.

### Khi nào chọn external trace?

| Nhu cầu | Đề xuất |
| --- | --- |
| Debug flow ngắn, nội bộ một JVM | MessageHistory chọn lọc |
| Flow có nhiều route rẽ nhánh/retry | MessageHistory + log/trace theo eventId |
| Qua nhiều service, broker và network | Distributed tracing + trace propagation rõ |
| Message phải tồn tại nhiều ngày trong store | Bounded headers, audit/log/trace external với retention |
| Yêu cầu bằng chứng nghiệp vụ đã commit | Durable business audit/outbox, không chỉ history |

Giữa các service khác nhau, history không tự động hoạt động như distributed tracing. Một message serializer/adapter có thể không map header `history` sang broker, hoặc consumer khác phiên bản không decode được outer header. Hãy mang `traceId` và các headers tối thiểu, kiểm soát schema và mapping.

## 13. Thay đổi quan trọng từ Spring Integration 6.3

### Trước 6.3: copy-on-write logic

Tài liệu phiên bản 6.2 mô tả history immutable: mỗi track thường tạo **instance MessageHistory mới** và message copy mới. Với flow dài, việc copy danh sách lặp lại có thể tăng allocation và CPU.

### Từ 6.3: append-only history container

Tài liệu mới mô tả:

- Lần ghi dấu đầu tiên có thể tạo message mới với container `MessageHistory`.
- Những lần `MessageHistory.write()` tiếp theo **append entries** vào header sẵn có, giảm copy message.
- Khi framework tạo nhiều output từ cùng một message, những component như `PublishSubscribeChannel`, `AbstractMessageRouter`, `WireTap` hoặc splitter được điều chỉnh để **clone history** giữa các nhánh phù hợp.

Điều này có thể cải thiện performance, nhưng **không đồng nghĩa kích thước history bị giới hạn tự động**. Một message đi qua hàng nghìn tracked hops vẫn có thể giữ hàng nghìn entries.

### Custom fan-out phải clone history khi dựng các nhánh

Nếu bạn tự viết component tạo nhiều message từ cùng input, cần tránh hai nhánh giữ chung container mutable history. Với các builder của Spring Integration từ 6.3, API được tài liệu khuyến nghị là:

~~~java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

// Snippet Spring Integration 6.3+, dùng builder của Spring Integration.
Message<String> child = MessageBuilder
        .withPayload("child-" + index)
        .copyHeaders(parent.getHeaders())
        .cloneMessageHistoryIfAny()
        .build();
~~~

Với snippet này, `parent` là message gốc, `index` là biến thứ tự của nhánh. Đây là đoạn dùng **trong custom splitter/multi-output code**, cần bố trí headers correlation/sequence cho đúng nghiệp vụ. `cloneMessageHistoryIfAny()` giúp nhánh có snapshot riêng; không nên gọi nếu mục đích là giữ cùng một message instance đi qua một luồng đơn.

**Lưu ý về import:** `org.springframework.integration.support.MessageBuilder` khác `org.springframework.messaging.support.MessageBuilder`. API `cloneMessageHistoryIfAny()` thuộc `AbstractIntegrationMessageBuilder` của Spring Integration. Nếu version dự án chưa có API này, xem lại cơ chế copy headers/history tương ứng, đừng copy snippet không tương thích.

## 14. History và các loại channel/endpoint tại runtime

| Thành phần | Điều gì xảy ra với message? | Điểm đáng quan sát |
| --- | --- | --- |
| `DirectChannel` | Dispatch đồng bộ trên thread gửi | Hops có thứ tự gần call stack; exception có thể quay về sender |
| `ExecutorChannel` | Handoff sang worker thread | Gap giữa hai timestamps có thể gồm queue wait |
| `QueueChannel` + poller | Message đợi rồi mới được poll | Gap có thể gồm interval/timeout và backlog |
| `PublishSubscribeChannel` | Một input tới nhiều subscribers | Cần history riêng theo nhánh khi có multiple outputs |
| Router | Rẽ nhánh theo routing key | Mỗi nhánh nên giữ dấu vết riêng |
| Splitter | Một input thành nhiều messages | History từ cha cần được copy phù hợp cho các con |
| Aggregator/resequencer | Gắn nhiều messages vào group | History của output không chứng minh toàn bộ histories của mọi phần đã gom |
| Retry advice | Handler có thể được gọi nhiều attempts | History entry count không phải retry count |
| Outbound gateway | Gửi ra ngoài rồi có reply | Header mapping và flow reply quyết định history được giữ ra sao |

Khi dùng executor, poller hay broker, **timestamp gap không phân loại được lý do chậm**. Cần metrics executor queue, poll duration, handler timers, connection pool và spans để biết phần nào gây latency.

### Aggregator và correlation

`MessageHistory` mô tả đường đi của **một message cụ thể**. Aggregator xử lý nhiều message có cùng `correlationId` và `sequenceNumber` khác nhau. History trên **output message** có thể chỉ biểu diễn một phần mối quan hệ; không thay thế `MessageGroupStore` để xem mọi message của group.

Khi debug group treo:

1. Kiểm tra correlation strategy và số phần group đã nhận.
2. Kiểm tra `sequenceNumber`, `sequenceSize`, release strategy.
3. Đối chiếu history của **từng input message** nếu còn.
4. Kiểm tra message store, locks, transaction và expiry.
5. Dùng eventId/correlationId nối các log/spans thay vì chỉ nhìn một history header.

## 15. ErrorMessage, recovery và lịch sử trước thời điểm lỗi

Khi handler ném exception, lỗi có thể:

- Truyền về caller với `DirectChannel`.
- Được poller/executor error handler chuyển thành `ErrorMessage`.
- Được retry advice thử lại trong cùng invocation.
- Được recovery callback gửi tới recovery channel.
- Thành reactive `onError` signal trong một publisher khác.

**Không có bảo đảm rằng `ErrorMessage` luôn chứa một history riêng đại diện đầy đủ tuyến đường của failed message.** Khi có `MessagingException`, dùng `getFailedMessage()`; khi có `ErrorMessage`, xem `getOriginalMessage()` nếu được cung cấp.

~~~java
import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

public static Message<?> failedMessage(ErrorMessage error) {
    Message<?> original = error.getOriginalMessage();
    if (original != null) {
        return original;
    }

    Throwable cause = error.getPayload();
    if (cause instanceof MessagingException messaging) {
        return messaging.getFailedMessage();
    }

    return null;
}
~~~

Sau đó:

~~~java
Message<?> failed = failedMessage(error);
MessageHistory history = MessageHistory.read(failed);

logger.warn("eventId={} hopCount={} failure={}",
        failed == null ? "unknown" :
            failed.getHeaders().get("eventId"),
        history == null ? 0 : history.size(),
        error.getPayload().getClass().getSimpleName());
~~~

Đây là snippet cho error consumer; cần class chứa method, `logger` và imports phù hợp. `MessageHistory.read(null)` trả về `null` theo API, nên không cần ép một message giả.

### Không dùng history để chứng minh retry

Cùng một message có thể được retry nhiều lần **mà không thêm hop mới** nếu advice bọc invocation của một handler. Mặt khác, loop gửi message lại qua các channel có thể thêm nhiều hop mà vẫn chỉ là một logical event. Muốn quan sát retry đúng, đo **attempt count** trong retry policy, đặt idempotency key ổn định và ghi outcome ở recovery.

## 16. History qua persistent Message Store và broker

Khi message được lưu trong `JdbcChannelMessageStore`, Redis hoặc MongoDB, việc encode outer `Message<?>` có thể phải xử lý cả header `history`. Các rủi ro:

- Serializer/provider không đọc được representation header sau khi nâng cấp.
- Header quá lớn làm tăng kích thước record, network I/O hoặc số lần allocate.
- Message replay có thể mang history cũ cộng thêm các entries mới.
- Với schema mapping không giữ header, history bị mất sau khi đi qua broker.
- Không có index/search theo history trong store trừ khi bạn thiết kế riêng.

### Tình huống giới hạn kích thước khi persist

Ví dụ hệ thống đặt ngân sách **16 KiB cho toàn bộ headers đã encode**. Nếu mỗi hop sau encoding trung bình khoảng **250 bytes** trong thử nghiệm, 50 hops đã chiếm khoảng **12,5 KiB**, chưa tính các headers khác. Đây là **giả định minh họa**, không phải kích thước hay giới hạn mặc định của Spring Integration.

Công thức planning:

\[
B_{\text{headers}} \approx B_{\text{base}} + n \times B_{\text{hop}}
\]

Trong thực tế, phải đo `B_headers` **sau serialization** của backend đang dùng. Java `Properties` có overhead in-memory khác JSON/protobuf bytes; một message header JSON nhỏ có thể nặng hơn nhiều trên heap vì số lượng objects.

### Những cách đo nên có

1. Lấy representative messages: flow ngắn, dài, retry, splitter, nhiều headers.
2. Đo `history.size()` theo endpoint quan trọng.
3. Encode bằng serializer/header mapper **thật** của broker/store.
4. Đo bytes tổng, bytes headers, bytes history nếu mapper cho phép.
5. Thử message history dài, cả phía gửi lẫn phía nhận qua restart.
6. Theo dõi GC, heap, throughput, latency poll/serialize và queue depth.
7. Nếu có hard cap của broker, đảm bảo hợp đồng đo **tổng** payload + headers và các limits liên quan.

Không lấy một số bytes/hop không đo được rồi áp dụng làm SLA.

## 17. Observability overhead và trade-off trong production

Message History là một **tính năng quan sát có chi phí**.

| Chi phí | Vì sao xảy ra | Giảm thế nào |
| --- | --- | --- |
| Allocation/heap | `Properties` entries và container history | Track subset, giới hạn vòng lặp, tóm tắt tại boundary |
| CPU | Ghi dấu, copy/clone nhánh, serialize | Tắt khi không cần, đo overhead, dùng tracing/metrics phù hợp |
| GC pressure | Nhiều message và history entries tồn tại | Giảm message retention, giảm số hop |
| Network/backend bytes | Headers đi vào queue/broker/store | Không mang full history qua boundary nếu không cần |
| Log volume | Formatter in full header/history | Log last N entries + eventId/traceId |
| Privacy | Component names/topology có thể lộ chi tiết nội bộ | Mask/redact, giới hạn export và retention |
| Debug ambiguity | Thiếu hop do pattern, tắt/bật hoặc mất header | Ghi config/version và kiểm tra thực tế |

**Không phải tối ưu duy nhất là tắt history toàn bộ.** Có thể bật tạm thời trong incident window, chọn component chiến lược, ghi ở level DEBUG, và dùng distributed tracing/metrics để theo dõi latency liên tục với overhead đã đo.

### Khi nào tắt tracking?

- Flow có vòng lặp nhiều lần khiến mỗi message mang hàng nghìn entries.
- Persistent store hoặc broker có limit nhỏ cho header.
- Trace/log backend đã cung cấp đường đi cần thiết với cost thấp hơn trong bối cảnh cụ thể.
- Tài nguyên CPU/heap đang bị history tracking chi phối theo profiling.

Nhưng trước khi tắt, phải đảm bảo vẫn có `eventId`, `traceId`, correlation và error records đủ để điều tra.

## 18. Metrics và dashboard hữu ích

| Metric gợi ý | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `message.history.entries` distribution | Số entries khi message tới điểm đo | p50/p95/p99, theo endpoint |
| `message.history.over_budget` count | Message vượt budget entries | Đừng tag full message ID |
| `message.history.preview.length` | Kích thước summary/log | Không thay byte-size measurement |
| `message.header.encoded.bytes` | Tổng header bytes sau serialize | Theo adapter/store format |
| `message.flow.duration` | End-to-end latency | Dựa vào tracing/timestamps đúng boundary |
| `message.store.write.latency` | Chi phí persistence | Phân biệt encode/DB I/O |
| `poller.duration` / `queue.oldest.age` | Backlog/poller chậm | History gap có thể chứa queue wait |
| `handler.error.count` / `retry.attempts` | Lỗi và attempts thực tế | Không suy từ history size |

Các tên trên là **gợi ý instrument**, không phải tất cả đều có sẵn trong Spring Integration hoặc Micrometer.

Không dùng `eventId`, `orderId` hoặc full history string làm **metric labels** vì cardinality quá cao. Có thể dùng endpoint name, channel, outcome, application version. Log/traces mới chứa correlation ID và business ID theo chính sách bảo mật.

Một ví dụ chỉ báo budget ở handler:

~~~java
MessageHistory history = MessageHistory.read(message);
int entries = history == null ? 0 : history.size();

if (entries > 32) {
    logger.warn("history budget exceeded: endpoint={} entries={} eventId={}",
            "ordersHandler", entries, message.getHeaders().get("eventId"));
}
~~~

Đoạn này **cảnh báo** chứ không giới hạn header. Để giảm overhead thực, dùng tracking scope/boundary đã trình bày.

## 19. Version và API: những điều cần kiểm tra trước khi nâng cấp

| Phiên bản/khía cạnh | Điều cần nhớ |
| --- | --- |
| Spring Integration 6.2 và trước | History theo mô hình bất biến/copy-on-write như mô tả trong tài liệu phiên bản đó |
| Spring Integration 6.3+ | History ghi theo append-only trong container, framework clone ở những điểm fan-out đã biết |
| `@EnableMessageHistory` | Dùng để bật chọn lọc component names/patterns, không có documented maxEntries setting |
| `MessageHistoryConfigurer` | Có runtime lifecycle/JMX, đổi patterns phải stop configurer trước |
| `MessageHistory.read(message)` | Đọc header; có thể trả `null` |
| `cloneMessageHistoryIfAny()` | API 6.3+ của Spring Integration builder cho custom fan-out |
| Persistent store | Phải kiểm tra serializer/headers/schema và dữ liệu cũ qua restart |
| Endpoint đang chạy | Không phải mọi component được named hoặc trackable giống nhau |

Khi chuyển từ 6.2 sang 6.3+, code nghiệp vụ **không nên** dựa vào việc `MessageHistory` luôn là một instance bất biến mới. Hãy kiểm tra trường hợp splitter/custom router tạo nhiều outputs và code nào đang giữ reference tới history của message cũ.

## 20. Chẩn đoán các tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| Message không có header `history` | Chưa enable, pattern không khớp, chưa qua component được track | Kiểm tra `@EnableMessageHistory`, ID, `MessageHistory.read()` |
| History chỉ có một vài hops | Chỉ track subset hoặc có đoạn không hỗ trợ | So sánh component list với integration graph |
| History mất sau khi qua broker | Header mapper/serializer bỏ header | Kiểm tra actual encoded headers và adapter |
| History tăng rất nhanh | Flow loop, requeue qua tracked channels | Tìm cùng `name/type` lặp trong timeline |
| History size khác số retry | Retry advice thực hiện handler invocation không tạo hop mới | Đo retry counter riêng |
| Fan-out branches có history "lẫn nhau" | Custom multi-producer chia sẻ mutable history (6.3+) | Clone history cho từng nhánh |
| `history.toString()` làm log quá lớn | Logging full header | Chỉ log tail N và giới hạn ký tự |
| Message store size tăng | Header được persist nhiều entries | Đo encode bytes, giảm tracked components/reset tại boundary |
| Có timestamp gap dài | Queue wait, scheduler, I/O hoặc retry | Kết hợp poller/executor/handler metrics |
| Handler báo success nhưng DB rollback | History chỉ ghi đường đi, không chứa commit outcome | Kiểm tra transaction log/DB |
| ErrorMessage không có history | Không có original message hoặc failed message | Truy `getOriginalMessage()`/`getFailedMessage()` |
| Đổi patterns runtime bị từ chối | Configurer đang running | Stop configurer rồi đổi/start lại |
| Track patterns khác nhau giữa nodes | Mỗi application context config riêng | Đồng bộ cấu hình, kiểm tra deploy version |
| Message history vượt giới hạn broker | Không giới hạn tại serialization boundary | Bounded summary + remove header, test real bytes |

### Quy trình debug có bằng chứng

1. **Xác định message:** eventId, correlationId, traceId và nguồn.
2. **Đối chiếu graph:** component nào thực sự có ID, endpoint nào start/stop.
3. **Kiểm tra configurer:** tracking đang bật không, patterns nào active, version ứng dụng.
4. **Đọc history:** dùng `MessageHistory.read()` và lưu snapshot ngắn để phân tích.
5. **Xem timing:** timestamp gap có trùng với queue wait, poller interval hoặc I/O không.
6. **Tìm loops/retries/fan-out:** phân biệt message vòng lại với retry cùng handler.
7. **Xem bytes thực:** serializer/broker/store có giữ history, dung lượng header là bao nhiêu.
8. **Đánh giá biện pháp:** chọn ít components, log tail, hoặc compact tại boundary.
9. **Kiểm thử lại:** restart, async, splitter, aggregator và recovery paths.
10. **Chỉ kết luận hoàn tất nghiệp vụ** khi DB/broker/error store xác nhận outcome.

## 21. Bài tập thực hành

1. **Bật/tắt:** chạy `MessageHistoryDemoApplication` với và không có `@EnableMessageHistory`, so sánh `MessageHistory.read()` và log.
2. **Lọc component:** thay annotation bằng pattern khớp `ordersIn` và `normalizedOrders`; giải thích entry nào còn, entry nào mất.
3. **Đo history dài:** tạo loop có giới hạn số vòng ở môi trường test và đo `history.size()` theo số vòng, không để loop vô hạn.
4. **Tail projection:** dùng `HistoryProjection.recentHopNames(message, 5)`; xác nhận log chỉ có tối đa năm names nhưng header gốc không đổi.
5. **Giới hạn ký tự:** cắt summary còn 300 chars; so sánh giới hạn ký tự với bytes UTF-8 sau encode.
6. **Boundary reset:** thêm `HistoryBoundary.compactBeforePersistence(...)` trước một channel/store test; so sánh size trước/sau, xem history mới xuất hiện khi downstream được track.
7. **Fan-out:** với Spring Integration 6.3+, tạo custom splitter hai nhánh; thử clone history rồi quan sát branch-specific hops.
8. **Executor:** đưa `ExecutorChannel` giữa hai handler, log thread và timestamps; giải thích vì sao gap không chỉ là handler latency.
9. **Poller:** thêm `QueueChannel` và polling consumer, cho message chờ vài giây; so sánh history gap, queue age và poller duration.
10. **Retry:** thêm `RequestHandlerRetryAdvice` làm một handler fail hai lần rồi thành công; so sánh retry attempt count với history entries.
11. **Error flow:** tạo exception trong handler, đọc history của `ErrorMessage.originalMessage` hoặc `MessagingException.failedMessage` nếu có.
12. **Persistence:** dùng message store bền vững thật, ghi rồi restart, kiểm tra history/header serializer và chiều dài sau replay.
13. **Runtime toggle:** nếu bật JMX exporter, stop `MessageHistoryConfigurer`, đổi tracked patterns, start lại; ghi event nào thiếu tracking trong khoảng chuyển đổi.
14. **Observability budget:** xác định header bytes limit của adapter/broker mục tiêu, đo dữ liệu thật và viết policy compact/alert.
15. **So sánh tracing:** bật tracing/Micrometer theo stack đang dùng, chỉ ra thông tin nào Message History có mà span không có và ngược lại.

### Câu hỏi tự kiểm tra

- `MessageHistory` và `MessageStore` khác nhau ở điểm nào?
- `tracked-components` có đảm bảo history tối đa 20 entries không? Vì sao?
- `MessageHistory.read(message)` có thể trả `null` khi nào?
- Vì sao log 5 hop cuối không làm persistent message nhỏ đi?
- Điều gì thay đổi trong Spring Integration 6.3 đối với history append/clone?
- Khi một message được retry ba attempts, history có bắt buộc tăng ba entries không?
- Tại sao `timestamp` gap không đủ để suy ra handler processing time?
- Khi qua broker, làm sao biết history có thật sự được serialize không?
- `MessageHistoryConfigurer` có thể đổi pattern trong lúc đang running không?
- Một message có full history có chứng minh database transaction commit không?

## 22. Checklist trước production

- Có ID/pattern ổn định cho component cần track, chỉ bật phạm vi thực sự hữu ích.
- Không giả định `@EnableMessageHistory` có giới hạn số entries tự động.
- Biết giới hạn về **header bytes thực** của store/broker/adapter.
- Không log nguyên cả history khi không cần; dùng projection và char limits.
- Nếu reset history, làm ở boundary rõ và giữ `eventId`, `traceId`, correlation/sequence headers cần thiết.
- Với 6.3+, custom multi-producer clone history để tránh nhánh ảnh hưởng lẫn nhau.
- Có metrics cho history size, message latency, error/retry và queue/store pressure.
- Chạy kiểm thử loop, retry, fan-out, executor, poller và restart.
- Không dùng history để suy commit, ack, exactly-once hoặc business audit.
- Control Bus/JMX tracking config được giới hạn quyền và ghi audit.
- Xử lý dữ liệu riêng tư: topology/component names không tự xuất ra logs/broker công khai.
- Có runbook khi history gây memory/serialization pressure: giảm pattern, log tail, compact tại boundary và đo lại.

## 23. Nguồn tham khảo chính thức

- [Spring Integration — Message History](https://docs.spring.io/spring-integration/reference/message-history.html): enable, `tracked-components`, JMX configurer và thay đổi append-only từ 6.3.
- [Spring Integration 6.2 — Message History](https://docs.spring.io/spring-integration/reference/6.2/message-history.html): hành vi trước 6.3.
- [Spring Integration API — MessageHistory](https://docs.spring.io/spring-integration/api/org/springframework/integration/history/MessageHistory.html): `read`, `write`, `HEADER_NAME`, `NAME_PROPERTY`, `TYPE_PROPERTY`, `TIMESTAMP_PROPERTY`.
- [Spring Integration API — MessageHistoryConfigurer](https://docs.spring.io/spring-integration/api/org/springframework/integration/history/MessageHistoryConfigurer.html): lifecycle, patterns, điều kiện stop trước khi đổi.
- [Spring Integration API — AbstractIntegrationMessageBuilder](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/AbstractIntegrationMessageBuilder.html): `cloneMessageHistoryIfAny()`.
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics-management.html): integration management, observability và metrics theo version.
- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): persistence và tương tác với headers.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html): DirectChannel, ExecutorChannel, QueueChannel, PubSub.
- [Micrometer Observation Documentation](https://docs.micrometer.io/micrometer/reference/observation.html): observations và tracing/metrics.
