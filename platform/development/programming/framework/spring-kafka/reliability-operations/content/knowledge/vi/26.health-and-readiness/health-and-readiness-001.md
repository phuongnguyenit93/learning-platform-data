# Health indicator cho Kafka connection

Một ứng dụng Spring Kafka có thể khởi động thành công, web server vẫn trả HTTP 200 và listener container vẫn tồn tại trong Spring context, nhưng kết nối tới Kafka broker đã mất hoặc Kafka cluster không thể phục vụ request. Nếu hệ thống chỉ kiểm tra JVM/process hoặc HTTP endpoint, tình trạng phụ thuộc Kafka bị lỗi có thể không được phát hiện kịp thời.

**Health indicator cho Kafka connection** là cơ chế kiểm tra và biểu diễn tình trạng kết nối Kafka trong Spring Boot Actuator. Nó giúp trả lời câu hỏi: ứng dụng có thể giao tiếp với Kafka cluster qua cấu hình và quyền truy cập đang dùng hay không? Tín hiệu này có thể được đưa vào health endpoint, dashboard và chính sách readiness phù hợp.

Cần hiểu rõ phạm vi: **Kafka connection health không đồng nghĩa toàn bộ Kafka workflow đang khỏe mạnh**. Một AdminClient có thể truy vấn cluster metadata thành công trong khi consumer không được assign partition, producer không có quyền ghi topic, listener xử lý chậm hoặc database bị lỗi. Health indicator là một phép kiểm tra có giới hạn, không phải chứng minh end-to-end rằng mọi record được xử lý thành công.

## 1. Health indicator nằm ở đâu trong Spring Boot?

Spring Boot Actuator cung cấp mô hình health contributors. Một health contributor có thể là:

- `HealthIndicator`: kiểm tra đồng bộ và trả về `Health`.
- `ReactiveHealthIndicator`: thực hiện kiểm tra theo API reactive.
- `CompositeHealthContributor`: nhóm nhiều contributor.
- Các health groups: tập hợp những contributor phục vụ một mục đích như readiness hoặc liveness.

Spring Boot có thể tự cấu hình health indicator cho những dependency phổ biến khi dependency và bean cần thiết có mặt. Với ứng dụng có Spring Kafka và Actuator, các phiên bản Spring Boot hỗ trợ có thể cung cấp **Kafka health indicator** dựa trên `KafkaAdmin`.

Luồng khái niệm:

~~~text
Kubernetes / Load balancer / Operator
                 |
                 v
          /actuator/health
                 |
                 v
       Spring Boot HealthEndpoint
                 |
                 v
          HealthContributor
                 |
          +------+------+
          |             |
          v             v
     Kafka health    DB health
      indicator      indicator
          |             |
          v             v
     KafkaAdmin      DataSource
          |
          v
     Kafka cluster
~~~

Health endpoint tổng hợp kết quả từ các contributors theo status và status aggregator. Tùy cấu hình, một contributor có thể được hiển thị trong response hoặc được đưa vào một health group cụ thể.

## 2. Kafka health indicator kiểm tra điều gì?

Kafka health indicator tích hợp của Spring Boot thường sử dụng **KafkaAdmin/AdminClient** để giao tiếp với Kafka cluster và truy vấn thông tin cluster. Những thông tin trả về có thể bao gồm cluster ID và broker nodes, tùy phiên bản Spring Boot.

Một kết quả `UP` thường cho thấy health check đã hoàn thành thao tác Kafka Admin mà indicator yêu cầu trong giới hạn thời gian của nó. Đây là bằng chứng hữu ích rằng cấu hình kết nối và đường giao tiếp Admin tới cluster đang hoạt động.

Nó không tự chứng minh:

- Consumer group đã được tạo hoặc đang có member.
- Listener đã nhận partition assignment.
- Consumer có quyền đọc mọi topic mà ứng dụng cần.
- Producer có quyền ghi mọi output topic.
- Kafka transaction có thể commit.
- DLT/retry topics đã được tạo đúng partition và ACL.
- Database side effect đã commit.
- Consumer lag đang nằm trong SLO.
- Business event đã được xử lý đúng một lần.

| Kiểm tra | Kafka health indicator tổng quát có thể chứng minh? |
|---|---|
| Kết nối Admin tới cluster và lấy cluster metadata | **Có**, theo thao tác cụ thể của indicator |
| Consumer group có assignment mong muốn | Không |
| Đọc được record từ một topic cụ thể | Không nhất thiết |
| Ghi được record vào một topic cụ thể | Không |
| Transactional producer commit thành công | Không |
| Listener xử lý record thành công | Không |
| Consumer lag thấp | Không |
| Database và Kafka nhất quán | Không |

Vì thế, đặt tên dashboard là **Kafka cluster connectivity** sẽ chính xác hơn một nhãn chung chung như “Kafka application fully healthy” nếu indicator chỉ kiểm tra Admin connectivity.

## 3. Bật Actuator và Kafka health indicator

Ứng dụng cần có Spring Boot Actuator và Spring Kafka tương ứng. Với Maven, các dependency thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
~~~

Spring Boot có thể cung cấp Kafka health contributor khi có `KafkaAdmin` và auto-configuration phù hợp. Một cấu hình cơ bản:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: when-authorized
  health:
    kafka:
      enabled: true
~~~

`management.health.kafka.enabled` là thuộc tính bật/tắt contributor theo cơ chế health indicator của Spring Boot ở các phiên bản hỗ trợ. Nếu response không có component `kafka`, cần kiểm tra:

1. Actuator dependency có trong runtime classpath không?
2. Có `KafkaAdmin` bean hay không?
3. Kafka health auto-configuration có bị exclude không?
4. `management.health.kafka.enabled` có bị đặt `false` ở profile/environment khác không?
5. Phiên bản Spring Boot có cung cấp Kafka health contributor theo cách đang kỳ vọng không?
6. Health endpoint có expose component details theo quyền hiện tại không?

Đừng kết luận indicator không chạy chỉ vì response mặc định không hiển thị tất cả details. `show-details` và `show-components` có chính sách hiển thị riêng.

## 4. Cấu hình KafkaAdmin và connection properties

Kafka health indicator chỉ có thể kiểm tra bằng chính cấu hình Kafka mà AdminClient sử dụng. Nếu broker yêu cầu SASL/SSL, credentials và truststore phải đúng.

Ví dụ cấu hình kết nối bảo mật theo hướng minh họa:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.example.internal:9093
      - kafka-2.example.internal:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="\${KAFKA_USERNAME}"
        password="\${KAFKA_PASSWORD}";
      ssl.truststore.location: \${KAFKA_TRUSTSTORE_PATH}
      ssl.truststore.password: \${KAFKA_TRUSTSTORE_PASSWORD}
~~~

Các giá trị là placeholder; không commit credentials vào source control. Trong môi trường thật, dùng secret manager/Kubernetes Secret và chính sách rotation phù hợp.

Spring Boot có thể áp dụng `spring.kafka.properties` làm common properties cho các Kafka clients; cấu hình riêng cho Admin, producer và consumer có thể được đặt ở các namespace tương ứng như `spring.kafka.admin.properties`, `spring.kafka.producer.properties` và `spring.kafka.consumer.properties`.

Điểm quan trọng: nếu listener dùng credentials hoặc client properties khác với AdminClient, **Kafka health indicator có thể UP trong khi consumer/producer vẫn lỗi**. Hãy kiểm tra cấu hình thực tế của từng client.

### 4.1. Bootstrap servers không phải toàn bộ broker topology

Client dùng bootstrap servers để bắt đầu kết nối và lấy metadata. Sau đó nó có thể kết nối tới những broker được metadata trả về. Một bootstrap endpoint reachable chưa chứng minh mọi broker, leader hoặc partition replica đều khỏe mạnh.

Health check lấy metadata thành công là một tín hiệu cluster reachability; nó không thay thế broker metrics, ISR monitoring hoặc partition-level diagnostics.

## 5. Đọc health response

Một response minh họa:

~~~json
{
  "status": "UP",
  "components": {
    "kafka": {
      "status": "UP",
      "details": {
        "clusterId": "cluster-abc",
        "nodes": 3
      }
    },
    "db": {
      "status": "UP"
    },
    "diskSpace": {
      "status": "UP"
    }
  }
}
~~~

Cấu trúc details cụ thể phụ thuộc Spring Boot version và contributor. Không dựa vào một field chưa được cam kết như API ổn định nếu ứng dụng cần parse health response tự động.

Khi Kafka không truy cập được, component có thể chuyển sang `DOWN` hoặc trạng thái khác tùy exception và implementation. Health endpoint tổng hợp có thể chuyển status tổng thể theo `StatusAggregator`.

Các status phổ biến:

| Status | Ý nghĩa khái quát |
|---|---|
| `UP` | Thành phần đang đáp ứng health check |
| `DOWN` | Thành phần kiểm tra thất bại |
| `OUT_OF_SERVICE` | Thành phần không nên được dùng tại thời điểm này |
| `UNKNOWN` | Không xác định được trạng thái |

Health status tổng thể có thể bị ảnh hưởng bởi các contributors khác và thứ tự status aggregator. Đừng suy luận chỉ từ một component khi đọc response ở root `/actuator/health`.

## 6. Timeout: health check không được treo vô hạn

Một health indicator gọi Kafka Admin API có thể bị chậm vì:

- DNS hoặc bootstrap endpoint không phân giải được.
- TCP connection bị timeout.
- TLS handshake hoặc SASL authentication bị chậm/lỗi.
- Broker không phản hồi.
- Request metadata/describe cluster không hoàn tất.
- Network partition hoặc firewall drop packets.

Nếu mỗi probe chờ quá lâu, health endpoint có thể chiếm thread, gây nghẽn các health checks khác và làm orchestrator đánh giá sai tình trạng ứng dụng.

Kafka client có các timeout như `request.timeout.ms` và `default.api.timeout.ms`. Có thể cấu hình giới hạn phù hợp cho AdminClient:

~~~yaml
spring:
  kafka:
    admin:
      properties:
        request.timeout.ms: 3000
        default.api.timeout.ms: 5000
~~~

Các giá trị minh họa này cần được cân nhắc theo network latency, broker topology và SLA. Chúng không phải một timeout duy nhất áp dụng cho toàn bộ Spring health endpoint. Health indicator implementation và client API quyết định thao tác nào bị giới hạn bởi timeout nào.

Ngoài ra, Spring Boot có thể log các health indicator chạy chậm qua cấu hình slow-indicator logging ở những phiên bản hỗ trợ. Đây là log cảnh báo thời gian kiểm tra, không tự cắt một health check bị block.

**Không đặt timeout quá ngắn chỉ để probe trả về nhanh.** Nếu timeout thấp hơn độ trễ bình thường của cluster, health sẽ chập chờn và tạo flapping.

## 7. Phân biệt connection health với readiness

Readiness trả lời câu hỏi: **instance này đã sẵn sàng nhận loại công việc mà hệ thống giao cho nó chưa?**

Kafka connection health là một input có thể hữu ích, nhưng không phải readiness hoàn chỉnh.

Ví dụ:

- Một HTTP service chỉ dùng Kafka để phát event bất đồng bộ: Kafka unavailable có thể làm một số API không đáp ứng hợp đồng, nhưng các endpoint đọc dữ liệu khác vẫn hoạt động.
- Một consumer worker cần Kafka để nhận công việc: mất Kafka có thể khiến worker không thể tiếp tục công việc.
- Một service đã kết nối cluster nhưng chưa được assign partition: Admin health vẫn có thể `UP`, còn consumer chưa thực sự xử lý được record.
- Một service có listener đang chạy nhưng database down: Kafka health `UP`, business readiness vẫn có thể `DOWN`.

Readiness cần dựa trên **business capability** mà instance cam kết cung cấp, không chỉ một kết nối mạng.

## 8. Phân biệt readiness và liveness

Spring Boot Actuator hỗ trợ health groups dành cho Kubernetes probes trong những phiên bản hiện đại.

~~~text
Kubernetes
    |
    +---- liveness probe
    |        |
    |        v
    |    /actuator/health/liveness
    |
    +---- readiness probe
             |
             v
         /actuator/health/readiness
~~~

- **Liveness:** process có đang sống và có khả năng tiếp tục hoạt động không?
- **Readiness:** instance có nên được nhận traffic/công việc mới theo hợp đồng ứng dụng không?

Một lỗi Kafka broker bên ngoài thường **không nên tự động làm liveness DOWN**. Nếu liveness fail khiến Kubernetes restart mọi Pod trong lúc Kafka cluster đang outage, các lần restart không sửa được broker và có thể tạo thêm connection storm/rebalance.

Readiness có thể bao gồm Kafka nếu service thực sự không thể phục vụ công việc khi Kafka unavailable. Tuy nhiên, với consumer-only worker, readiness HTTP không trực tiếp dừng Kafka consumer hoặc thu hồi partition; cần hiểu orchestrator và listener lifecycle điều khiển nhau như thế nào.

### 8.1. Cấu hình health probes

Ví dụ bật probe groups:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,kafka
~~~

Cấu hình trên minh họa đưa Kafka indicator vào readiness group. Chỉ sử dụng nếu chính sách service yêu cầu instance không sẵn sàng khi Kafka connection thất bại.

Không thêm `kafka` vào liveness group chỉ vì Kafka là dependency quan trọng. Một broker outage không phải bằng chứng JVM bị deadlock hoặc process cần restart.

Nếu ứng dụng có nhiều capability, có thể tạo custom group riêng như `kafkaConnectivity` hoặc `messagingReadiness` để người vận hành xem dependency health mà không buộc mọi traffic readiness phụ thuộc nó.

### 8.2. Readiness của worker không giống readiness của HTTP API

Với service tiêu thụ Kafka, HTTP readiness endpoint có thể chỉ phục vụ Kubernetes rollout/monitoring; Kafka broker không dùng endpoint này để cấp partition. Nếu muốn tạm ngừng consume khi dependency không sẵn sàng, cần có cơ chế điều khiển listener container (pause/stop/start) và recovery policy riêng.

Đừng cho rằng `readiness=DOWN` tự động gọi `KafkaListenerEndpointRegistry.stop()`. Hai cơ chế không tự liên kết nếu ứng dụng không cấu hình orchestration.

## 9. Health indicator mặc định và custom health indicator

Health indicator tích hợp thường đủ để trả lời câu hỏi **Kafka cluster có reachable qua Admin API hay không**. Một số ứng dụng cần kiểm tra sâu hơn:

- Topic bắt buộc có tồn tại không?
- Consumer group có assignment không?
- Producer có quyền ghi topic output không?
- DLT và retry topics có metadata hợp lệ không?
- Một canary event có thể được publish và consume không?

Không nên biến tất cả những kiểm tra đó thành một health check chạy mỗi vài giây. Mỗi phép kiểm tra sâu có thể tạo traffic, cần ACL khác, có side effect hoặc làm health endpoint phụ thuộc quá nhiều vào hệ thống ngoài.

### 9.1. Khi nào cần custom HealthIndicator?

Dùng custom indicator khi có **business capability cụ thể** mà built-in check không xác nhận. Ví dụ một service bắt buộc đọc được metadata của topic `payments.authorized` hoặc cần một producer/consumer credential khác với AdminClient.

Custom check nên:

1. Dùng đúng credentials/client configuration của capability cần xác minh.
2. Có timeout hữu hạn.
3. Không gửi business event giả vào topic thật trong mỗi probe.
4. Không làm commit offset hoặc thay đổi state nghiệp vụ.
5. Không tạo producer/consumer mới ở mỗi lần health call nếu có thể tái sử dụng resource an toàn.
6. Có metric/log cho chính health check.
7. Phân biệt trạng thái `DOWN` với lỗi tạm thời và `UNKNOWN` khi kết quả không xác định.

### 9.2. Ví dụ custom AdminClient health check

Có thể tạo một AdminClient dùng chung với cấu hình KafkaAdmin và đóng khi Spring context shutdown. Ví dụ sau minh họa kiểm tra cluster metadata có timeout hữu hạn:

~~~java
import java.util.Collection;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.DescribeClusterResult;
import org.apache.kafka.common.Node;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.kafka.core.KafkaAdmin;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

@Configuration
class KafkaHealthAdminConfiguration {

    @Bean(destroyMethod = "close")
    AdminClient healthAdminClient(KafkaAdmin kafkaAdmin) {
        return AdminClient.create(kafkaAdmin.getConfigurationProperties());
    }
}

@Component("kafkaConnection")
class KafkaConnectionHealthIndicator implements HealthIndicator {

    private final AdminClient adminClient;

    KafkaConnectionHealthIndicator(AdminClient adminClient) {
        this.adminClient = adminClient;
    }

    @Override
    public Health health() {
        try {
            DescribeClusterResult result = adminClient.describeCluster();

            String clusterId =
                    result.clusterId().get(3, TimeUnit.SECONDS);

            Collection<Node> nodes =
                    result.nodes().get(3, TimeUnit.SECONDS);

            return Health.up()
                    .withDetail("clusterId", clusterId)
                    .withDetail("brokerCount", nodes.size())
                    .build();
        } catch (Exception exception) {
            return Health.down(exception).build();
        }
    }
}
~~~

Ví dụ cần được đối chiếu với API Spring Kafka/Kafka client đúng phiên bản của ứng dụng; nếu phiên bản không công khai phương thức lấy cấu hình như trên, hãy tạo AdminClient từ cùng bộ properties được quản lý bởi cấu hình ứng dụng. Không hard-code một bootstrap server mới và vô tình bỏ qua SASL/SSL credentials.

Đây là **custom indicator** có ID `kafkaConnection`; nếu built-in Kafka indicator đã được đăng ký, hai checks có thể trùng chức năng. Chỉ giữ cả hai khi chúng có mục tiêu riêng và người vận hành hiểu được sự khác nhau.

Health indicator này chỉ kiểm tra Admin API/cluster metadata. Nó vẫn không chứng minh producer có quyền `WRITE` hoặc consumer có quyền `READ` trên topic nghiệp vụ.

### 9.3. Topic metadata check không phải produce/consume canary

Một custom check dùng AdminClient `describeTopics` có thể xác nhận topic tồn tại và metadata có thể truy cập. Nhưng điều đó không chứng minh ứng dụng có thể publish record vào topic nếu ACL WRITE bị từ chối.

Một phép thử produce/consume thật cần canary topic, key, consumer group, cleanup/retention và quy trình không tạo business side effect. Nên chạy **định kỳ như synthetic monitoring** với timeout riêng, không thực hiện trên mỗi Kubernetes readiness probe.

## 10. Health checks và security

Health endpoint có thể để lộ:

- Broker hostnames và cluster topology.
- Topic names và consumer group.
- Exception message chứa hostname, credentials path hoặc nội dung nhạy cảm.
- Thông tin network/security configuration.

Trong production, không công khai `show-details=always` cho mọi người dùng. Một cấu hình thận trọng:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Có thể giới hạn Actuator endpoint bằng network policy, authentication và management port riêng theo kiến trúc. Nếu health endpoint là đường Kubernetes probe, cần bảo đảm kubelet có thể truy cập mà không làm lộ details cho người dùng bên ngoài.

Health indicator không nên trả password, JAAS config, token, SASL payload hoặc toàn bộ client properties trong `details`.

## 11. Kafka health UP nhưng listener vẫn không xử lý record

Đây là một tình huống thường gây hiểu nhầm.

~~~text
/actuator/health:
  kafka = UP

Kafka consumer:
  container = RUNNING
  assignment = empty
  records processed = 0
  lag = increasing
~~~

Các nguyên nhân có thể:

- Consumer group chưa hoàn tất rebalance.
- Topic subscription sai hoặc topic không có partition phù hợp.
- Số consumer nhiều hơn số partition, một số consumer không được assign.
- Consumer có authentication/authorization riêng khác AdminClient.
- Container đang pause.
- Deserialization hoặc listener errors.
- Listener đang xử lý một record quá lâu.
- `max.poll.interval.ms` bị vi phạm.
- Offset commit/transaction bị lỗi.

Health indicator kết nối Admin thành công không kiểm tra tất cả những trạng thái trên. Để chẩn đoán cần consumer group metrics, listener container state, rebalance events, lag, logs và traces.

## 12. Producer health khác Admin connection health

Một ứng dụng có thể dùng:

- AdminClient để mô tả cluster và tạo topic.
- Producer để gửi event.
- Consumer để đọc event.

Ba client có thể dùng chung bootstrap servers nhưng có credentials, ACL và properties riêng.

Ví dụ Admin health `UP` trong khi producer gặp:

- `TopicAuthorizationException` do thiếu quyền WRITE.
- `RecordTooLargeException` do payload vượt giới hạn.
- Serializer exception.
- `ProducerFencedException` do transactional ID bị chiếm.
- Timeout hoặc broker errors ở request gửi.

Tương tự consumer có thể bị `TopicAuthorizationException` khi đọc hoặc gặp deserialization failure dù AdminClient vẫn truy vấn cluster được.

Nếu business capability bắt buộc publish, nên có producer-specific telemetry hoặc synthetic canary được kiểm soát. Không suy ra publish health từ Admin health.

## 13. Health indicator và consumer group assignment

Consumer group assignment là một trạng thái động. Một service có thể kết nối broker thành công nhưng chưa sở hữu partition.

Nếu readiness phụ thuộc consumer có assignment, hãy xây dựng tín hiệu riêng dựa trên listener/container và rebalance callbacks, ví dụ:

- Container đã start.
- Consumer đã join group.
- Partition assignment phù hợp với topology.
- Listener có thể poll và tiến triển.
- Consumer lag không vượt ngưỡng được định nghĩa.

Không đưa một điều kiện `assignmentCount > 0` vào mọi service một cách máy móc. Nếu một group có 2 partitions và 5 consumers, ba consumer idle vẫn có thể là trạng thái bình thường; nếu service chỉ xử lý một topic thưa, assignment và record traffic cũng là hai khái niệm riêng.

Với concurrent container, cần theo dõi parent/child containers và partition ownership đúng phạm vi. Không dùng số `ConsumerStartedEvent` làm số partition assigned.

## 14. Không đưa dependency ngoài vào liveness một cách tùy tiện

Giả sử Kafka cluster mất kết nối trong 90 giây:

~~~text
Kafka broker outage
      |
      +---- Kafka health = DOWN
      |
      +---- liveness = UP
      |
      +---- readiness có thể DOWN theo policy
      |
      +---- Kubernetes không restart tất cả Pods chỉ vì dependency outage
      |
      +---- ứng dụng chờ broker phục hồi và tiếp tục
~~~

Nếu đưa Kafka vào liveness, Kubernetes có thể restart mọi instance khi broker outage. Việc restart liên tục tạo connection churn, consumer group rebalance và tải khởi động tăng, nhưng không khắc phục Kafka.

Liveness nên phát hiện trạng thái process không thể tự phục hồi như deadlock nghiêm trọng hoặc ứng dụng không còn tiến triển theo hợp đồng. Một dependency bên ngoài tạm thời không khả dụng thường là lý do để cảnh báo hoặc điều chỉnh readiness, không phải tự động kill JVM.

## 15. Timeout, flapping và hysteresis

Health indicator được gọi định kỳ. Nếu Kafka network chập chờn, status có thể chuyển:

~~~text
UP -> DOWN -> UP -> DOWN -> UP
~~~

Trạng thái flapping có thể khiến alert liên tục mở/đóng, readiness thay đổi liên tục hoặc rollout bị gián đoạn.

Một số cách giảm nhiễu:

- Đặt request/connect timeouts phù hợp với latency thực tế.
- Alert theo thời gian duy trì, không theo một sample lỗi đơn lẻ.
- Phân biệt transient failure và permanent authentication/authorization failure.
- Dùng retry/backoff có giới hạn ở tầng health operation nếu phù hợp, không tạo request storm.
- Tách connectivity signal khỏi business readiness.
- Theo dõi duration và số lần liên tiếp fail/recover.

Không cache `UP` quá lâu tới mức che giấu outage. Nếu có hysteresis, phải ghi rõ độ trễ phát hiện tối đa và trade-off.

## 16. Health indicator không nên tạo tải hoặc side effect lớn

Health endpoint có thể được gọi nhiều lần bởi Kubernetes, load balancer, monitoring system và người vận hành. Nếu mỗi lần gọi tạo producer/consumer mới, gửi canary record, tạo topic hoặc đọc một lượng lớn dữ liệu, health checks có thể tự làm cluster quá tải.

Nên:

1. Ưu tiên built-in Admin connectivity check khi mục tiêu chỉ là reachability.
2. Dùng client có lifecycle được quản lý và đóng đúng cách.
3. Giữ số request và timeout nhỏ, hữu hạn.
4. Không tạo business record trong mỗi probe.
5. Không thực hiện expensive topic scans hoặc describe mọi consumer group nếu không cần.
6. Đưa synthetic produce/consume test sang lịch riêng.
7. Đảm bảo health check lỗi không làm thay đổi offset hay business state.

## 17. Custom health status theo capability

Một ứng dụng có thể định nghĩa nhiều nhóm health để không gom mọi ý nghĩa vào một component `kafka`.

Ví dụ:

~~~text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
/actuator/health/kafkaConnectivity
/actuator/health/messagingReadiness
~~~

- `kafkaConnectivity`: Admin API có thể kết nối cluster.
- `messagingReadiness`: những capability mà service cần để consume/publish theo policy.
- `readiness`: instance có thể nhận traffic/công việc theo hợp đồng service.
- `liveness`: process có thể tiếp tục hoạt động.

Health groups cho phép người vận hành xem các góc nhìn riêng. Đừng đưa custom group vào liveness/readiness tự động nếu chưa hiểu cách orchestrator phản ứng.

## 18. Kubernetes probes với Spring Boot

Ví dụ cấu hình probe groups và additional paths ở các phiên bản Spring Boot hỗ trợ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,kafka
~~~

Các đường dẫn bổ sung thường là `/livez` và `/readyz` trên main server port khi bật tính năng. Nếu chỉ expose Actuator qua management port riêng, cần kiểm tra kubelet có thể truy cập đúng port/path.

Readiness probe failure thường loại Pod khỏi endpoints phục vụ traffic; liveness probe failure có thể khiến container bị restart. Đừng để broker outage gây restart storm.

### 18.1. Ví dụ Kubernetes deployment

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: payment-worker
      image: example/payment-worker:latest
      ports:
        - name: http
          containerPort: 8080
      startupProbe:
        httpGet:
          path: /actuator/health/liveness
          port: http
        failureThreshold: 30
        periodSeconds: 5
      livenessProbe:
        httpGet:
          path: /actuator/health/liveness
          port: http
        periodSeconds: 10
      readinessProbe:
        httpGet:
          path: /actuator/health/readiness
          port: http
        periodSeconds: 5
~~~

Đây là ví dụ deployment, cần chỉnh port/path và startup budget theo ứng dụng. `startupProbe` bảo vệ giai đoạn khởi động chậm; nó không thay thế kiểm tra Kafka readiness. Với worker-only service, cân nhắc liệu readiness HTTP có thực sự là tín hiệu điều phối cần thiết hay nên dùng custom status/metrics cho consumer lifecycle.

## 19. Logging và metrics của health check

Health endpoint là snapshot; để xem lịch sử, cần metrics/logs riêng.

Metric gợi ý do ứng dụng/monitoring tự instrument:

| Metric | Ý nghĩa |
|---|---|
| `app.kafka.health.checks` | Số lần thực hiện health check |
| `app.kafka.health.failures` | Số lần health check thất bại |
| `app.kafka.health.duration` | Thời gian health operation |
| `app.kafka.health.status` | Trạng thái gần nhất nếu được biểu diễn bằng gauge/state |
| `app.kafka.admin.request.errors` | Lỗi request Admin API theo loại |

Không đưa exception message hoặc broker node ID thay đổi liên tục thành metric labels. Dùng structured logs cho chi tiết lỗi:

~~~text
event=dependency_health_check
dependency=kafka
indicator=kafka
status=DOWN
operation=describe_cluster
error_category=timeout
duration_ms=5000
instance=payment-worker-2
~~~

Các field là metadata do ứng dụng tự ghi, không phải response mặc định của Actuator. Không log credentials, SASL config hoặc secrets.

### 19.1. Phân biệt health failure và business failure

Một Kafka connection health check có thể `UP` trong khi DLT publish thất bại vì thiếu ACL cho DLT topic. Đừng gộp hai metric:

- `kafka_cluster_connectivity`: reachability của Admin API.
- `dlt_publish_failures`: kết quả publish recovery.
- `consumer_processing_failures`: business listener outcomes.
- `consumer_lag`: backlog.
- `kafka_transaction_commit_failures`: transaction outcome.

Mỗi metric đại diện cho một khả năng khác nhau. Dashboard nên hiển thị song song thay vì một health badge duy nhất.

## 20. Integration tests cho Kafka health indicator

Một test có ý nghĩa cần chạy health endpoint với Kafka broker thật, ví dụ Kafka Testcontainers hoặc Embedded Kafka.

Các trường hợp cơ bản:

1. **Broker available:** Kafka health component trả `UP`.
2. **Broker unavailable:** health check trả trạng thái fail theo implementation.
3. **Broker restart:** health phục hồi sau khi client kết nối lại.
4. **Authentication sai:** Admin health phản ánh lỗi credentials.
5. **Timeout:** health operation kết thúc trong ngân sách hữu hạn.
6. **Custom topic check:** topic metadata đúng/sai được phân biệt.
7. **ACL khác nhau:** Admin health có thể UP trong khi producer/consumer capability bị từ chối.
8. **Readiness policy:** Kafka DOWN làm readiness thay đổi theo cấu hình, liveness vẫn UP.
9. **Multiple clusters:** indicator phân biệt cluster/alias nếu service kết nối nhiều Kafka clusters.
10. **Health endpoint security:** details chỉ hiển thị cho principal được phép.

Ví dụ kiểm tra health endpoint:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class KafkaHealthIndicatorIT {

    @Autowired
    MockMvc mvc;

    @Test
    void kafkaComponentIsUpWhenBrokerIsAvailable() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.components.kafka.status")
                        .value("UP"));
    }
}
~~~

Imports và Testcontainers setup được lược bớt; broker phải thật sự được cấu hình vào application context. Nếu health details bị ẩn hoặc endpoint trả cấu trúc khác theo Spring Boot version, test nên dùng quyền phù hợp hoặc gọi health group/component theo contract đang expose.

### 20.1. Không test outage bằng cách chỉ mock indicator

Mock `KafkaHealthIndicator.health()` trả `DOWN` chỉ chứng minh endpoint tổng hợp status. Nó không chứng minh AdminClient timeout, broker reconnect, SSL/SASL hoặc health contributor auto-configuration hoạt động đúng.

Dùng unit tests cho status aggregation; dùng integration tests với broker/container/proxy để xác nhận network và Kafka client behavior.

### 20.2. Kiểm tra không gây side effect

Một health check nên không tạo business record hoặc commit offset. Trong integration test, xác nhận health polling nhiều lần không làm thay đổi topic offsets, business tables hoặc consumer group state ngoài metadata operations được mong đợi.

## 21. Các tình huống chẩn đoán phổ biến

| Quan sát | Diễn giải có thể | Hướng kiểm tra |
|---|---|---|
| Kafka health `DOWN`, listener container vẫn `RUNNING` | Container object còn chạy nhưng Admin connectivity đang lỗi | Broker/network/auth, client logs, reconnect |
| Kafka health `UP`, consumer không có assignment | Admin API hoạt động; group/consumer state có vấn đề hoặc chưa rebalance | Group state, subscription, partitions, ACL |
| Kafka health `UP`, producer send lỗi | Admin và producer capability khác nhau | Producer ACL, serializer, transaction, record size |
| Kafka health `UP`, consumer fetch lỗi | Consumer credentials/permissions khác Admin | READ ACL, group ACL, deserializer, poll |
| Kafka health `UP`, lag tăng | Consumer chậm, paused hoặc upstream tăng traffic | Processing timer, lag per partition, pause, DB |
| Kafka health `DOWN` chập chờn | Network/timeout hoặc probe threshold quá nhạy | Request latency, timeout, broker events |
| Readiness `DOWN`, liveness `UP` | Dependency/service capability không sẵn sàng nhưng process còn sống | Chính sách readiness và phục hồi dependency |
| Mọi Pod liveness restart khi Kafka outage | Kafka được đưa nhầm vào liveness hoặc health aggregation | Tách liveness khỏi dependency health |

Đừng dùng một `DOWN` để tự động restart ứng dụng trước khi biết failure thuộc process hay dependency. Restart có thể hữu ích với một số lỗi nội bộ, nhưng không sửa ACL sai hoặc broker outage.

## 22. Những sai lầm thường gặp

- **Coi Kafka health `UP` là consumer processing healthy:** indicator có thể chỉ kiểm tra Admin connectivity.
- **Coi Kafka health `DOWN` là JVM phải restart:** dependency bên ngoài có thể tạm thời unavailable.
- **Đưa Kafka vào liveness mặc định:** dễ tạo restart storm khi cluster lỗi.
- **Đưa Kafka vào readiness mà không xác định business contract:** có thể loại mọi Pod khỏi traffic dù một số chức năng vẫn hoạt động.
- **Cho rằng readiness `DOWN` tự stop Kafka listener:** health group và container lifecycle là hai cơ chế khác nhau.
- **Chỉ kiểm tra bootstrap endpoint:** metadata trả về có thể dẫn client tới broker khác đang unreachable.
- **Dùng AdminClient check để kết luận producer có quyền WRITE:** ACL có thể khác theo operation/topic.
- **Tạo AdminClient mới mỗi lần probe:** tăng connection churn và rò rỉ nếu không close.
- **Không đặt timeout hữu hạn:** health endpoint có thể treo và ảnh hưởng probes khác.
- **Đặt timeout quá ngắn:** health flapping dù cluster vẫn hoạt động bình thường.
- **Expose health details công khai:** lộ broker topology hoặc exception metadata.
- **Chỉ kiểm tra health endpoint một lần khi startup:** bỏ lỡ outage xảy ra sau đó.
- **Dùng health check để gửi business canary liên tục:** tạo side effect và tải không cần thiết.
- **Không test ACL khác nhau giữa Admin/Producer/Consumer:** health `UP` che giấu lỗi capability.
- **Dùng health indicator thay consumer lag và DLT metrics:** bỏ qua tiến độ và độ tin cậy nghiệp vụ.

## 23. Checklist production

Trước khi dùng Kafka health indicator để điều khiển deployment hoặc traffic, hãy xác định:

1. Health contributor Kafka có thực sự được auto-configure trong Spring Boot version này không?
2. Nó kiểm tra Admin cluster metadata hay capability nào khác?
3. AdminClient có dùng đúng bootstrap, SASL/SSL credentials và timeout không?
4. Producer và consumer có credentials/ACL khác với AdminClient không?
5. Kafka indicator có nên nằm trong readiness group không?
6. Nó có tuyệt đối cần thiết cho liveness không, và vì sao?
7. Với consumer-only worker, readiness HTTP ảnh hưởng rollout/traffic như thế nào?
8. Health endpoint có timeout hữu hạn và không chặn thread quá lâu không?
9. Có phân biệt `UP`, `DOWN`, `OUT_OF_SERVICE` và `UNKNOWN` phù hợp không?
10. Health details có được bảo vệ khỏi người dùng không có quyền không?
11. Có metric/log lịch sử cho health transitions và probe latency không?
12. Có consumer lag, assignment, producer errors, transaction failures và DLT metrics riêng không?
13. Có custom health indicator chỉ khi cần kiểm tra capability cụ thể không?
14. Synthetic produce/consume có dùng canary topic và chạy theo lịch thay vì mỗi probe không?
15. Đã kiểm thử broker outage, restart, auth failure, timeout, ACL và recovery bằng broker thật chưa?
16. Khi Kafka unavailable, process có thể tiếp tục sống và phục hồi mà không restart storm không?

**Health indicator cho Kafka connection** cung cấp một tín hiệu quan trọng về khả năng ứng dụng giao tiếp với Kafka cluster, thường qua KafkaAdmin/AdminClient. Nó giúp phát hiện dependency outage và tích hợp với Actuator/Kubernetes health groups, nhưng chỉ chứng minh những thao tác mà indicator thực sự thực hiện. Muốn đánh giá service có thể consume, produce và xử lý nghiệp vụ đúng hay không, cần bổ sung consumer assignment, lag, producer/transaction metrics, DLT status, business readiness và integration tests. Tách rõ connectivity, readiness và liveness sẽ giúp hệ thống phản ứng đúng với sự cố Kafka mà không biến một broker outage thành vòng lặp restart của toàn bộ ứng dụng.

