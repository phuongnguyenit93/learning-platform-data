# Spring AOP Auto-proxy: luồng tạo bean đích, tạo proxy và trả tham chiếu cho bên phụ thuộc

## 1. Vấn đề cần hiểu

Khi một Spring bean có phương thức phù hợp với advice, Spring AOP có thể tự tạo **proxy**. Một bean khác khai báo constructor injection thường nhận **proxy được container cung cấp**, chứ không giữ trực tiếp target object bên trong proxy. Từ đó, lời gọi qua dependency được chuyển qua advice rồi đến logic nghiệp vụ.

Ba đối tượng/khái niệm cần tách bạch:

- **Target bean**: đối tượng thực hiện nghiệp vụ, được tạo từ bean definition (ví dụ class `@Service` hoặc factory method `@Bean`).
- **AOP proxy**: đối tượng đại diện cho target để chặn các lời gọi phương thức phù hợp; Spring AOP dùng JDK dynamic proxy hoặc class-based proxy (CGLIB).
- **Dependent/consumer bean**: bean sử dụng target qua dependency injection; nó nhận tham chiếu mà Spring công bố cho tên bean, có thể là proxy khi auto-proxying áp dụng.

Trong ví dụ, một `CheckoutWorkflow` cần `OrderService`. Spring nhận yêu cầu này, bảo đảm `OrderService` được tạo và khởi tạo; nếu advisor cần chặn `OrderService.process()` thì container có thể cung cấp AOP proxy. Khi `CheckoutWorkflow` gọi `service.process()`, invocation qua proxy mới cho advice cơ hội thực thi.

**Phạm vi bài:** Spring AOP dựa trên proxy và lifecycle/IoC của Spring. Không suy rộng thành AspectJ bytecode weaving, cũng không coi mỗi method trong một Spring bean đều tự động được advice.

## 2. Sơ đồ thời gian của một singleton thường gặp

```text
Đăng ký @Configuration, @Service, @Component, @Aspect, @Bean
                           |
                           v
              ApplicationContext khởi động
                           |
                           v
           Hạ tầng BeanPostProcessor được đăng ký
          (gồm auto-proxy creator cho Spring AOP)
                           |
                           v
        Container cần tạo CheckoutWorkflow (consumer)
                           |
               Resolve constructor parameter
                           |
                    cần OrderService
                           |
             Tìm bean definition OrderService
                           |
                           v
                  TẠO TARGET INSTANCE
                   (constructor/factory)
                           |
                 điền cấu hình/dependencies
                           |
              before-initialization processors
                           |
                  lifecycle init callbacks
                           |
              after-initialization processors
                           |
         Auto-proxy creator xem xét advisor/pointcut
                   /                 \
           có advice phù hợp       không phù hợp
                   |                 |
             tạo AOP proxy       giữ target
                   \                 /
                    \               /
                     v             v
                Công bố bean reference
                           |
                           v
      Inject reference vào constructor CheckoutWorkflow
                           |
                           v
        Workflow --> proxy --> advice --> target.process()
```

Đây là **mô hình thông thường**, không phải thứ tự callback bất biến với mọi loại bean. Một `BeanPostProcessor` có thể áp dụng logic khác trong `postProcessBeforeInitialization`; auto-proxy creator phổ biến tạo proxy ở `postProcessAfterInitialization` hoặc theo đường đặc biệt khi cần tham chiếu sớm. Trường hợp circular dependencies, custom scopes, `FactoryBean`, post-processors tạo bean quá sớm, hoặc cấu hình đặc thù có đường đi phức tạp hơn.

Điểm quan trọng là **consumer nhận bean reference đã đi qua quá trình quản lý của Spring**. Kết quả không nhất thiết cùng Java object identity với target nằm sau proxy.

## 3. Từ bean definition đến instance của target

### 3.1. Bean definition chưa phải là object

Spring có thể biết sự tồn tại của một bean nhờ:

```java
@Service
public class OrderServiceImpl implements OrderService {
    // ...
}
```

hoặc thông qua một phương thức `@Bean`:

```java
@Configuration
class OrderConfiguration {
    @Bean
    OrderService orderService() {
        return new OrderServiceImpl();
    }
}
```

Đây là hai cách **thay thế** để đăng ký cùng vai trò bean, không phải hai snippet để bật đồng thời cho cùng một target. Chúng chỉ cho thấy nơi Spring lấy bean definition. Class có `@Service` phải nằm trong phạm vi component scanning; `@Bean` tạo và trả về object để container quản lý.

Không nên nhầm việc Spring biết bean definition với thời điểm target được tạo. Singleton thông thường thường được pre-instantiate khi context khởi động, nhưng cũng có thể chỉ được tạo khi được yêu cầu nếu có cấu hình lazy. Với prototype hoặc bean có scope khác, vòng đời khởi tạo và số instance có thể thay đổi.

### 3.2. Container tạo và cấu hình target

Khi cần một `OrderService`, Spring chọn constructor hoặc factory method thích hợp để tạo đối tượng:

1. Giải quyết những dependency cần thiết cho việc gọi constructor/factory method.
2. Tạo target object.
3. Điền field/setter dependencies và cấu hình thuộc tính mà Spring chịu trách nhiệm.
4. Gọi các callback `BeanPostProcessor.postProcessBeforeInitialization(...)`.
5. Thực hiện initialization callbacks thích hợp, chẳng hạn `@PostConstruct`, `InitializingBean.afterPropertiesSet()` hoặc custom init method.
6. Gọi `BeanPostProcessor.postProcessAfterInitialization(...)`. Auto-proxy creator có thể trả **một proxy khác instance target**.

Ở đây, thứ tự callback là logic của bean lifecycle; không có ý nghĩa rằng method nghiệp vụ chạy qua AOP trong constructor hoặc `@PostConstruct`. Target đang được xây dựng thường chưa được caller khác sử dụng thông qua proxy cuối cùng.

### 3.3. Tại sao `new OrderServiceImpl()` trong `@Bean` vẫn hoạt động?

Trong một factory method được container gọi, `new` tạo đối tượng mà phương thức **trả về cho Spring**. Spring tiếp tục quản lý object ấy, chạy hậu xử lý và có thể xuất bản proxy. Nhưng nếu nghiệp vụ tự viết:

```java
OrderService x = new OrderServiceImpl();
x.process("OUTSIDE");
```

thì biến `x` là tham chiếu đến object không tự đăng ký với container; Spring không tự đan AOP proxy vào lệnh gọi đó. Vì vậy vấn đề nằm ở **cách reference được cấp và sử dụng**, không phải chỉ ở sự xuất hiện của toán tử `new`.

## 4. Auto-proxy creator chọn bean và xây dựng proxy

### 4.1. Auto-proxy creator là thành phần nào?

Spring AOP sử dụng hạ tầng `BeanPostProcessor`. Với khai báo `@Aspect`, `@EnableAspectJAutoProxy` hoặc auto-configuration tương ứng sẽ đăng ký cơ chế tự tìm advisor/advice và tạo proxy khi phù hợp. Các implementation thuộc họ `AbstractAutoProxyCreator` thực hiện phần quan trọng này; đây là thành phần hạ tầng Spring, ứng dụng thường không tự gọi nó.

Một sequence khái quát:

```text
target object + bean name + bean class
                    |
         auto-proxy creator kiểm tra
                    |
     Có cần áp dụng advisor cho bean này?
              /             \
            không            có
             |                |
      trả target cũ      chọn advisors
                              |
                         chọn proxy type
                              |
                         tạo AOP proxy
                              |
                         trả proxy
```

Advisor chứa điều kiện áp dụng (pointcut) và advice. Nếu không có advisor phù hợp, hoặc bean không thuộc nhóm có thể auto-proxy, container có thể công bố **chính target**. Không thể suy ra cứ có `@Service`, `@Aspect` hoặc bật Spring AOP là mọi bean đều được proxy.

### 4.2. Khi nào chọn JDK proxy hoặc CGLIB?

Trong Spring Framework theo mặc định `@EnableAspectJAutoProxy(proxyTargetClass = false)`:

- Nếu target triển khai interface phù hợp, Spring có thể tạo **JDK dynamic proxy** thực hiện các interface đó.
- Nếu target không có interface để proxy, Spring tạo class-based proxy (CGLIB).
- Với `proxyTargetClass = true`, Spring chọn class-based proxy khi class có thể được proxy; `final class` không thể tạo subclass, `final`/`private` method không thể bị advice theo cơ chế override.

Spring Boot auto-configured AOP thường đặt `spring.aop.proxy-target-class=true` theo mặc định. Vì vậy cần kiểm tra cấu hình thực tế khi so sánh ứng dụng Spring Framework thuần và Spring Boot.

Sự khác biệt cũng quan trọng với injection: JDK proxy triển khai interface nên consumer nên inject theo interface; nếu consumer yêu cầu concrete class mà Spring trả JDK proxy, có thể lỗi tương thích kiểu. CGLIB proxy là subclass của target nên có thể tương thích với concrete class nếu class không bị giới hạn proxy.

### 4.3. Spring xuất bản **proxy reference** ra sao?

Giả sử target có tên bean `orderServiceImpl`. Thông thường, auto-proxy creator trả đối tượng proxy như kết quả xử lý bean. Khi bean khác tìm dependency theo kiểu hoặc tên, `BeanFactory` cấp **tham chiếu bean sau hậu xử lý**. Với singleton thông thường, các lần lấy lại bean từ cùng context/definition sẽ nhận tham chiếu singleton đã được công bố, không tự tái tạo proxy mới ở mỗi lần inject.

```java
OrderService service = context.getBean(OrderService.class);
System.out.println(AopUtils.isAopProxy(service));
```

Nếu `OrderService` bị advice và đã được proxy, kết quả là `true`. Nếu không có advisor phù hợp thì có thể là `false`, dù `OrderService` vẫn là Spring bean hợp lệ.

**Không đồng nhất proxy và target bằng object identity.** Với AOP proxy, `service.getClass()` có thể là class proxy của JDK hoặc class do CGLIB tạo; việc so sánh `service.getClass() == OrderServiceImpl.class` không phải phép kiểm tra đáng tin cho AOP. Hãy dùng `AopUtils.isAopProxy` và kiểm tra kiểu proxy khi cần.

## 5. Consumer nhận proxy qua Dependency Injection

### 5.1. Constructor injection làm luồng phụ thuộc rõ ràng

```java
@Component
class CheckoutWorkflow {
    private final OrderService service;

    CheckoutWorkflow(OrderService service) {
        this.service = service;
    }

    void checkout(String orderId) {
        service.process(orderId);
    }
}
```

Đây là snippet để minh họa; chương trình hoàn chỉnh nằm ở mục 7.

Khi Spring khởi tạo `CheckoutWorkflow`, nó phải resolve tham số `OrderService` trước khi gọi constructor. Nếu singleton target chưa được tạo, Spring xây dựng nó trước; sau bước auto-proxy, container dùng reference cuối cùng để inject. Vì vậy biến `service` của consumer có thể trỏ đến **proxy**.

### 5.2. Thứ tự thực tế phụ thuộc việc bean nào được tạo trước

Không nhất thiết mọi bean có thứ tự khởi tạo toàn cục cố định. Nếu consumer chưa được tạo nhưng Spring đã pre-instantiate target singleton, DI chỉ lấy reference có sẵn. Nếu consumer là bean khởi tạo sớm và cần target trước đó, thao tác resolve dependency khiến target được tạo trước consumer. Trong cả hai tình huống thông thường, mục tiêu của Spring là cấp dependency đã được container xử lý phù hợp.

### 5.3. Khi consumer gọi method

```text
CheckoutWorkflow.checkout()
          |
          | service.process("A-001")
          v
   AOP proxy của OrderService
          |
       [advice]
          |
   OrderServiceImpl.process()
```

Chỉ **lời gọi qua proxy** đi vào Spring AOP advice. Nếu bên trong `OrderServiceImpl.process()` có `this.anotherMethod()`, lời gọi nội bộ đó đi thẳng trên target nên advice dành cho `anotherMethod()` không tự chạy. Đây là hệ quả proxy-based AOP, ngay cả khi target là bean đúng chuẩn và consumer nhận proxy đúng cách.

Tương tự, một tham chiếu target bị giữ ngoài Spring, ví dụ từ `new`, không tự được thay đổi thành proxy chỉ vì class tương ứng cũng có một Spring bean.

## 6. Phân biệt bean lifecycle callbacks với lời gọi nghiệp vụ qua proxy

| Thời điểm | Diễn ra trên đối tượng nào? | Có nên chờ advice chạy? |
| --- | --- | --- |
| Constructor/factory method của target | Target đang được tạo | Không |
| Setter injection / field injection | Target đang được cấu hình | Không |
| `@PostConstruct`, `afterPropertiesSet` hoặc custom init callback | Thông thường target trước khi xuất bản proxy cuối cùng | Không nên |
| `postProcessAfterInitialization` trong auto-proxy creator | Nhận bean/target; có thể trả proxy | Đây là bước chuẩn bị proxy, chưa phải method nghiệp vụ qua proxy |
| Consumer gọi `service.process()` trên reference do Spring inject | Proxy, sau đó target | Có, nếu advisor/pointcut phù hợp |
| Target gọi `this.process()` | Chính target | Không, vì bỏ qua proxy |
| `@PreDestroy`/destroy callback | Do container quản lý lifecycle của bean | Không nên dựa vào advice để dọn dẹp |

Việc bean đã có một proxy sau initialization không có nghĩa mọi callback trong constructor, `@PostConstruct` hay `@PreDestroy` đều sẽ được AOP intercept. Đừng đặt logic bắt buộc dùng `@Transactional`, security advice hoặc caching advice bên trong chính lifecycle callback và kỳ vọng chúng hoạt động như lời gọi ngoài qua proxy.

Hạ tầng `BeanPostProcessor` phải được khởi tạo sớm. Những post-processor và một số dependency trực tiếp được tạo sớm có thể **không đủ điều kiện để trải qua toàn bộ post-processing/auto-proxying**; Spring có thể cảnh báo rằng bean không đủ điều kiện để tất cả post-processors xử lý. Khi tự viết `BeanPostProcessor`, hãy kiểm tra dependency và tránh khởi tạo không cần thiết các bean nghiệp vụ quá sớm.

## 7. Ví dụ chạy được: thấy target init, proxy và dependency injection

Ví dụ sử dụng **Java 17 + Spring Framework 6.2.x + Maven**, không cần Spring Boot. Hạ tầng `@EnableAspectJAutoProxy` tìm aspect, chọn bean service và công bố proxy cho `CheckoutWorkflow`.

Cấu trúc dự án:

```text
spring-auto-proxy-flow/
├── pom.xml
└── src/main/java/demo/autoproxy/
    ├── AppConfig.java
    ├── OrderService.java
    ├── OrderServiceImpl.java
    ├── TraceAspect.java
    ├── CheckoutWorkflow.java
    └── Main.java
```

### 7.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-auto-proxy-flow</artifactId>
    <version>1.0-SNAPSHOT</version>

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

### 7.2. `AppConfig.java` — đăng ký scanner và auto-proxy

```java
package demo.autoproxy;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy
public class AppConfig {
}
```

`@ComponentScan` tìm các Spring beans trong `demo.autoproxy`, còn `@EnableAspectJAutoProxy` cung cấp hạ tầng phân tích `@Aspect` và tự tạo proxy. Với cấu hình Spring Framework thuần này, service có interface nên proxy thường là JDK dynamic proxy.

### 7.3. `OrderService.java` — hợp đồng mà consumer cần

```java
package demo.autoproxy;

public interface OrderService {
    void process(String orderId);
}
```

### 7.4. `OrderServiceImpl.java` — target và init callback

```java
package demo.autoproxy;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Service;

@Service
public class OrderServiceImpl implements OrderService, InitializingBean {
    @Override
    public void afterPropertiesSet() {
        System.out.println("[target] initialized");
    }

    @Override
    public void process(String orderId) {
        System.out.println("[target] process " + orderId);
    }
}
```

Chọn `InitializingBean` để thể hiện lifecycle callback mà không cần cấu hình `@PostConstruct`. Method `afterPropertiesSet()` do container gọi trong bước initialization của target. Nó không phải lời gọi business qua proxy.

### 7.5. `TraceAspect.java` — aspect được Spring quản lý

```java
package demo.autoproxy;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {
    @Before("execution(* demo.autoproxy..*.process(..))")
    public void beforeProcess() {
        System.out.println("[advice] before process");
    }
}
```

`@Aspect` mô tả aspect; `@Component` làm Spring phát hiện và quản lý aspect như bean. Pointcut chỉ chọn phương thức `process` trong package demo này, nên target `OrderServiceImpl` được advice.

### 7.6. `CheckoutWorkflow.java` — bean nhận tham chiếu do Spring cấp

```java
package demo.autoproxy;

import org.springframework.aop.support.AopUtils;
import org.springframework.stereotype.Component;

@Component
public class CheckoutWorkflow {
    private final OrderService service;

    public CheckoutWorkflow(OrderService service) {
        this.service = service;
        System.out.println("[consumer] injected proxy="
                + AopUtils.isAopProxy(service));
    }

    public void checkout() {
        System.out.println("[consumer] checkout");
        service.process("A-001");
    }
}
```

Consumer nhận `OrderService` thông qua constructor. Không tạo `new OrderServiceImpl()`, nên nó sử dụng reference Spring cung cấp. `AopUtils.isAopProxy(service)` chỉ dùng để chẩn đoán trong ví dụ.

### 7.7. `Main.java` — tạo context và gọi consumer

```java
package demo.autoproxy;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(CheckoutWorkflow.class).checkout();
        }
    }
}
```

Chạy ở thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.autoproxy.Main
```

**Những dòng stdout được chương trình in ra** (các log Maven/Spring có thể xuất hiện tùy môi trường):

```text
[target] initialized
[consumer] injected proxy=true
[consumer] checkout
[advice] before process
[target] process A-001
```

Diễn giải:

1. `OrderServiceImpl` được Spring tạo, đi qua lifecycle, chạy `afterPropertiesSet()` và in `[target] initialized`.
2. Khi `CheckoutWorkflow` được tạo và constructor nhận `OrderService`, hạ tầng AOP đã bọc bean service; Spring inject proxy nên in `[consumer] injected proxy=true`.
3. Gọi `checkout()` trên consumer dẫn đến lời gọi `service.process("A-001")`. Lời gọi qua Spring AOP proxy chạy `@Before`, sau đó thực thi target `process()`.
4. `CheckoutWorkflow` không có advice khớp nên nó **không nhất thiết** bị proxy; Spring có thể inject một proxy cho dependency của nó trong khi bản thân consumer vẫn là bean thường.
5. Số lần tạo target và proxy phụ thuộc bean scope và cấu hình. Với singleton thông thường trong ví dụ, Spring xuất bản một reference singleton của service được xử lý cho consumer.

**Về tính xác định của thứ tự log:** Không có tác vụ concurrent, aspect không in gì ở giai đoạn khởi tạo, và consumer constructor cần resolve `OrderService`. Do đó dòng target initialization đứng trước dòng consumer injected; hai dòng advice/business được in khi gọi `checkout()`.

## 8. Thử thay đổi ví dụ để quan sát ranh giới proxy

### 8.1. Tự tạo target bằng `new` trong consumer

Đổi phương thức `checkout()` thành:

```java
public void checkout() {
    System.out.println("[consumer] checkout");
    OrderService unmanaged = new OrderServiceImpl();
    unmanaged.process("B-002");
}
```

Đây là đoạn **thay thế method** trong `CheckoutWorkflow`, không phải class độc lập. Lần gọi `unmanaged.process("B-002")` trực tiếp trên object tự tạo nên không xuất hiện `[advice] before process` cho `B-002`. Nó cũng không đi qua initialization callback của Spring; `afterPropertiesSet()` không tự chạy do object chỉ được tạo bằng toán tử Java `new`.

Trong khi đó field `service` được inject lúc constructor vẫn là proxy. Sự tồn tại của field này không tự biến biến `unmanaged` thành proxy.

### 8.2. Bỏ aspect

Bỏ `@Component` trên `TraceAspect` và không đăng ký aspect đó bằng `@Bean`. Khi không còn advisor nào khác cần bọc service, service có thể được công bố dưới dạng target thô; khi đó `AopUtils.isAopProxy(service)` cho `false`. Service **vẫn là Spring bean**, nhưng không có advice tương ứng.

### 8.3. Dùng factory method `@Bean` thay vì `@Service`

Có thể bỏ `@Service` khỏi `OrderServiceImpl` rồi thêm vào `AppConfig`:

```java
@Bean
OrderService orderService() {
    return new OrderServiceImpl();
}
```

Đây là fragment trong class `@Configuration`, cần import `org.springframework.context.annotation.Bean`. Object được trả về là target **do container quản lý**; Spring vẫn có cơ hội chạy lifecycle, auto-proxy và inject reference cho consumer. Việc factory dùng `new` không khiến nó thành object ngoài Spring.

### 8.4. Đổi sang class-based proxy

Thay `@EnableAspectJAutoProxy` thành:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
```

Khi service class có thể được subclass, Spring sẽ dùng CGLIB proxy. Với ví dụ này, `AopUtils.isAopProxy(service)` vẫn trả `true`. Nếu cần phân biệt loại proxy, in thêm:

```java
System.out.println(AopUtils.isJdkDynamicProxy(service));
System.out.println(AopUtils.isCglibProxy(service));
```

Hai dòng code trên là phần chèn minh họa vào consumer hoặc một method có biến `service`. Đối với ví dụ cấu hình ban đầu, kết quả kỳ vọng tương ứng là `true`, `false`; sau khi ép class-based proxy là `false`, `true`. Việc đổi loại proxy không làm self-invocation được advice.

## 9. Các ngoại lệ và giới hạn cần hiểu chính xác

### 9.1. Circular dependency và “early bean reference”

Nếu bean A cần B và B lại cần A, Spring có thể gặp **circular dependency**. Với một số trường hợp singleton sử dụng setter/field injection, BeanFactory có cơ chế cung cấp một **early reference** trước khi đối tượng hoàn tất initialization để giải quyết vòng phụ thuộc. Hạ tầng AOP có thể tham gia qua `SmartInstantiationAwareBeanPostProcessor.getEarlyBeanReference(...)` nhằm bảo đảm reference sớm phù hợp với proxy cuối cùng.

Tuy nhiên, đây là **đường đặc biệt**, không phải quy trình thông thường của mọi bean:

- Không nên dạy rằng Spring luôn tạo proxy **sau** khi đã inject hết vào tất cả các bean; early proxy có thể xuất hiện trước khi quá trình khởi tạo target hoàn tất.
- Không phải mọi circular dependency đều giải quyết được. Đặc biệt, vòng phụ thuộc constructor không thể được giải quyết như vòng setter thông thường.
- Spring Boot hiện đại mặc định hạn chế circular references. Không nên bật cấu hình cho phép vòng phụ thuộc chỉ để che vấn đề thiết kế.
- Nếu một bean đã nhận target thô nhưng sau đó target được proxy, Spring có thể báo lỗi liên quan raw injection dù bean cuối cùng là proxy. Giải pháp tốt là loại bỏ cycle và để các bean nhận reference cuối cùng ổn định.

Vì vậy sơ đồ mục 2 là **happy path** cho bean không có vòng phụ thuộc; khi debug vòng dependency phải xem việc cung cấp early reference và actual proxy.

### 9.2. `BeanPostProcessor` không thể kỳ vọng được auto-proxy như bean nghiệp vụ

`BeanPostProcessor` cần được tạo rất sớm để hậu xử lý những bean đến sau. Chính các post-processor và một số dependency mà chúng cần khởi tạo sớm thường không đủ điều kiện nhận toàn bộ xử lý AOP. Dòng cảnh báo Spring thường chứa nội dung tương tự `Bean '...' is not eligible for getting processed by all BeanPostProcessors`.

Nếu viết `@Bean` trả `BeanPostProcessor`, cần chú ý khai báo kiểu trả về để Spring phát hiện sớm; cách khai báo `static @Bean` ít dependency thường tránh việc tạo sớm nhiều bean không cần thiết. Đừng đặt business dependency phức tạp vào chính auto-proxy-related processors nếu không có lý do.

### 9.3. Scope và proxy khác nhau

- **Singleton**: một Spring bean instance/reference cho mỗi bean definition trong container theo singleton scope; với AOP, reference được công bố có thể là singleton proxy.
- **Prototype**: mỗi lần container xử lý yêu cầu bean có thể tạo một target mới và một proxy mới nếu cần; việc inject prototype trực tiếp vào singleton thường chỉ resolve một lần lúc xây dựng singleton.
- **Scoped proxy**: dùng để trì hoãn resolution đến đúng scope, là một hình thức proxy khác; có thể kết hợp với Spring AOP. Thấy tên class dạng proxy chưa đủ để khẳng định aspect advice đang chạy.

### 9.4. `FactoryBean` khác `@Bean`

`FactoryBean<T>` là một contract của Spring cung cấp sản phẩm từ `getObject()`; factory method gắn `@Bean` chỉ là một cách khai báo bean definition. Hai khái niệm không tương đương. Khi xử lý `FactoryBean`, container có thêm lớp tra cứu sản phẩm và có đường hậu xử lý riêng; đừng áp sơ đồ singleton thuần một cách máy móc.

### 9.5. Cùng class, hai `ApplicationContext`

Một bean thuộc context A không mặc nhiên được advice chỉ vì aspect tồn tại ở context B. Hạ tầng auto-proxy và khả năng tìm thấy advisor có phạm vi theo container. Ứng dụng có parent/child contexts cần kiểm tra nơi khai báo target, aspect, auto-proxy creator và nơi consumer lấy reference.

### 9.6. Không phải mọi method đều có thể bị advice

Với Spring AOP dựa trên proxy, chỉ các method invocation đi qua proxy mới có cơ hội chạy advice; CGLIB không override được `private` hay `final` method, còn JDK proxy phơi bày interface contract. Pointcut phải khớp phương thức thực tế. Self-invocation `this.method()` bypass proxy trong cả hai kiểu.

## 10. Checklist chẩn đoán “đã inject rồi mà aspect không chạy”

| Câu hỏi | Tác động đến luồng |
| --- | --- |
| Target đã đăng ký thành Spring bean? | Nếu tự `new` bên ngoài container, không có auto-proxy chuẩn |
| Component scan có phủ package của service và aspect? | Không tìm được bean definition hoặc advisor nếu scan sai |
| `@Aspect` có được đăng ký qua `@Component`/`@Bean`? | `@Aspect` đơn lẻ không bảo đảm aspect thành Spring bean |
| Spring AOP đã bật chưa? | Cần `@EnableAspectJAutoProxy` hoặc auto-configuration phù hợp |
| Advisor/pointcut có khớp service method? | Không khớp thì có thể trả target trực tiếp |
| Consumer nhận bean qua Spring DI? | Reference được inject mới có cơ hội là proxy |
| `AopUtils.isAopProxy(injectedService)` trả gì? | Phân biệt reference proxy và target |
| Đường gọi là `consumer -> injectedService.method()` hay `this.method()`? | Chỉ đường qua proxy được intercept |
| Kiểu proxy tương thích kiểu injection? | JDK proxy không phải implementation class; CGLIB bị giới hạn `final` |
| Có circular dependency/early bean hoặc khởi tạo quá sớm? | Có thể nhận reference sớm hoặc không được hậu xử lý đầy đủ |
| Có nhiều context hoặc scope đặc biệt? | Có thể đang sử dụng bean/reference ngoài phạm vi advisor |
| Code kỳ vọng advice trong `@PostConstruct`? | Callback khởi tạo target không tương đương external invocation qua proxy |

Một cách kiểm tra có hệ thống là: xác định bean definition → xem điều kiện/giới hạn auto-proxy → lấy reference thực tế từ consumer → kiểm tra proxy với `AopUtils` → quan sát lời gọi qua reference đó → kiểm tra pointcut và self-invocation. Đường đi này giúp phân biệt lỗi tạo bean, lỗi tạo proxy và lỗi gọi sai reference.

## 11. Câu hỏi ôn tập

**1. Spring tạo target rồi mới tạo proxy trong mọi trường hợp?** Với singleton bình thường, proxy thường được tạo sau initialization callback. Có ngoại lệ early proxy khi cần giải quyết một số circular dependency hoặc khi hạ tầng post-processing đặc biệt tham gia.

**2. Vì sao constructor của consumer có thể nhận AOP proxy dù khai báo kiểu interface của service?** Khi resolve dependency, Spring cấp bean reference do container công bố. Với JDK proxy, reference đó triển khai interface nên đáp ứng constructor parameter.

**3. Spring AOP có tạo proxy cho mọi bean không?** Không. Auto-proxy creator xét advisor/pointcut và các quy tắc áp dụng; bean không cần interception có thể được công bố nguyên trạng.

**4. Lệnh `new ServiceImpl()` bên trong phương thức `@Bean` có bị mất AOP không?** Không. Object được **trả về** từ phương thức `@Bean` được Spring quản lý và có thể được auto-proxy.

**5. Tại sao `@PostConstruct` không chắc kích hoạt advice?** Vì nó thuộc bước initialization trên target, thông thường xảy ra trước khi consumer dùng reference proxy để gọi business method.

**6. Làm sao chắc consumer đã nhận proxy?** Kiểm tra ngay reference được Spring inject bằng `AopUtils.isAopProxy(...)` và loại proxy bằng `isJdkDynamicProxy` / `isCglibProxy` nếu cần; cũng cần pointcut thực sự khớp phương thức được gọi.

**7. Nếu một bean đã nhận target thô trong circular dependency thì sao?** Reference đó có thể khác proxy cuối và khiến behavior không nhất quán hoặc bean creation thất bại; giải pháp bền vững là bỏ vòng phụ thuộc và đưa việc gọi qua reference bean ổn định.

## Tài liệu chính thức của Spring

- [Spring Framework — Container Extension Points / BeanPostProcessor](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework — @AspectJ support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework — Proxying Mechanisms và self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework 6.2 — Using the Auto-proxy Facility](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/autoproxy.html)
- [Spring Framework — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
