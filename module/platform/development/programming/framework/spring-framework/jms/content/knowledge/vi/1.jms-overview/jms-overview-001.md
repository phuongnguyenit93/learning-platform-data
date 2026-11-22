# JMS là gì và nhu cầu giao tiếp qua thông điệp

> **Chủ đề:** Spring Framework – JMS  
> **Nhóm kiến thức:** Bức tranh JMS

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích JMS giải quyết vấn đề gì, phân biệt API JMS với message broker và lớp tích hợp của Spring, mô tả luồng gửi–nhận qua queue/topic, đồng thời nhận diện các đánh đổi quan trọng khi chuyển từ lời gọi đồng bộ sang giao tiếp qua thông điệp.

## 1. Vì sao hệ thống cần giao tiếp qua thông điệp?

Giả sử dịch vụ Đơn hàng nhận yêu cầu đặt hàng. Ngoài việc lưu đơn, hệ thống còn cần gửi email xác nhận, cập nhật kho, tạo yêu cầu giao hàng và ghi dữ liệu phân tích.

**Cách gọi đồng bộ trực tiếp** có thể trông như sau:

```text
Client
  |
  v
Order Service
  |--HTTP--> Inventory Service
  |--HTTP--> Notification Service
  |--HTTP--> Shipping Service
  '--HTTP--> Analytics Service
  |
  '--> trả phản hồi cho Client
```

Mỗi bước có thể hợp lý nếu kết quả của nó thật sự cần trước khi trả lời. Tuy nhiên, khi mọi tác vụ phụ đều nằm trên đường xử lý yêu cầu, hệ thống dễ gặp các vấn đề:

1. **Phụ thuộc vào thời điểm hoạt động:** Notification Service đang bảo trì cũng có thể khiến luồng đặt hàng bị chậm hoặc thất bại, dù đơn đã được lưu.
2. **Độ trễ cộng dồn:** Nhiều lời gọi mạng và thao tác I/O làm thời gian phản hồi kéo dài.
3. **Liên kết chặt giữa các dịch vụ:** Order Service phải biết dịch vụ nào cần gọi, địa chỉ, API và cách xử lý lỗi của từng dịch vụ.
4. **Lưu lượng tăng đột biến:** Khi lượng đơn tăng nhanh, dịch vụ gửi email có thể bị quá tải mặc dù xử lý đơn vẫn đủ năng lực.
5. **Khó phục hồi tác vụ phụ:** Nếu email gửi thất bại, hệ thống phải tự quyết định lưu việc chưa hoàn thành ở đâu và thử lại như thế nào.

**Giao tiếp qua thông điệp** thêm một điểm trung gian: producer gửi một thông điệp vào hạ tầng messaging; consumer nhận thông điệp và xử lý theo nhịp riêng.

```text
Client -> Order Service -> [Broker / Queue: orders.created] -> Notification Worker
                  |                    |
                  |                    '--> thông điệp chờ khi worker tạm ngừng
                  '--> trả kết quả "đã tiếp nhận" khi thao tác cần thiết hoàn tất
```

Dịch vụ tạo đơn có thể hoàn thành phần trách nhiệm của mình mà không phải chờ việc gửi email. Notification Worker có thể được triển khai, bảo trì và tăng số lượng instance độc lập.

Điều này **không biến hệ thống thành tức thời hoặc bảo đảm thành công tuyệt đối**. Nó thay đổi hợp đồng xử lý: một tác vụ được *tiếp nhận* để thực hiện sau, và thành công cuối cùng phải được theo dõi riêng. Với tác vụ cần kết quả ngay (chẳng hạn xác nhận thanh toán trước khi phát hành vé), vẫn phải thiết kế rõ điểm chờ, trạng thái trung gian và quy tắc lỗi.

## 2. JMS là gì?

**JMS (Java Message Service)** là tên quen thuộc của API messaging trong hệ sinh thái Java. Trong Jakarta EE hiện đại, API tương ứng mang tên **Jakarta Messaging**, dùng các kiểu trong package `jakarta.jms`; các hệ thống Java EE cũ thường dùng `javax.jms`. Mục đích của API là cung cấp mô hình và hợp đồng lập trình chung để ứng dụng Java tạo, gửi, nhận và xử lý thông điệp.

Ba tầng cần tách bạch:

| Tầng | Vai trò | Ví dụ |
| --- | --- | --- |
| **JMS/Jakarta Messaging API** | Định nghĩa các giao diện và ngữ nghĩa gửi–nhận thông điệp | `ConnectionFactory`, `JMSContext`, `Message`, `Queue`, `Topic` |
| **JMS provider/message broker** | Cung cấp kết nối, định tuyến, lưu trữ và chuyển giao thông điệp theo cấu hình | Apache ActiveMQ Artemis và các provider tương thích |
| **Spring JMS** | Giúp ứng dụng Spring làm việc với JMS thuận tiện hơn | `JmsTemplate`, `@JmsListener`, listener container, message converter |

JMS **không phải chính message broker**, không phải giao thức HTTP và không tự tạo ra hàng đợi bền vững trong JVM của ứng dụng. Để hai tiến trình giao tiếp qua JMS thực tế, phải có provider phù hợp, cấu hình destination và kết nối đến provider đó.

JMS cũng **không đồng nghĩa với mọi hình thức messaging**. Kafka, AMQP và các hệ thống event streaming có hợp đồng, tính năng và cách vận hành riêng; không nên áp mô hình JMS trực tiếp lên chúng chỉ vì cùng truyền thông điệp.

### Các thành phần cơ bản

- **Producer:** bên tạo và gửi thông điệp. Ví dụ Order Service thông báo có đơn mới.
- **Consumer:** bên nhận và xử lý. Ví dụ Notification Worker gửi thư xác nhận.
- **Destination:** nơi thông điệp được gửi tới; trong JMS thường là `Queue` hoặc `Topic`.
- **Provider/broker:** thành phần trung gian quản lý destination và giao nhận.
- **Message:** đơn vị trao đổi chứa phần nội dung (*body/payload*), header tiêu chuẩn và properties do ứng dụng gắn thêm.
- **Connection / Session / JMSContext:** những đối tượng phía client dùng để giao tiếp với provider, quản lý hoạt động gửi–nhận và ngữ nghĩa xác nhận hoặc giao dịch.

Ứng dụng không cần biết bên tiêu thụ nằm ở máy chủ nào nếu cả hai cùng dùng đúng destination và tuân thủ hợp đồng thông điệp.

## 3. Hai mô hình phân phối: Queue và Topic

### 3.1. Queue — một công việc được một consumer nhận

```text
Producer A --\
              >-- [Queue: invoices.generate] --> Consumer 1
Producer B --/                            \-----> Consumer 2
```

Trong mô hình **point-to-point**, một thông điệp được chuyển đến **một consumer** đủ điều kiện của queue. Nhiều consumer cùng nhận từ queue thường được dùng để chia tải: mỗi thông điệp đi tới một trong số chúng, không tự động phát bản sao cho tất cả.

Ví dụ: hệ thống có 10.000 hóa đơn cần tạo PDF. Ba worker cùng đọc `invoices.generate` để chia nhau xử lý, nhưng mỗi hóa đơn chỉ cần một lần xử lý nghiệp vụ thành công.

Cần phân biệt: "một consumer nhận thông điệp tại một lần giao" **không có nghĩa việc xử lý nghiệp vụ được đảm bảo đúng một lần**. Khi có lỗi, broker có thể gửi lại thông điệp; consumer phải chịu được việc nhận trùng.

### 3.2. Topic — mỗi subscription nhận một bản sao phù hợp

```text
                      /--> [Subscription: analytics] --> Analytics Worker
Producer --> [Topic: orders.events]
                      \--> [Subscription: audit] -----> Audit Worker
```

Trong mô hình **publish/subscribe**, các subscription độc lập trên topic có thể nhận những bản sao riêng của cùng một thông điệp. Chẳng hạn sự kiện `OrderCreated` cần đến dịch vụ báo cáo và dịch vụ kiểm toán; xử lý ở một subscription không xác nhận thay cho subscription còn lại.

Có hai điểm cần nhớ:

- **Non-durable subscription:** thông thường chỉ tồn tại khi consumer/subscription đang hoạt động; các thông điệp được publish lúc không có subscriber đang hoạt động có thể bị bỏ lỡ.
- **Durable subscription:** provider duy trì subscription ngay khi consumer ngắt kết nối, cho phép nhận lại thông điệp còn được lưu theo điều kiện delivery, expiration, quota và chính sách provider.

Một subscription được chia sẻ giữa nhiều consumer có thể phân phối mỗi bản sao trong subscription đó cho một consumer; nó không biến toàn bộ topic thành một queue duy nhất.

| Tiêu chí | Queue | Topic |
| --- | --- | --- |
| Mục đích thường gặp | Giao một công việc cho một worker | Phát một sự kiện cho nhiều nhóm quan tâm |
| Nhiều consumer | Cùng chia việc trên một queue | Mỗi subscription nhận luồng của mình; consumer có thể chia tải trong subscription |
| Ví dụ | Tạo hóa đơn, gửi email, xử lý ảnh | Đơn hàng đã tạo, khách hàng đổi địa chỉ, cập nhật trạng thái |
| Khi consumer vắng mặt | Queue thường giữ thông điệp chờ theo chính sách lưu giữ | Phải xét durable hay non-durable subscription |
| Điều không được suy diễn | Xử lý chính xác một lần | Mọi subscriber luôn nhận đủ mọi sự kiện |

## 4. Luồng một thông điệp đi qua hệ thống

Xem ví dụ: Order Service phát thông điệp để gửi email.

1. **Nghiệp vụ tạo đơn:** dịch vụ lưu đơn và xác định cần thông báo `OrderCreated` (hoặc giao một command `SendOrderConfirmation`).
2. **Producer gửi:** chuyển payload thành message và gửi đến destination đã cấu hình.
3. **Provider tiếp nhận:** broker quyết định cách lưu, định tuyến và chuyển tới consumer theo chế độ delivery và chính sách vận hành.
4. **Consumer nhận:** listener lấy message và gọi logic gửi email.
5. **Xác nhận xử lý:** tùy session/transaction/acknowledgment mode, consumer xác nhận để broker có thể loại thông điệp đã xử lý khỏi phần đang chờ.
6. **Nếu lỗi:** message có thể được giao lại hoặc đi vào đường xử lý lỗi; chính sách retry, giới hạn số lần và dead-letter destination cần được thiết kế.

```text
[Order Service] --send--> [Broker / orders.confirm-email]
                               |
                               v
                         [Email Consumer]
                           |        |
                        thành công   lỗi
                           |        |
                         ack/commit  retry / dead-letter (tùy cấu hình)
```

**Gửi thành công** chỉ xác nhận thao tác gửi tới provider đạt điều kiện đã cấu hình; không đồng nghĩa email đã được gửi, database của consumer đã cập nhật hoặc toàn bộ quy trình kinh doanh đã hoàn thành.

### Một message mang những gì?

Tư duy hữu ích là tách phần nghiệp vụ khỏi metadata giao nhận. Ví dụ nội dung JSON được đưa vào `TextMessage`:

```json
{
  "eventId": "evt-2048",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "ORD-42",
  "occurredAt": "2026-10-30T01:00:00Z"
}
```

Đây là **ví dụ hợp đồng payload do ứng dụng tự định nghĩa**, không phải các field bắt buộc do JMS quy định. JMS có những header như `JMSMessageID`, `JMSCorrelationID`, `JMSTimestamp`, `JMSReplyTo`, `JMSExpiration` và `JMSDeliveryMode`; ứng dụng cũng có thể thêm properties phục vụ lọc hay truy vết. Không giả định `eventId` và `JMSMessageID` có cùng ý nghĩa: event ID có thể ổn định qua những lần gửi lại của nghiệp vụ, còn message ID gắn với một lần gửi trên hạ tầng.

**Event** mô tả điều đã xảy ra (`OrderCreated`). **Command** yêu cầu một bên làm việc (`SendOrderConfirmation`). Cả hai có thể truyền qua JMS, nhưng tên destination, điều kiện thành công và cách xử lý trùng nên phản ánh đúng ý nghĩa này. Không nên gửi nguyên đối tượng Java nội bộ chưa có hợp đồng phiên bản cho dịch vụ khác.

## 5. Điều nhận được và cái giá phải trả

### Những lợi ích đáng giá

**Tách biệt theo thời gian.** Producer và consumer không nhất thiết online đồng thời, đặc biệt với queue hoặc durable subscription được cấu hình phù hợp. Dịch vụ nhận có thể tạm dừng mà tác vụ chờ vẫn còn.

**Tách biệt triển khai.** Producer không cần gọi endpoint riêng của từng consumer. Một dịch vụ mới có thể đăng ký subscription mà không buộc producer phải sửa luồng gọi cho mục đích phát sự kiện.

**Hấp thụ tải đột biến.** Khi lượng message đến nhanh hơn tốc độ xử lý trong thời gian ngắn, queue đóng vai trò vùng đệm. Consumer có thể tăng số instance để xử lý dần.

**Cô lập một số lỗi.** Nếu tác vụ phụ lỗi, đường đặt hàng chính vẫn có thể hoàn thành theo hợp đồng đã thiết kế; consumer có cơ hội retry hoặc xử lý sau.

**Phù hợp công việc nền.** Gửi email, tạo báo cáo, đồng bộ tìm kiếm, cập nhật chỉ số, chuyển đổi media hay nhiều xử lý tốn thời gian khác thường không cần chặn HTTP request.

### Các đánh đổi bắt buộc hiểu

**Tính nhất quán cuối cùng (eventual consistency).** Consumer có thể xử lý sau vài mili giây hoặc nhiều phút. Chức năng đọc dữ liệu phải chấp nhận và hiển thị trạng thái "đang xử lý" khi cần.

**Hạ tầng vận hành.** Broker cũng có giới hạn dung lượng, quota, dung lượng đĩa, kết nối, xác thực và khả năng gặp sự cố. Queue không phải bộ nhớ vô hạn.

**Khó quan sát luồng hơn.** Một HTTP request không còn bao trùm toàn bộ công việc. Cần correlation ID, log, metric độ dài queue, tuổi thông điệp và tỷ lệ lỗi.

**Xử lý lặp và sai thứ tự.** Retry, nhiều worker và các nhánh song song có thể làm message được xử lý nhiều lần hoặc ngoài thứ tự kỳ vọng. Quy tắc nghiệp vụ phải chịu được các tình huống đó.

**Khó giữ giao dịch xuyên dịch vụ.** Ghi database của producer và publish JMS là hai hành động có thể thất bại ở những điểm khác nhau; cần chiến lược nhất quán như transactional outbox nếu không có một giao dịch thống nhất được hỗ trợ và cấu hình đúng.

## 6. Độ tin cậy: hiểu đủ để không hứa sai

JMS cung cấp các cơ chế delivery và acknowledgement nhưng **độ tin cậy đầu-cuối là thuộc tính của cả thiết kế**, không phải chỉ của tên API.

### Persistent không đồng nghĩa "mọi việc chắc chắn hoàn thành"

Chế độ delivery `PERSISTENT` yêu cầu provider ưu tiên bảo vệ message trước các kiểu hỏng hóc thuộc phạm vi đảm bảo của provider; `NON_PERSISTENT` thường ưu tiên hiệu năng và chấp nhận một số rủi ro mất message. Dù dùng `PERSISTENT`, message vẫn có thể hết hạn (TTL), bị tác động bởi giới hạn lưu trữ hoặc chính sách quản trị. Topic cần chọn subscription phù hợp để giữ thông điệp lúc consumer vắng mặt.

### Acknowledgment là ranh giới quan trọng

Nếu consumer báo đã xử lý trước khi thực sự ghi dữ liệu, sự cố ngay sau đó có thể làm mất công việc. Nếu consumer đã ghi dữ liệu nhưng gặp lỗi trước khi xác nhận message, broker có thể giao lại và lặp thao tác.

Trong session giao dịch, `commit` và `rollback` quyết định xác nhận/khôi phục phần việc JMS thuộc session đó. Với `AUTO_ACKNOWLEDGE` hay `CLIENT_ACKNOWLEDGE`, thời điểm xác nhận khác nhau. Cách Spring listener container cấu hình transaction/acknowledgment ảnh hưởng trực tiếp đến lúc thông điệp được coi là xử lý xong.

### Một ví dụ xử lý lặp

Consumer nhận `OrderCreated(orderId=ORD-42)` và ghi một bản ghi thưởng điểm. Database đã commit, nhưng kết nối broker đứt trước lúc broker thấy xác nhận. Lần nhận lại tiếp theo có thể ghi điểm lần hai nếu logic chỉ dùng lệnh "cộng 100 điểm".

Cách phòng vệ: dùng khóa nghiệp vụ hoặc `eventId` để phát hiện message đã xử lý; lưu trạng thái xử lý và tác động nghiệp vụ trong cùng giao dịch database khi có thể, ví dụ unique constraint trên (`consumerName`, `eventId`). Khi thấy trùng thì bỏ qua an toàn, rồi hoàn tất cơ chế xác nhận.

**Không gọi việc gửi có bảo đảm theo JMS là "exactly once end-to-end"** nếu chưa chứng minh tính nguyên tử giữa broker, database và tác dụng phụ bên ngoài (như email hay API thanh toán). Ngay cả khi message bị redeliver, kết quả nghiệp vụ cần được thiết kế để không nhân đôi.

### Retry và dead-letter

- Lỗi nhất thời (broker/DB mất kết nối, HTTP downstream timeout) có thể thử lại sau khoảng chờ hợp lý.
- Lỗi dữ liệu không thể xử lý (thiếu field bắt buộc, sai schema) cần đưa vào luồng lỗi để kiểm tra, tránh retry vô hạn.
- Retry nên có giới hạn số lần, khoảng chờ tăng dần và theo dõi rõ số lượng message lỗi.
- **Dead-letter queue (DLQ)** là cơ chế broker hoặc ứng dụng tùy cấu hình, không phải đảm bảo rằng cứ dùng JMS sẽ tự có DLQ.

## 7. Liên hệ với Spring Framework

Spring JMS cung cấp cách dùng API JMS thuận tiện mà không phải tự quản lý toàn bộ vòng đời kết nối và listener:

- `JmsTemplate` hỗ trợ gửi và nhận, chuyển đổi payload bằng `MessageConverter`.
- `@JmsListener` đánh dấu phương thức nhận; listener container chịu trách nhiệm điều phối việc gọi phương thức và tương tác với provider.
- `ConnectionFactory` là điểm kết nối đến JMS provider; cần cấu hình provider thực, ví dụ ActiveMQ Artemis.
- Spring Boot có thể tự cấu hình một phần hạ tầng JMS khi dependency và cấu hình phù hợp. Mặc định thường hướng đến queue; sử dụng topic cần cấu hình pub/sub thích hợp.

Ví dụ sau **minh họa mã trong một ứng dụng Spring đã cấu hình kết nối broker**, không phải hai file Java độc lập có thể chạy bằng `javac`:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final JmsTemplate jmsTemplate;

    public OrderEventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String orderId) {
        jmsTemplate.convertAndSend("orders.created", orderId);
    }
}
```

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class FulfillmentListener {
    @JmsListener(destination = "orders.created")
    public void onOrderCreated(String orderId) {
        // Thực hiện nghiệp vụ và ghi nhận idempotency tại đây.
        System.out.println("Received order: " + orderId);
    }
}
```

Nếu producer gọi `publish("ORD-42")` và listener nhận/ xử lý thành công, dòng log minh họa của listener là:

```text
Received order: ORD-42
```

Dòng log này **không phải kết quả chắc chắn của mỗi lần chạy**: còn phụ thuộc broker, kết nối, queue, listener, thời điểm khởi động và trạng thái lỗi. Ví dụ dùng `String` nên bộ chuyển đổi mặc định của `JmsTemplate` có thể tạo/đọc một message dạng text. Trong thực tế, payload nên có phiên bản schema, định danh sự kiện, correlation ID và quy tắc nhận trùng.

Lưu ý thêm: `JmsTemplate.convertAndSend(...)` vẫn thực hiện thao tác gửi với provider trên luồng gọi. "Messaging bất đồng bộ" chủ yếu mô tả **producer không chờ consumer hoàn tất nghiệp vụ**, chứ không nói mọi phương thức gửi đều không bao giờ chặn hoặc không thể thất bại.

## 8. Demo Java 17 chạy độc lập: hình dung sự tách thời điểm

Chương trình sau chỉ mô phỏng ý tưởng producer–consumer bằng hàng đợi trong bộ nhớ. **Nó không dùng JMS, không có broker, không có persistence và không có acknowledgment**. Mục đích là làm rõ sự khác nhau giữa "đã nhận công việc" và "đã hoàn thành công việc".

Tạo file `MessagingIdeaDemo.java`:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;

public class MessagingIdeaDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();
        CountDownLatch allowProcessing = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                String orderId = queue.take();
                allowProcessing.await();
                System.out.println("Consumer handled: " + orderId);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        worker.start();

        queue.put("ORD-42");
        System.out.println("Producer accepted: ORD-42");

        allowProcessing.countDown();
        worker.join();
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac MessagingIdeaDemo.java
java MessagingIdeaDemo
```

Đầu ra xác định của chương trình:

```text
Producer accepted: ORD-42
Consumer handled: ORD-42
```

`CountDownLatch` giữ consumer lại để thứ tự in minh họa rõ ràng; `join()` chỉ giúp chương trình demo chờ worker kết thúc trước khi thoát. Trong dịch vụ thực, producer và consumer thường là các tiến trình độc lập; provider chịu trách nhiệm trung gian. Không nên thay một hàng đợi nội bộ kiểu này cho broker nếu cần giữ công việc khi ứng dụng khởi động lại hoặc giao tiếp giữa nhiều service.

## 9. Chọn giao tiếp đồng bộ hay qua JMS?

Đặt câu hỏi đầu tiên: **Bên yêu cầu có cần kết quả nghiệp vụ hoàn tất ngay để tiếp tục hay không?** Sau đó xem các ràng buộc độ trễ, nhất quán, lỗi và vận hành.

| Tình huống | Xu hướng lựa chọn | Lý do |
| --- | --- | --- |
| Kiểm tra dữ liệu bắt buộc trước khi lưu đơn | Lời gọi trực tiếp hoặc xử lý cùng giao dịch | Phải biết kết quả trước khi chấp nhận |
| Gửi email xác nhận sau khi đơn đã lưu | Queue | Tác vụ độc lập, chậm cũng không nên chặn yêu cầu |
| Tạo thumbnail sau khi ảnh được tải lên | Queue | Công việc nền, có thể chia tải và retry |
| Nhiều dịch vụ phản ứng khi đơn được tạo | Topic với subscription phù hợp | Một sự kiện được nhiều nhóm xử lý |
| Truy vấn số dư hiện tại cần trả ngay | Đồng bộ | Cần dữ liệu tại thời điểm yêu cầu |
| Thanh toán yêu cầu xác nhận chắc chắn trước bước kế tiếp | Thiết kế rõ luồng xác nhận, có thể đồng bộ hoặc workflow bất đồng bộ | Không được coi "đã đưa vào queue" là "đã thanh toán" |

Có thể kết hợp: API HTTP tiếp nhận yêu cầu, kiểm tra và ghi trạng thái ban đầu, sau đó publish message; client nhận mã tác vụ và theo dõi trạng thái bằng API hoặc thông báo sau. Với công việc yêu cầu kết quả ngay, không ép dùng queue chỉ vì muốn hệ thống "microservices".

### Các câu hỏi thiết kế trước khi triển khai

1. **Thông điệp biểu diễn gì?** Sự kiện đã xảy ra hay lệnh yêu cầu xử lý? Ai là chủ sở hữu hợp đồng?
2. **Ai nhận?** Một worker trong nhóm hay nhiều subscription độc lập?
3. **Khi consumer ngừng hoạt động thì sao?** Cần lưu message bao lâu? Queue hay durable topic subscription?
4. **Thế nào là hoàn thành?** Đã lưu đơn, đã gửi message, đã nhận message hay đã thực hiện side effect?
5. **Nếu nhận trùng thì sao?** Khóa idempotency ở đâu và giữ bao lâu?
6. **Nếu xử lý lỗi nhiều lần thì sao?** Retry, backoff, dead-letter và cách can thiệp thủ công?
7. **Nếu queue tăng mãi thì sao?** Giới hạn tài nguyên, cảnh báo và cách giảm tốc hoặc mở rộng consumer?
8. **Theo dõi một yêu cầu bằng gì?** Event ID, correlation ID, trace ID và chỉ số queue/consumer?
9. **Ghi DB và gửi message có đồng bộ không?** Nếu không, cần transactional outbox hoặc một cơ chế phối hợp đáng tin cậy?

## 10. Hiểu sai thường gặp

- **"JMS chính là ActiveMQ."** Sai: JMS là hợp đồng API; ActiveMQ Artemis là một provider có thể triển khai hợp đồng đó.
- **"Dùng queue nghĩa là tuyệt đối không mất message."** Sai: cần xét persistence, transaction, expiration, broker storage, acknowledgment và chính sách vận hành.
- **"Một message trong queue sẽ làm nghiệp vụ đúng một lần."** Sai: redelivery có thể gây xử lý lặp; cần idempotency.
- **"Topic luôn chuyển đủ message cho mọi ứng dụng kể cả khi tắt."** Sai: non-durable và durable subscription có ngữ nghĩa khác nhau.
- **"Gọi send là xong toàn bộ nghiệp vụ."** Sai: consumer có thể chưa bắt đầu, đang retry hoặc thất bại.
- **"Mọi thao tác JMS đều bất đồng bộ."** Sai: JMS có thể nhận đồng bộ; lời gọi gửi cũng có thể chờ provider xác nhận.
- **"Có broker thì không cần quản lý tải."** Sai: broker có giới hạn và sẽ chịu áp lực nếu tốc độ sản xuất vượt tốc độ tiêu thụ lâu dài.
- **"Message luôn đến đúng thứ tự trên mọi consumer."** Sai: thứ tự phải xét session, destination, selector, multiple consumers và cơ chế retry; đừng giả định thứ tự toàn hệ thống.
- **"Bảo đảm JMS có thể thay cho giao dịch database."** Sai: phải xét ranh giới giao dịch và dữ liệu đã cập nhật của từng hệ thống.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Order Service đưa thông điệp `SendEmail` vào queue và trả HTTP 202. Có thể hiển thị "Email đã gửi" ngay không?

**Trả lời:** Không. 202 diễn đạt yêu cầu đã được tiếp nhận theo hợp đồng API. Phải có trạng thái hoặc tín hiệu từ consumer để xác nhận email thật sự được gửi.

**Câu 2.** Cùng một `OrderCreated` cần đến Analytics và Audit độc lập. Dùng một queue cho cả hai có đạt mục tiêu không?

**Trả lời:** Không nếu cả hai cùng cạnh tranh trên một queue: thường mỗi message chỉ đến một consumer. Dùng topic với hai subscription độc lập, hoặc thiết kế hai kênh công việc riêng tùy yêu cầu.

**Câu 3.** Một consumer đã ghi DB thành công nhưng mất kết nối trước khi ack; điều gì cần chuẩn bị?

**Trả lời:** Message có thể được giao lại. Phải nhận diện thông điệp trùng và giữ cho tác động nghiệp vụ idempotent.

**Câu 4.** Producer có thể phát thông điệp bền vững vào topic trong lúc một non-durable subscriber offline và chắc chắn subscriber ấy sẽ nhận sau khi khởi động lại không?

**Trả lời:** Không. Nếu cần nhận lúc vắng mặt, phải thiết kế durable subscription cùng chính sách lưu giữ phù hợp.

**Câu 5.** Lợi ích lớn nhất của messaging trong ví dụ gửi email là gì?

**Trả lời:** Tách thời điểm và trách nhiệm giữa việc tạo đơn với việc gửi email, cho phép xử lý tác vụ phụ theo nhịp riêng và phục hồi lỗi theo cơ chế đã thiết kế.

## Ghi nhớ

JMS/Jakarta Messaging cung cấp **ngôn ngữ chung cho ứng dụng Java trao đổi thông điệp**. Queue thích hợp cho việc giao một công việc đến một consumer trong nhóm; topic thích hợp cho việc phân phối sự kiện đến các subscription độc lập. Spring JMS giúp ứng dụng Spring gửi và nhận bằng những abstraction quen thuộc. Messaging hữu ích khi có công việc có thể xử lý sau và cần tách producer khỏi consumer, nhưng phải thiết kế rõ trạng thái hoàn tất, khả năng nhận trùng, retention, retry, nhất quán dữ liệu và quan sát vận hành.

### Tài liệu tham khảo chính thức

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — định nghĩa queue, topic, subscription, acknowledgment và reliability.
- [Spring Framework: Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate` và message converter.
- [Spring Framework: Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html) — nhận đồng bộ và `@JmsListener`.
- [Spring Guide: Messaging with JMS](https://spring.io/guides/gs/messaging-jms/) — ví dụ kết nối JMS và listener trong Spring Boot.