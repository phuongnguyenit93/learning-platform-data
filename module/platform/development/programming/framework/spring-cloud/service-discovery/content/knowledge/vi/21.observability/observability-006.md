# Đọc log tự cấu hình, đăng ký và tái kết nối có ngữ cảnh

Service discovery có nhiều hoạt động xảy ra trước khi request nghiệp vụ đầu tiên được xử lý: ứng dụng đọc cấu hình, tạo danh tính instance, kết nối registry, đăng ký service, gửi heartbeat hoặc health check, tải danh sách instance và tái kết nối khi mạng gián đoạn. Khi một bước thất bại, một dòng log chỉ ghi `Connection refused` thường không đủ để xác định service nào bị ảnh hưởng, registry nào đang được dùng, ứng dụng đang ở lần thử thứ mấy hay cấu hình nào đã được nạp.

Log có ngữ cảnh giúp nối các hoạt động đó thành một vòng đời có thể điều tra. Mỗi sự kiện cần mang theo service name, instance ID, môi trường, provider, operation, trạng thái trước/sau, thời gian thực hiện và thông tin lỗi phù hợp. Bài này trình bày cách thiết kế log có cấu trúc cho tự cấu hình, đăng ký và reconnect trong Spring Cloud Service Discovery; đồng thời chỉ ra dữ liệu cần bảo vệ và cách tránh log nhiễu.

## 1. Vì sao log discovery cần ngữ cảnh?

Một microservice có thể chạy nhiều replica, nhiều môi trường và nhiều registry endpoint. Nếu log chỉ ghi:

```text
Registered successfully
Retrying connection
Configuration loaded
```

thì người vận hành chưa biết:

- Service nào đã đăng ký? Instance ID nào?
- Instance đang chạy ở môi trường, region hoặc zone nào?
- Đang kết nối Eureka, Consul hay ZooKeeper? Đích registry nào?
- Cấu hình được lấy từ file, environment variables hay Config Server/KV?
- Đăng ký lần đầu hay đăng ký lại sau session expiration?
- Lần retry thứ mấy, đã chờ bao lâu và lỗi có thể retry không?
- Reconnect đã khôi phục cache/registration hay chỉ mới mở lại socket?

Log hữu ích phải trả lời được những câu hỏi này mà không cần in toàn bộ configuration object hoặc payload nhạy cảm.

## 2. Một schema log thống nhất

Nên thống nhất một tập field cho mọi service trong hệ thống. Tên field có thể theo ECS hoặc quy ước nội bộ, nhưng phải nhất quán giữa các ứng dụng và log pipeline.

| Field | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `event.name` | Tên sự kiện ổn định để lọc/đếm | `service.registration.succeeded` |
| `service.name` | Service ID logic | `inventory-service` |
| `service.instance.id` | ID duy nhất của replica | `inventory-10-20-1-15-8081` |
| `service.version` | Phiên bản phần mềm | `2.4.1` |
| `deployment.environment` | Môi trường triển khai | `production` |
| `service.region` | Region của instance | `ap-southeast-1` |
| `service.zone` | Zone/failure domain | `ap-southeast-1a` |
| `discovery.provider` | Provider discovery | `eureka`, `consul`, `zookeeper`, `kubernetes` |
| `registry.endpoint` | Tên endpoint registry đã chuẩn hóa | `consul-agent.internal:8500` |
| `operation.id` | ID nối các bước của một lifecycle operation | `reg-7f21a9` |
| `registration.state` | Trạng thái đăng ký hiện tại | `REGISTERING`, `REGISTERED`, `FAILED` |
| `connection.state` | Trạng thái kết nối provider/client | `CONNECTED`, `SUSPENDED`, `LOST` |
| `retry.attempt` | Số lần thử hiện tại | `3` |
| `retry.max` | Số lần thử tối đa theo policy | `5` |
| `retry.delay.ms` | Thời gian chờ trước lần thử tiếp theo | `2000` |
| `duration.ms` | Thời gian thao tác | `84` |
| `error.type` | Loại exception hoặc mã lỗi | `ConnectTimeoutException` |
| `trace.id`, `span.id` | Liên kết với distributed trace nếu có | ID do tracing system cấp |

Không nhất thiết mọi dòng log phải có mọi field. Tuy nhiên, các field nhận diện service/instance/provider nên có mặt ở các sự kiện lifecycle quan trọng. `registry.endpoint` nên là tên DNS/alias hoặc địa chỉ đã chuẩn hóa; không đưa URL chứa username, password, token hay query parameter bí mật vào log.

Một sự kiện JSON thành công có thể trông như sau:

```json
{
  "@timestamp": "2026-11-24T14:30:12.418Z",
  "log.level": "INFO",
  "event.name": "service.registration.succeeded",
  "service.name": "inventory-service",
  "service.instance.id": "inventory-10-20-1-15-8081",
  "service.version": "2.4.1",
  "deployment.environment": "production",
  "discovery.provider": "consul",
  "registry.endpoint": "consul-agent.internal:8500",
  "registration.state": "REGISTERED",
  "duration.ms": 84,
  "operation.id": "reg-7f21a9"
}
```

Đây là schema minh họa. Có thể đổi tên field theo chuẩn log của tổ chức, nhưng không nên để mỗi service tự nghĩ một tên khác nhau cho cùng một khái niệm.

## 3. Chia log theo giai đoạn lifecycle

Một vòng đời discovery nên có những mốc sự kiện rõ ràng:

| Giai đoạn | Event gợi ý | Thông tin cần ghi |
| --- | --- | --- |
| Đọc cấu hình | `discovery.config.loaded` | Provider, service ID, môi trường, nguồn cấu hình, profile, phiên bản schema |
| Kiểm tra cấu hình | `discovery.config.validated` / `discovery.config.invalid` | Trường thiếu/sai, không ghi giá trị bí mật |
| Bắt đầu kết nối | `registry.connection.started` | Endpoint alias, timeout, provider |
| Kết nối thành công | `registry.connection.established` | Thời gian kết nối, cluster/agent alias nếu an toàn |
| Bắt đầu đăng ký | `service.registration.started` | Service ID, instance ID, operation ID |
| Đăng ký thành công | `service.registration.succeeded` | Thời gian, provider, trạng thái cuối |
| Đăng ký thất bại | `service.registration.failed` | Error type, retryable, attempt, nguyên nhân đã chuẩn hóa |
| Lên lịch retry | `service.registration.retry_scheduled` | Attempt tiếp theo, backoff, giới hạn retry |
| Mất kết nối | `registry.connection.suspended` | Trạng thái cũ/mới, thời điểm, ảnh hưởng cache |
| Kết nối lại | `registry.connection.reconnected` | Thời gian gián đoạn, session còn hay mất nếu provider cung cấp |
| Khôi phục đăng ký | `service.registration.restored` | Instance ID, operation ID mới/cũ, thời gian hội tụ |
| Dừng ứng dụng | `service.registration.deregistered` | Lý do dừng, thời gian drain, kết quả deregister |

Nên dùng event name ổn định để dashboard và alert không phụ thuộc câu chữ tự do trong message. Message có thể thay đổi cho dễ đọc; `event.name` nên giữ ổn định như một phần schema.

## 4. Log quá trình tự cấu hình một cách an toàn

Ứng dụng Spring Boot có thể nhận cấu hình từ nhiều nguồn: `application.yml`, profile, environment variables, command-line arguments, Config Server, Consul Config hoặc Kubernetes ConfigMap/Secret. Khi ứng dụng khởi động, cần biết **cấu hình nào đã được chọn** và **giá trị nào đã được xác thực**, nhưng không được dump toàn bộ `Environment`.

Ví dụ cấu hình discovery:

```yaml
app:
  discovery:
    provider: ${DISCOVERY_PROVIDER:consul}
    service-id: ${spring.application.name}
    registry-endpoint: ${REGISTRY_ENDPOINT:consul-agent:8500}
    connect-timeout: 3s
    max-attempts: 5
    environment: ${APP_ENV:local}
```

Có thể bind vào `@ConfigurationProperties` và validate trước khi tạo client:

```java
import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.discovery")
public record DiscoveryProperties(
        @NotBlank String provider,
        @NotBlank String serviceId,
        @NotBlank String registryEndpoint,
        @NotNull Duration connectTimeout,
        @Min(1) @Max(10) int maxAttempts,
        @NotBlank String environment
) {}
```

Đăng ký properties bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(DiscoveryProperties.class)`. Sau khi bind và validate, chỉ log các field được phép:

Để các annotation Jakarta Validation được thực thi, thêm `spring-boot-starter-validation` nếu ứng dụng chưa có validation provider trên classpath.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DiscoveryStartupLogging {

    private static final Logger log =
            LoggerFactory.getLogger(DiscoveryStartupLogging.class);

    @Bean
    ApplicationRunner logDiscoveryConfiguration(DiscoveryProperties properties) {
        return args -> log.atInfo()
                .addKeyValue("event.name", "discovery.config.validated")
                .addKeyValue("discovery.provider", properties.provider())
                .addKeyValue("service.name", properties.serviceId())
                .addKeyValue("deployment.environment", properties.environment())
                .addKeyValue("registry.endpoint", properties.registryEndpoint())
                .addKeyValue("connect.timeout.ms", properties.connectTimeout().toMillis())
                .addKeyValue("retry.max", properties.maxAttempts())
                .log("Discovery configuration validated");
    }
}
```

Ví dụ dùng SLF4J 2 fluent logging API, thường có trong các ứng dụng Spring Boot 3. Nếu dùng SLF4J 1.7, dùng placeholder logging hoặc MDC thay cho `atInfo().addKeyValue(...)`.

Không log:

- Password, client secret, bearer token, API key, private key hoặc raw ServiceAccount token.
- Toàn bộ `Environment`, toàn bộ `@ConfigurationProperties` object hoặc `toString()` của object có thể chứa secret.
- URI có user-info, token trong query string hoặc header xác thực.
- Nội dung Secret, credential hoặc dữ liệu người dùng lấy từ Config Server/KV.

Nếu cần chứng minh cấu hình đến từ nguồn nào, ghi `config.source=consul-kv` hoặc `config.profile=production`; không cần in toàn bộ property value. Với cấu hình thay đổi runtime, ghi `config.revision` hoặc version/hash không nhạy cảm để đối chiếu các replica.

## 5. Cấu hình log trong Spring Boot

Ví dụ đặt mức log cho phần discovery và provider integration:

```yaml
logging:
  level:
    com.example.discovery: INFO
    org.springframework.cloud.client.serviceregistry: INFO
    org.springframework.cloud.netflix.eureka: INFO
    org.springframework.cloud.consul: INFO
    org.apache.curator: INFO
```

Tên logger cụ thể có thể thay đổi theo phiên bản Spring Cloud, Eureka, Consul hoặc Curator. Khi cần điều tra, tăng DEBUG có chọn lọc cho package liên quan trong thời gian ngắn; không bật TRACE toàn bộ hệ thống lâu dài vì có thể tạo lượng log lớn và lộ thông tin kết nối.

Với Spring Boot 3.4 trở lên, có thể dùng structured logging tích hợp để xuất JSON theo format hỗ trợ, ví dụ ECS:

```yaml
logging:
  structured:
    format:
      console: ecs
```

Nếu dùng phiên bản Spring Boot cũ hơn, có thể cấu hình encoder JSON của logging stack đang dùng. Dù dùng formatter nào, cần bảo đảm field `event.name`, service identity và operation context được giữ nguyên qua pipeline.

## 6. Log đăng ký service: bắt đầu, thành công và thất bại

Đăng ký service là thao tác lifecycle, không chỉ là một dòng `Registered`. Nên log cả điểm bắt đầu và kết quả để tính thời gian và phân biệt lỗi kết nối với lỗi dữ liệu đăng ký.

Ví dụ một helper log cho thao tác registration do ứng dụng quản lý:

```java
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RegistrationLog {

    private static final Logger log =
            LoggerFactory.getLogger(RegistrationLog.class);

    public void succeeded(
            String serviceId,
            String instanceId,
            String provider,
            String operationId,
            Duration duration) {

        log.atInfo()
                .addKeyValue("event.name", "service.registration.succeeded")
                .addKeyValue("service.name", serviceId)
                .addKeyValue("service.instance.id", instanceId)
                .addKeyValue("discovery.provider", provider)
                .addKeyValue("operation.id", operationId)
                .addKeyValue("duration.ms", duration.toMillis())
                .addKeyValue("registration.state", "REGISTERED")
                .log("Service instance registered");
    }

    public void failed(
            String serviceId,
            String instanceId,
            String provider,
            String operationId,
            int attempt,
            Throwable error) {

        log.atWarn()
                .addKeyValue("event.name", "service.registration.failed")
                .addKeyValue("service.name", serviceId)
                .addKeyValue("service.instance.id", instanceId)
                .addKeyValue("discovery.provider", provider)
                .addKeyValue("operation.id", operationId)
                .addKeyValue("retry.attempt", attempt)
                .addKeyValue("error.type", error.getClass().getSimpleName())
                .setCause(error)
                .log("Service instance registration failed");
    }
}
```

Đây là helper để dùng quanh thao tác registration do ứng dụng sở hữu. Nếu Spring Cloud auto-registration đang quản lý lifecycle, không gọi đăng ký lần thứ hai chỉ để tạo log. Hãy quan sát log của framework, các lifecycle event được cung cấp bởi phiên bản đang dùng hoặc bổ sung observer tại đúng extension point.

Không ghi log `REGISTERED` trước khi registry xác nhận thao tác thành công. Nếu provider chỉ chấp nhận đăng ký bất đồng bộ, hãy phân biệt `registration.requested` với `registration.confirmed`.

## 7. Ghi log retry có thể điều tra

Khi kết nối registry thất bại, cần phân loại lỗi trước khi retry:

- **Transient:** timeout, connection reset, leader election hoặc agent tạm thời không sẵn sàng.
- **Configuration/permanent:** sai hostname, port, scheme, token, ACL, TLS trust hoặc service ID không hợp lệ.
- **Capacity/throttling:** registry quá tải hoặc từ chối tạm thời do giới hạn request.

Ví dụ một chuỗi retry có ngữ cảnh:

```json
{
  "event.name": "registry.connection.retry_scheduled",
  "service.name": "inventory-service",
  "service.instance.id": "inventory-10-20-1-15-8081",
  "discovery.provider": "eureka",
  "registry.endpoint": "eureka-1.internal:8761",
  "retry.attempt": 2,
  "retry.max": 5,
  "retry.delay.ms": 2000,
  "error.type": "ConnectTimeoutException",
  "error.category": "transient",
  "operation.id": "reg-7f21a9"
}
```

Nên log một dòng khi lên lịch retry, kèm attempt và delay thực tế. Không ghi stack trace đầy đủ ở mọi lần retry nếu cùng một lỗi lặp lại liên tục; có thể log stack trace ở lần đầu và lần cuối, còn các lần giữa chỉ ghi loại lỗi và endpoint alias.

Backoff và jitter giúp giảm tình trạng nhiều replica retry cùng thời điểm. Log phải phản ánh delay đã tính sau khi áp dụng jitter, để người vận hành biết khi nào lần thử kế tiếp dự kiến diễn ra.

## 8. Log reconnect theo state transition

Không nên ghi một dòng `Reconnected` cho mọi loại provider mà không phân biệt trạng thái trước đó. Một mô hình chung có thể dùng các trạng thái:

```text
STARTING -> CONNECTING -> CONNECTED
CONNECTED -> SUSPENDED -> RECONNECTING -> RECONNECTED
RECONNECTED -> RECONCILING -> READY
CONNECTED -> SESSION_LOST -> NEW_SESSION -> REGISTERING -> REGISTERED
```

Các trạng thái là mô hình quan sát chung của ứng dụng; tên event thực tế phụ thuộc provider. `RECONNECTED` chỉ nói rằng kết nối đã trở lại. `READY` nên chỉ được ghi sau khi các bước đồng bộ cache hoặc đăng ký lại bắt buộc đã hoàn tất.

Ví dụ log state transition:

```java
log.atWarn()
        .addKeyValue("event.name", "registry.connection.state_changed")
        .addKeyValue("service.name", serviceId)
        .addKeyValue("service.instance.id", instanceId)
        .addKeyValue("discovery.provider", provider)
        .addKeyValue("connection.state.previous", "CONNECTED")
        .addKeyValue("connection.state.current", "SUSPENDED")
        .addKeyValue("operation.id", operationId)
        .log("Registry connection suspended");
```

Khi kết nối trở lại, log cả thời gian gián đoạn và kết quả reconciliation:

```json
{
  "event.name": "registry.recovery.completed",
  "service.name": "inventory-service",
  "discovery.provider": "zookeeper",
  "connection.state": "RECONNECTED",
  "session.state": "NEW_SESSION",
  "registration.state": "REGISTERED",
  "cache.state": "INITIALIZED",
  "outage.duration.ms": 12450,
  "operation.id": "recovery-b193c2"
}
```

Nếu kết nối trở lại nhưng registration chưa thành công, ghi `registry.connection.reconnected` và `service.registration.retry_scheduled` riêng. Không gộp thành một log thành công gây hiểu nhầm.

## 9. Khác biệt log theo provider

Các registry có lifecycle khác nhau; schema log chung nên được bổ sung field đặc thù thay vì ép mọi provider dùng một trạng thái giống hệt nhau.

| Provider | Sự kiện cần quan sát | Ngữ cảnh đặc thù |
| --- | --- | --- |
| Eureka | Client register, heartbeat/renew, fetch registry, status change, deregister | Application name, instance ID, server URL alias, lease/renew result, fetch duration |
| Consul | Agent registration, health check, catalog lookup, deregister, ACL/TLS failure | Service ID, node, check ID/status, datacenter/namespace, agent endpoint alias |
| ZooKeeper/Curator | Connected, SUSPENDED, RECONNECTED, LOST, session recovery, ephemeral node registration | Ensemble alias, znode path đã chuẩn hóa, session state, retry count, cache initialization |
| Kubernetes | API discovery, list/watch, informer/cache sync, RBAC failure, endpoint update | Namespace, resource kind, API group, ServiceAccount identity (không log token), resource version nếu phù hợp |

### Eureka

Khi dùng Eureka, cần phân biệt ba hoạt động:

1. Đăng ký instance lên Eureka Server.
2. Gửi heartbeat để gia hạn lease.
3. Fetch/refresh registry cục bộ để tra cứu service khác.

Log `register succeeded` không chứng minh consumer đã fetch được registry mới. Log heartbeat liên tục ở INFO thường tạo nhiễu; nên dùng metric cho tần suất heartbeat và chỉ log WARN/ERROR khi renew thất bại kéo dài hoặc có chuyển trạng thái đáng chú ý.

### Consul

Với Consul, registration có thể được gửi đến agent cục bộ; agent thực hiện check và cập nhật trạng thái catalog/health. Vì vậy, cần phân biệt `registration accepted by agent` với `health check passing`. Nếu check ở `critical`, log nên có check ID, check type, output đã làm sạch và thời điểm check gần nhất; tránh đưa raw output có thể chứa thông tin nhạy cảm.

### ZooKeeper và Curator

Curator phát các trạng thái `CONNECTED`, `SUSPENDED`, `RECONNECTED`, `LOST` và có thể `READ_ONLY`. `SUSPENDED` nghĩa là kết nối tạm thời mất và cache có thể stale; `LOST` nghĩa session hết hạn, ephemeral nodes gắn với session cũ bị xóa. Sau `LOST`, log cần thể hiện session mới, việc đăng ký lại znode và thời điểm cache được khởi tạo lại.

Không log session credential hoặc dữ liệu znode đầy đủ nếu payload chứa metadata nhạy cảm. Chỉ log path/service ID đã chuẩn hóa và instance ID.

### Kubernetes

Với Spring Cloud Kubernetes, lỗi `403 Forbidden` cần log resource, API group, verb và namespace để phân biệt RBAC thiếu quyền với lỗi kết nối API server. Không log bearer token. Khi dùng informer, cần phân biệt `watch connected` với `initial cache sync completed`; chỉ sau khi cache sync xong mới nên ghi discovery data sẵn sàng.

## 10. Dùng MDC và operation ID để nối các dòng log

MDC (Mapped Diagnostic Context) gắn field vào các log phát sinh trong một phạm vi thực thi. Ví dụ thêm service identity và operation ID trong một thao tác registration đồng bộ:

```java
import org.slf4j.MDC;

public void registerWithContext(String serviceId, String instanceId,
                                String operationId) {
    try (MDC.MDCCloseable service = MDC.putCloseable("service.name", serviceId);
         MDC.MDCCloseable instance = MDC.putCloseable("service.instance.id", instanceId);
         MDC.MDCCloseable operation = MDC.putCloseable("operation.id", operationId)) {

        log.info("Starting service registration");
        performRegistration();
        log.info("Service registration completed");
    }
}
```

`MDC.putCloseable` có trong SLF4J hiện đại. Cách dùng try-with-resources giúp khôi phục context trước đó và tránh rò field sang request/thread kế tiếp.

Không dùng MDC như một kho trạng thái toàn cục. Với thread pool hoặc tác vụ bất đồng bộ, context phải được truyền qua executor đúng cách. Trong WebFlux/Reactor, MDC dựa trên ThreadLocal không tự động đi theo mọi thread switch; nên dùng Micrometer Context Propagation/Observation hoặc Micrometer Tracing được tích hợp với Reactor thay vì tự `MDC.put()` ở một operator rồi giả định nó tồn tại ở operator tiếp theo.

`traceId` và `spanId` liên kết log với distributed trace của request. Registration/reconnect có thể xảy ra ngoài request nên không có trace context; khi đó dùng `operation.id` riêng để nối các bước lifecycle. Không tạo trace ID giả rồi gọi nó là trace nghiệp vụ.

## 11. Log thay đổi cấu hình runtime

Một số ứng dụng refresh cấu hình khi Config Server, Consul KV hoặc Kubernetes ConfigMap thay đổi. Khi có thay đổi, log nên ghi:

- Sự kiện `discovery.config.refresh.started` và `discovery.config.refresh.completed`.
- Nguồn cấu hình và profile/context.
- Revision/version/hash không nhạy cảm.
- Những nhóm property được thay đổi, không cần in mọi giá trị.
- Các client hoặc component nào cần reconnect/re-register sau refresh.
- Kết quả áp dụng và thời gian thực hiện.

Ví dụ:

```json
{
  "event.name": "discovery.config.refresh.completed",
  "service.name": "inventory-service",
  "config.source": "consul-kv",
  "config.profile": "production",
  "config.revision": "cfg-2026-11-24-03",
  "changed.keys": [
    "app.discovery.connect-timeout",
    "app.discovery.max-attempts"
  ],
  "duration.ms": 42
}
```

Nếu refresh làm thay đổi service ID, instance ID hoặc registry endpoint, cần có bước validate và lifecycle transition rõ ràng. Không âm thầm đổi endpoint giữa lúc đang có registration cũ; cần xác định có phải deregister endpoint cũ, kết nối endpoint mới và đăng ký lại hay không.

## 12. Chọn log level để không tạo nhiễu

| Level | Nên dùng cho | Ví dụ |
| --- | --- | --- |
| ERROR | Không thể hoàn thành thao tác sau policy retry hoặc cấu hình không thể phục hồi | Hết retry đăng ký, sai TLS trust, token bị từ chối và không có phương án fallback |
| WARN | Suy giảm tạm thời hoặc trạng thái bất thường cần theo dõi | Registry mất kết nối, retry được lên lịch, cache stale, health check critical |
| INFO | Mốc lifecycle có ý nghĩa và thay đổi trạng thái đã hoàn tất | Cấu hình được validate, đăng ký thành công, reconnect/reconciliation hoàn tất, deregister |
| DEBUG | Chi tiết phục vụ điều tra ngắn hạn | Chọn endpoint, property source precedence, request metadata đã làm sạch |
| TRACE | Giao thức hoặc chi tiết nội bộ rất nhiều | Watch event, heartbeat chi tiết, retry loop nội bộ |

Không log mỗi heartbeat hoặc mỗi lần polling registry ở INFO. Các hoạt động định kỳ nên được quan sát bằng metric như `registry_heartbeat_total`, `registry_fetch_duration`, `registration_retry_total`, `registry_reconnect_total` và `registry_cache_age_seconds`.

## 13. Từ log đến metric và trace

Log giải thích một sự kiện cụ thể; metric cho biết xu hướng và tần suất; trace nối các bước của một request xuyên nhiều service. Ba loại telemetry bổ sung cho nhau.

| Câu hỏi | Telemetry phù hợp |
| --- | --- |
| Instance nào vừa đăng ký thất bại và lỗi gì? | Log có service/instance/operation context |
| Tỷ lệ đăng ký thất bại tăng từ lúc nào? | Counter và alert theo provider/environment |
| Reconnect mất trung bình bao lâu? | Histogram về outage/recovery duration |
| Request nào bị lỗi khi LoadBalancer chọn instance? | Distributed trace với service ID và peer span |
| Cache discovery đang cũ bao lâu? | Gauge về cache age/last successful refresh |
| Có bao nhiêu lần retry đã xảy ra? | Counter theo error category, không gắn label có cardinality cao |

Tránh dùng `instance.id`, `operation.id` hoặc raw endpoint làm label metric vì số lượng giá trị có thể tăng không giới hạn. Các field chi tiết này phù hợp với log/trace; metric nên dùng nhãn có cardinality thấp như provider, environment, service name và outcome.

## 14. Điều tra một sự cố registration/reconnect

Giả sử `inventory-service` thỉnh thoảng biến mất khỏi registry. Có thể điều tra theo trình tự:

1. Tìm `service.name=inventory-service` và `service.instance.id` cụ thể.
2. Kiểm tra sự kiện `discovery.config.validated` để biết provider, endpoint alias, profile và cấu hình retry.
3. Tìm `service.registration.succeeded` gần nhất để xác định lần đăng ký thành công cuối.
4. Tìm `registry.connection.state_changed` hoặc `registry.connection.retry_scheduled` để biết lúc nào mất kết nối.
5. Đối chiếu `retry.attempt`, `error.type`, `duration.ms` và endpoint alias để phân loại timeout, DNS, ACL hay TLS.
6. Với Consul, kiểm tra thêm health check status; với Eureka, kiểm tra heartbeat và instance status; với ZooKeeper, kiểm tra `LOST` và session recovery.
7. Tìm `service.registration.restored` hoặc `registry.recovery.completed` để xác nhận đã hội tụ.
8. Nếu reconnect thành công nhưng consumer vẫn không tìm thấy instance, kiểm tra cache/fetch refresh ở phía consumer.

Ví dụ truy vấn khái niệm trong log platform:

```text
service.name = "inventory-service"
AND event.name IN (
  "service.registration.failed",
  "registry.connection.retry_scheduled",
  "registry.connection.reconnected",
  "service.registration.restored"
)
ORDER BY @timestamp ASC
```

Tên cú pháp truy vấn phụ thuộc Elasticsearch, Loki, Splunk hoặc nền tảng log đang sử dụng. Điều quan trọng là schema field nhất quán để có thể dựng timeline.

## 15. Tránh log storm và bảo vệ dữ liệu

Khi registry mất kết nối, nhiều replica có thể retry cùng lúc. Nếu mỗi retry ghi stack trace đầy đủ ở ERROR, log pipeline có thể bị quá tải đúng lúc cần điều tra nhất.

Các biện pháp nên áp dụng:

- Dùng exponential backoff có jitter và giới hạn số lần retry.
- Log một sự kiện khi trạng thái chuyển từ connected sang degraded, không log lặp lại cùng trạng thái mỗi giây.
- Ghi attempt/delay/error category ở các lần retry nhưng giảm stack trace lặp.
- Có log rõ khi retry thành công hoặc policy bị exhausted.
- Dùng rate limiting hoặc sampling cho các event lặp với tần suất cao.
- Không log token, password, secret, raw config, dữ liệu cá nhân hoặc payload registry đầy đủ.
- Làm sạch exception message nếu nó có thể chứa URL, header hoặc credential.
- Giới hạn quyền đọc log vì endpoint nội bộ, topology và instance ID vẫn có thể là thông tin nhạy cảm.

Không được che mất lần chuyển trạng thái đầu tiên hoặc lần retry cuối cùng bằng sampling. Những mốc lifecycle quan trọng phải luôn có khả năng truy vết.

## 16. Checklist logging cho discovery

- [ ] Mọi log lifecycle quan trọng có service name, instance ID và provider.
- [ ] Có environment, version và registry endpoint alias khi phù hợp.
- [ ] Có event name ổn định và operation ID để nối các bước.
- [ ] Log cấu hình chỉ ghi giá trị được phép; không dump toàn bộ properties hoặc Environment.
- [ ] Registration có log started/succeeded/failed và duration.
- [ ] Retry có attempt, max, delay, error type và error category.
- [ ] Reconnect ghi trạng thái trước/sau và kết quả reconciliation.
- [ ] Phân biệt kết nối trở lại với cache/registration đã phục hồi.
- [ ] Có field trace/span khi hoạt động nằm trong request trace; dùng operation ID cho lifecycle ngoài request.
- [ ] MDC được dọn đúng cách và context được truyền đúng qua async/reactive boundary.
- [ ] Heartbeat/polling định kỳ không tạo log INFO liên tục.
- [ ] Secret, token, credential và dữ liệu cá nhân không xuất hiện trong log.
- [ ] Metric theo dõi tỷ lệ lỗi, retry, outage duration và cache age.
- [ ] Đã thử truy vấn timeline cho một instance cụ thể trong tình huống reconnect.

Log discovery tốt không chỉ ghi rằng ứng dụng đã kết nối hay đăng ký thành công. Nó phải cho thấy service/instance nào đang hoạt động, dùng cấu hình và provider nào, thao tác diễn ra trong ngữ cảnh nào, đã retry bao nhiêu lần và sau reconnect những thành phần nào thực sự được khôi phục. Khi schema nhất quán, log an toàn và có operation context, đội vận hành có thể dựng lại vòng đời registration từ lúc tự cấu hình đến khi instance trở lại trạng thái sẵn sàng.
