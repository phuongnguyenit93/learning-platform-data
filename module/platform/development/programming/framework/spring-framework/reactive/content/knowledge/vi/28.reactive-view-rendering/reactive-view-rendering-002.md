# Trả tên view, Rendering và model chứa giá trị reactive trong Spring WebFlux

## 1. View rendering trong WebFlux là gì?

Spring WebFlux không chỉ phục vụ REST API trả JSON hoặc dữ liệu nhị phân. Ứng dụng cũng có thể render HTML phía server bằng template engine như Thymeleaf, FreeMarker hoặc Mustache. Controller chuẩn bị dữ liệu, chọn một view logic, rồi Spring kết hợp model với template để tạo response.

Ba khái niệm cần phân biệt:

- **View name** là tên logic của template, ví dụ \`catalog\` hoặc \`account/profile\`. Nó không phải đường dẫn file tuyệt đối.
- **View** là đối tượng biết cách render model thành response. Một \`ViewResolver\` tìm và tạo View từ view name.
- **Model** là tập thuộc tính dữ liệu mà template có thể truy cập, ví dụ \`pageTitle\`, \`featuredProduct\` và \`products\`.

Trong WebFlux, model còn có thể chứa giá trị reactive như \`Mono<Product>\` hoặc \`Flux<Product>\`. Spring resolve những publisher này trước khi gọi view để render. Nhờ đó controller có thể trả dữ liệu từ repository reactive mà không cần \`block()\` hoặc tự \`subscribe()\`.

## 2. Luồng xử lý từ controller đến template

~~~text
HTTP request
     |
     v
HandlerMapping tìm controller method
     |
     v
Controller trả String / Mono<String> / Rendering
và model attributes
     |
     v
ViewResolutionResultHandler
     |
     v
ViewResolver tìm View theo logical view name
     |
     v
AbstractView resolve model publishers
     |
     +--> Mono<T> thành T hoặc không có attribute
     |
     +--> Flux<T> được collect thành List<T>
     |
     v
View / Thymeleaf / FreeMarker render template
     |
     v
ServerHttpResponse ghi HTML
~~~

Các bước quan trọng:

1. WebFlux tìm handler cho request.
2. Controller trả về view name hoặc một đối tượng mô tả việc render.
3. \`ViewResolutionResultHandler\` nhận kết quả và model.
4. \`ViewResolver\` lần lượt tìm View có thể xử lý tên view.
5. Trước khi render, \`AbstractView\` resolve các model attribute reactive thành giá trị cụ thể.
6. Template engine đọc model đã resolve và tạo response.

View resolution là một phần của WebFlux result handling. Controller không tự đọc file HTML và không tự ghép chuỗi response trong trường hợp template rendering thông thường.

## 3. View name là tên logic, không phải tên file

Một controller có thể trả về một String để chọn view:

~~~java
@Controller
public class CatalogController {

    @GetMapping("/catalog")
    public String catalog() {
        return "catalog";
    }
}
~~~

Nếu cấu hình Thymeleaf mặc định của Spring Boot đang hoạt động, tên \`catalog\` thường được ánh xạ tới template:

~~~text
src/main/resources/templates/catalog.html
~~~

Cấu hình mặc định thường dùng:

- Prefix: \`classpath:/templates/\`
- Suffix: \`.html\`
- View name: \`catalog\`
- Template: \`classpath:/templates/catalog.html\`

Với thư mục con, view name có thể là \`account/profile\`, tương ứng \`templates/account/profile.html\`.

Không trả đường dẫn filesystem do người dùng gửi vào làm view name. View name nên được chọn từ các giá trị logic do ứng dụng kiểm soát; việc ghép view name từ input tùy ý có thể dẫn tới truy cập template ngoài dự kiến.

## 4. Các kiểu return value thường dùng cho view

Trong annotated controller, WebFlux hỗ trợ một số cách biểu diễn kết quả render:

| Return value | Ý nghĩa |
| --- | --- |
| \`String\` hoặc \`Mono<String>\` | Logical view name |
| \`View\` | Dùng trực tiếp View instance |
| \`Model\` hoặc \`Map<String, Object>\` | Thêm model attributes; view name mặc định có thể suy ra từ request path |
| Object model attribute | Thêm object vào model theo tên quy ước hoặc tên từ \`@ModelAttribute\` |
| \`Rendering\` hoặc \`Mono<Rendering>\` | Chọn view, model, status và headers trong một đối tượng |
| \`void\` hoặc publisher rỗng trong ngữ cảnh view | Có thể dùng default view name từ request path nếu response chưa được xử lý |

Ví dụ trả view name cùng model:

~~~java
@GetMapping("/catalog")
public String catalog(Model model) {
    model.addAttribute("pageTitle", "Product catalog");
    model.addAttribute("category", "Hardware");
    return "catalog";
}
~~~

Có thể trả reactive view name:

~~~java
@GetMapping("/catalog")
public Mono<String> catalog() {
    return Mono.just("catalog");
}
~~~

WebFlux unwrap reactive return value trước khi xử lý kết quả. Vì vậy, \`Mono<String>\` trong một controller render view có thể cung cấp view name sau khi publisher phát giá trị.

Nếu handler chỉ trả \`Model\` hoặc \`Map\` mà không chỉ định view name, WebFlux có thể chọn tên mặc định dựa trên request path sau khi bỏ dấu slash đầu/cuối. Ví dụ request \`/catalog\` có thể chọn view \`catalog\`. Hãy trả view name tường minh khi đường dẫn template khác với route hoặc khi muốn code dễ đọc hơn.

## 5. Model chứa giá trị reactive

Điểm đặc trưng của view rendering trong WebFlux là model có thể chứa publisher. Controller không cần đợi từng giá trị bằng cách block.

Ví dụ:

~~~java
@GetMapping("/catalog")
public Mono<String> catalog(Model model) {
    model.addAttribute("pageTitle", "Catalog");
    model.addAttribute("featuredProduct",
        productService.findFeatured());
    model.addAttribute("products",
        productService.findAll());

    return Mono.just("catalog");
}
~~~

Trong ví dụ:

- \`pageTitle\` là String bình thường.
- \`featuredProduct\` là \`Mono<Product>\`.
- \`products\` là \`Flux<Product>\`.
- Controller trả \`Mono<String>\` làm view name.

Trước khi render, WebFlux resolve model publisher:

| Giá trị trong model | Giá trị template nhận được |
| --- | --- |
| \`Mono<Product>\` phát một Product | Một Product |
| \`Mono.empty()\` | Không có attribute tương ứng trong model |
| \`Flux<Product>\` có nhiều phần tử | Một \`List<Product>\` chứa các phần tử |
| \`Flux.empty()\` | Một danh sách rỗng |
| Giá trị thường như String, Integer hoặc DTO | Giữ nguyên giá trị |

Cơ chế này được thực hiện ở tầng view, không phải bằng cách controller tự collect mọi Flux.

### 5.1. Mono trong model

Dùng \`Mono<T>\` khi attribute đại diện cho một kết quả đơn:

~~~java
model.addAttribute(
    "featuredProduct",
    productService.findFeatured()
);
~~~

Template có thể truy cập object sau khi Mono được resolve:

~~~html
<section th:if="\${featuredProduct != null}">
    <h2 th:text="\${featuredProduct.name}">Product name</h2>
</section>
~~~

Nếu Mono hoàn tất mà không phát giá trị, attribute đó không được thêm vào model đã resolve. Template nên kiểm tra sự tồn tại của attribute trước khi đọc thuộc tính con.

### 5.2. Flux trong model

Dùng \`Flux<T>\` khi service trả nhiều phần tử:

~~~java
model.addAttribute("products", productService.findAll());
~~~

Trước khi render, WebFlux thu thập các phần tử thành List. Template có thể lặp:

~~~html
<ul>
    <li th:each="product : \${products}">
        <span th:text="\${product.name}">Product name</span>
    </li>
</ul>
~~~

Đây là cách thuận tiện cho danh sách hữu hạn và có giới hạn kích thước. Nó không biến một template HTML thông thường thành stream vô hạn. Nếu Flux không bao giờ hoàn tất, bước resolve model cũng không thể hoàn tất để bắt đầu render toàn bộ view theo cách này.

### 5.3. Không block hoặc subscribe trong controller

Không làm như sau:

~~~java
Product product = productService.findFeatured().block();
model.addAttribute("featuredProduct", product);
return "catalog";
~~~

Cũng không tự subscribe:

~~~java
productService.findAll().subscribe(
    products -> model.addAttribute("products", products)
);
return "catalog";
~~~

Hai cách này phá vỡ reactive lifecycle: dữ liệu có thể chưa sẵn sàng khi render, lỗi khó truyền đúng và việc hủy request không còn điều khiển subscription như mong đợi.

Hãy đưa publisher trực tiếp vào model hoặc compose chúng thành một publisher trước khi trả kết quả:

~~~java
return productService.findFeatured()
    .map(product -> Rendering.view("catalog")
        .modelAttribute("pageTitle", "Catalog")
        .modelAttribute("featuredProduct", product)
        .build());
~~~

## 6. Lỗi, empty và cancellation khi resolve model

Model reactive vẫn tuân theo quy tắc của Reactor:

- \`Mono.empty()\` không tạo attribute cho model.
- \`Flux.empty()\` được resolve thành danh sách không có phần tử.
- Nếu publisher phát error, quá trình render bị lỗi và lỗi đi vào cơ chế exception handling của WebFlux.
- Nếu downstream bị cancel, subscription của các publisher đang resolve model có thể được hủy theo reactive lifecycle.

Không chuyển mọi lỗi service thành giá trị rỗng chỉ để template vẫn render. Nếu sản phẩm không tải được do lỗi database, việc đổi lỗi thành \`Mono.empty()\` có thể khiến giao diện trông như không có sản phẩm và che giấu sự cố. Hãy phân biệt trường hợp “không có dữ liệu” với “không tải được dữ liệu”.

Nếu có nhiều nguồn dữ liệu bắt buộc phải thành công cùng nhau, có thể kết hợp chúng bằng \`Mono.zip\` rồi tạo Rendering. Nếu một phần dữ liệu là tùy chọn, xử lý empty/fallback có chủ đích trước khi thêm vào model.

~~~java
return Mono.zip(
        productService.findFeatured(),
        categoryService.findVisible()
    )
    .map(tuple -> Rendering.view("catalog")
        .modelAttribute("featuredProduct", tuple.getT1())
        .modelAttribute("categories", tuple.getT2())
        .build());
~~~

Cách này tạo một điểm kết hợp rõ ràng khi controller cần một snapshot dữ liệu để chọn view. Với các model attribute độc lập, cũng có thể đưa Mono/Flux trực tiếp vào model và để view layer resolve.

## 7. Rendering: chọn view và model một cách tường minh

\`Rendering\` là API render dành cho annotated controller trong Spring WebFlux. Nó tương tự vai trò của \`ModelAndView\` trong Spring MVC, đồng thời hỗ trợ status và response headers.

Các thành phần có thể cấu hình:

- View name hoặc một View instance.
- Model attributes.
- HTTP status.
- HTTP headers.
- Redirect.

Ví dụ cơ bản:

~~~java
@GetMapping("/catalog/rendering")
public Rendering catalogRendering() {
    return Rendering.view("catalog")
        .modelAttribute("pageTitle", "Catalog")
        .modelAttribute("category", "Hardware")
        .build();
}
~~~

Có thể trả reactive wrapper:

~~~java
@GetMapping("/catalog/rendering")
public Mono<Rendering> catalogRendering() {
    return productService.findFeatured()
        .map(product -> Rendering.view("catalog")
            .modelAttribute("pageTitle", "Catalog")
            .modelAttribute("featuredProduct", product)
            .modelAttribute("products", productService.findAll())
            .build());
}
~~~

\`Rendering.view("catalog")\` tạo builder cho view name. \`modelAttribute(name, value)\` thêm một thuộc tính vào model. Giá trị của thuộc tính có thể là publisher reactive và được resolve trước khi render.

### 7.1. Thêm status và header

~~~java
@GetMapping("/catalog/rendering")
public Mono<Rendering> catalogRendering() {
    return productService.findAll().collectList()
        .map(products -> Rendering.view("catalog")
            .modelAttribute("pageTitle", "Catalog")
            .modelAttribute("products", products)
            .status(HttpStatus.OK)
            .header("X-Render-Mode", "rendering")
            .build());
}
~~~

Trong ví dụ này, \`collectList()\` được dùng có chủ đích để tạo một List trước khi xây Rendering. Có thể truyền trực tiếp Flux làm model attribute nếu muốn View layer resolve publisher; không cần collectList trong mọi trường hợp.

### 7.2. Dùng Map để thêm nhiều model attributes

~~~java
Map<String, Object> attributes = new HashMap<>();
attributes.put("pageTitle", "Catalog");
attributes.put("products", productService.findAll());

Rendering rendering = Rendering.view("catalog")
    .model(attributes)
    .build();
~~~

Các method thường gặp trên builder:

| Method | Tác dụng |
| --- | --- |
| \`view(name)\` | Chọn logical view name |
| \`modelAttribute(name, value)\` | Thêm một model attribute có tên rõ ràng |
| \`modelAttribute(value)\` | Thêm attribute với tên được suy ra |
| \`model(map)\` | Thêm nhiều attributes từ Map |
| \`modelAttributes(values...)\` | Thêm nhiều object với tên được suy ra |
| \`status(status)\` | Chọn HTTP status |
| \`header(name, values...)\` | Thêm response header |
| \`headers(httpHeaders)\` | Thêm tập response headers |
| \`build()\` | Tạo Rendering |

Ưu tiên tên tường minh với \`modelAttribute("products", ...)\` để template và controller cùng dùng một contract ổn định.

## 8. Redirect bằng Rendering

Khi controller muốn chuyển hướng, có thể dùng builder redirect:

~~~java
@GetMapping("/old-catalog")
public Rendering redirectCatalog() {
    return Rendering.redirectTo("/catalog").build();
}
~~~

Đường dẫn đích nên do ứng dụng quyết định. Không đưa trực tiếp URL do người dùng cung cấp vào redirect nếu chưa kiểm tra, vì có thể tạo open redirect.

Ngoài \`Rendering.redirectTo(...)\`, view resolver hỗ trợ một số quy ước view name như \`redirect:/catalog\` tùy resolver. Dùng Rendering giúp ý định redirect rõ ràng trong code WebFlux.

## 9. Phân biệt @Controller, @RestController và @ResponseBody

Đây là lỗi phổ biến khi bắt đầu dùng view rendering.

~~~java
@Controller
public class PageController {
    @GetMapping("/page")
    public Mono<String> page() {
        return Mono.just("catalog");
    }
}
~~~

Trong \`@Controller\`, String là logical view name nếu method không có \`@ResponseBody\`.

~~~java
@RestController
public class ApiController {
    @GetMapping("/api/message")
    public Mono<String> message() {
        return Mono.just("catalog");
    }
}
~~~

Trong \`@RestController\`, String được ghi vào response body. \`@RestController\` bao gồm semantics của \`@ResponseBody\`; nó không chọn template tên catalog.

Có thể dùng \`@ResponseBody\` cho một method cụ thể trong class \`@Controller\` khi method đó cần trả JSON hoặc text:

~~~java
@Controller
public class MixedController {
    @GetMapping("/page")
    public String page() {
        return "catalog";
    }

    @ResponseBody
    @GetMapping("/api/status")
    public Mono<String> status() {
        return Mono.just("ok");
    }
}
~~~

Hãy quyết định endpoint đang render HTML hay trả body API rồi chọn annotation tương ứng. Không dựa vào tên method hoặc nội dung String để đoán cách Spring xử lý.

## 10. ViewResolver và cấu hình view technology

\`ViewResolver\` nhận logical view name và trả về một \`View\` có thể render. Một ứng dụng có thể cấu hình một hoặc nhiều resolver; mỗi resolver có thể hỗ trợ một template engine hoặc một quy ước view khác nhau.

Spring WebFlux cung cấp \`WebFluxConfigurer.configureViewResolvers\` để tùy chỉnh:

~~~java
@Configuration
public class WebViewConfiguration implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(ViewResolverRegistry registry) {
        // Đăng ký ViewResolver tùy chỉnh nếu ứng dụng cần.
        // Ví dụ: registry.viewResolver(customResolver);
    }
}
~~~

Với Spring Boot, các template engine được hỗ trợ có auto-configuration. Khi thêm starter phù hợp, template mặc định được tìm trong \`src/main/resources/templates\`.

Không thêm \`@EnableWebFlux\` chỉ để tùy chỉnh một phần view resolver trong ứng dụng Spring Boot. \`@EnableWebFlux\` chuyển ứng dụng sang chế độ tự kiểm soát cấu hình WebFlux đầy đủ hơn và có thể làm mất một số customization của Boot. Dùng \`WebFluxConfigurer\` nếu chỉ cần bổ sung cấu hình.

### 10.1. Thymeleaf

Thymeleaf là template engine server-side thường dùng với Spring. Spring Boot có auto-configuration cho Thymeleaf trong WebFlux. Tích hợp reactive của Thymeleaf sử dụng các thành phần như \`SpringWebFluxTemplateEngine\` và \`ThymeleafReactiveViewResolver\`.

Template HTML thường đặt tại:

~~~text
src/main/resources/templates/catalog.html
~~~

Ví dụ:

~~~html
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="\${pageTitle}">Catalog</title>
</head>
<body>
    <h1 th:text="\${pageTitle}">Catalog</h1>

    <section th:if="\${featuredProduct != null}">
        <h2>Featured</h2>
        <p th:text="\${featuredProduct.name}">Featured product</p>
    </section>

    <ul>
        <li th:each="product : \${products}">
            <span th:text="\${product.name}">Product name</span>
            <span th:text="\${product.price}">0.00</span>
        </li>
    </ul>
</body>
</html>
~~~

\`th:text\` ghi nội dung dưới dạng text đã được escape theo ngữ cảnh HTML. Tránh dùng \`th:utext\` với nội dung không tin cậy vì nó chèn nội dung không escape vào HTML.

Template có quyền truy cập các bean trong application context theo cơ chế tích hợp của template engine. Vì vậy, chỉ dùng template nằm trong trust boundary của ứng dụng; không cho phép người dùng hoặc nguồn bên ngoài tùy ý sửa template có quyền truy cập bean.

### 10.2. FreeMarker và Mustache

Spring WebFlux cũng hỗ trợ FreeMarker và Mustache thông qua các tích hợp tương ứng. Cấu hình view resolver phụ thuộc template engine và dependency có trên classpath.

Spring Boot tự động tìm template trong thư mục templates theo cấu hình mặc định. Nếu thay prefix, suffix hoặc template resolver, hãy bảo đảm view name của controller khớp với đường dẫn template mới.

Không giả định mọi tính năng của một template engine đều hoạt động giống nhau giữa Servlet MVC và WebFlux. Kiểm tra tài liệu của tích hợp reactive khi dùng tính năng đặc thù.

## 11. Model reactive và template streaming

Một điểm quan trọng: model có \`Flux<T>\` không có nghĩa template tự động phát HTML từng item ngay khi upstream phát item.

Với view rendering thông thường, Spring resolve multi-value publisher thành List trước khi render. Điều này có nghĩa:

- Template nhận một collection đã hoàn tất.
- Nguồn Flux phải hoàn tất để có danh sách đầy đủ.
- Một Flux rất lớn có thể tiêu thụ nhiều bộ nhớ.
- Một Flux vô hạn không phù hợp làm model attribute cho một view render hoàn chỉnh.

Nếu cần hiển thị danh sách lớn, hãy phân trang hoặc giới hạn số bản ghi:

~~~java
Flux<Product> products =
    productService.findPage(page, pageSize);

model.addAttribute("products", products);
~~~

Nếu cần cập nhật giao diện liên tục theo thời gian, hãy chọn cơ chế phù hợp với streaming như SSE, WebSocket hoặc HTML fragments. Không dùng một Flux vô hạn làm model attribute cho template thông thường.

Spring WebFlux cũng có hỗ trợ HTML fragments để các ứng dụng HTMX/Hotwire cập nhật từng vùng giao diện. API \`FragmentsRendering\` hoặc \`Flux<Fragment>\` có thể biểu diễn nhiều fragment, mỗi fragment có model riêng và có thể kế thừa model chung của request. Đây là một hướng riêng cho HTML-over-the-wire.

## 12. Dùng view để trả JSON/XML theo content negotiation

View resolution không chỉ giới hạn ở HTML. WebFlux cung cấp \`HttpMessageWriterView\` để dùng codec sẵn có như Jackson JSON encoder hoặc XML encoder trong view layer.

Khác với template engine thông thường, \`HttpMessageWriterView\` không cần ViewResolver để tìm template file. Nó được cấu hình như default view và chọn writer phù hợp với media type được yêu cầu.

Ví dụ cấu hình ý tưởng:

~~~java
@Configuration
public class WebViewConfiguration implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(ViewResolverRegistry registry) {
        // Có thể đăng ký template resolver cho HTML tại đây.
        // Có thể thêm HttpMessageWriterView làm default view
        // nếu cần content negotiation cho JSON/XML.
    }
}
~~~

Trong REST API thông thường, \`@ResponseBody\` hoặc \`ResponseEntity\` vẫn là cách dễ hiểu để trả JSON. Dùng \`HttpMessageWriterView\` khi ứng dụng có chủ đích dùng cùng mô hình view resolution cho nhiều representation.

## 13. WebFlux.fn: RenderingResponse cho functional endpoints

Annotated controller dùng \`org.springframework.web.reactive.result.view.Rendering\`. Với functional endpoint WebFlux.fn, API tương ứng là \`RenderingResponse\` trong package \`org.springframework.web.reactive.function.server\`.

Ví dụ:

~~~java
Mono<RenderingResponse> renderCatalog(ProductService products) {
    return RenderingResponse.create("catalog")
        .modelAttribute("pageTitle", "Functional catalog")
        .modelAttribute("products", products.findAll())
        .build();
}
~~~

\`RenderingResponse\` là một subtype của \`ServerResponse\`, có tên template và model riêng. Nó phù hợp với handler function trả \`Mono<ServerResponse>\`.

Phân biệt hai API:

| Kiểu ứng dụng | API render |
| --- | --- |
| Annotated controller với \`@Controller\` | \`Rendering\` |
| Functional endpoint WebFlux.fn | \`RenderingResponse\` |
| REST endpoint trả JSON | \`@ResponseBody\`, \`ResponseEntity\` hoặc \`ServerResponse.body(...)\` |

Không dùng nhầm \`RenderingResponse\` với \`Rendering\`; chúng thuộc hai programming model khác nhau.

## 14. Java 17+ Spring Boot WebFlux demo hoàn chỉnh

Demo dùng Spring Boot 3.5.6, Java 17 và Thymeleaf. Hai endpoint render cùng một template:

- \`GET /catalog\` trả \`Mono<String>\` làm view name và đặt reactive values trong Model.
- \`GET /catalog/rendering\` trả \`Mono<Rendering>\`, chọn view, model, status và header tường minh.

### 14.1. Cấu trúc dự án

~~~text
webflux-view-demo/
  build.gradle
  src/
    main/java/demo/
      DemoApplication.java
      Product.java
      ProductService.java
      CatalogController.java
    main/resources/
      application.properties
      templates/
        catalog.html
    test/java/demo/
      CatalogControllerTest.java
~~~

### 14.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không thêm \`spring-boot-starter-web\` vào demo này vì mục tiêu là chạy reactive WebFlux application. Nếu cùng có hai starter web MVC và WebFlux, Spring Boot thường ưu tiên auto-configure MVC.

### 14.3. application.properties

~~~properties
spring.application.name=webflux-view-demo
spring.thymeleaf.cache=false
~~~

Spring Boot auto-configure Thymeleaf view resolver. Template được tìm trong \`classpath:/templates/\` với suffix mặc định \`.html\`.

### 14.4. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 14.5. Product.java

~~~java
package demo;

import java.math.BigDecimal;

public record Product(
    long id,
    String name,
    BigDecimal price
) {
}
~~~

### 14.6. ProductService.java

~~~java
package demo;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductService {

    public Mono<Product> findFeatured() {
        return Mono.just(new Product(
            1L,
            "Mechanical Keyboard",
            new BigDecimal("79.90")
        ));
    }

    public Flux<Product> findAll() {
        return Flux.just(
            new Product(1L, "Mechanical Keyboard",
                new BigDecimal("79.90")),
            new Product(2L, "Wireless Mouse",
                new BigDecimal("25.50")),
            new Product(3L, "USB-C Hub",
                new BigDecimal("39.00"))
        );
    }
}
~~~

Service dùng Mono cho một sản phẩm nổi bật và Flux cho danh sách. Dữ liệu cố định chỉ nhằm giúp demo có thể chạy ngay; trong ứng dụng thực tế, thay bằng reactive repository hoặc service phù hợp.

### 14.7. CatalogController.java

~~~java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;
import reactor.core.publisher.Mono;

@Controller
public class CatalogController {
    private final ProductService productService;

    public CatalogController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/catalog")
    public Mono<String> catalog(Model model) {
        model.addAttribute("pageTitle", "Catalog from view name");
        model.addAttribute(
            "featuredProduct",
            productService.findFeatured()
        );
        model.addAttribute(
            "products",
            productService.findAll()
        );

        return Mono.just("catalog");
    }

    @GetMapping("/catalog/rendering")
    public Mono<Rendering> catalogWithRendering() {
        return Mono.just(
            Rendering.view("catalog")
                .modelAttribute(
                    "pageTitle",
                    "Catalog from Rendering"
                )
                .modelAttribute(
                    "featuredProduct",
                    productService.findFeatured()
                )
                .modelAttribute(
                    "products",
                    productService.findAll()
                )
                .status(HttpStatus.OK)
                .header("X-Render-Mode", "rendering")
                .build()
        );
    }
}
~~~

Method đầu dùng Model để thêm attributes và trả logical view name. Method thứ hai dùng Rendering để gom view, model, status và response header. Cả hai truyền Mono/Flux trực tiếp vào model; WebFlux resolve chúng trước khi Thymeleaf render.

### 14.8. templates/catalog.html

~~~html
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="\${pageTitle}">Catalog</title>
</head>
<body>
    <h1 th:text="\${pageTitle}">Catalog</h1>

    <section th:if="\${featuredProduct != null}">
        <h2>Featured product</h2>
        <p th:text="\${featuredProduct.name}">
            Featured product name
        </p>
        <p th:text="\${featuredProduct.price}">
            0.00
        </p>
    </section>

    <h2>All products</h2>
    <ul>
        <li th:each="product : \${products}">
            <span th:text="\${product.name}">Product name</span>
            <span th:text="\${product.price}">0.00</span>
        </li>
    </ul>
</body>
</html>
~~~

Tên attribute trong template phải khớp với tên controller thêm vào model. Thymeleaf dùng \`th:each\` để lặp danh sách đã được WebFlux resolve từ Flux.

### 14.9. CatalogControllerTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CatalogControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void viewNameResolvesReactiveModelAttributes() {
        client.get()
            .uri("/catalog")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_HTML)
            .expectBody(String.class)
            .consumeWith(result -> {
                String html = result.getResponseBody();

                assertNotNull(html);
                assertTrue(html.contains("Catalog from view name"));
                assertTrue(html.contains("Mechanical Keyboard"));
                assertTrue(html.contains("Wireless Mouse"));
                assertTrue(html.contains("USB-C Hub"));
            });
    }

    @Test
    void renderingSelectsViewAndAddsResponseHeader() {
        client.get()
            .uri("/catalog/rendering")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_HTML)
            .expectHeader()
            .valueEquals("X-Render-Mode", "rendering")
            .expectBody(String.class)
            .consumeWith(result -> {
                String html = result.getResponseBody();

                assertNotNull(html);
                assertTrue(html.contains("Catalog from Rendering"));
                assertTrue(html.contains("Mechanical Keyboard"));
            });
    }
}
~~~

Test đầu xác minh view name được resolve và model Mono/Flux có dữ liệu khi template render. Test thứ hai xác minh Rendering chọn đúng view, thêm header và render model. WebTestClient kiểm tra HTML response thật thay vì chỉ kiểm tra object được controller trả về.

### 14.10. Chạy ứng dụng

Tại thư mục dự án:

~~~bash
./gradlew bootRun
~~~

Hoặc:

~~~bash
gradle bootRun
~~~

Mở hai endpoint:

~~~bash
curl -i http://localhost:8080/catalog
curl -i http://localhost:8080/catalog/rendering
~~~

Cả hai trả HTML với tiêu đề và danh sách sản phẩm. Endpoint thứ hai có thêm response header:

~~~http
X-Render-Mode: rendering
~~~

Chạy test:

~~~bash
./gradlew test
~~~

Hai test kiểm tra đường đi view name và Rendering, bao gồm việc resolve reactive model attributes và response header. Demo không cần Thread.sleep, block hoặc subscribe thủ công trong code production.

## 15. Lỗi thường gặp khi render view trong WebFlux

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Trả String từ \`@RestController\` và mong Spring tìm template | String được ghi thành response body | Dùng \`@Controller\` hoặc \`@ResponseBody\` đúng mục đích |
| Nhầm view name với đường dẫn file | Resolver không tìm được template | Trả logical name theo prefix/suffix đã cấu hình |
| Dùng sai tên model attribute | Template không thấy dữ liệu | Dùng tên rõ ràng trong \`addAttribute\` và \`modelAttribute\` |
| Gọi block để lấy Mono | Chặn thread reactive | Đưa publisher vào model hoặc compose publisher |
| Subscribe thủ công trong controller | Model có thể render trước khi dữ liệu đến | Return publisher cho WebFlux quản lý |
| Mong Mono.empty tạo attribute có giá trị null | Attribute không xuất hiện trong model đã resolve | Kiểm tra sự tồn tại của attribute trong template |
| Mong Flux trong model stream từng dòng HTML | Flux được collect thành List trước render thông thường | Phân trang hoặc dùng SSE/fragment streaming |
| Đưa Flux vô hạn vào model | View chờ publisher hoàn tất | Chỉ dùng publisher hữu hạn cho model view thông thường |
| Gom danh sách rất lớn vào model | Tốn bộ nhớ và tăng thời gian render | Phân trang, giới hạn số bản ghi hoặc stream qua endpoint khác |
| Dùng Rendering trong functional endpoint | Sai programming model | Dùng RenderingResponse của WebFlux.fn |
| Dùng RenderingResponse trong annotated controller | Sai loại return value | Dùng Rendering |
| Quên cấu hình template engine | Không có ViewResolver phù hợp | Thêm starter hoặc đăng ký resolver |
| Thêm @EnableWebFlux không cần thiết trong Boot | Có thể thay đổi auto-configuration | Dùng WebFluxConfigurer để bổ sung cấu hình |
| Trả view name từ input không tin cậy | Có thể chọn template ngoài ý muốn | Chọn view name từ whitelist hoặc logic nội bộ |
| Cho phép nguồn bên ngoài sửa template | Template có thể truy cập bean trong application context | Giữ template trong trust boundary của ứng dụng |
| Nuốt lỗi service thành empty | Giao diện hiển thị như không có dữ liệu và che giấu lỗi | Phân biệt lỗi với kết quả rỗng và xử lý rõ ràng |

## 16. Checklist thiết kế view rendering

Trước khi hoàn thiện controller, hãy kiểm tra:

1. Endpoint render HTML hay trả body JSON/text?
2. Controller có dùng \`@Controller\` thay vì vô tình dùng \`@RestController\` không?
3. View name có khớp quy tắc prefix/suffix của ViewResolver không?
4. Template file có nằm trong đúng thư mục không?
5. Tên model attribute có trùng với tên template đang đọc không?
6. Model có Mono/Flux nào cần resolve không?
7. Mono có thể empty không và template xử lý attribute vắng mặt thế nào?
8. Flux có hữu hạn và đủ nhỏ để collect thành List không?
9. Có thể truyền publisher trực tiếp vào model mà không block không?
10. Có cần Rendering để đặt status/header hoặc chọn view theo nhánh không?
11. Nếu dùng functional route, đã chọn RenderingResponse chưa?
12. Template có nằm trong trust boundary và escape dữ liệu đúng cách không?
13. Đã kiểm thử HTML response, status, headers và dữ liệu reactive chưa?

| Nhu cầu | Cách làm |
| --- | --- |
| Trả template theo tên | \`return "catalog"\` hoặc \`Mono.just("catalog")\` |
| Thêm model trong controller | \`Model.addAttribute(name, value)\` |
| Model chứa một giá trị async | \`Mono<T>\` |
| Model chứa danh sách async | \`Flux<T>\` được resolve thành List |
| Chọn view, model, status và header | \`Rendering.view(...)\` |
| Redirect | \`Rendering.redirectTo(...)\` |
| Functional endpoint render template | \`RenderingResponse.create(...)\` |
| Cấu hình ViewResolver | \`WebFluxConfigurer.configureViewResolvers(...)\` |
| Render JSON/XML qua view layer | \`HttpMessageWriterView\` |
| Kiểm thử HTML | \`WebTestClient\` |

## 17. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** View name có phải là đường dẫn file template không?

**Đáp án:** Không. Nó là tên logic được ViewResolver ánh xạ tới một View/template, ví dụ \`catalog\` được ánh xạ tới \`templates/catalog.html\` theo cấu hình mặc định.

**Câu 2.** Controller nào phù hợp để trả tên view?

**Đáp án:** Thường là \`@Controller\` method không có \`@ResponseBody\`. \`@RestController\` ghi String vào response body.

**Câu 3.** \`Mono<String>\` có thể là view name không?

**Đáp án:** Có. WebFlux resolve reactive return value rồi chuyển String đã phát tới view resolution handler.

**Câu 4.** \`Mono<Product>\` trong model được xử lý thế nào?

**Đáp án:** Spring resolve thành một Product nếu Mono phát giá trị; nếu Mono empty thì attribute không có trong model đã resolve.

**Câu 5.** \`Flux<Product>\` trong model được xử lý thế nào?

**Đáp án:** Spring collect các phần tử thành \`List<Product>\` trước khi render view thông thường.

**Câu 6.** Vì sao Flux vô hạn không phù hợp với model của template thông thường?

**Đáp án:** View cần resolve model trước khi render; Flux không hoàn tất thì danh sách không thể hoàn tất để render theo cách này.

**Câu 7.** Rendering khác String view name ở điểm nào?

**Đáp án:** Rendering đóng gói view cùng model attributes, HTTP status và headers; String chỉ chọn logical view name.

**Câu 8.** Rendering trong WebFlux tương tự API nào của Spring MVC?

**Đáp án:** Nó tương tự vai trò của ModelAndView, nhưng là API dành cho WebFlux.

**Câu 9.** Functional endpoint WebFlux.fn dùng Rendering hay RenderingResponse?

**Đáp án:** Dùng RenderingResponse; Rendering dành cho annotated controller.

**Câu 10.** Có nên gọi block hoặc subscribe trong controller để chuẩn bị model không?

**Đáp án:** Không. Đưa Mono/Flux vào model hoặc compose publisher để WebFlux quản lý subscription, lỗi và cancellation.

**Câu 11.** Nếu controller chỉ trả Model mà không có view name, WebFlux có thể chọn view nào?

**Đáp án:** View name mặc định có thể được suy ra từ request path sau khi bỏ dấu slash đầu/cuối.

**Câu 12.** Cần làm gì khi template không được tìm thấy?

**Đáp án:** Kiểm tra logical view name, prefix/suffix, thư mục templates, dependency template engine và cấu hình ViewResolver.

## 18. Ghi nhớ và tài liệu chính thức

- View name là tên logic; ViewResolver ánh xạ tên đó thành View.
- \`@Controller\` có thể trả String hoặc Mono<String> làm view name.
- \`@RestController\` và \`@ResponseBody\` dùng để ghi body, không chọn template.
- Model chứa dữ liệu thường hoặc reactive publisher.
- Mono được resolve thành một giá trị hoặc không có attribute nếu empty.
- Flux được collect thành List trước khi render view thông thường; không dùng Flux vô hạn cho model template.
- Rendering kết hợp view, model, status và headers trong annotated controller.
- RenderingResponse là API render tương ứng cho WebFlux.fn.
- Spring Boot hỗ trợ Thymeleaf, FreeMarker và Mustache; template mặc định nằm trong \`src/main/resources/templates\`.
- Không block hoặc subscribe thủ công trong controller.
- Giữ template trong trust boundary của ứng dụng và escape dữ liệu không tin cậy.

Tài liệu chính thức:

1. [Spring Framework Reference — DispatcherHandler và View Resolution](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): cách ViewResolutionResultHandler chọn view, xử lý return value và resolve reactive model attributes.
2. [Spring Framework Reference — View Technologies](https://docs.spring.io/spring-framework/reference/web/webflux-view.html): Thymeleaf, FreeMarker, HTML fragments, JSON/XML và các công nghệ view.
3. [Spring Framework Javadoc — Rendering](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/view/Rendering.html): API render cho annotated controllers.
4. [Spring Framework Javadoc — Rendering.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/view/Rendering.Builder.html): modelAttribute, model, status, header và build.
5. [Spring Framework Reference — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): ViewResolverRegistry và WebFluxConfigurer.
6. [Spring Framework Reference — Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): RouterFunction, ServerResponse và functional programming model.
7. [Spring Framework Javadoc — RenderingResponse](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/web/reactive/function/server/RenderingResponse.html): rendering response dành cho WebFlux.fn.
8. [Spring Boot Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): auto-configuration WebFlux và hỗ trợ template engine.
