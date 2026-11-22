# Độ bền và acknowledgement

Producer chịu trách nhiệm gửi record đến Kafka broker. Một lần gọi gửi thành công cần được hiểu chính xác: broker đã nhận record ở mức nào, các replica nào đã sao chép record, và producer có biết chắc kết quả hay không nếu mạng bị gián đoạn. Trong Kafka, thuộc tính **acks** quyết định mức xác nhận mà producer chờ từ broker.

Trong Spring Kafka, các lựa chọn này được cấu hình cho Kafka Producer bên dưới KafkaTemplate. Chọn acks, replication factor và min.insync.replicas cùng nhau giúp cân bằng độ bền dữ liệu, khả năng ghi và độ trễ. Producer retry và idempotence tiếp tục xử lý các lỗi tạm thời và tránh bản ghi trùng do retry nội bộ của producer.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt acks=0, acks=1 và acks=all.
- Giải thích quan hệ giữa acknowledgement, leader/follower replica và ISR.
- Chọn replication factor và min.insync.replicas phù hợp với mức độ quan trọng của dữ liệu.
- Cấu hình producer acknowledgement trong Spring Boot và ProducerFactory.
- Xử lý kết quả bất đồng bộ của KafkaTemplate.send().
- Hiểu retry, timeout và tình huống producer không biết chắc broker đã ghi record hay chưa.
- Giải thích producer idempotence, thứ tự record và ranh giới của Kafka transaction.
- Kiểm thử và giám sát lỗi gửi, retry, độ trễ và tình trạng replica.

## 1. Acknowledgement giải quyết vấn đề gì?

Producer gửi record đến leader của partition. Broker có thể trả lời ngay, trả lời sau khi leader nhận record, hoặc chờ các replica đang đồng bộ xác nhận. Mức chờ này được điều khiển bởi acks.

Ví dụ, producer gửi một sự kiện OrderCreated vào partition 2:

~~~text
Producer
   |
   |  produce record
   v
Partition 2 - Leader
   |
   +----> Follower replica 1
   |
   +----> Follower replica 2
   |
   v
Produce response theo cấu hình acks
~~~

Acknowledgement giúp producer biết broker đã xử lý yêu cầu ghi đến mức nào. Nó không xác nhận consumer đã đọc record, listener đã chạy hay nghiệp vụ trong database đã hoàn tất.

Ba thuộc tính cần tách biệt:

| Thuộc tính | Trả lời câu hỏi |
|---|---|
| acks | Producer cần chờ broker xác nhận ở mức nào? |
| Replication factor và ISR | Partition có bao nhiêu bản sao đang đồng bộ để bảo vệ dữ liệu? |
| Consumer offset | Consumer group đã ghi nhận vị trí đọc tiếp theo đến đâu? |

Không có một giá trị acks độc lập nào bảo đảm toàn bộ luồng nghiệp vụ không mất hoặc không lặp dữ liệu. Cần xem cả cấu hình topic/broker, producer, consumer và hệ thống đích.

## 2. Ba mức acknowledgement

### acks=0: không chờ xác nhận

Producer gửi record nhưng không chờ broker trả response xác nhận.

~~~text
Producer  -------- record -------->  Broker
Producer  <--- tiếp tục gửi --------
                 không chờ ack
~~~

Đặc điểm:

- Độ trễ phía producer thấp vì không chờ response từ broker.
- Producer không biết chắc broker đã nhận và ghi record hay chưa.
- Lỗi broker sau khi gửi có thể không được producer quan sát đầy đủ.
- Không phù hợp với dữ liệu cần độ tin cậy cao.

Có thể cân nhắc acks=0 cho dữ liệu telemetry có thể mất, tần suất rất cao và có cơ chế tổng hợp/bù dữ liệu riêng. Không nên dùng cho lệnh thanh toán, trạng thái đơn hàng hoặc sự kiện nghiệp vụ quan trọng chỉ để giảm vài mili giây.

### acks=1: leader xác nhận

Producer chờ leader xác nhận sau khi leader nhận và append record vào log cục bộ. Producer không chờ follower xác nhận đã sao chép record.

~~~text
Producer  ---- record ---->  Leader
Producer  <--- ack --------  Leader

                           Follower 1 (có thể chưa sao chép)
                           Follower 2 (có thể chưa sao chép)
~~~

Ưu điểm:

- Độ trễ thường thấp hơn acks=all.
- Producer biết leader đã nhận record và trả lời thành công.

Rủi ro:

- Nếu leader lỗi sau khi xác nhận nhưng trước khi follower sao chép record, leader mới có thể không có record đó.
- Nếu replica ngoài ISR được phép trở thành leader, nguy cơ mất dữ liệu có thể cao hơn nữa.

acks=1 có thể phù hợp khi ứng dụng chấp nhận một mức rủi ro mất dữ liệu nhất định và cần cân bằng latency với độ bền. Với sự kiện quan trọng, cần đánh giá kỹ khả năng mất record trong cửa sổ replication chưa hoàn tất.

### acks=all hoặc acks=-1: chờ ISR xác nhận

Với acks=all, producer chờ tất cả replica hiện thuộc ISR xác nhận record. ISR (in-sync replicas) là tập các replica đang theo kịp leader theo tiêu chí đồng bộ của Kafka.

~~~text
Producer  ---- record ---->  Leader
                               |
                 +-------------+-------------+
                 |                           |
                 v                           v
             Follower 1                  Follower 2
                 |                           |
                 +------ replicated --------+
                               |
Producer  <------ ack=all ------+
~~~

Ưu điểm:

- Tăng khả năng giữ record khi leader gặp sự cố.
- Giảm rủi ro record chỉ tồn tại trên leader rồi bị mất khi leader thay đổi.
- Phù hợp với dữ liệu nghiệp vụ cần độ bền cao khi được kết hợp với min.insync.replicas và replication factor phù hợp.

Đánh đổi:

- Độ trễ ghi có thể cao hơn vì phải chờ các replica trong ISR.
- Nếu số replica trong ISR thấp hơn ngưỡng tối thiểu, broker từ chối ghi thay vì hạ mức xác nhận.
- Cụm gặp sự cố replica có thể giảm khả năng ghi cho đến khi ISR được phục hồi.

acks=all là lựa chọn phổ biến cho producer quan trọng, nhưng mức bảo vệ thực tế phụ thuộc vào số replica đang có trong ISR và chính sách bầu leader.

## 3. Replication factor, ISR và min.insync.replicas

acks=all chỉ thực sự tạo mức bảo vệ mong muốn khi topic được cấu hình replication phù hợp.

Giả sử topic có:

- replication.factor=3: mỗi partition có một leader và hai follower.
- min.insync.replicas=2: broker yêu cầu ít nhất hai replica còn trong ISR để chấp nhận một lần ghi acks=all.

Các trạng thái minh họa:

| ISR hiện tại | Ghi với acks=all và min ISR = 2 |
|---|---|
| Leader + Follower 1 + Follower 2 | Chấp nhận; chờ các replica trong ISR xác nhận |
| Leader + Follower 1 | Chấp nhận; chờ hai replica này xác nhận |
| Chỉ Leader | Từ chối ghi vì ISR thấp hơn ngưỡng tối thiểu |
| Không có leader hoạt động | Không thể ghi cho đến khi partition có leader hợp lệ |

Cấu hình min.insync.replicas không tự tạo thêm bản sao. Nó là ngưỡng tối thiểu để broker chấp nhận ghi ở mức acks=all. Replication factor xác định số bản sao mục tiêu; ISR cho biết những replica nào đang theo kịp.

Nếu chỉ dùng replication factor 3 nhưng min.insync.replicas=1, khi hai follower rời ISR, leader đơn lẻ vẫn có thể nhận ghi acks=all. Lúc đó tên all chỉ có nghĩa là tất cả replica hiện có trong ISR (chỉ còn leader) xác nhận. Vì vậy, cần đặt min.insync.replicas để thể hiện số bản sao tối thiểu mà hệ thống thực sự yêu cầu.

### Cấu hình topic và broker

Có thể đặt ngưỡng ở cấp broker làm mặc định hoặc override ở topic. Ví dụ cấu hình topic:

~~~properties
min.insync.replicas=2
~~~

Replication factor không phải topic config có thể thay đổi bằng alter config; nó được chọn khi tạo topic (hoặc lấy từ default.replication.factor của broker khi tạo theo mặc định). min.insync.replicas có thể được cấu hình ở broker hoặc topic theo chính sách quản trị.

Ví dụ tạo topic bằng Kafka CLI:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic order-events \
  --partitions 6 \
  --replication-factor 3 \
  --config min.insync.replicas=2
~~~

Kiểm tra cấu hình topic:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name order-events \
  --describe
~~~

Cần bảo đảm broker đủ số lượng và có phân bố replica phù hợp trên các broker/failure domain. Topic replication factor 3 trên một cụm chỉ có hai broker không thể đạt ba replica độc lập.

### Khi ISR giảm dưới ngưỡng

Khi ISR thấp hơn min.insync.replicas, broker trả lỗi cho producer gửi với acks=all (chẳng hạn NotEnoughReplicas hoặc lỗi liên quan đến số replica trong ISR). Producer có thể retry theo cấu hình và timeout, nhưng retry không tự khôi phục replica. Đội vận hành cần xử lý broker, mạng hoặc replication lag.

Đây là một đánh đổi có chủ đích: hệ thống từ chối ghi để giữ yêu cầu độ bền. Ứng dụng cần xử lý lỗi gửi, retry có giới hạn theo delivery timeout và phát cảnh báo khi lỗi kéo dài.

## 4. Acknowledgement không đồng nghĩa flush xuống đĩa

Kafka ghi log thông qua cơ chế filesystem và page cache của hệ điều hành. Replica acknowledgement phản ánh việc replica đã nhận/append record theo giao thức replication; không nên diễn giải acks=all thành cam kết mọi bản sao đã fsync dữ liệu xuống thiết bị lưu trữ vật lý tại thời điểm trả response.

Kafka dựa vào replication, log recovery và cơ chế lưu trữ của broker để đạt độ bền. Nếu yêu cầu nghiệp vụ đòi hỏi bảo đảm lưu trữ dài hạn hoặc khôi phục thảm họa, cần xem thêm:

- Replication factor và phân bố replica qua broker/rack/availability zone.
- Chính sách clean leader election và hành vi khi mất nhiều replica.
- Backup, snapshot hoặc cơ chế lưu trữ dài hạn phù hợp.
- Theo dõi disk health, under-replicated partitions và broker failure.

Với clean leader election, Kafka ưu tiên chọn leader mới từ ISR để tránh bỏ các record đã được các replica đồng bộ xác nhận. Cho phép unclean leader election có thể tăng khả năng sẵn sàng nhưng có nguy cơ mất record chưa có trên replica được chọn làm leader. Hãy hiểu rõ đánh đổi này trước khi thay đổi cấu hình broker.

## 5. Cấu hình producer trong Spring Boot

Spring Boot cho phép cấu hình acknowledgement thông qua spring.kafka.producer.acks. Các producer properties khác có thể đặt trong spring.kafka.producer.properties.

Ví dụ cho producer cần độ bền cao:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
~~~

Ý nghĩa:

- acks: all: chờ ISR xác nhận.
- enable.idempotence: true: bật producer idempotence để loại bỏ duplicate do retry nội bộ của producer.
- max.in.flight.requests.per.connection: 5: giới hạn số request chưa hoàn tất trên một connection; giá trị này tương thích với producer idempotence ở các Kafka client hiện đại.
- delivery.timeout.ms: giới hạn tổng thời gian producer cố gắng hoàn tất một lần gửi, bao gồm chờ request và retry.
- request.timeout.ms: thời gian producer chờ response cho một request gửi đến broker.

Đây là ví dụ cấu hình, không phải bộ giá trị tối ưu cho mọi hệ thống. delivery.timeout.ms cần đủ lớn so với request timeout và thời gian batching/retry. Nếu timeout quá ngắn, producer có thể báo lỗi trước khi cụm kịp phục hồi.

Nếu dùng phiên bản Kafka client cũ, các giá trị mặc định và điều kiện tương thích có thể khác. Hãy kiểm tra tài liệu đúng với phiên bản dependency đang chạy.

## 6. Cấu hình bằng ProducerFactory

Nếu tự tạo ProducerFactory, có thể khai báo các thuộc tính qua ProducerConfig:

~~~java
@Bean
public ProducerFactory<String, OrderEvent> orderProducerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class);

    props.put(ProducerConfig.ACKS_CONFIG, "all");
    props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
    props.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
    props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);
    props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);

    return new DefaultKafkaProducerFactory<>(props);
}
~~~

Ví dụ tập trung vào acknowledgement và producer reliability. Ứng dụng thực tế cần cấu hình serializer, type mapping, trusted package và các thuộc tính kết nối phù hợp.

Nếu ứng dụng có nhiều ProducerFactory cho nhiều mục đích hoặc cluster, hãy kiểm tra KafkaTemplate đang inject factory nào. Cấu hình spring.kafka.producer không tự động áp dụng cho một factory tự tạo từ map độc lập nếu ứng dụng không truyền các thuộc tính đó vào factory.

## 7. Gửi record bằng KafkaTemplate và xử lý acknowledgement

KafkaTemplate.send() gửi record bất đồng bộ. Với Spring Kafka 3.x, phương thức trả về CompletableFuture<SendResult<K, V>>. Future hoàn tất khi producer nhận kết quả theo cấu hình acks hoặc khi lần gửi thất bại.

Ví dụ:

~~~java
public void publishOrder(String orderId, OrderCreated event) {
    kafkaTemplate.send("order-events", orderId, event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Cannot publish order {}", orderId, exception);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();

            log.info(
                "Published order {} to partition {} at offset {}",
                orderId,
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

Khi gửi thành công, RecordMetadata cung cấp topic, partition, offset và các thông tin của record được broker chấp nhận. Đây là bằng chứng hữu ích để log và quan sát.

Khi gửi thất bại, future hoàn tất với exception. Ứng dụng nên phân loại lỗi, ghi nhận event ID, phát metric và áp dụng retry phù hợp. Không nên bỏ qua exception trong callback vì khi đó hệ thống có thể mất khả năng phát hiện lỗi gửi.

Với Spring Kafka 2.x, API cũ có thể trả về ListenableFuture; hãy đối chiếu phiên bản thư viện trước khi sao chép ví dụ.

### Gửi đồng bộ khi thực sự cần

Có thể chờ kết quả bằng get():

~~~java
SendResult<String, OrderCreated> result =
        kafkaTemplate.send("order-events", orderId, event)
                .get(10, TimeUnit.SECONDS);
~~~

Cách này làm thread gọi bị chặn cho đến khi gửi xong hoặc timeout. Nó có thể hữu ích trong một luồng quản trị hoặc tác vụ cần kết quả ngay, nhưng không nên dùng tùy tiện trong request thread có lưu lượng cao. Hãy cân nhắc throughput, timeout và xử lý exception.

### Khi nào coi lần gửi là thành công?

Điều đó phụ thuộc vào acks:

- Với acks=0, producer không chờ broker xác nhận.
- Với acks=1, producer nhận xác nhận từ leader.
- Với acks=all, producer nhận xác nhận từ các replica trong ISR theo chính sách min ISR.

Vì vậy, callback thành công không có cùng mức ý nghĩa khi cấu hình acks khác nhau. Khi cần độ bền cao, hãy cấu hình acks=all và kiểm tra min.insync.replicas ở broker/topic.

## 8. Retry, timeout và kết quả gửi không rõ ràng

Producer có thể gặp timeout khi broker đã ghi record nhưng response không tới producer. Producer không thể biết chắc request thất bại trước khi ghi hay chỉ thất bại ở đường trả response.

Ví dụ:

~~~text
Producer                     Broker
   |                            |
   | -------- record ---------->|
   |                            | append record
   |                            |
   |       response bị mất      |
   |                            |
   | ---- retry cùng request -->|
   |                            |
   |<----------- ack -----------|
~~~

Nếu producer gửi lại mà không có idempotence, broker có thể append duplicate. Đây là lý do producer idempotence quan trọng.

Các timeout thường cần phân biệt:

| Thuộc tính | Vai trò |
|---|---|
| request.timeout.ms | Thời gian chờ response cho một request đến broker |
| delivery.timeout.ms | Tổng thời gian tối đa để producer hoàn tất một lần gửi, gồm batching, request và retry |
| linger.ms | Thời gian producer có thể chờ thêm để gom record thành batch |
| retry.backoff.ms | Khoảng nghỉ giữa các lần retry trong một số tình huống lỗi |

delivery.timeout.ms là giới hạn tổng cho một lần gửi. Nếu producer chưa thể hoàn tất trước hạn, future sẽ báo lỗi. Việc tăng retry count mà không xem delivery timeout không đảm bảo lần gửi có thêm thời gian thực tế.

### Retry nội bộ và retry ở tầng ứng dụng

- **Producer retry nội bộ:** Kafka producer tự gửi lại request khi gặp lỗi có thể retry. Producer idempotence bảo vệ khỏi duplicate do retry trong cùng producer session.
- **Application retry:** ứng dụng gọi KafkaTemplate.send() lần nữa sau khi nhận lỗi. Đây là một lần gửi mới từ góc nhìn ứng dụng và có thể tạo duplicate nếu lần gửi trước đã được broker ghi nhưng response bị mất.

Nếu retry ở tầng ứng dụng, nên mang theo eventId ổn định và làm consumer idempotent. Không tạo ID mới cho cùng một sự kiện chỉ vì producer cần gửi lại.

## 9. Producer idempotence bảo vệ điều gì?

Producer idempotence dùng producer ID và sequence number để broker nhận diện retry của cùng producer. Khi producer gửi lại một batch do lỗi tạm thời, broker có thể phát hiện đây là bản retry và không append duplicate cho batch đã ghi.

Idempotence giúp:

- Tránh duplicate do producer retry nội bộ.
- Duy trì thứ tự record trong một partition khi retry theo cơ chế idempotent.
- Tăng độ tin cậy khi kết hợp với acks=all.

Idempotence không giải quyết mọi nguồn duplicate:

- Ứng dụng gọi send() hai lần cho cùng một event.
- Hai producer instance độc lập cùng phát một sự kiện.
- Consumer xử lý lại record sau khi offset chưa commit.
- Một lần retry nghiệp vụ tạo ra event mới với ID mới.
- Side effect bên ngoài Kafka đã thành công nhưng consumer bị lỗi trước khi commit offset.

Vì vậy, producer idempotence và consumer idempotency giải quyết hai ranh giới khác nhau. Với nghiệp vụ quan trọng, nên có event ID duy nhất và cơ chế deduplicate ở hệ thống nhận.

## 10. Thứ tự record khi retry

Kafka giữ thứ tự append trong từng partition. Producer gửi cùng key thường định tuyến record vào cùng partition, nhưng retry có thể ảnh hưởng thứ tự nếu idempotence bị tắt và nhiều request đang in-flight.

Với producer không idempotent, nếu có nhiều request chưa hoàn tất và request cũ bị retry, một request mới hơn có thể được broker ghi trước. Điều này có thể làm thứ tự record khác với thứ tự ứng dụng gửi.

Khi bật idempotence, Kafka producer quản lý sequence number để bảo toàn thứ tự retry trong phạm vi producer và partition theo các giới hạn hỗ trợ. Các Kafka client hiện đại cho phép tối đa năm request in-flight mỗi connection khi idempotence bật.

Nếu nghiệp vụ cần thứ tự theo thực thể:

1. Dùng business key như orderId hoặc accountId.
2. Bật producer idempotence.
3. Không tự tạo nhiều producer độc lập gửi cùng key nếu cần một thứ tự nghiệp vụ duy nhất.
4. Tránh xử lý song song phía consumer làm đảo thứ tự side effect.
5. Cân nhắc tác động khi tăng số partition vì phép ánh xạ key có thể thay đổi.

Thứ tự trong Kafka chỉ được đảm bảo trong một partition. Không có thứ tự toàn cục giữa các partition.

## 11. Acknowledgement và Kafka transaction

Acknowledgement trả lời câu hỏi một record đã được broker chấp nhận ở mức nào. Kafka transaction giải quyết một bài toán khác: nhiều record Kafka và offset đầu vào có thể được commit như một đơn vị nguyên tử.

Ví dụ consume-transform-produce:

~~~text
Consume input record
       |
Transform
       |
Begin Kafka transaction
       |
Produce output record(s)
       |
Add consumed offset to transaction
       |
Commit transaction
       |
Output và offset cùng được commit
~~~

Producer transactional yêu cầu idempotence và sử dụng transactional ID phù hợp. Consumer đọc output transactional cần isolation.level=read_committed để chỉ quan sát các record thuộc transaction đã commit.

acks=all không tự tạo exactly-once. Nó tăng mức xác nhận replication cho record được ghi. Exactly-once cho pipeline Kafka cần transaction bao gồm cả output và offset đầu vào.

Kafka transaction cũng không tự bao phủ database, email hay HTTP API. Nếu listener gọi hệ thống ngoài Kafka rồi transaction abort, side effect có thể xảy ra lần nữa khi input được đọc lại. Hãy dùng idempotency key hoặc mẫu inbox/outbox phù hợp.

## 12. Tình huống lỗi và cách xử lý

| Tình huống | Kết quả có thể xảy ra | Cách giảm rủi ro |
|---|---|---|
| Dùng acks=0, broker không nhận record | Producer có thể không phát hiện lỗi | Dùng mức ack cao hơn nếu record quan trọng |
| Leader lỗi sau khi xác nhận acks=1 nhưng follower chưa sao chép | Record có thể mất khi leader mới được bầu | Dùng acks=all, min ISR phù hợp và clean leader election |
| ISR giảm dưới min ISR | Broker từ chối ghi acks=all | Khôi phục replica, theo dõi under-replicated partitions |
| Producer timeout sau khi broker append | Kết quả gửi không rõ ràng; retry thường có thể duplicate | Bật idempotence; dùng event ID ổn định |
| Delivery timeout hết hạn | Future hoàn tất lỗi dù broker có thể đã nhận record trong tình huống response thất lạc | Xử lý lỗi và deduplicate ở consumer |
| Ứng dụng retry bằng một lệnh send mới | Có thể tạo thêm record cho cùng sự kiện | Dùng idempotency key và quy tắc retry |
| Producer gửi cùng key qua nhiều instance | Thứ tự theo nghiệp vụ có thể không như mong muốn | Điều phối producer hoặc xác định version/sequence nghiệp vụ |
| Consumer xử lý thành công nhưng offset chưa commit | Record có thể được giao lại | Idempotent consumer hoặc inbox/unique constraint |

Một lần gửi thất bại không phải lúc nào cũng chứng minh record chưa tồn tại. Với các thao tác không idempotent, hãy coi trạng thái này là không chắc chắn và thiết kế consumer để chịu được duplicate.

## 13. Kiểm thử producer acknowledgement

Kiểm thử cần xác nhận hành vi gửi ở mức producer và broker, không chỉ mock KafkaTemplate.

Các kịch bản tích hợp có giá trị:

- Tạo topic với replication factor 3 và min.insync.replicas=2, gửi record bằng acks=all, xác nhận future hoàn tất và metadata có partition/offset.
- Làm một follower mất kết nối để ISR giảm còn hai, xác nhận ghi vẫn có thể thành công khi đủ min ISR.
- Làm ISR giảm xuống dưới min ISR, xác nhận producer nhận lỗi hoặc retry cho đến delivery timeout.
- Tạo lỗi kết nối tạm thời và xác nhận producer idempotence không tạo duplicate do retry nội bộ.
- Gửi cùng event ID qua application retry để xác nhận consumer deduplicate đúng.
- Kiểm tra callback success và failure đều được ghi nhận.
- Đo latency giữa các mức acks trong môi trường thử nghiệm có replication thực.

Không nên dùng một broker đơn lẻ để kết luận về hành vi ISR hoặc replication factor 3. Kịch bản cần số broker và topology đủ để mô phỏng các replica thực tế.

## 14. Quan sát producer trong môi trường chạy thật

Các chỉ số hữu ích:

- Tỷ lệ send success và send failure.
- Producer retry rate và error rate theo loại exception.
- Request latency, record send rate và batch size.
- Thời gian chờ acknowledgement và delivery timeout.
- Under-replicated partitions, ISR shrink/expand và offline partitions.
- Số lần NotEnoughReplicas hoặc lỗi liên quan đến min ISR.
- Số duplicate event ID được consumer phát hiện.

Khi latency tăng, hãy kiểm tra broker load, replication lag, network, request queue và batch configuration. Khi send failure tăng cùng ISR shrink, vấn đề có thể nằm ở cụm broker hoặc mạng chứ không phải logic KafkaTemplate.

## Checklist thiết kế producer

- [ ] Chọn acks dựa trên mức độ quan trọng của dữ liệu.
- [ ] Topic có replication factor phù hợp với số broker và failure domain.
- [ ] min.insync.replicas phản ánh số bản sao tối thiểu cần thiết.
- [ ] Producer idempotence được bật khi cần bảo vệ retry nội bộ.
- [ ] request.timeout.ms và delivery.timeout.ms phù hợp với SLO.
- [ ] Callback của KafkaTemplate.send() xử lý cả success và failure.
- [ ] Application retry dùng event ID ổn định và có kiểm soát duplicate.
- [ ] Consumer xử lý idempotent để chịu được giao lại.
- [ ] Nếu cần exactly-once Kafka-to-Kafka, transaction bao gồm output và offset.
- [ ] Có metric/cảnh báo cho send failure, retry, latency và ISR.

## Kết luận

acks xác định producer chờ broker xác nhận đến mức nào: không chờ với 0, chờ leader với 1, hoặc chờ các replica trong ISR với all. Độ bền thực tế còn phụ thuộc replication factor và min.insync.replicas. Trong Spring Kafka, hãy cấu hình producer properties phù hợp, xử lý kết quả bất đồng bộ của KafkaTemplate, bật idempotence khi cần và thiết kế consumer chịu được duplicate. Acknowledgement xác nhận việc ghi vào Kafka theo mức đã chọn; nó không thay thế transaction nghiệp vụ hoặc bảo đảm side effect ở hệ thống bên ngoài.

