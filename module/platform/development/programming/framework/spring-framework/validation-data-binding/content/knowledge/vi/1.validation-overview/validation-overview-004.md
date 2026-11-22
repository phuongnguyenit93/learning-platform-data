# Bản đồ thuật ngữ: target, property, binder, converter và validator

Trong Spring Framework, **data binding** là quá trình đưa dữ liệu đầu vào (thường là chuỗi từ form/request) vào một đối tượng Java có kiểu xác định. Muốn đọc đúng mã nguồn và xử lý lỗi chính xác, cần phân biệt năm vai trò: **target** là đối tượng nhận dữ liệu; **property** là vị trí nhận dữ liệu; **binder** điều phối gán giá trị; **converter** chuyển kiểu; **validator** kiểm tra quy tắc hợp lệ. `BindingResult` lưu lỗi phát sinh từ việc bind/chuyển kiểu và từ validation.

## 1. Sơ đồ tổng thể và một ví dụ xuyên suốt

Giả sử form đăng ký gửi các cặp tên–giá trị:

```text
name  = "An"
age   = "16"
level = "advanced"
```

Đối tượng dự kiến nhận là `SignupForm`, với `name: String`, `age: int` và `level: Level`. Luồng khái niệm:

```text
Input (tên property -> giá trị gốc)
                |
                v
       DataBinder / WebDataBinder ----------------------+
                |                                      |
      tìm property trên target                         |
                |                                      |
       chuyển kiểu khi cần                             |
                |                                      |
    ConversionService / Converter / Formatter          |
                |                                      |
                v                                      |
        gán vào target                                 |
                |                                      |
      gọi validate() hoặc @Valid/@Validated            |
                |                                      |
       Validator / Bean Validation                     |
                |                                      |
                v                                      v
       target chứa giá trị đã bind            BindingResult chứa lỗi
```

Đây là **bản đồ trách nhiệm**, không phải khẳng định mọi yêu cầu luôn chạy tuần tự đúng từng hộp. Chẳng hạn, việc validation phải được yêu cầu/kích hoạt; việc chuyển kiểu có thể không cần nếu đầu vào đã đúng kiểu; lỗi chuyển kiểu có thể khiến một property không được gán. Trong Spring MVC, việc tạo/lấy target có thể xảy ra bằng constructor binding hoặc property binding tùy trường hợp.

| Thuật ngữ | Bản chất | Ví dụ với form | Câu hỏi nó giải quyết |
| --- | --- | --- | --- |
| **Target** | Đối tượng Java nhận kết quả binding | Một instance của `SignupForm` | “Dữ liệu đi vào đối tượng nào?” |
| **Property** | Thuộc tính có thể truy cập/gán theo đường dẫn | `name`, `age`, `level` | “Giá trị này thuộc chỗ nào trên đối tượng?” |
| **Binder** | Thành phần điều phối ánh xạ, gán và ghi nhận lỗi | `DataBinder`; trên web là `WebDataBinder` | “Ai thực hiện việc gắn input vào target?” |
| **Converter** | Thành phần chuyển giá trị từ kiểu nguồn sang kiểu đích | `String -> Level`, `String -> Integer` | “Làm sao giá trị đầu vào trở thành đúng kiểu Java?” |
| **Validator** | Thành phần xét điều kiện hợp lệ | `age >= 18`, `name` không trống | “Giá trị đã có có thỏa quy tắc không?” |

**Phân biệt nhanh:** converter trả lời “có chuyển được `"16"` thành số 16 không?”; validator trả lời “16 có đạt tuổi tối thiểu 18 không?”. Giá trị có thể **đúng kiểu nhưng sai quy tắc**.

## 2. Target: đối tượng đích, không đồng nghĩa entity

`Target` là instance mà binder đang xử lý, ví dụ `new SignupForm()`. Nó có thể là form object, DTO, command object hoặc object dùng trong tầng khác; không bắt buộc là JPA entity, không phải tên bảng CSDL, và không phải request HTTP.

```java
public class SignupForm {
    private String name;
    private int age;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public int getAge() { return age; }
    public void setAge(int age) { this.age = age; }
}
```

Đây là **đoạn định nghĩa lớp**, không phải chương trình tự chạy. Với kiểu mutable JavaBean trên, binder thường thực hiện property binding qua cơ chế truy cập property. Trong constructor binding, Spring tạo target qua constructor phù hợp và chuyển giá trị cho các tham số constructor; một `record` cũng có thể là form object.

**Thiết kế an toàn:** đối với dữ liệu không tin cậy từ HTTP, ưu tiên DTO chỉ chứa các trường được phép nhập hoặc object immutable với constructor được thiết kế rõ. Tránh bind trực tiếp toàn bộ entity có các trường nhạy cảm như `role`, `isAdmin`, `price`, `ownerId`. Validation không tự ngăn việc gán ngoài ý muốn (*mass assignment*).

## 3. Property: tên đường dẫn để binder định vị giá trị

Property là điểm nhận dữ liệu trên target, thường theo JavaBeans convention: `getX()/setX(...)` hoặc `isX()` cho boolean. Ví dụ `age` tương ứng `getAge()/setAge(int)`. Field `private` không tự động đồng nghĩa property có thể bind; binder cần đường truy cập phù hợp. Spring cũng hỗ trợ direct field access khi cấu hình riêng, chẳng hạn qua `DataBinder.initDirectFieldAccess()`.

Một số tên đầu vào:

| Input name | Ý nghĩa |
| --- | --- |
| `name` | Property đơn ở đối tượng gốc |
| `address.city` | Property lồng nhau: `target.getAddress().getCity()/setCity(...)` theo cơ chế truy cập phù hợp |
| `items[0].quantity` | Property của phần tử danh sách ở chỉ số 0 |
| `settings[theme]` | Phần tử Map theo khóa `theme`, nếu cấu trúc target hỗ trợ |

Spring có cơ chế cho đường dẫn nested/indexed, nhưng việc khởi tạo các object trung gian và mở rộng collection phụ thuộc cấu trúc target cùng cấu hình binder. **Property không phải một cột database, không phải một annotation, cũng không phải “thuộc tính tùy ý” mà client được quyền tự đặt.**

Nên phân biệt thêm ba khái niệm:

- **Input name**: khóa đầu vào, ví dụ `age` trong request.
- **Property name/path**: đường dẫn mà binder hiểu trên target, ví dụ `age` hoặc `address.city`.
- **Property value**: giá trị thực tế sau chuyển kiểu, ví dụ `int 16`.

Tên đầu vào có thể trùng property, nhưng không phải mọi input name đều hợp lệ hoặc được phép bind.

## 4. Binder: trung tâm điều phối, không phải converter/validator

`org.springframework.validation.DataBinder` nhận target và dữ liệu kiểu `PropertyValues`, xác định các property có thể bind, thực hiện gán kèm chuyển kiểu khi cần, và thu thập lỗi qua `BindingResult`. `org.springframework.web.bind.WebDataBinder` mở rộng cơ chế này cho ngữ cảnh web. Trong Spring MVC, framework dùng binder theo yêu cầu và có thể cấu hình qua `@InitBinder`.

Ở mức chương trình, trình tự thường là:

```java
DataBinder binder = new DataBinder(target, "signupForm");
binder.setConversionService(conversionService);
binder.setValidator(validator);

binder.bind(inputValues);     // Bind + chuyển kiểu + lỗi binding nếu có.
binder.validate();            // Chủ động chạy validator đã cấu hình.
BindingResult result = binder.getBindingResult();
```

Đoạn trên minh họa **thứ tự API**; `target`, `conversionService`, `validator` và `inputValues` phải được khai báo. Phần 7 có chương trình đầy đủ.

Các điểm mấu chốt:

1. `bind(...)` và `validate()` là hai thao tác khác nhau trong API `DataBinder`. Chỉ tạo binder hoặc chỉ gọi `bind` không có nghĩa đã chạy validator.
2. Nếu giá trị không chuyển được sang kiểu property, binder có thể ghi `FieldError` (thường với mã `typeMismatch`); property đó không nhất thiết được cập nhật. Không nên giả định mọi lỗi đều ném exception ra ngoài ngay.
3. `BindingResult` là **kết quả** chứa lỗi binding/validation, không phải component làm chuyển kiểu hoặc tự kiểm tra quy tắc.
4. Binder có cấu hình như `setAllowedFields(...)` và `setDisallowedFields(...)` cho **property binding**. Với input từ web, hãy giới hạn các trường được phép gán; danh sách allowed fields không thay thế việc thiết kế DTO/constructor binding phù hợp.
5. `@InitBinder` dùng để cấu hình binder theo controller/phạm vi áp dụng; đây không phải nơi bắt buộc đặt toàn bộ business validation.

## 5. Converter: chuyển kiểu dữ liệu, chưa kết luận hợp lệ nghiệp vụ

`org.springframework.core.convert.converter.Converter<S, T>` là giao diện chuyển kiểu từ `S` sang `T`, ví dụ `String` sang enum `Level`. Các converter được đăng ký trong `ConversionService`; Spring đã cung cấp nhiều chuyển đổi thông dụng (chuỗi sang số, enum, v.v.).

```java
import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

enum Level { BASIC, ADVANCED }

class LevelConverter implements Converter<String, Level> {
    @Override
    public Level convert(String value) {
        return Level.valueOf(value.trim().toUpperCase(Locale.ROOT));
    }
}
```

Đây là **đoạn lớp minh họa trong dự án có Spring**, chưa phải file Java độc lập hoàn chỉnh. `"advanced"` thành `Level.ADVANCED`. Giá trị `"unknown"` không ánh xạ vào enum này và sẽ gây lỗi chuyển kiểu; xử lý lỗi khi bind thuộc trách nhiệm binder/`BindingResult`. Converter không quyết định liệu level đó có được cấp cho người dùng hiện tại hay không.

| Khái niệm gần converter | Dùng khi nào |
| --- | --- |
| `Converter<S,T>` | Một chuyển kiểu xác định, không gắn trực tiếp với rule nghiệp vụ |
| `ConversionService` | Đầu mối tra cứu/chạy các converter và cơ chế chuyển đổi liên quan |
| `Formatter<T>` | Parse/print giá trị cho UI, thường có yếu tố `Locale` như ngày, số tiền |
| `PropertyEditor` | Cơ chế JavaBeans cũ hơn mà Spring vẫn có thể hỗ trợ; với mã mới thường ưu tiên `ConversionService`/`Formatter` |

Ví dụ, `"2,5"` là 2.5 hay lỗi parse phụ thuộc quy ước locale và formatter, không nên tự giả định converter mặc định hiểu mọi định dạng. Cũng không nên dùng converter để gọi database hay thực hiện kiểm tra quyền truy cập nếu một lớp service/validator thích hợp hơn.

## 6. Validator: kiểm tra quy tắc sau khi có giá trị

Spring có interface `org.springframework.validation.Validator`:

- `supports(Class<?> clazz)` xác định validator có hỗ trợ kiểu target không.
- `validate(Object target, Errors errors)` kiểm tra và ghi lỗi qua `errors.rejectValue(...)` hoặc `errors.reject(...)`.

Các loại lỗi thường gặp:

| Trường hợp | Nơi nhận biết | Ví dụ |
| --- | --- | --- |
| Không chuyển được kiểu | Giai đoạn binding/conversion | `age="abc"` không thành `int`; thường ghi `typeMismatch` |
| Đúng kiểu, sai ràng buộc field | Validator/Bean Validation | `age=16` trong form yêu cầu tối thiểu 18 |
| Sai quy tắc liên trường | Validator/service thích hợp | `startDate` phải trước `endDate` |
| Tên property không được phép | Cấu hình binder/thiết kế DTO | Client gửi thêm `isAdmin=true` |
| Tác vụ nghiệp vụ thất bại | Tầng nghiệp vụ, không mặc nhiên là lỗi bind | Hết hàng, trùng giao dịch, không đủ quyền |

Ngoài Spring `Validator`, ứng dụng thường dùng **Jakarta Bean Validation** như `@NotBlank`, `@Min`, `@Email`, kích hoạt qua `@Valid` hoặc `@Validated` và provider phù hợp (trong Spring Boot, thường thêm `spring-boot-starter-validation`). `@Valid` không làm nhiệm vụ chuyển kiểu; nó kích hoạt validation trong ngữ cảnh hỗ trợ. Các annotation constraint không thay thế kiểm soát quyền, transaction hay invariant ở tầng domain.

## 7. Ví dụ Java 17+ có thể chạy: đủ năm thành phần

Ví dụ sau sử dụng Spring Framework **6.2.12** để thấy rõ binder, converter, validator và lỗi. Đây là project Maven tối thiểu, không cần chạy web server.

Tạo cấu trúc:

```text
binding-vocabulary/
├── pom.xml
└── src/main/java/BindingVocabularyDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>binding-vocabulary</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/BindingVocabularyDemo.java`:

```java
import java.util.Locale;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class BindingVocabularyDemo {
    enum Level { BASIC, ADVANCED }

    public static class SignupForm {
        private String name;
        private int age;
        private Level level;

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }

        public int getAge() { return age; }
        public void setAge(int age) { this.age = age; }

        public Level getLevel() { return level; }
        public void setLevel(Level level) { this.level = level; }
    }

    public static class SignupValidator implements Validator {
        @Override
        public boolean supports(Class<?> clazz) {
            return SignupForm.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            SignupForm form = (SignupForm) target;
            if (form.getName() == null || form.getName().isBlank()) {
                errors.rejectValue("name", "name.required", "Tên không được trống");
            }
            if (form.getAge() < 18) {
                errors.rejectValue("age", "age.tooYoung", "Tuổi phải từ 18");
            }
        }
    }

    public static void main(String[] args) {
        SignupForm target = new SignupForm();
        DataBinder binder = new DataBinder(target, "signupForm");

        DefaultConversionService conversions = new DefaultConversionService();
        conversions.addConverter(String.class, Level.class,
                raw -> Level.valueOf(raw.trim().toUpperCase(Locale.ROOT)));
        binder.setConversionService(conversions);
        binder.setValidator(new SignupValidator());

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "An");
        input.add("age", "16");
        input.add("level", "advanced");

        binder.bind(input);
        binder.validate();
        BindingResult result = binder.getBindingResult();

        System.out.println("name=" + target.getName());
        System.out.println("age=" + target.getAge());
        System.out.println("level=" + target.getLevel());
        System.out.println("errorCount=" + result.getErrorCount());
        System.out.println("ageError=" + (result.getFieldError("age") != null));
    }
}
```

Chạy từ thư mục `binding-vocabulary` (cần JDK 17+ và Maven, lần đầu cần tải dependency):

```bash
mvn -q compile exec:java -Dexec.mainClass=BindingVocabularyDemo
```

Kết quả stdout dự kiến:

```text
name=An
age=16
level=ADVANCED
errorCount=1
ageError=true
```

**Giải thích theo năm thuật ngữ:**

1. `target` là instance `SignupForm` được tạo trước khi bind.
2. `property` là `name`, `age`, `level`; các setter JavaBeans cung cấp đường gán.
3. `binder` là `DataBinder`; `bind(input)` đưa dữ liệu vào target.
4. `converter` cho `String -> Level` biến `"advanced"` thành `ADVANCED`; `"16"` được cơ chế chuyển kiểu mặc định biến thành `int 16`.
5. `validator` bác bỏ tuổi 16. `BindingResult` ghi một `FieldError` cho `age` mặc dù số 16 đã được gán thành công.

Đổi `input.add("age", "16")` thành `"20"` thì lỗi tuổi biến mất (nếu giữ nguyên các input khác). Đổi thành `"abc"` thì có thể phát sinh lỗi `typeMismatch` ở giai đoạn binding; không suy luận số lỗi hoặc giá trị trường sau thất bại từ ví dụ `"16"`.

## 8. Liên hệ Spring MVC: ai tạo binder và khi nào validation chạy?

Với controller dùng `@ModelAttribute`, Spring MVC có thể tạo hoặc lấy model attribute, bind dữ liệu request vào object và kích hoạt validation khi có `@Valid`/`@Validated`. `BindingResult` đặt **ngay sau** tham số model attribute cho phép controller xử lý lỗi.

```java
// Đoạn mã đặt trong ứng dụng Spring MVC có dependency Bean Validation.
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

record RegisterRequest(@NotBlank String name, @Min(18) int age) {}

@Controller
class RegisterController {
    @PostMapping("/register")
    String submit(@Valid @ModelAttribute("form") RegisterRequest form,
                  BindingResult errors) {
        if (errors.hasErrors()) {
            return "register-form";
        }
        return "register-success";
    }
}
```

Đây là **đoạn tích hợp Spring MVC**, không phải chương trình standalone ở phần 7; tên view giả định project đã cấu hình view resolver/template tương ứng. Với `record`, Spring có thể sử dụng constructor binding. Nếu bỏ `BindingResult` trong trường hợp validation thất bại, exception và cách phản hồi phụ thuộc nhánh xử lý Spring MVC (ví dụ `MethodArgumentNotValidException` cho validation của argument, hoặc `HandlerMethodValidationException` trong kịch bản method validation); không nên mặc định mọi lỗi đều cho một loại exception.

Cần phân biệt:

- `@ModelAttribute`: phù hợp binding tham số/form vào model object; liên quan trực tiếp tới `WebDataBinder`.
- `@RequestBody`: dữ liệu JSON thường được message converter (ví dụ Jackson) deserialize vào object trước; có thể validation với `@Valid`, nhưng **không nên đồng nhất bước JSON deserialization với property binding của `@ModelAttribute`**.
- `@InitBinder`: cấu hình binder cho phạm vi controller/advice, ví dụ đăng ký validator hay giới hạn field cho mutable form.
- `BindingResult`/`Errors`: chứa thông tin lỗi và phải đặt đúng vị trí trong method signature khi xử lý lỗi cho argument tương ứng.

Ví dụ cấu hình cho form mutable (khác với record ở trên):

```java
@InitBinder("signupForm")
void configure(WebDataBinder binder) {
    binder.setAllowedFields("name", "age", "level");
}
```

Đây là **đoạn phương thức minh họa trong controller**: cần import `org.springframework.web.bind.annotation.InitBinder` và `org.springframework.web.bind.WebDataBinder`. `setAllowedFields` giới hạn **property binding**; không nên xem nó là cách duy nhất kiểm soát constructor binding hoặc thay thế DTO/kiểm tra quyền.

## 9. Những nhầm lẫn và cách chẩn đoán

| Triệu chứng | Cần xem trước | Hướng kiểm tra |
| --- | --- | --- |
| Property không nhận giá trị | Tên input, getter/setter, nested path, allowed fields | Xác nhận path đúng và target có đường truy cập phù hợp |
| `age="abc"` không bind thành số | Conversion + `BindingResult` | Xem `FieldError`, mã `typeMismatch` và rejected value |
| `age=16` bind được nhưng bị bác | Validator/constraint | Tìm `@Min`, `rejectValue`, rule liên quan |
| `"advanced"` không thành enum | Converter/ConversionService | Kiểm tra converter đã được đăng ký, luật parse và chữ hoa/thường |
| Không thấy lỗi validation | Cơ chế kích hoạt validation | Kiểm tra `binder.validate()` hoặc `@Valid`/`@Validated` và provider |
| Client đổi được trường không mong muốn | Thiết kế target và phạm vi property binding | Dùng DTO phù hợp, constructor binding hoặc allowed fields |
| Controller không thấy lỗi trong `BindingResult` | Chữ ký method | Đặt `BindingResult` ngay sau argument tương ứng, kiểm tra kiểu binding |

Một cách debug có hệ thống là đi từ **input name/raw value → property path → target type → conversion → gán → validation → BindingResult**. Ví dụ gặp `typeMismatch` thì sửa converter/format đầu vào; gặp `@Min` thì sửa dữ liệu hoặc quy tắc validation; gặp trường bị bind ngoài ý muốn thì sửa contract target và giới hạn field, không “chữa” bằng converter.

## 10. Tự kiểm tra

**Tình huống A:** `age="twenty"`, target khai báo `int age`. Thành phần nào cần khảo sát đầu tiên? **Conversion/binding**. Không thể kết luận có lỗi “tuổi dưới 18” chỉ từ chuỗi này.

**Tình huống B:** `age="17"` chuyển thành `int 17`, ứng dụng yêu cầu người từ 18 tuổi. Thành phần nào chịu trách nhiệm? **Validator**. Chuyển kiểu đã thành công.

**Tình huống C:** Client gửi `isAdmin=true` dù màn hình chỉ có `name` và `age`. Đây là vấn đề gì? **Phạm vi property được phép bind và thiết kế target**, cần giới hạn ở DTO/constructor/allowed fields phù hợp; `@NotNull` hay converter không phải biện pháp kiểm soát quyền.

**Tình huống D:** Có `DataBinder` với converter và validator nhưng chỉ gọi `binder.bind(values)`. Có chắc validation đã chạy? **Không**; với API dùng trực tiếp, cần gọi `binder.validate()` để chạy validator đã cấu hình.

**Ghi nhớ cuối bài:** *target* là “ai nhận”, *property* là “nhận ở đâu”, *binder* là “ai điều phối”, *converter* là “chuyển thành kiểu gì”, *validator* là “có hợp lệ không”; *BindingResult* là “lỗi được ghi ở đâu”.

## Tài liệu tham khảo chính thức

- [Spring Framework – Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework – Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework – Java Bean Validation / DataBinder](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework – Spring MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework – MVC @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
