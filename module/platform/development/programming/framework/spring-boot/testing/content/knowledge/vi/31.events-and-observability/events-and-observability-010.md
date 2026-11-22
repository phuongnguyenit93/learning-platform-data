# Health indicator, Actuator endpoint và chính sách truy cập trong Spring Boot

**Spring Boot Actuator** giúp ứng dụng trả lời các câu hỏi vận hành: **ứng dụng có khỏe không**, **điều kiện nào khiến health xuống DOWN**, **endpoint giám sát có hiện diện và được expose không**, **ai được truy cập endpoint**, và **người xem được nhìn thấy bao nhiêu chi tiết**. Khi kiểm thử, đừng nhầm những khái niệm này:

- **HealthIndicator** là **nguồn dữ liệu** đóng góp trạng thái cho `HealthEndpoint`. Health indicator không tự là URL riêng biệt hoặc một rule bảo mật.
- **Actuator endpoint** là một điểm quan sát/điều khiển được Boot đăng ký, ví dụ `health`, `info` hoặc một `@Endpoint(id="snapshot")` tự viết. Endpoint có thể được mở qua HTTP/JMX nếu được phép và được expose.
- **Access policy** của Boot 3.5 (`management.endpoint.<id>.access`) quyết định endpoint/operation có được phép tồn tại, ở mức `none`, `read-only` hoặc `unrestricted`; đây **không phải** user role.
- **Exposure policy** (`management.endpoints.web.exposure.include/exclude`) quyết định endpoint nào được **định tuyến qua HTTP**; mở exposure không đồng nghĩa mọi người được truy cập.
- **HTTP authorization** do Spring Security `SecurityFilterChain` thực hiện, ví dụ health công khai nhưng snapshot yêu cầu role `OPS`.
- **Health detail visibility** (`management.endpoint.health.show-details`/`show-components`/`roles`) quyết định có lộ thành phần/metadata sức khỏe không, **khác** việc có được gọi URL hay không.
- **Health status mapping** đổi `UP`/`DOWN`/`OUT_OF_SERVICE` sang mã HTTP tương ứng. Một `503` của health có thể cho thấy tình trạng hệ thống, **không nhất thiết là 403/401 do bảo mật**.

Bài thuộc nhóm **Sự kiện và observability** của **Spring Boot - testing** và tập trung vào chủ đề **“Health indicator, Actuator endpoint và chính sách truy cập”**. Nội dung có mô hình, bảng quyết định, lỗi thường gặp, security hardening, health groups/liveness/readiness và một dự án Maven **Java 17 + Spring Boot 3.5.0 + Spring Security 6.5 + JUnit Jupiter**, dùng `MockMvc` và HTTP Basic demo để kiểm chính xác **20 test methods**: indicator UP/DOWN, aggregate 200/503, public health redaction, OPS details, 401/403, custom endpoint, endpoint không expose, endpoint access=none, ứng dụng vẫn được bảo vệ và điều kiện Spring context.

> **Ranh giới chứng minh:** `MockMvc` nạp Spring MVC/Actuator/Security thật trong application context nhưng **không chạy TCP listener thật**; đủ để kiểm mappings/filter/status/JSON trong cùng servlet context. Nếu management port tách riêng hoặc có reverse proxy/TLS/NetworkPolicy, phải bổ sung HTTP integration/E2E tests.

## 1. Lớp quan sát: indicator → health endpoint → HTTP → Security

```text
QueueState (simulated dependency state)
         |
         v
QueueHealthIndicator implements HealthIndicator
         |
         +--- health() -> Health.up().withDetail(...)
         |             hoặc Health.down().withDetail(...)
         |
         v
HealthContributorRegistry / HealthEndpoint
         |
         +--- StatusAggregator -> overall UP/DOWN/OUT_OF_SERVICE...
         |
         v
HealthEndpointWebExtension  -- HTTP status mapping
         |
         +--- 200 nếu UP (mặc định)
         +--- 503 nếu DOWN/OUT_OF_SERVICE (mặc định)
         |
         v
/actuator/health (HTTP route chỉ khi có exposure)
         |
         +--- Boot endpoint access: none/read-only/unrestricted
         +--- management.endpoints.web.exposure.include/exclude
         +--- SecurityFilterChain: permitAll hoặc require role
         +--- show-details / show-components / health.roles
         |
         v
Client nhận { "status": "UP" } (public)
     hoặc { "status": "UP", "components": {...} } (OPS)
```

**Không đảo quan hệ nhân quả:** một HealthIndicator trả `DOWN` không có nghĩa Spring Security ngăn endpoint. Nếu security cho phép và endpoint mapping còn hoạt động, HTTP health thường trả **503 Service Unavailable** kèm trạng thái `DOWN`. Ngược lại, một response `401`/`403` có thể xuất hiện trước khi health operation chạy, không chứng minh hệ thống đã DOWN.

### 1.1. HealthIndicator là interface, không phải controller

Spring Boot cung cấp:

```java
public interface HealthIndicator extends HealthContributor {
    Health health();
}
```

Đây là giản lược đúng chữ ký chính; implementation thực kế thừa default method `getHealth(boolean)`. Một indicator có thể tạo:

```java
return Health.up()
        .withDetail("queueDepth", 0)
        .build();
```

Hoặc:

```java
return Health.down()
        .withDetail("reason", "dependency-offline")
        .build();
```

Khi đăng ký Spring bean tên `queueHealthIndicator`, Boot thường suy ra contribution name **`queue`** bằng cách bỏ hậu tố `HealthIndicator`. Vì vậy cấu trúc JSON aggregate có thể chứa `components.queue` khi detail/components được cho phép. Nếu muốn kiểm đúng tên contributor, test phải xác nhận `components.queue`, không giả định tên Java class tự động là URL `/actuator/QueueHealthIndicator`.

### 1.2. Còn HealthContributor và ReactiveHealthIndicator?

- `HealthContributor` là abstraction cho các thành phần đóng góp health; một contributor có thể là indicator đơn hoặc composite.
- `CompositeHealthContributor` chứa nhiều contributors con, ví dụ health của nhiều datasource/tenant.
- `ReactiveHealthIndicator` trả reactive outcome, dùng trong ứng dụng reactive; Spring Boot có reactive health endpoint/registries tương ứng.
- Nếu cần tích hợp API chậm, indicator phải có timeout/chính sách xử lý failure phù hợp. Health check tắc nghẽn có thể làm chính endpoint kiểm sức khỏe trở thành nguồn tải mới.

**Health không phải báo cáo exception bí mật**: đừng gắn thông tin user token, password, JDBC connection string, IP nội bộ nhạy cảm hay stack trace chi tiết vào `withDetail(...)`, nhất là khi cấu hình `show-details=always`.

## 2. Ba lớp chính sách dễ nhầm: access, exposure và authorization

Spring Boot 3.5 có các properties riêng:

| Lớp | Ví dụ | Đặt câu hỏi | Điều không có nghĩa |
|---|---|---|---|
| Endpoint access | `management.endpoint.snapshot.access=read-only` | Endpoint/operation được **cho phép** trong ứng dụng? | Không xác định user role |
| Max access cap | `management.endpoints.access.max-permitted=read-only` | Có giới hạn chung chặt hơn không? | Không phải HTTP Basic/auth token |
| Default access | `management.endpoints.access.default=none` | Endpoint nào không opt-in sẽ bị loại? | Không thể mở lại bằng permitAll nếu đã bị loại |
| Web exposure | `management.endpoints.web.exposure.include=health,snapshot` | Endpoint nào có mapping HTTP? | Không tự cho anonymous truy cập |
| Web exclude | `management.endpoints.web.exposure.exclude=env` | Endpoint nào bị loại khỏi HTTP bất kể include? | Không tự tắt JMX access |
| Authorization | `EndpointRequest.to("health").permitAll()` | Caller nào qua được SecurityFilterChain? | Không làm endpoint vốn access=none xuất hiện |
| Health details | `show-details=when-authorized`, `roles=OPS` | Caller nhìn thấy chi tiết indicator? | Không giống quyền truy cập URL health |
| HTTP status | `DOWN -> 503` | Tình trạng sức khỏe được ánh xạ ra sao? | Không phải denial 403 |

### 2.1. Endpoint bị vô hiệu khác endpoint không expose

Với cấu hình:

```properties
management.endpoints.access.default=none
management.endpoint.health.access=read-only
management.endpoint.snapshot.access=read-only
management.endpoints.web.exposure.include=health,snapshot
```

Chỉ `health` và `snapshot` được opt-in và expose qua HTTP. Trong Spring Boot 3.5, endpoint access `none` làm endpoint **không có operation khả dụng trong application context** theo cơ chế Actuator; không thể cấp role OPS để khiến nó xuất hiện qua HTTP. Chỉ chỉnh `include` không đủ nếu endpoint đã bị access policy loại bỏ.

Ngược lại, endpoint có thể vẫn hiện diện nội bộ/JMX nhưng **không được expose HTTP**. Ví dụ `info` không nằm trong `include`, nên truy vấn `GET /actuator/info` bằng account đủ quyền vẫn **không có HTTP mapping**, thường dẫn đến **404** khi security cho request đi qua. Để test chính xác nguyên nhân 404, phải kiểm cả access, exposure và context path, không suy ngay rằng URL sai.

### 2.2. `read-only` khác `unrestricted`

Boot 3.5:
- `none`: không cho endpoint khả dụng.
- `read-only`: chỉ cho **read operations**; với `@Endpoint` là các method `@ReadOperation`.
- `unrestricted`: cho phép mọi operation mà endpoint hỗ trợ (read/write/delete), nhưng **Spring Security/CSRF/network policy vẫn có thể chặn HTTP request**.
- `management.endpoints.access.max-permitted` áp giới hạn toàn ứng dụng và **ưu tiên hơn** default/individual access level. Nếu cap bằng `read-only`, một endpoint riêng đặt `unrestricted` cũng không được cấp write.

**Không suy “read-only” từ HTTP GET trong controller nghiệp vụ thông thường**. Với Actuator annotations, operation type được xác định qua `@ReadOperation`, `@WriteOperation`, `@DeleteOperation`; tương ứng HTTP GET, POST, DELETE theo convention, còn một số controller/servlet endpoint types có tiêu chí read khác. Một endpoint không có write operation thì không thể test “write bị chặn” bằng cách gọi một method vốn chưa được khai báo.

### 2.3. Web exposure không thay thế Spring Security

Theo mặc định, chỉ `health` được expose qua HTTP/JMX. Các endpoint như `env`, `beans`, `configprops`, `loggers`, `heapdump`, `threaddump` hoặc `mappings` có thể bộc lộ thông tin nhạy cảm hoặc khả năng thay đổi cấu hình. **Không đặt**:

```properties
management.endpoints.web.exposure.include=*
```

cho internet-facing service chỉ vì debug cho tiện. Nếu phải expose thêm, dùng allowlist theo nhu cầu; kiểm authentication, roles, network firewall/ingress, TLS, secrets sanitization và audit. Một endpoint có JSON values được sanitize theo default cũng không đủ lý do để công khai toàn bộ cấu trúc của app.

### 2.4. Custom SecurityFilterChain khiến auto-security của Boot back off

Khi Spring Security có trên classpath và **không có** user-defined `SecurityFilterChain`, Boot thường tự bảo vệ những Actuator endpoints khác health. **Nhưng khi bạn khai báo bất kỳ custom `SecurityFilterChain` nào, auto-security policy đó back off**. Lúc đó **chính bạn phải bảo vệ cả actuator lẫn application**.

Một lỗi có thật:

```java
@Bean
SecurityFilterChain unsafe(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(a -> a
            .anyRequest().permitAll());
    return http.build();
}
```

Snippet trên có thể vô tình **mở tất cả các endpoint đã expose** cùng business paths. Không áp dụng vào production. Trong ví dụ runnable, ta đặt thứ tự rule rõ:
1. health public;
2. mọi Actuator endpoints còn lại yêu cầu `ROLE_OPS`;
3. các application paths ngoài Actuator vẫn yêu cầu authenticated user.

Spring Boot cung cấp `EndpointRequest.to("health")` và `EndpointRequest.toAnyEndpoint()` để matcher **theo endpoint và base path thực**, giảm rủi ro hardcode `/actuator/**` khi app đổi management base path. `EndpointRequest.to("health")` cũng match **subpaths** của health. Với nhiều `SecurityFilterChain` và `@Order`, phải kiểm filter chain nào thắng trước; securityMatcher được áp dụng ở mức chain, requestMatcher ở mức authorization bên trong chain.

## 3. Health status và HTTP response: test hai tầng

Health API có các statuses thường gặp:

| Status | Ý nghĩa tham khảo | HTTP mặc định |
|---|---|---|
| `UP` | Contributor hoặc aggregate được coi là khỏe | **200** |
| `DOWN` | Không khỏe | **503** |
| `OUT_OF_SERVICE` | Không sẵn sàng phục vụ | **503** |
| `UNKNOWN` | Không xác định | Thường **200** khi không được map khác |

Boot có `StatusAggregator` và `HttpCodeStatusMapper`. Aggregate lấy nhiều contributors và chọn overall status theo thứ tự ưu tiên; default thường `DOWN`/`OUT_OF_SERVICE` nghiêm trọng hơn `UP`. Cấu hình:
- `management.endpoint.health.status.order` có thể đổi độ ưu tiên custom statuses.
- `management.endpoint.health.status.http-mapping.*` có thể đổi code HTTP.
- Khi khai báo **custom HTTP mappings**, cần chú ý: mặc định mapping cho `DOWN` và `OUT_OF_SERVICE` có thể **không còn được áp dụng**; muốn giữ 503 thì cấu hình lại cả hai cùng custom mapping.

Ví dụ:

```properties
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.status.http-mapping.out-of-service=503
management.endpoint.health.status.http-mapping.fatal=500
```

Đây là **ví dụ chính sách**, không đặt trong runnable demo. Kỳ vọng `DOWN -> 503` của tests dựa trên **default HTTP mapping**, không phụ thuộc custom status codes.

**Đừng chỉ test JSON status:** Khi indicator trả `DOWN`, body có thể có `"status":"DOWN"` nhưng HTTP mapping sai, khiến load balancer/kubelet hiểu 200 là khỏe. Test nên kiểm **cả code HTTP và body**. Cũng đừng assert mọi lỗi HTTP 503 là Health DOWN: reverse proxy hoặc app gateway có thể trả 503 trước khi request tới Actuator.

## 4. Quyền xem details không phải quyền truy cập URL

Health endpoint trả lời được anonymous nếu policy public, nhưng nội dung có thể bị ẩn:

```http
GET /actuator/health HTTP/1.1

HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
```

Với caller được health roles cho phép:

```json
{
  "status": "UP",
  "components": {
    "queue": {
      "status": "UP",
      "details": {
        "mode": "ready"
      }
    }
  }
}
```

Đây là **shape minh họa rút gọn** (aggregate thực có thể có các contributor khác như diskSpace/ping). Header Content-Type có thể khác nếu content negotiation/Actuator API version thay đổi; test không nên hardcode vendor media type nếu không phải contract.

### 4.1. Cấu hình show-details và show-components

```properties
management.endpoint.health.show-details=when-authorized
management.endpoint.health.show-components=when-authorized
management.endpoint.health.roles=OPS
```

Các giá trị `show-details` và `show-components` có thể là:
- `never`: không hiển thị.
- `when-authorized`: chỉ hiển thị cho caller đã authenticated và có role phù hợp.
- `always`: hiển thị cho mọi caller **được phép gọi endpoint**.

Nếu không cấu hình `roles`, mặc định các authenticated users có thể được coi là authorized để xem details khi bật `when-authorized`. Vì vậy trong service có nhiều vai trò người dùng (customer, staff, operator), **đặt roles cụ thể**, tránh để mọi người đã đăng nhập xem thông tin hạ tầng.

**Hai điều kiện phải đồng thời đúng để OPS thấy details:**
1. HTTP security cho caller vào `/actuator/health` (ở demo là `permitAll`).
2. Health detail authorization thấy caller thuộc `OPS`, theo `management.endpoint.health.roles=OPS`.

Nếu `show-details=always`, người không đăng nhập vẫn có thể thấy cấu trúc/metadata của dependencies nếu health public. Không nên expose hostname, queue name, disk paths hoặc lỗi kết nối chi tiết cho internet.

### 4.2. Có thể public status nhưng che components

Trong demo:
- Anonymous `GET /actuator/health` được **200** với `{"status":"UP"}`, không thấy `components`.
- User role `USER` được **200** nhưng vẫn không thấy `components`.
- User role `OPS` được **200** và thấy `components.queue.details.mode`.
- Khi queue xuống, anonymous thấy **503** và `"status":"DOWN"` nhưng vẫn không thấy details.
- OPS thấy **503**, body có `components.queue.status=DOWN` và `reason/mode` được phép hiển thị.

**Sự tách biệt này rất quan trọng:** health status public cho load balancer/kubelet không nhất thiết phải public chi tiết hệ thống. Một test chỉ assert `status().isOk()` chưa chứng minh **không lộ data**; kiểm thêm `jsonPath("$.components").doesNotExist()`.

## 5. Health groups, liveness/readiness và management port

Health endpoint có thể phân nhóm indicators theo mục đích. Ví dụ readiness phụ thuộc DB/queue, còn liveness không nên phụ thuộc vào sự khỏe của các dịch vụ ngoài.

### 5.1. Liveness và readiness khác nhau

- **Liveness**: tiến trình có còn đủ khỏe để tiếp tục chạy? Nếu fail, orchestrator có thể **restart** pod.
- **Readiness**: instance có **sẵn sàng nhận lưu lượng** không? Nếu fail, orchestrator có thể tạm ngừng route traffic.
- **Startup probe**: có thể hữu ích khi startup dài để tránh liveness checks giết tiến trình quá sớm.

Nếu database hoặc API bên ngoài DOWN, thường **không** nên đưa chúng vào liveness: restart hàng loạt pods không sửa dependency ngoài và có thể tạo cascading failures. Tùy hệ thống, chúng có thể ảnh hưởng readiness; phải cân nhắc partial functionality và degrade modes.

Trong Kubernetes, Boot hỗ trợ `livenessState` và `readinessState` health indicators; groups có thể truy cập:
- `/actuator/health/liveness`
- `/actuator/health/readiness`

Ở các môi trường **không phải Kubernetes**, có thể bật rõ:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

Khi bật additional paths, Boot có thể expose `/livez` và `/readyz` **trên main application server port**, giúp kiểm thực tế connector ứng dụng. **Đây là cấu hình tham khảo, không đặt trong file properties của runnable demo** để tránh làm thay đổi số contributors/endpoint paths cần assert.

### 5.2. Management port khác application port

`management.server.port=9091` có thể mở một management web context/port riêng. Khi đó:
- `MockMvc` tại main servlet context **không tự kiểm toàn bộ đường HTTP của management port riêng**.
- `server.port` khác `management.server.port`; network ingress, TLS và firewall có thể khác.
- Kubelet probe trên management port riêng có thể vẫn khỏe khi **main app port không chấp nhận requests**.
- Cần test `@SpringBootTest(webEnvironment=RANDOM_PORT)`, lấy port phù hợp và gọi HTTP thật tới từng port, cùng security/cookie/mTLS requirements.
- Nếu mục tiêu là kubelet nhận ra main connector hỏng, cân nhắc additional paths trên main port theo tài liệu Boot.

### 5.3. Tạo health group riêng

Ví dụ:

```properties
management.endpoint.health.group.queueOnly.include=queue
management.endpoint.health.group.queueOnly.show-details=when-authorized
management.endpoint.health.group.queueOnly.roles=OPS
```

Đây là snippet khái niệm; group name thực tế và contributor name phải khớp với registry, và cần test Spring Boot version/binding cụ thể. Boot mặc định validate group membership, nhóm chứa indicator không tồn tại có thể làm context **khởi động lỗi**; kiểm `management.endpoint.health.validate-group-membership` khi gặp trường hợp này. Một custom group phải được thiết kế không tiết lộ thông tin ngoài mục tiêu. Không sử dụng nhóm duy nhất chứa DB/queue làm liveness nếu dependency outside có thể DOWN.

## 6. Dự án runnable Java 17 + Spring Boot 3.5: HealthIndicator, @Endpoint và security

Dự án cung cấp:
1. Một `QueueState` giả lập dependency, ban đầu healthy, có thể chuyển DOWN một cách deterministic.
2. Một `QueueHealthIndicator` trả `UP`/`DOWN` kèm details, contributor ID là `queue`.
3. Một endpoint tự viết `@Endpoint(id="snapshot")` có `@ReadOperation` trả JSON không chứa secrets.
4. `SecurityFilterChain` để health public, các Actuator endpoints khác yêu cầu role `OPS`, app business routes yêu cầu authenticated.
5. In-memory users chỉ phục vụ demo; real production dùng credential store/OIDC/mTLS.
6. Thuộc tính Actuator cho access/exposure/detail visibility.
7. Ba test classes: **3 pure unit tests**, **15 MockMvc integration tests**, **2 access-policy integration tests**. Tổng **20 `@Test`**.

### 6.1. Cây thư mục

```text
actuator-health-security/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/actuatordemo/
    │   │   ├── ActuatorDemoApplication.java
    │   │   ├── QueueState.java
    │   │   ├── QueueHealthIndicator.java
    │   │   ├── OpsSnapshotEndpoint.java
    │   │   ├── ActuatorSecurityConfig.java
    │   │   └── PrivateController.java
    │   └── resources/
    │       └── application.properties
    └── test/java/com/example/actuatordemo/
        ├── QueueHealthIndicatorTest.java
        ├── ActuatorAccessTest.java
        └── ActuatorDisabledTest.java
```

Không có service thật bên ngoài, không cần database, Redis, Kafka hoặc Testcontainers. Mọi data là demo giả. Khi đưa HealthIndicator vào production, thay `QueueState` bằng kiểm tra trạng thái thật có timeout, caching/bulkhead phù hợp.

### 6.2. POM Maven

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>actuator-health-security</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Boot 3.5 BOM giữ versions của Spring MVC/Security/Actuator/Mockito/JUnit tương thích. `spring-security-test` cung cấp `httpBasic(...)` trong `MockMvc`. Dùng imports `org.springframework.boot.actuate.*` đúng dòng Boot 3.5; không copy đường package mới của Boot 4 vào project này.

### 6.3. Main application

File **`src/main/java/com/example/actuatordemo/ActuatorDemoApplication.java`**:

```java
package com.example.actuatordemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorDemoApplication.class, args);
    }
}
```

Mọi component cùng package hoặc subpackages nên Spring scan tìm thấy HealthIndicator, custom endpoint, security config và controller. Không yêu cầu chạy main trong JUnit; context sẽ được `@SpringBootTest` khởi tạo.

### 6.4. State giả lập dependency

File **`src/main/java/com/example/actuatordemo/QueueState.java`**:

```java
package com.example.actuatordemo;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class QueueState {

    private final AtomicBoolean available =
            new AtomicBoolean(true);

    public boolean isAvailable() {
        return available.get();
    }

    public void setAvailable(boolean value) {
        available.set(value);
    }
}
```

Đây là test-friendly fake state: thay đổi `available` không cần sleep hoặc kết nối thật. Lớp này **không phải phép kiểm health production**. Test dùng singleton state chỉ chạy JUnit **tuần tự mặc định**; nếu bật parallel tests hoặc share cached context qua nhiều classes, phải cô lập state hoặc dùng per-test context/unique fixtures để không có race.

### 6.5. Custom HealthIndicator

File **`src/main/java/com/example/actuatordemo/QueueHealthIndicator.java`**:

```java
package com.example.actuatordemo;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("queueHealthIndicator")
public class QueueHealthIndicator implements HealthIndicator {

    private final QueueState state;

    public QueueHealthIndicator(QueueState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        if (state.isAvailable()) {
            return Health.up()
                    .withDetail("mode", "ready")
                    .build();
        }
        return Health.down()
                .withDetail("mode", "offline")
                .build();
    }
}
```

Actuator sẽ đưa contributor này vào aggregate health với ID `queue` theo convention tên bean. Giữ `mode` là giá trị mô phỏng **không nhạy cảm**; đừng đưa internal hostnames hoặc credentials vào details. Với dependency thật, timeout/network exception có thể được chuyển thành health DOWN theo policy; tránh bất kỳ health indicator nào block vô hạn làm probe bị timeout.

### 6.6. Custom Actuator endpoint có read operation

File **`src/main/java/com/example/actuatordemo/OpsSnapshotEndpoint.java`**:

```java
package com.example.actuatordemo;

import java.util.Map;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "snapshot")
public class OpsSnapshotEndpoint {

    @ReadOperation
    public Map<String, String> snapshot() {
        return Map.of(
                "kind", "operations",
                "mode", "demo");
    }
}
```

`@Endpoint(id="snapshot")` tạo endpoint ID, và `@ReadOperation` có thể map sang `GET /actuator/snapshot` khi **access + exposure** đều cho phép. Không cần `@RestController` hoặc `@GetMapping` cho class này; Actuator sinh mapping từ operation annotation. Trong demo này chỉ có **read operation**; không có method `@WriteOperation`. Để kiểm chính sách write thực sự, phải thêm write operation có chủ đích trong một test fixture riêng, set access=read-only/unrestricted và xử lý CSRF/security thích hợp.

### 6.7. Cấu hình Spring Security

File **`src/main/java/com/example/actuatordemo/ActuatorSecurityConfig.java`**:

```java
package com.example.actuatordemo;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                // Health public, kể cả health subpaths.
                .requestMatchers(
                        EndpointRequest.to("health")).permitAll()

                // Mọi Actuator endpoint còn lại phải có role OPS.
                .requestMatchers(
                        EndpointRequest.toAnyEndpoint()).hasRole("OPS")

                // Không vô tình mở các business endpoints.
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    UserDetailsService demoUsers() {
        return new InMemoryUserDetailsManager(
                User.withUsername("operator")
                        .password("{noop}ops-password")
                        .roles("OPS")
                        .build(),
                User.withUsername("reader")
                        .password("{noop}reader-password")
                        .roles("USER")
                        .build());
    }
}
```

**Chỉ cho mục đích học/test:** mật khẩu trong source với `{noop}` là hoàn toàn **không an toàn cho production**. Khi triển khai thật, dùng password encoder phù hợp hoặc OAuth2/OIDC/mTLS, secret manager và least privilege. Không copy demo credentials vào hệ thật.

Thứ tự matchers có ý nghĩa: health được permit trước, sau đó mọi Actuator endpoints còn lại cần `ROLE_OPS`, business routes khác cần authenticated. Vì ta tự khai báo `SecurityFilterChain`, **Boot actuator security auto-config sẽ back off**; chính class này chịu trách nhiệm bảo vệ Actuator và ứng dụng.

**Không tắt CSRF toàn cục.** Bài chỉ dùng GET/read operations, nên test có thể giữ mặc định. Nếu thêm `@WriteOperation` qua POST/DELETE và gọi bằng browser cookie/session, cần kiểm CSRF token. Một request POST trả 403 có thể do **thiếu CSRF**, không phải role OPS; cần test hai điều kiện riêng. Với non-browser machine-only clients, việc bỏ CSRF phải theo threat model thực, không chỉ vì gọi endpoint quản trị.

### 6.8. Một API nghiệp vụ để kiểm default deny

File **`src/main/java/com/example/actuatordemo/PrivateController.java`**:

```java
package com.example.actuatordemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PrivateController {

    @GetMapping("/api/private/ping")
    public Map<String, String> ping() {
        return Map.of("reply", "pong");
    }
}
```

Endpoint này **không thuộc Actuator**. Việc thêm custom `SecurityFilterChain` không được mở vô tình `/api/private/ping` cho anonymous; test sẽ kiểm **401 khi không có credentials**, **200 khi role USER đăng nhập**. Trong production, mỗi business route nên có authorization cụ thể theo dữ liệu/quyền, không chỉ authenticated như demo.

### 6.9. Actuator properties

File **`src/main/resources/application.properties`**:

```properties
# Mặc định KHÔNG cấp access cho các Actuator endpoints.
management.endpoints.access.default=none

# Chỉ opt-in 2 endpoint cần thiết, chỉ cho phép read operations.
management.endpoint.health.access=read-only
management.endpoint.snapshot.access=read-only

# Expose qua HTTP đúng allowlist. Không expose info/env/beans.
management.endpoints.web.exposure.include=health,snapshot

# Public chỉ thấy status; role OPS thấy components và details.
management.endpoint.health.show-details=when-authorized
management.endpoint.health.show-components=when-authorized
management.endpoint.health.roles=OPS

# Giữ management endpoint ở cùng servlet context/port cho MockMvc.
# Không set management.server.port ở ví dụ này.
```

Trong Boot 3.5, `access.default=none` ngăn những endpoints khác được tạo/đưa vào context dưới cơ chế Actuator, còn `include` chọn endpoint được route qua HTTP. Cấu hình này **cố ý không expose `info`**, để test OPS nhận **404** ở `/actuator/info` dù có role đủ cao.

**Chỉ cấp role OPS không làm health details bị public:** health URL public vì SecurityFilterChain `permitAll`; việc có nhìn thấy `components` còn tùy `show-details`/`show-components` và `health.roles`. Đây là trọng tâm của test policy.

### 6.10. Pure unit tests cho HealthIndicator: 3 methods

File **`src/test/java/com/example/actuatordemo/QueueHealthIndicatorTest.java`**:

```java
package com.example.actuatordemo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;

import static org.assertj.core.api.Assertions.assertThat;

class QueueHealthIndicatorTest {

    @Test
    void startsHealthyWithNonSensitiveDetail() {
        QueueState state = new QueueState();
        QueueHealthIndicator indicator =
                new QueueHealthIndicator(state);

        Health health = indicator.health();

        assertThat(health.getStatus()).isEqualTo(Status.UP);
        assertThat(health.getDetails())
                .containsEntry("mode", "ready");
    }

    @Test
    void offlineSignalChangesHealthToDown() {
        QueueState state = new QueueState();
        state.setAvailable(false);

        Health health =
                new QueueHealthIndicator(state).health();

        assertThat(health.getStatus()).isEqualTo(Status.DOWN);
        assertThat(health.getDetails())
                .containsEntry("mode", "offline");
    }

    @Test
    void recoveredStateReturnsUpAgain() {
        QueueState state = new QueueState();
        QueueHealthIndicator indicator =
                new QueueHealthIndicator(state);

        state.setAvailable(false);
        assertThat(indicator.health().getStatus())
                .isEqualTo(Status.DOWN);

        state.setAvailable(true);
        assertThat(indicator.health().getStatus())
                .isEqualTo(Status.UP);
    }
}
```

Các unit tests này kiểm **logic của indicator** mà không cần Spring context. Chúng **không** chứng minh bean được Actuator registry nhận, HTTP mapping hay Spring Security policy. Những điều đó thuộc integration tests ở phần tiếp theo.

### 6.11. MockMvc integration tests: 15 methods

File **`src/test/java/com/example/actuatordemo/ActuatorAccessTest.java`**:

```java
package com.example.actuatordemo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.health.Status;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class ActuatorAccessTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private QueueState queueState;

    @Autowired
    private QueueHealthIndicator queueIndicator;

    @Autowired
    private HealthEndpoint healthEndpoint;

    @BeforeEach
    void restoreQueue() {
        queueState.setAvailable(true);
    }

    @Test
    void indicatorBeanIsRegisteredAndInitiallyUp() {
        assertThat(queueIndicator.health().getStatus())
                .isEqualTo(Status.UP);
    }

    @Test
    void aggregateHealthReflectsOfflineContributor() {
        queueState.setAvailable(false);

        assertThat(healthEndpoint.health().getStatus())
                .isEqualTo(Status.DOWN);
    }

    @Test
    void anonymousMayReadStatusWithoutComponents() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components").doesNotExist());
    }

    @Test
    void ordinaryAuthenticatedUserStillCannotSeeDetails()
            throws Exception {

        mvc.perform(get("/actuator/health")
                .with(httpBasic("reader", "reader-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components").doesNotExist());
    }

    @Test
    void operatorSeesQueueHealthStatusAndDetails()
            throws Exception {

        mvc.perform(get("/actuator/health")
                .with(httpBasic("operator", "ops-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components.queue.status")
                        .value("UP"))
                .andExpect(jsonPath("$.components.queue.details.mode")
                        .value("ready"));
    }

    @Test
    void anonymousGets503ButNoSensitiveDetailsWhenDown()
            throws Exception {

        queueState.setAvailable(false);

        mvc.perform(get("/actuator/health"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value("DOWN"))
                .andExpect(jsonPath("$.components").doesNotExist());
    }

    @Test
    void operatorSeesDownContributorDetailsWith503()
            throws Exception {

        queueState.setAvailable(false);

        mvc.perform(get("/actuator/health")
                .with(httpBasic("operator", "ops-password")))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value("DOWN"))
                .andExpect(jsonPath("$.components.queue.status")
                        .value("DOWN"))
                .andExpect(jsonPath("$.components.queue.details.mode")
                        .value("offline"));
    }

    @Test
    void anonymousCannotReadCustomActuatorEndpoint()
            throws Exception {

        mvc.perform(get("/actuator/snapshot"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void readerWithoutOpsRoleGets403OnSnapshot()
            throws Exception {

        mvc.perform(get("/actuator/snapshot")
                .with(httpBasic("reader", "reader-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void operatorGetsCustomActuatorEndpointJson()
            throws Exception {

        mvc.perform(get("/actuator/snapshot")
                .with(httpBasic("operator", "ops-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.kind")
                        .value("operations"))
                .andExpect(jsonPath("$.mode").value("demo"));
    }

    @Test
    void unexposedInfoStillReturns404ForOperator()
            throws Exception {

        mvc.perform(get("/actuator/info")
                .with(httpBasic("operator", "ops-password")))
                .andExpect(status().isNotFound());
    }

    @Test
    void nonActuatorPrivateApiStillRequiresLogin()
            throws Exception {

        mvc.perform(get("/api/private/ping"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryReaderCanCallAuthenticatedBusinessApi()
            throws Exception {

        mvc.perform(get("/api/private/ping")
                .with(httpBasic("reader", "reader-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reply").value("pong"));
    }

    @Test
    void healthSubpathIsAlsoAllowedForOps()
            throws Exception {

        mvc.perform(get("/actuator/health/queue")
                .with(httpBasic("operator", "ops-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.details.mode")
                        .value("ready"));
    }

    @Test
    void anonymousCannotAccessActuatorDiscoveryLinks()
            throws Exception {

        mvc.perform(get("/actuator"))
                .andExpect(status().isUnauthorized());
    }
}
```

**15 test methods** này xác nhận từng lớp:

- HealthIndicator bean tồn tại, overall health cập nhật DOWN.
- `/actuator/health` công khai, nhưng anonymous/USER không thấy `components`.
- OPS thấy contributor `queue` và details; role được xác thực qua **HTTP Basic header thật trong MockMvc security filters**.
- Khi QueueState DOWN, HTTP health phải **503**, không phải 200, và visibility policy vẫn giữ nguyên.
- Custom `@Endpoint(id="snapshot")` trả 401 với anonymous, 403 với USER, 200 + JSON với OPS.
- `/actuator/info` không expose → OPS vẫn thấy 404 (không phải tự động có URL vì có role).
- Business route ngoài Actuator vẫn cần authentication; custom SecurityFilterChain không mở toàn hệ thống.
- `EndpointRequest.to("health")` match cả subpath health/queue; `EndpointRequest.toAnyEndpoint()` bao phủ discovery links `/actuator`.

Chúng không kiểm TCP port hoặc hệ thống reverse proxy. Nhờ `@BeforeEach`, health status được reset thành UP trước mỗi case; mỗi test cố ý đổi DOWN sẽ không làm test sau fail chỉ do dư state. JUnit mặc định chạy tuần tự khi không bật parallel, cần giữ nguyên hoặc cô lập singleton state nếu test suite cấu hình parallel.

### 6.12. Kiểm `access=none` ở context riêng: 2 methods

File **`src/test/java/com/example/actuatordemo/ActuatorDisabledTest.java`**:

```java
package com.example.actuatordemo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = "management.endpoint.snapshot.access=none")
@AutoConfigureMockMvc
class ActuatorDisabledTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void operatorCannotRecoverDisabledEndpointWithRole()
            throws Exception {

        mvc.perform(get("/actuator/snapshot")
                .with(httpBasic("operator", "ops-password")))
                .andExpect(status().isNotFound());
    }

    @Test
    void healthRemainsAvailableWhenSnapshotIsDisabled()
            throws Exception {

        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
```

Dòng `properties = "management.endpoint.snapshot.access=none"` tạo **test context với property override** cho class này; main application.properties vẫn giữ `snapshot.access=read-only`. Cấu hình Boot class/context khác nhau giúp kiểm khác biệt:
- Với `access=read-only` + exposure + role OPS → snapshot endpoint **200**.
- Với `access=none` + exposure vẫn ghi `snapshot` + role OPS → **404**, vì endpoint operation không khả dụng; security role không thể “mở lại” endpoint bị loại.
- Health vẫn **200** nhờ access/exposure riêng.

Không suy rằng tất cả 404 đều do access=none: 404 còn có thể do endpoint chưa được expose, sai base path, wrong management port, controller mapping không tồn tại hoặc reverse proxy. Test này cô lập một biến property để chứng minh nguyên nhân.

### 6.13. Lệnh chạy và kết quả mong đợi

Yêu cầu JDK 17+, Maven. Từ thư mục có `pom.xml`:

```bash
mvn test
```

Chạy từng class:

```bash
mvn -Dtest=QueueHealthIndicatorTest test
mvn -Dtest=ActuatorAccessTest test
mvn -Dtest=ActuatorDisabledTest test
```

Nếu project có Maven Wrapper: `./mvnw test` (Linux/macOS) hoặc `mvnw.cmd test` (Windows).

**Số lượng dự kiến**: 3 pure unit + 15 MockMvc integration + 2 disabled-policy integration = **20 JUnit @Test methods**. Dữ liệu giả, không phụ thuộc Docker/Internet, không có stdout nghiệp vụ bất biến để so khớp. Kỳ vọng tất cả assertions PASS khi chạy với Boot 3.5.0 và security/test configuration mô tả ở trên; **đây là kỳ vọng từ mã nguồn, không phải tuyên bố đã thực thi Maven tại thời điểm biên soạn bài**. Nếu project thật khác dependency/Boot patch/security config, chạy lại trong CI để xác minh.

## 7. Ma trận truy cập: 200/401/403/404/503 mang ý nghĩa khác nhau

| Request / role | Access/exposure | Health/endpoint state | Kỳ vọng |
|---|---|---|---|
| Anonymous GET `/actuator/health` | health read-only + exposed + permitAll | UP | **200**, chỉ `status` |
| Reader USER GET `/actuator/health` | như trên | UP | **200**, không details |
| Operator OPS GET `/actuator/health` | như trên | UP | **200**, có queue details |
| Anonymous GET `/actuator/health` | như trên | DOWN | **503**, chỉ `status` |
| Operator OPS GET `/actuator/health` | như trên | DOWN | **503**, queue DOWN/details |
| Anonymous GET `/actuator/snapshot` | snapshot read-only + exposed | available | **401** (HTTP Basic entry point) |
| Reader USER GET `/actuator/snapshot` | như trên | available | **403** (thiếu OPS role) |
| Operator OPS GET `/actuator/snapshot` | như trên | available | **200**, JSON |
| Operator OPS GET `/actuator/info` | info không exposed | không route | **404** |
| Operator OPS GET `/actuator/snapshot` khi access=none | snapshot bị disabled | không route | **404** |
| Anonymous GET `/api/private/ping` | không phải Actuator | authenticated required | **401** |
| Reader USER GET `/api/private/ping` | không phải Actuator | authenticated | **200** |

**Phân biệt status đúng lớp:**

- `401 Unauthorized`: chưa có authentication phù hợp trong **demo HTTP Basic**. Với form login, có thể redirect `302`; không mặc định mọi app đều trả 401.
- `403 Forbidden`: đã có authentication nhưng không đủ authorization, hoặc một request unsafe thiếu CSRF. 403 **không phải health DOWN**.
- `404 Not Found`: request không có HTTP mapping (chẳng hạn không expose/access none), nhưng cũng có thể đơn giản do path sai; một số cấu hình có thể che endpoint khác đi trước khi trả 404.
- `503 Service Unavailable`: mặc định mapping cho `Health DOWN/OUT_OF_SERVICE`; không thay vì role OPS, cũng có thể tới từ reverse proxy/infra nếu request không tới app.
- `200 OK`: endpoint response thành công, **không chứng minh mọi downstream dependency ổn** nếu indicator không bao phủ nó, không được register, bị exclude khỏi health group hoặc không kiểm đúng lỗi.

**Đừng thay tất cả assertions bằng `status().isOk()`:** health test phải kiểm chi tiết đúng/sai và code phù hợp, security test phải kiểm đúng role, endpoint availability test phải kiểm mapping thực sự có hay không.

## 8. Những lỗi khi đọc endpoint access và exposure

### 8.1. `management.endpoint.health.access=read-only` không phải permitAll

Property này chỉ nói health có read operation khả dụng; nó **không cấp quyền public HTTP**. Nếu Spring Security cho health yêu cầu login, anonymous vẫn 401/302. Ngược lại, `permitAll` không làm một endpoint bị `access=none` xuất hiện.

### 8.2. `management.endpoints.web.exposure.include=health` không cho phép truy cập các endpoint khác

Một operator có token hợp lệ vẫn không thể gọi `/actuator/env` nếu `env` không expose. Nếu cần mở thêm, phải thay cấu hình một cách có kiểm soát, sau đó test authorization/sanitization, không “quét” tất cả endpoints bằng wildcard. Nếu JMX được bật, exposure JMX riêng có thể vẫn khác HTTP; kiểm cả hai công nghệ khi threat model liên quan.

### 8.3. Health details với role quá rộng

`show-details=when-authorized` nhưng **không đặt `management.endpoint.health.roles`** thường khiến mọi authenticated user được xem chi tiết. Trong ứng dụng có user login bình thường, điều đó có thể lộ topology/exception details. Chỉ cấp OPS; giữ public payload tối thiểu.

### 8.4. Cấu hình `show-components=always` nhưng `show-details=never`

Bạn có thể cho thấy tên/status của components nhưng che details. Phân biệt:
- `show-components` điều khiển **cấu trúc contributors**.
- `show-details` điều khiển **metadata trong từng contributor**.
Nếu muốn không lộ topology, đừng để `show-components=always`. Bộ test demo dùng cả hai `when-authorized` và assert anonymous **không có `components`**, OPS thấy cả component và details.

### 8.5. Đổi custom status mapping làm DOWN thành 200

Khi cấu hình HTTP mapping cho một trạng thái tùy biến, Boot có thể không giữ mặc định `DOWN`/`OUT_OF_SERVICE`. Cần khai báo lại nếu mong 503. Một test chỉ kiểm `status=DOWN` mà không kiểm mã HTTP sẽ bỏ sót lỗi rollout/health probe rất lớn.

### 8.6. Indicator không được đặt tên/register đúng

`QueueHealthIndicator` có thể hoạt động khi tự `new` và gọi `health()`, nhưng không chứng minh Spring đã register bean. Test integration phải kiểm `HealthEndpoint` overall status khi state thay đổi, và (khi authorized) kiểm `components.queue` xuất hiện. Nếu custom bean không scan, Spring health mặc định vẫn `UP` và test chỉ xem 200 sẽ xanh giả.

### 8.7. Health check tự gây tải

HealthIndicator gọi đồng bộ API/DB external mà không có timeout có thể:
- khiến kubelet probe bị timeout dù app làm việc chính vẫn tốt;
- tăng tải lên dependency đang lỗi;
- làm mọi pods restart vì cùng kiểm external dependency ở liveness;
- dẫn đến cascading failure.

Đặt timeout ngắn và retry thấp, dùng cached state/backpressure khi phù hợp, phân chia readiness và liveness; log chậm mà không lộ secrets. Boot có property `management.endpoint.health.logging.slow-indicator-threshold` để cảnh báo các chỉ báo sức khỏe chậm.

### 8.8. Custom security chain chỉ match Actuator, bỏ trống phần còn lại

Một mẫu security cấu hình riêng chỉ cho `EndpointRequest.toAnyEndpoint()` có thể khiến **application routes không còn Boot security mặc định** vì custom chain đã làm Boot auto-config back off. Nếu dùng multiple chains, đăng ký **một chain thứ hai cho app**, với `@Order` đúng, và test business URL anonymous bị chặn. Demo tránh lỗi này bằng **một chain có fallback `anyRequest().authenticated()`**.

### 8.9. Health public không có nghĩa public secrets

Ngay cả khi public status chỉ có UP/DOWN, path có thể bị lạm dụng để probe availability và tạo traffic. Cần network rate limiting / load balancer policy phù hợp, không đưa thông tin nội bộ vào response, và có monitoring để phát hiện abuse. Đối với internal-only environments, có thể chỉ expose health qua management VLAN/sidecar, nhưng vẫn kiểm hoạt động ở cổng thực.

## 9. Test production: vượt khỏi MockMvc

Bộ demo kiểm đúng nhiều lớp **trong JVM**. Khi deployment thêm hạ tầng, cần kiểm thêm:

| Hạ tầng | Rủi ro | Test phù hợp |
|---|---|---|
| `management.server.port` riêng | Security/network config khác app port | Real HTTP test cả main và management ports |
| Ingress/reverse proxy | Rewrite base path, auth bypass hoặc không forward headers | E2E với deployment-like proxy |
| Kubernetes readiness/liveness | Probe sai path/port hoặc sai group | Integration with probes + deployment manifests |
| TLS/mTLS | Trust/CA/certificate, client authentication | HTTPS integration với test certificates |
| OAuth2/OIDC | Roles/scopes từ JWT không giống mock BASIC users | Security integration với test JWT/authorization server |
| Database/Redis/Kafka | HealthContributor thực DOWN và readiness | Testcontainers/environment isolated |
| Parallel tests | Singleton QueueState/health mocks bị trộn | Per-test state hoặc disable parallel |
| Separate management context | MockMvc không phản ánh management server child context | RANDOM_PORT + management port HTTP calls |
| Metrics/observations | Health status chưa chắc counter/trace đúng | MeterRegistry/ObservationRegistry tests riêng |
| Slow dependencies | Health probes bị timeouts | Fault injection + time budget/slow indicator threshold |
| High scale | Probe frequency gây tải quá mức | Load tests và rate limiting policy |

### 9.1. Không dùng MockMvc test như bằng chứng network ACL

MockMvc đi qua Spring MVC request handlers + security filters mà không mở socket thật. Một `MockMvc GET /actuator/snapshot` trả 403 chứng minh filter chain **trong context đó** chặn user. Nó **không chứng minh** firewall/ingress đang chặn public Internet, cũng không kiểm misconfigured management port. Nếu endpoint phải chỉ truy cập qua private network, cần deployment/infrastructure test riêng.

### 9.2. Nếu app chuyển sang WebFlux

Ứng dụng reactive dùng `ReactiveHealthIndicator`, `WebTestClient` và `SecurityWebFilterChain`, với matcher reactive `EndpointRequest` tương ứng trong package khác. Đừng copy `HttpSecurity`/`MockMvc` servlet example nguyên xi vào WebFlux. Những khái niệm access/exposure/health detail vẫn có, nhưng runtime/security APIs khác.

### 9.3. Nếu cần kiểm Prometheus endpoint

`/actuator/prometheus` đòi `micrometer-registry-prometheus` trên classpath và phải được **access/expose/security** đúng. `MetricsEndpoint` và `prometheus` không phải cùng ID/operation. Một health endpoint `UP` không bảo đảm Prometheus metrics được scrape; hãy kiểm từng endpoint theo nhiệm vụ vận hành, và không mở registry tùy tiện với Internet.

## 10. Ma trận test nên có trong service thực

| Kiểm thử | Input | Bằng chứng |
|---|---|---|
| Indicator unit UP | Dependency ready | `Health.status=UP`, detail safe |
| Indicator unit DOWN | Dependency offline | `Health.status=DOWN` |
| Aggregate health DOWN | Contributor registered, offline | Overall `HealthEndpoint.health().getStatus()=DOWN` |
| HTTP public healthy | Anonymous GET /actuator/health | 200, status UP, không components/details |
| HTTP public unhealthy | Anonymous GET /actuator/health | 503, status DOWN, không leak details |
| HTTP OPS healthy | Authenticated OPS | 200, components.queue và chi tiết đúng |
| HTTP USER healthy | Authenticated USER | 200, vẫn không có components |
| Custom endpoint no auth | Anonymous GET /actuator/snapshot | 401/redirect theo entry point |
| Custom endpoint wrong role | USER | 403 |
| Custom endpoint correct role | OPS | 200, JSON đúng |
| Not exposed | OPS GET /actuator/info | 404 |
| Access=none | OPS GET /actuator/snapshot với override property | 404 |
| App route non-Actuator | Anonymous GET /api/private/ping | 401 |
| Health subpath | OPS GET /actuator/health/queue | 200, status/details đúng |
| Actuator discovery links | Anonymous GET /actuator | 401 nếu security chain chặn |
| Read-only write operation (nếu có) | OPS POST actuator write endpoint | Không được gọi khi access=read-only; phân biệt CSRF và mapping |
| Probes | /actuator/health/readiness/liveness hoặc /readyz /livez | Đúng group/status/path/port theo deployment |
| Management server port | Remote client tới port riêng | Security/TLS/network policy đúng |
| Indicator timeout | Dependency chậm | Health fails within budget, không treo process |

**Chọn assertion theo contract:** nếu policy yêu cầu health public, test 200/503 và absence of details; nếu policy yêu cầu chỉ private subnet, cần thêm network ACL test. Với status tùy chỉnh, đừng mặc định 503: phải kiểm `HttpCodeStatusMapper` thực sự có mapping tương ứng.

## 11. Câu hỏi tự kiểm

**1. Endpoint đã có `management.endpoint.snapshot.access=read-only`. Anonymous gọi vẫn 401. Vì sao?**

Vì access nói **operation có sẵn**, không cho phép anonymous. SecurityFilterChain yêu cầu role OPS.

**2. OPS vẫn nhận 404 tại `/actuator/info`. Có phải thiếu OPS role không?**

Không nhất thiết: role OPS đã đủ cho Actuator policy, nhưng `info` không thuộc `management.endpoints.web.exposure.include` của demo và không opt-in access. Cần kiểm access/exposure/path, không sửa role bừa bãi.

**3. Anonymous gọi health trả 200 nhưng không thấy `components`. Đó có phải lỗi?**

Không. `show-components=when-authorized` và `roles=OPS` cố ý che thông tin. Kubelet/load balancer có thể chỉ cần status.

**4. Operator gọi health trả 503 với `"status":"DOWN"`. Có nghĩa operator thiếu quyền?**

Không. Operator đã qua security; đó là trạng thái health bị suy giảm và mapping `DOWN -> 503`.

**5. Đặt `management.endpoints.web.exposure.include=*` có bảo vệ endpoint không?**

Không. Nó mở HTTP exposure rộng; cần access policies, Spring Security, firewall/mTLS và kiểm sanitization riêng.

**6. Đã viết một custom SecurityFilterChain cho Actuator, ứng dụng web còn tự có Boot default security chain không?**

Boot security auto-config thường back off khi có custom SecurityFilterChain. Bạn phải kiểm/sắp xếp security cho **toàn bộ ứng dụng**, không chỉ Actuator.

**7. Tại sao kiểm `QueueHealthIndicator.health()` bằng unit test chưa đủ?**

Nó chưa chứng minh bean được registry nhận, status được aggregate, endpoint expose đúng, HTTP code mapping đúng hoặc details được ẩn đúng role.

**8. `DOWN` không làm health trả 503 sau khi thêm custom mapping cho `FATAL`. Điều gì có thể xảy ra?**

Custom mapping có thể bỏ default DOWN/OUT_OF_SERVICE mapping. Khai rõ các mappings cần giữ và thêm HTTP test regression.

**9. Nếu Kubernetes liveness dùng check DB, DB DOWN làm mọi pods restart. Có hợp lý?**

Thường không. Liveness nên phản ánh tình trạng nội tại không thể hồi phục của process; dependency bên ngoài thường phù hợp hơn với readiness hoặc chính sách degrade service.

**10. Dùng `@Endpoint(id="snapshot")` có phải tự public URL không?**

Không. Endpoint phải **được phép bằng access policy**, **được expose web**, và request phải **qua SecurityFilterChain**. `@ReadOperation` xác định operation GET, không cấp quyền anonymous.

## 12. Checklist vận hành và QA

- [ ] Tôi phân biệt HealthIndicator, HealthEndpoint, endpoint riêng, access, exposure, HTTP authorization và details visibility.
- [ ] Spring Boot 3.5 properties dùng đúng `management.endpoint.<id>.access` / `management.endpoints.access.default` / `max-permitted`.
- [ ] Endpoint mặc định deny khi không opt-in; endpoint cần dùng được phép phù hợp (`read-only` nếu chỉ GET).
- [ ] Web exposure chỉ có allowlist tối thiểu; không expose tất cả trong production.
- [ ] Có test 401 anonymous và 403 thiếu role cho Actuator endpoint nhạy cảm.
- [ ] Có positive test OPS role truy cập được custom read endpoint, JSON không chứa secrets.
- [ ] Custom SecurityFilterChain không mở business routes; có test anonymous bị 401.
- [ ] Health URL public theo threat model, nhưng body anonymous chỉ hiển thị status.
- [ ] `show-details`, `show-components` và `health.roles` được cấu hình có chủ đích.
- [ ] Tests chứng minh USER không thấy infrastructure details, OPS mới thấy.
- [ ] Test cùng một custom HealthIndicator ở state UP và DOWN; status aggregate thay đổi đúng.
- [ ] Test HTTP health trả **200 khi UP, 503 khi DOWN** theo HTTP mapping hiện hành.
- [ ] Test component name đúng (ví dụ `queue`) và details không nhạy cảm.
- [ ] Endpoint không expose được test bằng account có role đầy đủ để phân biệt 404 với 401/403.
- [ ] Endpoint access=none được kiểm trong context với property override.
- [ ] Tests không lạm dụng `@MockBean` làm mất registry/endpoint mapping thật cần kiểm.
- [ ] Với health groups, contributor IDs và group membership được validate.
- [ ] Liveness không phụ thuộc bừa bãi vào DB/API ngoài; readiness reflects traffic ability.
- [ ] Management port/context thực tế có network/TLS/security tests riêng nếu khác main port.
- [ ] Khi thêm status mapping tùy chỉnh, giữ rõ mapping DOWN/OUT_OF_SERVICE nếu cần 503.
- [ ] Nếu thêm write operation, kiểm CSRF cùng authorization; không chỉ assert 403 rồi đoán nguyên nhân.
- [ ] Đã xét endpoint docs/cấu hình khác giữa Servlet MVC và Reactive WebFlux.
- [ ] Không lộ secrets/PII/hostnames nhạy cảm trong `withDetail(...)` và Actuator custom output.
- [ ] Không dùng health endpoint làm kiểm tra dependency chậm vô hạn; có timeout/rate budget.
- [ ] Không nhầm test `MockMvc` với kiểm HTTP real port, ingress, NetworkPolicy hoặc mTLS.
- [ ] Chạy `mvn test` trên JDK 17+ với Spring Boot/Actuator/Security versions thực của project.

**Kết luận:** Test Actuator đúng phải kiểm cả **health indicator logic**, **contributor registration**, **HTTP health status mapping**, **endpoint availability**, **Spring Security authorization** và **mức độ tiết lộ thông tin**. Một endpoint trả `200` chưa chắc public an toàn; một `503` health không đồng nghĩa lỗi role; một `404` có thể do access/exposure; và khi có custom `SecurityFilterChain`, bạn chịu trách nhiệm bảo vệ cả actuator lẫn các API khác. Dùng unit tests cho indicator, `MockMvc`/`@SpringBootTest` cho security/mapping, rồi HTTP/deployment tests cho management port và hạ tầng thật.

### Tài liệu chính thức (Spring Boot 3.5)

- [Spring Boot 3.5 — Actuator Endpoints, Access, Exposure, Security, Health](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html)
- [Spring Boot 3.5 — HealthIndicator API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/health/HealthIndicator.html)
- [Spring Boot 3.5 — HealthEndpoint API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/health/HealthEndpoint.html)
- [Spring Boot 3.5 — EndpointRequest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html)
- [Spring Boot 3.5 — Custom Actuator @Endpoint API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html)
- [Spring Boot 3.5 — Spring Security Integration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
