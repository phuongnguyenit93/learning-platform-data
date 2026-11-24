# Trình tự sẵn sàng của broker, binding và ứng dụng

Trong ứng dụng **SPRING_CLOUD_STREAM**, tiến trình Java chạy thành công không đồng nghĩa dịch vụ đã có thể gửi hoặc nhận sự kiện. Spring Boot có thể tạo ApplicationContext trong khi Kafka chưa cấp metadata, RabbitMQ chưa có queue hợp lệ hoặc Pulsar chưa cho phép subscription. Ngay cả khi đã tạo binding, consumer vẫn có thể đang chờ assignment; Kafka Streams còn cần khôi phục state store trước khi cung cấp dữ liệu đúng.

Bài học trình bày thứ tự sẵn sàng khi triển khai các hàm Supplier/Function/Consumer qua Kafka, RabbitMQ và Pulsar. Mục tiêu là kiểm soát tình huống broker lên chậm, binding chưa hình thành, HTTP API nhận traffic quá sớm, ứng dụng bị restart hàng loạt lúc broker gặp sự cố, hoặc processor nhận message trước khi các phụ thuộc nghiệp vụ đã sẵn sàng.

## 1. Có nhiều mức “ready” chứ không chỉ một

| Mức | Điều đã xảy ra | Điều chưa được bảo đảm |
| --- | --- | --- |
| Container running | Container đã được khởi tạo và process còn sống | JVM/Spring Boot đã sẵn sàng |
| Spring Boot started | ApplicationContext và beans đã được dựng | Broker, binding và consumer hoạt động |
| Broker reachable | Client có thể kết nối tới broker | Topic/queue/ACL/schema đã đúng |
| Binding started | Lifecycle input/output binding đang chạy | Consumer đã nhận partition hoặc message đã được ghi thành công |
| Consumer/processor ready | Consumer có thể xử lý, topology/state cần thiết đã sẵn sàng | Mọi nghiệp vụ downstream luôn thành công |
| Application ready | Chức năng của dịch vụ có thể nhận traffic theo chính sách | Không bao giờ xảy ra lỗi sau startup |

Liveness, readiness, binding lifecycle và broker health là những tín hiệu khác nhau. Không nên thay chúng bằng một phép kiểm tra TCP hoặc một endpoint HTTP luôn trả 200.

~~~mermaid
flowchart TD
  A[Khởi động container] --> B[Spring Boot tạo ApplicationContext]
  B --> C[Chọn binder và cấu hình bindings]
  C --> D{Broker đủ điều kiện để bind?}
  D -->|Không| E[Retry binding hoặc fail-fast]
  E --> D
  D -->|Có| F[Tạo và start binding]
  F --> G[Consumer subscribe hoặc join group]
  G --> H{Assignment và state đã sẵn sàng?}
  H -->|Chưa| I[Rebalance hoặc restore]
  I --> H
  H -->|Rồi| J[Readiness theo chức năng]
  J --> K[Nhận traffic hoặc xử lý sự kiện]
~~~

Sơ đồ là mô hình vận hành. Producer binding, consumer binding, assignment và state restoration có thể diễn ra bất đồng bộ và trình tự chi tiết phụ thuộc binder.

## 2. Ví dụ cuộc đua khởi động

Một triển khai có Order Service và Kafka:

1. 10:00:00: Kubernetes tạo pod Kafka và pod Order Service.
2. 10:00:05: Kafka mở TCP port nhưng metadata/controller chưa ổn định.
3. 10:00:08: Spring Boot bắt đầu tạo binding cho topic orders.created.
4. 10:00:10: Kafka client chưa lấy được metadata nên binding có thể lỗi hoặc chờ retry.
5. 10:00:20: Kafka sẵn sàng phục vụ topic, ACL và metadata.
6. 10:00:24: Binding được tạo; consumer tham gia group.
7. 10:00:30: Consumer nhận partition; ứng dụng đủ điều kiện phục vụ chức năng cần message flow.

Các mốc chỉ minh họa. Nếu readiness chỉ kiểm tra web server ở bước 3, caller có thể gửi yêu cầu khi producer chưa hoạt động. Nếu liveness yêu cầu broker luôn UP, Kubernetes có thể liên tục restart Order Service trong khi Kafka chỉ đang khởi động, làm tình hình tệ hơn.

## 3. Broker chạy được khác broker dùng được

Một kết nối TCP thành công chưa chứng minh broker thực sự phục vụ workload. Cần kiểm tra thêm:

- DNS và địa chỉ kết nối; với Kafka, advertised listeners phải phù hợp network của client.
- TLS/SASL, user/password hoặc token đúng và còn hiệu lực.
- Quyền tạo/đọc/ghi topic, exchange, queue, namespace và subscription.
- Topic/queue tồn tại hoặc được provision đúng theo quyền của binder.
- Kafka metadata, partition leader, replication/acknowledgment theo yêu cầu.
- RabbitMQ virtual host, exchange, queue arguments và binding tương thích.
- Pulsar service URL, topic lookup, subscription và schema compatibility.

Phân biệt ba loại thất bại: broker đến muộn, kết nối tạm gián đoạn và cấu hình sai không thể tự hồi phục. Lỗi đến muộn có thể retry; lỗi ACL/hostname/queue arguments sai cần can thiệp cấu hình. Đừng dùng retry vô hạn để che giấu lỗi cố định.

## 4. Tên binding và trình tự tạo binding

Ví dụ một hàm:

~~~java
@Bean
public Function<OrderCreated, OrderValidated> validateOrder(
        OrderValidator validator) {
    return validator::validate;
}
~~~

Theo quy tắc đặt tên mặc định, Spring Cloud Stream tạo **validateOrder-in-0** và **validateOrder-out-0**. Nếu định nghĩa alias trong cấu hình function bindings, các thao tác quản trị phải dùng tên alias thực tế.

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: validation-service
        validateOrder-out-0:
          destination: orders.validated
~~~

Binding kết nối function input/output với destination của middleware. Tạo ApplicationContext không chứng minh binding đã thành công. Tương tự, một producer binding ở trạng thái STARTED không bảo đảm mọi lần gửi sau này sẽ được broker xác nhận.

Với consumer, còn có bước join group/subscription và assignment. Với Kafka Streams, phải thêm bước restore state và chờ stream threads chuyển tới trạng thái chạy phù hợp.

## 5. Retry khi broker chưa sẵn sàng lúc tạo binding

Spring Cloud Stream cung cấp **spring.cloud.stream.bindingRetryInterval** để thử tạo binding lại trong trường hợp binder không hỗ trợ late binding và broker chưa sẵn sàng. Giá trị tính bằng giây; tài liệu mô tả mặc định **30 giây**.

~~~yaml
spring:
  cloud:
    stream:
      binding-retry-interval: 15
~~~

Nếu đặt bằng **0**, các tình huống binding creation lỗi thuộc cơ chế này được coi là fatal và ứng dụng không hoàn tất startup.

| Cơ chế | Xử lý ở giai đoạn nào? |
| --- | --- |
| bindingRetryInterval | Chưa tạo được binding |
| Consumer maxAttempts | Handler đang xử lý một message và ném lỗi |
| Client reconnect/backoff | Kết nối broker bị mất hoặc thay đổi |
| Retry trong HTTP/database client | Downstream nghiệp vụ tạm lỗi |

Không dùng consumer.maxAttempts để sửa lỗi tạo binding. Không coi bindingRetryInterval là bảo đảm tự phục hồi mọi loại lỗi trên mọi binder: một số lỗi cấu hình, authentication hoặc khởi tạo bean có thể fail trước cơ chế retry; một số binder hỗ trợ late binding theo cách riêng.

Chọn **retry** khi broker có thể đến muộn hoặc gián đoạn ngắn và ứng dụng có readiness/alert phù hợp. Chọn **fail-fast** khi startup cần thất bại rõ ràng để orchestrator hoặc runbook can thiệp. Cả hai cách đều cần log nguyên nhân và giới hạn thời gian điều tra.

## 6. AutoStartup của input và output

Mặc định consumer và producer bindings tự start. Có thể dừng tự khởi động một binding khi cần điều phối prerequisites:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: validation-service
          consumer:
            auto-startup: false
        validateOrder-out-0:
          destination: orders.validated
          producer:
            auto-startup: true
~~~

Cách này hữu ích khi muốn hoàn tất migration, nạp config hoặc kiểm tra policy trước khi nhận sự kiện. Nhưng nếu consumer.auto-startup=false, input sẽ không tự nhận message cho tới khi được start bằng API lifecycle hoặc cơ chế ứng dụng tự quản lý.

AutoStartup là điều khiển vòng đời, không phải health check. Nếu có một consumer bị cố ý stop, readiness của chức năng phụ thuộc consumer phải phản ánh điều đó.

## 7. Truy vấn và điều khiển lifecycle bindings

Spring Cloud Stream cung cấp **BindingsLifecycleController** và Actuator **/actuator/bindings** để quan sát và điều khiển binding.

~~~java
import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.cloud.stream.binder.Binding;

Binding<?> binding = controller.queryState("validateOrder-in-0");
if (binding != null && !binding.isRunning()) {
    controller.start("validateOrder-in-0");
}
~~~

Controller trong ví dụ là bean BindingsLifecycleController của framework. Nếu binding chưa được tạo, đang lỗi hoặc binder không hỗ trợ một thao tác, phải xử lý trường hợp đó thay vì giả định start luôn thành công.

Bật endpoint nếu cần vận hành qua HTTP:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,bindings
~~~

Các thao tác đọc:

~~~bash
curl -fsS http://localhost:8080/actuator/bindings
curl -fsS http://localhost:8080/actuator/bindings/validateOrder-in-0
~~~

Để START một binding đã dừng:

~~~bash
curl -X POST http://localhost:8080/actuator/bindings/validateOrder-in-0 \
  -H "Content-Type: application/json" \
  -d '{"state":"STARTED"}'
~~~

Endpoint có khả năng start/stop/pause binding nên phải được bảo vệ bằng authentication, authorization và network policy. Không công khai endpoint điều khiển cho Internet. PAUSED/RESUMED chỉ dùng được khi binder và công nghệ nền hỗ trợ.

**isRunning() chỉ đo lifecycle.** Consumer còn có assignment, broker connectivity, retry và state restoration; producer còn có kết quả send và acknowledgment.

## 8. Liveness và readiness trong Spring Boot

Spring Boot Actuator công bố Application Availability:

- **/actuator/health/liveness**: ứng dụng có còn ở trạng thái nội tại đáng để tiếp tục chạy không?
- **/actuator/health/readiness**: ứng dụng có nên nhận traffic theo chính sách hiện tại không?

Trong startup, Spring Boot thường đi từ liveness BROKEN/readiness REFUSING_TRAFFIC, sang liveness CORRECT/readiness REFUSING_TRAFFIC, rồi readiness ACCEPTING_TRAFFIC khi các startup task hoàn tất.

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Khi có web server, Actuator có các đường **/actuator/health/liveness** và **/actuator/health/readiness**. Với add-additional-paths, Spring Boot cũng có thể cung cấp **/livez** và **/readyz** trên cổng chính, hữu ích khi management port khác cổng ứng dụng.

Theo mặc định, Spring Boot không tự động thêm tất cả HealthIndicator của hệ thống ngoài vào readiness group. Đây là quyết định thiết kế để tránh toàn bộ replica bị gỡ khỏi routing khi một dependency dùng chung bị DOWN.

## 9. Không đặt broker health vào liveness

Nếu một broker chung gặp sự cố và liveness của mỗi pod phụ thuộc broker:

1. Tất cả replica báo liveness DOWN.
2. Kubernetes khởi động lại hàng loạt replica.
3. Broker nhận thêm các kết nối, authentication, consumer group join và binding provisioning cùng lúc.
4. Rebalance và restore có thể kéo dài, làm phục hồi chậm hơn.

Liveness nên phản ánh vấn đề nội tại mà restart process có khả năng xử lý, như deadlock. Mất kết nối Kafka/RabbitMQ/Pulsar trong thời gian ngắn thường cần client reconnect và cảnh báo, không cần kill toàn bộ ứng dụng.

Readiness có thể xét dependency ngoài nếu dependency đó **thực sự bắt buộc để nhận HTTP request**. Tuy nhiên, việc đưa broker dùng chung vào readiness cũng có thể làm mọi replica bị loại khỏi Service. Quyết định phải dựa trên mô hình phục vụ và fallback của ứng dụng.

## 10. Readiness theo vai trò workload

| Loại ứng dụng | Chính sách readiness phù hợp | Lưu ý |
| --- | --- | --- |
| HTTP API phải publish event trước khi trả thành công | Cần kiểm tra chức năng producer bắt buộc đã sẵn sàng | Binding STARTED chưa chứng minh send cuối cùng luôn thành công |
| Consumer thuần không nhận HTTP request | Tập trung đo consumer lifecycle, lag, lỗi và reconnect | K8s readiness không tự pause consumer |
| Kafka Streams có truy vấn state | Task/threads cần thiết chạy và state đã restore | Web server có thể mở trước khi store phục hồi |
| Service có nhiều binding tùy chọn | Chỉ binding thực sự bắt buộc mới chặn readiness | Không để một luồng phụ làm ngắt toàn bộ API |

**Điểm rất quan trọng:** Kubernetes readiness quyết định pod có nằm trong EndpointSlice/Service routing để nhận traffic hay không. Nó **không dừng Kafka consumer, Rabbit listener hay Pulsar subscription** đang chạy. Consumer tiếp tục có thể xử lý message ngay cả khi HTTP readiness trả DOWN.

Nếu muốn consumer đợi một prerequisite, phải điều khiển binding lifecycle hoặc thêm cơ chế gating phù hợp trong processor. Readiness HTTP không phải công tắc dừng message consumption.

## 11. Kiểm tra binding trong readiness

Ví dụ với một input binding bắt buộc, có thể tạo custom HealthIndicator:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.cloud.stream.binder.Binding;
import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class BindingReadinessConfiguration {

    @Bean("inputBindingReady")
    HealthIndicator inputBindingReady(BindingsLifecycleController controller) {
        return () -> {
            try {
                Binding<?> binding = controller.queryState("validateOrder-in-0");
                if (binding != null && binding.isRunning()) {
                    return Health.up().build();
                }
            }
            catch (RuntimeException ex) {
                // Tránh đưa credentials hoặc stack trace vào health response.
            }
            return Health.down()
                    .withDetail("binding", "validateOrder-in-0")
                    .build();
        };
    }
}
~~~

Đưa indicator vào readiness group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,inputBindingReady
~~~

Đây là kiểm tra **lifecycle tối thiểu**. Binding running chưa chứng minh Kafka partition assignment, Rabbit queue có message dispatch hoặc Pulsar subscription đã hoạt động đúng. Với workload quan trọng, bổ sung tín hiệu nghiệp vụ/transport cần thiết và có timeout giới hạn.

Health probe nên nhanh, không tạo producer/AdminClient mới hoặc gọi mạng liên tục với mỗi request. Nếu phải kiểm tra broker, cache trạng thái và giới hạn tần suất/timeout.

## 12. Binder HealthIndicator và những giới hạn

Khi có Actuator, Spring Cloud Stream có thể cung cấp health contributor tên **binders**; cấu hình bằng **management.health.binders.enabled**:

~~~yaml
management:
  health:
    binders:
      enabled: true
  endpoint:
    health:
      show-details: when_authorized
~~~

Mức hỗ trợ khác nhau theo binder:

- **Kafka binder:** có health indicator kiểm tra giao tiếp với Kafka/metadata. Một kết quả UP không chứng minh gửi message end-to-end.
- **Rabbit binder:** health chủ yếu dựa trên Spring Boot RabbitHealthIndicator, phản ánh connectivity.
- **Kafka Streams binder:** theo dõi trạng thái các stream threads; tài liệu mô tả UP khi tất cả thread đăng ký ở trạng thái RUNNING.
- **Pulsar binder:** kiểm tra phiên bản binder/Spring Pulsar và khả năng health thực tế, bổ sung custom check khi cần.

Không giả định mọi binder luôn có một HealthIndicator. Việc binders health UP cũng không bảo đảm message được xác nhận hoặc consumer không còn lag.

## 13. Docker Compose: chờ dependency healthy

Dạng depends_on ngắn chỉ điều phối container start order; không chờ broker đã sẵn sàng dùng. Khi cần chờ tại lần khởi động, dùng condition: service_healthy và healthcheck.

Ví dụ với RabbitMQ:

~~~yaml
services:
  rabbitmq:
    image: rabbitmq:4-management
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 5s
      timeout: 5s
      retries: 12
      start_period: 15s

  order-service:
    image: example/order-service:1.0
    environment:
      SPRING_RABBITMQ_HOST: rabbitmq
    depends_on:
      rabbitmq:
        condition: service_healthy
~~~

Compose đợi healthcheck rabbitmq healthy trước khi tạo order-service. Tuy nhiên, rabbitmq-diagnostics ping chỉ kiểm tra node ở mức nhất định; nó không xác minh exchange/queue, arguments, ACL hoặc quyền consume của ứng dụng.

depends_on chủ yếu xử lý **thứ tự lúc start**, không thay thế reconnect khi broker bị lỗi sau đó. Với Kafka/Pulsar, kiểm tra readiness cần phù hợp image và khả năng metadata/lookup, không chỉ TCP open.

## 14. Kubernetes: startup, liveness và readiness probes

Kubernetes không tự bảo đảm broker Deployment hoàn tất trước application Deployment chỉ vì manifest được apply theo một thứ tự. Scheduler có thể tạo các pod song song; cần chủ động xử lý broker đến muộn.

Ví dụ một Spring Boot HTTP service:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: example/order-service:1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 3
            successThreshold: 1
~~~

Startup probe ở đây dành khoảng 150 giây (30 × 5) cho ứng dụng khởi động trước khi kubelet bắt đầu liveness/readiness. Đây là số minh họa, phải đo từ môi trường gần production. Startup probe thành công một lần rồi ngừng; readiness tiếp tục chạy trong vòng đời pod.

Nếu ứng dụng không có web server, chọn exec probe hoặc management endpoint riêng phản ánh đúng chức năng, không thêm HTTP endpoint giả chỉ để trả 200.

### Init container có thay thế được không?

Init container hữu ích để đợi một prerequisite hữu hạn như cấu hình hoặc database migration. Nhưng việc chỉ kiểm tra TCP port của broker không bảo đảm topic/queue/subscription và ACL hợp lệ. Init container cũng không giải quyết broker outage sau startup. Vì thế, dùng nó bổ trợ cho retry và lifecycle, không dùng thay thế.

## 15. Chủ động khởi động consumer sau prerequisite

Khi muốn consumer chỉ xử lý sau một bước chuẩn bị, trình tự có thể là:

1. Khởi động Spring Boot và thành phần quan sát.
2. Kiểm tra config/secrets, schema, migration hoặc cache bắt buộc với timeout.
3. Xác nhận đường tới broker/destination đủ điều kiện.
4. Gọi BindingsLifecycleController.start cho input có auto-startup=false.
5. Chờ consumer assignment/topology readiness nếu có.
6. Công bố readiness của chức năng liên quan.

Đừng blocking ApplicationRunner vĩnh viễn để chờ broker. Nếu điều kiện không đạt trong deadline, chọn retry có cảnh báo hoặc fail-fast. Nếu binding start bất đồng bộ, bước 4 hoàn thành vẫn chưa chứng minh bước 5 thành công.

## 16. Kafka: metadata, topic, consumer group

Kafka readiness có nhiều lớp:

- Bootstrap broker kết nối được.
- Metadata topic và advertised listeners đúng.
- Topic tồn tại, đủ partition và ACL phù hợp.
- Producer có thể publish theo acks/durability policy.
- Consumer subscribe, join group và nhận partition.
- Nếu xử lý có state, processor hoàn tất bước restore cần thiết.

Ví dụ regular Kafka binder:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      binding-retry-interval: 15
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-service
          consumer:
            auto-startup: true
      kafka:
        binder:
          brokers: kafka:9092
~~~

Cần thêm SASL/TLS nếu broker yêu cầu. Kết nối tới bootstrap broker không đủ để xác nhận ACL/topic của ứng dụng.

Trong rolling deployment hoặc scaling, consumer group có thể rebalance; partition assignment bị thay đổi tạm thời là bình thường. Đừng restart pod ngay khi một snapshot thấy assignment chưa có. Theo dõi trạng thái kéo dài, consumer lag và tiến độ xử lý.

## 17. RabbitMQ: connection, exchange, queue và listener

Rabbit binder thường cần các bước:

1. Kết nối tới RabbitMQ node với credentials và virtual host đúng.
2. Exchange, queue và binding tồn tại hoặc được provision hợp lệ.
3. Queue arguments như durable, TTL, DLX/queue-type không xung đột.
4. Listener container start và consumer được đăng ký.
5. Message được giao và ack/reject theo semantics.

Lỗi **PRECONDITION_FAILED: inequivalent arg** khi khai báo queue là sai cấu hình topology, không phải broker chưa ready. Retry không khắc phục được cho tới khi queue/config được chỉnh nhất quán. Lỗi access refused cũng cần sửa permissions.

Rabbit health indicator kiểm tra kết nối, nhưng không chứng minh một queue cụ thể đã có routing hoặc dead-lettering đúng. Kiểm thử provisioning, consume, acknowledgment và DLQ bằng integration test riêng.

## 18. Pulsar: lookup, schema và subscription

Pulsar binder dựa vào Spring for Apache Pulsar. Các bước cần xác minh:

- service-url và authentication đúng;
- topic/namespace có tồn tại hoặc cho phép tạo;
- producer có quyền publish và schema phù hợp;
- consumer lookup topic và subscribe với subscription type/name đúng;
- message processing, ack/redelivery hoạt động;
- dead-letter/retry-letter policy đã được cấu hình nếu cần.

Ví dụ input:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar-broker:6650
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://public/default/orders-created
          group: order-service
~~~

Tùy binder version, group và extended consumer settings quyết định subscription identity/type thực tế. Không giả định Pulsar subscription có semantics giống Kafka consumer group hay dùng cùng cấu hình health.

## 19. Kafka Streams: state restoration trước business readiness

Kafka Streams binder dùng KStream/KTable/GlobalKTable, có thể tạo RocksDB state store và changelog/repartition topics. Dù Kafka kết nối được, topology vẫn có thể đang:

- tạo/kiểm tra internal topics;
- join group, rebalance và assign stream tasks;
- đọc changelog để restore state store;
- cập nhật standby/warmup tasks;
- chuyển stream threads sang RUNNING.

Khi ứng dụng cung cấp truy vấn theo state hoặc window aggregate, readiness của chức năng đó phải chờ state có thể dùng đúng. Kafka Streams binder có health indicator theo trạng thái threads; RUNNING hữu ích nhưng với nhiều topology/store vẫn cần xác định readiness theo API và nghiệp vụ.

Nếu state.dir trên ephemeral volume, cold restore sau reschedule có thể lâu hơn warm restart. Sizing startup/readiness từ thời gian đo thực tế, và không đưa broker outage vào liveness khiến pod bị kill khi đang restore.

## 20. Broker mất kết nối sau startup

| Tình huống | Phản ứng thường phù hợp |
| --- | --- |
| Broker gián đoạn ngắn, client hỗ trợ reconnect | Giữ process, giám sát, để client phục hồi |
| HTTP API bắt buộc publish event | Trả lỗi/circuit breaker phù hợp; cân nhắc readiness theo khả năng publish |
| Consumer thuần không phục vụ HTTP | Theo dõi reconnect, lag, số message đã xử lý; không trông vào readiness để pause |
| Kafka Streams trong rebalance/restore | Theo dõi task/state; tạm hạn chế API phụ thuộc state |
| Secret/ACL sai sau credential rotation | Chẩn đoán và refresh/restart client theo runbook |
| Destination bị xóa hoặc queue arguments thay đổi | Điều tra provisioning drift; tránh retry vô hạn mà không alert |

Không phải mọi lỗi của mọi binder đều tự recover. Một số lỗi xảy ra ở lúc tạo binding cần rebind/restart; một số kết nối đang hoạt động có thể tự hồi phục. Hãy xác minh với phiên bản và topology thực tế.

Reconnect hoặc redelivery có thể tạo duplicate; cần event ID, idempotency hoặc outbox/inbox khi side effects quan trọng. “Ready” không có nghĩa exactly-once.

## 21. Graceful shutdown và rolling deployment

Một quy trình dừng an toàn:

1. Ngừng nhận HTTP traffic mới theo readiness/graceful shutdown nếu có web server.
2. Dừng trigger hoặc Supplier/scheduler phát sự kiện không cần thiết.
3. Cho in-flight xử lý hoàn tất trong giới hạn đã chọn.
4. Stop consumer binding/streams processor, flush và ack/commit theo binder.
5. Đóng client, giải phóng local state và kết nối.

Spring Boot graceful shutdown cho web server không tự bảo đảm mọi consumer message hoàn tất. Kafka, RabbitMQ, Pulsar và Kafka Streams có lifecycle/ack/commit khác nhau; phải kiểm thử riêng.

terminationGracePeriodSeconds cần đủ cho xử lý message dài, giao dịch đang mở và client shutdown. Nếu quá ngắn, pod bị SIGKILL có thể khiến message redeliver. Nếu quá dài, deploy bị trì hoãn khi tiến trình bị kẹt.

## 22. Ma trận kiểm thử sẵn sàng

| Kịch bản | Tín hiệu quan sát | Kỳ vọng |
| --- | --- | --- |
| Ứng dụng lên trước broker | Binding retry, Actuator health | Retry hoặc fail-fast đúng chủ đích, không báo business-ready sớm |
| TCP mở nhưng topic chưa tạo | Metadata/provision logs | Lỗi rõ ràng hoặc provision đúng quyền |
| Credential/ACL sai | Authentication/authorization failures | Không che lỗi với retry vô hạn |
| Consumer auto-startup=false | Actuator bindings | Binding STOPPED tới khi chủ động start |
| Kafka consumer rebalance | Group assignment, lag | Không restart vô ích do assignment đổi ngắn hạn |
| Kafka Streams cold restore | Store restore, thread state | Readiness state-dependent chỉ UP sau restore |
| Broker DOWN lúc đang xử lý | Liveness, error rate, retry | Không restart hàng loạt pod vì broker lỗi chung |
| Broker phục hồi | Binding/client state, xử lý mới | Reconnect hoặc rebind theo đúng khả năng binder |
| Rolling update và SIGTERM | In-flight ack/commit, redelivery | Không mất message, duplicate xử lý idempotent |
| Consumer readiness HTTP DOWN | Kafka/Rabbit/Pulsar consume metrics | Xác minh readiness không tự chặn consume |

Test Binder kiểm tra function/binding logic, nhưng không mô phỏng đầy đủ broker metadata, assignment hay recovery. Dùng Testcontainers Kafka, RabbitMQ hoặc Pulsar để kiểm tra trình tự thật.

Một kịch bản thực hành: start ứng dụng khi broker chưa chạy, quan sát trạng thái binding; bật broker; gửi một event có eventId cố định; tắt broker sau khi consumer hoạt động; khôi phục broker; kiểm tra liveness, readiness, lag và số side effects. Lặp lại khi có nhiều replica.

## 23. Theo dõi thời gian đến business-ready

Các timestamp và metrics nên thu thập:

- ApplicationStarted và ApplicationReady của Spring Boot.
- Thời điểm binding tạo được và vào trạng thái STARTED.
- Số lần/độ trễ binding creation retry.
- Kafka assignment/rebalance duration và consumer lag.
- RabbitMQ connection recovery và queue declaration failures.
- Pulsar lookup/subscription failures.
- Kafka Streams restore duration, thread state và changelog lag.
- Thời gian từ process start tới chức năng nghiệp vụ ready.
- Lỗi send/receive đầu tiên sau startup.

Đừng đưa synthetic publish/consume vào mỗi HTTP readiness probe production; nó tốn tài nguyên và có thể tạo side effects. Dùng metrics/lifecycle state được cập nhật và kiểm thử end-to-end có kiểm soát ở môi trường phù hợp.

## 24. Runbook khi pod chạy nhưng không sẵn sàng

1. Kiểm tra Kubernetes events, pod restart count và probe failures.
2. Đọc liveness/readiness group; xem custom health check nào đang DOWN.
3. Truy vấn /actuator/bindings (qua kênh quản trị được bảo vệ).
4. Kiểm tra bindingRetryInterval và autoStartup.
5. Kiểm tra broker DNS, advertised listeners/service-url, TLS/SASL, credentials và ACL.
6. Kiểm tra topic, partition, exchange, queue, subscription và schema.
7. Kiểm tra Kafka assignment/lag hoặc Pulsar subscription state.
8. Với Kafka Streams, kiểm tra state restoration, changelog và thread state.
9. Xác định có health check dependency chung quá nghiêm ngặt khiến tất cả replica mất readiness hay không.
10. Nếu broker đã phục hồi nhưng binding không tự recover, rebind hoặc restart theo runbook đã kiểm thử.

Không kết luận dịch vụ ổn chỉ vì HTTP /actuator/health trả 200. Đối chiếu binding lifecycle, broker metrics và kết quả gửi/nhận message thực tế.

## 25. Checklist production

- Xác định input/output bindings, destination và group/subscription.
- Kiểm tra broker DNS, network, credentials, ACL và provisioning.
- Cấu hình binding retry hoặc fail-fast đúng chính sách.
- Phân biệt retry binding và retry message.
- Tắt autoStartup khi thật sự cần điều phối consumer, có bước start rõ.
- Giám sát và bảo vệ Actuator bindings endpoint.
- Giữ liveness độc lập với broker outage thông thường.
- Định nghĩa readiness theo chức năng, không chỉ cổng HTTP.
- Nhớ Kubernetes readiness không pause broker consumers.
- Với Kafka Streams, tính thời gian assignment/state restore.
- Dùng Compose service_healthy khi cần, nhưng vẫn xử lý outage sau startup.
- Cấu hình Kubernetes startup/liveness/readiness và graceful termination phù hợp.
- Kiểm thử broker đến muộn, gián đoạn, reconnect và rolling deployment.
- Bảo đảm idempotency cho redelivery/duplicate.
- Theo dõi thời gian đến business-ready, error rates và consumer lag.

## Tài liệu tham khảo

- [Spring Cloud Stream — Binding Service Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-service-properties.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Binding visualization and control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html)
- [Spring Cloud Stream — Binder Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/health-indicator.html)
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Rabbit Binder Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/health-indicator.html)
- [Spring Cloud Stream — Kafka Streams Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/health-indicator.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring Boot Actuator — Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Docker Compose — Control startup and shutdown order](https://docs.docker.com/compose/how-tos/startup-order)

Cấu hình và khả năng health indicator phụ thuộc phiên bản Spring Boot, Spring Cloud Stream và binder. Đối chiếu BOM/release train đang dùng trước khi triển khai production.

## Kết luận

**Broker có thể truy cập**, **binding STARTED**, **processor đã sẵn sàng** và **application ready** là các trạng thái liên quan nhưng không đồng nhất. Spring Cloud Stream hỗ trợ retry khi tạo binding và quản lý lifecycle; Spring Boot cung cấp liveness/readiness; Kubernetes chỉ dùng readiness để điều phối network traffic tới pod. Việc phối hợp đúng giúp dịch vụ chịu được broker đến muộn, tránh restart liên tục khi broker lỗi chung và hạn chế nhận request hoặc chạy processor trước khi dữ liệu/trạng thái quan trọng thực sự sẵn sàng.
