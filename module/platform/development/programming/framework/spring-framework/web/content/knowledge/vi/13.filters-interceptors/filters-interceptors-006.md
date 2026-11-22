# CharacterEncodingFilter, FormContentFilter và HiddenHttpMethodFilter trong Spring MVC

## 1. Ba Servlet Filter xử lý ba vấn đề khác nhau

Trong Spring MVC **Servlet stack**, dữ liệu từ client không đi thẳng tới controller. Trước `DispatcherServlet`, một chuỗi `jakarta.servlet.Filter` có thể điều chỉnh encoding, bọc request, thêm thông tin và thậm chí thay đổi HTTP method mà code phía sau nhìn thấy.

Ba filter thuộc package `org.springframework.web.filter` giải quyết ba vấn đề riêng:

| Filter | Vấn đề nó giải quyết | Tác động cốt lõi |
| --- | --- | --- |
| **`CharacterEncodingFilter`** | Dữ liệu text/form bị giải mã sai vì request/response charset chưa được thiết lập phù hợp | Gọi `setCharacterEncoding` cho request và có thể cho response; cấu hình `forceRequestEncoding`/`forceResponseEncoding` |
| **`FormContentFilter`** | Servlet API chỉ yêu cầu cung cấp form parameters theo `getParameter*` đối với POST; còn PUT/PATCH/DELETE với body form-urlencoded có thể không bind được | Đọc body `application/x-www-form-urlencoded` của PUT/PATCH/DELETE rồi bọc request để lộ form fields qua `getParameter*` |
| **`HiddenHttpMethodFilter`** | HTML form trình duyệt gửi GET/POST, trong khi handler Spring muốn `@PutMapping`, `@PatchMapping` hoặc `@DeleteMapping` | Với POST chứa form parameter `_method=PUT/PATCH/DELETE`, bọc request để `getMethod()` trả method được yêu cầu |

**Một filter không thay thế hai filter còn lại.** Sửa encoding không tự làm PUT body thành Servlet parameters; đọc PUT form body không tự đổi method; đổi POST thành DELETE không làm việc kiểm tra authorization/CSRF trở nên không cần thiết.

Ví dụ ba request:

```http
POST /demo/form HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

text=Ph%E1%BB%9F
```

```http
PUT /demo/form HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

text=Ph%E1%BB%9F
```

```http
POST /demo/items/7 HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

_method=DELETE
```

Trong ứng dụng demo ở phần 8:

- Request thứ nhất đi tới `@PostMapping` với `text="Phở"`. Charset request phải được xác định **trước khi Servlet container đọc form parameters**.
- Request thứ hai đi tới `@PutMapping` với `text="Phở"` nhờ `FormContentFilter` hỗ trợ Servlet-style `@RequestParam` từ PUT body.
- Request thứ ba **vẫn là POST trên đường truyền HTTP**, nhưng `HiddenHttpMethodFilter` bọc request và phần MVC phía sau có thể thấy method DELETE để chọn `@DeleteMapping`.

Bài tập trung vào **Spring Framework 6.x/Spring Boot 3.x, Java 17+, Servlet MVC**; có giải thích các khác biệt với Boot 2 và 4. Với Spring WebFlux/reactive stack, không dùng các Servlet filters trên như một phần của `WebFilter` chain.

## 2. Chúng nằm ở đâu trong quá trình xử lý HTTP?

```text
Client gửi bytes HTTP
        |
        v
Servlet container: request, response, FilterChain
        |
        +--> CharacterEncodingFilter
        |      đặt request/response charset theo policy
        |
        +--> FormContentFilter
        |      PUT/PATCH/DELETE + application/x-www-form-urlencoded?
        |      parse body rồi wrap HttpServletRequest.getParameter*()
        |
        +--> HiddenHttpMethodFilter
        |      POST có _method=PUT/PATCH/DELETE?
        |      wrap HttpServletRequest.getMethod()
        |
        +--> các filter khác tùy app (logging, Security, CORS...)
        |
        v
DispatcherServlet
        |
        v
HandlerMapping chọn @PostMapping / @PutMapping / @DeleteMapping ...
        |
        v
HandlerAdapter:
  @RequestParam / @ModelAttribute -> đọc Servlet request parameters
  @RequestBody                -> dùng HttpMessageConverter khi phù hợp
        |
        v
Controller / View / ResponseEntity
        |
        v
Response đi ngược qua FilterChain
```

Đây là **sơ đồ chức năng**, không khẳng định mọi ứng dụng có chính xác ba filter theo cùng thứ tự và không có filter khác. Container chọn registrations, URL patterns, dispatcher types và order; Boot auto-configuration cung cấp mặc định tùy version/property. Với `HiddenHttpMethodFilter`, thứ tự tương đối với Spring Security và multipart processing có tác động lớn.

Điều không nên nhầm:

- `HttpServletRequest#getMethod()` là method Servlet API được các wrapper nhìn thấy. Hidden filter **không sửa gói HTTP đã gửi** và không biến một POST thành một DELETE trên đường truyền giữa browser và proxy.
- `request.getParameter("text")` lấy query/form parameters theo Servlet semantics; không đồng nghĩa đọc JSON body.
- `Content-Type` cho biết body đang dùng media type gì. `Accept` chỉ mô tả response representations mà client chấp nhận; không kích hoạt các filter nói trên.
- `@Valid` / `@Validated` thực hiện Bean Validation sau khi dữ liệu được bind; không phải chức năng của filter.
- `Filter` hoạt động ở lớp Servlet **trước** MVC; `HandlerInterceptor` chỉ được gọi trong phần chọn và thực thi handler MVC.

## 3. `CharacterEncodingFilter` hoạt động như thế nào?

Class: `org.springframework.web.filter.CharacterEncodingFilter`; kế thừa `OncePerRequestFilter`.

Servlet request parameters có thể là chuỗi đã được giải mã từ bytes HTTP. Nếu charset của input không được xác định đúng lúc, các ký tự như “Đắk Lắk”, “Phở”, “Hà Nội” có thể bị biến thành dấu hỏi hoặc ký tự mojibake.

Filter này cho phép định cấu hình:

- **`encoding`**: charset như `UTF-8`.
- **`forceRequestEncoding`**: áp đặt charset cho request, kể cả khi request đã chỉ định encoding khác.
- **`forceResponseEncoding`**: áp đặt charset cho response theo policy.
- **`forceEncoding`**: shortcut áp dụng việc force cho cả request và response trong API liên quan.

Ví dụ fragment Java cấu hình thủ công:

```java
import org.springframework.web.filter.CharacterEncodingFilter;

CharacterEncodingFilter filter = new CharacterEncodingFilter();
filter.setEncoding("UTF-8");
filter.setForceRequestEncoding(true);
filter.setForceResponseEncoding(false);
```

Fragment trên **chỉ tạo và cấu hình object**, chưa đăng ký vào Servlet container. Trong ứng dụng Spring Boot thông thường, ưu tiên properties do Boot quản lý để tránh đăng ký trùng.

### 3.1. Đặt encoding trước khi đọc parameter/body

Một lỗi thường gặp:

```java
String text = request.getParameter("text");
request.setCharacterEncoding("UTF-8"); // Có thể đã quá muộn.
```

Nếu container đã giải mã form parameter theo encoding sai, gọi `setCharacterEncoding` sau đó **không tự xây lại** chuỗi Java đã sai. Do vậy, `CharacterEncodingFilter` phải chạy trước một custom filter, controller hoặc Servlet component nào đó đọc request parameters/body.

Trong Spring Boot 3, filter quản lý encoding thường có order sớm. Nếu thêm custom filter đọc body và cố đặt ở `Ordered.HIGHEST_PRECEDENCE`, có nguy cơ chạy **trước filter encoding**. Hãy kiểm tra thứ tự filter thực tế bằng logs và integration test.

### 3.2. Force request không luôn là lựa chọn tương đương “chấp nhận mọi charset”

Ví dụ client ghi rõ:

```http
Content-Type: application/x-www-form-urlencoded; charset=ISO-8859-1
```

Nếu bạn cấu hình **force-request UTF-8**, request có thể bị đọc theo UTF-8 thay vì charset client khai báo. Điều này đúng khi API contract **bắt buộc UTF-8**, nhưng sai khi hệ thống cần hỗ trợ nhiều charset thật sự. Hãy công bố charset được chấp nhận thay vì bật “force” tùy tiện rồi gây biến dạng dữ liệu.

### 3.3. Request encoding và response encoding là hai quyết định

- Với form-urlencoded input, trọng tâm là **request charset trước khi parse**.
- Với HTML/text response, `response.setCharacterEncoding(...)` chỉ có ý nghĩa khi được áp dụng trước khi response body/headers bị commit và trước khi writer được sử dụng.
- Với JSON, Spring MVC sử dụng `HttpMessageConverter` (thường Jackson) và media type rules. `CharacterEncodingFilter` không thay thế JSON decoder hoặc việc chọn converter.
- URI path/query decoding, connector configuration, DB collation/charset, Java source file encoding và HTML meta charset là **những lớp khác**; filter này không tự sửa tất cả.

Khi debug tiếng Việt lỗi, kiểm tra cả bytes client thực gửi, `Content-Type`/charset, Servlet request decoding, filter order, converter, response charset và trình hiển thị của client.

## 4. `FormContentFilter` — giúp PUT/PATCH/DELETE đọc form parameters

Class: `org.springframework.web.filter.FormContentFilter`; kế thừa `OncePerRequestFilter`.

Theo Servlet specification, `getParameter*()` bắt buộc hỗ trợ parse `application/x-www-form-urlencoded` **cho POST** theo điều kiện hợp lệ. Không thể dựa vào mọi Servlet container để có cùng hành vi đối với PUT, PATCH, DELETE. `FormContentFilter` xử lý khoảng trống đó:

1. Nhận Servlet request trong filter chain.
2. Kiểm tra method là **PUT/PATCH/DELETE** và body có media type form-urlencoded phù hợp.
3. Dùng form HTTP message converter để đọc các key-value pairs.
4. Bọc `HttpServletRequest` để `getParameter`/`getParameterMap`/`getParameterNames`/`getParameterValues` thấy dữ liệu body như request parameters.
5. Chuyển request đã bọc đến MVC hoặc downstream filter.

Ví dụ:

```http
PATCH /api/products/7 HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

title=S%E1%BB%95+tay&quantity=2
```

Handler có thể đọc:

```java
@PatchMapping(
        path = "/api/products/{id}",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
String patch(
        @PathVariable long id,
        @RequestParam String title,
        @RequestParam int quantity) {

    return id + ":" + title + ":" + quantity;
}
```

Đây là fragment method trong controller với import `MediaType`/các MVC annotations. Nếu FormContentFilter được bật và request hợp lệ, các tham số dự kiến là `id=7`, `title="Sổ tay"`, `quantity=2`.

### 4.1. Filter này không làm gì?

- **Không đổi HTTP method.** PUT vẫn là PUT, PATCH vẫn là PATCH.
- **Không tự parse JSON thành form parameters.** Body `application/json` cần `@RequestBody`/JSON message converter.
- **Không bảo đảm mọi form type đều được hỗ trợ.** `multipart/form-data` cần multipart resolution riêng; không coi nó như `application/x-www-form-urlencoded`.
- **Không tự validate business logic.** `quantity=0` có thể bind thành int 0 nếu không có validation/rule khác.
- **Không bắt buộc nếu controller trực tiếp đọc body bằng cơ chế khác đã phù hợp.** Ví dụ `@RequestBody MultiValueMap<...>` có thể dùng message converter form phù hợp, nhưng đây là code path khác so với `@RequestParam`.

### 4.2. Query parameters và body parameters cùng tên

Ví dụ:

```http
PUT /api/products/7?title=from-query HTTP/1.1
Content-Type: application/x-www-form-urlencoded

title=from-body
```

Khi Servlet request wrapper kết hợp các nguồn parameters, đừng thiết kế hợp đồng phụ thuộc mơ hồ vào “giá trị nào thắng” hoặc “thứ tự values” cho cùng tên. Tốt hơn tránh trùng key hoặc quy định rõ vị trí: path ID trên URI, form fields chỉ trong body, pagination qua query.

### 4.3. InputStream có thể bị tiêu thụ

`FormContentFilter` phải đọc body để parse key-value data. Nếu filter khác hoặc controller về sau muốn đọc lại raw `ServletInputStream`, không nên mặc định body vẫn nguyên vẹn để đọc lần hai. Nếu ứng dụng bắt buộc inspect raw body cùng lúc với form binding, cần thiết kế wrapper/caching có kiểm soát và test trên container thật; **không log password, token hay dữ liệu nhạy cảm** chỉ để debug.

Đặt filter đọc body quá sớm hoặc chồng nhiều body-caching filters dễ làm parsing, request size và performance khác kỳ vọng.

## 5. `HiddenHttpMethodFilter` — giả lập PUT/PATCH/DELETE từ HTML POST

Class: `org.springframework.web.filter.HiddenHttpMethodFilter`; kế thừa `OncePerRequestFilter`.

HTML form tiêu chuẩn hỗ trợ gửi theo **GET hoặc POST**. Một RESTful MVC controller lại có thể muốn:

```java
@PutMapping("/products/{id}")
@PatchMapping("/products/{id}")
@DeleteMapping("/products/{id}")
```

Để nối hai cơ chế đó, HTML form có thể thực sự gửi POST, chứa một trường hidden:

```html
<form action="/demo/items/7" method="post">
  <input type="hidden" name="_method" value="DELETE">
  <button type="submit">Xóa</button>
</form>
```

Browser gửi:

```http
POST /demo/items/7 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_method=DELETE
```

`HiddenHttpMethodFilter` đọc request parameter `_method`, kiểm tra method được phép và bọc request. Các component **sau filter** (như `DispatcherServlet`) thấy `request.getMethod() == "DELETE"`, từ đó match `@DeleteMapping`.

**Chỉ ba method được phép override là PUT, DELETE và PATCH.** Đây không phải cơ chế cho client tùy ý biến POST thành GET/HEAD/OPTIONS/TRACE hoặc một method bất kỳ.

### 5.1. Cấu hình field tên khác `_method`

Mặc định field name là `_method` (`HiddenHttpMethodFilter.DEFAULT_METHOD_PARAM`). Có thể tùy chỉnh:

```java
HiddenHttpMethodFilter filter = new HiddenHttpMethodFilter();
filter.setMethodParam("_httpMethod");
```

Fragment này chỉ tạo object. Cần đăng ký filter đúng một lần; nếu đổi tên field, HTML phải gửi đúng tên mới. Trên Boot, nếu chỉ cần mặc định `_method` thì bật property tương ứng thường đơn giản hơn.

### 5.2. Vì sao chỉ xử lý POST?

Vì mục đích là hỗ trợ HTML form gửi **POST trên mạng** trong khi handler MVC muốn một method update/delete. Với một request native PUT/PATCH/DELETE, `HiddenHttpMethodFilter` **không cần thay method**.

Các filter downstream có thể thấy DELETE dù packet ban đầu là POST. Vì vậy, khi phân tích access logs ở reverse proxy và application logs, cần phân biệt **wire method** với **method đã được Servlet request wrapper trình bày**.

### 5.3. Hidden method không phải permission hoặc authorization

Client có thể tự gửi `_method=DELETE`, không cần nhấn vào nút của HTML view. Do đó:

- Phải có authentication, authorization, ownership checks riêng.
- Nếu dùng cookie authentication, phải bảo vệ request thay đổi state bằng CSRF policy phù hợp.
- Spring Security có thể dùng method-based matcher. Filter cần được sắp xếp và tích hợp sao cho lớp authorization nhìn thấy method đúng theo thiết kế.
- Không coi việc nút DELETE chỉ xuất hiện với admin trong template là bảo vệ server-side.
- Không ghi hoặc thực thi xóa chỉ vì key `_method` tồn tại; request phải đi qua toàn bộ MVC/security/business validation pipeline.

## 6. Cấu hình mặc định trong Spring Boot 3.x

**Cần phân biệt class của Spring Framework với auto-configuration của Spring Boot.** Việc một filter tồn tại trong `spring-web` không có nghĩa Boot đã bật filter đó trong mọi app.

Với **Spring Boot 3.5** trên Servlet MVC, tài liệu properties/autoconfiguration cho thấy:

| Thành phần | Boot 3.5 thường làm gì? | Property |
| --- | --- | --- |
| `CharacterEncodingFilter` | Boot autoconfigure khi Servlet web app phù hợp và encoding support bật | `server.servlet.encoding.enabled`, `server.servlet.encoding.charset`, `server.servlet.encoding.force-*` |
| `FormContentFilter` | **Bật theo mặc định** nếu điều kiện auto-configuration và classpath phù hợp | `spring.mvc.formcontent.filter.enabled=true` |
| `HiddenHttpMethodFilter` | **Tắt theo mặc định**, phải bật nếu app dùng HTML `_method` | `spring.mvc.hiddenmethod.filter.enabled=false` |

Một cấu hình minh họa cho project học tập Boot 3:

```properties
# src/main/resources/application.properties
server.servlet.encoding.enabled=true
server.servlet.encoding.charset=UTF-8
server.servlet.encoding.force-request=true

spring.mvc.formcontent.filter.enabled=true
spring.mvc.hiddenmethod.filter.enabled=true
```

- `CharacterEncodingFilter` nhận charset UTF-8 trước khi form parameter parsing (với registration order phù hợp).
- `FormContentFilter` được Boot cấu hình cho việc đọc form-urlencoded body trên PUT/PATCH/DELETE.
- `HiddenHttpMethodFilter` bật để HTML form POST `_method=...` vào các endpoints method tương ứng.
- Đây là **cấu hình chọn cho bài demo**, không phải lời khuyên mọi API đều cần bật hidden-method override. Nếu API chỉ nhận JSON với native HTTP PUT/DELETE từ mobile/SPA, thường không cần `HiddenHttpMethodFilter`.
- `force-request=true` thể hiện contract ví dụ chỉ dùng UTF-8. Với một dịch vụ chấp nhận nhiều charset khác nhau, cần thiết kế tương ứng.

**Nếu bạn muốn encoding response cũng được force**, Boot 3 có `server.servlet.encoding.force-response=true`; hãy cân nhắc loại nội dung được gửi, server/container và media type. Không thiết lập “force all” mặc định nếu client hợp lệ có charset khác.

### 6.1. Không đăng ký thủ công thêm lần nữa

Khi Boot đã tạo filter tương ứng, **đừng đồng thời tạo `@Bean CharacterEncodingFilter` / `FilterRegistrationBean` khác với cùng tác dụng** chỉ vì đọc được ví dụ trên Internet. Kết quả có thể là duplicate execution, request wrapping hai tầng, order khó dự đoán hoặc cấu hình một bean làm Boot auto-configuration back off không như bạn mong muốn.

Cách ưu tiên trong ứng dụng thông thường:

1. Chọn properties Boot phù hợp.
2. Kiểm tra registrations ở startup logs.
3. Dùng integration test xác nhận form binding và hidden override.
4. Chỉ tạo `FilterRegistrationBean` tùy chỉnh khi thực sự cần URL pattern/dispatcher types/order/constructor khác default.

### 6.2. Cách kiểm tra filter registrations

```properties
logging.level.web=debug
```

Trong Boot 3, log ở web group thường cung cấp thông tin filter registrations, URL patterns và order khi startup. Với nhiều filters đã được auto-configure (encoding, request wrappers, Spring Security, observation...), thứ tự thực tế **không chỉ gồm ba filter** của bài. Kiểm tra trong môi trường test riêng để không bật DEBUG gây lộ request metadata nhạy cảm ở production.

## 7. Một ví dụ chạy được: Java 17 + Spring Boot 3.5

Ứng dụng demo minh họa đồng thời:

- POST form-urlencoded với text tiếng Việt.
- PUT form-urlencoded mà `@RequestParam` vẫn nhận field từ body.
- PATCH form-urlencoded tương tự.
- HTML POST với `_method=DELETE` được handler `@DeleteMapping` nhận.

**Baseline:** Java 17+, Spring Boot **3.5.x**, Spring Framework 6.2.x, embedded Servlet MVC (Tomcat mặc định trong starter web). Ví dụ không dùng Spring Security, database hoặc Thymeleaf để tránh tác động ngoài phạm vi; HTML demo là form thuần.

### 7.1. Gradle dependencies

Trong project đã có Spring Boot Gradle plugin và repositories/dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **fragment `build.gradle`**. Project cần được tạo/cấu hình qua Spring Initializr hoặc build file Spring Boot chuẩn. Mẫu không có dependency Spring Security; trong app thật, nếu đã có Spring Security cần cấu hình auth/CSRF/test tương ứng.

### 7.2. Properties

Tạo **`src/main/resources/application.properties`**:

```properties
server.servlet.encoding.charset=UTF-8
server.servlet.encoding.force-request=true
spring.mvc.formcontent.filter.enabled=true
spring.mvc.hiddenmethod.filter.enabled=true
```

Không thêm các bean `CharacterEncodingFilter`, `FormContentFilter` hay `HiddenHttpMethodFilter` thủ công trong demo này. Để Boot thực hiện auto-registration theo config.

### 7.3. Controller Java

Tạo **`src/main/java/demo/builtinfilters/BuiltinFiltersApplication.java`**:

```java
package demo.builtinfilters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BuiltinFiltersApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuiltinFiltersApplication.class, args);
    }
}

@RestController
@RequestMapping("/demo")
class FormDemoController {

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    String post(@RequestParam("text") String text) {
        return "POST:" + text;
    }

    @PutMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    String put(@RequestParam("text") String text) {
        return "PUT:" + text;
    }

    @PatchMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    String patch(@RequestParam("text") String text) {
        return "PATCH:" + text;
    }

    @DeleteMapping(
            path = "/items/{id}",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String delete(@PathVariable long id) {
        // Chỉ mô phỏng; ứng dụng thật phải kiểm tra auth và xóa DB.
        return "DELETE:" + id;
    }
}
```

**Mã có thể biên dịch với baseline đã ghi**: file chỉ có một `public` class là `BuiltinFiltersApplication`; `FormDemoController` không public nên đặt cùng file hợp lệ. Controller được component scan từ package `demo.builtinfilters`.

Các endpoints chỉ trả text để tập trung quan sát Servlet filtering, không dùng Jackson, persistence hoặc Bean Validation. Response body `POST:Phở` chứng minh decoding của form; `PUT:Phở` chứng minh GET/POST không phải method duy nhất có thể lấy `@RequestParam` từ form body sau khi có FormContentFilter; `DELETE:7` chứng minh method override.

### 7.4. Chạy và gửi curl

Khởi chạy qua Gradle wrapper:

```bash
./gradlew bootRun
```

**POST form-urlencoded với UTF-8:**

```bash
curl -i -X POST 'http://localhost:8080/demo/form' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data-urlencode 'text=Phở'
```

Response body dự kiến (status 200):

```text
POST:Phở
```

**PUT form-urlencoded:**

```bash
curl -i -X PUT 'http://localhost:8080/demo/form' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data-urlencode 'text=Phở'
```

Response body dự kiến:

```text
PUT:Phở
```

**PATCH form-urlencoded:**

```bash
curl -i -X PATCH 'http://localhost:8080/demo/form' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data-urlencode 'text=Phở'
```

Response body dự kiến:

```text
PATCH:Phở
```

**POST giả lập DELETE:**

```bash
curl -i -X POST 'http://localhost:8080/demo/items/7' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data '_method=DELETE'
```

Response body dự kiến:

```text
DELETE:7
```

Với ví dụ này, controller chỉ có `@DeleteMapping("/items/{id}")`, **không** có `@PostMapping` cho route đó. Nếu tắt `HiddenHttpMethodFilter`, POST `_method=DELETE` **không tự match** `@DeleteMapping` và thường nhận 405 Method Not Allowed, tùy app/error handling. Nếu tắt `FormContentFilter`, PUT/PATCH form parameters từ body có thể không được Servlet container expose như mong muốn, làm `@RequestParam("text")` không resolve và thường dẫn tới HTTP 400. Không phụ thuộc vào “tình cờ container có hỗ trợ” vì Servlet spec không bắt buộc trường hợp này.

Các ví dụ curl giả định server ở cổng 8080, không có filter/proxy/security custom. Header thật (date, length, charset...) có thể khác; điều đáng test là status, method được controller chọn và Unicode text đúng.

### 7.5. HTML form dùng `_method`

Mẫu HTML có thể đặt vào template hay trang tĩnh (đường URL cần phù hợp context path của app):

```html
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Xóa tài nguyên demo</title>
</head>
<body>
  <form method="post" action="/demo/items/7"
        accept-charset="UTF-8">
    <input type="hidden" name="_method" value="DELETE">
    <button type="submit">Xóa mục 7</button>
  </form>
</body>
</html>
```

Browser thực sự gửi POST. Với `HiddenHttpMethodFilter` đã bật, MVC có thể gọi method `@DeleteMapping`. Trong ứng dụng thực tế có cookie-based login, **phải thêm CSRF token theo cơ chế Spring Security đang dùng**, xác nhận quyền được phép xóa mục 7 và không dùng đường dẫn này như endpoint demo public.

## 8. Integration test: kiểm tra filter thật qua embedded server

Dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` thay vì chỉ unit test controller để xác minh Servlet container và Boot auto-registered filters thật sự tham gia. `MockMvc` có thể test MVC bindings và filters được gắn trong test context, nhưng không nhất thiết phản ánh tất cả registration/dispatcher ordering của embedded container.

Tạo **`src/test/java/demo/builtinfilters/BuiltinFiltersApplicationTests.java`**:

```java
package demo.builtinfilters;

import java.nio.charset.StandardCharsets;
import java.net.URLEncoder;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BuiltinFiltersApplicationTests {

    @Autowired
    TestRestTemplate http;

    private HttpHeaders formHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
        return headers;
    }

    @Test
    void postFormDecodesUtf8() {
        String value = URLEncoder.encode(
                "Phở", StandardCharsets.UTF_8);
        HttpEntity<String> request = new HttpEntity<>(
                "text=" + value, formHeaders());

        ResponseEntity<String> response = http.postForEntity(
                "/demo/form", request, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("POST:Phở", response.getBody());
    }

    @Test
    void putFormBodyBecomesRequestParameter() {
        HttpEntity<String> request = new HttpEntity<>(
                "text=Notebook", formHeaders());

        ResponseEntity<String> response = http.exchange(
                "/demo/form", HttpMethod.PUT, request, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("PUT:Notebook", response.getBody());
    }

    @Test
    void patchFormBodyBecomesRequestParameter() {
        HttpEntity<String> request = new HttpEntity<>(
                "text=Notebook", formHeaders());

        ResponseEntity<String> response = http.exchange(
                "/demo/form", HttpMethod.PATCH, request, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("PATCH:Notebook", response.getBody());
    }

    @Test
    void hiddenMethodChangesPostToDeleteForMvc() {
        HttpEntity<String> request = new HttpEntity<>(
                "_method=DELETE", formHeaders());

        ResponseEntity<String> response = http.postForEntity(
                "/demo/items/7", request, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("DELETE:7", response.getBody());
    }

    @Test
    void postWithoutHiddenOverrideRemainsPost() {
        HttpEntity<String> request = new HttpEntity<>(
                "text=Notebook", formHeaders());

        ResponseEntity<String> response = http.postForEntity(
                "/demo/form", request, String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("POST:Notebook", response.getBody());
    }
}
```

Chạy:

```bash
./gradlew test
```

**Kỳ vọng các test này phản ánh hành vi nêu trên ở baseline Boot 3.5 với filter config được bật.** Tuy nhiên `PATCH` là điểm cần lưu ý: `TestRestTemplate` dùng request factory của HTTP client hiện có; một số cấu hình `RestTemplate`/`HttpURLConnection` **không hỗ trợ HTTP PATCH**. Nếu test PATCH thất bại với lỗi `Invalid HTTP method: PATCH` **trước khi request tới server**, đó là giới hạn **HTTP client của test**, không chứng minh FormContentFilter hoặc controller sai. Để kiểm thử PATCH bằng HTTP thật, cấu hình `TestRestTemplate` dùng request factory hỗ trợ PATCH (ví dụ Apache HttpComponents có dependency phù hợp), hoặc dùng `curl -X PATCH` như trên. Đừng ghi nhận test PATCH “PASS” nếu chưa kiểm tra client có gửi request thật.

**Lưu ý quan trọng để bộ test runnable:** nếu môi trường test không có HTTP client hỗ trợ PATCH, **không coi năm test phía trên chắc chắn pass nguyên xi**. Có thể thay phương thức test PATCH bằng request qua Java `java.net.http.HttpClient` (Java 17) như phần tiếp theo, vì client này hỗ trợ method PATCH tùy ý.

### 8.1. PATCH qua Java 17 HttpClient (không cần HttpComponents)

Trong test class nói trên, nếu muốn loại bỏ phụ thuộc vào PATCH support của `TestRestTemplate`, thêm field port và thay **duy nhất test method `patchFormBodyBecomesRequestParameter`** bằng:

```java
@org.springframework.boot.test.web.server.LocalServerPort
int port;

@Test
void patchFormBodyBecomesRequestParameter() throws Exception {
    java.net.http.HttpClient client =
            java.net.http.HttpClient.newHttpClient();

    java.net.http.HttpRequest request =
            java.net.http.HttpRequest.newBuilder()
                .uri(java.net.URI.create(
                        "http://localhost:" + port + "/demo/form"))
                .header("Content-Type",
                        "application/x-www-form-urlencoded; charset=UTF-8")
                .method(
                        "PATCH",
                        java.net.http.HttpRequest.BodyPublishers
                                .ofString("text=Notebook"))
                .build();

    java.net.http.HttpResponse<String> response =
            client.send(
                    request,
                    java.net.http.HttpResponse.BodyHandlers.ofString());

    assertEquals(200, response.statusCode());
    assertEquals("PATCH:Notebook", response.body());
}
```

Đoạn này là **fragment thay thế một method trong test class**, dùng Java 17 HttpClient và `LocalServerPort`, không bổ sung như method trùng tên trong cùng class. Cách thay thế này làm test PATCH gửi request tới **embedded server thật**, không lệ thuộc vào `RestTemplate` request factory. Nếu muốn áp dụng ngay, có thể dùng giải pháp `HttpClient` cho cả năm test và chỉ dùng `TestRestTemplate` cho các method khác.

**Các test trong bài chỉ mô tả kết quả dự kiến và chưa được thực thi**; muốn khẳng định pass, chạy `./gradlew test` trong project Spring Boot đã thiết lập.

## 9. Cấu hình filter thủ công khi thực sự cần kiểm soát thứ tự

Nếu ứng dụng không muốn dùng auto-registration mà cần order và dispatcher mapping rõ, có thể tạo `FilterRegistrationBean`. **Đây là phương án thay thế cho Boot property-based auto-configuration ở phần 7, không được bật đồng thời nguyên xi**.

Ví dụ fragment (đặt bên trong một class `@Configuration` trong Boot 3):

```java
@Bean
FilterRegistrationBean<CharacterEncodingFilter> encodingRegistration() {
    CharacterEncodingFilter filter = new CharacterEncodingFilter(
            "UTF-8", true);
    FilterRegistrationBean<CharacterEncodingFilter> bean =
            new FilterRegistrationBean<>(filter);
    bean.setName("myEncodingFilter");
    bean.setOrder(10);
    bean.addUrlPatterns("/*");
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    return bean;
}

@Bean
FilterRegistrationBean<FormContentFilter> formRegistration() {
    FilterRegistrationBean<FormContentFilter> bean =
            new FilterRegistrationBean<>(new FormContentFilter());
    bean.setName("myFormContentFilter");
    bean.setOrder(20);
    bean.addUrlPatterns("/*");
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    return bean;
}

@Bean
FilterRegistrationBean<HiddenHttpMethodFilter> hiddenMethodRegistration() {
    FilterRegistrationBean<HiddenHttpMethodFilter> bean =
            new FilterRegistrationBean<>(new HiddenHttpMethodFilter());
    bean.setName("myHiddenMethodFilter");
    bean.setOrder(30);
    bean.addUrlPatterns("/*");
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    return bean;
}
```

Đây là **fragment**, cần imports `org.springframework.boot.web.servlet.FilterRegistrationBean`, `org.springframework.web.filter.*`, `jakarta.servlet.DispatcherType` và `@Bean`. Nếu thực sự dùng ba registration này, cần **tắt hoặc loại bỏ auto-registration tương ứng** của Boot và kiểm tra rằng không có một servlet filter bean khác cùng chức năng:

```properties
# Chỉ là minh họa chế độ TỰ đăng ký, khác project demo phần 7.
server.servlet.encoding.enabled=false
spring.mvc.formcontent.filter.enabled=false
spring.mvc.hiddenmethod.filter.enabled=false
```

Thứ tự `10/20/30` chỉ nói lên **thứ tự tương đối giữa các registrations được Boot quản lý**, không đảm bảo encoding luôn chạy trước Spring Security hoặc mọi filter hạ tầng khác. Nếu cần filter đọc body, phải xem order của encoding filter thực tế trước đó. Với đăng ký thông qua `web.xml`/`@WebFilter` hoặc WAR ngoài container, cơ chế ordering còn theo Servlet specification/config khác; không dựa mù quáng vào số `setOrder` của Boot cho registrations không thuộc nó.

### 9.1. Tại sao phải xem Servlet DispatcherType?

`FilterRegistrationBean#setDispatcherTypes(DispatcherType.REQUEST)` ở ví dụ trên nghĩa là filter chạy cho **request dispatch ban đầu**; nó không tự tham gia `FORWARD`, `ERROR`, `ASYNC`, `INCLUDE`. Nếu filter cần hỗ trợ async/error, chọn dispatcher types có chủ đích và hiểu rằng cả ba filter kế thừa `OncePerRequestFilter`, mặc định có chính sách skip async/error. Không bật tất cả dispatcher types vô điều kiện chỉ vì có enum.

Với `HiddenHttpMethodFilter`, việc thay method một lần trong REQUEST trước khi MVC chọn handler thường là mục tiêu đủ rõ; không cần tự lặp lại method override trong ERROR dispatch. Với form data, tránh việc đọc body lần hai khi request đã bị wrapper xử lý và Servlet dispatch tiếp.

### 9.2. Multipart form và HiddenHttpMethodFilter

`HiddenHttpMethodFilter` phải đọc `_method` như request parameter, nên với POST `multipart/form-data` cần **multipart processing diễn ra trước nó** để field có thể được lấy theo cách filter dự kiến. Javadoc khuyến nghị `MultipartFilter` trước HiddenHttpMethodFilter khi dùng cách filter-based multipart resolution.

**Không kết luận rằng luôn phải thêm MultipartFilter trong Boot.** Trong các ứng dụng Spring MVC, multipart có thể được cấu hình để `DispatcherServlet` xử lý; khi HiddenHttpMethodFilter chạy trước DispatcherServlet, khả năng đọc multipart parameters tùy Servlet container và multipart config. Do đó cần integration test với **multipart POST + _method=PATCH/DELETE** trên đúng container, hoặc chọn form-urlencoded đơn giản cho hidden method.

Tránh kết hợp `MultipartFilter` với Servlet-specific multipart resolution không tương thích. Nếu custom order cần multipart trước hidden, xác định chính xác filter nào resolve multipart trong kiến trúc của bạn.

## 10. Spring Security, CSRF và HTTP method override

Khi bật `HiddenHttpMethodFilter`, security cần xem method đã được biến đổi trong Servlet request wrapper **nếu authorization policy dựa trên HTTP method**.

Một luồng mong muốn:

```text
Browser gửi POST /items/7 + _method=DELETE
      |
      +-- character encoding
      +-- parse form params khi cần
      +-- hidden method wrapper -> getMethod() = DELETE
      +-- Spring Security authentication/authorization/CSRF
      +-- DispatcherServlet -> @DeleteMapping
```

Đây là **sơ đồ yêu cầu thiết kế**, không phải thứ tự auto-reg chắc chắn trong mọi Boot/Security version. `Spring Security FilterChainProxy` nằm trong một Servlet filter registration riêng; nếu order khác, Security có thể xét POST trong khi MVC sau đó xét DELETE. Phải kiểm tra startup filter list hoặc security debug và test authorized/unauthorized requests.

**CSRF:** với các request sử dụng cookie session và thay đổi state, bảo vệ CSRF là yêu cầu quan trọng. HTML form method override không né CSRF. Spring Security có thể xử lý request parameter `_csrf`; bảo đảm hidden method filter, encoding/multipart và CSRF token processing cùng hoạt động trên request phù hợp. Nếu POST ban đầu có `_method=DELETE`, CSRF vẫn phải được xác minh theo policy của ứng dụng.

**Authorization:** đừng dựa vào việc UI chỉ render nút xóa cho admin. Client có thể tự gửi POST form hoặc DELETE native; server phải kiểm tra tài nguyên, identity và quyền thao tác.

### 10.1. Native DELETE và hidden DELETE khác gì?

| Khía cạnh | Native DELETE | POST + `_method=DELETE` |
| --- | --- | --- |
| HTTP method trên mạng | DELETE | POST |
| Servlet method sau hidden filter | DELETE | DELETE (nếu filter bật/mapping đúng) |
| Proxy/WAF/access logs phía trước | Thấy DELETE | Thấy POST |
| MVC handler | `@DeleteMapping` | `@DeleteMapping` |
| Browser HTML form không dùng JS | Không hỗ trợ method DELETE trực tiếp | Có thể dùng |
| Security/filter order | Cần áp dụng đúng | Đặc biệt cần đồng nhất method sau override |
| Caching, idempotency và retries | Theo semantics method HTTP gửi thật | Proxy/client thấy POST; không suy ra tính idempotent ở network |

Nếu API phục vụ SPA/mobile đã gửi native HTTP methods được, **thường không cần hidden method override**. Chỉ bật filter khi thực sự có HTML forms hoặc legacy clients cần pattern này.

## 11. Lỗi encoding: phân biệt form body, URL và response

### 11.1. Form-urlencoded có quy tắc percent-encoding

Với UTF-8, chuỗi `Phở` được mã hóa vào form-urlencoded body theo percent-encoded bytes. Ví dụ:

```text
Java String:       Phở
UTF-8 bytes:       50 68 E1 BB 9F
Form encoded:      Ph%E1%BB%9F
```

Khi nhận request đúng charset, Servlet/container và FormContentFilter (tùy method) khôi phục Java `String "Phở"`. Nếu bytes bị giải mã theo sai charset, text sẽ sai dù controller vẫn được gọi.

### 11.2. URL query/path không hoàn toàn do CharacterEncodingFilter quyết định

`/products?title=...` và `/products/{slug}` chịu ảnh hưởng URL percent-encoding, container connector settings và URI decoding policy. Ví dụ Tomcat có `server.tomcat.uri-encoding=UTF-8` trong cấu hình phù hợp. **Không** xem việc bật `CharacterEncodingFilter` là đã kiểm soát toàn bộ URL path/query decoding trong mọi Servlet container.

### 11.3. JSON không cần FormContentFilter

Client:

```http
PUT /api/products/7 HTTP/1.1
Content-Type: application/json

{"title":"Phở"}
```

Controller:

```java
@PutMapping("/api/products/{id}")
ResponseEntity<Void> update(
        @PathVariable long id,
        @RequestBody ProductUpdateRequest request) {

    // ...
}
```

Đây là fragment; `ProductUpdateRequest` phải định nghĩa trong project. Spring MVC đọc JSON bằng `HttpMessageConverter`, thường Jackson, **không** thông qua `FormContentFilter` hay `_method`.

Nếu endpoint chỉ nhận JSON, không bật form parsing/hidden override chỉ để “đảm bảo request được xử lý”. Cần chọn converter, validation và API contract đúng với JSON.

### 11.4. Response text mất dấu

Nếu input đúng nhưng output sai, kiểm tra response `Content-Type` charset, converter viết body (String converter, Thymeleaf, JSP, Jackson), Servlet response encoding và HTML/browser interpretation. `force-response=true` chỉ có tác dụng theo context và trước khi response committed; nó không sửa những byte đã ghi sai bởi code khác.

## 12. Các lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Khả năng cao | Hướng xác minh |
| --- | --- | --- |
| `Phở` thành ký tự lỗi | CharacterEncodingFilter chạy muộn, force policy sai hoặc request header/bytes không khớp | Log charset trước `getParameter` và kiểm tra body bytes bằng client thực |
| Form POST đọc được, PUT form-urlencoded lại thiếu `@RequestParam` | Chưa có FormContentFilter hoặc media type không phù hợp | Kiểm tra `spring.mvc.formcontent.filter.enabled` và content type |
| POST `_method=DELETE` trả 405 | Hidden filter chưa bật, field thiếu/sai tên, filter không map URL, hoặc method không nằm trong bộ cho phép | Bật property đúng Boot version, test request thật |
| POST hidden DELETE vào nhầm `@PostMapping` | Method wrapper chưa chạy trước MVC | Kiểm tra registration order và chain |
| POST `_method=PATCH` trả 415 | Handler PATCH `consumes` không khớp request body media type | Kiểm tra `Content-Type` là form-urlencoded và route |
| Multipart hidden method không hoạt động | Param `_method` chưa có khi filter chạy | Kiểm tra multipart resolution trước hidden filter và container |
| Cùng filter chạy hai lần | Auto-registration và manual registration đồng thời | Kiểm tra registrations và bean names |
| Security chặn request khác kỳ vọng | Security thấy method ở phase khác MVC hoặc thiếu auth/CSRF | Kiểm tra order, method-based matchers và CSRF |
| Body bị mất sau log filter | Một filter đọc `ServletInputStream` trước người xử lý chính | Thiết kế caching wrapper có kiểm soát |
| Dữ liệu form sai dù charset UTF-8 | HTML/client thực gửi encoding khác hoặc đã decode quá sớm | Xem raw bytes/headers và request charset |
| Lỗi chỉ khi deploy WAR | Filter ordering/config khác embedded container | Kiểm tra `web.xml`/Servlet registration thực tế |
| Tests xanh với MockMvc nhưng production sai | Test không tái hiện filter registration/container | Thêm RANDOM_PORT integration test |
| Hidden GET/HEAD không thay đổi method | HiddenHttpMethodFilter chỉ xét POST | Dùng native method hoặc thiết kế API khác |
| Có `_method=TRACE` mà không chọn TRACE handler | Filter chỉ hỗ trợ PUT/DELETE/PATCH | Không phụ thuộc override method bất kỳ |

**Chẩn đoán nên đi theo thứ tự:** raw HTTP request → filter registrations/URL/dispatcher mapping → encoding/filter order → wrapped method/params → Spring MVC handler mapping → binding/validation → response body/media type.

Với thông tin nhạy cảm như password, token, session ID và personal data, không bật log raw form body chỉ để debug.

## 13. Lựa chọn scope của filter và chi phí vận hành

Ba filter này kế thừa `OncePerRequestFilter`, nhưng “once” không đồng nghĩa chạy đúng một lần trong toàn bộ vòng đời ứng dụng hoặc mọi async/error dispatch. Mỗi Servlet request/dispatch có cách xử lý riêng. Khi filter map nhiều dispatcher types, cần xét cơ chế skip async/error của base class, tránh tự giả định mọi dispatch sẽ tiếp tục parse body hay override method.

Khi xử lý đồng thời:

- Servlet filters thường là **singleton instance** trong container và phục vụ nhiều requests trên nhiều threads.
- Không lưu mutable request-specific data ở fields của filter instance.
- Nếu dùng request attribute/ThreadLocal/MDC để quan sát method trước/sau override, cleanup trong `finally` để không leak data sang request tiếp.
- Không chỉnh lại encoding giữa request ở runtime bằng shared mutable filter config.
- Hạn chế đọc/lưu form body nhiều lần; áp giới hạn kích thước request qua Servlet/container, bảo vệ file upload riêng.

Về performance: encoding/method override thường nhẹ, còn form body parsing cần đọc và xử lý dữ liệu. Với app nhận payload lớn, phân biệt form body và raw JSON, thiết lập size limits và đo tác động thay vì bật toàn bộ custom wrappers.

## 14. Boot 2, Boot 3 và Boot 4: đừng dùng nhầm package/property

| Nền tảng | Servlet imports | Các filter Spring | Cấu hình cần xem |
| --- | --- | --- | --- |
| Spring Framework 5.x + Boot 2.x | `javax.servlet.*` | `CharacterEncodingFilter`, `FormContentFilter`, `HiddenHttpMethodFilter` trong `org.springframework.web.filter` | Properties theo đúng bản Boot 2, nhiều version dùng `server.servlet.encoding.*` và `spring.mvc.*.filter.enabled` |
| Spring Framework 6.x + Boot 3.x | **`jakarta.servlet.*`** | Các class filter cơ bản cùng package Spring; Boot 3.5 auto-configure như phần 6 | `server.servlet.encoding.*`, `spring.mvc.formcontent.filter.enabled`, `spring.mvc.hiddenmethod.filter.enabled` |
| Spring Framework 7.x + Boot 4.x | **`jakarta.servlet.*`** | Servlet Filter vẫn là layer web đúng, nhưng auto-config module/registration của Boot 4 thay đổi | Encoding được chuyển sang **`spring.servlet.encoding.*`**; kiểm tra metadata của webmvc auto-config khi tìm properties form/hidden |

**Chú ý thay đổi thực tế ở Boot 4:** `server.servlet.encoding.mapping.*` có thể vẫn dùng cho locale-to-charset mapping của **embedded Servlet container**, nhưng các properties cấu hình `CharacterEncodingFilter` được chuyển sang `spring.servlet.encoding.charset` / `spring.servlet.encoding.force-*`. Vì vậy hãy đọc đúng phần “Common Application Properties” của **Boot 4**; không copy nguyên `server.servlet.encoding.charset` từ Boot 3 và kết luận encoding mới đã được áp dụng.

Ví dụ **Boot 4** chỉ minh họa namespace encoding:

```properties
spring.servlet.encoding.charset=UTF-8
spring.servlet.encoding.force-request=true
```

Đây **không** phải đầy đủ cấu hình Boot 4 của bài demo; tập webmvc starters, tests và auto-config khác phải theo Spring Boot 4 BOM. Đừng trộn imports `javax.servlet.*` từ tutorial cũ vào Boot 3/4.

### Khi chạy trên Servlet container bên ngoài

Với WAR triển khai ngoài, filter có thể được đăng ký qua `web.xml`, Servlet annotations, `WebApplicationInitializer` hoặc container-specific configuration. Thứ tự đăng ký và dispatcher mappings có thể khác embedded Boot. Hãy xác minh thật thay vì coi property Boot hoặc `FilterRegistrationBean#setOrder` luôn là nguồn duy nhất kiểm soát mọi Servlet filter.

## 15. Checklist thực hành

- [ ] Đã xác định request là form-urlencoded, multipart hay JSON; không dùng một filter sai loại dữ liệu.
- [ ] `CharacterEncodingFilter` chạy trước thành phần đầu tiên đọc/parse form parameters.
- [ ] Charset client/server nhất quán; không force UTF-8 nếu contract thực sự cho phép encoding khác.
- [ ] `FormContentFilter` bật nếu cần nhận `@RequestParam`/`@ModelAttribute` từ PUT/PATCH/DELETE form body.
- [ ] `HiddenHttpMethodFilter` chỉ bật khi client dùng HTML POST + `_method`; bảo đảm giá trị chỉ PUT/PATCH/DELETE.
- [ ] Với multipart POST, `_method` có thể đọc được trước MVC handler; test trên container đích.
- [ ] Không đăng ký trùng filter qua Boot auto-config và `FilterRegistrationBean`/`@Component`/`web.xml`.
- [ ] Filter registration order, URL patterns và dispatcher types được xác minh bằng startup logs.
- [ ] Spring Security authorization/CSRF nhìn thấy method phù hợp và vẫn bảo vệ state-changing requests.
- [ ] Không sử dụng HiddenHttpMethodFilter để lách giới hạn reverse proxy hoặc policy HTTP methods một cách thiếu kiểm soát.
- [ ] Không đọc body hai lần khi filter, logger và controller cùng cần stream.
- [ ] Có HTTP integration tests trên container thật cho Unicode, PUT/PATCH form-urlencoded và hidden DELETE.
- [ ] Có negative tests khi tắt hidden filter, khi media type sai, khi field bắt buộc thiếu, và với request không được phép.
- [ ] Không log body/hidden fields chứa bí mật; kiểm soát request size.
- [ ] Khi nâng Boot version, xem lại namespace properties, imports và filter registration, không dựa vào ví dụ của major version cũ.

## 16. Bài tập tự kiểm tra

1. Một POST form-urlencoded chứa `name=Ph%E1%BB%9F` bị decode thành text sai, nhưng JSON cùng dữ liệu lại đúng. Hãy phân tích sự khác nhau giữa Servlet form parameters và JSON message converter, và vị trí CharacterEncodingFilter.
2. Vì sao `@RequestParam String name` trong `@PutMapping` có thể không có giá trị trên một Servlet container nếu tắt FormContentFilter, dù raw body có `name=An`?
3. Khi HTML form gửi POST với `_method=DELETE`, HTTP method nào được reverse proxy nhìn thấy? MVC downstream nhìn method nào khi HiddenHttpMethodFilter đã bật?
4. Cho ba filters Encoding, FormContent và Hidden, vì sao không đủ để chỉ chỉ định order mà còn phải xem URL mapping và dispatcher types?
5. Bật `spring.mvc.hiddenmethod.filter.enabled=true` trong Boot 3.5 nhưng POST `_method=DELETE` vẫn trả 405. Nêu ít nhất năm nguyên nhân ngoài việc property gõ sai.
6. Nếu custom security matcher bảo vệ mọi DELETE nhưng cho phép POST, và hidden-method filter chạy **sau** Security, rủi ro là gì? Hãy kiểm tra filter order và thiết kế lại.
7. Browser upload file bằng `multipart/form-data` kèm field `_method=PATCH`. Vì sao HiddenHttpMethodFilter có thể không đọc được field nếu multipart parsing chưa chạy? Nên test ở layer nào?
8. Gửi `PUT Content-Type: application/json` tới endpoint có `@RequestBody`. Vì sao FormContentFilter không phải giải pháp cho mọi lỗi parse JSON?
9. Trên Spring Boot 4, property `server.servlet.encoding.charset` từ Boot 3 không còn là namespace cấu hình chính của CharacterEncodingFilter. Tìm property tương ứng và kiểm chứng bằng test tiếng Việt.
10. Chạy unit test controller với MockMvc thấy `DELETE:7`, nhưng integration test với embedded container không pass. Những khác biệt filter registration/URL mapping/dispatcher type nào cần kiểm tra?
11. Thiết kế một test PATCH dùng Java 17 `HttpClient` thay cho request factory không hỗ trợ PATCH; chứng minh request thật đến controller với body form-urlencoded.
12. Trong app chỉ có SPA gửi JSON qua native PUT/DELETE, những filter nào thực sự cần? Giải thích vì sao nên giảm cấu hình không sử dụng.

## 17. Tài liệu chính thức

- [Spring Framework 6.2 — Servlet Filters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): vai trò filters; phần Form Data giải thích `FormContentFilter` trên PUT/PATCH/DELETE.
- [Spring Framework 6.2 — CharacterEncodingFilter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/filter/CharacterEncodingFilter.html): request/response encoding, force options.
- [Spring Framework 6.2 — FormContentFilter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/filter/FormContentFilter.html): parse form-urlencoded body và wrapper `getParameter*`.
- [Spring Framework 6.2 — HiddenHttpMethodFilter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/filter/HiddenHttpMethodFilter.html): `_method`, PUT/PATCH/DELETE và lưu ý multipart.
- [Spring Framework 6.2 — OncePerRequestFilter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): giới hạn “once” trong async/error/nested dispatch.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): mặc định của `spring.mvc.formcontent.filter.enabled` và `spring.mvc.hiddenmethod.filter.enabled`, encoding properties.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): auto-registration/order và character encoding.
- [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html): namespace `spring.servlet.encoding.*` và các thuộc tính cho Boot 4.
- [Spring Framework — MultipartFilter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/multipart/support/MultipartFilter.html): filter-based multipart resolution và tương tác với HiddenHttpMethodFilter.
- [Jakarta Servlet Specification 6.0](https://jakarta.ee/specifications/servlet/6.0/): Servlet request parameters, filters, dispatcher types và form processing.
