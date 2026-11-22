# Cơ chế AOP proxy kích hoạt kiểm tra phương thức trong Spring Framework

Trong Spring, annotation Jakarta Validation như `@NotBlank`, `@Min`, `@Valid` có thể xuất hiện trên **tham số hoặc giá trị trả về của phương thức**. Tuy nhiên, Java không tự kiểm tra một lời gọi method chỉ vì annotation xuất hiện trong source. Đối với một Spring bean thông thường (đặc biệt ở tầng service), Spring có thể kích hoạt **method validation** bằng **AOP proxy**: một đối tượng trung gian chặn lời gọi, yêu cầu Jakarta Validation kiểm tra các tham số, gọi phương thức thật nếu hợp lệ, rồi kiểm tra giá trị trả về.

Mục tiêu của bài học là hiểu chính xác **vì sao một method được validate**, các điều kiện để cơ chế hoạt động, những lời gọi nó **không chặn được**, và cách chẩn đoán một constraint có khai báo nhưng không chạy.

Trong ví dụ này, dùng Spring Framework 6.x / Spring Boot 3.x, Java 17+ và các annotation thuộc package `jakarta.validation.*`. Spring Framework 6.1+ còn có **method validation tích hợp trực tiếp trong Spring MVC**, cần phân biệt rõ với phương thức service được proxy bằng AOP.

## 1. Phân biệt bean validation, method validation và AOP proxy

| Khái niệm | Đối tượng kiểm tra | Điểm kích hoạt |
|---|---|---|
| Bean Validation thông thường | Trường/property của một object và constraint cấp class | `jakarta.validation.Validator.validate(object)` hoặc Spring gọi validator cho DTO |
| Method validation | Constraint trên **tham số**, **giá trị trả về**, cross-parameter, và các object được cascade bằng `@Valid` | `ExecutableValidator`, Spring AOP hoặc cơ chế method validation của MVC |
| AOP proxy | **Lời gọi method đi qua một bean proxy** | Framework tạo proxy/advisor và chạy interceptor quanh method call |
| Data binding | Chuyển request/string/form thành Java object và kiểu dữ liệu phù hợp | Spring MVC `WebDataBinder`, argument resolvers |

Ba tên gần nhau nhưng khác vai trò:

- `@Validated` là annotation của Spring (`org.springframework.validation.annotation.Validated`). Trong phương án **method validation bằng AOP**, đặt trên **class Spring bean** để cơ chế mặc định nhận diện bean cần được chặn; annotation này còn cho phép chọn nhóm validation.
- `@Valid` là annotation của Jakarta Validation (`jakarta.validation.Valid`). Nó yêu cầu **cascade** vào thuộc tính của object được gắn annotation; bản thân nó không phải constraint như `@NotBlank` hay `@NotNull`.
- `@NotBlank`, `@Size`, `@Min`, `@NotNull`... là các constraint thực sự được Jakarta Validation provider kiểm tra khi hệ thống gọi validation.

Ví dụ, khi có:

~~~java
@Service
@Validated
public class AccountService {
    public void register(@NotBlank String accountCode) {
        // business logic
    }
}
~~~

Spring phải có bean method-validation post-processor và Jakarta Validation provider; bên gọi phải dùng **Spring-managed proxy** của `AccountService`. Gọi `new AccountService().register("")` không tự kích hoạt method validation.

## 2. Luồng hoạt động: từ `@Validated` đến `ExecutableValidator`

Hai thành phần Spring đáng chú ý:

1. `MethodValidationPostProcessor` — BeanPostProcessor đăng ký advisor cho các target bean có `@Validated`; Spring có thể trả về proxy thay vì đối tượng đích nguyên bản.
2. `MethodValidationInterceptor` — lời khuyên AOP dạng **around interception** dùng Jakarta Validation `ExecutableValidator` để kiểm tra tham số và giá trị trả về.

Luồng tiêu biểu của một method đồng bộ:

~~~text
Client / Controller / another Spring bean
                   |
                   | gọi service.execute(argument)
                   v
         Spring AOP proxy của service
                   |
                   v
         MethodValidationInterceptor
                   |
                   | 1. validateParameters(...)
                   |    Nếu có vi phạm: ném exception
                   |    Không chạy method body
                   |
                   v
          invocation.proceed()
                   |
                   v
         Method thật trên target
                   |
                   | tạo/return kết quả
                   v
         MethodValidationInterceptor
                   |
                   | 2. validateReturnValue(...)
                   |    Nếu có vi phạm: ném exception
                   v
           Client nhận kết quả
~~~

`ExecutableValidator` là API **Jakarta Validation chuẩn**, lấy qua `Validator.forExecutables()`. Spring interceptor ủy quyền cho provider như Hibernate Validator để đánh giá constraint, không tự triển khai lại thuật toán `@NotBlank` hay `@Size`.

Chi tiết quan trọng:

- **Tham số sai**: interceptor có thể ném exception **trước** khi logic nghiệp vụ chạy.
- **Giá trị trả về sai**: method body **đã chạy xong**; interceptor chỉ phát hiện sau đó và không trao kết quả sai cho caller. Những side effect đã xảy ra bên trong method không tự được đảo ngược. Nếu có transaction, việc rollback còn phụ thuộc transaction configuration và thứ tự các advisor.
- **Method ném exception của nghiệp vụ**: đây không phải một giá trị trả về bình thường để kiểm tra return-value constraint.
- **Lời gọi không đi qua proxy**: interceptor không có cơ hội chạy, dù annotation vẫn tồn tại.
- **Các advisor khác** như transaction, cache và async có thể có thứ tự khác nhau tùy cấu hình; không mặc định method validation luôn nằm trước hoặc sau mọi advisor khác.

Đây là lý do method validation tại **service boundary** hữu ích để phát hiện input bất hợp lệ trước khi thực hiện nghiệp vụ, nhưng không nên xem nó như cơ chế thay thế transaction, kiểm soát quyền truy cập hay validation DTO tại HTTP boundary.

## 3. Điều kiện tối thiểu để method validation bằng AOP hoạt động

### 3.1. Có Jakarta Validation API và provider

`@NotBlank` chỉ là metadata. Cần một implementation như Hibernate Validator để thực thi.

Trong một project Spring Boot 3.x đã được cấu hình Java 17+ và Spring Boot Gradle plugin, dependency phổ biến:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Starter giúp tích hợp Jakarta Validation provider với Spring Boot và thường cho phép auto-configuration của `MethodValidationPostProcessor`. Trong Spring Framework thuần, cần tự cấu hình provider, `Validator`/`LocalValidatorFactoryBean` và `MethodValidationPostProcessor` phù hợp.

Không trộn `javax.validation.*` của hệ sinh thái Spring 5 / Boot 2 với `jakarta.validation.*` của Spring 6 / Boot 3.

### 3.2. Target là Spring-managed bean có `@Validated`

~~~java
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class ReportService {
    // Public method có các constraint trên parameter / return.
}
~~~

Trong mô hình proxy method validation thông dụng, `@Validated` ở **cấp class** được `MethodValidationPostProcessor` nhận diện để áp dụng advisor. Nó khác với chỉ viết `@Valid` hoặc `@NotBlank` ở một method bất kỳ. Trong trường hợp dùng `@Validated(SomeGroup.class)`, group được chọn cũng ảnh hưởng constraint nào được đánh giá.

Một phương thức service nên được **gọi qua bean do Spring inject** từ một bean khác. Annotation không tạo phép màu cho object được khởi tạo thủ công.

### 3.3. Method phải được proxy chặn được

Ở kịch bản dễ học nhất, dùng **public, non-final method** trên **non-final Spring bean class**, gọi qua reference đã được Spring cấp. Nếu dùng JDK dynamic proxy, method phải được expose bởi interface tương ứng; nếu dùng CGLIB/class-based proxy, target class/method phải có khả năng override.

`private` method không được Spring AOP chặn theo phương thức proxy thông thường. `final` method không thể được override qua CGLIB và do đó không được CGLIB advice. Constructor, field access và đoạn code chạy trực tiếp trong object không phải join point method call qua proxy này.

## 4. Ví dụ hoàn chỉnh với Spring Boot: minh họa cả thành công và lỗi

Ví dụ dùng hai class Java trong cùng package `com.example.methodvalidation`. Spring Boot context tự tạo bean service, proxy và Jakarta Validation integration. Chương trình cố tình gọi một method sai, một method trả dữ liệu sai và một method gọi nội bộ để nhìn thấy điểm khác nhau.

### 4.1. `CodeService.java`

Lưu tại `src/main/java/com/example/methodvalidation/CodeService.java`:

~~~java
package com.example.methodvalidation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.Locale;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class CodeService {

    @NotBlank
    public String normalize(
            @NotBlank
            @Size(min = 3, max = 8)
            String code) {
        return code.strip().toUpperCase(Locale.ROOT);
    }

    // Cố tình gọi phương thức cùng instance để minh họa bypass proxy.
    public String callInternally(String code) {
        return this.normalize(code);
    }

    @NotBlank
    public String returnBlank() {
        return "";
    }
}
~~~

Từng annotation ở vị trí riêng:

- `@Validated` trên class làm Spring AOP method-validation processor nhận diện service.
- `@NotBlank` và `@Size` trên tham số `code` được kiểm tra **trước** lời gọi `normalize` đi qua proxy.
- `@NotBlank` trên phương thức `normalize` là **return-value constraint**, dùng để kiểm tra chuỗi trả về sau khi method chạy.
- `@NotBlank` trên `returnBlank` cố tình tạo vi phạm ở **return value**.
- `callInternally` gọi `this.normalize(code)` **trực tiếp trên target** nên không có một lần interception thứ hai cho `normalize`. Method `callInternally` không có constraint trực tiếp.

Dùng `Locale.ROOT` khiến phép chuyển uppercase có hành vi nhất quán, tránh biến động do default locale của máy chạy. Tất cả phương thức trong ví dụ được công khai và class không `final`, phù hợp cả yêu cầu phổ biến của CGLIB proxy.

### 4.2. `DemoApplication.java`

Lưu tại `src/main/java/com/example/methodvalidation/DemoApplication.java`:

~~~java
package com.example.methodvalidation;

import jakarta.validation.ConstraintViolationException;
import org.springframework.aop.support.AopUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication implements CommandLineRunner {

    private final CodeService codeService;

    public DemoApplication(CodeService codeService) {
        this.codeService = codeService;
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println(
            "AOP proxy: " + AopUtils.isAopProxy(codeService));

        System.out.println(
            "Hợp lệ: " + codeService.normalize("abc"));

        System.out.println(
            "Tham số sai: " + countViolations(
                () -> codeService.normalize("xy")));

        System.out.println(
            "Tự gọi nội bộ: " + codeService.callInternally("xy"));

        System.out.println(
            "Kết quả sai: " + countViolations(
                () -> codeService.returnBlank()));
    }

    private static int countViolations(Runnable action) {
        try {
            action.run();
            return 0;
        } catch (ConstraintViolationException ex) {
            return ex.getConstraintViolations().size();
        }
    }
}
~~~

Mã trên sử dụng `jakarta.validation.ConstraintViolationException` mặc định của Spring method-validation interceptor (khi không bật chế độ chuyển đổi exception sang `MethodValidationException`). `countViolations` chỉ bắt đúng loại exception cần minh họa, nên những lỗi cấu hình khác vẫn được báo ra thay vì bị che giấu.

Trong project Spring Boot 3.x có plugin Gradle và dependency Validation, chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng:

~~~powershell
.\gradlew.bat bootRun
~~~

Ngoài log khởi động Spring Boot, chương trình in:

~~~text
AOP proxy: true
Hợp lệ: ABC
Tham số sai: 1
Tự gọi nội bộ: XY
Kết quả sai: 1
~~~

Vì sao các kết quả này ổn định trong cấu hình mẫu?

1. `CodeService` là Spring bean `@Validated` và có constraint, nên method validation auto-configuration của Boot tạo một AOP proxy: `AopUtils.isAopProxy(...)` trả `true`.
2. `normalize("abc")` hợp lệ: chuỗi không rỗng và dài 3 ký tự. Body trả `"ABC"` cũng đạt `@NotBlank`.
3. `normalize("xy")` sai `@Size(min=3,max=8)`; `@NotBlank` vẫn đạt, nên tập vi phạm có đúng **một** phần tử; method body không được gọi.
4. `callInternally("xy")` được gọi qua proxy, nhưng bên trong target gọi `this.normalize("xy")`. Lời gọi nội bộ đi thẳng vào method body và trả `"XY"`, cho thấy constraint `@Size` trên `normalize` đã **không được kiểm tra** trong lần gọi đó.
5. `returnBlank()` thực thi và trả chuỗi rỗng; interceptor kiểm tra `@NotBlank` ở **return value**, phát hiện một vi phạm và ném exception thay vì trả chuỗi cho caller.

Cả đoạn demo không có database, không cần HTTP endpoint và không cần lập trình interceptor thủ công. Việc tạo proxy/advisor và gọi provider được Spring/Boot quản lý.

Nếu `AOP proxy: false` hoặc ứng dụng không chạy, kiểm tra provider, cấu hình Boot, `@Validated`, bean thật mà bạn đang inject và tình trạng method-validation post-processor trước khi kết luận rằng Jakarta Validation không hoạt động.

## 5. Chứng minh cơ chế bằng integration test

Một test chỉ gọi `new CodeService().normalize("xy")` **không phải** integration test của Spring method validation: object được tự tạo không mang proxy Spring.

Để kiểm tra đúng integration, dùng `@SpringBootTest` và inject service. Với Spring Boot test starter:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Lưu tại `src/test/java/com/example/methodvalidation/CodeServiceValidationTest.java`:

~~~java
package com.example.methodvalidation;

import jakarta.validation.ConstraintViolationException;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class CodeServiceValidationTest {

    @Autowired
    private CodeService service;

    @Test
    void proxyChecksParameterBeforeMethodBody() {
        assertTrue(AopUtils.isAopProxy(service));
        assertEquals("ABC", service.normalize("abc"));

        var error = assertThrows(
            ConstraintViolationException.class,
            () -> service.normalize("xy"));

        assertEquals(1, error.getConstraintViolations().size());
    }

    @Test
    void selfInvocationBypassesValidationAdvice() {
        assertEquals("XY", service.callInternally("xy"));
    }

    @Test
    void proxyChecksReturnedValue() {
        var error = assertThrows(
            ConstraintViolationException.class,
            () -> service.returnBlank());

        assertEquals(1, error.getConstraintViolations().size());
    }
}
~~~

Chạy `./gradlew test` hoặc `.\gradlew.bat test`. Kỳ vọng: ba test **PASS** trong project Spring Boot 3.x đã có validation provider và cấu hình AOP method validation mặc định. Đây là kiểm tra hợp đồng runtime: object đã được Spring quản lý, tồn tại proxy, validation tham số, validation return và giới hạn self-invocation.

Với các ứng dụng bật `setAdaptConstraintViolations(true)`, loại exception có thể chuyển thành `MethodValidationException`; khi đó test cần đổi kỳ vọng tương ứng. Trong project Spring Framework không dùng Boot, cũng cần đăng ký `MethodValidationPostProcessor`.

## 6. `MethodValidationPostProcessor` và `MethodValidationInterceptor`

### 6.1. Vì sao cần BeanPostProcessor?

`MethodValidationPostProcessor` kiểm tra các bean do Spring tạo ra và đăng ký một advisor nhằm áp dụng validation cho method phù hợp. Advisor gắn:

- **Pointcut** nhận diện bean eligible, thường dựa trên `@Validated`.
- **Advice** là `MethodValidationInterceptor`, chạy quanh lời gọi đã match.
- **Proxy** là đối tượng mà client nhận từ Spring ApplicationContext.

Một đối tượng Java được tạo trước bằng `new` bên ngoài container không qua bean post-processing và không tự nhận advisor. Đó là giới hạn về **lifecycle và ownership**, không phải do annotation `@Size` không có hiệu lực.

### 6.2. Spring Framework không dùng Boot: cấu hình tường minh

Trong Spring application thuần có provider Jakarta Validation tương thích, có thể đăng ký:

~~~java
package com.example.methodvalidation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;

@Configuration
public class ValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }

    @Bean
    public static MethodValidationPostProcessor
            methodValidationPostProcessor() {
        return new MethodValidationPostProcessor();
    }
}
~~~

Đây là cấu hình **thay thế cho ứng dụng Spring Framework không có Boot auto-configuration**, đặt trong context có component scan cho service và provider. `LocalValidatorFactoryBean` kết nối Spring với Jakarta Validation; `MethodValidationPostProcessor` kích hoạt đường chặn phương thức.

Hàm `@Bean static` cho post-processor giúp nó được khởi tạo sớm, tránh các vấn đề lifecycle khi cấu hình BeanPostProcessor bằng instance method. Đừng sao chép cấu hình này vào một ứng dụng Boot đã có post-processor tương ứng rồi tạo trùng các advisor một cách vô ý.

### 6.3. Những bước interceptor thực hiện

`MethodValidationInterceptor` lấy thông tin method đang được gọi, arguments, target và các group cần áp dụng. Nó dùng Jakarta Validation `ExecutableValidator`:

~~~java
// Khái niệm, không phải source code hoàn chỉnh của Spring:
executableValidator.validateParameters(
    target, method, arguments, groups);

// Chỉ khi không có vi phạm đầu vào:
Object returnValue = invocation.proceed();

executableValidator.validateReturnValue(
    target, method, returnValue, groups);
~~~

Đây là **pseudocode về thứ tự**, không phải code có thể copy nguyên xi để biên dịch; chi tiết nội bộ còn xử lý method bridge/proxy, cascade, lỗi cấu hình và các loại return khác nhau. `validateParameters(...)` trả tập `ConstraintViolation<T>`; caller/framework quyết định xử lý lỗi theo cấu hình. Không nhất thiết có một instance `ConstraintValidator` mới cho mỗi lời gọi vì provider có thể cache.

Cơ chế này không dùng Java compiler để tự chèn `if` vào method. Nó là runtime interception dựa trên object proxy.

## 7. `@Validated`, `@Valid`, constraint và validation groups

### 7.1. Vì sao `@Valid` một mình không đủ cho mọi method?

Xét DTO:

~~~java
public record RegistrationRequest(
        @NotBlank String userId,
        @Min(1) int quantity) {
}
~~~

Và một service:

~~~java
@Service
@Validated
public class RegistrationService {

    public void register(
            @NotNull @Valid RegistrationRequest request) {
        // Chạy nghiệp vụ sau validation.
    }
}
~~~

Đây là các **đoạn code minh họa**, tách khỏi ví dụ Boot trước đó. `@Valid` yêu cầu provider đi vào `RegistrationRequest` và kiểm tra `userId`/`quantity`; `@NotNull` trên parameter bảo đảm object gốc không null. Nếu chỉ gắn `@Valid` thì theo Jakarta Validation, `null` không tự vi phạm cascade validation.

Trong Spring service AOP, cần có `@Validated` ở class và method invocation phải đi qua proxy. Lời gọi có annotation `@Valid` nhưng diễn ra qua `this.register(...)` vẫn bypass validation advice theo cơ chế proxy bình thường.

### 7.2. `@Validated` chọn nhóm

Mặc định, constraint không khai báo `groups` được áp trong `Default`. Khi cần nhiều phase, có thể đặt marker group:

~~~java
public interface PublishChecks {
}
~~~

~~~java
@Service
@Validated(PublishChecks.class)
public class PublishingService {

    public void publish(
            @NotBlank(groups = PublishChecks.class)
            String title) {
        // Xử lý sau khi tham số đạt nhóm PublishChecks.
    }
}
~~~

Đoạn code này minh họa cách cấu hình **group trên class**, không chạy cùng demo `CodeService`. Khi một class được `@Validated(PublishChecks.class)`, cơ chế sẽ chọn các constraint của nhóm tương ứng; các constraint chỉ thuộc `Default` không được tự động thêm vào cùng nhóm nếu không có quan hệ kế thừa/group sequence phù hợp.

Để tránh nhiều quy tắc bị bỏ sót, thiết kế các group có mục đích rõ ràng và kiểm thử cả dữ liệu hợp lệ lẫn không hợp lệ cho mỗi group.

## 8. AOP proxy có những giới hạn nào?

### 8.1. Self-invocation: gọi qua `this` bỏ qua proxy

Đây là lỗi dễ gặp nhất:

~~~java
@Service
@Validated
public class PaymentService {

    public void placeOrder(String reference) {
        this.checkReference(reference); // không qua AOP proxy
    }

    public void checkReference(
            @NotBlank String reference) {
        // Phần xử lý chạy trực tiếp khi self-invocation.
    }
}
~~~

Nếu gọi `paymentService.placeOrder("")` qua proxy, Spring có thể advice lời gọi `placeOrder`, nhưng trong target việc gọi `this.checkReference("")` **không tạo một lượt advice mới**. Nếu `placeOrder` không có constraint, chuỗi rỗng có thể đi vào `checkReference` mà không bị chặn.

Đây là đặc tính của Spring AOP proxy, cũng xuất hiện với `@Transactional`, `@Cacheable` và một số advice dựa trên proxy. Nó không đồng nghĩa annotation `@NotBlank` bị Java xoá bỏ; annotation vẫn có trong metadata nhưng invocation không đi qua interceptor.

**Giải pháp có ý nghĩa kiến trúc:** đặt boundary cần validate vào một bean khác và inject bean đó:

~~~java
@Service
@Validated
public class ReferencePolicyService {

    public void checkReference(
            @NotBlank String reference) {
        // Mã kiểm tra / nghiệp vụ tại boundary.
    }
}

@Service
public class PaymentFacade {

    private final ReferencePolicyService policy;

    public PaymentFacade(ReferencePolicyService policy) {
        this.policy = policy;
    }

    public void placeOrder(String reference) {
        policy.checkReference(reference); // qua Spring proxy
    }
}
~~~

Trong project thật, bảo đảm các class ở package được Spring scan. Hai class này là các ví dụ minh họa riêng biệt, thông thường đặt trong file `ReferencePolicyService.java` và `PaymentFacade.java`. Khi `ReferencePolicyService` là bean `@Validated` và post-processor đã bật, lời gọi từ `PaymentFacade` sẽ đi qua proxy của policy service.

Một số kỹ thuật khác như self-injection hoặc `AopContext.currentProxy()` tồn tại, nhưng chúng tăng phụ thuộc vào AOP infrastructure; tách boundary qua bean thường rõ ràng và kiểm thử dễ hơn.

### 8.2. JDK dynamic proxy và CGLIB proxy

Spring AOP có thể tạo hai loại proxy:

| Loại proxy | Cơ chế | Giới hạn cần nhớ |
|---|---|---|
| JDK dynamic proxy | Proxy triển khai các **interface** của target | Client chỉ gọi được các phương thức được expose qua interface; injection bằng concrete class có thể gặp vấn đề |
| CGLIB class-based proxy | Proxy là **subclass** của target | Class `final` không thể subclass; method `final` và `private` không thể được override/advice |

Không dựa vào giả định “Spring luôn dùng JDK proxy” hay “Spring luôn dùng CGLIB”. Cấu hình `proxyTargetClass`, AOP infrastructure và Spring Boot có thể ảnh hưởng lựa chọn. Chẩn đoán bằng:

~~~java
System.out.println(
    org.springframework.aop.support.AopUtils.isAopProxy(service));

System.out.println(
    org.springframework.aop.support.AopUtils.isJdkDynamicProxy(
        service));

System.out.println(
    org.springframework.aop.support.AopUtils.isCglibProxy(
        service));
~~~

Đây là đoạn **minh họa đặt ở một method có biến `service` là Spring bean**; không phải class Java độc lập. Với demo `CodeService`, chỉ cần xác nhận `isAopProxy(...)` là `true` để biết reference đang được proxy.

Nếu bắt buộc method validation áp lên concrete method không nằm trên interface, hãy hiểu kiểu proxy đang có; trong cấu hình JDK proxy, method ấy có thể không được expose. Nếu class/method `final`, không thể kỳ vọng CGLIB advice mọi method.

### 8.3. Private method, constructor và object tự tạo

~~~java
CodeService manuallyCreated = new CodeService();
manuallyCreated.normalize("xy"); // không có Spring proxy
~~~

Trong ví dụ, `normalize("xy")` vẫn trả `"XY"` vì không có method interceptor. Cũng không có interceptor cho việc gọi một `private` helper bên trong target. Đừng cố dùng `@Validated` trên object không đi qua Spring container để thay thế gọi `Validator` trực tiếp.

Method được gọi trong constructor hoặc giai đoạn bean initialization sớm cũng không nên được giả định đang đi qua proxy hoàn chỉnh. Nếu cần validation ở thời điểm xây dựng object, dùng validation programmatic tại điểm có thể kiểm soát, hoặc tách thao tác ra thành lifecycle sau khi bean được khởi tạo.

### 8.4. Kế thừa, override và annotation trên interface

Bean Validation có các quy tắc **method inheritance** để tránh một implementation siết chặt tiền điều kiện do interface/superclass cam kết. Ví dụ một implementation có thể gây `ConstraintDeclarationException` nếu thêm constraint vào parameter của method override trái với quy tắc Jakarta Validation.

Không khắc phục sự cố bằng cách tùy tiện nhân bản `@NotNull`, `@Size` lên cả interface và implementation. Hãy khai báo contract ở một vị trí nhất quán, theo đúng quy tắc method constraint inheritance, rồi kiểm tra bằng provider.

### 8.5. Thread, async và reactive: xác định boundary thực sự

Lời gọi qua proxy chỉ kiểm tra dữ liệu tại thời điểm interceptor có thể quan sát. Với `@Async`, `@Transactional` hoặc trả về `CompletableFuture`/`Mono`/`Flux`, thứ tự advisor và thời điểm dữ liệu thật xuất hiện rất quan trọng. Một constraint trên object wrapper không mặc nhiên chứng minh **nội dung được phát ra bất đồng bộ** đã được kiểm tra.

Với ứng dụng reactive, dùng contract và validator phù hợp với reactive flow; đừng suy luận rằng Jakarta Validation method interception mặc định sẽ đợi tất cả các phần tử phát ra để chạy `@NotBlank` trên từng phần tử. Muốn kiểm tra payload bất đồng bộ, xác định rõ nơi lấy dữ liệu và nơi áp quy tắc.

## 9. Service AOP method validation khác Spring MVC method validation thế nào?

### 9.1. Spring MVC 6.1+ có method validation tích hợp trực tiếp

Đây là điểm dễ gây nhầm khi đọc tài liệu Spring cũ. Từ **Spring Framework 6.1**, Spring MVC có hỗ trợ method validation ở tầng controller **không cần AOP proxy cho controller**. Khi một `@RequestMapping` handler có constraint trực tiếp trên parameter hoặc return value, MVC có cơ chế riêng thực hiện kiểm tra.

Ví dụ controller Spring MVC 6.1+:

~~~java
@RestController
public class LookupController {

    @GetMapping("/lookup")
    public String lookup(
            @RequestParam
            @NotBlank
            @Size(min = 3)
            String code) {
        return code;
    }
}
~~~

Đây là đoạn **minh họa** yêu cầu Spring MVC/web starter và imports cho `@RestController`, `@GetMapping`, `@RequestParam`, `@NotBlank`, `@Size`. Trong cấu hình MVC 6.1+, ràng buộc trực tiếp trên argument kích hoạt method validation của MVC và có thể sinh `HandlerMethodValidationException` khi input vi phạm.

**Không gắn `@Validated` cấp class cho controller nếu bạn muốn cơ chế MVC tích hợp mới quản lý method validation.** Tài liệu Spring khuyến nghị bỏ class-level `@Validated` khỏi controller để dùng built-in MVC method validation. Nếu để `@Validated` ở class, method validation có thể chuyển sang AOP proxy và có khác biệt về loại exception/đường xử lý.

Điều này không thay đổi yêu cầu `@Validated` đối với **service-level method validation bằng AOP** ở các phần trước.

### 9.2. Phân biệt lỗi DTO và lỗi method

Spring MVC có thể báo các exception khác nhau theo chữ ký handler:

| Trường hợp | Điểm kích hoạt | Exception thường gặp |
|---|---|---|
| `@Valid @RequestBody SomeDto dto`, không có constraint trực tiếp khác yêu cầu method validation | Validation một object sau argument binding | `MethodArgumentNotValidException` |
| Handler có `@NotBlank`, `@Min`, `@Size` trực tiếp trên parameter, hoặc constraint trên method return | MVC 6.1+ built-in method validation | `HandlerMethodValidationException` |
| Service bean `@Validated`, method call qua AOP proxy | Spring AOP + `MethodValidationInterceptor` | Mặc định `ConstraintViolationException` |
| Service AOP được cấu hình `setAdaptConstraintViolations(true)` | Spring adapter chuyển lỗi Jakarta sang Spring result | `MethodValidationException` |

`@Valid` **không phải constraint**; nếu dùng một mình trên DTO, nó thường yêu cầu validation nested object, không tự chuyển handler sang method validation. Khi đặt thêm `@NotNull` trực tiếp trên parameter, MVC có thể chọn đường method validation bao gồm cả nested constraints.

Đừng viết một handler chỉ bắt `ConstraintViolationException` rồi cho rằng mọi lỗi của MVC sẽ đi qua đó. Ở controller MVC 6.1+, có thể cần xử lý cả `MethodArgumentNotValidException` và `HandlerMethodValidationException`, chẳng hạn trong `@ControllerAdvice`.

### 9.3. Áp dụng hợp lý theo tầng

- Ở **HTTP boundary**, để Spring MVC bind và validate request DTO theo cơ chế của nó; trả lỗi HTTP có cấu trúc.
- Ở **service boundary**, `@Validated` + AOP method validation giúp bảo vệ các lời gọi đến từ nhiều caller: controller, scheduler, messaging consumer, CLI, service khác.
- Trong **domain invariant** hoặc những object được tạo ngoài Spring, dùng logic bất biến rõ ràng hoặc gọi Jakarta `Validator` trực tiếp; không dựa vào proxy nếu object không đi qua container.

Method validation ở service không thay thế kiểm tra quyền hay bảo đảm mọi side effect đã được rollback khi return-value validation thất bại.

## 10. Ngoại lệ của Spring method validation và cách xử lý

### 10.1. Mặc định: `ConstraintViolationException`

Trong đường AOP cổ điển, nếu `ExecutableValidator` phát hiện vi phạm, interceptor mặc định ném `jakarta.validation.ConstraintViolationException`. Exception chứa `getConstraintViolations()` để đọc:

~~~java
try {
    codeService.normalize("xy");
} catch (jakarta.validation.ConstraintViolationException ex) {
    for (var violation : ex.getConstraintViolations()) {
        System.out.println(violation.getPropertyPath());
        System.out.println(violation.getMessage());
    }
}
~~~

Đây là đoạn code trong một component đã inject `codeService` và dùng đường AOP mặc định. `getPropertyPath()` của method validation có thể chứa method name và parameter/return-value nodes, khác với lỗi property thuần. Đừng hard-code tên `arg0` hoặc thứ tự tập vi phạm làm hợp đồng public; provider có thể dùng parameter name provider và metadata khác nhau.

### 10.2. Tùy chọn: chuyển sang `MethodValidationException`

Từ Spring Framework 6.1, `MethodValidationPostProcessor` có tùy chọn:

~~~java
@Configuration
public class CustomMethodValidationConfiguration {

    @Bean
    public static MethodValidationPostProcessor
            methodValidationPostProcessor() {

        MethodValidationPostProcessor processor =
            new MethodValidationPostProcessor();

        processor.setAdaptConstraintViolations(true);
        return processor;
    }
}
~~~

Đây là cấu hình **thay thế**, không dùng đồng thời với một post-processor trùng chức năng. Import `org.springframework.validation.beanvalidation.MethodValidationPostProcessor`, `org.springframework.context.annotation.Bean` và `Configuration` khi đặt vào project riêng.

Khi bật option, Spring có thể chuyển lỗi sang `MethodValidationException` với kết quả theo `MethodValidationResult`, `ParameterValidationResult` và `MessageSourceResolvable`, thuận lợi cho một số cơ chế xây thông báo của Spring. Các ví dụ bắt `ConstraintViolationException` trong phần 4 và phần 5 được viết cho **default mode**; nếu thay option, cập nhật test và exception handling.

`MethodValidationException` của service AOP khác `HandlerMethodValidationException` của built-in MVC handler validation.

## 11. Validation groups, thứ tự advisor và transaction

Một bean có thể có cả `@Validated`, `@Transactional`, `@Async`, `@Cacheable`. Khi đó tồn tại nhiều interceptor/advisor:

~~~text
Caller
  |
  v
AOP proxy (chuỗi advisor)
  |-- Method validation advisor
  |-- Transaction advisor
  |-- Caching / other advisors
  v
Target method
~~~

Thứ tự minh họa ở sơ đồ **không phải bảo đảm thứ tự thực tế**. Cấu hình ordering thay đổi các khả năng quan trọng:

- Nếu parameter validation chạy **ngoài** transaction, dữ liệu sai có thể bị chặn trước khi mở transaction.
- Nếu return-value validation diễn ra **ngoài** transaction, giao dịch có thể đã commit trước khi exception validation bị ném.
- Nếu return-value validation diễn ra **trong** transaction và exception làm transaction rollback, kết quả có thể khác.
- Nếu call bị cache advisor trả về mà không chạy target, kết quả có được validate hay không phụ thuộc vị trí validation advisor trong chain.

Vì thế, đừng hứa rằng “return validation luôn rollback transaction” hoặc “method validation luôn chạy trước mọi business advice”. Với hành vi có tác động dữ liệu, thiết kế transaction boundary rõ ràng và kiểm thử **cấu hình AOP advisor thực tế**.

Các constraint parameter thường thể hiện *precondition*, còn constraint return value thể hiện *postcondition*. Postcondition có giá trị quan sát và kiểm tra hợp đồng, nhưng nó không tự hoàn tác nghiệp vụ đã thực thi.

## 12. Chẩn đoán khi annotation tồn tại mà method vẫn chạy với dữ liệu sai

Kiểm tra theo thứ tự sau:

1. **Có Jakarta Validation provider chưa?** `spring-boot-starter-validation` hoặc provider tương đương phải có; annotation API riêng lẻ chưa đủ.
2. **Bean có thật do Spring quản lý không?** Có `@Service`/`@Component` và component scan hoặc bean declaration? Tránh `new`.
3. **Có `@Validated` trên target class chưa?** Với Spring AOP method validation mặc định cho service, đây là dấu hiệu kích hoạt. Import đúng package của Spring.
4. **Method có constraint thật không?** `@NotBlank`/`@Size` trên tham số/return value hoặc `@Valid` cascade hợp lệ; đừng dùng một annotation sai kiểu dữ liệu.
5. **Có method-validation post-processor không?** Boot auto-config hay bean `MethodValidationPostProcessor` trong Spring thuần; kiểm tra có bị custom config thay thế không.
6. **Caller có đi qua proxy không?** Dùng `AopUtils.isAopProxy(bean)`; kiểm tra self-invocation, object tự tạo và reference không do Spring cấp.
7. **Proxy type cho phép intercept method không?** Kiểm tra interface với JDK proxy, `final`/`private` với class-based proxy, class visibility.
8. **Group nào đang được đánh giá?** `@Validated(SomeGroup.class)` có thể không gồm constraint thuộc `Default`; nhóm của `@NotBlank` không tự lan mọi nơi.
9. **Đang ở Spring MVC 6.1+ không?** Controller có built-in method validation riêng; nếu đặt class-level `@Validated`, có thể rẽ sang AOP proxy.
10. **Exception được xử lý ở đâu?** Nếu bên ngoài đang catch/swallow exception hoặc chuyển đổi exception, kiểm tra service method contract và HTTP exception handler.
11. **Có nhiều advisor không?** Xác minh tương tác transaction/cache/async và các post-processors trước khi suy ra thứ tự.
12. **Có vi phạm thật không?** `@NotNull` chấp nhận chuỗi rỗng nhưng `@NotBlank` không; `@Size(min=3)` đếm độ dài chuỗi đầu vào trước khi logic method thay đổi nó.

Bảng tình huống nhanh:

| Hiện tượng | Nguyên nhân thường gặp | Hướng giải quyết |
|---|---|---|
| `normalize("xy")` không ném lỗi khi inject bean | Provider/`@Validated`/post-processor chưa đúng hoặc bean không được proxy | Kiểm tra dependencies, context và `AopUtils` |
| Gọi từ bean khác thì lỗi, gọi bằng `this.normalize` thì không | Self-invocation bypass advice | Tách boundary thành bean được inject, rồi gọi qua proxy |
| Gọi bằng `new CodeService()` không validate | Đối tượng không do Spring tạo | Dùng Spring bean hoặc gọi Jakarta `Validator` programmatic |
| `private`/`final` method không bị chặn | Giới hạn khả năng proxy/advice | Thiết kế boundary public và có thể intercept được |
| Runtime cast/injection lỗi với JDK proxy | Bean được expose qua interface, không phải subtype concrete | Inject interface phù hợp hoặc cấu hình proxy type có chủ ý |
| Thấy `ConstraintViolationException` thay vì lỗi MVC | Validation qua service AOP, không phải built-in MVC | Xử lý exception theo boundary và cơ chế thực tế |
| Thấy `HandlerMethodValidationException` ở controller | Spring MVC 6.1+ built-in method validation | Xử lý loại lỗi MVC tương ứng |
| Method hợp lệ nhưng return sai bị exception | Có constraint trên return value | Điều chỉnh return logic; xem xét side effect/transaction ordering |
| Chỉ một số constraint chạy | Group selection hoặc kiểu constraint | Kiểm tra `groups`, `@Validated(...)` và annotation targets |
| App có hai method validation post-processor | Cấu hình thủ công trùng Boot auto-config | Đơn giản hóa cấu hình còn một cơ chế chủ đích |
| Thấy lỗi override constraint ở subclass | Quy tắc inheritance của Jakarta Validation bị vi phạm | Sửa method contract trên interface/superclass |
| Direct test thành công nhưng integration thất bại | Test không sử dụng Spring proxy/provider đúng | Kiểm thử bean từ ApplicationContext |

## 13. Khi nào dùng AOP method validation và khi nào không?

**Nên dùng** cho method public tại service boundary được gọi bởi các Spring bean khác; hợp đồng đầu vào/đầu ra biểu đạt được bằng Jakarta Validation; cần áp constraint nhất quán qua nhiều caller mà không lặp câu lệnh `validator.validate(...)`.

**Cân nhắc cách khác** khi object không do Spring quản lý, đoạn xử lý xảy ra trong constructor/private helper, self-invocation là thiết kế thường xuyên, hoặc cần chứng minh điều kiện nghiệp vụ phụ thuộc transaction/state tại một thời điểm cụ thể. Khi đó có thể dùng validation programmatic hoặc method/domain service với boundary rõ ràng.

AOP method validation phát hiện vi phạm theo declarative contract. Nó không tự thay việc kiểm tra nghiệp vụ phức tạp, không tự cung cấp transaction/authorization và không đảm bảo mọi luồng gọi nội bộ đều được kiểm tra.

## 14. Câu hỏi luyện tập

**Câu 1.** Vì sao Spring biết `@NotBlank` trên tham số method nhưng một lời gọi Java bình thường vẫn có thể chấp nhận chuỗi rỗng?

Vì annotation là metadata. Phải có `ExecutableValidator` được gọi bởi interceptor hoặc code chủ động. AOP chỉ can thiệp khi lời gọi **đi qua Spring proxy**.

**Câu 2.** `@Validated` và `@Valid` khác nhau thế nào trong service AOP?

`@Validated` cấp class giúp Spring method-validation post-processor chọn target và có thể chỉ định group. `@Valid` báo cho Jakarta Validation cascade vào object ở parameter/return/property; nó không tạo Spring AOP proxy một mình.

**Câu 3.** Trong demo, vì sao `codeService.normalize("xy")` bị chặn nhưng `codeService.callInternally("xy")` lại trả `XY`?

Lời gọi đầu đi qua proxy và bị `@Size(min=3)` chặn. Lời gọi thứ hai vào `callInternally` qua proxy, nhưng bên trong gọi `this.normalize` trực tiếp trên target và bỏ qua interceptor của `normalize`.

**Câu 4.** Với method được đánh dấu `@NotBlank` trên return value, Spring kiểm tra trước hay sau khi chạy body?

Sau khi method trả về bình thường. Nếu constraint sai, caller nhận exception; side effect trước đó không được AOP validation tự hủy.

**Câu 5.** Vì sao controller Spring MVC 6.1+ có thể ném `HandlerMethodValidationException` trong khi service `@Validated` thường ném `ConstraintViolationException`?

Controller có built-in method validation của MVC, còn service đang dùng AOP `MethodValidationInterceptor`; đây là hai cơ chế kích hoạt và chuyển đổi lỗi khác nhau.

**Câu 6.** Thêm `@NotBlank` vào một `private` helper có bảo đảm được validate khi gọi từ public service method không?

Không, vì proxy-based Spring AOP không chặn private method. Dùng boundary public qua bean khác hoặc gọi validation programmatic ở vị trí thích hợp.

**Câu 7.** Chỉ nhìn thấy bean `@Validated` có đủ khẳng định method validation hoạt động không?

Chưa. Phải có provider, post-processor, proxy/advisor, method phù hợp và invocation thực sự đi qua proxy; nên chứng minh bằng integration test.

## 15. Checklist triển khai và kiểm chứng

- [ ] Chọn đúng Jakarta Validation API/provider tương ứng Spring Framework 6 / Spring Boot 3.
- [ ] Service là Spring-managed bean; khai báo Spring `@Validated` ở cấp class cho AOP method validation thông dụng.
- [ ] Constraint nằm đúng vị trí trên parameter/return; kết hợp `@Valid` cho cascade và `@NotNull` nếu cần chống null.
- [ ] Có `MethodValidationPostProcessor`, do Boot auto-config hoặc cấu hình Spring rõ ràng.
- [ ] Caller inject bean và gọi qua proxy; không dựa vào `new` hay self-invocation.
- [ ] Method có khả năng được chặn theo JDK/CGLIB proxy, tránh `private`/`final` ở boundary cần validation.
- [ ] Hiểu mặc định `ConstraintViolationException` và tùy chọn `MethodValidationException`.
- [ ] Tách built-in Spring MVC 6.1+ method validation khỏi service AOP, xử lý đúng loại exception.
- [ ] Kiểm thử cả input sai, input đúng, return sai, self-invocation và các group liên quan.
- [ ] Khi phối hợp transaction/cache/async, kiểm tra advisor ordering và side effects thay vì suy luận từ thứ tự annotation.

**Ghi nhớ:** `@Validated` giúp Spring **chọn bean**, `MethodValidationPostProcessor` tạo **advisor/proxy**, `MethodValidationInterceptor` thực thi **Jakarta `ExecutableValidator` trước và sau method**, và **caller phải đi qua proxy** để advice có hiệu lực. Self-invocation là giới hạn trung tâm; còn Spring MVC 6.1+ có cơ chế method validation riêng cho controller.

## Tài liệu tham khảo chính thức

- [Spring Framework — Java Bean Validation: Spring-driven Method Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Proxying Mechanisms và self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Spring API — MethodValidationPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html)
- [Spring API — MethodValidationInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationInterceptor.html)
- [Jakarta Validation — Method and Constructor Validation](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#methodandconstructorvalidation)
