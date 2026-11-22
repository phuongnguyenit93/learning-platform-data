# Phân biệt kiểm tra constructor bằng API chuẩn với AOP của Spring

## 1. Tại sao constructor validation dễ bị hiểu sai?

Khi đọc một lớp Java có ràng buộc ở constructor, ta thường nghĩ rằng dữ liệu sai sẽ bị từ chối ngay khi gọi `new`:

```java
public class Booking {
    private final String code;

    public Booking(@NotBlank String code) {
        this.code = code;
    }
}
```

Tuy nhiên, trong **Java thuần**, lời gọi `new Booking("")` vẫn thực thi constructor bình thường. `@NotBlank` là *metadata* của Jakarta Validation, không phải câu lệnh `if` do JVM tự chèn. Để kiểm tra hợp đồng của constructor cần có **một chủ thể kích hoạt validation**, ví dụ code gọi `ExecutableValidator` hoặc một lớp tích hợp được xây dựng riêng.

Spring Framework có `@Validated` và cơ chế `MethodValidationPostProcessor`, nhưng Spring AOP thông thường dùng **proxy cho các lời gọi phương thức trên Spring bean**. Proxy đó **không chặn việc gọi constructor**. Vì thế không thể suy ra “đã bật Spring method validation” thì mọi tham số `@NotBlank` của constructor cũng được kiểm tra.

Bài học phân biệt ba thao tác:

1. **Constructor parameter validation:** kiểm tra arguments trước khi khởi tạo.
2. **Constructor return value validation:** kiểm tra đối tượng *đã được khởi tạo* theo các constraint/cascade khai báo trên constructor.
3. **Spring AOP method validation:** kiểm tra tham số và kết quả trả về của *method* khi lời gọi đi qua proxy được cấu hình phù hợp.

Mục tiêu là chọn đúng cơ chế, tránh nhầm constructor với method, thực hành đủ API chuẩn và hiểu ranh giới thời điểm có thể ngăn side effect.

## 2. So sánh nhanh API chuẩn và Spring AOP

| Khía cạnh | Jakarta Validation: `ExecutableValidator` cho constructor | Spring `MethodValidationPostProcessor` / AOP |
| --- | --- | --- |
| Đối tượng kiểm tra | `java.lang.reflect.Constructor<?>` cụ thể | `Method` được gọi qua Spring proxy |
| Giai đoạn trước | `validateConstructorParameters(constructor, args)` | Method parameter validation của interceptor |
| Giai đoạn sau | `validateConstructorReturnValue(constructor, createdObject)` | Method return value validation của interceptor |
| Ai kích hoạt? | Code ứng dụng/integration chủ động gọi API | Proxy Spring tự kích hoạt khi invocation đi qua nó |
| Có tự thực thi constructor/method? | **Không**: API chỉ kiểm tra giá trị được đưa vào | Proxy bao quanh lời gọi method thực, có thể từ chối trước/sau |
| Phụ thuộc Spring? | Không; thuộc Jakarta Validation, cần provider | Có, cần Spring bean/proxy và hạ tầng method validation |
| `new SomeClass(...)` thông thường? | Không tự được validate; cần gọi API riêng | Không được Spring AOP intercept |
| `@Validated` class level? | Không cần, không điều khiển hai API constructor | Thường là dấu hiệu chọn bean để áp method validation |
| Kết quả lỗi | `Set<ConstraintViolation<T>>`; code quyết định xử lý | Thường ném `ConstraintViolationException`, hoặc loại lỗi Spring đã adapt |
| Phạm vi sử dụng | Factory tự viết, testing, dynamic construction | Service/business methods, lời gọi qua bean proxy |

Một số container/framework khác có cơ chế tự động xác minh constructor, nhưng **đó là tính năng của integration cụ thể**. Đừng coi chúng là mặc định của JVM hoặc của Spring AOP proxy.

**Quy tắc then chốt:** `@Valid` trên một constructor **không tương đương** `@Validated` trên class. `@Valid` ở constructor đánh dấu *constructor return value* để provider có thể cascade vào đối tượng được tạo **khi API kiểm tra tương ứng được gọi**.

## 3. Hai API constructor của `ExecutableValidator`

Từ `jakarta.validation.Validator`, lấy:

```java
Validator validator = factory.getValidator();
ExecutableValidator executables = validator.forExecutables();
```

`ExecutableValidator` thuộc `jakarta.validation.executable`, là giao diện chuẩn của Jakarta Validation (Bean Validation), không phụ thuộc cách Spring tạo bean.

### 3.1. `validateConstructorParameters` — kiểm tra trước `new`

Chữ ký khái quát:

```java
<T> Set<ConstraintViolation<T>> validateConstructorParameters(
        Constructor<? extends T> constructor,
        Object[] parameterValues,
        Class<?>... groups);
```

Đầu vào:

- `constructor`: đối tượng reflection trỏ tới **đúng** constructor cần kiểm tra.
- `parameterValues`: mảng arguments có đủ số phần tử, đúng vị trí và kiểu; primitive như `int` được boxing thành `Integer` khi nằm trong `Object[]`.
- `groups`: những validation groups sẽ chạy; bỏ qua để dùng `Default`.

Provider kiểm tra constraint đặt trên từng parameter (`@NotBlank`, `@Min`, `@Valid`, v.v.) và constraint **cross-parameter** nếu có. Hàm **không chạy constructor**. Nếu vi phạm, trả về `Set` không rỗng; gọi tiếp hay dừng là quyết định của ứng dụng.

```java
Constructor<Booking> ctor =
        Booking.class.getConstructor(String.class, int.class);

Object[] args = {"", 0};

Set<ConstraintViolation<Booking>> problems =
        executables.validateConstructorParameters(ctor, args);
```

Đoạn trên minh họa cú pháp, cần `Booking` có constructor public nhận `String, int` và các import Jakarta Validation/reflection tương ứng. Bạn có thể dùng mảng kết quả để trả lỗi cho người gọi **trước khi** thực hiện bất kỳ thao tác nào trong constructor.

### 3.2. `validateConstructorReturnValue` — kiểm tra sau `new`

Chữ ký khái quát:

```java
<T> Set<ConstraintViolation<T>> validateConstructorReturnValue(
        Constructor<? extends T> constructor,
        T createdObject,
        Class<?>... groups);
```

`createdObject` phải là instance đã được tạo từ constructor tương ứng. Từ “return value” ở đây chỉ **đối tượng do constructor tạo ra**, dù Java constructor không khai báo kiểu trả về trong source.

Một cách phổ biến là đặt `@Valid` trên constructor:

```java
public class Booking {

    @NotBlank
    private final String code;

    @Valid
    public Booking(String code) {
        this.code = code;
    }
}
```

Khi gọi `executables.validateConstructorReturnValue(ctor, booking)`, provider thấy `@Valid` và cascade xuống các constraint trên `Booking.code`. Nếu bỏ `@Valid` khỏi constructor mà không có constraint return khác, việc kiểm tra constructor return **không tự động quét toàn bộ property**.

**Giới hạn quan trọng:** Vì `createdObject` đã tồn tại, kiểm tra return không thể “ngăn constructor chạy”. Nếu constructor đã ghi file, gửi request mạng hoặc thay đổi trạng thái chung, một violation hậu điều kiện không tự hoàn tác chúng. Do đó nên giữ constructor đơn giản, giới hạn side effect và kiểm tra tham số **trước** khi tạo object khi bạn quản lý được luồng khởi tạo.

## 4. Ví dụ Java 17 chạy độc lập: thấy chính xác các giai đoạn

Ví dụ hoàn chỉnh này dùng Java 17, Hibernate Validator 8.x và Jakarta Validation. Nó minh họa:

- Hai constraint tham số constructor.
- Hai constraint trên field của instance.
- `@Valid` trên constructor để bật cascaded validation sau khởi tạo.
- Kiểm tra bean thông thường để so sánh.
- Một method được validate bằng API thủ công, chứng minh cùng provider còn hỗ trợ method contracts.
- Một lời gọi `new` và method Java thuần vẫn chạy dù metadata có ràng buộc.

Cấu trúc:

```text
constructor-validation-demo/
├── pom.xml
└── src/main/java/demo/
    └── ConstructorVsAopDemo.java
```

### 4.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>constructor-validation-demo</artifactId>
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

Hibernate Validator là provider, Jakarta Validation API được kéo theo dưới dạng dependency. `expressly` cung cấp Jakarta Expression Language khi nội suy message. Đoạn ứng dụng này **không cần Spring** để chạy.

### 4.2. `ConstructorVsAopDemo.java`

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

public class ConstructorVsAopDemo {

    public static final class Booking {

        @NotBlank(message = "state.code.required")
        private final String code;

        @Min(value = 1, message = "state.seats.too.small")
        private final int seats;

        // Chỉ dùng cho minh họa thời điểm constructor chạy.
        private static int constructions = 0;

        // @Valid thuộc về CONTRACT của constructor return.
        @Valid
        public Booking(
                @NotBlank(message = "arg.code.required") String code,
                @Min(value = 1, message = "arg.seats.too.small")
                int seats) {
            constructions++;
            this.code = code;
            this.seats = seats;
        }

        public static int constructions() {
            return constructions;
        }
    }

    public static final class BookingService {

        @NotBlank(message = "method.result.blank")
        public String reserve(
                @NotBlank(message = "method.code.blank") String code) {
            return code;
        }
    }

    private static <T> void report(
            String label, Set<ConstraintViolation<T>> violations) {

        TreeSet<String> messages = new TreeSet<>();
        for (ConstraintViolation<T> v : violations) {
            messages.add(v.getMessage());
        }

        System.out.println(label + " -> " + messages);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            ExecutableValidator executable = validator.forExecutables();

            Constructor<Booking> constructor =
                    Booking.class.getConstructor(
                            String.class, int.class);

            Object[] invalidArgs = {"", 0};

            // PRE: không chạy constructor.
            report("ctor-params-invalid",
                    executable.validateConstructorParameters(
                            constructor, invalidArgs));

            System.out.println(
                    "constructions-before-new -> " +
                    Booking.constructions());

            // Lời gọi new Java thuần vẫn được thực thi.
            Booking invalid = new Booking("", 0);
            System.out.println(
                    "constructions-after-new -> " +
                    Booking.constructions());

            // POST: cascade nhờ @Valid trên constructor.
            report("ctor-return-invalid",
                    executable.validateConstructorReturnValue(
                            constructor, invalid));

            // So sánh với validation của bản thân bean.
            report("bean-invalid",
                    validator.validate(invalid));

            Object[] validArgs = {"BOOK-1", 2};
            report("ctor-params-valid",
                    executable.validateConstructorParameters(
                            constructor, validArgs));

            Booking valid = new Booking("BOOK-1", 2);
            report("ctor-return-valid",
                    executable.validateConstructorReturnValue(
                            constructor, valid));

            BookingService service = new BookingService();
            Method method = BookingService.class.getMethod(
                    "reserve", String.class);

            report("method-params-invalid",
                    executable.validateParameters(
                            service, method, new Object[] {""}));

            report("method-return-invalid",
                    executable.validateReturnValue(
                            service, method, ""));

            // Không có proxy hoặc interceptor nên vẫn gọi được.
            System.out.println(
                    "direct-method-return-empty -> " +
                    service.reserve("").isEmpty());
        }
    }
}
```

Chạy ở thư mục `constructor-validation-demo`, với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConstructorVsAopDemo
```

Những dòng chương trình in ra trên `stdout` (ngoại trừ log Maven/provider nếu có):

```text
ctor-params-invalid -> [arg.code.required, arg.seats.too.small]
constructions-before-new -> 0
constructions-after-new -> 1
ctor-return-invalid -> [state.code.required, state.seats.too.small]
bean-invalid -> [state.code.required, state.seats.too.small]
ctor-params-valid -> []
ctor-return-valid -> []
method-params-invalid -> [method.code.blank]
method-return-invalid -> [method.result.blank]
direct-method-return-empty -> true
```

**Lý giải:**

1. `validateConstructorParameters(...)` thấy cả code rỗng và seats bằng 0 nên trả hai violations, nhưng `constructions` vẫn bằng 0. API không tạo instance.
2. `new Booking("", 0)` chạy constructor và tăng bộ đếm thành 1, dù cùng dữ liệu ấy vi phạm hợp đồng tham số. Không có tự động chặn lời gọi `new`.
3. `@Valid` trên constructor làm `validateConstructorReturnValue(...)` cascade vào đối tượng mới và phát hiện hai field sai. Điều này không sửa instance hay hoàn tác bộ đếm.
4. `validator.validate(invalid)` cũng phát hiện hai field sai, nhưng đó là **bean validation độc lập**, không kiểm tra các annotation `@NotBlank`/`@Min` đặt trên constructor parameters.
5. Trường hợp hợp lệ không có violations. Vì `report(...)` sắp xếp message bằng `TreeSet`, stdout có thứ tự xác định.
6. Với `BookingService`, API method validation phát hiện parameter/return sai khi **được gọi trực tiếp**. Nhưng lời gọi `service.reserve("")` vẫn trả một chuỗi rỗng vì chương trình không có Spring proxy.

Ví dụ dùng dữ liệu rỗng để minh họa. Trong ứng dụng thật, đừng cố tạo object sai **sau khi** bạn đã biết `validateConstructorParameters` thất bại; hãy dừng tại bước precondition.

## 5. Cách thực thi một factory kiểm tra constructor đúng thứ tự

Muốn biến contract thành một hàng rào thực sự, gom hai lần gọi validation quanh việc tạo instance. Đây là phần **minh họa bổ sung** dùng các lớp `Booking` từ ví dụ 4, có thể đặt ở một lớp factory riêng trong ứng dụng:

```java
public final class BookingFactory {

    private final ExecutableValidator executable;

    public BookingFactory(Validator validator) {
        this.executable = validator.forExecutables();
    }

    public Booking create(String code, int seats)
            throws NoSuchMethodException {

        Constructor<Booking> constructor =
                Booking.class.getConstructor(String.class, int.class);
        Object[] inputs = {code, seats};

        var inputErrors =
                executable.validateConstructorParameters(
                        constructor, inputs);

        if (!inputErrors.isEmpty()) {
            throw new ConstraintViolationException(inputErrors);
        }

        // Chỉ chạy khi precondition đã hợp lệ.
        Booking result = new Booking(code, seats);

        var resultErrors =
                executable.validateConstructorReturnValue(
                        constructor, result);

        if (!resultErrors.isEmpty()) {
            throw new ConstraintViolationException(resultErrors);
        }

        return result;
    }
}
```

Để ghép đoạn này thành code biên dịch trong một file riêng, cần import `jakarta.validation.Validator`, `ConstraintViolationException`, `jakarta.validation.executable.ExecutableValidator`, `java.lang.reflect.Constructor` và dùng tên đầy đủ `ConstructorVsAopDemo.Booking` cho kiểu `Booking`. Đây không phải class được tự động Spring tạo; ứng dụng phải chủ động sử dụng factory này thay `new` rải rác.

Các quyết định thiết kế quan trọng:
- **Chỉ dùng một bộ arguments thực tế.** Nếu đã validate `inputs` nhưng lại thay dữ liệu trước khi gọi constructor, kết quả preflight không còn bảo vệ lời gọi ấy.
- Nếu constructor có side effect, postcondition validation chỉ báo lỗi **sau khi side effect xảy ra**. Tránh ghi DB hoặc phát sự kiện trong constructor; thực thi side effect sau khi cả hai giai đoạn đạt, hoặc có giao dịch/bù trừ phù hợp.
- Có thể giữ `ValidatorFactory` làm singleton do Spring quản lý và chia sẻ `Validator`/`ExecutableValidator` vì API được thiết kế cho việc dùng lặp lại. Tránh dựng một factory mới mỗi request.
- Lớp ứng dụng có thể chuyển violations thành exception hoặc danh sách lỗi có cấu trúc. Chỉ **gọi API** thì chưa đồng nghĩa exception sẽ xuất hiện.

## 6. Spring AOP method validation thực sự chặn cái gì?

### 6.1. Một service được `@Validated`

Trong ứng dụng Spring Boot 3.x đã cấu hình Jakarta Validation và AOP, thường có cấu hình dependency tương tự:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Đây là đoạn `build.gradle` minh họa trong một dự án Spring Boot đã có plugin và repositories; không thể chạy độc lập như `pom.xml` của mục 4.

Một bean:

```java
@Service
@Validated
public class BookingService {

    @NotNull
    public Booking book(
            @NotBlank String code,
            @Min(1) int seats) {
        return new Booking(code, seats);
    }
}
```

Giả sử `Booking` là lớp như ví dụ 4 và các import Spring/Jakarta đã có. `MethodValidationPostProcessor` thiết lập interceptor cho Spring bean có `@Validated`. Khi một bean khác nhận **proxy** và gọi `bookingService.book("", 0)`, interceptor có thể kiểm tra parameters của **method `book`** trước khi body method chạy, sau đó kiểm tra constraint của **method return value**.

Điều cần chú ý: interceptor kiểm tra **hợp đồng method** do Spring proxy nhận được, không tự gọi `validateConstructorParameters` cho `new Booking(code, seats)` bên trong. Ở ví dụ trên, ta đặt `@NotBlank`/`@Min` ngay trên **method parameters**, nên proxy có thể bắt vi phạm **trước khi** chạy body tạo object.

Nếu thay method thành:

```java
public Booking book(String code, int seats) {
    return new Booking(code, seats);
}
```

và chỉ giữ `@NotBlank`/`@Min` trên **constructor** của `Booking`, Spring AOP không tự biết phải validate constructor arguments; lời gọi `new Booking("", 0)` bên trong vẫn chạy.

### 6.2. Vì sao proxy không thể thay constructor interception?

Spring AOP hỗ trợ **method-execution join points**. Nó có thể sử dụng JDK dynamic proxy trên interface hoặc CGLIB subclass proxy tùy target bean; cả hai xoay quanh invocation của các method qua proxy. Constructor là thao tác **khởi tạo đối tượng**, không phải method invocation qua proxy của một instance đã có.

Do đó:
- `@Validated` đặt trên class chỉ đánh dấu mục tiêu method validation cho Spring, không biến constructor thành method.
- `@Valid` đặt trên constructor chỉ có hiệu lực khi một API/integration kiểm tra constructor return được gọi.
- Dù dùng CGLIB subclass proxy, **không được suy ra** advice của Spring AOP sẽ tự kiểm tra constructor arguments.
- Lời gọi trực tiếp `new`, một factory dùng `new` và Spring tự tạo bean qua constructor injection đều **không tự động** được `MethodValidationPostProcessor` kiểm tra constructor contract.
- `@PostConstruct` hay các lifecycle callbacks không biến thành bước constructor prevalidation. Bean validation ở giai đoạn sau khởi tạo (nếu có hạ tầng riêng) cũng không phải việc kiểm tra *constructor parameters trước khi new*.

Nếu một dự án sử dụng **AspectJ weaving** với constructor joinpoints, hoặc **CDI/Jakarta EE** tích hợp executable validation, đó là cơ chế khác có thể đáp ứng thêm ngữ cảnh. Không dùng khả năng ấy để suy luận về Spring AOP proxy thông thường.

### 6.3. Các giới hạn của proxy dễ gây bỏ sót method validation

Ngay cả với **method**, cần lưu ý:
- Bean phải được Spring quản lý và lời gọi phải **đi qua proxy**.
- `this.book(...)` trong chính target bean thường bỏ qua proxy (*self-invocation*).
- Với JDK dynamic proxy, lời gọi đi qua interface; với CGLIB, các method `final`/`private` không được override/advice như public method thích hợp.
- Validation groups có thể được quyết định bởi `@Validated(Group.class)`. Chỉ có `@Valid` không đồng nghĩa mọi group được chạy.
- Đặt constraint trên method declaration nhưng tạo object bằng `new SomeService()` ngoài container sẽ không có interceptor.

Kiểm thử cần gọi từ bean khác qua container thật nếu muốn chứng minh Spring đang enforce method contract.

## 7. Có thể thay constructor API bằng một factory method được proxy không?

Có thể thiết kế **một public factory method** để Spring validate *hợp đồng của method* trước và sau khi xây dựng đối tượng. Ví dụ minh họa:

```java
@Service
@Validated
public class BookingFactoryService {

    @Valid // Cascade vào các property của Booking trả về.
    public Booking create(
            @NotBlank String code,
            @Min(1) int seats) {

        return new Booking(code, seats);
    }
}
```

Khi một bean khác gọi `create(...)` qua proxy:
1. Interceptor validate **method parameters** (`code` và `seats`) trước khi vào body.
2. Nếu hợp lệ, body thực thi constructor.
3. Khi method trả về, `@Valid` trên **method** cho phép cascade để kiểm tra object trả về.

Hành vi này giúp bảo vệ một **đường tạo object có kiểm soát**, nhưng vẫn có những khác biệt:
- Ràng buộc kiểm tra ở đầu vào là **annotations trên factory method**, không tự động kế thừa annotation trên constructor parameters.
- Cascaded return là **hợp đồng của factory method**, không phải invocation của `validateConstructorReturnValue`.
- Mọi chỗ tạo object ngoài factory có thể bỏ qua cơ chế trên.
- Constructor đã chạy trước khi provider kiểm tra method return, nên side effect trong constructor vẫn có thể xảy ra.
- Không có `@Valid` trên method return thì proxy không tự quét field của `Booking` chỉ nhờ field có constraint.

Nếu yêu cầu là **thi hành đúng annotation khai báo ở constructor** mà không sao chép hợp đồng sang method, hãy dùng `ExecutableValidator`/một integration chủ động kiểm tra constructor đúng chữ ký.

## 8. Spring constructor injection không phải constructor validation

Trong Spring, các thuật ngữ "constructor injection" và "constructor validation" dễ bị trộn:

```java
@Service
public class PaymentService {

    private final GatewayClient gateway;

    public PaymentService(GatewayClient gateway) {
        this.gateway = gateway;
    }
}
```

Spring IoC **resolve dependency** `GatewayClient`, gọi constructor và quản lý vòng đời bean. Đó là công việc **dependency injection**, không phải lệnh gọi `ExecutableValidator.validateConstructorParameters`.

Nếu thêm:

```java
public PaymentService(@NotNull GatewayClient gateway) {
    this.gateway = gateway;
}
```

thì `@NotNull` là metadata Jakarta Validation trên parameter. Nó không khiến Spring AOP proxy thường dùng chặn constructor. Spring có thể thất bại lúc tạo bean nếu **không resolve được dependency** hoặc gặp lỗi của constructor; trường hợp ấy khác với việc `@NotNull` được một provider đánh giá.

Tương tự, `@ConfigurationProperties` của Spring Boot có thể được bind và validate bằng một con đường riêng (tùy version/cấu hình). Không nên coi validation của configuration property hoặc `@Valid` trên DTO là bằng chứng rằng mọi custom constructor trong ứng dụng đều tự được kiểm tra.

## 9. Khác biệt với `Validator.validate(bean)` và bean lifecycle validation

Giả sử `Booking` có:
- `@NotBlank` trên constructor parameter `code` với message `arg.code.required`.
- `@NotBlank` trên field `code` với message `state.code.required`.
- `@Valid` trên constructor để cascade instance.

Kết quả của các cách gọi:

| Lời gọi | Phạm vi validation |
| --- | --- |
| `validator.validate(booking)` | Field/getter/class constraints của **booking** |
| `executables.validateConstructorParameters(ctor, args)` | Parameter và cross-parameter constraints của **ctor** |
| `executables.validateConstructorReturnValue(ctor, booking)` | Constraint/cascade trên **constructor return**, có thể dẫn vào fields |
| `executables.validateParameters(service, method, args)` | Tham số của method cụ thể |
| `executables.validateReturnValue(service, method, result)` | Constraint/cascade trên return của method cụ thể |
| Spring AOP method validation | Tương đương ý nghĩa kiểm tra method, thực hiện tại invocation qua proxy |

`Validator.validate(bean)` không nhận được mảng arguments đã dùng trước khi khởi tạo và không thể kiểm tra hợp đồng **constructor parameter** chỉ dựa vào state hiện tại. Hai giá trị input khác nhau có thể dẫn đến một state giống nhau; ngược lại, constructor có thể biến đổi input thành state khác. Đó là lý do giữ hai tầng metadata riêng.

Một số ứng dụng có thể dùng `BeanValidationPostProcessor`, custom `BeanPostProcessor` hoặc init hook để xác minh *bean state sau khi Spring tạo object*. Tuy vậy, các bước ấy xảy ra **sau constructor**, không phải interceptor mặc định cho constructor arguments. Đừng dùng chúng để hứa rằng một constructor không hợp lệ sẽ không có side effect.

## 10. Khi nào cần kiểm tra constructor return?

Nếu constructor đảm bảo lưu state đúng như arguments đã được validate, có thể constructor parameter validation là đủ trong nhiều tình huống. Nhưng constructor return validation vẫn có giá trị khi:

- Có bất biến trên **đối tượng hoàn chỉnh**, ví dụ nhiều fields tương quan nhau.
- Constructor biến đổi, chuẩn hóa hoặc chọn giá trị mặc định và có nguy cơ tạo state sai.
- Có class-level constraint kiểm tra mối quan hệ giữa các property.
- Cần validate state của child object thông qua cascade đã được khai báo trên object.
- Một factory cần thực thi **precondition và postcondition** như hai hợp đồng độc lập.

Ví dụ một constraint cấp class (đoạn ý tưởng, chưa phải annotation đầy đủ):

```java
@ConsistentBooking
public class Booking {
    // code, startDate, endDate, ...
}
```

Với constructor được đánh dấu `@Valid`, `validateConstructorReturnValue` có thể cascade và đánh giá `@ConsistentBooking` trên đối tượng sau khi đã khởi tạo. `@ConsistentBooking` ở đây giả định là constraint tự định nghĩa có `ConstraintValidator` tương ứng.

**Tối ưu thiết kế:** Cố gắng để constructor không gây side effect (đặc biệt với immutable object/record). Khi hậu điều kiện thất bại, có thể loại bỏ object thay vì phải hoàn tác I/O.

## 11. Cross-parameter và groups trong constructor validation

Một constructor có thể có ràng buộc **giữa nhiều tham số**, không diễn tả được bằng `@NotNull` của từng tham số. Ví dụ constructor nhận `start`, `end` và yêu cầu `start <= end`.

Annotation minh họa:

```java
@ValidDateRange
public Schedule(LocalDate start, LocalDate end) {
    // ...
}
```

`@ValidDateRange` giả định là custom cross-parameter constraint, với validator nhận `Object[]` và được đánh dấu:

```java
@SupportedValidationTarget(ValidationTarget.PARAMETERS)
public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, Object[]> {

    @Override
    public boolean isValid(
            Object[] args, ConstraintValidatorContext ctx) {
        if (args == null || args.length != 2) {
            return false;
        }

        LocalDate start = (LocalDate) args[0];
        LocalDate end = (LocalDate) args[1];
        return start == null || end == null || !start.isAfter(end);
    }
}
```

Đây là các đoạn minh họa **chưa hoàn chỉnh để biên dịch riêng**: cần annotation `@ValidDateRange` được khai báo với target constructor, các import `java.time.LocalDate`, `jakarta.validation.*` và `jakarta.validation.constraintvalidation.*`. Khi gọi `validateConstructorParameters`, provider sẽ xét cả các cross-parameter constraints hợp lệ này.

Cả hai API constructor nhận `groups`. Ví dụ:

```java
public interface StrictCheck {}

public Schedule(
        @NotNull LocalDate start,
        @Future(groups = StrictCheck.class) LocalDate end) {
    // ...
}
```

Theo mặc định, `validateConstructorParameters(ctor, args)` kiểm tra nhóm `Default`. Để chạy constraint thuộc `StrictCheck`, truyền `StrictCheck.class`. Để kiểm tra cả hai:

```java
executables.validateConstructorParameters(
        ctor, args,
        jakarta.validation.groups.Default.class,
        StrictCheck.class);
```

Các đoạn trên chỉ minh họa cách chọn group. Không nhầm `@Validated(StrictCheck.class)` trên Spring bean với đối số groups của API constructor: cái thứ nhất thuộc cơ chế Spring method validation, cái thứ hai do **người gọi constructor API** lựa chọn.

## 12. Reflection, records và constructor overload

### 12.1. Lấy đúng chữ ký

`getConstructor` tìm **constructor public** với danh sách tham số đúng kiểu:

```java
Constructor<Booking> ctor =
        Booking.class.getConstructor(String.class, int.class);
```

Nếu lớp có cả `Booking(String, int)` và `Booking(String, long)`, đây là hai constructor khác nhau. Dữ liệu truyền `Object[]` phải khớp đúng số lượng, thứ tự và kiểu với constructor được chọn. Với `int`, giá trị trong mảng là boxed `Integer`.

Với constructor không tham số, truyền `new Object[0]`. **Không** dùng mảng `null` thay cho mảng rỗng: đó là dữ liệu API không hợp lệ. Một phần tử của mảng có thể là `null` nếu kiểu tương ứng cho phép; constraint `@NotNull` sẽ xét trường hợp ấy.

### 12.2. Constructor visibility

Nếu constructor không public, `Class.getDeclaredConstructor(...)` có thể trả về đối tượng reflection cho constructor đó. Việc **gọi** constructor bằng reflection có thể cần quyền truy cập phù hợp. Tuy nhiên, API `validateConstructorParameters` chỉ cần descriptor, không nhất thiết phải gọi constructor bằng `newInstance`; việc dùng `new` thông thường sau preflight là hợp lệ khi source có quyền truy cập.

### 12.3. Java record

Ví dụ với record:

```java
public record Account(
        @NotBlank String code,
        @Min(1) int level) {}
```

Các constraint khai báo trên record components có thể được Java nhân bản lên những phần tử tương ứng (field, accessor hoặc constructor parameter tùy `@Target` của annotation). Với `@NotBlank` và `@Min`, constructor parameter metadata của canonical constructor có thể được khai báo tương ứng. **Nhưng không nên suy ra** `new Account("", 0)` tự chạy Bean Validation; record construction vẫn cần integration nếu muốn chặn đầu vào.

Cần test chính xác bytecode/metadata của kiểu record và version compiler/provider khi phụ thuộc sự nhân bản annotation. Với business rule bắt buộc của record, một compact constructor có `if`/`throw` là **logic Java trực tiếp** chạy khi tạo, khác với annotation được Jakarta Validation provider kiểm tra.

## 13. API không tự ném lỗi validation

Một vi phạm hợp lệ được báo bằng tập `ConstraintViolation`:

```java
var problems =
        executables.validateConstructorParameters(
                constructor, new Object[] {"", 0});

if (!problems.isEmpty()) {
    throw new ConstraintViolationException(problems);
}
```

Đây là đoạn bổ sung cho ví dụ 4; cần import `jakarta.validation.ConstraintViolationException`. Đó là **quyết định của caller**, không phải hành vi tự động của phương thức `validateConstructorParameters`.

| Trường hợp | Điều có thể xảy ra |
| --- | --- |
| Arguments vi phạm `@NotBlank`/`@Min` | API trả về một `Set<ConstraintViolation<?>>` không rỗng |
| Caller tự throw khi `Set` không rỗng | `ConstraintViolationException` |
| `constructor` hoặc `createdObject` không tương ứng; mảng arguments sai kiểu/số lượng | `IllegalArgumentException` |
| Constraint/provider cấu hình sai | `ValidationException` hoặc subtype cụ thể |
| Invocation qua Spring method validation proxy vi phạm | `ConstraintViolationException` hoặc exception đã adapt, tùy cấu hình |
| Spring thiếu dependency bean trong constructor injection | Lỗi khởi tạo bean của Spring, **không** nhất thiết là violation từ Jakarta Validation |

Từng `ConstraintViolation` chứa path, message, invalid value, constraint descriptor. Với constructor, property path bắt đầu ở node `CONSTRUCTOR`; lỗi parameter đi qua node `PARAMETER`, lỗi postcondition đi qua `RETURN_VALUE` rồi có thể đến `PROPERTY` nhờ cascade. `getRootBean()` của constructor violation là `null` theo đặc tả; `getRootBeanClass()` là class khai báo constructor. Đây là một khác biệt với việc validate method của một object sẵn có.

Không dựa vào thứ tự trong `Set`. Nếu cần trả lỗi API ổn định, sắp xếp theo path/message; không tự động trả `getInvalidValue()` ra HTTP response vì có thể chứa dữ liệu riêng tư.

## 14. Tự kiểm tra: chọn kỹ thuật cho từng tình huống

| Yêu cầu | Cách phù hợp | Lý do |
| --- | --- | --- |
| Chặn arguments sai **trước khi** tạo object bằng constructor có constraint | `ExecutableValidator.validateConstructorParameters` trong factory có kiểm soát | Kiểm tra đúng metadata constructor và có thể dừng trước `new` |
| Kiểm tra bất biến của object **sau khi** khởi tạo theo metadata constructor | `validateConstructorReturnValue`, thường cùng `@Valid` | Có createdObject để cascade/state check |
| Kiểm tra state hiện có của bean bất kỳ | `Validator.validate(bean)` | Không cần biết constructor đã gọi với arguments nào |
| Enforce input/output của public Spring service method | `@Validated` và method validation proxy | Interceptor bao quanh method invocation |
| Chặn input của một factory method Spring trước khi body chạy | Constraint trực tiếp trên method parameters + proxy | Method contract được validate trước `new` bên trong body |
| Validate một DTO được Spring MVC nhận qua HTTP | `@Valid`/`@Validated` trên controller argument và provider thích hợp | Đây là request binding/validation, khác constructor interception |
| Tự động intercept **mọi** constructor của các object Java bất kỳ | Cơ chế ngoài phạm vi Spring AOP proxy, cần thiết kế/integration khác | Không có join point constructor trong Spring AOP |
| Cần kiểm tra **vừa method vừa constructor** trong framework riêng | Dùng các method tương ứng của `ExecutableValidator` | API chuẩn cung cấp cả hai loại executable |

Đặc biệt, một ứng dụng Spring Boot có thể chứa đồng thời:
- Bean được tạo qua constructor injection.
- Service được method validation qua `@Validated`.
- DTO được validate khi binding HTTP.
- Object được tạo bằng `new` trong service.

Bốn con đường này **không đồng nghĩa** mọi constructor argument đã được một bộ kiểm tra chung xác minh. Xác định rõ **ranh giới nào** chịu trách nhiệm bảo vệ invariant.

## 15. Lỗi thường gặp và cách sửa

1. **Gắn `@NotBlank` ở constructor rồi tin Spring `@Validated` sẽ bắt khi tạo bean.** Spring AOP proxy chỉ bao quanh method invocation. Muốn kiểm tra constructor metadata, dùng API chuẩn trong một factory hoặc tích hợp chuyên biệt.
2. **Chỉ gọi `Validator.validate(createdObject)` và cho rằng constructor parameters đã được kiểm tra.** API bean validation chỉ biết state hiện tại, không có mảng arguments ban đầu. Dùng `validateConstructorParameters` nếu hợp đồng ở constructor parameters quan trọng.
3. **Gọi `validateConstructorReturnValue` trước khi `new`.** API cần `createdObject` đã được tạo; thứ tự đúng là preflight → new → hậu kiểm.
4. **Dùng `@Valid` trên constructor nhưng không gọi API nào.** Metadata không tự chặn Java constructor. Cần explicit validation/integration.
5. **Dùng method factory có proxy nhưng chỉ đặt constraints trong constructor.** Interceptor method sẽ không tự chuyển metadata từ constructor vào method. Khai báo hợp đồng của factory method hoặc gọi constructor API tường minh.
6. **Dùng method factory có return `@Valid` và nghĩ có thể rollback constructor.** Return validation chạy sau body; không thể tự khôi phục side effect đã xảy ra.
7. **Dựa vào self-invocation của một `@Validated` bean.** `this.someMethod(...)` có thể bỏ qua proxy. Gọi qua Spring bean proxy từ bean khác hoặc tổ chức khác đường đi.
8. **Không ghi đúng `Method`/`Constructor` reflection khi overload.** Khác kiểu primitive/wrapper hoặc thứ tự sẽ tạo mismatch. Dùng chữ ký chính xác và test.
9. **Khẳng định Spring Boot luôn ném `ConstraintViolationException` với mọi kiểu validation.** MVC có loại lỗi riêng; `MethodValidationPostProcessor` còn có chế độ adapt. Xác minh nhánh thực thi và cấu hình.
10. **Dùng cùng một constraint nhưng vô tình kiểm tra hai lần.** Nếu một method factory đã được proxy validate, lại gọi `ExecutableValidator.validateParameters` cho cùng method thì có thể vừa tốn chi phí vừa báo lỗi lặp. Chọn một điểm enforcement chủ động.

## 16. Bài tập thực hành

1. Với ví dụ 4, bỏ `@Valid` khỏi constructor `Booking` rồi chạy lại hai lệnh `validateConstructorReturnValue` và `validator.validate(invalid)`. Vì sao kết quả có thể khác nhau?
2. Thay `new Booking("", 0)` bằng một factory kiểm tra `validateConstructorParameters` trước. In lại bộ đếm và chứng minh constructor không chạy trong nhánh input sai.
3. Sửa constructor thành một phiên bản có bug: input hợp lệ nhưng lưu `seats = 0`. Chứng minh parameter validation có thể pass còn return validation phát hiện state sai.
4. Tạo một Spring `@Service @Validated` với method `book(@NotBlank String, @Min(1) int)` và gọi từ bean khác qua proxy. Sau đó đặt duy nhất ràng buộc trên constructor của `Booking` và kiểm chứng khác biệt.
5. Viết test với record có constraint trên component; quan sát `getConstraintsForConstructor(...)` và thử gọi `validateConstructorParameters` với instance dữ liệu sai trước khi `new`.
6. Giải thích vì sao bean constructor injection được Spring quản lý nhưng không đủ chứng minh `ExecutableValidator.validateConstructorParameters` đã từng chạy.
7. Mở rộng factory để chuyển violations thành exception hoặc object lỗi có field `path`, `message`, `code`; không lộ toàn bộ dữ liệu `getInvalidValue()`.

**Ghi nhớ:** Jakarta Validation **định nghĩa** các constraint và cung cấp `ExecutableValidator` để chủ động kiểm tra constructor. Spring AOP **thực thi tự động** method contracts trên lời gọi qua proxy. Muốn constructor contract được enforce, bạn phải đặt một bước kiểm tra đúng chỗ — trước khi gọi constructor, hoặc sau khi có object tùy hợp đồng — và kiểm soát chính các đường khởi tạo.

## Tài liệu chuẩn

- [Jakarta Validation 3.1 Specification — Method and constructor constraints](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#constraintdeclarationvalidationprocess-methodlevelconstraints)
- [Jakarta Validation 3.1 Specification — ExecutableValidator](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#validationapi-triggeringmethodvalidation)
- [Jakarta Validation API — ExecutableValidator](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta.validation/jakarta/validation/executable/ExecutableValidator.html)
- [Hibernate Validator 8 — Method and constructor constraints](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#section-method-constraints)
- [Spring Framework — AOP proxying mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Spring-driven method validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation of handler methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)