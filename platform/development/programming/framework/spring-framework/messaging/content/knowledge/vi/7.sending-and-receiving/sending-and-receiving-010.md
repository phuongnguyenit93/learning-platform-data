# MessagePostProcessor và bổ sung metadata sau chuyển đổi

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích MessagePostProcessor là gì và nó nằm ở đâu trong luồng gửi thông điệp.
- Phân biệt chuyển đổi payload thành Message với bước hậu xử lý Message.
- Dùng MessagePostProcessor để bổ sung trace ID, event type, source và metadata khác sau khi converter tạo Message.
- Tạo Message mới bằng MessageBuilder mà vẫn giữ payload và headers hiện có.
- Hiểu thứ tự giữa MessageConverter, MessagePostProcessor và MessageChannel.send.
- Phân biệt MessagePostProcessor với MessageBuilder, MessageConverter và ChannelInterceptor.
- Dùng post processor trong convertAndSend và request post processor trong convertSendAndReceive.
- Tránh ghi đè metadata quan trọng, trả về null hoặc thực hiện công việc nặng trong callback.

## 1. Vì sao cần hậu xử lý Message?

Khi gửi một object Java, ứng dụng thường muốn dùng template để chuyển payload thành Message rồi gửi tới channel. Converter chịu trách nhiệm tạo Message từ payload và các headers ban đầu. Tuy nhiên, có những metadata chỉ được biết ở thời điểm gửi, sau khi payload đã được chuyển đổi:

- Trace ID hoặc correlation ID được tạo cho lần gửi hiện tại.
- Tên service hoặc component phát thông điệp.
- Event type hoặc schema version do ứng dụng quy ước.
- Tenant ID, locale hoặc thông tin phân loại cần thiết cho consumer.
- Thời điểm phát sự kiện hoặc một header phục vụ quan sát.

Có thể bổ sung các metadata này bằng MessageBuilder trước khi gửi. Nhưng khi dùng template và convertAndSend, Spring cung cấp một callback chuyên biệt để xử lý Message sau khi converter tạo xong: MessagePostProcessor.

MessagePostProcessor hữu ích khi muốn tái sử dụng một converter chung, còn metadata được thêm riêng theo từng lần gửi. Nó giữ rõ hai trách nhiệm: converter chuyển payload thành Message; post processor điều chỉnh Message đã được tạo.

## 2. MessagePostProcessor là gì?

MessagePostProcessor là một functional interface trong package org.springframework.messaging.core của Spring Framework. Hợp đồng có một phương thức:

~~~java
Message<?> postProcessMessage(Message<?> message);
~~~

Callback nhận Message đã được tạo và trả về:

- Một Message đã được hậu xử lý, thường là một Message mới có header hoặc nội dung được điều chỉnh.
- Chính Message đầu vào nếu không cần thay đổi.

Callback không được trả về null. Nếu không có thay đổi, hãy trả lại Message ban đầu.

Vì đây là functional interface, có thể triển khai bằng lambda:

~~~java
MessagePostProcessor processor = message -> MessageBuilder
        .fromMessage(message)
        .setHeader("traceId", "trace-92")
        .build();
~~~

MessagePostProcessor không phải là channel và không tự gửi Message. Template gọi callback trong quá trình gửi, sau đó chuyển Message kết quả tới destination.

## 3. Vị trí của post processor trong luồng gửi

Khi gọi convertAndSend(destination, payload, postProcessor), luồng khái niệm là:

~~~mermaid
flowchart LR
    A["Payload Java"]
    B["MessageConverter"]
    C["Message ban đầu"]
    D["MessagePostProcessor"]
    E["Message sau hậu xử lý"]
    F["MessageChannel.send"]
    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
~~~

Thứ tự này có ý nghĩa:

1. Template nhận payload Java.
2. MessageConverter chuyển payload thành Message và tạo các headers cần thiết theo converter.
3. MessagePostProcessor nhận Message đã tạo.
4. Callback có thể thêm, thay hoặc loại bỏ metadata bằng cách tạo Message phù hợp.
5. Template gửi Message sau hậu xử lý tới channel.

Do callback chạy sau chuyển đổi, nó có thể đọc Message headers và payload đã được converter chuẩn bị. Đây là lý do tên gọi của API nhấn mạnh việc post-process Message.

Post processor chạy trong luồng thực thi của thao tác gửi template. Nếu callback làm việc lâu, thao tác gửi cũng bị kéo dài. Nó không mặc định chạy trên thread consumer và cũng không tự tạo bất đồng bộ.

## 4. Dùng convertAndSend với MessagePostProcessor

Spring Integration cung cấp MessagingTemplate trong package org.springframework.integration.core. Template hỗ trợ overload:

~~~java
template.convertAndSend(channel, payload, postProcessor);
~~~

Template chuyển payload thành Message, gọi post processor, rồi gửi Message đã xử lý tới channel.

Ví dụ ngắn:

~~~java
MessagingTemplate template = new MessagingTemplate();

MessagePostProcessor addMetadata = message -> MessageBuilder
        .fromMessage(message)
        .setHeader("eventType", "order.created")
        .setHeader("traceId", "trace-92")
        .setHeader("producer", "checkout")
        .build();

template.convertAndSend(channel, "ORD-92", addMetadata);
~~~

Payload vẫn là ORD-92. Post processor thêm các header eventType, traceId và producer sau khi template đã chuyển payload thành Message.

Nếu cần gửi một Message đã được tạo từ trước, dùng send(channel, message). Trong trường hợp đó, ứng dụng có thể tạo Message mới bằng MessageBuilder trước khi gọi send. Overload có MessagePostProcessor gắn với các thao tác chuyển đổi như convertAndSend; không nên giả định rằng mọi lời gọi MessageChannel.send đều tự động chạy callback này.

## 5. Thêm metadata mà vẫn giữ Message hiện có

Message được thiết kế như một envelope bất biến. Không sửa trực tiếp map headers của Message. Hãy dùng MessageBuilder.fromMessage để tạo một Message mới dựa trên Message đầu vào.

Ví dụ:

~~~java
Message<?> enriched = MessageBuilder
        .fromMessage(message)
        .setHeader("traceId", "trace-92")
        .setHeader("producer", "checkout")
        .build();
~~~

Cách làm này giữ payload và những headers hiện có, đồng thời bổ sung các header mới. Nếu đặt một header đã tồn tại bằng setHeader, giá trị cũ sẽ được thay bằng giá trị mới.

Trước khi ghi đè, hãy xác định ai sở hữu header đó và quy ước của ứng dụng. Các header chuẩn của framework như ID, timestamp, replyChannel và errorChannel có ý nghĩa điều khiển; không nên tùy tiện thay đổi hoặc loại bỏ chúng.

Nếu cần giữ giá trị đã có, hãy kiểm tra trước khi bổ sung:

~~~java
MessagePostProcessor addTraceIfMissing = message -> {
    if (message.getHeaders().containsKey("traceId")) {
        return message;
    }

    return MessageBuilder
            .fromMessage(message)
            .setHeader("traceId", "trace-92")
            .build();
};
~~~

Ví dụ trên không ghi đè traceId nếu producer hoặc một bước trước đó đã thiết lập. Quy tắc này hữu ích khi nhiều thành phần cùng bổ sung metadata.

## 6. Những metadata thường được bổ sung

### 6.1. Trace ID và correlation ID

Trace ID giúp theo dõi một luồng xử lý qua nhiều thành phần. Correlation ID giúp ghép các thông điệp có liên quan, đặc biệt trong request-reply hoặc khi một nghiệp vụ phát ra nhiều event.

~~~java
MessagePostProcessor tracing = message -> MessageBuilder
        .fromMessage(message)
        .setHeader("traceId", traceId)
        .setHeader("correlationId", correlationId)
        .build();
~~~

Các giá trị traceId và correlationId phải được tạo hoặc lấy từ context đáng tin cậy của ứng dụng. Nếu có ID đã tồn tại, hãy quyết định rõ nên giữ ID gốc, tạo ID mới hay lưu cả hai theo quy ước.

### 6.2. Event type và schema version

Consumer có thể cần biết payload đại diện cho loại sự kiện nào và theo phiên bản schema nào:

~~~java
MessagePostProcessor eventMetadata = message -> MessageBuilder
        .fromMessage(message)
        .setHeader("eventType", "order.created")
        .setHeader("schemaVersion", 2)
        .build();
~~~

Không dùng schemaVersion để thay thế versioning thực sự của DTO hoặc schema trên wire. Header chỉ là metadata; producer và consumer vẫn phải thống nhất cấu trúc payload.

### 6.3. Source, tenant và locale

Metadata nguồn phát hoặc tenant có thể hỗ trợ định tuyến, logging và phân tách dữ liệu:

~~~java
MessagePostProcessor contextMetadata = message -> MessageBuilder
        .fromMessage(message)
        .setHeader("sourceService", "checkout")
        .setHeader("tenantId", tenantId)
        .setHeader("locale", "vi-VN")
        .build();
~~~

Không tin tưởng tenant ID hoặc quyền truy cập chỉ vì chúng xuất hiện trong header. Consumer vẫn phải xác thực và phân quyền theo nguồn dữ liệu đáng tin cậy. Tránh đưa token, mật khẩu hoặc thông tin bí mật vào headers vì metadata có thể được ghi log hoặc truyền qua hệ thống khác.

### 6.4. Timestamp

MessageHeaders có timestamp hệ thống khi Message được tạo. Nếu nghiệp vụ cần thời điểm phát sự kiện theo quy ước riêng, có thể bổ sung một header riêng như eventCreatedAt hoặc publishedAt. Phải xác định rõ ý nghĩa và múi giờ của giá trị thời gian; không ghi đè timestamp chuẩn của framework.

## 7. Ví dụ Java 17 chạy được với QueueChannel

Ví dụ sau dùng Spring Integration MessagingTemplate và QueueChannel. Template chuyển String thành Message, sau đó MessagePostProcessor thêm metadata. Consumer lấy Message và đọc cả payload lẫn headers.

### 7.1. Cấu hình Maven

Tạo file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>message-post-processor-demo</artifactId>
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

spring-integration-core cung cấp MessagingTemplate và QueueChannel, đồng thời kéo theo spring-messaging tương thích. Nếu ứng dụng dùng integration khác, hãy quản lý phiên bản dependency bằng BOM phù hợp với phiên bản Spring đang sử dụng.

### 7.2. Chương trình hoàn chỉnh

Tạo file src/main/java/demo/MessagePostProcessorDemo.java:

~~~java
package demo;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.core.MessagePostProcessor;
import org.springframework.messaging.support.MessageBuilder;

public class MessagePostProcessorDemo {

    public static void main(String[] args) {
        QueueChannel channel = new QueueChannel(10);

        MessagingTemplate template = new MessagingTemplate();
        template.setSendTimeout(1_000);
        template.setReceiveTimeout(1_000);

        MessagePostProcessor metadataProcessor = message ->
                MessageBuilder.fromMessage(message)
                        .setHeader("eventType", "order.created")
                        .setHeader("traceId", "trace-92")
                        .setHeader("producer", "checkout")
                        .build();

        // Payload được chuyển thành Message trước khi callback chạy.
        template.convertAndSend(channel, "ORD-92", metadataProcessor);

        Message<?> received = template.receive(channel);

        if (received == null) {
            throw new IllegalStateException("No message received");
        }

        System.out.println("payload=" + received.getPayload());
        System.out.println(
                "eventType=" + received.getHeaders().get("eventType")
        );
        System.out.println(
                "traceId=" + received.getHeaders().get("traceId")
        );
        System.out.println(
                "producer=" + received.getHeaders().get("producer")
        );
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.MessagePostProcessorDemo
~~~

Stdout:

~~~text
payload=ORD-92
eventType=order.created
traceId=trace-92
producer=checkout
~~~

### 7.3. Phân tích kết quả

Producer chỉ truyền payload ORD-92 cho convertAndSend. Template dùng MessageConverter để tạo Message. Sau đó callback metadataProcessor nhận Message và dùng MessageBuilder.fromMessage để thêm ba header.

QueueChannel nhận Message đã hậu xử lý. Consumer gọi receive và đọc được payload cùng các header. Điều này cho thấy post processor được gọi trước khi Message được gửi tới channel.

Ví dụ không thay đổi payload, không thực hiện serialization qua mạng và không tạo broker. Nó chỉ minh họa việc bổ sung metadata trên Message trong luồng gửi nội bộ.

## 8. Dùng post processor với request-reply

Spring Integration MessagingTemplate cũng hỗ trợ request post processor trong thao tác convertSendAndReceive:

~~~java
Object reply = template.convertSendAndReceive(
        requestChannel,
        requestPayload,
        requestMessage -> MessageBuilder
                .fromMessage(requestMessage)
                .setHeader("traceId", traceId)
                .setHeader("requestType", "inventory.check")
                .build()
);
~~~

Ở đây, template chuyển requestPayload thành request Message, gọi request post processor rồi gửi request. Nếu nhận được reply trong receive timeout, template chuyển đổi và trả kết quả reply theo API được gọi.

Post processor trong overload này xử lý **request Message trước khi gửi**. Nó không phải callback để hậu xử lý reply. Nếu cần điều chỉnh reply, hãy xử lý ở consumer, reply handler hoặc phía nhận sau khi nhận được reply.

Request-reply vẫn cần một handler hoặc endpoint gửi response về reply channel đúng cách. Việc thêm metadata bằng post processor không tự tạo reply và không bảo đảm consumer đã hoàn tất nghiệp vụ.

## 9. MessagePostProcessor khác các thành phần nào?

| Thành phần | Trách nhiệm | Thời điểm chính |
|---|---|---|
| MessageConverter | Chuyển payload Java thành Message hoặc chuyển payload khi nhận | Trong bước chuyển đổi |
| MessagePostProcessor | Điều chỉnh Message đã được tạo, thường để bổ sung metadata | Sau khi tạo Message, trước khi gửi |
| MessageBuilder | Tạo Message mới và thiết lập payload/headers | Khi ứng dụng chủ động xây dựng Message |
| ChannelInterceptor | Quan sát hoặc can thiệp vào hoạt động gửi/nhận tại channel | Tại ranh giới channel |
| MessageHandler | Xử lý Message ở phía consumer | Sau khi Message được chuyển tới handler |

### 9.1. MessageConverter

Converter quyết định payload được biểu diễn trong Message như thế nào. Ví dụ String, byte array hoặc DTO có thể cần converter khác nhau. Post processor không thay thế converter và không nên được dùng để biến một DTO thành JSON bằng thao tác nối chuỗi tùy tiện.

### 9.2. MessageBuilder

MessageBuilder hữu ích khi ứng dụng đã có payload hoặc Message và muốn tạo envelope với headers cụ thể. MessagePostProcessor thường dùng MessageBuilder bên trong callback để điều chỉnh Message do template tạo ra.

### 9.3. ChannelInterceptor

ChannelInterceptor áp dụng ở ranh giới channel và có thể quan sát nhiều thao tác gửi/nhận đi qua channel. MessagePostProcessor được truyền vào một thao tác template cụ thể, nên phạm vi thường hẹp và tường minh hơn.

Nếu cần gắn metadata theo từng lần gọi convertAndSend, dùng post processor. Nếu cần logic xuyên suốt mọi Message đi qua một channel, xem xét ChannelInterceptor.

### 9.4. JMS MessagePostProcessor

Spring JMS có một interface MessagePostProcessor riêng dành cho JMS Message, thuộc API Spring JMS. Nó không phải cùng kiểu với org.springframework.messaging.core.MessagePostProcessor của Spring Messaging. Khi import, hãy kiểm tra package để tránh nhầm hai callback cùng tên nhưng xử lý hai loại Message khác nhau.

## 10. Quy tắc xử lý header và metadata

Khi bổ sung metadata, nên áp dụng các nguyên tắc:

1. **Dùng tên header nhất quán:** thống nhất camelCase hoặc một quy ước đặt tên trong toàn hệ thống.
2. **Không ghi đè header hệ thống:** tránh thay ID, timestamp, replyChannel hoặc errorChannel nếu không có lý do và hiểu rõ hệ quả.
3. **Quy định rõ ai sở hữu header:** trace ID do gateway tạo có thể cần được giữ xuyên suốt; service downstream không nên tùy tiện tạo giá trị khác.
4. **Giữ kiểu dữ liệu ổn định:** nếu schemaVersion là số, mọi producer nên gửi cùng kiểu; không lúc Integer, lúc String.
5. **Không đặt dữ liệu bí mật vào header:** metadata có thể xuất hiện trong log, trace hoặc transport.
6. **Không tin metadata để cấp quyền:** xác thực tenant và quyền truy cập ở ranh giới tin cậy.
7. **Trả về Message hợp lệ:** postProcessMessage không được trả về null.
8. **Không thay payload ngoài ý muốn:** dùng fromMessage nếu chỉ muốn bổ sung header; nếu thay payload, ghi rõ lý do và kiểm tra kiểu dữ liệu.
9. **Không tạo timestamp mơ hồ:** xác định UTC, epoch hoặc kiểu thời gian được quy ước.
10. **Không làm callback quá nặng:** tránh truy vấn database, gọi HTTP hoặc chờ lock trong post processor nếu có thể chuẩn bị metadata trước.

## 11. Hiệu năng, thread safety và khả năng kiểm thử

MessagePostProcessor chạy trong đường gửi của template. Một callback có thể thực hiện nhanh, chẳng hạn đọc trace ID từ context, tạo metadata và trả về Message mới. Nếu callback gọi dịch vụ ngoài hoặc thực hiện thao tác blocking, độ trễ gửi sẽ tăng.

Nếu một post processor được chia sẻ giữa nhiều thread, hãy giữ nó stateless hoặc bảo đảm dữ liệu dùng chung an toàn khi truy cập đồng thời. Tránh lưu trace ID của từng request vào field mutable của processor; hãy lấy giá trị từ tham số hoặc context phù hợp với từng lần gọi.

Có thể kiểm thử callback riêng bằng cách tạo một Message mẫu, gọi postProcessMessage rồi kiểm tra payload và headers. Nên có test cho các trường hợp:

- Header được thêm khi chưa tồn tại.
- Header được giữ nguyên hoặc thay thế theo chính sách.
- Payload không đổi khi chỉ bổ sung metadata.
- Header chuẩn không bị ghi đè ngoài ý muốn.
- Callback không trả về null.
- Các request đồng thời không dùng nhầm metadata của nhau.

Ví dụ kiểm tra đơn giản:

~~~java
Message<String> input = MessageBuilder
        .withPayload("ORD-92")
        .setHeader("eventType", "order.created")
        .build();

Message<?> output = metadataProcessor.postProcessMessage(input);

assert output.getPayload().equals("ORD-92");
assert output.getHeaders().get("traceId").equals("trace-92");
assert output.getHeaders().get("producer").equals("checkout");
~~~

Trong dự án thực tế, dùng JUnit hoặc framework kiểm thử hiện có thay vì chỉ dựa vào Java assert, vì assert có thể bị tắt nếu JVM không bật -ea.

## 12. Lỗi thường gặp

1. **Nghĩ post processor chạy trước converter:** callback nhận Message sau khi converter đã tạo xong.
2. **Dùng post processor với mọi API send:** callback chỉ chạy ở overload có nhận MessagePostProcessor; MessageChannel.send không tự gọi nó.
3. **Trả về null:** hợp đồng yêu cầu trả về Message đã xử lý hoặc Message đầu vào.
4. **Sửa trực tiếp MessageHeaders:** map headers không phải cấu trúc để sửa tại chỗ; hãy tạo Message mới bằng MessageBuilder.
5. **Ghi đè header không chủ ý:** setHeader thay giá trị cũ; hãy kiểm tra trước nếu cần giữ metadata hiện có.
6. **Thay payload khi chỉ muốn thêm metadata:** dùng fromMessage để giữ payload và các header khác.
7. **Đưa logic nghiệp vụ nặng vào callback:** post processor nằm trong đường gửi và có thể tăng latency.
8. **Lưu request metadata trong field mutable của processor:** nhiều thread có thể dùng chung instance và trộn metadata giữa các Message.
9. **Dùng converter để làm việc của post processor:** converter chịu trách nhiệm biểu diễn payload; post processor chịu trách nhiệm điều chỉnh Message đã tạo.
10. **Nhầm ChannelInterceptor với MessagePostProcessor:** một callback gắn với lần gọi template; callback kia can thiệp ở ranh giới channel.
11. **Nhầm Spring Messaging với Spring JMS:** hai package có thể có interface cùng tên nhưng kiểu Message khác nhau.
12. **Cho rằng thêm header là đã truyền được qua mọi broker:** adapter có thể chỉ hỗ trợ một tập metadata nhất định hoặc ánh xạ header theo quy tắc giao thức.

## 13. Câu hỏi tự kiểm tra

1. MessagePostProcessor thuộc package nào?
2. Phương thức postProcessMessage nhận và trả về kiểu dữ liệu gì?
3. Vì sao post processor được gọi sau MessageConverter?
4. Overload convertAndSend nào nhận MessagePostProcessor?
5. Làm thế nào để thêm traceId mà vẫn giữ payload và các header khác?
6. Điều gì xảy ra khi setHeader ghi vào một key đã tồn tại?
7. Vì sao không được trả về null từ postProcessMessage?
8. MessagePostProcessor khác ChannelInterceptor ở phạm vi áp dụng như thế nào?
9. Request post processor trong convertSendAndReceive xử lý request hay reply?
10. Vì sao không nên gọi HTTP hoặc truy vấn database nặng trong callback?
11. Tại sao cần kiểm tra package khi gặp một interface tên MessagePostProcessor?
12. Những metadata nào không nên ghi đè hoặc đưa vào headers?

## 14. Kết luận

MessagePostProcessor là callback của Spring Messaging để xử lý một Message sau khi nó được tạo, thường là sau bước chuyển payload bằng MessageConverter và trước khi template gửi Message tới channel. Nó phù hợp để thêm trace ID, correlation ID, event type, source hoặc metadata theo từng lần gửi.

Khi dùng callback, hãy tạo Message mới bằng MessageBuilder.fromMessage nếu chỉ muốn bổ sung headers; chú ý setHeader có thể thay giá trị đã tồn tại và không được trả về null. Phân biệt rõ converter, post processor và channel interceptor để đặt logic đúng nơi. Giữ callback ngắn, an toàn khi chạy đồng thời và không dùng metadata như một cơ chế xác thực.

## Tài liệu tham khảo chính thức

- Spring Framework MessagePostProcessor API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessagePostProcessor.html
- Spring Framework MessageSendingOperations API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessageSendingOperations.html
- Spring Framework MessageBuilder API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html
- Spring Framework MessageConverter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConverter.html
- Spring Integration MessagingTemplate reference: https://docs.spring.io/spring-integration/reference/6.5/channel/template.html
- Spring Integration MessagingTemplate API: https://docs.spring.io/spring-integration/api/org/springframework/integration/core/MessagingTemplate.html
