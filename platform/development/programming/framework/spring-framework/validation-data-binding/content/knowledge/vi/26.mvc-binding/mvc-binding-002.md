# ServletRequestDataBinder và nguồn tham số HTTP trong Spring MVC

## 1. Tổng quan: từ HTTP request thành JavaBean

Khi nhận dữ liệu biểu mẫu hoặc query string, ứng dụng Spring MVC thường muốn dùng **đối tượng Java có kiểu** thay cho việc tự đọc từng giá trị chuỗi rồi chuyển kiểu thủ công. Ví dụ HTTP gửi `name=Lan&age=26&newsletter=true` và Java cần một `ProfileForm` có `String name`, `int age`, `boolean newsletter`.

`org.springframework.web.bind.ServletRequestDataBinder` là thành phần thuộc **Spring Web (Servlet stack)** chuyên thực hiện **data binding từ tham số của `jakarta.servlet.ServletRequest` vào JavaBean**. Nó kế thừa `WebDataBinder` → `DataBinder` và hỗ trợ thêm file multipart. `bind(ServletRequest)` chuyển dữ liệu request thành tập giá trị thuộc tính, áp dụng quy tắc allowed/required fields, chuyển kiểu, cập nhật target và ghi lỗi binding vào `BindingResult`.

Phân biệt ba công việc:

- **Thu thập dữ liệu:** `ServletRequest#getParameterMap()` đại diện cho các request parameters mà Servlet container đã phân tích từ query string/form body. Multipart cần cơ chế xử lý thêm.
- **Binding và chuyển kiểu:** `ServletRequestDataBinder#bind(request)` gán chúng vào thuộc tính target thông qua property access, type conversion và các cấu hình binder.
- **Validation nghiệp vụ:** annotation như `@NotBlank`, `@Min` hoặc Spring `Validator` có thể kiểm tra *sau* bước binding. Chỉ gọi `bind(request)` **không đồng nghĩa tự chạy toàn bộ Bean Validation**.

Trong controller Spring MVC, công việc thường được thực hiện tự động cho tham số `@ModelAttribute`. Hiểu `ServletRequestDataBinder` giúp giải thích nguồn dữ liệu, lỗi `typeMismatch`, checkbox không gửi giá trị, multipart và rủi ro **mass assignment** khi người dùng có thể gửi thêm property không mong muốn.

## 2. Vị trí trong hệ thống Spring

Sơ đồ đơn giản:

~~~text
HTTP request (query string / HTML form / multipart)
         |
         v
jakarta.servlet.ServletRequest
         |
         +-- getParameterMap(): tham số String/String[]
         +-- MultipartRequest / Servlet Part (nếu có)
         |
         v
ServletRequestDataBinder
  ├─ ServletRequestParameterPropertyValues
  ├─ bổ sung MultipartFile/Part khi tương ứng
  ├─ WebDataBinder: field defaults/markers
  ├─ DataBinder: allowed/required fields, conversion
  └─ BindingResult: các lỗi và suppressed fields
         |
         v
JavaBean / form object
         |
         v
Validator (khi MVC hoặc ứng dụng kích hoạt)
         |
         v
Controller / kết quả lỗi / xử lý nghiệp vụ
~~~

Những thành phần liên quan:

| Thành phần | Vai trò |
| --- | --- |
| `DataBinder` — `org.springframework.validation.DataBinder` | Binding vào target, hỗ trợ allowed fields, required fields, converter, `BindingResult`, đăng ký validator. Không phụ thuộc HTTP. |
| `WebDataBinder` — `org.springframework.web.bind.WebDataBinder` | Bổ sung xử lý HTML form: field marker, default, multipart. |
| **`ServletRequestDataBinder`** | Nhận trực tiếp `ServletRequest` và các request parameters/part, gọi binding. |
| `ServletRequestParameterPropertyValues` | Chuyển request parameters thành `MutablePropertyValues`; có overload lọc theo prefix. |
| `ExtendedServletRequestDataBinder` | Biến thể dùng trong Spring MVC để bổ sung **URI template variables và request headers** vào các giá trị binding khi phù hợp. |
| `BindingResult` | Chứa kết quả chuyển kiểu, lỗi `required`/`typeMismatch`, errors và các property bị chặn (suppressed). |
| `@ModelAttribute` | Cách khai báo controller thường dùng; Spring chọn và cấu hình binder phù hợp cho request. |
| `@InitBinder` | Hook của controller hoặc `@ControllerAdvice` để đặt allowed fields, converter, validator, tùy biến binder. |

**Lưu ý version:** bài dùng namespace `jakarta.servlet.*`, tương ứng Spring Framework **6+/7+** và Spring Boot **3+**. `ServletRequestDataBinder#construct(ServletRequest)` (constructor binding) có từ **Spring Framework 6.1**. Ở các bản cũ hơn, constructor binding và sự tích hợp/kiểu import có thể khác.

## 3. Nguồn tham số HTTP mà binder thực sự đọc

### 3.1. Query parameters và form parameters

Trong Servlet API, request parameter map thông thường cung cấp:

- Các cặp tên/giá trị trên URL, ví dụ `GET /profiles?name=Lan&age=26`.
- Dữ liệu HTML form đã được Servlet container giải mã, ví dụ `POST` với `application/x-www-form-urlencoded`.
- Giá trị lặp lại với cùng tên, ví dụ `tags=java&tags=spring`, được biểu diễn bằng `String[]` ở `getParameterValues("tags")`.

`ServletRequestDataBinder#bind(request)` mặc định tạo `ServletRequestParameterPropertyValues(request)` **không áp prefix**, chuyển chúng thành property values và binding vào target. Tên tham số phải tương ứng với tên thuộc tính JavaBean có thể ghi:

~~~text
HTTP request parameter       JavaBean target
------------------------     ------------------------------
name=Lan                     setName("Lan")
age=26                       setAge(26)              [String → int]
newsletter=true              setNewsletter(true)     [String → boolean]
address.city=Da Nang         getAddress().setCity("Da Nang")
tags=java&tags=spring        setTags(String[])       [nếu target có array]
~~~

Các tên lồng như `address.city` và chỉ số như `items[0].name` là **đường dẫn property** của BeanWrapper, không phải tên field trong JSON. Binder cần đường dẫn hợp lệ, target có thể ghi và cấu hình binding cho phép. Với nested collection, kiểm soát `autoGrowCollectionLimit` để tránh client cấp chỉ số quá lớn.

**Đừng giả định thứ tự/ưu tiên** khi query string và form body có cùng tên tham số. Servlet container xác định parameter map; nếu yêu cầu quan trọng, hãy thiết kế API tránh trùng key hoặc dùng cơ chế nhận dữ liệu có hợp đồng rõ ràng.

### 3.2. File multipart

`bind(request)` hỗ trợ `multipart/form-data` khi request đã được xử lý thành `MultipartRequest`/`MultipartHttpServletRequest`, hoặc có Servlet `Part` phù hợp trong điều kiện framework hỗ trợ. File dùng **tên phần multipart** để tìm thuộc tính bean, ví dụ `avatar` ↔ `setAvatar(MultipartFile avatar)`. Các kiểu property file được hỗ trợ bao gồm `MultipartFile`, `byte[]` hoặc `String` tùy nguồn và conversion.

Bật và cấu hình multipart trong stack Spring MVC phù hợp trước khi kỳ vọng request file tự xuất hiện trong binder. `WebDataBinder#setBindEmptyMultipartFiles(false)` có thể ngăn file rỗng ghi đè file đã có; mặc định thiết lập này là `true`. Việc lưu file, giới hạn kích thước, kiểm tra MIME/type và quét nội dung cần xử lý riêng; binding không phải cơ chế bảo đảm tệp an toàn.

### 3.3. URI template variables và HTTP headers

Một điểm dễ hiểu sai: **`ServletRequestDataBinder` trực tiếp** chủ yếu lấy **request parameters và multipart**, không tự quét mọi header, cookie, path variable hoặc JSON body.

Trong **Spring MVC `@ModelAttribute`**, biến thể `ExtendedServletRequestDataBinder` có thể bổ sung **URI template variables và request headers** khi xây giá trị binding. Theo tài liệu MVC, chúng chỉ được thêm nếu không ghi đè request parameter có cùng tên; dấu gạch ngang trong tên header được loại bỏ để ánh xạ đến property. Ví dụ:

~~~java
@PostMapping("/accounts/{accountId}/profile")
String update(@ModelAttribute AccountForm form,
              BindingResult result) {
    // Spring MVC chuẩn bị và bind form cho handler.
    return result.hasErrors() ? "profile-form" : "profile-ok";
}
~~~

Đây là **snippet controller** (giả định `AccountForm`, imports, view names đã có), không phải chương trình độc lập. Nếu URL có `/accounts/42/profile`, biến `accountId=42` có thể tham gia vào binding của `AccountForm` trong tích hợp MVC, nhưng chỉ khi không bị tham số request cùng tên ghi đè và thuộc tính được cho phép. **Không suy rộng hành vi MVC này sang lời gọi thủ công `new ServletRequestDataBinder(form).bind(request)`.**

**Cookies và arbitrary headers không mặc nhiên là request parameters.** `@CookieValue` và `@RequestHeader` dùng argument resolver riêng khi cần dữ liệu đó một cách tường minh. Header tham gia binding trong MVC cũng phải chịu whitelist và kiểm soát tin cậy như mọi input client gửi.

### 3.4. JSON body là luồng khác

Với JSON:

~~~http
POST /profiles
Content-Type: application/json

{"name":"Lan","age":26}
~~~

Controller thường dùng:

~~~java
@PostMapping("/profiles")
ResponseEntity<Void> create(@Valid @RequestBody ProfileRequest body) {
    // ...
    return ResponseEntity.ok().build();
}
~~~

Ở đây `@RequestBody` sử dụng `HttpMessageConverter` (thường Jackson) để đọc JSON, sau đó validation nếu được kích hoạt. JSON object **không tự trở thành Servlet request parameters** cho `ServletRequestDataBinder#bind`. Phân biệt hai đường đi giúp tránh nhầm vì sao `@ModelAttribute` không nhận JSON body theo cách `@RequestBody` làm.

## 4. API và vòng đời `ServletRequestDataBinder`

Các API quan trọng:

| API | Mục đích |
| --- | --- |
| `new ServletRequestDataBinder(target, "profileForm")` | Tạo binder cho target và object name dùng trong BindingResult. |
| `bind(ServletRequest request)` | Gán request parameters/multipart vào target đang có; có thể tạo field errors. |
| `construct(ServletRequest request)` (6.1+) | Tạo target qua data constructor từ request, khác với setter/property binding. |
| `getBindingResult()` | Lấy errors, field errors, suppressed fields; không tự tạo HTTP response. |
| `setAllowedFields("name", "age", ...)` | Chỉ cho phép property paths được chỉ rõ trong **setter/property binding**. |
| `setRequiredFields("name")` | Yêu cầu có field trong binding input; thiếu field gây lỗi mã `required`. |
| `setDeclarativeBinding(true)` (6.1+) | Cho phép constructor binding và chỉ cho setter binding khi có allowed fields. |
| `setConversionService(...)` / `registerCustomEditor(...)` | Tùy chỉnh chuyển kiểu và định dạng. |
| `setFieldMarkerPrefix(...)` / `setFieldDefaultPrefix(...)` | Tùy chỉnh `_field` và `!field` từ HTML form. |
| `setBindEmptyMultipartFiles(...)` | Điều khiển việc bind MultipartFile rỗng. |
| `closeNoCatch()` | Coi binding errors là nghiêm trọng; ném `ServletRequestBindingException` khi có lỗi. |

Luồng lập trình thủ công thông dụng:

~~~java
ProfileForm form = new ProfileForm();
ServletRequestDataBinder binder =
        new ServletRequestDataBinder(form, "profileForm");
binder.setAllowedFields("name", "age", "newsletter");
binder.bind(servletRequest);
BindingResult result = binder.getBindingResult();

if (result.hasErrors()) {
    // Xử lý typeMismatch / required / lỗi binding.
}
~~~

Đoạn này là **snippet minh họa** trong môi trường có `ProfileForm`, `ServletRequest` và imports; chương trình kiểm thử hoàn chỉnh ở phần 6. Binder có thể được Spring MVC tạo/sử dụng trong request pipeline; bình thường không cần khởi tạo thủ công ở controller chỉ để dùng `@ModelAttribute`.

### `BindingResult` và error code

- `result.getFieldError("age")`: trả `FieldError` khi `age=not-a-number` không chuyển sang `int` được. Mã lỗi thường bắt đầu từ `typeMismatch` (có thể được mở rộng thành các mã cụ thể theo object/property/type bằng `MessageCodesResolver`).
- `result.getFieldError("name")`: có thể mang mã `required` khi `setRequiredFields("name")` và tham số thiếu.
- `result.hasErrors()` kiểm tra có lỗi (binding hoặc validation nếu validation đã được kích hoạt).
- `result.getSuppressedFields()` liệt kê những property **bị chặn bởi allowed/disallowed field filter**. Không phải mọi request parameter lạ đều xuất hiện ở đây; đừng xem danh sách này là nhật ký đầy đủ của mọi key HTTP.
- `setIgnoreUnknownFields(true)` mặc định cho phép bỏ qua một số thuộc tính không tồn tại; đừng dựa vào đó để chặn mass assignment trên các property **có tồn tại**.
- `binder.validate()` chỉ chạy các validator đã đăng ký với binder. `bind(request)` đơn lẻ **không mặc định gọi** `binder.validate()`.

## 5. HTML form đặc biệt: checkbox marker và default

HTML checkbox không được chọn thường **không gửi** parameter tên field. Nếu target ban đầu có `newsletter=true`, form submit bỏ checkbox có thể để nguyên giá trị cũ nếu binder không biết checkbox từng xuất hiện.

`WebDataBinder` hỗ trợ hai cơ chế:

**Field marker (mặc định prefix `_`):**

~~~text
_newsletter=present
~~~

Nếu có `_newsletter` mà **không có `newsletter`**, binder hiểu field có mặt trên form nhưng không gửi giá trị và reset property về giá trị rỗng thích hợp (với `boolean` là `false`). Giá trị của marker như `present` không quan trọng; chỉ sự tồn tại của marker là tín hiệu.

**Field default (mặc định prefix `!`):**

~~~text
!age=18
~~~

Khi `age` không được gửi, binder có thể sử dụng `18` làm default rồi chuyển kiểu thành `int`. Default parameter có ưu tiên hơn field marker cho cùng field nếu cả hai được gửi.

Ví dụ HTML marker:

~~~html
<input type="hidden" name="_newsletter" value="present">
<input type="checkbox" name="newsletter" value="true">
~~~

Đây là ví dụ HTML form. Nếu checkbox được tick, trình duyệt gửi cả `newsletter=true` và marker; giá trị thực được bind. Nếu bỏ tick, trình duyệt chỉ gửi marker nên property được reset thành `false`. **Không sử dụng marker để ủy quyền bảo mật**: client có thể tự ý gửi hoặc sửa cả marker lẫn field.

Chú ý `ServletRequestParameterPropertyValues(request, "profile")` với prefix theo định dạng `profile_name` là **chức năng lọc prefix của lớp PropertyValues**, khác hoàn toàn marker `_newsletter` và default `!age` của `WebDataBinder`. `ServletRequestDataBinder#bind(request)` mặc định không tự dùng prefix `profile_`.

## 6. Ví dụ chạy được: kiểm thử binder với HTTP parameters

Dùng **Java 17+**, dự án **Spring Boot 3+** Maven, thêm hai dependency sau nếu chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo file **`src/test/java/com/example/binding/ServletRequestDataBinderTest.java`** với đầy đủ mã Java. `MockHttpServletRequest` và `MockMultipartHttpServletRequest` đến từ `spring-test` (qua starter test), có thể mô phỏng **parameter map đã được Servlet API phân tích** mà không mở web server:

~~~java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.mock.web.MockMultipartHttpServletRequest;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.ServletRequestDataBinder;
import org.springframework.web.multipart.MultipartFile;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;

class ServletRequestDataBinderTest {

    @Test
    void bindsParametersAndSuppressesUnsafeProperty() {
        ProfileForm form = new ProfileForm();
        MockHttpServletRequest request =
                new MockHttpServletRequest("POST", "/profiles");
        request.addParameter("name", "Lan");
        request.addParameter("age", "26");
        request.addParameter("newsletter", "true");
        request.addParameter("address.city", "Da Nang");
        request.addParameter("admin", "true"); // Client gửi thêm field.

        ServletRequestDataBinder binder =
                new ServletRequestDataBinder(form, "profileForm");
        binder.setAllowedFields(
                "name", "age", "newsletter", "address.city");
        binder.bind(request);

        BindingResult result = binder.getBindingResult();
        assertFalse(result.hasErrors());
        assertEquals("Lan", form.getName());
        assertEquals(26, form.getAge());
        assertTrue(form.isNewsletter());
        assertEquals("Da Nang", form.getAddress().getCity());
        assertFalse(form.isAdmin()); // Không được bind.
        assertArrayEquals(
                new String[] {"admin"}, result.getSuppressedFields());

        System.out.println(
                form.getName() + " | " + form.getAge()
                + " | " + form.getAddress().getCity()
                + " | admin=" + form.isAdmin());
        System.out.println(
                "errors=" + result.getErrorCount()
                + ", suppressed=" + Arrays.toString(
                        result.getSuppressedFields()));
    }

    @Test
    void recordsTypeMismatchInsteadOfSilentlyAcceptingIt() {
        ProfileForm form = new ProfileForm();
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addParameter("age", "not-a-number");

        ServletRequestDataBinder binder =
                new ServletRequestDataBinder(form, "profileForm");
        binder.setAllowedFields("age");
        binder.bind(request);

        BindingResult result = binder.getBindingResult();
        assertTrue(result.hasFieldErrors("age"));
        assertEquals("typeMismatch",
                result.getFieldError("age").getCode());
        assertEquals(0, form.getAge());
    }

    @Test
    void resetsCheckboxWithFieldMarker() {
        ProfileForm form = new ProfileForm();
        form.setNewsletter(true); // Giá trị trước khi submit.
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addParameter("_newsletter", "present");
        // Không có parameter "newsletter": checkbox không chọn.

        ServletRequestDataBinder binder =
                new ServletRequestDataBinder(form, "profileForm");
        binder.setAllowedFields("newsletter");
        binder.bind(request);

        assertFalse(form.isNewsletter());
        assertFalse(binder.getBindingResult().hasErrors());
    }

    @Test
    void usesFieldDefaultWhenRealFieldIsMissing() {
        ProfileForm form = new ProfileForm();
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addParameter("!age", "18");

        ServletRequestDataBinder binder =
                new ServletRequestDataBinder(form, "profileForm");
        binder.setAllowedFields("age");
        binder.bind(request);

        assertEquals(18, form.getAge());
        assertFalse(binder.getBindingResult().hasErrors());
    }

    @Test
    void recordsRequiredFieldWhenMissing() {
        ProfileForm form = new ProfileForm();
        ServletRequestDataBinder binder =
                new ServletRequestDataBinder(form, "profileForm");
        binder.setRequiredFields("name");
        binder.bind(new MockHttpServletRequest());

        assertTrue(binder.getBindingResult().hasFieldErrors("name"));
        assertEquals("required",
                binder.getBindingResult()
                        .getFieldError("name").getCode());
    }

    @Test
    void bindsMultipartFileByPartName() {
        ProfileForm form = new ProfileForm();
        MockMultipartHttpServletRequest request =
                new MockMultipartHttpServletRequest();
        request.addFile(new MockMultipartFile(
                "avatar", "avatar.txt", "text/plain",
                "demo".getBytes(StandardCharsets.UTF_8)));

        ServletRequestDataBinder binder =
                new ServletRequestDataBinder(form, "profileForm");
        binder.setAllowedFields("avatar");
        binder.bind(request);

        assertNotNull(form.getAvatar());
        assertEquals("avatar.txt",
                form.getAvatar().getOriginalFilename());
        assertFalse(binder.getBindingResult().hasErrors());
    }

    public static class ProfileForm {
        private String name;
        private int age;
        private boolean newsletter;
        private boolean admin;
        private Address address = new Address();
        private MultipartFile avatar;

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }

        public int getAge() { return age; }
        public void setAge(int age) { this.age = age; }

        public boolean isNewsletter() { return newsletter; }
        public void setNewsletter(boolean newsletter) {
            this.newsletter = newsletter;
        }

        public boolean isAdmin() { return admin; }
        public void setAdmin(boolean admin) { this.admin = admin; }

        public Address getAddress() { return address; }
        public void setAddress(Address address) {
            this.address = address;
        }

        public MultipartFile getAvatar() { return avatar; }
        public void setAvatar(MultipartFile avatar) {
            this.avatar = avatar;
        }
    }

    public static class Address {
        private String city;

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }
}
~~~

Từ root dự án Spring Boot chạy:

~~~bash
./mvnw test -Dtest=ServletRequestDataBinderTest
~~~

Trên Windows chạy `mvnw.cmd test -Dtest=ServletRequestDataBinderTest`; nếu cài Maven dùng `mvn test -Dtest=ServletRequestDataBinderTest`. Khi các test pass, trong phần standard output của test (bên cạnh log Maven/JUnit) có **hai dòng được chương trình in chủ động**, với cấu hình này:

~~~text
Lan | 26 | Da Nang | admin=false
errors=0, suppressed=[admin]
~~~

Các điểm chính cần quan sát:

1. `name=Lan` được gán vào String; `age=26` được Spring chuyển từ String sang `int`; `address.city=Da Nang` đi vào JavaBean lồng.
2. Client gửi thêm `admin=true`, nhưng `setAllowedFields(...)` chặn property này. Target giữ `admin=false` và `BindingResult#getSuppressedFields()` ghi nhận `admin`.
3. `age=not-a-number` không được lặng lẽ biến thành tuổi hợp lệ; `BindingResult` có một `FieldError` với mã `typeMismatch`.
4. Marker `_newsletter` reset boolean đã có từ `true` về `false` khi field thật không được gửi.
5. Default `!age=18` cung cấp giá trị khi request không có `age`.
6. `setRequiredFields("name")` phát hiện thiếu parameter name; nó **không thay thế** Bean Validation `@NotBlank` cho trường hợp người dùng gửi `name=""`.
7. `MockMultipartHttpServletRequest` mô phỏng request multipart đã chuẩn bị file; binder gán `avatar` vào `MultipartFile` có tên part phù hợp.

**Giới hạn chính xác của demo:** `MockHttpServletRequest#addParameter` trực tiếp tạo parameter map để test binder. Nó **không** chứng minh cách Servlet container thực tế phân tích raw HTTP body, không chạy proxy/controller và không tự chạy Bean Validation. Để kiểm tra toàn bộ HTTP stack, dùng MockMvc hoặc integration test với Spring MVC.

## 7. Trong controller: `@ModelAttribute` và `@InitBinder`

Trên Servlet MVC, cách phổ biến nhất là khai báo parameter `@ModelAttribute`; framework tạo/điều phối binder theo request và đưa kết quả vào `BindingResult`.

Đoạn sau là **snippet controller**, giả định `ProfileForm` là DTO public có getters/setters tương tự ví dụ ở trên và đã có imports Spring thích hợp:

~~~java
@Controller
@RequestMapping("/profiles")
class ProfileController {

    @InitBinder("profileForm")
    void configureProfileBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "name", "age", "newsletter", "address.city", "avatar");
    }

    @PostMapping
    String save(@ModelAttribute("profileForm") ProfileForm form,
                BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            return "profile-form";
        }

        // Chỉ xử lý những field đã được cho phép và kiểm tra.
        return "profile-saved";
    }
}
~~~

`BindingResult` phải đặt **ngay sau** tham số `@ModelAttribute` tương ứng. `@InitBinder("profileForm")` chỉ tùy chỉnh binder cho model attribute có tên đó; nếu đặt `@InitBinder` không chỉ rõ tên, nó có thể áp dụng cho nhiều model attribute trong phạm vi controller. Trong một ứng dụng lớn, `@ControllerAdvice` hỗ trợ chính sách chung, nhưng vẫn cần biết cụ thể form nào được phép bind property nào.

Để kiểm tra Bean Validation trên form, thêm `@Valid` vào `@ModelAttribute` nếu đã có provider và dependency `spring-boot-starter-validation` (hoặc cấu hình tương đương):

~~~java
String save(@Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult result) {
    if (result.hasErrors()) {
        return "profile-form";
    }
    return "profile-saved";
}
~~~

Đoạn này cũng là **snippet phương thức**, không phải controller đầy đủ. `@Valid` yêu cầu các constraint trên DTO chạy; `bind` là bước gán dữ liệu. Với endpoint JSON `@RequestBody`, đường đi chuyển đổi là `HttpMessageConverter` như đã phân biệt.

### Constructor binding cho object immutable

Spring Framework **6.1+** hỗ trợ `ServletRequestDataBinder#construct(ServletRequest)` để khởi tạo object thông qua constructor và request parameters. Trong luồng MVC, model attribute có thể được tạo qua constructor (kể cả record) rồi tiếp tục property binding tùy cấu hình. Đây là cơ chế khác với `bind` vào bean đã tồn tại.

Ví dụ một form bất biến:

~~~java
public record CreateProfileForm(String name, Integer age) {
}
~~~

Trong controller MVC:

~~~java
@PostMapping("/new-profiles")
String create(@ModelAttribute CreateProfileForm form) {
    // Spring có thể bind các tham số qua data constructor.
    return "created";
}
~~~

Đây là **hai snippet** minh họa riêng. Khi dùng constructor binding, phải có thông tin tên parameter và configuration Spring thích hợp để ánh xạ request parameters. Có thể dùng `@BindParam("http-name")` nếu tên trên wire khác tên constructor parameter. Không nên thay đổi các quy tắc constructor binding của immutable DTO bằng cách bật toàn bộ setter binding trên entity nghiệp vụ.

`DataBinder#setDeclarativeBinding(true)` là lựa chọn của Spring 6.1+ để ưu tiên chỉ các giá trị **được khai báo** trong constructor; setter/property binding chỉ được tiến hành khi có allowed fields. Chọn cách này hoặc DTO dành riêng cho form để giới hạn bề mặt có thể bị client sửa.

## 8. Bảo mật: mass assignment, nested fields và allowed fields

**Mass assignment** xảy ra khi hệ thống bind một property không được chủ đích cho người dùng sửa. Ví dụ entity có `role`, `admin`, `accountBalance`, `ownerId`; attacker gửi:

~~~http
POST /profiles
Content-Type: application/x-www-form-urlencoded

name=Lan&admin=true&accountBalance=1000000
~~~

Nếu các setter này được binder ghi mà không có kiểm soát, client có thể thay đổi trạng thái nhạy cảm. **Dữ liệu từ HTTP là không đáng tin**, kể cả path variables, headers, form fields hoặc multipart metadata.

Cách hạn chế:

1. **Dùng form DTO chuyên dụng** chỉ chứa field mà client thực sự được chỉnh sửa; không bind trực tiếp JPA entity có nhiều thuộc tính nội bộ.
2. **Ưu tiên immutable constructor-bound DTO** với những trường được khai báo rõ. Nếu dùng property binding, đặt `setAllowedFields(...)`/`@InitBinder` cho field cần thiết.
3. **Chặn cả property paths lồng nhau**. Allowed fields có thể dùng tên như `address.city`, `items[0].quantity` hoặc mẫu wildcard nếu thật sự cần, nhưng wildcard quá rộng có thể mở thêm fields ngoài dự kiến.
4. **Kiểm tra suppressed fields** trong luồng xử lý/giám sát khi phù hợp; việc chặn field không đồng nghĩa toàn bộ request đã được chứng minh hợp lệ.
5. **Không nhầm validation với authorization**: `@NotNull` và `@Valid` không quyết định ai được chỉnh sửa `role`. Phải có kiểm tra quyền tại service/API boundary.
6. **Giới hạn auto-grow và nested structures** khi nhận các đường dẫn property động; đừng để client tạo graph quá lớn do `items[999999]`.
7. **Không chỉ dựa vào `setDisallowedFields(...)`**. Danh sách chặn dễ bỏ sót property mới khi DTO/entity thay đổi; whitelist tường minh bền vững hơn.

Ví dụ input:

~~~text
name=Lan
address.city=Da Nang
address.isVerified=true
admin=true
~~~

Với `setAllowedFields("name", "address.city")`, binder chỉ được cập nhật `name` và `address.city` qua property binding. `admin` và `address.isVerified` không nên thay đổi kể cả khi bean có setter tương ứng. Với DTO constructor-bound, vẫn phải xác định đúng những constructor arguments có thể nhận dữ liệu và không để server-only fields được khai báo làm input tùy ý.

## 9. Mở rộng, cấu hình và xử lý lỗi

### 9.1. Extension point `addBindValues`

`ServletRequestDataBinder` cung cấp:

~~~java
@Override
protected void addBindValues(
        MutablePropertyValues mpvs, ServletRequest request) {
    // Bổ sung hoặc điều chỉnh giá trị trước doBind(...).
}
~~~

Đây là **snippet subclass**, cần import `MutablePropertyValues`/`ServletRequest` và một lớp kế thừa `ServletRequestDataBinder`. Implementation mặc định của `addBindValues` là rỗng; khi cần custom binder, có thể thêm dữ liệu bổ sung có kiểm soát trước khi `WebDataBinder#doBind`. **Không tự thêm các request headers hoặc server secrets không đáng tin vào property values** nếu điều đó cho phép client ghi nhầm property nhạy cảm.

### 9.2. Chuyển kiểu và formatter

`bind(request)` áp dụng cơ chế conversion của Spring. Ví dụ `age=26` → `int` hoạt động với type conversion mặc định; `date=2026-11-12` → `LocalDate` có thể cần formatter/conversion service tương ứng. Trong Spring MVC, `@DateTimeFormat`, converter/formatter và `@InitBinder` là cách tùy chỉnh thường gặp. Lỗi parse không phải tự động lỗi nghiệp vụ; nó có thể trở thành `FieldError` mã `typeMismatch`.

Đừng tự `Integer.parseInt(request.getParameter("age"))` trong controller nếu đã thiết kế form binding: việc đó dễ tạo hai đường xử lý lỗi khác nhau. Dùng `BindingResult` để hiển thị lại form và giữ thông tin lỗi theo field.

### 9.3. Khi nào dùng `closeNoCatch()`?

`ServletRequestDataBinder#closeNoCatch()` ném `ServletRequestBindingException` nếu `BindingResult` đang có lỗi. Nó chỉ nên dùng khi lỗi binding phải được coi là điều kiện nghiêm trọng; trong form MVC thông thường, nhận `BindingResult` ngay cạnh model attribute và trả form có thông báo lỗi thường thuận tiện hơn. `closeNoCatch()` không thay thế việc kiểm tra suppressed fields hoặc business validation.

## 10. Checklist thực hành và lỗi phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `@ModelAttribute` không nhận giá trị từ JSON | JSON body đi qua message converter của `@RequestBody`. | Dùng `@RequestBody` cho JSON hoặc gửi form/query parameters đúng định dạng. |
| `age` thành `0` và có lỗi `typeMismatch` | Chuỗi HTTP không chuyển được sang `int`. | Xem `BindingResult.getFieldError("age")` và conversion service. |
| Bỏ tick checkbox nhưng giá trị cũ vẫn `true` | Không gửi field cũng không gửi marker. | Thêm `_newsletter` hoặc cơ chế form rendering hỗ trợ marker. |
| Form multipart không bind file | Request chưa được parse thành multipart hoặc tên part khác property. | Kiểm tra multipart resolver/config, part name và kiểu property. |
| URI variable không xuất hiện khi gọi binder thủ công | `ServletRequestDataBinder` trực tiếp không tự thêm path vars. | Dùng tích hợp `@ModelAttribute`/MVC hoặc map tường minh. |
| Dữ liệu nhạy cảm bị sửa qua property khác | Bind entity rộng hoặc thiếu whitelist. | DTO chuyên dụng + allowed fields + authorization. |
| `@NotBlank` không chạy sau gọi `binder.bind` thủ công | Binding khác validation. | Đăng ký/kích hoạt validator và gọi `validate` hoặc dùng `@Valid` trong MVC. |
| Field lạ bị bỏ qua mà không báo lỗi | Unknown-field policy hoặc không phải writable property. | Dùng allowlist và quan sát suppressed fields; test request thực tế. |
| Một field lồng không thể bind | Thiếu getter/setter, đường dẫn sai, target null hoặc config auto-grow. | Kiểm tra JavaBean property paths và nested object. |

Trước khi đưa vào production:

- [ ] Xác định rõ input đi từ query/form/multipart hay JSON body; chọn `@ModelAttribute` hoặc `@RequestBody` phù hợp.
- [ ] Dùng form DTO phù hợp, giới hạn setter binding bằng allowed fields hoặc declarative/constructor binding.
- [ ] Dùng `BindingResult` để xử lý `typeMismatch`/`required` và nếu cần giám sát suppressed fields.
- [ ] Test nested property, repeated parameter, checkbox marker/default, multipart và lỗi chuyển kiểu.
- [ ] Đảm bảo validation/authorization chạy đúng tầng; không xem binding thành validation hoặc kiểm tra quyền.
- [ ] Kiểm tra hiện tượng URI/header sources bổ sung trong Spring MVC khác với `ServletRequestDataBinder` trực tiếp.
- [ ] Không đổi cấu hình binder hoặc dựa vào hành vi phụ thuộc version mà chưa có integration test.

## Tài liệu tham khảo

- Spring Framework API — `ServletRequestDataBinder` (method `bind`, `construct`, `addBindValues`, multipart, `closeNoCatch`): https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/bind/ServletRequestDataBinder.html
- Spring Framework API — `WebDataBinder` (field markers/defaults, multipart options): https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/WebDataBinder.html
- Spring Framework API — `ServletRequestParameterPropertyValues` (request parameter values và prefix): https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/ServletRequestParameterPropertyValues.html
- Spring Framework Reference — MVC data binding, model security, `@InitBinder`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework Reference — `@ModelAttribute` và nguồn request parameters/URI variables/headers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
