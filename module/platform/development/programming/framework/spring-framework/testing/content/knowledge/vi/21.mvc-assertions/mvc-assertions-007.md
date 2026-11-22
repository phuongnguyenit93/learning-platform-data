# Model, view name và ModelAndView

Trong Spring MVC, controller có thể trả về dữ liệu để một view hiển thị thành trang web. Ba khái niệm thường đi cùng nhau là **model**, **view name** và **`ModelAndView`**. Model chứa dữ liệu mà view cần dùng; view name xác định view logic mà Spring cần phân giải; `ModelAndView` là đối tượng có thể mang cả model lẫn thông tin view trong một kết quả trả về.

Khi kiểm thử bằng `MockMvc`, có thể xác nhận controller đã đưa đúng dữ liệu vào model và chọn đúng view mà không cần gửi HTTP request qua mạng. Các matcher như `model()`, `view()`, `forwardedUrl()` và `redirectedUrl()` giúp mô tả rõ kết quả MVC mà controller cam kết.

## 1. Model trong Spring MVC

Model là tập hợp các thuộc tính (attribute) được đặt tên để view sử dụng khi tạo response. Ví dụ, một trang chi tiết sản phẩm có thể cần đối tượng sản phẩm, tiêu đề trang và danh sách danh mục:

```java
model.addAttribute("product", product);
model.addAttribute("pageTitle", "Product detail");
model.addAttribute("categories", categories);
```

Tên thuộc tính là khóa để view truy cập dữ liệu. Với JSP, dữ liệu thường được đọc qua các expression hoặc tag; với Thymeleaf, template có thể truy cập thuộc tính bằng biểu thức như `${product.name}`.

Trong controller, Spring cung cấp tham số `Model` để thêm thuộc tính:

```java
@Controller
class ProductPageController {
    @GetMapping("/products/{id}")
    String detail(@PathVariable long id, Model model) {
        Product product = new Product(id, "Notebook");
        model.addAttribute("product", product);
        model.addAttribute("pageTitle", "Product detail");
        return "products/detail";
    }
}
```

`Model` là abstraction mà controller thường nên sử dụng. Spring cũng cung cấp `ModelMap`, một kiểu map có các phương thức tiện ích để thêm thuộc tính. Cả hai đều có thể dùng làm tham số handler method:

```java
@GetMapping("/products")
String list(ModelMap model) {
    model.addAttribute("products", List.of(
            new Product(1L, "Notebook"),
            new Product(2L, "Pen")));
    return "products/list";
}
```

Không cần tự tạo model rồi truyền vào view trong trường hợp thông thường. Spring MVC chuẩn bị model cho handler và thu thập các thuộc tính mà controller thêm vào.

### Thêm và đọc thuộc tính model

Các thao tác phổ biến của `Model` gồm:

| Phương thức | Công dụng |
| --- | --- |
| `addAttribute(name, value)` | Thêm một thuộc tính với tên cụ thể |
| `addAttribute(value)` | Thêm thuộc tính và để Spring suy ra tên từ kiểu object |
| `addAllAttributes(map)` | Thêm các thuộc tính từ map |
| `mergeAttributes(map)` | Bổ sung thuộc tính mà không ghi đè khóa đã có |
| `containsAttribute(name)` | Kiểm tra một thuộc tính có tồn tại hay không |
| `asMap()` | Lấy map các thuộc tính hiện có |

Trong code ứng dụng, nên đặt tên tường minh cho những thuộc tính quan trọng của view:

```java
model.addAttribute("product", product);
```

Việc dựa vào tên tự suy ra từ class có thể tiện trong trường hợp đơn giản, nhưng tên rõ ràng làm template và test dễ đọc hơn, đồng thời tránh bất ngờ khi kiểu object hoặc quy ước đặt tên thay đổi.

## 2. View name là gì?

View name là tên logic mà controller trả về để Spring tìm thành phần render response. Ví dụ:

```java
return "products/detail";
```

Chuỗi `products/detail` thường không phải URL trình duyệt và cũng chưa chắc là đường dẫn file đầy đủ. Nó là tên được chuyển cho `ViewResolver`. View resolver dựa trên cấu hình để tìm đối tượng `View` tương ứng.

Với một `InternalResourceViewResolver` cho JSP, cấu hình có thể thêm prefix và suffix:

```java
@Bean
InternalResourceViewResolver viewResolver() {
    InternalResourceViewResolver resolver = new InternalResourceViewResolver();
    resolver.setPrefix("/WEB-INF/views/");
    resolver.setSuffix(".jsp");
    return resolver;
}
```

Khi controller trả về `products/detail`, resolver có thể ánh xạ thành `/WEB-INF/views/products/detail.jsp`. Với Thymeleaf, view name có thể được ánh xạ tới template tương ứng trong thư mục template đã cấu hình.

Điểm cần nhớ:

- Controller chọn tên view logic.
- `ViewResolver` quyết định view implementation hoặc template tương ứng.
- View nhận model và tạo nội dung response theo công nghệ render được cấu hình.
- Đường dẫn template không nhất thiết trùng với URL request.

Do đó, kiểm tra `view().name("products/detail")` xác nhận controller chọn đúng view logic. Nó không tự chứng minh file JSP/Thymeleaf tồn tại hoặc template render không lỗi.

## 3. Phân biệt `Model`, `ModelMap` và `ModelAndView`

Ba kiểu này có liên quan nhưng phục vụ cách viết handler khác nhau:

| Kiểu | Vai trò | Cách dùng thường gặp |
| --- | --- | --- |
| `Model` | Abstraction để controller thêm dữ liệu cho view | Nhận làm tham số, sau đó trả về tên view dạng `String` |
| `ModelMap` | Map các thuộc tính model với API tiện ích | Nhận làm tham số khi cần thao tác như map |
| `ModelAndView` | Gói cả thông tin view và model trong kết quả trả về | Tạo đối tượng, thêm model và trả về từ handler |

Ví dụ dùng `Model` và trả về view name:

```java
@GetMapping("/products/{id}")
String detail(@PathVariable long id, Model model) {
    model.addAttribute("product", findProduct(id));
    return "products/detail";
}
```

Ví dụ dùng `ModelAndView`:

```java
@GetMapping("/products/{id}")
ModelAndView detail(@PathVariable long id) {
    ModelAndView result = new ModelAndView("products/detail");
    result.addObject("product", findProduct(id));
    return result;
}
```

Hai cách trên có thể biểu đạt cùng một kết quả MVC. Dùng `Model` thường đơn giản khi view name là một chuỗi được trả về từ handler. `ModelAndView` hữu ích khi muốn xây dựng hoặc chuyển tiếp một kết quả đã chứa cả view lẫn model, hoặc khi API của một thành phần đang làm việc trực tiếp với đối tượng này.

## 4. Tạo và sử dụng `ModelAndView`

`ModelAndView` là lớp thuộc `org.springframework.web.servlet`. Nó giữ thông tin view và các thuộc tính model. Có thể khởi tạo theo nhiều cách:

```java
ModelAndView first = new ModelAndView("products/detail");

ModelAndView second = new ModelAndView(
        "products/detail", "product", product);

ModelAndView third = new ModelAndView(
        "products/detail", Map.of("product", product));
```

Các thao tác thường dùng:

| Phương thức | Công dụng |
| --- | --- |
| `setViewName(name)` | Đặt tên view logic |
| `getViewName()` | Lấy tên view logic nếu đã đặt theo tên |
| `setView(view)` | Đặt trực tiếp một đối tượng `View` |
| `getView()` | Lấy đối tượng `View` nếu có |
| `addObject(name, value)` | Thêm thuộc tính vào model |
| `addAllObjects(map)` | Thêm nhiều thuộc tính |
| `getModel()` | Lấy model dưới dạng `Map` |
| `getModelMap()` | Lấy model dưới dạng `ModelMap` |
| `hasView()` | Kiểm tra đã có view name hoặc view instance hay chưa |
| `isReference()` | Kiểm tra view đang được biểu diễn bằng tên tham chiếu hay một `View` instance |

Ví dụ đầy đủ:

```java
@GetMapping("/products")
ModelAndView list() {
    ModelAndView result = new ModelAndView();
    result.setViewName("products/list");
    result.addObject("pageTitle", "Product catalog");
    result.addObject("products", productService.findAll());
    return result;
}
```

Có thể đặt trực tiếp một `View` instance thay cho view name. Khi đó Spring không cần phân giải tên view theo cùng cách:

```java
ModelAndView result = new ModelAndView(viewInstance);
result.addObject("product", product);
return result;
```

Đây là cách ít phổ biến hơn trong controller thông thường, nhưng có thể hữu ích khi view đã được tạo hoặc lựa chọn bởi một thành phần khác.

## 5. Khi nào một giá trị trả về được xem là view name?

Ngữ nghĩa của kiểu trả về phụ thuộc vào annotation và cách Spring MVC xử lý handler method.

| Controller/kiểu trả về | Ý nghĩa thường gặp |
| --- | --- |
| `@Controller` trả `String` | Tên view logic |
| `@Controller` nhận `Model`, trả `String` | Tên view logic; model được dùng cho view |
| `@Controller` trả `ModelAndView` | View cùng model |
| `@ResponseBody` trả object hoặc `String` | Dữ liệu response body, không phải view name |
| `@RestController` trả object hoặc `String` | Response body vì `@RestController` bao gồm `@ResponseBody` |
| Trả `ResponseEntity<T>` | HTTP status, headers và body |

Ví dụ khác biệt giữa MVC view và REST response:

```java
@Controller
class PageController {
    @GetMapping("/welcome")
    String welcome(Model model) {
        model.addAttribute("message", "Welcome");
        return "welcome";
    }
}

@RestController
class ApiController {
    @GetMapping("/api/welcome")
    String welcome() {
        return "Welcome";
    }
}
```

Ở controller đầu, `welcome` là view name. Ở controller thứ hai, chuỗi `Welcome` được ghi vào response body. Không nên dùng matcher `view().name(...)` cho endpoint REST trả JSON hoặc text body; hãy dùng matcher body như `content()` hoặc `jsonPath()`.

Các kiểu trả về khác như `void`, `null`, `Map`, `@ModelAttribute` hoặc `View` có quy tắc xử lý riêng và có thể phụ thuộc vào cấu hình mặc định. Khi muốn contract rõ ràng, hãy trả về view name hoặc `ModelAndView` một cách tường minh cho trang MVC; với REST endpoint, hãy khai báo rõ `@ResponseBody` hoặc dùng `@RestController`.

## 6. Đưa dữ liệu vào model bằng `@ModelAttribute`

`@ModelAttribute` có thể dùng trên phương thức để thêm dữ liệu chung vào model trước khi handler được gọi:

```java
@Controller
class ProductPageController {
    @ModelAttribute("pageTitle")
    String pageTitle() {
        return "Product catalog";
    }

    @GetMapping("/products")
    String list(Model model) {
        model.addAttribute("products", productService.findAll());
        return "products/list";
    }
}
```

Thuộc tính `pageTitle` có thể xuất hiện trong model của các handler phù hợp trong controller. Điều này tiện cho dữ liệu dùng chung như thông tin menu hoặc tiêu đề. Không nên đặt logic truy cập dịch vụ nặng vào phương thức `@ModelAttribute` nếu mọi request không cần dữ liệu đó.

`@ModelAttribute` trên tham số cũng có thể bind request parameters vào một object form:

```java
@PostMapping("/products/search")
String search(@ModelAttribute ProductSearchForm form, Model model) {
    model.addAttribute("products", productService.search(form));
    return "products/list";
}
```

Nếu form có validation, có thể dùng `@Valid` và `BindingResult` ngay sau tham số được validate:

```java
@PostMapping("/products")
String create(@Valid @ModelAttribute("form") ProductForm form,
              BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "products/new";
    }
    productService.create(form);
    return "redirect:/products";
}
```

Khi có lỗi validation, model thường chứa form object và binding result tương ứng. Test có thể kiểm tra view trả về, thuộc tính form và lỗi field bằng các matcher của `model()`.

## 7. View name, redirect và forward

Ngoài view name thông thường, Spring MVC hỗ trợ các prefix đặc biệt để yêu cầu redirect hoặc forward:

```java
return "redirect:/products";
```

`redirect:` tạo redirect response tới URL đích. Trình duyệt hoặc HTTP client có thể gửi request tiếp theo đến URL đó. Đây thường là cách triển khai Post/Redirect/Get để tránh gửi lại form khi người dùng refresh trang.

```java
return "forward:/products";
```

`forward:` yêu cầu servlet forward nội bộ đến đường dẫn đích trong cùng server request. Forward không tạo một redirect HTTP mới và URL phía client không nhất thiết thay đổi.

| Kết quả | Hành vi | Matcher MockMvc |
| --- | --- | --- |
| View thông thường | Chọn view để render | `view().name("products/list")` |
| Redirect | Response chuyển hướng tới URL khác | `redirectedUrl("/products")` |
| Forward | Servlet chuyển tiếp request nội bộ | `forwardedUrl("/products")` |

Không nên nhầm view name với URL. `products/detail` có thể là tên view logic được resolver ánh xạ thành file template; `redirect:/products` là chỉ thị chuyển hướng tới URL; `forward:/products` là chỉ thị forward nội bộ.

## 8. RedirectAttributes và flash attributes

Khi redirect sau khi xử lý form, có thể cần mang một thông báo sang request kế tiếp. `RedirectAttributes` hỗ trợ hai loại dữ liệu:

- `addAttribute(name, value)` thêm thuộc tính có thể được đưa vào URL redirect, thường dưới dạng path variable hoặc query parameter.
- `addFlashAttribute(name, value)` lưu dữ liệu flash để request kế tiếp đọc được; dữ liệu flash thường được giữ qua session trong thời gian chuyển tiếp và sau đó được tiêu thụ.

Ví dụ:

```java
@PostMapping("/products")
String create(@RequestParam String name, RedirectAttributes attributes) {
    productService.create(name);
    attributes.addAttribute("source", "form");
    attributes.addFlashAttribute("notice", "Product created");
    return "redirect:/products";
}
```

URL redirect có thể mang query parameter `source=form`; thông báo `notice` được gửi như flash attribute cho request tiếp theo. Không nên đặt dữ liệu nhạy cảm hoặc object lớn vào query parameter vì URL có thể xuất hiện trong browser history, access log và referrer.

Trong MockMvc, có thể kiểm tra redirect URL và flash attribute ngay trên kết quả của request POST:

```java
mockMvc.perform(post("/products").param("name", "Notebook"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/products?source=form"))
        .andExpect(flash().attribute("notice", "Product created"));
```

Nếu test cần kiểm tra cả request GET tiếp theo, có thể lấy flash attributes từ kết quả POST và gắn chúng vào request kế tiếp bằng `.flashAttrs(...)`. Điều này giúp xác nhận trang đích nhận được thông báo sau redirect.

## 9. Kiểm thử model và view bằng MockMvc

Spring Test cung cấp matcher trong `MockMvcResultMatchers` để kiểm tra model và view. Ví dụ sau dùng `standaloneSetup` để tập trung vào hành vi của controller:

```java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.servlet.ModelAndView;

import java.util.List;

record Product(long id, String name) {
}

@Controller
class CatalogPageController {
    @GetMapping("/catalog/products/{id}")
    String detail(@PathVariable long id, Model model) {
        model.addAttribute("product", new Product(id, "Notebook"));
        model.addAttribute("pageTitle", "Product detail");
        return "catalog/detail";
    }

    @GetMapping("/catalog/products")
    ModelAndView list() {
        ModelAndView result = new ModelAndView("catalog/list");
        result.addObject("products", List.of(
                new Product(1L, "Notebook"),
                new Product(2L, "Pen")));
        return result;
    }
}
```

Test kiểm tra handler dùng `Model`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

class CatalogPageControllerTest {
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new CatalogPageController())
                .build();
    }

    @Test
    void returnsDetailViewWithProductInModel() throws Exception {
        mockMvc.perform(get("/catalog/products/{id}", 7))
                .andExpect(status().isOk())
                .andExpect(view().name("catalog/detail"))
                .andExpect(model().attributeExists("product"))
                .andExpect(model().attribute("product", new Product(7, "Notebook")))
                .andExpect(model().attribute("pageTitle", "Product detail"));
    }
}
```

Test kiểm tra handler trả `ModelAndView`:

```java
@Test
void returnsListViewWithProductsInModel() throws Exception {
    mockMvc.perform(get("/catalog/products"))
            .andExpect(status().isOk())
            .andExpect(view().name("catalog/list"))
            .andExpect(model().attributeExists("products"))
            .andExpect(model().attribute("products", List.of(
                    new Product(1L, "Notebook"),
                    new Product(2L, "Pen"))));
}
```

Hai test trên xác nhận kết quả xử lý ở tầng Spring MVC. `standaloneSetup` không cần nạp toàn bộ application context, phù hợp với controller đơn giản. Nếu mục tiêu là kiểm tra cấu hình view resolver, interceptor, controller advice hoặc các bean MVC thật, nên dùng `webAppContextSetup(webApplicationContext)` hoặc `@WebMvcTest`/`@SpringBootTest` theo phạm vi cần kiểm tra.

## 10. Các matcher model và view thường dùng

`model()` trả về các matcher để kiểm tra model được tạo trong quá trình xử lý request:

| Matcher | Công dụng |
| --- | --- |
| `model().attributeExists("product")` | Kiểm tra thuộc tính tồn tại |
| `model().attributeDoesNotExist("error")` | Kiểm tra thuộc tính không tồn tại |
| `model().attribute("pageTitle", "Products")` | Kiểm tra giá trị thuộc tính |
| `model().attributeHasErrors("form")` | Kiểm tra object có lỗi binding/validation |
| `model().attributeHasNoErrors("form")` | Kiểm tra object không có lỗi |
| `model().attributeErrorCount("form", 2)` | Kiểm tra tổng số lỗi |
| `model().attributeHasFieldErrors("form", "name")` | Kiểm tra field có lỗi |
| `model().size(3)` | Kiểm tra số lượng thuộc tính model |

`view()` dùng để kiểm tra view đã được chọn:

```java
mockMvc.perform(get("/catalog/products"))
        .andExpect(view().name("catalog/list"));
```

Nếu controller dùng redirect hoặc forward, hãy dùng matcher tương ứng:

```java
mockMvc.perform(post("/catalog/products").param("name", "Pen"))
        .andExpect(redirectedUrl("/catalog/products"));

mockMvc.perform(get("/catalog/legacy-products"))
        .andExpect(forwardedUrl("/catalog/products"));
```

Tên matcher được import tĩnh từ `MockMvcResultMatchers`. Dùng matcher theo đúng loại kết quả giúp test mô tả ý định rõ ràng hơn việc chỉ kiểm tra response body.

## 11. Kiểm tra ModelAndView trực tiếp qua MvcResult

Trong một số trường hợp cần kiểm tra nhiều thuộc tính hoặc đọc metadata của `ModelAndView`, có thể lấy `MvcResult` từ `andReturn()`:

```java
MvcResult result = mockMvc.perform(get("/catalog/products"))
        .andExpect(status().isOk())
        .andReturn();

ModelAndView modelAndView = result.getModelAndView();

assertThat(modelAndView).isNotNull();
assertThat(modelAndView.getViewName()).isEqualTo("catalog/list");
assertThat(modelAndView.getModel()).containsKey("products");
```

`MvcResult.getModelAndView()` có thể là `null` đối với request không tạo kết quả view/model, chẳng hạn endpoint REST trả response body. Vì vậy, chỉ sử dụng API này khi test đang kiểm tra luồng MVC view. Với REST endpoint, dùng `getResponse()` và các matcher body/header/status phù hợp.

Thông thường, `view()` và `model()` matcher là lựa chọn ngắn gọn và dễ đọc. `MvcResult` phù hợp khi cần thực hiện logic assertion phức tạp hoặc chuyển kết quả cho một bước kiểm tra khác.

## 12. Kiểm tra lỗi validation trong model

Với form MVC, controller có thể trả lại cùng view khi dữ liệu không hợp lệ. Test cần xác nhận cả view name, object form và lỗi validation:

```java
@PostMapping("/catalog/products")
String save(@Valid @ModelAttribute("form") ProductForm form,
            BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "catalog/new";
    }
    return "redirect:/catalog/products";
}
```

Ví dụ kiểm tra:

```java
mockMvc.perform(post("/catalog/products")
                .param("name", "")
                .param("price", "-1"))
        .andExpect(status().isOk())
        .andExpect(view().name("catalog/new"))
        .andExpect(model().attributeExists("form"))
        .andExpect(model().attributeHasErrors("form"))
        .andExpect(model().attributeHasFieldErrors("form", "name"));
```

Để test hoạt động, `ProductForm` cần khai báo constraint phù hợp như `@NotBlank` hoặc `@Positive`, và validation provider cần có trong test runtime. Tham số `BindingResult` phải đứng ngay sau object được validate để controller có thể xử lý lỗi binding/validation. Nếu không có `BindingResult` tại vị trí phù hợp, exception có thể được chuyển cho exception resolver thay vì đi vào nhánh xử lý lỗi của controller.

## 13. Kiểm tra view name không đồng nghĩa render template

`MockMvc` có thể xác nhận controller chọn đúng view name và cung cấp model tương ứng. Tuy nhiên, mức độ kiểm tra template phụ thuộc vào view technology và cấu hình được nạp.

- Với `standaloneSetup`, test thường tập trung vào handler, model và logical view name. Nếu không cấu hình view resolver hoặc view implementation, test không xác nhận được template thực tế.
- Với `webAppContextSetup`, view resolver và các bean view đã được nạp trong context có thể tham gia xử lý response.
- JSP thường cần servlet container có khả năng biên dịch và thực thi JSP; `MockServletContext` không thay thế hoàn toàn môi trường triển khai JSP.
- Thymeleaf hoặc template engine khác có thể render trong test nếu dependency, template resolver và cấu hình tương ứng được nạp.

Nếu mục tiêu chỉ là xác nhận controller trả về `catalog/detail` cùng `product`, matcher `view()` và `model()` thường là đủ. Nếu mục tiêu là xác nhận HTML cuối cùng, hãy cấu hình template engine trong test hoặc chạy integration test phù hợp với môi trường render thực tế.

## 14. Lỗi thường gặp khi kiểm thử model và view

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| `view().name(...)` không khớp | Controller trả tên view khác hoặc đang dùng redirect/forward | Xác định chính xác kiểu kết quả handler trả về và dùng matcher phù hợp |
| `model().attributeExists(...)` thất bại | Controller chưa thêm thuộc tính hoặc tên attribute sai | Kiểm tra `addAttribute` và tên được view sử dụng |
| `getModelAndView()` trả `null` | Handler trả response body hoặc response không dùng view | Dùng matcher body/header/status cho REST endpoint |
| Test view name qua nhưng trang không hiển thị | Template không tồn tại hoặc view resolver chưa cấu hình | Kiểm tra template path và cấu hình resolver; thêm test render khi cần |
| Chuỗi trả về bị xem là response body | Handler dùng `@ResponseBody` hoặc `@RestController` | Dùng `@Controller` cho view hoặc kiểm tra body theo đúng ý định |
| Flash attribute không xuất hiện trong model của request POST | Flash attribute được chuyển sang request kế tiếp | Kiểm tra `flash()` hoặc thực hiện request redirect tiếp theo với flash map |
| Test redirect mong đợi forward | Nhầm prefix `redirect:` với `forward:` | Dùng `redirectedUrl` hoặc `forwardedUrl` đúng với hành vi |
| Lỗi validation không nằm trong model | Thiếu constraint, validation provider hoặc `BindingResult` đúng vị trí | Kiểm tra `@Valid`, dependency validation và thứ tự tham số |
| Model có thêm thuộc tính ngoài dự kiến | `@ModelAttribute` method hoặc binding tự thêm thuộc tính | Kiểm tra toàn bộ controller advice/model initialization trước khi assert size chính xác |

## 15. Nguyên tắc viết test xác nhận kết quả MVC

1. Dùng `Model` khi handler cần thêm dữ liệu và trả về view name dạng `String`.
2. Dùng `ModelAndView` khi muốn gói view cùng model trong một giá trị trả về.
3. Đặt tên model attribute rõ ràng và kiểm tra đúng tên đó trong test.
4. Phân biệt view name logic với đường dẫn template và URL của trình duyệt.
5. Dùng `view().name(...)` cho view thông thường, `redirectedUrl(...)` cho redirect và `forwardedUrl(...)` cho forward.
6. Dùng `model()` để xác nhận dữ liệu, form object và validation errors mà controller cung cấp cho view.
7. Không dùng matcher view/model cho endpoint REST trả body; hãy kiểm tra status, header và body.
8. Dùng `webAppContextSetup` hoặc test context phù hợp khi cần xác nhận cấu hình MVC thực tế; dùng test render riêng khi cần xác nhận HTML cuối cùng.

Model, view name và `ModelAndView` tạo thành kết quả quan trọng của controller trong ứng dụng Spring MVC dạng server-rendered. Khi test xác nhận cả view logic lẫn các model attribute cần thiết, lỗi chọn nhầm trang hoặc thiếu dữ liệu sẽ được phát hiện ngay tại tầng MVC. Việc tách kiểm tra controller result khỏi kiểm tra render template cũng giúp xác định rõ test đang bảo vệ phần hành vi nào của ứng dụng.
