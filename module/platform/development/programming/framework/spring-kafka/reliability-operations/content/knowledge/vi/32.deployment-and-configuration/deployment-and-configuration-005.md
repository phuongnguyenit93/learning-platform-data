# Cấu hình transactionIdPrefix theo instance trong Spring Kafka

## 1. Vấn đề khi nhiều instance cùng dùng Kafka transaction

Giả sử dịch vụ `orders-event-service` được triển khai thành ba replica:

```text
Kubernetes Deployment: orders-event-service (replicas=3)
    |
    +-- pod-A: đọc đơn hàng, gửi sự kiện Kafka theo transaction
    +-- pod-B: đọc đơn hàng, gửi sự kiện Kafka theo transaction
    +-- pod-C: đọc đơn hàng, gửi sự kiện Kafka theo transaction
```

Mỗi replica đều sử dụng Spring Kafka với `KafkaTemplate` hoặc một `@KafkaListener` có transaction. Nếu cả ba dùng một cấu hình như:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-
```

thì prefix trên **giống nhau** ở mọi replica. Khi producer factory tạo các producer giao dịch, mỗi producer cần một `transactional.id` hoàn chỉnh. Nếu hai producer đang hoạt động cuối cùng nhận **cùng `transactional.id`**, Kafka broker sẽ cho producer mới sở hữu một producer epoch cao hơn và **fence** producer cũ.

Hậu quả có thể là:

- Một pod đang xử lý message bất ngờ gặp `ProducerFencedException`.
- Giao dịch đang mở bị abort hoặc không thể commit.
- Listener transaction thất bại, message được xử lý lại theo chính sách offset/error handler.
- Lỗi xuất hiện không ổn định, thường xảy ra sau scale-out, rolling deployment hoặc restart.
- Dashboard ghi nhận transaction abort và Kafka listener failure dù logic nghiệp vụ không đổi.

**Mục tiêu của bài:** thiết kế `transactionIdPrefix` **khác nhau giữa các application instance có thể chạy đồng thời**, nhưng vẫn hỗ trợ producer caching, restart, scaling và việc broker fencing các producer cũ khi thật sự cần thiết.

Trong ngữ cảnh *Spring Kafka Reliability Operations → Deployment và cấu hình*, đây là **quyết định deployment**, không chỉ là đặt một property trong `application.yml`.

## 2. Hiểu đúng transactional.id và transactionIdPrefix

### 2.1. transactional.id là gì?

`transactional.id` là định danh transaction producer tại Kafka broker. Nó giúp broker và transaction coordinator nhận ra các phiên producer có cùng danh tính logic, phục vụ việc khôi phục và **fencing phiên cũ**.

Trong Kafka client thuần, một transactional producer thường được tạo với:

```java
Properties properties = new Properties();
properties.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "kafka:9092");
properties.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class);
properties.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class);
properties.put(
        ProducerConfig.TRANSACTIONAL_ID_CONFIG,
        "orders-prod-instance-01-producer-0");

KafkaProducer<String, String> producer =
        new KafkaProducer<>(properties);

producer.initTransactions();
```

Ví dụ trên chỉ minh họa cấu hình producer Kafka client và giả định import từ `org.apache.kafka.clients.producer`, `java.util.Properties` và `org.apache.kafka.common.serialization.StringSerializer`. Khi dùng Spring Kafka, bạn **không cần** tự quản lý `initTransactions()`/`beginTransaction()`/`commitTransaction()` cho từng message nếu đã sử dụng transaction support của framework.

### 2.2. transactionIdPrefix là gì?

Trong Spring Kafka, `DefaultKafkaProducerFactory` hỗ trợ một **transaction ID prefix**. Từ prefix này, factory quản lý các producer có `transactional.id` cụ thể, thường kết hợp prefix với một suffix do factory/strategy quyết định.

Ví dụ khái niệm:

```text
Spring Kafka transactionIdPrefix:
    orders-prod-podA-

Transactional IDs do producer factory tạo:
    orders-prod-podA-0
    orders-prod-podA-1
    orders-prod-podA-2
```

Các suffix trong ví dụ thể hiện ý tưởng, **không phải cam kết thứ tự suffix của tất cả phiên bản Spring Kafka**. Mục tiêu là đảm bảo tập ID sinh ra ở pod A **không giao nhau** với tập ID đang được pod B hoặc pod C sử dụng.

Nói ngắn gọn:

\[
\text{transactional.id} = \text{transactionIdPrefix} + \text{suffix do factory quản lý}
\]

Đừng đặt `transactional.id` tĩnh vào producer properties của một factory được kỳ vọng tạo **nhiều transactional producer đồng thời** rồi mặc định Spring Kafka sẽ tự làm nó duy nhất.

### 2.3. Phân biệt các định danh thường bị nhầm

| Thuộc tính | Vai trò | Có cần riêng theo pod? |
| --- | --- | --- |
| `transactional.id` | Danh tính producer transaction tại broker; liên quan fencing | Phải không trùng giữa các producer **đồng thời không phải phiên thay thế có chủ đích** |
| `transactionIdPrefix` | Tiền tố Spring Kafka dùng để sinh transactional IDs | **Nên duy nhất theo instance/factory có thể chạy đồng thời** |
| `client.id` | Tên client cho metrics, logs và broker-side observability | Nên giúp phân biệt client, nhưng không thay cho transactional ID |
| `group.id` | Danh tính consumer group dùng để phân phối partition và commit offset | Thường **chung giữa các consumer instance** của một workload |
| `member.id` hoặc `group.instance.id` | Danh tính thành viên consumer group, có ý nghĩa riêng trong membership | Không phải transactional producer ID |
| Kubernetes `Pod UID` | Danh tính duy nhất của một Pod object | Có thể dùng làm thành phần instance ID |
| Kafka `producerId`/`producer epoch` | Danh tính và epoch do broker phối hợp quản lý | Không tự chọn để thay transactionIdPrefix |

Một lỗi phổ biến là đặt `transactionIdPrefix` bằng `group.id` vì “cùng consumer group thì cùng transaction”. Điều đó nhầm giữa **tập consumer chia partition** và **tập transactional producer cần nhận diện riêng**.

## 3. Kafka producer fencing diễn ra như thế nào?

Giả sử hai replica sử dụng cùng transactional ID hoàn chỉnh:

```text
T0  Pod A tạo producer:
    transactional.id = orders-prod-0
    broker cấp producer epoch = 7

T1  Pod A bắt đầu transaction và gửi message.

T2  Pod B tạo producer:
    transactional.id = orders-prod-0
    broker chấp nhận phiên mới, epoch tăng lên 8

T3  Pod A cố gửi thêm hoặc commit với epoch cũ.
    Broker từ chối phiên cũ -> producer bị fenced.

T4  Pod A phải coi producer cũ không còn hợp lệ.
```

Fencing là **cơ chế bảo vệ dữ liệu**, không phải bug của Kafka. Nó ngăn hai phiên producer có cùng danh tính logic đồng thời commit một cách mâu thuẫn.

Nhưng có hai tình huống khác nhau:

1. **Fencing có chủ đích:** một instance cũ đã mất quyền sở hữu hoặc bị thay thế; producer mới dùng lại đúng transactional ID logic để vô hiệu hóa producer “zombie” cũ.
2. **Fencing do cấu hình sai:** hai pod độc lập cùng thực hiện công việc bình thường nhưng vô tình nhận cùng transactional ID; pod này liên tục fence pod kia.

Mục tiêu của việc cấu hình prefix theo instance là **tránh tình huống thứ hai**, không vô hiệu hóa fencing bảo vệ producer khi có phiên cũ thực sự cần bị thay thế.

### Một prefix khác chưa có nghĩa mọi lỗi ProducerFencedException biến mất

Producer có thể bị fence vì một phiên mới với **cùng ID** xuất hiện do restart, do sử dụng chung factory sai cách hoặc do producer cache. Kafka còn có các exception khác như transaction timeout, authorization failure hoặc broker/network error. Hãy điều tra root cause theo logs và cấu hình thực tế, thay vì kết luận mọi lỗi transaction đều do prefix.

## 4. Quy tắc thiết kế prefix theo instance

Một quy ước prefix dễ hiểu:

```text
<environment>-<application>-<workload>-<instance-id>-
```

Ví dụ:

```text
prod-orders-event-service-order-consumer-7e42a3-
prod-orders-event-service-order-consumer-8f58c1-
staging-orders-event-service-order-consumer-42ad91-
```

Ở đây các ID rút gọn chỉ để minh họa; trong cấu hình thật, nên dùng một danh tính đủ mạnh và đủ ổn định để đảm bảo không trùng trong phạm vi Kafka cluster.

### 4.1. Điều kiện bắt buộc

- **Không trùng giữa các producer có thể hoạt động đồng thời** ở cùng Kafka cluster, trừ trường hợp cố ý dùng lại ID để thay thế một producer cũ.
- **Mỗi instance có namespace riêng cho suffix:** prefix pod A khác pod B, dù cả hai factory đều tạo suffix `0`, `1`, `2`.
- **Khác nhau giữa các workload sử dụng chung cluster** nếu chúng có khả năng tạo trùng ID: ví dụ một deployment billing và một deployment orders.
- **Được xác định trước khi producer factory bắt đầu tạo transactional producer**; không đổi prefix của một factory đang chạy theo từng message.
- **Không chứa credential hoặc thông tin nhạy cảm**; transactional ID có thể xuất hiện trong log, broker state và observability.

### 4.2. Instance ID lấy từ đâu?

| Nguồn | Điểm mạnh | Điểm cần lưu ý |
| --- | --- | --- |
| Kubernetes `metadata.uid` | Duy nhất cho mỗi Pod object; thích hợp Deployment/ReplicaSet | Thay khi Pod được tạo mới; cần biến môi trường Downward API |
| Kubernetes `metadata.name` | Dễ đọc trong log; khác giữa Pod đang tồn tại | Có thể được tái sử dụng với StatefulSet hoặc sau recreate; cần xét overlap và semantics |
| StatefulSet ordinal | Danh tính vị trí ổn định khi Pod được thay thế | Dùng lại prefix cùng ordinal cho mục đích replacement; cần bảo đảm không có hai worker active cùng danh tính |
| VM/container instance ID do orchestrator cấp | Có thể gắn với instance được quản lý | Cần chính sách cấp/thu hồi tránh trùng |
| UUID tạo khi process khởi động | Dễ duy nhất cho tiến trình mới, kể cả local | Đổi sau mỗi restart; không dùng để cố định ownership logic |
| Hostname | Tiện trong môi trường đơn giản | Không luôn duy nhất giữa container, đặc biệt khi cấu hình tĩnh hoặc nhiều process/host |
| Consumer group ID | Thường giống ở mọi replica | **Không phù hợp làm phần duy nhất của instance** |
| `client.id` | Dùng để quan sát client | Không bảo đảm unique transactional ID |

**Lựa chọn mặc định hợp lý cho Kubernetes Deployment:** dùng Pod UID, kết hợp app name và environment. Với StatefulSet muốn tận dụng khả năng fencing phiên cũ khi ordinal được thay thế, có thể chọn stable ordinal, nhưng phải thiết kế rollout/membership để không có hai instance hợp lệ cùng giữ danh tính trong cùng thời điểm.

### 4.3. Prefix phải nhất quán trong vòng đời một instance

Không tạo giá trị mới mỗi khi gửi message:

```java
// Không nên: mỗi message thay đổi transaction prefix.
String prefix = "orders-" + UUID.randomUUID() + "-";
```

Thiết kế như vậy phá ý nghĩa quản lý cache và danh tính producer của `DefaultKafkaProducerFactory`. Hãy tạo/cấp instance identity **một lần tại startup**, cấu hình prefix trước khi factory tạo producer, rồi dùng nhất quán trong suốt vòng đời instance.

Khác biệt quan trọng: **UUID một lần cho process là ổn**, còn **UUID mới cho từng transaction/message** là không đúng mục đích của prefix.

## 5. Cấu hình bằng Spring Boot application.yml

Với Spring Boot 3.x tích hợp Spring Kafka 3.x, thuộc tính thông dụng:

```yaml
spring:
  kafka:
    bootstrap-servers: "kafka-1:9092,kafka-2:9092,kafka-3:9092"
    producer:
      transaction-id-prefix: "orders-${APP_ENV:local}-${INSTANCE_ID:local-dev}-"
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
```

Trong project Spring Boot, `${APP_ENV:local}` và `${INSTANCE_ID:local-dev}` là **property placeholders**. Phần sau dấu hai chấm là fallback nếu không có biến môi trường hoặc property tương ứng.

**Cảnh báo với fallback cố định:** `local-dev` chỉ an toàn khi bạn chạy đúng **một instance local** với cùng cấu hình. Nếu chạy hai process ở local hoặc deploy production mà quên cung cấp `INSTANCE_ID`, chúng sẽ dùng cùng prefix và có nguy cơ fencing. Vì vậy environment production nên **bắt buộc cung cấp instance ID**, không dựa vào fallback giá trị tĩnh.

Một biến thể dành cho local nhiều process là tạo một ID tại startup hoặc cung cấp từ launcher:

```bash
APP_ENV=dev INSTANCE_ID=developer-one ./mvnw spring-boot:run
```

Trên Windows/PowerShell, đặt biến môi trường theo cú pháp PowerShell hoặc truyền property qua cách chạy Spring Boot phù hợp. Không dùng một tên host hoặc instance ID giả cố định ở nhiều JVM cùng kết nối một Kafka cluster.

### Spring Boot tự cấu hình transaction như thế nào?

Khi `spring.kafka.producer.transaction-id-prefix` được thiết lập và các auto-configuration cần thiết có mặt, Spring Boot có thể cấu hình transactional `ProducerFactory` và `KafkaTransactionManager` phù hợp với Kafka producer, giúp `KafkaTemplate` thực hiện send trong transaction.

Các thành phần **có thể được ứng dụng override bằng bean tự khai báo**. Nếu bạn đã tự tạo `ProducerFactory` hoặc `KafkaTransactionManager`, cần đảm bảo prefix và transaction manager sử dụng **cùng một factory**; không được giả định mọi bean custom vẫn nhận toàn bộ property auto-config của Boot.

Việc đặt prefix cho producer **không tự biến toàn bộ logic business thành một Kafka transaction**. Bạn vẫn phải thực thi send trong transaction scope hoặc cấu hình listener container transaction cho flow consume-process-produce.

## 6. Kubernetes: cấp Pod UID và đưa vào transactionIdPrefix

### 6.1. Tại sao Pod UID phù hợp với Deployment?

Một Kubernetes Deployment có thể có nhiều Pod tồn tại đồng thời, bao gồm cả Pod từ phiên bản cũ và mới trong rolling update:

```text
before rollout:
  orders-abc-1  uid=1111
  orders-abc-2  uid=2222

during rollout:
  orders-abc-1  uid=1111  (old Pod vẫn chạy)
  orders-abc-2  uid=2222  (old Pod vẫn chạy)
  orders-def-1  uid=3333  (new Pod đã chạy)
  orders-def-2  uid=4444  (new Pod đã chạy)
```

Nếu prefix chỉ là `orders-prod-`, tất cả pod có thể tạo trùng transactional IDs. Nếu prefix bao gồm Pod UID, tập IDs được tách theo pod ngay cả lúc rollout có overlap.

### 6.2. Deployment manifest minh họa

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-event-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-event-service
  template:
    metadata:
      labels:
        app: orders-event-service
    spec:
      containers:
        - name: app
          image: example/orders-event-service:1.0
          env:
            - name: APP_ENV
              value: "prod"
            - name: INSTANCE_ID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.uid
            - name: SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX
              value: "orders-prod-$(INSTANCE_ID)-"
```

Kubernetes hỗ trợ mở rộng biến môi trường được khai báo **trước** trong giá trị của biến sau bằng cú pháp `$(VARIABLE_NAME)`. Ở ví dụ, `INSTANCE_ID` phải xuất hiện trước `SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX`. Chuỗi `$(INSTANCE_ID)` được kubelet thay bằng Pod UID thực khi khởi tạo container.

Spring Boot relaxed binding ánh xạ biến môi trường `SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX` sang thuộc tính `spring.kafka.producer.transaction-id-prefix`. Khi dùng cách này, biến môi trường từ Deployment có thể override giá trị mặc định trong `application.yml`.

**Không đồng thời cung cấp hai nguồn prefix độc lập mà không có chủ đích.** Ví dụ nếu bạn đặt `application.yml` dùng `INSTANCE_ID` và Deployment cũng đặt `SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX`, cần biết property nào được ưu tiên. Để dễ kiểm soát, chọn một quy ước deploy duy nhất.

### 6.3. Một cấu hình tối giản hơn

Nếu muốn logic prefix nằm trong ứng dụng:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: "orders-${APP_ENV}-${INSTANCE_ID}-"
```

Và Kubernetes chỉ cần:

```yaml
env:
  - name: APP_ENV
    value: "prod"
  - name: INSTANCE_ID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
```

Ở production, không đặt fallback cho `APP_ENV`/`INSTANCE_ID` để ứng dụng fail startup nếu thiếu biến. Điều này tốt hơn việc vô tình dùng cùng prefix `orders-local-local-dev-` cho toàn bộ deployment.

**Gợi ý:** chọn tên prefix đủ ngắn để quan sát dễ dàng; không cần đưa toàn bộ thông tin deployment, Git SHA hoặc timestamp vào prefix nếu Pod UID đã đảm bảo uniqueness. Version ứng dụng nên đặt trong log/trace/metrics, không cần biến thành phần thay đổi liên tục của transactional identity.

## 7. StatefulSet, stable identity và cơ chế thay thế producer

Với StatefulSet, tên Pod và ordinal thường ổn định theo vị trí, ví dụ `orders-worker-0`, `orders-worker-1`. Có hai chiến lược chính:

**Chiến lược A — Prefix theo Pod UID:**

```text
orders-prod-uid-1111-
orders-prod-uid-2222-
```

Mỗi Pod object mới có prefix mới. Ưu điểm là tách biệt giữa các instance có thể overlap. Nhược điểm là khi thay Pod, transactional IDs cũ không được sử dụng lại để fence producer cũ theo cùng danh tính. Broker vẫn quản lý timeout và transaction state, nhưng không có cùng-ID replacement fencing giữa các UID.

**Chiến lược B — Prefix theo ordinal/stable slot:**

```text
orders-prod-worker-0-
orders-prod-worker-1-
```

Khi worker-0 được thay thế, producer mới với cùng suffix/transactional ID có thể fence producer cũ còn tồn tại. Điều này hữu ích nếu toàn bộ logic ownership cam kết **chỉ một worker-0 hợp lệ tại một thời điểm**. Tuy nhiên:

- Phải có chính sách điều phối ownership khi node/pod cũ chưa thực sự dừng.
- Nếu hai process cùng nghĩ mình là worker-0, producer sẽ liên tục fence nhau.
- Nếu suffix strategy/cache không sinh cùng suffix vào cùng thời điểm, không nên giả định mọi phiên cũ đều bị fence ngay.
- Không dùng prefix ổn định như một cơ chế leader election đầy đủ; cần phối hợp với membership/lease và business idempotency.

**Tiêu chí:** nếu mục tiêu chính là **không va chạm trong Deployment scale-out**, Pod UID là lựa chọn đơn giản. Nếu có yêu cầu thay thế phiên cũ theo danh tính logic cố định, dùng stable ID với quy trình ownership và fencing có chủ đích.

## 8. Khi một instance có nhiều producer đồng thời

Một prefix duy nhất **theo instance** chưa hoàn tất toàn bộ bài toán. Trong cùng một Spring Boot instance, có thể có nhiều transaction đồng thời:

```text
Pod A: prefix = orders-prod-podA-
    |
    +-- listener thread 1 --> producer suffix 0
    +-- listener thread 2 --> producer suffix 1
    +-- listener thread 3 --> producer suffix 2
    +-- KafkaTemplate transaction từ service --> producer suffix 3
```

`DefaultKafkaProducerFactory` sử dụng cache/strategy để cung cấp transactional producer cho từng transaction cần thiết. Spring Kafka đã thay đổi cách phân phối và tái sử dụng suffix theo phiên bản, vì vậy cần sử dụng các tùy chọn tương ứng **với Spring Kafka thực tế của dự án**.

Điều cần hiểu về thiết kế:

1. **Prefix tách các instance/factory.**
2. **Suffix tách các producer của cùng factory** khi cần nhiều giao dịch đồng thời.
3. **Producer cache** và mức concurrency phải tương thích.
4. Khi không còn producer khả dụng trong cache/suffix pool, transaction có thể thất bại hoặc phải chờ/tái thử theo cơ chế được cấu hình.

### 8.1. Kafka listener concurrency

Giả sử:

```yaml
spring:
  kafka:
    listener:
      concurrency: 6
```

và một listener container được cấu hình transaction với cùng producer factory. Ở những phiên bản Spring Kafka dùng transaction producer caching với giới hạn suffix, cần đảm bảo cache/suffix capacity **đủ cho số transaction có thể hoạt động đồng thời**. Nếu có các transaction khởi phát từ `KafkaTemplate` bên ngoài listener, cần xét thêm nhu cầu ấy.

Không suy từ `concurrency=6` rằng phải có đúng sáu `transactional.id` trong mọi ứng dụng: số lượng transaction đồng thời phụ thuộc container, partition assignment, listener setup, producer usage, nested operations và phiên bản framework. Nhưng giới hạn quá thấp so với concurrency là nguyên nhân thường gặp của lỗi producer không khả dụng.

### 8.2. TransactionIdSuffixStrategy và maxCache

Ở Spring Kafka 3.2+, cơ chế `TransactionIdSuffixStrategy` cung cấp cách quản lý suffix cho transactional producer; phiên bản tương ứng có `DefaultTransactionIdSuffixStrategy` và giới hạn cache/suffix pool. Trong một số cấu hình, khi không còn suffix khả dụng, bạn có thể gặp `NoProducerAvailableException`.

Vì vậy khi nâng version:

- Xem tài liệu producer factory transaction của **đúng Spring Kafka version**.
- Xác định suffix strategy mặc định và khả năng tái sử dụng suffix.
- Đối chiếu `maxCache` với concurrency thực tế.
- Test scale-out, rolling restart và các transaction đồng thời.

**Không nhầm `NoProducerAvailableException` với fencing giữa pod:** một lỗi là nguồn producer/suffix trong một factory bị cạn; lỗi còn lại là broker từ chối producer cũ vì trùng transactional identity. Hai hiện tượng cần cách xử lý khác nhau.

## 9. Đặt prefix ở ProducerFactory bằng Java

Nếu không dùng auto-configuration property của Boot, có thể tự tạo `DefaultKafkaProducerFactory` và đặt prefix **trước khi factory được sử dụng**.

Ví dụ Spring Kafka 3.x, Java 17+, sử dụng serializer kiểu String:

```java
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Configuration
public class KafkaTxConfiguration {

    @Bean
    ProducerFactory<String, String> orderProducerFactory(
            @Value("${spring.kafka.bootstrap-servers}") String bootstrap,
            @Value("${app.kafka.instance-tx-prefix}") String txPrefix) {

        Map<String, Object> configs = new HashMap<>();
        configs.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrap);
        configs.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        configs.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        configs.put(ProducerConfig.ACKS_CONFIG, "all");

        DefaultKafkaProducerFactory<String, String> factory =
                new DefaultKafkaProducerFactory<>(configs);

        factory.setTransactionIdPrefix(txPrefix);
        return factory;
    }

    @Bean
    KafkaTemplate<String, String> orderKafkaTemplate(
            ProducerFactory<String, String> orderProducerFactory) {

        return new KafkaTemplate<>(orderProducerFactory);
    }

    @Bean
    KafkaTransactionManager<String, String> orderKafkaTransactionManager(
            ProducerFactory<String, String> orderProducerFactory) {

        return new KafkaTransactionManager<>(orderProducerFactory);
    }
}
```

Configuration:

```yaml
app:
  kafka:
    instance-tx-prefix: "orders-${APP_ENV}-${INSTANCE_ID}-"
spring:
  kafka:
    bootstrap-servers: "kafka:9092"
```

**Chọn một trong hai cách:**

- Cách A: dùng `spring.kafka.producer.transaction-id-prefix` để Spring Boot auto-configure.
- Cách B: chủ động tạo producer factory và transaction manager như ví dụ trên.

Đừng khai báo hai factory cạnh tranh nhau mà không rõ `KafkaTemplate`, listener container và transaction manager đang sử dụng factory nào. Trong ứng dụng có nhiều producer factory, mỗi factory cần prefix phân biệt nếu chúng có thể tạo transactional producer với suffix giao nhau.

### Không hardcode transactional.id trong map properties

Trong cách cấu hình producer factory của Spring Kafka:

```java
// Tránh cấu hình một transactional.id cố định cho mọi producer
// rồi lại kỳ vọng factory tạo các ID độc lập.
configs.put(
        ProducerConfig.TRANSACTIONAL_ID_CONFIG,
        "orders-shared-id");
```

Thay vì vậy, cấp prefix vào `DefaultKafkaProducerFactory` để framework quản lý các producer và suffix tương ứng.

## 10. Gửi message trong transaction

Đặt prefix chỉ mới bật khả năng tạo transactional producer. Để các message được commit/abort như một đơn vị Kafka transaction, cần dùng transaction scope.

### 10.1. KafkaTemplate.executeInTransaction

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishOrderAndAudit(
            String orderId, String payload) {

        kafkaTemplate.executeInTransaction(operations -> {
            operations.send("orders.events", orderId, payload);
            operations.send(
                    "orders.audit",
                    orderId,
                    "published:" + orderId);
            return null;
        });
    }
}
```

Hai sends nằm trong cùng Kafka transaction do `executeInTransaction` quản lý. Nếu một exception khiến transaction bị abort, consumer có `isolation.level=read_committed` sẽ không nhìn thấy các bản ghi bị abort trong phạm vi semantics Kafka transactions.

**Không hiểu nhầm “atomic” thành một transaction cho tất cả hệ thống:** đoạn này chỉ quản lý message/offset trong Kafka theo phạm vi transaction. Nó không tự đưa các thao tác database, HTTP API hoặc object storage vào cùng một ACID transaction.

### 10.2. @Transactional với KafkaTransactionManager

Ứng dụng cũng có thể dùng `@Transactional` gắn với Kafka transaction manager:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.kafka.core.KafkaTemplate;

@Service
public class TransactionalPublisher {

    private final KafkaTemplate<String, String> template;

    public TransactionalPublisher(
            KafkaTemplate<String, String> template) {
        this.template = template;
    }

    @Transactional("orderKafkaTransactionManager")
    public void publish(String orderId, String payload) {
        template.send("orders.events", orderId, payload);
        template.send("orders.audit", orderId, "audit");
    }
}
```

Ví dụ này dùng bean có tên `orderKafkaTransactionManager` như ở cấu hình Java phần 9. Nếu bạn dùng Spring Boot auto-configured manager, tên bean thực tế có thể khác, nên cần đối chiếu Spring context. `@Transactional` yêu cầu cấu hình transaction management phù hợp và được gọi qua proxy Spring; gọi nội bộ cùng object (*self-invocation*) có thể bỏ qua interceptor.

Không sử dụng một `DataSourceTransactionManager` mặc định rồi giả định đó là Kafka transaction. Trong ứng dụng có nhiều transaction manager, qualifier rõ ràng giúp tránh nhầm ranh giới transaction.

## 11. Consume-process-produce và exactly-once semantics

Một use case phổ biến:

```text
orders.input topic
       |
       v
  Kafka @Listener
       |
       v
  transform event
       |
       v
  orders.output topic
       |
       v
  commit consumer offset
```

Khi listener container được cấu hình với Kafka transaction manager/producer factory đúng cách, output records và offsets đã xử lý có thể được đưa vào **cùng Kafka transaction**. Trên broker, một transaction bị abort không làm output của nó hiển thị cho `read_committed` consumer, và offset của consumer group không được commit như một lần xử lý thành công.

Đây là phần quan trọng của **exactly-once semantics (EOS) trong Kafka-to-Kafka flow**. Nó không có nghĩa:

- Một message không bao giờ được xử lý lại ở Java.
- HTTP service chỉ được gọi đúng một lần.
- Ghi database nằm trong cùng Kafka transaction.
- Topic output không bao giờ có duplicate từ những nguồn/flow ngoài transaction.

Thực tế listener có thể xử lý lại record sau rollback. Vì vậy, side effect ngoài Kafka vẫn cần idempotency hoặc mô hình outbox.

### 11.1. Consumer đọc bản ghi đã commit

Đối với consumer cần bỏ qua các message bị abort:

```yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
```

`read_committed` không đồng nghĩa consumer sẽ chỉ nhận bản ghi của một producer cụ thể; nó kiểm soát việc hiển thị records thuộc transaction chưa commit hoặc đã abort. Các message được gửi không dùng transaction vẫn có thể được đọc theo semantics bình thường.

### 11.2. Listener container cần transaction configuration

Producer có `transactionIdPrefix` **không có nghĩa mọi Kafka listener tự động thực hiện consume-process-produce theo EOS**. Phải xác nhận listener container factory đang sử dụng một `KafkaTransactionManager` phù hợp và container properties được cấu hình theo Spring Kafka version.

Với Spring Kafka 3.x, một cấu hình custom listener container factory cần nối transaction manager tương ứng vào container (API có thể khác giữa các minor version). Nếu sử dụng Spring Boot auto-configuration, cần xác minh factory đang được dùng có nhận đúng manager hay không, nhất là khi ứng dụng tự tạo nhiều producer factory/listener factory.

Ví dụ listener đơn giản:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    private final KafkaTemplate<String, String> template;

    public OrderEventListener(
            KafkaTemplate<String, String> template) {
        this.template = template;
    }

    @KafkaListener(
            topics = "orders.input",
            groupId = "orders-processors")
    public void onOrder(String payload) {
        String orderId = extractOrderId(payload);
        template.send("orders.output", orderId, payload);
    }

    private String extractOrderId(String payload) {
        // Ví dụ minh họa; production cần parser và validation phù hợp.
        return payload;
    }
}
```

**Chỉ riêng annotation ở trên không chứng minh EOS.** Cần transaction-enabled listener container, đúng producer factory, đúng consumer group/offset management và consumer downstream `read_committed`. Nếu listener chạy không có Kafka transaction, lời gọi `template.send(...)` có thể thất bại vì template dùng transactional producer ngoài transaction hoặc được xử lý theo cấu hình khác; hãy test ranh giới transaction thực tế.

## 12. Transaction ID và vòng đời rolling deployment

Một đợt rolling update có thể giữ phiên bản cũ chạy song song phiên bản mới:

```text
             Rolling update

Old pod A (UID=A)  ------------------- shutdown
Old pod B (UID=B)  ----------- shutdown
New pod C (UID=C)       -------------------------
New pod D (UID=D)              ------------------

Prefixes:
    orders-prod-A-
    orders-prod-B-
    orders-prod-C-
    orders-prod-D-
```

Các prefix tách biệt giúp các transactional producers không tự fence nhau chỉ vì đang trong cùng deployment. Tuy nhiên, hệ thống vẫn cần xem xét:

- Consumer group rebalance khi pod tham gia/rời nhóm.
- Thời gian xử lý transaction so với `max.poll.interval.ms` và `transaction.timeout.ms`.
- Shutdown graceful để tránh abort transaction không cần thiết.
- Khả năng record được xử lý lại sau rebalance hoặc crash.
- Side effect của ứng dụng cần idempotent.

Đừng dùng một prefix độc nhất **theo deployment version** như `orders-v1-` hay `orders-v2-` nếu trong một version có nhiều pod: tất cả pod cùng version vẫn chia sẻ prefix.

### Rolling restart có thể làm prefix thay đổi

Với Pod UID, prefix sẽ đổi khi Pod bị recreate. Điều đó tách instances nhưng cũng có thể để lại transactional ID cũ ở broker đến khi transaction coordinator hoàn tất thời hạn/cleanup theo cấu hình Kafka.

Đây thường là đánh đổi chấp nhận được cho Deployment muốn tránh va chạm. Nếu hệ thống cần tái sử dụng một stable transactional ID để fence zombie producer, cần thiết kế stable ownership thay vì chỉ chọn UID ngẫu nhiên.

## 13. Transaction timeout, expiration và producer cache

Ngoài uniqueness, một hệ thống Kafka transaction cần hiểu các thời hạn:

| Cấu hình/khái niệm | Liên quan đến | Rủi ro |
| --- | --- | --- |
| `transaction.timeout.ms` của producer | Giới hạn thời gian một transaction có thể tồn tại | Transaction chạy quá lâu có thể bị broker abort |
| Broker `transaction.max.timeout.ms` | Giới hạn timeout transaction broker chấp nhận | Producer cấu hình timeout quá lớn có thể bị từ chối |
| Broker `transactional.id.expiration.ms` | Expiration của state transactional ID không còn hoạt động | Producer cached idle quá lâu có thể gặp vấn đề khi reuse |
| `DefaultKafkaProducerFactory` cache | Tái sử dụng producer transaction | Cần quản lý producer life cycle và số lượng transaction đồng thời |
| Spring Kafka `maxAge` trên producer factory | Chủ động loại producer idle/cũ trước một giới hạn tuổi | Có thể tránh reuse producer đã bị broker expire |

Spring Kafka hỗ trợ cấu hình tuổi tối đa producer cached ở các phiên bản có `DefaultKafkaProducerFactory#setMaxAge(Duration)`. Khi một transactional producer đã idle quá lâu so với broker expiration, refresh trước khi reuse có thể tránh một số lỗi fencing không mong đợi.

**Không giải quyết expiration bằng cách tạo prefix mới mỗi lần gửi.** Prefix theo instance giải quyết việc phân biệt danh tính; refresh producer và kiểm soát tuổi cache giải quyết một vấn đề lifecycle khác.

### Một transaction không nên bao trùm công việc quá dài

```text
beginTransaction()
  gọi API chậm 4 phút
  xử lý file lớn 10 phút
  gửi Kafka
commitTransaction()
```

Kiểu transaction quá dài có thể vượt timeout, block consumer progress và tăng xác suất abort. Nên giữ phần công việc bên trong Kafka transaction được bounded; xử lý nặng ở ngoài hoặc chia đơn vị theo kiến trúc phù hợp, vẫn giữ semantics offset/output rõ ràng.

## 14. Multi-instance không đồng nghĩa shared producer factory

Một số hệ thống dùng:

- Nhiều `KafkaTemplate` trong cùng process.
- Nhiều `ProducerFactory` cho các topic hoặc cluster khác nhau.
- Nhiều listener container factory.
- Một dịch vụ vừa consume-process-produce, vừa publish thông báo từ scheduler.

### 14.1. Cùng factory

Nếu hai `KafkaTemplate` cùng tham chiếu **một `DefaultKafkaProducerFactory`** đã cấu hình prefix, factory quản lý producer cache của chúng trong phạm vi đã thiết kế. Cần tính mức concurrency chung.

### 14.2. Nhiều factory

Nếu hai factory độc lập trong **cùng instance** cùng có prefix `orders-prod-podA-`, chúng có thể tạo suffix giao nhau và dẫn tới trùng `transactional.id`. Khi có nhiều transactional factories cùng gửi vào **một Kafka cluster**, nên cấp namespace prefix riêng:

```text
orders-prod-podA-events-
orders-prod-podA-audit-
```

Nếu factory phục vụ Kafka clusters khác nhau, scope uniqueness nằm trong từng cluster, nhưng vẫn nên đặt tên rõ để logs/metrics dễ điều tra.

### 14.3. Dùng chung prefix với ứng dụng khác

Hai ứng dụng có thể khác namespace Kubernetes nhưng cùng bootstrap vào một Kafka cluster. Chỉ dùng hostname/pod name mà không có app/workload prefix có thể chưa đủ tránh xung đột ID trên mọi môi trường. Quy ước nên đặt app/service/workload trước instance ID:

```text
prod-order-sync-podA-
prod-billing-export-podA-
```

Kafka transaction coordinator không biết đây là “hai microservice khác nhau” nếu chúng tự chọn cùng transactional ID.

## 15. Monitoring và logging transaction identity

Khi lỗi fencing xảy ra, cần biết **producer nào và instance nào** đang cạnh tranh transaction identity.

Các field log phù hợp:

```text
service
environment
podName
podUid / instanceId
transactionIdPrefix
producer clientId
topic
consumerGroupId
partition
listenerId
exceptionClass
transactionOutcome
deploymentVersion
```

Ví dụ event:

```json
{
  "event": "kafka_transaction_failed",
  "service": "orders-event-service",
  "environment": "production",
  "instanceId": "pod-uid-A",
  "transactionIdPrefix": "orders-prod-pod-uid-A-",
  "consumerGroupId": "orders-processors",
  "exceptionClass": "ProducerFencedException",
  "transactionOutcome": "ABORTED"
}
```

Đây là schema log minh họa. Không giả định Spring Kafka tự ghi tất cả các trường như trên; cần logging/instrumentation phù hợp.

**Lưu ý cardinality:** instance ID và transactional ID có thể thay đổi rất nhiều khi deploy hoặc scale. Chúng hữu ích ở **logs/traces**, nhưng không nên luôn dùng làm label metric thời gian dài. Các metric tổng hợp nên dùng `service`, `environment`, `listenerId`, `errorCategory` và trạng thái transaction có tập giá trị giới hạn.

Các tín hiệu nên giám sát:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `ProducerFencedException` tăng | Trùng transactional ID hoặc replacement/fencing cần điều tra |
| Transaction abort tăng | Timeout, lỗi ứng dụng hoặc phối hợp producer/consumer bất thường |
| `NoProducerAvailableException` | Cache/suffix pool không đáp ứng concurrency |
| Listener failures / error handler activations | Message bị lỗi, có thể được reprocess |
| Consumer lag | Flow lỗi làm backlog tăng |
| Transaction duration | Transaction gần timeout hoặc downstream chậm |
| Restarts/rolling update | Bối cảnh để tương quan sự cố |
| Last successful processing | Phát hiện service không còn hoàn tất transaction |

Các tên metric cụ thể phụ thuộc Kafka client JMX metrics, Micrometer, Spring Kafka và exporter. Không giả định tất cả phiên bản đều có cùng metric name; nên kiểm tra metric được hệ thống thật xuất ra khi triển khai.

## 16. Kiểm thử việc tạo prefix theo instance

Hãy tách logic tạo prefix thành một hàm có thể unit test thay vì viết rải rác trong YAML hoặc nhiều config class.

### 16.1. Hàm xây prefix có contract rõ

```java
package com.example.kafka.config;

import java.util.Objects;

public final class TransactionPrefix {

    private TransactionPrefix() {}

    public static String create(
            String environment,
            String application,
            String instanceId) {

        return valid(environment, "environment")
                + "-" + valid(application, "application")
                + "-" + valid(instanceId, "instanceId") + "-";
    }

    private static String valid(String value, String name) {
        Objects.requireNonNull(value, name + " is required");
        if (value.isBlank() || !value.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException(
                    name + " must contain only letters, digits, _ or -");
        }
        return value;
    }
}
```

Đây là một naming convention **của ứng dụng**, không phải giới hạn bắt buộc của Kafka. Mục tiêu là dễ log, dễ theo dõi và từ chối instance ID rỗng trước khi producer factory được khởi tạo.

### 16.2. Unit test JUnit 5

```java
package com.example.kafka.config;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class TransactionPrefixTest {

    @Test
    void twoInstancesHaveDifferentPrefixes() {
        String first = TransactionPrefix.create(
                "prod", "orders", "podA");
        String second = TransactionPrefix.create(
                "prod", "orders", "podB");

        assertNotEquals(first, second);
        assertEquals("prod-orders-podA-", first);
        assertEquals("prod-orders-podB-", second);
    }

    @Test
    void sameInstanceHasStablePrefix() {
        String first = TransactionPrefix.create(
                "prod", "orders", "podA");
        String again = TransactionPrefix.create(
                "prod", "orders", "podA");

        assertEquals(first, again);
    }

    @Test
    void missingInstanceIdFailsFast() {
        assertThrows(IllegalArgumentException.class,
                () -> TransactionPrefix.create(
                        "prod", "orders", ""));
    }

    @Test
    void differentWorkloadsDoNotShareNamespace() {
        assertNotEquals(
                TransactionPrefix.create("prod", "orders", "podA"),
                TransactionPrefix.create("prod", "billing", "podA")
        );
    }
}
```

Những test này xác nhận logic naming; chúng **không chứng minh transaction Kafka đã hoạt động** hoặc producer không bao giờ bị fence. Cần integration test với broker cho behavior thật.

## 17. Integration test với Kafka broker

Một chiến lược test có thể dùng `@EmbeddedKafka` hoặc Testcontainers Kafka, tùy môi trường và độ phức tạp. Với Kafka transactions, broker test phải có cấu hình transaction state phù hợp môi trường một broker, nếu không test có thể fail do internal transaction state topic chứ không phải do prefix.

### 17.1. Kiểm tra hai instance đồng thời

Mô hình:

```text
Test broker
   |
   +-- ProducerFactory A:
   |     prefix = test-orders-A-
   |
   +-- ProducerFactory B:
         prefix = test-orders-B-
```

Các bước:

1. Tạo hai transactional producer factories độc lập, mỗi factory có prefix khác.
2. Tạo `KafkaTemplate` tương ứng.
3. Chạy nhiều transaction có overlap từ A và B.
4. Gửi các message có key khác nhau vào topic test.
5. Dùng consumer `read_committed`, xác minh output được commit và không xuất hiện fencing do trùng ID.
6. Dừng/đóng producer factories và kiểm tra cleanup.

Với test cạnh tranh identity, nên cố tình cho hai factory nhận cùng prefix ở một kịch bản **chỉ trên broker test**, rồi quan sát producer fencing khi chúng tạo cùng transactional ID. Test này có thể cần kiểm soát thời điểm tạo producer và suffix strategy, vì **chia sẻ prefix chưa chắc ngay lập tức tạo ID giống nhau** trong tất cả phiên bản/cấu hình.

### 17.2. Kiểm tra commit và abort

```text
Transaction A:
  send record 1
  send record 2
  commit

Transaction B:
  send record 3
  abort

read_committed consumer:
  thấy record 1, 2
  không thấy record 3 bị abort
```

Không dùng `read_uncommitted` để assert message abort bị ẩn; isolation level phải đúng với contract test.

### 17.3. Test rolling restart và scaling

Thử:

- 1 → 3 → 5 replicas với prefix theo Pod UID.
- Rolling update tạo overlap old/new Pods.
- Restart một Pod, cấp identity mới theo mô hình Deployment.
- Restart stable slot theo StatefulSet, kiểm tra fencing có chủ đích.
- Tăng listener concurrency và tạo nhiều transaction đồng thời; quan sát producer cache/suffix exhaustion.

Các test nên ghi nhận prefix thực của từng instance và broker errors, không chỉ kiểm tra end-to-end message count. Cần phân biệt failure do consumer group rebalance, transaction timeout, network và producer fencing.

## 18. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Scale-out rồi xuất hiện `ProducerFencedException` | Nhiều replica dùng prefix cố định, suffix trùng | Thêm instance ID duy nhất vào prefix |
| Không lỗi khi một replica, lỗi khi chạy hai replica | Chia sẻ transactional identity | Kiểm tra prefix và producer factories của cả hai |
| Rolling update làm transaction abort tăng | Old/new pods overlap, trùng prefix hoặc transaction bị ngắt | Kiểm tra Pod identity, rollout, graceful shutdown và broker logs |
| `NoProducerAvailableException` | Cache/suffix pool cạn khi concurrency cao | Xem `maxCache`/suffix strategy theo Spring Kafka version |
| Fenced sau thời gian idle dài | Cached producer có thể đã bị broker expire | Xem broker `transactional.id.expiration.ms` và factory `maxAge` |
| Prefix đúng ở YAML nhưng vẫn giống ở mọi Pod | Biến môi trường override sai hoặc không expand | Xác minh effective property lúc startup và Pod UID |
| Có hai KafkaTemplate khác nhau nhưng cùng prefix | Hai producer factories độc lập cùng namespace | Phân biệt prefix theo factory/workload |
| Consumer đọc thấy record từ transaction abort | `isolation.level=read_uncommitted` hoặc flow không dùng transaction | Cấu hình `read_committed` và xác minh transaction scope |
| Gửi Kafka transactional nhưng DB bị duplicate | Kafka transaction không bao gồm DB | Idempotency/outbox, ranh giới dữ liệu rõ ràng |
| Job chạy lại tạo trùng business event | Transaction không thay thế business deduplication | Dùng business key/idempotency theo thiết kế |
| Prefix đổi cho từng message | Tạo UUID mỗi send, không dùng lifecycle factory | Tạo prefix một lần lúc startup |
| Pod UID có nhưng Kafka vẫn dùng prefix cũ | Custom ProducerFactory không đọc Boot property | Cấu hình trực tiếp đúng factory và manager |
| Chạy local hai JVM gây fencing | Fallback `local-dev` cố định | Gán INSTANCE_ID riêng cho từng process |
| Chạy dưới cùng consumer group nhưng đổi group.id để tránh fencing | Nhầm consumer membership với producer identity | Giữ group ID theo consumer design, đổi prefix |

## 19. Quy trình điều tra một sự cố producer fencing

Khi log xuất hiện `ProducerFencedException` hoặc transaction commit thất bại:

1. **Xác định instance:** lấy tên service, environment, pod name/UID, deployment version và thời điểm lỗi.
2. **Xác định prefix thực tế:** không chỉ đọc `application.yml`; kiểm tra biến môi trường, property override và factory bean được sử dụng.
3. **Liệt kê producer factories:** có bao nhiêu factory trong process, chúng có cùng Kafka cluster và prefix không?
4. **Kiểm tra overlap:** có pod mới khởi động, rolling update, autoscaling, restart hay consumer rebalance trùng thời điểm không?
5. **Tìm transactional ID trùng:** so sánh đầy đủ ID nếu instrumentation/log broker cho phép, không chỉ prefix.
6. **Đối chiếu với lỗi khác:** transaction timeout, missing authorization, cache exhaustion, broker instability có thể trông giống sự cố transaction.
7. **Khắc phục cấu hình:** cấp instance identity duy nhất hoặc stable ownership có kiểm soát, rồi rollout theo quy trình.
8. **Kiểm tra dữ liệu:** xác minh record/offset được commit đúng theo isolation level và idempotency; không chỉ dựa vào việc log lỗi biến mất.
9. **Bổ sung cảnh báo:** nếu fencing lặp lại sau scale, tạo alert theo error category và hướng dẫn runbook.

Không nên phản ứng bằng cách tắt Kafka transactions ngay khi gặp fencing. Cơ chế transaction có thể đang ngăn ghi dữ liệu sai; trước hết cần xác định collision hay lỗi lifecycle.

## 20. Bài tập thực hành

**Bài 1 — Chứng minh va chạm prefix.** Trên Kafka test broker, tạo hai `DefaultKafkaProducerFactory` với cùng prefix. Điều khiển để hai producer cuối cùng nhận cùng transactional ID và quan sát producer cũ bị fence. Sau đó đổi prefix riêng và so sánh.

**Bài 2 — Cấu hình Spring Boot.** Tạo hai process local kết nối cùng Kafka cluster, cung cấp `APP_ENV=dev` và hai `INSTANCE_ID` khác nhau. Gửi message trong transaction từ mỗi process, xác minh cả hai hoàn tất.

**Bài 3 — Deployment 3 replicas.** Viết Kubernetes Deployment cấp `INSTANCE_ID` từ `metadata.uid`. Dùng `spring.kafka.producer.transaction-id-prefix` sinh prefix cho từng pod. Xác minh ba pod có prefix khác nhau.

**Bài 4 — Rolling update.** Cho Deployment rolling update với old/new Pods tồn tại đồng thời. Theo dõi error rate, consumer lag và transaction outcomes; xác minh không có fencing do prefix trùng.

**Bài 5 — Concurrent transactions.** Tăng `spring.kafka.listener.concurrency` và thêm producer transaction từ service. Quan sát producer cache, suffix strategy và lỗi cạn producer, điều chỉnh cấu hình phù hợp version.

**Bài 6 — Transaction commit/abort.** Trong một Kafka transaction, gửi hai records rồi commit; ở transaction khác gửi một record và cố tình throw exception. Dùng consumer `read_committed` xác minh chỉ đọc những records đã commit.

**Bài 7 — Restart và stable identity.** So sánh prefix theo Pod UID với prefix theo StatefulSet ordinal. Mô phỏng instance cũ chưa dừng và instance mới khởi động; giải thích khi nào fencing là điều mong muốn.

**Bài 8 — DB side effect.** Một listener đọc Kafka, update database rồi gửi Kafka output. Gây failure sau DB commit nhưng trước Kafka commit để quan sát nguy cơ side effect lặp; đề xuất idempotency hoặc outbox.

**Bài 9 — Monitoring.** Bổ sung structured log có `instanceId`, prefix, `consumerGroupId` và error category. Thiết kế dashboard cho producer fencing, transaction abort, consumer lag và tình trạng restart.

**Bài 10 — Multi-factory.** Trong cùng một pod tạo hai transactional producer factories cho hai workload; cấp prefix phân biệt theo factory. Thử đổi cả hai về cùng prefix để nhận diện rủi ro suffix collision.

## 21. Kết luận

Trong Spring Kafka, `transactionIdPrefix` không chỉ là tên tùy ý: nó là namespace để `DefaultKafkaProducerFactory` tạo các `transactional.id` mà broker sử dụng để quản lý giao dịch và **fence phiên producer cũ**.

Với **nhiều instance chạy đồng thời**, hãy cấu hình prefix có thành phần nhận diện instance duy nhất (ví dụ Pod UID của Kubernetes Deployment), kết hợp environment/application/workload để tránh va chạm. Với **stable worker identity**, chỉ tái sử dụng prefix có chủ đích khi đã hiểu yêu cầu fencing và ownership. Đồng thời, phải cấp đủ producer/suffix capacity cho concurrency, hiểu transaction timeout/expiration và đảm bảo listener/consumer được cấu hình đúng để có Kafka EOS trong phạm vi Kafka-to-Kafka.

Quan trọng nhất, **tránh trùng transactional ID không thay thế thiết kế idempotency, restart và data consistency**. Kafka transactions bảo vệ message và offset trong Kafka; side effect ở database/API cần ranh giới và cơ chế chống lặp riêng.

### Tài liệu tham khảo

- [Spring Kafka Reference — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring Kafka Reference — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [Kubernetes — Downward API Environment Variables](https://kubernetes.io/docs/tasks/inject-data-application/environment-variable-expose-pod-information/)
