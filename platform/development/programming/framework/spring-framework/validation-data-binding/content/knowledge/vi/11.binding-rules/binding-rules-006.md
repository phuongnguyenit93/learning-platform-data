# setIgnoreUnknownFields và quyết định với trường không tồn tại trong Spring

## 1. Vấn đề: request chứa một thuộc tính mà đối tượng không có

Trong Spring Framework, **data binding** là quá trình lấy các giá trị đầu vào (thường từ request parameter, form field hoặc một nguồn `PropertyValues`) và gán vào thuộc tính của đối tượng Java. Lập trình viên định nghĩa các thuộc tính mà đối tượng có thể nhận; người gửi request lại có thể gửi thêm bất kỳ tên tham số nào.

Giả sử DTO có một thuộc tính có thể ghi là `name`:

~~~java
public class ProfileForm {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Request gửi các cặp tên/giá trị:

~~~text
name=Lan
nickname=Lana
~~~

`name` có một setter tương ứng. `nickname` không có thuộc tính để ghi trong `ProfileForm`. Khi Spring cố gắng thực hiện **property binding**, nó phải quyết định nên **bỏ qua** hay **báo lỗi** cho tên `nickname`.

Phương thức cấu hình quyết định việc này là:

~~~java
dataBinder.setIgnoreUnknownFields(true);  // Bỏ qua field không tồn tại
dataBinder.setIgnoreUnknownFields(false); // Không chấp nhận field không tồn tại
~~~

`setIgnoreUnknownFields` thuộc `org.springframework.validation.DataBinder`. Với Spring MVC, `org.springframework.web.bind.WebDataBinder` kế thừa cơ chế đó và có thể được cấu hình qua `@InitBinder`. **Giá trị mặc định là `true`**: binder bỏ qua các tham số không tương ứng với thuộc tính ghi được của target, thay vì yêu cầu mọi tên đầu vào đều tồn tại.

Quy tắc này dễ bị hiểu nhầm là một chế độ kiểm tra validation, nhưng thực chất nó quyết định **cách property accessor xử lý tên thuộc tính lạ khi ghi**. Nó không tự quy định HTTP status, không phải whitelist bảo mật và không thay thế kiểm tra các trường bắt buộc.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác `setIgnoreUnknownFields(boolean)` và trạng thái mặc định.
2. Dự đoán kết quả khi request chứa field không tồn tại, không có setter, có kiểu không hợp lệ hoặc bị chặn bởi allowed fields.
3. Phân biệt **unknown**, **invalid nested path**, **missing required**, **type mismatch** và **suppressed field**.
4. Tạo ví dụ chạy được bằng `DataBinder`, bắt đúng ngoại lệ khi cấu hình strict và kiểm tra `BindingResult`.
5. Cấu hình `@InitBinder` cho model attribute trong Spring MVC với phạm vi phù hợp.
6. Chọn chính sách bỏ qua hoặc từ chối đầu vào bất ngờ dựa trên hợp đồng API và độ an toàn khi binding.

## 2. API và hành vi mặc định

Chữ ký API:

~~~java
public void setIgnoreUnknownFields(boolean ignoreUnknownFields);
public boolean isIgnoreUnknownFields();
~~~

Trong các bản Spring Framework được sử dụng phổ biến như 5.3, 6.0, 6.1, 6.2 và 7.0, Javadoc mô tả mặc định `ignoreUnknownFields = true`. Luôn đối chiếu với **phiên bản thư viện thực tế** khi bảo trì ứng dụng.

| Cấu hình | Khi gặp một tên thuộc tính không có nơi ghi | Ý nghĩa |
| --- | --- | --- |
| Không gọi setter | Thường bỏ qua | Mặc định `true` |
| `setIgnoreUnknownFields(true)` | Bỏ qua | Ưu tiên dung nạp các tham số thừa |
| `setIgnoreUnknownFields(false)` | Không bỏ qua; có thể phát sinh `NotWritablePropertyException` | Yêu cầu tên đầu vào khớp thuộc tính ghi được |
| `setAllowedFields("name")` | Field ngoài whitelist được lọc ra trước khi gán | Là chính sách chọn field được phép bind, độc lập với flag unknown |
| Constructor binding bằng `construct(...)` | Chỉ sử dụng giá trị cần cho constructor | Flag này **không áp dụng** cho đường constructor binding |

Điểm giới hạn có trong Javadoc: cấu hình áp dụng khi binder gọi **`bind(PropertyValues)`**, không thay đổi việc đọc giá trị qua `getBindingResult()` và không tự thay đổi cơ chế constructor binding. Đối với một `@RequestBody` JSON, luồng đọc nội dung thông qua HTTP message converter/JSON deserializer là một cơ chế khác.

### 2.1. “Không tồn tại” xét theo khả năng ghi

Với chiến lược JavaBeans property binding mặc định, Spring cố gắng tìm một thuộc tính ghi được thông qua property accessor. Vì thế:

- **Không có thuộc tính** `nickname`: đây là trường unknown.
- **Có getter nhưng không có setter** cho `nickname`: thuộc tính có thể đọc nhưng không writable; trường hợp này cũng có thể dẫn tới `NotWritablePropertyException` khi binder cố gắng gán.
- **Có setter `setAge(Integer)` nhưng input là `"abc"`**: field `age` tồn tại, nhưng giá trị sai kiểu; đây là **type mismatch**, không phải unknown.
- **Có đường dẫn `address.city` nhưng `address` đang null và không thể tự tạo**: có thể là **invalid nested path**, khác unknown.
- **Không gửi `name`**: đây là field *vắng mặt*, khác với gửi một tên trường mà đối tượng không biết.

Chiến lược truy cập còn quan trọng: `DataBinder.initDirectFieldAccess()` cho phép binding trực tiếp vào field thay vì qua getter/setter. Một field không có setter có thể vẫn là đích hợp lệ trong chế độ direct field access nếu những điều kiện truy cập được đáp ứng. Vì vậy, khi đánh giá “unknown”, hãy xác định rõ binder đang dùng **BeanProperty access** hay **DirectFieldAccess**.

Không nên đánh đồng “class có thành viên tên này” với “binder có thể ghi thành công vào đường dẫn này”.

### 2.2. Một ví dụ trước và sau

Cho `ProfileForm` chỉ có `name` và input chứa `name=Lan&nickname=Lana`:

~~~text
Mặc định: ignoreUnknownFields = true
    name      -> setter được gọi -> target.name = "Lan"
    nickname  -> không tìm thấy property ghi được -> bị bỏ qua
    bind(...) -> hoàn tất, nếu không có lỗi khác

Strict: ignoreUnknownFields = false
    name      -> property ghi được
    nickname  -> không tìm thấy property ghi được
    bind(...) -> có thể ném NotWritablePropertyException
~~~

Mã xử lý không nên suy luận rằng strict mode sẽ luôn tạo một `FieldError` để controller đọc qua `BindingResult`. Ngoại lệ do **tên field không hợp lệ** được xử lý khác lỗi conversion thông thường.

## 3. Spring kiểm tra unknown field ở đâu trong pipeline?

Với property binding, mô hình thực hành gần đúng:

~~~text
PropertyValues từ request hoặc nguồn dữ liệu
             |
             v
DataBinder / WebDataBinder
             |
             +--> lọc field theo allowedFields / disallowedFields
             |
             +--> kiểm tra requiredFields (nếu cấu hình)
             |
             v
PropertyAccessor.setPropertyValues(
    values, ignoreUnknown, ignoreInvalid
)
             |
             +--> Tên writable + chuyển kiểu OK -> gán target
             |
             +--> Tên không writable:
             |       ignoreUnknown=true  -> bỏ qua
             |       ignoreUnknown=false -> NotWritablePropertyException
             |
             +--> Đường dẫn nested không truy cập được:
             |       xử lý theo ignoreInvalid và cấu hình nested path
             |
             +--> PropertyAccessException có thể gom lại:
                     BindingResult nhận lỗi conversion/ghi
~~~

Trong triển khai `AbstractPropertyAccessor`, một `NotWritablePropertyException` được bỏ qua nếu `ignoreUnknown` bật; nếu tắt thì exception được ném ra. Các lỗi `PropertyAccessException` có thể thu thập theo batch, rồi `DataBinder` chuyển các lỗi phù hợp thành thông tin binding. Lưu ý cách xử lý chi tiết của một lỗi phụ thuộc đường binding và phiên bản Spring.

Hệ quả cần nhớ:

- **Bỏ qua unknown** không đòi Spring thêm lỗi cho field đó. `result.hasErrors()` vẫn có thể là `false`.
- **Từ chối unknown** có thể làm `bind(...)` ném ngoại lệ, nên code đặt ngay sau `bind` có thể **không được thực thi**.
- **Lọc qua `setAllowedFields`** xảy ra trước khi ghi property values. Một unknown field nằm ngoài whitelist có thể bị loại trước khi strict accessor nhìn thấy nó.
- **Binding không phải giao dịch**: nếu vài property đã được gán rồi mới gặp lỗi nghiêm trọng, không giả định Spring tự rollback toàn bộ thay đổi trên object. Với API cần xử lý nguyên tử, phải thiết kế validation và thực thi nghiệp vụ thành bước riêng.

## 4. Ví dụ Java 17+ chạy độc lập: ba chính sách

Bài thử dùng Spring Context 6.2.12, Java 17+ và Gradle. Không cần Spring Boot hoặc servlet container. Nó giữ cùng một DTO và input cho ba chính sách khác nhau để so sánh trực tiếp.

Tạo thư mục dự án thử nghiệm, sau đó tạo các file:

**`settings.gradle`**

~~~groovy
rootProject.name = 'unknown-field-binding-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'UnknownFieldBindingDemo'
}
~~~

**`src/main/java/UnknownFieldBindingDemo.java`**

~~~java
import java.util.Arrays;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.NotWritablePropertyException;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class UnknownFieldBindingDemo {

    public static final class ProfileForm {
        private String name;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) {
        runCase("default", true, false);
        runCase("strict", false, false);
        runCase("strict+allow-list", false, true);
    }

    private static void runCase(
            String label, boolean ignoreUnknown, boolean allowOnlyName) {

        ProfileForm target = new ProfileForm();
        DataBinder binder = new DataBinder(target, "profileForm");
        binder.setIgnoreUnknownFields(ignoreUnknown);

        if (allowOnlyName) {
            binder.setAllowedFields("name");
        }

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "Lan");
        input.add("nickname", "Lana");

        try {
            binder.bind(input);
            BindingResult result = binder.getBindingResult();

            System.out.println(label
                    + ": ignore=" + binder.isIgnoreUnknownFields()
                    + ", name=" + target.getName()
                    + ", errors=" + result.getErrorCount()
                    + ", suppressed="
                    + Arrays.toString(result.getSuppressedFields()));
        } catch (NotWritablePropertyException ex) {
            System.out.println(label
                    + ": exception=" + ex.getClass().getSimpleName()
                    + ", property=" + ex.getPropertyName());
        }
    }
}
~~~

Chạy từ thư mục chứa `build.gradle`:

~~~bash
gradle -q run
~~~

Nếu có Gradle Wrapper, dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows. Gradle cần truy cập Maven Central khi dependencies chưa có trong cache.

**Stdout mong đợi**:

~~~text
default: ignore=true, name=Lan, errors=0, suppressed=[]
strict: exception=NotWritablePropertyException, property=nickname
strict+allow-list: ignore=false, name=Lan, errors=0, suppressed=[nickname]
~~~

### 4.1. Giải thích từng dòng output

**Trường hợp `default`:** `ignoreUnknownFields=true`. Tên `name` bind thành công, `nickname` không có thuộc tính writable và bị bỏ qua. Không có lỗi conversion hay validation khác, nên `errors=0`. Mảng `suppressed` rỗng: cơ chế bỏ qua unknown không phải là cơ chế ghi nhận **suppressed field** do whitelist.

**Trường hợp `strict`:** `ignoreUnknownFields=false` và chưa thiết lập allowed fields. `nickname` được đưa tới property accessor, nhưng `ProfileForm` không có setter cho nó. Exception `NotWritablePropertyException` xuất hiện, và catch block in ra tên thuộc tính. Đừng xây logic nghiệp vụ dựa trên giả định `name` đã được gán hay chưa sau khi gặp exception; thứ tự xử lý và các thay đổi từng phần có thể ảnh hưởng kết quả.

**Trường hợp `strict+allow-list`:** vẫn bật strict, nhưng `setAllowedFields("name")` lọc `nickname` ra khỏi bộ giá trị trước khi gán. Binding không gặp unknown property, chạy xong và ghi `suppressed=[nickname]`. Kết quả này chứng minh **strict + whitelist không nhất thiết là “cứ gửi field lạ thì ném exception”**.

Khi thực hành, hãy thử đổi `nickname` thành `name` và thêm một trường writable khác để quan sát. Sau đó thử xóa `input.add("name", "Lan")`; việc vắng `name` không bị `setIgnoreUnknownFields(false)` phát hiện là thiếu field. Muốn yêu cầu field phải có mặt, xem `setRequiredFields` ở phần tiếp theo.

## 5. Phân biệt năm tình huống dễ nhầm

| Tình huống | Ví dụ | Cơ chế liên quan | Kết quả thường gặp |
| --- | --- | --- | --- |
| **Unknown** | Input `nickname`, DTO không có property writable | `setIgnoreUnknownFields` | Mặc định bỏ qua; strict có thể ném `NotWritablePropertyException` |
| **Missing required** | Không gửi `name` dù form yêu cầu | `setRequiredFields` hoặc validation như `@NotBlank`/`@NotNull` | “required”/constraint error tùy cách cấu hình |
| **Invalid nested path** | `address.city` nhưng `address` không thể được truy cập | `setIgnoreInvalidFields`, `setAutoGrowNestedPaths` | Có thể ném `NullValueInNestedPathException` hoặc được bỏ qua |
| **Type mismatch** | `age=abc` nhưng `age` là `Integer` | `ConversionService`, `BindingErrorProcessor` | Thường là `FieldError` mã `typeMismatch` trong `BindingResult` |
| **Disallowed / suppressed** | `role=ADMIN` nhưng `allowedFields={"name"}` | `setAllowedFields`, `getSuppressedFields` | Input bị lọc trước binding; theo dõi suppressed fields |

Những loại này phải được xác định ở **đúng bước phát sinh**:

- Unknown là **tên property không ghi được**, ngay cả khi chuỗi giá trị có vẻ hợp lệ.
- Type mismatch là **tên property hợp lệ nhưng giá trị không chuyển được sang kiểu đích**.
- Missing required là **thiếu đầu vào**; khác với gửi đầu vào dư.
- Invalid nested field có thể tồn tại trong khai báo kiểu, nhưng object graph hiện tại không thể đi đến nó.
- Suppressed là **quyết định không cho bind** theo whitelist/blacklist; nó không tự động sinh `FieldError`.

### 5.1. Ví dụ setRequiredFields không thay cho unknown check

~~~java
DataBinder binder = new DataBinder(new ProfileForm(), "profileForm");
binder.setRequiredFields("name");
binder.setIgnoreUnknownFields(false);
~~~

Khi không có giá trị `name` trong `PropertyValues`, binder có thể ghi lỗi “required” theo `BindingErrorProcessor` mặc định. Điều này khác tình huống có `nickname` mà không có property tương ứng.

`setRequiredFields` kiểm tra sự hiện diện của giá trị binding theo cơ chế của binder, không tương đương hoàn toàn với mọi ràng buộc Bean Validation. Ví dụ, field được gửi dưới dạng chuỗi rỗng có thể đòi thêm validation nghiệp vụ. Từ “required” trong HTML, Jakarta Validation và `DataBinder` có thể mang những điều kiện khác nhau; đừng suy luận chúng dùng chung cùng một công tắc.

### 5.2. Ví dụ kiểu sai không thành unknown

Một DTO có `Integer age` cùng getter/setter phù hợp:

~~~java
public class AgeForm {
    private Integer age;

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Với `age=abc`, `age` là một writable property. `setIgnoreUnknownFields(true)` **không khiến giá trị “abc” tự hợp lệ**, cũng không có nhiệm vụ bỏ qua lỗi chuyển kiểu. Với cấu hình binder thông thường, `BindingResult.hasFieldErrors("age")` có thể `true`, `FieldError` chứa rejected value và mã lỗi như `typeMismatch`.

Nếu muốn từ chối dữ liệu sai, hãy xử lý lỗi conversion và validation; không dùng strict unknown mode để thay cho bộ kiểm tra kiểu.

## 6. Unknown, read-only và nested path: quyết định tinh tế

### 6.1. Property có getter nhưng thiếu setter

Ví dụ:

~~~java
public class ReadOnlyForm {
    private final String id = "fixed";

    public String getId() {
        return id;
    }
}
~~~

`id` **có thể đọc** qua getter, nhưng JavaBeans property binding mặc định không có setter để thay đổi nó. Input `id=other` thường được xử lý như một property không writable: mặc định bỏ qua, strict báo lỗi tương ứng. Việc field `id` có trong class không làm nó tự động có thể ghi.

Nếu ứng dụng muốn một giá trị bất biến, việc không có setter là một phần thiết kế, nhưng tốt hơn nữa là dùng **DTO chuyên biệt cho dữ liệu nhận**, không bind trực tiếp lên domain entity với toàn bộ cấu trúc nội bộ.

### 6.2. Null trong nested path không nhất thiết là unknown

Xét:

~~~java
public class ContactForm {
    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}

public class Address {
    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

Nếu `address` là `null` nhưng đầu vào là `address.city=Hanoi`, outcome phụ thuộc khả năng **auto-grow nested path** và cấu hình binder. Nếu auto-grow được bật và lớp nested có thể được khởi tạo, `address` có thể được tạo và `city` được gán. Nếu không thể đi qua path đó, bạn có thể gặp lỗi `NullValueInNestedPathException`.

Hai API khác nhau:

~~~java
binder.setIgnoreUnknownFields(false); // Xử lý thuộc tính không có nơi ghi
binder.setIgnoreInvalidFields(true);  // Bỏ qua nested path tồn tại nhưng không thể truy cập
~~~

`ignoreInvalidFields` mặc định là `false`; khi bật, nó giúp bỏ qua một số nested path không truy cập được. **Không nên bật flag này chỉ để “fix” lỗi input** nếu việc bỏ qua một giá trị quan trọng có thể gây ra quyết định nghiệp vụ sai. Ngược lại, bật `ignoreUnknownFields` không tự bảo đảm mọi nested path null đều được bỏ qua.

Đoạn mã trên minh họa hai class Java độc lập về cấu trúc; khi tự chạy, đặt chúng vào file riêng hoặc đổi modifier theo quy tắc Java, rồi kiểm thử với các thiết lập auto-grow thực tế của ứng dụng.

### 6.3. Tên property và chữ hoa/chữ thường

Với property JavaBeans `displayName`, input `displayName=An` thường khớp, còn `displayname=An` không nên được mặc định coi là cùng thuộc tính. Trên đường binding, tên thuộc tính có quy tắc riêng của property accessor; không nên tự động chuyển tên parameter tùy ý khi chưa khai báo contract.

Trong ứng dụng web, một lỗi đánh máy trong `name` của `<input>` rất dễ bị bỏ qua âm thầm khi `ignoreUnknownFields=true`. Nếu form không cập nhật dữ liệu dù HTTP request có tham số, hãy kiểm tra **tên chính xác của property** và setter trước khi nhìn tới validation.

## 7. Thiết lập trong Spring MVC với @InitBinder

Ở Spring MVC, `WebDataBinder` dùng một số hành vi của `DataBinder`. Ví dụ controller xử lý form `profileForm` có thể bật strict cho riêng model attribute này:

~~~java
package com.example.profile;

import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class ProfileController {

    @InitBinder("profileForm")
    public void configure(WebDataBinder binder) {
        binder.setIgnoreUnknownFields(false);
    }

    @PostMapping("/profiles")
    public String submit(
            @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "profile/form";
        }

        return "redirect:/profiles";
    }
}
~~~

Đây là **ví dụ tích hợp** (đặt trong ứng dụng Spring MVC có class `ProfileForm`, view engine và route chuyển hướng), không phải một chương trình Java độc lập. `@InitBinder("profileForm")` giới hạn customization cho attribute mang tên đó trong phạm vi controller này. `WebDataBinder` được tạo theo request/binding phù hợp, không nên lưu lại như state của singleton controller.

Với input `name=Lan`, binding được thực hiện bình thường. Nhưng nếu người dùng gửi `nickname=Lana` mà DTO không có property writable:

- Cấu hình strict khiến quá trình binding có thể ném `NotWritablePropertyException` khi resolve `@ModelAttribute`.
- Controller method có thể **chưa được gọi**, ngay cả khi có tham số `BindingResult errors` ngay sau `@ModelAttribute`.
- `BindingResult.hasErrors()` không phải một đảm bảo sẽ nhận được mọi exception về unknown property.
- HTTP status và response body phụ thuộc lớp MVC exception handling, `@ControllerAdvice`, cơ chế error response và cấu hình ứng dụng; **không được hứa luôn trả 400** nếu chưa thử trên stack thực tế.

Nếu hợp đồng public API muốn từ chối mọi tham số dư bằng HTTP 400, phải thiết kế và kiểm tra đường bắt exception/validation phù hợp; không chỉ bật một flag rồi mặc định coi đó là hợp đồng HTTP hoàn chỉnh.

### 7.1. Tùy chỉnh toàn cục có thể ảnh hưởng endpoint khác

Nếu đưa `@InitBinder` vào một `@ControllerAdvice` không giới hạn phạm vi, nhiều controller có thể chịu ảnh hưởng. Những request HTML/form có extra parameter, framework-specific marker hoặc input đến từ client cũ có thể có hành vi khác.

Trước khi bật strict trên toàn ứng dụng:

1. Liệt kê model attribute chịu ảnh hưởng và các tên field thực tế mà form gửi.
2. Xác định có dùng `@ModelAttribute`, query/form property binding hay không.
3. Test với form đúng, form thêm field dư và form chỉ thiếu field.
4. Kiểm tra exception handler và response contract.
5. Cân nhắc chỉ cấu hình cho DTO/endpoint cần kiểm soát nghiêm.
6. Test cả những tham số phụ của framework hoặc form markup thay vì giả định mọi request parameter đều được bind nguyên dạng.

`@InitBinder` có thể cấu hình conversion, formatter, allowed fields, validator và những tùy chọn binder khác. Giới hạn phạm vi giúp tránh thay đổi hành vi không chủ ý của các controller ngoài nhiệm vụ.

## 8. Vì sao setAllowedFields quan trọng hơn strict unknown với dữ liệu nhạy cảm?

Đây là điểm quyết định trong thiết kế binding an toàn.

Giả sử class nhận dữ liệu có hai writable properties:

~~~java
public class AccountForm {
    private String displayName;
    private boolean administrator;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public boolean isAdministrator() {
        return administrator;
    }

    public void setAdministrator(boolean administrator) {
        this.administrator = administrator;
    }
}
~~~

Input `administrator=true` **không phải unknown field**: DTO có setter tương ứng. Cả `setIgnoreUnknownFields(true)` lẫn `setIgnoreUnknownFields(false)` đều không tự cấm việc gán property này.

Vì vậy, nếu client chỉ được chỉnh tên hiển thị:

~~~java
@InitBinder("accountForm")
public void configureAccount(WebDataBinder binder) {
    binder.setAllowedFields("displayName");
}
~~~

Whitelisting `displayName` là quyết định cho phép **thuộc tính nào** được sửa; strict unknown chỉ quyết định cách xử lý **thuộc tính không ghi được**. Nên thiết kế DTO chỉ chứa field được chấp nhận, và dùng allow-list cho property binding nếu cần. Đối với quyền truy cập, trạng thái tài khoản, số dư hay role, phải thực hiện phân quyền ở tầng nghiệp vụ; không coi binder là ranh giới bảo mật duy nhất.

Một kết hợp có thể gây bất ngờ:

~~~java
binder.setAllowedFields("displayName");
binder.setIgnoreUnknownFields(false);
~~~

Nếu client gửi `displayName=A&administrator=true&strange=x`:

- `displayName` nằm trong allow-list.
- `administrator` dù là property tồn tại, vẫn bị loại khỏi property binding.
- `strange` không tồn tại và cũng bị loại khỏi binding vì không nằm trong allow-list.
- `getSuppressedFields()` có thể ghi lại những field bị chặn.
- Cơ chế strict không nhất thiết ném unknown-property exception, vì field đã bị lọc khỏi đầu vào trước khi property accessor được gọi.

Nếu yêu cầu “phải phát hiện và từ chối **mọi** key không được client phép gửi”, cần xây kiểm tra input keys theo schema/contract ở ranh giới request, hoặc xử lý suppressed fields theo chính sách phù hợp. `setAllowedFields` mặc định **lọc**, không phải luôn ném một exception cho mỗi field bị cấm.

### 8.1. Có nên tự từ chối suppressed fields?

Có thể, nếu hợp đồng nghiệp vụ muốn request chứa field bị cấm bị từ chối rõ ràng. Với `DataBinder` thuần, sau khi `bind(...)` hoàn tất:

~~~java
String[] suppressed = binder.getBindingResult().getSuppressedFields();
if (suppressed.length > 0) {
    throw new IllegalArgumentException("Unsupported input properties");
}
~~~

Đây là **snippet** minh họa chính sách, không tự giải quyết ánh xạ HTTP status. Với controller web, đặt logic tại chỗ có quyền kiểm tra kết quả binding/validation và đảm bảo không dùng object đã bị sửa một phần trước khi từ chối. Không trả danh sách field nội bộ nhạy cảm cho người dùng nếu không cần.

Trong code cần ghi log, hãy giới hạn độ dài/tần suất và tránh in nguyên giá trị input. Kẻ tấn công có thể cố ý gửi hàng nghìn tên tham số để tạo log noise.

## 9. Constructor binding là trường hợp ngoài phạm vi flag

Spring có thể tạo target bằng constructor binding, đặc biệt hữu ích với object bất biến, record hoặc DTO chỉ mô tả dữ liệu đầu vào hợp lệ. Javadoc của `setIgnoreUnknownFields` nói rõ: flag này áp dụng cho **property binding thông qua `bind(PropertyValues)`**, không áp dụng cho `construct(...)`, vì constructor binding lấy những giá trị cần thiết để tạo đối tượng.

Ví dụ DTO:

~~~java
public record CreateProfileRequest(String name, int age) {
}
~~~

Đoạn record chỉ có hai component `name` và `age`. Việc constructor binding có bỏ qua key khác, sinh lỗi do thiếu tham số hoặc chuyển kiểu ra sao phụ thuộc resolver và version/configuration. Không suy luận `setIgnoreUnknownFields(false)` biến constructor binding thành một “strict schema validator” cho mọi key.

Tương tự, `DataBinder.setDeclarativeBinding(true)` (có từ Spring Framework 6.1) giúp giới hạn binding theo khai báo: constructor binding và property binding chỉ khi có cấu hình allowed fields. Nó không phải synonym của `setIgnoreUnknownFields(false)`.

Những mục tiêu khác nhau:

| Mục tiêu | Hướng phù hợp |
| --- | --- |
| Đối tượng đầu vào immutable | Constructor binding / record DTO thích hợp |
| Hạn chế thuộc tính writable được update | DTO chuyên biệt + `setAllowedFields` cho property binding |
| Phát hiện property name không writable | `setIgnoreUnknownFields(false)` trong property binding |
| Phát hiện tất cả keys ngoài API contract | Kiểm tra request/schema rõ ràng, bao gồm suppressed fields nếu cần |
| Kiểm tra tính hợp lệ của giá trị | Conversion + Bean Validation / validator nghiệp vụ |
| Bảo đảm quyền chỉnh dữ liệu | Authorization ở tầng nghiệp vụ |

## 10. @RequestBody JSON và các binder khác

Một sai lầm phổ biến là áp dụng `setIgnoreUnknownFields(false)` rồi mong JSON body có key lạ bị từ chối. Trong Spring MVC:

~~~java
@PostMapping("/profiles/json")
public String submitJson(@RequestBody CreateProfileRequest request) {
    return request.name();
}
~~~

Đoạn này là **snippet trong REST controller**, không phải ứng dụng độc lập. Dữ liệu JSON được chuyển thành object thông qua `HttpMessageConverter` (thường dùng Jackson). Cách xử lý unknown JSON properties chịu quy tắc của JSON mapper, annotation/configuration và phiên bản tương ứng, ví dụ chính sách unknown-property của Jackson. Nó **không được điều khiển tự động bởi `DataBinder.setIgnoreUnknownFields`** trên một `@ModelAttribute` khác.

Cần tách ba đường:

~~~text
?name=Lan&nickname=Lana hoặc form-urlencoded
    -> @ModelAttribute / WebDataBinder property binding
    -> setIgnoreUnknownFields có thể tham gia

{"name":"Lan","nickname":"Lana"} trong @RequestBody JSON
    -> HttpMessageConverter / JSON mapper
    -> Quy tắc unknown property của JSON mapper

new CreateProfileRequest(name, age) bằng constructor binding
    -> Resolver chọn tham số constructor
    -> setIgnoreUnknownFields không kiểm tra toàn bộ key
~~~

Trong ứng dụng Spring Boot, thuộc tính cấu hình `@ConfigurationProperties(ignoreUnknownFields = ...)` cũng thuộc **cơ chế bind cấu hình của Spring Boot**. Nó có tên tương tự nhưng không phải phương thức trên một MVC `WebDataBinder` và không nên được dùng làm bằng chứng cho hành vi của request form.

Test JSON và form/query riêng biệt, nhất là khi client có nhiều phiên bản hoặc hệ thống đang migration.

## 11. Chọn chính sách ignore hay reject theo yêu cầu

Không có một lựa chọn đúng tuyệt đối cho mọi endpoint. Hãy cân nhắc **hợp đồng input**, khả năng tương thích và cách người dùng khắc phục lỗi.

| Bối cảnh | Phương án thường hợp lý | Lý do |
| --- | --- | --- |
| Form HTML đang tiến hóa, client cũ có field thừa không quan trọng | Có thể giữ mặc định `true` | Tránh hỏng submit chỉ vì tham số phụ |
| API form-urlencoded có schema nghiêm, cần phát hiện lỗi đánh máy | Cân nhắc `false` + error handler được kiểm thử | Field lạ không biến mất âm thầm |
| Form cập nhật thông tin tài khoản | DTO riêng + `setAllowedFields` | Tránh gán các property không được phép dù chúng tồn tại |
| Muốn reject tất cả keys ngoài allow-list | Prevalidation request keys hoặc xử lý suppressed fields | Strict flag **không đủ** khi allow-list đã lọc keys |
| Form có nhiều nested objects tùy chọn | Test nested auto-grow và `ignoreInvalidFields` | Tránh bỏ lỡ dữ liệu quan trọng hoặc lỗi null path |
| API JSON | Cấu hình và test JSON deserializer | Không dùng MVC property-binding flag |
| Constructor-bound immutable DTO | Xác định contract và validation của constructor/resolver | Strict unknown không áp dụng trực tiếp |

Đối với public API, nếu một key bị từ chối, nên cung cấp thông báo dễ hiểu ở mức hợp đồng (“unknown input field”, “unsupported parameter”), tránh gửi nguyên stack trace hoặc chi tiết thuộc tính nội bộ. Nếu bỏ qua key, nên cân nhắc metrics hoặc test contract để lỗi gõ sai tên trường không âm thầm lọt qua trong quá trình phát triển.

**Quyết định thực tế:** dùng whitelist để xác định *được quyền bind gì*; dùng strict unknown khi muốn lỗi với *property name không writable* trong đường property binding và đã có chiến lược exception handling; dùng validation để xác định *giá trị có hợp lệ không*.

## 12. Lỗi do unknown field có tự động thành HTTP 400 không?

Không nên coi `setIgnoreUnknownFields(false)` là một bộ dựng HTTP response. API này thuộc tầng binding; exception được truyền lên sẽ trải qua argument resolver, MVC exception handling, handler riêng của ứng dụng và các cơ chế xử lý lỗi của framework.

Vì thế cần làm rõ:

1. Có phải endpoint đi qua `WebDataBinder.bind(...)` không?
2. Request đang dùng `@ModelAttribute` hay `@RequestBody`?
3. Unknown field có bị lọc trước bởi allowed fields không?
4. Khi bật strict, exception cụ thể nào xuất hiện ở phiên bản Spring đang chạy?
5. Controller có được gọi không? Có `@ControllerAdvice` riêng không?
6. Status và error body theo hợp đồng public API của sản phẩm là gì?

Đối với `NotWritablePropertyException` ném ra từ property accessor, đây là một ngoại lệ từ lớp xử lý property, không nên mặc định khẳng định nó luôn là một `FieldError`. `BindingResult` thường mô tả lỗi binding/validation mà binder có thể thu thập; lỗi property name không ghi được ở strict mode có thể ngắt quá trình trước khi controller đọc result.

Nếu muốn chủ động trả 400, có thể dùng `@ExceptionHandler` với phạm vi và loại exception được xác minh qua integration test, hoặc kiểm tra schema input trước binding. Không cần và không nên bao quát mọi `BeansException` rồi trả 400, vì một số lỗi có thể là bug của server, không phải request xấu.

## 13. Thử nghiệm hồi quy nên có

Tạo tập dữ liệu và assertion cho cùng một DTO trên đúng phiên bản Framework/Boot đang dùng. Bộ ca tối thiểu:

| Ca | Input/cấu hình | Kỳ vọng có thể kiểm chứng |
| --- | --- | --- |
| 1. Happy path | `name=Lan` | Target.name được gán |
| 2. Unknown mặc định | `name=Lan&nickname=Lana`, `true` | Binding hoàn tất; unknown bị bỏ qua; không tự sinh typeMismatch |
| 3. Unknown strict | Cùng input, `false` | Ngoại lệ property không writable được phát hiện |
| 4. Known invalid value | `age=abc` với `Integer age` | Lỗi conversion; **không** coi là unknown |
| 5. Read-only | `id=other`, chỉ có `getId()` | Kiểm tra hành vi property không ghi được |
| 6. Missing required | Không có `name`, cấu hình `setRequiredFields("name")` | Lỗi missing field theo binder |
| 7. Suppressed field | `setAllowedFields("name")`, gửi `role` | `getSuppressedFields()` ghi lại field bị chặn |
| 8. Strict + allow-list | `false` và whitelist, gửi unknown ngoài whitelist | Field có thể bị suppress trước khi strict check |
| 9. Nested null path | `address.city` nhưng `address` chưa tạo | Kết quả phụ thuộc auto-grow/ignoreInvalid |
| 10. MVC form | `@ModelAttribute` + `@InitBinder` | Kiểm tra controller invocation, exception/status/body |
| 11. JSON body | JSON có extra property | Kết quả đến từ JSON mapper, không dựa vào flag property binding |
| 12. Security | Field có setter nhưng client không được phép sửa | DTO/allowed fields chặn cập nhật; nghiệp vụ vẫn kiểm tra quyền |

Khi test strict, ngoài việc assert loại exception, cần assert **bất biến nghiệp vụ**: service ghi database không được chạy nếu request bị từ chối. Đừng chỉ kiểm tra `BindingResult.hasErrors()`, vì unknown-property exception có thể xảy ra trước đường đi đó.

Ví dụ unit assertion (minh họa trong JUnit Jupiter với dependency Spring đầy đủ):

~~~java
assertThrows(NotWritablePropertyException.class,
        () -> binder.bind(values));
~~~

Đoạn này giả định `binder` đã được cấu hình `setIgnoreUnknownFields(false)`, `values` chứa field không writable, và import `org.junit.jupiter.api.Assertions.assertThrows`. Với `setAllowedFields` lọc field đó trước, assertion phải thay đổi: không nên ép một ngoại lệ không còn xảy ra.

### Kiểm thử ở level DataBinder trước khi dùng MockMvc

Ưu tiên hai lớp test:

- **Unit test `DataBinder`:** nhanh, cô lập quy tắc ignoreUnknown/allowedFields/suppressed/invalid/typeMismatch. Bạn có thể kiểm tra ngay class exception và target state.
- **MockMvc hoặc integration test MVC:** xác minh `@InitBinder` được áp dụng đúng model name, các tham số request thực tế được chuyển thành `PropertyValues` như mong đợi, và error handler trả status/body theo hợp đồng.

Nếu test đơn vị pass nhưng MockMvc không ném exception khi gửi JSON, hãy kiểm tra input path: JSON deserialization không đi qua flag của property binder.

## 14. Checklist chẩn đoán lỗi thường gặp

### “Đổi tên input nhưng server vẫn trả thành công”

- Kiểm tra `<input name="...">` hoặc tên query param thực tế.
- Kiểm tra getter/setter, JavaBeans naming và field access mode.
- Kiểm tra `isIgnoreUnknownFields()`; mặc định `true` có thể bỏ qua lỗi gõ sai.
- Kiểm tra DTO được binder dùng có đúng class/version không.
- Nếu yêu cầu strict, thêm test với unknown name và quan sát exception/HTTP behavior.

### “Bật false rồi không thấy FieldError trong BindingResult”

- `NotWritablePropertyException` có thể được ném ngay trong `bind`.
- Kiểm tra stack trace và entry point property accessor.
- Không trông chờ `BindingResult` luôn gom mọi lỗi fatal.
- Nếu API cần form error hiển thị thay vì exception, thiết kế lớp chuyển lỗi phù hợp, không nuốt exception toàn cục.

### “Bật false nhưng field lạ vẫn bị bỏ qua”

- Có `setAllowedFields` hay `setDisallowedFields` đã lọc field trước khi ghi không?
- Controller có dùng constructor binding/JSON thay vì property binding không?
- `@InitBinder` có áp dụng cho đúng model attribute name và controller scope không?
- Binder có đang dùng cùng cấu hình/instance mà bạn kiểm tra không?
- Property name có thực sự unknown, hay có setter/field writable tương ứng?

### “Một nested field không bind được”

- Xác minh đúng path `address.city` và object graph.
- Kiểm tra null intermediate object, khả năng khởi tạo nested type và `setAutoGrowNestedPaths`.
- Phân biệt `ignoreInvalidFields` với `ignoreUnknownFields`.
- Kiểm tra loại exception cụ thể thay vì bật cả hai flag để che lỗi.

### “Bật strict có phải biện pháp chống mass assignment không?”

- Không đủ: property nguy hiểm nhưng có setter vẫn là property **đã biết**.
- Dùng input DTO riêng, whitelist `allowedFields`, authorization và invariant check trong service.
- Nếu contract không cho extra keys, cần kiểm tra tất cả key được nhận ở request boundary hoặc theo dõi suppressed fields.
- Test một field được biết nhưng không được phép chỉnh, không chỉ một field unknown.

### “Controller trả 500 thay vì 400”

- Xác minh exception thực tế và nơi nó được ném.
- Đừng suy luận HTTP mapping từ API `setIgnoreUnknownFields`.
- Thiết kế error contract nhất quán, dùng exception handler hẹp hoặc request validation.
- Tránh vô tình chuyển lỗi lập trình nội bộ thành “bad request”.
- Test lại status/body với Spring MVC/Boot và cấu hình thực tế.

## 15. Tự kiểm tra kiến thức

1. **Mặc định của `setIgnoreUnknownFields` là gì?** — `true`, unknown property trong property binding thường bị bỏ qua.
2. **`false` thường gây lỗi gì nếu tên property không writable?** — Có thể là `NotWritablePropertyException`.
3. **Unknown field có luôn tạo `FieldError` không?** — Không; mặc định có thể bị bỏ qua và strict có thể ném exception trực tiếp.
4. **`setAllowedFields` với `setIgnoreUnknownFields(false)` có tự từ chối mọi field ngoài whitelist bằng exception không?** — Không. Field bị chặn thường được suppress trước khi property accessor chạy.
5. **`getSuppressedFields()` ghi gì?** — Các field bị loại khỏi property binding theo quy tắc allow/disallow; không tự biểu diễn mọi unknown field bị bỏ qua.
6. **Input `age=abc` vào `Integer age` là unknown không?** — Không, đó là lỗi chuyển kiểu.
7. **Thiếu `age` trong request có được `setIgnoreUnknownFields(false)` coi là lỗi không?** — Không chỉ vì thiếu; phải có required/validation rule nếu cần.
8. **`setIgnoreInvalidFields` kiểm tra gì?** — Các field/path có thể tồn tại nhưng không truy cập được, ví dụ nested path qua giá trị null không thể tự tạo.
9. **Flag này có tự kiểm soát unknown JSON keys trong `@RequestBody` không?** — Không; JSON mapper có cơ chế riêng.
10. **Một DTO có writable property `role` thì strict unknown có chặn `role=ADMIN` không?** — Không chỉ nhờ strict; dùng DTO/allowed fields/authorization.
11. **Vì sao phải test MockMvc sau unit test binder?** — Vì đường đi request, tên model attribute, handler và status HTTP phụ thuộc cấu hình MVC.
12. **Có nên cho phép tiếp tục ghi database sau khi binder strict ném exception?** — Không; request không hợp lệ phải được xử lý ở đúng ranh giới trước khi thực hiện nghiệp vụ.

## 16. Tài liệu chính thức để đối chiếu

- [Spring Framework – DataBinder Javadoc (6.1.0)](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html), gồm `setIgnoreUnknownFields`, `setIgnoreInvalidFields`, `setAllowedFields` và `bind`.
- [Spring Framework – DataBinder Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html), đối chiếu API trên nhánh ứng dụng.
- [Spring Framework – PropertyAccessor Javadoc (6.2.6)](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/beans/PropertyAccessor.html), hợp đồng `setPropertyValues` và các ngoại lệ.
- [Spring Framework – NotWritablePropertyException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/NotWritablePropertyException.html).
- [Spring Framework – BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BindingResult.html).
- [Spring Framework – MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html), định hướng sử dụng DTO và allowed fields.
- [Spring Framework – @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html), phạm vi cấu hình binder.
- [Spring Framework – Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html), cơ chế binder, property paths và validation.
- [Spring Framework 5.3.36 – DataBinder](https://docs.spring.io/spring-framework/docs/5.3.36/javadoc-api/org/springframework/validation/DataBinder.html), tham khảo hành vi trước thế hệ Spring 6.

**Điểm cần nhớ:** `setIgnoreUnknownFields(true)` giúp property binding bỏ qua tên thuộc tính không ghi được; `false` giúp nhận biết lỗi tên trong chính đường binding đó. Quy tắc này **khác** chọn field được phép gán (`setAllowedFields`), khác lỗi chuyển kiểu và khác xác thực giá trị. Hãy quyết định chính sách theo hợp đồng input, xử lý ngoại lệ rõ ràng và kiểm thử cả request thực tế trước khi phụ thuộc vào strict mode.
