# Quy tắc cụ thể trước quy tắc tổng quát

> **Chủ đề:** Spring Security - authorization  
> **Nhóm kiến thức:** Phân quyền HTTP  
> **Mục tiêu:** Biết vì sao thứ tự `requestMatchers` quyết định request được cho phép hay bị từ chối, đặt ngoại lệ hẹp trước luật tổng quát khi chúng có thể khớp cùng request, phân biệt thứ tự chọn `SecurityFilterChain` với thứ tự rule trong `authorizeHttpRequests`, và viết được test chứng minh không có endpoint nhạy cảm bị rule quá rộng che khuất.

## 1. Một lỗi nhỏ về thứ tự có thể biến thành lỗ hổng quyền

Giả sử ứng dụng có ba đường dẫn:

- `GET /api/reports/public/help`: bất kỳ ai cũng được đọc.
- `GET /api/reports/admin/audit`: chỉ admin được đọc.
- `GET /api/reports/annual`: người có quyền `reports:read` được đọc.

Một cấu hình nhìn qua có vẻ hợp lý:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("reports:read")
    .requestMatchers(HttpMethod.GET, "/api/reports/admin/**")
        .hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/reports/public/**")
        .permitAll()
    .anyRequest().denyAll()
);
```

Nhưng `GET /api/reports/admin/audit` **đã khớp** mẫu rộng `/api/reports/**` ở rule đầu tiên. Nếu Alice có `reports:read` mà không phải admin, Alice có thể được cho qua bước phân quyền HTTP của endpoint admin. Rule `hasRole("ADMIN")` phía dưới không được dùng để “siết thêm” quyết định trước đó.

Tương tự, một khách vô danh gửi `GET /api/reports/public/help` cũng bị rule đầu tiên kiểm tra `reports:read` và từ chối, dù phía dưới có `permitAll()`.

**Bài học cốt lõi:** với `authorizeHttpRequests`, các rule thường được thử **theo thứ tự khai báo; rule đầu tiên có request matcher khớp sẽ quyết định tại tầng HTTP**. Spring Security không tự sắp xếp từ “đường dẫn dài nhất” đến “đường dẫn ngắn nhất”; cũng không mặc định ghép kết quả của mọi rule khớp bằng AND.

## 2. Sửa đúng: đặt các trường hợp hẹp trước trường hợp rộng

Với cùng ba route, hãy viết:

```java
http.authorizeHttpRequests(auth -> auth
    // Ngoại lệ công khai hẹp, chỉ dành cho GET.
    .requestMatchers(HttpMethod.GET, "/api/reports/public/**")
        .permitAll()

    // Khu vực nhạy cảm phải được kiểm tra trước mẫu tổng quát.
    .requestMatchers(HttpMethod.GET, "/api/reports/admin/**")
        .hasRole("ADMIN")

    // Các báo cáo GET còn lại cần quyền đọc chung.
    .requestMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("reports:read")

    // Mọi method/path khác không được tự mở.
    .anyRequest().denyAll()
);
```

Kết quả mong muốn, với tiền tố role mặc định `ROLE_`:

| Request | Danh tính | Rule khớp đầu tiên | Quyết định HTTP |
| --- | --- | --- | --- |
| `GET /api/reports/public/help` | Anonymous | `/api/reports/public/**` | ALLOW bởi `permitAll` |
| `GET /api/reports/admin/audit` | `ROLE_ADMIN` | `/api/reports/admin/**` | ALLOW |
| `GET /api/reports/admin/audit` | `reports:read`, không có admin | `/api/reports/admin/**` | DENY |
| `GET /api/reports/annual` | `reports:read` | `/api/reports/**` | ALLOW |
| `GET /api/reports/annual` | Anonymous | `/api/reports/**` | DENY |
| `POST /api/reports/public/help` | Anonymous | `anyRequest` | DENY |
| `PATCH /api/reports/annual` | `reports:read` | `anyRequest` | DENY |
| `GET /api/unknown` | Đã đăng nhập | `anyRequest` | DENY |

Điểm quan trọng: `/api/reports/public/**` không nên được mở cho mọi HTTP method nếu chức năng chỉ công khai GET. Dùng `requestMatchers(HttpMethod.GET, ...)` thể hiện ý định: **đường dẫn và thao tác HTTP cùng quyết định rule có khớp không**.

Ngoài kiểm tra HTTP, nếu báo cáo thuộc tenant cụ thể hoặc có điều kiện trạng thái, service vẫn cần kiểm tra quyền trên bản ghi. `ALLOW` ở `hasAuthority("reports:read")` không phải giấy phép đọc mọi object.

## 3. Mô hình đúng: tìm rule khớp đầu tiên, rồi đánh giá nó

Một cách biểu diễn giản lược của `RequestMatcherDelegatingAuthorizationManager`:

```text
request = (HTTP method, path, dispatch type, ...)
rules = [rule1, rule2, ..., ruleN]

for rule in rules theo thứ tự khai báo:
    if rule.matcher.matches(request):
        return rule.authorizationManager.authorize(authentication, request)

return kết quả do fallback/no-match policy quyết định
```

Đoạn trên chỉ là **pseudocode mô tả first-match**, không phải mã nguồn đầy đủ của Spring Security. Các implementation còn xử lý `Supplier<Authentication>`, exception, matcher context, quyết định abstain/deny và các chi tiết khác theo phiên bản. Điều cần hiểu là: sau khi đã chọn một rule khớp đầu tiên, hệ thống **không đi tiếp để thử rule bên dưới** chỉ vì manager của rule đầu từ chối.

Đây là chỗ dễ nhầm:

```text
Rule 1: /api/**        -> authenticated()
Rule 2: /api/admin/**  -> hasRole("ADMIN")
```

Một request `GET /api/admin/users` khớp rule 1. Nếu đã đăng nhập, nó vượt qua kiểm tra tại rule 1. Rule 2 không bổ sung điều kiện admin. Đảo thứ tự:

```text
Rule 1: /api/admin/**  -> hasRole("ADMIN")
Rule 2: /api/**        -> authenticated()
```

Lúc này một request tới `/api/admin/users` được rule 1 xử lý; request API khác mới về rule 2.

**Không cần xếp theo số lượng ký tự một cách máy móc.** Tiêu chí là mức bao phủ của matcher và chính sách muốn áp dụng. Hai rule không giao nhau có thể đặt theo thứ tự bất kỳ về mặt kết quả; hai rule giao nhau mà yêu cầu quyết định khác nhau cần chọn thứ tự có chủ đích.

## 4. Matcher hẹp và matcher rộng: hiểu bằng tập hợp

Hãy xem mỗi `RequestMatcher` như một tập các request có thể khớp.

- Tập `A`: mọi `GET /api/reports/public/**`.
- Tập `B`: mọi `GET /api/reports/**`.
- Tập `C`: mọi `GET /api/**`.

Với cú pháp khớp path như trên và cách xử lý request path phù hợp, về ý tưởng `A ⊂ B ⊂ C`. Do `A` nằm trong `B`, nếu đặt `B` trước thì rule `A` ở sau không còn cơ hội xử lý request thuộc `A`.

Ví dụ quyền:

```text
GET /api/reports/public/help
  ├─ khớp public/**        -> permitAll
  ├─ khớp reports/**       -> reports:read
  └─ khớp api/**           -> authenticated

Nếu public/** đứng đầu: permitAll.
Nếu reports/** đứng đầu: cần reports:read.
Nếu api/** đứng đầu: chỉ cần authenticated.
```

**Không có luật tự động “matcher cụ thể hơn thắng”.** Kết quả thay đổi khi thứ tự thay đổi. Cụ thể hơn không đồng nghĩa bảo mật hơn trong mọi trường hợp: `permitAll` là ngoại lệ **ít hạn chế**, nhưng vẫn cần đứng trước rule quyền chung nếu tài nguyên thực sự công khai.

### Thế nào là “cụ thể hơn”?

Trong review cấu hình, hãy xét kết hợp:
- **HTTP method:** `GET` hẹp hơn mọi method.
- **Path:** `/api/admin/users/**` hẹp hơn `/api/admin/**`.
- **Dispatcher type:** `ERROR` hoặc `FORWARD` có thể tạo trường hợp khác so với request chính.
- **Thông tin matcher tùy biến:** host, header, media type hoặc predicate khác nếu dự án thật sự sử dụng.
- **Policy dự kiến:** nếu hai matcher cùng khớp nhưng yêu cầu giống hệt nhau, thứ tự không tạo khác biệt quyền tại điểm này.

Đừng định nghĩa “cụ thể” bằng chuỗi dài hơn. Một custom matcher có thể bao quát request theo method/header rộng hơn chuỗi path gợi ý. Hãy kiểm tra hành vi matcher thật thay vì suy luận từ tên.

## 5. Hai cấp thứ tự khác nhau: chọn SecurityFilterChain và chọn rule

Một điểm tinh tế của Spring Security Servlet là **thứ tự chain** và **thứ tự luật authorization trong chain** hoàn toàn khác nhau.

```text
HTTP request
    |
    v
DelegatingFilterProxy / FilterChainProxy
    |
    | 1. Chọn SecurityFilterChain ĐẦU TIÊN có securityMatcher khớp
    v
SecurityFilterChain đã được chọn
    |
    | authentication, context, các security filters khác
    v
AuthorizationFilter
    |
    | 2. Chọn requestMatcher ĐẦU TIÊN có rule khớp
    v
AuthorizationManager -> ALLOW / DENY
```

| Cấp | API thường gặp | Chọn theo thứ tự | Hậu quả |
| --- | --- | --- | --- |
| Chọn chain | `http.securityMatcher(...)` kết hợp `@Order` trên `SecurityFilterChain` | Chain khớp đầu tiên trong danh sách của `FilterChainProxy` | Những chain phía sau không cộng dồn bảo vệ |
| Chọn HTTP rule bên trong chain | `authorizeHttpRequests(...requestMatchers(...))` | Rule khớp đầu tiên | Những rule phía dưới không được AND thêm |
| Chính sách ở method | `@PreAuthorize`, `@PostAuthorize` | Spring AOP interceptor theo pointcut/order | Là lớp kiểm tra khác, xảy ra khi lời gọi method phù hợp |
| Chính sách trong service | Policy nghiệp vụ theo actor/resource | Theo code/use case được viết | Phải bảo vệ object/tenant/invariant rõ ràng |

Một sai lầm là tạo chain A cho `/api/**` và chain B cho `/api/admin/**`, rồi nghĩ “chain B sẽ kiểm tra thêm quyền admin”. Nếu A đứng trước, B có thể không bao giờ được chọn đối với `/api/admin/**`.

## 6. Ví dụ nhiều SecurityFilterChain: phần API admin phải chọn chain trước

Giả sử ứng dụng có API quản trị dùng cơ chế riêng và API thông thường:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultipleChainsSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/admin/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
            );
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain regularApi(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            );
        return http.build();
    }
}
```

**Đây là snippet cấu trúc**, chưa phải cấu hình ứng dụng hoàn chỉnh: chưa có lựa chọn phương thức xác thực, CSRF, session, error handling hoặc bảo vệ route nằm ngoài `/api/**`. Ý nghĩa chính:

1. `/api/admin/users` khớp cả `/api/admin/**` và `/api/**`, nhưng chain admin đứng trước nhờ `@Order(1)`.
2. `/api/documents` không khớp chain admin, nên được chain API thông thường xử lý.
3. Với chain admin, `anyRequest().hasRole("ADMIN")` áp dụng cho mọi request **đã thuộc chain admin**.
4. Với chain thường, `authenticated()` chỉ xác nhận mức authentication, không tự chứng minh permission trên từng chức năng và object.
5. **Nếu thiếu chain fallback**, một URL ngoài mọi `securityMatcher` có thể không được Spring Security filter chain bảo vệ. Cần thiết kế fallback rõ ràng.

Nếu đảo `@Order` để chain `/api/**` đứng trước chain admin, API admin có thể chỉ bị yêu cầu đăng nhập và không tới luật admin. Đừng nhầm vấn đề này với thứ tự `requestMatchers` bên trong một chain.

Khi không thật sự cần nhiều chain khác cơ chế xác thực, một chain duy nhất với các rule hẹp trước rule rộng thường dễ kiểm toán hơn. Nhiều chain chỉ nên dùng khi có ranh giới bảo mật rõ, chẳng hạn web session và API bearer khác nhau.

## 7. Cấu hình đầy đủ về ý định bảo mật: explicit public, chức năng, rồi fallback

Một cách tổ chức rule dễ đọc:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HttpAuthorizationConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            // 1. Public endpoint cần công khai thật sự.
            .requestMatchers(HttpMethod.GET, "/actuator/health")
                .permitAll()
            .requestMatchers(HttpMethod.GET, "/api/docs/public/**")
                .permitAll()

            // 2. Các vùng nhạy cảm hoặc exception hẹp.
            .requestMatchers("/api/admin/**")
                .hasRole("ADMIN")
            .requestMatchers(HttpMethod.DELETE, "/api/docs/**")
                .hasAuthority("document:delete")
            .requestMatchers(HttpMethod.PATCH, "/api/docs/**")
                .hasAuthority("document:edit")
            .requestMatchers(HttpMethod.GET, "/api/docs/**")
                .hasAuthority("document:read")

            // 3. Luật tổng quát chỉ nếu có chủ đích.
            .requestMatchers("/api/profile/**")
                .authenticated()

            // 4. Mặc định đóng.
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Snippet trên minh họa **thứ tự**. Trong ứng dụng thật, `/actuator/health` có thể dùng management context/port riêng; cần khớp đường dẫn thực tế. Cơ chế login/bearer, exception handling, CORS và CSRF cũng cần cấu hình phù hợp. Tài nguyên cụ thể vẫn cần business policy.

Hãy đọc theo thứ tự:
- `GET /api/docs/public/guide` gặp `permitAll()` trước các luật `/api/docs/**`.
- `DELETE /api/docs/42` gặp `document:delete` trước các luật chung cho docs.
- `GET /api/docs/42` gặp `document:read`.
- `GET /api/admin/users` đụng vùng admin và cần `ROLE_ADMIN`.
- `GET /api/profile/me` cần authentication.
- `POST /api/unknown` rơi vào `denyAll`.

Chú ý rằng rule `.requestMatchers("/api/admin/**").hasRole("ADMIN")` bao phủ mọi HTTP method của API admin. Đây là lựa chọn có chủ đích; nếu API admin cần quyền khác nhau cho GET và POST, hãy định nghĩa thêm các rule hẹp theo HTTP method phía trước, sau đó dùng fallback cho phần còn lại.

## 8. Trường hợp phổ biến: public GET nhưng write vẫn phải bảo vệ

Giả sử sản phẩm có một trang công khai:

```text
GET    /api/articles/42  -> public
POST   /api/articles     -> editor
PATCH  /api/articles/42  -> editor
DELETE /api/articles/42  -> administrator
```

Cấu hình nguy hiểm:

```java
.requestMatchers("/api/articles/**").permitAll()
.requestMatchers(HttpMethod.POST, "/api/articles/**").hasRole("EDITOR")
.requestMatchers(HttpMethod.DELETE, "/api/articles/**").hasRole("ADMIN")
```

Rule đầu **không giới hạn HTTP method**, vì thế POST/DELETE cũng có thể bị permitAll tại bước authorization HTTP. Rule bên dưới trở nên vô hiệu cho các request đã match.

Một thiết kế rõ ràng hơn:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/articles/**")
        .permitAll()
    .requestMatchers(HttpMethod.HEAD, "/api/articles/**")
        .permitAll() // Nếu HEAD cũng được public theo contract.
    .requestMatchers(HttpMethod.DELETE, "/api/articles/**")
        .hasRole("ADMIN")
    .requestMatchers(HttpMethod.POST, "/api/articles/**")
        .hasRole("EDITOR")
    .requestMatchers(HttpMethod.PATCH, "/api/articles/**")
        .hasRole("EDITOR")
    .anyRequest().denyAll()
);
```

Thực tế cần kiểm tra mapping `POST /api/articles` có khớp mẫu `/api/articles/**` theo chiến lược matcher của version đang dùng hay không; nếu muốn độ chắc chắn cao, khai báo exact path `/api/articles` cho POST. Đừng chuyển đổi từ Ant-style sang `PathPattern` mà không có test ở path gốc, path con, dấu slash cuối và case khác.

Đặc biệt với API có CORS, đừng mở tất cả method trên một path chỉ để preflight hoạt động. Cấu hình CORS/preflight một cách chuẩn tắc thay vì dùng `permitAll("/api/**")` cho toàn bộ request.

## 9. anyRequest(): quy tắc tổng quát cuối cùng

`anyRequest()` thường đóng vai trò catch-all cho tất cả request chưa được rule trước đó xử lý. Các lựa chọn:

- `anyRequest().denyAll()`: mặc định từ chối. Thích hợp với API chỉ công bố các route đã liệt kê.
- `anyRequest().authenticated()`: mặc định mọi route còn lại yêu cầu người dùng đã xác thực; **không bảo đảm** role/permission cho từng chức năng.
- `anyRequest().permitAll()`: các route chưa liệt kê được vào công khai tại bước authorization; chỉ dùng nếu đó thật sự là chính sách sản phẩm.

Với hệ thống cần kiểm soát truy cập chặt, **default deny** giúp route mới không vô tình được mở khi developer thêm controller mà quên rule. Tuy nhiên nếu ứng dụng có rất nhiều endpoint chung, nhóm có thể chủ đích dùng `authenticated()` làm fallback và bảo vệ chức năng tại method/domain; cần ghi rõ policy và test.

`anyRequest()` là catch-all cho phạm vi `authorizeHttpRequests` trong chain được chọn; không thay thế `securityMatcher` và không mở rộng phạm vi chain sang mọi URL. Hãy đặt `anyRequest` cuối cùng; các DSL có thể phát hiện việc khai báo rule sau catch-all là không hợp lệ, thay vì tiếp tục xét bình thường.

Ví dụ:

```java
// Tốt: rule cụ thể trước, catch-all cuối.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
```

Ở đây `GET /api/admin/users` cần role admin, còn `GET /api/tasks` chỉ cần authentication **tại HTTP layer**. Nếu `/api/tasks` có quyền đọc khác nhau theo người dùng, service phải kiểm tra thêm.

## 10. “Specific first” không phải là quy tắc xếp chuỗi dài trước chuỗi ngắn

Hãy xét:

```text
GET /api/invoices/123
GET /api/invoices/search
GET /api/invoices/admin/export
```

Một endpoint search có thể trùng cách biểu diễn với `/{id}`, tùy route mapping. Một `RequestMatcher` bao phủ `/api/invoices/*` có thể giao với `/api/invoices/search`. Nếu cần quyền khác nhau, hãy làm rõ:
- Matcher cho exact `/api/invoices/search`.
- Matcher cho export/admin path.
- Matcher cho chi tiết hóa đơn với ID.
- Chính sách theo HTTP method.
- Scope tenant/owner và quyền resource tại service.

Một rule “nhìn hẹp hơn” có thể lại có phạm vi rộng hơn do wildcard, custom matcher hoặc cấu hình servlet path. Đo lường bằng test matcher thực tế.

Trường hợp hai rule **không giao nhau**, thứ tự không làm thay đổi quyết định:
- `GET /api/articles/**`
- `POST /api/orders/**`

Trường hợp hai rule giao nhau nhưng có **cùng policy**, thứ tự có thể không làm thay đổi kết quả ALLOW/DENY; tuy nhiên vẫn cần cách tổ chức dễ review và bảo trì.

**Kết luận định lượng:** người viết chính sách phải hình dung tập request mà matcher bao phủ; không được chỉ dựa trên số segment của path.

## 11. Phải hiểu sự khác nhau giữa path matching và business permission

Một request matcher thường quyết định theo **đường dẫn, HTTP method hoặc thuộc tính request**. Nó không tự xác minh dữ liệu nghiệp vụ bên trong resource.

Giả sử:

```java
.requestMatchers(HttpMethod.GET, "/api/projects/*/documents/**")
    .hasAuthority("document:read")
```

Người dùng có `document:read` được cho qua request guard. Nhưng:
- Project ID trên URL có thuộc tenant của người đó không?
- Document ID có thuộc đúng project không?
- Người đó có grant trên document cụ thể không?
- Document đã bị archive/đánh dấu confidential chưa?
- Có endpoint download/export với quyền khác không?

Những câu hỏi này cần policy theo actor–resource–context ở service hoặc một `AuthorizationManager` tùy biến có dữ kiện đáng tin. Một rule URL không biến bất kỳ `/{id}` nào thành object-level authorization.

Ví dụ service (snippet tích hợp, không phải class standalone):

```java
@PreAuthorize("hasAuthority('document:read')")
public DocumentView readDocument(long projectId, long documentId) {
    Actor actor = actorResolver.requireActor();

    Document document = repository.findByIdAndProjectIdAndTenantId(
        documentId, projectId, actor.tenantId()
    ).orElseThrow(DocumentNotFoundException::new);

    if (!documentPolicy.canRead(actor, document)) {
        throw new AccessDeniedException("Not allowed");
    }

    return mapper.toView(document);
}
```

Các type `Actor`, `Document`, `DocumentView`, repository, policy và mapper thuộc ứng dụng; ví dụ thể hiện trách nhiệm, không có sẵn trong Spring. Đặt rule hẹp đúng vị trí **và** kiểm tra object trong use case mới đủ để tránh IDOR/BOLA.

## 12. Java 17+ chạy độc lập: mô phỏng first-match, sai rồi sửa

Ví dụ sau không cần Spring và không cố tái hiện `PathPatternRequestMatcher`. Nó mô phỏng chính xác ý tưởng **duyệt từ trên xuống, lấy rule khớp đầu tiên** bằng path exact hoặc tiền tố `/**`. Mục đích là thấy một lần đổi thứ tự ảnh hưởng ngay cả khi tập rule không đổi.

Lưu thành file `FirstMatchRulesDemo.java`:

```java
import java.util.List;
import java.util.Set;

public class FirstMatchRulesDemo {

    record Actor(boolean authenticated, Set<String> authorities) {}

    record Request(String method, String path) {}

    record Rule(
            String name,
            String method,
            String pathPattern,
            String requirement
    ) {
        boolean matches(Request request) {
            if (!method.equals("*") && !method.equals(request.method())) {
                return false;
            }

            if (pathPattern.equals("/**")) {
                return true;
            }
            if (pathPattern.endsWith("/**")) {
                String root = pathPattern.substring(
                    0, pathPattern.length() - 3
                );
                return request.path().equals(root)
                    || request.path().startsWith(root + "/");
            }
            return request.path().equals(pathPattern);
        }

        boolean allows(Actor actor) {
            return switch (requirement) {
                case "PERMIT_ALL" -> true;
                case "DENY_ALL" -> false;
                case "AUTHENTICATED" -> actor.authenticated();
                default -> actor.authenticated()
                    && actor.authorities().contains(requirement);
            };
        }
    }

    static String decide(
            List<Rule> rules, Actor actor, Request request
    ) {
        for (Rule rule : rules) {
            if (rule.matches(request)) {
                String decision = rule.allows(actor)
                    ? "ALLOW" : "DENY";
                return decision + " via " + rule.name();
            }
        }
        return "DENY via no-match";
    }

    public static void main(String[] args) {
        Actor anonymous = new Actor(false, Set.of());
        Actor reader = new Actor(true, Set.of("reports:read"));
        Actor admin = new Actor(true, Set.of("ROLE_ADMIN"));

        Request publicReport = new Request(
            "GET", "/api/reports/public/help"
        );
        Request adminReport = new Request(
            "GET", "/api/reports/admin/audit"
        );
        Request annualReport = new Request(
            "GET", "/api/reports/annual"
        );
        Request writeReport = new Request(
            "PATCH", "/api/reports/annual"
        );

        Rule generalRead = new Rule(
            "reports-general", "GET",
            "/api/reports/**", "reports:read"
        );
        Rule adminOnly = new Rule(
            "reports-admin", "GET",
            "/api/reports/admin/**", "ROLE_ADMIN"
        );
        Rule publicOnly = new Rule(
            "reports-public", "GET",
            "/api/reports/public/**", "PERMIT_ALL"
        );
        Rule denyFallback = new Rule(
            "fallback", "*", "/**", "DENY_ALL"
        );

        // SAI: rule tổng quát che các ngoại lệ đặc biệt.
        List<Rule> wrong = List.of(
            generalRead, adminOnly, publicOnly, denyFallback
        );

        // ĐÚNG: ngoại lệ riêng trước, luật chung sau.
        List<Rule> fixed = List.of(
            publicOnly, adminOnly, generalRead, denyFallback
        );

        System.out.println("Wrong reader-admin: "
            + decide(wrong, reader, adminReport));
        System.out.println("Wrong anonymous-public: "
            + decide(wrong, anonymous, publicReport));
        System.out.println("Wrong admin-admin: "
            + decide(wrong, admin, adminReport));

        System.out.println("Fixed reader-admin: "
            + decide(fixed, reader, adminReport));
        System.out.println("Fixed admin-admin: "
            + decide(fixed, admin, adminReport));
        System.out.println("Fixed anonymous-public: "
            + decide(fixed, anonymous, publicReport));
        System.out.println("Fixed reader-annual: "
            + decide(fixed, reader, annualReport));
        System.out.println("Fixed anonymous-annual: "
            + decide(fixed, anonymous, annualReport));
        System.out.println("Fixed reader-PATCH: "
            + decide(fixed, reader, writeReport));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac FirstMatchRulesDemo.java
java FirstMatchRulesDemo
```

Kết quả **chính xác**:

```text
Wrong reader-admin: ALLOW via reports-general
Wrong anonymous-public: DENY via reports-general
Wrong admin-admin: DENY via reports-general
Fixed reader-admin: DENY via reports-admin
Fixed admin-admin: ALLOW via reports-admin
Fixed anonymous-public: ALLOW via reports-public
Fixed reader-annual: ALLOW via reports-general
Fixed anonymous-annual: DENY via reports-general
Fixed reader-PATCH: DENY via fallback
```

Ý nghĩa:
1. Ở thứ tự sai, user chỉ có `reports:read` vào được URL admin; đó là **mở rộng quyền ngoài ý định**.
2. Khách vô danh không đọc được report công khai dù ứng dụng đã viết rule `permitAll` ở bên dưới.
3. Admin thậm chí có thể bị từ chối khi không mang authority `reports:read`, vì rule admin không đến lượt xử lý.
4. Sau khi sửa, rule admin và public được áp dụng trước rule báo cáo chung.
5. `PATCH` không khớp rule `GET` nào nên bị fallback `denyAll`.

**Giới hạn demo:** `Rule.matches` tự cài chỉ xử lý exact path và dạng suffix `/**`; nó không thể thay thế Spring MVC matcher, không có servlet path, query, URL decoding, dispatcher type, security context, JWT hoặc cache. Trong Spring, **hãy kiểm thử matcher của version đang chạy** thay vì mang hàm `matches` của demo vào production.

## 13. Đọc kết quả của một request theo từng bước

Giả sử cấu hình đúng ở mục 2.

### Tình huống A — GET báo cáo công khai

```text
GET /api/reports/public/help
1. requestMatchers(GET, "/api/reports/public/**")? YES
2. permitAll() -> ALLOW ở HTTP authorization
3. Không xét rule admin/report-read bên dưới
4. Controller/service tiếp tục theo các filter và bảo vệ khác
```

`permitAll()` không có nghĩa tắt toàn bộ bảo mật. CSRF, session, authentication filter hoặc custom filter vẫn có thể hoạt động theo cấu hình. Với GET thuần đọc, CSRF thường không phải yêu cầu nhưng handler phải tránh làm side effect trái chuẩn.

### Tình huống B — User thường gọi URL admin

```text
GET /api/reports/admin/audit
1. public matcher? NO
2. admin matcher? YES
3. hasRole("ADMIN") -> cần ROLE_ADMIN
4. Alice chỉ có reports:read -> DENY
5. Không thử general "/api/reports/**" để nhận ALLOW
```

Đây là điểm then chốt: **DENY tại rule đã được chọn không khiến engine thử rule kế tiếp**.

### Tình huống C — User có quyền đọc report thông thường

```text
GET /api/reports/annual
1. public matcher? NO
2. admin matcher? NO
3. general reports matcher? YES
4. hasAuthority("reports:read") -> ALLOW
5. Service vẫn xét tenant, owner, visibility nếu đó là tài nguyên có hạn chế
```

### Tình huống D — Method không được khai báo

```text
PATCH /api/reports/annual
1. Các matcher GET? NO
2. anyRequest()? YES
3. denyAll() -> DENY
```

Đừng mặc định rằng một rule GET dành cho một path cũng bảo vệ hoặc cho phép POST/PATCH/DELETE trên chính path đó. Cần định nghĩa quyền cho từng loại thao tác.

## 14. permitAll, authenticated, hasAuthority, hasRole và denyAll là quyết định khác nhau

| Luật | Ý nghĩa tại bước HTTP authorization | Điều nó không đảm bảo |
| --- | --- | --- |
| `permitAll()` | Cho phép request phù hợp mà không yêu cầu authority cụ thể | Không tắt toàn filter, không cam kết các method/service không tự từ chối |
| `authenticated()` | Yêu cầu danh tính được Spring Security coi là authenticated theo trust rules | Không kiểm tra role/permission hoặc quyền resource |
| `fullyAuthenticated()` | Yêu cầu mức authentication đầy đủ, không chỉ remember-me | Không thay thế policy nghiệp vụ |
| `hasAuthority("x")` | Kiểm tra authority string `x` | Không suy diễn role hierarchy nếu chưa cấu hình |
| `hasRole("ADMIN")` | Mặc định kiểm tra authority `ROLE_ADMIN` | Không bảo đảm quyền trên mọi tenant/object |
| `denyAll()` | Từ chối mọi request đến rule này | Không tự bảo vệ URL ngoài SecurityFilterChain |
| Custom manager | Quyết định theo logic do ứng dụng quy định | Chỉ đúng nếu dữ kiện và thứ tự matcher chính xác |

Một role không tự động mang tất cả quyền chỉ vì tên nghe “cao hơn”. Ví dụ `ROLE_ADMIN` và `reports:read` là hai authority khác nhau; `hasRole("ADMIN")` theo mặc định kiểm tra `ROLE_ADMIN`, còn `hasAuthority("reports:read")` tìm đúng chuỗi ấy.

Những vấn đề này thường làm đội phát triển “sửa” bằng cách nới `/api/**.permitAll()`. Cách đó chỉ che lỗi cấu hình trước mắt và có thể mở lỗ hổng lớn hơn. Hãy tìm rule thực sự được chọn và xác nhận principal có authority phù hợp.

## 15. Luật cụ thể trước luật chung trong một màn hình quản trị

Một cấu hình phổ biến khác:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/dashboard/status")
        .permitAll()
    .requestMatchers("/dashboard/admin/**")
        .hasRole("ADMIN")
    .requestMatchers("/dashboard/**")
        .authenticated()
    .anyRequest().denyAll()
);
```

Luồng này có ba mục đích:
- Cho phép xem status công khai mà không phải đăng nhập.
- Phân quyền mạnh hơn cho khu vực admin.
- Yêu cầu đăng nhập cho phần dashboard còn lại.

Nếu đảo `/dashboard/**.authenticated()` lên trước, người đã đăng nhập có thể đi tới đường dẫn `/dashboard/admin/**` mà không qua kiểm tra role admin tại HTTP layer. Nếu đặt `/dashboard/**.hasRole("USER")` lên trước, status công khai có thể bị chặn.

**Không phải mọi route admin đều phải được cho phép nếu có ROLE_ADMIN**. Ví dụ trang thay đổi quyền hoặc thực hiện giao dịch có thể cần MFA, approval, separation-of-duties và resource policy. HTTP layer chỉ là một phần của chuỗi quyết định.

## 16. Những trường hợp trùng lặp dễ bỏ sót

### 16.1. Admin trước API chung

Sai:

```java
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Đúng theo ý định admin bảo vệ riêng:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
```

### 16.2. API read-only public trước API cần quyền

Sai:

```java
.requestMatchers("/api/catalog/**").hasAuthority("catalog:read")
.requestMatchers(HttpMethod.GET, "/api/catalog/public/**").permitAll()
```

Nếu public thật sự là ngoại lệ của rule catalog, đảo lại hai rule này. Đồng thời kiểm soát method để không mở POST/PATCH vào public path.

### 16.3. Exact endpoint trước prefix

```java
.requestMatchers(HttpMethod.GET, "/api/users/me")
    .authenticated()
.requestMatchers(HttpMethod.GET, "/api/users/**")
    .hasRole("ADMIN")
```

Nếu “me” cho user thường xem chính hồ sơ của mình, cần đặt `/me` trước vùng admin rộng. Nhưng service vẫn phải ràng buộc hồ sơ theo **principal thật**, không cho client đổi ID sang người khác.

### 16.4. Path đặc biệt và path tham số

```java
.requestMatchers(HttpMethod.GET, "/api/orders/search")
    .hasAuthority("orders:search")
.requestMatchers(HttpMethod.GET, "/api/orders/*")
    .hasAuthority("orders:read")
```

Phải test thật khi controller có cả `/search` và `/{orderId}`. Dạng matcher wildcard và kiểu biến đường dẫn có thể phụ thuộc cách Spring Security chọn matcher trong version hiện tại.

### 16.5. Health check trước luật yêu cầu đăng nhập

```java
.requestMatchers(HttpMethod.GET, "/healthz").permitAll()
.anyRequest().authenticated()
```

Việc mở health là quyết định triển khai, không phải mặc định. Endpoint chứa thông tin nhạy cảm như dependencies, env hay metrics cần quyền và giới hạn truy cập riêng.

### 16.6. Error/forward dispatch

Nếu ứng dụng phải cho phép trang lỗi được render cho cả request bị từ chối, có thể cần rule cho dispatcher type như `ERROR`/`FORWARD` với phạm vi thích hợp. Hãy đặt rule này trước `anyRequest` khi có lý do chính đáng và test hành vi. Không mặc định mở mọi dispatch chỉ để loại bỏ lỗi 403 mà chưa hiểu tác động.

## 17. Matcher của Spring cần được kiểm thử với URL thực

Có các biến thể matcher như path patterns cho Servlet/MVC, `AntPathRequestMatcher` trong những phiên bản/ứng dụng cũ, và custom `RequestMatcher`. Các phiên bản Spring Security khác nhau có quy ước/khuyến nghị khác nhau về matcher. **Không bảo đảm** mẫu `/api/items/**` có hành vi giống hệt nhau ở mọi stack, mọi servlet path và mọi cấu hình.

Các chiều biến thiên đáng kiểm tra:
- Exact path `/api/items`, path con `/api/items/42`, trailing slash `/api/items/`.
- Path segment `*` so với `**` và tên biến `{id}` trong framework/matcher thực tế.
- Servlet path/context path khi triển khai dưới prefix.
- HTTP method HEAD/OPTIONS so với GET, và method override nếu ứng dụng hỗ trợ.
- Path có ký tự encode, dấu chấm, dấu phân cách không chuẩn hoặc chuỗi dễ gây nhầm.
- Dispatcher type như REQUEST/ERROR/FORWARD/ASYNC.
- Reverse proxy/path rewrite trước khi request tới Servlet container.
- MVC controller mapping và Security matcher có thực sự đồng ý về path hay không.

Không lấy việc `MockMvc` chạy được một URL chuẩn làm bằng chứng rằng các biến thể xấu không thể bypass. Test cần bao phủ những đường dẫn mà ứng dụng và reverse proxy thực sự chấp nhận. Nếu có custom matcher, hãy kiểm thử riêng matcher trước khi dùng nó như biên bảo mật.

## 18. RequestMatchers không phải là các rule cộng dồn

Một cấu hình như:

```java
.requestMatchers("/api/orders/**").authenticated()
.requestMatchers("/api/orders/**").hasAuthority("orders:read")
```

**Không có nghĩa** “phải đăng nhập **và** có orders:read”. Matcher thứ nhất đã khớp mọi URL thuộc cùng tập, nên rule thứ hai không có cơ hội quyết định.

Để yêu cầu một authority, trong bối cảnh Spring Security thông thường `hasAuthority("orders:read")` trên một `Authentication` đáng tin đã bao hàm quyền được nạp từ cơ chế xác thực phù hợp. Nếu chính sách cần mức xác thực đặc biệt cùng một permission, hãy dùng composite `AuthorizationManager`, biểu thức method policy hay helper phù hợp, thay vì viết hai matcher trùng nhau và mong chúng cộng lại.

Có thể tạo custom rule phối hợp điều kiện:
- Có authority `orders:read`.
- Là thành viên tenant.
- Có MFA level đúng yêu cầu.
- Resource thuộc phạm vi có quyền đọc.

Nhưng không nên nhét mọi điều kiện object vào request matcher khi chưa có resource thật; service/policy vẫn thường là vị trí rõ ràng hơn.

## 19. Thứ tự matchers không thay đổi thứ tự xử lý toàn bộ filter

Một hiểu lầm khác: viết `permitAll` lên đầu không làm `CsrfFilter`, authentication filters, `CorsFilter` hay một custom filter không liên quan bị bỏ qua. `authorizeHttpRequests` tạo luật cho **bước authorization request** của chain được chọn.

Ví dụ:
- `POST` có thể bị CSRF chặn trong ứng dụng dựa trên session dù matcher sau đó là `permitAll`.
- Bearer token sai có thể bị authentication filter từ chối trước khi logic permitAll có cơ hội cho request công khai đi tiếp, tùy filter/token handling.
- CORS preflight có thể cần cấu hình trước authorization, vì request OPTIONS không mang cookie/token theo cách như request chính.
- Custom filter nằm trước `AuthorizationFilter` có thể tự trả response hoặc ném exception bất kể rule định nghĩa bên dưới.

Vì vậy, nếu test thấy 401/403, chưa thể kết luận “rule cụ thể chưa thắng rule tổng quát” cho đến khi xác định **chain**, **filter**, **matcher**, **authentication** và **handler** thực sự đã tham gia.

## 20. Ma trận test: thứ tự đúng phải có cả positive và negative

Ví dụ cấu hình ở mục 2. Tạo bộ test sau:

| Request | Principal | Kỳ vọng |
| --- | --- | --- |
| GET public report | Anonymous | ALLOW |
| GET public report | Đã đăng nhập | ALLOW |
| GET admin report | `ROLE_ADMIN` | ALLOW |
| GET admin report | Chỉ `reports:read` | DENY |
| GET admin report | Chỉ `ROLE_USER` | DENY |
| GET annual report | `reports:read` | ALLOW |
| GET annual report | Chỉ `ROLE_ADMIN` | DENY nếu không map sang `reports:read` |
| GET annual report | Anonymous | DENY |
| PATCH annual report | `reports:read` | DENY |
| POST public report | Anonymous | DENY |
| GET route chưa khai báo | Đã đăng nhập | DENY |

Hai test có khả năng bắt lỗi thứ tự tốt nhất:
1. **User chỉ có quyền chung không được vào endpoint đặc biệt** (kiểm tra không bị bypass).
2. **Anonymous vẫn vào đúng endpoint công khai** (kiểm tra ngoại lệ không bị che).

Nếu chỉ test user admin gọi endpoint admin thành công, bạn có thể **không phát hiện** rằng user thường cũng vào được do một matcher `/api/**.authenticated()` đặt trước.

### Ví dụ MockMvc kiểm tra rule HTTP

Đoạn sau là **test snippet Spring Security Test**, không phải một chương trình Java standalone: cần `MockMvc`, controller thật hoặc fixture phù hợp, dependency `spring-security-test` và cấu hình `SecurityFilterChain` như đang kiểm thử.

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void readerCannotAccessAdminReport() throws Exception {
    mvc.perform(get("/api/reports/admin/audit")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("reports:read")
            )))
       .andExpect(status().isForbidden());
}

@Test
void adminCanAccessAdminReport() throws Exception {
    mvc.perform(get("/api/reports/admin/audit")
            .with(user("admin").roles("ADMIN")))
       .andExpect(status().isOk());
}

@Test
void anonymousCanReadPublicReport() throws Exception {
    mvc.perform(get("/api/reports/public/help"))
       .andExpect(status().isOk());
}
```

Các test trên giả định endpoint tồn tại, trả 200 khi được phép và không có handler/policy khác từ chối; import JUnit, `SimpleGrantedAuthority` và cấu hình test không được trình bày đầy đủ. Trong ứng dụng thật, nên verify controller/service có được gọi không để phân biệt DENY tại HTTP và từ chối do policy business.

### Test method không được vô tình mở

Với route `POST/PATCH/DELETE`, cần test ngoài “không có quyền” còn phải xác nhận **không có side effect**. Nếu CSRF đang bật, cung cấp CSRF token hợp lệ cho test không dùng bearer, để tránh một test 403 pass vì thiếu CSRF nhưng lại che lỗi thứ tự authorization.

```java
// Chỉ là phần minh họa trong test có MockMvc được cấu hình.
mvc.perform(patch("/api/reports/annual")
        .with(csrf())
        .with(user("reader").authorities(
            new SimpleGrantedAuthority("reports:read")))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"changed\"}"))
   .andExpect(status().isForbidden());
```

Nếu endpoint PATCH không tồn tại, response có thể 404/405; phải xây fixture/controller thực và assert đúng hợp đồng thay vì buộc 403 một cách máy móc.

## 21. Test nhiều SecurityFilterChain: tránh “chain tổng quát che chain admin”

Giả sử có:
- Chain A: `securityMatcher("/api/**")`, `@Order(1)`, yêu cầu authenticated.
- Chain B: `securityMatcher("/api/admin/**")`, `@Order(2)`, yêu cầu admin.

Khi đó request admin sẽ vào chain A trước. Test URL admin với user chỉ có authenticated giúp phát hiện lỗ hổng. Sửa bằng cách đặt chain B trước, hoặc đưa rule admin cụ thể vào chain A.

**Không chỉ kiểm tra HTTP status**, cần biết chain đã chọn:
- Bật log Spring Security ở môi trường dev/test khi cần.
- Quan sát filter chain tương ứng.
- Tạo test anonymous, reader, admin, và request ngoài mọi chain.
- Định nghĩa fallback chain nếu hệ thống yêu cầu mọi request đều đi qua Spring Security.
- Kiểm tra sự khác nhau giữa management port/actuator, ứng dụng MVC và API gateway ngoài ứng dụng.

Có thể dùng `FilterChainProxy` trong test để kiểm tra chain hiện hành theo setup phù hợp, nhưng tránh viết test phụ thuộc quá sâu vào implementation khi behavioral test đã đủ. Với lỗi bảo mật, test contract + test policy resource + test cấu hình matcher sẽ đáng tin hơn chỉ nhìn annotation.

## 22. Migration và bảo trì: thêm route mới có thể làm đổi nghĩa rule cũ

Một thay đổi “tưởng chỉ là thêm một endpoint” có thể tạo giao nhau:

**Ban đầu:**

```java
.requestMatchers("/api/docs/**").hasAuthority("document:read")
.anyRequest().denyAll()
```

**Về sau thêm:**

```java
.requestMatchers("/api/docs/**").hasAuthority("document:read")
.requestMatchers("/api/docs/admin/**").hasRole("ADMIN")
.anyRequest().denyAll()
```

Dòng admin nằm sau có thể vô tác dụng với request admin. Code review cần hỏi **route mới là tập con của matcher cũ nào?** Nếu là tập con và cần policy khác, đưa rule hẹp lên trước.

Một quy trình thay đổi tốt:

1. Liệt kê route, method và quyền mong muốn.
2. Xác định các `requestMatchers` đang bao phủ route mới, đặc biệt `/api/**` và `anyRequest`.
3. Đặt rule mới trước những matcher rộng hơn **nếu overlap và policy khác**.
4. Chạy test đại diện cho cả rule mới và rule cũ, không chỉ happy path.
5. Xác minh không vô tình mở route cùng path nhưng method khác.
6. Với nhiều chain, xem chain nào được chọn **trước khi** chỉnh rule trong một chain.
7. Kiểm tra policy ở method/domain; URL ALLOW không phải thay thế quyền trên dữ liệu.

**Review tip:** những rule `permitAll()` và `authenticated()` với wildcard rộng cần được nhìn như điểm thay đổi risk cao, bởi chúng có thể che nhiều rule nhạy cảm nằm phía dưới.

## 23. Phân quyền trong service vẫn phải gánh trách nhiệm của dữ liệu

Dù thứ tự HTTP rule hoàn toàn đúng, endpoint `GET /api/reports/42` vẫn có thể dính IDOR nếu user có `reports:read` đọc được object tenant khác. Do đó, bảo vệ nhiều lớp nên có:

```text
HTTP layer:
  GET /api/reports/** -> reports:read

Application layer:
  actor = verified principal + tenant context
  report = load id=42 within actor's authorized tenant
  check actor canRead(report)
  ensure content/status/visibility rules
  then serialize report

Data layer:
  query scoped, least-privilege DB access,
  consistency for concurrent changes
```

Đặt `/api/reports/admin/**` trước `/api/reports/**` là điều kiện cần của HTTP authorization khi hai rule giao nhau; nó không giải quyết quyền của từng document, invoice hoặc project.

Với endpoint danh sách và export, cần lọc theo scope **ngay từ truy vấn** khi thích hợp. Tải hàng nghìn record rồi lọc sau có thể làm rò metadata, sai pagination và tăng N+1 query. Tương tự, endpoint download file hoặc presigned URL cần cùng policy với endpoint xem metadata.

## 24. 401, 403 và 404 phụ thuộc nơi bị từ chối

Không nên suy đoán sai rule chỉ từ status:

| Trường hợp | Nguyên nhân | HTTP thông thường |
| --- | --- | --- |
| Anonymous vào endpoint bắt đăng nhập | Thiếu authentication phù hợp | 401 với bearer API; có thể redirect với form login |
| Đã đăng nhập nhưng thiếu authority | Authorization rule từ chối | Thường 403 |
| Sai CSRF token khi ghi qua session | `CsrfFilter` chặn | Thường 403 |
| Resource không tồn tại | Domain/query không tìm thấy | 404 |
| Resource tồn tại nhưng muốn che sự tồn tại khỏi người không có quyền | Chính sách resource | Có thể 404 hoặc 403 theo contract |
| Request không có controller mapping | Không có endpoint để phục vụ | 404/405 tùy method/mapping |
| Không chain phù hợp hoặc filter custom phản hồi | Cấu hình chain/filter | Kết quả tùy ứng dụng; có thể là lỗ hổng nếu không bảo vệ |

`ExceptionTranslationFilter` phối hợp `AuthenticationEntryPoint` và `AccessDeniedHandler` cho các ngoại lệ bảo mật đi qua phạm vi xử lý tương ứng. Controller advice, proxy, filter tùy biến và response đã commit có thể thay đổi kết quả. Hãy kiểm chứng đúng **rule và chain thực tế**, không gán mọi 403 cho “thứ tự sai”.

## 25. Các lỗi điển hình và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `/api/**.authenticated()` đứng trước `/api/admin/**.hasRole("ADMIN")` | User thường có thể qua HTTP admin | Đặt matcher admin trước hoặc chọn chain đúng |
| `/public/**.permitAll()` đứng sau `/**.authenticated()` | Endpoint công khai bị yêu cầu login | Đặt public exception trước |
| `/api/**.permitAll()` trước mọi rule chuyên biệt | Vô hiệu nhiều giới hạn HTTP | Giới hạn public theo path/method, fallback deny |
| `GET` public bị khai báo không có `HttpMethod` | Có thể mở cả write method | Chỉ permit GET/HEAD cần thiết, test POST/PATCH |
| Hai matcher giống nhau, mong chúng AND | Rule thứ hai không được áp dụng | Viết một rule kết hợp hoặc policy |
| Chain `/api/**` đứng trước chain `/api/admin/**` | Chain admin không được chọn | Sắp `@Order` cho chain hẹp trước |
| Không có fallback chain | URL ngoài chain có thể không được Spring Security bảo vệ | Thiết kế chain phù hợp/default |
| Dùng `authenticated()` như quyền chức năng | Mọi user đã login có thể tới route nhạy cảm | Dùng role/authority và resource policy |
| Nghĩ `hasRole("ADMIN")` so chuỗi `ADMIN` | DENY bất ngờ | Hiểu `ROLE_` prefix mặc định |
| Chỉ bảo vệ URL, bỏ service | Job/GraphQL/bypass HTTP có thể vào use case | Method/domain policy và test alternate entry points |
| Test chỉ happy path cho admin | Không phát hiện reader được vào admin | Negative test với authority thấp hơn |
| Test 403 khi thiếu CSRF token | False positive về authorization | Cung cấp CSRF hợp lệ, verify điểm deny |
| Bỏ qua path rewrite/trailing slash | Matcher khác controller thật | Test thực với servlet path/proxy/version |
| Kiểm tra role rồi bỏ scope tenant | IDOR/BOLA | Query và policy trên object/tenant |
| Đổi thứ tự mà không test route cũ | Regression công khai/riêng tư | Ma trận request × method × principal |

## 26. Checklist review khi thấy requestMatchers mới

Trước khi merge một thay đổi `SecurityFilterChain` hoặc `authorizeHttpRequests`:

1. **Chain nào xử lý URL?** Kiểm tra `securityMatcher` và `@Order`, đặc biệt nhiều chain giao nhau.
2. **Matcher nào khớp đầu tiên?** Lập trace cho request đại diện trước khi đọc quyền dưới nó.
3. **Có matcher rộng hơn ở phía trên không?** Nếu có, rule mới có thể không bao giờ được dùng.
4. **Ngoại lệ public có đúng method/path không?** Không vô tình công khai POST/DELETE.
5. **Admin và chức năng nhạy cảm có đứng trước fallback rộng không?** Test negative với user thường.
6. **`anyRequest` đã được khai báo cuối và có mức chặn chủ đích chưa?**
7. **Với role/authority, prefix và quyền map đúng chưa?** `ROLE_ADMIN` khác `reports:read`.
8. **Route ngoài SecurityFilterChain có được bảo vệ không?** Nếu không thì lý do là gì?
9. **Các path edge case đã test chưa?** Path gốc, path con, slash, method, context path, custom matcher.
10. **HTTP ALLOW đã có domain policy theo resource/tenant chưa?**
11. **Test đã loại nhiễu CSRF/authentication/CORS chưa?** Chứng minh luật authorization thực sự chặn.
12. **Thêm route mới có thay đổi tính công khai của route cũ không?** Chạy regression test.
13. **Audit và log có đủ để biết chain/rule nào deny mà không lộ secret không?**

### Bài tập tự kiểm tra

**Câu 1:** Có các rule:

```java
.requestMatchers("/admin/**").hasRole("ADMIN")
.requestMatchers("/**").authenticated()
```

User có `ROLE_USER` vào `/admin/users` có qua tầng HTTP authorization không?  
→ **Không.** Rule admin khớp đầu tiên và user không có `ROLE_ADMIN`.

**Câu 2:** Nếu đảo hai rule ở câu 1, kết quả thế nào?  
→ `/**.authenticated()` khớp trước. User đã đăng nhập có thể được cho qua HTTP authorization tại URL admin; rule phía dưới không siết thêm. Đây là lỗi nguy hiểm.

**Câu 3:** Có `GET /public/help` cần công khai nhưng fallback `anyRequest().authenticated()`. Đặt gì ở trước?  
→ `requestMatchers(HttpMethod.GET, "/public/**").permitAll()` trước catch-all. Chỉ mở các method có chủ đích.

**Câu 4:** Một app có chain `/api/**` ở `@Order(1)` và chain `/api/admin/**` ở `@Order(2)`. Rule admin ở chain sau có chắc chắn áp dụng không?  
→ **Không.** Chain `/api/**` khớp trước. Cần đổi chain order hoặc đưa admin rule vào chain được chọn.

**Câu 5:** Một user có `reports:read` nhưng báo cáo 42 thuộc tenant khác. HTTP matcher cho phép `GET /api/reports/**`. User có được đọc báo cáo 42 không?  
→ **Không**, nếu policy domain giới hạn đúng tenant. HTTP permission chung không thay thế object authorization.

**Câu 6:** Một test POST trả 403, nhóm kết luận vì matcher POST yêu cầu role editor. Kết luận đã chắc chưa?  
→ **Chưa.** 403 có thể do CSRF, authentication hoặc chặng khác. Test cần cố định request hợp lệ và thay authority để xác minh.

**Câu 7:** Đặt `requestMatchers("/api/reports/**").hasAuthority("reports:read")` trước `requestMatchers("/api/reports/public/**").permitAll()`. Anonymous được đọc public report không?  
→ **Không** theo first-match khi general matcher khớp trước. Đảo rule hẹp lên trên.

**Kết luận:** Khi nhiều luật HTTP cùng có thể khớp một request, **thứ tự khai báo là một phần của chính sách bảo mật**. Hãy đặt ngoại lệ/scope hẹp trước matcher bao phủ rộng nếu cần kết quả khác nhau, không trông chờ framework tự chọn “đường dẫn cụ thể nhất”. Đồng thời kiểm tra cả **thứ tự SecurityFilterChain** và **thứ tự requestMatchers**, luôn giữ fallback có chủ đích và kiểm thử các trường hợp đáng ra phải bị từ chối.

## Tài liệu tham khảo

- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Servlet Architecture / SecurityFilterChain](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — RequestMatcherDelegatingAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/intercept/RequestMatcherDelegatingAuthorizationManager.html)
- [Spring Security 6.5 — Testing HTTP Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)
