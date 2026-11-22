# DataBinder.NameResolver và tên tham số tùy chỉnh trong constructor binding

## 1. Vấn đề: tên trong request và tên tham số Java không luôn giống nhau

Khi Spring nhận dữ liệu cho một đối tượng, tên do phía ngoài gửi vào thường không khớp quy ước đặt tên trong Java. Ví dụ form hoặc URL có khóa **first-name**, trong khi constructor Java khai báo tham số **firstName**:

~~~text
Dữ liệu form/query: first-name=Lan&age=29

public Account(String firstName, Integer age)
                      ↑                ↑
              "first-name"          "age"
               cần ánh xạ         khớp sẵn
~~~

Nếu chỉ tra cứu theo **firstName**, binder không tìm thấy giá trị có khóa **first-name**. **DataBinder.NameResolver** giải quyết đúng vấn đề này trong **constructor binding**: nó quyết định **tên khóa đầu vào** mà DataBinder dùng để tìm giá trị cho *một tham số constructor*. Từ khóa cần nhớ là **ánh xạ tên khi tra cứu**, không phải đổi tên biến Java hoặc tự thay đổi nội dung của request.

Ngữ cảnh bài: phần **Gắn qua constructor** thuộc **Spring Framework – validation-data-binding**. Từ Spring Framework **6.1**, DataBinder hỗ trợ **NameResolver** và **ValueResolver** cho constructor binding. Trong Spring MVC, cách khai báo thông dụng là annotation **@BindParam**; khi cần annotation hay quy tắc tên khác, có thể cung cấp một **DataBinder.NameResolver** tùy chỉnh.

Đầu ra cần hiểu sau bài:

- Biết constructor binding diễn ra ở đâu và **NameResolver** tham gia bước nào.
- Sử dụng **@BindParam** để ánh xạ một tên tham số bên ngoài khác tên constructor.
- Biết viết **DataBinder.NameResolver** cho quy tắc/annotation riêng và hiểu cơ chế fallback.
- Phân biệt **NameResolver**, **ValueResolver**, chuyển đổi kiểu và Bean Validation.
- Nhận ra giới hạn, lỗi dễ mắc và yêu cầu an toàn khi binding dữ liệu HTTP.

## 2. Constructor binding và đường đi của một giá trị

**DataBinder** hỗ trợ hai kiểu gán dữ liệu liên quan:

1. **Constructor binding**: tạo đối tượng mới bằng constructor, tra cứu từng tham số, chuyển kiểu nếu cần, rồi truyền tham số cho constructor.
2. **Property binding**: sau khi có đối tượng, gán các thuộc tính qua setter hoặc cơ chế truy cập thuộc tính đã cấu hình.

**DataBinder.NameResolver** thuộc **kiểu thứ nhất**. Nó không phải bộ cấu hình toàn cục để thay thế mọi tên field ở bước property binding.

Sơ đồ khái niệm của constructor binding:

~~~text
Input names/values (ví dụ "first-name"="Lan", "age"="29")
          |
          v
DataBinder chuẩn bị tạo Account
          |
          v
Xét từng MethodParameter của constructor
          |
          +--> NameResolver.resolveName(parameter)
          |      |
          |      +--> "first-name" cho firstName
          |      +--> null nếu không quyết định tên riêng
          |
          +--> Fallback: tên tham số Java (nếu tìm thấy)
          |
          v
ValueResolver.resolveValue(lookupName, expectedType)
          |
          v
Chuyển kiểu nếu cần, ví dụ "29" -> Integer 29
          |
          v
new Account("Lan", 29)
          |
          v
DataBinder.getTarget() và BindingResult
~~~

Đây là thứ tự logic để học, không phải cam kết Spring luôn gọi chính xác từng hàm một lần trong mọi tình huống (nhất là object lồng nhau, collection và binding thất bại). Nếu target chưa được tạo thành công, **getTarget()** có thể vẫn là **null**, và phải kiểm tra **BindingResult**.

### Các vai trò không nên nhầm

| Thành phần | Nhận gì | Quyết định gì | Không chịu trách nhiệm |
| --- | --- | --- | --- |
| **DataBinder.NameResolver** | **MethodParameter** của constructor | Tên khóa cần tra cứu; có thể trả **null** | Không lấy raw value, không đổi kiểu, không validate |
| **DataBinder.ValueResolver** | Tên khóa cùng kiểu tham số | Giá trị thô ứng với tên đó; cung cấp tập tên hiện có | Không quyết định alias của tham số Java |
| **ConversionService** và editor/formatter | Giá trị đầu vào và kiểu đích | Cách đổi kiểu khi cần | Không tự gán alias tên tham số |
| **Constructor** | Các đối số Java đã chuẩn bị | Khởi tạo trạng thái đối tượng | Không tự đọc HTTP request |
| **Validator / @Valid** | Đối tượng hoặc đối số theo cơ chế validation | Kiểm tra ràng buộc được khai báo | Không tự sửa tên khóa/giá trị thô |

Thông thường Java constructor parameter **firstName** được tra theo tên **firstName**. Việc tìm được tên tham số Java dựa trên thông tin có sẵn, thường là metadata trình biên dịch tạo với **-parameters**. Nếu có alias rõ ràng qua resolver, tham số đó có thể được tra theo alias ngay cả khi tên Java và tên bên ngoài khác nhau.

## 3. Hợp đồng API của DataBinder.NameResolver

Đây là giao diện nằm trong **org.springframework.validation.DataBinder**:

~~~java
public interface NameResolver {
    String resolveName(org.springframework.core.MethodParameter parameter);
}
~~~

Đoạn trên là **chữ ký giản lược để giải thích**, không phải mã nguồn đầy đủ của Spring.

Một triển khai trả về:

- Một **String** khác **null**, chẳng hạn **"first-name"**: Spring dùng tên đó để tra cứu giá trị cho tham số đang xét.
- **null**: resolver không quyết định tên riêng; DataBinder quay về cơ chế phát hiện tên tham số mặc định (chẳng hạn **DefaultParameterNameDiscoverer**) nếu có thể.
- Không nên trả chuỗi rỗng để biểu diễn “không có alias”, bởi **""** vẫn là một tên, không phải tín hiệu fallback theo hợp đồng của giao diện.

Các API liên quan:

~~~java
binder.setNameResolver(customResolver);
DataBinder.NameResolver configured = binder.getNameResolver();
binder.construct(valueResolver);
~~~

Đây là các lời gọi minh họa cho một **DataBinder** đã được tạo và có **targetType** phù hợp. **setNameResolver(...)** cấu hình cách chọn tên; **construct(...)** thực sự thực hiện constructor binding. **getNameResolver()** có thể là null khi chưa được cấu hình.

**NameResolver chỉ được dùng để chọn tên cho constructor parameters** trong thao tác **construct(ValueResolver)**. Nó không làm cho **binder.bind(MutablePropertyValues)** tự hiểu tên cũ/mới của setter, không đổi tên property bên trong class và không định nghĩa contract phản hồi JSON.

## 4. Cách đơn giản nhất trong Spring MVC: @BindParam

Khi một tham số constructor cần tên đầu vào khác tên Java, Spring MVC hỗ trợ annotation:

~~~java
import org.springframework.web.bind.annotation.BindParam;

public final class CreateAccount {
    private final String firstName;
    private final Integer age;

    public CreateAccount(
            @BindParam("first-name") String firstName,
            Integer age) {
        this.firstName = firstName;
        this.age = age;
    }

    public String getFirstName() {
        return firstName;
    }

    public Integer getAge() {
        return age;
    }
}
~~~

Với một controller khai báo model attribute:

~~~java
@PostMapping("/accounts")
public String create(
        @Valid @ModelAttribute("account") CreateAccount account,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "account-form";
    }
    return "account-saved";
}
~~~

**Đây là hai đoạn minh họa để đặt vào ứng dụng Spring MVC**, cần import, controller, view và validation provider phù hợp; chúng chưa tạo thành một ứng dụng độc lập. Form gửi **first-name=Lan&age=29**. Khi Spring dùng constructor **CreateAccount(String firstName, Integer age)**, **@BindParam("first-name")** hướng binder tìm khóa **first-name** để cấp giá trị cho **firstName**. Tham số **age** vẫn dùng tên **age** thông thường.

Điều cần phân biệt:

- **@BindParam** được thiết kế cho **constructor binding** của model attribute, không phải một cách đổi tên mọi property.
- Có thể đặt **@BindParam** trên **constructor parameter** hoặc field tương ứng trong những trường hợp Spring hỗ trợ; đặt trực tiếp trên tham số constructor thường thể hiện ý định rõ nhất.
- **@ModelAttribute("account")** chỉ đặt tên model attribute là **account**. Nó **không** đổi tên constructor argument **firstName** sang **first-name**.
- **@RequestParam("first-name") String firstName** là cơ chế khác: tên dùng cho *tham số của handler method*, không phải ánh xạ constructor bên trong model attribute.
- **@RequestBody** JSON thường do Jackson **HttpMessageConverter** giải tuần tự; **@BindParam** và **DataBinder.NameResolver** không phải tùy chọn thay thế **@JsonProperty** để đổi tên JSON field khi Jackson tạo object.
- **@Valid** kích hoạt kiểm tra ràng buộc trong ngữ cảnh hỗ trợ sau/bên cạnh binding; nó không tự giải quyết alias.

**Lưu ý về DataBinder dùng trực tiếp:** Core **DataBinder** không tự suy đoán phải đọc **@BindParam** trong mọi cách khởi tạo thủ công. Muốn dùng annotation này trong ví dụ tự gọi **construct(...)**, cần cấu hình **setNameResolver(new BindParamNameResolver())**. Trong luồng **Spring MVC @ModelAttribute**, Spring cung cấp hỗ trợ **@BindParam** theo cấu hình web binding.

## 5. Khi cần tên tùy chỉnh ngoài @BindParam

Một hệ thống có thể phải chấp nhận tên đầu vào theo quy ước khác, ví dụ **customer_name**, **display-name**, hoặc tên do giao thức bên ngoài cố định. Nếu không muốn gắn tất cả trường với **@BindParam**, bạn có thể tạo annotation riêng và một resolver đọc annotation đó.

Ví dụ:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
public @interface ExternalName {
    String value();
}
~~~

Và constructor:

~~~java
public Account(@ExternalName("customer_name") String name,
               Integer age) {
    this.name = name;
    this.age = age;
}
~~~

Hai đoạn trên **chỉ là trích đoạn**; file chạy đầy đủ sẽ có import và khai báo class ở phần 6.

Một **NameResolver** có thể đọc annotation của tham số:

~~~java
DataBinder.NameResolver resolver = parameter -> {
    ExternalName annotation =
            parameter.getParameterAnnotation(ExternalName.class);
    return (annotation != null ? annotation.value() : null);
};
~~~

Trong tình huống tham số **name** có **@ExternalName("customer_name")**, resolver trả **"customer_name"**. Với **age** không có annotation, resolver trả **null**, để DataBinder tìm tên **age** theo metadata của constructor.

Có thể phối hợp resolver tùy chỉnh với **BindParamNameResolver** để vẫn hỗ trợ **@BindParam**:

~~~java
BindParamNameResolver builtIn = new BindParamNameResolver();

DataBinder.NameResolver combined = parameter -> {
    ExternalName external =
            parameter.getParameterAnnotation(ExternalName.class);

    if (external != null) {
        return external.value();
    }
    return builtIn.resolveName(parameter);
};
~~~

Đây là đoạn minh họa cho quy tắc ưu tiên: **@ExternalName** được thử trước, sau đó thử **@BindParam**, cuối cùng nếu kết quả null thì Spring tự phát hiện tên Java. Quy tắc ưu tiên là quyết định của ứng dụng, không phải một tính năng tự cấu hình mọi annotation.

## 6. Ví dụ Java 17+ hoàn chỉnh: mặc định, @BindParam và NameResolver riêng

Ví dụ Maven dưới đây **không cần chạy web server**. Nó chủ động tạo một **DataBinder** với target ban đầu bằng **null**, khai báo kiểu cần xây, cung cấp giá trị thô qua **ValueResolver**, rồi gọi **construct(...)**. Ba trường hợp cho thấy chính xác tên nào được dùng để tra cứu.

Sử dụng Java 17+ và các module **Spring Framework 6.2.6** ở cùng phiên bản. Để tái hiện ví dụ, cần Maven và khả năng tải dependency lần đầu.

Cấu trúc file:

~~~text
constructor-name-resolver/
├── pom.xml
└── src/main/java/demo/ConstructorNameResolverDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>constructor-name-resolver</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
            <version>6.2.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.ConstructorNameResolverDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/ConstructorNameResolverDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Map;
import java.util.Set;

import org.springframework.core.ResolvableType;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.validation.DataBinder;
import org.springframework.web.bind.annotation.BindParam;
import org.springframework.web.bind.support.BindParamNameResolver;

public final class ConstructorNameResolverDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface ExternalName {
        String value();
    }

    // Tên tham số Java trùng với tên của khóa đầu vào.
    public static final class DefaultPerson {
        private final String firstName;
        private final Integer age;

        public DefaultPerson(String firstName, Integer age) {
            this.firstName = firstName;
            this.age = age;
        }

        public String firstName() { return firstName; }
        public Integer age() { return age; }
    }

    // Một tham số dùng alias do @BindParam cung cấp.
    public static final class AliasedPerson {
        private final String firstName;
        private final Integer age;

        public AliasedPerson(
                @BindParam("given-name") String firstName,
                Integer age) {
            this.firstName = firstName;
            this.age = age;
        }

        public String firstName() { return firstName; }
        public Integer age() { return age; }
    }

    // Một tham số dùng annotation do ứng dụng tự khai báo.
    public static final class CustomPerson {
        private final String firstName;
        private final Integer age;

        public CustomPerson(
                @ExternalName("display_name") String firstName,
                Integer age) {
            this.firstName = firstName;
            this.age = age;
        }

        public String firstName() { return firstName; }
        public Integer age() { return age; }
    }

    private static <T> T create(
            Class<T> type,
            Map<String, String> rawInput,
            DataBinder.NameResolver nameResolver) {

        DataBinder binder = new DataBinder(null, "person");
        binder.setTargetType(ResolvableType.forClass(type));
        binder.setConversionService(new DefaultConversionService());

        if (nameResolver != null) {
            binder.setNameResolver(nameResolver);
        }

        binder.construct(new DataBinder.ValueResolver() {
            @Override
            public Object resolveValue(String name, Class<?> targetType) {
                // Đây là dữ liệu thô. DataBinder chịu trách nhiệm chuyển kiểu.
                return rawInput.get(name);
            }

            @Override
            public Set<String> getNames() {
                return rawInput.keySet();
            }
        });

        if (binder.getBindingResult().hasErrors()) {
            throw new IllegalStateException(
                    binder.getBindingResult().toString());
        }

        return type.cast(binder.getTarget());
    }

    public static void main(String[] args) {
        DefaultPerson first = create(
                DefaultPerson.class,
                Map.of("firstName", "Mai", "age", "23"),
                null);
        System.out.println("DEFAULT -> "
                + first.firstName() + " / " + first.age());

        AliasedPerson second = create(
                AliasedPerson.class,
                Map.of("given-name", "Lan", "age", "29"),
                new BindParamNameResolver());
        System.out.println("BIND_PARAM -> "
                + second.firstName() + " / " + second.age());

        DataBinder.NameResolver custom = parameter -> {
            ExternalName annotation =
                    parameter.getParameterAnnotation(ExternalName.class);
            return (annotation != null ? annotation.value() : null);
        };

        CustomPerson third = create(
                CustomPerson.class,
                Map.of("display_name", "An", "age", "31"),
                custom);
        System.out.println("CUSTOM -> "
                + third.firstName() + " / " + third.age());
    }
}
~~~

Ở thư mục chứa **pom.xml**, chạy:

~~~bash
mvn -q compile exec:java
~~~

Kết quả tiêu chuẩn của chương trình (không tính thông báo của Maven, nếu có):

~~~text
DEFAULT -> Mai / 23
BIND_PARAM -> Lan / 29
CUSTOM -> An / 31
~~~

### Phân tích kết quả

**DEFAULT:** constructor của **DefaultPerson** có tham số **firstName** và **age**, khớp hai khóa của **rawInput**. **nameResolver = null** nên DataBinder tra cứu theo tên tham số Java. Cấu hình Maven **parameters=true** bảo đảm metadata tên tham số được đưa vào bytecode. Chuỗi **"23"** được đổi thành **Integer 23** trước khi gọi constructor.

**BIND_PARAM:** **AliasedPerson** khai báo **@BindParam("given-name")** trên tham số **firstName**. Vì đây là **DataBinder** chạy thủ công, ví dụ đặt **new BindParamNameResolver()** thông qua **setNameResolver(...)**. Khóa ngoài **given-name** được tìm thấy; tham số **age** không có alias thì fallback về tên **age**. Kết quả là **Lan / 29**.

**CUSTOM:** resolver đọc **@ExternalName("display_name")** trên tham số **firstName** và trả **display_name**. Với **age**, nó trả **null** để Spring dùng tên Java **age**. Giá trị **"31"** được chuyển thành **Integer 31**, và đối tượng được tạo thành công.

Lưu ý: **getNames()** của **ValueResolver** trả tập tên đã cung cấp; nó còn hữu ích với constructor binding phức tạp gồm object lồng nhau và collection. **resolveValue(...)** của ví dụ cố ý chỉ lấy giá trị từ map, không tự parse Integer: mục tiêu là để DataBinder phụ trách bước conversion.

Nếu thay **"31"** bằng **"bad"**, việc tra đúng tên **age** vẫn không làm chuỗi trở thành một số nguyên hợp lệ. Cần kiểm tra **BindingResult** để phát hiện lỗi chuyển kiểu. Tách rõ lỗi “không tìm được khóa” khỏi lỗi “giá trị của khóa không đổi được kiểu”.

## 7. Tích hợp resolver vào WebDataBinder của Spring MVC

Trong ứng dụng Spring MVC, **@InitBinder** cấu hình một **WebDataBinder** dùng cho model attribute ở controller. Ví dụ minh họa cách đăng ký resolver khi ứng dụng dùng **@ExternalName**:

~~~java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.support.BindParamNameResolver;

@ControllerAdvice
public class AccountBinderAdvice {
    private final BindParamNameResolver builtIn =
            new BindParamNameResolver();

    @InitBinder("account")
    public void setup(WebDataBinder binder) {
        binder.setNameResolver(parameter -> {
            ExternalName alias =
                    parameter.getParameterAnnotation(ExternalName.class);
            return (alias != null
                    ? alias.value()
                    : builtIn.resolveName(parameter));
        });

        binder.setDeclarativeBinding(true);
    }
}
~~~

Đây là **đoạn cấu hình tích hợp**, cần khai báo hoặc import **ExternalName** của ứng dụng và lớp controller/model attribute tương ứng. **@InitBinder("account")** giới hạn cấu hình theo **tên model attribute account**, không phải tên tham số của constructor. Resolver hỗ trợ custom annotation trước, rồi **@BindParam**, rồi tên Java thông qua fallback.

**setDeclarativeBinding(true)** là một quyết định *riêng* về phạm vi binding: vẫn cho phép constructor binding, còn property binding chỉ được thực hiện khi khai báo **allowedFields** phù hợp. Nó không phải yêu cầu bắt buộc của **setNameResolver** nhưng hữu ích trong hướng thiết kế chỉ cho phép gán những trường được công bố.

Cần cân nhắc phạm vi **@ControllerAdvice** và xác thực rằng tên attribute khớp thực tế. Nếu resolver chỉ dùng cho một controller hoặc DTO, cấu hình cục bộ thường dễ quản lý hơn một thay đổi toàn ứng dụng.

### Khi nào không dùng NameResolver?

| Tình huống | API phù hợp hơn | Lý do |
| --- | --- | --- |
| Constructor model attribute cần alias khác tên Java | **@BindParam** hoặc **DataBinder.NameResolver** | Ánh xạ tên lúc tra cứu constructor argument |
| Handler muốn nhận tham số **?first-name=...** trực tiếp | **@RequestParam("first-name")** | Đặt tên cho một handler method argument, không tạo DTO |
| JSON **@RequestBody** có khóa **first_name** | **@JsonProperty("first_name")** hoặc cấu hình Jackson | Jackson đọc JSON thay vì DataBinder constructor mapping |
| Property binding cần ghi vào **userName** | DTO/setter phù hợp hoặc tiền xử lý input đúng hợp đồng | **NameResolver** không tự đổi khóa cho **bind(PropertyValues)** |
| Chuỗi **"29"** cần đổi thành **Integer** | **ConversionService**, converter/formatter | Đổi *giá trị*, không đổi tên khóa |
| Giá trị tuổi phải >= 18 | **@Min(18)** và validation phù hợp | Kiểm tra giá trị sau khi có kiểu hợp lệ |
| Endpoint cần ngăn client sửa field nội bộ | Constructor/DTO hẹp; **allowedFields** khi dùng property binding | Alias không phải cơ chế phân quyền |

## 8. Trường hợp biên và lỗi thường gặp

### 8.1. Tên gốc và tên alias đều có trong input

Ví dụ client gửi cả **firstName=Mai** và **given-name=Lan**, trong khi constructor dùng **@BindParam("given-name")**. Không nên ngầm cho rằng Spring sẽ so sánh hoặc kết hợp hai giá trị để kiểm tra xung đột. Với cấu hình ở phần 6, resolver yêu cầu tra cứu **given-name** cho tham số **firstName**. Một API cần quy định rõ tên nào hợp lệ, có chấp nhận tên cũ hay không và phản hồi thế nào khi cả hai cùng xuất hiện.

### 8.2. Alias bị thiếu

Nếu resolver trả **display_name** nhưng nguồn chỉ có **firstName**, không có phép “tự đoán tên gần giống”. **ValueResolver** có thể trả **null** vì thiếu khóa. Giá trị constructor được tạo ra hoặc lỗi phát sinh tùy kiểu tham số, ràng buộc, quy tắc mặc định và cấu hình binding. Với một tham số **String** tham chiếu, constructor có thể nhận **null**. Nếu trường bắt buộc, hãy kiểm tra bằng validation và hợp đồng DTO; đừng nghĩ NameResolver tự bảo đảm field không thiếu.

### 8.3. Resolver trả null cho mọi tham số

Điều này *không* có nghĩa mọi tham số biến mất; DataBinder sẽ thử phát hiện tên tham số Java như bình thường. Với Java, nên biên dịch bằng **-parameters** để tránh phụ thuộc vào việc đoán tên hoặc bytecode không có metadata. Nếu không tìm được tên và không có thông tin thay thế, quá trình binding có thể thất bại hoặc không nhận đúng dữ liệu.

### 8.4. Alias không có quy tắc nhất quán

Các alias kiểu **display_name**, **display-name** và **displayName** có thể là ba khóa khác nhau. Viết resolver tự “đổi mọi dấu” có thể dẫn đến va chạm tên (hai field khác nhau cùng ra một tên) hoặc thay đổi ngầm hợp đồng API. Với schema quan trọng, ưu tiên annotation tường minh và kiểm tra các alias trùng hoặc xung đột.

### 8.5. Tên của nested object và collection

Constructor binding hỗ trợ object lồng nhau, **List**, **Map**, mảng và các khóa dạng **addresses[0].city**, **accounts[KEY].name** trong ngữ cảnh được Spring hỗ trợ. Alias của tham số constructor có thể ảnh hưởng tên gốc dùng để tra cứu chuỗi đường dẫn lồng nhau. Không nên tự ghép prefix hoặc giả định mọi trường con dùng cùng một quy tắc, nhất là khi resolver tùy chỉnh sử dụng tên chứa dấu chấm, dấu ngoặc hoặc ký tự đặc biệt.

### 8.6. Bind thành công chưa có nghĩa dữ liệu hợp lệ

Resolver chỉ tìm tên; **ConversionService** chuyển kiểu; **Bean Validation** và tầng nghiệp vụ kiểm tra ràng buộc. Khi form gửi **age=abc** mà tham số constructor là **Integer age**, lỗi conversion cần được biểu diễn qua **BindingResult** hoặc nhánh xử lý lỗi tương ứng trong MVC. Nếu form gửi **age=12**, chuyển kiểu thành công nhưng vẫn có thể vi phạm **@Min(18)**. Không nên thay lỗi cú pháp bằng lỗi nghiệp vụ một cách võ đoán.

### 8.7. Cho client quyết định alias và reflection tùy ý

Không dùng **NameResolver** để nhận chỉ dẫn tùy ý từ request rồi tra cứu bất kỳ tên property/class nào. Resolver nên dựa trên quy tắc cố định, schema đã phê duyệt hoặc annotation do code kiểm soát. Input không tin cậy vẫn cần giới hạn các trường được chấp nhận, kích thước collection và dữ liệu đi qua validator. Dùng DTO riêng cho web thay vì bind thẳng domain entity chứa trường nhạy cảm.

## 9. Kiểm thử nên bao phủ những gì?

| Ca thử | Dữ liệu gửi | Kỳ vọng quan trọng |
| --- | --- | --- |
| Mặc định | firstName=Mai, age=23 | Tạo DTO từ tên Java; age thành Integer |
| Alias qua @BindParam | given-name=Lan, age=29 | firstName lấy từ given-name |
| Alias qua custom annotation | display_name=An, age=31 | firstName lấy từ display_name |
| Fallback null | age=31, resolver không nhận diện annotation age | age vẫn tra theo tên Java |
| Sai alias | firstName=Mai nhưng yêu cầu display_name | Không tự động tìm firstName thay cho alias |
| Sai kiểu | age=bad | Lỗi chuyển kiểu, không coi tên đúng là đủ |
| Trường bắt buộc bị thiếu | không có khóa firstName hay alias | Chính sách thiếu/null và validation phải được kiểm tra |
| Có cả tên cũ và alias | firstName=Mai, given-name=Lan | Hợp đồng phải quyết định tên nào được ưu tiên |
| Property binding sau constructor | thêm property không nằm trong DTO dự kiến | Không được để alias mở rộng quyền sửa dữ liệu |
| JSON @RequestBody | {"first_name":"Lan"} | Kiểm tra theo Jackson; không mặc định đi qua NameResolver |

Trong Spring MVC, dùng **MockMvc** để kiểm chứng tên request thực tế, việc tạo **@ModelAttribute**, **BindingResult** và lỗi ràng buộc. Với DataBinder thuần như phần 6, kiểm tra constructor nhận đúng tham số, **getTarget()** có object, **getBindingResult().hasErrors()** đúng dự kiến, và ValueResolver nhận các tên lookup mong đợi.

## 10. Bài tập thực hành

1. **Thêm alias thứ hai:** cho constructor **AliasedPerson** dùng **@BindParam("given_name")** thay vì **given-name**. Thay map đầu vào tương ứng và dự đoán stdout.
2. **Kiểm tra fallback:** bỏ **@ExternalName** khỏi tham số **firstName** của **CustomPerson**, đổi map từ **display_name** sang **firstName**, nhưng giữ resolver cũ. Vì sao nó vẫn hoạt động khi Maven bật **parameters=true**?
3. **Phối hợp annotation:** viết resolver dùng **@ExternalName** trước rồi **BindParamNameResolver** sau. Thử một constructor có một tham số gắn **@ExternalName**, tham số khác gắn **@BindParam**, và một tham số bình thường.
4. **Phân biệt conversion:** đổi tuổi hợp lệ từ **"31"** thành **"abc"**, xem **BindingResult**. Tên đã được resolve chính xác chưa, và lỗi nằm ở bước nào?
5. **Thiết kế API:** một dịch vụ phải nhận **first_name** từ hệ thống đối tác nhưng dùng **firstName** trong DTO Java. Hãy chọn một trong hai cách: **@BindParam** ở constructor hoặc custom resolver. Nêu tiêu chí dùng cách nào, cách kiểm tra alias và cách ghi lỗi ổn định.

## 11. Tài liệu chính thức

- [Spring Framework — Constructor Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): thứ tự khởi tạo DataBinder, targetType, construct và tùy biến tên tham số.
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): ví dụ **@BindParam** và giải thích NameResolver.
- [Spring Framework 6.2.6 — DataBinder.NameResolver](https://www.springframework.org/spring/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.NameResolver.html): chữ ký **resolveName(MethodParameter)** và fallback.
- [Spring Framework 6.2.6 — DataBinder.ValueResolver](https://www.springframework.org/spring/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.ValueResolver.html): **resolveValue(...)** và **getNames()**.
- [Spring Framework 6.2.6 — DataBinder](https://www.springframework.org/spring/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.html): **setNameResolver**, **setTargetType**, **construct** và **getBindingResult**.
- [Spring MVC — Data Binding Model Design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): DTO, constructor binding và kiểm soát property binding.

**Nguyên tắc cần nhớ:** **NameResolver** chỉ trả lời *“với tham số constructor này, phải tìm dữ liệu dưới tên nào?”*. **ValueResolver** trả lời *“tên đó có giá trị gì?”*; Spring chuyển kiểu và gọi constructor; validation đánh giá dữ liệu sau đó theo cấu hình. Dùng **@BindParam** cho alias đơn giản và resolver tùy chỉnh khi có quy tắc hoặc annotation riêng, đồng thời giữ hợp đồng input và phạm vi binding rõ ràng.