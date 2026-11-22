# Truyền dữ liệu từ controller tới view bằng @ModelAttribute trong Spring MVC

## 1. Mục tiêu: controller chuẩn bị dữ liệu, view trình bày dữ liệu

Trong ứng dụng **Spring MVC render HTML phía server** (JSP, Thymeleaf và các template engine tương thích), controller chịu trách nhiệm chuẩn bị dữ liệu cho màn hình và trả về tên view hoặc `ModelAndView`. View sau đó đọc **model attributes** do controller cung cấp để hiển thị thông tin, điền giá trị mặc định của form và thông báo lỗi.

Ví dụ người dùng mở `GET /products/new`:

1. Controller tạo một `ProductForm` rỗng và đưa vào model với tên `productForm`.
2. Controller trả view name `"products/form"`.
3. Spring tìm view tương ứng, chẳng hạn `src/main/resources/templates/products/form.html` qua Thymeleaf.
4. Template truy cập `productForm.title` và `productForm.quantity`, render HTML và gửi trình duyệt.
5. Người dùng điền form, submit `POST /products`; Spring bind request parameters thành một `ProductForm` mới rồi kiểm tra validation.
6. Nếu có lỗi, controller trả lại view cùng model/form/errors để người dùng sửa. Nếu thành công, controller có thể redirect sang trang chi tiết.

**`@ModelAttribute` có hai cách sử dụng chính**:

- **Trên phương thức**: góp dữ liệu vào model **trước khi** request handler cùng controller thực thi; thường dùng các thông tin chung cho nhiều view.
- **Trên tham số phương thức**: lấy một object từ model hoặc tạo object khi chưa có, sau đó có thể bind dữ liệu HTTP vào object; object này đồng thời được đưa vào model cho view.

Thêm vào đó, controller có thể đưa dữ liệu vào model bằng `Model.addAttribute(...)`, `ModelMap` hoặc `ModelAndView`. Vì thế `@ModelAttribute` không phải con đường duy nhất để đưa dữ liệu sang view; giá trị của nó là kết hợp **model population** và **binding** theo vòng đời Spring MVC.

Phạm vi bài: **Spring MVC Servlet stack**, Java 17+, ví dụ Spring Boot 3.x, Thymeleaf và Jakarta Bean Validation. Spring WebFlux có annotation tương tự nhưng đường thực thi phản ứng khác. `@RestController` / `@ResponseBody` dùng để trả HTTP body trực tiếp (thường JSON), nên không xem việc trả một `String` từ REST controller như view name.

## 2. Model, ModelAndView, ViewResolver và template

Trong một request điển hình:

```text
Browser GET /products/new
          |
          v
DispatcherServlet -> HandlerMapping/HandlerAdapter
          |
          v
@Controller
  @ModelAttribute methods (chuẩn bị dữ liệu chung)
  @GetMapping handler (thêm productForm)
          |
          v
Model = {
  "catalogName": "Sổ sản phẩm",
  "productForm": ProductForm(...)
}
View name = "products/form"
          |
          v
ViewResolver (Thymeleaf/JSP tùy cấu hình)
          |
          v
Render HTML dùng model
          |
          v
HTTP 200 + text/html
```

- **Model** là cấu trúc chứa cặp *tên → giá trị* cho hoạt động render hiện tại. `org.springframework.ui.Model` là interface controller thường nhận qua tham số.
- **View name** là tên logic như `"products/form"`. View resolver và cấu hình engine quyết định nó tương ứng tài nguyên template nào.
- **View** dùng các model attributes để render HTML. Với Thymeleaf, cú pháp `${productForm}`, `${product.title}` hoặc `th:object` / `th:field` nhận dữ liệu model.
- **`ModelAndView`** gói cả model và view name trong một giá trị trả về khi cần.
- **`@Controller`** thường dùng cho HTML. `@RestController` tương đương `@Controller + @ResponseBody`, nghĩa là một `String` được viết vào HTTP response body, **không mặc nhiên là tên template**.

Model ở đây mang ngữ nghĩa **một lần render request**. Nó không tự duy trì dữ liệu giữa hai HTTP requests. Với redirect, cần `RedirectAttributes` / flash attributes; với workflow nhiều bước có thể cân nhắc `@SessionAttributes`. Những cơ chế này được phân biệt ở phần sau.

## 3. Ba cách chuyển dữ liệu sang view

### 3.1. Thêm vào `Model` ngay trong handler

```java
@Controller
class WelcomeController {

    @GetMapping("/welcome")
    String welcome(Model model) {
        model.addAttribute("message", "Chào mừng đến Spring MVC");
        model.addAttribute("visitors", 42);
        return "welcome";
    }
}
```

Mẫu trên là **class controller minh họa**, cần import `@Controller`, `@GetMapping` và `Model` cùng template `welcome`. Khi Thymeleaf render, template có thể dùng:

```html
<h1 th:text="${message}">Tiêu đề dự phòng</h1>
<p th:text="${visitors}">0</p>
```

`th:text` escape HTML theo mặc định khi hiển thị giá trị, an toàn hơn việc cố ý render raw HTML bằng `th:utext`. Tuy nhiên, escaping đầu ra không thay thế việc kiểm tra dữ liệu input hay phân quyền.

Tên attr phải khớp: `model.addAttribute("message", ...)` ứng với `${message}`. Nếu model đặt `"msg"` nhưng view đọc `"message"`, template sẽ không nhận được giá trị mong muốn.

### 3.2. `@ModelAttribute` ở cấp phương thức để chia sẻ dữ liệu

```java
@Controller
@RequestMapping("/products")
class ProductController {

    @ModelAttribute("catalogName")
    String catalogName() {
        return "Sổ sản phẩm";
    }

    @GetMapping("/new")
    String newForm(Model model) {
        model.addAttribute("productForm", new ProductForm());
        return "products/form";
    }
}
```

Method `catalogName()` được Spring MVC gọi để thêm thuộc tính `catalogName` vào model **trước handler `@GetMapping`** trong controller này. Bất kỳ template nào do những handler tương ứng render đều có thể đọc `${catalogName}`.

Khi nhiều controller cần dữ liệu chung, có thể khai báo `@ModelAttribute` method trong `@ControllerAdvice` với selector phù hợp. Không nên đặt các query database đắt tiền vào global method chạy cho mọi endpoint nếu nhiều endpoint không cần dữ liệu đó.

Một method cũng có thể thêm nhiều thuộc tính:

```java
@ModelAttribute
void populateFormOptions(Model model) {
    model.addAttribute("regions", List.of("north", "south"));
    model.addAttribute("pageTitle", "Create product");
}
```

Đây là **method fragment** trong controller/advice và cần import `java.util.List`. Method `void` nhận `Model`, không có một object return riêng để tự đặt tên.

Các method `@ModelAttribute` có thể dùng nhiều tham số được MVC hỗ trợ, nhưng không nhất thiết hỗ trợ tất cả tham số giống `@RequestMapping` (đặc biệt không dùng chúng làm thay thế handler đọc body). Chúng có thể gây side effect/performance nếu được gọi lặp lại trước nhiều handler; hãy giữ chúng phù hợp việc xây model.

### 3.3. Trả `ModelAndView` khi muốn đóng gói

```java
@GetMapping("/summary")
ModelAndView summary() {
    ModelAndView result = new ModelAndView("products/summary");
    result.addObject("count", 10);
    return result;
}
```

Đây là **method fragment**; cần import `org.springframework.web.servlet.ModelAndView` và template `products/summary`. Nó tương đương về ý định với việc thêm vào `Model` rồi trả tên view. Không bắt buộc phải dùng `ModelAndView` cho mọi handler; nhiều ứng dụng dùng `Model + String` gọn và dễ đọc hơn.

## 4. Phân biệt `@ModelAttribute` trên method và trên tham số

| Vị trí | Ví dụ | Điều gì xảy ra? | Dùng khi nào? |
| --- | --- | --- | --- |
| Method không phải request handler | `@ModelAttribute("catalogName") String name()` | Giá trị trả về được thêm vào model trước khi handler cùng phạm vi chạy | Tiêu đề, danh sách lựa chọn, dữ liệu chung |
| Method `void` | `@ModelAttribute void add(Model model)` | Method tự thêm một hay nhiều entries vào model | Nhiều dữ liệu phụ trợ cho form |
| Handler parameter | `save(@ModelAttribute("productForm") ProductForm form)` | Lấy/tạo model attribute, bind request values, sẵn cho view | Submit form HTML, data binding |
| Handler method | `@GetMapping @ModelAttribute("item") Item getItem()` | Return value của handler được diễn giải là model attribute, thay vì body/view name theo kiểu return | Muốn trả object trực tiếp vào model |
| Annotation trên `@RestController` | `@ModelAttribute` ở method có thể thêm model nhưng handler có `@ResponseBody` | HTTP response trực tiếp không tự render template | Thường không cần để truyền dữ liệu tới HTML view |

**Chú ý sự nhập nhằng của `String`:** Nếu một handler trong `@Controller` trả `"products/form"` không có `@ResponseBody` thì đó thường là **view name**; nhưng một method được đánh dấu `@ModelAttribute("label")` trả `String` nghĩa là **giá trị attribute** `label`, không phải tên view.

Spring suy ra tên model attribute từ kiểu khi không đặt tên tường minh. Nhưng khi form/template phụ thuộc tên cụ thể hoặc dùng `BindingResult`, đặt tên rõ ràng (ví dụ `"productForm"`) giúp tránh lệch tên khi refactor Java type và giúp test ổn định.

## 5. Mạch dữ liệu khi bind form vào `@ModelAttribute` tham số

Giả sử form HTML submit:

```http
POST /products HTTP/1.1
Content-Type: application/x-www-form-urlencoded

title=Notebook&quantity=3
```

Controller khai báo:

```java
@PostMapping("/products")
String create(@ModelAttribute("productForm") ProductForm form) {
    // form.getTitle() == "Notebook"
    // form.getQuantity() == 3
    return "products/result";
}
```

Đây là method fragment, cần có class `ProductForm`, controller và view `products/result`. Spring MVC thực hiện những bước cơ bản:

1. Tìm model attribute tên `productForm` đã có nếu tồn tại; tùy khai báo nó có thể đến từ `@ModelAttribute` method hoặc cơ chế model/session liên quan.
2. Nếu chưa tồn tại, Spring tạo object phù hợp, thường bằng constructor được hỗ trợ (mặc định hoặc primary constructor).
3. `WebDataBinder` dùng nguồn dữ liệu request để bind vào thuộc tính/constructor arguments. Servlet request parameters bao gồm query parameters và form-encoded data; đối với một số cấu hình, URI path variables/headers cũng có thể tham gia khi tên không bị parameter override.
4. `ConversionService`/property editors chuyển chuỗi thành kiểu Java, chẳng hạn `"3"` sang `Integer(3)`.
5. Nếu có `@Valid` hoặc `@Validated`, validator được kích hoạt; lỗi binding/validation được ghi nhận.
6. Object và metadata binding có thể được thêm vào model để view hiển thị lại giá trị người dùng vừa nhập.

**`@ModelAttribute` không tương đương `@RequestBody`**:

- `@ModelAttribute` phù hợp dữ liệu form/query/path/header theo cơ chế data binding.
- `@RequestBody` dùng `HttpMessageConverter` (ví dụ Jackson) đọc body JSON/XML theo content type.
- Gửi JSON `{"title":"Notebook"}` kèm `Content-Type: application/json` tới endpoint chỉ khai báo `@ModelAttribute ProductForm` **không khiến Jackson tự deserialize JSON thành form**.
- Với REST JSON API, thường chọn `@RequestBody` và trả `ResponseEntity`/DTO thay vì view name.

Khi method tham số là object phức tạp không được xử lý bằng resolver khác, Spring MVC có thể suy luận **implicit `@ModelAttribute`**. Tuy nhiên, nên khai báo tường minh để rõ contract và hỗ trợ phân tích AOT/native image.

## 6. Ví dụ có thể chạy: form tạo sản phẩm với Thymeleaf

Ứng dụng mẫu dùng **Spring Boot 3.x, Java 17+, Spring MVC Servlet + Thymeleaf + Jakarta Validation**. Bạn có thể thấy đủ chu trình:

```text
GET /products/new
    -> Model {"productForm", "catalogName"}
    -> render templates/products/form.html

POST /products
    -> @ModelAttribute("productForm") bind form data
    -> @Valid + BindingResult
       |
       +-- invalid -> render lại templates/products/form.html (HTTP 200)
       |
       +-- valid   -> lưu in-memory
                      addFlashAttribute("notice")
                      redirect:/products/{id} (HTTP 302)
                          |
                          v
                      GET /products/{id}
                      -> Model {"product", "catalogName", "notice"}
                      -> render templates/products/detail.html
```

HTTP 302 ở luồng Post-Redirect-Get là hành vi mặc định thông dụng của view redirect Spring MVC; có thể cấu hình redirect status riêng (ví dụ 303) khi hợp đồng yêu cầu, nhưng mẫu không tự đổi status.

### 6.1. Dependencies

Trong một dự án Spring Boot 3.x đã có plugin, repositories, Java toolchain và dependency management, thêm đoạn `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **fragment cấu hình Gradle**, không phải toàn bộ build file. Starter Thymeleaf cung cấp view resolver/template integration; starter validation có provider Jakarta Bean Validation. Nếu dùng Maven, khai báo các starter tương ứng trong `pom.xml` do Spring Boot BOM quản lý.

### 6.2. Mã Java

Tạo **`src/main/java/demo/modelview/ModelViewApplication.java`**:

```java
package demo.modelview;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@SpringBootApplication
public class ModelViewApplication {
    public static void main(String[] args) {
        SpringApplication.run(ModelViewApplication.class, args);
    }
}

// Form DTO: chỉ cho bind các field mà người dùng được nhập.
class ProductForm {
    @NotBlank
    private String title;

    @NotNull
    @Min(1)
    private Integer quantity;

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}

// View object chỉ chứa dữ liệu được phép hiển thị.
class Product {
    private final long id;
    private final String title;
    private final int quantity;

    Product(long id, String title, int quantity) {
        this.id = id;
        this.title = title;
        this.quantity = quantity;
    }

    public long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public int getQuantity() {
        return quantity;
    }
}

@Controller
@RequestMapping("/products")
class ProductController {

    private final AtomicLong sequence = new AtomicLong(1000);
    private final ConcurrentMap<Long, Product> products =
            new ConcurrentHashMap<>();

    @ModelAttribute("catalogName")
    String catalogName() {
        return "Sổ sản phẩm";
    }

    @GetMapping("/new")
    String newForm(Model model) {
        model.addAttribute("productForm", new ProductForm());
        return "products/form";
    }

    @PostMapping
    String create(
            @Valid @ModelAttribute("productForm") ProductForm form,
            BindingResult errors,
            RedirectAttributes redirects) {

        if (errors.hasErrors()) {
            return "products/form";
        }

        long id = sequence.incrementAndGet();
        Product saved = new Product(
                id, form.getTitle(), form.getQuantity());
        products.put(id, saved);

        redirects.addFlashAttribute(
                "notice", "Đã tạo sản phẩm thành công");
        return "redirect:/products/" + id;
    }

    @GetMapping("/{id}")
    String detail(@PathVariable long id, Model model) {
        Product product = products.get(id);
        if (product == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Product not found");
        }

        model.addAttribute("product", product);
        return "products/detail";
    }
}
```

Đây là **một file Java hợp lệ** trong project Boot 3, chỉ `ModelViewApplication` là public; các class còn lại là package-private. Spring Boot scan package `demo.modelview` để phát hiện `@Controller`.

Các điểm cốt lõi:

- `catalogName()` là method có `@ModelAttribute`, luôn thêm tiêu đề vào model trước các handler trong `ProductController`.
- `newForm(Model model)` đặt một `ProductForm` rỗng trong model, key tường minh là `"productForm"`.
- Khi submit, `@ModelAttribute("productForm") ProductForm form` bind form parameters; `@Valid` kiểm tra `@NotBlank`, `@NotNull` và `@Min(1)`.
- `BindingResult errors` phải đứng **ngay sau** `form`. Nếu không, validation errors thường thành exception trước khi controller có cơ hội trả lại form.
- Nếu lỗi, trả view `products/form` trong **cùng request**. Model giữ form và `BindingResult` để Thymeleaf đọc lỗi.
- Nếu thành công, controller lưu dữ liệu demo, rồi thêm **flash attribute** `notice` và redirect sang GET chi tiết. Dữ liệu render của response sau redirect được chuẩn bị từ **request GET mới**.
- Dùng `ProductForm` riêng với các field public bind được; không bind trực tiếp entity hoặc bean chứa `role`, `priceOverride`, `isAdmin` hay field nhạy cảm do client không được sửa.
- `ConcurrentHashMap` chỉ dùng để minh họa: không có database, transaction, lưu lâu dài, shared state giữa nhiều instance. Không đưa lựa chọn in-memory này vào production mà không thay kiến trúc persistence.

### 6.3. Thymeleaf form template

Tạo **`src/main/resources/templates/products/form.html`**:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Tạo sản phẩm</title>
</head>
<body>
  <h1 th:text="${catalogName}">Tên danh mục</h1>
  <h2>Tạo sản phẩm</h2>

  <form th:action="@{/products}" th:object="${productForm}" method="post">
    <div>
      <label for="title">Tên sản phẩm</label>
      <input id="title" type="text" th:field="*{title}">
      <small th:if="${#fields.hasErrors('title')}"
             th:errors="*{title}">Lỗi tên</small>
    </div>

    <div>
      <label for="quantity">Số lượng</label>
      <input id="quantity" type="number" th:field="*{quantity}">
      <small th:if="${#fields.hasErrors('quantity')}"
             th:errors="*{quantity}">Lỗi số lượng</small>
    </div>

    <button type="submit">Tạo</button>
  </form>
</body>
</html>
```

Giải thích Thymeleaf:

- `th:object="${productForm}"` chọn object form trong model làm ngữ cảnh cho biểu thức `*{...}`.
- `th:field="*{title}"` đọc giá trị thuộc tính và tạo các thuộc tính HTML name/id/value phù hợp cho form binding.
- `#fields.hasErrors('title')`/`th:errors` dựa vào binding/validation errors của attribute `productForm`. Spring cũng đưa metadata lỗi vào model với key dạng `org.springframework.validation.BindingResult.productForm`.
- `th:text="${catalogName}"` lấy dữ liệu do `@ModelAttribute("catalogName")` method cung cấp.
- Khi form submit sai, template được render lại và hiển thị lỗi thay vì redirect, giúp giữ thông tin người dùng vừa nhập.

**Nếu có Spring Security với CSRF protection bật**, form POST trong ứng dụng thật phải có CSRF token hợp lệ; Thymeleaf/Spring Security integration có thể tự thêm hidden token tùy cấu hình. Ví dụ dependency trên không bao gồm Spring Security nên chưa có yêu cầu đó. Không tắt CSRF bừa bãi chỉ để demo chạy.

### 6.4. Thymeleaf detail template

Tạo **`src/main/resources/templates/products/detail.html`**:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Chi tiết sản phẩm</title>
</head>
<body>
  <h1 th:text="${catalogName}">Tên danh mục</h1>
  <p th:if="${notice}" th:text="${notice}">Thông báo</p>

  <dl>
    <dt>ID</dt>
    <dd th:text="${product.id}">0</dd>
    <dt>Tên</dt>
    <dd th:text="${product.title}">Tên mẫu</dd>
    <dt>Số lượng</dt>
    <dd th:text="${product.quantity}">0</dd>
  </dl>

  <a th:href="@{/products/new}">Thêm sản phẩm</a>
</body>
</html>
```

`${product.id}`, `${product.title}` và `${product.quantity}` được Thymeleaf/Spring EL đọc từ các JavaBean getter của `Product`. Model ở request GET hiện tại có `product` được đặt bằng `model.addAttribute("product", product)`.

`notice` không đến từ `@ModelAttribute("catalogName")`: nó là **flash attribute** ở redirect từ POST trước đó. Nếu người dùng mở detail trực tiếp, `notice` có thể không tồn tại; `th:if="${notice}"` ngăn hiển thị phần thông báo.

### 6.5. Chạy và kiểm tra kết quả

Chạy dự án Spring Boot đã thiết lập:

```bash
./gradlew bootRun
```

Mở `http://localhost:8080/products/new` trên trình duyệt. View form phải hiển thị:

```text
Sổ sản phẩm
Tạo sản phẩm
Tên sản phẩm: [             ]
Số lượng:    [             ]
[Tạo]
```

Phần này là **mô phỏng nội dung giao diện**, không phải stdout của Java. Điền tên “Sổ tay”, số lượng “2” rồi submit. Trình duyệt nhận redirect tới dạng `/products/1001` (nếu chưa có POST khác kể từ khi start), sau đó hiển thị detail kèm thông báo.

Có thể quan sát response bằng curl:

```bash
curl -i 'http://localhost:8080/products/new'

curl -i -X POST 'http://localhost:8080/products' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=So tay' \
  --data-urlencode 'quantity=2'
```

POST hợp lệ trả status redirect, thường **302 Found**, cùng header `Location` trỏ đến `/products/{id}`. `curl` không theo redirect nếu không thêm `-L`, nên response ban đầu sẽ chưa là HTML chi tiết. Nếu muốn theo request tiếp theo, dùng `curl -L`, cần chú ý HTTP method follow-redirect theo client; với form browser thông thường sẽ GET trang đích.

POST không hợp lệ:

```bash
curl -i -X POST 'http://localhost:8080/products' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=' \
  --data-urlencode 'quantity=0'
```

Khi validation thất bại, method trả `"products/form"` trực tiếp: thường HTTP **200 OK**, có HTML form với thông báo lỗi ở title/quantity. Đây là cách xử lý form HTML điển hình, nhưng **không mặc nhiên thích hợp cho JSON API**; REST API thường dùng 400 với error body thay cho render form.

## 7. `@ModelAttribute` method được gọi khi nào?

Theo cơ chế Spring MVC, method `@ModelAttribute` trong cùng controller được thực thi **trước `@RequestMapping` method tương ứng** để chuẩn bị model. Có thể đặt method như vậy trong `@ControllerAdvice` để dùng chung nhiều controller, tùy selectors và advice ordering.

Ví dụ:

```java
@ControllerAdvice(assignableTypes = ProductController.class)
class ProductViewAdvice {

    @ModelAttribute("footerText")
    String footer() {
        return "© Demo Catalog";
    }
}
```

Đây là fragment bổ sung cho project ví dụ phần 6; cần import `org.springframework.web.bind.annotation.ControllerAdvice` và `ModelAttribute`. Nếu thêm class này vào cùng package, các view của `ProductController` có thể đọc `footerText`.

Không sử dụng `@ModelAttribute` method như interceptor điều khiển mọi HTTP lifecycle, vì nó chỉ tham gia xử lý controller qua MVC theo điều kiện invocation. Nó không bảo đảm chạy với static assets, request bị filter/security chặn trước MVC, hoặc một số lỗi phát sinh trước khi handler được chọn.

### Có bắt buộc phải dùng `Model` parameter trong method `@ModelAttribute`?

Không. Có hai mẫu chính:

```java
@ModelAttribute("applicationName")
String applicationName() {
    return "Spring Training";
}
```

Giá trị return được thêm dưới tên `applicationName`, hoặc:

```java
@ModelAttribute
void setup(Model model) {
    model.addAttribute("applicationName", "Spring Training");
    model.addAttribute("displayCurrency", "VND");
}
```

Ở mẫu thứ hai, method tự thêm nhiều entries. Đây là **các fragment thay thế nhau**, không nên đặt cả hai cùng tên và ghi đè chéo nếu không có quy tắc rõ.

### `@ModelAttribute` trên chính handler method

Spring cũng cho phép:

```java
@GetMapping("/current-product")
@ModelAttribute("product")
Product currentProduct() {
    return productService.current();
}
```

Đây là fragment dùng service do ứng dụng định nghĩa. `@ModelAttribute("product")` đặt trên handler method làm **giá trị trả về được hiểu như model attribute**, thay vì coi một `String` là tên view hay dùng `@ResponseBody` để ghi JSON. Nếu method không khai báo view name rõ, Spring có thể sử dụng cơ chế mặc định suy ra view name từ request URL; cần bảo đảm view resolver/template tương ứng.

Đừng dùng kiểu này khi một controller trả API JSON và vô tình mong response được serialize; trong REST controller hãy thể hiện `@ResponseBody`/`ResponseEntity` theo hợp đồng.

## 8. `@ModelAttribute` method và `Model.addAttribute`: nên chọn gì?

| Tình huống | Giải pháp | Lý do |
| --- | --- | --- |
| Mỗi page cần dữ liệu riêng do handler vừa tải | `Model.addAttribute("product", product)` | Nguồn dữ liệu rõ trong method |
| Nhiều view của cùng controller đều cần tên danh mục | Method `@ModelAttribute("catalogName")` | Tránh lặp logic |
| Nhiều controller cùng cần một bộ chọn ngôn ngữ/nhãn | `@ControllerAdvice` có method `@ModelAttribute` | Chia sẻ theo selector phù hợp |
| Handler trả cả model và view name | `ModelAndView` | Một return object rõ ràng |
| Form submit cần bind và hiển thị lỗi | `@Valid @ModelAttribute("productForm")` + `BindingResult` | Spring quản lý binding/errors |
| Redirect sau POST thành công | `RedirectAttributes.addFlashAttribute(...)` | Truyền thông báo ngắn tới request kế tiếp |
| Dữ liệu dùng qua nhiều bước của một wizard | `@SessionAttributes` (cẩn trọng) | Model attributes được giữ ở HTTP session cho workflow |
| API REST trả JSON | `@RequestBody`, `@ResponseBody`, `ResponseEntity` | Không qua view template |

Quy tắc thiết kế: không đưa toàn bộ cơ sở dữ liệu hay những object nhạy cảm vào model chỉ vì template cần vài trường. Truyền **view model/DTO vừa đủ** giúp tránh dữ liệu thừa và nguy cơ vô tình render trường không được phép công khai.

## 9. BindingResult phải đi liền form object

Với form validation, mẫu chuẩn:

```java
@PostMapping("/save")
String save(
        @Valid @ModelAttribute("form") ProductForm form,
        BindingResult result,
        Model model) {

    if (result.hasErrors()) {
        return "products/form";
    }

    // Thực hiện thao tác lưu thành công, sau đó redirect.
    return "redirect:/products";
}
```

Đây là **fragment** trong controller; biến `form`, view path và destination cần gắn với ứng dụng thật.

`BindingResult` hoặc `Errors` phải khai báo **ngay sau** tham số được kiểm tra. Spring sử dụng nó để báo lỗi chuyển kiểu và validation, đồng thời cung cấp các lỗi cho view engine. Trong view dùng:

```html
<form th:object="${form}">
  <input th:field="*{title}">
  <span th:if="${#fields.hasErrors('title')}"
        th:errors="*{title}">Lỗi</span>
</form>
```

Nếu `BindingResult` thiếu hoặc sai vị trí, lỗi có thể gây exception trước khi body controller chạy. Với Spring Framework 6.1+, nếu handler có constraint trực tiếp trên method parameters làm bật native method validation, đường exception có thể là `HandlerMethodValidationException`; không cứng nhắc cho rằng mọi validation form đều chỉ có một exception type.

### Bind sai kiểu trước khi validate

Nếu form có `Integer quantity` nhưng client gửi `quantity=abc`, Spring không thể chuyển thành Integer. Lỗi **type mismatch** được ghi trong `BindingResult` (với cấu hình xử lý phù hợp), dù annotation `@Min(1)` chưa nhận được một số hợp lệ để so sánh. Template cần hiển thị lỗi chuyển kiểu thay vì chỉ xem constraint annotations.

Tương tự, một `@NotNull` đặt trên `Integer` không bắt lỗi khi input là chuỗi không convert được theo cùng cách như một giá trị Java `null`; cả binding errors và validation errors đều cần hiển thị.

## 10. Bảo mật data binding: tránh mass assignment

`@ModelAttribute` có thể bind nhiều thuộc tính của object từ request; tính thuận tiện này dẫn đến **mass assignment / over-posting** nếu bind trực tiếp domain entity:

```java
// Ví dụ không nên dùng trực tiếp với entity chứa trường nhạy cảm.
@PostMapping("/users/update")
String update(@ModelAttribute UserEntity user) {
    repository.save(user);
    return "redirect:/users";
}
```

Client có thể thử gửi thêm parameter như `isAdmin=true` hoặc `balance=999999` nếu object có property writable cùng tên. Khi bind thẳng entity, attacker có thể sửa fields mà UI không hiển thị.

Các biện pháp:

1. Dùng **form DTO riêng** chỉ chứa dữ liệu cần nhận từ client, như `ProductForm` ở ví dụ.
2. Chỉ chấp nhận những fields được phép sửa, tránh writable setter cho secret fields.
3. Khi cần dùng property binding trên object phức tạp, cấu hình `WebDataBinder#setAllowedFields(...)` bằng `@InitBinder` để whitelist field cho phép.
4. Không coi `@ModelAttribute(binding=false)` là bộ lọc authorization tổng quát; nó **tắt binding** cho object đã chọn, còn cập nhật database vẫn phải kiểm tra quyền.
5. Kiểm tra authorization, ownership và business rules ở service/domain, không tin dữ liệu form do client gửi.
6. Sử dụng CSRF protection phù hợp với HTML form có cookie authentication.

Ví dụ giới hạn field:

```java
@InitBinder("productForm")
void productBinder(WebDataBinder binder) {
    binder.setAllowedFields("title", "quantity");
}
```

Đây là **method fragment** trong controller hoặc advice, cần import `org.springframework.web.bind.annotation.InitBinder` và `org.springframework.web.bind.WebDataBinder`. Nó minh họa cách chặn việc bind thêm ngoài hai field được cho phép. Nếu DTO đã chỉ có title/quantity, biện pháp này bổ sung lớp bảo vệ, nhưng cần test vì mọi form có nested properties/collection có thể cần allowed field patterns chi tiết.

**Constructor binding** cũng là lựa chọn an toàn khi thiết kế immutable form DTO rõ ràng, nhưng cần version/framework hỗ trợ và cách đặt tên constructor parameters phù hợp. Với bean setters của ví dụ, binding đơn giản để quan sát; không mặc định áp dụng kiểu dữ liệu thực thể giàu thuộc tính.

## 11. Redirect không giữ nguyên model của request trước

Khi controller trả `"redirect:/products/1001"`, Spring gửi HTTP 3xx và trình duyệt tạo **HTTP request mới**. Model của POST **không mặc nhiên còn nguyên** ở GET. Có ba cách cung cấp dữ liệu cho đích redirect:

1. **Path/query parameters**: dùng URL như `/products/1001` hoặc `?view=compact` để GET tự tải dữ liệu cần thiết.
2. **`RedirectAttributes.addAttribute(...)`**: thêm URI variables / query attributes vào redirect URL theo contract. Dữ liệu có thể hiển thị trong address bar, logs, history.
3. **`RedirectAttributes.addFlashAttribute(...)`**: tạm lưu thông điệp hoặc dữ liệu cho request sau redirect; thông thường lưu tạm trong HTTP session rồi đưa vào model request đích.

Trong ví dụ chính:

```java
redirects.addFlashAttribute("notice", "Đã tạo sản phẩm thành công");
return "redirect:/products/" + id;
```

Đây là fragment đã có ở phần 6. Sau redirect, controller GET tự thêm `product` vào model; `notice` được Spring lấy từ **input FlashMap** và đưa vào model cho request đích. Flash attribute **không phải session state dài hạn** và thường được sử dụng một lần.

Mặt trái của cách gửi dữ liệu qua URL:

```java
redirects.addAttribute("notice", "Đã tạo sản phẩm");
```

Nếu tham số được dùng để dựng redirect URL, text này có thể xuất hiện trong query string và bị lưu vào browser history/referrer/log. Hãy chọn flash attribute cho thông báo hiển thị tạm thời, không đưa thông tin bí mật vào URI.

**Cảnh báo về redirect model:** cấu hình MVC có thể cho phép một số model attributes tự xuất hiện trong redirect URI nếu không dùng `RedirectAttributes`. Vì vậy, để tránh vô tình phát lộ dữ liệu trong URL, nên chỉ định rõ những attributes được phép dùng cho redirect và cân nhắc cấu hình `ignoreDefaultModelOnRedirect` theo contract framework đang chạy.

## 12. `@ModelAttribute`, `@SessionAttributes` và `@SessionAttribute`

Ba annotation này có tên gần nhau nhưng không giống nhau:

| Annotation | Vị trí | Ý nghĩa |
| --- | --- | --- |
| `@ModelAttribute` | Method/parameter của controller | Bổ sung hoặc truy cập/bind dữ liệu model cho MVC |
| `@SessionAttributes` | **Class controller** | Lưu **một số model attributes** trong HTTP session cho workflow controller |
| `@SessionAttribute` | **Method parameter** | Đọc một giá trị đã tồn tại trong HTTP session, không trực tiếp quản lý model workflow |

Ví dụ khi có form nhiều bước:

```java
@Controller
@SessionAttributes("draft")
class OrderWizardController {

    @ModelAttribute("draft")
    OrderDraft draft() {
        return new OrderDraft();
    }

    @GetMapping("/wizard")
    String show() {
        return "orders/wizard";
    }

    @PostMapping("/wizard/finish")
    String finish(
            @ModelAttribute("draft") OrderDraft draft,
            SessionStatus sessionStatus) {
        // Thực hiện save hợp lệ.
        sessionStatus.setComplete();
        return "redirect:/orders";
    }
}
```

Đây là **fragment minh họa**, cần khai báo `OrderDraft` và templates; thêm imports `@SessionAttributes`, `SessionStatus`, `@ModelAttribute`, `@Controller`, `@GetMapping`, `@PostMapping`. Thực tế cần `@Valid` và bảo vệ CSRF/auth/transactions trước khi hoàn tất.

`@SessionAttributes("draft")` nói Spring giữ model attribute `draft` trong session của workflow controller; `SessionStatus#setComplete()` đánh dấu hoàn thành để Spring dọn những model attributes đã quản lý qua `@SessionAttributes`. Nó **không** có nghĩa invalidate toàn bộ user session hay đăng xuất.

Không dùng `@SessionAttributes` chỉ vì nhiều trang đều cần tên website hoặc currency label. Các thông tin đọc chung có thể nạp từ config/service qua `@ModelAttribute` hoặc global advice; session giữ state người dùng và tăng độ phức tạp concurrency/lifecycle.

## 13. `@ModelAttribute(binding=false)` và các nguồn object đã tồn tại

Đôi khi controller cần một object từ DB đặt vào model, nhưng **không muốn request parameters tự sửa object đó**.

Ví dụ:

```java
@ModelAttribute("product")
Product product(@PathVariable long id) {
    return catalogService.getRequired(id);
}

@PostMapping("/products/{id}/review")
String review(
        @ModelAttribute(binding = false) Product product,
        @Valid @ModelAttribute("reviewForm") ReviewForm form,
        BindingResult result) {
    // Kiểm tra quyền, hợp đồng và lưu đánh giá.
    return "redirect:/products/" + product.getId();
}
```

Đây là các fragment mô tả pattern; `catalogService`, `ReviewForm`, đường mapping và authorization cần được ứng dụng tự triển khai. `binding=false` ngăn việc lấy parameters của request để mutate trực tiếp `product`, còn `reviewForm` vẫn được bind và validate.

Thứ tự đưa object vào model và nguồn object phải được kiểm tra theo request mappings thực tế. Với một số kiểu dữ liệu, Spring có thể tạo model attribute bằng converter/constructor khi chưa có; không giả định nó tự tìm object trong repository chỉ vì có `@ModelAttribute("product")`.

## 14. Kiểm thử với MockMvc cho cả model, view và binding

Tạo **`src/test/java/demo/modelview/ModelViewApplicationTests.java`**:

```java
package demo.modelview;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class ModelViewApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void getFormIncludesAttributesAndResolvesView() throws Exception {
        mvc.perform(get("/products/new"))
            .andExpect(status().isOk())
            .andExpect(view().name("products/form"))
            .andExpect(model().attributeExists(
                    "catalogName", "productForm"))
            .andExpect(model().attribute(
                    "catalogName", "Sổ sản phẩm"));
    }

    @Test
    void invalidFormKeepsFormAndValidationErrors() throws Exception {
        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("title", "")
                .param("quantity", "0"))
            .andExpect(status().isOk())
            .andExpect(view().name("products/form"))
            .andExpect(model().attributeHasFieldErrors(
                    "productForm", "title", "quantity"));
    }

    @Test
    void validFormRedirectsToCreatedProduct() throws Exception {
        MvcResult created = mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("title", "Notebook")
                .param("quantity", "2"))
            .andExpect(status().is3xxRedirection())
            .andExpect(flash().attribute(
                    "notice", "Đã tạo sản phẩm thành công"))
            .andReturn();

        String destination = created.getResponse().getRedirectedUrl();
        assertNotNull(destination);
        assertTrue(destination.matches("/products/[0-9]+"));

        // MockMvc không tự follow redirect; kiểm tra GET riêng.
        mvc.perform(get(destination).flashAttrs(created.getFlashMap()))
            .andExpect(status().isOk())
            .andExpect(view().name("products/detail"))
            .andExpect(model().attributeExists(
                    "product", "catalogName"))
            .andExpect(model().attribute(
                    "notice", "Đã tạo sản phẩm thành công"));
    }

    @Test
    void unknownProductReturns404() throws Exception {
        mvc.perform(get("/products/9223372036854775807"))
            .andExpect(status().isNotFound());
    }
}
```

Chạy:

```bash
./gradlew test
```

Với các file phần 6 và dependency Boot 3 đã cấu hình, **bốn test dự kiến pass**. Đây là kỳ vọng dựa trên code mẫu, không phải kết quả đã chạy Gradle. Test xác minh:

- `model().attributeExists(...)` khẳng định controller đã truyền dữ liệu vào model.
- `view().name(...)` xác nhận view name được chọn thay vì trả dữ liệu JSON trực tiếp.
- `attributeHasFieldErrors(...)` kiểm tra binding/validation xuất hiện trong model khi input sai.
- `flash().attribute(...)` xác nhận flash message được thêm trước redirect.
- POST thành công tạo URI resource mới; GET kế tiếp có model `product` và view đúng. `flashAttrs(created.getFlashMap())` mô phỏng việc cấp lại flash attributes cho request GET trong bài test độc lập.

**Giới hạn MockMvc:** không xác minh hoàn toàn hành vi proxy, browser thật, CSRF khi tích hợp Security, session store đa node hoặc JavaScript trên trang. Với sản phẩm có giao diện quan trọng, kết hợp view/MockMvc tests với browser integration tests.

### Test khi form bị type mismatch

Thêm case `quantity=abc` và assert `model().attributeHasFieldErrors("productForm","quantity")`. Điều này chứng minh Spring giữ lỗi conversion để render view thay vì để mã Java ném `NumberFormatException` sau khi controller đã chạy. Không nên assert thông điệp lỗi tiếng Anh cụ thể vì chúng phụ thuộc MessageSource/locale.

## 15. So sánh truy cập model trong Thymeleaf, JSP và REST

### Thymeleaf

Thông thường dùng:

```html
<span th:text="${catalogName}">Fallback</span>
<input th:field="*{title}">
```

Đầu tiên đọc model attr. Dòng thứ hai cần nằm trong form có `th:object="${productForm}"` để sử dụng selection expression `*{title}`. Spring integration hỗ trợ binding/error state.

### JSP + Spring Form Tags

Ví dụ fragment trong JSP đã cấu hình JSTL/taglib:

```jsp
<spring:eval expression="catalogName" var="catalogNameText"/>
<p>${catalogNameText}</p>
```

Đây là **fragment minh họa ý tưởng JSP**, không phải mã trực tiếp áp dụng nguyên xi mà không khai báo taglib phù hợp. Với JSP, JSP Expression Language thực tế thường dùng `${catalogName}` đọc model attribute đã expose trong request scope; Spring form tags có binding và errors riêng theo form model. Khi dùng Thymeleaf trong ứng dụng mẫu thì **không cần cấu hình JSP**.

### JSON REST

```java
@RestController
class CatalogApi {
    @GetMapping("/api/catalog")
    java.util.Map<String, String> catalog() {
        return java.util.Map.of("name", "Sổ sản phẩm");
    }
}
```

Ở đây `Map` là **response body** được message converter serialize (thường JSON), không phải model dành cho template. Nếu trong `@RestController` bạn trả `"products/form"`, body có thể chứa đúng text `products/form` thay vì render trang HTML. Đây là lỗi thường gặp khi chuyển code từ MVC view sang REST API.

## 16. Lỗi phổ biến khi dùng `@ModelAttribute`

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Template không thấy `productForm` | Controller quên `model.addAttribute("productForm", ...)` hoặc tên khác | Đặt tên model attr tường minh và assert bằng MockMvc |
| Form submit không bind vào object | Input `name` khác property hoặc content type không phù hợp | Dùng `th:field` hoặc kiểm tra form names / setters / constructors |
| Trả chữ `products/form` trên trình duyệt | Dùng `@RestController`/`@ResponseBody` | Chuyển controller phục vụ HTML sang `@Controller` |
| HTML form có lỗi nhưng không hiển thị | Thiếu `BindingResult` cạnh form hoặc template không dùng `th:errors` | Kiểm tra thứ tự tham số và name `th:object` |
| Invalid form redirect làm mất lỗi/value | Dùng redirect trong nhánh validation failed | Render trực tiếp cùng request hoặc thiết kế flash model phù hợp |
| Success message mất sau redirect | Đặt notice trong Model của POST | Dùng `RedirectAttributes.addFlashAttribute` |
| Model chứa dữ liệu cũ qua GET | Kỳ vọng request Model tự persist | GET tải lại data; session/flash nếu thực sự cần |
| Người dùng sửa field admin ngoài form | Bind trực tiếp entity có setters công khai | Form DTO riêng và allowed fields |
| Method `@ModelAttribute` chạy nhiều lần bất ngờ | Method góp model cho nhiều handler | Giảm side effect, cache nơi phù hợp và giới hạn scope |
| Model không được render | Method trả `@ResponseBody`/`ResponseEntity` | Chỉ render template khi handler trả view name hoặc ModelAndView |
| `@SessionAttributes` không được dọn | Quên `SessionStatus#setComplete()` | Hoàn thành wizard đúng lifecycle |
| Biến thể URL sau reverse proxy trả sai redirect | Context path/gateway prefix chưa đồng bộ | Kiểm tra `RedirectView`, forwarded headers đáng tin, test deploy path |

Các biểu hiện có thể chịu ảnh hưởng cấu hình khác (Spring Security, view resolver, filter, lỗi input); nên test và logs là nguồn xác nhận thay vì phỏng đoán.

## 17. Những điểm cần nắm khi nâng phiên bản Spring

**Spring Framework 5.x / Boot 2.x:** `@Controller`, `Model` và `@ModelAttribute` có semantics cơ bản như bài. Với Bean Validation, namespace thường là `javax.validation.Valid`. Tích hợp JSP/Thymeleaf phụ thuộc Boot starter và version.

**Spring Framework 6.x / Boot 3.x:** baseline Java 17+, Jakarta EE namespace chuyển sang `jakarta.validation.Valid` và `jakarta.servlet.*`. Spring 6 hỗ trợ constructor binding, Servlet data binding và cơ chế model ở MVC. Ví dụ bài dùng Boot 3.x với Thymeleaf. Native MVC method validation từ Framework 6.1 có thể ảnh hưởng exception trên một số handler khi constraints trực tiếp xuất hiện ở tham số method.

**Spring Framework 7.x / Boot 4.x:** các ý tưởng `@ModelAttribute` method, parameter binding, model/view và flash attributes vẫn còn. Tuy nhiên, dependency coordinates, starter module và các integration khác có thể thay đổi; cần xác nhận template engine / Spring MVC BOM theo version. Không sao chép build snippet Boot 3 vào Boot 4 mà bỏ qua migration guide.

Một lưu ý riêng với **GraalVM native image/AOT**: Spring khuyến nghị **khai báo `@ModelAttribute` tường minh** trên complex-type method arguments để phát hiện reflection hints cho data binding đúng; reliance on implicit `@ModelAttribute` có thể hạn chế AOT inference.

Những thay đổi version này không làm biến `@ModelAttribute` thành JSON parser hoặc cơ chế session tự động. Luôn đặt bài toán dữ liệu trong bối cảnh **view rendering vs request binding vs API response**.

## 18. Checklist xây form an toàn và dễ bảo trì

- [ ] Controller phục vụ HTML dùng `@Controller` và trả tên view hợp lệ.
- [ ] Form GET thêm object vào model với key tường minh; template `th:object` sử dụng đúng key.
- [ ] Tài nguyên template tồn tại trong thư mục được engine cấu hình và thuộc đúng view name.
- [ ] Các model attributes chung qua method `@ModelAttribute` không chạy query thừa hoặc làm thay đổi trạng thái ngoài ý muốn.
- [ ] POST chỉ bind vào DTO/form object cho phép, không bind trực tiếp entity chứa dữ liệu nhạy cảm.
- [ ] `@Valid`/`@Validated` phù hợp với constraints; `BindingResult` đứng ngay sau form parameter.
- [ ] Nếu lỗi, trả lại form cùng request, giữ errors và giá trị đã nhập.
- [ ] Nếu thành công, lưu xong rồi redirect theo Post-Redirect-Get, dùng flash attrs cho thông báo ngắn.
- [ ] Không đưa dữ liệu bí mật vào URL qua redirect attributes.
- [ ] Nếu dùng `@SessionAttributes`, lifecycle và `SessionStatus#setComplete()` rõ ràng.
- [ ] Form có CSRF protection khi dùng cookie-based authenticated actions.
- [ ] Có test cho model attributes, view name, field errors, redirect và flash attributes.
- [ ] Không giả định model/flash là persistence store hoặc cache dùng giữa mọi request.

## 19. Bài tập vận dụng

1. Thêm một method `@ModelAttribute("currentYear")` trong `ProductController`, hiển thị năm ở cả form và detail. Vì sao không cần thêm `model.addAttribute("currentYear", ...)` vào từng handler?
2. Trong form template, đổi `th:object="${productForm}"` thành `${product}`. Điều gì xảy ra nếu model chỉ có `productForm`? Làm sao MockMvc phát hiện lỗi này?
3. Bỏ `BindingResult` khỏi POST create rồi gửi `quantity=0`. Phân tích đường đi của validation, exception và status mặc định.
4. Chuyển POST create thành `@RestController`, trả `"products/detail"`. Vì sao trình duyệt không còn render view?
5. Một client gửi thêm `isAdmin=true` ngoài các field trong HTML. Giải thích vì sao bind entity nhiều setters tiềm ẩn rủi ro; thêm `@InitBinder#setAllowedFields` hoặc chuyển sang form DTO.
6. Viết test `POST /products` thành công, lấy URL từ `Location`, gửi request GET tiếp và kiểm tra model có thuộc tính `product`.
7. Thử chuyển thông báo thành công từ `addFlashAttribute` sang `addAttribute`. Phân biệt flash/session và query string, các rủi ro URL logging.
8. Xây một wizard ba bước dùng `@SessionAttributes("draft")`. Khi hoàn tất, tại sao nên gọi `SessionStatus#setComplete()` thay vì invalidate toàn bộ session?
9. Sửa form để nhận số lượng bằng `Integer` và gửi `quantity=abc`. Kiểm tra field error do conversion, giải thích vì sao nó khác lỗi `@Min(1)`.
10. Dùng `@ControllerAdvice` để thêm danh sách vùng lựa chọn cho hai controller. Làm sao giới hạn advice chỉ áp dụng cho nhóm view phù hợp và tránh chạy DB query trên mọi REST endpoint?

## 20. Tài liệu chính thức

- [Spring Framework — Model và `@ModelAttribute` methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-modelattrib-methods.html): method-level attribute population.
- [Spring Framework — `@ModelAttribute` method arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): binding, validation, object creation, `binding=false` và AOT.
- [Spring Framework — Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): `Model`, `BindingResult`, `RedirectAttributes`, `@SessionAttributes`.
- [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): String view name, ModelAndView, Model/Map, ResponseBody.
- [Spring Framework — Redirect Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html): truyền dữ liệu qua URI và flash attributes, `ignoreDefaultModelOnRedirect`.
- [Spring Framework — Flash Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/flash-attributes.html): FlashMap, lifecycle, concurrency.
- [Spring Framework — `@SessionAttributes`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html): model/session workflow.
- [Spring Framework — Data Binding and Validation](https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html): `DataBinder`, binding và allowed fields.
- [Thymeleaf — Spring Integration Tutorial](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): `th:object`, `th:field`, form errors và Spring model.
