# Liên kết log với `serviceId`, `instanceId` và vùng triển khai

## 1. Vì sao log cần định danh service và instance?

Trong hệ thống microservice, một request có thể đi qua gateway, nhiều service và nhiều instance nằm ở các node hoặc availability zone khác nhau. Khi có lỗi, chỉ có timestamp và message thường không đủ để xác định log đến từ service nào, instance nào hoặc vùng triển khai nào.

Mỗi log record nên mang theo định danh của process tạo ra log. Tối thiểu cần có:

- `serviceId`: tên logic của service, thường lấy từ `spring.application.name`.
- `instanceId`: định danh duy nhất của một bản chạy trong cùng service.
- `region`: vùng triển khai lớn, ví dụ `ap-southeast-1`.
- `zone`: vùng sẵn sàng hoặc failure domain nhỏ hơn, ví dụ `ap-southeast-1a`.

Trong Spring Cloud Service Discovery, registry cũng lưu service ID, instance ID, host, port và metadata. Nếu log sử dụng cùng quy ước định danh với registry, người vận hành có thể đi từ log tới đúng bản ghi instance, xem trạng thái đăng ký/health và xác định vùng đang gặp sự cố.

## 2. Phân biệt serviceId, instanceId, region và zone

| Trường | Ví dụ | Phạm vi | Nguồn phù hợp |
|---|---|---|---|
| `serviceId` | `payment-service` | Chung cho các instance của một service | `spring.application.name` hoặc tên service đã đăng ký |
| `instanceId` | `payment-service:pod-7f9c` | Riêng từng bản chạy | Pod UID, instance ID cấu hình hoặc hostname/port có bảo đảm duy nhất |
| `region` | `ap-southeast-1` | Khu vực triển khai lớn | Cấu hình môi trường hoặc metadata hạ tầng |
| `zone` | `ap-southeast-1a` | Availability zone/failure domain | Cấu hình scheduler/hạ tầng hoặc metadata node |
| `namespace` | `payments` | Phạm vi tài nguyên Kubernetes | Kubernetes Pod metadata hoặc cấu hình runtime |
| `podName` | `payment-service-7f9c8` | Tên Pod hiện tại | Kubernetes Downward API |
| `environment` | `production` | Môi trường triển khai | Profile/configuration của deployment |

`serviceId` và `instanceId` không thể thay thế nhau. Nhiều instance cùng thuộc `payment-service`, nhưng mỗi instance cần ID riêng để truy vết. `region` và `zone` cũng không phải một trường: nhiều zone có thể nằm trong cùng region.

Nên thống nhất cách viết tên trường trên toàn hệ thống. Nếu log dùng `serviceId`/`instanceId`, có thể ánh xạ sang OpenTelemetry Resource Attributes tương ứng như `service.name` và `service.instance.id`. Với môi trường Kubernetes, có thể bổ sung `k8s.namespace.name`, `k8s.pod.name` và `cloud.region`/`cloud.availability_zone` khi các giá trị đó có nguồn đáng tin cậy.

## 3. Chọn nguồn định danh ổn định

### 3.1. Service ID

Trong ứng dụng Spring Boot, `spring.application.name` thường là nguồn tự nhiên cho service ID:

```yaml
spring:
  application:
    name: payment-service
```

Hãy dùng cùng giá trị này trong log, registry và cấu hình client. Một số registry chuẩn hóa tên hiển thị, ví dụ Eureka thường hiển thị app name dạng chữ hoa. Khi ghi log, nên chọn một dạng canonical ổn định (thường là giá trị cấu hình Spring) và ánh xạ dạng hiển thị của registry khi cần đối chiếu.

### 3.2. Instance ID

`instanceId` phải phân biệt được các instance đang chạy đồng thời. Có thể dùng:

- Kubernetes Pod UID nếu muốn ID duy nhất trong suốt vòng đời Pod.
- Pod name nếu tên Pod đã duy nhất trong namespace và hệ thống log có thêm namespace.
- Hostname cộng port nếu triển khai trên VM/bare metal và tổ hợp này duy nhất.
- ID do nền tảng cấp khi đăng ký với Eureka/Consul.

Ví dụ cấu hình theo biến môi trường:

```yaml
app:
  identity:
    instance-id: ${INSTANCE_ID:${HOSTNAME:local}}
    region: ${DEPLOYMENT_REGION:local}
    zone: ${DEPLOYMENT_ZONE:local}
    namespace: ${POD_NAMESPACE:default}
    environment: ${DEPLOYMENT_ENV:local}
```

Không dùng một giá trị cố định như `payment-service-1` cho mọi replica. Nếu các instance trùng ID, log khó phân biệt và registry có thể ghi đè hoặc xung đột bản đăng ký tùy implementation.

### 3.3. Region và zone

Region/zone nên đến từ cấu hình triển khai hoặc metadata hạ tầng có thể xác minh. Không suy luận zone từ IP, hostname ngẫu nhiên hoặc tên Pod. Trong Kubernetes, Downward API có thể cung cấp Pod name, namespace, UID, Pod IP và node name; nó không tự cung cấp mọi label của Node, bao gồm `topology.kubernetes.io/zone`.

Có thể truyền zone vào container từ Helm values, ConfigMap, admission controller hoặc một thành phần metadata có quyền đọc Node. Nếu ứng dụng truy vấn Kubernetes API để đọc label của Node, chỉ cấp RBAC tối thiểu và xử lý trường hợp metadata chưa có. Đối với deployment ngoài Kubernetes, đặt region/zone bằng biến môi trường hoặc cấu hình nền tảng.

## 4. Đưa định danh Kubernetes vào môi trường ứng dụng

Kubernetes Downward API là cách phổ biến để đưa metadata của Pod vào environment variables mà không cần gọi Kubernetes API từ ứng dụng:

```yaml
spec:
  containers:
    - name: payment-service
      env:
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: POD_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        - name: POD_UID
          valueFrom:
            fieldRef:
              fieldPath: metadata.uid
        - name: POD_IP
          valueFrom:
            fieldRef:
              fieldPath: status.podIP
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        - name: INSTANCE_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.uid
        - name: DEPLOYMENT_REGION
          value: ap-southeast-1
        - name: DEPLOYMENT_ZONE
          value: ap-southeast-1a
        - name: DEPLOYMENT_ENV
          value: production
```

Trong ví dụ, region/zone được truyền từ cấu hình triển khai. Nếu nhiều replica có thể chạy ở nhiều zone, không nên gán cùng một zone cố định cho cả Deployment; hãy inject giá trị đúng theo node/placement hoặc dùng một cơ chế metadata phù hợp với topology.

Có thể dùng Pod UID làm instance ID và Pod name làm trường hiển thị. UID tránh nhầm lẫn khi Pod mới được tạo lại với tên khác hoặc khi log cũ vẫn còn trong hệ thống lưu trữ.

## 5. Thiết kế schema log nhất quán

Một schema log JSON nên chứa cả định danh service, instance, vùng triển khai và ngữ cảnh request:

```json
{
  "timestamp": "2026-11-24T14:30:12.345Z",
  "level": "INFO",
  "message": "Payment request accepted",
  "serviceId": "payment-service",
  "instanceId": "7b6d4e4a-2a31-4d5c-9c8d-1a2b3c4d5e6f",
  "region": "ap-southeast-1",
  "zone": "ap-southeast-1a",
  "namespace": "payments",
  "podName": "payment-service-7f9c8",
  "environment": "production",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "requestId": "req-8f12"
}
```

Quy ước:

- `serviceId`, `instanceId`, `region`, `zone`, `namespace`, `podName` mô tả nơi tạo log.
- `traceId` và `spanId` liên kết các span/log thuộc cùng một distributed trace.
- `requestId` là mã yêu cầu ở tầng ứng dụng nếu hệ thống cần một mã nghiệp vụ riêng.
- `environment` phân biệt dev, staging và production.

Không dùng một trường chung như `service` để lúc thì ghi service tạo log, lúc thì ghi service đích. Log inbound nên mô tả service hiện tại; log outbound nên dùng các trường có namespace riêng như `destination.serviceId`, `destination.instanceId` và `destination.zone`.

## 6. Gắn định danh vào MDC trong Spring MVC

Với ứng dụng Spring MVC chạy trên Servlet stack, có thể dùng `OncePerRequestFilter` để thêm định danh của instance vào SLF4J MDC cho toàn bộ log trong request:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
public class ObservabilityIdentityFilter extends OncePerRequestFilter {

    private final String serviceId;
    private final String instanceId;
    private final String region;
    private final String zone;
    private final String namespace;

    public ObservabilityIdentityFilter(
            @Value("${spring.application.name:unknown}") String serviceId,
            @Value("${app.identity.instance-id:unknown}") String instanceId,
            @Value("${app.identity.region:unknown}") String region,
            @Value("${app.identity.zone:unknown}") String zone,
            @Value("${app.identity.namespace:unknown}") String namespace) {
        this.serviceId = serviceId;
        this.instanceId = instanceId;
        this.region = region;
        this.zone = zone;
        this.namespace = namespace;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        MDC.put("serviceId", serviceId);
        MDC.put("instanceId", instanceId);
        MDC.put("region", region);
        MDC.put("zone", zone);
        MDC.put("namespace", namespace);

        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove("serviceId");
            MDC.remove("instanceId");
            MDC.remove("region");
            MDC.remove("zone");
            MDC.remove("namespace");
        }
    }
}
```

Filter lấy identity từ cấu hình cục bộ của process, không lấy `serviceId` hoặc `instanceId` từ header do caller gửi. Việc xóa MDC trong `finally` rất quan trọng vì Servlet container tái sử dụng thread; nếu không xóa, request sau có thể ghi nhầm identity của request trước.

Ví dụ `application.yml`:

```yaml
spring:
  application:
    name: payment-service

app:
  identity:
    instance-id: ${INSTANCE_ID:${HOSTNAME:local}}
    region: ${DEPLOYMENT_REGION:unknown}
    zone: ${DEPLOYMENT_ZONE:unknown}
    namespace: ${POD_NAMESPACE:unknown}
```

Nếu không dùng Servlet stack, không dùng filter này một cách máy móc; xem phần WebFlux và asynchronous context bên dưới.

## 7. Định dạng log để collector dễ truy vấn

### 7.1. Pattern console với MDC

Với Logback, có thể đưa MDC fields vào pattern. Nếu muốn identity xuất hiện cả trong log khởi động và tác vụ nền không đi qua HTTP filter, có thể đọc các thuộc tính cấu hình một lần trong `logback-spring.xml` bằng `springProperty`:

```xml
<configuration>
    <springProperty scope="context" name="serviceId" source="spring.application.name" defaultValue="unknown" />
    <springProperty scope="context" name="instanceId" source="app.identity.instance-id" defaultValue="unknown" />
    <springProperty scope="context" name="region" source="app.identity.region" defaultValue="unknown" />
    <springProperty scope="context" name="zone" source="app.identity.zone" defaultValue="unknown" />

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level serviceId=${serviceId} instanceId=${instanceId} region=${region} zone=${zone} namespace=%X{namespace} traceId=%X{traceId} spanId=%X{spanId} [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Các trường identity được đọc từ cấu hình là cố định trong suốt vòng đời process, nên xuất hiện cả ở log startup, scheduler và background worker. Các trường request/trace vẫn lấy từ MDC. Nếu chọn cách này, không đồng thời ghi lặp `serviceId`, `instanceId`, `region` và `zone` từ MDC trong cùng pattern. Một lựa chọn khác là đưa toàn bộ identity vào MDC như filter ở phần trước và dùng encoder đọc MDC; hãy chọn một cách để tránh field trùng.

Pattern text dễ đọc khi phát triển, nhưng log collector phải parse chính xác các key/value. Trong production, JSON thường thuận tiện hơn vì mỗi thuộc tính là một field độc lập, dễ lọc và dễ liên kết. Với JSON encoder, cấu hình các identity fields như resource/global fields và chỉ dùng MDC cho context thay đổi theo request.

### 7.2. Ví dụ JSON log

Một log encoder JSON có thể ghi MDC thành các field cùng cấp:

```json
{
  "timestamp": "2026-11-24T14:30:12.345Z",
  "level": "WARN",
  "logger": "com.example.payment.PaymentService",
  "message": "Inventory service call timed out",
  "serviceId": "payment-service",
  "instanceId": "payment-service-pod-7f9c8",
  "region": "ap-southeast-1",
  "zone": "ap-southeast-1a",
  "namespace": "payments",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7"
}
```

Đảm bảo timestamp được ghi theo ISO 8601 và có timezone/UTC offset. Không nối tất cả thông tin vào một chuỗi `message`, vì collector sẽ khó lọc theo từng field.

## 8. Liên kết log với distributed trace

`serviceId` và `instanceId` trả lời câu hỏi log đến từ đâu. `traceId` và `spanId` trả lời câu hỏi log thuộc request/operation nào. Hai nhóm trường bổ sung cho nhau:

- Một `traceId` có thể đi qua nhiều service và instance.
- Mỗi service tạo span riêng, thường có `spanId` khác nhau.
- Nhiều log trong cùng một span có thể mang cùng trace/span ID.
- Một instance xử lý nhiều trace khác nhau theo thời gian.

Với Spring Boot dùng Micrometer Tracing, khi cấu hình bridge/exporter phù hợp, trace/span context có thể được đưa vào MDC để log pattern hoặc JSON encoder ghi ra. Không tự ghi đè `traceId`/`spanId` bằng request ID hoặc instance ID.

Ví dụ cấu hình tracing sampling cơ bản:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
```

Sampling `0.1` nghĩa là lấy mẫu khoảng 10% trace theo cơ chế sampler đang dùng; điều chỉnh theo tải, chi phí và yêu cầu điều tra. Nếu cần giữ trace cho lỗi hoặc request đặc biệt, hãy dùng chính sách sampling phù hợp thay vì tăng vô hạn mọi log.

Nếu hệ thống nhận `traceparent` theo W3C Trace Context, instrumentation nên quản lý việc trích xuất và truyền tiếp context. Với `X-Request-ID`, chỉ chấp nhận theo chính sách tin cậy: validate độ dài/format, tạo ID mới nếu thiếu và không dùng giá trị tùy ý từ internet làm nhãn có quyền kiểm soát.

## 9. Truyền MDC qua async và WebFlux

MDC dựa trên thread-local. Khi request chuyển sang thread khác qua `@Async`, executor hoặc callback, MDC có thể không tự đi theo. Cần dùng cơ chế context propagation phù hợp với phiên bản Spring và Micrometer.

Với Spring Framework hỗ trợ `ContextPropagatingTaskDecorator`, có thể cấu hình executor:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;

@Configuration
public class AsyncConfiguration {

    @Bean
    TaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }

    @Bean
    Executor applicationTaskExecutor(TaskDecorator contextPropagatingTaskDecorator) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setTaskDecorator(contextPropagatingTaskDecorator);
        executor.setThreadNamePrefix("app-async-");
        executor.initialize();
        return executor;
    }
}
```

Context propagation cần được cấu hình và kiểm thử với tracing/MDC accessors đã đăng ký trong ứng dụng. Không tự copy toàn bộ MDC vào thread pool rồi quên xóa; thread pool tái sử dụng thread nên context cũ có thể rò sang tác vụ khác.

Với Spring WebFlux, request có thể chuyển thread giữa các operator. Không dựa vào Servlet `OncePerRequestFilter` hoặc thread-local MDC thuần để giữ context xuyên suốt reactive chain. Dùng Reactor Context và Micrometer Context Propagation/automatic context propagation theo phiên bản Spring Boot, rồi kiểm tra log ở các operator chạy trên scheduler khác nhau.

## 10. Liên kết log với metadata của registry

Log identity nên khớp với thông tin mà discovery provider công bố. Có thể dùng các cơ chế sau:

| Registry/platform | Nguồn định danh instance | Metadata vùng triển khai |
|---|---|---|
| Eureka | `eureka.instance.instance-id`, app name | `eureka.instance.metadata-map` có thể mang `region`, `zone` hoặc nhãn vận hành |
| Consul | Service ID và service instance ID khi đăng ký | Service metadata/tags có thể mang region, zone, environment |
| Kubernetes | Pod UID/name, namespace, Pod IP | Pod labels/annotations hoặc node topology labels; zone thường cần được inject/đọc từ Node |

Ví dụ Eureka:

```yaml
spring:
  application:
    name: payment-service

eureka:
  instance:
    instance-id: ${INSTANCE_ID:${HOSTNAME:local}}
    metadata-map:
      region: ${DEPLOYMENT_REGION:unknown}
      zone: ${DEPLOYMENT_ZONE:unknown}
      environment: ${DEPLOYMENT_ENV:local}
```

Nếu ứng dụng ghi `zone=ap-southeast-1a` trong log nhưng registry ghi `zone=ap-southeast-1b`, công cụ vận hành sẽ đưa ra kết luận sai khi điều tra. Nên dùng một nguồn cấu hình duy nhất hoặc kiểm tra sự nhất quán giữa environment, registry metadata và log resource attributes khi startup.

Metadata registry phục vụ discovery/routing; log resource attributes phục vụ truy vấn observability. Chúng có thể dùng cùng giá trị nhưng không nên giả định một bên tự động cập nhật bên kia.

## 11. Ghi nhận service đích trong log outbound

Khi một service gọi service khác, log nên phân biệt identity của caller và destination:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.ServiceInstance;

public class OutboundCallLogger {

    private static final Logger log =
            LoggerFactory.getLogger(OutboundCallLogger.class);

    public void logSelectedInstance(ServiceInstance target) {
        String destinationZone = target.getMetadata() == null
                ? "unknown"
                : target.getMetadata().getOrDefault("zone", "unknown");

        log.info(
                "Calling dependency destinationServiceId={} destinationInstanceId={} destinationHost={} destinationPort={} destinationZone={}",
                target.getServiceId(),
                target.getInstanceId(),
                target.getHost(),
                target.getPort(),
                destinationZone
        );
    }
}
```

Đây là ví dụ khi code đã có `ServiceInstance` được chọn. Nếu dùng Spring Cloud LoadBalancer, có thể tích hợp tại tầng client/lifecycle phù hợp để ghi instance thực sự được chọn; không log toàn bộ danh sách instance rồi coi phần tử đầu là destination. Nếu metadata không có `zone`, ghi `unknown` hoặc bỏ field thay vì suy luận từ hostname.

Trong schema log, caller giữ các trường `serviceId`, `instanceId`, `region`, `zone`; destination dùng `destinationServiceId`, `destinationInstanceId`, `destinationHost`, `destinationPort`, `destinationZone`. Cách đặt tên này giúp truy vấn không nhầm nơi tạo log với nơi nhận request.

## 12. Truy vấn log trong quá trình điều tra

Khi log được xuất dưới dạng JSON và collector parse field riêng, có thể lọc theo nhiều chiều:

| Câu hỏi | Điều kiện lọc gợi ý |
|---|---|
| Tất cả log của một service | `serviceId = "payment-service"` |
| Chỉ một instance bị lỗi | `serviceId = "payment-service" AND instanceId = "payment-service-pod-7f9c8"` |
| Lỗi tập trung ở một zone | `serviceId = "payment-service" AND zone = "ap-southeast-1a" AND level >= WARN` |
| So sánh hai region | `serviceId = "payment-service" AND region IN ("ap-southeast-1", "ap-southeast-2")` |
| Theo một request phân tán | `traceId = "4bf92f3577b34da6a3ce929d0e0e4736"` |
| Theo service đích | `destinationServiceId = "inventory-service" AND level >= WARN` |

Cú pháp thực tế phụ thuộc Elasticsearch, Loki, OpenSearch, Splunk hoặc hệ thống log đang dùng. Điều quan trọng là các trường phải được parse thành thuộc tính riêng và tên trường nhất quán giữa service.

### 12.1. Cardinality và chi phí

`instanceId`, `podName` và `traceId` có số lượng giá trị lớn. Chúng phù hợp để lọc log và trace, nhưng không nên mặc định đưa tất cả thành label/tag của metric. Metric label có cardinality cao có thể làm tăng mạnh số time series, bộ nhớ và chi phí lưu trữ.

Với metrics, thường dùng `serviceId`, `region`, `zone` và `environment` nếu số lượng giá trị được kiểm soát. Chỉ thêm `instanceId` khi backend và quy mô hệ thống cho phép. Trace ID và request ID không nên là metric label.

## 13. Bảo mật và chất lượng dữ liệu log

- Không ghi token, password, cookie, authorization header hoặc dữ liệu cá nhân không cần thiết.
- Không cho caller tự quyết định `serviceId`, `instanceId`, `region` hoặc `zone` của process bằng request header.
- Validate `X-Request-ID` nếu chấp nhận từ bên ngoài; giới hạn độ dài và ký tự để tránh log injection.
- Escape newline và ký tự điều khiển khi ghi log dạng text; JSON encoder nên serialize message an toàn.
- Dùng `unknown` hoặc bỏ field khi metadata chưa có; không tạo giá trị giả như một zone cụ thể.
- Đồng bộ clock của các node bằng NTP/chrony để timestamp giữa instance có thể so sánh được.
- Giới hạn quyền đọc log và thời gian lưu trữ theo chính sách dữ liệu của tổ chức.

## 14. Checklist triển khai

- [ ] `serviceId` lấy từ tên ứng dụng thống nhất với registry.
- [ ] `instanceId` duy nhất giữa các instance chạy đồng thời.
- [ ] `region`, `zone`, `namespace`, `environment` có nguồn cấu hình rõ ràng.
- [ ] Với Kubernetes, inject Pod UID/name/namespace bằng Downward API; không giả định Downward API tự đọc node zone label.
- [ ] Gắn các trường identity vào MDC hoặc logging resource context.
- [ ] Xóa MDC trong `finally` ở Servlet filter.
- [ ] Cấu hình JSON logging để collector parse field riêng.
- [ ] Giữ `traceId`/`spanId` do tracing instrumentation quản lý.
- [ ] Kiểm tra context propagation cho `@Async`, executor và WebFlux.
- [ ] Đồng bộ identity giữa log, Eureka/Consul metadata và Kubernetes labels.
- [ ] Phân biệt caller identity với `destination*` trong log outbound.
- [ ] Không dùng `instanceId`, `traceId` làm metric labels nếu gây cardinality cao.
- [ ] Không ghi secret hoặc dữ liệu nhạy cảm vào log/metadata.

## 15. Kết luận

Để liên kết log với service discovery, mỗi log record nên mang định danh ổn định của service tạo log (`serviceId`), instance cụ thể (`instanceId`) và vị trí triển khai (`region`, `zone`). Trong Spring Boot, có thể lấy service ID từ `spring.application.name`, lấy instance ID và topology từ cấu hình/runtime, rồi đưa chúng vào MDC hoặc logging resource context để mọi log đều có cùng schema.

Hãy giữ trace ID/span ID riêng để liên kết request xuyên service, phân biệt caller với destination trong log outbound, truyền context đúng qua async/WebFlux và đồng bộ giá trị với metadata của registry. Khi log được cấu trúc tốt, đội vận hành có thể lọc lỗi theo service, instance, zone hoặc trace mà không phải suy đoán từ hostname hay nội dung message.

## Tài liệu tham khảo

- [Spring Boot – Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Framework – Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [OpenTelemetry – Service Resource Attributes](https://opentelemetry.io/docs/specs/semconv/resource/service/)
- [Kubernetes – Downward API](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/)
- [Kubernetes – Well-known Labels, Annotations and Taints](https://kubernetes.io/docs/reference/labels-annotations-taints/)
