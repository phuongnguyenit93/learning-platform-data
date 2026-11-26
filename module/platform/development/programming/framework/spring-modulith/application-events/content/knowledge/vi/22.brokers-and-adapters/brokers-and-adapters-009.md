# Khả năng quan sát adapter

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp qua sự kiện nghiệp vụ, còn broker và adapter đưa sự kiện qua ranh giới tiến trình hoặc hệ thống. Khi event không được gửi, listener xử lý chậm hoặc broker gặp sự cố, đội phát triển cần xác định chính xác vấn đề nằm ở module phát, publication registry, adapter, transport hay consumer. Khả năng quan sát adapter (adapter observability) cung cấp dữ liệu để theo dõi luồng giao sự kiện, phát hiện bất thường và điều tra sự cố.

Một adapter có thể gửi event qua Kafka, AMQP hoặc một cơ chế messaging khác. Dù transport khác nhau, cách quan sát nên thống nhất ba tín hiệu: log cho biết điều gì đã xảy ra, metrics cho biết xu hướng và mức độ, trace cho biết một event đi qua những thành phần nào. Các tín hiệu này cần liên kết được với trạng thái publication và thông tin vận hành của broker.

## 1. Quan sát toàn bộ luồng giao sự kiện

Một event có thể đi qua nhiều bước: use case phát event, Event Publication Registry ghi nhận publication, adapter chuyển payload sang định dạng transport, broker nhận message và consumer xử lý. Mỗi bước có thể thành công hoặc thất bại độc lập.

~~~mermaid
flowchart LR
    A["Use case / publisher"] --> B["Application event"]
    B --> C["Publication registry"]
    C --> D["Externalization / messaging adapter"]
    D --> E["Broker"]
    E --> F["Consumer adapter"]
    F --> G["Consumer use case"]
    A -. "logs / metrics / traces" .-> H["Observability"]
    C -. "publication state" .-> H
    D -. "send result / latency" .-> H
    E -. "broker signals" .-> H
    F -. "consume result / lag" .-> H
~~~

Nên phân biệt các mốc trạng thái sau:

- **Event created:** ứng dụng tạo và phát event trong luồng nghiệp vụ.
- **Publication recorded:** registry ghi nhận publication cần được xử lý theo cấu hình.
- **Adapter send attempted:** adapter bắt đầu gửi thông điệp.
- **Broker acknowledged:** transport xác nhận đã nhận message theo mức đảm bảo mà adapter sử dụng.
- **Publication completed:** publication được đánh dấu hoàn tất trong registry theo cơ chế của ứng dụng.
- **Consumer processed:** consumer hoàn thành tác vụ nghiệp vụ của nó.

Các mốc này không đồng nghĩa. Ví dụ, broker acknowledge không chứng minh consumer đã hoàn thành nghiệp vụ. Tương tự, publication completed phản ánh bước publication tương ứng đã hoàn tất theo cơ chế tích hợp; nếu cần biết consumer đã xử lý, phải quan sát phía consumer hoặc dùng acknowledgement event riêng.

## 2. Xây dựng định danh xuyên suốt

Để liên kết log, metric, trace và trạng thái publication, event cần có metadata nhất quán. Tùy hệ thống, có thể dùng các trường:

| Trường | Vai trò |
|---|---|
| eventId | Định danh duy nhất của một event, giữ nguyên qua retry |
| eventType | Tên event ổn định trong contract |
| aggregateId | Đối tượng nghiệp vụ liên quan |
| publicationId | Định danh bản ghi publication nếu registry cung cấp |
| correlationId | Liên kết các event thuộc cùng một quy trình |
| causationId | Chỉ ra event hoặc command dẫn đến event hiện tại |
| traceId / spanId | Liên kết distributed trace |
| destination | Tên logic của topic, queue hoặc exchange |
| attempt | Lần gửi hoặc xử lý hiện tại, nếu ứng dụng theo dõi |

EventId giúp tìm một message cụ thể. CorrelationId giúp tìm toàn bộ quy trình, chẳng hạn từ lúc xác nhận đơn hàng đến khi giữ hàng và gửi thông báo. TraceId và spanId kết nối các bước trong hệ thống tracing.

Không tạo eventId mới cho mỗi lần retry. Nếu lần gửi đầu thất bại và adapter gửi lại cùng event, eventId phải giữ nguyên để log, deduplication và đối soát có thể nhận diện đó là cùng một sự kiện. Có thể dùng attempt hoặc retry counter riêng để phân biệt các lần thử.

Không đưa toàn bộ metadata vào mọi nơi một cách máy móc. Hãy xác định trường nào thuộc payload, trường nào thuộc message header và trường nào chỉ phục vụ telemetry. Trace context có thể được truyền trong header theo chuẩn W3C Trace Context nếu stack hỗ trợ. Adapter cần cấu hình việc inject và extract context; không giả định broker tự truyền trace context xuyên suốt.

## 3. Structured logging cho adapter

Log của adapter nên mô tả các chuyển trạng thái quan trọng và kết quả gửi. Dùng structured logging để mỗi bản ghi có các field có thể truy vấn thay vì ghép mọi thông tin thành một chuỗi văn bản.

Một bản ghi gửi thành công có thể có các field:

~~~json
{
  "level": "INFO",
  "message": "Event sent to broker",
  "eventId": "9a8b6c30-1d75-4f1a-9a20-4f1c4b4d6a11",
  "eventType": "orders.order-confirmed",
  "destination": "orders",
  "adapter": "kafka",
  "attempt": 1,
  "durationMs": 24,
  "outcome": "success",
  "correlationId": "workflow-8271"
}
~~~

Một bản ghi thất bại nên có exception class, mã lỗi transport và thông tin retry nếu có. Không ghi toàn bộ payload vào log theo mặc định; payload có thể chứa thông tin cá nhân, dữ liệu tài chính hoặc bí mật. Nếu cần lưu nội dung để điều tra, dùng kho lưu trữ được kiểm soát quyền truy cập và chính sách retention riêng.

Ví dụ dùng SLF4J:

~~~java
@Slf4j
@Component
class ObservedEventSender {

    private final BrokerClient brokerClient;

    ObservedEventSender(BrokerClient brokerClient) {
        this.brokerClient = brokerClient;
    }

    void send(OutboundEvent event) {
        long startedAt = System.nanoTime();

        try {
            brokerClient.send(event);

            long durationMs =
                (System.nanoTime() - startedAt) / 1_000_000;

            log.info(
                "Event sent: eventId={}, eventType={}, destination={}, durationMs={}",
                event.eventId(),
                event.eventType(),
                event.destination(),
                durationMs
            );
        } catch (RuntimeException exception) {
            log.error(
                "Event send failed: eventId={}, eventType={}, destination={}, errorType={}",
                event.eventId(),
                event.eventType(),
                event.destination(),
                exception.getClass().getSimpleName(),
                exception
            );
            throw exception;
        }
    }
}
~~~

Đây là ví dụ minh họa cho adapter. Trong ứng dụng thực tế, dùng message type và API của broker đang triển khai; không nuốt exception nếu cơ chế publication cần nhận biết lần gửi thất bại để giữ trạng thái incomplete hoặc kích hoạt retry.

Có thể dùng MDC để gắn eventId, correlationId và traceId vào mọi log trong cùng một lần xử lý. Với xử lý bất đồng bộ, MDC không phải lúc nào cũng tự truyền qua executor hoặc thread pool. Cần dùng cơ chế context propagation hoặc TaskDecorator phù hợp, đồng thời xóa context sau khi xử lý để tránh metadata của event trước rò sang event tiếp theo.

## 4. Metrics bằng Micrometer

Metrics giúp trả lời những câu hỏi ở cấp hệ thống: adapter gửi được bao nhiêu event, tỷ lệ lỗi tăng hay giảm, độ trễ thay đổi ra sao và publication tồn đọng có tăng không. Trong Spring Boot, Micrometer tích hợp với Actuator và có thể xuất dữ liệu tới backend quan sát phù hợp.

Các metric quan trọng gồm:

| Metric | Ý nghĩa |
|---|---|
| events.adapter.send.total | Tổng số lần adapter gửi, phân theo kết quả |
| events.adapter.send.duration | Thời gian gửi event |
| events.adapter.send.failures | Số lần gửi thất bại |
| events.adapter.retry.total | Số lần retry |
| events.publication.incomplete | Số publication chưa hoàn tất |
| events.publication.oldest.age | Tuổi của publication chưa hoàn tất lâu nhất |
| events.listener.duration | Thời gian listener xử lý |
| events.listener.failures | Số lần listener thất bại |
| events.consumer.lag | Độ trễ consumer so với dữ liệu broker |
| events.deadletter.total | Số message chuyển sang dead-letter |

Tên metric cụ thể nên tuân theo quy ước của hệ thống. Điều quan trọng là định nghĩa đơn vị, thời điểm ghi nhận và ý nghĩa của từng metric. Ví dụ, send duration nên đo thời gian từ lúc adapter bắt đầu gửi đến khi nhận được kết quả xác nhận của client, không bao gồm thời gian consumer xử lý nếu adapter không chờ consumer.

### Chọn tag có cardinality thấp

Tag giúp phân nhóm metric theo adapter, destination hoặc outcome. Nên dùng các giá trị có tập hữu hạn và ổn định:

- adapter: kafka, amqp hoặc tên adapter nội bộ.
- destination: tên logic đã cấu hình, không phải tên động theo từng event.
- outcome: success, failure hoặc timeout.
- event.type: loại event trong danh mục được kiểm soát.
- consumer.group: nhóm consumer đã định nghĩa trước.

Không dùng eventId, aggregateId, customerId, correlationId, traceId hoặc message payload làm metric tag. Những giá trị này gần như duy nhất cho mỗi event, làm tăng cardinality và có thể khiến hệ thống metrics tốn bộ nhớ hoặc vượt giới hạn chuỗi thời gian. Định danh chi tiết thuộc log và trace.

### Ví dụ đo thời gian gửi

Đoạn code dưới đây minh họa cách ghi counter và timer bằng Micrometer. Các tag là tên adapter, destination logic và outcome:

~~~java
@Component
class AdapterMetrics {

    private final MeterRegistry registry;

    AdapterMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void recordSuccess(
            String adapter,
            String destination,
            long durationNanos) {

        Counter.builder("application.events.adapter.send")
            .tag("adapter", adapter)
            .tag("destination", destination)
            .tag("outcome", "success")
            .register(registry)
            .increment();

        Timer.builder("application.events.adapter.send.duration")
            .tag("adapter", adapter)
            .tag("destination", destination)
            .register(registry)
            .record(durationNanos, TimeUnit.NANOSECONDS);
    }

    void recordFailure(String adapter, String destination) {
        Counter.builder("application.events.adapter.send")
            .tag("adapter", adapter)
            .tag("destination", destination)
            .tag("outcome", "failure")
            .register(registry)
            .increment();
    }
}
~~~

Trong code minh họa, có thể giữ tham chiếu Timer đã đăng ký thay vì đăng ký lại mỗi lần gọi; MeterRegistry cũng quản lý meter theo tên và tag. Hãy chuẩn hóa đơn vị và tên metric trong toàn ứng dụng. Nếu cần đo phân phối độ trễ, cấu hình histogram hoặc percentile phù hợp với backend metrics.

Cần tránh đếm một lần gửi thất bại thành nhiều loại lỗi chồng lấn nếu dashboard dùng các metric đó để tính tỷ lệ. Hãy xác định rõ một attempt là một lần adapter thực sự gọi transport, còn một event có thể có nhiều attempt. Tỷ lệ event cuối cùng thành công khác với tỷ lệ attempt thành công.

## 5. Distributed tracing và Observation

Trace cho biết một event đi qua những thành phần nào và thời gian tiêu tốn ở mỗi bước. Với event bất đồng bộ, trace có thể kết thúc ở producer và được nối tiếp ở consumer thông qua trace context được truyền trong message header.

Micrometer Observation cung cấp API thống nhất để instrument một thao tác. Khi ứng dụng có ObservationRegistry và tracing bridge phù hợp, observation có thể tạo metrics và span theo cấu hình. Ví dụ:

~~~java
void send(OutboundEvent event) {
    Observation.createNotStarted(
            "application.event.externalization",
            observationRegistry)
        .lowCardinalityKeyValue("adapter", adapterName)
        .lowCardinalityKeyValue("destination", event.destination())
        .lowCardinalityKeyValue("event.type", event.eventType())
        .highCardinalityKeyValue("event.id", event.eventId().toString())
        .observe(() -> brokerClient.send(event));
}
~~~

Các low-cardinality key có thể được đưa vào metrics. Event ID là high-cardinality, phù hợp hơn với trace hoặc log và không nên được dùng làm nhãn chuỗi thời gian metrics. Cần cân nhắc chính sách lưu trace và dữ liệu nhạy cảm trước khi đưa metadata vào span.

Với xử lý bất đồng bộ, trace của consumer có thể là continuation hoặc span liên kết (link) với trace producer, tùy mô hình tracing và cách context được truyền. Không nên giả định một trace cha duy nhất luôn tồn tại trong mọi luồng event. Nếu event được phát sinh từ nhiều nguồn hoặc được batch, span link có thể diễn đạt quan hệ chính xác hơn.

Một trace hữu ích có thể thể hiện các span:

1. Xử lý use case và phát event.
2. Ghi publication trong registry.
3. Adapter serialize và gửi message.
4. Broker client nhận xác nhận.
5. Consumer nhận và deserialize message.
6. Listener thực hiện nghiệp vụ và commit transaction.

Không phải mọi hệ thống đều instrument được broker nội bộ hoặc từng bước registry. Khi thiếu span ở một đoạn, dùng eventId, correlationId và timestamp để đối chiếu log giữa các thành phần.

## 6. Quan sát Event Publication Registry

Event Publication Registry cung cấp thông tin về publication được theo dõi trong ứng dụng. Với listener transactional, trạng thái publication cho biết listener đã hoàn tất hay còn incomplete. Đây là tín hiệu quan trọng để phát hiện event bị kẹt sau khi transaction nghiệp vụ đã commit.

Nên theo dõi:

- Số publication incomplete theo listener hoặc loại event.
- Tuổi của publication incomplete lâu nhất.
- Thời gian từ lúc publication được tạo đến lúc hoàn tất.
- Số lần resubmit hoặc retry do ứng dụng thực hiện.
- Số publication tồn đọng sau khi ứng dụng khởi động lại.
- Lỗi cuối cùng hoặc nhóm nguyên nhân nếu ứng dụng có lưu thông tin đó.

Không phải mọi adapter đều cung cấp cùng một mô hình trạng thái. Hãy xác định publication nào được registry quản lý, lúc nào được đánh dấu completed và điều kiện nào khiến nó còn incomplete. Nếu phiên bản Spring Modulith đang dùng cung cấp Actuator endpoint hoặc integration cho publication, có thể bật endpoint theo cấu hình bảo mật phù hợp để hỗ trợ kiểm tra vận hành. Tên endpoint và các field được trả về phụ thuộc phiên bản; không nên dựa vào endpoint chưa được xác nhận trong ứng dụng.

Có thể dùng API quản lý incomplete publications để truy vấn hoặc resubmit theo chính sách ứng dụng. Tuy nhiên, retry là một hành động vận hành, không phải metric. Mỗi lần resubmit cần được ghi nhận để biết ai hoặc tác vụ nào kích hoạt, thời điểm nào, event nào và kết quả ra sao.

Một publication incomplete không nhất thiết có nghĩa broker đã từ chối message. Nó có thể phản ánh listener thất bại, adapter không gửi được, lỗi serialization hoặc process dừng giữa các bước. Cần kết hợp trạng thái registry với log, trace và metric của transport để xác định nguyên nhân.

## 7. Quan sát broker và consumer

Adapter chỉ là một phần của luồng messaging. Để tránh chẩn đoán nhầm, cần theo dõi thêm broker và consumer.

Với broker, các tín hiệu thường hữu ích gồm:

- Số message được publish và số message bị từ chối.
- Throughput theo topic, queue hoặc exchange.
- Số connection, channel và consumer đang hoạt động.
- Queue depth hoặc partition offset.
- Consumer lag và tốc độ bắt kịp.
- Số lần redelivery, retry hoặc dead-letter.
- Thời gian broker xử lý request và tình trạng replication nếu có.

Với consumer, cần theo dõi thời gian deserialize, listener duration, số message thành công/thất bại, số duplicate bị bỏ qua và thời gian từ occurredAt hoặc publishedAt đến khi xử lý xong.

Các số liệu phải được hiểu theo semantics của broker. Queue depth của queue không tương đương consumer lag của log-based broker. Một publish được broker acknowledge cũng không có nghĩa message đã được consumer xử lý. Dashboard nên tách producer, broker và consumer để nhìn rõ điểm nghẽn.

## 8. Health check, readiness và cảnh báo

Health check giúp biết ứng dụng có thể phục vụ hay không, nhưng một trạng thái UP đơn lẻ không chứng minh event pipeline đang khỏe. Ứng dụng có thể nhận HTTP request bình thường trong khi publication backlog tăng nhanh hoặc broker mất kết nối.

Nên phân biệt:

- **Liveness:** process còn hoạt động và không rơi vào trạng thái cần khởi động lại.
- **Readiness:** ứng dụng có đủ điều kiện nhận traffic theo chính sách triển khai.
- **Dependency health:** trạng thái kết nối broker hoặc adapter.
- **Pipeline health:** backlog, tuổi publication incomplete, consumer lag và tỷ lệ lỗi.

Không nên làm liveness fail chỉ vì broker gián đoạn tạm thời; điều đó có thể gây restart hàng loạt và làm tăng áp lực khi broker phục hồi. Readiness có thể phản ánh dependency nếu ứng dụng thực sự không thể phục vụ nghiệp vụ khi broker không khả dụng. Quyết định cần dựa trên yêu cầu của use case và cơ chế lưu publication bền vững.

Cảnh báo nên dựa vào xu hướng và SLO thay vì một lỗi đơn lẻ:

| Cảnh báo | Tín hiệu gợi ý | Hành động điều tra |
|---|---|---|
| Adapter send failure tăng | Tỷ lệ attempt lỗi vượt ngưỡng trong cửa sổ thời gian | Kiểm tra kết nối, auth, serializer và broker response |
| Publication backlog tăng | Incomplete count tăng liên tục | Phân nhóm listener, kiểm tra lỗi và retry |
| Publication quá cũ | Tuổi publication lớn nhất vượt thời hạn xử lý | Tìm event đầu tiên bị kẹt và lần deploy liên quan |
| Consumer lag tăng | Lag tăng dù producer throughput ổn định | Kiểm tra consumer capacity, lỗi listener và partition |
| Dead-letter tăng | Số message bị đưa vào DLQ tăng | Phân tích schema, poison message và dependency |
| Latency tăng | p95/p99 send hoặc processing duration tăng | Tách thời gian serialize, network, broker và listener |

Ngưỡng cụ thể phụ thuộc lưu lượng, yêu cầu nghiệp vụ và SLO. Ví dụ, luồng xác nhận thanh toán có thể cần cảnh báo sớm hơn luồng gửi email thông báo. Mỗi cảnh báo nên có owner, dashboard và hướng xử lý để tránh tạo cảnh báo không có hành động.

## 9. Dashboard vận hành adapter

Một dashboard nên giúp người vận hành trả lời nhanh bốn câu hỏi: event có được tạo không, adapter có gửi được không, broker có nhận không và consumer có xử lý không.

Có thể tổ chức dashboard thành các vùng:

**Tổng quan pipeline:** throughput event, tỷ lệ thành công, số publication incomplete, queue depth hoặc consumer lag và độ trễ end-to-end.

**Adapter:** send attempts, success/failure, timeout, serialization error, retry count, p50/p95/p99 send duration và trạng thái connection.

**Publication registry:** incomplete count theo listener, tuổi publication lâu nhất, publication hoàn tất theo thời gian và số resubmit.

**Consumer:** receive throughput, deserialize failure, listener duration, duplicate count, retry và dead-letter.

**Phân tích sự cố:** event type, destination, adapter, exception class, correlation ID và trace link. Các bộ lọc phải có giới hạn để tránh dashboard tạo truy vấn tốn kém hoặc truy xuất payload nhạy cảm.

Nên có liên kết từ biểu đồ tỷ lệ lỗi tới log và trace tương ứng. Một metric cho biết tỷ lệ lỗi đang tăng; log cho biết event nào gặp lỗi; trace cho biết thời gian bị tiêu tốn ở bước nào. Ba tín hiệu bổ trợ nhau.

## 10. Runbook khi adapter gặp sự cố

Khi phát hiện event không được giao, điều tra theo thứ tự từ publisher đến consumer. Mục tiêu là xác định điểm cuối cùng đã hoàn thành và bước đầu tiên thất bại.

1. Tìm event bằng eventId hoặc correlationId trong log và trace.
2. Kiểm tra transaction nghiệp vụ đã commit và publication đã được registry ghi nhận chưa.
3. Kiểm tra adapter có bắt đầu send không; xem lỗi serialize, timeout, authentication hoặc routing.
4. Kiểm tra broker có nhận message và trả acknowledgement không.
5. Kiểm tra queue depth, partition offset, consumer lag và trạng thái consumer.
6. Kiểm tra consumer có deserialize được payload và listener có commit nghiệp vụ không.
7. Xác định lỗi tạm thời hay lỗi dữ liệu cố định trước khi retry hoặc chuyển dead-letter.

Một số tình huống thường gặp:

- **Không có log adapter:** event có thể chưa được publish, publication chưa tới adapter hoặc instrumentation chưa bao phủ đường đi đó.
- **Có log send attempt nhưng không có acknowledgement:** kiểm tra network, timeout, broker availability và client configuration.
- **Có acknowledgement nhưng consumer lag tăng:** kiểm tra subscription, consumer group, capacity và lỗi xử lý.
- **Publication incomplete kéo dài:** kiểm tra listener/adapter tương ứng, exception gần nhất và trạng thái resubmit.
- **Serialization failure:** kiểm tra event type, custom serializer, Java Time module, circular reference và schema compatibility.
- **Duplicate delivery:** kiểm tra retry semantics và idempotency key ở consumer.
- **Dead-letter tăng:** nhóm lỗi theo event type và schema version, sau đó quyết định sửa dữ liệu, sửa contract hay replay có kiểm soát.

Không xóa publication hoặc message lỗi chỉ để giảm số liệu dashboard. Trước khi replay, cần xác nhận tác dụng phụ có idempotent, event còn hợp lệ và consumer đã sẵn sàng. Mọi thao tác thủ công nên lưu người thực hiện, lý do, phạm vi event và kết quả.

## 11. Bảo mật và chất lượng telemetry

Observability cũng là một đường dữ liệu. Log, metric label, trace attribute và dashboard có thể làm lộ thông tin nếu đưa payload hoặc định danh nhạy cảm vào đó.

Áp dụng các nguyên tắc:

- Không ghi toàn bộ event payload vào log theo mặc định.
- Không đưa token, credential, thông tin thanh toán hoặc dữ liệu cá nhân vào span.
- Dùng logical destination thay vì địa chỉ broker chứa thông tin hạ tầng nhạy cảm.
- Không dùng customerId, email, aggregateId hoặc eventId làm metric tag.
- Giới hạn quyền xem log, trace, dashboard và endpoint quản trị publication.
- Đặt retention theo nhu cầu vận hành và chính sách dữ liệu.
- Làm sạch hoặc mask dữ liệu khi cần ghi chẩn đoán payload.
- Ghi audit cho hành động resubmit, replay hoặc purge publication.

Không tăng mức log toàn hệ thống lên DEBUG trong thời gian dài để điều tra một adapter. Nếu cần log chi tiết, giới hạn logger hoặc thời gian bật, rồi trả về cấu hình bình thường sau khi sự cố kết thúc.

## 12. Kiểm thử observability

Một adapter có thể gửi message đúng nhưng không có telemetry hữu ích; ngược lại, metric có thể ghi thành công dù message chưa được broker nhận. Vì vậy, kiểm thử observability cần xác minh tín hiệu phản ánh đúng mốc nghiệp vụ.

Các kịch bản nên có:

1. **Send success:** counter success tăng, timer ghi thời gian gửi và log có eventId.
2. **Send failure:** counter failure tăng, exception được ghi và lỗi được truyền về cơ chế publication.
3. **Retry:** mỗi attempt được đếm đúng; eventId không đổi và attempt number tăng theo chính sách.
4. **Publication incomplete:** registry phản ánh publication chưa hoàn tất khi listener hoặc adapter thất bại.
5. **Publication completion:** trạng thái hoàn tất chỉ được ghi khi điều kiện hoàn tất thực tế thỏa mãn.
6. **Trace propagation:** trace context được truyền qua message header và consumer có thể liên kết với producer.
7. **Async context:** MDC hoặc tracing context không bị mất hay rò sang event khác khi chạy trên thread pool.
8. **Cardinality:** metric không tạo tag mới theo eventId, aggregateId hoặc customerId.
9. **Sensitive data:** log và trace không chứa payload hoặc credential ngoài chính sách.
10. **Alert behavior:** cảnh báo phát khi backlog hoặc latency vượt ngưỡng và được giải quyết khi pipeline phục hồi.

Test có thể dùng MeterRegistry test, ObservationRegistry test hoặc log appender phù hợp với stack. Với broker thật hoặc container tích hợp, cần kiểm tra cả acknowledgement, redelivery và consumer lag theo đúng semantics của transport. Không chỉ mock send method rồi kết luận toàn pipeline đã được quan sát đầy đủ.

## 13. Lộ trình triển khai

Khi bổ sung khả năng quan sát cho một adapter, thực hiện theo thứ tự:

1. Vẽ các mốc event từ publisher đến consumer và thống nhất ý nghĩa từng trạng thái.
2. Chuẩn hóa eventId, eventType, correlationId, trace context và logical destination.
3. Bổ sung structured logs ở các điểm send, acknowledge, retry và failure.
4. Đo counter, timer và backlog bằng Micrometer với tag cardinality thấp.
5. Instrument adapter bằng Observation hoặc tracing API phù hợp.
6. Kết nối metric với trạng thái publication registry, broker và consumer.
7. Xây dashboard, SLO và cảnh báo có owner cùng runbook.
8. Kiểm thử success, failure, retry, async context, trace propagation và dữ liệu nhạy cảm.
9. Đánh giá chi phí telemetry, retention và quyền truy cập trước khi triển khai rộng.

Khả năng quan sát adapter có giá trị khi người vận hành nối được một event cụ thể với trạng thái publication, lần gửi qua broker và kết quả ở consumer. Structured logs cung cấp chi tiết, metrics cho biết xu hướng, traces thể hiện đường đi và broker/consumer signals chỉ ra điểm nghẽn. Khi các tín hiệu có định danh thống nhất, semantics rõ ràng và cardinality được kiểm soát, hệ thống application events có thể được vận hành và khôi phục với độ tin cậy cao hơn.

