# @ModelAttribute và gắn dữ liệu form hoặc query vào đối tượng trong Spring MVC

Trong Spring MVC, người dùng có thể gửi dữ liệu từ URL query string hoặc biểu mẫu HTML dưới dạng các cặp tên–giá trị. Thay vì đọc từng tham số bằng `@RequestParam` rồi tự gán vào object, controller có thể khai báo **`@ModelAttribute` trên một tham số kiểu đối tượng**. Spring tìm hoặc tạo đối tượng đó, dùng `WebDataBinder` chuyển dữ liệu từ request thành các thuộc tính/constructor arguments của đối tượng, ghi nhận lỗi binding, rồi chuyển object vào handler.

Ví dụ request:

~~~http
GET /catalog/search?term=spring&page=2&sort=recent HTTP/1.1
Host: localhost:8080
~~~

và controller:

~~~java
@GetMapping("/search")
public String search(@ModelAttribute("filter") SearchForm form) {
    return form.getTerm() + " - page " + form.getPage();
}
~~~

với JavaBean `SearchForm` có các thuộc tính `term` và `page` tương ứng sẽ nhận `"spring"` và `2`; nếu method trả chuỗi như trên trong một `@RestController`, chuỗi được viết vào HTTP response. Đây mới chỉ là **binding**: nếu muốn kiểm tra điều kiện như không rỗng hoặc page lớn hơn 0, cần thêm validation riêng.

Bài học tập trung vào **`@ModelAttribute` như tham số của handler Spring MVC** trong Spring Framework 6.x / Spring Boot 3.x, Java 17+. Cuối bài có một ví dụ chạy được với GET query, POST form, chuyển kiểu, Bean Validation, `BindingResult` và giới hạn trường cho phép bind.

## 1. `@ModelAttribute` giải quyết vấn đề gì?

Một form thường gửi nhiều trường:

~~~text
term=spring
page=3
sort=recent
~~~

Có hai cách nhận dữ liệu:

~~~java
// Cách đọc từng field riêng lẻ:
@GetMapping("/search")
public String search(
        @RequestParam String term,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "relevance") String sort) {
    return term + " / " + page + " / " + sort;
}
~~~

~~~java
// Cách gom các field thành đối tượng:
@GetMapping("/search")
public String search(@ModelAttribute SearchForm form) {
    return form.getTerm() + " / "
        + form.getPage() + " / "
        + form.getSort();
}
~~~

Hai đoạn chỉ minh họa chữ ký handler, cần imports/controller và định nghĩa `SearchForm` ở phần ví dụ hoàn chỉnh. `@ModelAttribute` đặc biệt hữu ích khi form có nhiều trường, cần tái sử dụng một DTO ở các handler, có nested property, cần validation tổng thể hoặc cần giữ object trong model để hiển thị lại HTML.

Điều cần nhớ:

- `@ModelAttribute` trên **tham số handler** nhận dữ liệu từ request vào một model object.
- `@ModelAttribute` trên **method của controller** thường dùng để tạo hoặc bổ sung thuộc tính cho model trước khi handler chạy; đây là công dụng khác, giải thích ở phần 8.
- `@ModelAttribute` không mặc nhiên đọc JSON body theo Jackson; JSON body thường dùng `@RequestBody`.
- Việc một object được bind thành công chưa khẳng định nó hợp lệ về nghiệp vụ hay đã được lưu vào database.

## 2. Dữ liệu đầu vào đến từ đâu?

Đối với Spring MVC chạy trên Servlet stack, **request parameters** bao gồm:

1. **Query string**: `GET /catalog/search?term=java&page=2`.
2. **Dữ liệu form URL-encoded**: các cặp tên–giá trị trong body `application/x-www-form-urlencoded` của POST.
3. **Các nguồn bổ sung của MVC**: URI path variables và request headers cũng có thể tham gia bind theo tên khi không bị request parameter cùng tên ưu tiên; tên header có dấu gạch nối được xử lý theo quy tắc binder.

Ví dụ GET và POST có thể đi vào **cùng một DTO**:

~~~http
GET /catalog/search?term=java&page=2 HTTP/1.1
Host: localhost:8080
~~~

~~~http
POST /catalog/submit HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded

term=java&page=2
~~~

Nếu DTO có `term` là `String` và `page` là `Integer`, Spring lấy chuỗi `"java"`, `"2"` rồi chuyển `"2"` thành số nguyên `2` theo ConversionService. Với `@ModelAttribute("filter")`, tên `filter` là **tên model attribute**; request vẫn có key `term`, `page`, không nhất thiết phải viết `filter.term` và `filter.page`.

**Lưu ý nguồn dữ liệu:** Có thể bind query parameter trong nhiều HTTP method, kể cả một POST có cả query và form body. Nếu cùng một key xuất hiện từ nhiều nguồn, cần kiểm tra ngữ nghĩa Servlet parameter map và binder; đừng thiết kế hợp đồng dựa trên giả định có một quy tắc ghép tùy ý. Với API JSON, dùng `@RequestBody`/`HttpMessageConverter` đúng mục đích.

### Bảng chọn annotation

| Mục tiêu | Annotation/phương thức phù hợp |
|---|---|
| Một giá trị từ query/form | `@RequestParam("page") int page` |
| Nhiều field cùng xây một object từ query/form | `@ModelAttribute SearchForm form` |
| ID nằm trên đường dẫn `/orders/{id}` | `@PathVariable Long id` |
| Header cụ thể | `@RequestHeader("X-Request-Id") String id` |
| JSON body chuyển thành DTO | `@RequestBody CreateOrderRequest request` |
| Một part trong multipart body | `@RequestPart`, hoặc `MultipartFile` phù hợp |
| Truy cập object đã có trong model và bind thêm giá trị | `@ModelAttribute("name") SomeType value` |
| Truy cập object model **không bind thêm request** | `@ModelAttribute(binding = false)` |

`@ModelAttribute` cũng dùng được trong xử lý multipart/form-data với cấu hình multipart phù hợp, ví dụ DTO có `MultipartFile`; nó không tự chuyển mọi MIME type thành form fields.

## 3. Luồng giải quyết tham số và gắn dữ liệu

Khi Spring MVC tìm được một handler, cơ chế argument resolution phải tạo đối số để gọi method. Với `@ModelAttribute`, trình tự khái quát:

~~~text
HTTP request
     |
     v
DispatcherServlet -> HandlerMapping -> HandlerAdapter
                                      |
                                      v
                          ModelAttribute argument resolver
                                      |
                      tìm đối tượng đã có trong Model
                      hoặc tạo đối tượng phù hợp
                                      |
                                      v
                                WebDataBinder
                      +-------------------------------+
                      | lấy request parameter values  |
                      | constructor/property binding  |
                      | chuyển String -> Java type    |
                      | ghi nhận binding errors       |
                      +-------------------------------+
                                      |
                         @Valid / @Validated nếu có
                                      |
                            BindingResult / exception
                                      |
                                      v
                            gọi controller method
~~~

Bốn cơ chế phối hợp nhưng khác trách nhiệm:

- **Argument resolver:** quyết định cách tạo/nhận model attribute và tham số method.
- **`WebDataBinder`:** thực hiện binding và type conversion, theo các thuộc tính/field được phép.
- **Validation:** nếu có `@Valid`/`@Validated` và validator, kiểm tra constraint của đối tượng sau khi binding.
- **`BindingResult`:** chứa binding/validation errors của **đúng đối tượng** và phải đứng ngay sau model attribute cần xử lý lỗi.

Một model attribute có thể đến từ object đã được chuẩn bị trong model, từ session theo `@SessionAttributes`, từ converter phù hợp hoặc được Spring tạo qua constructor. Vì vậy không phải mọi lần `@ModelAttribute` đều có nghĩa là `new DTO()`.

## 4. Spring khởi tạo đối tượng bằng cách nào?

### 4.1. Constructor + setter/property binding

Với JavaBean có constructor rỗng và setters:

~~~java
public class SearchForm {
    private String term;
    private Integer page = 1;

    public SearchForm() {
    }

    public String getTerm() {
        return term;
    }

    public void setTerm(String term) {
        this.term = term;
    }

    public Integer getPage() {
        return page;
    }

    public void setPage(Integer page) {
        this.page = page;
    }
}
~~~

Spring có thể tạo `SearchForm` bằng constructor không tham số và gọi các setters cho request fields có tên phù hợp. Khi không có `page` trong request, giá trị mặc định `1` được giữ lại trong ví dụ. Nếu request có `page=5`, binder chuyển sang `Integer(5)` và gọi `setPage(5)`.

**Không tự giả định tên Java field phải trùng mọi request key bất kể cấu hình.** Với property binding, cần writable property phù hợp (setter theo JavaBeans, trừ khi đã cấu hình cơ chế direct field binding). Một field `private` không có setter không tự được property binder ghi vào chỉ vì có tên trùng.

### 4.2. Constructor binding, record và object bất biến

Spring MVC hiện đại còn hỗ trợ **constructor binding**. Với một DTO bất biến:

~~~java
public record SearchQuery(String term, Integer page) {
}
~~~

handler có thể viết:

~~~java
@GetMapping("/search-record")
public SearchQuery search(
        @ModelAttribute SearchQuery query) {
    return query;
}
~~~

Đây là đoạn handler minh họa cần đặt trong `@RestController`; `SearchQuery` là record riêng. Spring dùng canonical/primary constructor và map request arguments theo tên phù hợp. Đảm bảo metadata tên tham số được giữ lúc biên dịch, thường nhờ cấu hình `-parameters` của build tool khi dùng constructor class thông thường; record cũng có thông tin thành phần canonical. Không cần tạo setters cho record.

Từ Spring Framework 6.1, `@BindParam` giúp ánh xạ tên request khi khác tên constructor argument:

~~~java
public final class SearchCriteria {
    private final String term;

    public SearchCriteria(
            @org.springframework.web.bind.annotation.BindParam("q")
            String term) {
        this.term = term;
    }

    public String getTerm() {
        return term;
    }
}
~~~

Với constructor binding, request `?q=spring` có thể cấp giá trị cho `term`. Đây là ví dụ **một class riêng**, không thuộc demo chính phía dưới. `@BindParam` là annotation của Spring MVC dành cho constructor binding, không thay thế `@RequestParam` trên handler.

**Mặc định Spring cho phép cả constructor binding và property binding** đối với model object phù hợp. Nếu muốn chặn mọi property binding và chỉ dùng constructor, có thể đặt `WebDataBinder.setDeclarativeBinding(true)`; chi tiết bảo mật ở phần 9.

### 4.3. Lấy object đã tồn tại trong model

Một `@ModelAttribute` ở cấp method có thể tạo DTO trước:

~~~java
@ModelAttribute("filter")
public SearchForm createForm() {
    return new SearchForm();
}
~~~

Sau đó handler nhận:

~~~java
@GetMapping("/search")
public String search(@ModelAttribute("filter") SearchForm form) {
    return form.getTerm();
}
~~~

Hai snippet này là ví dụ riêng trong một `@Controller`, không copy thêm vào demo chính nếu không cần. Spring lấy object tên `filter` từ model rồi bind request vào nó. Với ứng dụng server-rendered, object cũng có thể được đưa ra view để hiện lại giá trị người dùng nhập khi có lỗi.

Điều đó **không** có nghĩa dữ liệu cũ trong object luôn được bảo toàn: các trường được request bind sẽ ghi đè; binding trên domain entity có thể nguy hiểm nếu vô tình expose thuộc tính nhạy cảm.

## 5. Ví dụ Spring Boot hoàn chỉnh: GET query và POST form cùng một DTO

Bộ ví dụ gồm ba file trong package `com.example.binding`, sử dụng **Java 17+**, Spring Boot 3.x, Spring MVC Servlet stack và Jakarta Validation. Đây là ứng dụng có thể chạy trong một project Spring Boot hợp lệ, không phải một chương trình JDK thuần chỉ cần `javac`.

### 5.1. Gradle dependencies

Trong project đã có Spring Boot Gradle plugin và dependency version management, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

`spring-boot-starter-web` cung cấp Spring MVC và web server nhúng; `spring-boot-starter-validation` cung cấp integration Jakarta Validation và provider thích hợp. Nếu dùng Spring Boot 3, import `jakarta.validation.*` thay vì trộn `javax.validation.*` của ứng dụng cũ.

### 5.2. DTO nhận input — `SearchForm.java`

Đường dẫn:

`src/main/java/com/example/binding/SearchForm.java`

~~~java
package com.example.binding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SearchForm {

    @NotBlank
    private String term;

    @NotNull
    @Min(1)
    private Integer page = 1;

    private String sort = "relevance";

    public SearchForm() {
    }

    public String getTerm() {
        return term;
    }

    public void setTerm(String term) {
        this.term = term;
    }

    public Integer getPage() {
        return page;
    }

    public void setPage(Integer page) {
        this.page = page;
    }

    public String getSort() {
        return sort;
    }

    public void setSort(String sort) {
        this.sort = sort;
    }
}
~~~

**Giải thích mapping:**

- `term=java` → gọi `setTerm("java")`.
- `page=2` → chuyển chuỗi `"2"` thành `Integer 2` rồi gọi `setPage(2)`.
- Không gửi `page` → giữ mặc định `1` trong JavaBean mới.
- Không gửi `sort` → giữ mặc định `"relevance"`.
- `@NotBlank`, `@NotNull` và `@Min(1)` chỉ thực thi khi validator được gọi, chẳng hạn nhờ `@Valid` trên handler parameter.

DTO này được thiết kế **riêng cho dữ liệu từ request**. Nó không có trường quyền truy cập, định danh nội bộ hoặc cờ quản trị.

### 5.3. Controller — `SearchController.java`

Đường dẫn:

`src/main/java/com/example/binding/SearchController.java`

~~~java
package com.example.binding;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/catalog")
public class SearchController {

    @InitBinder("filter")
    public void configureFilterBinder(WebDataBinder binder) {
        binder.setAllowedFields("term", "page", "sort");
    }

    @GetMapping("/search")
    public ResponseEntity<SearchResult> search(
            @Valid @ModelAttribute("filter") SearchForm form,
            BindingResult errors) {
        return makeResult(form, errors);
    }

    @PostMapping(
        path = "/submit",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<SearchResult> submit(
            @Valid @ModelAttribute("filter") SearchForm form,
            BindingResult errors) {
        return makeResult(form, errors);
    }

    private ResponseEntity<SearchResult> makeResult(
            SearchForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            SearchResult invalid = new SearchResult(
                false, null, null, null, errors.getErrorCount());
            return ResponseEntity.badRequest().body(invalid);
        }

        SearchResult valid = new SearchResult(
            true, form.getTerm(), form.getPage(), form.getSort(), 0);
        return ResponseEntity.ok(valid);
    }

    public record SearchResult(
        boolean valid,
        String term,
        Integer page,
        String sort,
        int errorCount
    ) {
    }
}
~~~

Có năm điểm then chốt:

1. `@GetMapping("/search")` và `@PostMapping("/submit")` nhận **cùng kiểu `SearchForm`**, dù nguồn dữ liệu là query hay form body.
2. `@ModelAttribute("filter")` gắn tên cho object trong model; bản thân các request fields vẫn tên `term`, `page`, `sort`.
3. `@InitBinder("filter")` giới hạn **property binding** của attribute này vào đúng ba trường. Nó không đổi format, không tự validate và không loại bỏ nhu cầu dùng DTO an toàn.
4. `@Valid` yêu cầu Bean Validation sau binding. `BindingResult errors` đặt **ngay sau** `SearchForm form` để handler có thể đọc lỗi.
5. Khi có lỗi, controller trả HTTP 400 với số lỗi. Khi dữ liệu hợp lệ, trả HTTP 200 với DTO kết quả JSON. Dùng `@RestController` để tập trung vào cơ chế binding, không cần template engine.

Tại sao đặt `BindingResult` ngay sau `@ModelAttribute`? Vì Spring liên kết kết quả binding/validation với từng object argument theo vị trí. Nếu chen tham số khác ở giữa, việc xử lý lỗi không còn tuân đúng hợp đồng đối số của handler.

### 5.4. Application entry point — `BindingDemoApplication.java`

Đường dẫn:

`src/main/java/com/example/binding/BindingDemoApplication.java`

~~~java
package com.example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindingDemoApplication.class, args);
    }
}
~~~

Các file nằm cùng package, nên Spring Boot component scanning từ package chính nhận ra `SearchController`.

### 5.5. Chạy và thử bằng HTTP

Tại thư mục project Gradle có wrapper và Spring Boot plugin:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Gọi GET với query:

~~~bash
curl -i "http://localhost:8080/catalog/search?term=java&page=2&sort=recent"
~~~

Kỳ vọng **HTTP 200**, response JSON có các giá trị (thứ tự key trong JSON không phải hợp đồng):

~~~json
{
  "valid": true,
  "term": "java",
  "page": 2,
  "sort": "recent",
  "errorCount": 0
}
~~~

Gọi POST với form URL-encoded:

~~~bash
curl -i -X POST "http://localhost:8080/catalog/submit" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "term=spring" \
  --data-urlencode "page=3"
~~~

Kỳ vọng **HTTP 200** với JSON có `term="spring"`, `page=3`, `sort="relevance"` và `errorCount=0`. Thuộc tính `sort` không được gửi nên JavaBean giữ giá trị mặc định.

Dữ liệu vi phạm constraints:

~~~bash
curl -i "http://localhost:8080/catalog/search?term=%20%20&page=0"
~~~

Kỳ vọng **HTTP 400** với:

~~~json
{
  "valid": false,
  "term": null,
  "page": null,
  "sort": null,
  "errorCount": 2
}
~~~

`term` chỉ chứa khoảng trắng, vi phạm `@NotBlank`; `page=0` vi phạm `@Min(1)`. `@NotNull` vẫn đạt vì giá trị là số `0`, nên có đúng hai lỗi. Kết quả chỉ biểu diễn **số lỗi**, không phụ thuộc thứ tự thông báo đã nội suy.

Nếu request là `page=abc`, binder không chuyển được chuỗi thành `Integer`, nên có **binding/type mismatch error**. `BindingResult` giúp controller xử lý lỗi đó mà không cần để ứng dụng ném exception chưa xử lý. Số lỗi cụ thể trong các trường hợp phối hợp type mismatch với constraint khác phụ thuộc dữ liệu và cách bind; không nên suy đoán giá trị của trường đã convert thất bại.

### 5.6. Form HTML tương ứng

Một browser có thể gửi form như sau:

~~~html
<form action="/catalog/submit" method="post">
  <label>
    Từ khóa:
    <input type="text" name="term" required>
  </label>

  <label>
    Trang:
    <input type="number" name="page" min="1" value="1">
  </label>

  <label>
    Sắp xếp:
    <select name="sort">
      <option value="relevance">Liên quan</option>
      <option value="recent">Mới nhất</option>
    </select>
  </label>

  <button type="submit">Tìm kiếm</button>
</form>
~~~

Ví dụ REST controller hiện trả JSON nên browser sẽ hiển thị JSON sau khi submit. Nếu muốn hiển thị lại HTML view, dùng `@Controller` và template engine như Thymeleaf, cùng nguyên tắc binding nhưng return view name và đặt lỗi/đối tượng trong model. Thuộc tính HTML `required`/`min` chỉ hỗ trợ UX tại client; validation phải tiếp tục thực hiện trên server vì HTTP client có thể gửi request tùy ý.

## 6. `BindingResult`: lỗi chuyển kiểu khác lỗi validation

Hai nguồn lỗi thường gặp:

| Nguồn lỗi | Ví dụ | Dấu hiệu |
|---|---|---|
| **Binding/conversion** | `page=abc` nhưng `page` là `Integer` | `typeMismatch` và lỗi tương ứng trong `BindingResult` |
| **Bean Validation** | `page=0` vi phạm `@Min(1)` | Constraint violation được chuyển thành field/object errors |
| **Cả hai** | `page=abc`, `term` rỗng | Có thể có cả binding error của `page` và validation error của `term` |
| **Trường không được cho phép** | Request cố gửi một field bị allowlist từ chối | Có thể quan sát qua `getSuppressedFields()`; không tự xem nó là constraint violation |

Ví dụ xử lý lỗi chi tiết trong một controller:

~~~java
if (errors.hasErrors()) {
    for (var fieldError : errors.getFieldErrors()) {
        System.out.println(
            fieldError.getField() + ": " + fieldError.getCode());
    }
}
~~~

Đoạn trên là một **snippet bên trong handler** đã có biến `errors`, không phải một Java class độc lập. `getFieldErrors()` có thể trả lỗi cho nhiều trường; thứ tự trả về và thông điệp có thể thay đổi theo provider/locale, vì thế không nên viết test phụ thuộc chuỗi thông báo dịch sẵn.

Khi handler không khai báo `BindingResult`/`Errors` ngay sau model attribute, Spring MVC thường xử lý binding/validation thất bại bằng exception, điển hình `MethodArgumentNotValidException`. Nếu trên chính handler còn có các constraint tham số trực tiếp dẫn đến **method validation** theo Spring MVC 6.1+, loại exception có thể là `HandlerMethodValidationException`. Không gom mọi tình huống vào một loại lỗi cứng.

### `@Valid` và `@Validated` khác nhau

- `@Valid` (`jakarta.validation.Valid`) kích hoạt validation theo nhóm mặc định và hỗ trợ cascading nested bean.
- `@Validated` (`org.springframework.validation.annotation.Validated`) là annotation của Spring cho phép chọn validation group như `@Validated(Create.class)`.
- Các annotation `@NotBlank`, `@Min`, `@Size` trên DTO mới là **constraint declarations**.
- `@ModelAttribute` tự nó chủ yếu phục vụ binding; việc bind không đồng nghĩa tự kiểm tra hết constraint nếu thiếu cơ chế kích hoạt phù hợp.

Với nested DTO, có thể khai báo:

~~~java
public class AddressForm {
    @jakarta.validation.constraints.NotBlank
    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

public class CustomerForm {
    @jakarta.validation.Valid
    private AddressForm address = new AddressForm();

    public AddressForm getAddress() {
        return address;
    }

    public void setAddress(AddressForm address) {
        this.address = address;
    }
}
~~~

Đây là hai **class minh họa riêng**, đặt mỗi public class trong một file Java cùng tên. Request `address.city=Hanoi` có thể được Spring property binder gắn vào nested object `address`; `@Valid` trên field `address` cho phép provider cascade kiểm tra `AddressForm.city` khi top-level object được validate. Nếu nested object chỉ có constraint nhưng không cascade, đừng giả định validation top-level sẽ tự vào sâu.

## 7. Chuyển kiểu và định dạng dữ liệu

HTTP parameter về bản chất thường là chuỗi. `WebDataBinder` dùng `ConversionService`, converter, formatter và đôi khi các cơ chế biên tập property theo cấu hình để biến chúng thành kiểu Java phù hợp.

Các ví dụ:

| Request field | Java property | Cơ chế |
|---|---|---|
| `page=12` | `Integer page` | String → Integer |
| `active=true` | `Boolean active` | String → Boolean |
| `sort=RECENT` | `SortMode sort` (enum) | String → Enum theo tên phù hợp |
| `from=2026-11-06` | `LocalDate from` cùng `@DateTimeFormat(iso=ISO.DATE)` | Date formatter |
| `tags=java&tags=spring` | `List<String> tags` | Binding nhiều giá trị thành collection khi kiểu phù hợp |
| `address.city=Hanoi` | nested property `address.city` | Truy cập property path và object lồng |

Ví dụ LocalDate:

~~~java
@org.springframework.format.annotation.DateTimeFormat(
    iso = org.springframework.format.annotation.DateTimeFormat.ISO.DATE
)
private java.time.LocalDate from;
~~~

Đây là field minh họa cần đặt vào DTO có setter/getter hoặc constructor binding tương ứng. Khi request gửi `from=2026-11-06`, formatter được cấu hình của Spring chuyển thành `LocalDate`. Nếu dữ liệu không chuyển được, đó là binding error; đừng đợi `@NotNull` thay cho xử lý type mismatch.

Nếu muốn chuyển một chuỗi tùy chỉnh sang value object, đăng ký `Converter<String, T>` hoặc `Formatter<T>` trong ConversionService; khi bind form, Spring sẽ dùng cơ chế chuyển đổi tương ứng. Không parse dữ liệu thủ công lặp lại trong từng controller chỉ vì trường là kiểu không phải String.

### Collection và nested path

Form có thể gửi:

~~~text
items[0].name=Book
items[0].quantity=2
items[1].name=Pen
items[1].quantity=5
~~~

Binder có thể xử lý các indexed property paths khi DTO khai báo cấu trúc collection và khả năng tạo phần tử tương ứng. Constructor binding cũng hỗ trợ indexed arguments trong một số kiểu container. Các giới hạn như auto-grow collection limit và quy tắc tạo nested object cần được kiểm soát; không mặc định index bất kỳ đều được tạo an toàn. Với dữ liệu phức tạp mang nhiều nested arrays/maps, có thể nên chọn JSON `@RequestBody` để định nghĩa hợp đồng API rõ ràng hơn.

## 8. `@ModelAttribute` đặt trên method và vai trò của Spring Model

`@ModelAttribute` có nhiều vị trí sử dụng, cần phân biệt:

### 8.1. Trên tham số handler: bind object

~~~java
@PostMapping("/save")
public String save(@ModelAttribute("profile") ProfileForm form) {
    return "result";
}
~~~

Đoạn trên minh họa một handler `@Controller` trả **tên view**, không phải REST endpoint. Spring lấy/tạo attribute tên `profile` rồi bind request lên nó.

### 8.2. Trên method khởi tạo model

~~~java
@ModelAttribute("sortOptions")
public java.util.List<String> sortOptions() {
    return java.util.List.of("relevance", "recent");
}
~~~

Trong một `@Controller`, Spring thường gọi method `@ModelAttribute` loại này **trước handler `@RequestMapping`** nhằm bổ sung dữ liệu cho model. Method tương tự trong `@ControllerAdvice` có thể chia sẻ cho nhiều controller. Danh sách `sortOptions` thích hợp làm option của form; nó không có nghĩa là request tự bind vào danh sách đó.

Một method cũng có thể trả chính form object:

~~~java
@ModelAttribute("profile")
public ProfileForm loadProfile() {
    return new ProfileForm();
}
~~~

Sau đó `@ModelAttribute("profile") ProfileForm form` trong handler dùng đối tượng đã có. Khi load entity có dữ liệu thật để edit, **không** giao trực tiếp toàn bộ entity cho property binder nếu entity có các field nhạy cảm.

### 8.3. Trên handler return value

Trong HTML controller, `@ModelAttribute` trên handler method có thể yêu cầu xem return value là một thuộc tính model, thay vì tự viết HTTP response. `@RestController`/`@ResponseBody` xử lý return value thành body bằng cơ chế khác; cần xác định kiểu controller trước khi suy ra kết quả:

~~~java
@GetMapping("/profile")
@ModelAttribute("profile")
public ProfileForm profile() {
    return new ProfileForm();
}
~~~

Đây là ví dụ dùng trong `@Controller` và cần một cơ chế chọn/render view nếu muốn đưa model ra HTML. Nó không có tác dụng tương đương `@RequestBody`.

### 8.4. Khi chỉ muốn đọc model attribute, không muốn bind

Có thể dùng:

~~~java
@ModelAttribute("account")
public Account loadAccount(@PathVariable long id) {
    return accountService.findById(id);
}

@PostMapping("/account/{id}/activate")
public String activate(
        @ModelAttribute(value = "account", binding = false)
        Account account) {
    accountService.activate(account);
    return "redirect:/accounts";
}
~~~

Đây là đoạn minh họa trong controller có bean `accountService`; không phải class tự chạy. `binding = false` yêu cầu Spring **không bind các request values vào đối tượng đó**, hữu ích khi muốn handler nhận một entity vừa được load nhưng không cho HTTP form tự sửa trường của entity. Nếu thực sự muốn edit, nên nhận một DTO riêng rồi áp dụng có chủ ý những field đã được chấp thuận lên entity.

### 8.5. `@SessionAttributes` và form nhiều bước

Trong một số workflow server-rendered, class-level `@SessionAttributes("profile")` cho phép một model attribute được giữ trong HTTP session giữa những request liên quan; sau khi hoàn thành cần gọi `SessionStatus.setComplete()` để kết thúc workflow attribute đó. `@SessionAttributes` là cơ chế dành cho model/session của controller, khác với `@SessionAttribute` để đọc một thuộc tính session đã có. Đừng tự xem `@ModelAttribute` là cơ chế lưu session mặc định.

## 9. Bảo mật data binding: không bind thẳng domain entity

### 9.1. Vấn đề mass assignment / over-posting

Giả sử một entity có:

~~~java
public class Account {
    private String displayName;
    private boolean administrator;

    public void setDisplayName(String value) {
        this.displayName = value;
    }

    public void setAdministrator(boolean value) {
        this.administrator = value;
    }
}
~~~

Nếu một handler nhận thẳng `@ModelAttribute Account account` và cho phép property binding mặc định, HTTP client có thể thử gửi:

~~~text
displayName=Alice&administrator=true
~~~

Nếu field/constructor/property phù hợp và không được hạn chế, binder có thể ghi vào thuộc tính quản trị mà business logic không định cho người dùng thay đổi. **Không dùng request DTO giống hệt domain entity chỉ để tiết kiệm bước mapping.** Thiết kế DTO chỉ gồm các trường được phép nhập rồi map sang entity qua service là đường mặc định an toàn.

### 9.2. `@InitBinder` với `setAllowedFields`

Trong demo chính đã có:

~~~java
@InitBinder("filter")
public void configureFilterBinder(WebDataBinder binder) {
    binder.setAllowedFields("term", "page", "sort");
}
~~~

`allowedFields` là tập các **property paths được phép gắn bằng property binding**; đây là danh sách cho phép, hiệu quả rõ ràng hơn chỉ đặt `disallowedFields` rồi cố nhớ tất cả trường nhạy cảm. Hãy chọn danh sách nhỏ đúng với form. Việc thiết lập ở `@InitBinder("filter")` chỉ áp dụng cho model attribute có tên khớp, tránh vô tình thay đổi object khác trong controller.

Các thông tin cần phân biệt:

- `setAllowedFields` chủ yếu giới hạn **property binding**. Nó không phải biện pháp xác thực quyền người dùng hay validation của dữ liệu đã nhận.
- **Constructor binding** có quy tắc chọn constructor arguments riêng; dùng DTO chuyên biệt/constructor chỉ bao gồm input được chấp thuận để hạn chế việc request gắn dữ liệu ngoài ý muốn.
- Các field bị suppression có thể kiểm tra qua `BindingResult.getSuppressedFields()`; tùy chính sách ứng dụng, có thể coi việc cố gửi field không được phép là request đáng từ chối hoặc ghi nhận cho theo dõi.
- Đừng tin rằng không có input hiển thị trong HTML đồng nghĩa client không thể gửi key đó; client có thể tạo request thủ công.

### 9.3. `setDeclarativeBinding(true)` cho constructor-only

Spring Framework 6.1+ hỗ trợ:

~~~java
@InitBinder
public void configureBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

Khi bật `declarativeBinding`, Spring ưu tiên **constructor binding**; **property binding bị vô hiệu theo mặc định**, trừ khi bạn khai báo `allowedFields` một cách rõ ràng. Đây là lựa chọn tốt với record/immutable DTO chỉ có các constructor arguments cần cho request. Không sao chép đoạn này vào demo mutable `SearchForm` mà không sửa thiết kế, vì mẫu chính dựa vào setters; nếu chỉ bật constructor-only với constructor rỗng, form fields `term` và `page` sẽ không được gán như ý muốn.

### 9.4. Các bước phòng vệ gợi ý

1. Xây dựng **request DTO chuyên biệt**, chỉ expose các trường đã được chấp thuận.
2. Ưu tiên immutable constructor binding cho những input mà kiểu này phù hợp.
3. Nếu dùng mutable bean/property binding, giới hạn allowed fields và xem xét nested/indexed paths có thể bind.
4. Validate kiểu dữ liệu và constraint; kiểm tra authorization ở business/service layer.
5. Chỉ copy field đã được phép từ DTO vào entity sau khi xác thực, không dùng request trực tiếp để thay thế object hiện có.
6. Với form có trạng thái/session, hiểu chính xác nguồn model object để tránh bind nhầm entity hoặc trạng thái không thuộc request.

Bảo mật gắn dữ liệu là vấn đề **đối tượng nào được tạo, trường nào có thể thay đổi, và ai có quyền thay đổi**, ngoài chuyện có `@Valid` hay không.

## 10. Khi nào chọn `@RequestParam`, `@ModelAttribute`, `@RequestBody`?

| Tình huống | Lựa chọn thông dụng | Giải thích |
|---|---|---|
| Một hoặc hai query params đơn giản | `@RequestParam` | Rõ và ngắn |
| Form HTML gửi nhiều input | `@ModelAttribute` | Gom và bind thành form object |
| GET endpoint có bộ lọc nhiều field | `@ModelAttribute` | DTO có type conversion và validation |
| REST API nhận JSON | `@RequestBody` | Dùng HTTP message converters/Jackson |
| HTML form submit lỗi cần render lại | `@Valid @ModelAttribute` + `BindingResult` | Có object và lỗi để đưa về view |
| Upload file kèm các field form | `@ModelAttribute` DTO có `MultipartFile` khi multipart được cấu hình | Form binding dùng multipart infrastructure |
| Handler chỉ cần entity đã load, không cần bind thêm | `@ModelAttribute(binding=false)` | Ngăn request sửa entity qua property binding |
| Một path segment định danh | `@PathVariable` | Nguồn dữ liệu từ URI template |

Một request có body JSON `{"term":"java","page":2}` với Content-Type `application/json` **không** được xử lý bởi `@ModelAttribute` theo nghĩa tự gọi Jackson deserialize JSON. Đối với body JSON thông thường:

~~~java
@PostMapping(
    path = "/search-json",
    consumes = MediaType.APPLICATION_JSON_VALUE)
public SearchResult searchJson(
        @Valid @RequestBody SearchRequest request) {
    // Xử lý DTO được JSON deserialization.
}
~~~

Đây là snippet minh họa; cần class `SearchRequest` và `SearchResult`, không thuộc code chạy của demo chính. `@RequestBody` dùng message converters, còn `@ModelAttribute` dùng binder tạo/gán model object. Cả hai đều có thể phối hợp `@Valid` nhưng có đường xử lý input khác nhau.

## 11. Kiểm thử với MockMvc

Một smoke test bằng curl xác nhận đường HTTP hoạt động; một integration test bằng `MockMvc` giúp tự động kiểm tra việc Spring bind query/form, chuyển kiểu và ghi lỗi. Trong project Boot 3 có thể thêm:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Lưu file:

`src/test/java/com/example/binding/SearchControllerTest.java`

~~~java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SearchControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void queryParametersPopulateObject() throws Exception {
        mvc.perform(get("/catalog/search")
                .param("term", "java")
                .param("page", "2")
                .param("sort", "recent"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.valid").value(true))
            .andExpect(jsonPath("$.term").value("java"))
            .andExpect(jsonPath("$.page").value(2))
            .andExpect(jsonPath("$.sort").value("recent"))
            .andExpect(jsonPath("$.errorCount").value(0));
    }

    @Test
    void formBodyPopulatesObject() throws Exception {
        mvc.perform(post("/catalog/submit")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("term", "spring")
                .param("page", "3"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.term").value("spring"))
            .andExpect(jsonPath("$.page").value(3))
            .andExpect(jsonPath("$.sort").value("relevance"));
    }

    @Test
    void beanValidationErrorsAreCaptured() throws Exception {
        mvc.perform(get("/catalog/search")
                .param("term", " ")
                .param("page", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.valid").value(false))
            .andExpect(jsonPath("$.errorCount").value(2));
    }

    @Test
    void typeMismatchIsABindingError() throws Exception {
        mvc.perform(get("/catalog/search")
                .param("term", "java")
                .param("page", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.valid").value(false));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Hoặc trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Với Spring Boot 3.x, Web và Validation starters, các test trên kỳ vọng **PASS**. Chúng kiểm tra request mapping và binding qua HTTP simulation, thay vì chỉ gọi setter thủ công. `MockMvc.param(...)` mô phỏng request parameters; ở POST test, Content-Type được đặt `application/x-www-form-urlencoded` cho đúng form endpoint.

Nếu ứng dụng thật có Spring Security, CSRF hoặc custom filters, test POST có thể cần cấu hình thêm; project minh họa chỉ gồm Web + Validation.

### Bổ sung test cho allowlist

Nếu DTO vô tình có thêm một setter nhạy cảm trong tương lai, nên có test rằng request field ngoài `allowedFields` không làm thay đổi thuộc tính đó. `BindingResult.getSuppressedFields()` có thể giúp quan sát field bị từ chối. Mẫu demo chỉ có ba field public nên an toàn hơn từ đầu; dùng allowlist như một lớp giới hạn bổ sung.

## 12. Những lỗi phổ biến và cách chẩn đoán

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
|---|---|---|
| Controller nhận object nhưng mọi thuộc tính đều `null` | Request keys không khớp, thiếu setter, bật constructor-only trên bean mutable, hoặc gửi JSON body cho `@ModelAttribute` | Xem Content-Type, DTO constructor/setters, `@InitBinder` và field names |
| `page` vẫn là `1` dù gửi `page=2` | Field không được bind hoặc bị allowlist chặn | Kiểm tra `setAllowedFields`, tên request key và setter |
| `page=abc` gây lỗi | Không chuyển được chuỗi thành số nguyên | Đọc `BindingResult`, trả HTTP 400 với lỗi có cấu trúc |
| `@NotBlank` không báo lỗi | Không kích hoạt validation hoặc thiếu provider | Thêm `@Valid`/`@Validated` đúng vị trí và Validation starter |
| Có lỗi nhưng handler không chạy | Không khai báo `BindingResult` ngay sau attribute hoặc MVC dùng exception path | Đặt `BindingResult` đúng chỗ hoặc dùng `@ControllerAdvice` |
| Gửi JSON body nhưng `SearchForm` không có giá trị | `@ModelAttribute` không deserialize JSON bằng Jackson | Chọn `@RequestBody` cho JSON |
| Request field `filter.term` không bind như kỳ vọng | Nhầm tên model attribute với prefix của request key | Mẫu đơn giản dùng `term=...`, `page=...` |
| Field nhạy cảm bị sửa | Bind trực tiếp domain entity có setter hoặc constructor input không được kiểm soát | Dùng request DTO, allowlist, constructor-only khi phù hợp |
| Nested field như `address.city` không nhận | Nested object hoặc writable property path không phù hợp | Kiểm tra class, getter/setter, constructor và binder limits |
| Lỗi field dù người dùng gửi ngày hợp lệ | Date formatter/locale không phù hợp | Dùng `@DateTimeFormat` hoặc converter/formatter phù hợp |
| `@InitBinder("filter")` không chạy như dự kiến | Model attribute thực tế có tên khác | Khớp tên `@ModelAttribute("filter")` và binder scope |
| Form POST trả `415 Unsupported Media Type` | Handler yêu cầu `application/x-www-form-urlencoded` nhưng client gửi loại khác | Sửa Content-Type hoặc chọn handler thích hợp |
| BindingResult vẫn có lỗi dù đã đặt default | Request có giá trị sai/constraint chưa đạt | Phân biệt default cho key thiếu với key hiện diện nhưng invalid |
| Dùng record nhưng binding trống | Constructor parameter names/annotation mapping không có, phiên bản Spring không hỗ trợ cơ chế mong muốn | Kiểm tra Spring version, Java bytecode parameter metadata và `@BindParam` |
| Template hiển thị lại form sai | Model attribute name không khớp giữa controller và template | Dùng tên rõ ràng và giữ `BindingResult`/model phù hợp |
| Form nhiều bước không giữ object | Chưa dùng cơ chế session model phù hợp | Cân nhắc `@SessionAttributes` và `SessionStatus.setComplete()` |
| Tài liệu chạy native image bị lỗi reflection binding | Implicit model attribute không cung cấp đủ AOT hints | Gắn `@ModelAttribute` tường minh và kiểm tra native configuration |

Quy trình debug thực dụng: **HTTP method/Content-Type → request parameter names → attribute name/nguồn object → constructor hoặc setter → `WebDataBinder`/allowlist/converter → `BindingResult` → Bean Validation → handler logic**. Không nên sửa DTO hoặc tự thêm `@Autowired` nếu nguyên nhân chỉ là request gửi JSON cho một form binder.

## 13. Các tình huống thực tế cần chọn cách bind phù hợp

### Bộ lọc tìm kiếm bằng GET

GET query hợp lý khi người dùng muốn copy URL, bookmark hoặc tạo các link có trạng thái bộ lọc. `@ModelAttribute SearchForm` gom nhiều field, nhưng cần tránh đưa thông tin nhạy cảm vào query vì URL có thể xuất hiện trong history/log. Giới hạn page/size/sort ở server và dùng default rõ ràng.

### Biểu mẫu tạo dữ liệu bằng POST

POST form URL-encoded là kiểu gửi dữ liệu truyền thống của HTML form. `@ModelAttribute` nhận DTO; `@Valid` và `BindingResult` báo lỗi. Với HTML server-rendered, controller thường trả lại view khi có lỗi và chỉ gọi service sau khi form hợp lệ.

### Chỉnh sửa đối tượng đã có trong cơ sở dữ liệu

Không load entity đầy đủ rồi bind tùy ý các request fields vào entity. Dùng DTO chuyên biệt, xác thực user có quyền sửa, sau đó copy field hợp lệ sang entity trong service/transaction. Nếu cần đưa entity đã load vào handler như dữ liệu đọc, `@ModelAttribute(binding=false)` hữu ích.

### Form có collection hoặc object lồng nhau

Dùng tên property như `address.city` hoặc `items[0].name` nếu DTO và binder cho phép. Kiểm tra giới hạn độ sâu/index và allowlist; không nên cho phép client tự quyết định toàn bộ object graph của domain model.

### API nhận JSON

Dùng `@RequestBody` và type-safe DTO, không ép form binder xử lý JSON chỉ vì DTO có cùng trường. `@ModelAttribute` và `@RequestBody` đều có thể dùng Bean Validation, nhưng phụ thuộc vào nguồn dữ liệu/contract của endpoint.

## 14. Câu hỏi tự kiểm tra

**1. Request `GET /search?term=java&page=2` có thể bind vào `@ModelAttribute SearchForm` không?**

Có, nếu DTO có constructor/property binding phù hợp và request keys khớp tên input; Spring chuyển `page` thành kiểu Java phù hợp.

**2. Vì sao `@ModelAttribute("filter")` không đòi request phải gửi `filter.term=java`?**

`filter` là tên object trong Spring model. Binder dùng các request parameter names như `term` để map vào property/constructor arguments tương ứng.

**3. Gửi `Content-Type: application/json` với body `{"term":"java"}` có tự đi qua `@ModelAttribute` không?**

Không theo cơ chế deserialize JSON thông thường. Dùng `@RequestBody` cho JSON body.

**4. `@ModelAttribute` tự kiểm tra `@NotBlank` trên DTO chứ?**

Binding không đồng nghĩa validation. Thêm `@Valid` hoặc `@Validated` theo đúng cơ chế, bảo đảm có provider và xử lý lỗi qua `BindingResult` hoặc exception.

**5. Vì sao `BindingResult` phải nằm ngay sau model attribute?**

Để Spring gắn lỗi vào đúng đối tượng handler argument. Nếu chen tham số khác, signature không đáp ứng quy tắc xử lý lỗi tại chỗ.

**6. Với `page=abc` khi Java field là `Integer`, đây là lỗi nào?**

Lỗi chuyển kiểu trong quá trình binding. `BindingResult` có thể chứa field error tương ứng, độc lập với logic `@Min`.

**7. DTO có setter `setAdministrator(boolean)` nhưng form không hiển thị input admin. Có đủ an toàn không?**

Không. Client vẫn có thể tự gửi key `administrator=true`. Cần DTO đúng phạm vi, allowlist hoặc constructor binding được kiểm soát, và kiểm tra quyền tại service.

**8. `setDeclarativeBinding(true)` ảnh hưởng gì tới JavaBean mutable chỉ có constructor rỗng và setters?**

Property binding không còn chạy mặc định nếu không khai báo allowed fields; dữ liệu có thể không được gắn vào setters như trước. Phải chọn DTO/constructor phù hợp với chế độ đó.

**9. Khi nào nên dùng `@ModelAttribute(binding=false)`?**

Khi object đã có trong model và controller chỉ cần truy cập nó, không muốn request tự sửa các property của object.

**10. Vì sao test phải dùng MockMvc thay vì chỉ gọi `new SearchForm(); form.setPage(2);`?**

Setter thủ công không kiểm tra argument resolver, HTTP parameter parsing, type conversion, binder rules, Bean Validation hay `BindingResult` của Spring MVC.

## 15. Checklist triển khai `@ModelAttribute`

- [ ] Xác định endpoint nhận query/form parameters hay JSON để chọn `@ModelAttribute` hoặc `@RequestBody`.
- [ ] Chọn DTO chỉ gồm field được phép nhập; xác nhận constructor, parameter names, setters hoặc record binding.
- [ ] Đặt `@ModelAttribute("name")` tường minh nếu cần name ổn định hoặc native-image/AOT hints.
- [ ] Với HTML form/GET query, kiểm tra tên `name` của input khớp DTO property/constructor argument.
- [ ] Kiểm tra `ConversionService`, `Formatter`, enum/date conversion và nested field paths.
- [ ] Bật Bean Validation nếu cần: `@Valid`/`@Validated`, provider và constraints trên DTO.
- [ ] Đặt `BindingResult` ngay sau attribute nếu muốn handler tự xử lý binding/validation errors.
- [ ] Với property binding, giới hạn `allowedFields` hoặc dùng constructor-only/declarative binding khi phù hợp.
- [ ] Không bind thẳng entity chứa field nhạy cảm; map DTO sang entity tại service sau authorization.
- [ ] Kiểm thử GET query, POST URL-encoded, input thiếu, input sai kiểu, invalid constraints và request chứa field không được phép.
- [ ] Nếu trả HTML, xác minh model name, view rendering và việc hiển thị lại field errors.
- [ ] Nếu form nhiều bước dùng session model, dọn `@SessionAttributes` khi hoàn tất.

**Ghi nhớ:** `@ModelAttribute` nhận **một đối tượng** từ Spring MVC model và liên kết dữ liệu **query/form** qua `WebDataBinder`; constructor/property binding chuyển giá trị HTTP vào kiểu Java. `@Valid`/`@Validated` thêm kiểm tra dữ liệu, `BindingResult` giữ lỗi, còn DTO/allowed fields bảo vệ phạm vi dữ liệu được phép sửa. Với JSON body, cơ chế chính là `@RequestBody`.

## Tài liệu tham khảo chính thức

- [Spring MVC — @ModelAttribute method arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — @ModelAttribute methods to initialize the model](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-modelattrib-methods.html)
- [Spring MVC — @InitBinder and model design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC — @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
