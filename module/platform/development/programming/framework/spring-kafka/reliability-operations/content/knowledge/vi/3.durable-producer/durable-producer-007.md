# request.timeout.ms trong Spring Kafka Producer

Trong Spring Kafka, cấu hình **request.timeout.ms** xác định khoảng thời gian Kafka producer chờ phản hồi cho một request gửi tới broker. Nếu broker không trả lời trong thời gian này, producer xem request là hết hạn và có thể retry theo cấu hình hiện tại; khi không thể retry tiếp, lần gửi sẽ thất bại.

Đây là một phần của cơ chế vận hành producer bền vững. Giá trị quá thấp có thể tạo retry không cần thiết khi broker hoặc mạng đang chậm. Giá trị quá cao làm ứng dụng phát hiện sự cố chậm hơn. Để cấu hình đúng, cần đặt request timeout trong mối quan hệ với delivery timeout, retry, acknowledgement và cách ứng dụng quan sát kết quả gửi.

## 1. request.timeout.ms kiểm soát điều gì?

Kafka producer gửi request qua kết nối TCP tới broker. Với cấu hình chờ acknowledgement, producer cần nhận phản hồi để biết broker đã xử lý request như thế nào. request.timeout.ms là giới hạn thời gian chờ phản hồi cho một request đó.

Luồng đơn giản:

~~~text
Ứng dụng
   |
   | producer.send(record)
   v
Kafka producer
   |
   | ProduceRequest
   v
Kafka broker
   |
   | xử lý request, ghi record và tạo phản hồi
   v
Kafka producer
   |
   +--> nhận phản hồi trước timeout: tiếp tục theo kết quả broker
   |
   +--> không nhận phản hồi đúng hạn: timeout, có thể retry
~~~

Trong Kafka Java producer, giá trị mặc định phổ biến của request.timeout.ms là 30.000 ms (30 giây). Hãy xác nhận giá trị mặc định theo phiên bản Kafka client mà ứng dụng đang dùng; Spring Boot thường chuyển cấu hình này tới Kafka client thông qua producer properties.

Cấu hình được tính bằng mili giây. Ví dụ, 45.000 tương đương 45 giây.

Điều cần nhớ là timeout chỉ cho biết producer không nhận được phản hồi đúng hạn. Nó **không chứng minh broker chưa ghi record**. Broker có thể đã ghi thành công nhưng phản hồi bị mất trên đường truyền hoặc đến quá muộn. Vì vậy, sau một request timeout, kết quả của lần gửi có thể chưa rõ ràng cho ứng dụng.

## 2. Phân biệt request.timeout.ms với các timeout khác

Một producer có nhiều giới hạn thời gian. Mỗi cấu hình bảo vệ một phần khác nhau của quá trình gửi.

| Cấu hình | Phạm vi kiểm soát | Khi hết thời gian |
|---|---|---|
| request.timeout.ms | Thời gian chờ phản hồi cho một request tới broker | Request có thể được retry hoặc báo lỗi |
| delivery.timeout.ms | Tổng thời gian tối đa để producer báo kết quả gửi sau khi send được gọi | Record hết hạn giao và future hoàn tất với lỗi |
| max.block.ms | Thời gian một lời gọi send có thể chờ metadata hoặc chờ chỗ trong buffer | Lời gọi send có thể ném TimeoutException trước khi trả future |
| Future.get(timeout) | Thời gian code ứng dụng chờ kết quả future | Chỉ lời gọi chờ của ứng dụng hết hạn; thao tác gửi nền có thể vẫn tiếp tục |

### request.timeout.ms và delivery.timeout.ms

Đây là hai cấu hình dễ bị nhầm nhất.

- request.timeout.ms giới hạn thời gian chờ phản hồi cho một request cụ thể.
- delivery.timeout.ms giới hạn tổng thời gian producer được phép hoàn tất việc giao một record, tính từ khi send trả về. Thời gian này bao gồm việc chờ batch, chờ acknowledgement và các lần retry do lỗi có thể phục hồi.

Kafka yêu cầu delivery.timeout.ms lớn hơn hoặc bằng tổng request.timeout.ms và linger.ms. Nếu tăng request timeout, hãy kiểm tra delivery timeout để cấu hình vẫn hợp lệ.

Ví dụ:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        "[request.timeout.ms]": 45000
        "[delivery.timeout.ms]": 120000
        "[linger.ms]": 5
~~~

Với cấu hình trên, một request có thể chờ phản hồi tối đa 45 giây; producer có tổng ngân sách giao record là 120 giây. Khoảng thời gian tổng này cho phép producer xử lý nhiều tình huống retry nếu các điều kiện khác cho phép.

Đừng hiểu delivery.timeout.ms là thời gian chờ cho một lần request. Nếu broker liên tục phản hồi chậm hoặc request phải retry, tổng thời gian giao record mới là giới hạn quan trọng đối với kết quả cuối cùng.

### request.timeout.ms và max.block.ms

max.block.ms có thể khiến chính lời gọi send bị chặn khi producer cần lấy metadata hoặc chờ buffer có chỗ trống. Khi metadata đã sẵn sàng và record được đưa vào luồng gửi, producer tiếp tục xử lý bất đồng bộ.

Do đó, có hai giai đoạn khác nhau:

1. Lời gọi send cần metadata hoặc buffer. max.block.ms giới hạn thời gian chờ ở giai đoạn này.
2. Record đã được đưa vào producer. request.timeout.ms và delivery.timeout.ms điều khiển việc chờ phản hồi và hoàn tất giao record.

Tăng request.timeout.ms không giải quyết tình trạng producer hết buffer hoặc không lấy được metadata. Khi send bị chặn, cần quan sát buffer memory, tốc độ gửi, metadata và cấu hình max.block.ms.

### request.timeout.ms và Future.get(timeout)

Spring Kafka trả về future cho kết quả gửi. Nếu code gọi future.get(2, TimeUnit.SECONDS), thời gian hai giây là giới hạn chờ của code ứng dụng. Nó không thay đổi request.timeout.ms và không tự hủy request đang được producer xử lý.

Ví dụ:

~~~java
SendResult<String, OrderCreated> result =
        kafkaTemplate.send("orders", order).get(2, TimeUnit.SECONDS);
~~~

Nếu hai giây trôi qua mà future chưa hoàn tất, lời gọi get có thể ném java.util.concurrent.TimeoutException. Producer vẫn có thể hoàn tất gửi sau đó. Ứng dụng cần xử lý rõ việc tiếp tục theo dõi future và tránh gửi lại một record mới chỉ vì code chờ đã hết thời gian.

## 3. request timeout tương tác với acks

Thời gian producer chờ phản hồi chịu ảnh hưởng bởi acknowledgement policy.

| acks | Ý nghĩa | Quan hệ với request timeout |
|---|---|---|
| 0 | Producer không chờ broker xác nhận record | Không có acknowledgement response để chờ cho ProduceRequest theo cách thông thường |
| 1 | Leader partition xác nhận sau khi ghi record vào log cục bộ | Chờ phản hồi từ leader |
| all | Các replica hiện thuộc ISR xác nhận theo quy tắc Kafka | Có thể chờ lâu hơn khi replica trong ISR chậm hoặc ISR thay đổi |

Với hệ thống cần durability cao, producer thường dùng acks=all và cấu hình min.insync.replicas phù hợp ở broker/topic. Khi số replica trong ISR thấp hơn mức min.insync.replicas, broker có thể từ chối ghi thay vì xác nhận một bản ghi không đáp ứng mức durability đã đặt.

request.timeout.ms nên đủ dài để bao phủ thời gian phản hồi hợp lý của broker trong điều kiện tải và replication bình thường. Nếu giá trị quá thấp, producer có thể retry trong khi broker vẫn đang xử lý request ban đầu.

Tài liệu Kafka khuyến nghị request.timeout.ms lớn hơn replica.lag.time.max.ms của broker để giảm khả năng retry không cần thiết do phản hồi của broker hoặc replica bị chậm. Hãy đánh giá hai giá trị này cùng nhau, đặc biệt khi dùng acks=all.

## 4. Cấu hình request.timeout.ms trong Spring Boot

Spring Boot cung cấp nhóm cấu hình producer properties để chuyển các thuộc tính của Kafka client. request.timeout.ms là thuộc tính Kafka producer, vì vậy đặt nó trong map properties của producer.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[request.timeout.ms]": 45000
        "[delivery.timeout.ms]": 120000
        "[linger.ms]": 5
~~~

Các điểm cần lưu ý:

- acks: all yêu cầu broker xác nhận theo ISR.
- enable.idempotence: true bật idempotent producer để Kafka xử lý an toàn các lần retry do producer thực hiện trong cùng producer session.
- request.timeout.ms: 45 giây là ví dụ minh họa, không phải giá trị tối ưu cho mọi môi trường.
- delivery.timeout.ms: 120 giây là ngân sách giao record tổng thể trong ví dụ.
- linger.ms: 5 ms là khoảng chờ tối đa để gom batch trước khi gửi trong điều kiện phù hợp.

Cách khai báo bracketed key giúp Spring Boot giữ nguyên tên thuộc tính Kafka có dấu chấm khi bind map. Nếu ứng dụng dùng application.properties, có thể khai báo:

~~~properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[request.timeout.ms]=45000
spring.kafka.producer.properties[delivery.timeout.ms]=120000
spring.kafka.producer.properties[linger.ms]=5
~~~

Nếu ứng dụng tự tạo ProducerFactory thay vì dùng cấu hình tự động của Spring Boot, hãy thêm thuộc tính vào map cấu hình được truyền cho DefaultKafkaProducerFactory. Cần bảo đảm KafkaTemplate sử dụng đúng ProducerFactory đó; nếu có nhiều producer factory, việc đặt cấu hình ở factory không được listener hoặc template sử dụng sẽ không có tác dụng.

## 5. Gửi record và quan sát kết quả trong Spring Kafka

Không nên xem việc gọi KafkaTemplate.send là bằng chứng record đã được broker xác nhận. Việc gửi diễn ra bất đồng bộ; ứng dụng cần xử lý kết quả hoàn tất hoặc lỗi.

Ví dụ với Spring Kafka phiên bản có API CompletableFuture:

~~~java
@Service
public class OrderProducer {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderProducer(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send("orders", event)
                .whenComplete((result, exception) -> {
                    if (exception != null) {
                        handleSendFailure(event, exception);
                        return;
                    }

                    var metadata = result.getRecordMetadata();
                    log.info(
                            "Published order event: topic={}, partition={}, offset={}",
                            metadata.topic(),
                            metadata.partition(),
                            metadata.offset()
                    );
                });
    }

    private void handleSendFailure(
            OrderCreated event,
            Throwable exception) {
        log.error(
                "Could not publish order event, eventId={}",
                event.eventId(),
                exception
        );
    }
}
~~~

Tên kiểu dữ liệu và các phương thức nghiệp vụ trong ví dụ là minh họa. Spring Kafka 3.x dùng CompletableFuture cho kết quả gửi; các phiên bản cũ hơn có thể dùng ListenableFuture. Hãy dùng API phù hợp với phiên bản thư viện của dự án.

Khi future hoàn tất thành công, ứng dụng có thể đọc metadata của record như topic, partition và offset. Khi future hoàn tất với lỗi, cần ghi nhận nguyên nhân và áp dụng chính sách phục hồi của ứng dụng.

Nếu lỗi xảy ra do request timeout, không nên mặc định rằng record chắc chắn chưa được ghi. Broker có thể đã xử lý request nhưng producer không nhận được phản hồi. Nếu ứng dụng tự tạo một lần send mới, đây là một lần gửi độc lập và có thể tạo record trùng.

## 6. Idempotent producer và retry sau timeout

Một request timeout tạo ra tình huống không chắc chắn: broker có thể chưa nhận request, đang xử lý request hoặc đã ghi record nhưng phản hồi bị mất.

Kafka idempotent producer giúp xử lý retry nội bộ của producer bằng producer ID và sequence number. Khi producer retry một batch theo cơ chế Kafka, broker có thể nhận diện và loại bỏ lần ghi lặp thuộc cùng chuỗi sequence.

Cấu hình điển hình:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[request.timeout.ms]": 45000
        "[delivery.timeout.ms]": 120000
~~~

Idempotent producer có các điều kiện tương thích về acks, retries và max.in.flight.requests.per.connection. Với các phiên bản Kafka hiện đại, bật idempotence sẽ yêu cầu các cấu hình liên quan phù hợp hoặc client tự áp dụng giá trị tương thích. Nếu ghi đè các thuộc tính này, hãy kiểm tra cấu hình thực tế khi producer khởi tạo.

Idempotence bảo vệ retry của Kafka producer trong phạm vi producer session. Nó không tự nhận diện hai lần gọi send riêng biệt từ code nghiệp vụ là cùng một event. Ví dụ, nếu ứng dụng nhận timeout rồi gọi publish(event) lần nữa, lần gọi thứ hai có thể được xem là một lần gửi mới.

Đối với event nghiệp vụ quan trọng:

- Gán eventId ổn định trước khi gửi.
- Dùng idempotent producer để bảo vệ retry nội bộ.
- Không tạo eventId mới khi chỉ đang phục hồi cùng một lần phát event.
- Thiết kế consumer idempotent để xử lý trường hợp ứng dụng gửi lại sau khi không xác định được kết quả lần trước.
- Ghi log eventId cùng lỗi gửi để có thể điều tra và đối chiếu.

Không nên dùng request timeout thấp rồi liên tục gửi lại từ tầng nghiệp vụ. Cách đó có thể biến một sự cố mạng ngắn thành nhiều record trùng.

## 7. Chọn giá trị request.timeout.ms

Không có một con số phù hợp cho mọi cụm Kafka. Hãy chọn giá trị dựa trên thời gian phản hồi thực tế, mức chịu lỗi và thời hạn mà ứng dụng cần nhận kết quả.

### Khi giá trị quá thấp

Giá trị thấp có thể gây ra:

- Request bị xem là thất bại trong khi broker vẫn đang xử lý.
- Retry tăng khi broker chịu tải cao hoặc replication chậm.
- Nhiều request lặp lại làm tăng tải mạng và broker.
- Ứng dụng nhận lỗi sớm hơn khả năng phục hồi thực tế của cụm.
- Kết quả gửi trở nên khó diễn giải nếu ứng dụng tự phát lại record.

Ví dụ, nếu broker thường cần 8 đến 12 giây để phản hồi khi cụm đang phục hồi, đặt request timeout ở mức 2 giây có thể khiến producer liên tục hết hạn và retry trong chính giai đoạn cụm cần giảm tải.

### Khi giá trị quá cao

Giá trị cao có thể gây ra:

- Phát hiện broker không phản hồi chậm.
- Future của record giữ trạng thái chờ lâu hơn.
- Ứng dụng phải giữ nhiều công việc đang chờ kết quả.
- Thời gian phục hồi và xử lý lỗi kéo dài.
- Các tầng gọi phía trên có thể hết timeout trước producer, tạo ra nhiều trạng thái chờ không đồng nhất.

Ví dụ, nếu API gọi producer chỉ cho phép 10 giây nhưng request timeout của Kafka là 90 giây, API có thể đã trả lỗi cho client trong khi producer vẫn tiếp tục gửi. Nếu client thử lại thao tác nghiệp vụ, hệ thống cần cơ chế idempotency để tránh tạo hiệu ứng trùng.

### Quy trình chọn giá trị

1. Đo request latency của producer trong điều kiện tải bình thường và tải cao.
2. Xác định thời gian phản hồi có thể chấp nhận khi broker leader thay đổi hoặc ISR biến động.
3. Đặt request timeout đủ lớn để tránh timeout giả do độ trễ thông thường.
4. Đặt delivery timeout lớn hơn hoặc bằng request timeout cộng linger.
5. So sánh delivery timeout với timeout ở các tầng gọi phía trên.
6. Kiểm tra replica.lag.time.max.ms khi dùng acks=all.
7. Chạy thử với broker chậm, mất kết nối và leader failover để quan sát retry và thời gian báo lỗi.
8. Theo dõi tỷ lệ retry, lỗi gửi và độ trễ sau khi triển khai.

Ví dụ 45 giây cho request timeout và 120 giây cho delivery timeout có thể là điểm bắt đầu để thử nghiệm trong một hệ thống cần thời gian phục hồi tương đối rộng. Hãy điều chỉnh theo số liệu của cụm và phiên bản client; không sao chép các giá trị này mà không đo kiểm.

## 8. Quan sát và xử lý sự cố

Khi producer báo timeout, hãy phân biệt lỗi phản hồi, lỗi kết nối, lỗi xác nhận replica và lỗi hết tổng thời gian giao record.

Một số tín hiệu nên theo dõi:

| Chỉ số hoặc tín hiệu | Ý nghĩa vận hành |
|---|---|
| request-latency-avg | Độ trễ phản hồi request trung bình |
| request-latency-max | Độ trễ phản hồi request lớn nhất |
| record-retry-rate | Tần suất record phải retry |
| record-error-rate | Tỷ lệ record gửi lỗi |
| record-send-rate | Tốc độ record được gửi |
| requests-in-flight | Số request đang chờ xử lý/phản hồi |
| bufferpool-wait-time | Thời gian producer chờ buffer |
| Log timeout và delivery failure | Thời điểm, loại lỗi và record liên quan |

Tên metric thực tế có thể khác theo phiên bản Kafka client, exporter và hệ thống metrics. Với Spring Kafka, có thể tích hợp Micrometer để xuất các chỉ số producer và theo dõi cùng log ứng dụng.

Khi điều tra một đợt timeout, kiểm tra theo thứ tự:

1. **Mạng và kết nối:** packet loss, DNS, firewall, kết nối TCP, thời gian thiết lập kết nối và lỗi broker disconnect.
2. **Broker:** request handler saturation, CPU, disk latency, network throughput, request queue và log của broker.
3. **Replication:** ISR shrink, replica lag, under-replicated partitions và min.insync.replicas.
4. **Producer:** request latency, retry rate, error rate, buffer pool wait và số request đang in-flight.
5. **Cấu hình thời gian:** request.timeout.ms, delivery.timeout.ms, linger.ms, max.block.ms và timeout ở tầng gọi ứng dụng.
6. **Kết quả nghiệp vụ:** eventId, trạng thái future, metadata record nếu thành công và lịch sử phát lại.

### Một số tình huống thường gặp

**Broker chậm nhưng vẫn phục hồi**

Request timeout quá thấp có thể khiến producer retry liên tục. Kiểm tra latency và tải broker trước khi tăng timeout. Nếu độ trễ tăng do broker quá tải, tăng timeout chỉ giúp tránh lỗi sớm; nó không xử lý nguyên nhân quá tải.

**Leader partition thay đổi**

Trong lúc leader election, producer có thể gặp lỗi kết nối hoặc lỗi có thể retry. Retry và idempotence giúp producer phục hồi theo cơ chế Kafka. Delivery timeout vẫn giới hạn tổng thời gian chờ của record.

**ISR không đáp ứng min.insync.replicas**

Với acks=all, broker có thể từ chối ghi khi không đủ replica đồng bộ. Đây là lỗi về điều kiện durability, không đơn thuần là request timeout. Tăng request timeout không thể tạo thêm replica trong ISR; cần khôi phục replication hoặc xem lại chính sách khả dụng/durability.

**Future hoàn tất lỗi sau một khoảng chờ dài**

Kiểm tra exception gốc, thời gian từ khi gửi đến khi lỗi và các metric retry. Nếu lỗi là do delivery timeout, record đã vượt tổng ngân sách giao. Nếu code ứng dụng chỉ hết thời gian chờ ở Future.get, producer có thể vẫn đang xử lý record.

**Producer buffer đầy**

Nếu lời gọi send chờ buffer quá lâu, xem max.block.ms, buffer.memory, batch size, tốc độ broker nhận dữ liệu và khả năng tiêu thụ của mạng. request.timeout.ms không phải cấu hình xử lý buffer exhaustion.

## 9. Các nguyên tắc cấu hình an toàn

- Đặt request.timeout.ms theo độ trễ broker và mạng có đo lường.
- Đảm bảo delivery.timeout.ms lớn hơn hoặc bằng request.timeout.ms cộng linger.ms.
- Dùng acks=all khi cần durability cao và đặt min.insync.replicas phù hợp với số replica.
- Bật idempotent producer nếu yêu cầu retry an toàn.
- Không coi timeout là bằng chứng record chưa được ghi.
- Không tự gửi lại một event bằng một lần send mới nếu chưa có eventId ổn định và chính sách chống trùng.
- Phân biệt timeout ở Kafka client với timeout do Future.get hoặc tầng HTTP gọi producer.
- Theo dõi retry rate, request latency, buffer wait và delivery errors.
- Thử nghiệm broker chậm, mất kết nối, leader change và ISR shrink trước khi chốt cấu hình production.
- Khi dùng nhiều ProducerFactory, xác nhận KafkaTemplate thực sự sử dụng factory có request.timeout.ms mong muốn.

## 10. Ví dụ cấu hình hoàn chỉnh và cách đọc

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[request.timeout.ms]": 45000
        "[delivery.timeout.ms]": 120000
        "[linger.ms]": 5
~~~

Đọc cấu hình theo từng lớp:

- Producer chờ tối đa 45 giây cho phản hồi của một request.
- Producer có tổng ngân sách giao record 120 giây kể từ khi send trả về.
- Producer có thể gom record trong khoảng linger đã cấu hình trước khi gửi batch.
- Producer yêu cầu acknowledgement theo ISR.
- Producer bật idempotence để Kafka xử lý an toàn retry nội bộ.

Nếu broker phản hồi trong 200 ms, request thường hoàn tất nhanh hơn giới hạn 45 giây. Timeout là giới hạn trên cho việc chờ phản hồi, không phải thời gian producer cố ý đợi trước mỗi lần gửi.

Nếu broker không phản hồi, producer có thể retry trong giới hạn retry và delivery timeout. Khi tổng thời gian giao vượt delivery timeout, future báo lỗi. Nếu ứng dụng nhận lỗi rồi phát lại bằng một lệnh send độc lập, cần dựa vào eventId và idempotent consumer để xử lý khả năng record đầu tiên đã được broker ghi.

Trong vận hành Spring Kafka, request.timeout.ms cần được xem cùng delivery.timeout.ms, retry, acks, idempotence và timeout của các tầng gọi ứng dụng. Cấu hình đúng giúp producer chịu được độ trễ và lỗi tạm thời, đồng thời báo lỗi trong khoảng thời gian mà hệ thống có thể quan sát và phục hồi.
