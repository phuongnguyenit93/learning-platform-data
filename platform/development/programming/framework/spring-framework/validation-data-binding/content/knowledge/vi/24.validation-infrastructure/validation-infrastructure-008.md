# Cấu hình META-INF/validation.xml và ánh xạ constraint bằng XML

## 1. Mục tiêu và bối cảnh

Jakarta Bean Validation thường khai báo các ràng buộc như `@NotBlank`, `@Size`, `@Min` ngay trong mã Java. Nhưng có những trường hợp cần **khai báo hoặc điều chỉnh quy tắc mà không sửa model**: domain class đến từ thư viện, DTO dùng lại ở nhiều ứng dụng, chính sách triển khai khác nhau, hoặc quy tắc xác thực do một module cấu hình riêng.

Jakarta Validation hỗ trợ **hai loại XML khác nhau**:

1. `META-INF/validation.xml`: cấu hình cách khởi tạo `ValidatorFactory` (provider, bộ nội suy thông điệp, lựa chọn method validation, danh sách tệp mapping, thuộc tính provider...).
2. **Constraint mapping XML**: mô tả chính xác constraint nào gắn vào class, field, getter, parameter, return value hay phần tử container; có thể thay thế hoặc kết hợp với annotation Java.

Trong ứng dụng Spring Framework, cấu hình XML này tác động đến Jakarta Validation **khi ứng dụng sử dụng `ValidatorFactory`/`Validator` được khởi tạo với các resource tương ứng**; nó không phải XML cấu hình Spring bean, cũng không phải cấu hình JSON data binding của Jackson.

Nội dung dưới đây tập trung vào **Jakarta Validation 3.0** và **Spring Framework 6 / Spring Boot 3**, sử dụng namespace `jakarta.validation.*`, Java 17 và Hibernate Validator 8. Với Spring 5/Boot 2 dùng namespace `javax.validation.*` và schema XML thế hệ cũ; không trộn cấu hình của hai hệ.

## 2. Chu trình nạp và quan hệ giữa hai tệp

Luồng cấu hình thường gặp:

```text
src/main/resources/META-INF/validation.xml
                  |
                  | <constraint-mapping>...
                  v
src/main/resources/META-INF/validation/customer-constraints.xml
                  |
                  | khai báo constraint cho demo.Customer
                  v
Validation.buildDefaultValidatorFactory()
                  |
                  v
Validator.validate(customer) -> Set<ConstraintViolation<Customer>>
```

Khi ứng dụng chạy, Maven/Gradle đóng gói nội dung `src/main/resources` lên **runtime classpath**. Jakarta Validation tìm `META-INF/validation.xml` khi khởi tạo `ValidatorFactory` (trừ khi được yêu cầu bỏ qua). Mỗi mục `constraint-mapping` trong file cấu hình tham chiếu đến một tệp mapping ở **classpath**; tên của mapping không bắt buộc phải là `constraints.xml`, miễn đường dẫn trỏ đúng resource.

**Lưu ý phân biệt:**

- `validation.xml` là tên và vị trí **quy ước bắt buộc** để tự phát hiện cấu hình mặc định.
- `customer-constraints.xml` là tên **tự đặt**, được khai báo trong `validation.xml` (hoặc đăng ký bằng API).
- Một tệp mapping có thể mô tả nhiều bean; một `validation.xml` có thể đăng ký nhiều tệp mapping.
- Chỉ tạo tệp mapping **không có nghĩa provider tự quét mọi XML**. Phải đăng ký qua `constraint-mapping`, `Configuration.addMapping(InputStream)` hoặc cơ chế tích hợp tương đương.
- Nếu trên runtime classpath có **nhiều hơn một** resource tên `META-INF/validation.xml`, Jakarta Validation quy định ném `ValidationException` khi dựng factory.

## 3. Cấu trúc dự án Maven mẫu

Ví dụ hoàn chỉnh sẽ dùng các file sau:

```text
validation-xml-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── Customer.java
        │       └── ValidationXmlDemo.java
        └── resources/
            └── META-INF/
                ├── validation.xml
                └── validation/
                    └── customer-constraints.xml
```

Khi đóng gói, hãy kiểm tra resource đã thực sự nằm trên classpath, chẳng hạn file `target/classes/META-INF/validation.xml` và `target/classes/META-INF/validation/customer-constraints.xml` có xuất hiện sau lệnh `mvn compile`.

Không đặt `validation.xml` dưới `src/main/java` rồi kỳ vọng provider phát hiện tự động. Cũng không ghi đường dẫn hệ điều hành dạng `C:\project\...` trong `constraint-mapping`: đó là **classpath resource name**.

## 4. Cấu hình toàn cục: `META-INF/validation.xml`

Tạo `src/main/resources/META-INF/validation.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<validation-config
    xmlns="https://jakarta.ee/xml/ns/validation/configuration"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/validation/configuration
        https://jakarta.ee/xml/ns/validation/validation-configuration-3.0.xsd"
    version="3.0">

    <constraint-mapping>
        META-INF/validation/customer-constraints.xml
    </constraint-mapping>

</validation-config>
```

**Ý nghĩa chính:**

- `validation-config`: root của tài liệu cấu hình, namespace riêng cho **configuration** (khác với mapping).
- `version="3.0"`: schema của Jakarta Validation 3.0.
- `xsi:schemaLocation`: gắn namespace với schema XSD tương ứng; file phải đúng cấu trúc và đúng thứ tự phần tử như XSD.
- `constraint-mapping`: đường dẫn đến XML khai báo các constraint cần tải. Khoảng trắng đầu/cuối trong nội dung phần tử thường được xử lý khi đọc resource name; để dễ kiểm tra đường dẫn, có thể viết trên **một dòng**: `<constraint-mapping>META-INF/validation/customer-constraints.xml</constraint-mapping>`.

Để loại trừ mọi khác biệt về việc xử lý whitespace trong các triển khai, cấu hình sản xuất nên ưu tiên cách **một dòng**. Các ví dụ phía dưới dùng đường dẫn chuẩn này.

### Các phần tử cấu hình đáng biết

| Phần tử trong `validation.xml` | Tác dụng |
| --- | --- |
| `<default-provider>` | Chọn lớp `ValidationProvider` cụ thể, ví dụ `org.hibernate.validator.HibernateValidator`; thường không cần ghi nếu classpath chỉ có một provider phù hợp |
| `<message-interpolator>` | Lớp `MessageInterpolator` để biến message template thành câu lỗi |
| `<traversable-resolver>` | Quyết định một thuộc tính có reachable/cascadable cho validation hay không |
| `<constraint-validator-factory>` | Cơ chế tạo `ConstraintValidator` |
| `<parameter-name-provider>` | Lấy tên tham số của method/constructor |
| `<clock-provider>` | Cấp `java.time.Clock` cho `@Past`/`@Future` |
| `<value-extractor>` | Đăng ký `ValueExtractor` cho các container |
| `<executable-validation>` | Thiết lập kiểu executable được xác thực theo cấu hình chuẩn |
| `<constraint-mapping>` | Đăng ký một XML mapping |
| `<property name="...">` | Thuộc tính thêm, thường do provider xác định |

Các phần tử là **tùy chọn** nhưng **thứ tự phải đúng schema**. Ví dụ Hibernate Validator cho phép:

```xml
<property name="hibernate.validator.fail_fast">true</property>
```

Khi bật chế độ fail-fast này, provider có thể dừng ngay sau vi phạm đầu tiên, khiến số lỗi trả về khác ví dụ phía dưới. Vì vậy, demo sử dụng cấu hình mặc định (không bật fail-fast). Thuộc tính `hibernate.validator.*` là **mở rộng riêng của Hibernate Validator**, không phải mọi provider đều hỗ trợ.

### Ưu tiên cấu hình

Nếu một phần tử trong `validation.xml` và API `Configuration` cùng cấu hình một hành vi, **giá trị do API lập trình đặt tường minh có ưu tiên** theo Jakarta Validation (ví dụ `configuration.messageInterpolator(...)` ưu tiên hơn cấu hình XML). Điều này khác với quy tắc kết hợp giữa annotation và mapping XML, được giải thích ở mục sau.

## 5. Constraint mapping XML: khai báo quy tắc trên model

Tạo `src/main/resources/META-INF/validation/customer-constraints.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<constraint-mappings
    xmlns="https://jakarta.ee/xml/ns/validation/mapping"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/validation/mapping
        https://jakarta.ee/xml/ns/validation/validation-mapping-3.0.xsd"
    version="3.0">

    <bean class="demo.Customer" ignore-annotations="false">

        <field name="code">
            <constraint annotation="jakarta.validation.constraints.NotBlank">
                <message>Code is required</message>
            </constraint>
            <constraint annotation="jakarta.validation.constraints.Size">
                <message>Code must be 3-8 chars</message>
                <element name="min">3</element>
                <element name="max">8</element>
            </constraint>
        </field>

        <field name="age">
            <constraint annotation="jakarta.validation.constraints.Min">
                <message>Age must be at least 18</message>
                <element name="value">18</element>
            </constraint>
        </field>

    </bean>
</constraint-mappings>
```

**Giải thích:**

- `constraint-mappings`: root trong namespace **mapping** của Jakarta Validation 3.0.
- `bean class="demo.Customer"`: ánh xạ đến Java class tên đầy đủ `demo.Customer`; nếu ghi thiếu package, có thể dùng phần tử `<default-package>demo</default-package>` ngay trước danh sách `bean`.
- `ignore-annotations="false"`: **giữ lại** constraint annotation Java của bean, đồng thời thêm các constraint khai báo qua XML.
- `field name="code"`, `field name="age"`: nhắm trực tiếp **field** trên class, không phải tên cột DB; tên phải tồn tại chính xác trong model.
- `constraint annotation="..."`: tên đầy đủ của **annotation constraint** đã tồn tại trên classpath, ví dụ `@NotBlank`, `@Size` và `@Min`.
- `message`: ghi đè thông điệp mặc định của constraint.
- `element name="min"`/`element name="max"`/`element name="value"`: đặt giá trị cho các thành phần cùng tên của annotation constraint. Kiểu dữ liệu và nội dung phải tương thích với khai báo annotation.

Chẳng hạn, `@Size(min = 3, max = 8)` trong Java tương đương đoạn XML:

```xml
<constraint annotation="jakarta.validation.constraints.Size">
    <element name="min">3</element>
    <element name="max">8</element>
</constraint>
```

Đoạn này chỉ là **fragment**, phải nằm đúng bên trong `<field>`/`<getter>`/phần tử mapping phù hợp; bản thân nó không phải file XML độc lập.

**Cảnh báo quan trọng:** nếu bỏ `ignore-annotations="false"` trong mẫu trên, giá trị mặc định của `ignore-annotations` tại `bean` là **`true`**. Khi đó annotation Java của `demo.Customer` có thể bị bỏ qua. Đây là khác biệt lớn so với kỳ vọng “XML mặc nhiên chỉ bổ sung annotation”.

## 6. Chạy thử Java 17: XML và annotation kết hợp ra sao?

### 6.1. Maven dependencies

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
             http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>validation-xml-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.5.Final</version>
        </dependency>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ValidationXmlDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Dependency `hibernate-validator` cung cấp Jakarta Validation provider; `expressly` cung cấp implementation của Jakarta Expression Language (EL) phục vụ message interpolation mặc định.

### 6.2. Model có annotation trên một field

Tạo `src/main/java/demo/Customer.java`:

```java
package demo;

import jakarta.validation.constraints.NotBlank;

public final class Customer {
    @NotBlank(message = "Name is required")
    private final String name;

    // Hai field này không gắn constraint Java;
    // chúng sẽ được ràng buộc bằng XML mapping.
    private final String code;
    private final int age;

    public Customer(String name, String code, int age) {
        this.name = name;
        this.code = code;
        this.age = age;
    }
}
```

`name` chịu ràng buộc **annotation**; `code` và `age` chịu ràng buộc **mapping XML**. Hibernate Validator có thể đọc các field private bằng reflection theo cơ chế field-level validation, nên ví dụ không cần getter.

### 6.3. Khởi tạo factory và so sánh khi bỏ qua XML

Tạo `src/main/java/demo/ValidationXmlDemo.java`:

```java
package demo;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import java.util.List;

public final class ValidationXmlDemo {
    private static List<String> errors(Validator validator, Customer bean) {
        return validator.validate(bean).stream()
                .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                .sorted()
                .toList();
    }

    public static void main(String[] args) {
        Customer invalid = new Customer("", "ab", 17);
        Customer valid = new Customer("Lan", "code123", 25);

        // Tự động đọc META-INF/validation.xml từ runtime classpath.
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            System.out.println("XML + Java invalid: "
                    + errors(validator, invalid));
            System.out.println("XML + Java valid: "
                    + errors(validator, valid));
        }

        // Tạo factory thứ hai, cố ý không đọc validation.xml
        // và các mapping được đăng ký qua file này.
        try (ValidatorFactory factory =
                     Validation.byDefaultProvider()
                             .configure()
                             .ignoreXmlConfiguration()
                             .buildValidatorFactory()) {
            System.out.println("Ignore XML invalid: "
                    + errors(factory.getValidator(), invalid));
        }
    }
}
```

Chạy bằng **JDK 17+** và Maven tại thư mục chứa `pom.xml`:

```bash
mvn -q clean compile exec:java
```

**Các dòng stdout do chương trình in** (không tính log của Maven hoặc provider):

```text
XML + Java invalid: [age: Age must be at least 18, code: Code must be 3-8 chars, name: Name is required]
XML + Java valid: []
Ignore XML invalid: [name: Name is required]
```

Vì mã Java đã gọi `sorted()`, thứ tự field trong kết quả là ổn định. Thứ tự phần tử của `Set<ConstraintViolation<?>>` vốn **không được bảo đảm**, nên không viết test dựa vào thứ tự chưa sort.

Đối chiếu:

| Chế độ | `name` | `code` | `age` |
| --- | --- | --- | --- |
| XML + annotation, `ignore-annotations="false"` | `@NotBlank` từ Java | `@NotBlank` và `@Size` từ XML | `@Min` từ XML |
| Bỏ `validation.xml` qua `ignoreXmlConfiguration()` | `@NotBlank` từ Java | Không có constraint trong demo | Không có constraint trong demo |

Khi `invalid = ("", "ab", 17)`, `name` sai vì chuỗi rỗng, `code` sai vì độ dài 2 nhỏ hơn 3, và `age` sai vì 17 nhỏ hơn 18. Với `valid = ("Lan", "code123", 25)`, cả ba field đều hợp lệ. Khi bỏ cấu hình XML, chỉ ràng buộc `@NotBlank` đặt trực tiếp trên Java còn tồn tại, nên chỉ có một lỗi `name`.

Hàm `ignoreXmlConfiguration()` áp dụng cho **factory đang xây dựng**. Nó không xóa `validation.xml` khỏi JAR, không vô hiệu hóa annotation Jakarta Validation trong Java, và không ngăn một ứng dụng khác chủ động đăng ký XML mapping bằng API `addMapping(...)`.

## 7. Khi nào XML bổ sung, khi nào XML thay thế annotation?

Cách xử lý phụ thuộc thuộc tính `ignore-annotations`:

| Khai báo trên bean | Hành vi đối với annotation trên bean đã mapping |
| --- | --- |
| `<bean class="demo.Customer">` | Mặc định là `ignore-annotations="true"`: bỏ qua constraint annotation trên bean đó |
| `<bean class="demo.Customer" ignore-annotations="true">` | Tường minh yêu cầu các khai báo XML thay thế annotation theo phạm vi tương ứng |
| `<bean class="demo.Customer" ignore-annotations="false">` | Giữ annotation Java **và** thêm constraint XML |

Có thể kiểm soát chi tiết hơn ở `class`, `field`, `getter`, `method`, `constructor`, `parameter` và `return-value`. Nếu một node con không khai báo `ignore-annotations`, nó kế thừa thiết lập từ node bao chứa theo quy tắc của đặc tả.

Ví dụ **fragment** sau minh họa bỏ riêng annotation ở field `name`, trong khi các annotation khác của bean vẫn được xét:

```xml
<bean class="demo.Customer" ignore-annotations="false">
    <field name="name" ignore-annotations="true">
        <constraint annotation="jakarta.validation.constraints.NotBlank">
            <message>Name is mandatory by XML policy</message>
        </constraint>
    </field>
</bean>
```

Đây là **cấu hình thay thế để minh họa**, không chèn thêm vào file mapping hoàn chỉnh ở mục 5, vì không nên khai báo `demo.Customer` hai lần trong cùng một tập XML mapping.

**Điều quan trọng:** cờ `ignore-annotations` áp dụng với bean/phần tử tương ứng. Nó không tự đổi cấu hình mọi bean khác trong ứng dụng và không tự động ngăn constraint được kế thừa từ superclass. Nếu annotation và XML cùng khai báo ràng buộc tương đương cho một thuộc tính mà `ignore-annotations="false"`, có thể xuất hiện **vi phạm trùng lặp**; hãy quyết định rõ muốn bổ sung hay thay thế.

## 8. Những kiểu mapping nâng cao

Ngoài `field`, mapping còn có các cấu trúc sau:

| Cấu trúc XML | Ứng dụng |
| --- | --- |
| `<class>` | Constraint cấp class; có thể mô tả `group-sequence` |
| `<getter name="property">` | Constraint tại getter/property thay cho field trực tiếp |
| `<valid/>` | Bật xác thực lan truyền tương đương `@Valid` |
| `<container-element-type>` | Constraint trên phần tử của `List`, `Map`, `Optional`... |
| `<method>` / `<constructor>` | Constraint trên tham số, kết quả trả về, cross-parameter |
| `<groups>` | Gán constraint vào một hoặc nhiều validation group |
| `<convert-group from="..." to="..."/>` | Chuyển group trong quá trình cascaded validation |
| `<constraint-definition>` | Thay hoặc bổ sung danh sách `ConstraintValidator` cho một **annotation constraint đã tồn tại** |

### 8.1. Constraint trên phần tử của collection

Ví dụ khác, giả sử class `demo.TagRequest` có field `List<String> tags`. Fragment XML bên trong một `<bean class="demo.TagRequest">` có thể viết:

```xml
<field name="tags">
    <container-element-type type-argument-index="0">
        <constraint annotation="jakarta.validation.constraints.NotBlank">
            <message>Tag must not be blank</message>
        </constraint>
    </container-element-type>
</field>
```

Với `List<String>`, type argument chỉ có index 0. Với `Map<K,V>`, key thường là index 0 và value là index 1. Không nhầm `<valid/>` (đi sâu vào object con) với constraint của chính giá trị collection element; mỗi cái có ý nghĩa riêng.

### 8.2. Method validation

Đối với một method `void register(String email)`, fragment bên trong `bean` cho class khai báo method đó có thể mô tả:

```xml
<method name="register">
    <parameter type="java.lang.String">
        <constraint annotation="jakarta.validation.constraints.NotBlank">
            <message>Email is required</message>
        </constraint>
    </parameter>
</method>
```

Đây chỉ là **khai báo metadata**; lời gọi method không tự bị chặn nếu không có cơ chế kích hoạt method validation. Với Jakarta Validation API, có thể gọi `Validator.forExecutables()`; trong Spring thường dùng cơ chế method validation phù hợp với phiên bản Spring và vị trí gọi. Method overload phải được mô tả bằng đúng danh sách tham số và kiểu.

### 8.3. `constraint-definition` không tạo ra một annotation mới

Ví dụ minh họa **thay validator** cho một annotation đã được định nghĩa trong mã:

```xml
<constraint-definition annotation="demo.ValidCode">
    <validated-by include-existing-validators="false">
        <value>demo.ValidCodeValidator</value>
    </validated-by>
</constraint-definition>
```

Cả `demo.ValidCode` và `demo.ValidCodeValidator` phải là class có thật với hợp đồng hợp lệ. `include-existing-validators="false"` thay danh sách validator từ annotation; `true` bổ sung validator XML vào danh sách có sẵn. Không thể tạo một kiểu annotation hoàn toàn mới chỉ bằng XML. Cũng không được định nghĩa lại cùng một constraint annotation nhiều lần trong một tập mapping của factory.

## 9. Áp dụng trong Spring Framework / Spring Boot

Trong Spring Boot 3 có `spring-boot-starter-validation`, thông thường Boot tạo một `LocalValidatorFactoryBean` làm validator Jakarta Validation. Khi provider được khởi tạo theo cơ chế mặc định và XML nằm trên classpath, `META-INF/validation.xml` cùng các mapping được tham chiếu sẽ được xem xét. Một DTO dùng trong controller có thể là class không có annotation ràng buộc Java, nhưng vẫn nhận constraint từ XML nếu mapping chỉ đúng class/field.

Đoạn minh họa trong một ứng dụng có Spring Web:

```java
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {
    @PostMapping("/customers")
    String create(@Valid @RequestBody CustomerRequest request) {
        return "accepted";
    }
}
```

`CustomerRequest` ở đây đại diện cho class DTO trong ứng dụng Spring và **không phải file trong Maven demo độc lập**. Nếu muốn xác thực field qua XML, phải khai báo `<bean class="...CustomerRequest">` với đúng tên class và property, rồi đảm bảo Spring MVC đang dùng factory đã tải mapping. Với `@Valid @RequestBody`, một constraint thất bại thường dẫn đến HTTP 400 do xử lý validation mặc định; định dạng response phụ thuộc handler của ứng dụng.

### Đăng ký mapping qua `LocalValidatorFactoryBean`

Spring còn cho phép nạp mapping bằng code khi không muốn khai báo phần `<constraint-mapping>` trong `validation.xml`. Ví dụ **một lựa chọn cấu hình thay thế**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
class ExplicitMappingConfig {
    @Bean
    LocalValidatorFactoryBean validator() {
        LocalValidatorFactoryBean factory =
                new LocalValidatorFactoryBean();
        factory.setMappingLocations(
                new ClassPathResource(
                    "META-INF/validation/customer-constraints.xml"
                )
        );
        return factory;
    }
}
```

**Đừng đồng thời khai báo cùng mapping** qua `<constraint-mapping>` trong `validation.xml` **và** `setMappingLocations(...)` của cùng một validator factory: có thể khiến một bean/constraint bị đăng ký lặp và gây `ValidationException`. Nếu đã dùng `validation.xml` để đăng ký mapping như demo, không cần cấu hình Spring ở trên. Nếu chọn `setMappingLocations`, hãy xóa mục đăng ký trùng trong `validation.xml` hoặc bỏ file cấu hình nếu không cần các thiết lập khác.

Khi ứng dụng có nhiều `Validator` / `ValidatorFactory` hoặc tùy biến `WebMvcConfigurer#getValidator()`, hãy xác minh chính instance đang thực thi validation đã được gắn mapping. Annotation `@Valid` chỉ **kích hoạt validation**, không tự quyết định nguồn XML nào được tải.

### XML mapping khác gì Spring DataBinder?

- `@Valid` và `Validator` áp dụng các **quy tắc Bean Validation** lên object đã có giá trị.
- `WebDataBinder`, Jackson và các converter xử lý **gắn dữ liệu/chuyển đổi kiểu**; constraint XML không tự thay đổi thuật toán parse JSON, conversion service hoặc binding errors.
- `LocalValidatorFactoryBean` là cầu nối từ Spring Validation đến Jakarta Validation provider. XML có hiệu lực khi nó nằm trong factory/provider tương ứng.

## 10. Thử nghiệm và chẩn đoán sự cố

### Xác minh resource có được đóng gói

Sau `mvn compile`, kiểm tra:

```text
target/classes/META-INF/validation.xml
target/classes/META-INF/validation/customer-constraints.xml
```

Có thể dùng Java để kiểm tra classloader tìm đúng resource:

```java
var loader = Thread.currentThread().getContextClassLoader();
System.out.println(loader.getResource("META-INF/validation.xml"));
System.out.println(
    loader.getResource("META-INF/validation/customer-constraints.xml")
);
```

Đây là **đoạn debug minh họa** đặt trong một phương thức Java, không phải chương trình độc lập. Nếu kết quả là `null`, hãy kiểm tra đường dẫn thực tế trong build output, cấu hình resource filter và classpath runtime.

### Kiểm tra metadata của constraint

Ngoài `validate()`, có thể truy vấn:

```java
var codeDescriptor = factory.getValidator()
        .getConstraintsForClass(Customer.class)
        .getConstraintsForProperty("code");

System.out.println(codeDescriptor != null);
```

Đoạn này dùng trong scope đang có `factory` và `Customer`; khi mapping đã tải, `codeDescriptor` tồn tại. Nếu thiếu mapping và field không có annotation, kết quả có thể là `null`. Truy vấn metadata là cách kiểm tra **ràng buộc thực sự đã được đăng ký**, không phụ thuộc hoàn toàn vào thông điệp lỗi.

### Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Constraint XML không chạy | `validation.xml` sai vị trí hoặc thiếu `constraint-mapping` | Kiểm tra resource trên runtime classpath và tên file |
| `ValidationException` lúc khởi tạo | Namespace/XSD/version sai, XML không đúng schema | Dùng namespace `https://jakarta.ee/xml/ns/validation/...` và version phù hợp |
| Annotation Java đột nhiên không còn hiệu lực | Mặc định `ignore-annotations="true"` tại `bean` | Đặt `false` nếu muốn kết hợp |
| Cùng một lỗi xuất hiện nhiều lần | Annotation và XML cùng ràng buộc hoặc field/getter khai báo trùng | Kiểm tra metadata, quyết định một nguồn cho mỗi quy tắc |
| Provider báo bean được mapping hai lần | Class khai báo trong nhiều tệp mapping hoặc đăng ký file lặp | Mỗi class chỉ ánh xạ một lần trong tập XML của factory |
| Class/field không tìm thấy | Tên class đầy đủ/field/getter sai | So khớp class/package và tên member của bytecode |
| Không nhận annotation `jakarta.validation.*` | Thư viện `javax.validation` của thế hệ cũ được trộn vào stack Jakarta | Đồng bộ Spring, provider, API và XML schema theo cùng thế hệ |
| Đặt `fail_fast=true` rồi thiếu lỗi | Provider dừng sau vi phạm đầu tiên | Tắt fail-fast khi cần tổng hợp đủ lỗi |
| Có mapping nhưng controller vẫn chấp nhận dữ liệu sai | Controller không kích hoạt validation hoặc dùng validator khác | Kiểm tra `@Valid`/`@Validated`, validator bean và cấu hình MVC |
| Bài test chỉ kiểm tra nội dung message | Message có thể thay đổi theo locale/resource bundle | Kiểm tra property path, annotation type, groups, số violations khi cần |

### Một số quy tắc của đặc tả cần nhớ

1. Các descriptor XML phải hợp lệ theo XSD tương ứng; cấu hình sai có thể gây `ValidationException` ở bước xây factory, trước khi gọi `validate()`.
2. Mỗi bean class chỉ nên được mô tả **một lần** trong tập constraint mappings của một validator factory; mỗi định nghĩa constraint annotation cũng chỉ được định nghĩa lại một lần.
3. Khi dùng `<getter>`, tên và kiểu property/method phải đúng theo quy tắc JavaBean/provider; tránh vô tình áp cùng constraint ở cả field và getter.
4. XML cho phép đặt giá trị annotation element, nhưng element và kiểu giá trị phải tồn tại và tương thích với annotation thực tế. Ví dụ `@Min.value` là `long`, `@Size.min` là `int`.
5. XML có thể mô tả `@Valid` (cascading), group, group conversion và method validation, nhưng việc kích hoạt kiểm tra ở điểm gọi vẫn do ứng dụng / framework điều phối.
6. Không dựa vào thông điệp mặc định nếu cần snapshot test ổn định; dùng message tường minh hoặc test theo metadata/violation code.
7. Cấu hình factory qua API lập trình có thể ưu tiên XML ở những thuộc tính trùng; nếu ứng dụng khởi tạo nhiều factory, chúng có thể áp dụng cấu hình khác nhau.

## 11. Checklist triển khai

- [ ] Tất cả dependency và import thuộc đúng thế hệ Jakarta Validation / Spring.
- [ ] Chỉ có một `META-INF/validation.xml` được nhận diện trên runtime classpath.
- [ ] `validation.xml` đúng namespace **configuration** và schema version.
- [ ] Constraint mapping đúng namespace **mapping**, schema version và classpath location.
- [ ] Mỗi class được mapping một lần, field/getter/method chính xác.
- [ ] Lựa chọn `ignore-annotations` có chủ đích: `false` để bổ sung, `true` để thay thế annotation trong phạm vi tương ứng.
- [ ] XML khai báo đúng type/name của constraint annotation và các `element`.
- [ ] Không đăng ký cùng mapping qua nhiều đường trên cùng validator factory.
- [ ] Có test cho dữ liệu hợp lệ, dữ liệu lỗi, annotation + XML và trường hợp bỏ XML.
- [ ] Với Spring MVC/service, kiểm tra validator thực sự được gọi và HTTP/error handling đúng kỳ vọng.

**Ghi nhớ:** `META-INF/validation.xml` quyết định **cách nạp cấu hình và mapping**; constraint mapping XML quyết định **quy tắc nào áp dụng lên bean**. Cờ `ignore-annotations` quyết định **ghép hay thay thế annotation Java**. Chỉ cần xác định đúng ba tầng này, cấu hình XML sẽ trở nên minh bạch và có thể kiểm thử.

## Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 specification — XML configuration and XML deployment descriptor](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Hibernate Validator 8 Reference Guide — Configuring via XML](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-xml-configuration)
- [Jakarta Validation Configuration API — ignoreXmlConfiguration()](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Configuration.html)
- [Spring Framework — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
