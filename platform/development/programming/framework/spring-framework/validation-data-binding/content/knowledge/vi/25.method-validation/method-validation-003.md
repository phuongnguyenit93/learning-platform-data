# ExecutableValidator và gọi kiểm tra trực tiếp

## 1. Vì sao cần kiểm tra phương thức trực tiếp?

Jakarta Validation (Bean Validation) hỗ trợ ràng buộc không chỉ trên field và DTO mà còn trên **tham số phương thức**, **giá trị trả về**, **tham số constructor** và **đối tượng do constructor tạo ra**. Xét ví dụ trong một service:

```java
public class InventoryService {

    @NotBlank(message = "Result must have an id")
    public String reserve(
            @NotBlank(message = "Code is required") String productCode,
            @Min(value = 1, message = "Quantity must be positive") int quantity) {
        return "RES-1";
    }
}
```

Các annotation như `@NotBlank` và `@Min` chỉ công bố metadata ràng buộc. Việc gọi `new InventoryService().reserve("", 0)` trong Java thuần **không tự động kiểm tra** các annotation. Cần một lớp tích hợp (interceptor, proxy, framework) hoặc một lệnh validation tường minh trước/sau khi gọi.

`jakarta.validation.executable.ExecutableValidator` là API chuẩn để chủ động kiểm tra **hợp đồng của một lần gọi** mà không cần Spring AOP hay request HTTP. Đây là công cụ hữu ích khi:

- Viết unit test cho điều kiện đầu vào và đầu ra của public API.
- Tự xây dựng job scheduler, command handler, RPC dispatcher hoặc một cơ chế gọi method bằng reflection.
- Kiểm tra constructor arguments trước khi tạo instance, hoặc state của instance ngay sau khi tạo.
- Định vị chính xác một vi phạm thuộc parameter, return, cross-parameter hay cascade của executable.

Sau bài học, bạn sẽ biết cách lấy `ExecutableValidator`, gọi đủ bốn phương thức, chuẩn bị `Method`/`Constructor`/`Object[]` chính xác, đọc `ConstraintViolation`, dùng groups và `@Valid`, cũng như hiểu cách cơ chế này liên hệ với Spring MVC và method validation qua proxy.

## 2. Hai API khác nhau: `Validator` và `ExecutableValidator`

Khởi tạo một Jakarta Validation provider (ví dụ Hibernate Validator) và lấy hai API:

```java
try (ValidatorFactory factory = Validation.buildDefaultValidatorFactory()) {
    Validator validator = factory.getValidator();

    // Bean/property-level validation:
    Set<ConstraintViolation<Customer>> beanErrors =
            validator.validate(customer);

    // Method/constructor-level validation:
    ExecutableValidator executable = validator.forExecutables();
}
```

Đây là đoạn minh họa, giả sử có lớp `Customer` và biến `customer`. Ý nghĩa:

- `validator.validate(bean)` kiểm tra các constraint trên object: field, getter JavaBeans, class và cascade từ những vị trí đó.
- `validator.validateProperty(bean, "name")` kiểm tra constraint của property `name`, **không** kiểm tra một method parameter tên `name`.
- `validator.forExecutables()` tạo điểm truy cập để kiểm tra ràng buộc trên các executable (method và constructor).

Chỉ truyền `service` vào `validator.validate(service)` **không** khiến provider tự chọn một method rồi kiểm tra các argument của method đó. `ExecutableValidator` cần thêm ngữ cảnh của lời gọi: reflection object và giá trị được truyền hoặc trả về.

## 3. Bốn phương thức cốt lõi

| API | Kiểm tra | Đầu vào |
| --- | --- | --- |
| `validateParameters(object, method, parameterValues, groups...)` | Các constraint trên từng parameter và **cross-parameter** của instance method | Object nhận lời gọi, `Method`, mảng arguments |
| `validateReturnValue(object, method, returnValue, groups...)` | Constraint và cascade áp dụng lên **giá trị trả về của method** | Object, `Method`, return value |
| `validateConstructorParameters(constructor, parameterValues, groups...)` | Constraint parameter và cross-parameter của constructor | `Constructor`, mảng arguments |
| `validateConstructorReturnValue(constructor, createdObject, groups...)` | Constraint/cascade trên **đối tượng do constructor tạo ra** | `Constructor` và instance mới |

Các hàm đều trả về `Set<ConstraintViolation<T>>`; không có lỗi thì tập rỗng, **không phải `null`**. Tham số `Class<?>... groups` là tùy chọn; khi bỏ qua sẽ chạy group `jakarta.validation.groups.Default`. Chính API trực tiếp không ném `ConstraintViolationException` để báo một lỗi validation thông thường, mà để code gọi quyết định xử lý tập violations.

**Đặc điểm quan trọng:** `validateParameters` không thực thi method; `validateReturnValue` không gọi method để tự lấy kết quả. Hai phương thức constructor cũng không tự khởi tạo đối tượng. Người gọi phải điều khiển thứ tự và chủ động dừng khi không đạt điều kiện.

## 4. Trình tự chuẩn của validation thủ công

### 4.1. Với instance method

```text
Method + object + Object[] arguments
               |
               v
      validateParameters(...)
               |
         có violations?
           /       \
         có       không
         |           |
      từ chối     gọi method
                     |
                  returnValue
                     |
                     v
       validateReturnValue(...)
                     |
               có violations?
                 /       \
               có       không
               |           |
             báo lỗi      chấp nhận
```

Ví dụ khung mã (cần có `service`, provider và service method tương ứng):

```java
Method method = InventoryService.class.getMethod(
        "reserve", String.class, int.class);

Object[] inputs = {"P100", 2};
var before = executable.validateParameters(
        service, method, inputs);

if (!before.isEmpty()) {
    throw new ConstraintViolationException(before);
}

String actualResult =
        service.reserve((String) inputs[0], (Integer) inputs[1]);

var after = executable.validateReturnValue(
        service, method, actualResult);

if (!after.isEmpty()) {
    throw new ConstraintViolationException(after);
}
```

`ConstraintViolationException` thuộc `jakarta.validation.ConstraintViolationException`, và được **người gọi chủ động ném** ở đây. Vì `validateReturnValue` nhận chính kết quả thực tế, nó có thể kiểm tra hậu điều kiện mà method đã cam kết.

Nếu mục tiêu là từ chối một lời gọi vi phạm trước khi gây side effect, **phải** chặn trước khi gọi method. Kiểm tra lại sau khi đã ghi dữ liệu hoặc gọi hệ thống ngoài không hoàn tác được các side effect đã xảy ra.

### 4.2. Với constructor

```java
Constructor<Order> constructor =
        Order.class.getConstructor(String.class);

Object[] inputs = {"ORD-1"};
var before = executable.validateConstructorParameters(
        constructor, inputs);

// Chỉ khởi tạo khi before.isEmpty().
Order created = constructor.newInstance(inputs);

var after = executable.validateConstructorReturnValue(
        constructor, created);
```

Đây là đoạn minh họa, giả sử `Order` có constructor public nhận `String`. `validateConstructorParameters` không chạy constructor; `validateConstructorReturnValue` nhận đối tượng đã tạo. Với constructor, return value theo nghĩa Jakarta Validation chính là **đối tượng mới**, không phải một kiểu return được khai báo trong Java source.

## 5. Ví dụ chạy hoàn chỉnh: bốn lần kiểm tra chính

Ví dụ dùng **Java 17+**, **Jakarta Validation 3.0** qua **Hibernate Validator 8.0.6.Final**. Không cần Spring để chạy. Ta thiết kế hai lớp:
- `ReceiptService.issue` có constraint trên hai parameters và một return.
- `Invoice` có constraint trên parameter constructor và constraint trên field; `@Valid` ở constructor kích hoạt cascade trên instance tạo ra.

Để stdout nhất quán, các message dùng mã cố định và được sắp xếp bằng `TreeSet`. Không dựa vào thứ tự trong `Set<ConstraintViolation<?>>`.

Cấu trúc:

```text
executable-demo/
├── pom.xml
└── src/main/java/demo/
    └── ExecutableDemo.java
```

### 5.1. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>executable-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
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

`hibernate-validator` cung cấp provider và dependency Jakarta Validation API. `expressly` cung cấp Jakarta Expression Language cho message interpolation. Khi dùng Spring Boot, thông thường khai báo `spring-boot-starter-validation` để Boot quản lý các phiên bản tương thích.

### 5.2. File `src/main/java/demo/ExecutableDemo.java`

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.executable.ExecutableValidator;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.Set;
import java.util.TreeSet;

public class ExecutableDemo {

    public static final class ReceiptService {

        // Constraint trên METHOD: áp dụng vào return value.
        @NotBlank(message = "receipt.blank")
        public String issue(
                @NotBlank(message = "code.blank") String code,
                @Min(value = 1, message = "quantity.too.small")
                int quantity) {
            return "REC-" + code + "-" + quantity;
        }
    }

    public static final class Invoice {

        // Constraint trên FIELD: được xét khi cascade đến object.
        @NotBlank(message = "invoice.number.blank")
        private final String number;

        // @Valid trên CONSTRUCTOR: cascade đến instance được tạo.
        @Valid
        public Invoice(
                @NotBlank(message = "invoice.argument.blank")
                String number) {
            this.number = number;
        }

        public String getNumber() {
            return number;
        }
    }

    private static <T> void print(
            String label, Set<ConstraintViolation<T>> violations) {
        TreeSet<String> messages = new TreeSet<>();

        for (ConstraintViolation<T> violation : violations) {
            messages.add(violation.getMessage());
        }

        System.out.println(label + " -> " + messages);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            ExecutableValidator executable = validator.forExecutables();

            ReceiptService service = new ReceiptService();
            Method method = ReceiptService.class.getMethod(
                    "issue", String.class, int.class);

            // 1. Hai method arguments sai.
            print("method-params-invalid",
                    executable.validateParameters(
                            service, method, new Object[] {"", 0}));

            // 2. Một method return value sai.
            print("method-return-invalid",
                    executable.validateReturnValue(
                            service, method, ""));

            Constructor<Invoice> constructor =
                    Invoice.class.getConstructor(String.class);

            // 3. Một constructor argument sai.
            print("constructor-params-invalid",
                    executable.validateConstructorParameters(
                            constructor, new Object[] {""}));

            // 4. State của instance mới sai; @Valid cho cascade.
            Invoice invalidInvoice = new Invoice("");
            print("constructor-return-invalid",
                    executable.validateConstructorReturnValue(
                            constructor, invalidInvoice));

            // 5. Bốn nhánh hợp lệ tương ứng.
            print("method-params-valid",
                    executable.validateParameters(
                            service, method, new Object[] {"P1", 2}));

            print("method-return-valid",
                    executable.validateReturnValue(
                            service, method, "REC-P1-2"));

            print("constructor-params-valid",
                    executable.validateConstructorParameters(
                            constructor, new Object[] {"INV-7"}));

            print("constructor-return-valid",
                    executable.validateConstructorReturnValue(
                            constructor, new Invoice("INV-7")));
        }
    }
}
```

Chạy trong thư mục `executable-demo` (JDK 17+, Maven và truy cập dependency Maven Central):

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ExecutableDemo
```

Các dòng mà `System.out` của `ExecutableDemo` in ra (không tính log Maven/provider nếu có):

```text
method-params-invalid -> [code.blank, quantity.too.small]
method-return-invalid -> [receipt.blank]
constructor-params-invalid -> [invoice.argument.blank]
constructor-return-invalid -> [invoice.number.blank]
method-params-valid -> []
method-return-valid -> []
constructor-params-valid -> []
constructor-return-valid -> []
```

### 5.3. Vì sao các kết quả đúng như vậy?

- `validateParameters(service, method, {"", 0})` kiểm tra cả `@NotBlank` trên `code` lẫn `@Min(1)` trên `quantity`. Hai lỗi được báo, không cần thực thi `issue`.
- `validateReturnValue(service, method, "")` nhận chuỗi rỗng do bài test cung cấp, áp `@NotBlank` ở declaration của method và nhận `receipt.blank`. Nó **không tự gọi `issue`**.
- `validateConstructorParameters(constructor, {""})` kiểm tra `@NotBlank` trên tham số constructor: `invoice.argument.blank`.
- `validateConstructorReturnValue(constructor, new Invoice(""))` gặp `@Valid` đặt trên constructor, cascade vào field `number` và thấy `invoice.number.blank`. Nếu bỏ `@Valid` ở constructor, API kiểm tra return constructor **không tự quét field** chỉ vì field có constraint.
- Bốn lần gọi còn lại đều hợp lệ, kết quả là tập rỗng `[]`.

Trong production, hãy truyền **return thực tế** vào `validateReturnValue`; ví dụ cố ý dùng `""` để kiểm tra độc lập API. Đặc biệt, nếu bạn trực tiếp gọi `new Invoice("")` ở Java thuần, constructor vẫn chạy; Jakarta Validation chỉ báo lỗi khi code gọi `validateConstructorReturnValue` hoặc có lớp tích hợp áp dụng quy tắc.

## 6. Đọc và xử lý `ConstraintViolation`

`ConstraintViolation` cung cấp nhiều thông tin hơn message. Khi đang ở trong `main` của ví dụ 5:

```java
Set<ConstraintViolation<ReceiptService>> errors =
        executable.validateParameters(
                service, method, new Object[] {"", 0});

for (ConstraintViolation<ReceiptService> v : errors) {
    System.out.println("path=" + v.getPropertyPath());
    System.out.println("message=" + v.getMessage());
    System.out.println("invalid=" + v.getInvalidValue());
    System.out.println("rootClass=" + v.getRootBeanClass().getName());
    System.out.println("arguments=" +
            java.util.Arrays.toString(v.getExecutableParameters()));
}
```

Đây là **đoạn code bổ sung**, không phải file Java độc lập. Một `ConstraintViolation` có các API:

| API | Ý nghĩa |
| --- | --- |
| `getPropertyPath()` | Đường đi từ method/constructor đến parameter, return, property cascade hoặc container element gây lỗi |
| `getMessage()`, `getMessageTemplate()` | Message đã nội suy và mẫu gốc |
| `getInvalidValue()` | Giá trị mà validator nhận để kiểm tra; với cross-parameter có thể là `Object[]` |
| `getRootBean()`, `getRootBeanClass()` | Root instance và class; với constructor parameter validation, root bean có thể là `null` |
| `getExecutableParameters()` | Mảng arguments trong lỗi thuộc kiểm tra **parameters**; ngoài nhánh này là `null` |
| `getExecutableReturnValue()` | Return object/value ở nhánh kiểm tra **return value**; ngoài nhánh này là `null` |
| `getConstraintDescriptor()` | Metadata annotation, attributes như `min`, `max`, `groups` và `message` |

Đường dẫn parameter có thể có dạng `issue.arg0` nếu tên tham số không có sẵn, hoặc `issue.code` khi provider biết tên. Return có node `<return value>`; cascade constructor có thể kết thúc ở `Invoice.<return value>.number`. **Không hard-code `arg0`** làm business key: tên phụ thuộc `ParameterNameProvider` và compiler flag `-parameters`. Nếu phải phân loại lỗi, duyệt `Path.Node` và kiểm tra `getKind()` (ví dụ `METHOD`, `CONSTRUCTOR`, `PARAMETER`, `RETURN_VALUE`, `PROPERTY`, `CROSS_PARAMETER`).

Tập `ConstraintViolation` không có thứ tự duyệt cố định. Khi trả lỗi JSON hoặc ghi log, sắp xếp theo property path và code nếu cần output ổn định. Đồng thời đừng tự động đẩy `getInvalidValue()` ra response: nó có thể chứa thông tin nhạy cảm.

## 7. Cascade trên tham số và kết quả trả về

### 7.1. Tham số là DTO

```java
public record Customer(
        @NotBlank String name,
        @NotBlank String email) {}

public void register(@NotNull @Valid Customer customer) {
    // ...
}
```

Đây là hai khai báo **minh họa**, cần đặt vào lớp thích hợp và import Jakarta Validation. Khi `validateParameters` nhận `new Customer("", "a@b")` ở vị trí `customer`, `@Valid` kích hoạt validation sâu xuống `Customer.name`. `@NotNull` áp lên **chính tham số customer** để bắt trường hợp customer null.

`@Valid` và `@NotNull` có mục đích khác nhau: một cái đi sâu vào object graph, cái còn lại kiểm tra null ngay tại tầng đang xét. Nếu input `null` mà chỉ có `@Valid`, validation cascade thường bỏ qua giá trị null.

### 7.2. Return là DTO hoặc container

```java
@NotNull
@Valid
public Customer findCustomer(String id) {
    // ...
}

public List<@NotBlank String> listCodes() {
    // ...
}
```

`validateReturnValue` có thể kiểm tra `@NotNull` trên return, cascade `@Valid` qua object, và constraints trên **container elements** như từng `String` trong `List`. Với `List<@NotBlank String>`, provider dùng value extractor tích hợp cho List để xét phần tử và báo index nếu phù hợp.

Với method trả `void`, không có return value hữu ích để kiểm tra; trường hợp này thường tập trung vào parameters hoặc cross-parameter rules.

### 7.3. Constructor return và `@Valid`

Với constructor `@Valid public Invoice(...)` ở ví dụ 5, provider được yêu cầu cascade trên **instance sau khi khởi tạo**. Nếu muốn kiểm tra field của đối tượng mà không dựa vào constructor metadata, bạn cũng có thể dùng `validator.validate(invoice)`; tuy nhiên đó là một API bean validation khác với kiểm tra hợp đồng constructor. Hai cách không nên bị nhầm là tự động tương đương.

## 8. Cross-parameter constraints: nhìn nhiều arguments cùng lúc

Nhiều business rule không thuộc về một argument đơn lẻ: ví dụ ngày bắt đầu phải không muộn hơn ngày kết thúc.

```java
@ValidDateRange
public void schedule(LocalDate startDate, LocalDate endDate) {
    // ...
}
```

`@ValidDateRange` ở đây là một **custom cross-parameter constraint**, không có sẵn trong Jakarta Validation. Annotation cần target `METHOD`/`CONSTRUCTOR`, có khai báo `@Constraint` và một `ConstraintValidator` nhắm tới mảng tham số.

Một lõi validator minh họa:

```java
@SupportedValidationTarget(ValidationTarget.PARAMETERS)
public class ValidDateRangeValidator
        implements ConstraintValidator<ValidDateRange, Object[]> {

    @Override
    public boolean isValid(
            Object[] values, ConstraintValidatorContext context) {
        if (values == null || values.length != 2) {
            return false;
        }

        LocalDate start = (LocalDate) values[0];
        LocalDate end = (LocalDate) values[1];

        return start == null || end == null || !start.isAfter(end);
    }
}
```

Đoạn trên **chưa phải chương trình độc lập** vì cần khai báo `@ValidDateRange` và import `java.time.LocalDate`, `jakarta.validation.*`, `jakarta.validation.constraintvalidation.*`. Khi annotation vừa hỗ trợ constraint generic vừa cross-parameter, có thể cần đặt `validationAppliesTo = ConstraintTarget.PARAMETERS` để giải quyết sự mơ hồ theo đặc tả.

Cả `validateParameters` và `validateConstructorParameters` đều đánh giá cross-parameter constraints. Violation loại này thường có node `<cross-parameter>` và `getInvalidValue()` là `Object[]`. Nếu chỉ đặt hai `@NotNull` lên các tham số, ta vẫn chưa kiểm tra được điều kiện so sánh hai ngày.

## 9. Groups khi kiểm tra thủ công

Mỗi hàm `ExecutableValidator` nhận varargs `Class<?>... groups`. Nếu không truyền, provider chạy group `Default`. Một constraint gắn group riêng **không tự chạy cùng Default** trừ khi bạn yêu cầu group đó hoặc có kế thừa/group sequence liên quan.

Ví dụ minh họa:

```java
public interface StrictCheck {}

public void publish(
        @NotBlank String title,
        @Size(min = 8, groups = StrictCheck.class)
        String content) {
    // ...
}
```

Giả sử đã lấy đúng `publishMethod` và `service` cho khai báo trên:

```java
executable.validateParameters(
        service, publishMethod, new Object[] {"Intro", "abc"});
// Default: không kiểm tra @Size thuộc StrictCheck.

executable.validateParameters(
        service, publishMethod, new Object[] {"Intro", "abc"},
        StrictCheck.class);
// StrictCheck: @Size vi phạm. @NotBlank mặc định
// không tự động được xét nếu chỉ yêu cầu StrictCheck.

executable.validateParameters(
        service, publishMethod, new Object[] {"Intro", "abc"},
        jakarta.validation.groups.Default.class,
        StrictCheck.class);
// Yêu cầu cả Default và StrictCheck.
```

Mã trên là đoạn **minh họa API**, không thuộc file `ExecutableDemo.java` đã viết ở mục 5. Khi cần thứ tự và dừng theo từng giai đoạn group, xem `@GroupSequence` thay vì giả định thứ tự của varargs sẽ ép provider thực hiện tuần tự.

## 10. Spring Framework gọi method validation thế nào?

### 10.1. Spring AOP cho service

Một cách phổ biến để tự động kích hoạt method validation ở tầng service là:
- Có Jakarta Validation provider trên classpath.
- Có `MethodValidationPostProcessor` (trong nhiều ứng dụng Spring Boot có starter validation, Boot có thể tự cấu hình).
- Đặt Spring `@Validated` trên **class bean**; gọi method qua **Spring proxy**.

Đoạn sau dành cho một ứng dụng Spring đã cấu hình, **không phải file Java độc lập** của mục 5:

```java
@Service
@Validated
public class PriceService {

    @NotNull
    public BigDecimal calculate(
            @NotBlank String sku,
            @Positive int quantity) {

        return BigDecimal.TEN;
    }
}
```

Nếu dùng Spring Framework thuần và cần khai báo post-processor:

```java
@Configuration
class ValidationConfig {

    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        return new MethodValidationPostProcessor();
    }
}
```

Cần các import Spring `@Service`, `@Validated`, `@Configuration`, `@Bean`, `MethodValidationPostProcessor`, Jakarta `@NotNull`/`@NotBlank`/`@Positive` và `java.math.BigDecimal`.

Với cấu hình mặc định của `MethodValidationPostProcessor`, vi phạm có thể được ném dưới dạng `jakarta.validation.ConstraintViolationException`. Spring còn có tùy chọn `setAdaptConstraintViolations(true)` để tạo `MethodValidationException` với kết quả được adapt qua `MessageSourceResolvable`.

**Hạn chế của proxy:** Nếu gọi `this.calculate(...)` bên trong chính `PriceService`, hoặc tạo instance bằng `new PriceService()` ngoài Spring, invocation không đi qua proxy nên cơ chế method validation bằng AOP có thể không chạy. `ExecutableValidator` trực tiếp là lựa chọn khi bạn chủ động kiểm tra tại một vị trí code và không muốn phụ thuộc AOP.

### 10.2. Spring MVC 6.1+ có method validation tích hợp

Từ Spring Framework 6.1, MVC tự hỗ trợ method validation của handler khi ràng buộc đặt **trực tiếp** trên method parameters hoặc return. Ví dụ (đoạn minh họa controller):

```java
@RestController
@RequestMapping("/products")
public class ProductController {

    @GetMapping("/{code}")
    public String lookup(
            @PathVariable @NotBlank String code) {

        return code;
    }
}
```

- Nếu MVC chạy **method validation** vì có `@Constraint` trực tiếp trên tham số/return, một lỗi thường là `HandlerMethodValidationException`.
- Nếu chỉ validate một DTO `@Valid @RequestBody` hoặc `@ModelAttribute` theo argument validation thông thường, một lỗi thường là `MethodArgumentNotValidException`.
- `@Valid` bản thân không phải constraint và không tự động khiến MVC chọn nhánh method validation; nó đánh dấu cascade.
- Với controller đã đặt `@Validated` ở class level để kích hoạt AOP kiểu cũ, tài liệu Spring MVC 6.1+ hướng dẫn bỏ class-level `@Validated` để sử dụng nhánh built-in mới.

Vì exception và cơ chế xử lý HTTP khác nhau theo chữ ký handler, đừng gắn cứng một exception duy nhất cho mọi trường hợp trong `@ControllerAdvice`.

### 10.3. Tự gọi API trong một Spring bean

Bạn có thể inject `jakarta.validation.Validator` do Spring cấu hình và lấy API thực thi:

```java
@Component
public class ManualMethodChecker {

    private final Validator validator;

    public ManualMethodChecker(Validator validator) {
        this.validator = validator;
    }

    public <T> Set<ConstraintViolation<T>> check(
            T target, Method method, Object[] values) {
        return validator.forExecutables()
                .validateParameters(target, method, values);
    }
}
```

Đây là đoạn minh họa, cần các import Spring, Jakarta Validation, reflection và collections. Cách này thích hợp cho framework tích hợp riêng hay workflow gọi method động. Nếu lời gọi bình thường đã được Spring proxy validate, việc thêm kiểm tra thủ công ở chính luồng ấy có thể gây **validate hai lần**, không cải thiện bảo đảm hợp đồng.

## 11. Reflection: chuẩn bị dữ liệu đầu vào chính xác

### 11.1. Method overload

`Class.getMethod(name, parameterTypes...)` nhận **đúng kiểu các tham số**. Với hai overload:

```java
public void save(String id, int amount) { /* ... */ }
public void save(String id, long amount) { /* ... */ }
```

Hai `Method` khác nhau:

```java
Method a = Target.class.getMethod("save", String.class, int.class);
Method b = Target.class.getMethod("save", String.class, long.class);
```

Đây là đoạn minh họa, giả sử các method nằm trong lớp `Target`. `Object[]` phải khớp số lượng, vị trí và kiểu arguments. Primitive như `int` được truyền dưới dạng `Integer` trong mảng. Không lấy ngẫu nhiên method đầu tiên chỉ dựa vào tên.

### 11.2. Không có tham số, varargs và null

- Với method không tham số, truyền `new Object[0]`. Không truyền chính `parameterValues = null`.
- Giá trị **phần tử** trong `Object[]` được phép `null` khi phù hợp, để `@NotNull` bắt lỗi. Nhưng mảng arguments bản thân `null` là lời gọi API không hợp lệ.
- Varargs như `String... values` xuất hiện trong reflection với một tham số cuối kiểu `String[]`. Khi build `Object[]`, truyền **một phần tử chứa mảng `String[]`** cho vị trí cuối.
- `validateReturnValue` nhận giá trị return phù hợp với kiểu method; gọi API với Method không tương ứng object hoặc loại dữ liệu không tương thích có thể gây `IllegalArgumentException`.
- `getMethod` chỉ tìm public methods; với nonpublic methods, `getDeclaredMethod` là một API reflection khác, và quyền truy cập/khả năng intercept phụ thuộc môi trường.

### 11.3. Method inheritance và static method

Theo Jakarta Validation, method constraints chịu các quy tắc hợp đồng kiểu Liskov: subclass không được tùy ý **siết chặt precondition của parameter** trên method override; return constraints có thể tăng cường postcondition trong giới hạn đặc tả. Khai báo sai trong hierarchy có thể dẫn tới `ConstraintDeclarationException`. Không đánh dấu cascaded return lặp lại bất hợp lệ trên cùng nhánh kế thừa.

**Static methods** không được portable method validation của Jakarta Validation đảm bảo. Đừng dùng constraint trên một static method như hàng rào nghiệp vụ nếu thiếu cơ chế kiểm tra riêng.

## 12. Gọi API trực tiếp và `@ValidateOnExecution`

`jakarta.validation.executable.ValidateOnExecution` và cấu hình executable validation trong `validation.xml` dùng để định hướng **lớp tích hợp tự động** chọn executable nào khi intercept. Theo Jakarta Validation specification, bốn phương thức `ExecutableValidator` được gọi **tường minh** vẫn thực hiện kiểm tra tương ứng ngay cả khi cấu hình automatic executable validation không chọn executable đó. Đây là sự phân biệt quan trọng khi debug tình huống "gọi trực tiếp thì có lỗi, nhưng gọi service thông thường không thấy exception".

Không nên tự suy luận rằng `@ValidateOnExecution` sẽ khiến `Validator.forExecutables()` bỏ qua lời gọi validate; nó không phải công tắc tắt API kiểm tra thủ công.

## 13. Exceptions và cách xử lý vi phạm

| Tình huống | Kết quả |
| --- | --- |
| `@NotBlank`, `@Min` hoặc cascade trả false | Tập `ConstraintViolation` không rỗng; API trực tiếp không tự ném exception lỗi nghiệp vụ |
| Object/Method/Constructor không tương thích, sai số/type arguments, null ở tham số API bắt buộc | `IllegalArgumentException` |
| Không có validator hỗ trợ kiểu được constraint nhắm đến (ví dụ `@NotBlank` cho `int`) | `UnexpectedTypeException`, một loại `ValidationException` |
| Sai constraint declaration hoặc inheritance method constraint | `ConstraintDeclarationException` hay lỗi cấu hình liên quan |
| Spring AOP tự động chặn invocation | Thường `ConstraintViolationException`, có thể `MethodValidationException` nếu adapt |
| Spring MVC method validation trên handler | Có thể `HandlerMethodValidationException` (đặc biệt với direct constraints trên tham số/return) |

Nếu bạn tự điều phối invocation:

```java
var violations = executable.validateParameters(
        service, method, new Object[] {"", 0});

if (!violations.isEmpty()) {
    throw new ConstraintViolationException(violations);
}
```

Đoạn này dùng biến từ ví dụ 5, giả sử đã import `jakarta.validation.ConstraintViolationException`. Nó cho thấy exception do **chính ứng dụng quyết định ném**. Không dùng `catch (ValidationException ignored)` để bỏ qua các lỗi cấu hình provider. Khi trả lỗi ra mạng, chỉ đưa path/message/code được kiểm soát, không tự động trả dữ liệu nguyên bản từ `getInvalidValue()`.

## 14. Những lỗi thường gặp

| Sai lầm | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Gọi method Java trực tiếp và mong constraint tự chặn | Annotation chỉ là metadata | Cài đặt integration Spring phù hợp hoặc gọi `ExecutableValidator` |
| Dùng `validator.validate(service)` để kiểm tra method argument | Không có `Method` và giá trị parameter | Dùng `validateParameters` |
| Quên kiểm tra return value | Mới kiểm tra precondition, bỏ postcondition | Gọi `validateReturnValue` trên return thực tế |
| Gọi validate với `Object[]` sai thứ tự | Reflection argument mapping bị lệch | Lấy đúng signature và truyền đúng index |
| Dùng `null` thay cho `new Object[0]` | API cần mảng arguments hợp lệ | Truyền mảng rỗng cho zero-argument method |
| Quên `@Valid` trên constructor nhưng mong quét field của instance | Chưa có cascade từ constructor return | Dùng `@Valid` trên constructor hoặc gọi bean validation riêng |
| Khẳng định thứ tự `Set<ConstraintViolation>` cố định | Không có bảo đảm thứ tự | Sort theo path/code nếu output cần ổn định |
| Mặc định tên tham số luôn là `arg0` | Tên phụ thuộc ParameterNameProvider/compiler | Xem node kind; dùng `-parameters` nếu cần tên thực |
| Không thấy method validation trong `this.serviceMethod()` | Self-invocation không đi qua Spring proxy | Chuyển logic qua bean proxy phù hợp hoặc validate thủ công |
| Trộn `javax.validation` với Jakarta Validation của Spring Boot 3+ | Khác namespace/API generation | Dùng đồng nhất `jakarta.validation` và dependency tương thích |

## 15. Chiến lược kiểm thử

Với mỗi method có hợp đồng validation, nên bao phủ những tình huống độc lập:

1. **Precondition:** `null`, rỗng, min/max, DTO cascade, list/container element.
2. **Cross-parameter:** từng giá trị có thể hợp lệ nhưng mối liên hệ giữa hai tham số sai.
3. **Postcondition:** method trả `null`, rỗng, DTO có field sai hoặc collection chứa phần tử sai.
4. **Constructor:** argument sai trước khởi tạo; state sai sau khởi tạo.
5. **Groups:** `Default` và từng group tùy chỉnh, cùng group sequence khi có.
6. **Integration:** cùng rule chạy qua service proxy hoặc MVC thật như luồng production, thay vì kết luận từ `validator.validate(bean)`.

Nên kiểm tra cả `getPropertyPath()` (bằng node kind nếu có thể), `getMessageTemplate()` và số lượng violations. Với ví dụ `Invoice`, constructor parameter và constructor return có thể cùng mang thông báo "blank" về mặt ý nghĩa nhưng là **hai giai đoạn khác nhau**, được phản ánh trong đường dẫn lỗi.

## 16. Bài tập củng cố

1. Đổi `@Min(1)` trong `ReceiptService.issue` thành `@Min(3)`. Kiểm tra lại `{"P1", 2}` bằng `validateParameters` và dự đoán kết quả.
2. Thử chạy `service.issue("", 0)` bằng Java thuần rồi kiểm tra return. Giải thích vì sao lời gọi thực tế vẫn thực thi nếu không có interceptor.
3. Bỏ `@Valid` trên constructor `Invoice`. So sánh `validateConstructorReturnValue(constructor, new Invoice(""))` với `validator.validate(new Invoice(""))` để thấy khác biệt giữa constructor contract và bean validation.
4. Thêm `@Valid Customer` vào tham số method, cố tình để trống một field rồi quan sát path của violation.
5. Thêm group `StrictCheck` cho một constraint; gọi `validateParameters` với Default, StrictCheck, và cả hai.
6. Chuyển `ReceiptService` thành bean Spring `@Validated`, kiểm tra lời gọi từ bean khác qua proxy và từ `this.issue(...)`, rồi giải thích kết quả.

**Ghi nhớ:** `ExecutableValidator` cho phép kiểm tra rõ ràng "method/constructor nào, arguments/return nào, group nào". API **trả violations**; việc dừng lời gọi, ném exception hoặc trả lỗi HTTP thuộc lớp tích hợp. Với Spring, method validation tự động chính là một cơ chế điều phối kiểm tra quanh invocation khi được cấu hình và gọi đúng đường đi.

## Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 specification — Method/constructor constraints](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#constraintdeclarationvalidationprocess-methodlevelconstraints)
- [Jakarta Bean Validation 3.0 specification — `ExecutableValidator`](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#validationapi)
- [Jakarta Validation API 3.0 — ExecutableValidator](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executable/executablevalidator)
- [Hibernate Validator 8 — Method/constructor constraints](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#section-method-constraints)
- [Spring Framework — Method validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)