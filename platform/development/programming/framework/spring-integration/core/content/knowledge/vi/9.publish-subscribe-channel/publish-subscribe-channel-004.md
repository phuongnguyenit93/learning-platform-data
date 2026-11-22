# Synchronous broadcast với PublishSubscribeChannel

## 1. Mục tiêu và bối cảnh

Trong module **SPRING_INTEGRATION_CORE**, `PublishSubscribeChannel` là một cách tổ chức luồng thông điệp theo mẫu publish–subscribe: bên phát gửi một sự kiện, nhiều endpoint đăng ký xử lý sự kiện đó. Bài này tập trung vào **synchronous broadcast**, tức phát thông điệp đồng bộ trong cùng luồng thực thi của bên gửi.

Sau bài học, bạn có thể:

- Phân biệt broadcast với việc chọn một consumer và với xử lý song song.
- Dự đoán thứ tự gọi handler, thời điểm `send()` trả về và tác động của một nhánh chậm.
- Xây dựng luồng bằng `Message`, `MessageHandler`, `PublishSubscribeChannel`, gateway và Java DSL.
- Chọn cách xử lý lỗi, hiểu giới hạn giao dịch và tránh chia sẻ payload có thể bị sửa.
- Viết kiểm thử xác nhận cùng luồng, thứ tự xử lý và hành vi khi một subscriber thất bại.

Bạn cần biết Java cơ bản, cấu trúc `Message<T>` gồm payload và headers, cùng vai trò của service activator. Các ví dụ dùng API của Spring Integration 6.x trở lên và cú pháp Java 17. Khi chọn phiên bản thư viện, dùng BOM phù hợp với dự án; các bản Spring mới hơn có thể yêu cầu JDK cao hơn. Phần kiểm thử dùng JUnit Jupiter.

Tình huống xuyên suốt là sự kiện `OrderPlaced`. Ứng dụng cần ghi nhận sự kiện vào nhật ký nghiệp vụ và cập nhật một mô hình đọc trong cùng ứng dụng. Hai thao tác được tách thành hai subscriber để bên phát không gọi trực tiếp từng dịch vụ.

## 2. Broadcast đồng bộ có nghĩa gì?

### 2.1. Hai quyết định độc lập

**Broadcast** trả lời câu hỏi: “Thông điệp được phân phối cho những ai?”. Với `PublishSubscribeChannel`, mục tiêu là chuyển thông điệp đến các handler đã đăng ký.

**Synchronous** trả lời câu hỏi: “Ai thực thi handler và bên gửi chờ đến đâu?”. Khi không cấu hình `Executor`, channel gọi các handler ngay trên thread đang thực hiện `send()`. Handler thứ nhất trả về thì dispatcher mới tiếp tục gọi handler kế tiếp.

Vì vậy, một thông điệp gửi đến ba subscriber thường có trình tự:

```text
caller bắt đầu send(message)
  -> gọi subscriber A
  <- A trả về
  -> gọi subscriber B
  <- B trả về
  -> gọi subscriber C
  <- C trả về
caller nhận kết quả của send(message)
```

Đây là việc một thread lần lượt thực hiện nhiều lời gọi. Tên “publish–subscribe” không hàm ý có thread pool.

`PublishSubscribeChannel` triển khai `SubscribableChannel`: consumer đăng ký bằng `subscribe(MessageHandler)`. Channel này không có thao tác `receive()` để consumer lấy thông điệp như một hàng đợi. Xem [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

### 2.2. Dòng thời gian của một lần gửi

```mermaid
sequenceDiagram
    participant Caller as Bên gửi
    participant Channel as PublishSubscribeChannel
    participant Audit as Subscriber audit
    participant Projection as Subscriber projection

    Note over Caller,Projection: Không có Executor; các lời gọi dưới đây cùng thread
    Caller->>Channel: send(OrderPlaced)
    Channel->>Audit: handleMessage(message)
    Audit-->>Channel: hoàn tất
    Channel->>Projection: handleMessage(message)
    Projection-->>Channel: hoàn tất
    Channel-->>Caller: true
```

Sơ đồ giả định hai subscriber đều thành công, cấu hình mặc định về số subscriber tối thiểu và không có interceptor ngăn việc gửi.

Nếu subscriber chỉ đưa việc vào một executor riêng rồi trả về, bên gửi chỉ chờ đến lúc giao việc xong. Muốn kết luận toàn bộ xử lý nghiệp vụ đã hoàn tất, phải xét tất cả ranh giới bất đồng bộ ở downstream.

### 2.3. So sánh với những channel gần giống

| Lựa chọn | Cách phân phối | Thread xử lý | Bên gửi chờ gì? |
| --- | --- | --- | --- |
| `DirectChannel` | Point-to-point; một handler xử lý thành công mỗi thông điệp | Thông thường cùng thread bên gửi | Lời gọi downstream đồng bộ trả về |
| `PublishSubscribeChannel` không có executor | Broadcast đến các subscriber | Cùng thread bên gửi | Các lời gọi handler đồng bộ trả về, hoặc gặp lỗi làm dừng dispatch |
| `PublishSubscribeChannel` có executor dùng thread pool | Broadcast, có thể xử lý đồng thời | Thread do executor bố trí | Thường chờ giao tác vụ; không bảo đảm nghiệp vụ ở mọi nhánh đã xong |
| `QueueChannel` | Lưu thông điệp để một consumer nhận mỗi lần | Thread của consumer/poller | Đưa thông điệp vào queue theo khả năng tiếp nhận |

Với `DirectChannel`, failover có thể thử handler khác khi handler trước thất bại; điều đó vẫn khác broadcast. Với channel có executor, lịch chạy thực tế phụ thuộc executor được chọn.

Bảng này giúp chọn cơ chế cho một yêu cầu cụ thể. Nếu chỉ một trong nhiều worker được phép xử lý đơn hàng, broadcast sẽ tạo hành vi khác mong muốn.

## 3. Quan sát bằng một ví dụ Java nhỏ

Ví dụ sau dùng trực tiếp channel, chưa cần khởi tạo Spring application context:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class SynchronousBroadcastDemo {

    public static void main(String[] args) {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        List<String> trace = new ArrayList<>();
        Thread caller = Thread.currentThread();

        channel.subscribe(message -> {
            if (Thread.currentThread() != caller) {
                throw new IllegalStateException("Audit chạy khác thread");
            }
            trace.add("audit:" + message.getPayload());
        });

        channel.subscribe(message -> {
            if (Thread.currentThread() != caller) {
                throw new IllegalStateException("Projection chạy khác thread");
            }
            trace.add("projection:" + message.getPayload());
        });

        Message<String> event = MessageBuilder
                .withPayload("ORDER-1042")
                .setHeader("eventType", "OrderPlaced")
                .build();

        trace.add("before-send");
        boolean sent = channel.send(event);
        trace.add("after-send");

        System.out.println(sent);
        System.out.println(trace);
    }
}
```

Trong ví dụ đăng ký trực tiếp, tuần tự và không đặt độ ưu tiên riêng, kết quả dự kiến là:

```text
true
[before-send, audit:ORDER-1042, projection:ORDER-1042, after-send]
```

Điểm cần quan sát là cả hai handler đã thêm dữ liệu trước khi xuất hiện `after-send`. Biến `caller` giữ chính đối tượng `Thread`, nên phép kiểm tra không phụ thuộc tên thread.

`ArrayList` ở đây chỉ phục vụ ví dụ một bên gửi trong một thread. Không dùng cách lưu vết này cho nhiều producer đồng thời nếu chưa có cơ chế đồng bộ phù hợp.

## 4. Thứ tự subscriber và giới hạn của tính đồng bộ

### 4.1. Cấu hình thứ tự có chủ đích

Dispatcher duy trì tập handler có xét thông tin `Ordered`. Trong Java DSL, có thể đặt `endpoint.order(10)`, `endpoint.order(20)`; giá trị nhỏ hơn được ưu tiên trước. Với handler không có độ ưu tiên khác nhau, thứ tự đăng ký có vai trò trong thứ tự dispatch. Cơ chế nền được mô tả trong [AbstractDispatcher](https://docs.spring.io/spring-integration/api/org/springframework/integration/dispatcher/AbstractDispatcher.html); DSL cung cấp [ConsumerEndpointSpec.order](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/ConsumerEndpointSpec.html).

Không suy thứ tự chạy từ vị trí các phương thức `@Bean` trong mã nguồn. Lifecycle, cách tạo endpoint và thứ tự đăng ký thực tế có thể khiến suy luận đó sai.

Nếu B bắt buộc sử dụng **kết quả mà A vừa tính**, hãy cân nhắc mô hình pipeline:

```text
input -> validate -> transform -> persist -> output
```

Trong broadcast, các nhánh nhận sự kiện đầu vào. Kết quả trả về từ transformer ở nhánh A không tự trở thành đầu vào của nhánh B. Đặt `order` chỉ quyết định thứ tự gọi, không tạo quan hệ truyền kết quả giữa hai nhánh.

### 4.2. Đồng bộ theo từng lần gọi, không tuần tự hóa toàn hệ thống

Giả sử hai thread cùng gửi đến một channel:

```text
Thread T1: send(event-1) -> audit(event-1) -> projection(event-1)
Thread T2: send(event-2) -> audit(event-2) -> projection(event-2)
```

Các lời gọi của T1 và T2 có thể xen kẽ. Cùng một handler có thể đang xử lý hai sự kiện trên hai thread khác nhau. Do đó:

- Handler dạng singleton phải an toàn khi được gọi đồng thời.
- Không lưu thông điệp hiện tại trong một field dùng chung của handler.
- Thứ tự nhánh trong một lần gửi không tạo bảo đảm thứ tự toàn cục giữa mọi thông điệp.
- Nếu cần thứ tự theo mã đơn hàng, phải thiết kế cơ chế điều phối theo khóa hoặc cơ chế tuần tự hóa phù hợp.

Synchronous broadcast không tự thêm một khóa toàn cục bao quanh mọi lời gọi `send()`.

### 4.3. Chi phí của nhánh chậm

Nếu audit mất 12 ms, projection mất 35 ms và cập nhật thống kê mất 8 ms, thời gian xử lý đồng bộ của một lần gửi xấp xỉ:

```text
T_send ≈ 12 + 35 + 8 + chi phí dispatch = 55 ms + chi phí dispatch
```

Đây là phép ước lượng cho ba lời gọi tuần tự, không bao gồm phần xử lý khác của request. Thêm một nhánh gọi HTTP mất 2 giây sẽ trực tiếp làm tăng thời gian chờ của bên gửi và trì hoãn các subscriber đứng sau nó.

Một thread xử lý liên tiếp các thông điệp như trên có trần lý thuyết khoảng `1000 / 55 ≈ 18` thông điệp/giây trước khi tính thêm chi phí. Tăng số producer có thể tăng số lời gọi đồng thời, nhưng cũng tăng áp lực lên database và dịch vụ downstream.

`channel.send(message, 100)` không đặt giới hạn 100 ms cho toàn bộ mã nghiệp vụ trong các handler. Đối số timeout của API gửi không phải cơ chế cưỡng chế ngắt một handler đồng bộ đang chạy. Timeout khi gọi HTTP, JDBC hoặc dịch vụ khác cần được cấu hình ở chính lớp thực hiện thao tác đó.

## 5. Xây dựng luồng bằng gateway và Java DSL

### 5.1. Cấu hình hoàn chỉnh cho hai subscriber

Mã sau là một cấu hình minh họa đặt trong file `OrderBroadcastConfiguration.java`. Dự án cần `spring-integration-core` cùng các dependency Spring tương thích; khi dùng Spring Boot, có thể dùng starter Integration. Các ví dụ kiểm thử ở phần sau cần thêm `junit-jupiter` trong test scope.

```java
package example.integration;

import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
@IntegrationComponentScan(
        basePackageClasses = OrderBroadcastConfiguration.class)
public class OrderBroadcastConfiguration {

    public record OrderPlaced(
            String eventId,
            String orderId,
            BigDecimal total) {
    }

    @MessagingGateway(defaultRequestChannel = "orderEvents")
    public interface OrderEvents {
        void publish(OrderPlaced event);
    }

    @Bean
    public EventConsumers eventConsumers() {
        return new EventConsumers();
    }

    @Bean
    public IntegrationFlow orderEventFlow(EventConsumers consumers) {
        return IntegrationFlow.from("orderEvents")
                .publishSubscribeChannel(broadcast -> broadcast
                        .applySequence(false)
                        .ignoreFailures(false)
                        .subscribe(branch -> branch
                                .handle(consumers, "audit",
                                        endpoint -> endpoint.order(10)))
                        .subscribe(branch -> branch
                                .handle(consumers, "updateProjection",
                                        endpoint -> endpoint.order(20))))
                .get();
    }

    public static class EventConsumers {

        public void audit(OrderPlaced event) {
            System.out.printf(
                    "audit order=%s event=%s thread=%s%n",
                    event.orderId(),
                    event.eventId(),
                    Thread.currentThread().getName());
        }

        public void updateProjection(OrderPlaced event) {
            System.out.printf(
                    "projection order=%s total=%s thread=%s%n",
                    event.orderId(),
                    event.total(),
                    Thread.currentThread().getName());
        }
    }
}
```

Trong ứng dụng thực tế, `EventConsumers` có thể được thay bằng các service riêng. Hai phương thức hiện chỉ in thông tin để làm rõ cơ chế gọi.

Luồng gồm các bước:

1. Spring tạo proxy cho interface `OrderEvents` được quét bởi `@IntegrationComponentScan`.
2. Proxy bọc `OrderPlaced` thành một `Message` và gửi đến `orderEvents`.
3. `IntegrationFlow.from("orderEvents")` sử dụng channel đầu vào theo tên; trong cấu hình này DSL tạo channel đầu vào mặc định.
4. `.publishSubscribeChannel(...)` tạo điểm broadcast không có executor.
5. Hai endpoint service activator gọi lần lượt `audit` rồi `updateProjection`, theo `order` đã cấu hình.

Kiểu trả về `void` của gateway thể hiện không yêu cầu một business reply. Trong luồng hoàn toàn đồng bộ này, lời gọi `publish()` vẫn thực thi các subscriber trước khi trở về; `void` không biến lời gọi thành bất đồng bộ.

Hai phương thức xử lý cũng trả `void`, phù hợp với nhánh nhận sự kiện và kết thúc xử lý. Nếu thay bằng phương thức trả dữ liệu, cần thiết kế output/reply channel thích hợp.

Ví dụ sử dụng một gateway đã được inject:

```java
events.publish(new OrderBroadcastConfiguration.OrderPlaced(
        "evt-1042",
        "ORDER-1042",
        new BigDecimal("125000.00")));
```

Biến `events` trong đoạn gọi trên có kiểu `OrderBroadcastConfiguration.OrderEvents`.

### 5.2. Đọc đúng cấu trúc subflow

Mỗi `.subscribe(branch -> ...)` tạo một nhánh nhận thông điệp từ điểm broadcast. Trong mỗi nhánh, bạn có thể tiếp tục dùng transformer, filter, router hoặc handler.

Ví dụ, filter đặt trong nhánh thống kê chỉ quyết định nhánh thống kê có đi tiếp hay không. Nếu muốn mọi subscriber chỉ thấy các sự kiện hợp lệ, hãy đặt bước kiểm tra chung trước điểm broadcast.

Một bước viết tiếp sau `.publishSubscribeChannel(...)` trong DSL cũng có thể trở thành một subscriber bổ sung. Không coi đó là điểm “đợi tất cả nhánh rồi hợp nhất”. Cách DSL nối các nhánh được minh họa trong [Sub-flows support](https://docs.spring.io/spring-integration/reference/dsl/java-subflows.html).

Nếu cần thu thập kết quả từ nhiều nhánh thành một reply, hãy thiết kế luồng scatter–gather hoặc aggregator với channel kết quả và quy tắc hoàn tất rõ ràng.

## 6. Một subscriber thất bại thì chuyện gì xảy ra?

### 6.1. Hành vi mặc định: dừng sớm

`ignoreFailures` mặc định là `false`. Khi không có executor, lỗi từ một handler làm lời gọi dispatch thất bại và có thể ngăn các handler phía sau được gọi. `BroadcastingDispatcher` mô tả đây là hành vi fail-fast. Xem [BroadcastingDispatcher](https://docs.spring.io/spring-integration/api/org/springframework/integration/dispatcher/BroadcastingDispatcher.html).

Với thứ tự audit → projection → statistics:

```text
audit: hoàn tất
projection: ném exception
statistics: chưa được gọi
send(): ném exception về bên gửi
```

Đối với handler và endpoint Spring Integration, exception nghiệp vụ thường xuất hiện bên trong một `MessagingException`, chẳng hạn `MessageHandlingException`. Khi phân tích lỗi, xem cả nguyên nhân gốc và `failedMessage` nếu có.

Điều này cũng giải thích vì sao “gửi đến mọi subscriber” là mục tiêu phân phối, không phải lời hứa mọi subscriber đều đã được gọi bất chấp lỗi.

### 6.2. Tiếp tục các nhánh bằng ignoreFailures

Bạn có thể chọn:

```java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
channel.setIgnoreFailures(true);
```

Với cấu hình này, lỗi dispatch thông thường của một handler được ghi log và dispatcher cố tiếp tục các handler khác. Kết quả xử lý có thể là:

```text
audit: hoàn tất
projection: thất bại, dispatcher ghi cảnh báo
statistics: vẫn được gọi
send(): không ném lại lỗi projection chỉ vì lỗi đó
```

`ignoreFailures(true)` không phải retry, không tạo bản ghi lỗi bền vững và không tạo một giá trị kết quả tổng hợp cho từng nhánh.

Một lựa chọn thiết kế tốt hơn cho nhiều nghiệp vụ là phân loại nhánh:

| Loại nhánh | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Bắt buộc để request được chấp nhận | Kiểm tra nghiệp vụ hoặc ghi dữ liệu thiết yếu | Cho lỗi đi ra ngoài; xác định ranh giới giao dịch |
| Bổ sung, cho phép thất bại tạm thời | Thống kê hoặc theo dõi phụ trợ | Xử lý lỗi cục bộ, ghi nhận và có cơ chế thử lại nếu cần |
| Tác vụ lâu hoặc phụ thuộc hệ thống ngoài | Gửi email, gọi đối tác | Cân nhắc tách qua ranh giới bất đồng bộ và cơ chế giao nhận phù hợp |

Đặt cờ bỏ qua lỗi trên toàn channel ảnh hưởng đến mọi subscriber của channel đó. Nếu chỉ một nhánh có chính sách chấp nhận lỗi, nên thể hiện chính sách ngay tại nhánh.

### 6.3. errorChannel không tự bắt mọi lỗi đồng bộ

Với channel đồng bộ gọi trực tiếp, lỗi thường đi theo call stack về caller. Chỉ thêm header `errorChannel` không khiến channel này tự chuyển mọi exception thành `ErrorMessage`.

`ErrorHandler` gắn cho `PublishSubscribeChannel` chỉ được áp dụng khi channel có executor; khi không có executor, exception được ném trực tiếp trên thread bên gửi. Xem [cấu hình PublishSubscribeChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

Gateway có thể có chính sách lỗi riêng, chẳng hạn một error channel được cấu hình cho gateway. Đây là hành vi của gateway ở ranh giới lời gọi. Cấu hình DSL ở trên không khai báo chính sách đó.

Nếu cần tạo thông điệp lỗi cho một nhánh đồng bộ, hãy chủ động cấu hình advice hoặc một lớp xử lý lỗi thích hợp. Chính sách lỗi trong luồng đồng bộ và bất đồng bộ được trình bày tại [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

## 7. Cùng thread hỗ trợ giao dịch đến mức nào?

Một giao dịch Spring được mở trước khi gọi gateway có thể tiếp tục bao phủ những endpoint chạy cùng thread, với điều kiện các thao tác tham gia đúng transaction manager và tuân theo quy tắc propagation phù hợp. Channel không tự mở transaction. Xem [Transaction Boundaries](https://docs.spring.io/spring-integration/reference/transactions.html#transaction-boundaries).

Xét một service được gọi qua Spring proxy với `@Transactional`:

```text
bắt đầu transaction
  -> ghi đơn hàng bằng repository
  -> gateway.publish(event)
       -> audit ghi database
       -> projection ghi database rồi ném RuntimeException
exception đi ra ngoài service
transaction manager áp dụng quy tắc rollback
```

Nếu các lần ghi đều tham gia cùng giao dịch và tài nguyên được quản lý, rollback có thể hoàn tác chúng. Tuy nhiên, kết quả thực tế còn phụ thuộc propagation, transaction manager, tài nguyên và cấu hình rollback.

Các trường hợp cần phân biệt:

- Email đã gửi hoặc HTTP request đã được đối tác xử lý không tự được hoàn tác khi database rollback.
- Nhánh dùng `REQUIRES_NEW` có thể commit một giao dịch độc lập trước khi nhánh khác thất bại.
- Nhánh chuyển qua executor hoặc queue không tiếp tục dùng cùng transaction context chỉ vì được gọi từ channel ban đầu.
- Nếu bắt và nuốt exception, caller có thể thấy thành công. Ngược lại, một transaction interceptor phía trong có thể đã đánh dấu rollback-only, làm giao dịch vẫn không commit được.

Vì vậy, không dùng `ignoreFailures(true)` như cách bảo đảm “nhánh lỗi nhưng transaction chắc chắn vẫn commit”.

Tên sự kiện `OrderPlaced` trong ví dụ chỉ mô tả một thông tin nghiệp vụ. Nếu phát trước commit, subscriber không được suy ra đơn hàng đã commit. Khi yêu cầu là “chỉ phát sự kiện sau khi đơn hàng được ghi chắc chắn”, cần xác định rõ thời điểm phát và có thể dùng cơ chế sau commit hoặc transactional outbox tùy yêu cầu giao nhận.

## 8. Chia sẻ Message, payload và metadata cho aggregator

### 8.1. Bất biến của vỏ Message khác với bất biến sâu của payload

Mặc định `applySequence` là `false`, nên các subscriber có thể nhận cùng một đối tượng `Message`. Khi bật cờ này, channel tạo các message với metadata sequence riêng nhưng vẫn dùng chung tham chiếu payload. Đây không phải sao chép sâu. Cấu trúc này được mô tả trong [PublishSubscribeChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

Xét payload là một `Map<String, Object>`:

```text
subscriber A: payload.put("status", "PROCESSED")
subscriber B: đọc payload.get("status")
```

B có thể nhìn thấy thay đổi từ A trong cùng lần gửi. Cách truyền thông tin ngầm này làm các nhánh phụ thuộc thứ tự và dễ gây lỗi khi thay cấu hình.

Nên chọn:

- Payload bất biến, chẳng hạn record chứa các giá trị bất biến.
- Sao chép phòng vệ đối với collection hoặc đối tượng lồng bên trong.
- Transformer tạo payload mới cho đầu ra của nhánh thay vì sửa payload gốc.

Record chỉ bảo đảm các component reference là final. Một record chứa `ArrayList` vẫn có thể để lộ danh sách có thể sửa. Record `OrderPlaced` trong bài dùng `String` và `BigDecimal`, phù hợp để chia sẻ trong ví dụ.

### 8.2. applySequence không làm các nhánh chạy song song

Nếu kết quả các nhánh cần đi vào aggregator, có thể bật:

```java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
channel.setApplySequence(true);
```

Với hai subscriber, metadata phục vụ việc liên kết nhóm gồm correlation ID, sequence number tương ứng từng nhánh và sequence size bằng 2. API khuyến nghị bật cờ khi dùng aggregator với chiến lược correlation và completion mặc định. Xem [PublishSubscribeChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html).

Cờ này chỉ thêm thông tin để downstream biết các thông điệp liên quan với nhau. Nó không:

- Tạo executor hay thread mới.
- Tự nối các output của các nhánh vào một aggregator.
- Biến handler `void` thành handler có reply.
- Tạo kết quả cho nhánh đã bị filter loại bỏ hoặc gặp lỗi.

Ví dụ, nếu sequence size là 2 nhưng một nhánh không phát kết quả, aggregator có thể chờ mãi nếu thiếu timeout hoặc chính sách hoàn tất khác. Đây là lý do phải thiết kế đồng thời fan-out, đường quay về và điều kiện giải phóng nhóm.

## 9. Giá trị send(), số subscriber và khả năng giao nhận

### 9.1. true không phải biên nhận nghiệp vụ đầy đủ

Trong trường hợp không có lỗi và có đủ subscriber theo cấu hình, `send()` trả `true`. Giá trị đó không chứa danh sách kết quả từng nhánh.

Mặc định `minSubscribers = 0`. Vì vậy, một `PublishSubscribeChannel` chưa có subscriber vẫn có thể trả `true`. Nếu không chấp nhận trường hợp đó, có thể dùng constructor với `requireSubscribers = true`:

```java
PublishSubscribeChannel requiredChannel =
        new PublishSubscribeChannel(true);
```

Khi không có subscriber, channel này từ chối việc dispatch bằng exception thay vì âm thầm bỏ qua. Constructor này có từ Spring Integration 5.4.3. `setMinSubscribers(int)` là một tùy chọn khác liên quan điều kiện kết quả dispatch, không phải cơ chế tự tạo subscriber hay giao thức xác nhận phân tán. Xem [các constructor và minSubscribers](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html).

Nếu `send()` thất bại, không suy ra “chưa có tác dụng phụ nào”. Các nhánh trước điểm lỗi có thể đã xử lý.

### 9.2. Không có lưu trữ hoặc phát lại mặc định

Channel trong bài là cơ chế dispatch trong bộ nhớ của một ứng dụng. Subscriber đăng ký sau khi một sự kiện đã được gửi không tự nhận lại sự kiện cũ.

Nếu ứng dụng dừng giữa các nhánh, không có sẵn một bản ghi bền vững ở channel này để tiếp tục đúng nhánh còn thiếu sau khi khởi động lại. Với yêu cầu giao nhận qua sự cố, cần thiết kế message store, broker hoặc outbox thích hợp.

Một sự kiện mang `eventId` giúp downstream nhận diện lần giao lại, nhưng header hoặc field đó không tự cung cấp idempotency.

### 9.3. Retry toàn bộ broadcast có thể lặp tác dụng phụ

Giả sử:

```text
lần 1: audit thành công -> projection lỗi
lần 2: retry toàn send -> audit lại chạy -> projection chạy lại
```

Nếu audit không tham gia một giao dịch đã được rollback, nó có thể ghi trùng. Khi thiết kế retry, xác định:

- Retry riêng handler thất bại hay retry cả lời gọi gateway.
- Tác dụng phụ nào đã commit trước điểm lỗi.
- Khóa idempotency cho từng subscriber, chẳng hạn `(subscriberName, eventId)`.
- Cách cập nhật dấu đã xử lý và dữ liệu nghiệp vụ một cách nhất quán.

Nếu cần bảo đảm chống trùng khi có nhiều thread, kiểm tra rồi ghi bằng hai thao tác rời rạc thường chưa đủ; cần cơ chế nguyên tử phù hợp, chẳng hạn ràng buộc duy nhất trong database cùng giao dịch.

## 10. Kiểm thử các đặc tính của broadcast đồng bộ

### 10.1. Những điều nên chứng minh

Kiểm thử hữu ích cần quan sát hành vi:

1. Mọi subscriber dự kiến nhận sự kiện trước khi `send()` trả về.
2. Handler chạy trên cùng đối tượng thread với bên gửi.
3. Độ ưu tiên được tôn trọng dù thứ tự đăng ký khác nhau.
4. Lỗi mặc định ngăn nhánh sau chạy nhưng không xóa tác dụng phụ đã xảy ra trong bộ nhớ.
5. Bật bỏ qua lỗi cho phép nhánh tiếp theo được gọi.
6. Không có subscriber được xử lý theo chính sách đã chọn.

Không cần `Thread.sleep()` hoặc vòng polling để chứng minh các hành vi đồng bộ này.

### 10.2. Ví dụ JUnit Jupiter

Lớp bên dưới kiểm thử channel trực tiếp. `OrderedHandler` kế thừa `AbstractMessageHandler` để dùng cơ chế `setOrder()` rõ ràng.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.handler.AbstractMessageHandler;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SynchronousBroadcastTest {

    @Test
    void invokesEverySubscriberOnCallerThreadBeforeReturning() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        List<String> trace = new ArrayList<>();
        Thread caller = Thread.currentThread();

        // Đăng ký order=20 trước để kiểm tra độ ưu tiên thực sự.
        channel.subscribe(new OrderedHandler(20, message -> {
            assertSame(caller, Thread.currentThread());
            trace.add("projection");
        }));
        channel.subscribe(new OrderedHandler(10, message -> {
            assertSame(caller, Thread.currentThread());
            trace.add("audit");
        }));

        trace.add("before");
        boolean sent = channel.send(event());
        trace.add("after");

        assertTrue(sent);
        assertEquals(
                List.of("before", "audit", "projection", "after"),
                trace);
    }

    @Test
    void stopsAfterFailureAndKeepsEarlierInMemorySideEffects() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        List<String> trace = new ArrayList<>();

        channel.subscribe(new OrderedHandler(
                10, message -> trace.add("audit")));
        channel.subscribe(new OrderedHandler(20, message -> {
            trace.add("projection-start");
            throw new IllegalStateException("Projection unavailable");
        }));
        channel.subscribe(new OrderedHandler(
                30, message -> trace.add("statistics")));

        assertThrows(MessagingException.class,
                () -> channel.send(event()));

        assertEquals(List.of("audit", "projection-start"), trace);
    }

    @Test
    void continuesAfterFailureWhenConfiguredToIgnoreFailures() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        channel.setIgnoreFailures(true);
        List<String> trace = new ArrayList<>();

        channel.subscribe(new OrderedHandler(10, message -> {
            trace.add("audit-failed");
            throw new IllegalStateException("Audit unavailable");
        }));
        channel.subscribe(new OrderedHandler(
                20, message -> trace.add("projection")));

        assertTrue(channel.send(event()));
        assertEquals(List.of("audit-failed", "projection"), trace);
    }

    @Test
    void allowsNoSubscribersByDefaultButCanRequireOne() {
        PublishSubscribeChannel optional = new PublishSubscribeChannel();
        PublishSubscribeChannel required = new PublishSubscribeChannel(true);

        assertTrue(optional.send(event()));
        assertThrows(MessagingException.class,
                () -> required.send(event()));
    }

    private static Message<String> event() {
        return MessageBuilder.withPayload("ORDER-1042").build();
    }

    private static final class OrderedHandler
            extends AbstractMessageHandler {

        private final Consumer<Message<?>> action;

        private OrderedHandler(
                int order, Consumer<Message<?>> action) {
            setOrder(order);
            this.action = action;
        }

        @Override
        protected void handleMessageInternal(Message<?> message) {
            action.accept(message);
        }
    }
}
```

Kiểm thử đầu tiên dùng `assertSame` cho thread và đặt `after` ngay sau lời gọi `send()`. Hai quan sát này xác nhận đồng thời nơi handler chạy và thời điểm trả về.

Kiểm thử thứ hai cố ý dùng một danh sách trong bộ nhớ. Nó cho thấy tác dụng phụ trước lỗi vẫn còn; nó không kiểm chứng khả năng rollback database.

Kiểm thử với `ignoreFailures` có thể tạo log cảnh báo do lỗi chủ động trong test. Assertions cần tập trung vào nhánh được gọi và exception có truyền ra hay không.

Bộ kiểm thử này chưa khởi tạo cấu hình gateway/DSL. Để xác nhận wiring của ứng dụng, bổ sung kiểm thử application context gọi gateway thật và quan sát các service được inject. Kiểm thử transaction cần transaction manager và tài nguyên thực tế hoặc môi trường kiểm thử phù hợp; không suy ra kết quả giao dịch từ những assertions trên danh sách.

## 11. Chẩn đoán những hiểu nhầm thường gặp

| Hiện tượng hoặc giả định | Cách giải thích | Hướng điều chỉnh |
| --- | --- | --- |
| “Có nhiều subscriber thì chúng phải chạy song song” | Không có executor nên các lời gọi của một lần gửi là tuần tự | Quan sát thread; lựa chọn mô hình đồng thời theo yêu cầu |
| Request chậm sau khi thêm một nhánh | Thời gian nhánh mới cộng vào thời gian caller chờ | Đo từng handler; cấu hình timeout của tác vụ I/O; cân nhắc tách nhánh |
| Subscriber thứ ba không nhận thông điệp | Subscriber trước có thể đã ném lỗi với `ignoreFailures=false` | Xem nguyên nhân gốc và thứ tự handler |
| Đã đặt `errorChannel` nhưng caller vẫn nhận exception | Lỗi đồng bộ đang truyền theo call stack | Cấu hình chính sách tại caller, gateway hoặc endpoint phù hợp |
| `send()` trả `true` dù không thấy xử lý | Có thể không có subscriber, hoặc downstream chỉ giao việc | Kiểm tra lifecycle, số subscriber và các ranh giới bất đồng bộ |
| Nhánh B thấy dữ liệu do A sửa | Các nhánh có thể chia sẻ payload | Dùng dữ liệu bất biến và transformer tạo đầu ra mới |
| Retry làm audit bị ghi hai lần | Phát lại toàn bộ broadcast gọi lại nhánh trước | Xác định phạm vi retry và cơ chế idempotency |
| Dùng pub-sub nhưng chỉ muốn một worker nhận | Yêu cầu thực tế là point-to-point | Chọn channel và consumer model phù hợp |
| Bật `applySequence` nhưng không có kết quả tổng | Metadata sequence không tạo aggregator hoặc đường kết quả | Nối output từng nhánh và định nghĩa cách hoàn tất nhóm |

Khi theo dõi một sự kiện, ghi tối thiểu `eventId`, `orderId`, tên nhánh, thời gian bắt đầu/kết thúc và trạng thái lỗi. Thời gian `send()` tổng giúp phát hiện caller chờ lâu; số đo theo nhánh giúp xác định nơi gây chậm.

Nếu có nhiều request đồng thời, log sẽ xen kẽ dù mỗi lần broadcast là đồng bộ. Dùng correlation ID để nhóm log theo sự kiện thay vì suy thứ tự từ toàn bộ console.

## 12. Thực hành mở rộng trong phạm vi bài học

Bắt đầu với cấu hình hai subscriber ở trên và thực hiện lần lượt:

1. Thay output console bằng hai service giả lưu sự kiện; xác nhận mỗi service được gọi một lần sau khi gateway trả về.
2. Làm nhánh projection ném lỗi cho một `orderId` cụ thể; quan sát exception ở caller và tác dụng phụ của nhánh audit.
3. Thêm subscriber thứ ba với `order=30`; so sánh danh sách lời gọi khi `ignoreFailures` là `false` và `true`.
4. Đặt một filter vào một nhánh; xác nhận việc lọc ở nhánh đó không tự loại thông điệp khỏi các nhánh còn lại.
5. Đổi payload thành một record chứa collection được sao chép phòng vệ; giải thích vì sao việc này giúp các nhánh độc lập hơn.
6. Thiết kế trên giấy cách gom hai kết quả bằng aggregator: output channel nào nhận kết quả, nhóm theo gì, khi nào nhóm hoàn tất và xử lý thế nào nếu một nhánh không trả kết quả.

Tiêu chí hoàn thành là dự đoán được đường đi của từng thông điệp, thread thực hiện, các subscriber thực sự được gọi và cách lỗi quay về bên phát.

## 13. Tài liệu chính thức để tra cứu

- [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html): phân biệt publish–subscribe, point-to-point và queue.
- [PublishSubscribeChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html): constructor, `ignoreFailures`, `minSubscribers`, `applySequence`.
- [BroadcastingDispatcher API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dispatcher/BroadcastingDispatcher.html): dừng sớm và tiếp tục dispatch khi bỏ qua lỗi.
- [Sub-flows support](https://docs.spring.io/spring-integration/reference/dsl/java-subflows.html): cấu trúc subscriber trong Java DSL.
- [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): đường truyền lỗi trong các loại luồng.
- [Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): khởi tạo giao dịch và ranh giới thread.
