# max.poll.records, fetch.min.bytes và giới hạn lô đọc

Kafka consumer đọc dữ liệu theo cơ chế pull: client gửi FetchRequest đến broker để lấy record từ các partition được giao. Có nhiều cấu hình ảnh hưởng đến lượng dữ liệu được lấy qua mạng và số record được trả về cho ứng dụng trong mỗi lần gọi poll. Ba cấu hình thường được điều chỉnh cùng nhau là **max.poll.records**, **fetch.min.bytes** và các giới hạn fetch theo byte.

Các cấu hình này có vai trò khác nhau. max.poll.records giới hạn số record ứng dụng nhận trong một lần poll; fetch.min.bytes quy định lượng dữ liệu tối thiểu broker nên tích lũy trước khi trả fetch response; còn max.partition.fetch.bytes và fetch.max.bytes giới hạn kích thước dữ liệu fetch theo partition và theo request. Điều chỉnh đúng giúp cân bằng throughput, latency, bộ nhớ và thời gian xử lý batch.

## 1. Hai giai đoạn: fetch dữ liệu và trả record qua poll

Consumer client có thể fetch dữ liệu từ broker và lưu tạm trong bộ nhớ nội bộ. Khi ứng dụng gọi poll(), client trả các record đã có sẵn theo giới hạn max.poll.records. Vì vậy, số record trả về trong một lần poll và số byte broker gửi trong một FetchResponse là hai giới hạn khác nhau.

~~~mermaid
flowchart LR
    A["Ứng dụng gọi poll()"] --> B["KafkaConsumer"]
    B --> C["Fetcher gửi FetchRequest"]
    C --> D["Broker trả FetchResponse"]
    D --> E["Consumer lưu record đã fetch"]
    E --> F["poll() trả tối đa<br/>max.poll.records"]
    F --> G["Ứng dụng xử lý batch"]
    G --> A
~~~

Consumer có thể nhận nhiều byte qua một hoặc nhiều fetch response, rồi trả dần record cho ứng dụng qua các lần poll. Vì thế, giảm max.poll.records không nhất thiết làm giảm lượng dữ liệu được tải từ broker hoặc lượng bộ nhớ client đang sử dụng.

## 2. max.poll.records giới hạn số record trong một lần poll

**max.poll.records** đặt số record tối đa mà một lần poll() trả về cho ứng dụng. Giá trị mặc định phổ biến của Kafka consumer là 500; hãy kiểm tra cấu hình mặc định của đúng phiên bản client.

Ví dụ:

~~~properties
max.poll.records=200
~~~

Nếu consumer có đủ dữ liệu trong bộ đệm, một lần poll có thể trả tối đa 200 record. Kết quả thực tế có thể ít hơn do lượng dữ liệu sẵn có, số partition được giao, fetch response, thời điểm gọi poll hoặc giới hạn khác.

max.poll.records:

- Giới hạn số record ứng dụng nhận trong một poll.
- Không phải giới hạn số byte của fetch response.
- Không thay đổi trực tiếp fetch size ở tầng network.
- Ảnh hưởng đến số record ứng dụng cần xử lý trước lần poll tiếp theo.

### Khi nào nên giảm max.poll.records?

Giảm giá trị này khi mỗi record cần xử lý lâu, batch lớn gây áp lực bộ nhớ hoặc thời gian xử lý vượt quá giới hạn poll interval. Batch nhỏ giúp ứng dụng hoàn tất công việc nhanh hơn trước lần poll tiếp theo, nhưng có thể tăng overhead gọi poll, commit và xử lý.

### Khi nào nên tăng max.poll.records?

Tăng giá trị này khi xử lý từng record nhẹ, consumer có khả năng xử lý batch hiệu quả và cần giảm overhead trên mỗi record. Batch lớn có thể tăng throughput, nhưng cũng làm thời gian xử lý mỗi poll dài hơn và tăng số record có thể phải đọc lại nếu batch chưa commit.

## 3. fetch.min.bytes và fetch.max.wait.ms

**fetch.min.bytes** là lượng dữ liệu tối thiểu broker nên tích lũy cho một FetchResponse trước khi trả lời. Giá trị mặc định phổ biến là 1 byte, tức broker có thể trả dữ liệu ngay khi có record.

Nếu đặt giá trị cao hơn, broker có thể đợi thêm dữ liệu để gom thành response lớn hơn, giúp tăng hiệu quả throughput khi luồng dữ liệu liên tục.

Ví dụ:

~~~properties
fetch.min.bytes=65536
fetch.max.wait.ms=250
~~~

Trong ví dụ, broker cố gắng tích lũy khoảng 64 KiB dữ liệu trước khi trả response, nhưng không chờ quá 250 ms theo fetch.max.wait.ms. Nếu hết thời gian chờ mà chưa đủ 64 KiB, broker vẫn trả lượng dữ liệu đang có.

Hai cấu hình phối hợp:

| Cấu hình | Vai trò |
|---|---|
| fetch.min.bytes | Ngưỡng byte tối thiểu mà broker cố gắng tích lũy |
| fetch.max.wait.ms | Thời gian tối đa broker chờ ngưỡng byte đó |

Tăng fetch.min.bytes có thể cải thiện kích thước fetch và throughput, nhưng tăng latency khi traffic thấp hoặc không đều. Tăng fetch.max.wait.ms cho phép broker chờ lâu hơn để gom dữ liệu, đồng thời có thể làm consumer nhận record chậm hơn.

fetch.max.wait.ms là thời gian broker chờ cho FetchRequest. Nó khác với timeout truyền vào poll(Duration): poll timeout là thời gian ứng dụng chờ kết quả từ consumer API; fetch wait là chính sách chờ dữ liệu ở broker. Hai giá trị có thể tương tác trong cảm nhận latency nhưng không phải cùng một bộ đếm.

## 4. Giới hạn fetch theo partition và toàn request

Ngoài ngưỡng byte tối thiểu, Kafka consumer còn có các giới hạn kích thước response:

| Cấu hình | Phạm vi | Ý nghĩa |
|---|---|---|
| max.partition.fetch.bytes | Mỗi partition trong một fetch | Số byte tối đa broker nên trả cho một partition |
| fetch.max.bytes | Toàn bộ FetchResponse của một request | Số byte tối đa broker nên trả cho một fetch request |
| fetch.min.bytes | Toàn bộ response | Ngưỡng byte broker cố gắng tích lũy trước khi trả |
| fetch.max.wait.ms | Một FetchRequest | Thời gian tối đa broker chờ dữ liệu đạt fetch.min.bytes |

Giá trị mặc định phổ biến của max.partition.fetch.bytes là 1 MiB và fetch.max.bytes là 50 MiB. Các mặc định có thể thay đổi theo phiên bản Kafka client, vì vậy hãy xác minh trước khi đưa vào cấu hình production.

Ví dụ:

~~~properties
max.partition.fetch.bytes=1048576
fetch.max.bytes=52428800
~~~

Nếu consumer được giao nhiều partition, giới hạn max.partition.fetch.bytes áp dụng cho từng partition; tổng lượng dữ liệu từ nhiều partition có thể lớn hơn giá trị này. fetch.max.bytes giới hạn tổng response của một request, nhưng không phải giới hạn bộ nhớ tuyệt đối của toàn consumer.

### Vì sao broker đôi khi trả nhiều byte hơn giới hạn?

Kafka cần bảo đảm consumer có thể tiến lên. Nếu batch đầu tiên trong partition đầu tiên không rỗng của fetch response lớn hơn max.partition.fetch.bytes hoặc fetch.max.bytes, broker vẫn có thể trả batch đó để consumer không bị kẹt mãi vì batch lớn hơn giới hạn cấu hình.

Vì vậy, các giá trị fetch byte là giới hạn mục tiêu cho response thông thường, không phải rào chắn tuyệt đối trong mọi trường hợp. Cần phối hợp giới hạn phía consumer với kích thước record batch phía producer và giới hạn message của broker/topic.

## 5. Phân biệt ba loại giới hạn

| Câu hỏi | Cấu hình liên quan |
|---|---|
| Một lần poll trả tối đa bao nhiêu record cho code ứng dụng? | max.poll.records |
| Broker nên chờ đến khi có bao nhiêu byte trước khi trả fetch response? | fetch.min.bytes |
| Broker nên chờ tối đa bao lâu để tích lũy dữ liệu? | fetch.max.wait.ms |
| Một partition nên trả tối đa bao nhiêu byte trong fetch? | max.partition.fetch.bytes |
| Một fetch response nên có tổng cộng tối đa bao nhiêu byte? | fetch.max.bytes |

Ví dụ, max.poll.records=100 không có nghĩa broker chỉ gửi 100 record hoặc tối đa 100 KiB. Broker có thể gửi nhiều dữ liệu hơn vào bộ đệm client; consumer sau đó trả tối đa 100 record cho mỗi lần poll.

## 6. max.poll.records liên quan đến max.poll.interval.ms

**max.poll.interval.ms** là khoảng thời gian tối đa được phép giữa hai lần gọi poll() trước khi consumer bị xem là không còn tiến triển trong group. Nếu ứng dụng xử lý batch quá lâu rồi không gọi poll kịp, consumer có thể rời group và partition được rebalance.

Ví dụ:

~~~properties
max.poll.records=500
max.poll.interval.ms=300000
~~~

Nếu mỗi record mất trung bình 800 ms và xử lý tuần tự 500 record, thời gian xử lý ước tính là 400 giây, lớn hơn 5 phút. Consumer có nguy cơ vượt max.poll.interval.ms trước khi gọi poll tiếp.

Đây chỉ là phép ước lượng; thời gian thực tế cần tính cả p95/p99, database/network call, retry nghiệp vụ, GC pause và overhead của ứng dụng. Không nên dùng thời gian trung bình làm căn cứ duy nhất.

Để giảm nguy cơ:

- Giảm max.poll.records để batch hoàn tất trong thời gian cho phép.
- Tối ưu xử lý record hoặc batch ở tầng nghiệp vụ.
- Tách công việc dài khỏi luồng poll nhưng phải tự quản lý backpressure, partition ownership và thứ tự commit.
- Chỉ tăng max.poll.interval.ms khi thời gian xử lý dài là có chủ đích và đã đánh giá tác động rebalance.

Tăng max.poll.interval.ms không tự làm consumer xử lý nhanh hơn. Nó chỉ kéo dài thời gian được phép giữa hai lần poll; nếu ứng dụng treo, việc phát hiện consumer không tiến triển cũng chậm hơn.

## 7. Ước lượng batch size theo thời gian xử lý

Với xử lý tuần tự, có thể ước lượng giới hạn max.poll.records ban đầu bằng ngân sách thời gian:

\[
N_{\max} \approx \frac{T_{\text{poll budget}}}{T_{\text{record,p99}}}
\]

Trong đó:

- T_poll budget là thời gian dành cho xử lý batch, sau khi trừ thời gian poll, commit, overhead ứng dụng và biên an toàn khỏi max.poll.interval.ms.
- T_record,p99 là thời gian xử lý ở percentile 99 của một record.
- N_max là số record tối đa nên xử lý trong một batch theo ước lượng ban đầu.

Ví dụ max.poll.interval.ms là 300 giây. Sau khi trừ 60 giây dự phòng cho các hoạt động khác, ngân sách xử lý còn 240 giây. Nếu p99 mỗi record là 200 ms:

\[
N_{\max} \approx \frac{240000}{200}=1200
\]

Có thể bắt đầu thử với max.poll.records thấp hơn 1200, chẳng hạn 300 hoặc 500, rồi đo thời gian xử lý batch và rebalance thực tế. Công thức chỉ là điểm xuất phát; xử lý theo batch, concurrency và phân bố thời gian record có thể làm kết quả khác đáng kể.

Nếu xử lý bất đồng bộ, không được coi việc submit task vào executor là xử lý xong. Consumer phải kiểm soát số công việc đang chờ, tránh poll quá nhanh làm hàng đợi nội bộ tăng không giới hạn và chỉ commit offset khi các record trước checkpoint đã hoàn tất.

## 8. Ví dụ cấu hình Kafka Consumer Java

Ví dụ consumer đọc topic orders.events với String key/value:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put("group.id", "billing-service");
properties.put("key.deserializer", StringDeserializer.class.getName());
properties.put("value.deserializer", StringDeserializer.class.getName());
properties.put("enable.auto.commit", false);
properties.put("max.poll.records", 200);
properties.put("fetch.min.bytes", 65_536);
properties.put("fetch.max.wait.ms", 250);
properties.put("max.partition.fetch.bytes", 1_048_576);
properties.put("fetch.max.bytes", 52_428_800);
properties.put("max.poll.interval.ms", 300_000);

try (KafkaConsumer<String, String> consumer =
         new KafkaConsumer<>(properties)) {
    consumer.subscribe(List.of("orders.events"));

    while (true) {
        ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, String> record : records) {
            processOrder(record);
        }

        consumer.commitSync();
    }
}
~~~

Đây là cấu hình minh họa cho xử lý tuần tự theo batch. Trong ứng dụng thực tế cần xử lý shutdown, exception, rebalance và commit an toàn. Nếu processOrder thất bại, không commit vượt qua record chưa xử lý.

## 9. Cấu hình bằng Spring Boot và Spring Kafka

Có thể cấu hình các thuộc tính consumer trong application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      max-poll-records: 200
      fetch-min-size: 65536
      fetch-max-wait: 250ms
      max-poll-interval: 5m
      properties:
        max.partition.fetch.bytes: 1048576
        fetch.max.bytes: 52428800
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    listener:
      ack-mode: batch
~~~

Các thuộc tính Spring Boot được hỗ trợ có thể thay đổi theo phiên bản. Nếu binder không nhận một thuộc tính, có thể khai báo trực tiếp qua consumer.properties bằng tên cấu hình Kafka chuẩn và xác minh cấu hình cuối cùng lúc ứng dụng khởi động.

Với listener xử lý theo batch, có thể nhận một danh sách record:

~~~java
import java.util.List;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchListener {

    @KafkaListener(
        topics = "orders.events",
        groupId = "billing-service"
    )
    public void onMessages(List<String> events) {
        for (String event : events) {
            processOrder(event);
        }
    }
}
~~~

Để listener nhận batch, cần bật batch listener trong cấu hình listener container factory (ví dụ setBatchListener(true)) hoặc cấu hình tương đương của phiên bản Spring Kafka đang dùng. AckMode và error handler cần được thiết kế phù hợp với việc xử lý cả batch.

## 10. Cân bằng throughput và latency

Các cấu hình fetch tạo ra những đánh đổi:

| Mục tiêu | Hướng điều chỉnh thử nghiệm | Tác động cần quan sát |
|---|---|---|
| Giảm latency khi traffic thấp | Giảm fetch.min.bytes hoặc fetch.max.wait.ms | Fetch response nhỏ hơn, có thể tăng số request |
| Tăng throughput khi traffic liên tục | Tăng fetch.min.bytes vừa phải | Batch fetch lớn hơn nhưng latency traffic thấp có thể tăng |
| Giảm thời gian xử lý mỗi poll | Giảm max.poll.records | Ít record mỗi batch, tăng số lần poll |
| Giảm overhead khi record nhẹ | Tăng max.poll.records | Batch lớn hơn, cần đủ thời gian xử lý |
| Hỗ trợ record batch lớn | Tăng max.partition.fetch.bytes và khi cần fetch.max.bytes | Bộ nhớ và kích thước response có thể tăng |
| Giảm nguy cơ rebalance do xử lý lâu | Giảm batch hoặc tối ưu xử lý; xem xét max.poll.interval.ms | Cần đo thời gian xử lý p99 và poll gap |

Không nên tăng đồng thời tất cả các giới hạn. Hãy thay đổi từng nhóm cấu hình, đo kết quả rồi mới điều chỉnh tiếp để xác định nguyên nhân ảnh hưởng.

## 11. Bộ nhớ và kích thước record batch

Giới hạn fetch byte không phải giới hạn chính xác cho tổng bộ nhớ consumer. Bộ nhớ còn phụ thuộc:

- Số partition được giao cho consumer.
- Số broker đang phục vụ fetch request.
- Số fetch response đang được giữ trong bộ đệm.
- Kích thước record batch sau giải nén.
- Chi phí object Java sau deserialization.
- Số batch ứng dụng đang xử lý đồng thời.

Payload JSON có thể chiếm nhiều bộ nhớ hơn byte nén nhận từ broker sau khi deserialize thành object. Nếu ứng dụng dispatch batch sang worker, cần giới hạn kích thước queue và số task đang chạy để tránh giữ quá nhiều object trong heap.

Đối với topic có record batch lớn, hãy phối hợp max.partition.fetch.bytes với cấu hình kích thước message phía producer, broker và topic. Kafka có cơ chế cho phép fetch batch đầu tiên vượt giới hạn byte để bảo đảm tiến triển, nhưng không nên dựa vào ngoại lệ đó như một thiết kế thay thế cho cấu hình kích thước hợp lý.

## 12. Theo dõi hiệu quả của batch và fetch

Khi tuning, theo dõi cả phía Kafka consumer và ứng dụng:

- Records consumed rate và bytes consumed rate.
- Fetch size trung bình/tối đa và fetch latency.
- Số record trung bình mỗi poll và tỷ lệ poll rỗng.
- Thời gian xử lý batch p50/p95/p99.
- Khoảng thời gian giữa hai lần poll và số lần rebalance.
- Consumer lag theo partition.
- Heap usage, allocation rate, GC pause và số task đang chờ.
- Số lần retry khi gọi database/API từ logic xử lý.

Consumer lag cần được đọc cùng processing time. Lag giảm không có nghĩa ứng dụng đã hoàn tất nếu offset được commit sớm; lag tăng cũng có thể chỉ do batch được xử lý lâu nhưng vẫn nằm trong giới hạn poll interval.

## 13. Quy trình tuning thực tế

1. Đo baseline với cấu hình hiện tại: throughput, fetch latency, poll size, processing p99, lag và heap.
2. Xác định mục tiêu chính: throughput, latency, giới hạn bộ nhớ hay giảm rebalance.
3. Nếu muốn tăng throughput, thử điều chỉnh fetch.min.bytes và fetch.max.wait.ms trước, theo dõi latency.
4. Điều chỉnh max.poll.records dựa trên thời gian xử lý batch và max.poll.interval.ms.
5. Điều chỉnh max.partition.fetch.bytes/fetch.max.bytes nếu record batch lớn hoặc fetch response bị giới hạn.
6. Chạy tải thử đại diện cho số partition, số consumer và phân bố kích thước payload production.
7. Kiểm tra rebalance, memory/GC và consumer lag sau mỗi thay đổi.
8. Lưu lại cấu hình và kết quả để có thể rollback khi throughput hoặc latency xấu đi.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Poll trả ít record hơn max.poll.records | Broker chưa có đủ dữ liệu, fetch chưa hoàn tất hoặc chỉ một số partition có record | Kiểm tra fetch size, lag, traffic và partition assignment |
| Tăng max.poll.records nhưng throughput không tăng | Nút thắt nằm ở xử lý nghiệp vụ, broker, network hoặc fetch byte | Đo processing time, bytes consumed và fetch latency |
| Consumer thường xuyên rebalance | Batch xử lý vượt max.poll.interval.ms hoặc consumer không poll đều | Đo poll gap và thời gian xử lý p99 |
| Latency tăng sau khi tăng fetch.min.bytes | Broker chờ gom đủ byte trước khi trả response | Giảm fetch.min.bytes hoặc fetch.max.wait.ms |
| Heap tăng dù max.poll.records nhỏ | Consumer đã fetch và buffer dữ liệu; nhiều partition/broker hoặc deserialized objects lớn | Kiểm tra fetch byte, assigned partitions, heap và concurrency |
| Record batch lớn không fetch được như mong muốn | Giới hạn partition/response hoặc message size phía broker/topic/client chưa phù hợp | Kiểm tra max.partition.fetch.bytes, fetch.max.bytes và message size |
| Poll rỗng dù có dữ liệu mới | Fetch wait, latency mạng, assignment hoặc dữ liệu chưa đến partition đang được giao | Kiểm tra fetch metrics, broker và group assignment |

## 15. Bài tập tự kiểm tra

1. max.poll.records=100 có nghĩa broker chỉ gửi tối đa 100 record trong một FetchResponse không? Giải thích.
2. fetch.min.bytes=65536 và fetch.max.wait.ms=250 có ý nghĩa gì khi broker chưa có đủ 64 KiB dữ liệu?
3. max.partition.fetch.bytes khác fetch.max.bytes ở phạm vi nào?
4. Vì sao max.poll.records quá lớn có thể dẫn đến rebalance?
5. Một consumer xử lý mỗi record mất 300 ms và max.poll.records=500. Thời gian xử lý tuần tự ước tính là bao lâu? Có cần kiểm tra max.poll.interval.ms không?
6. Vì sao giảm max.poll.records không nhất thiết làm giảm lượng byte consumer đã fetch?
7. Nếu tăng fetch.min.bytes, latency của traffic thấp có thể thay đổi như thế nào?

## Kết luận

max.poll.records giới hạn số record trả về cho ứng dụng trong một lần poll; fetch.min.bytes và fetch.max.wait.ms điều khiển việc broker chờ gom dữ liệu; max.partition.fetch.bytes và fetch.max.bytes giới hạn kích thước fetch theo partition và toàn request. Các cấu hình này tác động đến những giai đoạn khác nhau của luồng đọc.

Hãy chọn batch size theo thời gian xử lý và max.poll.interval.ms, chọn fetch byte theo kích thước record batch và ngân sách bộ nhớ, rồi điều chỉnh fetch.min.bytes theo mục tiêu throughput/latency. Đo poll size, fetch latency, processing p99, lag và heap sau từng thay đổi để tìm cấu hình phù hợp với tải thực tế.
