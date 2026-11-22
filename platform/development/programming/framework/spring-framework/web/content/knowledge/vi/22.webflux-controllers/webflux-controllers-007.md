# Trả view, Model và tích hợp template engine reactive trong Spring WebFlux

## 1. Khi WebFlux không chỉ trả JSON

Spring WebFlux thường được giới thiệu qua `@RestController` trả `Mono<Product>`, `Flux<Product>` và JSON. Nhưng WebFlux cũng phục vụ **HTML render phía server**: trình duyệt gửi GET, `@Controller` chuẩn bị **Model**, trả **tên view logic** hoặc một đối tượng `Rendering`, và một template engine như Thymeleaf tạo HTML.

Ba thành phần cần phân biệt:

- **View**: mẫu thể hiện đầu ra, ví dụ template `src/main/resources/templates/catalog.html`, được tìm thông qua logical view name `"catalog"`.
- **Model**: bản đồ tên → dữ liệu để template đọc, ví dụ `title = "Sản phẩm"`, `products = Flux<Product>`.
- **Reactive view resolution/rendering**: framework nhận return value, chọn `ViewResolver`, giải reactive model attributes phù hợp và ghi HTML thành HTTP response. Reactor `Mono`/`Flux` không tự biến template thành luồng HTML không giới hạn.

Mục tiêu bài:

1. Hiểu luồng `DispatcherHandler → HandlerResult → ViewResolutionResultHandler → ViewResolver → View → ServerHttpResponse`.
2. Trả `String` logical view name qua `@Controller` và truyền dữ liệu qua `Model`.
3. Phân biệt `@Controller` trả view với `@RestController`/`@ResponseBody` trả JSON hay text body.
4. Hiểu `Mono<String>` tên view, `Mono<Rendering>` và `Model` có thuộc tính `Mono<T>` hoặc `Flux<T>`.
5. Nắm sự khác nhau giữa thuộc tính `Flux<T>` (thường được gom thành `List<T>` trước render view) và HTTP SSE/streaming.
6. Cấu hình Thymeleaf tích hợp WebFlux bằng Spring Boot 3 và so sánh FreeMarker/Mustache với reactive template engine.
7. Tạo ứng dụng Java 17 chạy được, có trang danh sách, chi tiết, 404, redirect, model reactive, API JSON và tests WebTestClient.
8. Chẩn đoán lỗi mất template, HTML không được render, template chặn event loop, dữ liệu không được escape, cache, CSRF và những hiểu nhầm Servlet/WebFlux.

**Phạm vi:** Spring Framework 6.x, Spring Boot 3.x, Java 17+ và **Spring WebFlux** reactive stack. Những ví dụ chạy thử dùng Boot 3.3.13 với Reactor Netty mặc định, `spring-boot-starter-webflux` và `spring-boot-starter-thymeleaf`. Không dùng JSP/Servlet-specific ViewResolver hoặc `org.springframework.web.servlet.ModelAndView` cho ví dụ WebFlux.

## 2. Tại sao view rendering cũng có thể là reactive?

Hình dung trang danh mục cần dữ liệu sản phẩm từ remote API. Nếu controller dùng WebClient hoặc reactive repository, nó có thể trả hoặc đặt `Mono<List<Product>>` vào model **mà không chặn Servlet worker đợi dữ liệu**. WebFlux dùng các publishers để chờ kết quả và sau đó render view.

Luồng tổng quát:

```text
GET /pages/home
   │
   ▼
Reactor Netty HTTP server
   │
   ▼
DispatcherHandler (Spring WebFlux, không phải DispatcherServlet)
   │
   ├─ HandlerMapping: xác định @Controller method
   └─ HandlerAdapter: gọi method, nhận view name và Model
         │
         │ model["title"] = "Danh mục"
         │ model["products"] = Flux<Product>
         │ model["featured"] = Mono<Product>
         ▼
HandlerResult
   │
   ▼
ViewResolutionResultHandler
   ├─ chọn logical view name "home"
   ├─ hỏi các ViewResolver thích hợp
   ├─ resolve model attributes kiểu Mono/Flux trước view rendering
   │      ├─ Mono<Product> → Product hoặc không có thuộc tính
   │      └─ Flux<Product> → List<Product> (có thể cần toàn bộ sequence)
   └─ render qua Thymeleaf reactive integration
           │
           ▼
      ServerHttpResponse: text/html
```

Spring Framework cho phép model chứa reactive wrappers và giải chúng trước khi view thực sự sử dụng dữ liệu. Đây là điểm khác biệt quan trọng với model thông thường của Spring MVC.

### 2.1. Reactive không có nghĩa HTML đã xuất ngay khi Flux emit

Giả sử `Flux<Product>` phát 10.000 dòng. Nếu view renderer cần một collection hoàn chỉnh trước khi mở vòng lặp HTML, framework có thể **gom chúng thành List**. Khi đó:

- Template phải chờ Flux complete.
- Có thể giữ nhiều item trong memory.
- Infinite Flux không bao giờ complete → view có thể không bao giờ kết thúc.
- Error giữa quá trình resolve có thể ngăn HTML bình thường được dựng.

Một số template technologies (đặc biệt Thymeleaf reactive integration) có khả năng rendering/chunking theo cấu hình riêng, nhưng **không suy từ việc model chứa Flux rằng browser nhận một item HTML cho mỗi onNext**. Nếu mục tiêu là tiến trình cập nhật liên tục, cân nhắc SSE, WebSocket, HTML fragments streaming hoặc thiết kế phân trang.

### 2.2. View rendering vs JSON serialization

| Yêu cầu | Return phổ biến | Thành phần cuối |
| --- | --- | --- |
| GET trang HTML | `String` hoặc `Rendering` trong `@Controller` | `ViewResolver` + template engine |
| GET dữ liệu JSON | `Mono<Product>` trong `@RestController` | `HttpMessageWriter` / JSON codec |
| GET nhiều dữ liệu JSON | `Flux<Product>` với `@ResponseBody` | JSON encoding, có thể thành array |
| SSE cập nhật | `Flux<ServerSentEvent<?>>` với `text/event-stream` | Streamed response writer |
| Redirect browser | `"redirect:/pages/home"` | Redirect view/status và Location |
| Không có nội dung | `Mono<ResponseEntity<Void>>` trả 204 | HTTP status/headers, không template |

Content negotiation còn có thể tham gia view choice, nhưng một controller view-oriented không đồng nghĩa tự động hỗ trợ cả HTML lẫn JSON cho mọi Accept header.

## 3. @Controller, @RestController và @ResponseBody: khác nhau rất lớn

### 3.1. @Controller trả String là tên template

```java
@Controller
class WelcomeController {
    @GetMapping("/welcome")
    String welcome(Model model) {
        model.addAttribute("message", "Xin chào!");
        return "welcome";
    }
}
```

Spring WebFlux hiểu `"welcome"` là **logical view name**, không phải response text literal. Với Thymeleaf auto-config mặc định, view resolver tìm `classpath:/templates/welcome.html` rồi render.

### 3.2. @RestController trả String là body

```java
@RestController
class WelcomeApi {
    @GetMapping("/api/welcome")
    String welcome() {
        return "welcome";
    }
}
```

Spring ghi chuỗi **welcome** vào HTTP response body; không tìm `welcome.html`. `@RestController` có semantics `@Controller + @ResponseBody`.

### 3.3. @ResponseBody trên một method của @Controller

```java
@Controller
class MixedController {
    @GetMapping("/page")
    String page() {
        return "welcome"; // tên view
    }

    @ResponseBody
    @GetMapping("/raw")
    String raw() {
        return "welcome"; // body literal
    }
}
```

**Sai lầm kinh điển:** dùng `@RestController` rồi return `"home"`, kỳ vọng trang `home.html`. Kết quả là text "home". Khi mục đích là render HTML qua template, dùng `@Controller` và view name.

### 3.4. @ModelAttribute không tự biến method thành REST

Trong HTML controller, một object trả về (không phải kiểu đơn giản đặc biệt) có thể được xem như model attribute. `@ModelAttribute("product")` cũng cho phép đặt tên cho attribute. Nhưng nếu method trả `String`, Framework thường diễn giải thành **view name**; cần dùng `@ModelAttribute` tường minh nếu muốn coi chính String đó là model attribute, hoặc gọi `model.addAttribute(...)` để dễ đọc.

## 4. Model: dữ liệu truyền vào template

`org.springframework.ui.Model` là interface dùng trong cả MVC và WebFlux. Ví dụ:

```java
@GetMapping("/pages/hello")
String hello(Model model) {
    model.addAttribute("title", "Khóa học WebFlux");
    model.addAttribute("user", new UserView("Lan"));
    return "hello";
}
```

Đoạn trên là **snippet**; cần class UserView và @Controller hoàn chỉnh. Model là tập attributes theo tên. Với template:

```html
<h1 th:text="${title}">Tiêu đề mẫu</h1>
<p th:text="${user.name()}">Tên mẫu</p>
```

`th:text` đưa dữ liệu qua cơ chế escaping HTML của Thymeleaf; khác với `th:utext` vốn render unescaped markup. Đừng đưa dữ liệu user vào `th:utext` trừ khi nguồn thật sự trusted/sanitized với chính sách rõ.

### 4.1. Mono trong Model

Spring WebFlux cho phép:

```java
@GetMapping("/pages/profile")
String profile(Model model) {
    Mono<Profile> profileMono = service.loadProfile();
    model.addAttribute("profile", profileMono);
    return "profile";
}
```

Trước view rendering, model attribute reactive có thể được resolve thành giá trị `Profile`. Không gọi `profileMono.block()` trong WebFlux handler.

### 4.2. Flux trong Model

```java
@GetMapping("/pages/items")
String items(Model model) {
    Flux<Item> all = service.findAll();
    model.addAttribute("items", all);
    return "items";
}
```

WebFlux view infrastructure có thể resolve `Flux<Item>` thành `List<Item>` trước render. Nếu nguồn không complete hoặc có một triệu items, đây là vấn đề. Vì vậy list HTML nên phân trang và áp dụng limit tại repository/query, **không** dùng `collectList` vô hạn hoặc giả định template tự giải quyết backpressure UI.

### 4.3. Model chứa Mono.empty()

Nếu `profileMono` complete empty, model attribute có thể không có giá trị tương ứng. Template viết `${profile.name}` có thể gây lỗi hoặc không hiển thị như mong muốn. Hãy định nghĩa semantics rõ:

- Nếu resource không tồn tại: trả 404 với view phù hợp trước khi render.
- Nếu thông tin là tùy chọn: dùng fallback hoặc hiển thị có điều kiện.
- Nếu remote service lỗi: không tự chuyển mọi `onError` thành empty, vì che giấu outage.

Một service trả `Mono.empty()` không có nghĩa framework phải tự chọn HTTP 404 cho trang.

### 4.4. @ModelAttribute method

```java
@ModelAttribute
void common(Model model) {
    model.addAttribute("siteName", "Học Spring");
}
```

Các `@ModelAttribute` methods có thể chạy trước request handler trong cùng controller và chuẩn bị dữ liệu dùng chung. Tuy nhiên, nếu đặt I/O blocking trực tiếp trong `@ModelAttribute`, nó vẫn có thể chặn request path. Dùng reactive publisher/async style và kiểm soát lỗi phù hợp.

### 4.5. Tránh giữ state giữa nhiều requests

`@Controller` mặc định là singleton Spring bean. Không dùng một field mutable kiểu `private String currentUserName` để lưu model data của request hiện tại. Hai requests concurrent có thể làm lộ dữ liệu người này sang người khác. Sử dụng local method variables, scoped request/session phù hợp hoặc context có kiểm soát.

## 5. ViewResolutionResultHandler và ViewResolver hoạt động ra sao?

Spring WebFlux sử dụng `DispatcherHandler` làm front controller. Khi handler trả kết quả, các `HandlerResultHandler` xử lý từng loại return value. Với view rendering, `ViewResolutionResultHandler` chọn một `View` từ registered `ViewResolver`.

Các bước khái quát:

1. `HandlerMapping` chọn method/controller.
2. `HandlerAdapter` thực thi và tạo `HandlerResult` có return value và Model.
3. `ViewResolutionResultHandler` xác định logical view name từ String/Rendering/default translation.
4. `ViewResolver` tương ứng tìm `View` ứng với tên và locale phù hợp.
5. Model attributes reactive được giải theo contract view.
6. View engine tạo HTML và ghi vào `ServerHttpResponse` dưới một publisher phản ánh completion.

**Đừng import nhầm các lớp Servlet:**

| Spring MVC Servlet | Spring WebFlux |
| --- | --- |
| `DispatcherServlet` | `DispatcherHandler` |
| `org.springframework.web.servlet.ViewResolver` | `org.springframework.web.reactive.result.view.ViewResolver` |
| `org.springframework.web.servlet.View` | `org.springframework.web.reactive.result.view.View` |
| `ModelAndView` (Servlet) | `Rendering` (reactive view scenarios) |
| `HttpServletRequest` | `ServerHttpRequest`/`ServerWebExchange` |
| `HttpMessageConverter` | `HttpMessageReader`/`HttpMessageWriter` |
| Servlet `Filter` | WebFlux `WebFilter` |

Spring MVC có hỗ trợ reactive return types trong một số trường hợp, nhưng đó **không** khiến MVC chuyển thành WebFlux. Cần xác định application type khi debug.

### 5.1. String logical name

```java
return "catalog";
```

Với Thymeleaf mặc định, resolver thường tra `classpath:/templates/catalog.html`. Đừng trả cả đường dẫn filesystem hoặc URL absolute do user kiểm soát: logical names cần thuộc allowlist/trust boundary của ứng dụng.

### 5.2. Tên view mặc định

Nếu view controller không nêu tên và handler result phù hợp, WebFlux có thể suy tên view theo request path (bỏ slash đầu/cuối). Ví dụ `/pages/default` tương ứng logical view `pages/default`, và template `templates/pages/default.html`.

Đây là khả năng Framework, nhưng thường **return tên view tường minh** sẽ ít gây hiểu nhầm và dễ refactor hơn. Với REST controller, void/null semantics khác tùy response handling.

### 5.3. Redirect

```java
@GetMapping("/pages/old")
String old() {
    return "redirect:/pages/home";
}
```

Prefix `redirect:` được view infrastructure nhận diện để trả redirect đến route mục tiêu. Status có thể là 303 See Other trong WebFlux RedirectView mặc định; test redirect nên assert 3xx + Location thay vì hardcode 302 nếu không có policy status được cấu hình.

Không dùng `forward:` như Servlet MVC: **WebFlux không hỗ trợ Servlet FORWARD dispatch**. Redirect tạo thêm request từ client, không phải server-side internal forward.

### 5.4. Content negotiation và default views

`ViewResolutionResultHandler` có thể so `Accept` với media types của views. WebFlux cung cấp `HttpMessageWriterView` để render model thành JSON/XML thông qua codecs khi muốn cấu hình default views.

Tuy nhiên, đây là cấu hình nâng cao. Với đa số ứng dụng, nên tách rõ:

- `GET /pages/products` → HTML.
- `GET /api/products` → JSON.

Trộn HTTP HTML/JSON vào cùng một endpoint đòi hỏi quy tắc Content-Type, caching, error handling và test Accept chặt chẽ.

## 6. Tích hợp Thymeleaf reactive vào Spring Boot

### 6.1. Dependencies cần thiết

Với Maven và Spring Boot 3:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-thymeleaf</artifactId>
</dependency>
```

Starter thứ nhất chọn WebFlux/reactive HTTP runtime, starter thứ hai tự cấu hình Thymeleaf tương thích WebFlux. Không cần đồng thời thêm `spring-boot-starter-web`: khi MVC và WebFlux starters cùng có mặt, Spring Boot thường chọn **MVC/Servlet application** theo mặc định.

### 6.2. Vị trí templates mặc định

```text
src/main/resources/
├── templates/
│   ├── home.html
│   ├── detail.html
│   └── missing.html
└── static/
    └── css/site.css
```

Boot tự tìm templates từ `classpath:/templates/`. Với view name `"home"` và suffix `.html`, tên resource tương ứng là `classpath:/templates/home.html`.

Không đặt templates cần server render vào `src/main/resources/static/` rồi kỳ vọng expressions `th:text` được thực thi. Static handler gửi nguyên nội dung file.

### 6.3. Các properties thường gặp

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.encoding=UTF-8
spring.thymeleaf.cache=false
```

Đây là một **profile phát triển** để template thay đổi dễ quan sát. Trong production nên cân nhắc bật cache template (thường default là true) để tránh chi phí parse/lắp lại template quá thường xuyên. Cache template **khác** HTTP response cache và **không tự làm data/model được cache**.

### 6.4. Các class đặc trưng của Thymeleaf WebFlux

Tích hợp Thymeleaf reactive (do Thymeleaf project quản lý) có các khái niệm như:

- `SpringResourceTemplateResolver`.
- `SpringWebFluxTemplateEngine`.
- `ThymeleafReactiveViewResolver`.
- `ThymeleafReactiveView` và reactive view support.

Với Boot auto-configuration, **không phải tự viết tất cả các bean trên**. Chỉ cấu hình thủ công khi thật sự thay template resolver path/encoding/engine/dialect hoặc có nhiều engines. Nếu tự khai báo resolver sai, có thể mất auto-config defaults và templates trả 500.

### 6.5. Thymeleaf template cú pháp

Các expressions thường gặp:

| Cú pháp | Công dụng |
| --- | --- |
| `th:text="${title}"` | Escape rồi hiển thị model attribute |
| `th:each="item : ${items}"` | Lặp qua collection model |
| `th:if="${item != null}"` | Render có điều kiện |
| `th:href="@{/pages/products/{id}(id=${item.id()})}"` | Dựng URL từ path variable |
| `th:object="${command}"` | Chọn form-backing bean |
| `th:field="*{title}"` | Gắn field trong form |
| `#{message.key}` | Đọc message bundle theo locale |
| `th:utext="${rawHtml}"` | Không escape HTML; cần kiểm soát XSS |

Khi dùng Java record trong template, cách chắc chắn đọc dữ liệu là gọi accessor `item.name()`, `item.id()` theo SpringEL/Thymeleaf phù hợp. Chỉ dùng `th:utext` với HTML trusted hoặc đã sanitize chặt.

## 7. Rendering: view name, model, status trong một giá trị

Spring WebFlux có interface `org.springframework.web.reactive.result.view.Rendering` để xây return value thể hiện view, model, status và headers.

```java
@GetMapping("/products/{id}")
Mono<Rendering> detail(@PathVariable long id) {
    return service.findById(id)
        .map(item -> Rendering.view("detail")
                .modelAttribute("product", item)
                .build())
        .switchIfEmpty(Mono.just(
            Rendering.view("missing")
                .status(HttpStatus.NOT_FOUND)
                .modelAttribute("id", id)
                .build()));
}
```

Đây là **snippet** cần controller/service và imports; ví dụ hoàn chỉnh ở mục 11. Điểm chính: HTTP 404 được quyết định **trước render**, chứ không kỳ vọng Thymeleaf tự biến `Mono.empty()` thành 404.

### 7.1. Mono<Rendering> khác Mono<DTO>

- `Mono<Rendering>`: kết quả khi subscribe là thông tin về **view để render**.
- `Mono<Product>` trong `@RestController`: khi complete thành công, framework serialize một Product ra JSON.
- `Mono<String>` trong `@Controller`: String thường là **view name**, không phải body text.
- `Mono<ResponseEntity<Product>>` trong REST: quyết định HTTP status/body theo object.
- `Mono<Void>`: phản ánh completion không payload, hoặc có thể cho view name mặc định trong các tình huống đặc biệt; không dùng để đại diện view tùy ý.

### 7.2. Rendering status và redirects

Nếu cần redirect có status cụ thể, có thể dùng API `Rendering.redirectTo(...)` và cấu hình status/headers theo API version. Tuy nhiên route đơn giản `return "redirect:/pages/home";` thường dễ hiểu.

Không truyền external redirect target trực tiếp từ query param không kiểm soát như `return "redirect:" + request.getParameter("next")`; đó là rủi ro **open redirect**. Dùng allowlist internal routes hoặc kiểm tra hosts/paths.

## 8. Reactive Model: giải quyết nguồn dữ liệu trước khi render

### 8.1. Gán trực tiếp Mono/Flux vào model

```java
@GetMapping("/catalog")
String catalog(Model model) {
    model.addAttribute("featured", service.featured()); // Mono<Product>
    model.addAttribute("products", service.findAll());   // Flux<Product>
    model.addAttribute("count", service.findAll().count()); // Mono<Long>
    return "catalog";
}
```

Khi view được render, các publishers cần được subscribe/resolve thành dữ liệu dùng trong template. Không cần tự `block()`. Tuy nhiên lưu ý:

- Mỗi lần gọi `service.findAll()` có thể tạo source mới; danh sách và count trong ví dụ có thể là **hai truy vấn** nếu service thực có R2DBC.
- Nếu muốn snapshot nhất quán, hãy thiết kế một service call trả DTO tổng hợp thích hợp thay vì gọi nhiều publishers không đồng bộ lẫn nhau.
- Nếu `Flux<Product>` lớn, cần phân trang trước khi đưa vào view.
- `Mono.empty()` có thể tạo attribute absent; có fallback/conditional view logic đúng nghiệp vụ.
- Model attributes có side effects không idempotent tuyệt đối không nên phụ thuộc vào số lần subscribe không kiểm soát.

### 8.2. Chuẩn bị dữ liệu rồi mới chọn view

Một cách khác: controller compose publisher trước, rồi emit `Rendering`:

```java
@GetMapping("/catalog/summary")
Mono<Rendering> summary() {
    return service.findAll()
        .collectList()
        .map(items -> Rendering.view("summary")
            .modelAttribute("total", items.size())
            .modelAttribute("items", items)
            .build());
}
```

Ưu: dữ liệu đã rõ, có thể xử lý empty/error và status. Nhược: `collectList()` buffer toàn bộ Flux, không dùng với vô hạn hoặc data lớn. Trong ví dụ production, query nên có pagination và hard limit.

### 8.3. Đặt một Mono vào Model không nhất thiết cho HTML streaming

Nhận một `Mono<Product>` hay `Flux<Product>` không làm template trở thành kết nối push updates liên tục. View thường cần model concrete values trước khi render. Nếu muốn giữ trang HTML mở và gửi cập nhật từng phần, phải thiết kế riêng theo Thymeleaf reactive modes hoặc WebFlux fragment streaming/SSE.

### 8.4. Model và context reactive

WebFlux không phải Servlet application nếu chạy Reactor Netty. Vì vậy:

- Không tự ép kiểu `ServerWebExchange` thành `HttpServletRequest`.
- Không dựa vào một ThreadLocal do Servlet filter set để render đúng user/locale khi pipeline đổi thread.
- Dùng Spring Security reactive context, Reactor Context và các APIs tương ứng khi cần principal, locale, request data.
- Khi render template, tránh gọi trực tiếp dịch vụ blocking thông qua custom dialect/expression trong event-loop; đưa data vào model bằng service đã được cấu hình phù hợp.

## 9. Template engine reactive khác REST response streaming

Một số luồng thường bị nhầm:

| Luồng | Dữ liệu đầu vào | Response |
| --- | --- | --- |
| Thymeleaf thông thường | Model đã resolve (có thể từ Mono/Flux) | HTML document |
| Thymeleaf chunked/data-driven | Reactive model + cấu hình/mode hỗ trợ | Các HTML chunks theo policy engine |
| FreeMarker/Mustache | Model để dựng view | HTML document theo engine integration |
| `Flux<ServerSentEvent<?>>` | Các events phát liên tục | `text/event-stream`, browser nhận events |
| `Flux<DTO>` / JSON | Reactive elements | JSON array hoặc streaming JSON tùy media type |
| `Flux<Fragment>` / fragment renderer | Các fragments HTML | HTML fragments theo API hỗ trợ và media type |

**Quyết định theo UX:** Nếu người dùng cần trang HTML có thông tin để đọc/submit form, server-side render thường phù hợp. Nếu cần cập nhật realtime, dùng SSE/WebSocket hoặc HTML-over-the-wire streaming với contract/DOM update rõ. Không chọn Flux vô hạn làm model cho trang HTML thông thường.

### 9.1. FreeMarker và Mustache

Spring Boot hỗ trợ FreeMarker, Thymeleaf và Mustache với WebFlux. Khi dùng starter hoặc dependencies đúng, templates được tìm từ `src/main/resources/templates` theo conventions của engine. FreeMarker có phần hỗ trợ WebFlux riêng; không mặc nhiên mọi tính năng Servlet form macros đều tồn tại giống MVC.

Thyemleaf có native WebFlux integration do chính Thymeleaf project cung cấp. Sửa lỗi template nên xác định engine thực đang được Boot auto-configure và resolver bean nào xử lý view name.

### 9.2. JSP và Servlet-only engines

JSP dựa vào Servlet/JSP container và không phải engine view phù hợp cho WebFlux chạy Reactor Netty. Không đặt `/WEB-INF/jsp/*.jsp` và cấu hình MVC `InternalResourceViewResolver` trong một project WebFlux reactive rồi mong chạy như Servlet MVC.

### 9.3. HTML fragments và HTMX

Ở các phiên bản Spring WebFlux mới, có hỗ trợ fragment-oriented responses như `Fragment` và `FragmentsRendering`. Mục tiêu là trả một hoặc nhiều phần HTML để frontend (HTMX/Hotwire) chèn vào DOM, có thể qua streaming. Các API này có thay đổi theo Framework minor/major version; trước khi copy snippet từ tài liệu phiên bản khác, cần xác minh class/package và media type phù hợp với 6.x/7.x đang sử dụng.

Bài runnable dưới đây giữ mô hình **whole-page view** để rõ và ổn định trên Boot 3.3.

## 10. Những lỗi liên quan template và bảo mật

### 10.1. Cross-site scripting (XSS)

Nếu user đặt tên:

```text
<script>alert("hello")</script>
```

Và template dùng:

```html
<p th:text="${name}">name</p>
```

Thymeleaf escape text HTML, trình duyệt hiển thị ký tự như văn bản, không thực thi script. Ngược lại:

```html
<p th:utext="${name}">name</p>
```

Ký tự HTML được render theo markup; **nguy hiểm** khi name từ input không tin cậy. Luôn validate/sanitize rich HTML nếu có yêu cầu thực sự, dùng escaping phù hợp ngữ cảnh HTML/attribute/JavaScript/URL, thêm CSP khi cần. Escaping của một template expression không thay toàn bộ XSS defenses.

### 10.2. Template name injection

Không bao giờ làm:

```java
@GetMapping("/unsafe")
String unsafe(@RequestParam String template) {
    return template; // user tự quyết định tên view
}
```

Đoạn trên là **anti-pattern**. Template engine có thể truy cập Spring application beans hoặc resources trong trust boundary; khi template names/content do user điều khiển, hệ thống có nguy cơ template injection, resource disclosure hoặc open redirect. Dùng whitelist server-controlled names, không cho user upload/chỉnh sửa arbitrary templates.

### 10.3. Form POST/CSRF

Server-rendered HTML thường đi cùng session cookie. Nếu có POST/PUT/DELETE qua browser với ambient credentials, cần cấu hình CSRF trong **Spring Security WebFlux**. Reactive security sử dụng `SecurityWebFilterChain` chứ không phải Servlet `SecurityFilterChain`. Form có thể cần CSRF hidden input theo dialect/security integration tương ứng; không bỏ CSRF chỉ vì ứng dụng đang dùng reactive.

### 10.4. Authorization từng resource

Chỉ ẩn nút “Xóa” với `th:if` **không** bảo vệ endpoint DELETE. Backend cần kiểm tra quyền theo object ID/owner/tenant. Model data nên chỉ chứa fields đã được phép lộ cho request hiện tại; nếu cache HTML response, đảm bảo không trộn nội dung của user A vào user B.

### 10.5. Content Security Policy và URL escaping

Không nối raw HTML bằng StringBuilder trong controller rồi gửi mà bỏ escaping. Dùng template engine và CSP phù hợp. URL sinh từ template cần an toàn/encoded; tránh mở redirect tới external host không kiểm soát. Không gắn access token hoặc dữ liệu riêng tư vào query string/logs/HTML source.

### 10.6. Caching template khác caching HTTP

- **Template cache**: lưu parsed/compiled template structures để render nhanh hơn, **không** giữ nguyên response HTML của từng user.
- **HTTP cache**: browser/CDN có thể lưu response theo Cache-Control, ETag và Vary; cần cân nhắc privacy.
- **Service/data cache**: lưu dữ liệu nghiệp vụ theo key/TTL và invalidation.

Một trang dashboard user-specific không an toàn để gắn `Cache-Control: public` chỉ vì Thymeleaf template đã cache.

## 11. Ứng dụng runnable: Spring Boot 3 + Java 17 + WebFlux + Thymeleaf

Dự án minh họa:

- `GET /pages/home`: template `home.html` có title và ba thuộc tính model reactive.
- `GET /pages/products/1`: dùng `Mono<Rendering>`, render `detail.html` cùng HTTP 200.
- `GET /pages/products/999`: không tìm thấy, render `missing.html` và HTTP 404.
- `GET /pages/summary`: `Mono<String>` chọn tên template sau khi count đã xong.
- `GET /pages/greeting?name=...`: HTML escaping qua `th:text`.
- `GET /pages/old`: redirect tới trang mới.
- `GET /api/products`: cùng service nhưng `@RestController` trả Flux JSON, để so sánh view và body.
- `GET /pages/default`: template path mặc định khi handler không trả tên view tường minh.

Không có database/remote network để làm ví dụ tự chứa; `CatalogService` cố tình chỉ dùng `List` nhỏ, `Mono` và `Flux`. Khi thay service bằng R2DBC/WebClient, phải quản lý subscription/errors/timeout.

### 11.1. Cấu trúc dự án

```text
webflux-reactive-views/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── ReactiveViewsApplication.java
    │   │   ├── Product.java
    │   │   ├── CatalogService.java
    │   │   ├── PageController.java
    │   │   └── CatalogApiController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/
    │           ├── home.html
    │           ├── detail.html
    │           ├── missing.html
    │           ├── summary.html
    │           ├── greeting.html
    │           └── pages/default.html
    └── test/
        └── java/example/ReactiveViewsTest.java
```

### 11.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>webflux-reactive-views</artifactId>
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
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

Chỉ có `spring-boot-starter-webflux` để Boot không chuyển ngầm sang Servlet MVC. Thymeleaf starter auto-configure view engine; không cần `@EnableWebFlux` vì Boot đã cung cấp WebFlux auto-configuration.

### 11.3. ReactiveViewsApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveViewsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveViewsApplication.class, args);
    }
}
```

### 11.4. Product.java

```java
package example;

public record Product(long id, String name, long priceVnd) {}
```

Record giữ dữ liệu hiển thị, không expose entity persistence với fields nhạy cảm.

### 11.5. CatalogService.java

```java
package example;

import java.util.List;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CatalogService {

    private final List<Product> products = List.of(
        new Product(1L, "Spring WebFlux", 120000L),
        new Product(2L, "Spring Boot", 99000L),
        new Product(3L, "Project Reactor", 85000L)
    );

    public Flux<Product> all() {
        return Flux.defer(() -> Flux.fromIterable(products));
    }

    public Mono<Product> find(long id) {
        return all()
            .filter(item -> item.id() == id)
            .next();
    }
}
```

Cả `all()` và `find()` là cold publishers. Ví dụ cố tình không truy cập database: từ đó thấy rõ model resolver không cần `block()`. Ứng dụng thật nên có các giới hạn phân trang, caching/transactions và xử lý sự cố nguồn dữ liệu.

### 11.6. PageController.java

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.reactive.result.view.Rendering;

import reactor.core.publisher.Mono;

@Controller
@RequestMapping("/pages")
public class PageController {

    private final CatalogService catalog;

    public PageController(CatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/home")
    public String home(Model model) {
        model.addAttribute("title", "Danh mục sản phẩm");
        model.addAttribute("products", catalog.all());
        model.addAttribute("featured", catalog.find(1L));
        model.addAttribute("count", catalog.all().count());
        return "home";
    }

    @GetMapping("/products/{id}")
    public Mono<Rendering> detail(@PathVariable long id) {
        return catalog.find(id)
            .map(product -> Rendering.view("detail")
                .modelAttribute("product", product)
                .build())
            .switchIfEmpty(Mono.just(
                Rendering.view("missing")
                    .status(HttpStatus.NOT_FOUND)
                    .modelAttribute("id", id)
                    .build()));
    }

    @GetMapping("/summary")
    public Mono<String> summary(Model model) {
        return catalog.all()
            .count()
            .map(count -> {
                model.addAttribute("count", count);
                return "summary";
            });
    }

    @GetMapping("/greeting")
    public String greeting(
            @RequestParam(defaultValue = "Khách") String name,
            Model model) {
        model.addAttribute("name", name);
        return "greeting";
    }

    @GetMapping("/old")
    public String oldPage() {
        return "redirect:/pages/home";
    }

    @GetMapping("/default")
    public void defaultView(Model model) {
        model.addAttribute("message", "Trang được chọn theo đường dẫn");
        // Không trả view name tường minh; WebFlux có thể suy
        // logical view name "pages/default" theo request path.
    }
}
```

Ý nghĩa:

- `home(Model)` dùng reactive attributes; template engine sẽ nhận concrete values khi render.
- `detail()` dùng reactive service rồi chọn view tương ứng; không chặn event-loop. 404 không phụ thuộc `Mono.empty` default.
- `summary()` trả `Mono<String>`, khi số lượng sẵn sàng mới emit logical view name "summary".
- `greeting()` render text có escape qua template.
- `oldPage()` chuyển hướng theo prefix `redirect:`.
- `defaultView()` minh họa convention. Trong production, trả `"pages/default"` tường minh thường rõ hơn và ít phụ thuộc path.

### 11.7. CatalogApiController.java

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api")
public class CatalogApiController {

    private final CatalogService catalog;

    public CatalogApiController(CatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/products")
    public Flux<Product> products() {
        return catalog.all();
    }
}
```

Đường `/api/products` dùng HTTP response writer JSON, không dùng template `home.html`. Cùng một CatalogService có thể phục vụ HTML và JSON mà không duplicate business logic.

### 11.8. application.properties

```properties
server.port=8080
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.encoding=UTF-8
spring.thymeleaf.cache=false
```

Đây là config development. Chỉnh `spring.thymeleaf.cache=true` cho production sau khi kiểm tra hot reload và deployment pipeline.

### 11.9. home.html

File `src/main/resources/templates/home.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="${title}">Danh mục</title>
</head>
<body>
    <h1 th:text="${title}">Danh mục</h1>
    <p id="count" th:text="|Số sản phẩm: ${count}|">
        Số sản phẩm: 0
    </p>

    <h2>Sản phẩm nổi bật</h2>
    <p id="featured" th:if="${featured != null}"
       th:text="${featured.name()}">Sản phẩm</p>

    <h2>Danh sách</h2>
    <ul id="products">
        <li th:each="item : ${products}">
            <a th:href="@{/pages/products/{id}(id=${item.id()})}"
               th:text="${item.name()}">Tên sản phẩm</a>
            <span th:text="${item.priceVnd()}">0</span>
        </li>
    </ul>

    <p><a th:href="@{/pages/summary}">Xem tổng kết</a></p>
</body>
</html>
```

Thymeleaf dùng `th:each` qua danh sách sau khi model Flux được resolve. `th:text` escape nội dung. URL `@{...}` tạo link ứng dụng từ record accessor thay vì nối chuỗi không được encode.

### 11.10. detail.html

File `src/main/resources/templates/detail.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Chi tiết sản phẩm</title>
</head>
<body>
    <h1>Chi tiết sản phẩm</h1>
    <p id="item-id" th:text="${product.id()}">0</p>
    <p id="item-name" th:text="${product.name()}">Tên</p>
    <p id="item-price" th:text="${product.priceVnd()}">0</p>
    <a th:href="@{/pages/home}">Quay lại danh sách</a>
</body>
</html>
```

HTTP status của trang này là 200 vì `Rendering.view("detail")` không override status.

### 11.11. missing.html

File `src/main/resources/templates/missing.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Không tìm thấy</title>
</head>
<body>
    <h1>Không tìm thấy sản phẩm</h1>
    <p>Mã sản phẩm:
        <span id="missing-id" th:text="${id}">0</span>
    </p>
    <a th:href="@{/pages/home}">Danh mục</a>
</body>
</html>
```

Nội dung HTML “Không tìm thấy” và HTTP status 404 là hai thứ riêng. `Rendering.status(HttpStatus.NOT_FOUND)` làm status đúng, không chỉ có message trên trang.

### 11.12. summary.html

File `src/main/resources/templates/summary.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Tổng kết</title>
</head>
<body>
    <h1>Tổng kết danh mục</h1>
    <p id="summary-count"
       th:text="|Số sản phẩm: ${count}|">Số sản phẩm: 0</p>
</body>
</html>
```

`summary(Model)` trả `Mono<String>` đã tạo `count` trước khi emit view name. Không có `block()` hoặc `subscribe()` thủ công.

### 11.13. greeting.html

File `src/main/resources/templates/greeting.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Chào mừng</title>
</head>
<body>
    <h1>Chào mừng</h1>
    <p id="greeting-name" th:text="${name}">Khách</p>
</body>
</html>
```

Trường hợp tên là `<script>alert(1)</script>` thì `th:text` escape thành văn bản an toàn trong HTML context. Ví dụ này không kiểm thử tất cả XSS vectors, chỉ minh họa khác nhau giữa escaping và raw output.

### 11.14. pages/default.html

File `src/main/resources/templates/pages/default.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Trang mặc định</title>
</head>
<body>
    <h1>Trang mặc định</h1>
    <p id="default-message"
       th:text="${message}">Nội dung</p>
</body>
</html>
```

Nếu `defaultView(Model)` không có return value và framework chọn implicit logical view name theo path, template này được tìm nhờ `pages/default`. Với một cấu hình router/view tùy biến, nên test hoặc trả tên view tường minh để không phụ thuộc vào convention.

## 12. Chạy và quan sát kết quả

Ở thư mục có `pom.xml`, với JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Gọi trang HTML:

```bash
curl -i http://localhost:8080/pages/home
```

Kỳ vọng HTTP 200, `Content-Type: text/html` (có thể có charset) và HTML có:

```html
<h1>Danh mục sản phẩm</h1>
<p id="count">Số sản phẩm: 3</p>
```

Danh sách đã render có các tên `Spring WebFlux`, `Spring Boot` và `Project Reactor`. HTML thực tế có thể được format/indent khác template, nên không so byte-for-byte.

Chi tiết:

```bash
curl -i http://localhost:8080/pages/products/1
```

Kỳ vọng 200 và nội dung tên `Spring WebFlux`.

Missing:

```bash
curl -i http://localhost:8080/pages/products/999
```

Kỳ vọng HTTP 404 cùng **HTML của missing.html**, không phải chỉ JSON error mặc định.

Summary:

```bash
curl -i http://localhost:8080/pages/summary
```

Kỳ vọng 200 và `Số sản phẩm: 3`.

Redirect:

```bash
curl -i http://localhost:8080/pages/old
```

Kỳ vọng 3xx với `Location: /pages/home`. Dùng `curl -L` để theo chuyển hướng.

REST JSON:

```bash
curl -i http://localhost:8080/api/products
```

Kỳ vọng JSON array:

```json
[
  {"id":1,"name":"Spring WebFlux","priceVnd":120000},
  {"id":2,"name":"Spring Boot","priceVnd":99000},
  {"id":3,"name":"Project Reactor","priceVnd":85000}
]
```

JSON key order/indent không phải contract; test nên theo fields. JSON endpoint dùng dữ liệu cùng service nhưng **không** chạy Thymeleaf.

### 12.1. Nhìn rõ sự khác nhau giữa @Controller và @RestController

Nếu thay `@Controller` ở PageController thành `@RestController`, method `home()` trả chuỗi `"home"` dưới dạng response body; trang sẽ không được render như kỳ vọng. Đây là phép thử tư duy tốt để tránh lỗi controller trả tên view thành raw text.

## 13. WebTestClient: kiểm thử reactive views qua HTTP

Kiểm thử dùng Spring Boot context thật và embedded reactive web server. Kỳ vọng HTML theo những vùng text ổn định, không assert toàn bộ HTML đã render chính xác từng whitespace.

File `src/test/java/example/ReactiveViewsTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveViewsTest {

    @Autowired
    WebTestClient client;

    @Test
    void homeRendersHtmlWithResolvedReactiveAttributes() {
        client.get().uri("/pages/home")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_HTML)
            .expectBody(String.class)
                .value(html -> {
                    assertTrue(html.contains("Danh mục sản phẩm"));
                    assertTrue(html.contains("Số sản phẩm: 3"));
                    assertTrue(html.contains("Spring WebFlux"));
                    assertTrue(html.contains("Spring Boot"));
                    assertTrue(html.contains("Project Reactor"));
                });
    }

    @Test
    void detailUsesReactiveRenderingAndReturns200() {
        client.get().uri("/pages/products/1")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
                .value(html -> {
                    assertTrue(html.contains("Chi tiết sản phẩm"));
                    assertTrue(html.contains("Spring WebFlux"));
                });
    }

    @Test
    void missingProductIsExplicitHtml404() {
        client.get().uri("/pages/products/999")
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_HTML)
            .expectBody(String.class)
                .value(html -> {
                    assertTrue(html.contains("Không tìm thấy sản phẩm"));
                    assertTrue(html.contains("999"));
                });
    }

    @Test
    void monoViewNameRendersSummary() {
        client.get().uri("/pages/summary")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
                .value(html -> assertTrue(
                    html.contains("Số sản phẩm: 3")));
    }

    @Test
    void greetingEscapesUntrustedHtml() {
        client.get().uri(builder -> builder
                .path("/pages/greeting")
                .queryParam("name", "<script>alert(1)</script>")
                .build())
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
                .value(html -> {
                    assertFalse(html.contains("<script>"));
                    assertTrue(html.contains("&lt;script&gt;"));
                });
    }

    @Test
    void redirectHasLocationHeader() {
        client.get().uri("/pages/old")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/pages/home");
    }

    @Test
    void jsonApiDoesNotRenderThymeleaf() {
        client.get().uri("/api/products")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$[0].id").isEqualTo(1)
                .jsonPath("$[1].name").isEqualTo("Spring Boot")
                .jsonPath("$[2].priceVnd").isEqualTo(85000);
    }

    @Test
    void implicitPathViewCanResolveTemplate() {
        client.get().uri("/pages/default")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
                .value(html -> assertTrue(
                    html.contains("Trang được chọn theo đường dẫn")));
    }

    @Test
    void homeDoesNotExposeThymeleafExpressionsLiterally() {
        client.get().uri("/pages/home")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
                .value(html -> {
                    assertFalse(html.contains("th:text="));
                    assertFalse(html.contains("th:each="));
                });
    }
}
```

**Vì sao test vừa HTML vừa JSON?** Đây là cách rõ nhất chứng minh `ViewResolutionResultHandler` và `HttpMessageWriter` là hai hướng xử lý khác nhau trong cùng WebFlux application. Test `homeRendersHtmlWithResolvedReactiveAttributes` cũng giúp phát hiện việc model được render nguyên `Mono/Flux.toString()` thay vì dữ liệu concrete.

### 13.1. Kiểm thử có thể thất bại vì version/encoding, không nên đoán

- Nếu test HTML fail 500, xem exception khi resolver không tìm template hoặc Thymeleaf expression lỗi.
- Nếu HTML thực xuất ra khác spacing, dùng HTML parser/assert structural semantics thay vì so raw whitespace.
- Nếu running app sử dụng Servlet MVC do vô tình thêm `spring-boot-starter-web`, kiểm tra actual application type trước khi debug view.
- Nếu test implicit view fail vì framework/config đã tùy biến, có thể chủ động trả `"pages/default"` ở project production; test ở đây cố tình minh họa convention WebFlux 6.x.
- Nếu assert escaping fail ở một version engine, kiểm tra cách output được escape và DOM behavior thay vì vô hiệu hóa escaping.

Các test trên là **mã được cung cấp**; chỉ được tuyên bố “test PASS” sau khi chạy Maven và có kết quả thực.

## 14. Mô hình tối ưu dữ liệu cho trang HTML reactive

### 14.1. Tránh gọi ba lần database

Trong demo home:

```java
model.addAttribute("products", catalog.all());
model.addAttribute("featured", catalog.find(1L));
model.addAttribute("count", catalog.all().count());
```

Với List in-memory thì rất nhẹ. Nhưng nếu `catalog.all()` là R2DBC query thực, màn home có thể chạy **hai truy vấn danh sách** và một truy vấn nổi bật.

Trong production, hướng tốt hơn là xây view model trong service:

```java
record CatalogPage(
        String title,
        long count,
        List<Product> products,
        Product featured) {}

Mono<CatalogPage> page = service.loadCatalogPage(limit, pageIndex);
```

Đây là concept snippet, không phải method standalone. Service có thể trả đúng một snapshot DTO đã phân trang. Controller dùng:

```java
return page.map(p ->
    Rendering.view("home")
        .modelAttribute("title", p.title())
        .modelAttribute("count", p.count())
        .modelAttribute("products", p.products())
        .modelAttribute("featured", p.featured())
        .build());
```

Đoạn code là phần return của `Mono<Rendering>` handler với biến `page` đã tạo ở trên. Nó tránh việc view resolver phải resolve nhiều reactive attributes riêng rẽ và giúp định nghĩa data consistency.

### 14.2. Giới hạn dữ liệu trước render

Nếu danh sách 1 triệu hàng, browser cũng không cần HTML cho mọi item ngay. Thường nên:

1. Nhận page/cursor với limit bounded.
2. Validate page size trên server.
3. Thực hiện DB query có limit, không chỉ `flux.take(20)` sau một query đã tải hết.
4. Render những records của trang hiện tại.
5. Cho client load next page hoặc dùng HTMX/infinite scroll với contract cụ thể.

### 14.3. Đặt timeout trước giai đoạn render

Một reactive data source không bao giờ complete sẽ khiến HTML view có thể treo. Đặt timeout business trước khi truyền model:

```java
Mono<Product> featured =
    service.featured()
        .timeout(Duration.ofSeconds(2));
```

Đây là snippet, cần import `Duration` và policy lỗi phù hợp. Nếu timeout, có thể cho view fallback sản phẩm nổi bật rỗng hoặc trả error page, nhưng không nên lặng lẽ coi timeout của database là “không có sản phẩm”.

### 14.4. Template processing có dùng CPU

Reactive I/O giúp tránh chờ thread khi kết nối remote, nhưng template engine phải parse expressions, lặp records, escape HTML và tạo bytes. Nếu trang rất lớn, việc render có thể tốn CPU và allocations, ngay cả khi model là reactive.

Theo dõi event-loop lag/CPU, latency template, memory, encoder buffers và GC. Nếu cần xử lý CPU/blocking nặng, thiết kế scheduler/bulkhead phù hợp hoặc đẩy sang service chuyên biệt; không mặc định mọi việc bên trong template là non-blocking.

### 14.5. Caching danh mục và model

Dữ liệu công khai ít đổi có thể cache ở service level. Nhưng cache theo user/session phải có key và TTL/invalidation chính xác. Không đặt `Mono.cache()` vô hạn cho một publisher chứa thông tin riêng tư rồi dùng chung bean/controller cho nhiều requests.

## 15. Forms, binding và validation trong WebFlux view

Template engine giúp dựng form:

```html
<form th:action="@{/pages/products/create}" method="post">
    <label for="name">Tên sản phẩm</label>
    <input id="name" type="text" name="name">
    <button type="submit">Tạo</button>
</form>
```

Form HTML `application/x-www-form-urlencoded` cần data binding và validation. Trong annotated WebFlux controller, có thể dùng `@ModelAttribute` và `BindingResult` với quy tắc thứ tự arguments phù hợp. Với reactive binder/validator, cần hiểu `WebExchangeBindException` khi có lỗi binding/validation.

Ví dụ minh họa:

```java
@PostMapping("/pages/products/create")
Mono<String> create(
        @Valid @ModelAttribute ProductForm form,
        BindingResult errors,
        Model model) {
    if (errors.hasErrors()) {
        model.addAttribute("form", form);
        return Mono.just("create-form");
    }
    return service.create(form)
                  .thenReturn("redirect:/pages/home");
}
```

Đây là **snippet không chạy độc lập**: cần `ProductForm`/service/validator imports, template create-form và cấu hình Security/CSRF. Với WebFlux, validation còn phụ thuộc method signatures và reactive input; không sao chép Servlet MVC form code rồi giả định mọi annotation/method overload hoạt động giống hệt. Nếu dùng `BindingResult`, đặt ngay sau argument `@ModelAttribute` được validate theo contract Framework.

### 15.1. Chống over-posting/mass assignment

Không bind request form trực tiếp vào JPA entity có `role`, `ownerId`, `isAdmin` hay trường giá trị do server kiểm soát. Dùng dedicated command DTO, giới hạn fields được bind và gán identity từ principal. Template hidden field không được tin cậy vì client có thể tự sửa.

### 15.2. Hiển thị lỗi validation

Thymeleaf có `th:errors` và `#fields` cho form binding theo integration. Luồng thực tế phải:

1. Validate input.
2. Trả lại form view khi lỗi, giữ binding result trong model đúng convention.
3. Escape mọi giá trị đã submit.
4. Không commit transaction/sửa DB khi form invalid.
5. Thiết kế CSRF token trong form khi login/session cần.
6. Trên thành công, redirect (PRG: Post/Redirect/Get) để giảm accidental duplicate POST.

## 16. Những lỗi thường gặp và hướng khắc phục

| Triệu chứng | Nguyên nhân khả dĩ | Xử lý |
| --- | --- | --- |
| Browser chỉ hiện chữ `home` | `@RestController` trả String body | Dùng `@Controller` cho view |
| 500 TemplateInputException | Sai logical view name hoặc thiếu `templates/home.html` | Kiểm tra prefix/suffix/classpath |
| HTML còn `th:text`/`th:each` | Template file bị phục vụ dưới `static` hoặc không qua resolver | Đặt dưới `templates` và return view name |
| IDE import Servlet ModelAndView | Nhầm MVC và WebFlux | Dùng `Rendering` reactive |
| Trang HTML đợi vô hạn | Model chứa Flux không complete | Pagination/take/timeout/streaming |
| Tạo được Mono nhưng block() gây lỗi | Blocking trên Netty event-loop | Compose operators/return Publisher |
| Flux trong Model không stream từng item | View resolver giải toàn List | Chọn SSE/fragments nếu cần incremental |
| Trang chi tiết rỗng không 404 | `Mono.empty()` không tự set HTTP status | Dùng `Rendering.status(NOT_FOUND)` |
| Trang 404 chỉ có text nhưng status 200 | Render missing view nhưng không set HTTP 404 | Dùng Rendering status |
| `Model` có `Mono<User>` dạng chuỗi | Custom view engine không hỗ trợ reactive attrs | Verify view resolver/engine integration |
| XSS qua field name | Dùng `th:utext` cho untrusted input | Dùng `th:text`/escaping |
| Open redirect qua URL param | Return `redirect:` + user input | Allowlist server-controlled target |
| Template được user upload tùy ý | Template expression có thể truy cập beans | Không dùng editable templates từ untrusted users |
| Form POST 403 | Spring Security CSRF/roles | Bổ sung token và security policy đúng |
| Form tự submit nhưng over-posting | Binding trực tiếp entity | DTO với allowed fields |
| Trang quá nặng CPU | Template render/loop khối lượng lớn | Page limit, caching, profiling |
| Reactors Mono cache lẫn user | Reuse publisher của session A cho B | Partition by principal, TTL/invalidation |
| 404 khi /pages/default | Default name/path không có template | Thêm pages/default.html hoặc return explicit |
| Redirect status không phải 302 | WebFlux RedirectView default semantics | Assert 3xx+Location hoặc cấu hình status rõ |
| WebFlux project chạy DispatcherServlet | Thêm cả MVC starter | Kiểm tra app type/dependencies |
| JSP template không được resolve trên Netty | JSP cần Servlet/JSP infrastructure | Thymeleaf/FreeMarker/Mustache |
| Server 200 nhưng text/html không có | `@ResponseBody` hoặc converter khác | Kiểm tra controller annotations |
| Invalid HTML chứa raw script | Unescaped expression/custom dialect | Escape/sanitize, test XSS |
| API JSON phát sai key/format | DTO/Jackson contract hoặc Content-Type | JSON tests, schema, negotiation |

### 16.1. Quy trình debug từng tầng

1. **Runtime:** kiểm tra Boot chạy WebFlux reactive (Reactor Netty mặc định) hay MVC Servlet.
2. **Mapping:** route có match `GET /pages/home` và được xử lý bởi `@Controller` không?
3. **Return value:** `"home"` được xem là tên view hay String body?
4. **View resolver:** Thymeleaf reactive view resolver bean có tồn tại không, template path là gì?
5. **Model:** những keys được thêm có đúng tên template dùng? Mono/Flux complete/error ra sao?
6. **Render:** kiểm tra Thymeleaf syntax, SpringEL, escaping, fragments, locale và message bundles.
7. **HTTP:** status, `Content-Type: text/html`, caching/security/redirect headers có đúng không?
8. **Metrics:** template rendering latency, memory, codec buffering và event-loop CPU dưới tải thực.

## 17. Checklist thiết kế trước khi triển khai

- [ ] Chọn `@Controller` cho HTML, `@RestController` cho REST API.
- [ ] Return view name từ allowlist server-controlled; không dùng untrusted URL làm template name.
- [ ] Các template ở đúng `classpath:/templates/` và engine phù hợp Spring WebFlux.
- [ ] Model data chỉ gồm các fields cần hiển thị, đã được authorize.
- [ ] `Mono.empty()` có semantics rõ (missing, optional hoặc error), status được set đúng.
- [ ] `Flux`/collections được giới hạn theo pagination, không render vô hạn.
- [ ] Không `block()` hoặc gọi blocking clients trực tiếp trong request event-loop.
- [ ] Template expressions dùng escaping; không `th:utext` với user input không tin cậy.
- [ ] Cấu hình CSRF/AuthN/AuthZ nếu dùng session và form mutations.
- [ ] HTTP caching không chia sẻ HTML riêng tư qua shared proxies.
- [ ] Resource URLs/CSP/redirect targets được validate.
- [ ] Tests xác minh HTML 200, HTML 404, redirect, escaping, JSON API.
- [ ] Theo dõi template render time, codec buffers, event-loop lag và GC.
- [ ] Không thêm Servlet-only JSP resolver vào Reactor Netty app.
- [ ] Biết rõ view cache khác HTTP response cache và data cache.

## 18. Câu hỏi ôn tập

**1.** WebFlux có thể render HTML template phía server không?  
**Đáp án:** Có. Nó có view resolution qua ViewResolutionResultHandler và view engines như Thymeleaf.

**2.** String `"home"` trong `@Controller` thường là gì?  
**Đáp án:** Logical view name.

**3.** String `"home"` trong `@RestController` thường là gì?  
**Đáp án:** Response body literal.

**4.** `Model` nằm ở package nào?  
**Đáp án:** `org.springframework.ui.Model`.

**5.** `ViewResolutionResultHandler` làm gì?  
**Đáp án:** Chọn View qua ViewResolver và điều phối render theo Model.

**6.** Thymeleaf Boot default template directory ở đâu?  
**Đáp án:** `src/main/resources/templates/`.

**7.** Với view name `"detail"`, default Thymeleaf tìm file nào?  
**Đáp án:** `classpath:/templates/detail.html`.

**8.** `Mono<Product>` đặt trong model có được resolve trước render không?  
**Đáp án:** Có theo Spring WebFlux view model resolution.

**9.** `Flux<Product>` trong model có nhất thiết stream từng item HTML ngay không?  
**Đáp án:** Không; framework có thể collect thành List trước view rendering.

**10.** Một Flux không bao giờ complete sẽ ảnh hưởng normal view thế nào?  
**Đáp án:** View có thể không render xong nếu đang chờ toàn bộ model.

**11.** Mono.empty từ repository có tự trả 404 cho HTML page không?  
**Đáp án:** Không; nên chọn Missing view + 404 tường minh.

**12.** WebFlux dùng Servlet ModelAndView cho view controller không?  
**Đáp án:** Không; Rendering là API phù hợp của reactive stack.

**13.** `Mono<Rendering>` biểu diễn điều gì?  
**Đáp án:** Async decision về template, model, status và headers.

**14.** `Mono<String>` trong HTML controller có thể biểu diễn gì?  
**Đáp án:** Tên view được cung cấp bất đồng bộ.

**15.** Vì sao `@RestController` không hiển thị Thymeleaf `home.html` khi trả "home"?  
**Đáp án:** Vì return value được ghi như body bởi @ResponseBody semantics.

**16.** `th:text` khác `th:utext` thế nào?  
**Đáp án:** th:text escape HTML, th:utext không escape.

**17.** Dùng untrusted template name có an toàn không?  
**Đáp án:** Không; cần allowlist tên template và kiểm soát redirect targets.

**18.** Return `redirect:/pages/home` khác `forward:...` thế nào?  
**Đáp án:** Redirect là phản hồi 3xx tạo request mới, WebFlux không hỗ trợ Servlet forward dispatch.

**19.** Template cache có lưu trang user A để gửi user B không?  
**Đáp án:** Template cache chủ yếu cache template structures, không nên trộn với HTTP response cache.

**20.** View rendering reactive có làm CPU template biến mất không?  
**Đáp án:** Không; render vẫn dùng CPU, memory và HTML encoding.

**21.** Form POST dùng cookie session có cần xét CSRF không?  
**Đáp án:** Có, cần policy Spring Security WebFlux phù hợp.

**22.** Nếu cả WebFlux và MVC starters cùng tồn tại, Boot mặc định chọn stack nào?  
**Đáp án:** Thường chọn MVC/Servlet.

**23.** Tại sao dùng Flux lớn để render HTML cần pagination?  
**Đáp án:** Tránh đợi quá lâu và giữ nhiều dữ liệu trong heap.

**24.** Test HTML nên so string y hệt từng whitespace không?  
**Đáp án:** Không; ưu tiên kiểm tra status, media type, cấu trúc và text quan trọng.

**25.** Nếu muốn cập nhật HTML từng phần khi dữ liệu mới đến, phải cân nhắc gì?  
**Đáp án:** Thymeleaf reactive streaming modes, fragments, SSE/HTML-over-the-wire, proxy buffering và browser update logic.

## 19. Tài liệu chính thức

- [Spring Framework 6.2 — DispatcherHandler / View Resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): `ViewResolutionResultHandler`, logical view names, reactive model attributes, redirects.
- [Spring Framework 6.2 — View Technologies](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-view.html): Thymeleaf, FreeMarker, Script Views, fragments và HTTP message writer views.
- [Spring Framework 6.2 — Controller Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/arguments.html): `Model`, model binding, request handling.
- [Spring Framework 6.2 — Model](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-modelattrib-methods.html): reactive attributes, `@ModelAttribute` lifecycle.
- [Spring Framework 6.2 — Controller Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html): `String` view names, Rendering, Model và HTTP body cases.
- [Spring Framework 6.2 — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): cấu hình ViewResolver/Content Negotiation.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): template engines, WebFlux/Boot auto-configuration, Reactor Netty runtime.
- [Thymeleaf — Spring Integration](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): Spring expressions, forms, reactive integration guidance.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): reactive HTTP testing.

**Kết luận:** WebFlux không chỉ trả Mono/Flux JSON. Với `@Controller`, `Model` và một view resolver như Thymeleaf reactive, bạn có thể render HTML phía server mà không tự chặn event-loop để đợi data. Tuy nhiên **reactive attributes có thể được gom trước render**, nên phải thiết kế pagination, timeout, escaping, authorization và streaming strategy theo đúng yêu cầu. Phân biệt rõ **view name**, **model data** và **HTTP response body** là chìa khóa để không nhầm WebFlux với REST-only hoặc Servlet MVC.
