# Resume an toàn sau incident

Trong hệ thống Spring Kafka, **pause** giúp tạm ngừng nhận thêm record khi ứng dụng hoặc một dependency đang gặp sự cố. Khi nguyên nhân incident đã được xử lý, thao tác **resume** cho phép container hoặc từng partition tiếp tục tiêu thụ dữ liệu. Tuy nhiên, resume không chỉ là gọi một API để “chạy lại”: backlog có thể đã tích tụ, record cũ có thể sắp hết thời gian retention, downstream có thể vừa phục hồi nhưng chưa chịu được tải cao, và một số event có thể đã tạo side effect trước khi lỗi xuất hiện.

**Resume an toàn sau incident** là quy trình phục hồi có kiểm soát: xác nhận điều kiện sẵn sàng, hiểu trạng thái pause thực tế, khôi phục consumption theo từng mức tải, theo dõi tác động rồi có phương án pause trở lại nếu sức khỏe hệ thống suy giảm. Mục tiêu không phải làm consumer lag về 0 càng nhanh càng tốt bằng mọi giá, mà là **đưa dữ liệu trở lại luồng xử lý mà không gây incident lần hai, không bỏ sót record và không tạo hiệu ứng nghiệp vụ trùng không kiểm soát**.

Bài học nằm trong chương **Pause và backpressure** của Spring Kafka Reliability Operations. Các ví dụ dùng Spring Kafka listener container, consumer group, topic-partition và môi trường Kubernetes; quy tắc cốt lõi cũng áp dụng cho ứng dụng chạy VM hoặc bare metal.

## 1. Tình huống điển hình

Giả sử service `payment-worker` đọc topic `payment-requests`, partition 0–5. Khi payment gateway bắt đầu trả lỗi timeout, ứng dụng chủ động pause consumption để tránh tiếp tục gửi request vào dependency đang quá tải.

```text
T0 — Bình thường

payment-requests (6 partitions)
       |
       v
payment-worker consumers
       |
       v
Payment gateway — healthy

T1 — Incident

Payment gateway timeout tăng
       |
       v
Pause listener / một số partitions
       |
       v
Kafka tiếp tục lưu record mới
       |
       v
Consumer lag tích tụ

T2 — Dependency được sửa

Không resume toàn bộ ngay lập tức
       |
       v
Kiểm tra readiness + offset + in-flight state
       |
       v
Resume theo từng nhóm partition
       |
       v
Theo dõi retry, gateway latency, lag, DLT
       |
       v
Mở rộng đến tải bình thường
```

Nếu đồng thời resume sáu partition khi gateway mới phục hồi, service có thể tạo một đợt request dồn dập, khiến gateway lại timeout. Nếu chờ quá lâu, record cũ có thể vượt thời gian retention. Vì vậy, kế hoạch khôi phục phải cân đối **tốc độ catch-up**, **sức khỏe dependency**, **thứ tự xử lý**, và **khả năng khôi phục khi một bước thất bại**.

## 2. Hiểu đúng pause/resume trong Spring Kafka

Spring Kafka hỗ trợ pause/resume ở mức container và mức partition thông qua `MessageListenerContainer`.

```java
// Tạm dừng/toàn bộ container theo API Spring Kafka.
container.pause();
container.resume();

// Tạm dừng/tái mở một topic-partition cụ thể.
TopicPartition tp = new TopicPartition("payment-requests", 2);
container.pausePartition(tp);
container.resumePartition(tp);
```

| Thao tác | Tác dụng chính | Không tự thực hiện |
|---|---|---|
| `pause()` | Yêu cầu container ngừng tiêu thụ thêm từ các partition được quản lý. | Không stop JVM, không commit offset, không hủy công việc đang chạy. |
| `resume()` | Bỏ yêu cầu pause ở mức container, cho phép container tiếp tục poll record. | Không sửa dependency, không thay đổi offset, không giải quyết poison record. |
| `pausePartition(tp)` | Yêu cầu pause riêng partition. | Không thu hồi assignment, không chuyển partition sang member khác. |
| `resumePartition(tp)` | Bỏ yêu cầu pause của một partition. | Không tự resume các partition khác hay một lệnh pause còn hiệu lực ở mức container. |
| `stop()` | Dừng lifecycle container theo chính sách được cấu hình. | Không tương đương pause; có thể làm consumer rời group. |

**Resume là yêu cầu bất đồng bộ về mặt áp dụng.** Container thường áp dụng thay đổi tại ranh giới vòng `poll()` thích hợp; phương thức Java trả về không bảo đảm cùng thời điểm record đã được fetch trở lại.

Hai trạng thái khác nhau cần được theo dõi:

```java
boolean requested = container.isPauseRequested();
boolean applied = container.isContainerPaused();

TopicPartition tp = new TopicPartition("payment-requests", 2);
boolean partitionRequested =
        container.isPartitionPauseRequested(tp);
boolean partitionPaused =
        container.isPartitionPaused(tp);
```

`isPauseRequested()` phản ánh yêu cầu pause toàn container; `isContainerPaused()` phản ánh trạng thái container đã áp dụng theo API Spring Kafka. Với partition, cặp `isPartitionPauseRequested` và `isPartitionPaused` cho phép phân biệt yêu cầu với trạng thái thực tế.

Khi xử lý incident, cần báo cáo chính xác:

- **Resume requested:** đã gửi yêu cầu mở lại consumption.
- **Resume applied:** container không còn ở trạng thái pause đối với phạm vi cần mở.
- **Consumption healthy:** record thực sự được xử lý và offset tiến với tỷ lệ lỗi chấp nhận được.

Ba điều trên **không tương đương**. Không thông báo “hệ thống đã phục hồi” chỉ vì một lời gọi `resume()` trả về bình thường.

## 3. Những gì pause không đảm bảo

Kafka consumer vẫn sở hữu partition khi tạm pause. Group membership thường được duy trì nhờ container tiếp tục `poll()`, thay vì để thread đứng yên vô hạn. Trong thời gian pause:

1. Producer vẫn có thể ghi thêm record vào Kafka.
2. Consumer lag của partition bị pause có thể tăng.
3. Các record đã lấy từ lần poll trước có thể còn đang xử lý.
4. Transaction hoặc retry đã bắt đầu có thể đang hoàn tất hoặc abort.
5. Offset không tự commit chỉ vì pause/resume.
6. Consumer group vẫn có thể rebalance nếu instance restart, poll timeout hoặc membership thay đổi.

Khi resume, consumer tiếp tục theo **vị trí đọc và committed offset thực tế**, không tự quay về thời điểm bắt đầu incident. Một số record đã xử lý nhưng chưa commit có thể được giao lại sau crash; ứng dụng phải chịu được at-least-once delivery và idempotency theo nghiệp vụ.

Ví dụ:

```text
Trước incident:
  committed offset = 100
  log end offset   = 120

Trong incident:
  pause applied
  producer gửi thêm 80 record

Sau incident:
  committed offset = 100  (nếu không có commit thêm)
  log end offset   = 200
  lag              = 100

resume() -> consumer có thể lấy các record chưa xử lý
            từ vị trí hợp lệ theo trạng thái consumer
```

Không tự gọi `seek()` tới log end offset để “bỏ backlog” nếu nghiệp vụ cần xử lý các record đang chờ. Seek và offset reset là thao tác có nguy cơ mất dữ liệu và cần quyết định riêng.

## 4. Điều kiện tiên quyết trước khi resume

Một incident được đánh dấu “resolved” trong hệ thống ticket **chưa đủ**. Nên lập các **readiness gates** (điều kiện mở lại) độc lập với thao tác kỹ thuật:

| Nhóm điều kiện | Câu hỏi phải trả lời | Bằng chứng mong đợi |
|---|---|---|
| Root cause | Nguyên nhân incident đã được khắc phục hay chỉ tạm thời giảm lỗi? | Deploy/config fix, kết quả test, health của dependency. |
| Dependency capacity | Downstream có chịu được traffic tăng dần không? | Error rate, p95/p99 latency, pool saturation, quota. |
| Consumer health | Container, pod, consumer group và assignment có ổn định? | Pod ready, không crash loop, lag/assignment được quan sát. |
| Offset & retention | Backlog có còn nằm trong Kafka không, có nguy cơ mất record do retention không? | Committed offset, log start/end offset, tuổi record. |
| In-flight work | Có transaction, callback hoặc job đã lấy record trước pause còn đang chạy không? | In-flight counter, transaction state, worker queue depth. |
| Data correctness | Có poison record, schema incompatibility hoặc dữ liệu cần sửa trước replay không? | Kết quả kiểm tra sample và DLT. |
| Idempotency | Record giao lại có thể tạo side effect trùng không? | Unique constraint, event ID, inbox, API idempotency key. |
| Rollback | Có thể pause trở lại nhanh nếu metric xấu đi không? | Owner, quyền vận hành, API/feature flag đã xác nhận. |

Không nhất thiết mọi hệ thống đều có cùng chỉ số hoặc ngưỡng. Với giao dịch tài chính, điều kiện idempotency và đối soát có thể là bắt buộc; với telemetry không quan trọng, có thể ưu tiên khôi phục thông lượng. Các ngưỡng nên lấy từ SLO, sức chứa dependency và yêu cầu lưu trữ dữ liệu.

## 5. Khôi phục dependency trước, rồi mới mở lại Kafka

Nếu lý do pause là database connection pool cạn hoặc HTTP gateway timeout, trước tiên xác nhận **dịch vụ đích có thể nhận tải thật**. Một health check trả HTTP 200 chỉ chứng minh endpoint trả lời, không bảo đảm service xử lý được backlog.

Nên kết hợp:

- Readiness/liveness chỉ ra service và dependency kết nối được.
- Một request canary hoặc giao dịch thử ở mức lưu lượng nhỏ hoàn tất.
- Error rate và latency ổn định qua một khoảng quan sát.
- Connection pool, thread pool, queue depth, rate limit/quota còn headroom.
- Không còn một deployment chưa hoàn tất hoặc cấu hình đang thay đổi giữa các instance.
- DLT/retry từ incident trước được phân loại, không đồng thời replay bừa bãi với backlog chính.

Một cách vận hành hiệu quả là **giữ rate limiter/circuit breaker ở downstream callsite** ngay cả sau khi resume. Pause chỉ điều khiển lượng record mới đến listener; nó không đủ để giới hạn chính xác mỗi giây có bao nhiêu request HTTP hoặc SQL nếu listener xử lý nhiều record đồng thời.

## 6. Kiểm tra consumer group và partition ownership

Trước khi resume, cần xác định partition nào thuộc consumer nào. Với một Kafka topic có nhiều partition, assignment có thể thay đổi trong incident do pod restart hoặc rolling update.

Ví dụ lệnh quan sát:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group payment-worker

kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group payment-worker \
  --members --verbose
```

Các lệnh hỗ trợ xác định group members, partition assignment, committed offset, log-end offset và lag theo khả năng của phiên bản Kafka CLI đang dùng. Tuy nhiên, **Kafka CLI thông thường không biết một partition đã bị pause bởi Spring container hay chưa**. Trạng thái pause cần được đọc từ Spring Kafka container API, application events hoặc metric riêng của ứng dụng.

Trong Kubernetes:

```bash
kubectl get pods -l app=payment-worker -o wide
kubectl logs -l app=payment-worker --since=15m --prefix=true
```

Kiểm tra log assignment, rebalance, pause/resume, consumer error, transaction abort, producer fencing và lỗi dependency. Nếu một partition đã chuyển owner sang pod mới, việc gọi resume trên **pod cũ** có thể không thay đổi consumption thực tế.

Với `@KafkaListener(concurrency = "4")`, Spring Kafka có thể tạo nhiều child container trong một JVM. Không dựa vào suy luận “partition N luôn thuộc child N”; partition owner chịu ảnh hưởng của assignor, số member và rebalance.

## 7. Kiểm tra lag, offset và giới hạn retention

Lag giúp ước lượng lượng công việc cần catch-up sau resume, nhưng không phản ánh đầy đủ độ khó xử lý của từng record.

```text
Topic payment-requests, partition 2:

committed offset = 2500
log end offset   = 12500
lag              = 10000 record
```

Nếu producer tiếp tục ghi 200 record/giây và consumer sau resume xử lý được 500 record/giây trên partition đó, tốc độ giảm backlog lý thuyết là:

```text
Net catch-up = 500 - 200 = 300 record/giây
Backlog      = 10.000 record
Thời gian ước lượng ≈ 10.000 / 300 ≈ 33,3 giây
```

Đây là tính toán **minh họa**, không phải SLA thực tế: record có thể tốn thời gian khác nhau, retry có thể tạo tải bổ sung và throughput không cố định. Nếu tốc độ xử lý bằng hoặc thấp hơn tốc độ producer, lag sẽ không giảm dù consumer đã resume.

Đặc biệt cần xem **log start offset** và chính sách retention. Nếu partition bị pause lâu hơn thời gian giữ dữ liệu hoặc log bị compaction, một số record cũ có thể không còn tồn tại. Không nên coi `auto.offset.reset=earliest` là cách khôi phục dữ liệu đã bị xóa: `earliest` chỉ chọn offset sớm nhất **còn được lưu**, không phục hồi record đã hết retention.

Trước khi resume, xác nhận committed offset còn hợp lệ. Nếu offset không còn trong log, incident chuyển thành bài toán **khôi phục dữ liệu từ nguồn khác** hoặc quyết định nghiệp vụ chấp nhận mất dữ liệu; không chỉ đơn thuần là thao tác resume.

## 8. Một service điều khiển resume bằng Spring Kafka

Có thể khai báo `id` cố định cho listener để truy xuất container qua `KafkaListenerEndpointRegistry`:

```java
@Component
public class PaymentRequestListener {

    @KafkaListener(
        id = "payment-requests-listener",
        topics = "payment-requests",
        groupId = "payment-worker",
        concurrency = "3"
    )
    public void onRecord(ConsumerRecord<String, String> record) {
        paymentService.process(record.key(), record.value());
    }
}
```

Service quản lý trạng thái:

```java
@Service
public class PaymentListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public PaymentListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void requestResumeAll() {
        container().resume();
    }

    public void requestResumePartition(int partition) {
        TopicPartition tp =
                new TopicPartition("payment-requests", partition);
        container().resumePartition(tp);
    }

    public boolean isResumeApplied(int partition) {
        TopicPartition tp =
                new TopicPartition("payment-requests", partition);
        MessageListenerContainer c = container();

        return !c.isPartitionPauseRequested(tp)
                && !c.isPartitionPaused(tp)
                && !c.isPauseRequested();
    }

    public void requestPausePartition(int partition) {
        TopicPartition tp =
                new TopicPartition("payment-requests", partition);
        container().pausePartition(tp);
    }

    private MessageListenerContainer container() {
        MessageListenerContainer c =
                registry.getListenerContainer("payment-requests-listener");
        if (c == null) {
            throw new IllegalStateException("Listener not registered");
        }
        return c;
    }
}
```

Các import cần dùng:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
```

**Giới hạn quan trọng của ví dụ:** `isResumeApplied` chỉ đọc các cờ pause cục bộ của container; nó **không tự chứng minh partition đang assigned, container đang running hoặc offset thực sự tiến**. Với hệ thống nhiều pod, phải kiểm tra đúng owner và kết hợp metric consumption. Nếu toàn container vẫn còn một yêu cầu pause hoặc container đã stop, gọi `resumePartition` riêng có thể chưa đủ để nhận record.

Hệ thống thực tế nên tách hai endpoint/operation: **đặt desired state** (request) và **xác minh applied state** (quan sát), thay vì đồng bộ trả về “resumed successfully” ngay sau khi gọi method.

## 9. Phục hồi nhiều pod: desired state là nguồn sự thật

Trong một deployment nhiều replica, `KafkaListenerEndpointRegistry` chỉ nhìn thấy container trong **JVM hiện tại**. Một lệnh `resume()` trên pod A không đồng nghĩa pod B cũng resume, và partition có thể đổi owner vì rebalance.

Nếu incident pause ở cấp toàn hệ thống, nên lưu **desired state** trong một control plane hoặc database có quyền truy cập phù hợp:

```text
Control plane
  incident_id = INC-4821
  generation  = 12
  desired_paused_partitions = {payment-requests-2, payment-requests-4}
                 |
                 v
         Reconciler trên mỗi pod
                 |
       +---------+---------+
       |                   |
       v                   v
     Pod A               Pod B
  current assignment  current assignment
       |                   |
       v                   v
  Áp dụng pause/resume theo owner thực tế
```

Khi operator mở `payment-requests-2`, control plane thay đổi desired state và tăng generation. Các instance đọc generation mới, nhận biết assignment của mình rồi áp dụng pause/resume phù hợp. Nếu partition chuyển sang pod mới, owner mới cũng cần reconcile.

Thiết kế này tránh hai rủi ro:

- **Mất pause khi restart:** pod mới khởi động không tự nhớ yêu cầu pause chỉ lưu trong RAM của pod cũ.
- **Resume nhầm owner:** command đi vào một instance không còn sở hữu partition đó.

Cần bảo đảm quyền thay đổi desired state được kiểm soát, có audit trail (người thực hiện, incident ID, thời gian, lý do), và tránh lệnh **resume cũ** ghi đè một **pause mới** từ incident khác. Có thể dùng generation/version, compare-and-set hoặc lease để kiểm soát race.

Nếu yêu cầu “không xử lý thêm bất cứ record nào trước khi policy pause được xác nhận”, có thể cần thêm gate nghiệp vụ trong listener và logic kiểm soát startup/assignment. Chỉ dựa vào việc một reconciler sớm hay muộn gọi API pause sau khi assignment đã xảy ra là chưa đủ để bảo đảm tuyệt đối không có record lọt qua.

## 10. Resume theo từng đợt, không tạo thundering herd

Khi backlog lớn, resume tất cả partition có thể tạo một **traffic spike** vượt năng lực dependency. Cách an toàn thường là mở theo đợt:

```text
Giai đoạn A: một partition / một canary instance
                    |
                    v
      Đo error rate, latency, throughput
                    |
             Đạt readiness gate?
               /          \
             Không          Có
              |             |
              v             v
           Pause lại   Giai đoạn B: thêm partitions
                              |
                              v
                       Theo dõi và tăng dần
                              |
                              v
                      Mở toàn bộ khi ổn định
```

Ví dụ runbook có thể mở một partition ở giai đoạn canary, rồi hai partition tiếp theo sau một cửa sổ quan sát, và cuối cùng mở phần còn lại. **Số lượng partition và thời gian quan sát là tham số vận hành**, không có một công thức mặc định cho mọi workload.

Ở tầng dependency, nên điều chỉnh cả:

- Maximum concurrent HTTP/DB calls hoặc semaphore.
- Rate limit theo tenant/partner khi partition chứa nhiều key khác nhau.
- Consumer concurrency và `max.poll.records` nếu thực sự cần thay đổi kích thước đợt xử lý.
- Timeout và retry/backoff để tránh nhân tải lên dependency vừa hồi phục.
- Circuit breaker và bulkhead để một nhóm lỗi không làm nghẽn toàn hệ thống.

Pause/resume không tự tạo rate limiting chính xác. Một partition có thể chứa hàng triệu record và một listener xử lý nhanh vẫn có thể bắn traffic lớn ngay khi được resume. Phải có giới hạn phù hợp tại điểm gọi dependency.

## 11. Ngưỡng dừng và tự động pause lại

Trước khi resume, xác định **stop conditions** và người có quyền kích hoạt lại pause. Ví dụ:

| Chỉ số | Điều kiện cần giám sát | Hành động khi vượt ngưỡng |
|---|---|---|
| Dependency error rate | Tăng kéo dài vượt mức chịu đựng đã định. | Pause đợt đang mở, giữ các partition khác đang dừng. |
| p95/p99 latency | Tăng mạnh sau khi backlog bắt đầu chạy. | Giảm tốc gọi downstream hoặc pause bớt partition. |
| Connection pool/queue depth | Tiến gần mức bão hòa. | Giới hạn concurrency, dừng tăng tải. |
| Listener retry/exception | Record lỗi tăng bất thường. | Kiểm tra dữ liệu, classifier và DLT; không mở thêm đợt. |
| DLT ingress | Record bị recover sang DLT nhiều. | Kiểm tra correctness, có thể dừng resume. |
| Transaction abort/commit errors | Transactional listener không commit ổn định. | Pause, điều tra coordinator/fencing/timeout. |
| Consumer lag | Không giảm dù đã mở đủ một khoảng đo. | Kiểm tra throughput thực tế và dependency, tránh scale mù. |

Ngưỡng phải có **hysteresis** để tránh pause/resume liên tục quanh một giá trị. Ví dụ ngưỡng pause dựa trên latency cao và ngưỡng resume thấp hơn, đồng thời yêu cầu ổn định trong một khoảng thời gian. Những giá trị này nên được định nghĩa bởi SLO thực tế, không hard-code giống nhau cho mọi service.

Hệ thống có thể tự động pause lại khi điều kiện xấu rõ ràng, nhưng cần giới hạn số chu kỳ tự động, có cảnh báo và có thể chuyển sang chế độ operator intervention nếu lỗi lặp liên tục.

## 12. Xử lý poison record và schema error trước khi mở lại

Không phải incident nào cũng do dependency quá tải. Nếu một record gây `DeserializationException`, `ValidationException` hoặc lỗi nghiệp vụ vĩnh viễn, resume có thể đưa consumer về cùng record rồi thất bại lặp lại.

### Lỗi trước khi vào listener

Deserialization xảy ra trong Kafka consumer `poll()`. Nếu payload sai wire format hoặc schema không tồn tại, `@KafkaListener` có thể chưa được gọi. Với Spring Kafka, `ErrorHandlingDeserializer` giúp container chuyển lỗi deserialize vào nhánh error handling thay vì để consumer mắc kẹt tại `poll()`.

### Lỗi trong listener

`DefaultErrorHandler` có thể retry theo `BackOff` và chuyển record sang recoverer khi cạn. Với non-blocking retry, một record có thể đã được đưa sang retry topic hoặc DLT; resume topic chính không đồng nghĩa resume toàn bộ retry/DLT workflow.

Trước resume cần quyết định:

1. Dữ liệu đã sửa hoặc code có thể xử lý record cũ chưa?
2. Lỗi transient nên retry bao nhiêu lần trước khi recovery?
3. Lỗi permanent có được đưa sang DLT cùng metadata nguồn không?
4. DLT producer có serializer/ACL/topic phù hợp, kể cả `byte[]` khi deserialize lỗi không?
5. Có runbook kiểm soát replay để tránh vòng lặp poison record không?

**Đừng dùng resume như một vòng retry vô hạn.** Nếu lỗi vĩnh viễn chưa được xử lý, cần fix contract, phân loại exception hoặc chuyển record sang quy trình recovery có kiểm soát.

## 13. Idempotency và side effect khi record được giao lại

Một consumer có thể đã hoàn tất bước gọi payment gateway nhưng crash trước khi commit offset. Khi resume hoặc restart, cùng record có thể được giao lại và gọi gateway lần nữa.

```text
Kafka record OrderPaymentRequested
             |
             v
Payment gateway trả SUCCESS
             |
             X process crash trước commit offset
             |
             v
Consumer đọc lại record khi phục hồi
             |
             v
Nguy cơ charge hai lần nếu không idempotent
```

Giải pháp không nằm ở pause/resume mà ở **idempotency**:

- Mỗi event có ID ổn định xuyên retry/replay.
- Khi gọi API ngoài, truyền idempotency key nếu đối tác hỗ trợ.
- Ghi dấu vết xử lý trong database với unique constraint và cùng transaction với side effect DB.
- Xử lý trạng thái “đã gọi API nhưng chưa nhận xác nhận” bằng reconciliation, không quyết định charge lại mù.
- Với transactional Kafka listener, nhớ rằng Kafka transaction không bao phủ transaction của payment provider hoặc database ngoài Kafka.

Khi incident liên quan side effect không thể lặp, readiness gate phải bao gồm kết quả đối soát các record in-flight. Nếu chưa thể biết record nào đã thanh toán, **chưa nên resume toàn bộ**.

## 14. Application events và log trạng thái

Spring Kafka có các application event liên quan việc consumer hoặc partition được pause/resume. Tùy phiên bản, có thể dùng `ConsumerPausedEvent`, `ConsumerResumedEvent` hoặc `ConsumerPartitionPausedEvent`, `ConsumerPartitionResumedEvent`.

Ví dụ logging:

```java
@Component
public class KafkaPauseResumeEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPauseResumeEvents.class);

    @EventListener
    public void onResumed(ConsumerPartitionResumedEvent event) {
        log.info("Kafka partition resume applied: {}", event);
    }

    @EventListener
    public void onPaused(ConsumerPartitionPausedEvent event) {
        log.warn("Kafka partition pause applied: {}", event);
    }
}
```

Các import:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPartitionPausedEvent;
import org.springframework.kafka.event.ConsumerPartitionResumedEvent;
import org.springframework.stereotype.Component;
```

Application event giúp xác nhận trạng thái đã áp dụng ở phía container. Tuy nhiên, event này **không chứng minh listener đã xử lý record thành công sau resume**; hãy đối chiếu committed offset, throughput, error rate và business metrics.

Một structured log hữu ích khi điều phối incident:

```text
incident_id=INC-4821
action=RESUME_PARTITION
topic=payment-requests
partition=2
consumer_group=payment-worker
instance=payment-worker-pod-3
control_generation=12
requested_state=ACTIVE
applied_state=ACTIVE
reason=payment-gateway-recovered
```

Đây là schema log minh họa; không phải format mặc định của Spring Kafka. Hãy thêm timestamp, actor và correlation ID phù hợp, không log payload chứa dữ liệu nhạy cảm.

## 15. Định nghĩa phục hồi thành công bằng metric

Đánh giá recovery cần nhiều góc nhìn:

| Tín hiệu | Ý nghĩa | Kết luận không nên rút ra một mình |
|---|---|---|
| Container pause state | Request resume đã được áp dụng ở nơi quan sát. | Không chứng minh record đã xử lý xong. |
| Assigned partitions | Consumer có quyền đọc partition hiện tại. | Không có nghĩa partition chưa bị pause. |
| Committed offset | Group đã ghi nhận tiến độ. | Không bảo đảm side effect ngoài Kafka đúng nếu listener thiếu idempotency. |
| Lag theo partition | Lượng backlog còn lại theo offset. | Không cho biết từng event đúng nghiệp vụ hay không. |
| Processing throughput | Tốc độ hoàn tất record. | Không phản ánh tỷ lệ event lỗi sang DLT. |
| Retry/DLT rate | Mức thất bại và recovery. | DLT tăng có thể che giấu sự cố dù lag topic chính giảm. |
| Dependency saturation | Rủi ro quá tải trở lại. | Health tốt trong vài giây chưa chắc ổn dưới full load. |
| Event age | Độ trễ dữ liệu và nguy cơ vi phạm SLA/retention. | Lag thấp không luôn có nghĩa dữ liệu mới. |

Một điều kiện “recovery complete” có thể là: mọi partition cần mở đều ở trạng thái active trên owner thực tế, committed offset tăng ổn định, lag giảm về phạm vi mục tiêu, tỷ lệ lỗi/DTL không tăng bất thường, dependency còn headroom và không phát hiện dữ liệu bị bỏ qua. Cách viết chính xác và ngưỡng là quyết định của ứng dụng.

## 16. Runbook resume sau incident

Quy trình sau giả định incident đã được xác định, và việc pause trước đó có chủ đích.

### Giai đoạn A — Chuẩn bị

1. **Khóa phạm vi:** ghi incident ID, topic, group, danh sách partition đang pause và các instance liên quan.
2. **Xác nhận root cause:** dependency/code/config đã được sửa và có bằng chứng ở môi trường tương ứng.
3. **Kiểm tra an toàn dữ liệu:** committed offset, log start/end, tuổi record, retry/DLT, các side effect nghi ngờ đã xử lý một phần.
4. **Kiểm tra tài nguyên:** pod ổn định, group assignment không rebalance liên tục, CPU/thread/connection pool còn headroom.
5. **Đặt stop conditions:** ngưỡng lỗi, latency, retry, DLT và cách pause lại.
6. **Xác nhận quyền điều khiển:** operator hoặc control plane có thể gửi lệnh tới owner partition đúng và ghi audit.

### Giai đoạn B — Resume canary

7. Chọn **một partition hoặc một phạm vi tải nhỏ** đại diện và cập nhật desired state sang active.
8. Gọi `resumePartition(tp)` trên container owner, hoặc để reconciler trên các pod áp dụng desired state.
9. Chờ `isPartitionPauseRequested(tp) == false` và `isPartitionPaused(tp) == false` trên owner hợp lệ; nếu container vẫn pause toàn cục thì xử lý yêu cầu pause đó riêng.
10. Theo dõi committed offset, throughput, dependency error rate, latency, retry/DLT và in-flight jobs trong cửa sổ quan sát đã định.
11. Nếu vượt ngưỡng, pause lại canary và điều tra; không mở các partition còn lại.

### Giai đoạn C — Mở rộng và hoàn tất

12. Khi canary ổn định, mở thêm partition theo từng đợt; giữa các đợt xác nhận dependency headroom và lag giảm như dự kiến.
13. Kiểm tra desired/applied state sau bất kỳ rebalance hoặc rolling deployment nào.
14. Khi tất cả partition cần xử lý đã resume, tiếp tục giám sát cho đến khi backlog và event age trở về giới hạn nghiệp vụ.
15. Đối soát các event có rủi ro duplicate/partial side effect, xử lý DLT và cập nhật incident timeline.
16. Chỉ đánh dấu incident hoàn tất khi **consumption + nghiệp vụ + dependency** đều đạt điều kiện phục hồi đã xác định.

Không biến runbook thành một script đơn giản “resume all; sleep 30; done”. Khi lượng backlog và độ nhạy nghiệp vụ thay đổi, điều kiện canary và thứ tự mở partition cần thay đổi tương ứng.

## 17. Khi nào nên pause lại?

Ngay sau resume, có thể xuất hiện triệu chứng dependency sắp sụp lần nữa hoặc code mới vẫn lỗi với dữ liệu cũ. Khi ấy:

```text
Resume batch N
       |
       v
Error rate / latency / DLT vượt stop condition
       |
       v
Pause batch N hoặc các partition bị ảnh hưởng
       |
       v
Đợi pause applied; quản lý in-flight work
       |
       v
Điều tra; giảm rate limit/concurrency hoặc sửa dữ liệu
       |
       v
Quay lại readiness gates trước lần resume tiếp theo
```

Đừng coi pause lại là thất bại của runbook: đây là một cơ chế bảo vệ được thiết kế trước. Cũng không tự động resume lại ngay khi metric giảm một chút nếu chưa có hysteresis và thời gian ổn định.

Nếu số partition pause liên tục tăng, hoặc mỗi lần resume chỉ giữ được vài giây, cần dừng mở rộng, nâng mức incident và điều tra nguyên nhân gốc. Việc liên tục bật/tắt có thể tạo burst traffic, retry storm và khó xác định record đã tạo side effect đến đâu.

## 18. Lỗi thường gặp khi resume

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Gọi `resume()` nhưng không thấy record mới | Container stopped, chưa assigned, pause per-partition vẫn còn, hoặc topic không có backlog. | Kiểm tra container lifecycle, assignment, requested/applied state và offsets. |
| Resume một partition nhưng lag không giảm | Consumer đang xử lý chậm, dependency lỗi, record poison, hoặc tốc độ producer cao hơn tốc độ xử lý. | Xem throughput, retry/DLT, dependency, lag theo partition. |
| Chỉ một pod hoạt động trở lại | Lệnh gửi tới một registry cục bộ, không phải tất cả owner. | Dùng desired state toàn deployment và reconcile theo assignment. |
| Partition đổi owner và tự chạy khi vẫn cần pause | Desired pause chỉ lưu trong pod cũ hoặc race khi rebalance. | Lưu state bền vững, áp lại lúc assignment/startup, có generation/version. |
| Sau resume thấy xử lý trùng | Record đã tạo side effect trước crash nhưng offset chưa commit. | Dùng event ID, inbox/unique constraint và API idempotency key. |
| DLT tăng mạnh ngay sau resume | Dữ liệu cũ vẫn không tương thích hoặc lỗi nghiệp vụ chưa sửa. | Dừng mở rộng, xem classifier, schema và recoverer. |
| Consumer liên tục rebalance | Listener/blocking retry quá lâu, poll interval, pod restart hoặc network. | Kiểm tra `max.poll.interval.ms`, log group và thời gian xử lý. |
| Offset không còn hợp lệ | Record cũ đã vượt retention hoặc bị log cleanup loại bỏ. | Xác định log start, kế hoạch phục hồi nguồn, không reset offset tùy tiện. |
| Gateway vừa phục hồi lại timeout | Thundering herd khi resume tất cả partitions cùng lúc. | Pause có chọn lọc, ramp-up theo đợt và giới hạn concurrency/rate. |

## 19. Kiểm thử resume an toàn trước production

Có thể dựng integration test với Kafka Testcontainers hoặc embedded Kafka để mô phỏng pause, resume và record backlog.

Một kịch bản cơ bản:

1. Tạo topic có nhiều partition, consumer group thử nghiệm và listener ID cố định.
2. Gửi record baseline và xác nhận các partition đã được assigned.
3. Pause một hoặc nhiều partition bằng container API.
4. Chờ trạng thái pause **applied** thay vì chỉ đợi một `Thread.sleep` cố định.
5. Publish thêm record vào cả partition paused và active; xác nhận active vẫn được xử lý.
6. Giả lập dependency hồi phục và gọi resume ở một partition.
7. Xác nhận requested/applied state chuyển sang active, record tồn đọng được tiêu thụ và offset tiến.
8. Tạo lỗi transient để kiểm tra retry/backoff, DLT và stop condition.
9. Nếu có nhiều instance, gây rebalance/restart để kiểm tra desired state được áp dụng lại đúng owner.
10. Mô phỏng side effect thành công rồi crash trước commit để kiểm tra idempotency.

Các bài test phải hiểu **in-flight records**: có thể có record đã poll trước khi pause. Không assert “không một listener invocation nào xảy ra kể từ thời điểm gọi pause” nếu chưa xác nhận trạng thái pause áp dụng và công việc cũ đã kết thúc.

Không dùng môi trường production để giả lập mất offset, force fencing hay reset group chỉ nhằm kiểm tra runbook. Hãy dùng topic/group cô lập và dependency giả lập.

## 20. Nguyên tắc vận hành

- Resume là **quy trình có điều kiện**, không chỉ một lời gọi API.
- Kiểm tra dependency, consumer health, dữ liệu, retention, idempotency và đường rollback trước khi mở lại.
- Phân biệt **resume requested**, **resume applied** và **consumption healthy**.
- Dùng Spring Kafka container API thay vì thao tác trực tiếp `KafkaConsumer` từ thread ngoài.
- Không suy ra partition đã resume chỉ từ Kafka assignment hay lag.
- Với nhiều pod, áp dụng desired state trên **owner hiện tại** và reconcile sau rebalance/restart.
- Không reset offset hoặc seek đến cuối để xóa backlog khi chưa có quyết định nghiệp vụ.
- Ưu tiên **canary và ramp-up từng đợt**, có rate limit, hysteresis và stop conditions.
- Theo dõi committed offset, lag, tuổi record, dependency saturation, retry, DLT và transaction errors cùng nhau.
- Dùng event ID/idempotency để xử lý record có thể bị giao lại sau crash hoặc resume.
- Giữ audit log về lý do pause/resume, incident ID, người thực hiện và trạng thái đã áp dụng.
- Có runbook pause lại và khôi phục dữ liệu nếu retention đã vượt giới hạn.

**Resume an toàn sau incident** hoàn tất khi việc tiêu thụ đã chạy trở lại **đúng phạm vi**, với tốc độ nằm trong năng lực downstream, committed offset và business outcome tiến triển hợp lệ, và không tạo ra một đợt lỗi mới. Spring Kafka cung cấp cơ chế pause/resume; mức độ tin cậy thực sự phụ thuộc vào readiness gates, kiểm soát tải, quan sát toàn bộ luồng xử lý và khả năng ứng phó nếu recovery không diễn ra như dự kiến.
