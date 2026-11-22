# Annotation trên interface, phương thức triển khai và lớp trong Spring AOP

## 1. Vì sao vị trí đặt annotation ảnh hưởng đến advice?

Trong Spring AOP, annotation có thể nằm ở **phương thức của interface**, **phương thức triển khai**, **lớp triển khai**, hoặc **chính interface**. Tuy cùng ghi một annotation tùy chỉnh, bốn vị trí này không tương đương khi viết pointcut và khi đọc metadata của lời gọi.

Lý do cốt lõi nằm ở ba lớp cơ chế:

1. Spring AOP dùng **proxy** để chặn các method execution trên Spring bean. Lời gọi cần đi qua proxy và pointcut phải khớp.
2. **Java reflection không tự sao chép annotation** từ interface sang lớp hoặc phương thức triển khai. `@Override` không thay đổi quy tắc này.
3. `@annotation`, `@within`, `@target` xét những vị trí khác nhau; cách một framework cụ thể tra cứu thêm metadata ở interface không đồng nghĩa Java có annotation inheritance cho interface.

Bài này tập trung vào **việc chọn và đọc annotation cho Spring AOP**, với ví dụ chạy được và kết quả quan sát cụ thể. Các khái niệm annotation Java thuần túy chỉ được nhắc đến tại điểm cần thiết để giải thích kết quả trong Spring.

### Các vị trí thường gặp

~~~java
// (A) Annotation trên phương thức của interface
interface PaymentPort {
    @Tracked("interface-method")
    void pay();
}

// (B) Annotation trên phương thức triển khai
class PaymentService implements PaymentPort {
    @Override
    @Tracked("implementation-method")
    public void pay() { }
}

// (C) Annotation trên lớp triển khai
@Tracked("implementation-class")
class ShippingService {
    public void ship() { }
}

// (D) Annotation trên chính interface
@Tracked("interface-type")
interface ShippingPort {
    void ship();
}
~~~

Đây là **đoạn minh họa vị trí** (chưa phải chương trình Java độc lập). Annotation `Tracked` phải có `@Retention(RUNTIME)` và `@Target({METHOD, TYPE})` nếu muốn đọc được bằng reflection lúc chạy.

## 2. Phân biệt matching pointcut với tra cứu annotation

### 2.1. Ba expression khác nhau

Spring AOP hỗ trợ các pointcut designator liên quan đến annotation:

| Expression | Ý nghĩa trong Spring AOP | Câu hỏi đặt ra |
| --- | --- | --- |
| `@annotation(com.example.Tracked)` | Khớp method execution có annotation trên phương thức làm subject của join point | Lời gọi method này có annotation phù hợp không? |
| `@within(com.example.Tracked)` | Giới hạn vào các method execution nằm trong kiểu được annotation | Phương thức được khai báo trong type được đánh dấu không? |
| `@target(com.example.Tracked)` | Kiểm tra annotation trên lớp của đối tượng target thực thi | Lớp target tại runtime có annotation phù hợp không? |

Với `execution(* ...)`, bạn chọn phương thức theo chữ ký; còn các biểu thức trên chọn dựa vào annotation. **Đừng giả định `@annotation` tự đồng nghĩa với “quét annotation trên method triển khai, mọi interface, lớp và lớp cha”**.

Ví dụ muốn đo mọi public method của các đối tượng có annotation trên **target class**:

~~~java
@Around("@target(com.example.annotationdemo.Tracked) && execution(public * *(..))")
public Object aroundTargetClass(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
~~~

Đoạn trên minh họa expression; nó cần được đặt trong một Spring `@Aspect` hợp lệ. `@target` không có nghĩa là lấy annotation gắn trên interface bằng cách “kế thừa” nó sang target class.

### 2.2. Hai kiểu proxy tạo ra những khác biệt quan trọng

| Yếu tố | JDK dynamic proxy | Class-based proxy (CGLIB trong Spring) |
| --- | --- | --- |
| Kiểu object client thường nhìn thấy | Proxy triển khai interface | Proxy kế thừa lớp target |
| Method client gọi được để advice | Public method phơi ra qua proxied interface | Các method có thể override/intercept; thông thường nên dùng public method |
| Chữ ký method thu được từ `MethodSignature.getMethod()` | Có thể là method khai báo ở interface | Có thể là method của lớp triển khai |
| Tìm annotation chỉ từ method của chữ ký proxy | Có thể bỏ qua annotation chỉ nằm ở implementation | Có thể bỏ qua annotation chỉ nằm trên interface |
| Self-invocation `this.method()` | Không qua proxy | Không qua proxy |

Spring Boot 3.x thông thường dùng class-based proxy mặc định cho AOP; có thể chọn JDK proxy bằng `spring.aop.proxy-target-class=false` nếu bean có interface phù hợp. Spring Framework thuần có thể có mặc định khác theo cấu hình. Không cần đoán proxy type: có thể dùng `AopUtils.isJdkDynamicProxy(bean)` hoặc `AopUtils.isCglibProxy(bean)` khi kiểm tra.

Lưu ý: `MethodSignature.getMethod()` cung cấp method tương ứng chữ ký của join point. Để nghiên cứu annotation của implementation, dùng `AopUtils.getMostSpecificMethod(signature.getMethod(), targetClass)` và kiểm tra trực tiếp class của **target**, không dựa riêng vào proxy class.

### 2.3. Java `@Inherited` không giải quyết chuyện interface method

`@Inherited` chỉ có ý nghĩa kế thừa annotation **trên lớp** theo chuỗi superclass trong cơ chế tra cứu của Java; nó không làm interface annotation trở thành annotation được khai báo trên lớp triển khai, và cũng không áp dụng cho annotation trên phương thức overridden. Không được xem `getDeclaredAnnotation()` trên implementation method như thể nó tự đọc annotation từ interface method.

Một số thành phần Spring như `@Transactional` dùng **cơ chế tìm metadata chuyên biệt của chính thành phần đó**, có thể hỗ trợ annotation khai báo trên interface trong chế độ proxy. Không suy diễn rằng custom `@Aspect` với `@annotation` có cùng chính sách tra cứu như transaction interceptor. Khi cần bảo đảm, hãy định nghĩa chính sách vị trí và kiểm chứng ở đúng phiên bản Spring đang dùng.

## 3. Quy tắc đề xuất để dùng annotation tùy chỉnh nhất quán

Giả sử nghiệp vụ muốn cho phép người viết annotation ở cả bốn vị trí. Có thể định nghĩa thứ tự ưu tiên rõ ràng:

1. Annotation trực tiếp trên **implementation method**.
2. Annotation trên **interface method** tương ứng.
3. Annotation trên **implementation class**.
4. Annotation trên **interface type**.

Đây là **quy tắc do ứng dụng tự chọn**, không phải thứ tự ưu tiên mặc định của mọi Spring annotation. Nó tránh tình huống annotation chung trên class ghi đè cấu hình cụ thể ở method, đồng thời vẫn hỗ trợ interface làm nơi khai báo contract.

Nếu nhiều interface có cùng signature nhưng mang annotation khác nhau, cần chính sách xung đột (ví dụ báo lỗi khởi động) hoặc thứ tự ưu tiên được công bố. Không nên phụ thuộc vào thứ tự `Class.getInterfaces()` để quyết định nghiệp vụ khi cấu hình mâu thuẫn. Ví dụ thực hành bên dưới mỗi service chỉ triển khai một interface, nên không có xung đột đó.

Một điểm đặc biệt: **advice phải được chọn trước thì mới thực hiện được resolver bên trong advice**. Nếu aspect chỉ dùng `@annotation(Tracked)` mà expression không khớp tại proxy boundary, việc viết mã reflection đầy đủ bên trong advice vẫn không làm method đó được intercept. Cách an toàn khi muốn tự định nghĩa chính sách bốn vị trí là chọn phạm vi method bằng `execution` (và giới hạn package/bean cần thiết), sau đó tự tra cứu annotation trong advice.

## 4. Chương trình Spring Boot chạy được: đủ cả bốn vị trí

Ví dụ dùng Java 17, Spring Boot 3.3.x và Spring AOP. Mỗi service có một method `execute()`, được đánh dấu ở **đúng một** vị trí, nhằm tránh nhầm lẫn khi quan sát. Advice dùng `execution` để chặn method rồi tìm annotation theo thứ tự trên.

Cấu trúc thư mục:

~~~text
pom.xml
src/main/java/com/example/annotationdemo/
    DemoApplication.java
    Tracked.java
    Services.java
    TrackedAspect.java
~~~

### 4.1. Dependencies

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-annotation-aop</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-aop` cung cấp Spring AOP cùng các thành phần AspectJ cần thiết để Spring phân tích pointcut expression. Ví dụ không dùng AspectJ compile-time weaving.

### 4.2. Annotation chỉ lưu metadata

`src/main/java/com/example/annotationdemo/Tracked.java`:

~~~java
package com.example.annotationdemo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
public @interface Tracked {
    String value();
}
~~~

Annotation này không tự làm advice chạy. Spring phải có aspect được đăng ký và pointcut khớp lời gọi qua proxy thì metadata mới được sử dụng.

### 4.3. Bốn interface và bốn service

`src/main/java/com/example/annotationdemo/Services.java`:

~~~java
package com.example.annotationdemo;

import org.springframework.stereotype.Service;

// Tình huống 1: annotation tại interface method
interface InterfaceMethodPort {
    @Tracked("interface-method")
    String execute();
}

@Service
class InterfaceMethodService implements InterfaceMethodPort {
    @Override
    public String execute() {
        return "A";
    }
}

// Tình huống 2: annotation tại implementation method
interface ImplementationMethodPort {
    String execute();
}

@Service
class ImplementationMethodService implements ImplementationMethodPort {
    @Override
    @Tracked("implementation-method")
    public String execute() {
        return "B";
    }
}

// Tình huống 3: annotation tại implementation class
interface ClassLevelPort {
    String execute();
}

@Service
@Tracked("implementation-class")
class ClassLevelService implements ClassLevelPort {
    @Override
    public String execute() {
        return "C";
    }
}

// Tình huống 4: annotation tại interface type
@Tracked("interface-type")
interface InterfaceTypePort {
    String execute();
}

@Service
class InterfaceTypeService implements InterfaceTypePort {
    @Override
    public String execute() {
        return "D";
    }
}
~~~

Các interface và class trong tệp này có quyền truy cập package-private vì ứng dụng demo và aspect cùng package. Các method triển khai `execute()` đều `public`, không `final`; mỗi bean có đúng một interface. Spring quản lý các service thông qua `@Service`, nên những lời gọi nhận bean qua dependency injection có thể đi qua Spring AOP proxy.

### 4.4. Aspect tra cứu metadata ở bốn vị trí

`src/main/java/com/example/annotationdemo/TrackedAspect.java`:

~~~java
package com.example.annotationdemo;

import java.lang.reflect.Method;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.aop.support.AopUtils;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TrackedAspect {

    @Around("execution(public * com.example.annotationdemo..*.execute(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        MethodSignature signature = (MethodSignature) pjp.getSignature();
        Class<?> targetClass = pjp.getTarget().getClass();

        Method implementationMethod =
                AopUtils.getMostSpecificMethod(signature.getMethod(), targetClass);

        Tracked annotation = resolve(implementationMethod, targetClass);

        if (annotation != null) {
            System.out.println("tracked=" + annotation.value());
        }

        return pjp.proceed();
    }

    private Tracked resolve(Method method, Class<?> targetClass) {
        // 1. Annotation khai báo trực tiếp ở implementation method
        Tracked found = method.getDeclaredAnnotation(Tracked.class);
        if (found != null) {
            return found;
        }

        // 2. Annotation ở method tương ứng trên direct interface
        for (Class<?> contract : targetClass.getInterfaces()) {
            try {
                Method interfaceMethod = contract.getMethod(
                        method.getName(), method.getParameterTypes());

                found = interfaceMethod.getDeclaredAnnotation(Tracked.class);
                if (found != null) {
                    return found;
                }
            } catch (NoSuchMethodException ignored) {
                // Interface này không khai báo/không kế thừa method tương ứng.
            }
        }

        // 3. Annotation khai báo trực tiếp trên implementation class
        found = targetClass.getDeclaredAnnotation(Tracked.class);
        if (found != null) {
            return found;
        }

        // 4. Annotation khai báo trực tiếp trên interface type
        for (Class<?> contract : targetClass.getInterfaces()) {
            found = contract.getDeclaredAnnotation(Tracked.class);
            if (found != null) {
                return found;
            }
        }

        return null;
    }
}
~~~

**Tại sao dùng `execution`?** Biểu thức `execution(public * com.example.annotationdemo..*.execute(..))` bắt các method public tên `execute` trong package demo (hoặc các package con), không đòi hỏi Spring phải tự tìm `@Tracked` tại một vị trí nhất định lúc match pointcut. Trong advice, resolver mới quyết định annotation nào có hiệu lực.

**Tại sao phải tìm `implementationMethod`?** Khi gọi qua JDK proxy, `signature.getMethod()` có thể là method của interface, vốn không chứa annotation được đặt riêng tại implementation method. `AopUtils.getMostSpecificMethod(...)` chuyển về method cụ thể tương ứng của target class để đọc chính xác annotation khai báo tại đó.

Đây là **resolver có chủ ý giới hạn**: xử lý direct interface, method không generic/bridge phức tạp, và một annotation mỗi vị trí. Với interface kế thừa nhiều tầng, generic bridge method, meta-annotation, hoặc nhiều interface cùng khai báo một signature, hãy dùng chính sách rõ ràng và API như `BridgeMethodResolver`/`AnnotatedElementUtils` phù hợp. Không biến ví dụ tối giản thành cơ chế tra cứu chung cho mọi Spring annotation.

### 4.5. Chạy và đọc kết quả

`src/main/java/com/example/annotationdemo/DemoApplication.java`:

~~~java
package com.example.annotationdemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner examples(
            InterfaceMethodPort fromInterfaceMethod,
            ImplementationMethodPort fromImplementationMethod,
            ClassLevelPort fromClass,
            InterfaceTypePort fromInterfaceType) {

        return args -> {
            System.out.println("== Interface method ==");
            System.out.println("result=" + fromInterfaceMethod.execute());

            System.out.println("== Implementation method ==");
            System.out.println("result=" + fromImplementationMethod.execute());

            System.out.println("== Implementation class ==");
            System.out.println("result=" + fromClass.execute());

            System.out.println("== Interface type ==");
            System.out.println("result=" + fromInterfaceType.execute());
        };
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Bỏ qua log khởi động Spring Boot, kết quả demo là:

~~~text
== Interface method ==
tracked=interface-method
result=A
== Implementation method ==
tracked=implementation-method
result=B
== Implementation class ==
tracked=implementation-class
result=C
== Interface type ==
tracked=interface-type
result=D
~~~

Mỗi lời gọi `execute()` qua proxy vào advice một lần. Resolver biết cách tra annotation ở cả bốn vị trí theo thứ tự định nghĩa, nên các dòng `tracked=...` xuất hiện tương ứng. `proceed()` vẫn trả về đúng chuỗi `A`, `B`, `C`, `D` từ service.

Muốn thử JDK proxy trong Spring Boot, chạy lại với thuộc tính sau (hoặc đặt vào `application.properties`):

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--spring.aop.proxy-target-class=false
~~~

Các bean demo đều có interface nên có thể dùng interface-based proxies. Vì `CommandLineRunner` nhận dependency theo **interface**, và aspect sử dụng `execution` rồi tự phân giải annotation từ target, **các dòng nghiệp vụ ở trên vẫn được kỳ vọng như nhau**. Để xem chính xác loại proxy, có thể thêm kiểm tra bằng `AopUtils.isJdkDynamicProxy(...)` hoặc `AopUtils.isCglibProxy(...)` trong runner. Không ép inject concrete class khi chọn JDK proxy: JDK proxy không phải subclass của implementation.

## 5. Nếu annotation xuất hiện ở nhiều vị trí cùng lúc?

Xét trường hợp method trên interface có `@Tracked("contract")`, implementation method có `@Tracked("implementation")`, và implementation class có `@Tracked("service-default")`.

Với resolver ở mục 4, kết quả là `tracked=implementation` vì implementation method được kiểm tra trước. Nếu bỏ annotation trên implementation method thì resolver trả `contract`; nếu bỏ tiếp annotation trên interface method thì trả `service-default`.

Đây là **chính sách ưu tiên riêng của ví dụ**, có thể thay đổi theo yêu cầu hệ thống. Một chính sách khác có thể ưu tiên annotation của implementation class hơn interface method để áp một default cho cả service. Dù chọn gì, nên dùng test mô tả rõ thứ tự vì không có một bảng ưu tiên chung áp dụng cho tất cả AOP annotation của Spring.

Không nên tổng hợp hai cấu hình trái ngược tùy ý (ví dụ `@Tracked(value="fast")` ở interface và `@Tracked(value="slow")` ở implementation) mà không có chính sách xung đột. Một resolver cho production có thể từ chối cấu hình mơ hồ tại startup, giúp phát hiện thay đổi contract sớm.

## 6. Điểm khác giữa custom `@Aspect` và annotation tích hợp của Spring

Ví dụ điển hình là `@Transactional`. Spring có `TransactionAttributeSource` để tìm metadata transaction ở method và class, bao gồm những trường hợp interface method được hỗ trợ trong **proxy mode**. Điều đó là hành vi của **hạ tầng transaction**, không phải vì mọi annotation Java tự được kế thừa hay mọi `@annotation` pointcut đều tự động dùng resolver như vậy.

Khi thiết kế annotation của riêng mình, hãy tách hai bước:

- **Bước chọn join point:** pointcut xác định lời gọi nào có thể chạy advice.
- **Bước chọn metadata:** logic resolver xác định annotation nào được đọc, vị trí nào ưu tiên và cách xử lý xung đột.

Trong ứng dụng đơn giản chỉ chấp nhận annotation trên implementation method, biểu thức `@annotation(com.example.annotationdemo.Tracked)` có thể là cách gọn hơn. Nếu hợp đồng API yêu cầu annotation trên interface **và** hỗ trợ chuyển đổi JDK/CGLIB proxy, đừng chỉ dựa vào một reflection call trên `MethodSignature.getMethod()`; thử chính xác các trường hợp mong muốn.

Với meta-annotation/composed annotation (ví dụ một `@AuditedCommand` được đánh dấu `@Tracked`), `getDeclaredAnnotation(Tracked.class)` sẽ không giải quyết toàn bộ mô hình Spring merged annotations. Khi đó có thể dùng `AnnotatedElementUtils.findMergedAnnotation(...)` hoặc `MergedAnnotations`, nhưng cần chủ động quy định thứ tự giữa method, type và interface thay vì giả định hai API này thay thế toàn bộ resolver.

## 7. Các lỗi thường gặp và cách kiểm tra

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Gắn `@Tracked` trên interface method nhưng không có advice | Pointcut không khớp tại method execution do proxy thấy, hoặc lời gọi không qua proxy | Xác minh AOP được bật, proxy tồn tại và pointcut match; thử expression `execution` được giới hạn rõ |
| Advice chạy nhưng không tìm được annotation ở implementation method | Chỉ đọc method của interface từ `MethodSignature` | Lấy most-specific method trên target class trước |
| Annotation class không có trên method | Class annotation không đồng nghĩa method có annotation trực tiếp | Kiểm tra class riêng; chọn `@target`/`@within` hoặc resolver tùy mục đích |
| Interface type được đánh dấu nhưng target class không có annotation | Java không kế thừa annotation từ interface sang class | Tra interface type nếu policy cần |
| Advice chạy khi JDK proxy nhưng vắng khi đổi cấu hình proxy | Pointcut, visibility, exposed method và metadata source khác nhau | Test cả hai chế độ, kiểm tra method public/interface |
| Inner method có annotation nhưng không bị chặn | `this.inner()` gọi trực tiếp trong cùng target | Tách sang bean khác để lời gọi đi qua proxy |
| Dùng `@Inherited` mà interface method vẫn không được nhận diện | `@Inherited` không áp dụng cho method hoặc interface inheritance | Tra interface method tường minh |
| Nhiều interface cho kết quả phụ thuộc cấu trúc kế thừa | Resolver chưa có chính sách conflict | Khai báo precedence hoặc fail-fast; test interface hierarchy |
| Gắn annotation lên `private`/`final` method nhưng không có advice | Proxy không thể intercept phương thức phù hợp | Dùng public method qua proxy, hoặc thay thiết kế phù hợp |

Để xác minh thay vì suy đoán: lấy bean từ ApplicationContext, kiểm tra bằng `AopUtils.isAopProxy(bean)`, phân biệt JDK/CGLIB, xác nhận phương thức công khai được gọi **từ bean khác**, rồi kiểm tra pointcut có match và resolver đã tìm tới đúng nơi đặt annotation chưa.

## 8. Checklist khi đưa annotation custom vào dự án

1. Xác định rõ `@Target`, `@Retention(RUNTIME)`, tên và dữ liệu annotation; vị trí nào là contract công khai.
2. Chỉ rõ annotation được phép nằm ở interface method, implementation method, class và/hoặc interface type.
3. Chọn `@annotation`, `@within`, `@target` nếu vị trí đơn nhất đáp ứng yêu cầu; nếu cần chính sách hợp nhất nhiều vị trí thì giới hạn bằng `execution` và dùng resolver có kiểm thử.
4. Định nghĩa precedence và cách xử lý nhiều interface, method overload, generic bridge, inheritance và composed annotation.
5. Kiểm chứng đường gọi qua proxy trong cả cấu hình JDK/class-based đang được hỗ trợ; tránh self-invocation và các method không intercept được.
6. Kiểm tra advice giữ nguyên return value/exception của `proceed()`, đồng thời không tạo chi phí reflection lớn ở hot path. Có thể cache kết quả tra metadata theo method + target class, sau khi bảo đảm khóa cache phản ánh đúng chính sách.
7. Nếu annotation ảnh hưởng tới authorization, transaction hay bảo đảm nghiệp vụ, viết integration test cho các trường hợp khớp và không khớp; không coi log demo là bằng chứng đầy đủ về policy.

## 9. Kết luận

Trong Spring AOP, vị trí đặt annotation và đường gọi qua proxy là hai quyết định riêng. **Annotation trên interface không tự trở thành annotation trên implementation**, còn `@annotation`, `@within`, `@target` có ý nghĩa matching khác nhau. Khi cần hỗ trợ đồng thời interface method, implementation method, implementation class và interface type, hãy xác định chính sách tra metadata tường minh, dùng pointcut đủ bao phủ các lời gọi được phép và kiểm chứng trên proxy thực tế.

Tham khảo chính thức:
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
