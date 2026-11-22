# Cách đọc một nền tảng theo trách nhiệm Model, View và Controller

Khi học một nền tảng web, người mới thường tìm ba lớp có tên Model, View và Controller rồi ghép chúng thành sơ đồ MVC. Cách đọc này hữu ích khi framework dùng đúng thuật ngữ cổ điển, nhưng dễ gây nhầm khi tên gọi giữa các nền tảng khác nhau. Spring MVC có `Model` là nơi Controller đặt thuộc tính cho template; Django gọi hàm xử lý request là “view”; Rails thường dùng Active Record làm Model; ASP.NET Core MVC dùng model binding để tạo object từ request. Các thành phần có tên giống nhau chưa chắc có cùng trách nhiệm.

Vì vậy, hãy đọc một nền tảng theo **việc mỗi thành phần làm trong luồng request/response**, sau đó mới gắn nó vào vai trò Model, View hoặc Controller. Cách này giúp nhận diện đúng nơi tiếp nhận HTTP, nơi giữ quy tắc nghiệp vụ, nơi chuyển đổi dữ liệu, nơi render HTML hoặc serialize JSON, cùng những cơ chế validation, bảo mật và kiểm thử đi kèm.

Bài học này thuộc module Model–View–Controller: tổ chức ứng dụng để phân tách trạng thái/nghiệp vụ, trình bày và tiếp nhận tương tác. Khi đọc một nền tảng, mục tiêu không phải ghi nhớ tên annotation hay folder, mà là hiểu cách nền tảng hỗ trợ những trách nhiệm đó và cách chúng kết nối thành một ứng dụng có thể bảo trì.

## 1. Đọc theo trách nhiệm, không chỉ theo tên gọi

Ba vai trò MVC có thể được mô tả bằng những câu hỏi:

- **Model:** dữ liệu và quy tắc nào mô tả trạng thái, nghiệp vụ hoặc kết quả xử lý của ứng dụng?
- **View:** dữ liệu được trình bày thành HTML, giao diện hoặc response representation như thế nào?
- **Controller:** request hoặc tương tác đi vào hệ thống ở đâu, được chuyển thành hành động nào và kết quả được điều hướng ra sao?

Trong ứng dụng thực tế, mỗi vai trò có thể gồm nhiều thành phần. Nếu dùng “Model” theo nghĩa rộng để chỉ phần dữ liệu và nghiệp vụ phía sau giao diện, vùng này có thể gồm domain entity, value object, application service, repository và DTO; trong một kiến trúc phân lớp, các thành phần đó vẫn có trách nhiệm riêng. View có thể là template HTML, component UI hoặc bộ serialize JSON. Controller có thể bao gồm router, request handler, action method hoặc adapter nhận message.

Một số trách nhiệm thường nằm cạnh MVC nhưng không nên gộp tùy tiện vào ba vai trò:

| Trách nhiệm | Câu hỏi cần đặt ra |
|---|---|
| Routing | URL hoặc loại message nào được chuyển đến handler nào? |
| Binding | Dữ liệu request được chuyển thành kiểu dữ liệu ứng dụng ra sao? |
| Validation | Đầu vào sai cấu trúc hoặc vi phạm quy tắc bị phát hiện ở đâu? |
| Authentication | Hệ thống xác định người gọi là ai bằng cách nào? |
| Authorization | Người gọi có được phép thực hiện hành động hoặc xem tài nguyên không? |
| Transaction | Những thao tác dữ liệu nào phải thành công hoặc thất bại cùng nhau? |
| Serialization | Kết quả được chuyển thành JSON, XML hoặc định dạng khác ra sao? |
| Error handling | Lỗi được chuyển thành trang lỗi, redirect hay HTTP status nào? |

Những cơ chế này có thể được framework cung cấp, nhưng cần xác định chúng phục vụ vai trò nào và ranh giới nào của ứng dụng.

## 2. Một phương pháp đọc nền tảng theo từng bước

Khi mở tài liệu hoặc một dự án mẫu của framework, hãy đi theo luồng từ đầu vào đến đầu ra. Không cần bắt đầu bằng việc tìm class tên `Model`.

### Bước 1: Tìm điểm tiếp nhận request

Tìm cơ chế ánh xạ URL, HTTP method hoặc route đến handler. Hãy trả lời:

- Request đi vào ứng dụng qua thành phần nào?
- Route được khai báo bằng annotation, file cấu hình, convention hay hàm đăng ký?
- Path variable, query parameter, header và body được lấy ở đâu?
- Handler nào quyết định request này cần chạy use case nào?

Thành phần nhận request và điều phối hành động thường thuộc vai trò Controller hoặc input adapter.

### Bước 2: Tìm nơi chuyển đổi đầu vào

Tìm model binding, form binding, request DTO, command object và validation:

- Framework tự chuyển chuỗi thành số/ngày/enum ở đâu?
- Dữ liệu thiếu hoặc sai định dạng được báo thế nào?
- Validation chỉ kiểm tra cấu trúc hay có cả quy tắc nghiệp vụ?
- Dữ liệu danh tính và tenant đến từ nguồn tin cậy nào?

Request object thường là dữ liệu của adapter. Không nên mặc định nó chính là domain entity.

### Bước 3: Tìm nơi thực thi nghiệp vụ

Theo dõi handler gọi thành phần nào tiếp theo:

- Service hoặc use case nào thực hiện hành động?
- Quy tắc trạng thái và bất biến nằm trong entity, policy hay service?
- Thành phần nào truy cập database hoặc dịch vụ bên ngoài?
- Transaction bắt đầu và kết thúc ở đâu?

Đây thường là phần cốt lõi của Model theo nghĩa rộng, dù framework có thể đặt tên nó là service, manager, model, handler hoặc use case.

### Bước 4: Tìm dữ liệu đầu ra

Xác định kết quả nghiệp vụ được chuyển thành cấu trúc nào:

- ViewModel hoặc response DTO có được tạo riêng không?
- Có presenter, mapper hoặc serializer không?
- Trường nhạy cảm nào được loại bỏ?
- Nhãn trạng thái, tiền tệ và ngày giờ được định dạng ở đâu?

Kết quả use case và dữ liệu trình bày có thể khác nhau. Một ứng dụng có thể dùng chung application result cho HTML và JSON nhưng tạo hai DTO đầu ra riêng.

### Bước 5: Tìm nơi tạo response

Kiểm tra handler trả về loại kết quả nào:

- Tên template hoặc View object?
- Redirect đến URL khác?
- JSON response?
- File download hoặc stream?
- Status code và header nào được thiết lập?

Template hoặc component hiển thị thường thuộc vai trò View. Serializer cũng có thể đóng vai trò View cho API, dù không tạo HTML.

### Bước 6: Theo dõi các cơ chế xuyên suốt

Cuối cùng, xác định authentication, authorization, exception handling, logging, caching và transaction được kết nối vào luồng ở đâu. Không giả định vì framework có annotation cho một cơ chế thì mọi quy tắc bảo mật hoặc nghiệp vụ đã được xử lý.

~~~mermaid
flowchart TD
    A[Đọc route và điểm vào] --> B[Đọc binding và validation]
    B --> C[Theo dõi use case và domain]
    C --> D[Theo dõi repository và tích hợp]
    D --> E[Đọc application result]
    E --> F[Đọc presenter, ViewModel hoặc DTO]
    F --> G[Đọc template hoặc serializer]
    G --> H[Kiểm tra auth, lỗi, transaction và test]
~~~

## 3. Spring MVC: ánh xạ thành phần theo trách nhiệm

Spring MVC là ví dụ Java phổ biến cho mô hình request-driven MVC. Một request thường được Servlet container chuyển đến `DispatcherServlet`. DispatcherServlet tìm handler phù hợp, gọi handler thông qua HandlerAdapter rồi xử lý kết quả để tạo response.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant B as Browser / API Client
    participant D as DispatcherServlet
    participant M as HandlerMapping
    participant C as Controller
    participant S as Application Service
    participant R as Repository
    participant V as ViewResolver / Serializer
    B->>D: HTTP Request
    D->>M: Tìm handler
    M-->>D: Handler phù hợp
    D->>C: Gọi Controller qua HandlerAdapter
    C->>S: Gọi use case/service
    S->>R: Đọc hoặc ghi dữ liệu
    R-->>S: Kết quả
    S-->>C: Application result
    C-->>D: View name + Model hoặc response body
    D->>V: Render View hoặc serialize
    V-->>B: HTTP Response
~~~

Các thành phần quan trọng:

| Thành phần Spring | Trách nhiệm thực tế | Cách đọc theo MVC |
|---|---|---|
| `DispatcherServlet` | Front controller nhận request và điều phối | Điểm vào của Controller layer |
| `HandlerMapping` | Tìm handler phù hợp với request | Routing |
| `HandlerAdapter` | Gọi handler theo loại được hỗ trợ | Cơ chế thực thi Controller |
| `@Controller` | Đánh dấu component xử lý request và có thể trả View | Controller |
| `@RequestMapping`, `@GetMapping`, `@PostMapping` | Khai báo route và HTTP method | Routing của Controller |
| `@PathVariable`, `@RequestParam`, `@RequestHeader` | Bind dữ liệu từ request | Input binding |
| `@ModelAttribute` | Bind form hoặc đưa thuộc tính vào model | Adapter input / dữ liệu cho View, tùy cách dùng |
| `@RequestBody` | Đọc body và chuyển thành object bằng converter | Input binding cho API |
| `Model` | Chứa thuộc tính được chuyển sang View | View data carrier, không phải domain model |
| `ModelAndView` | Kết hợp tên View và dữ liệu model | Kết quả điều hướng/render |
| Thymeleaf/JSP | Render template thành HTML | View |
| `@ResponseBody`, `@RestController` | Ghi kết quả qua HttpMessageConverter | API output/serialization |
| `@ControllerAdvice` | Xử lý lỗi và binding ở phạm vi Controller | Adapter error handling |

### 3.1. Phân biệt `Model` của Spring và Domain Model

Trong Spring MVC, interface `org.springframework.ui.Model` là nơi Controller thêm thuộc tính để template sử dụng. Nó không phải đối tượng nghiệp vụ và cũng không phải một kho lưu trạng thái lâu dài.

~~~java
@Controller
public class ProductPageController {
    private final ProductQueryService products;
    private final ProductPresenter presenter;

    public ProductPageController(
            ProductQueryService products,
            ProductPresenter presenter
    ) {
        this.products = products;
        this.presenter = presenter;
    }

    @GetMapping("/products/{id}")
    public String detail(
            @PathVariable long id,
            Model model
    ) {
        ProductDetails result = products.getDetails(id);
        ProductViewModel viewModel = presenter.toViewModel(result);
        model.addAttribute("product", viewModel);
        return "products/detail";
    }
}
~~~

Ở đây:

- `ProductPageController` nhận request và điều phối: Controller.
- `ProductQueryService` lấy kết quả use case: application/model logic.
- `ProductDetails` biểu diễn kết quả truy vấn: application result.
- `ProductPresenter` tạo dữ liệu phù hợp cho màn hình: presentation adapter.
- `ProductViewModel` chứa dữ liệu cần hiển thị: View data.
- `Model` của Spring chỉ mang thuộc tính `product` đến template.
- `products/detail` là tên View được ViewResolver xử lý.

Không nên lưu `Model` vào field của Controller hoặc truyền nó vào service. Controller Spring thường là singleton; field mutable dùng chung giữa request có thể gây race condition và rò dữ liệu giữa người dùng.

### 3.2. `@Controller` và `@RestController` không trả cùng loại View

`@Controller` thường được dùng cho handler trả tên template hoặc `ModelAndView`. Khi method dùng `@ResponseBody`, kết quả được ghi trực tiếp vào response qua `HttpMessageConverter`.

`@RestController` là cách kết hợp `@Controller` và `@ResponseBody`. Vì vậy, một method REST trả DTO không đi qua ViewResolver để render Thymeleaf. Bộ chuyển đổi HTTP có thể serialize DTO thành JSON.

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductApiController {
    private final ProductQueryService products;

    public ProductApiController(ProductQueryService products) {
        this.products = products;
    }

    @GetMapping("/{id}")
    public ProductResponse detail(@PathVariable long id) {
        ProductDetails result = products.getDetails(id);
        return new ProductResponse(
                result.id(),
                result.name(),
                result.price(),
                result.currency()
        );
    }
}
~~~

REST response DTO là hợp đồng API. Nó không phải entity JPA và cũng không cần giống ViewModel của trang HTML.

### 3.3. Đọc `@ModelAttribute` đúng ngữ cảnh

`@ModelAttribute` có thể xuất hiện ở tham số handler để bind form/request parameter vào object, hoặc ở method để chuẩn bị thuộc tính dùng trong model. Vì cùng annotation có nhiều cách dùng, hãy đọc vị trí và chữ ký method thay vì suy ra chỉ từ tên annotation.

~~~java
public record CreateProductForm(
        @NotBlank String name,
        @NotNull @Positive BigDecimal price
) {
}

@Controller
public class ProductFormController {
    private final CreateProductUseCase createProduct;

    public ProductFormController(CreateProductUseCase createProduct) {
        this.createProduct = createProduct;
    }

    @PostMapping("/products")
    public String create(
            @Valid @ModelAttribute("form") CreateProductForm form,
            BindingResult errors,
            RedirectAttributes redirect
    ) {
        if (errors.hasErrors()) {
            return "products/new";
        }

        long id = createProduct.execute(
                new CreateProductCommand(form.name(), form.price())
        );
        redirect.addFlashAttribute("notice", "Đã tạo sản phẩm");
        return "redirect:/products/" + id;
    }
}
~~~

Form object thuộc biên web. Nó mô tả dữ liệu người dùng gửi lên và có thể dùng Bean Validation cho lỗi cấu trúc. Use case vẫn cần kiểm tra các quy tắc nghiệp vụ có thể bị vi phạm từ adapter khác hoặc từ dữ liệu đã thay đổi.

## 4. Phân biệt các loại Model trong một nền tảng

Khi đọc tài liệu framework, hãy xác định rõ “Model” đang nói đến loại nào:

| Loại | Ví dụ | Vai trò |
|---|---|---|
| Domain model | `Order`, `Money`, `OrderStatus` | Quy tắc và trạng thái nghiệp vụ |
| Persistence model | `OrderEntity` được JPA ánh xạ | Lưu trữ dữ liệu |
| Request model | `CreateOrderForm`, `CreateOrderRequest` | Nhận dữ liệu từ client |
| Application model | `PlaceOrderCommand`, `PlaceOrderResult` | Hợp đồng của use case |
| ViewModel | `OrderDetailViewModel` | Dữ liệu cho màn hình |
| Framework View model container | Spring `Model` | Truyền thuộc tính sang template |

Một nền tảng có thể dùng từ Model để chỉ một hoặc nhiều loại trong bảng. Không được mặc định class tên `Product` là domain model chỉ vì nó nằm trong folder `models`.

### 4.1. Dấu hiệu nhận biết domain model

Một domain model thường:

- Có tên theo khái niệm nghiệp vụ như Order, Invoice, Subscription hoặc Money.
- Bảo vệ bất biến và quy tắc trạng thái.
- Có hành vi có ý nghĩa nghiệp vụ, không chỉ getter/setter.
- Không phụ thuộc HTTP request, template hoặc cách serialize.
- Có thể được kiểm thử bằng unit test mà không cần khởi động web server.

### 4.2. Dấu hiệu nhận biết persistence model

Một persistence entity thường:

- Có annotation ORM hoặc mapping metadata.
- Có ID, quan hệ và cấu hình fetch.
- Chịu ảnh hưởng của schema và cách lưu trữ.
- Có thể chứa field kỹ thuật phục vụ database.

Entity JPA có thể trùng với domain entity trong ứng dụng đơn giản. Tuy nhiên, không nên trả nó trực tiếp ra JSON chỉ vì framework có thể serialize object đó.

### 4.3. Dấu hiệu nhận biết ViewModel

ViewModel thường:

- Chỉ chứa trường mà một màn hình cần.
- Có thể có nhãn đã bản địa hóa, cờ hiển thị hoặc dữ liệu nhóm theo bố cục.
- Có thể thay đổi khi thiết kế màn hình thay đổi.
- Không tự quyết định quy tắc nghiệp vụ như có được hủy đơn hay không.

Nếu một cờ như `canCancel` được đưa vào ViewModel, giá trị đó nên đến từ policy hoặc use case có thẩm quyền. Việc ẩn nút trên View không thay thế kiểm tra quyền ở endpoint hủy đơn.

## 5. Cách đọc View và cơ chế hiển thị

View không nhất thiết là một class có tên `View`. Hãy tìm nơi dữ liệu được chuyển thành biểu diễn mà người dùng hoặc client nhận được.

Trong server-side MVC, View có thể là:

- Template Thymeleaf, JSP hoặc FreeMarker.
- Razor view trong ASP.NET Core.
- Template trong Rails hoặc Django.
- Component hoặc template server-rendered.

Trong API, output representation thường được tạo bởi serializer hoặc HTTP message converter. Có thể xem serializer là phần trình bày representation cho client, nhưng nó không nhất thiết là View template theo nghĩa HTML cổ điển.

Hãy kiểm tra:

- View nhận dữ liệu từ đâu?
- Có gọi repository hoặc service trực tiếp không?
- Có tính lại quy tắc nghiệp vụ không?
- Dữ liệu nhạy cảm có bị đưa vào HTML hoặc JSON không?
- Escaping và output encoding có được thực hiện đúng không?
- Locale, timezone và định dạng tiền tệ được áp dụng ở đâu?

Một View tốt chủ yếu trình bày dữ liệu đã chuẩn bị. Nếu template tự truy vấn dữ liệu hoặc thực hiện nhiều phép tính nghiệp vụ, ranh giới MVC đã bị làm mờ.

### 5.1. HTML View và JSON representation

Hai đầu ra có thể dùng cùng kết quả use case nhưng cần cách trình bày khác nhau:

| Dữ liệu đầu ra | HTML View | JSON API |
|---|---|---|
| Trạng thái | Nhãn đã dịch theo locale | Mã trạng thái ổn định |
| Tiền | Chuỗi định dạng cho người dùng | Số tiền và mã tiền tệ |
| Ngày giờ | Có thể hiển thị theo múi giờ người dùng | Timestamp/ISO representation theo hợp đồng |
| Quyền thao tác | Có thể dùng để ẩn/hiện nút | Có thể trả capability nếu hợp đồng cần |
| Bố cục | Nhóm trường theo màn hình | Cấu trúc dữ liệu theo API contract |

Không đưa các thuộc tính chỉ phục vụ bố cục như `activeTab` hoặc `isExpanded` vào API công khai nếu client không cần chúng.

## 6. So sánh cách đặt tên giữa các nền tảng

Các framework có thể dùng cùng từ nhưng gán cho nó trách nhiệm khác nhau. Bảng sau giúp đọc nhanh một số quy ước phổ biến:

| Nền tảng | Thành phần nhận request | Thành phần dữ liệu/nghiệp vụ | Thành phần trình bày |
|---|---|---|---|
| Spring MVC | `@Controller`, handler method | Domain/service/repository; `Model` của Spring chỉ mang dữ liệu cho View | Thymeleaf, JSP, hoặc JSON converter |
| ASP.NET Core MVC | Controller và action, routing | Domain/service; model binding tạo input model; ViewModel tùy ứng dụng | Razor View, formatter hoặc JSON output |
| Django | URLconf gọi function/class “view” | `models.Model` thường là ORM model; service/domain logic có thể tách riêng | Django template |
| Ruby on Rails | Controller action | Active Record Model thường kết hợp domain và persistence | ERB/Haml template hoặc JSON serializer |
| Jakarta Faces | Managed/backing bean và lifecycle component | CDI bean, service và domain object | Facelets/component tree |

Đây là bản đồ trách nhiệm ở mức khái quát. Một dự án có thể tổ chức khác theo convention, phiên bản framework hoặc kiến trúc riêng.

### 6.1. ASP.NET Core MVC

Trong ASP.NET Core MVC:

- Routing chọn controller/action.
- Model binding tạo tham số hoặc object từ route, query, form và body.
- Model validation ghi lỗi vào `ModelState`.
- Controller action trả `IActionResult`, `ViewResult`, `RedirectToAction` hoặc kết quả JSON.
- Razor View render HTML từ ViewModel.

Từ “Model” có thể chỉ request model hoặc ViewModel. Nó không tự động có nghĩa domain model. Khi đọc code, hãy tìm nơi controller action gọi service và nơi service thực thi nghiệp vụ.

### 6.2. Django

Django có cách đặt tên khác với MVC cổ điển:

- URLconf ánh xạ URL tới một view function hoặc class-based view.
- View nhận request, điều phối xử lý và trả response; về trách nhiệm, nó thường gần với Controller.
- `models.Model` thường là lớp ORM biểu diễn dữ liệu lưu trữ.
- Template chịu trách nhiệm render HTML.

Do đó, khi đọc Django, không nên kết luận rằng `views.py` là View trong MVC chỉ vì tên file. Nó thường chứa request handler, tức phần Controller-like. Template mới là phần trình bày.

### 6.3. Ruby on Rails

Rails theo convention MVC rõ ràng:

- Router ánh xạ request đến controller action.
- Model thường là Active Record class, vừa biểu diễn dữ liệu vừa gắn với persistence.
- Controller điều phối request và chọn response.
- View template render HTML.

Một ứng dụng Rails có nghiệp vụ phức tạp vẫn có thể cần service object, form object hoặc domain object để tránh dồn toàn bộ logic vào Active Record model hoặc controller.

### 6.4. Jakarta Faces

Jakarta Faces là framework UI component-based. Người đọc thường gặp Facelets view, managed/backing bean, CDI bean và service. Lifecycle của component xử lý submit, conversion và validation theo cách khác Spring MVC request handler truyền thống.

Không nên ép mọi thành phần của Jakarta Faces vào một sơ đồ class MVC đơn giản. Hãy tìm component view, bean tiếp nhận hành động, service/domain xử lý nghiệp vụ và cơ chế render response; sau đó mới đối chiếu trách nhiệm.

## 7. Ví dụ đọc cùng một chức năng trên hai nền tảng

Giả sử chức năng là xem chi tiết sản phẩm. Hợp đồng mong muốn:

- Nhận product ID.
- Chỉ trả sản phẩm tồn tại và người dùng được phép xem.
- Lấy dữ liệu cần cho trang hoặc API.
- Trả HTML hoặc JSON theo adapter.

Trong Spring MVC, ta có thể tìm:

1. `@GetMapping("/products/{id}")`: route và Controller.
2. `@PathVariable`: binding ID.
3. `ProductQueryService`: application logic.
4. `ProductRepository`: truy cập dữ liệu.
5. `ProductViewModelMapper`: ánh xạ cho màn hình.
6. `return "products/detail"`: chọn HTML View.

Trong Django, cùng chức năng có thể xuất hiện dưới dạng:

1. `path("products/<int:pk>/", product_detail)`: route.
2. `product_detail(request, pk)`: request handler, có trách nhiệm Controller-like.
3. Service hoặc query function: xử lý use case.
4. Django ORM model/manager: persistence access.
5. Context dictionary: dữ liệu đưa vào template.
6. `render(request, "products/detail.html", context)`: tạo HTML response.

Tên gọi khác nhau, nhưng câu hỏi về trách nhiệm vẫn giống nhau. Nếu view function Django chứa cả truy vấn, kiểm tra quyền, tính giá và định dạng HTML, đó là dấu hiệu nhiều trách nhiệm đang bị gộp; có thể tách use case/service và presenter khi độ phức tạp tăng.

## 8. Phân biệt routing, Controller và middleware/filter

Các nền tảng thường cung cấp middleware, filter, interceptor hoặc request pipeline. Chúng có thể chạy trước hoặc sau Controller, nhưng không mặc định là Controller.

| Thành phần | Vai trò |
|---|---|
| Router / HandlerMapping | Chọn handler theo URL và HTTP method |
| Middleware / Filter | Xử lý xuyên suốt request như correlation ID, CORS hoặc logging |
| Authentication filter | Xác thực danh tính trước khi handler chạy |
| Authorization interceptor/policy | Kiểm tra quyền theo endpoint hoặc resource |
| Controller/action/view function | Điều phối request cụ thể và gọi use case |
| Exception handler | Chuyển lỗi thành response |
| View resolver/serializer | Tạo representation đầu ra |

Không nên đưa quy tắc nghiệp vụ riêng của một use case vào middleware chỉ vì middleware có thể chạy trước Controller. Middleware phù hợp với chính sách xuyên suốt hoặc xử lý giao thức.

## 9. Đọc validation và bảo mật theo trách nhiệm

Một nền tảng có thể tự động bind và validate dữ liệu, nhưng điều đó không có nghĩa mọi quy tắc nghiệp vụ đã được bảo vệ.

Hãy phân biệt:

1. **Binding/conversion:** `"12"` được chuyển thành số 12; ngày có đúng định dạng không?
2. **Input validation:** tên có rỗng không; số lượng có lớn hơn 0 không?
3. **Business validation:** sản phẩm còn được bán không; đơn có thể chuyển trạng thái này không?
4. **Authorization:** người dùng có quyền xem hoặc thay đổi tài nguyên này không?
5. **Persistence constraint:** database có chặn dữ liệu trùng hoặc quan hệ không hợp lệ không?

Ví dụ Spring:

~~~java
public record UpdateProfileRequest(
        @NotBlank @Size(max = 80) String displayName
) {
}

@RestController
@RequestMapping("/api/profile")
public class ProfileController {
    private final UpdateProfileUseCase updateProfile;

    public ProfileController(UpdateProfileUseCase updateProfile) {
        this.updateProfile = updateProfile;
    }

    @PutMapping
    public ProfileResponse update(
            @Valid @RequestBody UpdateProfileRequest request,
            @AuthenticationPrincipal CurrentUser user
    ) {
        UpdateProfileResult result = updateProfile.execute(
                new UpdateProfileCommand(user.id(), request.displayName())
        );
        return ProfileResponse.from(result);
    }
}
~~~

Controller lấy user ID từ principal đã xác thực, không tin một `userId` tùy ý trong body. Use case vẫn cần kiểm tra quy tắc cập nhật và quyền ở mức tài nguyên nếu có nhiều phạm vi truy cập.

Khi đọc framework, hãy tìm cơ chế CSRF, CORS, authentication, authorization, output escaping và error handling. Không suy ra ứng dụng an toàn chỉ vì framework có sẵn annotation hoặc middleware cho các cơ chế này.

## 10. Đọc transaction và persistence

Transaction thường liên quan đến use case hoặc application service, không phải View. Khi theo dõi một request ghi dữ liệu, hãy tìm:

- Transaction bắt đầu ở đâu?
- Có bao nhiêu repository hoặc dịch vụ được gọi?
- Các thao tác nào cần nguyên tử?
- Lỗi nào làm rollback?
- Có thao tác bên ngoài transaction như gửi email hoặc gọi thanh toán không?
- Có dùng outbox, idempotency hoặc cơ chế bù trừ khi cần không?

Trong Spring, `@Transactional` thường được đặt ở service/use case method. Tuy nhiên, annotation chỉ có hiệu lực theo cơ chế proxy và transaction manager được cấu hình; self-invocation có thể không đi qua proxy trong cấu hình proxy thông thường. Hãy đọc cấu hình và cách gọi thực tế thay vì chỉ tìm annotation.

Repository là cơ chế truy cập dữ liệu. Domain model không nhất thiết phải là entity JPA. Khi một class vừa có annotation ORM vừa chứa nghiệp vụ, cần xác định liệu coupling đó có phù hợp quy mô ứng dụng hay đã làm domain phụ thuộc quá nhiều vào persistence.

## 11. Đọc error handling và response contract

Controller thường chuyển kết quả hoặc lỗi thành HTTP response. Hãy tìm:

- Lỗi validation trả lại form với dữ liệu người dùng đã nhập hay trả JSON lỗi?
- Lỗi không tìm thấy dùng 404 hay một response chung?
- Lỗi quyền truy cập dùng 403 hay 404 theo chính sách bảo mật?
- Lỗi xung đột trạng thái dùng 409 hay mã khác?
- Exception không dự kiến có để lộ stack trace hoặc SQL không?
- Redirect có tuân theo Post/Redirect/Get không?

Trong Spring MVC, `@ExceptionHandler` và `@ControllerAdvice` có thể chuyển exception thành View hoặc response body. Trong ASP.NET Core, exception middleware hoặc exception filter có thể đảm nhiệm vai trò tương tự. Trong Django, exception handling và middleware có thể tạo response lỗi. Hãy xác định trách nhiệm và phạm vi áp dụng, không chỉ ghi nhớ tên API.

Response contract là thứ client quan sát. Đổi class nội bộ hoặc tên service không nhất thiết phải đổi contract; đổi field JSON, status code hoặc redirect URL có thể là thay đổi tương thích cần được quản lý.

## 12. Đọc testing theo từng ranh giới

Một nền tảng thường cung cấp nhiều loại công cụ kiểm thử. Chọn công cụ dựa trên trách nhiệm cần xác nhận:

| Ranh giới | Điều cần kiểm tra | Ví dụ công cụ trong Java/Spring |
|---|---|---|
| Domain Model | Bất biến, phép tính, chuyển trạng thái | JUnit, AssertJ |
| Application service | Use case và tương tác với port | JUnit, Mockito |
| Controller/HTTP | Binding, validation, status, response | MockMvc, `@WebMvcTest` |
| View | Nội dung và khả năng render | MVC test, browser test |
| Repository | Query, mapping, transaction, constraint | `@DataJpaTest`, Testcontainers |
| Toàn luồng | Hành trình người dùng | `@SpringBootTest`, Playwright/Selenium |

Không nên chỉ kiểm tra Controller đã gọi service. Hãy kiểm tra HTTP response và hành vi nghiệp vụ ở ranh giới tương ứng. Test domain không cần Spring context; test repository nên dùng database phù hợp để xác nhận hành vi ORM thật.

Một số dấu hiệu test bám sát chi tiết triển khai:

- Dùng reflection gọi private method.
- Verify thứ tự gọi helper nội bộ không thuộc hợp đồng.
- Mock mọi lớp trong cùng một luồng.
- Dùng selector CSS phụ thuộc cấu trúc DOM sâu.
- So sánh toàn bộ HTML hoặc object lớn khi chỉ một vài trường quan trọng.

Test bền vững tập trung vào những điều người dùng, client hoặc nghiệp vụ có quyền kỳ vọng.

## 13. Bài tập thực hành: lập bản đồ một nền tảng

Chọn một chức năng có sẵn trong dự án mẫu, chẳng hạn xem chi tiết sản phẩm hoặc tạo tài khoản. Điền bảng sau khi đọc route, handler, service, model và template:

| Câu hỏi | Thành phần tìm được | Vai trò |
|---|---|---|
| Request vào từ đâu? |  | Routing / Controller |
| Dữ liệu request được bind ở đâu? |  | Input adapter |
| Validation cấu trúc nằm ở đâu? |  | Input validation |
| Quy tắc nghiệp vụ được gọi ở đâu? |  | Model / Use case |
| Dữ liệu được đọc/ghi ở đâu? |  | Repository / Gateway |
| Kết quả được chuyển đổi ở đâu? |  | Presenter / Mapper |
| HTML hoặc JSON được tạo ở đâu? |  | View / Serializer |
| Lỗi được chuyển thành response ở đâu? |  | Error adapter |
| Quyền được kiểm tra ở đâu? |  | Authentication / Authorization |
| Hành vi được kiểm thử ở đâu? |  | Test boundary |

Sau khi điền, vẽ luồng từ request đến response. Đánh dấu nơi có nhiều trách nhiệm bị trộn, ví dụ Controller truy vấn database và tự tính giá, template gọi service, hoặc entity ORM được serialize trực tiếp.

### 13.1. Câu hỏi tự kiểm tra

1. Trong Spring MVC, `Model` truyền cho template có phải domain model không? Vì sao?
2. Vì sao file `views.py` trong Django thường đảm nhiệm vai trò Controller-like?
3. `@RestController` khác `@Controller` trả tên template ở điểm nào?
4. Request DTO và domain entity có nên dùng chung trong mọi trường hợp không?
5. Middleware/filter thường phù hợp với loại trách nhiệm nào?
6. Nếu đổi template engine nhưng giữ nguyên use case, những thành phần nào nên ít bị ảnh hưởng?
7. Một test chỉ verify Controller gọi mapper có đủ chứng minh response đúng không?

## 14. Các lỗi thường gặp khi ánh xạ nền tảng

| Cách đọc sai | Vì sao sai | Cách đọc đúng |
|---|---|---|
| Thấy class tên `Model` rồi xem đó là domain model | Framework có thể dùng tên này cho container dữ liệu View | Đọc field, hành vi và người tiêu thụ của class |
| Thấy file `views.py` rồi xem nó là HTML View | Django view thường nhận request và trả response | Tìm template để xác định phần trình bày |
| Xem JPA entity là DTO API | Entity có quan hệ ORM và field nội bộ | Tìm response DTO hoặc serializer contract |
| Xem mọi validation là quy tắc nghiệp vụ | Binding/Bean Validation chỉ kiểm tra một phần đầu vào | Phân chia input validation và business invariants |
| Xem middleware là Controller | Middleware thường chạy xuyên suốt nhiều endpoint | Tìm handler cụ thể được route chọn |
| Xem JSON serializer là use case | Serializer chỉ chuyển object thành representation | Theo dõi service/use case tạo dữ liệu |
| Xem ẩn nút là bảo vệ quyền | Client vẫn có thể gọi endpoint trực tiếp | Kiểm tra authorization ở server |
| Tìm annotation rồi kết luận tính năng hoạt động | Proxy, lifecycle hoặc cấu hình có thể ảnh hưởng | Theo dõi luồng gọi và kiểm thử hành vi |
| Ép mọi framework vào cùng cấu trúc folder | Convention của framework khác nhau | Ánh xạ theo trách nhiệm thay vì tên folder |

## 15. Checklist đọc một nền tảng MVC

Khi bắt đầu với một framework hoặc dự án mới, hãy xác nhận:

- Đã tìm được router và điểm vào của request chưa?
- Đã xác định Controller hoặc request handler thực tế chưa?
- Đã hiểu cách binding route, query, header và body chưa?
- Đã phân biệt request model, application model, domain model và persistence model chưa?
- Đã tìm được nơi thực thi use case và quy tắc nghiệp vụ chưa?
- Đã xác định repository/gateway và transaction boundary chưa?
- Đã tìm được View template hoặc JSON serializer chưa?
- Đã hiểu response contract, redirect và error mapping chưa?
- Đã xác định authentication và authorization được áp dụng ở đâu chưa?
- Đã tìm được test cho domain, Controller, persistence và luồng người dùng chưa?
- Đã nhận diện nơi các trách nhiệm MVC đang bị trộn chưa?

## 16. Kết luận

Đọc một nền tảng theo MVC hiệu quả nhất khi bắt đầu từ request và lần theo dữ liệu đến response. Hãy tìm nơi tiếp nhận tương tác để nhận diện Controller, nơi thực thi trạng thái và quy tắc để nhận diện Model, và nơi tạo HTML hoặc representation để nhận diện View. Sau đó kiểm tra binding, validation, bảo mật, transaction, lỗi và test như những cơ chế hỗ trợ các ranh giới đó.

Tên gọi của framework chỉ là quy ước. Spring `Model`, Django `view`, Rails Active Record và ASP.NET Core ViewModel có thể mang ý nghĩa khác nhau. Khi hiểu trách nhiệm thực tế, người học có thể đọc nhiều nền tảng mà không nhầm tên lớp với kiến trúc, đồng thời nhận ra nơi cần tách dữ liệu request, nghiệp vụ, persistence và trình bày trong một ứng dụng MVC có thể phát triển lâu dài.
