# Ma trận truy cập theo endpoint, danh tính, vai trò và thao tác

> **Chủ đề:** Bảo vệ endpoint — Spring Security fundamentals (Java 17+, Spring Security 6.x). Bài này hướng dẫn biến yêu cầu nghiệp vụ thành **ma trận phân quyền có thể kiểm thử**, triển khai lớp kiểm soát ở HTTP endpoint và ở cấp bản ghi/tác vụ; phân biệt rõ danh tính, role, authority, điều kiện sở hữu, tenant, trạng thái dữ liệu và hành động.

## 1. Ma trận truy cập là gì, giải quyết vấn đề nào?

**Access matrix (ma trận truy cập)** là bảng đặc tả: **ai** có thể thực hiện **hành động nào** trên **tài nguyên nào**, trong **điều kiện gì**, với **kết quả cho phép hay từ chối**. Khi áp dụng cho API, một quyết định cần xem đồng thời:

- **Endpoint:** HTTP method + path pattern, ví dụ `GET /api/orders/{id}` khác `PATCH /api/orders/{id}`. Query string, request body và route variable có thể mang dữ liệu nghiệp vụ cần kiểm tra tiếp.
- **Danh tính (identity/principal):** người dùng hoặc máy gọi API, đã xác thực hay chưa, có `userId` nào, thuộc `tenantId` nào, tài khoản còn hợp lệ không. Không coi chuỗi `userId` do client tự nhập là danh tính đáng tin.
- **Vai trò (role):** nhóm trách nhiệm như `MEMBER`, `REVIEWER`, `ADMIN`. Trong Spring Security, mặc định `hasRole("ADMIN")` đối chiếu authority `ROLE_ADMIN`.
- **Quyền cụ thể (authority/permission):** khả năng thực hiện thao tác, ví dụ `order:read`, `order:create`, `order:update`, `order:approve`. `hasAuthority("order:read")` so khớp chính xác chuỗi.
- **Thao tác (action):** `READ`, `CREATE`, `UPDATE`, `APPROVE`, `DELETE`; cùng một tài nguyên nhưng mỗi action có điều kiện khác nhau. Mapping HTTP verb là điểm bắt đầu, không phải toàn bộ ý nghĩa nghiệp vụ.
- **Ngữ cảnh/tài nguyên:** chủ sở hữu bản ghi, tenant, trạng thái `DRAFT`/`PENDING`/`APPROVED`, hạn mức, khóa dữ liệu, quan hệ ủy quyền hoặc quyền phê duyệt độc lập.
- **Quyết định:** `ALLOW` hoặc `DENY`, với **mặc định từ chối khi không khớp quy tắc**; nên định nghĩa cả lỗi thiếu dữ liệu, không tìm thấy tài nguyên và không thể tải policy.

Công thức tư duy:

```text
Decision = Policy(
    trusted identity,
    roles + authorities,
    HTTP method + route,
    business action,
    resource owner + tenant + state,
    relevant conditions
)

ALLOW chỉ khi tất cả điều kiện bắt buộc đều thỏa.
Không có quy tắc khớp hoặc không có đủ dữ liệu → DENY.
```

Ma trận giúp người thiết kế, người viết controller/service, người quản trị quyền và tester cùng đọc **một chính sách nghiệp vụ**. Nó tránh hai lỗi phổ biến: chỉ kiểm tra “đã đăng nhập” rồi cho sửa mọi bản ghi; hoặc khóa endpoint theo role nhưng quên rằng người thuộc role vẫn không được thao tác với dữ liệu tenant khác.

## 2. Phân biệt identity, role, authority và quyền trên đối tượng

| Khái niệm | Ví dụ | Ý nghĩa | Điều không nên suy ra |
|---|---|---|---|
| Identity | `alice`, `tenant=A` | Ai đang gọi request | Tham số `?user=alice` là identity |
| Authentication | `Authentication` hợp lệ | Có kết quả xác thực từ cơ chế tin cậy | Đã đăng nhập thì có mọi quyền |
| Role | `ROLE_REVIEWER` | Chức trách của actor | Reviewer được duyệt bất kỳ đơn nào |
| Authority | `order:approve` | Khả năng cụ thể | Có quyền này thì được duyệt đơn khác tenant |
| Ownership | `order.ownerId == alice.id` | Quan hệ với một bản ghi | Owner được làm mọi action |
| Tenant scope | `order.tenantId == principal.tenantId` | Ranh giới tổ chức | ADMIN mặc nhiên vượt mọi tenant |
| Resource state | `PENDING`, `DRAFT` | Điều kiện nghiệp vụ | Có quyền UPDATE thì sửa đơn đã duyệt |
| Action | `APPROVE`, `UPDATE` | Tác động mong muốn lên tài nguyên | `POST` nào cũng có nghĩa CREATE |

Role thường được ánh xạ thành một tập authority khi đăng nhập hoặc chuyển đổi token. Spring Security không tự hiểu mọi claim JWT là role/permission: cần thiết lập mapper/converter để tạo `GrantedAuthority` đúng quy ước. Với token resource server, scope có thể được ánh xạ thành authority kiểu `SCOPE_...`; **không giả định** claim `roles` hay `permissions` tự trở thành `ROLE_ADMIN` hoặc `order:read` nếu chưa cấu hình.

**RBAC (role-based access control)** giải quyết chính sách theo vai trò. **ABAC (attribute-based access control)** thêm thuộc tính như owner, tenant, trạng thái, giờ truy cập. Quyền trên một đối tượng cụ thể thường cần phối hợp cả hai: role/authority ở mức route, rồi kiểm tra owner/tenant/state ở service hoặc policy chuyên trách.

## 3. Kịch bản mẫu: hệ thống quản lý đơn đặt hàng nhiều tenant

Giả sử hệ thống quản lý order có hai tenant `A` và `B`. Mỗi request đã xác thực mang identity và tenant đáng tin từ user store/session hoặc token đã được xác minh. Role và authority của các actor được quy định như sau:

| Actor | Identity/tenant | Role | Authority |
|---|---|---|---|
| Khách chưa đăng nhập | `anonymous` | không có | không có |
| Alice | `alice / A` | `ROLE_MEMBER` | `order:read`, `order:create`, `order:update` |
| Bob | `bob / A` | `ROLE_MEMBER` | `order:read`, `order:create`, `order:update` |
| Ray | `ray / A` | `ROLE_REVIEWER` | `order:read`, `order:approve` |
| Ada | `ada / A` | `ROLE_ADMIN` | `order:read`, `order:create`, `order:update`, `order:approve`, `order:delete` |
| Mai | `mai / B` | `ROLE_MEMBER` | `order:read`, `order:create`, `order:update` |

**Đây là giả định nghiệp vụ của ví dụ**, không phải tập role Spring Security tự tạo. Định nghĩa thêm ba bản ghi:

| Order | Owner | Tenant | Trạng thái |
|---|---|---|---|
| `101` | `alice` | `A` | `DRAFT` |
| `102` | `bob` | `A` | `PENDING` |
| `201` | `mai` | `B` | `DRAFT` |

Chính sách ví dụ:

- Mọi người được `GET /public/ping` và `GET /api/catalog`.
- Thành viên có `order:read` được **xem đơn của chính mình** trong cùng tenant. Reviewer có `order:read` được xem các đơn cùng tenant để xử lý; admin cùng tenant được xem đơn theo quyền quản trị. Không truy cập dữ liệu tenant khác chỉ vì mang role ADMIN.
- Người có `order:create` được tạo đơn mới trong tenant của mình; backend phải **tự lấy owner/tenant từ identity**, không tin `ownerId`/`tenantId` trong JSON do client gửi.
- Thành viên sở hữu đơn hoặc admin cùng tenant có `order:update` được sửa khi đơn đang `DRAFT`. Sau khi chuyển `PENDING` thì không thể sửa qua action này.
- Reviewer hoặc admin cùng tenant, có `order:approve`, được phê duyệt order `PENDING`, **và không tự phê duyệt order do chính mình sở hữu**.
- Chỉ admin cùng tenant có `order:delete` được xóa order `DRAFT`; xóa đơn đã gửi/duyệt phải đi theo luồng khác nếu nghiệp vụ cần.
- Chỉ role `ADMIN` xem endpoint quản trị `GET /api/admin/audit`; kết quả truy vấn audit vẫn bị giới hạn tenant `A` của Ada trong ví dụ.
- Mọi endpoint/method ngoài danh sách bị từ chối theo `denyAll`.

## 4. Ma trận endpoint × hành động × điều kiện

Đây là **ma trận chính sách chuẩn** dùng để review và viết test. Cột “HTTP gate” là điều kiện cơ bản tại filter chain; cột “Business gate” phải kiểm tra ở service/policy khi có dữ liệu thật.

| HTTP endpoint | Action | HTTP gate | Business gate trước khi thực thi | Nếu không đạt |
|---|---|---|---|---|
| `GET /public/ping` | PUBLIC_READ | `permitAll` | Không có | Từ chối chỉ khi một cơ chế khác yêu cầu |
| `GET /api/catalog` | PUBLIC_READ | `permitAll` | Không có | Từ chối chỉ khi một cơ chế khác yêu cầu |
| `GET /api/orders/{id}` | READ | `order:read` | Cùng tenant; owner hoặc REVIEWER hoặc ADMIN | DENY |
| `POST /api/orders` | CREATE | `order:create` | Owner = caller; tenant = tenant của caller | DENY |
| `PATCH /api/orders/{id}` | UPDATE | `order:update` | Cùng tenant; `DRAFT`; owner hoặc ADMIN | DENY |
| `POST /api/orders/{id}/approve` | APPROVE | `order:approve` | Cùng tenant; `PENDING`; REVIEWER hoặc ADMIN; không tự duyệt | DENY |
| `DELETE /api/orders/{id}` | DELETE | `order:delete` | Cùng tenant; `DRAFT`; ADMIN | DENY |
| `GET /api/admin/audit` | AUDIT_READ | `ROLE_ADMIN` | Kết quả lọc theo tenant của caller | DENY |
| Các endpoint/method khác | UNKNOWN | `denyAll` | Không chạy nghiệp vụ | DENY |

**Quan trọng:** Với các dòng READ, UPDATE, APPROVE, DELETE, kiểm tra authority ở route **chưa đủ để ALLOW hoàn chỉnh**. Đến khi tải bản ghi và xác minh owner/tenant/state, service mới quyết định cho phép thực hiện. Việc không có dữ liệu để quyết định phải được xử lý có chủ đích; đừng mặc nhiên cho phép khi truy vấn owner/tenant gặp lỗi.

`POST /api/orders/{id}/approve` tuy dùng HTTP `POST` nhưng nghiệp vụ là **APPROVE**, không phải CREATE. Vì thế action nên lấy từ đặc tả route, không ánh xạ mù “POST = CREATE”.

## 5. Ma trận actor × tài nguyên × thao tác: kết quả kỳ vọng

Giả định token, authentication và các lớp bảo vệ khác đã hợp lệ; với request thay đổi trạng thái từ trình duyệt, CSRF token hợp lệ khi cấu hình yêu cầu. Bảng sau mô tả **kết quả phân quyền**, không cam kết mọi response HTTP đều trả 200.

| Actor | Request / order | Kết quả quyền | Vì sao |
|---|---|---|---|
| Anonymous | `GET /api/catalog` | ALLOW | Endpoint công khai |
| Anonymous | `GET /api/orders/101` | DENY | Chưa xác thực/không có `order:read` |
| Alice | `GET /api/orders/101` | ALLOW | Owner, tenant A, có `order:read` |
| Alice | `GET /api/orders/102` | DENY | Không phải owner, cũng không phải REVIEWER/ADMIN |
| Bob | `GET /api/orders/102` | ALLOW | Owner cùng tenant và có `order:read` |
| Ray | `GET /api/orders/102` | ALLOW | Reviewer cùng tenant với `order:read` |
| Ray | `PATCH /api/orders/102` | DENY | Không có `order:update`; đơn cũng không ở `DRAFT` |
| Alice | `PATCH /api/orders/101` | ALLOW | Owner, cùng tenant, `DRAFT`, có `order:update` |
| Alice | `PATCH /api/orders/102` | DENY | Không phải owner và order `PENDING` |
| Ray | `POST /api/orders/102/approve` | ALLOW | Reviewer cùng tenant, `PENDING`, không tự duyệt |
| Ray | `POST /api/orders/101/approve` | DENY | Chưa ở `PENDING` |
| Alice | `POST /api/orders/102/approve` | DENY | Không có quyền approve |
| Ada | `DELETE /api/orders/101` | ALLOW | ADMIN cùng tenant, có `order:delete`, đơn `DRAFT` |
| Ada | `DELETE /api/orders/102` | DENY | Đơn đã `PENDING` |
| Ada | `GET /api/orders/201` | DENY | ADMIN tenant A không được vượt tenant B |
| Mai | `GET /api/orders/201` | ALLOW | Owner, tenant B, có `order:read` |
| Ada | `GET /api/admin/audit` | ALLOW | ROLE_ADMIN, dữ liệu trả ra giới hạn tenant A |
| Alice | `GET /api/admin/audit` | DENY | Không có ROLE_ADMIN |
| Ada | `DELETE /api/catalog` | DENY | Method/endpoint không được khai báo |

Cùng một identity có thể được ALLOW cho `GET` nhưng DENY cho `PATCH` hoặc `APPROVE`. Cùng một role có thể được ALLOW với order 101 nhưng DENY với order 201 vì **tenant** khác. Các trường hợp âm tính (DENY) có ý nghĩa kiểm thử không kém các trường hợp ALLOW.

## 6. Chuyển ma trận thành quy tắc quyết định có thứ tự

Với mỗi request, nên tách hai “cửa”:

```text
1. Request → xác định security filter chain áp dụng
2. Authentication → dựng identity + GrantedAuthority tin cậy
3. HTTP rule → method + path có được vào action này không?
4. Nạp resource (nếu action cần bản ghi)
5. Resource policy → tenant + owner + role + permission + state
6. ALLOW → thực hiện nghiệp vụ; DENY → dừng
```

Nếu quy tắc yêu cầu **đồng thời** các điều kiện thì dùng logic AND:

```text
allowUpdate(actor, order) =
    actor đã xác thực
    AND actor có "order:update"
    AND actor.tenantId == order.tenantId
    AND order.status == DRAFT
    AND (actor.id == order.ownerId OR actor có ROLE_ADMIN)

allowApprove(actor, order) =
    actor đã xác thực
    AND actor có "order:approve"
    AND actor.tenantId == order.tenantId
    AND order.status == PENDING
    AND (ROLE_REVIEWER OR ROLE_ADMIN)
    AND actor.id != order.ownerId
```

Không nhầm điều kiện `(isOwner OR isAdmin)` thành `isOwner OR (isAdmin AND sameTenant)`. Cách sau có thể cho owner được cấp role/identity bất thường vượt ranh giới tenant. Đặt `sameTenant` bên ngoài nhóm OR để áp dụng cho **tất cả nhánh**.

Nếu có rule “ADMIN được bỏ qua tenant”, đó là quyền xuyên tổ chức có rủi ro cao; phải đặc tả riêng, kèm audit và test, không được suy ra chỉ từ tên role.

### 6.1. Thứ tự matcher

Trong một security filter chain, DSL authorization thường xét các matcher theo thứ tự khai báo và áp dụng **rule khớp đầu tiên**. Trường hợp cụ thể cần đi trước `anyRequest()`/`anyExchange()`. Ví dụ `requestMatchers("/**").permitAll()` nằm trước route quản trị có thể biến các rule phía sau thành vô hiệu. 

**Chọn chain** là một bước khác với **chọn rule bên trong chain**. Một `SecurityFilterChain` chỉ match `/api/**` không bảo vệ các path ngoài phạm vi đó; nếu có nhiều chain, phải xét `securityMatcher`, `@Order` và chain fallback. Đừng nhầm `anyRequest().denyAll()` của chain hẹp với “từ chối toàn bộ ứng dụng”.

### 6.2. Không lấy thông tin quyền từ dữ liệu client có thể sửa

Không tin `X-Tenant-Id`, `?userId=alice` hay `ownerId` trong JSON để chứng minh quyền. Chúng chỉ có thể là yêu cầu/định danh cần đối chiếu với identity đã được xác thực và kho dữ liệu đáng tin. Nếu request body chứa `tenantId=B` nhưng token hợp lệ mang tenant A, backend không được âm thầm thao tác dữ liệu tenant B.

## 7. Ví dụ Spring Security Servlet: bảo vệ “cửa” HTTP

Sau đây là **lớp cấu hình đầy đủ** cho ứng dụng Spring Boot **MVC/Servlet**, Java 17+, Spring Security 6.x. Đặt trong tệp `ServletAccessSecurityConfig.java` thuộc package ứng dụng có `spring-boot-starter-web` và `spring-boot-starter-security`. Các user và authority cần được application authentication cung cấp; lớp này chỉ cấu hình **HTTP gate**, chưa thực hiện owner/tenant/state gate.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ServletAccessSecurityConfig {

    @Bean
    SecurityFilterChain accessSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/public/ping", "/api/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin/audit")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST,
                        "/api/orders/*/approve")
                    .hasAuthority("order:approve")
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("order:read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("order:create")
                .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
                    .hasAuthority("order:update")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("order:delete")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

**Đọc lớp cấu hình:**

- `requestMatchers(HttpMethod.GET, ...)` tách được GET và PATCH/DELETE trên cùng nhóm URL. Không có rule cho `DELETE /api/catalog` nên rơi vào `denyAll`.
- `.hasRole("ADMIN")` đối chiếu `ROLE_ADMIN` theo prefix mặc định; `.hasAuthority("order:approve")` đối chiếu đúng chuỗi permission.
- `.anyRequest().denyAll()` đảm bảo route/method chưa được mô hình hóa không tự mở.
- `.httpBasic(...)` tạo ví dụ về điểm vào authentication. Trong ứng dụng thật có thể dùng session login hoặc JWT resource server thay cho Basic. Muốn đánh giá ma trận, cần cấu hình user store/token-to-authority đúng như bảng actor.
- `POST`, `PATCH`, `DELETE` có thể bị **CSRF** chặn thêm nếu CSRF đang bật. Authorization gate cấp quyền không tự bỏ qua CSRF; thiết kế CSRF theo cách client xác thực (session/cookie hay stateless bearer).
- Đường dẫn `/api/orders/**` vẫn cho phép các đoạn path bổ sung tùy matcher; lớp HTTP này **chưa biết** order id tồn tại hay thuộc tenant nào. Để bảo vệ object, cần resource policy phía sau.

Đây là ví dụ policy-based authorization để học tập, không phải thiết kế API production hoàn chỉnh. Khi kết hợp Servlet MVC và WebFlux trong cùng project, không được tùy tiện đăng ký cả hai kiểu security chain như thể chúng cùng xử lý một web runtime.

## 8. Ví dụ WebFlux: cùng ma trận, DSL reactive khác

Ứng dụng **Spring WebFlux** sử dụng `ServerHttpSecurity`, `SecurityWebFilterChain` và `authorizeExchange`. Lớp `ReactiveAccessSecurityConfig.java` dưới đây đặt trong **ứng dụng riêng** với `spring-boot-starter-webflux` và `spring-boot-starter-security`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveAccessSecurityConfig {

    @Bean
    SecurityWebFilterChain accessSecurityWebFilterChain(ServerHttpSecurity http) {
        http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET,
                        "/public/ping", "/api/catalog")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin/audit")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.POST,
                        "/api/orders/*/approve")
                    .hasAuthority("order:approve")
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("order:read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("order:create")
                .pathMatchers(HttpMethod.PATCH, "/api/orders/**")
                    .hasAuthority("order:update")
                .pathMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("order:delete")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Hai lớp cấu hình trên diễn đạt **cùng ý nghĩa HTTP gate**, nhưng không hoán đổi builder/bean/matcher cho nhau:

| Servlet/MVC | WebFlux |
|---|---|
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `authorizeHttpRequests` | `authorizeExchange` |
| `requestMatchers` | `pathMatchers` |
| `anyRequest()` | `anyExchange()` |
| `HttpServletRequest` | `ServerWebExchange` |
| `SecurityContextHolder` trong Servlet | `ReactiveSecurityContextHolder` qua Reactor Context |

Trong WebFlux, policy bất đồng bộ phải tiếp tục bằng `Mono`/`Flux`; không gọi `block()` để đợi database và không `subscribe()` thủ công để “kiểm tra quyền ngầm”. Kết quả kiểm tra phải nằm trong Publisher mà HTTP request đợi, để duy trì thứ tự, lỗi, hủy và security context.

**Giới hạn của cả hai ví dụ:** `order:read` ở route không suy ra quyền xem mọi đơn. Chỉ đưa request qua được lớp đầu; **phải gọi resource policy** khi xử lý bản ghi.

## 9. Biểu diễn resource policy thành Java 17 có thể chạy độc lập

Để thấy ma trận biến thành quyết định tất định như thế nào, có thể mô hình hóa một phần nghiệp vụ bằng Java thuần, không cần Spring. Tệp **`AccessMatrixDemo.java`** dưới đây minh họa READ, UPDATE, APPROVE, DELETE. Đây là mô hình học tập; ứng dụng thật phải dùng identity đã xác thực và dữ liệu order từ nguồn đáng tin.

```java
import java.util.Set;

public class AccessMatrixDemo {

    record Actor(String id, String tenant, Set<String> authorities) {}
    record Order(String owner, String tenant, String status) {}

    enum Action { READ, UPDATE, APPROVE, DELETE }

    static boolean allowed(Actor actor, Action action, Order order) {
        if (actor == null || order == null) {
            return false;
        }
        if (!actor.tenant().equals(order.tenant())) {
            return false; // ADMIN cũng không vượt tenant.
        }

        boolean owner = actor.id().equals(order.owner());
        boolean admin = actor.authorities().contains("ROLE_ADMIN");
        boolean reviewer = actor.authorities().contains("ROLE_REVIEWER");

        return switch (action) {
            case READ ->
                actor.authorities().contains("order:read")
                    && (owner || reviewer || admin);

            case UPDATE ->
                actor.authorities().contains("order:update")
                    && order.status().equals("DRAFT")
                    && (owner || admin);

            case APPROVE ->
                actor.authorities().contains("order:approve")
                    && order.status().equals("PENDING")
                    && (reviewer || admin)
                    && !owner;

            case DELETE ->
                actor.authorities().contains("order:delete")
                    && order.status().equals("DRAFT")
                    && admin;
        };
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", "A", Set.of(
            "ROLE_MEMBER", "order:read", "order:create", "order:update"
        ));
        Actor ray = new Actor("ray", "A", Set.of(
            "ROLE_REVIEWER", "order:read", "order:approve"
        ));
        Actor ada = new Actor("ada", "A", Set.of(
            "ROLE_ADMIN", "order:read", "order:create",
            "order:update", "order:approve", "order:delete"
        ));
        Order order101 = new Order("alice", "A", "DRAFT");
        Order order102 = new Order("bob", "A", "PENDING");
        Order order201 = new Order("mai", "B", "DRAFT");

        System.out.println("Alice READ #101: "
            + allowed(alice, Action.READ, order101));
        System.out.println("Alice READ #102: "
            + allowed(alice, Action.READ, order102));
        System.out.println("Ray READ #102: "
            + allowed(ray, Action.READ, order102));
        System.out.println("Ray APPROVE #102: "
            + allowed(ray, Action.APPROVE, order102));
        System.out.println("Ada DELETE #101: "
            + allowed(ada, Action.DELETE, order101));
        System.out.println("Ada READ #201: "
            + allowed(ada, Action.READ, order201));
    }
}
```

Biên dịch và chạy trên **JDK 17+**:

```bash
javac AccessMatrixDemo.java
java AccessMatrixDemo
```

Đầu ra chuẩn dự kiến, với đúng lớp ở trên:

```text
Alice READ #101: true
Alice READ #102: false
Ray READ #102: true
Ray APPROVE #102: true
Ada DELETE #101: true
Ada READ #201: false
```

Điểm đáng học từ ví dụ:

1. Chỉ cần có `ROLE_ADMIN` **không** đủ để vượt `tenant`, vì kiểm tra tenant được thực hiện trước mọi action.
2. `READ` cho owner, reviewer, admin cùng tenant; `UPDATE` còn yêu cầu `DRAFT`; `APPROVE` cần `PENDING` và không tự duyệt.
3. `Set<String> authorities` đã chứa cả role-prefixed authority (`ROLE_...`) và business permission. Trong Spring Security, tập này là kết quả của cơ chế authentication/mapping, không nên nhận trực tiếp từ body.
4. Lớp Java thuần minh họa **resource-level policy**; chưa tự giải quyết HTTP authentication, CSRF, loading database, mapping status, hay race condition khi order đổi trạng thái giữa lúc kiểm tra và ghi.

## 10. Đặt kiểm tra ở đâu để ma trận có hiệu lực?

### 10.1. HTTP gate: lọc thô theo action/permission

Filter chain có thể từ chối sớm các request không có authority, ví dụ user không có `order:update` không được chạm vào `PATCH /api/orders/{id}`. Nhưng filter **không tự biết** order đang `DRAFT` hoặc thuộc ai. Đó là lý do cần lớp policy ở mức service, nơi đã có dữ liệu order thật.

### 10.2. Service gate: kiểm tra tenant, owner, state trước khi tác động

Ví dụ **trích đoạn** từ service trong ứng dụng Servlet/MVC (các kiểu `OrderEntity`, `OrderRepository`, `OrderDto` và `OrderPolicy` là kiểu do ứng dụng định nghĩa; trích đoạn không phải class độc lập):

```java
public OrderDto updateOrder(
        long orderId,
        UpdateOrderCommand command,
        Authentication authentication) {

    OrderEntity order = orderRepository.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));

    if (!orderPolicy.canUpdate(authentication, order)) {
        throw new AccessDeniedException("Not allowed to update order");
    }

    order.applyAllowedChanges(command);
    return toDto(orderRepository.save(order));
}
```

Ở đây `canUpdate` phải kiểm tra đủ **order:update + tenant + (owner hoặc ADMIN) + DRAFT** theo bảng đã chốt. Việc trả 404 hay 403 đối với bản ghi không thuộc tenant là lựa chọn tránh rò thông tin, cần một chính sách thống nhất; không trả nội dung chi tiết của bản ghi khi quyền chưa được xác minh.

**Lưu ý race condition/TOCTOU:** nếu order đổi từ `DRAFT` sang `APPROVED` giữa lúc đọc và lưu, check ban đầu không còn đủ. Với hành động quan trọng, dùng transaction/locking/optimistic version hoặc cập nhật có điều kiện ngay trong database (ví dụ `WHERE tenant_id = ? AND status = 'DRAFT' AND version = ?`) và kiểm tra số hàng cập nhật. Đừng coi một `if` trong memory là bảo đảm cuối cùng khi có request đồng thời.

### 10.3. Reactive service gate: ghép Publisher, bảo toàn identity

Trong WebFlux, logic truy cập bản ghi bất đồng bộ phải nằm trong một Publisher. Trích đoạn minh họa sử dụng `reactiveOrderRepository.findById` trả `Mono<OrderEntity>` và `orderPolicy.canRead` là kiểm tra đồng bộ nhanh dựa trên các giá trị đã có:

```java
return reactiveOrderRepository.findById(orderId)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND)))
    .flatMap(order ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Unauthenticated")))
            .flatMap(authentication -> {
                if (!orderPolicy.canRead(authentication, order)) {
                    return Mono.error(
                        new AccessDeniedException("Forbidden"));
                }
                return Mono.just(toDto(order));
            })
    );
```

Các kiểu và import trong trích đoạn: `Mono` của Reactor, `ReactiveSecurityContextHolder`, `SecurityContext`, `AccessDeniedException`, `ResponseStatusException` và `HttpStatus` của Spring. Nếu việc kiểm tra quyền còn phải gọi kho dữ liệu khác, `orderPolicy` nên cung cấp `Mono<Boolean>` để ghép tiếp bằng `flatMap`; không `block()` hoặc `subscribe()` thủ công trong security chain.

### 10.4. Method security bổ sung lớp bảo vệ khi service được gọi nơi khác

- Với Servlet, kích hoạt `@EnableMethodSecurity` và dùng `@PreAuthorize`/`@PostAuthorize` khi điều kiện phù hợp. Ví dụ `@PreAuthorize("hasAuthority('order:read')")` hạn chế phương thức cho người có permission; kiểm tra owner/tenant cụ thể vẫn phải được thực hiện ở nơi có resource.
- Với Reactive, có `@EnableReactiveMethodSecurity` (với cấu hình phù hợp phiên bản Spring Security); kiểm tra được tích hợp với Reactor `Context`. Method/service trả `Mono`/`Flux` cần bảo toàn subscription context.
- Một service không có annotation không tự động trở thành an toàn nhờ bật method security. HTTP catch-all vẫn cần thiết; các entry point ngoài HTTP (message consumer, scheduled job) cần quy tắc truy cập riêng.
- Không nên giấu một kiểm tra quan trọng chỉ trong controller; nếu cùng service được gọi bởi batch, event listener hoặc API khác, nó có thể bỏ qua controller đó. Policy ở service hoặc một tầng domain/authorization dùng lại giúp tránh lệch quyền giữa các đường vào.

## 11. Cách chuyển từng dòng ma trận thành test

Với một rule, tối thiểu kiểm tra **một ca được phép và một ca bị từ chối**, sau đó thêm các nhánh ngữ cảnh. Dữ liệu test nên tạo **cụ thể** các actor và order 101/102/201; tránh lấy tất cả token quyền cao làm test mặc định.

Ví dụ bộ test theo luồng:

| Nhóm | Case phải kiểm tra | Điều chứng minh |
|---|---|---|
| Public | Anonymous GET catalog → cho qua | `permitAll` đúng phạm vi |
| Authentication | Anonymous GET order → không cho qua | Route không công khai |
| Authority | Alice PATCH own DRAFT được; Ray PATCH bị từ chối | `order:update` có hiệu lực |
| Role | Ada xem audit; Alice bị từ chối | `ROLE_ADMIN` hoạt động |
| Ownership | Alice GET own 101, không GET Bob 102 | IDOR/BOLA được chặn |
| Tenant isolation | Ada tenant A không GET order 201 tenant B | ADMIN không tự vượt tenant |
| Resource state | Alice PATCH DRAFT được, PENDING bị từ chối | Điều kiện trạng thái có hiệu lực |
| Separation of duties | Reviewer không được tự duyệt order mình tạo | Chặn self-approval |
| Action mapping | Ray APPROVE PENDING được nhưng UPDATE không được | Phân biệt APPROVE với UPDATE |
| Unknown route/method | DELETE catalog, PATCH audit → từ chối | Catch-all hoạt động |
| CSRF | POST/PATCH trong session browser có/không token | Phân biệt CSRF và permission |
| Concurrency | Hai request cùng đổi state/version | Không vượt policy do race condition |

**Với Spring MVC:** dùng `MockMvc` và `spring-security-test`, hỗ trợ `with(user(...))`, `with(csrf())`; với Spring WebFlux dùng `WebTestClient` và các configurer như `mockUser()`, `csrf()`. Khi test tenant/owner, dựng principal custom hoặc authentication fixture đúng tenant — chỉ giả lập role bằng `mockUser("alice")` không đủ để chứng minh chính sách owner.

Trích đoạn MVC cho tầng route khi có endpoint thử nghiệm tương ứng (không phải một class test độc lập):

```java
mockMvc.perform(get("/api/orders/101")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("order:read"))))
    .andExpect(status().isOk());
```

Để test tầng owner/tenant, service fixture phải biết `alice` thuộc tenant A, order 101 thuộc alice và A; nếu không có fixture đó, chỉ chứng minh route gate. Với request POST/PATCH/DELETE mà CSRF đang bật, cung cấp `with(csrf())` trong test nếu đang kiểm tra authorization business, rồi có thêm ca riêng xác nhận thiếu CSRF bị chặn.

Trích đoạn WebFlux minh họa route gate:

```java
webTestClient
    .mutateWith(mockUser("ray").authorities(
        new SimpleGrantedAuthority("order:approve")))
    .post().uri("/api/orders/102/approve")
    .exchange()
    .expectStatus().is2xxSuccessful();
```

Ví dụ trên giả định đã cấu hình WebTestClient, endpoint, test authentication fixture và CSRF phù hợp; không có nghĩa Spring Security tự hiểu rằng order 102 đang PENDING. Với cấu hình CSRF mặc định, request POST có thể cần `mutateWith(csrf())`. Nếu endpoint trả mã khác 2xx trong nghiệp vụ thực, điều chỉnh assertion theo contract. Test đầy đủ phải kiểm tra rằng **từ chối không gây tác dụng phụ** (không thay order, không tạo audit approval sai, không gửi event). Một response 403 mà dữ liệu vẫn bị cập nhật vẫn là lỗi nghiêm trọng.

Nên giữ ma trận ở dạng YAML/CSV hoặc code fixture để test sinh được trường hợp. Ví dụ YAML đặc tả một số ca (mang tính minh họa schema, không phải định dạng Spring Security tự tiêu thụ):

```yaml
cases:
  - actor: alice
    tenant: A
    method: GET
    path: /api/orders/101
    expected: ALLOW
  - actor: alice
    tenant: A
    method: GET
    path: /api/orders/102
    expected: DENY
  - actor: ada
    tenant: A
    method: GET
    path: /api/orders/201
    expected: DENY
  - actor: ray
    tenant: A
    method: POST
    path: /api/orders/102/approve
    expected: ALLOW
```

Mỗi testcase muốn chạy thực cần ánh xạ sang user/tenant/order fixture và expected HTTP response phù hợp cách xác thực (401, 403, redirect hoặc 404 khi che giấu tồn tại tài nguyên). Không đồng nhất `DENY` trong ma trận với đúng một mã HTTP bất biến.

## 12. Kết quả từ chối và những lớp bảo vệ khác

**401 Unauthorized** thường được dùng khi yêu cầu chưa có authentication hợp lệ với cơ chế như HTTP Basic/JWT; **403 Forbidden** thường xảy ra khi đã xác thực nhưng thiếu quyền, hoặc CSRF từ chối. Với form login có thể bị chuyển hướng đến trang login. `404 Not Found` có thể được chọn cho tài nguyên ngoài phạm vi để tránh lộ sự tồn tại, nhưng cần chính sách nhất quán. Spring Security còn xử lý entry point, exception translation và CSRF; vì vậy đừng suy ra quyền chỉ từ status mà bỏ qua log và fixture.

Khi dùng các web stack khác nhau:

- **Servlet/MVC:** `authorizeHttpRequests` kiểm tra ở filter chain; method security qua `@EnableMethodSecurity`; lưu ý Servlet `FORWARD`/`ERROR` dispatch khi có trang lỗi. Đường dẫn và method phải test với request matcher thực tế.
- **WebFlux:** `authorizeExchange` kiểm tra trên `ServerWebExchange`; nhận identity qua Reactor context; policy không được gọi `block()`/`subscribe()` để xử lý tùy biến. 
- **Nhiều chain:** Matcher dùng chọn `SecurityFilterChain`/`SecurityWebFilterChain` khác matcher chọn rule trong chain. Đừng để path không khớp bất kỳ chain nào trở thành khoảng trống bảo vệ.
- **JWT OAuth2:** Nếu dùng scope/claim làm authority, mapper phải định nghĩa rõ prefix/định dạng; một actor có scope `SCOPE_order.read` không mặc nhiên có `order:read`. Ma trận phải nêu chính xác chuỗi quyền Spring Security sẽ kiểm tra.

## 13. Các lỗi thiết kế ma trận thường gặp

1. **Chỉ liệt kê role theo endpoint** mà thiếu HTTP method, owner, tenant, state → dễ dính IDOR/BOLA và vượt quyền theo thao tác.
2. **Tin role ADMIN mặc nhiên toàn hệ thống** → rò dữ liệu nhiều tenant. Hãy đặc tả rõ quyền global nếu thật sự có.
3. **Mặc định ALLOW** khi gặp route mới, action chưa định nghĩa, owner null hoặc policy service trả rỗng → endpoint mới tự mở.
4. **Có `hasRole` nhưng cấp sai authority:** `hasRole("ADMIN")` thường tìm `ROLE_ADMIN`, còn `hasAuthority("ADMIN")` tìm đúng `ADMIN`. Không trộn quy ước thiếu kiểm soát.
5. **Dùng query/body/HTTP header làm tenant hoặc owner đáng tin** → caller có thể tự đổi ID của đối tượng để truy cập dữ liệu khác.
6. **Chỉ chặn ở UI** (ẩn nút Approve/Delete) → attacker vẫn gọi HTTP request trực tiếp.
7. **Chỉ chặn ở controller** → service được gọi từ đường vào khác có thể thiếu policy.
8. **Để rule quá rộng ở đầu** như `/**.permitAll()` hoặc không có catch-all → mất hiệu lực rule đặc thù.
9. **Kiểm tra trước nhưng cập nhật sau không có bảo vệ concurrency** → order đổi state giữa check và write, vẫn bị duyệt/sửa sai.
10. **Không test negative cases:** có vài test 2xx cho admin nhưng không có test cho user thiếu quyền, sai tenant, sai status, sai HTTP method.
11. **Dùng một status code làm bằng chứng duy nhất:** thiếu CSRF, chưa xác thực, không có handler và deny policy có thể tạo response khác nhau.
12. **Copy rule giữa Servlet/WebFlux bằng đổi tên hàm** mà bỏ qua loại chain, matcher, context và yêu cầu reactive.
13. **Không theo dõi thay đổi quyền:** thêm action `EXPORT`/`REFUND`/`CANCEL` nhưng không cập nhật ma trận và test dẫn đến rule thiếu hoặc logic nhất quán không còn.
14. **Quy tắc audit chưa rõ:** ai xem log, log của tenant nào, log có dữ liệu nhạy cảm nào; role ADMIN không loại bỏ nghĩa vụ bảo vệ dữ liệu trong log.

## 14. Cách triển khai và duy trì ma trận trong dự án thật

1. **Lập inventory endpoint** theo method + route; ghi rõ action nghiệp vụ, tài nguyên, resource ID và ai sở hữu.
2. **Chốt identity contract**: `userId`, `tenantId`, role, authorities đến từ hệ thống xác thực tin cậy; quy ước namespace permission được công bố nhất quán.
3. **Điền cả hai cấp policy**: HTTP gate để chặn sớm, resource gate để kiểm tra tenant/owner/state; quy định xử lý thiếu dữ liệu và lỗi.
4. **Chốt default deny** và thứ tự các matcher; xác minh mọi route được một security chain phù hợp quản lý.
5. **Từ ma trận tạo test fixtures** cho anonymous, member, reviewer, admin, các tenant và trạng thái dữ liệu. Mỗi ALLOW có các biến thể DENY gần nhất.
6. **Rà soát concurrency, transaction và side effects** trên action thay đổi trạng thái; kiểm tra audit/sự kiện chỉ xảy ra khi được phép.
7. **Tài liệu hóa cơ chế phản hồi**: 401/403/404/redirect, CSRF, log và cách không lộ dữ liệu qua error.
8. **Cập nhật theo thay đổi API**: PR thêm endpoint/action phải bổ sung hoặc sửa dòng ma trận, policy và test; tránh bảng đúng ở tài liệu nhưng code đã lệch.
9. **Review quyền cao**: role ADMIN, super-admin, hỗ trợ xuyên tenant và thao tác phá hủy cần kiểm soát chặt, theo nguyên tắc đặc quyền tối thiểu.

## 15. Tự kiểm tra hiểu bài

**Câu 1.** Alice có `order:read` và `ROLE_MEMBER` nhưng muốn `GET /api/orders/102` (Bob sở hữu, cùng tenant). Có cho phép không?

**Đáp án:** Không. Request vượt qua HTTP gate vì có authority, nhưng resource gate từ chối vì Alice không phải owner và không phải REVIEWER/ADMIN. Ma trận phải kiểm tra cả hai tầng.

**Câu 2.** Ada là ADMIN tenant A, muốn xem order 201 tenant B. Vai trò ADMIN có đủ chưa?

**Đáp án:** Chưa. Chính sách ví dụ yêu cầu `actor.tenantId == order.tenantId` cho mọi actor, kể cả ADMIN. Truy cập xuyên tenant cần policy riêng nếu nghiệp vụ thật sự cho phép.

**Câu 3.** Ray có `order:approve`, muốn phê duyệt order 101 nhưng đơn đang `DRAFT`. Lớp HTTP cho qua không và kết quả cuối là gì?

**Đáp án:** HTTP gate theo authority có thể cho qua, nhưng resource policy từ chối do đơn chưa `PENDING`. Không được chạy hành động phê duyệt.

**Câu 4.** API vừa thêm `POST /api/orders/{id}/cancel`. Nếu không khai báo rule hoặc action thì sao?

**Đáp án:** Theo catch-all `denyAll`, route mới bị từ chối cho đến khi đặc tả action CANCEL, role/permission, điều kiện state/owner/tenant và tests của nó. Đây là hành vi an toàn.

**Câu 5.** Sau khi thêm `@EnableMethodSecurity`, mọi service đã được bảo vệ chưa?

**Đáp án:** Chưa. Chỉ những method/class chịu rule method security được khai báo phù hợp mới có kiểm soát ở mức đó. Vẫn cần thiết kế HTTP gate và service policy; method không được annotate có thể không bị chặn bởi method security.

## 16. Nguồn tài liệu

- [Spring Security – Servlet: Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Servlet: Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security – WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security – Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [OWASP – API Security Top 10: Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)

**Ghi nhớ:** Một ma trận truy cập tốt trả lời đồng thời **endpoint nào, ai gọi, mang quyền gì, thực hiện action gì trên bản ghi nào, trong tenant/trạng thái nào**. `permitAll`, `hasRole`, `hasAuthority` và `denyAll` mới là cửa kiểm soát HTTP; tính đúng của phân quyền còn phụ thuộc service policy trên owner/tenant/state và bộ test ALLOW/DENY phủ đủ các trường hợp.