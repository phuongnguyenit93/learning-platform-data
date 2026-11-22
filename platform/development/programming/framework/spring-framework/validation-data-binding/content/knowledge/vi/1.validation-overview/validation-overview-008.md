# Phạm vi sử dụng Spring Validation và Data Binding ở tầng web, service và ứng dụng độc lập

## 1. Mục tiêu và ý tưởng cốt lõi

Spring Framework cung cấp cơ chế **data binding** (đưa dữ liệu đầu vào vào đối tượng, kèm chuyển kiểu) và **validation** (kiểm tra dữ liệu có đáp ứng ràng buộc hay không). Hai cơ chế này thường xuất hiện trong xử lý HTTP, nhưng các hợp đồng cốt lõi trong `org.springframework.validation` có thể dùng ở service, tác vụ nền, CLI và ứng dụng Java độc lập. Điểm cần phân biệt là **vị trí chạy** và **cách phát sinh/xử lý lỗi** tùy tầng.

Hãy hình dung một dữ liệu đăng ký gồm `email` và `age`:

1. Nguồn nhận: HTTP form, JSON, thông điệp hàng đợi, CSV hay tham số CLI.
2. Chuyển đổi/binding: chuỗi `"21"` trở thành số nguyên `21`; tên thuộc tính được gắn với thuộc tính hoặc tham số constructor của đối tượng.
3. Kiểm tra kỹ thuật/định dạng: email đúng cấu trúc, tuổi nằm trong khoảng cho phép, trường bắt buộc không rỗng.
4. Kiểm tra nghiệp vụ: email đã tồn tại, tài khoản có quyền đặt hàng, tồn kho đủ, trạng thái giao dịch hợp lệ.
5. Xử lý kết quả: trả HTTP 400, ném exception từ service, trả lỗi theo từng dòng CSV hoặc in thông báo CLI.

Bước 2 và 3 có thể tái sử dụng xuyên tầng. Bước 4 thường thuộc miền nghiệp vụ/service và có thể cần truy vấn dữ liệu hoặc phối hợp nhiều đối tượng. Bước 5 thuộc về bên nhận/trình bày kết quả; `Validator` không tự quyết định HTTP status hay thông điệp người dùng.

### Phân biệt bốn khái niệm

| Khái niệm | Trách nhiệm | API Spring/Jakarta thường gặp |
| --- | --- | --- |
| Data binding | Gắn giá trị từ nguồn dữ liệu theo tên thuộc tính/constructor vào đối tượng | `DataBinder`, `WebDataBinder`, `@ModelAttribute` |
| Type conversion/formatting | Chuyển String thành số, ngày, enum hoặc kiểu khác; định dạng ngược khi cần | `ConversionService`, `Converter`, `Formatter` |
| Validation | Kiểm ràng buộc và sinh lỗi có cấu trúc | `org.springframework.validation.Validator`, `Errors`, `BindingResult`, `jakarta.validation.Validator` |
| Quy tắc nghiệp vụ | Kiểm điều kiện thuộc quy trình, trạng thái hệ thống hoặc dữ liệu ngoài | Service/domain logic, repository, policy, transaction |

**Lưu ý:** Bean Validation (các annotation như `@NotBlank`, `@Min`, `@Valid`) là chuẩn Jakarta Validation; cần một provider, chẳng hạn Hibernate Validator, tại thời điểm chạy. Spring tích hợp chuẩn này thông qua `LocalValidatorFactoryBean`, trong khi `org.springframework.validation.Validator` là hợp đồng riêng của Spring. `@Valid` không tự ràng buộc dữ liệu vào object và không tự kích hoạt kiểm tra tại mọi lời gọi Java thông thường.

## 2. Chọn nơi áp dụng theo trách nhiệm của từng tầng

| Môi trường | Nguồn dữ liệu chủ yếu | Cách dùng phù hợp | Kết quả lỗi nên đi về đâu |
| --- | --- | --- | --- |
| Spring MVC/WebFlux | Form/query/path/JSON/multipart từ HTTP | Cơ chế bind và validate của framework trong controller, DTO đầu vào | `BindingResult`/exception của framework, được ánh xạ thành response API hoặc biểu mẫu |
| Service trong Spring container | DTO/command được gọi từ web, job, message consumer, service khác | Validate bằng Jakarta `Validator`/Spring `Validator`; tùy chọn method validation qua proxy | Exception/kết quả nghiệp vụ do caller xử lý; không phụ thuộc Servlet |
| Ứng dụng độc lập/CLI/batch | Map, properties, CSV, tham số dòng lệnh, đối tượng được tạo thủ công | Khởi tạo `DataBinder` và `Validator` trực tiếp; hoặc Jakarta Validator trực tiếp | Thông báo dòng lỗi, báo cáo batch, exit code, file kết quả; không có HTTP mặc định |

Nguyên tắc thiết kế là **kiểm tra đầu vào tại ranh giới tiếp nhận**, đồng thời **giữ bất biến nghiệp vụ tại nơi sở hữu nghiệp vụ**. Ví dụ, controller kiểm tra request có `quantity >= 1`; service vẫn phải kiểm tra tồn kho và quyền mua vì service có thể được gọi từ scheduled job hoặc consumer mà không đi qua controller.

## 3. Tầng web: binding và validation gắn với vòng đời request

### 3.1. Form/query và JSON đi qua hai cơ chế khác nhau

- Với form/query parameters, `@ModelAttribute` yêu cầu Spring MVC tạo hoặc lấy model attribute rồi bind các giá trị phù hợp vào thuộc tính hoặc constructor của command object. `WebDataBinder` phối hợp chuyển kiểu, ghi nhận lỗi binding và gọi validator khi được yêu cầu.
- Với JSON `@RequestBody`, Spring MVC trước hết dùng `HttpMessageConverter` (thường là Jackson) để deserialize HTTP body thành Java object. `@Valid`/`@Validated` có thể kiểm tra đối tượng sau đó. Không nên mô tả việc đọc JSON này như lời gọi `DataBinder.bind(...)` theo trường form.
- `@RequestParam`/`@PathVariable` giải quyết tham số đơn lẻ; chuyển kiểu có thể thất bại trước khi controller chạy. Constraint đặt trực tiếp trên tham số method có thể kích hoạt method validation ở cấp controller, tùy chữ ký method và phiên bản Spring.

Đoạn dưới **minh họa các lớp bên trong một ứng dụng Spring MVC đã cấu hình Jakarta Validation** (không phải một chương trình độc lập; cần Spring Web và Bean Validation provider trên classpath):

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;

record RegisterRequest(
    @NotBlank @Email String email,
    @Min(18) int age
) {}

@RestController
@RequestMapping("/registrations")
class RegistrationController {

    @PostMapping(
        path = "/form",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    ResponseEntity<?> fromForm(
        @Valid @ModelAttribute RegisterRequest request,
        BindingResult errors
    ) {
        if (errors.hasErrors()) {
            var details = errors.getFieldErrors().stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .toList();
            return ResponseEntity.badRequest().body(details);
        }
        return ResponseEntity.ok("accepted");
    }

    @PostMapping(
        path = "/json",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<String> fromJson(
        @Valid @RequestBody RegisterRequest request
    ) {
        return ResponseEntity.ok("accepted");
    }
}
~~~

- Gửi form `email=invalid&age=17` đến `/registrations/form`: dữ liệu được bind vào `RegisterRequest`; các constraint email và tuổi thất bại; `BindingResult` ngay sau tham số cần kiểm tra chứa lỗi và nhánh controller trả 400.
- Gửi JSON `{"email":"person@example.org","age":21}` đến `/registrations/json`: body được deserialize, sau đó validate, kết quả thành công là chuỗi `accepted`.
- Gửi JSON không hợp lệ về cú pháp có thể gây lỗi đọc body (ví dụ `HttpMessageNotReadableException`) trước Bean Validation. Không nên gộp lỗi parse JSON, lỗi chuyển kiểu form và lỗi constraint thành một nguyên nhân.
- Với `@ModelAttribute` và `@RequestBody`, nếu có validation failure mà không có `Errors`/`BindingResult` phù hợp ngay sau tham số thì Spring MVC thường phát sinh `MethodArgumentNotValidException`; cấu hình mặc định xử lý nó thành HTTP 400. Khi có method validation ở cấp chữ ký method, Spring MVC 6.1+ có thể phát sinh `HandlerMethodValidationException`. Nên thiết kế xử lý lỗi bao quát cả hai trường hợp.
- Record minh họa constructor binding; với mutable JavaBean, Spring có thể dùng property binding qua setter. Đừng giả định mọi trường JSON/form đều được bind tự động ở cùng một cách.

### 3.2. Chỗ đặt custom validator, converter và điều khiển dữ liệu được phép bind

Đối với quy tắc đầu vào riêng một form, có thể bổ sung Spring `Validator` thông qua `@InitBinder`; với chuyển đổi kiểu dùng `Converter`/`Formatter` (đăng ký chung qua `FormattingConversionService` hoặc cấu hình binder). `@ControllerAdvice` hỗ trợ áp dụng cấu hình có chủ đích cho nhiều controller.

Ví dụ cấu hình bind cho **mutable form DTO có hai setter `email` và `age`**:

~~~java
@InitBinder("registerRequest")
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("email", "age");
}
~~~

Đây là **mảnh code đặt trong controller**, với import `org.springframework.web.bind.WebDataBinder` và `org.springframework.web.bind.annotation.InitBinder`. Tên `registerRequest` phải khớp model attribute thực tế; các field được cho phép phải khớp DTO. Đối với immutable DTO dùng constructor binding, có thể ưu tiên chỉ bind qua constructor thay vì mở mọi setter.

Không bind request trực tiếp lên entity đang quản lý những trường nhạy cảm (ví dụ `role`, `isAdmin`, `balance`). Ưu tiên request DTO riêng và chỉ ánh xạ rõ các trường được chấp nhận; nếu dùng property binding thì khai báo `allowedFields`. Đây là giới hạn **những gì được phép thay đổi**, khác với validation vốn kiểm tra **giá trị có hợp lệ hay không**. Một field có thể mang giá trị hợp lệ nhưng vẫn không được phép do client cung cấp.

### 3.3. Phạm vi của WebFlux

Spring WebFlux cũng hỗ trợ các kiểu `@ModelAttribute`, `@RequestBody`, `@Valid` và binding/validation, nhưng cơ chế đọc body dùng `HttpMessageReader` và có thể xử lý kiểu reactive. Lỗi validation body trong WebFlux có thể là `WebExchangeBindException`; không copy nguyên logic bắt exception của MVC sang WebFlux. Những phần cốt lõi như ràng buộc dữ liệu, chuyển kiểu và Jakarta Bean Validation vẫn có thể được tái sử dụng.

## 4. Tầng service: tái sử dụng validation nhưng giữ nghiệp vụ độc lập HTTP

Service cần kiểm tra đầu vào đến từ **nhiều đường gọi**, không thể tin rằng caller luôn đi qua một controller có `@Valid`. Có hai cách chính:

1. **Gọi validator tường minh:** inject `jakarta.validation.Validator`, gọi `validate(command)`, xử lý `Set<ConstraintViolation<T>>` hoặc dùng Spring `Validator.validate(target, errors)`. Dễ kiểm soát trong service, job, consumer và kiểm thử, không phụ thuộc AOP.
2. **Method validation do Spring quản lý:** đặt `@Validated` trên Spring-managed service class, đặt constraint trên tham số/return và dùng `@Valid` để kiểm tra lồng bên trong command. Cần Bean Validation provider cùng hạ tầng `MethodValidationPostProcessor` (Spring Boot có thể tự cấu hình khi đủ dependency). Lời gọi phải đi qua Spring AOP proxy.

Ví dụ sau là **hai kiểu khai báo trong module service Spring**, có thể tổ chức vào hai tệp tương ứng nếu dùng class `public`; mục đích là minh họa method validation và quy tắc nghiệp vụ:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

record PurchaseCommand(
    @NotBlank String sku,
    @Min(1) int quantity
) {}

@Service
@Validated
class PurchaseService {
    public PurchaseCommand accept(@NotNull @Valid PurchaseCommand command) {
        if (command.quantity() > 100) {
            throw new IllegalArgumentException(
                "Mỗi đơn chỉ được tối đa 100 sản phẩm"
            );
        }
        return command;
    }
}
~~~

Trong ví dụ: `@NotNull` kiểm tra command không null; `@Valid` yêu cầu cascade vào `sku` và `quantity`; `@Min(1)` bắt số lượng tối thiểu; `quantity > 100` là quy tắc nghiệp vụ xử lý tường minh. Lời gọi qua Spring proxy với tham số sai có thể phát sinh `ConstraintViolationException` theo cấu hình mặc định của method validation; nhánh >100 phát sinh `IllegalArgumentException` của chính service. Không có HTTP status tự sinh trong service.

**Giới hạn AOP quan trọng:**

- Tự gọi từ method này sang method khác qua `this` của cùng instance (self-invocation) thường bỏ qua proxy, nên annotation trên method được tự gọi không được thực thi qua cơ chế AOP.
- Tự tạo instance bằng `new PurchaseService()` cũng không đi qua Spring container/proxy; annotation không tự chạy.
- Một service method chỉ có `@Valid` nhưng không được gọi qua cơ chế method validation hoặc không gọi validator tường minh thì không có bảo đảm validation sẽ chạy.
- Method validation và controller validation không có cùng exception hoặc điểm móc. Đừng cố dùng `BindingResult` của controller làm API phụ thuộc bên trong service.
- Service phải tiếp tục thực thi những bất biến như quyền truy cập, tồn kho và chuyển trạng thái trong transaction, kể cả khi DTO đã vượt qua mọi annotation.

Nếu service chỉ làm việc với dữ liệu đã được biểu diễn bằng Java object, thường **không cần bind lại**. Data binding thích hợp ở ranh giới nhập dữ liệu thô; gọi `DataBinder` nhiều lần qua các lớp làm phức tạp luồng và nguy cơ ghi đè trường.

## 5. Ứng dụng độc lập: sử dụng DataBinder không cần server hay Spring container

`DataBinder` là một lớp Java dùng được ngoài Servlet. Bạn có thể tạo instance, nhận `PropertyValues`, đăng ký `org.springframework.validation.Validator`, gọi `bind()` rồi `validate()`, sau đó lấy `BindingResult` để biết lỗi. Đây là cách hợp lý khi nhập dữ liệu dạng key-value từ CLI, CSV hoặc cấu hình và cần lợi ích chuyển kiểu/ghi lỗi của Spring.

Ví dụ dưới là **chương trình hoàn chỉnh** chạy với Java 17, Maven và Spring Framework 6.2.0; không dùng Spring Boot, `ApplicationContext` hay HTTP.

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>standalone-binding</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `src/main/java/StandaloneBindingDemo.java`:

~~~java
import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class StandaloneBindingDemo {

    public static class Profile {
        private String email;
        private int age;

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public int getAge() {
            return age;
        }

        public void setAge(int age) {
            this.age = age;
        }
    }

    public static class ProfileValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Profile.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Profile profile = (Profile) target;
            if (profile.getEmail() == null
                    || !profile.getEmail().contains("@")) {
                errors.rejectValue("email", "email.invalid");
            }
            if (profile.getAge() < 18) {
                errors.rejectValue("age", "age.tooYoung");
            }
        }
    }

    public static void main(String[] args) {
        Profile profile = new Profile();
        DataBinder binder = new DataBinder(profile, "profile");
        binder.setAllowedFields("email", "age");
        binder.setValidator(new ProfileValidator());

        binder.bind(new MutablePropertyValues(
            Map.of("email", "wrong-email", "age", "17")
        ));
        binder.validate();

        BindingResult result = binder.getBindingResult();
        System.out.println("age=" + profile.getAge());
        System.out.println("errors=" + result.getErrorCount());
        System.out.println("emailInvalid=" + result.hasFieldErrors("email"));
        System.out.println("ageInvalid=" + result.hasFieldErrors("age"));
    }
}
~~~

Chạy ở thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=StandaloneBindingDemo
~~~

Stdout do `main` in ra (bỏ qua log của công cụ build nếu môi trường có):

~~~text
age=17
errors=2
emailInvalid=true
ageInvalid=true
~~~

Giải thích từng bước:

1. `MutablePropertyValues` chứa chuỗi đầu vào, tương tự một hàng CSV hay map tham số; `DataBinder` nhận hai tên thuộc tính đã được whitelist.
2. Binder dùng cơ chế chuyển kiểu để đưa `"17"` vào thuộc tính `int age`, nên `getAge()` trả `17`.
3. `ProfileValidator` kiểm tra cấu trúc email tối thiểu và giới hạn tuổi; hai trường đều không hợp lệ nên ghi nhận hai `FieldError` trong `BindingResult`. Kiểm tra email trong demo chỉ phục vụ minh họa; ứng dụng thực cần tiêu chí email chuẩn hóa hơn, ví dụ Bean Validation `@Email` cùng yêu cầu nghiệp vụ.
4. `BindingResult` chứa lỗi để caller lựa chọn cách trình bày. Chương trình này không có MVC controller, request, HTTP response hay annotation `@Valid` mà vẫn binding và validation được.

Nếu đổi `"17"` thành `"abc"`, giai đoạn chuyển kiểu sang `int` thất bại và lỗi kiểu `typeMismatch` có thể được ghi lại ngay khi bind. Với dữ liệu CSV thực, cần phân biệt lỗi chuyển kiểu với lỗi validator và tránh giả định giá trị tuổi sau chuyển kiểu lỗi đã hợp lệ. Nếu **đã có sẵn đối tượng Java đúng kiểu** và chỉ cần kiểm ràng buộc, gọi `Validator` trực tiếp thường đơn giản hơn tạo `DataBinder`.

### Dùng Jakarta Bean Validation mà không cần DataBinder

Với đối tượng đã tạo sẵn, có thể gọi `jakarta.validation.Validator#validate(bean)` để lấy các `ConstraintViolation`. Trường hợp chạy độc lập cần thêm API Jakarta Validation và một provider phù hợp trên classpath, khởi tạo `ValidatorFactory` hoặc cấu hình qua Spring. Không cần servlet, nhưng không thể chỉ thêm annotation mà bỏ qua lệnh validate và mong quá trình kiểm tra tự diễn ra. Đối tượng nhận từ Jackson/CSV cũng cần được kiểm tra bằng lời gọi tương ứng.

## 6. Một quy tắc có thể xuất hiện ở nhiều điểm vào

Giả sử module đăng ký tài khoản chấp nhận dữ liệu từ trang web, job nhập CSV và dịch vụ nội bộ:

~~~text
HTTP form / JSON -----┐
                      ├──> Chuẩn hóa & kiểm tra DTO đầu vào
CSV / CLI ------------┤                      |
                      |                      v
Lời gọi nội bộ -------┘              Service / domain
                                             |
                                      Quy tắc nghiệp vụ
                                             |
                                      Lưu / phát sự kiện
~~~

- Ở **HTTP**: MVC xử lý binding và validation cho command; lỗi yêu cầu đi về response (ví dụ 400) với thông báo an toàn cho client.
- Ở **CSV/CLI**: adapter tự parse/bind hoặc tạo DTO rồi validate; lỗi gắn với số dòng/tên trường để báo cáo, không có status 400.
- Ở **service/domain**: bảo vệ bất biến chung bất kể nguồn gọi; nếu dùng method validation thì hạ tầng AOP phải hoạt động, hoặc lựa chọn gọi validator tường minh. Những kiểm tra đòi hỏi trạng thái hệ thống vẫn do service thực hiện.

Đặt ràng buộc thuần về cấu trúc (bắt buộc, định dạng, độ dài) ở DTO phù hợp từng use case, hoặc ở value object/domain khi đó thực sự là bất biến chung. Không nhất thiết phải dùng một DTO cho cả mọi tầng: contract HTTP, schema CSV, command nội bộ có thể khác nhau về dữ liệu được phép nhận và cách báo lỗi, trong khi vẫn chia sẻ validator hoặc chính sách kiểm tra chung nếu hợp lý.

### Khi nào chọn công cụ nào?

| Tình huống | Cách khuyến nghị |
| --- | --- |
| Nhận form/query trong Spring MVC | `@ModelAttribute` + binding/conversion + `@Valid`/`@Validated`, `BindingResult` khi cần xử lý lỗi tại controller |
| Nhận JSON trong Spring MVC | `@RequestBody` + message converter + `@Valid`/`@Validated`; xử lý exception đọc body và validation riêng |
| Kiểm dữ liệu trước khi service thực thi | `jakarta.validation.Validator` hoặc Spring `Validator` gọi tường minh; cân nhắc `@Validated` method validation nếu proxy phù hợp |
| Nhập CSV/map cấu hình trong chương trình không web | `DataBinder` + `PropertyValues` + `Validator` khi cần binding/chuyển kiểu; chỉ `Validator` khi object đã có |
| Kiểm quyền, tồn kho, trạng thái, giao dịch | Logic trong service/domain; không phụ thuộc vào việc controller đã validate |
| Cần thông báo lỗi tùy ngôn ngữ | Giữ mã lỗi/metadata trong `Errors`, `ConstraintViolation` và ánh xạ qua message catalog/adapter ở boundary |

## 7. Các sai lầm phổ biến và cách tránh

1. **Đồng nhất binding với validation:** object được tạo thành công không có nghĩa field hợp lệ. Áp dụng validation rõ ràng; ngược lại, một lỗi parse/chuyển kiểu có thể xảy ra trước validator.
2. **Cho rằng `@Valid` luôn tự chạy:** annotation cần môi trường có tích hợp validation hoặc lời gọi `Validator` thực tế; `new` service hay gọi method nội bộ qua `this` không đi qua Spring AOP proxy.
3. **Tin rằng đã validate ở controller thì service luôn an toàn:** job, consumer và service khác có thể gọi trực tiếp. Đưa bất biến nghiệp vụ vào service/domain và chọn cách bảo vệ contract phù hợp.
4. **Bind trực tiếp object miền có trường nhạy cảm:** kẻ gọi có thể gửi thuộc tính không mong muốn. Dùng DTO riêng, constructor binding khi phù hợp và `setAllowedFields` nếu cần property binding.
5. **Đặt `BindingResult` sai vị trí:** với chữ ký có tham số `@Valid @ModelAttribute` (hoặc request body phù hợp), `Errors`/`BindingResult` để xử lý lỗi cục bộ phải đứng ngay sau tham số đó.
6. **Xem lỗi MVC, WebFlux, method validation và lỗi nghiệp vụ như nhau:** chúng có exception và quy trình xử lý khác nhau. Tầng adapter ánh xạ lỗi thành response/log/report theo contract riêng.
7. **Nhầm `@Valid` với constraint trực tiếp:** `@Valid` dùng cho cascade validation; `@NotNull`, `@Min`, `@NotBlank` mới thực sự diễn đạt constraint. Trên method, constraint trực tiếp có thể khiến Spring MVC dùng method validation.
8. **Chỉ kiểm tra happy path:** thử thiếu field, kiểu sai, constraint sai, thuộc tính ngoài whitelist, gọi service từ nguồn không HTTP, lỗi nghiệp vụ sau khi DTO đã hợp lệ.

## 8. Tự kiểm tra để quyết định phạm vi

- **Có dữ liệu thô cần chuyển thành object không?** Có thì chọn binding/conversion ở điểm vào; không thì có thể chỉ cần validation.
- **Cần kiểm tra định dạng hay quy tắc nghiệp vụ?** Định dạng/ràng buộc cấu trúc đưa vào validator; điều kiện liên quan trạng thái, quyền, giao dịch ở service/domain.
- **Đầu vào từ HTTP hay từ nguồn khác?** Chọn cơ chế adapter và cách trình bày lỗi; bản thân các validator có thể không cần biết HTTP.
- **Có chắc validation được kích hoạt không?** Xác minh `@Valid` ở đúng vị trí, provider, `@Validated`/AOP khi dùng method validation hoặc lời gọi validator tường minh.
- **Có an toàn về trường được bind không?** Xác định DTO/constructor/allowed fields và tránh dùng entity có thuộc tính đặc quyền làm request target.
- **Có xử lý đầy đủ các dạng lỗi không?** Bao gồm binding, conversion, constraint, business, và lỗi malformed body; đừng suy luận một exception bao phủ mọi tầng.

## Tài liệu chính thức để tra cứu thêm

- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — Java Bean Validation và Method Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)

Các ví dụ web/service yêu cầu dependency và lifecycle của Spring tương ứng. Ví dụ `StandaloneBindingDemo` có `pom.xml` và lệnh chạy độc lập để kiểm chứng rằng validation/data binding không bị giới hạn ở tầng web.
