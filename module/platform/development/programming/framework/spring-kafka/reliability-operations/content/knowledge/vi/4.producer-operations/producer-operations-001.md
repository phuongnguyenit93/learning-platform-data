# KafkaTemplate metrics

Trong Spring Kafka, `KafkaTemplate` là API thường dùng để gửi record đến Kafka. Khi vận hành producer, chỉ biết ứng dụng có gọi `send()` thành công hay không là chưa đủ. Cần đo được thời gian gửi và chờ broker xác nhận, số lần gửi lỗi, tỷ lệ retry, kích thước batch, mức sử dụng buffer và các dấu hiệu cho thấy broker hoặc mạng đang làm producer chậm lại.

KafkaTemplate metrics giúp quan sát hoạt động gửi ở cấp ứng dụng. Khi kết hợp với metrics gốc của Kafka producer, metrics của broker và consumer lag, đội vận hành có thể phân biệt lỗi nằm ở code gửi, producer client, broker hay phần xử lý phía sau. Các chỉ số này cũng giúp đánh giá tác động của thay đổi `acks`, batching, compression, timeout và số partition.

## 1. Các lớp metrics cần phân biệt

Một hệ thống Spring Kafka có nhiều lớp quan sát. Không nên gom tất cả thành một chỉ số “Kafka latency” vì mỗi lớp đo một khoảng thời gian khác nhau.

| Lớp quan sát | Nguồn | Trả lời câu hỏi |
|---|---|---|
| KafkaTemplate timer/observation | Spring Kafka và Micrometer | Một lần gọi gửi từ ứng dụng mất bao lâu để hoàn tất hoặc báo lỗi? |
| Kafka producer client metrics | Kafka client được dùng bên trong template | Producer đang chờ broker, retry, gom batch hay cạn buffer ở mức nào? |
| Broker metrics | Kafka broker/JMX hoặc exporter | Broker có quá tải, mất replica, throttling hoặc chậm I/O không? |
| Consumer metrics | Listener container, Kafka consumer client | Record có được tiêu thụ kịp thời không, consumer lag có tăng không? |
| Business metrics | Mã nghiệp vụ | Sự kiện được phát có dẫn đến kết quả nghiệp vụ trong SLA không? |

Ví dụ, timer của KafkaTemplate có thể tăng vì producer phải chờ broker xác nhận. Nhưng nó cũng có thể tăng do producer buffer bị áp lực hoặc do mạng chậm. Ngược lại, timer gửi thấp không chứng minh sự kiện đã được consumer xử lý; record có thể nằm trong topic một thời gian dài.

## 2. KafkaTemplate metrics đo điều gì?

KafkaTemplate gửi record bất đồng bộ và nhận kết quả qua callback/future. Metrics ở cấp template thường ghi nhận thời gian của thao tác gửi từ lúc bắt đầu đến khi kết quả gửi được hoàn tất, cùng trạng thái thành công hoặc thất bại.

Trong các cấu hình Micrometer timer truyền thống của Spring Kafka, meter thường có tên `spring.kafka.template` và các tag mô tả template, kết quả và exception. Các tag phổ biến gồm:

- `name`: tên hoặc định danh KafkaTemplate.
- `result`: kết quả của lần gửi, thường phân biệt thành công và thất bại.
- `exception`: loại exception hoặc giá trị biểu thị không có exception.

Tên meter, tag và cách biểu diễn cụ thể có thể thay đổi theo phiên bản Spring Kafka và cách bật instrumentation. Hãy kiểm tra meter thực tế trong registry thay vì phụ thuộc vào một dashboard được sao chép từ phiên bản khác.

Timer cho biết số lần ghi nhận, tổng thời gian và thời gian cực đại; khi bật histogram, backend có thể tính các phân vị như p95 hoặc p99. Các phép đo này hữu ích để trả lời:

- Gửi record đang mất bao lâu ở p50, p95 và p99?
- Tỷ lệ lần gửi thất bại có tăng sau một lần deploy không?
- Một KafkaTemplate cụ thể có hành vi khác các template còn lại không?
- Thời gian gửi có tăng cùng lúc với retry hoặc producer buffer wait không?

Timer không đo thời gian consumer xử lý, không xác nhận tác động nghiệp vụ đã commit và không thay thế metrics của Kafka broker.

## 3. Bật Micrometer metrics truyền thống

Spring Kafka có hỗ trợ Micrometer timer cho KafkaTemplate. Khi ứng dụng có Micrometer registry phù hợp, template có thể ghi nhận thời gian gửi và các tag kết quả. Có thể bật và thêm tag ổn định khi tự cấu hình template:

~~~java
@Bean
KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory) {

    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);

    template.setMicrometerEnabled(true);
    template.setMicrometerTags(Map.of(
            "producer", "orders"));

    return template;
}
~~~

Ví dụ trên minh họa cấu hình template theo API của các phiên bản Spring Kafka có hỗ trợ Micrometer timers. Hãy kiểm tra API của phiên bản đang dùng; một số phiên bản mới ưu tiên Micrometer Observation và có thể có khác biệt về cách cấu hình.

Tag bổ sung nên là giá trị có tập hữu hạn, chẳng hạn tên luồng producer hoặc loại nghiệp vụ. Không thêm `orderId`, `customerId`, event id, correlation id hay message key làm tag metric. Mỗi giá trị tag mới có thể tạo một chuỗi time series riêng và làm tăng cardinality rất nhanh.

Nếu ứng dụng dùng nhiều KafkaTemplate, hãy đặt tên bean hoặc tag nhận diện có ý nghĩa để phân biệt producer. Không tạo template mới cho từng request hoặc từng tenant; điều đó làm tăng số producer client, kết nối, tài nguyên và meter cần quản lý.

## 4. Micrometer Observation và tracing

Từ Spring Kafka 3.0, KafkaTemplate hỗ trợ Micrometer Observation. Observation cung cấp một mô hình chung để ghi metrics và tạo trace khi ứng dụng có cấu hình tracing tương ứng. Đây thường là lựa chọn phù hợp cho ứng dụng Spring hiện đại vì một lần gửi có thể được liên kết với trace của request hoặc luồng xử lý đã tạo ra event.

Có thể bật Observation qua cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    template:
      observation-enabled: true
~~~

Khi tự tạo template, có thể cấu hình trực tiếp:

~~~java
@Bean
KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> producerFactory,
        ObservationRegistry observationRegistry) {

    KafkaTemplate<String, OrderEvent> template =
            new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    template.setObservationRegistry(observationRegistry);
    return template;
}
~~~

Nếu Spring Boot đã tự cấu hình KafkaTemplate và ObservationRegistry, hãy ưu tiên cấu hình qua property thay vì tạo một template khác không cần thiết. Cách đặt property và API có thể khác theo phiên bản Spring Boot/Spring Kafka; cần xác nhận phiên bản dependency thực tế.

Observation có thể tạo timer và span tùy theo các registry/handler được kết nối. Việc bật Observation không có nghĩa trace tự động xuất hiện ở backend nếu ứng dụng chưa cấu hình tracing exporter. Metrics và tracing cũng phục vụ hai mục đích khác nhau:

- Metrics tổng hợp xu hướng và tỷ lệ trên nhiều lần gửi.
- Trace giúp lần theo một request cụ thể qua các thành phần và thời điểm.

Không đưa event id hoặc customer id thành nhãn metric chỉ để truy vấn một sự kiện. Hãy giữ định danh chi tiết trong trace hoặc log có kiểm soát, còn metrics nên dùng tag có cardinality thấp.

### 4.1. Chọn giữa timer truyền thống và Observation

Timer truyền thống tập trung vào thời gian gửi và kết quả. Observation cung cấp điểm tích hợp rộng hơn cho metrics và tracing. Trong một ứng dụng, cần chọn cấu hình theo phiên bản Spring Kafka và yêu cầu quan sát để tránh tạo hai bộ đo trùng nhau.

Nếu Observation đã được bật, Spring Kafka có thể sử dụng Observation thay cho timer Micrometer truyền thống cho thao tác đó. Đừng giả định cả hai bộ meter đều xuất hiện. Hãy kiểm tra tên meter thực tế, tag và trace sau khi khởi động ứng dụng.

## 5. Metrics gốc của Kafka producer

KafkaTemplate dùng Kafka producer client bên dưới. Producer client cung cấp nhiều metrics mô tả hiệu năng nội bộ. Đây là lớp rất quan trọng khi timer ở cấp template tăng nhưng chưa rõ nguyên nhân.

Một số metrics thường được quan sát:

| Metric Kafka client | Ý nghĩa | Cách diễn giải |
|---|---|---|
| `record-send-rate` / `record-send-total` | Tốc độ và tổng số record gửi | Xác định producer có đang phát dữ liệu và throughput thay đổi ra sao |
| `record-error-rate` / `record-error-total` | Tốc độ và tổng số lỗi gửi | Phát hiện lỗi broker, serialization hoặc request |
| `record-retry-rate` / `record-retry-total` | Tốc độ và tổng số lần retry | Retry tăng có thể báo hiệu broker hoặc mạng không ổn định |
| `request-latency-avg` / `request-latency-max` | Độ trễ request ở producer client | Phản ánh thời gian request được broker xử lý/phản hồi ở góc nhìn client |
| `request-rate` / `request-total` | Tốc độ và tổng số request | Kết hợp với batch size để đánh giá hiệu quả gom batch |
| `batch-size-avg` / `batch-size-max` | Kích thước batch trung bình và lớn nhất | Batch nhỏ có thể làm tăng overhead request khi traffic thấp hoặc phân tán nhiều partition |
| `compression-rate-avg` | Tỷ lệ nén quan sát được | Đánh giá hiệu quả compression theo workload |
| `bufferpool-wait-ratio` | Tỷ lệ thời gian producer chờ buffer pool | Giá trị tăng có thể chỉ ra buffer bị áp lực |
| `bufferpool-wait-time-total` | Tổng thời gian chờ buffer | Dùng để phát hiện producer bị chặn khi buffer không còn đủ |
| `buffer-available-bytes` | Dung lượng buffer còn khả dụng | Giúp xác định producer có đang gần cạn bộ đệm không |
| `outgoing-byte-rate` | Tốc độ byte gửi đi | Theo dõi lưu lượng mạng do producer tạo ra |
| `produce-throttle-time-avg` | Thời gian throttling trung bình | Có thể cho thấy quota broker đang giới hạn producer |

Tên metric và tập metric có thể thay đổi theo phiên bản Kafka client. Các metric cũng thường có scope theo client, node hoặc connection. Cần giữ lại các dimension do Kafka cung cấp để xác định broker/producer liên quan, nhưng không tạo thêm tag tùy ý có cardinality cao.

### 5.1. Đọc các metric theo nhóm

**Nhóm gửi và lỗi:** `record-send-rate`, `record-error-rate` và `record-retry-rate` cho biết producer đang gửi với tốc độ nào và có gặp lỗi hay phải retry không. Retry tăng trước khi error tăng có thể là dấu hiệu broker bắt đầu chậm hoặc request thường xuyên timeout nhưng cuối cùng vẫn thành công.

**Nhóm latency:** `request-latency-avg` và `request-latency-max` mô tả thời gian request ở Kafka client. Giá trị trung bình có thể che khuất những request rất chậm, vì vậy cần kết hợp max, phân bố latency nếu hệ thống thu thập được và timer ở cấp template.

**Nhóm batching và compression:** `batch-size-avg` cùng `compression-rate-avg` giúp đánh giá producer có gom đủ dữ liệu và compression có hiệu quả không. Batch nhỏ không tự động là vấn đề; với luồng ít traffic, batch nhỏ có thể là hệ quả bình thường.

**Nhóm buffer:** `bufferpool-wait-ratio`, `bufferpool-wait-time-total` và `buffer-available-bytes` giúp phát hiện producer không đẩy dữ liệu ra nhanh bằng tốc độ ứng dụng tạo dữ liệu. Khi buffer chờ tăng, kiểm tra broker latency, network, request in-flight và tốc độ phát trước khi chỉ tăng `buffer.memory`.

## 6. Truy cập metrics từ KafkaTemplate

KafkaTemplate cung cấp quyền truy cập đến metrics của producer client thông qua API `metrics()` ở các phiên bản hỗ trợ:

~~~java
Map<MetricName, ? extends Metric> producerMetrics =
        kafkaTemplate.metrics();

producerMetrics.forEach((name, metric) -> {
    Object value = metric.metricValue();
    log.debug("Kafka producer metric: name={}, value={}",
            name.name(), value);
});
~~~

Đoạn code chỉ minh họa cách đọc metric. Trong ứng dụng production, không nên log toàn bộ metric ở mỗi request hoặc tạo meter mới cho từng metric mỗi lần gọi. Hãy dùng Micrometer, JMX hoặc hệ thống thu thập metrics hiện có để scrape định kỳ. Việc đọc `metrics()` hữu ích cho chẩn đoán hoặc công cụ nội bộ, nhưng không thay thế pipeline metrics chuẩn.

ProducerFactory có thể quản lý hoặc chia sẻ producer tùy cấu hình và cách sử dụng. Vì vậy, khi đọc metrics cần hiểu metric thuộc producer client nào và scope của nó. Nếu có nhiều KafkaTemplate dùng chung factory, một số metrics client có thể phản ánh hoạt động tổng hợp của producer được chia sẻ chứ không chỉ một bean template.

## 7. Xuất metrics qua Spring Boot Actuator

Trong ứng dụng Spring Boot, Actuator cung cấp endpoint để kiểm tra health và expose metrics. Để xuất metrics sang Prometheus, ứng dụng thường cần Actuator và registry Prometheus:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Ví dụ cấu hình expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Sau khi khởi động, endpoint Prometheus thường có dạng `/actuator/prometheus`. Cần xác nhận endpoint được expose trong môi trường triển khai và được bảo vệ bằng cơ chế xác thực, network policy hoặc reverse proxy phù hợp. Không nên công khai toàn bộ Actuator endpoints ra Internet.

Metrics có thể được xuất sang Prometheus, OTLP hoặc backend khác tùy registry và hạ tầng quan sát. Không cần buộc mọi ứng dụng dùng cùng một backend; điều quan trọng là giữ được tên metric, tag và quy ước dashboard nhất quán.

### 7.1. Kiểm tra meter đã được tạo

Khi KafkaTemplate gửi record, kiểm tra endpoint `/actuator/metrics` hoặc registry để xác nhận timer/observation đã xuất hiện. Ví dụ, có thể kiểm tra meter `spring.kafka.template` nếu ứng dụng dùng Micrometer timer truyền thống. Với Observation, tên meter và tag có thể khác theo convention.

Nếu không thấy meter:

1. Xác nhận dependency Micrometer và registry đã nằm trên classpath.
2. Xác nhận template đang dùng được cấu hình instrumentation.
3. Gửi một record thử và chờ callback/future hoàn tất.
4. Kiểm tra cấu hình Observation hoặc Micrometer timer của phiên bản Spring Kafka.
5. Kiểm tra meter filter hoặc cấu hình export có loại bỏ meter hay không.
6. Kiểm tra đúng application instance và đúng registry/endpoint.

Đừng kết luận metrics không hoạt động chỉ vì tìm sai tên meter hoặc truy vấn sai tag. Hãy xem danh sách meter thực tế của ứng dụng.

## 8. Tag và cardinality

Tag cho phép chia metrics theo một số thuộc tính có ý nghĩa. Ví dụ `producer=orders` hoặc `result=failure` có thể giúp xác định nhóm gửi đang gặp lỗi. Tuy nhiên, mỗi tổ hợp tag có thể tạo một time series riêng.

Các tag thường phù hợp:

- Tên template có tập giá trị nhỏ, được định nghĩa khi ứng dụng khởi động.
- Tên service hoặc luồng producer ổn định.
- Kết quả gửi thành công/thất bại.
- Loại exception theo class nếu số loại exception được kiểm soát.
- Topic có tập tên hữu hạn và không được tạo động vô hạn.

Các tag không phù hợp:

- `orderId`, `customerId`, `userId` hoặc event id.
- Message key có thể có hàng triệu giá trị.
- Correlation id hoặc trace id.
- Exception message chứa nội dung động.
- URL đầy đủ hoặc tên tenant tùy ý nếu số lượng tenant lớn.

Ví dụ, nếu một service xử lý 500.000 order mỗi ngày và thêm `orderId` vào tag, registry có thể tạo hàng trăm nghìn series. Điều này làm tăng bộ nhớ, tải scrape, chi phí lưu trữ và độ trễ truy vấn. Hãy dùng log hoặc trace để tra cứu một order cụ thể.

Nếu cần phân biệt loại nghiệp vụ, dùng một thuộc tính phân loại có tập giá trị nhỏ như `event_type=order_created` hoặc `event_type=order_cancelled`, sau khi cân nhắc số tổ hợp tag. Không lấy giá trị tùy ý từ payload để tạo nhãn.

## 9. Histogram và percentile

Timer mặc định có thể cung cấp count, total time và max. Để quan sát p95 hoặc p99, backend cần có dữ liệu phân bố phù hợp, thường bằng histogram hoặc percentile configuration.

Histogram hữu ích khi cần so sánh tail latency giữa các instance và truy vấn percentile ở Prometheus. Đổi lại, mỗi bucket và tổ hợp tag có thể làm tăng số series. Chỉ bật histogram cho các meter quan trọng và giới hạn tag.

Ví dụ, có thể cấu hình histogram cho meter gửi KafkaTemplate qua cơ chế distribution configuration của Micrometer/Spring Boot. Cú pháp property cụ thể phụ thuộc phiên bản Spring Boot và tên meter thực tế; hãy xác nhận meter name sau khi bật timer hoặc Observation trước khi cấu hình.

Không nên chỉ xem average latency. Nếu average là 10 ms nhưng p99 là 2 giây, một nhóm nhỏ request vẫn có trải nghiệm rất xấu. Theo dõi p50, p95, p99 cùng request rate và error rate sẽ giúp xác định liệu thay đổi có cải thiện phần lớn request hay chỉ thay đổi trung bình.

## 10. Xây dựng dashboard KafkaTemplate

Dashboard producer nên trả lời ba câu hỏi: producer có gửi được không, gửi mất bao lâu và điều gì khiến nó chậm?

Một dashboard hữu ích có thể gồm:

| Panel | Metrics | Mục đích |
|---|---|---|
| Send rate | Số lần gửi thành công theo thời gian | Theo dõi lưu lượng phát |
| Send duration | p50/p95/p99 của timer KafkaTemplate | Quan sát latency ở cấp ứng dụng |
| Error rate | Số lần gửi lỗi và tỷ lệ lỗi | Phát hiện producer không gửi được |
| Retry rate | Kafka client retry rate | Phát hiện request phải thử lại |
| Request latency | Kafka producer request latency | Phân biệt chậm ở client/broker |
| Batch size | Batch size trung bình | Kiểm tra hiệu quả batching |
| Compression | Compression rate | Theo dõi hiệu quả nén |
| Buffer pressure | Buffer wait ratio/time và available bytes | Phát hiện producer bị nghẽn buffer |
| Throttling | Produce throttle time | Phát hiện quota giới hạn |

Nếu có nhiều template, cho phép lọc theo tên template hoặc producer tag ổn định. Giữ cùng một khoảng thời gian khi so sánh latency, error và retry để thấy mối tương quan.

### 10.1. Ví dụ truy vấn Prometheus

Tên metric Prometheus thường được chuẩn hóa từ meter Micrometer, ví dụ timer có thể xuất thành metric dạng `spring_kafka_template_seconds_*`. Tên cuối cùng phụ thuộc instrumentation và registry, vì vậy hãy kiểm tra `/actuator/prometheus` trước khi dùng truy vấn.

Với một timer histogram, truy vấn percentile có dạng:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(spring_kafka_template_seconds_bucket[5m])
  )
)
~~~

Tốc độ ghi nhận timer có thể được ước lượng bằng:

~~~promql
sum(rate(spring_kafka_template_seconds_count[5m]))
~~~

Các truy vấn trên là mẫu minh họa. Nếu meter thực tế có tên khác hoặc tag phân biệt template/result, hãy điều chỉnh truy vấn để giữ dimension cần thiết và tránh cộng gộp các producer có hành vi khác nhau.

## 11. Alert cho producer metrics

Alert nên tập trung vào dấu hiệu ảnh hưởng đến khả năng phát sự kiện hoặc SLA, thay vì cảnh báo chỉ vì một metric thay đổi trong vài giây.

Các tình huống nên cân nhắc cảnh báo:

- Send error rate tăng vượt baseline trong một khoảng thời gian.
- p95 hoặc p99 send duration vượt ngân sách latency.
- Retry rate tăng kéo dài cùng lúc với request latency.
- Buffer wait ratio tăng và buffer available giảm.
- Produce throttle time tăng do quota.
- Send rate giảm bất thường trong khi lưu lượng đầu vào của ứng dụng vẫn cao.
- Under-replicated partitions hoặc ISR shrink xuất hiện ở cluster.

Một alert chỉ dựa trên `record-error-rate` có thể bỏ sót tình huống producer retry thành công nhưng latency đã tăng mạnh. Kết hợp retry, request latency và timer template giúp phát hiện sớm hơn.

Ngưỡng alert nên được xác định từ SLO và baseline của hệ thống. Không đặt một ngưỡng chung cho mọi topic, mọi môi trường hoặc mọi thời điểm trong ngày. Cần có thời gian duy trì điều kiện (for duration) để tránh cảnh báo chập chờn do spike ngắn.

## 12. Chẩn đoán các tình huống thường gặp

### 12.1. KafkaTemplate send duration tăng

Kiểm tra lần lượt:

1. `request-latency-avg/max` có tăng cùng lúc không?
2. `record-retry-rate` hoặc `record-error-rate` có tăng không?
3. Buffer wait ratio có tăng và buffer available có giảm không?
4. Broker có produce request latency, disk/network pressure hoặc throttling không?
5. ISR có shrink hoặc partition leader có thay đổi liên tục không?
6. Traffic có tăng đột biến hoặc key phân bố tạo hot partition không?

Nếu request latency và retry cùng tăng, ưu tiên kiểm tra broker, network và ISR. Nếu request latency bình thường nhưng buffer wait tăng, producer có thể đang tạo dữ liệu nhanh hơn tốc độ gửi; kiểm tra số request in-flight, batching và tốc độ phát.

### 12.2. Send error tăng nhưng request latency không tăng

Lỗi có thể xuất hiện nhanh do authorization, topic không tồn tại, serialization hoặc cấu hình producer không hợp lệ. Xem exception class và log có correlation/event id. Không retry vô hạn lỗi cấu hình hoặc lỗi dữ liệu vì retry không sửa được nguyên nhân.

### 12.3. Retry tăng nhưng hầu hết send vẫn thành công

Đây có thể là dấu hiệu cảnh báo sớm: broker hoặc mạng có các request chậm/chập chờn nhưng producer còn phục hồi được. So sánh retry rate với request latency, broker throttling, ISR và network errors. Nếu retry tăng kéo dài, latency đầu cuối có thể vượt SLA dù error rate cuối cùng vẫn thấp.

### 12.4. Producer metrics bình thường nhưng sự kiện đến consumer chậm

KafkaTemplate timer chỉ đo thao tác gửi. Kiểm tra consumer lag, tốc độ poll, thời gian xử lý listener, downstream latency và số partition được gán. Cũng cần kiểm tra record có đang chờ trong retry topic hoặc bị xử lý theo thứ tự khác do non-blocking retry không.

### 12.5. Metrics biến mất sau khi nâng cấp

Kiểm tra thay đổi phiên bản Spring Boot, Spring Kafka, Micrometer và Kafka client. Nếu chuyển từ Micrometer timer sang Observation, tên meter hoặc tag có thể thay đổi. Kiểm tra cấu hình observation-enabled, registry, meter filter và dashboard query. Không tạo meter thay thế ngay khi chưa xác định nguyên nhân đổi tên hoặc đổi instrumentation.

## 13. Liên kết metrics với log và trace

Metrics cho biết vấn đề xảy ra trên diện rộng; log và trace giúp tìm một lần gửi cụ thể. Khi gửi event, nên có event id và correlation id trong log context hoặc message header nếu kiến trúc hỗ trợ.

Không đưa các định danh này thành metric tag. Có thể dùng chúng trong log có cấu trúc hoặc trace để tra cứu một event. Cần kiểm soát quyền truy cập và tránh log payload nhạy cảm.

Với Observation/tracing, trace có thể nối request đầu vào, thao tác gửi Kafka và các bước tiếp theo nếu context được truyền qua message header và consumer instrumentation được cấu hình tương thích. Không giả định trace context tự động đi qua mọi custom serializer hoặc hệ thống trung gian; hãy kiểm thử propagation trong môi trường thực tế.

## 14. Kiểm thử instrumentation

Trước khi triển khai dashboard và alert, hãy kiểm thử instrumentation:

1. Gửi một record hợp lệ và xác nhận timer/observation được ghi nhận.
2. Gửi record vào topic không tồn tại hoặc tạo lỗi phù hợp với môi trường test để xác nhận failure metric.
3. Mô phỏng broker chậm hoặc mất kết nối để quan sát retry và latency.
4. Xác nhận metrics producer client có các dimension cần thiết.
5. Kiểm tra endpoint Prometheus hoặc backend tương ứng có scrape được meter.
6. Kiểm tra tag không chứa event id, message key hoặc dữ liệu cá nhân.
7. Xác nhận histogram và percentile xuất hiện nếu dashboard cần p95/p99.
8. Kiểm tra alert bằng cách tạo điều kiện thử nghiệm có kiểm soát.

Test nên xác nhận cả hai phía: metrics xuất hiện và nghiệp vụ gửi thực sự có kết quả mong muốn. Một metric timer được ghi nhận không có nghĩa record đã được consumer xử lý.

## 15. Checklist vận hành KafkaTemplate metrics

### Instrumentation

- [ ] Phiên bản Spring Kafka và cách cấu hình Micrometer/Observation đã được xác định.
- [ ] KafkaTemplate đang dùng được instrument đúng cách.
- [ ] Metrics timer/observation và Kafka producer client được phân biệt rõ.
- [ ] Kết quả thành công và thất bại đều được ghi nhận.
- [ ] Observation/tracing được bật khi cần và registry/exporter đã được cấu hình.

### Chất lượng metrics

- [ ] Có send rate, duration, error và retry.
- [ ] Có request latency, batch size, compression và buffer metrics.
- [ ] Có histogram nếu cần p95/p99.
- [ ] Tag chỉ dùng giá trị có cardinality thấp.
- [ ] Không dùng event id, customer id, order id, message key hoặc trace id làm metric tag.

### Dashboard và alert

- [ ] Dashboard phân biệt template, producer client và broker.
- [ ] Có thể đối chiếu producer latency với consumer lag.
- [ ] Alert dựa trên SLO/baseline và có thời gian duy trì phù hợp.
- [ ] Endpoint metrics được bảo vệ và chỉ expose cần thiết.
- [ ] Dashboard/query đã được kiểm tra sau nâng cấp dependency.

## Kết luận

KafkaTemplate metrics cho biết thao tác gửi ở cấp ứng dụng mất bao lâu và kết thúc với kết quả nào. Metrics gốc của Kafka producer giải thích thêm retry, request latency, batching, compression và áp lực buffer. Micrometer timer hoặc Observation cung cấp đường xuất dữ liệu sang Actuator và backend giám sát; tracing và log giúp điều tra từng sự kiện. Khi kết hợp các lớp này với broker metrics, consumer lag và business metrics, đội vận hành có thể phát hiện producer chậm, phân biệt lỗi broker với lỗi ứng dụng và đánh giá tác động của thay đổi cấu hình mà không nhầm thời gian gửi với thời gian hoàn tất nghiệp vụ.
