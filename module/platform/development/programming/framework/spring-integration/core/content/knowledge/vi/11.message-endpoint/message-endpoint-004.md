# PollingConsumer

## 1. Mục tiêu và phạm vi

Trong chương **Message endpoint** của **SPRING_INTEGRATION_CORE**, `PollingConsumer` là endpoint chủ động lấy thông điệp từ một `PollableChannel`, sau đó giao thông điệp cho `MessageHandler`. Nó kết nối mô hình hàng đợi với các thành phần xử lý như service activator, transformer, filter và router.

Sau bài này, bạn có thể:

- Phân biệt `PollingConsumer`, `EventDrivenConsumer` và `SourcePollingChannelAdapter`.
- Tạo luồng `Message` qua `QueueChannel` đến handler bằng Java DSL.
- Chọn lịch polling, thời gian chờ nhận, số message mỗi lượt và mức độ đồng thời.
- Giải thích cách xử lý lỗi, giới hạn transaction và nguy cơ mất hoặc xử lý trùng message.
- Kiểm thử hành vi bất đồng bộ với thời hạn chờ rõ ràng.

Bài tập trung vào Spring Integration Core. Các hệ thống lưu trữ hoặc truyền tin khác chỉ được nhắc đến để làm rõ ranh giới độ bền và transaction.

## 2. Bài toán: tiếp nhận nhanh, xử lý theo nhịp riêng

Giả sử gateway tiếp nhận đơn hàng nhưng bước xử lý phải gọi một dịch vụ có tốc độ giới hạn. Nếu thực hiện toàn bộ nghiệp vụ ngay trên luồng gửi, thời gian phản hồi sẽ phụ thuộc vào dịch vụ phía sau.

Có thể tách hai giai đoạn bằng `QueueChannel`:

```text
Gateway hoặc producer
         |
         | send(Message<Order>)
         v
QueueChannel
         ^
         | receive(timeout)
PollingConsumer
         |
         | handleMessage(message)
         v
MessageHandler xử lý đơn
```

Producer gửi message vào queue. Endpoint phía nhận được kích hoạt theo lịch để gọi `receive(...)`. Gửi thành công vào hàng đợi chưa có nghĩa là nghiệp vụ đã hoàn thành.

Cách này giúp hấp thụ các đợt tăng tải ngắn và điều chỉnh nhịp xử lý. Đổi lại, cần quản lý dung lượng queue, độ trễ, lỗi sau khi gửi và trạng thái endpoint.

> `QueueChannel` trong bộ nhớ không tự cung cấp khả năng lưu bền. Khi tiến trình dừng, các message còn trong queue có thể bị mất.

## 3. Cấu trúc của PollingConsumer

### 3.1. Channel, endpoint và handler

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `PollableChannel` | Cho phép bên nhận chủ động lấy message | `QueueChannel`, `PriorityChannel` |
| `PollingConsumer` | Điều phối việc nhận và gọi handler | Endpoint của service activator đọc queue |
| `MessageHandler` | Thực hiện bước xử lý thông điệp | Transformer, filter, router, service activator |

Quan hệ cốt lõi có thể biểu diễn bằng:

```java
PollableChannel inputChannel;
MessageHandler handler;

PollingConsumer endpoint =
        new PollingConsumer(inputChannel, handler);
```

Đây chỉ là minh họa quan hệ giữa các kiểu, chưa phải cấu hình có thể chạy độc lập. Endpoint còn cần lịch polling, scheduler và quản lý vòng đời. Trong ứng dụng thông thường, nên để Spring tạo endpoint qua Java DSL hoặc cấu hình framework.

### 3.2. Handler không phải endpoint

Service activator mô tả vai trò xử lý nghiệp vụ; `PollingConsumer` mô tả cách nhận message. Cùng một loại handler có thể được bao bởi endpoint khác nhau:

- Đọc từ `SubscribableChannel`: thường dùng `EventDrivenConsumer`.
- Đọc từ `PollableChannel`: dùng `PollingConsumer` và cần poller.

Transformer, filter và router cũng có thể chạy trong `PollingConsumer` nếu đầu vào của chính bước đó là `PollableChannel`.

Với aggregator, poller chỉ điều khiển việc nhận message vào bước xử lý. Việc gom nhóm và giải phóng nhóm vẫn phụ thuộc correlation strategy, release strategy, message store và chính sách hết hạn của aggregator.

### 3.3. Một lượt polling

Một lượt polling có thể hình dung như sau:

1. Trigger xác định đã đến thời điểm kích hoạt.
2. Endpoint bắt đầu lượt polling trên luồng thực thi tương ứng.
3. Endpoint gọi `receive(receiveTimeout)` trên input channel.
4. Nếu nhận được message, endpoint gọi handler với message đó.
5. Nếu cấu hình cho phép, endpoint tiếp tục nhận message trong cùng lượt.
6. Lượt kết thúc khi đạt giới hạn, không nhận được message hoặc gặp điều kiện kết thúc như lỗi không được xử lý.

Advice, transaction, executor và xử lý lỗi có thể bổ sung hành vi quanh quá trình này.

## 4. Phân biệt các cơ chế tiêu thụ và lấy nguồn

| Tiêu chí | `EventDrivenConsumer` | `PollingConsumer` | `SourcePollingChannelAdapter` |
| --- | --- | --- | --- |
| Đầu vào | `SubscribableChannel` | `PollableChannel` | `MessageSource` |
| Kích hoạt | Channel phân phối tới subscriber | Endpoint chủ động nhận từ channel | Endpoint chủ động đọc source |
| Cấu hình polling | Không áp dụng cho bước nhận này | Poller của consumer endpoint | Poller của inbound adapter |
| Ví dụ | Service activator đọc `DirectChannel` | Service activator đọc `QueueChannel` | Adapter đọc thư mục theo lịch |
| Vai trò | Tiêu thụ message được phân phối | Tiêu thụ message đã có trong channel | Đưa message từ nguồn vào luồng |

`PollingConsumer` không tự quét thư mục hoặc truy vấn một nguồn bên ngoài. Khi inbound adapter đọc file rồi gửi message vào queue, việc đọc file và việc tiêu thụ queue là hai giai đoạn khác nhau.

Bất đồng bộ cũng không đồng nghĩa với polling. `ExecutorChannel` chuyển công việc qua executor nhưng vẫn là channel có subscriber. Với `DirectChannel`, handler thường chạy ngay trên luồng gửi; với `QueueChannel`, producer đặt message vào queue để bên nhận lấy sau.

## 5. Java DSL: xử lý đơn hàng từ QueueChannel

### 5.1. Cấu hình luồng

Ví dụ dùng `spring-integration-core`, Spring Context và Java 17 trở lên để khai báo `record`. Với Spring Boot, có thể dùng starter integration và quản lý phiên bản theo bộ dependency của dự án. Những đoạn dưới là ví dụ cấu hình, chưa phải một dự án có đầy đủ dependency và chương trình khởi chạy.

```java
import java.math.BigDecimal;

public record Order(String id, BigDecimal amount) {
}
```

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
@EnableIntegration
public class OrderFlowConfiguration {

    @Bean
    public QueueChannel ordersQueue() {
        return new QueueChannel(200);
    }

    @Bean
    public IntegrationFlow processOrders() {
        return IntegrationFlow
                .from(ordersQueue())
                .handle(Order.class, (order, headers) -> {
                    System.out.println("Processing order " + order.id());
                    // Thực hiện nghiệp vụ tại đây.
                    return null;
                }, endpoint -> endpoint
                        .id("orderPollingConsumer")
                        .poller(Pollers
                                .fixedDelay(Duration.ofMillis(500))
                                .receiveTimeout(0)
                                .maxMessagesPerPoll(10)))
                .get();
    }
}
```

Ý nghĩa của từng phần:

- `ordersQueue()` tạo queue có sức chứa 200 message.
- `.from(ordersQueue())` chọn channel đầu vào.
- `.handle(...)` khai báo handler xử lý payload `Order`.
- `.poller(...)` cấu hình polling trên endpoint của chính handler đó.
- `.id("orderPollingConsumer")` đặt tên endpoint để nhận diện khi quản lý hoặc theo dõi.
- `receiveTimeout(0)` trả về ngay nếu chưa có message trong queue.
- `maxMessagesPerPoll(10)` giới hạn tối đa 10 message trong một lượt.
- Handler trả `null` vì luồng kết thúc tại bước xử lý đơn, không tạo reply.

Các lời gọi chéo `ordersQueue()` trong lớp trên dựa vào proxy mặc định của `@Configuration`. Nếu dùng `@Configuration(proxyBeanMethods = false)`, hãy truyền bean channel qua tham số thay vì gọi chéo phương thức tạo bean.

### 5.2. Gửi message có thời hạn chờ

```java
import java.math.BigDecimal;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class OrderPublisher {

    private final QueueChannel ordersQueue;

    public OrderPublisher(QueueChannel ordersQueue) {
        this.ordersQueue = ordersQueue;
    }

    public void publish() {
        Message<Order> message = MessageBuilder
                .withPayload(new Order("ORD-1001", new BigDecimal("250000")))
                .setHeader("traceId", "trace-1001")
                .build();

        boolean accepted = ordersQueue.send(message, 200);
        if (!accepted) {
            throw new IllegalStateException("Orders queue is full");
        }
    }
}
```

Thời hạn 200 ms trong `send(...)` là thời gian chờ đặt message vào queue khi queue đầy. Nó không phải thời hạn xử lý nghiệp vụ và không phải `receiveTimeout` của consumer.

Header `traceId` đi cùng message tới handler. Dữ liệu chỉ nằm trong `ThreadLocal` của producer không tự xuất hiện ở luồng consumer, nên thông tin truy vết cần được truyền bằng cơ chế phù hợp.

### 5.3. Đặt poller ở đúng bước

Xét luồng:

```text
QueueChannel -> transformer -> DirectChannel -> service activator
```

Transformer là bước đầu tiên đọc queue nên endpoint của transformer cần poller. Service activator nhận qua `DirectChannel` và không cần poller cho bước nhận đó.

Nếu đặt một `QueueChannel` khác trước service activator, endpoint đọc queue thứ hai cần poller riêng. Không gắn poller vào mọi bước chỉ vì đầu luồng có queue.

## 6. Cấu hình nhịp polling

### 6.1. fixedDelay

Khi poller thực hiện công việc trực tiếp trên scheduler, không chuyển lượt polling sang executor riêng, fixed delay là khoảng nghỉ từ lúc lượt trước hoàn tất đến khi lượt tiếp theo bắt đầu.

Ví dụ `fixedDelay = 500 ms`:

```text
T0         bắt đầu polling
T0+300 ms  xử lý xong lượt hiện tại
T0+800 ms  lượt tiếp theo có thể bắt đầu
```

Nếu một lượt xử lý nhiều message hoặc gọi dịch vụ chậm, chu kỳ thực tế dài hơn 500 ms. Cấu hình trên không có nghĩa cứ 500 ms chắc chắn xử lý được 10 message.

Khi có `taskExecutor`, scheduler có thể chỉ giao công việc cho executor. Thời điểm giao việc xong và thời điểm worker hoàn tất không còn là một mốc; cần xem cả khả năng chồng lấn và backlog của executor.

### 6.2. fixedRate và cron

- **Fixed rate:** phù hợp khi lịch cần dựa trên nhịp định kỳ; không bảo đảm nghiệp vụ hoàn thành đúng từng mốc nếu tài nguyên bận.
- **Cron:** phù hợp với lịch theo thời điểm, chẳng hạn khung giờ trong ngày; cần xác định múi giờ của trigger.
- **Fixed delay:** dễ suy luận khi muốn có khoảng nghỉ sau một lượt làm việc.

Fixed rate không tự bảo đảm handler chạy song song. Mức đồng thời phụ thuộc scheduler, executor và cấu trúc endpoint.

### 6.3. receiveTimeout

`receiveTimeout` điều khiển thời gian một lần nhận có thể chờ khi channel chưa cung cấp message. Với `QueueChannel`, `0` giúp trả về ngay khi queue rỗng.

Nếu timeout nhận là 1.000 ms, một lượt có thể dành gần một giây để chờ message. Sau khi nhận được message, handler vẫn có thể chạy lâu hơn một giây.

- Timeout lớn có thể nhận message đến trong lúc chờ, nhưng giữ luồng trong thời gian chờ.
- Timeout nhỏ hoặc bằng 0 dễ kiểm soát khi nhiều endpoint chia sẻ scheduler.
- Timeout của HTTP, cơ sở dữ liệu hoặc nghiệp vụ phải đặt tại thành phần thực hiện lời gọi đó.

### 6.4. maxMessagesPerPoll

| Cách chọn | Ý nghĩa và đánh đổi |
| --- | --- |
| `1` | Mỗi lượt tối đa một message; dễ quan sát nhưng có thể tăng chi phí lập lịch |
| Số dương lớn hơn `1` | Nhiều message trong một lượt; giảm số lần kích hoạt nhưng giữ luồng lâu hơn |
| Giá trị âm theo cơ chế poller | Không giới hạn bằng số lượng; lượt thường dừng khi không nhận được message hoặc gặp điều kiện kết thúc |

Nên khai báo rõ một giá trị dương ban đầu, thay vì dựa vào mặc định của các loại polling endpoint. Với cấu hình không giới hạn và producer liên tục bổ sung message, một lượt có thể kéo dài, chiếm tài nguyên dùng chung.

`maxMessagesPerPoll(10)` không có nghĩa là:

- Handler nhận một danh sách 10 phần tử.
- Có 10 worker chạy đồng thời.
- Toàn hệ thống chỉ được xử lý 10 message mỗi giây.
- Mười message tự động thuộc cùng một transaction.

Handler thông thường vẫn được gọi từng message. Nếu cần payload dạng batch, phải thiết kế bước gom nhóm hoặc nguồn hỗ trợ batch.

### 6.5. Ước lượng thông lượng

Với queue luôn có dữ liệu, một worker tuần tự, fixed delay và không có executor riêng:

```text
Thời gian một lượt ≈ N × T_xử_lý + D

Thông lượng ≈ N / (N × T_xử_lý + D)
```

Trong đó `N` là số message thực tế trong lượt, `T_xử_lý` là thời gian xử lý trung bình của một message và `D` là fixed delay; thời gian tính bằng giây.

Nếu `N = 10`, mỗi message mất `0,05 s`, delay là `0,5 s`, thông lượng lý tưởng khoảng `10 message/s`. Phép tính chưa gồm thời gian nhận, logging, tranh chấp tài nguyên, lỗi hoặc retry.

Nếu tốc độ vào trung bình là 15 message/s trong thời gian dài, backlog vẫn tăng. Tăng dung lượng queue chỉ kéo dài thời gian trước khi đầy; cần tăng năng lực xử lý, điều chỉnh tốc độ vào hoặc thay đổi cách phân phối công việc.

## 7. Scheduler, executor và mức đồng thời

### 7.1. Hai vai trò khác nhau

Task scheduler quyết định thời điểm kích hoạt. Task executor cung cấp luồng thực thi khi poller được cấu hình chuyển công việc sang executor riêng.

Không khai báo executor riêng không có nghĩa toàn ứng dụng chỉ có một luồng. Nhiều endpoint vẫn có thể dùng những luồng scheduler khác nhau, nhưng một lần nhận chặn lâu hoặc handler chạy lâu sẽ giữ luồng thực hiện nó.

### 7.2. Thêm executor có giới hạn

Có thể bổ sung bean sau vào lớp cấu hình chính:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
public ThreadPoolTaskExecutor orderPollExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("order-poll-");
    return executor;
}
```

Thay cấu hình poller của handler bằng:

```java
.poller(Pollers
        .fixedDelay(Duration.ofMillis(500))
        .receiveTimeout(0)
        .maxMessagesPerPoll(10)
        .taskExecutor(orderPollExecutor()))
```

Spring quản lý khởi tạo và đóng executor khi nó là bean. Các lượt polling có thể thực thi chồng lấn khi lịch tiếp tục giao việc và executor có khả năng nhận việc.

Mỗi lượt vẫn xử lý tuần tự các message của lượt đó. Executor tạo cơ hội cho nhiều lượt cùng hoạt động, không tự chia một lượt 10 message thành 10 công việc độc lập.

### 7.3. Điều kiện cần xem xét khi tăng đồng thời

1. **Thread safety:** handler không được sửa trạng thái dùng chung một cách không an toàn.
2. **Thứ tự:** FIFO nói về thứ tự lấy message; nhiều worker có thể hoàn thành khác thứ tự lấy.
3. **Tài nguyên phía sau:** số worker phải phù hợp connection pool và giới hạn dịch vụ ngoài.
4. **Backlog executor:** cần hiểu chính sách từ chối hoặc chặn giao việc khi hàng đợi đầy.
5. **Ngữ cảnh luồng:** transaction, security context và logging context không tự đi qua mọi ranh giới bất đồng bộ.

Nếu nghiệp vụ cần đúng thứ tự theo từng khách hàng, hãy thiết kế phân vùng hoặc tuần tự hóa theo khóa. Chỉ tăng worker của một queue không đáp ứng yêu cầu đó.

## 8. Poller mặc định và poller cục bộ

Có thể dùng poller mặc định cho các endpoint có đặc tính tương tự:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.scheduling.PollerMetadata;

@Bean(name = PollerMetadata.DEFAULT_POLLER)
public PollerMetadata defaultPoller() {
    return Pollers
            .fixedDelay(Duration.ofSeconds(1))
            .receiveTimeout(0)
            .maxMessagesPerPoll(5)
            .getObject();
}
```

Endpoint cần polling có thể dùng poller mặc định khi không khai báo poller cục bộ. Nếu endpoint đã có `.poller(...)`, chính sách cục bộ được dùng cho endpoint đó.

Nếu thiếu cả poller cục bộ và mặc định, endpoint đọc `PollableChannel` thường khiến việc tạo application context thất bại. Gắn poller vào endpoint đọc `DirectChannel` lại là dấu hiệu chọn sai cơ chế nhận.

Các luồng có SLA hoặc chi phí xử lý khác biệt nên có cấu hình riêng rõ ràng ngay tại endpoint.

## 9. Xử lý lỗi sau khi message đã vào queue

### 9.1. Bên gửi không còn ở cùng call stack

```text
Producer: send(message) -> thành công -> tiếp tục công việc khác

Sau đó:
PollingConsumer: receive() -> handler -> ném exception
```

`try/catch` quanh `send(...)` chỉ bắt lỗi đồng bộ của thao tác gửi và các xử lý thực sự xảy ra trong lời gọi đó. Nó không bắt lỗi nghiệp vụ xuất hiện sau này trên luồng polling consumer.

Với gateway, phải phân biệt:

- Gateway một chiều: hoàn tất thao tác gửi không thể hiện kết quả nghiệp vụ.
- Gateway request-reply: caller có thể đang chờ reply; cần thiết kế `replyChannel`, `errorChannel`, timeout và cách trả kết quả lỗi phù hợp luồng bất đồng bộ.

Không giả định cứ dùng gateway thì mọi lỗi sau queue sẽ tự trở lại thành exception cho caller.

### 9.2. ErrorMessage và errorChannel

Trong cơ chế xử lý lỗi bất đồng bộ thông thường, Spring Integration chuyển lỗi thành `ErrorMessage` và gửi đến error channel theo cấu hình. Với lỗi gắn được vào message, header `errorChannel` có thể tham gia chọn nơi nhận lỗi; khi không có chỉ định riêng, error channel mặc định là điểm xử lý thường dùng.

Payload của `ErrorMessage` là một `Throwable`. Message thất bại thường có thể lấy từ `MessagingException`. Tuy nhiên, lỗi khi nhận từ kho lưu trữ có thể xảy ra trước khi có message nghiệp vụ.

Ví dụ thêm luồng lỗi vào cấu hình đã có `@EnableIntegration`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;

@Bean
public IntegrationFlow logIntegrationErrors() {
    return IntegrationFlow
            .from("errorChannel")
            .handle(Throwable.class, (failure, headers) -> {
                Message<?> failedMessage = null;

                if (failure instanceof MessagingException messagingException) {
                    failedMessage = messagingException.getFailedMessage();
                }

                Object traceId = failedMessage == null
                        ? null
                        : failedMessage.getHeaders().get("traceId");

                System.err.println("Integration failure, traceId=" + traceId);
                failure.printStackTrace();
                return null;
            })
            .get();
}
```

Đây là ví dụ quan sát cơ chế. Khi vận hành, nên dùng logging có cấu trúc và tránh ghi dữ liệu nhạy cảm. Nếu exception bị bọc nhiều lớp, có thể cần kiểm tra chuỗi nguyên nhân để tìm message thất bại.

Nếu cấu hình `ErrorHandler` riêng cho poller, phải kiểm tra hành vi của cấu hình đó; không suy ra đường đi của lỗi chỉ từ tên bean `errorChannel`.

### 9.3. Error channel không tự phục hồi message

Có subscriber nhận `ErrorMessage` không tự tạo ra các hành vi sau:

- Đặt lại message vào queue ban đầu.
- Rollback queue trong bộ nhớ.
- Retry có backoff.
- Lưu bền thông tin để phát lại sau khi khởi động lại.

Nên phân loại lỗi trước khi quyết định xử lý:

| Loại lỗi | Hướng xử lý |
| --- | --- |
| Dữ liệu không hợp lệ | Đưa vào luồng từ chối, giữ lý do và khóa nghiệp vụ |
| Dịch vụ ngoài tạm thời không khả dụng | Retry có giới hạn và backoff |
| Hết số lần retry | Chuyển sang kênh lỗi cuối hoặc kho message thất bại |
| Lỗi kho lưu trữ của channel | Cảnh báo hạ tầng, đánh giá khả năng phục hồi endpoint |

Nếu cần phục hồi sau sự cố tiến trình, nơi lưu lỗi cuối cũng cần độ bền phù hợp. Một `QueueChannel` thứ hai trong bộ nhớ không giải quyết yêu cầu đó.

### 9.4. Phạm vi retry

Cần phân biệt advice của poller, có thể bao quanh thao tác nhận và gọi handler, với advice của chính handler nghiệp vụ.

Nếu chỉ muốn thử lại một lời gọi dịch vụ, advice dành cho handler thường dễ kiểm soát hơn. Retry quanh polling có thể dẫn đến lần thử lại nhận message khác sau khi message trước đã bị lấy khỏi queue.

Nếu handler đã tạo tác dụng phụ rồi mới lỗi, retry có thể lặp lại tác dụng phụ đó. Cần khóa nghiệp vụ hoặc idempotency key và quy tắc rõ ràng về lỗi được phép thử lại.

## 10. Transaction và độ tin cậy

### 10.1. Poller có transaction

Poller có thể được cấu hình với transaction manager:

```java
// transactionManager là PlatformTransactionManager của tài nguyên liên quan.
.poller(Pollers
        .fixedDelay(Duration.ofMillis(500))
        .receiveTimeout(0)
        .maxMessagesPerPoll(1)
        .transactional(transactionManager))
```

Đây là mảnh cấu hình để ghép vào endpoint, chưa khai báo transaction manager hoặc kho lưu trữ cụ thể.

Transaction chỉ bảo vệ tài nguyên thực sự tham gia cùng ranh giới transaction. Thêm `.transactional(...)` không khiến mọi thao tác trong handler đều có thể rollback.

`maxMessagesPerPoll` cũng không phải API định nghĩa transaction batch. Không được suy ra một lượt tối đa 10 message có nghĩa cả 10 nằm trong cùng transaction; cần xét cách thực thi polling và advice thực tế.

### 10.2. Queue bộ nhớ không tự hoàn tác receive

Với queue trong bộ nhớ thông thường:

```text
1. receive() lấy message ra khỏi queue.
2. Handler ghi cơ sở dữ liệu.
3. Handler ném exception.
4. Transaction cơ sở dữ liệu rollback.
5. Message không tự quay lại queue chỉ nhờ rollback đó.
```

Queue dùng message store có hỗ trợ giao dịch, chẳng hạn thiết kế dựa trên JDBC channel message store, có thể cho phép thao tác lấy message tham gia transaction. Cần chọn đúng transaction manager, tài nguyên kết nối và cấu hình store. Chỉ có một kho lưu trữ bất kỳ chưa đủ để kết luận nhận message sẽ rollback đúng yêu cầu.

### 10.3. Ranh giới đồng bộ

Transaction gắn với luồng xử lý có thể bao phủ các bước đồng bộ tiếp theo nếu tài nguyên hỗ trợ. Nếu gửi công việc qua `ExecutorChannel` hoặc một queue khác, phần phía sau có ranh giới thực thi riêng và không tự kế thừa transaction hiện tại.

HTTP hoặc email không tự được hoàn tác khi cơ sở dữ liệu rollback. Quy trình vừa ghi dữ liệu vừa phát sự kiện có thể cần transactional outbox hoặc cơ chế điều phối phù hợp nghiệp vụ.

### 10.4. Exactly-once không đến từ riêng endpoint

`PollingConsumer` điều phối nhận và xử lý, không tự bảo đảm nghiệp vụ chỉ xảy ra đúng một lần.

Ví dụ, yêu cầu thanh toán đã thành công nhưng ứng dụng lỗi trước khi ghi nhận kết quả. Nếu message được phát lại, yêu cầu thanh toán có thể được gửi lần nữa. Khóa như `orderId` hoặc `paymentRequestId` phải được dùng tại nơi thực hiện tác dụng phụ, không chỉ có trong log.

Độ tin cậy toàn luồng phụ thuộc độ bền message, rollback hoặc phát lại, idempotency và khả năng đối soát.

## 11. Kiểm thử PollingConsumer

### 11.1. Kiểm thử đầu vào và đầu ra

Kiểm thử nên chứng minh message đi qua queue, được xử lý và xuất hiện ở đầu ra. Output queue cho phép chờ kết quả với thời hạn rõ ràng.

Cấu hình dưới độc lập với ví dụ đơn hàng. Nó cần JUnit Jupiter cùng Spring Integration và Spring Context của dự án.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PollingConsumerTest {

    @Configuration
    @EnableIntegration
    static class TestConfiguration {

        @Bean
        QueueChannel testInput() {
            return new QueueChannel(10);
        }

        @Bean
        QueueChannel testOutput() {
            return new QueueChannel(10);
        }

        @Bean
        IntegrationFlow testFlow() {
            return IntegrationFlow
                    .from(testInput())
                    .handle(String.class, (payload, headers) ->
                                    payload.toUpperCase(Locale.ROOT),
                            endpoint -> endpoint.poller(Pollers
                                    .fixedDelay(Duration.ofMillis(20))
                                    .receiveTimeout(0)
                                    .maxMessagesPerPoll(1)))
                    .channel(testOutput())
                    .get();
        }
    }

    @Test
    void shouldProcessMessageFromQueue() {
        try (var context = new AnnotationConfigApplicationContext(
                TestConfiguration.class)) {
            QueueChannel input = context.getBean("testInput", QueueChannel.class);
            QueueChannel output = context.getBean("testOutput", QueueChannel.class);

            boolean sent = input.send(MessageBuilder
                    .withPayload("spring integration")
                    .setHeader("traceId", "test-001")
                    .build(), 100);

            assertTrue(sent);

            Message<?> result = output.receive(2_000);

            assertNotNull(result);
            assertEquals("SPRING INTEGRATION", result.getPayload());
            assertEquals("test-001", result.getHeaders().get("traceId"));
        }
    }
}
```

Đầu vào là queue và handler có poller nên kiểm thử thực sự đi qua cơ chế polling. Đầu ra cũng là queue để kiểm thử có thể nhận kết quả; không cần thêm consumer chỉ để lấy message kiểm thử.

Hai giây là giới hạn chờ, không phải thời gian xử lý cố định. `receive(...)` trả về sớm khi có message. Cách này tốt hơn `Thread.sleep(...)` rồi giả định xử lý đã hoàn tất.

### 11.2. Các tình huống bổ sung

| Tình huống | Điều cần quan sát |
| --- | --- |
| Queue rỗng | Không có kết quả giả, không làm cạn tài nguyên chờ |
| Nhiều message | Đủ kết quả, thứ tự phù hợp mức đồng thời |
| Queue đầy | Producer timeout hoặc nhận lỗi đúng chính sách |
| Handler lỗi | Lỗi đến đúng kênh, có thông tin truy vết |
| Retry | Đúng số lần thử và tác dụng phụ mong muốn |
| Endpoint dừng | Không tiếp tục lấy message mới như khi đang chạy |
| Rollback với store giao dịch | Message và dữ liệu nghiệp vụ phục hồi theo thiết kế |
| Khởi động lại | Chỉ khẳng định phục hồi khi có cơ chế lưu bền được kiểm chứng |

Muốn kiểm thử riêng `maxMessagesPerPoll`, cần kiểm soát trigger và vòng đời endpoint. Gửi 10 message rồi chờ vài giây không chứng minh mỗi lượt chỉ nhận một message, vì poller có thể đã chạy nhiều lượt.

## 12. Vòng đời và vận hành

### 12.1. Kiểm tra endpoint có chạy hay không

Queue có thể nhận message ngay cả khi consumer chưa chạy. Khi backlog tăng, hãy kiểm tra lifecycle, auto-startup, lịch polling, scheduler và executor, thay vì chỉ kiểm tra handler.

Tên endpoint `.id("orderPollingConsumer")` giúp định vị thành phần cần quản lý. Dừng endpoint và hoàn tất các công việc đang chạy không phải một thao tác tức thời; chính sách shutdown cần xét handler đang gọi dịch vụ và executor còn công việc chờ.

### 12.2. Tín hiệu cần theo dõi

- Số message đang chờ và xu hướng backlog.
- Tuổi message lâu nhất hoặc thời gian chờ trước khi xử lý.
- Thời gian xử lý handler và thông lượng thực tế.
- Số lỗi, retry và message chuyển sang kho lỗi cuối.
- Số luồng scheduler bận, worker executor bận và công việc chờ.
- Tỷ lệ producer timeout khi gửi vào queue.

Không phải mọi metric trên tự xuất hiện với cùng tên trong mọi ứng dụng; có thể cần Micrometer, observation hoặc phép đo nghiệp vụ bổ sung.

Nếu cần đo tuổi message từ lần tiếp nhận đầu tiên, hãy dùng header thời điểm tiếp nhận rõ ràng. Không mặc định timestamp của message hiện tại luôn đại diện cho lần đầu dữ liệu vào hệ thống, vì các bước tạo message mới có thể thay đổi metadata.

### 12.3. Chẩn đoán theo triệu chứng

| Triệu chứng | Khả năng cần kiểm tra | Hành động ban đầu |
| --- | --- | --- |
| Khởi động lỗi khi handler đọc queue | Thiếu poller | Kiểm tra poller cục bộ và mặc định |
| Backlog tăng nhưng không xử lý | Endpoint dừng, lịch chưa đến hoặc luồng bị chiếm | Kiểm tra lifecycle và thread dump |
| Chậm hơn chu kỳ cấu hình | Handler chậm, nhận bị chặn hoặc lượt quá dài | Đo thời gian nhận và xử lý riêng |
| Nhiều endpoint cùng chậm | Scheduler hoặc tài nguyên phía sau bão hòa | Kiểm tra pool và lời gọi chặn |
| Hoàn thành sai thứ tự | Nhiều lượt/worker xử lý đồng thời | Xem lại yêu cầu thứ tự và phân vùng |
| Message mất sau lỗi | Queue bộ nhớ không có rollback/phát lại | Kiểm tra chính sách lỗi và store |
| CPU cao khi queue rỗng | Polling quá dày hoặc quá nhiều endpoint thăm dò | Điều chỉnh nhịp theo SLA và số đo |
| Executor tích nhiều công việc | Giao việc nhanh hơn worker xử lý | Giới hạn queue, đồng thời và nhịp kích hoạt |

## 13. Bài thực hành: bộ xử lý thông báo đơn hàng

Thiết kế luồng:

```text
Producer
   |
   v
notificationQueue (capacity = 100)
   |
   | PollingConsumer
   v
Kiểm tra dữ liệu -> Chọn loại thông báo -> Gửi thông báo
                                      |
                                      v
                               Luồng xử lý lỗi
```

Thực hiện lần lượt:

1. Tạo queue sức chứa 100; message có `notificationId` và `traceId`.
2. Đặt fixed delay 200 ms, `receiveTimeout(0)`, tối đa 5 message mỗi lượt.
3. Bắt đầu với xử lý tuần tự; ghi nhận thời điểm tiếp nhận, bắt đầu và hoàn tất.
4. Trong môi trường thực hành, mô phỏng handler cần khoảng 100 ms mỗi message.
5. Tạo một trường hợp dữ liệu sai và một trường hợp dịch vụ tạm thời lỗi.
6. Thiết kế nơi nhận lỗi để có thể xử lý lại yêu cầu thất bại khi phù hợp.
7. Thêm executor có giới hạn, quan sát thông lượng và thứ tự hoàn thành.
8. Viết kiểm thử đường thành công và đường lỗi với thời hạn chờ.

Câu hỏi phân tích:

- Một lượt 5 message mất khoảng bao lâu trước khi tính fixed delay?
- Tốc độ vào 20 message/s có bền vững với cấu hình tuần tự không?
- Tăng `maxMessagesPerPoll` có giảm thời gian gọi dịch vụ cho từng message không?
- Hai worker có bảo đảm hoàn thành theo thứ tự gửi không?
- Nếu tiến trình dừng sau khi lấy message nhưng trước khi gửi thông báo, phục hồi bằng cách nào?
- Dùng `notificationId` như thế nào để tránh gửi trùng khi retry?

Với 100 ms mỗi message, 5 message mất khoảng 500 ms. Cộng fixed delay 200 ms, năng lực lý tưởng tuần tự khoảng `5 / 0,7 ≈ 7,14 message/s`, chưa tính chi phí khác. Tốc độ vào 20 message/s sẽ khiến backlog tăng dần.

## 14. Tự kiểm tra kiến thức

1. **PollingConsumer nhận từ đâu?** Từ `PollableChannel`; inbound adapter polling đọc từ `MessageSource`.
2. **Tại sao handler đọc QueueChannel cần poller?** Queue không chủ động gọi subscriber khi producer gửi; cần bên nhận chủ động lấy.
3. **receiveTimeout có giới hạn handler không?** Không, nó giới hạn thời gian chờ nhận.
4. **maxMessagesPerPoll(10) có tạo 10 worker không?** Không, nó giới hạn số message mỗi lượt.
5. **Gửi thành công có nghĩa xử lý thành công không?** Không, đặc biệt khi queue tạo ranh giới bất đồng bộ.
6. **Error channel có tự retry không?** Không, cần chính sách retry hoặc phát lại riêng.
7. **Transaction manager có tự rollback queue bộ nhớ không?** Không, tài nguyên channel phải hỗ trợ và tham gia transaction tương ứng.
8. **Vì sao cần idempotency?** Message có thể được thử lại sau khi tác dụng phụ đã xảy ra.
9. **Khi nào cần poller thứ hai?** Khi endpoint khác lại nhận từ một `PollableChannel` riêng.
10. **Cấu hình tốt được quyết định bằng gì?** Độ trễ, thông lượng, thứ tự, tài nguyên và độ tin cậy được kiểm chứng bằng hành vi thực tế.

Khi thiết kế `PollingConsumer`, cần xác định đồng thời chính sách nhận, tài nguyên thực thi, nơi nhận lỗi và cách phục hồi message. Một chu kỳ polling hợp lý chỉ là một phần của luồng tích hợp tin cậy.
