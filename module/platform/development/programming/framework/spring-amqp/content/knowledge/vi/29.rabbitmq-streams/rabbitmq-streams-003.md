# spring-rabbit-stream và cấu hình Environment

> **Chương:** RabbitMQ Streams. Trong module **SPRING_AMQP**, chúng ta đã làm việc với `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding và xác nhận giao nhận. Bài này đi sâu vào tích hợp **RabbitMQ Streams** bằng `spring-rabbit-stream` và `com.rabbitmq.stream.Environment`: cấu hình connection, khai báo stream, producer, consumer, offset, bảo mật và vòng đời ứng dụng.

## 1. Vì sao cần RabbitMQ Streams?

Giả sử hệ thống lưu các sự kiện `OrderCreated`, `OrderPaid` và `OrderCancelled`. Dịch vụ kho cần xử lý sự kiện mới, dịch vụ phân tích cần đọc cùng dữ liệu, còn một tác vụ kiểm toán phải **đọc lại** sự kiện trong bảy ngày qua. Nếu chỉ sử dụng một queue công việc thông thường, message được ack rồi thường biến mất khỏi queue; việc replay và nhiều nhóm đọc độc lập sẽ khó hơn.

**RabbitMQ Stream** là một nhật ký **append-only**, message được ghi tuần tự và lưu đến khi **retention** xóa các segment cũ. Consumer lưu **offset** (vị trí đọc) và có thể đọc lại lịch sử còn lưu. Một stream phù hợp cho event log, replay, nhiều nhóm consumer và throughput cao, chứ không thay thế mọi công dụng của queue cổ điển.

```mermaid
flowchart LR
    P[Order Producer] --> S[(orders.history Stream)]
    S --> A[Inventory Consumer<br/>offset A]
    S --> B[Analytics Consumer<br/>offset B]
    S --> C[Audit Reader<br/>replay từ offset cũ]
```

| Đặc tính | Queue classic/quorum truyền thống | RabbitMQ Stream |
| --- | --- | --- |
| Mô hình dữ liệu | Hàng đợi công việc | Log append-only, có thứ tự trong từng stream |
| Sau xử lý thành công | Ack thường loại message khỏi queue | Message vẫn nằm trong stream cho đến khi retention xóa |
| Nhiều nhóm đọc độc lập | Thường cấp nhiều queue/binding | Mỗi nhóm quản lý vị trí đọc riêng |
| Replay | Không phải khả năng mặc định của queue | Đọc lại từ offset/timestamp/first còn lưu |
| Theo dõi tiến độ | Ack/nack/reject | Offset tracking |
| DLX, TTL, ưu tiên message | Có tùy queue type | **Không hỗ trợ DLX/TTL/priority như queue thường** |
| Cổng protocol | AMQP 0-9-1 thường 5672 | Stream protocol thường **5552**, TLS thường **5551** |

**Lưu ý:** stream cũng có thể được khai báo như queue kiểu `stream` qua AMQP 0-9-1 và bind tới exchange. Nhưng các ví dụ `spring-rabbit-stream` trong bài dùng **native Stream Java Client**, có connection/protocol riêng và API offset thay vì ngữ nghĩa ack/reject của consumer queue thông thường.

## 2. Sơ đồ thành phần và dependency

| Thành phần | Vai trò trong tích hợp |
| --- | --- |
| Plugin broker `rabbitmq_stream` | Bật stream protocol và lưu stream |
| `com.rabbitmq.stream.Environment` | Điểm vào native client: kết nối/metadata/TLS; tạo producer, consumer và stream creator |
| `RabbitStreamTemplate` | API Spring gửi message vào **một stream**; trả kết quả bất đồng bộ |
| `StreamListenerContainer` | Quản lý consumer stream và lifecycle |
| `StreamRabbitListenerContainerFactory` | Tạo container cho `@RabbitListener` sử dụng stream |
| `StreamAdmin` | Provision stream bằng native `StreamCreator`, phù hợp ứng dụng chỉ dùng stream |
| `RabbitTemplate` và `RabbitAdmin` | Công cụ AMQP 0-9-1 truyền thống, hoạt động với connection khác |

Thư viện `spring-rabbit-stream` được giới thiệu từ **Spring AMQP 2.4**. Với Maven có dependency management/BOM tương ứng:

```xml
<dependency>
    <groupId>org.springframework.amqp</groupId>
    <artifactId>spring-rabbit-stream</artifactId>
</dependency>
```

Với Gradle:

```groovy
implementation 'org.springframework.amqp:spring-rabbit-stream'
```

Chọn phiên bản `spring-rabbit-stream` **cùng dòng phiên bản** với các thành phần Spring AMQP còn lại. Khi dùng Spring Boot, ưu tiên version được BOM quản lý. Nếu ứng dụng vừa dùng queue classic/quorum vừa dùng Streams, cũng cần `spring-rabbit` và phần cấu hình AMQP thông thường. Spring Boot 3.x thường có `spring-boot-starter-amqp`; tên starter RabbitMQ trong Spring Boot 4.x có thay đổi, cần tra đúng phiên bản dự án.

### Bật plugin trên broker thử nghiệm

```bash
rabbitmq-plugins enable rabbitmq_stream rabbitmq_stream_management
```

Plugin `rabbitmq_stream_management` phục vụ tính năng quản trị/quan sát; `rabbitmq_stream` mới là plugin bắt buộc cho stream protocol. Đảm bảo **5552/TCP** truy cập được từ ứng dụng; có thể mở thêm 5672 cho `RabbitTemplate` và 15672 cho Management UI khi thực hành. Kết nối AMQP thành công trên 5672 **không** chứng minh stream protocol trên 5552 sẵn sàng.

```bash
# Chỉ dùng để thực hành trong môi trường cô lập.
docker run --rm --name rabbit-stream-lab \
  -p 5552:5552 -p 5672:5672 -p 15672:15672 \
  rabbitmq:4-management

# Terminal thứ hai:
docker exec rabbit-stream-lab rabbitmq-plugins enable \
  rabbitmq_stream rabbitmq_stream_management
```

Khi dùng Docker bridge, ứng dụng bên ngoài container có thể cần cấu hình advertised hostname/port của Stream listener do client sẽ nhận **metadata về node giữ leader/replica** rồi mở connection tới node thích hợp. Port mapping một mình chưa chắc đủ cho tất cả topology. Tài khoản `guest/guest` mặc định chỉ nên dùng trong lab cục bộ.

## 3. Hiểu đúng `Environment`

`Environment` ở đây là **`com.rabbitmq.stream.Environment`**, khác hoàn toàn `org.springframework.core.env.Environment` của Spring Framework (đối tượng đọc configuration properties). Stream Environment quản lý **locator/metadata connections, producer/consumer connections, heartbeat, Netty resource, reconnect và cấu hình TLS**.

```mermaid
flowchart TB
    E["Stream Environment Bean<br/>lifetime ứng dụng"]
    E --> M[Metadata / Locator]
    E --> P[Producer]
    E --> C[Consumer]
    M --> R[RabbitMQ cluster metadata]
    P --> R
    C --> R
    E --> X[close khi Spring shutdown]
```

Theo hướng dẫn RabbitMQ, một ứng dụng thường tạo **một Environment dùng lâu dài** cho cùng bộ thông tin kết nối và đóng bằng `close()` khi kết thúc. Không tạo mới environment trên mỗi HTTP request hoặc mỗi message: điều đó phát sinh connection, thread, buffer và overhead không cần thiết.

### 3.1. Khai báo bean thủ công

Để tự quyết định toàn bộ cấu hình, ví dụ định nghĩa nhóm property riêng `demo.rabbit.stream.*`. Đây là property do ứng dụng **tự đặt tên**, không phải property Spring Boot tự nhận:

```yaml
demo:
  rabbit:
    stream:
      host: ${RABBIT_STREAM_HOST:localhost}
      port: ${RABBIT_STREAM_PORT:5552}
      username: ${RABBIT_STREAM_USER:guest}
      password: ${RABBIT_STREAM_PASSWORD:guest}
      virtual-host: ${RABBIT_STREAM_VHOST:/}
```

```java
import com.rabbitmq.stream.Environment;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StreamEnvironmentConfig {
    @Bean(destroyMethod = "close")
    Environment streamEnvironment(
            @Value("${demo.rabbit.stream.host}") String host,
            @Value("${demo.rabbit.stream.port}") int port,
            @Value("${demo.rabbit.stream.username}") String username,
            @Value("${demo.rabbit.stream.password}") String password,
            @Value("${demo.rabbit.stream.virtual-host}") String virtualHost) {
        return Environment.builder()
            .host(host)
            .port(port)
            .username(username)
            .password(password)
            .virtualHost(virtualHost)
            .build();
    }
}
```

`@Bean(destroyMethod = "close")` buộc Spring đóng `Environment` lúc ApplicationContext shutdown. Nếu có nhiều cluster/vhost với nhiều Environment, dùng tên bean và `@Qualifier` để phân biệt. Không để secret thật trong mã nguồn hoặc log.

**Tại sao không dùng `CachingConnectionFactory`?** `org.springframework.amqp.rabbit.connection.CachingConnectionFactory` dành cho AMQP 0-9-1. Native Stream Client có mô hình connection/metadata riêng; Spring stream template và listener phải nhận `com.rabbitmq.stream.Environment` đúng loại.

### 3.2. Tận dụng Spring Boot auto-configuration

Nếu Spring Boot phiên bản đang dùng có auto-configuration Stream và `spring-rabbit-stream` nằm trên classpath, có thể dùng các property chuẩn sau để Boot tạo Environment và template:

```yaml
spring:
  rabbitmq:
    stream:
      host: ${RABBIT_STREAM_HOST:localhost}
      port: ${RABBIT_STREAM_PORT:5552}
      username: ${RABBIT_STREAM_USER:guest}
      password: ${RABBIT_STREAM_PASSWORD:guest}
      virtual-host: ${RABBIT_STREAM_VHOST:/}
      name: orders.history
```

`spring.rabbitmq.stream.name` chỉ định stream mặc định của `RabbitStreamTemplate` do Boot tự tạo. Một số phiên bản hỗ trợ `spring.rabbitmq.stream.ssl.enabled` và SSL bundle. Nếu cần cấu hình sâu hơn (nhiều URI, resolver, các giới hạn connection) có thể tạo custom Environment bean hoặc sử dụng builder customizer do phiên bản Boot cung cấp.

**Hai đoạn cấu hình 3.1 và 3.2 là hai lựa chọn thay thế.** Khi đã có Environment và RabbitStreamTemplate tự khai báo, không đồng thời sao chép thêm một cấu hình auto-config không rõ thứ tự ưu tiên. Đối với ví dụ code từ mục 5 trở đi, ta dùng **cách bean thủ công**.

## 4. Các tùy chọn quan trọng của `Environment.builder()`

| Tùy chọn | Công dụng | Lưu ý |
| --- | --- | --- |
| `host`, `port` | Entry node cho client | Mặc định localhost:5552 |
| `username`, `password`, `virtualHost` | Xác thực và scope | Quyền phải phù hợp với vhost |
| `uri(...)` | URI protocol/credential/host/vhost | `rabbitmq-stream://...` hoặc TLS |
| `uris(...)` | Nhiều entry node cùng cluster | Hỗ trợ failover; không phải nhiều cluster độc lập |
| `addressResolver(...)` | Ánh xạ địa chỉ từ cluster metadata | Quan trọng trong Kubernetes, NAT, proxy/LB |
| `rpcTimeout` | Chờ RPC metadata/management | Đừng để quá ngắn khi broker bận |
| `requestedHeartbeat` | Phát hiện đường truyền hỏng | Tùy mạng/GC, mặc định khoảng 60 giây |
| `recoveryBackOffDelayPolicy` | Khoảng chờ phục hồi connection | Nên có backoff/jitter khi nhiều replica |
| `topologyUpdateBackOffDelayPolicy` | Chờ update topology khi leader/replica thay đổi | Không phải retry message nghiệp vụ |
| `locatorConnectionCount` | Connection cho metadata | Cân đối số URI và load balancer |
| `maxProducersByConnection`, `maxConsumersByConnection` | Giới hạn số producer/consumer trên một connection | Không phải trần tổng producer/consumer của cả cluster |
| `tls()`, `netty()` | TLS, certificate, Netty resource | Tự cung cấp executor/event loop thì tự quản lý lifecycle |

### Nhiều entry node trong cluster

```java
import com.rabbitmq.stream.Environment;
import java.util.List;

// URI chỉ minh họa cấu trúc; không lưu secret thật trong source.
Environment environment = Environment.builder()
    .uris(List.of(
        "rabbitmq-stream://service:secret@rabbit-1.internal:5552/%2f",
        "rabbitmq-stream://service:secret@rabbit-2.internal:5552/%2f",
        "rabbitmq-stream://service:secret@rabbit-3.internal:5552/%2f"))
    .build();
```

Virtual host `/` được mã hóa thành `%2f` trong URI. Client chọn entry node, truy vấn metadata và có thể chuyển connection tới leader/replica. Nếu broker quảng bá tên host mà client không phân giải được, chỉ thêm nhiều URIs sẽ không khắc phục; cần cấu hình `stream.advertised_host`/`stream.advertised_port` thích hợp và mạng.

### Ánh xạ địa chỉ khi đi qua load balancer

```java
import com.rabbitmq.stream.Address;
import com.rabbitmq.stream.Environment;

Address gateway = new Address("rabbit-stream-gateway.internal", 5552);
Environment environment = Environment.builder()
    .host(gateway.host())
    .port(gateway.port())
    .addressResolver(originalAddress -> gateway)
    .build();
```

`addressResolver` chỉ thích hợp nếu gateway/proxy thực sự hỗ trợ đường đi cần thiết tới stream leader/replica. Ưu tiên giải quyết địa chỉ quảng bá và DNS của broker đúng chuẩn; ánh xạ tất cả node về một gateway bất kỳ có thể làm producer/consumer kết nối nhầm node.

### TLS và security

URI TLS dùng scheme `rabbitmq-stream+tls://`, cổng mặc định 5551. Khi tự khai báo Environment, có thể cung cấp Netty `SslContext` qua `builder.tls().sslContext(...)`; tin cậy CA hợp lệ và xác minh hostname trùng với địa chỉ broker trả trong metadata. `trustEverything()` chỉ dành cho tình huống phát triển cô lập, không dùng production.

Khi dùng Spring Boot auto-config, tham khảo `spring.rabbitmq.stream.ssl.enabled` hoặc cấu hình SSL bundle theo phiên bản. Bật TLS cho `spring.rabbitmq` của kết nối AMQP 0-9-1 **không tự động** bật TLS cho một Stream Environment tự tạo.

## 5. Provisioning stream với `StreamAdmin`

Trước khi publish hoặc consume, stream phải tồn tại. Với native Stream API, ứng dụng chỉ dùng Stream nên khai báo bằng `StreamAdmin`, có thể cấu hình retention khi tạo stream:

```java
import com.rabbitmq.stream.Environment;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.rabbit.stream.support.StreamAdmin;

@Configuration(proxyBeanMethods = false)
class StreamProvisioningConfig {
    @Bean
    StreamAdmin ordersStreamAdmin(Environment environment) {
        return new StreamAdmin(environment, creator -> {
            creator.stream("orders.history")
                .maxAge(Duration.ofDays(7))
                .create();
        });
    }
}
```

`StreamAdmin` dùng native `StreamCreator` thay vì dựa vào AMQP 0-9-1 connection. Đây là điểm đáng chú ý: trong một ứng dụng **chỉ có stream components**, việc khai báo các bean `Queue` bằng `RabbitAdmin` có thể **không được kích hoạt** vì chưa có AMQP connection mở. Vì vậy dùng `StreamAdmin` hoặc provision stream qua hạ tầng/CLI sẽ rõ ràng hơn.

Nếu ứng dụng cũng đang dùng AMQP 0-9-1, có thể khai báo stream queue theo cách cũ:

```java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;

@Bean
Queue ordersHistoryQueue() {
    return QueueBuilder.durable("orders.history")
        .stream() // x-queue-type=stream
        .build();
}
```

Hai phương án trên là **lựa chọn thay thế** khi tạo cùng một stream, không cần thực hiện đồng thời. Nếu dùng `RabbitAdmin`, cần chắc chắn admin được khởi tạo và có AMQP connection kích hoạt việc declaration; nếu dùng `StreamAdmin`, cần broker hỗ trợ Stream plugin/cổng 5552. Trong môi trường production, có thể để hạ tầng sở hữu provisioning và ứng dụng chỉ consume/publish.

**Retention không phải ack:** `maxAge(Duration.ofDays(7))` nghĩa là broker giữ stream theo chính sách dọn dữ liệu trên **segment**, không phải xóa từng message khi consumer xử lý xong. Một consumer bị ngừng hơn bảy ngày có thể **không** đọc lại được toàn bộ lịch sử vì dữ liệu cũ đã bị xóa. Khi cần bảo đảm replay đầy đủ, theo dõi độ trễ consumer so với chính sách retention; có thể kết hợp thêm `maxLengthBytes`.

### Exchange, binding và native stream publisher

Một stream vẫn là queue type `stream` trong RabbitMQ và có thể bind với exchange, giống queue thường. Ví dụ producer **AMQP 0-9-1** có thể gửi qua `RabbitTemplate.convertAndSend("orders.events", "created", payload)` nếu exchange có binding tới `orders.history`. Nhưng **`RabbitStreamTemplate` gửi trực tiếp theo tên stream trong constructor**, không yêu cầu chỉ định exchange/routing key ở mỗi lần `convertAndSend`.

Điều này có ý nghĩa thực tế: với một event bus có nhiều routing key, bạn có thể sử dụng RabbitTemplate và exchange/binding, hoặc thiết kế native stream producer riêng cho từng stream/super stream. Đừng nhầm hai API khi port từ queue sang stream.

## 6. Producer: `RabbitStreamTemplate`

Tạo template dùng chính `Environment` được Spring quản lý và stream đã được provision:

```java
import com.rabbitmq.stream.Environment;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.rabbit.stream.producer.RabbitStreamTemplate;

@Configuration(proxyBeanMethods = false)
class StreamPublisherConfiguration {
    @Bean("ordersStreamTemplate")
    RabbitStreamTemplate ordersStreamTemplate(Environment environment) {
        return new RabbitStreamTemplate(environment, "orders.history");
    }
}
```

`RabbitStreamTemplate` cung cấp các phương thức `send(...)` và `convertAndSend(...)` trả về `CompletableFuture<Boolean>`. Không mặc định rằng gọi method là message đã được broker chấp nhận; phải quan sát kết quả future và xử lý lỗi:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.rabbit.stream.producer.RabbitStreamTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderStreamPublisher {
    private final RabbitStreamTemplate template;

    OrderStreamPublisher(
            @Qualifier("ordersStreamTemplate")
            RabbitStreamTemplate template) {
        this.template = template;
    }

    CompletableFuture<Void> publishOrderEvent(String json) {
        return template.convertAndSend(json)
            .orTimeout(10, TimeUnit.SECONDS)
            .thenApply(confirmed -> {
                if (!Boolean.TRUE.equals(confirmed)) {
                    throw new IllegalStateException(
                        "Stream publish not confirmed");
                }
                return null;
            });
    }
}
```

Đoạn `orTimeout(...)` chỉ đặt thời hạn **đợi kết quả ở ứng dụng**, không chứng minh broker không nhận message nếu hết hạn. Trạng thái publisher không rõ sau timeout/mất kết nối phải được xử lý bằng **event ID ổn định, retry có backoff, outbox nếu cần** và idempotent consumer. `CompletableFuture<Boolean>` hoàn thành thành công cho biết kết quả publish theo Stream API, **không** có nghĩa một `@RabbitListener` đã xử lý xong.

`RabbitStreamTemplate` dùng hai tầng chuyển đổi:

1. `MessageConverter` chuyển Java object thành Spring AMQP `Message` khi gọi `convertAndSend`.
2. `StreamMessageConverter` chuyển Spring AMQP `Message` thành native `com.rabbitmq.stream.Message` để gửi qua Stream protocol.

Ứng dụng có thể tùy biến converter qua `setMessageConverter(...)`, `setStreamConverter(...)`, hoặc gửi native message bằng `template.messageBuilder()`. Với dữ liệu nghiệp vụ, hãy thống nhất schema, content type và encoding với consumer. Đừng mặc định một object Java tùy ý sẽ tự tương thích JSON nếu chưa cấu hình converter.

### Native message và producer customizer

Ví dụ gửi payload UTF-8 bằng builder native:

```java
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import org.springframework.rabbit.stream.producer.RabbitStreamTemplate;

CompletableFuture<Boolean> sent = template.send(
    template.messageBuilder()
        .addData("OrderCreated:42".getBytes(StandardCharsets.UTF_8))
        .build());
```

`RabbitStreamTemplate.setProducerCustomizer(...)` cho phép chỉnh `ProducerBuilder` trước khi xây producer, ví dụ bật tên producer phục vụ dedup và điều chỉnh các thiết lập native. **Không đặt cùng một producer name cho các producer độc lập với chuỗi publishing ID xung đột**: khả năng broker-side dedup của Stream yêu cầu quản lý producer name và publishing ID đúng quy tắc. Tên consumer và tên producer có mục đích khác nhau.

Nếu cần gửi đồng thời hàng nghìn message, giới hạn số future đang chờ; dồn vô hạn vào bộ nhớ rồi chỉ kiểm tra khi ứng dụng dừng sẽ làm mất kiểm soát lỗi và áp lực tài nguyên. Khi tạo `RabbitStreamTemplate` bean riêng, Spring quản lý lifecycle của template; template cũng có `close()`. Không chủ động đóng Environment trước khi các template/container sử dụng nó dừng.

## 7. Consumer với `StreamRabbitListenerContainerFactory` và `@RabbitListener`

### 7.1. Listener nhận Spring AMQP Message

Tạo **container factory chuyên dụng cho stream**. Tên bean rõ ràng để không vô tình lấy `SimpleRabbitListenerContainerFactory` của queue truyền thống:

```java
import com.rabbitmq.stream.Environment;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.rabbit.stream.config.StreamRabbitListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
class StreamConsumerConfiguration {
    @Bean("ordersStreamListenerFactory")
    StreamRabbitListenerContainerFactory ordersStreamListenerFactory(
            Environment environment) {
        StreamRabbitListenerContainerFactory factory =
            new StreamRabbitListenerContainerFactory(environment);

        factory.setConsumerCustomizer((listenerId, builder) ->
            builder.name("orders-inventory-reader"));
        return factory;
    }
}
```

```java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class OrderStreamListener {
    private final OrderProjectionService projectionService;

    OrderStreamListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @RabbitListener(
        id = "ordersInventoryStreamListener",
        queues = "orders.history",
        containerFactory = "ordersStreamListenerFactory")
    public void onEvent(String eventText) {
        projectionService.apply(eventText);
    }
}
```

`OrderProjectionService` là service nghiệp vụ do ứng dụng tự hiện thực, chẳng hạn parse event JSON và cập nhật bản đọc của tồn kho. Khi dùng Spring Boot, cơ chế xử lý `@RabbitListener` được auto-config tương ứng; trong Spring thuần cần bật annotation processing với `@EnableRabbit`.

**Khác biệt lớn so với queue:** với stream container, `@RabbitListener` chỉ hỗ trợ một số thuộc tính thích hợp như `id`, `queues`, `autoStartup` và `containerFactory`. Một listener chỉ nhận **một stream name**; nhiều thuộc tính khác (bao gồm `concurrency` trên annotation) bị bỏ qua. Không tăng `@RabbitListener(concurrency="10")` rồi kỳ vọng có 10 consumer stream.

Tùy cách định nghĩa offset/naming, consumer có thể đọc message đã tồn tại trước khi listener khởi động. Khi chỉ định `name("orders-inventory-reader")`, native client dùng tên này cho server-side offset tracking mặc định. Không sử dụng cùng tên một cách bừa bãi trên hai replica: **tên giống nhau không tự biến hai instance thành competing consumers/consumer group kiểu queue**; server-side offsets có thể bị ghi đè xen kẽ. Nếu cần scale-out đúng nghĩa, xem **super stream với partitions và single active consumer**.

### 7.2. Native listener để tự điều khiển offset

`StreamRabbitListenerContainerFactory` có `setNativeListener(true)`. Khi đó method listener nhận native `com.rabbitmq.stream.Message` và `MessageHandler.Context`, cho phép ghi offset sau khi xử lý:

```java
import com.rabbitmq.stream.Environment;
import com.rabbitmq.stream.OffsetSpecification;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.rabbit.stream.config.StreamRabbitListenerContainerFactory;

@Configuration(proxyBeanMethods = false)
class NativeStreamListenerConfiguration {
    @Bean("nativeOrdersStreamFactory")
    StreamRabbitListenerContainerFactory nativeOrdersStreamFactory(
            Environment environment) {
        StreamRabbitListenerContainerFactory factory =
            new StreamRabbitListenerContainerFactory(environment);
        factory.setNativeListener(true);
        factory.setConsumerCustomizer((listenerId, builder) ->
            builder.name("orders-audit-reader")
                .offset(OffsetSpecification.first())
                .manualTrackingStrategy());
        return factory;
    }
}
```

```java
import com.rabbitmq.stream.Message;
import com.rabbitmq.stream.MessageHandler.Context;
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class NativeOrderAuditListener {
    private final AuditService auditService;

    NativeOrderAuditListener(AuditService auditService) {
        this.auditService = auditService;
    }

    @RabbitListener(
        id = "nativeOrdersAudit",
        queues = "orders.history",
        containerFactory = "nativeOrdersStreamFactory")
    public void onStreamEvent(Message message, Context context) {
        String eventText = new String(
            message.getBodyAsBinary(), StandardCharsets.UTF_8);

        auditService.record(eventText); // Hoàn thành commit nghiệp vụ trước.
        context.storeOffset();          // Sau đó lưu offset đã xử lý.
    }
}
```

`AuditService` là business service giả định, có thể ghi dữ liệu qua database transaction. Cách gọi `context.storeOffset()` sau từng message được dùng **chỉ để làm rõ thứ tự trong lab**; với lưu lượng lớn, cần cân nhắc lưu offset theo batch/khoảng thời gian, vì offset tracking cũng tạo dữ liệu lưu trên stream. Nếu offset cũ hơn kết quả xử lý cuối khi ứng dụng crash, consumer có thể đọc lại message; consumer nghiệp vụ nên **idempotent**.

**Hai listener 7.1 và 7.2 là hai lựa chọn để học hai chế độ.** Khi thử nghiệm, nên chạy lần lượt hoặc dùng tên stream/consumer đích khác để không nhầm việc cả hai cùng nhận toàn bộ event với tình huống competing consumers của queue.

## 8. Offset tracking: phần quyết định tính đúng đắn của consumer

Một stream không loại message ngay khi consumer xử lý thành công. Thay vào đó, consumer lựa chọn **vị trí bắt đầu** và lưu **vị trí đã xử lý** theo một trong các chiến lược do Stream Java Client cung cấp.

| `OffsetSpecification` | Điểm đọc khởi đầu | Tình huống sử dụng |
| --- | --- | --- |
| `first()` | Message đầu tiên còn trong retention | Replay toàn bộ lịch sử đang lưu |
| `next()` | Message mới đến sau khi subscription bắt đầu | Theo dõi sự kiện từ thời điểm consumer online |
| `last()` | Từ chunk cuối của stream, có thể gồm nhiều message cũ | Muốn đọc gần cuối, **khác với next()** |
| `offset(n)` | Từ offset cụ thể | Tiếp tục/replay từ checkpoint xác định |
| `timestamp(instantMillis)` | Tìm vị trí theo thời điểm | Replay theo mốc thời gian, tùy dữ liệu retention |

**Lưu ý:** offset không nhất thiết liên tiếp từng số nguyên. Stream lưu cả metadata như checkpoint; không dùng `offset % 1000 == 0` để suy ra “đã xử lý đúng 1.000 message”. Dùng counter message thực nhận nếu cần xử lý theo batch.

### 8.1. Consumer không đặt tên

Khi không chỉ định `name` và không có offset explicit, consumer mặc định bắt đầu từ `next()`, có nghĩa chỉ đọc dữ liệu mới sau khi subscribe. Đó là nguyên nhân rất thường gặp của câu hỏi “publisher đã gửi trước khi listener khởi động, sao listener không thấy message?”.

Để đọc từ đầu trong buổi lab:

```java
factory.setConsumerCustomizer((listenerId, builder) ->
    builder.offset(OffsetSpecification.first()));
```

### 8.2. Consumer có tên, offset lưu trên broker

Khi đặt `builder.name("orders-inventory-reader")`, Stream Java Client dùng **server-side offset tracking tự động** theo cấu hình mặc định. Client lưu offset theo số message được xử lý và chu kỳ flush; tài liệu client hiện hành nêu các giá trị mặc định khoảng **10.000 message** hoặc **5 giây**. Điều này giảm overhead so với lưu một checkpoint cho từng message.

Đặc biệt, khi consumer **đã có stored offset trên broker**, stored offset có thể **ưu tiên** hơn tham số `.offset(OffsetSpecification.first())` ở lần subscribe đầu tiên. Vì vậy sửa `first()` nhưng vẫn thấy đọc từ vị trí cũ là hành vi có thể đúng. Muốn replay một lần độc lập, dùng **consumer name khác** hoặc cơ chế quản lý/reset offset có chủ đích và tránh ghi đè checkpoint của consumer sản xuất.

### 8.3. Manual offset tracking và tính nhất quán

`manualTrackingStrategy()` cho phép gọi `Context.storeOffset()` sau khi xử lý thành công. Nhưng **ghi offset lên broker không tạo một transaction nguyên tử với database**:

```mermaid
sequenceDiagram
    participant S as Stream
    participant C as Consumer
    participant DB as Database
    S->>C: Event E42
    C->>DB: Commit business update E42
    C--xS: Crash trước khi store offset
    Note over S,C: Consumer restart từ stored offset cũ
    S->>C: Giao lại E42
    C->>DB: Dedup theo eventId
    C->>S: Store offset mới
```

Nguyên tắc: **commit side effect trước, rồi lưu offset**; sử dụng inbox/dedup hoặc thao tác idempotent ở downstream. Nếu lưu offset trước khi xử lý thành công, restart có thể bỏ qua message chưa thực sự được áp dụng.

Nếu xử lý song song nhiều message, không được lưu offset của message **sau** khi message **trước** còn thất bại, vì điều đó có thể khiến lần restart bỏ qua khoảng trống nghiệp vụ. Cần theo dõi **contiguous committed offset** hoặc xử lý tuần tự theo stream/partition khi yêu cầu thứ tự nghiêm ngặt.

### 8.4. Retry và poison message

Không sao chép cơ chế `basicReject(requeue=true)` hoặc DLX/DLQ của classic/quorum queue rồi kỳ vọng stream xử lý giống hệt. Với Streams, producer/consumer có thể tự điều khiển retry **trước khi checkpoint**, có thể dùng `StreamRetryOperationsInterceptorFactoryBean` với stateless retry (Spring AMQP hỗ trợ từ 2.4.5), hoặc chuyển message lỗi sang một queue/sink điều tra riêng có chủ đích.

Những lỗi không thể phục hồi (payload sai schema, ID không hợp lệ) cần chính sách **quarantine/parking** rõ ràng trước khi tiến offset qua chúng. Nếu gặp lỗi tạm thời, retry có backoff và giới hạn tài nguyên; nếu buộc phải tiếp tục dòng sự kiện, hãy ghi sự kiện thất bại một cách bền vững, có thể replay. **Stream listener container không hỗ trợ stateful retry giống queue container** theo hướng dẫn Spring AMQP.

## 9. Cấu hình Environment khi chạy cluster và nhiều replica

### 9.1. Metadata địa chỉ broker và điểm kết nối

Stream client có thể cần hai bước kết nối: tới **locator/entry node** để lấy metadata; sau đó tới **leader hoặc replica** cho producer/consumer. Vì vậy một host trong `uris(...)` reachable chưa đủ: địa chỉ node do metadata trả về cũng phải reachable.

| Triệu chứng | Nguyên nhân phổ biến | Cách kiểm tra |
| --- | --- | --- |
| TCP 5552 bị từ chối | Plugin chưa bật, cổng chưa expose, firewall | Kiểm tra listener stream trên broker và routing mạng |
| Environment tạo được nhưng producer mở không được | Advertised hostname không phân giải hoặc port metadata sai | Kiểm tra hostname/port node được broker quảng bá, DNS, NAT |
| Client trong Docker kết nối sai `localhost` | `localhost` là container hiện tại hoặc client áp dụng local development fallback | Dùng đúng hostname mạng và resolver/advertised host |
| TLS handshake thất bại | CA, hostname, SNI hoặc certificate không phù hợp với metadata | Xác minh trust chain và advertised addresses |
| `ACCESS_REFUSED` hoặc lỗi vhost | Sai username/password/quyền | Kiểm tra credential, vhost, user permissions |
| Client thấy stream không tồn tại | Chưa provision, sai vhost, tên stream nhầm | Xác nhận StreamAdmin/CLI đã tạo đúng stream |
| Consumer không thấy dữ liệu cũ | Offset bắt đầu `next()` hoặc stored offset đã gần cuối | Kiểm tra name, offset specification và retention |
| Consumer nhận lại dữ liệu | Stored offset lag so với xử lý thành công | Thiết kế idempotency, tăng tần suất checkpoint cân đối |
| Replica khác ghi đè offset | Nhiều consumer dùng một `name` không có coordination | Dùng name khác, hoặc super stream single active consumer phù hợp |

### 9.2. Bảo vệ tài nguyên

`Environment` giữ connection và tài nguyên nền cho nhiều producer/consumer. Các tham số `maxProducersByConnection`, `maxConsumersByConnection`, `locatorConnectionCount` ảnh hưởng số connection thực; tăng số consumer quá cao có thể gây quá tải broker và client. Theo dõi:

- **Connections** theo loại locator/producer/consumer, reconnect rate và thời gian phục hồi sau node failover.
- **Publishing confirm latency** và số future publish đang chờ; nếu timeout, phân loại trạng thái chưa rõ, tránh retry nóng.
- **Consumer lag** theo thời gian và khả năng replay còn nằm trong retention.
- **Disk/stream segments**: stream là log giữ dữ liệu theo thời gian, phải đặt retention phù hợp dung lượng và nhu cầu kiểm toán.
- **Memory, Netty buffers, threads, scheduler** ở JVM; bảo đảm `close()` khi shutdown.

Một stream có thể được đọc bởi nhiều consumer độc lập, nhưng không có nghĩa mọi consumer đều chia việc như competing consumers của queue. Nếu nhu cầu là scale xử lý trên nhiều instance, cân nhắc **super streams (nhiều partition)** với cơ chế **single active consumer** và nhóm tiêu thụ được định nghĩa rõ. Khi dùng `@RabbitListener` cơ bản cho một stream, thuộc tính `concurrency` không tự biến stream thành nhiều partition.

### 9.3. Phân biệt lỗi publish và lỗi listener

`RabbitStreamTemplate.convertAndSend` trả future để biết kết quả publish; tương tự publisher confirms trên AMQP, lỗi mất kết nối sau gửi có thể khiến trạng thái **không xác định**. Không gắn side effect DB với một future chưa hoàn thành rồi khẳng định đã publish thành công. Với giao dịch quan trọng, dùng transactional outbox hoặc một nguồn sự kiện bền vững, cùng event ID ổn định và tiêu thụ idempotent.

Ở phía consumer, **offset tracking không thay thế business transaction**. Nếu ghi vào database xong mà offset chưa kịp lưu, message có thể replay; nếu offset đã tiến mà nghiệp vụ thất bại, có thể bỏ sót dữ liệu. Giải quyết bằng transaction nghiệp vụ, retry rõ ràng, dedup và khả năng quan sát.

## 10. Quan sát stream bằng Spring AMQP và RabbitMQ

Spring AMQP hỗ trợ Micrometer Observation cho `RabbitStreamTemplate` và stream listener container từ **Spring AMQP 3.0.5**. Có thể bật theo bean/factory khi có registry tương ứng:

```java
@Bean
StreamRabbitListenerContainerFactory observedStreamListenerFactory(
        Environment environment) {
    StreamRabbitListenerContainerFactory factory =
        new StreamRabbitListenerContainerFactory(environment);
    factory.setObservationEnabled(true);
    return factory;
}
```

Tương tự `RabbitStreamTemplate` có `setObservationEnabled(true)`; cấu hình observation cụ thể còn phụ thuộc phiên bản Spring AMQP và Micrometer. Với `observationEnabled=true`, timer riêng có thể được thay bởi metrics sinh từ observation; kiểm tra dashboard trước khi giả định có cả hai số liệu.

| Nguồn chỉ số | Cần quan sát | Ý nghĩa |
| --- | --- | --- |
| RabbitMQ stream | Stream size, segment/retention, publish/deliver rate | Broker có giữ và phát dữ liệu đúng không? |
| Producer | Future true/false/exception, publish latency, in-flight | Broker nhận được publish hay client đang nghẽn? |
| Consumer | Offset đã đọc, stored offset, lag, lỗi xử lý | Có đang đọc kịp trước retention? |
| JVM/Netty | Heap/direct memory, thread, connection count | Environment và consumer có dùng quá nhiều tài nguyên? |
| Business DB | Tỷ lệ xử lý trùng, transaction error | Replay có tạo side effect lặp không? |

Tránh gắn `eventId` làm label metric vì cardinality quá cao; dùng trong trace/log có cấu trúc khi cần truy vết. Khi có nhiều replica, đặt tên Environment theo instance để việc điều tra connection dễ hơn, nhưng đừng nhầm **Environment ID** (chủ yếu để đặt tên connection) với **consumer name** dùng quản lý offset.

## 11. Bài thực hành end-to-end

**Mục tiêu:** tự thiết lập Environment, tạo stream, gửi/nhận event, kiểm tra offset/replay, sau đó mô phỏng lỗi kết nối và duplicate.

### Điều kiện ban đầu

1. Có RabbitMQ thử nghiệm đã bật `rabbitmq_stream`, địa chỉ 5552 và một virtual host có quyền thích hợp.
2. Ứng dụng Spring Boot chứa dependency `spring-rabbit-stream` cùng phiên bản tương thích với `spring-rabbit`, có Spring Rabbit listener infrastructure.
3. Dùng cấu hình bean thủ công trong mục 3.1 và code `StreamAdmin`, `RabbitStreamTemplate`, `StreamRabbitListenerContainerFactory` ở các mục 5–7; không sao chép đồng thời phần auto-config 3.2.
4. Có `OrderProjectionService` và `AuditService` minh họa xử lý nghiệp vụ; trong bài lab có thể thay chúng bằng log/collection, nhưng production cần lưu trữ và idempotency thật.

### Thử nghiệm A — Tạo stream và publish

- Khởi động ứng dụng, kiểm tra stream `orders.history` tồn tại trong Management UI với queue type **stream**.
- Gửi ba event khác nhau qua `OrderStreamPublisher.publishOrderEvent(...)` và quan sát `CompletableFuture` hoàn thành thành công.
- Kiểm tra message có nằm trong stream và listener đã nhận. Đừng đánh đồng publish future thành công với consumer xử lý hoàn tất.
- Dừng consumer, tiếp tục publish: message **vẫn được lưu trong stream** cho đến khi retention dọn dữ liệu cũ.

### Thử nghiệm B — Offset mặc định và replay

| Lần chạy | Cấu hình consumer | Kỳ vọng |
| --- | --- | --- |
| 1 | Consumer **không tên**, không đặt offset | Mặc định `next()`, nhận message mới sau subscribe |
| 2 | Consumer không tên với `OffsetSpecification.first()` | Đọc toàn bộ dữ liệu còn lưu trong retention |
| 3 | Consumer có tên `orders-audit-reader`, manual tracking và `first()` | Lần đầu đọc từ đầu và ghi offset khi nghiệp vụ hoàn tất |
| 4 | Khởi động lại consumer cùng tên từ bước 3 | Thường tiếp tục từ stored offset, có thể replay message sau checkpoint gần nhất |
| 5 | Đổi sang consumer name mới khi muốn chạy kiểm toán | Có thể replay riêng, không sửa checkpoint của nhóm xử lý cũ |

**Ghi chú:** khi đã có stored offset cho consumer name, nó có thể ghi đè `first()`; đừng tưởng `first()` luôn bắt đầu tại offset 0 trong mọi lần restart. Nếu retention đã xóa phần log cũ, không thể replay dữ liệu không còn tồn tại.

### Thử nghiệm C — Lỗi nghiệp vụ và lỗi mạng

| Tình huống | Cách thực hiện | Điều phải quan sát |
| --- | --- | --- |
| Consumer thất bại trước side effect | Cho service ném exception trước DB commit | Offset không được cập nhật như một lần hoàn tất thành công; cần retry/quarantine rõ |
| DB commit rồi consumer crash trước store offset | Mô phỏng đứt kết nối hoặc dừng process | Consumer có thể đọc lại event; dedup ngăn tác động trùng |
| Producer timeout sau khi gửi | Chặn đường nhận confirm hoặc dùng test double | Không khẳng định broker chưa nhận; retry cùng event ID nếu cần |
| Stream plugin/port 5552 không truy cập được | Tắt plugin hoặc chặn network trong môi trường lab | Lỗi connection cụ thể, không nhầm với 5672 của AMQP |
| Client ở ngoài Docker/Kubernetes | Cố tình dùng advertised host không truy cập được | Environment có thể tới entry node nhưng producer/consumer lỗi metadata routing |
| Consumer đứng yên quá retention | Giảm retention trong lab, dừng consumer đủ lâu | Dữ liệu đầu log bị dọn; replay thiếu lịch sử đã hết hạn |

Đối với bài kiểm tra duplicate, gắn `eventId` vào payload và ghi dấu `processed_events(consumer_name, event_id)` với unique key **trong cùng transaction** với side effect. Kết quả đúng có thể là **message đến hai lần nhưng side effect chỉ được áp dụng một lần**.

### Câu hỏi tự kiểm tra

1. `com.rabbitmq.stream.Environment` quản lý gì? Vì sao không dùng `org.springframework.core.env.Environment` hoặc `CachingConnectionFactory` thay thế?
2. Khi ứng dụng chỉ có Stream consumer và không mở AMQP 0-9-1 connection, khai báo `QueueBuilder.stream()` dựa trên `RabbitAdmin` có thể gặp vấn đề gì?
3. `RabbitStreamTemplate.convertAndSend(...)` nhận tham số exchange/routing key giống `RabbitTemplate.convertAndSend(...)` không?
4. Khi dùng `@RabbitListener` với Stream container, tại sao `concurrency="5"` không tạo năm stream consumer?
5. Consumer không đặt tên có nhận message cũ trước khi khởi động không? Dùng `first()` có ý nghĩa gì?
6. Vì sao có `name("audit")` rồi `first()` vẫn có thể đọc từ giữa stream sau restart?
7. Đặt `context.storeOffset()` trước khi commit database có thể gây lỗi gì?
8. Có thể dùng `basicReject(requeue=false)` để đẩy message lỗi trong stream vào DLX như quorum queue không?
9. Vì sao `localhost:5552` reachable chưa đủ để kết luận producer có thể kết nối tới leader của stream trong Kubernetes?
10. Khi nào nên dùng stream và khi nào nên dùng classic/quorum queue?

## 12. Checklist cấu hình production

| Hạng mục | Cần quyết định |
| --- | --- |
| Workload | Cần replay/event log hay chỉ cần work queue? |
| Dependency | `spring-rabbit-stream` và `spring-rabbit` cùng dòng phiên bản? |
| Plugin | `rabbitmq_stream` bật, port 5552/5551 mở đúng mạng? |
| Bean lifecycle | Dùng một Environment dài hạn và đóng khi shutdown? |
| Configuration owner | Chọn Boot auto-config hay custom Environment, tránh bean trùng/mơ hồ? |
| Secrets/TLS | Tách secret, xác minh CA, hostname, vhost/permission? |
| Cluster connectivity | Entry URIs, advertised host/port và addressResolver đúng? |
| Provisioning | `StreamAdmin`/hạ tầng đã tạo stream; retention đủ cho replay và lag? |
| Publishing | Kiểm tra future, giới hạn in-flight, có retry và idempotency khi kết quả không rõ? |
| Consuming | Chọn offset initial, consumer name, auto/manual tracking; nhận thức replay? |
| Business correctness | Side effect idempotent, không checkpoint quá sớm; lỗi được quarantine có kiểm soát? |
| Scaling | Có partition/super stream nếu cần scale-out; không nhầm consumer name với work sharing? |
| Observability | Publish latency, consumer lag, stored offset, stream size, broker/client reconnect, JVM resource? |

## 13. Tài liệu tham khảo chính thức

- [Spring AMQP — Using the RabbitMQ Stream Plugin](https://docs.spring.io/spring-amqp/reference/stream.html): `spring-rabbit-stream`, `RabbitStreamTemplate`, `StreamListenerContainer`, `StreamAdmin` và factory.
- [Spring AMQP — Stream Support bản 3.2](https://docs.spring.io/spring-amqp/reference/3.2/stream.html): đối chiếu API khi dùng Spring AMQP 3.x.
- [RabbitMQ Stream Java Client — Reference Guide](https://rabbitmq.github.io/rabbitmq-stream-java-client/stable/htmlsingle/): `Environment.builder()`, kết nối cluster, offset, producer/consumer, TLS, metadata.
- [RabbitMQ Stream Java Client — EnvironmentBuilder API](https://rabbitmq.github.io/rabbitmq-stream-java-client/stable/api/com/rabbitmq/stream/EnvironmentBuilder.html): các thuộc tính builder và address resolver.
- [RabbitMQ — Streams and Superstreams](https://www.rabbitmq.com/docs/streams): đặc tính stream, retention, queue type `stream` và các giới hạn so với queue.
- [RabbitMQ — Stream Client Connections](https://www.rabbitmq.com/docs/stream-connections): advertised address, kết nối trực tiếp và load balancer.
- [RabbitMQ — Stream Java Client, Hello World](https://www.rabbitmq.com/tutorials/tutorial-one-java-stream): bật plugin, tạo stream, publish và consume.
- [RabbitMQ — Stream Java Client, Offset Tracking](https://www.rabbitmq.com/tutorials/tutorial-two-java-stream): name, `first()`, manual tracking và replay.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): `spring.rabbitmq.stream.*`, template auto-configuration và SSL theo phiên bản Boot.

**Ghi nhớ:** `spring-rabbit-stream` tích hợp native RabbitMQ Stream Java Client vào Spring. `Environment` là **tài nguyên kết nối dài hạn** cho producer/consumer; `RabbitStreamTemplate` gửi theo tên stream; `StreamListenerContainer`/`@RabbitListener` đọc theo **offset**. Muốn hệ thống đáng tin cậy, phải cấu hình đúng plugin/port/metadata/TLS, quản lý offset sau nghiệp vụ, cân nhắc retention và xử lý **replay/duplicate** thay vì áp dụng máy móc ack/requeue/DLQ của classic hoặc quorum queue.
