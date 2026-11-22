# RequestMatcher tùy chỉnh và tiêu chí không bỏ lọt endpoint

> **Module:** Spring Security - authorization  
> **Nhóm:** RequestMatcher  
> **Đích học tập:** Biết lúc nào phải viết `RequestMatcher` riêng, hiểu matcher được dùng để chọn `SecurityFilterChain` và chọn quy tắc `authorizeHttpRequests` khác nhau ra sao, kết hợp matcher với `AuthorizationManager` để giữ nguyên quyền tối thiểu, và thiết lập checklist/test chứng minh các endpoint quan trọng không bị bỏ lọt.

## 1. Bài toán: matcher không khớp có thể mở đường cho quyền yếu hơn

Giả sử hệ thống quản lý báo cáo:

```http
GET /api/reports/42
GET /api/reports/42?view=preview
POST /api/reports/42/export
GET /internal/metrics
```

Chức năng đọc bình thường cần `reports:read`; bản preview nhạy cảm cần **cả** `reports:read` và `reports:preview`. Ứng dụng có thể tạo matcher custom chỉ đúng khi query parameter `view` bằng `preview` rồi gắn quyền mạnh cho matcher đó. Nhưng nếu controller nhận thêm alias/format khác để bật preview, custom matcher không khớp và request rơi xuống một rule `authenticated()` chung, hệ thống đã vô tình cho phép người thiếu quyền preview vượt qua lớp bảo vệ HTTP.

Một lỗi khác ở cấp cao hơn: chỉ tạo `SecurityFilterChain` áp dụng `/api/**` mà không có fallback. Khi request đến `/internal/metrics`, nếu không chain nào khác khớp, **các Spring Security filters trong cấu hình đó không chạy**. `anyRequest().denyAll()` bên trong chain API không thể giúp cho URL ở ngoài chain.

Vì vậy, có ba ranh giới không được nhầm:

1. **Chain coverage:** request có được bảo vệ bởi một `SecurityFilterChain` phù hợp không?
2. **Rule coverage:** trong chain đó, rule được chọn có yêu cầu đúng authority/role không?
3. **Resource coverage:** sau khi đi vào service, principal có quyền trên **object thực** không (tenant, owner, ACL, trạng thái)?

Một matcher chỉ quyết định “request có thuộc tập này không?”. Nó **không thay thế** bước xác thực danh tính, quyết định quyền hoặc kiểm tra tài nguyên nghiệp vụ.

## 2. Hai tầng first-match: chọn chain rồi chọn rule

```text
HTTP request
   |
   v
DelegatingFilterProxy → FilterChainProxy
   |
   | (A) duyệt SecurityFilterChain theo thứ tự
   |     chọn chain ĐẦU TIÊN có securityMatcher khớp
   v
SecurityFilterChain được chọn
   |
   | authentication, SecurityContext, CSRF, filters khác
   v
AuthorizationFilter
   |
   | (B) duyệt requestMatchers trong chain theo thứ tự khai báo
   |     chọn rule ĐẦU TIÊN có matcher khớp
   v
AuthorizationManager của rule
   |
   +---- DENY -> AccessDeniedException / HTTP handler
   |
   +---- ALLOW -> controller -> service -> domain policy
```

| Điểm gắn matcher | Ý nghĩa | Nếu `matches(request) == false` |
| --- | --- | --- |
| `http.securityMatcher(custom)` | Chain này có áp dụng không? | Thử chain ưu tiên thấp hơn; không có chain nào có thể dẫn tới request không được Spring Security bảo vệ |
| `authorizeHttpRequests(...requestMatchers(custom))` | Luật authorization này có áp dụng không? | Chuyển sang rule phía sau trong **cùng chain** |
| `web.ignoring()` | Yêu cầu bỏ qua Spring Security cho URL này | Không nên dùng tùy tiện để public endpoint; thông thường ưu tiên `permitAll` |
| `@PreAuthorize`/domain policy | Chốt quyền khác, ở method hoặc trên resource | Không thể thay thế việc xác định chain/rule HTTP chính xác |

**First-match không phải most-specific-match.** Spring Security không mặc định gom mọi rule khớp thành AND. Một rule tổng quát đứng trước rule hẹp có thể khiến rule hẹp không bao giờ được chạy.

**Mấu chốt:** nếu tất cả chain đều có `securityMatcher` hẹp, đừng trông chờ một `anyRequest().denyAll()` trong từng chain sẽ bảo vệ toàn ứng dụng. Nên có fallback chain không đặt matcher hẹp nếu mục tiêu là bảo vệ mọi request.

## 3. RequestMatcher là interface gì?

Trong Spring Security Servlet 6.5, interface `org.springframework.security.web.util.matcher.RequestMatcher` là một functional interface; contract chính:

```java
boolean matches(jakarta.servlet.http.HttpServletRequest request);
```

Nó còn có default method `matcher(HttpServletRequest)` trả `RequestMatcher.MatchResult`, chứa trạng thái khớp và map các biến path được trích nếu implementation hỗ trợ. `MatchResult` có các method như `isMatch()`, `getVariables()` và factory `match()`, `match(Map)`, `notMatch()`.

Một lambda đơn giản:

```java
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher previewParam =
    request -> "preview".equals(request.getParameter("view"));
```

Dòng trên chỉ trả true khi tham số có giá trị phù hợp. Nó **không** xét:
- URL/path nào đang được gọi;
- request là GET hay POST;
- user đã xác thực hay chưa;
- user có authority `reports:preview` hay không;
- resource thuộc tenant/owner nào.

Lambda nhận hành vi mặc định của `matcher(request)`: thông thường không trích path variables, nên `MatchResult#getVariables()` không tự có `{id}` từ một lambda chỉ implement `matches`. Nếu cần biến đường dẫn, dùng matcher path có hỗ trợ hoặc custom class override `matcher`.

**Đừng nhầm `RequestMatcher` với `AuthorizationManager<RequestAuthorizationContext>`**. Matcher lựa chọn tập request; manager kiểm tra Authentication và đưa quyết định.

## 4. Ưu tiên matcher có sẵn trước khi tùy chỉnh

| Yêu cầu | Gợi ý | Lưu ý |
| --- | --- | --- |
| Path + HTTP method | `PathPatternRequestMatcher` ở 6.5+ | Kiểm tra context path, servlet path và parser |
| Hai điều kiện phải cùng khớp | `AndRequestMatcher` | Đây là AND của **matcher**, không phải AND của authority |
| Một trong hai loại request | `OrRequestMatcher` | Không vô tình tạo nhánh quá rộng |
| Loại trừ một loại request | `NegatedRequestMatcher` | Negative space thường dễ bao phủ route mới không dự kiến |
| Regex path thực sự đặc biệt | `RegexRequestMatcher` | Regex anchoring, encoding và runtime normalization |
| Dispatcher type | `dispatcherTypeMatchers` trong DSL | `REQUEST`, `ERROR`, `FORWARD` ... |
| Query/header làm thay đổi kiểu chức năng | Custom lambda hoặc class | Kiểm tra đối chiếu với cách controller diễn giải input |
| Kiểm tra role, tenant, owner | `AuthorizationManager` và domain policy | Không coi header/query tự khai là bằng chứng quyền |

Từ Spring Security 6.5, `PathPatternRequestMatcher` là hướng migration cho các matcher legacy. Spring Security 7 không còn hỗ trợ `AntPathRequestMatcher` và `MvcRequestMatcher` như các nhánh trước. Khi dùng code từ tài liệu cũ, cần đối chiếu dependency version để tránh suy đoán sai hành vi.

Đối với một chức năng nhạy cảm, path + method riêng thường dễ test và review hơn một custom matcher phụ thuộc nhiều query/header. Nếu muốn dùng custom, cần một lý do rõ ràng vì sao matchers có sẵn không biểu diễn được tập request.

## 5. Tiêu chí của một custom matcher an toàn

Một matcher ở ranh giới bảo mật nên:

1. **Khớp chính xác phạm vi:** không bao phủ route nhạy cảm khác chỉ vì cùng substring.
2. **Giới hạn đúng HTTP method:** GET công khai không kéo theo DELETE công khai.
3. **Ổn định/deterministic:** cùng request đã được chuẩn hóa cho cùng kết quả.
4. **Không side effect:** `matches` không ghi dữ liệu, gửi email, thay đổi session hoặc kích hoạt command.
5. **Không dùng client input làm chứng cứ quyền:** header `X-Role: ADMIN` chỉ là text không tin cậy.
6. **Không phụ thuộc DB/network để chọn chain:** quyền owner/tenant thuộc manager/domain; lỗi hạ tầng không được biến thành match=false rồi rơi vào policy yếu hơn.
7. **Không bị rule rộng che:** custom matcher được xét trước các matcher bao phủ nó nếu yêu cầu quyền khác nhau.
8. **Có fallback bảo thủ:** khi custom matcher bỏ sót một biến thể, endpoint nhạy cảm vẫn không được mở bởi `permitAll` hoặc `authenticated` sai phạm vi.
9. **Đúng servlet topology:** phân biệt context root, servlet prefix, reverse proxy rewrite.
10. **Có bằng chứng kiểm thử:** unit matcher, MockMvc/Servlet integration và ma trận phủ URL × method × actor.

Đặc biệt phân biệt hai kết luận: “request không thuộc nhóm này” và “request bị từ chối”. `matches == false` là kết luận thứ nhất; không tự động tương đương DENY.

## 6. Quy tắc cụ thể trước tổng quát

Cấu hình **sai**:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/reports/**").authenticated()
    .requestMatchers(previewMatcher)
        .hasAuthority("reports:preview")
    .anyRequest().denyAll()
);
```

Mọi request preview dưới `/api/reports/**` đã match rule `authenticated()` ở đầu. Người đăng nhập thông thường có thể được cho qua kiểm tra HTTP, rule preview không có tác dụng.

Đảo thứ tự là cần thiết:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(previewMatcher)
        .hasAuthority("reports:preview")
    .requestMatchers("/api/reports/**")
        .hasAuthority("reports:read")
    .anyRequest().denyAll()
);
```

Nhưng nếu muốn preview **bắt buộc phải có cả quyền đọc và preview**, chỉ `reports:preview` là chưa đủ. Phải dùng composite authorization manager hoặc policy phù hợp. Ngoài ra, nếu matcher preview bỏ sót biến thể input mà controller vẫn tạo preview, fallback `reports:read` cũng chưa đủ; cần đồng nhất contract request hoặc giữ guard trong service.

**Không cố làm cho một custom matcher “khó bypass” bằng cách chuyển tất cả URL sang `denyAll` rồi mở một vài trường hợp quá rộng.** Tốt hơn là mô hình hóa capability, route và quyền đầy đủ, với fallback rõ.

## 7. Ví dụ Spring Security 6.5+: custom matcher và quyền kết hợp

Giả sử endpoint GET `/api/reports/{id}`; query `?view=preview` là một chế độ bổ sung. Tạo matcher preview bằng AND của path/method và query:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class ReportSecurityConfiguration {

    @Bean
    SecurityFilterChain reportChain(HttpSecurity http) throws Exception {
        var paths = PathPatternRequestMatcher.withDefaults();

        RequestMatcher readReport =
            paths.matcher(HttpMethod.GET, "/api/reports/{id}");

        RequestMatcher previewReport = new AndRequestMatcher(
            readReport,
            request -> "preview".equals(request.getParameter("view"))
        );

        AuthorizationManager<RequestAuthorizationContext> readAndPreview =
            AuthorizationManagers.allOf(
                AuthorityAuthorizationManager
                    .<RequestAuthorizationContext>hasAuthority("reports:read"),
                AuthorityAuthorizationManager
                    .<RequestAuthorizationContext>hasAuthority("reports:preview")
            );

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(previewReport).access(readAndPreview)
            .requestMatchers(readReport).hasAuthority("reports:read")
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

**Đây là snippet cấu hình Spring, không phải chương trình `javac` standalone.** Chưa có authentication mechanism (JWT/session/form), controller, CSRF, resource policy hoặc error handling cụ thể.

Giải thích:
- `PathPatternRequestMatcher` giới hạn GET đúng đường dẫn report với một segment ID.
- `AndRequestMatcher` phân loại thêm chế độ preview.
- `AuthorizationManagers.allOf` yêu cầu **cả hai authority**, không phải OR.
- Matcher hẹp đứng trước matcher đọc chung.
- `anyRequest().denyAll()` từ chối phần chưa liệt kê **trong chain hiện tại**.

**Giới hạn quan trọng:** controller có thể xử lý các alias như `view=PREVIEW`, duplicate params hoặc `Accept` header khác với custom matcher. Nếu một biến thể kích hoạt preview mà matcher không khớp, người chỉ có `reports:read` có thể rơi vào rule chung. Đối với capability nhạy cảm, cần thống nhất request parser và bổ sung kiểm tra trong service hoặc dùng URL riêng.

## 8. Route riêng thường tốt hơn điều kiện query nhạy cảm

Thay vì một endpoint đa chế độ:

```text
GET /api/reports/{id}?view=preview
GET /api/reports/{id}?view=normal
```

có thể cân nhắc:

```text
GET  /api/reports/{id}          -> reports:read
GET  /api/reports/{id}/preview  -> reports:read + reports:preview
POST /api/reports/{id}/export   -> reports:read + reports:export
```

Lợi ích:
- Match path/method dễ chứng minh.
- Không có bất đồng về query duplicate/default/case.
- CI có thể có test riêng cho mỗi operation.
- API gateway và logs dễ phân biệt capability.
- Việc thêm một chế độ mới dễ review hơn.
- Domain policy nhận actor/resource và kiểm tra tenant/owner thống nhất.

Không bắt buộc tách mọi query thành URL khác; nhưng khi query hoặc header làm thay đổi mức phân quyền, độ rõ ràng của routing là lợi thế bảo mật lớn.

## 9. Viết class RequestMatcher cần trả MatchResult

Nếu cần giữ lại biến path `{id}` cho downstream manager, có thể viết class cụ thể:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpMethod;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

public final class PreviewReportMatcher implements RequestMatcher {

    private final RequestMatcher reportGet =
        PathPatternRequestMatcher.withDefaults()
            .matcher(HttpMethod.GET, "/api/reports/{id}");

    @Override
    public boolean matches(HttpServletRequest request) {
        return matcher(request).isMatch();
    }

    @Override
    public MatchResult matcher(HttpServletRequest request) {
        MatchResult pathResult = reportGet.matcher(request);

        if (!pathResult.isMatch()) {
            return MatchResult.notMatch();
        }
        if (!"preview".equals(request.getParameter("view"))) {
            return MatchResult.notMatch();
        }
        return MatchResult.match(pathResult.getVariables());
    }
}
```

Đây là Java class tích hợp **cần dependency Spring Security/Jakarta Servlet** và chỉ hợp với 6.5+ có `PathPatternRequestMatcher`; không chạy bằng JDK đơn độc. Nó chỉ xác định match, hoàn toàn không quyết định actor có quyền hay không.

Các lưu ý:
- `reportGet.matcher(request)` lấy `MatchResult` và biến path nếu thư viện cung cấp.
- `matches` gọi `matcher` để nhất quán một kết quả. Tránh đệ quy ngược khi override.
- `MatchResult.match(pathResult.getVariables())` giữ biến `id`.
- `getParameter("view")` có thể không mô tả mọi cách controller bật preview; cần test.
- Biến `id` vẫn chỉ là **input từ URL**, không phải resource đã được xác nhận quyền.
- Nếu policy cần tải document/report, dùng manager hoặc domain service trong scope tin cậy.

Một class matcher có thể được unit-test độc lập với Authentication, còn manager/policy được test với nhiều actor và object.

## 10. Sai lầm: nhập quyền vào logic matches()

Ví dụ **không an toàn**:

```java
RequestMatcher adminArea = request ->
    "/api/admin".equals(request.getHeader("X-Role"));
```

Header là dữ liệu client kiểm soát. Một client có thể gửi bất kỳ giá trị nào; nó không có khả năng chứng minh user là admin. Tệ hơn, matcher có thể không match và request rơi vào fallback yếu, gây bypass.

Một mẫu sai khác:

```java
RequestMatcher ownDocument = request ->
    request.getParameter("ownerId").equals(
        request.getParameter("currentUserId"));
```

Hai giá trị có thể cùng do client đặt, hoàn toàn không ràng buộc với principal tin cậy hoặc dữ liệu DB. Cách đúng là:
1. Matcher xác định route/method.
2. Authentication cung cấp actor ID đã xác thực.
3. Domain service tải object theo tenant từ data source đáng tin.
4. Policy kiểm tra owner/grant/trạng thái trước khi đọc hoặc ghi.

**Không query DB ngay trong matcher chỉ để xác minh owner.** Cách này trộn cơ chế chọn rule với quyết định domain, khó tái sử dụng và dễ fail-open khi I/O lỗi rồi return `false`. Một `AuthorizationManager` tùy chỉnh là điểm mở rộng phù hợp hơn khi cần quyết định phức tạp trong authorization layer.

## 11. Các điều kiện request dễ gây lệch matcher và controller

Giả sử controller hỗ trợ nhiều dạng input:

```http
GET /api/reports/42?view=preview
GET /api/reports/42?view=PREVIEW
GET /api/reports/42?view=preview&view=normal
GET /api/reports/42?view=normal&view=preview
GET /api/reports/42?view=preview%20
GET /api/reports/42
Accept: application/vnd.example.preview+json
```

Cần xác định:
- Matcher đọc `getParameter` hay `getParameterValues`? Controller dùng kiểu gì?
- Giá trị rỗng, trắng, case khác nhau được xử lý ra sao?
- Query duplicate được lấy first, last, nhiều giá trị hay rejected?
- Header Accept/Content-Type có làm thay đổi response nhạy cảm không?
- Một request không có `view` vẫn có thể trả preview theo default không?
- Reverse proxy hoặc Servlet container có normalize/URL-decode khác nhau không?

**Không khẳng định rằng tất cả biến thể trên phải khớp preview.** Kết quả phải theo contract ứng dụng, nhưng **mọi cách thực sự kích hoạt capability preview phải bị ràng buộc cùng policy**.

Nếu không thể thống nhất cách parse, nên từ chối request mơ hồ và thiết kế route riêng. Đừng để một cách decode ở filter khác cách decode của controller.

## 12. And, Or và Negated: kết hợp phạm vi chứ không kết hợp quyền

- `AndRequestMatcher(A,B)`: chỉ đúng khi A **và** B match.
- `OrRequestMatcher(A,B)`: đúng khi A **hoặc** B match.
- `NegatedRequestMatcher(A)`: đúng khi A không match.

Ví dụ:

```java
RequestMatcher preview = new AndRequestMatcher(
    reportGet,
    request -> "preview".equals(request.getParameter("view"))
);
```

Ở đây AND áp dụng cho **request conditions**. Để yêu cầu cả `reports:read` và `reports:preview`, cần dùng `AuthorizationManagers.allOf(...)` hoặc policy tương đương. Nếu dùng `hasAnyAuthority("reports:read","reports:preview")`, đó là OR và có thể cho user chỉ có một quyền đi qua.

`NegatedRequestMatcher` cần đặc biệt cẩn thận: “mọi thứ ngoài /public” là tập lớn thay đổi khi team thêm route. Dùng phủ định khi quy tắc loại trừ được chứng minh và có fallback strict; không dùng để mặc định phân quyền admin.

## 13. Chain fallback và rủi ro không có SecurityFilterChain

Chỉ có chain API:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        );
    return http.build();
}
```

Thì `GET /internal/metrics` không khớp `/api/**`. Nếu app không có chain khác, request đó có thể không được Spring Security bảo vệ. Mặc dù `anyRequest().authenticated()` nằm trong cấu hình, nó **chỉ** áp dụng trong chain API được chọn.

Fallback chain không giới hạn scope:

```java
@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll()
    );
    return http.build();
}
```

Đây là snippet định hướng; cần cấu hình đầy đủ các bean, authentication/CSRF và routes thật. Trong ứng dụng có website public, có thể có rule public cụ thể trước `denyAll`. Quan trọng là fallback **không** dùng matcher path hẹp làm mất coverage.

**Thứ tự chain:** nếu chain `/api/**` đứng trước chain `/api/admin/**`, admin chain có thể không bao giờ được chọn với URL admin. Giải pháp: chain hẹp trước chain rộng hoặc tích hợp rule admin mạnh trong chain API. Cách chọn chain có ảnh hưởng tới **toàn bộ filters**, không chỉ authorization rule.

## 14. Servlet path, context root và proxy rewrite

Một request có thể có:

```text
URL ngoài        https://example.com/portal/mvc/api/reports/42
Context root     /portal
Servlet path     /mvc
MVC mapping      /api/reports/42
App-relative     /mvc/api/reports/42
```

`PathPatternRequestMatcher` trong 6.5+ thường dùng pattern không gồm context root nhưng cần tính servlet prefix. Có thể:

```java
var mvc = PathPatternRequestMatcher.withDefaults()
    .basePath("/mvc");

RequestMatcher readReport =
    mvc.matcher(HttpMethod.GET, "/api/reports/{id}");
```

Nếu custom matcher tự dùng `request.getRequestURI().startsWith("/api/")`, nó có thể fail khi requestURI chứa `/portal/mvc`. Ngược lại, hard-code external prefix `/gateway` có thể fail khi proxy đã rewrite.

Cần kiểm tra bằng request runtime: contextPath, servletPath, pathInfo, requestURI, framework parser, proxy rewrite. Đặt test trên deployment có cấu hình thực, không suy ra từ URL browser.

## 15. Cẩn thận với GET/HEAD/POST/PATCH/DELETE/OPTIONS

Một path có thể map các operations hoàn toàn khác nhau. Nếu matcher custom chỉ nhìn path:

```java
RequestMatcher bad = request ->
    request.getRequestURI().contains("/api/reports/");
```

thì rule `hasAuthority("reports:read")` có thể bị dùng cho cả endpoint xóa/export. Đây là lỗi thiếu điều kiện method, đồng thời `contains` khớp URL không mong muốn.

Dùng matcher method-specific:

```java
var paths = PathPatternRequestMatcher.withDefaults();

RequestMatcher read =
    paths.matcher(HttpMethod.GET, "/api/reports/{id}");

RequestMatcher delete =
    paths.matcher(HttpMethod.DELETE, "/api/reports/{id}");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(delete).hasAuthority("reports:delete")
    .requestMatchers(read).hasAuthority("reports:read")
    .anyRequest().denyAll()
);
```

Nếu controller tự hỗ trợ HEAD qua GET, cần test HTTP HEAD. OPTIONS CORS preflight nên dùng cấu hình CORS chuẩn tắc, không nới `permitAll("/api/**")` cho mọi method chỉ để bỏ lỗi browser. Đối với POST/PATCH dùng cookie/session, test CSRF phải gửi token hợp lệ khi mục tiêu là chứng minh quyền, tránh 403 do CSRF che lỗi authorization.

## 16. Dispatcher type và những request cùng URL nhưng khác luồng

Một HTTP request có thể trải qua `REQUEST`, `FORWARD`, `ERROR` hoặc `ASYNC` dispatch theo Servlet/runtime. `AuthorizationFilter` có thể xét cả những dispatch này tùy cấu hình. Ví dụ một controller ném exception rồi container dispatch tới `/error`; một deny ở ERROR dispatch có thể làm response khác lỗi gốc.

Spring Security cho phép các rule dispatcher type theo policy:

```java
import static jakarta.servlet.DispatcherType.ERROR;
import static jakarta.servlet.DispatcherType.FORWARD;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(ERROR, FORWARD).permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

Đây chỉ là một lựa chọn kiến trúc, **không phải khuyến nghị mở mọi dispatch vô điều kiện**. Nếu app có forward vào endpoint nhạy cảm, phải kiểm tra đường đi thực tế và không cho phép bỏ qua chốt quyền. Với custom matcher, dispatcher type là một chiều của tập request cần kiểm thử.

## 17. Danh sách endpoint không chỉ có @GetMapping

Bề mặt ứng dụng còn gồm:
- MVC controller mapping với class-level prefix và GET/POST/PUT/PATCH/DELETE.
- Các servlet khác `DispatcherServlet`, ví dụ legacy/admin/upload.
- Spring Boot Actuator hoặc management port/context riêng.
- OAuth2 login callback, login/logout, error handling và các endpoint framework.
- GraphQL endpoint `/graphql`, nơi một URL có nhiều operation và field-level policies.
- WebSocket handshake, với authorization message/channel riêng.
- Static resources và file downloads; tránh phục vụ dữ liệu private như static content.
- Export/PDF, signed URL, bulk/batch operations.
- Reverse proxy routes, gateway rewrite hoặc aliases.
- Custom filters có thể xử lý và trả response trước controller.
- Internal endpoints như `/internal/**`.

Vì vậy, chỉ scan một tập controller không chứng minh toàn bộ bề mặt HTTP đã được bảo vệ. Đặc biệt nếu management server có port riêng, test MockMvc của ứng dụng chính không khẳng định được security ở management port.

## 18. Ma trận coverage cho một ứng dụng thật

| Endpoint hoặc nhóm | Method | Chain | Matcher/rule | Quyền tối thiểu | Domain policy | Test âm tính |
| --- | --- | --- | --- | --- | --- | --- |
| `/api/public/info` | GET | API/web | Public path GET | Public | Không lộ dữ liệu riêng | POST không tự public |
| `/api/reports/{id}` | GET | API | Read matcher | `reports:read` | Tenant + read grant | Thiếu read DENY |
| `/api/reports/{id}?view=preview` | GET | API | Custom preview hẹp | Read + preview | Tenant + preview grant | Chỉ read DENY |
| `/api/reports/{id}/export` | POST | API | Export matcher | `reports:export` và policy | Audit, hạn mức, owner | Chỉ read DENY |
| `/api/admin/users` | GET/PATCH | Admin/API | Admin matcher | `ROLE_ADMIN` | Admin scope/tenant | User thường DENY |
| `/internal/metrics` | GET | Fallback/management | Ops matcher | Ops/private policy | Không để lộ cấu hình | Anonymous DENY |
| `/error` | ERROR | Web/fallback | Dispatcher policy | Theo contract lỗi | Không lộ secrets | Lỗi gốc không bị che sai |

Từng dòng phải được **xác nhận bằng test chạy trên ứng dụng**, không chỉ dựa trên tài liệu dự kiến. Với resource riêng tư, ngoài rule HTTP còn cần test user có authority đúng nhưng object ở tenant khác vẫn bị từ chối.

Định nghĩa “đủ phủ” ở mức thực dụng:

```text
Với mọi request thuộc bề mặt private của ứng dụng:
  1. Có SecurityFilterChain khớp.
  2. Chain được chọn có rule/policy đúng.
  3. Rule đầu tiên khớp không yếu hơn yêu cầu chức năng.
  4. Actor đến từ authentication đáng tin.
  5. Tài nguyên thật được xét owner/tenant/ACL/trạng thái.
  6. Command có side effect chỉ chạy sau khi policy ALLOW.
```

Một bộ test hữu hạn không thể chứng minh tuyệt đối với mọi URL biến thể. Nhưng ma trận inventory + test positive/negative + servlet integration + review gateway làm giảm rủi ro bỏ sót.

## 19. Java 17+ chạy độc lập: rule sai, rule đúng và chain bị bỏ lọt

Ví dụ thuần Java sau **mô phỏng** first-match, quyền kết hợp và fallback chain. Nó không implement Servlet, Spring Security hay `PathPatternParser`; các request và actor là dữ liệu test đã được gán tin cậy.

Lưu file `MatcherCoverageDemo.java`:

```java
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

public class MatcherCoverageDemo {
    record Request(String method, String path, String view) {}
    record Actor(boolean authenticated, Set<String> authorities) {}
    record Rule(String name, Predicate<Request> matcher,
                String requirement) {}

    static boolean allowed(Actor actor, String requirement) {
        if (requirement.equals("DENY")) return false;
        if (requirement.equals("READ")) {
            return actor.authenticated()
                && actor.authorities().contains("reports:read");
        }
        if (requirement.equals("READ_AND_PREVIEW")) {
            return actor.authenticated()
                && actor.authorities().contains("reports:read")
                && actor.authorities().contains("reports:preview");
        }
        throw new IllegalArgumentException(requirement);
    }

    static String decide(List<Rule> rules, Actor actor,
                         Request request) {
        for (Rule rule : rules) {
            if (rule.matcher().test(request)) {
                return (allowed(actor, rule.requirement())
                    ? "ALLOW" : "DENY") + " via " + rule.name();
            }
        }
        return "DENY via no-rule";
    }

    static boolean reportGet(Request request) {
        return request.method().equals("GET")
            && request.path().startsWith("/api/reports/");
    }

    static boolean previewGet(Request request) {
        return reportGet(request)
            && "preview".equals(request.view());
    }

    public static void main(String[] args) {
        Actor reader = new Actor(true, Set.of("reports:read"));
        Actor specialist = new Actor(true,
            Set.of("reports:read", "reports:preview"));

        Request preview = new Request(
            "GET", "/api/reports/42", "preview");
        Request normal = new Request(
            "GET", "/api/reports/42", "normal");
        Request write = new Request(
            "POST", "/api/reports/42", "normal");
        Request internal = new Request(
            "GET", "/internal/metrics", "");

        Rule general = new Rule(
            "general", MatcherCoverageDemo::reportGet, "READ");
        Rule special = new Rule(
            "preview", MatcherCoverageDemo::previewGet,
            "READ_AND_PREVIEW");
        Rule deny = new Rule(
            "api-fallback", r -> true, "DENY");

        List<Rule> wrong = List.of(general, special, deny);
        List<Rule> safe = List.of(special, general, deny);

        System.out.println("Wrong reader preview: "
            + decide(wrong, reader, preview));
        System.out.println("Safe reader preview: "
            + decide(safe, reader, preview));
        System.out.println("Safe specialist preview: "
            + decide(safe, specialist, preview));
        System.out.println("Safe reader normal: "
            + decide(safe, reader, normal));
        System.out.println("Safe reader POST: "
            + decide(safe, reader, write));

        boolean apiChain =
            internal.path().startsWith("/api/");
        System.out.println("Internal covered by API chain: "
            + apiChain);
        System.out.println("Internal without fallback chain: "
            + (apiChain ? "COVERED" : "NO_SECURITY_CHAIN"));
        System.out.println("Internal with fallback chain: "
            + (apiChain ? "COVERED" : "DENY"));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac MatcherCoverageDemo.java
java MatcherCoverageDemo
```

Stdout **chính xác**:

```text
Wrong reader preview: ALLOW via general
Safe reader preview: DENY via preview
Safe specialist preview: ALLOW via preview
Safe reader normal: ALLOW via general
Safe reader POST: DENY via api-fallback
Internal covered by API chain: false
Internal without fallback chain: NO_SECURITY_CHAIN
Internal with fallback chain: DENY
```

Phân tích:
1. Thứ tự sai khiến rule đọc chung cho qua preview trước khi xét rule mạnh.
2. Thứ tự đúng từ chối reader thiếu quyền preview.
3. Specialist có cả hai authority vượt rule preview.
4. Report GET thông thường vẫn cần quyền read.
5. POST không được mở chỉ vì GET cùng path cho phép đọc.
6. `/internal/metrics` không thuộc chain giả lập `/api/**`, chứng minh một fallback chain là cần thiết nếu muốn bảo vệ mọi endpoint.

**Giới hạn:** `startsWith` trong chương trình là một mô phỏng tối giản, không xử lý servlet path, URL encoding, regex, parser version hoặc dispatch. Không dùng lại hàm này thay cho matcher thư viện ở production.

## 20. Unit test RequestMatcher bằng MockHttpServletRequest

Với Spring Security + Spring Test tương thích, test một matcher thật:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;
import static org.assertj.core.api.Assertions.assertThat;

class PreviewMatcherTest {
    private final RequestMatcher report =
        PathPatternRequestMatcher.withDefaults()
            .matcher(HttpMethod.GET, "/api/reports/{id}");

    private final RequestMatcher preview =
        new AndRequestMatcher(
            report,
            req -> "preview".equals(req.getParameter("view"))
        );

    @Test
    void matchesOnlyPreviewGet() {
        MockHttpServletRequest yes =
            new MockHttpServletRequest("GET", "/api/reports/42");
        yes.setServletPath("/api/reports/42");
        yes.setParameter("view", "preview");

        MockHttpServletRequest wrongMode =
            new MockHttpServletRequest("GET", "/api/reports/42");
        wrongMode.setServletPath("/api/reports/42");
        wrongMode.setParameter("view", "normal");

        MockHttpServletRequest wrongMethod =
            new MockHttpServletRequest("POST", "/api/reports/42");
        wrongMethod.setServletPath("/api/reports/42");
        wrongMethod.setParameter("view", "preview");

        assertThat(preview.matches(yes)).isTrue();
        assertThat(preview.matches(wrongMode)).isFalse();
        assertThat(preview.matches(wrongMethod)).isFalse();
    }
}
```

**Đây là test snippet**, không phải JDK standalone. Cần `spring-security-web`, Spring Test, JUnit và AssertJ đúng version; `PathPatternRequestMatcher` còn có thể yêu cầu mock request path được thiết lập theo cơ chế parser/version thực tế. Khi mock trực tiếp không mô phỏng đủ Servlet pipeline, dùng `MockMvc`/embedded server để khẳng định behavior runtime. Đừng chỉ dựa vào một mock path không phù hợp để kết luận rule production đúng/sai.

Ma trận custom matcher:
- GET report với `view=preview` → MATCH.
- GET report với `view=normal` → NO MATCH.
- POST report với `view=preview` → NO MATCH.
- GET path khác với `view=preview` → NO MATCH.
- GET thiếu `view` → theo contract đã định.
- GET với `view=PREVIEW`, duplicate param hoặc encoded value → phải có quyết định rõ và test.
- URL có servlet prefix hoặc reverse-proxy rewrite → test trên topology thật.

Đặc biệt, `matcher.matches() == false` chỉ chứng minh một rule không được chọn; **phải test cả fallback thực sự DENY hoặc yêu cầu quyền đúng**.

## 21. Integration test: không chỉ cần 403, cần chứng minh điểm chặn

Spring Security Test hỗ trợ `MockMvc` và mock Authentication:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void readerDeniedPreview() throws Exception {
    mvc.perform(get("/api/reports/42")
            .param("view", "preview")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("reports:read")
            )))
       .andExpect(status().isForbidden());
}

@Test
void specialistCanReadPreview() throws Exception {
    mvc.perform(get("/api/reports/42")
            .param("view", "preview")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("reports:read"),
                new SimpleGrantedAuthority("reports:preview")
            )))
       .andExpect(status().isOk());
}
```

Đây là snippets tích hợp cần `MockMvc`, JUnit, `SimpleGrantedAuthority`, `spring-security-test`, một controller có handler thật, fixtures và policy cho phép user hợp lệ. Nếu handler không tồn tại, không thể kết luận matcher chỉ từ 404; nếu domain policy từ chối ngay cả specialist, test 200 cũng không thể pass trước khi fixture phù hợp.

Cần test đối chứng:
- Reader chỉ có read → preview DENY, normal ALLOW.
- Specialist có cả read và preview → preview ALLOW.
- User chỉ có preview, thiếu read → DENY.
- Anonymous → DENY trên private report.
- POST/PATCH/DELETE với chỉ read → DENY.
- User có đúng authority nhưng khác tenant/owner → domain DENY.
- URL outside API chain → fallback DENY nếu private.

**Dương tính giả:** một POST trả 403 vì thiếu CSRF token không chứng minh rule write. Khi test authorization write trong app có CSRF, phải tạo request hợp lệ có `with(csrf())` và assert target không có side effect khi deny.

## 22. Các chiều cần fuzz/property-test

Các biến thể thường bị bỏ qua:
- Root path, path con, slash cuối và slash kép.
- Các HTTP method `GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS`.
- URL encoded/decoded chars, duplicate query và case.
- `ContextPath` và `ServletPath` khác mặc định.
- `REQUEST/ERROR/FORWARD/ASYNC` dispatch.
- Header có nhiều giá trị hoặc kiểu media type khác.
- Reverse proxy rewrite/forwarded headers.
- Route alias từ controller, legacy servlet, actuator/management path.
- Endpoint export/download/bulk có capability mạnh hơn read.
- Custom matcher trả false do lỗi hệ thống hoặc input lạ.

Các thuộc tính mong muốn:

```text
P1: Một request có thể kích hoạt preview phải yêu cầu
    reports:read AND reports:preview.

P2: Một request write không thể được cho phép chỉ vì read.

P3: Mọi private endpoint phải thuộc một SecurityFilterChain.

P4: Một biến thể URL vẫn tới cùng handler nhạy cảm
    không được có mức quyền thấp hơn.

P5: Lỗi xác minh policy dữ liệu không được biến thành
    ALLOW hoặc fallback yếu không chủ đích.
```

Property tests hữu ích để tìm sự khác biệt giữa matcher và controller, nhưng không thay thế kiểm kê endpoints và kiểm thử deployment thật. Code coverage 100% của `matches` cũng không chứng minh hệ thống không còn URL bypass.

## 23. Chẩn đoán một endpoint “không bị chặn”

Khi thấy client thiếu quyền mà vẫn vào được:

1. Request sau reverse proxy/Servlet thật sự có `requestURI`, `contextPath`, `servletPath`, `pathInfo` gì?
2. `FilterChainProxy` đã chọn `SecurityFilterChain` nào? Có chain nào match không?
3. `securityMatcher` có đúng servlet prefix và HTTP method không?
4. Trong chain đó, custom `requestMatchers` có match trước rule rộng không?
5. Request có kích hoạt chức năng qua alias/header/query mà matcher chưa xét không?
6. Rule được chọn yêu cầu authority đúng chưa? Có nhầm `hasAnyAuthority` và AND không?
7. Authentication có quyền từ nguồn tin cậy hay user tự khai quyền qua input?
8. Nếu qua HTTP, service có kiểm tra tenant/owner/ACL/trạng thái thật không?
9. Nếu response là 403, có thể là lỗi CSRF hay handler khác chứ không phải custom matcher?
10. Có custom filter, GraphQL resolver, scheduler hoặc đường gọi ngoài HTTP bỏ qua điểm chặn này không?

Có thể bật logging Spring Security tại dev/test để quan sát chain/rule; không ghi raw token, password, full private response hay thông tin nhạy cảm. Audit nên ghi actor ID chuẩn hóa, action, resource ID, decision và reason code an toàn.

## 24. Những lỗi phổ biến và hướng sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `contains("/admin")` | Match sai hoặc quá rộng | PathPattern/regex có test |
| Quên HttpMethod | Read permission áp dụng cả write | Method-specific matcher |
| Đặt custom trước nhưng fallback `permitAll` | Biến thể chưa nhận diện có thể bypass | Fallback strict, guard trong service |
| Đặt matcher hẹp sau `/api/**.authenticated()` | Rule hẹp bị che | Sắp thứ tự first-match |
| Gán quyền theo query/header tự khai | Leo thang đặc quyền | Authentication + manager/policy |
| SQL trong `matches` và catch lỗi rồi false | Rơi vào rule/chain yếu | Tách authorization và fail-closed |
| `securityMatcher` hẹp không có fallback | Endpoint ngoài chain không được bảo vệ | Fallback SecurityFilterChain |
| Chain API chung đứng trước admin chain | Admin chain không được áp dụng | Đặt chain hẹp trước hoặc rule mạnh trong chain chung |
| Hiểu sai context/servlet path | Rule không match URL thật | Base path và integration test |
| Chỉ test admin có quyền | Không phát hiện user thường được vào | Negative tests với role thấp |
| Test 403 thiếu CSRF | Dương tính giả | Request hợp lệ và kiểm chứng đúng điểm deny |
| Chỉ scan MVC controller | Quên actuator, framework, servlet khác | Inventory runtime và gateway |
| Không có policy object | IDOR/BOLA dù URL được bảo vệ | Tenant/owner/ACL trong use case |
| Mở `web.ignoring()` quá rộng | Không có các security filters/headers | Ưu tiên `permitAll` nếu thực sự public |

## 25. Checklist trước khi merge custom RequestMatcher

1. Phạm vi yêu cầu gồm method, path, query/header, dispatcher và servlet context nào?
2. Matcher được dùng để chọn chain hay rule? Thứ tự tương ứng ra sao?
3. Có URL thực nào không match chain? Fallback chain có bảo vệ mọi private route không?
4. Có rule tổng quát đứng trên che mất rule hẹp không?
5. Khi custom matcher false, request được route vào rule nào và quyền đủ nghiêm chưa?
6. Input do client kiểm soát có bị biến thành chứng cứ authority/owner không?
7. Một capability nhạy cảm có thể kích hoạt qua cách diễn giải request khác không?
8. Policy cần cả hai quyền đã dùng AND thay vì OR chưa?
9. Có kiểm tra quyền resource thật ở service không?
10. Có test với method khác, duplicate query, encoded path, servlet prefix và dispatcher không?
11. Có negative test về user thiếu quyền, khác tenant và resource bị khóa không?
12. Có test command không phát sinh side effect khi deny không?
13. Có test integration ở runtime tương thích production/version đã chọn không?
14. Có thể quan sát chain/rule nào deny mà không lộ token/secrets không?
15. Khi thêm route mới, inventory và test được cập nhật cùng pull request chưa?

### Câu hỏi tự kiểm tra

**1.** Custom matcher cho `view=preview` bị false nhưng controller vẫn trả preview ở một alias khác. Request sẽ tự DENY không?  
→ **Không.** Nó có thể rơi xuống rule bên dưới; cần cập nhật predicate, hợp đồng input và thêm guard tại use case.

**2.** Một chain `securityMatcher("/api/**")` có `anyRequest().denyAll()`. `/internal/metrics` có bị chain đó deny không?  
→ **Không**, vì chain không được chọn. Cần chain khác/fallback.

**3.** `AndRequestMatcher(reportPath, previewParam)` đã yêu cầu cả hai authority chưa?  
→ **Chưa.** Đây chỉ là AND của điều kiện request. Quyền cần `AuthorizationManagers.allOf` hoặc policy tương đương.

**4.** Chỉ test `previewMatcher.matches(request)==false` ở POST thì có chứng minh POST không vào controller không?  
→ **Chưa.** Phải kiểm tra rule được chọn tiếp theo, fallback và handler runtime.

**5.** Một test POST trả 403 nhưng thiếu CSRF token; có chứng minh quyền DELETE/POST đúng không?  
→ **Không.** Lỗi có thể do CSRF, cần dùng request hợp lệ và test đối chứng.

**6.** Một URL có `/portal` là context root và `/mvc` là servlet path. Đối với PathPattern, mẫu có nên chứa context root không?  
→ **Không**. Mẫu thường app-relative không chứa context root; có thể cần servlet prefix hoặc `basePath("/mvc")`.

**7.** Một user có `reports:read` nhưng report 42 thuộc tenant khác. HTTP matcher allow thì đã được đọc chưa?  
→ **Không**. Phải có domain policy trên resource thật.

**8.** Tại sao test một rule bằng `MockMvc` vẫn chưa đủ để khẳng định không bỏ lọt endpoint?  
→ Có thể tồn tại servlet/management port/framework route khác; cần inventory các entry point, chain coverage và kiểm thử thực tế.

## Kết luận

`RequestMatcher` tùy chỉnh chỉ quyết định một request **thuộc tập nào**. Việc bảo vệ endpoint đòi hỏi ít nhất ba bằng chứng: **chain phù hợp được chọn**, **rule/manager đầu tiên áp dụng đúng quyền tối thiểu**, và **domain policy kiểm tra actor trên resource thật**. Giảm lỗ hổng bằng cách ưu tiên matcher path/method chuẩn, giữ custom predicate ngắn và deterministic, dùng fallback bảo thủ, bổ sung negative tests và duy trì inventory endpoint khi hệ thống thay đổi.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — RequestMatcher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/RequestMatcher.html) — `matches`, `matcher` và `MatchResult`.
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — custom matchers, first-match, `AuthorizationManager`.
- [Spring Security 6.5 — Java Configuration: securityMatcher vs requestMatchers](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html) — chain selection và fallback.
- [Spring Security 6.5 — AuthorizationManagers Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManagers.html) — `allOf` và `anyOf`.
- [Spring Security 6.5 — PathPatternRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html).
- [Spring Security 6.5 — MockMvc Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html).
- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html).
