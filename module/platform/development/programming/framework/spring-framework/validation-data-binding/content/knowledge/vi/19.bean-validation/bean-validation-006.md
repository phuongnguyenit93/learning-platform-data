# ConstraintViolation và tập kết quả vi phạm trong Bean Validation

## 1. ConstraintViolation giải quyết vấn đề gì?

Trong **Jakarta Bean Validation** (được Spring Framework tích hợp), một đối tượng có thể vi phạm nhiều ràng buộc cùng lúc: tên để trống, email sai định dạng, tuổi nhỏ hơn giới hạn và địa chỉ thiếu thành phố. Phương thức `jakarta.validation.Validator.validate(bean)` không chỉ trả về một thông báo “dữ liệu sai”; nó trả về **một tập `Set<ConstraintViolation<T>>`**, trong đó mỗi `ConstraintViolation<T>` mô tả một ràng buộc không đạt, vị trí liên quan và metadata về ràng buộc đó.

Ví dụ, một đơn đăng ký có thể đồng thời trả các vi phạm như sau:

| Đường dẫn (`propertyPath`) | Ràng buộc | Nội dung lỗi minh họa |
| --- | --- | --- |
| `name` | `@NotBlank` | `name is required` |
| `email` | `@Email` | `email is invalid` |
| `age` | `@Min(18)` | `age must be 18 or older` |
| `address.city` | `@NotBlank` trong đối tượng lồng nhau | `city is required` |

**Điểm then chốt:**

- **Không có vi phạm** → tập kết quả rỗng: `violations.isEmpty() == true`. Đây là điều kiện thường được dùng để quyết định dữ liệu hợp lệ đối với **những ràng buộc và nhóm đã được yêu cầu kiểm tra**.
- **Có một hoặc nhiều vi phạm** → tập chứa các đối tượng `ConstraintViolation<T>`. Mỗi đối tượng có thể cung cấp `getPropertyPath()`, `getMessage()`, `getInvalidValue()`, `getConstraintDescriptor()`, v.v.
- `Validator.validate(...)` **thường trả tập vi phạm, không tự ném `ConstraintViolationException` chỉ vì dữ liệu không hợp lệ**. Exception này có thể xuất hiện ở tầng gọi khác (ví dụ method validation qua AOP hoặc do ứng dụng chủ động ném).
- Tập `Set` **không cam kết thứ tự**. Nếu cần JSON lỗi ổn định, log dễ so sánh hoặc kiểm thử chính xác, hãy sắp xếp các phần tử sau khi đọc.
- Kết quả phản ánh **đợt validation cụ thể**; không phải một danh sách lỗi duy nhất và bất biến của đối tượng cho mọi thời điểm. Khi đối tượng đổi giá trị, nhóm validation đổi, hoặc cấu hình/provider đổi, kết quả có thể khác.

Đọc được tập vi phạm giúp trả về phản hồi rõ trường nào sai, hỗ trợ các form có nhiều lỗi đồng thời, viết test chính xác và tránh đánh đồng lỗi input với lỗi hạ tầng.

## 2. Ba thành phần chính và mối quan hệ

~~~text
Đối tượng Java + constraint annotations
    @NotBlank  @Email  @Min  @Valid ...
                  |
                  v
    jakarta.validation.Validator
       validate(bean, groups...)
                  |
                  v
  Set<ConstraintViolation<T>>
           /             \
       rỗng           có phần tử
         |                 |
    Hợp lệ theo       Đọc propertyPath,
    đợt kiểm tra      message, descriptor...
                           |
                    Ứng dụng quyết định
                    xử lý / ghi nhận lỗi
~~~

Phân biệt các khái niệm dễ nhầm:

| Thành phần | Vai trò |
| --- | --- |
| `jakarta.validation.Validator` | API chạy validation của Bean Validation; `validate`, `validateProperty`, `validateValue` đều trả một `Set<ConstraintViolation<T>>`. |
| `jakarta.validation.ConstraintViolation<T>` | Một kết quả **vi phạm đơn lẻ** kèm dữ liệu về đường dẫn, thông điệp, giá trị vi phạm và ràng buộc. |
| `Set<ConstraintViolation<T>>` | Tập các vi phạm thuộc một lần gọi. Không cần chuyển thành chuỗi sớm vì sẽ mất metadata quan trọng. |
| `jakarta.validation.ConstraintViolationException` | Exception có thể mang tập vi phạm qua `getConstraintViolations()`; không đồng nghĩa với kiểu dữ liệu trả về của `Validator.validate`. |
| `jakarta.validation.ValidationException` | Lỗi không thể khôi phục của hạ tầng validation, cấu hình hoặc provider; không phải “một field sai” theo nghĩa thông thường. |
| `org.springframework.validation.Errors` / `BindingResult` | Mô hình lỗi ở tầng Spring binding/validation; có thể bao gồm `FieldError` và lỗi chuyển đổi kiểu, không phải trực tiếp một `Set<ConstraintViolation<?>>`. |
| `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` | Cầu nối giữa Jakarta Validator và Spring Validator; khi dùng giao diện Spring, các vi phạm được thích ứng thành lỗi Spring. |

Từ Spring Framework 6 / Spring Boot 3, API tiêu chuẩn thuộc namespace `jakarta.validation.*`. Các dự án cũ Spring 5/Boot 2 có thể dùng `javax.validation.*`. Không ghép tùy tiện annotation `javax` với provider chỉ hỗ trợ `jakarta`.

## 3. Ba cách nhận tập vi phạm từ Validator

### 3.1. validate(bean, groups...) — kiểm tra đối tượng

~~~java
Set<ConstraintViolation<OrderForm>> violations =
    validator.validate(orderForm);
~~~

`validate(bean)` xét các ràng buộc áp dụng trên đối tượng, những thuộc tính của nó và **các nhánh được đánh dấu cascade `@Valid`** theo nhóm đang kiểm tra. Với input khác null, phương thức có thể trả tập rỗng hoặc nhiều vi phạm. Nếu truyền chính đối tượng nguồn là `null` vào `validator.validate(null)`, API báo `IllegalArgumentException`; đây không phải cách kiểm tra một trường nullable. Hãy đặt `@NotNull` ở thuộc tính/parameter tương ứng rồi validate đối tượng hoặc tham số chứa thuộc tính đó.

### 3.2. validateProperty(bean, "propertyName", groups...)

~~~java
Set<ConstraintViolation<OrderForm>> violations =
    validator.validateProperty(orderForm, "customerName");
~~~

Chỉ xét các constraint được khai báo trên property được chỉ định. Tên là tên property JavaBeans hợp lệ, **không phải biểu thức đường dẫn tùy ý**. Theo hợp đồng Bean Validation, `@Valid` **không được thực thi để cascade** từ `validateProperty`. Muốn kiểm tra toàn bộ cây đối tượng, hãy dùng `validate(bean)`.

### 3.3. validateValue(BeanType.class, "propertyName", value, groups...)

~~~java
Set<ConstraintViolation<OrderForm>> violations =
    validator.validateValue(OrderForm.class, "customerName", "");
~~~

Giả lập validation một giá trị thuộc tính **mà không cần tạo instance** của bean. Cách này hữu ích khi kiểm tra trường đơn trong biểu mẫu trước khi lưu. Vì không có instance gốc, các violation của `validateValue` có `getRootBean() == null` và `getLeafBean() == null`. `@Valid` không cascade ở chế độ này. `getRootBeanClass()` vẫn cho biết lớp bean liên quan.

So sánh:

| Phương thức | Có instance thật? | Phạm vi | Cascade `@Valid` | `getRootBean()` |
| --- | --- | --- | --- | --- |
| `validate(bean)` | Có | Bean và các nhánh được cascade | Có | Bean gốc |
| `validateProperty(bean, "x")` | Có | Các constraint trên property `x` | Không | Bean gốc |
| `validateValue(Type.class, "x", value)` | Không | Constraint trên giá trị giả lập cho `x` | Không | `null` |

Ba API đều có tham số varargs `Class<?>... groups`. Khi không truyền group, Bean Validation sử dụng nhóm `jakarta.validation.groups.Default`.

### 3.4. Method/constructor validation

Đối với ràng buộc trên tham số hoặc giá trị trả về của method/constructor, Jakarta Bean Validation có `ExecutableValidator` lấy qua `validator.forExecutables()`. Các phương thức như `validateParameters(...)` và `validateReturnValue(...)` cũng trả tập các `ConstraintViolation<T>`, nhưng `propertyPath` có thể chứa **node phương thức, node tham số, node return value**. Spring có cơ chế tích hợp method validation riêng, được trình bày ở mục 11.

## 4. Đọc một ConstraintViolation đúng cách

Giả sử:

~~~java
for (ConstraintViolation<OrderForm> violation : violations) {
    String path = violation.getPropertyPath().toString();
    String message = violation.getMessage();
    System.out.println(path + ": " + message);
}
~~~

Đây là đoạn minh họa cần có biến `violations`; thứ tự lặp của `Set` không được bảo đảm. Những phương thức chính:

| API | Dữ liệu trả về | Ý nghĩa thực tế |
| --- | --- | --- |
| `getMessage()` | `String` | Thông báo đã qua message interpolation, ví dụ `"must not be blank"` hoặc thông điệp tùy chỉnh. |
| `getMessageTemplate()` | `String` | Mẫu gốc, ví dụ `"{jakarta.validation.constraints.NotBlank.message}"`; có ích để phân biệt template với bản hiển thị. |
| `getPropertyPath()` | `jakarta.validation.Path` | Đường dẫn đến phần tử bị vi phạm từ root: property, phần tử collection, tham số method... |
| `getInvalidValue()` | `Object` | Giá trị **được chuyển cho constraint validator và không đạt**; có thể `null`, có thể là đối tượng hoặc phần tử collection. |
| `getRootBean()` | `T` hoặc `null` trong ngữ cảnh đặc biệt | Instance gốc được validate; `validateValue` không có instance nên trả null. |
| `getRootBeanClass()` | `Class<T>` | Loại bean gốc; vẫn hữu ích khi `getRootBean()` không có. |
| `getLeafBean()` | `Object` hoặc `null` | Bean gần constraint nhất, ví dụ bean `Address` khi `address.city` sai; `validateValue` trả null. |
| `getConstraintDescriptor()` | `ConstraintDescriptor<?>` | Metadata constraint bị vi phạm, annotation, thuộc tính `min`/`max`, groups, payload... |
| `getExecutableParameters()` | `Object[]` hoặc `null` | Tham số invocation nếu violation thuộc executable validation tương ứng. |
| `getExecutableReturnValue()` | `Object` hoặc `null` | Giá trị trả về của method/constructor khi phù hợp; có thể null nếu method trả null. |
| `unwrap(SomeProviderClass.class)` | Tùy provider | Mở API provider-specific; có thể ném `ValidationException` khi không hỗ trợ. |

**Không coi `getMessage()` là mã định danh lỗi ổn định**: thông điệp có thể thay đổi theo locale hoặc message bundle. Nếu API cần một `code` bền vững, có thể dùng loại annotation (ví dụ `NotBlank`), một mã nghiệp vụ riêng, hoặc metadata đã quy định. Cũng không trực tiếp đưa `getInvalidValue()` lên client; nó có thể chứa mật khẩu, email, token hoặc cả object graph.

### getMessage() so với getMessageTemplate()

~~~java
String rendered = violation.getMessage();
String template = violation.getMessageTemplate();
~~~

Ví dụ sử dụng `@Size(min = 2, max = 10)` với message mặc định: template có thể là khóa thông điệp, còn rendered trong một locale có thể là `size must be between 2 and 10`. Nếu annotation khai báo `message = "age must be 18 or older"`, cả hai có thể trùng nhau vì không cần nội suy.

Locale do cấu hình message interpolator và ngữ cảnh gọi quyết định. Trong Spring có thể tích hợp `MessageSource`, do đó test cần chọn cách kiểm tra phù hợp; tránh hardcode thông điệp tiếng Anh của provider vào API mà không kiểm soát locale.

### Metadata từ ConstraintDescriptor

~~~java
String annotationName = violation
    .getConstraintDescriptor()
    .getAnnotation()
    .annotationType()
    .getSimpleName();

Map<String, Object> attributes =
    violation.getConstraintDescriptor().getAttributes();
~~~

Ví dụ `@Min(18)` có thuộc tính `value = 18`. `getAttributes()` cũng có thể chứa `message`, `groups`, `payload` hoặc thuộc tính tùy biến. Metadata thích hợp cho logging nội bộ hoặc xây code trả về có kiểm soát; không nên serialize toàn bộ descriptor trực tiếp thành JSON, vì có thể chứa `Class<?>`, annotation và thông tin không cần thiết.

## 5. Hiểu propertyPath: từ field đơn đến collection lồng nhau

`getPropertyPath()` trả đối tượng `Path`, không phải chuỗi JavaBeans đơn thuần. Chuyển sang String bằng `toString()` thuận tiện cho thông báo, nhưng để xử lý cấu trúc chính xác có thể duyệt từng `Path.Node`.

| Ngữ cảnh | Đường dẫn minh họa | Điều cần hiểu |
| --- | --- | --- |
| Property trực tiếp | `email` | Một node thuộc tính. |
| Bean lồng nhau qua `@Valid` | `address.city` | Vi phạm nằm trong bean `Address` nhưng root vẫn là bean chứa nó. |
| Phần tử danh sách có constraint | `tags[1].<list element>` | Phần tử vị trí 1 của `tags` sai; dạng String chính xác tùy loại container và provider. |
| Giá trị trong Map | `labels[HOME].<map value>` | Key của Map có thể xuất hiện ở path. |
| Constraint cấp lớp | Đường dẫn rỗng đối với root bean | Không thể mặc định lỗi nào cũng có tên field. |
| Tham số phương thức | `submit.arg0` hoặc tên tham số thật | Tên tham số phụ thuộc metadata/parameter name provider; không coi `arg0` là API contract ổn định. |

Ví dụ duyệt node:

~~~java
import jakarta.validation.Path;

for (Path.Node node : violation.getPropertyPath()) {
    System.out.println(
        "kind=" + node.getKind()
        + ", name=" + node.getName()
        + ", inIterable=" + node.isInIterable()
        + ", index=" + node.getIndex()
        + ", key=" + node.getKey());
}
~~~

Đây là đoạn minh họa dùng biến `violation` đã có. Các node có thể có kind `PROPERTY`, `BEAN`, `CONTAINER_ELEMENT`, `METHOD`, `PARAMETER`, `RETURN_VALUE` v.v. Khi là phần tử list, `getIndex()` có thể giúp xác định vị trí; Map có thể dùng `getKey()`. Đừng dùng `String.split("\\.")` để parse mọi path: đường dẫn collection có ký hiệu chỉ mục/key và tên node đặc biệt.

### Những hiểu nhầm về root, leaf và invalid value

Với `OrderForm.address.city` bị `@NotBlank`:

- `getRootBean()` là instance `OrderForm` đã truyền cho `validate`.
- `getLeafBean()` thường là instance `Address` chứa property `city`.
- `getInvalidValue()` là giá trị `city` được kiểm tra, chẳng hạn `" "`; nó không phải mặc định cả `Address`.
- `getRootBeanClass()` là `OrderForm.class`.

Với constraint cấp class `@ValidOrder` trên root, `getPropertyPath()` có thể rỗng và `getInvalidValue()` có thể là toàn bộ đối tượng bị kiểm tra. Với `validateValue(...)`, root/leaf instance không tồn tại nên đều null. Với method/constructor validation, định nghĩa root/leaf còn phụ thuộc vị trí constraint; không áp một quy tắc field duy nhất cho mọi trường hợp.

## 6. Ví dụ runnable Java 17: thu thập bốn vi phạm và xử lý Set

Ví dụ này chạy bằng **Java 17 + Maven + Hibernate Validator 8.0.6.Final (Jakarta Validation 3.0)**. Hibernate Validator là một *implementation/provider* của Jakarta Bean Validation. Một mình dependency `jakarta.validation-api` chỉ chứa API, không cung cấp engine chạy validation.

Cấu trúc dự án:

~~~text
bean-validation-violations/
├── pom.xml
└── src/
    ├── main/java/demo/ViolationsDemo.java
    └── test/java/demo/ViolationsDemoTest.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-validation-violations</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.6.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
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

Dependency `org.glassfish.expressly:expressly` cung cấp Jakarta Expression Language cho message interpolation khi chạy standalone Java SE. Nếu chạy trong một môi trường đã cung cấp EL, chính sách dependency có thể khác.

Tệp `src/main/java/demo/ViolationsDemo.java`:

~~~java
package demo;

import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ViolationsDemo {

    static final class Address {
        @NotBlank(message = "city is required")
        private final String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Account {
        @NotBlank(message = "name is required")
        private final String name;

        @Email(message = "email is invalid")
        @NotBlank(message = "email is required")
        private final String email;

        @Min(value = 18, message = "age must be 18 or older")
        private final int age;

        @NotNull(message = "address is required")
        @Valid
        private final Address address;

        Account(String name, String email, int age, Address address) {
            this.name = name;
            this.email = email;
            this.age = age;
            this.address = address;
        }
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            Account invalid = new Account(
                " ", "not-an-email", 16, new Address(" "));

            Set<ConstraintViolation<Account>> violations =
                validator.validate(invalid);

            System.out.println("violations=" + violations.size());

            // Set không cam kết thứ tự; sort cho output ổn định.
            violations.stream()
                .map(v -> v.getPropertyPath() + " -> " + v.getMessage())
                .sorted()
                .forEach(System.out::println);

            Account valid = new Account(
                "An", "an@example.com", 21, new Address("Ha Noi"));
            System.out.println(
                "valid=" + validator.validate(valid).size());

            System.out.println(
                "property(name)=" +
                validator.validateProperty(invalid, "name").size());

            Set<ConstraintViolation<Account>> hypothetical =
                validator.validateValue(Account.class, "age", 16);

            System.out.println(
                "value(age)=" + hypothetical.size());
            System.out.println(
                "value-root-null=" +
                (hypothetical.iterator().next().getRootBean() == null));
        }
    }
}
~~~

Lệnh chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ViolationsDemo
~~~

Stdout do chương trình tạo ra (Maven và provider có thể in thêm log môi trường riêng):

~~~text
violations=4
address.city -> city is required
age -> age must be 18 or older
email -> email is invalid
name -> name is required
valid=0
property(name)=1
value(age)=1
value-root-null=true
~~~

**Phân tích vì sao chính xác bốn vi phạm:**

1. `name = " "` bị `@NotBlank` từ chối (String chứa khoảng trắng vẫn không phải văn bản có ký tự thực).
2. `email = "not-an-email"` không phải một địa chỉ email theo constraint `@Email`; `@NotBlank` không vi phạm vì chuỗi không rỗng.
3. `age = 16` nhỏ hơn `@Min(18)`.
4. `address.city = " "` vi phạm `@NotBlank`. Constraint được tìm thấy vì field `address` có `@Valid` yêu cầu cascade xuống `Address`.
5. `@NotNull` trên `address` không vi phạm trong ví dụ vì đối tượng `Address` có mặt.

Hai lần in bổ sung xác nhận `validateProperty(invalid, "name")` chỉ xét `name` và `validateValue(Account.class, "age", 16)` xét thuộc tính giả lập mà không có instance root.

Tập các violation được đổi thành chuỗi và `sorted()` **chỉ để hiển thị ổn định**. Không dựa vào thứ tự thực tế provider trả về hoặc giả định “vi phạm đầu tiên” chính là lỗi quan trọng nhất. Nếu sau này thêm constraint khác hoặc đổi dữ liệu, số lượng và thứ tự sau sort có thể thay đổi tương ứng.

## 7. Kiểm thử thật sự kiểm tra tập kết quả

Tệp `src/test/java/demo/ViolationsDemoTest.java`:

~~~java
package demo;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ViolationsDemoTest {

    @Test
    void collectsAllExpectedPaths() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            var bean = new ViolationsDemo.Account(
                " ", "not-an-email", 16,
                new ViolationsDemo.Address(" "));

            Set<ConstraintViolation<ViolationsDemo.Account>> errors =
                validator.validate(bean);

            assertEquals(4, errors.size());
            Set<String> paths = errors.stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());

            assertEquals(
                Set.of("name", "email", "age", "address.city"),
                paths);
        }
    }

    @Test
    void validBeanReturnsEmptySet() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var bean = new ViolationsDemo.Account(
                "An", "an@example.com", 22,
                new ViolationsDemo.Address("Ha Noi"));

            assertTrue(validator.validate(bean).isEmpty());
        }
    }

    @Test
    void validateValueHasNoRootBean() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var errors = validator.validateValue(
                ViolationsDemo.Account.class, "age", 17);

            assertEquals(1, errors.size());
            assertNull(errors.iterator().next().getRootBean());
            assertEquals("age",
                errors.iterator().next().getPropertyPath().toString());
        }
    }

    @Test
    void validatePropertyDoesNotCascade() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            var validator = factory.getValidator();
            var bean = new ViolationsDemo.Account(
                "An", "an@example.com", 22,
                new ViolationsDemo.Address(" "));

            // Bản thân address khác null; validateProperty không
            // đi theo @Valid để kiểm tra address.city.
            assertTrue(
                validator.validateProperty(bean, "address").isEmpty());

            // validate(bean) thì có cascade.
            assertEquals(1, validator.validate(bean).size());
        }
    }
}
~~~

Lệnh:

~~~bash
mvn test
~~~

Với các dependency nêu trên, kỳ vọng **4 test thành công**. Nội dung test đáng tin hơn việc chỉ kiểm tra `!violations.isEmpty()`, vì nó khẳng định cụ thể các property path và ý nghĩa của từng cách validate. Tránh viết test dựa vào `violations.iterator().next()` khi có nhiều phần tử mà không biết phần tử nào sẽ đứng đầu.

Trong dự án thực tế, mỗi tình huống nên kiểm tra thêm nội dung metadata, nhóm validation, null field và nested collection nếu ứng dụng có yêu cầu. Các thông điệp user-facing được bản địa hóa nên kiểm tra bằng locale đã xác định.

## 8. Từ Set<ConstraintViolation<T>> sang danh sách lỗi API

Một giao diện thường cần JSON gồm `field`, `code` và `message`, chứ không cần toàn bộ đối tượng `ConstraintViolation` có cấu trúc phức tạp.

Ví dụ DTO và hàm ánh xạ. Đây là **đoạn minh họa độc lập về phép ánh xạ**, đặt trong một class tiện ích có các import cần thiết:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import jakarta.validation.ConstraintViolation;

record ValidationError(String field, String code, String message) {}

static <T> List<ValidationError> toErrors(
        Set<ConstraintViolation<T>> violations) {
    return violations.stream()
        .map(v -> new ValidationError(
            v.getPropertyPath().toString(),
            v.getConstraintDescriptor().getAnnotation()
                .annotationType().getSimpleName(),
            v.getMessage()))
        .sorted(Comparator
            .comparing(ValidationError::field)
            .thenComparing(ValidationError::code))
        .toList();
}
~~~

Nếu nhận tập violation từ ví dụ ở mục 6, dữ liệu biểu diễn có thể tương đương:

~~~json
[
  {"field":"address.city","code":"NotBlank","message":"city is required"},
  {"field":"age","code":"Min","message":"age must be 18 or older"},
  {"field":"email","code":"Email","message":"email is invalid"},
  {"field":"name","code":"NotBlank","message":"name is required"}
]
~~~

Các chuỗi `code` trong ví dụ lấy tên annotation để minh họa; với một API công khai cần ổn định khi đổi provider/annotation, nên định nghĩa danh mục **mã lỗi nghiệp vụ** riêng và ánh xạ minh bạch. `getMessage()` phục vụ hiển thị; `getMessageTemplate()` và descriptor giúp nhận biết nguồn tạo thông điệp. Đừng biến message đã dịch thành khóa xử lý logic.

Một field có thể vi phạm **nhiều constraint** cùng lúc, chẳng hạn `@NotBlank` và `@Size(min=8)`. Vì vậy JSON nên là **mảng lỗi**, không tùy tiện đổi thẳng thành `Map<String,String>` chỉ giữ một message cuối cùng trên mỗi field. Nếu client muốn nhóm theo field, dùng `Map<String,List<ValidationError>>` hoặc `Map<String,List<String>>`.

Tập kết quả có thể chứa lỗi cấp object/class với `propertyPath` rỗng. Đừng bỏ qua chúng; có thể trình bày dưới khóa `"_global"` hoặc kiểu lỗi object-level được giao ước ở API.

## 9. ConstraintViolationException: khác với tập trả về từ validate()

Hai đoạn sau có ý nghĩa khác nhau:

~~~java
Set<ConstraintViolation<ViolationsDemo.Account>> errors =
    validator.validate(account);

// Chỉ trả Set, không tự ném do bean sai.
~~~

~~~java
if (!errors.isEmpty()) {
    throw new jakarta.validation.ConstraintViolationException(
        "Account validation failed", errors);
}
~~~

Đây là **đoạn minh họa** giả định biến `validator` và `account` thuộc mẫu ở mục 6. Bản thân `validate(...)` trả về tập. Phần `throw` là quyết định của ứng dụng và làm thay đổi luồng điều khiển.

Bắt exception khi nó thật sự được ném:

~~~java
try {
    // Thực thi một operation có thể ném ConstraintViolationException.
} catch (jakarta.validation.ConstraintViolationException ex) {
    for (var violation : ex.getConstraintViolations()) {
        System.out.println(
            violation.getPropertyPath() + ": " + violation.getMessage());
    }
}
~~~

`ConstraintViolationException.getConstraintViolations()` cung cấp tập vi phạm để xử lý tương tự `Validator.validate`. Nó có thể phát sinh từ method validation hoặc từ code application. Không giả định một request Spring MVC có lỗi luôn ném đúng exception này; Spring dùng các exception thích ứng khác ở những đường xử lý tương ứng (xem mục 11).

**Phân loại lỗi:** `ConstraintViolationException` báo các constraint đã thất bại; `ValidationException` nói chung có thể là sự cố cấu hình/provider/metadata và không nên tự động coi tất cả là lỗi dữ liệu người dùng. Ví dụ khai báo sai constraint cho một kiểu Java có thể gây `UnexpectedTypeException`, một subtype của `ValidationException`. Hãy log/giám sát lỗi lập trình riêng và trả status phù hợp cho hệ thống.

## 10. Nhóm ràng buộc, cascade và vì sao tập kết quả thay đổi

### 10.1. Group kiểm soát phạm vi

Mặc định, `validator.validate(bean)` kiểm tra nhóm `Default`. Ví dụ:

~~~java
interface RegistrationChecks {}

class RegistrationForm {
    @NotBlank
    String username;

    @NotBlank(groups = RegistrationChecks.class)
    String referralCode;
}
~~~

Đây là **đoạn khai báo minh họa**, cần import `jakarta.validation.constraints.NotBlank`. Với `RegistrationForm` có hai trường trống:

~~~java
validator.validate(form);                          // Default: username
validator.validate(form, RegistrationChecks.class); // Chỉ referralCode
validator.validate(form, jakarta.validation.groups.Default.class,
                    RegistrationChecks.class);     // Cả hai nhóm
~~~

Không được hiểu `violations.isEmpty()` là “đối tượng luôn hợp lệ theo mọi group”. Nó chỉ hợp lệ theo nhóm và cấu hình được yêu cầu ở **lần gọi đó**.

Nếu cần thứ tự kiểm tra cụ thể, dùng `@GroupSequence`. Khi một group trước có vi phạm, các group tiếp theo trong sequence sẽ không được đánh giá theo quy tắc group sequence. Việc yêu cầu nhiều group không có sequence **không bảo đảm thứ tự đánh giá**.

### 10.2. @Valid làm xuất hiện đường dẫn lồng nhau

Trong ví dụ runnable, `@Valid` trên `Account.address` khiến `@NotBlank` của `Address.city` được kiểm tra. Nếu bỏ `@Valid`, `validate(account)` có thể chỉ kiểm tra `@NotNull` của `address` mà không đi vào `city`. Lúc đó tập vi phạm ít hơn, dù dữ liệu bên trong `Address` không đổi.

Với danh sách, có thể khai báo constraint ngay trên phần tử:

~~~java
import java.util.List;
import jakarta.validation.constraints.NotBlank;

class RequestData {
    List<@NotBlank String> tags;
}
~~~

Đây là **đoạn minh họa** cần một bean chứa field. Nếu `tags` chứa `"ok"` và `""`, provider có thể tạo vi phạm với path dạng `tags[1].<list element>`. Đường dẫn được trả về là đối tượng `Path` có chỉ mục; phần chuỗi cụ thể tùy container, metadata và provider. Nếu cần kiểm tra các thuộc tính **bên trong một đối tượng con** của list, dùng `List<@Valid Child>`; còn `List<@NotBlank String>` kiểm tra chính phần tử String.

### 10.3. Có phải luôn nhận “tất cả lỗi”?

Không nên hứa tuyệt đối rằng mọi constraint của mọi group sẽ xuất hiện trong một lần gọi. Kết quả còn phụ thuộc:

- Chỉ những constraint thuộc nhóm được yêu cầu mới được xét.
- `@Valid` quyết định phạm vi cascade; `validateProperty`/`validateValue` không cascade.
- Group sequence có thể dừng sau group có vi phạm.
- Provider Hibernate Validator có tùy chọn **fail-fast** (không phải mặc định portable của Jakarta API) để dừng sớm khi phát hiện vi phạm; trong trường hợp đó, không kỳ vọng đầy đủ danh sách.
- Một class-level constraint do ứng dụng viết có thể tạo nhiều violation với các đường dẫn được chỉ định thông qua `ConstraintValidatorContext`.
- Validation trên method/constructor có phạm vi khác validation của object.

**Nếu mục tiêu là hiển thị toàn bộ lỗi form**, hãy kiểm tra group, cascade và fail-fast trong cấu hình thực tế, rồi viết test cho trường hợp có nhiều lỗi đồng thời.

## 11. ConstraintViolation trong Spring Framework: nhìn đúng từng đường xử lý

### 11.1. Dùng trực tiếp jakarta.validation.Validator trong service

Spring Framework có thể tạo bean `LocalValidatorFactoryBean`, là cầu nối implement cả `jakarta.validation.Validator` và `org.springframework.validation.Validator`. Đối với service chỉ muốn lấy `Set<ConstraintViolation<T>>`, có thể inject đúng giao diện Jakarta.

Ví dụ **đoạn tích hợp** trong ứng dụng Spring có Bean Validation provider:

~~~java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;
import org.springframework.stereotype.Service;

@Service
public class AccountService {
    private final Validator validator;

    public AccountService(Validator validator) {
        this.validator = validator;
    }

    public void register(AccountRequest request) {
        Set<ConstraintViolation<AccountRequest>> errors =
            validator.validate(request);
        if (!errors.isEmpty()) {
            throw new ConstraintViolationException(
                "Account request invalid", errors);
        }
        // Lưu account sau khi nghiệp vụ xác nhận hợp lệ.
    }
}
~~~

Đây là đoạn tích hợp, chưa độc lập: cần `AccountRequest` là DTO có constraint, import `java.util.Set`, các bean Spring và hạ tầng lưu trữ của ứng dụng. Điểm chính là Spring inject `jakarta.validation.Validator`, còn ứng dụng quyết định xử lý Set. Đừng coi `LocalValidatorFactoryBean` của Spring là một `ConstraintViolation`; nó là bộ thực thi.

Nếu code sử dụng `org.springframework.validation.Validator` thay vì Jakarta Validator, cách lấy kết quả là qua `Errors` / `BindingResult`, không phải chữ ký `Set<ConstraintViolation<T>> validate(T)`. Cần import chính xác vì cả hai package cùng tên `Validator`.

### 11.2. @Valid + @RequestBody/@ModelAttribute ở Spring MVC

~~~java
@PostMapping("/accounts")
public ResponseEntity<Void> create(
        @Valid @RequestBody AccountRequest request) {
    accountService.register(request);
    return ResponseEntity.noContent().build();
}
~~~

Đây là **đoạn controller minh họa** với imports phù hợp từ Spring Web MVC, chưa phải lớp chạy độc lập.

Trong trường hợp Spring MVC validate một command object riêng lẻ với `@Valid` và không có `BindingResult`/`Errors` đứng ngay sau tham số (và không yêu cầu method validation ở mức method), lỗi thường được Spring báo bằng `MethodArgumentNotValidException`. Exception này cung cấp `BindingResult` và `FieldError`/`ObjectError`. Tập kết quả ở tầng Jakarta đã được thích ứng cho hạ tầng Spring; **không ép cast `FieldError` sang `ConstraintViolation<?>`**.

Nếu muốn trả thông báo ngay trong controller theo lỗi binding, có thể thêm tham số `BindingResult` ngay sau đối tượng:

~~~java
@PostMapping("/accounts/check")
public ResponseEntity<?> check(
        @Valid @RequestBody AccountRequest request,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return ResponseEntity.badRequest()
            .body(bindingResult.getFieldErrors().stream()
                .map(e -> e.getField() + ": " + e.getDefaultMessage())
                .toList());
    }
    return ResponseEntity.ok("valid");
}
~~~

Đây cũng là **đoạn minh họa** cần các imports và `AccountRequest` trong ứng dụng; chỉ cho thấy cách sử dụng `BindingResult`. Với API sản phẩm, dùng DTO lỗi ổn định và kiểm soát nội dung trả về, thay vì chỉ truyền chuỗi thô.

### 11.3. Method validation của controller trong Spring MVC 6.1+

Nếu trên tham số controller có constraint trực tiếp như `@Min`/`@NotBlank` hoặc trên return value có constraint, Spring MVC 6.1+ có hỗ trợ method validation và lỗi có thể phát sinh dưới dạng **`HandlerMethodValidationException`**. Đây là cơ chế riêng có dữ liệu theo tham số; không đồng nghĩa với `MethodArgumentNotValidException` cho từng object.

Ví dụ khai báo tham số trực tiếp:

~~~java
@GetMapping("/accounts/{id}")
public String find(@PathVariable @Min(1) long id) {
    return "account=" + id;
}
~~~

Với `id=0`, ràng buộc trực tiếp `@Min(1)` yêu cầu method validation. Ở Spring MVC 6.1+ với cơ chế built-in tương ứng, handler có thể ném `HandlerMethodValidationException`. Trong dự án có class-level `@Validated` hoặc cấu hình proxy phương thức đặc biệt, luồng lỗi có thể khác; nên kiểm tra version và cách đăng ký.

### 11.4. Method validation ở service qua AOP

Đối với Spring bean sử dụng `@Validated` và `MethodValidationPostProcessor` (thường được Spring Boot với validation starter cấu hình), một lời gọi **qua proxy** đến method có constraint có thể phát sinh `jakarta.validation.ConstraintViolationException` mặc định. Khi cấu hình `MethodValidationPostProcessor.setAdaptConstraintViolations(true)`, Spring dùng `MethodValidationException` với mô hình `MethodValidationResult`/`ParameterValidationResult` thay thế.

Đừng giả định lỗi từ proxy AOP luôn giống built-in controller method validation, hoặc rằng tự gọi method nội bộ cùng instance (`this.someMethod()`) chắc chắn đi qua proxy. Nếu cần thực thi tự động, hãy kiểm thử gọi qua bean Spring thật.

### 11.5. Bảng chọn đúng API lỗi

| Nơi xảy ra | Cách tiếp cận kết quả thường gặp |
| --- | --- |
| Code Java gọi `validator.validate(bean)` | `Set<ConstraintViolation<T>>`; ứng dụng tự kiểm tra `isEmpty()`. |
| Code tự ném `ConstraintViolationException` sau `validate` | Bắt exception và gọi `getConstraintViolations()`. |
| Spring MVC `@Valid @RequestBody` kiểm tra object riêng lẻ | `MethodArgumentNotValidException` hoặc `BindingResult` theo chữ ký controller. |
| Spring MVC method constraint trực tiếp, built-in 6.1+ | `HandlerMethodValidationException`. |
| Service `@Validated` qua method-validation AOP | `ConstraintViolationException` mặc định hoặc `MethodValidationException` nếu thích ứng. |
| Spring DataBinder/Spring Validator | `Errors`/`BindingResult`, `FieldError`/`ObjectError`. |

Đọc đúng loại exception và dữ liệu thật tại boundary giúp xây một định dạng lỗi API thống nhất, dù nguồn lỗi đến từ Bean Validation, binding hay method validation.

## 12. Xử lý lỗi an toàn và rõ nghĩa trong REST API

Khi biến vi phạm thành thông báo trả cho client, có thể áp dụng quy trình:

1. **Phân loại nguồn**: Bean Validation, conversion/type mismatch, lỗi business rule và lỗi hạ tầng không nhất thiết có cùng cách xử lý.
2. **Giữ từng vi phạm**: nhiều lỗi cùng field vẫn giữ được đầy đủ; có thể sắp xếp theo path/code.
3. **Chọn field path đúng**: nested path, collection index, Map key, class-level error cần được thể hiện có kiểm soát.
4. **Trả thông điệp thân thiện**: áp dụng locale hoặc message bundle được cấu hình, tránh phụ thuộc ngôn ngữ mặc định của host.
5. **Không để lộ dữ liệu nhạy cảm**: tránh trả `getInvalidValue()`, `rootBean`, stack trace, tên class nội bộ hoặc metadata không cần thiết.
6. **Chọn HTTP status theo biên**: dữ liệu request không hợp lệ thường đi cùng HTTP 400, nhưng lỗi hạ tầng cấu hình validation không nên bị che thành 400. Phần định tuyến status cụ thể do exception handler của ứng dụng quyết định.
7. **Thử nhiều lỗi đồng thời**: xác minh kết quả theo tập, không theo vị trí phần tử bất kỳ.

Ví dụ một `@RestControllerAdvice` có thể nhận `MethodArgumentNotValidException` và xây DTO từ `BindingResult.getFieldErrors()`, đồng thời có handler riêng cho `HandlerMethodValidationException`. Nếu ứng dụng có service ném `ConstraintViolationException`, hãy xử lý thêm exception đó, nhưng chỉ trả một DTO đã loại bỏ dữ liệu nhạy cảm. Không viết một handler nhận mọi `ValidationException` rồi coi chúng đều là input sai.

## 13. Các lỗi thực tế thường gặp

| Lỗi | Tại sao sai | Cách sửa |
| --- | --- | --- |
| `validator.validate(bean);` nhưng không dùng kết quả | Lỗi dữ liệu vẫn tiếp tục xử lý như hợp lệ. | Giữ `Set<ConstraintViolation<T>>`, kiểm tra `isEmpty()`, quyết định trả lỗi/chặn theo nghiệp vụ. |
| Nghĩ `validate(bean)` luôn ném exception | Hợp đồng phương thức trả một `Set`. | Tách rõ kết quả vi phạm và cách xử lý exception. |
| Dựa vào `violations.iterator().next()` là “lỗi đầu tiên” | `Set` không bảo đảm thứ tự. | Sort theo field/code hoặc dùng tiêu chí ưu tiên đã định nghĩa. |
| Tạo `Map<String,String>` và ghi đè message | Một property có thể vi phạm nhiều constraint. | Dùng danh sách lỗi hoặc `Map<String,List<...>>`. |
| So `getMessage()` như mã lỗi cố định | Message phụ thuộc locale/template. | Dùng code tường minh, descriptor hoặc message template có kiểm soát. |
| Dùng `getInvalidValue()` trong response/log | Có thể lộ email, password, token hoặc object nội bộ. | Log có lọc và trả field/code/message an toàn. |
| Bỏ qua `@Valid` khi có object lồng nhau | Vi phạm sâu có thể không được phát hiện. | Đặt cascade tại reference cần validate; test nested property. |
| Dùng `validateProperty` rồi mong cascade | API này không làm `@Valid` cascade. | Dùng `validate(bean)` nếu muốn xét toàn bộ graph. |
| `validateValue` rồi đọc `getRootBean()` | Không có instance bean, root/leaf trả null. | Dùng `getRootBeanClass()` và `getPropertyPath()`. |
| Dùng `String.split("\\.")` để parse toàn bộ path | Collection/Map có index/key và node đặc biệt. | Duyệt `Path.Node` nếu cần cấu trúc chuẩn. |
| Cho rằng `isEmpty()` chứng minh mọi group đều đạt | Chỉ nhóm được yêu cầu mới được kiểm tra. | Xác định group/sequence và viết test. |
| Bật fail-fast rồi hứa hiển thị tất cả lỗi | Provider có thể dừng sớm. | Tắt fail-fast nếu UI cần toàn bộ lỗi. |
| Cast `BindingResult` thành `ConstraintViolation` | Đây là hai mô hình dữ liệu. | Dùng adapter/mapper riêng cho Spring Errors. |
| Bắt mỗi `ConstraintViolationException` trong MVC | Spring MVC còn có các kiểu exception khác. | Phân biệt `MethodArgumentNotValidException` và `HandlerMethodValidationException`. |
| Gộp lỗi cấu hình provider với lỗi form | `ValidationException` có thể chỉ ra bug server. | Phân loại/giám sát lỗi hạ tầng riêng. |
| Dùng chung annotation `javax` và provider `jakarta` | Không tương thích ở dự án đã nâng cấp. | Đồng bộ namespace với Spring/Boot và provider hiện dùng. |

## 14. Checklist tự kiểm tra

- [ ] Dự án có **Bean Validation provider** hoạt động (không chỉ có API/annotation).
- [ ] Constraint được đặt đúng field, property, class hoặc method, với group phù hợp.
- [ ] Các object/list cần validation lồng nhau được khai báo `@Valid` hoặc container element constraint thích hợp.
- [ ] Đã phân biệt `validate`, `validateProperty` và `validateValue`.
- [ ] Logic kiểm tra `violations.isEmpty()`, không bỏ qua kết quả.
- [ ] Không phụ thuộc vào thứ tự `Set`; kết quả API đã được sort khi cần.
- [ ] Không làm mất lỗi khi nhiều constraint cùng vi phạm một property.
- [ ] Không trả `getInvalidValue()` hoặc raw root object ra response.
- [ ] Có test cho dữ liệu hợp lệ, nhiều lỗi cùng lúc, nested path và group nếu dùng.
- [ ] Có handler phù hợp cho `ConstraintViolationException`, `MethodArgumentNotValidException`, `HandlerMethodValidationException` theo đường thực tế.
- [ ] Message hiển thị và mã lỗi được tách bạch; lỗi hệ thống không bị che thành lỗi input.

**Tự kiểm tra kiến thức**

1. Vì sao `validator.validate(bean)` trả một `Set` chứ không chỉ một String?
2. Khi tất cả constraint thuộc nhóm được yêu cầu đều đạt, tập trả về có gì?
3. Vì sao `getRootBean()` của violation từ `validateValue` lại null?
4. Với `address.city`, `getRootBean()` và `getLeafBean()` có thể là hai instance nào?
5. Vì sao hai lần lặp cùng `Set` không nên được coi là thứ tự ưu tiên của lỗi?
6. Đối với `@Valid @RequestBody` trong Spring MVC, tại sao thường nhận `MethodArgumentNotValidException` thay vì trực tiếp nhận Set?
7. Bật provider fail-fast có giúp hiển thị **tất cả lỗi** cùng lúc không?

**Đáp án:** (1) mỗi constraint thất bại có thể tạo metadata riêng, và một đối tượng có thể có nhiều lỗi; (2) tập rỗng; (3) không có bean instance trong phép kiểm tra giả lập; (4) bean gốc chứa `address` và bean `Address` chứa `city`; (5) `Set` không bảo đảm thứ tự; (6) Spring đã thích ứng lỗi sang `BindingResult` trong pipeline MVC; (7) không, fail-fast có thể dừng sau vi phạm đầu tiên.

## 15. Tài liệu tham khảo chính thức

- Jakarta Bean Validation 3.0 API — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html
- Jakarta Bean Validation 3.0 API — `ConstraintViolation`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolation.html
- Jakarta Bean Validation 3.0 API — `ConstraintViolationException`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolationException.html
- Jakarta Bean Validation 3.0 specification: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Hibernate Validator 8.0 Reference Guide, *Validating constraints*, *ConstraintViolation* và *Group*: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework Reference, *Java Bean Validation*: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework Reference, *Spring MVC Validation*: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
