# Thông điệp là gì và bài toán giao tiếp giữa các thành phần

Trong một ứng dụng Spring, các thành phần như service, controller, repository hoặc các tiến trình độc lập cần trao đổi dữ liệu và phối hợp công việc. Cách đơn giản nhất là gọi trực tiếp phương thức của nhau. Tuy nhiên, khi hệ thống lớn hơn, cách giao tiếp này có thể tạo ra phụ thuộc chặt, khiến một thành phần phải biết thành phần kia ở đâu, cung cấp API nào và có đang sẵn sàng hay không.

Messaging (giao tiếp bằng thông điệp) là cách các thành phần trao đổi thông tin thông qua những thông điệp có cấu trúc. Thành phần gửi tạo thông điệp và chuyển nó tới một kênh hoặc hệ thống trung gian; thành phần nhận lấy thông điệp và xử lý. Cách tổ chức này giúp tách nơi phát sinh công việc khỏi nơi thực hiện công việc, đồng thời hỗ trợ xử lý bất đồng bộ, phân phối cho nhiều người nhận và tích hợp các hệ thống khác nhau.

## 1. Bài toán giao tiếp giữa các thành phần

Hãy xét quy trình tạo đơn hàng. Sau khi khách hàng đặt hàng, hệ thống có thể cần:

- Lưu đơn hàng.
- Kiểm tra hoặc giữ tồn kho.
- Yêu cầu thanh toán.
- Gửi email hoặc thông báo cho khách hàng.
- Cập nhật báo cáo hoặc hệ thống phân tích.

Nếu OrderService gọi trực tiếp tất cả thành phần này, nó phải biết nhiều chi tiết triển khai. Khi dịch vụ gửi email chậm, thao tác tạo đơn hàng có thể bị kéo dài. Khi dịch vụ thanh toán tạm thời không hoạt động, lời gọi đồng bộ có thể thất bại và ảnh hưởng đến luồng chính. Khi cần thêm một người nhận mới, mã của bên gửi có thể phải thay đổi.

Những khó khăn thường gặp gồm:

**Phụ thuộc chặt:** bên gửi biết rõ lớp, API hoặc địa chỉ của bên nhận. Thay đổi ở một bên có thể buộc bên còn lại thay đổi theo.

**Phụ thuộc thời gian:** với lời gọi đồng bộ, bên nhận thường phải sẵn sàng ngay lúc bên gửi gọi. Bên gửi có thể phải chờ kết quả.

**Độ trễ và lỗi lan truyền:** một dịch vụ chậm hoặc lỗi có thể làm chậm hoặc làm hỏng toàn bộ chuỗi lời gọi.

**Khó mở rộng và phân phối:** thêm người nhận, tăng số lượng consumer hoặc phân phối tải có thể đòi hỏi sửa nhiều điểm kết nối.

**Khó tích hợp khác công nghệ:** các hệ thống có thể chạy ở tiến trình, máy chủ hoặc ngôn ngữ khác nhau; gọi trực tiếp đối tượng Java không phù hợp để kết nối chúng.

Messaging tạo ra một hợp đồng trao đổi thông tin rõ ràng. Bên gửi chỉ cần biết cách tạo thông điệp và nơi gửi; bên nhận chỉ cần biết cách nhận và diễn giải thông điệp theo hợp đồng đã thống nhất.

## 2. Thông điệp là gì?

Thông điệp (message) là một đơn vị dữ liệu được đóng gói để truyền từ nơi gửi đến nơi nhận. Trong Spring Messaging, một thông điệp thường có hai phần:

- **Payload:** nội dung chính mà bên nhận cần xử lý, ví dụ thông tin đơn hàng, yêu cầu thanh toán hoặc dữ liệu trạng thái.
- **Headers:** metadata đi kèm payload, ví dụ loại sự kiện, mã tương quan, nguồn gửi, thời điểm hoặc thông tin định tuyến.

Có thể hình dung cấu trúc như sau:

~~~text
Message
├── Payload
│   └── OrderPlaced { orderId, customerId, total }
└── Headers
    ├── eventType: order.placed
    ├── correlationId: ...
    └── source: order-service
~~~

Payload trả lời câu hỏi “thông tin hoặc công việc cần truyền là gì?”. Header trả lời các câu hỏi “thông điệp thuộc luồng nào?”, “được gửi từ đâu?” hoặc “consumer cần định tuyến và quan sát nó ra sao?”.

Trong Spring Messaging, giao diện Message<T> biểu diễn một thông điệp có payload kiểu T và tập MessageHeaders. MessageHeaders cung cấp metadata theo dạng key/value. Các header chuẩn có thể chứa ID và timestamp; ứng dụng cũng có thể thêm header riêng. Header của một Message là bất biến sau khi thông điệp được tạo. Khi cần tạo thông điệp mới hoặc bổ sung metadata, hãy dùng MessageBuilder.

Ví dụ về một payload nghiệp vụ:

~~~json
{
  "orderId": "ORD-1024",
  "customerId": "CUS-81",
  "total": 1250000
}
~~~

Thông điệp có thể mang payload là một đối tượng Java khi giao tiếp trong cùng tiến trình. Khi đi qua mạng hoặc broker, payload thường cần được chuyển thành định dạng truyền tải như JSON, Avro hoặc Protobuf. Không nên mặc định rằng một đối tượng Java bất kỳ có thể được gửi nguyên trạng giữa các ứng dụng khác nhau.

### Phân biệt command, event và request/reply

Ba dạng thông điệp thường gặp có ý nghĩa khác nhau:

| Dạng | Ý nghĩa | Ví dụ |
|---|---|---|
| Command | Yêu cầu một thành phần thực hiện hành động | ReserveStock, ChargePayment |
| Event | Thông báo một việc đã xảy ra | OrderPlaced, PaymentCompleted |
| Request/reply | Gửi câu hỏi và chờ một phản hồi tương ứng | GetOrderStatus → OrderStatus |

Command thường hướng tới một nơi có trách nhiệm thực hiện hành động. Event mô tả sự kiện đã xảy ra và có thể có nhiều consumer quan tâm. Request/reply có quan hệ tương quan giữa yêu cầu và phản hồi; dù được truyền qua messaging, mô hình này vẫn có thể khiến bên gọi phải chờ.

Đặt tên event theo sự kiện đã xảy ra, chẳng hạn OrderPlaced. Đặt tên command theo hành động cần thực hiện, chẳng hạn PlaceOrder hoặc ReserveStock. Phân biệt hai loại này giúp consumer hiểu liệu nó đang nhận một yêu cầu hay một thông tin về sự kiện trong quá khứ.

## 3. Luồng xử lý thông điệp

Một luồng messaging cơ bản có các vai trò sau:

~~~text
Producer
   |
   | tạo Message (payload + headers)
   v
MessageChannel hoặc broker
   |
   | chuyển / lưu / phân phối
   v
Consumer (MessageHandler)
   |
   | kiểm tra và xử lý payload
   v
Kết quả nghiệp vụ
~~~

**Producer** là thành phần tạo và gửi thông điệp. Producer không nhất thiết phải biết consumer cụ thể nào sẽ xử lý.

**Message** là gói dữ liệu có cấu trúc, gồm payload và headers.

**Channel** là điểm giao tiếp logic mà producer gửi thông điệp vào. Channel có thể đại diện cho một đường truyền trong cùng tiến trình hoặc là một phần của luồng tích hợp rộng hơn.

**Consumer** là thành phần nhận và xử lý thông điệp. Consumer cần hiểu hợp đồng dữ liệu, kiểm tra tính hợp lệ và thực hiện nghiệp vụ phù hợp.

**Broker** là hạ tầng trung gian có thể nhận, lưu trữ và phân phối thông điệp giữa các tiến trình. Broker thường hữu ích khi cần giao tiếp qua mạng, lưu thông điệp để xử lý sau, phân phối tải hoặc hỗ trợ nhiều consumer.

Không phải mọi luồng messaging đều cần broker. Một ứng dụng có thể dùng channel trong cùng tiến trình. Ngược lại, khi cần lưu trữ bền vững, truyền qua mạng hoặc vận hành độc lập giữa nhiều dịch vụ, cần chọn một hạ tầng truyền tải phù hợp.

## 4. Các abstraction messaging trong Spring Framework

Spring Framework cung cấp module Spring Messaging với những abstraction cốt lõi. Các abstraction này giúp mô hình hóa thông điệp và điểm gửi/nhận mà không buộc mã nghiệp vụ phụ thuộc vào một giao thức cụ thể.

| Abstraction | Vai trò |
|---|---|
| Message<T> | Biểu diễn payload và headers của một thông điệp |
| MessageHeaders | Chứa metadata của thông điệp |
| MessageBuilder<T> | Tạo Message và thiết lập payload/header |
| MessageChannel | Abstraction để gửi Message |
| SubscribableChannel | Channel cho phép MessageHandler đăng ký nhận thông điệp |
| PollableChannel | Channel mà consumer chủ động lấy thông điệp bằng thao tác receive |
| MessageHandler | Hợp đồng xử lý một Message |

Một số điểm cần hiểu rõ:

- MessageChannel định nghĩa thao tác gửi. Bản thân interface này không khẳng định thông điệp sẽ được xử lý đồng bộ hay bất đồng bộ.
- SubscribableChannel thường dùng mô hình đẩy: handler đăng ký trước và được gọi khi có thông điệp.
- PollableChannel dùng mô hình kéo: consumer chủ động gọi receive, có thể chờ trong một khoảng thời gian tùy implementation.
- MessageHandler nhận Message<?> và thực hiện logic xử lý.
- MessageBuilder giúp tạo thông điệp có payload và metadata mà không phải tự quản lý việc khởi tạo MessageHeaders.

Các interface trên là abstraction. Cách lưu trữ, định tuyến, đồng bộ, bất đồng bộ và bảo đảm giao nhận phụ thuộc vào implementation hoặc hạ tầng được kết nối. Spring Messaging tự nó không phải là một message broker.

Trong hệ sinh thái Spring:

- Spring Integration bổ sung các channel, endpoint, adapter và luồng tích hợp để kết nối ứng dụng với nhiều nguồn dữ liệu hoặc giao thức.
- Spring WebSocket hỗ trợ mô hình messaging trên WebSocket, bao gồm STOMP.
- Các giải pháp tích hợp JMS, AMQP hoặc Kafka cung cấp cách kết nối với những hệ thống truyền thông điệp tương ứng.

Khi chọn thư viện, hãy xác định rõ nhu cầu giao tiếp trước: chỉ trao đổi trong cùng tiến trình, kết nối qua WebSocket, hay gửi thông điệp bền vững qua broker. Sau đó mới chọn implementation và adapter phù hợp.

## 5. Ví dụ: tạo và gửi một Message bằng Spring Messaging

Ví dụ sau minh họa cách tạo một Message có payload và headers, sau đó gửi qua một implementation MessageChannel đơn giản. Channel trong ví dụ gọi handler ngay trong cùng luồng thực thi để minh họa hợp đồng gửi/nhận của Spring Messaging.

Ví dụ này dùng Java 17 và Spring Messaging 6.2.8. Trong dự án Spring Boot, nên để Spring Boot dependency management quản lý phiên bản Spring thay vì tự ghim từng module.

Cấu trúc thư mục:

~~~text
spring-messaging-intro/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MessagingDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-messaging-intro</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.8</version>
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

### src/main/java/demo/MessagingDemo.java

~~~java
package demo;

import java.util.Objects;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

public class MessagingDemo {

    public static void main(String[] args) {
        MessageHandler receiver = message -> {
            System.out.println("Received payload: " + message.getPayload());
            System.out.println("Event type: " + message.getHeaders().get("eventType"));
            System.out.println("Correlation ID: " + message.getHeaders().get("correlationId"));
        };

        MessageChannel channel = new InMemoryMessageChannel(receiver);

        Message<String> message = MessageBuilder
                .withPayload("Order #1024 created")
                .setHeader("eventType", "order.created")
                .setHeader("correlationId", "corr-001")
                .build();

        channel.send(message);
    }

    private static final class InMemoryMessageChannel implements MessageChannel {

        private final MessageHandler handler;

        private InMemoryMessageChannel(MessageHandler handler) {
            this.handler = Objects.requireNonNull(handler, "handler");
        }

        @Override
        public boolean send(Message<?> message) {
            return send(message, MessageChannel.INDEFINITE_TIMEOUT);
        }

        @Override
        public boolean send(Message<?> message, long timeout) {
            Objects.requireNonNull(message, "message");
            handler.handleMessage(message);
            return true;
        }
    }
}
~~~

Chạy chương trình từ thư mục có pom.xml:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.MessagingDemo
~~~

Kết quả:

~~~text
Received payload: Order #1024 created
Event type: order.created
Correlation ID: corr-001
~~~

Giải thích:

1. MessageHandler đại diện cho phía nhận. Lambda đọc payload và hai header từ thông điệp.
2. MessageBuilder.withPayload(...) tạo thông điệp với payload kiểu String.
3. setHeader(...) bổ sung metadata eventType và correlationId.
4. build() hoàn tất việc tạo Message<String>.
5. MessageChannel.send(message) chuyển thông điệp đến handler trong implementation của ví dụ.
6. Handler đọc dữ liệu từ Message mà không cần biết producer đã tạo đối tượng ở đâu.

InMemoryMessageChannel là implementation tối giản do ví dụ tự định nghĩa. Nó gọi handler trực tiếp, đồng bộ và trong cùng tiến trình; tham số timeout không cần dùng vì không có thao tác chờ. Nó không có hàng đợi, lưu trữ bền vững, retry hay broker. Mục đích của nó là làm rõ hợp đồng MessageChannel và MessageHandler, không phải cung cấp hạ tầng messaging cho môi trường production.

## 6. Những kiểu giao tiếp thường gặp

Messaging có nhiều cách tổ chức. Cần phân biệt chúng vì mỗi kiểu giải quyết một bài toán khác nhau.

### Đồng bộ và bất đồng bộ

**Đồng bộ (synchronous):** thao tác gửi có thể gọi trực tiếp consumer và chờ xử lý hoàn tất. Bên gửi chịu ảnh hưởng bởi thời gian xử lý và lỗi của bên nhận. Cách này đơn giản, dễ theo dõi luồng chạy nhưng mức độ tách rời thấp hơn.

**Bất đồng bộ (asynchronous):** bên gửi chuyển thông điệp và tiếp tục công việc mà không cần đợi consumer hoàn tất. Consumer xử lý sau, có thể ở thread hoặc tiến trình khác. Cách này giúp giảm phụ thuộc thời gian, nhưng cần xử lý trạng thái, lỗi, retry và quan sát luồng công việc.

Không nên suy luận rằng cứ dùng MessageChannel là hệ thống tự động bất đồng bộ. Tính đồng bộ phụ thuộc vào channel implementation và cách cấu hình luồng xử lý.

### Point-to-point và publish/subscribe

**Point-to-point:** một thông điệp được phân phối để một consumer trong nhóm xử lý. Mô hình này phù hợp với hàng đợi công việc, ví dụ mỗi đơn hàng cần được một worker xử lý.

**Publish/subscribe:** một sự kiện được phát tới nhiều subscriber quan tâm. Mô hình này phù hợp khi OrderPlaced cần kích hoạt cập nhật tồn kho, gửi thông báo và ghi nhận phân tích độc lập.

Một broker có thể cung cấp cả hai mô hình, nhưng cách phân phối cụ thể phụ thuộc vào loại broker và cấu hình subscription.

### Request/reply

Bên gửi phát một yêu cầu và nhận phản hồi tương ứng. Cần có correlation ID hoặc cơ chế tương đương để ghép phản hồi với yêu cầu ban đầu, đặc biệt khi nhiều yêu cầu đang được xử lý đồng thời. Request/reply có thể được triển khai qua messaging, nhưng vẫn có đặc tính chờ phản hồi của một giao dịch yêu cầu.

## 7. Những vấn đề cần giải quyết trong hệ thống messaging

Messaging giảm phụ thuộc trực tiếp giữa các thành phần nhưng tạo ra các vấn đề vận hành riêng. Thiết kế thông điệp cần tính đến các tình huống sau.

### Giao nhận và xử lý trùng

Consumer có thể nhận lại cùng một thông điệp khi broker gửi lại sau timeout hoặc khi consumer xử lý xong nhưng xác nhận chưa được ghi nhận. Vì vậy, không nên giả định mỗi thông điệp chỉ đến đúng một lần.

Thiết kế consumer theo hướng idempotent: xử lý lặp một thông điệp không làm phát sinh tác động nghiệp vụ ngoài ý muốn. Có thể dùng message ID, event ID hoặc khóa nghiệp vụ để phát hiện lần xử lý đã hoàn tất.

Các hệ thống thường nói đến những mức giao nhận như at-most-once và at-least-once. Exactly-once end-to-end là mục tiêu khó hơn nhiều, phụ thuộc vào phạm vi transaction, broker, consumer và hệ thống lưu trữ; không thể đạt được chỉ bằng cách thêm một cấu hình gửi thông điệp.

### Thứ tự xử lý

Nhiều broker không bảo đảm thứ tự toàn cục khi có nhiều partition, queue hoặc consumer chạy song song. Nếu nghiệp vụ cần thứ tự theo một thực thể, hãy xác định khóa phân vùng hoặc chiến lược tuần tự hóa phù hợp, chẳng hạn xử lý các event của cùng orderId theo thứ tự.

Không nên dựa vào thứ tự gửi trong một tiến trình để suy ra thứ tự xử lý ở một hệ thống phân tán.

### Retry và thông điệp lỗi

Một lỗi tạm thời như timeout hoặc mất kết nối có thể được thử lại với backoff. Một lỗi dữ liệu hoặc lỗi nghiệp vụ không thể khắc phục bằng retry vô hạn. Cần giới hạn số lần thử, ghi nhận nguyên nhân và có cơ chế đưa thông điệp lỗi sang dead-letter queue hoặc quy trình xử lý thủ công khi hạ tầng hỗ trợ.

Phân biệt lỗi tạm thời với lỗi vĩnh viễn giúp tránh lặp vô hạn và tránh làm nghẽn hàng đợi.

### Hợp đồng dữ liệu và phiên bản

Producer và consumer có thể được triển khai, nâng cấp ở thời điểm khác nhau. Khi cấu trúc payload thay đổi, consumer cũ vẫn có thể nhận thông điệp mới. Vì vậy:

- Đặt tên trường rõ nghĩa và định nghĩa kiểu dữ liệu.
- Chỉ thêm trường mới theo cách tương thích khi có thể.
- Có chiến lược versioning cho thay đổi không tương thích.
- Không đổi ý nghĩa của một trường đang được consumer sử dụng.
- Kiểm tra payload đầu vào và xử lý trường không biết một cách có chủ đích.

### Quan sát và truy vết

Trong một luồng qua nhiều dịch vụ, log của từng thành phần riêng lẻ thường không đủ để tìm nguyên nhân lỗi. Hãy truyền correlation ID hoặc trace context phù hợp qua các thông điệp. Ghi nhận message ID, loại sự kiện, consumer, thời gian xử lý và kết quả xử lý, đồng thời tránh ghi dữ liệu nhạy cảm vào log.

### Backpressure và tải tăng đột biến

Producer có thể gửi nhanh hơn tốc độ consumer xử lý. Khi đó backlog tăng, độ trễ tăng và bộ nhớ hoặc dung lượng lưu trữ có thể bị tiêu thụ quá mức. Cần theo dõi độ dài hàng đợi, tuổi của thông điệp cũ nhất, tốc độ gửi/nhận và tỷ lệ lỗi. Tùy hạ tầng, có thể giới hạn tốc độ producer, điều chỉnh số consumer hoặc áp dụng cơ chế điều tiết tải.

### Bảo mật

Không tin cậy payload chỉ vì nó đến từ một channel hoặc broker nội bộ. Xác thực và phân quyền publisher/consumer, kiểm tra dữ liệu đầu vào, bảo vệ thông tin nhạy cảm và cấu hình mã hóa khi truyền qua mạng. Quyền gửi một loại command có thể khác quyền đăng ký nhận một loại event.

## 8. Nguyên tắc thiết kế thông điệp tốt

Một số nguyên tắc thực tế giúp hệ thống dễ bảo trì hơn:

1. **Thiết kế hợp đồng trước:** xác định tên thông điệp, payload, kiểu dữ liệu, headers và ý nghĩa nghiệp vụ trước khi triển khai producer/consumer.
2. **Giữ payload tập trung vào nghiệp vụ:** chỉ gửi dữ liệu consumer cần. Tránh đưa cả object graph hoặc dữ liệu không liên quan vào thông điệp.
3. **Dùng header cho metadata:** correlation ID, trace context, nguồn phát hoặc thông tin định tuyến phù hợp với header; dữ liệu nghiệp vụ thuộc payload.
4. **Thiết kế consumer idempotent:** giả định có thể nhận lại thông điệp và bảo vệ các thao tác ghi hoặc thanh toán khỏi tác động lặp.
5. **Xác định chính sách lỗi:** quy định timeout, retry, backoff, dead-letter và cách xử lý lỗi không thể phục hồi.
6. **Quản lý phiên bản:** thay đổi schema theo hướng tương thích và có kế hoạch chuyển đổi consumer.
7. **Đo lường luồng xử lý:** theo dõi thông lượng, backlog, độ trễ, tỷ lệ retry và lỗi.
8. **Chọn mức độ phức tạp phù hợp:** không đưa broker vào hệ thống nếu lời gọi phương thức trong cùng ứng dụng đã đáp ứng yêu cầu.

## 9. Khi nào nên dùng messaging?

Messaging phù hợp khi cần một hoặc nhiều đặc tính sau:

- Xử lý công việc nền hoặc tác vụ có thể hoàn tất sau yêu cầu ban đầu.
- Phát một sự kiện để nhiều thành phần độc lập cùng phản ứng.
- Tích hợp các dịch vụ chạy ở tiến trình hoặc công nghệ khác nhau.
- Giảm phụ thuộc thời gian giữa producer và consumer.
- Đệm tải hoặc phân phối công việc cho nhiều worker.
- Ghi nhận sự kiện để các hệ thống khác tiêu thụ theo nhu cầu.

Gọi trực tiếp phương thức thường phù hợp hơn khi thao tác đơn giản, cần kết quả ngay, các thành phần nằm trong cùng ứng dụng và không cần lưu trữ hay phân phối thông điệp. Messaging có thêm chi phí về schema, xử lý lỗi, quan sát và vận hành; không nên áp dụng chỉ vì muốn hệ thống trông có vẻ phân tán.

Một cách lựa chọn thực tế:

| Nhu cầu | Hướng tiếp cận |
|---|---|
| Gọi logic nội bộ và cần kết quả ngay | Gọi phương thức trực tiếp |
| Gửi công việc nền trong cùng ứng dụng | Channel hoặc executor phù hợp |
| Phát sự kiện cho nhiều thành phần | Publish/subscribe |
| Giao tiếp bền vững giữa các tiến trình | Broker và adapter tương ứng |
| Giao tiếp hai chiều với trình duyệt qua WebSocket | Spring WebSocket và giao thức phù hợp |

## 10. Những nhầm lẫn phổ biến

**Cho rằng message luôn bất đồng bộ:** message là cấu trúc dữ liệu; channel hoặc transport quyết định cách chuyển và xử lý. Một handler có thể được gọi ngay trong thread gửi.

**Cho rằng Spring Messaging là broker:** Spring Messaging cung cấp abstraction và API. Muốn có lưu trữ bền vững, phân phối qua mạng hoặc quản lý hàng đợi, cần implementation hoặc broker tương ứng.

**Cho rằng gửi thành công nghĩa là nghiệp vụ đã hoàn tất:** kết quả send thường chỉ phản ánh thao tác gửi theo hợp đồng của channel. Nó không nhất thiết chứng minh consumer đã xử lý xong hoặc transaction nghiệp vụ đã commit.

**Cho rằng event và command giống nhau:** command yêu cầu thực hiện hành động; event thông báo một sự kiện đã xảy ra. Nhầm hai loại có thể khiến consumer thực hiện hành động ngoài ý muốn.

**Bỏ qua xử lý trùng:** retry và redelivery có thể khiến consumer nhận một thông điệp nhiều lần. Consumer cần có chiến lược idempotency.

**Đưa toàn bộ dữ liệu vào header:** header dành cho metadata. Payload nên chứa nội dung nghiệp vụ có cấu trúc và được quản lý như một hợp đồng dữ liệu.

**Dùng messaging cho mọi lời gọi:** nếu bên gọi cần phản hồi tức thì và không có nhu cầu tách rời, lời gọi phương thức trực tiếp thường đơn giản hơn.

## 11. Ghi nhớ

- Message là đơn vị dữ liệu trao đổi, thường gồm payload và headers.
- Producer tạo và gửi thông điệp; channel hoặc broker chuyển thông điệp; consumer nhận và xử lý.
- Spring Messaging cung cấp các abstraction như Message, MessageHeaders, MessageChannel và MessageHandler.
- API messaging không tự quyết định tính đồng bộ, độ bền dữ liệu hay bảo đảm giao nhận; các đặc tính này phụ thuộc implementation và hạ tầng.
- Messaging giúp giảm phụ thuộc giữa các thành phần, hỗ trợ bất đồng bộ và phân phối sự kiện, nhưng cần thiết kế cho retry, xử lý trùng, thứ tự, versioning, bảo mật và quan sát.
- Chọn messaging khi những lợi ích đó giải quyết một yêu cầu thực tế; với giao tiếp nội bộ đơn giản và cần kết quả ngay, gọi phương thức trực tiếp thường là lựa chọn phù hợp hơn.
