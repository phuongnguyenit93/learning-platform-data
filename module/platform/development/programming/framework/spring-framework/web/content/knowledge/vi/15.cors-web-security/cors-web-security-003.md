# @CrossOrigin, cấu hình toàn cục và cách kết hợp chính sách trong Spring MVC

## 1. Mục tiêu học tập

Một trang frontend chạy tại `https://app.example.com` gọi API Spring MVC ở `https://api.example.com`. Dù cùng hệ thống nghiệp vụ, đây là **hai origin khác nhau**; JavaScript trong trình duyệt chịu quy tắc **same-origin policy**. CORS (**Cross-Origin Resource Sharing**) là cơ chế HTTP cho phép server quyết định những origin nào được trình duyệt cho phép đọc response và những request cross-origin nào được thực hiện theo cơ chế CORS.

Trong Spring MVC, có hai cấp cấu hình rất dễ bị hiểu nhầm:

- **Cục bộ**: annotation `@CrossOrigin` trên controller hoặc method.
- **Toàn cục**: `WebMvcConfigurer#addCorsMappings` hoặc các cấu hình `CorsConfiguration`/filter tương ứng.

Nếu áp dụng **cả hai**, Spring MVC có quy tắc **kết hợp chính sách** — thường **cộng gộp danh sách** nhưng **ghi đè thuộc tính đơn**. Không được mặc định rằng annotation method luôn “chặt hơn” hoặc “ghi đè hoàn toàn” cấu hình toàn cục.

Bài này giúp bạn:

1. Phân biệt **origin**, **site**, CORS, preflight, actual/simple request và các HTTP header quan trọng.
2. Dùng `@CrossOrigin` ở mức method/class, hiểu mặc định và giới hạn của từng thuộc tính.
3. Dùng `WebMvcConfigurer#addCorsMappings` để đặt chính sách theo URL path.
4. Giải thích chính xác `CorsConfiguration.combine`, additive list, local override scalar, wildcard, `allowedOriginPatterns` và credential rules.
5. Kết hợp Spring MVC CORS với Spring Security đúng thứ tự; phân biệt CORS với authentication, authorization, CSRF, cookie `SameSite` và reverse proxy.
6. Viết ví dụ chạy được bằng **Java 17+, Spring Boot 3.x, Spring Framework 6.x**, cùng MockMvc tests xác minh **preflight**, **actual request**, cấu hình gộp và origin bị từ chối.
7. Chẩn đoán lỗi CORS có hệ thống thay vì thêm `Access-Control-Allow-Origin: *` một cách mù quáng.

**Phạm vi phiên bản:** Spring MVC (Servlet stack), Spring Framework **6.x** và Spring Boot **3.x**. Code demo dùng `spring-boot-starter-web` và không mặc định thêm Spring Security. Với Spring Framework 7/Boot 4, cần kiểm tra Javadoc/API đúng phiên bản trước khi chuyển nguyên ví dụ.

## 2. Xác định origin trước khi phân tích chính sách kết hợp

Đối với HTTP(S), **origin = scheme + hostname + effective port**. Vì vậy `https://app.example.com` và `https://api.example.com` là hai origin khác nhau; path `/api/items` không ảnh hưởng phép so sánh. `http://localhost:3000` và `http://localhost:8080` cũng khác origin vì khác port.

Trong bài này, vấn đề không còn là học lại toàn bộ bảng same-origin, mà là **một handler có thể nhận quyền CORS từ hai nơi**. Ví dụ API tại `https://api.example.com` đặt chính sách toàn cục cho `https://app.example.com`; riêng handler đối tác khai báo thêm `https://partner.example.com`. Câu hỏi phải kiểm thử là danh sách origin được **cộng gộp hay thay thế**, và những thuộc tính như `maxAge` có cùng quy tắc hay không.

| Nguồn chính sách | Ví dụ | Trách nhiệm cần rà soát |
| --- | --- | --- |
| Global `WebMvcConfigurer` | `https://app.example.com` trên `/api/**` | Quyền chung cho nhiều route |
| Local `@CrossOrigin` | `https://partner.example.com` trên một handler | Quyền bổ sung, không mặc định thu hẹp global |
| Spring Security/proxy | Filter chain, gateway hoặc CDN | Chỉ xử lý CORS ở tầng đã được thiết kế, tránh nhiều policy độc lập xung đột |

Hai subdomain có thể **same-site đối với cookie nhưng cross-origin đối với JavaScript**. CORS không chứng thực principal và không ngăn `curl` gọi API; xác thực, phân quyền và CSRF vẫn là các lớp bảo vệ độc lập. Phần kế tiếp dùng actual/preflight requests để xác định cách Spring hợp nhất cấu hình, thay vì chỉ so các URL.

## 3. Hai luồng CORS: actual request và preflight

### 3.1. Actual request

Ví dụ request đọc dữ liệu:

~~~http
GET /api/items HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
~~~

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json

[{"id":1,"name":"Book"}]
~~~

`Access-Control-Allow-Origin` quyết định origin được phép đọc response trong điều kiện CORS. `Vary: Origin` giúp cache trung gian biết response header có thể phụ thuộc Origin; các cache/proxy cần tôn trọng đầy đủ `Vary`.

**Không suy ra** có `Access-Control-Allow-Origin` là endpoint được bảo vệ bằng authentication. Nếu không có auth, người ngoài vẫn có thể gọi API trực tiếp, bất kể CORS.

### 3.2. Preflight request

Với request cần preflight, chẳng hạn dùng `PATCH` hoặc request header tùy chỉnh, browser thường gửi **OPTIONS** trước:

~~~http
OPTIONS /api/items/1 HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type,x-request-id
~~~

Server phản hồi nếu chính sách cho phép:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PATCH
Access-Control-Allow-Headers: content-type,x-request-id
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Các header trên là **một ví dụ cú pháp**, không bảo đảm thứ tự dòng hoặc giá trị của mọi Spring project. `Access-Control-Max-Age` tính bằng **giây**, mô tả thời gian cache kết quả preflight; browser có thể áp giới hạn nhỏ hơn.

Nếu preflight thất bại, browser **không gửi actual request** mà nó định gửi theo quy trình CORS. Vì preflight là OPTIONS do trình duyệt gửi, frontend không cần tự gọi một OPTIONS riêng trước mỗi request.

**Simple request** (thuật ngữ thường gặp) không cần preflight khi thỏa điều kiện về method và các safelisted headers/content types. Ví dụ cross-origin `GET` thông thường có thể được gửi trực tiếp; trình duyệt vẫn kiểm tra response CORS trước khi cho JavaScript đọc. Với `Content-Type: application/json` trên một request POST cross-origin, preflight thường được thực hiện do media type này không nằm trong safelist cho trường hợp đó.

### Các header cần ghi nhớ

| Header | Chiều | Ý nghĩa |
| --- | --- | --- |
| `Origin` | Request | Origin của client theo HTTP/browser |
| `Access-Control-Request-Method` | Preflight request | Actual method dự kiến |
| `Access-Control-Request-Headers` | Preflight request | Các request headers không thuộc safelist dự kiến |
| `Access-Control-Allow-Origin` | Response | Origin được phép đọc theo CORS |
| `Access-Control-Allow-Methods` | Preflight response | Các HTTP methods được chấp nhận |
| `Access-Control-Allow-Headers` | Preflight response | Các request headers được cho phép |
| `Access-Control-Allow-Credentials` | Response | Cho phép credentialed CORS response khi bằng `true` |
| `Access-Control-Expose-Headers` | Actual response | Các response headers bổ sung mà JS được phép đọc |
| `Access-Control-Max-Age` | Preflight response | TTL của preflight permission |
| `Vary` | Response | Cache key phụ thuộc Origin/preflight headers |

`allowedHeaders` dành cho **headers client gửi**; `exposedHeaders` dành cho **headers của response mà JavaScript muốn đọc**. Nhầm hai nhóm này thường làm frontend báo “không đọc được `X-Request-Id`” dù request API trả 200.

## 4. Spring MVC xử lý CORS tại đâu?

Trên Servlet MVC stack, `HandlerMapping` hỗ trợ CORS. Khi một request được map đến controller, Spring có thể lấy `CorsConfiguration` theo URL (toàn cục) và theo `@CrossOrigin` (cục bộ), rồi kết hợp chúng cho handler.

- **Preflight** phù hợp được xử lý trực tiếp theo CORS configuration thay vì gọi business handler.
- **Actual/simple CORS** được kiểm tra rồi bổ sung response headers nếu được phép.
- Nếu không có cấu hình CORS phù hợp, server thường không thêm CORS headers cho actual request; browser sẽ không cho JavaScript đọc. Preflight không có cấu hình được phép thường bị từ chối.
- Nếu Origin không được phép hoặc method/headers của preflight không phù hợp, Spring `DefaultCorsProcessor` có thể trả **403 Invalid CORS request**.
- Nếu request **cùng origin**, CORS không phải tầng kiểm tra quyền tương ứng; controller vẫn được gọi bình thường theo security/business policies.

**Đặc biệt:** CORS hoạt động chủ yếu ở **rìa trình duyệt và MVC request mapping**. Nó không tự bảo vệ file static ở CDN, gateway hoặc endpoint không qua cùng HandlerMapping; những đường response khác phải được cấu hình CORS ở đúng tầng phục vụ chúng.

## 5. `@CrossOrigin` ở mức method và class

Một method REST:

~~~java
@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    @CrossOrigin(origins = "https://app.example.com")
    @GetMapping("/items")
    public List<Item> items() {
        return List.of(new Item(1L, "Book"));
    }

    public record Item(long id, String name) {}
}
~~~

**Đây là đoạn minh họa controller**, cần import và file riêng. `@CrossOrigin` áp dụng cho handler `GET /api/catalog/items`; method khác trên cùng class không tự nhận annotation này.

Annotation có thể đặt trên class:

~~~java
@CrossOrigin(
        origins = {"https://app.example.com", "https://admin.example.com"},
        maxAge = 3600)
@RestController
@RequestMapping("/api/catalog")
public class CatalogController {
    // Handler methods phù hợp trong class này dùng cấu hình CORS.
}
~~~

Đây cũng là ví dụ rút gọn. `@CrossOrigin` ở class level cung cấp cấu hình cho nhiều handler, method level có thể thêm customizations và chúng cũng được **combine**, không đơn thuần xóa sạch chính sách ở class.

### Mặc định nguy hiểm nếu không để ý

~~~java
@CrossOrigin
@GetMapping("/items")
public List<Item> items() {
    return service.findAll();
}
~~~

Đây là method minh họa. `@CrossOrigin` **không tham số** mặc định cho phép **mọi origin** và **mọi header**, các HTTP method được map đến handler, preflight maxAge thông dụng là **1800 giây**, và **không cho phép credentials mặc định**. Nó dễ giúp demo frontend chạy được, nhưng cũng có thể cấp khả năng đọc API public cho bất kỳ website nào. Không dùng `@CrossOrigin` trống trên API chứa dữ liệu nhạy cảm chỉ vì muốn “sửa CORS nhanh”.

### Những thuộc tính quan trọng

| `@CrossOrigin` | Ý nghĩa |
| --- | --- |
| `origins` / `value` | Danh sách origin cụ thể, ví dụ `https://app.example.com` |
| `originPatterns` | Pattern origin linh hoạt hơn, chỉ dùng khi cần và có giới hạn |
| `methods` | Các HTTP methods cho CORS; lưu ý mapping method của handler |
| `allowedHeaders` | Request headers có thể được trình duyệt gửi sau preflight |
| `exposedHeaders` | Response headers JS được phép đọc thêm |
| `allowCredentials` | Chuỗi `"true"`/`"false"` trong annotation của Spring Framework 6.x |
| `maxAge` | Cache TTL của preflight, đơn vị giây |

`@CrossOrigin(allowCredentials = "true")` dùng **String** ở annotation theo API Spring 6.x, không phải boolean Java literal. Khi bật credentials, `origins = "*"` bị từ chối vì không thể đáp ứng chuẩn CORS credentialed response. Hãy chỉ định origin cụ thể hoặc pattern được kiểm soát phù hợp.

## 6. Cấu hình CORS toàn cục bằng `WebMvcConfigurer`

Ví dụ Spring Framework 6.x/Spring Boot 3.x:

~~~java
@Configuration
public class ApiCorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(
                        "https://app.example.com",
                        "https://admin.example.com")
                .allowedMethods("GET", "POST", "PUT", "DELETE")
                .allowedHeaders("Content-Type", "Authorization")
                .exposedHeaders("X-Request-Id")
                .allowCredentials(true)
                .maxAge(600);
    }
}
~~~

Đây là **class minh họa**, cần import `Configuration`, `WebMvcConfigurer`, `CorsRegistry`. Nó áp dụng cho những URL theo pattern `/api/**` do MVC xử lý; các route ngoài pattern không tự được cấp chính sách này.

**Lưu ý về credentials:** chỉ bật `allowCredentials(true)` nếu frontend thật sự gửi cookies, HTTP authentication hoặc credentials cần thiết và trust boundary phù hợp. `Authorization: Bearer ...` là một request header cần được cho phép qua preflight, nhưng **không mặc định phải bật cookie credentials** chỉ vì endpoint dùng bearer token. Hãy đánh giá cách frontend gửi auth và quy tắc Fetch cụ thể.

### Mặc định của global registration

Nếu gọi `registry.addMapping("/api/**")` mà không hạn chế thêm, cấu hình mặc định thường cho phép **mọi origin**, **mọi header**, **GET/HEAD/POST**, `maxAge=1800` giây, **không bật credentials**. Vì vậy cần đặt `allowedOrigins` tường minh cho ứng dụng có dữ liệu không public.

Trong ứng dụng Spring Boot thông thường, `WebMvcConfigurer` là cách mở rộng cấu hình MVC mà **không** cần `@EnableWebMvc`. Thêm `@EnableWebMvc` trong Boot chỉ để bật CORS là không cần thiết và có thể làm mất nhiều hành vi Web MVC auto-configuration hữu ích.

### Local và global không tự tách biệt

Nếu cả global `/api/**` và `@CrossOrigin` trên method đều khớp, Spring kết hợp **cả hai cấu hình**. Bạn không thể chỉ nhìn method annotation rồi kết luận chính sách cuối cùng mà browser sẽ thấy. Cần xem mọi config hoạt động, kể cả CORS filter, Spring Security và gateway.

## 7. Cơ chế kết hợp `CorsConfiguration.combine`: phần trọng tâm

Theo Spring MVC 6.x, khi **global và local đều áp dụng**, cấu hình được kết hợp theo quy tắc của `CorsConfiguration#combine`.

### 7.1. List-valued properties thường cộng gộp

Các trường dạng danh sách như **`allowedOrigins`**, **`allowedOriginPatterns`**, **`allowedMethods`**, **`allowedHeaders`**, **`exposedHeaders`** thường kết hợp theo hướng **additive / union**.

Giả sử:

- Global `allowedOrigins = [https://app.example.com]`.
- Method `@CrossOrigin(origins = "https://partner.example.com")`.

Kết quả cho endpoint đó có thể cho phép **cả** `https://app.example.com` **và** `https://partner.example.com`. Annotation method **mở rộng** nhóm origin so với global, **không** biến nó thành “chỉ partner”.

Với headers:

- Global `allowedHeaders = [Content-Type]`.
- Local `allowedHeaders = [X-Partner-Key]`.
- Kết hợp: request có thể dùng cả `Content-Type` và `X-Partner-Key` khi những điều kiện khác cho phép.

Tương tự, `exposedHeaders` của global và local được cộng gộp; frontend có thể đọc cả những response headers được liệt kê nếu response thực sự có chúng.

**Wildcard `"*"` đặc biệt:** nếu một danh sách được kết hợp chứa wildcard có nghĩa cho phép tất cả, kết quả có thể vẫn là wildcard, thay vì “thu hẹp” theo danh sách cụ thể. Các giá trị mặc định được `applyPermitDefaultValues()` có xử lý riêng khi gặp những giá trị explicit. Vì vậy không dựa vào khẩu hiệu “local always overrides” hoặc “global always wins”; phải nhìn kết quả sau combine và test thực tế.

### 7.2. Scalar properties: local override global

Những thuộc tính chỉ nhận một giá trị như:

- `allowCredentials`
- `maxAge`
- `allowPrivateNetwork` khi sử dụng trong phiên bản Spring tương ứng

được kết hợp theo hướng **giá trị local không-null ghi đè global**. Ví dụ:

- Global `maxAge = 600`.
- Method `@CrossOrigin(maxAge = 1200)`.
- Endpoint method có preflight `Access-Control-Max-Age: 1200` trong trường hợp hợp lệ.

Còn nếu method không khai báo `allowCredentials`, nó thường kế thừa chính sách từ global thay vì tự động đổi ngược giá trị. Hãy phân biệt thuộc tính explicit và giá trị `null`/không chỉ định.

### 7.3. Bảng quyết định

| Thuộc tính | Global | Local | Cách hiểu khi combine |
| --- | --- | --- | --- |
| origins | `app.example.com` | `partner.example.com` | Cho phép cả hai origin nếu không có wildcard khác |
| allowedMethods | GET, POST | PATCH | Thường hợp thành GET, POST, PATCH, song còn phụ thuộc handler mapping |
| allowedHeaders | Content-Type | X-Partner-Key | Cả hai tên header |
| exposedHeaders | X-Trace-Global | X-Trace-Partner | Cả hai tên response header |
| maxAge | 600 | 1200 | 1200 (local ghi đè) |
| allowCredentials | false | true | true (local ghi đè nếu được khai báo rõ) |

**Cảnh báo:** Bảng minh họa quy tắc `CorsConfiguration` chứ không khẳng định mỗi HTTP method có business handler tương ứng. CORS `allowedMethods` không tự tạo `@PatchMapping` và không cấp quyền update ở tầng security. Nếu một method không có route tương ứng, request vẫn có thể bị 404/405 hoặc security chặn.

### 7.4. Trường hợp không thể “thu hẹp” global bằng annotation method

Giả sử global áp dụng `allowedOrigins("*")` và local chỉ định một domain đáng tin, bạn **không thể coi method đã thu hẹp** tất cả các origin được phép. Cấu hình hiệu lực có thể vẫn rất rộng sau combine. Với cookie credentials, còn có nguy cơ cấu hình không hợp lệ nếu wildcard trộn với `allowCredentials(true)`.

**Cách sửa đúng** là làm global policy đủ hẹp từ đầu, chọn mapping chính xác (ví dụ `/api/public/**` và `/api/private/**`), hoặc đưa policy vào một `CorsConfigurationSource` duy nhất khi cần kiểm soát tuyệt đối. Không dùng annotation local như “deny rule” đối với một global `*"`.

## 8. Wildcard, `allowedOriginPatterns` và credentials

### 8.1. `allowedOrigins("*")` khi không dùng credentials

Một API tài nguyên hoàn toàn public có thể chọn `Access-Control-Allow-Origin: *` khi dữ liệu thực sự được mọi browser origin đọc và không dùng credentials. Đây là **quyết định product/security** cần làm có chủ đích, không phải cấu hình “chống mọi lỗi CORS”.

### 8.2. Không dùng `*"` với `allowCredentials(true)`

Browser không chấp nhận credentialed CORS response khi `Access-Control-Allow-Origin: *`. Spring MVC 6.x cũng kiểm tra và từ chối tổ hợp không hợp lệ giữa `allowedOrigins("*")` với `allowCredentials(true)`.

Đúng hơn:

~~~java
registry.addMapping("/api/private/**")
        .allowedOrigins("https://app.example.com")
        .allowedMethods("GET", "POST")
        .allowCredentials(true);
~~~

Đây là **đoạn minh họa** bên trong `addCorsMappings`, chưa phải class Java độc lập. Nếu dùng cookie session, phải quản lý CSRF và cookie scope/SameSite bên cạnh CORS.

### 8.3. `allowedOriginPatterns` cho những subdomain được kiểm soát

~~~java
registry.addMapping("/api/tenant/**")
        .allowedOriginPatterns("https://*.trusted.example.com")
        .allowedMethods("GET")
        .allowCredentials(true);
~~~

Trong trường hợp pattern phù hợp, Spring trả **origin đã khớp** vào `Access-Control-Allow-Origin`, không trả ký tự pattern hay `*"`. Điều này cho phép một số cấu hình credentialed CORS với pattern trong giới hạn trust boundary.

Tuy nhiên, `https://*.trusted.example.com` **không tự chứng minh mọi subdomain đều đáng tin**: subdomain do user kiểm soát, subdomain takeover hoặc DNS bị quản lý kém đều có thể mở rộng attack surface. Nếu có một danh sách tenant hữu hạn, allowlist origin cụ thể và quản lý bằng config là lựa chọn dễ audit hơn. Kiểm tra cả scheme và port, không cho `http` chỉ vì muốn tương thích dev.

### 8.4. Chính sách cache và exposed headers

`Access-Control-Max-Age` cho browser cache preflight, nhưng nhiều browser có giới hạn riêng. Nó **không** nói client/cache có thể lưu data của API lâu bao nhiêu; data caching thuộc `Cache-Control`, ETag và cơ chế HTTP caching.

`Access-Control-Expose-Headers` điều khiển response headers được JavaScript đọc (ngoài safelisted response headers). Đừng để lộ token nhạy cảm trong response header rồi “bảo vệ” bằng cách không expose: browser/script cùng origin và nhiều HTTP client khác vẫn có thể đọc; server vẫn phải thiết kế bảo mật đúng.

## 9. Ví dụ Spring Boot 3.x: global + local thật sự combine

Ta xây demo dễ kiểm chứng:

- **Global:** mọi route `/api/**` cho phép origin `https://app.example.com`, method GET/POST, headers `Content-Type` và `X-Requested-With`, exposed header `X-Global-Trace`, preflight maxAge **600**.
- **Local:** handler `GET /api/demo/partner` thêm origin `https://partner.example.com`, thêm request header `X-Partner-Key`, thêm exposed header `X-Partner-Trace`, và maxAge **1200**.
- **Kết quả:** endpoint `/api/demo/global` chỉ cho `app.example.com` từ global. Endpoint `/api/demo/partner` cho **app + partner** vì origins cộng gộp; cả `X-Global-Trace` và `X-Partner-Trace` được expose, và maxAge local là 1200.

Dự án Maven **Java 17+**, **Spring Boot 3.x**; dependencies **Spring Web** và **Spring Boot Starter Test**. Tạo bằng Spring Initializr, package `com.example.demo`.

Các file:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/GlobalCorsConfig.java
src/main/java/com/example/demo/CorsDemoController.java
src/test/java/com/example/demo/CorsPolicyTest.java
~~~

### 9.1. `DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.2. `GlobalCorsConfig.java`

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class GlobalCorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "X-Requested-With")
                .exposedHeaders("X-Global-Trace")
                .allowCredentials(false)
                .maxAge(600);
    }
}
~~~

### 9.3. `CorsDemoController.java`

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class CorsDemoController {

    @GetMapping("/global")
    public ResponseEntity<Map<String, String>> globalOnly() {
        return ResponseEntity.ok()
                .header("X-Global-Trace", "global-001")
                .body(Map.of("scope", "global"));
    }

    @CrossOrigin(
            origins = "https://partner.example.com",
            allowedHeaders = "X-Partner-Key",
            exposedHeaders = "X-Partner-Trace",
            maxAge = 1200)
    @GetMapping("/partner")
    public ResponseEntity<Map<String, String>> partner() {
        return ResponseEntity.ok()
                .header("X-Global-Trace", "global-002")
                .header("X-Partner-Trace", "partner-002")
                .body(Map.of("scope", "global-plus-local"));
    }
}
~~~

Mã trên chạy trong `@RestController` Spring Boot 3.x thông thường, không có Spring Security. Để chứng minh tính cộng gộp, tuyệt đối **không sửa global thành `allowedOrigins("*")`** rồi kỳ vọng local thu hẹp quyền; làm vậy sẽ thay đổi hoàn toàn nội dung bài test và có thể mở quá rộng CORS.

### 9.4. Vì sao cấu hình này khác với hai policy độc lập?

`/api/demo/global` không mang annotation, chỉ có global policy.

`/api/demo/partner` nằm trong `/api/**` nên **nhận global policy**, đồng thời có local annotation. Spring MVC kết hợp cả hai:

~~~text
/ api / demo / partner
        |
        +--- global (/api/**)
        |       allowedOrigins: app.example.com
        |       allowedHeaders: Content-Type, X-Requested-With
        |       exposedHeaders: X-Global-Trace
        |       maxAge: 600
        |
        +--- local (@CrossOrigin trên method)
                allowedOrigins: partner.example.com
                allowedHeaders: X-Partner-Key
                exposedHeaders: X-Partner-Trace
                maxAge: 1200
        |
        v
  effective CORS policy:
    origins: app + partner
    headers: Content-Type + X-Requested-With + X-Partner-Key
    exposed: X-Global-Trace + X-Partner-Trace
    maxAge: 1200
~~~

Đoạn trên là sơ đồ giải thích, không phải file cấu hình. Nó nhấn mạnh **không có phép AND tự động** giữa origin toàn cục và origin cục bộ.

## 10. Kiểm thử CORS bằng MockMvc

Với Spring Boot 3.x và `spring-boot-starter-test`, file **`src/test/java/com/example/demo/CorsPolicyTest.java`**:

~~~java
package com.example.demo;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsPolicyTest {

    private static final String APP = "https://app.example.com";
    private static final String PARTNER = "https://partner.example.com";

    @Autowired
    MockMvc mockMvc;

    @Test
    void globalEndpointAllowsConfiguredOrigin() throws Exception {
        mockMvc.perform(get("/api/demo/global")
                        .header(HttpHeaders.ORIGIN, APP))
                .andExpect(status().isOk())
                .andExpect(org.springframework.test.web.servlet.result
                        .MockMvcResultMatchers.header()
                        .string(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, APP))
                .andExpect(jsonPath("$.scope").value("global"));
    }

    @Test
    void localEndpointAlsoAllowsGlobalOrigin() throws Exception {
        mockMvc.perform(get("/api/demo/partner")
                        .header(HttpHeaders.ORIGIN, APP))
                .andExpect(status().isOk())
                .andExpect(org.springframework.test.web.servlet.result
                        .MockMvcResultMatchers.header()
                        .string(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, APP));
    }

    @Test
    void partnerOriginIsAddedOnlyForLocalEndpoint() throws Exception {
        mockMvc.perform(get("/api/demo/partner")
                        .header(HttpHeaders.ORIGIN, PARTNER))
                .andExpect(status().isOk())
                .andExpect(org.springframework.test.web.servlet.result
                        .MockMvcResultMatchers.header()
                        .string(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                                PARTNER))
                .andExpect(jsonPath("$.scope")
                        .value("global-plus-local"));
    }

    @Test
    void globalOnlyEndpointRejectsPartnerPreflight() throws Exception {
        mockMvc.perform(options("/api/demo/global")
                        .header(HttpHeaders.ORIGIN, PARTNER)
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                                "GET"))
                .andExpect(status().isForbidden());
    }

    @Test
    void partnerPreflightCombinesHeadersAndOverridesMaxAge()
            throws Exception {
        MvcResult response = mockMvc.perform(
                        options("/api/demo/partner")
                                .header(HttpHeaders.ORIGIN, PARTNER)
                                .header(
                                        HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                                        "GET")
                                .header(
                                        HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                                        "X-Partner-Key"))
                .andExpect(status().isOk())
                .andReturn();

        assertEquals(PARTNER, response.getResponse().getHeader(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
        assertEquals("1200", response.getResponse().getHeader(
                HttpHeaders.ACCESS_CONTROL_MAX_AGE));

        String allowedHeaders = response.getResponse().getHeader(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
        assertNotNull(allowedHeaders);
        assertTrue(allowedHeaders.toLowerCase(Locale.ROOT)
                .contains("x-partner-key"));
    }

    @Test
    void localEndpointExposesBothResponseHeaders() throws Exception {
        MvcResult response = mockMvc.perform(
                        get("/api/demo/partner")
                                .header(HttpHeaders.ORIGIN, PARTNER))
                .andExpect(status().isOk())
                .andReturn();

        String exposed = response.getResponse().getHeader(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS);
        assertNotNull(exposed);
        assertTrue(exposed.contains("X-Global-Trace"));
        assertTrue(exposed.contains("X-Partner-Trace"));
    }

    @Test
    void globalPreflightUsesGlobalMaxAge() throws Exception {
        MvcResult response = mockMvc.perform(
                        options("/api/demo/global")
                                .header(HttpHeaders.ORIGIN, APP)
                                .header(
                                        HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                                        "GET")
                                .header(
                                        HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                                        "X-Requested-With"))
                .andExpect(status().isOk())
                .andReturn();

        assertEquals("600", response.getResponse().getHeader(
                HttpHeaders.ACCESS_CONTROL_MAX_AGE));
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

**Lưu ý về code:** trong ví dụ dùng lời gọi đầy đủ `MockMvcResultMatchers.header()` để không nhập nhằng `HttpHeaders`. Có thể dùng static import `header` để code ngắn hơn. Package/class đã đặt chính xác để test có thể tìm Spring Boot application context ở package gốc.

Các test thể hiện:

- Một origin global được phép truy cập cả endpoint chỉ global và endpoint có local annotation.
- Origin partner chỉ được cộng thêm tại handler được annotate.
- Preflight local có `Access-Control-Max-Age: 1200`, còn global dùng 600.
- Request header `X-Partner-Key` được cho phép trong preflight local.
- `exposedHeaders` từ global và local được union.
- Preflight từ partner tới endpoint global-only bị Spring chặn, thường với HTTP 403.

**Giới hạn:** MockMvc kiểm chứng chính sách mà Spring MVC tạo ra; nó **không chạy thuật toán CORS của một browser thật**, không thực hiện cookie store, không kiểm tra CDN/gateway và không đo vòng đời preflight cache trong Chrome/Firefox. Đối với production, bổ sung browser end-to-end test dưới các origin HTTPS thực và quan sát Network panel.

## 11. Kiểm tra CORS bằng curl mà không cần frontend

### 11.1. Actual request từ origin toàn cục

~~~bash
curl -i "http://localhost:8080/api/demo/global"   -H "Origin: https://app.example.com"
~~~

Status kỳ vọng **200 OK**, với:

~~~http
Access-Control-Allow-Origin: https://app.example.com
~~~

### 11.2. Actual request từ origin partner đến method local

~~~bash
curl -i "http://localhost:8080/api/demo/partner"   -H "Origin: https://partner.example.com"
~~~

Status kỳ vọng **200 OK**, với các header:

~~~http
Access-Control-Allow-Origin: https://partner.example.com
Access-Control-Expose-Headers: X-Global-Trace, X-Partner-Trace
~~~

Thứ tự hai exposed headers và cách format có thể khác nhau; nên so token header thay vì so thứ tự cứng.

### 11.3. Preflight cho header tùy chỉnh

~~~bash
curl -i -X OPTIONS   "http://localhost:8080/api/demo/partner"   -H "Origin: https://partner.example.com"   -H "Access-Control-Request-Method: GET"   -H "Access-Control-Request-Headers: X-Partner-Key"
~~~

Kết quả kỳ vọng status **200 OK** cùng `Access-Control-Allow-Origin: https://partner.example.com`, `Access-Control-Allow-Headers` chứa `X-Partner-Key`, và `Access-Control-Max-Age: 1200`. Đây là **preflight**; business method `partner()` không cần chạy để trả response OPTIONS.

### 11.4. Origin không được phép

~~~bash
curl -i -X OPTIONS   "http://localhost:8080/api/demo/global"   -H "Origin: https://partner.example.com"   -H "Access-Control-Request-Method: GET"
~~~

Với `DefaultCorsProcessor` và cấu hình trên, status thường **403 Forbidden**. `curl` vẫn đọc response bất kể CORS; trình duyệt chặn phía script theo cơ chế CORS.

Trên Windows PowerShell, dùng `curl.exe`, tránh alias `curl` và xử lý line continuation theo shell. Các dòng trên dùng `\` của Linux/macOS/Git Bash.

## 12. Tích hợp Spring Security: CORS cần chạy trước authentication

Khi ứng dụng có **Spring Security 6.x** (thường đi với Boot 3.x), preflight OPTIONS thông thường **không mang session cookie**. Nếu security filter yêu cầu authentication trước khi xử lý CORS, browser có thể thấy OPTIONS bị trả 401/403 và không bao giờ gửi actual request.

Spring Security cung cấp hỗ trợ CORS trong security filter chain. Nếu dùng cấu hình MVC `WebMvcConfigurer` và không tự khai báo `CorsConfigurationSource`, có thể cho Security dùng cấu hình của MVC:

~~~java
@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll());
        return http.build();
    }
}
~~~

**Đây là class minh họa cho project có thêm dependency `spring-boot-starter-security`**, cần import `@Configuration`, `@Bean`, `SecurityFilterChain`, `HttpSecurity`, `Customizer`. Authentication provider/login/session strategy cần được cấu hình phù hợp với ứng dụng thật. Đừng sao chép code này vào demo phần 9 nếu chỉ muốn kiểm thử CORS thuần MVC.

Nếu ứng dụng cần một `CorsConfigurationSource` riêng, có thể đăng ký `UrlBasedCorsConfigurationSource` và cho Security dùng nguồn đó. Nhưng **không** cấu hình nhiều `CorsFilter`/nguồn CORS khác nhau một cách không chủ đích: response có thể có header CORS trùng hoặc chính sách ở Security/filter không tương ứng với annotation method.

### Lựa chọn đường tích hợp

| Kiến trúc | Cách bắt đầu |
| --- | --- |
| Spring MVC thuần, không Security | `@CrossOrigin` và/hoặc `WebMvcConfigurer` |
| Boot 3 + Spring Security 6 và MVC CORS đã cấu hình | `http.cors(Customizer.withDefaults())` dùng MVC khi phù hợp |
| Security nhiều filter chains, policy khác nhau | Chỉ định `CorsConfigurationSource` tương ứng từng chain |
| CORS cần xử lý trước MVC hoặc cho endpoint không qua handler | `CorsFilter`/gateway với ownership rõ |
| Reverse proxy hoặc API gateway sở hữu CORS | Cấu hình ở gateway và tránh duplicate/inconsistent policy tại ứng dụng |

Dù Spring Security xử lý preflight đúng, **actual request vẫn phải thỏa authentication và authorization**. Việc preflight OK không cho phép user bỏ qua security.

## 13. Credentialed requests, cookie SameSite và CSRF

Frontend có thể gọi API kèm cookie khi đúng policy:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}
const user = await response.json();
~~~

Để browser cho script đọc credentialed CORS response, backend cần trả **origin cụ thể** và `Access-Control-Allow-Credentials: true`. Thêm `credentials: "include"` **không** làm cookie bị browser cấm tự nhiên xuất hiện:
- Cookie còn bị giới hạn bởi `Domain`, `Path`, `Secure`, expiry và `SameSite`.
- Một số browser chặn third-party cookies và có partitioning/tracking protection.
- Cross-origin nhưng same-site có hành vi cookie khác cross-site.
- Preflight không phải một request được ủy quyền chỉ nhờ client muốn gửi credentials.

**SameSite** giới hạn việc browser gửi cookie theo quan hệ site. **CORS** giới hạn khả năng JavaScript cross-origin tương tác/đọc response theo chính sách server. **CSRF** là vấn đề request giả mạo khi browser có thể tự gửi cookie auth. CORS **không thay thế CSRF token**, cũng không chặn mọi HTML form hoặc điều hướng cross-site có side effect. Với cookie-based authentication, dùng CSRF protection phù hợp, phân quyền từng operation và tuân thủ safe method semantics.

**Origin allowlist phải gắn với trust boundary:** nếu bạn cho phép credentialed CORS từ một origin do bên thứ ba điều khiển, script tại origin đó có thể truy cập dữ liệu mà credentialed user được phép và CORS expose. Không thêm một origin chưa được kiểm soát chỉ vì nó thuộc cùng tổ chức trên danh nghĩa.

## 14. Khi combine làm chính sách rộng hơn dự kiến

### 14.1. Global quá rộng

~~~java
registry.addMapping("/**")
        .allowedOrigins("*")
        .allowedMethods("*");
~~~

Đây là cấu hình **minh họa phản diện** cho ứng dụng có dữ liệu riêng tư. Nếu sau đó một method gắn `@CrossOrigin(origins="https://trusted.example.com")`, bạn không được giả định endpoint chỉ còn cho trusted origin; list combine có thể giữ quyền cho mọi origin.

**Cách sửa:** dùng policy global đủ hẹp và tách route public/private; tránh `**` nếu chỉ `/api/public/**` cần CORS mở.

### 14.2. Local bật credentials ngoài ý định global

~~~java
@CrossOrigin(
        origins = "https://partner.example.com",
        allowCredentials = "true")
@GetMapping("/private")
public SecretView privateData() {
    // ...
}
~~~

Đây là **handler minh họa không độc lập** và cần authentication/authorization. `allowCredentials` là scalar, local explicit có thể override global. Nếu global origins rộng, sự kết hợp có thể trở nên không hợp lệ hoặc nguy hiểm. Kiểm tra effective CorsConfiguration và test không cho origin ngoài allowlist nhận dữ liệu private.

### 14.3. Wildcard headers và methods

Nếu cấu hình cho phép `allowedHeaders("*")`, Spring có thể phản ánh những request header cụ thể trong preflight response, đặc biệt khi credentials được bật; không được hiểu mọi header đều tự nhiên an toàn. Header như `Authorization`, `X-Admin-Key` cần chính sách ứng dụng và xác thực riêng.

`allowedMethods("*")` cũng không tự bảo đảm controller nhận mọi HTTP method, nhưng khiến CORS gate rộng hơn cần thiết. Trong API có mutating methods, chỉ cho phép những method thực sự cần.

### 14.4. Trộn `CorsFilter`, `@CrossOrigin` và gateway

Một reverse proxy có thể thêm ACAO `*` trong khi Spring MVC trả ACAO origin cụ thể. Browser có thể coi response có **nhiều Access-Control-Allow-Origin** là không hợp lệ. Không tự sửa bằng cách add thêm header tại controller; cần xác định **một tầng chủ sở hữu** chính sách CORS hoặc cấu hình nhất quán, tránh trùng.

## 15. CORS không thay authorization: minh họa đe dọa

Giả sử API `GET /api/admin/reports` trả báo cáo nhạy cảm. Nếu chỉ cấu hình CORS để cho origin nội bộ mà **không** yêu cầu role, một người dùng có thể gọi endpoint trực tiếp qua HTTP client. CORS chỉ là browser permission, không phải ACL.

Ngược lại, API đã có authentication vẫn có thể bị truy cập cross-origin từ script ở origin được cho phép. Nếu `allowCredentials(true)` và attacker kiểm soát một origin nằm trong allowlist, attacker có thể lợi dụng khả năng đọc response theo quyền người dùng bị đăng nhập. Vì vậy chọn origin là một phần của threat modeling.

Bảo vệ đúng cần kết hợp:
1. Authentication và authorization ở server.
2. CORS allowlist tối thiểu cho frontend thật.
3. CSRF protection khi auth dựa vào cookie và các thao tác thay đổi trạng thái.
4. Cookie flags `Secure`, `HttpOnly`, `SameSite` theo use case.
5. Hạn chế XSS trong frontend, vì script chạy tại origin đáng tin có thể dùng chính quyền CORS của origin đó.
6. Logging/tracing không làm lộ access token, session cookie hoặc dữ liệu nhạy cảm.

## 16. Khi gặp lỗi CORS: quy trình kiểm tra

Đừng chỉ dựa vào dòng console “blocked by CORS policy”. Cần xem **Network panel** và đối chiếu các lớp:

| Hiện tượng | Nguyên nhân có thể | Hướng xác minh |
| --- | --- | --- |
| OPTIONS trả 401/403 trước handler | Spring Security/filter chặn preflight | Cấu hình `http.cors(...)`, thứ tự filter, logs |
| OPTIONS 403 Invalid CORS request | Origin/method/headers không được cấp | Đối chiếu effective config sau combine |
| GET 200 nhưng JS không đọc được body | Thiếu `Access-Control-Allow-Origin`, credentials mismatch, CORS header trùng | Inspect actual response headers |
| API được dùng từ Postman nhưng browser lỗi | HTTP client không thực thi same-origin policy của browser | Gửi `Origin` và preflight để chẩn đoán server |
| Cookie không gửi | `credentials`, SameSite, Secure, Domain/Path, third-party policy | DevTools Cookies và Request Headers |
| `Access-Control-Allow-Origin: *` với credentials | Tổ hợp bị browser từ chối | Dùng allowlist origin cụ thể và ACAC true |
| Request header X-Token bị từ chối | Không nằm trong `allowedHeaders` hoặc preflight mismatch | Xem `Access-Control-Request-Headers` |
| JS không đọc được `X-Request-Id` | Chưa có `exposedHeaders` | Set `Access-Control-Expose-Headers` |
| Policy local “không thu hẹp” global | Combine origin/method/header theo union | Xem toàn cục + local, thu hẹp global |
| Chỉ production bị lỗi | Gateway/CDN thêm/trừ header, proxy rewrite, HTTPS redirect | So response tại backend và gateway |
| Cache trả ACAO của origin khác | CDN bỏ qua `Vary: Origin` | Cấu hình cache key/Vary đúng |
| Server trả redirect trong preflight | HTTP→HTTPS hoặc login redirect, browser xử lý khó thống nhất | Dùng URL HTTPS/API route đúng trước, xử lý auth sau CORS |
| Origin đúng nhưng port sai | Origin gồm cả scheme, host và port | So header Origin chính xác, không chỉ hostname |

### Debug bảy bước

1. Mở DevTools → **Network** → tìm OPTIONS preflight và actual request; so Origin, method, custom headers.
2. Kiểm tra response của preflight: status, ACAO, Allow-Methods, Allow-Headers, Max-Age. 401/403 có thể đến từ security/gateway khác Spring MVC.
3. Kiểm tra response actual: ACAO, ACAC, exposed headers và Vary. Xác minh không có nhiều ACAO trái nhau.
4. Đọc global path mapping `/api/**`, class-level/method-level `@CrossOrigin`, combine rules và cấu hình Security.
5. Kiểm tra frontend `fetch`: `credentials`, URL, method, Content-Type, headers, cookie policy và redirect.
6. Nếu sau proxy/CDN mới lỗi, gọi trực tiếp backend (trong môi trường được phép) và so headers với gateway.
7. Viết MockMvc tests cho **allowed origin**, **disallowed origin**, preflight **method/header**, credentials và **cấu hình kết hợp** trước khi triển khai lại.

**Không nên** xử lý bằng `@CrossOrigin(origins = "*")` trên toàn bộ controller hoặc bằng cách vô hiệu Spring Security CORS/CSRF. Các thay đổi đó có thể làm browser ngừng báo lỗi nhưng mở rộng bề mặt tấn công.

## 17. Câu hỏi ôn tập

**1. `@CrossOrigin(origins="https://partner.example.com")` đặt trên method có xóa danh sách origin toàn cục không?**

Không mặc định. Spring MVC 6.x kết hợp các danh sách origins theo hướng cộng gộp. Nếu global cho `app.example.com`, method có thể cho cả app và partner.

**2. Thuộc tính `maxAge` giữa global và local được kết hợp thế nào?**

Đây là scalar property: nếu local khai báo non-null thì local override global. Global 600 + local 1200 cho method → preflight maxAge 1200.

**3. Tại sao preflight OPTIONS thường không có session cookie?**

Preflight là bước kiểm tra chính sách browser, không tự gửi credential như một actual authenticated request. Security phải cho CORS được xử lý trước auth khi áp dụng.

**4. CORS có bảo vệ được API khi gọi từ curl không?**

Không. curl không thực thi chính sách same-origin của browser. API phải bảo vệ bằng auth, authorization và business validations.

**5. `allowedHeaders` khác `exposedHeaders` ở đâu?**

`allowedHeaders` kiểm soát request headers browser được gửi qua preflight; `exposedHeaders` cho phép JS đọc những response headers bổ sung từ actual response.

**6. Khi dùng cookie qua cross-origin fetch cần những yếu tố nào?**

Frontend `credentials` thích hợp, server ACAO origin cụ thể + ACAC true, cookie Domain/Path/Secure/SameSite đủ điều kiện, browser không chặn, và CSRF/authorization đúng thiết kế.

**7. `allowedOriginPatterns` có cho phép dùng wildcard cùng credentials?**

Có thể, vì với pattern khớp, Spring trả origin thực tế chứ không phải `*"`. Nhưng pattern quá rộng vẫn nguy hiểm và phải giới hạn trust boundary.

**8. Cấu hình global origins `*"` có thể được local origins cụ thể thu hẹp không?**

Không được giả định. Hãy sửa global policy, tách scope routes và kiểm thử effective config thay vì hy vọng local annotation sẽ đóng vai trò deny rule.

## 18. Checklist áp dụng thực tế

1. Liệt kê frontend origins thực tế theo **scheme + host + port**. Chỉ mở origin cần thiết.
2. Với API public và private, tách rõ URL patterns; không đặt wildcard global rồi cố thu hẹp bằng local.
3. Dùng `@CrossOrigin` cho ngoại lệ rõ ràng, hoặc cấu hình `WebMvcConfigurer` cho policy nhất quán. Khi dùng cả hai, review **combine**.
4. Ghi nhớ list-valued properties thường cộng gộp, scalar local non-null ghi đè global.
5. Chỉ bật `allowCredentials(true)` khi thực sự cần; không dùng `allowedOrigins("*")` với credentials.
6. Khi dùng Spring Security, xử lý CORS preflight trước authentication; tránh cấu hình nhiều filter/gateway khác nhau tạo header trùng.
7. Đặt `allowedMethods`/`allowedHeaders` tối thiểu, `exposedHeaders` chỉ cho những response headers frontend cần đọc.
8. Kiểm soát CSRF, cookie và XSS độc lập; CORS không phải xác thực hay phân quyền.
9. Test actual request và preflight ở cả origin hợp lệ/không hợp lệ; kiểm tra maxAge, exposed headers, credentials và Vary.
10. Kiểm tra HTTPS, proxy/CDN và browser integration, không chỉ MockMvc hay Postman.

## Nguồn chính thức

- [Spring Framework 6.2 — CORS trong Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-cors.html)
- [Spring Framework 6.2 — `@CrossOrigin` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/CrossOrigin.html)
- [Spring Framework 6.2 — `CorsConfiguration#combine` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/CorsConfiguration.html)
- [Spring Security 6.5 — Servlet CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — HTTP Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin)
- [OWASP — Cross Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
