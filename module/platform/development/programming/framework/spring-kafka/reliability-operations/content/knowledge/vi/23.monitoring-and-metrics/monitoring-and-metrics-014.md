# Metric cardinality và tag hygiene

Trong hệ thống Spring Kafka chạy production, monitoring không chỉ là bật Micrometer, cấu hình Prometheus scrape rồi tạo dashboard. **Một metric có số lượng tag values không được kiểm soát có thể sinh ra hàng chục nghìn hoặc hàng triệu time series**, làm tăng bộ nhớ ứng dụng, tải của metrics backend, chi phí lưu trữ, độ trễ truy vấn và nguy cơ monitoring bị quá tải đúng lúc hệ thống Kafka đang gặp sự cố.

**Metric cardinality** mô tả số tổ hợp nhãn khác nhau mà một metric có thể sinh ra. **Tag hygiene** là tập hợp quy tắc đặt tên, chọn tag, giới hạn giá trị, bảo vệ dữ liệu nhạy cảm và quản lý vòng đời của các chuỗi thời gian. Trong Spring Kafka Reliability Operations, tag hygiene quan trọng đặc biệt vì dữ liệu Kafka thường chứa **topic, partition, group ID, client ID, listener ID, transaction ID, event ID, tenant ID, retry topic và exception details**. Một số giá trị phù hợp để làm metric tag; nhiều giá trị khác chỉ nên xuất hiện trong log hoặc trace.

Bài học này giải thích cách tính cardinality, nhận diện những tag có rủi ro, thiết kế metrics cho Kafka consumer/producer/transactions/retry/DLT, sử dụng Micrometer MeterFilter và Observation, tổ chức Prometheus/Actuator, lập ngân sách time series, giám sát label churn và xử lý sự cố khi đã có cardinality explosion.

## 1. Metric tag là gì?

Một metric mô tả đại lượng được đo, chẳng hạn số record xử lý thành công, độ trễ listener hoặc số lần gửi message lỗi. Các **tags** (còn gọi là **labels** trong Prometheus) bổ sung chiều phân loại cho metric.

Ví dụ một counter theo dõi lỗi consumer:

~~~text
Metric name:
  app.kafka.consumer.failures

Tags:
  application = orders-service
  listener    = orders-listener
  topic       = orders.events
  category    = deserialization
~~~

Tại Prometheus, một mẫu có thể được biểu diễn:

~~~promql
app_kafka_consumer_failures_total{
  application="orders-service",
  listener="orders-listener",
  topic="orders.events",
  category="deserialization"
}
~~~

Tên metric thực tế phụ thuộc registry, naming convention và instrumentation version. Trong ví dụ, metric Micrometer dạng counter được export sang tên tương thích Prometheus. Điều quan trọng không phải tên chính xác mà là **mỗi tổ hợp nhãn duy nhất tạo một time series riêng**.

Nếu category đổi từ deserialization sang timeout, dù metric name và các tags khác không đổi, Prometheus lưu một time series khác.

## 2. Cardinality được tính như thế nào?

Giả sử một metric có bốn nhãn:

| Tag | Số giá trị có thể có |
|---|---:|
| application | 5 |
| listener | 8 |
| topic | 12 |
| outcome | 3 |

Nếu mọi kết hợp đều xuất hiện, số series tối đa theo các chiều là:

~~~text
5 applications
  × 8 listeners
  × 12 topics
  × 3 outcomes
= 1.440 time series
~~~

Công thức ước lượng:

\[
C \leq \prod_{i=1}^{n} |V_i|
\]

Trong đó C là số tổ hợp nhãn và V_i là tập giá trị quan sát được của tag thứ i. Đây là **giới hạn theo tích số lượng giá trị**, không phải phép đo chính xác khi các chiều có quan hệ phụ thuộc. Ví dụ mỗi listener chỉ tiêu thụ một số topic, nên nhiều kết hợp về lý thuyết sẽ không xuất hiện.

Tuy nhiên, nếu thêm tag **event_id** có một triệu giá trị khác nhau:

~~~text
1.440 series ban đầu
  × 1.000.000 event IDs
= 1.440.000.000 tổ hợp tiềm năng
~~~

Không nhất thiết mọi tổ hợp này đều được tạo, nhưng riêng việc tag thay đổi theo từng event đã làm khả năng mở rộng của metrics trở nên không kiểm soát được.

**Câu hỏi nên đặt ra trước khi thêm tag:** trong một ngày, một tuần và một chu kỳ triển khai, tag này có bao nhiêu giá trị khác nhau?

## 3. Series count khác sample count

Hai khái niệm thường bị nhầm:

- **Time series cardinality**: số tổ hợp metric name + label set khác nhau.
- **Sample volume**: số điểm dữ liệu được ghi vào các series theo thời gian, phụ thuộc scrape interval và thời gian series tồn tại.

Một metric có 20 series được scrape mỗi 15 giây tạo nhiều samples trong ngày, nhưng số series vẫn tương đối nhỏ. Một metric có 200.000 series mới xuất hiện trong 5 phút có thể gây **series churn** lớn dù mỗi series chỉ có ít samples.

~~~text
Trường hợp A:
  20 series
  scrape mỗi 15 giây
  các series ổn định nhiều ngày

Trường hợp B:
  mỗi message tạo event_id mới
  20.000 series mới trong vài phút
  nhiều series chỉ tồn tại ngắn
~~~

Trường hợp B thường đáng lo hơn cho index, memory, WAL, remote write và quản lý vòng đời trong hệ thống time-series.

**Giảm scrape frequency** có thể giảm sample ingestion nhưng **không sửa được cardinality theo số tổ hợp nhãn**. Phải loại bỏ hoặc chuẩn hóa các tag có giá trị không giới hạn.

## 4. Vì sao Kafka tạo nguy cơ cardinality cao?

Kafka có nhiều identifiers hữu ích cho tracing nhưng không phù hợp với metrics:

| Dữ liệu | Mức cardinality tiềm năng | Nhận xét |
|---|---|---|
| application/service | Thường thấp | Thích hợp nếu tên ổn định |
| environment | Thấp | dev, staging, production |
| cluster alias | Thường thấp | Nên dùng tên cluster có kiểm soát |
| consumer group | Thấp đến trung bình | Tránh biến thành một group cho mỗi request |
| listener ID | Thấp nếu định nghĩa cố định | Cảnh giác listener được sinh động |
| topic | Từ thấp đến rất cao | Topic-per-tenant hoặc retry topics có thể bùng nổ |
| partition | Giới hạn theo topic, nhưng có thể rất lớn toàn cluster | Không đưa vào mọi metric |
| client.id | Có thể cao và biến động | Random suffix, pod ID, instance churn |
| transactional.id | Cao khi có nhiều producer, suffix và vòng đời | Phù hợp hơn trong log |
| exception class | Thường hữu hạn nhưng cần quản lý | Nên nhóm theo failure category khi cần |
| exception message | Rất cao | Chứa ID, URL, payload, timestamp |
| record key | Rất cao | Thường trùng business/entity ID |
| event ID / correlation ID | Gần như không giới hạn | Không đưa vào metric tags |
| tenant ID / customer ID | Từ vài chục đến hàng triệu | Chỉ dùng khi có ngân sách và giới hạn rõ |
| original offset | Tăng theo record | Không bao giờ là tag metric tổng hợp |

Nguy hiểm nhất là các **giá trị phát sinh theo record hoặc theo request**, vì metrics có thể tạo series mới cho mỗi đơn hàng, mỗi retry attempt hoặc mỗi offset.

## 5. Ba mức độ của tag

Một policy thực dụng chia tags thành ba nhóm:

| Nhóm | Ví dụ | Cách sử dụng |
|---|---|---|
| **Low cardinality** | environment, outcome, error_category, operation | Phù hợp cho metrics |
| **Bounded cardinality** | topic theo whitelist, listener ID cố định, group ID đã quản lý | Dùng có ngân sách và theo dõi |
| **High/unbounded cardinality** | event_id, order_id, user_id, stack trace, exception_message | Chỉ dùng ở log/trace hoặc hệ thống truy vấn khác |

**Bounded không đồng nghĩa luôn an toàn.** Một cluster có 20 topic hôm nay có thể có 20.000 topic nếu hệ thống triển khai topic-per-customer. Một topic tag chỉ an toàn khi tổ chức có giới hạn rõ về số topic và naming policy.

Tương tự, exception class tương đối hữu hạn nhưng có thể tăng theo số thư viện và phiên bản. Nếu tên exception không cần thiết cho dashboard, dùng một tag chuẩn hóa như error_category sẽ dễ quản lý hơn.

## 6. Tag hygiene là quy trình, không chỉ naming convention

Tag hygiene bao gồm:

1. Định nghĩa rõ **metric dùng cho quyết định vận hành nào**.
2. Chỉ thêm những chiều phân loại thực sự cần cho dashboard, alert và SLO.
3. Đặt tên tag thống nhất giữa services.
4. Chuẩn hóa danh sách giá trị được phép.
5. Giới hạn số giá trị và tốc độ xuất hiện giá trị mới.
6. Không để dữ liệu từ Kafka record trở thành label tùy ý.
7. Không để PII, token, secret, email, payload hoặc SQL text vào tags.
8. Theo dõi số active series và churn.
9. Kiểm soát thay đổi thông qua code review và test.
10. Có đường khẩn cấp để vô hiệu hóa instrumentation gây bùng nổ series.

Một metric có tên đẹp nhưng tag event_id theo mọi record vẫn là metric được thiết kế sai.

## 7. Thiết kế schema tag chuẩn cho Spring Kafka

Ví dụ một schema dùng cho metrics ứng dụng:

| Tag | Giá trị hợp lệ | Hạn chế |
|---|---|---|
| application | orders-service | Tên service ổn định |
| environment | prod, staging, dev | Bộ giá trị cố định |
| kafka_cluster | core, analytics | Alias được quản lý |
| listener | orders-created, orders-payment | ID đã định nghĩa |
| operation | consume, produce, recover | Enum đóng |
| outcome | success, error, skipped | Enum đóng |
| error_category | none, deserialize, timeout, validation, infra, unknown | Danh mục chuẩn |
| topic_family | orders, payments, inventory, retry, dlt | Nhóm topic có giới hạn |

Ví dụ:

~~~text
app.kafka.listener.records{
  application="orders-service",
  environment="prod",
  listener="orders-created",
  topic_family="orders",
  outcome="error",
  error_category="deserialize"
}
~~~

Không cần lặp application, environment và cluster alias ở **mọi chỗ trong code** nếu Micrometer common tags hoặc resource attributes đã có cơ chế thêm nhất quán. Càng nhiều instrumentation tự thêm tag, nguy cơ trùng tên hoặc giá trị khác nhau càng lớn.

## 8. Đưa thông tin gì vào metric, log, trace?

Ba loại telemetry phục vụ các câu hỏi khác nhau:

| Câu hỏi | Dữ liệu nên dùng |
|---|---|
| Tỷ lệ consumer failures theo topic family là bao nhiêu? | Metric aggregate |
| Partition nào bị lag lớn trong sự cố hiện tại? | Kafka client metric theo partition có giới hạn, dashboard chuyên biệt |
| Event E123 bị lỗi ở bước nào? | Structured log/trace với event ID |
| Record lỗi nằm tại offset nào? | Log/trace và DLT metadata |
| Mất bao lâu để listener xử lý các records? | Timer/histogram theo bounded tags |
| Tại sao một record timeout? | Trace/log với exception details |
| Bao nhiêu recovery sang DLT trong 5 phút? | Counter theo outcome/category |
| Những tenant nào bị ảnh hưởng? | Query log/trace hoặc metrics theo tenant tier đã kiểm soát |

**Cardinality thấp không đồng nghĩa mất khả năng chẩn đoán.** Dùng aggregate metrics để phát hiện triệu chứng, sau đó chuyển sang logs/traces có correlation IDs để xác định từng record.

Ví dụ:

~~~text
Metric:
  error_category="serialization"
  count tăng bất thường

Trace:
  trace_id = ...
  event.id = E123
  topic = orders.created
  partition = 2
  offset = 105

Log:
  nguyên nhân chi tiết và context được redaction
~~~

Không nên ép một hệ thống metrics thành database tìm kiếm theo từng event.

## 9. Consumer metrics: chiều phân loại nào hữu ích?

Với Spring Kafka consumer, những metrics chính thường gồm:

- Số records xử lý thành công/thất bại.
- Listener processing duration.
- Poll/consumer liveness.
- Consumer lag.
- Commit offset failure.
- Rebalance count/duration.
- Error handler recoveries.
- Retry attempts hoặc DLT output.

Các chiều phù hợp thường là:

~~~text
application
listener
topic_family
outcome
error_category
~~~

Cần cân nhắc topic và partition:

- **topic** hữu ích khi số topic được quản lý và có ngân sách.
- **topic_family** phù hợp hơn khi topic names chứa tenant ID, ngày hoặc các suffix động.
- **partition** hữu ích cho một số native Kafka metrics nhưng không nhất thiết phải gắn vào tất cả business metrics.
- **consumer group** giúp phân biệt các flows, nhưng cần tránh group ID sinh riêng cho mỗi job nếu số lượng job không giới hạn.

Không đặt **record.key()**, **record.offset()** hoặc business event ID vào tag chỉ để tìm record trong dashboard.

## 10. Tác động của partition-level metrics

Giả sử service chạy 12 consumer instances, mỗi instance sở hữu nhiều partitions. Nếu một metric có:

~~~text
topic = 40 giá trị
partition = tối đa 200 giá trị trên một số topic
client_id = 12 giá trị
outcome = 3 giá trị
~~~

Số tổ hợp tối đa về mặt lý thuyết có thể tăng mạnh. Thực tế mỗi client chỉ sở hữu một tập topic-partition, nhưng nếu cả broker/client metrics cùng export nhiều nhóm metrics, tổng series vẫn rất đáng kể.

Với **lag theo partition**, chi tiết partition là thông tin có giá trị vì một partition bị kẹt có thể bị che bởi lag trung bình. Tuy nhiên, không cần thêm partition vào mọi timer và business counter.

Một thiết kế cân bằng:

- Theo dõi **lag max hoặc aggregated lag** theo consumer group/listener cho alert tổng quát.
- Theo dõi **partition lag** trên dashboard chẩn đoán có giới hạn và retention phù hợp.
- Dùng logs/consumer group tooling để xem từng partition khi cần điều tra.
- Không tự tạo một metric latency cho mỗi **offset**.

**Partition là một chiều hữu hạn tại một thời điểm nhưng tổng số partition của một hệ thống lớn vẫn có thể rất cao.**

## 11. Topic-per-tenant: tag topic có thể biến thành ID khách hàng

Giả sử hệ thống tạo topic:

~~~text
orders.tenant-1001
orders.tenant-1002
orders.tenant-1003
...
orders.tenant-9999
~~~

Nếu đặt topic làm tag trên mọi listener timer/counter, metric sẽ có ít nhất một label value cho từng tenant. Khi thêm partition, outcome và instance, cardinality nhân lên nhanh chóng.

Thay vì:

~~~text
topic="orders.tenant-1001"
topic="orders.tenant-1002"
~~~

Có thể dùng:

~~~text
topic_family="orders"
tenant_tier="standard"
~~~

Nếu phải xem metrics cho một nhóm tenant trọng điểm, hãy thiết kế whitelist/allowlist rõ ràng với tag giá trị còn lại như other, nhưng không đưa toàn bộ customer IDs vào Prometheus chỉ vì một dashboard riêng.

Quan trọng: **thay tag giá trị động bằng một nhóm có nghĩa** thường tốt hơn xóa hết thông tin topic. Dashboard vẫn biết lỗi xảy ra ở nhóm orders mà không tạo một series cho mỗi khách hàng.

## 12. Client ID và transactional ID cần đặc biệt thận trọng

Kafka native client metrics thường chứa client.id. Spring Kafka có thể tạo các client IDs có suffix theo concurrency hoặc container lifecycle. Nếu tên còn chứa pod UUID hoặc timestamp, mỗi lần restart có thể tạo nhãn mới.

~~~text
client_id="orders-consumer-f4b8d1-0"
client_id="orders-consumer-a19c77-0"
client_id="orders-consumer-2d851e-0"
~~~

Cho dù mỗi instance chỉ tạo một số consumer, **restart thường xuyên sẽ gây series churn**. Với service autoscaling, số series sinh ra theo thời gian có thể lớn hơn nhiều so với số pods đang chạy.

Đối với transactional producer, transactional.id có thể gồm instance prefix và suffix. Đây là thông tin quan trọng trong **log khi xử lý ProducerFencedException**, nhưng thường không cần làm label cho mọi transaction metric.

Khuyến nghị:

1. Dùng stable logical listener/container ID cho metrics tổng hợp.
2. Không trộn random UUID vào label của custom metrics.
3. Để client.id tồn tại ở native client metrics nếu cần, nhưng cân nhắc phạm vi scrape/retention và số series.
4. Ghi transactional.id cụ thể vào structured log có kiểm soát khi điều tra fencing.
5. Tránh thêm cả client_id, transactional_id, pod_uid và event_id lên cùng một custom timer.

Việc loại bỏ client ID khỏi metrics cần đánh giá nhu cầu debug từng Kafka client, không phải một quy tắc cấm tuyệt đối. **Vấn đề là ngân sách và khả năng chẩn đoán tương xứng với chi phí.**

## 13. Retry và DLT tags dễ bùng nổ ra sao?

Spring Kafka retry có thể tạo các topic như:

~~~text
orders-retry-1000
orders-retry-5000
orders-dlt
~~~

Tên cụ thể phụ thuộc retry topology và naming strategy đang dùng. Một tag topic riêng có thể còn kiểm soát được khi số topic cố định.

Nhưng nếu retry topics được tạo động theo tenant, sự kiện, duration, deployment ID hoặc random suffix, tag topic sẽ nhanh chóng tăng cardinality.

Các metrics phù hợp:

~~~text
app.kafka.recovery.attempts{
  topic_family="orders",
  stage="retry",
  outcome="scheduled"
}

app.kafka.recovery.attempts{
  topic_family="orders",
  stage="dlt",
  outcome="published"
}
~~~

Tags được khuyến nghị:

| Tag | Giá trị có kiểm soát |
|---|---|
| stage | listener, retry, dlt, replay |
| outcome | success, failed, scheduled, published |
| error_category | deserialize, validation, infra, timeout, unknown |
| topic_family | orders, payments, inventory, other |

Không dùng retry attempt UUID, original offset, DLT offset hoặc full exception message làm metric labels.

Khi cần truy record DLT, dùng original topic/partition/offset headers trong log hoặc DLT investigation store.

## 14. Exception class và exception message

Phân loại lỗi là một nhu cầu quan trọng cho alerts, nhưng cách chọn nhãn phải có giới hạn.

So sánh:

~~~text
Tốt:
  error_category="timeout"

Có thể phù hợp khi kiểm soát:
  exception_class="org.apache.kafka.common.errors.TimeoutException"

Không nên:
  exception_message="Request for order 927341 to https://... timed out at 12:01:32"
~~~

Exception message thường chứa:

- Event ID, order ID hoặc tenant ID.
- URL và dynamic request parameters.
- Timestamp.
- SQL query, database key hoặc stack trace fragment.
- Chi tiết dữ liệu nhạy cảm.

Nếu đưa nguyên văn exception message vào tag, mỗi lỗi có thể tạo một time series mới. Đây là nguyên nhân phổ biến của **cardinality explosion trong ngày incident**: khi lỗi tăng mạnh, metric labels cũng tăng theo chính những dữ liệu gây lỗi.

Một strategy phù hợp:

~~~text
exception -> classification function
               |
               +-- DeserializationException -> deserialize
               +-- TimeoutException         -> timeout
               +-- ValidationException      -> validation
               +-- ProducerFencedException  -> transaction
               +-- others                   -> unknown
~~~

Giữ full exception trong log đã kiểm soát, không trong metric tag.

## 15. Viết bộ phân loại lỗi hữu hạn

Một enum giúp ngăn giá trị metric bị tạo tùy ý:

~~~java
public enum KafkaFailureCategory {
    NONE,
    DESERIALIZE,
    VALIDATION,
    TIMEOUT,
    TRANSACTION,
    INFRASTRUCTURE,
    UNKNOWN
}
~~~

Một mapper minh họa:

~~~java
public final class KafkaFailureClassifier {

    private KafkaFailureClassifier() {
    }

    public static KafkaFailureCategory classify(Throwable error) {
        if (error == null) {
            return KafkaFailureCategory.NONE;
        }

        if (error instanceof org.apache.kafka.common.errors.TimeoutException) {
            return KafkaFailureCategory.TIMEOUT;
        }

        if (error instanceof org.apache.kafka.common.errors.ProducerFencedException) {
            return KafkaFailureCategory.TRANSACTION;
        }

        if (error instanceof org.springframework.kafka.support.serializer.DeserializationException) {
            return KafkaFailureCategory.DESERIALIZE;
        }

        return KafkaFailureCategory.UNKNOWN;
    }
}
~~~

Code minh họa cách gắn **category hữu hạn**; trong ứng dụng thực tế cần unwrap các wrapper exceptions, áp dụng classification theo root cause phù hợp và bổ sung các loại exception nghiệp vụ. Không cần làm danh sách enum lớn đến mức mỗi class exception mới tạo một category riêng.

Khi ghi metrics, chuyển enum thành giá trị chuẩn như lowercase. Không dùng **error.toString()** làm category.

## 16. Counter bằng Micrometer: ví dụ an toàn

Giả sử muốn đếm số records được xử lý theo listener, outcome và error category:

~~~java
@Component
public class KafkaProcessingMetrics {

    private final MeterRegistry registry;

    public KafkaProcessingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordSuccess() {
        registry.counter(
                "app.kafka.listener.records",
                "listener", "orders-created",
                "outcome", "success",
                "error_category", "none")
            .increment();
    }

    public void recordFailure(KafkaFailureCategory category) {
        registry.counter(
                "app.kafka.listener.records",
                "listener", "orders-created",
                "outcome", "error",
                "error_category", category.name().toLowerCase(Locale.ROOT))
            .increment();
    }
}
~~~

Ở ví dụ này, các giá trị tag được lấy từ enum hoặc literal ổn định. Số series có giới hạn rõ ràng theo số listener, outcome và category.

Trong code production, có thể định nghĩa các counters một lần tại lúc khởi tạo để giảm chi phí lookup khi xử lý throughput lớn. Nhưng **caching metric instances không làm giảm cardinality** nếu mỗi bản ghi vẫn tạo một combination tag khác nhau.

Không đưa record.key(), eventId hoặc customerName vào lời gọi registry.counter(...).

## 17. Anti-pattern: tạo metric theo từng record

Ví dụ sai:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(ConsumerRecord<String, OrderEvent> record) {
    registry.counter(
            "app.kafka.listener.records",
            "topic", record.topic(),
            "partition", String.valueOf(record.partition()),
            "offset", String.valueOf(record.offset()),
            "record_key", String.valueOf(record.key()))
        .increment();

    orderService.process(record.value());
}
~~~

Mỗi record thường có offset khác nhau, vì vậy **offset tag gần như bảo đảm một series mới cho mỗi record**. Record key cũng thường là ID đơn hàng hoặc khách hàng có số lượng không giới hạn.

Một phiên bản tốt hơn:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(ConsumerRecord<String, OrderEvent> record) {
    long started = System.nanoTime();
    try {
        orderService.process(record.value());
        metrics.recordSuccess();
    }
    catch (RuntimeException ex) {
        metrics.recordFailure(
                KafkaFailureClassifier.classify(ex));

        log.error(
                "Kafka record failed: topic={}, partition={}, offset={}, key={}",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                ex);

        throw ex;
    }
}
~~~

Ở đây topic/partition/offset/key đi vào structured log để điều tra. **Cần redaction/truncation phù hợp nếu key chứa PII**, và không log payload tùy tiện.

Biến started chỉ minh họa điểm có thể bắt đầu đo latency; nếu muốn đo Timer, dùng Timer.Sample hoặc Observation theo API hỗ trợ, không tạo tag động theo timestamp.

## 18. Timer/histogram làm cardinality tăng nhiều hơn counter

Một counter thường tương ứng một hoặc vài chuỗi thời gian ở backend. Timer/histogram thường export nhiều series hơn, ví dụ:

~~~text
app_kafka_processing_seconds_count{...}
app_kafka_processing_seconds_sum{...}

Nếu histogram enabled:
app_kafka_processing_seconds_bucket{...,le="0.01"}
app_kafka_processing_seconds_bucket{...,le="0.05"}
app_kafka_processing_seconds_bucket{...,le="0.1"}
...
~~~

Mỗi tổ hợp label sẽ được nhân thêm các bucket theo cấu hình histogram. Ví dụ:

~~~text
400 tổ hợp tag
  × 15 bucket series
= khoảng 6.000 bucket series

Chưa tính count/sum và các series phụ khác.
~~~

Vì vậy, một timer có event_id hoặc tenant_id nguy hiểm hơn nhiều so với một counter tương tự.

Khi cần p95/p99:

- Chỉ bật histogram cho những timer cần SLO.
- Chọn boundary/buckets phù hợp với latency thực tế.
- Giữ label set nhỏ.
- Không bật percentile histogram cho mọi metric chỉ vì muốn dashboard đẹp.
- Xác định số histograms mới được tạo theo số listener, outcome, topic và instance.

Đối với hệ thống có nhiều metrics, **bucket count phải được tính vào time-series budget**.

## 19. Ví dụ Timer.Sample với bounded tags

~~~java
@Component
public class OrderProcessingTimer {

    private final MeterRegistry registry;

    public OrderProcessingTimer(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(Runnable work) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            work.run();
        }
        catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        }
        finally {
            sample.stop(
                    Timer.builder("app.kafka.processing")
                            .description("Kafka listener processing duration")
                            .tag("listener", "orders-created")
                            .tag("outcome", outcome)
                            .register(registry));
        }
    }
}
~~~

Code này dùng hai giá trị outcome hữu hạn và listener ID cố định. Timer được lookup/register theo tập tag có giới hạn.

Nếu application muốn timer phân biệt lỗi theo category, category cũng phải lấy từ danh mục chuẩn. Tránh dùng exception message, full stack trace hoặc record key.

Trong Spring Kafka, có thể đã có **built-in listener observation/timer**. Trước khi viết timer custom, cần xem instrumentation hiện hữu để tránh đo trùng và tăng cardinality không cần thiết.

## 20. Spring Kafka Micrometer timers và Observations

Spring Kafka tích hợp với Micrometer để đo hoạt động của listener và producer. Tùy phiên bản, có thể sử dụng **Micrometer timers** hoặc **Micrometer Observation** và xuất metrics/traces qua ObservationRegistry.

Ví dụ cấu hình observation cho listener container trong phiên bản hỗ trợ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        observedKafkaListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setObservationEnabled(true);
    return factory;
}
~~~

KafkaTemplate cũng có cơ chế bật observation ở các phiên bản hỗ trợ, ví dụ thông qua setter của template:

~~~java
kafkaTemplate.setObservationEnabled(true);
~~~

Các method và metric names cụ thể tùy Spring Kafka/Micrometer version. Không giả định tất cả timers và observations đều được bật mặc định hoặc tạo cùng một metric name ở mọi phiên bản.

**Tag hygiene vẫn quan trọng khi instrumentation do framework tạo.** Các default conventions, listener IDs, client IDs và tags tùy biến có thể làm số series tăng mạnh, nhất là khi ứng dụng cho phép custom dynamic tags.

## 21. Micrometer Observation: low và high cardinality

Micrometer Observation phân biệt:

- **Low-cardinality key values**: phù hợp để dùng làm metric labels.
- **High-cardinality key values**: có thể cung cấp context cho tracing, nhưng không nên được xuất như metric labels.

Ví dụ khái niệm:

~~~java
Observation.createNotStarted(
        "app.kafka.order.processing",
        observationRegistry)
    .lowCardinalityKeyValue("operation", "consume")
    .lowCardinalityKeyValue("outcome", "success")
    .highCardinalityKeyValue("event.id", eventId)
    .observe(() -> orderService.process(event));
~~~

Đây là minh họa cách tách context theo cardinality trong Observation API. **High-cardinality observation key không tự bảo đảm an toàn dữ liệu nhạy cảm**: tracing backend vẫn có chi phí và chính sách bảo mật riêng. Nếu event ID, user ID hoặc payload chứa dữ liệu cần bảo vệ, phải áp dụng filtering và retention phù hợp.

Đừng cố biến event.id thành lowCardinalityKeyValue chỉ để tìm trace từ Prometheus.

Nếu cần kết nối metrics sang traces, hãy dùng trace exemplars hoặc trace IDs trong logs/traces theo khả năng của monitoring stack, thay vì thêm trace_id như một label trên tất cả samples.

## 22. Custom ObservationConvention có thể gây lỗi

Spring Kafka hỗ trợ các observation conventions tùy biến trong những phiên bản thích hợp. Đây là nơi instrumentation có thể thêm key values vào spans/metrics.

Nguyên tắc khi viết convention:

~~~text
Low cardinality:
  listener = orders-created
  operation = consume
  result = success | error
  topic_family = orders

High cardinality / tracing only:
  event.id
  kafka.record.offset
  message.key (nếu được phép)
  correlation.id
~~~

Không đưa nguyên payload vào convention và không trích dữ liệu Kafka header thành metric tag tùy ý. Headers do producer hoặc khách hàng có thể tự điều khiển; nếu map mọi header thành tag, người gửi message có thể vô tình hoặc cố ý tạo số series không giới hạn.

Một convention nên được code review như một phần của **telemetry schema**, không chỉ như một tiện ích kỹ thuật.

## 23. MeterFilter: phòng tuyến ở mức registry

Micrometer cung cấp **MeterFilter** để chấp nhận, từ chối hoặc biến đổi meter IDs trước khi chúng được đăng ký trong MeterRegistry.

Ví dụ giới hạn những tag nguy hiểm:

~~~java
@Bean
MeterFilter denyDynamicKafkaTags() {
    return MeterFilter.deny(id ->
            id.getName().startsWith("app.kafka.")
                    && (id.getTag("event_id") != null
                        || id.getTag("order_id") != null
                        || id.getTag("record_key") != null
                        || id.getTag("offset") != null));
}
~~~

Trong Spring Boot, các MeterFilter beans thường được áp dụng vào registry bởi auto-configuration phù hợp.

Ví dụ trên **từ chối meter** chứa những tag cấm trong namespace custom app.kafka. Đây là hàng rào phòng lỗi, không phải thay thế cho việc không tạo tag nguy hiểm ngay từ code.

Khi MeterFilter deny một meter, instrumentation có thể nhận **noop meter**. Metric không xuất hiện, nhưng business processing vẫn tiếp tục. Vì vậy cần alert/observability cho thay đổi filter để tránh che khuất một metric vận hành quan trọng mà không ai biết.

## 24. maximumAllowableTags: giới hạn số giá trị

Micrometer còn cung cấp phương pháp giới hạn số tag values:

~~~java
@Bean
MeterFilter limitTenantTagValues() {
    return MeterFilter.maximumAllowableTags(
            "app.kafka.",
            "tenant",
            20,
            MeterFilter.deny());
}
~~~

Ý nghĩa khái quát: với các meters có tên bắt đầu bằng app.kafka., chỉ cho phép số lượng giá trị khác nhau của tag tenant theo giới hạn filter; khi vượt ngưỡng, áp dụng filter fallback là deny.

Những điều cần hiểu:

- Giới hạn này **không làm tenant IDs trở thành một metric tag tốt**.
- Khi các tag values vượt giới hạn, metrics mới có thể bị từ chối và tạo lỗ hổng quan sát.
- Filter state có thể phản ánh những giá trị từng được đăng ký, không đơn giản là số tenant active tại một thời điểm.
- Mỗi application instance có MeterRegistry riêng; limit cục bộ không phải cluster-wide cardinality quota.
- Một số giá trị được ưu tiên do thứ tự xuất hiện có thể khác nhau giữa pods.

Do đó, **maximumAllowableTags là safety net**, không phải phương án chính để triển khai per-tenant metrics hàng triệu tenants. Nên dùng whitelist/aggregation từ đầu và dự báo số series.

## 25. Chuẩn hóa tag bằng MeterFilter map

Một chiến lược khác là chuyển tag động thành nhóm hữu hạn. Ví dụ chỉ giữ các topic families được cho phép:

~~~java
private static String topicFamily(String topic) {
    if (topic == null) {
        return "unknown";
    }
    if (topic.startsWith("orders.")) {
        return "orders";
    }
    if (topic.startsWith("payments.")) {
        return "payments";
    }
    if (topic.startsWith("inventory.")) {
        return "inventory";
    }
    return "other";
}
~~~

Ở tầng instrumentation ứng dụng, tốt nhất gọi:

~~~java
registry.counter(
        "app.kafka.listener.records",
        "topic_family", topicFamily(record.topic()),
        "outcome", "success")
    .increment();
~~~

Nếu muốn dùng MeterFilter để thay tag, cần bảo đảm logic filter tạo/rename tags mà không làm mất các tags khác và tuân thủ contract Micrometer. Nhưng **chuẩn hóa tại nguồn** thường đơn giản và dễ kiểm tra hơn một filter bất ngờ thay đổi mọi metric cùng tên.

Hàm topicFamily cũng cần được review: một prefix rộng có thể gom nhầm topic hoặc lộ cách đặt tên hạ tầng. Dùng whitelist/regex được quản lý khi topology phức tạp.

## 26. Tại sao giảm tag sau khi scrape là chưa đủ?

Prometheus hỗ trợ **metric relabeling** để drop series hoặc labels trước khi ingest. Điều này có thể giảm tải cho storage/backend, nhưng có giới hạn:

~~~text
Spring application
  |
  +-- Micrometer đã tạo meter IDs
  +-- Actuator đã chuẩn bị xuất metrics
  |
  v
Prometheus scrape
  |
  v
metric_relabel_configs
  |
  +-- drop/keep series hoặc label
  |
  v
Prometheus storage
~~~

Nếu ứng dụng đã đăng ký hàng trăm nghìn meters, việc drop sau scrape **không xóa được chi phí meter registry và export trong application process**. Nó cũng không làm HTTP response của /actuator/prometheus nhỏ đi trước khi scrape.

Vì vậy, cần phòng vệ theo tầng:

1. **Instrumentation source**: không tạo tag không giới hạn.
2. **Micrometer MeterFilter**: giới hạn/chặn trước meter registration.
3. **Prometheus metric relabel**: chặn nhãn/series không mong muốn ở thời điểm ingest.
4. **Backend quotas**: giới hạn active series, ingestion rate và storage.
5. **Monitoring alerts**: phát hiện tăng đột ngột trước khi hệ thống cạn tài nguyên.

Không trông cậy vào một tầng duy nhất để sửa toàn bộ telemetry pipeline.

## 27. Ví dụ Spring Boot Actuator/Prometheus

Một cấu hình Spring Boot cơ bản:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    tags:
      application: orders-service
      environment: production
~~~

Ứng dụng cần các dependencies phù hợp như Spring Boot Actuator và Micrometer Prometheus registry; nếu thiếu registry, endpoint Prometheus có thể không được expose.

Ví dụ cấu hình chỉ định common tags ổn định. Nó không giải quyết các dynamic tags bên trong custom metrics hoặc Kafka client meters.

Khi vận hành:

- Không expose actuator endpoints nhạy cảm trực tiếp ra Internet.
- Giới hạn truy cập /actuator/prometheus theo monitoring network/security policy.
- Không đưa secret vào common tags.
- Đo response size và scrape duration.
- Đặt scrape timeout phù hợp với thời gian export.
- Xác nhận metrics có giá trị trước khi thêm label vào dashboards.

Nếu metrics endpoint response tăng bất thường sau một deployment, cần kiểm tra tag cardinality, không chỉ tăng Prometheus scrape timeout.

## 28. Common tags: nhất quán nhưng không lạm dụng

Common tags hữu ích để phân biệt application, environment hoặc region.

~~~text
application = orders-service
environment = prod
region = ap-southeast-1
~~~

Nhưng common tags áp dụng cho **rất nhiều meters** trong ứng dụng. Nếu thêm một tag có giá trị biến động theo từng request vào common tags, hậu quả có thể lan rộng hơn một metric đơn lẻ.

Không nên đặt:

~~~text
request_id
event_id
user_id
order_id
last_processed_offset
current_transactional_id
~~~

vào common tags.

Với Kubernetes, service, namespace, pod và instance labels thường được thêm ở tầng scrape/service discovery. Cần xác định nguồn authoritative cho các labels đó để tránh tạo nhiều biến thể trùng nhau như application, app, app_name, service_name trên cùng một metric mà không có ý nghĩa mới.

**Tag convention thống nhất quan trọng hơn số lượng tag nhiều.**

## 29. Metric schema và namespace

Một team nên ghi rõ contract cho mỗi metric:

~~~text
Metric:
  app.kafka.listener.records

Type:
  counter

Unit:
  records

Purpose:
  count handled records by outcome

Allowed tags:
  application: set from common tags
  listener: fixed listener IDs
  outcome: success | error | skipped
  error_category:
    none | deserialize | timeout | validation | transaction | unknown

Forbidden:
  event_id, record_key, offset, payload, exception_message

Owner:
  messaging-platform

Budget:
  maximum expected series documented per service
~~~

Với Kafka latency timer, nên ghi rõ histogram có bật không, bucket configuration, SLO và expected series multiplication.

Đặt tên metric không nên chứa dynamic IDs:

~~~text
Sai:
  app.kafka.orders.customer123.failures
  app.kafka.orders.customer124.failures

Tốt:
  app.kafka.orders.failures{customer_tier="premium"}
~~~

Metric name cũng là một phần identity; tạo metric name mới cho từng khách hàng gây cardinality tương tự tạo tag value mới.

## 30. Lập ngân sách cardinality

Một ngân sách nên được tính **theo metric family và theo service**, không chỉ đặt một ngưỡng toàn cluster.

Ví dụ dự báo cho listener latency timer:

| Chiều | Số giá trị dự kiến |
|---|---:|
| listener | 6 |
| topic_family | 4 |
| outcome | 2 |
| instance | 10 |
| **Tổ hợp tối đa** | **480** |

Nếu timer export 12 buckets cộng count/sum, 480 combinations có thể tương ứng nhiều nghìn Prometheus series.

Một budget hợp lý cần tính:

1. Số service replicas tối đa, không chỉ trung bình hiện tại.
2. Concurrency của các consumers.
3. Số listener IDs trong mỗi deployment.
4. Số topic families và group IDs được hỗ trợ.
5. Histogram buckets, sum, count và series phụ.
6. Kafka native producer/consumer client metrics.
7. Series churn khi rollout/restart.
8. Số môi trường/cluster cùng đổ vào một backend.

Budget là một **ước lượng có kiểm chứng**, không phải công thức bắt buộc mọi tổ hợp đều tồn tại. Nên đo active series thực tế sau khi rollout nhỏ và so sánh với forecast.

## 31. Kiểm tra active series bằng Prometheus

Prometheus có thể cung cấp các hàm/truy vấn để đếm số series theo namespace hoặc label set, tùy dữ liệu đã ingest.

Ví dụ đếm số series có metric name bắt đầu bằng app_kafka_ trong một instant query:

~~~promql
count({__name__=~"app_kafka_.*"})
~~~

Đếm theo metric name:

~~~promql
count by (__name__) ({__name__=~"app_kafka_.*"})
~~~

Đếm số giá trị label topic xuất hiện trong một metric:

~~~promql
count(
  count by (topic) (app_kafka_listener_records_total)
)
~~~

Những truy vấn trên mang tính minh họa; nếu metric không có label topic hoặc tên khác trong deployment cụ thể, cần thay đúng tên/tag.

Một metric có nhiều time series có thể là nhu cầu hợp lệ, ví dụ partition lag của một cluster lớn. Trước khi drop, phải xem **chi phí so với giá trị vận hành**.

## 32. Nhìn label churn, không chỉ active series

Một service có thể có số active series không quá lớn nhưng liên tục tạo series mới khi pods restart hoặc event IDs thay đổi.

Với Prometheus, có thể xem:

- Active series theo metric và job.
- Tốc độ tạo series mới trong TSDB, theo các metrics nội bộ hiện có của backend.
- Remote-write samples/series ingestion và queue backlog.
- WAL/storage growth.
- Scrape duration và scrape samples theo target.

Một dấu hiệu:

~~~text
Service đang chạy:
  10 pods, mỗi pod hiện có 200 series

Trong ngày:
  pods thay đổi identity hàng trăm lần
  labels có pod UUID mới mỗi lần

Backend có nhiều historical series với vòng đời ngắn
~~~

Đây là **series churn**, không nhất thiết biểu hiện bằng active series tăng liên tục. Nếu chỉ nhìn số series hiện tại, có thể bỏ qua áp lực lên indexing và storage.

Đối với labels như client_id, pod_uid, session_id, hãy kiểm tra tính ổn định qua deployments và restarts.

## 33. Quy tắc bảo mật cho Kafka metric labels

Metric labels không chỉ gây chi phí, chúng còn là kênh có thể làm lộ dữ liệu:

~~~text
record_key = email@example.com
tenant_id = customer-secret-code
exception_message = Authorization failed for token ...
payload = {"creditCard": "..."}
~~~

Một metric thường được truy cập bởi nhiều dashboards, exporters, Prometheus servers và remote-write endpoints. Dữ liệu được đưa vào label có thể bị lưu trữ lâu dài và có phạm vi truy cập rộng hơn application logs.

Quy tắc:

- Không đưa PII, access token, password, email, phone, account number vào labels.
- Không map Kafka headers sang tags không giới hạn.
- Không dùng raw exception message hoặc stack trace.
- Dùng **tier/region/category** khi cần phân tích phân khúc.
- Kiểm soát retention và RBAC của telemetry backend.
- Nếu phải đưa một identifier vào trace/log, thực hiện masking/hashing theo chính sách; hashing không tự giải quyết cardinality nếu mỗi giá trị vẫn duy nhất.

**Hash event ID rồi đưa vào label vẫn tạo cùng số giá trị khác nhau**. Hashing có thể thay đổi khả năng nhận diện trực tiếp nhưng không làm giảm cardinality.

## 34. Kafka native client metrics có cần lọc không?

Kafka producer/consumer expose nhiều JMX/client metrics: request rate, bytes in/out, fetch latency, records lag, rebalance metrics, connection metrics và các nhóm khác. Spring/Kafka instrumentation có thể bind hoặc export các chỉ số này qua Micrometer.

Một số metrics hữu ích ở mức chi tiết client/partition; số khác có thể thừa nếu application chỉ cần SLO tổng hợp.

Khi bật native client metrics:

1. Xem số consumer/producer instances được tạo thực tế.
2. Xem các tag mặc định như client-id, topic, partition hoặc node.
3. Xem số metric families mỗi client.
4. Xem producer cache có nhiều transactional producers không.
5. Đo số series phát sinh sau khi tăng listener concurrency.
6. Lọc những nhóm không dùng tới nếu chi phí quá cao.
7. Không xóa các metrics cần cho điều tra lag hoặc broker/network failures mà không có thay thế.

Việc dùng KafkaClientMetrics, MicrometerConsumerListener hoặc MicrometerProducerListener tùy integration và phiên bản Spring Kafka. Các API này có thể tạo binders với tags khác nhau; cần xác minh phiên bản đang triển khai thay vì giả định tên metric giống nhau ở mọi release.

## 35. Partition tag trong consumer lag: ngoại lệ có kiểm soát

Lag theo partition là một trường hợp tag partition thực sự có thể cần thiết:

~~~text
Consumer group orders-service:
  P0 lag = 0
  P1 lag = 0
  P2 lag = 50.000
  P3 lag = 0
~~~

Nếu dashboard chỉ có average lag, partition P2 bị kẹt có thể bị che mờ. Partition-level lag giúp phát hiện skew và hot partition.

Nhưng cần giới hạn:

- Chỉ các lag-related metric families cần partition tag.
- Không gắn partition vào mọi business metric.
- Đánh giá tổng partition count của group và cluster.
- Dùng retention phù hợp cho dữ liệu chi tiết.
- Khi partition count tăng mạnh, xem lại budget và dashboards.

Một thiết kế theo tầng:

~~~text
Alert chung:
  max lag theo group > threshold

Dashboard điều tra:
  lag theo topic/partition để tìm hot partition

Log/trace:
  event IDs và offsets khi cần tìm records cụ thể
~~~

Chọn độ chi tiết phù hợp với câu hỏi, thay vì sao chép cùng tập tags cho mọi metric.

## 36. DLT metrics cần tách thành công/thất bại

Khi một consumer gặp lỗi và recoverer gửi record sang DLT, một dashboard chỉ có counter "DLT attempts" không đủ để biết publish thành công.

Nên phân biệt các outcomes:

~~~text
app.kafka.recovery.records{
  stage="dlt",
  outcome="publish_success",
  error_category="deserialize"
}

app.kafka.recovery.records{
  stage="dlt",
  outcome="publish_failed",
  error_category="infrastructure"
}
~~~

Giá trị outcome nên là enum có giới hạn, không lấy từ nguyên văn Kafka producer exception.

Khi publish thất bại, **không tăng success counter chỉ vì recoverer đã được gọi**. Việc kết luận success phải dựa trên semantics acknowledgement/send result do đường recovery cung cấp.

Đối với DLT investigation, lưu **original topic/partition/offset** trong Kafka headers và logs; không tạo metric label cho từng original offset.

## 37. Transactions và producer fencing metrics

Trong Kafka transactional processing, những tín hiệu cần theo dõi gồm:

- Transaction begin/commit/abort outcome.
- ProducerFencedException count.
- Commit duration.
- Transaction timeout occurrences.
- ConsumerStoppedEvent reason=FENCED.
- Retry/restart after fencing.

Một schema phù hợp:

~~~text
app.kafka.transaction.events{
  application="orders-service",
  operation="commit",
  outcome="error",
  failure_category="fenced"
}
~~~

Không đưa full transactional.id vào mọi metric để phân biệt từng producer. Nếu muốn điều tra một producer bị fenced, log identity cụ thể cùng instance/pod trong structured log đã kiểm soát.

Với ConsumerStoppedEvent, tag **reason** thường có tập giá trị hữu hạn (NORMAL, FENCED, AUTH, NO_OFFSET, ERROR và các giá trị mà phiên bản hỗ trợ). Đây là một tag phù hợp nếu không biến nó thành nguyên văn exception message.

Khi metric cho reason=FENCED tăng, drill down logs để tìm transactional.id và timeline; không cần đưa transactional.id vào counter.

## 38. Consumer application events và cardinality

Spring Kafka có các events như ConsumerPausedEvent, ConsumerResumedEvent, ConsumerStoppedEvent, ListenerContainerIdleEvent và NonResponsiveConsumerEvent.

Các metrics hữu ích:

~~~text
app.kafka.consumer.lifecycle.events{
  listener="orders-created",
  event="paused"
}

app.kafka.consumer.lifecycle.events{
  listener="orders-created",
  event="resumed"
}

app.kafka.consumer.lifecycle.events{
  listener="orders-created",
  event="stopped",
  reason="fenced"
}
~~~

Một **event type** hoặc **stop reason** có số lượng giá trị hữu hạn nên phù hợp hơn **event source object.toString()**, vốn có thể chứa object identity hoặc child consumer ID thay đổi liên tục.

Với concurrent containers, có thể cần thêm bounded child index để điều tra, nhưng không tự gắn nguyên tên thread chứa runtime-generated IDs nếu không có yêu cầu và ngân sách cụ thể.

Đừng dùng lifecycle metric như nơi lưu danh sách từng partition event đã xảy ra; những thông tin đó phù hợp với logs khi cần.

## 39. Kiểm soát label values có giá trị rỗng và lỗi

Nếu dữ liệu không xác định, instrumentation đôi khi dùng:

~~~text
topic=""
topic="null"
topic="unknown"
topic="N/A"
topic="undefined"
~~~

Năm cách biểu đạt cùng một ý nghĩa làm tăng cardinality và gây khó query.

Tag hygiene yêu cầu thống nhất:

- Chọn một giá trị fallback như **unknown**.
- Không sử dụng String.valueOf(null) nếu nó tạo chuỗi "null" ngoài convention.
- Chuẩn hóa case: success/error, không trộn SUCCESS, Success và success.
- Không tự thêm whitespace hoặc timestamp vào label.
- Phân biệt unknown, none và not_applicable khi có ý nghĩa vận hành khác nhau.

Ví dụ method chuẩn hóa:

~~~java
private static String normalizeOutcome(String value) {
    if ("success".equalsIgnoreCase(value)) {
        return "success";
    }
    if ("error".equalsIgnoreCase(value)) {
        return "error";
    }
    if ("skipped".equalsIgnoreCase(value)) {
        return "skipped";
    }
    return "unknown";
}
~~~

Không đưa nguyên chuỗi input khác vào tag khi không khớp; như vậy fallback sẽ mất ý nghĩa giới hạn cardinality.

## 40. Thay đổi metric schema qua deployments

Một deployment có thể đổi:

~~~text
Trước:
  tag result="ok"

Sau:
  tag outcome="success"
~~~

Trong thời gian rolling update, hai phiên bản có thể cùng chạy và tạo hai sets series. Dashboard/alerts cũ có thể không thấy metric mới.

Khi thay đổi tags:

1. Có kế hoạch migration cho dashboards và PromQL alerts.
2. Đánh giá overlap thời gian hai versions chạy song song.
3. Dự toán series tăng tạm thời.
4. Dùng tên tag/value ổn định cho lâu dài.
5. Không đổi định nghĩa outcome tùy hứng giữa teams.
6. Xóa instrumentation/recording rules cũ sau giai đoạn tương thích.

Tag hygiene cũng là **quản lý phiên bản telemetry schema**. Một label bị đổi tên có thể không gây lỗi Java compile nhưng gây lỗi alerts âm thầm.

## 41. Cách kiểm tra cardinality trước merge

Code review cần rà soát tất cả vị trí tạo metrics:

~~~text
registry.counter(...)
Counter.builder(...)
Timer.builder(...)
DistributionSummary.builder(...)
Gauge.builder(...)
Observation.lowCardinalityKeyValue(...)
custom ObservationConvention
MeterFilter map(...)
Kafka/Micrometer binder configuration
~~~

Một bài test đơn giản có thể gọi instrumentation với nhiều event IDs khác nhau và kiểm tra số meters không tăng theo số events.

Ví dụ về logic test:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
KafkaProcessingMetrics metrics = new KafkaProcessingMetrics(registry);

for (int i = 0; i < 1000; i++) {
    metrics.recordSuccess();
}

long meterCount =
        registry.getMeters().stream()
                .filter(m -> m.getId().getName()
                        .equals("app.kafka.listener.records"))
                .count();

assertThat(meterCount).isEqualTo(1L);
~~~

Trong ví dụ, mỗi lần recordSuccess() dùng cùng set tags. Vì vậy 1.000 events chỉ tăng value của counter, **không tạo 1.000 meter identities**.

Nếu thay tag listener bằng "orders-" cộng event ID, bài test sẽ phát hiện meterCount tăng theo số events.

Không cần chạy test trên một triệu events chỉ để biết có vấn đề; test vài trăm đến vài nghìn IDs giả đã đủ chứng minh sự phụ thuộc cardinality không mong muốn.

## 42. Test MeterFilter từ chối tags bị cấm

Có thể unit test filter với SimpleMeterRegistry:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

registry.config().meterFilter(
        MeterFilter.deny(id ->
                id.getTag("event_id") != null));

registry.counter(
        "app.kafka.listener.records",
        "event_id", "E-1001")
    .increment();

assertThat(
        registry.find("app.kafka.listener.records")
                .meters())
        .isEmpty();
~~~

Đây là ví dụ định hướng kiểm thử; cần imports và assertion library tương ứng. MeterFilter có thể trả noop meter cho một registration bị deny, nên không suy luận việc counter.increment() không throw nghĩa là metric đã được ghi nhận.

Quan trọng hơn, đừng chỉ test filter. Nên test instrumentation **không tạo event_id tag ngay từ đầu**. Filter là phòng tuyến thứ hai để bắt lỗi từ code hoặc convention tương lai.

## 43. Incident: metrics backend quá tải vì event_id

Một tình huống thực tế có thể diễn ra:

~~~text
Deployment mới:
  thêm event_id tag vào listener timer

Traffic:
  10.000 records/phút

Sau vài phút:
  số meter IDs tăng nhanh
  /actuator/prometheus response lớn
  scrape duration tăng
  Prometheus ingestion và memory tăng
  dashboards chậm hoặc lỗi
~~~

Khi ứng dụng gặp lỗi nghiệp vụ, số failed event IDs cũng tăng, làm monitoring chịu thêm tải đúng lúc cần sử dụng nhất.

Quy trình xử lý khẩn cấp:

1. Xác định metric family và tag gây tăng series.
2. Xác nhận thay đổi vừa deploy hay custom instrumentation nào tạo label động.
3. Tạm **disable/deny metric nguy hiểm tại application registry** nếu có cơ chế cấu hình an toàn.
4. Nếu cần, dùng metric relabel drop/keep để giảm ingest vào backend.
5. Rollback hoặc hotfix instrumentation, bỏ event_id/exception_message từ metric labels.
6. Xem lại scrape duration, active series và series churn sau khắc phục.
7. Kiểm tra monitoring backend đã ổn định trước khi bật lại alerts/query nặng.
8. Lưu postmortem: vì sao review/test không bắt được cardinality.

Không vội xóa các metrics Kafka quan trọng phục vụ consumer lag, transaction failures hoặc DLT vì một metric custom lỗi. Cần khoanh vùng metric family bị ảnh hưởng.

## 44. Incident: partition tags tăng sau scale

Giả sử topic tăng từ 16 lên 256 partitions, service mở rộng từ 4 lên 30 consumers. Native client metrics theo client-id, topic, partition và node có thể tăng số series.

Không có tag event_id, nhưng:

~~~text
Số consumers tăng
Số partitions tăng
Số metrics per client tăng
Histogram buckets được bật rộng

=> Series tăng đáng kể
~~~

Đây không nhất thiết là bug instrumentation; có thể là **hệ quả của topology thay đổi**.

Giải pháp:

- Dự toán series trước khi tăng partitions.
- Chọn metric families cần chi tiết partition.
- Giảm redundancy giữa application metrics và native Kafka metrics.
- Dùng aggregate group-level alert và partition-level drill-down.
- Đánh giá scrape interval và retention.
- Điều chỉnh backend capacity hoặc metrics filtering.

Không xóa partition lag metrics mù quáng nếu chúng là nguồn duy nhất phát hiện hot partition.

## 45. Incident: client ID churn do restart loop

Một service có lỗi producer fencing và liên tục restart. Mỗi lần restart tạo client ID hoặc pod UID mới, làm metrics backend lưu thêm các time series ngắn hạn.

~~~text
12:00  pod-A-1 -> client_id=orders-abc
12:05  pod-A-2 -> client_id=orders-def
12:10  pod-A-3 -> client_id=orders-ghi
...
~~~

Khi điều tra:

1. Xác định root cause restart/fencing trước.
2. Đo series churn và số client IDs mới.
3. Kiểm tra một số metrics có thể dùng logical listener ID thay vì runtime ID không.
4. Giữ client ID chi tiết tại đúng những native metrics cần thiết.
5. Đảm bảo pod/instance labels ở scrape metadata không bị nhân bản thành nhiều biến thể.

Tag hygiene không thay thế reliability engineering của producer/container. Nếu ứng dụng crash-loop, việc giảm label churn chỉ xử lý phần telemetry overhead, không sửa nguyên nhân gốc.

## 46. Alerting không nên phụ thuộc tags không ổn định

Một alert nên dựa trên tín hiệu aggregate:

~~~promql
sum by (application, listener) (
  rate(app_kafka_listener_records_total{outcome="error"}[5m])
)
~~~

Nếu muốn tỷ lệ lỗi, cần tính cả tổng xử lý và bảo vệ mẫu số bằng clamp_min:

~~~promql
sum by (application, listener) (
  rate(app_kafka_listener_records_total{outcome="error"}[5m])
)
/
clamp_min(
  sum by (application, listener) (
    rate(app_kafka_listener_records_total[5m])
  ),
  0.001
)
~~~

PromQL trên minh họa ratio cho custom counter; điều kiện alert thực tế cần xét low traffic, missing data và SLO.

Không tạo một alert rule cho mỗi event ID hoặc exception message. Thay vào đó, alert theo listener/topic family/error category rồi link tới logs/traces có correlation context.

Khi muốn alert transaction fencing, nhóm theo application/listener/reason có kiểm soát; không tạo rule riêng cho mỗi transactional.id.

## 47. Dashboard thiết kế theo hai tầng

Một dashboard reliability hữu ích:

### Tầng 1: Overview

- Processing rate.
- Error rate.
- p95/p99 processing latency.
- Consumer lag max/group.
- Rebalance rate.
- DLT publish success/failure.
- Transaction commit/abort/fencing.
- Pause/stop/idle/non-responsive events.

Tất cả dùng tag sets nhỏ để tải dashboard nhẹ.

### Tầng 2: Drill-down

- Topic cụ thể trong allowlist.
- Partition lag.
- Client-specific Kafka native metrics.
- Exception class ở nhóm cần thiết.
- Trace/log link theo listener, event ID hoặc original topic/partition/offset.

Không nhất thiết duy trì partition-level views cho mọi service ở mọi dashboard. Khi cần điều tra, drill-down đủ để phân tích mà không nhân mọi metric theo partition và tenant.

## 48. Chỉ tiêu sức khỏe cho telemetry pipeline

Metrics pipeline cũng cần được monitoring:

| Chỉ tiêu | Khi tăng bất thường có thể nói lên |
|---|---|
| App meter registry size | Dynamic tag registration |
| Prometheus scrape samples | Tăng metric families hoặc label combinations |
| Scrape duration | Metrics endpoint quá lớn hoặc app chậm |
| Active series | Tag cardinality tăng |
| Series creation/churn | Random IDs, rollout/restart hoặc event tags |
| Remote write queue backlog | Backend không theo kịp ingestion |
| Metrics endpoint response bytes | App export quá nhiều samples |
| Query latency | High cardinality hoặc queries quá rộng |

Không phải mọi monitoring backend đều expose các metrics cùng tên. Hãy dùng metrics được chính Prometheus, collector hoặc vendor cung cấp ở phiên bản triển khai.

Nếu telemetry pipeline không khỏe, alerts có thể tới chậm hoặc không có dữ liệu. Vì vậy một chiến lược observability cần cân bằng giữa độ chi tiết và khả năng hoạt động của chính hệ thống giám sát.

## 49. Một chuẩn tag hygiene cho code review

Trước khi chấp nhận metric mới, hỏi:

1. Metric này phục vụ SLO, dashboard, alert hoặc capacity decision nào?
2. Những tags nào thực sự cần cho quyết định đó?
3. Mỗi tag tối đa bao nhiêu giá trị trong một ngày/tháng?
4. Có tag lấy từ record key, header, payload hoặc exception message không?
5. Có IDs biến động theo retry, deployment hoặc partition assignment không?
6. Nếu topic/tenant/partition count tăng 10 lần, series budget thay đổi ra sao?
7. Nếu bật histogram, mỗi combination sinh bao nhiêu bucket series?
8. Trùng instrumentation mặc định của Kafka/Micrometer không?
9. Có PII hoặc secrets bị đưa vào labels không?
10. Có MeterFilter và test phòng ngừa dynamic tags không?
11. Có dashboard/alert owner và lộ trình khi metric schema thay đổi không?
12. Có alert khi cardinality, churn hoặc scrape duration tăng bất thường không?

Một metric tốt nên có **giá trị rõ ràng, tag schema nhỏ, cardinality ước lượng được, và người sở hữu**. Không cần có càng nhiều tags càng tốt.

## 50. Quy trình triển khai metric cardinality và tag hygiene

Đối với một ứng dụng Spring Kafka production:

1. Liệt kê Spring Kafka listener metrics, producer metrics, native Kafka client metrics và custom metrics đang có.
2. Phân loại tags thành low, bounded và high/unbounded cardinality.
3. Chặn event_id, record_key, offset, raw exception_message, payload, tenant ID không giới hạn khỏi metric labels.
4. Xây dựng whitelist cho listener IDs, error categories, outcomes và topic families.
5. Dùng Micrometer common tags cho application/environment có giá trị ổn định.
6. Dùng Observation low-cardinality key values cho metric dimensions; high-cardinality context chỉ dùng cho trace/log có kiểm soát.
7. Áp dụng MeterFilter làm safety net cho tag cấm và giới hạn số tag values.
8. Ước lượng series theo số replicas, listeners, topics, partitions, outcomes và histogram buckets.
9. Giữ partition-level chi tiết chỉ trên những metrics cần để điều tra lag hoặc skew.
10. Không dùng Prometheus metric relabeling như giải pháp duy nhất cho meter explosion trong application.
11. Viết test với nhiều dynamic record IDs để chứng minh meter count không tăng theo message count.
12. Theo dõi active series, series churn, scrape duration, exporter response size và ingestion rate.
13. Thiết kế alerts aggregate theo service/listener/outcome; logs và traces dùng để tìm record cụ thể.
14. Có rollout/rollback plan khi thay đổi metric names hoặc tags.
15. Đưa tag schema và cardinality budget thành một phần của code review và vận hành thường xuyên.

**Metric cardinality và tag hygiene** là một phần của độ tin cậy hệ thống Spring Kafka, không phải tối ưu chi phí giám sát thuần túy. Một metric gây ra hàng trăm nghìn series có thể làm monitoring mất tác dụng ngay khi consumer lag, DLT failures hoặc transaction fencing tăng cao. Chọn **những nhãn có giới hạn, có ý nghĩa vận hành**, đồng thời để record ID, offset, exception details và correlation context ở logs/traces sẽ giúp hệ thống vừa phát hiện sự cố sớm, vừa truy nguyên được nguyên nhân mà không làm metrics backend quá tải.
