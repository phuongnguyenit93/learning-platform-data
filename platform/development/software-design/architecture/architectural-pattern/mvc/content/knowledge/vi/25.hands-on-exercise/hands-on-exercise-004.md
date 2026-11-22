# Thêm biểu mẫu và phân tách các loại kiểm tra

Bài thực hành này xây dựng biểu mẫu thêm sản phẩm trong ứng dụng web MVC dùng Spring MVC và Thymeleaf. Người học theo dõi dữ liệu từ HTML form vào Controller, qua các lớp kiểm tra, chuyển thành command, đi qua application service và domain model, rồi tạo phản hồi phù hợp cho người dùng.

Một lỗi thường gặp là gom mọi kiểm tra vào Controller hoặc chỉ dùng annotation trên form rồi cho rằng dữ liệu đã an toàn. Trong bài này, mỗi loại kiểm tra có mục đích và vị trí riêng:

- Binding kiểm tra dữ liệu HTTP có chuyển được thành kiểu Java hay không.
- Form validation kiểm tra đầu vào có đủ và đúng định dạng để người dùng gửi hay không.
- Domain invariant bảo vệ những điều kiện mà một Product hợp lệ luôn phải thỏa mãn.
- Business validation kiểm tra ngữ cảnh nghiệp vụ, ví dụ SKU đã được sử dụng chưa.
- Authorization xác định người dùng có quyền thêm sản phẩm không.
- Database constraint bảo vệ tính duy nhất kể cả khi hai request đến đồng thời.

Các kiểm tra bổ sung cho nhau nhưng không thay thế nhau. Controller điều phối phản hồi; application service và domain bảo vệ hành vi; security layer kiểm soát quyền; database bảo vệ tính nhất quán cuối cùng.

## 1. Bối cảnh và mục tiêu

Giả sử ứng dụng có trang quản trị danh mục sản phẩm. Người dùng có vai trò quản trị danh mục mở trang thêm sản phẩm, nhập thông tin rồi gửi biểu mẫu.

Biểu mẫu cần các trường:

| Trường | Ý nghĩa | Quy tắc đầu vào |
|---|---|---|
| name | Tên sản phẩm | Bắt buộc, tối đa 120 ký tự |
| sku | Mã định danh hàng hóa | Bắt buộc, 4–20 ký tự chữ/số/dấu gạch ngang |
| price | Giá bán | Bắt buộc, lớn hơn 0, tối đa 2 chữ số thập phân |
| stock | Số lượng tồn ban đầu | Bắt buộc, số nguyên từ 0 trở lên |

Ngoài các quy tắc đầu vào, hệ thống có quy tắc nghiệp vụ: SKU sau khi chuẩn hóa phải là duy nhất. Chỉ người có quyền quản trị danh mục mới được tạo sản phẩm.

### 1.1. Kết quả cần đạt

1. Tạo GET endpoint hiển thị form và POST endpoint tiếp nhận form.
2. Dùng Form DTO riêng thay vì bind trực tiếp vào Entity.
3. Dùng Bean Validation cho kiểm tra đầu vào.
4. Phân biệt lỗi binding, lỗi form, domain invariant và business validation.
5. Chuyển Form DTO thành application command.
6. Trả lại form với lỗi gắn đúng trường.
7. Dùng Post/Redirect/Get khi tạo thành công.
8. Bảo vệ endpoint bằng authorization và CSRF.
9. Viết test riêng cho Controller, application service, domain và persistence.

### 1.2. Luồng xử lý mong đợi

~~~mermaid
flowchart TD
    A[GET /admin/products/new] --> B[Controller tạo Form DTO]
    B --> C[Thymeleaf render biểu mẫu]
    C --> D[Người dùng gửi POST]
    D --> E[HTTP binding và type conversion]
    E --> F[Form validation]
    F -->|Có lỗi| G[Trả lại form + lỗi theo trường]
    F -->|Hợp lệ| H[Controller tạo command]
    H --> I[Application service]
    I --> J[Kiểm tra SKU trùng]
    J -->|Trùng| G
    J -->|Không trùng| K[Domain tạo Product]
    K --> L[Repository adapter + unique constraint]
    L --> M[Redirect tới danh sách]
~~~

Authorization và CSRF được kiểm tra ở security filter trước khi Controller xử lý POST. Database unique constraint vẫn cần thiết vì hai request có thể cùng vượt qua bước kiểm tra SKU trước khi một request ghi dữ liệu.

## 2. Phân loại các loại kiểm tra

Trước khi viết code, hãy xác định mỗi điều kiện thuộc ranh giới nào.

| Loại kiểm tra | Ví dụ | Nơi thực hiện | Phản hồi thường thấy |
|---|---|---|---|
| Binding/type conversion | Chuỗi giá không chuyển được thành BigDecimal | Spring MVC binder | Lỗi trường trong form |
| Form/input validation | Tên rỗng, SKU sai định dạng, giá không dương | Form DTO + Bean Validation | Trả lại form |
| Domain invariant | Product không thể có giá không dương hoặc tồn kho âm | Domain model/value object | Từ chối tạo đối tượng |
| Business validation | SKU đã tồn tại trong danh mục | Application service/domain policy | Lỗi nghiệp vụ gắn với SKU |
| Authorization | Người dùng không có quyền quản trị danh mục | Spring Security hoặc policy | HTTP 403/đăng nhập |
| CSRF protection | POST form thiếu token hợp lệ | Spring Security filter | HTTP 403 |
| Persistence constraint | Hai request đồng thời tạo cùng SKU | Database unique constraint | Adapter ánh xạ lỗi về lỗi nghiệp vụ |

### 2.1. Binding không phải validation

Nếu người dùng gửi price=abc, Spring không thể chuyển chuỗi đó thành BigDecimal. Đây là lỗi chuyển kiểu, xảy ra trước khi Bean Validation kiểm tra @DecimalMin.

Nếu người dùng gửi price=0, việc chuyển kiểu thành công nhưng giá trị không thỏa @DecimalMin("0.01"). Đây là lỗi validation.

Cả hai có thể xuất hiện trong BindingResult, nhưng nguyên nhân và cách xử lý khác nhau. Không nên viết code để tự parse tất cả trường trong Controller.

### 2.2. Form validation không thay thế domain invariant

Form DTO kiểm tra dữ liệu đến từ một màn hình cụ thể và cung cấp lỗi dễ hiểu cho người dùng. Domain invariant bảo vệ trạng thái hợp lệ bất kể Product được tạo từ web form, REST API, import file hay job nền.

Ví dụ, @DecimalMin("0.01") giúp người dùng thấy lỗi tại trường price. Nhưng Product vẫn phải từ chối giá không dương nếu một caller khác bỏ qua Controller.

### 2.3. Business validation khác với kiểm tra định dạng

SKU có thể đúng định dạng nhưng đã được một sản phẩm khác sử dụng. Pattern chỉ xác nhận hình dạng chuỗi; application cần kiểm tra tính duy nhất theo dữ liệu hiện tại.

Kiểm tra trước khi lưu cải thiện trải nghiệm, còn unique constraint trong database bảo vệ trường hợp cạnh tranh đồng thời. Hai lớp này có mục đích khác nhau.

### 2.4. Authorization không phải lỗi form

Người không có quyền không nên được phép tạo sản phẩm chỉ vì form hợp lệ. Ẩn nút hoặc không hiển thị link quản trị không phải biện pháp bảo mật. Server phải kiểm tra quyền trên request.

## 3. Thiết kế dữ liệu đầu vào

Không bind trực tiếp vào Product Entity. Tạo một Form DTO chỉ chứa các trường người dùng được phép nhập.

~~~java
public class CreateProductForm {

    @NotBlank(message = "Tên sản phẩm không được để trống")
    @Size(max = 120, message = "Tên sản phẩm tối đa 120 ký tự")
    private String name;

    @NotBlank(message = "SKU không được để trống")
    @Pattern(
        regexp = "^[A-Za-z0-9-]{4,20}$",
        message = "SKU phải có 4–20 ký tự chữ, số hoặc dấu gạch ngang"
    )
    private String sku;

    @NotNull(message = "Giá bán là bắt buộc")
    @DecimalMin(
        value = "0.01",
        message = "Giá bán phải lớn hơn 0"
    )
    @Digits(
        integer = 10,
        fraction = 2,
        message = "Giá bán tối đa 10 chữ số nguyên và 2 chữ số thập phân"
    )
    private BigDecimal price;

    @NotNull(message = "Số lượng tồn là bắt buộc")
    @Min(value = 0, message = "Số lượng tồn không được âm")
    private Integer stock;

    // Thêm getter và setter cho các trường.
}
~~~

Dùng Integer thay vì int cho stock để phân biệt trường bị bỏ trống (null) với giá trị 0. Dùng BigDecimal cho tiền để tránh sai số dấu phẩy động.

### 3.1. Vì sao không dùng Entity làm Form DTO?

Product Entity có thể chứa ID, trạng thái kiểm duyệt, ngày tạo, người tạo hoặc thông tin nội bộ. Những trường này do server quản lý, không được phép nhận tùy ý từ client.

Form DTO giới hạn rõ những gì người dùng có thể gửi. Khi form thay đổi, cấu trúc persistence không cần thay đổi theo.

### 3.2. Xác định quy tắc chuẩn hóa

Trong bài tập, SKU không phân biệt chữ hoa/chữ thường. Ví dụ ab-1200 và AB-1200 được xem là cùng một SKU.

Chọn một quy tắc chuẩn hóa thống nhất:

- Loại bỏ khoảng trắng ở đầu và cuối.
- Chuyển chữ cái thành uppercase bằng Locale.ROOT.
- Thực hiện kiểm tra duy nhất trên giá trị đã chuẩn hóa.
- Lưu giá trị chuẩn hóa để truy vấn nhất quán.

Không kiểm tra SKU trùng trên chuỗi chưa chuẩn hóa rồi lưu chuỗi đã chuẩn hóa, vì cách đó có thể tạo bản ghi trùng logic.

## 4. Tạo View cho biểu mẫu

Tạo template tại templates/admin/products/new.html:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Thêm sản phẩm</title>
</head>
<body>
<main>
    <h1>Thêm sản phẩm</h1>

    <form th:action="@{/admin/products}"
          th:object="${form}"
          method="post">

        <div>
            <label for="name">Tên sản phẩm</label>
            <input id="name" type="text" th:field="*{name}">
            <p th:if="${#fields.hasErrors('name')}"
               th:errors="*{name}"></p>
        </div>

        <div>
            <label for="sku">SKU</label>
            <input id="sku" type="text" th:field="*{sku}">
            <p th:if="${#fields.hasErrors('sku')}"
               th:errors="*{sku}"></p>
        </div>

        <div>
            <label for="price">Giá bán</label>
            <input id="price" type="number" step="0.01"
                   th:field="*{price}">
            <p th:if="${#fields.hasErrors('price')}"
               th:errors="*{price}"></p>
        </div>

        <div>
            <label for="stock">Số lượng tồn</label>
            <input id="stock" type="number" step="1"
                   th:field="*{stock}">
            <p th:if="${#fields.hasErrors('stock')}"
               th:errors="*{stock}"></p>
        </div>

        <button type="submit">Lưu sản phẩm</button>
    </form>
</main>
</body>
</html>
~~~

th:object xác định Form DTO làm đối tượng binding. th:field nối input với thuộc tính. th:errors hiển thị lỗi đúng trường. Dùng th:text/th:errors để render dữ liệu dưới dạng text đã escape; không chèn thông báo người dùng bằng HTML không tin cậy.

Khi Spring Security và Thymeleaf integration được cấu hình đúng, form POST dùng th:action có thể được bổ sung CSRF token tự động. Hãy kiểm tra HTML được render và cấu hình thực tế của dự án; không tắt CSRF chỉ để form hoạt động.

## 5. Controller: hiển thị form và tiếp nhận POST

Controller chỉ xử lý HTTP, binding, gọi application service và chọn View hoặc redirect.

~~~java
@Controller
@RequestMapping("/admin/products")
public class ProductAdminController {

    private final CreateProductUseCase createProduct;

    public ProductAdminController(CreateProductUseCase createProduct) {
        this.createProduct = createProduct;
    }

    @GetMapping("/new")
    public String newForm(Model model) {
        model.addAttribute("form", new CreateProductForm());
        return "admin/products/new";
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("form") CreateProductForm form,
            BindingResult bindingResult,
            RedirectAttributes redirectAttributes) {

        if (bindingResult.hasErrors()) {
            return "admin/products/new";
        }

        try {
            createProduct.handle(new CreateProductCommand(
                form.getName(),
                form.getSku(),
                form.getPrice(),
                form.getStock()
            ));
        } catch (DuplicateSkuException exception) {
            bindingResult.rejectValue(
                "sku",
                "product.sku.duplicate",
                "SKU này đã được sử dụng"
            );
            return "admin/products/new";
        }

        redirectAttributes.addFlashAttribute(
            "successMessage",
            "Sản phẩm đã được tạo"
        );

        return "redirect:/admin/products";
    }
}
~~~

Trong ví dụ, Form DTO có getter/setter theo JavaBean convention. BindingResult phải đứng ngay sau tham số có @Valid để Spring gắn lỗi binding và validation vào đúng đối tượng.

### 5.1. Vì sao trả lại cùng View khi có lỗi?

Khi validation thất bại, Controller trả admin/products/new. Spring giữ Form DTO và BindingResult trong Model để template hiển thị giá trị đã nhập cùng lỗi theo trường.

Không cần tạo lại Form DTO rỗng trong nhánh lỗi, vì như vậy người dùng sẽ mất dữ liệu vừa nhập.

### 5.2. Vì sao redirect khi thành công?

POST/Redirect/GET giúp tránh gửi lại thao tác tạo sản phẩm khi người dùng refresh trang kết quả. Flash attribute được lưu tạm để hiển thị thông báo ở trang đích.

Không nên trả trực tiếp View danh sách từ POST nếu hợp đồng ứng dụng muốn tránh resubmit.

### 5.3. Xử lý lỗi nghiệp vụ có phạm vi

SKU trùng là lỗi có thể gắn với trường sku, nên Controller có thể chuyển nó thành field error. Các lỗi kỹ thuật không nên bị bắt chung rồi hiển thị như lỗi nhập liệu.

Trong dự án lớn, có thể dùng @ControllerAdvice hoặc một kết quả application có kiểu để ánh xạ lỗi nhất quán. Giữ quy tắc ánh xạ ở một nơi phù hợp, tránh mỗi Controller tự diễn giải exception theo cách khác nhau.

## 6. Application service và domain invariant

Application service kiểm tra quy tắc phụ thuộc vào ngữ cảnh hiện tại, như SKU đã tồn tại chưa, rồi yêu cầu domain tạo Product.

~~~java
public record CreateProductCommand(
    String name,
    String sku,
    BigDecimal price,
    int stock
) {}

public interface CreateProductUseCase {
    ProductId handle(CreateProductCommand command);
}

public interface ProductRepository {
    boolean existsBySku(ProductSku sku);
    void save(Product product);
}
~~~

Một implementation có thể như sau:

~~~java
public class CreateProductService implements CreateProductUseCase {

    private final ProductRepository products;

    public CreateProductService(ProductRepository products) {
        this.products = products;
    }

    @Override
    public ProductId handle(CreateProductCommand command) {
        ProductSku sku = ProductSku.of(command.sku());

        if (products.existsBySku(sku)) {
            throw new DuplicateSkuException(sku);
        }

        Product product = Product.create(
            command.name(),
            sku,
            command.price(),
            command.stock()
        );

        products.save(product);
        return product.id();
    }
}
~~~

### 6.1. Chuẩn hóa SKU bằng Value Object

~~~java
public record ProductSku(String value) {

    public ProductSku {
        if (value == null || value.isBlank()) {
            throw new InvalidProductSkuException();
        }

        value = value.trim().toUpperCase(Locale.ROOT);
        if (!value.matches("[A-Z0-9-]{4,20}")) {
            throw new InvalidProductSkuException();
        }
    }

    public static ProductSku of(String value) {
        return new ProductSku(value);
    }
}
~~~

Value Object kiểm tra cú pháp sau chuẩn hóa để mọi nguồn tạo SKU đều dùng cùng quy tắc. Form DTO vẫn giữ @Pattern để cung cấp lỗi thân thiện ngay trên biểu mẫu; hai kiểm tra có mục đích khác nhau: một kiểm tra phản hồi đầu vào, một bảo vệ giá trị domain.

### 6.2. Domain bảo vệ điều kiện luôn đúng

~~~java
public class Product {

    private final ProductId id;
    private final String name;
    private final ProductSku sku;
    private final BigDecimal price;
    private final int stock;

    private Product(
            ProductId id,
            String name,
            ProductSku sku,
            BigDecimal price,
            int stock) {
        this.id = id;
        this.name = name;
        this.sku = sku;
        this.price = price;
        this.stock = stock;
    }

    public static Product create(
            String name,
            ProductSku sku,
            BigDecimal price,
            int stock) {

        if (name == null || name.isBlank()) {
            throw new InvalidProductException("Tên sản phẩm bắt buộc");
        }
        if (price == null || price.signum() <= 0) {
            throw new InvalidProductException("Giá phải lớn hơn 0");
        }
        if (stock < 0) {
            throw new InvalidProductException("Tồn kho không được âm");
        }

        return new Product(
            ProductId.newId(),
            name.trim(),
            sku,
            price,
            stock
        );
    }
}
~~~

Domain invariant là hàng rào cuối ở cấp mô hình nghiệp vụ. Dù một message listener hoặc API khác gọi use case mà không đi qua HTML form, Product vẫn không được tạo với giá không hợp lệ.

## 7. Bảo vệ tính duy nhất khi có request đồng thời

Kiểm tra existsBySku trước khi lưu giúp trả lỗi dễ hiểu, nhưng không bảo đảm tuyệt đối tính duy nhất.

Ví dụ hai request đến gần như cùng lúc:

1. Request A kiểm tra SKU chưa tồn tại.
2. Request B cũng kiểm tra SKU chưa tồn tại.
3. A lưu thành công.
4. B cố lưu cùng SKU.

Cả hai đều vượt qua bước kiểm tra trước khi ghi. Database cần unique constraint trên cột SKU đã chuẩn hóa.

Ví dụ migration SQL:

~~~sql
ALTER TABLE products
ADD CONSTRAINT uk_products_sku UNIQUE (sku);
~~~

Repository adapter hoặc lớp persistence bắt lỗi vi phạm unique constraint và chuyển thành DuplicateSkuException. Controller có thể trả lại form với lỗi SKU như trong ví dụ.

Không nên để DataIntegrityViolationException hoặc thông điệp SQL thô xuất hiện với người dùng. Đồng thời, không bắt mọi lỗi database rồi coi là SKU trùng; chỉ ánh xạ đúng constraint đã biết.

## 8. Authorization và CSRF

Endpoint thêm sản phẩm chỉ dành cho người có quyền quản trị danh mục. Có thể cấu hình quyền ở Spring Security:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/products/**")
            .hasRole("CATALOG_ADMIN")
        .anyRequest()
            .authenticated()
    );

    // Giữ CSRF protection cho form dùng session cookie.
    return http.build();
}
~~~

hasRole("CATALOG_ADMIN") thường kiểm tra authority ROLE_CATALOG_ADMIN. Cấu hình thực tế cần phù hợp với cách ứng dụng cấp role.

Các điểm cần kiểm tra:

- Người chưa đăng nhập được chuyển tới login hoặc nhận 401 theo cấu hình.
- Người đã đăng nhập nhưng không có role nhận 403.
- Người có role hợp lệ được mở form và gửi POST.
- POST thiếu hoặc sai CSRF token bị từ chối.
- Ẩn link quản trị trong View chỉ là trải nghiệm; security layer vẫn phải bảo vệ endpoint.

Không dùng canCreateProduct trong Form DTO làm bằng chứng phân quyền. Quyền phải được xác định từ danh tính đã xác thực ở server.

## 9. Tách kiểm thử theo loại trách nhiệm

Không viết một bài test khổng lồ vừa kiểm tra annotation, domain, database và template. Mỗi test nên xác nhận một ranh giới cụ thể.

### 9.1. Domain unit test

~~~java
@Test
void rejectsNonPositivePrice() {
    assertThatThrownBy(() ->
        Product.create(
            "Bàn phím",
            ProductSku.of("KB-100"),
            new BigDecimal("0.00"),
            5
        )
    ).isInstanceOf(InvalidProductException.class);
}

@Test
void rejectsNegativeStock() {
    assertThatThrownBy(() ->
        Product.create(
            "Bàn phím",
            ProductSku.of("KB-100"),
            new BigDecimal("100.00"),
            -1
        )
    ).isInstanceOf(InvalidProductException.class);
}
~~~

Hai test này không kiểm tra Bean Validation. Chúng xác nhận domain không cho phép tạo trạng thái bất hợp lệ.

### 9.2. Application service unit test

Dùng fake repository để kiểm tra quy tắc SKU duy nhất:

~~~java
@Test
void rejectsDuplicateSkuBeforeSaving() {
    ProductRepository repository = new InMemoryProductRepository();
    repository.addSku(ProductSku.of("KB-100"));

    CreateProductService service = new CreateProductService(repository);

    assertThatThrownBy(() -> service.handle(new CreateProductCommand(
        "Bàn phím",
        "kb-100",
        new BigDecimal("100.00"),
        5
    ))).isInstanceOf(DuplicateSkuException.class);

    assertThat(repository.savedProducts()).isEmpty();
}
~~~

Test này xác nhận application chuẩn hóa SKU, kiểm tra tính duy nhất và không lưu khi trùng. Fake repository cần cung cấp existsBySku, save và danh sách sản phẩm đã lưu theo hợp đồng của dự án.

### 9.3. Controller/MockMvc test cho form validation

~~~java
@Test
void returnsFormWhenInputValidationFails() throws Exception {
    mockMvc.perform(post("/admin/products")
            .with(user("catalog-admin").roles("CATALOG_ADMIN"))
            .with(csrf())
            .param("name", "")
            .param("sku", "!")
            .param("price", "0")
            .param("stock", "-1"))
        .andExpect(status().isOk())
        .andExpect(view().name("admin/products/new"))
        .andExpect(model().attributeHasFieldErrors(
            "form", "name", "sku", "price", "stock"
        ));

    verify(createProduct, never()).handle(any());
}
~~~

Test này xác nhận lỗi đầu vào được phát hiện trước khi gọi use case. Nó không thay thế domain test hoặc application test.

### 9.4. Controller test cho binding error

Gửi giá không thể chuyển thành BigDecimal:

~~~java
@Test
void returnsFormWhenPriceCannotBeConverted() throws Exception {
    mockMvc.perform(post("/admin/products")
            .with(user("catalog-admin").roles("CATALOG_ADMIN"))
            .with(csrf())
            .param("name", "Bàn phím")
            .param("sku", "KB-100")
            .param("price", "not-a-number")
            .param("stock", "5"))
        .andExpect(status().isOk())
        .andExpect(view().name("admin/products/new"))
        .andExpect(model().attributeHasFieldErrors("form", "price"));

    verify(createProduct, never()).handle(any());
}
~~~

Đây là binding/type conversion error. Giá trị không chuyển thành BigDecimal nên Bean Validation không nhận được một giá trị số hợp lệ để kiểm tra.

### 9.5. Controller test cho business error

Giả lập use case ném DuplicateSkuException, rồi xác nhận lỗi được gắn vào trường sku:

~~~java
@Test
void returnsFormWhenSkuAlreadyExists() throws Exception {
    when(createProduct.handle(any()))
        .thenThrow(new DuplicateSkuException(ProductSku.of("KB-100")));

    mockMvc.perform(post("/admin/products")
            .with(user("catalog-admin").roles("CATALOG_ADMIN"))
            .with(csrf())
            .param("name", "Bàn phím")
            .param("sku", "KB-100")
            .param("price", "100.00")
            .param("stock", "5"))
        .andExpect(status().isOk())
        .andExpect(view().name("admin/products/new"))
        .andExpect(model().attributeHasFieldErrors("form", "sku"));
}
~~~

Test này tập trung vào cách Controller chuyển lỗi nghiệp vụ thành phản hồi form. Quy tắc SKU trùng đã được kiểm tra riêng trong application service test.

### 9.6. Security test

Tách quyền và CSRF thành test riêng:

~~~java
@Test
void rejectsUserWithoutCatalogRole() throws Exception {
    mockMvc.perform(post("/admin/products")
            .with(user("reader").roles("READER"))
            .with(csrf())
            .param("name", "Bàn phím"))
        .andExpect(status().isForbidden());

    verifyNoInteractions(createProduct);
}

@Test
void rejectsPostWithoutCsrfToken() throws Exception {
    mockMvc.perform(post("/admin/products")
            .with(user("catalog-admin").roles("CATALOG_ADMIN"))
            .param("name", "Bàn phím"))
        .andExpect(status().isForbidden());

    verifyNoInteractions(createProduct);
}
~~~

Các test này giả định MockMvc được cấu hình với Spring Security filter chain thật. Nếu dùng standaloneSetup, cần cấu hình filter phù hợp hoặc dùng @SpringBootTest/@WebMvcTest để kiểm tra security integration.

### 9.7. Persistence integration test

Kiểm tra unique constraint bằng database test thực tế hoặc Testcontainers:

- Lưu một sản phẩm có SKU KB-100.
- Thử lưu sản phẩm thứ hai có cùng SKU chuẩn hóa.
- Xác nhận database từ chối.
- Xác nhận adapter ánh xạ đúng constraint thành lỗi ứng dụng.
- Kiểm tra transaction không để lại bản ghi dở dang.

Không dùng H2 để giả định mọi hành vi constraint giống hệt production database nếu dự án phụ thuộc vào đặc tính riêng của PostgreSQL/MySQL.

## 10. Kịch bản thực hành theo từng bước

Thực hiện lần lượt. Mỗi bước cần có một kết quả có thể kiểm tra.

### Bước 1: Tạo Form DTO

- Tạo CreateProductForm.
- Thêm các trường name, sku, price, stock.
- Thêm constraint Bean Validation tương ứng.
- Dùng BigDecimal cho price và Integer cho stock.
- Không thêm ID, role, createdAt hoặc trạng thái nội bộ.

**Kết quả:** Form DTO chỉ đại diện dữ liệu người dùng được phép nhập.

### Bước 2: Tạo template

- Tạo trang thêm sản phẩm.
- Dùng th:object và th:field.
- Gắn label cho từng input.
- Hiển thị lỗi theo từng trường.
- Thêm nút submit.
- Dùng POST form với CSRF protection.

**Kết quả:** Người dùng có thể nhập và gửi đủ bốn trường.

### Bước 3: Tạo GET endpoint

- Route GET /admin/products/new.
- Tạo Form DTO rỗng.
- Đưa form vào Model với tên form.
- Trả template admin/products/new.

**Kết quả:** Mở URL hiển thị trang form không lỗi.

### Bước 4: Tạo POST endpoint

- Bind vào Form DTO bằng @ModelAttribute.
- Dùng @Valid.
- Đặt BindingResult ngay sau Form DTO.
- Nếu có lỗi, trả lại cùng View.
- Nếu hợp lệ, chuyển dữ liệu thành CreateProductCommand.

**Kết quả:** Lỗi binding/form không gọi use case.

### Bước 5: Tạo domain model

- Tạo ProductSku và quy tắc chuẩn hóa.
- Tạo Product factory.
- Bảo vệ name, price và stock invariant.
- Không để domain biết Spring MVC hoặc Thymeleaf.

**Kết quả:** Product không thể được tạo với trạng thái bất hợp lệ dù caller không đi qua form.

### Bước 6: Tạo application service

- Tạo CreateProductUseCase.
- Tạo CreateProductCommand.
- Kiểm tra SKU đã tồn tại.
- Tạo Product qua domain factory.
- Lưu qua ProductRepository port.

**Kết quả:** Quy tắc duy nhất được kiểm tra ở application; domain giữ invariant.

### Bước 7: Thêm unique constraint

- Tạo migration có unique constraint cho SKU chuẩn hóa.
- Trong persistence adapter, ánh xạ vi phạm constraint đã biết thành DuplicateSkuException.
- Không làm lộ SQL hoặc exception hạ tầng ra Controller.

**Kết quả:** Tính duy nhất vẫn được bảo vệ khi có request đồng thời.

### Bước 8: Xử lý lỗi và redirect

- SKU trùng trả lại form và lỗi ở trường sku.
- Thành công redirect tới danh sách sản phẩm.
- Hiển thị flash message ở trang đích.
- Không bắt mọi exception rồi trả cùng một lỗi form.

**Kết quả:** Phản hồi phân biệt rõ lỗi người dùng và thành công.

### Bước 9: Bảo vệ endpoint

- Yêu cầu role CATALOG_ADMIN.
- Giữ CSRF protection.
- Kiểm tra người không có quyền bị từ chối.
- Kiểm tra POST không có token bị từ chối.

**Kết quả:** Form không thể được sử dụng trái quyền.

### Bước 10: Viết test theo ranh giới

- Domain test cho invariant.
- Application test cho SKU trùng.
- MockMvc test cho binding và form validation.
- MockMvc test cho business error mapping.
- Security test cho role và CSRF.
- Persistence integration test cho unique constraint.

**Kết quả:** Mỗi nhóm test chỉ rõ loại kiểm tra và trách nhiệm được bảo vệ.

## 11. Bộ dữ liệu kiểm thử thủ công

Dùng các trường hợp sau để kiểm tra form qua trình duyệt:

| Lần thử | Name | SKU | Price | Stock | Kết quả mong đợi |
|---|---|---|---:|---:|---|
| 1 | Bàn phím cơ | KB-100 | 1250000.00 | 5 | Thành công nếu SKU chưa có |
| 2 | Trống | KB-101 | 100.00 | 2 | Lỗi name |
| 3 | Chuột | !@# | 100.00 | 2 | Lỗi định dạng SKU |
| 4 | Chuột | MS-100 | 0 | 2 | Lỗi price |
| 5 | Chuột | MS-101 | 100.00 | -1 | Lỗi stock |
| 6 | Chuột | KB-100 | 100.00 | 2 | Lỗi SKU trùng |
| 7 | Chuột | MS-102 | abc | 2 | Lỗi chuyển kiểu price |
| 8 | Chuột | MS-103 | 100.00 | để trống | Lỗi stock bắt buộc |

Giá trị ở lần 1 phù hợp với giới hạn @Digits đã khai báo. Nếu dùng tối đa 10 chữ số nguyên và 2 chữ số thập phân, giá trị 1250000.00 là hợp lệ; không nhập dấu phân tách hàng nghìn vào trường number nếu trình duyệt gửi chuỗi không phù hợp với locale.

Sau đó thử cùng form bằng tài khoản không có role quản trị và thử POST thiếu CSRF token trong test. Không cần dựa vào việc nút submit có bị ẩn hay không.

## 12. Tiêu chí nghiệm thu

| Tiêu chí | Đạt khi |
|---|---|
| Form GET | Trang thêm sản phẩm render với đủ bốn trường |
| Form binding | Giá trị hợp lệ được bind đúng kiểu |
| Form validation | Lỗi hiển thị đúng trường và giữ lại dữ liệu |
| Binding error | Giá trị không chuyển kiểu được xử lý như lỗi form |
| Application validation | SKU trùng bị từ chối trước khi lưu |
| Domain invariant | Giá không dương và tồn kho âm không tạo được Product |
| Persistence | Database có unique constraint cho SKU chuẩn hóa |
| Security | Chỉ role quản trị danh mục được tạo sản phẩm |
| CSRF | POST thiếu token bị từ chối |
| Thành công | Tạo sản phẩm xong redirect theo PRG |
| Kiểm thử | Có test riêng cho domain, application, MVC, security và persistence |

## 13. Lỗi thường gặp và cách tự sửa

### Đặt BindingResult sai vị trí

Nếu BindingResult không đứng ngay sau tham số có @Valid, Spring có thể không gắn lỗi vào đúng form. Đặt nó liền sau Form DTO.

### Bind trực tiếp vào Entity

Client có thể gửi thêm trường nội bộ hoặc làm ứng dụng phụ thuộc cấu trúc persistence. Dùng Form DTO chỉ chứa trường được phép nhập.

### Gọi use case dù form đã có lỗi

Điều này khiến tầng application nhận dữ liệu chưa hợp lệ và tạo lỗi khó hiểu. Kiểm tra bindingResult.hasErrors() trước khi gọi use case.

### Chỉ dùng JavaScript validation

Client có thể bị bỏ qua. Server vẫn phải bind, validate, kiểm tra nghiệp vụ và phân quyền.

### Chỉ kiểm tra SKU trùng bằng truy vấn trước khi lưu

Hai request đồng thời có thể cùng thấy SKU chưa tồn tại. Database unique constraint mới bảo vệ tính duy nhất cuối cùng.

### Đặt mọi quy tắc vào Controller

Controller phình to và use case khó dùng lại từ API khác hoặc job. Chuyển quy tắc nghiệp vụ vào application/domain.

### Bắt mọi exception rồi trả lỗi form

Lỗi database, timeout hoặc bug không phải lỗi nhập liệu. Chỉ ánh xạ các lỗi nghiệp vụ đã biết; lỗi kỹ thuật cần được xử lý tập trung và trả phản hồi an toàn.

### Tắt CSRF để làm form chạy

Điều này làm mất lớp bảo vệ cho form dùng session cookie. Kiểm tra token và cấu hình Thymeleaf/Spring Security đúng cách.

### Kiểm thử mọi thứ trong một integration test

Một test lớn khó chỉ ra ranh giới nào sai và thường chậm. Tách domain, application, MVC, security và persistence test; bổ sung integration test để xác nhận wiring thật.

## 14. Phần mở rộng

Sau khi hoàn thành yêu cầu cơ bản, có thể chọn một hoặc nhiều bài mở rộng:

1. Thêm trường category và kiểm tra category phải tồn tại.
2. Thêm ảnh sản phẩm, giới hạn loại MIME và dung lượng; không tin phần mở rộng file do client gửi.
3. Thêm chức năng sửa sản phẩm và xử lý optimistic locking khi hai quản trị viên cùng cập nhật.
4. Thêm thông báo lỗi chung cho lỗi hệ thống bằng ControllerAdvice.
5. Thêm localization cho thông báo validation.
6. Thêm test kiểm tra dữ liệu không tin cậy được escape trong HTML.
7. Thêm audit record lưu actorId và thời điểm tạo ở application boundary.
8. Thêm API REST dùng chung CreateProductUseCase để chứng minh quy tắc nghiệp vụ không phụ thuộc HTML Controller.

## Kết luận

Bài thực hành hoàn thành khi form thêm sản phẩm hoạt động và mỗi loại kiểm tra nằm đúng ranh giới. Binding và Bean Validation giúp phản hồi lỗi nhập liệu; domain invariant giữ Product hợp lệ; application service kiểm tra SKU theo ngữ cảnh; database unique constraint bảo vệ cạnh tranh đồng thời; authorization và CSRF bảo vệ request; các test riêng xác nhận từng hợp đồng. Khi tách rõ trách nhiệm như vậy, MVC vừa tạo được trải nghiệm biểu mẫu dễ dùng vừa giữ được quy tắc và dữ liệu an toàn ở phía server.

