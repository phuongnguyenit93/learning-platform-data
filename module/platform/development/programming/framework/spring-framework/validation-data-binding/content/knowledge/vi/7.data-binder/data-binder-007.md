# DataBinder: validate với hoặc không có validation hints

## 1. Vấn đề cần hiểu

Spring Framework cung cấp hai phương thức trên `org.springframework.validation.DataBinder`:

```java
binder.validate();                 // Không truyền hints.
binder.validate("strict");         // Hint tùy biến do ứng dụng hiểu.
binder.validate(Publish.class);    // Hint là class, thường dùng làm validation group.
```

Cả hai overload đều yêu cầu chạy các validator đã đăng ký trên target của binder, rồi đưa lỗi vào `BindingResult`. Sự khác biệt nằm ở **cách Spring gọi từng validator**: không truyền hints thì dùng phương thức validation cơ bản; có hints không rỗng thì Spring có thể chuyển chúng tới `SmartValidator`.

Hãy hình dung một biểu mẫu đăng ký: quy tắc cơ bản yêu cầu tên đủ dài và email hợp lệ; chế độ xuất bản bổ sung yêu cầu địa chỉ email thuộc miền doanh nghiệp. Bộ kiểm tra cơ bản luôn chạy, còn một validator thông minh có thể nhận hint `"strict"` để áp dụng thêm yêu cầu. Bản thân `DataBinder` **không hiểu** ý nghĩa nghiệp vụ của `"strict"`.

Nắm chắc bốn ý:

1. `DataBinder` **điều phối** binding và validation.
2. `Validator` thường chỉ có `validate(Object, Errors)`.
3. `SmartValidator` hỗ trợ thêm `validate(Object, Errors, Object... hints)`.
4. Hints chỉ là thông tin bổ sung; tác dụng phụ thuộc validator được gọi.

## 2. Những thành phần tham gia

`DataBinder` nhận target Java và tên đối tượng, quản lý lỗi binding và cho phép đăng ký một hoặc nhiều Spring validator:

```java
DataBinder binder = new DataBinder(form, "registration");
binder.addValidators(new RegistrationValidator());
binder.validate();
BindingResult result = binder.getBindingResult();
```

Đây là mã minh họa đặt trong method đã có `form` và `RegistrationValidator` hợp lệ. `"registration"` là object name dùng trong `BindingResult`, không nhất thiết là tên class. `DataBinder` có thể được sử dụng ngoài Spring MVC; `WebDataBinder` trong ứng dụng web kế thừa cơ chế này.

### Validator thường

`org.springframework.validation.Validator` có hợp đồng cơ bản:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

`supports(Class<?>)` xác định lớp target có thể kiểm tra. `validate(Object, Errors)` đánh giá đối tượng và gọi `errors.rejectValue(...)` cho lỗi thuộc trường hoặc `errors.reject(...)` cho lỗi toàn đối tượng. Nó không có tham số hint.

### SmartValidator

`org.springframework.validation.SmartValidator` mở rộng `Validator`, bổ sung overload:

```java
public interface SmartValidator extends Validator {
    void validate(Object target, Errors errors, Object... validationHints);
}
```

Đây là chữ ký trọng tâm rút gọn; các phiên bản Spring có thể có thêm phương thức hỗ trợ. Một class triển khai `SmartValidator` vẫn là một `Validator`, và cần định nghĩa cả hành vi validation cơ bản. `Object...` là cú pháp varargs: lời gọi có thể truyền nhiều đối tượng, chẳng hạn chuỗi, enum, hoặc class đại diện một nhóm validation.

### BindingResult

`DataBinder.validate(...)` trả về **`void`**, không trả boolean hay một tập vi phạm. Để đọc kết quả:

```java
BindingResult result = binder.getBindingResult();
boolean invalid = result.hasErrors();
int totalErrors = result.getErrorCount();
int fieldErrors = result.getFieldErrorCount();
int globalErrors = result.getGlobalErrorCount();
```

`BindingResult` có thể chứa lỗi chuyển đổi dữ liệu từ bước binding cũng như lỗi do validator ghi. Kết quả của `DataBinder` khác kiểu `Set<ConstraintViolation<T>>` do Jakarta Validation API trả về; nếu Spring tích hợp Jakarta provider, adapter sẽ chuyển thông tin phù hợp sang lỗi Spring.

## 3. Cách validate() không có hints hoạt động

Lời gọi:

```java
binder.validate();
```

Spring lấy target và `BindingResult` rồi duyệt các validator được cấu hình. Với **mọi validator**, kể cả class có triển khai `SmartValidator`, overload `DataBinder.validate()` yêu cầu phương thức cơ bản:

```java
validator.validate(target, bindingResult);
```

Điều này có nghĩa:

- `Validator` thông thường chạy toàn bộ luật mà nó tự viết.
- `SmartValidator` chạy phần luật của phương thức `validate(Object, Errors)`.
- Không có hints nào được truyền đến phương thức ba tham số của `SmartValidator`.
- Mỗi validator ghi lỗi vào `BindingResult` dùng chung; có thể xem `getFieldErrors()` và `getGlobalErrors()`.
- Không có validator nào được đăng ký thì lời gọi không tự tạo ra luật mới. Một annotation trên model cũng không tự thực thi chỉ vì binder tồn tại.

**Không có hint không đồng nghĩa bỏ qua validation.** `validate()` vẫn chạy luật mặc định của các validator đã đăng ký.

## 4. Cách validate(Object... hints) hoạt động

Ví dụ:

```java
binder.validate("strict");
binder.validate(Publish.class);
binder.validate(Default.class, Publish.class);
```

`Publish` cần được ứng dụng định nghĩa; trong ví dụ Jakarta, `Default` là `jakarta.validation.groups.Default`.

Đối với Spring Framework 6.1, cơ chế chọn overload có thể biểu diễn bằng pseudocode sau:

```java
for (Validator validator : validatorsToApply) {
    if (hints.length > 0 && validator instanceof SmartValidator smart) {
        smart.validate(target, bindingResult, hints);
    } else {
        validator.validate(target, bindingResult);
    }
}
```

Đây là **pseudocode**, không phải mã nguồn đầy đủ: mã Spring còn lấy target, kiểm tra trạng thái và xử lý mảng hints bằng tiện ích riêng. Điều quan trọng là chỉ **SmartValidator** mới nhận hints không rỗng; `Validator` thường vẫn được gọi như cũ.

| Lời gọi | Validator thường | SmartValidator |
| --- | --- | --- |
| `binder.validate()` | `validate(target, errors)` | `validate(target, errors)` |
| `binder.validate("strict")` | `validate(target, errors)` | `validate(target, errors, "strict")` |
| `binder.validate(Publish.class)` | `validate(target, errors)` | `validate(target, errors, Publish.class)` |
| `binder.validate(new Object[0])` | `validate(target, errors)` | `validate(target, errors)` vì hints rỗng |

Tại sao `validate(new Object[0])` giống `validate()`? Trong overload varargs, Spring chỉ đi theo nhánh `SmartValidator` khi mảng hints **không rỗng**. Dù vậy, viết `validate()` vẫn rõ ý định hơn khi bạn không cần hint.

**Lưu ý cốt lõi:** DataBinder không diễn giải, lọc hoặc đặt ý nghĩa mặc định cho chuỗi `"strict"`, class `Publish.class` hay một enum khác. Một `SmartValidator` có thể hiểu hint, bỏ qua hint, hoặc dùng hint để chọn nhóm quy tắc khác. Javadoc cũng ghi rõ hints có thể bị validator đích bỏ qua.

## 5. Ví dụ Java 17 độc lập: validator thường và SmartValidator

Trong ví dụ này có hai validator Spring, không cần Spring Boot, HTTP server hoặc Jakarta Validation provider:

- `BasicEmailValidator implements Validator`: kiểm tra email có ký tự `@`.
- `PolicyValidator implements SmartValidator`: luôn kiểm tra tên dài ít nhất ba ký tự; nếu nhận `"strict"` thì kiểm tra thêm email thuộc miền `@example.org`.

Chúng ta dùng **binder mới mỗi lần** để so sánh hai chế độ mà không cộng dồn lỗi.

Cấu trúc:

```text
databinder-hints/
├── pom.xml
└── src/main/java/demo/DataBinderHintsDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>databinder-hints</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/DataBinderHintsDemo.java`:

```java
package demo;

import java.util.Arrays;
import java.util.List;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.SmartValidator;
import org.springframework.validation.Validator;

public final class DataBinderHintsDemo {

    public static final class Signup {
        private final String username;
        private final String email;

        public Signup(String username, String email) {
            this.username = username;
            this.email = email;
        }

        public String getUsername() {
            return username;
        }

        public String getEmail() {
            return email;
        }
    }

    // Validator cơ bản: không thể nhận validation hints.
    public static final class BasicEmailValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Signup.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Signup form = (Signup) target;
            if (form.getEmail() == null
                    || !form.getEmail().contains("@")) {
                errors.rejectValue("email", "email.invalid");
            }
        }
    }

    // SmartValidator có overload hỗ trợ hints.
    public static final class PolicyValidator implements SmartValidator {
        @Override
        public boolean supports(Class<?> type) {
            return Signup.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Signup form = (Signup) target;
            if (form.getUsername() == null
                    || form.getUsername().length() < 3) {
                errors.rejectValue("username", "username.tooShort");
            }
        }

        @Override
        public void validate(
                Object target, Errors errors, Object... hints) {
            // Chủ động áp dụng luật cơ bản trong chế độ có hints.
            validate(target, errors);

            Signup form = (Signup) target;
            boolean strict = Arrays.asList(hints).contains("strict");

            if (strict
                    && (form.getEmail() == null
                        || !form.getEmail().endsWith("@example.org"))) {
                errors.rejectValue("email", "email.domain");
            }
        }
    }

    private static DataBinder newBinder(Signup signup) {
        DataBinder binder = new DataBinder(signup, "signup");
        binder.addValidators(
            new BasicEmailValidator(),
            new PolicyValidator()
        );
        return binder;
    }

    private static void show(String label, BindingResult result) {
        List<String> codes = result.getFieldErrors().stream()
            .map(error -> error.getCode())
            .sorted()
            .toList();
        System.out.println(label + ": " + codes);
    }

    public static void main(String[] args) {
        Signup input = new Signup("Li", "invalid");

        DataBinder normal = newBinder(input);
        normal.validate();
        show("no hints", normal.getBindingResult());

        DataBinder strict = newBinder(input);
        strict.validate("strict");
        show("strict", strict.getBindingResult());

        DataBinder unknown = newBinder(input);
        unknown.validate("unknown");
        show("unknown hint", unknown.getBindingResult());
    }
}
```

Chạy từ thư mục chứa `pom.xml`, với JDK 17+ và Maven đã cài:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.DataBinderHintsDemo
```

Các dòng **do chương trình in ra** (không tính log Maven/Spring nếu môi trường có thêm):

```text
no hints: [email.invalid, username.tooShort]
strict: [email.domain, email.invalid, username.tooShort]
unknown hint: [email.invalid, username.tooShort]
```

Diễn giải từng trường hợp:

1. `BasicEmailValidator` chạy ở cả ba lần, vì dù có hint hay không, nó chỉ triển khai `Validator` thường. `"invalid"` không chứa `@` nên có `email.invalid`.
2. `PolicyValidator.validate(Object, Errors)` kiểm tra tên `"Li"` ngắn hơn ba ký tự và tạo `username.tooShort`.
3. `normal.validate()` gọi phương thức cơ bản của `PolicyValidator`, nên **không** tạo `email.domain`.
4. `strict.validate("strict")` gọi overload của `SmartValidator`. Trong code, overload **chủ động gọi lại phương thức cơ bản**, sau đó áp dụng luật miền email và tạo `email.domain`.
5. `unknown.validate("unknown")` vẫn truyền một hint tới `SmartValidator`, nhưng validator không nhận diện nó nên không bổ sung lỗi.
6. `sorted()` sắp xếp mã lỗi theo chữ cái để dòng output có thứ tự ổn định. Đây là mã lỗi đã ghi vào `BindingResult`; không phải các message đã nội suy từ `MessageSource`.

### Điểm rất dễ sai khi tự viết SmartValidator

Trong overload:

```java
@Override
public void validate(Object target, Errors errors, Object... hints) {
    validate(target, errors);
    // Các kiểm tra bổ sung dựa trên hints.
}
```

Lời gọi `validate(target, errors)` là **do người viết chủ động thêm**. Spring không tự động gọi đồng thời cả phương thức cơ bản và phương thức có hints của cùng một `SmartValidator`. Nếu bạn muốn chế độ strict **bổ sung** luật mặc định, cần tái sử dụng chúng như trên hoặc thiết kế một method nội bộ dùng chung. Nếu mục đích của hint là **thay bộ quy tắc**, có thể lựa chọn logic khác; không có quy tắc rằng truyền hint luôn tạo nhiều lỗi hơn.

## 6. Validation hints khi tích hợp Jakarta Validation groups

Một tình huống khác với chuỗi `"strict"` tự định nghĩa là **Bean Validation groups** của Jakarta Validation. Spring cung cấp `LocalValidatorFactoryBean` và `SpringValidatorAdapter` để kết nối Jakarta Validation provider với mô hình `SmartValidator`/`BindingResult` của Spring.

Ví dụ DTO có ràng buộc theo nhóm:

```java
import jakarta.validation.constraints.NotBlank;

interface Publish {}

record Article(
    @NotBlank String title,
    @NotBlank(groups = Publish.class) String slug
) {}
```

Đây là đoạn mô tả dữ liệu, chưa phải chương trình độc lập. `@NotBlank` trên `title` thuộc nhóm `jakarta.validation.groups.Default` (không khai báo groups); `@NotBlank` trên `slug` chỉ thuộc nhóm `Publish`.

Nếu một `LocalValidatorFactoryBean` đã được khởi tạo, provider tương thích đang hiện diện và binder đăng ký adapter đó:

```java
DataBinder binder = new DataBinder(article, "article");
binder.setValidator(localValidatorFactoryBean);

binder.validate();                        // Default.
binder.validate(Publish.class);           // Publish.
binder.validate(
    jakarta.validation.groups.Default.class,
    Publish.class
);                                        // Default + Publish.
```

**Đây là minh họa API**, với `article` và `localValidatorFactoryBean` giả định đã có, không thuộc ví dụ Java SE ở mục 5. Khi so sánh từng cách gọi, hãy tạo các binder độc lập để kết quả không tích lũy.

Sự khác nhau:

- `DataBinder.validate()` gọi phương thức validation cơ bản của adapter, tương ứng cách Jakarta provider validate nhóm mặc định.
- `DataBinder.validate(Publish.class)` truyền hint lớp nhóm cho adapter và provider, yêu cầu kiểm tra constraint thuộc `Publish`. Một nhóm được chọn **không tự bao gồm `Default`** chỉ vì constraint mặc định có trong DTO.
- `DataBinder.validate(Default.class, Publish.class)` là cách tường minh kiểm tra cả hai nhóm ở entry point đó (hoặc dùng group inheritance/sequence phù hợp nếu được thiết kế).
- `DataBinder.validate("strict")` trong ví dụ trước chỉ là giao ước riêng của `PolicyValidator`. Đừng đưa chuỗi tùy ý vào Jakarta adapter rồi kỳ vọng nó tự trở thành group.

Phần Java SE ví dụ ở mục 5 **không dùng Jakarta provider**, vì vậy `"strict"` được hiểu hoàn toàn bởi Java code trong `PolicyValidator`. Khi dùng Spring Boot 3, dependency thông dụng cho Jakarta Validation là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Đây là phần phụ thuộc đặt trong dự án đã có Spring Boot parent/BOM tương ứng. Starter thường cung cấp Jakarta Validation API và Hibernate Validator provider phù hợp; `DataBinder` không phải chính provider đó.

## 7. Có nhiều validator thì hints ảnh hưởng thế nào?

Giả sử binder đăng ký:

```java
binder.addValidators(new BasicEmailValidator(), new PolicyValidator());
binder.validate("strict");
```

Trình tự tổng quát:

1. `BasicEmailValidator` được gọi qua `validate(target, errors)`; nó không biết hint `"strict"`.
2. `PolicyValidator` được gọi qua `validate(target, errors, "strict")` vì là `SmartValidator`.
3. Cả hai ghi lỗi vào **cùng `BindingResult`**.
4. `binder.getBindingResult().hasErrors()` phản ánh tổng số lỗi, có thể gồm lỗi binding đã phát sinh trước.

Nếu đăng ký một `LocalValidatorFactoryBean` cho Jakarta groups cùng một validator Spring thường, truyền `Publish.class` chỉ có tác động groups ở adapter; validator Spring thường **vẫn kiểm tra luật của nó**. Vì vậy group không phải “công tắc tắt mọi validator khác”.

### addValidators và setValidator

- `addValidators(...)` thêm validator vào danh sách dùng cho binder.
- `setValidator(...)` đặt validator chính, có thể thay danh sách cấu hình trước theo hợp đồng Spring tương ứng.
- Spring kiểm tra tính phù hợp với target qua `supports(Class<?>)` khi đăng ký validator. Đăng ký nhầm kiểu target là lỗi cấu hình, không phải một cách dùng hint để lọc validator.

Nếu cần kiểm soát thứ tự hoặc việc loại trừ validator, hãy cấu hình binder/luồng gọi đúng theo Spring version đang sử dụng; đừng giả định hints là danh sách tên validator cần chạy.

## 8. Dùng lại DataBinder và tích lũy lỗi

Một lỗi trong phép thử là gọi liên tiếp:

```java
binder.validate();
binder.validate("strict");
System.out.println(binder.getBindingResult().getErrorCount());
```

Cùng một `BindingResult` có thể giữ lỗi của cả hai lượt. Ví dụ `errors.rejectValue(...)` có thể thêm lỗi lặp. Kết quả cuối không đại diện riêng cho chế độ strict. Muốn so sánh, hãy khởi tạo binder mới cho mỗi trường hợp như ví dụ chạy được.

Điều này cũng áp dụng khi có lỗi **binding/conversion** trước validation: `validate(...)` không xóa các `FieldError` do chuyển kiểu không thành công. `hasErrors()` và `getErrorCount()` không chỉ đếm các ràng buộc được kích hoạt bởi hint.

Một `DataBinder` phải có target hợp lệ để validate. Hệ thống có thể từ chối thao tác nếu không có target; nếu validator gọi `rejectValue("someField", ...)`, tên trường cần tương ứng với property mà Spring có thể truy cập. Hints không sửa được vấn đề sai field path, sai kiểu target hoặc sai cấu hình validator.

## 9. Liên hệ Spring MVC: @Valid và @Validated

Trong Spring MVC, `WebDataBinder` kế thừa `DataBinder`. Khi framework xử lý một tham số `@ModelAttribute` hoặc `@RequestBody` có annotation kích hoạt validation, Spring có thể thực hiện bước validate sau binding và cung cấp `BindingResult`.

Ví dụ chọn nhóm Jakarta:

```java
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@PostMapping("/articles")
String publish(
        @Validated(Publish.class)
        @ModelAttribute("article") ArticleForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "article-form";
    }
    return "article-created";
}
```

Đây là **đoạn mã minh họa đặt trong controller** có `ArticleForm` và `Publish` được định nghĩa. Không phải chương trình Java độc lập. `BindingResult` phải đặt ngay sau tham số được validate để controller xử lý lỗi tại chỗ.

Trong cấu hình Jakarta Validation của Spring MVC, `@Validated(Publish.class)` cung cấp group hint cho validator phù hợp. `@Valid` thường yêu cầu validation theo nhóm mặc định, không tự chỉ định thêm một nhóm nghiệp vụ. Nếu controller đã được framework tự kích hoạt validation, không cần tự gọi lại `binder.validate(...)` chỉ để nhận cùng lỗi lần nữa.

Lưu ý validation **đối số controller** và **method validation qua AOP** không phải một đường thực thi duy nhất. `@Validated` ở service có thể tham gia method validation thông qua proxy; gọi `DataBinder.validate(...)` thủ công không tự tạo proxy hoặc kiểm tra mọi lời gọi method khác.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần xem | Cách xử lý |
| --- | --- | --- |
| Truyền `"strict"` nhưng không có lỗi mới | Validator thường không nhận hint; SmartValidator không xử lý hint | Kiểm tra kiểu validator và overload triển khai |
| `validate()` vẫn có lỗi | Đây là hành vi bình thường khi có validator đăng ký | Đọc `BindingResult`, xem luật mặc định |
| Nhóm `Publish` không kiểm tra constraint mặc định | `Publish` không mặc nhiên bao gồm `Default` | Truyền đúng nhiều nhóm hoặc thiết kế group |
| Truyền chuỗi `"Publish"` thay vì `Publish.class` | Jakarta Validation groups dùng class | Dùng class nhóm thực và adapter tương thích |
| Hints làm mất luật cơ bản ở SmartValidator | Overload có hints không tự gọi overload cơ bản | Tái sử dụng logic khi mục tiêu là bổ sung luật |
| Gọi validate hai lần làm tăng lỗi | Dùng lại `BindingResult` cùng binder | Tách binder/test case cho từng lần chạy |
| Có annotation mà không thấy lỗi | Provider/adapter/entry point chưa kích hoạt | Kiểm tra dependency, Bean Validation và luồng gọi |
| Lỗi Spring có mã nhưng thiếu thông điệp | `MessageSource` hoặc default message chưa phù hợp | Cấu hình thông điệp theo error code |
| Kỳ vọng `validate(...)` trả boolean | API trả `void` | Kiểm tra `getBindingResult().hasErrors()` |
| Validation thất bại khi binder không có target | Chưa tạo target hợp lệ | Tạo target và cấu hình validator trước khi gọi |

Quy tắc thiết kế hữu ích:

- Chỉ cần luật mặc định: ưu tiên `Validator` cơ bản và `binder.validate()`.
- Cần luật phụ thuộc ngữ cảnh: dùng `SmartValidator` và hợp đồng hints được mô tả rõ.
- Cần nhóm annotation chuẩn: dùng Jakarta Validation groups với provider/adapter tương thích và hints kiểu `Class<?>`.
- Tránh dùng hint như cơ chế phân quyền: validation mode không thay thế authorization hoặc kiểm soát nghiệp vụ.
- Khi kiểm thử các mode, xác nhận tập error codes với binder mới cho mỗi mode thay vì chỉ đếm lỗi trong cùng binder.

## 11. Câu hỏi tự kiểm tra

1. `binder.validate("strict")` làm gì nếu chỉ có một `Validator` thông thường?
2. Với `SmartValidator`, khi gọi `binder.validate()`, Spring sử dụng overload nào?
3. Nếu overload nhận hints không gọi lại logic cơ bản, tại sao strict mode có thể bỏ mất một rule?
4. `validate(new Object[0])` khác và giống `validate()` ở điểm nào?
5. `Publish.class` là gì và tại sao khác với chuỗi `"Publish"` trong Jakarta groups?
6. Vì sao `DataBinder.validate(Publish.class)` không tự ép một Spring `Validator` thường bỏ qua các luật của nó?
7. Sau validation, làm sao lấy tập lỗi và phân biệt lỗi binding với lỗi validation?

**Ghi nhớ:** `validate()` dùng phương thức validation cơ bản; `validate(hints...)` chỉ chuyển hints **không rỗng** cho `SmartValidator`, còn validator thường vẫn chạy như cũ. Hint có tác dụng đến đâu là trách nhiệm của validator nhận nó. Với Jakarta Validation adapter, các class hint thường biểu diễn validation groups.

## Tài liệu tham khảo

- Spring Framework — DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework — SmartValidator Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/validation/SmartValidator.html
- Spring Framework — SpringValidatorAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/validation/beanvalidation/SpringValidatorAdapter.html
- Spring Framework — Validation, Data Binding, and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Jakarta Validation Specification: https://jakarta.ee/specifications/bean-validation/
