# RegexRequestMatcher và trường hợp cần biểu thức chính quy

> **Module:** Spring Security – authorization  
> **Nhóm:** RequestMatcher  
> **Mục tiêu:** Hiểu khi nào nên dùng `RegexRequestMatcher`, nó so khớp phần nào của HTTP request, cách kết hợp HTTP method và phân quyền, cũng như cách tránh rule quá rộng, sai escaping, sai thứ tự và lỗ hổng bao phủ.

## 1. Bài toán thực tế

Xét API đọc đơn hàng. Chính sách dự kiến: HTTP GET với đường dẫn chứa **một ID gồm 1–8 chữ số ASCII** phải có permission `order:read`; các hành động khác không được dùng lẫn quyền đọc:

~~~http
GET /api/orders/42
GET /api/orders/1007?expand=items
GET /api/orders/ABC
GET /api/orders/42/approve
POST /api/orders/42
~~~

Matcher `/api/orders/**` đơn giản nhưng rộng: nó có thể nhận cả URL chứa chữ, đoạn path bổ sung và action đặc quyền. Nếu chính sách HTTP **thật sự cần phân biệt cấu trúc path**, regular expression là một lựa chọn.

Tuy nhiên **khớp regex không phải được phép truy cập**. Regex chỉ trả lời “request có đúng hình dạng/HTTP method mà rule này nhắm tới không?”. Sau đó Spring Security phải kiểm tra `Authentication` và authority, còn service phải xác minh quyền trên **đơn hàng cụ thể** (owner/tenant/trạng thái). Một URL có ID hợp lệ vẫn có thể là yêu cầu trái phép.

## 2. RequestMatcher nằm ở đâu?

`RequestMatcher` là giao diện Servlet của Spring Security để kiểm tra một `HttpServletRequest`. `RegexRequestMatcher` là implementation sử dụng `java.util.regex.Pattern`.

~~~text
HTTP request
    |
    v
FilterChainProxy
    |
    +--> securityMatcher: chọn SecurityFilterChain đầu tiên khớp
    |
    v
Các filter trong chain đã chọn
    |
    v
AuthorizationFilter
    |
    +--> requestMatchers: chọn rule đầu tiên khớp
    |
    v
AuthorizationManager: hasAuthority / hasRole / authenticated / denyAll
    |
    v
Controller / Service / policy theo tài nguyên
~~~

**Hai vị trí sử dụng matcher không được nhầm lẫn:**

| Cấp | API | Ý nghĩa khi regex không khớp |
|---|---|---|
| Cấp chain | `http.securityMatcher(regexMatcher(...))` | Chain này không được chọn; chỉ có chain khác phù hợp mới tiếp tục bảo vệ request |
| Cấp rule | `authorizeHttpRequests(...).requestMatchers(regexMatcher(...))` | Spring Security thử rule tiếp theo **trong chain đã chọn** |

Với `authorizeHttpRequests`, **rule đầu tiên khớp sẽ quyết định**; các rule sau không được cộng dồn. Với nhiều `SecurityFilterChain`, chain được ưu tiên và khớp đầu tiên là chain duy nhất chạy. Vì thế regex rộng đặt trước rule nhạy cảm có thể làm rule nhạy cảm không bao giờ được dùng.

## 3. RegexRequestMatcher thực sự so khớp chuỗi nào?

Theo JavaDoc của Spring Security 6.5 và 7.x, `RegexRequestMatcher` đánh giá URL được ghép từ:

~~~text
servletPath + pathInfo + queryString
~~~

Nếu có query string, dấu `?` được thêm vào trước query. Ví dụ request có:

~~~text
contextPath = "/shop"
servletPath = "/api/orders"
pathInfo = "/42"
queryString = "expand=items"

Đầu vào regex:
  /api/orders/42?expand=items
~~~

**Hệ quả quan trọng:**

- `contextPath` không phải một phần của chuỗi đem so khớp. Đừng tự thêm `/shop` vào regex chỉ vì deployment dùng context path đó.
- Query string **có thể ảnh hưởng** kết quả regex, khác với nhiều path matcher thông thường chỉ xét đường dẫn.
- Method GET/POST là một điều kiện riêng của matcher nếu cấu hình, không được suy ra từ regex path.
- `RegexRequestMatcher` **phân biệt chữ hoa/thường theo mặc định**; `/API/orders/42` không tự tương đương `/api/orders/42`.
- `HttpFirewall`, servlet container, reverse proxy và handler mapping có thể tác động đến URL trước khi matcher nhìn thấy. Không suy đoán behavior của slash kép, semicolon, encoded slash hoặc URL rewrite nếu chưa test môi trường thật.

### Ví dụ quan trọng: query string làm rule trượt

Mẫu:

~~~regex
^/api/orders/[0-9]+$
~~~

Có thể nhận `/api/orders/42` nhưng sẽ không nhận `/api/orders/42?expand=items` theo phép ghép URL nói trên.

Nếu query tùy chọn là một phần nhu cầu:

~~~regex
^/api/orders/[0-9]+(?:\?.*)?$
~~~

Nhóm `(?:\?.*)?` cho phép dấu `?` thật và phần query theo sau. Trong **chuỗi Java**, phải escape backslash:

~~~java
String pattern = "^/api/orders/[0-9]+(?:\\?.*)?$";
~~~

Lưu ý: cho phép cú pháp query string không đồng nghĩa cấp quyền cho mọi `expand` hoặc `mode`. Nếu tham số làm lộ dữ liệu bổ sung, chính sách nghiệp vụ vẫn phải kiểm tra.

## 4. API tạo RegexRequestMatcher

Factory method có từ Spring Security 5.8 và được tài liệu chính thức minh họa trong các dòng 6.x/7.x:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.util.matcher.RegexRequestMatcher;

// Chỉ xem regex, không giới hạn method.
RegexRequestMatcher allMethods =
        RegexRequestMatcher.regexMatcher(
                "^/api/orders/[0-9]+(?:\\?.*)?$");

// Giới hạn cả GET và regex.
RegexRequestMatcher onlyGet =
        RegexRequestMatcher.regexMatcher(
                HttpMethod.GET,
                "^/api/orders/[0-9]+(?:\\?.*)?$");

// Dùng constructor nhận method ở dạng chuỗi.
RegexRequestMatcher onlyPost =
        new RegexRequestMatcher(
                "^/api/orders/[0-9]+(?:\\?.*)?$",
                "POST");

// Chỉ khi cần matching không phân biệt chữ hoa/thường.
RegexRequestMatcher caseInsensitive =
        new RegexRequestMatcher(
                "^/api/orders/[0-9]+(?:\\?.*)?$",
                "GET",
                true);
~~~

Đây là **snippet thuộc một dự án Spring Security Servlet**, không phải chương trình JDK thuần. Luôn kiểm tra overload theo dependency hiện hành khi nâng version.

Cú pháp static import thông dụng:

~~~java
import static org.springframework.security.web.util.matcher.RegexRequestMatcher.regexMatcher;
~~~

Sau đó có thể gọi `regexMatcher(HttpMethod.GET, pattern)`.

**Không dùng case-insensitive tùy tiện.** Nó làm matcher chấp nhận thêm cách viết URL, trong khi routing/controller/gateway có thể không có cùng quy ước. Test chính xác case sensitivity ở cả security và controller.

## 5. Khi nào regex là lựa chọn hợp lý?

Regex có giá trị khi **định dạng segment là một phần cần thiết của rule HTTP** và path matcher thông thường không diễn đạt đủ rõ.

### Tình huống A: một ID chỉ gồm chữ số, giới hạn độ dài

~~~regex
^/api/orders/[0-9]{1,8}(?:\?.*)?$
~~~

Cho một segment 1–8 chữ số. Không nhận `ABC`, ID dài chín chữ số hay `/42/approve`. Bản thân controller vẫn nên parse và validate ID; regex là lớp xác định nhóm request.

### Tình huống B: phiên bản báo cáo với kỳ rõ ràng

~~~regex
^/api/reports/20[0-9]{2}/Q[1-4](?:\?.*)?$
~~~

Cấu trúc này nhận một năm `20xx` và quý `Q1` đến `Q4`. Độ chính xác về định dạng không có nghĩa người gọi được phép xem mọi báo cáo.

### Tình huống C: slug có bảng ký tự giới hạn

~~~regex
^/api/catalog/[A-Za-z0-9_-]{3,24}(?:\?.*)?$
~~~

Giới hạn slug 3–24 ký tự Latin ASCII, chữ số, gạch dưới/gạch nối. Nếu ứng dụng hỗ trợ tiếng Việt/Unicode trong path, regex này có thể quá hẹp. Không áp quy tắc ASCII nếu nghiệp vụ không yêu cầu.

### Tình huống D: một nhóm hữu hạn dùng chung policy

~~~regex
^/api/(?:invoices|receipts)/[0-9]+(?:\?.*)?$
~~~

Chỉ gộp khi hai loại tài nguyên **thật sự cùng permission và điều kiện**. Nếu `invoice:read` khác `receipt:read`, hai rule tách biệt dễ audit hơn một regex có nhiều nhánh.

### Những tình huống không nên dùng regex

| Mục tiêu | Thường chọn |
|---|---|
| Mọi path dưới `/api/**` cần đăng nhập | Path matcher + `authenticated()` |
| `/admin/**` cần role ADMIN | Path matcher + `hasRole("ADMIN")` |
| `GET /orders/{id}` cần permission đọc | Path matcher theo method/placeholder và service policy |
| ID phải là số Java `long` | MVC binding/validation |
| JSON body phải có trường hợp lệ | DTO + Bean Validation |
| Query `?mode=export` yêu cầu permission khác | Custom RequestMatcher/AuthorizationManager hoặc service policy |
| Chủ sở hữu đơn hàng phải là người gọi | Object-level authorization, owner/tenant-scoped repository |
| Token JWT có scope nào | Authentication converter + authorization rule |
| Tất cả URL chưa biết phải bị chặn | `anyRequest().denyAll()` và filter-chain fallback |

**Quy tắc thực hành:** Nếu `requestMatchers(HttpMethod.GET, "/api/orders/{id}")` đã thể hiện đủ policy, ưu tiên nó và để controller xử lý kiểu ID. Chọn regex khi nó giải quyết yêu cầu thật, không chỉ để cấu hình trông “chặt chẽ”.

## 6. Đọc đúng các metacharacter

| Ký hiệu regex | Ý nghĩa | Ví dụ |
|---|---|---|
| `^` | Đầu chuỗi | `^/api/` |
| `$` | Cuối chuỗi | `[0-9]+$` |
| `[0-9]` | Một chữ số ASCII | `[0-9]{1,8}` |
| `[A-Za-z]` | Chữ Latin ASCII | `[A-Za-z]+` |
| `{m,n}` | Số lần xuất hiện từ m đến n | `[0-9]{1,8}` |
| `+` | Một hoặc nhiều | `[0-9]+` |
| `*` | Không hoặc nhiều | `[A-Z]*` |
| `?` | Tùy chọn một thành phần | `(?:...)?` |
| `(?:...)` | Nhóm không capture | `(?:pdf|csv)` |
| `\?` | Dấu hỏi thật | `(?:\?.*)?` |
| `\.` | Dấu chấm thật | `\.csv` |
| `.` | Ký tự bất kỳ theo regex (một số newline có ngoại lệ) | `.*` |
| `|` | Hoặc | `(?:GET|POST)` |

Các ký hiệu `\?` và `\.` cần thành `\\?`, `\\.` khi viết bằng Java string literal.

### 6.1. Dấu chấm là wildcard, không phải dấu chấm thật

Mẫu không chuẩn:

~~~regex
^/reports/[0-9]+.csv$
~~~

Dấu `.` có thể nhận một ký tự khác dấu chấm; muốn đuôi `.csv` thật phải dùng:

~~~regex
^/reports/[0-9]+\.csv$
~~~

Java string tương ứng:

~~~java
"^/reports/[0-9]+\\.csv$"
~~~

### 6.2. Cẩn thận với `.*` và `.+`

Mẫu:

~~~regex
^/api/orders/.+$
~~~

có thể nhận `/api/orders/42/approve` vì dấu slash nằm trong miền ký tự của `.+`. Nếu rule áp dụng `order:read`, đường duyệt có thể bị đánh giá như đường đọc.

Khi chỉ muốn **một segment**, `[^/]+` hẹp hơn. Nếu định dạng ID xác định, `[0-9]{1,8}` còn minh bạch hơn. Không dùng `.*` để “sửa” lỗi matcher khi chưa hiểu nguyên nhân.

### 6.3. Anchors không thay thế kiểm tra

Dùng `^...$` làm rõ yêu cầu toàn chuỗi; với Java `Pattern.matcher(input).matches()`, bản thân `matches()` cũng yêu cầu khớp toàn input. Anchors có ích cho khả năng đọc và khi tái sử dụng pattern trong code khác, nhưng một regex có anchors vẫn có thể quá rộng hoặc cấp sai permission.

## 7. Cấu hình Spring Security Servlet thực tế

Giả sử ứng dụng dùng Spring Boot 3.x, Spring Security 6.x, HTTP Basic và authorities đã được cấp từ nguồn tin cậy:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RegexRequestMatcher;

@Configuration
public class OrderSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        RegexRequestMatcher numericOrderGet =
                RegexRequestMatcher.regexMatcher(
                        HttpMethod.GET,
                        "^/api/orders/[0-9]{1,8}(?:\\?.*)?$");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(numericOrderGet)
                    .hasAuthority("order:read")
                .requestMatchers("/api/orders/**")
                    .denyAll()
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là **class cấu hình của dự án**, không biên dịch độc lập chỉ bằng JDK 17. Ứng dụng phải cung cấp controller, authentication provider, dependencies và các rule công khai cần thiết. Một API dùng JWT nên có cấu hình Bearer Resource Server và kiểm tra scope/permission đúng kiến trúc, không sao chép cấu hình HTTP Basic một cách máy móc.

**Đọc ba rule:**

1. `GET /api/orders/42`: regex + method khớp → yêu cầu authority `order:read`.
2. `GET /api/orders/42?expand=items`: regex cho phép query → vẫn cần `order:read`.
3. `GET /api/orders/ABC`, `POST /api/orders/42`, `GET /api/orders/42/approve`: không khớp rule đặc thù → rule `/api/orders/**` từ chối.
4. URL còn lại → fallback `anyRequest().denyAll()` **trong chain này**.
5. Người dùng có `order:read` vẫn phải qua service policy kiểm tra tenant/owner của đơn hàng.

### Sai thứ tự: rule rộng che rule regex

~~~java
// CẤU HÌNH SAI cho policy đọc đơn hàng:
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/orders/**").authenticated()
        .requestMatchers(numericOrderGet).hasAuthority("order:read")
        .anyRequest().denyAll()
);
~~~

`GET /api/orders/42` đã khớp rule yêu cầu đăng nhập, nên quy tắc `order:read` phía sau **không chạy**. Đây là lỗi phân quyền do “first match wins”, không phải lỗi regex engine. Đặt rule cụ thể trước, nhưng vẫn phải đảm bảo rule sau không vô tình mở thêm endpoint nhạy cảm.

### Không cần regex nếu chỉ quan tâm ID là placeholder

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
            .hasAuthority("order:read")
        .anyRequest().denyAll()
);
~~~

Đây thường là cách ngắn, dễ bảo trì hơn khi route thông thường và controller có kiểu ID. Path matching có semantics riêng, không đồng nghĩa regex ở mọi biên (query, URL encoding, trailing slash).

## 8. Query string: phần dễ sai nhất

Vì `RegexRequestMatcher` nhìn thấy query string, hãy chọn một chủ đích rõ ràng.

**Chủ đích A – Query không quyết định policy:** dùng regex có phần query tùy chọn như `(?:\\?.*)?` trong Java string, nhưng controller/service vẫn validate từng parameter. Ví dụ `?expand=items` có thể mở dữ liệu nhạy cảm; yêu cầu thêm permission nếu nghiệp vụ cần.

**Chủ đích B – Muốn matcher dựa trên path thuần:** dùng `requestMatchers` với path pattern thông thường, không nhúng logic query vào regex.

**Chủ đích C – Query quyết định action:** nếu `?mode=export` cần quyền xuất dữ liệu nhưng `?mode=view` chỉ cần quyền đọc, một custom `RequestMatcher` hoặc service policy đánh giá parameter **đã parse** thường rõ ràng hơn.

Ví dụ custom matcher ngắn trong ứng dụng Servlet:

~~~java
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher exportMode = request ->
        "GET".equals(request.getMethod())
        && "/api/orders".equals(request.getServletPath())
        && "export".equals(request.getParameter("mode"));
~~~

Đây không phải chương trình chạy độc lập. Request có thể có query key lặp, encoding khác, giá trị rỗng hoặc default; cần định nghĩa chính sách và kiểm thử các biến thể. Không dùng parameter `tenantId` do client tự nhập làm bằng chứng được phép truy cập tenant đó.

**Điểm bảo mật:** Cho phép `?mode=export` trong regex URL không chứng minh user có `order:export`; kiểm tra action/authority thực sự tại authorization policy.

## 9. Regex ở cấp securityMatcher và rủi ro request nằm ngoài chain

Nếu đặt regex ở `http.securityMatcher`:

~~~java
http.securityMatcher(
        RegexRequestMatcher.regexMatcher("^/api/v[0-9]+/.*$"))
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated());
~~~

thì **chỉ** request khớp regex được chọn vào chain này. Nếu `GET /admin/users` hoặc `GET /debug` không khớp chain nào khác, chúng có thể **không được bảo vệ bởi Spring Security filter chain**.

`anyRequest().authenticated()` hoặc `anyRequest().denyAll()` **không bảo vệ những URL ở ngoài matcher cấp chain**.

Với nhiều chain, thường có một fallback đặt cuối:

~~~java
@Bean
@Order(99)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().denyAll());
    return http.build();
}
~~~

Đây là snippet có nghĩa trong một Spring configuration class, cần các imports và những chain có `@Order` phù hợp. Fallback không có `securityMatcher` nên mặc định có phạm vi toàn request chưa được chain trước nhận. Nếu fallback đặt lên trước chain chuyên biệt, nó có thể che chain đó. Không có fallback là một lỗi coverage tiềm tàng dù regex bên trong chain riêng được viết hoàn hảo.

Nếu ứng dụng không cần filter/authentication mechanism khác nhau, một chain với nhiều `requestMatchers` thường dễ audit hơn nhiều chain có các regex giao nhau.

## 10. Regex không thay thế owner/tenant permission

User có `order:read` và URL `/api/orders/42` đúng regex **không đủ** để được xem đơn hàng 42. Cần còn xác minh:

- Đơn hàng có tồn tại và thuộc tenant của user không?
- User có phải owner hoặc người được chia sẻ không?
- Role/permission có áp dụng cho loại đơn hàng và trạng thái đó không?
- Query mở rộng có tiết lộ trường dữ liệu ngoài quyền không?
- Policy có cần cập nhật nếu quyền user vừa bị thu hồi không?

Ví dụ service method:

~~~java
@PreAuthorize(
    "hasAuthority('order:read') " +
    "and @orderPolicy.canRead(authentication, #id)"
)
public OrderDto getOrder(long id) {
    return orderQueryService.find(id);
}
~~~

Đây là method minh họa phụ thuộc `@EnableMethodSecurity`, bean `orderPolicy` và service/repository thực tế. Tham số `#id` phải được nhận diện tên đúng. Policy kiểm tra tenant/owner từ nguồn server, không dùng ID đẹp hay token scope làm phép suy luận quyền trên bản ghi.

## 11. Encoding, normalization và firewall

Các URL có thể được biểu diễn theo nhiều cách:

~~~text
/api/orders/42
/api/orders/42/
/api//orders/42
/api/orders/%34%32
/api/orders/42;param=x
/API/orders/42
/shop/api/orders/42
/api/orders/42?expand=items
~~~

Không nên tự kết luận chúng tương đương hoặc khác nhau tuyệt đối trên mọi môi trường. Reverse proxy, servlet container, mapping MVC và Spring Security `HttpFirewall` có thể chuẩn hóa hoặc chặn một số dạng.

Đặc biệt:

- `contextPath` như `/shop` không nằm trong chuỗi ghép của `RegexRequestMatcher` theo JavaDoc.
- Nếu proxy rewrite path, kiểm tra URL mà Servlet thực nhận, không chỉ URL ngoài trình duyệt.
- `StrictHttpFirewall` có thể từ chối một số dạng URL bất thường; đừng nới cấu hình firewall chỉ để pattern bắt được encoded slash/semicolon.
- Security và MVC phải cùng hiểu URL; nếu mỗi tầng diễn giải khác, có nguy cơ bypass rule.
- Không “sửa nhanh” bằng regex `.*orders.*`: nó có thể mở rộng phạm vi quyền vượt ý định.

Dùng integration test qua proxy/test servlet mapping khi hệ thống có URL rewrite đặc biệt, và kiểm tra cả kết quả của controller lẫn security rule.

## 12. ReDoS và khả năng bảo trì regex

Java `Pattern` có thể dùng backtracking. Những mẫu lặp chồng lấn/nhánh mơ hồ có thể gây chi phí CPU rất lớn trên chuỗi gần khớp nhưng thất bại.

Mẫu kinh điển đáng tránh nếu không có lý do:

~~~regex
^(a+)+$
~~~

Tại lớp authorization, matcher có thể chạy thường xuyên và trên request do client kiểm soát. Vì vậy:

1. Không ghép regex từ tham số do client tự gửi.
2. Dùng mẫu cố định, code-reviewed, dễ đọc.
3. Chọn lớp ký tự hẹp và lượng lặp có giới hạn, như `[0-9]{1,8}`.
4. Tránh `.*` và nhóm lặp lồng nhau khi không thực sự cần.
5. Đặt giới hạn URL/request size ở proxy/servlet.
6. Benchmark pattern phức tạp với input biên dài và thất bại.
7. Ưu tiên path matcher khi chỉ cần prefix/placeholder.

Regex phức tạp không tự làm hệ thống “an toàn hơn”. Tính đúng đắn của **policy** và test negative quan trọng hơn số lượng ký hiệu trong pattern.

## 13. Kiểm thử RegexRequestMatcher trực tiếp

Ví dụ test trong dự án có JUnit 5, Spring Test và Spring Security:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.util.matcher.RegexRequestMatcher;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RegexMatcherTest {

    private final RegexRequestMatcher matcher =
            RegexRequestMatcher.regexMatcher(
                    HttpMethod.GET,
                    "^/api/orders/[0-9]{1,8}(?:\\?.*)?$");

    static MockHttpServletRequest req(
            String method, String servletPath, String queryString) {
        MockHttpServletRequest request =
                new MockHttpServletRequest(method, servletPath);
        request.setServletPath(servletPath);
        if (queryString != null) {
            request.setQueryString(queryString);
        }
        return request;
    }

    @Test
    void acceptsNumericId() {
        assertTrue(matcher.matches(req("GET", "/api/orders/42", null)));
    }

    @Test
    void acceptsQueryStringWhenConfigured() {
        assertTrue(matcher.matches(
                req("GET", "/api/orders/42", "expand=items")));
    }

    @Test
    void rejectsAlphabeticId() {
        assertFalse(matcher.matches(
                req("GET", "/api/orders/A42", null)));
    }

    @Test
    void rejectsWrongMethod() {
        assertFalse(matcher.matches(
                req("POST", "/api/orders/42", null)));
    }

    @Test
    void rejectsExtraPathSegment() {
        assertFalse(matcher.matches(
                req("GET", "/api/orders/42/approve", null)));
    }
}
~~~

Đây là **test thuộc dự án Spring**, không phải ví dụ JDK độc lập. Cần chú ý `MockHttpServletRequest.setServletPath`: chỉ thiết lập request URI chưa chắc đã tạo ra các trường Servlet mà matcher dùng theo cách bạn dự đoán. Nên test query string và method tường minh.

### Bộ test âm tính nên có

| Tình huống | Regex GET ID số khớp? | Kỳ vọng của policy |
|---|---|---|
| `GET /api/orders/42` | Có | Kiểm tra `order:read` |
| `GET /api/orders/42?expand=items` | Có với mẫu có query tùy chọn | Kiểm tra quyền đọc và permission mở rộng nếu có |
| `GET /api/orders/A42` | Không | Rule sau từ chối nếu không hợp lệ |
| `GET /api/orders/123456789` | Không | Không được đi qua rule rộng |
| `POST /api/orders/42` | Không do method | Cần rule POST riêng hoặc deny |
| `GET /api/orders/42/approve` | Không | Không dùng quyền đọc để duyệt |
| `GET /API/orders/42` | Không trong cấu hình case-sensitive | Đối chiếu routing thật |
| `GET /api/orders/42/` | Không với mẫu trên | Kiểm tra trailing slash và MVC |
| `GET /api/orders/00042` | Có | Zero đầu có hợp lệ không là chuyện validation |
| User thiếu `order:read`, URL hợp lệ | Có | Authorization từ chối |
| User có `order:read` nhưng sai tenant | Có | Service/object policy từ chối |
| URL ngoài mọi `SecurityFilterChain` | Không có chain | Thiết kế fallback để bảo vệ |

Test matcher chỉ trả true/false **chưa chứng minh** HTTP status. Test bằng `MockMvc` với controller có tồn tại để chứng minh user thiếu permission nhận denial và user đúng permission đi tiếp theo policy. Một URL trả 404 vì không có controller **không chứng minh** đã có security filter bảo vệ nó.

## 14. Ví dụ Java 17 độc lập: mô phỏng method, regex và fallback

Chương trình Java thuần dưới đây mô phỏng ý tưởng của `RegexRequestMatcher` mà không cần Spring Security. Nó ghép `servletPath + pathInfo + ?queryString`, kiểm tra HTTP method, chọn rule đầu tiên khớp và cho thấy fallback từ chối. **Đây là mô phỏng**, không kiểm tra thật `Authentication`, `HttpFirewall`, CSRF, Servlet hoặc object policy.

Lưu tệp `RegexRoutingDemo.java`:

~~~java
import java.util.List;
import java.util.regex.Pattern;

public class RegexRoutingDemo {
    record Request(String method, String servletPath, String pathInfo,
                   String queryString) {
        String urlForMatch() {
            return servletPath
                    + (pathInfo == null ? "" : pathInfo)
                    + (queryString == null ? "" : "?" + queryString);
        }
    }

    record Rule(String name, String method, Pattern pattern, String policy) {
        boolean matches(Request request) {
            return (method == null || method.equals(request.method()))
                    && pattern.matcher(request.urlForMatch()).matches();
        }
    }

    static String choose(Request request, List<Rule> rules) {
        for (Rule rule : rules) {
            if (rule.matches(request)) {
                return rule.name() + " -> " + rule.policy();
            }
        }
        return "NO_RULE";
    }

    static void show(String label, Request request, List<Rule> rules) {
        System.out.println(label + ": " + choose(request, rules));
    }

    public static void main(String[] args) {
        List<Rule> rules = List.of(
                new Rule("numeric GET", "GET",
                        Pattern.compile("^/api/orders/[0-9]{1,8}(?:\\?.*)?$"),
                        "REQUIRE order:read"),
                new Rule("orders fallback", null,
                        Pattern.compile("^/api/orders(?:/.*)?(?:\\?.*)?$"),
                        "DENY"),
                new Rule("global fallback", null,
                        Pattern.compile("^.*$"), "DENY")
        );

        show("numeric", new Request("GET", "/api/orders/42", null, null), rules);
        show("with query", new Request("GET", "/api/orders/42", null,
                "expand=items"), rules);
        show("split servlet path", new Request("GET", "/api", "/orders/42",
                null), rules);
        show("letters", new Request("GET", "/api/orders/A42", null, null), rules);
        show("wrong method", new Request("POST", "/api/orders/42", null, null), rules);
        show("extra path", new Request("GET", "/api/orders/42/approve",
                null, null), rules);
        show("too many digits", new Request("GET", "/api/orders/123456789",
                null, null), rules);
        show("uppercase path", new Request("GET", "/API/orders/42",
                null, null), rules);
        show("outside orders", new Request("GET", "/internal/health",
                null, null), rules);
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 17 RegexRoutingDemo.java
java RegexRoutingDemo
~~~

Output đúng:

~~~text
numeric: numeric GET -> REQUIRE order:read
with query: numeric GET -> REQUIRE order:read
split servlet path: numeric GET -> REQUIRE order:read
letters: orders fallback -> DENY
wrong method: orders fallback -> DENY
extra path: orders fallback -> DENY
too many digits: orders fallback -> DENY
uppercase path: global fallback -> DENY
outside orders: global fallback -> DENY
~~~

**Giải thích:** Ba dòng đầu khớp regex GET ID số; những trường hợp chứa chữ, sai method, thừa path hoặc ID quá dài bị fallback từ chối. `/API/...` khác chữ hoa nên không khớp regex mặc định. `/internal/health` rơi vào fallback toàn cục.

Chữ `REQUIRE order:read` ở đây **chỉ là tên policy**, không có nghĩa user thực sự được phép. Trong Spring Security thật, `AuthorizationManager` còn kiểm tra authority từ `Authentication` và service kiểm tra tài nguyên.

## 15. Lỗi phổ biến và cách sửa

| Lỗi | Hệ quả | Sửa |
|---|---|---|
| `^/api/orders/.*$` được gắn với `order:read` | Có thể bắt cả action duyệt/xóa | Regex hẹp và method riêng |
| Không tính query string | Request có `?x=1` trượt rule | Pattern tùy chọn query hoặc path matcher |
| Dùng `.` thay `\.` | Khớp ký tự ngoài ý định | Escape đúng trong regex và Java |
| Quên `\?` trong regex URL | Dấu hỏi bị hiểu là quantifier | Dùng `\\?` trong Java string |
| Không ràng buộc GET/POST | POST có thể bị xử lý bởi rule đọc | Factory với `HttpMethod` |
| Đặt rule rộng trước regex | Rule regex không được xét | Rule hẹp có policy đúng lên trước |
| Dùng regex ở `securityMatcher` nhưng không có fallback | Có request không được security chain bảo vệ | Catch-all chain ở cuối |
| Cho rằng regex ID chứng minh ownership | IDOR/BOLA | Policy tenant/owner ở service |
| Đặt `.*`, lượng lặp chồng nhau | Overmatch hoặc tốn CPU | Bounded classes, benchmark |
| Ghép regex từ client input | Regex injection, ReDoS | Pattern tĩnh |
| Nới firewall để URL bất thường được match | Mở nguy cơ bypass routing | Giữ normalization chặt, test |
| Chỉ test URL hợp lệ | Bỏ sót case âm tính | Matrix path/method/query/authority |
| Coi 404 là deny bởi Spring Security | Endpoint có thể chỉ không tồn tại | Test chain, matcher, controller thật |

## 16. Checklist review

- [ ] Regex có thực sự cần hơn path matcher thông thường?
- [ ] Hiểu đúng chuỗi `servletPath + pathInfo + ?queryString` và context path?
- [ ] Giới hạn method khi các action có permission khác nhau?
- [ ] Escape chính xác `\?`, `\.` và backslash trong Java string?
- [ ] Cần case-sensitive hay case-insensitive? Có test?
- [ ] Mẫu có anchors và phạm vi segment hẹp; không lạm dụng `.*`?
- [ ] Rule thứ tự đúng: đặc thù trước, deny fallback sau?
- [ ] Nếu regex ở `securityMatcher`, có chain fallback cho URL ngoài phạm vi?
- [ ] Có test URL với query, method sai, ID sai, ID quá dài, trailing slash, path lạ, encoding?
- [ ] Cấp quyền dựa trên authority thật; không dựa ID, tenant do client tự khai?
- [ ] Có service-level check owner/tenant và action nghiệp vụ?
- [ ] Pattern được review về ReDoS và kích thước input?
- [ ] Hệ thống có gateway, custom servlet path hoặc reverse proxy rewrite? Đã test thực tế?

**Ghi nhớ:** `RegexRequestMatcher` giúp **nhận diện một HTTP request có hình dạng cụ thể**. Nó chỉ là một mắt xích của authorization; chính sách đầy đủ còn cần chain coverage, thứ tự rule, authentication/authority và quyền trên resource.

## 17. Câu hỏi tự kiểm tra

**1. RegexRequestMatcher chỉ xem path, bỏ qua query string?**  
Không. JavaDoc mô tả việc so khớp `servletPath + pathInfo + queryString`; nếu có query, chuỗi sẽ có dấu `?`.

**2. Mẫu `^/api/orders/[0-9]+$` có chắc khớp `/api/orders/42?expand=items`?**  
Không; query string có thể làm mẫu đó không khớp. Dùng pattern có query tùy chọn hoặc path matcher khi chỉ cần path.

**3. Làm sao giới hạn regex cho HTTP GET?**  
Dùng `RegexRequestMatcher.regexMatcher(HttpMethod.GET, pattern)` với phiên bản hỗ trợ factory này.

**4. Vì sao `.+` có thể làm quyền đọc áp dụng quá rộng?**  
Nó có thể nuốt cả dấu slash và các segment sau ID, kể cả `/approve`.

**5. Nếu regex trong `securityMatcher` không khớp thì sao?**  
Chain đó không được chọn; nếu không có chain khác hoặc fallback, URL có thể nằm ngoài bộ lọc Spring Security.

**6. Một URL ID hợp lệ và authority `order:read` đã đủ đọc mọi đơn hàng?**  
Không. Phải kiểm tra owner/tenant và phạm vi tài nguyên.

**7. Có nên dùng regex để kiểm tra dữ liệu JSON body hoặc quyền export theo query?**  
Không nên dùng nó làm validator/policy duy nhất; dùng DTO validation, custom matcher và service authorization tùy tình huống.

**8. Vì sao phải test cả dấu `?`, chữ hoa, POST và slash dư?**  
Vì regex/method/path matching có thể cho kết quả khác và làm rule đặc quyền bị bỏ qua.

## 18. Nguồn chính thức

- Spring Security – Authorize HttpServletRequests, *Matching Using Regular Expressions*: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – RegexRequestMatcher JavaDoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/util/matcher/RegexRequestMatcher.html
- Spring Security – Java Configuration và securityMatcher: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security – HttpFirewall: https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html
- Java SE 17 – java.util.regex.Pattern: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html
