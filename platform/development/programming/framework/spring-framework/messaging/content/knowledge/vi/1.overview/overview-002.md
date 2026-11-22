# Vì sao ứng dụng cần cơ chế gửi và nhận thông điệp

Trong một ứng dụng nhỏ, một chức năng thường gọi trực tiếp chức năng khác: controller gọi service, service gọi repository hoặc gọi một API khác, rồi chờ kết quả trả về. Cách làm này đơn giản và phù hợp khi công việc ngắn, cần kết quả ngay và các thành phần có thể hoạt động cùng thời điểm.

Khi hệ thống lớn dần, một thao tác nghiệp vụ có thể kéo theo nhiều công việc: lưu đơn hàng, trừ tồn kho, thu tiền, gửi email, cập nhật báo cáo và thông báo cho người dùng. Nếu tất cả được thực hiện bằng các lời gọi đồng bộ nối tiếp, thời gian phản hồi tăng lên, các thành phần phụ thuộc chặt vào nhau và một dịch vụ phụ bị lỗi có thể làm hỏng cả luồng chính. Cơ chế gửi và nhận thông điệp giúp tách thời điểm gửi yêu cầu khỏi thời điểm xử lý, nhờ đó các thành phần phối hợp mà không phải luôn gọi trực tiếp và chờ nhau.

## 1. Vấn đề của cách gọi đồng bộ trực tiếp

Giả sử khách hàng đặt hàng. Order Service lưu đơn hàng rồi gọi lần lượt Payment Service, Inventory Service và Notification Service. Với lời gọi đồng bộ, mỗi bước thường phải chờ bước trước hoàn tất:

- Thời gian phản hồi của yêu cầu có thể gần bằng tổng thời gian của các dịch vụ được gọi.
- Nếu Notification Service chậm, người dùng vẫn phải chờ dù đơn hàng và thanh toán đã xử lý xong.
- Nếu một dịch vụ không hoạt động, lời gọi có thể thất bại và buộc dịch vụ gọi phải xử lý lỗi của một thành phần không trực tiếp thuộc trách nhiệm của nó.
- Khi tải tăng đột biến, nhiều yêu cầu đồng thời dồn đến dịch vụ phía sau, dù dịch vụ đó chỉ có thể xử lý một lượng công việc giới hạn.
- Order Service phải biết địa chỉ, giao thức, cách gọi và cách xử lý lỗi của từng dịch vụ phụ thuộc.

Đây là hiện tượng phụ thuộc cả về cấu trúc lẫn thời gian. Hai thành phần phụ thuộc cấu trúc khi bên gửi phải biết chi tiết của bên nhận. Chúng phụ thuộc thời gian khi bên nhận phải sẵn sàng đúng lúc bên gửi thực hiện lời gọi.

Lời gọi đồng bộ vẫn có chỗ đứng: đọc dữ liệu cần trả ngay, kiểm tra điều kiện trước khi xác nhận giao dịch hoặc gọi một chức năng ngắn trong cùng ứng dụng thường phù hợp với HTTP request/response hoặc lời gọi hàm. Vấn đề xuất hiện khi mọi công việc đều bị buộc vào cùng một luồng xử lý.

## 2. Thông điệp là gì?

Thông điệp (message) là một đơn vị dữ liệu được tạo ra để chuyển từ thành phần gửi (producer/sender) đến thành phần nhận (consumer/receiver). Thông điệp thường có hai phần:

- **Payload:** nội dung nghiệp vụ, chẳng hạn mã đơn hàng, số tiền, mã khách hàng hoặc thông tin một sự kiện.
- **Headers:** metadata mô tả thông điệp, chẳng hạn message ID, correlation ID, thời điểm tạo, content type, phiên bản schema hoặc thông tin định tuyến.

Ví dụ payload có thể biểu diễn sự kiện **OrderPlaced** với **orderId = "ORD-42"** và **totalCents = 129900**. Header **correlationId** giúp liên kết thông điệp với yêu cầu ban đầu khi cần theo dõi toàn bộ luồng xử lý.

Một luồng messaging thường có ba vai trò:

1. Producer tạo thông điệp và gửi thông điệp vào một channel hoặc broker.
2. Channel/broker tiếp nhận, định tuyến hoặc lưu thông điệp theo cấu hình.
3. Consumer nhận thông điệp và thực hiện công việc tương ứng.

Producer có thể không biết consumer cụ thể nào sẽ xử lý. Consumer có thể được triển khai, mở rộng hoặc khởi động lại độc lập. Broker là một thành phần trung gian thường gặp, nhưng không phải mọi cơ chế messaging đều cần broker bên ngoài: một channel trong bộ nhớ của ứng dụng cũng có thể chuyển thông điệp giữa các thành phần.

Cần phân biệt **command** và **event**:

- Command diễn tả việc người gửi yêu cầu một hành động, ví dụ **ChargePayment**. Command thường hướng đến một consumer có trách nhiệm xử lý hành động đó.
- Event diễn tả điều đã xảy ra, ví dụ **OrderPlaced**. Nhiều consumer có thể quan tâm đến cùng một event để thực hiện các phản ứng khác nhau.

Tên thông điệp nên thể hiện rõ ý nghĩa nghiệp vụ. Event thường được đặt ở dạng quá khứ vì nó mô tả một sự kiện đã xảy ra.

## 3. Vì sao ứng dụng cần cơ chế gửi và nhận thông điệp?

### 3.1. Tách thời điểm gửi và thời điểm xử lý

Producer có thể gửi thông điệp rồi tiếp tục công việc của mình mà không phải chờ consumer hoàn tất. Consumer xử lý khi có tài nguyên và thời gian phù hợp. Điều này hữu ích với những công việc không cần kết quả ngay trong phản hồi HTTP, như gửi email, tạo hóa đơn PDF, đồng bộ dữ liệu hoặc cập nhật chỉ mục tìm kiếm.

Ví dụ, sau khi lưu đơn hàng thành công, ứng dụng có thể trả mã đơn hàng cho khách. Việc gửi email xác nhận được xử lý ở một consumer riêng. Nếu gửi email mất vài giây, thời gian đó không nhất thiết kéo dài yêu cầu đặt hàng.

Đây là **temporal decoupling** (tách rời về thời gian). Mức độ tách rời phụ thuộc vào cơ chế triển khai. Một channel gọi handler trực tiếp vẫn có thể xử lý đồng bộ; muốn xử lý bất đồng bộ cần có executor, queue hoặc broker được cấu hình phù hợp.

### 3.2. Giảm phụ thuộc giữa các thành phần

Order Service chỉ cần biết cách tạo và gửi event **OrderPlaced**. Nó không cần biết Notification Service dùng thư viện email nào, Inventory Service lưu dữ liệu ra sao hay Analytics Service chạy ở đâu. Mỗi consumer chịu trách nhiệm cho phần việc của mình.

Nhờ vậy, các thành phần có thể thay đổi công nghệ hoặc triển khai độc lập hơn. Một consumer mới, chẳng hạn Fraud Detection, có thể đăng ký nhận event mà không cần sửa luồng đặt hàng, miễn là hợp đồng thông điệp vẫn tương thích.

Messaging không xóa bỏ mọi phụ thuộc. Producer và consumer vẫn phải thống nhất schema, ý nghĩa dữ liệu, phiên bản và quy tắc xử lý. Một thay đổi phá vỡ schema có thể làm consumer cũ không đọc được thông điệp mới.

### 3.3. Hấp thụ tải tăng đột biến và điều tiết tốc độ xử lý

Broker có thể giữ thông điệp trong queue khi lượng công việc đến nhanh hơn khả năng xử lý của consumer. Consumer lấy thông điệp theo tốc độ mà nó có thể xử lý. Đây là cách làm phẳng tải (load leveling), giúp một đợt tăng tải ngắn không lập tức tạo ra cùng mức tải đỉnh ở dịch vụ phía sau.

Có thể tăng số consumer để xử lý song song. Với một queue dùng mô hình competing consumers, mỗi thông điệp thường được một consumer trong nhóm nhận xử lý. Số consumer, số partition, giới hạn queue và cấu hình concurrency cần được chọn theo khả năng của hệ thống.

Queue không làm năng lực xử lý tăng vô hạn. Nếu tốc độ gửi luôn cao hơn tốc độ xử lý, backlog sẽ tăng dần. Hệ thống vẫn cần giới hạn dung lượng, backpressure, quota, cảnh báo và chính sách từ chối hoặc trì hoãn công việc khi quá tải.

### 3.4. Phát một sự kiện cho nhiều bên quan tâm

Với publish/subscribe (pub/sub), một producer phát một event và nhiều subscriber độc lập nhận được bản sao sự kiện theo cơ chế của nền tảng. Sau khi có **OrderPlaced**, hệ thống có thể đồng thời:

- yêu cầu Payment Service bắt đầu thu tiền;
- yêu cầu Inventory Service giữ hoặc trừ tồn kho;
- yêu cầu Notification Service gửi email;
- yêu cầu Analytics Service cập nhật số liệu.

Order Service không cần gọi tuần tự từng dịch vụ. Một consumer có thể gặp lỗi mà các consumer khác vẫn tiếp tục, nếu broker và cấu hình subscription hỗ trợ cách ly như vậy.

Pub/sub khác với một queue chia sẻ cho nhiều consumer cạnh tranh. Trong queue cạnh tranh, các consumer chia nhau xử lý từng message. Trong pub/sub, mỗi subscription nhận luồng sự kiện của riêng nó. Chọn sai mô hình có thể khiến một số consumer không nhận được sự kiện mà chúng cần.

### 3.5. Tăng khả năng phục hồi khi có lỗi

Một broker có lưu trữ bền vững (durable/persistent), queue hoặc subscription được cấu hình phù hợp, acknowledgement và retry có thể giữ thông điệp trong thời gian consumer tạm ngừng, sau đó giao lại để xử lý. Dead-letter queue (DLQ) có thể giữ những message liên tục thất bại để điều tra thay vì retry vô hạn.

Tuy nhiên, chỉ gửi vào một channel không đồng nghĩa thông điệp đã được lưu bền vững. Một queue trong bộ nhớ có thể mất toàn bộ message khi tiến trình dừng. Kết quả gửi thành công cũng không có nghĩa nghiệp vụ phía consumer đã hoàn tất; nó thường chỉ cho biết message đã được channel/broker tiếp nhận theo hợp đồng của API đó.

Trong nhiều hệ thống, delivery là **at-least-once**: một message có thể được giao lại nếu acknowledgement bị mất hoặc consumer gặp lỗi sau khi đã thực hiện một phần công việc. Vì vậy consumer cần xử lý lặp an toàn (idempotent), ví dụ lưu message ID hoặc mã nghiệp vụ đã xử lý để không thu tiền hai lần.

### 3.6. Kết nối các hệ thống khác nhau

Các hệ thống có thể được viết bằng ngôn ngữ, framework hoặc giao thức khác nhau. Một hệ thống gửi event qua broker; hệ thống khác nhận và chuyển đổi event sang mô hình dữ liệu nội bộ. Messaging giúp tích hợp theo hợp đồng dữ liệu thay vì buộc hai hệ thống gọi trực tiếp nhau.

Điều này hữu ích cho tích hợp với hệ thống kế toán, vận chuyển, CRM, đối tác hoặc các ứng dụng cũ. Cần xác định rõ quyền sở hữu dữ liệu, bảo mật kết nối, xác thực, schema và chính sách tương thích giữa các bên.

## 4. Luồng xử lý thông điệp điển hình

Một luồng bất đồng bộ thường diễn ra như sau:

1. Ứng dụng hoàn tất thay đổi nghiệp vụ cần thiết và tạo message/event.
2. Producer gửi message vào channel hoặc broker.
3. Channel/broker định tuyến message đến queue hoặc subscription thích hợp.
4. Consumer nhận message, kiểm tra dữ liệu và thực hiện nghiệp vụ.
5. Sau khi xử lý thành công, consumer xác nhận (acknowledge) theo cơ chế của nền tảng.
6. Nếu xử lý thất bại, message có thể được retry, trì hoãn hoặc chuyển sang DLQ tùy chính sách.

Ví dụ event đơn hàng có thể được phân phối đến nhiều consumer:

~~~mermaid
flowchart LR
    O["Order Service"] -->|"OrderPlaced"| B[("Broker / topic")]
    B --> P["Payment consumer"]
    B --> I["Inventory consumer"]
    B --> N["Notification consumer"]
    B --> A["Analytics consumer"]
~~~

Trong mô hình queue, nhiều worker có thể cùng đọc một queue để chia tải. Trong mô hình topic/pub-sub, các subscription độc lập có thể nhận cùng một event. Chi tiết phân phối phụ thuộc broker và cấu hình; không nên suy ra semantics chỉ từ tên gọi “message queue”.

## 5. Messaging khác gì lời gọi HTTP đồng bộ?

| Khía cạnh | HTTP request/response đồng bộ | Messaging bất đồng bộ |
|---|---|---|
| Nhịp xử lý | Bên gọi thường chờ phản hồi | Bên gửi có thể tiếp tục sau khi gửi |
| Phụ thuộc thời gian | Bên nhận thường phải sẵn sàng lúc gọi | Broker có thể giữ message để consumer xử lý sau nếu được cấu hình |
| Kết nối thành phần | Bên gọi thường biết endpoint và hợp đồng phản hồi | Bên gửi biết channel/topic và schema message |
| Tải đột biến | Dễ dồn trực tiếp lên dịch vụ nhận | Queue có thể đệm tải và điều tiết consumer |
| Kết quả nghiệp vụ | Có thể nhận kết quả ngay trong response | Thường phải theo dõi trạng thái hoặc dùng event phản hồi |
| Độ phức tạp | Dễ quan sát luồng request/response | Cần quản lý retry, duplicate, ordering, backlog và tracing |

Hai cách tiếp cận bổ sung cho nhau. Một ứng dụng có thể dùng HTTP để xác thực và tạo đơn hàng, sau đó dùng message để xử lý email, báo cáo hoặc đồng bộ. Nếu người dùng cần biết kết quả thanh toán ngay trước khi tiếp tục, một luồng request/response có thể phù hợp hơn; nếu chỉ cần bắt đầu xử lý và nhận cập nhật sau, messaging thường phù hợp hơn.

## 6. Spring Framework hỗ trợ messaging như thế nào?

Spring Framework cung cấp các abstraction trong module **spring-messaging** để biểu diễn message và cách các thành phần gửi/nhận message:

- **Message<T>:** đại diện cho một thông điệp có payload kiểu T và headers.
- **MessageHeaders:** chứa metadata của message.
- **MessageBuilder:** hỗ trợ tạo message và thêm headers.
- **MessageChannel:** abstraction để gửi message.
- **MessageHandler:** abstraction cho thành phần xử lý message.

Ví dụ tạo một message trong Spring:

~~~java
Message<OrderPlaced> message = MessageBuilder
        .withPayload(event)
        .setHeader("correlationId", correlationId)
        .build();

boolean accepted = channel.send(message);
~~~

Đoạn mã này minh họa việc đóng gói payload và gửi qua một channel đã được cấu hình. Nó chưa tự tạo broker, queue hay bảo đảm lưu trữ bền vững. Giá trị **accepted** chỉ phản ánh kết quả gửi theo hợp đồng của channel; không nên diễn giải nó là consumer đã xử lý xong nghiệp vụ.

Một handler có thể nhận và xử lý message:

~~~java
public class PaymentHandler implements MessageHandler {

    @Override
    public void handleMessage(Message<?> message) {
        OrderPlaced event = (OrderPlaced) message.getPayload();
        // Kiểm tra và xử lý thanh toán cho event.
    }
}
~~~

Trong ứng dụng thực tế, handler cần được đăng ký với channel hoặc endpoint phù hợp. Phần tích hợp cụ thể phụ thuộc công nghệ được chọn:

- Spring Integration cung cấp nhiều channel, endpoint và adapter để kết nối hệ thống.
- Spring AMQP hỗ trợ tích hợp với AMQP broker như RabbitMQ.
- Spring for Apache Kafka tích hợp với Apache Kafka.
- Spring JMS hỗ trợ Java Message Service.
- Spring WebSocket/STOMP hỗ trợ trao đổi message thời gian thực giữa server và client qua WebSocket.

Các thư viện tích hợp cung cấp cách kết nối và cấu hình transport tương ứng. **spring-messaging** cung cấp abstraction chung; bản thân abstraction này không phải một message broker.

Cũng cần phân biệt messaging với **@Async**. **@Async** chuyển lời gọi sang executor khác trong ứng dụng, nhưng công việc vẫn thường nằm trong tiến trình hiện tại và không tự có lưu trữ bền vững, retry sau khi tiến trình chết hay khả năng giao tiếp liên dịch vụ. Nó hữu ích cho tác vụ nền nội bộ, còn broker messaging phù hợp khi cần queue, tích hợp hoặc tách biệt tiến trình.

## 7. Ví dụ Java 17: producer gửi, consumer nhận qua queue

Ví dụ sau dùng **BlockingQueue** của Java để minh họa cách producer đưa message vào hàng đợi và consumer lấy ra xử lý. Đây là mô hình trong bộ nhớ của một tiến trình, không phải broker bền vững.

Tạo file **MessagingWhyDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class MessagingWhyDemo {

    record OrderPlaced(String orderId, int totalCents) {}

    record Message<T>(String id, T payload) {}

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message<OrderPlaced>> queue =
                new ArrayBlockingQueue<>(10);

        // Chỉ dùng để làm thứ tự log trong ví dụ luôn ổn định.
        CountDownLatch allowConsumerToPrint = new CountDownLatch(1);

        Thread consumer = new Thread(() -> {
            try {
                Message<OrderPlaced> received = queue.take();
                allowConsumerToPrint.await();

                System.out.printf(
                        "Consumer processed %s (%d cents)%n",
                        received.payload().orderId(),
                        received.payload().totalCents()
                );
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();

        Message<OrderPlaced> outgoing = new Message<>(
                "msg-001",
                new OrderPlaced("ORD-42", 129_900)
        );

        queue.put(outgoing);
        System.out.println("Producer queued " + outgoing.id());
        allowConsumerToPrint.countDown();

        consumer.join();
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac MessagingWhyDemo.java
java MessagingWhyDemo
~~~

Kết quả:

~~~text
Producer queued msg-001
Consumer processed ORD-42 (129900 cents)
~~~

Producer chỉ đưa message vào queue rồi tiếp tục. Consumer lấy message từ queue và xử lý độc lập. **CountDownLatch** trong ví dụ chỉ đảm bảo thứ tự hai dòng log để output dễ kiểm tra; nó không phải thành phần bắt buộc của messaging.

**ArrayBlockingQueue** có dung lượng giới hạn. Khi queue đầy, **put** sẽ chờ đến khi có chỗ trống, minh họa một dạng backpressure đơn giản. Tuy nhiên queue này chỉ nằm trong bộ nhớ của tiến trình: nếu ứng dụng dừng đột ngột, message chưa xử lý có thể mất. Broker thực tế cần được cấu hình persistence, acknowledgement, retry và DLQ nếu nghiệp vụ yêu cầu những bảo đảm đó.

## 8. Những đánh đổi cần cân nhắc

Messaging giải quyết một số vấn đề về phối hợp hệ thống, nhưng cũng tạo ra trách nhiệm thiết kế mới:

- **Eventual consistency:** producer và consumer xử lý ở các thời điểm khác nhau, nên dữ liệu ở các hệ thống có thể tạm thời chưa đồng nhất. Giao diện cần biểu diễn trạng thái đang xử lý nếu người dùng phải chờ kết quả.
- **Duplicate delivery:** consumer có thể nhận cùng một message nhiều lần. Thiết kế handler idempotent và dùng khóa nghiệp vụ/message ID để chống xử lý trùng.
- **Ordering:** không phải broker nào cũng bảo đảm thứ tự trên toàn hệ thống. Nếu thứ tự quan trọng, cần chọn queue/partition key và quy tắc xử lý phù hợp.
- **Retry và message lỗi:** retry vô hạn có thể làm nghẽn queue. Dùng giới hạn số lần retry, khoảng chờ tăng dần và DLQ để điều tra message lỗi.
- **Giao dịch dữ liệu và gửi message:** nếu ứng dụng commit dữ liệu vào database nhưng gửi event thất bại (hoặc ngược lại), trạng thái có thể lệch nhau. Transactional outbox là một mẫu thiết kế phổ biến: ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng database transaction, sau đó một tiến trình riêng phát event từ outbox.
- **Schema evolution:** producer và consumer có thể được triển khai ở thời điểm khác nhau. Nên bổ sung field theo hướng tương thích, quản lý phiên bản schema và tránh đổi nghĩa field đang được sử dụng.
- **Quan sát và truy vết:** một yêu cầu có thể đi qua nhiều message và consumer. Dùng correlation ID/trace context, log có cấu trúc, metric về queue depth, tuổi message, thời gian xử lý và tỷ lệ lỗi.
- **Bảo mật:** xác thực producer/consumer, phân quyền truy cập queue/topic, mã hóa kết nối và kiểm tra dữ liệu đầu vào. Không đưa bí mật hoặc dữ liệu nhạy cảm không cần thiết vào payload hay headers.

Không nên đưa mọi lời gọi vào message broker. Nếu một chức năng cần phản hồi ngay, cần tính nhất quán tức thời hoặc chỉ là lời gọi ngắn trong cùng ứng dụng, lời gọi trực tiếp thường đơn giản hơn. Messaging phù hợp khi lợi ích từ xử lý nền, đệm tải, fan-out, tích hợp hoặc tách biệt vòng đời thành phần lớn hơn chi phí vận hành.

## 9. Cách quyết định có nên dùng messaging

Hãy cân nhắc messaging khi có một hoặc nhiều dấu hiệu sau:

- Công việc có thể hoàn thành sau khi phản hồi chính đã được gửi.
- Một sự kiện cần kích hoạt nhiều quy trình độc lập.
- Dịch vụ nhận có tải biến động hoặc cần xử lý theo tốc độ riêng.
- Producer và consumer cần triển khai, mở rộng hoặc phục hồi độc lập.
- Hệ thống cần tích hợp với nhiều ứng dụng hoặc công nghệ khác nhau.
- Cần lưu giữ công việc khi consumer tạm thời không sẵn sàng.

Trước khi chọn giải pháp, hãy trả lời: message là command hay event; ai sở hữu schema; gửi thành công có nghĩa là gì; có cần lưu bền vững không; xử lý trùng ra sao; cần thứ tự ở phạm vi nào; lỗi được retry bao nhiêu lần; message lỗi đi đâu; và người dùng theo dõi kết quả bằng cách nào.

Cơ chế gửi và nhận thông điệp giúp ứng dụng phối hợp công việc mà không buộc mọi thành phần phải gọi và chờ nhau trong cùng một luồng. Giá trị của nó đến từ việc tách rời thời gian, giảm phụ thuộc, điều tiết tải và phân phối sự kiện. Để đạt được độ tin cậy mong muốn, những lợi ích đó phải đi cùng hợp đồng message rõ ràng, consumer idempotent, chính sách lỗi và cấu hình broker phù hợp.