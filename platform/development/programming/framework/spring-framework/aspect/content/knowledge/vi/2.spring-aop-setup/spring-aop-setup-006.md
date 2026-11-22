# Phạm vi hiệu lực cấu hình Spring AOP trong từng ApplicationContext

## 1. Vấn đề cần hiểu khi thiết lập Spring AOP

Một ứng dụng Spring có thể chỉ có một `ApplicationContext`, nhưng cũng có thể có **nhiều context độc lập hoặc có quan hệ cha–con**. Khi dùng `@EnableAspectJAutoProxy`, câu hỏi then chốt không phải chỉ là “đã bật AOP trong ứng dụng chưa?”, mà là **AOP được bật trong context nào và bean cần proxy do context nào tạo ra?**

**Quy tắc cốt lõi:** Trong cấu hình Spring Framework tường minh, `@EnableAspectJAutoProxy` áp dụng cho **`ApplicationContext` cục bộ chứa cấu hình đó**. Nếu có nhiều context và muốn từng context tự tạo proxy cho bean của nó, cần kích hoạt hỗ trợ `@AspectJ` trong các context tương ứng. Kích hoạt ở cha **không tự lan** xuống con; kích hoạt ở con **không xử lý lại** bean do cha tạo.

Bài này chỉ xét **Spring AOP theo cơ chế Spring proxy** và cách cấu hình nó trong Spring IoC, đặc biệt là `@EnableAspectJAutoProxy`. Không cần ôn lại các khái niệm AOP tổng quát.

Sau bài học, bạn sẽ:
- Xác định context sở hữu bean, context chứa hạ tầng auto-proxy và context chứa aspect.
- Dự đoán bean nào thực sự có proxy khi dùng hai `ApplicationContext`.
- Phân biệt **khả năng nhìn thấy bean/aspect qua quan hệ cha–con** với **khả năng hậu xử lý bean để tạo proxy**.
- Viết ví dụ kiểm chứng bằng `AopUtils.isAopProxy(...)`.
- Áp dụng nguyên tắc cho Spring MVC nhiều context và Spring Boot có AOP auto-configuration.

## 2. `@EnableAspectJAutoProxy` làm gì trong một context?

Trong ứng dụng Spring Framework thuần, cấu hình sau cho phép Spring đọc các Spring bean đã khai báo `@Aspect`, dựng advisor và tự tạo AOP proxy khi cần:

```java
@Configuration
@EnableAspectJAutoProxy
public class AopConfig {
}
```

Cấu hình này cần thư viện `aspectjweaver` trên classpath để Spring phân tích các biểu thức pointcut của `@AspectJ`. Thêm `@Aspect` lên một lớp **chưa đủ** để có aspect bean: phải đăng ký lớp bằng `@Component`, `@Bean` hoặc một cách đăng ký Spring bean phù hợp.

Trong context đã bật hỗ trợ, hạ tầng Spring đăng ký một **auto-proxy creator** (thuộc nhóm `BeanPostProcessor`). Khi context tạo bean, bộ xử lý này xem xét các advisor thích hợp và có thể trả về proxy thay vì target trực tiếp.

Sơ đồ một context:

```text
ApplicationContext A
├── @Configuration + @EnableAspectJAutoProxy
│    └── đăng ký AOP auto-proxy creator trong A
├── @Bean / @Component: AuditAspect
│    └── Spring phân tích các advice/pointcut thành advisor
└── @Bean / @Service: BillingService
     └── A tạo BillingService → A áp dụng bean post-processors
                                     └── có advisor phù hợp?
                                           ├── có → trả proxy
                                           └── không → trả bean gốc
```

Điều kiện để advice thực sự chạy là **phương thức khớp pointcut và lời gọi đi qua proxy**. Bật AOP không bắt buộc mọi bean có proxy và không biến method call nội bộ trên `this` thành lời gọi qua proxy.

### Những cấu hình cùng một context

Nếu nhiều lớp `@Configuration` trong **cùng một context** khai báo các tùy chọn auto-proxy, Spring hợp nhất hạ tầng auto-proxy phù hợp trong context đó; các tùy chọn như `proxyTargetClass` có thể tác động lên cấu hình proxy chung của context. Điều này **không biến** các context trong cây cha–con thành một hạ tầng AOP duy nhất.

## 3. Context cha–con: hai phạm vi khác nhau

Ví dụ có hai context:

```text
Parent ApplicationContext
├── parentService     (được parent tạo)
├── parentAspect      (được parent đăng ký)
└── parent AOP creator?  ← chỉ có nếu parent bật AOP

                 ↑ child tra cứu được một số bean từ parent
                 │
Child ApplicationContext
├── childService      (được child tạo)
├── childAspect       (được child đăng ký)
└── child AOP creator?   ← chỉ có nếu child bật AOP
```

Trong quan hệ này:
1. **Bean do parent định nghĩa và khởi tạo** được xử lý bởi các `BeanPostProcessor` của parent. Nếu parent tạo một Spring AOP proxy, child khi tra cứu bean parent sẽ nhận chính proxy đó.
2. **Bean do child định nghĩa và khởi tạo** được xử lý bởi các `BeanPostProcessor` của child. Bộ xử lý chỉ nằm ở parent không tự hậu xử lý bean child.
3. Child thông thường có thể tra cứu bean của parent nếu tên/kiểu phù hợp và không bị che khuất bởi định nghĩa local. Parent không tra cứu ngược được bean chỉ định nghĩa trong child.
4. **Có thể nhìn thấy aspect/advisor từ tổ tiên không có nghĩa auto-proxy creator từ tổ tiên chạy trong child.** Ngược lại, auto-proxy creator nằm trong child có thể dùng advisor/aspect mà cơ chế tìm kiếm bean của nó nhìn thấy ở parent để advise bean **do child tạo**, nếu điều kiện pointcut khớp. Đây là hai khía cạnh riêng.
5. Nếu trong child đăng ký bean trùng tên bean parent, bean local thường che bean parent trong các lần tra cứu theo tên. Không suy ra hai bean trở thành cùng một instance hay có cùng proxy.

**Vì sao?** `BeanPostProcessor` hoạt động **theo từng bean factory/container**. AOP auto-proxy creator là một `BeanPostProcessor`. Khi child gọi `getBean(...)` và lấy được bean do parent quản lý, việc tìm thấy bean đó không khiến child dùng auto-proxy creator của mình để tạo lại hoặc bọc lại instance thuộc parent.

Đây là khác biệt giữa **ranh giới sở hữu bean** và **phạm vi tra cứu bean**.

## 4. Ma trận bật/tắt AOP ở parent và child

Để ma trận có thể kiểm chứng, giả sử:
- Parent sở hữu một bean `ParentService` và một aspect với pointcut khớp riêng `ParentService.work()`.
- Child sở hữu một bean `ChildService` và một aspect với pointcut khớp riêng `ChildService.work()`.
- Cả hai service là class có method `public`, không `final`, và được gọi từ bên ngoài qua bean lấy từ Spring.
- Không có auto-proxy creator nào khác được cấu hình; vì vậy kết quả trong bảng chỉ nói về **AOP được bật qua `@EnableAspectJAutoProxy`**.

| Bật AOP tại parent | Bật AOP tại child | `ParentService` có Spring AOP proxy? | `ChildService` có Spring AOP proxy? | Giải thích |
| --- | --- | --- | --- | --- |
| Không | Không | Không | Không | Không context nào có auto-proxy creator cho `@AspectJ`. |
| Có | Không | Có | Không | Parent xử lý bean của parent; child không có auto-proxy creator tương ứng. |
| Không | Có | Không | Có | Child xử lý bean của child; bean parent không bị child proxy ngược trở lại. |
| Có | Có | Có | Có | Mỗi context chủ động xử lý bean của chính mình. |

Ma trận nêu **trạng thái proxy** trong mô hình cô lập trên. Ở hệ thống thực, các cơ chế khác (ví dụ giao dịch khai báo hoặc một cấu hình AOP khác) cũng có thể tạo proxy; hãy kiểm tra các bean cụ thể thay vì suy diễn chỉ từ sự hiện diện của `@EnableAspectJAutoProxy`.

### Trường hợp dễ hiểu nhầm

Giả sử **chỉ child bật AOP**, rồi làm:

```java
ParentService inherited = childContext.getBean(ParentService.class);
```

Biến `inherited` vẫn trỏ tới bean (hoặc proxy nếu có) mà parent đã tạo. Nó **không tự được chuyển thành proxy của child**. Ngược lại, nếu parent đã bật AOP và trả về proxy cho `ParentService`, child nhìn thấy proxy parent đó ngay cả khi child không bật AOP.

## 5. Ví dụ Java chạy độc lập: kiểm chứng cả bốn trường hợp

Ví dụ dùng **Java 17+, Spring Framework 6.1.14 và Gradle**. Đây là chương trình Spring Framework thuần, cố tình **không dùng Spring Boot**, nhằm kiểm soát rõ context nào có `@EnableAspectJAutoProxy`. Các lớp không dùng component scanning để không vô tình đăng ký bean vào sai context.

### 5.1. Tạo project Gradle

Cấu trúc:

```text
spring-aop-context-scope/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/scope/
    ├── ContextScopeDemo.java
    ├── ParentService.java
    ├── ChildService.java
    ├── ParentTrace.java
    └── ChildTrace.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-context-scope'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.scope.ContextScopeDemo'
}
```

`spring-aop` chứa hạ tầng tạo proxy; `spring-context` cung cấp `ApplicationContext` và cấu hình Java; `aspectjweaver` là thư viện Spring cần để xử lý `@AspectJ` và pointcut expression. Sự có mặt của ba dependency **chưa tự bật** `@EnableAspectJAutoProxy` trong ví dụ Framework thuần này.

### 5.2. Hai service thuộc hai context

`src/main/java/demo/scope/ParentService.java`:

```java
package demo.scope;

public class ParentService {
    public String work() {
        return "parent-result";
    }
}
```

`src/main/java/demo/scope/ChildService.java`:

```java
package demo.scope;

public class ChildService {
    public String work() {
        return "child-result";
    }
}
```

### 5.3. Hai aspect có điểm khớp tách biệt

`src/main/java/demo/scope/ParentTrace.java`:

```java
package demo.scope;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class ParentTrace {
    @Before("execution(public * demo.scope.ParentService.work(..))")
    public void beforeWork() {
        System.out.println("advice:parent");
    }
}
```

`src/main/java/demo/scope/ChildTrace.java`:

```java
package demo.scope;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class ChildTrace {
    @Before("execution(public * demo.scope.ChildService.work(..))")
    public void beforeWork() {
        System.out.println("advice:child");
    }
}
```

Hai aspect là các lớp `@Aspect` bình thường; chúng sẽ được đưa vào Spring bằng `@Bean` trong phần sau. Pointcut của parent không khớp `ChildService` và ngược lại. Vì vậy, kể cả khi child nhìn thấy `ParentTrace` thông qua parent, log cho `ChildService` vẫn chỉ do `ChildTrace` tạo ra. Cách thiết kế này giúp thấy rõ **proxy được tạo trong context nào**, không phụ thuộc vào giả định sai rằng child hoàn toàn không nhìn thấy aspect parent.

### 5.4. Đăng ký bean và cấu hình bật AOP theo từng context

`src/main/java/demo/scope/ContextScopeDemo.java`:

```java
package demo.scope;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class ContextScopeDemo {

    @Configuration(proxyBeanMethods = false)
    static class ParentBeans {
        @Bean
        ParentService parentService() {
            return new ParentService();
        }

        @Bean
        ParentTrace parentTrace() {
            return new ParentTrace();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ChildBeans {
        @Bean
        ChildService childService() {
            return new ChildService();
        }

        @Bean
        ChildTrace childTrace() {
            return new ChildTrace();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy
    static class EnableParentAop {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy
    static class EnableChildAop {
    }

    public static void main(String[] args) {
        runCase("NONE", false, false);
        runCase("PARENT_ONLY", true, false);
        runCase("CHILD_ONLY", false, true);
        runCase("BOTH", true, true);
    }

    private static void runCase(String name,
                                boolean enableParent,
                                boolean enableChild) {
        try (AnnotationConfigApplicationContext parent =
                 new AnnotationConfigApplicationContext()) {

            parent.register(ParentBeans.class);
            if (enableParent) {
                parent.register(EnableParentAop.class);
            }
            parent.refresh();

            try (AnnotationConfigApplicationContext child =
                     new AnnotationConfigApplicationContext()) {

                child.setParent(parent);
                child.register(ChildBeans.class);
                if (enableChild) {
                    child.register(EnableChildAop.class);
                }
                child.refresh();

                ParentService p = parent.getBean(ParentService.class);
                ChildService c = child.getBean(ChildService.class);
                ParentService inherited =
                    child.getBean(ParentService.class);

                System.out.printf(
                    "%s parentProxy=%s childProxy=%s sameParent=%s%n",
                    name,
                    AopUtils.isAopProxy(p),
                    AopUtils.isAopProxy(c),
                    p == inherited
                );

                System.out.println("parent=" + p.work());
                System.out.println("child=" + c.work());
            }
        }
    }
}
```

**Giải thích chính xác vai trò từng lớp:**
- `ParentBeans` đăng ký `ParentService` và `ParentTrace` **vào parent**, bất kể parent có bật AOP hay không.
- `ChildBeans` đăng ký `ChildService` và `ChildTrace` **vào child**.
- `EnableParentAop` và `EnableChildAop` có cùng annotation, nhưng được đăng ký vào **hai context khác nhau**, nên có hai phạm vi cấu hình độc lập.
- `child.setParent(parent)` thiết lập quyền tra cứu bean của parent từ child; nó không khiến auto-proxy creator trở thành một `BeanPostProcessor` dùng chung.
- `AopUtils.isAopProxy(...)` cho biết đối tượng được lấy ra có phải Spring AOP proxy hay không. So sánh `p == inherited` chứng minh child lấy lại **đúng instance do parent cung cấp**.

### 5.5. Chạy chương trình và đối chiếu kết quả

Từ thư mục chứa `build.gradle`:

```bash
gradle run
```

Hoặc, nếu dự án đã có Gradle Wrapper, dùng `./gradlew run` (Linux/macOS) hay `gradlew.bat run` (Windows).

Các dòng do **mã ứng dụng** in ra (không kể thông tin build của Gradle hay logger môi trường) theo thứ tự:

```text
NONE parentProxy=false childProxy=false sameParent=true
parent=parent-result
child=child-result
PARENT_ONLY parentProxy=true childProxy=false sameParent=true
advice:parent
parent=parent-result
child=child-result
CHILD_ONLY parentProxy=false childProxy=true sameParent=true
parent=parent-result
advice:child
child=child-result
BOTH parentProxy=true childProxy=true sameParent=true
advice:parent
parent=parent-result
advice:child
child=child-result
```

**Đọc kết quả:**
- `NONE`: cả hai service vẫn là Spring bean, nhưng không có AOP proxy vì chưa bật auto-proxy.
- `PARENT_ONLY`: advice của parent xuất hiện cho `ParentService`; `ChildService` vẫn là bean thường, dù child có cha đã bật AOP.
- `CHILD_ONLY`: `ChildService` có advice; `ParentService` không bị child xử lý lại và `sameParent=true`.
- `BOTH`: mỗi context tạo proxy cho service do nó sở hữu, và mỗi advice xuất hiện đúng tại lời gọi khớp pointcut.

Ví dụ này minh họa **ranh giới cấu hình `@AspectJ`**, không phải cách chạy AOP cho object được tạo bằng `new` ngoài Spring. Các lời gọi đều dùng bean được container trả về.

## 6. Ứng dụng vào Spring MVC với root context và DispatcherServlet

Trong ứng dụng web Spring MVC cấu hình kiểu truyền thống, có thể có:

```text
Root WebApplicationContext
├── Service, Repository, shared infrastructure
├── @Aspect dùng cho service
└── RootAopConfig (@EnableAspectJAutoProxy)
          |
          +--> DispatcherServlet A child WebApplicationContext
          |    ├── Controller của servlet A
          |    └── ServletAopConfig (@EnableAspectJAutoProxy) nếu cần
          |
          +--> DispatcherServlet B child WebApplicationContext
               ├── Controller của servlet B
               └── ServletAopConfig (@EnableAspectJAutoProxy) nếu cần
```

Nếu pointcut nhắm đến **service được tạo trong root**, cấu hình Spring AOP nên tồn tại trong **root context** để root có thể tạo proxy cho service. Nếu pointcut nhắm đến **controller do context của `DispatcherServlet` tạo**, hãy bảo đảm context của servlet đó cũng có hỗ trợ auto-proxy phù hợp.

Cấu hình `@EnableAspectJAutoProxy` **chỉ ở root** sẽ không khiến toàn bộ controller thuộc các servlet child tự nhận proxy. Ngược lại, chỉ đặt annotation ở child cũng không có tác dụng hồi tố lên service đã được root tạo.

Một mẫu cấu hình rút gọn, trong đó mỗi config được **nạp vào đúng context**:

```java
// Nạp trong root context (minh họa cấu hình, không phải ứng dụng độc lập).
@Configuration
@EnableAspectJAutoProxy
public class RootAopConfig {
}

// Nạp trong context của một DispatcherServlet nếu cần
// advise các bean do chính servlet context đó tạo.
@Configuration
@EnableAspectJAutoProxy
public class ServletAopConfig {
}
```

Không đăng ký trùng lặp các service/controller/aspect ngoài ý muốn vào nhiều context chỉ để “bật AOP toàn cục”. Cần xác định trước bean nào là của root, bean nào là của từng servlet và điểm cắt có khớp bean mong muốn hay không.

### Kiểm tra phạm vi thật sự

Có thể ghi log hoặc assert trực tiếp:

```java
Object service = rootContext.getBean("orderService");
Object controller = servletContext.getBean("orderController");

System.out.println(AopUtils.isAopProxy(service));
System.out.println(AopUtils.isAopProxy(controller));
```

Đoạn trên chỉ minh họa cách kiểm tra, giả sử hai bean có các tên đã nêu và đã được đăng ký. Một kết quả `false` **không tự chứng minh cấu hình bị lỗi**: có thể pointcut không khớp, không có advisor tương ứng, hoặc bean không thể được proxy theo cơ chế đang chọn.

## 7. Spring Boot: bật tự động không làm mất ranh giới context

Spring Boot có **AOP auto-configuration**. Khi có các dependency AspectJ phù hợp (thường qua `spring-boot-starter-aop`), Boot có thể bật `@AspectJ` auto-proxy tự động mà không yêu cầu ứng dụng viết `@EnableAspectJAutoProxy` thủ công.

Ví dụ dependency Gradle của ứng dụng Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Với Spring Boot 3.3:
- `spring.aop.auto=true` là hành vi auto-configuration mặc định khi điều kiện đáp ứng; đặt `spring.aop.auto=false` để vô hiệu cơ chế AOP auto-configuration này.
- `spring.aop.proxy-target-class=true` là mặc định proxy theo lớp của Boot; đặt `false` để ưu tiên JDK proxy khi phù hợp.
- Khi ứng dụng chỉ có **một** context, thường không phải suy nghĩ về nhiều phạm vi container.
- Nếu hệ thống tạo **nhiều** context (ví dụ context con hoặc cấu trúc web tùy biến), hãy kiểm tra **auto-configuration nào thực sự chạy ở từng context**, bean nào thuộc context nào và proxy nào được tạo ở đó. Không nên mặc định rằng vì Boot đã bật AOP trong context chính nên AOP tự áp dụng cho mọi context tự tạo.

**Không nhầm `@EnableAspectJAutoProxy` với Spring Boot property:** annotation là cách bật tường minh ở một context; Boot property điều khiển phần auto-configuration do Boot quản lý. Đặt `spring.aop.auto=false` không phải cam kết tắt mọi proxy do các cấu hình thủ công hoặc cơ chế Spring khác đã đăng ký.

## 8. Các cấu hình và tình huống dễ sai

| Tình huống | Ngộ nhận thường gặp | Cách xác định/sửa |
| --- | --- | --- |
| `@EnableAspectJAutoProxy` ở parent; aspect/target ở child | “Child tự nhận AOP từ parent” | Kiểm tra auto-proxy creator trong child; kích hoạt AOP đúng child khi cần advise bean child. |
| `@EnableAspectJAutoProxy` chỉ ở child; target bean từ parent | “Child sẽ bọc proxy thêm cho bean parent” | Xác định context sở hữu bean; cấu hình AOP ở parent nếu cần proxy lúc parent tạo bean. |
| Aspect ở parent, target ở child | “Không thể dùng aspect parent vì khác context” | Phân biệt khả năng child nhìn thấy bean/aspect tổ tiên và việc child có auto-proxy creator; kiểm tra pointcut cụ thể. |
| Aspect chỉ ở child, target ở parent | “Parent tìm thấy aspect child” | Parent không tự nhìn thấy child; đưa aspect/logic advisor phù hợp vào parent nếu target thuộc parent. |
| Hai child context cùng parent | “Bật AOP ở child A cũng bật cho child B” | Mỗi child có BeanFactory riêng; cấu hình độc lập ở từng child theo nhu cầu. |
| Cùng tên bean ở parent/child | “`getBean` ở child chắc chắn trả bean parent” | Xem định nghĩa bean local, bean shadowing và context thực sự tạo instance. |
| Chuyển `@Configuration` AOP sang component scan khác | “Bean vẫn ở context cũ” | Xác minh phạm vi `@ComponentScan` / `@Import`, nơi từng config được đăng ký và nơi bean được tạo. |
| `isAopProxy(bean) == false` | “`@EnableAspectJAutoProxy` không hoạt động” | Kiểm tra aspect bean, pointcut, method visibility, thời điểm bean tạo và hạ tầng proxy khác. |
| `isAopProxy(bean) == true` nhưng advice không in | “Proxy luôn chạy mọi advice” | Xác minh pointcut/method và lời gọi có qua proxy; kiểm tra self-invocation. |

### Tại sao không chỉ kiểm tra annotation?

`@EnableAspectJAutoProxy` có thể được đặt trên config nhưng config **không được register trong context đang xét**. Ngoài ra, một service có thể được tạo bởi parent rồi inject vào child; quan sát nơi inject không xác định được nơi tạo proxy. Khi cần kết luận, phải nhìn vào **runtime bean và context sở hữu**, không chỉ vào package hoặc vị trí đặt lớp Java.

### Điều chỉnh `proxyTargetClass` hoặc `exposeProxy` có lan qua context không?

Các thuộc tính như:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true, exposeProxy = true)
```

được khai báo cho hạ tầng trong context tương ứng. `proxyTargetClass=true` ưu tiên proxy theo lớp; `exposeProxy=true` cho phép truy cập proxy hiện hành qua `AopContext` khi đang ở trong lời gọi proxy phù hợp. Chúng **không** khiến auto-proxy creator trong context này hậu xử lý bean do context khác tạo, và `exposeProxy` không tạo ra một “proxy toàn ứng dụng” dùng chung giữa các context.

Hạn chế của proxy như self-invocation, `final` và `private` vẫn áp dụng bất kể cách tổ chức context; chúng thuộc cơ chế Spring AOP theo proxy, không phải lỗi kế thừa cấu hình.

## 9. Quy trình chẩn đoán khi gặp AOP không chạy trong nhiều context

1. **Liệt kê context:** Có bao nhiêu `ApplicationContext`? Context nào là parent, child hoặc sibling? Context nào đã `refresh()`?
2. **Xác định chủ sở hữu bean:** Bean target định nghĩa và được tạo ở context nào? Nếu lấy qua child, kiểm tra có phải bean inherited từ parent không.
3. **Kiểm tra bật AOP:** `@EnableAspectJAutoProxy` được nạp vào context nào? Với Boot, AOP auto-configuration có chạy tại đó không?
4. **Kiểm tra aspect/advisor:** Aspect bean tồn tại và được auto-proxy creator tương ứng tìm thấy không? Pointcut có khớp đúng phương thức target không?
5. **Kiểm tra proxy thực tế:** Dùng `AopUtils.isAopProxy`; nếu cần có thể dùng `AopUtils.isJdkDynamicProxy` / `AopUtils.isCglibProxy`.
6. **Kiểm tra đường gọi:** Client gọi qua proxy Spring hay trực tiếp target/`this`? Method có phù hợp với proxy type không?
7. **Kiểm tra thời điểm:** Thay đổi cấu hình sau khi context đã tạo bean không mặc nhiên khiến bean đó được tự động proxy lại; sửa cấu hình khởi tạo và chạy lại context để kiểm chứng.

Khi debug sâu một bean proxy, có thể kiểm tra các `Advisor` mà Spring gắn vào đối tượng nếu proxy triển khai giao diện `org.springframework.aop.framework.Advised`:

```java
if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (org.springframework.aop.Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor);
    }
}
```

Đây là đoạn kiểm tra dùng khi có biến `bean` đã lấy từ Spring; không phải chương trình Java độc lập. Nó giúp phân biệt “bean có proxy” với “proxy có đúng advisor mong đợi”. Một số proxy hoặc cấu hình đặc biệt có thể không cho xem/chỉnh advisor qua giao diện này, vì thế kết luận nên dựa trên cả thực nghiệm hành vi.

## 10. Kết luận thực hành

Trong Spring, **cấu hình auto-proxy thuộc về từng `ApplicationContext`**, còn **bean, aspect và advisor có các quy tắc sở hữu/tra cứu riêng**. Với cây cha–con, hãy nhớ:

- Bật `@EnableAspectJAutoProxy` tại **context tạo target bean cần advise**.
- Đừng coi việc child tra cứu được bean parent là bằng chứng child tạo lại proxy cho bean đó.
- Khi cần advise bean thuộc nhiều context, kiểm tra cơ chế AOP ở **mỗi context có bean mục tiêu** và xác định aspect/advisor nào được context đó nhìn thấy.
- Dùng `AopUtils.isAopProxy(...)` và lời gọi method qua bean Spring để xác minh giả thuyết bằng runtime.

### Tài liệu Spring chính thức

- [Spring Framework 6.0 Javadoc — `@EnableAspectJAutoProxy`](https://docs.spring.io/spring-framework/docs/6.0.23/javadoc-api/org/springframework/context/annotation/EnableAspectJAutoProxy.html): ghi rõ annotation chỉ áp dụng cho local application context, kể cả ví dụ root/`DispatcherServlet`.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): bật hỗ trợ `@AspectJ` và yêu cầu dependency.
- [Spring Framework — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): phạm vi per-container của `BeanPostProcessor`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): cơ chế proxy, cấu hình proxy type và giới hạn.
- [Spring Boot 3.3 — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/3.3/reference/features/aop.html): AOP auto-configuration của Boot.
