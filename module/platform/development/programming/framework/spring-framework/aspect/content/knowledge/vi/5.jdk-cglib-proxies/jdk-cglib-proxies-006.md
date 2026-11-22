# Spring AOP: phương thức private, static và lời gọi không thể ghi đè

## 1. Vấn đề: có aspect và pointcut nhưng advice vẫn không chạy

Spring AOP là cơ chế **proxy-based AOP** dành cho các lời gọi phương thức trên bean do Spring quản lý. Khi một service được bọc bằng proxy, lời gọi từ consumer đi qua proxy có thể bị advisor/advice chặn. Có những lời gọi mà proxy **không thể quan sát**, dù biểu thức pointcut nhìn qua có vẻ đúng:

- Phương thức `private` không nằm trên bề mặt phương thức có thể gọi từ bên ngoài và không thể bị subclass override.
- Phương thức `static` thuộc về class; lời gọi theo tên class không phải lời gọi instance qua Spring AOP proxy.
- Phương thức instance `final` không thể bị CGLIB subclass override; với **JDK interface proxy**, quy tắc có khác: proxy vẫn có thể chặn lời gọi thông qua method của interface, ngay cả khi implementation method là `final`.
- Class `final` không thể được CGLIB subclass để tạo proxy. Nếu class triển khai interface phù hợp, Spring có thể chọn JDK interface proxy.
- Method có visibility ngăn subclass truy cập/override, ví dụ package-private method kế thừa từ class thuộc package khác, có thể không được CGLIB advice.
- **Self-invocation** như `this.publicMethod()` bỏ qua proxy, dù method đó public và có thể override. Đây là nguyên nhân **khác** với việc method không thể override.

Cần phân biệt hai câu hỏi:

1. **Proxy có thể tạo điểm chặn cho method này không?** Phụ thuộc JDK proxy hay CGLIB, interface, visibility và khả năng override.
2. **Lời gọi cụ thể có đi qua proxy không?** Phụ thuộc reference mà caller dùng. Một method public bình thường cũng không được advice nếu target tự gọi qua `this`.

Bài này tập trung hoàn toàn vào **giới hạn trong Spring AOP** và cách xử lý khi dùng Spring IoC, dependency injection, Spring AOP proxy; không mở rộng sang giải thích AOP tổng quát.

## 2. Spring AOP chặn lời gọi ở đâu?

### 2.1. Đường gọi qua proxy

```text
Consumer (Spring bean hoặc code lấy bean từ ApplicationContext)
            |
            | service.publicOperation()
            v
        Spring AOP proxy
            |
            | kiểm tra advisor/pointcut
            v
        Interceptor / advice
            |
            v
        Target.publicOperation()
```

Target và proxy có thể là các đối tượng khác nhau. Khi bean khác inject service, Spring cấp **tham chiếu bean do container công bố**; nếu được AOP bọc, đó thường là proxy. Với một target tự tạo bằng `new` bên ngoài container, không có quá trình xuất bản Spring AOP proxy này.

### 2.2. Những đường gọi bypass proxy

```text
Target.publicOperation()
      |
      +---- this.otherPublic()   ---> target trực tiếp
      |
      +---- privateHelper()      ---> target trực tiếp
      |
      +---- finalMethod()        ---> target trực tiếp
      |
      +---- SomeClass.staticOp() ---> class, không phải proxy instance
```

**Self-invocation:** Một method đi qua proxy ở đầu luồng không có nghĩa mọi method nó gọi nội bộ cũng qua proxy. Khi target đã nhận điều khiển, lời gọi `this.otherPublic()` là lời gọi trên target, không quay lại Spring proxy.

**Khả năng override:** Riêng CGLIB tạo subclass để intercept các lời gọi phù hợp. Nó không thể override `private` và `final` methods. Nhưng một method public có thể override vẫn có thể bị bỏ qua advice do self-invocation.

**Giới hạn pointcut:** Spring AOP chỉ hỗ trợ **method execution join points trên Spring beans**, không hỗ trợ các join point kiểu `call`, `get`, `set`, constructor execution, hoặc static initialization trong cách dùng @AspectJ pointcut của Spring AOP. Một chuỗi pointcut có vẻ nhắm đến method nào đó không giúp proxy chặn một lời gọi mà proxy không nhận được.

## 3. Phương thức private: không có đường gọi qua Spring proxy

Xem service:

```java
@Service
public class AccountService {
    public void register(String id) {
        validate(id); // private method trên chính target
        System.out.println("Registered " + id);
    }

    private void validate(String id) {
        if (id.isBlank()) {
            throw new IllegalArgumentException("Empty id");
        }
    }
}
```

Đây là **fragment minh họa**, không phải ứng dụng chạy độc lập. Nếu một aspect được đặt để advice `register(...)`, lời gọi từ bean khác vào `register(...)` qua Spring proxy có thể được intercept. Nhưng `validate(...)` là `private`:

- Caller bên ngoài không thể gọi trực tiếp `validate` qua public API của service.
- JDK proxy chỉ có thể công bố các method public trên interface; `private` method của target không thuộc bề mặt này.
- CGLIB proxy subclass không thể override một private method. Do đó không thể dùng advice của Spring AOP proxy để chặn `validate()`.
- Thêm annotation vào private method hoặc viết pointcut chỉ nhắm vào method ấy **không biến** lời gọi private thành lời gọi proxy.
- Reflection gọi private method trên target cũng không tự khiến nó đi qua AOP proxy.

**Hướng xử lý:** Nếu chỉ cần kiểm tra input nội bộ, cứ giữ helper private và để advice áp dụng cho **public service boundary**. Nếu logic private thật sự cần một advice riêng như transaction/caching/audit, hãy cân nhắc đưa logic ấy thành public method của **một Spring bean khác**, sau đó inject bean đó và gọi từ service.

Ví dụ:

```java
@Service
public class RegistrationService {
    private final ValidatorService validator;

    public RegistrationService(ValidatorService validator) {
        this.validator = validator;
    }

    public void register(String id) {
        validator.validate(id); // Lời gọi qua bean được Spring inject.
    }
}

@Service
public class ValidatorService {
    public void validate(String id) {
        if (id.isBlank()) {
            throw new IllegalArgumentException("Empty id");
        }
    }
}
```

Hai class trên là fragment thiết kế, cần import `org.springframework.stereotype.Service` và đặt trong các tệp thích hợp. Lời gọi sang `ValidatorService` có thể đi qua Spring AOP proxy nếu aspect/advisor chọn method `validate`. Tách bean nên dựa trên trách nhiệm hợp lý, không tạo thêm bean chỉ để làm mất encapsulation nếu advice ở public boundary đã đủ.

## 4. Phương thức static: lời gọi gắn với class, không có instance proxy

Trong Java, `static` method được gọi theo class:

```java
public class FeeRules {
    public static long calculate(long subtotal) {
        return subtotal * 5 / 100;
    }
}
```

Lời gọi `FeeRules.calculate(1000)` không đi vào một Spring bean proxy. Dù `FeeRules` hoặc một object khác được đăng ký thành bean, static method vẫn gắn với **class**.

Với Spring AOP proxy:

- **JDK dynamic proxy** chặn các lời gọi method trên đối tượng proxy qua các interface. Static interface method không phải instance method được kế thừa bởi implementing class và không phải method trên proxy instance.
- **CGLIB proxy** là subclass của target. Static methods trong Java bị **ẩn** (method hiding), không được override đa hình; không thể dùng override interception để advice một static method.
- Annotation lên static method, hoặc `execution(* ...staticMethod(..))` trong một pointcut, không làm xuất hiện một Spring proxy interception point cho lời gọi static.
- `@Component` trên class chứa static helper không đổi cách Java dispatch lời gọi static.

Nếu muốn bổ sung logging, cache, transaction hoặc policy thông qua Spring AOP, chuyển hành vi cần intercept thành **instance method của Spring-managed bean**:

```java
@Service
public class FeeService {
    public long calculate(long subtotal) {
        return subtotal * 5 / 100;
    }
}
```

Sau đó consumer nhận `FeeService` bằng constructor injection và gọi qua reference do Spring cung cấp. Nếu static method chỉ là utility thuần, không có nhu cầu advice, giữ static là lựa chọn hoàn toàn bình thường.

**Điểm dễ hiểu sai:** Không phải “static không hoạt động trong Spring”. Static methods vẫn chạy Java bình thường; chúng chỉ không đi qua **Spring AOP proxy method interception**.

## 5. Final method và final class: khác biệt giữa JDK proxy và CGLIB

### 5.1. Với CGLIB: cần subclass và override

Spring dùng CGLIB class-based proxy khi target không có interface thích hợp hoặc cấu hình buộc dùng class proxy. Về cơ chế, proxy là một subclass của target; do đó:

- `final class` không thể bị subclass, nên không thể tạo **CGLIB proxy** cho class ấy.
- `final instance method` không thể bị subclass override, nên **không được advice qua CGLIB**.
- `private method` cũng không thể override.
- Method không thể truy cập từ subclass, ví dụ một package-private method khai báo trong supertype thuộc package khác, cũng không thể được proxy subclass intercept theo cách thông thường.

Ví dụ:

```java
public class JobService {
    public void run() {
        System.out.println("run");
    }

    public final void locked() {
        System.out.println("locked");
    }
}
```

Với CGLIB proxy, `run()` có thể advice nếu lời gọi từ bên ngoài qua proxy và advisor khớp. `locked()` vẫn chạy theo logic Java, nhưng không có advice của proxy kiểu subclass. Chỉ đổi tên pointcut không thể sửa giới hạn `final`.

Một điểm thực hành quan trọng: với proxy CGLIB, lời gọi đến method `final` có thể thực thi trực tiếp method được kế thừa trên **đối tượng proxy subclass**, không đi qua interceptor/delegation đến target như các method được override. Nếu method final truy cập mutable fields hoặc dependency đã khởi tạo ở target, behavior có thể gây bất ngờ trong một số cấu hình proxy. Đừng thiết kế nghiệp vụ dựa vào lời gọi final method trên class proxy; nếu cần advice, hãy chọn method có thể proxy hoặc đổi ranh giới bean.

### 5.2. Với JDK proxy: final method của implementation có thể được advice

JDK dynamic proxy **không phải subclass của target**. Nó tạo object triển khai các interface mà Spring chọn proxy, rồi xử lý lời gọi public interface method trước khi chuyển cho target. Vì vậy một `final` method trên target **không cản trở** intercept lời gọi qua interface tương ứng.

```java
public interface JobPort {
    void locked();
}

public final class FinalJobService implements JobPort {
    @Override
    public final void locked() {
        System.out.println("locked");
    }
}
```

Đây là fragment độc lập về kiểu Java nhưng chưa chứa Spring context/aspect. Nếu `FinalJobService` được đăng ký làm Spring bean, có advisor cho `locked()` và được dùng qua **JDK proxy của `JobPort`**, advice có thể chạy mặc dù class và implementation method đều `final`.

Không được suy ra rằng “mọi phương thức final đều không thể được Spring AOP advice”. Câu đúng là **CGLIB không thể advice final method theo cơ chế override**, còn JDK proxy có thể intercept public interface method trước khi đến target final implementation.

Nếu target class là `final` nhưng không có interface phù hợp, Spring không thể tạo subclass proxy để advice phương thức của class đó; khi bean thật sự cần class-based proxy, quá trình tạo proxy có thể thất bại.

### 5.3. Bảng quyết định

| Loại phương thức hoặc class | JDK dynamic proxy của Spring | CGLIB class-based proxy của Spring |
| --- | --- | --- |
| Public method khai báo trên interface được proxy thực hiện | Có thể advice nếu pointcut khớp | Có thể advice nếu method có thể override |
| Public method chỉ có trên concrete class | Không được JDK proxy công bố qua interface | Có thể advice nếu method có thể override |
| Private method của target | Không | Không |
| Static method của target/interface | Không | Không |
| Public final method được khai báo trên interface | Có thể advice qua lời gọi interface | Không thể override để advice |
| Final class triển khai interface | Có thể tạo JDK proxy qua interface | Không subclass được class |
| Final class không có interface phù hợp | Không có bề mặt interface proxy thích hợp | Không subclass được |
| Protected/package-private instance method trên target | Không thuộc public interface proxy surface | Có thể tùy quyền truy cập/khả năng override; không xem là public API |
| Package-private method khai báo ở supertype khác package | Không nằm trên public interface | Có thể không truy cập/override được |
| Public, non-final method nhưng `this.method()` | Không advice lời gọi self-invocation | Cũng không advice lời gọi self-invocation |

*Bảng giả định target thuộc Spring container, cơ chế AOP được bật và có advisor thích hợp. “Có thể advice” luôn cần lời gọi qua proxy; không phải bảo đảm advice tự chạy.*

## 6. Self-invocation và trường hợp “method hoàn toàn override được”

Đây là lỗi thường gặp nhất khiến người học nhầm với giới hạn `private`/`final`:

```java
@Service
public class TransferService {
    public void transfer() {
        this.audit(); // Vẫn bypass Spring proxy.
    }

    public void audit() {
        System.out.println("audit");
    }
}
```

`audit()` là public, non-final và có thể override. Nếu một consumer gọi `transferService.audit()` trên Spring proxy, advice cho `audit()` có thể chạy. Nhưng khi target gọi `this.audit()`, lời gọi trên **target** không quay qua proxy. Cả JDK và CGLIB proxy đều có giới hạn self-invocation này trong Spring AOP.

Phân biệt chính xác:

- **Private/final/static:** có giới hạn bản chất của kiểu proxy hoặc Java dispatch, nên ngay cả một lời gọi tương tự từ ngoài cũng không tạo được interception phù hợp qua CGLIB/instance proxy.
- **Self-invocation:** method vẫn có thể advice qua lời gọi **từ một bean khác đến proxy**, nhưng cuộc gọi từ chính target không đi qua proxy.
- **Constructor và initialization callbacks:** logic chạy trong quá trình tạo target, trước khi bean được dùng qua proxy cuối cùng; không nên kỳ vọng `@Transactional` hoặc advice khác được kích hoạt từ `@PostConstruct` hoặc constructor.

**Giải pháp ưu tiên:** tách method cần policy riêng sang một Spring bean có trách nhiệm rõ ràng, inject bằng constructor và gọi qua reference đó. Với nhu cầu đặc thù, `AopContext.currentProxy()` có thể cho code biết proxy hiện tại nếu cấu hình `exposeProxy=true` và lời gọi đang ở trong một invocation qua proxy; cách này gắn business code với Spring AOP, không biến private/static/final method thành interceptable.

## 7. Ví dụ hoàn chỉnh chạy được — Spring Framework 6.2 và Java 17

Ví dụ cho thấy một target service dùng **CGLIB proxy**, có method public có thể override, private helper, final method, static method và lời gọi public method qua `this`. Pointcut cố tình rộng để quan sát chính xác **lời gọi nào Spring AOP proxy chặn được**.

Cấu trúc:

```text
spring-method-limits/
├── pom.xml
└── src/main/java/demo/limits/
    ├── AppConfig.java
    ├── VisibilityService.java
    ├── TraceAspect.java
    └── Demo.java
```

### 7.1. Maven dependencies

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-method-limits</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Dự án dùng Spring Framework thuần, không cần Spring Boot. `aspectjweaver` cung cấp phần hỗ trợ đọc @AspectJ pointcut cho Spring AOP. Không phải bật AspectJ compiler/load-time weaving để chạy ví dụ này.

### 7.2. Cấu hình auto-proxy

Tệp `src/main/java/demo/limits/AppConfig.java`:

```java
package demo.limits;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
}
```

`proxyTargetClass=true` ép class-based proxy. Target bên dưới không có interface; ví dụ dùng CGLIB để thể hiện rõ giới hạn override. `@ComponentScan` quét package `demo.limits`, tìm target và aspect.

### 7.3. Target có public/private/final/static methods

Tệp `src/main/java/demo/limits/VisibilityService.java`:

```java
package demo.limits;

import org.springframework.stereotype.Service;

@Service
public class VisibilityService {
    public void publicAction() {
        System.out.println("[target] publicAction");
    }

    public void route() {
        System.out.println("[target] route");
        this.publicAction(); // Public nhưng self-invocation.
        privateAction();      // Private, không override được.
        finalAction();        // Final, không override được.
        staticAction();       // Static, không qua proxy.
    }

    private void privateAction() {
        System.out.println("[target] privateAction");
    }

    public final void finalAction() {
        System.out.println("[target] finalAction");
    }

    public static void staticAction() {
        System.out.println("[target] staticAction");
    }
}
```

Class không `final` nên CGLIB có thể tạo subclass. `publicAction()` và `route()` có thể override. `finalAction()` được public để caller có thể thử gọi từ bên ngoài; nó vẫn không thể bị CGLIB advice.

### 7.4. Aspect có pointcut rộng

Tệp `src/main/java/demo/limits/TraceAspect.java`:

```java
package demo.limits;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {
    @Before("execution(* demo.limits.VisibilityService.*(..))")
    public void before(JoinPoint joinPoint) {
        System.out.println("[advice] " + joinPoint.getSignature().getName());
    }
}
```

Biểu thức `execution(* ...VisibilityService.*(..))` chọn các method matching signature của class ở mức pointcut, nhưng **không thể biến lời gọi private/static/final thành lời gọi được CGLIB proxy intercept**. Hai lời gọi vào public, non-final method từ bên ngoài qua proxy mới tạo advice trong ví dụ này.

### 7.5. Main lấy Spring bean và thực hiện các lời gọi

Tệp `src/main/java/demo/limits/Demo.java`:

```java
package demo.limits;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Demo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            VisibilityService service = context.getBean(VisibilityService.class);

            System.out.println("cglibProxy="
                    + AopUtils.isCglibProxy(service));

            service.publicAction();
            service.route();
            service.finalAction();
            VisibilityService.staticAction();
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.limits.Demo
```

Các dòng chuẩn do chương trình in (Maven/Spring có thể phát thêm log/cảnh báo):

```text
cglibProxy=true
[advice] publicAction
[target] publicAction
[advice] route
[target] route
[target] publicAction
[target] privateAction
[target] finalAction
[target] staticAction
[target] finalAction
[target] staticAction
```

**Đọc kết quả theo từng đường gọi:**

1. `AopUtils.isCglibProxy(service)` trả `true` vì service được advice và `proxyTargetClass=true`.
2. `service.publicAction()` từ `Demo` gọi qua proxy. `@Before` in `[advice] publicAction` trước target.
3. `service.route()` cũng gọi qua proxy. Advice in `[advice] route`.
4. Trong `route()`, lời gọi `this.publicAction()` **không đi qua proxy**, dù public và override được: chỉ in `[target] publicAction`.
5. `privateAction()` không thể override hay được CGLIB advice; chỉ in phần target.
6. `finalAction()` không thể CGLIB override. Lời gọi trong `route()` và lời gọi trực tiếp từ `Demo` đều **không** in thêm advice.
7. `staticAction()` được gọi trong `route()` và trực tiếp theo tên class. Cả hai là Java static method calls, không phải proxy instance invocation.

Vì ví dụ không giữ state trong target, thứ tự output không bị nhiễu bởi các khác biệt thực thể target/proxy đối với final method. **Không suy rộng** rằng có thể dùng final method an toàn để truy cập mọi state của CGLIB proxied object.

### 7.6. Thử thay pointcut chỉ chọn final method

Nếu đổi advice thành:

```java
@Before("execution(* demo.limits.VisibilityService.finalAction(..))")
public void beforeFinal() {
    System.out.println("[advice] final");
}
```

đây là snippet **thay thế method trong `TraceAspect`**, không phải source file riêng. Spring không thể intercept lời gọi final method bằng CGLIB. Trong trường hợp chỉ có advisor này và không advisor nào chặn method có thể proxy khác, đừng giả định một bean chắc chắn nhận proxy. Cấu hình AOP và việc advisor chọn candidate bean có thể tác động quyết định tạo proxy; dù có tạo proxy, `finalAction()` vẫn không được override/advice.

### 7.7. Thử static hoặc private method bằng annotation

Một phương thức private như:

```java
@Transactional
private void storeAudit() {
    // ...
}
```

hoặc static như:

```java
@Transactional
public static void storeAudit() {
    // ...
}
```

là **fragment minh họa** và cần import `org.springframework.transaction.annotation.Transactional` trong ứng dụng dùng module transaction. Khi Spring transaction được cấu hình ở chế độ **proxy** thông thường, annotation đó **không làm Spring AOP chặn** private/static method. Trước khi kết luận một transaction annotation “bị lỗi”, cần kiểm tra method visibility, đường gọi qua proxy và các ranh giới bean.

## 8. Ví dụ phụ: JDK proxy vẫn advice được implementation final method

Vì bài học nằm trong nhóm JDK và CGLIB, cần phân biệt ngoại lệ quan trọng đối với `final`. Không dùng cùng class `VisibilityService` ở ví dụ trên để minh họa JDK proxy vì class đó không có interface.

Mã Java sau là **fragment minh họa** hai tệp kiểu/interface:

```java
public interface WorkPort {
    void finish();
}

public final class FinalWorker implements WorkPort {
    @Override
    public final void finish() {
        System.out.println("finished");
    }
}
```

Đăng ký `FinalWorker` làm Spring bean, bật AOP chọn JDK proxy (Spring Framework thuần dùng `@EnableAspectJAutoProxy(proxyTargetClass=false)`), có một advisor khớp `finish()`, và inject `WorkPort` vào consumer. Khi consumer gọi `port.finish()`, interceptor chạy **trên interface proxy trước khi delegate** đến target. Vì JDK proxy không cần subclass `FinalWorker`, `final class` và `final method` của implementation không ngăn advice.

Tuy nhiên, nếu consumer đòi inject `FinalWorker` trực tiếp khi Spring trả JDK proxy, có thể lỗi kiểu, vì proxy không phải instance của concrete class. Nên dùng interface `WorkPort` làm hợp đồng dependency.

**Không bao giờ áp dụng kết luận của JDK proxy cho CGLIB:** CGLIB vẫn không thể subclass final class hay override final method.

## 9. Khi cần advice cho hành vi đang nằm trong private/static/final method

### 9.1. Đặt advice lên public entry point

Nếu requirement là “mọi lần gọi đăng ký tài khoản phải được ghi audit”, hãy advice public method `RegistrationService.register()`. Nó có thể gọi nhiều helper private, nhưng lời gọi đến entry point đã được advice trước/sau toàn bộ thao tác theo thời điểm advice được cấu hình. Đây thường là giải pháp tối thiểu và dễ kiểm soát nhất.

Nếu cần transaction quanh chuỗi thao tác, đặt transaction boundary ở public service method được bean khác gọi qua proxy, thay vì trên helper private được gọi nội bộ.

### 9.2. Tách policy boundary thành bean riêng

Nếu một helper cần chính sách riêng, có thể tách thành bean chuyên trách:

```java
@Service
public class ApprovalService {
    private final AuditService auditService;

    public ApprovalService(AuditService auditService) {
        this.auditService = auditService;
    }

    public void approve(String id) {
        auditService.record(id); // Method invocation qua dependency Spring.
    }
}

@Service
public class AuditService {
    public void record(String id) {
        System.out.println("audit " + id);
    }
}
```

Đây là fragment minh họa thiết kế, cần các imports/package và cấu hình Spring thích hợp. Khi `AuditService` được proxy do advisor khớp `record()`, lời gọi qua dependency được chặn. Cách này còn giúp test độc lập và tránh coupling với `AopContext.currentProxy()`.

### 9.3. Chọn JDK proxy nếu hợp đồng interface phù hợp

Nếu target class phải `final` do yêu cầu thiết kế nhưng vẫn có public interface, cân nhắc Spring AOP dựa trên JDK proxy. Spring Boot tự cấu hình AOP thường mặc định CGLIB; nếu muốn ưu tiên JDK proxy, có thể đặt:

```properties
spring.aop.proxy-target-class=false
```

Trong Spring Framework thuần, `@EnableAspectJAutoProxy(proxyTargetClass=false)` là mặc định của annotation. Giá trị `false` không tự bảo đảm JDK proxy nếu bean không có interface hoặc có cấu hình auto-proxy khác buộc class-based proxy.

Dùng `AopUtils.isJdkDynamicProxy(bean)` và `AopUtils.isCglibProxy(bean)` kiểm tra runtime trên reference được Spring inject/getBean; không dựa hoàn toàn vào tên class hoặc một annotation đơn lẻ.

### 9.4. Khi nào cần cơ chế ngoài Spring AOP proxy?

Nếu requirement bắt buộc intercept lời gọi private/static/constructor/field access hoặc self-invocation ở mức bytecode, **Spring AOP proxy không hỗ trợ**. Đó là một phạm vi khác, có thể yêu cầu giải pháp compile-time/load-time AspectJ weaving với cấu hình khác, hoặc thay đổi thiết kế để biểu diễn operation qua public Spring bean boundary. Không thể đạt cùng kết quả chỉ bằng đổi pointcut hoặc bật `proxyTargetClass=true`.

## 10. Chẩn đoán khi “pointcut đúng nhưng advice không chạy”

| Dấu hiệu | Nguyên nhân có thể xảy ra | Hướng kiểm tra |
| --- | --- | --- |
| Method `private` có `@Transactional` nhưng transaction không mở | Private method không nằm trên proxy surface | Đặt boundary trên method proxyable hoặc tách bean |
| Method `static` có pointcut khớp về tên nhưng advice không chạy | Static call không qua instance proxy | Đổi sang instance method trên Spring bean nếu cần advice |
| `public final` method trên CGLIB proxy không advice | Không thể override final method | Bỏ final nếu thiết kế cho phép, dùng JDK interface proxy, hoặc tách bean |
| Target class `final` và buộc class proxy | CGLIB không subclass được | Dùng interface/JDK proxy hoặc thay thiết kế |
| Public non-final method gọi qua `this` không advice | Self-invocation bypass proxy | Gọi qua bean khác được DI |
| Method package-private trong base class khác package không advice | Không visible/override được trong subclass proxy | Đặt API tại method public/protected phù hợp |
| Có interface nhưng runtime lại CGLIB | Spring Boot mặc định class-based proxy hoặc có cấu hình gộp | Kiểm tra `spring.aop.proxy-target-class` và `AopUtils` |
| Tự `new Service()` rồi gọi method | Object không do Spring quản lý | Inject bean từ container thay vì tự tạo target |
| `@Aspect` có mặt nhưng không có advice nào chạy | Aspect chưa thành Spring bean, AOP chưa bật, hoặc pointcut không khớp | Xác minh `@Component`/`@Bean` và `@EnableAspectJAutoProxy`/Boot AOP |
| Advice chạy trên `outer()` nhưng không chạy trên method gọi nội bộ | Caller đi vào proxy một lần, sau đó target dùng `this` | Xem đường gọi thực tế, tách thành bean riêng khi cần |

### Quy trình kiểm tra có thể lặp lại

1. Xác nhận target là Spring-managed bean và aspect đã được đăng ký, hạ tầng AOP đã bật.
2. Lấy **reference thực tế** tại injection point hoặc bằng `ApplicationContext.getBean(...)`.
3. Kiểm tra với `AopUtils.isAopProxy(bean)`; nếu cần, phân biệt `isJdkDynamicProxy` và `isCglibProxy`.
4. Xác định method là instance hay static, public/protected/private, final hay có thể override, và target class có final hay không.
5. Nếu JDK proxy, kiểm tra method có thuộc interface mà proxy công bố hay không; nếu CGLIB, kiểm tra subclass visibility/overridability.
6. Theo dõi **đường gọi**: từ consumer qua proxy hay qua `this`/object `new`/callback khởi tạo.
7. Chỉ sau đó mới điều chỉnh pointcut. Đừng mở rộng pointcut để chữa lỗi thuộc về đường gọi hoặc kiểu proxy.

## 11. Tự kiểm tra

**1. Tại sao CGLIB không advice được một private method dù biểu thức `execution(* my.pkg.Service.helper(..))` có vẻ chính xác?** Vì subclass proxy không thể override private method và không thể nhận một lời gọi private thông qua proxy.

**2. Một public final implementation method có luôn nằm ngoài Spring AOP không?** Không. JDK proxy có thể intercept public interface invocation đến final implementation. CGLIB thì không override được final method.

**3. Một service có public instance method, nhưng aspect không chạy khi gọi từ method khác cùng class. Vì sao?** Self-invocation đi trên target `this` nên không qua proxy; không liên quan đến method có final hay không.

**4. Bật `proxyTargetClass=true` có giúp intercept static method không?** Không. Static method không được override và không là instance invocation qua proxy.

**5. Vì sao `final class` có thể chạy AOP qua JDK proxy nhưng không qua CGLIB?** JDK proxy triển khai interface; CGLIB cần tạo subclass của target, điều Java cấm với final class.

**6. Khi nào nên tách logic private thành bean riêng?** Khi phần nghiệp vụ ấy thực sự cần policy riêng qua Spring AOP và có ranh giới trách nhiệm rõ ràng; nếu chỉ là helper nội bộ, advice ở public entry point thường đã hợp lý.

## Tài liệu Spring chính thức

- [Spring Framework — Proxying Mechanisms (JDK, CGLIB, private/final và self-invocation)](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Declaring a Pointcut (phạm vi method execution join points)](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework — ProxyFactoryBean và class-based proxy](https://docs.spring.io/spring-framework/reference/core/aop-api/pfb.html)
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html)
