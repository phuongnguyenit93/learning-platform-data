# Biến đường dẫn, wildcard và khác biệt ngữ nghĩa từng kiểu matcher

**`RequestMatcher`** trong Spring Security Servlet trả lời câu hỏi: *“Request HTTP hiện tại có thỏa điều kiện khớp này không?”* Nó có thể xét đường dẫn, HTTP method, hoặc điều kiện khác tùy implementation. Với các matcher theo đường dẫn, ký hiệu **`*`**, **`**`**, **`?`** và **`{id}`** trông giống nhau giữa các framework, nhưng **không phải mọi kiểu matcher đều hiểu chúng như nhau**.

Ví dụ `/api/documents/{documentId}` có thể khớp một tài liệu cụ thể và **trích xuất** `documentId=42`. Trong khi đó `/api/documents/**` bao phủ nhiều đường dẫn con nhưng thường **không tạo ra một biến có tên**. Regex `/api/documents/[0-9]+` ràng buộc ID là số theo cú pháp *biểu thức chính quy*, chứ không dùng cú pháp template `{documentId}`.

**Mục tiêu của bài:**

1. Phân biệt **segment**, **path variable**, **single-segment wildcard**, **multi-segment wildcard** và **regex**.
2. Hiểu phạm vi, ngữ nghĩa và thay đổi phiên bản của **`PathPatternRequestMatcher`**, **`MvcRequestMatcher`**, **`AntPathRequestMatcher`**, **`RegexRequestMatcher`**, matcher tùy biến.
3. Biết cách lấy biến đường dẫn cho **authorization theo tài nguyên**, không chỉ khớp URL.
4. Viết và kiểm thử rule để tránh mở quyền sai vì `/**` quá rộng, query string, prefix servlet hoặc khác biệt parser.

Ngữ cảnh chính: **Spring Security 6.5.x, Spring MVC/Servlet và Java 17+**. Bài cũng chỉ rõ hướng thay đổi trong Spring Security 7; không giả định rằng mọi project đang dùng cùng implementation mặc định.

## 1. RequestMatcher là gì, và nó khớp ở tầng nào?

Interface `org.springframework.security.web.util.matcher.RequestMatcher` nhận một `HttpServletRequest` và đánh giá điều kiện khớp. Hai thao tác đáng chú ý:

```java
boolean matches(HttpServletRequest request);

RequestMatcher.MatchResult matcher(HttpServletRequest request);
```

- `matches(...)` trả boolean: request có khớp hay không.
- `matcher(...)` có thể trả **`MatchResult`** gồm trạng thái khớp và **map biến được trích xuất**, nếu implementation có khả năng trích xuất. Không mặc định mọi matcher đều có biến.
- Matcher chỉ xác định **request có thuộc tập được mô tả**; nó **không tự cấp quyền**. Quyền được đánh giá bởi `AuthorizationManager` tương ứng.

Matcher xuất hiện ở **hai cấp**:

```java
http.securityMatcher("/api/**"); // Chọn SecurityFilterChain.

http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/documents/{documentId}")
        .hasAuthority("documents.read")
    .anyRequest().denyAll()
); // Chọn authorization rule bên trong chain.
```

`securityMatcher` giới hạn những request đi vào **toàn bộ chain**; `requestMatchers` trong `authorizeHttpRequests` chọn **quy tắc** trong chain đã được chọn. Một path matcher với mẫu giống nhau có thể dùng ở cả hai nơi, nhưng tác động khác nhau.

Khi có nhiều `SecurityFilterChain`, `FilterChainProxy` chọn **chain khớp đầu tiên**. Trong một chain dùng `RequestMatcherDelegatingAuthorizationManager`, rule khớp **đầu tiên** được áp dụng; nếu rule đó từ chối thì không thử rule sau để tìm quyền dễ hơn.

## 2. Nền tảng: một URL path gồm các segment

Xét request:

```text
GET /api/teams/alpha/documents/42?include=history
```

Phần **path** là `/api/teams/alpha/documents/42`. Dấu `/` ngăn các **segment**:

```text
api | teams | alpha | documents | 42
```

Query string là `include=history`, **không phải segment** của path. Những điều thường cần phân biệt:

- `/api/teams/alpha/documents/42`: đường dẫn theo các segment.
- `/api/teams/alpha/documents/42?include=history`: URL có query; matcher chỉ đọc path thường **không** lấy query vào phép so khớp.
- `/api/teams/alpha/documents/42/comments/3`: nhiều segment hơn.
- `/api/teams/alpha/documents/42/`: có dấu `/` cuối; tùy parser/config, điều này có thể khác với không có dấu.
- `/api/teams/Alpha/documents/42`: khác chữ hoa; nhiều matcher mặc định phân biệt chữ hoa/chữ thường.
- `/api/teams/alpha/documents/a%2Fb`: chứa ký tự percent-encoded; phải xem **đường dẫn được giải mã và chia segment tại tầng nào**.

Đường dẫn nhìn thấy trong browser không phải lúc nào cũng giống phần `servletPath`, `pathInfo` hay path đã được Spring MVC parse. **Context path** (ví dụ deploy ứng dụng ở `/portal`) và **servlet mapping** (ví dụ `/mvc/*`) là hai yếu tố khác nhau; cần kiểm implementation cụ thể.

## 3. Cú pháp PathPattern: literal, `?`, `*`, `**` và biến có tên

Spring Framework sử dụng `PathPattern` để khớp đường dẫn theo segment; `PathPatternRequestMatcher` dùng cơ chế này ở Spring Security 6.5+. Những mẫu cơ bản:

| Mẫu | Ý nghĩa PathPattern | Ví dụ khớp | Ví dụ không khớp |
| --- | --- | --- | --- |
| `/api/orders` | Literal, path cố định | `/api/orders` | `/api/orders/42` |
| `/api/orders/{orderId}` | Một segment, đồng thời lấy biến `orderId` | `/api/orders/42` → `orderId=42` | `/api/orders/42/items` |
| `/files/*` | Bất kỳ nội dung trong **một segment hiện diện** | `/files/a.txt` | `/files/a/b.txt` |
| `/files/??.txt` | Hai ký tự ở vị trí `??` trong **một segment** | `/files/ab.txt` | `/files/abcd.txt` |
| `/files/*.csv` | Một tên tệp kết thúc bằng `.csv` trong một segment | `/files/report.csv` | `/files/archive/report.csv` |
| `/api/orders/**` | Không hoặc nhiều **segment phía cuối path** | `/api/orders`, `/api/orders/42/items` | `/api/users` |
| `/api/orders/{orderId:[0-9]+}` | Một segment với regex ràng buộc giá trị và trích xuất biến | `/api/orders/42` | `/api/orders/abc` |
| `/files/{*filePath}` | Bắt phần **còn lại của path** thành biến có tên | `/files/a/b.txt` → `filePath=/a/b.txt` | `/users/a/b.txt` |

Các ví dụ mô tả ngữ nghĩa **PathPattern** chuẩn. Khi xét path encode, dấu slash cuối, servlet prefix hoặc biến rỗng, đừng chuyển bảng này thành bảo đảm cho một matcher chưa xác minh parser/config.

### 3.1. `*` là wildcard trong một segment, không ăn xuyên dấu slash

`/projects/*/tasks` có thể khớp `/projects/alpha/tasks`. Nó **không khớp** `/projects/alpha/team/tasks`, vì phần `*` chỉ ở segment giữa `projects` và `tasks`. Một segment chứa `*` thường **không đại diện cho sự vắng mặt của chính segment**: `/projects/*/tasks` không tự khớp `/projects/tasks`.

Ngộ nhận thường gặp là dùng `*` rồi tin mọi cấp thư mục được mở; thực chất cần phân biệt `*` và `**`. Trong quy tắc bảo mật, dùng wildcard càng rộng càng phải kiểm tra path phủ định.

### 3.2. `?` là đúng một ký tự trong segment

Với `/files/doc?.pdf`, `doc1.pdf` có thể khớp nhưng `doc12.pdf` không khớp. `?` trong **PathPattern** là wildcard của *một ký tự*; **`?` trong một URL thực tế** sau path lại thường mở đầu **query string**. Đừng đánh đồng hai ngữ cảnh.

`/api/orders/42?include=history` có dấu `?` làm **ranh giới query**, không phải ký tự wildcard trong dữ liệu path. Matcher path thường kiểm `/api/orders/42`; nếu cần quyền phụ thuộc `include=history`, kiểm query riêng qua logic phù hợp.

### 3.3. `**` ăn nhiều segment nhưng PathPattern hạn chế vị trí

`/reports/**` bao phủ `/reports`, `/reports/2026` và `/reports/2026/11/export.csv`. Trong `PathPattern`, `**` **chỉ được dùng ở cuối pattern** (tương tự biến catch-all `{*path}`). Ví dụ:

```text
Hợp lệ theo PathPattern:
  /reports/**
  /reports/{*remaining}
  /teams/{teamId}/documents/{documentId}

Không hợp lệ theo PathPattern:
  /reports/**/export
  /**/admin/**
  /files/{*path}/download
```

Lý do là `PathPattern` tránh mẫu nhiều nhánh nhập nhằng như `**` ở giữa; quy tắc parse được định rõ. **Một số mẫu Ant cũ cho phép `**` ở giữa**, nên code từng hoạt động với `AntPathRequestMatcher` có thể **không parse được** hoặc thay đổi ý nghĩa sau khi đổi sang `PathPatternRequestMatcher`.

Nếu cần match một route có cấu trúc trung gian, hãy thiết kế URL cụ thể, tách vài pattern, hoặc dùng `RegexRequestMatcher`/custom matcher thật cẩn thận, thay vì cố “đem nguyên mẫu Ant qua PathPattern”.

### 3.4. `{id}` vừa khớp vừa trích xuất

`/orders/{orderId}` mô tả **một segment bắt buộc** và tạo cặp `orderId=42` từ `/orders/42`. Nó **không tự xác minh user có quyền xem đơn 42**. Để quyết định cấp phép, phải dùng cả principal, ID trích xuất, resource metadata/tenant và chính sách nghiệp vụ.

Nếu muốn chỉ khớp ID số ở bước matching, `/orders/{orderId:[0-9]+}` dùng regex **bên trong segment**. Tuy nhiên regex không thay thế validation dữ liệu và authorization: số `42` hợp lệ cú pháp nhưng user vẫn có thể không được xem đơn đó.

### 3.5. `{*rest}` khác `**` ở việc lấy giá trị

Hai pattern có thể phủ phần đuôi của đường dẫn:

```text
/files/**          -> matching phần còn lại, không tự có biến tên "rest"
/files/{*rest}     -> matching phần còn lại và lấy giá trị "rest"
```

Với `/files/2026/report.csv`, `{*rest}` có thể trích xuất `rest=/2026/report.csv` (bao gồm slash đầu). Không dùng giá trị này như đường dẫn file hệ điều hành chưa được kiểm tra; cần giới hạn thư mục gốc, chuẩn hóa path và chống path traversal.

## 4. Bốn loại matcher thường gặp: cùng là RequestMatcher, khác ngữ nghĩa

### 4.1. `PathPatternRequestMatcher` – lựa chọn mới theo path segment

**`org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher`** có từ Spring Security 6.5, sử dụng `PathPattern` của Spring Framework. Nó nhận pattern tương đối với **context path** và có builder cấu hình `basePath` cho servlet prefix.

Ví dụ trong cấu hình Spring Security 6.5+:

```java
import static org.springframework.security.web.servlet.util.matcher
        .PathPatternRequestMatcher.withDefaults;

PathPatternRequestMatcher.Builder paths = withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(paths.matcher(HttpMethod.GET, "/api/orders/{orderId}"))
        .hasAuthority("orders.read")
    .requestMatchers(paths.matcher(HttpMethod.POST, "/api/orders"))
        .hasAuthority("orders.create")
    .requestMatchers(paths.matcher("/public/**"))
        .permitAll()
    .anyRequest().denyAll()
);
```

Đây là **mảnh cấu hình**, cần import `HttpMethod`, `PathPatternRequestMatcher`, nằm trong bean `SecurityFilterChain` và có authentication setup. `PathPatternRequestMatcher.Builder#matcher(HttpMethod, String)` khớp **đồng thời** method và path. Method null/overload chỉ có path thì rule không giới hạn HTTP method.

**Điểm đáng chú ý:**

- Pattern bắt đầu bằng `/`, viết tương đối với context path.
- `basePath` dùng khi các request cùng có servlet path prefix, ví dụ `basePath("/mvc")`.
- Hỗ trợ `{var}`, `{var:regex}`, `{*rest}` và trả biến qua `RequestMatcher.MatchResult`.
- Nên bảo đảm `HandlerMapping` liên quan dùng **`PathPatternParser` tương thích** với matcher. `withDefaults()` dùng các mặc định của parser; nếu MVC tùy chỉnh parser, cần phối hợp lại để controller và security match thống nhất.
- Là hướng thay thế mà Spring Security 6.5 khuyến nghị cho `AntPathRequestMatcher`/`MvcRequestMatcher` khi chuẩn bị nâng cấp Spring Security 7.

### 4.2. `MvcRequestMatcher` – khớp theo ngữ nghĩa Spring MVC đời trước

`org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher` dùng **`HandlerMappingIntrospector`** để đối chiếu ngữ nghĩa match của Spring MVC, có hỗ trợ variables. Nó hữu ích trong những project đã dùng tích hợp MVC trước đây.

Đặc trưng:

- Match có liên hệ cách Spring MVC cấu hình handler mapping và parser.
- Nếu DispatcherServlet không map ở mặc định `/` mà có **servlet path riêng**, phải khai báo đúng `servletPath`/builder để không nhầm route của các servlet.
- Có thể dùng `MvcRequestMatcher.Builder(introspector).servletPath("/mvc")` theo phiên bản 6.x tương thích.
- Tại **Spring Security 6.5**, `MvcRequestMatcher` đã **deprecated for removal**; tài liệu khuyên chuyển sang `PathPatternRequestMatcher`. Spring Security 7 không còn dùng nó như matcher mặc định.

Ví dụ dự án cũ (mã minh họa chuyển đổi, **không phải lựa chọn khuyên dùng cho code mới**):

```java
MvcRequestMatcher.Builder mvc = new MvcRequestMatcher.Builder(introspector)
    .servletPath("/mvc");

RequestMatcher matcher = mvc.pattern("/orders/{orderId}");
```

Để nâng cấp, xem xét `PathPatternRequestMatcher.withDefaults().basePath("/mvc").matcher("/orders/{orderId}")` và kiểm lại tất cả URI/servlet mappings trong integration tests; không chỉ thay tên class rồi mặc định mọi trường hợp đều giống nhau.

### 4.3. `AntPathRequestMatcher` – cú pháp Ant legacy

`org.springframework.security.web.util.matcher.AntPathRequestMatcher` áp dụng Ant-style pattern cho phần `servletPath + pathInfo` của request; **bỏ qua query string**. Nó dùng `AntPathMatcher` (với tối ưu cho vài mẫu `/**` đơn giản).

Ví dụ legacy:

```java
RequestMatcher legacy = AntPathRequestMatcher.antMatcher("/api/**");
```

Chú ý:

- `/api/**` ở Ant path matcher chuyên dụng có thể khớp `/api`, `/api/` và những path con.
- Ant-style có cách hiểu `*`, `?`, `**`, `{var}` và cú pháp lồng khác `PathPattern`; đặc biệt **`**` ở giữa path có thể được chấp nhận** theo Ant, trong khi `PathPattern` không cho phép.
- Constructor/matcher mặc định thường **phân biệt hoa/thường**, nhưng overload có thể cấu hình khác; không mặc định rằng mọi matcher đều không phân biệt chữ hoa.
- Trong **Spring Security 6.5**, class này cũng đã **deprecated for removal**, và Javadoc đề nghị dùng `PathPatternRequestMatcher`. Không khởi tạo mới nó trong thiết kế dài hạn chỉ vì code cũ đang dùng.

### 4.4. `RegexRequestMatcher` – cú pháp Java regular expression

`org.springframework.security.web.util.matcher.RegexRequestMatcher` dùng **Java regex**, không phải `PathPattern` hay Ant template:

```java
import static org.springframework.security.web.util.matcher
        .RegexRequestMatcher.regexMatcher;

RequestMatcher onlyNumericId = regexMatcher(
    HttpMethod.GET, "/api/orders/[0-9]+"
);
```

Nó có thể giới hạn HTTP method, ví dụ GET. Regex `[0-9]+` tương đương “một hay nhiều chữ số ASCII”; để dùng một dấu chấm literal, phải escape đúng cú pháp regex/Java string.

**Khác biệt quan trọng về query:** Theo Javadoc, `RegexRequestMatcher` match trên **`servletPath + pathInfo + queryString`** (nếu có query, dấu `?` được ghép vào chuỗi). Trái lại, `AntPathRequestMatcher` bỏ qua query, và matcher theo path thường chỉ xét path.

Do đó pattern `/api/orders/[0-9]+` có thể khớp `GET /api/orders/42` **nhưng không khớp** `GET /api/orders/42?preview=true` khi dùng RegexRequestMatcher, vì chuỗi match chứa thêm query. Hãy viết regex cho đúng phạm vi cần kiểm hoặc dùng matcher path và kiểm query ở policy riêng.

Không dùng `/api/orders/**` theo tư duy Ant cho `RegexRequestMatcher`: trong regex, `*` là lượng từ cho **phần tử ngay trước nó**, còn `**` đứng liên tiếp thường không hợp lệ hoặc có ý nghĩa khác. Regex phủ nhiều segment có dạng như `/api/orders/.*`; tuy nhiên `.*` quá rộng dễ mở đường dẫn ngoài ý định.

### 4.5. Custom RequestMatcher và matcher kết hợp

Nếu cần xét **host đáng tin**, header, query, method, IP hoặc trạng thái request khác mà path matcher không diễn đạt, có thể viết `RequestMatcher` tùy biến:

```java
RequestMatcher previewRequest = request ->
        "GET".equals(request.getMethod())
        && "/api/reports".equals(request.getServletPath())
        && "true".equals(request.getParameter("preview"));
```

Đây là **mảnh code trong ứng dụng Servlet**, chỉ minh họa cách tạo lambda cho interface functional `RequestMatcher` (với đường dẫn đơn giản, mapping mặc định). Trong thực tế cần xử lý `pathInfo`, context/servlet path, query parameter trùng tên và các dữ liệu không tin cậy; nếu muốn có path variables từ custom matcher, triển khai `matcher(request)` trả `MatchResult` phù hợp.

Có thể ghép điều kiện bằng `AndRequestMatcher`, `OrRequestMatcher`, `NegatedRequestMatcher`. Tuy nhiên việc kết hợp phức tạp có thể khiến policy khó đọc; cân nhắc matcher cụ thể cùng test các trường hợp bất lợi.

## 5. Bảng so sánh những khác biệt dễ gây lỗi

| Khía cạnh | PathPatternRequestMatcher | MvcRequestMatcher (6.x legacy) | AntPathRequestMatcher (legacy) | RegexRequestMatcher |
| --- | --- | --- | --- | --- |
| Ngôn ngữ | Spring `PathPattern` theo segment | Ngữ nghĩa mapping Spring MVC qua introspector | Ant-style path pattern | Java regular expression |
| `{id}` | Segment có tên; lấy biến | Có thể lấy biến template theo MVC | Hỗ trợ template theo Ant | **Không** hiểu `{id}` là template có tên |
| `**` ở giữa pattern | **Không hợp lệ** theo PathPattern | Phụ thuộc strategy MVC/version | Có thể hợp lệ với Ant | `**` không tương đương wildcard path |
| `{*rest}` | Catch-all có tên ở cuối | Phụ thuộc parser/config MVC | Không cùng contract PathPattern | Không phải cú pháp regex bắt buộc |
| Query string | Matcher theo path, không tự xét query | Theo ngữ nghĩa đường dẫn MVC | Bỏ qua query | **Chuỗi match có thể bao gồm query** |
| Case sensitivity | Theo parser cấu hình (mặc định thường có phân biệt) | Theo MVC config | Theo constructor (mặc định phân biệt) | Mặc định phân biệt; có tùy chọn khác |
| Servlet path | `basePath`/context-path rules | `servletPath` quan trọng | `servletPath + pathInfo` | `servletPath + pathInfo + query` |
| Kết hợp HTTP method | Builder nhận `HttpMethod` | Có thể cấu hình method | Có overload method | Có overload method |
| Khuyến nghị cho code mới | **Ưu tiên khi phù hợp** | Deprecated for removal 6.5 | Deprecated for removal 6.5 | Dùng khi thật sự cần regex |
| Test cần chú ý | Pattern parsing, variables, encoded path | DispatcherServlet/parser alignment | Legacy matching, query ignore | Escape regex, query, full-string matching |

**Không thay tất cả matcher bằng matcher khác mà không kiểm lại tập request được khớp.** “Cùng một pattern trông giống nhau” không chứng minh cùng policy.

## 6. RequestMatcher và biến đường dẫn: MatchResult khác Controller @PathVariable

Spring MVC controller có thể khai báo:

```java
@GetMapping("/api/documents/{documentId}")
public DocumentDto getDocument(@PathVariable String documentId) {
    return service.read(documentId);
}
```

Controller nhận biến `documentId` **sau khi mapping request vào method**. Trong khi đó Spring Security HTTP authorization có thể cần ID **trước khi request được dispatch đến controller**. `RequestMatcher.MatchResult#getVariables()` giúp đưa biến của pattern vào `RequestAuthorizationContext#getVariables()` để rule sử dụng.

Đây là **hai lần match tại hai vị trí khác nhau**; tên biến giống nhau là một quy ước cần giữ nhất quán, không phải cùng một Java object được chia sẻ mặc định.

Ví dụ `PathPatternRequestMatcher`:

```java
PathPatternRequestMatcher.Builder path = PathPatternRequestMatcher.withDefaults();

RequestMatcher byId =
    path.matcher(HttpMethod.GET, "/api/documents/{documentId}");
```

Với request `GET /api/documents/42`, matcher có thể trích biến `documentId=42`. Nhưng nếu client gọi `GET /api/documents/42/history`, pattern một segment ở trên **không khớp**. Muốn route lịch sử, nên định nghĩa pattern khác và policy phù hợp.

### 6.1. Dùng biến cho authorization động, không chỉ so khớp URL

Ví dụ dùng `AuthorizationManager<RequestAuthorizationContext>` kết hợp service nghiệp vụ do ứng dụng định nghĩa:

```java
@Bean
SecurityFilterChain docsSecurity(
        HttpSecurity http,
        DocumentAccessPolicy documentAccessPolicy
) throws Exception {

    PathPatternRequestMatcher.Builder paths =
            PathPatternRequestMatcher.withDefaults();

    AuthorizationManager<RequestAuthorizationContext> canReadDocument =
            (authentication, context) -> {
                Authentication user = authentication.get();

                if (user == null
                        || user instanceof AnonymousAuthenticationToken
                        || !user.isAuthenticated()) {
                    return new AuthorizationDecision(false);
                }

                String documentId = context.getVariables().get("documentId");
                boolean granted = documentId != null
                        && documentAccessPolicy.canRead(
                                user.getName(), documentId);

                return new AuthorizationDecision(granted);
            };

    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
                paths.matcher(
                    HttpMethod.GET, "/api/documents/{documentId}"
                )
        ).access(canReadDocument)
        .anyRequest().denyAll()
    );

    return http.build();
}
```

**Đây là mảnh tích hợp Spring, không phải một chương trình độc lập.** Cần các imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
```

`DocumentAccessPolicy` là **bean/service tự định nghĩa**, ví dụ `boolean canRead(String subject, String documentId)`, phải đọc dữ liệu đáng tin để xét owner, tenant, share và trạng thái tài liệu. Không suy quyền chỉ vì ID có dạng số hoặc user tự truyền ID đó.

Điểm kỹ thuật:

1. Sử dụng `documentId` từ **variables của matcher đã khớp**.
2. Dùng `Authentication` đã được Spring xác thực để xác định chủ thể.
3. Từ chối anonymous; `Authentication#isAuthenticated()` một mình chưa đủ để phân biệt mọi token “anonymous” trong Spring Security.
4. Resource service kiểm quyền trên **đúng document** từ nguồn dữ liệu tin cậy.
5. Bổ sung rule cho các hành động list, upload, export, delete... và method security nếu cần; `GET /api/documents/{documentId}` không bao phủ mọi đường vào dữ liệu.

Trong Spring Security 6.5, `AuthorizationManager#check(...)` là API cũ đã được đánh dấu deprecated; `authorize(...)` là API hướng tới. Lambda `AuthorizationManager` trong ví dụ sử dụng contract tương thích của Spring Security 6.5; khi nâng major version, hãy rà lại signature.

### 6.2. Biến đường dẫn không phải bằng chứng danh tính hay quyền

Đây là rule **nguy hiểm** nếu hệ thống không ràng buộc principal:

```text
Request: GET /api/users/admin/settings
Path variable: userId="admin"
=> Không được suy ra người gọi là admin.
```

Biến trong URL là **đầu vào do client chọn**. Phải so với `Authentication` đáng tin và điều kiện nghiệp vụ. Ngay cả khi `/api/users/{userId}` kiểm `authentication.name == userId`, còn cần bảo đảm ID này thực sự là ID canonical của user, có thể không tương đương email/username/subject claim ở các issuer khác nhau.

## 7. Quy tắc chọn matcher theo HTTP method, không chỉ path

Với đường dẫn `/api/documents/{documentId}`:

- `GET` có thể yêu cầu `documents.read`.
- `PATCH` có thể yêu cầu `documents.edit`.
- `DELETE` có thể yêu cầu `documents.delete`.

Đừng đặt `requestMatchers("/api/documents/**").hasAuthority("documents.read")` phía trước nếu muốn kiểm riêng mutation: matcher không giới hạn method có thể khớp cả POST, PATCH, DELETE trước khi rule chặt hơn được xét.

Ví dụ:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        paths.matcher(HttpMethod.DELETE, "/api/documents/{documentId}")
    ).hasAuthority("documents.delete")

    .requestMatchers(
        paths.matcher(HttpMethod.PATCH, "/api/documents/{documentId}")
    ).hasAuthority("documents.edit")

    .requestMatchers(
        paths.matcher(HttpMethod.GET, "/api/documents/{documentId}")
    ).hasAuthority("documents.read")

    .anyRequest().denyAll()
);
```

Bảng kết quả nếu principal có **duy nhất `documents.read`**:

| Request | Rule/method khớp | Kết quả ở HTTP authorization |
| --- | --- | --- |
| `GET /api/documents/42` | GET + `{documentId}` | ALLOW |
| `PATCH /api/documents/42` | PATCH + `{documentId}` | DENY |
| `DELETE /api/documents/42` | DELETE + `{documentId}` | DENY |
| `GET /api/documents/42/versions` | Không khớp ba rule một segment | DENY bởi fallback |
| `GET /api/documents` | Không khớp ba rule có ID | DENY bởi fallback |
| `GET /api/documents/abc` | Khớp `{documentId}` nếu không có regex giới hạn | ALLOW ở tầng URL; controller/service có thể từ chối ID không hợp lệ |

Bảng chỉ mô tả **rule-level authorization** của ví dụ; kết quả HTTP thực tế có thể còn phụ thuộc CSRF, authentication, controller và resource policy.

## 8. Java 17 chạy độc lập: phân biệt một segment, nhiều segment và regex

Chương trình dưới đây dùng **Java SE 17**, không phụ thuộc Spring. Nó dùng các regex Java được xây dựng rõ ràng để **mô phỏng ba ý nghĩa**:

- Một segment `{id}`: `^/reports/[^/]+$`.
- Không hoặc nhiều segment `/**` ở cuối: `^/reports(?:/.*)?$`.
- Một segment ID số `{id:[0-9]+}`: `^/reports/[0-9]+$`.

**Đây là mô hình học tập**, không phải implementation thay thế cho `PathPatternRequestMatcher`. Khi kiểm thực tế, dùng Spring matcher tương ứng với servlet request và parser của dự án.

Tạo tệp **`PathWildcardDemo.java`**:

```java
import java.util.List;
import java.util.regex.Pattern;

public class PathWildcardDemo {

    static final Pattern ONE_SEGMENT =
            Pattern.compile("^/reports/[^/]+$");

    static final Pattern ALL_DESCENDANTS =
            Pattern.compile("^/reports(?:/.*)?$");

    static final Pattern NUMERIC_ID =
            Pattern.compile("^/reports/[0-9]+$");

    record Request(String method, String path, String query) {
        String pathAndQuery() {
            return query == null ? path : path + "?" + query;
        }
    }

    static boolean matches(Pattern pattern, String path) {
        return pattern.matcher(path).matches();
    }

    public static void main(String[] args) {
        List<String> paths = List.of(
                "/reports",
                "/reports/42",
                "/reports/42/items",
                "/reports/abc",
                "/reports/42/"
        );

        for (String path : paths) {
            System.out.println(
                    path
                    + " | one=" + matches(ONE_SEGMENT, path)
                    + " | deep=" + matches(ALL_DESCENDANTS, path)
                    + " | numeric=" + matches(NUMERIC_ID, path)
            );
        }

        Request withQuery =
                new Request("GET", "/reports/42", "download=true");

        System.out.println("path-only: "
                + matches(NUMERIC_ID, withQuery.path()));
        System.out.println("path+query full regex: "
                + matches(NUMERIC_ID, withQuery.pathAndQuery()));
        System.out.println("GET numeric: "
                + ("GET".equals(withQuery.method())
                   && matches(NUMERIC_ID, withQuery.path())));
        System.out.println("POST numeric: "
                + ("POST".equals(withQuery.method())
                   && matches(NUMERIC_ID, withQuery.path())));
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac PathWildcardDemo.java
java PathWildcardDemo
```

Stdout chính xác:

```text
/reports | one=false | deep=true | numeric=false
/reports/42 | one=true | deep=true | numeric=true
/reports/42/items | one=false | deep=true | numeric=false
/reports/abc | one=true | deep=true | numeric=false
/reports/42/ | one=false | deep=true | numeric=false
path-only: true
path+query full regex: false
GET numeric: true
POST numeric: false
```

**Giải thích từng trường hợp:**

1. `/reports` không có segment ID, nên `one=false`, nhưng mẫu đuôi `/**` mô phỏng khớp zero segment con: `deep=true`.
2. `/reports/42` có đúng một segment ID là số: cả ba điều kiện đều đúng.
3. `/reports/42/items` có thêm một segment: chỉ điều kiện phủ nhiều segment đúng.
4. `/reports/abc` đủ một segment nhưng không phải số: `one=true`, `numeric=false`.
5. `/reports/42/` có trailing slash làm khác mẫu một segment được minh họa; PathPattern thực tế còn phụ thuộc parser/trailing-separator policy.
6. Query `download=true` không làm đổi **path**; regex chạy trên **path+query** như `RegexRequestMatcher` cần tính thêm phần query, nên biểu thức giới hạn cuối chuỗi có thể không khớp.
7. Method GET và POST có thể được phân biệt độc lập với path.

**Không áp dụng output mô phỏng này như bảng kết quả bảo mật tuyệt đối** cho Ant/MVC/PathPattern/Regex matcher ở tất cả phiên bản. Nó minh họa những câu hỏi cần đưa vào bài test của matcher thật.

## 9. Những URL khó: slash cuối, encoding, dấu chấm phẩy, chữ hoa và query

Matcher theo path trong thực tế đứng trên nhiều tầng chuẩn hóa:

```text
Client URL
 -> reverse proxy / WAF
 -> servlet container: path decoding, normalization, mapping
 -> Spring Security: FilterChainProxy + RequestMatcher
 -> Spring MVC: HandlerMapping / @RequestMapping
 -> service / repository
```

Nếu **proxy, Spring Security và Spring MVC hiểu URL khác nhau**, rule bảo mật có thể kiểm một tài nguyên nhưng controller xử lý tài nguyên khác. Đây là lý do không nên tự viết matcher bằng phép so chuỗi đơn giản rồi giả định nó đồng nhất với đường routing của MVC.

### 9.1. Trailing slash

`/api/items/42` và `/api/items/42/` có thể khác nhau tùy matcher/parser. Các phiên bản Spring Framework hiện đại không mặc định xem hai đường này tương đương trong mọi cấu hình.

**Khuyến nghị:** chọn canonical path rõ ràng, kiểm tình huống có/không trailing slash trong integration test, và đừng dựa vào khả năng framework tự chuyển hướng hoặc chuẩn hóa khi chưa xác minh. Một bypass có thể xuất hiện nếu matcher từ chối rất chính xác nhưng controller chấp nhận biến thể khác qua đường cấu hình riêng.

### 9.2. Encoded slash và path traversal

`%2F` là ký tự slash được percent-encode. Path parser theo segment có thể xử lý encoded path khác cách decode toàn chuỗi rồi split; servlet container/proxy cũng có thể chặn hoặc chuẩn hóa URL theo policy riêng.

Cần test các biến thể:

```text
/api/files/a%2Fb
/api/files/a/b
/api/files/%2e%2e/secret
/api/files/../secret
/api/files/a%252Fb
```

Không nên tự tuyên bố một tổ hợp encoded path “chắc chắn khớp/không khớp” khi chưa biết container, firewall và matcher. Không dùng path variable làm đường dẫn file hệ điều hành trực tiếp: phải normalize và kiểm ranh giới thư mục sau khi decode phù hợp.

### 9.3. Matrix variables, dấu chấm phẩy trong segment

Spring MVC có khái niệm **matrix variables** như `/cars/42;color=red`. Tùy cấu hình, `StrictHttpFirewall` có thể chặn semicolon và những ký tự URL không được cho phép trước khi matcher chạy. Nếu ứng dụng chủ động dùng matrix variables, phải thống nhất firewall, parser, request matcher và controller, không tùy tiện tắt kiểm tra bảo mật.

### 9.4. Chữ hoa/chữ thường

`/Admin/report` có nhất thiết giống `/admin/report`? Không. Nhiều path matcher mặc định phân biệt chữ hoa; một số constructor/parser cho phép cấu hình khác. Nếu URL do proxy hoặc container thay đổi case, phải test. Không dùng một rule `/admin/**` rồi đoán mọi biến thể case cũng bị bảo vệ như nhau.

### 9.5. Query string và thứ tự tham số

Một path matcher `/download/{id}` thường không phân biệt `/download/42?format=csv` và `/download/42?format=pdf` ở bước match URL path. Nếu quyền xuất PDF khác CSV, phải áp dụng **policy có xét query/format** ở nơi phù hợp.

Đừng dùng regex không có kiểm soát trên toàn URL chỉ để đọc một query parameter: thứ tự tham số, dấu escape, nhiều giá trị cùng tên và encoding dễ làm điều kiện không như dự kiến. Ưu tiên `request.getParameter(...)` cùng validation hoặc một policy service có kiểu dữ liệu rõ ràng.

## 10. Context path và servlet path: cùng mẫu nhưng phạm vi khác nhau

Giả sử deploy ở:

```text
Context path:  /portal
Servlet path:  /mvc
Endpoint:      /orders/42
Request URI:   /portal/mvc/orders/42
```

Bài toán gồm hai tiền tố:

- **`/portal`** là context path của ứng dụng, thường **không viết vào** pattern của `PathPatternRequestMatcher`.
- **`/mvc`** là servlet path (nếu DispatcherServlet mapping như vậy). Matcher cần được cấu hình đúng prefix/`basePath` theo đường dẫn mà nó thực sự xét.
- Phần cuối `/orders/42` là path do controller handling.

Với `PathPatternRequestMatcher`, có thể nhóm matcher cùng servlet path:

```java
PathPatternRequestMatcher.Builder mvc =
        PathPatternRequestMatcher.withDefaults()
                .basePath("/mvc");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.matcher(HttpMethod.GET, "/orders/{orderId}"))
        .hasAuthority("orders.read")
    .anyRequest().denyAll()
);
```

Không thêm `/portal` vào pattern do chỉ nhìn URL browser. Với `MvcRequestMatcher` cũ, cơ chế `setServletPath("/mvc")` tương ứng nhưng API khác; với `AntPathRequestMatcher`, đường được so khớp là `servletPath + pathInfo`.

**Khi có nhiều Servlet**, matcher tạo tự động từ một String có thể không đủ rõ. Chỉ rõ servlet path và matcher phù hợp, tránh tưởng cùng một `/admin` có cùng nghĩa với mọi servlet mapping.

## 11. Thứ tự rule và wildcard rộng: ranh giới bảo mật

Nếu dùng:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

Thì `GET /api/admin/audit` đã khớp `/api/**`, nên rule phía dưới **không chạy**. Đây là lỗi **first-match-wins**, không phải lỗi regex hay URI variable.

Sửa:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
        .hasAuthority("documents.read")
    .anyRequest().denyAll()
)
```

Ngoài ra:

- Đừng gán `/**` cho `permitAll` trong một chain chứa endpoint nhạy cảm.
- Đừng tin rằng authority `documents.read` tự cho phép xem **mọi** tài liệu; nếu policy cần owner/tenant, phải check theo ID.
- Đừng đặt rule DELETE/POST phía sau wildcard không giới hạn method đã allow.
- Không có rule fallback rõ ràng có thể gây hành vi khó lý giải; `anyRequest().denyAll()` làm thiết kế dễ kiểm toán.
- Nếu dùng nhiều `SecurityFilterChain`, xem thêm `securityMatcher` và thứ tự `@Order`: rule bên trong chain **không có tác dụng** với request không vào chain đó.

## 12. Lưu ý nâng cấp Spring Security 6.5 → 7

**Tên phương thức `requestMatchers(String...)` không phải lời cam kết dùng mãi một kiểu matcher.**

- Trong các project Spring Security 6.x, cơ chế tạo matcher từ String có thể chọn implementation dựa trên Spring MVC có mặt hay không, cấu hình và các builder đã đăng ký. Tài liệu 6.x truyền thống mô tả `MvcRequestMatcher` khi có MVC, `AntPathRequestMatcher` khi không có MVC.
- **Spring Security 6.5** giới thiệu `PathPatternRequestMatcher` và tài liệu migration hướng dẫn chuẩn bị để dùng matcher này.
- **Spring Security 7** chuyển sang `PathPatternRequestMatcher` mặc định; `AntPathRequestMatcher` và `MvcRequestMatcher` không còn là lựa chọn được hỗ trợ trong lộ trình này.
- Vì `PathPattern` có giới hạn `**` ở cuối, những mẫu như `/**/admin/**` từng chạy dưới Ant có thể **không hợp lệ** khi migrate. Trước khi cập nhật, kiểm parser và test lại toàn bộ tập URL.
- Với matcher explicit, import chính xác class bạn muốn dùng. Với matcher String tự tạo, đọc tài liệu đúng phiên bản Spring Security đang chạy và xác nhận DSL chọn implementation nào.

Trong project đang hoạt động, hãy viết **test về kết quả match thực tế** thay vì dựa vào tên class hay phỏng đoán. Khi nâng cấp major version, giữ lại bộ test đó để bắt lỗi semantic regression.

## 13. Bộ kiểm thử tối thiểu cho path matcher trong API thực tế

Giả sử có các rule:

```text
GET    /api/documents/{documentId}          -> documents.read
PATCH  /api/documents/{documentId}          -> documents.edit
GET    /api/documents/{documentId}/history  -> documents.history
GET    /public/**                           -> permitAll
anyRequest                                -> denyAll
```

Các test cần có:

| Input | Phương án kiểm tra |
| --- | --- |
| `GET /api/documents/42` | Matcher bắt đúng một segment; biến `documentId=42` |
| `GET /api/documents/42/history` | Không bị rule một segment chọn nhầm; khớp history |
| `PATCH /api/documents/42` | Không rơi vào quyền read |
| `DELETE /api/documents/42` | Không match hai rule GET/PATCH; fallback deny |
| `GET /api/documents` | Không có ID; không khớp `{documentId}` |
| `GET /api/documents/abc` | Với `{documentId}` thông thường có thể khớp, cần validation/policy khác |
| `GET /api/documents/42?include=history` | Path matcher có thể vẫn match ID 42; kiểm query ở logic riêng |
| `GET /api/documents/42/` | Kiểm trailing slash thực tế |
| `GET /API/documents/42` | Kiểm case sensitivity thực tế |
| `GET /api/documents/a%2Fb` | Kiểm encoded slash qua container/firewall/parser |
| `GET /public/help` | `permitAll` cho đúng public path |
| `GET /publicity/help` | **Không** vô tình bị `/public/**` cho phép |
| `GET /api/admin/secret` | Không bị wildcard rộng `/api/**` cho phép sai |
| Có context path/servlet path | Matcher path dùng đúng namespace, không bỏ/multiply prefix |
| Có HTTP method OPTIONS/CORS | Filter/authorization CORS xử lý theo thiết kế, không mặc nhiên deny/allow |
| Có Servlet `ERROR`/`FORWARD` dispatch | Kiểm theo policy dispatch đã chủ động cấu hình |

Đừng chỉ test với principal **có quyền**. Cần test anonymous, user đã xác thực nhưng thiếu quyền, scope/role sai tiền tố và đường dẫn rất gần pattern được allow.

### Test matcher thật bằng MockMvc/Spring Security Test

Sau khi cấu hình một Spring Boot test context có controller và `spring-security-test`, có thể viết test (mã minh họa, **không phải tệp chạy độc lập**):

```java
mvc.perform(get("/api/documents/42")
        .with(user("alice").authorities(
                new SimpleGrantedAuthority("documents.read"))))
    .andExpect(status().isOk());

mvc.perform(patch("/api/documents/42")
        .with(user("alice").authorities(
                new SimpleGrantedAuthority("documents.read")))
        .with(csrf()))
    .andExpect(status().isForbidden());
```

`isOk()` giả định controller trong test trả 200 khi thành công. Nếu controller không tồn tại, request đã qua authorization vẫn có thể trả 404. Với POST/PATCH/DELETE, `with(csrf())` giúp tách lỗi CSRF khỏi lỗi phân quyền khi CSRF đang bật.

Nếu muốn test **đúng bản thân matcher**, có thể dùng `MockHttpServletRequest` trong Spring Test để gọi `matcher.matches(request)` và kiểm `matcher.matcher(request).getVariables()`, nhưng nhớ thiết lập `servletPath`/`contextPath` tương ứng với runtime thật.

## 14. Những lỗi thường gặp và cách khắc phục

| Lỗi | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Dùng `*` để match nhiều cấp URL | `*` chỉ đại diện nội dung trong một segment | Dùng `/**` nếu thật sự muốn bao phủ descendants, hoặc route cụ thể hơn |
| Dùng `**` ở giữa PathPattern | PathPattern không cho catch-all ở giữa | Tách pattern hoặc dùng matcher khác có kiểm thử |
| Dùng `{id}` rồi cho rằng ID hợp lệ/có quyền | Path variable chỉ là dữ liệu client | Validate ID, kiểm owner/tenant/permission từ server |
| Dùng `RegexRequestMatcher` với pattern Ant `/api/**` | Regex `*` không phải wildcard path | Viết Java regex chính xác, test query/method |
| Dùng `RegexRequestMatcher` với `/api/orders/[0-9]+` rồi URL có query không match | RegexRequestMatcher có thể bao gồm query string | Chủ động xử lý query/regex hoặc dùng path matcher |
| Giả định `requestMatchers` String luôn là Ant | Implementation phụ thuộc phiên bản/cấu hình | Kiểm Spring Security version; dùng matcher explicit nếu cần |
| Quên servlet path khi nhiều servlet | Security và MVC có thể xét prefix khác nhau | Cấu hình `basePath`/`servletPath` phù hợp |
| Ghi thêm context path vào PathPattern | Dễ bị lặp prefix và không match | Viết pattern tương đối với context path |
| Đặt `/api/** permitAll` trước rule admin | Rule rộng khớp trước và che rule admin | Cụ thể trước, fallback sau |
| Dùng `path variable` làm file path không kiểm | Có thể traversal/escaped path | Chuẩn hóa, giới hạn root, validate server-side |
| Tin `@GetMapping` luôn dùng cùng parser với Spring Security | Có thể lệch config/versions | Đồng bộ parser/Matcher và integration test |
| Chỉ kiểm đường dẫn có dấu slash chuẩn | Có thể hở với slash/encoding/case khác | Test URL edge cases và canonical routing |
| Dùng một matcher chỉ theo path cho mọi method | GET read có thể mở mutation | Kết hợp HTTP method và rule riêng |
| Tắt firewall để request khác lạ “cho chạy” | Làm thay đổi bề mặt tấn công | Hiểu nguyên nhân, sửa policy cụ thể, không tắt toàn bộ |

## 15. Câu hỏi tự kiểm tra

**1. `/api/orders/*` có khớp `/api/orders/42/items` không?**  
Không theo PathPattern single-segment wildcard; nó không ăn qua dấu slash.

**2. `/api/orders/**` có khác `/api/orders/{orderId}` không?**  
Có. `/**` có thể khớp nhiều segment (kể cả zero segment ở cuối); `{orderId}` yêu cầu đúng một segment và có tên biến.

**3. Có thể dùng `/api/**/admin` trong PathPattern không?**  
Không; `**` phải ở cuối PathPattern. Một mẫu Ant cũ có thể khác, nên cần test khi migrate.

**4. `GET /api/orders/42?expand=true` có nhất thiết khác khi dùng RegexRequestMatcher?**  
Có thể. RegexRequestMatcher xét chuỗi gồm path và query; một regex giới hạn cuối path có thể không khớp khi có query. Với matcher theo path, query thường được xử lý riêng.

**5. `{userId}` từ URL có chứng minh người gọi là user đó không?**  
Không. Cần authentication đáng tin và policy kiểm quan hệ/tenant.

**6. Trong Spring Security 6.5, matcher nào được khuyến nghị thay thế AntPathRequestMatcher/MvcRequestMatcher?**  
`PathPatternRequestMatcher`.

**7. Có `documents.read` thì request `GET /api/documents/42` chắc chắn xem được nội dung 42?**  
Không. Nếu nghiệp vụ yêu cầu owner/share/tenant, cần kiểm thêm trên tài liệu 42.

**8. Vì sao nên test `/api/orders/42/` và `/api/orders/42` riêng?**  
Trailing slash matching có thể khác theo parser/config; không nên giả định tương đương.

**9. `requestMatchers(HttpMethod.GET, "/api/orders/**")` có áp dụng cho POST không?**  
Không; match method GET. POST cần rule riêng hoặc fallback xử lý.

**10. `securityMatcher` và `requestMatchers` sử dụng cùng một pattern có đồng nghĩa cùng tác động không?**  
Không. Một cái chọn **SecurityFilterChain**, một cái chọn **authorization rule trong chain đã được chọn**.

## Tóm tắt ứng dụng

- **`*` và `?`** chỉ nói về ký tự trong một segment; **`**`** bao phủ các segment phía cuối; **`{id}`** bắt một segment và trích biến; **`{*rest}`** bắt phần path còn lại theo PathPattern.
- **`PathPatternRequestMatcher`** tuân cú pháp PathPattern và là hướng khuyến nghị trong Spring Security 6.5+/7. **`MvcRequestMatcher`** và **`AntPathRequestMatcher`** là đường legacy/deprecated ở 6.5. **`RegexRequestMatcher`** dùng Java regex với ngữ nghĩa chuỗi match khác, đặc biệt query.
- **Một match thành công không đồng nghĩa được phép**. Spring Security còn quyết định authority, và nhiều ứng dụng cần kiểm thêm tài nguyên/tenant/owner.
- **Luôn test trên stack thật**: HTTP method, path segments, trailing slash, case, encoded URL, context/servlet path, parser, query và thứ tự rule.
- **Không đoán matcher mặc định chỉ từ tên `requestMatchers`**; phải kiểm phiên bản và cấu hình.

## Tài liệu tham khảo

- [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 – Migrate to PathPatternRequestMatcher](https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html)
- [Spring Security 6.5 – PathPatternRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html)
- [Spring Security 6.5 – AntPathRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/AntPathRequestMatcher.html)
- [Spring Security 6.5 – MvcRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/MvcRequestMatcher.html)
- [Spring Security 6.5 – RegexRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/RegexRequestMatcher.html)
- [Spring Framework – Mapping Requests và PathPattern syntax](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
