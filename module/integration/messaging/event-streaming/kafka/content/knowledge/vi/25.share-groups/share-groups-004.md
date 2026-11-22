# KafkaShareConsumer và vòng lặp nhận bản ghi

## Mục tiêu

Kafka Share Groups cho phép nhiều consumer cùng chia sẻ việc xử lý record của một topic. Khác với consumer group truyền thống, các member trong share group có thể cùng nhận record từ một partition; broker khóa tạm thời record đã giao cho một member và chờ acknowledgement để biết record đã xử lý xong, cần giao lại hay bị từ chối.

Trong Java, client chính để tham gia share group là **KafkaShareConsumer**. Ứng dụng đăng ký topic bằng **subscribe()**, gọi **poll()** trong vòng lặp nhận bản ghi, xử lý record rồi xác nhận kết quả bằng implicit hoặc explicit acknowledgement.

Bài học này tập trung vào vòng lặp poll, cơ chế acquisition lock, acknowledgement theo từng record, retry, liveness và cách vận hành share group.

Sau bài học, bạn có thể:

- Giải thích cách KafkaShareConsumer tham gia share group và nhận record.
- Phân biệt share group với consumer group truyền thống.
- Viết vòng lặp poll và đóng consumer an toàn.
- Chọn implicit hay explicit acknowledgement.
- Dùng ACCEPT, RELEASE và REJECT đúng theo kết quả xử lý.
- Hiểu acquisition lock, delivery count và giới hạn thời gian xử lý.
- Kiểm tra share group bằng CLI và theo dõi lỗi trong production.

## 1. KafkaShareConsumer trong kiến trúc Share Groups

Kafka Share Group là một nhóm consumer cùng chia sẻ công việc đọc record. Tất cả instance có cùng **group.id** sẽ tham gia cùng một share group. Khi nhiều consumer trong nhóm subscribe cùng topic, Kafka có thể giao các record của cùng partition cho những member khác nhau.

Điều này khác consumer group truyền thống:

| Tiêu chí | Consumer group | Share group |
|---|---|---|
| Phân phối partition | Một partition được gán cho tối đa một consumer member tại một thời điểm | Nhiều member có thể cùng xử lý record từ một partition |
| Đơn vị phối hợp | Partition assignment và committed offset | Record acquisition và acknowledgement |
| Số consumer so với partition | Consumer dư có thể không nhận partition | Consumer có thể nhiều hơn số partition |
| Xử lý lỗi | Thường retry theo offset hoặc chuyển DLT bằng ứng dụng | Có ACCEPT, RELEASE, REJECT và acquisition lock |
| Ordering | Có thể duy trì thứ tự xử lý trong partition nếu xử lý tuần tự | Không bảo đảm thứ tự hoàn tất xử lý giữa các member |
| Use case | Xử lý stream cần thứ tự và state theo partition | Công việc độc lập theo từng record, queue-like workload |

Ví dụ, topic có 3 partition nhưng có 8 worker xử lý ảnh. Với consumer group truyền thống, tại một thời điểm chỉ tối đa 3 consumer nhận partition. Với share group, nhiều worker có thể cùng nhận record từ các partition đó, giúp tận dụng worker khi mỗi record là một tác vụ độc lập.

Share group không biến Kafka thành một queue đơn giản. Record vẫn nằm trong topic log, có partition và offset; broker quản lý trạng thái acquisition/acknowledgement riêng cho share group. Một topic có thể được đọc độc lập bởi nhiều share group và nhiều consumer group.

### 1.1. Vai trò của KafkaShareConsumer

KafkaShareConsumer nằm trong package:

~~~java
org.apache.kafka.clients.consumer.KafkaShareConsumer
~~~

Client cung cấp các thao tác chính:

| API | Vai trò |
|---|---|
| Constructor | Tạo consumer từ Properties hoặc Map cấu hình |
| subscribe(topics) | Đăng ký danh sách topic muốn nhận |
| poll(timeout) | Tham gia group và lấy các record đã được broker acquire |
| acknowledge(record, type) | Xác nhận kết quả xử lý của một record trong explicit mode |
| commitSync() | Gửi các acknowledgement đang chờ tới Kafka và chờ kết quả |
| commitAsync() | Gửi acknowledgement bất đồng bộ |
| close() | Commit acknowledgement đang chờ theo semantics của mode, giải phóng record còn lại và rời group |
| wakeup() | Đánh thức poll đang chờ để shutdown từ thread khác |

KafkaShareConsumer không phải KafkaConsumer với một tên khác. Nó thực hiện giao thức share group và dùng acknowledgement thay cho cách quản lý offset tuần tự quen thuộc của consumer group.

### 1.2. Mốc phiên bản cần biết

Share Groups được giới thiệu qua KIP-932:

- Apache Kafka 4.1 cung cấp Share Groups ở trạng thái preview, chưa bật mặc định. Cần nâng feature level của cluster lên share.version=1 để thử nghiệm.
- Apache Kafka 4.2 đưa Share Groups vào trạng thái production-ready.
- Apache Kafka 4.4 bổ sung các khả năng như renewal acknowledgement và dead-letter queue cho Share Groups khi cluster bật share.version=2.

API client và broker phải hỗ trợ cùng các tính năng ứng dụng sử dụng. Client mới kết nối broker cũ có thể nhận UnsupportedVersionException nếu gọi API chưa được broker hỗ trợ. Luôn kiểm tra release note và API reference của đúng phiên bản đang triển khai.

Với Kafka 4.1, có thể bật feature preview bằng lệnh:

~~~bash
bin/kafka-features.sh --bootstrap-server localhost:9092 upgrade --feature share.version=1
~~~

Không chạy lệnh nâng feature trên production chỉ để thử code. Đây là thay đổi feature level của cluster; cần kiểm tra compatibility, quy trình nâng cấp và kế hoạch vận hành trước khi thực hiện.

## 2. Vòng đời nhận record

Một share consumer thường thực hiện chu trình:

1. Tạo KafkaShareConsumer với bootstrap server, group ID và deserializer.
2. Gọi subscribe() với topic cần đọc.
3. Gọi poll() để tham gia share group và nhận record.
4. Xử lý record theo nghiệp vụ.
5. Xác nhận kết quả xử lý bằng acknowledgement.
6. Commit acknowledgement hoặc để poll tiếp theo commit theo mode.
7. Lặp lại cho đến khi ứng dụng shutdown.

~~~mermaid
flowchart TD
    A[Create KafkaShareConsumer] --> B[subscribe topics]
    B --> C[poll]
    C --> D{Có record?}
    D -->|Không| C
    D -->|Có| E[Process each record]
    E --> F{Kết quả}
    F -->|Thành công| G[ACCEPT]
    F -->|Lỗi tạm thời| H[RELEASE]
    F -->|Lỗi vĩnh viễn| I[REJECT]
    G --> J[Commit acknowledgements]
    H --> J
    I --> J
    J --> C
~~~

Điểm khác biệt quan trọng là broker chỉ giao một record cho một member khi record đó đang được acquisition lock. Nếu member xử lý xong và ACCEPT, record được xác nhận thành công. Nếu RELEASE hoặc lock hết hạn, record có thể được giao lại cho member khác.

## 3. Cấu hình KafkaShareConsumer

Ví dụ cấu hình cơ bản:

~~~java
Properties props = new Properties();
props.put("bootstrap.servers", "localhost:9092");
props.put("group.id", "image-processing-share");
props.put("key.deserializer",
        "org.apache.kafka.common.serialization.StringDeserializer");
props.put("value.deserializer",
        "org.apache.kafka.common.serialization.StringDeserializer");
~~~

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| bootstrap.servers | Địa chỉ broker để client bootstrap |
| group.id | Định danh share group; các consumer cùng giá trị sẽ chia sẻ công việc |
| key.deserializer | Deserialize key |
| value.deserializer | Deserialize value |
| share.acknowledgement.mode | implicit hoặc explicit |
| share.acquire.mode | Chọn batch_optimized hoặc record_limit ở các phiên bản hỗ trợ |
| max.poll.records | Số record tối đa theo acquire mode record_limit |
| max.poll.interval.ms | Khoảng thời gian tối đa giữa các lần gọi poll |
| share.auto.offset.reset | Vị trí khởi tạo share-partition khi group chưa có tiến độ: latest (mặc định), earliest hoặc by_duration |

Consumer phải luôn được đóng bằng close(). Có thể dùng try-with-resources để bảo đảm close được gọi khi thoát vòng lặp hoặc có exception.

### 3.1. group.id là share group ID

Hai consumer cùng group.id sẽ tham gia cùng một share group. Consumer có group.id khác sẽ tạo nhóm độc lập và nhận bản sao công việc riêng của topic.

Ví dụ:

~~~text
image-processing-share
    ├── consumer-instance-1
    ├── consumer-instance-2
    └── consumer-instance-3

fraud-detection-share
    ├── consumer-instance-4
    └── consumer-instance-5
~~~

Hai share group đều có thể đọc topic đầu vào, nhưng mỗi group quản lý trạng thái giao nhận độc lập. Đừng dùng group ID giống nhau giữa hai workload không liên quan vì chúng sẽ vô tình chia sẻ record.

### 3.2. Acquisition lock

Khi poll trả về record, broker đặt acquisition lock cho record đó. Trong thời gian lock còn hiệu lực, record không được giao cho member khác. Theo mặc định, lock duration là 30 giây; group có thể điều chỉnh qua cấu hình **share.record.lock.duration.ms**, trong giới hạn broker cho phép.

Nếu consumer:

- ACCEPT: xác nhận record đã xử lý thành công.
- RELEASE: trả record để có thể được giao lại.
- REJECT: xác nhận record không thể xử lý và không yêu cầu giao lại.
- Không gửi acknowledgement: broker tự giải phóng lock khi hết hạn.

Broker cũng giới hạn số record đang được acquire trên mỗi topic-partition trong một share group. Khi chạm giới hạn, poll có thể tạm thời không nhận thêm record cho partition đó cho đến khi một số acquisition được giải phóng.

Acquisition lock không phải distributed lock để bảo vệ side effect bên ngoài. Nếu processing vượt lock duration, record có thể được giao cho consumer khác trong khi worker cũ vẫn đang chạy. Vì vậy, cần đặt thời gian xử lý phù hợp, dùng idempotency và chỉ dùng renewal khi có nhu cầu thực sự.

## 4. Vòng lặp poll cơ bản với implicit acknowledgement

Nếu không cấu hình share.acknowledgement.mode, share consumer sử dụng implicit acknowledgement.

Trong mode này:

- Gọi poll() tiếp theo sẽ implicit acknowledge các record đã trả về từ poll trước và gửi acknowledgement bất đồng bộ.
- Gọi commitSync() hoặc commitAsync() sẽ implicit acknowledge toàn bộ record của poll gần nhất.
- Gọi close() sẽ giải phóng các record còn acquired mà chưa được acknowledge.

Ví dụ:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaShareConsumer;

public class ImplicitShareConsumerExample {

    public static void main(String[] args) {
        Properties props = new Properties();
        props.put("bootstrap.servers", "localhost:9092");
        props.put("group.id", "image-processing-share");
        props.put("key.deserializer",
                "org.apache.kafka.common.serialization.StringDeserializer");
        props.put("value.deserializer",
                "org.apache.kafka.common.serialization.StringDeserializer");

        try (KafkaShareConsumer<String, String> consumer =
                     new KafkaShareConsumer<>(props)) {
            consumer.subscribe(List.of("images-to-process"));

            while (!Thread.currentThread().isInterrupted()) {
                ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofMillis(1000));

                for (ConsumerRecord<String, String> record : records) {
                    processImage(record.key(), record.value());
                }
            }
        }
    }

    private static void processImage(String imageId, String payload) {
        // Business processing.
    }
}
~~~

Ví dụ này phù hợp khi toàn bộ batch được xem là thành công. Nó không thích hợp nếu ứng dụng cần quyết định ACCEPT, RELEASE hoặc REJECT riêng cho từng record.

### 4.1. Rủi ro của implicit acknowledgement

Giả sử một poll trả về 10 record. 8 record xử lý thành công, record thứ 9 gặp lỗi tạm thời. Nếu ứng dụng bắt exception, ghi log rồi gọi poll tiếp theo, toàn bộ record của poll trước được implicit acknowledge như đã xử lý thành công.

Điều này có thể làm mất cơ hội retry cho record thứ 9. Nếu ứng dụng cần xử lý lỗi theo từng record, hãy chọn explicit acknowledgement.

Implicit mode cũng có thể phù hợp với batch mà ứng dụng có thể retry toàn batch bằng logic riêng. Tuy nhiên, cần hiểu rõ rằng Kafka không tự biết record nào trong batch đã xử lý thành công.

## 5. Explicit acknowledgement theo từng record

Để xác nhận từng record riêng biệt, cấu hình:

~~~java
props.put("share.acknowledgement.mode", "explicit");
~~~

Trong explicit mode:

1. Mỗi record từ poll phải được acknowledge bằng acknowledge(record, type).
2. Phải acknowledge tất cả record đã nhận trước khi gọi poll tiếp theo.
3. Nếu gọi poll khi vẫn còn record chưa acknowledge, client ném IllegalStateException.
4. acknowledge() chỉ cập nhật trạng thái local trong consumer.
5. commitSync(), commitAsync() hoặc poll tiếp theo mới gửi acknowledgement tới Kafka.

### 5.1. Ba loại acknowledgement chính

| AcknowledgeType | Ý nghĩa | Khi sử dụng |
|---|---|---|
| ACCEPT | Xử lý thành công | Record đã tạo side effect nghiệp vụ thành công |
| RELEASE | Xử lý chưa thành công, cho phép giao lại | Lỗi tạm thời như timeout, dependency unavailable hoặc rate limit |
| REJECT | Record không xử lý được và không giao lại | Payload sai vĩnh viễn, vi phạm contract hoặc lỗi nghiệp vụ không thể retry |

Không dùng REJECT cho mọi exception. Nếu database tạm thời unavailable, REJECT sẽ loại bỏ khả năng giao lại record. Ngược lại, RELEASE vô hạn cho payload sai có thể tạo vòng lặp lỗi; cần delivery limit và dead-letter strategy.

### 5.2. Vòng lặp explicit acknowledgement

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.AcknowledgeType;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaShareConsumer;

public class ExplicitShareConsumerExample {

    public static void main(String[] args) {
        Properties props = new Properties();
        props.put("bootstrap.servers", "localhost:9092");
        props.put("group.id", "payment-command-share");
        props.put("key.deserializer",
                "org.apache.kafka.common.serialization.StringDeserializer");
        props.put("value.deserializer",
                "org.apache.kafka.common.serialization.StringDeserializer");
        props.put("share.acknowledgement.mode", "explicit");

        try (KafkaShareConsumer<String, String> consumer =
                     new KafkaShareConsumer<>(props)) {
            consumer.subscribe(List.of("payment-commands"));

            while (!Thread.currentThread().isInterrupted()) {
                ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofMillis(1000));

                for (ConsumerRecord<String, String> record : records) {
                    try {
                        processPayment(record.key(), record.value());
                        consumer.acknowledge(record, AcknowledgeType.ACCEPT);
                    } catch (TransientProcessingException ex) {
                        consumer.acknowledge(record, AcknowledgeType.RELEASE);
                    } catch (InvalidPaymentCommandException ex) {
                        consumer.acknowledge(record, AcknowledgeType.REJECT);
                    }
                }

                var commitResults = consumer.commitSync();
                commitResults.forEach((partition, error) ->
                        error.ifPresent(ex ->
                                System.err.println(
                                        "Acknowledgement commit failed for "
                                                + partition + ": " + ex)));
            }
        }
    }

    private static void processPayment(String key, String command) {
        // Business processing.
    }
}
~~~

Đây là skeleton minh họa. Trong ứng dụng thật, hãy định nghĩa exception theo domain và xử lý cả lỗi ngoài dự kiến. Nếu không thể xác định record đã tạo side effect hay chưa, cần idempotency key trước khi retry.

### 5.3. Vì sao phải commit acknowledgement?

Lệnh acknowledge(record, ACCEPT) chưa đồng nghĩa broker đã ghi nhận kết quả. Nó chỉ cập nhật trạng thái acknowledgement trong client. commitSync() gửi trạng thái này tới Kafka và chờ kết quả.

Nếu commit thất bại hoặc kết quả không rõ do mất kết nối, record có thể được giao lại. Do đó, side effect nghiệp vụ phải idempotent. Không dựa vào việc gọi acknowledge một lần để kết luận record chắc chắn sẽ không xuất hiện lần nữa.

commitSync() trả về kết quả theo topic-partition. Mỗi phần tử có thể chứa exception nếu acknowledgement của partition đó không thành công. Ứng dụng production cần kiểm tra kết quả, phát metric và có chiến lược phục hồi; không bỏ qua map kết quả.

## 6. Xử lý lỗi và retry

Share group phân biệt rõ lỗi tạm thời và lỗi vĩnh viễn.

### 6.1. Lỗi tạm thời

Ví dụ:

- Database đang bảo trì.
- API downstream trả HTTP 429 hoặc 503.
- Network timeout.
- Service phụ thuộc chưa sẵn sàng.

Hướng xử lý:

1. Ghi log có event ID, topic, partition, offset và nguyên nhân.
2. Gọi RELEASE để record có thể được giao lại.
3. Dùng retry/backoff ở business layer nếu cần, nhưng phải nằm trong acquisition lock hợp lý.
4. Theo dõi delivery count để phát hiện record liên tục thất bại.

### 6.2. Lỗi vĩnh viễn

Ví dụ:

- Payload không đúng schema.
- Thiếu trường bắt buộc.
- Event type không được hỗ trợ.
- Command vi phạm quy tắc nghiệp vụ không thể sửa bằng retry.

Hướng xử lý:

1. Ghi nhận lỗi và metadata của record.
2. Chuyển record vào dead-letter workflow nếu cấu hình hỗ trợ.
3. Chỉ REJECT sau khi đã bảo đảm record lỗi được lưu/quan sát theo yêu cầu vận hành.

### 6.3. Delivery count

Share group đếm số lần record được giao. Trong Kafka 4.1, broker config **group.share.delivery.count.limit** có mặc định 5 lần và giới hạn trong khoảng được broker hỗ trợ. Từ Kafka 4.3, group config tương ứng là **share.delivery.count.limit**; mặc định trong Kafka 4.4 vẫn là 5 lần.

ConsumerRecord cung cấp **deliveryCount()** dưới dạng Optional<Short> khi thông tin này có sẵn:

~~~java
record.deliveryCount().ifPresent(count ->
        metrics.recordDeliveryAttempt(record.topic(), count));
~~~

Delivery count giúp nhận biết record bị giao lại nhiều lần. Không phải mọi ConsumerRecord đều có delivery count; hãy xử lý trường hợp Optional rỗng.

### 6.4. Dead-letter queue

Kafka 4.1/4.2 không nên được hiểu là tự động có DLQ tích hợp cho mọi share group. Ứng dụng có thể tự publish record lỗi sang một topic riêng rồi REJECT record gốc, nhưng phải xử lý idempotency giữa việc ghi DLQ và acknowledgement.

Kafka 4.4 hỗ trợ DLQ cho share group khi feature share.version được nâng lên 2. Các dynamic config liên quan gồm:

- errors.deadletterqueue.topic.name: tên topic DLQ.
- errors.deadletterqueue.auto.create.topics.enable: có tự tạo topic DLQ hay không.
- errors.deadletterqueue.group.enable: bật cấu hình DLQ cho topic đích khi không tự tạo.
- errors.deadletterqueue.topic.name.prefix: prefix được phép của DLQ topic.
- errors.deadletterqueue.copy.record.enable: có sao chép payload gốc vào DLQ record hay chỉ metadata.

Trong Kafka 4.4, record bị REJECT hoặc RELEASE vượt quá delivery count có thể đủ điều kiện vào DLQ khi feature/config đã bật. DLQ không tự thay thế việc thiết kế quy trình sửa dữ liệu và replay.

Nếu errors.deadletterqueue.topic.name để trống, group không có DLQ topic. Mặc định DLQ record chỉ chứa metadata nguồn; muốn sao chép payload gốc cần bật errors.deadletterqueue.copy.record.enable. Khi không bật tự tạo topic, phải tạo topic và đặt dynamic config errors.deadletterqueue.group.enable=true trên topic đích theo hướng dẫn của đúng phiên bản Kafka.

## 7. Acquisition lock và thời gian xử lý

Acquisition lock mặc định là 30 giây. Khi hết thời gian, broker có thể giao record cho consumer khác nếu record chưa được acknowledge thành công.

Ví dụ:

1. Consumer A nhận record lúc 10:00:00.
2. A gọi API ngoài và bị treo.
3. Lock hết hạn lúc 10:00:30.
4. Consumer B có thể nhận lại record.
5. A vẫn tiếp tục xử lý và có thể tạo side effect sau khi B đã bắt đầu.

Điều này tạo nguy cơ xử lý đồng thời. Vì vậy:

- Thiết kế business handler idempotent.
- Đặt timeout của API downstream nhỏ hơn acquisition lock khi có thể.
- Chọn batch size phù hợp với thời gian xử lý.
- Không giữ record acquired trong khi chờ công việc không có giới hạn.
- Theo dõi thời gian xử lý p95/p99 so với lock duration.

### 7.1. Cấu hình lock duration

Group có thể điều chỉnh:

~~~properties
share.record.lock.duration.ms=30000
~~~

Broker giới hạn giá trị tối đa bằng cấu hình **group.share.max.record.lock.duration.ms**. Giá trị thực tế phải nằm trong giới hạn broker. Tăng lock duration giúp xử lý lâu hơn nhưng giữ record lâu hơn khi consumer chết, làm chậm cơ hội giao lại.

### 7.2. Renewal acknowledgement trong Kafka 4.4

Kafka 4.4 bổ sung **AcknowledgeType.RENEW**. Khi xử lý lâu hơn acquisition lock, ứng dụng dùng explicit acknowledgement, tiếp tục gọi poll đều đặn và gửi RENEW cho record còn đang xử lý để gia hạn acquisition lock.

Group config **share.renew.acknowledge.enable** điều khiển khả năng này và mặc định được bật trong Kafka 4.4.

Đây là kỹ thuật nâng cao:

- Chỉ dùng khi thời gian xử lý thực sự vượt lock duration.
- Cần poll đều để duy trì liveness và renewal.
- Cần theo dõi kết quả acknowledgement commit.
- Renewal có thể làm chậm tiến độ giao record cho member khác.
- Nếu partition leadership thay đổi hoặc kết nối tới leader mất, delivery attempt hiện tại có thể kết thúc.

RENEW không có trong API Kafka 4.1; kiểm tra version client/broker trước khi dùng.

Chỉ dùng RENEW khi thời gian xử lý thực sự có thể vượt lock duration. Với công việc hoàn thành nhanh, ACCEPT/RELEASE/REJECT đơn giản hơn và giảm thời gian record bị giữ.

## 8. Batching và max.poll.records

Share consumer được tối ưu để nhận record theo batch. Ở Kafka 4.4, thuộc tính **share.acquire.mode** có hai chế độ:

| Mode | Hành vi |
|---|---|
| batch_optimized | Mặc định; căn theo batch boundary, số record trả về có thể vượt max.poll.records và client có thể prefetch |
| record_limit | Giới hạn số record trả về theo max.poll.records và không prefetch; đổi lại throughput có thể thấp hơn |

Ví dụ cấu hình kiểm soát batch:

~~~properties
share.acquire.mode=record_limit
max.poll.records=50
share.acknowledgement.mode=explicit
~~~

Chọn record_limit nếu mỗi record xử lý lâu hoặc cần kiểm soát chính xác số record đang giữ. Chọn batch_optimized nếu xử lý nhanh và muốn tận dụng batch throughput. Tính năng share.acquire.mode phụ thuộc phiên bản client; không mặc định rằng Kafka 4.1 có cùng behavior như Kafka 4.4.

## 9. Poll loop và liveness

Share consumer phải tiếp tục gọi poll để duy trì membership. Client gửi heartbeat định kỳ trong nền, nhưng nếu khoảng thời gian giữa hai lần poll vượt **max.poll.interval.ms**, consumer có thể chủ động rời group.

Ví dụ lỗi:

~~~java
while (true) {
    ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofSeconds(1));

    // Xử lý 20 phút trong cùng thread.
    processAll(records);
}
~~~

Nếu processAll mất quá lâu, ứng dụng có thể vượt max.poll.interval.ms. Ngoài ra, acquisition lock của record có thể hết hạn trước khi xử lý xong.

Thiết kế phù hợp:

- Giới hạn số record mỗi poll.
- Giới hạn thời gian xử lý một batch.
- Dùng explicit acknowledgement khi từng record có kết quả khác nhau.
- Nếu cần xử lý song song, chỉ chuyển business work sang worker pool có bounded queue; poll loop vẫn phải tiếp tục chạy và acknowledgement phải được điều phối an toàn.
- Không gọi KafkaShareConsumer từ nhiều thread đồng thời vì client không thread-safe.

### 9.1. Consumer không thread-safe

Chỉ một thread sở hữu KafkaShareConsumer và thực hiện subscribe, poll, acknowledge, commit, close. Nếu cần shutdown từ thread khác, gọi wakeup() là thao tác được hỗ trợ an toàn để ngắt poll đang chờ.

Không dùng chung một KafkaShareConsumer instance cho nhiều worker thread. Nếu cần concurrency cao, thường tạo nhiều consumer instance cùng group.id và để broker chia sẻ record.

### 9.2. Shutdown an toàn

Khi ứng dụng dừng:

1. Ngừng nhận công việc mới theo cơ chế điều phối ứng dụng.
2. Hoàn thành hoặc dừng xử lý record đang giữ theo deadline.
3. Gửi acknowledgement phù hợp cho record đã xử lý.
4. Commit acknowledgement.
5. Gọi close() để rời group và giải phóng resource.

Nếu shutdown đột ngột, acquisition lock sẽ hết hạn và record có thể được giao lại. Consumer handler phải idempotent để lần giao tiếp theo không tạo side effect trùng.

## 10. Vòng lặp nhận bản ghi hoàn chỉnh

Một poll loop production nên có các phần:

- Subscribe topic.
- Poll định kỳ.
- Kiểm tra record metadata.
- Xử lý từng record.
- Chọn ACCEPT, RELEASE hoặc REJECT.
- Commit acknowledgement và kiểm tra kết quả.
- Theo dõi lỗi và shutdown.

Ví dụ dưới đây dùng explicit mode:

~~~java
import java.time.Duration;
import java.util.List;

import org.apache.kafka.clients.consumer.AcknowledgeType;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaShareConsumer;
import org.apache.kafka.common.errors.WakeupException;

public final class ShareConsumerRunner implements Runnable {

    private final KafkaShareConsumer<String, String> consumer;
    private volatile boolean stopping;

    public ShareConsumerRunner(KafkaShareConsumer<String, String> consumer) {
        this.consumer = consumer;
    }

    @Override
    public void run() {
        try {
            consumer.subscribe(List.of("orders-to-enrich"));

            while (!stopping) {
                ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofMillis(1000));

                for (ConsumerRecord<String, String> record : records) {
                    try {
                        enrichOrder(record.key(), record.value());
                        consumer.acknowledge(record, AcknowledgeType.ACCEPT);
                    } catch (TemporaryDependencyException ex) {
                        consumer.acknowledge(record, AcknowledgeType.RELEASE);
                    } catch (InvalidOrderEventException ex) {
                        writeApplicationDlq(record, ex);
                        consumer.acknowledge(record, AcknowledgeType.REJECT);
                    }
                }

                var results = consumer.commitSync();
                results.forEach((partition, error) ->
                        error.ifPresent(ex ->
                                reportCommitFailure(partition, ex)));
            }
        } catch (WakeupException ex) {
            if (!stopping) {
                throw ex;
            }
        } finally {
            consumer.close();
        }
    }

    public void shutdown() {
        stopping = true;
        consumer.wakeup();
    }

    private void enrichOrder(String key, String value) {
        // Business logic.
    }

    private void writeApplicationDlq(
            ConsumerRecord<String, String> record,
            Exception error) {
        // Publish to a durable DLQ and wait for its acknowledgement.
    }

    private void reportCommitFailure(Object partition, Exception error) {
        // Log and emit metrics.
    }
}
~~~

Đây là skeleton minh họa; khi dùng writeApplicationDlq(), chỉ REJECT record gốc sau khi publish DLQ thành công. Nếu publish DLQ thất bại, RELEASE để có thể thử lại. Việc publish DLQ cũng cần idempotency vì producer có thể gửi thành công nhưng ứng dụng không nhận được acknowledgement.

Trong production, nên xử lý WakeupException riêng: bỏ qua khi stopping=true và ném lại khi đây là lỗi bất ngờ. Cũng cần đảm bảo close chỉ được thực hiện sau khi poll loop kết thúc, tránh đóng consumer đồng thời với thao tác khác.

## 11. Ordering và xử lý song song

Share group tối ưu việc chia sẻ công việc, không tối ưu strict ordering.

Kafka đảm bảo record trả về trong một ConsumerRecords batch của cùng topic-partition có thứ tự offset tăng dần. Tuy nhiên, nhiều member có thể xử lý record khác nhau trong cùng partition; thời gian xử lý và acknowledgement có thể hoàn tất theo thứ tự khác nhau.

Ví dụ:

| Offset | Consumer | Thời gian xử lý | Hoàn tất |
|---:|---|---:|---|
| 100 | A | 8 giây | 10:00:08 |
| 101 | B | 1 giây | 10:00:01 |
| 102 | C | 3 giây | 10:00:03 |

Consumer B có thể hoàn tất offset 101 trước A hoàn tất offset 100. Nếu event là các trạng thái tuần tự của cùng một order, điều này có thể gây sai nghiệp vụ.

Share group phù hợp với record độc lập như xử lý ảnh, gửi thông báo, kiểm tra file hoặc chạy tác vụ có thể retry riêng. Nếu cần xử lý event theo thứ tự của key, consumer group truyền thống thường là lựa chọn phù hợp hơn.

Nếu vẫn cần dùng share group, ứng dụng phải bổ sung sequence/version, idempotency và cơ chế kiểm soát thứ tự ở domain. Cách đó tăng độ phức tạp và cần được kiểm thử kỹ.

## 12. Transactional records

Share group có cấu hình isolation level ở cấp group:

| Giá trị | Hành vi |
|---|---|
| read_uncommitted | Nhận cả record transactional đã commit hoặc bị abort cùng record non-transactional |
| read_committed | Chỉ nhận record non-transactional và transactional đã commit; tiến độ bị giới hạn bởi last stable offset |

Trong Kafka 4.1, read_committed chưa được hỗ trợ cho share group. Kafka 4.4 hỗ trợ cấu hình group.share.isolation.level với read_committed hoặc read_uncommitted.

Nếu share group dùng read_committed, một transaction đang mở có thể giữ last stable offset lại và chặn tiến độ đọc phía sau transaction đó. Cấu hình isolation level áp dụng cho toàn share group, không phải riêng một consumer member.

## 13. Quản lý share group bằng CLI

Kafka cung cấp công cụ **kafka-share-groups.sh** để xem và quản lý share group.

Khi thử nghiệm trên Kafka 4.1, bật feature bằng share.version=1. Với Kafka 4.4, DLQ cho share group yêu cầu nâng share.version lên 2 và cấu hình DLQ tương ứng.

Liệt kê share group:

~~~bash
bin/kafka-share-groups.sh --bootstrap-server localhost:9092 --list
~~~

Xem offset/state của một group:

~~~bash
bin/kafka-share-groups.sh --bootstrap-server localhost:9092 --describe --group image-processing-share
~~~

Xem members:

~~~bash
bin/kafka-share-groups.sh --bootstrap-server localhost:9092 --describe --group image-processing-share --members
~~~

Xem trạng thái tổng quan:

~~~bash
bin/kafka-share-groups.sh --bootstrap-server localhost:9092 --describe --group image-processing-share --state
~~~

Xóa offset của một topic trong share group:

~~~bash
bin/kafka-share-groups.sh --bootstrap-server localhost:9092 --delete-offsets --group image-processing-share --topic images-to-process
~~~

Xóa share group:

~~~bash
bin/kafka-share-groups.sh --bootstrap-server localhost:9092 --delete --group image-processing-share
~~~

Chỉ xóa được share group không còn active member. Admin client cần quyền DESCRIBE trên các topic mà group sử dụng. Xóa share group hoặc offsets là thao tác quản trị ảnh hưởng tiến độ giao record; phải xác nhận workload đã dừng và có kế hoạch xử lý record còn lại.

## 14. Security và vận hành

KafkaShareConsumer cần quyền:

- READ trên topic được subscribe.
- Quyền group phù hợp để tham gia share group.
- DESCRIBE topic nếu công cụ quản trị cần xem metadata.

Không cấp quyền rộng cho mọi consumer. Tách principal theo service và share group, dùng TLS/SASL theo chính sách cluster và quản lý secret qua secret store.

Trong cluster KRaft, share group coordinator quản lý trạng thái share group. Kafka sử dụng internal topic **__share_group_state** để lưu trạng thái. Không xóa hoặc sửa internal topic này bằng tay. Trong môi trường lab một broker, kiểm tra replication factor/min ISR của share coordinator state topic trước khi kích hoạt share group; production nên thiết kế replication phù hợp với số broker và availability requirement.

Với lab chỉ có một broker, tài liệu nâng cấp Kafka 4.2 nêu cần đặt hai broker config sau về 1 trước khi bắt đầu dùng share group:

~~~properties
share.coordinator.state.topic.replication.factor=1
share.coordinator.state.topic.min.isr=1
~~~

Chỉ dùng giá trị này cho lab một broker. Production cần replication factor và min ISR phù hợp với cluster.

## 15. Monitoring và troubleshooting

Theo dõi:

| Nhóm | Chỉ số cần quan sát | Ý nghĩa |
|---|---|---|
| Consumer | Poll rate, poll latency, processing latency | Liveness và throughput |
| Acknowledgement | ACCEPT/RELEASE/REJECT count, commit failures | Kết quả xử lý và retry |
| Delivery | Delivery count distribution, lock expiry | Record bị giao lại nhiều lần |
| Group | Member count, group state, active share sessions | Tình trạng share group |
| Broker | Share coordinator errors, state topic availability | Khả năng quản lý acquisition/ack |
| Topic | Produce rate, partition throughput, retention | Tải và khả năng lưu record |
| Business | Success rate, permanent failure, duplicate side effects | Kết quả nghiệp vụ thực tế |

### 15.1. Poll trả về rỗng liên tục

Kiểm tra:

1. Consumer đã subscribe đúng topic chưa?
2. Topic có record mới và offset reset policy phù hợp không?
3. Feature share.version đã được bật trên broker chưa?
4. Principal có READ và group permission không?
5. Share group có đang ở trạng thái hợp lệ không?
6. Có quá nhiều record đang acquired trên partition khiến broker tạm ngừng giao thêm không?

### 15.2. IllegalStateException khi poll

Trong explicit mode, lỗi này thường xuất hiện khi ứng dụng gọi poll tiếp theo trong khi vẫn còn record từ poll trước chưa được acknowledge. Hãy bảo đảm mọi record đều được ACCEPT, RELEASE hoặc REJECT trước lần poll tiếp theo.

### 15.3. Record bị giao lại liên tục

Kiểm tra:

- Business processing có vượt acquisition lock duration không?
- Ứng dụng có RELEASE quá thường xuyên không?
- Downstream dependency có timeout/rate limit không?
- Delivery count có chạm giới hạn không?
- Acknowledgement commit có thất bại không?
- Consumer có crash sau side effect nhưng trước commit acknowledgement không?

Giải pháp có thể gồm tăng timeout phù hợp, giảm batch, cải thiện downstream dependency, thêm idempotency và cấu hình DLQ.

### 15.4. Consumer rời group

Kiểm tra max.poll.interval.ms, thời gian xử lý batch và heartbeat/session timeout. Đảm bảo poll được gọi đều đặn và không chặn consumer thread bằng tác vụ dài.

### 15.5. Side effect bị lặp

Share group cho phép record được giao lại khi lock hết hạn, RELEASE, consumer crash hoặc acknowledgement commit không thành công. Hãy dùng event ID/business key để deduplicate ở hệ thống đích. Không coi ACCEPT là bảo đảm side effect đã xảy ra đúng một lần end-to-end.

## 16. Khi nào dùng Share Group?

| Nhu cầu | Gợi ý |
|---|---|
| Mỗi record là một tác vụ độc lập | Share group |
| Nhiều worker cần chia sẻ cùng partition | Share group |
| Consumer có thời gian xử lý không đồng đều | Share group, có lock/retry phù hợp |
| Cần ACCEPT/RELEASE/REJECT từng record | Share group |
| Cần ordering nghiêm ngặt theo partition/key | Consumer group |
| Xử lý stateful stream theo thứ tự offset | Consumer group hoặc Kafka Streams |
| Muốn scale worker vượt số partition | Share group |
| Cần retry riêng cho từng record | Share group |

Share group phù hợp với queue-like workload, trong khi consumer group phù hợp với ordered stream processing. Việc lựa chọn phải dựa vào semantics nghiệp vụ, không chỉ dựa vào số consumer cần chạy.

## 17. Bài thực hành và tự kiểm tra

### Thực hành A — Vòng lặp poll cơ bản

1. Chuẩn bị Kafka cluster hỗ trợ Share Groups.
2. Bật feature share.version theo phiên bản broker trong môi trường lab.
3. Tạo topic images-to-process và ghi một số record.
4. Viết KafkaShareConsumer với group.id image-processing-share.
5. Subscribe topic và gọi poll trong vòng lặp.
6. Chạy hai consumer cùng group.id và quan sát record được chia sẻ.
7. So sánh với hai consumer group truyền thống.

### Thực hành B — Explicit acknowledgement

1. Cấu hình share.acknowledgement.mode=explicit.
2. Xử lý record thành công và gọi ACCEPT.
3. Cố tình tạo lỗi tạm thời và gọi RELEASE.
4. Tạo payload sai vĩnh viễn và gọi REJECT.
5. Gọi commitSync và kiểm tra kết quả theo topic-partition.
6. Thử gọi poll khi còn record chưa acknowledge và quan sát IllegalStateException.

### Thực hành C — Acquisition lock và retry

1. Cấu hình lock duration ngắn trong cluster lab.
2. Cố tình làm consumer xử lý lâu hơn lock duration.
3. Chạy consumer thứ hai cùng share group.
4. Quan sát record có thể được giao lại khi lock hết hạn.
5. Thêm idempotency key vào business handler.
6. Thử RELEASE nhiều lần và quan sát delivery count.

### Thực hành D — Vận hành share group

1. Dùng kafka-share-groups.sh --list để xem group.
2. Dùng --describe --members để kiểm tra member.
3. Dùng --describe --state để kiểm tra trạng thái group.
4. Dừng một consumer và quan sát member thay đổi.
5. Kiểm tra log và metric khi acknowledgement commit lỗi.
6. Thử shutdown bằng wakeup() và xác nhận close() được gọi.

### Câu hỏi tự kiểm tra

1. KafkaShareConsumer khác KafkaConsumer ở điểm nào?
2. Vì sao nhiều consumer trong share group có thể cùng đọc một partition?
3. group.id có ý nghĩa gì với share group?
4. poll() vừa nhận record vừa duy trì liveness như thế nào?
5. Acquisition lock là gì và điều gì xảy ra khi lock hết hạn?
6. Implicit acknowledgement khác explicit acknowledgement ở đâu?
7. Vì sao phải acknowledge tất cả record trước lần poll tiếp theo trong explicit mode?
8. ACCEPT, RELEASE và REJECT khác nhau như thế nào?
9. Vì sao acknowledge() chưa đồng nghĩa broker đã commit acknowledgement?
10. Delivery count giúp ích gì khi xử lý poison record?
11. Vì sao share group không phù hợp với strict ordering?
12. Khi nào nên dùng RENEW trong Kafka 4.4?
13. Tại sao KafkaShareConsumer không thread-safe?
14. KafkaShareConsumer có bảo đảm exactly-once cho side effect database/API không?
15. Có thể dùng CLI nào để quan sát và xóa share group?

## Kết luận

KafkaShareConsumer cung cấp vòng lặp nhận record cho Share Groups: subscribe, poll, xử lý và acknowledge. Implicit mode xác nhận cả batch theo lần poll/commit; explicit mode cho phép quyết định ACCEPT, RELEASE hoặc REJECT riêng từng record. Acquisition lock và delivery count giúp broker giao lại record khi consumer gặp lỗi, nhưng cũng có thể tạo duplicate nếu xử lý lâu hoặc acknowledgement commit không thành công. Thiết kế đúng cần poll đều, xử lý trong lock duration phù hợp, dùng idempotency, kiểm tra commit result và chọn share group cho workload độc lập theo record; với strict ordering, consumer group truyền thống vẫn là lựa chọn phù hợp hơn.

## Tài liệu tham khảo

- [Apache Kafka 4.4 — KafkaShareConsumer API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/KafkaShareConsumer.html)
- [Apache Kafka 4.4 — AcknowledgeType API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/AcknowledgeType.html)
- [Apache Kafka 4.1 — Design: Share Groups](https://kafka.apache.org/41/design/design/#share-groups)
- [Apache Kafka 4.1 — Basic Kafka Operations: Managing Share Groups](https://kafka.apache.org/41/operations/basic-kafka-operations/)
- [Apache Kafka 4.4 — Release Announcement](https://kafka.apache.org/blog/2026/10/22/apache-kafka-4.4.0-release-announcement/)
- [Apache Kafka — KIP-932: Queues for Kafka](https://cwiki.apache.org/confluence/display/KAFKA/KIP-932%3A+Queues+for+Kafka)
