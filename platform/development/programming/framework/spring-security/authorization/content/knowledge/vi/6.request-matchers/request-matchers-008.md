# Matcher theo header, tham số hoặc thuộc tính request có kiểm soát

## 1. Bài toán: chọn đúng quy tắc từ dữ liệu request nhưng không biến dữ liệu đó thành quyền

Một HTTP request không chỉ có đường dẫn và phương thức. Nó còn mang **header**, **query/form parameter**, **thuộc tính request (request attribute)** và dữ liệu do hạ tầng tạo hoặc chuyển tiếp. Spring Security cho phép dùng những dữ liệu này để lựa chọn chính sách phù hợp thông qua `RequestMatcher`. Tuy nhiên, đây là vùng rất dễ tạo lỗ hổng nếu coi mọi thứ có trong request là đáng tin.

Ví dụ ứng dụng cung cấp:

- `GET /api/reports`: xem danh sách báo cáo, cần `report:read`.
- `GET /api/reports?format=csv`: xuất báo cáo, cần `report:export`.
- Header `X-Api-Version: v2`: yêu cầu sử dụng biến thể giao thức v2, **không** có nghĩa người gửi là quản trị viên.
- Request attribute `internal.verifiedTenant` do một thành phần máy chủ xác thực thiết lập: có thể hỗ trợ xác định tenant đã được kiểm chứng nếu nguồn tạo và thời điểm tạo đáng tin.

Nếu cấu hình chỉ có matcher đường dẫn `/api/reports` với `report:read`, một yêu cầu mang `?format=csv` có thể đi vào logic export mà không bị yêu cầu quyền export. Ngược lại, nếu triển khai:

```text
if (header X-Role == ADMIN) -> allow
```

thì người gửi có thể tự giả mạo header. Cả hai lỗi xuất phát từ việc **trộn lẫn phân loại request với quyết định phân quyền**.

### Mô hình đúng

```text
                         HttpServletRequest
                  method, path, header, parameter,
                    attribute được tạo ở server
                                  |
                                  v
                    [RequestMatcher.matches()]
                      phân loại request thuộc
                        quy tắc / nhánh nào
                                  |
                                  v
                         [AuthorizationManager]
                   Authentication + GrantedAuthority
                   + chính sách của nhánh được chọn
                                  |
                                  v
                        [Service / Data policy]
                    tenant, owner, object, workflow
                                  |
                            ALLOW / DENY
```

**RequestMatcher quyết định “request nào?”; AuthorizationManager và chính sách nghiệp vụ quyết định “ai được làm gì?”.** Một header/parameter có thể được sử dụng để chọn nhánh cần kiểm tra quyền **mạnh hơn**, nhưng không được dùng làm bằng chứng rằng quyền đó đã được cấp.

Mục tiêu sau bài: hiểu nguồn gốc và mức độ tin cậy của từng trường, dùng matcher dựng sẵn hoặc tùy chỉnh đúng phiên bản, kết hợp điều kiện an toàn, giữ hành vi không khớp theo nguyên tắc mặc định từ chối và kiểm thử các trường hợp giả mạo/nhập nhằng.

## 2. Cấu trúc API và các trường quan trọng

Trong Spring Security Servlet, `org.springframework.security.web.util.matcher.RequestMatcher` là một interface chức năng. Phương thức cốt lõi:

```java
boolean matches(jakarta.servlet.http.HttpServletRequest request);
```

Một matcher có thể dựa vào path, method, header, parameter hoặc thông tin khác của `HttpServletRequest`. Nó trả về true/false cho điều kiện khớp. Một số implementation hỗ trợ lấy biến từ kết quả match qua `matcher(request)` và `RequestMatcher.MatchResult`, nhưng không cần đến khả năng này khi chỉ xét đúng/sai.

| Loại dữ liệu | Cách lấy thông dụng | Ai thường kiểm soát? | Dùng cho việc gì? |
| --- | --- | --- | --- |
| HTTP method | `request.getMethod()` | Client chọn; server quyết định route | Chọn thao tác GET/POST/PATCH... |
| Path và servlet path | `getRequestURI()`, `getServletPath()`, `getPathInfo()` | Client chọn URL, server/router chuẩn hóa | Chọn endpoint hoặc nhóm endpoint |
| Header | `getHeader(name)`, `getHeaders(name)` | Thường do client gửi, đôi khi proxy thêm | API version, format, content negotiation |
| Parameter | `getParameter(name)`, `getParameterValues(name)`, `getParameterMap()` | Client gửi query hoặc form | Chọn nhánh “preview/export” theo hợp đồng |
| Request attribute | `getAttribute(name)` | Thành phần Java phía server đặt qua `setAttribute` | Ngữ cảnh nội bộ đã được kiểm chứng |
| Dispatcher type | `getDispatcherType()` | Servlet container/dispatch nội bộ | Quy tắc REQUEST/FORWARD/ERROR/ASYNC |
| Media type | `getContentType()`, header `Accept` | Client báo loại payload/kết quả mong muốn | Chọn xử lý dữ liệu; không làm bằng chứng quyền |
| Remote IP / host | `getRemoteAddr()`, `getServerName()` | Hạ tầng, proxy và cấu hình ảnh hưởng | Kiểm soát hạ tầng ở phạm vi thích hợp |

Chưa có xác thực, những trường như `X-User`, `X-Role`, `X-Internal`, `tenantId`, `admin=true` đều chỉ là **giá trị đầu vào**. Dù chúng trông giống thông tin bảo mật, không vì thế mà trở thành `Authentication` hay `GrantedAuthority`.

### 2.1. Ba nguồn thông tin cần phân biệt

1. **Client-controlled:** header tùy ý, query string, form field, path và phần lớn body. Bất kỳ ai gọi HTTP API đều có thể gửi chúng. Chỉ nên dùng để **mô tả yêu cầu** và kiểm tra dữ liệu.
2. **Infrastructure-asserted:** giá trị proxy, API gateway hoặc load balancer thêm vào sau khi **xác minh**. Chỉ đáng tin khi server không thể bị gọi vòng qua ranh giới đó, giá trị do client gửi được loại bỏ/thay thế và có cơ chế trust rõ ràng.
3. **Server-verified:** thuộc tính được filter/service nội bộ tạo từ token hoặc nguồn dữ liệu đã được kiểm chứng. Ví dụ ID tenant đã xác minh từ principal và membership, không phải tenant do client tự khai.

Không thể tin một request attribute chỉ dựa vào tên có tiền tố `internal.`. Nếu code đặt:

```java
request.setAttribute(
    "internal.verifiedTenant",
    request.getHeader("X-Tenant-Id")
);
```

mà không xác minh membership, thì dù dữ liệu nằm trong attribute server-side, nó vẫn có **nguồn gốc chưa đáng tin**. Nguồn gốc và bước xác minh mới là ranh giới quyết định.

## 3. Matcher theo header: điều kiện chính xác nhưng không phải xác thực

### 3.1. Header có thể dùng để phân loại request

Một số ví dụ phù hợp:

- `X-Api-Version: v2` dùng để chọn phiên bản giao thức cho client đã được phân quyền bình thường.
- `Accept: text/csv` mô tả định dạng kết quả; nếu phản hồi là export dữ liệu nhạy cảm thì vẫn cần quyền export.
- `X-Requested-With: XMLHttpRequest` từng được dùng để nhận diện kiểu client, **không đủ làm cơ chế xác thực hoặc thay thế CSRF**.
- Header định tuyến qua proxy có thể mô tả kênh xử lý nhưng phải có đường fallback bảo vệ.

Nếu dùng header để mở nhánh bảo mật nhạy cảm, hãy nghĩ tới trường hợp header **không có**, **sai giá trị**, **bị lặp**, **đổi chữ hoa/thường**, hoặc bị proxy thay đổi. Không dùng “có header nghĩa là nội bộ”.

### 3.2. `RequestHeaderRequestMatcher` có sẵn

Spring Security có `RequestHeaderRequestMatcher` để kiểm tra tên header và có thể kiểm tra giá trị mong đợi.

Đoạn mã minh họa tích hợp:

```java
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.security.web.util.matcher.RequestHeaderRequestMatcher;

RequestMatcher anyVersionHeader =
    new RequestHeaderRequestMatcher("X-Api-Version");

RequestMatcher onlyV2 =
    new RequestHeaderRequestMatcher("X-Api-Version", "v2");
```

- Cách tạo một đối số kiểm tra **sự hiện diện** của header; không quan tâm giá trị.
- Cách tạo hai đối số kiểm tra giá trị cụ thể do matcher hỗ trợ. Theo JavaDoc, khi có nhiều giá trị header, implementation này so sánh giá trị đầu tiên, vì vậy **không nên dùng nó làm bộ xác minh một header nhạy cảm có thể bị lặp**.
- Đó là phép so khớp request. Nếu principal không có `report:read` hoặc `report:export` tương ứng, chỉ có `X-Api-Version: v2` không được giúp vượt qua kiểm tra quyền.

HTTP header name được xử lý không phân biệt hoa/thường theo quy ước giao thức; header value có thể có ngữ nghĩa và cách chuẩn hóa riêng. Không tự viết so sánh `contains("admin")`, `startsWith("trusted")` hoặc mặc định trim/lowercase mọi giá trị rồi coi đó là bằng chứng đặc quyền.

### 3.3. Header lặp và nhiều giá trị

Các API của Servlet cung cấp:

```java
String first = request.getHeader("X-Api-Version");
java.util.Enumeration<String> all =
    request.getHeaders("X-Api-Version");
```

`getHeader` thường lấy một giá trị; nếu tồn tại nhiều giá trị mà thành phần phía trước và phía sau xử lý khác nhau, kết quả chọn rule có thể **khác hành vi thực thi**. Đây là một dạng rủi ro xử lý request nhập nhằng.

Ví dụ request có hai dòng header:

```http
GET /api/reports HTTP/1.1
Host: example.test
X-Api-Version: v2
X-Api-Version: v1
```

Nếu security chỉ xem giá trị đầu còn controller/gateway chọn giá trị sau, “phiên bản được bảo vệ” có thể không phải phiên bản được chạy. Khi giá trị điều khiển hành vi nhạy cảm, hãy định nghĩa **một dạng duy nhất hợp lệ** hoặc chuẩn hóa tại gateway/entrypoint đáng tin trước khi cả security và nghiệp vụ sử dụng. Không tự suy đoán cách container ghép nhiều header; hãy test đúng stack/proxy của ứng dụng.

### 3.4. Header sau reverse proxy

Các header như `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto` hoặc tên header nội bộ của gateway chỉ đáng tin khi đường truyền proxy đã được bảo vệ đúng, proxy bỏ header đầu vào giả mạo, và ứng dụng chỉ truy cập được qua kênh cho phép.

Một request có:

```http
X-Internal: true
X-Role: ADMIN
X-Forwarded-For: 127.0.0.1
```

**không tự động trở thành request nội bộ, admin hay request từ localhost.** Cũng không dùng `Origin` hay `Referer` làm chứng cứ chính cho danh tính. Kiểm soát CORS, CSRF, proxy trust và authentication phục vụ các vấn đề khác nhau.

## 4. Matcher theo parameter: query, form và tính đa trị

### 4.1. `getParameter` thực sự đọc gì?

Với Servlet request, `getParameter("format")` thường lấy giá trị parameter đã được parse từ query và, tùy request/content type, dữ liệu form. Nó **không tự động parse mọi JSON body**.

Các trường hợp:

```http
GET /api/reports?format=csv HTTP/1.1
GET /api/reports?format=pdf HTTP/1.1
GET /api/reports?format=csv&format=pdf HTTP/1.1
GET /api/reports?format= HTTP/1.1
GET /api/reports HTTP/1.1
```

Kết quả:

- Với `format=csv`, parameter tồn tại và có giá trị csv.
- Với `format=`, parameter có thể tồn tại nhưng giá trị là chuỗi rỗng, **khác với parameter vắng mặt**.
- Với `format=csv&format=pdf`, parameter có **nhiều giá trị**; chỉ đọc `getParameter` có thể bỏ qua phần còn lại. Dùng `getParameterValues` để phát hiện nhập nhằng khi hợp đồng chỉ cho một.
- Với request không có format, `getParameterMap().containsKey("format")` là false theo hành vi thông thường.

Một yêu cầu dạng JSON:

```http
POST /api/reports HTTP/1.1
Content-Type: application/json

{"format":"csv"}
```

không tự biến khóa `format` trong JSON thành request parameter. Quyết định bảo mật phụ thuộc body tốt nhất được thực hiện tại tầng xử lý nghiệp vụ sau khi body được parse/validated; tránh custom matcher tiêu thụ InputStream rồi khiến controller đọc body sai hoặc đọc hai lần không nhất quán.

### 4.2. `ParameterRequestMatcher` và tương thích phiên bản

Spring Security **6.4+** giới thiệu `ParameterRequestMatcher` để match request parameter. Hai constructor thường gặp:

```java
import org.springframework.security.web.util.matcher.ParameterRequestMatcher;

var anyFormat = new ParameterRequestMatcher("format");
var csvFormat = new ParameterRequestMatcher("format", "csv");
```

Đây là **đoạn API dành cho Spring Security 6.4 trở lên**. Nếu dự án còn Spring Security 6.3, không sao chép class này rồi cho rằng có sẵn; thay bằng matcher lambda dựa trên Servlet API hoặc thành phần tương thích phiên bản.

Ví dụ **không phụ thuộc `ParameterRequestMatcher`**, dùng được theo kiểu API custom matcher của Spring Security 6.x:

```java
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher anyExportFormat = request ->
    request.getParameterMap().containsKey("format");
```

Dòng trên chỉ phân loại “có parameter `format`”, không kiểm tra giá trị hợp lệ, không kiểm tra user và không áp đặt path/method. Thường nên kết hợp với một matcher path/method hoặc xử lý trực tiếp trong một lambda có đầy đủ điều kiện chọn route.

### 4.3. Parameter pollution: tránh nhánh quyền yếu

Xét hai cách triển khai nguy hiểm:

```text
Security rule:
  nếu format=csv -> cần report:export
  còn lại -> chỉ cần report:read

Controller:
  nếu format có bất kỳ giá trị nào -> chạy export
```

Nếu security dùng so sánh đúng `csv` mà controller lại export cả `pdf`, request `?format=pdf` có thể rơi vào rule đọc yếu hơn nhưng vẫn thực hiện export. Đây là **policy mismatch** giữa cách matcher và controller hiểu hành động.

Một thiết kế mạnh hơn:

- Nếu **bất kỳ** sự hiện diện nào của parameter `format` có khả năng kích hoạt export, match **mọi request có format** và yêu cầu `report:export`.
- Controller validate `format` đúng một giá trị hợp lệ; từ chối chuỗi rỗng/đa giá trị/định dạng lạ trước khi xuất.
- Nhánh không có format chỉ được đọc danh sách; không có logic ẩn có thể tự export dựa trên header hoặc state chưa kiểm soát.
- Nếu có nhiều kiểu export, cân nhắc route tách riêng `GET /api/reports/export?format=csv` để chính sách rõ ràng và kiểm thử dễ.

### 4.4. Validate dữ liệu không giống authorization

Các bước “format phải là csv/pdf”, “limit phải là số dương”, “sortBy chỉ nhận các cột cho phép” là **validation**. Các bước “người này có `report:export`”, “được xuất dữ liệu của tenant này”, “hạn mức số dòng có hợp lệ” là **authorization/business policy**.

Một request có thể format hợp lệ nhưng thiếu quyền; cũng có thể có quyền export nhưng format không hợp lệ. Cả hai đều không được thực hiện export. Đừng dùng matcher validation để ngầm cấp permission.

## 5. Request attribute: đáng tin khi biết ai tạo, lúc nào và từ đâu

### 5.1. Attribute khác parameter

Servlet API:

```java
request.setAttribute("internal.verifiedTenant", verifiedTenantId);
Object value = request.getAttribute("internal.verifiedTenant");
```

Attribute là dữ liệu gắn với đối tượng `HttpServletRequest` do mã server/container thiết lập. Nó **không tự được tạo** chỉ vì client gửi query `?internal.verifiedTenant=7` hoặc header có tên giống hệt.

Tuy nhiên, việc một giá trị nằm trong attribute không chứng minh nó được **xác minh**. Nếu filter sao chép giá trị user gửi vào attribute, độ tin cậy vẫn là của giá trị đầu vào. Phải ghi rõ trách nhiệm của thành phần tạo attribute, kiểu dữ liệu, chính sách xác minh và vòng đời của attribute.

### 5.2. Ví dụ ngữ cảnh tenant đã xác minh

Một đường xử lý hợp lý:

```text
Bearer token hoặc session
       |
       v
Bộ xác thực tạo Authentication
       |
       v
Bộ kiểm tra membership/tenant của user
       |
       v
Gắn VerifiedTenantContext (object nội bộ) vào request
       |
       v
Matcher có thể dùng context để CHỌN chính sách
       |
       v
AuthorizationManager vẫn kiểm tra authority
       |
       v
Service/repository kiểm tra tenant của resource
```

Nếu dùng attribute để phân loại request, nên dùng một kiểu đối tượng nội bộ cụ thể thay vì chuỗi `"true"` hoặc giá trị do client tự gõ. Nhưng ngay cả việc kiểm tra `instanceof VerifiedTenantContext` cũng không đủ nếu mã khác có quyền tạo object này mà không xác minh dữ liệu. Tin cậy được thiết lập bằng **quy trình tạo và đường đi thực thi**, không chỉ bằng tên class.

### 5.3. Cạm bẫy thứ tự filter

Rất quan trọng: `FilterChainProxy` phải **chọn SecurityFilterChain trước khi các filter bên trong chain đó chạy**. Do vậy:

- Một attribute do **filter nằm bên trong chain** đặt sẽ **không kịp** ảnh hưởng tới `securityMatcher` dùng để chọn chính chain đó.
- Một attribute do filter chạy **trước AuthorizationFilter** trong chain phù hợp đặt có thể sẵn sàng để `requestMatchers` lựa chọn rule (phụ thuộc thứ tự filter thật).
- Attribute do controller hoặc service đặt sau khi authorization đã thực hiện **không kịp** ảnh hưởng quyết định trước controller.
- Attribute do filter bên ngoài `FilterChainProxy` đặt có thể tồn tại lúc chọn chain, nhưng cần đặc biệt cẩn trọng về trust, cấu hình đăng ký filter, thứ tự và mọi đường request.

**Không dùng attribute do một filter cần được chọn mới chạy làm điều kiện để chọn chính filter chain đó.** Đây là lỗi phụ thuộc vòng: matcher luôn thiếu dữ liệu ở thời điểm cần đánh giá.

Trong kiến trúc đơn giản, thay vì chia filter chain theo attribute tenant, nên chọn chain bằng path/method rõ ràng, sau đó đánh giá tenant ở authorization manager/service với principal đã xác thực.

### 5.4. Vòng đời và dispatcher

Một request có thể đi qua `REQUEST`, `FORWARD`, `ERROR` hoặc `ASYNC` dispatch. Attribute có thể tồn tại trong request qua một số giai đoạn nhưng không được giả định rằng nó có cùng nguồn, giá trị hoặc thời điểm tạo khi request chuyển xử lý. Lớp bảo vệ phải xác nhận attribute đã được thiết lập trước quyết định và có chính sách rõ cho những dispatch liên quan.

Đừng lưu một `HttpServletRequest` hoặc attribute của nó trong biến `static`, singleton bean hay cache toàn cục để sử dụng ở request khác. Đồng thời, đừng nhầm request attribute với `SecurityContextHolder` hoặc `Authentication`: đó là các cơ chế khác nhau, có vòng đời và ý nghĩa bảo mật khác nhau.

## 6. Kết hợp path, method, header và parameter mà không mở đường vòng

### 6.1. Matcher phải phân loại chính xác hành động

Một rule “có `format`” đứng một mình sẽ khớp cả API không liên quan như `/api/users?format=csv`. Nếu rule này đứng trước rule khác và dùng quyền yếu, nó có thể khiến request vào một chính sách không định trước.

Nên ghép:

```text
GET
AND path == /api/reports
AND parameter "format" hiện diện
    -> đây là nhánh export
    -> phải có report:export

GET
AND path == /api/reports
AND không có "format"
    -> đây là nhánh list
    -> phải có report:read
```

Khi dùng DSL, rule nhạy cảm nên đứng **trước** rule GET tổng quát, và cuối cùng là denyAll. Trong ứng dụng thực, nếu path được map bằng Spring MVC hoặc servlet prefix khác, chọn matcher đường dẫn tương thích với router, tránh so sánh `getRequestURI()` bằng chuỗi không xử lý context path.

### 6.2. Cấu hình Spring Security 6.x có kiểm soát

Đoạn này là **mã tích hợp** trong ứng dụng Spring Security Servlet 6.x. Nó không phụ thuộc `ParameterRequestMatcher`, do đó minh họa được cách viết custom matcher tương thích cả dự án Spring Security 6.3. Ứng dụng thật vẫn cần cấu hình xác thực và kiểm soát dữ liệu thích hợp.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class ReportHttpSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        // Ví dụ này giả sử DispatcherServlet ánh xạ tại root,
        // servletPath == "/api/reports" cho endpoint tương ứng.
        RequestMatcher exportVariant = request ->
            "GET".equals(request.getMethod())
                && "/api/reports".equals(request.getServletPath())
                && request.getParameterMap().containsKey("format");

        http.authorizeHttpRequests(auth -> auth
            // Nhánh nhạy cảm PHẢI xét trước nhánh đọc tổng quát.
            .requestMatchers(exportVariant)
                .hasAuthority("report:export")
            .requestMatchers(HttpMethod.GET, "/api/reports")
                .hasAuthority("report:read")
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

Cần hiểu kỹ:

1. `GET /api/reports?format=csv` khớp `exportVariant`, nên phải có `report:export`. Trường `format` trống hoặc giá trị không được hỗ trợ vẫn rơi vào nhánh cần quyền export nếu parameter tồn tại; controller sau đó trả lỗi validation.
2. `GET /api/reports` không có parameter `format` đi tới rule đọc `report:read`.
3. `POST /api/reports?format=csv` không khớp exportVariant vì method không phải GET; cũng không khớp GET rule nên bị `denyAll()`.
4. Mọi đường và method chưa đăng ký đều bị từ chối. Với nhiều `SecurityFilterChain`, cần xác minh chain bao phủ request; `anyRequest().denyAll()` chỉ có tác dụng trong chain được chọn.
5. `getServletPath()` phụ thuộc servlet mapping. Nếu ứng dụng chạy với prefix servlet đặc biệt, cần cập nhật matcher hoặc dùng API path matcher được framework hỗ trợ, đồng thời kiểm thử URL thực.
6. Code không cấu hình xác thực, CSRF, CORS, session hay resource server. Không được xem snippet đơn lẻ là cấu hình bảo mật sản xuất hoàn chỉnh.

**Điều kiện bắt buộc để cấu hình này an toàn:** logic điều khiển export phải **khớp chính xác** với tiêu chí “parameter `format` hiện diện”. Nếu export còn được kích hoạt bởi `Accept: text/csv`, `?download=true` hoặc một URL khác, những đường ấy cần chính sách tương đương. Đừng để request thực thi export nhưng lại trượt sang rule đọc yếu hơn.

### 6.3. Ví dụ matcher theo header cho phân loại API version

Đoạn mã minh họa:

```java
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestHeaderRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher apiPathAndMethod = request ->
    "GET".equals(request.getMethod())
        && "/api/reports".equals(request.getServletPath());

RequestMatcher versionTwo =
    new RequestHeaderRequestMatcher("X-Api-Version", "v2");

RequestMatcher versionTwoReports =
    new AndRequestMatcher(apiPathAndMethod, versionTwo);
```

`AndRequestMatcher` yêu cầu **cả hai matcher** cùng khớp. Đây vẫn chỉ là điều kiện chọn nhánh. Nếu muốn hỗ trợ v2 cho user thường, rule v2 vẫn phải yêu cầu permission đọc; nếu v2 mở thao tác nhạy cảm, rule cần permission nhạy cảm tương ứng.

Để tránh rủi ro trùng header, phiên bản giao thức v2 nên được xác định bởi một bộ chuẩn hóa/validation riêng hoặc matcher tùy chỉnh kiểm tra mọi giá trị trước khi handler thực thi. Một cách rõ ràng hơn nữa là tách phiên bản qua path nếu hệ thống cho phép.

### 6.4. AND, OR, NOT và hiệu ứng first-match

Một matcher tổng hợp có thể dùng `AndRequestMatcher`, `OrRequestMatcher` hoặc `NegatedRequestMatcher`. Nhưng:

- **AND** phù hợp để ràng buộc method, path và tín hiệu phân loại cùng lúc.
- **OR** chỉ dùng khi *mỗi nhánh* thực sự có quyền tương đương; nếu một nhánh yếu hơn, nó có thể mở đường vòng.
- **NOT** dễ tạo tập request rộng không ngờ tới; cần có fallback nghiêm ngặt.
- Các matcher trong `authorizeHttpRequests` thường chọn **rule đầu tiên khớp**. Rule tổng quát trước rule export sẽ làm rule export không được dùng.
- Trong nhiều filter chain, `securityMatcher` chọn **chain đầu tiên khớp**, không có chuyện tất cả chain được kiểm tra nối tiếp.

Ví dụ sai:

```text
GET /api/reports (chỉ cần report:read)
GET /api/reports?format=csv (cần report:export)
```

Nếu rule GET tổng quát đứng trước, request export có thể vào rule đọc trước. Sửa bằng cách ưu tiên nhánh nhạy cảm hoặc tách endpoint export.

## 7. Java 17 chạy độc lập: header, parameter và attribute có nguồn kiểm chứng

Chương trình này giúp quan sát việc chọn nhánh dựa trên ba loại tín hiệu. Nó sử dụng **lớp request giả lập**, không dùng Spring để có thể biên dịch độc lập. Chính sách minh họa:

- Nhận dạng nhánh export theo method GET, path `/api/reports` và **sự hiện diện** của parameter `format`.
- Chỉ chấp nhận format là **một** giá trị `csv` hoặc `pdf`.
- Yêu cầu header API version v2 có **đúng một** giá trị; header chỉ chọn giao thức, không cấp permission.
- Cần authority `report:export`.
- Cần ngữ cảnh tenant được một bước xác minh phía server tạo ra, không dùng header `X-Tenant-Id` để cấp quyền.

Lưu file `ControlledRequestMatcherDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ControlledRequestMatcherDemo {
    record VerifiedTenant(String id) {}

    record RequestData(
        String method,
        String path,
        Map<String, List<String>> headers,
        Map<String, List<String>> parameters,
        Map<String, Object> attributes
    ) {}

    // Chỉ mô tả nhánh nào đang được yêu cầu, chưa cấp quyền.
    static boolean isExportIntent(RequestData request) {
        return request != null
            && "GET".equals(request.method())
            && "/api/reports".equals(request.path())
            && request.parameters() != null
            && request.parameters().containsKey("format");
    }

    static boolean hasSingleV2Header(RequestData request) {
        if (request == null || request.headers() == null) {
            return false;
        }
        List<String> versions =
            request.headers().get("X-Api-Version");
        return versions != null && versions.size() == 1
            && "v2".equals(versions.get(0));
    }

    static boolean hasValidFormat(RequestData request) {
        if (request == null || request.parameters() == null) {
            return false;
        }
        List<String> values =
            request.parameters().get("format");
        return values != null && values.size() == 1
            && Set.of("csv", "pdf").contains(values.get(0));
    }

    // Điều kiện này chỉ có ý nghĩa nếu VerifiedTenant thực sự
    // được tạo sau bước server-side verification.
    static boolean sameVerifiedTenant(
            RequestData request, String currentTenant) {
        if (request == null || request.attributes() == null
                || currentTenant == null) {
            return false;
        }
        Object attribute =
            request.attributes().get("internal.verifiedTenant");
        return attribute instanceof VerifiedTenant verified
            && currentTenant.equals(verified.id());
    }

    static boolean canExport(
            RequestData request,
            Set<String> authorities,
            String currentTenant) {
        return isExportIntent(request)
            && hasSingleV2Header(request)
            && hasValidFormat(request)
            && authorities != null
            && authorities.contains("report:export")
            && sameVerifiedTenant(request, currentTenant);
    }

    static RequestData sample() {
        return new RequestData(
            "GET",
            "/api/reports",
            Map.of("X-Api-Version", List.of("v2")),
            Map.of("format", List.of("csv")),
            Map.of("internal.verifiedTenant",
                   new VerifiedTenant("tenant-A"))
        );
    }

    static void show(String name, boolean result) {
        System.out.println(name + ": " + result);
    }

    public static void main(String[] args) {
        RequestData valid = sample();

        show("export intent", isExportIntent(valid));
        show("one v2 header", hasSingleV2Header(valid));
        show("valid format", hasValidFormat(valid));
        show("export allowed",
            canExport(valid, Set.of("report:export"), "tenant-A"));
        show("read permission only",
            canExport(valid, Set.of("report:read"), "tenant-A"));

        RequestData duplicateFormat = new RequestData(
            "GET", "/api/reports",
            Map.of("X-Api-Version", List.of("v2")),
            Map.of("format", List.of("csv", "pdf")),
            valid.attributes()
        );
        show("duplicate still export intent",
            isExportIntent(duplicateFormat));
        show("duplicate format rejected",
            canExport(duplicateFormat,
                Set.of("report:export"), "tenant-A"));

        RequestData duplicateHeader = new RequestData(
            "GET", "/api/reports",
            Map.of("X-Api-Version", List.of("v2", "v1")),
            valid.parameters(),
            valid.attributes()
        );
        show("duplicate header rejected",
            canExport(duplicateHeader,
                Set.of("report:export"), "tenant-A"));

        RequestData forgedRole = new RequestData(
            "GET", "/api/reports",
            Map.of(
                "X-Api-Version", List.of("v2"),
                "X-Role", List.of("ADMIN")
            ),
            valid.parameters(), valid.attributes()
        );
        show("forged role header grants nothing",
            canExport(forgedRole,
                Set.of("report:read"), "tenant-A"));

        RequestData unverifiedAttribute = new RequestData(
            "GET", "/api/reports",
            valid.headers(), valid.parameters(),
            Map.of("internal.verifiedTenant", "tenant-A")
        );
        show("unverified attribute rejected",
            canExport(unverifiedAttribute,
                Set.of("report:export"), "tenant-A"));

        show("other tenant rejected",
            canExport(valid,
                Set.of("report:export"), "tenant-B"));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac ControlledRequestMatcherDemo.java
java ControlledRequestMatcherDemo
```

Kết quả chuẩn:

```text
export intent: true
one v2 header: true
valid format: true
export allowed: true
read permission only: false
duplicate still export intent: true
duplicate format rejected: false
duplicate header rejected: false
forged role header grants nothing: false
unverified attribute rejected: false
other tenant rejected: false
```

**Tại sao kết quả quan trọng?**

1. Header v2 đúng và parameter hợp lệ chỉ mô tả dạng yêu cầu; chưa cho phép export nếu authority không có.
2. Parameter lặp **vẫn là yêu cầu export** (không được rơi vào nhánh đọc), nhưng logic validation từ chối vì cần đúng một giá trị.
3. Header v2 lặp bị từ chối vì quy tắc minh họa đòi đúng một giá trị; điều này loại bỏ sự nhập nhằng giữa các parser.
4. Header `X-Role: ADMIN` không được chuyển thành `GrantedAuthority`. Chủ thể chỉ có `report:read` vẫn không được export.
5. Attribute dạng chuỗi `"tenant-A"` không khớp đối tượng `VerifiedTenant`; quan trọng hơn, trong ứng dụng thật, **phải xác minh nguồn tạo VerifiedTenant trước khi tin nó**.
6. Dù có quyền export, ngữ cảnh tenant không phù hợp vẫn từ chối.

**Giới hạn ví dụ:** hai `record` chỉ mô hình hóa dữ liệu, không xác minh token, proxy hoặc database. Vì code minh họa tự tạo `VerifiedTenant` trong `sample()`, đừng lấy đó làm bằng chứng một object kiểu này có thể được tin khi được tạo ở nơi khác. Trong dự án thật, chỉ thành phần xác thực/chính sách đã được kiểm chứng mới được tạo context hợp lệ, và service vẫn kiểm tra tenant của dữ liệu cần export.

## 8. Kiểm thử matcher trong Spring Security

### 8.1. Test riêng matcher trước khi test phân quyền

Với `MockHttpServletRequest` từ Spring Test, có thể tạo request cụ thể rồi gọi `matches()`. Đoạn sau là **fragment đặt trong JUnit test với dependency Spring Test/Spring Security**:

```java
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.util.matcher.RequestHeaderRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher v2 =
    new RequestHeaderRequestMatcher("X-Api-Version", "v2");

MockHttpServletRequest request =
    new MockHttpServletRequest("GET", "/api/reports");
request.addHeader("X-Api-Version", "v2");

boolean matches = v2.matches(request);
// matches phải true trong cấu hình kiểm thử này.
```

Test tương ứng phải có case thiếu header, sai giá trị, header nhiều giá trị và request không thuộc route nếu sử dụng matcher kết hợp path. Đối với request attribute, test thời điểm filter đặt attribute và sự khác nhau giữa attribute đã xác minh và giá trị copy từ header.

### 8.2. Ma trận an toàn: match và authorize là hai bước khác nhau

| Request | Matcher dự kiến | Quyền/kiểm tra thêm | Kỳ vọng |
| --- | --- | --- | --- |
| `GET /api/reports` | Nhánh list | `report:read` | Được đọc khi có quyền |
| `GET /api/reports?format=csv` | Nhánh export | `report:export`, tenant scope | Chỉ export nếu đủ quyền |
| `GET /api/reports?format=pdf` | Nhánh export | `report:export`, validation | Không fallback vào quyền đọc |
| `GET /api/reports?format=` | Nhánh export | Export quyền + input validation | Từ chối format rỗng |
| `GET /api/reports?format=csv&format=pdf` | Nhánh export | Từ chối dữ liệu đa trị nếu hợp đồng đơn trị | Không đi qua nhánh đọc |
| `GET /api/reports?format=csv` + chỉ `report:read` | Nhánh export | Thiếu export quyền | 403 (giả sử đã xác thực) |
| Header `X-Role: ADMIN` | Không thay đổi authority | Bắt buộc kiểm tra principal | Không nâng quyền |
| Header version v2 bị lặp | Nhánh version theo chính sách validation | Kiểm tra nhập nhằng | Không thực thi hành động dựa trên giá trị khác nhau |
| Request có `internal.verifiedTenant` do filter tin cậy tạo | Nhánh policy nếu đã có trước matcher | Tenant/permission | Theo chính sách |
| Header tự khai tenant rồi được copy vào attribute | Không được coi là đã xác minh | Membership/tenant policy | Từ chối nếu chưa kiểm chứng |
| Parameter JSON body nhưng matcher đọc `getParameter` | Không tự có parameter JSON | Quy tắc khác hoặc validate tại service | Không được bỏ qua quyền |
| Request outside `securityMatcher("/api/**")` | Chain khác/fallback | Mặc định deny | Không lọt ngoài Spring Security |

Khi test một rule, cần làm rõ **điều kiện nào đang bị kiểm tra**. Một request trả 403 do CSRF không chứng minh matcher phân quyền đã chặn. Đối với POST/PATCH/DELETE trong ứng dụng có CSRF, dùng token CSRF hợp lệ khi muốn test nhánh authorization; kiểm thử CSRF nên có ca riêng.

### 8.3. MockMvc kiểm thử nhánh export

Đoạn minh họa trong môi trường test đã có `MockMvc`, controller và fixture tương ứng:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// User có quyền đọc nhưng không có quyền export.
mockMvc.perform(get("/api/reports")
        .param("format", "csv")
        .with(user("reader").authorities(
            new SimpleGrantedAuthority("report:read"))))
    .andExpect(status().isForbidden());
```

Cần import `org.springframework.security.core.authority.SimpleGrantedAuthority` trong test. Đây không phải một chương trình standalone; phải có cấu hình security và endpoint thực tế. Test tương ứng cho người có `report:export` phải xác minh format, tenant, phạm vi dữ liệu, và không chỉ response 200. Nếu endpoint export chạy asynchronous job, cũng phải bảo vệ việc tạo job lẫn quyền tải artifact kết quả.

### 8.4. Test ranh giới bộ lọc/attribute

Một số trường hợp rất quan trọng:

- Attribute được đặt bởi filter **trước AuthorizationFilter**: matcher authorization có nhìn thấy không?
- Attribute được đặt bởi controller: matcher trước controller có nhìn thấy không? Không nên kỳ vọng.
- Attribute được đặt bởi filter **trong chain** nhưng dùng để quyết định `securityMatcher` của chính chain ấy: có thể tạo vòng phụ thuộc, cần thiết kế lại.
- Request đi qua `FORWARD`, `ASYNC` hoặc `ERROR` dispatch: thuộc tính còn hợp lệ không, rule nào được áp dụng?
- Một filter copy từ `X-Tenant-Id`: principal có được xác minh là thành viên tenant đó trước khi attribute được dùng không?
- Có hai filter cùng đặt cùng tên attribute: phần nào sở hữu giá trị cuối, có bị ghi đè không?
- Dữ liệu do reverse proxy thêm và dữ liệu client giả header cùng tên: đâu là giá trị thực sự vào ứng dụng?

Không chấp nhận test chỉ dùng request tự dựng đã được đặt sẵn attribute “tin cậy” mà bỏ qua quy trình tạo attribute trên server.

## 9. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `X-Role: ADMIN` làm điều kiện cấp quyền | Client tự nâng đặc quyền | Chỉ dùng Authentication/authority đã xác minh |
| Match `format=csv` nhưng controller export mọi format | Format khác lọt sang rule đọc | Match mọi export intent hoặc tách endpoint |
| Rule list rộng đặt trước rule export | Rule xuất không được chọn | Rule nhạy cảm trước, default deny |
| Dùng `getParameter` mà quên đa giá trị | Security và controller có thể đọc khác nhau | Dùng `getParameterValues` và chính sách đơn trị |
| Coi `format=` giống vắng mặt | Nhánh không rõ, validation yếu | Phân biệt presence và valid value |
| Tưởng JSON body tự vào `getParameter` | Matcher không khớp hành động thật | Parse/validate tại tầng đúng hoặc tách route |
| Tin attribute chỉ vì có tên `internal.*` | Giá trị thực chất lấy từ header chưa kiểm chứng | Xác minh producer và provenance |
| Dùng attribute đặt trong chain để chọn chính chain | Attribute chưa tồn tại tại lúc chọn | Thay điều kiện chain hoặc đặt trước đúng cách |
| X-Forwarded-For từ client được coi IP nội bộ | Giả mạo nguồn mạng | Proxy trust và lọc header đầu vào |
| Header lặp, mỗi tầng đọc một kiểu | Chọn rule khác hành vi thực | Reject ambiguous/canonicalize một nơi |
| Matcher chỉ xét header, không xét method/path | Match nhầm endpoint khác | Kết hợp các tiêu chí có phạm vi |
| Dùng OR phủ quá rộng | Nhánh yếu mở quyền trái chính sách | Diễn đạt AND/OR rõ, test nhánh |
| Chỉ test `matches()` | Không biết quyền và dữ liệu có được bảo vệ | Thêm HTTP/service/data integration test |
| Xử lý lỗi policy bằng `permitAll` | Sự cố biến thành mở quyền | Fail closed cho thao tác bảo vệ |
| Gọi `RequestHeaderRequestMatcher` như bộ xác thực | Khớp header không chứng minh principal | Tách authentication khỏi request classification |
| Sao chép `ParameterRequestMatcher` vào Security 6.3 | Lỗi API/version | Dùng custom matcher 6.3, 6.4+ mới có class này |

## 10. Checklist thiết kế một matcher có kiểm soát

1. **Xác định hành động** mà matcher muốn phân loại: list, export, preview, version routing hay content negotiation.
2. **Vẽ hợp đồng request**: HTTP method, path, query/form parameters, header, content type, servlet mapping, dispatcher type.
3. **Ghi nguồn dữ liệu** của mỗi tín hiệu: do client đặt, do proxy tin cậy, hay do service/filter phía server xác minh.
4. **Chọn tiêu chí tối thiểu**: path và method thường cần trước; header/parameter chỉ bổ sung nếu action thực sự thay đổi.
5. **Phân biệt presence và validity**: tham số có mặt chưa chắc có giá trị hợp lệ; header có mặt chưa chắc chỉ có một giá trị.
6. **Chặn sự nhập nhằng**: giá trị lặp, value rỗng, encoding bất thường và parser khác nhau phải được xử lý rõ.
7. **Không dùng tín hiệu client làm quyền**: chỉ Authentication/authority đáng tin để đánh giá ai có permission.
8. **Đặt rule nhạy cảm trước rule rộng** và có fallback deny cho request không được khai báo.
9. **Kiểm tra thứ tự filter** nếu dựa trên attribute; đặc biệt phân biệt `securityMatcher` với `requestMatchers`.
10. **Duy trì object policy** tại service/data: tenant, owner, phạm vi dữ liệu và trạng thái.
11. **Viết unit test và integration test** cho cả match và phép cho phép cuối, gồm nhiều header, nhiều parameter, missing/sai value, dispatcher và proxy.
12. **Rà soát theo phiên bản Spring Security** khi nâng cấp, nhất là các API matcher và pattern parser.

## 11. Bài tập thực hành

### Bài 1 — Nhận diện ranh giới tin cậy

Phân loại `X-Role`, `X-Api-Version`, `format=csv`, `internal.verifiedTenant`, `Authorization: Bearer ...` và `X-Forwarded-For` thành “dữ liệu client tự khai”, “dữ liệu hạ tầng nếu được xác minh”, hoặc “dữ liệu ứng dụng đã kiểm chứng”. Giải thích vì sao `Authorization` header cũng chỉ là credential cần **được xác thực**, không phải bằng chứng ngay lúc đọc raw header.

### Bài 2 — Sửa rule export bị bypass

Giả sử controller export nếu parameter `format` tồn tại, còn security chỉ yêu cầu `report:export` khi `format=csv`. Thiết kế lại matcher để cả csv, pdf, chuỗi rỗng, giá trị lặp đều không thể lọt vào nhánh chỉ cần `report:read`. Viết ma trận request và kết quả trước/sau.

### Bài 3 — Chạy Java 17

Chạy `ControlledRequestMatcherDemo.java`. Thêm trường hợp thiếu header v2, parameter là chuỗi rỗng và request POST có format. Dự đoán stdout rồi xác minh. Giải thích tại sao một header giả mạo role không thay đổi `Set<String> authorities`.

### Bài 4 — Attribute theo đúng thứ tự

Thiết kế một filter xác minh tenant theo principal và tạo một object `VerifiedTenantContext`. Giải thích nó phải chạy ở đâu nếu matcher authorization cần attribute, và vì sao không thể dựa vào filter trong chính chain để chọn chain. Test bằng `MockMvc` thay vì chỉ gán attribute giả ngay trong test.

### Bài 5 — Kiểm soát header lặp

Tạo request hai header `X-Api-Version`. Dùng `getHeaders` để phát hiện nhiều giá trị và từ chối khi chỉ chấp nhận một. Test với proxy/gateway thật nếu hệ thống có nhiều lớp vì chúng có thể gộp header theo cách khác.

### Bài 6 — Review bảo mật đầu-cuối

Thêm quyền `report:export` vào API. Kiểm tra cả branch HTTP, tenant scope của truy vấn, xuất file bất đồng bộ, URL tải file thành phẩm, cache và audit. Chứng minh người chỉ có `report:read` không thể tải nội dung export thông qua bất kỳ đường nào.

## 12. Tự kiểm tra cuối bài

1. **RequestMatcher trả về true nghĩa là user đã có quyền chưa?** Chưa. Nó chỉ khẳng định request phù hợp điều kiện phân loại.
2. **Header do client gửi có thể dùng chọn API version không?** Có, nhưng không làm bằng chứng danh tính/role và phải xử lý giá trị lặp/không hợp lệ.
3. **`RequestHeaderRequestMatcher("X-Api-Version")` kiểm tra gì?** Header có mặt, không bắt buộc có giá trị v2.
4. **`ParameterRequestMatcher` có sẵn trong mọi Spring Security 6.x không?** Không; class này có từ 6.4.
5. **Vì sao `getParameter("format")` chưa đủ để phát hiện nhập nhằng?** Vì parameter có thể có nhiều giá trị; dùng `getParameterValues` khi cần validate dạng đơn trị.
6. **JSON field `format` có tự động thành Servlet parameter không?** Không.
7. **Vì sao request attribute có thể vẫn không đáng tin?** Nó có thể được server copy từ dữ liệu client mà chưa xác minh; phải biết producer và nguồn dữ liệu.
8. **Filter trong chain có thể đặt attribute để chọn chính chain đó không?** Không thể dựa vào nó; chọn chain diễn ra trước khi các filter trong chain thực thi.
9. **Nếu controller export cả csv và pdf nhưng matcher chỉ bảo vệ csv, nguy hiểm gì?** Pdf có thể rơi vào rule quyền đọc yếu hơn; chính sách phải bảo vệ mọi intent export.
10. **Vì sao cần match method + path + tín hiệu phụ?** Để không áp rule của endpoint khác do cùng header/parameter.
11. **Có `report:export` thì được xuất dữ liệu tenant khác không?** Không; service/repository còn phải kiểm tra phạm vi đối tượng.
12. **Một test 403 có chứng minh matcher đúng không?** Không; 403 có thể do CSRF, rule khác hoặc thiếu authentication, cần test từng lớp với fixture phù hợp.

**Ghi nhớ:** header, parameter và request attribute giúp Spring Security **nhận biết loại request** để chọn chính sách đúng. Chúng chỉ an toàn khi biết rõ **nguồn dữ liệu, thời điểm tồn tại và cách xử lý giá trị nhập nhằng**. Không bao giờ biến header/query tự khai thành quyền; kết hợp matcher theo path/method, kiểm tra authority đã xác thực, và giữ quyền theo tenant/tài nguyên ở tầng nghiệp vụ.

### Tài liệu tham khảo

- [Spring Security – Authorize HttpServletRequests / Custom Matcher](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – RequestMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/util/matcher/RequestMatcher.html)
- [Spring Security – RequestHeaderRequestMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/util/matcher/RequestHeaderRequestMatcher.html)
- [Spring Security – ParameterRequestMatcher API (từ 6.4)](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/util/matcher/ParameterRequestMatcher.html)
- [Spring Security – Servlet Architecture / FilterChainProxy](https://docs.spring.io/spring-security/reference/servlet/architecture.html)