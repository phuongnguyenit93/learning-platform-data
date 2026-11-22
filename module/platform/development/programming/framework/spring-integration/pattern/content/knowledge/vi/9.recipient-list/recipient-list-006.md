# Có cần chờ mọi recipient hay không?

## 1. Trả lời ngắn: phụ thuộc ý nghĩa của việc hoàn tất

Trong **Recipient List** (một Enterprise Integration Pattern), một message được gửi đến **một tập các recipient** do cấu hình hoặc điều kiện quyết định. Nhưng việc gửi tới nhiều recipient **không mặc nhiên có nghĩa phải chờ tất cả xử lý xong**, cũng không có nghĩa framework tự tổng hợp kết quả rồi trả một phản hồi duy nhất.

Ta cần quyết định theo hợp đồng nghiệp vụ:

- **Không cần chờ mọi recipient** nếu mỗi nhánh là tác vụ độc lập, chẳng hạn cập nhật số liệu, phát thông báo không quan trọng hoặc thu thập telemetry; request chính có thể tiếp tục khi đạt **mốc tiếp nhận** được định nghĩa rõ.
- **Cần chờ tất cả kết quả** nếu quyết định tiếp theo đòi đủ những điều kiện độc lập, chẳng hạn xác nhận đơn hàng chỉ sau khi **kiểm tra tồn kho** và **kiểm tra gian lận** đều hoàn tất.
- **Chỉ chờ một tập con**, hoặc áp dụng quy tắc **đạt ngưỡng (quorum)**, khi nghiệp vụ cho phép. Khi đó cũng phải thiết kế cách xử lý các nhánh chưa hoàn thành, kết quả đến muộn và thất bại từng phần.

Từ “chờ” phải được định nghĩa: **chờ cho message được chuyển cho channel**, **chờ handler nhận**, **chờ handler hoàn tất** hay **chờ side effect được commit và ghi nhận bền vững**? Bốn mốc này không giống nhau.

Trong module `SPRING_INTEGRATION_PATTERN`, chúng ta dùng Spring Integration để triển khai Enterprise Integration Patterns, xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Recipient List liên quan chặt với Router, Filter, Transformer, Gateway, Splitter, Aggregator, retry, error channel và correlation, nhất là khi nhiều nhánh cần được kiểm thử và quan sát độc lập.

### Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Phân biệt **fan-out**, **dispatch acknowledgement** và **business completion**.
2. Giải thích vì sao hành vi chờ phụ thuộc vào loại channel và execution model, chứ không chỉ do có Recipient List.
3. Cấu hình Recipient List Router trong Spring Integration Java DSL.
4. Biết khi nào chọn fire-and-forget, đồng bộ, Scatter–Gather hoặc Aggregator.
5. Thiết kế correlation, release strategy, timeout, kết quả thiếu, kết quả đến muộn, retry và idempotency.
6. Kiểm thử hành vi của từng recipient, không nhầm “đã gửi” với “đã xử lý”.

## 2. Recipient List: một message, nhiều đích nhận

### 2.1. Sơ đồ cơ bản

~~~mermaid
flowchart LR
    P[Order Gateway / Publisher] --> I[(orders.received)]
    I --> R{Recipient List Router}
    R -->|Audit| A[(orders.audit)]
    R -->|Notification| N[(orders.notification)]
    R -->|Analytics| M[(orders.analytics)]
    A --> HA[Audit Handler]
    N --> HN[Notification Handler]
    M --> HM[Metrics Handler]
~~~

Ở đây Router xác định **danh sách các channel đích**; các handler được nối với từng channel mới chịu trách nhiệm xử lý. Một message có thể được phát tới tất cả đích hoặc một tập con theo điều kiện. Thứ tự lựa chọn recipient và việc hoàn thành của handler là **hai vấn đề khác nhau**.

Ví dụ một đơn hàng mới tạo:

| Recipient | Công việc | Có bắt buộc hoàn tất trước khi trả lời API tạo đơn? |
|---|---|---|
| `orders.audit` | Ghi dấu sự kiện phục vụ truy nguyên | Tùy yêu cầu tuân thủ và mức bảo đảm ghi. |
| `orders.notification` | Thông báo đến người dùng | Thường không cần chặn kết quả tạo đơn, nếu có cơ chế giao nhận đáng tin cậy. |
| `orders.analytics` | Thống kê theo ngày | Thường không, có thể chấp nhận xử lý chậm. |
| `orders.inventoryCheck` | Kiểm tra khả dụng tồn kho | Có, **nếu** hợp đồng trả lời “đơn đã được xác nhận đủ hàng”. |
| `orders.fraudCheck` | Chấm điểm nguy cơ | Có, **nếu** quyết định chấp thuận phụ thuộc kết quả này. |

Không thể quyết định “mọi recipient phải hoàn tất” chỉ vì danh sách có ba phần tử. Hãy định nghĩa **điều kiện hoàn tất của nghiệp vụ** rồi mới chọn công cụ kỹ thuật.

### 2.2. Recipient List so với Content-Based Router và Publish–Subscribe

| Mẫu | Hành vi chính | Phù hợp khi |
|---|---|---|
| **Content-Based Router** | Chọn channel dựa vào nội dung/header, trong trường hợp phổ biến là một nhánh. | Đơn giá trị lớn → review; đơn thường → xử lý tự động. |
| **Recipient List Router** | Xác định danh sách người nhận, có thể theo điều kiện. | Gửi đến audit và notification; gửi thêm compliance cho đơn quốc tế. |
| **Publish–Subscribe Channel** | Phát đến các subscriber đã đăng ký của một channel. | Nhiều listener độc lập quan tâm cùng một event. |
| **Scatter–Gather** | Phân phối yêu cầu cho nhiều bên rồi tập hợp phản hồi theo chính sách. | Quyết định nghiệp vụ chỉ khi đủ kiểm tra tồn kho/gian lận. |
| **Splitter / Aggregator** | Chia message thành nhiều phần rồi gom các kết quả tương quan. | Một đơn nhiều dòng hàng cần kết quả xử lý toàn bộ các dòng. |

Recipient List Router **không tự là Aggregator**. Nó lựa chọn các đích; việc chờ nhiều kết quả cần một thành phần hoặc cơ chế tổng hợp riêng.

### 2.3. Không phải mọi recipient đều nhận được message trong mọi tình huống

Danh sách cấu hình là **ý định phân phối**, không phải một bảo đảm tất cả đích đã xử lý:

- Recipient có thể bị loại theo điều kiện.
- Channel đích có thể không tồn tại hoặc không có consumer đang chạy.
- Queue có thể đầy; executor có thể từ chối task.
- Một handler đồng bộ có thể ném exception, ảnh hưởng việc dispatch các đích tiếp theo theo cấu hình.
- Một recipient bất đồng bộ có thể đã nhận message vào queue nhưng thất bại sau đó.

Vì vậy, không nên ghi “đã xử lý bởi mọi recipient” chỉ vì Router đã chọn ba channel.

## 3. Bốn mốc hoàn tất dễ bị nhầm

Để xác định **có cần chờ hay không**, hãy phân biệt các mốc:

| Mốc | Ví dụ | Có đủ để công bố nghiệp vụ thành công? |
|---|---|---|
| **1. Recipient selected** | Router tính được `audit, notification, analytics`. | Chưa; chỉ là quyết định đích. |
| **2. Message dispatched/accepted** | Send tới channel thành công hoặc executor đã nhận task. | Chưa chắc; có thể còn chờ xử lý. |
| **3. Handler completed** | Handler chạy xong và trả kết quả. | Tùy; side effect bên ngoài có thể còn thiếu commit/ack. |
| **4. Durable/business outcome committed** | Đã ghi nhận giao dịch hoặc xác nhận broker/database theo contract. | Mạnh hơn, nhưng còn tùy delivery/idempotency và hợp đồng cuối cùng. |

Ví dụ tạo đơn qua API:

~~~text
POST /orders
    |
    +-- Order persisted (đã commit)
    |
    +-- Recipient List
          |-- audit
          |-- email
          |-- analytics
~~~

Nếu hợp đồng API chỉ cần xác nhận **đơn đã được lưu** và các tác vụ còn lại có thể xử lý sau, không nhất thiết chờ email/analytics. Nhưng nếu compliance yêu cầu phải **ghi audit bền vững trước khi xác nhận**, việc chỉ gửi một message audit vào hàng đợi in-memory là chưa đủ. Cần bảo đảm tại tầng lưu trữ phù hợp, ví dụ giao dịch với outbox hoặc một cơ chế ghi nhận bền vững đã thiết kế.

### 3.1. Ba khái niệm thường bị đánh đồng

**Fire-and-forget:** phía gửi không yêu cầu một reply nghiệp vụ từ từng recipient. Điều này **không đảm bảo** gửi không bao giờ chặn: một `DirectChannel` đồng bộ vẫn có thể giữ thread gửi cho tới khi handler chạy xong.

**Async dispatch:** gửi một nhiệm vụ cho executor/broker để xử lý sau. Sender có thể thoát sớm khi công việc được chấp nhận, nhưng **không đảm bảo handler đã thành công** và cũng không tự có durability.

**Wait-for-all:** cần thu đủ kết quả từ tập recipient được kỳ vọng. Cần **correlation**, chính sách đủ kết quả, timeout và cách xử lý lỗi/thiếu. Một Router phát nhiều bản tin **không tự tạo** hợp đồng wait-for-all.

### 3.2. “Chờ tất cả” phải xác định tập tất cả là gì

Recipient List có thể chọn động. Ví dụ:

~~~text
Order nội địa:
  expected recipients = {inventory, fraud}

Order quốc tế:
  expected recipients = {inventory, fraud, compliance}
~~~

Nếu Aggregator luôn chờ **ba** kết quả cho cả hai loại đơn thì đơn nội địa chỉ có hai recipient sẽ không bao giờ hoàn tất. Tập `expectedRecipients` phải được chốt cho **từng request** vào thời điểm fan-out và được truyền tới bước tổng hợp theo một định dạng đáng tin cậy.

## 4. Hành vi chờ phụ thuộc channel và execution model

### 4.1. Hai flow nhìn giống nhau nhưng có semantics khác nhau

~~~mermaid
flowchart TD
    subgraph S[DirectChannel đồng bộ]
        P1[Producer] --> R1[Recipient List]
        R1 --> D1[DirectChannel audit]
        R1 --> D2[DirectChannel notify]
        D1 --> H1[Handler audit]
        D2 --> H2[Handler notify]
    end
    subgraph A[ExecutorChannel bất đồng bộ]
        P2[Producer] --> R2[Recipient List]
        R2 --> E1[ExecutorChannel audit]
        R2 --> E2[ExecutorChannel notify]
        E1 --> Q1[Executor task audit]
        E2 --> Q2[Executor task notify]
    end
~~~

Với các recipient đi qua `DirectChannel` và handler chạy đồng bộ, lời gọi gửi có thể chỉ hoàn tất **sau khi các handler được dispatch đồng bộ đã chạy xong**, nếu không có lỗi ngắt đường đi. Đây là hệ quả của **semantics đồng bộ của channel/handler**, không phải tính năng “chờ kết quả tất cả” của Recipient List.

Với `ExecutorChannel` hoặc queue/poller, send có thể hoàn tất ngay khi nhiệm vụ được **chấp nhận**, trong khi business handler chưa bắt đầu hoặc còn xử lý. Khi có lỗi ở nhánh async, caller ban đầu thường không nhận được exception trực tiếp qua cùng call stack; phải thiết kế error/recovery/notification phù hợp.

### 4.2. Bảng lựa chọn channel

| Loại channel/consumer | Khi gọi gửi thành công | Điều không được suy ra |
|---|---|---|
| `DirectChannel` + handler đồng bộ | Dispatch/handler đồng bộ hoàn tất theo đường gọi, nếu không lỗi. | Không mặc định side effect bên ngoài được commit/durable ở mọi hệ thống. |
| `ExecutorChannel` | Executor có thể đã nhận task theo rejection policy. | Handler đã hoàn tất hoặc thread thực thi giữ MDC/transaction của caller. |
| `QueueChannel` + poller | Message đã enqueue nếu `send` thực sự thành công. | Handler đã poll/commit; in-memory queue bền vững qua restart. |
| Broker/JMS/Kafka/AMQP | Xác nhận theo producer/adapter/broker contract tương ứng. | Consumer đã hoàn tất nghiệp vụ hoặc không thể giao lại trùng. |
| `PublishSubscribeChannel` đồng bộ | Các subscriber đã được dispatch theo chính sách và bối cảnh cụ thể. | Mọi subscriber đều có reply được gom; không có lỗi từng phần. |

**Lưu ý:** Một cơ chế bất đồng bộ có thể vẫn **chặn hoặc từ chối lúc quá tải** nếu task queue đầy, broker chậm, backpressure được áp dụng hoặc rejection policy yêu cầu caller chạy task. “Async” không đồng nghĩa “luôn không chờ”.

### 4.3. Tác động lên latency

Giả sử ba recipient xử lý mất 25 ms, 80 ms và 150 ms:

- Nếu xử lý **nối tiếp, đồng bộ**, thời gian dispatch xấp xỉ tổng các bước: khoảng **255 ms**, chưa tính overhead.
- Nếu các công việc thật sự chạy **song song** và phải chờ đủ, thời gian hoàn tất lý tưởng xấp xỉ bước chậm nhất: **150 ms**, cộng overhead và phụ thuộc tài nguyên.
- Nếu **gửi bất đồng bộ không chờ kết quả**, response có thể đến sớm hơn, nhưng lúc đó mới xác nhận **tiếp nhận**, không thể tự công bố cả ba recipient đã xử lý.

Đây chỉ là phép minh họa để so sánh mô hình, **không phải bảo đảm độ trễ Spring Integration**: thread pool, transaction, network, các nhánh điều kiện và tải thực tế có thể làm thay đổi kết quả.

## 5. Cấu hình Recipient List với Spring Integration Java DSL

### 5.1. Bài toán

Sau khi đơn hàng được ghi nhận, ứng dụng muốn thông báo độc lập cho **audit** và **notification**. Ví dụ ban đầu dùng hai `DirectChannel` để thấy rõ việc fan-out; không cần gom một reply nghiệp vụ.

~~~mermaid
flowchart LR
    P[Producer] --> I[(orders.received)]
    I --> R[Recipient List Router]
    R --> A[(orders.audit)]
    R --> N[(orders.notify)]
    A --> HA[Audit handler]
    N --> HN[Notification handler]
~~~

Ví dụ hướng tới **Java 17+, Spring Boot 3.x và Spring Integration 6.x** với dependency `spring-boot-starter-integration`. Các kiểu có thể đặt cùng package; những top-level type khai báo `public` cần tách file Java phù hợp trong dự án.

### 5.2. Java DSL fan-out cơ bản

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

record OrderCreated(String eventId, String orderId) {}

final class RecipientProbe {
    final AtomicInteger audits = new AtomicInteger();
    final AtomicInteger notifications = new AtomicInteger();

    void audit(OrderCreated event) {
        audits.incrementAndGet();
    }

    void notifyUser(OrderCreated event) {
        notifications.incrementAndGet();
    }
}

@Configuration
@EnableIntegration
class RecipientListConfiguration {

    @Bean(name = "orders.received")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.audit")
    MessageChannel auditChannel() {
        return new DirectChannel();
    }

    @Bean(name = "orders.notify")
    MessageChannel notifyChannel() {
        return new DirectChannel();
    }

    @Bean
    RecipientProbe recipientProbe() {
        return new RecipientProbe();
    }

    @Bean
    IntegrationFlow distributeOrder() {
        return IntegrationFlow.from("orders.received")
                .routeToRecipients(routes -> routes
                        .recipient("orders.audit")
                        .recipient("orders.notify"))
                .get();
    }

    @Bean
    IntegrationFlow auditFlow(RecipientProbe probe) {
        return IntegrationFlow.from("orders.audit")
                .handle(OrderCreated.class, (event, headers) -> {
                    probe.audit(event);
                    return null; // Handler một chiều; không phát reply.
                })
                .get();
    }

    @Bean
    IntegrationFlow notificationFlow(RecipientProbe probe) {
        return IntegrationFlow.from("orders.notify")
                .handle(OrderCreated.class, (event, headers) -> {
                    probe.notifyUser(event);
                    return null;
                })
                .get();
    }
}
~~~

**Đọc ví dụ đúng cách:**

- `.routeToRecipients(...)` định nghĩa một **Recipient List Router**, ở đây có hai recipient tĩnh.
- Hai bean `DirectChannel` là channel đích; hai `IntegrationFlow` ở cuối đăng ký consumer riêng.
- `RecipientProbe` chỉ ghi counter để quan sát trong bài học. Một ứng dụng thật phải thay bằng audit service/notification service và thiết kế side effect, retry, tracing, security.
- Handler dùng `return null` để kết thúc **một chiều**; không cố trả hai reply khác nhau vào cùng Gateway.
- Vì cả hai nhánh đang dùng `DirectChannel`, demo có thể quan sát cả hai handler đã chạy khi `send` thành công và trở về trong điều kiện không có lỗi; **không** suy rộng điều này cho nhánh bất đồng bộ.

### 5.3. Gửi message từ producer

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

boolean accepted = input.send(
        MessageBuilder.withPayload(
                new OrderCreated("EVT-1001", "ORD-1001"))
                .setHeader("traceId", "trace-ord-1001")
                .build(), 1_000);

// Trong cấu hình DirectChannel của demo,
// kiểm tra cả hai counter trong test để xác minh fan-out.
~~~

`accepted` là kết quả **lệnh gửi vào flow** theo semantics của channel và các endpoint liên quan. Không biến boolean này thành câu trả lời “người dùng đã nhận email và audit đã ghi bền vững”; hai kết luận đó cần bằng chứng riêng từ recipient tương ứng.

### 5.4. Recipient động và có điều kiện

Ngoài danh sách tĩnh, Recipient List có thể chọn **một tập con** theo điều kiện. Ví dụ:

~~~text
OrderCreated
  -> orders.audit            (mọi đơn)
  -> orders.notify           (nếu khách bật thông báo)
  -> orders.exportCompliance (nếu đơn quốc tế)
~~~

Điều kiện cần được tính từ **payload/headers đã được xác thực**, không tin flag do bên ngoài tùy ý đặt cho các yêu cầu liên quan bảo mật. Khi chọn đích có điều kiện, hãy lưu rõ **tập recipient kỳ vọng của từng event** nếu sau đó cần tổng hợp kết quả; không dùng số recipient cố định cho mọi request.

Với Java DSL, có thể dùng cấu hình recipient có điều kiện tương ứng với phiên bản Spring Integration đang sử dụng. Vì cú pháp biểu thức và overload khác nhau giữa DSL/phiên bản, ví dụ `routeToRecipients` ở trên giữ nguyên danh sách tĩnh để trình bày rõ cơ chế cốt lõi; phần điều kiện nên có test riêng, không giả định một expression chưa kiểm chứng luôn hoạt động.

## 6. Không chờ mọi recipient: fire-and-forget có kiểm soát

### 6.1. Khi nào phù hợp?

Các công việc như gửi email, cập nhật dashboard và analytics thường **không quyết định** tính hợp lệ của giao dịch chính. Sau khi lưu đơn hàng, ứng dụng có thể publish một event và trả lời mà không đợi tất cả người nhận hoàn tất.

~~~mermaid
sequenceDiagram
    participant API
    participant DB
    participant OUT as Outbox / Broker
    participant A as Audit Consumer
    participant N as Notification Consumer
    API->>DB: Commit đơn hàng
    API->>OUT: Ghi/phát event theo delivery contract
    OUT-->>API: Xác nhận tiếp nhận theo contract
    API-->>API: Trả lời đã ghi nhận
    OUT->>A: Delivery (có thể trễ)
    OUT->>N: Delivery (có thể trễ)
~~~

Sơ đồ này minh họa **mục tiêu thiết kế**, không phải bảo đảm rằng chỉ dùng `RecipientListRouter` thì tự có outbox, broker hoặc commit nguyên tử. Với nhu cầu không mất sự kiện khi ứng dụng restart hay giữa DB commit và publish, cân nhắc **transactional outbox** hoặc cơ chế tương đương được xác minh về delivery semantics.

### 6.2. Chuyển một recipient sang xử lý async

Ví dụ trong mục 5 đang dùng `DirectChannel` cho `orders.notify`. Nếu muốn chuyển việc sang executor, có thể **thay** định nghĩa bean channel đó bằng:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
ThreadPoolTaskExecutor notificationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(50);
    executor.setThreadNamePrefix("notify-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
    executor.initialize();
    return executor;
}

@Bean(name = "orders.notify")
MessageChannel asyncNotificationChannel(
        ThreadPoolTaskExecutor notificationExecutor) {
    return new ExecutorChannel(notificationExecutor);
}
~~~

Đây là **đoạn cấu hình thay thế**, không được để cả bean `orders.notify` đồng bộ và bất đồng bộ cùng tên trong một context. Với executor, `send` thường kết thúc sau khi task được nhận, không cần đợi notification handler xử lý xong; khi executor bão hòa, `AbortPolicy` có thể từ chối và gây exception theo hạ tầng Spring. `ExecutorChannel` **không** phải message store bền vững: restart có thể làm mất task còn trong bộ nhớ.

### 6.3. Fire-and-forget không có nghĩa bỏ qua lỗi

Nếu email thất bại sau khi API trả lời, hệ thống phải có **cách quan sát và phục hồi**:

- Gắn event/business ID ổn định để có thể retry mà không gửi lặp ngoài ý muốn.
- Theo dõi kết quả enqueue, backlog, retry count, timeout và xử lý lỗi riêng từng recipient.
- Xác định có cần dead-letter/quarantine hay không.
- Không công bố “tất cả thông báo đã gửi” khi chỉ mới phát event.
- Có giới hạn queue/executor, backpressure và hành vi khi recipient chậm.

Fire-and-forget chỉ bỏ **ràng buộc chờ trong đường phản hồi chính**, không bỏ trách nhiệm vận hành của các nhánh.

## 7. Cần chờ mọi recipient: Scatter–Gather và Aggregator

### 7.1. Một ví dụ cần đủ kết quả

Giả sử API `confirmOrder` chỉ được trả `CONFIRMED` sau khi:

- Hệ thống **inventory** xác minh đủ hàng.
- Hệ thống **fraud** xác minh đơn không bị từ chối.

Nếu chỉ có một kết quả, hệ thống chưa thể quyết định xác nhận đơn. Khi đó ta cần **Scatter–Gather**: *scatter* gửi yêu cầu đến các recipient, *gather* gom câu trả lời của chính request đó. Recipient List có thể tham gia giai đoạn **scatter**, nhưng **chỉ Recipient List Router là chưa đủ**.

~~~mermaid
flowchart TD
    G[Gateway confirmOrder] --> S[Scatter đến 2 recipients]
    S --> F[Fraud Check]
    S --> I[Inventory Check]
    F --> FR[FraudResult + correlation]
    I --> IR[InventoryResult + correlation]
    FR --> A[Aggregator / Gatherer]
    IR --> A
    A --> D{Đã đủ theo release policy?}
    D -->|Chưa| W[Chờ thêm / timeout]
    D -->|Đủ| O[CombinedDecision]
    O --> G
~~~

Trong Spring Integration có **Scatter–Gather** và các thành phần **Aggregator** hỗ trợ mô hình này. Tùy loại scatterer (Recipient List, Publish–Subscribe hoặc cấu hình khác), cần xem xét cách hình thành reply, correlation và sequence. Không chỉ gọi `routeToRecipients(...)` rồi mặc định có một list các phản hồi.

### 7.2. Bốn thành phần phải định nghĩa

1. **Tập recipient cần chờ**: `{inventory, fraud}` cho request này. Nếu chọn có điều kiện, tập này thay đổi theo message và phải được chốt tại fan-out.
2. **Correlation key**: ví dụ `validationRequestId` duy nhất cho một lần kiểm tra. Nếu dùng đơn thuần `orderId` cho nhiều lượt kiểm tra đồng thời, có thể trộn phản hồi của các attempt khác nhau.
3. **Release strategy**: khi nào group được xem là đủ? Đủ một kết quả **hợp lệ từ mỗi recipient yêu cầu**, hay đạt quorum, hay một kết quả `FAIL` là đủ để từ chối sớm?
4. **Group expiration và reply contract**: hết hạn thì trả thất bại, trả partial, hay đưa vào recovery? Message đến muộn xử lý thế nào?

Một request ví dụ:

~~~text
validationRequestId = check-ORD-1001-v3
expectedRecipients  = {inventory, fraud}
deadline            = 2026-11-21T10:00:05+07:00

inventory -> PASS, validationRequestId=check-ORD-1001-v3
fraud     -> PASS, validationRequestId=check-ORD-1001-v3

Aggregator -> CONFIRMED
~~~

Thời điểm trong ví dụ là **dữ liệu minh họa**, không phải deadline mặc định của Spring Integration. Giá trị `validationRequestId` cần được propagate qua adapter và được kiểm tra ở gatherer; không giả định message ID sẽ giữ nguyên qua mọi hệ thống.

### 7.3. Correlation khác message ID

| Loại ID | Công dụng | Rủi ro khi dùng sai |
|---|---|---|
| `orderId` | Định danh đơn hàng. | Hai đợt xác minh cùng đơn dễ bị gộp chung. |
| `messageId` | Một message cụ thể. | Mỗi recipient/reply có thể tạo message mới với ID khác. |
| `validationRequestId` | Nhóm một lần kiểm tra cần gom. | Phải tránh trùng giữa các lần kiểm tra và bảo toàn qua transport. |
| `traceId` | Truy nguyên đường đi xuyên các bước. | Dùng trace ID làm release key có thể gộp nhầm nhiều nhóm trong cùng trace. |
| `recipientId` | Xác định kết quả đến từ nhánh nào. | Nếu chỉ đếm số message, duplicate của một nhánh có thể bị tính là đủ hai kết quả. |

Để kết quả chính xác, release strategy thường cần **đếm số recipient duy nhất đã phản hồi**, không chỉ đếm số message. Ví dụ nếu inventory gửi hai reply trùng còn fraud chưa gửi, tổng số message là 2 nhưng **chưa đủ** hai recipient.

### 7.4. Minh họa chính sách tổng hợp bằng Java thuần

Đoạn sau mô tả **logic nghiệp vụ sau khi Aggregator đã gom đủ** một tập kết quả. Nó không thay thế cấu hình AggregatingMessageHandler, MessageGroupStore hoặc Scatter–Gather của Spring Integration:

~~~java
import java.util.Map;
import java.util.Set;

enum CheckStatus { PASS, FAIL, TIMEOUT }

record CheckResult(
        String validationRequestId,
        String recipientId,
        CheckStatus status) {}

record CombinedDecision(String requestId, boolean confirmed) {}

final class DecisionPolicy {
    private static final Set<String> REQUIRED =
            Set.of("inventory", "fraud");

    CombinedDecision combine(
            String requestId,
            Map<String, CheckResult> latestByRecipient) {

        if (!latestByRecipient.keySet().containsAll(REQUIRED)) {
            throw new IllegalStateException(
                    "Required recipients have not all responded");
        }

        boolean allPassed = REQUIRED.stream()
                .map(latestByRecipient::get)
                .allMatch(result ->
                        requestId.equals(result.validationRequestId())
                                && result.status() == CheckStatus.PASS);

        return new CombinedDecision(requestId, allPassed);
    }
}
~~~

**Ý nghĩa:**

- Dùng `Map<recipientId, CheckResult>` để biết **mỗi recipient có kết quả**, thay vì chỉ nhìn số phần tử.
- `combine` chỉ nhận input đã được nhóm theo đúng request. Việc **gom message, chờ, khóa group và expiry** là trách nhiệm cấu hình Aggregator/Scatter–Gather ở tầng integration.
- Trong hệ thống thật, nên xác minh tập key **không chứa kết quả giả mạo**, mỗi recipient có danh tính và trạng thái đáng tin cậy, kết quả duplicate được xử lý theo policy rõ ràng.
- Quyết định `confirmed=false` chưa đủ mô tả lý do. Production thường dùng status và error code như `FRAUD_REJECTED`, `OUT_OF_STOCK`, `CHECK_TIMEOUT` để phân biệt lỗi nghiệp vụ với lỗi hạ tầng.

### 7.5. Có cần thực sự đợi *mọi* recipient nếu một nhánh đã từ chối?

Không phải lúc nào cũng cần. Nếu một kết quả `FAIL` chắc chắn khiến giao dịch bị từ chối, có thể dùng **fail-fast**: đưa ra quyết định từ chối sớm mà không chờ các kiểm tra còn lại, **nếu** các nhánh chưa hoàn tất có thể bị hủy/tiếp tục an toàn và nghiệp vụ cho phép.

Ví dụ:

| Inventory | Fraud | Quyết định | Có cần chờ tiếp không? |
|---|---|---|---|
| PASS | PASS | CONFIRMED | Đủ hai kết quả, hoàn tất. |
| FAIL | Chưa nhận | REJECTED_OUT_OF_STOCK | Có thể fail-fast nếu nghiệp vụ cho phép. |
| Chưa nhận | FAIL | REJECTED_FRAUD | Có thể fail-fast, nhưng vẫn cần kiểm soát tác vụ đang chạy. |
| PASS | Chưa nhận | Chưa đủ | Phải chờ fraud hoặc timeout. |
| TIMEOUT | PASS | Chưa thể CONFIRMED | Dùng timeout/recovery contract. |

**Fail-fast không tự hủy công việc đã gửi.** Các recipient khác có thể vẫn chạy, tạo log và side effect; kết quả đến muộn cần được nhận diện và bỏ qua/ghi nhận theo chính sách. Nếu kiểm tra có thao tác ngoài không thể hoàn tác, “trả lời sớm” không đồng nghĩa được phép bỏ qua cleanup.

### 7.6. Timeout ở Gateway và timeout ở Aggregator

Nên có **ngân sách thời gian** cho toàn request:

~~~text
Client HTTP timeout
   └─ Gateway reply timeout
        └─ Scatter–Gather / Aggregator deadline
             ├─ Inventory downstream timeout
             └─ Fraud downstream timeout
~~~

Nếu Gateway hết thời gian chờ **trước khi** Aggregator hết hạn, caller có thể đã nhận timeout trong khi group vẫn tồn tại và tiếp tục xử lý. Nếu Aggregator phát kết quả sau khi caller đã rời đi, cần chính sách xử lý **late reply**, cleanup và cập nhật trạng thái bằng kênh bất đồng bộ nếu phù hợp.

Thời hạn nên phối hợp có dư địa cho xử lý lỗi và phản hồi, nhưng không được coi một con số timeout đơn lẻ là bảo đảm. Tài nguyên của **message group store** và các group chờ phải được giám sát.

## 8. Kết quả một phần, duplicate và nhánh lỗi

### 8.1. Các tình huống khi fan-out

~~~mermaid
flowchart TD
    S[Recipient List / Scatter] --> A[Recipient A]
    S --> B[Recipient B]
    A --> AR{Kết quả A}
    B --> BR{Kết quả B}
    AR -->|Success| G[Gatherer]
    AR -->|Failure/timeout| E[Error/recovery policy]
    BR -->|Success| G
    BR -->|Failure/timeout| E
    E --> G
    G --> D{Release policy}
    D -->|Đủ| O[Combined outcome]
    D -->|Thiếu quá hạn| T[Timeout / partial / recovery]
~~~

Không phải lỗi nào cũng làm recipient trả một `CheckResult`. Một outbound gateway có thể throw exception, broker consumer có thể bị redelivery, hoặc một thread bị dừng. **Nếu Aggregator chỉ biết đếm kết quả thành công**, một nhánh lỗi có thể khiến group chờ tới timeout. Cần lựa chọn rõ:

- **Đưa lỗi thành kết quả có cấu trúc**, ví dụ `CheckResult(recipient=fraud, status=TIMEOUT)`, khi hợp đồng phù hợp.
- **Chờ retry có giới hạn**, rồi chuyển sang `FAILED`/recovery nếu vẫn không đủ.
- **Expire group** với policy rõ cho kết quả thiếu, không để group tồn tại mãi.
- **Cancel** các recipient còn lại nếu thực sự hỗ trợ cancellation và không làm sai side effect.

### 8.2. Duplicate làm sai phép đếm

Một recipient có thể phát nhiều lần vì retry hoặc broker redelivery:

~~~text
request=REQ-7 inventory -> PASS (attempt 1)
request=REQ-7 inventory -> PASS (attempt 2, duplicate)
request=REQ-7 fraud     -> chưa có
~~~

Nếu release strategy dùng “đủ 2 message”, group có thể release sai. Hãy kiểm tra **recipient ID duy nhất**, **request ID**, event/result ID, và chính sách thay thế kết quả khi cùng recipient gửi lại. Không tự nhận mọi message lặp là lỗi: có thể là cập nhật phiên bản mới, nhưng contract phải nói rõ có được cập nhật hay không.

### 8.3. Partial success và không có giao dịch chung

Giả sử audit đã ghi thành công, notification thất bại. Recipient List không tự thực hiện **distributed transaction** để rollback audit. Ngay cả khi các nhánh chạy đồng bộ, việc một handler ném exception không bảo đảm side effect của handler khác được hoàn tác.

Với tích hợp đa dịch vụ, ưu tiên các cơ chế phù hợp: **idempotency**, retry có giới hạn, outbox, trạng thái nghiệp vụ riêng, hoặc **compensation/Saga** nếu phải xử lý những tác động phân tán. Không dùng `@Transactional` của một ứng dụng rồi mặc nhiên coi email, Kafka và HTTP downstream cùng tham gia một ACID transaction.

### 8.4. Nhánh lỗi có cần chờ không?

Nếu mục tiêu là ghi audit hoặc telemetry độc lập, có thể cho phép notification thất bại mà vẫn công bố đơn đã được lưu, **nhưng phải ghi trạng thái lỗi và cơ chế retry**. Nếu mục tiêu là quyết định phê duyệt, một nhánh bắt buộc thất bại thường không được xem là “đã đủ điều kiện”.

| Phần việc | Có cần chờ thành công? | Khi thất bại |
|---|---|---|
| Lưu đơn hàng | Có nếu API trả “đã lưu”. | Trả lỗi hoặc trạng thái không chắc chắn theo transaction contract. |
| Phát sự kiện ra outbox | Cần đảm bảo tương thích với cam kết xử lý sau. | Retry/recovery, không tuyên bố event đã phát nếu chưa có bằng chứng. |
| Email chào mừng | Thường không chờ. | Retry/DLQ, báo lỗi riêng, không rollback đơn chỉ vì email. |
| Kiểm tra fraud bắt buộc | Có trước khi “confirmed”. | Fail/timeout/review theo chính sách. |
| Kiểm tra inventory bắt buộc | Có trước khi “confirmed”. | Out of stock/timeout/recovery. |
| Analytics | Thường không. | Theo dõi lag và mất dữ liệu theo SLO tương ứng. |

## 9. Gateway, error channel và reply: ba đường đi khác nhau

### 9.1. Recipient List không tạo một reply hợp lệ tự động

Khi request–reply Gateway đưa message vào Router phân phát nhiều đích, nếu mỗi handler đều trả một reply về cùng `replyChannel` mà không có Gatherer phù hợp, ta có thể gặp **nhiều reply cạnh tranh**, reply không được định nghĩa hoặc timeout tùy flow/transport. Đừng lấy reply đầu tiên rồi coi là kết quả của tất cả các nhánh.

Để dùng Gateway đồng bộ với nhiều recipient có kết quả, nên:

1. Xác định mô hình **Scatter–Gather** và tập recipient kỳ vọng.
2. Propagate correlation/reply metadata phù hợp.
3. Định nghĩa **một** combined result hoặc business error cuối cùng.
4. Cấu hình timeout, xử lý kết quả thiếu và late reply.

Nếu chỉ muốn broadcast sự kiện một chiều, tránh buộc một Gateway đồng bộ chờ các recipient không có contract trả reply.

### 9.2. Exception đồng bộ khác lỗi bất đồng bộ

Với Recipient List dispatch qua `DirectChannel`, exception từ handler có thể truyền theo call stack của sender và ảnh hưởng việc chuyển tới những đích còn lại. **Không được mặc định** cả danh sách đã được gọi, cũng không được mặc định những side effect trước khi exception đã được rollback.

Khi dispatch sang executor, poller hoặc broker, lỗi của consumer có thể xảy ra **sau khi sender đã thoát**, và có thể xuất hiện dưới dạng `ErrorMessage`/`errorChannel` trong những bối cảnh đã cấu hình. Cơ chế gửi không thành công do queue đầy cũng khác với handler đã nhận message rồi thất bại.

Việc một recipient thất bại có làm ngừng gửi các recipient khác hay được bỏ qua tùy thuộc **loại router/channel và chính sách send failure** đang dùng. Phải chủ động kiểm tra và test cấu hình, không suy từ tên Recipient List rằng nó luôn tiếp tục hoặc luôn dừng.

### 9.3. Retry phải có phạm vi

Một lỗi ở notification không nhất thiết yêu cầu **gửi lại toàn bộ Recipient List**. Nếu retry cả fan-out, audit và analytics có thể chạy lại, gây duplicate. Thường tốt hơn là đặt retry/recovery tại **nhánh thất bại** và sử dụng idempotency key riêng cho từng recipient:

~~~text
deliveryKey = eventId + ":" + recipientId

EVT-1001:audit        -> completed
EVT-1001:notification -> retrying
EVT-1001:analytics    -> completed
~~~

Đây là **quy ước ứng dụng**, không phải header tự sinh sẵn. Nó giúp phân biệt ba nhánh được giao từ cùng event khi thực hiện retry/redelivery. Trong trường hợp nhiều lần phát cùng event là chủ ý, hãy dùng thêm version/operation ID theo hợp đồng.

## 10. Quan sát thời gian và trạng thái từng recipient

### 10.1. Theo dõi quyết định gửi và kết quả

Một bộ sự kiện log có cấu trúc có thể gồm:

~~~text
event=RECIPIENTS_SELECTED requestId=REQ-8
  expected={inventory,fraud}

event=RECIPIENT_ACCEPTED requestId=REQ-8 recipient=inventory

event=RECIPIENT_COMPLETED requestId=REQ-8
  recipient=inventory outcome=PASS durationMs=42

event=RECIPIENT_FAILED requestId=REQ-8
  recipient=fraud outcome=TIMEOUT attempt=2

event=GROUP_EXPIRED requestId=REQ-8
  expected=2 receivedUnique=1 missing={fraud}
~~~

Đây là **schema do ứng dụng đề xuất**, không phải output mặc định của Spring Integration. Đặc biệt, `RECIPIENT_ACCEPTED` **không được đặt tên `RECIPIENT_COMPLETED`** nếu chỉ mới enqueue task.

Nên giữ bốn loại định danh tách biệt:

- `businessId` như `orderId` để tìm nghiệp vụ.
- `eventId` / `messageId` để tìm sự kiện và bản tin kỹ thuật.
- `correlationId` / `validationRequestId` để gom đúng những kết quả liên quan.
- `traceId` để theo dõi hành trình qua thread/process và dịch vụ.

### 10.2. Metrics phù hợp

| Metric | Câu hỏi trả lời |
|---|---|
| Số recipient được chọn theo loại | Fan-out trung bình bao nhiêu nhánh? |
| Accepted/rejected send count | Nhánh nào không tiếp nhận message? |
| Processed/failed count theo recipient | Nhánh nào hoàn thành hay thất bại? |
| Processing latency theo recipient | Đích nào là bottleneck khi phải chờ đủ? |
| Queue depth / oldest-message age | Nhánh bất đồng bộ có backlog tăng không? |
| Pending group count | Có bao nhiêu group Aggregator đang chờ? |
| Group completion / expiry rate | Tỷ lệ đủ kết quả và timeout? |
| Retry/duplicate/late-reply count | Delivery/recovery có ổn định không? |

Không dùng `orderId` hay `traceId` làm nhãn metric có cardinality lớn. Log/tracing với retention và quyền truy cập phù hợp sẽ xử lý các ID cụ thể tốt hơn.

### 10.3. Message History không thay thế kết quả nghiệp vụ

`Message History` có thể cho biết các component đã được theo dõi trong Spring Integration, nhưng không mặc nhiên ghi **recipient nào đã commit một giao dịch**, không tự gom distributed traces hoặc xác nhận mọi reply. Trong flow có `ExecutorChannel`, thread-local/MDC của thread sender cũng không tự lan truyền; trace context cần propagation phù hợp.

Ở mô hình fan-out/gather, nên ghi dấu ở cả ba nơi:

1. **Trước scatter:** expected recipient set, correlation key, deadline.
2. **Tại mỗi recipient:** started, accepted/processed/failed, attempt, latency.
3. **Tại gatherer:** số kết quả duy nhất, release reason, outcome, late reply, expiry.

Nhờ đó một request timeout có thể được chẩn đoán: đã chọn sai recipients, gửi tới queue đầy, handler không chạy, hay aggregator chờ nhầm group.

## 11. Kiểm thử: xác nhận chính xác mình đang chờ điều gì

### 11.1. Integration test cho Recipient List đồng bộ

Với cấu hình `RecipientListConfiguration` ở mục 5, kiểm thử JUnit 5 và Spring Test có thể xác nhận hai recipient đều được gọi:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(RecipientListConfiguration.class)
class RecipientListFlowTest {

    @Autowired
    @Qualifier("orders.received")
    private MessageChannel input;

    @Autowired
    private RecipientProbe probe;

    @Test
    void twoDirectRecipientsAreHandledWhenSendReturns() {
        int beforeAudit = probe.audits.get();
        int beforeNotify = probe.notifications.get();

        boolean sent = input.send(
                MessageBuilder.withPayload(
                        new OrderCreated("EVT-1", "ORD-1"))
                        .build(), 1_000);

        assertTrue(sent);
        assertEquals(beforeAudit + 1, probe.audits.get());
        assertEquals(beforeNotify + 1, probe.notifications.get());
    }
}
~~~

**Test này chứng minh được gì?** Trong **cấu hình DirectChannel đồng bộ của ví dụ** và khi không xảy ra lỗi, mỗi handler đã tăng counter trước khi lời gọi gửi hoàn tất. Nó không chứng minh notification thật đã tới người dùng, audit đã ghi vào database bền vững, hoặc nhánh executor/broker chạy xong trước `send`.

Nếu muốn xác minh **đúng channel đã nhận**, có thể sử dụng interceptor hoặc test-only handler trong cấu hình test. Đừng lấy số dòng log làm bằng chứng duy nhất, đặc biệt khi có executor và xử lý song song.

### 11.2. Unit test cho chính sách wait-for-all

Dùng `DecisionPolicy` ở mục 7 để phân biệt “đủ số message” và “đủ recipient”:

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DecisionPolicyTest {
    private final DecisionPolicy policy = new DecisionPolicy();

    @Test
    void confirmsOnlyWhenBothRecipientsPassed() {
        CombinedDecision result = policy.combine(
                "REQ-1",
                Map.of(
                        "inventory",
                        new CheckResult("REQ-1", "inventory",
                                CheckStatus.PASS),
                        "fraud",
                        new CheckResult("REQ-1", "fraud",
                                CheckStatus.PASS)));

        assertTrue(result.confirmed());
    }

    @Test
    void doesNotConfirmIfFraudRejected() {
        CombinedDecision result = policy.combine(
                "REQ-2",
                Map.of(
                        "inventory",
                        new CheckResult("REQ-2", "inventory",
                                CheckStatus.PASS),
                        "fraud",
                        new CheckResult("REQ-2", "fraud",
                                CheckStatus.FAIL)));

        assertFalse(result.confirmed());
    }

    @Test
    void missingFraudResultCannotBeTreatedAsComplete() {
        assertThrows(IllegalStateException.class, () ->
                policy.combine(
                        "REQ-3",
                        Map.of("inventory",
                                new CheckResult("REQ-3", "inventory",
                                        CheckStatus.PASS))));
    }
}
~~~

Các test trên **chưa kiểm thử hạ tầng Aggregator**. Chúng chỉ kiểm tra quyết định của ứng dụng **sau khi đã có tập kết quả**. Để kiểm thử end-to-end Scatter–Gather, phải thêm flow xử lý phản hồi, group store, timeout, release strategy và test những tình huống reply thiếu, duplicate, đến trễ.

### 11.3. Test bất đồng bộ không được dựa vào thời gian cố định

Khi thay một recipient bằng `ExecutorChannel`, **không** assert `notificationCount == 1` ngay sau `send` như một quy tắc tổng quát. Dùng `CountDownLatch` hoặc cơ chế await có timeout để biết handler thực sự hoàn tất.

Ví dụ kế hoạch test:

1. Gửi một message có `eventId` xác định.
2. Dùng handler test ghi nhận sự kiện `received` và `completed`, có latch điều khiển.
3. Giữ handler chưa hoàn tất; kiểm tra sender nhận kết quả **chấp nhận task** theo contract mà không nhầm với kết quả nghiệp vụ.
4. Thả latch; chờ `completed` bằng timeout hữu hạn.
5. Cho executor bão hòa và xác minh rejection policy/exception hoặc backpressure được báo đúng.
6. Đảm bảo executor được shutdown trong `finally` hoặc theo lifecycle của Spring context.

Không bắt một tác vụ ngoài đã commit phải “biến mất” khi test hủy `Future`; cancellation Java không bảo đảm rollback side effect.

### 11.4. Ma trận kiểm thử cho wait-for-all

| Kịch bản | Điều cần xác nhận |
|---|---|
| Hai recipient đều phản hồi PASS | Aggregator release một combined result thành công. |
| Một PASS, một FAIL | Kết quả từ chối hoặc fail-fast theo policy, không CONFIRMED. |
| Một PASS, một không phản hồi | Hết deadline và trả timeout/partial/recovery rõ ràng. |
| Một recipient gửi hai reply duplicate | Không tính thành hai recipient đã hoàn tất. |
| Reply đến sau group expiry | Late reply được bỏ qua/xử lý theo policy, không tái xác nhận sai. |
| Các request cùng `orderId` chạy đồng thời | Correlation ID khác nhau, không trộn nhóm. |
| Recipient List chọn một subset | Expected count/set tính theo subset **thực sự được chọn**. |
| Một handler sync throw exception | Không giả định các recipient còn lại đã được gọi; kiểm tra partial side effects. |
| Executor/broker tiếp nhận rồi consumer lỗi | Không xem accepted send là business success. |
| Gateway reply timeout trước group expiry | Không mất kiểm soát group và late reply sau khi caller đã timeout. |
| Message qua adapter mất correlation header | Group không được ghép nhầm; có lỗi/recovery rõ. |
| Retry toàn fan-out | Kiểm tra recipient đã thành công có bị duplicate hay không. |

## 12. Các lỗi thiết kế thường gặp

| Hiểu nhầm | Hậu quả | Cách tiếp cận đúng |
|---|---|---|
| “Recipient List tự chờ tất cả reply.” | Gateway thiếu phản hồi hoặc trả kết quả không xác định. | Dùng Scatter–Gather/Aggregator với correlation, release và timeout. |
| “Fire-and-forget nghĩa là `send` luôn trở về tức thì.” | `DirectChannel` vẫn có thể chặn do handler đồng bộ. | Xem channel và execution model, chọn async nếu thực sự cần. |
| “Async nghĩa là bền vững.” | Task trong executor/queue mất khi restart. | Chọn broker/outbox/store phù hợp với delivery guarantee. |
| “Đã route tới ba đích nghĩa là ba nhánh thành công.” | Không nhận diện queue full, dispatch failure và lỗi xử lý. | Theo dõi accepted/started/completed/failed riêng từng recipient. |
| “Đủ ba message là đủ ba recipient.” | Duplicate của một recipient làm release sai. | Dùng recipient ID duy nhất và kiểm soát duplicate. |
| “Mọi request luôn có cùng số recipient.” | Conditional list làm Aggregator chờ sai số lượng. | Chốt expected recipient set cho từng request. |
| “Một nhánh lỗi thì các nhánh trước đã rollback.” | Side effect từng phần, gửi trùng khi retry. | Idempotency, compensation và recovery theo từng nhánh. |
| “Timeout Gateway là group đã bị xóa.” | Message group tồn đọng, late replies không được xử lý. | Thiết kế group expiration/cleanup độc lập. |
| “Retry toàn Recipient List khi email lỗi.” | Audit và analytics chạy lại dù đã thành công. | Retry tại recipient thất bại, dùng delivery/idempotency key. |
| “`traceId` thay được correlation key.” | Nhiều nhóm trong một trace bị ghép nhầm. | Dùng request/group ID riêng cho Aggregator. |
| “Không có reply thì có thể khẳng định recipient không nhận.” | Consumer có thể đang xử lý hoặc reply bị mất. | Quan sát dispatch, processing, timeout và transport. |
| “Cần đợi mọi telemetry trước khi trả API.” | Latency tăng, biến nhánh phụ thành dependency cứng. | Xác định critical path và SLO thật sự. |

## 13. Bài tập thực hành

1. **Fan-out cơ bản:** dùng `routeToRecipients` gửi `OrderCreated` tới audit và notification. Viết test rằng cả hai handler đồng bộ nhận message.
2. **Async một nhánh:** thay `orders.notify` bằng `ExecutorChannel` và đo chênh lệch giữa thời điểm `send` trả về và thời điểm notification hoàn tất. Thêm test executor bão hòa.
3. **Recipient List có điều kiện:** với đơn quốc tế, thêm `compliance`; đơn nội địa chỉ gửi audit/notification. Ghi `expectedRecipients` để thấy vì sao không thể hardcode số recipient.
4. **Scatter–Gather:** tạo hai recipient `inventory` và `fraud`, dùng một request ID để gom reply. Chỉ trả `CONFIRMED` khi cả hai PASS.
5. **Duplicate:** cho inventory gửi hai message thành công, fraud chưa gửi. Chứng minh Aggregator không được release nếu chưa có kết quả fraud.
6. **Timeout:** mô phỏng fraud không phản hồi, thiết kế deadline, group expiry, phản hồi Gateway và đường xử lý late reply.
7. **Fail-fast:** cho inventory FAIL trước fraud. So sánh chính sách chờ đủ với từ chối sớm; giải thích tác vụ fraud đang chạy phải được xử lý như thế nào.
8. **Retry và idempotency:** làm notification thất bại sau khi audit thành công. So sánh retry cả fan-out với retry riêng notification; sử dụng `eventId:recipientId` làm khóa chống duplicate.
9. **Bảo toàn correlation:** gửi kết quả qua một adapter và tái tạo message; kiểm tra correlation/request ID còn được mapper khôi phục, không dựa vào `replyChannel` object của JVM khác.
10. **Quan sát:** thêm log `RECIPIENT_ACCEPTED`, `RECIPIENT_COMPLETED` và `GROUP_EXPIRED`; tạo lỗi ngẫu nhiên ở một nhánh, xác định mốc hệ thống thực sự đạt được.

### Câu hỏi tự kiểm tra

**Câu 1:** Recipient List Router gửi một message đến ba `DirectChannel` đồng bộ. `send` hoàn tất thì đã đủ chứng minh cả ba side effect bên ngoài được commit chưa? **Chưa.** Chỉ có thể suy luận về quá trình dispatch/handler đồng bộ theo cấu hình; commit/durability cần bằng chứng riêng.

**Câu 2:** Nếu một recipient dùng `ExecutorChannel`, sender có phải đợi handler hoàn tất không? **Không mặc nhiên.** Có thể chỉ đợi executor nhận task; còn có rejection/backpressure tùy cấu hình.

**Câu 3:** Khi inventory PASS và fraud không trả lời, có thể trả `CONFIRMED` không? **Không**, nếu hợp đồng bắt buộc đủ cả hai; cần timeout/recovery hoặc trạng thái chưa quyết định.

**Câu 4:** Một nhánh gửi hai reply duplicate, nhánh khác chưa phản hồi. Aggregator thấy hai message, có đủ để release chưa? **Chưa.** Phải đối chiếu tập recipient duy nhất và correlation.

**Câu 5:** Nếu notification thất bại nhưng đơn đã commit, có nhất thiết rollback đơn không? **Không**, trừ khi nghiệp vụ và giao dịch được thiết kế như vậy. Thường cần recovery riêng cho notification.

**Câu 6:** Scatter–Gather có tự bảo đảm exactly-once khi qua broker không? **Không.** Delivery, deduplication, idempotency, retry và transaction là những trách nhiệm cần thiết kế độc lập.

**Kết luận:** Không có quy tắc “Recipient List luôn phải chờ tất cả” hoặc “luôn nên fire-and-forget”. Quyết định xuất phát từ **hợp đồng nghiệp vụ**: những kết quả nào bắt buộc để tuyên bố thành công, mốc hoàn tất nào được chấp nhận và điều gì xảy ra nếu một recipient chậm hoặc lỗi. Trong Spring Integration, Recipient List giải quyết **chọn và phát tới nhiều đích**; loại channel quyết định **đồng bộ hay bất đồng bộ**; Scatter–Gather/Aggregator giải quyết **chờ và tổng hợp kết quả**. Thiết kế đúng correlation, expected recipient set, timeout, partial failure, retry, error channel, idempotency và observability sẽ giúp flow ít phụ thuộc mà vẫn có kết quả rõ ràng, có thể kiểm thử và phục hồi.
