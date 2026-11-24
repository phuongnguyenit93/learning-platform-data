# Liveness, readiness và ảnh hưởng của lỗi broker

Khi triển khai ứng dụng Spring Cloud Stream lên Kubernetes, nhiều nhóm đặt một endpoint kiểm tra sức khỏe rồi dùng cùng endpoint đó cho cả liveness và readiness. Cách làm này dễ gây sự cố: nếu Kafka, RabbitMQ hoặc Pulsar tạm mất kết nối, toàn bộ Pod có thể bị khởi động lại dù ứng dụng vẫn hoạt động bình thường và đang tự reconnect. Ngược lại, một endpoint chỉ trả HTTP 200 cũng chưa chứng minh consumer đang nhận message hoặc producer đã ghi thành công.

Để thiết kế probe đúng, cần phân biệt **sức sống của tiến trình**, **khả năng nhận traffic**, **khả năng giao tiếp broker** và **tiến triển của luồng sự kiện**. Spring Boot Actuator hỗ trợ liveness/readiness dựa trên ApplicationAvailability, còn Spring Cloud Stream cung cấp health indicator theo từng binder. Kubernetes có cơ chế startup, liveness và readiness probe với tác động rất khác nhau. Bài này trình bày cách kết hợp chúng mà không tạo vòng lặp restart, không che giấu lỗi messaging và không làm mất khả năng phục hồi của consumer.

## 1. Bốn câu hỏi sức khỏe khác nhau

Trước khi viết probe, hãy xác định câu hỏi mà phép kiểm tra cần trả lời.

| Câu hỏi | Tín hiệu phù hợp | Khi thất bại |
|---|---|---|
| Tiến trình còn có khả năng tự phục hồi không? | Liveness | Kubernetes có thể restart container |
| Instance đã sẵn sàng phục vụ traffic được định tuyến vào nó chưa? | Readiness | Kubernetes bỏ Pod khỏi tập endpoint nhận traffic của Service |
| Binder có thể kết nối và làm việc với broker không? | Binder/connection health và telemetry | Cảnh báo, điều tra, có thể ảnh hưởng readiness tùy nghiệp vụ |
| Luồng sự kiện có tiến triển đúng không? | Lag, throughput, lỗi publish, ack, retry, DLQ, trạng thái binding | Điều tra khả năng xử lý; không nhất thiết restart |

**Liveness** là tín hiệu nội tại: ứng dụng còn khả năng tiến triển hoặc tự hồi phục không? **Readiness** là hợp đồng nhận traffic: instance có nên tiếp nhận yêu cầu được router đưa tới không? **Broker health** cho biết một phụ thuộc ngoài đang sẵn sàng ở mức nào. **Flow health** đòi hỏi kiểm tra dữ liệu thực sự dịch chuyển theo đúng kỳ vọng.

Một broker mất kết nối không tự động khiến JVM bị deadlock. Cũng không có nghĩa chỉ cần broker trả lời ping thì pipeline đã xử lý thành công. Cần quản lý riêng các tầng tín hiệu này.

## 2. Startup, liveness và readiness probe của Kubernetes

Kubernetes hỗ trợ ba loại probe:

- **Startup probe**: kiểm tra ứng dụng hoàn tất giai đoạn khởi tạo; khi startup probe chưa thành công, Kubernetes chưa chạy liveness/readiness probe.
- **Liveness probe**: khi thất bại đủ số lần, kubelet restart container theo restart policy.
- **Readiness probe**: khi thất bại, Pod bị đánh dấu NotReady và không được chọn làm endpoint nhận traffic qua Kubernetes Service; kubelet tiếp tục kiểm tra, không restart chỉ vì readiness thất bại.

Startup probe chỉ chạy trong giai đoạn khởi động. Liveness và readiness được kiểm tra định kỳ trong vòng đời container.

Ví dụ quyết định xử lý:

~~~mermaid
flowchart TD
    A[Pod đang chạy] --> B{Startup hoàn tất?}
    B -->|Chưa| C[Tiếp tục startup probe trong giới hạn]
    B -->|Rồi| D{Liveness thành công?}
    D -->|Không, vượt ngưỡng| E[Restart container]
    D -->|Có| F{Readiness thành công?}
    F -->|Có| G[Pod có thể nhận Service traffic]
    F -->|Không| H[Pod NotReady, vẫn chạy và được kiểm tra lại]
    C --> B
    H --> F
~~~

Khác biệt vận hành rất lớn: liveness thất bại có thể xóa trạng thái tạm của process và khiến consumer group rebalance; readiness thất bại chủ yếu ảnh hưởng tuyến traffic Kubernetes Service. Hãy chọn phép kiểm tra theo hành động cần thực hiện khi nó thất bại.

## 3. Vì sao không đưa broker trực tiếp vào liveness?

Giả sử một Kafka cluster ngừng đáp ứng trong ba phút. Cả mười instance Spring Cloud Stream đều dùng Kafka Binder và endpoint liveness kiểm tra broker. Các probe lần lượt thất bại và Kubernetes restart tất cả instance.

Hệ quả có thể gồm:

1. Mọi instance mất trạng thái trong bộ nhớ và đóng connection.
2. Consumer group rebalance lặp lại khi Pod restart.
3. Message chưa được xác nhận có thể được giao lại.
4. Các Pod cùng cố kết nối hoặc khai báo topic khi broker chưa khôi phục.
5. Khi broker hoạt động trở lại, nhiều Pod tạo reconnect storm cùng lúc.
6. Service downstream nhận duplicate hoặc độ trễ phục hồi tăng.

Restart ứng dụng không sửa được broker đang lỗi. Spring Boot chính thức khuyến nghị **liveness không phụ thuộc dịch vụ ngoài**, vì như vậy có thể gây cascading failure khi một dependency chung của mọi instance gặp sự cố.

Liveness phù hợp với các dấu hiệu khó tự hồi phục như tiến trình không còn phản hồi, trạng thái ứng dụng bị hỏng nghiêm trọng hoặc một lỗi nội tại khiến worker không thể tiến triển sau khi đã thử biện pháp phục hồi. Không nên đưa Kafka metadata check, Rabbit connection check, Pulsar broker query hoặc database query vào mỗi lần gọi liveness.

Nếu JVM còn chạy nhưng stream thread chết và không thể tự khôi phục, cần xác định rõ chính sách xử lý: thay thread, dừng process có kiểm soát, hoặc phát tín hiệu liveness thất bại. Quyết định đó cần dựa trên trạng thái không thể phục hồi đã được xác nhận, thay vì một lỗi network thoáng qua.

## 4. Readiness có luôn phải phụ thuộc broker không?

Không. Điều này phụ thuộc ứng dụng đang nhận loại traffic nào.

**Trường hợp A: HTTP API nhận request rồi publish message.** Nếu API chỉ trả thành công sau khi đã ghi bền vững vào Kafka, broker mất kết nối có thể khiến API không còn đáp ứng hợp đồng. Readiness có thể cần phản ánh khả năng publish hoặc trạng thái outbox. Nếu API ghi request vào transactional outbox bền vững, nó có thể tiếp tục nhận traffic dù broker tạm ngừng.

**Trường hợp B: Consumer chỉ nhận message trực tiếp từ Kafka/RabbitMQ/Pulsar.** Pod có thể không có Kubernetes Service, hoặc Service chỉ dùng cho metrics. Readiness thất bại **không** tự dừng consumer của binder: broker vẫn có thể kết nối và giao message vì nó không dùng Kubernetes Service endpoint để phân phối. Trong tình huống này, readiness phản ánh tình trạng HTTP/Pod, còn khả năng tiêu thụ cần được quan sát qua binder state, lag, subscription và metrics.

**Trường hợp C: Ứng dụng bridge vừa nhận HTTP vừa tiêu thụ broker.** Có thể cần readiness cho HTTP độc lập với khả năng consumer hoạt động. Đánh dấu NotReady toàn bộ chỉ vì một broker không thiết yếu có thể làm gián đoạn chức năng HTTP vẫn còn khả dụng.

Readiness không phải công tắc pause của Kafka, RabbitMQ hoặc Pulsar consumer. Nếu thật sự cần ngừng nhận message, phải dùng lifecycle API của binding, cấu hình container hoặc cơ chế quản trị broker phù hợp.

## 5. Spring Boot ApplicationAvailability

Spring Boot công bố trạng thái sẵn sàng của ứng dụng qua **ApplicationAvailability**. Có hai nhóm trạng thái quan trọng:

| Nhóm | Trạng thái | Ý nghĩa |
|---|---|---|
| LivenessState | CORRECT | Ứng dụng được xem là hoạt động bình thường |
| LivenessState | BROKEN | Ứng dụng bị hỏng ở mức cần can thiệp |
| ReadinessState | ACCEPTING_TRAFFIC | Có thể phục vụ traffic theo hợp đồng |
| ReadinessState | REFUSING_TRAFFIC | Chưa/không nên nhận traffic mới |

Trong giai đoạn startup, ứng dụng thường ở trạng thái chưa chấp nhận traffic. Khi hoàn tất khởi tạo, Spring Boot phát sự kiện để chuyển readiness sang ACCEPTING_TRAFFIC. Khi shutdown, readiness được chuyển sang REFUSING_TRAFFIC.

Spring Boot Actuator cung cấp:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Hai endpoint liveness/readiness là **health groups**. Chúng sử dụng **LivenessStateHealthIndicator** và **ReadinessStateHealthIndicator**, thay vì mặc định kiểm tra mọi dependency của ứng dụng.

Ở môi trường Kubernetes, Spring Boot có thể tự nhận diện và bật probe support. Nếu muốn bật tường minh, dùng thuộc tính **management.endpoint.health.probes.enabled=true**. Không giả định endpoint đã sẵn có khi ứng dụng không có Actuator hoặc không có web stack để phục vụ HTTP.

## 6. Bật Actuator và endpoint cho deployment

Ứng dụng cần Actuator dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Nếu ứng dụng chỉ là background consumer và chưa có HTTP server, cần thêm web starter phù hợp với dòng Spring Boot đang dùng (Spring MVC hoặc WebFlux) khi muốn Kubernetes gọi HTTP probe. Có thể thay bằng probe dạng exec, nhưng HTTP health group thường đơn giản hơn để chuẩn hóa vận hành.

Cấu hình baseline:

~~~yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: "readinessState"
      show-details: when-authorized
~~~

Khi dùng **add-additional-paths=true**, Spring Boot cung cấp thêm:

~~~text
GET /livez
GET /readyz
~~~

trên **main application server port**. Cấu hình này hữu ích khi Actuator dùng management port riêng: kiểm tra duy nhất management port có thể thành công trong khi main server không tiếp nhận connection được.

Nếu không cần path bổ sung, có thể dùng trực tiếp **/actuator/health/liveness** và **/actuator/health/readiness** trên port Actuator. Đảm bảo path, port và context path thực tế nhất quán với cấu hình của Pod.

Thuộc tính **show-details: when-authorized** giúp tránh công khai toàn bộ metadata health cho người không có quyền. Probe cần mã trạng thái HTTP, không cần payload chứa topic, broker, credential hoặc chi tiết nội bộ.

## 7. Ví dụ Kubernetes Deployment với ba probe

Đây là ví dụ cho ứng dụng có main HTTP port 8080 và Spring Boot đã bật /livez, /readyz:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-stream
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-stream
  template:
    metadata:
      labels:
        app: order-stream
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example/order-stream:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 60
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 2
~~~

Đây là giá trị minh họa, không phải bộ ngưỡng áp dụng cho mọi workload:

- Startup probe cho phép tối đa khoảng 300 giây để khởi động (60 × 5 giây). Hãy đo thực tế thời gian khởi tạo và Kafka Streams state-store restoration.
- Liveness chịu tối đa ba lần kiểm tra thất bại liên tiếp, tránh restart sau một lần HTTP timeout ngẫu nhiên.
- Readiness dùng hai lần thành công liên tiếp để giảm hiện tượng Pod nhấp nháy Ready/NotReady khi hệ thống vừa phục hồi.
- Termination grace period cần đủ cho HTTP request và message handler đang xử lý, nhưng không được kéo dài vô hạn.

**Startup probe không thay thế readiness.** Startup bảo vệ quá trình khởi tạo; readiness quyết định traffic trong toàn bộ thời gian chạy. **Readiness không thay thế liveness** vì Kubernetes sẽ không tự restart chỉ do readiness trả lỗi.

## 8. HTTP status và thông tin trả về

Spring Boot Actuator ánh xạ các Health status thông dụng thành HTTP status:

| Actuator status | HTTP status mặc định | Ý nghĩa với HTTP probe |
|---|---|---|
| UP | 200 | Probe thành công |
| DOWN | 503 | Probe thất bại |
| OUT_OF_SERVICE | 503 | Probe thất bại |
| UNKNOWN | 200 nếu chưa cấu hình mapping riêng | Không nên coi UNKNOWN là chứng minh broker khỏe |

Ví dụ khi readinessState là REFUSING_TRAFFIC:

~~~json
{
  "status": "OUT_OF_SERVICE"
}
~~~

Readiness HTTP probe nhận 503 và Pod trở thành NotReady sau khi vượt failure threshold. Khi readiness trở lại ACCEPTING_TRAFFIC, health group thường báo UP/200 nếu không có health indicator nào khác trong nhóm thất bại.

Không kiểm tra nội dung chuỗi JSON để tự quyết định restart khi kubelet đã có cơ chế dựa trên HTTP response code. Nếu tự thêm Health status hoặc HTTP mapping, phải giữ mapping cho DOWN và OUT_OF_SERVICE để tránh biến lỗi thành HTTP 200 ngoài ý muốn.

## 9. Spring Cloud Stream Binder Health Indicator

Spring Cloud Stream đăng ký health contributor cho các binder dưới tên **binders**. Có thể bật/tắt bằng **management.health.binders.enabled**; nếu không khai báo, hành vi phụ thuộc vào cấu hình health defaults và phiên bản framework.

Ví dụ cấu hình để quan sát sức khỏe binder qua Actuator:

~~~yaml
management:
  health:
    binders:
      enabled: true
  endpoint:
    health:
      show-details: when-authorized
~~~

Sau khi cấp quyền phù hợp, endpoint **/actuator/health** có thể trả trạng thái và chi tiết của binders. Không giả định rằng chỉ cần Health status UP là tất cả message đã được xử lý; binder health thường kiểm tra trạng thái kết nối/metadata hoặc thread, không kiểm tra business side effects.

Một số binder có health indicator riêng; không phải mọi implementation đều cung cấp cùng mức chi tiết. Với nhiều binder, contributor tổng hợp có thể trả DOWN khi một binder lỗi, ngay cả khi các binding khác vẫn hoạt động. Trước khi đưa binders vào readiness, cần hiểu ứng dụng đang sử dụng những binder nào và trạng thái của từng binder có thực sự thiết yếu cho traffic cần nhận hay không.

### Không nhầm lẫn global health với readiness

Ba endpoint có thể khác nhau trong cùng thời điểm:

~~~text
/actuator/health            -> DOWN (một binder mất kết nối)
/actuator/health/liveness   -> UP
/actuator/health/readiness  -> UP (nếu chỉ có readinessState)
~~~

Đây có thể là kết quả đúng: tiến trình vẫn hoạt động, consumer đang tự reconnect, nhưng binder đã cảnh báo broker mất kết nối. Nếu nghiệp vụ yêu cầu không nhận HTTP traffic khi binder down, cần khai báo thêm health indicator trong nhóm readiness một cách chủ động.

## 10. Kafka Binder Health Indicator

Kafka Binder kiểm tra tình trạng broker/topic metadata. Các thuộc tính hữu ích:

| Thuộc tính | Tác dụng |
|---|---|
| spring.cloud.stream.kafka.binder.healthTimeout | Thời gian tối đa chờ lấy thông tin partition; hết hạn có thể báo DOWN |
| spring.cloud.stream.kafka.binder.considerDownWhenAnyPartitionHasNoLeader | Xem binder DOWN nếu phát hiện partition của topic liên quan không có leader |
| spring.cloud.stream.kafka.binder.healthIndicatorConsumerGroup | Group ID của metadata consumer dùng cho health indicator ở phiên bản hỗ trợ |

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          healthTimeout: 15
          considerDownWhenAnyPartitionHasNoLeader: true

management:
  health:
    binders:
      enabled: true
~~~

**healthTimeout tính bằng giây**, không phải mili giây. Ví dụ 15 giây minh họa timeout metadata; giá trị quá lớn có thể làm HTTP health check chậm hơn timeoutSeconds của Kubernetes probe. Giá trị quá nhỏ có thể gây false negative khi Kafka cluster đang bầu leader hoặc mạng biến động.

Thuộc tính **considerDownWhenAnyPartitionHasNoLeader** xét tình trạng leader của partition trong topic; đây không phải bộ đo consumer lag hay độ trễ xử lý. Một consumer có thể còn kết nối broker nhưng lag tăng vì downstream quá chậm. Ngược lại, một thay đổi leader ngắn có thể khiến health tạm thời DOWN nhưng client tự phục hồi.

Không dùng mọi lỗi metadata Kafka làm liveness failure. Giám sát metadata/leader state song song với request timeout, consumer lag, commit failures và retry exhaustion.

## 11. Kafka Streams Binder và trạng thái stream thread

Kafka Streams Binder cung cấp health indicator liên quan đến các stream thread và task. Chi tiết có thể gồm thread name, thread state, active tasks, standby tasks và application ID khi có nhiều topology.

Các trạng thái thường thấy:

- CREATED: thread mới được tạo.
- RUNNING: thread đang hoạt động.
- PARTITIONS_REVOKED và PARTITIONS_ASSIGNED: đang chuyển giao partition/task.
- PENDING_SHUTDOWN: thread đang kết thúc.
- DEAD: thread đã dừng.

Tài liệu Kafka Streams Binder cho biết indicator báo UP khi các thread được đăng ký ở trạng thái RUNNING. Trong quá trình startup hoặc rebalance, thread có thể tạm ở trạng thái khác. Vì vậy, nếu đưa trạng thái này trực tiếp vào readiness, Pod có thể nhấp nháy NotReady/Ready trong thời gian rebalancing; nếu đưa vào liveness, Kubernetes có thể restart đúng lúc Kafka Streams đang tái phân phối task.

Kafka Streams còn có **state restoration**: khi Pod mới nhận task, nó có thể phải khôi phục state store từ changelog trước khi xử lý bình thường. Startup/readiness timeout cần được chọn dựa trên thời gian phục hồi thực tế của state store. Không đặt liveness failureThreshold quá thấp rồi khiến ứng dụng liên tục restart trước khi state restore hoàn thành.

Đối với topology stateful, quan sát thêm restore duration, changelog lag, task rebalance count, processing error, commit latency và throughput. Thread RUNNING là cần thiết nhưng chưa đủ để chứng minh kết quả aggregation đúng.

## 12. RabbitMQ Binder Health Indicator

RabbitMQ Binder sử dụng health indicator do Spring Boot hỗ trợ thông qua Spring AMQP. Có hai phạm vi cấu hình thường gặp:

~~~yaml
management:
  health:
    binders:
      enabled: true
    rabbit:
      enabled: true
~~~

- **management.health.binders.enabled** kiểm soát health indicator ở lớp binder.
- **management.health.rabbit.enabled** kiểm soát Rabbit health indicator của Spring Boot.
- Trong multi-binder environment, một binder có application context riêng và cần property tương ứng nếu muốn tắt riêng indicator của binder đó.

Rabbit health có thể báo DOWN khi không thể kết nối hoặc kiểm tra broker. Tuy nhiên, một Rabbit connection hoạt động không chứng minh producer đã route vào đúng queue hoặc consumer đã acknowledge dữ liệu. Các lỗi routing key, queue binding, ACL, DLQ và publish confirm cần telemetry hoặc test riêng.

Khi RabbitMQ restart, listener container và connection factory thường có cơ chế reconnect. Các delivery chưa ack có thể được requeue. Restart Pod do liveness gắn với broker sẽ làm tăng nguy cơ redelivery và tạo áp lực phục hồi không cần thiết.

Nếu RabbitMQ là nguồn duy nhất của một background consumer, readiness của Kubernetes Service thường không dừng việc broker giao message. Hãy đo consumer count, ready/unacked messages, redelivered rate, queue depth và DLQ depth để đánh giá đường xử lý.

## 13. Pulsar Binder và health của client/subscription

Pulsar Binder dựa trên Spring for Apache Pulsar và sử dụng producer/consumer client do framework quản lý. Tính năng health indicator cụ thể phụ thuộc phiên bản Spring Boot, Spring Pulsar và binder được chọn. Không giả định luôn có contributor tên **pulsar** hoặc contributor đó cung cấp cùng semantics như Kafka Binder.

Những tín hiệu quan trọng với Pulsar:

- Client có thể kết nối broker theo service URL đã cấu hình.
- Producer publish và nhận acknowledgement thành công.
- Consumer subscription được tạo và nhận message.
- Unacked messages, redelivery count và subscription backlog.
- Subscription type như Shared, Failover hoặc Key_Shared và hành vi takeover.
- Retry letter topic và dead-letter topic nếu ứng dụng sử dụng.
- Thời gian reconnect và authentication/TLS failures.

Nếu cần health theo Pulsar, hãy kiểm tra contributor thực sự tồn tại trong runtime bằng Actuator, sau đó định nghĩa readiness policy theo chức năng ứng dụng. Với luồng chỉ xử lý message, metrics về subscription/backlog và cơ chế tự reconnect thường có ích hơn một liveness check phụ thuộc broker.

## 14. Cấu hình readiness theo mức phụ thuộc thực tế

Spring Boot mặc định không tự đưa mọi health indicator ngoài vào readiness. Có thể chủ động mở rộng nhóm readiness:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: "readinessState,binders"
~~~

Cấu hình này **chỉ phù hợp khi mọi binder trong contributor đều là dependency bắt buộc của traffic mà Pod nhận**. Nếu chỉ một binder tùy chọn bị lỗi, toàn Pod có thể bị loại khỏi Service dù vẫn còn đáp ứng được chức năng khác.

Trong nhiều ứng dụng, nên dùng readiness mặc định chỉ gồm readinessState và tạo dashboard/alert riêng cho binders. Nếu bắt buộc phản ánh broker ở readiness của HTTP API, hãy thêm indicator chuyên biệt và có timeout ngắn, cache kết quả hoặc cập nhật bất đồng bộ. Đừng để mỗi HTTP probe gọi trực tiếp metadata broker với thời gian chờ dài, vì chính health endpoint có thể bị nghẽn.

Một ví dụ đơn giản về custom indicator không thực hiện network I/O mỗi lần kubelet hỏi:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("bridgeOutputReady")
public class BridgeOutputReadyHealthIndicator implements HealthIndicator {

    private final AtomicBoolean canAccept = new AtomicBoolean(false);

    public void markUnavailable() {
        canAccept.set(false);
    }

    public void markRecovered() {
        canAccept.set(true);
    }

    @Override
    public Health health() {
        return canAccept.get()
            ? Health.up().build()
            : Health.outOfService().build();
    }
}
~~~

Đây là indicator minh họa, **không tự động theo dõi broker**. Ban đầu nó trả OUT_OF_SERVICE; ứng dụng cần gọi markRecovered sau khi xác minh đường ghi thật sự sẵn sàng và markUnavailable khi khả năng đó bị mất. Các lời gọi phải đến từ thành phần quan sát trạng thái publish/connection hoặc state machine đã kiểm thử. Một TCP connect thành công chưa chắc bảo đảm publish.

Ví dụ import Health/HealthIndicator theo **Spring Boot 4.x**. Với **Spring Boot 3.x**, hai class này thuộc package org.springframework.boot.actuate.health. Chọn đúng import theo dependency thực tế của dự án.

Kích hoạt cho HTTP readiness nếu chức năng bridge output là bắt buộc:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: "readinessState,bridgeOutputReady"
~~~

Không đưa bridgeOutputReady vào liveness. Không bật cơ chế này chỉ để phản ánh mọi lần retry thất bại trong consumer, vì consumer có thể tự retry trong khi Pod vẫn cần giữ state và tiếp tục xử lý.

## 15. Cập nhật ReadinessState bằng sự kiện ứng dụng

Spring Boot hỗ trợ **AvailabilityChangeEvent** để cập nhật readiness theo trạng thái nghiệp vụ. Ví dụ:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class TrafficReadinessControl {

    private final ApplicationEventPublisher publisher;

    public TrafficReadinessControl(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void refuseNewTraffic() {
        AvailabilityChangeEvent.publish(
            publisher,
            this,
            ReadinessState.REFUSING_TRAFFIC
        );
    }

    public void acceptNewTraffic() {
        AvailabilityChangeEvent.publish(
            publisher,
            this,
            ReadinessState.ACCEPTING_TRAFFIC
        );
    }
}
~~~

Lớp này chỉ phát sự kiện; trạng thái được chuyển khi service gọi method tại một mốc có ý nghĩa. Ví dụ, API gateway nội bộ có thể từ chối traffic mới trong lúc nguồn dữ liệu quan trọng đang khôi phục. Không nên gọi refuseNewTraffic khi gặp mọi transient exception.

ReadinessState ảnh hưởng nhóm readiness của Actuator. Nó không tự pause binding hoặc dừng consumer thread. Nếu ứng dụng cần ngừng tiêu thụ, phải điều khiển binding/container bằng cơ chế riêng.

## 16. Binding lifecycle và readiness là hai việc khác nhau

Spring Cloud Stream có **BindingsLifecycleController** để quản lý vòng đời binding. Ví dụ một thành phần điều khiển được gọi theo quy trình vận hành:

~~~java
import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.stereotype.Component;

@Component
public class OrderInputLifecycle {
    private final BindingsLifecycleController controller;

    public OrderInputLifecycle(BindingsLifecycleController controller) {
        this.controller = controller;
    }

    public void stopInput() {
        controller.stop("processOrder-in-0");
    }

    public void startInput() {
        controller.start("processOrder-in-0");
    }
}
~~~

Actuator cũng hỗ trợ endpoint bindings khi được bật và phân quyền. Thao tác STARTED/STOPPED là điều khiển lifecycle. PAUSED/RESUMED chỉ hoạt động ở các binder/transport hỗ trợ; tài liệu Spring Cloud Stream ghi rõ không phải binder nào cũng hỗ trợ pause/resume.

**Không dùng readiness failure như cơ chế stop consumer.** Nếu một Pod xử lý Kafka consumer ngay cả khi NotReady, đó là hành vi hợp lệ: Kubernetes vẫn cho Pod chạy và Kafka vẫn phân phối record theo consumer group.

Cần thận trọng khi stop binding trong production: message đang xử lý có thể bị giao lại, partition assignment có thể thay đổi và producer/consumer downstream có thể nhìn thấy duplicate. Hãy thiết kế idempotency và kiểm thử lifecycle action trong môi trường staging.

## 17. Broker mất kết nối: điều gì thực sự xảy ra?

| Tình huống | Liveness | Readiness đề xuất | Điều cần quan sát |
|---|---|---|---|
| Kafka broker tạm down, consumer còn khả năng reconnect | Giữ UP | Tùy vai trò HTTP; worker-only thường không cần đưa broker vào readiness | Lag, reconnect, failed poll/commit |
| RabbitMQ restart, unacked message được requeue | Giữ UP | Tùy khả năng tiếp nhận request mới | Redelivery, unacked count, DLQ |
| Pulsar broker mất kết nối, client đang thử reconnect | Giữ UP | Tùy khả năng publish hoặc lưu outbox | Subscription backlog, errors, retry |
| Kafka Streams task đang rebalance/restore | Thường giữ UP | Có thể chưa ready với nghiệp vụ phải phục vụ query state | Thread/task state, restore duration |
| Application deadlock không thể phục hồi | DOWN nếu xác minh được tình trạng nội tại | DOWN | Thread dump, request timeout, restart count |
| Broker down kéo dài nhưng API có durable outbox | UP | Có thể UP nếu lưu outbox và tiếp nhận request đúng hợp đồng | Outbox pending, publish retry |
| Broker down kéo dài, API yêu cầu publish đồng bộ | UP | Có thể DOWN | Publish failures, client timeout |

Khi broker phục hồi, backlog có thể khiến consumer lag tăng cao rồi giảm dần. Việc liveness vẫn UP không có nghĩa không cần cảnh báo. Alert cần dựa trên tình trạng luồng dữ liệu, độ trễ và số lần retry; không chỉ dựa trên Pod Ready.

Khi thiết kế recovery, xét các giới hạn của client như connection backoff, Kafka poll interval, listener concurrency, Rabbit prefetch, Pulsar subscription type và DLQ. Restart toàn bộ Pod có thể tạo duplicate và làm thời gian phục hồi dài hơn.

## 18. Graceful shutdown khi deploy hoặc scale down

Khi rollout phiên bản mới hoặc scale down, Kubernetes gửi tín hiệu dừng theo vòng đời container. Spring Boot có graceful shutdown cho web server: nó ngừng nhận request mới và chờ xử lý request đang chạy trong giới hạn cấu hình. Các binder là SmartLifecycle components và có quá trình stop riêng khi application context đóng.

Ví dụ cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

Kết hợp với **terminationGracePeriodSeconds: 60** ở Pod để dành thời gian cho ứng dụng kết thúc có kiểm soát. Giá trị thực phải đo theo batch size, thời gian xử lý handler và yêu cầu của orchestrator.

Đối với message consumer, cần kiểm tra:

1. Thời điểm consumer ngừng nhận delivery mới.
2. Message đang xử lý có hoàn tất hay bị hủy.
3. Offset Kafka hoặc acknowledgement Rabbit/Pulsar có được ghi nhận.
4. Message chưa ack có được giao lại sau khi instance dừng.
5. Idempotency có ngăn side effect trùng khi nhận lại không.
6. Producer có flush output hoặc publisher confirm trước khi process kết thúc không.

Không dựa vào graceful shutdown để đạt exactly-once xuyên Kafka/RabbitMQ/Pulsar và database. Khi process bị kill đột ngột, message có thể được giao lại. Thiết kế idempotent và outbox vẫn cần thiết khi có side effect quan trọng.

## 19. Health của nhiều binder và binder không sử dụng

Trong ứng dụng multi-binder, một instance có thể dùng Kafka Binder cho input và Rabbit Binder cho output. Contributor **binders** có thể gộp sức khỏe của cả hai. Nếu Rabbit tạm down, global /actuator/health có thể DOWN dù Kafka consumer vẫn nhận dữ liệu. Điều này cần được diễn giải theo ranh giới nghiệp vụ.

Một vấn đề khác: ứng dụng có thể để một binder implementation trên classpath nhưng không tạo binding cho nó. Tài liệu Spring Cloud Stream cảnh báo binder không sử dụng có thể báo DOWN vì không có destination được đăng ký. Khi đó global health bị ảnh hưởng dù các binding thực tế đang chạy.

Cách xử lý:

- Giữ dependency classpath chỉ gồm binder thực sự cần dùng.
- Kiểm tra các alias/named binder đã được khởi tạo.
- Dùng health indicator phù hợp với mỗi binder.
- Nếu có custom health implementation, đưa vào nhóm health phù hợp theo chức năng.
- Không vô hiệu hóa toàn bộ kiểm tra binder chỉ để ẩn một lỗi cấu hình thực sự.

Nếu cần tắt health của một binder trong multi-binder environment, có thể đặt **management.health.binders.enabled=false** trong environment của binder đó. Phải phân biệt việc tắt indicator với việc ngừng kết nối hoặc khắc phục broker error.

## 20. Khi nào chọn custom health thay vì binders mặc định?

Bản thân binder health có thể không mô tả đúng hợp đồng đầu cuối. Ví dụ:

- Kafka metadata healthy nhưng một consumer handler luôn ném exception.
- RabbitMQ connection UP nhưng exchange không route tới queue nào.
- Pulsar client kết nối được nhưng subscription không nhận message do ACL hoặc schema.
- Kafka Streams thread RUNNING nhưng một stateful window đang lag lớn.
- HTTP request nhận 202 vì outbox đã lưu thành công dù broker chưa thể publish.

Trong các trường hợp đó, một indicator hoặc metric theo nghiệp vụ có ý nghĩa hơn. Custom readiness nên trả lời câu hỏi cụ thể: “Instance này có thể nhận và xử lý request mới theo hợp đồng đã công bố không?”. Nó không nên trở thành bản sao của dashboard monitor broker.

Nếu cần dùng network check trong readiness, hãy đảm bảo timeout nhỏ, tần suất hợp lý, cache trạng thái và giới hạn số connection tạo mới. Tránh check nặng trong mọi lần kubelet poll.

## 21. Monitoring ngoài Kubernetes probes

Probes là công cụ điều khiển vòng đời Pod và traffic. Chúng không thể thay thế hệ thống observability.

| Tín hiệu | Giá trị vận hành |
|---|---|
| Kubernetes restarts / CrashLoopBackOff | Phát hiện liveness config sai hoặc startup fail |
| Pod Ready ratio | Phát hiện instance bị loại khỏi Service |
| Broker connect/reconnect attempts | Phát hiện mất kết nối và phục hồi |
| Kafka consumer lag / partition assignment | Đo khả năng theo kịp nguồn dữ liệu |
| Kafka Streams task/thread state, restore duration | Đo tiến trình của topology stateful |
| Rabbit ready/unacked/redelivery/DLQ depth | Quan sát backlog và duplicate |
| Pulsar subscription backlog/unacked/redelivery | Quan sát consumer subscription |
| Producer send failures, confirm latency | Đo khả năng xuất dữ liệu |
| Retry count, retry exhaustion, DLT count | Phát hiện poison messages |
| Handler latency / throughput | Phát hiện bottleneck của nghiệp vụ |
| Outbox pending age | Phát hiện bridge chưa gửi được sự kiện |

Một sự cố broker thường hiện ra đồng thời ở nhiều tín hiệu: connect failures tăng, lag hoặc queue depth tăng, DLT có thể tăng, nhưng liveness vẫn UP. Đây là mục tiêu đúng của phân tách health: cảnh báo sự cố hạ tầng mà không tạo restart storm.

Nên dùng metric và alert để quyết định khi nào cần con người can thiệp hoặc automation vận hành, thay vì biến mọi ngưỡng lag cao thành liveness DOWN.

## 22. Kiểm thử thực tế trước khi triển khai

Dùng Testcontainers, môi trường staging có broker thật hoặc chaos testing có kiểm soát để kiểm chứng các hành vi:

1. Khởi động khi broker đã sẵn sàng: liveness/readiness lên UP đúng thứ tự.
2. Khởi động khi broker tạm chưa sẵn sàng: kiểm tra binder provisioning có fail-fast hay retry; không giả định startup probe sửa được lỗi khởi động không thể phục hồi.
3. Dừng Kafka trong lúc consumer đang chạy: kiểm tra liveness không DOWN chỉ vì broker, và consumer reconnect sau khi broker trở lại.
4. Dừng RabbitMQ khi có delivery chưa ack: kiểm tra redelivery/idempotency.
5. Ngắt Pulsar broker rồi phục hồi: kiểm tra subscription, reconnect và redelivery.
6. Tạo Kafka Streams rebalance/state restore dài: startup/readiness không khiến Pod bị restart sai.
7. Kiểm tra /actuator/health, /livez, /readyz trả HTTP status như cấu hình.
8. Nếu readiness phụ thuộc binder, xác minh cả tình huống broker lỗi và broker phục hồi; đánh giá tác động tới tất cả Pod.
9. Kiểm tra background consumer vẫn có thể nhận message trong khi Pod NotReady nếu không stop binding.
10. Simulate graceful shutdown và hard kill: xác minh ack/offset, message redelivery và idempotency.
11. Giả lập một binder không sử dụng trên classpath: kiểm tra global health có bị false DOWN không.
12. Kiểm tra network timeout của health indicator không vượt timeoutSeconds của kubelet.
13. Đảm bảo Actuator không lộ thông tin nhạy cảm qua health details hoặc bindings endpoint.

Một bài kiểm thử chỉ assert rằng GET /readyz trả 200 không chứng minh ứng dụng đang tiêu thụ thành công. Phải gửi message thật, xác minh side effect, trạng thái commit/ack và metrics tiến triển.

## 23. Triệu chứng thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Broker down kéo theo hàng loạt Pod restart | Liveness bao gồm binder/external health | Tách external dependency ra khỏi liveness |
| /actuator/health DOWN nhưng /readyz UP | Readiness group chỉ gồm readinessState | Đây có thể là thiết kế đúng; đối chiếu workload contract |
| Pod NotReady nhưng Kafka vẫn xử lý message | Readiness không điều khiển consumer group | Dùng binding lifecycle nếu thực sự cần dừng nhận |
| Probe timeout dù app còn hoạt động | Binder health query chờ broker quá lâu | Kiểm tra healthTimeout, timeoutSeconds và thiết kế cache |
| Stateful processor liên tục restart khi rebalance | Liveness gắn trực tiếp Kafka Streams thread status | Dành thời gian restore/rebalance; dùng metric riêng |
| Consumer không nhận message sau khi Ready | Binding chưa tạo, ACL lỗi, schema sai hoặc handler bị lỗi | Kiểm tra binding state, error logs và broker metrics |
| Không có /livez hoặc /readyz | Chưa bật probes/additional paths hoặc thiếu web server | Kiểm tra Actuator, path và cổng main server |
| Kafka Binder báo DOWN dù Kafka Streams chạy | Kafka binder dependency không sử dụng trên classpath | Loại bỏ binder thừa hoặc kiểm tra health configuration |
| Một broker lỗi làm toàn bộ Service mất endpoint | Readiness gộp mọi binder | Xác định dependency thật sự cần thiết cho HTTP traffic |
| Broker phục hồi nhưng lag tiếp tục tăng | Consumer xử lý không theo kịp hoặc handler retry liên tục | Điều tra throughput, partition, DLQ và downstream |
| Shutdown làm message xử lý hai lần | Ack/commit chưa ghi nhận trước khi Pod dừng | Dùng idempotency và kiểm thử shutdown window |

## 24. Checklist production

- [ ] Liveness chỉ kiểm tra tình trạng nội tại khó tự phục hồi.
- [ ] Readiness phản ánh hợp đồng tiếp nhận traffic, không đơn thuần là broker có ping được không.
- [ ] Với worker chỉ tiêu thụ message, hiểu rằng Pod NotReady không tự pause consumer.
- [ ] Startup probe đủ thời gian cho Spring Boot và Kafka Streams state restoration.
- [ ] Có Actuator, web stack và đúng path/port cho HTTP probe.
- [ ] Nếu management port khác main port, cân nhắc /livez và /readyz trên main server port.
- [ ] Không đưa tất cả dependency bên ngoài vào liveness.
- [ ] Xác minh binder health riêng cho Kafka, RabbitMQ và Pulsar theo phiên bản đang dùng.
- [ ] Không gộp binder không thiết yếu vào readiness của mọi chức năng.
- [ ] Health indicator không gây network storm hoặc block quá lâu.
- [ ] Graceful shutdown timeout tương thích terminationGracePeriodSeconds.
- [ ] Có idempotency khi broker redelivery hoặc Pod restart.
- [ ] Theo dõi consumer lag, queue depth, subscription backlog, retry và DLQ.
- [ ] Kiểm thử broker disconnect/reconnect, restart, rebalance và state restoration.
- [ ] Bảo vệ endpoint Actuator và giới hạn thông tin health details.

## 25. Tài liệu tham khảo

- [Spring Boot — Actuator Endpoints và Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html), ApplicationAvailability, liveness/readiness health groups, additional paths và nguyên tắc kiểm tra hệ thống bên ngoài.
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/), tác động của từng probe lên container và Service endpoints.
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/), startup timeout, failureThreshold, successThreshold và HTTP probe.
- [Spring Cloud Stream — Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/health-indicator.html), binders health contributor, nhiều binder và sự khác biệt theo implementation.
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html), healthTimeout, metadata và partition leader.
- [Spring Cloud Stream — Kafka Streams Binder Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/health-indicator.html), RUNNING thread state, task metadata và application ID.
- [Spring Cloud Stream — Rabbit Binder Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/health-indicator.html), Spring Boot Rabbit health và management.health.binders.enabled.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html), Pulsar client, consumer/producer và subscription.
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html), quản lý vòng đời binding bằng controller và Actuator.
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html), thời gian kết thúc HTTP và lifecycle khi dừng ứng dụng.

Liveness, readiness và binder health trả lời ba câu hỏi khác nhau. Một broker mất kết nối tạm thời thường cần được xử lý bằng reconnect, retry và giám sát lag, chứ không phải restart toàn bộ Pod. Readiness chỉ nên phản ánh khả năng nhận traffic theo hợp đồng; Kubernetes NotReady không tự ngừng consumer đang được broker phân phối message. Khi thêm Actuator health groups, probe timeout hợp lý, graceful shutdown và kiểm thử sự cố broker thật, ứng dụng Spring Cloud Stream có thể tự phục hồi mà không gây cascading failure khi hệ thống message gặp sự cố.

