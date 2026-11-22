# Phân biệt Controller, dữ liệu Model và bộ phân giải View trong Spring MVC

Trong Spring MVC, một request web có thể đi qua nhiều thành phần trước khi người dùng nhận được HTML hoặc JSON. Controller tiếp nhận request và điều phối use case; Model mang dữ liệu mà View cần; ViewResolver tìm cách tạo View từ tên logic; còn View thực hiện việc render nội dung phản hồi. Những thành phần này phối hợp với nhau nhưng có trách nhiệm khác nhau.

Một nhầm lẫn phổ biến là xem Model trong tham số Controller như toàn bộ mô hình nghiệp vụ, hoặc cho rằng ViewResolver trực tiếp chọn Controller. Thực tế, Spring MVC còn có DispatcherServlet, HandlerMapping, HandlerAdapter, các cơ chế xử lý kiểu trả về và HttpMessageConverter. Hiểu đúng chuỗi này giúp thiết kế Controller gọn, truyền dữ liệu đúng hợp đồng và lựa chọn chính xác giữa render View với trả JSON.

Bài học này tập trung vào cách ánh xạ ba vai trò Controller, Model và View trong Spring MVC. Nội dung cũng làm rõ Model, ModelAndView, @ModelAttribute, ViewResolver, luồng redirect và sự khác nhau giữa MVC view rendering với HTTP message conversion.

## 1. Ba vai trò trong Spring MVC

### Controller: tiếp nhận và điều phối request

Controller là adapter ở ranh giới HTTP. Nó nhận dữ liệu từ path, query string, header hoặc request body; thực hiện binding và validation; gọi application service/use case; sau đó quyết định phản hồi phù hợp.

Controller thường chịu trách nhiệm:

- Khai báo route và HTTP method bằng các annotation như @GetMapping, @PostMapping.
- Nhận dữ liệu đầu vào qua @PathVariable, @RequestParam, @RequestBody hoặc @ModelAttribute.
- Kích hoạt validation và xử lý lỗi binding.
- Gọi use case hoặc application service.
- Đưa dữ liệu cần trình bày vào Model hoặc tạo response body.
- Chọn View name, redirect hoặc HTTP status phù hợp.

Controller không nên trở thành nơi chứa toàn bộ quy tắc nghiệp vụ, truy vấn database tùy tiện hoặc chi tiết giao tiếp với từng dịch vụ ngoài.

### Model: dữ liệu được cung cấp cho View

Trong Spring MVC, org.springframework.ui.Model là một abstraction dạng key/value để Controller đặt dữ liệu cho View sử dụng. Ví dụ, Controller thêm danh sách đơn hàng dưới tên orders, rồi template đọc thuộc tính đó để render.

Đối tượng này không đồng nghĩa với Domain Model. Domain Model biểu diễn khái niệm, trạng thái và quy tắc nghiệp vụ; org.springframework.ui.Model chỉ là vùng chứa dữ liệu trình bày trong một lần xử lý request.

### View: trình bày dữ liệu thành response

View chịu trách nhiệm tạo representation, thường là HTML. Spring MVC có thể dùng Thymeleaf, JSP, FreeMarker hoặc một loại View khác. View nhận model attributes rồi render nội dung.

View nên tập trung vào trình bày và định dạng. Nó không nên tự gọi repository, tự thực hiện quy tắc nghiệp vụ hoặc quyết định quyền truy cập dữ liệu.

## 2. Không nhầm Domain Model với Spring UI Model

Từ Model được dùng ở nhiều ngữ cảnh:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Domain Model | Đối tượng và quy tắc nghiệp vụ | Order, Money, OrderStatus |
| Application data | Dữ liệu use case trả về | OrderDetail |
| View Model / DTO | Dữ liệu được chuẩn bị riêng cho màn hình | OrderDetailView |
| Spring UI Model | Container key/value đưa dữ liệu vào View | org.springframework.ui.Model |

Ví dụ Domain Model:

~~~java
public class Order {
    private final OrderId id;
    private OrderStatus status;

    public void cancel() {
        if (status == OrderStatus.SHIPPED) {
            throw new OrderCannotBeCancelled();
        }
        status = OrderStatus.CANCELLED;
    }
}
~~~

Đây là đối tượng nghiệp vụ có hành vi và bất biến. Controller không nên dùng org.springframework.ui.Model để thay thế đối tượng này hoặc đưa toàn bộ quy tắc vào các thuộc tính key/value.

Một View Model có thể chỉ chứa dữ liệu cần hiển thị:

~~~java
public record OrderDetailView(
        String orderNumber,
        String customerName,
        String statusLabel,
        List<OrderLineView> lines,
        BigDecimal total
) {}
~~~

Controller thêm View Model vào Spring UI Model:

~~~java
@GetMapping("/orders/{id}")
public String detail(
        @PathVariable long id,
        Model model
) {
    OrderDetailView detail = orderQueryService.getDetail(id);
    model.addAttribute("order", detail);
    return "orders/detail";
}
~~~

Trong ví dụ, OrderDetailView là dữ liệu trình bày; biến model là container Spring MVC; chuỗi orders/detail là tên logic của View. Ba khái niệm này có quan hệ nhưng không thể dùng thay cho nhau.

## 3. DispatcherServlet điều phối request như thế nào?

Trong Spring MVC, DispatcherServlet là front controller. Nó tiếp nhận request và điều phối tới thành phần xử lý phù hợp. Một luồng đơn giản:

~~~mermaid
flowchart TD
    R[HTTP Request] --> D[DispatcherServlet]
    D --> HM[HandlerMapping]
    HM --> H[Handler / Controller method]
    H --> HA[HandlerAdapter]
    HA --> C[Invoke Controller]
    C --> RV[Return value handling]
    RV -->|View name / ModelAndView| VR[ViewResolver]
    VR --> V[View]
    V --> RESP[HTTP Response]
    RV -->|Response body| MC[HttpMessageConverter]
    MC --> RESP
~~~

Các thành phần chính:

1. **DispatcherServlet:** nhận request và điều phối quá trình xử lý.
2. **HandlerMapping:** tìm handler phù hợp dựa trên URL, HTTP method, params, headers và các điều kiện mapping.
3. **HandlerAdapter:** biết cách gọi handler đã tìm được. Với annotated Controller, adapter hỗ trợ gọi method có các annotation Spring MVC.
4. **Return value handling:** diễn giải giá trị trả về của method, ví dụ tên View, ModelAndView, response body hoặc ResponseEntity.
5. **ViewResolver:** khi kết quả là tên View logic, tìm View phù hợp.
6. **View:** render nội dung thành response.
7. **HttpMessageConverter:** đọc request body hoặc ghi response body cho các kiểu như JSON, XML và text khi dùng @RequestBody/@ResponseBody.

Sơ đồ là luồng khái quát. Spring còn có interceptor, argument resolver, exception resolver, content negotiation và các extension point khác.

## 4. HandlerMapping khác ViewResolver ở đâu?

Hai thành phần này thường bị nhầm vì đều tham gia lựa chọn thành phần trong request.

| Thành phần | Câu hỏi nó trả lời | Đầu vào điển hình | Kết quả |
|---|---|---|---|
| HandlerMapping | Request này được xử lý bởi handler nào? | URL, method, điều kiện request | Handler/Controller method |
| ViewResolver | Tên View logic này tương ứng với View nào? | View name và đôi khi locale | Đối tượng View |

Ví dụ request GET /orders/42 được HandlerMapping ánh xạ đến OrderController.detail. Method này trả về orders/detail. ViewResolver tìm template tương ứng, chẳng hạn template Thymeleaf orders/detail.html.

ViewResolver không chọn Controller. HandlerMapping cũng không tìm template HTML.

## 5. Controller trả về tên View và dùng Model

Với một trang HTML, Controller thường nhận Model, thêm dữ liệu rồi trả về tên logic của View:

~~~java
@Controller
@RequestMapping("/products")
public class ProductController {

    private final ProductQueryService productQueryService;

    public ProductController(ProductQueryService productQueryService) {
        this.productQueryService = productQueryService;
    }

    @GetMapping
    public String list(Model model) {
        model.addAttribute(
                "products",
                productQueryService.findVisibleProducts()
        );
        return "products/list";
    }
}
~~~

Ở đây:

- @Controller đánh dấu component xử lý request và có thể trả tên View.
- Model là vùng chứa dữ liệu trình bày.
- addAttribute("products", ...) tạo model attribute tên products.
- return "products/list" trả tên logic, không phải đường dẫn file tuyệt đối.

Template Thymeleaf có thể dùng dữ liệu:

~~~html
<h1>Danh sách sản phẩm</h1>
<ul>
    <li th:each="product : ${products}">
        <span th:text="${product.name}">Tên sản phẩm</span>
        <span th:text="${product.price}">0</span>
    </li>
</ul>
~~~

Tên attribute phải thống nhất giữa Controller và View. Nếu Controller thêm items nhưng template đọc products, View sẽ không nhận được dữ liệu mong muốn.

## 6. Tên View logic không phải tên file

Khi Controller trả:

~~~java
return "products/list";
~~~

chuỗi products/list là tên logic. ViewResolver quyết định nó ánh xạ tới tài nguyên nào.

Ví dụ với cấu hình JSP:

~~~java
@Configuration
public class MvcViewConfiguration implements WebMvcConfigurer {

    @Bean
    public InternalResourceViewResolver jspViewResolver() {
        InternalResourceViewResolver resolver =
                new InternalResourceViewResolver();
        resolver.setPrefix("/WEB-INF/views/");
        resolver.setSuffix(".jsp");
        return resolver;
    }
}
~~~

Tên logic products/list được ghép thành /WEB-INF/views/products/list.jsp.

Với Spring Boot và Thymeleaf, starter thường tự cấu hình ViewResolver theo convention. Nếu đặt template tại src/main/resources/templates/products/list.html, Controller có thể trả products/list mà không cần tự tạo resolver thủ công.

Không nên ghép prefix/suffix trong Controller:

~~~java
// Không nên buộc Controller biết vị trí file template
return "/WEB-INF/views/products/list.jsp";
~~~

Giữ tên View logic giúp có thể đổi template engine hoặc vị trí tài nguyên mà ít ảnh hưởng Controller.

## 7. ViewResolver và View thực hiện những việc gì?

ViewResolver nhận tên logic và tìm một đối tượng View. View mới là thành phần thực hiện render.

Ví dụ:

- InternalResourceViewResolver ánh xạ tên View sang JSP hoặc tài nguyên Servlet phù hợp.
- ThymeleafViewResolver tìm template Thymeleaf và render với model.
- FreeMarkerViewResolver tìm template FreeMarker.
- ContentNegotiatingViewResolver có thể lựa chọn View dựa trên media type được thương lượng, thường phối hợp với các resolver khác.

Trong ứng dụng có nhiều resolver, thứ tự và cấu hình của chúng có ý nghĩa. Một resolver bắt được tên View quá rộng hoặc chạy trước resolver mong muốn có thể làm template không được tìm đúng.

Một View thường nhận model map và đối tượng request/response để render. Controller không cần tự đọc file HTML hoặc nối chuỗi HTML trong method.

## 8. Khi nào dùng ModelAndView?

ModelAndView kết hợp tên View và model attributes trong một đối tượng:

~~~java
@GetMapping("/orders/{id}/summary")
public ModelAndView summary(@PathVariable long id) {
    OrderSummaryView summary = orderQueryService.getSummary(id);

    ModelAndView result = new ModelAndView("orders/summary");
    result.addObject("summary", summary);
    return result;
}
~~~

Tương đương về ý nghĩa với cách dùng Model và trả về String:

~~~java
@GetMapping("/orders/{id}/summary")
public String summary(
        @PathVariable long id,
        Model model
) {
    model.addAttribute("summary", orderQueryService.getSummary(id));
    return "orders/summary";
}
~~~

Nên chọn một kiểu nhất quán theo convention của dự án. ModelAndView hữu ích khi muốn trả View và model như một kết quả gắn liền; Model cộng tên View thường dễ đọc khi method chủ yếu điều phối dữ liệu.

ModelAndView không phải một loại View và cũng không phải domain model.

## 9. @ModelAttribute có hai cách dùng quan trọng

Annotation @ModelAttribute xuất hiện ở cả tham số handler method và method riêng.

### 9.1. Binding form data vào object

~~~java
public record ProductSearchForm(
        String keyword,
        String category
) {}

@GetMapping("/products/search")
public String search(
        @ModelAttribute("form") ProductSearchForm form,
        Model model
) {
    model.addAttribute(
            "products",
            productQueryService.search(form.keyword(), form.category())
    );
    return "products/search";
}
~~~

Spring bind request parameters vào object form theo cơ chế data binding. Với dữ liệu đầu vào không tin cậy, nên dùng request/form DTO chỉ có các trường được phép bind. Không bind trực tiếp vào entity có nhiều trường nội bộ như role, owner ID, balance hoặc trạng thái.

### 9.2. Đưa dữ liệu dùng chung vào Model trước handler

~~~java
@Controller
@RequestMapping("/products")
public class ProductController {

    @ModelAttribute("categories")
    public List<CategoryOption> categories() {
        return categoryQueryService.findVisibleCategories();
    }

    // Các handler trong controller có thể dùng categories.
}
~~~

Method được đánh dấu @ModelAttribute có thể chạy trước các handler trong Controller để thêm dữ liệu vào model. Cần tránh đưa truy vấn nặng hoặc dữ liệu không cần thiết vào method dùng chung vì nó có thể chạy trên nhiều request.

## 10. Validation và BindingResult

Controller thường nhận form DTO với @Valid và BindingResult để kiểm tra dữ liệu trước khi gọi use case:

~~~java
public record CreateProductForm(
        @NotBlank @Size(max = 120) String name,
        @NotNull @DecimalMin("0.01") BigDecimal price
) {}

@PostMapping
public String create(
        @Valid @ModelAttribute("form") CreateProductForm form,
        BindingResult bindingResult
) {
    if (bindingResult.hasErrors()) {
        return "products/create";
    }

    productCommandService.create(
            new CreateProductCommand(form.name(), form.price())
    );
    return "redirect:/products";
}
~~~

BindingResult phải đặt ngay sau tham số được validate để nhận lỗi tương ứng. Khi có lỗi, Controller trả lại View form; template có thể hiển thị lỗi theo trường. Khi dữ liệu hợp lệ, Controller chuyển form thành command của use case.

Validation đầu vào không thay thế quy tắc nghiệp vụ. Ví dụ giá lớn hơn 0 có thể là validation của form, nhưng quy tắc một sản phẩm không thể được bán khi đã ngừng kinh doanh phải được kiểm tra trong application/domain layer.

## 11. Luồng POST-Redirect-GET và RedirectAttributes

Sau khi xử lý POST thành công, ứng dụng HTML thường redirect sang GET để tránh người dùng refresh trình duyệt và gửi lại form.

~~~java
@PostMapping
public String create(
        @Valid @ModelAttribute("form") CreateOrderForm form,
        BindingResult errors,
        RedirectAttributes redirect
) {
    if (errors.hasErrors()) {
        return "orders/create";
    }

    OrderId id = orderCommandService.create(form.toCommand());
    redirect.addFlashAttribute("notice", "Đã tạo đơn hàng.");
    return "redirect:/orders/" + id.value();
}
~~~

RedirectAttributes hỗ trợ thêm query parameters hoặc flash attributes. Flash attribute thường được lưu tạm qua redirect để trang GET tiếp theo hiển thị thông báo.

Tiền tố redirect: là chỉ dẫn đặc biệt để Spring tạo redirect response; nó không phải tên template thông thường. Tương tự, forward: yêu cầu forward nội bộ theo cơ chế Servlet. Hãy dùng redirect cho PRG và hiểu rõ khác biệt giữa redirect (client gửi request mới) với forward (server chuyển tiếp trong cùng request).

## 12. @Controller và @RestController chọn hai cách phản hồi khác nhau

Một điểm quan trọng khi ánh xạ View là phân biệt controller render HTML với controller trả dữ liệu trực tiếp.

### Controller render View

~~~java
@Controller
public class AccountPageController {
    @GetMapping("/account")
    public String account(Model model) {
        model.addAttribute("account", accountQueryService.getCurrentAccount());
        return "account/detail";
    }
}
~~~

Spring xem String là tên logic của View. ViewResolver được dùng để tìm View và render.

### REST Controller trả JSON

~~~java
@RestController
@RequestMapping("/api/accounts")
public class AccountApiController {
    @GetMapping("/me")
    public AccountResponse currentAccount() {
        return accountQueryService.getCurrentAccountResponse();
    }
}
~~~

@RestController tương đương @Controller kết hợp @ResponseBody. Đối tượng trả về được ghi vào HTTP response thông qua HttpMessageConverter, ví dụ Jackson chuyển DTO thành JSON. Không có bước tìm template bằng ViewResolver cho response body này.

Có thể dùng @ResponseBody trên một method trong @Controller nếu chỉ method đó trả dữ liệu trực tiếp:

~~~java
@Controller
public class ProductController {
    @ResponseBody
    @GetMapping("/api/products/{id}")
    public ProductResponse apiDetail(@PathVariable String id) {
        return productQueryService.getResponse(id);
    }
}
~~~

## 13. ViewResolver không xử lý JSON serialization

Hai luồng phản hồi cần phân biệt:

| Trường hợp | Cơ chế chính | Kết quả |
|---|---|---|
| @Controller trả tên View | ViewResolver rồi View | Render HTML/template |
| ModelAndView có View name | ViewResolver rồi View | Render View với model |
| @ResponseBody trả DTO | HttpMessageConverter | JSON/XML/text theo converter |
| @RestController trả DTO | HttpMessageConverter | JSON/XML/text theo converter |
| Trả ResponseEntity<DTO> | HttpMessageConverter cùng status/header | HTTP response body và metadata |

Ví dụ API:

~~~java
@GetMapping("/api/orders/{id}")
public ResponseEntity<OrderResponse> detail(@PathVariable long id) {
    OrderResponse response = orderQueryService.getResponse(id);
    return ResponseEntity.ok(response);
}
~~~

ResponseEntity cho phép điều khiển status và header. Nó không yêu cầu ViewResolver tìm template.

Nếu một method trả String trong @RestController, String đó thường là response body dạng text, không phải tên View. Ngược lại, String trong @Controller không có @ResponseBody thường được xem là tên View. Annotation và kiểu trả về cần được đọc cùng nhau.

## 14. Content negotiation và lựa chọn representation

Một ứng dụng có thể phục vụ nhiều representation, ví dụ HTML cho browser và JSON cho API client. Spring MVC có cơ chế content negotiation dựa trên request headers và cấu hình của ứng dụng.

Các thành phần có thể tham gia:

- Accept header từ client.
- produces trên @RequestMapping.
- HttpMessageConverter cho response body.
- ContentNegotiatingViewResolver khi ứng dụng dùng nhiều loại View.

Ví dụ route phân biệt representation:

~~~java
@GetMapping(value = "/orders/{id}", produces = MediaType.TEXT_HTML_VALUE)
public String htmlDetail(@PathVariable long id, Model model) {
    model.addAttribute("order", orderQueryService.getDetail(id));
    return "orders/detail";
}

@GetMapping(value = "/orders/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
@ResponseBody
public OrderResponse jsonDetail(@PathVariable long id) {
    return orderQueryService.getResponse(id);
}
~~~

Hai handler cùng một path nhưng khác điều kiện media type. Trong dự án thực tế, cần kiểm tra route không mơ hồ và định nghĩa hành vi khi client không gửi hoặc gửi Accept không tương thích.

Không nên dùng content negotiation chỉ để che giấu sự khác biệt giữa HTML page và API nếu hai loại response có bảo mật, validation hoặc versioning khác nhau. Có thể tách route /api/... khi điều đó làm hợp đồng rõ hơn.

## 15. Model attribute có thể được tạo tự động

Khi thêm một object bằng model.addAttribute(object) mà không truyền tên, Spring có thể suy ra tên từ kiểu dữ liệu hoặc quy tắc đặt tên attribute. Dù tiện, việc đặt tên tường minh thường dễ đọc và ổn định hơn:

~~~java
model.addAttribute("products", productList);
~~~

Tên attribute là một phần hợp đồng giữa Controller và View. Khi template dùng một tên cố định, hãy cân nhắc đặt tên rõ ràng để tránh thay đổi kiểu dữ liệu làm thay đổi tên suy ra.

## 16. Không đưa entity persistence trực tiếp vào View nếu không cần

Controller có thể thêm một JPA entity vào Model, nhưng điều đó có thể làm View phụ thuộc vào cấu trúc persistence:

- Template có thể truy cập quan hệ lazy và kích hoạt truy vấn ngoài dự kiến.
- View có thể làm phát sinh N+1 query.
- Trường nội bộ có thể bị render ngoài ý muốn.
- Thay đổi mapping entity có thể ảnh hưởng template.
- Render sau khi transaction đóng có thể gặp LazyInitializationException.

Nên dùng DTO/View Model chứa dữ liệu cần hiển thị:

~~~java
public record ProductRowView(
        String code,
        String name,
        String categoryName,
        String formattedPrice
) {}
~~~

Query service có thể lấy dữ liệu bằng projection hoặc mapping phù hợp rồi trả List<ProductRowView>. Controller chỉ đặt danh sách này vào Model.

## 17. View không nên truy cập database hoặc thực hiện authorization

Một template có thể dùng điều kiện để ẩn/hiện thành phần giao diện, nhưng việc ẩn nút không bảo vệ endpoint. Authorization phải được kiểm tra ở security layer và application/service layer phù hợp.

Tương tự, View không nên gọi repository để tự lấy dữ liệu. Khi View truy cập persistence:

- Trách nhiệm trình bày và truy vấn bị trộn.
- Hiệu năng khó dự đoán.
- Khó kiểm thử template độc lập.
- Quyền truy cập dữ liệu có thể bị bỏ qua.

Controller hoặc query service chuẩn bị model đã được phân quyền. View chỉ hiển thị những trường cần thiết. Việc ẩn một nút thao tác trong template là cải thiện trải nghiệm, không phải ranh giới bảo mật.

## 18. Kiểm thử Controller và View mapping

Spring MVC Test với MockMvc có thể kiểm tra Controller mà không cần mở server thật.

Ví dụ xác minh View name và model:

~~~java
@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    ProductQueryService productQueryService;

    @Test
    void listUsesTheExpectedViewAndModelAttribute() throws Exception {
        given(productQueryService.findVisibleProducts())
                .willReturn(List.of(
                        new ProductRowView(
                                "P-1", "Bàn phím", "Phụ kiện", "500.000"
                        )
                ));

        mockMvc.perform(get("/products"))
                .andExpect(status().isOk())
                .andExpect(view().name("products/list"))
                .andExpect(model().attributeExists("products"));
    }
}
~~~

Test này kiểm tra Controller trả đúng tên View và attribute. Nó không chứng minh file template thực sự render được. Muốn kiểm tra template, cần thêm test render/integration phù hợp với template engine đang dùng.

### 18.1. Kiểm thử API không đi qua ViewResolver

~~~java
@WebMvcTest(AccountApiController.class)
class AccountApiControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    AccountQueryService accountQueryService;

    @Test
    void apiReturnsJsonBody() throws Exception {
        given(accountQueryService.getCurrentAccountResponse())
                .willReturn(new AccountResponse("An", "an@example.test"));

        mockMvc.perform(get("/api/accounts/me")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$.displayName").value("An"));
    }
}
~~~

Test xác minh response JSON theo hợp đồng. Không cần assertion tên View vì method dùng @RestController và response body được ghi qua message converter.

## 19. Lỗi thường gặp khi cấu hình Controller, Model và ViewResolver

### Trả sai tên View

Controller trả product/list nhưng template thực tế ở products/list.html. ViewResolver không tìm được tài nguyên và ứng dụng có thể báo lỗi render. Hãy thống nhất tên logic với cấu trúc template.

### Nghĩ rằng String luôn là response body

Trong @Controller, String thường là tên View. Trong @RestController hoặc method có @ResponseBody, String là body. Kiểm tra annotation trước khi suy luận.

### Nghĩ rằng ViewResolver xử lý JSON

JSON được serialize qua HttpMessageConverter. ViewResolver dành cho việc tìm View từ tên logic.

### Đưa entity đầy đủ vào Model

Điều này có thể làm lộ trường nội bộ, kích hoạt lazy loading và tạo truy vấn không mong muốn. Ưu tiên View Model/DTO.

### Đặt dữ liệu vào Model nhưng template đọc tên khác

Tên model attribute là hợp đồng. Dùng tên tường minh và kiểm thử model attribute.

### Đặt BindingResult sai vị trí

BindingResult cần đứng ngay sau tham số được validate để Spring liên kết lỗi đúng đối tượng.

### Dùng @ModelAttribute trên entity nhiều trường

Data binding có thể cho phép client thay đổi trường ngoài ý muốn. Dùng form DTO giới hạn trường và kiểm tra quyền ở tầng ứng dụng.

### Đặt truy vấn nặng trong method @ModelAttribute dùng chung

Method này có thể chạy trước nhiều handler. Chỉ đưa dữ liệu thực sự cần cho các View liên quan và cân nhắc chi phí truy vấn.

### Nhầm redirect với render View

redirect:/orders yêu cầu trình duyệt gửi request mới. Nó không render template tên redirect:/orders.

## 20. Quy trình lần theo một request khi View không hiển thị đúng

Khi một trang không render hoặc thiếu dữ liệu, có thể kiểm tra theo thứ tự:

1. **Route:** HandlerMapping có ánh xạ request đến đúng Controller method không?
2. **Binding:** tham số path/query/form có được bind đúng không?
3. **Controller:** method có được gọi và có tạo model attribute cần thiết không?
4. **Tên View:** method trả về đúng tên logic chưa?
5. **ViewResolver:** resolver nào xử lý tên đó, prefix/suffix và template location có đúng không?
6. **View rendering:** template có lỗi cú pháp hoặc truy cập thuộc tính không hợp lệ không?
7. **Response:** status, content type và response body có đúng không?

Nếu endpoint là API, kiểm tra method có @ResponseBody/@RestController, Accept header và HttpMessageConverter thay vì tìm template. Cách phân nhánh này giúp tránh mất thời gian chỉnh ViewResolver cho một response thực chất đang được serialize thành JSON.

## 21. Checklist review Controller, Model và ViewResolver

- [ ] Controller tập trung vào HTTP, binding, validation và gọi use case.
- [ ] Quy tắc nghiệp vụ không bị đặt trong Controller hoặc template.
- [ ] Phân biệt Domain Model, View Model và org.springframework.ui.Model.
- [ ] Model attributes có tên rõ ràng, thống nhất với template.
- [ ] Controller trả tên View logic thay vì đường dẫn file cụ thể.
- [ ] HandlerMapping được hiểu là thành phần tìm Controller/handler.
- [ ] ViewResolver được hiểu là thành phần tìm View từ tên logic.
- [ ] View chỉ trình bày dữ liệu và không tự truy cập repository.
- [ ] View Model/DTO giới hạn dữ liệu cần hiển thị.
- [ ] @ModelAttribute được dùng đúng cho binding hoặc dữ liệu chung.
- [ ] BindingResult đứng ngay sau tham số được validate.
- [ ] Redirect và PRG được dùng đúng cho form POST khi phù hợp.
- [ ] Phân biệt @Controller với @RestController và @ResponseBody.
- [ ] Hiểu JSON được ghi qua HttpMessageConverter, không qua ViewResolver.
- [ ] Có test cho View name, model attributes và API response.
- [ ] Có kiểm tra render template khi giao diện phụ thuộc template engine.

## Kết luận

Trong Spring MVC, Controller tiếp nhận và điều phối request; org.springframework.ui.Model mang dữ liệu trình bày; ViewResolver ánh xạ tên View logic thành đối tượng View; còn View render nội dung. Domain Model và View Model là các khái niệm dữ liệu khác với Spring UI Model. DispatcherServlet, HandlerMapping và HandlerAdapter xử lý định tuyến và gọi handler, trong khi HttpMessageConverter ghi response body cho @ResponseBody và @RestController. Nắm rõ các ranh giới này giúp Controller không phụ thuộc đường dẫn template, View không truy cập persistence và API JSON không bị nhầm với luồng render HTML.
