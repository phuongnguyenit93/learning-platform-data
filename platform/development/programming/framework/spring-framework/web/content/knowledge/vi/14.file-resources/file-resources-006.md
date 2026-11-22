# ResourceHandler, vị trí tài nguyên tĩnh và thứ tự ánh xạ trong Spring MVC

## 1. Vấn đề thực tế

Một dự án Spring Boot có các file:

```text
src/main/resources/static/css/site.css
src/main/resources/static/images/logo.svg
src/main/resources/templates/home.html
src/main/resources/manuals/intro.txt
```

Trình duyệt yêu cầu `GET /css/site.css`: Spring MVC cần tìm đúng file và trả CSS. Nhưng `GET /manuals/intro.txt` thường chưa hoạt động nếu bạn chỉ thêm thư mục `manuals` vào classpath. Còn `GET /products/42` nên chạy controller, ngay cả khi static resource handler mặc định của Spring Boot có URL pattern `/**`.

Từ ba tình huống đó, bài học giải đáp:

1. **ResourceHandler là gì?** URL pattern được ánh xạ sang `ResourceHttpRequestHandler` để tìm và phục vụ file tĩnh.
2. **Tài nguyên phải nằm ở đâu?** Những thư mục mặc định của Boot, đường dẫn classpath, đường dẫn servlet context, JAR/WAR và vị trí tự cấu hình.
3. **Thứ tự ánh xạ hoạt động thế nào?** `HandlerMapping` của controller thường ưu tiên trước resource handler mặc định; trong resource mappings, pattern cụ thể được chọn thay vì wildcard rộng.
4. **Khi nào dùng `WebMvcConfigurer#addResourceHandlers`, `spring.mvc.static-path-pattern`, `spring.web.resources.static-locations`, `spring.web.resources.add-mappings`?**
5. **Làm thế nào dùng caching, versioned URLs, conditional GET, content types, bảo mật?**
6. **Kiểm thử ra sao?** Viết Spring Boot 3/Java 17 có file tĩnh mặc định, thư mục riêng, route controller trùng URL với static file; dùng MockMvc xác nhận kết quả.

**Phạm vi:** Spring MVC trên Servlet stack, Spring Framework 6.x/Spring Boot 3.x, Java 17+. Cơ chế WebFlux dùng `ResourceWebHandler` và `WebFluxConfigurer`, **không** dùng `ResourceHttpRequestHandler` của Servlet MVC.

## 2. “Static resource” nghĩa gì?

Static resource là nội dung được trả về chủ yếu dưới dạng file/bytes thay vì chạy controller để dựng một tài liệu mới: CSS, JS, icon, hình ảnh, font, file PDF công khai, tài liệu tải xuống. “Tĩnh” **không có nghĩa** không có header HTTP động: Spring vẫn có thể tính `Last-Modified`, trả `304 Not Modified` hoặc áp dụng cache policy.

Ví dụ:

```http
GET /css/site.css HTTP/1.1
Host: localhost:8080
```

Phản hồi:

```http
HTTP/1.1 200 OK
Content-Type: text/css
Cache-Control: max-age=300

body { color: #123456; }
```

Phần status/content-type/header chính xác phụ thuộc cấu hình và tài nguyên, nhưng luồng chính là tìm file, mở stream và ghi nội dung. Client chỉ thấy **URL công khai**, không thấy hoặc không cần biết file nguồn nằm dưới `src/main/resources/static/`.

**Phân biệt ba khái niệm:**

- **Resource location**: thư mục nguồn như `classpath:/static/`. Đây là cấu hình phía server.
- **URL mapping pattern**: đường URL client yêu cầu như `/**` hoặc `/assets/**`.
- **Resource path**: phần còn lại sau URL pattern dùng để tìm file, ví dụ `css/site.css`.

Ví dụ cấu hình:

```java
registry.addResourceHandler("/files/**")
        .addResourceLocations("classpath:/downloadable/");
```

Client gọi `GET /files/guide.pdf` thì server tìm `classpath:/downloadable/guide.pdf`. Không tìm file ở `src/main/resources/static/files/guide.pdf` trừ khi thư mục ấy cũng nằm trong locations tương ứng.

## 3. Thành phần của Spring MVC resource pipeline

Một request thông thường:

```text
Client GET /assets/main.css
   │
   ▼
DispatcherServlet
   │
   ├── HandlerMapping: tìm handler cho URL
   │     ├── Controller @GetMapping(...)
   │     ├── View controller / welcome page...
   │     └── Resource handler mappings
   │
   ▼
ResourceHttpRequestHandler (khi URL được map sang static handler)
   │
   ├── xác định path tương đối từ URL đã match
   ├── duyệt locations đã đăng ký
   ├── ResourceResolver chain
   │     ├── version / encoded / webjar resolver nếu cấu hình
   │     └── PathResourceResolver để tìm file được phép
   ├── kiểm tra file tồn tại, được phép truy cập và đọc được
   ├── xác định media type, Last-Modified, cache headers
   └── truyền nội dung tài nguyên vào HttpServletResponse
```

**Các lớp cần phân biệt:**

| Thành phần | Package / vai trò |
| --- | --- |
| `ResourceHandlerRegistry` | API cấu hình qua `WebMvcConfigurer#addResourceHandlers`; đăng ký pattern và location |
| `ResourceHandlerRegistration` | Kết quả `addResourceHandler(...)`; cấu hình locations/cache/resource chain |
| `ResourceHttpRequestHandler` | MVC `HttpRequestHandler` thực sự phục vụ static resource |
| `HandlerMapping` | Quyết định request URL nên vào controller hay static handler |
| `ResourceResolver` | Tìm URL/resource: path, version, WebJars, encoded resources… |
| `ResourceTransformer` | Biến đổi response resource khi cần, ví dụ rewrite URL trong CSS |
| `org.springframework.core.io.Resource` | Trừu tượng truy cập classpath, filesystem hoặc ServletContext |
| `ViewResolver` | **Không phải static resource handler**; dùng khi controller trả logical view name |

`ResourceHandlerRegistry` không nhận GET rồi trực tiếp viết bytes. Nó tạo các mapping cho `ResourceHttpRequestHandler` khi ứng dụng khởi động; đến request runtime, `HandlerMapping` chọn handler này.

### 3.1. HandlerMapping khác ViewResolver

Controller:

```java
@Controller
class PageController {
    @GetMapping("/home")
    String home() {
        return "home";
    }
}
```

`"home"` là logical view name, thường được Thymeleaf/JSP resolver xử lý để tạo HTML. Trong khi đó, file `static/main.css` được `ResourceHttpRequestHandler` phục vụ như file, không cần logical view name, không cần Thymeleaf render.

Không nên tìm cách dùng `spring.thymeleaf.prefix=classpath:/static/` để giải quyết các URL CSS. Template engine và HTTP static resources là hai pipeline khác nhau.

### 3.2. Static handler khác @ResponseBody

Controller có thể dùng `ResponseEntity<Resource>` để tải file:

```java
@GetMapping("/download/{id}")
ResponseEntity<Resource> download(@PathVariable long id) {
    // Phân quyền, lookup Resource riêng theo id,
    // và trả header phù hợp.
}
```

Đây là đoạn **minh họa không độc lập**, thích hợp khi cần nghiệp vụ, quyền truy cập, nội dung người dùng upload, audit hoặc kiểm tra ID. Ngược lại, CSS/JS/logo công khai có URL quy ước nên để static resource handler giải quyết. Không dùng file handler công khai để vô tình lộ tài liệu riêng tư.

## 4. Vị trí static resources mặc định trong Spring Boot

Với Spring Boot Servlet MVC 3.x, trong điều kiện auto-configuration mặc định, tài nguyên được phục vụ từ các vị trí trên classpath:

1. `classpath:/META-INF/resources/`
2. `classpath:/resources/`
3. `classpath:/static/`
4. `classpath:/public/`

Ngoài các classpath locations, có thể có root của ServletContext khi triển khai kiểu servlet webapp. Với executable JAR, đặt nội dung dưới `src/main/resources/static/` là lựa chọn phổ biến, dễ đóng gói và dễ hiểu.

Ví dụ:

| Đường dẫn file trong dự án | URL mặc định | Ghi chú |
| --- | --- | --- |
| `src/main/resources/static/css/site.css` | `/css/site.css` | Không có `/static` trong URL |
| `src/main/resources/public/images/logo.svg` | `/images/logo.svg` | Vẫn được dùng như một resource location |
| `src/main/resources/resources/manual.pdf` | `/manual.pdf` | Một default location khác |
| `src/main/resources/META-INF/resources/favicon.ico` | `/favicon.ico` | Phù hợp convention của một số JAR |
| `src/main/resources/templates/home.html` | **Không có URL static mặc định** | Dành cho template engine, không phục vụ trực tiếp |
| `src/main/resources/config/secrets.yml` | **Không có URL static mặc định** | Không nên expose bí mật |
| `src/main/resources/manuals/intro.txt` | **Không có URL static mặc định** | Muốn công khai phải đăng ký location |

**Lưu ý:** Bảng mô tả từng vị trí có thể hoạt động khi có file tương ứng, không bảo đảm thứ tự “nếu trùng tên ở nhiều locations thì cái nào thắng” là hợp đồng ứng dụng lâu dài. Tránh đặt hai file public cùng relative path trong những static locations khác nhau; chỉ giữ một bản rõ ràng.

### 4.1. static không đồng nghĩa /static

File `src/main/resources/static/css/site.css` được phục vụ tại:

```text
http://localhost:8080/css/site.css
```

Không mặc định tại:

```text
http://localhost:8080/static/css/site.css
```

Muốn URL có tiền tố `/static`, phải đặt mapping URL riêng, ví dụ property `spring.mvc.static-path-pattern=/static/**` (phần 6). Khi đó URL và vị trí file vẫn là hai chuyện khác nhau.

### 4.2. Có nên dùng src/main/webapp?

`src/main/webapp/` là vị trí quen thuộc của các ứng dụng WAR/Servlet truyền thống. Với Spring Boot executable JAR, thư mục này **không phải cách an toàn để đóng gói static content**; nhiều build setup không đưa nó vào JAR như bạn mong muốn. Hãy dùng `src/main/resources/static/` hoặc một trong các default classpath locations.

JSP dưới `WEB-INF/jsp/` cũng không phải static public resource. Nếu ứng dụng dùng JSP, cần Servlet/JSP engine phù hợp, ViewResolver và đóng gói được hỗ trợ.

### 4.3. Welcome page index.html

Nếu `src/main/resources/static/index.html` tồn tại, Boot có thể dùng nó làm **welcome page** cho `GET /`. Một controller được map tường minh `@GetMapping("/")` thường được chọn trước welcome page mapping. Đây là một cơ chế cụ thể trong chuỗi HandlerMappings, không có nghĩa Boot “vô điều kiện phục vụ index.html trước controller”.

Ví dụ:

```text
static/index.html có tồn tại
  → GET / có thể được welcome-page handler phục vụ
  → GET /index.html được static handler phục vụ

Thêm @GetMapping("/")
  → GET / chạy controller thay vì welcome page fallback
```

Nếu có cả static index và template index, Boot mặc định tìm static index trước, rồi mới đến template index, với điều kiện không có route explicit ưu tiên hơn.

## 5. Thứ tự ánh xạ là thứ tự HandlerMapping, không phải tên file

Khi Spring MVC tìm handler cho một URL, các `HandlerMapping` có thể áp dụng các giá trị `order`. Theo API `ResourceHandlerRegistry#setOrder(...)`, mapping tài nguyên tĩnh mặc định có thứ tự:

```text
Integer.MAX_VALUE - 1
= 2147483646
= Ordered.LOWEST_PRECEDENCE - 1
```

Đây là giá trị **ưu tiên rất thấp**: các mapping controller MVC phổ biến có order nhỏ hơn và được xét trước. Nó giữ static resources như fallback sau những route động thực sự đã được khai báo.

Sơ đồ đơn giản:

```text
GET /catalog/42
  │
  ├── RequestMappingHandlerMapping có @GetMapping("/catalog/{id}")
  │        → MATCH → chạy controller → JSON
  │
  └── ResourceHandlerMapping mặc định "/**"
           → không đến lượt cho request này

GET /assets/site.css
  │
  ├── Không có controller cho URL này
  │
  └── Resource handler "/**"
           → MATCH → tìm static/assets/site.css
           → trả CSS
```

**Lưu ý về tính chính xác:** thứ tự giữa các loại HandlerMappings có thể thay đổi khi cấu hình MVC hoặc Spring Boot, và có thêm các nhóm như RouterFunctionMapping/WelcomePageHandlerMapping. Giá trị `Integer.MAX_VALUE-1` là mặc định của `ResourceHandlerRegistry` trong Spring Framework 6.2, **không phải một giá trị bảo đảm cho mọi loại handler mapping**.

### 5.1. Thứ tự mapping khác độ cụ thể của path

Có **hai mức** phân giải:

1. **Giữa các HandlerMapping**: order nhỏ hơn được hỏi trước. Một HandlerMapping đã tìm được handler thường kết thúc quá trình chọn, dù HandlerMapping khác có pattern URL “trông có vẻ cụ thể hơn”.
2. **Bên trong một HandlerMapping**: hệ thống so sánh các URL patterns, thường chọn pattern phù hợp và cụ thể hơn theo matching strategy đã cấu hình.

Ví dụ với hai resource patterns đăng ký cùng một ResourceHandlerRegistry:

```java
registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/brand-assets/");

registry.addResourceHandler("/**")
        .addResourceLocations("classpath:/fallback-assets/");
```

Trong cùng mapping, URL `/assets/logo.svg` có pattern `/assets/**` cụ thể hơn `/**`. Nhưng **không** coi thứ tự hai dòng Java là phương thức bảo đảm ưu tiên; matching sử dụng các rules của PathPattern/Ant matcher tương ứng.

Với Spring Boot đã có mapping `/**` mặc định, việc đăng ký thêm `/manuals/**` qua `addResourceHandlers` vẫn có thể hoạt động vì pattern cụ thể hơn trên cùng chuỗi MVC resource mappings; hãy test khi thay đổi order hoặc bật `@EnableWebMvc`.

### 5.2. Tại sao wildcard /** có thể gây khó debug 404?

Khi Boot đăng ký static handler mặc định `/**`, URL không trùng controller như `/not-found-route` vẫn có thể **match ResourceHttpRequestHandler**, nhưng resource file tương ứng không tồn tại. Kết quả vẫn là 404, song exception có thể là `NoResourceFoundException` (Spring 6.1+) thay vì “No handler found”.

Hệ quả:

- Không khẳng định cứ HTTP 404 là `DispatcherServlet` không tìm thấy handler.
- Cấu hình `spring.mvc.throw-exception-if-no-handler-found=true` không tự giải quyết mọi 404 nếu `/**` vẫn match resource handler.
- Kiểm tra log handler type và source exception; phân biệt URL chưa có controller và URL static resource không tồn tại.

**Không đặt resource handler cao hơn toàn bộ controller chỉ để ưu tiên CSS**, vì nó có thể “nuốt” route động nếu pattern quá rộng.

### 5.3. Phân biệt Filter order và HandlerMapping order

Servlet `FilterRegistrationBean#setOrder(...)` quyết định thứ tự filter trong Servlet container; `HandlerMapping#setOrder(...)` quyết định việc MVC chọn handler. `ViewResolver#setOrder(...)` lại áp dụng khi controller trả logical view name. Ba loại order độc lập.

```text
Servlet Filter order
  → DispatcherServlet
      → HandlerMapping order
          → controller hoặc resource handler
              → ViewResolver order (CHỈ khi có view name)
```

Chỉnh `@Order` trên filter không phải cách thay thứ tự static-vs-controller. Chỉnh ViewResolver không làm file CSS được phục vụ sớm hơn.

## 6. Bốn công cụ cấu hình thường bị nhầm

### 6.1. spring.mvc.static-path-pattern: đổi URL pattern

Mặc định static resources được map tại `/**`. Muốn công khai dưới URL prefix `/resources/`:

```properties
spring.mvc.static-path-pattern=/resources/**
```

Khi đó file `classpath:/static/css/site.css` được truy cập qua `GET /resources/css/site.css` theo cấu hình mặc định phù hợp.

Property này **không dời file trên classpath**. Đừng nhầm nó với directory location. Cũng cân nhắc rằng welcome-page mapping có thể bị ảnh hưởng bởi đường static path, nên phải kiểm thử `GET /` khi thay property.

### 6.2. spring.web.resources.static-locations: đổi nguồn

Muốn chỉ dùng một directory custom thay thế các classpath locations mặc định:

```properties
spring.web.resources.static-locations=classpath:/site-assets/
```

Khi đó Boot lấy static resources từ location được cấu hình này (và khả năng ServletContext root trong Servlet MVC), thay vì cộng thêm tất cả các default classpath locations. **Đây là REPLACE, không phải append** trong cách Boot xử lý property.

Vì vậy nếu đã set location custom rồi không thấy `static/css/site.css` nữa, hãy kiểm tra bạn có vô tình thay thế các default locations hay không.

Muốn sử dụng cả nguồn custom và một nguồn mặc định, hãy khai báo rõ danh sách:

```properties
spring.web.resources.static-locations=classpath:/site-assets/,classpath:/static/
```

Đừng dùng property cho một thư mục yêu cầu chính sách URL riêng khi `addResourceHandlers` mô tả rõ hơn.

### 6.3. spring.web.resources.add-mappings=false: tắt tự động

```properties
spring.web.resources.add-mappings=false
```

Khi đặt false, Boot không thêm **các mappings static mặc định** của mình. Các resource handlers do bạn chủ động đăng ký vẫn có thể tồn tại qua cấu hình MVC tương ứng. Đây có thể là lựa chọn khi muốn API-only, static files do CDN/reverse proxy phục vụ hoặc muốn kiểm soát toàn bộ mapping.

**Không tự bật property này chỉ để xử lý một 404**: có thể làm mất CSS/JS/favicon/welcome page đang chạy đúng. Sau thay đổi, test các URL public và route controller chính.

### 6.4. addResourceHandlers: thêm mapping tường minh

Để công khai riêng thư mục `classpath:/manuals/` tại `/manuals/**`:

```java
@Configuration
class StaticResourceConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/manuals/**")
                .addResourceLocations("classpath:/manuals/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic());
    }
}
```

*Đoạn cấu hình minh họa; cần imports `Configuration`, `WebMvcConfigurer`, `ResourceHandlerRegistry`, `CacheControl` và `Duration`. Project chạy đầy đủ ở mục 9.*

Cách này thêm một mapping có URL namespace rõ ràng; nó **không cần thay** đường static mặc định `/**`. Khi ứng dụng có nhiều nhóm files (ảnh, manual công khai, bundle), nên thiết kế path tường minh, ví dụ `/assets/**`, `/manuals/**` hoặc `/webjars/**`.

### 6.5. @EnableWebMvc trong Spring Boot

Không thêm `@EnableWebMvc` chỉ vì muốn đăng ký một mapping resource. Trong Spring Boot, annotation này làm bạn tự chịu trách nhiệm phần lớn MVC configuration, khiến các defaults Boot có thể không còn được áp dụng.

Ưu tiên:

- Dùng Boot properties cho thay đổi đơn giản.
- Dùng `@Configuration implements WebMvcConfigurer` và override `addResourceHandlers` cho mapping thêm.
- Chỉ dùng `@EnableWebMvc` khi chủ đích kiểm soát MVC ở mức Framework và đã bổ sung lại những thành phần cần thiết.

## 7. Cache và versioned URLs của static resources

`ResourceHttpRequestHandler` không chỉ đọc file tĩnh; phản hồi còn có thể mang **caching headers** và xử lý **conditional GET**. Hãy phân biệt ba nhiệm vụ thay vì bật một property rồi coi như đã xử lý hết:

| Nhiệm vụ | HTTP/Spring mechanism | Quyết định thiết kế |
| --- | --- | --- |
| Cache trong thời hạn | `Cache-Control`, ví dụ `max-age` | File không version không nên cache dài khi bytes có thể đổi tại cùng URL |
| Kiểm tra còn mới | `Last-Modified` / `If-Modified-Since` và status `304` | Không phải mọi nguồn Resource cung cấp timestamp chính xác |
| Tránh cache cũ sau deploy | Resource chain, URL fingerprint theo nội dung hoặc version cố định | Phải phát sinh URL mới trong HTML/template và giữ asset cũ đủ lâu |

Ví dụ cho resource tương đối ít đổi, handler riêng có thể đặt cache 5 phút:

```java
registry.addResourceHandler("/manuals/**")
        .addResourceLocations("classpath:/manuals/")
        .setCacheControl(
                CacheControl.maxAge(Duration.ofMinutes(5)).cachePublic());
```

Đây là fragment bên trong `WebMvcConfigurer#addResourceHandlers`; cần imports `CacheControl`, `Duration` và cấu hình bean thích hợp. Response có thể chứa `Cache-Control: max-age=300, public`. Nếu client gửi `If-Modified-Since` và resource có metadata cập nhật phù hợp, server có thể phản hồi `304 Not Modified` mà không truyền lại body.

Với static assets như CSS/JS được cache dài, **đường dẫn có content hash** giúp khi bytes đổi thì URL đổi. Nhưng tạo một URL phiên bản không đồng nghĩa có `Cache-Control` đúng, và bật `VersionResourceResolver` không tự sửa mọi đường dẫn hardcode trong HTML. Cần bảo đảm asset URLs được tạo/rewrite bằng template, `ResourceUrlProvider`, filter tương ứng hoặc manifest của bundler. Đừng thêm version resolver vào mọi resource handler tùy chỉnh nếu chưa kiểm tra mapping thực được dùng; một resolver custom cũng không được bỏ qua path containment.

Bài kế tiếp về **resource chain và dấu vân tay nội dung** là nơi trình bày cấu hình `ContentVersionStrategy`/`FixedVersionStrategy`, `VersionResourceResolver`, URL rewriting, Java config và kiểm thử rolling deployment. Ở đây điều quan trọng là xác định static file **được HandlerMapping nào phục vụ** trước khi chọn caching policy cho handler đó.

## 8. Bảo mật: file công khai không phải nơi chứa bí mật

Một static resource handler thường nên phục vụ **nội dung có thể công khai**. Những file sau không nên đặt trong public static locations:

```text
application-prod.yml chứa credentials
secret.key
private-invoices/customer-123.pdf
.env
backup.sql
repository .git/
```

Lý do: nếu có mapping rộng và file lọt vào resource root, client có thể gọi URL tương ứng trực tiếp. Việc thêm `/WEB-INF/`, đặt file ngoài web root hoặc bảo vệ bằng quyền truy cập thích hợp là trách nhiệm ứng dụng.

### 8.1. Path traversal

Ví dụ tấn công muốn lấy:

```text
GET /manuals/../config/secret.txt
GET /manuals/%2e%2e%2fconfig%2fsecret.txt
```

Spring MVC cùng `PathResourceResolver` và Servlet container có bảo vệ đối với path đi khỏi allowed resource locations. Tuy nhiên:

- Đừng vô hiệu hóa path validation hoặc tự ghép path từ request rồi mở `new File(...)`.
- Sự từ chối có thể xảy ra ở Servlet firewall/container/path matching trước resource handler; HTTP status cụ thể còn tùy cấu hình.
- Không dùng test “một biến thể traversal trả 404” để khẳng định đã chống mọi biến thể encoding.
- Hãy cập nhật Spring/container, giới hạn locations và test cả authorized/unauthorized file access theo môi trường triển khai.

### 8.2. Spring Security và static assets

ResourceHandler **không tự mở bypass Spring Security**. Servlet security filter chain có thể áp dụng cho CSS/JS/image requests. Nếu giao diện login không hiện CSS, kiểm tra authorize rules:

```java
// Ý tưởng policy trong SecurityFilterChain,
// không phải toàn bộ security configuration:
.requestMatchers("/css/**", "/js/**", "/images/**").permitAll()
.anyRequest().authenticated()
```

*Đoạn minh họa chỉ để hiểu policy; cần dự án có Spring Security và cấu hình đầy đủ.*

Ưu tiên `permitAll()` cho static assets công khai thay vì loại bỏ toàn bộ filter security bằng `web.ignoring()` khi bạn muốn giữ các security headers và protections. Không mở `/**` công khai nếu API/website còn tài nguyên cần bảo vệ.

### 8.3. CORS, content type và content sniffing

Nếu asset được tải cross-origin, CORS có thể cần cấu hình tùy loại request/usage; static handler có thể có CORS policy riêng. Không thêm `Access-Control-Allow-Origin: *` cho toàn bộ resource một cách vô điều kiện khi có credentials hoặc nội dung nhạy cảm.

Đảm bảo media types được xác định đúng (ví dụ `text/css`, `application/javascript`, `image/svg+xml`) và cân nhắc `X-Content-Type-Options: nosniff`. Một số định dạng, đặc biệt SVG/HTML/JS do người dùng upload, có thể chạy script trong các bối cảnh khác nhau: **không đưa untrusted uploads vào thư mục static công khai mà không có policy/validation**.

## 9. Dự án Spring Boot 3 + Java 17 chạy được

Demo thiết kế để nhìn thấy **cả static mapping mặc định và mapping custom**, đồng thời chứng minh route controller có ưu tiên hơn wildcard static fallback.

### 9.1. Hành vi sẽ kiểm thử

- File `static/assets/site.css` được phục vụ tại `GET /assets/site.css` (static mapping mặc định `/**`).
- File `manuals/guide.txt` được phục vụ tại `GET /manuals/guide.txt` sau khi đăng ký `/manuals/**`.
- File `static/catalog/7` tồn tại, nhưng `GET /catalog/7` chạy controller trả JSON (mapping động được chọn trước).
- `GET /manuals/absent.txt` trả 404; đó là request match resource handler nhưng không có file.
- `GET /index.html` phục vụ static welcome-file asset; khi chạy trong Servlet container thật, `GET /` có thể sử dụng welcome-page support.
- Response cho `/manuals/guide.txt` có cache-control `max-age=300` (chính sách demo).

Dùng Java 17+, Maven, Spring Boot **3.3.13** và Spring MVC.

### 9.2. Cấu trúc thư mục

```text
resource-handler-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/ResourceHandlerDemoApplication.java
    │   └── resources/
    │       ├── application.properties
    │       ├── static/
    │       │   ├── index.html
    │       │   ├── assets/site.css
    │       │   └── catalog/7
    │       └── manuals/guide.txt
    └── test/java/example/ResourceHandlerDemoTest.java
```

### 9.3. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>resource-handler-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 9.4. ResourceHandlerDemoApplication.java

Tạo file `src/main/java/example/ResourceHandlerDemoApplication.java`. Các class phụ package-private cùng file, chỉ class main là public.

```java
package example;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class ResourceHandlerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceHandlerDemoApplication.class, args);
    }
}

@Configuration
class PublicManualsConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        // URL /manuals/** trỏ vào classpath:/manuals/
        // và không thay thế static handler mặc định của Boot.
        registry.addResourceHandler("/manuals/**")
                .addResourceLocations("classpath:/manuals/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(5))
                                .cachePublic());
    }
}

@RestController
class CatalogController {
    @GetMapping("/catalog/{id}")
    Map<String, Object> product(@PathVariable int id) {
        return Map.of("id", id, "source", "controller");
    }
}
```

**Vì sao code chạy được?**

- `@SpringBootApplication` bật Spring Boot MVC auto-configuration khi đã thêm `spring-boot-starter-web`.
- `PublicManualsConfig implements WebMvcConfigurer` chỉ **bổ sung** một resource mapping, không bật `@EnableWebMvc`, nên Boot defaults vẫn còn.
- `registry.addResourceHandler("/manuals/**")` đăng ký URL namespace; `addResourceLocations("classpath:/manuals/")` trỏ tới folder thực được Maven đóng gói từ `src/main/resources/manuals/`.
- `CacheControl.maxAge(Duration.ofMinutes(5)).cachePublic()` phục vụ cache public có thời hạn 300 giây; đây chỉ là policy demo, không phù hợp với mọi tài liệu.
- `CatalogController` nhận URL `/catalog/7` trước resource fallback; file static trùng URL được thêm vào dự án **cố tình** để chứng minh thứ tự.

### 9.5. application.properties

File `src/main/resources/application.properties`:

```properties
# Giữ mặc định; giải thích rõ để quan sát thứ tự ánh xạ.
spring.web.resources.add-mappings=true
spring.mvc.static-path-pattern=/**
```

Không định nghĩa `spring.web.resources.static-locations`: sử dụng các classpath locations mặc định của Boot và custom location qua WebMvcConfigurer. Không cần đặt một thứ tự `registry.setOrder(...)` nếu chưa có nhu cầu rõ.

### 9.6. static/assets/site.css

File `src/main/resources/static/assets/site.css`:

```css
body {
    font-family: system-ui, sans-serif;
    color: #123456;
}
```

URL là `/assets/site.css`. Trình duyệt không gọi `/static/assets/site.css`; chữ `static` chỉ là tên location trên classpath.

### 9.7. manuals/guide.txt

File `src/main/resources/manuals/guide.txt`:

```text
Welcome to the public manual.
```

URL là `/manuals/guide.txt` nhờ mapping custom. File này nằm ngoài bốn static classpath locations mặc định, minh họa rằng chỉ “nằm trong resources” không tự tạo URL công khai.

### 9.8. static/catalog/7 (tài nguyên cố ý trùng route)

File `src/main/resources/static/catalog/7`:

```text
STATIC-FALLBACK-SHOULD-NOT-WIN
```

Khi gọi `GET /catalog/7`, controller vẫn được chọn, response JSON là `{"id":7,"source":"controller"}` (thứ tự keys không cần cố định). File này chỉ là fixture để test routing precedence; trong dự án production không nên có duplicate URL vô ích.

### 9.9. static/index.html

File `src/main/resources/static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Static Resource Demo</title>
    <link rel="stylesheet" href="/assets/site.css">
</head>
<body>
    <h1>Public index page</h1>
</body>
</html>
```

Đây là file HTML static, không phải Thymeleaf template: không có biểu thức view engine và có thể truy cập tại `/index.html`. Trong Boot Servlet MVC, cũng có thể được sử dụng cho welcome page `/` khi không có controller route riêng.

Khi ứng dụng có context path, dùng URL tương đối hoặc công cụ tạo context-aware URL trong template; literal `href="/assets/site.css"` trỏ tới origin root, nên chỉ phù hợp với demo chạy không có context path.

### 9.10. Chạy và kiểm tra bằng cURL

Cần JDK 17+ và Maven, ở thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Terminal khác:

```bash
curl -i http://localhost:8080/assets/site.css
curl -i http://localhost:8080/manuals/guide.txt
curl -i http://localhost:8080/catalog/7
curl -i http://localhost:8080/index.html
curl -i http://localhost:8080/manuals/not-found.txt
```

Kỳ vọng:

| URL | Status | Nội dung chính |
| --- | ---: | --- |
| `/assets/site.css` | 200 | CSS chứa `color: #123456;` |
| `/manuals/guide.txt` | 200 | Text `Welcome to the public manual.` |
| `/catalog/7` | 200 | JSON `{"id":7,"source":"controller"}` |
| `/index.html` | 200 | HTML chứa `Public index page` |
| `/manuals/not-found.txt` | 404 | Không có resource trong configured location |

Với `/manuals/guide.txt`, response header Cache-Control có `max-age=300`. `curl -i` hiển thị thêm headers phụ thuộc Tomcat/Boot. Đừng so sánh toàn bộ response byte-for-byte gồm ngày và headers tự sinh.

Để thử conditional HTTP (tùy Last-Modified của resource):

```bash
curl -I http://localhost:8080/manuals/guide.txt
# Đọc Last-Modified nếu có, rồi gửi:
curl -i -H 'If-Modified-Since: <date-from-last-modified>' \
  http://localhost:8080/manuals/guide.txt
```

Thay giá trị ngày đúng từ server. Nếu resource chưa thay đổi và server hỗ trợ validator thích hợp, response có thể là HTTP 304. Dòng có dấu góc ở đây là placeholder **chỉ trong lệnh CLI**, không phải giá trị HTTP thực.

## 10. MockMvc chứng minh default/custom/mapping priority

File `src/test/java/example/ResourceHandlerDemoTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.servlet.resource.ResourceHttpRequestHandler;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.handler;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceHandlerDemoTest {

    @Autowired
    MockMvc mvc;

    @Test
    void defaultBootStaticLocationServesCss() throws Exception {
        mvc.perform(get("/assets/site.css"))
            .andExpect(status().isOk())
            .andExpect(handler().handlerType(
                    ResourceHttpRequestHandler.class))
            .andExpect(content().string(
                    containsString("color: #123456;")));
    }

    @Test
    void customResourceHandlerServesManual() throws Exception {
        mvc.perform(get("/manuals/guide.txt"))
            .andExpect(status().isOk())
            .andExpect(handler().handlerType(
                    ResourceHttpRequestHandler.class))
            .andExpect(content().string(
                    containsString("Welcome to the public manual.")));
    }

    @Test
    void customManualHasFiveMinuteCachePolicy() throws Exception {
        mvc.perform(get("/manuals/guide.txt"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Cache-Control", containsString("max-age=300")));
    }

    @Test
    void controllerTakesPrecedenceOverStaticWildcard()
            throws Exception {
        mvc.perform(get("/catalog/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.source").value("controller"));
    }

    @Test
    void missingCustomResourceIsNotFound() throws Exception {
        mvc.perform(get("/manuals/absent.txt"))
            .andExpect(status().isNotFound());
    }

    @Test
    void indexHtmlIsAvailableAsStaticFile() throws Exception {
        mvc.perform(get("/index.html"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                    containsString("Public index page")));
    }

    @Test
    void staticIsNotAUrlPrefixByDefault() throws Exception {
        mvc.perform(get("/static/assets/site.css"))
            .andExpect(status().isNotFound());
    }
}
```

Chạy `mvn test`. Test xác nhận không chỉ status code mà cả **handler type** cho resources và **nội dung file**. Khi URL `/catalog/7`, test JSON chứng minh controller thật sự chạy dù có file static trùng URL.

`@SpringBootTest` với `@AutoConfigureMockMvc` nạp Boot auto-configuration và custom WebMvcConfigurer; không cần mở network port. Nhưng có những khác biệt khi deploy WAR/executable JAR hoặc dùng reverse proxy. Để kiểm chứng welcome page `GET /`, caching qua browser và headers do container tạo, có thể bổ sung integration tests chạy embedded server trên random port.

### 10.1. Vì sao không test bằng cách “cứ 404 là OK”?

Request `/manuals/absent.txt` có thể được resource HandlerMapping chọn, nhưng không tìm file. Test 404 chỉ chứng minh resource không được trả, chưa giải thích **nhánh** gây 404. Muốn phân tích thêm, dùng `handler().handlerType(ResourceHttpRequestHandler.class)` khi handler tồn tại, kiểm tra resolved exception nếu cần hoặc bật debug logging. Với Spring Framework 6.1+ `NoResourceFoundException` có thể được dùng khi không tìm thấy resource.

## 11. Resource locations ở ngoài classpath

Có trường hợp files là ảnh upload công khai, có thư mục cố định do admin quản lý hoặc được cập nhật sau khi JAR build. Có thể dùng `file:` location:

```java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/media/**")
            .addResourceLocations("file:/srv/myapp/public-media/")
            .setCacheControl(
                    CacheControl.maxAge(Duration.ofMinutes(10)));
}
```

Đoạn trên **chỉ minh họa**. File location có thể khác trên Windows/Linux, container images và cloud mounts. Nếu chọn public filesystem root, phải cấu hình quyền truy cập/ownership và không trộn với private directories; file nguồn cần nằm dưới location được phép.

### 11.1. Vì sao không lấy path từ query parameter?

Không triển khai kiểu sau:

```java
// Ví dụ sai: KHÔNG dùng với input từ người dùng.
Path file = Paths.get(request.getParameter("path"));
return Files.readAllBytes(file);
```

Nó bỏ qua các checks mà resource handler và path resolver đang cung cấp, có thể dẫn đến traversal hoặc đọc file tùy ý. Nếu cần cấp file theo ID nghiệp vụ, map ID tới metadata tin cậy ở server, kiểm tra ownership và sử dụng API tải file có kiểm soát.

### 11.2. Lưu file trong S3/CDN/object storage

Static content lớn và có lưu lượng cao có thể đặt ở CDN/object storage. Khi đó Spring MVC resource handler không nhất thiết là nơi tối ưu để truyền toàn bộ bytes. Có thể trả signed URL, redirect có kiểm soát hoặc dùng CDN origins với quyền phù hợp. Tài nguyên của nhiều tenants cần chính sách ACL chính xác; đừng chỉ đổi resource location sang một bucket public rồi coi như đã bảo mật.

## 12. Tương tác với templates, frontend bundlers và reverse proxy

### 12.1. Thymeleaf/JSP reference static URLs

Trong Thymeleaf:

```html
<link rel="stylesheet" th:href="@{/assets/site.css}">
<img th:src="@{/images/logo.svg}" alt="Logo">
<script th:src="@{/js/app.js}" defer></script>
```

Template engine tạo đường URL thích hợp theo context path. File thật vẫn nằm trong `static/assets/site.css`, `static/images/logo.svg` hoặc thư mục mapping custom. Với resource chain versioned URLs, cần bảo đảm URL rewriting đã được cấu hình đầy đủ.

Đừng tham chiếu `@{/static/assets/site.css}` theo thói quen nếu mapping URL vẫn là `/**`.

### 12.2. Khi frontend tool đã build bundles

Các bundlers có thể tạo:

```text
dist/assets/main-48abd3.css
dist/assets/main-93cf12.js
```

Có thể copy build output vào `src/main/resources/static/` ở giai đoạn packaging, hoặc cấu hình resource location tới output thích hợp. Trong sản phẩm thực tế, pipeline build phải bảo đảm filenames và index.html tham chiếu khớp. Không đọc thẳng source React/Vue project như static production asset nếu browser không hiểu modules/chưa build.

### 12.3. Reverse proxy / ingress

Nginx, Apache, CDN hoặc gateway có thể phục vụ static assets **trước khi request tới Spring Boot**. Khi đó bạn thấy 404/403/cache headers nhưng Spring MVC chưa hề chạy. Chẩn đoán theo từng layer:

```text
Browser
  → CDN/browser cache
  → Reverse proxy
  → Servlet container
  → Spring Security filters
  → DispatcherServlet
  → HandlerMapping / ResourceHttpRequestHandler
```

Kiểm tra request có tới ứng dụng không, host/path rewrite, forwarded headers, cache key và thời điểm deploy assets. Không sửa `ResourceHandlerRegistry` nếu 404 do CDN trỏ nhầm thư mục.

## 13. Debug checklist theo thứ tự nhanh nhất

1. **Xác định URL ngoài trình duyệt**: `/assets/site.css` hay `/static/assets/site.css`?
2. **Xác định file thực**: có trong `target/classes/static/` hoặc bên trong JAR sau build không?
3. **Kiểm tra Boot config**: `spring.web.resources.add-mappings`, `spring.mvc.static-path-pattern`, `spring.web.resources.static-locations`; properties của profile đang chạy.
4. **Kiểm tra handler mapping**: một controller có route trùng URL không? Có registry custom pattern bao phủ URL không?
5. **Kiểm tra resource handler**: URL đã match nhưng relative path/location có đúng không?
6. **Kiểm tra order**: giữa các HandlerMappings, controller thường chạy trước resource fallback; đừng nhầm order của filter/view resolver.
7. **Kiểm tra Security/CORS**: request thực tế bị 401/403/redirect login hay không?
8. **Kiểm tra cache**: stale content, 304, Cache-Control, content-version URL đã đúng chưa?
9. **Kiểm tra reverse proxy**: request có tới Servlet container không, có bị rewrite path không?
10. **Dùng MockMvc** để kiểm tra resource URL và controller priority; dùng HTTP integration test để xác nhận Servlet container/cache headers và deployment packaging.

Trong môi trường phát triển có thể bật logging:

```properties
logging.level.org.springframework.web.servlet.resource=DEBUG
logging.level.org.springframework.web.servlet.handler=DEBUG
```

Không bật DEBUG toàn web framework trên production dài hạn nếu sinh log rất lớn hoặc có nguy cơ lộ dữ liệu.

## 14. Các lỗi phổ biến

| Hiểu nhầm | Hậu quả | Sửa như thế nào |
| --- | --- | --- |
| “File nằm trong resources là tự public” | `manuals/guide.txt` 404 | Đặt trong default static dir hoặc đăng ký addResourceHandlers |
| “Static file URL phải có /static” | Sai URL, 404 | Nhớ `classpath:/static/` không đồng nghĩa URL `/static/` |
| “Thay static-path-pattern sẽ đổi thư mục nguồn” | Request vẫn tìm vị trí cũ | Dùng static-locations để đổi location |
| “static-locations tự append mặc định” | CSS cũ biến mất | Đây là replace; khai báo đủ locations |
| “ResourceHandlerRegistry đặt trước controller nếu code config viết trước” | Hiểu sai precedence | HandlerMapping order, không phải thứ tự câu lệnh |
| “/** wildcard luôn thắng @GetMapping” | Nghĩ route động không chạy | Controller mapping thường có priority cao hơn |
| “Cứ 404 là NoHandlerFoundException” | Exception handler không bắt được lỗi static file | Xem NoResourceFoundException và mapping /** |
| “@EnableWebMvc chỉ bật MVC cho Boot” | Mất nhiều auto-configuration | Dùng WebMvcConfigurer khi chỉ cần chỉnh mapping |
| “ViewResolver xử lý CSS” | Chỉnh nhầm template prefix | Dùng resource mappings và ResourceHttpRequestHandler |
| “Cache static 1 năm mà không cần version URL” | Users thấy file cũ | Gắn hash/version hoặc cache ngắn |
| “Bật VersionResourceResolver là HTML tự đổi URL” | URL không khớp, cache issues | ResourceUrlProvider/encoding integration |
| “Bật CORS * cho mọi file” | Mở rộng quyền quá mức | CORS policy theo nhu cầu và credentials |
| “Có PathResourceResolver nên upload nào cũng an toàn” | XSS, lộ dữ liệu qua public files | Tách uploads private, validate MIME/ACL |
| “Servlet root và classpath static giống nhau” | Deploy WAR/JAR khác hành vi | Hiểu packaging/resource loading cụ thể |
| “Security phải bỏ qua mọi static assets” | Mất security headers/protections | Permit public paths trong SecurityFilterChain nếu phù hợp |
| “Thấy Cache-Control là chắc 304” | Sai HTTP caching semantics | 304 phụ thuộc conditional request/validators |
| “CSS không đổi trong browser thì sửa mapping” | Sửa sai layer | Kiểm tra browser/CDN cache trước |
| “File static luôn có thứ tự ưu tiên theo folder name” | Duplicate path ngoài ý muốn | Tránh trùng relative paths giữa locations |

## 15. Tự kiểm tra

**1.** File `src/main/resources/static/css/main.css` có URL nào dưới Boot default?  
**Đáp án:** `GET /css/main.css`, không phải `/static/css/main.css`.

**2.** File `src/main/resources/manuals/intro.txt` tự có URL không?  
**Đáp án:** không nằm trong các default locations; cần thêm mapping hoặc chuyển file.

**3.** `addResourceHandler("/public/**")` và `addResourceLocations("classpath:/assets/")`: URL `/public/site.css` tìm file ở đâu?  
**Đáp án:** `classpath:/assets/site.css`.

**4.** `ResourceHttpRequestHandler` làm gì?  
**Đáp án:** nhận static request được map, resolve file và phục vụ bytes/headers.

**5.** `ViewResolver` có phải `ResourceHttpRequestHandler` không?  
**Đáp án:** không; ViewResolver dùng cho logical view name trong pipeline render.

**6.** `HandlerMapping` của resource registry có order mặc định bao nhiêu trong Spring 6.2?  
**Đáp án:** `Integer.MAX_VALUE - 1`, ưu tiên rất thấp.

**7.** Khi `@GetMapping("/catalog/{id}")` và static `catalog/7` cùng tồn tại, ai thường thắng?  
**Đáp án:** controller vì RequestMappingHandlerMapping được xét trước resource fallback.

**8.** Có phải `/assets/**` luôn được xét trước `/**` vì được khai báo trước trong Java?  
**Đáp án:** không; path specificity và mapping rules quyết định trong cùng HandlerMapping.

**9.** Cấu hình nào đổi URL prefix của static assets?  
**Đáp án:** `spring.mvc.static-path-pattern`.

**10.** Cấu hình nào đổi resource locations của Boot?  
**Đáp án:** `spring.web.resources.static-locations`; nó thay thế default locations.

**11.** Tắt Boot static auto mappings thế nào?  
**Đáp án:** `spring.web.resources.add-mappings=false`.

**12.** Vì sao bật `@EnableWebMvc` dễ làm static files biến mất?  
**Đáp án:** bạn nhận trách nhiệm cấu hình MVC thay nhiều defaults của Boot.

**13.** `/manuals/not-found.txt` trả 404, có chắc không có handler không?  
**Đáp án:** không; resource handler có thể match rồi không tìm thấy file.

**14.** Khi nào nên dùng content version URL?  
**Đáp án:** khi cần cache dài hạn nhưng asset có thể đổi theo release; URL hash/version giúp cache busting.

**15.** `If-Modified-Since` có thể dẫn tới status nào nếu file chưa đổi?  
**Đáp án:** 304 Not Modified, tùy resource validator/HTTP policy.

**16.** Đặt private user PDFs vào `static/` có an toàn không?  
**Đáp án:** không mặc định; static location là khu vực public theo URL mapping, cần access control riêng.

**17.** Header `X-Content-Type-Options: nosniff` có vai trò gì?  
**Đáp án:** hạn chế browser đoán MIME vượt khai báo server, một lớp giảm nguy cơ xử lý sai kiểu.

**18.** Khi CDN trả 404, có chắc `ResourceHandlerRegistry` của Spring đang sai không?  
**Đáp án:** không; request có thể chưa đến Spring.

**19.** Vì sao cần kiểm tra bên trong JAR sau build?  
**Đáp án:** file đúng trong source tree chưa bảo đảm được đóng gói tới classpath runtime.

**20.** Nên viết test nào để chứng minh thứ tự controller/static?  
**Đáp án:** tạo route/controller và file static cùng URL, assert response từ controller và handler phù hợp.

## 16. Tài liệu chính thức

- [Spring Framework 6.2 — Static Resources](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/static-resources.html): `addResourceHandlers`, cache control, versioned resource URLs, resource resolver chain.
- [Spring Framework 6.2 — ResourceHandlerRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/servlet/config/annotation/ResourceHandlerRegistry.html): `addResourceHandler` và `setOrder`, mặc định `Integer.MAX_VALUE - 1`.
- [Spring Framework 6.2 — ResourceHttpRequestHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/resource/ResourceHttpRequestHandler.html): tìm và phục vụ resource, conditional request/Last-Modified.
- [Spring Framework 6.2 — VersionResourceResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/web/servlet/resource/VersionResourceResolver.html): content/fixed version strategies.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): static content locations, `static-path-pattern`, `static-locations`, welcome page, WebJars.
- [Spring Framework — Handler Mappings](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping.html): cách MVC chọn handler theo URL/order.
- [Spring Framework 6.2 — MVC Test Framework](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html): MockMvc và kiểm thử handler.

**Ghi nhớ:** ResourceHandler gắn **URL pattern** với **vị trí file/resource thực** để `ResourceHttpRequestHandler` phục vụ. Spring Boot có các classpath static locations mặc định và fallback `/**`; controller mappings thường được xét trước. Khi file không xuất hiện, kiểm tra **đường URL → HandlerMapping order → resource location → file packaging → security/cache/proxy** thay vì đoán hoặc chỉnh sai ViewResolver.
