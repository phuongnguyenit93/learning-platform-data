# send, receive và sendAndReceive

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt thao tác gửi một chiều với thao tác gửi request và chờ reply.
- Hiểu vai trò của MessageChannel.send(), PollableChannel.receive() và các phương thức trên MessagingTemplate.
- Chọn đúng channel cho send, receive và request-reply.
- Giải thích replyChannel được dùng như thế nào để ghép phản hồi với request.
- Cấu hình send timeout và receive timeout, đồng thời xử lý trường hợp không có reply.
- Phân biệt API mức thấp của Spring Messaging với template tiện ích của Spring Integration.
- Tránh nhầm việc channel chấp nhận thông điệp với việc consumer hoàn tất nghiệp vụ.

## 1. Bức tranh tổng quan

Trong Spring Messaging, producer tạo Message và gửi nó tới một MessageChannel. Consumer có thể nhận thông điệp bằng cách polling nếu channel hỗ trợ PollableChannel, hoặc được channel gọi qua MessageHandler nếu channel hỗ trợ SubscribableChannel.

Ba thao tác send, receive và sendAndReceive thể hiện ba kiểu trao đổi:

| Thao tác | Ý nghĩa | Kết quả thường nhận được |
|---|---|---|
| send | Gửi một Message tới channel | Xác nhận gửi hoặc exception tùy API được gọi |
| receive | Lấy một Message từ channel có thể polling | Message hoặc null khi hết thời gian chờ |
| sendAndReceive | Gửi request và chờ response tương ứng | Reply Message hoặc null khi hết timeout |

Có hai lớp API cần phân biệt:

- **API channel mức thấp:** MessageChannel.send() và PollableChannel.receive(). Đây là hợp đồng cốt lõi của Spring Messaging.
- **Messaging template:** cung cấp các thao tác thuận tiện để gửi, nhận, chuyển đổi payload và thực hiện request-reply. Spring Framework có GenericMessagingTemplate trong package org.springframework.messaging.core. Spring Integration cung cấp MessagingTemplate trong package org.springframework.integration.core, kế thừa GenericMessagingTemplate và bổ sung tích hợp với hệ thống channel của Spring Integration.

Tên phương thức tương tự nhau nhưng kiểu trả về và trách nhiệm có thể khác nhau. Đặc biệt, MessageChannel.send() trả về boolean, trong khi MessagingTemplate.send() là phương thức void và báo lỗi gửi qua exception.

## 2. send: gửi một Message

### 2.1. Gửi trực tiếp qua MessageChannel

MessageChannel định nghĩa hợp đồng gửi. Hai phương thức thường dùng:

~~~java
boolean send(Message<?> message);

boolean send(Message<?> message, long timeout);
~~~

Phương thức send(message) gửi theo chính sách của implementation. Nó có thể chờ vô thời hạn nếu channel cần chờ để chấp nhận Message.

Phương thức send(message, timeout) giới hạn thời gian chờ bằng mili giây. Hằng số MessageChannel.INDEFINITE_TIMEOUT biểu thị không đặt giới hạn thời gian chờ.

Giá trị trả về:

- true: channel chấp nhận Message.
- false: channel không chấp nhận được Message trong điều kiện hiện tại, ví dụ timeout hoặc thao tác gửi bị interrupt.
- RuntimeException: có lỗi không thể khôi phục hoặc lỗi delivery tùy implementation.

Ví dụ:

~~~java
Message<String> message = MessageBuilder
        .withPayload("ORD-89")
        .setHeader("eventType", "order.created")
        .build();

boolean accepted = channel.send(message, 500);

if (!accepted) {
    System.out.println("Message was not accepted");
}
~~~

Giá trị true không khẳng định handler đã xử lý xong, transaction đã commit hoặc broker đã lưu bền thông điệp. Nó chỉ phản ánh việc gửi được chấp nhận theo hợp đồng của channel.

### 2.2. Gửi bằng MessagingTemplate

Template giúp ứng dụng gọi messaging API thuận tiện hơn. Ví dụ với Spring Integration:

~~~java
MessagingTemplate template = new MessagingTemplate();
template.setSendTimeout(500);

template.send(channel, message);
~~~

MessagingTemplate.send(destination, message) trả về void. Khi phương thức trả về bình thường, thao tác gửi đã hoàn tất theo hợp đồng của template. Nếu channel không chấp nhận Message hoặc xảy ra lỗi delivery, template có thể ném MessagingException hoặc exception chuyên biệt trong hệ thống messaging.

Khác biệt cần nhớ:

| API | Kiểu trả về | Cách nhận biết gửi thất bại |
|---|---|---|
| MessageChannel.send(message) | boolean | Kiểm tra false hoặc bắt exception |
| MessageChannel.send(message, timeout) | boolean | Kiểm tra false hoặc bắt exception |
| MessagingTemplate.send(channel, message) | void | Bắt MessagingException/MessageDeliveryException |

Không nên viết mã dựa vào giả định rằng hai phương thức send này trả về cùng kiểu dữ liệu.

### 2.3. send và convertAndSend

Nếu đã có Message, dùng send. Nếu chỉ có payload và muốn template tạo Message, có thể dùng convertAndSend:

~~~java
template.convertAndSend(channel, "ORD-89");
~~~

Template sử dụng MessageConverter đã cấu hình để chuyển payload thành Message. Có thể truyền thêm headers hoặc MessagePostProcessor khi cần bổ sung metadata hay điều chỉnh Message sau khi chuyển đổi.

MessageConverter không phải broker và không tự đảm bảo mọi payload đều được serialize thành JSON. Kiểu chuyển đổi phụ thuộc converter được cấu hình và kiểu dữ liệu được hỗ trợ.

## 3. receive: chủ động lấy một Message

### 3.1. PollableChannel là điều kiện quan trọng

receive chỉ phù hợp với channel hỗ trợ polling. PollableChannel mở rộng MessageChannel và cung cấp:

~~~java
Message<?> receive();

Message<?> receive(long timeout);
~~~

Consumer chủ động gọi receive để lấy Message. Với receive() không có timeout, implementation có thể chặn vô thời hạn nếu chưa có thông điệp. Với receive(timeout), thread chờ tối đa số mili giây được chỉ định.

Nếu hết timeout hoặc việc nhận bị interrupt, PollableChannel có thể trả về null.

Ví dụ:

~~~java
Message<?> received = pollableChannel.receive(1_000);

if (received == null) {
    System.out.println("No message received");
}
else {
    System.out.println("payload=" + received.getPayload());
}
~~~

Không thể gọi receive trên một SubscribableChannel chỉ vì nó cũng là MessageChannel. SubscribableChannel nhận thông điệp bằng cách đăng ký MessageHandler; nó không cung cấp hợp đồng polling.

### 3.2. receive bằng MessagingTemplate

MessagingTemplate.receive(destination) là wrapper thuận tiện cho thao tác nhận. Template dùng receive timeout đã cấu hình:

~~~java
template.setReceiveTimeout(1_000);

Message<?> received = template.receive(pollableChannel);
~~~

Đích nhận phải là PollableChannel. GenericMessagingTemplate kiểm tra điều kiện này; nếu channel không hỗ trợ polling, thao tác receive không hợp lệ và có thể ném IllegalStateException.

Nếu không có Message trong khoảng chờ, receive trả về null. Ứng dụng phải kiểm tra null trước khi đọc payload hoặc headers.

### 3.3. receiveAndConvert

Khi ứng dụng chỉ cần payload đã chuyển về một kiểu cụ thể, có thể dùng receiveAndConvert:

~~~java
String payload = template.receiveAndConvert(pollableChannel, String.class);
~~~

Template nhận Message, sau đó dùng MessageConverter để chuyển payload sang kiểu yêu cầu. Nếu không nhận được Message trong timeout, kết quả có thể là null. Nếu chuyển đổi không thành công, template có thể ném MessageConversionException.

Dùng receive khi cần cả headers và payload. Dùng receiveAndConvert khi chỉ cần payload đã chuyển đổi và không cần giữ envelope.

## 4. sendAndReceive: request-reply trong một thao tác

### 4.1. Khi nào cần request-reply?

send là một chiều: producer phát Message và không tự động nhận kết quả nghiệp vụ.

Có những tình huống producer cần phản hồi tương ứng:

- Gửi yêu cầu kiểm tra trạng thái đơn hàng và cần kết quả.
- Yêu cầu một service tính giá rồi chờ giá trả về.
- Gửi lệnh kiểm tra tồn kho và cần biết số lượng còn lại.
- Gọi một handler nội bộ và cần một response Message.

Đây là mô hình request-reply. Producer gửi request rồi chờ reply. Phương thức sendAndReceive gom hai thao tác đó vào một API:

~~~java
Message<?> reply = template.sendAndReceive(channel, request);
~~~

Kết quả là reply Message hoặc null nếu không nhận được phản hồi trong receive timeout. Các lỗi gửi hoặc lỗi messaging có thể được báo qua MessagingException.

### 4.2. replyChannel dùng để làm gì?

Template cần biết gửi reply về đâu. Khi gọi sendAndReceive, GenericMessagingTemplate tạo một temporary reply channel cho lần trao đổi đó và gắn channel này vào header replyChannel của request.

Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant A as Requester
    participant T as MessagingTemplate
    participant C as Request Channel
    participant H as Handler
    participant R as Temporary Reply Channel

    A->>T: sendAndReceive(request)
    T->>T: Tạo reply channel tạm
    T->>C: Gửi request kèm replyChannel header
    C->>H: Chuyển request tới handler
    H->>R: Gửi response tới replyChannel
    R-->>T: Trả về reply Message
    T-->>A: sendAndReceive trả reply
~~~

Handler phải tôn trọng replyChannel nếu tự triển khai xử lý request-reply ở mức MessageHandler. Trong Spring Integration, các endpoint như service activator có thể tự xử lý giá trị trả về và định tuyến reply theo cấu hình endpoint.

Nếu handler không gửi reply hoặc gửi reply sai channel, requester sẽ chờ tới receive timeout và nhận null. Một response được gửi tới channel khác không tự động trở thành reply cho lời gọi sendAndReceive đang chờ.

### 4.3. Request và reply là hai Message

Request và reply là hai Message độc lập. Reply có thể có payload khác, headers khác và mang metadata liên quan tới request.

Nên giữ correlation ID hoặc thông tin định danh nghiệp vụ nếu cần theo dõi trao đổi qua nhiều hệ thống. Temporary reply channel giúp template ghép reply với lời gọi đang chờ, còn correlation ID hữu ích cho logging, tracing và giao tiếp qua broker.

Không nên nhầm correlation ID với replyChannel. Correlation ID là metadata định danh để ứng dụng theo dõi request/response; replyChannel là địa chỉ nhận reply mà messaging infrastructure sử dụng.

## 5. Cấu hình timeout cho send và receive

GenericMessagingTemplate có hai timeout độc lập:

- sendTimeout: thời gian tối đa chờ channel chấp nhận request Message.
- receiveTimeout: thời gian tối đa chờ reply hoặc Message được nhận.

Ví dụ:

~~~java
template.setSendTimeout(500);
template.setReceiveTimeout(2_000);
~~~

Trong request-reply, sendTimeout áp dụng cho bước gửi request. receiveTimeout áp dụng cho bước đợi reply.

Nếu receiveTimeout quá ngắn, reply có thể tới sau khi requester đã timeout. Nếu reply tới muộn, temporary reply channel không còn được requester chờ. GenericMessagingTemplate có tùy chọn setThrowExceptionOnLateReply để quyết định có ném MessageDeliveryException khi một reply tới muộn hay chỉ ghi cảnh báo theo mặc định.

Các timeout mặc định của GenericMessagingTemplate là -1, nghĩa là không đặt giới hạn chờ. Trong ứng dụng thực tế, nên cấu hình timeout rõ ràng để tránh thread bị giữ vô thời hạn.

Timeout không chứng minh request chưa được xử lý. Consumer có thể vẫn đang xử lý sau khi requester hết thời gian chờ. Nếu producer gửi lại, nghiệp vụ có thể bị chạy lặp. Với thao tác có side effect, cần thiết kế idempotency key hoặc cơ chế chống trùng.

## 6. Ví dụ Java 17 chạy được: send, receive và sendAndReceive

Ví dụ sau sử dụng MessagingTemplate của Spring Integration cùng QueueChannel và DirectChannel. QueueChannel minh họa gửi/nhận kiểu polling; DirectChannel minh họa request-reply với replyChannel.

### 6.1. Cấu hình Maven

Tạo file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>messaging-operations-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.5.10</version>
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

Spring Integration core cung cấp MessagingTemplate, QueueChannel và DirectChannel. Artifact này kéo theo spring-messaging tương thích.

### 6.2. Chương trình hoàn chỉnh

Tạo file src/main/java/demo/MessagingOperationsDemo.java:

~~~java
package demo;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

public class MessagingOperationsDemo {

    public static void main(String[] args) {
        MessagingTemplate template = new MessagingTemplate();
        template.setSendTimeout(1_000);
        template.setReceiveTimeout(1_000);

        demonstrateSendAndReceive(template);
        demonstrateSendAndReceiveReply(template);
    }

    private static void demonstrateSendAndReceive(MessagingTemplate template) {
        QueueChannel queue = new QueueChannel(10);

        Message<String> outbound = MessageBuilder
                .withPayload("ORD-89")
                .setHeader("eventType", "order.created")
                .build();

        // MessagingTemplate.send() trả về void.
        // Nếu gửi thất bại, template báo lỗi qua exception.
        template.send(queue, outbound);
        System.out.println("send.completed=true");

        Message<?> received = template.receive(queue);

        if (received == null) {
            throw new IllegalStateException("Expected a message from the queue");
        }

        System.out.println("receive.payload=" + received.getPayload());
        System.out.println(
                "receive.eventType=" + received.getHeaders().get("eventType")
        );

        // Queue hiện đã rỗng. Chỉ chờ 100 ms cho lần nhận tiếp theo.
        template.setReceiveTimeout(100);
        Message<?> empty = template.receive(queue);
        System.out.println("receive.empty=" + (empty == null));
    }

    private static void demonstrateSendAndReceiveReply(
            MessagingTemplate template) {

        DirectChannel requestChannel = new DirectChannel();

        requestChannel.subscribe(request -> {
            Object replyHeader =
                    request.getHeaders().get(MessageHeaders.REPLY_CHANNEL);

            if (!(replyHeader instanceof MessageChannel replyChannel)) {
                throw new IllegalStateException("Request has no reply channel");
            }

            Message<String> reply = MessageBuilder
                    .withPayload("accepted:" + request.getPayload())
                    .build();

            if (!replyChannel.send(reply)) {
                throw new IllegalStateException("Reply channel rejected the reply");
            }
        });

        template.setReceiveTimeout(1_000);

        Message<String> request = MessageBuilder
                .withPayload("ORD-89")
                .setHeader("requestType", "inventory.check")
                .build();

        Message<?> reply = template.sendAndReceive(requestChannel, request);

        if (reply == null) {
            throw new IllegalStateException("No reply received before timeout");
        }

        System.out.println("request.payload=" + request.getPayload());
        System.out.println("reply.payload=" + reply.getPayload());
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.MessagingOperationsDemo
~~~

Stdout:

~~~text
send.completed=true
receive.payload=ORD-89
receive.eventType=order.created
receive.empty=true
request.payload=ORD-89
reply.payload=accepted:ORD-89
~~~

### 6.3. Phân tích chương trình

Ở phần đầu, producer tạo Message có payload ORD-89 và header eventType. template.send đưa Message vào QueueChannel. Phương thức send của template trả về void; khi nó trả về bình thường, chương trình tiếp tục. Consumer gọi template.receive để lấy Message từ queue.

Lần receive tiếp theo không có Message, vì QueueChannel đã được lấy hết. Template chỉ chờ 100 mili giây rồi trả về null. Chương trình kiểm tra null và in receive.empty=true.

Ở phần request-reply, DirectChannel chuyển request tới MessageHandler đã đăng ký. Template gắn temporary reply channel vào header replyChannel. Handler lấy header đó, tạo Message phản hồi rồi gửi vào channel tạm. sendAndReceive nhận reply và trả về cho caller.

Ví dụ dùng DirectChannel nên handler chạy trực tiếp trong lời gọi gửi. Với channel hoặc adapter bất đồng bộ, handler có thể chạy ở thread khác; requester vẫn chờ reply cho tới khi nhận được hoặc receive timeout hết hạn.

## 7. Khi nào dùng từng thao tác?

| Nhu cầu | API phù hợp | Lưu ý |
|---|---|---|
| Phát một event, không cần reply | send | Chỉ xác nhận gửi theo channel/template |
| Gửi payload chưa đóng gói thành Message | convertAndSend | Template dùng MessageConverter |
| Lấy Message từ queue hoặc pollable channel | receive | Cần PollableChannel |
| Lấy payload và chuyển đổi sang kiểu Java | receiveAndConvert | Phụ thuộc MessageConverter |
| Gửi request và chờ reply | sendAndReceive | Cần handler hoặc endpoint gửi response về replyChannel |
| Gửi request và nhận payload đã chuyển đổi | convertSendAndReceive | Cần converter phù hợp |
| Gửi tới một channel và xử lý bất đồng bộ một chiều | send | Chọn channel/adapter có dispatch phù hợp |

Một quy tắc lựa chọn hữu ích:

- Dùng send khi caller chỉ cần phát thông điệp.
- Dùng receive khi caller chủ động lấy một Message từ channel có thể polling.
- Dùng sendAndReceive khi caller cần response tương ứng với request.
- Dùng convertAndSend hoặc convertSendAndReceive khi muốn template xử lý chuyển đổi payload.

Không dùng sendAndReceive chỉ để kiểm tra rằng channel nhận được request. Nếu không cần response nghiệp vụ, send đơn giản hơn và tránh giữ thread chờ reply.

## 8. Lỗi thường gặp và cách xử lý

### 8.1. Gọi receive trên SubscribableChannel

SubscribableChannel không có hợp đồng polling. Nó đẩy Message tới MessageHandler đã đăng ký. Muốn gọi receive, hãy dùng PollableChannel hoặc một implementation có hỗ trợ polling.

### 8.2. Không kiểm tra null

receive và sendAndReceive có thể trả về null khi hết receive timeout hoặc không có Message. Luôn kiểm tra kết quả trước khi đọc payload.

### 8.3. Nhầm boolean của MessageChannel.send với void của MessagingTemplate.send

MessageChannel.send trả về boolean. MessagingTemplate.send trả về void và báo lỗi bằng exception. Đọc đúng kiểu API để xử lý kết quả gửi chính xác.

### 8.4. Chờ reply nhưng handler không gửi response

sendAndReceive cần reply. Nếu handler chỉ xử lý request mà không gửi phản hồi, caller sẽ chờ tới receive timeout rồi nhận null. Nếu nghiệp vụ không cần reply, dùng send.

### 8.5. Gửi reply tới sai channel

Khi template tạo temporary reply channel, handler phải gửi response về channel trong header replyChannel. Gửi reply tới một channel khác không tự hoàn tất lời gọi sendAndReceive đang chờ.

### 8.6. Đặt timeout quá ngắn hoặc để vô hạn

Timeout quá ngắn làm requester bỏ cuộc trước khi consumer xử lý xong. Timeout vô hạn có thể giữ thread lâu và làm cạn tài nguyên. Chọn timeout theo latency mục tiêu và xử lý trường hợp không có reply.

### 8.7. Retry sau timeout mà không chống trùng

Timeout chỉ cho biết requester không nhận được reply đúng hạn. Consumer có thể vẫn đã thực hiện side effect. Gửi lại request có thể tạo tác động lặp. Dùng idempotency key, request ID hoặc cơ chế deduplication khi cần.

### 8.8. Cho rằng send thành công nghĩa là nghiệp vụ hoàn tất

send chỉ phản ánh việc channel chấp nhận Message. Nó không thay thế acknowledgement nghiệp vụ, transaction commit hoặc xác nhận lưu bền của broker.

### 8.9. Không xử lý MessagingException

Các thao tác template có thể ném MessagingException hoặc exception cụ thể như MessageDeliveryException, MessageConversionException. Hãy phân loại lỗi gửi, lỗi chuyển đổi, timeout và lỗi handler để quyết định retry hay trả lỗi cho caller.

## 9. Lưu ý về module và implementation

Các API nền tảng thuộc Spring Framework:

- MessageChannel và phương thức send.
- PollableChannel và phương thức receive.
- Message, MessageHeaders và MessageBuilder.
- GenericMessagingTemplate và các interface MessageSendingOperations, MessageReceivingOperations, MessageRequestReplyOperations.

Spring Integration bổ sung:

- MessagingTemplate trong package org.springframework.integration.core, kế thừa GenericMessagingTemplate.
- QueueChannel và DirectChannel.
- Các endpoint và integration flow có thể tự xử lý request-reply, poller, adapter và routing.

Vì vậy, không nên mặc định rằng chỉ thêm spring-messaging là đã có QueueChannel hoặc DirectChannel. Nếu dùng các implementation của Spring Integration, cần dependency spring-integration-core tương ứng. Nếu dùng API nền tảng của Spring Framework, hãy chọn GenericMessagingTemplate và channel implementation phù hợp với kiến trúc.

Một channel trong bộ nhớ cũng không tự trở thành broker bền vững. Các đặc tính như persistence, acknowledgement, redelivery, ordering và exactly-once semantics phụ thuộc adapter/broker và cấu hình thực tế.

## 10. Câu hỏi tự kiểm tra

1. MessageChannel.send() trả về kiểu dữ liệu gì?
2. MessagingTemplate.send() khác MessageChannel.send() ở kiểu trả về và cách báo lỗi như thế nào?
3. Vì sao receive chỉ phù hợp với PollableChannel?
4. Khi receive timeout hết hạn, kết quả thường là gì?
5. sendAndReceive khác send ở yêu cầu reply như thế nào?
6. Template dùng header nào để gửi reply về đúng request đang chờ?
7. Điều gì xảy ra nếu handler không gửi reply?
8. sendTimeout và receiveTimeout kiểm soát hai giai đoạn nào?
9. Vì sao timeout không chứng minh request chưa được xử lý?
10. Khi nào nên dùng convertSendAndReceive thay vì sendAndReceive?
11. GenericMessagingTemplate thuộc Spring Framework hay Spring Integration?
12. QueueChannel và DirectChannel thuộc module nào?

## 11. Kết luận

send, receive và sendAndReceive biểu diễn ba nhu cầu trao đổi khác nhau. send phát một Message tới channel; receive chủ động lấy Message từ channel có thể polling; sendAndReceive gửi request rồi chờ reply tương ứng.

Khi làm việc ở mức thấp, hãy nhớ MessageChannel.send trả về boolean và PollableChannel.receive có thể trả về null. Khi dùng MessagingTemplate, send là void, receive dùng timeout đã cấu hình và sendAndReceive cần một reply được gửi về replyChannel. Cấu hình timeout, xử lý exception và kiểm tra null giúp ứng dụng kiểm soát tốt hơn khi channel từ chối gửi hoặc consumer không phản hồi đúng hạn.

## Tài liệu tham khảo chính thức

- Spring Framework MessageChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html
- Spring Framework PollableChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html
- Spring Framework GenericMessagingTemplate API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html
- Spring Framework MessageSendingOperations API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessageSendingOperations.html
- Spring Framework MessageRequestReplyOperations API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessageRequestReplyOperations.html
- Spring Integration MessagingTemplate reference: https://docs.spring.io/spring-integration/reference/channel/template.html
- Spring Integration MessagingTemplate API: https://docs.spring.io/spring-integration/api/org/springframework/integration/core/MessagingTemplate.html
