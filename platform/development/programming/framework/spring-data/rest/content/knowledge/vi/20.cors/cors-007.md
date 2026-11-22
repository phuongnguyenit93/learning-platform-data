# Origins, methods, headers, credentials và giới hạn wildcard trong CORS

## Mục tiêu

Cross-Origin Resource Sharing (CORS) là cơ chế cho phép trình duyệt web gọi tài nguyên ở một origin khác theo chính sách do server công bố. Với Spring Data REST, CORS có thể được cấu hình ở cấp repository bằng `@CrossOrigin` hoặc ở cấp đường dẫn bằng `RepositoryRestConfigurer` và `CorsRegistry`.

Một chính sách CORS cần xác định rõ:

- **Origins**: website nào được phép gửi request từ trình duyệt đến API.
- **Methods**: các HTTP method mà origin đó được phép sử dụng.
- **Allowed headers**: các request header mà browser được phép gửi.
- **Exposed headers**: các response header mà JavaScript phía browser được phép đọc.
- **Credentials**: request có được gửi cookie hoặc thông tin xác thực theo cơ chế browser hay không.
- **Max age**: thời gian browser có thể cache kết quả preflight.

Các giá trị này có quan hệ với nhau. Đặc biệt, khi bật credentials, không thể dùng wildcard origin `*` theo cách thông thường. Cần cấu hình đúng từng thành phần để tránh lỗi preflight, lỗi đọc response hoặc mở API cho origin ngoài dự định.

## 1. Origin là gì?

Origin được xác định bởi ba thành phần:

```text
scheme + host + port
```

Ví dụ:

- `https://app.example.com`
- `http://localhost:3000`
- `http://localhost:5173`

Các URL sau là các origin khác nhau:

| URL | Lý do |
|---|---|
| `http://localhost:3000` | Port 3000 |
| `http://localhost:5173` | Port 5173 |
| `https://localhost:3000` | Scheme HTTPS thay vì HTTP |
| `https://app.example.com` | Host khác localhost |

Path không thuộc origin. Ví dụ `https://app.example.com/page-a` và `https://app.example.com/page-b` có cùng origin.

Trình duyệt gửi request header `Origin` để cho server biết trang web nào khởi tạo request cross-origin. Server so sánh giá trị này với danh sách origin được phép và trả các CORS response header tương ứng.

CORS chủ yếu là chính sách do browser thực thi. Một chương trình như curl, Postman hoặc backend service có thể gửi request trực tiếp mà không bị cơ chế CORS của browser chặn. Vì vậy, gọi API thành công bằng Postman không chứng minh cấu hình CORS của browser đã đúng.

## 2. CORS hoạt động như thế nào?

Khi frontend và API khác origin, browser kiểm tra CORS response header. Tùy loại request, browser có thể gửi request trực tiếp hoặc gửi một request preflight trước.

### 2.1. Simple request

Với một số request đơn giản, browser gửi request thật kèm `Origin`. Server phải trả `Access-Control-Allow-Origin` phù hợp để JavaScript được phép đọc response.

Ví dụ:

```http
GET /people
Origin: https://app.example.com
Accept: application/hal+json
```

Nếu origin được phép, response có thể chứa:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

Nếu server không cho phép origin, browser không cho JavaScript truy cập response. Request đơn giản vẫn có thể đã đến server và được xử lý; CORS không phải cơ chế xác thực request.

### 2.2. Preflight request

Với request không thuộc nhóm simple request, browser thường gửi preflight bằng HTTP OPTIONS để hỏi server trước khi gửi request thật. Ví dụ PUT có `Content-Type: application/json` và header `Authorization` thường cần preflight.

Request preflight:

```http
OPTIONS /people/42
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: authorization, content-type, x-request-id
```

Server trả các header cho biết request thật có được phép hay không:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Nếu preflight thành công, browser mới gửi request PUT thật. Nếu origin, method hoặc header không được phép, browser dừng luồng và không gửi request thật.

OPTIONS là method browser dùng để hỏi trước. Trong `allowedMethods`, hãy khai báo các method thực sự mà frontend muốn gọi, chẳng hạn GET, POST, PUT, PATCH và DELETE. Spring xử lý preflight OPTIONS dựa trên method được yêu cầu trong `Access-Control-Request-Method`; không nhầm việc này với việc cấp quyền nghiệp vụ cho endpoint OPTIONS.

## 3. Cấu hình CORS ở cấp repository bằng @CrossOrigin

Spring Data REST hỗ trợ `@CrossOrigin` trên repository interface. Cấu hình này áp dụng cho các resource thuộc repository đó.

Ví dụ:

```java
@RepositoryRestResource(path = "people")
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {
        RequestMethod.GET,
        RequestMethod.POST,
        RequestMethod.PUT,
        RequestMethod.PATCH
    },
    allowedHeaders = {
        "Authorization",
        "Content-Type",
        "X-Request-Id"
    },
    exposedHeaders = {
        "Location",
        "ETag"
    },
    allowCredentials = "true",
    maxAge = 3600
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

Ý nghĩa:

- `origins`: chỉ frontend tại `https://app.example.com` được phép gọi cross-origin.
- `methods`: giới hạn các HTTP method mà frontend có thể gọi.
- `allowedHeaders`: cho phép browser gửi Authorization, Content-Type và X-Request-Id.
- `exposedHeaders`: cho phép JavaScript đọc Location và ETag trong response.
- `allowCredentials`: cho phép browser gửi credentials theo chính sách CORS.
- `maxAge`: cache kết quả preflight trong 3.600 giây.

Nếu chỉ cần một cấu hình đơn giản cho repository không dùng cookie hoặc credentials, có thể dùng:

```java
@CrossOrigin(
    origins = "https://app.example.com",
    methods = { RequestMethod.GET, RequestMethod.POST }
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

Không nên dùng `@CrossOrigin` không có thuộc tính trên repository nhạy cảm mà không xem xét mặc định. Theo tài liệu Spring Data REST, dạng annotation mặc định cho phép mọi origin và mọi HTTP method. Hãy khai báo origin và method cụ thể theo nhu cầu API.

Spring Data REST cũng hỗ trợ CORS trên custom controller mang `@RepositoryRestController`. Controller này có thể kế thừa cấu hình `@CrossOrigin` từ repository liên quan.

## 4. Cấu hình CORS toàn cục bằng RepositoryRestConfigurer

Khi cần cấu hình theo URL path thay vì lặp lại annotation trên nhiều repository, triển khai `RepositoryRestConfigurer`:

```java
@Component
public class SpringDataRestCorsConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        cors.addMapping("/people/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods(
                "GET", "POST", "PUT", "PATCH", "DELETE"
            )
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-Request-Id"
            )
            .exposedHeaders(
                "Location",
                "ETag"
            )
            .allowCredentials(true)
            .maxAge(3600);
    }
}
```

Mapping `/people/**` áp dụng cho các URI people, bao gồm collection, item và các đường dẫn con phù hợp. Nếu Spring Data REST có base path, hãy xác nhận mapping path theo cách cấu hình của ứng dụng và kiểm thử URI thực tế.

Có thể đăng ký mapping riêng cho nhiều resource:

```java
cors.addMapping("/people/**")
    .allowedOrigins("https://people.example.com")
    .allowedMethods("GET", "POST", "PUT", "PATCH")
    .allowedHeaders("Content-Type", "Authorization")
    .allowCredentials(true);

cors.addMapping("/public-catalog/**")
    .allowedOrigins("*")
    .allowedMethods("GET", "HEAD")
    .allowedHeaders("*")
    .allowCredentials(false);
```

Ví dụ thứ hai dùng wildcard origin cho catalog công khai không có credentials. Không dùng cấu hình này cho endpoint chứa dữ liệu người dùng hoặc phiên đăng nhập.

**Lưu ý quan trọng:** cấu hình CORS Spring MVC hiện có thông qua `WebMvcConfigurer.addCorsMappings(...)` không tự động được áp dụng cho Spring Data REST. Nếu muốn cấu hình CORS cho repository resource, hãy dùng cơ chế CORS của Spring Data REST như `RepositoryRestConfigurer` hoặc `@CrossOrigin`. Nếu ứng dụng đồng thời có custom MVC controller và Spring Data REST, hãy xác định rõ từng nhóm endpoint đang nhận cấu hình nào.

## 5. allowedOrigins: chỉ định origin được phép

`allowedOrigins(...)` nhận danh sách origin cụ thể hoặc wildcard `*` khi không dùng credentialed request.

Ví dụ danh sách origin:

```java
cors.addMapping("/people/**")
    .allowedOrigins(
        "https://app.example.com",
        "https://admin.example.com",
        "http://localhost:5173"
    )
    .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE");
```

Mỗi origin phải khớp scheme, host và port mà browser gửi trong header `Origin`. Khi frontend chuyển từ HTTP sang HTTPS hoặc đổi port dev server, cần cập nhật allow-list.

Không thêm dấu path vào origin. Ví dụ đúng là `https://app.example.com`, không phải `https://app.example.com/dashboard`.

Nếu dùng `allowedOrigins("*")`, server cho phép mọi origin theo chính sách CORS của mapping đó. Đây là lựa chọn chỉ nên dùng cho tài nguyên công khai không cần credentials và không chứa dữ liệu phụ thuộc người dùng.

## 6. allowedOriginPatterns: wildcard theo pattern

Spring Framework hỗ trợ `allowedOriginPatterns(...)` để so khớp một tập origin bằng pattern. Ví dụ:

```java
cors.addMapping("/tenant-api/**")
    .allowedOriginPatterns("https://*.example.com")
    .allowedMethods("GET", "POST")
    .allowCredentials(true);
```

Khác với `allowedOrigins("*")`, pattern được dùng để tìm origin phù hợp; khi request khớp, response trả origin thực tế của request thay vì trả chuỗi wildcard. Điều này cho phép dùng pattern trong một số cấu hình credentialed request.

Tuy nhiên, pattern không tự động làm một origin trở nên đáng tin cậy. Nếu bất kỳ tenant hoặc người dùng nào có thể tạo subdomain dưới `example.com`, pattern `https://*.example.com` có thể cho phép cả những origin không nên truy cập API. Hãy xác định rõ ai có thể kiểm soát các host khớp pattern.

`allowedOriginPatterns` được hỗ trợ từ Spring Framework 5.3. Nếu dự án dùng phiên bản cũ hơn, kiểm tra API tương ứng trước khi dùng. Với hệ thống có danh sách frontend ổn định, danh sách origin cụ thể vẫn là lựa chọn dễ kiểm soát nhất.

## 7. allowedMethods: giới hạn HTTP method

`allowedMethods(...)` xác định các HTTP method mà browser được phép sử dụng cho origin được cho phép.

Ví dụ:

```java
.allowedMethods("GET", "HEAD", "POST")
```

Nếu frontend cần cập nhật tài nguyên, bổ sung PUT hoặc PATCH. Nếu cần xóa, bổ sung DELETE. Không mở method chỉ vì repository có hỗ trợ method đó; hãy dựa trên chức năng client thực sự cần.

Ví dụ phân quyền method theo resource:

| Resource | Methods CORS có thể mở |
|---|---|
| Public catalog | GET, HEAD |
| People directory | GET |
| Profile management | GET, PUT, PATCH |
| Order management | GET, POST, PUT, PATCH |
| Admin operation | GET, POST, DELETE |

CORS chỉ cho browser biết method nào được phép gửi cross-origin. Nó không thay thế authorization. Nếu một origin được phép gửi DELETE, người dùng vẫn phải vượt qua Spring Security và các kiểm tra quyền nghiệp vụ trước khi xóa dữ liệu.

## 8. allowedHeaders và exposedHeaders khác nhau

Hai cấu hình này thường bị nhầm lẫn.

### 8.1. allowedHeaders: request header được phép gửi

`allowedHeaders(...)` kiểm soát các header phía browser muốn gửi trong request cross-origin. Ví dụ:

```java
.allowedHeaders(
    "Authorization",
    "Content-Type",
    "X-Request-Id",
    "X-XSRF-TOKEN"
)
```

Khi preflight được gửi, browser liệt kê các header dự định sử dụng trong `Access-Control-Request-Headers`. Server phải cho phép các header đó bằng `Access-Control-Allow-Headers`.

Các header thường gặp:

- `Authorization`: gửi bearer token hoặc thông tin xác thực theo cơ chế client dùng.
- `Content-Type`: mô tả định dạng request body, ví dụ JSON.
- `X-Request-Id`: mã tương quan để truy vết request.
- `X-XSRF-TOKEN`: token CSRF nếu ứng dụng dùng cơ chế cookie-based CSRF.

Không cần thêm mọi header vào allow-list nếu frontend không gửi chúng. Hãy kiểm tra request thực tế trong browser Network panel để biết danh sách cần thiết.

### 8.2. exposedHeaders: response header JavaScript được đọc

Browser chỉ cho JavaScript đọc một số response header an toàn theo mặc định. Nếu frontend cần đọc header khác, server phải khai báo `exposedHeaders(...)`.

Ví dụ:

```java
.exposedHeaders(
    "Location",
    "ETag",
    "Link",
    "X-Request-Id"
)
```

Các tình huống thường gặp:

- `Location`: đọc URI item mới sau POST.
- `ETag`: dùng validator cho cache hoặc cập nhật có điều kiện.
- `Link`: đọc metadata liên kết nếu client cần xử lý header này.
- `X-Request-Id`: hiển thị hoặc ghi log mã truy vết.

Khai báo `allowedHeaders("Location")` không làm JavaScript đọc được response header Location. Muốn browser cho phép đọc response header, phải dùng `exposedHeaders("Location")`.

## 9. Credentials: cookie, session và thông tin xác thực

Khi frontend cần gửi cookie hoặc credentials qua cross-origin request, phải cấu hình CORS cho phép credentials.

Ví dụ:

```java
cors.addMapping("/people/**")
    .allowedOrigins("https://app.example.com")
    .allowedMethods("GET", "POST", "PUT", "PATCH")
    .allowedHeaders("Content-Type", "X-XSRF-TOKEN")
    .exposedHeaders("Location")
    .allowCredentials(true)
    .maxAge(3600);
```

Phía browser với Fetch API:

```javascript
const response = await fetch("https://api.example.com/people", {
  method: "GET",
  credentials: "include",
  headers: {
    "Accept": "application/hal+json"
  }
});
```

Với XMLHttpRequest, thuộc tính tương ứng là `withCredentials = true`.

Server cần trả:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

Giá trị `Access-Control-Allow-Origin: *` không hợp lệ cho credentialed request. Browser không chấp nhận response có wildcard origin khi request dùng credentials.

Cấu hình credentials tạo mức tin cậy cao với origin được phép vì browser có thể gửi cookie phiên, thông tin xác thực và CSRF token. Chỉ bật khi thật sự cần và chỉ cho các origin được kiểm soát.

CORS không ghi đè cookie `SameSite`, `Secure`, domain hoặc path. Cookie vẫn phải đáp ứng chính sách cookie của browser. Trong môi trường production, cookie cross-site thường cần `SameSite=None; Secure`, nhưng hãy chọn thuộc tính theo kiến trúc domain và threat model của ứng dụng.

## 10. Giới hạn wildcard khi bật credentials

Đây là quy tắc cần nhớ:

```java
// Không hợp lệ khi allowCredentials(true)
.allowedOrigins("*")
.allowCredentials(true)
```

Spring Framework từ chối cấu hình `allowedOrigins("*")` cùng `allowCredentials(true)`, vì server không thể trả wildcard origin trong response credentialed theo CORS specification.

Có hai cách:

**Cách 1: khai báo origin cụ thể**

```java
.allowedOrigins(
    "https://app.example.com",
    "https://admin.example.com"
)
.allowCredentials(true)
```

**Cách 2: dùng origin pattern có kiểm soát**

```java
.allowedOriginPatterns("https://*.example.com")
.allowCredentials(true)
```

Khi pattern khớp, Spring trả origin thực tế thay vì ký tự wildcard. Dù vậy, pattern rộng vẫn có thể cho phép một tập host lớn; không dùng pattern nếu không kiểm soát được việc tạo subdomain.

Wildcard trong allowed methods và allowed headers có cách xử lý khác với wildcard origin. Khi credentials được bật, Spring có thể sao chép method và headers mà browser yêu cầu trong preflight vào response tương ứng. Cấu hình này tiện lợi nhưng làm chính sách rộng hơn; nếu biết trước các method/header cần dùng, hãy khai báo danh sách cụ thể.

Đối với `exposedHeaders("*")`, hành vi thực tế có khác biệt so với quy tắc wildcard origin và có giới hạn tương thích với CORS specification khi credentials được bật. Không dựa vào wildcard để expose mọi header trong ứng dụng credentialed; hãy liệt kê các response header mà frontend thực sự cần đọc.

## 11. maxAge: cache kết quả preflight

`maxAge(...)` xác định thời gian browser có thể cache kết quả preflight, tính bằng giây.

Ví dụ:

```java
.maxAge(3600)
```

Browser có thể dùng kết quả preflight đã cache trong tối đa một giờ, tùy giới hạn nội bộ của browser. Nhờ vậy, những request tiếp theo cùng điều kiện không cần gửi OPTIONS mỗi lần.

Thời gian dài giúp giảm số request preflight nhưng làm thay đổi CORS policy có thể không được browser áp dụng ngay cho đến khi cache hết hạn. Trong môi trường phát triển hoặc khi đang điều chỉnh policy, dùng thời gian ngắn hơn; khi policy ổn định, có thể tăng phù hợp.

Không nhầm `maxAge` với thời hạn đăng nhập, thời hạn cookie hoặc thời hạn cache response dữ liệu.

## 12. Kết hợp CORS với Spring Security

Nếu ứng dụng bật Spring Security, cần bảo đảm CORS được xử lý trước bước xác thực/authorization phù hợp. Preflight OPTIONS thường không mang cookie phiên giống request thật; nếu security filter chặn OPTIONS trước khi CORS xử lý, browser sẽ báo lỗi CORS dù endpoint GET/PUT có thể đã được bảo vệ đúng.

Spring Security có hỗ trợ CORS tích hợp. Cấu hình filter chain có thể bật cơ chế này:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .build();
    }
}
```

Khi dùng `.cors(Customizer.withDefaults())`, Spring Security cần tìm được CORS configuration source phù hợp. Hãy kiểm tra cách cấu hình CORS hiện có của ứng dụng và bảo đảm mapping áp dụng cho cả repository resource. Không tạo nhiều CORS filter hoặc nhiều nguồn cấu hình xung đột khiến response có header trùng lặp.

Với Spring Data REST, cấu hình CORS cho repository resource bằng `RepositoryRestConfigurer` hoặc `@CrossOrigin`. Tài liệu Spring Data REST lưu ý cấu hình CORS hiện có của Spring MVC không tự động áp dụng cho Spring Data REST. Khi dùng Spring Security đồng thời, hãy kiểm thử preflight qua toàn bộ filter chain chứ không chỉ kiểm tra handler mapping.

## 13. CORS không thay thế authentication, authorization hoặc CSRF

CORS và security giải quyết các vấn đề khác nhau:

| Cơ chế | Câu hỏi được giải quyết |
|---|---|
| CORS | Browser từ origin nào được phép đọc response cross-origin? |
| Authentication | Người gọi là ai? |
| Authorization | Người gọi được phép thực hiện thao tác nào trên tài nguyên? |
| CSRF protection | Request dùng cookie tự động gửi có bị giả mạo từ site khác không? |

Một API cho phép `https://app.example.com` qua CORS vẫn phải xác thực người dùng và kiểm tra quyền truy cập dữ liệu. CORS không ngăn curl hoặc backend service gửi request trực tiếp.

Đặc biệt, simple request có thể đến server ngay cả khi browser sau đó chặn JavaScript đọc response. Vì vậy, không dùng CORS như biện pháp chống CSRF. Nếu ứng dụng dùng cookie/session authentication, hãy giữ CSRF protection phù hợp và gửi token CSRF qua header được allow-list.

Không cho phép mọi origin có credentials chỉ để xử lý lỗi browser. Hãy xác định origin thật của frontend, method và header cần thiết, sau đó cấu hình allow-list tương ứng.

## 14. Ví dụ cấu hình theo môi trường

Trong development, frontend có thể chạy tại localhost với port riêng:

```java
cors.addMapping("/people/**")
    .allowedOrigins("http://localhost:5173")
    .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
    .allowedHeaders("Content-Type", "Authorization", "X-XSRF-TOKEN")
    .exposedHeaders("Location", "ETag")
    .allowCredentials(true)
    .maxAge(300);
```

Trong production:

```java
cors.addMapping("/people/**")
    .allowedOrigins("https://app.example.com")
    .allowedMethods("GET", "POST", "PUT", "PATCH")
    .allowedHeaders("Content-Type", "Authorization", "X-XSRF-TOKEN")
    .exposedHeaders("Location", "ETag")
    .allowCredentials(true)
    .maxAge(3600);
```

Nếu frontend admin nằm ở một origin khác, thêm origin đó một cách có chủ đích hoặc tạo mapping riêng nếu quyền và chức năng khác nhau.

Không nên đưa `http://localhost:5173` vào cấu hình production chỉ để tránh lỗi trong môi trường dev. Tách cấu hình theo profile hoặc externalize danh sách origin bằng cấu hình ứng dụng, nhưng không để một profile production vô tình nhận wildcard từ cấu hình development.

## 15. Kiểm tra CORS bằng curl

Có thể gửi preflight thủ công để xem server trả gì:

```bash
curl -i -X OPTIONS "http://localhost:8080/people/42" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: authorization,content-type,x-request-id"
```

Kiểm tra các response header:

- `Access-Control-Allow-Origin` có đúng origin không.
- `Access-Control-Allow-Methods` có PUT không.
- `Access-Control-Allow-Headers` có các header browser yêu cầu không.
- `Access-Control-Allow-Credentials` có `true` nếu request dùng credentials không.
- `Access-Control-Max-Age` có giá trị như cấu hình không.

Kiểm tra một origin không được phép:

```bash
curl -i -X OPTIONS "http://localhost:8080/people/42" \
  -H "Origin: https://unknown.example.net" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type"
```

Response không được cấp `Access-Control-Allow-Origin` cho origin không nằm trong policy. Curl chỉ hiển thị response; nó không thực thi quy tắc CORS giống browser.

Sau khi kiểm tra bằng curl, hãy thử từ frontend thật trong browser vì browser còn áp dụng cookie, SameSite, preflight cache và các giới hạn CORS riêng.

## 16. Kiểm thử CORS trong ứng dụng

Có thể kiểm thử bằng MockMvc để xác nhận preflight được xử lý:

```java
@SpringBootTest
@AutoConfigureMockMvc
class PersonCorsTests {

    @Autowired
    MockMvc mvc;

    @Test
    void allowsConfiguredOriginAndPutPreflight() throws Exception {
        mvc.perform(options("/people/42")
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "PUT"
                )
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type"
                ))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"
            ))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true"
            ));
    }

    @Test
    void doesNotAllowUnknownOrigin() throws Exception {
        mvc.perform(options("/people/42")
                .header(HttpHeaders.ORIGIN, "https://unknown.example.net")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "PUT"
                ))
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN
            ));
    }
}
```

Đây là khung test tích hợp; status của preflight và cách security filter chain xử lý OPTIONS phụ thuộc cấu hình ứng dụng. Có thể cần thêm Spring Security Test request post-processors hoặc cấu hình test authentication tương ứng.

Nên kiểm tra thêm:

- Origin hợp lệ và origin không hợp lệ.
- Method được phép và method bị từ chối.
- Request header được phép và header không được phép.
- Response header chỉ được JavaScript đọc khi nằm trong exposed headers.
- Credentials có `Access-Control-Allow-Credentials: true` và origin không phải wildcard.
- Custom repository controller và Spring Data REST repository resource đều nhận policy dự kiến.
- Preflight không bị Spring Security chặn trước khi CORS xử lý.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| Browser báo CORS nhưng Postman gọi được | Postman không thực thi CORS như browser | Kiểm tra Origin và response CORS header trong browser |
| OPTIONS trả 401/403 | Security filter chặn preflight trước CORS | Bật CORS integration và cho preflight được xử lý trước authorization phù hợp |
| Frontend localhost đổi port thì lỗi | Origin gồm scheme, host và port | Thêm đúng origin của dev server |
| GET chạy nhưng PUT/PATCH lỗi | Method chưa nằm trong allowedMethods | Bổ sung method thật sự cần dùng |
| Preflight báo header không được phép | Thiếu header trong allowedHeaders | Thêm Authorization, Content-Type hoặc custom header cần thiết |
| JavaScript không đọc được Location | Location chưa nằm trong exposedHeaders | Thêm exposedHeaders("Location") |
| Credentials không hoạt động | Thiếu allowCredentials hoặc browser không gửi credentials | Bật allowCredentials và dùng credentials: "include" |
| Spring từ chối cấu hình CORS | allowedOrigins("*") kết hợp allowCredentials(true) | Dùng origin cụ thể hoặc allowedOriginPatterns có kiểm soát |
| Origin pattern cho phép quá nhiều site | Wildcard pattern bao phủ subdomain không tin cậy | Thu hẹp pattern hoặc dùng danh sách origin cụ thể |
| CORS annotation không tác dụng với repository | Annotation đặt trên MVC controller khác hoặc bean không đúng | Đặt @CrossOrigin trên repository interface hoặc dùng RepositoryRestConfigurer |
| CORS MVC không áp dụng cho Spring Data REST | Hai cấu hình thuộc các handler mapping khác nhau | Cấu hình riêng CORS của Spring Data REST |
| Browser vẫn gửi request dù response bị chặn | CORS không phải cơ chế chặn mọi request hay CSRF | Dùng authentication, authorization và CSRF protection phù hợp |

## 18. Checklist cấu hình CORS

- Xác định chính xác origin của từng frontend: scheme, host và port.
- Chỉ cho phép origin thực sự cần truy cập API.
- Chọn `@CrossOrigin` cho repository cụ thể hoặc `RepositoryRestConfigurer` cho mapping theo path.
- Khai báo các HTTP method client thực sự sử dụng.
- Phân biệt request header được phép gửi với response header được phép đọc.
- Thêm Location hoặc ETag vào exposed headers khi frontend cần đọc.
- Chỉ bật credentials khi ứng dụng cần cookie hoặc browser credentials.
- Không dùng `allowedOrigins("*")` cùng `allowCredentials(true)`.
- Dùng `allowedOriginPatterns` chỉ khi kiểm soát được toàn bộ host khớp pattern.
- Đặt maxAge phù hợp với tần suất thay đổi policy.
- Kiểm tra preflight OPTIONS qua cả CORS và Spring Security.
- Không coi CORS là thay thế cho authentication, authorization hoặc CSRF.
- Tách origin development và production.
- Kiểm thử bằng browser thật ngoài các kiểm tra curl/MockMvc.

## Kết luận

CORS trong Spring Data REST có thể cấu hình ở cấp repository bằng `@CrossOrigin` hoặc theo URL path bằng `RepositoryRestConfigurer` và `CorsRegistry`. Origins xác định website được phép gọi; methods giới hạn HTTP method; allowedHeaders kiểm soát request header; exposedHeaders quyết định response header JavaScript có thể đọc; credentials cho phép browser gửi cookie hoặc thông tin xác thực; maxAge cache kết quả preflight. Khi bật credentials, không dùng `allowedOrigins("*")`; hãy khai báo origin cụ thể hoặc dùng `allowedOriginPatterns` có kiểm soát. CORS không thay thế authentication, authorization hay CSRF protection. Hãy kiểm thử preflight qua toàn bộ cấu hình Spring Security và browser thực tế để xác nhận chính sách hoạt động đúng.

## Tài liệu tham khảo

- Spring Data REST – Configuring CORS: https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html
- Spring Framework – CORS in Spring MVC, credentialed requests, origin patterns and preflight: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Security – CORS integration and filter ordering: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- MDN – Cross-Origin Resource Sharing (CORS): https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS
