# Khi nào dùng ActiveMQ; khi nào cân nhắc HTTP, RabbitMQ hoặc Kafka

> **Chương:** Tổng quan ActiveMQ  
> **Học phần:** INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ — giao tiếp bất đồng bộ với Apache ActiveMQ Classic và Artemis, queue, topic, routing, JMS; triển khai producer/consumer Java và vận hành broker đáng tin cậy.

## 1. Mục tiêu và câu hỏi cần giải quyết

Sau bài học, bạn có thể:

1. Phân biệt lời gọi đồng bộ HTTP với trao đổi thông điệp bất đồng bộ, hiểu tác động đến độ trễ, lỗi và tính nhất quán.
2. Chọn ActiveMQ, RabbitMQ hoặc Kafka dựa trên **hành vi cần có của hệ thống**: hàng đợi công việc, định tuyến, phân phối sự kiện, lưu lịch sử để đọc lại hay tích hợp JMS.
3. Biết khi nào ActiveMQ Classic phù hợp và khi nào nên khảo sát ActiveMQ Artemis.
4. Thiết kế luồng producer/consumer Java với persistence, acknowledgment, transaction, retry/redelivery, dead-letter queue (DLQ) và xử lý trùng lặp.
5. Nhận diện các yêu cầu vận hành thực tế: bảo mật, dự phòng, giám sát, giới hạn tải và phục hồi sau lỗi.

Không có broker nào tốt nhất cho mọi tình huống. Câu hỏi quyết định là: **bên gọi cần kết quả ngay, cần giao việc để xử lý sau, hay cần ghi lại dòng sự kiện để nhiều hệ thống có thể đọc theo tiến độ riêng?**

## 2. Ba kiểu giao tiếp dễ bị nhầm lẫn

### 2.1. HTTP: yêu cầu và phản hồi

Ví dụ: ứng dụng gọi **POST /orders**, API xác thực dữ liệu, ghi đơn hàng và trả về mã đơn.

~~~text
Trình duyệt --HTTP POST--> Order API --trả HTTP 201 + orderId--> Trình duyệt
~~~

HTTP thường là lựa chọn đầu tiên nếu bên gọi cần biết **kết quả nghiệp vụ ngay trong lần gọi đó**: đăng nhập, kiểm tra giá, đọc hồ sơ, xác nhận đặt hàng đã được ghi nhận. HTTP không đồng nghĩa với xử lý chậm hoặc luôn đồng bộ: API có thể trả **202 Accepted** rồi xử lý nền; HTTP cũng có streaming và các mô hình callback. Điểm phân biệt ở đây là **hợp đồng giao tiếp**: caller có đang phụ thuộc vào kết quả tức thì từ callee hay không.

Với chuỗi gọi đồng bộ A → B → C, nếu C gặp sự cố, thời gian phản hồi và tính sẵn sàng của A có thể bị ảnh hưởng. Timeout và retry cần được thiết kế cẩn thận vì caller có thể không biết yêu cầu trước đó đã được xử lý hay chưa.

### 2.2. Message queue: giao một việc và xử lý sau

Ví dụ: sau khi đặt hàng, hệ thống cần tạo vận đơn, gửi email và đồng bộ kho mà không bắt khách hàng chờ tất cả hoàn tất.

~~~text
Order API --ghi thông điệp--> Broker queue --phát cho consumer--> Shipping worker
                   |                                  |
             nhận vào bền vững                  xử lý + xác nhận (ack)
~~~

Producer và consumer được tách về **thời điểm hoạt động**: consumer tạm ngừng thì broker có thể giữ thông điệp chờ xử lý, tùy chế độ lưu trữ, dung lượng, thời hạn sống và cấu hình. Đây là nhóm bài toán ActiveMQ và RabbitMQ xử lý tốt. Việc đưa thông điệp vào queue **không tự động bảo đảm** rằng công việc sẽ hoàn tất chính xác một lần.

### 2.3. Event stream: lưu dòng sự kiện để nhiều nhóm đọc

Ví dụ: mỗi sự kiện thay đổi đơn hàng cần được hệ thống phân tích, chống gian lận, tìm kiếm và kho dữ liệu đọc độc lập; nhóm mới cần đọc lại sự kiện vài ngày trước.

~~~text
Order Service --> order-events (log giữ theo retention)
                          |--> Consumer group: Analytics
                          |--> Consumer group: Fraud
                          |--> Consumer group: Search
                       mỗi nhóm lưu tiến độ đọc riêng
~~~

Kafka được xây cho mô hình **log phân vùng, lưu theo chính sách retention và đọc lại theo offset**. ActiveMQ topic cũng có thể phát một sự kiện đến nhiều subscriber, nhưng **topic JMS không phải mặc nhiên là kho lưu lịch sử có khả năng tua lại tùy ý**. Durable subscription giữ các thông điệp phù hợp khi subscriber tạm offline theo hợp đồng và cấu hình; nó không tương đương cơ chế replay theo offset của Kafka.

## 3. ActiveMQ là gì, và Classic khác Artemis ở đâu?

**Apache ActiveMQ** là hệ sinh thái message broker mã nguồn mở. Có hai nhánh cần phân biệt khi ra quyết định:

| Tiêu chí | ActiveMQ Classic | ActiveMQ Artemis |
|---|---|---|
| Định vị | Broker lâu đời, phổ biến trong hệ thống JMS hiện hữu | Broker thế hệ mới với kiến trúc lưu trữ, routing và HA riêng |
| Tích hợp Java | JMS và các ứng dụng sẵn có dùng client/protocol của Classic | JMS cùng các client/protocol Artemis hỗ trợ |
| Mô hình nổi bật | Queue, topic, selector, durable subscription, cơ chế lưu bền và redelivery | Address, queue, **anycast** và **multicast**; có thể trình bày thành JMS queue/topic |
| Khi nên ưu tiên đánh giá | Ứng dụng đang vận hành ổn định, phụ thuộc tính tương thích cụ thể với Classic | Dự án mới hoặc kế hoạch nâng cấp cần xem xét hiệu năng, HA, khả năng mở rộng và vận hành |
| Lưu ý chuyển đổi | Phụ thuộc phiên bản/client, OpenWire, cấu hình broker và hành vi ứng dụng hiện có | Không coi việc đổi broker là thay thế cấu hình đơn thuần; cần thử protocol, JMS API, durability, transaction và routing |

**JMS (Java Message Service)** là API chuẩn để ứng dụng Java gửi và nhận thông điệp. JMS không phải tên giao thức truyền trên mạng. Ví dụ, ứng dụng dùng **jakarta.jms** hay **javax.jms** phụ thuộc vào phiên bản API và bộ client được chọn; không trộn hai hệ package trong cùng ví dụ nếu chưa xác minh hỗ trợ. Các giao thức như OpenWire, AMQP, MQTT, STOMP hay giao thức Core phụ thuộc dòng broker, phiên bản và cấu hình acceptor/client. **AMQP 1.0 không giống AMQP 0-9-1**, vì vậy ghi “cùng hỗ trợ AMQP” chưa đủ để kết luận hai client thay thế được nhau.

Trong Artemis, một **address** có thể định tuyến đến các queue theo hai kiểu chính:

- **Anycast:** một thông điệp được chuyển đến một queue phù hợp; nhiều consumer của queue đó cạnh tranh nhận việc.
- **Multicast:** thông điệp có thể được sao chép đến các queue subscription phù hợp, nhờ đó nhiều nhóm tiêu thụ nhận bản riêng.

Cấu hình address/queue, JMS queue/topic và các quy tắc routing phải khớp nhau. Khi ứng dụng yêu cầu một nhóm xử lý mỗi việc, dùng queue; khi mỗi nhóm độc lập đều cần thông báo, dùng topic/durable subscription hoặc cấu hình multicast thích hợp.

## 4. Bảng so sánh để chọn công nghệ

| Câu hỏi thiết kế | HTTP | ActiveMQ (Classic/Artemis) | RabbitMQ | Kafka |
|---|---|---|---|---|
| Tương tác chủ đạo | Request/response giữa dịch vụ | Queue công việc và pub/sub qua broker, đặc biệt trong hệ Java/JMS | Queue và routing thông điệp linh hoạt qua exchange/binding | Distributed event log, topic phân vùng và consumer group |
| Producer cần consumer đang chạy? | Với phản hồi đồng bộ: thường có | Không, nếu broker nhận và giữ thông điệp theo cấu hình | Không, nếu queue tồn tại và thông điệp được lưu phù hợp | Không; record được giữ theo retention đã cấu hình |
| Phân phối đến nhiều nhóm | Caller phải gọi nhiều nơi hoặc có lớp trung gian | Topic/subscription hoặc routing nhiều queue | Fanout/topic/direct exchange và binding | Nhiều consumer group độc lập |
| Đọc lại lịch sử nhiều ngày | Phải có kho riêng | Không phải đặc tính mặc định của queue/topic JMS | Queue truyền thống thường xóa sau ack; RabbitMQ Streams là ngoại lệ cần đánh giá riêng | Mục tiêu thiết kế cốt lõi: đọc lại theo offset trong retention |
| API/giao thức nổi bật | HTTP/REST/gRPC qua HTTP/2, v.v. | JMS cho Java; giao thức cụ thể tùy broker | Hệ sinh thái AMQP 0-9-1 và mô hình exchange; có giao thức khác tùy phiên bản | Kafka client protocol và hệ sinh thái event streaming |
| Đơn vị ordering cần chú ý | Thứ tự từng lời gọi không tự tạo thứ tự tổng thể | Dispatch, priority, redelivery và nhiều consumer có thể làm thay đổi thứ tự xử lý | Nhiều consumer, retry và requeue ảnh hưởng thứ tự quan sát | Thứ tự record **trong mỗi partition**, không có thứ tự tổng trên toàn topic |
| Công cụ vận hành cần hiểu | Timeout, retry, rate limit, circuit breaker | Ack/transaction, DLQ, store, paging/flow control, HA | Publisher confirms, consumer ack, prefetch, DLX, queue type | Partition, replication, offset, consumer lag, retention |
| Điểm mạnh điển hình | Đơn giản, phản hồi tức thì, dễ dùng từ nhiều client | JMS, xử lý nền bền vững, tách producer/consumer | Routing theo exchange/binding, hàng đợi đa ngôn ngữ | Replay, stream processing, nhiều nhóm đọc lịch sử |
| Chi phí cần cân nhắc | Phụ thuộc trực tiếp vào callee | Cần broker và vận hành lifecycle của message | Cần broker và quản lý routing/queue | Cần thiết kế partition, retention, consumer group và cluster |

**Đừng chọn dựa trên một khẩu hiệu như “Kafka nhanh nhất” hay “queue bảo đảm đúng một lần”.** Độ trễ, thông lượng và chi phí phụ thuộc kích thước message, persistence, replication, batch, số consumer, phần cứng, topology và cách đo. Luôn thử tải với dữ liệu thực tế.

### Sơ đồ quyết định ban đầu

~~~mermaid
flowchart TD
    A["Nhu cầu giao tiếp?"] --> B{"Caller cần kết quả nghiệp vụ ngay?"}
    B -->|Có| H["HTTP API / RPC"]
    B -->|Không| C{"Cần giữ lịch sử và đọc lại theo offset?"}
    C -->|Có| K["Đánh giá Kafka"]
    C -->|Không| D{"Đang dùng JMS, có hợp đồng Java/JMS?"}
    D -->|Có| M["Đánh giá ActiveMQ Classic hoặc Artemis"]
    D -->|Không| E{"Cần exchange/binding linh hoạt?"}
    E -->|Có| R["Đánh giá RabbitMQ"]
    E -->|Không| F["So sánh ActiveMQ, RabbitMQ theo hệ sinh thái và vận hành"]
~~~

Sơ đồ là **bộ lọc đầu tiên**, không phải phép quyết định tuyệt đối. Một hệ thống có thể dùng HTTP cho API đối ngoại, ActiveMQ cho tác vụ nền và Kafka cho luồng phân tích. RabbitMQ cũng có cơ chế stream trong những cấu hình riêng; ActiveMQ cũng có khả năng routing phức tạp tùy nhánh. Hãy xác minh yêu cầu bắt buộc trước khi chốt.

## 5. Khi nào ActiveMQ là lựa chọn hợp lý?

### Trường hợp A — Hệ thống Java/JMS đã có sẵn

Ứng dụng ERP dùng **ConnectionFactory**, **Queue**, **MessageListener**, **Session** và JMS transaction. Nhiều thành phần đã được kiểm thử theo chính sách acknowledgment/redelivery. Duy trì hoặc hiện đại hóa trên ActiveMQ thường tiết kiệm công sức tích hợp hơn đổi toàn bộ API và hành vi consumer chỉ để thay broker.

**Chọn hướng:** đánh giá Classic nếu cần giữ tương thích đặc thù của hệ thống hiện tại; đánh giá Artemis nếu dự án có mục tiêu nâng cấp và đã kiểm thử đường chuyển đổi. Đừng chọn chỉ theo tên “ActiveMQ”: xác định rõ **Classic hay Artemis**, version, client, protocol và cách lưu bền.

### Trường hợp B — Tác vụ nền có thể xử lý lại

Ứng dụng đặt hàng ghi nhận đơn trong cơ sở dữ liệu rồi cần tạo nhãn giao hàng. Một queue **shipping.create** giúp worker xử lý ở tốc độ riêng; khi worker tạm dừng, công việc có thể chờ trên broker. Nhóm worker có thể mở rộng số consumer để tăng năng lực.

Điều kiện quan trọng:

- Producer gửi thông điệp **persistent** và broker cấu hình store/replication phù hợp; việc nhận được xác nhận gửi phải phù hợp hợp đồng bền vững của client/broker.
- Consumer chỉ **ack/commit sau khi xử lý thành công**; nếu xử lý lỗi, rollback hoặc để cơ chế redelivery hoạt động.
- Công việc phải **idempotent** vì cùng message có thể được giao lại.
- Có giới hạn số lần thử và DLQ để tránh lỗi cố định lặp mãi.

### Trường hợp C — Nhiều dịch vụ Java cần nhận cùng một thông báo

Khi đơn hàng được tạo, bộ phận hóa đơn và thông báo đều cần biết. Một JMS topic với **durable subscription được tạo và cấu hình đúng** cho mỗi nhóm có thể bảo toàn việc nhận thông báo khi nhóm tạm offline theo chính sách broker. Nếu chỉ dùng non-durable subscriber, nhóm offline thường sẽ bỏ lỡ các message phát trong thời gian đó.

**Kiểm tra:** mỗi nhóm cần bản riêng hay chỉ một worker trong nhóm xử lý? Có phải đọc lại dữ liệu nhiều tuần trước không? Nếu replay theo mốc thời gian là yêu cầu quan trọng, Kafka có thể thích hợp hơn.

### Trường hợp D — Muốn tách nhịp triển khai giữa các dịch vụ

Một dịch vụ gửi sự kiện nội bộ theo schema ổn định; consumer có thể được triển khai, tạm dừng và mở rộng độc lập. Broker giúp giảm phụ thuộc về thời điểm, nhưng **không xóa phụ thuộc dữ liệu**: thay đổi cấu trúc payload phải có version, quy tắc tương thích và kế hoạch rollout.

**Không nên đưa mọi thao tác sang message queue**: việc tra cứu số dư hiện tại hoặc kiểm tra quyền trước khi hiển thị màn hình thường cần phản hồi rõ ràng ngay; HTTP/RPC và dữ liệu truy vấn phù hợp hơn.

## 6. Khi nào nên cân nhắc công nghệ khác?

### Ưu tiên HTTP khi...

- Caller cần trả lỗi/giá trị ngay trong cùng giao dịch tương tác; một request có đích cụ thể, ít hệ tiêu thụ.
- Lưu lượng và độ phức tạp thấp, kết nối giữa các dịch vụ ổn định, retry/timeout được quản lý tốt.
- Việc bổ sung broker sẽ tăng đáng kể chi phí vận hành mà không giải quyết vấn đề thực tế.

Ví dụ: kiểm tra mã giảm giá trước khi thanh toán. API cần biết mã có hợp lệ để hiển thị ngay. Một queue trả kết quả sau vài giây không phù hợp trải nghiệm này.

### Ưu tiên đánh giá RabbitMQ khi...

- Ứng dụng đa ngôn ngữ đang dùng AMQP 0-9-1 và cần mô hình **exchange → binding → queue** với routing key, fanout, topic hoặc direct.
- Work queue cần cấu hình prefetch, consumer acknowledgment, publisher confirms, DLX và loại queue phù hợp (ví dụ quorum queue) với yêu cầu chịu lỗi.
- Đội ngũ đã có năng lực vận hành RabbitMQ, công cụ quan sát và mô hình routing tương thích nhu cầu.

Ví dụ: hệ thống xử lý ảnh phân loại job theo loại tệp và độ ưu tiên; nhiều worker Python/Go/Java nhận qua các queue được route từ exchange. RabbitMQ thường là ứng viên tự nhiên để thử nghiệm. ActiveMQ cũng làm được nhiều trường hợp; hãy so sánh độ phức tạp routing, vận hành và client thực tế.

### Ưu tiên đánh giá Kafka khi...

- Cần **lưu event lâu dài theo retention**, đọc lại từ offset cũ, tái xây dựng materialized view hoặc backfill dữ liệu cho consumer mới.
- Nhiều hệ thống độc lập cần đọc cùng dòng sự kiện ở tốc độ riêng.
- Dữ liệu có khóa (ví dụ orderId) và cần thứ tự **trong cùng partition**; throughput và mở rộng dựa trên thiết kế partition.
- Có nhu cầu hệ sinh thái stream processing, CDC hoặc data platform.

Ví dụ: mọi thay đổi trạng thái đơn hàng đi vào **orders.events**; nhóm fraud đọc realtime, nhóm báo cáo đọc lại tuần trước để sửa pipeline. Kafka phù hợp hơn queue chỉ tồn tại cho đến lúc được ack.

Kafka **không thay thế mọi work queue**. Consumer group có thể chia việc giữa các instance, nhưng retry từng message, trì hoãn độc lập và DLQ phải thiết kế theo đặc thù partition/offset; không giả định cơ chế giống JMS queue. Ngược lại, Kafka có các cơ chế transaction và xử lý exactly-once trong những phạm vi hỗ trợ cụ thể, nhưng **không tự biến giao dịch với cơ sở dữ liệu bên ngoài thành exactly-once end-to-end**.

## 7. Ví dụ kiến trúc: đặt hàng không làm khách đợi tác vụ nền

Giả sử yêu cầu là:

- API xác nhận đơn hàng đã được ghi vào database và trả **201 Created** cùng orderId.
- Gửi yêu cầu tạo vận đơn qua ActiveMQ cho shipping worker.
- Nếu worker ngừng 15 phút, việc đã nhận vào broker vẫn còn để xử lý khi worker hoạt động lại, trong giới hạn persistence, retention và dung lượng.
- Không tạo hai vận đơn khi consumer bị khởi động lại đúng lúc xử lý xong.

Thiết kế đáng tin cậy nên dùng **transactional outbox** ở phía producer:

~~~mermaid
flowchart LR
    U["Client"] -->|HTTP POST /orders| API["Order API"]
    API -->|Một DB transaction| DB[("orders + outbox")]
    DB -->|Đọc bản ghi outbox đã commit| Relay["Outbox relay"]
    Relay -->|JMS persistent message| Q[["ActiveMQ queue: shipping.create"]]
    Q -->|deliver / redeliver| W["Shipping worker"]
    W -->|transaction: kiểm tra eventId + tạo yêu cầu| S[("Shipping DB")]
    W -->|JMS commit sau khi xử lý| Q
~~~

**Vì sao cần outbox?** Nếu API ghi database thành công nhưng chết trước khi gửi message, công việc shipping sẽ bị thất lạc. Nếu gửi message trước rồi transaction database rollback, worker có thể xử lý đơn hàng chưa tồn tại. Ghi **orders** và **outbox** trong cùng một DB transaction đóng khoảng trống này. Một relay đọc outbox, gửi message và đánh dấu đã phát; relay cũng có thể phát trùng khi gặp lỗi, do đó consumer vẫn phải idempotent.

Quy trình điển hình:

1. API bắt đầu DB transaction, ghi đơn và bản ghi outbox có **eventId** duy nhất, commit, trả 201.
2. Relay gửi message với eventId, orderId và schema version; gửi persistent, theo dõi xác nhận, cập nhật trạng thái outbox khi hoàn tất.
3. Broker phân phối đến shipping worker. Worker xử lý **eventId** dưới một transaction cơ sở dữ liệu: nếu đã xử lý thì bỏ qua; nếu chưa thì ghi thay đổi nghiệp vụ và dấu đã xử lý.
4. Worker commit JMS sau khi transaction nghiệp vụ thành công. Nếu chết sau DB commit nhưng trước JMS commit, broker có thể redeliver; kiểm tra eventId ngăn tạo trùng.
5. Message lỗi tạm thời được redeliver theo backoff. Message lỗi cố định hoặc đã vượt ngưỡng thử được chuyển DLQ theo cấu hình và phải có quy trình kiểm tra, sửa dữ liệu, phát lại có kiểm soát.

**Giới hạn cần nói rõ:** nếu shipping worker gọi API hãng vận chuyển tạo nhãn, kiểm tra trùng chỉ ở DB nội bộ vẫn chưa đủ nếu request trước đó đã tới đối tác rồi timeout. Sử dụng idempotency key ở API đối tác nếu có; nếu không, cần đối soát trạng thái trước khi thử lại.

## 8. Java JMS thực hành: producer và consumer có transaction

Ví dụ dưới dùng **Jakarta Messaging (jakarta.jms)** và một **ConnectionFactory** do ứng dụng cấu hình bằng bộ client tương thích với phiên bản ActiveMQ Classic/Artemis đang chạy. Không lấy tên class/URL của một broker làm mặc định cho broker còn lại.

Đích là queue **shipping.create**. Đoạn code xử lý một message mỗi lần gọi để minh họa rõ transaction; ứng dụng thực tế thường có vòng lặp consumer hoặc listener và cơ chế shutdown phù hợp.

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import java.util.UUID;

public final class ShippingMessaging {
    private static final String QUEUE_NAME = "shipping.create";

    private ShippingMessaging() {}

    // Chỉ minh họa việc gửi JMS. Nếu đơn hàng đã ghi vào DB,
    // dùng transactional outbox để phối hợp DB -> JMS.
    public static String publish(ConnectionFactory factory, String orderId) {
        String eventId = UUID.randomUUID().toString();

        try (JMSContext context =
                     factory.createContext(JMSContext.SESSION_TRANSACTED)) {
            Queue queue = context.createQueue(QUEUE_NAME);

            TextMessage message = context.createTextMessage(orderId);
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("schemaVersion", "1");

            context.createProducer()
                   .setDeliveryMode(DeliveryMode.PERSISTENT)
                   .send(queue, message);

            context.commit(); // Commit giao dịch JMS phía producer
            return eventId;
        }
    }

    // OrderHandler phải tự đảm bảo xử lý eventId chỉ một lần về mặt
    // nghiệp vụ; lưu eventId và thay đổi nghiệp vụ trong cùng DB txn.
    @FunctionalInterface
    public interface OrderHandler {
        void handle(String eventId, String orderId) throws Exception;
    }

    // Trả false nếu chưa có message sau thời gian chờ.
    public static boolean consumeOnce(ConnectionFactory factory,
                                      OrderHandler handler) {
        try (JMSContext context =
                     factory.createContext(JMSContext.SESSION_TRANSACTED)) {
            JMSConsumer consumer =
                    context.createConsumer(context.createQueue(QUEUE_NAME));

            Message message = consumer.receive(3000);
            if (message == null) {
                return false;
            }

            try {
                String eventId = message.getStringProperty("eventId");
                String orderId = message.getBody(String.class);

                handler.handle(eventId, orderId); // Hoàn tất DB txn trước
                context.commit();                 // Sau đó mới xác nhận JMS
                return true;
            } catch (Exception failure) {
                context.rollback(); // Cho phép redelivery theo chính sách broker
                throw new IllegalStateException(
                        "Không xử lý được shipping event", failure);
            }
        }
    }
}
~~~

### Điều gì xảy ra trong code?

- **PERSISTENT** yêu cầu chế độ gửi bền vững theo JMS, nhưng mức chịu lỗi thực tế còn phụ thuộc cấu hình store, đồng bộ ghi, replication, broker và cơ chế xác nhận.
- **SESSION_TRANSACTED** làm các thao tác JMS thuộc giao dịch session; **commit** consumer xác nhận message sau khi xử lý, còn **rollback** khiến message đủ điều kiện được giao lại.
- **JMS transaction không đồng nghĩa DB transaction**. Hai commit là hai hệ thống độc lập, vì vậy vẫn phải có outbox và idempotency để xử lý điểm lỗi nằm giữa chúng.
- Message có thể được gửi lại khi kết nối đứt, client timeout hoặc consumer chết. **eventId** là khóa ứng dụng quản lý, không đồng nghĩa với JMSMessageID; xử lý trùng lặp nên dựa trên định danh nghiệp vụ/event được lưu ổn định.
- Nếu dùng **CLIENT_ACKNOWLEDGE** thay cho transacted session, cần nhớ một lần gọi acknowledge theo JMS có thể xác nhận **mọi message đã nhận trong cùng session** đến thời điểm đó. Không mặc nhiên coi acknowledge là riêng lẻ từng message.
- Đoạn ví dụ xử lý lỗi bằng rollback rồi ném exception để caller biết lần xử lý thất bại. Đưa về retry có kiểm soát, giới hạn số lần và DLQ là phần **cấu hình broker/client theo sản phẩm**, không tự xảy ra với mọi bản cài đặt.

**Tính tương thích:** Ví dụ biên dịch với API **jakarta.jms** và provider Jakarta tương ứng. Dự án cũ dùng **javax.jms** cần client/API cùng hệ; không chỉ thay import rồi cho rằng hành vi và wire protocol sẽ tự tương thích. Trước khi triển khai, kiểm tra version broker, artifact client, acceptor/protocol và quyền truy cập đích.

## 9. Acknowledgment, redelivery, DLQ và transaction: hiểu đúng cam kết

| Tình huống | Rủi ro | Thiết kế khuyến nghị |
|---|---|---|
| Producer gửi message non-persistent, broker chết | Message có thể mất | Chọn persistent và kiểm chứng store/HA theo RPO yêu cầu |
| Consumer ack trước khi DB commit | DB lỗi nhưng message đã mất khỏi queue | Xử lý nghiệp vụ thành công rồi mới ack/commit JMS |
| DB commit xong, consumer chết trước JMS ack | Message được giao lại, dễ tạo tác dụng phụ trùng | Ghi dedup bằng eventId trong transaction nghiệp vụ; dùng idempotency key ngoài hệ thống khi cần |
| Message luôn gây lỗi (poison message) | Vòng retry vô hạn, backlog tăng | Delay/backoff, giới hạn redelivery, DLQ, cảnh báo và quy trình re-drive |
| Consumer rất chậm | Queue phình, đầy disk/memory hoặc ảnh hưởng luồng khác | Giám sát queue depth/age, flow control, prefetch/credit, scale worker và giới hạn tốc độ producer |
| Nhiều consumer cùng queue | Xử lý hoàn thành không theo thứ tự phát | Thiết kế công việc độc lập, khóa theo aggregate, chọn mô hình partition/ordering phù hợp |
| Topic subscriber offline | Có thể bỏ lỡ message | Tạo durable subscription đúng cách hoặc chọn event log nếu cần replay tùy ý |

**At-most-once, at-least-once, exactly-once** là những mô tả hành vi cần xác định theo **phạm vi**. Khi ack sớm, hệ thống có thể mất việc (gần at-most-once). Khi xử lý rồi mới ack và có redelivery, thường cần thiết kế theo **at-least-once**: có thể nhận trùng. Muốn tác dụng nghiệp vụ chỉ xảy ra một lần cần kết hợp idempotency, khóa duy nhất, transaction dữ liệu và đối soát các side effect bên ngoài. Không nên hứa “exactly-once end-to-end” chỉ nhờ bật một tùy chọn của broker.

**Delivery count** và cờ redelivered (ví dụ thuộc tính JMSXDeliveryCount khi provider hỗ trợ) hữu ích cho logging và phân tích lỗi. Giới hạn redelivery, delay và DLQ là chính sách triển khai: Classic và Artemis có **các cơ chế, phạm vi cài đặt và mặc định khác nhau**; hãy đọc tài liệu đúng dòng/phiên bản của broker trước khi cấu hình.

**Thứ tự xử lý** cũng không đồng nhất với thứ tự enqueue. Nhiều consumer, ưu tiên, redelivery, delayed delivery, transaction rollback và các quy tắc dispatch có thể làm thay đổi thứ tự kết quả nghiệp vụ. Nếu mọi thay đổi của một đơn hàng phải tuần tự, cần chiến lược serialization theo **orderId** hoặc thiết kế partitioning/consumer phù hợp; đừng chỉ dựa vào nhãn “FIFO”.

## 10. Đánh giá hệ thống trước khi chốt ActiveMQ

Dùng checklist này trong buổi thiết kế:

1. **Tương tác:** Caller có cần phản hồi ngay? Nếu có, phần nào nên ở HTTP và phần nào có thể chuyển nền?
2. **Phân phối:** Một worker duy nhất, một nhóm worker cạnh tranh, hay nhiều nhóm đều phải nhận? Queue, topic và durable subscription nào đáp ứng đúng?
3. **Lịch sử:** Message chỉ cần giữ đến khi xử lý xong hay consumer cần tua lại từ nhiều ngày trước? Nếu cần replay theo offset, đánh giá Kafka.
4. **Tích hợp:** Có hợp đồng JMS, Spring JMS, client Classic/Artemis, OpenWire hoặc AMQP cụ thể? Kiểm tra **phiên bản protocol** và khả năng tương thích thay vì chỉ tên giao thức.
5. **Độ tin cậy:** RPO/RTO mục tiêu, persistent store, HA, replication, DLQ, timeout, retry, dedup và giao dịch với DB đã được xác định chưa?
6. **Thông lượng:** Kích thước payload, tốc độ peak, queue backlog tối đa, độ tuổi message, thời gian xử lý, số consumer và giới hạn phần cứng là bao nhiêu?
7. **Vận hành và bảo mật:** Có đội quản trị broker, phân quyền, TLS, quản lý credential, backup, cảnh báo và quy trình xử lý DLQ không?

### Các chỉ số nên theo dõi

- **Queue depth** và **tuổi message lâu nhất**: chỉ số quan trọng hơn việc nhìn số message đơn thuần.
- **Enqueue/dequeue rate**, số consumer, tỷ lệ lỗi, redelivery và số message vào DLQ.
- **Disk/journal usage**, paging/flow control, kết nối, heap/GC và độ trễ publish/consume.
- **Consumer lag/offset** khi dùng Kafka; metrics phù hợp theo từng công nghệ.
- **Broker availability**, thời gian failover và tỷ lệ timeout phía ứng dụng.

Không gộp các khái niệm queue depth (ActiveMQ/RabbitMQ) và consumer lag (Kafka) thành cùng một định nghĩa; chúng phản ánh cơ chế lưu và tiêu thụ khác nhau.

### Bảo mật và triển khai

Broker là hạ tầng dữ liệu, không nên để cổng quản trị hoặc cổng message công khai trên Internet. Tối thiểu cần xác thực producer/consumer, phân quyền theo queue/topic/address, TLS cho kết nối cần bảo vệ, credential riêng theo ứng dụng, nguyên tắc quyền tối thiểu và ghi log truy cập/lỗi. Với dữ liệu nhạy cảm, cân nhắc mã hóa payload, giới hạn PII trong message và retention/DLQ phù hợp. Kiểm thử việc khởi động lại broker, failover và khôi phục journal/store bằng dữ liệu giả lập trước khi vận hành.

## 11. Bốn tình huống chọn nhanh

| Tình huống | Lựa chọn nên thử đầu tiên | Giải thích |
|---|---|---|
| Frontend cần biết ngay coupon hợp lệ và số tiền phải trả | HTTP | Có yêu cầu phản hồi đồng bộ rõ ràng |
| Ứng dụng Java dùng JMS, cần queue xử lý email/vận đơn bền vững | ActiveMQ Classic hoặc Artemis | Phù hợp mô hình JMS queue, transaction và redelivery |
| Hệ thống đa ngôn ngữ cần exchange với nhiều routing key và worker chuyên trách | RabbitMQ | Exchange/binding và hệ client AMQP 0-9-1 là lợi thế thường gặp |
| Data platform cần nhiều consumer group đọc lại sự kiện 7–30 ngày trước | Kafka | Log retention, partition và offset/replay là yêu cầu chính |

**Tình huống kết hợp:** một endpoint HTTP ghi đơn hàng và outbox; ActiveMQ phục vụ shipping/email; Kafka phục vụ phân tích và tái xây dựng dữ liệu. Không có mâu thuẫn khi dùng nhiều công nghệ, miễn là chi phí vận hành và đường đi dữ liệu được kiểm soát. Nhưng đừng bổ sung nhiều broker chỉ để “đúng xu hướng”.

## 12. Bài thực hành tư duy và kiểm thử lỗi

Giả sử message **shipping.create** có eventId **evt-123**, orderId **o-987**. Consumer nhận message, đã ghi thành công yêu cầu tạo vận đơn vào DB nhưng mất kết nối trước khi JMS commit.

**Câu hỏi 1:** Khi broker phát lại message, hệ thống phải làm gì?  
**Gợi ý:** Transaction xử lý kiểm tra **evt-123** đã xuất hiện trong bảng processed_events hay chưa. Nếu đã có, không tạo lại vận đơn; vẫn hoàn tất JMS commit để message không quay lại queue. Unique constraint trên eventId giúp ngăn hai worker chạy đồng thời tạo kết quả trùng.

**Câu hỏi 2:** Nếu message chứa orderId không tồn tại do lỗi dữ liệu thì xử lý ra sao?  
**Gợi ý:** Phân biệt lỗi tạm thời (DB tạm mất kết nối) và lỗi vĩnh viễn (schema sai hoặc ID bất hợp lệ). Dùng giới hạn redelivery và DLQ, lưu nguyên nhân, cảnh báo. Chỉ phát lại sau khi đã xác định và xử lý nguyên nhân.

**Câu hỏi 3:** Kiểm thử tối thiểu trước khi triển khai gồm gì?  
**Gợi ý:** Gửi persistent message rồi khởi động lại broker; dừng consumer giữa chừng; làm consumer chết sau DB commit trước JMS commit; gây poison message để xác nhận đường vào DLQ; tạo backlog và đo tốc độ xả; thử failover; thử user không có quyền publish/consume. Đối chiếu kết quả với yêu cầu RPO/RTO và số tác dụng nghiệp vụ thực sự tạo ra.

**Câu hỏi 4:** Nếu nhóm phân tích mới cần toàn bộ sự kiện của tháng trước, JMS topic đã đủ chưa?  
**Gợi ý:** Không được giả định topic là log lưu mọi message. Xác minh subscription/retention đã tồn tại từ trước; nếu bắt buộc replay lịch sử theo offset, Kafka hoặc một event store được thiết kế rõ ràng là phương án cần khảo sát.

## 13. Kết luận định hướng thiết kế

Dùng **HTTP** khi hợp đồng cần phản hồi ngay. Chọn **ActiveMQ Classic/Artemis** khi bài toán chính là xử lý bất đồng bộ bền vững, producer/consumer Java và tích hợp **JMS**; phân biệt hai broker trước khi chọn client, giao thức và chính sách vận hành. Cân nhắc **RabbitMQ** khi mô hình exchange/binding, routing và hệ sinh thái AMQP 0-9-1 phù hợp hơn. Cân nhắc **Kafka** khi cần event log, nhiều consumer group độc lập và replay theo offset.

Dù chọn công nghệ nào, bản thiết kế đáng tin cậy vẫn phải trả lời được: **khi producer, broker hoặc consumer chết ở từng thời điểm, dữ liệu còn ở đâu, ai sẽ thử lại, thông điệp có thể bị trùng không, và làm sao biết công việc đã hoàn tất?**
