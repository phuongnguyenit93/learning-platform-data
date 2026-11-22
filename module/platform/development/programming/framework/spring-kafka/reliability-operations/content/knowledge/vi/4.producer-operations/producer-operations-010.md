# Đặt client.id có thể truy vết

Trong Kafka, **client.id** là tên logic mà một Kafka client gửi kèm các request đến broker. Với Spring Kafka, producer bên dưới KafkaTemplate sử dụng thuộc tính này để broker và hệ thống quan sát nhận biết request đến từ client nào. Đặt client.id rõ ràng giúp tìm log, phân tích metric, phân biệt các luồng gửi và điều tra sự cố trong production.

client.id là một phần của khả năng vận hành producer. Nó không thay thế event ID, trace ID, producer ID hoặc danh tính bảo mật. Mỗi loại định danh trả lời một câu hỏi khác nhau: client.id cho biết request đến từ Kafka client nào; event ID cho biết sự kiện nghiệp vụ nào đang được phát; trace ID nối các bước trong một request phân tán; producer ID là định danh do Kafka quản lý để hỗ trợ idempotence và transaction.

## 1. client.id là gì?

Kafka producer được tạo từ cấu hình của Kafka client. Trong cấu hình đó, thuộc tính **client.id** đặt tên logic cho producer. Spring Kafka chuyển cấu hình này xuống KafkaProducer mà KafkaTemplate sử dụng.

Khi producer gửi request, client ID được đưa vào request header của giao thức Kafka. Broker có thể dùng thông tin này trong log, metric và chính sách quota. Ở phía ứng dụng, Kafka client cũng dùng client ID làm nhãn trong các metric và thông tin log liên quan đến client.

Luồng khái quát:

~~~text
Ứng dụng Spring
       |
       | KafkaTemplate.send(...)
       v
ProducerFactory
       |
       | tạo / quản lý KafkaProducer
       v
KafkaProducer
       |
       | client.id = orders-prod-publisher
       | ProduceRequest + request header
       v
Kafka broker
       |
       +--> broker log / request log
       |
       +--> request metrics / client quota

Ứng dụng quan sát producer metrics
       |
       +--> client-id = orders-prod-publisher
~~~

Ví dụ, nếu nhiều ứng dụng cùng gửi vào topic orders, broker có thể nhận diện request đến từ orders-api, order-replay và billing-service thông qua client ID khác nhau. Khi một luồng gửi có tỷ lệ retry cao, người vận hành có thể lọc log và metric theo client ID để khoanh vùng.

client.id là chuỗi do ứng dụng cấu hình. Nếu không đặt, Kafka client có thể tự tạo một tên mặc định như producer-1. Tên tự sinh hữu ích cho một số log trong lúc phát triển, nhưng khó diễn giải khi có nhiều service, nhiều instance và nhiều producer chạy đồng thời.

## 2. client.id giúp truy vết điều gì?

Một client ID có quy ước đặt tên rõ ràng hỗ trợ nhiều công việc vận hành:

| Nhu cầu | client.id hỗ trợ như thế nào |
|---|---|
| Tìm log | Nhận biết request hoặc thông báo log liên quan đến producer cụ thể. |
| Phân tích metric | Phân biệt metric của các Kafka client; có thể lọc theo nhãn client ID nếu hệ thống thu thập giữ nhãn này. |
| Điều tra lỗi gửi | Đối chiếu retry, request latency, lỗi broker và log của service phát sinh request. |
| Phân biệt luồng nghiệp vụ | Nhận biết producer gửi đơn hàng, phát lại dữ liệu, gửi audit hoặc gửi thông báo. |
| Quản lý quota | Broker có thể áp dụng client quota theo client ID để giới hạn tốc độ dữ liệu hoặc mức sử dụng request. |
| Đối chiếu môi trường | Phân biệt producer ở local, staging và production khi các môi trường cùng xuất hiện trong hệ thống giám sát. |

Ví dụ, một dashboard có thể nhóm các metric producer theo client ID:

~~~text
orders-prod-publisher
  record-send-rate
  record-error-rate
  record-retry-rate
  request-latency-avg
  request-latency-max

orders-prod-replay
  record-send-rate
  record-error-rate
  record-retry-rate
  request-latency-avg
  request-latency-max
~~~

Tên metric và tập metric có sẵn tùy thuộc phiên bản Kafka client, cách exporter thu thập và hệ thống monitoring. Điểm quan trọng là client ID cung cấp một nhãn có ý nghĩa để phân tách số liệu của từng Kafka client.

client.id cũng có thể xuất hiện trong log broker, đặc biệt khi bật log liên quan đến request hoặc client. Mức độ chi tiết phụ thuộc cấu hình logging của broker. Không nên giả định mọi broker log đều ghi mọi request ở mức mặc định; hãy kiểm tra log level và định dạng log đang triển khai.

## 3. Phân biệt các loại định danh

Một hệ thống Spring Kafka có thể sử dụng nhiều loại ID cùng lúc. Dùng nhầm một ID cho mục đích khác có thể khiến việc truy vết sai lệch.

| Định danh | Ai tạo / cấu hình? | Phạm vi và mục đích |
|---|---|---|
| client.id | Ứng dụng cấu hình cho Kafka client | Nhận biết producer hoặc consumer client trong log, metric và quota. |
| producer ID | Kafka cấp cho producer | Định danh producer trong giao thức Kafka, phục vụ idempotence và transaction. |
| event ID | Ứng dụng hoặc domain tạo | Nhận biết một sự kiện nghiệp vụ xuyên suốt các lần phát lại hoặc xử lý lại. |
| trace ID | Hệ thống tracing tạo hoặc truyền tiếp | Nối các span của một request qua nhiều service. |
| correlation ID | Ứng dụng hoặc hệ thống tích hợp tạo | Đối chiếu các thao tác có liên quan trong log hoặc quy trình nghiệp vụ. |
| consumer group ID | Ứng dụng cấu hình cho consumer group | Xác định nhóm consumer phối hợp đọc và chia partition. |

### client.id không phải producer ID

producer ID do Kafka quản lý và có vai trò trong cơ chế idempotent producer. client.id là tên logic do ứng dụng đặt và có thể giữ ổn định qua nhiều lần khởi động. Đổi client.id không có nghĩa tạo ra một event mới, cũng không thay thế cơ chế sequence number của idempotence.

### client.id không phải event ID

Một producer có thể gửi hàng triệu event với cùng một client ID. Đây là điều bình thường: client.id nhận diện tiến trình hoặc vai trò producer, còn event ID nhận diện từng sự kiện.

Nếu đưa event ID vào client.id, mỗi event sẽ tạo ra một tên client khác nhau về mặt quan sát. Cách này làm tăng cardinality của metric và gây khó khăn cho quota, dashboard, log search. Hãy đặt event ID trong payload hoặc record header.

### client.id không phải trace ID

Trace ID thay đổi theo trace hoặc request. client.id thường ổn định trong suốt vòng đời của một KafkaProducer. Một producer có thể gửi record thuộc nhiều trace khác nhau, vì vậy không nên đặt client.id bằng trace ID của request hiện tại.

Nếu cần nối một event Kafka với trace nguồn, hãy truyền trace context qua record header bằng cơ chế tracing tương thích của ứng dụng. Khi điều tra, dùng client.id để xác định producer và trace ID để theo dõi request đã tạo ra event.

### client.id không phải danh tính bảo mật

client.id là nhãn do client tự khai báo. Nó không chứng minh ứng dụng là service nào và không thay thế SASL principal, TLS client certificate hoặc cơ chế xác thực khác. Broker authorization dựa trên principal và ACL, không nên dựa vào client.id để cấp quyền truy cập topic.

Một client có thể khai báo client.id giống tên của service khác nếu không có chính sách bổ sung. Vì vậy, dùng client ID cho quan sát và quota là phù hợp; dùng nó như bằng chứng xác thực hoặc ranh giới tin cậy là không phù hợp.

## 4. Quy ước đặt tên có thể truy vết

Một client ID hữu ích cần dễ đọc, ổn định và phân biệt được vai trò. Nên chọn một cấu trúc đơn giản, ví dụ:

~~~text
<service>-<environment>-<role>
~~~

Ví dụ:

| client.id | Ý nghĩa |
|---|---|
| orders-prod-publisher | Producer chính của service orders trong production. |
| orders-prod-replay | Producer dùng để phát lại dữ liệu của orders trong production. |
| billing-prod-publisher | Producer của service billing trong production. |
| orders-staging-publisher | Producer của orders trong staging. |
| inventory-dev-publisher | Producer của inventory trong môi trường phát triển. |

Nếu cần phân biệt từng instance, có thể thêm hậu tố instance:

~~~text
<service>-<environment>-<role>-<instance>
~~~

Ví dụ:

~~~text
orders-prod-publisher-pod-7f8c9
orders-prod-publisher-pod-a31d2
~~~

Hậu tố instance giúp xác định pod hoặc process nào có vấn đề. Nó đặc biệt hữu ích khi chỉ một replica bị lỗi mạng, retry nhiều hoặc có độ trễ khác biệt so với các replica còn lại.

### Chọn ID chung hay ID riêng cho từng instance?

Đây là quyết định về mức chi tiết quan sát. Hai cách đều có ích, nhưng phục vụ mục tiêu khác nhau:

| Cách đặt | Lợi ích | Đánh đổi |
|---|---|---|
| Cùng một client ID cho tất cả instance của một vai trò | Metric được gom theo service/role; tên ổn định và ít nhãn hơn. | Khó nhận ra một pod cụ thể đang lỗi chỉ bằng client ID. |
| Client ID riêng cho từng instance | Có thể lọc log và metric theo process hoặc pod. | Số lượng nhãn tăng khi scale; dashboard và hệ thống metrics có thể chịu cardinality cao hơn. |

Có thể dùng một quy ước kết hợp: client ID ổn định theo service và role cho dashboard tổng quan, còn instance ID, hostname hoặc pod name được ghi trong log ứng dụng và resource attributes của telemetry. Nếu cần phân tích metric theo instance, thêm suffix có vòng đời phù hợp và theo dõi cardinality.

Không nên tạo client ID mới cho mỗi HTTP request, mỗi user hoặc mỗi message. KafkaProducer là client có vòng đời dài; client ID nên mô tả client đó, không mô tả một lần gọi API.

### Các nguyên tắc đặt tên

- Dùng chữ thường, số và dấu gạch ngang để dễ đọc, tìm kiếm và thống nhất giữa các môi trường.
- Bao gồm service hoặc ứng dụng, môi trường và vai trò producer khi cần.
- Chọn một tên ổn định qua các lần restart nếu mục tiêu là so sánh xu hướng dài hạn.
- Chỉ thêm instance suffix khi có nhu cầu quan sát ở cấp instance.
- Không đưa tên người dùng, email, access token, dữ liệu khách hàng hoặc thông tin bí mật vào client ID.
- Tránh tên quá chung như producer, kafka-client hoặc app nếu có nhiều client cùng loại.
- Tránh tên dài chứa nhiều thuộc tính thay đổi liên tục khiến log và metric khó lọc.

## 5. Cấu hình client.id trong Spring Boot

Spring Boot có thuộc tính chung **spring.kafka.client-id** để đặt client ID cho các Kafka client được cấu hình qua auto-configuration. Nếu muốn đặt riêng cho producer, có thể truyền thuộc tính Kafka **client.id** trong map **spring.kafka.producer.properties**.

Ví dụ đặt ID riêng cho producer trong application.yml:

~~~yaml
spring:
  application:
    name: orders-service
  kafka:
    producer:
      acks: all
      properties:
        "[client.id]": orders-prod-publisher
        "[enable.idempotence]": true
~~~

Trong ví dụ này, producer được tạo bởi cấu hình producer của Spring Boot dùng client ID orders-prod-publisher. Các producer khác như consumer hoặc AdminClient có thể được cấu hình bằng client ID riêng tùy mục tiêu quan sát.

Nếu muốn đặt client ID chung cho Kafka clients do Spring Boot auto-configuration tạo, có thể khai báo:

~~~yaml
spring:
  kafka:
    client-id: orders-prod
~~~

Thuộc tính chung hữu ích khi mọi client của ứng dụng có thể dùng cùng một nhãn service. Nếu cần phân biệt producer với consumer, hãy đặt ID riêng trong cấu hình cụ thể của từng loại client. Với producer, thuộc tính trong map producer có thể ghi đè giá trị chung khi được áp dụng trong cấu hình producer.

Tương đương trong application.properties:

~~~properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[client.id]=orders-prod-publisher
spring.kafka.producer.properties[enable.idempotence]=true
~~~

Khi dùng YAML, dấu ngoặc vuông trong key của map giúp giữ nguyên tên Kafka property có dấu chấm. Khi dùng properties file, cú pháp dấu ngoặc vuông giữ key client.id như một phần tử của map.

### Đặt client ID theo môi trường

Không nên hard-code tên production vào file cấu hình dùng chung cho mọi môi trường. Có thể dùng profile riêng cho từng môi trường và đặt giá trị client ID ổn định trong profile tương ứng.

Ví dụ trong application-prod.yml:

~~~yaml
spring:
  application:
    name: orders-service
  kafka:
    producer:
      properties:
        "[client.id]": orders-service-prod-publisher
~~~

Ví dụ trong application-local.yml:

~~~yaml
spring:
  application:
    name: orders-service
  kafka:
    producer:
      properties:
        "[client.id]": orders-service-local-publisher
~~~

Nếu cần phân biệt từng instance, có thể tạo profile hoặc cấu hình triển khai riêng với hậu tố pod/process. Hãy cân nhắc tác động của hostname hoặc pod name lên cardinality. Nếu hệ thống thường xuyên tạo và hủy pod, metric theo client ID có thể sinh ra nhiều chuỗi nhãn ngắn hạn.

## 6. Cấu hình client.id bằng ProducerFactory

Khi ứng dụng tự tạo ProducerFactory, có thể đặt client ID trực tiếp bằng ProducerConfig.CLIENT_ID_CONFIG. KafkaTemplate sẽ dùng ProducerFactory để tạo hoặc quản lý KafkaProducer theo cấu hình đó.

~~~java
Map<String, Object> producerProps = new HashMap<>();

producerProps.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "kafka-1:9092,kafka-2:9092");
producerProps.put(
        ProducerConfig.CLIENT_ID_CONFIG,
        "orders-prod-publisher");
producerProps.put(
        ProducerConfig.ACKS_CONFIG,
        "all");
producerProps.put(
        ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
        true);

ProducerFactory<String, OrderEvent> producerFactory =
        new DefaultKafkaProducerFactory<>(producerProps);

KafkaTemplate<String, OrderEvent> kafkaTemplate =
        new KafkaTemplate<>(producerFactory);
~~~

Đoạn mã chỉ minh họa các thuộc tính liên quan. Trong ứng dụng thực tế, cần khai báo serializer, bảo mật, bootstrap server và các cấu hình khác theo môi trường.

Nếu có hai luồng gửi với mục đích khác nhau, có thể tạo hai ProducerFactory và KafkaTemplate riêng với client ID riêng:

~~~java
// ProducerFactory chính
producerProps.put(
        ProducerConfig.CLIENT_ID_CONFIG,
        "orders-prod-publisher");

// ProducerFactory phát lại dữ liệu
replayProducerProps.put(
        ProducerConfig.CLIENT_ID_CONFIG,
        "orders-prod-replay");
~~~

Cách tổ chức này giúp phân biệt lưu lượng gửi thông thường và lưu lượng replay trong log và metric. Cần quản lý vòng đời các factory, producer và template để đóng tài nguyên đúng cách.

### Nhiều KafkaTemplate dùng chung ProducerFactory

Nếu nhiều KafkaTemplate dùng chung một ProducerFactory, chúng có thể sử dụng cùng cấu hình và cùng KafkaProducer được factory quản lý. Khi đó, client.id nhận diện KafkaProducer dùng chung, không tự động phân biệt từng template hoặc từng phương thức nghiệp vụ.

Nếu cần phân biệt các luồng gửi ở mức template nhưng vẫn muốn dùng chung producer, hãy bổ sung event type, correlation ID hoặc trace context vào log và record header. Nếu cần client ID riêng thực sự, phải tạo cấu hình và producer factory riêng phù hợp.

### Khi thay đổi client.id

client.id được đọc khi KafkaProducer được khởi tạo. Thay đổi giá trị trong file cấu hình không tự đổi tên một producer đã được tạo và đang chạy. Cần tạo lại producer hoặc khởi động lại ứng dụng theo quy trình triển khai để client mới sử dụng ID mới.

Với Spring Kafka, hãy xem xét cách ProducerFactory cache và quản lý producer. Nếu cập nhật cấu hình động, phải đảm bảo producer cũ được đóng đúng cách và producer mới được tạo từ cấu hình mới; không nên thay đổi map cấu hình đang được dùng mà không quản lý vòng đời.

## 7. Kết hợp client.id với log và metric

client.id chỉ có ích khi hệ thống quan sát thu thập và hiển thị nó. Cần cấu hình logging và metrics để người vận hành có thể lọc theo cùng một quy ước tên.

### Log phía ứng dụng

Khi ghi log kết quả gửi, nên có event ID cùng metadata Kafka và thông tin ngữ cảnh. client.id thường đã có trong metric hoặc log nội bộ của Kafka client, nhưng việc ghi thêm tên luồng gửi ở log nghiệp vụ có thể giúp tìm kiếm thuận tiện.

~~~java
public CompletableFuture<SendResult<String, OrderEvent>> publish(
        OrderEvent event) {

    return kafkaTemplate
            .send("orders", event.orderId(), event)
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    log.error(
                            "Kafka publish failed, eventId={}, orderId={}",
                            event.eventId(),
                            event.orderId(),
                            exception);
                    return;
                }

                RecordMetadata metadata = result.getRecordMetadata();
                log.info(
                        "Kafka publish succeeded, eventId={}, topic={}, partition={}, offset={}",
                        event.eventId(),
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset());
            });
}
~~~

Ví dụ này log event ID và metadata trả về từ broker. client.id được cấu hình ở cấp KafkaProducer; không cần truyền nó như một trường nghiệp vụ trong mọi message.

Khi gửi thất bại, log nên có event ID, loại exception, topic và thông tin correlation cần thiết. Tránh log payload đầy đủ nếu payload chứa dữ liệu cá nhân hoặc thông tin nhạy cảm.

### Producer metrics

Kafka producer cung cấp các metric hữu ích cho việc điều tra:

| Nhóm metric | Ví dụ | Câu hỏi vận hành |
|---|---|---|
| Tốc độ gửi | record-send-rate, byte-rate | Producer đang gửi bao nhiêu record và byte mỗi giây? |
| Lỗi và retry | record-error-rate, record-retry-rate | Có lỗi cuối cùng hoặc retry tăng bất thường không? |
| Độ trễ request | request-latency-avg, request-latency-max | Broker phản hồi request nhanh hay chậm? |
| Buffer | bufferpool-wait-time-total, buffer-available-bytes | Producer có đang chờ buffer hoặc chịu backpressure không? |
| Batch | batch-size-avg, records-per-request-avg | Producer gom batch có hiệu quả không? |

Khi exporter đưa client ID thành metric tag, hãy lọc hoặc group theo client ID để so sánh các producer. Ví dụ, nếu orders-prod-replay có retry cao nhưng orders-prod-publisher bình thường, vấn đề có thể nằm ở luồng replay, cấu hình riêng hoặc cách luồng này tạo tải.

Metric chính xác và tên metric có thể thay đổi theo Kafka client và exporter. Hãy kiểm tra metric được công bố trong môi trường thực tế trước khi viết dashboard hoặc alert phụ thuộc vào một tên cụ thể.

### Broker log và quota

Broker nhận client ID trong request header. Tùy cấu hình logging, broker log có thể cho thấy client ID đi cùng request hoặc lỗi liên quan. Khi cần giới hạn lưu lượng, Kafka hỗ trợ client quota dựa trên client ID, ví dụ giới hạn producer byte rate.

Ví dụ đặt quota producer cho client ID orders-prod-publisher:

~~~bash
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --alter \
  --add-config 'producer_byte_rate=1048576' \
  --entity-type clients \
  --entity-name orders-prod-publisher
~~~

Lệnh trên minh họa quota tốc độ byte producer cho client ID đã chọn. Đơn vị của producer_byte_rate là byte mỗi giây. Quyền quản trị cấu hình broker và phiên bản Kafka đang chạy có thể ảnh hưởng cách thực hiện; hãy xác nhận cấu hình hiện hành trước khi áp dụng quota production.

Quota theo client ID hữu ích khi cần phân biệt tải giữa các luồng gửi. Tuy nhiên, vì client ID do client khai báo, không dùng quota theo client ID như một cơ chế xác thực. Nếu nhiều producer dùng cùng một ID, chúng có thể cùng khớp một cấu hình quota. Nếu mỗi instance dùng ID khác nhau, cách áp dụng quota sẽ khác so với việc gom tất cả instance dưới một ID chung.

## 8. Phân biệt producer client ID và consumer client ID trong Spring Kafka

Một ứng dụng Spring Kafka có thể vừa gửi vừa nhận record. Producer và consumer là hai Kafka client khác nhau và có thể có client ID khác nhau.

Ví dụ:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        "[client.id]": orders-prod-publisher
    consumer:
      properties:
        "[client.id]": orders-prod-consumer
      group-id: orders-worker
~~~

Ở đây:

- orders-prod-publisher nhận diện producer gửi record.
- orders-prod-consumer nhận diện consumer client đọc record.
- orders-worker là group ID xác định nhóm consumer phối hợp đọc topic.

Spring Kafka cũng có thuộc tính clientIdPrefix trên @KafkaListener để đặt tiền tố client ID cho các consumer do listener container tạo. Khi listener có concurrency, framework có thể thêm hậu tố để phân biệt các consumer instance thuộc container. Thuộc tính đó phục vụ client ID của consumer, không thay thế cấu hình client.id của producer.

Không nên dùng cùng một tên cho producer, consumer và AdminClient nếu mục tiêu là điều tra riêng từng loại client. Dùng hậu tố role giúp log và metric dễ hiểu hơn, ví dụ publisher, consumer và admin.

## 9. Các lỗi thường gặp khi đặt client.id

**Để Kafka tự sinh tên mặc định trong production.** Tên mặc định có thể không cho biết service, môi trường hoặc vai trò. Khi nhiều ứng dụng chạy cùng cluster, việc tìm log và metric sẽ khó hơn.

**Dùng một client ID khác nhau cho từng message.** client.id là định danh của Kafka client, không phải định danh của message. Tạo ID biến thiên theo từng record làm tăng cardinality và khiến dashboard khó sử dụng.

**Dùng client.id làm event ID.** Một producer gửi nhiều event nên các event có thể cùng client ID. Hãy tạo event ID riêng trong payload hoặc header.

**Dùng client.id làm trace ID.** Một producer có thể gửi record từ nhiều trace. Hãy truyền trace context theo từng record nếu cần nối các bước xử lý phân tán.

**Cho rằng client.id xác thực service.** client.id do client tự khai báo. Dùng SASL/TLS và ACL để xác thực, phân quyền.

**Đặt ID giống nhau cho các luồng có mục đích khác nhau.** Nếu replay, publisher chính và publisher audit cần được điều tra riêng, hãy đặt role riêng hoặc bổ sung nhãn phù hợp.

**Thêm pod name vào mọi client ID mà không xét cardinality.** Việc này giúp truy vết từng instance nhưng tạo nhiều nhãn metric ngắn hạn khi workload scale liên tục. Cân nhắc dùng log và resource attributes cho định danh instance.

**Đổi client.id trong cấu hình nhưng kỳ vọng producer đang chạy tự đổi tên.** KafkaProducer giữ cấu hình khi khởi tạo. Cần tạo lại producer để áp dụng giá trị mới.

## 10. Quy trình thiết lập và kiểm tra

Khi triển khai một producer mới, hãy xác định mục tiêu truy vết trước rồi chọn cách đặt tên:

1. Xác định service phát record và môi trường chạy.
2. Xác định vai trò producer, chẳng hạn publisher chính, replay hoặc audit.
3. Chọn client ID ổn định theo service, môi trường và vai trò.
4. Quyết định có cần suffix instance hay không; cân nhắc cardinality của metrics.
5. Cấu hình client ID qua Spring Boot producer properties hoặc ProducerFactory.
6. Khởi tạo producer và kiểm tra log cấu hình để xác nhận client ID được áp dụng.
7. Kiểm tra metric của producer có nhãn client ID tương ứng.
8. Gửi một record thử nghiệm và kiểm tra log broker nếu cần xác minh request header.
9. Nếu dùng client quota, xác nhận entity client ID khớp với tên producer thực tế.
10. Ghi lại quy ước tên để các service và môi trường khác áp dụng nhất quán.

Khi điều tra sự cố, dùng client.id để khoanh vùng producer, sau đó kết hợp event ID, topic, partition, offset và trace ID để lần theo một sự kiện cụ thể. Cách kết hợp này cho biết request đến từ client nào, record nằm ở đâu trong Kafka và nghiệp vụ nào đã tạo ra nó.

## 11. Mẫu quy ước cho hệ thống Spring Kafka

Một quy ước có thể áp dụng cho nhiều service:

~~~text
<service>-<environment>-<role>
~~~

Ví dụ:

| Thành phần | client.id |
|---|---|
| Producer chính của orders | orders-prod-publisher |
| Producer replay của orders | orders-prod-replay |
| Consumer của orders | orders-prod-consumer |
| Producer billing | billing-prod-publisher |
| Admin client của orders | orders-prod-admin |

Nếu cần theo dõi từng instance, thêm hậu tố instance vào client ID của đúng loại client. Duy trì event ID và trace ID riêng ở record header hoặc payload để truy vết từng thông điệp xuyên suốt các service.

client.id có thể truy vết hiệu quả khi tên được đặt có chủ đích, cấu hình được áp dụng nhất quán và log/metric thực sự thu thập nhãn này. Hãy xem nó là định danh vận hành của Kafka client, kết hợp với định danh sự kiện và trace ở đúng phạm vi để điều tra từ producer đến broker và các bước xử lý tiếp theo.
