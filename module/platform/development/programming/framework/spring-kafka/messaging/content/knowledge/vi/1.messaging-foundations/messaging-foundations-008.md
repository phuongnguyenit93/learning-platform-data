# Phạm vi trách nhiệm của Spring Kafka

## Mục tiêu của bài học

Trong chương **Nền tảng messaging**, bài này xác định Spring Kafka chịu trách nhiệm ở lớp nào trong một hệ thống dùng Apache Kafka, những khả năng mà thư viện cung cấp cho ứng dụng Spring và những phần vẫn thuộc về Kafka broker, nền tảng vận hành hoặc mã nghiệp vụ.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện bằng Spring Kafka, đặc biệt là KafkaTemplate và @KafkaListener. Khi học phần này, cần hiểu topic, partition, offset và consumer group; cách serialization; retry và dead-letter; transaction và exactly-once; xử lý đồng thời; cùng cách kiểm thử để vận hành luồng messaging đáng tin cậy.

Sau bài học, người học có thể:

- Đặt Spring Kafka đúng vị trí trong kiến trúc ứng dụng và phân biệt nó với Apache Kafka.
- Chỉ ra phần việc Spring Kafka hỗ trợ khi gửi, nhận, chuyển đổi và xử lý lỗi thông điệp.
- Giải thích ranh giới giữa API của Spring Kafka, Kafka client, Kafka broker và logic nghiệp vụ.
- Nhận diện những bảo đảm mà hệ thống phải thiết kế thêm, chẳng hạn tính idempotent của nghiệp vụ và phối hợp với cơ sở dữ liệu bên ngoài.

## 1. Spring Kafka nằm ở đâu trong kiến trúc?

Apache Kafka là nền tảng event streaming phân tán. Một cụm Kafka lưu trữ các bản ghi trong topic, chia topic thành partition, phân phối partition cho consumer thuộc các consumer group và quản lý offset. Producer và consumer giao tiếp với cụm Kafka thông qua Kafka client.

Spring Kafka là thư viện tích hợp Kafka vào hệ sinh thái Spring. Nó cung cấp API, cấu hình và cơ chế quản lý vòng đời để ứng dụng Spring sử dụng Kafka client thuận tiện hơn. Spring Kafka không thay thế Kafka broker và cũng không loại bỏ các khái niệm cốt lõi của Kafka.

Một luồng điển hình có thể hình dung như sau:

~~~mermaid
flowchart LR
    A["Mã nghiệp vụ Spring"] --> B["Spring Kafka"]
    B --> C["Apache Kafka Client"]
    C --> D["Kafka Broker Cluster"]
    D --> C
    C --> B
    B --> E["Listener / mã xử lý nghiệp vụ"]
~~~

Ở chiều gửi, mã nghiệp vụ gọi API Spring Kafka. Thư viện chuyển yêu cầu thành thao tác trên Kafka producer client; client thực hiện serialization và gửi bản ghi tới broker. Ở chiều nhận, Kafka consumer client lấy bản ghi từ broker; Spring Kafka điều phối việc poll, chuyển đổi thông điệp và gọi phương thức listener của ứng dụng.

Spring Boot có thể tự động cấu hình nhiều thành phần dựa trên các thuộc tính trong cấu hình ứng dụng và các bean hiện có. Đây là lớp tiện ích cấu hình của Spring Boot; phần tích hợp messaging cốt lõi vẫn do Spring Kafka cung cấp.

## 2. Những trách nhiệm chính của Spring Kafka

### 2.1. Tích hợp Kafka client với ứng dụng Spring

Spring Kafka kết nối các abstraction của Spring với producer, consumer và admin client của Apache Kafka. Ứng dụng có thể khai báo cấu hình qua properties, bean hoặc cấu hình Java, chẳng hạn:

- Địa chỉ bootstrap server và các thuộc tính kết nối.
- Serializer cho dữ liệu gửi và deserializer cho dữ liệu nhận.
- Consumer group, các thuộc tính consumer và cách quản lý offset.
- Các thiết lập bảo mật mà Kafka client hỗ trợ.
- Cấu hình transaction, timeout, retry ở client và các giới hạn liên quan.

Spring Kafka giúp cấu hình và sử dụng client theo cách phù hợp với container và dependency injection của Spring. Việc xác thực kết nối, phân quyền, cấu hình TLS/SASL và vận hành cụm Kafka vẫn cần được thiết kế phù hợp ở cả phía client lẫn hạ tầng.

### 2.2. Gửi bản ghi bằng KafkaTemplate

KafkaTemplate là abstraction chính để ứng dụng gửi bản ghi tới Kafka. Nó giúp mã nghiệp vụ không phải tự quản lý trực tiếp vòng đời KafkaProducer trong từng thao tác.

KafkaTemplate hỗ trợ các dạng gửi phổ biến:

- Gửi tới một topic, có thể kèm key và value.
- Gửi bản ghi có chỉ định partition hoặc timestamp khi nghiệp vụ cần.
- Gửi kèm header để truyền metadata.
- Nhận kết quả bất đồng bộ để biết thao tác gửi thành công hay thất bại.
- Tham gia transaction Kafka khi producer được cấu hình và quản lý transaction phù hợp.

Ví dụ, một dịch vụ đơn hàng phát sự kiện khi đơn hàng được tạo:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );
    }
}
~~~

Trong ví dụ, topic là nơi lưu sự kiện; orderId là key để Kafka partitioner xác định partition theo cấu hình mặc định hoặc partitioner được chọn. Dùng cùng key thường giúp các sự kiện liên quan đến một thực thể đi vào cùng partition, nhờ đó có thể duy trì thứ tự trong phạm vi partition đó.

Lời gọi send chỉ khởi tạo thao tác gửi bất đồng bộ. Nếu nghiệp vụ cần phản ứng với kết quả gửi, ứng dụng phải quan sát future/callback và xử lý lỗi tương ứng. Không nên xem việc gọi send mà không kiểm tra kết quả là bằng chứng rằng sự kiện đã được broker ghi nhận.

### 2.3. Nhận và điều phối xử lý bằng @KafkaListener

Spring Kafka cung cấp @KafkaListener để đánh dấu phương thức nhận bản ghi. Listener container đứng phía sau annotation này: container tạo và quản lý Kafka consumer, thực hiện poll, điều phối bản ghi tới listener và quản lý việc commit offset theo cấu hình.

~~~java
@Service
public class OrderEventListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "billing-service"
    )
    public void handle(OrderCreated event) {
        // Kiểm tra và xử lý sự kiện theo nghiệp vụ billing.
    }
}
~~~

Ứng dụng có thể cấu hình listener để nhận một bản ghi mỗi lần hoặc nhận theo batch. Listener container cũng cung cấp các thiết lập về concurrency, acknowledgment, error handler, pause/resume và vòng đời container.

Một số ranh giới quan trọng:

- @KafkaListener là điểm nối giữa Kafka consumer và phương thức Java; nó không biến xử lý thông điệp thành một giao dịch nghiệp vụ tự động.
- Listener container điều phối poll và offset; cách commit phụ thuộc acknowledgment mode, cấu hình container và cách listener xử lý.
- Consumer group và partition vẫn tuân theo mô hình phân phối của Kafka. Tăng concurrency không thể tạo thêm mức song song hữu ích vượt quá số partition được gán cho consumer trong group.
- Thứ tự bản ghi được bảo đảm trong phạm vi một partition, không phải trên toàn bộ topic hoặc giữa các topic.

### 2.4. Quản lý topic ở phía ứng dụng

Spring Kafka cung cấp KafkaAdmin để ứng dụng khai báo hoặc yêu cầu tạo các topic cần thiết, thường thông qua bean NewTopic. Cơ chế này hữu ích khi khởi tạo môi trường hoặc quản lý topic gắn với vòng đời ứng dụng.

Tuy vậy, KafkaAdmin không thay thế trách nhiệm quản trị nền tảng. Các quyết định về số partition, replication factor, retention, quota, phân quyền, dung lượng lưu trữ và chính sách vận hành cần được thống nhất với đội ngũ quản lý cụm Kafka. Khả năng tạo topic cũng phụ thuộc quyền của principal kết nối và cấu hình broker.

### 2.5. Chuyển đổi dữ liệu và metadata

Kafka lưu trữ key và value dưới dạng byte. Spring Kafka kết hợp serializer/deserializer của Kafka với message converter để ánh xạ dữ liệu giữa byte, đối tượng Java và abstraction Message của Spring.

Các thành phần này giúp ứng dụng:

- Gửi và nhận object Java thay vì tự chuyển đổi byte trong từng phương thức.
- Sử dụng header để truyền metadata như correlation id, loại sự kiện hoặc thông tin phục vụ tracing.
- Ánh xạ header Kafka sang message header của Spring và ngược lại.
- Chọn kiểu dữ liệu, converter và serializer phù hợp với hợp đồng sự kiện.

Serializer và deserializer ở hai phía phải tương thích. Với JSON hoặc định dạng có schema, nhóm phát triển cần xác định rõ cấu trúc dữ liệu, quy tắc tương thích ngược/tiến và cách xử lý phiên bản. Spring Kafka hỗ trợ việc chuyển đổi, nhưng không tự quyết định hợp đồng dữ liệu của tổ chức.

### 2.6. Xử lý lỗi, retry và dead-letter

Trong thực tế, listener có thể thất bại do dữ liệu không hợp lệ, dịch vụ phụ thuộc tạm thời không sẵn sàng, timeout hoặc lỗi lập trình. Spring Kafka cung cấp cơ chế error handler và recovery để ứng dụng định nghĩa cách xử lý những tình huống này.

Các lựa chọn thường gặp gồm:

- Retry có backoff đối với lỗi có khả năng tự hồi phục.
- Phân loại exception để quyết định lỗi nào được retry và lỗi nào cần chuyển sang recovery.
- DeadLetterPublishingRecoverer để publish bản ghi không xử lý được tới dead-letter topic (DLT).
- Cơ chế retry topic, chẳng hạn @RetryableTopic, cho những trường hợp muốn trì hoãn việc thử lại bằng các topic riêng.

Retry phải có giới hạn và chính sách rõ ràng. Retry vô hạn có thể làm consumer liên tục mắc kẹt ở một bản ghi, tăng tải lên hệ thống phụ thuộc hoặc kéo dài thời gian xử lý. Khi chuyển bản ghi sang DLT, cần lưu đủ thông tin để truy vết nguyên nhân, xác định cách sửa dữ liệu và quyết định phát lại.

Retry topic có thể làm thay đổi thứ tự quan sát được giữa các sự kiện liên quan vì bản ghi lỗi được xử lý lại ở topic khác trong một thời điểm khác. Nếu thứ tự là yêu cầu nghiệp vụ, cần đánh giá kỹ chiến lược retry và cách phân vùng dữ liệu.

### 2.7. Transaction và exactly-once trong phạm vi Kafka

Spring Kafka tích hợp transaction của Kafka để ứng dụng có thể gửi nhiều bản ghi như một đơn vị nguyên tử và xây dựng luồng consume-transform-produce có thể phối hợp việc ghi kết quả với offset đầu vào. Tùy cấu hình, consumer có thể chỉ đọc các bản ghi đã commit bằng isolation level phù hợp.

Đây là nền tảng cho các kịch bản exactly-once semantics trong phạm vi Kafka. Tuy nhiên, khái niệm này có ranh giới cụ thể:

- Nó không tự biến một lệnh gọi HTTP hoặc thao tác ghi vào cơ sở dữ liệu quan hệ thành một phần của Kafka transaction.
- Nó không tự loại bỏ mọi tác dụng phụ bị lặp trong logic nghiệp vụ.
- Nó đòi hỏi cấu hình producer/consumer, transaction manager và cách xử lý offset phù hợp.
- Ứng dụng vẫn phải thiết kế phục hồi khi tiến trình dừng giữa các bước hoặc khi hệ thống phụ thuộc gặp lỗi.

Với luồng cần phối hợp Kafka và database, có thể cân nhắc Outbox Pattern, Inbox Pattern hoặc xử lý idempotent tùy yêu cầu nhất quán. Không nên tuyên bố hệ thống đạt exactly-once end-to-end chỉ vì đã bật transaction trong Spring Kafka.

### 2.8. Xử lý đồng thời và điều khiển listener

Spring Kafka cho phép cấu hình concurrency cho listener container để xử lý nhiều partition song song. Nó cũng cung cấp các cơ chế quản lý container, pause/resume và batch listener để phù hợp với tải thực tế.

Mức song song hữu ích bị giới hạn bởi số partition được gán cho consumer trong một group. Nếu một topic có ít partition, tăng số consumer hoặc concurrency có thể không làm tăng thông lượng. Nếu xử lý một partition quá chậm, partition đó vẫn có thể trở thành điểm nghẽn.

Việc chọn concurrency cần xét tới:

- Số partition và cách key phân phối bản ghi.
- Thời gian xử lý trung bình và độ biến động của listener.
- Khả năng chịu tải của database và dịch vụ phụ thuộc.
- Giới hạn tài nguyên của ứng dụng, số kết nối và kích thước batch.
- Thời gian poll, heartbeat, rebalance và yêu cầu xử lý theo thứ tự.

Spring Kafka cung cấp công cụ điều phối; ứng dụng và đội vận hành phải chọn cấu hình phù hợp với tải, tài nguyên và yêu cầu nghiệp vụ.

### 2.9. Kiểm thử và quan sát hoạt động

Spring Kafka có các tiện ích kiểm thử để kiểm tra producer, listener và luồng tích hợp với Kafka. Có thể dùng EmbeddedKafka trong các bài kiểm thử cần broker nhúng, hoặc dùng môi trường Kafka riêng như Testcontainers khi muốn kiểm tra gần với cách triển khai thực tế hơn.

Trong vận hành, cần quan sát cả ứng dụng lẫn cụm Kafka. Những tín hiệu hữu ích gồm:

- Tốc độ gửi/nhận và tỷ lệ lỗi.
- Consumer lag theo group và partition.
- Thời gian xử lý của listener.
- Số lần retry, số bản ghi vào DLT và tuổi của bản ghi chờ xử lý.
- Số lần rebalance, trạng thái consumer và lỗi kết nối.
- Tình trạng transaction, timeout và lỗi serialization/deserialization.

Spring Kafka tích hợp với hệ sinh thái quan sát của Spring và các metric từ Kafka client. Tuy nhiên, việc đặt ngưỡng cảnh báo, lưu trữ metric, dựng dashboard và xây dựng quy trình phản ứng sự cố vẫn là công việc vận hành của hệ thống.

## 3. Ranh giới trách nhiệm giữa các lớp

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| Ứng dụng nghiệp vụ | Quyết định sự kiện nào cần phát, nội dung có hợp lệ không và phải làm gì khi nhận sự kiện | Tạo OrderCreated, kiểm tra quyền, cập nhật trạng thái đơn hàng |
| Spring Kafka | Cung cấp API Spring, cấu hình và điều phối producer/consumer/listener, chuyển đổi message, xử lý lỗi và tích hợp transaction | KafkaTemplate, @KafkaListener, listener container, KafkaAdmin |
| Apache Kafka client | Thực hiện giao thức giao tiếp với broker và các thao tác producer/consumer/admin | Partition assignment, poll, gửi bản ghi, serializer/deserializer |
| Kafka broker cluster | Lưu trữ bản ghi, quản lý topic/partition, replication, leader và offset theo cơ chế Kafka | Retention, replication factor, ISR, log |
| Nền tảng vận hành | Cung cấp và bảo vệ cụm, quản lý dung lượng, quyền truy cập, giám sát và khôi phục | TLS/SASL, ACL, quota, backup/DR, cảnh báo |
| Hợp đồng sự kiện và dữ liệu | Quy định cấu trúc, ý nghĩa và quy tắc tương thích của event | Schema versioning, compatibility, quy ước tên event |

Bảng này giúp tránh hai nhầm lẫn phổ biến. Thứ nhất, sử dụng Spring Kafka không có nghĩa là ứng dụng không cần hiểu topic, partition, offset và consumer group. Thứ hai, Spring Kafka cung cấp cơ chế kỹ thuật để gửi và nhận bản ghi, nhưng không thể tự quyết định một sự kiện có đúng về mặt nghiệp vụ hay một thao tác có an toàn khi được thực hiện lại hay không.

## 4. Theo dấu một sự kiện qua Spring Kafka

Giả sử dịch vụ Order phát sự kiện OrderCreated và dịch vụ Billing nhận sự kiện đó.

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant S as Spring Kafka
    participant P as Kafka Producer
    participant K as Kafka Broker
    participant C as Kafka Consumer
    participant B as Billing Listener

    O->>S: KafkaTemplate.send(topic, key, event)
    S->>P: Gửi bản ghi
    P->>K: Serialize và publish
    K-->>P: Kết quả gửi
    P-->>S: Send result
    K-->>C: Bản ghi thuộc partition được gán
    C->>S: Poll bản ghi
    S->>B: Chuyển đổi và gọi @KafkaListener
    B->>B: Xử lý nghiệp vụ
    S->>C: Quản lý acknowledgment/offset theo cấu hình
~~~

Ở chiều producer, key ảnh hưởng tới partition được chọn. Kết quả gửi cho biết thao tác publish có thành công theo phản hồi của Kafka client hay không. Nếu ứng dụng cần bảo đảm rằng trạng thái nghiệp vụ chỉ được xác nhận sau khi sự kiện được gửi, nó phải thiết kế trình tự cập nhật và phát sự kiện phù hợp, chẳng hạn dùng Outbox Pattern khi có database tham gia.

Ở chiều consumer, listener container poll bản ghi rồi gọi phương thức được đánh dấu @KafkaListener. Offset cho biết vị trí đọc của consumer trong partition. Thời điểm commit offset cần phù hợp với thời điểm hoàn tất xử lý: commit quá sớm có thể khiến bản ghi bị bỏ qua sau sự cố; commit muộn có thể khiến bản ghi được giao lại và nghiệp vụ phải chịu được việc xử lý lặp.

Ví dụ này cho thấy Spring Kafka chịu trách nhiệm điều phối kỹ thuật quanh luồng messaging. Kết quả cuối cùng vẫn phụ thuộc vào cấu hình Kafka, cách container quản lý offset và tính đúng đắn của mã nghiệp vụ.

## 5. Những việc ứng dụng vẫn phải tự thiết kế

Khi xây dựng hệ thống bằng Spring Kafka, nhóm phát triển vẫn cần đưa ra các quyết định sau:

1. **Thiết kế event:** xác định event phản ánh sự kiện nghiệp vụ đã xảy ra, có tên và payload ổn định, tránh gửi một object nội bộ chứa quá nhiều chi tiết triển khai.
2. **Chọn key và partition:** chọn key theo thực thể cần giữ thứ tự; xác định số partition dựa trên thông lượng, mức song song và khả năng mở rộng.
3. **Quản lý schema:** thống nhất kiểu dữ liệu, versioning và quy tắc tương thích giữa producer với consumer.
4. **Thiết kế idempotency:** xử lý an toàn khi cùng một event được giao lại, ví dụ lưu event id đã xử lý hoặc dùng khóa duy nhất ở database.
5. **Chọn chính sách retry:** phân biệt lỗi tạm thời với lỗi dữ liệu, đặt giới hạn retry, backoff và quy trình xử lý DLT.
6. **Quyết định offset:** chọn acknowledgment/commit strategy phù hợp với tác dụng phụ của listener và yêu cầu mất hoặc lặp thông điệp.
7. **Phối hợp hệ thống ngoài Kafka:** dùng transaction hoặc pattern tích hợp phù hợp khi một luồng phải ghi database, gọi API hoặc phát event.
8. **Vận hành và bảo mật:** chuẩn bị quyền truy cập, mã hóa kết nối, giám sát consumer lag, cảnh báo DLT và quy trình khôi phục.

## 6. Cách chọn đúng abstraction

| Nhu cầu | Thành phần Spring Kafka thường dùng |
|---|---|
| Gửi một event từ mã nghiệp vụ | KafkaTemplate |
| Khai báo phương thức nhận event | @KafkaListener |
| Tùy chỉnh vòng đời, concurrency, acknowledgment và batch | ConcurrentKafkaListenerContainerFactory / listener container |
| Khai báo topic cần tạo từ ứng dụng | KafkaAdmin và NewTopic |
| Chuyển đổi object, key, value và header | Serializer, deserializer và message converter |
| Xử lý lỗi, retry và chuyển bản ghi sang DLT | Error handler, recoverer và retry-topic support |
| Gửi/nhận trong transaction Kafka | Transactional producer và Kafka transaction manager |
| Kiểm thử luồng messaging | Spring Kafka testing utilities, EmbeddedKafka hoặc Kafka trong Testcontainers |

Nên bắt đầu từ abstraction đơn giản nhất đáp ứng nhu cầu. KafkaTemplate phù hợp với thao tác gửi tường minh trong service; @KafkaListener phù hợp với consumer có vòng đời được Spring quản lý. Chỉ tùy chỉnh container, retry, transaction hoặc batch khi yêu cầu về thông lượng, thứ tự, độ tin cậy và khả năng phục hồi đã rõ.

## 7. Các hiểu lầm cần tránh

- **“Spring Kafka là Kafka broker.”** Sai. Spring Kafka là thư viện tích hợp phía ứng dụng; dữ liệu được lưu và phân phối bởi Kafka cluster.
- **“Dùng @KafkaListener là tự động xử lý đúng một lần.”** Sai. Việc giao lại bản ghi, commit offset và tác dụng phụ nghiệp vụ vẫn cần được thiết kế.
- **“Tăng concurrency luôn tăng throughput.”** Sai. Số partition được gán, tải của hệ thống phụ thuộc và thời gian xử lý giới hạn mức song song.
- **“Retry giải quyết được mọi lỗi.”** Sai. Lỗi dữ liệu hoặc lỗi logic có thể không bao giờ tự hết; cần phân loại lỗi và có DLT/recovery.
- **“Kafka transaction bao gồm cả database và HTTP.”** Sai. Kafka transaction có phạm vi trong Kafka; hệ thống ngoài cần cơ chế phối hợp riêng.
- **“Có serializer JSON là đã có schema governance.”** Sai. Chuyển đổi JSON không tự định nghĩa versioning hay bảo đảm producer và consumer tương thích.

## 8. Checklist đánh giá phạm vi trách nhiệm

Trước khi đưa một luồng messaging vào vận hành, hãy kiểm tra:

- [ ] Ứng dụng xác định rõ event, topic, key và consumer group.
- [ ] Producer và consumer dùng cấu hình serialization/deserialization tương thích.
- [ ] Kết quả gửi được theo dõi nếu nghiệp vụ phụ thuộc vào việc publish thành công.
- [ ] Listener có chiến lược acknowledgment/commit phù hợp với xử lý nghiệp vụ.
- [ ] Consumer chịu được việc nhận lại cùng một event.
- [ ] Retry có giới hạn, backoff và cách phân loại exception.
- [ ] DLT có người hoặc quy trình chịu trách nhiệm kiểm tra và xử lý lại.
- [ ] Concurrency phù hợp với số partition và năng lực hệ thống phụ thuộc.
- [ ] Transaction được cấu hình đúng phạm vi; không nhầm với bảo đảm end-to-end.
- [ ] Có metric, log, tracing và cảnh báo cho lỗi xử lý cũng như consumer lag.
- [ ] Topic, quyền truy cập, retention và tài nguyên cụm được quản trị phù hợp.

## Kết luận

Spring Kafka đảm nhiệm lớp tích hợp giữa ứng dụng Spring và Apache Kafka: cung cấp API gửi/nhận, quản lý listener container, chuyển đổi message, hỗ trợ quản lý topic, xử lý lỗi, retry, transaction, concurrency, kiểm thử và quan sát hoạt động. Kafka vẫn chịu trách nhiệm về lưu trữ và phân phối bản ghi theo topic, partition, offset và consumer group. Ứng dụng vẫn chịu trách nhiệm về ý nghĩa event, tính đúng đắn nghiệp vụ, idempotency và phối hợp với các hệ thống bên ngoài.

Hiểu đúng ranh giới này là nền tảng để sử dụng KafkaTemplate và @KafkaListener hiệu quả, đồng thời thiết kế được luồng messaging có thể mở rộng, phục hồi và vận hành tin cậy.
