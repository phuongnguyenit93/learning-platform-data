# @BridgeFrom

## 1. Mục tiêu và phạm vi

Trong chương **Annotation và XML** của module **SPRING_INTEGRATION_CORE**, `@BridgeFrom` giúp khai báo một cầu nối thông điệp ngay tại bean kênh đích. Bài học tập trung vào cách đọc cấu hình, chọn kênh nguồn, cấu hình poller và kiểm thử việc chuyển tiếp.

Sau bài này, bạn có thể:

- Xác định chính xác kênh vào, kênh ra và endpoint được tạo bởi `@BridgeFrom`.
- Nối các đoạn luồng mà không cần viết thêm phương thức xử lý nghiệp vụ.
- Phân biệt cầu nối nhận thông điệp theo sự kiện với cầu nối đọc thông điệp từ hàng đợi.
- Chuyển cấu hình giữa annotation, XML và Java DSL.
- Giải thích ảnh hưởng của cầu nối tới luồng thực thi và đường đi của lỗi.

Bạn cần biết `Message<?>` chứa payload và headers, `MessageChannel` cung cấp thao tác `send(...)`, còn `PollableChannel` bổ sung `receive(...)`. Các ví dụ dùng Java 17, API thuộc Spring Integration 6.x và JUnit Jupiter. Dependency Spring nên được quản lý bằng BOM hoặc nền tảng Spring Boot tương thích của dự án; bài không yêu cầu đổi phiên bản dependency đang dùng.

## 2. Bài toán: nối hai đoạn luồng thông điệp

Giả sử một thành phần gửi mã đơn hàng vào `incomingOrders`. Một thành phần khác chỉ biết đọc từ `acceptedOrders`. Hai nhóm muốn giữ tên kênh riêng để thể hiện trách nhiệm của từng đoạn luồng.

Nếu thông điệp đã có định dạng phù hợp, bạn có thể dùng một bridge:

```text
Producer
   |
   v
incomingOrders
   |
   v
BridgeHandler
   |
   v
acceptedOrders
   |
   v
Consumer
```

Bridge nhận thông điệp ở một kênh và chuyển tiếp sang kênh khác. Khi cần thay đổi nội dung, bạn đặt transformer ở vị trí thích hợp. Khi cần chọn đường đi theo dữ liệu, bạn dùng router. Bridge phù hợp với đoạn nối không có quy tắc chuyển đổi hay phân nhánh. Spring Integration mô tả thành phần này trong [Messaging Bridge](https://docs.spring.io/spring-integration/reference/bridge.html).

Ví dụ, một router có thể đưa đơn hàng hợp lệ vào `validatedOrders`; bridge tiếp tục nối kênh này với đầu vào của một luồng xử lý dùng chung. Việc xác thực và định tuyến vẫn thuộc các endpoint đứng trước bridge.

## 3. Cách đọc @BridgeFrom

Cấu hình ngắn nhất có dạng:

```java
@Bean
@BridgeFrom("incomingOrders")
public QueueChannel acceptedOrders() {
    return new QueueChannel(20);
}
```

Đọc từ tên annotation: **kênh được khai báo nhận thông điệp từ `incomingOrders` thông qua một bridge**.

| Thành phần | Ý nghĩa trong ví dụ |
| --- | --- |
| `incomingOrders` | Tên bean kênh nguồn, nơi bridge nhận thông điệp |
| `acceptedOrders` | Bean kênh đích do phương thức `@Bean` tạo ra |
| `BridgeHandler` | Handler được hạ tầng annotation đăng ký để chuyển tiếp |
| Consumer endpoint | Thành phần gắn handler với kênh nguồn và quản lý cách nhận thông điệp |

Điểm dễ nhầm là annotation được đặt trên **bean kênh ra**. Giá trị `"incomingOrders"` chỉ về kênh vào.

Phương thức `acceptedOrders()` là phương thức tạo bean. Nó không được gọi lại cho mỗi đơn hàng và không nhận payload làm tham số xử lý nghiệp vụ. Việc chuyển tiếp xảy ra trong endpoint do Spring Integration tạo.

Đây là cách khai báo bridge trên phương thức `@Bean` trả về `MessageChannel` hoặc một kiểu kênh cụ thể. Có thể dùng annotation làm meta-annotation, nhưng không cần xây annotation riêng cho những cấu hình đơn giản. Xem [Creating a Bridge with Annotations](https://docs.spring.io/spring-integration/reference/configuration/meta-annotations.html#creating-a-bridge-with-annotations).

## 4. Điều kiện để cấu hình có hiệu lực

Trong ứng dụng dùng Spring Java Configuration thuần, khai báo `@EnableIntegration` trên một lớp cấu hình được đưa vào `ApplicationContext`:

```java
@Configuration
@EnableIntegration
public class OrderIntegrationConfiguration {
    // Các bean kênh và endpoint.
}
```

Các import tương ứng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.BridgeFrom;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.channel.QueueChannel;
```

Dependency nghiệp vụ cần có `org.springframework.integration:spring-integration-core`. Những bài kiểm thử bên dưới cần JUnit Jupiter và cơ chế chạy JUnit 5 của dự án.

Với Spring Boot, hạ tầng Integration có thể đã được tự cấu hình. Các ví dụ vẫn khai báo `@EnableIntegration` để thể hiện rõ điều kiện khi chạy bằng `AnnotationConfigApplicationContext`.

Hãy khai báo rõ bean kênh nguồn thay vì dựa vào việc tự tạo kênh ở các kiểu cấu hình khác. Nếu nguồn phải là hàng đợi, một bean `DirectChannel` được tạo nhầm sẽ thay đổi cả cách nhận thông điệp lẫn luồng thực thi.

## 5. Kênh nguồn quyết định cách bridge nhận thông điệp

Trong cách dùng thông thường, khi không bật chế độ reactive, kiểu kênh **nguồn** quyết định loại consumer endpoint:

| Kênh nguồn | Consumer endpoint | Cách nhận | Poller |
| --- | --- | --- | --- |
| `DirectChannel` hoặc kênh triển khai `SubscribableChannel` | `EventDrivenConsumer` | Đăng ký handler để kênh gọi khi có thông điệp | Không cấu hình |
| `QueueChannel` hoặc kênh triển khai `PollableChannel` | `PollingConsumer` | Chủ động gọi `receive(...)` theo lịch | Cần poller riêng hoặc default poller hợp lệ |

Kênh đích có thể khác loại kênh nguồn. Chẳng hạn:

```text
DirectChannel nguồn -> bridge -> QueueChannel đích
QueueChannel nguồn  -> poller/bridge -> DirectChannel đích
QueueChannel nguồn  -> poller/bridge -> QueueChannel đích
```

Ở dòng đầu, bridge nhận theo sự kiện dù kênh đích là hàng đợi. Ở hai dòng sau, bridge phải polling vì nguồn là hàng đợi.

Sự phân tách giữa handler và endpoint được giải thích trong [Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html).

## 6. Ví dụ hoàn chỉnh: DirectChannel sang QueueChannel

Tạo lớp `DirectBridgeConfiguration.java`:

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.BridgeFrom;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class DirectBridgeConfiguration {

    @Bean
    public DirectChannel incomingOrders() {
        return new DirectChannel();
    }

    @Bean
    @BridgeFrom("incomingOrders")
    public QueueChannel acceptedOrders() {
        return new QueueChannel(20);
    }
}
```

Luồng hoạt động:

1. Producer gọi `incomingOrders.send(message)`.
2. `DirectChannel` gọi handler của bridge trên luồng của producer.
3. Bridge gửi thông điệp sang `acceptedOrders`.
4. `QueueChannel` giữ thông điệp cho consumer đọc sau.

Vì đầu vào là `DirectChannel`, cấu hình không có `@Poller`. Hàng đợi ở đầu ra không khiến bridge tự chuyển sang polling.

Trong cấu hình này, `send(...)` thành công cho biết thông điệp đã được đưa tới hàng đợi đích. Nó chưa chứng minh consumer phía sau đã xử lý xong đơn hàng.

`QueueChannel(20)` có giới hạn sức chứa. Nếu chưa có consumer và producer tiếp tục gửi, hàng đợi có thể đầy. Hãy tính đến thời gian chờ khi thiết kế đường gửi qua các kênh hữu hạn; timeout của thao tác gửi vào kênh nguồn không mặc nhiên là thời hạn cho toàn bộ chuỗi xử lý phía sau.

### Payload và headers

Bridge không khai báo phép đổi payload. Với luồng minh họa chỉ gồm hai kênh và bridge, bạn mong đợi mã đơn hàng cùng header như `traceId` xuất hiện ở đầu ra.

Không suy rộng điều này thành cam kết mọi header và đối tượng `Message` luôn giữ nguyên trong một luồng lớn. Interceptor, message history, transformer hoặc adapter ở các đoạn khác có thể bổ sung metadata hay tạo thông điệp mới. Kiểm thử nên tập trung vào hợp đồng dữ liệu cần giữ.

## 7. Ví dụ hoàn chỉnh: QueueChannel sang QueueChannel

Một producer có thể đưa thông điệp vào hàng đợi trước, còn bridge rút ra theo lịch. Tạo lớp `QueueBridgeConfiguration.java`:

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.BridgeFrom;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class QueueBridgeConfiguration {

    @Bean
    public QueueChannel bufferedOrders() {
        return new QueueChannel(20);
    }

    @Bean
    @BridgeFrom(
        value = "bufferedOrders",
        poller = @Poller(
            fixedDelay = "100",
            maxMessagesPerPoll = "10",
            receiveTimeout = "0"
        )
    )
    public QueueChannel readyOrders() {
        return new QueueChannel(20);
    }
}
```

Ở đây:

- `bufferedOrders` tách việc tiếp nhận khỏi thời điểm bridge chuyển tiếp.
- Endpoint được tạo là một `PollingConsumer`.
- `fixedDelay = "100"` đặt khoảng nghỉ 100 mili giây sau khi lượt polling trước hoàn tất.
- `maxMessagesPerPoll = "10"` giới hạn số thông điệp được lấy trong một lượt.
- `receiveTimeout = "0"` khiến thao tác đọc trả về ngay nếu nguồn đang rỗng.

Một lượt polling không gom mười đơn hàng thành một thông điệp. Bridge vẫn chuyển tiếp từng `Message`. Nếu cần gom các phần tử thành một kết quả, bạn cần aggregator với quy tắc tương quan và điều kiện phát hành.

Giới hạn mười thông điệp mỗi lượt cũng không bảo đảm tốc độ đúng 100 thông điệp mỗi giây. Thời gian xử lý, lịch thực thi và khả năng nhận ở đầu ra đều ảnh hưởng tốc độ thực tế.

### Đổi đầu ra thành DirectChannel

Nếu `readyOrders` là `DirectChannel`, phần poller vẫn nằm ở annotation trên bean `readyOrders` vì nó điều khiển việc đọc từ `bufferedOrders`:

```java
@Bean
@BridgeFrom(
    value = "bufferedOrders",
    poller = @Poller(
        fixedDelay = "100",
        maxMessagesPerPoll = "10",
        receiveTimeout = "0"
    )
)
public DirectChannel readyOrders() {
    return new DirectChannel();
}
```

Khi dùng biến thể này, phải có consumer đăng ký trên `readyOrders`, chẳng hạn một service activator. Nếu đoạn sau tiếp tục dùng các kênh đồng bộ, nghiệp vụ phía sau chạy trên luồng đang thực thi lượt polling. Chỉ đổi đầu ra sang `DirectChannel` không làm nghiệp vụ quay về luồng producer ban đầu.

## 8. Những thuộc tính cần hiểu

| Thuộc tính | Vai trò | Lưu ý |
| --- | --- | --- |
| `value` | Tên kênh nguồn | Bắt buộc với `@BridgeFrom` |
| `poller` | Cấu hình đọc nguồn pollable | Không dùng cho nguồn `DirectChannel` |
| `autoStartup` | Cho endpoint tự khởi động theo lifecycle | Mặc định `"true"` |
| `phase` | Điều khiển thứ tự lifecycle | Không quy định thứ tự xử lý từng thông điệp |
| `reactive` | Chọn cách tiêu thụ reactive | Loại trừ nhau với `poller` |

Các thuộc tính và điều kiện sử dụng nằm trong [Javadoc của BridgeFrom](https://docs.spring.io/spring-integration/docs/6.0.x/api/org/springframework/integration/annotation/BridgeFrom.html).

### Tách tham số ra cấu hình ứng dụng

Các thuộc tính poller dạng chuỗi hỗ trợ property placeholder:

```java
@Bean
@BridgeFrom(
    value = "bufferedOrders",
    autoStartup = "${orders.bridge.auto-startup:true}",
    poller = @Poller(
        fixedDelay = "${orders.bridge.delay-ms:100}",
        maxMessagesPerPoll = "${orders.bridge.batch-size:10}",
        receiveTimeout = "0"
    )
)
public QueueChannel readyOrders() {
    return new QueueChannel(20);
}
```

Đây là đoạn thay thế cho bean `readyOrders`, không phải một bean bổ sung có cùng tên. Ứng dụng cần có cơ chế phân giải placeholder; Spring Boot cung cấp hạ tầng tương ứng khi dùng cấu hình ứng dụng thông thường.

`orders.bridge.batch-size` chỉ là tên property do ví dụ lựa chọn. Nó điều khiển giới hạn nhận trong một lượt poll, không làm thay đổi kiểu payload.

### Dùng PollerMetadata có tên

Khi cần tùy chọn polling phức tạp như advice hoặc transaction, có thể khai báo một bean `PollerMetadata` rồi tham chiếu:

```java
@BridgeFrom(
    value = "bufferedOrders",
    poller = @Poller("orderBridgePoller")
)
```

Đoạn này giả định `orderBridgePoller` đã được khai báo. Khi dùng `@Poller` theo tên bean, các tùy chọn khác được đặt trên bean metadata, không trộn với `fixedDelay` hay `maxMessagesPerPoll` trong cùng annotation. Xem [Javadoc của Poller](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Poller.html).

Nếu nguồn là `PollableChannel` nhưng bỏ `poller`, framework có thể dùng default poller đã đăng ký. Khi không có poller riêng lẫn default poller, cấu hình không đủ điều kiện khởi tạo endpoint. Các ví dụ khai báo trực tiếp để người đọc nhìn thấy lịch nhận thông điệp.

## 9. Luồng thực thi và lỗi

### 9.1. Đường đồng bộ

Với chuỗi kênh đồng bộ:

```text
producer thread
  -> DirectChannel
  -> bridge
  -> DirectChannel
  -> handler nghiệp vụ
```

Nếu handler phía sau ném ngoại lệ, lỗi có thể lan ngược theo lời gọi `send(...)` tới producer. Việc thêm một bean tên `errorChannel` không tự chuyển mọi ngoại lệ trên đường đồng bộ thành thông điệp lỗi.

### 9.2. Đường có hàng đợi đầu vào

Với nguồn là hàng đợi:

```text
producer thread -> bufferedOrders -> producer tiếp tục
                         |
                  scheduled poller
                         |
                       bridge
                         |
                   consumer phía sau
```

Lỗi xảy ra khi poller đang xử lý không thể quay ngược về lời gọi `send(...)` đã hoàn tất của producer. Hạ tầng polling có thể phát `ErrorMessage` tới kênh lỗi. Thông điệp lỗi mang exception làm payload.

Bạn có thể chỉ định kênh lỗi mặc định riêng cho poller:

```java
@BridgeFrom(
    value = "bufferedOrders",
    poller = @Poller(
        fixedDelay = "100",
        maxMessagesPerPoll = "10",
        receiveTimeout = "0",
        errorChannel = "orderBridgeErrors"
    )
)
```

Khai báo thêm kênh tương ứng trong cấu hình:

```java
@Bean
public QueueChannel orderBridgeErrors() {
    return new QueueChannel(20);
}
```

Hai đoạn trên minh họa phần thay đổi đối với ví dụ polling. Consumer xử lý lỗi phải đọc `orderBridgeErrors` hoặc được nối với kênh đó bằng một endpoint phù hợp; hàng đợi không tự ghi log hay phục hồi đơn hàng.

Header `errorChannel` trên thông điệp có thể quyết định đích lỗi trước kênh mặc định của error handler. Để hiểu cách phân giải và khác biệt với ngoại lệ đồng bộ, xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

### 9.3. Những điều cần thiết kế thêm

Một lỗi được chuyển tới kênh lỗi chưa đồng nghĩa đơn hàng được xử lý lại. Bridge không tự thêm retry, dead-letter queue hay cơ chế chống xử lý trùng.

Với một `QueueChannel` trong bộ nhớ, thông điệp đã được lấy khỏi nguồn trước khi gửi tiếp. Nếu đoạn sau thất bại, không nên giả định thông điệp tự xuất hiện lại ở hàng đợi cũ. Khi cần phục hồi, hãy thiết kế retry, đường xử lý lỗi hoặc cơ chế lưu trữ/giao dịch phù hợp.

Tương tự, chuyển công việc qua hàng đợi không tự truyền transaction gắn với luồng producer sang luồng poller. Yêu cầu như cập nhật trạng thái đơn hàng và phát sự kiện cùng một đơn vị nguyên tử cần thiết kế transaction riêng.

## 10. @BridgeFrom và @BridgeTo khác nhau ở điểm nào?

Hai annotation có thể biểu diễn cùng một cạnh nối, nhưng được đặt ở hai đầu khác nhau:

| Annotation | Đặt trên bean | Giá trị annotation |
| --- | --- | --- |
| `@BridgeFrom("source")` | Kênh đích | Tên kênh nguồn |
| `@BridgeTo("target")` | Kênh nguồn | Tên kênh đích |

Ví dụ sau là **hai phương án thay thế** để biểu diễn `incomingOrders -> acceptedOrders`.

Phương án dùng `@BridgeFrom`:

```java
@Bean
public DirectChannel incomingOrders() {
    return new DirectChannel();
}

@Bean
@BridgeFrom("incomingOrders")
public QueueChannel acceptedOrders() {
    return new QueueChannel(20);
}
```

Phương án dùng `@BridgeTo`:

```java
@Bean
@BridgeTo("acceptedOrders")
public DirectChannel incomingOrders() {
    return new DirectChannel();
}

@Bean
public QueueChannel acceptedOrders() {
    return new QueueChannel(20);
}
```

Phương án thứ hai cần import `org.springframework.integration.annotation.BridgeTo`. Không đặt cả hai annotation cho cùng cạnh nối với mục đích “khai báo đủ hai đầu”; bạn sẽ đăng ký thêm endpoint.

Chọn `@BridgeFrom` khi đọc cấu hình theo đầu vào của kênh đích. Chọn `@BridgeTo` khi muốn đặt thông tin nơi gửi tiếp ngay tại kênh nguồn. Quy tắc chọn polling theo **nguồn** vẫn giữ nguyên. Chi tiết nằm trong [Javadoc của BridgeTo](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/BridgeTo.html).

## 11. Cấu hình XML tương đương

Ví dụ XML dưới đây biểu diễn cùng cấu trúc hàng đợi nguồn, bridge có poller và hàng đợi đích như `QueueBridgeConfiguration`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           https://www.springframework.org/schema/integration/spring-integration.xsd">

    <int:channel id="bufferedOrders">
        <int:queue capacity="20"/>
    </int:channel>

    <int:channel id="readyOrders">
        <int:queue capacity="20"/>
    </int:channel>

    <int:bridge id="ordersBridge"
                input-channel="bufferedOrders"
                output-channel="readyOrders">
        <int:poller fixed-delay="100"
                    max-messages-per-poll="10"
                    receive-timeout="0"/>
    </int:bridge>
</beans>
```

Trong XML, đầu vào và đầu ra xuất hiện trực tiếp trên `<int:bridge>`. Trong annotation, đầu ra được suy ra từ bean mang `@BridgeFrom`.

Nếu nguồn là một kênh subscribable, khai báo bridge XML không có phần poller. XML cần được nạp vào application context thì cấu hình mới có hiệu lực.

Chọn một cơ chế để khai báo cạnh nối này. Khi import XML vào ứng dụng đã có annotation bridge tương ứng, hãy bỏ một trong hai khai báo để tránh tạo thêm consumer.

## 12. Java DSL tương đương

Với Java DSL, giữ hai bean `bufferedOrders` và `readyOrders` nhưng bỏ `@BridgeFrom` khỏi `readyOrders`. Thêm bean flow:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

// Phương thức đặt trong lớp @Configuration có @EnableIntegration.
@Bean
public IntegrationFlow ordersBridgeFlow() {
    return IntegrationFlow.from("bufferedOrders")
        .bridge(endpoint -> endpoint.poller(
            Pollers.fixedDelay(Duration.ofMillis(100))
                .maxMessagesPerPoll(10)
                .receiveTimeout(0)
        ))
        .channel("readyOrders")
        .get();
}
```

Đoạn `.bridge(...)` tạo bước chuyển tiếp; `.channel("readyOrders")` chỉ định nơi nhận kết quả. Poller được cấu hình tại endpoint đọc từ nguồn.

Annotation thuận tiện khi quan hệ nối có thể đọc ngay tại bean kênh. DSL thường dễ theo dõi hơn khi phải nhìn toàn bộ một chuỗi nhiều bước:

```text
gateway -> filter -> transformer -> router -> các luồng xử lý
```

Bridge có thể là đoạn nối trong kiến trúc đó. Nó không cung cấp hợp đồng request-reply như gateway, không thực hiện điều kiện lọc và không thay thế quy tắc tương quan của aggregator.

## 13. Kiểm thử hợp đồng chuyển tiếp

Hai cấu hình ở phần 6 và phần 7 có thể dùng trực tiếp trong một bài kiểm thử JUnit 5. Tạo `BridgeFromTest.java` trong cùng package:

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BridgeFromTest {

    @Test
    void forwardsFromDirectChannelAndKeepsBusinessHeader() {
        try (var context = new AnnotationConfigApplicationContext(
                DirectBridgeConfiguration.class)) {

            MessageChannel input = context.getBean(
                "incomingOrders", MessageChannel.class);
            QueueChannel output = context.getBean(
                "acceptedOrders", QueueChannel.class);

            Message<String> sent = MessageBuilder
                .withPayload("ORDER-1001")
                .setHeader("traceId", "trace-direct-1001")
                .build();

            assertTrue(input.send(sent));

            Message<?> received = output.receive(0);
            assertNotNull(received);
            assertEquals("ORDER-1001", received.getPayload());
            assertEquals(
                "trace-direct-1001",
                received.getHeaders().get("traceId")
            );
        }
    }

    @Test
    void forwardsFromQueueUsingConfiguredPoller() {
        try (var context = new AnnotationConfigApplicationContext(
                QueueBridgeConfiguration.class)) {

            MessageChannel input = context.getBean(
                "bufferedOrders", MessageChannel.class);
            QueueChannel output = context.getBean(
                "readyOrders", QueueChannel.class);

            Message<String> sent = MessageBuilder
                .withPayload("ORDER-2001")
                .setHeader("traceId", "trace-queue-2001")
                .build();

            assertTrue(input.send(sent, 1_000));

            Message<?> received = output.receive(3_000);
            assertNotNull(received);
            assertEquals("ORDER-2001", received.getPayload());
            assertEquals(
                "trace-queue-2001",
                received.getHeaders().get("traceId")
            );
        }
    }
}
```

Bài kiểm thử đầu đọc bằng `receive(0)` vì bridge chạy ngay trên đường gửi đồng bộ và đích đang trống. Bài kiểm thử thứ hai chờ tối đa ba giây vì lịch polling độc lập với producer.

Không dùng `Thread.sleep(...)` để đoán thời điểm hoàn tất. `receive(timeout)` vừa chờ dữ liệu cần kiểm tra, vừa giới hạn thời gian chờ khi cấu hình có lỗi. Đóng context bằng `try-with-resources` giúp dừng các tài nguyên polling sau bài kiểm thử.

Các assertion chứng minh payload và header nghiệp vụ tới được đích trong hai cấu hình tối giản. Chúng chưa chứng minh năng lực chịu tải, độ bền dữ liệu, retry hay tính nguyên tử của một luồng đơn hàng thực tế. Mốc ba giây là thời gian chờ kiểm thử, không phải cam kết độ trễ của ứng dụng.

## 14. Những lỗi cấu hình thường gặp

| Biểu hiện | Điều cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Không có endpoint chuyển tiếp | Lớp cấu hình đã được nạp và hạ tầng annotation đã bật chưa? | Kiểm tra đăng ký cấu hình và `@EnableIntegration`/auto-configuration |
| Khởi tạo thất bại vì kênh nguồn | `value` có đúng tên bean và bean có phải kênh không? | Khai báo rõ kênh nguồn và sửa tên tham chiếu |
| Nguồn queue nhưng endpoint không khởi tạo được | Có poller riêng hoặc default poller không? | Khai báo poller phù hợp |
| Cấu hình báo không thể dùng poller | Nguồn thực tế có phải `DirectChannel` không? | Bỏ poller hoặc dùng đúng loại nguồn theo thiết kế |
| Gửi tới `DirectChannel` bị lỗi không có subscriber | Consumer ở đầu ra đã được đăng ký và khởi động chưa? | Bổ sung hoặc khởi động endpoint tiêu thụ |
| Thông điệp không đi hết qua bridge | Nguồn có consumer khác không? Endpoint có đang chạy không? | Kiểm tra đồ thị luồng và lifecycle |
| Luồng gửi chậm hoặc bị chặn | Hàng đợi đích có đầy không? Handler đồng bộ có chậm không? | Kiểm tra sức chứa, consumer và thời gian chờ |
| Có lỗi sau khi producer đã gửi thành công | Có ranh giới hàng đợi hoặc executor không? | Theo dõi đường lỗi của đoạn chạy bất đồng bộ |

### autoStartup và phase

`autoStartup = "false"` dừng việc tự khởi động **endpoint bridge** khi context khởi động. Kênh đích vẫn là bean được tạo bình thường.

Nếu nguồn là hàng đợi, thông điệp có thể nằm ở đó trong khi bridge chưa chạy. Nếu nguồn là `DirectChannel` và không còn subscriber nào khác, gửi vào kênh có thể thất bại vì không có handler.

Khi cần điều khiển vận hành, phải lấy đúng endpoint lifecycle để gọi `start()`/`stop()` hoặc sử dụng cơ chế quản lý phù hợp. Gọi `start()` trên đối tượng kênh không thay thế việc khởi động bridge.

`phase` điều chỉnh thứ tự bắt đầu và dừng của các thành phần lifecycle. Nó không sắp thứ tự đơn hàng và không làm thông điệp ở kênh ưu tiên thấp chờ thông điệp ở kênh khác.

### Consumer cạnh tranh

`DirectChannel` có ngữ nghĩa point-to-point. Nếu bridge và một service activator cùng đăng ký trên nguồn này, không nên kỳ vọng cả hai đều nhận mọi thông điệp. `QueueChannel` cũng phân phối một thông điệp cho một bên đọc; bridge có thể cạnh tranh với consumer khác.

Khi yêu cầu là phát cùng một sự kiện cho nhiều nhánh, hãy thiết kế `PublishSubscribeChannel` hoặc router theo đúng hợp đồng. Đặc tính phân phối và chặn của các kênh được mô tả tại [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

### Tránh vòng lặp

Không nối bridge từ một kênh về chính nó, hoặc tạo chu trình nhiều kênh không có điều kiện kết thúc:

```text
channelA -> bridge -> channelB -> bridge -> channelA
```

Với các kênh đồng bộ, chu trình có thể liên tục gọi lồng nhau. Với hàng đợi, nó có thể làm cùng dữ liệu quay vòng và tiêu tốn tài nguyên. Khi rà cấu hình, hãy vẽ các cạnh theo đúng chiều trước khi phân tích business handler.

## 15. Áp dụng vào một luồng thực tế

Giả sử hệ thống tiếp nhận đơn hàng theo chuỗi:

```text
gateway
  -> kiểm tra dữ liệu
  -> chuẩn hóa đơn hàng
  -> router phân loại
  -> bufferedOrders
  -> bridge có poller
  -> readyOrders
  -> handler nghiệp vụ
```

Trong thiết kế này, `@BridgeFrom` thích hợp nếu bạn muốn kênh `readyOrders` khai báo rõ nó nhận thông điệp từ `bufferedOrders`. Poller thể hiện chính sách lấy dữ liệu khỏi vùng đệm, còn handler phía sau tập trung vào xử lý đơn hàng.

Trước khi dùng mô hình đó, xác định các yêu cầu cụ thể:

- Nếu đơn hàng phải tồn tại qua lần khởi động lại, `QueueChannel` trong bộ nhớ của ví dụ chưa đáp ứng yêu cầu lưu bền.
- Nếu producer cần biết kết quả nghiệp vụ, việc gửi vào hàng đợi cần được kết hợp với hợp đồng phản hồi phù hợp.
- Nếu cần gửi lại khi thất bại, xác định nơi lưu dữ liệu gốc, chính sách retry và điểm kết thúc xử lý lỗi.
- Nếu cùng sự kiện phải đi tới nhiều nhóm xử lý, chọn cấu trúc phân phối phù hợp trước khi thêm bridge.

Với một khai báo `@BridgeFrom`, cách đọc nhất quán là: **lấy thông điệp từ kênh được chỉ định trong annotation, để endpoint nhận theo cơ chế của nguồn, rồi dùng bridge chuyển tiếp sang bean kênh mang annotation**.
