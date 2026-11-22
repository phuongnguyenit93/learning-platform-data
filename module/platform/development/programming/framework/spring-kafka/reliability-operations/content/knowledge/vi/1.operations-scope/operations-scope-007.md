# Khi nào dùng Spring Kafka thay cho client thuần

Spring Kafka phù hợp khi một ứng dụng Java dùng Spring cần gửi và nhận message Kafka theo các mô hình phổ biến, đồng thời muốn tích hợp việc tiêu thụ message vào vòng đời, cấu hình và cơ chế vận hành của Spring. Client Kafka thuần phù hợp khi chương trình cần kiểm soát trực tiếp producer hoặc consumer, cần ít phụ thuộc, hoặc không sử dụng Spring.

Hai lựa chọn này dùng cùng Kafka Java Client ở tầng giao tiếp với broker. Spring Kafka cung cấp một lớp tích hợp và các abstraction ở phía trên client đó. Vì vậy, chọn Spring Kafka chủ yếu là quyết định về mức abstraction, cách tổ chức ứng dụng và chi phí vận hành mã nguồn; bản thân việc dùng Spring Kafka không tự động làm hệ thống đáng tin cậy hơn.

## 1. Phân biệt hai lựa chọn

### Kafka client thuần

Kafka client thuần là các API Java trực tiếp như `KafkaProducer`, `KafkaConsumer` và `AdminClient` trong thư viện `kafka-clients`.

Với producer, ứng dụng tự tạo cấu hình, tạo `ProducerRecord`, gửi record và xử lý kết quả gửi. Với consumer, ứng dụng tự quản lý vòng lặp `poll()`, subscription hoặc partition assignment, xử lý record, commit offset, rebalance và đóng consumer khi dừng chương trình.

Đây là lựa chọn có mức kiểm soát thấp tầng cao. Đổi lại, ứng dụng phải tự xây dựng và duy trì nhiều phần mã vận hành.

### Spring for Apache Kafka (Spring Kafka)

Spring Kafka cung cấp các thành phần tích hợp với Spring, trong đó thường gặp nhất là:

- `KafkaTemplate` để gửi message.
- Listener container và `@KafkaListener` để nhận message.
- Cơ chế quản lý vòng đời consumer, concurrency, acknowledgement và commit offset.
- Cấu hình xử lý lỗi, retry, dead-letter topic (DLT) và transaction.
- Các điểm tích hợp với dependency injection, cấu hình ứng dụng, logging, metrics, tracing và kiểm thử của hệ sinh thái Spring.

Spring Boot có thể tự động cấu hình nhiều thành phần từ các thuộc tính `spring.kafka.*`. Ứng dụng vẫn cần quyết định các thuộc tính quan trọng như bootstrap servers, serializer/deserializer, consumer group, acknowledgement, retry và transaction.

### Bảng so sánh nhanh

| Khía cạnh | Spring Kafka | Kafka client thuần |
|---|---|---|
| Gửi message | Dùng `KafkaTemplate` và cấu hình Spring | Gọi trực tiếp `KafkaProducer.send()` |
| Nhận message | Listener container, thường khai báo bằng `@KafkaListener` | Tự viết vòng lặp `poll()` |
| Offset và acknowledgement | Container quản lý theo AckMode; có thể cấu hình manual ack | Tự quyết định thời điểm và cách commit |
| Xử lý lỗi | Có error handler, backoff, DLT và retry topic tích hợp | Tự thiết kế retry, pause/resume, DLT và commit |
| Vòng đời | Tích hợp vòng đời bean và ứng dụng Spring | Tự khởi tạo, đóng và phối hợp vòng đời |
| Cấu hình | Bean, properties và Spring Boot auto-configuration | `Properties` hoặc cấu hình riêng của ứng dụng |
| Kiểm thử | Có tiện ích kiểm thử Spring Kafka và tích hợp Spring Test | Tự dựng producer/consumer và môi trường test |
| Mức kiểm soát | Cao ở các use case phổ biến; có thể truy cập API thấp tầng khi cần | Trực tiếp và chi tiết nhất |
| Phụ thuộc | Cần hệ sinh thái Spring Kafka/Spring | Chỉ cần Kafka client và các thư viện ứng dụng cần |
| Công sức vận hành mã | Thường ít mã hạ tầng hơn trong ứng dụng Spring | Nhiều trách nhiệm vòng đời và xử lý lỗi nằm trong mã ứng dụng |

## 2. Khi nào nên chọn Spring Kafka?

### 2.1. Ứng dụng đã chạy trên Spring hoặc Spring Boot

Đây thường là lý do rõ ràng nhất. Nếu ứng dụng đã dùng Spring, Spring Kafka giúp cấu hình Kafka theo cùng cách ứng dụng quản lý database, HTTP client, service và các thành phần khác.

Ví dụ, một dịch vụ thanh toán nhận sự kiện đơn hàng có thể khai báo listener thành một bean. Spring quản lý listener container cùng vòng đời ứng dụng; các dependency nghiệp vụ được inject trực tiếp vào listener. Nhóm phát triển không phải tự viết một thread chạy `poll()`, tự xử lý shutdown và tự phối hợp việc khởi động consumer với ứng dụng.

Spring Kafka đặc biệt phù hợp khi nhiều service trong cùng hệ thống cần tuân theo một cách cấu hình và vận hành Kafka thống nhất.

### 2.2. Luồng gửi và nhận message theo mô hình phổ biến

Các ứng dụng thường có những nhu cầu như:

- Gửi event sau khi một nghiệp vụ hoàn tất.
- Nhận event theo consumer group.
- Xử lý từng record hoặc một batch record.
- Điều chỉnh số listener thread theo số partition và năng lực xử lý.
- Chuyển message lỗi sang retry hoặc DLT.
- Theo dõi lỗi và trạng thái listener trong quá trình vận hành.

Spring Kafka đã có abstraction cho những công việc này. Nhóm phát triển có thể tập trung vào logic nghiệp vụ và chính sách vận hành thay vì tự duy trì một framework consumer riêng.

### 2.3. Cần cơ chế acknowledgement và commit có cấu hình rõ ràng

Với consumer, thời điểm commit offset quyết định khả năng xử lý lại message sau sự cố. Spring Kafka cung cấp các AckMode để xác định container commit offset theo từng record, theo batch, theo chu kỳ hoặc theo acknowledgement tường minh.

Ví dụ, listener có thể chỉ acknowledge sau khi xử lý nghiệp vụ thành công. Cách làm này hỗ trợ mô hình at-least-once: nếu ứng dụng gặp sự cố trước khi commit, record có thể được giao lại. Do đó, handler vẫn cần idempotent để tránh tạo tác dụng phụ trùng lặp.

Spring Kafka giúp tổ chức acknowledgement và commit nhất quán hơn, nhưng người thiết kế vẫn phải chọn đúng AckMode và xác định rõ ranh giới giữa xử lý thành công và commit.

### 2.4. Cần retry, backoff và dead-letter topic

Một message có thể thất bại vì lỗi tạm thời như dịch vụ phụ thuộc bị gián đoạn, hoặc lỗi không thể tự phục hồi như payload sai schema. Hai loại lỗi này cần chính sách khác nhau.

Spring Kafka cung cấp các cơ chế như error handler, backoff, `DeadLetterPublishingRecoverer` và retry topic. Tùy mô hình, ứng dụng có thể:

- Retry một số lần với khoảng chờ tăng dần đối với lỗi tạm thời.
- Chuyển message không thể xử lý sang DLT để điều tra và xử lý lại.
- Ghi log, metric và thông tin lỗi để hỗ trợ vận hành.
- Phân loại exception để quyết định lỗi nào được retry và lỗi nào được chuyển thẳng sang recoverer.

Các cơ chế này giúp giảm mã tự viết và làm chính sách lỗi dễ nhìn thấy hơn. Chúng không thay thế việc xác định số lần retry, thời gian chờ, giới hạn lưu trữ, quyền truy cập DLT, quy trình replay và cách xử lý message độc hại hoặc không hợp lệ.

Cần cân nhắc thứ tự message khi dùng retry topic. Khi message được đưa sang topic retry riêng, các message phía sau trong partition gốc có thể tiếp tục được xử lý trước message đang retry. Nếu thứ tự theo aggregate hoặc theo key là yêu cầu nghiệp vụ, hãy chọn chiến lược retry và partitioning phù hợp, đồng thời kiểm thử hành vi thứ tự thực tế.

### 2.5. Cần tích hợp transaction trong luồng Kafka

Spring Kafka hỗ trợ cấu hình Kafka transaction và phối hợp transaction với listener container. Điều này hữu ích cho luồng đọc message, xử lý rồi ghi một hoặc nhiều message Kafka khác, khi cần bảo đảm các thao tác ghi Kafka nằm trong cùng một transaction.

Tuy nhiên, transaction Kafka không tự tạo transaction nguyên tử giữa Kafka và một database bên ngoài. Nếu listener cập nhật database rồi commit offset Kafka, sự cố giữa hai thao tác vẫn có thể tạo trạng thái không nhất quán. Với luồng có database, hãy xem xét outbox/inbox, idempotency key hoặc một thiết kế phối hợp phù hợp.

### 2.6. Muốn chuẩn hóa khả năng quan sát và kiểm thử

Trong ứng dụng Spring, listener và producer có thể được tích hợp với cấu hình logging, metrics, tracing và cơ chế kiểm thử đang dùng. Spring Kafka cũng cung cấp các tiện ích trong module kiểm thử để tạo broker test hoặc kiểm thử listener với môi trường Kafka phù hợp.

Điều này hữu ích khi nhiều nhóm cùng vận hành nhiều consumer: cấu hình, cách đặt tên listener, xử lý exception và cách đo độ trễ có thể được chuẩn hóa ở cấp ứng dụng.

## 3. Khi nào nên dùng Kafka client thuần?

### 3.1. Chương trình không sử dụng Spring

Nếu ứng dụng là một công cụ dòng lệnh, một tiến trình Java nhỏ, một thư viện dùng lại trong nhiều framework hoặc một dịch vụ không dùng Spring, thêm Spring Kafka có thể làm tăng số phụ thuộc và cấu hình mà ứng dụng không cần.

Dùng trực tiếp Kafka client giúp chương trình giữ kiến trúc đơn giản và không buộc người dùng thư viện phải đưa Spring vào ứng dụng của họ.

### 3.2. Cần kiểm soát chi tiết vòng đời consumer

Consumer thuần phù hợp khi thuật toán cần điều khiển trực tiếp các thao tác như:

- Gán partition thủ công thay vì dùng subscription theo consumer group.
- Phản ứng với rebalance theo logic riêng.
- Pause/resume một số partition theo trạng thái hệ thống.
- Điều chỉnh poll, xử lý và commit theo một state machine riêng.
- Điều phối nhiều nguồn dữ liệu hoặc nhiều consumer với một vòng lặp tùy biến.
- Quản lý offset hoặc quy trình khôi phục theo yêu cầu đặc thù.

Spring Kafka có nhiều hook và API mở rộng, nên không phải cứ dùng Spring là mất quyền kiểm soát. Tuy vậy, nếu phần lớn thiết kế phải né listener container hoặc can thiệp sâu vào vòng đời consumer, client thuần có thể làm ý đồ kiến trúc rõ ràng hơn.

### 3.3. Cần thư viện độc lập với framework

Một thư viện tích hợp Kafka có thể được dùng bởi ứng dụng Spring, ứng dụng Jakarta EE, chương trình Java độc lập hoặc một hệ thống khác. Nếu thư viện chỉ cần tạo producer hoặc consumer theo một interface riêng, phụ thuộc trực tiếp vào Kafka client thường giúp API công khai gọn và dễ tích hợp hơn.

Trong trường hợp này, không nên buộc người dùng thư viện phải khởi tạo Spring ApplicationContext chỉ để gửi hoặc đọc một record.

### 3.4. Có yêu cầu đặc biệt về tài nguyên hoặc độ trễ

Client thuần có thể giúp giảm phần overhead của Spring context, listener container và các lớp tích hợp. Nó cũng cho phép kiểm soát chi tiết hơn việc cấp phát thread, batch, poll và xử lý record.

Tuy nhiên, Spring Kafka vẫn sử dụng Kafka Java client ở bên dưới. Không nên kết luận client thuần luôn nhanh hơn hoặc có throughput cao hơn chỉ vì ít abstraction hơn. Nếu hiệu năng là lý do quyết định, hãy benchmark trên workload thực tế, cùng cấu hình producer/consumer, số partition, payload, mức xác nhận ghi, độ trễ xử lý và cách commit. Đo cả CPU, heap, GC, p95/p99 latency và throughput trước khi chọn.

### 3.5. Consumer có thuật toán xử lý chuyên biệt

Một số consumer được thiết kế như một tiến trình điều phối chuyên dụng: việc poll, xử lý, checkpoint, pause/resume và phục hồi partition là một phần cốt lõi của thuật toán. Khi đó, vòng lặp consumer thuần có thể biểu đạt rõ ràng hơn toàn bộ trạng thái và thứ tự thao tác.

Đây là lựa chọn hợp lý khi nhóm phát triển thực sự cần các khả năng thấp tầng và sẵn sàng sở hữu mã xử lý rebalance, commit, shutdown, retry, metrics và giám sát.

## 4. Ma trận quyết định theo tình huống

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Spring Boot service gửi event bằng một producer thông thường | Spring Kafka | `KafkaTemplate` tích hợp cấu hình và vòng đời Spring |
| Spring Boot service nhận event bằng consumer group | Spring Kafka | Listener container quản lý poll, concurrency và commit |
| Cần retry, DLT và error handler theo chính sách chung | Spring Kafka | Có abstraction và cơ chế tích hợp sẵn |
| Cần Kafka transaction cho luồng đọc rồi ghi Kafka | Spring Kafka thường thuận tiện | Tích hợp transaction với template và listener container |
| Java CLI chạy theo lịch, không có Spring | Client thuần | Ít phụ thuộc, vòng đời nhỏ |
| Thư viện Kafka phải độc lập framework | Client thuần | Không ép consumer của thư viện dùng Spring |
| Cần tự điều phối partition, rebalance và poll loop | Client thuần hoặc Spring Kafka với custom integration | Quyết định dựa trên mức độ can thiệp cần thiết |
| Cần tối ưu hiệu năng nhưng chưa có số đo | Chưa quyết định | Benchmark cả hai với cùng workload |
| Ứng dụng Spring nhưng một consumer có yêu cầu điều khiển đặc thù | Đánh giá từng consumer | Có thể dùng Spring Kafka cho luồng chuẩn và client thuần cho phần thực sự cần kiểm soát thấp tầng |

Có thể dùng cả hai trong cùng một hệ thống nếu mỗi thành phần có ranh giới rõ ràng. Ví dụ, phần lớn service dùng Spring Kafka, còn một tiến trình chuyên dụng dùng Kafka client thuần. Tránh để hai thành phần cùng sở hữu một consumer hoặc cùng điều khiển một luồng offset mà không có thiết kế phối hợp rõ ràng.

## 5. Ví dụ triển khai cùng một use case

Giả sử service Billing cần nhận sự kiện `orders.created` để tạo thông tin thanh toán. Payload đã có serializer/deserializer JSON được cấu hình thống nhất.

### 5.1. Dùng Spring Kafka

Producer có thể dùng `KafkaTemplate`:

```java
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
```

Consumer có thể khai báo bằng annotation:

```java
@Component
public class BillingOrderListener {

    private final BillingService billingService;

    public BillingOrderListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "billing-service"
    )
    public void onOrderCreated(OrderCreated event) {
        billingService.createPendingPayment(event);
    }
}
```

Ví dụ trên giả định ứng dụng đã cấu hình serializer/deserializer tương ứng và listener container được cấu hình với chính sách acknowledgement, error handling phù hợp. Trong production, producer phải theo dõi kết quả gửi bất đồng bộ và xử lý lỗi gửi; không nên xem việc gọi `send()` là bằng chứng message đã được broker xác nhận.

Nếu dùng manual acknowledgement, listener phải được cấu hình AckMode tương ứng. Ví dụ sau chỉ minh họa ranh giới acknowledgement:

```java
@KafkaListener(topics = "orders.created", groupId = "billing-service")
public void onOrderCreated(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {

    billingService.createPendingPayment(record.value());
    acknowledgment.acknowledge();
}
```

Chỉ acknowledge sau khi thao tác nghiệp vụ đã thành công. Nếu phương thức nghiệp vụ ghi database, hãy bảo đảm thao tác đó an toàn khi được gọi lại, vì record có thể được giao lại nếu ứng dụng dừng trước khi offset được commit.

### 5.2. Dùng Kafka client thuần

Với client thuần, chương trình phải tự quản lý consumer loop:

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ConsumerConfig.GROUP_ID_CONFIG, "billing-service");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
          StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
          OrderCreatedDeserializer.class);

try (KafkaConsumer<String, OrderCreated> consumer =
         new KafkaConsumer<>(props)) {

    consumer.subscribe(List.of("orders.created"));

    while (!Thread.currentThread().isInterrupted()) {
        ConsumerRecords<String, OrderCreated> records =
            consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, OrderCreated> record : records) {
            billingService.createPendingPayment(record.value());
        }

        // Commit sau khi toàn bộ record trong poll đã xử lý thành công.
        consumer.commitSync();
    }
}
```

Đây là ví dụ rút gọn để thể hiện trách nhiệm của ứng dụng, chưa phải consumer production hoàn chỉnh. Khi triển khai thực tế, cần thiết kế shutdown và wakeup, xử lý exception theo từng record, rebalance listener, giới hạn thời gian xử lý so với `max.poll.interval.ms`, commit offset an toàn và quan sát trạng thái consumer. `KafkaConsumer` không thread-safe; một consumer nên được sở hữu và điều khiển bởi một thread theo đúng quy tắc của Kafka client.

Hai ví dụ giải quyết cùng một nghiệp vụ. Với Spring Kafka, mã nghiệp vụ tập trung ở listener; container đảm nhận phần lớn vòng lặp và lifecycle. Với client thuần, mã ứng dụng nhìn thấy trực tiếp poll và commit nên có quyền điều khiển cao hơn, đồng thời phải chịu trách nhiệm nhiều hơn.

## 6. Reliability không đến tự động từ framework

Dù chọn cách nào, độ tin cậy phụ thuộc vào cấu hình Kafka, thiết kế xử lý message và cách hệ thống phục hồi khi lỗi. Các quyết định sau vẫn cần được làm rõ.

### 6.1. Producer phải biết khi nào broker đã xác nhận

Đối với message quan trọng, cần xem xét `acks`, idempotent producer, retry, replication factor và `min.insync.replicas`. Các thuộc tính producer quyết định điều kiện xác nhận và khả năng chống ghi trùng ở phía producer; cấu hình replication và ISR thuộc về broker/topic.

Spring Kafka giúp đưa cấu hình producer vào Spring properties hoặc producer factory. Client thuần đặt các thuộc tính tương tự trực tiếp trên producer. Không lựa chọn nào thay thế việc kiểm tra cấu hình thực tế và trạng thái cluster.

### 6.2. Consumer cần chính sách commit phù hợp với tác dụng phụ

Nếu consumer commit trước khi hoàn tất xử lý, sự cố có thể khiến message bị bỏ qua. Nếu xử lý xong nhưng chưa commit, sự cố có thể khiến message được giao lại. Vì vậy, at-least-once thường đòi hỏi handler idempotent: cùng một event được xử lý lại không tạo thêm thanh toán, đơn hàng hoặc tác dụng phụ ngoài ý muốn.

Trong Spring Kafka, xác định AckMode và error handler. Với client thuần, xác định rõ offset nào được commit và trong điều kiện nào. Với cả hai, tránh bật auto commit một cách thiếu chủ đích khi ứng dụng cần gắn commit với kết quả xử lý nghiệp vụ.

### 6.3. Retry phải có giới hạn và có đường xử lý cuối

Retry vô hạn có thể khiến partition bị kẹt, tăng độ trễ và làm cạn tài nguyên. Hãy quy định số lần retry, backoff, nhóm lỗi được retry, DLT, cảnh báo và quy trình replay. DLT cũng cần được giám sát; chuyển message vào DLT không có nghĩa sự cố đã được giải quyết.

### 6.4. Bảo toàn thứ tự theo partition

Kafka bảo đảm thứ tự trong một partition. Nếu các event của cùng một đơn hàng phải được xử lý theo thứ tự, hãy dùng key ổn định như `orderId` để chúng được định tuyến vào cùng partition. Tăng concurrency không tạo thêm thứ tự toàn cục; số consumer thread có thể xử lý song song các partition khác nhau.

Retry topic, xử lý song song và thay đổi partition count đều có thể ảnh hưởng đến thứ tự quan sát được ở tầng nghiệp vụ. Cần kiểm thử với luồng event thực tế thay vì giả định rằng annotation listener tự bảo đảm thứ tự.

### 6.5. Transaction có phạm vi rõ ràng

Kafka transaction hữu ích khi cần ghi nhiều record Kafka theo nguyên tử hoặc kết hợp việc consume và produce trong một luồng Kafka. Nó không tự bao phủ thao tác database, HTTP call hay hệ thống bên ngoài. Với các tác dụng phụ ngoài Kafka, thiết kế idempotency hoặc outbox/inbox vẫn rất quan trọng.

## 7. Những sai lầm thường gặp khi lựa chọn

**Chọn Spring Kafka với kỳ vọng framework tự bảo đảm exactly-once.** Framework cung cấp cơ chế transaction và acknowledgement, nhưng semantics cuối cùng phụ thuộc cấu hình, phạm vi transaction và hệ thống bên ngoài. Cần mô tả rõ điều gì được bảo đảm và điều gì có thể chạy lại.

**Chọn client thuần chỉ vì nghĩ rằng nó luôn nhanh hơn.** Hai lựa chọn dùng cùng Kafka Java client. Hãy đo overhead thực tế trước khi chấp nhận chi phí tự quản lý poll loop, rebalance, commit và shutdown.

**Dùng manual acknowledgement nhưng acknowledge trước khi xử lý xong.** Điều này có thể commit offset quá sớm và làm mất cơ hội xử lý lại khi nghiệp vụ thất bại.

**Retry mọi exception theo cùng một cách.** Lỗi dữ liệu không hợp lệ thường không được giải quyết bằng retry liên tục. Phân loại lỗi và đặt giới hạn cho retry.

**Tăng concurrency mà không xét số partition.** Consumer thread chỉ có thể nhận partition để xử lý khi group có partition được phân bổ. Concurrency cao hơn số partition không tạo thêm khả năng xử lý song song hữu ích cho topic đó.

**Dùng đồng thời listener container và một consumer tự tạo cho cùng trách nhiệm mà không phân định ownership.** Điều này dễ gây nhầm lẫn về consumer group, partition assignment và offset. Mỗi consumer cần có một chủ sở hữu vòng đời và chính sách commit rõ ràng.

## 8. Quy trình chọn lựa cho một service mới

Trước khi triển khai, trả lời lần lượt các câu hỏi sau:

1. Service có đang dùng Spring Boot hoặc Spring Framework không? Nếu có, bắt đầu đánh giá Spring Kafka.
2. Use case có phải gửi event và nhận event theo consumer group với mô hình thông thường không? Nếu có, Spring Kafka thường giảm đáng kể mã hạ tầng.
3. Có yêu cầu đặc biệt về partition assignment, rebalance, pause/resume, poll loop hoặc commit offset không? Nếu có, xác định chính xác hook của Spring Kafka có đáp ứng được không; nếu phần lớn thiết kế phải tự quản lý consumer, cân nhắc client thuần.
4. Thành phần này có phải thư viện hoặc công cụ độc lập framework không? Nếu có, client thuần thường giữ API và dependency gọn hơn.
5. Lý do chọn client thuần có phải hiệu năng hoặc tài nguyên không? Nếu có, tạo benchmark có thể lặp lại trước khi quyết định.
6. Đã xác định delivery semantics, idempotency, retry, DLT, thứ tự, transaction và giám sát chưa? Nếu chưa, cần hoàn thiện thiết kế reliability trước khi chọn abstraction.

Một quy tắc thực tế là dùng Spring Kafka cho các luồng Kafka thông thường bên trong ứng dụng Spring, vì nó giảm mã vận hành lặp lại và thống nhất cách tích hợp. Chọn Kafka client thuần khi có lý do kỹ thuật cụ thể cần quyền kiểm soát thấp tầng, tính độc lập framework hoặc dependency tối giản. Có thể kết hợp hai cách ở cấp hệ thống, miễn là ownership của từng producer/consumer, consumer group và offset được xác định rõ.

## 9. Tài liệu cần đối chiếu khi triển khai

Khi triển khai trên một phiên bản cụ thể, đối chiếu tài liệu đúng phiên bản của:

- Spring for Apache Kafka: cấu hình listener container, AckMode, error handling, retry topic, DLT và transaction.
- Spring Boot: thuộc tính `spring.kafka.*` và phiên bản Spring Kafka được dependency management quản lý.
- Apache Kafka Java Client: producer configuration, consumer configuration, offset commit, rebalance và transaction.
- Kafka broker và topic: replication, ISR, retention, partition count và quyền truy cập.

Ưu tiên để Spring Boot quản lý phiên bản dependency tương thích. Nếu ghi đè phiên bản Spring Kafka hoặc Kafka client thủ công, cần xác nhận ma trận tương thích trước khi nâng cấp.
