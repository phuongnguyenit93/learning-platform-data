# RequestMatcher và thông tin request dùng để so khớp

## 1. Bức tranh tổng thể: RequestMatcher trả lời câu hỏi gì?

Trong Spring Security trên nền Servlet, mỗi HTTP request đi vào ứng dụng mang theo thông tin như **phương thức HTTP**, **đường dẫn**, **servlet path**, **query string**, **header**, **dispatcher type** và nhiều thuộc tính khác. Hệ thống cần biết request nào thuộc chuỗi bảo mật nào, và trong chuỗi đó sẽ áp dụng quy tắc phân quyền nào. Thành phần quan trọng để quyết định **một request có phù hợp một điều kiện lựa chọn hay không** là `RequestMatcher`.

Ý tưởng cơ bản rất đơn giản:

> RequestMatcher nhìn vào một `HttpServletRequest` và trả lời request có khớp điều kiện đã mô tả hay không. Kết quả khớp **không phải** quyết định người dùng được phép thực hiện hành động.

Ví dụ:

- `GET /api/documents/42` khớp matcher “GET vào đường lấy tài liệu”.
- `DELETE /api/documents/42` không khớp matcher chỉ dành cho GET.
- Một request khớp matcher “GET tài liệu” vẫn cần `document:read` và chính sách theo tài liệu thực tế trước khi được trả dữ liệu.
- Header tự gửi `X-Role: ADMIN` có thể được nhìn thấy ở request, nhưng **không chứng minh** người gọi có role admin.

Luồng minh họa:

```text
HTTP REQUEST
  method, URI/path, contextPath, servletPath, pathInfo,
  query, headers, dispatcherType, ...
                |
                v
         FilterChainProxy
         chọn SecurityFilterChain đầu tiên
         có RequestMatcher khớp
                |
                v
         AuthorizationFilter
         chọn quy tắc phân quyền theo
         requestMatchers(...) bên trong chain
                |
                v
         AuthorizationManager
         đọc Authentication nếu cần
         và quyết định ALLOW / DENY
                |
                v
         Service / Data policy
         tenant, owner, trạng thái, ...
```

**Phân biệt ba quyết định khác nhau**:

1. **Match:** request này phù hợp tiêu chí nào? (`RequestMatcher`).
2. **Authorization:** người gọi có quyền đối với hành động đã chọn không? (`AuthorizationManager` và chính sách).
3. **Object authorization:** có được thao tác trên bản ghi/tài nguyên **cụ thể** hay không? (điều kiện tenant, owner, trạng thái, quan hệ chia sẻ).

Nắm chắc sự tách biệt này giúp tránh lỗi “đúng URL thì được quyền” hoặc “đã đăng nhập thì được đọc mọi ID”.

## 2. API `RequestMatcher` và điều nó không làm

Trong Spring Security Servlet, interface `org.springframework.security.web.util.matcher.RequestMatcher` nhận `jakarta.servlet.http.HttpServletRequest` để so khớp.

Chữ ký cốt lõi là:

```java
boolean matches(HttpServletRequest request);
```

Một matcher có thể xem xét một hoặc nhiều thuộc tính của request. Nó có thể là matcher dựng sẵn cho URL/path/method, matcher dựa trên biểu thức điều kiện, hoặc matcher tùy chỉnh. Một số API còn trả về kết quả match kèm các biến đường dẫn; cách lấy thông tin đó phụ thuộc interface và phiên bản Spring Security cụ thể.

**RequestMatcher không tự:**

- Xác thực mật khẩu, phiên đăng nhập hay JWT.
- Kiểm tra `GrantedAuthority` trừ khi chính bạn cố ý viết thêm logic không phù hợp vào matcher.
- Đảm bảo một ID tài nguyên thuộc tenant đang đăng nhập.
- Bảo vệ mọi endpoint chỉ vì đã xuất hiện trong một dòng cấu hình.
- Đảm bảo mọi filter chain đều được chạy tuần tự.

Chính sách chuẩn nên để matcher xác định **request thuộc loại nào**, và để manager/service xử lý **ai có quyền gì**.

### 2.1. Bảng các loại thông tin từ `HttpServletRequest`

| Thông tin | API thường gặp | Có thể dùng để match gì? | Lưu ý |
| --- | --- | --- | --- |
| HTTP method | `getMethod()` | GET, POST, PATCH, DELETE | Tên method phân biệt hoa/thường theo giao thức; cấu hình cần chính xác |
| Request URI | `getRequestURI()` | Đường request bên trong server | Thường gồm context path, không chứa query; không dùng trực tiếp thay mọi path matcher |
| Context path | `getContextPath()` | Tiền tố nơi ứng dụng triển khai | Có thể khác giữa local và production |
| Servlet path | `getServletPath()` | Phần đường được ánh xạ tới servlet | Phụ thuộc servlet mapping |
| Path info | `getPathInfo()` | Phần đường còn lại sau servlet path, nếu có | Có thể là `null` |
| Query string | `getQueryString()` | Dữ liệu sau dấu hỏi trong URL | Không phải path; raw string có thể cần xử lý mã hóa |
| Parameter | `getParameter(...)` | Trường query hoặc form đã parse theo servlet | Không mặc định đọc được trường JSON |
| Request header | `getHeader(...)` | Content negotiation, API version... | Client có thể tùy ý đặt nhiều header |
| Content type | `getContentType()` | Kiểu payload | Không phải bằng chứng danh tính hay quyền |
| Dispatcher type | `getDispatcherType()` | REQUEST, FORWARD, ERROR, ASYNC... | Có ảnh hưởng đến các lần dispatch và chính sách |
| Host/scheme | `getServerName()`, `getScheme()` | Chọn domain/HTTPS trong trường hợp cần | Có thể bị ảnh hưởng bởi proxy/header chuyển tiếp |
| Remote address | `getRemoteAddr()` | Kiểm soát theo mạng trong phạm vi phù hợp | Thường là IP của proxy, không phải danh tính người dùng |
| Principal | `getUserPrincipal()`, Spring `Authentication` | Danh tính phía server đã xác thực | Không lẫn với username từ query/header |

Không có quy tắc chung nói “RequestMatcher luôn sử dụng tất cả trường này”. **Một matcher chỉ quan tâm những thuộc tính do implementation của nó định nghĩa**. Matcher path thông thường không lấy giá trị `?role=ADMIN` làm permission; matcher method không tự kiểm tra body.

### 2.2. Ba phần đường dẫn cần phân biệt

Giả sử ứng dụng chạy dưới context path `/portal`; servlet của ứng dụng nhận request `GET /portal/api/documents/42?expand=true`.

Ta có thể nhìn nhận:

```text
HTTP method       GET
Request URI       /portal/api/documents/42
Context path      /portal
Query string      expand=true
Đường ứng dụng    /api/documents/42
```

Giá trị cụ thể của `servletPath` và `pathInfo` phụ thuộc servlet mapping. Với cách mapping thường gặp của Spring MVC, servlet path có thể là `/api/documents/42` và path info null; khi servlet được map theo một prefix khác, chúng có thể chia đoạn theo cách khác.

**Đừng tự trừ tiền tố chuỗi một cách tùy tiện** rồi dùng làm ranh giới bảo mật. Các matcher dựng sẵn biết cách xử lý đường dẫn theo kiểu của chúng, còn mã tự so chuỗi phải hiểu context path, servlet path, URL encoding, dấu gạch chéo kết thúc và phép chuẩn hóa đường dẫn.

### 2.3. Path và query là hai loại dữ liệu khác nhau

`GET /api/documents/42?download=true` vẫn có **cùng path** với `GET /api/documents/42`. Nếu một matcher chỉ xét path và method, hai request này thường có cùng kết quả match.

Nếu tham số `download=true` làm thay đổi nghiệp vụ thành **xuất dữ liệu hoặc tải file nhạy cảm**, đừng đặt toàn bộ trách nhiệm bảo mật vào một matcher path chung rồi tin rằng query tự được kiểm tra. Có thể cần endpoint/HTTP method riêng, một `RequestMatcher` có điều kiện tham số được thiết kế cẩn thận, hoặc chính sách nghiệp vụ bổ sung. Khi hành động thay đổi thực chất, một route tách riêng như `GET /api/documents/42/download` thường dễ kiểm tra hơn.

Không dùng tham số `?admin=true`, header `X-Role` hay bất kỳ trường client tự gửi nào như bằng chứng cấp quyền.

## 3. Các loại RequestMatcher và cách chọn

Spring Security cung cấp nhiều hướng tiếp cận. Tên API khả dụng và đề xuất sử dụng thay đổi theo phiên bản; cần đối chiếu tài liệu của bản Spring Security đang dùng, đặc biệt khi chuyển từ các matcher kiểu cũ sang path pattern mới.

| Cách tiếp cận | Dùng khi | Điểm cần kiểm tra |
| --- | --- | --- |
| `requestMatchers(HttpMethod, "...")` trong DSL | Match HTTP method và đường dẫn bằng cơ chế mà framework cấu hình | Đúng method, path, servlet mapping và thứ tự |
| Matcher dựa trên Spring MVC | Muốn so khớp tương thích với Spring MVC routing | `HandlerMappingIntrospector` và servlet path khi có nhiều servlet |
| Matcher dựa trên PathPattern | Muốn dùng cú pháp path pattern của Spring | Cấu hình parser/path base và version framework |
| Matcher dựa trên Ant-style pattern | Dự án cũ hoặc yêu cầu tương thích | Semantics ký tự wildcard, deprecation/version |
| `RegexRequestMatcher` | Cần biểu thức regex cụ thể | Regex quá rộng, anchoring và encoding |
| Matcher tùy chỉnh | Điều kiện request đặc biệt chưa có sẵn | Không tạo đường vòng từ header/query do client kiểm soát |
| Matcher kết hợp (AND, OR, NOT) | Lựa chọn dựa trên nhiều tiêu chí | Đúng dấu ngoặc, phủ định và phạm vi |

Đối với mã dự án mới, ưu tiên **DSL đơn giản và matcher được khuyến nghị theo phiên bản hiện hành**; không sao chép ngẫu nhiên tên class từ hướng dẫn của phiên bản cũ. Trong các bản Spring Security 6.x, họ matcher liên quan tới MVC/Ant/PathPattern đã trải qua thay đổi và giai đoạn chuyển đổi. Câu hỏi quan trọng không phải chỉ “đây là class nào?”, mà là **nó hiểu đường dẫn, servlet path, method và encoded path như thế nào trong ứng dụng cụ thể?**

### 3.1. Các dạng pattern thường thấy

Ví dụ về ý định (ngữ nghĩa wildcard thực tế cần kiểm chứng theo loại matcher):

```text
/api/documents          -> endpoint collection
/api/documents/*        -> thường muốn một đoạn con như /42
/api/documents/**       -> thường muốn các đoạn đường con bất kỳ
/api/admin/**           -> nhóm endpoint admin
/public/**              -> nội dung được phép public
```

Đừng nghĩ `*`, `**` và `{id}` giống nhau trên mọi loại matcher. Spring MVC `PathPattern` có quy tắc riêng về vị trí `**`; regex lại có cú pháp khác hoàn toàn. Không dùng wildcard quá rộng chỉ vì nó “match được test đầu tiên”.

### 3.2. Spring MVC và nhiều servlet

Trong dự án Spring MVC có thể dùng matcher tương thích mapping của MVC; khi có nhiều servlet hoặc servlet được map ở prefix riêng, cần chỉ rõ **servlet path** hoặc chọn loại matcher phù hợp. Tên path hiển thị trong browser chưa đủ cho biết matcher nào sẽ áp dụng.

Một ứng dụng có thể có servlet chính ở `/`, servlet phụ ở `/legacy/*` và một DispatcherServlet tại một prefix khác. Cùng chuỗi `/api/**` có thể được hiểu khác nếu build matcher và servlet mapping không thống nhất. Hãy test bằng request qua server thực hoặc `MockMvc` có cấu hình sát với ứng dụng.

### 3.3. Matcher tùy chỉnh: điều kiện gì phù hợp?

Có thể định nghĩa matcher riêng nếu cần phân loại request theo method, một header version hay một thuộc tính request xác định:

```java
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher clientRequestsV2 =
    request -> "v2".equals(request.getHeader("X-Api-Version"));
```

Đoạn này **chỉ kiểm tra header**. Nó không xác thực header, không đảm bảo request thuộc API nào và không cấp quyền. Nếu được dùng để chọn tuyến cần chính sách riêng, nhánh không khớp phải có fallback an toàn; tuyệt đối không diễn giải `X-Api-Version: v2` là role hay authority.

Matcher tùy chỉnh liên quan path nên đặc biệt cẩn trọng với context path, servlet path, chuẩn hóa encoding, các ký tự đặc biệt và khả năng khác nhau giữa bộ lọc bảo mật với router thực. Nếu có sẵn matcher đường dẫn phù hợp thì nên dùng thay vì tự ghép `getRequestURI()` và kiểm tra chuỗi.

### 3.4. Không nhầm matcher với kiểm tra quyền

Ví dụ:

```text
M = request có method DELETE, path /api/documents/42
A = principal có authority document:delete
O = principal được xóa document 42 trong tenant hiện tại

ALLOW = M AND A AND O
```

Trong đó M giúp **chọn chính sách**. M không cung cấp thông tin rằng A hoặc O đúng. Cũng không có chuyện request “match DELETE” thì đồng nghĩa đã vượt qua CSRF hoặc đã được xác thực.

## 4. Hai nơi dùng matcher trong Spring Security có ý nghĩa khác nhau

### 4.1. `securityMatcher` chọn phạm vi của cả SecurityFilterChain

Một ứng dụng Servlet có thể khai báo nhiều `SecurityFilterChain`. `FilterChainProxy` chọn **chain đầu tiên khớp request** theo thứ tự. Khi chain đã chọn, những chain phía sau không được thực thi nối tiếp để “bổ sung lớp bảo vệ”.

Ví dụ nếu chain chỉ khớp `/api/**`, request `/admin/export` sẽ không vào chain đó. Một `anyRequest().denyAll()` **bên trong API chain** không bảo vệ `/admin/export`. Cần có fallback chain hoặc một thiết kế coverage phù hợp.

### 4.2. `requestMatchers` chọn quy tắc phân quyền trong chain đã chọn

Trong `authorizeHttpRequests`, các matcher thường được xét **theo thứ tự khai báo** và quy tắc **đầu tiên khớp** được sử dụng. Nếu đặt rule rộng trước rule hẹp, rule hẹp có thể không bao giờ chạy:

```text
Nguy hiểm:
  /api/**            -> authenticated
  /api/admin/**      -> hasRole("ADMIN")

An toàn hơn:
  /api/admin/**      -> hasRole("ADMIN")
  /api/reports/**    -> quyền tương ứng
  anyRequest         -> denyAll
```

Người đã đăng nhập không đương nhiên được gọi endpoint quản trị. Cần kiểm thử các trường hợp rule hẹp và rule bao quát có vùng giao nhau.

### 4.3. Ví dụ Spring Security 6 Servlet

Đây là **cấu hình tích hợp**, không phải chương trình Java biên dịch độc lập. Giả sử ứng dụng đã cấu hình cơ chế xác thực thích hợp và authorities do server/IdP đã xác minh cung cấp.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DocumentHttpSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/admin/**")
                    .hasAuthority("admin:read")
                .requestMatchers(HttpMethod.GET, "/api/documents/*")
                    .hasAuthority("document:read")
                .requestMatchers(HttpMethod.POST, "/api/documents")
                    .hasAuthority("document:create")
                .requestMatchers(HttpMethod.DELETE, "/api/documents/*")
                    .hasAuthority("document:delete")
                .anyRequest().denyAll()
            );
        return http.build();
    }

    @Bean
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping")
                .permitAll()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Ý nghĩa:

1. `@Order(1)` ưu tiên xét API chain. `securityMatcher("/api/**")` xác định toàn bộ chain chỉ xử lý các request phù hợp phạm vi API.
2. Sau khi request vào API chain, các rule phân loại tiếp theo dựa trên **HTTP method và đường dẫn**.
3. `GET /api/documents/42` cần `document:read`; `DELETE /api/documents/42` cần `document:delete`. Không được coi GET và DELETE có cùng mức quyền chỉ vì path giống nhau.
4. `GET /api/admin/users` cần `admin:read`; những hành động admin khác chưa được liệt kê vẫn bị deny.
5. Request không vào API chain vẫn gặp fallback, nơi chỉ cho phép một endpoint public đã xác định.
6. Cấu hình chưa trình bày JWT/form login, CSRF, CORS hoặc entrypoint lỗi; phải cấu hình theo kiến trúc ứng dụng thực.

Đặc biệt với ứng dụng dùng cookie/session, **CSRF** là một lớp bảo vệ riêng cho những request thay đổi trạng thái. Không tắt CSRF chỉ vì muốn cho bài test POST/DELETE đi qua.

### 4.4. Một matcher không khớp không đồng nghĩa request được cho phép

Giả sử `GET /api/documents/42` khớp GET rule và được kiểm tra `document:read`. Nếu thay bằng `PUT /api/documents/42` thì GET rule không khớp. Nếu cuối chuỗi có `denyAll`, PUT bị chặn. Nếu lại có `anyRequest().authenticated()`, mọi user đã đăng nhập có thể vô tình được cho qua PUT dù chưa có chính sách sửa.

Vì vậy, hai câu hỏi phải được test độc lập: **route nào khớp?** và **route không khớp được xử lý thế nào?**

## 5. Java 17 độc lập: thử so khớp method, path, context path và query

Để nhìn rõ những trường nào ảnh hưởng đến kết quả, trước tiên dùng Java thuần. Ví dụ này **mô phỏng một bộ so khớp của riêng bài học**, không mô phỏng mọi chi tiết của matcher tích hợp Spring Security.

Lưu toàn bộ chương trình dưới tên `RequestMatchingDemo.java`:

```java
import java.util.Map;
import java.util.regex.Pattern;

public class RequestMatchingDemo {
    private static final Pattern DOCUMENT_DETAIL =
        Pattern.compile("/api/documents/[0-9]+");

    record DemoRequest(
        String method,
        String contextPath,
        String servletPath,
        String pathInfo,
        String queryString,
        Map<String, String> headers
    ) {}

    static boolean matchesGetDocument(DemoRequest request) {
        if (request == null || !"GET".equals(request.method())
                || request.servletPath() == null) {
            return false;
        }

        // Quy ước mô phỏng: match servletPath + pathInfo.
        // Không nối contextPath, queryString hoặc headers.
        String path = request.servletPath()
            + (request.pathInfo() == null ? "" : request.pathInfo());

        return DOCUMENT_DETAIL.matcher(path).matches();
    }

    static DemoRequest of(String method, String servletPath) {
        return new DemoRequest(
            method, "", servletPath, null, null, Map.of()
        );
    }

    static void show(String name, DemoRequest request) {
        System.out.println(name + ": " + matchesGetDocument(request));
    }

    public static void main(String[] args) {
        show("get document 42",
            of("GET", "/api/documents/42"));

        show("post same path",
            of("POST", "/api/documents/42"));

        show("non numeric id",
            of("GET", "/api/documents/abc"));

        show("query does not change path",
            new DemoRequest(
                "GET", "", "/api/documents/42", null,
                "role=ADMIN", Map.of()
            ));

        show("context path separate",
            new DemoRequest(
                "GET", "/portal", "/api/documents/42", null,
                null, Map.of()
            ));

        show("path info appended",
            new DemoRequest(
                "GET", "/portal", "/api", "/documents/42",
                null, Map.of()
            ));

        show("header does not grant path match",
            new DemoRequest(
                "GET", "", "/api/documents/42", null,
                null, Map.of("X-Role", "ADMIN")
            ));

        show("trailing slash",
            of("GET", "/api/documents/42/"));

        show("different prefix",
            of("GET", "/private/documents/42"));

        show("missing request", null);
    }
}
```

Lệnh chạy trên JDK 17+:

```bash
javac RequestMatchingDemo.java
java RequestMatchingDemo
```

Kết quả stdout chính xác:

```text
get document 42: true
post same path: false
non numeric id: false
query does not change path: true
context path separate: true
path info appended: true
header does not grant path match: true
trailing slash: false
different prefix: false
missing request: false
```

**Diễn giải từng nhóm:**

- `POST` không khớp rule GET dù URL giống nhau.
- Regex demo chỉ nhận ID dạng số và chỉ match toàn bộ path; `/api/documents/abc` hoặc dấu `/` cuối không khớp.
- `?role=ADMIN` và header `X-Role` không được dùng để thay đổi kết quả match path: client không thể cấp quyền qua hai trường đó. Dòng “header does not grant path match: true” nghĩa là **path GET đã khớp sẵn**; không có nghĩa request được cho quyền admin.
- `contextPath=/portal` không được tính vào phần path của ví dụ, nên triển khai ứng dụng dưới prefix không làm đổi kết quả mô phỏng.
- Trường hợp `servletPath=/api`, `pathInfo=/documents/42` chứng minh vì sao hai thành phần cần được xem xét cùng nhau ở một số kiểu servlet mapping.

**Giới hạn quan trọng:** các matcher thực trong Spring Security có thể dùng chính sách khác nhau để chuẩn hóa đường dẫn, xử lý dấu gạch chéo, dấu chấm phẩy, URL encoding và servlet mapping. Ví dụ `Pattern.compile` ở đây chỉ là hàm Java thuần để học cách nghĩ; **không thay thế trực tiếp các RequestMatcher được framework hỗ trợ**.

## 6. Chọn thông tin request để match: đúng ý định, đúng ranh giới tin cậy

### 6.1. HTTP method và path: cặp tiêu chí thường cần nhất

Một URI có thể xử lý nhiều hành động:

| Request | Hành động thường gặp | Quyền ví dụ |
| --- | --- | --- |
| `GET /api/orders/123` | Đọc đơn hàng | `order:read` |
| `PATCH /api/orders/123` | Sửa một số trường | `order:update` |
| `DELETE /api/orders/123` | Xóa/hủy đơn | `order:delete` |
| `POST /api/orders/123/approve` | Duyệt đơn | `order:approve` |

Nếu matcher chỉ xét `/api/orders/**` rồi dùng một `authenticated()` quá rộng, người đã đăng nhập có thể gọi cả thao tác hủy/duyệt dù chỉ được đọc. Luôn kiểm tra method cùng với đường dẫn khi ý nghĩa và quyền khác nhau.

HTTP HEAD, OPTIONS và CORS preflight cần được xem xét theo hành vi ứng dụng. Đừng mặc định cứ `OPTIONS` là được phép thực hiện mọi hành động; preflight là một phần cơ chế trình duyệt, không phải bằng chứng đã xác thực hoặc cấp quyền nghiệp vụ.

### 6.2. Header, query, host và IP: chỉ tin ở mức được chứng minh

Một matcher có thể nhìn vào header, host hoặc tham số query, nhưng đó là **dữ liệu đầu vào của request**. Client thường kiểm soát được nhiều trường. Không được kết luận người dùng có quyền chỉ vì:

```text
X-Role: ADMIN
X-Tenant-Id: tenant-7
?isInternal=true
X-Forwarded-For: 10.0.0.1
```

Nếu hệ thống dùng reverse proxy/gateway, chỉ tin những header đã được proxy tin cậy kiểm soát, có cơ chế loại bỏ giá trị do client gửi giả mạo và đã cấu hình xử lý forwarded headers đúng. Ngay cả IP nội bộ hoặc host hợp lệ cũng không thay thế xác thực người dùng và kiểm tra quyền tài nguyên.

Header `Accept`, `Content-Type` hoặc tham số `format` có thể dùng để phân loại kiểu xử lý, nhưng **một thao tác export nhạy cảm vẫn phải yêu cầu permission riêng**. Cũng cần lưu ý `getParameter(...)` có thể parse query/form; nó không mặc định là bộ đọc JSON body.

### 6.3. Cẩn trọng với chuẩn hóa URL

Các tình huống như `%2F` (dấu slash encoded), `..`, dấu chấm phẩy, dấu slash kép, chuỗi UTF-8, phần path sau servlet mapping hoặc proxy rewrite có thể khiến **thành phần bảo mật và router hiểu đường dẫn khác nhau** nếu cấu hình không đồng bộ.

Một rủi ro điển hình là “security kiểm tra đường A nhưng controller thực tế xử lý đường B”. Vì vậy:

1. Ưu tiên matcher tương thích router của framework và phiên bản ứng dụng.
2. Không tự giải mã URL nhiều lần theo cách khác với Servlet container.
3. Cấu hình firewall và routing có chủ đích; tránh nới lỏng bảo vệ URL bất thường chỉ để giải quyết một trường hợp kiểm thử.
4. Test trên đường đi HTTP thực tế gồm proxy, context path và servlet mapping.
5. Quyết định quyền nhạy cảm phải được kiểm tra tại service/data ngay cả khi route đã khớp.

### 6.4. Nhiều DispatcherType và internal forward

Một request Servlet có thể có các lần dispatch khác nhau, chẳng hạn `REQUEST`, `FORWARD`, `ERROR` hoặc `ASYNC`. Spring Security có quy tắc xử lý các dispatch này; việc xử lý cụ thể phụ thuộc cấu hình và phiên bản.

Ví dụ, ứng dụng cần hiển thị trang lỗi hoặc forward view nội bộ có thể gặp vấn đề nếu một security rule áp dụng cho dispatch phụ theo cách không mong muốn. Không nên xử lý bằng cách `permitAll()` tất cả dispatcher type một cách máy móc.

Nếu thực sự cần cho phép dispatch nội bộ cụ thể, hãy đặt matcher tương ứng một cách có chủ đích, ví dụ cấu hình `dispatcherTypeMatchers(...)` theo tài liệu phiên bản đang dùng, và test rằng **request trực tiếp bên ngoài** vẫn không thể truy cập chức năng nhạy cảm. Một `FORWARD` nội bộ không tự làm mất trách nhiệm bảo vệ tài nguyên của handler đích.

## 7. Kết hợp matcher có điều kiện: AND, OR, NOT

Khi một route cần chọn theo nhiều thuộc tính, ta có thể diễn đạt điều kiện logic:

```text
M1 = method là GET
M2 = path thuộc /api/reports/**
M3 = header X-Api-Version bằng v2

GET_V2_REPORT = M1 AND M2 AND M3
```

Các bộ kết hợp matcher tương ứng với AND, OR, NOT có thể tồn tại trong API Spring Security theo phiên bản. Tuy nhiên, **kết hợp matcher chỉ làm rõ yêu cầu nào sẽ được chọn để đánh giá chính sách**, không tự bảo đảm rằng policy của nhánh được chọn là đủ chặt.

### 7.1. Thứ tự có thể đổi kết quả

Giả sử các rule trong một chain:

```text
Rule A: GET /api/reports/**              -> hasAuthority("report:read")
Rule B: GET /api/reports/export           -> hasAuthority("report:export")
```

Nếu A đứng trước B và matcher A bao trùm export, một người chỉ có `report:read` có thể đến endpoint export mà không qua rule export (trừ khi có chốt khác). Đổi thứ tự:

```text
Rule B: GET /api/reports/export           -> hasAuthority("report:export")
Rule A: GET /api/reports/**              -> hasAuthority("report:read")
Other                                     -> denyAll
```

Đây là ví dụ rất rõ về việc **cùng request, cùng principal nhưng thứ tự matcher làm khác chính sách được áp dụng**. Test phải thử cả người chỉ có `report:read` lẫn người có `report:export`.

### 7.2. Matcher phủ định không phải chính sách mặc định từ chối

Nếu `NOT /public/**` được dùng để chọn một nhóm request, hãy kiểm tra chính xác phần còn lại và liệu có endpoint nhạy cảm nào nằm trong tập phủ định hay không. Một phép phủ định dễ tạo vùng khớp rộng hơn dự kiến. Ưu tiên các nhóm đường dẫn dương tính, rõ ràng và kết thúc bằng deny mặc định.

### 7.3. Đừng đặt quyền người dùng vào custom RequestMatcher

Một RequestMatcher tự đọc `Authentication` để quyết định có match route hay không dễ khiến việc **phân loại request** và **quyết định quyền** bị trộn lẫn. Điều này làm thứ tự rule khó dự đoán và khó debug: nếu matcher không khớp vì thiếu quyền, request có thể rơi xuống một rule khác yếu hơn.

Nên tách:

```text
RequestMatcher: method/path/query pattern xác định route nào
AuthorizationManager: Authentication, authority, policy chức năng
Service/repository: tenant, owner, status, dữ liệu thực
```

Nếu cần quyền theo request attribute hoặc tài nguyên, dùng một `AuthorizationManager` hoặc policy nghiệp vụ với đầu vào đáng tin; không cố giải quyết bằng cách biến matcher thành một hệ thống phân quyền thứ hai.

## 8. Kiểm thử RequestMatcher có phương pháp

### 8.1. Ma trận match và quyền cần kiểm tra riêng

| Request | Matcher mong đợi | Quyết định quyền sau match |
| --- | --- | --- |
| `GET /api/documents/42` | GET document | Cần `document:read` |
| `POST /api/documents/42` | Không phải GET document | Rule POST khác hoặc mặc định deny |
| `DELETE /api/documents/42` | DELETE document | Cần `document:delete` |
| `GET /api/documents/abc` | Phụ thuộc route pattern có chấp nhận chuỗi ID | Không bỏ kiểm tra object |
| `GET /api/documents/42?role=ADMIN` | Thường cùng path matcher GET | Không cấp admin qua query |
| `GET /portal/api/documents/42` với context path /portal | Khớp theo cách matcher hiểu đường ứng dụng | Vẫn cần quyền đọc |
| `GET /api/reports/export` | Matcher export phải ưu tiên nếu nhạy cảm | Cần `report:export` |
| `GET /api/documents/42/` | Tùy semantics slash của matcher/router | Không tự giả định được phép |
| `PATCH /api/documents/42` | Không khớp GET/DELETE | Rule cập nhật riêng hoặc deny |
| `GET /private/admin` ngoài API chain | Fallback/chain bảo vệ | Không vô tình lọt qua |
| `FORWARD` tới handler nhạy cảm | Phụ thuộc dispatcher policy | Không vượt quyền chức năng/object |
| Encoded URL hoặc slash kép | Phụ thuộc firewall/router | Cách xử lý phải nhất quán và an toàn |

Với mỗi hàng nên có **hai assertion**: request chọn matcher nào, và user được phép hay từ chối sau khi manager và chính sách nghiệp vụ chạy. Không coi “matcher trả true” là một test bảo mật hoàn chỉnh.

### 8.2. Unit test RequestMatcher riêng

Với matcher tùy chỉnh hoặc matcher dựng sẵn, có thể dùng `MockHttpServletRequest` từ Spring Test để tạo request với method, servlet path, context path, header, query và dispatcher type rồi kiểm tra `matches(...)`.

Đoạn sau là **mã minh họa bên trong một test có dependency Spring Test**:

```java
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.util.matcher.RequestMatcher;

// requestMatcher là matcher đã được tạo trong test.
MockHttpServletRequest request =
    new MockHttpServletRequest("GET", "/api/documents/42");

request.setContextPath("");
request.setServletPath("/api/documents/42");
request.addHeader("X-Role", "ADMIN");

boolean matched = requestMatcher.matches(request);
```

Kết quả `matched` phụ thuộc matcher do test cung cấp. Không thể khẳng định true/false cho mọi matcher từ đoạn mã này; phải đặt assertion phù hợp với quy tắc cần thử. `MockHttpServletRequest` là công cụ kiểm thử, không phải cơ chế xác thực user.

### 8.3. Integration test bằng MockMvc

Với Spring MVC, `MockMvc` và `spring-security-test` giúp xác minh SecurityFilterChain, matcher order và kết quả phân quyền. Những test helper như `user(...)` hoặc `jwt(...)` tạo bối cảnh giả lập: chúng không chứng minh chữ ký JWT hay mật khẩu được kiểm tra thật.

Ví dụ phần thân **một test tích hợp đã được cấu hình MockMvc và controller**:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Người chỉ có quyền đọc không được qua rule export riêng:
mockMvc.perform(get("/api/reports/export")
        .with(user("reader").authorities(
            new SimpleGrantedAuthority("report:read"))))
    .andExpect(status().isForbidden());
```

Đoạn test chỉ đúng nếu endpoint export tồn tại, ứng dụng đã cấu hình rule export trước rule đọc báo cáo rộng và không có cơ chế khác che kết quả. `SimpleGrantedAuthority` là `org.springframework.security.core.authority.SimpleGrantedAuthority`. Đây là đoạn mã **không độc lập**, cần môi trường ứng dụng/test đầy đủ.

Với POST/PATCH/DELETE, nếu CSRF bật, phải cung cấp token CSRF hợp lệ khi đang kiểm thử **quyền truy cập**, nếu không 403 có thể do CSRF chứ không chứng minh matcher hoặc authority được kiểm tra đúng.

### 8.4. Khi có reverse proxy và context path

Test local tại `/api/**` chưa đủ nếu production triển khai tại `/portal/api/**`, dùng URL rewrite hoặc forward headers. Nên chạy ít nhất một kiểm thử trên đường HTTP thực tế hoặc môi trường tích hợp tương đương, quan sát:

- `requestURI`, `contextPath`, `servletPath` và `pathInfo` thực tế.
- Matcher nào được chọn trong chain nào.
- Controller nào được router thực thi.
- Quyết định quyền và dữ liệu thực tế được trả về.

Không ghi raw token/cookie hoặc thông tin nhạy cảm vào log chỉ để debug matcher. Dùng request ID, method, mẫu path đã chuẩn hóa, mã rule và kết quả, đồng thời kiểm soát việc tiết lộ ID/định danh tài nguyên.

## 9. Lỗi cấu hình và cách xử lý

| Lỗi | Tại sao nguy hiểm? | Cách sửa |
| --- | --- | --- |
| Dùng `securityMatcher("/api/**")` mà không có fallback | URL ngoài API có thể không qua Spring Security | Bao phủ mọi đường cần bảo vệ |
| Chain ưu tiên cao khớp `/**` quá rộng | Chain admin/API phía sau không chạy | Xem `@Order` và phạm vi matcher |
| Đặt matcher đọc rộng trước export nhạy cảm | Export được áp dụng quyền đọc yếu hơn | Đặt rule cụ thể trước |
| Chỉ match path, bỏ method | GET, DELETE dùng sai permission | Match theo HTTP method |
| Coi query string là phần của path pattern | Test và thực tế khác nhau | Phân biệt path, query, parameter |
| Ghép `getRequestURI()` bằng tay bỏ context path | Match sai khi deploy dưới prefix | Dùng matcher phù hợp servlet mapping |
| Dùng tên nhóm hoặc header client làm quyền | Client tự nâng quyền | Authentication và authority từ nguồn đã xác minh |
| Đoán wildcard giống nhau trên MVC/Ant/regex | Route lệch hoặc quá rộng | Kiểm thử cú pháp matcher thực dùng |
| Cho mọi `FORWARD`/`ERROR` không kiểm soát | Có thể tạo lối đi ngoài chính sách | Thiết kế dispatcher policy có chủ đích |
| Test 403 nhưng thiếu CSRF | Kết luận sai nguyên nhân từ chối | Tách test CSRF và authorization |
| Chỉ test matches, không test quyền | Match đúng nhưng permission sai | Unit match + integration authorization |
| Chỉ bảo vệ URL, không bảo vệ record | IDOR/BOLA | Tenant/owner/state ở service/data |
| Nới lỏng firewall cho URL encoded bất thường | Security/router hiểu path khác nhau | Thống nhất xử lý path và test cạnh |
| Dùng `authenticated()` cho route nhạy cảm | Mọi user đăng nhập có thể gọi | Permission riêng + deny mặc định |

## 10. Quy trình áp dụng khi thêm một endpoint

1. **Định nghĩa hành động và quyền:** ví dụ `document:download` cho việc tải file, không chỉ “người dùng đã đăng nhập”.
2. **Xác định request shape:** method, path, path variables, query, content type, servlet mapping và context path sản xuất.
3. **Chọn chain:** request thuộc `SecurityFilterChain` nào, có fallback không? Có chain rộng phía trước không?
4. **Chọn matcher:** ưu tiên path/method matcher phù hợp MVC/router; dùng custom matcher khi thực sự cần điều kiện bổ sung.
5. **Đặt đúng thứ tự:** route hẹp/nhạy cảm trước route rộng, deny phần còn lại.
6. **Gắn authorization rule:** authority/role cụ thể; quy ước `ROLE_`, `SCOPE_` và permission phải thống nhất.
7. **Kiểm tra object policy:** tải tài liệu thật, xác minh tenant, owner, sharing, trạng thái, điều kiện khác.
8. **Kiểm thử:** có/không quyền, method khác, query/header tự thay, context path, slash/encoding, route không khai báo, export/endpoint phụ.
9. **Quan sát sau triển khai:** nếu có 401/403 mới, xác định là authentication, matcher, CSRF, permission hay object policy, không lập tức chuyển sang `permitAll()`.
10. **Rà soát khi nâng phiên bản:** matcher implementation hoặc pattern parser có thể thay đổi; test nên bắt những khác biệt đường dẫn quan trọng.

## 11. Câu hỏi tự kiểm tra

1. **`RequestMatcher` kiểm tra điều gì?** Một `HttpServletRequest` có phù hợp điều kiện chọn hay không; bản thân match không phải cấp quyền.
2. **Tại sao GET và DELETE cùng URI nên có rule riêng?** Chúng là hai hành động với rủi ro/permission khác nhau.
3. **`?role=ADMIN` có làm matcher path GET trở thành quyền admin không?** Không. Query là đầu vào do client kiểm soát, không phải authority.
4. **Khác nhau giữa `securityMatcher` và `requestMatchers`?** Cái đầu chọn phạm vi của cả chain; cái sau chọn rule phân quyền trong chain đã được chọn.
5. **Nếu hai SecurityFilterChain khớp cùng request?** Chain khớp đầu tiên theo thứ tự được sử dụng; các chain khác không chạy cộng dồn.
6. **`anyRequest().denyAll()` trong API chain bảo vệ mọi URL ngoài API không?** Không. Cần chain phù hợp bao phủ chúng.
7. **Vì sao servlet path và context path quan trọng?** Vì đường hiển thị trong browser và đường matcher sử dụng có thể khác theo triển khai/servlet mapping.
8. **Có nên dùng header `X-Role` làm điều kiện cấp quyền?** Không; người dùng có thể tự gửi header giả, trừ khi một cơ chế xác thực đáng tin đã thiết lập authority ở server.
9. **Vì sao thứ tự matcher có thể gây lỗi bảo mật?** Rule rộng trước rule hẹp có thể che điều kiện nhạy cảm.
10. **Tại sao unit test matcher chưa đủ?** Nó không chứng minh authentication, authority, object policy và side effect đã được xử lý.
11. **Khi nào dùng custom matcher?** Khi cần lựa chọn theo thuộc tính request mà matcher dựng sẵn không diễn đạt được, và đã hiểu ranh giới dữ liệu tin cậy.
12. **Khi request khớp `/api/documents/42` và user có `document:read`, có chắc được đọc?** Không; service còn phải kiểm tra owner, tenant, trạng thái và quyền trên đối tượng.

**Ghi nhớ:** `RequestMatcher` giúp Spring Security **chọn đúng đường xử lý và đúng quy tắc** dựa trên thông tin của HTTP request. Tính bảo mật đến từ việc **hiểu chính xác thông tin nào được match**, **thứ tự và phạm vi của các matcher**, **không biến dữ liệu client thành authority**, và **tiếp tục đánh giá quyền trên tài nguyên thực tế sau khi matcher đã khớp**.

### Tài liệu tham khảo chính thức

- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Java Configuration và nhiều HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security – Servlet Architecture và FilterChainProxy](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security – RequestMatcher API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/util/matcher/RequestMatcher.html)