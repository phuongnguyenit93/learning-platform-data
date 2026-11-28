# Converter hoặc validation không được áp dụng

Khi một command nhận giá trị không đúng kiểu hoặc dữ liệu không hợp lệ, Spring Shell cần xử lý ở đúng bước: phân tích cú pháp, chuyển token thành kiểu Java, kiểm tra constraint rồi mới gọi command method. Nếu converter hoặc validation không chạy, nguyên nhân thường nằm ở ranh giới giữa các bước này: kiểu tham số không khớp converter, bean chưa được đăng ký, ứng dụng thiếu Bean Validation provider, constraint đặt sai kiểu dữ liệu hoặc lỗi bị exception handler che đi.

Bài học dùng Spring Shell 3.1.6, Spring Boot 3.1.x và mô hình command annotation legacy để minh họa. Các nguyên tắc chẩn đoán cũng áp dụng khi đăng ký command bằng **CommandRegistration**. Hãy đối chiếu version thực tế của ứng dụng trước khi áp dụng tên API hoặc cấu hình từ tài liệu của version khác.

## 1. Phân biệt conversion và validation

Hai cơ chế này giải quyết hai vấn đề khác nhau:

- **Conversion** chuyển token văn bản do người dùng nhập thành kiểu Java mà command yêu cầu.
- **Validation** kiểm tra giá trị đã được bind có thỏa mãn các ràng buộc hay không.

Ví dụ:

~~~text
project show --code OPS-1024
~~~

Command nhận tham số kiểu **ProjectCode**. Spring Shell phải chuyển chuỗi **OPS-1024** thành object **ProjectCode** trước khi method chạy. Sau đó, nếu command có constraint như **@NotNull** hoặc **@Pattern**, validator mới kiểm tra giá trị tương ứng.

Nếu người dùng nhập:

~~~text
project show --code invalid
~~~

và converter từ chối chuỗi này, lỗi xảy ra ở bước conversion. Method command chưa được gọi, vì vậy validation trong method không thể sửa lỗi parse đó.

Ngược lại, nếu converter tạo được object nhưng object không thỏa điều kiện nghiệp vụ, validation có thể từ chối trước khi command chạy hoặc service có thể từ chối trong use case.

## 2. Luồng xử lý input của Spring Shell

Có thể hình dung pipeline của một command như sau:

~~~mermaid
flowchart TD
    A["Người dùng nhập command"] --> B["Parser tách command, argument và option"]
    B --> C["Bind token vào tham số"]
    C --> D["ConversionService chuyển kiểu"]
    D --> E["Bean Validation kiểm tra constraint"]
    E --> F["Gọi command method"]
    F --> G["Service/domain kiểm tra quy tắc nghiệp vụ"]
    G --> H["Result handler hoặc exception resolver"]
    H --> I["Output và mã kết quả"]
    D -->|Conversion lỗi| J["Lỗi parse/conversion"]
    E -->|Constraint lỗi| K["ParameterValidationException"]
    G -->|Nghiệp vụ lỗi| L["Exception của ứng dụng"]
~~~

| Bước | Thành phần | Ví dụ lỗi |
|---|---|---|
| Parse | Spring Shell parser | Thiếu option bắt buộc, token không đúng cú pháp |
| Convert | Spring ConversionService | Không chuyển được chuỗi thành ProjectCode |
| Validate command | Bean Validation của Spring Shell | Tên rỗng, số lượng ngoài giới hạn |
| Execute | Command method | Logic command bị lỗi |
| Validate nghiệp vụ | Service/domain | Dự án đã tồn tại, trạng thái không cho phép |
| Handle result | Result handler/exception resolver | Lỗi bị đổi thành message không rõ hoặc bị che đi |

Khi điều tra, hãy xác định command method có được gọi hay không. Đây là dấu hiệu nhanh để phân biệt lỗi trước invocation với lỗi trong command hoặc service.

## 3. Nhận diện triệu chứng trước khi sửa

| Triệu chứng | Bước cần kiểm tra đầu tiên |
|---|---|
| Chuỗi nhập vào vẫn là String, dù tham số khai báo kiểu riêng | Converter và kiểu đích của tham số |
| Báo không tìm thấy converter | Bean registration và ConversionService đang dùng |
| Số hoặc enum không chuyển được | Token, target type và converter mặc định |
| Giá trị sai vẫn đi vào command method | Bean Validation provider và constraint |
| @NotBlank không báo lỗi | Kiểu tham số, import annotation và validation provider |
| @Valid không kiểm tra field bên trong object | Cascade validation và constraint trên object con |
| Service không từ chối giá trị sai | @Validated, method-validation proxy hoặc validation thủ công |
| Có exception nhưng terminal chỉ in message chung | Exception resolver/result handler |
| Chỉ lỗi trong test, chạy ứng dụng thật lại được | Test context, component scan hoặc dependency test |
| Chỉ lỗi ở một profile | Conditional bean, profile hoặc cấu hình ConversionService |

Đừng bắt đầu bằng cách thêm một converter hoặc validator mới. Trước hết xác định chính xác giá trị đầu vào, kiểu Java đích và lớp nào phải chịu trách nhiệm từ chối nó.

## 4. Kiểm tra chữ ký tham số command

Converter chỉ được dùng khi cặp kiểu nguồn và kiểu đích phù hợp. Với input từ terminal, kiểu nguồn thường là **String**. Kiểu đích được xác định bởi tham số method hoặc option registration.

Ví dụ:

~~~java
@ShellComponent
public class ProjectCommands {

    @ShellMethod("Show a project.")
    public String show(
            @ShellOption("--code") ProjectCode code) {
        return "Project code: " + code.value();
    }
}
~~~

Converter phải hỗ trợ chuyển từ **String** sang **ProjectCode**. Nếu converter được khai báo là **Converter<String, ProjectId>**, nó không áp dụng cho tham số **ProjectCode**.

Kiểm tra các điểm sau:

- Tham số command thực sự có kiểu đích mà bạn muốn chuyển đổi.
- Không khai báo tham số là **Object** hoặc **String** nếu mong muốn nhận kiểu domain.
- Không có wrapper hoặc generic type khiến target type khác với dự kiến.
- Annotation option trỏ đúng tên option mà người dùng truyền.
- Không có overload hoặc command khác đang được gọi.
- Không nhầm positional argument với named option.

Có thể kiểm tra bằng một command tạm thời trả về tên lớp và giá trị đã bind:

~~~java
@ShellMethod("Inspect a project code.")
public String inspect(@ShellOption("--code") ProjectCode code) {
    return code.getClass().getName() + ": " + code;
}
~~~

Nếu command không được gọi, lỗi nằm trước invocation. Nếu method chạy nhưng kiểu nhận được không như mong muốn, hãy kiểm tra lại chữ ký method và registration.

## 5. Đăng ký custom Converter đúng cách

Spring Shell dùng cơ chế chuyển đổi kiểu của Spring. Một converter cơ bản triển khai **org.springframework.core.convert.converter.Converter<S, T>**.

Ví dụ kiểu domain:

~~~java
public record ProjectCode(String value) {

    public ProjectCode {
        if (value == null || !value.matches("[A-Z]{3}-\\d{4}")) {
            throw new IllegalArgumentException(
                    "Project code must match AAA-1234");
        }
    }
}
~~~

Converter chuyển chuỗi thành kiểu domain:

~~~java
import java.util.Locale;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public class StringToProjectCodeConverter
        implements Converter<String, ProjectCode> {

    @Override
    public ProjectCode convert(String source) {
        String normalized = source.trim().toUpperCase(Locale.ROOT);
        return new ProjectCode(normalized);
    }
}
~~~

Khi converter là bean trong ApplicationContext, Spring Shell có thể sử dụng converter đó qua ConversionService được cấu hình cho command execution. Hãy bảo đảm converter được component scan hoặc được khai báo bằng **@Bean**.

Ví dụ command dùng converter:

~~~java
@ShellComponent
public class ProjectCommands {

    @ShellMethod("Show a project.")
    public String show(@ShellOption("--code") ProjectCode code) {
        return "Project code: " + code.value();
    }
}
~~~

Gọi:

~~~text
shell:> project show --code ops-1024
Project code: OPS-1024
~~~

### 5.1. Converter phải làm đúng một việc

Converter nên chuyển đổi và chuẩn hóa biểu diễn dữ liệu. Tránh đưa truy vấn database, kiểm tra quyền hoặc quy tắc nghiệp vụ phức tạp vào converter.

Ví dụ, converter có thể kiểm tra định dạng mã dự án. Việc mã đó có tồn tại hay người dùng có quyền xem dự án hay không nên do service/domain xử lý.

Nếu converter không thể chuyển đổi input, hãy ném exception không kiểm tra phù hợp, thường là **IllegalArgumentException** với thông báo ngắn gọn. Đừng trả về **null** để biểu diễn input sai, vì null có thể bị hiểu là một giá trị hợp lệ hoặc làm lỗi xuất hiện ở bước sau.

### 5.2. Chọn đúng loại converter

Spring cung cấp nhiều SPI:

| SPI | Dùng khi |
|---|---|
| **Converter<S, T>** | Một cặp kiểu nguồn/đích cụ thể |
| **ConverterFactory<S, R>** | Một nguồn chuyển thành nhiều kiểu đích thuộc cùng hierarchy |
| **GenericConverter** | Cần hỗ trợ nhiều cặp kiểu hoặc cần TypeDescriptor |
| **ConditionalGenericConverter** | Chỉ chuyển đổi khi điều kiện trên source/target type được thỏa mãn |

Bắt đầu với **Converter<String, ProjectCode>** cho một kiểu domain đơn giản. Chỉ dùng **GenericConverter** khi thực sự cần metadata hoặc nhiều cặp kiểu.

## 6. Những lý do converter không được gọi

### 6.1. Converter không phải Spring bean

Một class triển khai **Converter** nhưng không được đăng ký trong ApplicationContext sẽ không được component scan tự động tìm thấy.

Ví dụ dễ bị bỏ sót:

~~~java
public class StringToProjectCodeConverter
        implements Converter<String, ProjectCode> {
    // ...
}
~~~

Nếu class này không có stereotype annotation và không được khai báo trong cấu hình bean, converter không tồn tại trong context.

Có thể đăng ký bằng **@Component**:

~~~java
@Component
public class StringToProjectCodeConverter
        implements Converter<String, ProjectCode> {
    // ...
}
~~~

Hoặc khai báo bằng cấu hình:

~~~java
@Configuration
public class CliConversionConfiguration {

    @Bean
    StringToProjectCodeConverter stringToProjectCodeConverter() {
        return new StringToProjectCodeConverter();
    }
}
~~~

Đảm bảo package chứa converter nằm trong phạm vi component scan hoặc cấu hình được import vào application context.

### 6.2. Sai cặp kiểu nguồn và kiểu đích

Kiểm tra generic signature của converter:

~~~java
Converter<String, ProjectCode>
~~~

phải khớp với tham số:

~~~java
ProjectCode code
~~~

Các trường hợp không khớp thường gặp:

- Converter đích là ProjectId, nhưng command nhận ProjectCode.
- Converter nguồn là một kiểu khác với kiểu mà parser cung cấp.
- Command nhận List<ProjectCode> nhưng converter chỉ chuyển một chuỗi thành một ProjectCode.
- Converter được viết cho một DTO nhưng command đang nhận entity.

Nếu cần chuyển danh sách hoặc array, kiểm tra cách parser gom token và cách ConversionService chuyển đổi phần tử. Converter cho một phần tử không tự động chứng minh mọi dạng collection đều được hỗ trợ.

### 6.3. Custom ConversionService thay thế cấu hình mặc định

Một ứng dụng có thể khai báo ConversionService riêng. Nếu thay thế service mặc định mà không đăng ký lại converter cần thiết, Spring Shell có thể không còn thấy converter hoặc conversion mặc định mà bạn mong đợi.

Dấu hiệu thường gặp:

- Một số kiểu cơ bản trước đây chuyển được nhưng sau khi thêm bean ConversionService lại thất bại.
- Converter được inject ở một service khác hoạt động, nhưng command shell vẫn báo không convert được.
- Một custom converter chỉ có trong service được tạo thủ công, không có trong service dùng bởi command execution.

Cách xử lý:

1. Xác định ConversionService nào được dùng trong command execution.
2. Kiểm tra converter có được đăng ký vào đúng instance đó không.
3. Nếu thay thế service mặc định, thêm lại các converter mặc định cần thiết.
4. Tránh tạo nhiều ConversionService khác nhau mà không có lý do.
5. Kiểm tra bằng command shell thực tế sau khi cấu hình.

Spring Shell 3.1.x cung cấp API command execution nhận một ConversionService. Vì vậy, việc một bean converter tồn tại trong context chưa đủ để kết luận command đang dùng đúng service đó.

### 6.4. Converter không xử lý đúng biểu diễn đầu vào

Kiểm tra input thực tế mà parser chuyển tới converter:

- Có khoảng trắng đầu/cuối không?
- Có dấu nháy được parser loại bỏ hay giữ lại không?
- Có chữ hoa/thường không?
- Có prefix hoặc suffix không?
- Có dấu phân cách khác với format converter mong đợi không?
- Có Unicode hoặc ký tự escape không?

Ví dụ converter chờ OPS-1024 nhưng script truyền --code=OPS/1024. Hai chuỗi này khác định dạng, nên converter cần từ chối hoặc hỗ trợ format mới một cách có chủ đích.

### 6.5. Converter bị lỗi nhưng exception handler che mất nguyên nhân

Một converter có thể được gọi nhưng ném exception. Nếu exception resolver bắt mọi lỗi và chỉ in “Invalid input”, người phát triển không biết converter có được gọi hay không.

Trong môi trường phát triển, ghi log exception với cause và target type. Ở giao diện người dùng, chỉ hiển thị thông báo có ích, không lộ stack trace hoặc dữ liệu nhạy cảm.

## 7. Kiểm tra ConversionService có hỗ trợ cặp kiểu không

Có thể inject **ConversionService** để kiểm tra khả năng chuyển đổi:

~~~java
@Component
public class ConversionDiagnostics {

    private final ConversionService conversionService;

    public ConversionDiagnostics(ConversionService conversionService) {
        this.conversionService = conversionService;
    }

    public boolean supportsProjectCode() {
        return conversionService.canConvert(
                String.class,
                ProjectCode.class);
    }
}
~~~

Nếu trả về **false**, service được inject không có converter phù hợp cho cặp kiểu đó. Nếu trả về **true**, điều đó chỉ xác nhận service này có thể chuyển đổi; vẫn cần kiểm tra shell command đang sử dụng cùng ConversionService.

Có thể thử conversion trực tiếp trong test:

~~~java
assertThat(conversionService.canConvert(
        String.class, ProjectCode.class))
        .isTrue();

assertThat(conversionService.convert(
        "ops-1024", ProjectCode.class))
        .isEqualTo(new ProjectCode("OPS-1024"));
~~~

Không nên thêm một command chẩn đoán vào sản phẩm chỉ để kiểm tra converter. Dùng unit test hoặc test context phù hợp sẽ dễ kiểm soát hơn.

## 8. Kiểm tra validation của tham số command

Spring Shell tích hợp Bean Validation để kiểm tra constraint trên tham số command và method trước khi command được thực thi.

Ví dụ:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@ShellComponent
public class ProjectCommands {

    private final ProjectService projectService;

    public ProjectCommands(ProjectService projectService) {
        this.projectService = projectService;
    }

    @ShellMethod("Create a project.")
    public String create(
            @ShellOption("--name")
            @NotBlank
            @Size(max = 60)
            String name,

            @ShellOption("--priority")
            @Min(1)
            @Max(5)
            int priority) {

        projectService.create(name, priority);
        return "Created " + name + " with priority " + priority;
    }
}
~~~

Khi người dùng nhập tên rỗng hoặc priority ngoài khoảng 1–5, Spring Shell có thể báo constraint violation trước khi gọi method.

Ví dụ:

~~~text
shell:> project create --name "" --priority 7
The following constraints were not met:
...
~~~

Nếu command method vẫn chạy với giá trị không hợp lệ, hãy kiểm tra Bean Validation provider, annotation import, target type và cách command được đăng ký.

## 9. Cài Bean Validation provider

Các annotation như **@NotBlank**, **@Size** và **@Min** thuộc Jakarta Bean Validation. Chỉ có annotation API trên classpath chưa chắc đã có provider thực thi validation.

Với Spring Boot 3.1.x, dependency thường dùng là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Starter này cung cấp implementation Bean Validation, thường là Hibernate Validator, cùng các dependency cần thiết.

Kiểm tra:

- Dependency có nằm trên runtime classpath không, không chỉ test classpath.
- Có Bean Validation provider tương thích với Jakarta namespace không.
- Có vô tình loại trừ Hibernate Validator trong dependency exclusion không.
- Có dùng đúng version Spring Boot và dependency management không.
- Context có khởi tạo validator thành công không.

Spring Shell 3.x dựa trên Jakarta Validation. Nếu ứng dụng nâng từ Spring Boot 2 lên Spring Boot 3 mà còn import **javax.validation.***, các annotation cũ không thuộc namespace mà stack hiện tại sử dụng. Hãy đổi sang **jakarta.validation.***.

## 10. Chọn constraint đúng với kiểu dữ liệu

Một constraint chỉ áp dụng cho kiểu dữ liệu mà Bean Validation hỗ trợ. Chọn sai annotation có thể làm validation không hoạt động như mong muốn hoặc gây lỗi cấu hình.

| Constraint | Kiểu phù hợp | Mục đích |
|---|---|---|
| **@NotNull** | Object/reference | Không cho phép null |
| **@NotBlank** | String/CharSequence | Không null, không rỗng và phải có ký tự không phải whitespace |
| **@NotEmpty** | String, collection, map, array | Không null và không rỗng |
| **@Size** | String, collection, map, array | Giới hạn kích thước |
| **@Min**, **@Max** | Kiểu số được hỗ trợ | Giới hạn giá trị số |
| **@Positive**, **@PositiveOrZero** | Kiểu số | Yêu cầu số dương hoặc không âm |
| **@Pattern** | CharSequence | Kiểm tra biểu thức chính quy |

Ví dụ không phù hợp:

~~~java
@Min(1)
String quantity
~~~

**@Min** không phải constraint dành cho chuỗi. Nếu command nhận số lượng, hãy dùng kiểu số:

~~~java
@Min(1)
Integer quantity
~~~

Nếu input cần được kiểm tra theo pattern trước khi chuyển đổi, dùng **@Pattern** trên String hoặc dùng converter có quy tắc parse rõ ràng. Không mong một constraint chuỗi có thể chạy sau khi conversion đã thất bại.

### 10.1. Primitive và wrapper type

Primitive không thể chứa null:

- **int** mặc định là 0.
- **boolean** mặc định là false.
- **long** mặc định là 0L.

Nếu cần phân biệt “người dùng không truyền giá trị” với “người dùng truyền 0”, hãy cân nhắc wrapper như **Integer** hoặc **Long** và cấu hình option optional phù hợp.

Ví dụ:

~~~java
public String list(
        @ShellOption(defaultValue = ShellOption.NULL)
        @NotNull
        Integer limit) {
    // ...
}
~~~

Ở đây, parser có thể đưa null vào tham số nếu option không được cung cấp; **@NotNull** mới có cơ hội từ chối giá trị đó nếu validation được kích hoạt. Nếu đặt default value cụ thể, validation sẽ kiểm tra giá trị mặc định sau khi bind chứ không thể biết người dùng có chủ động nhập option hay không.

Required/optional và validation là hai khái niệm khác nhau. Dùng cấu hình option để quy định cú pháp bắt buộc; dùng constraint để kiểm tra giá trị đã bind.

## 11. Phân biệt @Valid và constraint thực tế

**@Valid** không phải constraint. Nó yêu cầu validator đi tiếp vào object lồng nhau để kiểm tra các constraint trên object đó.

Ví dụ:

~~~java
public record OwnerDetails(
        @NotBlank String username,
        @Email String email) {
}

public record CreateProjectRequest(
        @NotBlank String name,
        @Valid OwnerDetails owner) {
}
~~~

Nếu cần cascade validation cho **OwnerDetails**, tham số hoặc thuộc tính tương ứng phải được đánh dấu **@Valid** và object con phải có constraint cụ thể.

Một lỗi phổ biến là chỉ thêm:

~~~java
@Valid
CreateProjectRequest request
~~~

nhưng không có constraint trên field của request. Khi đó không có quy tắc nào để validator báo lỗi.

Cũng cần kiểm tra object có thực sự được truyền vào validation path hay không. Một DTO chỉ được tạo bên trong command method sau khi Spring Shell đã hoàn tất validation tham số sẽ không tự động được kiểm tra chỉ vì các field của nó có annotation.

## 12. Kiểm tra annotation import và vị trí khai báo

Có nhiều annotation cùng tên hoặc gần giống nhau trong các package khác nhau. Hãy kiểm tra import thực tế.

| Annotation | Package cần dùng trong Boot 3 |
|---|---|
| **@NotBlank**, **@Size**, **@Min** | **jakarta.validation.constraints.*** |
| **@Valid** | **jakarta.validation.Valid** |
| **@Validated** | **org.springframework.validation.annotation.Validated** |
| Validator Bean Validation | **jakarta.validation.Validator** |
| Validator của Spring | **org.springframework.validation.Validator** |

Đừng nhầm **org.springframework.validation.Validator** với **jakarta.validation.Validator**. Đây là hai API khác nhau:

- Jakarta Bean Validation dùng constraint annotation như **@NotBlank**, **@Size** và **@Valid**.
- Spring Validator là interface để tự triển khai logic kiểm tra object qua **supports** và **validate**.

Việc đăng ký một bean Spring Validator không có nghĩa Spring Shell sẽ tự động dùng nó để validate command parameter. Nếu cần gọi Spring Validator, hãy gọi nó rõ ràng tại ranh giới thích hợp hoặc tích hợp vào use case theo thiết kế của ứng dụng.

## 13. Phân biệt validation ở command và validation ở service

Spring Shell hỗ trợ validation của tham số command. Spring Boot cũng hỗ trợ method validation cho bean Spring, nhưng hai đường này có mục tiêu và cơ chế kích hoạt khác nhau.

### 13.1. Validation command parameter

Đây là validation chạy trước khi Spring Shell gọi method command. Ví dụ:

~~~java
@ShellMethod("Set a project priority.")
public String setPriority(
        @Min(1) @Max(5) int priority) {
    return "Priority set to " + priority;
}
~~~

Không cần gắn **@Validated** lên class command chỉ để minh họa cơ chế Bean Validation tích hợp của Spring Shell.

### 13.2. Validation trên service method

Nếu service được gọi từ nhiều adapter, có thể đặt constraint tại service:

~~~java
import jakarta.validation.constraints.Min;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class ProjectService {

    public Project findById(@Min(1) Long id) {
        // ...
    }
}
~~~

Trong Spring Boot 3.1.x, method validation được tự động cấu hình khi Bean Validation implementation có trên classpath. Class chứa method constraint cần được đánh dấu **@Validated** để Spring tạo method-validation proxy.

Một số nguyên nhân khiến service method validation không chạy:

- Thiếu provider như Hibernate Validator.
- Class không có **@Validated**.
- Gọi method nội bộ từ chính object thay vì đi qua Spring proxy.
- Tạo service bằng **new** thay vì lấy bean từ Spring.
- Bean không nằm trong ApplicationContext hoặc bị proxy/configuration thay đổi.
- Constraint đặt ở method khác với method thực sự được gọi.

Validation ở service có ích để bảo vệ use case khỏi mọi caller. Validation ở command giúp người dùng nhận lỗi input sớm và có thông báo gắn với cú pháp CLI. Nếu cả hai cùng kiểm tra một quy tắc, hãy thống nhất message và tránh tạo hai đường xử lý mâu thuẫn.

## 14. Kiểm tra validation group và custom constraint

Bean Validation mặc định chạy nhóm **Default** nếu không chỉ định group khác. Nếu constraint được gắn vào một group riêng, nhưng quá trình validation chỉ chạy group mặc định, constraint đó sẽ không được kích hoạt.

Ví dụ:

~~~java
public interface CreateChecks {
}

public record CreateProjectRequest(
        @NotBlank(groups = CreateChecks.class)
        String name) {
}
~~~

Nếu ứng dụng dùng group tùy chỉnh, hãy xác minh nơi gọi validator có truyền group đó không. Không giả định việc khai báo group trên annotation sẽ tự khiến Spring Shell chọn group tương ứng.

Với custom constraint, kiểm tra:

- Annotation có **@Constraint(validatedBy = ...)** không?
- Có **@Retention(RUNTIME)** không?
- **@Target** có chứa element type cần dùng không?
- Có khai báo **message**, **groups** và **payload** theo Bean Validation không?
- Validator có triển khai đúng **ConstraintValidator<A, T>** không?
- **isValid** trả về đúng kết quả với null theo hợp đồng constraint không?
- Có test cho giá trị hợp lệ, không hợp lệ và null không?

Nếu custom constraint không được gọi, kiểm tra metadata của annotation trước khi sửa Spring Shell.

## 15. Exception handling có thể che lỗi validation

Spring Shell 3.1.x có **ParameterValidationException** cho trường hợp một hoặc nhiều command parameter không thỏa Bean Validation constraint.

Nếu ứng dụng có exception resolver toàn cục bắt mọi **RuntimeException**, lỗi validation có thể bị biến thành message chung. Điều đó khiến người dùng nghĩ constraint không chạy.

Kiểm tra:

- Log có ghi nhận **ParameterValidationException** không?
- Resolver nào được gọi trước?
- Có resolver riêng cho command hoặc component không?
- Có resolver toàn cục bắt exception quá rộng không?
- Resolver có trả message phù hợp và giữ đúng mã lỗi không?
- Có vô tình trả kết quả thành công khi xử lý lỗi không?

Trong môi trường phát triển, ghi exception type và cause. Ở production, hiển thị thông báo rõ ràng nhưng không lộ dữ liệu nhạy cảm hoặc stack trace.

Đừng bắt mọi exception trong command rồi trả chuỗi rỗng. Cách đó có thể khiến command thất bại nhưng người dùng không biết nguyên nhân.

## 16. Quy trình chẩn đoán converter không được áp dụng

Làm theo thứ tự sau:

1. Ghi lại command và token chính xác mà người dùng nhập.
2. Xác định kiểu Java của tham số command.
3. Xác định converter cần hỗ trợ cặp source/target nào.
4. Kiểm tra converter có được đăng ký thành Spring bean không.
5. Kiểm tra component scan và profile.
6. Kiểm tra ConversionService được command execution sử dụng.
7. Kiểm tra **canConvert(String.class, TargetType.class)** nếu có thể inject service tương ứng.
8. Gọi conversion trực tiếp trong unit test.
9. Chạy command qua **ShellTestClient** để xác nhận đường parse thực tế.
10. Nếu converter được gọi nhưng thất bại, kiểm tra exception và input normalization.

Không sửa parser, option registration và converter cùng lúc. Thay đổi một yếu tố rồi chạy lại cùng input để biết nguyên nhân thực sự.

## 17. Quy trình chẩn đoán validation không được áp dụng

1. Xác định command method có được gọi hay không.
2. Kiểm tra constraint nằm trên đúng tham số hoặc method.
3. Kiểm tra import là **jakarta.validation.***.
4. Kiểm tra constraint phù hợp với kiểu dữ liệu.
5. Kiểm tra Bean Validation provider trên runtime classpath.
6. Kiểm tra command registration có đi qua Spring Shell command execution.
7. Kiểm tra constraint có thuộc group được chạy không.
8. Kiểm tra **@Valid** có được dùng cho object lồng nhau và object con có constraint không.
9. Nếu lỗi nằm ở service, kiểm tra **@Validated** và proxy.
10. Kiểm tra exception resolver có che **ParameterValidationException** hoặc **ConstraintViolationException** không.

Hãy dùng một input chắc chắn vi phạm constraint, ví dụ chuỗi rỗng cho **@NotBlank** hoặc số 0 cho **@Min(1)**. Đừng dùng một input có thể đã được converter chuẩn hóa thành giá trị hợp lệ.

## 18. Kiểm thử converter độc lập

Converter nên có unit test không cần khởi động shell.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class StringToProjectCodeConverterTests {

    private final StringToProjectCodeConverter converter =
            new StringToProjectCodeConverter();

    @Test
    void convertsLowercaseCodeToCanonicalForm() {
        ProjectCode result = converter.convert("ops-1024");

        assertThat(result.value()).isEqualTo("OPS-1024");
    }

    @Test
    void rejectsInvalidCode() {
        assertThatThrownBy(() -> converter.convert("invalid"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Unit test này chứng minh logic converter. Nó chưa chứng minh Spring đã đăng ký converter vào ApplicationContext hoặc Spring Shell đang sử dụng nó.

## 19. Kiểm thử converter qua command shell

Dùng **@ShellTest** để xác minh cả đường registration, parsing và conversion.

~~~java
import static org.awaitility.Awaitility.await;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
class ProjectCommandConversionTests {

    @Autowired
    ShellTestClient client;

    @Test
    void commandReceivesConvertedProjectCode() {
        var session = client.nonInterative(
                "project", "show",
                "--code", "ops-1024")
                .run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("OPS-1024"));
    }
}
~~~

Trong Spring Shell 3.1.x, tên method của non-interactive client là **nonInterative**. Các version mới hơn có thể đã sửa spelling; hãy dùng API đúng với version trong dự án.

Bổ sung test cho input sai:

~~~java
var session = client.nonInterative(
        "project", "show",
        "--code", "invalid")
        .run();
~~~

Chờ màn hình hiển thị thông báo conversion error hoặc thông báo do resolver của ứng dụng cấu hình. Không chỉ kiểm tra rằng test không ném exception, vì Spring Shell có thể bắt exception và đưa lỗi lên terminal.

## 20. Kiểm thử validation command parameter

Một test shell nên xác minh command không chạy khi constraint bị vi phạm. Có thể mock service để kiểm tra không có invocation.

~~~java
import static org.awaitility.Awaitility.await;
import static org.mockito.Mockito.verifyNoInteractions;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
class ProjectCommandValidationTests {

    @Autowired
    ShellTestClient client;

    @MockBean
    ProjectService projectService;

    @Test
    void blankNameIsRejectedBeforeCommandRuns() {
        var session = client.nonInterative(
                "project", "create",
                "--name", "",
                "--priority", "3")
                .run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("must not be blank"));

        verifyNoInteractions(projectService);
    }
}
~~~

Ví dụ giả định command gọi **ProjectService** sau khi validation thành công và message mặc định của provider có chứa đoạn **must not be blank**. Trong ứng dụng thực tế, dùng message ổn định do ứng dụng định nghĩa hoặc kiểm tra một đoạn phù hợp với locale đang dùng.

Nếu muốn kiểm tra method command không chạy, có thể dùng spy hoặc mock dependency mà command gọi. Đừng suy luận điều đó chỉ từ message trên terminal.

## 21. Kiểm thử service method validation

Nếu service được bảo vệ bằng **@Validated**, kiểm tra nó qua bean Spring thay vì tự tạo object bằng **new**.

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.validation.ConstraintViolationException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ProjectServiceValidationTests {

    @Autowired
    ProjectService projectService;

    @Test
    void rejectsNonPositiveId() {
        assertThatThrownBy(() -> projectService.findById(0L))
                .isInstanceOf(ConstraintViolationException.class);
    }
}
~~~

Test này cần Bean Validation provider và Spring method-validation proxy được cấu hình. Nếu gọi một method nội bộ từ cùng object, lời gọi có thể bỏ qua proxy; hãy kiểm tra đường gọi thực tế của ứng dụng.

Nếu Spring Boot đã tự cấu hình method validation từ dependency validation starter, không cần tạo thêm một **MethodValidationPostProcessor** khác trừ khi ứng dụng có lý do cấu hình riêng. Tránh đăng ký nhiều processor hoặc validator gây xung đột.

## 22. Bảng lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy converter | Converter không phải bean | Đăng ký @Component hoặc @Bean |
| Converter có bean nhưng command không dùng | Shell đang dùng ConversionService khác | Kiểm tra ConversionService của command execution |
| Chỉ một command không convert | Target type của tham số khác converter | So khớp source/target generic |
| Converter không nhận đúng chuỗi | Quote, whitespace hoặc tokenization | Ghi input thực tế và test token |
| Số hoặc enum lỗi conversion | Input không phù hợp format/constant | Kiểm tra token và kiểu tham số |
| Thêm ConversionService xong converter mặc định biến mất | Đã thay service mặc định mà không thêm lại converter | Giữ built-in converters và đăng ký custom converter |
| @NotBlank không chạy | Thiếu provider hoặc annotation sai namespace | Thêm validation starter, dùng Jakarta |
| @Min không áp dụng cho String | Constraint không phù hợp kiểu | Đổi sang kiểu số hoặc dùng @Pattern |
| @NotNull không bắt được 0 | Tham số primitive không thể null | Dùng wrapper hoặc constraint số |
| @Valid không báo lỗi | Không có constraint trên object con hoặc không cascade | Thêm constraint và kiểm tra @Valid |
| Service method validation không chạy | Thiếu @Validated hoặc gọi bỏ qua proxy | Gọi qua Spring bean proxy |
| Validation có chạy nhưng message chung | Exception resolver bắt lỗi quá rộng | Xử lý riêng validation exception |
| Chỉ test không thấy validation | Test thiếu provider hoặc test context không đăng ký command | Kiểm tra test dependencies và @ShellTest |
| Chỉ một profile bị lỗi | Converter/validator bị điều kiện profile loại bỏ | Kiểm tra bean theo profile |
| Constraint tùy chỉnh không chạy | Annotation metadata hoặc validator sai | Kiểm tra @Constraint, @Target, @Retention |

## 23. Checklist chẩn đoán nhanh

- [ ] Đã xác định command method có được gọi hay chưa.
- [ ] Đã ghi lại command và token đầu vào chính xác.
- [ ] Đã xác định kiểu Java đích của tham số.
- [ ] Converter có đúng source type và target type.
- [ ] Converter được đăng ký trong Spring ApplicationContext.
- [ ] Package converter nằm trong phạm vi component scan.
- [ ] Command execution dùng đúng ConversionService.
- [ ] Custom ConversionService vẫn có built-in converters cần thiết.
- [ ] Converter từ chối input sai bằng exception rõ ràng.
- [ ] Bean Validation provider có trên runtime classpath.
- [ ] Constraint dùng namespace jakarta.validation.
- [ ] Constraint phù hợp với kiểu tham số.
- [ ] Phân biệt @Valid với constraint như @NotBlank.
- [ ] Phân biệt command parameter validation với service method validation.
- [ ] Service method có @Validated khi cần AOP method validation.
- [ ] Lời gọi service đi qua Spring proxy.
- [ ] Exception resolver không che nguyên nhân.
- [ ] Có unit test cho converter và validation rule.
- [ ] Có shell test cho đường parse/conversion/validation thực tế.

## 24. Bài thực hành: sửa lỗi converter và validation trong Project CLI

Giả sử command hiện tại:

~~~java
@ShellComponent
public class ProjectCommands {

    private final ProjectService projectService;

    public ProjectCommands(ProjectService projectService) {
        this.projectService = projectService;
    }

    @ShellMethod("Create a project.")
    public String create(
            @ShellOption("--code") ProjectCode code,
            @ShellOption("--name") String name,
            @ShellOption("--priority") int priority) {
        projectService.create(code, name, priority);
        return "Created " + code + " / " + name;
    }
}
~~~

Người dùng phản ánh:

- **--code ops-1024** không được chuyển thành ProjectCode.
- **--name ""** vẫn được chấp nhận.
- **--priority 0** vẫn đi vào command method.

Thực hiện:

1. Viết unit test cho StringToProjectCodeConverter với input hợp lệ và không hợp lệ.
2. Đăng ký converter thành bean trong ApplicationContext.
3. Kiểm tra target type của tham số code.
4. Chạy shell test để xác minh converter thực sự được gọi.
5. Thêm spring-boot-starter-validation nếu ứng dụng chưa có provider.
6. Thêm @NotBlank cho name và @Min(1), @Max(5) cho priority.
7. Xác minh import annotation dùng Jakarta.
8. Viết shell test với name rỗng và priority bằng 0.
9. Kiểm tra service hoặc dependency không được gọi khi validation thất bại.
10. Kiểm tra exception resolver hiển thị lỗi rõ ràng.
11. Chạy test với cùng command trong non-interactive mode.
12. Ghi lại nguyên nhân, thay đổi và test bảo vệ regression.

Kết quả mong đợi:

~~~text
shell:> project create --code ops-1024 --name inventory-api --priority 3
Created OPS-1024 / inventory-api

shell:> project create --code invalid --name inventory-api --priority 3
Conversion error: expected project code such as OPS-1024

shell:> project create --code ops-1024 --name "" --priority 3
Validation error: name must not be blank

shell:> project create --code ops-1024 --name inventory-api --priority 0
Validation error: priority must be between 1 and 5
~~~

Thông báo trên chỉ minh họa kết quả mong đợi. Ứng dụng có thể dùng wording khác, nhưng phải phân biệt được conversion failure, constraint violation và business error.

## 25. Kết luận

Khi converter hoặc validation không được áp dụng, hãy tìm đúng bước trong pipeline của Spring Shell. Conversion xử lý việc biến token thành kiểu Java; Bean Validation kiểm tra constraint trên giá trị đã bind; service/domain bảo vệ quy tắc nghiệp vụ.

Đăng ký converter đúng cặp kiểu và trong đúng ApplicationContext/ConversionService. Với Bean Validation, bảo đảm provider có trên runtime classpath, dùng Jakarta namespace và chọn constraint phù hợp với kiểu dữ liệu. Dùng **@Valid** để cascade vào object lồng nhau; dùng **@Validated** cho method validation của Spring bean khi cần proxy.

Cuối cùng, kiểm tra bằng cả unit test và shell test. Unit test xác minh converter hoặc constraint riêng lẻ; shell test chứng minh command registration, parser, conversion, validation và exception handling phối hợp đúng trong ứng dụng thật.

## Tài liệu tham khảo

- [Spring Shell 3.1.6 Reference: Options and Validation](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1 API: CommandExecution](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/CommandExecution.html)
- [Spring Shell 3.1 API: ParameterValidationException](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/ParameterValidationException.html)
- [Spring Shell 3.1 API: ShellTestClient](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/test/ShellTestClient.html)
- [Spring Framework: Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework: Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework: Spring Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring Boot 3.1 Reference: Validation](https://docs.spring.io/spring-boot/docs/3.1.x/reference/htmlsingle/)

