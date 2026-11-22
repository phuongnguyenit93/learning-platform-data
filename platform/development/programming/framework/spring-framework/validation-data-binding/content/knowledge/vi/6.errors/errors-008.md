# BeanPropertyBindingResult, DirectFieldBindingResult và MapBindingResult trong Spring Framework

Khi Spring bind dữ liệu hoặc kiểm tra một đối tượng, cần một nơi lưu **kết quả thành công hay thất bại của quá trình binding/validation**. Giao diện `org.springframework.validation.BindingResult` đảm nhiệm vai trò đó: chứa lỗi gắn với từng trường, lỗi toàn đối tượng, giá trị bị từ chối, mã lỗi và thông tin đối tượng đích. Ba implementation thường gặp là **`BeanPropertyBindingResult`**, **`DirectFieldBindingResult`** và **`MapBindingResult`**.

Điểm khác biệt cốt lõi: **chúng đọc giá trị trường của target theo cách nào?** `BeanPropertyBindingResult` dùng JavaBean properties (getter/setter), `DirectFieldBindingResult` dùng field của object trực tiếp, còn `MapBindingResult` đọc từ một `Map` theo key. Hiểu khác biệt này giúp chọn đúng error holder, xử lý lỗi binding ổn định và tránh suy luận rằng annotation hay `BindingResult` tự động biến dữ liệu đầu vào thành đối tượng hợp lệ.

## 1. `Errors`, `BindingResult` và quá trình xử lý

Một luồng xử lý khái quát:

~~~text
Input (HTTP form, request parameters, cấu hình, dữ liệu nội bộ)
                |
                v
       DataBinder / cách bind riêng
                |
                +-- chuyển kiểu hoặc gán property thất bại
                |                 |
                |                 v
                |             FieldError
                v
         Đối tượng đích
                |
                v
      Validator.validate(target, errors)
                |
                +-- vi phạm quy tắc -> FieldError / ObjectError
                |
                v
           BindingResult
                |
                +-- hasErrors(), getFieldErrors(), getGlobalErrors()
                +-- getFieldValue(), getRawFieldValue()
                +-- getModel(), getSuppressedFields()
~~~

Phân biệt hai giao diện:

- `Errors` là hợp đồng báo và truy vấn lỗi: `reject(...)`, `rejectValue(...)`, `hasErrors()`, `getFieldErrors()`, `getGlobalErrors()`, `getErrorCount()`, quản lý nested path...
- `BindingResult` mở rộng `Errors` với ngữ cảnh binding: `getTarget()`, `getRawFieldValue()`, `getFieldType()`, `getModel()`, `getSuppressedFields()`, ghi nhận giá trị hoặc field bị loại...
- `FieldError` biểu diễn lỗi trên một field; `ObjectError` biểu diễn lỗi chung. `FieldError` kế thừa `ObjectError` và có thêm tên field, rejected value và cờ `bindingFailure`.

**Lưu ý:** `new BeanPropertyBindingResult(target, "form")` chỉ **tạo nơi chứa lỗi**. Nó không tự bind request, gọi validator, ghi vào target hay tự quét các annotation `@NotBlank`, `@Min`. `DataBinder.bind(...)` thực hiện binding và có thể ghi binding errors; `DataBinder.validate()` hoặc một lần gọi `Validator.validate(...)` riêng mới tạo validation errors tương ứng.

`objectName` là tên logic của target, ví dụ `"registrationForm"`, dùng trong phân giải message code và model key. Nó không phải tên class Java bắt buộc và không tự suy ra URL HTTP.

## 2. So sánh ba implementation

| Tiêu chí | `BeanPropertyBindingResult` | `DirectFieldBindingResult` | `MapBindingResult` |
| --- | --- | --- | --- |
| Target | Java object có thuộc tính theo JavaBean | Java object có instance fields | `Map<?, ?>` |
| Cách đọc giá trị | `BeanWrapper`: JavaBean property access, thường qua getter | `DirectFieldAccessor`: truy cập trực tiếp field | `map.get(fieldName)` |
| Khi bind bằng `DataBinder` | Chế độ property access mặc định | Bật `initDirectFieldAccess()` trước binding | Thường tạo trực tiếp khi tự bind/validate Map |
| Nested field | Hỗ trợ property path như `address.city` | Hỗ trợ nested field path (Spring 4.1+) | Key là chuỗi field; không tự duyệt một object graph |
| Cấu hình auto-grow | Constructor tùy chọn có `autoGrowNestedPaths`, `autoGrowCollectionLimit` | Constructor tùy chọn có `autoGrowNestedPaths` | Không có accessor auto-grow của JavaBean |
| Trường hợp phù hợp | DTO/form mutable có getter/setter | Object chủ động expose field mà không theo JavaBean setter | Bản ghi thuộc tính động, form dựa trên Map |
| Cần chú ý | Getter/setter và conversion hợp lệ | Đụng đến field trực tiếp, tránh giả định có setter | Key, kiểu value và quy tắc validation phải được quản lý rõ |

Cả ba đều triển khai `BindingResult` nên code xử lý chung có thể nhận tham số kiểu interface:

~~~java
static void printErrors(BindingResult result) {
    for (FieldError error : result.getFieldErrors()) {
        System.out.printf("%s: %s%n",
                error.getField(), error.getDefaultMessage());
    }
}
~~~

Đoạn trên là một **phương thức minh họa** cần được đặt trong một class và import `BindingResult`, `FieldError`. Chính cách **truy xuất target** khác nhau mới là điều phải chọn theo cấu trúc dữ liệu.

## 3. `BeanPropertyBindingResult`: giá trị qua JavaBean property

Khai báo thông dụng:

~~~java
BindingResult result =
        new BeanPropertyBindingResult(customerForm, "customerForm");
~~~

Constructor đầy đủ của nhánh Spring Framework 6.x:

~~~java
new BeanPropertyBindingResult(
        target, objectName, autoGrowNestedPaths, autoGrowCollectionLimit);
~~~

Lớp này kế thừa `AbstractPropertyBindingResult`. Nó dùng `BeanWrapper` để đọc thuộc tính theo tên như `name`, `address.city`. Với property thông thường, getter trả lại giá trị hiện tại còn setter cho phép `DataBinder` ghi giá trị. Tên property xuất phát từ JavaBeans convention, không phải mọi private field đều mặc nhiên là property đọc/ghi được.

Ví dụ:

~~~java
public class CustomerForm {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Với class này, `getRawFieldValue("name")` đọc giá trị qua cơ chế property access. Nếu đổi tên field thành `internalName` nhưng getter vẫn là `getName()`, property logic của JavaBean vẫn là `name`. Nếu chỉ có field private `name` mà không có getter, property access có thể không đọc được nó; lúc đó `DirectFieldBindingResult` có thể phù hợp hơn.

**Nested path và auto-grow:** `address.city` chỉ dùng được khi object graph và accessor đáp ứng điều kiện truy cập. Nếu bật auto-grow, Spring có thể tạo đối tượng lồng nhau hay mở rộng collection trong giới hạn cấu hình, nhưng cần constructor, kiểu mutable và ngữ cảnh phù hợp. Không nên xem auto-grow là cơ chế tạo mọi loại object bất kỳ; với untrusted input cần giới hạn allowed fields và độ sâu/collection size theo ứng dụng.

## 4. `DirectFieldBindingResult`: đọc trực tiếp instance field

Khai báo:

~~~java
BindingResult result =
        new DirectFieldBindingResult(inventoryRow, "inventoryRow");
~~~

Constructor tùy chọn:

~~~java
new DirectFieldBindingResult(
        target, objectName, autoGrowNestedPaths);
~~~

Lớp này cũng kế thừa `AbstractPropertyBindingResult` nhưng dùng `DirectFieldAccessor` thay cho `BeanWrapper`. Nó đọc field dựa trên tên khai báo, kể cả khi không có JavaBean getter:

~~~java
public class InventoryRow {
    private String sku;

    public InventoryRow(String sku) {
        this.sku = sku;
    }
}
~~~

Lệnh `new DirectFieldBindingResult(row, "row").getRawFieldValue("sku")` đọc giá trị của field `sku`. Trong khi đó `BeanPropertyBindingResult` không thể tự coi private field thiếu getter là property đọc được. Direct field access có hỗ trợ nested field path trong Spring hiện đại, nhưng hành vi vẫn dựa trên **trường dữ liệu**, không dùng getter làm nguồn giá trị.

Không nên hiểu “direct field” là lời khuyên bind trực tiếp mọi request lên domain entity:

- Reflective field access có thể bỏ qua kiểm soát trong setter nếu ứng dụng trông chờ setter thực thi bất biến.
- Object immutable, record và field `final` không phải đối tượng thích hợp cho việc tùy ý ghi field bằng binder; nên chọn constructor binding hoặc DTO phù hợp.
- Cần xác định rõ trường nào được phép bind, tránh chỉnh nhầm `role`, `ownerId`, `status` hay dữ liệu nội bộ.
- Tương tự bean property, `DirectFieldBindingResult` chỉ theo dõi lỗi; một target không tự được validate khi constructor của result chạy.

## 5. `MapBindingResult`: trường là các key trong Map

Ví dụ:

~~~java
Map<String, Object> settings = new HashMap<>();
settings.put("region", "apac");

BindingResult result = new MapBindingResult(settings, "settings");
~~~

Constructor có hai tham số `Map<?, ?> target` và `String objectName`. `getTarget()` trả về target Map ở dạng Object, còn `getTargetMap()` trả đúng `Map<?, ?>`.

Khác với hai lớp trên, `MapBindingResult` **không tạo BeanWrapper hoặc DirectFieldAccessor**. Trong nhánh Spring 6.x, cách lấy giá trị field về bản chất là:

~~~java
return targetMap.get(field);
~~~

Đây là mô tả cơ chế nội bộ, không phải một phương thức public độc lập để gọi. Vì vậy:

- Key `"region"` lấy giá trị của entry `"region"`.
- Key `"user.email"` chỉ được lấy nếu Map thực sự có **key chuỗi `"user.email"`**; không tự lần theo một Map con nằm dưới key `"user"`.
- Nếu key không tồn tại, giá trị đọc thường là `null`; cần phân biệt key vắng mặt với key có value `null` nếu nghiệp vụ yêu cầu.
- Các value có thể mang kiểu Java không đồng nhất, nên không thể mặc định một property type ổn định như bean.
- Một Map chứa dữ liệu động vẫn cần **schema/whitelist** hợp lệ và validator tương ứng; map không mặc định an toàn hay hợp lệ.

`MapBindingResult` là lựa chọn tốt khi đã có quá trình nhận, chuyển đổi và đặt dữ liệu vào Map rồi cần một đối tượng `Errors/BindingResult` để validator bổ sung lỗi. Nó **không tự biến Map thành form DTO**, cũng không tự được Spring MVC chọn chỉ vì controller nhận `Map<String, String>`.

## 6. Ví dụ Java 17+ đầy đủ cho cả ba lớp

Ví dụ sau chạy độc lập như một ứng dụng Java dùng dependency Spring Framework, **không cần khởi động Spring Boot hoặc HTTP server**. Nó minh họa tạo result, đăng ký lỗi field, chọn kiểu access của `DataBinder`, và lỗi type mismatch.

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'binding-result-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.BindingResultsDemo'
}
~~~

Tạo file `src/main/java/example/BindingResultsDemo.java`:

~~~java
package example;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.DirectFieldBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.MapBindingResult;

public class BindingResultsDemo {

    public static class BeanForm {
        private String name;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

    public static class FieldForm {
        private String code;
    }

    public static class AgeForm {
        private Integer age;

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }
    }

    public static void main(String[] args) {
        // 1. Tạo nơi lưu lỗi; không tự thực hiện binding.
        BeanForm beanTarget = new BeanForm();
        beanTarget.setName("");

        BindingResult beanResult =
                new BeanPropertyBindingResult(beanTarget, "account");
        beanResult.rejectValue("name", "required", "Name is required");

        FieldForm fieldTarget = new FieldForm();
        fieldTarget.code = "";

        BindingResult directResult =
                new DirectFieldBindingResult(fieldTarget, "fieldAccount");
        directResult.rejectValue("code", "required", "Code is required");

        Map<String, Object> mapTarget = new LinkedHashMap<>();
        mapTarget.put("region", "");

        BindingResult mapResult =
                new MapBindingResult(mapTarget, "settings");
        mapResult.rejectValue("region", "required", "Region is required");

        System.out.println("bean field: "
                + beanResult.getFieldError("name").getField());
        System.out.println("direct field: "
                + directResult.getFieldError("code").getField());
        System.out.println("map field: "
                + mapResult.getFieldError("region").getField());
        System.out.println("errors: "
                + beanResult.getErrorCount() + "/"
                + directResult.getErrorCount() + "/"
                + mapResult.getErrorCount());

        String modelKey = BindingResult.MODEL_KEY_PREFIX + "account";
        System.out.println("model entry: "
                + beanResult.getModel().containsKey(modelKey));

        // 2. DataBinder chọn BindingResult theo cách truy cập.
        BeanForm boundBean = new BeanForm();
        DataBinder beanBinder = new DataBinder(boundBean, "bean");
        beanBinder.setAllowedFields("name");
        beanBinder.bind(new MutablePropertyValues(Map.of("name", "Mai")));

        FieldForm boundField = new FieldForm();
        DataBinder fieldBinder = new DataBinder(boundField, "field");
        fieldBinder.initDirectFieldAccess();
        fieldBinder.setAllowedFields("code");
        fieldBinder.bind(new MutablePropertyValues(Map.of("code", "A01")));

        System.out.println("binder types: "
                + beanBinder.getBindingResult().getClass().getSimpleName()
                + "/"
                + fieldBinder.getBindingResult().getClass().getSimpleName());
        System.out.println("bound values: "
                + boundBean.getName() + "/" + boundField.code);

        // 3. Lỗi chuyển kiểu được ghi lại trong BindingResult.
        AgeForm ageForm = new AgeForm();
        DataBinder ageBinder = new DataBinder(ageForm, "ageForm");
        ageBinder.setAllowedFields("age");
        ageBinder.bind(new MutablePropertyValues(Map.of("age", "oops")));

        FieldError ageError =
                ageBinder.getBindingResult().getFieldError("age");

        System.out.println("type mismatch: "
                + ageError.getCode() + "/" + ageError.isBindingFailure());
        System.out.println("rejected: " + ageError.getRejectedValue());
    }
}
~~~

Chạy từ thư mục gốc có Gradle Wrapper:

~~~bash
./gradlew run
~~~

Hoặc dùng Gradle đã cài trên máy:

~~~bash
gradle run
~~~

Trên Windows với Gradle Wrapper:

~~~powershell
.\gradlew.bat run
~~~

Bỏ các dòng log khởi động Gradle, stdout của chương trình là:

~~~text
bean field: name
direct field: code
map field: region
errors: 1/1/1
model entry: true
binder types: BeanPropertyBindingResult/DirectFieldBindingResult
bound values: Mai/A01
type mismatch: typeMismatch/true
rejected: oops
~~~

**Vì sao kết quả này có ý nghĩa?**

1. Ba result đều nhận `rejectValue(...)` và cung cấp `getFieldError(...)` dù target có cấu trúc khác nhau.
2. `getModel()` của bean result chứa entry có key `BindingResult.MODEL_KEY_PREFIX + "account"` (tức `org.springframework.validation.BindingResult.account`), giúp view dùng dữ liệu và thông tin lỗi đúng object.
3. `DataBinder` dùng `BeanPropertyBindingResult` khi bind qua JavaBean property. Gọi `initDirectFieldAccess()` **trước khi binding** chuyển binder sang `DirectFieldBindingResult`.
4. Giá trị `"oops"` không chuyển được sang `Integer` nên Spring ghi `FieldError` với error code cơ sở `typeMismatch`, cờ `bindingFailure=true` và rejected value là `"oops"`. Giá trị `age` trong đối tượng `AgeForm` không được gán thành công.

Ví dụ không có Map binding qua `DataBinder` vì trong trường hợp này `MapBindingResult` được tạo trực tiếp để làm bộ chứa lỗi cho một Map đã có giá trị. Nếu muốn bind Map từ request thật, phải thiết kế riêng luồng bind và kiểm soát key/value phù hợp.

## 7. Tạo lỗi validation khác gì lỗi binding?

Một `BindingResult` có thể chứa cả hai loại lỗi. Điều này quan trọng vì client có thể cần phân biệt “không thể đọc/đổi kiểu dữ liệu” và “dữ liệu đọc được nhưng vi phạm quy tắc”.

### Lỗi binding

Ví dụ client gửi `age=oops`, trong khi `AgeForm.age` là `Integer`. `DataBinder` không chuyển chuỗi thành số được; `DefaultBindingErrorProcessor` thường ghi một `FieldError` mã `typeMismatch` và `bindingFailure=true`.

Khi xảy ra lỗi này:

- Target có thể giữ giá trị ban đầu hoặc `null` do việc gán không thành công.
- `FieldError.getRejectedValue()` trả lại dữ liệu đầu vào đã bị từ chối, hữu ích để hiển thị lỗi form có kiểm soát.
- `getFieldValue("age")` có thể trả rejected value để render form, còn `getRawFieldValue("age")` phản ánh giá trị hiện tại trên target. Vì thế hai phương thức **không luôn giống nhau**.
- Không hiển thị raw/rejected value của mật khẩu, token hoặc dữ liệu nhạy cảm trong log hay response.

### Lỗi validation

Nếu `age=15` được chuyển thành `Integer` thành công, validation vẫn có thể báo lỗi “phải từ 18 trở lên”. Một `org.springframework.validation.Validator` có thể tự ghi lỗi:

~~~java
public final class AgeValidator
        implements org.springframework.validation.Validator {

    @Override
    public boolean supports(Class<?> type) {
        return BindingResultsDemo.AgeForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target,
                         org.springframework.validation.Errors errors) {
        BindingResultsDemo.AgeForm form =
                (BindingResultsDemo.AgeForm) target;

        Integer age = form.getAge();
        if (age == null || age < 18) {
            errors.rejectValue(
                    "age", "age.tooYoung", "Age must be at least 18");
        }
    }
}
~~~

Đoạn code này là **một class bổ sung** trong package `example`, đặt ở file `AgeValidator.java`; nó sử dụng `BindingResultsDemo.AgeForm` của ví dụ hoàn chỉnh. Có thể dùng:

~~~java
AgeForm ageForm = new AgeForm();
ageForm.setAge(15);

DataBinder binder = new DataBinder(ageForm, "ageForm");
binder.addValidators(new AgeValidator());
binder.validate();

BindingResult result = binder.getBindingResult();
System.out.println(result.getFieldError("age").getCode());
~~~

Đây là **đoạn thêm vào một phương thức của class có thể tham chiếu `AgeForm`**, không phải một chương trình Java độc lập. Output của dòng `println` là:

~~~text
age.tooYoung
~~~

`Validator.validate(...)` và Bean Validation của Jakarta là các cơ chế tích hợp nhưng cần phân biệt. Nếu dùng constraint như `@Min(18)` cùng `@Valid`, validator/provider phù hợp phải được cấu hình; bản thân `BindingResult` không tự tìm và thực thi annotation. Bài này tập trung vào cấu trúc error holder và cách truy cập giá trị.

## 8. API tra cứu lỗi cần dùng đúng

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `hasErrors()`, `getErrorCount()` | Có lỗi và tổng số lỗi | Có cả global và field errors |
| `getFieldErrors()`, `getFieldError("field")` | Danh sách hoặc lỗi đầu tiên của field | Một field có thể có nhiều lỗi |
| `getGlobalErrors()`, `getGlobalError()` | Lỗi chung cho cả object | Dùng khi quan hệ nhiều trường không hợp lệ |
| `reject("code", "message")` | Đăng ký global error | Không gắn vào một field cụ thể |
| `rejectValue("field", "code", "message")` | Đăng ký field error | Field phải có ý nghĩa theo kiểu target |
| `getRawFieldValue("field")` | Giá trị thực hiện có ở target | Khác rejected value khi binding thất bại |
| `getFieldValue("field")` | Giá trị thích hợp cho hiển thị form | Có thể ưu tiên rejected value |
| `getFieldType("field")` | Kiểu field nếu xác định được | Map value null/không có key có thể thiếu thông tin |
| `getModel()` | Map gồm target và BindingResult | Mỗi lần gọi tạo Map mới |
| `getSuppressedFields()` | Những field bị loại trong binding | Không mặc định đồng nghĩa lỗi validation |
| `getObjectName()`, `getTarget()` | Tên logic và target gốc | Hữu ích khi xử lý nhiều form |
| `resolveMessageCodes(...)` | Danh sách message code theo quy tắc | Hỗ trợ i18n và thông báo nhất quán |

Ví dụ, `result.reject("dateRange.invalid", "End date must not precede start date")` dùng global error nếu lỗi phụ thuộc nhiều field. Còn `result.rejectValue("age", "age.tooYoung", "Age must be at least 18")` tạo field error.

**Message code** như `required.account.name`, `required.name` và `required` thường xuất hiện khi `DefaultMessageCodesResolver` phân giải mã theo object, field và kiểu. Code cụ thể trong `FieldError.getCodes()` phụ thuộc resolver và ngữ cảnh, vì vậy không hard-code số lượng hoặc thứ tự thành hợp đồng HTTP. `getCode()` là mã cơ sở; `getDefaultMessage()` là thông điệp fallback.

### Nested path

Với JavaBean hoặc direct field chứa đối tượng lồng nhau, có thể ghi lỗi bằng tên đầy đủ như `"address.city"` hoặc sử dụng `pushNestedPath("address")` rồi `rejectValue("city", ...)`, sau đó `popNestedPath()`. Cần bảo đảm path tồn tại và accessor xử lý được đối tượng đích.

Với `MapBindingResult`, `"address.city"` là **tên key chuỗi đầy đủ** khi trích giá trị; không được suy luận rằng `Map.of("address", Map.of("city", ...))` sẽ tự được duyệt giống một JavaBean.

## 9. Cách dùng trong Spring MVC và lỗi thường gặp

Với MVC form, Spring có thể tạo binder và cung cấp `BindingResult` cho controller. Mẫu thông dụng:

~~~java
@PostMapping("/accounts")
public String submit(
        @Valid @ModelAttribute("account") AccountForm account,
        BindingResult result) {

    if (result.hasErrors()) {
        return "account-form";
    }
    return "account-created";
}
~~~

Đây là **minh họa chữ ký controller**, giả định `AccountForm` có class và cấu hình view tương ứng. Với tham số form, `BindingResult` phải đứng **ngay sau** tham số được bind/validate. Ví dụ không tự định nghĩa error handler hay chế độ view. Nếu dùng `@RequestBody` JSON, conversion thường qua Jackson, có ngoại lệ xử lý khác; đừng mặc định MVC sử dụng ba implementation giống nhau cho mọi loại input.

Nếu muốn MVC bind qua field thay vì property cho một model attribute cụ thể, có thể cấu hình binder ở thời điểm phù hợp:

~~~java
@InitBinder("account")
void useFieldAccess(WebDataBinder binder) {
    binder.initDirectFieldAccess();
}
~~~

Đoạn code này giả định đang nằm trong controller hoặc `@ControllerAdvice` có imports tương ứng. Hãy cân nhắc trước khi bật: direct field access thay đổi đường ghi dữ liệu, có thể bỏ qua setter, nên phải xác định rõ ownership, allowed fields và đặc điểm domain model.

Với `DataBinder` tự tạo, nên:

1. Đặt object name mô tả đúng target.
2. Chọn JavaBean hoặc direct field access **trước khi bind**.
3. Dùng `setAllowedFields(...)` hoặc chiến lược binding khai báo rõ để chống mass assignment khi nguồn input không tin cậy.
4. Gọi `bind(...)` trước, rồi `validate()` nếu muốn chạy các validator đã gắn.
5. Đọc `getBindingResult()` để xử lý lỗi; không đoán rằng không có exception thì toàn bộ field đã hợp lệ.
6. Không dùng một result mutable làm singleton chia sẻ giữa request hoặc thread.

### Những ngộ nhận cần tránh

- **“Cả ba lớp tự động bind dữ liệu.”** Sai: chúng giữ và đánh giá lỗi; `DataBinder` hoặc cơ chế khác mới thực hiện binding.
- **“DirectFieldBindingResult là BeanPropertyBindingResult nhanh hơn.”** Không nên chọn theo phỏng đoán hiệu năng. Chúng khác nhau ở mô hình truy cập, hành vi getter/setter và khả năng bảo toàn bất biến.
- **“MapBindingResult tự traverse nested Map.”** Sai: đọc theo key từ Map.
- **“`getFieldValue` luôn là giá trị trên object.”** Sai khi có rejected value từ lỗi binding.
- **“`rejectValue` tự chứng minh mọi constraint đã được kiểm tra.”** Sai: nó chỉ ghi một lỗi do code/validator quyết định.
- **“`hasErrors() == false` nghĩa là request an toàn.”** Chỉ đúng là chưa ghi nhận lỗi trong result này; vẫn cần kiểm tra phân quyền, nghiệp vụ, giao dịch và ràng buộc dữ liệu.
- **“Có `BindingResult` thì không cần trả HTTP error chuẩn.”** Trong controller, ứng dụng vẫn cần quyết định response/status phù hợp, không để lỗi lộ thông tin nội bộ.
- **“Cứ dùng Map cho mọi request động.”** Map làm mất schema rõ ràng, dễ khó kiểm soát field và type; DTO có kiểu thường phù hợp hơn khi hợp đồng ổn định.

## 10. Bài tập tự kiểm tra

1. Một class có `private String nickname` nhưng không có getter. Vì sao `BeanPropertyBindingResult` có thể không đọc được `nickname`, trong khi `DirectFieldBindingResult` đọc được?
2. Khi `DataBinder` chuyển `"oops"` sang `Integer` thất bại, vì sao `getFieldValue("age")` có thể khác `getRawFieldValue("age")`?
3. Map có entry `"user" -> Map.of("email", "a@example.com")`. `MapBindingResult.getRawFieldValue("user.email")` có tự trả email không? Cần thiết kế key/schema thế nào?
4. Cần gọi gì để thực thi `Validator` trên target và lưu validation errors sau binding?
5. Khi nào nên dùng global error thay vì field error?
6. Vì sao `BindingResult` trong form controller phải nằm ngay sau đối tượng `@ModelAttribute` được bind?
7. Làm sao bảo vệ các field không được phép sửa khi dùng direct field access?

**Ghi nhớ:** Ba implementation dùng chung giao diện `BindingResult` nên cùng có khả năng lưu lỗi, mã lỗi, rejected value và model metadata. Chọn `BeanPropertyBindingResult` cho **JavaBean properties**, `DirectFieldBindingResult` cho **instance fields**, và `MapBindingResult` cho **Map entries**. Binding/validation là các bước riêng; dùng đúng `DataBinder`/`Validator` rồi đọc result ở ranh giới phù hợp.

### Tài liệu tham khảo

- Spring Framework 6.2 — [BeanPropertyBindingResult API](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/validation/BeanPropertyBindingResult.html).
- Spring Framework 6.2 — [DirectFieldBindingResult API](https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/validation/DirectFieldBindingResult.html).
- Spring Framework 6.2 — [MapBindingResult API](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/validation/MapBindingResult.html).
- Spring Framework — [Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html).
- Spring Framework — [Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).
