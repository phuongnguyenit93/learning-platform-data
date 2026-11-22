# `propertyPath`, `invalidValue`, `message` và `messageTemplate` trong Bean Validation

## 1. Mục tiêu: đọc đúng một lỗi xác thực

Khi đối tượng không thỏa ràng buộc Bean Validation, API Jakarta Validation trả về tập `ConstraintViolation<T>`. Mỗi phần tử mô tả **một ràng buộc bị vi phạm**, gồm vị trí lỗi, giá trị được kiểm tra và thông tin thông báo. Bốn thành phần cần phân biệt là:

| Thuộc tính qua API | Kiểu trả về | Trả lời câu hỏi |
| --- | --- | --- |
| `getPropertyPath()` | `jakarta.validation.Path` | Vi phạm phát sinh tại **đường dẫn nào**, tính từ đối tượng gốc được validate? |
| `getInvalidValue()` | `Object` | **Giá trị nào** được đưa vào constraint validator và không đạt? |
| `getMessage()` | `String` | **Thông báo đã được nội suy** cho vi phạm này là gì? |
| `getMessageTemplate()` | `String` | **Mẫu thông báo gốc, trước nội suy**, của vi phạm là gì? |

Ví dụ, một trường `reference` có `@Size(min = 4, message = "Mã cần ít nhất {min} ký tự")` nhưng nhận chuỗi `"AB"`:

```text
propertyPath    = reference
invalidValue    = "AB"
message         = Mã cần ít nhất 4 ký tự
messageTemplate = Mã cần ít nhất {min} ký tự
```

`{min}` được lấy từ thuộc tính `min = 4` của annotation. Trong ví dụ đơn giản này, `invalidValue` là giá trị trường; nhưng với **ràng buộc ở cấp class**, ở tham số phương thức, hay ở phần tử của collection, không được suy diễn rằng nó luôn là giá trị của một field cùng tên với đường dẫn.

Sau bài học, bạn có thể đọc và diễn giải bốn thành phần từ `ConstraintViolation`, hiển thị lỗi an toàn, hiểu mối liên hệ với `BindingResult` trong Spring MVC và kiểm thử cả trường hợp lồng nhau, collection, nội suy và lỗi chuyển kiểu.

## 2. `ConstraintViolation<T>` được sinh ra khi nào?

Ví dụ với Jakarta Validation:

```java
Validator validator = validatorFactory.getValidator();
Set<ConstraintViolation<OrderForm>> violations =
        validator.validate(orderForm);
```

Đây là **đoạn minh họa**, cần `Validator`, `ValidatorFactory`, `ConstraintViolation` thuộc `jakarta.validation.*` và các đối tượng được khởi tạo. `Validator.validate(object)` trả về một **Set** các vi phạm đối với object và những đối tượng được cascade bằng `@Valid`; thứ tự phần tử **không được bảo đảm**. Tập rỗng nghĩa là không tìm thấy vi phạm trong các nhóm ràng buộc được kiểm tra, không có nghĩa dữ liệu luôn đúng theo mọi nghiệp vụ.

Mỗi violation còn có `getRootBean()`, `getRootBeanClass()`, `getLeafBean()` và `getConstraintDescriptor()`. Bốn thông tin chính nên được đọc cùng ngữ cảnh đó khi có nhiều cấp đối tượng.

Phân biệt **đường đi lỗi** với **đường chạy validation**:

```text
HTTP/form String --Spring data binding--> Java object
                                       |
                                       v
                            Jakarta Bean Validation
                                       |
                                       v
                           ConstraintViolation<T>
                                       |
                                       v
                        Spring BindingResult / FieldError
```

Spring phải chuyển chuỗi thành đúng kiểu Java **trước khi** validator kiểm tra ràng buộc như `@Size`, `@Min` hoặc custom constraint. Nếu chuỗi `"abc"` không chuyển được sang `Integer`, đó có thể là **lỗi binding `typeMismatch`**, không phải một `ConstraintViolation<Integer>`; vì vậy không phải mọi `FieldError` đều có đủ bốn trường theo Jakarta Validation.

## 3. `getPropertyPath()`: cấu trúc vị trí lỗi

Chữ ký API:

```java
Path path = violation.getPropertyPath();
String displayPath = path.toString();
```

`Path` là **đối tượng có cấu trúc**, không đơn thuần là một `String`. Khi validate một object `OrderForm` chứa `@Valid Address shipping` và `Address.zip` sai pattern, đường dẫn thông dụng là:

```text
shipping.zip
```

`Path` gồm các `Path.Node`. Mỗi node có thể cho biết `getName()`, `getKind()`, `isInIterable()`, `getIndex()` hoặc `getKey()`. Những loại node thường gặp qua `jakarta.validation.ElementKind` gồm `PROPERTY`, `BEAN`, `METHOD`, `PARAMETER`, `RETURN_VALUE`, `CROSS_PARAMETER` và `CONTAINER_ELEMENT`.

### 3.1. Đường dẫn của các dạng constraint

| Vị trí ràng buộc | Ví dụ đường dẫn khi dùng `toString()` | Ý nghĩa |
| --- | --- | --- |
| Property trực tiếp | `customerName` | Trường trên bean gốc |
| Property trong object lồng nhau có `@Valid` | `shipping.zip` | Đi từ bean gốc qua property `shipping` |
| Phần tử `List<@NotBlank String>` | Có thể là `tags[0].<list element>` | Có node phần tử container và index; cú pháp trình bày phụ thuộc provider |
| Phần tử Map | Có thể gắn key như `options[K]` | Cần xét `getKey()`, `ElementKind` và đường đi đầy đủ |
| Constraint cấp class của bean gốc | Thường là đường dẫn rỗng (`""`) | Lỗi liên quan tới cả bean, không gắn sẵn vào field |
| Constraint tham số/return value của method | Chứa node method, parameter/return value | Không phải đường dẫn field của form thông thường |

Các chuỗi `<list element>` hoặc tên tham số có thể khác theo **provider/cấu hình**. Đặc biệt, tên tham số phương thức phụ thuộc `ParameterNameProvider` và khả năng thu thập metadata tên tham số. Không cắt chuỗi path bằng `split("\\.")` rồi mặc định mọi segment đều là property, vì collection index, Map key và container node có cấu trúc riêng.

### 3.2. Khi cần xử lý path chính xác

Đoạn mã sau là **trích đoạn** bên trong vòng lặp violation; cần import `jakarta.validation.Path`, `jakarta.validation.ElementKind`:

```java
for (Path.Node node : violation.getPropertyPath()) {
    String name = node.getName();
    ElementKind kind = node.getKind();

    if (node.isInIterable()) {
        Integer index = node.getIndex(); // List/array: có thể khác null
        Object key = node.getKey();      // Map: có thể khác null
        // Xử lý index/key theo cấu trúc thật của node.
    }

    if (kind == ElementKind.PROPERTY) {
        // name là tên property của node này.
    }
}
```

Nếu trả `field` về UI, hãy chuyển từ các node sang **quy tắc field naming được ứng dụng xác định**, nhất là với list hoặc map. Chuỗi `path.toString()` rất tiện cho log/test, nhưng không tự động là JSON Pointer, không bảo đảm trùng tên trường trong JSON và không nhất thiết tương ứng một ô input HTML.

## 4. `getInvalidValue()`: giá trị thực sự bị kiểm tra

`violation.getInvalidValue()` trả về `Object`, có thể là `String`, `Integer`, phần tử collection, object, `null` hoặc một kiểu tùy chỉnh. Theo Jakarta Validation, đây là **giá trị được chuyển tới phép kiểm tra constraint** (`isValid`), không phải bản sao bảo đảm luôn là chuỗi người dùng đã nhập.

Những trường hợp quan trọng:

1. **Constraint trên field:** `@Size` áp dụng cho `reference = "AB"` → `getInvalidValue()` trả `"AB"`.
2. **Constraint trên property lồng nhau:** `shipping.zip = "12x"` → trả `"12x"` khi constraint áp dụng trực tiếp cho `zip`; `getPropertyPath()` chứa `shipping.zip`.
3. **Constraint cấp class:** giá trị bị kiểm tra thường là **toàn bộ object** đã gắn constraint, không phải một field cụ thể.
4. **Constraint trên phần tử container:** giá trị trả về là **phần tử** không hợp lệ, ví dụ `""` trong `List<@NotBlank String>`.
5. **Constraint cross-parameter của method/constructor:** giá trị có thể là `Object[]` gồm các đối số được kiểm tra.
6. **Constraint với giá trị `null`:** `getInvalidValue()` có thể trả `null`, ví dụ `@NotNull`. Không gọi `.toString()` khi chưa kiểm tra null.

Ngoài ra, `getRootBean()` là object gốc đưa vào `Validator.validate(...)`; `getLeafBean()` chỉ object gần nhất chứa constraint theo ngữ cảnh spec. Ba giá trị `rootBean`, `leafBean` và `invalidValue` **không phải luôn cùng đối tượng**. Với `Validator.validateValue(SomeClass.class, "field", value)`, `getRootBean()` có thể là `null` vì không có bean instance thực sự.

**Lưu ý bảo mật:** không tự động trả `invalidValue` về HTTP response hoặc ghi nguyên vào log. Nó có thể là mật khẩu, token, dữ liệu cá nhân, một object có `toString()` tiết lộ trạng thái nội bộ, hoặc dữ liệu lớn. Khi cần debug, dùng loại lỗi, path đã lọc và correlation ID; nếu thật sự cần giá trị, chỉ ghi bản đã che/giảm dữ liệu theo chính sách. Trong Spring, `FieldError.getRejectedValue()` cũng cần được xử lý theo nguyên tắc tương tự.

## 5. `getMessage()` và `getMessageTemplate()`: nội suy khác với lưu mẫu

Giả sử annotation:

```java
@Size(
    min = 4,
    max = 10,
    message = "Mã cần ít nhất {min} ký tự"
)
private String reference;
```

Với `reference = "AB"`, một violation có:

```text
getMessage()         -> "Mã cần ít nhất 4 ký tự"
getMessageTemplate() -> "Mã cần ít nhất {min} ký tự"
```

`getMessage()` trả về kết quả đã nội suy; `getMessageTemplate()` trả nguyên mẫu trước nội suy. **Mẫu không nhất thiết có placeholder**. Ví dụ `@NotBlank(message = "Tên không được để trống")` trả cùng một chuỗi ở cả hai phương thức.

### 5.1. Message template có thể là khóa resource bundle

Khai báo khác:

```java
@NotBlank(message = "{order.customer.required}")
private String customerName;
```

Và file `ValidationMessages.properties` trên classpath:

```properties
order.customer.required=Customer name is required
```

Khi provider và resource bundle được cấu hình đúng, `getMessageTemplate()` vẫn là `"{order.customer.required}"`; `getMessage()` là thông báo đã được resolve và nội suy, chẳng hạn `"Customer name is required"`.

Với locale tiếng Việt, có thể có `ValidationMessages_vi.properties` chứa thông điệp dịch. Locale **được chọn theo chiến lược message interpolator và tích hợp framework**, không thể suy ra chỉ từ việc request có header `Accept-Language`. Khi muốn kiểm thử đa ngôn ngữ, xác nhận locale resolver, `MessageInterpolator`, `MessageSource` (nếu tích hợp Spring) và các file bundle trên đúng môi trường.

### 5.2. Mẫu chứa thuộc tính annotation hoặc biểu thức

Trong message, `{min}` và `{max}` thường trỏ tới các thuộc tính constraint. Jakarta Validation cũng quy định cơ chế nội suy message có thể hỗ trợ biểu thức EL `${...}` theo cấu hình/provider; đó là cơ chế khác với việc **đọc nguyên mẫu**.

- `getMessageTemplate()` có giá trị khi chẩn đoán, thống kê lỗi hoặc làm đầu vào cho lớp dịch riêng.
- `getMessage()` phù hợp hơn để hiển thị thông báo mà provider đã xử lý.
- **Không mặc định** template luôn là key code ổn định: nó có thể là nguyên câu tiếng Việt, một bundle key, hoặc chuỗi chứa placeholder.
- Nếu cần một mã lỗi API ổn định như `ORDER_REFERENCE_TOO_SHORT`, định nghĩa mã riêng hoặc ánh xạ từ metadata constraint; không dùng raw message làm mã định danh bất biến.
- Không cho người dùng tự cung cấp biểu thức message template rồi đưa thẳng vào engine nội suy; template là thành phần cấu hình phía server, cần kiểm soát nguồn.

## 6. Ví dụ đầy đủ Java 17+: đọc cả bốn thông tin

Ví dụ sử dụng **Jakarta Validation 3.0 qua Hibernate Validator 8.x** và **Spring Framework 6.2.x**. Chương trình kiểm tra ba lỗi: field gốc trống, độ dài field không đủ, và field trong object lồng nhau sai pattern. Sau đó nó cho thấy Spring ánh xạ các lỗi thành `BindingResult`.

### 6.1. Maven

Tạo `pom.xml` ở thư mục project:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>violation-details</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Hibernate Validator là implementation của Jakarta Validation. Dependency `jakarta.el` hỗ trợ cơ chế nội suy message dùng Expression Language. Khi dùng Spring Boot, thường để dependency management của Boot chọn phiên bản tương thích và thêm starter validation; ví dụ Maven ở đây cố định version để dễ tái hiện.

### 6.2. Mã Java

Tạo `src/main/java/example/ConstraintViolationDemo.java`:

```java
package example;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.beanvalidation.SpringValidatorAdapter;

public final class ConstraintViolationDemo {

    public static final class Address {
        @Pattern(
            regexp = "\\d{5}",
            message = "Mã bưu chính cần 5 chữ số"
        )
        private String zip;

        public Address(String zip) {
            this.zip = zip;
        }

        public String getZip() {
            return zip;
        }

        public void setZip(String zip) {
            this.zip = zip;
        }
    }

    public static final class OrderForm {
        @NotBlank(message = "Tên không được để trống")
        private String customerName;

        @Size(min = 4, max = 10,
              message = "Mã cần ít nhất {min} ký tự")
        private String reference;

        @Valid
        private Address shipping;

        public OrderForm(String customerName,
                         String reference,
                         Address shipping) {
            this.customerName = customerName;
            this.reference = reference;
            this.shipping = shipping;
        }

        public String getCustomerName() {
            return customerName;
        }

        public void setCustomerName(String customerName) {
            this.customerName = customerName;
        }

        public String getReference() {
            return reference;
        }

        public void setReference(String reference) {
            this.reference = reference;
        }

        public Address getShipping() {
            return shipping;
        }

        public void setShipping(Address shipping) {
            this.shipping = shipping;
        }
    }

    private static String show(Object value) {
        return value == null ? "<null>" : "\"" + value + "\"";
    }

    public static void main(String[] args) {
        OrderForm order = new OrderForm(
                " ", "AB", new Address("12x"));

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Set<ConstraintViolation<OrderForm>> found =
                    validator.validate(order);

            // Set không bảo đảm thứ tự; sort theo path để output ổn định.
            List<ConstraintViolation<OrderForm>> violations =
                    new ArrayList<>(found);
            violations.sort(Comparator.comparing(
                    v -> v.getPropertyPath().toString()));

            for (ConstraintViolation<OrderForm> v : violations) {
                System.out.println(
                    v.getPropertyPath() +
                    " | invalid=" + show(v.getInvalidValue()) +
                    " | message=" + v.getMessage() +
                    " | template=" + v.getMessageTemplate());
            }
            System.out.println("violationCount=" + violations.size());

            // Dùng cùng Jakarta Validator qua adapter của Spring.
            SpringValidatorAdapter adapter =
                    new SpringValidatorAdapter(validator);

            BeanPropertyBindingResult result =
                    new BeanPropertyBindingResult(order, "order");
            adapter.validate(order, result);

            FieldError referenceError =
                    result.getFieldError("reference");
            if (referenceError == null) {
                throw new AssertionError(
                        "Missing reference FieldError");
            }
            System.out.println(
                    "springFieldErrors=" + result.getFieldErrorCount());
            System.out.println(
                    "springReference=" + referenceError.getField() +
                    " | rejected=" +
                    show(referenceError.getRejectedValue()) +
                    " | message=" +
                    referenceError.getDefaultMessage());

            if (violations.size() != 3
                    || result.getFieldErrorCount() != 3) {
                throw new AssertionError(
                        "Expected three field violations");
            }
            System.out.println("CHECKS: PASS");
        }
    }
}
```

### 6.3. Chạy và đọc stdout

Từ thư mục chứa `pom.xml` với JDK 17+, Maven 3.9+:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.ConstraintViolationDemo
```

Các dòng do chương trình in ra, sau khi bỏ qua log phụ trợ của thư viện nếu có, được kỳ vọng như sau:

```text
customerName | invalid=" " | message=Tên không được để trống | template=Tên không được để trống
reference | invalid="AB" | message=Mã cần ít nhất 4 ký tự | template=Mã cần ít nhất {min} ký tự
shipping.zip | invalid="12x" | message=Mã bưu chính cần 5 chữ số | template=Mã bưu chính cần 5 chữ số
violationCount=3
springFieldErrors=3
springReference=reference | rejected="AB" | message=Mã cần ít nhất 4 ký tự
CHECKS: PASS
```

Quan sát trực tiếp:
- `customerName` có `@NotBlank` nên `" "` không hợp lệ; template không có placeholder nên message trùng template.
- `reference` có `@Size(min = 4)` nên message thay `{min}` bằng `4`, còn template giữ nguyên `{min}`.
- `shipping.zip` minh họa path lồng nhau nhờ `@Valid` trên `shipping`.
- `getInvalidValue()` phản ánh **giá trị Java đã được validate**. Trường hợp này đều là `String`, nhưng API trả `Object`.
- `SpringValidatorAdapter` chuyển thông tin lỗi Bean Validation thành `FieldError`; `getField()` và `getRejectedValue()` có thể tương ứng path/invalid value, nhưng **không phải** API đồng nhất với `getPropertyPath()` và `getInvalidValue()` trong mọi ngữ cảnh.

Các thông báo trong mã được viết cụ thể để kết quả không phụ thuộc một bản dịch tiếng Anh của message bundle mặc định. Trong dự án thực tế, dùng bundle nhiều locale và kiểm tra nội suy theo ngữ cảnh request.

## 7. Quan hệ giữa Jakarta `ConstraintViolation` và Spring `BindingResult`

Spring có hai bộ API khác nhau:

| Jakarta Validation | Spring validation/binding | Nhận xét |
| --- | --- | --- |
| `ConstraintViolation.getPropertyPath()` | `FieldError.getField()` | Thường cùng ý nghĩa vị trí lỗi property nhưng Spring dùng quy tắc field path/error riêng |
| `ConstraintViolation.getInvalidValue()` | `FieldError.getRejectedValue()` | Có thể tương ứng, nhưng Spring có thể giữ raw input hoặc giá trị đã bind tùy nguồn lỗi |
| `ConstraintViolation.getMessage()` | `ObjectError.getDefaultMessage()` | Thường là nội dung thông báo cho người dùng; còn có thể qua `MessageSource` |
| `ConstraintViolation.getMessageTemplate()` | **Không có getter tương ứng trực tiếp** trên `FieldError` | Spring sử dụng error codes/arguments của `MessageSourceResolvable` |
| `getConstraintDescriptor()` | `ObjectError.getCodes()`, `getArguments()` | Không phải ánh xạ 1:1; Spring dựng mã theo annotation/field/object |

Với Spring MVC, thường dùng:

```java
@PostMapping("/orders")
String submit(
        @Valid @ModelAttribute("order") OrderForm order,
        BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "orders/form";
    }
    return "orders/success";
}
```

Đây là **đoạn minh họa trong controller**; cần `jakarta.validation.Valid`, `org.springframework.web.bind.annotation.PostMapping`, `ModelAttribute`, và `org.springframework.validation.BindingResult`. Vị trí `BindingResult` phải theo ngay sau đối số model được validate khi muốn xử lý lỗi binding/validation của chính đối số đó.

- `@Valid` yêu cầu bean validation trên đối số nếu được cấu hình; `@Validated` còn cho phép chỉ định nhóm constraint của Spring.
- Với lập trình thủ công, gọi `DataBinder.bind(...)` chỉ thực hiện binding; để chạy validator cần thiết lập `binder.setValidator(...)` và gọi `binder.validate()`.
- Spring `LocalValidatorFactoryBean` và `SpringValidatorAdapter` giúp nối Jakarta Bean Validation với `org.springframework.validation.Validator`.
- Spring chọn mã lỗi (`codes`) theo loại annotation, object/field/type và `MessageCodesResolver`; **không** coi `codes[0]` là `getMessageTemplate()`.
- Một `FieldError` do **type conversion** có thể chứa chuỗi gốc người dùng nhập dù không có `ConstraintViolation`; khi thiết kế API trả lỗi phải phân loại đúng nguồn.

Một lỗi cấp class thường thành `ObjectError` thay vì `FieldError`, vì không có field cụ thể. Nếu một custom class-level validator gắn property node tường minh, Spring có thể biểu diễn nó dưới dạng field error tùy adapter và đường path. Không ép mọi lỗi vào `FieldError` bằng cách đoán tên field.

## 8. Path do custom validator quyết định trong lỗi cấp class

Giả sử ràng buộc `@ValidDateRange` đặt ở class `BookingRequest`, cần `end` không trước `start`. Ban đầu, khi `ConstraintValidator<ValidDateRange, BookingRequest>` trả `false` mà không thêm node, path thường là đường dẫn bean (cấp class).

Trong `isValid(...)`, có thể chỉ rõ lỗi liên quan field `end` bằng **trích đoạn**:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
           "{booking.end.before.start}")
       .addPropertyNode("end")
       .addConstraintViolation();
return false;
```

`context` là `jakarta.validation.ConstraintValidatorContext`. Mã trên giả định validator có thể truy cập object và đã xác định `end` không hợp lệ. Đây là trích đoạn, **không phải chương trình Java độc lập**.

Khi thêm node `end`, `getPropertyPath()` có thể thành `end` (hoặc đường dẫn lồng nhau nếu class này là bean con). Tuy nhiên, `getInvalidValue()` của **constraint cấp class** vẫn có thể là **toàn bộ `BookingRequest`**, bởi validator áp dụng lên class. Đây là ví dụ vì sao không thể lấy `getInvalidValue()` rồi ép kiểu `String` chỉ từ tên propertyPath.

Nếu `messageTemplate = "{booking.end.before.start}"`, message chỉ thành câu người dùng đọc được khi có resource bundle/`MessageInterpolator` resolve key đó. Nếu chưa có bundle, nội dung nhận được có thể vẫn là chuỗi chứa dấu `{...}`; cần kiểm thử cấu hình localization.

## 9. Thiết kế response API và logging an toàn

Không gửi nguyên cả `ConstraintViolation` hoặc `FieldError` ra JSON nếu không kiểm soát serialization. Trong HTTP API, thường chỉ cần:

```json
{
  "errors": [
    {
      "field": "reference",
      "code": "REFERENCE_TOO_SHORT",
      "message": "Mã cần ít nhất 4 ký tự"
    }
  ]
}
```

Đây là **ví dụ hợp đồng API do ứng dụng tự định nghĩa**, không phải payload Spring tự tạo. Trong đó:
- `field` được ánh xạ có kiểm soát từ path sang tên public; đừng phát tán path nội bộ không cần thiết.
- `code` là mã ổn định do ứng dụng định nghĩa, độc lập locale và câu chữ.
- `message` là thông báo phía client được phép hiển thị.
- `invalidValue` không được đưa vào mặc định; giá trị có thể nhạy cảm.
- `messageTemplate` có thể hữu ích cho quan sát nội bộ, nhưng không nhất thiết nên công khai; nó có thể lộ tên key bundle/nội dung implementation.

Nếu cần thống kê lỗi, dùng loại constraint từ `getConstraintDescriptor().getAnnotation().annotationType()`, mã nghiệp vụ hoặc category. Không gom nhóm theo `getMessage()` vì câu thông báo đổi khi locale hay bản dịch thay đổi.

Khi dùng nested/container paths, phải thống nhất một định dạng public, ví dụ `items[2].sku` hoặc JSON Pointer `/items/2/sku`, dựa trên **các node path**; tránh giả định `Path.toString()` luôn là JSON Pointer hợp lệ. Với class-level error, có thể trả `field: null` và một mã error cấp object.

## 10. Ma trận kiểm thử cần có

| Tình huống | Ví dụ | Kiểm tra bốn thuộc tính |
| --- | --- | --- |
| Field lỗi cơ bản | `@NotBlank`, name trống | Path là field; invalid value là chuỗi; message và template có thể trùng |
| Attribute interpolation | `@Size(min = 4)` | Message thay `{min}`; template giữ nguyên mẫu |
| Resource bundle | `message = "{order.required}"` | Template giữ key; message được resolve theo locale được cấu hình |
| Nested object | `@Valid Address`, `zip` sai | Path có `shipping.zip`, giá trị sai là zip |
| Nested object bằng `null` | `shipping = null` | `@Valid` một mình không báo lỗi null; cần thêm `@NotNull` nếu bắt buộc |
| Collection element | `List<@NotBlank String>` | Xem `CONTAINER_ELEMENT`, index/key và invalid element |
| Constraint cấp class | Tương quan `start/end` sai | Path cấp bean hoặc node tùy chỉnh; invalid value có thể là toàn bean |
| Cross-parameter | Constraint trên cặp tham số method | Path có method/parameter node; invalid value có thể là `Object[]` |
| Numeric binding lỗi | Trường `Integer`, input `"abc"` | `BindingResult` có type mismatch nhưng có thể không có `ConstraintViolation` |
| Bean Validation lỗi sau binding | `@Min(1)`, input `"0"` parse thành int | Có `ConstraintViolation`, invalid value là số `0` |
| Unicode/locale | Tiếng Việt, tiếng Anh, bundle thiếu | Message đúng ngôn ngữ, template giữ nguyên; test locale tường minh |
| Thứ tự kết quả | Nhiều vi phạm cùng lúc | Không giả định thứ tự Set; sort trước khi in/assert nếu cần |
| Dữ liệu nhạy cảm | Password/token lỗi | Không leak invalid value, root/leaf bean hoặc object `toString()` |
| Group validation | `@Validated(Group.class)` | Chỉ những constraint trong group phù hợp được đánh giá |

Ví dụ kiểm tra bằng unit test:

```java
Set<ConstraintViolation<OrderForm>> errors =
        validator.validate(order);
boolean hasReferenceError = errors.stream().anyMatch(v ->
        v.getPropertyPath().toString().equals("reference")
        && "AB".equals(v.getInvalidValue())
        && v.getMessageTemplate().contains("{min}")
        && v.getMessage().contains("4"));
```

Đây là **đoạn Java minh họa** nằm trong test/hàm có sẵn `validator` và `order`. Với yêu cầu ổn định, nên kiểm tra một message template đã biết và thuộc tính constraint cụ thể thay vì phụ thuộc quá nhiều vào câu chữ đã dịch.

## 11. Sai lầm phổ biến và cách xử lý

**1. So sánh `propertyPath` trực tiếp với một tên field bất kể ngữ cảnh.** Path có thể lồng nhau, chứa index/key hoặc có node method/return value. Sử dụng `Path.Node` nếu cần xác định vị trí chính xác.

**2. Coi `invalidValue` luôn là raw input String.** Bean Validation chạy trên object đã bind, còn Spring conversion có thể thất bại trước khi validator chạy. Class-level hoặc cross-parameter có kiểu khác; hãy kiểm tra null và kiểu trước khi xử lý.

**3. Gọi `toString()` và log toàn bộ invalid value.** Có nguy cơ lộ password, token, PII hoặc stack/object nội bộ. Mặc định chỉ log path/code đã kiểm soát và correlation ID.

**4. Coi `message` với `messageTemplate` là cùng một thứ.** Với `{min}`, template giữ tham số, message là kết quả nội suy; với bundle key template giữ tên key.

**5. Đồng nhất Spring `FieldError.getCodes()` với template.** Error codes được Spring dựng để phục vụ `MessageSource`, trong khi template là metadata Bean Validation trước nội suy. Không dựa vào một trong hai để định nghĩa hợp đồng API nếu không kiểm soát quy tắc.

**6. Quên `@Valid` trên property chứa object con.** Constraint trên object con không được cascade chỉ vì nó tồn tại; `@Valid` kích hoạt cascade. `@NotNull` riêng nếu object con bắt buộc hiện diện.

**7. Dựa vào thứ tự `Set<ConstraintViolation<?>>`.** Spec không cam kết thứ tự. Sắp xếp theo path và mã constraint khi cần output hoặc test xác định.

**8. Trộn `javax.validation.*` với `jakarta.validation.*`.** Các nhánh Spring Framework 6+ dùng hệ sinh thái Jakarta; Spring Framework 5 thường dùng `javax.validation`. Chọn dependencies và imports phù hợp phiên bản, không đổi một nửa.

**9. Nhầm lỗi validation với lỗi cấu hình hoặc binding.** Provider thiếu hoặc constraint định nghĩa sai có thể ném exception; field không parse được sinh lỗi Spring binding. Không biến mọi exception thành violation với thông báo không đáng tin.

## 12. Checklist trước khi đưa vào sản phẩm

- [ ] Chạy Bean Validation trên đúng đối tượng đã bind và đúng validation group.
- [ ] Lấy `getPropertyPath()` bằng `Path` khi có collection, map, method hoặc nested object.
- [ ] Xử lý `getInvalidValue()` dưới dạng `Object`, null-safe và có chính sách bảo vệ dữ liệu.
- [ ] Hiểu `getMessage()` là **đã nội suy**, còn `getMessageTemplate()` là **chưa nội suy**.
- [ ] Kiểm thử resource bundle, locale, placeholder và trường hợp thiếu bản dịch.
- [ ] Tách `ConstraintViolation` khỏi Spring `BindingResult`/`FieldError`; có test cả lỗi type conversion.
- [ ] Dùng mã lỗi API ổn định do ứng dụng quản lý, không phụ thuộc text của thông báo.
- [ ] Sort các violation trước khi xuất log/assert nếu cần thứ tự xác định.
- [ ] Kiểm tra chính sách cho class-level, nested và container-element constraint.

## Tài liệu chính thức

- Jakarta Validation API 3.0 — `ConstraintViolation<T>`: https://javadoc.io/static/jakarta.validation/jakarta.validation-api/3.0.0/jakarta/validation/ConstraintViolation.html
- Jakarta Bean Validation 3.0 specification, mục ConstraintViolation và message interpolation: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation API 3.0 — `Path`: https://javadoc.io/static/jakarta.validation/jakarta.validation-api/3.0.0/jakarta/validation/Path.html
- Spring Framework 6.2 — Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — `SpringValidatorAdapter`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/SpringValidatorAdapter.html
- Spring Framework 6.2 — `BindingResult`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/BindingResult.html
- Hibernate Validator 8 — Reference Guide: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
