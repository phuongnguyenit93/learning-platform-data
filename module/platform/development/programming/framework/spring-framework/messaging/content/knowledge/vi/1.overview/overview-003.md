# Vị trí của spring-messaging trong Spring Framework

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao Spring Framework có một lớp trừu tượng dành cho messaging.
- Xác định vai trò của artifact spring-messaging trong kiến trúc Spring và phân biệt nó với broker hoặc thư viện tích hợp giao thức.
- Mô tả mối quan hệ giữa Message, MessageHeaders, MessageChannel và MessageHandler.
- Nhận biết cách Spring WebSocket/STOMP và Spring Integration sử dụng nền tảng messaging.
- Chọn đúng mức trừu tượng cho một bài toán giao tiếp giữa các thành phần.

## 1. Bài toán mà spring-messaging giải quyết

Trong ứng dụng thông thường, một đối tượng gọi trực tiếp phương thức của đối tượng khác. Bên gọi phải biết đối tượng nhận và thường phụ thuộc vào kiểu hoặc API của đối tượng đó. Cách này phù hợp với lời gọi đồng bộ trong cùng tiến trình, nhưng tạo liên kết chặt khi cần thay đổi cách phân phối công việc, thêm người nhận, đưa dữ liệu qua một giao thức hoặc chuyển xử lý sang luồng khác.

Messaging thay đổi cách kết nối: bên gửi tạo một thông điệp rồi gửi nó qua một kênh. Bên nhận đăng ký xử lý thông điệp trên kênh đó. Bên gửi làm việc với hợp đồng gửi thông điệp, thay vì gọi trực tiếp một phương thức nghiệp vụ cụ thể.

Ví dụ, khi đơn hàng được tạo, thành phần đặt hàng có thể phát một thông điệp mang dữ liệu đơn hàng. Thành phần gửi email, cập nhật tồn kho hoặc ghi nhận phân tích có thể nhận thông điệp qua các luồng riêng. Mô hình này giúp tách nơi phát sinh sự kiện khỏi nơi xử lý, nhưng bản thân một MessageChannel không tự biến ứng dụng thành hệ thống phân tán: cách chạy, lưu đệm, phân phối và độ bền của thông điệp phụ thuộc vào implementation hoặc adapter được sử dụng.

Spring Framework cung cấp module spring-messaging để chuẩn hóa những khái niệm nền tảng này. Module có mô hình thông điệp, hợp đồng kênh, hợp đồng bộ xử lý và các tiện ích hỗ trợ. Những dự án hoặc module ở tầng cao hơn có thể dùng lại cùng mô hình thay vì tự định nghĩa một bộ API messaging riêng.

## 2. Vị trí của module trong kiến trúc Spring

Spring Framework được chia thành nhiều module có trách nhiệm khác nhau: container và dependency injection, context, truy cập dữ liệu, giao dịch, web, kiểm thử và messaging. spring-messaging là module chuyên về mô hình và hợp đồng trao đổi thông điệp. Nó thuộc Spring Framework, nhưng không đồng nghĩa với spring-core và cũng không phải một message broker.

Có thể hình dung vị trí của nó như sau:

~~~mermaid
flowchart TB
    APP["Thành phần nghiệp vụ của ứng dụng"]
    API["spring-messaging<br/>Message · Headers · Channel · Handler"]
    WS["spring-websocket<br/>WebSocket và STOMP"]
    SI["Spring Integration<br/>Integration flow và adapter"]
    BROKER["Adapter hoặc client theo giao thức<br/>JMS · AMQP · Kafka · RSocket"]
    INFRA["Transport hoặc broker thực tế"]

    APP --> API
    WS --> API
    SI --> API
    BROKER --> API
    BROKER --> INFRA
~~~

Sơ đồ thể hiện quan hệ về mặt khái niệm. Mỗi integration có cách nối cụ thể và không phải mọi broker đều được Spring Framework cung cấp trực tiếp.

- **spring-messaging:** định nghĩa hình dạng của một Message, cách gửi qua MessageChannel, cách đăng ký MessageHandler, chuyển đổi thông điệp và một số tiện ích liên quan.
- **spring-websocket:** cung cấp hạ tầng WebSocket và hỗ trợ STOMP. Khi dùng STOMP, các frame được ánh xạ thành Spring Message và đi qua các channel của Spring.
- **Spring Integration:** mở rộng mô hình messaging bằng các mẫu tích hợp hệ thống như router, filter, transformer, splitter, aggregator, service activator và adapter kết nối hệ thống ngoài.
- **Spring JMS, Spring AMQP, Spring Kafka và các adapter tương ứng:** làm việc với API, client và quy tắc riêng của từng giao thức hoặc broker. Đây là các lớp tích hợp theo công nghệ; không nên mặc định rằng chỉ thêm spring-messaging là đã có kết nối tới RabbitMQ, Kafka hay JMS broker.
- **Broker hoặc transport:** chịu trách nhiệm cho những đặc tính cụ thể như định tuyến, lưu bền, xác nhận, phân phối qua mạng, consumer group hoặc giao thức truyền tải.

spring-messaging có nguồn gốc từ mô hình messaging của Spring Integration. Các abstraction nền tảng được tách ra và đưa vào Spring Framework để nhiều dự án Spring có thể dùng chung, kể cả khi ứng dụng không sử dụng toàn bộ Spring Integration.

Điểm cần nhớ: spring-messaging là lớp hợp đồng chung ở phía ứng dụng. Nó giúp các thành phần trao đổi thông điệp theo một mô hình nhất quán; nó không tự cung cấp toàn bộ tính năng vận hành của một broker.

## 3. Các abstraction cốt lõi

### 3.1. Message: dữ liệu được đóng gói thành thông điệp

Một Message<T> gồm hai phần:

- **Payload:** nội dung chính mà người gửi muốn truyền. Kiểu payload có thể là String, một DTO, byte array hoặc một kiểu đối tượng khác.
- **Headers:** metadata đi kèm payload, chẳng hạn ID, thời điểm tạo, content type, correlation ID, destination hoặc thông tin do ứng dụng tự định nghĩa.

Headers giúp tách dữ liệu nghiệp vụ khỏi thông tin điều khiển. Ví dụ payload chứa thông tin đơn hàng, còn header có thể chứa mã tương quan để theo dõi toàn bộ quá trình xử lý.

Trong Spring, MessageHeaders là cấu trúc metadata được cung cấp qua Message. Message và header map theo cách sử dụng thông thường có tính bất biến: không nên xem chúng như một Map để sửa trực tiếp sau khi đã phát đi. Tuy nhiên, tính bất biến của vỏ thông điệp không làm cho mọi object bên trong payload tự động bất biến. Nếu payload là một object mutable và nhiều thành phần cùng tham chiếu đến object đó, ứng dụng vẫn phải kiểm soát việc thay đổi dữ liệu.

Các lớp thường gặp:

- **Message<T>:** interface mô tả một thông điệp có payload và headers.
- **MessageHeaders:** cung cấp các header của thông điệp, bao gồm những metadata chuẩn như ID và timestamp.
- **GenericMessage<T>:** implementation phổ biến của Message.
- **MessageBuilder<T>:** API builder để tạo Message hoặc tạo thông điệp mới dựa trên một Message có sẵn.
- **ErrorMessage:** thông điệp dùng để mang một Throwable như payload.

Ví dụ tạo thông điệp:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class BuildMessageExample {
    public static void main(String[] args) {
        Message<String> message = MessageBuilder
                .withPayload("ORD-42")
                .setHeader("eventType", "order.created")
                .setHeader("source", "checkout")
                .build();

        System.out.println(message.getPayload());
        System.out.println(message.getHeaders().get("eventType"));
    }
}
~~~

Kết quả:

~~~text
ORD-42
order.created
~~~

Payload là mã đơn hàng. Header eventType mô tả loại sự kiện, còn source cho biết thành phần phát sinh. Các header này là metadata do ứng dụng quy ước; Spring không tự hiểu ý nghĩa nghiệp vụ của chúng.

### 3.2. MessageChannel: điểm gửi và ranh giới giữa bên gửi với bên nhận

MessageChannel định nghĩa hợp đồng gửi một Message. Bên gửi chỉ cần biết channel mà nó gửi vào. Nó không cần biết cụ thể handler nào sẽ nhận thông điệp hoặc handler được triển khai bằng lớp nào.

Hai phương thức gửi quan trọng là:

- send(message): gửi thông điệp theo chính sách của channel.
- send(message, timeout): gửi với thời gian chờ tối đa tính bằng mili giây.

Giá trị boolean trả về cho biết channel có chấp nhận thông điệp hay không. Nếu send trả về false, việc gửi không được chấp nhận, chẳng hạn do hết thời gian chờ hoặc channel từ chối. Một lỗi không thể khôi phục có thể được ném dưới dạng runtime exception.

Không nên diễn giải send trả về true thành “nghiệp vụ đã hoàn tất”, “broker đã lưu bền” hoặc “mọi consumer đã xử lý thành công”. Ý nghĩa chính xác của việc chấp nhận phụ thuộc implementation. Với channel đồng bộ, handler có thể được gọi ngay trong luồng gửi; với channel dùng executor, việc xử lý có thể diễn ra ở luồng khác.

### 3.3. PollableChannel và SubscribableChannel

Hai nhóm channel phổ biến thể hiện hai cách nhận thông điệp khác nhau:

| Loại channel | Cách nhận | Đặc điểm |
|---|---|---|
| PollableChannel | Consumer chủ động gọi receive() | Có thể nhận thông điệp đang chờ trong channel; thường phù hợp với mô hình lấy dữ liệu theo lượt |
| SubscribableChannel | Consumer đăng ký MessageHandler | Khi có thông điệp, channel chuyển nó tới các subscriber theo implementation |

SubscribableChannel quản lý danh sách handler đăng ký. ExecutorSubscribableChannel là implementation thuộc Spring Framework: nó gửi thông điệp tới các subscriber và có thể sử dụng Executor. Constructor không tham số thực thi handler ngay trong luồng gọi send; constructor nhận Executor sử dụng executor được truyền vào.

Đừng nhầm các implementation của Spring Framework với những channel cụ thể của Spring Integration. Ví dụ DirectChannel, QueueChannel và PublishSubscribeChannel thường được nhắc đến trong tài liệu Spring Integration. Chúng thuộc tầng tích hợp cao hơn, không phải tên thay thế cho mọi MessageChannel trong spring-messaging.

### 3.4. MessageHandler: hợp đồng xử lý thông điệp

MessageHandler là hợp đồng cho thành phần nhận và xử lý Message. Handler đọc payload, kiểm tra headers cần thiết rồi gọi logic nghiệp vụ tương ứng.

Việc tách MessageHandler khỏi MessageChannel tạo ra hai trách nhiệm độc lập:

- Channel quyết định cách chuyển thông điệp tới người nhận.
- Handler quyết định phải làm gì với thông điệp đã nhận.

Một channel có thể phục vụ một hoặc nhiều handler tùy loại channel và cấu hình. Khi dùng nhiều subscriber, cần hiểu rõ channel phát một bản tới từng subscriber hay chọn một consumer theo chính sách riêng của implementation.

Spring cũng có ReactiveMessageHandler cho hợp đồng xử lý theo kiểu reactive. Khi dùng API reactive, cần phân biệt việc tạo hoặc trả về một Publisher với thời điểm dữ liệu thực sự được tiêu thụ.

### 3.5. Các thành phần hỗ trợ khác

Ngoài ba abstraction chính, module còn có những thành phần hỗ trợ:

- **MessageConverter:** chuyển đổi giữa payload và biểu diễn thông điệp phù hợp với một ngữ cảnh. Converter không có nghĩa là mọi payload tự động được JSON hóa hoặc mọi giao thức đều dùng cùng một định dạng.
- **ChannelInterceptor:** quan sát hoặc can thiệp vào quá trình gửi/nhận qua channel, phù hợp với những xử lý xuyên suốt như logging, kiểm tra metadata hoặc bổ sung thông tin tương quan.
- **MessageHeaderAccessor:** truy cập và thao tác headers theo cách có kiểm soát, thay vì sửa trực tiếp MessageHeaders.
- **GenericMessagingTemplate:** implementation trong `org.springframework.messaging.core` cung cấp các thao tác gửi, nhận và request-reply qua `MessageChannel`. Các module tích hợp có template riêng như `JmsMessagingTemplate` (Spring JMS), `RabbitTemplate` (Spring AMQP), `KafkaTemplate` (Spring Kafka) và `SimpMessagingTemplate` (Spring WebSocket/STOMP).

Những tiện ích này bổ sung cho hợp đồng nền tảng. Chúng không thay thế chính sách bảo mật, xác thực, retry, giám sát hoặc lưu bền của hệ thống tích hợp.

## 4. Luồng xử lý một thông điệp

Một luồng messaging cơ bản thường có các bước:

1. Thành phần phát sinh sự kiện tạo payload từ dữ liệu nghiệp vụ.
2. MessageBuilder đóng gói payload cùng headers cần thiết.
3. Producer gọi send trên MessageChannel.
4. Implementation của channel quyết định cách tiếp nhận và chuyển thông điệp.
5. Một hoặc nhiều MessageHandler nhận thông điệp theo quy tắc của channel.
6. Handler gọi dịch vụ nghiệp vụ để xử lý payload.
7. Nếu cần phản hồi, ứng dụng tạo và gửi một Message khác theo luồng phản hồi đã thiết kế.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as MessageBuilder
    participant C as MessageChannel
    participant H as MessageHandler
    participant S as Domain Service

    P->>B: Tạo payload và headers
    B-->>P: Message<T>
    P->>C: send(message)
    C->>H: Chuyển Message tới subscriber
    H->>S: Gọi logic nghiệp vụ
    S-->>H: Kết quả xử lý
    H-->>C: Hoàn tất theo luồng hiện tại
    C-->>P: Kết quả chấp nhận gửi
~~~

Sơ đồ mô tả luồng khái niệm. Với channel đồng bộ, handler có thể chạy ngay trong lời gọi send. Với channel bất đồng bộ hoặc adapter kết nối broker, thời điểm và kết quả xử lý có thể tách khỏi lời gọi gửi. Vì vậy, không nên giả định rằng producer luôn nhận được kết quả nghiệp vụ chỉ từ boolean của send.

## 5. Ví dụ chạy được với spring-messaging

Ví dụ dưới đây dùng một ExecutorSubscribableChannel không truyền Executor. Theo hợp đồng của implementation, subscriber chạy trong luồng gọi send, nên thứ tự stdout trong ví dụ là xác định.

### 5.1. Cấu hình Maven

Có thể dùng Spring Framework BOM để giữ phiên bản các module đồng nhất. Ví dụ sau minh họa với Spring Framework 7.0.10 và Java 17:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-messaging-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>7.0.10</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
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

Tạo file src/main/java/demo/MessageDemo.java:

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class MessageDemo {

    public static void main(String[] args) {
        SubscribableChannel channel = new ExecutorSubscribableChannel();

        MessageHandler handler = message -> {
            String orderId = (String) message.getPayload();
            String eventType = (String) message.getHeaders().get("eventType");
            System.out.println(eventType + "|" + orderId);
        };

        channel.subscribe(handler);

        Message<String> message = MessageBuilder
                .withPayload("ORD-42")
                .setHeader("eventType", "order.created")
                .build();

        boolean accepted = channel.send(message);
        System.out.println("sendAccepted=" + accepted);
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.MessageDemo
~~~

Stdout:

~~~text
order.created|ORD-42
sendAccepted=true
~~~

Giải thích:

- Producer tạo Message có payload là ORD-42 và header eventType là order.created.
- Producer chỉ giữ tham chiếu tới SubscribableChannel, không gọi trực tiếp handler.
- Handler được đăng ký bằng subscribe.
- Khi send được gọi, ExecutorSubscribableChannel không có Executor nên gọi subscriber trong luồng hiện tại.
- Handler đọc payload và header rồi in ra một dòng.
- send trả về true vì channel đã chấp nhận thông điệp. Trong ví dụ đồng bộ này, handler cũng đã chạy trước khi send trả về. Với channel hoặc adapter bất đồng bộ, không được suy rộng kết luận đó.

Ví dụ chỉ minh họa API messaging nền tảng. Nó chưa tạo Spring ApplicationContext, chưa kết nối broker, chưa lưu thông điệp vào database và chưa thiết lập retry hoặc dead-letter queue.

## 6. Quan hệ với các module và dự án Spring khác

### 6.1. Spring WebSocket và STOMP

WebSocket cung cấp kết nối hai chiều giữa client và server, nhưng bản thân giao thức WebSocket không định nghĩa đầy đủ ý nghĩa nghiệp vụ của từng thông điệp. STOMP có thể được dùng làm sub-protocol để định nghĩa frame, command và destination.

Trong hỗ trợ STOMP của Spring:

- Frame từ client được giải mã và biểu diễn thành Spring Message.
- Thông điệp đi vào các channel như clientInboundChannel.
- Destination có thể định tuyến thông điệp tới phương thức controller được đánh dấu bằng MessageMapping hoặc tới message broker.
- Thông điệp do ứng dụng phát ra có thể đi qua brokerChannel rồi được gửi tới client qua clientOutboundChannel.

Đây là ví dụ rõ ràng về việc spring-websocket sử dụng nền tảng spring-messaging. Để cấu hình STOMP over WebSocket, ứng dụng cần các module phù hợp như spring-messaging và spring-websocket. Chỉ thêm spring-messaging không tự mở một WebSocket endpoint.

### 6.2. Spring Integration

Spring Integration dùng nền tảng Message, MessageChannel và MessageHandler để xây dựng các integration flow ở mức cao hơn. Nó bổ sung nhiều enterprise integration patterns và adapter cho hệ thống ngoài.

Ví dụ, một flow có thể nhận dữ liệu từ một endpoint, chuyển đổi định dạng, lọc theo điều kiện, định tuyến tới các handler khác nhau rồi gửi kết quả tới hệ thống đích. Các bước này là chức năng của Spring Integration, không phải chỉ riêng spring-messaging.

### 6.3. JMS, AMQP, Kafka và broker

Mỗi công nghệ messaging có những khái niệm riêng:

- JMS định nghĩa API Java cho hệ thống message-oriented middleware.
- AMQP là một giao thức messaging; RabbitMQ là một broker thường được sử dụng với AMQP.
- Kafka tổ chức dữ liệu thành topic và partition, có consumer group và offset.
- RSocket cung cấp mô hình tương tác qua kết nối hai chiều, với các kiểu tương tác như request-response và stream.

Các integration tương ứng phải ánh xạ khái niệm riêng của công nghệ sang API hoặc mô hình của ứng dụng. spring-messaging giúp chuẩn hóa một số khái niệm chung, nhưng không làm cho semantics của các công nghệ này giống nhau. Ví dụ acknowledgement, offset, transaction, ordering, partition và delivery guarantee vẫn phải được hiểu theo công nghệ cụ thể.

### 6.4. Spring Application Events

ApplicationEventPublisher và event listener phục vụ giao tiếp sự kiện trong ApplicationContext. Chúng hữu ích khi một thành phần trong cùng ứng dụng muốn thông báo cho thành phần khác. Chúng không tự cung cấp broker, lưu bền qua lần khởi động lại hay giao tiếp qua mạng.

MessageChannel có mô hình Message và channel riêng. Hai cơ chế có thể cùng xuất hiện trong một ứng dụng, nhưng không nên xem Spring application event là một broker messaging hoặc ngược lại.

### 6.5. HTTP/REST

HTTP controller thường xử lý request-response: client gửi request tới endpoint và nhận response. Messaging phù hợp khi ứng dụng cần tách producer khỏi consumer, gửi sự kiện, fan-out tới subscriber hoặc dùng một adapter để nối với broker. Việc chọn messaging chỉ vì nó có thể bất đồng bộ sẽ làm hệ thống phức tạp không cần thiết nếu một API request-response đã đáp ứng bài toán.

## 7. spring-messaging không tự đảm nhiệm điều gì?

Khi đọc tên module, cần tránh một số suy luận sai:

- **Không phải message broker:** module không tự cung cấp cụm broker, durable queue, replicated log hay giao diện quản trị.
- **Không mặc định là bất đồng bộ:** channel có thể thực thi handler ngay trong luồng gửi. Bất đồng bộ phụ thuộc implementation và cấu hình.
- **Không bảo đảm xử lý đúng một lần:** boolean trả về từ send không chứng minh nghiệp vụ đã commit hoặc consumer đã xử lý đúng một lần.
- **Không tự tạo retry và dead-letter queue:** các chính sách này phải đến từ adapter, broker hoặc logic ứng dụng.
- **Không tự định nghĩa schema nghiệp vụ:** payload và header là dữ liệu do ứng dụng và hệ thống tích hợp thống nhất.
- **Không tự bảo đảm thứ tự toàn cục:** nhiều subscriber, executor, partition hoặc consumer có thể làm thứ tự xử lý khác với thứ tự phát sinh.
- **Không tự bảo vệ payload:** ứng dụng vẫn cần kiểm tra dữ liệu đầu vào, xác thực nguồn gửi, phân quyền và tránh ghi thông tin nhạy cảm vào log.

## 8. Hướng dẫn lựa chọn mức trừu tượng

| Nhu cầu | Nên bắt đầu từ |
|---|---|
| Đóng gói payload và metadata thành Message | spring-messaging |
| Gửi Message qua channel tới handler trong ứng dụng | spring-messaging |
| Xây dựng luồng tích hợp có router, filter, transformer, splitter, aggregator và adapter | Spring Integration |
| Trao đổi STOMP qua WebSocket với browser client | spring-websocket cùng spring-messaging |
| Kết nối ứng dụng với Kafka | Spring for Apache Kafka |
| Kết nối ứng dụng với RabbitMQ/AMQP | Spring AMQP |
| Tích hợp JMS | Spring JMS |
| Phát sự kiện nội bộ trong ApplicationContext | Spring Application Events |
| Cung cấp API request-response cho client | Spring MVC hoặc Spring WebFlux |

Có thể dùng trực tiếp spring-messaging khi xây dựng adapter riêng, cần thao tác với Message/MessageChannel/MessageHandler hoặc làm việc với API messaging của một module Spring khác. Nếu cần một nền tảng integration flow hoàn chỉnh, hãy xem Spring Integration. Nếu cần broker cụ thể, hãy dùng integration tương ứng và học thêm semantics của broker đó.

## 9. Lưu ý thiết kế và lỗi thường gặp

1. **Nhầm gửi thành xử lý xong:** send trả về true thường chỉ xác nhận channel đã chấp nhận thông điệp. Muốn biết nghiệp vụ hoàn tất, hãy thiết kế acknowledgement hoặc response riêng.
2. **Giả định channel nào cũng có buffer:** MessageChannel là hợp đồng gửi. Khả năng lưu đệm, giới hạn dung lượng và cách nhận phụ thuộc loại channel.
3. **Giả định channel nào cũng chạy ở thread khác:** ExecutorSubscribableChannel không có Executor chạy handler ngay trong luồng gọi. Cần đọc tài liệu implementation trước khi suy luận về concurrency.
4. **Đưa toàn bộ dữ liệu vào headers:** payload nên chứa dữ liệu nghiệp vụ; headers nên chứa metadata như correlation ID, content type hoặc destination.
5. **Sửa payload sau khi gửi:** envelope có thể bất biến nhưng object payload vẫn có thể mutable. Hãy dùng object bất biến hoặc sao chép dữ liệu khi cần tránh chia sẻ trạng thái.
6. **Bỏ qua giới hạn và timeout:** gửi có thể chặn hoặc bị từ chối. Ứng dụng cần xử lý false, timeout và exception theo chính sách phù hợp.
7. **Dùng tên header tùy tiện:** thống nhất tên, kiểu dữ liệu và ý nghĩa header giữa producer và consumer. Tránh ghi đè header hệ thống hoặc tin tưởng metadata đến từ nguồn không đáng tin.
8. **Dùng executor mà không quản lý tải:** cần tính tới kích thước pool, hàng đợi, back-pressure, shutdown và xử lý exception.
9. **Cho rằng converter đồng nghĩa serializer của broker:** chuyển đổi payload trong Spring và serialization trên wire có thể là hai bước khác nhau. Kiểm tra cấu hình adapter thực tế.
10. **Bỏ qua quan sát và tương quan:** correlation ID, log có cấu trúc và metric giúp lần theo một thông điệp qua nhiều thành phần. Không log payload nhạy cảm chỉ để debug.

## 10. Câu hỏi tự kiểm tra

1. Message khác payload ở điểm nào? Vì sao headers hữu ích?
2. MessageChannel tách producer khỏi consumer như thế nào?
3. Điểm khác nhau chính giữa PollableChannel và SubscribableChannel là gì?
4. Vì sao send trả về true không đồng nghĩa với việc nghiệp vụ đã hoàn tất?
5. ExecutorSubscribableChannel không có Executor thực thi handler ở đâu?
6. spring-messaging khác Spring Integration ở phạm vi trách nhiệm nào?
7. Vì sao thêm spring-messaging chưa đủ để kết nối RabbitMQ hoặc Kafka?
8. Khi nào nên dùng Application Events hoặc REST thay cho messaging?

## 11. Kết luận

spring-messaging là nền tảng messaging ở cấp Spring Framework: nó cung cấp mô hình Message, headers, channel, handler và các tiện ích để các thành phần trao đổi thông điệp theo hợp đồng chung. Những module và dự án khác dùng nền tảng này để xây dựng tính năng cao hơn, chẳng hạn STOMP qua WebSocket hoặc integration flow.

Khi thiết kế hệ thống, hãy phân biệt rõ ba lớp: mô hình thông điệp của ứng dụng, implementation/adapter chuyển thông điệp và hạ tầng broker hoặc transport. Sự phân biệt này giúp chọn đúng dependency, hiểu đúng bảo đảm xử lý và tránh kỳ vọng sai vào MessageChannel.

## Tài liệu tham khảo chính thức

- Spring Framework Reference Documentation: https://docs.spring.io/spring-framework/reference/
- Spring Framework STOMP message flow: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework STOMP overview: https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html
- Spring Framework Messaging API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/package-summary.html
- Spring Framework messaging support API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/package-summary.html
- Spring Integration overview: https://docs.spring.io/spring-integration/reference/overview.html
