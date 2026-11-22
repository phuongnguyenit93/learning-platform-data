# Kết hợp blocking và non-blocking retry

Trong Spring Kafka, **blocking retry** và **non-blocking retry** xử lý lỗi ở hai nhịp khác nhau. Blocking retry thử lại một record ngay trong luồng xử lý của listener container, thường với một vài khoảng chờ ngắn. Non-blocking retry chuyển record thất bại sang retry topic, để consumer của topic chính tiếp tục xử lý và record lỗi được thử lại sau một khoảng trễ dài hơn.

Kết hợp hai cơ chế tạo thành chính sách retry nhiều tầng: **thử lại nhanh vài lần cho lỗi thoáng qua; nếu lỗi kéo dài, chuyển sang retry topic để chờ lâu hơn; nếu vẫn không thành công hoặc lỗi không thể retry, thực hiện recovery như gửi Dead Letter Topic (DLT)**. Thiết kế này có thể giảm độ trễ cho lỗi ngắn, hạn chế giữ partition chính khi dependency bị gián đoạn và cho phép kiểm soát backlog. Đổi lại, nó làm tăng số lần thực thi nghiệp vụ, độ phức tạp vận hành và nguy cơ thay đổi thứ tự xử lý.

Bài học tập trung vào listener Spring Kafka trong mô hình reliability, đặc biệt là điều kiện chọn từng tầng retry, cấu hình, ảnh hưởng đến offset, tính idempotent, thứ tự record và cách quan sát hệ thống.

## 1. Hai cơ chế retry khác nhau ở đâu?

### 1.1. Blocking retry

Với blocking retry, listener xử lý record và ném exception. Error handler chờ theo BackOff rồi giao lại record để listener xử lý, thường trước khi tiếp tục các record phía sau theo trình tự xử lý của container.

~~~text
orders (partition 1)
    |
    v
Listener xử lý record A
    |
    +-- lỗi --> chờ ngắn --> thử A lần 2
                                  |
                                  +-- lỗi --> chờ ngắn --> thử A lần 3
                                                            |
                                                            +-- thành công
~~~

Đây là lựa chọn phù hợp khi lỗi có thể tự hết trong vài trăm mili giây hoặc vài giây: kết nối database vừa reset, một dependency đang thay leader, hoặc lần gọi API bị timeout ngắn.

Ưu điểm là không cần publish record sang topic khác cho mỗi lỗi nhỏ và dễ giữ thứ tự trong partition hơn. Hạn chế là consumer thread và partition bị ảnh hưởng trong lúc retry. Nếu mỗi lần xử lý hoặc backoff quá lâu, throughput giảm, lag có thể tăng và chu kỳ poll phải được quản lý cẩn thận.

### 1.2. Non-blocking retry

Với non-blocking retry, khi quá trình xử lý ở một tầng thất bại, framework có thể publish record sang retry topic. Một consumer riêng của retry topic xử lý record sau thời gian delay được cấu hình. Consumer chính tiếp tục nhận record khác.

~~~text
orders ----> listener chính
                 |
                 +-- lỗi --> orders-retry-2000
                                  |
                                chờ 2s
                                  |
                                  v
                              listener retry
                                  |
                                  +-- lỗi --> orders-retry-8000
                                                    |
                                                  chờ 8s
                                                    |
                                                    v
                                                listener retry
                                                    |
                                                    +-- hết retry --> orders-dlt
~~~

Non-blocking retry thích hợp khi dependency thường cần nhiều giây hoặc vài phút để phục hồi. Nó tránh việc một record lỗi giữ consumer của topic chính trong toàn bộ thời gian chờ. Tuy nhiên, record được chuyển sang retry topic có thể hoàn thành **sau** những record mới hơn của cùng key. Vì vậy, không được mặc định cơ chế này giữ đúng ordering của partition gốc.

### 1.3. Bảng đối chiếu

| Tiêu chí | Blocking retry | Non-blocking retry |
|---|---|---|
| Nơi chờ | Luồng xử lý/container theo BackOff | Retry topic và consumer của tầng retry |
| Độ trễ phù hợp | Thường ngắn | Có thể dài hơn |
| Tác động consumer chính | Có thể trì hoãn xử lý record phía sau | Consumer chính có thể tiếp tục |
| Topic bổ sung | Không bắt buộc | Cần retry topic, thường có DLT |
| Thứ tự theo partition gốc | Dễ kiểm soát hơn | Có thể thay đổi |
| Chi phí vận hành | Ít topic hơn | Thêm topic, group, lag, ACL và retention |
| Recovery | Error handler/recoverer | Retry topic, DLT và recovery policy |
| Rủi ro duplicate | Có khi listener được gọi lại | Có cả retry lẫn publish/commit chuyển tầng |

## 2. Vì sao kết hợp cả hai?

Một hệ thống dùng **chỉ blocking retry** có thể giữ consumer rất lâu nếu downstream gặp outage kéo dài. Ngược lại, nếu mọi lỗi đều đi thẳng sang retry topic, một lỗi kết nối kéo dài 100 ms cũng tạo thêm publish, ghi log, poll, vận hành retry topic và tăng độ trễ không cần thiết.

Kết hợp hai tầng giúp phù hợp với phân phối thời gian phục hồi thực tế:

1. Lỗi lần đầu: listener thử xử lý.
2. Lỗi transient ngắn: thử thêm một vài lần tại chỗ với backoff ngắn.
3. Vẫn lỗi: publish record sang retry topic có delay dài hơn.
4. Ở mỗi retry topic, framework có thể áp dụng lại chính sách blocking retry đã cấu hình cho các exception được chọn.
5. Sau khi hết số lần non-blocking retry hoặc gặp lỗi fatal, gửi tới DLT/recoverer theo cấu hình.

Mô hình thường được gọi là **hybrid retry**. Blocking retry xử lý lỗi ngắn; non-blocking retry hấp thụ lỗi kéo dài và tạo thời gian cho dependency phục hồi.

Không nên dùng hybrid retry chỉ vì có sẵn hai API. Nếu nghiệp vụ cần giữ thứ tự nghiêm ngặt, có transaction của listener container hoặc không chấp nhận độ trễ nhiều tầng, cần đánh giá giới hạn trước khi chọn.

## 3. Luồng tổng thể

Giả sử consumer xử lý event OrderCreated và gọi Inventory API. Ứng dụng cho phép hai lần blocking retry với delay 300 ms và có hai chặng retry topic với delay lớn hơn.

~~~text
orders
  |
  v
Listener A (lần đầu)
  |
  +-- transient error --> chờ 300ms --> local retry 1
                                             |
                                             +-- lỗi --> chờ 300ms --> local retry 2
                                                                       |
                                                                       +-- vẫn lỗi
                                                                               |
                                                                               v
                                                                       Publish retry topic
                                                                               |
                                                                               v
                                                                    orders-retry (delay dài)
                                                                               |
                                                                               v
                                                                    Listener retry stage
                                                                               |
                                                             local retries nếu có cấu hình
                                                                               |
                                                                               +-- thành công
                                                                               |
                                                                               +-- vẫn lỗi
                                                                                       |
                                                                                       v
                                                                              Retry stage tiếp
                                                                                       |
                                                                                hết attempts
                                                                                       |
                                                                                       v
                                                                                   orders-dlt
~~~

Các mốc cụ thể phụ thuộc số retry topic, cách framework tái sử dụng topic, classification, số attempts, BackOff và phiên bản Spring Kafka. Sơ đồ minh họa quyết định xử lý; nó không phải cam kết rằng sẽ có chính xác hai retry topic hay mỗi topic luôn chỉ nhận một lần giao.

**Điểm quan trọng:** việc chuyển từ blocking sang non-blocking là một bước publish record mới tới retry topic. Sau đó, consumer của retry topic tiến hành xử lý theo luồng tiêu thụ của nó. Đây không phải một thao tác sleep dài trên thread consumer chính.

## 4. Cấu hình Spring Kafka theo mô hình kết hợp

Spring Kafka có cơ chế retry-topic integration và hỗ trợ cấu hình blocking retries cùng non-blocking retries. Một cách triển khai điển hình trong các phiên bản hỗ trợ là mở rộng **RetryTopicConfigurationSupport** để khai báo exception nào được blocking retry, sau đó dùng **@RetryableTopic** trên listener để định nghĩa các tầng retry không blocking.

Ví dụ minh họa:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;
import org.springframework.kafka.retrytopic.RetryTopicConfigurationSupport;
import org.springframework.kafka.retrytopic.RetryTopicConfigurationSupport.BlockingRetriesConfigurer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
@EnableKafka
public class KafkaRetryConfiguration extends RetryTopicConfigurationSupport {

    @Override
    protected void configureBlockingRetries(
            BlockingRetriesConfigurer blockingRetries) {

        blockingRetries
            .retryOn(InventoryTemporarilyUnavailableException.class)
            .backOff(new FixedBackOff(300L, 2L));
    }
}
~~~

Ví dụ chỉ định rằng **InventoryTemporarilyUnavailableException** được thử lại ở tầng blocking với hai lần retry bổ sung, mỗi lần chờ 300 ms. Những exception khác được xử lý theo classifier và policy tương ứng.

Tiếp theo, khai báo non-blocking retry trên listener:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.annotation.RetryableTopic;
import org.springframework.retry.annotation.Backoff;

@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 2_000,
        multiplier = 2.0,
        maxDelay = 10_000
    ),
    exclude = {
        InvalidOrderEventException.class,
        UnsupportedEventVersionException.class
    }
)
@KafkaListener(
    topics = "orders.events",
    groupId = "inventory-service"
)
public void onOrderEvent(OrderEvent event) {
    inventoryService.reserve(event);
}
~~~

Ở đây, annotation mô tả các lần giao record ở tầng non-blocking. Trong nhiều phiên bản Spring Kafka, **attempts** của @RetryableTopic đếm tổng số lần non-blocking delivery, bao gồm lần xử lý ban đầu; cần xác nhận semantics chính xác với phiên bản đang chạy. Blocking retries là các lần thử bên trong mỗi lần delivery đó và có thể làm tổng số lần gọi listener lớn hơn attempts.

Để cấu hình retry topic bằng cách kế thừa RetryTopicConfigurationSupport, tránh đồng thời kích hoạt cơ chế khai báo cấu hình retry topic khác tạo trùng hạ tầng, ví dụ dùng **@EnableKafkaRetryTopic** cùng lớp cấu hình kế thừa khi tài liệu phiên bản yêu cầu chọn một. Hãy kiểm tra cấu hình bean retry-topic thực tế của ứng dụng.

Các tên API, package và khả năng kết hợp cụ thể phụ thuộc phiên bản Spring Kafka. Ví dụ trình bày cấu trúc cần thiết; code ứng dụng còn phải có các exception domain, service, KafkaTemplate và cấu hình topic/serializer phù hợp.

## 5. Số attempts thực tế có thể lớn hơn dự kiến

Một lỗi cấu hình phổ biến là xem attempts của @RetryableTopic như tổng số lần listener có thể được gọi. Khi kết hợp blocking retry, mỗi lần giao record từ topic chính hoặc retry topic có thể kích hoạt thêm các lần thử tại chỗ.

Ví dụ giả định:

- Non-blocking policy có 4 lần delivery, gồm 1 ở topic chính và các lần tiếp theo ở retry topics.
- Mỗi delivery cho phép tối đa 2 lần blocking retry bổ sung với exception thuộc nhóm được cấu hình.
- Mọi lần đều lỗi và cùng exception tiếp tục được phân loại retryable.

Tổng số lần gọi listener theo mô hình lý tưởng có thể lên tới:

~~~text
total_listener_calls
    = number_of_non_blocking_deliveries
      × (1 + blocking_retries_per_delivery)

    = 4 × (1 + 2)
    = 12 lần
~~~

Đây là **ước lượng theo cấu hình**, không phải giới hạn cứng cho mọi tình huống. Consumer restart, rebalance, commit failure, publish retry-topic failure hoặc các cơ chế redelivery khác có thể khiến record được nhìn thấy thêm lần nữa. Classification cũng có thể khiến blocking chỉ áp dụng ở một số lần hoặc loại exception.

Nếu listener gọi HTTP API hoặc cập nhật database ở mỗi lần thử, có thể có nhiều lần thực thi side effect hơn dự kiến. Hãy tính ngân sách retry theo **tổng số lần xử lý thực tế**, bao gồm mọi tầng.

## 6. Classification: lỗi nào retry tại chỗ, lỗi nào chuyển tầng?

Hybrid retry hiệu quả khi policy phân loại lỗi phản ánh thời gian phục hồi và bản chất nguyên nhân.

| Trường hợp | Blocking retry ngắn | Non-blocking retry | Recovery |
|---|---|---|---|
| Database vừa reset kết nối | Phù hợp | Nếu vẫn lỗi có thể chuyển tầng | DLT hoặc alert sau khi hết policy |
| HTTP 503 do deploy | Có thể thử vài lần | Phù hợp nếu outage kéo dài | DLT/workflow sau deadline |
| HTTP 429 có Retry-After lớn | Ít hoặc không cần | Phù hợp nếu delay theo server | Xem lại quota khi quá hạn |
| JSON không deserialize được | Thường không | Không nếu payload sai cố định | DLT sớm và sửa schema/payload |
| Business rule từ chối dữ liệu | Thường không | Chỉ khi trạng thái có thể thay đổi | DLT hoặc quy trình từ chối |
| ACL/credential sai | Không có giá trị khi điều kiện không đổi | Không nên lặp vô hạn | Sửa bảo mật/cấu hình |
| HTTP request kết quả chưa rõ | Phải kiểm tra idempotency | Chỉ retry khi an toàn | Đối soát trạng thái |

Có thể chia exception thành ba nhóm:

**Nhóm A — lỗi thoáng qua:** một vài blocking retries thường đủ. Ví dụ kết nối database mất vài trăm mili giây.

**Nhóm B — lỗi phục hồi chậm:** retry tại chỗ ít lần hoặc bỏ qua blocking rồi chuyển retry topic. Ví dụ service đang bảo trì hoặc bị throttling.

**Nhóm C — lỗi không retry được:** đưa ngay vào DLT/recoverer hoặc xử lý riêng. Ví dụ payload không hợp lệ và không thể tự sửa.

Không phân loại chỉ bằng chuỗi exception message. Nên dùng exception class, nguyên nhân gốc, mã lỗi và hợp đồng dependency. Một TimeoutException có thể transient, nhưng cũng có thể do endpoint cấu hình sai và sẽ không tự hết.

## 7. Blocking retry dùng DefaultErrorHandler như thế nào?

Với listener non-transactional, **DefaultErrorHandler** là cơ chế cốt lõi cho retry blocking và recovery. Trong hệ thống đã bật retry-topic support, framework tạo/cấu hình các thành phần cần thiết để chuyển record từ blocking retries sang non-blocking destinations.

Khi cấu hình hybrid bằng **RetryTopicConfigurationSupport.configureBlockingRetries**, framework biết exception nào cần được retry ngay và dùng BackOff tương ứng. Sau khi blocking retry cạn hoặc exception không thuộc nhóm blocking, luồng retry topic có thể thực hiện publish theo chính sách non-blocking.

Đừng mặc định rằng chỉ cần tự tạo một bean DefaultErrorHandler toàn cục với FixedBackOff là nó sẽ tự động chuyển record sang retry topic. Việc publish sang retry topic cần recoverer/destination routing do retry-topic infrastructure cấu hình. Nếu ghi đè handler sai cách, ứng dụng có thể chỉ retry tại chỗ rồi log, dừng hoặc recovery sai đích.

Nếu dự án có nhiều listener container factory, hãy xác định rõ factory nào áp dụng retry-topic configuration và blocking policy. Kiểm tra listener sử dụng container factory nào, bởi một error handler đặt ở factory A không nhất thiết ảnh hưởng listener đang dùng factory B.

## 8. BackOff của hai tầng cần khác nhau

Tầng blocking thường có khoảng chờ ngắn; tầng non-blocking thường chờ dài hơn. Ví dụ:

| Tầng | Ví dụ | Mục tiêu |
|---|---|---|
| Blocking retry 1 | 200 ms | Phục hồi lỗi cực ngắn |
| Blocking retry 2 | 400 ms | Tránh lập tức chuyển topic |
| Retry topic 1 | 3 giây | Chờ dependency ổn định |
| Retry topic 2 | 15 giây | Giảm áp lực khi outage kéo dài |
| Retry topic 3 | 60 giây | Cho phép hồi phục trước recovery |
| DLT | Sau khi hết chính sách | Lưu lỗi để xử lý riêng |

Đây là lịch minh họa, không phải cấu hình mặc định của framework. Backoff thực tế còn phụ thuộc số lần retry, multiplier, giới hạn interval, độ trễ poll và tải của retry consumers.

Một cấu hình không phù hợp là mỗi tầng blocking chờ 30 giây, rồi non-blocking chỉ chờ 1 giây: nó giữ consumer chính lâu mà lại tạo các lần chuyển retry topic quá sát nhau. Hãy thiết kế trên cơ sở một ngân sách thời gian chung.

### 8.1. Ước lượng thời gian đến recovery

Một ước lượng đơn giản:

~~~text
T_total
  ≈ Σ(thời gian xử lý của từng lần listener được gọi)
    + Σ(blocking_backoff mỗi delivery)
    + Σ(non_blocking_delay giữa các retry topic)
    + T_publish_and_poll_overhead
~~~

Giả sử có 3 deliveries, mỗi delivery tối đa 3 lần gọi listener, mỗi lần có thể chờ HTTP timeout 2 giây; blocking chờ 200 ms và 400 ms trong mỗi delivery; non-blocking delays lần lượt 5 giây và 20 giây.

~~~text
T_processing_max  = 3 deliveries × 3 calls × 2s = 18s
T_blocking_wait   = 3 deliveries × (0.2s + 0.4s) = 1.8s
T_retry_topics    = 5s + 20s = 25s
T_total_ước_lượng ≈ 44.8s + overhead
~~~

Đó là thời gian của một luồng thử liên tục khi mỗi lần đều gặp timeout. Nếu có rebalance, outage hoặc backlog retry topic, thời gian thực tế có thể dài hơn đáng kể.

## 9. max.poll.interval.ms và thời gian chờ blocking

Kafka consumer cần tiếp tục poll trong giới hạn **max.poll.interval.ms**. Blocking retries và thời gian xử lý trong listener ảnh hưởng đến khả năng duy trì nhịp poll. Nếu một lần xử lý hoặc chuỗi backoff giữ consumer không poll đủ lâu, group có thể rebalance và partition được giao lại.

Spring Kafka có các cơ chế backoff handling, bao gồm cách cho container tiếp tục poll trong thời gian chờ ở một số cấu hình. Ví dụ **ContainerPausingBackOffHandler** có thể hỗ trợ các khoảng chờ dài bằng cách pause container thay vì giữ luồng theo cách gây vượt poll interval. Hành vi cụ thể phụ thuộc phiên bản và cấu hình error handler.

Nguyên tắc vận hành:

- Đặt timeout hữu hạn cho database/HTTP dependency.
- Giữ blocking retries ngắn và có giới hạn.
- Đo thời gian xử lý toàn poll, kể cả retry và commit.
- Chuyển lỗi cần chờ lâu sang retry topic.
- Theo dõi rebalance, poll interval và commit latency.
- Không tăng max.poll.interval.ms vô hạn để che một tác vụ treo.

Non-blocking retry giúp giải phóng consumer chính sớm hơn, nhưng retry consumers cũng có max.poll.interval.ms riêng. Nếu blocking policy được áp dụng lại tại mỗi retry topic, mỗi retry consumer vẫn cần giữ nhịp poll.

## 10. Offset commit khi record chuyển sang retry topic

Đây là phần quan trọng nhất của reliability. Khi listener chính xử lý thất bại và framework chuyển record sang retry topic, có hai kết quả cần phối hợp:

1. Record cần được publish sang topic retry để có thể được xử lý sau.
2. Offset trên topic gốc cần được ghi nhận theo recovery policy để consumer chính tiếp tục.

~~~text
Topic gốc: orders partition 0 offset 100
                  |
                  v
               Listener
                  |
                  +-- lỗi, hết blocking retries
                              |
                              v
                     Publish orders-retry
                              |
                         thành công?
                         /       \
                       Có       Không
                       |          |
                       v          v
                Recovery thành   Xử lý lỗi publish,
                công; offset     tránh bỏ qua record
                gốc tiến lên     trước khi lưu được
                theo policy      bản sao retry
~~~

Spring Kafka retry-topic infrastructure điều phối publish sang retry topic và recovery của record gốc. Tuy nhiên, **một lần publish Kafka và một lần commit offset consumer thông thường không tự động là một transaction nguyên tử chung**.

Ví dụ cửa sổ lỗi: publish sang retry topic đã thành công nhưng ứng dụng dừng trước khi offset topic gốc được commit. Sau restart, record ở topic gốc có thể được giao lại và publish sang retry topic thêm lần nữa. Do đó, ngay cả khi framework xử lý lỗi đúng, ứng dụng vẫn phải chịu được duplicate theo delivery semantics thực tế.

Nếu publish sang retry topic không thành công, cần để quá trình xử lý lỗi tuân theo recovery behavior của framework; không tự commit offset gốc chỉ để lag giảm. Cần biết cấu hình xác nhận send và cơ chế xử lý lỗi publish đang dùng.

## 11. Idempotency là yêu cầu bắt buộc về mặt nghiệp vụ

Hybrid retry có thể gọi listener nhiều lần ở cùng hoặc khác topic. Một lần xử lý có thể đã ghi database hoặc gọi HTTP thành công nhưng exception xảy ra trước khi offset được commit hoặc trước khi hệ thống ghi nhận kết quả. Khi retry, side effect có thể lặp.

Ví dụ listener nhận PaymentRequested:

~~~text
Nhận PaymentRequested(eventId=evt-417)
      |
      v
Gọi Payment API: thành công
      |
      v
Ứng dụng timeout khi ghi trạng thái
      |
      v
Record được retry tại chỗ hoặc qua retry topic
      |
      v
Gọi Payment API lần hai nếu không có idempotency
~~~

Hướng thiết kế:

- Mỗi event có **event ID** ổn định và được giữ nguyên qua các tầng retry.
- Với database, dùng unique constraint/inbox table để ghi nhận event đã xử lý.
- Ghi trạng thái processed và thay đổi nghiệp vụ trong **cùng database transaction**.
- Với HTTP API hỗ trợ idempotency key, gửi cùng key ở mọi lần retry.
- Với thao tác có kết quả không rõ, đối soát trạng thái trước khi phát lại.

Ví dụ bảng đơn giản:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong một database transaction, ứng dụng thực hiện insert event ID theo cơ chế unique constraint rồi cập nhật nghiệp vụ. Nếu ID đã tồn tại, handler không thực hiện side effect lần nữa. Chỉ kiểm tra SELECT rồi INSERT tách rời không đủ để tránh race condition.

Idempotent producer của Kafka bảo vệ một số retry ở protocol producer; nó không tự coi hai lần publish nghiệp vụ độc lập là một event duy nhất. Vì vậy, cần idempotency ở boundary nghiệp vụ.

## 12. Thứ tự record có thể thay đổi

Kafka bảo đảm thứ tự theo partition trong log gốc, nhưng chuyển record sang retry topic sẽ thay đổi luồng tiêu thụ. Ví dụ:

~~~text
orders (cùng key order-7):
    Created(v1) ---> Paid(v2) ---> Cancelled(v3)
          |
          +-- xử lý lỗi, chuyển sang orders-retry

orders listener tiếp tục:
    Paid(v2) ---> Cancelled(v3)

orders-retry listener xử lý Created(v1) sau
~~~

Nếu business logic yêu cầu Created phải được áp dụng trước Paid, trạng thái có thể sai. Blocking retry giữ record ở luồng chính lâu hơn và do đó dễ bảo toàn thứ tự xử lý; non-blocking retry ưu tiên tiến độ của topic chính và chấp nhận khả năng out-of-order.

Các chiến lược giảm rủi ro:

- Dùng aggregate version hoặc sequence number và từ chối cập nhật lỗi thứ tự.
- Thiết kế handler idempotent và có thể xử lý event đến muộn khi nghiệp vụ cho phép.
- Giữ blocking retry có giới hạn ở luồng bắt buộc ordering, rồi đưa lỗi lâu dài sang quy trình can thiệp thay vì cho record sau vượt qua.
- Tách các loại event có yêu cầu ordering khác nhau.
- Đối với workflow nghiêm ngặt, cân nhắc state machine/saga hoặc xử lý tuần tự theo key tại một service chuyên biệt.

Không nên quảng bá non-blocking retry như một giải pháp vừa giữ throughput vừa giữ nguyên ordering cho mọi nghiệp vụ; hai thuộc tính này có thể xung đột trong trường hợp record lỗi.

## 13. DLT và điểm kết thúc của quá trình retry

Khi non-blocking attempts hết, framework có thể chuyển record sang DLT. Với record permanent, có thể chọn skip các tầng retry và đưa trực tiếp sang DLT theo classification.

Một DLT record nên đủ thông tin để xử lý sau:

- Original topic, partition và offset.
- Event ID/business key, schema version.
- Exception class, root cause và message được làm sạch.
- Thời điểm lỗi, số lần delivery và retry metadata nếu có.
- Source group/correlation ID để tra cứu trace.

Spring Kafka hỗ trợ **@DltHandler** để xử lý DLT trong retry-topic pattern:

~~~java
@DltHandler
public void handleDlt(OrderEvent event) {
    log.error("Event routed to DLT: id={}", event.eventId());
    // Ghi trạng thái điều tra, alert hoặc chuyển sang hệ thống xử lý lỗi.
}
~~~

Phương thức DLT handler cần được đặt đúng trong bean/listener mà retry-topic infrastructure tìm kiếm và có serializer/deserializer tương ứng. Chỉ log DLT mà không có dashboard và quy trình xử lý lại sẽ khiến lỗi tích tụ.

Cần phân biệt:

- **Recovery thành công:** record đã được chuyển DLT hoặc xử lý theo chính sách.
- **Nghiệp vụ thành công:** side effect được hoàn tất.

Một record ở DLT thường được xem là hoàn tất về mặt retry routing, nhưng chưa hoàn tất nghiệp vụ. Quy trình vận hành phải có cách sửa và replay nếu dữ liệu còn giá trị.

## 14. Khi chuyển DLT thất bại

DLT cũng là một Kafka topic và có thể gặp lỗi authorization, serialization, broker outage hoặc timeout. Nếu DLT publish thất bại mà ứng dụng vẫn commit offset gốc, record có nguy cơ bị bỏ qua khỏi quy trình khôi phục.

Policy cần xác định:

1. Recoverer có xác nhận publish thành công theo yêu cầu không?
2. Nếu publish thất bại, record có được redeliver/retry recovery hay không?
3. Offset gốc có bị commit trước thời điểm recovery an toàn không?
4. Có alert riêng cho DLT publish failure không?
5. Có khả năng tìm và replay lại record gốc từ Kafka nếu cần không?

Các mặc định về kiểm tra send result, commit recovered và error-handler recovery behavior phụ thuộc phiên bản/configuration. Hãy dựa vào hợp đồng Spring Kafka thực tế thay vì suy luận rằng chỉ cấu hình topic DLT đã tạo bảo đảm no-loss.

## 15. Giới hạn: batch listener và Kafka transaction

Non-blocking retry topics có những giới hạn quan trọng trong Spring Kafka. Theo thiết kế và các phiên bản phổ biến, **non-blocking retries không hỗ trợ batch listener và không dùng kết hợp với container transactions** theo cách dùng tiêu chuẩn của retry-topic infrastructure.

Với batch listener, việc tách record lỗi ra retry topic có semantics khác so với record listener. Nếu ứng dụng có listener nhận cả batch, cần xem xét giới hạn của phiên bản Spring Kafka hoặc thay đổi mô hình thành record listener để dùng @RetryableTopic.

Với Kafka transaction do listener container quản lý, offset input và output Kafka có thể được commit/abort cùng transaction. Non-blocking retry theo mô hình chuyển record sang retry topic là một luồng recovery khác và không thể mặc định ghép trực tiếp với container transaction để nhận cùng bảo đảm nguyên tử.

Nếu cần xử lý transactional consume-transform-produce:

- Dùng transaction manager và cơ chế rollback/retry tương ứng, chẳng hạn DefaultAfterRollbackProcessor theo phiên bản.
- Phân biệt retry record trong transaction với publish sang retry topic ngoài transaction.
- Nếu mục tiêu là phối hợp database và Kafka, cân nhắc transactional outbox/inbox hoặc workflow riêng.
- Không gắn @RetryableTopic vào transactional listener rồi giả định EOS vẫn được giữ nguyên.

Kiểm tra giới hạn và API theo đúng phiên bản thư viện, vì các tiện ích và chế độ hỗ trợ có thể thay đổi theo thời gian.

## 16. Tham số cần cấu hình cùng nhau

| Tham số/cơ chế | Ý nghĩa | Lưu ý khi kết hợp |
|---|---|---|
| Blocking retry count | Số lần thử lại ngay trong listener/container | Nhân với số lần retry-topic delivery có thể làm tổng số lần xử lý lớn |
| Blocking BackOff | Chờ giữa các lần retry tại chỗ | Giữ ngắn, tính vào poll budget |
| @RetryableTopic attempts | Ngưỡng attempts ở tầng non-blocking | Xác minh có tính lần ban đầu theo phiên bản |
| Non-blocking delay/backoff | Khoảng chờ giữa các retry deliveries | Không bảo đảm thời điểm xử lý chính xác tới mili giây |
| Exception classification | Quyết định retry hay recovery | Tách transient và permanent; có thể khác theo tầng |
| max.poll.interval.ms | Khoảng thời gian tối đa giữa poll | Bị ảnh hưởng bởi xử lý/blocking retry |
| AckMode | Thời điểm container ghi nhận offset | Phải khớp recovery policy |
| Retry topic retention | Thời gian Kafka giữ retry record | Phải lớn hơn thời gian chờ/outage dự kiến |
| DLT retention | Thời gian giữ record lỗi để điều tra | Cần quy trình replay |
| Concurrency | Số consumer/container xử lý song song | Có thể tăng tải lên dependency khi retry đồng loạt |
| Idempotency key | Nhận diện một nghiệp vụ qua mọi lần xử lý | Phải giữ nguyên qua các tầng |

Chọn cấu hình dựa trên SLO: thời gian tối đa trước khi nghiệp vụ thành công hoặc chuyển recovery, tỷ lệ lỗi transient và khả năng chịu tải của dependency.

## 17. Retry topic, partition và consumer groups

Spring Kafka retry-topic infrastructure thường tạo container riêng cho retry topic và DLT, với tên topic/group được suy ra từ cấu hình. Các retry topic cần được tạo đúng cách, có partition phù hợp, serializer, ACL, replication factor và retention.

Một số điều cần kiểm tra:

- Consumer chính và consumer retry có thể dùng group IDs liên quan nhưng không nên nhầm chúng là cùng một phép commit offset.
- Mỗi retry topic có offset log riêng; committed offset ở topic chính không phải offset của retry topic.
- Bản sao record gửi sang retry topic có topic/partition/offset mới, dù business event ID giữ nguyên.
- Partition gốc và thứ tự của key không tự động được bảo đảm xuyên các retry topic.
- Khi deploy nhiều phiên bản ứng dụng, thay đổi quy tắc naming/attempts có thể làm xuất hiện retry topic cũ/mới; cần theo dõi backlog trước khi xóa topic.

Nếu framework tự tạo retry topics ở môi trường dev, production có thể yêu cầu tạo topic qua IaC để kiểm soát partition, retention, replication và ACL. Tránh phụ thuộc vào auto-create khi cluster production đã khóa quyền tạo topic.

## 18. Backpressure khi lỗi lan rộng

Giả sử Inventory API dừng 10 phút, trong khi orders topic tiếp tục nhận hàng nghìn record mỗi giây. Blocking retry ngắn thất bại rồi mọi record chuyển sang retry topic. Lúc này consumer chính vẫn có thể tiến triển, nhưng retry topic sẽ tích tụ backlog rất nhanh.

Đây là chuyển dịch tải: consumer chính thoát khỏi việc chờ, còn hệ thống retry phải lưu và xử lý các record đó sau khi dependency phục hồi.

Chiến lược bảo vệ:

- Theo dõi tốc độ publish vào retry topic và tốc độ xử lý ra.
- Giới hạn concurrency của retry consumers để không gây retry storm khi API trở lại.
- Dùng exponential backoff và cân nhắc jitter ở tầng thích hợp.
- Dùng circuit breaker hoặc tạm giảm ingress nếu dependency không thể chịu thêm tải.
- Tính dung lượng retention của retry topic cho outage window.
- Đặt alert theo tuổi record, không chỉ tổng lag.
- Lập kế hoạch bắt kịp backlog khi dependency phục hồi.

Nếu retry consumers xử lý 1.000 record/giây còn backlog nhận 2.000 record/giây trong outage, backlog tiếp tục tăng. Sau khi dependency phục hồi, cần processing rate lớn hơn ingress rate để giảm backlog; tăng concurrency chỉ hiệu quả khi downstream còn capacity.

## 19. Quan sát hai tầng retry

Khi chỉ nhìn consumer lag ở topic chính, hệ thống có thể trông khỏe mạnh dù nhiều record đã được chuyển sang retry topics. Vì vậy, dashboard cần tách tiến độ topic chính khỏi toàn bộ pipeline xử lý nghiệp vụ.

| Tín hiệu | Câu hỏi cần trả lời |
|---|---|
| Blocking retry attempts theo exception | Lỗi ngắn có đang tự phục hồi không? |
| Blocking retry success rate | Bao nhiêu record thành công trước khi chuyển topic? |
| Retry topic publish rate | Bao nhiêu record đang rời topic chính để chờ? |
| Retry topic lag | Backlog retry đang nằm ở tầng nào? |
| Oldest retry record age | Record bị trì hoãn bao lâu? |
| Non-blocking attempts/exhausted | Bao nhiêu record sắp vào DLT? |
| DLT publish rate và lag | Bao nhiêu nghiệp vụ chưa xử lý thành công? |
| Consumer rebalance | Blocking retry có gây mất nhịp poll không? |
| Dependency latency/error rate | Nguyên nhân lỗi đã phục hồi chưa? |
| Publish/recovery failures | Có lỗi khi chuyển retry topic hoặc DLT không? |

Log và trace nên giữ business event ID xuyên mọi tầng. Các header retry của Spring Kafka có thể chứa thông tin attempt, topic/exception gốc; tên header phụ thuộc phiên bản. Đừng dùng riêng topic offset mới để nhận diện nghiệp vụ vì mỗi lần publish sang topic khác sẽ có offset mới.

Cần tránh cardinality quá cao khi đưa event ID trực tiếp vào metric label; có thể đưa event ID vào log/trace và giữ metric aggregate theo topic, exception và stage.

## 20. Các tình huống điều tra thường gặp

### 20.1. Blocking retry thành công nhưng latency tăng

Nếu phần lớn record phục hồi sau 1–2 retry tại chỗ, hệ thống có thể chưa cần nhiều retry topics. Tuy nhiên, nếu blocking backoff lớn làm p99 processing latency tăng và lag tăng, hãy giảm blocking attempts hoặc tối ưu dependency.

Xem thời gian xử lý record, retry attempts và lag theo partition. Điều chỉnh initial interval và số lần thử dựa trên phân phối thời gian phục hồi thực tế.

### 20.2. Topic chính không lag nhưng nghiệp vụ chậm

Record có thể đã chuyển sang retry topic và offset gốc được commit. Dashboard chỉ xem group chính sẽ bỏ sót backlog ở retry topics.

Hãy cộng trạng thái xử lý theo event ID, theo dõi retry topic lag và oldest event age. KPI nghiệp vụ nên đo thời điểm event được hoàn tất, không chỉ thời điểm rời topic chính.

### 20.3. Cùng event xuất hiện hai lần ở retry topic

Có thể publish retry đã thành công nhưng commit offset gốc thất bại, hoặc một consumer rebalance làm record gốc được đọc lại. Đừng giả định framework tự loại mọi duplicate giữa topic và offset commit.

Tra event ID, offset gốc, các lần publish và trạng thái side effect. Xác minh idempotency và cách xử lý publish result/commit failure.

### 20.4. Một số record không vào DLT

Kiểm tra attempts, classification, retry policy có còn đang chạy không, retry topic retention, lỗi publish và DLT handler. Một retry policy vô hạn hoặc một exception được phân loại retryable liên tục có thể khiến record không bao giờ chạm giới hạn để được chuyển sang DLT.

### 20.5. Lỗi tăng sau thay đổi schema

Nếu tất cả lần retry đều thất bại do deserialization hoặc validation, đây thường là lỗi dữ liệu/contract không thể sửa bằng backoff. Dùng ErrorHandlingDeserializer khi cần đưa lỗi poll-time deserialization cho container xử lý, cấu hình exception non-retryable và gửi record vào DLT cùng metadata thích hợp.

## 21. Runbook triển khai hybrid retry

Một quy trình triển khai thực tế:

1. **Phân loại lỗi:** xác định lỗi transient ngắn, transient dài và permanent.
2. **Thiết kế retry budget:** đặt số lần blocking retry, delay và giới hạn non-blocking attempts; tính tổng thời gian worst-case.
3. **Đánh giá ordering:** xác định event type/key nào không thể xử lý đảo thứ tự.
4. **Kiểm tra transaction:** xác nhận listener sử dụng non-transactional record container nếu dùng retry-topic pattern tiêu chuẩn.
5. **Cấu hình framework:** khai báo blocking retries trong RetryTopicConfigurationSupport và non-blocking policy qua @RetryableTopic hoặc builder tương ứng.
6. **Chuẩn bị topic:** tạo retry topics/DLT với partition, retention, replication, ACL và serializer phù hợp.
7. **Bảo vệ side effect:** dùng event ID ổn định và idempotency ở database/API.
8. **Thiết lập observability:** đo attempts, lag, oldest age, publish failure và DLT backlog.
9. **Thử các đường lỗi:** lỗi phục hồi ở local retry; lỗi chuyển retry topic; lỗi hết attempts; publish DLT thất bại; restart/rebalance.
10. **Triển khai dần:** theo dõi lượng retry topic phát sinh, throughput và p95/p99 end-to-end latency.

Không cần một policy retry chung cho mọi topic. Các luồng cần thứ tự chặt có thể dùng blocking retry hữu hạn, còn các luồng chấp nhận đảo thứ tự có thể tận dụng non-blocking retry.

## 22. Các lỗi thiết kế thường gặp

| Cách làm | Hậu quả | Hướng điều chỉnh |
|---|---|---|
| Dùng attempts của @RetryableTopic như tổng lần gọi listener | Đánh giá thấp số side effect/retry | Tính thêm blocking retries tại mỗi delivery |
| Blocking retry quá lâu rồi mới chuyển topic | Topic chính vẫn bị chặn, poll cycle dài | Giữ blocking retries ngắn, dùng retry topic cho lỗi kéo dài |
| Mọi exception đều đi qua cả hai tầng | Lỗi permanent làm tăng chi phí và chậm recovery | Phân loại non-retryable và xử lý DLT sớm |
| Ghi đè DefaultErrorHandler không theo retry-topic infrastructure | Record không được định tuyến đúng retry topic | Dùng extension/API chính thức của phiên bản |
| Giả định publish retry + commit offset nguyên tử | Duplicate khi lỗi giữa hai bước | Thiết kế idempotency và kiểm tra recovery |
| Bỏ qua ordering theo key | Event mới hoàn tất trước event cũ | Dùng version/state machine hoặc chọn policy khác |
| Dùng retry topic trên transactional/batch listener khi không hỗ trợ | Không có semantics mong muốn hoặc cấu hình lỗi | Kiểm tra giới hạn, chọn processor/container phù hợp |
| Không theo dõi retry topic lag | KPI topic chính tốt nhưng nghiệp vụ trễ | Theo dõi toàn pipeline, oldest event age |
| Retention retry topic quá ngắn | Record có thể hết hạn trước khi xử lý lại | Tính retention theo outage và backoff |
| Retry đồng loạt sau outage | Dependency vừa phục hồi bị quá tải lại | Giới hạn concurrency, backoff và jitter |
| DLT chỉ ghi log rồi bỏ quên | Permanent errors tích tụ | Có owner, alert và quy trình sửa/replay |

## 23. Checklist trước khi đưa vào production

Trước khi bật hybrid retry, trả lời:

1. Lỗi nào được blocking retry và lỗi nào chuyển thẳng sang retry topic?
2. Permanent exceptions có được loại khỏi cả hai tầng retry không?
3. Mỗi non-blocking delivery có tối đa bao nhiêu blocking attempts?
4. Tổng số lần gọi listener và tổng thời gian tối đa theo cấu hình là bao nhiêu?
5. Blocking backoff có an toàn với max.poll.interval.ms không?
6. Listener có cần giữ ordering theo key/partition không?
7. Retry topic pattern có được hỗ trợ với record listener và transaction configuration hiện tại không?
8. Khi publish retry topic thành công nhưng commit offset gốc thất bại, duplicate được xử lý ra sao?
9. Nếu publish retry topic hoặc DLT thất bại, có giữ khả năng redelivery không?
10. Event ID và idempotency key có được giữ nguyên xuyên tất cả các tầng không?
11. Retry topics có retention, ACL, partition và replication phù hợp không?
12. Dashboard có theo dõi retry topic lag, oldest age và DLT backlog không?
13. Có quy trình xử lý DLT và replay không làm lặp side effect không?
14. Khi dependency outage kéo dài, hệ thống có đủ capacity để giữ backlog và bắt kịp sau phục hồi không?
15. Test đã bao phủ restart, rebalance và lỗi publish/commit ở ranh giới chuyển topic chưa?

Kết hợp blocking và non-blocking retry giúp hệ thống phản ứng nhanh với lỗi thoáng qua và tránh giữ consumer chính quá lâu khi lỗi kéo dài. Giá trị của thiết kế nằm ở việc chọn đúng exception, thời gian chờ và điểm chuyển tầng; tính ổn định thực tế còn phụ thuộc idempotency, quản lý offset, ordering, giới hạn transaction và observability. Khi các ranh giới này rõ ràng, retry hai tầng có thể tăng khả năng phục hồi mà vẫn giữ được cách điều tra và xử lý record thất bại.
