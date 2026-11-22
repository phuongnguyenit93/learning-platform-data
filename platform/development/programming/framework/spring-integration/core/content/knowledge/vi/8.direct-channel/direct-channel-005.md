# UnicastingDispatcher

Trong module **SPRING_INTEGRATION_CORE**, bài này thuộc chương **DirectChannel** và giải thích cách một thông điệp được giao cho subscriber. Đây là nền tảng để nối endpoint, đọc luồng Java DSL và hiểu lỗi khi nhiều handler cùng dùng một channel.

**UnicastingDispatcher** là bộ điều phối bên trong DirectChannel. Nó chọn thứ tự thử các handler và dừng khi một handler hoàn tất lời gọi mà không ném exception. Nếu được phép failover, những handler trước đó có thể đã được gọi và thất bại. Vì vậy, “unicast” không có nghĩa mọi lần gửi đều chỉ phát sinh đúng một lần gọi handler. [Javadoc UnicastingDispatcher](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dispatcher/UnicastingDispatcher.html)

## 1. Mục tiêu và phạm vi ví dụ

Sau bài này, bạn có thể:

- Phân biệt channel, dispatcher, endpoint và handler.
- Dự đoán handler được thử đầu tiên khi dùng round-robin hoặc thứ tự cố định.
- Cấu hình failover và nhận biết rủi ro thực thi nghiệp vụ lặp.
- Tạo hai endpoint cùng nhận từ một DirectChannel bằng Java DSL.
- Thiết kế kiểm thử về phân phối, lỗi và luồng thực thi.

Các ví dụ dùng **Java 17**, API **Spring Integration 6.5.0** làm mốc tái hiện. Riêng `setFailoverStrategy(Predicate<Exception>)` có từ **6.3**. Đây là mốc API của bài, không phải khẳng định về phiên bản mới nhất. [Javadoc về failover strategy](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dispatcher/UnicastingDispatcher.html#setFailoverStrategy(java.util.function.Predicate))

Với Maven độc lập, dependency phục vụ ví dụ chính là:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
    <version>6.5.0</version>
</dependency>
~~~

Nếu dự án dùng Spring Boot, để BOM của Boot quản lý phiên bản tương thích. Các đoạn minh họa dưới đây không yêu cầu broker, cơ sở dữ liệu hay dịch vụ bên ngoài.

## 2. Vị trí trong luồng thông điệp

~~~mermaid
flowchart LR
    P["Producer hoặc gateway"] --> C["DirectChannel"]
    C --> D["UnicastingDispatcher"]
    D --> S["Thứ tự thử handler"]
    S --> A["Handler A"]
    A -->|Thành công| R["send trả về"]
    A -->|Exception và cho phép failover| B["Handler B"]
    B -->|Thành công| R
    B -->|Hết ứng viên hoặc dừng failover| E["Exception về caller"]
~~~

| Thành phần | Trách nhiệm |
| --- | --- |
| `Message<?>` | Mang payload và headers của một thông điệp. |
| `DirectChannel` | Cung cấp API gửi và đăng ký subscriber. |
| `UnicastingDispatcher` | Thực hiện việc giao thông điệp theo ngữ nghĩa unicast. |
| `LoadBalancingStrategy` | Xác định thứ tự thử các handler. |
| Chính sách failover | Quyết định có tiếp tục sang handler khác sau exception hay không. |
| Consumer endpoint | Quản lý việc kết nối handler với input channel và vòng đời endpoint. |
| `MessageHandler` | Nhận lời gọi `handleMessage(message)` để xử lý. |

Ở mức triển khai, `subscribe()` và `unsubscribe()` của channel chuyển việc thêm hoặc xóa handler xuống dispatcher; `doSend()` chuyển việc giao thông điệp xuống `dispatch()`. [Mã nguồn AbstractSubscribableChannel](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/AbstractSubscribableChannel.java)

Bạn thường cấu hình **DirectChannel**, không cần tạo bean UnicastingDispatcher riêng. `getDispatcher()` trên DirectChannel là phương thức `protected`; các setter công khai của channel chuyển cấu hình xuống bộ điều phối. [Mã nguồn DirectChannel](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/DirectChannel.java)

### Unicast và broadcast

Với đơn hàng `ORDER-701`, hai handler cùng thực hiện nghiệp vụ “ghi nhận đơn hàng” có thể là hai lựa chọn thay thế nhau. DirectChannel phù hợp với cấu trúc này.

Nếu cùng một sự kiện phải đến cả kế toán và gửi email, cần cấu trúc phát tới nhiều nhánh, chẳng hạn PublishSubscribeChannel. Nhiều subscriber trên DirectChannel không biến channel thành broadcast. [Các triển khai message channel](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html)

## 3. Điều gì xảy ra trong một lần dispatch?

Có thể đọc cơ chế theo bốn bước:

1. Lấy các handler đang đăng ký và thứ tự thử.
2. Gọi handler đầu tiên trong thứ tự đó.
3. Nếu lời gọi hoàn tất bình thường, kết thúc dispatch.
4. Nếu có exception, xét chính sách failover: thử ứng viên tiếp theo hoặc kết thúc bằng lỗi.

Dispatcher không tự chờ rồi thử lại cùng handler. Với round-robin chuẩn và tập subscriber ổn định, danh sách ứng viên chứa mỗi handler một lần trong một lượt dispatch. [Mã nguồn UnicastingDispatcher](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/UnicastingDispatcher.java), [mã nguồn RoundRobinLoadBalancingStrategy](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/RoundRobinLoadBalancingStrategy.java)

### “Thành công” được nhận biết ở đâu?

Hợp đồng `MessageHandler.handleMessage()` trả về `void`. Ở ranh giới dispatcher, hoàn tất bình thường được xem là đã nhận xử lý; dispatcher không kiểm tra trạng thái đơn hàng trong database.

Ví dụ, handler bắt lỗi rồi chỉ ghi log sẽ che lỗi khỏi dispatcher:

~~~java
channel.subscribe(message -> {
    try {
        persistOrder(message.getPayload());
    }
    catch (RuntimeException ex) {
        logger.warn("Không lưu được đơn hàng", ex);
        // Lời gọi kết thúc bình thường: dispatcher không failover.
    }
});
~~~

Đây là đoạn mã tình huống: `persistOrder` và `logger` thuộc ứng dụng. Nếu hợp đồng yêu cầu chuyển sang phương án dự phòng, lỗi cần được biểu đạt ra ngoài ranh giới xử lý phù hợp.

Một filter loại bỏ message mà không ném exception cũng không làm dispatcher tự tìm subscriber khác. Mặc định filter có thể loại bỏ thông điệp mà không phát sinh lỗi; cấu hình rejection cần được chọn theo nghiệp vụ. [Tài liệu Message Filter](https://docs.spring.io/spring-integration/reference/6.5/filter.html)

Không nên tạo các filter cạnh tranh trên DirectChannel rồi mong channel tự tìm nhánh khớp payload. Khi nghiệp vụ yêu cầu chọn nhánh theo loại đơn hàng hoặc header, hãy biểu đạt quyết định đó bằng router. [Tổng quan router](https://docs.spring.io/spring-integration/reference/6.5/router/overview.html)

## 4. Round-robin: luân phiên điểm bắt đầu

`new DirectChannel()` dùng `RoundRobinLoadBalancingStrategy` mặc định. Failover cũng mặc định được bật. Hai tùy chọn này giải quyết hai việc khác nhau: chọn thứ tự thử và quyết định có tiếp tục sau lỗi. [Cấu hình DirectChannel](https://docs.spring.io/spring-integration/reference/6.4/channel/configuration.html)

Giả sử đăng ký lần lượt A, B, C, dùng một producer gửi tuần tự, không thay đổi subscriber và không có lỗi:

| Lần gửi | Thứ tự ứng viên | Handler hoàn tất |
| --- | --- | --- |
| M1 | A → B → C | A |
| M2 | B → C → A | B |
| M3 | C → A → B | C |
| M4 | A → B → C | A |

Nếu A thất bại ở M1 và B thành công, M1 kết thúc tại B. Điểm bắt đầu của M2 vẫn là B trong điều kiện trên; round-robin luân phiên theo lượt dispatch, không tính theo “handler thành công gần nhất”. [Cách round-robin tạo iterator](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/RoundRobinLoadBalancingStrategy.java)

### Ví dụ Java độc lập

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

public class RoundRobinDemo {

    public static void main(String[] args) {
        DirectChannel orders = new DirectChannel();
        List<String> events = new ArrayList<>();
        Thread sender = Thread.currentThread();

        orders.subscribe(message -> {
            requireSenderThread(sender);
            events.add("A:" + message.getPayload());
        });

        orders.subscribe(message -> {
            requireSenderThread(sender);
            events.add("B:" + message.getPayload());
        });

        for (int number = 1; number <= 4; number++) {
            Message<String> message =
                    new GenericMessage<>("ORDER-" + number);

            if (!orders.send(message)) {
                throw new IllegalStateException("Không gửi được message");
            }
        }

        System.out.println(events);
    }

    private static void requireSenderThread(Thread sender) {
        if (Thread.currentThread() != sender) {
            throw new IllegalStateException("Handler đổi thread");
        }
    }
}
~~~

Kết quả dự kiến:

~~~text
[A:ORDER-1, B:ORDER-2, A:ORDER-3, B:ORDER-4]
~~~

Ví dụ đăng ký trực tiếp handler để quan sát dispatcher, không cần khởi tạo Spring context.

### Luân phiên không đồng nghĩa xử lý song song

DirectChannel gọi handler trong thread gửi. Khi M1 đang chạy một handler chậm, producer tuần tự chưa thể gửi tiếp M2 qua cùng chuỗi lời gọi. [Javadoc DirectChannel](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/channel/DirectChannel.html)

Suy ra, thêm subscriber không tự tăng số thread. Nếu có nhiều producer đồng thời, cùng một handler có thể được nhiều thread gọi; trạng thái dùng chung của handler vẫn cần được bảo vệ. Round-robin cũng không cân tải theo thời gian xử lý hoặc số công việc đang chạy.

## 5. Thứ tự cố định và failover

Khi có một phương án chính và một phương án dự phòng, có thể tắt load balancing:

~~~java
DirectChannel orders = new DirectChannel(null);
orders.setFailover(true);
~~~

`null` ở constructor có nghĩa không dùng chiến lược cân bằng tải. Khi đó, việc thử handler bắt đầu theo thứ tự của tập subscriber. Nếu muốn dừng ngay ở lỗi đầu tiên, dùng `setFailover(false)`. [API cấu hình DirectChannel](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/channel/DirectChannel.html)

Ví dụ hoàn chỉnh:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.support.GenericMessage;

public class FixedOrderFailoverDemo {

    public static void main(String[] args) {
        DirectChannel orders = new DirectChannel(null);
        orders.setFailover(true);

        List<String> attempts = new ArrayList<>();

        orders.subscribe(message -> {
            attempts.add("primary:" + message.getPayload());
            throw new IllegalStateException("Kho chính tạm ngừng");
        });

        orders.subscribe(message ->
                attempts.add("backup:" + message.getPayload()));

        boolean delivered = orders.send(new GenericMessage<>("ORDER-701"));

        System.out.println("delivered=" + delivered);
        System.out.println(attempts);
    }
}
~~~

Kết quả dự kiến, ngoài log của framework:

~~~text
delivered=true
[primary:ORDER-701, backup:ORDER-701]
~~~

Handler đầu đã được gọi, ném exception, rồi handler sau hoàn tất. Một lần gửi đã có hai lần thử xử lý.

| Cấu hình | Điểm bắt đầu | Nếu handler đầu lỗi |
| --- | --- | --- |
| `new DirectChannel()` | Luân phiên | Mặc định thử handler tiếp theo |
| Channel mặc định + `setFailover(false)` | Luân phiên | Dừng và phát lỗi |
| `new DirectChannel(null)` | Theo thứ tự cố định | Mặc định thử handler tiếp theo |
| Thứ tự cố định + `setFailover(false)` | Theo thứ tự cố định | Dừng và phát lỗi |

Không nên dựa vào thứ tự khai báo bean để diễn đạt phương án chính. Khi dùng endpoint, hãy đặt `order` rõ ràng; thứ tự số nhỏ được ưu tiên trước. Với handler trực tiếp không có thông tin thứ tự như ví dụ trên, thứ tự thêm được giữ lại. [Tập handler có thứ tự của dispatcher](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/OrderedAwareCopyOnWriteArraySet.java)

## 6. Chỉ failover với loại lỗi phù hợp

Một lỗi kết nối tạm thời và một đơn hàng sai dữ liệu cần chính sách khác nhau. Từ Spring Integration 6.3, có thể cấu hình predicate thay vì bật failover cho mọi exception. `setFailover()` và `setFailoverStrategy()` thay thế chính sách của nhau; không nên xem chúng là hai điều kiện được kết hợp. [Cấu hình failover theo exception](https://docs.spring.io/spring-integration/reference/channel/configuration.html)

Ví dụ sau chỉ cho phép chuyển tiếp nếu chuỗi nguyên nhân chứa lỗi tạm thời do ứng dụng định nghĩa:

~~~java
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.support.GenericMessage;

public class SelectiveFailoverDemo {

    static class TemporaryStoreException extends RuntimeException {
        TemporaryStoreException(String message) {
            super(message);
        }
    }

    public static void main(String[] args) {
        DirectChannel orders = new DirectChannel(null);
        orders.setFailoverStrategy(SelectiveFailoverDemo::isTemporaryFailure);

        orders.subscribe(message -> {
            String order = (String) message.getPayload();

            if (order.isBlank()) {
                throw new IllegalArgumentException("Thiếu mã đơn hàng");
            }

            throw new TemporaryStoreException("Kho chính chưa sẵn sàng");
        });

        orders.subscribe(message ->
                System.out.println("Backup nhận " + message.getPayload()));

        orders.send(new GenericMessage<>("ORDER-701"));
    }

    private static boolean isTemporaryFailure(Exception failure) {
        Throwable current = failure;

        while (current != null) {
            if (current instanceof TemporaryStoreException) {
                return true;
            }
            current = current.getCause();
        }

        return false;
    }
}
~~~

Với payload `ORDER-701`, backup được gọi. Nếu thay bằng chuỗi rỗng, lỗi validation khiến predicate trả về `false`; backup không được gọi.

Việc duyệt cause giúp ví dụ dùng được khi lỗi nghiệp vụ nằm trong exception bọc của endpoint. Trong ứng dụng, predicate nên ngắn, ổn định và không tự ném lỗi.

**Failover không phải retry:** ví dụ này thử phương án dự phòng, không chờ một khoảng thời gian rồi gọi lại kho chính. Nó cũng chưa có bộ nhớ để loại kho chính khỏi các lượt gửi tiếp theo.

## 7. Exception nào đến được caller?

Cần phân biệt lỗi tại dispatcher với lỗi quan sát qua API channel.

| Tình huống | Hành vi cần hiểu |
| --- | --- |
| Không có subscriber | Dispatcher phát sinh `MessageDispatchingException`; qua DirectChannel, lỗi này được bọc thành `MessageDeliveryException`. |
| Chỉ một handler và handler lỗi | Lỗi của lần xử lý được truyền ra theo cơ chế bọc lỗi giao thông điệp. |
| Nhiều handler, tắt failover, handler đầu lỗi | Dừng sau lần thử đầu tiên. |
| Nhiều lần thử đều lỗi | Khi danh sách lỗi đã có nhiều phần tử, dispatcher phát sinh `AggregateMessageDeliveryException`. |
| Một handler trước đó lỗi nhưng handler sau thành công | `send()` có thể trả về `true`; lỗi trước đó không trở thành exception cuối cùng của lời gọi gửi. |

Không nên hiểu Javadoc khái quát “mọi handler đều lỗi” thành “luôn nhận AggregateMessageDeliveryException”. Trong triển khai 6.5.0, một lỗi được truyền riêng; nhiều lỗi mới được tổng hợp. [Mã nguồn xử lý lỗi của UnicastingDispatcher](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/UnicastingDispatcher.java)

Lớp channel thực hiện việc bọc lỗi không có subscriber, nên khi kiểm tra lỗi này cần xem cả cause. [Mã nguồn AbstractSubscribableChannel](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/AbstractSubscribableChannel.java)

### Đường đi được tối ưu khi có một handler

`AbstractDispatcher` có đường gọi trực tiếp cho trường hợp chỉ một subscriber. Khi đó không có handler thay thế; không nên dựa vào việc predicate failover được gọi để ghi nhận mọi lỗi xử lý. [Mã nguồn AbstractDispatcher](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/AbstractDispatcher.java)

### errorChannel không tự nhận mọi lỗi đồng bộ

Khi gọi trực tiếp `DirectChannel.send()`, exception xử lý đồng bộ được đưa về caller. Chỉ đặt header `errorChannel` không biến lời gọi này thành cơ chế tự phát ErrorMessage. Gateway hoặc thành phần xử lý bất đồng bộ có cơ chế chuyển lỗi riêng cần cấu hình tương ứng. [Tài liệu Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html)

Ví dụ, producer cần quyết định việc trả lỗi cho API client, ghi nhận thất bại hay gửi sang luồng xử lý lỗi. Không nên bắt rồi bỏ qua exception chỉ để `send()` nhìn có vẻ thành công.

## 8. Hai endpoint dùng chung DirectChannel bằng Java DSL

Trong ứng dụng Spring, endpoint được quản lý bởi container. Hai flow sau đăng ký hai handler vào cùng bean `ordersInput`.

Ví dụ chọn thứ tự cố định, endpoint chính có `order(0)`, endpoint dự phòng có `order(1)`. Cấu hình dưới đây là một lớp Java hoàn chỉnh:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class OrderFlowConfiguration {

    @Bean
    public DirectChannel ordersInput() {
        DirectChannel channel = new DirectChannel(null);
        channel.setFailover(true);
        return channel;
    }

    @Bean
    public IntegrationFlow primaryOrders(DirectChannel ordersInput) {
        return IntegrationFlow.from(ordersInput)
                .handle(String.class, (order, headers) -> {
                    if (Boolean.TRUE.equals(
                            headers.get("simulatePrimaryFailure"))) {
                        throw new IllegalStateException(
                                "Phương án chính tạm thời không xử lý được");
                    }

                    System.out.println("Primary: " + order);
                    return null;
                }, endpoint -> endpoint
                        .id("primaryOrderEndpoint")
                        .order(0)
                        .requiresReply(false))
                .get();
    }

    @Bean
    public IntegrationFlow backupOrders(DirectChannel ordersInput) {
        return IntegrationFlow.from(ordersInput)
                .handle(String.class, (order, headers) -> {
                    System.out.println("Backup: " + order);
                    return null;
                }, endpoint -> endpoint
                        .id("backupOrderEndpoint")
                        .order(1)
                        .requiresReply(false))
                .get();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFlowConfiguration.class)) {

            DirectChannel input =
                    context.getBean("ordersInput", DirectChannel.class);

            input.send(MessageBuilder.withPayload("ORDER-701")
                    .setHeader("simulatePrimaryFailure", true)
                    .build());

            input.send(MessageBuilder.withPayload("ORDER-702")
                    .build());
        }
    }
}
~~~

Ngoài log framework, đầu ra nghiệp vụ dự kiến:

~~~text
Backup: ORDER-701
Primary: ORDER-702
~~~

`IntegrationFlow` đóng vai trò mô tả các thành phần để đăng ký vào context; các overload của `handle()` cho phép cấu hình handler cùng endpoint. [API IntegrationFlow](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/IntegrationFlow.html), [API handle trong DSL](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html)

`order()` đặt thứ tự handler; `requiresReply(false)` cho phép hoàn tất mà không tạo reply. Trong ví dụ, `return null` kết thúc một tác vụ gửi một chiều, không có nghĩa yêu cầu dispatcher thử backup. [API ConsumerEndpointSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/ConsumerEndpointSpec.html)

Các điểm cần quan sát:

- ORDER-701 vào endpoint chính trước; exception kích hoạt thử endpoint dự phòng.
- ORDER-702 lại bắt đầu ở endpoint chính. Failover trước đó không tự chuyển toàn bộ lưu lượng tương lai sang backup.
- Nếu thay `new DirectChannel(null)` bằng `new DirectChannel()`, hai endpoint sẽ cạnh tranh theo round-robin.
- Một gateway gửi lệnh vào `ordersInput` vẫn đi qua cùng cơ chế này. Nếu gateway chờ reply, các nhánh thay thế cần có hợp đồng trả lời phù hợp.

Ví dụ dùng failover rộng để dễ quan sát. Khi áp dụng vào nghiệp vụ thật, thay chính sách bằng predicate như mục 6 nếu chỉ một số lỗi đủ điều kiện chuyển tiếp.

### Phân biệt hai handler thay thế với hai bước nối tiếp

Hai flow cùng bắt đầu từ một DirectChannel là các subscriber cạnh tranh. Muốn biến đổi đơn hàng rồi lưu đơn hàng, hãy nối transformer và service activator thành các bước của một flow.

Tương tự, nếu cần aggregator gom nhiều kết quả, phải chủ động thiết kế các nhánh phát thông điệp và correlation. Đăng ký thêm handler trên DirectChannel không tự tạo đủ các kết quả đó.

## 9. Hệ quả đối với transaction và tác dụng phụ

DirectChannel giữ lời gọi trên thread của producer, nên một transaction đã tồn tại có thể bao quanh phần xử lý ở hai phía channel. Channel không tự tạo transaction. Khả năng tham gia còn phụ thuộc transaction manager và tài nguyên được dùng. [DirectChannel và transaction](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html)

Từ cơ chế failover, có thể suy ra tình huống sau:

~~~text
1. Handler chính gửi lệnh thanh toán tới hệ thống bên ngoài.
2. Hệ thống ngoài đã thu tiền nhưng phản hồi bị mất.
3. Handler chính ném exception do timeout.
4. Dispatcher chuyển cùng yêu cầu sang handler dự phòng.
5. Handler dự phòng gửi một lệnh thanh toán khác.
~~~

Nếu không có khóa chống lặp, khách hàng có thể bị thu tiền hai lần. Một handler hoàn tất bình thường không chứng minh rằng chỉ một handler đã tạo tác dụng phụ.

Thiết kế cho tình huống này cần xác định:

- Khóa nghiệp vụ ổn định, chẳng hạn `paymentRequestId`, được giữ qua các lần thử.
- Cách hệ thống nhận lệnh xử lý yêu cầu lặp.
- Khả năng xác minh kết quả của lần gọi trước khi thực hiện phương án thay thế.
- Ranh giới commit/rollback và những thao tác nằm ngoài transaction cục bộ.

Cũng không thể kết luận “backup thành công thì transaction chắc chắn commit”. Nếu thao tác trước đã đánh dấu transaction là rollback-only, kết quả commit còn chịu trạng thái đó.

### Lỗi ở bước sau có thể kích hoạt thử lại cả nhánh

Giả sử subscriber A mở đầu một nhánh đồng bộ:

~~~text
DirectChannel → handler A → DirectChannel khác → handler ghi dữ liệu
~~~

Nếu bước ghi dữ liệu ném lỗi và lỗi truyền ngược ra lời gọi handler A, dispatcher đầu tiên có thể xem cả lần thử nhánh A là thất bại rồi gọi B. Suy luận này xuất phát từ call stack đồng bộ: phạm vi ảnh hưởng cần xét là toàn bộ phần xử lý trước khi lời gọi subscriber trả về.

Vì thế, failover phù hợp nhất khi các subscriber thực hiện những phương án thay thế có cùng hợp đồng nghiệp vụ và đã tính đến tác dụng phụ.

## 10. Kiểm thử hành vi cần quan sát

Các test dưới đây là tài liệu thực hành dành cho dự án đã có **JUnit Jupiter**. Chúng dùng handler trực tiếp để cô lập hành vi channel, không cần Spring context hay hạ tầng ngoài.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import org.springframework.integration.MessageDispatchingException;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dispatcher.AggregateMessageDeliveryException;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.support.GenericMessage;

import static org.junit.jupiter.api.Assertions.*;

class UnicastingBehaviorTest {

    @Test
    void roundRobinAlternatesAndRunsOnSenderThread() {
        DirectChannel channel = new DirectChannel();
        Thread sender = Thread.currentThread();
        List<String> received = new ArrayList<>();

        channel.subscribe(message -> {
            assertSame(sender, Thread.currentThread());
            received.add("A:" + message.getPayload());
        });

        channel.subscribe(message -> {
            assertSame(sender, Thread.currentThread());
            received.add("B:" + message.getPayload());
        });

        for (int number = 1; number <= 4; number++) {
            assertTrue(channel.send(new GenericMessage<>(number)));
        }

        assertEquals(List.of("A:1", "B:2", "A:3", "B:4"), received);
    }

    @Test
    void failoverCallsBackupAfterPrimaryFails() {
        DirectChannel channel = new DirectChannel(null);
        channel.setFailover(true);
        List<String> attempts = new ArrayList<>();

        channel.subscribe(message -> {
            attempts.add("primary");
            throw new IllegalStateException("Tạm lỗi");
        });

        channel.subscribe(message -> attempts.add("backup"));

        assertTrue(channel.send(new GenericMessage<>("ORDER-701")));
        assertEquals(List.of("primary", "backup"), attempts);
    }

    @Test
    void disablingFailoverKeepsBackupUntouched() {
        DirectChannel channel = new DirectChannel(null);
        channel.setFailover(false);
        AtomicInteger backupCalls = new AtomicInteger();

        channel.subscribe(message -> {
            throw new IllegalStateException("Primary lỗi");
        });

        channel.subscribe(message -> {
            backupCalls.incrementAndGet();
        });

        assertThrows(MessageDeliveryException.class,
                () -> channel.send(new GenericMessage<>("ORDER-701")));

        assertEquals(0, backupCalls.get());
    }

    @Test
    void missingSubscriberIsWrappedByChannel() {
        DirectChannel channel = new DirectChannel();

        MessageDeliveryException failure = assertThrows(
                MessageDeliveryException.class,
                () -> channel.send(new GenericMessage<>("ORDER-701")));

        assertInstanceOf(
                MessageDispatchingException.class, failure.getCause());
    }

    @Test
    void twoFailedAttemptsProduceAnAggregateFailure() {
        DirectChannel channel = new DirectChannel(null);
        channel.setFailover(true);

        channel.subscribe(message -> {
            throw new IllegalStateException("Primary lỗi");
        });

        channel.subscribe(message -> {
            throw new IllegalArgumentException("Backup lỗi");
        });

        assertThrows(AggregateMessageDeliveryException.class,
                () -> channel.send(new GenericMessage<>("ORDER-701")));
    }
}
~~~

Các ví dụ trên trình bày kết quả mong đợi; bài viết không ghi nhận rằng chúng đã được thực thi trong dự án hiện tại.

Với ví dụ Java DSL, nên kiểm tra thêm mức tích hợp:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Primary hoạt động | Primary được gọi, backup không được gọi. |
| Primary lỗi tạm thời | Backup xử lý đúng payload và khóa nghiệp vụ. |
| Primary lỗi validation, dùng predicate | Backup không được gọi và caller nhận lỗi. |
| Endpoint bị dừng | Số subscriber và khả năng nhận message phản ánh đúng vòng đời. |
| Nhiều producer đồng thời | Dữ liệu dùng chung an toàn; không suy diễn thứ tự hoàn tất từ round-robin. |
| Primary đã tạo tác dụng phụ rồi lỗi | Backup không tạo nghiệp vụ lặp ngoài mong muốn. |

Với test đồng bộ này, không cần `Thread.sleep()`: khi `send()` trả về, phần handler đồng bộ đã kết thúc. Nếu kiểm thử ứng dụng có ranh giới bất đồng bộ, dùng tín hiệu hoàn tất phù hợp với ranh giới đó.

## 11. Chọn cấu hình và chẩn đoán

| Nhu cầu | Hướng thiết kế |
| --- | --- |
| Một bước xử lý đồng bộ, một consumer | DirectChannel với một subscriber |
| Nhiều handler thay thế tương đương | DirectChannel với round-robin |
| Primary/backup theo ưu tiên | Tắt load balancing, đặt order rõ ràng, chọn chính sách failover |
| Chọn nghiệp vụ theo payload hoặc header | Router và các channel đầu ra |
| Mọi nhánh đều nhận sự kiện | PublishSubscribeChannel hoặc cấu trúc phát nhiều nhánh |
| Tách việc gửi khỏi xử lý, cần đệm | Cân nhắc QueueChannel hoặc kênh qua broker tùy yêu cầu |
| Giao việc qua executor | ExecutorChannel; kiểm tra lại ranh giới thread và transaction |

Các lựa chọn channel có ngữ nghĩa khác nhau; đặc biệt, UnicastingDispatcher có khả năng dùng executor nhưng **DirectChannel khởi tạo dispatcher không có executor**. Không nên suy ngược rằng mọi UnicastingDispatcher đều luôn đồng bộ. [Mã nguồn UnicastingDispatcher](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/UnicastingDispatcher.java), [mã nguồn DirectChannel](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/DirectChannel.java)

Một số tình huống chẩn đoán thường gặp:

| Quan sát | Điều nên kiểm tra |
| --- | --- |
| Có channel nhưng gửi báo không có subscriber | Endpoint đã được tạo, khởi động và trỏ đúng bean channel chưa? |
| Chỉ một trong hai tác vụ chạy | Hai endpoint có đang cạnh tranh trên DirectChannel thay vì nằm nối tiếp không? |
| Lỗi nhưng backup không chạy | Failover có bị tắt, predicate trả false, hoặc exception đã bị bắt bên trong handler không? |
| Backup chạy nhưng request vẫn lỗi | Backup hoặc phần downstream của nó có tiếp tục ném exception không? |
| Gửi message thành công nhưng không có reply | Flow có tạo reply và hợp đồng gateway có yêu cầu phản hồi không? |
| Thêm subscriber nhưng không tăng tốc | Producer có đang gửi tuần tự trên một thread không? |
| Một đơn hàng được xử lý nhiều lần | Đã kiểm tra failover, retry ở lớp khác và khóa chống lặp chưa? |

`setMaxSubscribers(...)` có thể giới hạn số handler đăng ký; nó không phải giới hạn số request đồng thời hay độ dài hàng đợi. [API DirectChannel](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/channel/DirectChannel.html)

Khi mở rộng `LoadBalancingStrategy`, hợp đồng cốt lõi là tạo iterator từ message và tập handler. Hãy kiểm thử thứ tự ứng viên, tính an toàn khi gửi đồng thời và chính sách khi danh sách subscriber thay đổi. [Mã nguồn LoadBalancingStrategy](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/LoadBalancingStrategy.java)

Một strategy tự viết không tự bổ sung persistence, retry hoặc đảm bảo xử lý đúng một lần. Những yêu cầu đó cần được giải quyết ở các thành phần và ranh giới nghiệp vụ tương ứng.
