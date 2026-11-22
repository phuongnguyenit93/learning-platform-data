# ValueExtractor cho kiểu container tùy chỉnh trong Spring Framework và Jakarta Validation

## 1. Vấn đề cần giải quyết

Giả sử ứng dụng có kiểu bao dữ liệu tự định nghĩa:

~~~java
public final class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = value;
    }

    public T getValue() {
        return value;
    }
}
~~~

Bạn muốn xác thực **giá trị nằm bên trong** `Box<T>`, chẳng hạn:

~~~java
private Box<@NotBlank String> referenceCode;
private Box<@Valid Customer> customer;
~~~

Các annotation `@NotBlank` và `@Valid` nằm trên **tham số kiểu** `T`. Jakarta Validation cần biết phải lấy `T` từ `Box<T>` như thế nào. Với các container thông dụng như `List`, `Iterable`, `Map` và `Optional`, provider thường có bộ trích xuất mặc định. Với `Box<T>` riêng, bạn phải cung cấp `ValueExtractor` và **đăng ký extractor** vào cùng cấu hình `ValidatorFactory` mà ứng dụng dùng.

**`ValueExtractor` chỉ mô tả cách lấy phần tử để validation tiếp tục.** Nó không phải quy tắc hợp lệ/sai, không thay thế `ConstraintValidator`, không chuyển JSON thành Java object và không thực hiện data binding. Việc một giá trị hợp lệ hay không vẫn do `@NotBlank`, `@Min`, `@Valid` hoặc constraint cụ thể quyết định.

Kết quả mong muốn:

- `Box.of("A-01")` với phần tử mang `@NotBlank`: hợp lệ.
- `Box.of("")` với phần tử mang `@NotBlank`: phát sinh violation.
- `Box.of(new Customer(""))` với `@Valid` trên tham số kiểu: cascade vào `Customer.name` và phát hiện `@NotBlank`.
- Container `Box` bằng `null`: extractor không được gọi; nếu chính container bắt buộc tồn tại thì đặt `@NotNull` lên thuộc tính `Box`.

Phân biệt rõ hai lớp kiểm tra:

~~~java
@NotNull(message = "Hộp dữ liệu không được null")
private Box<@NotBlank(message = "Mã không được trống") String> referenceCode;
~~~

`@NotNull` kiểm tra **đối tượng `Box`**, còn `@NotBlank` kiểm tra **`String` được `Box` chứa**. Nếu chỉ viết `@NotBlank Box<String>`, constraint mặc định được áp dụng lên kiểu `Box` và thường không có validator phù hợp, trừ khi cấu hình explicit/implicit unwrapping ở phần sau.

## 2. Cơ chế `ValueExtractor` hoạt động như thế nào?

Jakarta Validation thực hiện quy trình khái quát:

~~~text
Đối tượng có property chứa container
  └── Box<@NotBlank String>
       ├── Provider xác định extractor cho Box<T>
       ├── extractValues(box, receiver)
       │    └── receiver.value(null, box.getValue())
       └── Chạy @NotBlank trên String được trích xuất
              └── Sinh ConstraintViolation (nếu sai)
~~~

Interface chính:

~~~java
package jakarta.validation.valueextraction;

public interface ValueExtractor<T> {
    void extractValues(T originalValue, ValueReceiver receiver);
}
~~~

*Đoạn trên là chữ ký API rút gọn để giải thích, không phải tệp cần tự định nghĩa trong dự án.*

Bạn implement `ValueExtractor<Container<...>>`; tại **tham số kiểu đang được trích xuất**, đặt `@ExtractedValue`. Trong phương thức `extractValues`, gọi một trong các phương thức của `ValueReceiver` để đưa giá trị cho validation engine. Với container đơn trị như `Box<T>`, dùng `receiver.value(...)`.

### Bốn phương thức quan trọng của `ValueReceiver`

| Phương thức | Khi dùng | Thông tin path mà engine nhận |
| --- | --- | --- |
| `value(nodeName, value)` | Wrapper đơn trị: `Box<T>`, kiểu giống `Optional` | Giá trị; không có chỉ số/key |
| `iterableValue(nodeName, value)` | Tập nhiều phần tử không có index ổn định như `Set` | Đánh dấu phần tử thuộc iterable |
| `indexedValue(nodeName, index, value)` | Container có vị trí như list, mảng hoặc collection tùy chỉnh có index | Đánh dấu iterable kèm index |
| `keyedValue(nodeName, key, value)` | Container có khóa, tương tự map | Đánh dấu iterable kèm key |

`nodeName` là tên **node của phần tử container** trên `ConstraintViolation#getPropertyPath()`. Truyền `null` để không thêm node phần tử; với `Box<T>` một giá trị, cách này giúp violation gắn trực tiếp với tên property chứa `Box`. Nếu dùng `"<box element>"`, path sẽ có thêm node mô tả phần tử container. Với container nhiều phần tử, tên node và index/key rất hữu ích để biết phần tử nào sai.

**Quy tắc:** gọi đúng phương thức `ValueReceiver` cho **mỗi giá trị được chứa**. Không tự chạy `validator.validate(...)` trong extractor, không gọi `ConstraintValidator` thủ công, không sửa phần tử trong lúc duyệt. Việc chạy constraint, cascade, groups, message và tạo path thuộc về validation engine.

## 3. Ví dụ đầy đủ: validate một `Box<T>` và cascade sang object con

Ví dụ độc lập theo **Java 17, Spring Boot 3.5.x, Jakarta Validation**. Spring Boot ở đây dùng để quản lý dependencies và test; bộ test đăng ký `BoxValueExtractor` trực tiếp nên có thể hiểu cơ chế trước khi tích hợp Spring MVC.

Cấu trúc tệp:

~~~text
pom.xml
src/main/java/com/example/validation/
  Box.java
  BoxValueExtractor.java
  Customer.java
  Submission.java
src/test/java/com/example/validation/
  BoxValueExtractorTest.java
~~~

### 3.1. Cấu hình Maven

~~~xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>custom-container-validation</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-validation` đưa một Bean Validation provider (thường là Hibernate Validator) vào classpath. Chỉ thêm `jakarta.validation-api` mà thiếu provider thì không đủ để thực thi các constraint. Dự án không cần khởi động web server để chạy test này.

### 3.2. Kiểu container `Box<T>`

~~~java
// src/main/java/com/example/validation/Box.java
package com.example.validation;

public final class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = value;
    }

    public T getValue() {
        return value;
    }
}
~~~

Container này có đúng **một tham số kiểu**, không phải `Iterable` và không có sẵn bộ trích xuất tương ứng. Mục tiêu là cho phép annotation nằm trên `T` hoạt động.

### 3.3. Tạo `ValueExtractor`

~~~java
// src/main/java/com/example/validation/BoxValueExtractor.java
package com.example.validation;

import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.ValueExtractor;

public final class BoxValueExtractor
        implements ValueExtractor<Box<@ExtractedValue ?>> {

    @Override
    public void extractValues(Box<?> originalValue, ValueReceiver receiver) {
        receiver.value(null, originalValue.getValue());
    }
}
~~~

Giải thích từng phần:

1. `ValueExtractor<Box<@ExtractedValue ?>>` nói với provider rằng extractor nhận kiểu `Box` và giá trị bị trích xuất nằm ở **tham số kiểu thứ nhất** (`T`). Đây là annotation của **khai báo extractor**, khác với `@NotBlank`/`@Valid` trong DTO.
2. `originalValue` là container mà engine chuyển vào; theo hợp đồng Jakarta Validation, nó **không phải `null`** khi phương thức này được gọi.
3. `receiver.value(null, originalValue.getValue())` chuyển giá trị trong `Box` cho engine. `null` đầu tiên là tên node, **không phải giá trị được validate**.
4. Nếu `Box` chứa `null` thì vẫn chuyển `null` làm đối số thứ hai để constraint của phần tử như `@NotBlank`/`@NotNull` xử lý đúng. Không được tự loại bỏ phần tử `null` một cách tùy tiện.
5. Extractor này không cần `@Component`, `@Bean` hay `@Validated` để có hiệu lực khi được **đăng ký qua Bean Validation configuration**. Chỉ khai báo class vẫn chưa đủ.

Cố ý không dùng `@UnwrapByDefault`: chúng ta muốn constraint ở **type argument** (`Box<@NotBlank String>`), không tự chuyển mọi constraint đặt lên `Box` sang `String`.

### 3.4. Một object con để thử cascade

~~~java
// src/main/java/com/example/validation/Customer.java
package com.example.validation;

import jakarta.validation.constraints.NotBlank;

public final class Customer {
    @NotBlank(message = "Tên khách hàng không được trống")
    private final String name;

    public Customer(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

### 3.5. Đặt constraint trên phần tử bên trong `Box`

~~~java
// src/main/java/com/example/validation/Submission.java
package com.example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public final class Submission {
    @NotNull(message = "Box mã không được null")
    private final Box<
            @NotBlank(message = "Mã không được trống") String> code;

    private final Box<@Valid Customer> customer;

    public Submission(Box<String> code, Box<Customer> customer) {
        this.code = code;
        this.customer = customer;
    }

    public Box<String> getCode() {
        return code;
    }

    public Box<Customer> getCustomer() {
        return customer;
    }
}
~~~

Có ba quy tắc khác nhau:

- `@NotNull` đặt **bên ngoài** `Box<...>`: kiểm tra property container `code`.
- `@NotBlank` đặt **trong** `Box<...>`: kiểm tra `String` nằm trong `code` sau extraction.
- `@Valid` đặt trên `Customer` trong `Box<...>`: sau extraction, kiểm tra các ràng buộc bên trong object `Customer`.

`@Valid` không tự biến `Box` thành object hợp lệ hay sai; nó yêu cầu **cascaded validation** lên giá trị bên trong. Constructor và getter ở đây phục vụ ví dụ Java thường; khi nhận JSON/form trong Spring MVC, còn cần thiết kế DTO phù hợp với cơ chế deserialization/binding.

### 3.6. Test chạy được và kết quả kỳ vọng

~~~java
// src/test/java/com/example/validation/BoxValueExtractorTest.java
package com.example.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BoxValueExtractorTest {

    @Test
    void validatesContainerElementAndCascades() {
        try (ValidatorFactory factory = Validation.byDefaultProvider()
                .configure()
                .addValueExtractor(new BoxValueExtractor())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            Submission form = new Submission(
                    new Box<>(""),
                    new Box<>(new Customer(""))
            );

            Set<ConstraintViolation<Submission>> violations =
                    validator.validate(form);

            Map<String, String> errors = violations.stream()
                    .collect(Collectors.toMap(
                            v -> v.getPropertyPath().toString(),
                            ConstraintViolation::getMessage
                    ));

            assertEquals(Map.of(
                    "code", "Mã không được trống",
                    "customer.name", "Tên khách hàng không được trống"
            ), errors);

            assertTrue(validator.validate(new Submission(
                    new Box<>("ORD-01"),
                    new Box<>(new Customer("An"))
            )).isEmpty());
        }
    }

    @Test
    void distinguishesNullContainerFromNullElement() {
        try (ValidatorFactory factory = Validation.byDefaultProvider()
                .configure()
                .addValueExtractor(new BoxValueExtractor())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            Set<ConstraintViolation<Submission>> nullContainer =
                    validator.validate(new Submission(
                            null, new Box<>(new Customer("An"))));

            assertEquals(1, nullContainer.size());
            assertEquals("code", nullContainer.iterator().next()
                    .getPropertyPath().toString());
            assertEquals("Box mã không được null",
                    nullContainer.iterator().next().getMessage());

            Set<ConstraintViolation<Submission>> nullElement =
                    validator.validate(new Submission(
                            new Box<>(null),
                            new Box<>(new Customer("An"))));

            assertEquals(1, nullElement.size());
            assertEquals("code", nullElement.iterator().next()
                    .getPropertyPath().toString());
            assertEquals("Mã không được trống",
                    nullElement.iterator().next().getMessage());
        }
    }
}
~~~

Chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn test
~~~

**Kết quả kỳ vọng:** Maven chạy thành công **2 tests**, không có assertion failure. Test thứ nhất tìm đúng hai property path `code` và `customer.name`; test thứ hai chứng minh sự khác nhau giữa `Box` bằng `null` và `Box` có phần tử bằng `null`. Tên phương thức test, số lượng và format log có thể khác theo phiên bản Maven/Surefire, nên chỉ khẳng định các điều kiện được assert.

Điểm quan trọng là chuỗi `"code"`, thay vì thêm `"<box element>"`, xuất hiện vì extractor dùng `receiver.value(null, ...)`. Đây là chủ đích cho wrapper đơn trị.

## 4. Đăng ký extractor để Spring dùng đúng `ValidatorFactory`

**Viết class extractor chưa khiến nó được sử dụng.** Bạn phải đăng ký nó vào provider. Những cách chính:

| Cách | Phạm vi | Khi nên dùng |
| --- | --- | --- |
| `Configuration#addValueExtractor(...)` | `ValidatorFactory` được tạo từ cấu hình đó | Test, bootstrap thủ công, cấu hình rõ ràng |
| Spring Boot `ValidationConfigurationCustomizer` | Validator factory do Boot tự cấu hình | Ứng dụng Spring Boot 3.x |
| Java `ServiceLoader` | Các factory đọc đăng ký từ classpath | Đóng gói thư viện dùng nhiều dự án |
| `META-INF/validation.xml` | Cấu hình Bean Validation cho factory liên quan | Dự án quản lý provider qua XML |
| `ValidatorContext#addValueExtractor(...)` | `Validator` tạo từ context ấy | Cần điều chỉnh trong phạm vi một validator |

### 4.1. Bootstrap thủ công

Trong test ở trên:

~~~java
ValidatorFactory factory = Validation.byDefaultProvider()
        .configure()
        .addValueExtractor(new BoxValueExtractor())
        .buildValidatorFactory();

try {
    Validator validator = factory.getValidator();
    // validator.validate(form);
} finally {
    factory.close();
}
~~~

Đây là cách trực tiếp nhất để chứng minh extractor hoạt động. `ValidatorFactory` nên được tái sử dụng trong ứng dụng thay vì tạo cho từng request; test có thể đóng factory sau khi dùng. Cùng một kiểu container và tham số kiểu không nên được đăng ký trùng nhiều extractor trong cùng configuration.

### 4.2. Spring Boot 3.x: dùng `ValidationConfigurationCustomizer`

Trong ứng dụng đã có `spring-boot-starter-validation`, định nghĩa bean:

~~~java
// src/main/java/com/example/validation/ValidationConfig.java
package com.example.validation;

import org.springframework.boot.autoconfigure.validation.ValidationConfigurationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ValidationConfig {

    @Bean
    ValidationConfigurationCustomizer boxExtractorCustomizer() {
        return configuration ->
                configuration.addValueExtractor(new BoxValueExtractor());
    }
}
~~~

Spring Boot sử dụng customizer để xây `LocalValidatorFactoryBean` mặc định, do đó `@Valid` trên Spring MVC model, request DTO và việc injection `jakarta.validation.Validator` có thể dùng extractor này khi chúng trỏ tới validator do Boot quản lý.

**Phạm vi phiên bản:** đường dẫn import `org.springframework.boot.autoconfigure.validation.ValidationConfigurationCustomizer` dành cho **Spring Boot 3.x**. Spring Boot 4 đã tổ chức lại các package auto-configuration; nếu nâng cấp framework, kiểm tra Javadoc của đúng phiên bản thay vì sao chép import cũ.

Để Spring MVC kích hoạt validation, ví dụ controller có thể khai báo `@Valid @RequestBody Submission request` hoặc `@Valid @ModelAttribute("submission") Submission form` tùy loại dữ liệu. Việc tạo instance `Submission` từ request **là vấn đề binding/deserialization riêng**; class immutable trong ví dụ test cần được thiết kế thêm constructor mapping hoặc DTO phù hợp nếu dùng làm HTTP request thật.

### 4.3. Đăng ký qua Java `ServiceLoader`

Trong một thư viện phân phối extractor, tạo tệp:

~~~text
src/main/resources/META-INF/services/jakarta.validation.valueextraction.ValueExtractor
~~~

Nội dung **một dòng là tên class đầy đủ**:

~~~text
com.example.validation.BoxValueExtractor
~~~

Class phải có constructor mà `ServiceLoader` có thể khởi tạo (ví dụ public no-arg constructor) và nằm trên classpath/module path phù hợp. Sau khi đóng gói JAR, provider có thể phát hiện đăng ký thông qua dịch vụ. Không đặt tên tệp là `javax.validation.valueextraction.ValueExtractor` khi dùng Jakarta Validation 3.x.

Dùng **một** cách đăng ký chủ đạo cho cùng extractor trong một cấu hình để dễ kiểm soát ưu tiên, tránh định nghĩa trùng. Hibernate Validator có thứ tự ưu tiên giữa extractor có sẵn, service loader, XML, factory configuration và validator context; custom extractor ở mức cấu hình cao hơn có thể override extractor cùng container/type parameter ở mức thấp hơn.

## 5. Container có nhiều phần tử: path, index và key

`receiver.value(...)` là lựa chọn tự nhiên cho wrapper đơn trị. Nếu bạn xây kiểu nhiều phần tử, gọi `indexedValue`/`iterableValue`/`keyedValue` chính xác theo cấu trúc. Điều này quyết định khả năng định vị phần tử sai trên `ConstraintViolation#getPropertyPath()`.

### 5.1. Container có vị trí: `Slots<T>`

Giả sử `Slots<T>` chứa một danh sách và muốn validate từng slot:

~~~java
// Ví dụ bổ sung, triển khai thành các class riêng khi dùng trong dự án
package com.example.validation;

import java.util.List;

public final class Slots<T> {
    private final List<T> elements;

    public Slots(List<T> elements) {
        this.elements = List.copyOf(elements);
    }

    public List<T> getElements() {
        return elements;
    }
}
~~~

~~~java
package com.example.validation;

import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.ValueExtractor;

public final class SlotsValueExtractor
        implements ValueExtractor<Slots<@ExtractedValue ?>> {

    @Override
    public void extractValues(Slots<?> originalValue, ValueReceiver receiver) {
        for (int i = 0; i < originalValue.getElements().size(); i++) {
            receiver.indexedValue(
                    "<slot>", i, originalValue.getElements().get(i));
        }
    }
}
~~~

Sau khi **đăng ký `SlotsValueExtractor`**, DTO có thể khai báo:

~~~java
private Slots<@NotBlank String> labels;
~~~

Nếu một phần tử sai, engine có thể đưa index cùng node `"<slot>"` vào property path, giúp truy vết đến `labels` và slot tương ứng. Với path API, đọc `Path.Node#isInIterable()`, `getIndex()` hoặc `getKey()` nếu cần xử lý cấu trúc; việc chuyển path sang chuỗi do provider đảm nhiệm.

**Chú ý:** `List.copyOf(elements)` ở class `Slots` **không chấp nhận phần tử null**. Nếu yêu cầu minh họa validation `@NotNull` trên từng phần tử, cần chọn một cách lưu trữ cho phép null; đừng dựa vào `List.copyOf` để tạo danh sách có null.

### 5.2. Container không có index và container có key

Với tập hợp không định vị bằng index, dùng:

~~~java
for (Object element : customSet.elements()) {
    receiver.iterableValue("<element>", element);
}
~~~

Với container có khóa, ví dụ entry map:

~~~java
for (var entry : customMap.entries()) {
    receiver.keyedValue(
            "<value>", entry.getKey(), entry.getValue());
}
~~~

Hai đoạn này là **phần thân minh họa** của một `extractValues(...)`; `customSet` và `customMap` biểu thị API của container do bạn tự định nghĩa, không phải class từ thư viện Java chuẩn. Để có class chạy được cần thay bằng API thật của loại container đang dùng.

Nếu kiểu chứa cả key và value với **hai tham số kiểu**, ví dụ `PairMap<K,V>`, có thể cần **hai extractor riêng**, mỗi extractor đánh dấu đúng một tham số kiểu bằng `@ExtractedValue`: một extractor cho `K`, một cho `V`. Đừng đánh dấu hai tham số kiểu được trích xuất trong cùng một khai báo extractor.

## 6. Khi nào dùng `@UnwrapByDefault`?

Có hai cú pháp khác nhau với mục đích khác nhau:

~~~java
// Đặt constraint trực tiếp trên phần tử container:
Box<@NotBlank String> code;

// Đặt constraint lên chính đối tượng Box, nếu không yêu cầu unwrapping:
@NotNull
Box<String> box;
~~~

Trong trường hợp thứ nhất, extractor `ValueExtractor<Box<@ExtractedValue ?>>` giúp validation engine lấy `String`. Trong trường hợp thứ hai, `@NotNull` kiểm tra việc `box` có null hay không, **không cần** unwrap.

Nếu muốn một loại wrapper mặc định “trong suốt” với các constraint đặt lên wrapper, có thể khai báo extractor bằng `@UnwrapByDefault`:

~~~java
// Chỉ minh họa một extractor thay thế; không đăng ký đồng thời
// với BoxValueExtractor ở mục 3 cho cùng Box<T>.
package com.example.validation;

import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.UnwrapByDefault;
import jakarta.validation.valueextraction.ValueExtractor;

@UnwrapByDefault
public final class UnwrappingBoxValueExtractor
        implements ValueExtractor<Box<@ExtractedValue ?>> {

    @Override
    public void extractValues(Box<?> originalValue, ValueReceiver receiver) {
        receiver.value(null, originalValue.getValue());
    }
}
~~~

Khi extractor kiểu này được chọn, annotation ràng buộc đặt **trên wrapper** có thể được áp dụng tự động lên giá trị bên trong:

~~~java
// Với UnwrappingBoxValueExtractor được đăng ký:
@NotBlank
Box<String> code;
~~~

Không nên chọn implicit unwrapping chỉ vì muốn `Box<@NotBlank String>` hoạt động; container-element validation đã giải quyết nhu cầu ấy. `@UnwrapByDefault` đổi **ý nghĩa** một số ràng buộc khai báo lên wrapper, nhất là `@NotNull`. Khi cần kiểm tra wrapper thay vì giá trị bên trong, có thể điều khiển bằng payload `jakarta.validation.valueextraction.Unwrapping.Skip`; ngược lại `Unwrapping.Unwrap` yêu cầu unwrap ở một constraint cụ thể khi có extractor thích hợp.

Ví dụ cú pháp (dùng trong class có `import jakarta.validation.valueextraction.Unwrapping;`):

~~~java
@NotNull(payload = Unwrapping.Skip.class)
private Box<String> code;
~~~

Không gắn `@UnwrapByDefault` trong ví dụ chính để giữ đúng sự khác nhau giữa `@NotNull Box<T>` và `Box<@NotBlank T>`. Khi thiết kế thư viện wrapper dùng ở nhiều module, lựa chọn unwrapping cần được ghi rõ trong tài liệu API.

## 7. `ValueExtractor` có quan hệ gì với Spring Validation và Data Binding?

Trong hệ sinh thái Spring, dễ nhầm các thành phần sau:

| Thành phần | Chức năng | Có giải quyết `Box<@NotBlank String>`? |
| --- | --- | --- |
| `Converter<S,T>` / `Formatter` | Chuyển chuỗi/kiểu khi bind dữ liệu | Không, chỉ giải quyết chuyển kiểu |
| `DataBinder` / `WebDataBinder` | Gán dữ liệu request vào target object, lưu binding errors | Không tự định nghĩa extraction của Bean Validation |
| `jakarta.validation.ConstraintValidator` | Thực thi quy tắc constraint cụ thể | Không tự tìm phần tử trong mọi custom container |
| `jakarta.validation.valueextraction.ValueExtractor` | Đưa phần tử container cho Bean Validation | Có, nếu được đăng ký đúng |
| `LocalValidatorFactoryBean` | Spring adapter/factory cho Jakarta Bean Validation | Sử dụng extractor đã đăng ký trong configuration |
| `BindingResult` | Chứa field errors và global errors sau binding/validation | Có thể nhận lỗi phát sinh từ constraint của phần tử |

Chuỗi xử lý thông thường khi Spring MVC validate một request:

~~~text
HTTP request
  -> Jackson / Spring DataBinder tạo và gán dữ liệu cho DTO
  -> @Valid / Validator được Spring gọi
  -> Bean Validation tìm container element constraints
  -> ValueExtractor lấy từng giá trị trong container
  -> ConstraintValidator kiểm tra giá trị
  -> ConstraintViolation có property path
  -> Spring chuyển thành field/global errors tương ứng
~~~

Khi ứng dụng có DTO như `Submission` được bind thành công, một violation tại phần tử trong `code` với `nodeName=null` có path `code`; Spring thường ánh xạ đường dẫn này thành `FieldError` cho field `code`. Với container indexed hoặc keyed, path có thêm metadata để UI/API chỉ đúng vị trí. Đường dẫn thể hiện nơi lỗi xuất hiện, không tự chỉ thị Spring cách bind request vào `Box`.

Đừng nghĩ rằng chỉ thêm `@Bean BoxValueExtractor` là Spring sẽ tự lấy mọi Bean `ValueExtractor` để đưa vào provider. Với Spring Boot 3.x, cách rõ ràng được framework hỗ trợ là bean `ValidationConfigurationCustomizer` hoặc service loader/configuration thích hợp.

## 8. Thiết kế và xử lý các tình huống khó

### 8.1. Ngữ nghĩa null và container rỗng

| Trạng thái | `ValueExtractor` có chạy? | Nơi cần constraint |
| --- | --- | --- |
| `Box` là `null` | Không | `@NotNull` trên property container nếu bắt buộc |
| `Box` có một giá trị `null` | Có, chuyển phần tử null qua receiver | `Box<@NotNull T>` hoặc constraint phù hợp |
| `Box` có `String=""` | Có | `Box<@NotBlank String>` |
| `Slots` không có phần tử | Không có phần tử để nhận; extractor có thể được gọi nhưng không gọi receiver cho element nào | `@Size` trên container nếu có validator phù hợp, hoặc custom constraint cho kích thước |
| `Slots` có nhiều phần tử | Có, receiver nhận từng phần tử | Constraint trên type argument và `@Valid` nếu cần cascade |

`ValueExtractor` **không chịu trách nhiệm** đánh giá kích thước, trạng thái empty hay tính hợp lệ của cả container. Các quy tắc đó thường là constraint dành cho container hoặc constraint tùy chỉnh. Không dùng `@NotBlank` cho kiểu tùy chỉnh rồi mặc định nghĩ nó có khả năng hiểu cấu trúc `Box`.

### 8.2. Nhiều extractors và độ ưu tiên

Provider chọn extractor dựa trên **container type**, **type parameter** và độ đặc hiệu. Nếu hai extractors cùng cấp cấu hình áp dụng cho đúng một tham số kiểu của cùng container, có thể gặp lỗi định nghĩa/khai báo hoặc ambiguity khi khởi tạo/validate. Để tránh:

- Mỗi tham số kiểu cần trích xuất có chiến lược rõ ràng.
- Không đăng ký lặp extractors tương đương ở Spring customizer, service loader và cấu hình riêng mà không kiểm soát thứ tự.
- Đảm bảo đúng factory là nơi thực sự chạy validation. Test tự tạo `ValidatorFactory` sẽ không kế thừa cấu hình Spring Boot của ứng dụng.
- Nếu container kế thừa/implement nhiều kiểu generic, cân nhắc ưu tiên extractor sẵn có của provider và thử validation với từng kiểu khai báo của property.

### 8.3. Hai tham số kiểu, non-generic wrapper và giới hạn khai báo

- Với `Pair<L,R>`, đánh dấu tối đa **một** type parameter bằng `@ExtractedValue` trong mỗi định nghĩa extractor. Khi cần validate cả hai, thường tạo hai extractors riêng.
- Với wrapper **không generic**, có thể khai báo `@ExtractedValue(type = SomeType.class)` tại container type use trong `ValueExtractor` để mô tả kiểu phần tử được trích xuất. Không thể dùng `?` như generic type argument nếu loại container không có tham số kiểu.
- Chọn `@ExtractedValue` trên **đúng type argument** có constraint; chọn sai vị trí có thể khiến provider không tìm được extractor tương ứng.
- Đừng dùng kiểu thô (`raw type`) hoặc loại bỏ thông tin generic ở property nếu đang dựa vào constraint trong tham số kiểu.

### 8.4. Hiệu năng và thread safety

Extractor có thể chạy nhiều lần trong các lượt validate; giữ implementation **nhẹ, không trạng thái**, chỉ đọc container và gọi receiver. Không gọi dịch vụ từ xa, query DB hoặc mutate dữ liệu trong `extractValues`. Với collection lớn, thời gian validation có thể tỷ lệ với số phần tử được duyệt; kiểm tra giới hạn kích thước input từ trước khi yêu cầu xác thực toàn bộ.

Nếu container cho phép thay đổi đồng thời, việc vừa duyệt vừa mutate có thể làm path/index sai hoặc phát sinh exception. Thiết kế input ổn định trong thời gian validate và tận dụng immutable snapshot nếu phù hợp ngữ cảnh. Các singleton extractor stateless như `BoxValueExtractor` trong ví dụ thích hợp để dùng lặp lại từ nhiều request.

## 9. Lỗi phổ biến và cách chẩn đoán

1. **Viết `ValueExtractor` nhưng không đăng ký:** provider không có thông tin extraction cho kiểu custom. Kiểm tra config factory, customizer Spring, service loader và dependencies.
2. **Đặt `@ExtractedValue` sai hoặc đánh dấu nhiều type arguments:** provider không thể xác định rõ loại phần tử được trích xuất. Kiểm tra chữ ký `ValueExtractor<Box<@ExtractedValue ?>>`.
3. **Truyền chính container vào receiver:** `receiver.value(null, originalValue)` khiến constraint trên `String` nhận sai kiểu; phải truyền `originalValue.getValue()`.
4. **Dùng `indexedValue` cho wrapper đơn trị:** dễ tạo path mang index không có ý nghĩa. Dùng `value(null, ...)` cho single-value wrapper.
5. **Bỏ qua null element bằng `if (value != null)`:** có thể khiến `Box<@NotNull String>` không báo lỗi; chỉ bỏ qua theo đúng semantics của chính loại container.
6. **Đặt constraint sai chỗ:** `@NotNull Box<String>` kiểm tra container, còn `Box<@NotNull String>` kiểm tra phần tử; hai trường hợp khác nhau.
7. **Chỉ định `@Valid` trên object con nhưng bỏ extractor:** cascade có thể không đi vào kiểu custom. Kiểm tra đăng ký và đặt `@Valid` trên type argument phù hợp.
8. **Kỳ vọng extractor sửa data binding:** việc Jackson không tạo được `Box<T>` là vấn đề mapping constructor/deserializer, tách khỏi Bean Validation.
9. **Dùng extractor sai package:** Spring Boot 3.x sử dụng `jakarta.validation.*`, không trộn `javax.validation.*` từ hệ cũ.
10. **Không xem property path trong test:** chỉ kiểm tra `hasErrors()` không chứng minh lỗi gắn đúng field/slot. Test cả `ConstraintViolation#getPropertyPath()` và message/type của violation.
11. **Khai báo hai chiến lược unwrap mâu thuẫn:** hiểu ý nghĩa của `@UnwrapByDefault` và cấu hình override trước khi thêm vào wrapper dùng rộng rãi.
12. **Nhầm `@Component` với đăng ký extractor:** component scanning và Jakarta Bean Validation bootstrap là hai cơ chế khác nhau; dùng đúng factory do ứng dụng quản lý.

Khi debug, nên bắt đầu từ trường hợp tối giản `Box<@NotBlank String>`, register `BoxValueExtractor` trên một factory độc lập, kiểm tra property path, rồi mới đưa vào Spring. Cách này xác định được vấn đề nằm ở extractor hay cấu hình tích hợp.

## 10. Checklist triển khai

1. Xác định loại custom container: một giá trị, nhiều phần tử có index, iterable không index, hay map có key.
2. Đặt constraint vào đúng type argument (`Box<@NotBlank String>`, `Box<@Valid Customer>`).
3. Implement `ValueExtractor<Container<@ExtractedValue ?>>`, hoặc extractor phù hợp với số tham số kiểu của container.
4. Gọi đúng `ValueReceiver` method cho từng phần tử; chọn `nodeName=null` hoặc tên cụ thể theo nhu cầu property path.
5. Đăng ký extractor vào **đúng `ValidatorFactory`**; với Boot 3.x dùng `ValidationConfigurationCustomizer` khi phù hợp.
6. Test giá trị hợp lệ, giá trị sai, container null, phần tử null, cascade, property path và khả năng định vị index/key.
7. Nếu dùng Spring MVC, xác nhận DTO bind được trước khi đánh giá lỗi validation; kiểm tra `BindingResult` ở field mong muốn.
8. Chỉ thêm `@UnwrapByDefault` khi muốn thay đổi semantics constraint đặt trên chính wrapper.

## Tài liệu tham khảo

- Jakarta Validation 3.1, `ValueExtractor.ValueReceiver`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/valueextraction/valueextractor.valuereceiver
- Jakarta Validation specification, value extractors và property path: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1
- Hibernate Validator Reference Guide, chương 7 (Value extraction): https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#chapter-valueextraction
- Spring Boot 3.5 Reference, Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5 API, `ValidationConfigurationCustomizer`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/validation/ValidationConfigurationCustomizer.html
