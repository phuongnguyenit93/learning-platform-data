# Kiểm soát retry vô hạn trong Spring Kafka Producer

Kafka producer có thể tự động retry khi một request thất bại do lỗi tạm thời như broker đổi leader, kết nối bị gián đoạn hoặc broker phản hồi chậm. Cơ chế này giúp ứng dụng chịu được sự cố ngắn mà không phải tự gửi lại từng record. Tuy nhiên, retry không được phép giữ một record chờ mãi mãi, chiếm tài nguyên vô hạn hoặc khiến ứng dụng liên tục phát lại cùng một sự kiện.

Trong Spring Kafka, cần kiểm soát retry ở hai tầng riêng biệt:

- **Kafka client retry:** producer tự thử lại request bên trong Kafka client. Các thuộc tính retries, retry.backoff.ms, retry.backoff.max.ms và delivery.timeout.ms chi phối hành vi này.
- **Application retry:** code ứng dụng gọi KafkaTemplate.send() lại sau khi lần gửi trước thất bại. Tầng này cần giới hạn số lần, thời gian, loại lỗi và cách chống gửi trùng.

delivery.timeout.ms là giới hạn thời gian quan trọng cho một record ở Kafka producer hiện đại. Chỉ giới hạn retries mà không hiểu delivery timeout, hoặc chỉ tăng timeout để chờ lâu hơn, đều có thể dẫn đến hành vi vận hành khó kiểm soát.

## 1. Retry diễn ra ở đâu?

Một lần gửi record có thể trải qua nhiều bước:

~~~text
Ứng dụng gọi KafkaTemplate.send()
          |
          v
Kafka producer nhận record
          |
          +--> Chờ metadata / buffer
          |
          v
Gửi ProduceRequest tới broker
          |
          +--> Broker xác nhận thành công
          |          |
          |          v
          |     Future hoàn tất thành công
          |
          +--> Lỗi có thể retry
          |          |
          |          v
          |     Chờ retry backoff
          |          |
          |          v
          |     Gửi lại request
          |
          +--> Lỗi không thể retry
          |          |
          |          v
          |     Future hoàn tất với lỗi
          |
          +--> Hết delivery timeout
                     |
                     v
               Future hoàn tất với lỗi
~~~

Kafka client tự retry một số lỗi được phân loại là retriable. Ví dụ thường gặp là lỗi tạm thời trong quá trình kết nối, lỗi leader hoặc lỗi request có thể phục hồi. Những lỗi cấu hình hoặc dữ liệu như serialization không hợp lệ, topic không hợp lệ hay thiếu quyền truy cập thường không được giải quyết bằng cách gửi lại liên tục.

Sau khi producer không thể giao record trong giới hạn cho phép, future của lần gửi sẽ hoàn tất với lỗi. Ứng dụng cần nhận biết kết quả đó và quyết định lưu lại, thử lại ở thời điểm khác hoặc đưa bản ghi vào trạng thái cần can thiệp.

Không nên gộp tất cả các tầng retry thành một vòng lặp duy nhất. Kafka client retry xử lý lỗi request ở tầng giao thức; application retry xử lý quyết định nghiệp vụ sau khi lần gửi đã thất bại.

## 2. Vì sao retry có vẻ vô hạn?

Thuộc tính retries quy định số lần Kafka producer có thể thử lại một request sau lần gửi ban đầu khi gặp lỗi có thể phục hồi. Nhiều phiên bản Kafka client hiện đại đặt giá trị mặc định rất lớn cho thuộc tính này. Thiết kế đó cho phép client tiếp tục thử trong khi các giới hạn thời gian khác quyết định lúc nào phải dừng.

Vì vậy, một giá trị retries rất lớn không nhất thiết khiến một record được gửi mãi mãi. Với Kafka client hiện đại, delivery.timeout.ms giới hạn tổng thời gian producer được phép báo kết quả thành công hoặc thất bại sau khi send() trả về. Khi hết thời gian này, record hết hạn ngay cả khi số retry chưa dùng hết.

Một record thường dừng retry khi một trong các điều kiện sau xảy ra:

1. Broker xác nhận thành công.
2. Producer gặp lỗi không thể retry.
3. Số lần retry được cấu hình đã hết.
4. delivery.timeout.ms hết hạn.
5. Producer hoặc ứng dụng bị đóng, bị dừng hay mất tài nguyên cần thiết.

Do đó, “retry vô hạn” trong vận hành thường là một trong các tình huống sau:

- retries đặt quá cao và delivery.timeout.ms cũng quá lớn.
- Ứng dụng tự gọi send() lại trong vòng lặp không có giới hạn.
- Một scheduler liên tục lấy cùng bản ghi lỗi để gửi lại mà không có backoff hoặc giới hạn tuổi bản ghi.
- Lỗi cấu hình cố định bị xem nhầm là lỗi tạm thời, nên bản ghi được retry mãi dù không thể thành công.
- Broker ngừng hoạt động nhưng ứng dụng vẫn tạo thêm công việc gửi, khiến hàng đợi nội bộ và hàng đợi nghiệp vụ tăng liên tục.

Một thiết kế tốt cần có giới hạn cho từng record, giới hạn tổng thời gian phục hồi và cơ chế lưu giữ dữ liệu khi Kafka chưa sẵn sàng.

## 3. Các thuộc tính điều khiển retry của Kafka producer

| Thuộc tính | Vai trò | Cách dùng để kiểm soát |
|---|---|---|
| retries | Số lần retry sau lần gửi ban đầu | Đặt giới hạn số lần thử nếu cần dừng theo số lượt |
| delivery.timeout.ms | Tổng thời gian tối đa để báo kết quả giao record | Đặt deadline hữu hạn cho mỗi record |
| request.timeout.ms | Thời gian chờ phản hồi cho một request tới broker | Đặt theo độ trễ broker và mạng |
| retry.backoff.ms | Thời gian chờ cơ bản giữa các lần retry | Tránh gửi lại liên tục |
| retry.backoff.max.ms | Giới hạn trên của khoảng backoff tăng dần | Tránh khoảng chờ tăng quá lớn |
| enable.idempotence | Bảo vệ retry nội bộ khỏi tạo bản ghi trùng trong cùng producer session | Bật khi cần retry an toàn |
| acks | Mức xác nhận từ broker | Kết hợp với durability và idempotence |

### retries

retries là số lần thử lại sau lần gửi đầu tiên, không phải tổng số lần gửi tính cả lần đầu. Ví dụ, retries=5 cho phép tối đa năm lần retry đối với lỗi có thể retry, tức tối đa sáu lần gửi request theo cách đếm đơn giản. Delivery timeout hoặc lỗi không thể retry có thể khiến quá trình kết thúc sớm hơn.

Nếu cần giới hạn theo số lần thử, hãy đặt giá trị hữu hạn. Nếu muốn Kafka client tiếp tục xử lý lỗi tạm thời trong một khoảng thời gian đã định, có thể dùng giá trị retry lớn nhưng phải đặt delivery.timeout.ms hữu hạn và phù hợp.

### delivery.timeout.ms

Đây là giới hạn tổng thời gian quan trọng nhất cho một record. Thời gian này bao gồm việc chờ batch, chờ broker xác nhận và các lần retry do lỗi có thể phục hồi. Khi hết hạn, producer báo lỗi giao record.

Kafka yêu cầu:

~~~text
delivery.timeout.ms >= request.timeout.ms + linger.ms
~~~

Ví dụ, nếu request.timeout.ms là 30.000 ms và linger.ms là 5 ms, delivery.timeout.ms phải ít nhất là 30.005 ms. Trong thực tế nên có khoảng dự phòng đủ rộng để phù hợp với độ trễ và retry mong muốn.

### request.timeout.ms

Đây là giới hạn chờ phản hồi cho một request cụ thể. Nó không phải tổng thời gian retry của một record. Một record có thể trải qua nhiều request và các khoảng backoff trước khi thành công hoặc hết delivery.timeout.ms.

### retry.backoff.ms và retry.backoff.max.ms

Các thuộc tính này kiểm soát khoảng nghỉ giữa các lần retry. Kafka client hiện đại tăng khoảng chờ theo cấp số nhân, có giới hạn trên và jitter tùy phiên bản, để giảm việc nhiều producer cùng retry đúng một thời điểm.

- retry.backoff.ms: khoảng chờ cơ bản.
- retry.backoff.max.ms: khoảng chờ tối đa khi backoff tăng dần.

retry.backoff.max.ms chỉ có ở các phiên bản Kafka client hỗ trợ thuộc tính này. Hãy kiểm tra phiên bản client thực tế trước khi dùng.

## 4. Cấu hình giới hạn retry trong Spring Boot

Ví dụ sau giới hạn số lần retry nội bộ và tổng thời gian giao record:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 5
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[request.timeout.ms]": 30000
        "[delivery.timeout.ms]": 90000
        "[retry.backoff.ms]": 200
        "[retry.backoff.max.ms]": 2000
        "[linger.ms]": 5
~~~

Cách đọc cấu hình:

- retries: 5 cho phép tối đa năm lần retry sau lần gửi ban đầu.
- delivery.timeout.ms: 90000 đặt tổng deadline giao record là 90 giây.
- request.timeout.ms: 30000 giới hạn thời gian chờ phản hồi cho một request.
- retry.backoff.ms: 200 đặt khoảng chờ cơ bản giữa các lần retry.
- retry.backoff.max.ms: 2000 giới hạn khoảng backoff tăng dần.
- enable.idempotence: true bật idempotent producer.
- acks: all yêu cầu broker xác nhận theo ISR.

Các con số chỉ là ví dụ để minh họa cách phối hợp cấu hình. Hãy chọn giá trị theo độ trễ thực tế, khả năng phục hồi của broker và deadline nghiệp vụ. Với các giá trị trên, điều kiện delivery.timeout.ms >= request.timeout.ms + linger.ms được đáp ứng.

Idempotent producer có các điều kiện tương thích về acks, retries và max.in.flight.requests.per.connection. Khi bật idempotence, hãy giữ các thuộc tính ở cấu hình tương thích; Kafka client hiện đại thường tự áp dụng giá trị phù hợp nếu ứng dụng không ghi đè. Nếu cấu hình xung đột, producer có thể từ chối khởi tạo.

Nếu ứng dụng dùng application.properties, cấu hình tương đương là:

~~~properties
spring.kafka.producer.acks=all
spring.kafka.producer.retries=5
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5
spring.kafka.producer.properties[request.timeout.ms]=30000
spring.kafka.producer.properties[delivery.timeout.ms]=90000
spring.kafka.producer.properties[retry.backoff.ms]=200
spring.kafka.producer.properties[retry.backoff.max.ms]=2000
spring.kafka.producer.properties[linger.ms]=5
~~~

Khi tự tạo ProducerFactory, hãy đưa các thuộc tính này vào đúng map cấu hình được truyền cho factory. Nếu ứng dụng có nhiều ProducerFactory hoặc KafkaTemplate, cần xác nhận producer thực sự gửi record đang dùng cấu hình mong muốn.

## 5. Phân biệt Kafka client retry và application retry

Đây là ranh giới quan trọng nhất khi kiểm soát retry.

**Kafka client retry** diễn ra bên trong một lần KafkaTemplate.send(). Client tự xử lý các request lỗi có thể phục hồi theo retries, backoff và delivery timeout. Ứng dụng không cần gọi send() lại cho từng lần retry nội bộ.

**Application retry** xảy ra khi code nhận kết quả thất bại rồi gọi KafkaTemplate.send() thêm lần nữa. Đây là một lần gửi mới từ góc nhìn ứng dụng. Nó cần chính sách riêng về số lần thử, tổng thời gian, loại lỗi và idempotency.

Ví dụ về application retry không an toàn:

~~~java
while (true) {
    try {
        kafkaTemplate.send("orders", event).get();
        break;
    }
    catch (Exception ex) {
        // Gửi lại ngay, không giới hạn số lần hoặc thời gian.
    }
}
~~~

Vòng lặp này có thể chiếm thread vô thời hạn, tạo tải liên tục khi Kafka đang lỗi và gửi trùng khi broker đã ghi record nhưng ứng dụng không nhận được phản hồi.

Ngoài ra, KafkaTemplate.send() là bất đồng bộ. Lỗi có thể xuất hiện trước khi future được trả về, chẳng hạn khi producer không thể lấy metadata hoặc buffer trong giới hạn max.block.ms; lỗi khác có thể xuất hiện khi future hoàn tất. Code cần xử lý cả lỗi đồng bộ lẫn lỗi bất đồng bộ.

## 6. Xử lý kết quả gửi mà không tạo vòng retry vô hạn

Với Spring Kafka 3.x, KafkaTemplate.send() trả về CompletableFuture. Ứng dụng nên quan sát kết quả gửi, ghi nhận thành công hoặc chuyển lỗi sang cơ chế phục hồi có giới hạn.

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;
    private final OutboxRepository outboxRepository;
    private final Executor completionExecutor;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate,
            OutboxRepository outboxRepository,
            Executor completionExecutor) {
        this.kafkaTemplate = kafkaTemplate;
        this.outboxRepository = outboxRepository;
        this.completionExecutor = completionExecutor;
    }

    public void publish(OutboxEvent event) {
        try {
            kafkaTemplate.send(
                    "orders",
                    event.key(),
                    event.payload()
            ).whenComplete((result, failure) ->
                    completionExecutor.execute(() -> {
                        if (failure == null) {
                            outboxRepository.markSent(
                                    event.id(),
                                    result.getRecordMetadata().partition(),
                                    result.getRecordMetadata().offset()
                            );
                        }
                        else {
                            outboxRepository.scheduleRetry(
                                    event.id(),
                                    failure
                            );
                        }
                    })
            );
        }
        catch (RuntimeException failure) {
            // Có thể lỗi ngay trong lúc khởi tạo/gửi request,
            // trước khi future được trả về.
            outboxRepository.scheduleRetry(event.id(), failure);
        }
    }
}
~~~

Các kiểu OutboxEvent, repository và executor trong ví dụ đại diện cho thành phần ứng dụng. scheduleRetry cần phân loại lỗi, tăng số lần thử, tính thời điểm thử tiếp theo và chuyển lỗi không thể phục hồi sang trạng thái cần xử lý.

Callback của producer cần làm việc ngắn gọn. Không nên chạy một vòng retry blocking hoặc thao tác database chậm ngay trên thread callback; hãy chuyển kết quả sang executor hoặc hàng đợi nội bộ phù hợp. Nếu dùng Spring Kafka phiên bản cũ trả về ListenableFuture, hãy điều chỉnh cách đăng ký callback theo API của phiên bản đó.

Một luồng xử lý nên có các trạng thái rõ ràng:

~~~text
PENDING
   |
   v
SENDING
   |
   +--> broker xác nhận --> SENT
   |
   +--> lỗi tạm thời ----> RETRY_WAIT
   |                          |
   |                          +--> đến hạn, còn lượt --> SENDING
   |                          |
   |                          +--> quá giới hạn ------> FAILED / NEEDS_REVIEW
   |
   +--> lỗi cố định ------> FAILED / NEEDS_REVIEW
~~~

Trạng thái FAILED không có nghĩa phải xóa sự kiện. Với dữ liệu nghiệp vụ quan trọng, hãy giữ lại payload, event ID, lỗi gần nhất và lịch sử thử gửi để có thể điều tra hoặc phát lại có kiểm soát.

## 7. Thiết kế application retry có giới hạn

Nếu nghiệp vụ cần thử lại sau khi Kafka client đã hết thời gian giao record, hãy xác định rõ các giới hạn sau.

### Giới hạn số lần thử

Ví dụ, cho phép tối đa năm lần thử ở tầng ứng dụng sau khi một lần gửi đã thất bại. Cần ghi rõ cách đếm: năm lần gửi tổng cộng hay năm lần retry sau lần đầu. Không để scheduler liên tục lấy lại một bản ghi mà không tăng bộ đếm.

### Giới hạn tổng thời gian

Một sự kiện có thể có deadline nghiệp vụ, chẳng hạn phải được phát trong vòng 15 phút. Khi quá deadline, chuyển sự kiện sang trạng thái cần can thiệp thay vì tiếp tục thử vô hạn. Deadline nghiệp vụ nên độc lập với delivery.timeout.ms của một lần gửi.

### Exponential backoff và jitter

Một lịch retry thường dùng là:

~~~text
delay(n) = min(baseDelay * 2^n, maxDelay) + jitter
~~~

Ví dụ:

| Lần retry | Khoảng chờ cơ sở | Mục đích |
|---:|---:|---|
| 1 | 200 ms | Thử lại nhanh sau lỗi ngắn |
| 2 | 400 ms | Tăng khoảng nghỉ |
| 3 | 800 ms | Giảm áp lực lên broker |
| 4 | 1.600 ms | Cho cụm thêm thời gian phục hồi |
| 5 trở đi | Tối đa 2.000 ms | Không tăng khoảng nghỉ vượt giới hạn |

Jitter thêm một độ lệch ngẫu nhiên vào khoảng chờ để nhiều instance không đồng loạt gửi lại cùng lúc. Các con số trong bảng là ví dụ; lịch retry cần nằm trong deadline tổng của sự kiện.

### Phân loại lỗi

Không phải lỗi nào cũng nên retry.

| Nhóm lỗi | Hành động thường phù hợp |
|---|---|
| Broker tạm thời không khả dụng, mất kết nối, leader thay đổi | Retry theo backoff và deadline |
| Request timeout hoặc delivery timeout | Ghi nhận kết quả không chắc chắn, retry có kiểm soát và giữ event ID |
| Serialization không hợp lệ | Không retry nguyên trạng; sửa dữ liệu hoặc xử lý thủ công |
| Topic không tồn tại hoặc tên topic sai | Sửa cấu hình hoặc quy trình tạo topic |
| Thiếu quyền ghi topic | Xử lý quyền truy cập; retry liên tục không khắc phục được |
| Record vượt giới hạn kích thước | Điều chỉnh payload hoặc giới hạn broker/topic |
| Producer đã đóng hoặc ứng dụng đang shutdown | Xử lý vòng đời producer; không lặp send vô hạn |

Có thể phân loại dựa trên exception gốc sau khi bỏ lớp bọc như CompletionException. Một số exception cụ thể thay đổi theo Kafka client và Spring Kafka version; hãy dùng loại lỗi và nguyên nhân gốc thay vì chỉ kiểm tra chuỗi thông báo.

## 8. Dùng transactional outbox để giữ sự kiện khi Kafka lỗi

Nếu sự kiện không được phép mất, một vòng retry trong bộ nhớ không đủ. Khi ứng dụng restart, trạng thái chờ có thể mất; khi Kafka ngừng lâu, một hàng đợi trong bộ nhớ có thể đầy.

Transactional outbox lưu sự kiện trong database cùng transaction với thay đổi nghiệp vụ:

~~~text
Database transaction
    |
    +--> Cập nhật dữ liệu nghiệp vụ
    |
    +--> Insert outbox event (PENDING)
    |
    +--> Commit
             |
             v
       Outbox publisher
             |
             +--> KafkaTemplate.send()
             |
             +--> ACK thành công: đánh dấu SENT
             |
             +--> Gửi lỗi: lưu attempts và next_attempt_at
~~~

Publisher đọc các bản ghi PENDING hoặc RETRY_WAIT đã đến hạn. Mỗi lần thất bại, nó cập nhật số lần thử, lỗi cuối cùng và next_attempt_at. Khi vượt số lần thử hoặc deadline, nó chuyển sang FAILED/NEEDS_REVIEW và phát cảnh báo.

Có một cửa sổ lỗi cần tính đến: broker đã xác nhận record nhưng ứng dụng dừng trước khi đánh dấu outbox là SENT. Khi khởi động lại, publisher có thể gửi lại event. Vì vậy:

- Giữ eventId ổn định trong mọi lần gửi lại.
- Dùng idempotent producer để bảo vệ retry nội bộ.
- Thiết kế consumer idempotent hoặc có inbox/unique constraint.
- Đánh dấu outbox SENT chỉ sau khi nhận acknowledgement thành công.
- Lưu lịch sử lỗi và số lần thử để vận hành có thể phục hồi.

Outbox tạo ra khả năng phục hồi bền vững qua restart. Nó không tự biến một lần gửi có thể lặp thành exactly once end-to-end.

## 9. Idempotence, thứ tự và transaction khi retry

### Idempotent producer

enable.idempotence=true giúp broker nhận diện retry nội bộ của cùng producer bằng producer ID và sequence number. Điều này hạn chế duplicate do Kafka client retry một request không nhận được phản hồi.

Idempotence không loại bỏ duplicate do ứng dụng gọi KafkaTemplate.send() nhiều lần độc lập. Nếu một lần gửi hết timeout nhưng broker thực tế đã ghi record, lần gửi mới của ứng dụng có thể tạo record thứ hai. Dùng event ID ổn định và consumer idempotent để bảo vệ hiệu ứng nghiệp vụ.

### Thứ tự record

Khi idempotence tắt, retry kết hợp với nhiều request đang in-flight có thể làm thay đổi thứ tự record trong một số tình huống lỗi. Khi bật idempotence, Kafka hỗ trợ bảo toàn thứ tự với giới hạn max.in.flight.requests.per.connection tương thích (tối đa 5 trong cấu hình idempotent producer hiện đại).

Retry ở tầng ứng dụng là một lần gửi mới, vì vậy vẫn có thể làm thay đổi thứ tự nghiệp vụ. Nếu cần thứ tự theo đơn hàng hoặc tài khoản:

- Dùng key ổn định để các record liên quan đi vào cùng partition.
- Không phát lại record cũ vượt qua record mới hơn nếu thứ tự là bắt buộc.
- Có thể tuần tự hóa publisher theo key hoặc partition.
- Lưu sequence nghiệp vụ nếu consumer cần phát hiện record đến sai thứ tự.

### Producer transaction

Với transactional producer, lỗi trong quá trình gửi có thể khiến transaction không thể commit. Ứng dụng cần xử lý abort và bắt đầu một transaction mới theo đúng vòng đời producer/container. Không nên gửi lại record trong một transaction đã abort rồi xem đó là lần thử độc lập thành công.

Nếu Spring Kafka dùng transaction manager cho listener hoặc KafkaTemplate.executeInTransaction, hãy tuân thủ quy trình commit/abort của transaction. Chính sách retry ở tầng ứng dụng phải đặt bên ngoài ranh giới transaction đã kết thúc.

## 10. Những công cụ retry của Spring Kafka không thay thế producer retry

Một số API Spring Kafka thường bị nhầm với retry gửi record:

- DefaultErrorHandler xử lý lỗi khi consumer listener xử lý record thất bại.
- @RetryableTopic triển khai retry topic cho luồng consumer/listener.
- KafkaTemplate.send() là API gửi bất đồng bộ; future phản ánh kết quả gửi.
- Kafka producer properties điều khiển retry request nội bộ của producer.

@RetryableTopic và DefaultErrorHandler không phải cấu hình giới hạn retry của KafkaTemplate.send(). Nếu producer không gửi được record, hãy quản lý kết quả gửi ở producer service hoặc outbox publisher.

Nếu một listener đọc record rồi gửi sang topic khác, có thể có cả hai cơ chế: consumer retry khi listener thất bại và producer retry khi gửi output thất bại. Hãy xác định transaction và offset behavior để tránh việc listener được gọi lại trong khi output đã được ghi, hoặc output được gửi lặp khi listener retry.

## 11. Circuit breaker, backpressure và shutdown

Khi broker gặp sự cố kéo dài, retry nhanh từ nhiều instance có thể làm tình trạng nặng hơn. Bên cạnh giới hạn retry, hãy kiểm soát tốc độ tạo công việc.

**Circuit breaker:** Khi tỷ lệ lỗi hoặc độ trễ vượt ngưỡng, tạm ngừng gửi mới trong một khoảng thời gian. Sau đó cho phép một số request thử để xác định broker đã phục hồi. Circuit breaker cần phối hợp với outbox để sự kiện vẫn được lưu.

**Backpressure:** Giới hạn số record đang chờ gửi, số publisher đồng thời và tốc độ lấy outbox. Khi backlog tăng, giảm tốc độ đọc hoặc dừng nhận thêm công việc nếu hệ thống có thể áp dụng.

**Shutdown:** Khi ứng dụng dừng, ngừng nhận công việc mới, cho các lần gửi đang chạy có thời gian hoàn tất trong giới hạn shutdown, rồi đóng producer/factory theo lifecycle của Spring. Không giữ shutdown vô thời hạn chỉ để chờ retry. Các outbox event chưa gửi phải còn trạng thái bền vững để instance khác tiếp tục sau restart.

Không nên dùng flush() hoặc Future.get() blocking vô hạn trong luồng xử lý request. Nếu cần chờ kết quả, hãy đặt timeout rõ ràng và hiểu rằng timeout của code chờ không nhất thiết hủy thao tác gửi đang chạy.

## 12. Theo dõi retry và phát hiện vòng lặp bất thường

Theo dõi cả metric Kafka producer lẫn trạng thái outbox/application retry.

| Tín hiệu | Điều cần phát hiện |
|---|---|
| record-retry-rate | Producer phải retry thường xuyên |
| record-error-rate | Tỷ lệ record gửi thất bại |
| request-latency-avg / request-latency-max | Broker phản hồi chậm |
| bufferpool-wait-time | Producer thiếu buffer hoặc gửi chậm hơn tốc độ tạo record |
| Số request in-flight | Nhiều request chờ phản hồi |
| Outbox pending count | Sự kiện đang tích tụ chưa gửi |
| Tuổi của outbox event cũ nhất | Sự kiện vượt quá thời gian chờ nghiệp vụ |
| Application retry attempts | Một event bị thử lại quá nhiều lần |
| Failed / needs-review count | Sự kiện cần người vận hành xử lý |

Tên metric có thể khác theo Kafka client version, Micrometer và hệ thống exporter. Hãy kiểm tra metric thực tế đang được xuất.

Một số cảnh báo hữu ích:

- Outbox backlog tăng liên tục trong khi producer send rate giảm.
- Một event vượt số lần retry hoặc deadline.
- Tỷ lệ retry tăng mạnh sau khi broker thay đổi leader.
- Producer liên tục báo delivery timeout.
- Cùng một event ID xuất hiện nhiều lần ở consumer.
- Số lượng record đang chờ gửi tăng nhanh hơn khả năng xử lý.

Log nên có eventId, topic, key, attempt number, lỗi gốc, thời gian lần gửi, thời điểm retry kế tiếp và trạng thái outbox. Tránh chỉ log stack trace mà không có định danh để đối chiếu.

## 13. Checklist thiết kế chính sách retry

Trước khi đưa producer vào production, hãy xác định:

- retries có giới hạn hữu hạn hay được để lớn nhưng bị giới hạn bởi delivery.timeout.ms?
- Mỗi record có delivery deadline hữu hạn và phù hợp với deadline nghiệp vụ không?
- request.timeout.ms, delivery.timeout.ms và linger.ms có thỏa quan hệ cấu hình của Kafka không?
- Backoff có giới hạn trên và jitter để tránh retry đồng loạt không?
- Idempotent producer có bật và dùng cấu hình tương thích không?
- Code có xử lý cả lỗi đồng bộ khi gọi send() và lỗi bất đồng bộ từ future không?
- Application retry có giới hạn số lần, tổng thời gian và phân loại lỗi không?
- Event ID có ổn định qua mọi lần gửi lại không?
- Sự kiện quan trọng có được lưu bền vững bằng outbox không?
- Consumer có idempotent để chịu được lần gửi trùng không?
- Có kiểm soát backlog, concurrency, circuit breaker và shutdown không?
- Có metrics, log và cảnh báo cho retry rate, delivery error và outbox age không?

Một chính sách retry có kiểm soát cho Spring Kafka cần kết hợp giới hạn thời gian ở Kafka client, giới hạn số lần và deadline ở tầng ứng dụng, backoff có jitter, idempotency và lưu trữ bền vững cho sự kiện quan trọng. Khi hết ngân sách retry, hệ thống phải chuyển sự kiện sang trạng thái có thể quan sát và phục hồi, thay vì tiếp tục gửi vô hạn hoặc âm thầm làm mất dữ liệu.
