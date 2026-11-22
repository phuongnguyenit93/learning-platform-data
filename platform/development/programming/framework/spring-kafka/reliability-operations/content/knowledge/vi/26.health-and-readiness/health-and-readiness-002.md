# Readiness khi broker chưa sẵn sàng

Một ứng dụng Spring Kafka có thể khởi động được JVM và Spring ApplicationContext trong khi **Kafka broker vẫn chưa sẵn sàng nhận kết nối hoặc xử lý request**. Tình huống này thường xảy ra khi Kubernetes khởi động application pod trước broker, broker đang rolling restart, DNS/network chưa ổn định, cluster vừa phục hồi sau sự cố hoặc Kafka authentication/authorization chưa hoạt động đúng.

Trong production, **process đã chạy không có nghĩa service đã sẵn sàng phục vụ**. Readiness phải phản ánh khả năng thực hiện công việc mà instance được giao. Nếu một service không thể tiếp nhận hoặc xử lý message khi Kafka unavailable, nó không nên được đánh dấu ready chỉ vì HTTP server đã mở cổng.

Tuy nhiên, readiness cũng phải được thiết kế đúng phạm vi: **broker unavailable không phải lý do để liveness probe thất bại và Kubernetes liên tục restart pod**. Broker là dependency bên ngoài; restart application không làm broker khỏe hơn. Với Spring Kafka, cần phân biệt application startup, broker connectivity, listener container running, consumer group assignment, producer capability và business dependency health.

Bài học này trình bày cách thiết kế readiness khi broker chưa sẵn sàng, dùng Spring Boot Actuator và Kafka AdminClient để kiểm tra broker có giới hạn thời gian, phối hợp trạng thái consumer assignment, phân biệt readiness/liveness/startup probes, quản lý retry/recovery, tránh probe flapping và kiểm thử các tình huống broker outage.

## 1. Process started không đồng nghĩa service ready

Một ứng dụng Spring Boot có thể đi qua các giai đoạn:

~~~text
JVM started
    |
    v
Spring ApplicationContext initialized
    |
    v
HTTP server started
    |
    v
Kafka listener containers start
    |
    v
Kafka broker reachable
    |
    v
Consumer group assigned required partitions
    |
    v
Business dependencies ready
    |
    v
Application ready
~~~

Những mốc này khác nhau:

- **Started**: process/JVM đã chạy.
- **Application context ready**: Spring đã tạo beans và hoàn thành giai đoạn khởi tạo tương ứng.
- **HTTP accepting connections**: web server có thể nhận request.
- **Kafka reachable**: application có thể liên hệ broker/cluster theo phép kiểm tra đã chọn.
- **Listener assigned**: consumer đã gia nhập group và nhận partitions cần thiết.
- **Business ready**: database, schema, credentials và các dependency cần cho xử lý message đã sẵn sàng.

Nếu Kubernetes chỉ kiểm tra HTTP port hoặc một endpoint trả 200 ngay sau khi web server mở, pod có thể vào Service endpoints trong khi Kafka broker vẫn unavailable.

Readiness cần trả lời một câu hỏi cụ thể: **instance này có thể thực hiện đúng vai trò hiện tại mà không nhận thêm công việc mà nó không thể xử lý an toàn hay không?**

## 2. Readiness, liveness và startup probe khác nhau

Kubernetes cung cấp ba loại probe có mục tiêu riêng:

| Probe | Câu hỏi | Khi thất bại, Kubernetes làm gì? |
|---|---|---|
| **Startup** | Ứng dụng đã hoàn tất giai đoạn khởi động cho phép kiểm tra tiếp chưa? | Tiếp tục kiểm tra startup; nếu vượt ngưỡng thất bại, container có thể bị restart |
| **Readiness** | Pod có nên nhận traffic/công việc mới không? | Đánh dấu pod NotReady và loại khỏi Service endpoints |
| **Liveness** | Process có còn sống và có khả năng tự phục hồi không? | Restart container sau khi vượt ngưỡng thất bại |

Với Kafka dependency:

- **Readiness** có thể thất bại khi broker chưa sẵn sàng nếu Kafka là dependency bắt buộc cho vai trò của service.
- **Liveness** thường không nên phụ thuộc trực tiếp vào Kafka broker.
- **Startup probe** giúp application có thời gian khởi động và chờ dependency trong một khoảng giới hạn mà chưa bị liveness probe restart sớm.

Ví dụ tình huống:

~~~text
Kafka broker đang rolling restart
       |
       v
Spring Boot application vẫn chạy bình thường
       |
       +-- readiness -> DOWN
       |
       +-- liveness  -> UP
       |
       v
Kubernetes giữ pod chạy nhưng không đưa HTTP traffic mới vào
       |
       v
Broker phục hồi
       |
       v
Readiness -> UP
~~~

Điều này tránh **restart storm** khi một dependency dùng chung gặp sự cố.

## 3. Readiness có tác động gì với Kafka consumer?

Một điểm quan trọng: Kubernetes readiness probe chủ yếu điều khiển việc pod có được đưa vào **Service endpoints** hay không. Nó **không tự dừng Kafka listener container**.

Nếu một consumer application đánh dấu NotReady trong khi Kafka broker vẫn reachable, listener container có thể tiếp tục consume records bình thường. Điều đó có thể đúng hoặc sai tùy yêu cầu nghiệp vụ.

~~~text
Pod NotReady với Kubernetes Service
       |
       +-- HTTP traffic mới không được route tới pod
       |
       +-- Kafka listener vẫn đang RUNNING
               |
               +-- tiếp tục poll và xử lý records
~~~

Vì vậy phải xác định readiness dùng cho mục tiêu nào:

1. **HTTP readiness**: instance có thể phục vụ API request hay không.
2. **Kafka consumer readiness**: listener có broker connectivity, assignment và dependencies cần thiết hay không.
3. **Producer readiness**: ứng dụng có thể publish theo yêu cầu nghiệp vụ hay không.
4. **Combined application readiness**: tất cả khả năng bắt buộc cho vai trò service đều sẵn sàng.

Nếu consumer phải ngừng nhận records khi database quá tải, chỉ trả readiness DOWN là chưa đủ. Cần phối hợp **pause/resume container** hoặc cơ chế điều khiển consumption riêng, với acknowledgment/offset semantics an toàn.

## 4. Những lý do broker có thể chưa sẵn sàng

Không phải mọi lỗi kết nối Kafka đều giống nhau:

| Nguyên nhân | Dấu hiệu có thể thấy | Hành động |
|---|---|---|
| Broker process chưa start | Connection refused / timeout | Chờ retry có giới hạn và giữ readiness DOWN |
| DNS chưa phân giải được | Unknown host / resolution error | Kiểm tra service discovery và DNS |
| Network policy/firewall | Timeout hoặc connection failure | Kiểm tra network path |
| Kafka metadata chưa ổn định | Broker/controller metadata errors | Chờ cluster ổn định và quan sát |
| TLS handshake lỗi | SSL handshake exception | Kiểm tra truststore/certificate |
| SASL authentication lỗi | Authentication exception | Kiểm tra mechanism, credentials, JAAS |
| ACL thiếu quyền | Topic/group/cluster authorization exception | Cấp quyền đúng; không retry vô hạn |
| Topic chưa tồn tại | Unknown topic/partition hoặc metadata timeout | Kiểm tra provisioning và missing-topic policy |
| Transaction coordinator chưa sẵn sàng | Transaction initialization/commit failure | Kiểm tra coordinator và producer transaction state |
| Broker reachable nhưng dependency nghiệp vụ lỗi | Consumer poll được nhưng DB/API không dùng được | Readiness cần phản ánh business dependency riêng |

Một probe chỉ kiểm tra bootstrap broker có phản hồi metadata **không chứng minh mọi thao tác Kafka đều thành công**. Ví dụ AdminClient có thể mô tả cluster nhưng producer không có quyền ghi topic hoặc consumer không có quyền join group.

## 5. Đừng làm liveness phụ thuộc broker

Một cấu hình nguy hiểm:

~~~text
Liveness:
  Kafka broker reachable?

Broker DOWN
  -> liveness DOWN
  -> Kubernetes restart application
  -> application reconnect
  -> broker vẫn DOWN
  -> liveness DOWN
  -> restart tiếp
~~~

Kết quả có thể là:

- Application liên tục restart dù code không lỗi.
- Consumer group churn và rebalance khi broker phục hồi.
- Producer/consumer connection storm.
- Log và metrics bị tăng đột biến.
- Thời gian phục hồi tổng thể dài hơn.

**Liveness nên kiểm tra process/application có bị kẹt hoặc hỏng nội bộ hay không**, chẳng hạn event loop chết, deadlock nghiêm trọng hoặc health mechanism nội bộ không phản hồi.

Broker outage thường là tình trạng dependency bên ngoài mà application cần chờ phục hồi. Đưa nó vào liveness sẽ khiến Kubernetes xử lý sai tầng.

Một quy tắc hữu ích:

~~~text
Broker unavailable:
  readiness = DOWN
  liveness  = UP
~~~

Đây là mặc định hợp lý cho service phụ thuộc Kafka, nhưng readiness cụ thể còn phụ thuộc vai trò và degraded mode mà ứng dụng hỗ trợ.

## 6. Spring Boot Actuator health probes

Spring Boot Actuator cung cấp health infrastructure và các health groups cho readiness/liveness ở những phiên bản hỗ trợ Kubernetes probes.

Cấu hình ví dụ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,kafkaBroker
        liveness:
          include: livenessState
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Trong ví dụ:

- **readinessState** phản ánh ReadinessState do Spring Boot quản lý.
- **kafkaBroker** là custom HealthIndicator do ứng dụng cung cấp.
- **livenessState** phản ánh LivenessState.

Tên health contributor trong include list phải khớp với bean name/health contributor thực tế. Nếu bean được đặt tên kafkaBrokerHealthIndicator, Spring Boot thường nhận diện contributor ID tương ứng là **kafkaBroker**.

Các property và probe defaults thay đổi theo Spring Boot version. Cần kiểm tra dependency version của dự án trước khi áp dụng nguyên văn YAML.

Không include kafkaBroker vào liveness group chỉ vì muốn Kubernetes restart ứng dụng khi Kafka outage.

## 7. Tạo một AdminClient dùng lâu dài cho broker health

Một cách kiểm tra broker là dùng Kafka **AdminClient.describeCluster()**. Không nên tạo và đóng một AdminClient mới trong mỗi lần health check; hãy quản lý một client bean có lifecycle rõ ràng.

Ví dụ dùng cấu hình đã được Spring Kafka **KafkaAdmin** quản lý:

~~~java
@Configuration
public class KafkaReadinessConfiguration {

    @Bean(destroyMethod = "close")
    AdminClient readinessAdminClient(KafkaAdmin kafkaAdmin) {
        return AdminClient.create(
                kafkaAdmin.getConfigurationProperties());
    }
}
~~~

Ví dụ cần imports:

~~~java
import org.apache.kafka.clients.admin.AdminClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaAdmin;
~~~

KafkaAdmin cung cấp cấu hình AdminClient của ứng dụng ở các phiên bản Spring Kafka hỗ trợ API này. Cần xác nhận đúng version đang dùng và đảm bảo cấu hình có bootstrap servers, TLS/SASL và các thuộc tính bảo mật cần thiết.

Client được đóng khi Spring context shutdown nhờ **destroyMethod="close"**. Nếu application có nhiều Kafka clusters, nên quản lý một AdminClient/health contributor riêng cho từng cluster alias.

Không dùng một AdminClient bean cho một cluster rồi kiểm tra nó như bằng chứng mọi Kafka clusters trong ứng dụng đều khỏe.

## 8. HealthIndicator kiểm tra broker với timeout

Một custom HealthIndicator:

~~~java
@Component("kafkaBrokerHealthIndicator")
public class KafkaBrokerHealthIndicator implements HealthIndicator {

    private final AdminClient adminClient;
    private final long timeoutMillis;

    public KafkaBrokerHealthIndicator(AdminClient adminClient) {
        this.adminClient = adminClient;
        this.timeoutMillis = 2_000L;
    }

    @Override
    public Health health() {
        try {
            Collection<Node> nodes = adminClient.describeCluster()
                    .nodes()
                    .get(timeoutMillis, TimeUnit.MILLISECONDS);

            if (nodes == null || nodes.isEmpty()) {
                return Health.down()
                        .withDetail("reason", "no_brokers_discovered")
                        .build();
            }

            return Health.up()
                    .withDetail("brokerCount", nodes.size())
                    .build();
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return Health.down()
                    .withDetail("reason", "probe_interrupted")
                    .build();
        }
        catch (Exception ex) {
            return Health.down()
                    .withDetail("reason", "broker_unavailable")
                    .withDetail("errorType", ex.getClass().getSimpleName())
                    .build();
        }
    }
}
~~~

Các imports chính:

~~~java
import java.util.Collection;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.common.Node;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;
~~~

Điểm quan trọng:

- **AdminClient được tái sử dụng**, không tạo theo mỗi request.
- **Timeout hữu hạn** để health endpoint không bị treo lâu khi broker unavailable.
- Khi thread bị interrupt, khôi phục interrupt flag.
- Health detail chỉ ghi loại lỗi tổng quát, tránh lộ credentials, SASL details hoặc connection strings.
- Không ghi nguyên exception message vào response health endpoint công khai.

Timeout 2 giây chỉ là ví dụ. Nó phải ngắn hơn probe timeout và phù hợp latency của cluster. Kafka AdminClient cũng có request/default API timeouts riêng; cần đặt chúng nhất quán để các lời gọi không giữ tài nguyên quá lâu.

## 9. Probe broker thực sự kiểm tra điều gì?

Đoạn code trên gọi **describeCluster().nodes()**. Nếu trả về danh sách broker, ứng dụng đã có thể lấy metadata cluster theo quyền và cấu hình AdminClient hiện tại.

Nó cung cấp bằng chứng cho:

- DNS/network path tới bootstrap brokers hoạt động đủ để lấy metadata.
- Kafka cluster phản hồi request mô tả cluster.
- Credentials/ACL cho thao tác metadata này có hiệu lực.
- Có broker nodes được khám phá.

Nó **không chứng minh**:

- Consumer group đã được assign partitions.
- Consumer có quyền đọc mọi topic cần thiết.
- Producer có quyền ghi vào mọi topic.
- Transaction coordinator sẵn sàng cho transactional producer.
- Topic cụ thể đã tồn tại hoặc có đúng partition count.
- Database/API dependencies của business handler khỏe.
- Một record thực tế có thể được xử lý end-to-end.

Vì vậy, đặt tên health indicator là **kafkaBroker** hoặc **kafkaClusterMetadata**, không nên đặt là businessReady nếu nó chỉ kiểm tra broker metadata.

## 10. Timeout và tác động của health probe

Health endpoints có thể được Kubernetes gọi thường xuyên. Nếu mỗi request tạo một Kafka AdminClient mới và chờ broker timeout dài, chính probe sẽ tạo thêm tải trong lúc broker đang gặp sự cố.

~~~text
Kubernetes probes:
  10 pods
  mỗi pod probe mỗi 5 giây
  mỗi probe tạo AdminClient mới
  broker không phản hồi trong 10 giây

=> nhiều kết nối và request pending cùng lúc
~~~

Các biện pháp:

1. Dùng một AdminClient được quản lý lâu dài.
2. Đặt timeout hữu hạn cho từng health check.
3. Không chạy nhiều describeCluster request chồng lấn không giới hạn.
4. Cân nhắc cache kết quả trong một khoảng ngắn hoặc cập nhật health state bằng background probe.
5. Giới hạn chi tiết trả về trong health response.
6. Không chạy health check quá thường xuyên so với khả năng phục hồi của broker.

Health check phải đủ nhạy để phát hiện outage nhưng không được trở thành nguồn tạo connection storm.

## 11. HealthIndicator đồng bộ hay background probe?

Có hai cách tổ chức:

### Probe đồng bộ khi health endpoint được gọi

Mỗi lần Actuator health check gọi health(), code thực hiện AdminClient request với timeout.

Ưu điểm:

- Trạng thái gần với kết quả kiểm tra mới nhất.
- Cấu trúc đơn giản.
- Ít state riêng phải đồng bộ.

Nhược điểm:

- Probe endpoint có thể chậm khi broker/network chậm.
- Nhiều pods cùng probe có thể tạo nhiều request.
- Kubernetes gọi probe thường xuyên có thể gây tải không cần thiết.

### Background probe cập nhật cached state

Một scheduled task kiểm tra broker theo chu kỳ, lưu kết quả và HealthIndicator chỉ đọc state đã cập nhật.

~~~text
Scheduled probe
     |
     v
AdminClient.describeCluster()
     |
     v
Broker result
     |
     v
Atomic readiness snapshot
     |
     v
Actuator health endpoint đọc snapshot
~~~

Ưu điểm:

- Health endpoint trả lời nhanh và ổn định.
- Có thể giới hạn tần suất gọi broker.
- Dễ áp dụng hysteresis và consecutive failure thresholds.

Nhược điểm:

- Trạng thái có độ trễ so với thực tế.
- Phải quản lý stale result và startup state.
- Background task cần timeout và lifecycle rõ.

Với hệ thống nhiều replicas hoặc probe interval ngắn, **background probe với cached state** thường phù hợp hơn, miễn là có giới hạn tuổi dữ liệu và xử lý stale state.

## 12. Trạng thái chưa từng probe phải là NOT READY

Khi ứng dụng vừa khởi động, background probe có thể chưa chạy lần đầu. Không nên mặc định broker healthy chỉ vì chưa có lỗi.

Một state model:

~~~text
UNKNOWN
  |
  +-- probe success -> UP
  |
  +-- probe failure -> DOWN

UP
  |
  +-- consecutive failures vượt threshold -> DOWN

DOWN
  |
  +-- consecutive successes đạt threshold -> UP
~~~

Trong đó:

- **UNKNOWN**: chưa có kết quả đáng tin cậy.
- **UP**: probe gần đây thành công.
- **DOWN**: probe gần đây thất bại đủ điều kiện.

Readiness khi state UNKNOWN nên trả **OUT_OF_SERVICE hoặc DOWN**, tùy policy. Không đánh dấu UP trước khi có kết quả đầu tiên.

Một snapshot có thể lưu:

~~~text
status: UNKNOWN | UP | DOWN
lastSuccessAt: timestamp
lastProbeAt: timestamp
consecutiveFailures: integer
consecutiveSuccesses: integer
lastErrorCategory: bounded value
~~~

Không lưu exception message hoặc credentials trong readiness snapshot.

## 13. Hysteresis tránh readiness flapping

Nếu readiness đổi UP/DOWN chỉ vì một lần timeout ngắn, Kubernetes Service endpoints có thể liên tục thêm/bớt pod.

Ví dụ policy:

~~~text
UP:
  1 probe failure -> giữ UP
  3 failures liên tiếp -> DOWN

DOWN:
  1 probe success -> vẫn DOWN
  2 successes liên tiếp -> UP
~~~

Các ngưỡng chỉ là ví dụ. Chọn dựa trên:

- Broker outage SLO.
- Probe interval và timeout.
- Consumer reconnect behavior.
- Mức độ chấp nhận xử lý degraded mode.
- Tác động khi pod rời/nhập Service endpoints.

**Không trì hoãn DOWN quá lâu** nếu instance thật sự không thể xử lý message an toàn. Hysteresis giúp bỏ qua nhiễu ngắn, không phải che giấu outage kéo dài.

## 14. Kubernetes probe configuration

Ví dụ Deployment:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: orders-service
          image: example/orders-service:1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Ví dụ giả định Actuator health probe paths được bật và endpoint được expose đúng. Các giá trị period/timeout/failureThreshold cần điều chỉnh theo SLO và thời gian khởi động thực tế.

Startup probe dùng liveness endpoint để xác nhận application process đã khởi động; nó **không chờ Kafka healthy**. Sau khi startup probe thành công, readiness mới quyết định pod có nhận traffic hay không, còn liveness tiếp tục kiểm tra process health.

Nếu dùng Spring Boot version không tự expose các health probe paths, cần bật probes hoặc cấu hình endpoint paths phù hợp.

## 15. Readiness group nên include những gì?

Một service có thể có nhiều dependency:

~~~text
orders-service
  |
  +-- database
  +-- Kafka cluster
  +-- schema registry
  +-- payment API
  +-- object storage
~~~

Không nên include mọi dependency vào readiness chỉ vì có HealthIndicator cho nó. Cần xác định dependency nào thực sự bắt buộc để instance phục vụ vai trò hiện tại.

Ví dụ:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,kafkaBroker,database
        liveness:
          include: livenessState
~~~

Nếu ứng dụng vẫn có thể phục vụ HTTP GET read-only khi Kafka unavailable, nhưng không thể nhận lệnh tạo đơn hàng, một **global readiness** phụ thuộc Kafka có thể loại pod khỏi toàn bộ HTTP Service quá rộng. Có thể thiết kế health group/endpoint theo chức năng hoặc trả trạng thái degraded ở API.

Ngược lại, nếu mọi request của service đều cần publish Kafka event để bảo đảm consistency, Kafka có thể là dependency bắt buộc của readiness.

**Readiness là quyết định theo vai trò**, không phải một danh sách dependencies luôn giống nhau cho mọi service.

## 16. Broker reachable chưa có nghĩa consumer ready

Một AdminClient probe có thể trả UP trong khi consumer chưa nhận partition assignment.

~~~text
AdminClient:
  describeCluster() -> success

KafkaListenerContainer:
  isRunning() -> true
  consumer group -> chưa assigned partition

Business processing:
  chưa thể xử lý records
~~~

Nguyên nhân có thể:

- Consumer group chưa join thành công.
- Topic chưa tồn tại hoặc không có partitions.
- ACL cho group/topic thiếu.
- Rebalance chưa hoàn tất.
- Consumer đang paused.
- Consumer instance chưa được broker chấp nhận do authentication/configuration.

Với service có trách nhiệm **consume** một topic bắt buộc, readiness có thể cần kiểm tra thêm **assignment readiness**.

Không dùng isRunning() làm bằng chứng consumer đã sẵn sàng. Running chỉ cho biết container lifecycle đang chạy; nó không xác nhận group đã giao partition.

## 17. Theo dõi assignment bằng ConsumerAwareRebalanceListener

Spring Kafka cung cấp **ConsumerAwareRebalanceListener** để nhận callbacks khi partitions được assign/revoke. Có thể dùng callbacks này cập nhật trạng thái assignment:

~~~java
@Component
public class OrdersAssignmentTracker
        implements ConsumerAwareRebalanceListener {

    private final AssignedPartitionRegistry registry;

    public OrdersAssignmentTracker(AssignedPartitionRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        registry.assigned(consumer, partitions);
    }

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        registry.revoked(consumer, partitions);
    }
}
~~~

Đây là code minh họa: AssignedPartitionRegistry là thành phần ứng dụng cần triển khai thread-safe. Nếu Spring Kafka version hỗ trợ callback onPartitionsLost, registry cũng cần xóa ownership khi consumer mất partition mà không có revoke bình thường.

Đăng ký listener:

~~~java
factory.getContainerProperties()
        .setConsumerRebalanceListener(ordersAssignmentTracker);
~~~

Khi dùng concurrent container, nhiều child consumers có thể gọi callbacks trên các threads khác nhau. Registry phải phân biệt consumer/container identity và chỉ thêm/xóa partitions tương ứng.

Không chỉ lưu một AtomicBoolean assigned toàn cục được đặt true khi **bất kỳ** child nào nhận partition. Parent có thể có child chưa sẵn sàng, hoặc partition bị revoke ngay sau đó.

## 18. Xác định assignment readiness thế nào?

Một policy đơn giản cho consumer group:

~~~text
Required topic:
  orders.commands

Expected partitions:
  6

Observed assigned partitions:
  consumer 0 -> P0, P1
  consumer 1 -> P2, P3
  consumer 2 -> P4, P5

Assigned coverage:
  6 / 6

Consumer group assignment readiness:
  READY
~~~

Tuy nhiên, **mọi partitions được assign trong group không nhất thiết phải nằm trên một instance**. Nếu group có nhiều replicas, mỗi pod chỉ nhận một phần partitions. Vì vậy không thể yêu cầu mỗi pod phải sở hữu đủ toàn bộ partition count của topic.

Các policy có thể là:

- **At least one partition assigned** cho consumer instance cần thực sự consume.
- **Expected assignment per child** dựa trên concurrency và group assignment.
- **Group-level coverage** được đo qua một hệ thống quan sát riêng, không thể kết luận đầy đủ từ một pod đơn lẻ.
- **Listener container running + no fatal startup/auth error + at least one assignment** cho readiness ở cấp pod.

Chọn policy theo kiến trúc group và khả năng phân phối partitions. Với instance hợp lệ nhưng không có partition do số replicas lớn hơn partitions, việc đánh dấu NotReady có thể gây scale/rebalance loop.

## 19. Assignment readiness và rebalance

Khi rebalance, một consumer có thể tạm thời mất assignment trước khi nhận assignment mới. Nếu readiness chuyển DOWN/UP ngay theo mỗi callback, pod có thể flapping trong quá trình deploy hoặc scale.

~~~text
Assigned
   |
   v
Rebalance begins
   |
   v
Partitions revoked
   |
   v
No assignment temporarily
   |
   v
Partitions assigned again
   |
   v
Ready
~~~

Một policy có thể dùng grace period ngắn cho rebalance dự kiến, nhưng phải có timeout để không giữ readiness UP vô thời hạn khi consumer thực sự mất ownership.

Đừng coi onPartitionsRevoked là bằng chứng broker unavailable. Rebalance là hoạt động group lifecycle bình thường.

Với cooperative rebalance, consumer có thể chỉ revoke một phần partitions và vẫn giữ các partitions khác. Assignment tracker phải cập nhật đúng tập được truyền vào callback, không xóa toàn bộ trạng thái parent.

## 20. Readiness của producer khác consumer

Một ứng dụng chỉ publish Kafka có thể không có listener consumer. Với producer-only service, assignment readiness không có ý nghĩa.

Producer readiness có thể cần xác nhận:

- Broker metadata reachable.
- Producer factory có thể khởi tạo producer.
- Serializer/configuration hợp lệ.
- ACL cho phép ghi topic bắt buộc.
- Nếu transactional, transaction coordinator và transactional ID hoạt động.

**AdminClient.describeCluster() không kiểm tra quyền produce**. Có thể broker UP nhưng producer bị TopicAuthorizationException khi gửi vào topic.

Một số hệ thống dùng **canary message** tới health topic để kiểm tra đường publish thực tế. Cần thiết kế cẩn thận:

- Dùng topic riêng, key/event type riêng và consumer xác nhận tương ứng.
- Định danh canary để không bị business listener xử lý như đơn hàng thật.
- Có timeout và cleanup/retention.
- Không gửi canary liên tục theo mỗi health probe.
- Đánh giá tác động của transactional producer nếu đường publish dùng transaction.

Không gửi message giả vào topic nghiệp vụ để chứng minh readiness; điều đó có thể kích hoạt side effects thật.

## 21. Consumer readiness không phải producer readiness

Một service có cả consumer và producer:

~~~text
orders-service
  |
  +-- consume orders.commands
  |
  +-- process order
  |
  +-- produce orders.events
~~~

Nếu broker metadata reachable nhưng consumer ACL thiếu, producer vẫn có thể hoạt động. Nếu consumer có thể đọc nhưng producer ACL thiếu, listener vẫn nhận record nhưng không hoàn tất output.

Readiness tổng thể cần xác định khả năng nào bắt buộc:

~~~text
broker metadata reachable
       AND
required consumer assignment ready
       AND
required produce capability ready
       AND
database ready
       |
       v
application ready
~~~

Đối với producer transactions, một lần describe cluster không đủ chứng minh transaction commit thành công. Có thể cần integration/canary validation riêng hoặc chỉ phát hiện qua producer transaction health/error metrics.

Không chạy một transaction canary trên mỗi liveness/readiness probe; việc đó có thể tạo producer churn, transaction coordinator load và dữ liệu không mong muốn.

## 22. Listener container start khi broker chưa sẵn sàng

Spring Kafka listener container có thể được khởi động khi Spring context hoàn tất. Nếu broker unavailable, Kafka consumer có thể gặp lỗi kết nối trong poll/reconnect path và thử lại theo client behavior/configuration.

Một số điều cần phân biệt:

- Container bean đã được start.
- Consumer object đã được tạo.
- Consumer đã kết nối và lấy metadata.
- Consumer đã join group.
- Consumer đã nhận partitions.
- Listener đã xử lý được record.

Không phải mọi trạng thái đều được biểu diễn bởi một boolean isRunning().

Trong một outage ngắn, thường nên cho application và container tiếp tục lifecycle để Kafka client tự reconnect, đồng thời readiness phản ánh broker chưa sẵn sàng. Nếu container tự dừng vì lỗi fatal (ví dụ cấu hình authentication/authorization hoặc lỗi khởi tạo không retry theo policy), readiness cần phản ánh listener thực sự không hoạt động và operator cần điều tra.

Không tự restart listener liên tục chỉ vì broker connection timeout. Restart không thay thế reconnect/backoff của Kafka client.

## 23. Authentication và authorization cần policy riêng

Broker reachable nhưng credentials sai là tình huống khác với broker chưa start.

| Lỗi | Có nên chờ tự phục hồi? |
|---|---|
| Broker connection refused trong lúc rollout | Thường có, với retry và readiness DOWN |
| Temporary network timeout | Thường có, với backoff |
| DNS tạm thời lỗi | Có thể chờ và quan sát |
| Invalid SASL credentials | Không nên retry vô hạn như lỗi tạm thời |
| TLS truststore/certificate sai | Cần sửa cấu hình/certificate |
| Topic authorization denied | Cần sửa ACL |
| Consumer group authorization denied | Cần sửa ACL |

Spring Kafka có cấu hình liên quan **authExceptionRetryInterval** cho listener container trong các phiên bản hỗ trợ. Nếu cấu hình phù hợp, một số authentication/authorization exceptions có thể được retry theo interval thay vì dừng container ngay.

Không bật retry vô hạn cho credentials sai mà không có alert; readiness sẽ DOWN liên tục nhưng operator có thể không biết root cause.

Health response nên trả error category như **authentication**, **authorization**, **network** hoặc **metadata_timeout**, thay vì lộ nguyên exception message có thể chứa thông tin nhạy cảm.

## 24. Missing topic không đồng nghĩa broker unavailable

Broker có thể UP nhưng topic mà listener subscribe chưa tồn tại.

Spring Kafka có **missingTopicsFatal** trên container properties trong các phiên bản hỗ trợ. Thuộc tính này quyết định hành vi khi topic listener yêu cầu không tồn tại trong giai đoạn kiểm tra tương ứng.

~~~java
factory.getContainerProperties()
        .setMissingTopicsFatal(true);
~~~

Đây là một lựa chọn fail-fast khi topic là dependency bắt buộc và thiếu topic được xem là cấu hình/provisioning error. Nhưng nếu topic được tạo sau khi application start, policy cần phù hợp với quy trình provisioning.

Không nhầm:

- **Broker unavailable**: không thể liên hệ cluster.
- **Topic missing**: cluster reachable nhưng resource chưa tồn tại.
- **Topic authorization denied**: resource có thể tồn tại nhưng client không có quyền.
- **No partition assigned**: group/assignment state chưa sẵn sàng.

Readiness có thể DOWN trong cả bốn trường hợp, nhưng error category và cách khắc phục khác nhau.

## 25. Không phụ thuộc startup fail-fast vào Kafka nếu muốn phục hồi linh hoạt

Một lựa chọn là bắt application startup thất bại ngay khi Kafka unavailable. Cách này có thể phù hợp khi:

- Application không có chức năng nào hữu ích nếu không có Kafka.
- Deployment/orchestrator có retry/backoff phù hợp.
- Kafka availability là điều kiện bắt buộc để hoàn tất initialization.
- Không muốn process tồn tại trong trạng thái degraded.

Nhưng trong nhiều môi trường Kubernetes, **để application start, readiness DOWN và chờ Kafka phục hồi** có thể tốt hơn:

- Pod không bị restart liên tục.
- Logs/metrics vẫn có thể quan sát qua management endpoints.
- Spring Kafka client có thể reconnect theo policy.
- Khi broker phục hồi, readiness có thể chuyển UP mà không cần redeploy.

Không có một lựa chọn duy nhất cho mọi ứng dụng. Quan trọng là startup policy, retry behavior và Kubernetes probes phải nhất quán.

## 26. ApplicationAvailability và ReadinessState

Spring Boot cung cấp **ApplicationAvailability** và **AvailabilityChangeEvent** để quản lý trạng thái readiness/liveness.

Readiness states thường gồm:

- **ACCEPTING_TRAFFIC**: ứng dụng sẵn sàng nhận traffic.
- **REFUSING_TRAFFIC**: ứng dụng chưa sẵn sàng hoặc đang shutdown.

Có thể chủ động đổi trạng thái:

~~~java
@Component
public class KafkaReadinessStatePublisher {

    private final ApplicationContext applicationContext;

    public KafkaReadinessStatePublisher(
            ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public void refuseTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.REFUSING_TRAFFIC);
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Các imports chính:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;
~~~

Ví dụ minh họa cách publish readiness state. Cần lưu ý **ReadinessState là trạng thái toàn application**, nên một controller không được tùy tiện đặt ACCEPTING_TRAFFIC khi một dependency khác vẫn đang yêu cầu REFUSING_TRAFFIC.

Với nhiều lý do readiness, nên có một coordinator tính toán trạng thái tổng hợp từ các conditions thay vì để mỗi HealthIndicator tự phát event và ghi đè lẫn nhau.

## 27. HealthIndicator và AvailabilityChangeEvent khác nhau

Hai cơ chế có thể cùng tham gia readiness nhưng không giống nhau:

| Cơ chế | Vai trò |
|---|---|
| **HealthIndicator** | Trả kết quả UP/DOWN/OUT_OF_SERVICE/UNKNOWN cho một dependency hoặc component |
| **Health group** | Tổng hợp nhiều health contributors thành endpoint/group |
| **ReadinessState** | Trạng thái ứng dụng có chấp nhận traffic không |
| **AvailabilityChangeEvent** | Thông báo/thay đổi trạng thái availability |
| **Kubernetes readiness probe** | Đọc endpoint để quyết định pod có nằm trong Service endpoints hay không |

Nếu readiness group include readinessState,kafkaBroker, broker HealthIndicator DOWN có thể làm group readiness DOWN dù ReadinessState vẫn ACCEPTING_TRAFFIC. Đây là một mô hình tổng hợp rõ ràng.

Nếu muốn dùng AvailabilityChangeEvent để cập nhật readiness state, cần coordinator lắng nghe broker state và publish transitions. Khi đó group có thể include readinessState cùng các thành phần khác tùy policy.

Không nhất thiết phải sử dụng cả hai cách cùng lúc. Tránh tạo hai nguồn sự thật mâu thuẫn.

## 28. Ví dụ cached broker health state

Một background probe có thể lưu kết quả trong một bean:

~~~java
public record BrokerHealthSnapshot(
        boolean known,
        boolean available,
        Instant lastProbeAt,
        String errorCategory) {
}
~~~

Một component kiểm tra theo chu kỳ:

~~~java
@Component
public class BrokerHealthMonitor {

    private final AdminClient adminClient;
    private final AtomicReference<BrokerHealthSnapshot> snapshot =
            new AtomicReference<>(
                    new BrokerHealthSnapshot(
                            false, false, Instant.EPOCH, "not_probed"));

    public BrokerHealthMonitor(AdminClient adminClient) {
        this.adminClient = adminClient;
    }

    @Scheduled(fixedDelay = 5_000L)
    public void probe() {
        try {
            Collection<Node> nodes = adminClient.describeCluster()
                    .nodes()
                    .get(2, TimeUnit.SECONDS);

            boolean available = nodes != null && !nodes.isEmpty();
            snapshot.set(new BrokerHealthSnapshot(
                    true,
                    available,
                    Instant.now(),
                    available ? "none" : "no_brokers_discovered"));
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            snapshot.set(new BrokerHealthSnapshot(
                    true, false, Instant.now(), "interrupted"));
        }
        catch (Exception ex) {
            snapshot.set(new BrokerHealthSnapshot(
                    true, false, Instant.now(), "broker_unavailable"));
        }
    }

    public BrokerHealthSnapshot current() {
        return snapshot.get();
    }
}
~~~

Đây là ví dụ tối giản để minh họa background probe và snapshot thread-safe. Production cần bổ sung:

- Consecutive failure/success thresholds.
- Stale snapshot timeout.
- Metrics và logs cho lỗi.
- Chống probe overlap nếu request trước chưa kết thúc.
- Quản lý shutdown và exception classification.

**Không coi một snapshot cũ là healthy vô thời hạn**. Nếu lastProbeAt quá lâu so với policy, health state nên trở thành UNKNOWN/DOWN.

## 29. HealthIndicator đọc cached snapshot

Health endpoint có thể chỉ đọc snapshot:

~~~java
@Component("kafkaBrokerHealthIndicator")
public class CachedKafkaBrokerHealthIndicator
        implements HealthIndicator {

    private final BrokerHealthMonitor monitor;

    public CachedKafkaBrokerHealthIndicator(
            BrokerHealthMonitor monitor) {
        this.monitor = monitor;
    }

    @Override
    public Health health() {
        BrokerHealthSnapshot state = monitor.current();

        if (!state.known() || !state.available()) {
            return Health.down()
                    .withDetail("errorCategory", state.errorCategory())
                    .withDetail("lastProbeAt", state.lastProbeAt())
                    .build();
        }

        return Health.up()
                .withDetail("lastProbeAt", state.lastProbeAt())
                .build();
    }
}
~~~

Ví dụ dùng boolean snapshot để đơn giản hóa. Nếu cần phân biệt UNKNOWN và DOWN, có thể trả Health.unknown() cho state chưa probe hoặc stale, tùy cách health group và Kubernetes diễn giải.

Đối với readiness, trạng thái chưa xác minh thường nên được coi là **chưa ready**. Đối với liveness, cached broker health không nên được include.

## 30. Hysteresis cho broker readiness

Một probe có thể timeout ngắn do GC pause, network jitter hoặc broker leader election. Chuyển readiness UP/DOWN ngay theo từng lần probe có thể gây flapping.

Ví dụ policy:

~~~text
State = UP
  failure #1 -> giữ UP
  failure #2 -> giữ UP
  failure #3 -> DOWN

State = DOWN
  success #1 -> giữ DOWN
  success #2 -> UP
~~~

Hysteresis cần được kết hợp với **stale timeout**:

- Nếu background probe thread chết hoặc không chạy nữa, snapshot không được giữ UP vô hạn.
- Nếu probe bị treo, timeout phải kết thúc future và cập nhật failure.
- Nếu broker phục hồi nhưng AdminClient cache metadata cũ, lần probe mới cần đủ thời gian lấy metadata mới.

Các threshold chỉ là ví dụ. Không nên đợi quá nhiều failures nếu outage ảnh hưởng ngay đến khả năng xử lý message; cũng không nên chuyển UP sau một thành công đơn lẻ nếu broker cluster còn đang chập chờn.

## 31. Readiness policy theo vai trò service

Không phải service nào cũng cần cùng một policy:

| Vai trò | Broker unavailable | Readiness gợi ý |
|---|---|---|
| Consumer-only worker | Không thể nhận/process Kafka records | DOWN nếu Kafka là dependency bắt buộc |
| Producer-only API | Không thể publish event bắt buộc của request | DOWN cho endpoint phụ thuộc publish; có thể degraded cho endpoint khác |
| HTTP query service, Kafka chỉ dùng để phát telemetry phụ | API vẫn phục vụ được | Có thể giữ UP nếu degraded mode chấp nhận |
| Command service dùng DB + outbox | Có thể ghi business state và outbox event dù broker tạm unavailable | Có thể UP nếu outbox backlog có giới hạn và yêu cầu cho phép eventual publish |
| Kafka Streams application | Processing topology phụ thuộc cluster | DOWN khi topology không thể thực hiện nhiệm vụ theo policy |
| Multi-cluster application | Một cluster lỗi, cluster khác vẫn hoạt động | Readiness theo capability/service route, không nhất thiết global DOWN |

Đặc biệt, với **transactional outbox**, database có thể tiếp tục ghi business state và event intent khi Kafka tạm unavailable. Nếu đây là degraded mode được thiết kế và outbox có quota/backlog policy, ứng dụng có thể vẫn ready cho một số API. Nhưng relay chưa publish được và cần metrics/alerts rõ ràng.

Readiness không nên phản ánh dependency availability một cách máy móc; nó phải phản ánh **khả năng đáp ứng contract của service**.

## 32. Broker outage và consumer retry behavior

Kafka consumer có cơ chế reconnect/network retry ở client. Khi broker unavailable:

~~~text
Spring Kafka container
       |
       v
consumer.poll()
       |
       v
network / metadata failure
       |
       v
Kafka client reconnect/retry theo cấu hình
       |
       +-- broker chưa sẵn sàng -> tiếp tục lỗi
       |
       +-- broker phục hồi -> poll/metadata thành công
                              |
                              v
                        group join/assignment
~~~

Không nên mỗi lần health probe DOWN lại stop/start listener container. Điều đó có thể reset client state và gây thêm group membership churn.

Nếu container vẫn running và Kafka client tự reconnect, readiness indicator chỉ cần phản ánh dependency state. Khi broker phục hồi, consumer có thể tự lấy assignment lại.

Nếu container đã dừng vì fatal error, health logic cần phân biệt container stopped với broker metadata unavailable; chỉ reconnect broker không tự khởi động lại một container đã dừng.

## 33. Readiness khi topic chưa được tạo

Một service có thể kết nối broker thành công nhưng listener topic chưa được provision:

~~~text
Broker UP
  |
  v
AdminClient describeCluster -> success
  |
  v
orders.commands không tồn tại
  |
  v
Listener chưa thể consume topic
~~~

Nếu topic là dependency bắt buộc, readiness nên DOWN với category **topic_missing** hoặc **listener_not_assigned**, thay vì trả UP chỉ vì broker reachable.

Có thể kiểm tra topic metadata bằng AdminClient hoặc dựa vào provisioning/assignment state. Cần phân biệt topic missing với topic authorization denied; một số ACL restrictions có thể khiến metadata lookup không thể xác nhận resource theo cách mong muốn.

Không tự động tạo mọi topic từ health probe. Provisioning là trách nhiệm riêng với partition count, replication factor, retention và ACL đã được kiểm soát.

## 34. Readiness khi consumer group chưa assign

Consumer group có thể chưa có partition assignment vì:

- Consumer vừa start và đang chờ rebalance.
- Topic chưa có partitions hoặc topic missing.
- Group protocol/coordinator đang phục hồi.
- Replica count lớn hơn partition count nên một số instances không nhận partition.
- ACL group/topic chưa đúng.
- Consumer container đã stop hoặc đang pause.

Với một worker cần thực sự xử lý records, readiness có thể yêu cầu **assignment của child consumer**. Nhưng policy cần xét trường hợp hợp lệ không được assign partition do topology.

Không đặt readiness DOWN chỉ vì một pod không có assignment nếu:

- Service được scale nhiều hơn số partitions.
- Một số consumer replicas được phép idle.
- Listener subscription có nhiều topics và partition distribution không đồng đều.

Trong những hệ thống như vậy, readiness có thể dựa vào **group-level coverage** hoặc xác nhận container lifecycle và broker health, thay vì mỗi pod phải sở hữu ít nhất một partition.

## 35. Pause và readiness

Một consumer bị pause có thể vẫn giữ group membership và poll. Readiness có thể được diễn giải theo hai cách:

- **Infrastructure ready**: broker/consumer còn hoạt động, pause chỉ là trạng thái điều tiết tạm thời.
- **Processing ready**: listener có thể nhận và xử lý record mới ngay lúc này.

Nếu backpressure controller chủ động pause container, không nhất thiết readiness phải DOWN. Nếu pause do dependency nghiệp vụ không thể xử lý, readiness có thể DOWN tùy service contract.

~~~text
Broker UP
Consumer assigned
Database overloaded
Container paused

Infrastructure readiness = UP
Business processing readiness = DOWN
~~~

Không dùng một boolean duy nhất nếu dashboard và Kubernetes cần phân biệt hai khía cạnh. Tuy nhiên, Kubernetes chỉ dùng một readiness result cho endpoint đó; cần quyết định trạng thái nào có ý nghĩa với traffic mà Service route.

## 36. Health check không nên gửi business message

Một cách kiểm tra producer là publish một record test vào topic nghiệp vụ mỗi lần readiness probe chạy. Cách này nguy hiểm:

- Business consumer có thể xử lý message giả.
- Record canary làm tăng traffic/lag.
- Retry/DLT có thể chứa canary.
- Transactional producer có thể tạo transaction coordinator load.
- Nếu key trùng, canary có thể ảnh hưởng ordering.

Nếu cần end-to-end canary:

1. Dùng topic riêng.
2. Có message type riêng và consumer xác nhận.
3. Dùng unique canary ID chỉ trong log/trace.
4. Không dùng canary ID làm metric tag.
5. Tạo theo chu kỳ dài hơn readiness probe.
6. Đặt retention và cleanup.
7. Phân biệt canary health với business traffic.

AdminClient describeCluster phù hợp cho metadata reachability. Canary phù hợp để kiểm tra **đường publish/consume end-to-end**, nhưng cần được thiết kế như một hệ thống kiểm thử chủ động, không phải probe nhẹ không tác động.

## 37. Health endpoint không được lộ chi tiết bảo mật

Không trả:

~~~json
{
  "status": "DOWN",
  "error": "SASL authentication failed using username=...",
  "bootstrapServers": "internal-broker-secret...",
  "jaasConfig": "..."
}
~~~

Một response an toàn hơn:

~~~json
{
  "status": "DOWN",
  "components": {
    "kafkaBroker": {
      "status": "DOWN",
      "details": {
        "errorCategory": "authentication",
        "lastProbeAt": "2026-11-15T10:00:00Z"
      }
    }
  }
}
~~~

Response là ví dụ schema; cấu trúc thật phụ thuộc Actuator health groups và show-details policy.

Khuyến nghị:

- Không expose health details cho người dùng Internet.
- Dùng management endpoint health show-details theo security policy.
- Không đưa JAAS, passwords, tokens, broker internal hostnames hoặc full exception messages vào response.
- Giới hạn network access cho Actuator.
- Dùng log nội bộ đã redaction để điều tra root cause chi tiết.

## 38. Monitoring readiness và Kafka metrics

Readiness chỉ cho biết pod có được đánh dấu ready hay không. Để hiểu nguyên nhân, cần các metrics/logs bổ sung:

- Broker probe success/failure count.
- Probe latency và timeout count.
- Last successful probe age.
- Consumer container running/stopped state.
- Consumer assignment count hoặc partition coverage.
- Consumer lag.
- Rebalance count/duration.
- Authentication/authorization errors.
- Producer send/transaction failures.
- Outbox backlog nếu có.
- Pause duration và in-flight processing nếu backpressure.

Một structured log:

~~~text
event=readiness_changed
service=orders-service
previous=UP
current=DOWN
reason=kafka_metadata_timeout
probe_latency_ms=2000
last_success_age_seconds=45
~~~

Không ghi một log ERROR mỗi lần probe thất bại nếu Kubernetes gọi probe vài giây một lần. Log theo state transition, rate-limit repeated failures và dùng metrics để theo dõi số lần probe.

Readiness state transitions giúp operator biết khi nào pod bị loại khỏi Service endpoints và khi nào phục hồi.

## 39. Alert khi readiness DOWN

Một số alert hữu ích:

| Alert | Ý nghĩa |
|---|---|
| Kafka readiness down trên nhiều replicas | Broker/cluster/network outage có phạm vi rộng |
| Readiness down trên một pod | Local DNS, network, credentials hoặc instance issue |
| Broker probe latency tăng | Cluster/network đang suy giảm trước outage |
| Consumer assignment không phục hồi | Group/ACL/topic/consumer lifecycle issue |
| Consumer lag tăng trong khi readiness UP | Consumer chậm hoặc readiness policy quá lỏng |
| Readiness UP nhưng producer errors tăng | Broker metadata OK nhưng produce path/ACL/transaction lỗi |
| Readiness flapping | Threshold/timeout quá nhạy hoặc cluster chập chờn |
| Outbox backlog tăng | Broker unavailable hoặc relay không publish được |

Không alert chỉ vì một probe timeout đơn lẻ. Dùng duration/threshold và correlate với Kafka broker metrics.

Với consumer-only service, readiness DOWN có thể không làm Kafka listener ngừng consume. Nếu đó là vấn đề, cần alert và điều khiển container riêng.

## 40. Chẩn đoán khi pod NotReady nhưng broker có vẻ khỏe

Một quy trình:

1. Kiểm tra readiness endpoint và contributor nào trả DOWN.
2. Xem error category: network, authentication, authorization, metadata timeout hay topic missing.
3. Kiểm tra bootstrap servers và DNS resolution từ đúng pod.
4. Kiểm tra TLS/SASL configuration và credential rotation.
5. Xác nhận AdminClient có quyền describe cluster.
6. Kiểm tra consumer group/topic ACL riêng; broker health không chứng minh quyền consumer.
7. Kiểm tra listener container isRunning và trạng thái stopped event.
8. Kiểm tra partition assignment/rebalance.
9. Kiểm tra topic tồn tại, partition count và metadata.
10. Nếu producer-only, kiểm tra produce ACL và transaction coordinator.
11. Đối chiếu probe timeout với broker/client request timeout.
12. Xác định có probe flapping hay stale cached state không.

Không sửa readiness bằng cách trả UP cứng khi endpoint báo DOWN. Hãy sửa nguyên nhân hoặc điều chỉnh policy dựa trên business contract.

## 41. Chẩn đoán khi pod Ready nhưng không consume

Nếu pod Ready nhưng không xử lý Kafka records:

- Health indicator có thể chỉ kiểm tra AdminClient metadata.
- Listener container có thể chưa được start hoặc đã stop.
- Consumer group có thể chưa assign partitions.
- Topic subscription có thể sai.
- Consumer đang pause.
- Group offset đang ở cuối log hoặc topic không có data.
- Deserialization hoặc authorization có thể lỗi ở đường consumer riêng.
- Listener có thể đang block/non-responsive.

Đây là lý do **broker readiness không đồng nghĩa consumer readiness**. Một consumer service có thể cần một readiness contributor bổ sung để xác nhận listener assignment hoặc trạng thái processing.

Không dùng consumer lag bằng 0 làm bằng chứng listener healthy: topic có thể không có dữ liệu, hoặc consumer chưa bao giờ nhận assignment.

## 42. Readiness trong rolling deployment

Trong rolling deployment, pod mới cần sẵn sàng trước khi pod cũ bị terminate nếu muốn giảm gián đoạn:

~~~text
Pod A (old) -> Ready, consumes
Pod B (new) -> Starting, broker unavailable

Readiness B = DOWN
Pod A remains active

Kafka recovers
Pod B -> broker reachable
Pod B -> group assigned
Readiness B = UP

Pod A graceful shutdown
Group rebalance
Pod B continues
~~~

Nếu readiness B chỉ kiểm tra HTTP server mà không xét Kafka, deployment controller có thể cho rằng pod mới sẵn sàng quá sớm. Nếu readiness yêu cầu full group assignment nhưng pod mới hợp lệ chưa nhận partition do group topology, rollout có thể bị chặn.

Hãy chọn readiness gate vừa đủ cho service role và đặt maxUnavailable, maxSurge, termination grace period cùng consumer group behavior phù hợp.

Không yêu cầu mọi pod mới phải sở hữu tất cả partitions; group assignment là phân phối toàn group.

## 43. Readiness khi dùng transactional producer

Với producer transaction, metadata probe thành công chưa đủ để chứng minh transaction hoạt động.

~~~text
AdminClient describeCluster -> UP

KafkaTemplate producer:
  initTransactions -> failure
  hoặc send/commit -> ProducerFencedException

Business event publish:
  không sẵn sàng
~~~

Nếu transaction là điều kiện bắt buộc, readiness cần phản ánh khả năng transactional publishing theo policy phù hợp.

Không khởi tạo và commit một Kafka transaction trên mỗi probe. Thay vào đó:

- Theo dõi producer initialization/transaction failures.
- Đảm bảo transactional.id không trùng giữa active instances.
- Xử lý fencing và container/producer lifecycle đúng cách.
- Có canary transaction riêng nếu cần xác minh end-to-end.
- Chỉ thay đổi readiness khi có trạng thái đủ tin cậy, không dựa vào một log lỗi cũ.

## 44. Readiness khi broker phục hồi nhưng consumer chưa ổn định

Broker có thể trả lời metadata request trước khi consumer group hoàn tất rebalance hoặc listener bắt đầu nhận partitions:

~~~text
Broker probe -> UP
      |
      v
Consumer reconnect
      |
      v
Group join/rebalance
      |
      v
Partitions assigned
      |
      v
Listener processing resumes
~~~

Nếu service cần consume để thực hiện vai trò chính, chỉ mark ready sau khi assignment condition phù hợp đã đạt.

Tuy nhiên, nếu một consumer group có nhiều members và một pod được assign 0 partitions một cách hợp lệ, không nên bắt pod đó chờ vô hạn. Cần chọn một policy theo instance role hoặc group-level assignment.

Một thời gian grace period sau broker recovery có thể tránh flapping khi group còn đang rebalance, nhưng phải có upper bound và alert nếu assignment không bao giờ hoàn tất.

## 45. Readiness và database dependency

Một consumer service có thể kết nối Kafka nhưng database chưa sẵn sàng:

~~~text
Kafka broker -> UP
Database -> DOWN
Consumer group -> ASSIGNED
Listener -> không thể ghi business state
~~~

Nếu listener vẫn consume và listener method ném exception, error handler có thể retry. Nhưng retry vô hạn hoặc blocking retry lâu có thể làm partition lag và ảnh hưởng các records khác.

Một policy có thể:

- Readiness DOWN khi database là dependency bắt buộc.
- Pause consumer khi database quá tải để tránh nhận thêm work.
- Giữ consumer group membership nếu outage ngắn.
- Resume khi database phục hồi.
- Dùng outbox/idempotency cho side effects và event publication.

Không chỉ include kafkaBroker vào readiness rồi coi toàn bộ service healthy. **Readiness phải bao phủ các dependencies thực sự cần cho business path.**

## 46. Readiness và transactional outbox

Với transactional outbox, API có thể ghi business state cùng outbox event trong một DB transaction ngay cả khi Kafka tạm unavailable:

~~~text
HTTP command
    |
    v
DB transaction:
  update orders
  insert outbox event
    |
    v
DB commit
    |
    v
Outbox relay
    |
    +-- Kafka unavailable -> backlog tăng
    |
    +-- Kafka recovered -> publish backlog
~~~

Trong kiến trúc này, Kafka outage không nhất thiết làm toàn bộ HTTP API NotReady ngay lập tức. Nếu database còn capacity và outbox backlog dưới giới hạn, API có thể tiếp tục nhận lệnh theo contract eventual consistency.

Readiness cần xem:

- Database ready.
- Outbox storage writable.
- Outbox backlog/oldest event age trong giới hạn.
- Relay state được theo dõi.
- Disk/database capacity đủ cho thời gian outage dự kiến.

Nếu backlog vượt hard limit hoặc event age vượt business SLA, readiness/traffic policy có thể chuyển degraded hoặc DOWN.

Không giữ UP vô hạn khi outbox backlog tích tụ không giới hạn; eventual consistency cũng cần một budget.

## 47. Tránh restart storm và rebalance storm

Một thiết kế probe sai có thể gây chuỗi:

~~~text
Kafka broker outage
   |
   v
Liveness probe thất bại
   |
   v
Kubernetes restart tất cả pods
   |
   v
Consumers rời group
   |
   v
Broker phục hồi
   |
   v
Tất cả pods reconnect đồng thời
   |
   v
Group rebalance và transaction initialization tăng
   |
   v
Recovery chậm hơn
~~~

Để tránh:

1. Không đưa broker availability vào liveness.
2. Dùng readiness để loại pod khỏi HTTP Service khi cần.
3. Cho Kafka client reconnect theo backoff.
4. Dùng startup probe đủ rộng cho thời gian khởi động.
5. Hạn chế restart/start-stop listener theo mỗi probe failure.
6. Dùng rollout strategy và graceful shutdown.
7. Giám sát consumer group rebalance và connection rate khi broker phục hồi.

Nếu cần pause listener do business dependency, dùng pause/resume với hysteresis; không restart pod để giảm tải.

## 48. Kiểm thử broker unavailable

Nên dùng Kafka broker test thật như **Testcontainers Kafka** hoặc môi trường integration có thể dừng/khởi động broker có kiểm soát.

### Test 1: broker chưa sẵn sàng lúc application start

1. Khởi động Spring Boot application khi broker chưa chạy.
2. Xác nhận application context/HTTP management endpoint có thể khởi động theo policy.
3. Xác nhận readiness DOWN hoặc UNKNOWN.
4. Xác nhận liveness UP.
5. Xác nhận pod không bị yêu cầu restart chỉ vì Kafka outage.
6. Khởi động broker.
7. Chờ readiness chuyển UP theo threshold đã định.

### Test 2: broker mất kết nối sau khi service ready

1. Đợi application và consumer group ready.
2. Dừng broker hoặc chặn network.
3. Xác nhận readiness chuyển DOWN sau threshold.
4. Xác nhận liveness vẫn UP.
5. Kiểm tra Kafka client reconnect attempts và container state.
6. Khôi phục broker.
7. Xác nhận consumer lấy lại assignment và readiness UP.

### Test 3: broker reachable nhưng topic missing

1. Khởi động broker.
2. Không tạo topic bắt buộc.
3. Xác nhận broker metadata probe UP.
4. Xác nhận listener readiness DOWN nếu policy yêu cầu topic/assignment.
5. Tạo topic đúng cấu hình.
6. Xác nhận listener readiness phục hồi.

### Test 4: authentication/authorization failure

1. Cấu hình sai SASL credentials hoặc ACL trong test.
2. Xác nhận health state phân loại authentication/authorization.
3. Kiểm tra liveness không bị kéo DOWN.
4. Cấp lại credential/ACL đúng.
5. Xác nhận retry/reconnect và readiness recovery theo policy.

### Test 5: metadata UP nhưng consumer chưa assigned

1. Cho AdminClient describeCluster thành công.
2. Giữ consumer group ở trạng thái chưa assign (ví dụ topic/ACL/subscription phù hợp trong test).
3. Xác nhận broker health UP nhưng consumer assignment readiness chưa UP.
4. Sửa điều kiện group/topic.
5. Xác nhận assignment tracker cập nhật đúng.

### Test 6: readiness flapping

1. Mô phỏng một lần probe timeout ngắn.
2. Xác nhận threshold chưa chuyển DOWN nếu policy yêu cầu nhiều failures.
3. Mô phỏng nhiều failures liên tiếp.
4. Xác nhận DOWN.
5. Mô phỏng một success đơn lẻ.
6. Xác nhận vẫn DOWN cho tới khi đủ recovery successes.

### Test 7: probe timeout

1. Làm AdminClient request không hoàn tất trong timeout.
2. Xác nhận health endpoint phản hồi trong thời gian giới hạn.
3. Xác nhận interrupted thread khôi phục interrupt flag.
4. Xác nhận không tạo AdminClient mới ở mỗi request.
5. Xác nhận scheduled probes không chồng lấn vô hạn.

### Test 8: transactional producer không sẵn sàng

1. Cho broker metadata probe thành công.
2. Cấu hình producer transaction lỗi (ví dụ transactional ID conflict hoặc coordinator issue).
3. Xác nhận broker readiness không bị hiểu nhầm là transaction readiness.
4. Kiểm tra transaction error metrics/logs và policy readiness bổ sung nếu cần.
5. Khôi phục producer lifecycle.

## 49. Kiểm thử với Kubernetes probes

Trong integration/deployment test:

1. Deploy application trước Kafka hoặc mô phỏng broker unavailable.
2. Quan sát startup probe, readiness và liveness riêng.
3. Xác nhận liveness không restart pod liên tục khi broker down.
4. Xác nhận readiness loại pod khỏi HTTP Service endpoints nếu policy yêu cầu.
5. Kiểm tra consumer listener vẫn tiếp tục hay pause theo đúng policy riêng.
6. Khôi phục broker và xác nhận pod trở lại Ready.
7. Theo dõi consumer group rebalance/lag trong quá trình phục hồi.

Không chỉ kiểm tra HTTP response status. Cần xem **Kubernetes pod condition Ready**, restart count và Service endpoints để xác nhận probe tác động như mong đợi.

## 50. Những hiểu nhầm thường gặp

**ApplicationContext đã khởi động nghĩa là Kafka ready.** Không đúng. Spring beans có thể được tạo trước khi broker reachable hoặc consumer group assign.

**Kafka broker unavailable thì phải fail liveness.** Không đúng trong hầu hết hệ thống; broker là dependency ngoài process.

**Readiness DOWN tự dừng Kafka listener.** Không đúng. Kubernetes readiness chủ yếu ảnh hưởng Service routing; listener container có thể tiếp tục consume.

**AdminClient describeCluster thành công chứng minh producer/consumer đều sẵn sàng.** Không đúng. Nó không chứng minh topic/group ACL, assignment hoặc transaction publish.

**container.isRunning() nghĩa consumer đã có partitions.** Không đúng. Running là lifecycle state, assignment là group state.

**Consumer group assignment phải có đủ mọi partitions trên mỗi pod.** Không đúng. Partitions được phân phối giữa các group members.

**Một health check timeout nghĩa broker chắc chắn DOWN.** Không nhất thiết. Có thể là network jitter, request timeout hoặc thread bị chặn; cần threshold và category.

**Tạo AdminClient mỗi lần health check là đơn giản và an toàn.** Không tốt. Nó có thể tạo connection churn và tăng tải lúc broker outage.

**Readiness nên fail ngay sau một timeout.** Tùy SLO. Một failure đơn lẻ có thể là transient; cần hysteresis nhưng không che giấu outage kéo dài.

**Broker UP nghĩa topic đã tồn tại.** Không đúng. Topic provisioning là điều kiện riêng.

**Broker UP nghĩa consumer group đã được assign.** Không đúng. Group membership/rebalance là lifecycle riêng.

**Consumer paused thì phải readiness DOWN.** Không nhất thiết. Pause có thể là backpressure có chủ đích; cần phân biệt infrastructure readiness với processing readiness.

**Readiness UP bảo đảm business processing thành công.** Không đúng. Dependency có thể lỗi sau probe hoặc side effects có thể thất bại.

**Khi broker phục hồi phải restart application.** Không cần nếu consumer/producer client còn hoạt động và có thể reconnect theo lifecycle.

**Transactional outbox vẫn phải readiness DOWN mỗi khi Kafka down.** Không nhất thiết. Nếu contract cho phép ghi outbox và backlog còn trong giới hạn, một số API vẫn có thể phục vụ.

## 51. Quy trình triển khai production

Để thiết kế readiness khi Kafka broker chưa sẵn sàng:

1. Xác định service role: consumer, producer, combined API, Kafka Streams hay outbox relay.
2. Định nghĩa rõ **ready** nghĩa là có thể thực hiện contract nghiệp vụ nào.
3. Tách readiness, liveness và startup probe.
4. Không đưa broker availability vào liveness nếu process vẫn khỏe và có thể chờ dependency.
5. Bật Spring Boot Actuator health probes và cấu hình readiness group có chủ đích.
6. Dùng một AdminClient được quản lý lâu dài để kiểm tra broker metadata với timeout hữu hạn.
7. Để state UNKNOWN/NOT READY cho đến khi có probe thành công đáng tin cậy.
8. Dùng consecutive failure/success thresholds và stale-result timeout để tránh flapping.
9. Với consumer service, bổ sung assignment readiness theo đúng group topology nếu business cần partitions được assign trước khi ready.
10. Không dùng isRunning() làm bằng chứng consumer assigned hoặc producer transactional.
11. Phân loại network, authentication, authorization, topic missing và transaction failures.
12. Không restart listener/pod theo mỗi readiness failure; cho Kafka client reconnect và chỉ restart khi lifecycle thực sự cần.
13. Nếu cần ngừng nhận records vì backpressure, điều khiển container pause/resume riêng; readiness không tự làm điều đó.
14. Nếu dùng outbox, đặt backlog/age limits cho degraded mode.
15. Không để health endpoint lộ credentials, exception messages hoặc broker configuration nhạy cảm.
16. Theo dõi readiness transitions, probe latency, assignment, consumer lag, rebalance và transaction errors.
17. Kiểm thử broker startup delay, outage, recovery, topic missing, ACL failure, unassigned consumers và Kubernetes restart behavior.

**Readiness khi broker chưa sẵn sàng** là bài toán về khả năng phục vụ, không phải phép thử đơn giản xem process có mở cổng HTTP hay không. Spring Boot Actuator và Kafka AdminClient giúp quan sát broker connectivity, còn consumer assignment và producer transaction cần những tín hiệu riêng nếu chúng là điều kiện bắt buộc. Khi Kafka unavailable, một ứng dụng vẫn có thể sống và chờ reconnect; **readiness nên phản ánh việc instance có thể nhận công việc an toàn, trong khi liveness tiếp tục phản ánh sức khỏe nội tại của process**. Sự tách biệt này giúp Kubernetes tránh restart storm, consumer group tránh churn không cần thiết và hệ thống phục hồi có kiểm soát khi broker trở lại.
