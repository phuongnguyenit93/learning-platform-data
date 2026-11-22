# View, ViewResolver và dữ liệu Model trong Spring WebFlux

## 1. Mục tiêu

Spring WebFlux có thể trả JSON cho API hoặc render HTML ở server bằng template engine. Khi render HTML, controller không cần tự nối chuỗi HTML. Thay vào đó, controller chuẩn bị dữ liệu trong **Model**, chọn một view theo tên logic hoặc tạo một đối tượng **Rendering**, rồi giao việc render cho cơ chế **ViewResolver** và **View**.

Ba khái niệm cốt lõi:

- **Model:** tập hợp thuộc tính có tên và giá trị để template sử dụng khi tạo response.
- **ViewResolver:** chuyển tên view logic, ví dụ products/list, thành một đối tượng View cụ thể.
- **View:** kết xuất model thành nội dung response, thường là HTML, nhưng cũng có thể là JSON/XML qua HttpMessageWriterView.

Spring WebFlux giữ quy trình này trong mô hình reactive. Controller có thể trả String, Mono<String>, Rendering, Mono<Rendering>, View, Model hoặc các giá trị model khác. Việc resolve và render được compose thành reactive pipeline.

Bài học trình bày luồng xử lý view, cách truyền dữ liệu bằng Model và @ModelAttribute, lựa chọn template engine, cấu hình FreeMarker/Thymeleaf, content negotiation, redirect, xử lý form và validation, model chứa Mono/Flux, HTML fragments, bảo mật template và kiểm thử bằng WebTestClient. Ví dụ hoàn chỉnh dùng Java 17+, Spring Boot 3.5.x và Spring Framework 6.2.x.

## 2. View, ViewResolver và Model là gì?

### 2.1. Model

Model là dữ liệu của một lần xử lý request. Controller có thể thêm thuộc tính bằng Model:

```java
@GetMapping("/products")
public String list(Model model) {
    model.addAttribute("title", "Product catalog");
    model.addAttribute("products", productService.findAll());
    return "products/list";
}
```

Trong ví dụ:

- products là tên thuộc tính.
- productService.findAll() là giá trị của thuộc tính.
- products/list là tên view logic.

Template products/list.ftl có thể đọc title và products để dựng trang HTML.

Model không phải database, không phải cache dùng chung và cũng không tự động tồn tại qua nhiều request. Mỗi lần request có model riêng. Nếu cần lưu dữ liệu giữa các request, hãy dùng database, session hoặc một cơ chế lưu trữ phù hợp; không xem Model là nơi lưu trạng thái lâu dài.

Model thường được truy cập qua các API:

| API | Vai trò |
| --- | --- |
| org.springframework.ui.Model | Interface để thêm, xóa và truy vấn thuộc tính model |
| ModelMap | Map có hỗ trợ các thao tác model |
| Map<String, Object> | Có thể dùng làm tập thuộc tính model trong chữ ký controller |
| @ModelAttribute | Khởi tạo, truy cập, bind hoặc đánh dấu một thuộc tính model |

### 2.2. View

View chịu trách nhiệm biến model thành nội dung response. Với HTML, View thường dùng một template engine như FreeMarker hoặc Thymeleaf.

Ở tầng framework, contract của View có dạng reactive:

```java
Mono<Void> render(
        Map<String, ?> model,
        MediaType contentType,
        ServerWebExchange exchange);
```

View nhận:

- Map chứa tên thuộc tính và giá trị tương ứng.
- MediaType đã được chọn cho response.
- ServerWebExchange đại diện cho HTTP request/response hiện tại.

Mono<Void> hoàn tất khi quá trình render hoàn tất. Nếu render lỗi, lỗi được truyền qua reactive chain để WebFlux xử lý.

### 2.3. ViewResolver

ViewResolver ánh xạ một tên view logic thành một View thực tế. Ví dụ controller trả products/list; FreeMarker resolver tìm template tương ứng và tạo FreeMarkerView.

Contract chính:

```java
Mono<View> resolveViewName(
        String viewName,
        Locale locale);
```

Resolver có thể:

- Trả Mono chứa View nếu nó xử lý được tên view.
- Trả Mono.empty() nếu không xử lý tên đó để resolver tiếp theo thử.
- Phát lỗi nếu quá trình resolve thất bại thực sự.

Tên view logic không nhất thiết là đường dẫn file. Quy tắc prefix, suffix và template loader phụ thuộc resolver/template engine.

Ví dụ:

| View name | Template được tìm |
| --- | --- |
| products/list | classpath:/templates/products/list.ftl |
| products/detail | classpath:/templates/products/detail.ftl |
| errors/not-found | classpath:/templates/errors/not-found.ftl |

Bảng trên minh họa cấu hình FreeMarker có template loader root là classpath:/templates và suffix .ftl.

## 3. Luồng xử lý view trong Spring WebFlux

Spring WebFlux sử dụng DispatcherHandler theo mô hình front controller. HandlerMapping tìm controller hoặc functional route, HandlerAdapter gọi handler, rồi HandlerResultHandler xử lý giá trị trả về.

Luồng tổng quát:

```text
HTTP request
    |
    v
DispatcherHandler
    |
    v
HandlerMapping
    |  tìm handler phù hợp
    v
HandlerAdapter
    |  gọi controller
    v
HandlerResult
    |  giá trị trả về + model
    v
HandlerResultHandler
    |
    +-- ResponseEntityResultHandler
    |
    +-- ResponseBodyResultHandler
    |
    +-- ViewResolutionResultHandler
             |
             v
         ViewResolver
             |
             v
            View
             |
             v
      HTML / JSON / XML response
```

Các result handler được đăng ký trong WebFlux configuration. Một số thứ tự mặc định quan trọng:

| Result handler | Giá trị thường xử lý | Order mặc định |
| --- | --- | --- |
| ResponseEntityResultHandler | ResponseEntity | 0 |
| ServerResponseResultHandler | ServerResponse của functional endpoints | 0 |
| ResponseBodyResultHandler | @ResponseBody hoặc @RestController | 100 |
| ViewResolutionResultHandler | CharSequence, View, Model, Map, Rendering và model attributes khác | Integer.MAX_VALUE |

Điều này giải thích vì sao controller có @RestController trả String sẽ ghi chuỗi vào response body thay vì tìm template. @RestController là annotation tổng hợp của @Controller và @ResponseBody.

Nếu muốn trả tên view để render HTML, dùng @Controller và không đánh dấu method bằng @ResponseBody.

### 3.1. View resolution khác response body encoding

Hai luồng thường bị nhầm:

- **Response body:** @ResponseBody, @RestController hoặc ResponseEntity. Giá trị được HttpMessageWriter encode thành response body.
- **View rendering:** @Controller trả tên view, View, Model, Map hoặc Rendering. ViewResolver chọn View rồi render model.

Ví dụ API:

```java
@RestController
public class ProductApiController {

    @GetMapping("/api/products")
    public Flux<Product> products() {
        return productService.findAll();
    }
}
```

Ví dụ HTML page:

```java
@Controller
public class ProductPageController {

    @GetMapping("/products")
    public String products(Model model) {
        model.addAttribute("products", productService.findAll());
        return "products/list";
    }
}
```

Cả hai có thể dùng cùng ProductService, nhưng cách tạo response khác nhau.

## 4. Các kiểu giá trị controller có thể trả về

ViewResolutionResultHandler xử lý nhiều loại return value. Những kiểu quan trọng:

| Return value | Ý nghĩa trong HTML controller |
| --- | --- |
| String / CharSequence | Tên view logic cần resolve |
| View | Dùng trực tiếp View instance |
| Model hoặc Map | Thêm thuộc tính vào model; tên view có thể suy ra từ request path |
| Rendering | Chỉ định view, model, status, headers hoặc redirect rõ ràng |
| POJO không phải simple type | Được xem là model attribute |
| @ModelAttribute trên method | Đánh dấu giá trị trả về là model attribute |
| void hoặc Mono<Void> | Có thể dùng default view name theo request path nếu response chưa được xử lý |
| Mono<String> | Khi hoàn tất, String được hiểu là view name trong @Controller |
| Mono<Rendering> | Rendering được tạo bất đồng bộ rồi dùng để render |

### 4.1. String là tên view trong @Controller

```java
@Controller
public class HomeController {

    @GetMapping("/")
    public String home() {
        return "home";
    }
}
```

Spring resolve tên home thành một View. Với FreeMarker và cấu hình mặc định, template có thể nằm tại src/main/resources/templates/home.ftlh hoặc phần mở rộng được cấu hình.

Nếu dùng @RestController:

```java
@RestController
public class HomeApiController {

    @GetMapping("/message")
    public String message() {
        return "Hello WebFlux";
    }
}
```

Response body là Hello WebFlux. Không có ViewResolver nào được gọi cho String này vì @RestController đã bật @ResponseBody.

### 4.2. Model hoặc Map và default view name

Controller có thể trả Model hoặc Map:

```java
@GetMapping("/products")
public Model products() {
    return new ExtendedModelMap()
            .addAttribute("title", "Products");
}
```

Khi không cung cấp view name, WebFlux có thể chọn default view name từ request path, loại bỏ dấu slash đầu/cuối. Với GET /products, tên view mặc định thường là products.

Cách này ngắn nhưng có thể khó đọc khi route và template không cùng quy ước. Trong controller có nhiều nhánh, trả String hoặc Rendering với view name tường minh thường dễ bảo trì hơn.

### 4.3. Rendering: chỉ định view và model rõ ràng

Rendering là API riêng của Spring WebFlux cho kịch bản kết hợp view và model. Nó tương tự ý tưởng ModelAndView của Spring MVC, nhưng dùng đúng abstraction của WebFlux.

```java
@GetMapping("/products")
public Rendering products() {
    return Rendering.view("products/list")
            .modelAttribute("title", "Products")
            .modelAttribute("products", productService.findAll())
            .build();
}
```

Rendering.Builder còn có thể đặt status, response headers và cookie. Ví dụ:

```java
return Rendering.view("products/list")
        .modelAttribute("products", products)
        .status(HttpStatus.OK)
        .header("X-Page", "catalog")
        .build();
```

Khi cần tạo view dựa trên kết quả reactive:

```java
@GetMapping("/products/{id}")
public Mono<Rendering> detail(@PathVariable long id) {
    return productService.findById(id)
            .map(product -> Rendering.view("products/detail")
                    .modelAttribute("product", product)
                    .build());
}
```

Không dùng org.springframework.web.servlet.ModelAndView trong WebFlux controller. Đó là API thuộc Spring MVC/Servlet stack; trong WebFlux hãy dùng Rendering hoặc các kiểu return value được WebFlux hỗ trợ.

## 5. Làm việc với Model

### 5.1. Thêm thuộc tính

Model có các thao tác phổ biến:

```java
@GetMapping("/dashboard")
public String dashboard(Model model) {
    model.addAttribute("title", "Dashboard");
    model.addAttribute("username", "An");
    model.addAttribute("notifications", 3);
    return "dashboard";
}
```

Tên thuộc tính phải ổn định và dễ hiểu. Nên dùng tên rõ ràng như product, products, currentUser, pageTitle thay vì phụ thuộc tên class được suy ra tự động.

Có thể truyền nhiều thuộc tính qua Map:

```java
@GetMapping("/dashboard")
public Rendering dashboard() {
    Map<String, Object> attributes = Map.of(
            "title", "Dashboard",
            "username", "An",
            "notifications", 3);

    return Rendering.view("dashboard")
            .modelAttributes(attributes)
            .build();
}
```

### 5.2. Tên model attribute

Khi dùng addAttribute(value) mà không chỉ định tên, Spring dùng quy tắc naming convention dựa trên kiểu object. Ví dụ Product có thể trở thành product.

Để template không phụ thuộc quy tắc suy luận, ưu tiên:

```java
model.addAttribute("product", product);
model.addAttribute("products", products);
```

Với method-level @ModelAttribute, tên có thể được đặt rõ:

```java
@ModelAttribute("pageTitle")
public String pageTitle() {
    return "Product catalog";
}
```

### 5.3. Thuộc tính model dùng chung trong controller

Method có @ModelAttribute ở cấp method được gọi trước handler method trong cùng controller. Nó phù hợp để thêm dữ liệu chung cho các view:

```java
@Controller
@RequestMapping("/products")
public class ProductPageController {

    @ModelAttribute("applicationName")
    public String applicationName() {
        return "Catalog";
    }

    @GetMapping
    public String list(Model model) {
        model.addAttribute("products", productService.findAll());
        return "products/list";
    }
}
```

Có thể chia sẻ dữ liệu cho nhiều controller bằng @ControllerAdvice có method @ModelAttribute. Chỉ nên đưa dữ liệu thực sự dùng chung; không biến method này thành nơi thực hiện nhiều truy vấn không cần thiết cho mọi request.

### 5.4. Model, @ModelAttribute và SessionAttributes

Ba khái niệm này có phạm vi khác nhau:

- Model: dữ liệu của request hiện tại, dùng khi render response.
- @ModelAttribute: annotation để khởi tạo/truy cập/bind một model object hoặc đánh dấu return value là model attribute.
- @SessionAttributes: cơ chế giữ một số model attribute qua nhiều request trong session theo quy trình được khai báo.

Không nên nhầm Model với session. Nếu một dữ liệu cần tồn tại sau khi response kết thúc, hãy chọn session, database hoặc store phù hợp.

## 6. @ModelAttribute và data binding cho form

### 6.1. Bind dữ liệu form vào object

Trong HTML controller, @ModelAttribute có thể bind form data, query parameters, URI path variables và request headers vào một object.

Ví dụ:

```java
@PostMapping("/products")
public String create(@ModelAttribute ProductForm form) {
    // form đã nhận dữ liệu từ request
    return "products/success";
}
```

Spring có thể tìm object đã tồn tại trong model, lấy từ session nếu cấu hình @SessionAttributes, hoặc tạo object mới bằng constructor phù hợp rồi bind dữ liệu request.

Form data và query parameters có độ ưu tiên cao hơn URI variables và headers khi tên trùng nhau. Header chỉ được dùng nếu không bị request parameter cùng tên ghi đè.

### 6.2. Dùng DTO chuyên biệt cho form

Không nên bind trực tiếp request vào JPA entity hoặc domain object có nhiều field nhạy cảm. Nếu binder cho phép client sửa mọi property, người dùng có thể gửi thêm field không hiển thị trên form để thay đổi trạng thái hoặc quyền ngoài ý muốn.

Tạo form DTO chỉ chứa những field được phép cập nhật:

```java
public class ProductForm {

    @NotBlank(message = "Name is required")
    @Size(max = 120, message = "Name must be at most 120 characters")
    private String name;

    @NotNull(message = "Price is required")
    @DecimalMin(value = "0.01", message = "Price must be at least 0.01")
    private BigDecimal price;

    public ProductForm() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }
}
```

Nếu cần constructor binding, có thể dùng record hoặc constructor rõ ràng và @BindParam để map tên request parameter. Nếu vẫn dùng property binding, hãy giới hạn allowed fields qua WebDataBinder/@InitBinder khi phù hợp.

### 6.3. Validation và BindingResult

Để validation chạy sau data binding, dùng @Valid hoặc @Validated:

```java
@PostMapping("/products")
public String create(
        @Valid @ModelAttribute("productForm") ProductForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return "products/form";
    }

    // Lưu dữ liệu sau khi validation thành công.
    return "redirect:/products";
}
```

BindingResult phải đứng ngay sau tham số @ModelAttribute mà nó mô tả. Nếu không có BindingResult, lỗi binding thường được biểu diễn bằng WebExchangeBindException.

Khi dùng reactive wrapper:

```java
@PostMapping("/products")
public Mono<String> create(
        @Valid @ModelAttribute("productForm") Mono<ProductForm> formMono) {

    return formMono
            .flatMap(form -> productService.create(form)
                    .thenReturn("redirect:/products"))
            .onErrorResume(WebExchangeBindException.class,
                    error -> Mono.just("products/form"));
}
```

Trong trường hợp này, lỗi được xử lý trong reactive chain. BindingResult không dùng theo cùng cách với tham số Mono<ProductForm>; nếu cần BindingResult làm tham số kế tiếp, khai báo model attribute không có reactive wrapper.

### 6.4. @ModelAttribute ở cấp method

Method-level @ModelAttribute có thể trả về một object để thêm vào model:

```java
@ModelAttribute("categories")
public List<Category> categories() {
    return categoryService.findAll();
}
```

Hoặc nhận Model và thêm nhiều thuộc tính:

```java
@ModelAttribute
public void populatePage(Model model) {
    model.addAttribute("applicationName", "Catalog");
    model.addAttribute("supportEmail", "support@example.test");
}
```

Các method này chạy trước handler method. Có thể chia sẻ qua @ControllerAdvice khi cần dùng ở nhiều controller.

## 7. Dữ liệu reactive trong Model

Spring WebFlux cho phép model chứa các kiểu reactive như Mono<T> hoặc Flux<T>. Trước khi render, AbstractView resolve các giá trị bất đồng bộ thành giá trị cụ thể rồi cập nhật model.

Quy tắc phổ biến:

- Mono<T> được resolve thành một giá trị T hoặc không có giá trị nếu publisher rỗng.
- Flux<T> được collect thành List<T>.
- Các kiểu reactive tương thích khác được xử lý thông qua ReactiveAdapterRegistry.

Ví dụ:

```java
@GetMapping("/products")
public String list(Model model) {
    model.addAttribute("products", productService.findAll());
    return "products/list";
}
```

Ở đây findAll() trả Flux<Product>. Trước khi FreeMarker render, Flux được thu thập thành List<Product> để template lặp qua.

**Lưu ý:** đặt Flux vào Model không đồng nghĩa template sẽ nhận từng phần tử ngay khi phát ra. View rendering chờ resolve model attribute; Flux được collect thành List. Vì vậy không đặt publisher vô hạn hoặc tập dữ liệu cực lớn vào model. Với dữ liệu lớn, phân trang hoặc giới hạn số phần tử; với UI cần stream fragment, xem phần HTML fragments/SSE.

## 8. ViewResolver và quá trình chọn View

### 8.1. Resolver chain

ViewResolutionResultHandler nhận tên view logic và thử các ViewResolver đã cấu hình. Resolver có thể trả view phù hợp hoặc Mono.empty() để resolver tiếp theo xử lý.

Các resolver thường được sắp xếp theo order. Một resolver chuyên biệt có thể xử lý tên theo prefix, trong khi resolver tổng quát xử lý các tên còn lại.

Không nên tạo nhiều resolver cùng nhận mọi tên view nếu không có quy tắc ưu tiên rõ ràng. Khi tên template không tồn tại, hãy kiểm tra resolver nào được chọn, prefix/suffix và template loader path.

### 8.2. ViewResolver và View là hai hợp đồng khác nhau

| Hợp đồng | Trách nhiệm |
| --- | --- |
| ViewResolver | Nhận tên view và Locale, resolve thành View |
| View | Nhận model, content type và ServerWebExchange rồi render response |
| ViewResolutionResultHandler | Kết nối return value của controller với resolver và view |
| Rendering | API tường minh để controller chỉ định view và model |

Một View tùy chỉnh cần triển khai render trả Mono<Void>, hỗ trợ media type phù hợp và xử lý nội dung response theo reactive lifecycle. Một ViewResolver tùy chỉnh thường triển khai resolveViewName trả Mono<View>.

### 8.3. Cấu hình ViewResolver

Spring WebFlux cung cấp WebFluxConfigurer và ViewResolverRegistry:

```java
@Configuration
public class WebViewConfiguration implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(ViewResolverRegistry registry) {
        registry.freeMarker();
    }
}
```

Registry có shortcut cho FreeMarker và script templates, đồng thời cho phép đăng ký một ViewResolver tùy chỉnh:

```java
@Override
public void configureViewResolvers(ViewResolverRegistry registry) {
    ViewResolver resolver = customViewResolver();
    registry.viewResolver(resolver);
}
```

Nếu dùng Spring Boot với starter template engine, thường có thể dựa vào auto-configuration. Chỉ cấu hình resolver thủ công khi cần kiểm soát prefix/suffix, thứ tự, default views hoặc tích hợp riêng. Tránh đăng ký trùng resolver với auto-configuration.

## 9. Template engines trong Spring WebFlux

### 9.1. FreeMarker

Spring Framework có tích hợp FreeMarker phía WebFlux. Spring Boot hỗ trợ auto-configuration cho FreeMarker và mặc định tìm template trong src/main/resources/templates.

Ưu điểm:

- Template dạng text linh hoạt, dùng được cho HTML và các định dạng văn bản.
- Có directive để lặp, điều kiện và macro.
- Có tích hợp Spring binding macros cho form.
- Có thể cấu hình template loader, settings và shared variables.

Spring Framework manual config có thể dùng:

```java
@Configuration
public class WebConfiguration implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(ViewResolverRegistry registry) {
        registry.freeMarker();
    }

    @Bean
    public FreeMarkerConfigurer freeMarkerConfigurer() {
        FreeMarkerConfigurer configurer = new FreeMarkerConfigurer();
        configurer.setTemplateLoaderPath("classpath:/templates/freemarker");
        return configurer;
    }
}
```

Với cấu hình này, view name welcome được resolve tới classpath:/templates/freemarker/welcome.ftl.

Trong Spring Boot, nếu dùng spring-boot-starter-freemarker thì template được auto-configure ở src/main/resources/templates. Không cần tạo FreeMarkerConfigurer thủ công nếu không có yêu cầu tùy biến.

### 9.2. Thymeleaf

Thymeleaf là template engine HTML phía server. Tích hợp Spring WebFlux được quản lý bởi dự án Thymeleaf và thường dùng các thành phần:

- SpringResourceTemplateResolver.
- SpringWebFluxTemplateEngine.
- ThymeleafReactiveViewResolver.

Spring Boot có auto-configuration cho Thymeleaf khi thêm starter tương ứng. Template thường đặt trong src/main/resources/templates. Thymeleaf phù hợp khi muốn HTML template có thể xem trước trong browser và có cú pháp thẻ/attribute rõ ràng.

### 9.3. Mustache và các engine khác

Spring Boot hỗ trợ Mustache trong reactive applications. Các template engine khác có thể tích hợp thông qua ViewResolver hoặc ScriptTemplateConfigurer nếu đáp ứng yêu cầu runtime.

Script views của Spring Framework dựa trên JSR-223 Java scripting engine; engine phải hỗ trợ ScriptEngine và Invocable. Đây là hướng mở rộng chuyên biệt, không phải lựa chọn mặc định cho ứng dụng mới nếu không có nhu cầu rõ ràng.

### 9.4. Template không nên do user không tin cậy chỉnh sửa

View chạy trong trust boundary nội bộ của ứng dụng và có thể truy cập Spring application context. Không cho phép người dùng cuối upload/chỉnh sửa template server-side rồi render trực tiếp nếu chưa thiết kế sandbox an toàn. Template phải là mã được kiểm soát, review và triển khai cùng ứng dụng.

## 10. Ví dụ hoàn chỉnh: Spring Boot WebFlux + FreeMarker

Ví dụ tạo trang danh sách sản phẩm, trang chi tiết và form thêm sản phẩm. Service trả reactive type, controller tạo Model/Rendering và FreeMarker render HTML.

### 10.1. Cấu trúc project

```text
src/
 +- main/
 |  +- java/demo/catalog/
 |  |  +- CatalogApplication.java
 |  |  +- Product.java
 |  |  +- ProductForm.java
 |  |  +- ProductCatalogService.java
 |  |  +- ProductPageController.java
 |  +- resources/
 |     +- templates/
 |        +- products/
 |        |  +- list.ftl
 |        |  +- detail.ftl
 |        |  +- form.ftl
 |        +- errors/
 |           +- not-found.ftl
 +- test/
    +- java/demo/catalog/
       +- ProductPageControllerTest.java
```

### 10.2. Dependencies

Tệp build.gradle:

```groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-freemarker'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Spring Boot quản lý version Spring Framework, Reactor, FreeMarker và các dependency liên quan qua dependency management. Không tự override riêng spring-webflux hoặc freemarker nếu không có yêu cầu tương thích cụ thể.

### 10.3. Cấu hình template

Tệp src/main/resources/application.properties:

```properties
spring.application.name=webflux-view-demo
spring.freemarker.template-loader-path=classpath:/templates/
spring.freemarker.suffix=.ftl
spring.freemarker.charset=UTF-8
```

Với Spring Boot auto-configuration, template được lấy từ src/main/resources/templates. Nếu cần cache hoặc cấu hình nâng cao, kiểm tra từng property vì không phải tính năng FreeMarker nào cũng được hỗ trợ trên WebFlux.

### 10.4. Application class

Tệp CatalogApplication.java:

```java
package demo.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

### 10.5. Product model

Tệp Product.java:

```java
package demo.catalog;

import java.math.BigDecimal;

public record Product(long id, String name, BigDecimal price) {
}
```

Product là kiểu dữ liệu chỉ đọc được dùng trong model của view.

### 10.6. Form DTO

Tệp ProductForm.java:

```java
package demo.catalog;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class ProductForm {

    @NotBlank(message = "Name is required")
    @Size(max = 120, message = "Name must be at most 120 characters")
    private String name;

    @NotNull(message = "Price is required")
    @DecimalMin(value = "0.01", message = "Price must be at least 0.01")
    private BigDecimal price;

    public ProductForm() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }
}
```

ProductForm chỉ chứa hai field mà người dùng được phép gửi. Controller sẽ chuyển DTO này sang service; không bind trực tiếp request vào entity có các field quản trị như ownerId, status hoặc createdAt.

### 10.7. ProductCatalogService

Tệp ProductCatalogService.java:

```java
package demo.catalog;

import java.math.BigDecimal;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductCatalogService {

    private final ConcurrentSkipListMap<Long, Product> products =
            new ConcurrentSkipListMap<>();

    private final AtomicLong ids = new AtomicLong(2);

    public ProductCatalogService() {
        products.put(1L, new Product(
                1L, "Keyboard", new BigDecimal("49.90")));
        products.put(2L, new Product(
                2L, "Mouse", new BigDecimal("19.50")));
    }

    public Flux<Product> findAll() {
        return Flux.defer(() -> Flux.fromIterable(products.values()));
    }

    public Mono<Product> findById(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(products.get(id)));
    }

    public Mono<Product> create(ProductForm form) {
        return Mono.fromSupplier(() -> {
            long id = ids.incrementAndGet();

            Product product = new Product(
                    id,
                    form.getName().trim(),
                    form.getPrice());

            products.put(id, product);
            return product;
        });
    }
}
```

Ví dụ dùng map đồng thời trong bộ nhớ để có thể chạy độc lập. Production thường thay bằng repository/database reactive. Việc tạo Product được bọc trong Mono để thực hiện khi publisher được subscribe.

### 10.8. Controller

Tệp ProductPageController.java:

```java
package demo.catalog;

import java.util.List;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.reactive.result.view.Rendering;

import reactor.core.publisher.Mono;

@Controller
@RequestMapping("/products")
public class ProductPageController {

    private final ProductCatalogService productService;

    public ProductPageController(ProductCatalogService productService) {
        this.productService = productService;
    }

    @ModelAttribute("applicationName")
    public String applicationName() {
        return "Product Catalog";
    }

    @GetMapping
    public String list(org.springframework.ui.Model model) {
        model.addAttribute("products", productService.findAll());
        return "products/list";
    }

    @GetMapping("/new")
    public Rendering newForm() {
        return Rendering.view("products/form")
                .modelAttribute("productForm", new ProductForm())
                .build();
    }

    @PostMapping
    public Mono<Rendering> create(
            @Valid @ModelAttribute("productForm") ProductForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            List<String> errors = bindingResult.getFieldErrors()
                    .stream()
                    .map(error -> error.getDefaultMessage() == null
                            ? "Invalid value"
                            : error.getDefaultMessage())
                    .toList();

            return Mono.just(Rendering.view("products/form")
                    .modelAttribute("productForm", form)
                    .modelAttribute("errors", errors)
                    .status(HttpStatus.BAD_REQUEST)
                    .build());
        }

        return productService.create(form)
                .thenReturn(Rendering.redirectTo("/products").build());
    }

    @GetMapping("/{id}")
    public Mono<Rendering> detail(@PathVariable long id) {
        return productService.findById(id)
                .map(product -> Rendering.view("products/detail")
                        .modelAttribute("product", product)
                        .build())
                .switchIfEmpty(Mono.just(
                        Rendering.view("errors/not-found")
                                .status(HttpStatus.NOT_FOUND)
                                .build()));
    }
}
```

Những điểm cần chú ý:

- @Controller cho phép String được hiểu là view name.
- @ModelAttribute("applicationName") bổ sung dữ liệu chung cho model của request.
- list() thêm Flux<Product> vào model. Trước khi render, Spring resolve Flux thành List<Product>.
- newForm() dùng Rendering để chọn view và truyền form object.
- create() dùng BindingResult ngay sau @ModelAttribute để xử lý validation errors.
- Khi lưu thành công, controller trả Rendering redirect để browser chuyển về danh sách.
- detail() trả Mono<Rendering>, vì dữ liệu sản phẩm được lấy bất đồng bộ.

### 10.9. Template danh sách

Tệp src/main/resources/templates/products/list.ftl:

```text
<#ftl output_format="HTML" auto_esc=true>
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>${pageTitle!"Products"}</title>
</head>
<body>
    <h1>${applicationName}</h1>
    <p>Danh sách sản phẩm</p>

    <p><a href="/products/new">Thêm sản phẩm</a></p>

    <#if products?has_content>
        <ul>
            <#list products as product>
                <li>
                    <a href="/products/${product.id?c}">
                        ${product.name}
                    </a>
                    -
                    ${product.price?string["0.00"]}
                </li>
            </#list>
        </ul>
    <#else>
        <p>Chưa có sản phẩm.</p>
    </#if>
</body>
</html>
```

Template đọc các thuộc tính model theo tên. FreeMarker HTML output format với auto_esc=true giúp escape nội dung được in ra HTML. Không dùng ?no_esc cho dữ liệu do user gửi nếu chưa có bước sanitize phù hợp.

### 10.10. Template form

Tệp src/main/resources/templates/products/form.ftl:

```text
<#ftl output_format="HTML" auto_esc=true>
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Thêm sản phẩm</title>
</head>
<body>
    <h1>Thêm sản phẩm</h1>

    <#if errors?? && errors?has_content>
        <ul>
            <#list errors as error>
                <li>${error}</li>
            </#list>
        </ul>
    </#if>

    <form method="post" action="/products">
        <div>
            <label for="name">Tên sản phẩm</label>
            <input
                id="name"
                name="name"
                type="text"
                value="${(productForm.name)!''}">
        </div>

        <div>
            <label for="price">Giá</label>
            <input
                id="price"
                name="price"
                type="number"
                min="0.01"
                step="0.01"
                value="${(productForm.price)!''}">
        </div>

        <button type="submit">Lưu</button>
    </form>

    <p><a href="/products">Quay lại danh sách</a></p>
</body>
</html>
```

Khi validation thất bại, controller trả lại chính view form cùng dữ liệu form và danh sách lỗi. Nhờ đó người dùng không mất nội dung đã nhập.

Nếu ứng dụng bật Spring Security CSRF, form POST cần gửi CSRF token theo cấu hình Spring Security. Với FreeMarker, có thể dùng Spring binding macros hoặc đưa token vào template một cách có kiểm soát; không bỏ CSRF protection chỉ để form chạy được.

### 10.11. Template chi tiết

Tệp src/main/resources/templates/products/detail.ftl:

```text
<#ftl output_format="HTML" auto_esc=true>
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>${product.name}</title>
</head>
<body>
    <h1>${product.name}</h1>
    <p>Mã sản phẩm: ${product.id?c}</p>
    <p>Giá: ${product.price?string["0.00"]}</p>
    <p><a href="/products">Quay lại danh sách</a></p>
</body>
</html>
```

### 10.12. Template 404

Tệp src/main/resources/templates/errors/not-found.ftl:

```text
<#ftl output_format="HTML" auto_esc=true>
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Không tìm thấy</title>
</head>
<body>
    <h1>Không tìm thấy sản phẩm</h1>
    <p>Sản phẩm không tồn tại hoặc đã bị xóa.</p>
    <a href="/products">Quay lại danh sách</a>
</body>
</html>
```

Controller đặt status 404 trong Rendering, vì vậy template vẫn được render nhưng response có status Not Found.

### 10.13. Chạy ứng dụng

Chạy:

```bash
./gradlew bootRun
```

Mở các URL:

| URL | Kết quả |
| --- | --- |
| http://localhost:8080/products | Danh sách sản phẩm |
| http://localhost:8080/products/new | Form thêm sản phẩm |
| http://localhost:8080/products/1 | Chi tiết Keyboard |
| http://localhost:8080/products/999 | Trang 404 |

Gửi form bằng curl:

```bash
curl -i -X POST http://localhost:8080/products   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode "name=Monitor"   --data-urlencode "price=149.90"
```

Request hợp lệ sẽ nhận response redirect tới /products. Giá trị được lưu trong service in-memory nên sẽ mất khi ứng dụng khởi động lại.

## 11. Kiểm thử view rendering bằng WebTestClient

WebTestClient có thể kiểm tra status, headers và nội dung HTML mà không cần browser.

Tệp ProductPageControllerTest.java:

```java
package demo.catalog;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductPageControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void rendersProductList() {
        client.get()
                .uri("/products")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.TEXT_HTML)
                .expectBody(String.class)
                .value(html -> {
                    assertTrue(html.contains("Product Catalog"));
                    assertTrue(html.contains("Keyboard"));
                    assertTrue(html.contains("Mouse"));
                });
    }

    @Test
    void invalidFormReturnsRenderedFormWithErrors() {
        client.post()
                .uri("/products")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "")
                        .with("price", "0"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.TEXT_HTML)
                .expectBody(String.class)
                .value(html -> {
                    assertTrue(html.contains("Name is required"));
                    assertTrue(html.contains("Price must be at least 0.01"));
                });
    }

    @Test
    void validFormRedirectsToProductList() {
        client.post()
                .uri("/products")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Monitor")
                        .with("price", "149.90"))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().value(
                        "Location",
                        location -> assertTrue(location.endsWith("/products")));
    }

    @Test
    void missingProductUsesNotFoundView() {
        client.get()
                .uri("/products/999999")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().isNotFound()
                .expectBody(String.class)
                .value(html ->
                        assertTrue(html.contains("Không tìm thấy sản phẩm")));
    }
}
```

Chạy:

```bash
./gradlew test
```

Các test kiểm tra cả view resolution, template rendering, form binding, validation, redirect và status 404. Đây là kiểm thử tích hợp qua HTTP server ngẫu nhiên, hữu ích hơn việc chỉ test controller method như một Java method độc lập.

## 12. Content negotiation: HTML, JSON và XML

ViewResolutionResultHandler hỗ trợ content negotiation. Nó so sánh media type client yêu cầu với media type mà các View hỗ trợ, rồi chọn view phù hợp.

Mặc định WebFlux xem Accept header để xác định requested media types. Có thể tùy chỉnh chiến lược bằng WebFluxConfigurer.configureContentTypeResolver, ví dụ bổ sung query parameter-based strategy.

### 12.1. HttpMessageWriterView

Để render model thành JSON hoặc XML qua view resolution, WebFlux có HttpMessageWriterView. View này bọc một HttpMessageWriter hoặc Encoder từ spring-web.

Khác với FreeMarker/Thymeleaf, HttpMessageWriterView không cần ViewResolver. Nó được đăng ký như một default view; khi requested media type phù hợp, default view được chọn.

Ví dụ với Spring Framework 6.2 và Jackson 2:

```java
@Configuration
public class JsonViewConfiguration implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(ViewResolverRegistry registry) {
        Jackson2JsonEncoder encoder = new Jackson2JsonEncoder();

        HttpMessageWriterView jsonView =
                new HttpMessageWriterView(encoder);

        jsonView.setModelKeys(Set.of("products"));
        registry.defaultViews(jsonView);
    }
}
```

Khi dùng Spring Framework 7 với Jackson 3, lớp encoder tương ứng là JacksonJsonEncoder. Hãy dùng đúng encoder theo version Spring và Jackson đang có trong dependency management.

setModelKeys chỉ định model attributes mà view được phép serialize. Nếu không cấu hình, view cần xác định thuộc tính phù hợp theo số lượng và khả năng ghi của HttpMessageWriter. Khi model có nhiều thuộc tính, chỉ định key giúp kết quả rõ ràng.

### 12.2. Khi nào nên dùng HttpMessageWriterView?

Phù hợp khi một controller muốn render cùng model theo nhiều media type, ví dụ HTML cho browser và JSON cho client khác. Tuy nhiên, nếu endpoint là REST API thuần, @RestController và HttpMessageWriter thường đơn giản hơn.

Không dùng một template HTML để tạo JSON bằng cách tự nối chuỗi. Hãy dùng HttpMessageWriter/Encoder để có escaping, serialization và Content-Type đúng.

## 13. Redirect và Rendering

### 13.1. redirect: prefix

Có thể trả tên view có prefix redirect:

```java
@PostMapping("/save")
public String save() {
    return "redirect:/products";
}
```

UrlBasedViewResolver nhận ra prefix redirect: và tạo redirect tới URL còn lại. redirect:/products là đường dẫn tương đối với ứng dụng hiện tại.

### 13.2. Rendering.redirectTo

Cách tường minh hơn:

```java
@PostMapping("/save")
public Mono<Rendering> save() {
    return productService.save()
            .thenReturn(Rendering.redirectTo("/products").build());
}
```

Rendering.redirectTo cũng hỗ trợ URI. Có thể đặt status hoặc headers trên builder khi contract cần.

### 13.3. Không có forward: trong WebFlux

Khác Servlet stack, Spring WebFlux không hỗ trợ FORWARD dispatch. Prefix forward: không phải cơ chế chuyển tiếp view hợp lệ trong WebFlux. Nếu muốn dùng lại dữ liệu/view, hãy gọi service rồi chọn view phù hợp trong cùng request hoặc redirect client tới URL khác.

## 14. HTML fragments và HTML-over-the-wire

Thông thường một request render một view với một model. Với HTMX hoặc Hotwire Turbo, server có thể trả các HTML fragment để browser thay một phần trang.

Spring WebFlux hỗ trợ:

- Collection<Fragment>.
- FragmentsRendering.
- Flux<Fragment> hoặc publisher tương thích.
- FragmentsRendering có Flux<Fragment> để stream fragment qua SSE.

Ví dụ:

```java
@GetMapping("/dashboard")
public FragmentsRendering dashboard() {
    return FragmentsRendering.fragment("dashboard/header")
            .fragment("dashboard/sidebar")
            .fragment("dashboard/content")
            .build();
}
```

Mỗi fragment có thể có model riêng và kế thừa các thuộc tính model chung của request.

Nếu cần stream fragment theo thời gian:

```java
@GetMapping(
        value = "/updates",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<Fragment> updates() {
    return Flux.interval(Duration.ofSeconds(2))
            .map(index -> Fragment.create(
                    "dashboard/update",
                    Map.of("index", index)));
}
```

Đây là hướng phù hợp cho HTML-over-the-wire. Nó khác với việc đặt Flux<Product> trong Model thông thường: model attribute Flux sẽ được collect thành List trước khi render, còn Flux<Fragment> là return type chuyên biệt cho fragment rendering/streaming.

## 15. Xử lý lỗi và trang lỗi

View rendering có thể thất bại vì template không tồn tại, model không có thuộc tính mong đợi, template syntax lỗi hoặc data source phát lỗi. Hãy phân biệt:

- Lỗi tìm view: kiểm tra tên view, prefix/suffix và template loader.
- Lỗi render: kiểm tra cú pháp template, dữ liệu null và kiểu dữ liệu.
- Lỗi nghiệp vụ: xử lý bằng exception handler hoặc nhánh controller phù hợp.
- Lỗi binding/validation: trả lại form cùng lỗi để người dùng sửa.

Có thể dùng @ExceptionHandler trong @Controller hoặc @ControllerAdvice để trả Rendering:

```java
@ControllerAdvice
public class PageExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public Rendering productNotFound(ProductNotFoundException error) {
        return Rendering.view("errors/not-found")
                .modelAttribute("message", "Product was not found")
                .status(HttpStatus.NOT_FOUND)
                .build();
    }
}
```

Đối với lỗi toàn ứng dụng, Spring Boot có WebExceptionHandler và hỗ trợ error views theo mã HTTP trong thư mục error. Có thể cung cấp template cho 404, 5xx hoặc error mặc định. Khi cần response cho máy, cân nhắc ProblemDetail/application/problem+json thay vì trang HTML.

Không trả stack trace, SQL, đường dẫn nội bộ hoặc secret trong model lỗi hiển thị cho người dùng.

## 16. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Controller trả String nhưng browser nhận plain text | Controller dùng @RestController hoặc @ResponseBody | Dùng @Controller cho view rendering |
| Template không được tìm thấy | Sai tên view, prefix, suffix hoặc template loader | Kiểm tra tên view và vị trí template |
| Trả products/list.html nhưng resolver tự thêm .ftl | Đã đưa extension vào tên view trong khi resolver tự cấu hình suffix | Trả tên logic products/list |
| Model attribute không xuất hiện trong template | Sai key hoặc addAttribute chưa được gọi | Dùng tên model thống nhất và kiểm tra model |
| Flux trong model không stream | AbstractView resolve Flux thành List trước render | Phân trang hoặc dùng Fragment/SSE nếu cần streaming |
| View trả lỗi content type | Media type của View không hỗ trợ Accept | Kiểm tra supported media types và default views |
| JSON view serialize nhiều thuộc tính không mong muốn | Không giới hạn model keys | Cấu hình HttpMessageWriterView.setModelKeys |
| Form validation không quay lại trang form | Không có BindingResult hoặc exception chưa được xử lý | Đặt BindingResult ngay sau @ModelAttribute |
| User sửa được field ngoài form | Bind trực tiếp domain object có quá nhiều property | Dùng DTO chuyên biệt, constructor binding hoặc allowedFields |
| Template in raw HTML từ input | Tắt auto-escape hoặc dùng no_esc | Bật HTML escaping, sanitize theo ngữ cảnh |
| Dùng Model như session | Nhầm phạm vi của model | Dùng session/store nếu cần giữ qua request |
| Dùng ModelAndView của Servlet trong WebFlux | Nhầm API MVC và reactive stack | Dùng Rendering |
| Dùng forward: | WebFlux không hỗ trợ forward dispatch | Dùng view trực tiếp hoặc redirect |
| Template tự gọi database/service | Đưa business logic vào view | Tải dữ liệu ở service/controller và đưa qua Model |
| Resolver tùy chỉnh không được gọi | Thứ tự resolver hoặc điều kiện tên view không phù hợp | Kiểm tra order và logic resolveViewName |
| Dùng template do user upload | Template có thể truy cập bean/application context | Chỉ render template tin cậy, được kiểm soát |
| Dùng Flux vô hạn trong Model | View chờ resolve model trước khi render | Dùng SSE/FragmentsRendering hoặc API streaming phù hợp |

## 17. Hiệu năng và bảo mật

### 17.1. Giữ template đơn giản

Template nên tập trung trình bày. Truy vấn database, gọi service từ xa, tính toán nghiệp vụ và authorization nên nằm trong service/controller. Việc template gọi nhiều nguồn dữ liệu làm khó kiểm soát latency và lỗi.

### 17.2. Tránh collect dữ liệu quá lớn

WebFlux tự resolve reactive model attributes trước khi render. Flux<T> được collect thành List<T>. Nếu danh sách có hàng triệu phần tử, bộ nhớ có thể tăng cao.

Hãy dùng pagination, giới hạn dữ liệu hoặc render fragment theo cơ chế streaming khi UI thực sự cần cập nhật dần.

### 17.3. Escape output theo ngữ cảnh

HTML text, attribute, URL, JavaScript và CSS có quy tắc escape khác nhau. Không dùng một phép replace chung cho mọi ngữ cảnh. Ưu tiên auto-escaping của template engine, tránh in raw HTML từ dữ liệu người dùng.

### 17.4. Không expose domain object nhạy cảm

Chỉ đưa các field cần thiết vào Model. Không đưa password hash, access token, internal flags, database entity lazy proxies hoặc object có dữ liệu nhạy cảm vào template. Dùng view model/DTO có cấu trúc rõ ràng.

### 17.5. Template là mã tin cậy

Template engine có thể truy cập các bean hoặc tính năng của application context. Không cho phép user bên ngoài chỉnh sửa template rồi render bằng quyền của server. Cần kiểm soát source template, review thay đổi và đóng gói template như một phần ứng dụng.

### 17.6. Cache và quan sát

Template engine có thể cache template đã biên dịch/parse, tùy engine và cấu hình. Kiểm tra khả năng cache cụ thể khi chạy trên WebFlux; ví dụ một số tính năng cache FreeMarker không được hỗ trợ trong reactive stack. Theo dõi thời gian resolve/render, số template lỗi, response size và latency của các publisher tạo model.

## 18. Checklist triển khai

Trước khi hoàn thiện HTML rendering trong WebFlux, kiểm tra:

1. Controller dùng @Controller nếu cần trả tên view.
2. Không có @ResponseBody/@RestController ngoài ý muốn.
3. Model attribute có tên rõ ràng và chỉ chứa dữ liệu template cần.
4. Tên view logic khớp resolver prefix/suffix và vị trí template.
5. ViewResolver được đăng ký đúng một lần và có order rõ ràng.
6. Return type phù hợp: String, View, Model, Map hoặc Rendering.
7. Dùng Rendering khi cần chỉ định view/model/status/headers rõ ràng.
8. Dữ liệu reactive trong model có giới hạn; Flux không vô hạn.
9. Form dùng DTO riêng, validation và BindingResult đúng vị trí.
10. Data binding không cho phép client thay đổi field nhạy cảm.
11. Template auto-escape dữ liệu HTML.
12. Accept header và default views được cấu hình nếu cần JSON/XML qua view rendering.
13. Redirect dùng redirect: hoặc Rendering.redirectTo; không dùng forward:.
14. Template không chứa truy vấn nghiệp vụ hoặc secret.
15. Test bằng WebTestClient cho HTML, status, validation, redirect và view lỗi.
16. Kiểm tra log và metric để phát hiện template resolve/render chậm hoặc lỗi.

## 19. Tóm tắt lựa chọn API

| Nhu cầu | API |
| --- | --- |
| Thêm dữ liệu vào model | Model.addAttribute(name, value) |
| Bind form/query/path/header vào object | @ModelAttribute |
| Thêm thuộc tính chung trước handler | Method-level @ModelAttribute |
| Chọn view bằng tên logic | Trả String trong @Controller |
| Chọn view và model tường minh | Rendering.view(name).modelAttribute(...).build() |
| Redirect | redirect:/path hoặc Rendering.redirectTo(path) |
| Đăng ký resolver | WebFluxConfigurer.configureViewResolvers |
| Resolve tên view | ViewResolver.resolveViewName(name, locale) |
| Render view | View.render(model, contentType, exchange) |
| Render JSON/XML qua view | HttpMessageWriterView |
| Render nhiều HTML fragment | FragmentsRendering hoặc Collection<Fragment> |
| Xử lý form validation | @Valid + BindingResult |
| Kiểm thử HTTP và HTML | WebTestClient |

## 20. Tài liệu tham khảo chính thức

- [Spring Framework – DispatcherHandler và View Resolution](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): luồng DispatcherHandler, HandlerResultHandler, ViewResolutionResultHandler, xử lý return value, reactive model attributes, redirect và content negotiation.
- [Spring Framework – View Technologies](https://docs.spring.io/spring-framework/reference/web/webflux-view.html): Thymeleaf, FreeMarker, script views, HTML fragments, JSON/XML và cảnh báo trust boundary của template.
- [Spring Framework – WebFlux Config](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): WebFluxConfigurer, ViewResolverRegistry, default views, HttpMessageWriterView và content type resolver.
- [Spring Framework – @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html): binding form/query/path/header, validation, BindingResult và reactive model attribute.
- [Spring Framework – @Controller](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann.html): khác biệt giữa @Controller và @RestController.
- [Spring Framework – Rendering Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/view/Rendering.html): builder để tạo view rendering, model attributes, status, headers và redirect.
- [Spring Framework – ViewResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/view/ViewResolver.html): contract resolveViewName trả Mono<View>.
- [Spring Framework – View Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/view/View.html): contract render trả Mono<Void>.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): template engines được auto-configure và vị trí template mặc định.
- [Spring Framework – Data Binding](https://docs.spring.io/spring-framework/reference/web/webflux/data-binding.html): constructor/property binding, WebDataBinder và cấu hình validation.

## 21. Ghi nhớ

**Model giữ dữ liệu của request; ViewResolver tìm View từ tên logic; View render dữ liệu thành response.** Trong WebFlux, toàn bộ quá trình được tích hợp vào reactive lifecycle: controller có thể trả Mono<Rendering>, ViewResolver trả Mono<View>, View.render trả Mono<Void>.

Dùng @Controller và tên view String cho trang đơn giản; dùng Rendering khi cần kiểm soát rõ view, model, status hoặc redirect. Dùng Model/@ModelAttribute để truyền dữ liệu và xử lý form; giữ DTO hẹp để tránh mass assignment. FreeMarker, Thymeleaf và Mustache đều có thể dùng với WebFlux. Nếu cần JSON/XML qua view resolution, cấu hình HttpMessageWriterView; nếu là REST API thuần, @RestController thường phù hợp hơn. Luôn nhớ rằng Mono/Flux trong Model được resolve trước khi template chạy, và template phải là mã tin cậy với output escaping phù hợp.
