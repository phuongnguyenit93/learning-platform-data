# ParameterNameProvider và tên tham số trong kết quả Jakarta Bean Validation

## Mục tiêu

Khi một ràng buộc đặt trên tham số phương thức hoặc constructor bị vi phạm, người đọc kết quả cần biết **tham số nào sai**. Bài này giải thích hạ tầng `jakarta.validation.ParameterNameProvider`, nơi tên tham số xuất hiện trong `ConstraintViolation.getPropertyPath()`, sự khác nhau giữa tên thực và `arg0`/`arg1`, cách cấu hình provider riêng, và mối quan hệ với Spring Framework.

Sau bài học, bạn có thể:

- Mô tả chính xác hai phương thức của `ParameterNameProvider` và điều kiện thread-safe.
- Giải thích vì sao biên dịch Java với `-parameters` ảnh hưởng đến tên trong violation.
- Đọc `Path.ParameterNode.getName()` và `getParameterIndex()` mà không phải phân tích chuỗi path bằng tay.
- Viết một custom provider có fallback an toàn, cấu hình nó khi tạo `ValidatorFactory` và quan sát kết quả trên method lẫn constructor.
- Phân biệt tên tham số của Jakarta Validation với tên HTTP parameter, tên thuộc tính DTO và cơ chế khám phá tên tham số của Spring.

## 1. Vấn đề: lỗi ở tham số nào?

Giả sử có phương thức:

~~~java
public void reserve(@NotBlank String customerId, @Min(1) int seats) {
    // Business logic
}
~~~

Nếu lời gọi dự kiến có `customerId = ""` và `seats = 0`, cả hai tham số đều vi phạm constraint. Bean Validation có thể tạo hai `ConstraintViolation`, mỗi lỗi chứa một `Path` dẫn đến vị trí lỗi.

Hai cách hiển thị có thể gặp:

~~~text
reserve.customerId
reserve.seats
~~~

hoặc, nếu thông tin tên thực không có trong bytecode:

~~~text
reserve.arg0
reserve.arg1
~~~

Ở đây `arg0` và `arg1` là tên tổng hợp theo **vị trí tham số, bắt đầu từ 0**. Tên trên path được cung cấp bởi `ParameterNameProvider`. Constraint `@NotBlank`/`@Min` và giá trị được kiểm tra vẫn như cũ; chỉ phần nhận diện tên trong kết quả thay đổi.

**Điều kiện tiên quyết:** method/constructor validation đã được kích hoạt. Việc chỉ đặt `@NotBlank` lên tham số rồi gọi một method Java trực tiếp **không tự động gọi** Bean Validation. Ở Java SE ta dùng `ExecutableValidator`; trong Spring có thể dùng tích hợp method validation phù hợp.

## 2. API của ParameterNameProvider

Giao diện Jakarta Validation:

~~~java
package jakarta.validation;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.List;

public interface ParameterNameProvider {
    List<String> getParameterNames(Constructor<?> constructor);
    List<String> getParameterNames(Method method);
}
~~~

Hai overload đều nhận một đối tượng reflection mô tả executable và trả danh sách tên theo **đúng thứ tự khai báo**:

| Phương thức | Đối tượng đầu vào | Kết quả với hai tham số |
| --- | --- | --- |
| `getParameterNames(Method)` | Method được validation engine xử lý | `["customerId", "seats"]` |
| `getParameterNames(Constructor<?>)` | Constructor được validation engine xử lý | `["customerId", "seats"]` |

Hợp đồng cần tuân theo:

1. Danh sách tên phải ứng với **số lượng và thứ tự** tham số của executable. Với executable không có tham số, trả danh sách rỗng. Không trả `null`.
2. Mỗi vị trí phải có tên hợp lệ; không đổi thứ tự hoặc bỏ qua một tham số vì nó không có annotation.
3. Implementation phải **thread-safe**: provider/validator có thể gọi lặp lại hoặc đồng thời từ nhiều luồng.
4. Nên giữ kết quả ổn định cho cùng một `Method`/`Constructor`, không phụ thuộc request hoặc dữ liệu người dùng.
5. Khi không có quy tắc đặt tên riêng, **ủy quyền provider mặc định** thay vì tự đoán tên cho mọi executable.

Tên trả về là tên phục vụ cho báo cáo vi phạm. `ParameterNameProvider` **không** đổi tên tham số trong bytecode, tên trong chữ ký Java, tên field của DTO hay giá trị truyền vào phương thức.

### Phạm vi tác động

- **Có tác động:** `ElementKind.PARAMETER` trong `ConstraintViolation.getPropertyPath()` khi validation constraint trên method/constructor parameter.
- **Không đổi:** tên method, tên constructor, chỉ số tham số, thuộc tính bean trong field/property validation, hay node `<return value>` của return-value constraint.
- **Khác vấn đề:** metadata tham số trong Spring MVC request binding và tên khóa trong JSON request.

Ví dụ, `@NotBlank` trên `reserve(String customerId, ...)` tạo một parameter node; `@NotBlank` trên field `OrderRequest.customerId` tạo một property node. Provider của bài này giải quyết trường hợp **parameter node**.

## 3. Provider mặc định lấy tên từ đâu?

Theo Jakarta Validation, implementation mặc định phải tương thích hành vi Java reflection: lấy `Executable.getParameters()` và `Parameter.getName()`. Với class file có thông tin tên tham số, kết quả là tên đã khai báo; khi thiếu thông tin, Java reflection trả tên tổng hợp `arg0`, `arg1`,...

Java compiler flag:

~~~bash
javac -parameters -d out Example.java
~~~

Flag `-parameters` đưa metadata tên tham số vào class file để Java reflection đọc được. Cờ `-g` hỗ trợ debug information **không phải** cam kết tương đương với `-parameters` cho Java reflection. Trong Maven/Gradle, phải bảo đảm cấu hình compiler được áp dụng cho **module chứa method/constructor cần validate**, không chỉ cho module gọi nó.

Có thể tự kiểm tra metadata bằng Java reflection:

~~~java
for (java.lang.reflect.Parameter p : method.getParameters()) {
    System.out.println(p.getName() + " | present=" + p.isNamePresent());
}
~~~

Với `-parameters` và method có `customerId`, `seats`, kết quả là:

~~~text
customerId | present=true
seats | present=true
~~~

Nếu class được biên dịch lại **không có** metadata này, Java reflection điển hình trả:

~~~text
arg0 | present=false
arg1 | present=false
~~~

`isNamePresent()` giúp phân biệt tên thực được compiler lưu với tên tổng hợp. Tên Java dùng trong source code không tự động hiện diện trong bytecode; cần nhìn vào **artifact đã biên dịch thực tế**, nhất là khi dùng dependency ngoài.

Một số framework/provider có nguồn tên thay thế (ví dụ metadata/annotation hoặc công cụ đọc bytecode chuyên biệt), nhưng **hành vi portable mặc định** là reflection. Muốn tên khác reflection, bạn có thể cấu hình `ParameterNameProvider` riêng.

## 4. Tên được ghi vào ConstraintViolation như thế nào?

Khi validation method parameter thất bại, path chứa các node có loại (`ElementKind`) tương ứng. Với ví dụ `reserve`, đường đi điển hình:

~~~text
MethodNode(name="reserve")
    -> ParameterNode(name="customerId", index=0)
~~~

Khi thiếu tên thật, `ParameterNode.name` có thể thành `arg0` trong khi `index=0` **không đổi**.

Những API quan trọng:

~~~java
ConstraintViolation<?> violation = /* lỗi do validation trả về */;
Path path = violation.getPropertyPath();

for (Path.Node node : path) {
    if (node.getKind() == ElementKind.PARAMETER) {
        Path.ParameterNode parameter =
                node.as(Path.ParameterNode.class);
        String name = parameter.getName();
        int index = parameter.getParameterIndex();
        // name: "customerId" (hoặc "arg0")
        // index: 0
    }
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. Khi cần code có thể dùng làm máy, hãy dựa vào `ElementKind.PARAMETER` và `getParameterIndex()`. `Path.toString()` hữu ích để log/debug, nhưng Jakarta Validation xác định đây là biểu diễn đọc được; ứng dụng không nên phụ thuộc format chuỗi chính xác của nó để trích tên bằng `split(".")`.

Ngoài tên/index, violation còn có `getMessage()`, `getMessageTemplate()`, `getInvalidValue()`, `getConstraintDescriptor()`. Provider đổi tên **trên path**; nó không tự thay đổi nội dung `message` hoặc ngôn ngữ thông điệp, trừ khi một tầng hiển thị chủ động kết hợp path với thông điệp.

## 5. Ví dụ Java 17+: default provider và custom provider

Ví dụ dưới đây minh họa cả hai overload của `ParameterNameProvider`, phân biệt tên mặc định với tên tùy biến, và kiểm tra các lỗi method/constructor qua API Jakarta Validation. Không cần chạy Spring container để kiểm chứng.

Ta có một file Java: `src/main/java/com/example/validation/Demo.java`.

~~~java
package com.example.validation;

import jakarta.validation.Configuration;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ElementKind;
import jakarta.validation.ParameterNameProvider;
import jakarta.validation.Path;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Collectors;

public final class Demo {

    public static final class BookingService {
        public void reserve(
                @NotBlank String customerId,
                @Min(1) int seats) {
            // No invocation is needed for this validation demo.
        }
    }

    public static final class BookingRequest {
        public BookingRequest(
                @NotBlank String customerId,
                @Min(1) int seats) {
            // Constructor parameters carry the constraints.
        }
    }

    // An immutable, thread-safe wrapper around the standard provider.
    public static final class FriendlyParameterNames
            implements ParameterNameProvider {

        private final ParameterNameProvider delegate;

        public FriendlyParameterNames(ParameterNameProvider delegate) {
            this.delegate = delegate;
        }

        @Override
        public List<String> getParameterNames(Method method) {
            if (method.getDeclaringClass() == BookingService.class
                    && method.getName().equals("reserve")
                    && method.getParameterCount() == 2) {
                return List.of("clientCode", "seatCount");
            }
            return delegate.getParameterNames(method);
        }

        @Override
        public List<String> getParameterNames(
                Constructor<?> constructor) {
            if (constructor.getDeclaringClass()
                    == BookingRequest.class
                    && constructor.getParameterCount() == 2) {
                return List.of("clientCode", "seatCount");
            }
            return delegate.getParameterNames(constructor);
        }
    }

    private static void printParameterErrors(
            String label,
            Set<? extends ConstraintViolation<?>> violations) {

        Map<Integer, String> byIndex = new TreeMap<>();

        for (ConstraintViolation<?> violation : violations) {
            for (Path.Node node : violation.getPropertyPath()) {
                if (node.getKind() == ElementKind.PARAMETER) {
                    Path.ParameterNode parameter =
                            node.as(Path.ParameterNode.class);
                    byIndex.put(
                            parameter.getParameterIndex(),
                            parameter.getName());
                }
            }
        }

        String summary = byIndex.entrySet().stream()
                .map(entry -> entry.getKey() + ":"
                        + entry.getValue())
                .collect(Collectors.joining(", "));

        System.out.println(label + " -> " + summary);
    }

    private static void runChecks(
            String label,
            Validator validator,
            Method method,
            Constructor<BookingRequest> constructor) {

        BookingService service = new BookingService();
        Object[] invalidArguments = {"", 0};

        var executableValidator = validator.forExecutables();

        Set<ConstraintViolation<BookingService>> methodErrors =
                executableValidator.validateParameters(
                        service, method, invalidArguments);

        Set<ConstraintViolation<BookingRequest>> constructorErrors =
                executableValidator.validateConstructorParameters(
                        constructor, invalidArguments);

        printParameterErrors(label + " method", methodErrors);
        printParameterErrors(label + " constructor", constructorErrors);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Method method = BookingService.class.getMethod(
                "reserve", String.class, int.class);

        Constructor<BookingRequest> constructor =
                BookingRequest.class.getConstructor(
                        String.class, int.class);

        try (ValidatorFactory defaultFactory =
                     Validation.buildDefaultValidatorFactory()) {
            runChecks(
                    "default",
                    defaultFactory.getValidator(),
                    method,
                    constructor);
        }

        Configuration<?> configuration =
                Validation.byDefaultProvider().configure();

        ParameterNameProvider fallback =
                configuration.getDefaultParameterNameProvider();

        try (ValidatorFactory customFactory = configuration
                .parameterNameProvider(
                        new FriendlyParameterNames(fallback))
                .buildValidatorFactory()) {
            runChecks(
                    "custom",
                    customFactory.getValidator(),
                    method,
                    constructor);
        }
    }
}
~~~

### 5.1. Phân tích những điểm quan trọng

1. `@NotBlank` và `@Min(1)` được đặt trên **method parameter** và **constructor parameter**. Hai lời gọi kiểm tra nhận `Object[]{"", 0}` nên cả hai vị trí đều tạo lỗi.
2. `validateParameters(service, method, args)` kiểm tra tham số method. `validateConstructorParameters(constructor, args)` kiểm tra tham số constructor. Cả hai đều thuộc `Validator.forExecutables()`; chúng **không cần** gọi method hoặc khởi tạo object.
3. `FriendlyParameterNames` dùng đúng kiểu reflection và nhận `ParameterNameProvider` mặc định làm delegate. Với đúng executable được chọn, nó trả `clientCode`/`seatCount`; với mọi executable khác, nó dùng fallback.
4. `List.of(...)` là danh sách bất biến; `delegate` là field `final`. Không có mutable map/request state nào trong provider. Điều này phù hợp yêu cầu thread-safe, giả sử delegate cũng tuân thủ contract.
5. `TreeMap<Integer,String>` sắp xếp **theo vị trí tham số**, tránh dựa vào thứ tự của `Set<ConstraintViolation<?>>` vốn không được bảo đảm.
6. Đoạn in kết quả lấy tên trực tiếp từ `Path.ParameterNode`; không phụ thuộc dấu chấm hay cú pháp toàn chuỗi `getPropertyPath().toString()`.

### 5.2. Maven cấu hình -parameters và chạy demo

Tạo `pom.xml` tại root dự án:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>parameter-names-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.3.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chạy bằng JDK 17+ và Maven:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.validation.Demo
~~~

Các dòng **do `Demo` in ra**, không kể log do Maven hoặc validation provider có thể phát ra:

~~~text
default method -> 0:customerId, 1:seats
default constructor -> 0:customerId, 1:seats
custom method -> 0:clientCode, 1:seatCount
custom constructor -> 0:clientCode, 1:seatCount
~~~

Nếu bỏ `<parameters>true</parameters>` rồi **clean và biên dịch lại** mà không có nguồn metadata tên khác, mặc định `default` điển hình thành `0:arg0, 1:arg1`. Hai dòng `custom` vẫn dùng tên do ta cung cấp.

Lưu ý phiên bản: Hibernate Validator **8.x** dùng Jakarta Validation **3.0**, tương thích với Java 17 và Spring Boot 3.x. Hợp đồng `ParameterNameProvider` đang dùng ở ví dụ có mặt ở cả Jakarta Validation 3.0 và 3.1. Khi chuyển sang một provider/phiên bản khác, cần kiểm tra compatibility matrix và dependency management của dự án.

### 5.3. Vì sao nên có fallback?

Một ứng dụng thực tế có nhiều method/constructor, kể cả do thư viện bên ngoài khai báo. Nếu custom provider luôn trả cùng hai tên cho **mọi** method, executable có 0, 1 hoặc 3 tham số sẽ nhận metadata sai; engine có thể phát sinh lỗi cấu hình thay vì violation hữu ích.

Cấu trúc an toàn:

~~~java
@Override
public List<String> getParameterNames(Method method) {
    if (/* đúng class/method/signature có quy ước riêng */) {
        return List.of(/* một tên cho mỗi tham số */);
    }
    return delegate.getParameterNames(method);
}
~~~

Đây là đoạn **minh họa** được rút từ class ở trên, không phải code biên dịch độc lập. Trong dự án có overload, method kế thừa, interface và proxy, nên kiểm tra cả signature đủ chính xác; chỉ so tên `"reserve"` có thể đụng overload. Bất kỳ lookup dựa trên tên khai báo/annotation nào cũng phải có quy tắc ổn định, kiểm thử được.

## 6. Cấu hình ParameterNameProvider ở đâu?

### 6.1. Jakarta Validation bootstrap

Cách portable là tùy chỉnh `Configuration` trước khi xây dựng `ValidatorFactory`:

~~~java
Configuration<?> config =
        Validation.byDefaultProvider().configure();

ParameterNameProvider defaultProvider =
        config.getDefaultParameterNameProvider();

ValidatorFactory factory = config
        .parameterNameProvider(
                new FriendlyParameterNames(defaultProvider))
        .buildValidatorFactory();

try {
    Validator validator = factory.getValidator();
    // Use validator.forExecutables() here.
} finally {
    factory.close();
}
~~~

Đây là **đoạn trích** dựa trên `Demo.FriendlyParameterNames` đã khai báo, không chạy độc lập. Chọn provider trước khi tạo factory, vì `Validator` được sinh ra từ factory sẽ dùng cấu hình của factory. Ngoài API Java, Jakarta Validation có thể cấu hình provider bằng `META-INF/validation.xml`; cần dùng chính xác namespace/schema phù hợp phiên bản đang chạy và bảo đảm không có nhiều file cấu hình trùng.

Tùy use case, Jakarta Validation còn có `ValidatorContext.parameterNameProvider(...)` để tùy chỉnh cho `Validator` lấy từ một factory. Nếu cần hành vi nhất quán toàn ứng dụng, cấu hình ở factory thường dễ quản lý hơn.

### 6.2. Spring Framework và LocalValidatorFactoryBean

Spring Framework 6.x tích hợp Jakarta Validation qua `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean`, làm cầu nối giữa API Spring `Validator` và Jakarta `ValidatorFactory`. Một ứng dụng Spring MVC có provider Bean Validation trên classpath thường đăng ký bean validator dùng cho `@Valid` / `@Validated`.

`LocalValidatorFactoryBean` có phương thức:

~~~java
void setParameterNameDiscoverer(
        org.springframework.core.ParameterNameDiscoverer discoverer)
~~~

Phương thức này cho phép Spring cấu hình cách tìm tên tham số khi cần. Có thể dùng `org.springframework.core.DefaultParameterNameDiscoverer`. Ví dụ bean cấu hình khi ứng dụng **chủ động sở hữu** cấu hình validation:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.DefaultParameterNameDiscoverer;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
class ValidationConfig {

    @Bean
    LocalValidatorFactoryBean validator() {
        LocalValidatorFactoryBean bean =
                new LocalValidatorFactoryBean();

        bean.setParameterNameDiscoverer(
                new DefaultParameterNameDiscoverer());

        return bean;
    }
}
~~~

Đây là snippet tích hợp Spring, không ghép chung vào chương trình `Demo` độc lập. Trong Spring Boot, cần kiểm tra các bean/auto-configuration hiện có trước khi định nghĩa lại validator: việc khai báo thêm `LocalValidatorFactoryBean` có thể đổi cách ứng dụng chọn validator, message source hay các tùy chỉnh khác. Trên Spring Framework 6, `DefaultParameterNameDiscoverer` chủ yếu tận dụng Java reflection cho Java (và có thể hỗ trợ Kotlin khi thích hợp); nó không bảo đảm lấy lại tên Java thực nếu class file thiếu metadata `-parameters`.

**Đừng nhầm hai SPI:**

| API | Thuộc hệ sinh thái | Vai trò |
| --- | --- | --- |
| `jakarta.validation.ParameterNameProvider` | Jakarta Validation | Cung cấp tên cho method/constructor parameter trong violation path |
| `org.springframework.core.ParameterNameDiscoverer` | Spring Core | Tìm tên tham số cho hạ tầng Spring; có thể được Spring adapter sử dụng cho Jakarta Validation |
| `org.springframework.validation.Validator` | Spring | Kiểm tra target object và ghi lỗi vào `Errors` |
| `jakarta.validation.Validator` | Jakarta Validation | Kiểm tra bean/executable và trả `ConstraintViolation` |

Nếu cần **chính xác một custom `ParameterNameProvider`** bên trong Spring, hãy bảo đảm cấu hình cuối cùng của `ValidatorFactory` thực sự sử dụng provider đó. Không mặc nhiên cho rằng gọi Java SE `Validation.buildDefaultValidatorFactory()` và Spring-managed `LocalValidatorFactoryBean` sử dụng cùng một factory hoặc cùng cách đặt tên.

### 6.3. Tên trong kết quả HTTP không nhất thiết là tên của Jakarta violation

Xét Spring MVC controller:

~~~java
@GetMapping("/bookings")
public String find(@RequestParam("customer") String id) {
    return id;
}
~~~

`"customer"` là **tên query parameter HTTP** do `@RequestParam` chỉ định; `id` là tên tham số Java. Đây là hai nguồn tên khác nhau. Binding errors, `MethodArgumentNotValidException` và `HandlerMethodValidationException` có cấu trúc xử lý riêng theo trường hợp Spring MVC. Không nên hứa rằng thay `ParameterNameProvider` sẽ tự động đổi mọi key trong JSON lỗi HTTP của Spring.

Trong các cơ chế method validation, Spring hoặc một proxy/interceptor có thể kích hoạt Jakarta `ExecutableValidator` và tạo `ConstraintViolation`. Khi đó `ParameterNameProvider` ảnh hưởng đến tên node `PARAMETER`. Tuy nhiên ứng dụng vẫn phải quyết định cách ánh xạ lỗi sang API response. Nếu client phụ thuộc trường `field` hoặc `parameter` ổn định, nên thiết kế contract lỗi rõ ràng thay vì dùng nguyên chuỗi `Path.toString()` làm định danh công khai.

## 7. Constructor, return value, cascade và container element

`ParameterNameProvider` có overload cho **constructor** vì constraint có thể đặt ngay trên tham số khởi tạo:

~~~java
public BookingRequest(
        @NotBlank String customerId,
        @Min(1) int seats) {
    // ...
}
~~~

`ExecutableValidator.validateConstructorParameters(...)` tạo violation có đường dẫn đi qua constructor node và parameter node. Với return value constraint như `@NotNull` trên giá trị trả về, path có node `ElementKind.RETURN_VALUE` với tên quy ước `<return value>`; parameter name provider không được dùng để đổi tên node này.

Với một parameter kiểu object có `@Valid` và nested field không hợp lệ, path có thể tiếp tục từ parameter node sang property node, chẳng hạn:

~~~text
reserve.request.customerId
~~~

`request` (parameter node) đến từ `ParameterNameProvider`, còn `customerId` (property node) là tên thuộc tính của bean. Với container element constraint, path có thể chứa các node bổ sung và chỉ số/key của phần tử. Bởi vậy, không thể xem toàn bộ path là duy nhất một tên tham số.

Với **cross-parameter constraint** (quy tắc đánh giá phối hợp nhiều tham số), chuẩn có node loại `CROSS_PARAMETER` mang tên `<cross-parameter>`. Node này khác với từng `ParameterNode`; muốn gắn lỗi lên tham số cụ thể, constraint validator phải xây dựng đường dẫn lỗi tương ứng. `ParameterNameProvider` không tự phân chia một cross-parameter violation thành nhiều lỗi riêng.

## 8. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| Path hiển thị `arg0`, `arg1` | Bytecode thiếu tên tham số Java | Bật `-parameters` tại module khai báo method, clean rebuild, kiểm tra reflection |
| Tên Java đúng ở máy này nhưng khác trên CI | Cấu hình compiler hoặc artifact khác nhau | Kiểm tra command compiler và `isNamePresent()` trên artifact thực tế |
| Không có violation dù tham số sai | Chưa kích hoạt method validation | Dùng `ExecutableValidator` hoặc cơ chế intercept validation của Spring |
| Provider custom không ảnh hưởng | Factory/validator được khởi tạo trước cấu hình, hoặc Spring dùng factory khác | Xác định instance `ValidatorFactory` thực dùng và gắn provider tại bootstrap |
| Tên trả ra bị xô lệch | Danh sách tên không đúng thứ tự/độ dài | Trả tên theo index của executable; fallback cho executable khác |
| Test flaky khi có nhiều lỗi | Dựa vào thứ tự `Set<ConstraintViolation>` | Lấy `ParameterNode.getParameterIndex()` rồi sort theo index |
| Exception khi provider lấy tên | Lỗi runtime trong custom provider hoặc metadata không hợp lệ | Xem stack trace của `ValidationException` và kiểm tra rule đặt tên |
| Lỗi API HTTP vẫn mang tên cũ | Spring MVC tạo error response theo binding/method validation riêng | Xem lớp chuyển đổi lỗi của ứng dụng và tách tên HTTP khỏi tên parameter |
| Kết quả sai khi chạy đa luồng | Cache mutable hoặc field của provider bị thay đổi | Dùng implementation bất biến/thread-safe; tránh state theo request |

### Quy trình debug nhanh

1. Xác nhận điểm kích hoạt: `Validator.forExecutables().validateParameters(...)` hoặc method-validation integration thực sự đã chạy.
2. Kiểm tra đúng method/constructor reflection và signature được dùng, nhất là trường hợp proxy/interface/overload.
3. Dùng `Executable.getParameters()`, `Parameter.getName()` và `isNamePresent()` để kiểm tra tên thực trong bytecode.
4. Xác nhận `ValidatorFactory.getParameterNameProvider()` hoặc đường cấu hình Spring đang sử dụng provider nào.
5. In từng `Path.Node` gồm `getKind()`/`getName()`; với `PARAMETER` lấy thêm `getParameterIndex()` để xác nhận ánh xạ đúng.
6. Với test, so tên và vị trí rõ ràng, đồng thời kiểm tra nội dung constraint message riêng. Không dựa vào thứ tự iteration hoặc format toàn chuỗi path.

## 9. Bài tập và tiêu chí tự kiểm tra

**Bài tập 1 — Đoán kết quả:** Với `reserve(@NotBlank String customerId, @Min(1) int seats)` và đối số `["", 0]`, compiler không bật `-parameters`, default provider sẽ cho tên nào? Theo quy tắc mặc định: `arg0` và `arg1`. Vị trí tương ứng vẫn là `0` và `1`. Nếu chỉ `seats=2`, sẽ còn lỗi ở vị trí `0`.

**Bài tập 2 — Thêm overload:** Thêm `reserve(String customerId)`. Sửa provider custom sao cho chỉ method hai tham số dùng `clientCode`/`seatCount`, còn overload một tham số dùng fallback. Giải thích vì sao chỉ so tên `"reserve"` là chưa đủ.

**Bài tập 3 — Constructor:** Thêm constructor không tham số vào `BookingRequest`. Vì sao provider phải trả danh sách rỗng cho constructor đó? Đối chiếu `getParameterCount()` để chắc danh sách tên không bị lệch.

**Bài tập 4 — Tách khái niệm:** Trong controller `find(@RequestParam("customer") String id)`, đâu là tên của HTTP query parameter, đâu là tên Java method parameter? Vì sao thay `ParameterNameProvider` không có nghĩa là đổi `"customer"` thành `"id"` trong URL?

**Bài tập 5 — Test tự động:** Viết test tạo `ValidatorFactory` theo hai cấu hình default/custom, gọi `validateParameters()` và xác minh một violation có `ParameterNode.getParameterIndex()==0`, với tên lần lượt là `customerId` và `clientCode`. Không so sánh toàn bộ `Set` theo thứ tự iteration.

**Điểm cần nhớ:** `ParameterNameProvider` là hạ tầng đặt tên cho **tham số method/constructor trong đường dẫn lỗi Jakarta Validation**. Mặc định tên đến từ metadata Java reflection (`-parameters` giúp giữ tên nguồn); provider tùy chỉnh có thể thay cách hiển thị, nhưng phải đúng thứ tự, thread-safe và có fallback. Khi dùng kết quả, chỉ số từ `Path.ParameterNode` đáng tin cậy hơn việc tự phân tích chuỗi path.

## Tài liệu tham khảo

- [Jakarta Validation 3.1 — Naming parameters và ConstraintViolation paths](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html)
- [Jakarta Validation 3.1 — ParameterNameProvider API](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/ParameterNameProvider.html)
- [Hibernate Validator 8 — Reference Guide, Configuration / ParameterNameProvider](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
- [Spring Framework 6.2 — LocalValidatorFactoryBean API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Framework — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
