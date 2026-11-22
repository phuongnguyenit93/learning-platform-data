# REPLY_CHANNEL và ERROR_CHANNEL trong hợp đồng trao đổi

Trong một luồng messaging, consumer cần biết phải gửi kết quả về đâu khi xử lý thành công và chuyển thông tin lỗi đến đâu khi xử lý thất bại. Spring Integration sử dụng hai header quy ước là **replyChannel** và **errorChannel** để hỗ trợ hai đường đi này.

- **replyChannel** chỉ nơi nhận phản hồi của một message theo mô hình request/reply.
- **errorChannel** chỉ nơi tiếp nhận thông tin lỗi trong những luồng có cơ chế phát lỗi qua channel.

Hai header này là metadata điều khiển luồng trao đổi. Chúng không phải payload nghiệp vụ, không phải địa chỉ mạng phổ quát và cũng không tự tạo ra hành vi định tuyến chỉ bằng việc thêm một key vào message. Channel, endpoint, gateway, adapter hoặc cơ chế xử lý lỗi phải đọc và thực thi hợp đồng đó.

## 1. Vị trí của hai header trong Message

Một message của Spring Messaging có payload và headers. Payload chứa dữ liệu cần xử lý; headers mang metadata giúp các thành phần phối hợp.

Ví dụ một request có thể gồm:

~~~text
Message<OrderRequest>
    |
    +-- payload
    |     orderId
    |     customerId
    |
    +-- headers
          replyChannel
          errorChannel
          correlationId
          id
          timestamp
~~~

Trong đó:

- Payload mô tả yêu cầu nghiệp vụ, ví dụ tạo đơn hàng.
- replyChannel cung cấp đường trả kết quả nếu luồng hỗ trợ request/reply.
- errorChannel cung cấp đường chuyển thông tin lỗi khi endpoint hoặc cơ chế xử lý lỗi sử dụng header này.
- correlationId giúp liên kết request với reply hoặc các message cùng một giao dịch logic.
- id và timestamp là metadata của message do Spring Messaging quản lý.

Không nên đưa đối tượng channel vào payload chỉ để consumer biết nơi trả kết quả. Payload nên giữ hợp đồng nghiệp vụ ổn định; thông tin điều khiển trao đổi thuộc headers.

### Tên header và giá trị

Tên header được sử dụng theo quy ước:

- **replyChannel**
- **errorChannel**

Trong các luồng Spring Integration, giá trị header thường có thể là một đối tượng MessageChannel hoặc tên channel dạng String nếu cơ chế phân giải channel của luồng đó hỗ trợ. Một tham chiếu MessageChannel phù hợp cho trao đổi trong cùng ứng dụng/JVM; tên channel có thể thuận tiện khi cấu hình và phân giải qua registry.

Không phải mọi transport hoặc framework đều hiểu các header này. Nếu message rời khỏi ứng dụng qua JMS, Kafka hoặc một adapter khác, cần kiểm tra header mapper và quy tắc chuyển đổi. Không nên giả định một Java object MessageChannel có thể serialize và truyền qua broker.

## 2. REPLY_CHANNEL: đường trả lời trong request/reply

Request/reply là mô hình trong đó một thành phần gửi yêu cầu và mong đợi một kết quả tương ứng. Khác với publish/subscribe, requester thường cần nhận kết quả xử lý cho chính request đã gửi.

Một luồng tổng quát:

~~~text
Requester
   |
   | Request + replyChannel
   v
Request Channel
   |
   v
Service / Message Handler
   |
   | tạo kết quả
   v
replyChannel
   |
   v
Requester nhận Reply
~~~

Header replyChannel giúp thành phần xử lý biết nơi gửi response. Trong Spring Integration, các gateway và message-producing endpoint có thể tham gia cơ chế request/reply và sử dụng thông tin phản hồi theo cấu hình của endpoint.

### Khi nào cần replyChannel?

Dùng replyChannel khi:

- Một request cần nhận kết quả từ service xử lý.
- Một message flow có nhiều endpoint và kết quả cần quay về requester ban đầu.
- Muốn tách channel nhận request khỏi channel nhận response.
- Một thành phần xử lý cần trả lời về kênh do phía gửi chỉ định.

Không phải mọi message đều cần replyChannel. Event thông báo một sự kiện đã xảy ra thường là one-way: producer phát event và không chờ một reply nghiệp vụ. Nếu cần xác nhận giao nhận, đó là một cơ chế khác với response nghiệp vụ.

### Reply và correlation

Trong hệ thống có nhiều request đồng thời, requester cần biết reply nào thuộc request nào. Header replyChannel xác định đường trả lời; correlation ID xác định mối liên hệ logic giữa request và response.

Hai khái niệm này bổ sung cho nhau:

| Metadata | Trả lời câu hỏi |
|---|---|
| replyChannel | Gửi phản hồi về đâu? |
| correlationId | Phản hồi thuộc request hoặc luồng xử lý nào? |
| message id | Đây là message instance nào? |

Không dùng message ID thay cho correlation ID nếu hai phía cần cùng một giá trị để liên kết request/reply. Message được tạo mới cho reply có thể có ID riêng.

Trong một số request/reply flow, framework có thể tự quản lý correlation hoặc reply destination. Khi tự thiết kế flow, hãy thống nhất cách tạo, sao chép và kiểm tra correlation ID, đặc biệt khi request đi qua broker hoặc nhiều service.

## 3. ERROR_CHANNEL: đường chuyển thông tin lỗi

Trong một message flow, lỗi có thể phát sinh khi:

- Payload không hợp lệ hoặc không chuyển đổi được.
- Service nghiệp vụ ném exception.
- Một endpoint không thể kết nối hệ thống bên ngoài.
- Consumer xử lý timeout hoặc gặp lỗi tạm thời.
- Một bước định tuyến không tìm được đích phù hợp.

Header errorChannel cung cấp thông tin về channel có thể nhận thông báo lỗi cho message tương ứng trong các cơ chế hỗ trợ nó. Spring Integration dùng ErrorMessage để biểu diễn lỗi được chuyển qua message channel.

### ErrorMessage

ErrorMessage là message chuyên biệt có payload là Throwable. Nó có thể mang thêm ngữ cảnh về message gốc để bộ xử lý lỗi biết request nào gây ra sự cố.

~~~text
Request Message
      |
      v
Message Handler
      |
      | exception
      v
ErrorMessage
   |
   +-- payload: Throwable
   |
   +-- original message/context
   |
   v
errorChannel
   |
   v
Error Handler / Recovery Flow
~~~

Bộ xử lý lỗi có thể ghi log, phân loại lỗi, gửi cảnh báo, lưu thông tin vào kho lỗi hoặc chuyển message sang dead-letter flow. Việc retry hay bỏ qua message phải theo chính sách cụ thể của ứng dụng và transport.

### ERROR_CHANNEL không đồng nghĩa với retry

Chuyển lỗi sang errorChannel chỉ định tuyến thông tin lỗi đến nơi xử lý. Nó không tự động retry, rollback database, acknowledge broker hay bảo đảm message được xử lý lại.

Các quyết định này thuộc tầng xử lý lỗi và cơ chế giao nhận:

- Retry có giới hạn với backoff cho lỗi tạm thời.
- Không retry vô hạn với lỗi dữ liệu không hợp lệ.
- Chuyển sang dead-letter queue hoặc nơi lưu trữ lỗi sau khi hết retry.
- Giữ correlation ID và thông tin nguồn để điều tra.
- Chỉ acknowledge hoặc commit khi phù hợp với transaction và delivery semantics của transport.

Với luồng đồng bộ, exception có thể được truyền ngược về bên gọi. Với luồng bất đồng bộ, lỗi có thể được phát thành ErrorMessage qua error channel, tùy endpoint, executor, gateway và cấu hình error handling. Vì vậy cần xác định rõ flow đang chạy đồng bộ hay bất đồng bộ trước khi thiết kế kỳ vọng về lỗi.

## 4. Phân biệt replyChannel và errorChannel

| Tiêu chí | replyChannel | errorChannel |
|---|---|---|
| Mục đích | Nhận kết quả xử lý thành công. | Nhận thông tin lỗi. |
| Ngữ cảnh | Request/reply. | Error handling và recovery. |
| Nội dung thường nhận | Message chứa response payload nghiệp vụ. | ErrorMessage chứa Throwable và có thể có original message. |
| Người tiêu thụ | Requester hoặc bước tiếp theo trong reply flow. | Error handler, recovery flow hoặc nơi giám sát lỗi. |
| Có phải luôn cần? | Không; chỉ khi cần reply. | Không; tùy cơ chế xử lý lỗi. |
| Có tự retry không? | Không. | Không. |
| Quan hệ với correlation | Giúp xác định nơi trả lời; correlation ID liên kết response với request. | Nên giữ correlation và nguồn message để xác định lỗi thuộc request nào. |

Một request có thể có cả hai header. Khi xử lý thành công, flow gửi reply đến replyChannel. Khi xử lý thất bại, flow hoặc error-handling mechanism chuyển ErrorMessage đến errorChannel. Hai đường đi không nên bị trộn lẫn thành một payload kết quả chứa cờ success/error nếu kiến trúc cần phân biệt rõ response và exception.

## 5. Tạo message và gắn hai header

Spring MessageBuilder giúp gắn metadata vào message:

~~~java
Message<OrderRequest> request = MessageBuilder
        .withPayload(new OrderRequest("ORD-1001"))
        .setHeader("replyChannel", replyChannel)
        .setHeader("errorChannel", errorChannel)
        .setHeader("correlationId", "checkout-001")
        .build();
~~~

Ví dụ này giả định replyChannel và errorChannel đã được khai báo là các MessageChannel phù hợp. MessageBuilder chỉ lưu các giá trị header. Việc thực sự gửi response hoặc ErrorMessage cần endpoint, gateway, handler hoặc code điều phối đọc và sử dụng chúng.

Không nên gắn header bằng một tên tùy ý rồi mong mọi Spring component tự hiểu. Cần dùng đúng tên quy ước và kiểm tra component nhận message có hỗ trợ semantics tương ứng.

### Kênh phản hồi có thể được cấu hình riêng

Có thể dùng DirectChannel khi cần chuyển message đến subscriber ngay trong luồng gửi đồng bộ, hoặc QueueChannel khi muốn lưu message trong queue nội bộ để thành phần khác nhận sau. Lựa chọn channel ảnh hưởng đến cách dispatch, threading và backpressure.

Tên channel chỉ có ý nghĩa trong phạm vi cấu hình ứng dụng. Nếu dùng String làm giá trị header, flow phải có khả năng phân giải tên đó thành channel. Nếu dùng trực tiếp MessageChannel reference, không nên chuyển nguyên reference đó qua ranh giới serialization.

## 6. Ví dụ Java: định tuyến reply và error rõ ràng

Ví dụ sau dùng Spring Integration Core để tạo ba DirectChannel: request, reply và error. Handler đọc hai header từ request và chủ động gửi kết quả hoặc ErrorMessage đến đúng channel.

Đây là ví dụ minh họa hợp đồng định tuyến bằng một handler tự viết. Nó cho thấy việc thêm header không tự chạy logic định tuyến; handler đọc header và thực hiện send.

### Maven

Tạo file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reply-error-channel-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.3.0</version>
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
                <version>3.2.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### Java

Tạo file src/main/java/com/example/messaging/ReplyErrorChannelExample.java:

~~~java
package com.example.messaging;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

public class ReplyErrorChannelExample {

    public static void main(String[] args) {
        DirectChannel requests = new DirectChannel();
        DirectChannel replies = new DirectChannel();
        DirectChannel errors = new DirectChannel();

        replies.subscribe(message ->
                System.out.println("reply=" + message.getPayload()));

        errors.subscribe(message -> {
            ErrorMessage errorMessage = (ErrorMessage) message;
            System.out.println(
                    "error=" + errorMessage.getPayload().getMessage()
            );
        });

        requests.subscribe(request -> {
            MessageChannel replyChannel =
                    (MessageChannel) request.getHeaders().get("replyChannel");
            MessageChannel errorChannel =
                    (MessageChannel) request.getHeaders().get("errorChannel");

            try {
                String command = (String) request.getPayload();

                if ("fail".equals(command)) {
                    throw new IllegalArgumentException("invalid request");
                }

                replyChannel.send(
                        MessageBuilder
                                .withPayload("accepted: " + command)
                                .setHeader(
                                        "correlationId",
                                        request.getHeaders().get("correlationId")
                                )
                                .build()
                );
            }
            catch (RuntimeException exception) {
                errorChannel.send(new ErrorMessage(exception, request));
            }
        });

        requests.send(createRequest("order-1001", replies, errors));
        requests.send(createRequest("fail", replies, errors));
    }

    private static Message<String> createRequest(
            String payload,
            MessageChannel replies,
            MessageChannel errors) {
        return MessageBuilder
                .withPayload(payload)
                .setHeader("replyChannel", replies)
                .setHeader("errorChannel", errors)
                .setHeader("correlationId", "checkout-001")
                .build();
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.ReplyErrorChannelExample
~~~

Output:

~~~text
reply=accepted: order-1001
error=invalid request
~~~

Diễn giải:

1. Request đầu tiên mang payload order-1001. Handler đọc replyChannel và gửi response thành công đến channel đó.
2. Request thứ hai mang payload fail. Handler phát sinh exception, tạo ErrorMessage kèm request gốc và gửi đến errorChannel.
3. Subscriber của reply channel chỉ nhận response thành công.
4. Subscriber của error channel nhận ErrorMessage và đọc exception từ payload.

Ví dụ dùng DirectChannel nên việc gửi và xử lý diễn ra đồng bộ trong luồng hiện tại. Với QueueChannel, executor hoặc broker adapter, thời điểm xử lý và cách exception được truyền có thể khác. Trong ứng dụng thật, cần cấu hình transaction, retry, acknowledgment và recovery phù hợp.

## 7. Tích hợp qua broker và ranh giới hệ thống

replyChannel và errorChannel thường là metadata điều khiển nội bộ của Spring Integration. Khi gửi message qua JMS, Kafka hoặc transport khác, cần xác định cách biểu diễn địa chỉ ở phía transport.

Ví dụ:

- Trong JMS, reply destination có thể là một Queue hoặc Topic và có thể được biểu diễn bằng JMSReplyTo.
- Trong Kafka, reply flow thường cần topic đích và correlation key/header theo contract ứng dụng.
- Trong WebSocket/STOMP, destination là chuỗi theo quy ước endpoint/broker; không phải MessageChannel object.

Không nên truyền trực tiếp đối tượng channel Java qua broker. Thay vào đó, adapter có thể ánh xạ tên channel logic sang destination bên ngoài, hoặc dùng metadata transport-specific theo hợp đồng đã thống nhất.

Cần kiểm tra header mapper vì không phải mọi header nội bộ đều được gửi ra ngoài. Một số header có thể bị bỏ qua có chủ đích vì không serialize được hoặc không phù hợp với giao thức đích.

### Bảo toàn correlation qua nhiều hop

Khi request đi qua nhiều service:

1. Producer tạo correlation ID ổn định cho request.
2. Adapter chuyển metadata cần thiết sang header/property của transport.
3. Consumer đọc correlation ID và giữ nó khi tạo reply hoặc ErrorMessage.
4. Reply/error handler dùng correlation ID để ghi log, ghép kết quả và truy vết.
5. Không phụ thuộc vào ID message do từng tầng tạo vì ID có thể thay đổi khi chuyển đổi hoặc tạo message mới.

Với request/reply bất đồng bộ, cần có timeout và chính sách xử lý reply đến muộn. Reply channel đã bị đóng hoặc requester không còn chờ có thể khiến response không được tiêu thụ. Hệ thống nên có correlation store, timeout hoặc nơi xử lý reply không còn người nhận nếu bài toán yêu cầu.

## 8. Thiết kế hợp đồng lỗi có thể vận hành

Một error channel hữu ích khi thông tin lỗi đủ để điều tra và quyết định hành động. Khi xử lý lỗi, nên giữ:

- Correlation ID và message ID liên quan.
- Loại exception hoặc mã lỗi ổn định.
- Thông tin message gốc ở mức cần thiết.
- Tên flow/endpoint phát sinh lỗi.
- Số lần thử hoặc delivery attempt nếu transport cung cấp.
- Phân loại lỗi tạm thời và lỗi dữ liệu/logic không thể retry.

Không nên gửi toàn bộ stack trace hoặc payload nhạy cảm vào một channel được nhiều thành phần cùng truy cập nếu không có kiểm soát. Có thể ghi chi tiết vào log bảo mật, còn ErrorMessage chỉ mang mã lỗi và thông tin tham chiếu.

Chính sách xử lý nên phân biệt:

| Loại lỗi | Hướng xử lý thường cân nhắc |
|---|---|
| Lỗi kết nối tạm thời | Retry có giới hạn, backoff và jitter. |
| Rate limit từ hệ thống ngoài | Tôn trọng thời gian chờ, retry theo chính sách. |
| Payload/schema không hợp lệ | Đưa vào quarantine hoặc dead-letter flow; không retry vô hạn. |
| Lỗi nghiệp vụ từ chối hợp lệ | Trả response nghiệp vụ rõ ràng nếu đây là kết quả dự kiến, không nhất thiết coi là infrastructure error. |
| Lỗi lập trình không mong đợi | Ghi nhận, cảnh báo và xử lý theo chính sách vận hành; tránh che giấu exception. |

Một từ chối nghiệp vụ như “hết hàng” có thể là reply hợp lệ, dù kết quả không thành công theo góc nhìn người dùng. ERROR_CHANNEL nên dành cho exception hoặc lỗi xử lý theo hợp đồng kỹ thuật, trừ khi hệ thống chủ động định nghĩa khác.

## 9. Những nhầm lẫn thường gặp

1. **“Chỉ cần thêm replyChannel là Spring tự gửi mọi kết quả về đó.”** Không đúng với mọi MessageChannel và handler. Cần endpoint hoặc flow có hỗ trợ request/reply, hoặc handler tự đọc header và gửi response.
2. **“errorChannel là nơi chứa mọi lỗi của toàn ứng dụng.”** Không nhất thiết. Có thể có error channel riêng theo message, channel mặc định của integration infrastructure hoặc cơ chế exception propagation tùy flow.
3. **“errorChannel tự retry message.”** Không đúng. Nó định tuyến thông tin lỗi; retry và recovery phải được cấu hình riêng.
4. **“replyChannel và errorChannel có thể dùng chung mà không cần phân loại.”** Không nên nếu consumer cần phân biệt response nghiệp vụ với ErrorMessage và áp dụng chính sách khác nhau.
5. **“Đặt tên header destination là đủ để định tuyến.”** Không đúng. Chỉ thành phần được cấu hình đọc header đó mới thực hiện routing.
6. **“MessageChannel object có thể gửi qua JMS/Kafka.”** Không nên giả định như vậy. Đây là tham chiếu nội bộ; cần ánh xạ sang địa chỉ transport có thể serialize.
7. **“Message ID chính là correlation ID.”** Không đúng. Message mới có thể có ID mới; correlation ID phải được giữ ổn định theo request.
8. **“Mọi exception đều phải đi vào errorChannel.”** Không đúng. Exception đồng bộ có thể truyền ngược caller; asynchronous endpoint và adapter có cơ chế xử lý riêng.
9. **“Lỗi nghiệp vụ và lỗi kỹ thuật là một.”** Không nhất thiết. Một kết quả từ chối nghiệp vụ có thể là reply hợp lệ; exception hạ tầng hoặc lỗi xử lý mới đi theo error flow.

## 10. Ghi nhớ

- **replyChannel** là đường nhận response của request/reply flow.
- **errorChannel** là đường nhận thông tin lỗi trong cơ chế error handling hỗ trợ channel.
- Hai header là metadata điều khiển; chúng không phải payload và không tự kích hoạt routing.
- Reply channel nhận kết quả; error channel thường nhận ErrorMessage chứa Throwable và ngữ cảnh message gốc.
- Correlation ID liên kết request/reply/error; message ID nhận diện từng message instance.
- Error routing không tự bảo đảm retry, rollback, acknowledgment hoặc dead-letter.
- Khi đi qua broker, cần ánh xạ channel nội bộ sang destination của transport và kiểm tra header mapping.

Một hợp đồng trao đổi tốt xác định trước nơi trả kết quả, nơi chuyển lỗi, cách liên kết các message và ai chịu trách nhiệm retry hoặc recovery. Nhờ vậy, cả luồng thành công lẫn luồng thất bại đều có thể quan sát và vận hành rõ ràng.
