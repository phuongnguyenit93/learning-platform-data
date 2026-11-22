# delivery.timeout.ms

Trong Kafka producer, **delivery.timeout.ms** đặt giới hạn thời gian mà producer dành cho một record để hoàn tất việc gửi và báo kết quả thành công hoặc thất bại cho ứng dụng. Đây là một trong những cấu hình quan trọng của producer bền vững vì nó quyết định một record có bao nhiêu thời gian để chờ batching, chờ broker xác nhận và thử lại khi gặp lỗi có thể phục hồi.

Trong Spring Kafka, cấu hình này được truyền tới Kafka producer client thông qua producer properties. Nó hoạt động ở phía client, không phải cấu hình timeout của broker. Hiểu đúng phạm vi của nó giúp ứng dụng tránh báo lỗi quá sớm khi cluster chỉ gián đoạn ngắn, đồng thời tránh giữ record trong hàng đợi quá lâu khi hệ thống đang gặp sự cố.

## 1. delivery.timeout.ms điều khiển điều gì?

Một lời gọi gửi record không nhất thiết được chuyển ngay thành một request tới broker. Producer có thể giữ record trong buffer để gom batch, chờ metadata, gửi request, đợi acknowledgement và thử lại nếu gặp lỗi tạm thời. Các bước này tiêu tốn thời gian.

**delivery.timeout.ms** giới hạn tổng thời gian Kafka producer cho phép record chờ để được giao thành công hoặc bị kết luận thất bại. Nếu record chưa được giao thành công trong thời hạn này, producer hoàn tất thao tác gửi với lỗi timeout. Ứng dụng nhận lỗi thông qua callback hoặc future của lần gửi.

Có thể hình dung luồng gửi như sau:

~~~mermaid
flowchart TD
    A["Ứng dụng gọi send(record)"] --> B["Producer xếp record vào buffer"]
    B --> C["Chờ batching theo linger.ms"]
    C --> D["Gửi Produce request tới broker"]
    D --> E{"Nhận acknowledgement thành công?"}
    E -->|Có| F["Hoàn tất future thành công"]
    E -->|Không, lỗi có thể retry| G["Chờ retry backoff"]
    G --> H{"Còn thời gian delivery?"}
    H -->|Có| D
    H -->|Không| I["Hoàn tất future với lỗi timeout"]
    E -->|Lỗi không thể retry| J["Hoàn tất future với lỗi tương ứng"]
~~~

Thời hạn này bao trùm thời gian chờ trước khi gửi, thời gian chờ broker xác nhận và thời gian dành cho các lần gửi lại có thể phục hồi. Producer có thể báo lỗi sớm hơn nếu gặp lỗi không thể retry, đã hết số lần retry được cấu hình hoặc batch có deadline hết hạn sớm hơn.

Đây là deadline giao record ở phía producer. Nó không phải thời gian xử lý nghiệp vụ ở consumer, không phải thời gian lưu record trong Kafka và cũng không phải thời gian tối đa cho toàn bộ một request HTTP đi qua ứng dụng.

## 2. Phân biệt các timeout liên quan

Không nên điều chỉnh delivery.timeout.ms một cách độc lập. Một số cấu hình producer có quan hệ trực tiếp với thời gian giao record nhưng điều khiển những giai đoạn khác nhau.

| Cấu hình | Phạm vi | Ý nghĩa |
|---|---|---|
| **delivery.timeout.ms** | Toàn bộ quá trình giao một record | Giới hạn tổng thời gian producer chờ để báo kết quả gửi |
| **request.timeout.ms** | Một request tới broker | Giới hạn thời gian client chờ response cho một request |
| **linger.ms** | Trước khi gửi batch | Thời gian producer có thể chờ thêm record để tạo batch hiệu quả hơn |
| **retry.backoff.ms** | Giữa các lần thử lại | Khoảng chờ trước khi retry một request thất bại |
| **retries** | Số lần thử lại | Giới hạn số lần retry nếu cấu hình đặt một giới hạn hữu hạn |
| **max.block.ms** | Một số thao tác đồng bộ trong send | Giới hạn thời gian lời gọi send chờ metadata hoặc chờ cấp buffer khi producer chưa thể nhận record |

### 2.1 request.timeout.ms: giới hạn cho một request

Khi producer gửi Produce request tới broker, client phải chờ response. **request.timeout.ms** giới hạn thời gian chờ response của request đó.

Nếu broker hoặc mạng không trả lời trong thời gian này, client xem request là thất bại. Nếu lỗi có thể retry và record vẫn còn thời gian trong delivery deadline, producer có thể gửi lại request.

Ví dụ, request timeout là 30 giây. Một request không nhận được response sau khoảng thời gian đó có thể được thử lại. Một record có delivery timeout 120 giây có thể có cơ hội trải qua nhiều chu kỳ request và retry, tùy theo backoff, tình trạng mạng và số lần retry còn lại.

Do đó, request.timeout.ms là giới hạn ở cấp request, còn delivery.timeout.ms là ngân sách thời gian ở cấp record.

### 2.2 linger.ms: thời gian chờ gom batch

Producer có thể giữ record trong accumulator một khoảng thời gian trước khi gửi để gom nhiều record cùng partition thành một batch. **linger.ms** điều khiển khoảng chờ thêm này.

Giá trị linger lớn hơn có thể tăng khả năng gom batch, giảm số request và cải thiện throughput trong một số tải. Đổi lại, record có thể chờ lâu hơn trước khi được gửi. Thời gian chờ batching nằm trong ngân sách delivery timeout.

Nếu đặt delivery timeout quá sát request timeout mà vẫn dành thời gian cho linger, cấu hình có thể không hợp lệ hoặc không còn đủ thời gian cho chu kỳ gửi. Kafka yêu cầu:

\[
delivery.timeout.ms \ge request.timeout.ms + linger.ms
\]

Ví dụ, với request timeout 30.000 ms và linger 5 ms, delivery timeout phải ít nhất 30.005 ms. Trong thực tế nên có khoảng dự phòng cho retry và dao động của cluster, thay vì chỉ đặt đúng mức tối thiểu.

### 2.3 retry.backoff.ms và retries

Khi một request gặp lỗi có thể phục hồi, producer có thể chờ **retry.backoff.ms** rồi thử lại. Thời gian backoff cũng tiêu tốn ngân sách delivery timeout.

**retries** giới hạn số lần thử lại nếu được cấu hình thành một số hữu hạn. Vì vậy record có thể thất bại trước delivery deadline nếu đã hết lượt retry. Ngược lại, nếu còn retry nhưng delivery deadline đã hết, producer không tiếp tục thử chỉ vì số lượt retry vẫn còn.

Trong các Kafka client hiện đại, delivery timeout là giới hạn tổng thể quan trọng cho quá trình retry. Không nên dựa vào một giá trị retries lớn để suy ra producer sẽ thử mãi; deadline giao record vẫn giới hạn thời gian.

### 2.4 max.block.ms không thay thế delivery.timeout.ms

Producer có thể phải chờ metadata của topic hoặc chờ buffer trống trước khi có thể nhận record. **max.block.ms** giới hạn một số thao tác chờ đồng bộ bên trong lời gọi send.

Delivery timeout quản lý vòng đời giao record sau khi producer nhận record vào quá trình gửi. Max block điều khiển thời gian chờ để lời gọi gửi có thể tiếp tục khi thiếu metadata hoặc buffer. Vì vậy thời gian mà thread ứng dụng quan sát quanh lời gọi send có thể chịu ảnh hưởng của cả hai cấu hình.

Nếu ứng dụng gặp lỗi kiểu chờ metadata hoặc buffer, chỉ tăng delivery timeout không giải quyết được nguyên nhân. Cần xem bootstrap servers, metadata, kết nối tới cluster, kích thước buffer, tốc độ gửi và tình trạng producer.

## 3. Quan hệ với acks và độ bền dữ liệu

Delivery timeout chỉ trả lời câu hỏi **producer chờ tối đa bao lâu để có kết quả**. Nó không quyết định broker cần xác nhận theo mức nào và cũng không tự tạo ra khả năng chống mất dữ liệu.

Cấu hình **acks** xác định mức acknowledgement producer yêu cầu:

- **acks=0**: producer không chờ broker xác nhận. Thời hạn chờ acknowledgement không mang ý nghĩa bảo đảm tương tự các chế độ có acknowledgement.
- **acks=1**: producer chờ leader partition xác nhận ghi record.
- **acks=all**: producer chờ các replica hiện thuộc ISR xác nhận theo semantics của Kafka.

Với luồng cần độ bền cao, ứng dụng thường phối hợp acks=all với replication factor và min.insync.replicas phù hợp ở phía cluster. Ví dụ, topic có replication factor 3 và min.insync.replicas 2 có thể tiếp tục nhận ghi với acks=all khi ít nhất hai replica còn trong ISR. Nếu ISR thấp hơn ngưỡng, broker có thể từ chối ghi để bảo vệ mức độ bền đã đặt ra.

Ví dụ cấu hình producer:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[linger.ms]": 5
~~~

Trong ví dụ này:

- Producer yêu cầu acknowledgement theo acks=all.
- Idempotence được bật để Kafka producer có thể xử lý retry nội bộ mà tránh tạo duplicate do các lần gửi lại thuộc cùng producer session.
- Mỗi record có ngân sách giao tối đa 120 giây.
- Một request được giới hạn thời gian chờ response ở 30 giây.
- Producer có thể chờ thêm tối đa 5 ms để gom batch.

Các giá trị chỉ là ví dụ khởi điểm. Chúng cần được điều chỉnh theo latency thực tế, khả năng chịu gián đoạn, SLO và cấu hình broker của môi trường triển khai.

**Tăng delivery.timeout.ms không làm record bền hơn.** Nó chỉ cho producer thêm thời gian để thử hoàn tất việc gửi. Độ bền phụ thuộc vào acknowledgement, replication, ISR, trạng thái cluster và các quyết định lưu trữ liên quan.

## 4. Cấu hình delivery.timeout.ms trong Spring Kafka

### 4.1 Spring Boot application properties

Spring Boot cho phép truyền các thuộc tính Kafka client qua map **spring.kafka.producer.properties**. Delivery timeout là thuộc tính của Kafka producer client, vì vậy có thể cấu hình tại đây:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker-1:9092,broker-2:9092
    producer:
      acks: all
      properties:
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[linger.ms]": 5
        "[enable.idempotence]": true
~~~

Dạng properties tương đương:

~~~properties
spring.kafka.bootstrap-servers=broker-1:9092,broker-2:9092
spring.kafka.producer.acks=all
spring.kafka.producer.properties[delivery.timeout.ms]=120000
spring.kafka.producer.properties[request.timeout.ms]=30000
spring.kafka.producer.properties[linger.ms]=5
spring.kafka.producer.properties[enable.idempotence]=true
~~~

Cách đặt thuộc tính trong map giúp Spring Boot chuyển đúng tên Kafka client property, bao gồm dấu chấm trong **delivery.timeout.ms**. Không nhầm thuộc tính này với một timeout do Spring listener container quản lý.

### 4.2 Cấu hình bằng ProducerFactory

Nếu ứng dụng tự tạo ProducerFactory, có thể đặt thuộc tính trực tiếp trong cấu hình producer:

~~~java
Map<String, Object> props = new HashMap<>();

props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
props.put(ProducerConfig.LINGER_MS_CONFIG, 5);

ProducerFactory<String, OrderCreated> producerFactory =
        new DefaultKafkaProducerFactory<>(props);

KafkaTemplate<String, OrderCreated> kafkaTemplate =
        new KafkaTemplate<>(producerFactory);
~~~

Các hằng số trong **ProducerConfig** giúp tránh gõ sai tên thuộc tính. Nếu ứng dụng dùng cấu hình producer chung do Spring Boot tạo, nên giữ cấu hình ở một nơi nhất quán để tránh giá trị ở custom ProducerFactory ghi đè giá trị từ application properties.

### 4.3 Chọn giá trị theo môi trường

Một số hướng lựa chọn:

| Môi trường / đặc điểm tải | Hướng cấu hình |
|---|---|
| Phát triển local | Có thể dùng deadline ngắn hơn để phát hiện lỗi cấu hình nhanh, nhưng vẫn phải thỏa quan hệ với request timeout và linger |
| Production ổn định, có retry | Dùng ngân sách đủ cho một số chu kỳ request và backoff khi có gián đoạn ngắn |
| Mạng liên vùng hoặc broker có failover | Đo latency và thời gian phục hồi thực tế trước khi chọn deadline dài hơn |
| API có deadline phản hồi ngắn | Xác định rõ API có chờ Kafka acknowledgement hay ghi qua outbox rồi trả kết quả; đồng bộ các deadline của các tầng |
| Hệ thống có downstream chậm | Phân biệt producer delivery timeout với timeout của database/API downstream; không kéo dài Kafka timeout để che lỗi ở dịch vụ khác |

Kafka client hiện đại thường có mặc định **120.000 ms** cho delivery timeout. Tuy vậy, cần kiểm tra phiên bản Kafka client thực tế mà ứng dụng Spring Kafka đang sử dụng, vì mặc định và khả năng cấu hình có thể thay đổi theo phiên bản.

## 5. Nhận biết timeout trong Spring Kafka

Ở các phiên bản Spring Kafka hiện đại, **KafkaTemplate.send** trả về một CompletableFuture. Ứng dụng nên gắn callback để xử lý cả kết quả thành công lẫn thất bại.

~~~java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send("orders.created", event.orderId(), event);

future.whenComplete((result, error) -> {
    if (error != null) {
        log.error(
            "Kafka delivery failed for eventId={}",
            event.eventId(),
            error
        );
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();

    log.info(
        "Kafka delivery acknowledged: eventId={}, topic={}, partition={}, offset={}",
        event.eventId(),
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
});
~~~

Khi deadline giao record hết hạn, future hoàn tất với lỗi. Tùy phiên bản và lớp tích hợp, exception mà ứng dụng nhìn thấy có thể được Spring bọc trong exception khác; cần kiểm tra nguyên nhân gốc thay vì chỉ so sánh chuỗi message.

Callback cần ghi nhận đủ thông tin để truy vết: event ID, topic, key phù hợp, loại lỗi và thời điểm. Tránh ghi toàn bộ payload nhạy cảm vào log. Callback cũng nên thực hiện công việc ngắn gọn; nếu cần thao tác phục hồi tốn thời gian, hãy chuyển sang executor hoặc cơ chế xử lý nền có kiểm soát.

### 5.1 Gửi đồng bộ và timeout ở tầng gọi

Ứng dụng có thể gọi **future.get(timeout)** để giới hạn thời gian thread chờ kết quả. Đây là timeout của thao tác chờ ở phía ứng dụng, khác với delivery.timeout.ms.

Ví dụ, nếu thread HTTP chỉ chờ 3 giây nhưng producer có delivery timeout 120 giây, thao tác get có thể hết 3 giây trước khi producer kết luận record thất bại. Việc thread ngừng chờ không chứng minh Kafka đã hủy lần gửi. Record vẫn có thể được broker xác nhận sau đó.

Vì vậy cần phân biệt:

- **Delivery timeout**: Kafka producer kết luận việc giao record thành công hay thất bại trong ngân sách của nó.
- **Caller wait timeout**: thread ứng dụng ngừng chờ kết quả sau thời gian do ứng dụng đặt.
- **HTTP/request timeout**: gateway, server hoặc client HTTP kết thúc request theo deadline riêng.

Không nên xem timeout của future.get là bằng chứng record chưa vào Kafka. Nếu ứng dụng trả lỗi cho caller rồi gửi lại cùng nghiệp vụ bằng một event mới, có thể phát sinh xử lý trùng.

## 6. Điều gì xảy ra khi delivery timeout hết hạn?

Khi record không thể được giao thành công trong deadline, producer hoàn tất thao tác gửi với lỗi timeout. Ứng dụng cần quyết định cách lưu nhận biết sự kiện thất bại, có retry ở tầng nghiệp vụ hay không và làm thế nào để tránh mất hoặc nhân đôi sự kiện.

Một số tình huống cần phân biệt:

### 6.1 Broker tạm thời không khả dụng

Producer có thể chưa gửi được request hoặc không nhận được response. Nếu broker phục hồi trước khi deadline hết và lỗi có thể retry, producer có thể gửi thành công. Nếu deadline hết trước khi phục hồi, future báo lỗi.

Tăng deadline có thể giúp vượt qua một gián đoạn ngắn. Nhưng nếu cluster ngừng hoạt động lâu, tăng timeout chỉ làm ứng dụng chờ lâu hơn trước khi nhận lỗi. Nó không phục hồi broker hay giải quyết lỗi network.

### 6.2 Broker đã ghi nhưng acknowledgement bị thất lạc

Một trường hợp khó hơn là broker đã nhận và ghi record, nhưng response không về được producer do mạng bị ngắt. Producer không có bằng chứng xác nhận thành công. Sau các lần retry hoặc khi deadline hết, ứng dụng có thể nhận lỗi dù record đã được ghi vào Kafka.

Vì thế, **timeout không luôn đồng nghĩa với việc broker chắc chắn chưa lưu record**. Kết quả có thể không xác định được từ phía producer.

Producer idempotence giúp Kafka xử lý duplicate phát sinh từ retry nội bộ của producer trong phạm vi producer session và protocol hỗ trợ. Nhưng nếu ứng dụng tạo một lần gửi mới sau lỗi timeout, đặc biệt sau restart hoặc bằng một producer session khác, idempotence không thay thế idempotency ở tầng nghiệp vụ.

Cách bảo vệ phù hợp là gắn event ID ổn định với sự kiện, để consumer có thể nhận diện và xử lý lặp an toàn. Nếu sự kiện bắt nguồn từ một thay đổi database, transactional outbox giúp lưu thay đổi nghiệp vụ và ý định phát event trong cùng transaction; publisher có thể tiếp tục gửi outbox chưa được xác nhận.

### 6.3 Producer quá tải hoặc buffer không đủ

Nếu producer gửi nhanh hơn khả năng broker tiếp nhận, batch có thể chờ lâu trong accumulator. Buffer pressure cũng có thể làm thread gọi send phải chờ cấp phát bộ nhớ và chạm max.block.ms.

Trong trường hợp này, tăng delivery timeout có thể làm record chờ lâu hơn và khiến hàng đợi giữ dữ liệu trong thời gian dài hơn. Hãy kiểm tra tốc độ gửi, kích thước batch, buffer memory, số thread gửi, broker throughput và tình trạng network trước khi tăng deadline.

### 6.4 Broker phản hồi lỗi không thể retry

Một số lỗi là lỗi cấu hình hoặc nghiệp vụ ở tầng Kafka client, ví dụ authorization failure hoặc lỗi serialization ở phía ứng dụng. Các lỗi không thể retry sẽ được báo sớm, không cần đợi toàn bộ delivery timeout.

Nếu mọi lỗi đều bị quy về timeout, đội vận hành có thể bỏ lỡ nguyên nhân thật. Hãy phân loại exception và theo dõi cause chain.

## 7. Xây dựng chiến lược retry an toàn

Delivery timeout kết thúc một lần thử giao record ở phía producer. Nó không tự quyết định ứng dụng phải thử lại nghiệp vụ như thế nào.

Một chiến lược retry nên có ba lớp:

1. **Retry nội bộ của producer**: xử lý lỗi tạm thời trong giới hạn retries và delivery timeout của Kafka client.
2. **Retry bền vững ở ứng dụng**: nếu lần gửi thất bại, lưu trạng thái cần gửi lại trong outbox hoặc kho dữ liệu bền vững, thay vì chỉ giữ trong bộ nhớ.
3. **Idempotency ở consumer/nghiệp vụ**: nếu cùng một event được giao nhiều lần, side effect không bị thực hiện lặp ngoài ý muốn.

Ví dụ, một publisher đọc các bản ghi outbox chưa gửi, gửi event bằng KafkaTemplate và chỉ đánh dấu bản ghi đã publish sau khi nhận acknowledgement. Nếu process dừng sau khi Kafka đã ghi event nhưng trước khi cập nhật trạng thái outbox, publisher có thể gửi lại event đó. Consumer cần nhận diện event ID để xử lý lặp an toàn.

Không nên viết vòng lặp retry vô hạn ngay trong callback gửi. Vòng lặp như vậy có thể chiếm thread, tạo tải lớn hơn khi broker đang quá tải và làm request kéo dài không giới hạn. Retry cần có backoff, giới hạn tốc độ, trạng thái bền vững và khả năng quan sát.

### 7.1 Idempotence không thay thế idempotency nghiệp vụ

Bật **enable.idempotence=true** giúp producer chống duplicate do retry protocol của chính producer. Nó không bảo đảm một thao tác nghiệp vụ chỉ được phát đúng một lần trong mọi tình huống.

Ví dụ, dịch vụ đặt hàng gửi event OrderCreated. Broker đã ghi event nhưng acknowledgement thất lạc. Ứng dụng timeout và tạo một lần gửi mới sau khi khởi động lại. Nếu event mới có ID khác, consumer có thể coi đó là một sự kiện mới và tạo side effect lần thứ hai.

Nếu event ID ổn định theo giao dịch nghiệp vụ, consumer có thể kiểm tra inbox table hoặc unique constraint trước khi áp dụng side effect. Đây là lớp bảo vệ cần thiết khi kết quả gửi không xác định.

## 8. Điều chỉnh delivery timeout theo SLO

Không có một giá trị delivery timeout phù hợp cho mọi ứng dụng. Giá trị cần phản ánh khoảng gián đoạn mà hệ thống muốn tự phục hồi, mức trễ mà producer có thể chấp nhận và deadline của tầng gọi.

Khi chọn giá trị, hãy trả lời:

- Ứng dụng có thể chờ tối đa bao lâu để Kafka xác nhận một record?
- Cluster thường phục hồi broker hoặc leader trong bao lâu khi có failover?
- Độ trễ request ở percentile cao là bao nhiêu trong điều kiện tải production?
- Producer có cần thời gian gom batch đáng kể không?
- Các retry và backoff cần bao nhiêu thời gian?
- API caller hoặc job scheduler có deadline ngắn hơn producer hay không?
- Nếu gửi thất bại, ứng dụng có outbox hoặc cơ chế phát lại bền vững không?

Một cấu hình minh họa cho producer cần độ bền có thể là:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[linger.ms]": 5
~~~

Giá trị 120 giây cho phép producer có ngân sách dài hơn một request timeout để xử lý gián đoạn và retry. Nó chỉ là ví dụ. Nếu SLO yêu cầu báo lỗi trong 5 giây, cấu hình 120 giây có thể không phù hợp với đường request đồng bộ; khi đó cần xem lại kiến trúc gửi, deadline của caller và cơ chế outbox.

Không nên giảm request timeout xuống quá thấp để buộc producer báo lỗi nhanh trong mọi trường hợp. Timeout quá ngắn có thể biến biến động latency bình thường thành retry liên tục. Cũng không nên tăng delivery timeout vô hạn: record chờ lâu có thể chiếm buffer, trì hoãn cảnh báo và làm thời gian phục hồi nghiệp vụ khó dự đoán.

## 9. Theo dõi producer để biết timeout đến từ đâu

Khi delivery timeout xảy ra, cần quan sát cả kết quả gửi và sức khỏe producer. Chỉ nhìn số exception timeout sẽ không đủ để phân biệt broker chậm, network lỗi hay producer bị nghẽn.

Các metric Kafka producer hữu ích gồm:

| Metric | Điều cần quan sát |
|---|---|
| **record-error-rate** | Tần suất record gửi thất bại |
| **record-retry-rate** | Tần suất producer phải retry |
| **request-latency-avg / request-latency-max** | Độ trễ response của request tới broker |
| **record-queue-time-avg / record-queue-time-max** | Thời gian record nằm trong hàng đợi producer trước khi gửi |
| **bufferpool-wait-time** | Thời gian producer chờ buffer |
| **bufferpool-wait-ratio** | Tỷ lệ thời gian producer phải chờ buffer |
| **requests-in-flight** | Số request đang chờ response |

Có thể kết hợp các metric với log chứa event ID, topic, partition khi đã có metadata, loại exception, thời gian gửi và trạng thái outbox. Nếu request latency tăng cùng record queue time, hãy kiểm tra tải broker, network và batching. Nếu buffer wait tăng, hãy kiểm tra tốc độ producer, buffer memory và khả năng drain batch. Nếu lỗi authorization hoặc serialization xuất hiện, tăng delivery timeout không giải quyết được nguyên nhân.

Trong Spring Boot, các Kafka client metrics có thể được tích hợp với hệ thống quan sát của ứng dụng tùy cấu hình Micrometer và phiên bản Spring Boot. Cần xác nhận metric thực sự được export trong môi trường triển khai và thiết lập cảnh báo theo baseline của hệ thống.

## 10. Quy trình xử lý incident liên quan delivery timeout

Khi producer bắt đầu báo delivery timeout, có thể điều tra theo trình tự:

1. **Xác định phạm vi**: một topic, một producer instance, một broker leader hay toàn bộ ứng dụng đang bị ảnh hưởng?
2. **Kiểm tra exception gốc**: lỗi là timeout request, lỗi metadata, authorization, serialization hay lỗi khác?
3. **Kiểm tra latency**: request latency và record queue time có tăng trước khi timeout không?
4. **Kiểm tra buffer**: producer có chờ buffer hoặc có nhiều thread bị block không?
5. **Kiểm tra cluster**: broker availability, leader changes, ISR, request handler saturation và network.
6. **Đối chiếu deadline**: delivery timeout, request timeout, linger, retry backoff và deadline của caller có tương thích không?
7. **Xác định trạng thái nghiệp vụ**: record có thể đã được ghi nhưng acknowledgement bị mất không? Có event ID ổn định và cơ chế deduplicate không?
8. **Khôi phục có kiểm soát**: phục hồi kết nối hoặc cluster, để producer retry trong giới hạn, sau đó xử lý outbox còn pending và theo dõi duplicate.

Không nên chỉ tăng delivery timeout ngay khi có incident. Trước tiên cần biết record bị chậm ở giai đoạn batching, request, retry hay buffer. Sau khi xác định nguyên nhân, mới điều chỉnh đúng timeout hoặc capacity tương ứng.

## 11. Các lỗi cấu hình và hiểu nhầm thường gặp

| Hiểu nhầm | Hệ quả | Cách hiểu đúng |
|---|---|---|
| Delivery timeout là timeout của broker | Điều chỉnh sai nơi | Đây là Kafka producer client property |
| Tăng delivery timeout sẽ bảo đảm không mất record | Tạo cảm giác an toàn giả | Độ bền còn phụ thuộc acks, replication, ISR và cách ứng dụng phục hồi |
| Request timeout và delivery timeout là một | Chọn deadline không hợp lý | Request timeout giới hạn một request; delivery timeout giới hạn toàn bộ quá trình giao record |
| Timeout nghĩa là broker chưa ghi | Có thể gửi lại và tạo duplicate | Broker có thể đã ghi nhưng acknowledgement bị thất lạc |
| Future.get timeout hủy lần gửi | Ứng dụng có thể gửi lại khi record cũ vẫn đang được giao | Timeout của caller chỉ kết thúc việc chờ ở thread đó |
| Retries lớn nghĩa là thử mãi | Record vẫn có thể hết hạn | Delivery timeout là deadline tổng thể |
| Tăng timeout luôn cải thiện độ tin cậy | Làm lỗi được phát hiện muộn và giữ record lâu hơn | Cần cân bằng thời gian phục hồi, SLO, buffer và khả năng xử lý sự cố |

Một lỗi cấu hình phổ biến là đặt delivery timeout nhỏ hơn tổng request timeout và linger. Kafka client yêu cầu delivery timeout ít nhất bằng tổng hai giá trị đó. Nếu thay đổi một trong hai giá trị, cần kiểm tra lại quan hệ này để tránh producer không khởi tạo được.

## 12. Checklist trước khi đưa producer vào production

**Cấu hình thời gian**

- [ ] Delivery timeout được đặt theo SLO và khả năng phục hồi của cluster.
- [ ] Delivery timeout lớn hơn hoặc bằng request timeout cộng linger.
- [ ] Request timeout phản ánh latency thực tế và không quá thấp.
- [ ] Retry backoff và số lần retry phù hợp với ngân sách giao record.
- [ ] Max block được xem xét riêng cho metadata và buffer allocation.

**Độ bền và xử lý lỗi**

- [ ] Acks phù hợp với yêu cầu độ bền của luồng.
- [ ] Replication factor và min.insync.replicas của topic được xác nhận với đội nền tảng.
- [ ] Producer idempotence được bật khi phù hợp.
- [ ] Ứng dụng xử lý future/callback thất bại và ghi nhận event ID.
- [ ] Timeout được xem là kết quả có thể chưa xác định khi acknowledgement thất lạc.
- [ ] Có idempotency ở tầng nghiệp vụ và cơ chế outbox nếu cần phát lại bền vững.

**Quan sát và vận hành**

- [ ] Có metric cho record error, retry, request latency, queue time và buffer wait.
- [ ] Log có event ID và thông tin đủ để truy vết, không lộ payload nhạy cảm.
- [ ] Có cảnh báo khi timeout tăng vượt baseline.
- [ ] Runbook phân biệt lỗi broker, network, buffer, metadata và cấu hình.
- [ ] Có kiểm thử broker unavailable, failover, mất acknowledgement và producer restart.

## 13. Nguyên tắc vận hành

**delivery.timeout.ms là ngân sách thời gian cho Kafka producer hoàn tất việc giao một record.** Nó phối hợp với request.timeout.ms, linger.ms, retry.backoff.ms và retries để quyết định producer chờ bao lâu trước khi trả kết quả cho ứng dụng.

Trong Spring Kafka, hãy cấu hình thuộc tính này ở producer properties, theo dõi future từ KafkaTemplate và kết nối lỗi gửi với quy trình phục hồi bền vững. Phối hợp nó với acks và replication để đạt mức độ bền mong muốn, đồng thời dùng event ID và idempotent consumer để xử lý trường hợp kết quả gửi không xác định.

Một producer bền vững cần deadline rõ ràng, retry có giới hạn, quan sát được nguyên nhân lỗi và có khả năng phục hồi sau khi process hoặc kết nối gặp sự cố.
