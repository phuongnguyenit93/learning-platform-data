# Bảo vệ URI đích, biểu thức và tham số của cấu hình động trong Spring Cloud Gateway

Trong một kiến trúc microservices, **API Gateway** có thể thay đổi route mà không phải triển khai lại mã nguồn. Khả năng ấy hữu ích khi đưa service mới vào hoạt động, chuyển hướng lưu lượng hay quản lý hàng trăm API; nhưng nó đồng thời biến cấu hình route thành **đầu vào có thể điều khiển mạng, filter chain và chính sách truy cập**.

Một thao tác tạo route từ API quản trị tưởng như đơn giản có thể:

- Đổi `uri` sang một địa chỉ không được phép, khiến Gateway gọi dịch vụ quản trị, host nội bộ hoặc địa chỉ metadata cloud (**SSRF**).
- Chèn biểu thức, regex hoặc tham số của GatewayFilter để đổi đường dẫn, header, retry budget hay fallback đích.
- Tạo predicate quá rộng và `order` ưu tiên cao, khiến route mới **chiếm traffic** của route đang được bảo vệ.

Bài học thuộc chương **Tuyến động**, tập trung vào **bảo vệ URI đích, biểu thức và tham số của cấu hình động** cho **SPRING_CLOUD_GATEWAY**. Nội dung kết hợp route predicates, filter chain, biến đổi path/header, service discovery, Spring Security, rate limiting, circuit breaker, retry, TLS và observability để tổ chức quyền thay đổi cấu hình mà không đánh mất ranh giới bảo mật.

> **Phạm vi:** Các ví dụ hướng đến **Spring Cloud Gateway Server WebFlux**. Namespace cấu hình, tên starter, API Actuator và chi tiết xử lý có thể thay đổi theo Spring Boot/Spring Cloud release train. Gateway Server MVC có mô hình khác. Tên service, hostname, policy và phiên bản bên dưới đều là **minh họa**, không phải policy production dùng được ngay.

## 1. RouteDefinition động là cấu hình có quyền thực thi

Ở Gateway Server WebFlux, một `RouteDefinition` mô tả tuyến bằng các thành phần như sau:

| Trường | Ví dụ | Tác động khi bị chỉnh sửa |
|---|---|---|
| `id` | `managed-public-catalog` | Định danh dùng để cập nhật, xóa và quan sát |
| `uri` | `lb://catalog-service` | Chọn **đích outbound** |
| `predicates` | `Path=/api/public/catalog/**` | Chọn **những request được đưa vào route** |
| `filters` | `StripPrefix=2` | Biến đổi request/response, áp giới hạn hoặc fallback |
| `order` | `1000` | Thứ tự ưu tiên khi nhiều routes match |
| `metadata` | Timeout, thông tin tùy runtime | Có thể ảnh hưởng thời gian chờ/quan sát |

Một cấu hình YAML tĩnh thường được review và triển khai cùng release ứng dụng. Với route động, những trường tương tự có thể đến từ database, portal, một API quản trị, GitOps hoặc service registry. **Mức độ nguy hiểm phụ thuộc quyền của nguồn dữ liệu**, không phụ thuộc việc route được lưu trong YAML hay JSON.

### Thành phần trong vòng đời route

- `RouteDefinitionLocator` cung cấp các route definitions.
- `RouteDefinitionWriter` biểu diễn thao tác lưu/xóa route definitions.
- `RouteDefinitionRepository` là một loại nguồn route có cả khả năng đọc và ghi; cách persist tùy implementation.
- Các thành phần của Gateway chuyển `RouteDefinition` thành `Route` runtime và khởi tạo predicate/filter.
- Các route runtime có thể được cache để không đọc nguồn cấu hình trong từng request.
- `RefreshRoutesEvent` và cơ chế refresh giúp kích hoạt tải lại, nhưng **không phải giao thức commit phân tán trên mọi Gateway instance**.

~~~mermaid
flowchart TD
    C["Người quản trị / control plane"] --> AU["Authentication + authorization"]
    AU --> CMD["Lệnh cấp cao: resource, targetCode, policyId"]
    CMD --> V["Validate + allowlist + route conflict checks"]
    V --> D{"Được duyệt?"}
    D -->|Không| NO["Reject + audit"]
    D -->|Có| P["Lưu snapshot/revision"]
    P --> RF["Refresh / rollout từng node"]
    RF --> RT["Gateway runtime routes"]
    RT --> TRAFFIC["Match predicate + filters + outbound routing"]
    TRAFFIC --> MON["Metrics + rollback readiness"]
~~~

**Quy tắc nền tảng:** Không cho người dùng self-service gửi nguyên một `RouteDefinition` với `uri`, `predicates`, `filters` và `order` tùy ý rồi lưu trực tiếp.

## 2. Threat model cho API cập nhật route

Không phải ai có tài khoản trong portal cũng có quyền điều khiển toàn bộ Gateway. Nên tách các năng lực: **xem**, **đề xuất**, **phê duyệt**, **publish**, **rollback**, **xóa** và **quản lý allowlist đích**.

| Mối đe dọa | Ví dụ | Hậu quả | Kiểm soát |
|---|---|---|---|
| SSRF | Chọn URI nội bộ/localhost | Đọc/gọi endpoint không được phép | Đích được duyệt + network egress policy |
| Chiếm route | `Path=/**` với order rất ưu tiên | Lấy traffic của API khác | Kiểm tra prefix/order/overlap |
| Sai namespace tenant | Sửa route của tenant khác | Gián đoạn hoặc lộ dữ liệu chéo tenant | RBAC/ABAC và ownership |
| Expression abuse | Raw SpEL/Bean reference | Tham chiếu thành phần ngoài hợp đồng | Không nhận expression thô |
| Header forgery | Chèn `X-Authenticated-User` hoặc xóa auth header | Mạo danh, làm sai hợp đồng danh tính | Allowlist filters/headers |
| Regex DoS | Pattern có backtracking lớn | CPU/latency tăng đột biến | Cấm regex tự do, giới hạn mẫu |
| Retry storm | `retries` và timeout quá lớn | Nhân tải backend | Policy budget có giới hạn |
| Unsafe cache | Cache API cá nhân hóa | Lộ dữ liệu người dùng | Policy mặc định không cache |
| Config drift | Chỉ một số nodes nhận route mới | Routing/security không nhất quán | Versioned rollout + reconciliation |

**Cần phân quyền trên chính route resource**, không chỉ trên HTTP method `PUT` hoặc `DELETE`. Biết route ID không đồng nghĩa có quyền sửa route ấy.

## 3. URI đích: cho phép theo danh sách, không theo ý muốn client

Trường `uri` quyết định Gateway sẽ gửi outbound request đi đâu. Đối với portal tạo route cho một nhóm dịch vụ đã được đăng ký, mẫu tốt là cho chọn một **targetCode** thuộc tập được duyệt rồi ánh xạ server-side sang URI.

| URI được yêu cầu | Mức độ tin cậy | Chính sách ví dụ |
|---|---|---|
| `lb://catalog-service` | Hợp lệ nếu service ID được phê duyệt | Cho phép qua mapping |
| `lb://internal-admin` | Có thể có trong registry nhưng không được public | Từ chối |
| `https://partner.example.test` | Đối tác ngoài có hợp đồng riêng | Chỉ cho phép qua kiểm soát dedicated |
| `http://127.0.0.1:8080` | Loopback | Từ chối trong self-service |
| `http://169.254.169.254` | Link-local, liên quan metadata ở một số hạ tầng | Từ chối |
| `http://10.0.0.5` | IP private bất kỳ | Từ chối nếu không nằm trong contract |
| `forward:/actuator/gateway/routes` | Forward vào handler nội bộ | Từ chối cho route self-service |
| `ws://...` / `wss://...` | WebSocket | Chỉ theo policy riêng |
| URI có userinfo, fragment hoặc host mơ hồ | Dễ vượt giả định validator | Từ chối nếu schema không hỗ trợ |

**Đây là chính sách bảo mật đề xuất, không phải danh sách toàn bộ scheme Gateway hỗ trợ.** Runtime có thể hỗ trợ `lb`, `http`, `https`, `ws`, `wss`, `forward` hoặc scheme khác tùy phiên bản. Một scheme được hỗ trợ kỹ thuật **không mặc định được phép** trong API quản trị route.

### Đầu vào tốt hơn: không có trường URI

Không nên nhận:

~~~json
{
  "id": "anything",
  "uri": "http://arbitrary-host:8080",
  "predicates": ["Path=/**"],
  "filters": ["..."]
}
~~~

Nên nhận lệnh có schema hẹp:

~~~json
{
  "resource": "catalog",
  "targetCode": "catalog",
  "exposure": "PUBLIC_READ_ONLY"
}
~~~

Server tạo mapping:

~~~text
targetCode=catalog  -> lb://catalog-service
targetCode=articles -> lb://article-service
~~~

Trong ứng dụng thật, mapping còn cần **owner, environment, authentication policy, allowed public prefixes và quyền sử dụng**. `targetCode` là mã trong danh mục platform, **không phải một tên service client có thể tự chọn**.

### URI parse thành công không đồng nghĩa an toàn

`URI.create(input)` xác minh cấu trúc URI cơ bản; nó **không chứng minh** scheme an toàn, domain thuộc quyền kiểm soát, DNS sẽ trỏ tới đâu, outbound network có bị vượt hay endpoint có chứa bí mật. Validation bằng regex trên chuỗi URI dễ bỏ sót canonicalization, IDN, userinfo, port hoặc trường hợp tên miền gần giống.

**Ưu tiên URL/URI được dựng sẵn từ danh mục đích**; nếu nghiệp vụ buộc cho đăng ký HTTPS host, phải có quy trình xác nhận ownership và lớp network egress độc lập.

## 4. Ngăn SSRF bằng nhiều lớp kiểm tra

Một host nằm trong allowlist lúc lưu route vẫn có thể resolve sang địa chỉ khác khi Gateway xử lý traffic. Đặc biệt cần đề phòng **DNS rebinding, CNAME thay đổi, IPv4/IPv6, loopback và địa chỉ link-local/private không thuộc quyền truy cập được phê duyệt**.

### Quy trình bảo vệ đích HTTP(S)

1. Parse URI bằng thư viện chuẩn và kiểm tra `scheme`, hostname, port, userinfo, fragment.
2. Chuẩn hóa hostname theo quy tắc cụ thể; không so sánh suffix thô kiểu “chuỗi kết thúc bằng example.test” mà bỏ qua ranh giới nhãn.
3. Allowlist **hostname + port + scheme cụ thể** đã được duyệt, không chỉ allowlist một suffix rộng.
4. Xác minh DNS và IP thực được kết nối theo network policy; đề phòng thời điểm resolve khác lúc validate.
5. Dùng egress firewall, Kubernetes NetworkPolicy, proxy có ACL hoặc security groups để Gateway **không thể** gọi đích cấm dù application validation bị lỗi.
6. Với HTTPS, xác minh certificate chain, hostname/SNI và TLS trust đúng hợp đồng; không dùng trust-all client.
7. Rà soát redirect/proxy/filter custom: không giả định mọi HTTP client sẽ hoặc sẽ không theo `Location` ở mọi đường đi.
8. Audit targetCode đã duyệt và đích thực tế ở mức phù hợp, không log raw token hoặc query nhạy cảm.

**Private IP không có nghĩa được tin cậy.** Máy nội bộ có thể chạy database, actuator, metadata service, admin UI và các workload ngoài quyền truy cập của người đăng ký route.

### URI `lb://` và service discovery

`lb://catalog-service` giới hạn routing bằng service ID, nhưng registry/DiscoveryClient có thể cung cấp **các instance host/port khác nhau theo thời gian**. Muốn bảo đảm an toàn:

- Chỉ những service ID được duyệt mới được đưa vào public route.
- Việc đăng ký instance vào registry phải được kiểm soát.
- Egress/network/TLS policy vẫn phải bảo vệ địa chỉ do load balancer chọn.
- Health/discovery state cần được quan sát; “có trong registry” không có nghĩa “được phép public”.
- Không cho người tạo route chọn arbitrary service ID để thử các dịch vụ nội bộ.

## 5. Predicates là quyền chọn traffic

Một `Path` quá rộng có thể chiếm requests hợp pháp của những route khác, kể cả khi URI đích đã nằm trong allowlist.

~~~yaml
# Không cho phép người dùng tự phục vụ tạo route này.
id: overly-broad
uri: lb://catalog-service
order: -999
predicates:
  - Path=/**
~~~

Cần kiểm soát **đồng thời** predicate và `order`, không chỉ validate từng chuỗi một.

| Trường/predicate | Rủi ro | Chính sách phù hợp |
|---|---|---|
| `Path` | `/**`, chiếm `/api/admin/**` | Platform cấp prefix và tạo pattern |
| `Host` | Chiếm domain của tenant khác | Xác minh quyền sở hữu host |
| `Method` | Expose POST/PUT/DELETE ngoài ý muốn | Chỉ method đúng exposure policy |
| `Header` / `Cookie` | Regex nặng, header client giả mạo | Không dùng làm nguồn chứng minh danh tính |
| `Query` | Regex/nhập nhằng query values | Chỉ mẫu được duyệt |
| `RemoteAddr` | Proxy/client IP không đáng tin | Trusted proxy policy |
| `After` / `Before` / `Between` | Mở route sai thời điểm | Timezone và expiry review |
| `order` | Override tuyến quan trọng | Giá trị do platform cấp |

### Route shadowing và namespace

Ví dụ:

~~~text
Route hiện hành:
  admin-api      Path=/api/admin/**       order=0
  public-api     Path=/api/public/**      order=100

Route được đề xuất:
  new-route      Path=/api/**             order=-100
~~~

Ở mô hình matching thông thường của Gateway, `order` thấp hơn được ưu tiên trước. Route mới có thể chiếm requests mà trước đó đi vào admin-api, tùy các predicates khác. Do đó phải đánh giá **tập route sau thay đổi**, bao gồm route từ YAML, repository và service discovery, chứ không chỉ kiểm tra một route độc lập.

**Không cho self-service API cấp phát** `/api/**`, `/actuator/**`, `/internal/**` hoặc prefix của tenant khác. Kiểm soát những biến thể case, percent-encoding, slash và path normalization khi Gateway/proxy/backend có thể hiểu khác nhau.

## 6. Filter name hợp lệ chưa chứng minh args an toàn

GatewayFilter Factories có khả năng thay đổi cả request/response và tải hệ thống.

| Factory hoặc nhóm filter | Rủi ro nếu cho nhập args tự do |
|---|---|
| `SetRequestHeader`, `AddRequestHeader` | Gắn danh tính/role/Host giả, thay header tin cậy |
| `RemoveRequestHeader` | Xóa `Authorization` hoặc request metadata backend cần |
| `StripPrefix`, `SetPath`, `RewritePath` | Chuyển public path đến endpoint backend nhạy cảm |
| `RequestRateLimiter` | Dùng KeyResolver tùy ý, quota quá rộng hoặc bị bypass |
| `Retry` | Nhân outbound attempts, replay POST không idempotent |
| `CircuitBreaker` | Fallback URI/handler ngoài danh sách cho phép |
| `FallbackHeaders` | Chuyển raw exception messages tới nơi không đáng tin |
| `LocalResponseCache` | Cache response riêng tư/tenant-sensitive |
| `SetResponseHeader`, `RemoveResponseHeader` | Sửa CORS, security hoặc cache headers trái policy |
| Custom factory | Script, query, network call hoặc buffer body theo args không kiểm soát |

**Cần allowlist cả tên filter lẫn schema tham số của filter.** Nếu chính sách đã cho phép `StripPrefix` với số 2 cố định thì người dùng không nên được đổi tùy ý thành 10. Nếu rate-limit policy dùng `KeyResolver` theo người dùng đã xác thực, người dùng không thể thay nó bằng raw IP hay một Bean reference không được duyệt.

### Regex có thể trở thành lỗi bảo mật và hiệu năng

Một số predicates và filters cho phép regex, ví dụ `Header`, `Query` hoặc `RewritePath`. Một biểu thức có nested quantifiers phức tạp khi xử lý input dài có thể gây **catastrophic backtracking** và CPU spike.

Để expose `/api/public/catalog/**`, cấu hình do platform tạo thường đơn giản hơn:

~~~yaml
predicates:
  - Path=/api/public/catalog/**
filters:
  - StripPrefix=2
~~~

Nếu thật sự cần regex động, phải quản trị độ dài, cú pháp, các nhóm ký tự, tập trường được match và chạy fuzz/performance tests. **Compile thành công không chứng minh regex an toàn dưới traffic độc hại.**

## 7. SpEL, Bean references và các biểu thức cấu hình

Một số cấu hình Gateway dùng **Spring Expression Language (SpEL)**. Ví dụ `RequestRateLimiter` ở những dòng Server WebFlux hỗ trợ tham chiếu một Bean `KeyResolver`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-limited
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
          filters:
            - name: RequestRateLimiter
              args:
                key-resolver: "#{@userKeyResolver}"
                redis-rate-limiter.replenishRate: 10
                redis-rate-limiter.burstCapacity: 20
~~~

Biểu thức `#{@userKeyResolver}` hợp lý khi được developer/ops kiểm soát. Nhưng nếu người đăng ký route có thể đưa **expression text bất kỳ**, họ có khả năng cố truy cập các Bean hoặc hành vi khác ngoài hợp đồng, tùy evaluation context.

**Không khẳng định mọi SpEL input đều là remote-code execution.** Mức độ ảnh hưởng phụ thuộc nơi đánh giá biểu thức, cơ chế giới hạn và môi trường ứng dụng. Tuy nhiên, nhu cầu bảo mật đủ rõ: **không nhận SpEL/Bean reference thô từ API self-service**.

### Thay expression bằng policy ID

Không nhận:

~~~json
{
  "rateLimiter": {
    "keyResolverExpression": "untrusted-expression",
    "replenishRate": 100000
  }
}
~~~

Nên nhận:

~~~json
{
  "rateLimitPolicy": "orders-user-read"
}
~~~

Server map `orders-user-read` sang một policy **đã duyệt**, gồm resolver, rate, burst, empty-key policy và các tham số filter an toàn. Tương tự, với `discovery.locator.include-expression`, regex, header templates hay tham số custom factories, **biên dịch từ schema giới hạn** thay vì lưu expression do người dùng tự nhập.

## 8. API quản trị nên nhận lệnh cấp cao

Giả sử platform chỉ cho phép đăng ký hai nhóm public-read API:

- `catalog` → `lb://catalog-service`;
- `articles` → `lb://article-service`.

Payload self-service:

~~~json
{
  "resource": "catalog",
  "targetCode": "catalog"
}
~~~

Những kiểm soát phía server:

1. Caller được xác thực với identity quản trị đáng tin.
2. Caller có quyền tạo route thuộc owner/environment tương ứng.
3. `resource` thuộc charset/length hẹp và prefix đã được phân quyền.
4. `targetCode` phải là khóa trong mapping **do server sở hữu**.
5. Route ID được tạo server-side, có namespace không trùng route được bảo vệ.
6. Path, Method, `order` và filters được sinh từ policy.
7. Conflict detection xét cả routes đã có và các URL quản trị.
8. Save/publish có revision, audit, dry-run/canary khi cần.

### Ví dụ Java: compile RouteDefinition đã ràng buộc

Đây là đoạn mẫu theo API thường gặp của Gateway Server WebFlux, **không phải toàn bộ hệ thống quản trị production**. Nó chưa triển khai authorization, optimistic locking và phân phối route nhiều nodes.

~~~java
package example.gateway.dynamic;

import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

import org.springframework.cloud.gateway.filter.FilterDefinition;
import org.springframework.cloud.gateway.handler.predicate.PredicateDefinition;
import org.springframework.cloud.gateway.route.RouteDefinition;

public final class SafeRouteCompiler {

    private static final Pattern RESOURCE =
        Pattern.compile("[a-z][a-z0-9-]{0,31}");

    private static final Map<String, URI> ALLOWED_TARGETS = Map.of(
        "catalog", URI.create("lb://catalog-service"),
        "articles", URI.create("lb://article-service")
    );

    public record RouteCommand(String resource, String targetCode) {}

    public RouteDefinition compile(RouteCommand input) {
        if (input == null || input.resource() == null ||
            input.targetCode() == null ||
            !RESOURCE.matcher(input.resource()).matches()) {
            throw new IllegalArgumentException("Invalid route command");
        }

        URI target = ALLOWED_TARGETS.get(input.targetCode());
        if (target == null) {
            throw new IllegalArgumentException("Target is not approved");
        }

        if (!input.resource().equals(input.targetCode())) {
            throw new IllegalArgumentException("Resource/target mismatch");
        }

        RouteDefinition route = new RouteDefinition();
        route.setId("managed-public-" + input.resource());
        route.setUri(target);
        route.setOrder(1000); // Platform chọn, không do client chọn.
        route.setPredicates(List.of(
            new PredicateDefinition(
                "Path=/api/public/" + input.resource() + "/**"),
            new PredicateDefinition("Method=GET,HEAD")
        ));
        route.setFilters(List.of(
            new FilterDefinition("StripPrefix=2")
        ));
        return route;
    }
}
~~~

### Vì sao giới hạn này hữu ích?

- Không có `uri` tùy ý, nên caller không thể trực tiếp yêu cầu Gateway truy cập localhost hoặc `forward:/actuator`.
- Resource không có slash, wildcard, kí tự regex hoặc ký tự điều khiển.
- Route chỉ nhận `GET`/`HEAD` theo exposure policy đọc công khai.
- Không có raw filter, SpEL, regex hoặc `order` từ client.
- Route ID có namespace `managed-public-` và filter path do platform tạo.
- URI là đối tượng được lấy từ allowlist, không parse từ chuỗi do caller cung cấp.

**Không dừng ở compiler:** Ngoài logic trên cần RBAC/ABAC, kiểm tra route shadowing, ownership, giới hạn số routes, audit, và kiểm thử đường đi backend. Đặc biệt, `StripPrefix=2` biến `/api/public/catalog/items/42` thành `/catalog/items/42`; backend phải tự có authorization nếu phục vụ dữ liệu khác mức public.

## 9. Lưu route và refresh theo pipeline reactive

Sau khi compile thành công, một service quản trị có thể dùng `RouteDefinitionWriter` để lưu route và phát `RefreshRoutesEvent` khi thao tác hoàn thành:

~~~java
package example.gateway.dynamic;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionWriter;
import reactor.core.publisher.Mono;

public final class RoutePublisher {

    private final RouteDefinitionWriter writer;
    private final ApplicationEventPublisher events;
    private final SafeRouteCompiler compiler;

    public RoutePublisher(
            RouteDefinitionWriter writer,
            ApplicationEventPublisher events,
            SafeRouteCompiler compiler) {
        this.writer = writer;
        this.events = events;
        this.compiler = compiler;
    }

    public Mono<Void> upsert(SafeRouteCompiler.RouteCommand command) {
        // Chỉ gọi khi authZ, ownership và conflict checks đã PASS.
        RouteDefinition candidate = compiler.compile(command);

        return writer.save(Mono.just(candidate))
            .then(Mono.fromRunnable(() ->
                events.publishEvent(new RefreshRoutesEvent(this))));
    }
}
~~~

**Chú ý:** `RouteDefinitionWriter` là interface; application phải có **implementation phù hợp** (memory/repository khác). Một bản lưu trong tiến trình không tự trở thành persistent store hoặc trạng thái chung cho nhiều Gateway instances.

Dùng composition reactive như `then(...)` giúp phát refresh event **sau khi publisher của save hoàn thành**. Không tự `subscribe()` ở giữa rồi phản hồi HTTP thành công quá sớm.

### Refresh không phải distributed transaction

Sau khi save và phát event, vẫn cần hỏi:

- Repository có lưu bền vững không?
- Node nào đã nhận version mới? Có node nào lỗi refresh/binding?
- Hai admin cùng sửa route ID thì có revision/optimistic locking không?
- Một Gateway instance mới khởi động có lấy đúng snapshot không?
- Khi route mới tạo lỗi 401/403/404/5xx, có rollback về snapshot cũ không?
- Route bị thu hồi có biến mất khỏi cache trên mọi node không?

`RefreshRoutesEvent` chỉ là một tín hiệu vòng đời refresh; **không cam kết tất cả node nhìn cùng version ở cùng thời điểm**.

## 10. Actuator Gateway là control plane cần bảo vệ

Tùy phiên bản và cấu hình, Spring Cloud Gateway cung cấp khả năng xem, refresh và có thể quản lý routes qua những endpoint thuộc nhóm `/actuator/gateway/**`. Chỉ bật write endpoints khi thật sự cần và với **quyền quản trị riêng**.

### Chính sách tối thiểu

- Không expose mutation endpoints ra Internet công cộng.
- Sử dụng private management network/VPN hoặc identity-aware proxy phù hợp.
- Bảo vệ bằng **Spring Security WebFlux** và kiểm soát role/scope cho từng năng lực.
- Tách quyền **read/inspect**, **refresh**, **create/update/delete**, **approve**.
- Nếu Actuator chạy cổng/application context riêng, bảo vệ đúng ngữ cảnh đó.
- Giới hạn request size, rate, audit, CSRF/session nếu giao diện quản trị dùng cookie.
- Không trả thông tin credentials, URI nhạy cảm hoặc raw config qua response/log cho đối tượng không được phép.
- Xác nhận cách expose/read-write của **đúng phiên bản**; không mặc định endpoint, verb hoặc property là bất biến.

Ví dụ cấu hình tối thiểu tránh expose route management trong một deployment cơ bản:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Cần rà các cấu hình override và management port thật; ví dụ không thay thế security rules hoặc network ACL. Không bật `include: "*"` chỉ để thuận tiện debug.

**Route ID biết được từ endpoint liệt kê không cấp quyền xóa route.** Mọi thao tác cập nhật/xóa đều phải kiểm tra owner, protected flag và revision.

## 11. Kiểm tra schema trước và sau khi compile

Một hệ thống route động an toàn thường tách hai dạng dữ liệu:

1. **Command DTO:** chứa định danh nghiệp vụ, targetCode, policy ID, revision dự kiến.
2. **RouteDefinition đã biên dịch:** chứa URI/predicates/filters do platform tạo.

Ví dụ policy source mang tính minh họa, **không phải YAML schema mặc định của Gateway**:

~~~yaml
routePolicies:
  public-read:
    allowedResources: [catalog, articles]
    allowedMethods: [GET, HEAD]
    pathPrefix: /api/public/
    fixedFilters: [StripPrefix]
    stripPrefixCount: 2
    retryMax: 0
    cacheAllowed: false
    authorization: PUBLIC_READ_ONLY

  orders-user-read:
    allowedResources: [orders]
    allowedMethods: [GET]
    pathPrefix: /api/orders/
    fixedFilters: [StripPrefix, RequestRateLimiter]
    rateLimitPolicyId: orders-user-read
    cacheAllowed: false
    authorization: JWT_REQUIRED
~~~

`authorization: JWT_REQUIRED` trong YAML minh họa **không tự cấu hình Spring Security**. Platform phải ánh xạ chính sách vào security và routing thực tế, đồng thời kiểm chứng backend authZ.

| Trước compile | Sau compile |
|---|---|
| Từ chối field lạ, raw URI, raw filters | URI/schema thuộc allowlist |
| Kiểm tra kích thước, charset và độ sâu payload | Route ID không đụng reserved IDs |
| Kiểm tra owner/tenant/environment | Path/Host/Method/Order không shadow routes |
| Kiểm tra policy ID có quyền chọn | Filter names/args đúng policy |
| Kiểm tra revision mong muốn | Không xóa/đổi header bảo mật ngoài hợp đồng |
| Không nhận SpEL/regex tùy ý | Không có route quá rộng, timeout/budget vô hạn |
| Audit người yêu cầu và lý do | Có diff/snapshot trước publish |

**Không âm thầm bỏ qua unknown fields** theo cách làm hai client hiểu schema khác nhau. Thiết kế rõ behavior cho null, duplicate JSON fields, payload quá lớn, nested data và malformed encoding.

## 12. Route shadowing: phải kiểm tra toàn bộ tập cấu hình

Một candidate route có thể hợp lệ khi xét riêng nhưng xung đột khi kết hợp với route đang hoạt động.

~~~text
Existing:
  admin-api:  Path=/api/admin/**,  order=0
  public:     Path=/api/public/**, order=100

Proposed:
  new-route:  Path=/api/**,        order=-100
~~~

Candidate ở đây có thể match cả admin lẫn public và được xét ưu tiên hơn. **Allowlist URI không đủ để chặn traffic hijacking**.

Một pre-publish checker cần xem:

- Prefix đã cấp phát cho đội/tenant.
- Host/domain ownership và các wildcard hosts.
- Route order, method và các predicates khác.
- Reserved public/internal/actuator/security paths.
- Routes được sinh từ DiscoveryClient locator.
- Cách `RewritePath`/`StripPrefix` biến public path thành backend path.
- Paths có percent-encoding, dot segment, double slash và Unicode/case normalization.
- Những handler không phải Gateway route nhưng vẫn có thể nhận path.
- Default/global filters và các response/security policies.

**Phân tích tĩnh không dễ chứng minh toàn bộ regex/predicate interactions.** Bổ sung integration tests với URL đại diện, kể cả negative cases được chọn để phát hiện shadowing.

## 13. Spring Security và backend authorization vẫn độc lập

Một route mới không tự làm `SecurityWebFilterChain` mất tác dụng. Nhưng nó có thể đưa một backend hoặc path mới vào vùng URL đang `permitAll` vì security rule quá rộng. Do đó cần review **security policy trên public URL của Gateway** và **authorization nghiệp vụ ở backend**.

Ví dụ route public GET đến catalog-service chỉ hợp lệ nếu backend path `/catalog/items/42` thực sự không trả dữ liệu riêng tư. Đừng chỉ nhìn route predicate `Method=GET` rồi kết luận an toàn.

### Mối liên hệ các tính năng Gateway

| Cấu phần | Điều route động phải tôn trọng |
|---|---|
| Authentication/Authorization | Không giả mạo principal/role, không expose API private qua path public |
| RequestRateLimiter | Policy KeyResolver theo danh tính đã xác minh, empty-key/Redis error behavior |
| CircuitBreaker | Chỉ dùng breaker/fallbackUri được duyệt, không forward vào handler quản trị |
| Retry | Giới hạn attempts, backoff, timeout, idempotency và ngân sách tổng |
| LocalResponseCache | Không cache response user/tenant-sensitive, test TTL/Vary/correctness |
| LoadBalancer/DiscoveryClient | Service ID allowlist, instance registration ACL và health |
| TLS | Không cho tự tắt certificate/hostname verification |
| Headers | Không sửa `Authorization`/`Host`/`X-Authenticated-User` tùy ý |
| Observability | Route ID và revision để trace, không ghi raw secret vào logs |

### Retry/caching sau khi đổi URI

Nếu URI của route được cập nhật từ một backend công khai sang backend dữ liệu riêng tư, những filter cache/retry đã tồn tại có thể không còn an toàn. Xem thay đổi `uri` là **thay đổi hợp đồng bảo mật**, không chỉ thay đích TCP.

Local caches có thể giữ entries sau khi route refresh tùy implementation; cần chiến lược invalidation. Với retry, một request có thể tạo nhiều outbound attempts; yêu cầu budget và không replay side effects.

## 14. Rollout an toàn trên nhiều Gateway instances

~~~mermaid
flowchart LR
    CP["Control plane, approved snapshot v12"] --> STORE["Versioned route store"]
    STORE --> A["Gateway A: v12"]
    STORE --> B["Gateway B: v11"]
    STORE --> C["Gateway C: v12"]
    A --> DS["Downstream services"]
    B --> DS
    C --> DS
    MON["Reconciliation / monitoring"] -.-> A
    MON -.-> B
    MON -.-> C
~~~

Một yêu cầu cùng URL có thể gặp hành vi khác nhau nếu Gateway B chưa nhận revision mới. Nếu thay đổi route liên quan bảo mật, **partial rollout có thể khiến request vào node cũ đi theo policy cũ**.

### Trạng thái publish đề xuất

~~~text
DRAFT -> VALIDATED -> APPROVED -> PUBLISHED
                                  |
                                  +-> ACTIVE_ON_ALL_NODES
                                  +-> FAILED_ROLLOUT -> ROLLED_BACK
~~~

Đây là các trạng thái **do control plane đề xuất quản lý**, không phải các enum có sẵn trong `RouteDefinition`.

### Những bảo đảm nên có

1. Snapshot/version cho toàn bộ tập route.
2. Idempotent apply và revision/optimistic locking.
3. Mỗi node báo phiên bản đã tải và lỗi binding (nếu có).
4. Canary trước khi mở rộng rollout.
5. Rollback về snapshot đã được duyệt và xác minh.
6. Chính sách xử lý node stale khi bảo mật thay đổi.
7. Kiểm tra toàn bộ route conflicts và security invariants sau refresh.
8. Quota số route/filters và cleanup routes hết hiệu lực.

Không chỉ phát `RefreshRoutesEvent` rồi giả định một cluster đã thay đổi nguyên tử.

## 15. Bài thực hành: kiểm thử tuyến động an toàn

Giả sử môi trường lab có:

- Gateway Server WebFlux tại `http://localhost:8080`.
- Service catalog đã đăng ký với service ID `catalog-service` và backend nhận `GET /catalog/items/42`.
- Một control-plane service chỉ cho phép publish sau khi đã authZ.
- `SafeRouteCompiler` và `RoutePublisher` như phần 8–9.
- Một danh sách URLs quản trị/public cần giữ nguyên (negative-test fixtures).

### Bước 1 — Đề xuất route hợp lệ

~~~json
{
  "resource": "catalog",
  "targetCode": "catalog"
}
~~~

Kỳ vọng compiler sinh:

~~~text
id:         managed-public-catalog
uri:        lb://catalog-service
order:      1000
predicates: Path=/api/public/catalog/**, Method=GET,HEAD
filters:    StripPrefix=2
~~~

Sau publish/refresh, thử:

~~~bash
curl -i "http://localhost:8080/api/public/catalog/items/42"
~~~

Backend dự kiến nhận `/catalog/items/42` và response theo chính sách nghiệp vụ. Đồng thời kiểm tra version route của Gateway instance thực sự xử lý request.

### Bước 2 — Chứng minh không tạo arbitrary target

Ở unit test, gọi compiler với target code không thuộc allowlist:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class SafeRouteCompilerTest {

    private final SafeRouteCompiler compiler = new SafeRouteCompiler();

    @Test
    void allowsCuratedCatalogRoute() {
        var route = compiler.compile(
            new SafeRouteCompiler.RouteCommand("catalog", "catalog"));
        assertEquals("managed-public-catalog", route.getId());
        assertEquals("lb://catalog-service", route.getUri().toString());
    }

    @Test
    void rejectsPathInjection() {
        assertThrows(IllegalArgumentException.class,
            () -> compiler.compile(
                new SafeRouteCompiler.RouteCommand("../admin", "catalog")));
    }

    @Test
    void rejectsUnknownTarget() {
        assertThrows(IllegalArgumentException.class,
            () -> compiler.compile(
                new SafeRouteCompiler.RouteCommand("catalog", "internal-admin")));
    }
}
~~~

Test này chứng minh **compiler behavior**, chưa chứng minh authentication, service discovery, Gateway route binding hoặc runtime security. Cần integration tests riêng.

### Bước 3 — Bảng negative tests ở control plane

| Thao tác/payload | Kỳ vọng |
|---|---|
| `resource=../admin` | Từ chối syntax |
| `resource=**` | Từ chối wildcard |
| `targetCode=internal-admin` | Từ chối target không được duyệt |
| Input thêm field `uri=http://127.0.0.1` | Từ chối field ngoài schema |
| Input thêm `filters` tùy ý | Từ chối field ngoài schema |
| Input thêm SpEL `#{@someBean}` | Từ chối expression thô |
| User tenant A sửa route tenant B | 403 từ control plane |
| User tự đổi `order=-999` | Từ chối/không có quyền chọn order |
| Cố tạo route với `Path=/**` | Từ chối policy |
| Cố dùng `forward:/actuator/...` | Không có raw URI field; reject |
| Trùng route ID protected | Không overwrite |
| Hai updates cùng revision cũ | Một thao tác phải bị conflict |
| Một node refresh fail | Không báo active toàn cluster |
| Token thiếu/hết hạn gọi management API | 401/403 theo policy |
| Public request đến `/actuator/**` | Không bị route động chiếm/cho phép |

### Bước 4 — Xác nhận security và filter semantics

Thực hiện các request:

~~~bash
# Chỉ đọc public catalog:
curl -i -X GET "http://localhost:8080/api/public/catalog/items/42"

# Không nên match route public-read-only này:
curl -i -X POST "http://localhost:8080/api/public/catalog/items/42"

# Protected paths không được publish bằng route mới:
curl -i "http://localhost:8080/api/admin/status"
curl -i "http://localhost:8080/actuator/gateway/routes"
~~~

Mã HTTP cuối cùng phụ thuộc security/router/Actuator configuration; **không kỳ vọng mọi POST hay management URL đều trả cùng một status cố định**. Điều cần chứng minh: chúng **không bị forward sai đến catalog-service và không mở quyền ngoài policy**.

### Bước 5 — Nhiều Gateway nodes và rollback

1. Publish route snapshot mới cho canary instance.
2. Gửi requests qua từng instance được định danh trong môi trường test.
3. Kiểm tra route revision, path, downstream target, 401/403 và các default filters.
4. Cố ý tạo một cấu hình bị validator từ chối; xác minh **không có node nào tải cấu hình không hợp lệ**.
5. Mô phỏng refresh/persist error; đảm bảo báo failed rollout và giữ hoặc khôi phục snapshot an toàn.
6. Thu hồi route, xác nhận nó không còn match trên mọi instance và cân nhắc cache invalidation.

Không thử những đích SSRF thật hoặc endpoints nhạy cảm trong môi trường production; dùng **fixtures được kiểm soát** để kiểm tra policy từ chối.

## 16. Troubleshooting theo lớp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| URI parse được nhưng bị deny | Target không trong allowlist/egress policy | Xác minh quyền target, không nới policy tùy tiện |
| Route save thành công nhưng không active | Chưa refresh hoặc node còn route cache cũ | Đối chiếu revision và refresh result |
| Một node route đúng, node khác sai | Partial rollout/config drift | Reconcile snapshots, canary hoặc rollback |
| Request đi sai service | Route shadowing, order/predicate chồng nhau | Kiểm tra effective routes và request matching |
| 401/403 sau publish | Spring Security không permit public path mới | Review chính sách; không mở `permitAll` toàn cục |
| 404 | Predicate không match hoặc path rewrite/backend endpoint sai | So sánh public path với downstream path |
| 503 từ `lb://` | Service ID không resolve, instance unhealthy | Kiểm tra registry và TLS/network |
| Filter/expression không resolve | Bean thiếu, factory/args sai phiên bản | Chỉ nhận policy đã duyệt; kiểm tra runtime |
| Latency tăng sau route mới | Regex ReDoS, retry, buffer body hoặc backend chậm | Tắt route, profile và kiểm tra budgets |
| Header identity biến mất | Dynamic filter xóa/thay header | Rollback và khôi phục header trust policy |
| User B thấy dữ liệu user A | Cache nhầm hoặc route tới backend sai | Tắt route/cache, xử lý incident bảo mật |
| Route mất sau restart | Repository in-memory hay source không đồng nhất | Bổ sung persistent source và reconciliation |
| Actuator bị gọi không kiểm soát | Endpoint expose sai/thiếu authZ | Chặn management network, audit và thu hồi quyền |
| Concurrent updates ghi đè nhau | Không có revision/optimistic locking | Serialize publish hoặc kiểm soát version |

### Sáu câu hỏi khoanh vùng

1. **Caller** có đúng quyền quản lý route/owner/environment không?
2. **DTO** có raw URI, filter, regex, expression hoặc field ngoài schema không?
3. **Compiled RouteDefinition** có thuộc policy và không shadow route khác không?
4. **Repository/refresh**: Gateway node nào đã tải revision nào?
5. **Runtime**: request thật match route, order và outbound target nào?
6. **Trust boundary**: Spring Security, backend authZ, egress, TLS và header policies có còn đúng không?

Không debug bằng cách bật public Actuator mutation endpoints hoặc tắt xác minh certificate.

## 17. Checklist trước khi triển khai

- [ ] Tôi coi RouteDefinition động là **cấu hình có quyền thực thi**, không phải CRUD thông thường.
- [ ] Tôi phân quyền xem, đề xuất, phê duyệt, publish, sửa, xóa và rollback theo owner/environment.
- [ ] Tôi không nhận raw RouteDefinition từ self-service caller.
- [ ] Tôi dùng command DTO/schema hẹp và mapping `targetCode` → URI đã duyệt ở server.
- [ ] Tôi giới hạn URI/scheme/host/port/service ID và kiểm soát DNS, TLS, egress policy.
- [ ] Tôi không cho route tự do gọi loopback, metadata, admin endpoints hoặc arbitrary `forward:`.
- [ ] Tôi quản lý registry và quyền đăng ký instance của `lb://`.
- [ ] Tôi cấp phát public prefix/host/method/order, không cho user tự chiếm namespace.
- [ ] Tôi kiểm tra route shadowing trên toàn bộ route set, kể cả discovery routes.
- [ ] Tôi không chấp nhận raw SpEL/Bean reference và raw regex do client tự nhập.
- [ ] Tôi allowlist cả tên filter **và** cấu trúc/giới hạn args.
- [ ] Tôi không cho filter giả mạo principal, role, tenant hoặc bỏ header bảo mật ngoài policy.
- [ ] Tôi kiểm soát Retry, CircuitBreaker, RateLimiter, caching và timeout theo policy.
- [ ] Tôi vẫn bảo vệ request bằng Spring Security và backend authorization độc lập.
- [ ] Tôi xác minh public path, rewritten path, host và các trường hợp encoded URL.
- [ ] Tôi có revision/ownership/concurrency checks và audit được redact.
- [ ] Tôi không xem RefreshRoutesEvent là cam kết cập nhật đồng bộ cả cluster.
- [ ] Tôi có canary, reconciliation, per-node active version và rollback.
- [ ] Tôi khóa management/Actuator API bằng network ACL và authentication/authorization.
- [ ] Tôi đã thử SSRF negative cases, route conflicts, config injection, header spoofing và lỗi refresh.
- [ ] Tôi theo dõi route change metrics, 401/403/429/5xx, downstream targets và bảo vệ log khỏi token/PII.
- [ ] Tôi có phương án dừng route nguy hiểm và xử lý cache khi phát hiện sự cố.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — RouteDefinition, GatewayFilter Factories, DiscoveryClient routes, Actuator, Server WebFlux và route configuration theo phiên bản.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — release train và hướng dẫn chọn tài liệu phù hợp.
- [Spring Framework WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — `ServerWebExchange`, request handling và reactive lifecycle.
- [Spring Security Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html) — bảo vệ control-plane HTTP endpoints bằng `SecurityWebFilterChain`.
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/) — quản lý exposure, security và access của management APIs.
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — allowlist, DNS, IP và network controls.
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) — validate input theo schema và allowlist.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — least privilege, ownership và deny-by-default.

**Ghi nhớ:** **URI đích, predicates, filters, biểu thức và tham số của tuyến động có thể thay đổi ranh giới bảo mật Gateway.** Đừng cho người dùng quản trị gửi cấu hình thực thi tùy ý: hãy nhận lệnh schema hẹp, ánh xạ URI và policy được duyệt, chặn SSRF bằng allowlist + egress controls, kiểm tra route conflicts/authorization, quản lý version và xác minh rollout trên từng node. **Một RouteDefinition hợp lệ về cú pháp chưa đủ điều kiện để public.**
