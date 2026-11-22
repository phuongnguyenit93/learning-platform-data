# preSend và cách từ chối một thông điệp trong Spring Messaging

## 1. ChannelInterceptor trong luồng gửi message

Spring Messaging biểu diễn dữ liệu dưới dạng Message<T>, gồm payload và headers. MessageChannel là điểm gửi message; implementation của channel quyết định cách message được chuyển tới subscriber hoặc được lưu để consumer nhận.

**ChannelInterceptor** là extension point cho phép quan sát, kiểm tra hoặc biến đổi message khi nó đi qua một channel. Interceptor được gắn vào một channel cụ thể và tham gia vào vòng đời gửi/nhận của channel đó.

Phương thức quan trọng nhất khi gửi là:

~~~java
Message<?> preSend(Message<?> message, MessageChannel channel);
~~~

Spring gọi preSend trước khi channel thực hiện việc dispatch message. Kết quả trả về quyết định bước tiếp theo:

- **Trả về chính message:** cho phép gửi tiếp mà không thay đổi message.
- **Trả về một message khác:** cho phép gửi tiếp với message đã được biến đổi.
- **Trả về null:** từ chối message; channel dừng quá trình gửi và không dispatch message đó tới subscriber.

Do đó, preSend vừa có thể dùng để kiểm tra điều kiện, vừa có thể chuẩn hóa hoặc bổ sung metadata trước khi message được xử lý.

Một interceptor chỉ ảnh hưởng tới các thao tác đi qua channel đã đăng ký interceptor. Việc tạo một GenericMessage hoặc MessageBuilder riêng không tự kích hoạt preSend; message phải được gửi qua channel có interceptor.

## 2. Contract của preSend

### 2.1. Cho phép message đi tiếp

Nếu không cần thay đổi message, trả lại đối tượng message nhận được:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    return message;
}
~~~

Đây là trường hợp phù hợp khi interceptor chỉ kiểm tra hoặc ghi nhận thông tin. Sau khi preSend trả về message, channel tiếp tục dispatch theo implementation của nó.

### 2.2. Từ chối bằng cách trả về null

Để ngăn message đi tiếp, trả về null:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    if (!isAllowed(message)) {
        return null;
    }

    return message;
}
~~~

Khi preSend trả về null, quá trình gửi bị hủy ở interceptor chain. Với AbstractMessageChannel, lời gọi send trả về false và subscriber không nhận được message bị từ chối.

Đây là cơ chế từ chối có kiểm soát, không cần ném exception cho một điều kiện nghiệp vụ dự kiến như payload thiếu trường bắt buộc hoặc giá trị không hợp lệ.

Cần phân biệt hai kết quả:

- **send trả về false do interceptor từ chối:** message không được chuyển tới channel handler.
- **send ném exception:** thao tác gửi gặp lỗi; caller cần xử lý exception theo chính sách của ứng dụng.

Không nên dùng null để che giấu lỗi hạ tầng, lỗi lập trình hoặc tình trạng channel không hoạt động. Hãy chọn kết quả theo đúng ý nghĩa của điều kiện kiểm tra.

### 2.3. Từ chối bằng exception

Interceptor cũng có thể ném exception khi gặp lỗi cần báo trực tiếp cho caller:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    if (message.getHeaders().get("tenantId") == null) {
        throw new IllegalArgumentException("tenantId is required");
    }

    return message;
}
~~~

Khi exception thoát khỏi preSend, thao tác send thất bại bằng exception thay vì trả về false. Caller cần phân biệt exception dự kiến với lỗi không mong đợi và không tự động retry mọi exception.

Dùng exception khi caller cần biết lý do gửi không thể tiếp tục. Với một điều kiện từ chối thông thường mà caller chỉ cần biết message không được chấp nhận, trả null có thể phù hợp hơn.

## 3. Biến đổi message trong preSend

preSend không bắt buộc phải trả về đúng instance đầu vào. Nếu cần thêm header hoặc tạo payload đã chuẩn hóa, hãy tạo message mới:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    return MessageBuilder
        .fromMessage(message)
        .setHeader("validated", true)
        .build();
}
~~~

Channel sẽ tiếp tục với message được trả về. Subscriber nhận message mới có header validated.

MessageBuilder.fromMessage sao chép payload và headers vào builder. Message gốc không bị sửa; tuy nhiên payload object có thể vẫn là cùng tham chiếu. Nếu cần biến đổi nội dung payload, hãy tạo payload mới thay vì thay đổi object mutable đang được chia sẻ.

Không nên thay đổi MessageHeaders trực tiếp vì chúng immutable. Tạo message mới qua MessageBuilder là cách rõ ràng để bổ sung hoặc thay metadata.

### 3.1. Thứ tự kiểm tra và biến đổi

Một interceptor thường thực hiện các bước:

1. Xác định payload có đúng kiểu mong đợi không.
2. Kiểm tra các trường bắt buộc và quy tắc nghiệp vụ.
3. Xác minh metadata cần tin cậy, chẳng hạn tenant hoặc source, từ context phù hợp.
4. Từ chối bằng null nếu điều kiện không đạt.
5. Tạo message mới nếu cần bổ sung header đã được xác minh.
6. Trả message để channel tiếp tục dispatch.

Không nên dùng một header do client tự gửi làm bằng chứng xác thực. Nếu header ảnh hưởng tới quyền truy cập, tenant hoặc routing, hãy kiểm tra nó với security context hoặc nguồn tin cậy của ứng dụng.

## 4. Đăng ký ChannelInterceptor vào channel

ChannelInterceptor không được tự động áp dụng cho mọi MessageChannel trong ứng dụng. Nó cần được đăng ký vào implementation hỗ trợ interceptor, thường là AbstractMessageChannel hoặc một subclass.

Trong Spring Framework Messaging, có thể dùng ExecutorSubscribableChannel:

~~~java
ExecutorSubscribableChannel ordersChannel =
    new ExecutorSubscribableChannel();

ordersChannel.addInterceptor(new ChannelInterceptor() {
    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        if (!isAllowed(message)) {
            return null;
        }

        return message;
    }
});
~~~

Có thể đăng ký interceptor khi tạo bean channel:

~~~java
@Bean
ExecutorSubscribableChannel ordersChannel() {
    ExecutorSubscribableChannel channel =
        new ExecutorSubscribableChannel();

    channel.addInterceptor(new OrderValidationInterceptor());
    return channel;
}
~~~

Đăng ký ở đúng channel giúp phạm vi kiểm soát rõ ràng. Ví dụ, chỉ channel nhận lệnh tạo đơn hàng cần kiểm tra OrderCommand; channel gửi log hoặc metric có thể có chính sách khác.

Nếu một channel được chia sẻ bởi nhiều luồng nghiệp vụ, interceptor phải kiểm tra kiểu payload và điều kiện áp dụng một cách rõ ràng. Không giả định mọi message đi qua channel đều có cùng payload type.

**Lưu ý về DirectChannel:** class DirectChannel quen thuộc thuộc dự án Spring Integration, package org.springframework.integration.channel. Ví dụ trong bài dùng ExecutorSubscribableChannel thuộc Spring Framework Messaging để chương trình chỉ cần dependency spring-messaging.

## 5. Các callback khác trong ChannelInterceptor

ChannelInterceptor cung cấp nhiều callback cho vòng đời gửi và nhận:

| Callback | Thời điểm và mục đích |
|---|---|
| preSend(message, channel) | Trước khi gửi; có thể biến đổi hoặc từ chối bằng null |
| postSend(message, channel, sent) | Sau khi channel thực hiện send; nhận kết quả sent |
| afterSendCompletion(message, channel, sent, ex) | Sau khi hoàn tất send, kể cả khi có lỗi; phù hợp cho cleanup |
| preReceive(channel) | Trước khi poll một message từ PollableChannel; trả false để không nhận |
| postReceive(message, channel) | Sau khi nhận được message từ PollableChannel; có thể biến đổi message nhận |
| afterReceiveCompletion(message, channel, ex) | Sau khi hoàn tất thao tác receive; phù hợp cho cleanup |

preSend kiểm soát **đường gửi**. Với PollableChannel, preReceive kiểm soát **đường nhận** bằng boolean: trả false để bỏ qua thao tác receive ở lần gọi đó.

Không nhầm preSend với preReceive:

- preSend nhận Message<?> và có thể trả message mới hoặc null.
- preReceive nhận MessageChannel và trả boolean vì tại thời điểm đó message chưa được lấy ra.

postSend nhận giá trị sent để biết channel báo kết quả gửi thế nào. Nó không chứng minh nghiệp vụ consumer đã hoàn tất. Với channel bất đồng bộ, send có thể thành công trong khi handler vẫn đang xử lý.

afterSendCompletion và afterReceiveCompletion hữu ích để giải phóng tài nguyên hoặc đóng phạm vi quan sát sau khi thao tác kết thúc. Không dùng callback cleanup để thay thế việc xử lý exception ở tầng phù hợp.

## 6. Từ chối message khác với retry và dead-letter

Khi preSend trả về null, message bị chặn trước khi channel dispatch. Spring Messaging không tự lưu message bị chặn vào một hàng đợi từ chối, không tự retry và không tự tạo dead-letter queue.

Nếu cần giữ lại message bị từ chối để kiểm tra, ứng dụng phải chủ động triển khai cơ chế phù hợp, ví dụ:

- Ghi nhận lý do từ chối bằng metric hoặc audit log đã loại bỏ dữ liệu nhạy cảm.
- Chuyển bản sao message an toàn tới một rejection channel được thiết kế riêng, nếu kiến trúc cho phép.
- Lưu thông tin cần điều tra vào kho lưu trữ có kiểm soát truy cập.
- Dùng cơ chế retry/dead-letter của broker hoặc Spring Integration khi message đi qua hạ tầng tương ứng.

Cẩn thận khi gửi một message khác ngay bên trong preSend. Việc gửi sang channel khác có thể gây đệ quy, vòng lặp định tuyến hoặc deadlock nếu hai channel phụ thuộc nhau. Nếu cần chuyển message sang rejection flow, hãy thiết kế đường đi riêng và tránh gửi ngược lại channel đang được intercept.

## 7. Thiết kế điều kiện từ chối an toàn

### 7.1. Chỉ từ chối vì điều kiện xác định được

Điều kiện từ chối nên rõ ràng và có thể giải thích. Ví dụ:

- Payload không thuộc kiểu message mà channel chấp nhận.
- Trường nghiệp vụ bắt buộc bị thiếu.
- Giá trị nằm ngoài giới hạn đã quy định.
- Message đã hết hạn theo quy tắc của ứng dụng.
- Danh tính hoặc quyền truy cập đã được xác minh không cho phép thao tác.

Tránh điều kiện mơ hồ như từ chối vì header “có vẻ lạ” mà không có quy tắc kiểm tra cụ thể.

### 7.2. Không làm công việc chậm trong preSend

preSend nằm trên đường gửi message. Nếu thực hiện truy vấn database, gọi HTTP hoặc chờ một dịch vụ khác trong callback này, mọi thao tác gửi qua channel có thể bị chậm.

Ưu tiên kiểm tra nhanh, xác định và có thể thực hiện tại chỗ. Nếu cần xác minh từ xa, cân nhắc một bước xử lý riêng có timeout và chính sách lỗi rõ ràng.

### 7.3. Ghi nhận lý do từ chối

Nếu trả null, caller thường chỉ thấy send trả về false. Hãy thiết kế khả năng quan sát phù hợp:

- Metric đếm message bị từ chối theo loại lý do.
- Log có correlation ID hoặc message ID nếu có.
- Không ghi toàn bộ payload hoặc token nhạy cảm.
- Có thể dùng counter riêng cho sai schema, vi phạm nghiệp vụ và thiếu quyền.

Không log bí mật trong header hoặc nội dung message. Nếu lý do từ chối cần được trả về cho caller, hãy dùng exception có chủ đích hoặc một response nghiệp vụ riêng thay vì chỉ dựa vào boolean false.

## 8. Ví dụ Java 17+ chạy độc lập

Ví dụ sau tạo ExecutorSubscribableChannel, đăng ký một ChannelInterceptor và subscriber. Interceptor chỉ cho phép OrderCommand có amount dương. Message hợp lệ được bổ sung header validated; message có amount bằng 0 bị từ chối bằng null.

**Cấu trúc dự án**

~~~text
presend-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          PreSendDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>presend-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.18</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/PreSendDemo.java**

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class PreSendDemo {

    public record OrderCommand(String orderId, long amount) {}

    public static void main(String[] args) {
        ExecutorSubscribableChannel ordersChannel =
            new ExecutorSubscribableChannel();

        ordersChannel.addInterceptor(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(
                    Message<?> message,
                    MessageChannel channel) {

                if (!(message.getPayload() instanceof OrderCommand command)) {
                    return null;
                }

                if (command.amount() <= 0) {
                    return null;
                }

                return MessageBuilder
                    .fromMessage(message)
                    .setHeader("validated", true)
                    .build();
            }
        });

        ordersChannel.subscribe(message -> {
            OrderCommand command = (OrderCommand) message.getPayload();
            System.out.println(
                "handled=" + command.orderId()
                + ", validated=" + message.getHeaders().get("validated")
            );
        });

        Message<OrderCommand> validMessage = MessageBuilder
            .withPayload(new OrderCommand("ORD-1071", 125_000L))
            .build();

        Message<OrderCommand> invalidMessage = MessageBuilder
            .withPayload(new OrderCommand("ORD-1072", 0L))
            .build();

        boolean validSend = ordersChannel.send(validMessage);
        boolean invalidSend = ordersChannel.send(invalidMessage);

        System.out.println("validSend=" + validSend);
        System.out.println("invalidSend=" + invalidSend);
    }
}
~~~

Chạy từ thư mục presend-demo:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.PreSendDemo
~~~

**stdout**

~~~text
handled=ORD-1071, validated=true
validSend=true
invalidSend=false
~~~

Kết quả thể hiện:

- Message ORD-1071 có amount dương nên preSend trả về message đã bổ sung validated=true; subscriber nhận message và xử lý.
- Message ORD-1072 có amount bằng 0 nên preSend trả null; subscriber không nhận message.
- send trả true cho message hợp lệ và false cho message bị interceptor từ chối.

Ví dụ dùng ExecutorSubscribableChannel không cấu hình executor nên subscriber được gọi đồng bộ trong lời gọi send. Nếu cấu hình executor, send trả true chỉ cho biết channel chấp nhận/dispatch message theo cơ chế của channel; không có nghĩa handler đã hoàn tất nghiệp vụ.

## 9. Lỗi thường gặp

1. **Trả null nhưng mong channel tự retry:** null chỉ từ chối lần gửi hiện tại. Retry hoặc dead-letter cần được thiết kế riêng.
2. **Ném exception cho mọi trường hợp không hợp lệ:** lỗi nghiệp vụ dự kiến có thể được biểu diễn bằng null và metric; exception dành cho lỗi cần báo trực tiếp.
3. **Trả message gốc sau khi đã tạo bản sao:** nếu muốn subscriber nhận header mới, phải trả đúng message đã build.
4. **Sửa MessageHeaders trực tiếp:** headers immutable. Dùng MessageBuilder để tạo message mới.
5. **Đăng ký interceptor nhầm channel:** interceptor chỉ chạy trên channel được gắn vào.
6. **Giả định preSend kiểm soát mọi đường vào ứng dụng:** message có thể tới consumer qua channel khác hoặc một transport không đi qua channel đang intercept.
7. **Dùng header không đáng tin cậy làm bằng chứng quyền:** xác thực danh tính và quyền ở security boundary.
8. **Gọi dịch vụ chậm trong preSend:** làm tăng latency của đường gửi và có thể gây nghẽn.
9. **Cho rằng send=true nghĩa là consumer đã xử lý xong:** kết quả send không thay thế acknowledgment hoặc kết quả transaction của consumer.
10. **Gửi message lỗi lại chính channel đang bị intercept:** dễ tạo vòng lặp hoặc đệ quy. Dùng rejection flow riêng nếu cần lưu message bị từ chối.

## 10. Khi nào nên dùng preSend?

Dùng preSend khi cần một bước kiểm tra đồng bộ, nhanh trước khi message đi vào channel, chẳng hạn kiểm tra payload type, trường bắt buộc, giới hạn kích thước hoặc thêm metadata đã được xác minh.

Nếu cần điều phối nghiệp vụ phức tạp, retry, lưu message lỗi, dead-letter hoặc xác thực từ xa, hãy dùng một thành phần chuyên trách trong flow hoặc broker thay vì dồn toàn bộ logic vào interceptor.

Hãy giữ interceptor nhỏ, có phạm vi rõ ràng và có thể kiểm thử độc lập. Việc từ chối phải có lý do đo được, còn message được chấp nhận phải giữ nguyên hợp đồng payload/header mà consumer mong đợi.

## 11. Tài liệu tham khảo

- [ChannelInterceptor — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [AbstractMessageChannel — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html)
- [ExecutorSubscribableChannel — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [MessageBuilder — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)