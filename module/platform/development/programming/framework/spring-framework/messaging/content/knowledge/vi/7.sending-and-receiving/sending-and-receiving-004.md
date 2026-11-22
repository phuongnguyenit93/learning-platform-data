# GenericMessagingTemplate và thao tác trên MessageChannel

Trong Spring Messaging, MessageChannel là abstraction để gửi Message từ producer tới nơi nhận. Khi mã ứng dụng cần thao tác thuận tiện hơn với channel, Spring cung cấp GenericMessagingTemplate. Template này gom các thao tác gửi, nhận, request/reply, chuyển đổi payload và cấu hình timeout vào một API nhất quán.

Bài này tập trung vào cách dùng GenericMessagingTemplate với MessageChannel, phân biệt channel có subscriber với channel có hàng đợi, hiểu kết quả và timeout của từng thao tác, rồi xây dựng một chương trình Java nhỏ có thể chạy bằng Maven.

## 1. Vì sao cần GenericMessagingTemplate?

Một ứng dụng có thể gọi trực tiếp phương thức send() trên MessageChannel:

~~~java
boolean sent = channel.send(message);
~~~

Cách này phù hợp khi chỉ cần gửi một Message. Tuy nhiên, mã ứng dụng phải tự xử lý kết quả boolean, tự chọn cách nhận thông điệp, tự tổ chức request/reply và tự quản lý các khoảng chờ.

GenericMessagingTemplate cung cấp một lớp thao tác ở mức cao hơn:

- Gửi Message tới một MessageChannel.
- Nhận Message từ channel có khả năng polling.
- Gửi request và chờ reply.
- Chuyển đổi payload thành Message hoặc chuyển payload của Message về kiểu Java.
- Cấu hình timeout gửi và nhận.
- Giải quyết tên destination thành MessageChannel khi được cấu hình với Spring BeanFactory hoặc DestinationResolver.

Template không phải broker và cũng không tự tạo ra một hạ tầng lưu trữ thông điệp. Nó gọi các thao tác trên channel mà ứng dụng đã cung cấp. Cách gửi, phân phối, lưu đệm và thực thi vẫn do implementation của channel quyết định.

## 2. GenericMessagingTemplate nằm ở đâu?

Lớp GenericMessagingTemplate thuộc package:

~~~java
org.springframework.messaging.core.GenericMessagingTemplate
~~~

Nó làm việc trực tiếp với abstraction MessageChannel của Spring Messaging. Trong hệ sinh thái Spring, các channel cụ thể như DirectChannel và QueueChannel thường được cung cấp bởi Spring Integration.

Có thể nhìn các lớp theo vai trò:

| Thành phần | Vai trò |
|---|---|
| Message<T> | Đóng gói payload và headers |
| MessageChannel | Hợp đồng gửi Message |
| PollableChannel | Channel cho phép consumer chủ động nhận Message |
| SubscribableChannel | Channel cho phép handler đăng ký nhận Message |
| GenericMessagingTemplate | Cung cấp các thao tác gửi, nhận và request/reply trên channel |
| Spring Integration | Cung cấp nhiều implementation channel và endpoint tích hợp |

Một điểm cần nhớ: MessageChannel chỉ định nghĩa việc gửi. Không phải MessageChannel nào cũng hỗ trợ nhận. GenericMessagingTemplate.receive() cần một PollableChannel; nếu truyền DirectChannel, thao tác nhận sẽ thất bại vì DirectChannel là SubscribableChannel.

## 3. Các thao tác chính

### 3.1. Gửi một Message bằng send()

Ví dụ:

~~~java
Message<String> message = MessageBuilder
        .withPayload("Order created")
        .setHeader("eventType", "order.created")
        .build();

template.send(channel, message);
~~~

send() nhận channel đích và Message đã được tạo sẵn. Phương thức của template trả về void. Bên dưới, template gọi MessageChannel.send(...). Nếu channel trả về false, template phát sinh MessageDeliveryException để thông báo gửi thất bại.

Điều này khác với gọi trực tiếp channel.send(message), vốn trả về boolean cho caller tự quyết định cách xử lý.

Nên dùng send() khi payload và headers đã được đóng gói thành Message, và ứng dụng muốn tập trung vào thao tác gửi thay vì lặp lại phần kiểm tra kết quả của channel.

### 3.2. Gửi payload bằng convertAndSend()

Khi chưa có Message, có thể gửi trực tiếp payload:

~~~java
template.convertAndSend(channel, "Order created");
~~~

Template sử dụng MessageConverter để tạo Message từ payload. Có thể cung cấp thêm headers:

~~~java
Map<String, Object> headers = Map.of(
        "eventType", "order.created",
        "source", "checkout-service"
);

template.convertAndSend(channel, "Order created", headers);
~~~

Cách này thuận tiện khi producer làm việc với DTO hoặc payload nghiệp vụ và không cần tự gọi MessageBuilder. Nếu cần kiểm soát đầy đủ Message, hãy dùng send() với Message được tạo trước.

### 3.3. Nhận Message bằng receive()

~~~java
Message<?> message = template.receive(channel);
~~~

receive() dùng để lấy một Message từ channel. Channel phải triển khai PollableChannel, ví dụ QueueChannel hoặc PriorityChannel.

Nếu không có Message trong khoảng thời gian chờ, phương thức có thể trả về null. Vì vậy, luôn kiểm tra null trước khi truy cập payload.

~~~java
Message<?> message = template.receive(queueChannel);

if (message != null) {
    System.out.println(message.getPayload());
}
~~~

DirectChannel không hỗ trợ thao tác nhận kiểu polling. Handler của DirectChannel được đăng ký trước và được gọi khi producer gửi Message.

### 3.4. Nhận payload bằng receiveAndConvert()

Nếu chỉ cần payload, có thể dùng:

~~~java
String payload = template.receiveAndConvert(queueChannel, String.class);
~~~

Phương thức nhận Message rồi dùng MessageConverter để chuyển payload sang kiểu yêu cầu. Nếu không có Message trước khi hết timeout, kết quả là null.

Kiểu đích cần tương thích với payload thực tế hoặc có converter phù hợp. Nếu không thể chuyển đổi, framework có thể phát sinh MessageConversionException.

### 3.5. Request/reply bằng sendAndReceive()

sendAndReceive() gửi request tới một channel và chờ một Message phản hồi:

~~~java
Message<?> reply = template.sendAndReceive(
        requestChannel,
        MessageBuilder.withPayload("Create order #1024").build()
);
~~~

Để làm việc này, GenericMessagingTemplate tạo một temporary reply channel, gắn channel đó vào header replyChannel của request, rồi gửi request. Handler phía nhận lấy replyChannel từ header và gửi reply trở lại. Template chờ một phản hồi trên temporary channel.

Nếu hết thời gian chờ mà không có reply, sendAndReceive() trả về null. Nếu reply đến sau khi bên gọi đã timeout hoặc đã nhận phản hồi, template xử lý tình huống late reply theo cấu hình.

Điểm thuận tiện là caller không phải tự tạo QueueChannel tạm thời cho mỗi lần request/reply. Tuy vậy, handler vẫn phải gửi phản hồi đúng vào replyChannel được truyền trong request.

Có thể dùng convertSendAndReceive() nếu muốn gửi một payload và nhận về payload đã chuyển đổi:

~~~java
String reply = template.convertSendAndReceive(
        requestChannel,
        "Create order #1024",
        String.class
);
~~~

Nếu hệ thống dùng kiểu request và response khác nhau, cần converter tương ứng hoặc sử dụng sendAndReceive() với Message tường minh.

## 4. Phân biệt các loại channel khi thao tác với template

GenericMessagingTemplate làm việc với nhiều implementation MessageChannel, nhưng mỗi loại có khả năng khác nhau.

| Channel | Interface chính | Gửi | Nhận bằng receive() | Cách hoạt động |
|---|---|---|---|---|
| DirectChannel | SubscribableChannel | Có | Không | Chuyển tới handler đã đăng ký trong luồng gửi |
| PublishSubscribeChannel | SubscribableChannel | Có | Không | Phát tới các subscriber |
| QueueChannel | PollableChannel | Có | Có | Đưa Message vào hàng đợi để consumer lấy |
| PriorityChannel | PollableChannel | Có | Có | Nhận theo thứ tự ưu tiên |

Ví dụ:

~~~java
DirectChannel direct = new DirectChannel();
direct.subscribe(message -> System.out.println(message.getPayload()));

QueueChannel queue = new QueueChannel(20);
~~~

Với DirectChannel, khi gọi template.send(), handler được gọi trực tiếp theo cách dispatch của channel. Với QueueChannel, send() đưa Message vào hàng đợi; một consumer khác có thể gọi template.receive() để lấy nó sau.

QueueChannel mặc định lưu dữ liệu trong bộ nhớ. Khi ứng dụng dừng bất thường, các Message chưa được xử lý có thể mất. Nếu cần lưu bền vững, phải cấu hình MessageStore phù hợp hoặc dùng broker/hạ tầng messaging có khả năng lưu trữ bền vững.

Đặt capacity cho QueueChannel là cách kiểm soát lượng Message có thể chờ trong bộ nhớ. Khi hàng đợi đầy, send() có thể chờ theo timeout hoặc thất bại theo implementation và cấu hình.

## 5. Timeout gửi và nhận

GenericMessagingTemplate có hai cấu hình timeout chính:

~~~java
template.setSendTimeout(1000);
template.setReceiveTimeout(2000);
~~~

Các giá trị tính bằng mili giây.

**Send timeout** giới hạn thời gian channel được phép nhận Message. Nó hữu ích với channel có khả năng chờ, chẳng hạn QueueChannel có capacity hữu hạn và đang đầy.

**Receive timeout** giới hạn thời gian chờ Message khi gọi receive() hoặc chờ reply trong sendAndReceive().

Mặc định, hai timeout có giá trị -1, nghĩa là không đặt giới hạn thời gian và thao tác dùng dạng send()/receive() không truyền timeout. Điều này có thể khiến một thread chờ vô hạn nếu channel không nhận được Message hoặc request không có reply.

Nên cấu hình timeout tường minh khi thao tác có thể chờ tài nguyên hoặc phản hồi từ thành phần khác.

### Timeout theo từng Message

Ngoài cấu hình mặc định trên template, có thể ghi đè timeout cho từng Message bằng các header mặc định:

- sendTimeout: ghi đè timeout gửi.
- receiveTimeout: ghi đè timeout nhận khi dùng sendAndReceive().

Ví dụ:

~~~java
Message<String> request = MessageBuilder
        .withPayload("Check order status")
        .setHeader("sendTimeout", 500)
        .setHeader("receiveTimeout", 1500)
        .build();

Message<?> reply = template.sendAndReceive(requestChannel, request);
~~~

Tên header có thể được tùy chỉnh bằng setSendTimeoutHeader() và setReceiveTimeoutHeader(). Template loại bỏ các header timeout này trước khi chuyển Message xuống channel, tránh để metadata điều khiển nội bộ bị phát tán như dữ liệu nghiệp vụ.

Nếu send thất bại do hết timeout hoặc channel từ chối Message, template phát sinh MessageDeliveryException. Với receive(), hết timeout thường được biểu diễn bằng kết quả null. Với sendAndReceive(), không có reply trong thời hạn cũng được biểu diễn bằng null.

### Reply đến trễ

Trong request/reply, service có thể trả lời sau khi client đã timeout. GenericMessagingTemplate có cấu hình:

~~~java
template.setThrowExceptionOnLateReply(true);
~~~

Mặc định là false: framework ghi log cảnh báo khi reply không còn người nhận đang chờ. Nếu bật true, thao tác gửi reply vào temporary channel còn phát sinh MessageDeliveryException.

Cấu hình này giúp phát hiện luồng phản hồi đến quá muộn. Nó không hủy nghiệp vụ đang chạy ở service và cũng không chứng minh request đã thất bại. Ứng dụng vẫn cần thiết kế timeout, retry và idempotency phù hợp.

## 6. Ví dụ hoàn chỉnh: gửi, nhận và request/reply

Ví dụ sau dùng Java 17, Spring Integration 6.4.6 và GenericMessagingTemplate. Chương trình minh họa ba thao tác:

1. Gửi Message vào DirectChannel.
2. Gửi và nhận Message qua QueueChannel.
3. Gửi request và nhận reply bằng sendAndReceive().

Ví dụ chạy trong một tiến trình, không cần broker hay Spring ApplicationContext.

Cấu trúc dự án:

~~~text
generic-template-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── GenericTemplateDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>generic-template-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.4.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/GenericTemplateDemo.java

~~~java
package demo;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.core.GenericMessagingTemplate;
import org.springframework.messaging.support.MessageBuilder;

public class GenericTemplateDemo {

    public static void main(String[] args) {
        GenericMessagingTemplate template = new GenericMessagingTemplate();
        template.setSendTimeout(1000);
        template.setReceiveTimeout(1000);

        // 1. Send to a DirectChannel.
        DirectChannel eventChannel = new DirectChannel();
        eventChannel.subscribe(message ->
                System.out.println("[send] event = " + message.getPayload()));

        template.send(
                eventChannel,
                MessageBuilder.withPayload("OrderCreated").build()
        );

        // 2. Send to and receive from a QueueChannel.
        QueueChannel inbox = new QueueChannel(10);

        template.send(
                inbox,
                MessageBuilder.withPayload("Reconcile #42").build()
        );

        Message<?> received = template.receive(inbox);

        if (received == null) {
            throw new IllegalStateException("No message received from inbox");
        }

        System.out.println("[receive] payload = " + received.getPayload());

        // 3. Request/reply with a temporary reply channel.
        DirectChannel requestChannel = new DirectChannel();

        requestChannel.subscribe(request -> {
            Object replyChannelValue =
                    request.getHeaders().get("replyChannel");

            if (!(replyChannelValue instanceof MessageChannel replyChannel)) {
                throw new IllegalStateException("Missing replyChannel header");
            }

            System.out.println("[service] request = " + request.getPayload());

            Message<String> reply = MessageBuilder
                    .withPayload("Accepted: " + request.getPayload())
                    .build();

            if (!replyChannel.send(reply)) {
                throw new IllegalStateException("Reply could not be delivered");
            }
        });

        Message<?> reply = template.sendAndReceive(
                requestChannel,
                MessageBuilder.withPayload("Create order #1024").build()
        );

        if (reply == null) {
            throw new IllegalStateException("Timed out waiting for reply");
        }

        System.out.println("[reply] payload = " + reply.getPayload());
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.GenericTemplateDemo
~~~

Output:

~~~text
[send] event = OrderCreated
[receive] payload = Reconcile #42
[service] request = Create order #1024
[reply] payload = Accepted: Create order #1024
~~~

### Phân tích chương trình

**Phần 1 — Gửi vào DirectChannel**

Producer tạo DirectChannel và đăng ký một subscriber. template.send() chuyển Message tới channel. Handler chạy trong luồng gửi và in payload.

**Phần 2 — Gửi và nhận từ QueueChannel**

QueueChannel lưu Message trong hàng đợi. template.send() đưa Message vào queue, sau đó template.receive() lấy Message ra. Vì QueueChannel triển khai PollableChannel, thao tác nhận được hỗ trợ.

**Phần 3 — Request/reply**

GenericMessagingTemplate.sendAndReceive() tự tạo temporary reply channel và gắn vào header replyChannel của request. Handler lấy channel này, tạo Message phản hồi và gửi về. Template chờ phản hồi, sau đó trả Message cho caller.

Trong ví dụ, DirectChannel gọi handler đồng bộ, vì vậy service xử lý request và gửi reply ngay trong lần gọi sendAndReceive(). Với một channel hoặc endpoint bất đồng bộ, template có thể phải chờ đến khi reply xuất hiện hoặc hết receive timeout.

## 7. Dùng tên channel thay vì truyền trực tiếp object

GenericMessagingTemplate cũng hỗ trợ thao tác với destination name. Khi được cấu hình trong Spring BeanFactory, nó dùng BeanFactoryMessageChannelDestinationResolver để tìm MessageChannel theo tên bean.

Ví dụ cấu hình channel:

~~~java
@Configuration
public class MessagingConfiguration {

    @Bean
    public MessageChannel orderChannel() {
        return new DirectChannel();
    }

    @Bean
    public GenericMessagingTemplate messagingTemplate() {
        GenericMessagingTemplate template = new GenericMessagingTemplate();
        template.setSendTimeout(1000);
        template.setReceiveTimeout(2000);
        return template;
    }
}
~~~

Khi template là Spring bean, Spring gọi callback BeanFactoryAware và cung cấp BeanFactory để giải quyết tên channel.

Mã ứng dụng có thể gửi theo tên:

~~~java
template.convertAndSend("orderChannel", "Order created");
~~~

Tên destination phải trùng với tên bean MessageChannel đã đăng ký. Nếu không tìm thấy channel, destination resolver phát sinh lỗi giải quyết destination.

Truyền trực tiếp object MessageChannel vẫn phù hợp khi ứng dụng đã có sẵn tham chiếu channel và muốn compiler kiểm tra kiểu ở thời điểm biên dịch.

## 8. Xử lý lỗi và các trường hợp cần chú ý

### Channel từ chối Message

Nếu MessageChannel.send() trả về false, GenericMessagingTemplate.send() phát sinh MessageDeliveryException. Caller nên xử lý lỗi theo chính sách của ứng dụng, chẳng hạn ghi log, retry có giới hạn hoặc chuyển sang luồng lỗi.

Không nên giả định send() luôn thành công chỉ vì channel object tồn tại.

### Nhận trên sai loại channel

receive() cần PollableChannel. Nếu truyền DirectChannel hoặc một SubscribableChannel khác, template phát sinh IllegalStateException vì channel đó không hỗ trợ thao tác nhận.

Hãy kiểm tra loại channel theo đúng mô hình giao tiếp: push qua subscriber hay pull từ queue.

### Không có Message trước timeout

receive() trả về null nếu không có Message trong khoảng chờ. sendAndReceive() cũng có thể trả về null nếu handler không gửi reply đúng hạn.

Luôn kiểm tra null trước khi dùng payload. Đừng chuyển null thành lỗi nghiệp vụ chung nếu nguyên nhân thực tế chỉ là hết thời gian chờ.

### Handler phát sinh exception

Với DirectChannel, handler được gọi trong luồng gửi. Exception từ handler có thể truyền ngược về caller của send(). Với channel dùng executor, handler có thể chạy trên thread khác sau khi lời gọi gửi đã hoàn tất; khi đó lỗi cần được định tuyến và quan sát qua cơ chế error handling phù hợp.

Không nên giả định mọi channel đều có cùng ngữ nghĩa exception.

### Hàng đợi đầy

QueueChannel có capacity giới hạn có thể từ chối hoặc chờ khi không còn chỗ, tùy timeout và implementation. Cấu hình send timeout để tránh producer chờ vô hạn. Theo dõi queue depth và tốc độ consumer để phát hiện backlog.

### Reply đến muộn hoặc trùng

sendAndReceive() chờ một reply cho một lần gọi. Nếu phản hồi đến sau timeout, người nhận tạm thời có thể đã kết thúc chờ. Dùng setThrowExceptionOnLateReply(true) khi muốn biến tình huống gửi reply muộn thành MessageDeliveryException ở phía gửi reply; mặc định framework chỉ ghi cảnh báo.

Nếu nghiệp vụ cần retry, hãy bảo đảm consumer có tính idempotent để một request được gửi lại không gây tác động lặp.

## 9. Thực hành tốt khi dùng GenericMessagingTemplate

1. **Tái sử dụng template đã cấu hình:** tránh tạo template mới cho mỗi Message nếu cấu hình timeout và converter giống nhau.
2. **Đặt timeout có chủ đích:** send timeout bảo vệ thao tác gửi; receive timeout bảo vệ thao tác chờ Message hoặc reply.
3. **Chọn đúng loại channel:** dùng SubscribableChannel cho handler đăng ký nhận và PollableChannel cho consumer polling.
4. **Kiểm tra kết quả receive:** kết quả null là một trường hợp bình thường khi hết timeout.
5. **Xử lý MessageDeliveryException:** phân biệt channel từ chối gửi với lỗi nghiệp vụ ở consumer.
6. **Giữ payload và headers rõ ràng:** dùng payload cho dữ liệu nghiệp vụ, headers cho metadata và thông tin điều khiển.
7. **Không xem QueueChannel trong bộ nhớ là lưu trữ bền vững:** dùng message store hoặc broker khi cần bảo toàn dữ liệu qua sự cố.
8. **Quan sát request/reply:** ghi nhận correlation ID, thời gian chờ và reply timeout để tìm nguyên nhân chậm.
9. **Quản lý late reply:** chọn chính sách log hoặc exception phù hợp và xử lý reply đến trễ.
10. **Không che giấu tính đồng bộ của channel:** DirectChannel có thể gọi handler ngay trong luồng gửi; ExecutorChannel có thể thay đổi thread và ngữ nghĩa transaction.

## 10. Những nhầm lẫn phổ biến

**GenericMessagingTemplate là message broker:** sai. Nó là API tiện ích thao tác trên MessageChannel; broker là hạ tầng vận chuyển/lưu trữ độc lập.

**send() của template trả về boolean:** sai. Phương thức send() của GenericMessagingTemplate trả về void. Nếu channel từ chối Message, template phát sinh exception.

**Mọi MessageChannel đều nhận được Message:** sai. receive() yêu cầu PollableChannel; DirectChannel chỉ hỗ trợ subscriber nhận khi gửi.

**Timeout gửi và timeout nhận giống nhau:** sai. send timeout áp dụng khi đưa Message vào channel; receive timeout áp dụng khi chờ Message hoặc reply.

**sendAndReceive() cần caller tự tạo reply channel:** không cần trong trường hợp thông thường. Template tự tạo temporary reply channel và gắn vào request.

**sendAndReceive() luôn trả về Message:** sai. Nếu không nhận được reply trong receive timeout, kết quả có thể là null.

**QueueChannel lưu dữ liệu bền vững:** sai. QueueChannel mặc định dùng bộ nhớ trong tiến trình. Cần persistent MessageStore hoặc broker nếu yêu cầu độ bền.

**Gửi thành công đồng nghĩa xử lý nghiệp vụ thành công:** sai. Gửi thành công chỉ thể hiện channel chấp nhận/chuyển Message theo hợp đồng của nó. Kết quả nghiệp vụ cần được xác nhận riêng.

## 11. Ghi nhớ

- GenericMessagingTemplate là template của Spring Messaging dùng để gửi, nhận và request/reply qua MessageChannel.
- send() gửi một Message; convertAndSend() tạo Message từ payload.
- receive() và receiveAndConvert() yêu cầu PollableChannel như QueueChannel.
- sendAndReceive() tạo temporary reply channel, gửi request và chờ một reply.
- send() của template trả về void và phát MessageDeliveryException khi channel từ chối gửi.
- receive() và sendAndReceive() có thể trả về null khi hết receive timeout.
- Send timeout và receive timeout tính bằng mili giây; mặc định -1 là không giới hạn thời gian.
- DirectChannel phù hợp với dispatch tới subscriber; QueueChannel phù hợp với mô hình gửi vào hàng đợi rồi polling.
- GenericMessagingTemplate không thay thế broker, transaction hoặc cơ chế xác nhận nghiệp vụ.
