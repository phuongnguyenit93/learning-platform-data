# Phân biệt Jakarta Validation API và validation provider

## 1. Vì sao phải phân biệt ngay khi thiết lập?

Giả sử một ứng dụng Java có DTO với `@NotBlank` và `@Min`. IDE nhận diện được annotation, `mvn compile` thành công, nhưng khi chạy không có lỗi nào được phát hiện, hoặc ứng dụng báo không tìm thấy validation provider. Hai tình huống này chỉ giải quyết đúng khi tách bạch **API**, **provider** và **bước kích hoạt validation**.

- **Jakarta Validation API** là *hợp đồng chuẩn* (specification/API): định nghĩa annotation ràng buộc, các interface, đối tượng kết quả và cơ chế bootstrap. Artifact thường dùng là `jakarta.validation:jakarta.validation-api`; package là `jakarta.validation.*`.
- **Validation provider** là *thư viện hiện thực* hợp đồng đó: tìm constraint, tạo `ConstraintValidator`, kiểm tra giá trị, nội suy thông điệp và tạo `ConstraintViolation`. Một provider phổ biến là **Hibernate Validator**, artifact `org.hibernate.validator:hibernate-validator`. Apache BVal cũng là ví dụ provider khác.
- **Caller/trigger** là phần thực sự yêu cầu validation: mã gọi `jakarta.validation.Validator#validate(...)`, hoặc Spring MVC/Method Validation đã được cấu hình để gọi validator ở đúng điểm thực thi.

Có API giúp mã **biên dịch**. Có provider giúp API **có bộ máy kiểm tra**. Có trigger giúp quá trình kiểm tra **thật sự diễn ra**. Ba điều kiện không thay thế được nhau.

```text
Mã ứng dụng / Spring
  |  dùng @NotBlank, @Min, @Valid và Validator
  v
Jakarta Validation API (jakarta.validation.*)
  |  Bootstrap / SPI / hợp đồng thực thi
  v
Validation provider (ví dụ Hibernate Validator)
  |  Tìm metadata, chạy ConstraintValidator, nội suy thông điệp
  v
Set<ConstraintViolation<T>> -> ứng dụng hoặc adapter của Spring xử lý
```

**Điểm dễ nhầm:** `@Valid` là annotation trong API; chỉ gắn `@Valid` lên một object tự tạo bằng `new` không khiến validation tự chạy. Cần entry point có hỗ trợ, chẳng hạn `validator.validate(obj)` hoặc một đối số controller mà Spring MVC xử lý validation.

## 2. API chứa gì, provider bổ sung gì?

| Khía cạnh | Jakarta Validation API | Validation provider |
| --- | --- | --- |
| Vai trò | Mô tả hợp đồng chuẩn, kiểu dữ liệu và quy tắc tương tác | Cung cấp runtime thực thi hợp đồng |
| Maven coordinate | `jakarta.validation:jakarta.validation-api` | Ví dụ `org.hibernate.validator:hibernate-validator` |
| Các kiểu tiêu biểu | `Validation`, `Validator`, `ValidatorFactory`, `ConstraintViolation`, `ConstraintValidator` | Lớp bootstrap, metadata engine, validator implementations, message interpolation |
| Constraint chuẩn | Khai báo `@NotNull`, `@NotBlank`, `@Size`, `@Min`, `@Valid`… | Cung cấp logic kiểm tra các constraint khi ứng dụng chạy |
| Có thể biên dịch annotation? | Có, nếu API có trên compile classpath | Provider thường không cần trực tiếp trong source code |
| Có thể kiểm tra thật qua `validate`? | Không nếu chỉ có API | Có nếu provider tương thích được phát hiện và khởi tạo |
| Ràng buộc Spring? | Không | Không bắt buộc; Spring là một consumer/integrator |
| Đổi implementation? | Mã dùng API chuẩn thường giữ nguyên | Có thể chọn provider khác nếu tuân theo đặc tả và không phụ thuộc extension riêng |

Những API cốt lõi:

- `jakarta.validation.Validation`: điểm khởi tạo `ValidatorFactory` qua cơ chế bootstrap.
- `jakarta.validation.ValidatorFactory`: factory có thể cấu hình, được khởi tạo một lần và đóng khi ứng dụng kết thúc; cung cấp `Validator`.
- `jakarta.validation.Validator`: API để gọi `validate`, `validateProperty`, `validateValue` và truy cập metadata.
- `jakarta.validation.ConstraintViolation<T>`: mô tả lỗi của một constraint, có đường dẫn thuộc tính, thông điệp, giá trị không hợp lệ, descriptor.
- `jakarta.validation.ConstraintValidator<A, T>`: hợp đồng cho logic kiểm tra một annotation custom.
- `jakarta.validation.spi.ValidationProvider`: SPI để thư viện triển khai tham gia vào bootstrap.

**Cần phân biệt thêm:** `jakarta.validation.Validator` và `org.springframework.validation.Validator` là hai interface khác nhau. `Hibernate Validator` cũng là một dự án khác với `Hibernate ORM` dùng cho JPA; không thể suy ra Bean Validation đã sẵn sàng chỉ vì có Hibernate ORM.

## 3. Thử thiết lập chỉ có API: biên dịch được nhưng thiếu engine

Trong một dự án Maven Java SE, dependency API độc lập có thể khai báo:

```xml
<dependency>
    <groupId>jakarta.validation</groupId>
    <artifactId>jakarta.validation-api</artifactId>
    <version>3.0.2</version>
</dependency>
```

Khi đó các import sau có thể biên dịch:

```java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Min;
```

Một lớp dữ liệu cũng có thể khai báo constraint:

```java
record Account(@NotBlank String username, @Min(18) int age) {}
```

Nhưng nếu runtime classpath **chỉ có Jakarta Validation API, không có provider**, lệnh bootstrap:

```java
var factory = Validation.buildDefaultValidatorFactory();
```

không thể tạo một factory hoạt động. Trong kịch bản thiếu provider, API ném `jakarta.validation.NoProviderFoundException` (một loại `ValidationException`), thay vì tự đánh giá `@NotBlank` hoặc `@Min`. Không nên bắt exception rồi coi như "đã validation thành công": đó là **lỗi thiết lập**.

Ngoài ra, **có API và provider nhưng không có trigger** cũng làm annotation không được thực thi. Ví dụ chỉ tạo `new Account(" ", 16)` rồi lưu object, hoàn toàn không có lời gọi `validate` hay cơ chế framework tương ứng, thì không có lý do để kỳ vọng exception validation xuất hiện.

## 4. Thiết lập provider cho Java SE bằng Maven

Ví dụ dưới đây dùng Jakarta Validation API 3.0.2, Hibernate Validator 8.0.x tương thích và implementation Jakarta Expression Language cho nội suy thông điệp. Các phiên bản được **ghim để ví dụ tái lập được**; khi đưa vào dự án thực tế cần dùng bộ phiên bản tương thích với dependency management của dự án.

Cấu trúc thư mục:

```text
validation-setup/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApiProviderDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>validation-setup</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <!-- Hợp đồng chuẩn; provider cũng có thể kéo API transitively. -->
        <dependency>
            <groupId>jakarta.validation</groupId>
            <artifactId>jakarta.validation-api</artifactId>
            <version>3.0.2</version>
        </dependency>

        <!-- Implementation thực thi constraint. -->
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.6.Final</version>
        </dependency>

        <!-- Jakarta EL dùng cho message interpolation mặc định trong Java SE. -->
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
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

Lý do có dependency EL: theo tài liệu Hibernate Validator, cơ chế message interpolation mặc định hỗ trợ biểu thức Jakarta Expression Language. Trong môi trường Jakarta EE container, EL implementation có thể đã do container cung cấp; trong Java SE độc lập, thường cần thêm thư viện phù hợp. Không nhầm **EL implementation** với **validation provider**: EL chỉ hỗ trợ nội suy thông điệp; thêm EL không thể thay thế Hibernate Validator.

File `src/main/java/demo/ApiProviderDemo.java`:

```java
package demo;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.util.List;

public final class ApiProviderDemo {

    record Account(@NotBlank String username, @Min(18) int age) {}

    public static void main(String[] args) {
        Account account = new Account("   ", 16);

        try (ValidatorFactory factory =
                 Validation.buildDefaultValidatorFactory()) {

            // Kiểu của biến là API Jakarta, implementation nằm ở provider.
            jakarta.validation.Validator validator = factory.getValidator();

            List<String> errors = validator.validate(account).stream()
                .map(v -> v.getPropertyPath() + ":"
                    + v.getConstraintDescriptor()
                       .getAnnotation()
                       .annotationType()
                       .getSimpleName())
                .sorted()
                .toList();

            System.out.println("Errors: " + errors);
        }
    }
}
```

Từ thư mục `validation-setup`, với JDK 17+ và Maven đã cài:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ApiProviderDemo
```

Dòng kết quả do chính chương trình in ra (có thể còn thông báo logging từ provider tùy cấu hình):

```text
Errors: [age:Min, username:NotBlank]
```

Giải thích theo thứ tự:

1. `@NotBlank` và `@Min` được compiler nhận biết qua API.
2. `Validation.buildDefaultValidatorFactory()` dùng cơ chế bootstrap để tìm implementation.
3. Hibernate Validator được khởi tạo làm provider; `factory.getValidator()` trả validator theo interface chuẩn Jakarta.
4. `validator.validate(account)` kiểm tra dữ liệu và trả `Set<ConstraintViolation<Account>>`.
5. Chương trình chuyển các violation thành tên thuộc tính + tên annotation và sắp xếp để output ổn định; kết quả có hai lỗi vì username chỉ chứa khoảng trắng và age nhỏ hơn 18.

Nếu bỏ dependency `hibernate-validator` khỏi `pom.xml` nhưng giữ API và EL, chương trình vẫn biên dịch, song đến bước bootstrap sẽ gặp lỗi thiếu provider. Nếu bỏ bước `validator.validate(account)`, sẽ không có validation nào được yêu cầu. Hai thí nghiệm này phân biệt rõ ba khâu: **compile contract → runtime implementation → invocation**.

## 5. Bootstrap tìm validation provider như thế nào?

Jakarta Validation quy định cơ chế khám phá implementation qua SPI. Với bootstrap mặc định:

```java
try (var factory = Validation.buildDefaultValidatorFactory()) {
    var validator = factory.getValidator();
    // Sử dụng validator.
}
```

quá trình khái quát:

1. API dùng cơ chế provider resolution để tìm các implementation khả dụng trên runtime classpath/module path.
2. Theo cơ chế Java Service Provider, implementation có thể công bố service qua tài nguyên `META-INF/services/jakarta.validation.spi.ValidationProvider`. Hibernate Validator dùng lớp provider `org.hibernate.validator.HibernateValidator`.
3. Bootstrap chọn và cấu hình provider theo quy tắc của Jakarta Validation, tạo `ValidatorFactory`.
4. `ValidatorFactory` trả về `Validator` để thực thi validation trên object.

Tệp `META-INF/services/jakarta.validation.spi.ValidationProvider` là **service descriptor của provider**, không phải nơi ứng dụng đặt annotation cho DTO. Thông thường Maven/Gradle lấy tài nguyên này từ JAR provider; ứng dụng không cần tự tạo.

### Nếu có nhiều provider

Không nên dựa vào thứ tự JAR trên classpath để đoán provider nào được dùng. Có thể chỉ định rõ một implementation khi thật sự cần:

```java
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.hibernate.validator.HibernateValidator;

try (ValidatorFactory factory =
         Validation.byProvider(HibernateValidator.class)
             .configure()
             .buildValidatorFactory()) {
    var validator = factory.getValidator();
    // Kiểm tra đối tượng qua Jakarta API.
}
```

Đây là đoạn minh họa đặt trong method Java có khai báo hoặc xử lý exception thích hợp. Sử dụng `HibernateValidator.class` khiến mã **phụ thuộc trực tiếp** provider cụ thể: muốn biên dịch phải có artifact Hibernate Validator trên compile classpath, và đổi provider sẽ cần sửa mã. Khi chỉ cần portability, ưu tiên `buildDefaultValidatorFactory()`; khi cần provider nhất định, có thể dùng `Validation.byProvider(...)` hoặc cấu hình provider mặc định bằng `META-INF/validation.xml` theo đặc tả.

Ở môi trường classloader đặc biệt, như OSGi hoặc một số ứng dụng đóng gói tùy biến, cơ chế khám phá qua services có thể cần `ValidationProviderResolver` riêng. Với fat JAR được build bằng cách merge JAR thủ công, đừng làm mất các tệp `META-INF/services/*`; mất service descriptor có thể dẫn đến `NoProviderFoundException` dù class provider vẫn còn.

## 6. Spring Boot: khai báo dependency nào?

Với **Spring Boot 3.x** (sử dụng namespace `jakarta.validation.*`), cách thiết lập phổ biến là dùng starter validation; Boot dependency management chọn bộ dependency tương thích. Không cần gắn tay phiên bản Jakarta API và provider nếu dùng BOM/parent của Boot đúng cách.

Maven, trong dự án đã dùng Spring Boot parent/BOM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Gradle Groovy DSL, trong dự án đã cấu hình Spring Boot plugin/dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

Starter cung cấp các thành phần cần cho Jakarta Bean Validation, bao gồm provider Hibernate Validator ở cấu hình điển hình của Spring Boot. Nếu ứng dụng cũng cung cấp REST endpoints, thường thêm dependency Web riêng; starter validation tự nó **không** tạo controller hay HTTP server.

Ví dụ DTO dùng API chuẩn:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateAccountRequest(
    @NotBlank String username,
    @Min(18) int age
) {}
```

Ví dụ **minh họa** trong một Spring MVC controller thuộc dự án đã có Spring Web và Bean Validation:

```java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @PostMapping("/accounts")
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateAccountRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Đây **không phải** chương trình độc lập ở mục 4; cần dự án Spring Boot Web và file `CreateAccountRequest.java` riêng. `@Valid` trên tham số yêu cầu Spring MVC kích hoạt Bean Validation sau khi JSON đã được deserialize thành object. Với vi phạm ràng buộc của đối số request được validate theo đường này, Spring MVC thường tạo `MethodArgumentNotValidException`; nếu không có handler riêng, cơ chế mặc định có thể trả HTTP 400. Cần cấu hình error response phù hợp cho ứng dụng.

### LocalValidatorFactoryBean làm gì?

Spring cung cấp `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean`, khởi tạo Jakarta Validation provider theo cơ chế bootstrap và đồng thời thích ứng với:

- `jakarta.validation.Validator` / `jakarta.validation.ValidatorFactory`: phía API chuẩn.
- `org.springframework.validation.Validator`: phía `Errors`/`BindingResult` của Spring.

Trong dự án Spring Framework không dùng Boot, khi đã có Jakarta API và provider, có thể khai báo bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationConfig {
    @Bean
    public LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
```

Đoạn này là cấu hình Spring cần được quét/đăng ký trong ApplicationContext. `LocalValidatorFactoryBean` **không phải** một provider thứ hai: nó bootstrap và sử dụng provider thực sự, rồi tích hợp lỗi vào mô hình Spring. Khi dùng Boot, thường để auto-configuration thực hiện phần thiết lập này, chỉ tự đăng ký bean nếu có yêu cầu tùy chỉnh cụ thể.

**Phân biệt lỗi runtime:** Jackson/HTTP converter không đọc được JSON là lỗi deserialization/binding; object đã tạo nhưng không thỏa `@NotBlank`/`@Min` là lỗi constraint validation. Đừng gộp cả hai thành "thiếu validation provider".

## 7. Tương thích phiên bản và namespace

Khi thiết lập, ba lớp phụ thuộc cần cùng một thế hệ:

1. **API/spec**: namespace và phiên bản Jakarta Validation mà dự án/framework mong đợi.
2. **Provider**: implementation hỗ trợ phiên bản API đó.
3. **Tích hợp framework**: Spring Framework/Spring Boot, thư viện chuyển đổi lỗi và các thành phần liên quan.

Một cặp ví dụ có thể hoạt động là Jakarta Validation API 3.0.x và Hibernate Validator 8.0.x với JDK 17. Trong dự án Spring Boot, nên dùng tập phiên bản do BOM tương ứng quản lý thay vì sao chép cứng từ một ví dụ standalone.

| Môi trường | Import validation tiêu biểu | Hướng lựa chọn dependency |
| --- | --- | --- |
| Spring Framework 5 / Boot 2 (đời cũ) | `javax.validation.*` | API/provider tương thích thế hệ `javax` |
| Spring Framework 6 / Boot 3 | `jakarta.validation.*` | Starter validation hoặc API/provider tương thích Jakarta |
| Java SE dùng Jakarta Validation | `jakarta.validation.*` | API + provider + các runtime dependency cần thiết |
| Jakarta EE container | `jakarta.validation.*` | Kiểm tra provider và EL do container cung cấp trước khi thêm JAR |

**Không sửa bằng cách đổi mỗi import** từ `javax.validation` sang `jakarta.validation` mà giữ provider cũ không tương thích. Cũng không phải mọi artifact tên `hibernate-*` đều cung cấp `ValidationProvider`. Để kiểm tra chính xác những JAR được resolve, dùng dependency tree thay vì suy luận từ tên starter.

Ví dụ:

```bash
mvn dependency:tree
```

Hoặc với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Khi đọc dependency tree, kiểm tra **runtime classpath** có cả Jakarta Validation API và một provider tương thích. `compileOnly` hoặc `provided` dùng sai ngữ cảnh có thể khiến IDE biên dịch được nhưng provider không hiện diện lúc chạy. Trong bản đóng gói thực tế (Docker image, executable JAR), cũng phải xác nhận provider được đóng gói đúng.

## 8. EL, message interpolation và lỗi khởi tạo

Ngoài API/provider, Hibernate Validator thường cần implementation Jakarta Expression Language để xử lý đầy đủ nội suy thông điệp mặc định. Ví dụ:

```java
@Min(value = 18, message = "Tuoi phai tu {value}")
int age;
```

`{value}` là tham số message của constraint; bên cạnh đó, message template có thể chứa biểu thức EL. Provider chịu trách nhiệm xử lý message theo đặc tả. Khi chưa có EL implementation ở Java SE, provider có thể báo lỗi lúc khởi tạo message interpolator dù thư viện Hibernate Validator đã hiện diện.

Hibernate Validator có `org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator` cho môi trường không dùng EL:

```java
import jakarta.validation.Validation;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

try (var factory = Validation.byDefaultProvider()
        .configure()
        .messageInterpolator(new ParameterMessageInterpolator())
        .buildValidatorFactory()) {
    var validator = factory.getValidator();
    // Sử dụng validator.
}
```

Đây là **tùy chọn phụ thuộc Hibernate Validator**, không phải giải pháp tương đương hoàn toàn với thuật toán nội suy theo đặc tả khi có EL: template chứa biểu thức EL sẽ không được xử lý đầy đủ. Với ứng dụng thông thường, ưu tiên cung cấp EL implementation tương thích và giữ message interpolation chuẩn.

Nếu cần thông điệp được địa phương hóa, Jakarta Validation có cơ chế `ValidationMessages.properties` và các bundle locale tương ứng trên classpath. Trong Spring, `LocalValidatorFactoryBean` cũng cho phép tích hợp message source phù hợp. Thông điệp lỗi không được nội suy đúng có thể là vấn đề resource bundle/EL, độc lập với việc constraint có được đánh giá hay không.

## 9. Chẩn đoán khi thiết lập thất bại

| Triệu chứng | Nguyên nhân nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Compiler báo không có package `jakarta.validation` | Thiếu API trên compile classpath, hoặc dùng nhầm `javax`/`jakarta` | Thêm dependency/BOM phù hợp, sửa import theo phiên bản framework |
| `NoProviderFoundException` khi gọi bootstrap | Có API nhưng thiếu provider trên runtime classpath, hoặc service discovery bị hỏng | Thêm provider tương thích; kiểm tra dependency tree và `META-INF/services` |
| Provider có mặt nhưng khởi tạo message interpolator thất bại | Thiếu Jakarta EL implementation hoặc lệch phiên bản | Bổ sung EL tương thích; cân nhắc interpolator thay thế với giới hạn đã nêu |
| Có annotation nhưng dữ liệu sai vẫn đi qua | Không có lệnh `validate`, thiếu `@Valid` tại entry point, hoặc framework chưa bật validation phù hợp | Xác định chính xác điểm kích hoạt và kiểm tra cấu hình |
| `NoSuchMethodError`, `ClassNotFoundException`, `LinkageError` | API/provider/framework không tương thích hoặc classpath có bản trùng | Kiểm tra dependency resolution, BOM, bản đóng gói và namespace |
| Có nhiều provider và hành vi không như mong đợi | Provider mặc định không được chọn như dự kiến | Cấu hình provider tường minh, không phụ thuộc thứ tự JAR |
| `@NotBlank` không áp dụng với kiểu trường đang dùng | Constraint không hỗ trợ kiểu mục tiêu hoặc kiểu dữ liệu khác kỳ vọng | Kiểm tra constraint targets; `@NotBlank` dành cho chuỗi `CharSequence` |
| Có lỗi validation nhưng response REST sai định dạng | Spring chuyển lỗi thành exception/`BindingResult` nhưng ứng dụng thiếu xử lý response | Xây dựng handler thích hợp sau khi provider hoạt động |
| Provider không tìm thấy trong executable/fat JAR | Packaging làm mất thư viện hoặc service descriptor | Kiểm tra nội dung artifact cuối và cách merge service metadata |

Các bước kiểm tra tối thiểu, theo đúng thứ tự giảm thời gian tìm lỗi:

1. Xem dependency tree của **ứng dụng được chạy**; xác nhận API và provider có mặt ở runtime.
2. Xem package của annotation và API là `jakarta.validation` hay `javax.validation`; kiểm tra tính tương thích provider/framework.
3. Gọi thử `Validation.buildDefaultValidatorFactory()` ở một chương trình độc lập để phân biệt lỗi bootstrap với lỗi Spring/controller.
4. Gọi `validator.validate(new Account("   ", 16))` để xác nhận provider thật sự trả violation.
5. Nếu bootstrap thành công nhưng thông điệp không đúng, kiểm tra EL, bundle và locale; nếu Spring không kích hoạt, xem vị trí `@Valid`, `@Validated` và entry point.
6. Nếu lỗi chỉ xuất hiện sau khi đóng gói, kiểm tra classpath/service descriptor bên trong artifact triển khai.

## 10. Lưu ý thiết kế khi sử dụng lâu dài

- **Lập trình dựa trên API chuẩn:** class DTO, service và thư viện chia sẻ nên ưu tiên import `jakarta.validation.*`. Chỉ dùng extension của provider khi nó giải quyết một nhu cầu thật sự.
- **Để dependency management quản lý phiên bản:** với Spring Boot, ưu tiên starter/BOM. Với Java SE, khóa phiên bản API/provider/EL tương thích và kiểm tra dependency tree.
- **Tái sử dụng `ValidatorFactory`:** khởi tạo factory không phải thao tác cần làm cho mỗi request; tạo ở vòng đời ứng dụng, lấy `Validator` từ factory, đóng factory khi ứng dụng dừng. Trong Spring, để container quản lý bean này.
- **Không tạo provider bằng tay:** đi qua `Validation`/`ValidatorFactory` hoặc cấu hình tích hợp của Spring để tôn trọng SPI và vòng đời đối tượng.
- **Phân biệt errors và exceptions:** violation là kết quả kiểm tra dữ liệu không đạt yêu cầu; bootstrap exception là cấu hình ứng dụng sai. Không coi exception thiếu provider như một violation nghiệp vụ.
- **Chỉ tin vào hành vi đã kích hoạt:** annotation có trên model, dependency có trên classpath và request đã đi qua validator là ba điều kiện khác nhau; kiểm tra cả ba khi làm QA.

## 11. Câu hỏi tự kiểm tra

1. Vì sao chỉ khai báo `jakarta.validation-api` có thể biên dịch `@NotBlank` nhưng `Validation.buildDefaultValidatorFactory()` lại thất bại?
2. Hibernate Validator và `jakarta.validation.Validator` khác nhau ở vai trò nào? Khi thay provider, mã nào thường được giữ nguyên?
3. Tại sao thêm EL implementation mà không thêm provider vẫn không giải quyết `NoProviderFoundException`?
4. Khi Spring Boot 3 đã dùng `spring-boot-starter-validation`, có nên thêm thủ công nhiều phiên bản API/provider khác nhau không? Vì sao?
5. Nếu đã đủ API và provider nhưng object chỉ được tạo bằng `new`, cần thêm điều gì để phát hiện dữ liệu sai?
6. Khi đóng gói fat JAR, vì sao mất `META-INF/services/jakarta.validation.spi.ValidationProvider` có thể gây lỗi?

**Ghi nhớ:** Jakarta Validation API định nghĩa *giao ước*; validation provider thực thi giao ước; mã ứng dụng/Spring tạo *thời điểm gọi validation*. Thiết lập đúng phải thỏa cả phụ thuộc compile, phụ thuộc runtime và vị trí kích hoạt.

## Tài liệu tham khảo

- Jakarta Validation specification: https://jakarta.ee/specifications/bean-validation/
- Hibernate Validator 8.0 Reference Guide — Getting started, Provider discovery và Message interpolation: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework — Java Bean Validation và `LocalValidatorFactoryBean`: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Boot — Validation: https://docs.spring.io/spring-boot/reference/io/validation.html
