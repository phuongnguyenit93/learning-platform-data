# Nguồn dữ liệu, tên trường và giá trị đầu vào trong Spring MVC Data Binding

Khi Spring MVC nhận một HTTP request, dữ liệu từ client chưa tự trở thành thuộc tính Java. Framework phải xác định **dữ liệu nằm ở đâu**, **tên nào dùng để tìm dữ liệu**, **giá trị ban đầu là gì**, và **tham số controller hoặc thuộc tính đối tượng nào sẽ nhận giá trị ấy**. Đây là bước đầu của luồng data binding, xảy ra trước khi ứng dụng sử dụng dữ liệu và thường trước bước validation của đối tượng đã được bind.

## 1. Phân biệt bốn khái niệm

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Nguồn dữ liệu (*source*) | Vị trí chứa đầu vào của request | Query string `?page=2`, body form, biến đường dẫn, header, JSON body |
| Tên trường (*field/parameter name*) | Khóa dùng để tra cứu giá trị; với property binding thường là đường dẫn thuộc tính JavaBeans | `age`, `address.city`, `tags[0]` |
| Giá trị đầu vào (*raw input value*) | Dữ liệu client gửi, thường là chuỗi trong query/form | `"23"`, `"Da Nang"` |
| Đích binding (*target*) | Tham số method hoặc thuộc tính trên một model object sau khi được chuyển kiểu | `int page`, `ProfileForm.age` kiểu `Integer` |

Ví dụ, từ request:

```http
POST /profiles/form?campaign=web HTTP/1.1
Content-Type: application/x-www-form-urlencoded

fullName=Lan+Anh&age=23&address.city=Da+Nang&tags%5B0%5D=java&tags%5B1%5D=spring
```

Sau khi giải mã form, Spring có thể nhìn thấy các cặp tên/giá trị:

| Tên gửi lên | Giá trị sau giải mã | Đích có thể nhận |
| --- | --- | --- |
| `fullName` | `Lan Anh` | `ProfileForm.fullName: String` |
| `age` | `23` (chuỗi) | `ProfileForm.age: Integer` (số 23 sau chuyển kiểu) |
| `address.city` | `Da Nang` | `ProfileForm.address.city` |
| `tags[0]`, `tags[1]` | `java`, `spring` | Hai phần tử của `ProfileForm.tags` |
| `campaign` ở query string | `web` | `@RequestParam("campaign") String campaign` |

Điểm cần nhớ: tên `campaign` không tự động là thuộc tính của `ProfileForm`. Mỗi tên được áp dụng theo **cách controller khai báo tham số** và **cấu trúc đối tượng đích**. Giá trị `23` trong form ban đầu là text; chỉ sau khi conversion thành công mới có `Integer 23`.

## 2. Những nguồn dữ liệu Spring MVC có thể đọc

Trong Spring MVC chạy trên Servlet stack, không phải mọi nguồn đều đi qua cùng một cơ chế.

| Nguồn HTTP | Ví dụ | Cách nhận phổ biến | Cần lưu ý |
| --- | --- | --- | --- |
| Query parameter | `GET /search?page=2` | `@RequestParam("page") int page` | Query parameter thuộc tập *request parameters* của Servlet |
| Form URL-encoded body | `name=An&age=23` | `@RequestParam` hoặc `@ModelAttribute` | Body `application/x-www-form-urlencoded` được parse thành request parameters |
| Trường text trong multipart | `multipart/form-data`, part `name` | `@RequestParam` hoặc form object | Cần cấu hình hỗ trợ multipart phù hợp |
| File tải lên | part `avatar` | `@RequestParam MultipartFile`, `@RequestPart` hoặc thuộc tính form | Giá trị file không phải một chuỗi text thông thường |
| Biến trên URL | `/users/42` với `/{id}` | `@PathVariable("id") Long id` | Lấy từ kết quả khớp URL, không phải query parameter |
| HTTP header | `X-Region: vi` | `@RequestHeader("X-Region") String region` | Tên header và tên property không nên bị đồng nhất |
| Cookie | `Cookie: locale=vi` | `@CookieValue("locale") String locale` | Đọc cookie qua argument resolver tương ứng |
| JSON/XML body | `{"age":23}` | `@RequestBody ProfilePayload` | `HttpMessageConverter` deserializes body; không phải cơ chế property binding của form |
| JSON part trong multipart | Part có `Content-Type: application/json` | `@RequestPart` | Mỗi part có thể được chuyển bằng message converter |

**Chi tiết quan trọng của `@ModelAttribute`:** Spring MVC có thể dùng request parameters (query + form), URI path variables và request headers làm nguồn binding. Khi trùng tên, path variable và header không được dùng để ghi đè request parameter cùng tên; tên header được xử lý theo quy tắc riêng (ví dụ bỏ dấu gạch nối). Trong code nghiệp vụ, dùng `@PathVariable`/`@RequestHeader` khi muốn nguồn cụ thể, thay vì dựa vào cơ chế bổ sung này.

**Khác biệt giữa form và JSON:** `@ModelAttribute` thường làm việc với tập tên/giá trị phẳng như `address.city=Da+Nang`. Với `@RequestBody` và JSON, client gửi cấu trúc JSON lồng nhau như `{"address":{"city":"Da Nang"}}`; Jackson hoặc converter tương ứng tạo đối tượng từ body. Cả hai có thể được validation sau đó, nhưng cách đọc đầu vào và loại lỗi đọc/chuyển đổi khác nhau.

## 3. Tên trường được đối chiếu với thuộc tính Java như thế nào?

Với **property binding**, tên gửi lên là một *property path* theo quy ước JavaBeans. Spring dùng cơ chế truy cập thuộc tính (chẳng hạn `BeanWrapper`), setter/getter và conversion phù hợp để gán vào đối tượng.

| Tên trong form | Đường dẫn trên Java object | Điều kiện thường cần |
| --- | --- | --- |
| `fullName` | `form.setFullName(...)` | Có thuộc tính ghi được `fullName` |
| `address.city` | `form.getAddress().setCity(...)` | Có thuộc tính `address` và `city` thích hợp |
| `tags[0]` | `form.getTags().get(0)` hoặc phần tử list tương ứng | Có list/array phù hợp; binder có giới hạn auto-grow |
| `items[1].sku` | Phần tử thứ hai của `items`, trường `sku` | Cấu trúc phần tử và kiểu phần tử tương thích |
| `preferences[theme]` | Map `preferences` tại khóa `theme` | Thuộc tính `Map` tương thích |
| `tags=java&tags=spring` | Nhiều giá trị cùng tên | Có thể bind vào array/list thích hợp hoặc nhận bằng `MultiValueMap` |

Các quy tắc dễ nhầm:

1. **HTML `name` quyết định tên field gửi lên; `id` không thay thế `name`.** Ví dụ `<input id="user-age" name="age">` được gửi với khóa `age`.
2. **Tên model attribute khác tên field.** `@ModelAttribute("form") ProfileForm form` đặt tên đối tượng trong model là `form`. Trong form thông thường, field vẫn là `fullName`, không bắt buộc `form.fullName`.
3. **Tên phải khớp thuộc tính hoặc quy tắc đổi tên đã cấu hình.** `user_name` không đương nhiên khớp `userName` của JavaBean; cần đặt tên form đúng, mapper riêng hoặc cơ chế ánh xạ như `@BindParam` cho constructor binding ở các phiên bản hỗ trợ.
4. **Phân biệt cấu trúc phẳng với cấu trúc lồng nhau.** Với form, `address.city` là một key có ý nghĩa property path. Với JSON, `address` thường là object chứa key `city`.
5. **Dữ liệu do client cung cấp là không đáng tin.** Tên field có thể được sửa bằng công cụ HTTP, kể cả trường không xuất hiện trên giao diện; phải giới hạn các thuộc tính được bind.

## 4. Luồng từ request đến Java object

```text
HTTP request
  ├─ query/form parameters: tên -> một hoặc nhiều giá trị
  ├─ path variables / headers / cookies: nguồn riêng
  └─ JSON body: nội dung có cấu trúc
          |
          v
Spring MVC chọn handler và argument resolver
          |
          +-- @RequestParam / @PathVariable / @RequestHeader / ... 
          |      tra tên -> chuyển kiểu -> tham số controller
          |
          +-- @ModelAttribute
          |      tìm/tạo model object -> WebDataBinder
          |      -> constructor/property binding -> conversion
          |      -> BindingResult -> validation khi được yêu cầu
          |
          +-- @RequestBody
                 HttpMessageConverter -> object
                 -> validation khi được yêu cầu
```

Trong nhánh `@ModelAttribute`, có thể hình dung:

1. **Chọn đối tượng đích.** Spring tìm object đã có trong model/session theo cấu hình, hoặc tạo object mới bằng constructor thích hợp. Các phiên bản Spring hiện đại hỗ trợ cả constructor binding và property binding.
2. **Thu thập giá trị và tên.** Với form, request parameters có các key như `fullName`, `age`, `address.city`. Dữ liệu có thể chứa nhiều giá trị cho cùng một key.
3. **Giải property path.** Với property binding, binder đối chiếu key với thuộc tính hoặc thuộc tính lồng nhau; với constructor binding, đối chiếu tên argument constructor và có thể sử dụng `@BindParam`.
4. **Chuyển kiểu.** Ví dụ chuỗi `"23"` thành `Integer 23`, chuỗi ngày thành ngày theo formatter cấu hình. Converter/Formatter/PropertyEditor quyết định cách chuyển.
5. **Ghi lỗi binding.** Nếu `age=abc` không đổi được sang số, `BindingResult` có lỗi kiểu `typeMismatch` và thông tin field; không nên coi giá trị đó đã được chấp nhận.
6. **Validation (nếu được kích hoạt).** `@Valid`/`@Validated` có thể kiểm tra ràng buộc như `@NotBlank` hoặc `@Min` sau quá trình bind; lỗi binding và lỗi validation là hai nguyên nhân khác nhau, dù cùng được biểu diễn trong `BindingResult`.

**`DataBinder`** là phần lõi gắn tên/giá trị với đối tượng. **`WebDataBinder`** bổ sung các nhu cầu trong môi trường web. **`BindingResult`** là kết quả chứa lỗi của quá trình binding/validation và giúp controller trả lại thông báo phù hợp. Một lỗi chuyển kiểu không đồng nghĩa với một ràng buộc Bean Validation bị vi phạm.

## 5. Ví dụ đầy đủ trong một ứng dụng Spring MVC

Giả sử ứng dụng đã chạy Spring MVC và có Bean Validation provider (ví dụ project dùng `spring-webmvc` cùng cấu hình Jakarta Validation). Đây là một controller Java 17+ có thể đặt vào ứng dụng đó; **đoạn này không phải chương trình Java thuần tự chạy bằng `javac` vì cần Spring MVC, Servlet runtime và các dependency liên quan**.

**`ProfileController.java`**

```java
package demo.web;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.List;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    @PostMapping(
        path = "/form",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public ResponseEntity<String> submit(
            @Valid @ModelAttribute("form") ProfileForm form,
            BindingResult errors,
            @RequestParam(name = "campaign", required = false) String campaign) {

        if (errors.hasErrors()) {
            String fields = errors.getFieldErrors().stream()
                    .map(error -> error.getField())
                    .distinct()
                    .toList()
                    .toString();
            return ResponseEntity.badRequest().body("invalid=" + fields);
        }

        return ResponseEntity.ok(
                "name=" + form.getFullName()
                + ";age=" + form.getAge()
                + ";city=" + form.getAddress().getCity()
                + ";tags=" + form.getTags()
                + ";campaign=" + campaign
        );
    }

    public static class ProfileForm {
        @NotBlank
        private String fullName;

        @NotNull
        @Min(18)
        private Integer age;

        @Valid
        private Address address = new Address();

        private List<String> tags = new ArrayList<>();

        public String getFullName() { return fullName; }
        public void setFullName(String fullName) { this.fullName = fullName; }

        public Integer getAge() { return age; }
        public void setAge(Integer age) { this.age = age; }

        public Address getAddress() { return address; }
        public void setAddress(Address address) { this.address = address; }

        public List<String> getTags() { return tags; }
        public void setTags(List<String> tags) { this.tags = tags; }
    }

    public static class Address {
        @NotBlank
        private String city;

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }
}
```

Request mẫu (Bash hoặc shell có `curl`; giả định server chạy trên cổng 8080):

```bash
curl -sS -X POST 'http://localhost:8080/profiles/form?campaign=web' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'fullName=Lan Anh' \
  --data-urlencode 'age=23' \
  --data-urlencode 'address.city=Da Nang' \
  --data-urlencode 'tags[0]=java' \
  --data-urlencode 'tags[1]=spring'
```

Body thành công (HTTP 200, text/plain):

```text
name=Lan Anh;age=23;city=Da Nang;tags=[java, spring];campaign=web
```

**Đọc kết quả theo tên và đích:**

- `fullName` được gán qua `setFullName`; khoảng trắng trong `Lan Anh` được giải mã từ form.
- `age` là chuỗi gửi lên nhưng trở thành `Integer` nhờ conversion; `@Min(18)` kiểm tra giá trị số sau binding.
- `address.city` đi vào object lồng `Address`, không phải một thuộc tính tên nguyên văn `address.city`.
- `tags[0]`/`tags[1]` tạo nội dung list theo chỉ số; số đầu tiên là 0.
- `campaign` do `@RequestParam` nhận riêng. Không có setter `setCampaign` trong `ProfileForm`, nên nó không trở thành thuộc tính form.

Nếu gửi `age=abc`, converter không thể tạo `Integer` và `errors.hasErrors()` là true; controller trả HTTP 400 cùng danh sách field lỗi, ví dụ `invalid=[age]`. Nếu gửi `age=16`, chuyển kiểu có thể thành công nhưng `@Min(18)` tạo lỗi validation. Hai tình huống đều được kiểm tra qua `BindingResult`, với nguồn gốc lỗi khác nhau. `BindingResult` phải đứng **ngay sau** tham số `@ModelAttribute` được bind/validate như trong ví dụ.

## 6. Trường hợp nhận một giá trị và nhiều giá trị

Với một tham số đơn lẻ:

```java
@GetMapping("/search")
public String search(
        @RequestParam("q") String keyword,
        @RequestParam(name = "page", defaultValue = "1") int page) {
    return keyword + ":" + page;
}
```

Ở đây `q` và `page` là **tên HTTP parameter**, không phải tên biến Java bắt buộc phải giống hệt. Request `GET /search?q=java&page=2` trả text `java:2` nếu method được đặt trong một `@RestController`. `defaultValue` giúp cấp giá trị khi thiếu hoặc rỗng theo ngữ nghĩa của `@RequestParam`; không nên áp dụng cách hiểu ấy cho mọi property trong form object.

Với tham số lặp lại, một key có thể mang **nhiều giá trị**, không chỉ một:

```http
GET /filter?tag=java&tag=spring HTTP/1.1
```

```java
@GetMapping("/filter")
public List<String> filter(@RequestParam("tag") List<String> tags) {
    return tags;
}
```

Trong `@RestController`, method này trả danh sách gồm `java` và `spring` (thông thường được serialize thành JSON). Nếu cần giữ tất cả key và mọi giá trị thô của request, có thể nhận `@RequestParam MultiValueMap<String, String> params`. Dùng `Map<String, String>` sẽ không thể biểu diễn đầy đủ các giá trị lặp cho một key.

## 7. Khi tên không khớp, giá trị thiếu hoặc conversion thất bại

| Tình huống | Biểu hiện có thể gặp | Cách xử lý đúng |
| --- | --- | --- |
| HTML có `id="age"` nhưng thiếu `name="age"` | Browser không gửi key `age` trong form | Đặt `name` khớp input contract |
| Form gửi `full_name`, bean chỉ có `fullName` | Không bind vào field dự kiến | Thống nhất tên hoặc định nghĩa ánh xạ rõ ràng |
| Gửi `address.city` nhưng object đích không có đường dẫn ghi phù hợp | Field không bind hoặc sinh lỗi tùy cấu hình | Thiết kế DTO và nested property đúng |
| `age=abc` với đích `Integer` | Lỗi chuyển kiểu (thường `typeMismatch`) | Đọc `BindingResult`, trả lỗi đúng field |
| `age` không xuất hiện | Giá trị hiện tại có thể giữ nguyên, hoặc mới tạo có thể là `null`/giá trị mặc định | Phân biệt *missing* với chuỗi rỗng và giá trị mặc định; đặt constraint thích hợp |
| `age=` | Có input nhưng rỗng; conversion có thể thành `null` và gây lỗi required/validation tùy đích | Xử lý theo contract của API, tránh coi rỗng luôn là 0 |
| Gửi nhiều `tag` cùng tên | Một string đơn không biểu diễn đủ toàn bộ đầu vào | Dùng `List`/array/`MultiValueMap` khi cần |
| Client gửi field nhạy cảm như `isAdmin=true` | Có nguy cơ *mass assignment* nếu bind trực tiếp entity có setter | Chỉ bind DTO được phép, giới hạn field |

**Không đánh đồng ba trạng thái**: key không tồn tại; key tồn tại nhưng giá trị rỗng; key có giá trị nhưng không chuyển được sang kiểu đích. Hành vi cụ thể phụ thuộc vào annotation, kiểu Java (`int` khác `Integer`), converter và cấu hình binder. Đối với `@RequestParam`, `required=true` là mặc định; thiếu tham số bắt buộc có thể sinh lỗi trước khi chạy method. Với `@ModelAttribute`, lỗi thường được kiểm tra qua `BindingResult` nếu khai báo đúng vị trí.

## 8. Giới hạn tập field được phép bind

Validation kiểm tra dữ liệu có hợp lệ hay không; **giới hạn field** quyết định client được phép thay đổi thuộc tính nào. Không nên bind trực tiếp domain entity chứa các thuộc tính như `role`, `balance` hoặc `approved` chỉ vì frontend không hiển thị chúng.

Ưu tiên một DTO chỉ gồm field cho phép nhập. Nếu dùng property binding, có thể bổ sung danh sách field được phép:

```java
@InitBinder("form")
void configureFormBinder(WebDataBinder binder) {
    binder.setAllowedFields("fullName", "age", "address.city", "tags*");
}
```

Đây là method đặt trong controller phù hợp (cần import `org.springframework.web.bind.WebDataBinder`? **Không**: đúng import là `org.springframework.web.bind.WebDataBinder`). `tags*` bao phủ các key chỉ số như `tags[0]`. Khi áp dụng vào `ProfileController` ở trên, phương thức này chỉ cho phép property binding đến các đường dẫn đã liệt kê. Với bản Spring có hỗ trợ `setDeclarativeBinding(true)`, còn có thể lựa chọn cơ chế chỉ dùng constructor binding, và chỉ cho setter binding khi đã khai báo `allowedFields`. Constructor binding và property binding là hai cơ chế khác nhau, cần xác định mình đang sử dụng cơ chế nào.

## 9. Cách tự kiểm tra luồng binding

Khi một field “không nhận giá trị”, lần theo thứ tự sau:

1. Xem request thật (URL, `Content-Type`, body, multipart) để xác định **nguồn** và các cặp tên/giá trị sau giải mã. Đừng chỉ nhìn HTML hoặc Postman UI.
2. Kiểm tra annotation tham số controller: `@RequestParam`, `@PathVariable`, `@ModelAttribute` hay `@RequestBody`. Mỗi annotation có nguồn dữ liệu và cơ chế xử lý riêng.
3. So tên thực tế với contract: `name` trong form; property path JavaBeans; tên constructor argument và `@BindParam` nếu có; JSON property nếu dùng body converter.
4. Kiểm tra kiểu đích và conversion/formatting; quan sát `BindingResult.getFieldErrors()`, `FieldError.getField()` và mã lỗi (`typeMismatch`, mã constraint).
5. Kiểm tra ràng buộc validation, `allowedFields`, nested object, collection index và việc giá trị đã có trong model có thể được tái sử dụng.
6. Khi log debug, chỉ log tên field, kiểu lỗi và dữ liệu không nhạy cảm; tránh ghi password, token, cookie hoặc thông tin riêng tư thô.

**Bài tập nhỏ:** Với form `name="address.city" value="Hue"`, hãy giải thích vì sao `Address.city` nhận `Hue` nhưng một field `name="addressCity"` không tự động nhận vào cùng nơi. Sau đó đổi giá trị `age` từ `23` sang `abc` rồi `16` và xác định lỗi ở bước **conversion** hay **validation**. Kết quả mong đợi: tên đầu tiên là nested property path hợp lệ nếu DTO hỗ trợ; `addressCity` là một tên property khác; `abc` gây lỗi conversion, còn `16` chuyển được thành số rồi vi phạm `@Min(18)`.

## Tài liệu chính thức

- [Spring MVC: @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC: @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring MVC: Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Core: Data Binding và property paths](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring MVC: @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
