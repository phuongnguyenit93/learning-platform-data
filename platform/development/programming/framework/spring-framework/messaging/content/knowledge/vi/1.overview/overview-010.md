# Lộ trình học Spring Framework Messaging: từ trừu tượng nền tảng đến các giao thức

> **Phạm vi bài học:** xây dựng hiểu biết theo từng lớp về hệ thống messaging trong hệ sinh thái Spring: bắt đầu từ mô hình Message, MessageChannel và MessageHandler của Spring Messaging; tiếp tục với Spring Integration; sau đó kết nối các giao thức ứng dụng như STOMP và RSocket, rồi phân biệt chúng với các tích hợp broker như JMS, AMQP và Kafka.

## 1. Mục tiêu và bản đồ kiến trúc

Messaging là cách các thành phần trao đổi thông tin thông qua thông điệp. Bên gửi tạo một message, chuyển message vào một điểm giao tiếp, và một hoặc nhiều thành phần nhận xử lý nó. Bên gửi và bên nhận có thể ít phụ thuộc trực tiếp vào lớp triển khai của nhau; mức độ tách rời thực tế phụ thuộc vào cách chọn channel, giao thức, broker và chính sách giao nhận.

Sau bài học, bạn cần có thể:

- Giải thích payload, header, message, channel, handler và endpoint.
- Đọc được một luồng message trong ứng dụng Spring và xác định nơi message được tạo, chuyển tiếp, biến đổi và xử lý.
- Phân biệt abstraction của Spring Messaging với các channel và Enterprise Integration Patterns do Spring Integration cung cấp.
- Chọn đúng cách tiếp cận cho giao tiếp trong tiến trình, WebSocket/STOMP, RSocket hoặc message broker.
- Nhận diện các vấn đề về thread, thứ tự, lỗi, retry, xác nhận, bảo mật và khả năng quan sát.

Có thể hình dung các lớp như sau:

~~~text
Ứng dụng gửi
    |
    v
Message<T> = payload + headers
    |
    v
MessageChannel.send(message)
    |
    v
MessageHandler.handleMessage(message)
    |
    +----> xử lý nghiệp vụ
    |
    +----> channel / handler tiếp theo
    |
    +----> adapter kết nối giao thức hoặc broker
                 |
                 +---- STOMP qua WebSocket
                 +---- RSocket
                 +---- JMS / AMQP / Kafka (các dự án tích hợp tương ứng)
~~~

Các khối trên không đồng nghĩa với nhau. Message là mô hình dữ liệu; channel là abstraction chuyển message; handler là thành phần xử lý; protocol định nghĩa cách các hệ thống trao đổi dữ liệu trên đường truyền; broker thường đảm nhiệm lưu trữ, định tuyến và phân phối message giữa các tiến trình. Một channel trong bộ nhớ không tự động có các bảo đảm của broker.

## 2. Nền tảng: Message, payload và headers

### 2.1 Message là một phong bì dữ liệu

Trong Spring Messaging, một message có hai phần:

- **Payload:** nội dung chính, có thể là object Java, chuỗi, byte array hoặc kiểu dữ liệu khác.
- **Headers:** metadata đi kèm, chẳng hạn message ID, thời điểm tạo, content type, correlation ID, thông tin định tuyến hoặc dữ liệu phục vụ xử lý.

Kiểu tổng quát thường gặp là `Message<T>`. Tham số T biểu diễn kiểu payload. Phần lớn API xử lý message nhận `Message<?>` vì handler có thể nhận payload thuộc nhiều kiểu khác nhau.

Một số kiểu và API quan trọng:

- **Message<T>:** interface biểu diễn message, cung cấp payload và headers.
- **GenericMessage<T>:** implementation cơ bản của Message.
- **MessageHeaders:** tập metadata của message. Headers được thiết kế theo hướng chỉ đọc sau khi message được tạo.
- **MessageBuilder:** cách thuận tiện để tạo message mới hoặc xây dựng message từ message hiện có.
- **MessageHeaderAccessor:** API truy cập và thiết lập headers có kiểm soát, hữu ích khi làm việc với header đặc thù của framework.

Ví dụ, một sự kiện đơn hàng có thể mang payload là dữ liệu đơn hàng và header gồm `tenantId`, `correlationId` và `contentType`. Payload trả lời câu hỏi “dữ liệu nghiệp vụ là gì”; header trả lời “message này được tạo trong ngữ cảnh nào và cần được xử lý ra sao”.

Không nên đưa toàn bộ dữ liệu nghiệp vụ vào headers. Headers phù hợp với metadata phục vụ vận chuyển, định tuyến, tương quan hoặc xử lý. Nội dung nghiệp vụ nên nằm trong payload để schema của payload có thể được quản lý rõ ràng.

### 2.2 Tạo message

Ví dụ Java dưới đây là một lớp hoàn chỉnh. Project cần có dependency **org.springframework:spring-messaging**, với phiên bản được quản lý đồng bộ qua Spring Framework BOM hoặc Spring Boot dependency management.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class MessageEnvelopeDemo {
    public static void main(String[] args) {
        Message<String> message = MessageBuilder
                .withPayload("order.created")
                .setHeader("tenantId", "acme")
                .setHeader("correlationId", "corr-001")
                .build();

        System.out.println(message.getPayload());
        System.out.println(message.getHeaders().get("tenantId"));
    }
}
~~~

Kết quả:

~~~text
order.created
acme
~~~

Message đã được tạo là một đơn vị dữ liệu có cấu trúc. Nếu cần thay payload hoặc header, hãy tạo message mới qua builder hoặc accessor phù hợp thay vì coi headers là một map có thể sửa tùy ý sau khi message đã phát đi.

### 2.3 Những header thường gặp

Một số metadata có ý nghĩa phổ biến:

- **id:** định danh của message.
- **timestamp:** thời điểm tạo message.
- **contentType:** gợi ý kiểu nội dung và cách chuyển đổi payload.
- **replyChannel:** gợi ý nơi gửi kết quả phản hồi trong một số luồng request-reply.
- **errorChannel:** nơi nhận thông tin lỗi trong những cơ chế messaging có hỗ trợ định tuyến lỗi.
- **correlationId:** thường do ứng dụng hoặc tầng tích hợp bổ sung để liên kết các message thuộc cùng một nghiệp vụ.

Không nên giả định mọi header đều tồn tại trên mọi message hoặc được mọi giao thức bảo toàn. Khi message đi qua ranh giới mạng, adapter có thể ánh xạ, chuyển đổi hoặc loại bỏ metadata. Hãy xác định rõ header nào là hợp đồng ứng dụng và header nào chỉ có ý nghĩa nội bộ trong một framework.

## 3. MessageChannel và MessageHandler: abstraction vận chuyển và xử lý

### 3.1 MessageChannel

**MessageChannel** là abstraction để gửi message. Bên gửi gọi phương thức send với message và có thể chỉ định thời gian chờ. Kết quả boolean cho biết thao tác gửi được chấp nhận theo hợp đồng của channel hay không; điều đó không tự chứng minh nghiệp vụ ở phía nhận đã hoàn tất.

Một channel tạo ranh giới giữa nơi phát message và nơi xử lý message. Bên gửi cần biết channel đích, nhưng thường không cần biết implementation cụ thể của handler phía sau.

### 3.2 SubscribableChannel và PollableChannel

Hai kiểu mở rộng thường gặp mô tả hai cách nhận message:

- **SubscribableChannel:** handler đăng ký nhận message. Khi message được gửi, channel phân phối message tới các subscriber theo chính sách của implementation.
- **PollableChannel:** bên nhận chủ động gọi receive, có thể chờ trong một khoảng thời gian để lấy message.

Đây là hai kiểu giao tiếp khác nhau. Với mô hình subscription, channel chủ động gọi handler khi có message. Với mô hình polling, consumer quyết định thời điểm lấy message. Sự khác nhau ảnh hưởng tới thread, tải, khả năng điều tiết và cách xử lý khi consumer chậm.

### 3.3 MessageHandler

**MessageHandler** là abstraction xử lý một message thông qua phương thức handleMessage. Handler có thể thực hiện nghiệp vụ, xác thực dữ liệu, chuyển đổi payload, ghi log, gọi dịch vụ khác hoặc gửi message mới tới channel tiếp theo.

Một luồng xử lý thường gồm nhiều handler nhỏ, mỗi handler có một trách nhiệm rõ ràng. Cách chia này giúp kiểm thử từng bước và thay đổi thứ tự xử lý mà không buộc mọi thành phần phụ thuộc trực tiếp vào nhau.

### 3.4 Phân biệt abstraction với implementation

Spring Messaging cung cấp các abstraction cốt lõi và một số implementation hỗ trợ messaging, nhưng không biến mọi channel thành một broker. Nhiều implementation channel và các mẫu xử lý luồng phong phú thường đến từ **Spring Integration**.

Trong Spring Integration, các channel thường gặp gồm:

| Channel | Cách hoạt động | Trường hợp phù hợp |
|---|---|---|
| DirectChannel | Gọi subscriber trực tiếp trên luồng gửi | Luồng đồng bộ, đơn giản |
| PublishSubscribeChannel | Phân phối một message tới nhiều subscriber | Một sự kiện cần nhiều nhánh xử lý |
| QueueChannel | Giữ message trong hàng đợi để consumer lấy ra | Tách thời điểm gửi và nhận |
| PriorityChannel | Lấy message theo mức ưu tiên | Công việc có độ ưu tiên khác nhau |
| ExecutorChannel | Phân phối xử lý qua executor | Tách xử lý sang thread khác |

Tên channel và hành vi cụ thể phụ thuộc implementation. Ví dụ, DirectChannel không tạo một hàng đợi bền vững; QueueChannel trong bộ nhớ cũng không tương đương một broker có lưu trữ bền vững. Khi cần durability, phân phối qua nhiều tiến trình, xác nhận hoặc lưu trữ message, hãy dùng broker và adapter phù hợp.

## 4. Gửi, nhận và chuyển đổi message

Ở mức API thao tác, Spring Messaging cung cấp **MessageSendingOperations**, **MessageReceivingOperations**, **MessageRequestReplyOperations** và implementation **GenericMessagingTemplate** trong package `org.springframework.messaging.core`. Template này phân giải tên destination thành `MessageChannel` để gửi, nhận hoặc thực hiện request-reply. Spring Integration có class **MessagingTemplate** riêng trong package `org.springframework.integration.core`; đây là API của dự án Integration, không phải của module spring-messaging.

Các thao tác cần phân biệt:

- **send:** gửi một Message đã được tạo.
- **convertAndSend:** chuyển đổi object thành message rồi gửi.
- **receive:** lấy một message từ kiểu channel có hỗ trợ nhận.
- **receiveAndConvert:** nhận message rồi chuyển payload về kiểu mong muốn.
- **sendAndReceive:** gửi yêu cầu và chờ message phản hồi khi channel và cấu hình hỗ trợ mô hình request-reply.

Việc chuyển đổi thường liên quan tới **MessageConverter** và metadata như content type. Chuyển đổi object thành JSON không tự giải quyết việc tương thích schema giữa các phiên bản dịch vụ. Cần quản lý tên trường, kiểu dữ liệu, giá trị mặc định, version schema và quy tắc xử lý payload không hợp lệ.

Request-reply chỉ phù hợp khi bên gửi có thể chờ phản hồi và đường đi của phản hồi được xác định. Với tác vụ dài hoặc xử lý bất đồng bộ, nên biểu diễn kết quả bằng một message riêng có correlation ID thay vì giữ một lời gọi đồng bộ kéo dài.

## 5. Từ Spring Messaging đến Spring Integration

**Spring Messaging** cung cấp ngôn ngữ chung cho message, channel và handler. **Spring Integration** là dự án riêng trong hệ sinh thái Spring, sử dụng các abstraction messaging để xây dựng luồng tích hợp và cung cấp nhiều channel, endpoint, adapter cùng Enterprise Integration Patterns (EIP).

Không nên gộp hai dự án thành một API duy nhất:

- Spring Messaging định nghĩa các abstraction nền tảng và hỗ trợ messaging cho một số môi trường Spring.
- Spring Integration cung cấp công cụ xây dựng pipeline tích hợp giữa thành phần ứng dụng, hệ thống ngoài và các nguồn dữ liệu.
- Các adapter cụ thể kết nối với công nghệ bên ngoài có thể thuộc Spring Integration hoặc dự án Spring chuyên biệt khác.

### 5.1 Các EIP quan trọng

| Pattern | Nhiệm vụ | Câu hỏi cần trả lời |
|---|---|---|
| Service Activator | Gọi một service hoặc method để xử lý message | Ai thực hiện nghiệp vụ? |
| Transformer | Biến đổi payload hoặc cấu trúc message | Dữ liệu cần đổi thành dạng nào? |
| Filter | Cho message đi tiếp hoặc loại bỏ | Message có thỏa điều kiện không? |
| Router | Chọn channel đích | Message cần đi nhánh nào? |
| Splitter | Tách một message thành nhiều message | Một đầu vào cần chia thành những phần nào? |
| Aggregator | Gom nhiều message thành một kết quả | Khi nào các phần đã đủ để tổng hợp? |
| Gateway | Cung cấp giao diện gọi luồng tích hợp | Ứng dụng gọi flow như thế nào? |
| Channel Adapter | Nối channel với nguồn hoặc đích bên ngoài | Message đi vào hoặc ra khỏi hệ thống ở đâu? |

Spring Integration có các annotation và DSL để khai báo các pattern này, ví dụ **@ServiceActivator**, **@Transformer**, **@Filter**, **@Router**, **@Splitter**, **@Aggregator** và **IntegrationFlow**. Chúng thuộc Spring Integration, không phải toàn bộ đều là annotation của Spring Framework core.

### 5.2 Ví dụ một luồng tích hợp

Một luồng xử lý đơn hàng có thể được thiết kế như sau:

~~~text
Đầu vào đơn hàng
    |
    v
Validate
    |
    v
Router theo loại đơn
    |
    +----> Đơn nội địa ----> Tính phí giao hàng
    |
    +----> Đơn quốc tế ----> Kiểm tra hải quan
    |
    v
Ghi nhận kết quả
    |
    v
Phát sự kiện OrderProcessed
~~~

Khi thiết kế flow, hãy xác định rõ kiểu payload tại từng bước, header nào được giữ lại, lỗi được chuyển đi đâu và bước nào có thể chạy song song. Với splitter và aggregator, cần định nghĩa correlation, điều kiện hoàn tất, timeout và hành vi khi một phần bị thiếu. Nếu không có các quy tắc này, aggregator có thể chờ vô hạn hoặc gom nhầm các message thuộc những yêu cầu khác nhau.

## 6. Giao thức STOMP qua WebSocket

### 6.1 Các lớp tham gia

WebSocket cung cấp kết nối hai chiều lâu dài giữa client và server. STOMP là giao thức messaging dạng frame có thể chạy trên WebSocket. Spring hỗ trợ mô hình WebSocket messaging và STOMP qua các thành phần của Spring Framework, đặc biệt trong Spring WebSocket và Spring Messaging.

Các API và annotation thường gặp:

- **@EnableWebSocketMessageBroker:** bật hạ tầng xử lý message qua WebSocket với broker.
- **@MessageMapping:** ánh xạ destination tới method xử lý message.
- **@SubscribeMapping:** xử lý yêu cầu đăng ký subscription theo cách ánh xạ của controller.
- **@SendTo:** chỉ định destination gửi kết quả.
- **SimpMessagingTemplate:** gửi message tới destination từ code ứng dụng.
- **@Payload**, **@Header**, **@Headers**, **@DestinationVariable:** lấy payload, header hoặc biến destination trong method handler.
- **@MessageExceptionHandler:** xử lý lỗi phát sinh trong các method xử lý message theo phạm vi hỗ trợ.

### 6.2 Luồng điển hình

Một cấu hình thường chia destination thành hai nhóm:

- Prefix ứng dụng, ví dụ `/app`, dùng để định tuyến message từ client tới các method controller.
- Prefix broker, ví dụ `/topic` hoặc `/queue`, dùng cho destination mà broker quản lý và phân phối tới subscriber.

Ví dụ luồng:

~~~text
Client gửi STOMP SEND tới /app/orders
             |
             v
Spring định tuyến tới @MessageMapping
             |
             v
Controller xử lý lệnh tạo đơn
             |
             v
@SendTo hoặc SimpMessagingTemplate
             |
             v
Destination /topic/orders
             |
             v
Broker phân phối STOMP MESSAGE
             |
             v
Các client đã SUBSCRIBE nhận kết quả
~~~

Các tên prefix trên là cấu hình ví dụ, không phải giá trị bắt buộc. Server phải khai báo prefix và broker tương ứng. Một simple broker trong bộ nhớ phù hợp cho một số trường hợp phát triển hoặc triển khai đơn giản; broker relay kết nối tới broker bên ngoài khi cần hạ tầng phân phối chuyên dụng. Khả năng mở rộng, lưu trữ, xác nhận, định tuyến và bảo đảm giao nhận phụ thuộc broker thực tế.

### 6.3 Các frame STOMP cần biết

- **CONNECT:** client bắt đầu phiên STOMP.
- **SUBSCRIBE:** đăng ký nhận message từ destination.
- **SEND:** gửi message tới destination.
- **MESSAGE:** frame broker gửi cho subscriber.
- **ACK / NACK:** xác nhận hoặc từ chối message trong các chế độ và broker hỗ trợ.
- **DISCONNECT:** kết thúc phiên.

Khi làm việc với STOMP, cần hiểu cả vòng đời WebSocket lẫn vòng đời phiên STOMP. WebSocket mở kết nối truyền tải; STOMP trao đổi các frame messaging trên kết nối đó. Việc gửi được frame không đồng nghĩa message đã được xử lý thành công ở tầng nghiệp vụ.

### 6.4 Những điểm phải thiết kế

- Xác thực người dùng trong quá trình thiết lập kết nối và áp dụng quyền truy cập theo destination.
- Kiểm tra quyền gửi và quyền subscribe riêng biệt.
- Kiểm tra dữ liệu payload, giới hạn kích thước frame và kiểm soát tốc độ gửi.
- Xử lý mất kết nối, reconnect, subscription và trạng thái phiên.
- Không giả định client luôn online hoặc luôn nhận được mọi message.
- Nếu cần khôi phục sự kiện đã bỏ lỡ, hãy thiết kế lưu trữ, replay hoặc cơ chế đồng bộ trạng thái ở tầng phù hợp; WebSocket tự nó không cung cấp lịch sử message.

## 7. RSocket: mô hình tương tác reactive

RSocket là giao thức ứng dụng cho giao tiếp message giữa các bên, hỗ trợ các kiểu tương tác một lần và dạng stream. Spring cung cấp tích hợp RSocket thông qua Spring Messaging và các thành phần liên quan.

Các thành phần thường gặp:

- **RSocketRequester:** client API để gửi yêu cầu tới RSocket peer.
- **RSocketMessageHandler:** kết nối message của RSocket với các method xử lý trong Spring.
- **@MessageMapping:** ánh xạ route tới method xử lý message.
- **@ConnectMapping:** xử lý metadata hoặc dữ liệu ở giai đoạn thiết lập kết nối theo cấu hình hỗ trợ.
- **Mono và Flux:** kiểu reactive thường dùng để biểu diễn một kết quả hoặc một luồng nhiều kết quả.

### 7.1 Bốn kiểu tương tác

| Kiểu | Mô tả | Ví dụ |
|---|---|---|
| Fire-and-forget | Gửi yêu cầu, không chờ response ở tầng giao thức | Gửi tín hiệu hoặc lệnh không cần kết quả trực tiếp |
| Request-response | Một request nhận một response | Tra cứu trạng thái đơn hàng |
| Request-stream | Một request nhận một stream response | Theo dõi giá hoặc tiến trình |
| Request-channel | Hai phía trao đổi các stream message | Gửi liên tục dữ liệu và nhận kết quả liên tục |

RSocket hỗ trợ giao tiếp reactive và cơ chế điều tiết theo mô hình của giao thức. Điều đó hữu ích khi cần stream hoặc giao tiếp hai chiều, nhưng không loại bỏ nhu cầu quản lý lỗi, timeout, hủy subscription, giới hạn tài nguyên và tính idempotent của nghiệp vụ.

RSocket có thể chạy trên nhiều transport được hỗ trợ, chẳng hạn TCP hoặc WebSocket. Cần phân biệt transport với interaction model: transport quyết định dữ liệu đi qua kết nối nào; interaction model quyết định cách request và response được trao đổi.

### 7.2 Khi nào chọn RSocket?

RSocket phù hợp khi ứng dụng cần giao tiếp request-response hoặc streaming với mô hình reactive, đặc biệt khi cần stream hai chiều. Nếu yêu cầu chính là client web subscribe các destination theo mô hình broker phổ biến, STOMP qua WebSocket có thể dễ tiếp cận hơn. Nếu cần hàng đợi bền vững và xử lý giữa nhiều dịch vụ độc lập, hãy đánh giá broker chuyên dụng.

## 8. JMS, AMQP và Kafka: các tích hợp broker liên quan nhưng khác lớp

Các công nghệ này thường được dùng cùng Spring Messaging, nhưng cần học như những hệ tích hợp riêng:

| Công nghệ | API Spring thường gặp | Trọng tâm |
|---|---|---|
| JMS | Spring JMS, **JmsTemplate**, **@JmsListener** | API messaging chuẩn Java và provider JMS |
| AMQP | Spring AMQP, **RabbitTemplate**, **@RabbitListener** | Exchange, queue, binding, routing key và broker AMQP |
| Kafka | Spring for Apache Kafka, **KafkaTemplate**, **@KafkaListener** | Topic, partition, offset, consumer group và log phân tán |

Chúng không đơn giản là các implementation thay thế cho MessageChannel:

- JMS định nghĩa API messaging và phụ thuộc provider triển khai.
- AMQP đưa vào mô hình exchange, queue và binding của broker.
- Kafka tổ chức dữ liệu theo topic và partition; consumer quản lý offset và vị trí đọc.
- Spring Messaging cung cấp abstraction message chung, nhưng không đồng nhất semantics của các hệ thống trên.

Khi tích hợp, cần hiểu riêng cơ chế xác nhận, retry, dead-letter, thứ tự, phân vùng, transaction, retention và khả năng replay của công nghệ được chọn. Adapter có thể giúp ứng dụng dùng mô hình message thống nhất hơn, nhưng không làm mất đi các quy tắc giao nhận của broker.

## 9. Cách chọn lớp phù hợp

| Nhu cầu | Hướng tiếp cận nên tìm hiểu |
|---|---|
| Truyền message giữa các thành phần trong cùng ứng dụng | Spring Messaging abstraction và channel phù hợp |
| Xây dựng pipeline, định tuyến, biến đổi và kết hợp message | Spring Integration |
| Server đẩy sự kiện tới trình duyệt qua destination và subscription | WebSocket + STOMP |
| Giao tiếp reactive, request-response hoặc stream hai chiều | RSocket |
| Hàng đợi và tích hợp hệ thống theo JMS | Spring JMS |
| Routing qua exchange và queue AMQP | Spring AMQP |
| Event stream theo topic, partition và consumer group | Spring for Apache Kafka |

Hãy chọn theo yêu cầu vận hành: có cần lưu trữ bền vững không, cần giao tiếp đồng bộ hay bất đồng bộ, có cần stream không, cần phân phối tới nhiều consumer không, có cần replay không, và hệ thống phải xử lý lỗi hoặc mất kết nối như thế nào.

## 10. Lộ trình thực hành theo thứ tự

1. **Mô hình message:** tạo Message bằng MessageBuilder; đọc payload và headers; phân biệt metadata với dữ liệu nghiệp vụ.
2. **Abstraction channel và handler:** đọc interface MessageChannel, SubscribableChannel, PollableChannel và MessageHandler; theo dõi luồng send tới handler.
3. **Gửi và chuyển đổi:** thử GenericMessagingTemplate, MessageSendingOperations, MessageReceivingOperations, MessageRequestReplyOperations và MessageConverter; quan sát cách content type ảnh hưởng tới conversion.
4. **Spring Integration:** xây flow nhỏ gồm service activator, transformer, filter và router; thêm splitter/aggregator khi đã hiểu correlation.
5. **Xử lý lỗi:** thử lỗi ở từng handler, xác định nơi nhận lỗi, phân biệt lỗi gửi message với lỗi xử lý nghiệp vụ.
6. **STOMP:** tạo server WebSocket, ánh xạ một destination bằng @MessageMapping, gửi kết quả tới destination và subscribe từ client.
7. **RSocket:** thử request-response, request-stream và request-channel; quan sát cancellation, backpressure và lỗi reactive.
8. **Broker:** chọn một trong JMS, AMQP hoặc Kafka; học mô hình broker trước, sau đó tích hợp bằng API Spring tương ứng.
9. **Vận hành:** kiểm tra xác thực, phân quyền, retry, idempotency, timeout, observability và cách khôi phục sau khi consumer hoặc kết nối bị gián đoạn.

Không nên bắt đầu bằng việc học đồng thời tất cả broker và giao thức. Nắm vững message, channel và handler trước sẽ giúp bạn hiểu phần nào là abstraction chung, phần nào là đặc tính riêng của giao thức hoặc broker.

## 11. Các lỗi thiết kế thường gặp

- **Nhầm channel với broker:** channel trong bộ nhớ không mặc nhiên có persistence, retry qua lần khởi động lại hay phân phối giữa nhiều instance.
- **Nhầm send thành xử lý thành công:** send được chấp nhận chỉ phản ánh kết quả ở bước gửi; cần theo dõi kết quả xử lý ở tầng nghiệp vụ.
- **Đưa dữ liệu nghiệp vụ vào headers:** làm hợp đồng payload khó đọc và khó quản lý schema.
- **Giả định headers luôn được bảo toàn:** adapter và protocol mapping có thể thay đổi metadata khi message đi qua ranh giới hệ thống.
- **Không kiểm soát thread:** chuyển sang executor có thể thay đổi thứ tự hoàn tất và làm lộ race condition.
- **Dùng request-reply cho tác vụ dài:** giữ request chờ quá lâu làm tăng tài nguyên bị chiếm dụng; nên cân nhắc message kết quả bất đồng bộ.
- **Thiếu correlation ID:** khó ghép các message của cùng một yêu cầu, đặc biệt khi có splitter, aggregator hoặc nhiều service.
- **Không thiết kế idempotency:** retry hoặc giao nhận lặp có thể khiến một nghiệp vụ được thực hiện nhiều lần.
- **Bỏ qua timeout và backpressure:** consumer chậm có thể làm tăng bộ nhớ, độ trễ hoặc số message tồn đọng.
- **Coi WebSocket là hàng đợi bền vững:** client có thể ngắt kết nối và bỏ lỡ sự kiện; cần cơ chế lưu trữ hoặc đồng bộ trạng thái nếu nghiệp vụ yêu cầu.
- **Không kiểm tra quyền destination:** một kết nối đã xác thực vẫn có thể không được phép publish hoặc subscribe vào mọi destination.
- **Đồng nhất semantics giữa các broker:** ACK, retry, thứ tự, transaction và retention khác nhau giữa JMS, AMQP và Kafka.

## 12. Checklist tự đánh giá

Bạn đã nắm được nền tảng khi có thể tự trả lời:

- Message khác payload ở điểm nào? Header nên chứa loại thông tin gì?
- MessageChannel, SubscribableChannel và PollableChannel khác nhau ra sao?
- MessageHandler chịu trách nhiệm gì? Ai quyết định message đi tới handler nào?
- Vì sao một channel trong bộ nhớ không tương đương broker bền vững?
- Spring Messaging khác Spring Integration ở phạm vi trách nhiệm nào?
- STOMP frame, WebSocket connection và broker destination liên hệ với nhau thế nào?
- RSocket request-stream khác request-response ra sao? Backpressure có ý nghĩa gì?
- JMS, AMQP và Kafka khác nhau về mô hình giao nhận ở điểm nào?
- Khi xử lý lỗi, retry hoặc giao nhận lặp, làm sao tránh thực hiện nghiệp vụ hai lần?
- Làm thế nào để bảo vệ destination, theo dõi correlation ID và phát hiện consumer bị chậm?

Khi trả lời được các câu hỏi này và tự xây dựng được một flow nhỏ từ message đầu vào tới kết quả, bạn đã có nền tảng để đọc tài liệu chuyên sâu và lựa chọn giao thức theo yêu cầu thực tế của hệ thống.

## 13. Tài liệu nên tra cứu tiếp

Ưu tiên tài liệu chính thức tương ứng với lớp đang học:

- Spring Framework Reference Documentation: phần Messaging, WebSocket/STOMP và RSocket.
- Spring Integration Reference Documentation: channel, endpoint, Enterprise Integration Patterns, DSL và adapters.
- Spring JMS Reference Documentation: JmsTemplate, listener container và transaction.
- Spring AMQP Reference Documentation: exchange, queue, binding, listener container và RabbitTemplate.
- Spring for Apache Kafka Reference Documentation: producer, consumer, listener, offset và transaction.
- Tài liệu giao thức STOMP và RSocket để hiểu frame, interaction model và semantics ở tầng giao thức.

Luôn đối chiếu phiên bản tài liệu với phiên bản Spring đang dùng trong dự án. Tên API, cấu hình và khả năng tích hợp có thể thay đổi giữa các phiên bản lớn.