# Phát hành tuyến động có kiểm tra, kiểm toán và khôi phục

## 1. Bối cảnh và mục tiêu của bài thực hành

Trong một hệ thống microservices, route của **Spring Cloud Gateway (SCG)** thường được khai báo tĩnh bằng YAML hoặc Java DSL. Khi có service mới, thay đổi public path, chuyển traffic sang backend mới hoặc cần khôi phục sau sự cố, đội vận hành phải sửa cấu hình, triển khai lại hoặc cập nhật từng Gateway instance. Cách làm này phù hợp với một số hệ thống nhỏ, nhưng khó đáp ứng yêu cầu thay đổi route có kiểm soát, audit và rollback nhanh.

Bài thực hành xây dựng một quy trình **phát hành tuyến động**: quản trị viên gửi yêu cầu thay đổi route, Gateway kiểm tra dữ liệu và quyền, lưu phiên bản mong muốn, phát hành route vào runtime, ghi audit event và có thể khôi phục phiên bản trước khi phát hiện lỗi.

Chúng ta sẽ dùng một Gateway WebFlux đứng trước Catalog và Orders. Route có thể được thay đổi mà không cần restart ứng dụng. Một thao tác publish phải chứng minh được:

- **Đúng người:** actor có quyền quản trị route.
- **Đúng đích:** upstream thuộc danh sách service đã được phê duyệt.
- **Đúng cấu trúc:** route ID, path, method và filter hợp lệ.
- **Có dấu vết:** lưu ai thay đổi, lúc nào, thay đổi gì và kết quả ra sao.
- **Có thể khôi phục:** giữ snapshot phiên bản trước và biết route nào đang active.
- **Đồng bộ:** các Gateway replicas nhận cùng một desired state và cùng refresh route cache.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt route tĩnh, route động trong bộ nhớ và route động có nguồn dữ liệu bền vững.
2. Sử dụng `RouteDefinitionWriter` để lưu/xóa `RouteDefinition` và phát `RefreshRoutesEvent` sau khi thay đổi.
3. Xây một admin API có authentication/authorization riêng cho thao tác publish.
4. Validate route ID, path, method, service key, URI và filter theo allowlist.
5. Ngăn SSRF bằng cách không nhận upstream URI tùy ý từ request quản trị.
6. Thiết kế release candidate, activation, audit record và snapshot trước khi cập nhật route.
7. Phân biệt trạng thái desired, applied và observed trên nhiều Gateway instances.
8. Rollback bằng cách khôi phục snapshot đã lưu và refresh route cache.
9. Kiểm thử publish, validation failure, refresh failure, backend outage và rollback qua HTTP.
10. Xây runbook và tiêu chí nghiệm thu cho một thay đổi route production.

> **Phạm vi ví dụ:** Bài dùng **Spring Cloud Gateway Server WebFlux**. Namespace cấu hình, starter và một số API thay đổi giữa các release Spring Cloud Gateway; hãy khóa Spring Boot/Spring Cloud BOM trước khi triển khai. Các hostname, service ID, actor và dữ liệu trong bài là ví dụ lab. Chưa có thao tác nào được chạy trên hệ thống production.

## 2. Kịch bản lab và yêu cầu nghiệp vụ

Giả sử Gateway nhận request public:

~~~http
GET /api/catalog/items/42 HTTP/1.1
Host: gateway.lab.example.test
~~~

Route hiện tại:

~~~text
catalog-public -> lb://catalog-service
Path=/api/catalog/**
Method=GET
StripPrefix=2
~~~

Backend Catalog nhận:

~~~http
GET /items/42 HTTP/1.1
~~~

Nhóm vận hành cần thay đổi upstream từ `catalog-service` sang `catalog-v2-service` trong một lần phát hành có audit. Nếu v2 trả lỗi hoặc latency vượt ngưỡng, quản trị viên có thể rollback về route trước đó.

### Ràng buộc của bài

| Yêu cầu | Quyết định thiết kế |
| --- | --- |
| Public route ID | `catalog-public` ổn định qua các lần release |
| Public path | `/api/catalog/**` |
| Allowed methods | `GET`, `HEAD` |
| Upstream | Chọn qua service key trong allowlist |
| Filters | Chỉ cho phép `StripPrefix=2` trong lab |
| Route priority | Giá trị order do server đặt, không nhận từ client |
| Route release | Tạo candidate, validate, activate |
| Audit | Ghi actor, release ID, route ID, before/after và outcome |
| Rollback | Khôi phục snapshot active gần nhất |
| Cluster | Một source of truth, mọi Gateway instance refresh cùng version |

**Không cho admin API nhận URI tùy ý.** Nếu request có thể truyền `http://169.254.169.254`, `http://127.0.0.1`, một địa chỉ IP nội bộ hoặc hostname bất kỳ làm upstream, chức năng quản trị route có thể trở thành SSRF. Người có quyền publish route chỉ được chọn các service đã được platform owner phê duyệt.

## 3. Kiến trúc phát hành route

~~~mermaid
flowchart TD
    A["Operator / Release pipeline"] -->|"JWT + change request"| M["Private Route Admin API"]
    M --> S["Authentication + route-admin authorization"]
    S --> V["Validate schema, allowlist, overlap, filters"]
    V -->|"Invalid"| X["Reject + audit failure"]
    V -->|"Valid"| C["Create immutable candidate"]
    C --> R["Review / approval gate"]
    R -->|"Approved"| P["Publish desired route version"]
    P --> DB[("Durable route store + audit log")]
    P --> E["Refresh notification"]
    E --> G1["Gateway Pod A: reload + refresh"]
    E --> G2["Gateway Pod B: reload + refresh"]
    E --> G3["Gateway Pod N: reload + refresh"]
    G1 --> H["Health / route version observations"]
    G2 --> H
    G3 --> H
    H -->|"Failure / rollback request"| RB["Restore previous snapshot"]
    RB --> DB
    RB --> E
~~~

Kiến trúc có ba loại dữ liệu cần tách:

1. **Release candidate:** bản đề xuất, chưa phục vụ traffic. Có ID, người tạo, nội dung và kết quả validation.
2. **Desired route state:** phiên bản route được phê duyệt và lưu bền vững. Đây là nguồn dữ liệu chuẩn để Gateway instances tải lại.
3. **Observed/applied state:** phiên bản mỗi Gateway instance đã nạp và đang dùng. Nó có thể chậm hơn desired state trong lúc refresh hoặc khi một Pod gặp lỗi.

Nếu chỉ cập nhật route trong một `InMemoryRouteDefinitionRepository`, route có thể mất khi restart và mỗi Pod có thể có cấu hình khác nhau. Lab nhỏ có thể dùng in-memory repository để hiểu API; production cần **durable source of truth** và cơ chế phân phối thay đổi tới mọi replicas.

## 4. RouteDefinition và cơ chế refresh của Gateway

Spring Cloud Gateway mô hình hóa route bằng `RouteDefinition`. Một route có:

- `id`: định danh ổn định.
- `uri`: upstream URI hoặc service URI như `lb://catalog-service`.
- `predicates`: điều kiện match request.
- `filters`: biến đổi request/response.
- `order`: thứ tự ưu tiên route.
- metadata bổ sung nếu ứng dụng có nhu cầu.

Các API quan trọng trong Gateway Server WebFlux:

| API | Vai trò |
| --- | --- |
| `RouteDefinitionWriter` | Lưu hoặc xóa route definition |
| `RouteDefinitionLocator` | Đọc route definitions từ nguồn cấu hình/repository |
| `RouteDefinitionRepository` | Kết hợp khả năng đọc và ghi route definitions |
| `RouteDefinitionRouteLocator` | Chuyển RouteDefinition thành runtime Route |
| `RefreshRoutesEvent` | Thông báo Gateway tải lại routes |
| `RouteLocator` | Cung cấp runtime routes cho request routing |

`RouteDefinitionWriter.save(...)` **không nên được hiểu là đã bảo đảm mọi instance đang phục vụ request dùng route mới**. Sau khi lưu thành công, ứng dụng cần phát sự kiện refresh phù hợp và quan sát kết quả trên từng instance.

Ví dụ luồng API ở mức khái niệm:

~~~java
routeDefinitionWriter.save(Mono.just(route))
    .then(Mono.fromRunnable(() ->
        eventPublisher.publishEvent(new RefreshRoutesEvent(this))));
~~~

Đây là cách làm phù hợp cho một ứng dụng đơn hoặc lab. Trong cluster, một sự kiện trong JVM chỉ đến các listener trong JVM đó; nó **không tự broadcast sang các Pod khác**. Cần event bus/message broker, polling theo version, hoặc cơ chế điều phối refresh được thiết kế riêng.

### Route definitions không phải route objects đang chạy

`RouteDefinition` là cấu hình đầu vào. Gateway chuyển đổi nó thành runtime `Route`, rồi sử dụng các predicate/filter đã được khởi tạo. Vì vậy:

- Route definition được lưu không đồng nghĩa predicate/filter runtime đã tạo thành công.
- URI parse được không đồng nghĩa DNS, service discovery hoặc backend đang healthy.
- Refresh event được phát không đồng nghĩa mọi Pod đã nhận và áp dụng event.
- Một API admin trả 202/200 không thay cho kiểm tra observed state.

## 5. Thiết kế release lifecycle

Một release route nên có state machine rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Validated: validation passed
    Draft --> Rejected: validation failed
    Validated --> Approved: authorized approval
    Validated --> Rejected: approval denied
    Approved --> Publishing: activate
    Publishing --> Active: all required instances applied
    Publishing --> Degraded: one or more instances failed
    Degraded --> Active: retry / convergence
    Degraded --> RolledBack: restore previous version
    Active --> RolledBack: rollback request
    Rejected --> [*]
    RolledBack --> [*]
    Active --> [*]
~~~

### Các trạng thái cần phân biệt

| State | Ý nghĩa | Có phục vụ traffic? |
| --- | --- | --- |
| `DRAFT` | Bản đề xuất đang chỉnh sửa | Không |
| `VALIDATED` | Schema/policy/route conflict đã qua kiểm tra | Không |
| `APPROVED` | Đã có phê duyệt cần thiết | Chưa |
| `PUBLISHING` | Desired state đã được ghi và đang refresh | Tùy instance |
| `ACTIVE` | Các instance bắt buộc đã xác nhận version | Có |
| `DEGRADED` | Chưa hội tụ đủ replicas hoặc có lỗi quan sát | Có thể có một phần |
| `REJECTED` | Candidate bị từ chối | Không |
| `ROLLED_BACK` | Đã khôi phục phiên bản trước | Phiên bản trước được phục vụ |

Trong bài lab, ta thực hiện một quy trình rút gọn: **create candidate → validate → approve → activate → verify → rollback**. Production có thể cần approval hai người, maintenance window, canary, change ticket và giới hạn phạm vi theo tenant/region.

## 6. Chuẩn bị môi trường thực hành

### Thành phần cần có

| Thành phần | Vai trò | Ví dụ lab |
| --- | --- | --- |
| Gateway WebFlux | Nhận request và áp dụng routes | Port 8080 |
| Catalog v1 | Backend hiện tại | `catalog-service` |
| Catalog v2 | Backend đích sau release | `catalog-v2-service` |
| Route Admin API | Tạo candidate, validate, activate, rollback | Chỉ truy cập mạng quản trị |
| Route store | Lưu candidate, desired state và snapshot | In-memory trong bài; DB trong production |
| Audit store | Lưu lịch sử thay đổi bất biến | DB append-only hoặc audit platform |
| Operator client | Gửi yêu cầu quản trị có credentials | curl/Postman/test client |

### Dependency gợi ý

Ứng dụng sử dụng Spring Boot và Spring Cloud BOM tương thích, với Gateway Server WebFlux, OAuth2 Resource Server cho admin API và Actuator cho health/metrics nếu cần:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Tên starter Gateway ở release cũ có thể là `spring-cloud-starter-gateway`. Chỉ dùng đúng starter cho runtime đã chọn. Bài không giả định một phiên bản cụ thể; các API Java bên dưới cần đối chiếu với BOM của dự án.

### Topology lab

~~~mermaid
flowchart LR
    OP["Operator"] -->|8080 / private admin| GW["Gateway"]
    CL["Test client"] -->|8080 /api/catalog/**| GW
    GW -->|"lb://catalog-service"| V1["Catalog v1"]
    GW -->|"lb://catalog-v2-service"| V2["Catalog v2"]
    GW -->|"lb://orders-service"| ORD["Orders"]
    GW --> STORE[("Route store")]
    GW --> AUDIT[("Audit log")]
~~~

Nếu lab chưa có service discovery, thay `lb://...` bằng các URI loopback/HTTP stub đã được cấu hình sẵn. Trong production, `lb://` cần Spring Cloud LoadBalancer và service instance supplier phù hợp; không tự giả định DNS/Kubernetes Service tự cung cấp `ServiceInstance` cho LoadBalancer.

## 7. Hợp đồng Admin API

Admin API không nhận nguyên `RouteDefinition` do client gửi. Nó nhận một **command DTO nhỏ** rồi server tự dựng route từ policy đã duyệt.

### 7.1. Các endpoint trong lab

| Method | Endpoint | Quyền | Mục đích |
| --- | --- | --- | --- |
| `POST` | `/internal/admin/route-releases` | `gateway.routes.write` | Tạo candidate |
| `GET` | `/internal/admin/route-releases/{releaseId}` | `gateway.routes.read` | Xem trạng thái candidate |
| `POST` | `/internal/admin/route-releases/{releaseId}/validate` | `gateway.routes.write` | Chạy validation |
| `POST` | `/internal/admin/route-releases/{releaseId}/approve` | `gateway.routes.approve` | Phê duyệt |
| `POST` | `/internal/admin/route-releases/{releaseId}/activate` | `gateway.routes.publish` | Ghi desired state và refresh |
| `POST` | `/internal/admin/route-releases/{releaseId}/rollback` | `gateway.routes.rollback` | Khôi phục snapshot |
| `GET` | `/internal/admin/routes/{routeId}/status` | `gateway.routes.read` | Desired/observed version |

Tách quyền **write**, **approve**, **publish** và **rollback** giúp thực hiện separation of duties. Với hệ thống nhỏ, một role có thể được cấp nhiều scopes; với hệ thống nhạy cảm, người tạo candidate không nên tự approve và publish thay đổi của chính mình.

### 7.2. Request DTO

Ví dụ tạo candidate:

~~~http
POST /internal/admin/route-releases HTTP/1.1
Authorization: Bearer <operator-token>
Content-Type: application/json
Idempotency-Key: change-2026-042

{
  "routeKey": "catalog-public",
  "serviceKey": "catalog-v2",
  "publicPrefix": "/api/catalog",
  "methods": ["GET", "HEAD"],
  "changeTicket": "CHG-2026-042",
  "reason": "Chuyển Catalog traffic sang backend v2"
}
~~~

Response mẫu:

~~~json
{
  "releaseId": "rel-01JCATALOGV2",
  "routeKey": "catalog-public",
  "state": "DRAFT",
  "validation": "PENDING"
}
~~~

Client chỉ chọn `serviceKey` và khai báo các thuộc tính đã được policy cho phép. Server sẽ map service key thành upstream URI và áp dụng filter/order cố định. Không chấp nhận các trường `uri`, `filters`, `order`, `metadata` tùy ý trong DTO public.

### 7.3. Idempotency và optimistic concurrency

Một lệnh publish có thể bị client retry do timeout dù Gateway đã ghi desired state. Cần:

- `Idempotency-Key` hoặc release ID duy nhất để một command retry không tạo hai releases.
- `expectedVersion`/ETag để ngăn hai quản trị viên ghi đè route cùng lúc.
- `changeTicket` và `reason` bắt buộc để audit.
- Một release chỉ activate một lần; các lần retry phải trả trạng thái đã có.
- Rollback phải kiểm tra active version hiện tại còn đúng version mà lệnh rollback dự kiến.

Nếu thiếu concurrency control, hai thay đổi A/B có thể xảy ra gần nhau: A đọc version 5, B đọc version 5, A publish version 6, B ghi đè version 7 dựa trên snapshot cũ và làm mất thay đổi của A.

## 8. Bảo vệ Route Admin API

Admin API có thể thay đổi traffic toàn hệ thống, vì vậy phải được xem như **control plane**. Không public endpoint này ra Internet như một API nghiệp vụ thông thường.

### 8.1. Security WebFlux

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class RouteAdminSecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/internal/admin/**")
                            .hasAuthority("SCOPE_gateway.routes.write")
                        .pathMatchers("/actuator/health")
                            .permitAll()
                        .anyExchange().authenticated())
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                // Chỉ dùng khi control plane stateless Bearer-only.
                // Nếu admin dùng browser cookie/session, giữ CSRF protection phù hợp.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

Đây là cấu hình tối giản để minh họa. Trong triển khai thật, không dùng một scope `write` cho tất cả endpoint nếu đã tách quyền read/approve/publish/rollback. Có thể dùng matcher theo method/path, reactive method security hoặc một policy service để kiểm tra scope cụ thể.

### 8.2. Các lớp bảo vệ bổ sung

- Đặt admin listener trên management/private network hoặc ingress riêng.
- Xác minh issuer, audience, chữ ký, thời hạn và scope của operator token.
- Dùng mTLS/service identity giữa release pipeline và admin API nếu phù hợp.
- Giới hạn IP/network policy, rate limit và request size.
- Bắt buộc change ticket, reason, release ID và idempotency key.
- Tách người tạo, người phê duyệt và người phát hành nếu mức độ rủi ro yêu cầu.
- Bảo vệ Actuator route listing/refresh endpoints; chúng không phải public admin API.
- Audit cả hành động thành công lẫn bị từ chối, nhưng không ghi token/secret.

### 8.3. Phân biệt data plane và control plane

| Control plane | Data plane |
| --- | --- |
| Tạo/validate/approve route | Match request và proxy traffic |
| Quản lý desired route version | Dùng runtime route cache |
| Audit, rollback, rollout status | Metrics latency/status/upstream |
| Cần quyền quản trị cao | Phục vụ client/API traffic |
| Thay đổi hiếm, có review | Request liên tục, latency nhạy cảm |

Không để một request nghiệp vụ có thể tự sửa route hoặc chọn upstream bằng query/header. Data plane chỉ đọc cấu hình đã được control plane phát hành.

## 9. Allowlist và validation chống SSRF

Đây là bước quan trọng nhất trước khi tạo `RouteDefinition`. **Không nhận upstream URI tự do từ operator request**. Một tài khoản có quyền publish route không nên có khả năng biến Gateway thành proxy tới mọi địa chỉ mạng.

### 9.1. Allowlist service key

~~~java
import java.net.URI;
import java.util.Map;

public final class ApprovedUpstreams {

    private ApprovedUpstreams() {}

    public static final Map<String, URI> BY_KEY = Map.of(
            "catalog-v1", URI.create("lb://catalog-service"),
            "catalog-v2", URI.create("lb://catalog-v2-service"),
            "orders", URI.create("lb://orders-service")
    );
}
~~~

Trong production, danh sách này nên đến từ service inventory/configuration có owner và approval. Service key không được ánh xạ tới host tùy ý do client truyền.

### 9.2. Những dữ liệu cần từ chối

| Input | Lý do |
| --- | --- |
| `http://127.0.0.1:...` | Có thể truy cập loopback/admin service |
| `http://169.254.169.254/...` | Có thể truy cập cloud metadata endpoint |
| `http://10.x.x.x`, `172.16/12`, `192.168/16` tùy ý | Có thể truy cập mạng nội bộ không được phép |
| `file:`, `jar:`, `ftp:` | Không phải upstream HTTP service được phép |
| URI có userinfo (`user:pass@host`) | Có thể đưa credentials vào URI/log |
| Hostname do client tự cung cấp | DNS rebinding/SSRF và truy cập ngoài inventory |
| `lb://` service ID không nằm allowlist | Có thể route tới service nội bộ trái phép |
| Query/fragment trong upstream URI | Không thuộc contract route và dễ gây sai semantics |
| Filter expression tùy ý | Có thể tạo behavior ngoài policy hoặc tăng attack surface |

Allowlist là lớp chính. Các kiểm tra scheme/host/port bổ sung giúp phát hiện cấu hình sai, nhưng **không thay inventory và network egress policy**.

### 9.3. Path validation

Trong lab chỉ cho phép prefix đã khai báo như `/api/catalog` và `/api/orders`. Từ chối:

- Prefix rỗng, không bắt đầu bằng `/`, chứa `//`, `..` hoặc ký tự control.
- Wildcard do operator tự chèn (`*`, `**`, `{*path}`).
- Prefix trùng với `/internal/admin`, `/actuator` hoặc management paths.
- Prefix overlap với route khác mà không có chính sách priority rõ.
- Encoded slash/path normalization không phù hợp contract.

Path phải được kiểm tra sau khi normalize theo cùng semantics mà Gateway sẽ dùng; không dùng một phép `String.replace` tùy ý để kiểm tra route conflict.

## 10. Xây RouteDefinition từ command đã được kiểm tra

Ta không deserialize trực tiếp một `RouteDefinition` do client gửi. Thay vào đó, server ánh xạ command sang một route có cấu trúc cố định.

### 10.1. Command DTO

~~~java
import java.util.List;

public record CreateRouteReleaseRequest(
        String routeKey,
        String serviceKey,
        String publicPrefix,
        List<String> methods,
        String changeTicket,
        String reason
) {}
~~~

Không có trường `uri`, `filters`, `order` hoặc `predicateArgs` trong DTO. Những giá trị đó được server quyết định.

### 10.2. Validator

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.stereotype.Component;
import org.springframework.web.util.pattern.PathPatternParser;

@Component
public class RouteCommandValidator {

    private static final Pattern ROUTE_KEY =
            Pattern.compile("[a-z][a-z0-9-]{2,50}");
    private static final Set<String> ROUTE_KEYS =
            Set.of("catalog-public", "orders-public");
    private static final Set<String> PREFIXES =
            Set.of("/api/catalog", "/api/orders");
    private static final Set<String> METHODS =
            Set.of("GET", "HEAD");
    private static final Set<String> SERVICE_KEYS =
            ApprovedUpstreams.BY_KEY.keySet();
    private static final Map<String, String> PREFIX_BY_ROUTE =
            Map.of(
                    "catalog-public", "/api/catalog",
                    "orders-public", "/api/orders");
    private static final Map<String, Set<String>> SERVICES_BY_ROUTE =
            Map.of(
                    "catalog-public", Set.of("catalog-v1", "catalog-v2"),
                    "orders-public", Set.of("orders"));

    public void validate(CreateRouteReleaseRequest request) {
        require(request != null, "request is required");
        require(request.routeKey() != null
                        && ROUTE_KEY.matcher(request.routeKey()).matches(),
                "invalid routeKey");
        require(ROUTE_KEYS.contains(request.routeKey()),
                "routeKey is not approved");
        require(SERVICE_KEYS.contains(request.serviceKey()),
                "serviceKey is not approved");
        require(PREFIXES.contains(request.publicPrefix()),
                "publicPrefix is not approved");
        require(request.publicPrefix().equals(
                        PREFIX_BY_ROUTE.get(request.routeKey())),
                "routeKey and publicPrefix do not match");
        require(SERVICES_BY_ROUTE.get(request.routeKey())
                        .contains(request.serviceKey()),
                "serviceKey is not approved for this routeKey");
        require(request.methods() != null
                        && !request.methods().isEmpty()
                        && METHODS.containsAll(request.methods()),
                "method is not approved");
        require(request.methods().stream().distinct().count()
                        == request.methods().size(),
                "duplicate methods are not allowed");
        require(request.changeTicket() != null
                        && request.changeTicket().matches("CHG-[A-Z0-9-]{4,40}"),
                "changeTicket is invalid");
        require(request.reason() != null
                        && !request.reason().isBlank()
                        && request.reason().length() <= 300,
                "reason is required and must be at most 300 characters");

        // Parse bằng path parser mà ứng dụng dùng; prefix vẫn phải nằm trong allowlist.
        PathPatternParser.defaultInstance.parse(
                request.publicPrefix() + "/**");
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalArgumentException(message);
        }
    }
}
~~~

Validator ở trên minh họa policy của lab, không thay kiểm tra authorization hay route-conflict service. `PathPatternParser` xác nhận pattern hợp lệ theo parser; allowlist mới giới hạn prefix được phép. Trong production, route conflict cần xét **tất cả routes hiện có**, method overlap, host predicate, order và các rewrite ở ingress.

### 10.3. Build RouteDefinition

~~~java
import java.net.URI;
import java.util.List;

import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.filter.FilterDefinition;
import org.springframework.cloud.gateway.handler.predicate.PredicateDefinition;
import org.springframework.stereotype.Component;

@Component
public class RouteDefinitionFactory {

    public RouteDefinition build(CreateRouteReleaseRequest request) {
        URI upstream = ApprovedUpstreams.BY_KEY.get(request.serviceKey());

        RouteDefinition route = new RouteDefinition();
        route.setId(request.routeKey());
        route.setUri(upstream);
        route.setOrder(100);
        route.setPredicates(List.of(
                new PredicateDefinition(
                        "Path=" + request.publicPrefix() + "/**"),
                new PredicateDefinition(
                        "Method=" + String.join(",", request.methods()))
        ));
        route.setFilters(List.of(
                new FilterDefinition("StripPrefix=2")
        ));
        return route;
    }
}
~~~

Đối với `/api/catalog/items/42`, `StripPrefix=2` đưa backend path về `/items/42`. Prefix `/api/orders` cũng có hai segments; nếu public prefix thay đổi, filter phải được tính lại hoặc cấu hình thành policy tương ứng. Không để admin chọn tùy ý `StripPrefix` trong lab.

**Lưu ý về API version:** constructors và binding của `PredicateDefinition`/`FilterDefinition` có thể khác theo Gateway release. Đối chiếu compile API với BOM đang dùng. Nếu project release không hỗ trợ shortcut constructor, tạo definition bằng API builder/config args tương ứng của release đó; không đoán args rồi publish vào production.

## 11. Lưu candidate và audit record

Một release candidate cần giữ **nội dung bất biến** sau khi đã được phê duyệt. Nếu candidate có thể bị sửa sau approval mà không tạo version mới, audit trail không còn chứng minh được nội dung nào đã được phát hành.

### 11.1. Mô hình dữ liệu

| Bản ghi | Trường tiêu biểu | Quy tắc |
| --- | --- | --- |
| `route_release` | release_id, route_key, state, created_by, created_at, change_ticket, reason | Một candidate có lifecycle |
| `route_release_spec` | release_id, service_key, public_prefix, methods, spec_hash | Nội dung candidate bất biến sau validation |
| `route_version` | route_key, version, route_definition_json, spec_hash, created_at | Snapshot mỗi version |
| `route_active_state` | route_key, active_version, desired_version, updated_at | Optimistic lock theo version |
| `route_audit_event` | event_id, actor, action, release_id, before_hash, after_hash, outcome, timestamp, correlation_id | Append-only |
| `route_instance_observation` | instance_id, desired_version, applied_version, status, observed_at, error_code | Theo dõi convergence |

### 11.2. Audit event mẫu

~~~json
{
  "eventId": "aud-01JCATALOG-0007",
  "actor": "operator-17",
  "action": "ROUTE_ACTIVATE",
  "routeKey": "catalog-public",
  "releaseId": "rel-01JCATALOGV2",
  "changeTicket": "CHG-2026-042",
  "beforeVersion": 12,
  "afterVersion": 13,
  "beforeHash": "sha256:8c2f...redacted-example",
  "afterHash": "sha256:0b9a...redacted-example",
  "outcome": "REQUESTED",
  "correlationId": "trace-lab-00042",
  "timestamp": "2026-11-24T08:30:00Z"
}
~~~

Audit record không cần chứa bearer token, client secret, cookie hoặc toàn bộ HTTP headers. Route definition có thể chứa thông tin topology nội bộ; giới hạn quyền đọc audit và che thông tin nhạy cảm khi hiển thị.

### 11.3. Thứ tự ghi dữ liệu khi activate

Trong một hệ thống bền vững, nên dùng một transaction ở control-plane store để:

1. Kiểm tra candidate đang `APPROVED`.
2. Kiểm tra `expectedVersion` bằng active version hiện tại.
3. Lưu snapshot version trước.
4. Ghi desired route version mới.
5. Ghi audit event `ROUTE_ACTIVATE_REQUESTED`.
6. Commit transaction.
7. Phát refresh notification sau commit.
8. Ghi nhận observed state từ từng Gateway instance.

Không giữ transaction DB mở trong lúc chờ mọi Gateway Pod refresh. Thay vào đó dùng outbox/event pattern hoặc một release coordinator theo dõi trạng thái. Nếu refresh thất bại, desired state vẫn có thể được phát lại hoặc rollback theo policy.

### 11.4. Audit phải ghi cả thất bại

Các hành động cần audit:

- Candidate được tạo, validation thành công/thất bại.
- Approval được cấp hoặc từ chối.
- Activation được yêu cầu, lưu thành công, refresh thành công/thất bại.
- Một Gateway instance báo degraded hoặc không hội tụ.
- Rollback được yêu cầu, chấp nhận/từ chối và hoàn tất.
- Admin request bị 401/403 hoặc bị policy từ chối.

Audit store nên có retention, access control, backup và tamper-evidence phù hợp. Không cho API admin xóa lịch sử audit cùng lúc với route.

## 12. Publish route trong một Gateway instance

Đối với lab một instance, có thể dùng `RouteDefinitionWriter` để ghi route và `RefreshRoutesEvent` để yêu cầu Gateway nạp lại routes.

### 12.1. Service publish tối giản

~~~java
import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionWriter;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class LocalRoutePublisher {

    private final RouteDefinitionWriter writer;
    private final ApplicationEventPublisher events;

    public LocalRoutePublisher(
            RouteDefinitionWriter writer,
            ApplicationEventPublisher events) {
        this.writer = writer;
        this.events = events;
    }

    public Mono<Void> publish(RouteDefinition definition) {
        return writer.save(Mono.just(definition))
                .then(Mono.fromRunnable(() ->
                        events.publishEvent(new RefreshRoutesEvent(this))));
    }

    public Mono<Void> remove(String routeId) {
        return writer.delete(Mono.just(routeId))
                .then(Mono.fromRunnable(() ->
                        events.publishEvent(new RefreshRoutesEvent(this))));
    }
}
~~~

Đây là **publisher cục bộ cho lab**. Nó không tự cung cấp transaction giữa route store và audit store, không tự xác minh runtime route đã build thành công và không broadcast refresh tới các JVM khác.

### 12.2. Xử lý lỗi save và refresh

Một chuỗi reactive chỉ hoàn tất khi `writer.save(...)` hoàn tất và event publish được gọi. Nhưng event publication không đồng nghĩa mọi route predicate/filter đã được materialize thành công. Cần một bước quan sát sau refresh:

- Đọc runtime routes và xác nhận route ID/version mong đợi xuất hiện.
- Gửi smoke request qua public path tới backend test/health endpoint phù hợp.
- Ghi `appliedVersion` và kết quả theo instance.
- Nếu lỗi, ghi failure reason đã redact và chuyển release sang `DEGRADED`.

Không trả trạng thái `ACTIVE` chỉ vì publisher method trả `onComplete`.

### 12.3. In-memory repository phù hợp khi nào?

`InMemoryRouteDefinitionRepository` tiện cho demo và test vì route definition được lưu trong process. Nhưng:

- Restart Gateway có thể mất các route động.
- Pod A và Pod B có state riêng.
- Một lần publish vào Pod A không tự sửa Pod B.
- Không có audit/history/rollback bền vững nếu không tự lưu nơi khác.

Trong production, dùng một `RouteDefinitionRepository` có persistence hoặc một `RouteDefinitionLocator` đọc từ nguồn bền vững. Phần route activation vẫn phải có refresh và quan sát trạng thái.

## 13. Xây Route Release Service và Admin Controller

Ta tách phần HTTP, validation, route factory, release store, audit và publisher để mỗi thành phần có thể kiểm thử riêng.

### 13.1. Các abstraction của control plane

~~~java
import reactor.core.publisher.Mono;

public interface RouteReleaseStore {
    Mono<RouteRelease> createDraft(
            CreateRouteReleaseRequest request,
            String actor,
            String idempotencyKey);

    Mono<RouteRelease> findById(String releaseId);

    Mono<RouteRelease> markValidated(String releaseId, String specHash);

    Mono<RouteRelease> approve(
            String releaseId, String approver, long expectedVersion);

    Mono<RouteActivation> activateAtomically(
            String releaseId, String actor, long expectedVersion);

    Mono<RouteSnapshot> findActiveSnapshot(String routeKey);

    Mono<RouteActivation> rollbackAtomically(
            String routeKey,
            String actor,
            long expectedVersion,
            String reason);
}

public interface RouteAuditStore {
    Mono<Void> append(RouteAuditEvent event);
}

public interface RouteObservationStore {
    Mono<Void> record(RouteInstanceObservation observation);
}
~~~

Các record `RouteRelease`, `RouteActivation`, `RouteSnapshot`, `RouteAuditEvent` và `RouteInstanceObservation` là mô hình dữ liệu cần định nghĩa trong ứng dụng. Interface trên thể hiện contract của lab, **không phải class có sẵn của Spring Cloud Gateway**.

### 13.2. Controller mỏng

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/internal/admin/route-releases")
public class RouteReleaseController {

    private final RouteReleaseApplicationService service;

    public RouteReleaseController(RouteReleaseApplicationService service) {
        this.service = service;
    }

    @PostMapping
    public Mono<ResponseEntity<ReleaseResponse>> create(
            @RequestBody CreateRouteReleaseRequest request,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @AuthenticationPrincipal Jwt operator) {

        return service.createCandidate(
                        request, operator.getSubject(), idempotencyKey)
                .map(response -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(response));
    }

    @PostMapping("/{releaseId}/validate")
    public Mono<ReleaseResponse> validate(
            @PathVariable String releaseId,
            @AuthenticationPrincipal Jwt operator) {
        return service.validate(releaseId, operator.getSubject());
    }

    @PostMapping("/{releaseId}/approve")
    public Mono<ReleaseResponse> approve(
            @PathVariable String releaseId,
            @RequestHeader("If-Match") String expectedVersion,
            @AuthenticationPrincipal Jwt operator) {
        return service.approve(
                releaseId, operator.getSubject(), expectedVersion);
    }

    @PostMapping("/{releaseId}/activate")
    public Mono<ReleaseResponse> activate(
            @PathVariable String releaseId,
            @RequestHeader("If-Match") String expectedVersion,
            @AuthenticationPrincipal Jwt operator) {
        return service.activate(
                releaseId, operator.getSubject(), expectedVersion);
    }
}
~~~

Đây là skeleton WebFlux minh họa. `ReleaseResponse` và `RouteReleaseApplicationService` do bài thực hành định nghĩa. Nếu method nhận `Jwt` làm principal, admin API phải thực sự dùng JWT Resource Server; nếu dùng authentication khác, lấy actor từ principal đã được xác minh theo cách tương ứng. Không lấy `actor` từ JSON request.

### 13.3. Phân quyền theo từng hành động

Cấu hình ở phần 8 đang dùng một scope cho toàn bộ `/internal/admin/**` để giữ ví dụ ngắn. Khi triển khai, tách quyền:

| Endpoint | Authority gợi ý |
| --- | --- |
| Tạo candidate | `SCOPE_gateway.routes.write` |
| Đọc release/status | `SCOPE_gateway.routes.read` |
| Approve | `SCOPE_gateway.routes.approve` |
| Activate | `SCOPE_gateway.routes.publish` |
| Rollback | `SCOPE_gateway.routes.rollback` |

Nếu dùng một `SecurityWebFilterChain`, có thể kết hợp matcher method/path và authority. Cần test trường hợp user chỉ có `write` không thể gọi `activate` hoặc `rollback`.

## 14. Quy trình create → validate → approve → activate

### 14.1. Create candidate

1. Xác thực operator token.
2. Kiểm tra quyền `gateway.routes.write`.
3. Kiểm tra `Idempotency-Key`.
4. Validate DTO cơ bản và service key/path/method allowlist.
5. Tạo release ID duy nhất và lưu candidate ở `DRAFT`.
6. Ghi audit `ROUTE_CANDIDATE_CREATED`.

### 14.2. Validate candidate

Validation nên kiểm tra:

- DTO schema, độ dài, ký tự và trường bắt buộc.
- Service key có trong inventory/allowlist và service còn được phép publish.
- Public prefix nằm trong path allowlist và không trùng route reserved.
- Predicate/filter thuộc danh sách hỗ trợ; không có expression tùy ý.
- Route ID không xung đột hoặc thay đổi sai owner.
- Method/path overlap với routes hiện có.
- Upstream service có health/registration phù hợp.
- Route definition có thể parse/materialize trong một test context đúng Gateway version.
- Policy security, rate limit, TLS và observability của route đã được gắn.

Validation pass chỉ chứng minh cấu hình **đủ điều kiện xét duyệt**, không chứng minh backend chắc chắn healthy khi phát hành.

### 14.3. Approve candidate

Approval cần ghi:

- Approver identity và authority.
- Candidate spec hash.
- Version hiện tại mà candidate dựa vào.
- Change ticket, reason và thời điểm phê duyệt.
- Điều kiện publish (thời gian, phạm vi, canary, maintenance window).

Nếu spec hash thay đổi sau approval, trạng thái phải quay lại `DRAFT` hoặc `VALIDATED` và cần approval mới. Không cho sửa nội dung đã được duyệt tại chỗ.

### 14.4. Activate candidate

Activation cần dùng compare-and-set/optimistic locking:

~~~text
expectedVersion = 12
activeVersion   = 12
candidate       = approved release 13

transaction:
  assert activeVersion == expectedVersion
  save snapshot(version=12)
  write desiredVersion=13
  write audit(ROUTE_ACTIVATE_REQUESTED, before=12, after=13)
commit

publish refresh notification(version=13)
observe each Gateway instance
~~~

Nếu active version đã là 13 hoặc 14, lệnh dựa trên `expectedVersion=12` phải bị từ chối bằng conflict (ví dụ HTTP 409). Operator cần đọc state mới và tạo candidate/review lại.

## 15. Phát hành route và quan sát trên nhiều Gateway replicas

Một cluster Gateway thường có nhiều Pod. Việc cập nhật route phải **hội tụ trên mọi instance** hoặc đạt policy rollout đã được công bố.

### 15.1. Không chỉ gửi RefreshRoutesEvent trong một Pod

`RefreshRoutesEvent` là application event trong process. Để phân phối:

1. Control plane ghi desired version vào store dùng chung.
2. Control plane ghi event vào outbox trong cùng transaction.
3. Publisher gửi event chứa `routeKey`, `desiredVersion`, `releaseId`, `eventId`.
4. Mỗi Gateway Pod nhận event và tải route definition theo version từ source of truth.
5. Pod cập nhật route repository/cache và phát refresh event local.
6. Pod ghi observation thành công/thất bại kèm instance ID.
7. Coordinator tổng hợp trạng thái và quyết định `ACTIVE` hay `DEGRADED`.

### 15.2. Payload refresh notification

~~~json
{
  "eventId": "evt-01JCATALOG-00013",
  "eventType": "ROUTE_VERSION_PUBLISHED",
  "routeKey": "catalog-public",
  "releaseId": "rel-01JCATALOGV2",
  "desiredVersion": 13,
  "specHash": "sha256:0b9a...example",
  "createdAt": "2026-11-24T08:30:00Z"
}
~~~

Event không cần chứa toàn bộ access token hoặc secret. Pod nhận event có thể tải version từ store qua identity riêng và kiểm tra hash để bảo đảm payload không bị thay đổi.

### 15.3. Trạng thái quan sát

| Instance | Desired | Applied | Status | Hành động |
| --- | ---: | ---: | --- | --- |
| gateway-a | 13 | 13 | `APPLIED` | Không cần |
| gateway-b | 13 | 13 | `APPLIED` | Không cần |
| gateway-c | 13 | 12 | `REFRESH_FAILED` | Retry/reconcile |

Trong ví dụ, cluster chưa nên được đánh dấu `ACTIVE` nếu policy yêu cầu 100% replicas đã áp dụng. Có thể dùng quorum/canary policy nếu được phê duyệt, nhưng phải công bố rõ Pod nào còn phục vụ version cũ và cách tránh split behavior.

### 15.4. Reconciliation quan trọng hơn event delivery một lần

Message broker có thể giao event lặp, đến trễ hoặc sai thứ tự. Mỗi Pod nên:

- Xử lý event idempotently theo `eventId` và `desiredVersion`.
- Bỏ qua version thấp hơn version đã áp dụng.
- Nếu nhận version 15 khi đang ở 13, tải trực tiếp version 15 nếu store có snapshot đầy đủ.
- Định kỳ so sánh applied version với desired version.
- Retry có backoff và giới hạn; không refresh liên tục không kiểm soát.
- Báo lỗi có mã hữu hạn, không ghi token/config secrets.

Nếu Pod restart, nó phải tải desired state mới nhất từ source of truth khi khởi động, không chỉ dựa vào event có thể đã bỏ lỡ.

## 16. Rollback có kiểm soát

Rollback là một **release mới** khôi phục nội dung của snapshot trước. Không xóa lịch sử và không sửa ngược bản ghi version đã phát hành.

### 16.1. Ví dụ version timeline

| Version | Nội dung | State |
| ---: | --- | --- |
| 12 | `catalog-public` → `lb://catalog-service` | Snapshot trước |
| 13 | `catalog-public` → `lb://catalog-v2-service` | Active sau publish |
| 14 | Khôi phục spec của version 12 | Rollback release mới |

Version 14 có số lớn hơn version 13 nhưng dùng lại **route specification** của version 12. Cách đánh version đơn điệu này giúp event ordering, audit và reconciliation dễ hiểu hơn việc giảm active version từ 13 về 12.

### 16.2. Quy trình rollback

1. Operator có quyền `gateway.routes.rollback` gửi rollback command với reason và `expectedVersion=13`.
2. Control plane đọc active snapshot version 13 và previous known-good snapshot 12.
3. Kiểm tra version hiện tại vẫn là 13; nếu route đã đổi sang version 14, trả conflict.
4. Tạo rollback release 14 chứa spec đã lưu của version 12 và ghi `rollbackOfVersion=12`.
5. Ghi desired state version 14, audit event và outbox trong transaction.
6. Phát refresh notification version 14.
7. Mỗi Gateway Pod tải version 14, refresh và báo applied state.
8. Chạy smoke tests qua route public.
9. Khi đạt convergence policy, đánh dấu version 14 `ACTIVE`; giữ version 13 và toàn bộ audit history.

### 16.3. Code khôi phục route definition trong lab

~~~java
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionWriter;
import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.context.ApplicationEventPublisher;

import reactor.core.publisher.Mono;

public class RouteRollbackPublisher {

    private final RouteDefinitionWriter writer;
    private final ApplicationEventPublisher events;

    public RouteRollbackPublisher(
            RouteDefinitionWriter writer,
            ApplicationEventPublisher events) {
        this.writer = writer;
        this.events = events;
    }

    public Mono<Void> restore(RouteDefinition previousSnapshot) {
        // Snapshot phải được đọc từ store đã xác thực và có version/hash.
        return writer.save(Mono.just(previousSnapshot))
                .then(Mono.fromRunnable(() ->
                        events.publishEvent(new RefreshRoutesEvent(this))));
    }
}
~~~

Đoạn code này chỉ thực hiện ghi và refresh trong **một Gateway instance**. Production phải gọi qua release coordinator: kiểm tra expected version, tạo rollback version mới, ghi audit/outbox bền vững, broadcast tới replicas và đợi observed state.

### 16.4. Khi rollback cũng thất bại

Không được giả định version cũ luôn deploy được. Có thể:

- Service cũ đã bị xóa hoặc không còn instance.
- DNS/service discovery không còn resolve.
- TLS certificate cũ hết hạn.
- Database schema đã thay đổi không tương thích.
- Backend cũ vẫn tồn tại nhưng không còn đủ capacity.
- Route snapshot chứa filter factory không còn trong Gateway build mới.

Vì vậy release cần ghi cả **route spec version lẫn compatibility/dependency assumptions**. Trước khi xóa backend cũ, phải xác nhận thời hạn rollback đã kết thúc và có phương án phục hồi khác.

## 17. Audit trail và tính toàn vẹn

Audit trail phải giúp trả lời: **ai đã làm gì, trên route nào, dựa vào version nào, thay đổi thành gì, được ai duyệt và các Gateway instance đã áp dụng ra sao?**

### 17.1. Event model

~~~java
import java.time.Instant;

public record RouteAuditEvent(
        String eventId,
        String actor,
        String action,
        String routeKey,
        String releaseId,
        Long beforeVersion,
        Long afterVersion,
        String beforeHash,
        String afterHash,
        String outcome,
        String changeTicket,
        String correlationId,
        Instant occurredAt
) {}
~~~

### 17.2. Hash route specification

Hash giúp nhận biết hai bản cấu hình có cùng nội dung hay không. Trước khi hash:

1. Serialize route spec theo một định dạng canonical ổn định.
2. Sắp xếp map keys và chuẩn hóa cách biểu diễn URI/method/filter.
3. Loại bỏ field biến động không thuộc cấu hình (ví dụ `createdAt`).
4. Tính SHA-256 trên byte UTF-8.
5. Lưu hash cùng immutable snapshot.

Không hash chuỗi JSON tùy thứ tự map rồi kết luận cấu hình khác nhau khi chỉ đổi thứ tự field. Hash **không thay chữ ký số hoặc quyền truy cập**; người có quyền sửa cả spec lẫn hash vẫn có thể thay đổi cả hai. Cần bảo vệ store/audit và quyền ghi.

### 17.3. Outbox pattern để không mất audit/refresh event

Trong cùng transaction:

- Lưu route version mới.
- Cập nhật desired state bằng optimistic lock.
- Append audit event.
- Ghi outbox event cần gửi cho Gateway instances.

Một publisher nền đọc outbox và gửi message. Khi gửi thành công, đánh dấu delivered; khi lỗi, retry. Consumer idempotent theo event ID. Cách này xử lý tình huống DB commit thành công nhưng process chết trước khi gửi refresh notification.

### 17.4. Audit bất biến và bảo vệ dữ liệu

- Chỉ service audit được append; operator không được sửa/xóa event cũ.
- Giới hạn người đọc audit và có retention policy.
- Không ghi Authorization, client secret, refresh token, cookie hoặc raw request body.
- Lưu actor từ identity đã xác thực, không tin actor trong DTO.
- Gắn change ticket và correlation ID để nối với release pipeline.
- Với yêu cầu tuân thủ cao, dùng append-only storage, immutable backup hoặc chữ ký/hash chain do platform quản lý.

## 18. Canary và phạm vi phát hành

Một route động có thể được phát hành theo nhiều chiến lược. **Không coi việc đổi URI là canary** nếu toàn bộ Gateway instances lập tức chuyển sang backend mới.

### 18.1. Các lựa chọn

| Chiến lược | Cách thực hiện | Khi phù hợp |
| --- | --- | --- |
| All-at-once | Cập nhật route ID ổn định trên tất cả instances | Thay đổi nhỏ, backend đã kiểm thử |
| Instance canary | Một nhóm Gateway Pod dùng desired version mới | Muốn quan sát data-plane behavior theo Pod |
| Weighted backend | Route phân phối traffic theo weight tới các backend tương thích | Có support/version-specific configuration đã kiểm thử |
| Header cohort | Chỉ nhóm client/test có header được allowlist mới vào candidate path | Canary có kiểm soát theo client cohort |
| Shadow traffic | Mirror request sang backend mới nhưng không dùng response của nó | So sánh behavior/latency, tránh side effects |

### 18.2. Canary không thay route validation

Trước khi chuyển 5% traffic:

- Candidate phải qua schema/policy validation.
- Backend v2 có readiness/health và capacity phù hợp.
- Authorization/TLS/headers được kiểm tra.
- Metrics theo route version/upstream có sẵn.
- Có threshold và rollback trigger rõ.
- Canary traffic không bao gồm operations có side effect nếu backend mirror không idempotent.

### 18.3. Không phát hành weight do client tự gửi

Weight là policy của control plane, không lấy từ query/header tùy ý. Nếu dùng weighted routing, giới hạn min/max, tổng weight, backend set allowlist và kiểm thử phân phối. Không dùng random selection như một cơ chế authorization.

## 19. Observability và health verification

Sau publish, cần đo **route config đã áp dụng** và **traffic thực tế có khỏe không**.

### 19.1. Metrics gợi ý

| Metric | Nhãn hữu hạn | Mục đích |
| --- | --- | --- |
| `route_release_total` | action, outcome | Số lần create/validate/activate/rollback |
| `route_refresh_total` | instance, outcome | Kết quả refresh trên từng Gateway Pod |
| `route_applied_version` | route_key, instance | Version hiện đang áp dụng |
| `route_publish_duration` | route_key, outcome | Thời gian từ desired đến observed |
| `gateway_requests` | route_id, status, upstream | Traffic và lỗi theo route |
| `gateway_request_duration` | route_id, upstream | Latency theo route/backend |
| `route_rollback_total` | route_key, reason_code | Theo dõi rollback |
| `route_validation_failure_total` | rule_code | Phát hiện candidate không hợp lệ |

Không dùng `releaseId`, user ID, raw path, query string hoặc arbitrary hostname làm metric label nếu chúng tạo cardinality cao. Chi tiết release/audit nên lưu trong event store.

### 19.2. Health checks sau activation

Một route được đánh dấu active khi đạt các điều kiện đã định:

1. Desired version đã được ghi bền vững.
2. Các Gateway instances bắt buộc đã báo applied version.
3. Route ID xuất hiện trong runtime route view của từng instance.
4. Smoke request đi qua route tới đúng upstream.
5. Backend readiness/health đạt ngưỡng.
6. Không có lỗi 401/403/404/5xx bất thường sau rollout.
7. Latency/error rate nằm trong threshold trong observation window.

Không gọi một endpoint health của backend rồi kết luận route path/filter hoạt động đúng. Smoke test phải đi qua **public route thực tế** với request method/path/header đã được phê duyệt.

### 19.3. Actuator và route diagnostics

Actuator có thể giúp kiểm tra health/metrics và route diagnostics tùy Gateway release/configuration. Các endpoint route listing/refresh có thể lộ backend URI, filter config hoặc cho phép thay đổi runtime. Vì vậy:

- Chỉ expose những endpoint thật sự cần.
- Bảo vệ bằng authentication, role và private network.
- Không public route mutation endpoint cho client nghiệp vụ.
- Không coi Actuator endpoint là audit/release workflow đầy đủ.
- Ghi version/hash và actor ở control plane, không chỉ dựa vào route listing.

## 20. Kiểm thử quy trình publish và rollback

Một test chỉ assert admin API trả HTTP 200 chưa đủ. Cần kiểm tra **state store, audit record, runtime route, backend nhận request và mọi instance**.

### 20.1. Các lớp test

| Loại test | Thành phần | Điều cần chứng minh |
| --- | --- | --- |
| Unit test | Validator, route factory | Input sai bị từ chối; route definition tạo đúng |
| Application test | Release service/store/audit | State transition, idempotency, optimistic lock |
| Gateway integration test | `RouteDefinitionWriter` + HTTP listener | Route mới được refresh và match request |
| Admin API security test | JWT/authorities | Operator thiếu quyền không thể publish/rollback |
| Multi-instance test | Nhiều Gateway contexts hoặc test nodes | Desired version hội tụ, event lặp không gây lỗi |
| Failure injection | Token store, event bus, backend | Degraded state và recovery hoạt động |
| E2E test | Operator → control plane → Gateway → backend | Toàn bộ release path có audit và rollback |

### 20.2. Unit test cho validator

~~~java
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RouteCommandValidatorTest {
    private final RouteCommandValidator validator =
            new RouteCommandValidator();

    @Test
    void acceptsApprovedCatalogRoute() {
        var request = new CreateRouteReleaseRequest(
                "catalog-public", "catalog-v2", "/api/catalog",
                List.of("GET", "HEAD"), "CHG-2026-042",
                "Switch to catalog v2");
        assertDoesNotThrow(() -> validator.validate(request));
    }

    @Test
    void rejectsUnapprovedServiceKey() {
        var request = new CreateRouteReleaseRequest(
                "catalog-public", "http://127.0.0.1:9000",
                "/api/catalog", List.of("GET"), "CHG-2026-042",
                "Invalid upstream attempt");
        assertThrows(IllegalArgumentException.class,
                () -> validator.validate(request));
    }

    @Test
    void rejectsAdminPathAsPublicPrefix() {
        var request = new CreateRouteReleaseRequest(
                "catalog-public", "catalog-v2", "/internal/admin",
                List.of("GET"), "CHG-2026-042",
                "Reserved path attempt");
        assertThrows(IllegalArgumentException.class,
                () -> validator.validate(request));
    }

    @Test
    void rejectsMethodOutsideAllowlist() {
        var request = new CreateRouteReleaseRequest(
                "catalog-public", "catalog-v2", "/api/catalog",
                List.of("DELETE"), "CHG-2026-042",
                "Method is not approved");
        assertThrows(IllegalArgumentException.class,
                () -> validator.validate(request));
    }
}
~~~

Các tests này chỉ kiểm tra allowlist trong ví dụ. Khi mở rộng policy, thêm tests cho route overlap, duplicate methods, path normalization, service disabled và change ticket invalid.

### 20.3. Test route definition

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class RouteDefinitionFactoryTest {
    private final RouteDefinitionFactory factory =
            new RouteDefinitionFactory();

    @Test
    void buildsApprovedCatalogRoute() {
        var request = new CreateRouteReleaseRequest(
                "catalog-public", "catalog-v2", "/api/catalog",
                java.util.List.of("GET"), "CHG-2026-042",
                "Switch backend");
        var route = factory.build(request);

        assertEquals("catalog-public", route.getId());
        assertEquals("lb://catalog-v2-service",
                route.getUri().toString());
        assertEquals(100, route.getOrder());
        assertEquals(2, route.getPredicates().size());
        assertEquals("Path", route.getPredicates().get(0).getName());
        assertEquals("Method", route.getPredicates().get(1).getName());
        assertEquals("StripPrefix", route.getFilters().get(0).getName());
    }
}
~~~

Nếu constructor shortcut của `PredicateDefinition`/`FilterDefinition` khác trong Gateway release đang dùng, điều chỉnh test theo API thực tế của BOM. Không bỏ assertion về URI/predicate/filter chỉ để test compile.

### 20.4. Gateway integration test

Trong integration test:

1. Khởi động Gateway với `RANDOM_PORT`.
2. Cấu hình hai backend HTTP stubs trên port ngẫu nhiên.
3. Gọi route hiện tại và xác nhận Catalog v1 nhận request.
4. Gọi `RouteDefinitionWriter.save(...)` qua publisher lab và phát refresh event.
5. Gọi lại cùng public path và xác nhận Catalog v2 nhận request.
6. Khôi phục snapshot v1, refresh lần nữa và xác nhận request quay lại v1.
7. Kiểm tra response status/body, request count và path backend nhận.

Test phải gửi HTTP qua Gateway listener thật. Gọi trực tiếp service method không chứng minh predicate/filter chain đã chạy.

### 20.5. Test security cho Admin API

| Operator token | Create | Approve | Activate | Rollback |
| --- | --- | --- | --- | --- |
| Không token | 401 | 401 | 401 | 401 |
| Chỉ `routes.read` | 403 | 403 | 403 | 403 |
| Chỉ `routes.write` | Cho phép | 403 | 403 | 403 |
| `routes.approve` | Theo policy | Cho phép | 403 | 403 |
| `routes.publish` | Theo policy | 403 | Cho phép nếu approved | 403 |
| `routes.rollback` | Theo policy | 403 | 403 | Cho phép |

Trong test dùng mock JWT để kiểm tra authority mapping là hữu ích, nhưng phải có một test riêng dùng signed JWT/test issuer qua HTTP để xác minh signature, issuer và audience thật.

## 21. Failure injection và tiêu chí phục hồi

Một quy trình phát hành đáng tin phải xử lý cả trường hợp không thuận lợi.

| Sự cố | Kết quả mong đợi | Hành động |
| --- | --- | --- |
| Candidate có service key lạ | Validation fail | Audit `VALIDATION_REJECTED`, không ghi desired state |
| Operator thiếu scope publish | 403 | Không gọi writer, audit denied |
| Hai operator publish cùng expected version | Một lệnh thắng, lệnh còn lại 409 | Tải state mới và review lại |
| DB commit thành công, publisher chết | Desired state/outbox vẫn tồn tại | Outbox worker gửi lại event |
| Event gửi lặp | Pod xử lý idempotent | Không tạo version/refresh side effect trùng |
| Event đến sai thứ tự | Pod bỏ qua version cũ | Reconcile desired version mới nhất |
| Một Pod refresh thất bại | Release `DEGRADED` | Retry/reconcile hoặc rollback theo policy |
| Backend v2 trả 5xx tăng đột biến | Route đã áp dụng nhưng traffic unhealthy | Trigger rollback threshold |
| Backend v2 DNS/service discovery lỗi | Smoke test fail | Không đánh dấu release ACTIVE |
| Rollback version conflict | 409 | Đọc active version mới và tạo rollback request mới |
| Audit store/outbox không ghi được | Không activate nếu audit bắt buộc | Fail closed, báo control-plane error |
| Gateway restart | Tải desired state mới nhất khi startup | So sánh applied/desired sau readiness |

### 21.1. Không retry publish một cách mù quáng

Publish có side effect. Nếu client timeout, chưa biết server đã commit hay chưa. Hãy:

1. Gửi lại cùng `Idempotency-Key`.
2. Đọc release status bằng release ID.
3. Kiểm tra desired version và observed state.
4. Chỉ tạo command mới nếu release trước chưa được ghi nhận.

Không gửi lặp `POST activate` với ID mới khi chưa kiểm tra trạng thái lệnh cũ.

### 21.2. Rollback trigger phải dựa trên số liệu

Ví dụ policy lab:

| Signal | Threshold ví dụ | Action |
| --- | --- | --- |
| Upstream 5xx | > 5% trong 5 phút với đủ request sample | Đánh dấu degraded và yêu cầu review/rollback |
| p95 latency | Tăng hơn 2 lần baseline trong 10 phút | Cảnh báo và đánh giá rollback |
| Gateway refresh | Một instance không applied sau 60 giây | Retry/reconcile; không đánh dấu fully active |
| Health probe | Backend v2 unhealthy liên tiếp 3 lần | Dừng rollout |

Các con số là **ngưỡng minh họa**, phải hiệu chỉnh theo traffic/SLO. Tránh tự rollback chỉ vì một request lỗi đơn lẻ hoặc sample quá nhỏ. Với route có side effects, cân nhắc data compatibility trước khi chuyển ngược.

## 22. Lệnh thực hành qua HTTP

Các lệnh dưới đây minh họa quy trình operator. Chạy trong lab/private environment với operator token test. Không ghi token thật vào shell history hoặc CI log.

### 22.1. Tạo candidate

~~~bash
curl --silent --show-error --fail-with-body \
  -X POST 'http://127.0.0.1:8080/internal/admin/route-releases' \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: change-2026-042' \
  -d '{
    "routeKey": "catalog-public",
    "serviceKey": "catalog-v2",
    "publicPrefix": "/api/catalog",
    "methods": ["GET", "HEAD"],
    "changeTicket": "CHG-2026-042",
    "reason": "Chuyen Catalog traffic sang backend v2"
  }'
~~~

Response mong đợi là một candidate `DRAFT` có release ID. Đây là ví dụ request, không phải output đã chạy.

### 22.2. Validate và approve

~~~bash
RELEASE_ID='rel-01JCATALOGV2'

curl --silent --show-error --fail-with-body \
  -X POST "http://127.0.0.1:8080/internal/admin/route-releases/$RELEASE_ID/validate" \
  -H "Authorization: Bearer $OPERATOR_TOKEN"

# Dùng token của approver có scope riêng.
curl --silent --show-error --fail-with-body \
  -X POST "http://127.0.0.1:8080/internal/admin/route-releases/$RELEASE_ID/approve" \
  -H "Authorization: Bearer $APPROVER_TOKEN" \
  -H 'If-Match: "12"'
~~~

### 22.3. Activate và kiểm tra trạng thái

~~~bash
curl --silent --show-error --fail-with-body \
  -X POST "http://127.0.0.1:8080/internal/admin/route-releases/$RELEASE_ID/activate" \
  -H "Authorization: Bearer $PUBLISH_TOKEN" \
  -H 'If-Match: "12"'

curl --silent --show-error \
  -H "Authorization: Bearer $READ_TOKEN" \
  'http://127.0.0.1:8080/internal/admin/routes/catalog-public/status'

curl --silent --show-error -i \
  'http://127.0.0.1:8080/api/catalog/items/42'
~~~

Chỉ coi release là `ACTIVE` khi desired/applied versions hội tụ theo policy và smoke request tới đúng backend.

### 22.4. Rollback

~~~bash
curl --silent --show-error --fail-with-body \
  -X POST 'http://127.0.0.1:8080/internal/admin/route-releases/rel-01JCATALOGV2/rollback' \
  -H "Authorization: Bearer $ROLLBACK_TOKEN" \
  -H 'If-Match: "13"' \
  -H 'Content-Type: application/json' \
  -d '{"reason":"Catalog v2 error rate exceeded approved threshold"}'
~~~

Endpoint rollback ở phần 7 là contract đề xuất; request body/header cụ thể cần khớp controller và release service của lab. Không giả định skeleton controller đã triển khai đầy đủ rollback endpoint.

## 23. Runbook phát hành và khôi phục

### Trước khi publish

1. Xác nhận change ticket, owner và thời gian phát hành.
2. Kiểm tra candidate spec hash và active version hiện tại.
3. Xác minh approver độc lập nếu policy yêu cầu.
4. Kiểm tra upstream health, capacity, service discovery và TLS.
5. Xác nhận route conflict, path rewrite, method, security, rate limit và observability.
6. Xác nhận snapshot version trước có thể khôi phục.
7. Xác nhận các Gateway instances đang healthy và có thể nhận refresh notification.

### Khi publish

1. Gửi activate với idempotency key và expected version.
2. Kiểm tra desired version và outbox event đã được ghi.
3. Theo dõi từng Gateway instance: applied version, refresh status và error code.
4. Gửi smoke request qua public route.
5. Theo dõi 4xx/5xx, latency, backend HITS và saturation.
6. Chỉ đánh dấu ACTIVE sau khi đạt convergence/observation policy.

### Khi phát hiện lỗi

1. Xác định lỗi route config, Gateway refresh, service discovery, backend hay security.
2. Đánh giá mức ảnh hưởng: tất cả instances hay một phần, toàn bộ clients hay cohort.
3. Dừng rollout hoặc giảm traffic theo chiến lược đã phê duyệt.
4. Tạo rollback release từ snapshot known-good, với expected version hiện tại.
5. Theo dõi refresh trên tất cả replicas và chạy smoke test.
6. Ghi audit outcome, nguyên nhân, người thực hiện và version sau rollback.
7. Giữ nguyên release lỗi để phân tích; không xóa audit/history.

### Sau rollback

- Xác nhận desired/applied versions đã hội tụ.
- Kiểm tra backend cũ còn healthy và đủ capacity.
- Kiểm tra client response/status/latency trở lại baseline.
- Mở incident/postmortem và lưu evidence không chứa secrets.
- Tạo candidate mới đã sửa lỗi nếu vẫn cần tiếp tục migration.

## 24. Ma trận nghiệm thu

| ID | Kịch bản | Kết quả bắt buộc |
| --- | --- | --- |
| R01 | Candidate với service key hợp lệ | Tạo DRAFT |
| R02 | Candidate với URI loopback/metadata | Bị từ chối, không ghi route |
| R03 | Candidate với service key ngoài allowlist | Validation fail |
| R04 | Candidate với path `/internal/admin` | Validation fail |
| R05 | Candidate có method DELETE | Validation fail theo lab policy |
| R06 | Operator không token | 401, backend route không bị ảnh hưởng |
| R07 | Operator thiếu write scope | 403, audit denied |
| R08 | Operator chỉ có write gọi activate | 403 |
| R09 | Candidate validate thành công | Spec hash được lưu |
| R10 | Spec thay đổi sau approval | Approval bị invalidated |
| R11 | Hai publish cùng expected version | Một thành công, một 409 |
| R12 | Idempotency key được gửi lại | Không tạo release trùng |
| R13 | RouteDefinition được lưu | Route repository chứa desired definition |
| R14 | Refresh local | Runtime route mới được nạp |
| R15 | Path request sau publish | Đi tới backend mới |
| R16 | StripPrefix | Backend nhận đúng path |
| R17 | Audit activate | Có actor, before/after hash, ticket, outcome |
| R18 | Pod nhận event lặp | Không áp dụng version lùi/trùng |
| R19 | Một Pod refresh fail | Release chuyển DEGRADED |
| R20 | Pod restart | Tải desired state mới nhất |
| R21 | Backend mới trả 5xx vượt threshold | Trigger review/rollback |
| R22 | Rollback với expected version đúng | Tạo version mới từ snapshot cũ |
| R23 | Rollback với expected version sai | 409, không ghi đè |
| R24 | Audit/outbox store lỗi | Không publish khi audit bắt buộc |
| R25 | Sau rollback | Tất cả instances và smoke test xác nhận backend cũ |

**Tiêu chí đạt:** Từng test có bằng chứng từ HTTP response, route store, audit log, backend stub hoặc per-instance observation. Không đánh dấu PASS chỉ dựa trên log “publish success”.

## 25. Ghép các thành phần thành một release flow

Các ví dụ ở trên là những thành phần độc lập. Application service cần nối chúng theo đúng thứ tự và không bỏ qua các trạng thái trung gian.

### 25.1. Create candidate

~~~text
createCandidate(request, actor, idempotencyKey):
  require actor has gateway.routes.write
  validate request schema
  validate routeKey, serviceKey, publicPrefix, methods
  reject arbitrary URI/filter/order values
  build RouteDefinition with approved factory
  calculate canonical spec hash
  store immutable DRAFT candidate
  append ROUTE_CANDIDATE_CREATED audit event
  return release ID and state
~~~

### 25.2. Validate và approve

~~~text
validate(releaseId, actor):
  release = store.load(releaseId)
  require release.state == DRAFT
  definition = routeFactory.build(release.spec)
  validate schema + policy + conflicts + runtime compatibility
  hash = canonicalHash(definition)
  store.markValidated(releaseId, hash)
  audit.append(ROUTE_VALIDATED, actor, releaseId, hash)

approve(releaseId, approver, expectedVersion):
  require approver has gateway.routes.approve
  require approver != creator when separation-of-duties is enabled
  store.approve(releaseId, approver, expectedVersion)
  audit.append(ROUTE_APPROVED, ...)
~~~

### 25.3. Activate và reconcile

~~~text
activate(releaseId, actor, expectedVersion):
  require actor has gateway.routes.publish
  require release.state == APPROVED
  transaction:
    snapshot current active route
    compare active version with expectedVersion
    persist immutable new version + desired state
    append activation audit event
    append refresh event to outbox
  return PUBLISHING

outbox publisher:
  deliver event to every Gateway instance
  retry delivery; consumers are idempotent

reconciler:
  compare desiredVersion with each appliedVersion
  run smoke test and health checks
  mark ACTIVE or DEGRADED
~~~

Pseudocode làm rõ các trách nhiệm; không được coi là một class Java đã compile. Tách transaction store khỏi việc chờ Gateway Pods refresh để tránh giữ lock/connection trong một thao tác mạng dài.

### 25.4. Trạng thái response của Admin API

| Operation | HTTP response gợi ý | Điều kiện |
| --- | --- | --- |
| Create candidate | 201 Created | Candidate mới được lưu |
| Duplicate idempotency key | 200/303 theo contract | Trả lại release đã tạo trước |
| Validation error | 422 Unprocessable Content | Payload hợp lệ về JSON nhưng vi phạm policy |
| Unauthorized | 401 | Token thiếu/không hợp lệ |
| Forbidden | 403 | Actor không có quyền |
| Version conflict | 409 Conflict hoặc 412 Precondition Failed | expectedVersion/If-Match không còn đúng |
| Activate accepted | 202 Accepted | Đã ghi desired state, đang chờ convergence |
| Fully active | 200 khi đọc status | Mọi điều kiện activation đã đạt |
| Rollback accepted | 202 Accepted | Rollback release đã được tạo và đang áp dụng |

Không trả 200 ACTIVE ngay khi chỉ mới enqueue event. HTTP status nên phản ánh rõ request đã được chấp nhận hay rollout đã hoàn tất.

## 26. Những phản mẫu cần tránh

| Phản mẫu | Rủi ro | Cách thay thế |
| --- | --- | --- |
| Admin gửi nguyên `RouteDefinition` | Có thể đặt URI/filter/order tùy ý | DTO nhỏ + server-side factory |
| Nhận URL upstream từ body | SSRF, truy cập metadata/loopback/internal hosts | Service key allowlist và egress policy |
| Chỉ validate URI scheme | DNS rebinding hoặc internal host vẫn có thể lọt | Approved service inventory, network controls |
| Chỉ ghi route trong `InMemoryRouteDefinitionRepository` | Mất route khi restart và drift giữa replicas | Durable route store/source of truth |
| Chỉ gọi `writer.save()` | Runtime cache có thể chưa refresh | Refresh event + observed-state check |
| Chỉ publish `RefreshRoutesEvent` ở một Pod | Các Pod khác không nhận event local | Event bus/outbox hoặc polling/reconciliation |
| Đánh dấu ACTIVE khi event đã gửi | Không chứng minh instance đã áp dụng | Per-instance applied version và smoke tests |
| Sửa version cũ khi rollback | Mất lịch sử và khó kiểm toán | Tạo version mới từ snapshot cũ |
| Retry POST publish bằng release ID mới | Có thể tạo nhiều releases | Idempotency key và đọc trạng thái |
| Không dùng optimistic locking | Hai operator ghi đè thay đổi nhau | If-Match/expectedVersion |
| Audit chỉ ghi thành công | Không biết ai đã thử thay đổi bị từ chối | Audit cả validation/security/publish failures |
| Lưu audit sau khi gửi event | Process crash có thể mất dấu vết | Transaction + outbox |
| Ghi raw headers/token vào audit | Lộ credentials và PII | Metadata allowlist, redact |
| Dùng Actuator route endpoint làm admin workflow | Thiếu approval, audit, policy và rollback | Control-plane API có lifecycle |
| Chỉ test route definition object | Không chứng minh runtime matching/proxy | HTTP integration test qua Gateway listener |
| Canary route nhưng không theo dõi metrics | Traffic có thể lỗi mà không phát hiện | Threshold, observation window, rollback |
| Xóa backend cũ ngay sau publish | Không còn target để rollback | Giữ compatibility window và capacity |
| Cho user data plane sửa route | Client có thể thay đổi traffic topology | Control plane riêng, quyền quản trị cao |

## 27. Checklist trước phát hành và tổng kết

### Checklist kỹ thuật

~~~text
[ ] Gateway runtime và Spring Boot/Spring Cloud BOM đã được khóa.
[ ] Route Admin API chỉ nằm trên private management network.
[ ] Operator token có issuer, audience, signature và scope đúng.
[ ] Quyền write/approve/publish/rollback được tách theo policy.
[ ] Candidate DTO không nhận URI/filter/order tùy ý.
[ ] Service key và public prefix nằm trong allowlist.
[ ] Route ID, path, method, order và filter đã qua validation.
[ ] Route conflict/overlap đã được kiểm tra với route inventory.
[ ] RouteDefinition được dựng bởi server-side factory.
[ ] Desired route state và audit được lưu bền vững.
[ ] Candidate spec bất biến sau approval và có canonical hash.
[ ] Publish dùng expectedVersion và idempotency key.
[ ] Refresh notification được phát sau commit qua outbox.
[ ] Mỗi Gateway instance có desired/applied version observation.
[ ] Pod restart có thể tải desired state mới nhất.
[ ] Route smoke test đi qua public path và tới đúng backend.
[ ] Metrics có route/version labels hữu hạn, không có PII/secrets.
[ ] Rollback tạo version mới từ immutable snapshot trước.
[ ] Failure injection bao gồm event retry, Pod refresh fail và backend 5xx.
[ ] Audit append-only có retention, backup và access control.
[ ] Có runbook, change ticket, owner và người phê duyệt.
[ ] Có điều kiện kết thúc rollback window trước khi xóa backend cũ.
~~~

### Tóm tắt bài thực hành

- **Dynamic routing** cho phép thay đổi route mà không restart Gateway, nhưng thay đổi runtime cần `RouteDefinitionWriter` và cơ chế refresh route cache.
- **Control plane** chịu trách nhiệm tạo candidate, validate, approve, publish, audit và rollback; **data plane** chỉ phục vụ request bằng route đã phát hành.
- **Validation phải giới hạn upstream** bằng service inventory/allowlist, không nhận URI tùy ý và không cho filter expression tự do. Điều này giảm nguy cơ SSRF và thay đổi traffic trái phép.
- **Audit trail** cần ghi actor, change ticket, route/version trước-sau, spec hash, outcome và correlation ID; không ghi token/secret.
- **Cluster refresh** cần event distribution, durable desired state, per-instance observation và reconciliation. `RefreshRoutesEvent` trong một JVM không tự cập nhật mọi Pod.
- **Rollback là một release mới** khôi phục snapshot known-good, có optimistic locking và audit; không xóa lịch sử version lỗi.
- **Kiểm thử phải đi qua HTTP thật**, xác nhận route, backend, status, metrics, audit và behavior sau rollback.

Khi quy trình hoàn tất, đội vận hành có thể trả lời rõ: **ai đã phát hành route nào, dựa trên change ticket nào, Gateway instances nào đã áp dụng, traffic có khỏe không và có thể khôi phục về phiên bản nào**. Đó là tiêu chí của một quy trình phát hành tuyến động có kiểm soát trong **SPRING_CLOUD_GATEWAY**.

### Tài liệu tham khảo để đối chiếu phiên bản

- **Spring Cloud Gateway Reference — RouteDefinition, RouteDefinitionWriter, route refresh và Actuator:** https://docs.spring.io/spring-cloud-gateway/reference/
- **Spring Cloud Gateway — Route Predicate Factories và GatewayFilter Factories:** https://docs.spring.io/spring-cloud-gateway/reference/
- **Spring Security Reactive OAuth2 Resource Server:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- **Spring Boot Actuator:** https://docs.spring.io/spring-boot/reference/actuator/
- **OWASP SSRF Prevention Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

Các ví dụ Java/YAML là lab WebFlux minh họa; cần đối chiếu API với BOM thực tế và chạy integration tests trong môi trường phù hợp. Bài chưa thay cho Content QA chuyên môn STEP 6.
