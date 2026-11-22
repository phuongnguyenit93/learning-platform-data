# Vai trò của auto-proxy creator trong ApplicationContext

## 1. Auto-proxy creator là gì và giải quyết vấn đề gì?

Trong một ứng dụng Spring, `OrderService`, `PaymentService` hoặc `InventoryService` thường được lấy qua dependency injection hoặc `ApplicationContext.getBean()`. Khi lập trình viên định nghĩa một aspect để ghi log, đo thời gian hay áp dụng chính sách chung, họ thường **không tự tạo proxy cho từng service**. Spring thực hiện việc đó nhờ thành phần hạ tầng gọi là **auto-proxy creator**.

**Auto-proxy creator** là một loại **`BeanPostProcessor` của Spring** có khả năng quan sát các bean được container tạo ra, xác định liệu bean có cần advisor/advice hay không, rồi cung cấp một **AOP proxy** thay cho đối tượng bean gốc khi cần. Nhờ vậy:

- Các bean đích không phải biết cụ thể về `@Aspect`, advisor, interceptor hoặc cách tạo proxy.
- Một chính sách AOP có thể áp dụng nhất quán lên nhiều Spring-managed beans theo pointcut.
- Caller nhận **tham chiếu do container trả về**; nếu bean đủ điều kiện, tham chiếu đó là proxy có chuỗi interceptor cần thiết.
- Bean không khớp advisor nào có thể được trả về bình thường, không cần proxy AOP do cấu hình đó tạo ra.

Phạm vi bài này là **auto-proxy creator của Spring AOP bên trong `ApplicationContext`**, đặc biệt khi dùng khai báo `@Aspect` và `@EnableAspectJAutoProxy`. Đây là cơ chế proxy trong Spring, **không phải compile-time hay load-time weaving của AspectJ**.

Một quy tắc cần nhớ ngay từ đầu:

> **Auto-proxy creator chọn và tạo proxy trong vòng đời quản lý bean; advice chạy khi một phương thức phù hợp được gọi qua proxy.** Hai thời điểm này khác nhau.

## 2. Nó đứng ở đâu trong `ApplicationContext`?

Sơ đồ giản lược:

```text
@Configuration / <aop:aspectj-autoproxy/> / Boot AOP configuration
                         |
                         v
           Đăng ký auto-proxy creator
           như một BeanPostProcessor
                         |
                         v
ApplicationContext khởi tạo và đăng ký các BeanPostProcessor
                         |
                         v
             Tạo target bean từ definition
                         |
                         v
            Inject dependency, init callbacks
                         |
                         v
Auto-proxy creator xem xét bean sau khởi tạo
         |                               |
         | Có advisor phù hợp            | Không có advisor phù hợp
         v                               v
   Tạo AOP proxy                  Giữ bean không có AOP proxy
         |                               |
         +---------------+---------------+
                         |
                         v
            Expose bean từ ApplicationContext
                         |
                         v
Caller gọi qua proxy -> advice -> target method
```

Sơ đồ mô tả đường thông thường khi bean khởi tạo hoàn tất. Spring còn có các hook hỗ trợ tham chiếu sớm cho tình huống tạo bean phức tạp; vì thế **không nên hiểu đây là một thuật toán cố định áp dụng nguyên xi cho mọi bean**. Điểm cần nắm là auto-proxy creator được đăng ký đủ sớm với container để tham gia xử lý những bean được tạo sau đó.

### 2.1. Phân biệt các đối tượng

| Đối tượng | Được ai quản lý? | Trách nhiệm |
| --- | --- | --- |
| `ApplicationContext` | Spring runtime | Điều phối bean definitions, post-processors, scopes, lifecycle và lookup. |
| **Auto-proxy creator** | Đăng ký như bean `BeanPostProcessor` trong context | Tìm candidate advisors/aspects, đánh giá khả năng áp dụng, tạo proxy khi cần. |
| **Aspect bean** | Spring IoC | Chứa `@Aspect`, pointcut/advice cho hành vi chung. |
| **Advisor** | Spring AOP infrastructure | Kết hợp advice với điều kiện áp dụng/pointcut; là dữ liệu để auto-proxy creator lựa chọn. |
| **Target bean** | Spring IoC | Chứa mã nghiệp vụ thực sự. |
| **AOP proxy** | Spring AOP tạo và trao cho caller | Chuyển lời gọi phương thức qua interceptor chain trước khi đến target. |

Auto-proxy creator **không thay thế** bean factory. Bean factory vẫn tạo/inject/khởi tạo target theo hợp đồng của Spring; auto-proxy creator tham gia giai đoạn post-processing để có thể bọc bean đó.

## 3. Vì sao auto-proxy creator lại là `BeanPostProcessor`?

`BeanPostProcessor` là điểm mở rộng cho phép Spring xử lý **đối tượng bean** ở thời điểm container tạo ra nó, thay vì chỉ chỉnh bean definition. Hai callback cơ bản là:

```java
Object postProcessBeforeInitialization(Object bean, String beanName);
Object postProcessAfterInitialization(Object bean, String beanName);
```

Đây là **chữ ký được giản lược để học**, không phải một class Java độc lập. Trong quy trình thông thường, auto-proxy creator kế thừa hạ tầng `AbstractAutoProxyCreator`, sử dụng các callback thích hợp để quyết định trả về proxy hay giữ bean hiện tại.

Khi một `@Bean` hoặc `@Component` được tạo:

1. Spring xử lý việc tạo instance, inject dependency và callbacks theo lifecycle.
2. Auto-proxy creator xem tên/class/metadata và các advisor có thể áp dụng.
3. Nếu có advice tương ứng, nó xây dựng proxy phù hợp, gắn các advisor/interceptor đã chọn.
4. Spring công bố tham chiếu cuối cùng cho những caller lấy bean từ container.

Về mặt kết quả, các client nhận bean qua DI hoặc `context.getBean()` có thể chỉ thấy **proxy**; việc gọi một method qua tham chiếu này kích hoạt advisor chain. Nếu caller tự `new` target object hoặc giữ raw target reference từ bên ngoài, Spring không thể tự áp dụng proxy của `ApplicationContext` lên reference đó.

**Không nên nhầm với `BeanFactoryPostProcessor`:** loại latter xử lý **metadata/bean definitions**, còn `BeanPostProcessor` xử lý **instances**. Auto-proxy creator thuộc nhóm xử lý bean instances, không phải một bước thay đổi source code của class.

## 4. Auto-proxy creator lấy thông tin advice từ đâu?

Tùy cấu hình, Spring có thể có các **`Advisor` beans** hoặc **aspect beans** có `@Aspect`. Với cấu hình `@EnableAspectJAutoProxy`, Spring đăng ký lớp hỗ trợ kiểu `@AspectJ` để nhận diện aspect beans trong chính context, chuyển các khai báo advice thành advisor và xem advisor nào thích hợp với bean đang được tạo.

Ví dụ:

```java
@Aspect
public class AuditAspect {
    @Before("execution(public * com.example.shop.*Service.*(..))")
    public void audit() {
        // Ghi sự kiện trước khi service method thực thi.
    }
}
```

Đây là **fragment minh họa**, chưa gồm import/đăng ký bean. Nếu `AuditAspect` được đăng ký vào Spring context và chế độ `@AspectJ` được kích hoạt, Spring có thể tìm ra advice `audit()` và áp dụng nó cho các method khớp biểu thức. Một `InventoryService.update()` nằm trong package ví dụ có thể được proxy; một `HealthStatus.ping()` không khớp pointcut sẽ không bị proxy chỉ bởi aspect đó.

Một số tiêu chí đánh giá:

- **Bean có được Spring quản lý?** Annotation `@Aspect` một mình không tự tạo bean; thường khai báo `@Aspect` + `@Component` hoặc `@Bean`.
- **Aspect/advisor có thuộc context liên quan?** Auto-proxy creator hoạt động trong miền container cụ thể.
- **Class/method có khớp pointcut?** Một aspect tồn tại không đồng nghĩa mọi bean đều bị proxy.
- **Bean có thuộc nhóm cần bỏ qua?** Advice, advisor, aspect class và những bean hạ tầng nhất định không được chính cơ chế Spring AOP này tự proxy.
- **Proxy strategy có hợp lệ?** Interface-based proxy và class-based proxy có giới hạn khác nhau; class/method `final` không thể được override bởi CGLIB.

Trong Spring Framework, lớp thường dùng cho `@AspectJ` auto-proxying là:

```text
org.springframework.aop.aspectj.annotation.AnnotationAwareAspectJAutoProxyCreator
```

Nó kế thừa hạ tầng `AspectJAwareAdvisorAutoProxyCreator` / `AbstractAdvisorAutoProxyCreator`, xử lý cả **Spring Advisor** và các aspect khai báo bằng annotation. Đây là **class hạ tầng**, thông thường người học không cần tự khai báo `@Bean` hay `new AnnotationAwareAspectJAutoProxyCreator()`; cứ dùng cấu hình Spring cung cấp.

## 5. Kích hoạt auto-proxy creator trong một ứng dụng Spring

### 5.1. Java configuration — `@EnableAspectJAutoProxy`

```java
@Configuration
@EnableAspectJAutoProxy
public class AopConfig {
}
```

Đây là **fragment cấu hình**. Annotation yêu cầu Spring bật hỗ trợ auto-proxy dựa trên các aspect `@Aspect` được quản lý. Trong ứng dụng Spring Framework thuần, bạn còn cần `spring-context`/Spring AOP và thư viện `aspectjweaver` để phân tích cú pháp `@AspectJ` (ví dụ thông qua Maven/Gradle).

Annotation **không biến mọi class mang `@Aspect` thành bean**. Aspect phải thực sự được đăng ký, chẳng hạn `@Aspect` + `@Component` nằm trong component scan hoặc `@Bean` trả về class aspect.

Có thể cấu hình:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true, exposeProxy = false)
```

- `proxyTargetClass = true`: ưu tiên **class-based proxy** (CGLIB).
- `proxyTargetClass = false`: sử dụng chiến lược proxy mặc định; khi target có interface phù hợp thường chọn JDK dynamic proxy.
- `exposeProxy = true`: cho phép truy cập proxy hiện hành qua `AopContext.currentProxy()` trong lời gọi AOP được expose. Đây là tùy chọn nâng cao có chi phí và coupling, **không phải cách sửa self-invocation mặc định**.

### 5.2. XML configuration

```xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
```

Dòng trên cần đặt trong XML hợp lệ đã khai báo namespace `aop`; đây chỉ là **fragment**, không phải toàn bộ tài liệu XML. Nó yêu cầu hỗ trợ auto-proxy cho `@AspectJ` bằng Spring tương tự Java annotation.

Một cấu hình XML khác có `<aop:config>` hoặc một tính năng dựa vào proxy như `<tx:annotation-driven>` cũng có thể đăng ký/nâng cấp hạ tầng auto-proxy. Spring thống nhất các cấu hình hạ tầng chuẩn để tránh tạo một auto-proxy creator riêng cho mỗi dòng XML.

### 5.3. Spring Boot

Với Spring Boot, thông thường starter AOP và auto-configuration đã đảm nhiệm việc bật hạ tầng phù hợp. Ví dụ Boot 3.x dùng `spring-boot-starter-aop`; Boot 4.x có `spring-boot-starter-aspectj`. Không cần thêm `@EnableAspectJAutoProxy` chỉ để “bật thêm một lần” nếu Boot đã cấu hình AOP đúng.

Khi thay đổi chế độ proxy ở Boot, kiểm tra property `spring.aop.proxy-target-class` và các cấu hình proxy khác thật sự được nạp. **Property của Boot không thay thế việc hiểu cơ chế auto-proxy creator trong Spring container**, và không nên suy từ starter rằng AspectJ weaving đang hoạt động.

## 6. Ví dụ hoàn chỉnh: nhìn thấy auto-proxy creator trong `ApplicationContext`

Ví dụ dùng **Java 17+, Spring Framework 6.1.14, AspectJ 1.9.22.1 và Maven**, không cần Spring Boot hoặc máy chủ web. Mục tiêu quan sát được:

1. `ApplicationContext` có bean auto-proxy creator nội bộ.
2. Bean `OrderService` khớp pointcut được tạo proxy.
3. Bean `CatalogInfo` không khớp pointcut nên không bị aspect này yêu cầu proxy.
4. Gọi `OrderService.place()` qua bean lấy từ context chạy advice chính xác một lần.
5. Aspect `AuditAspect` được Spring quản lý nhưng không bị Spring AOP tự proxy.

### 6.1. Cấu trúc project

```text
spring-auto-proxy-demo/
├── pom.xml
└── src/main/java/com/example/apc/
    ├── DemoApp.java
    ├── AppConfig.java
    ├── OrderService.java
    ├── CatalogInfo.java
    └── AuditAspect.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-auto-proxy-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <version>3.13.0</version>
                <artifactId>maven-compiler-plugin</artifactId>
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

`spring-context` cung cấp container và kéo các module Spring liên quan, bao gồm `spring-aop`; `aspectjweaver` cung cấp phần AspectJ cần thiết cho cách khai báo `@Aspect`. Tất cả code bên dưới chạy với dependency của ví dụ; không yêu cầu AspectJ compiler/weaving agent.

### 6.3. `src/main/java/com/example/apc/OrderService.java`

```java
package com.example.apc;

public class OrderService {
    public String place(String orderId) {
        System.out.println("[ORDER] " + orderId);
        return "accepted:" + orderId;
    }
}
```

### 6.4. `src/main/java/com/example/apc/CatalogInfo.java`

```java
package com.example.apc;

public class CatalogInfo {
    public String version() {
        return "v1";
    }
}
```

### 6.5. `src/main/java/com/example/apc/AuditAspect.java`

```java
package com.example.apc;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    private final AtomicInteger invoked = new AtomicInteger();

    @Before("execution(public * com.example.apc.OrderService.place(..))")
    public void beforePlace(JoinPoint joinPoint) {
        invoked.incrementAndGet();
        System.out.println("[AUDIT] " + joinPoint.getSignature().getName());
    }

    public int calls() {
        return invoked.get();
    }
}
```

Aspect này chỉ có một advice dành riêng cho `OrderService.place(..)`. `AtomicInteger` giúp phép đếm an toàn khi có lời gọi đồng thời; một aspect singleton thường được nhiều target calls sử dụng. Code minh họa dùng `println` để quan sát; ứng dụng thực tế nên dùng logging/metrics phù hợp.

### 6.6. `src/main/java/com/example/apc/AppConfig.java`

```java
package com.example.apc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public CatalogInfo catalogInfo() {
        return new CatalogInfo();
    }
}
```

`@Bean auditAspect()` đưa `AuditAspect` vào context. `@EnableAspectJAutoProxy` kích hoạt auto-proxy creator; `proxyTargetClass=true` buộc class-based proxy cho `OrderService` không triển khai interface. `CatalogInfo` cũng là Spring bean, nhưng không có advisor nào khớp nó trong cấu hình này.

### 6.7. `src/main/java/com/example/apc/DemoApp.java`

```java
package com.example.apc;

import org.springframework.aop.config.AopConfigUtils;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            Object creator =
                    context.getBean(AopConfigUtils.AUTO_PROXY_CREATOR_BEAN_NAME);
            OrderService orderService = context.getBean(OrderService.class);
            CatalogInfo catalogInfo = context.getBean(CatalogInfo.class);
            AuditAspect aspect = context.getBean(AuditAspect.class);

            System.out.println("creatorIsBPP="
                    + (creator instanceof BeanPostProcessor));
            System.out.println("orderIsAopProxy=" + AopUtils.isAopProxy(orderService));
            System.out.println("catalogIsAopProxy=" + AopUtils.isAopProxy(catalogInfo));
            System.out.println("aspectIsAopProxy=" + AopUtils.isAopProxy(aspect));

            String result = orderService.place("O-42");
            System.out.println("result=" + result);
            System.out.println("catalog=" + catalogInfo.version());
            System.out.println("adviceCalls=" + aspect.calls());
        }
    }
}
```

Ở ví dụ Spring Framework này, `AopConfigUtils.AUTO_PROXY_CREATOR_BEAN_NAME` là tên hạ tầng nội bộ do Spring dùng cho auto-proxy creator. **Đây là API/chi tiết chẩn đoán thuộc cấu hình cụ thể**, không phải tên một application service để hệ thống bên ngoài dựa vào. Trong ứng dụng Spring Boot hoặc khi cấu hình AOP khác, không nên hardcode một class implementation duy nhất làm điều kiện hoạt động của hệ thống.

### 6.8. Chạy và đọc kết quả

Yêu cầu: JDK 17+, Maven, kết nối để lấy dependencies. Tại thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.apc.DemoApp
```

Các dòng do chính chương trình in ra (không tính thông báo riêng của Maven/SLF4J nếu có):

```text
creatorIsBPP=true
orderIsAopProxy=true
catalogIsAopProxy=false
aspectIsAopProxy=false
[AUDIT] place
[ORDER] O-42
result=accepted:O-42
catalog=v1
adviceCalls=1
```

**Vì sao chương trình cho kết quả đó?**

- `creatorIsBPP=true`: Spring đã đăng ký một bean hạ tầng auto-proxy creator triển khai `BeanPostProcessor`.
- `orderIsAopProxy=true`: advice khớp `OrderService.place(..)`; Spring tạo proxy và trả proxy cho `context.getBean(OrderService.class)`.
- `catalogIsAopProxy=false`: `CatalogInfo.version()` không được advisor này chọn; không có lý do tạo AOP proxy cho `CatalogInfo` trong ví dụ.
- `aspectIsAopProxy=false`: class `@Aspect` được dùng để cung cấp advice, không phải target được Spring AOP tự proxy bằng chính hạ tầng `@AspectJ`.
- `[AUDIT]` xuất hiện **trước** `[ORDER]`: caller gọi qua proxy, `@Before` chạy rồi target method thực thi. `adviceCalls=1` xác nhận số lần chạy advice.

Điều được chứng minh ở đây là **sự tồn tại và kết quả của auto-proxy creator trong một Spring context cụ thể**. Không được suy diễn rằng mọi bean trong Spring đều bị proxy hoặc các giá trị `isAopProxy` trên luôn đúng khi thêm advisor/proxy khác vào application.

## 7. Cách auto-proxy creator chọn bean nào cần proxy

Trong mô hình hỗ trợ `@AspectJ`, luồng quyết định có thể hình dung:

```text
Bean vừa được tạo
    |
    v
Có phải bean hạ tầng/aspect/advisor cần loại trừ?
    | Có
    +--> Bỏ qua auto-proxy kiểu này
    |
    | Không
    v
Tìm advisor có thể áp dụng với class/method của bean
    |
    +--> Không có advisor phù hợp
    |        |
    |        +--> Giữ bean gốc
    |
    +--> Có advisor phù hợp
             |
             v
     Xác định chiến lược proxy
     (interface hoặc class-based)
             |
             v
     Gắn advisor/interceptor vào proxy
             |
             v
     Trả tham chiếu proxy cho caller
```

`AnnotationAwareAspectJAutoProxyCreator` nhận diện advisor beans và các `@Aspect` beans trong context. Nó sử dụng metadata pointcut để biết phương thức nào có thể được advice; không cần chạy thử mọi method rồi mới biết có match.

### 7.1. Không phải mọi bean đều được proxy

Một aspect chỉ áp dụng cho `execution(* com.example..service.*.*(..))` không nên tạo proxy cho toàn bộ lớp cấu hình, DAO hoặc plain DTO chỉ vì các class đó cũng là Spring beans.

**Có bean không được proxy là trạng thái đúng.** Khi xem log startup, đừng kết luận auto-proxy creator không chạy chỉ vì không thấy class mọi bean đổi thành tên proxy.

### 7.2. Auto-proxy creator không quyết định “gọi method nào” thay caller

Spring auto-proxy creator bọc bean trong quá trình quản lý. Sau đó **caller vẫn là nơi gọi method**, và interceptor chain thực hiện advice khi lời gọi đi qua proxy, pointcut phù hợp. Nếu gọi method khác không khớp, proxy có thể chuyển tiếp mà không chạy advice đó.

Với class-based proxy, một đối tượng có thể có nhiều method; việc class đủ điều kiện được bọc proxy không chứng minh rằng mọi method đều có advice. Dùng kiểm thử trên từng method/policy thay vì chỉ `AopUtils.isAopProxy()`.

### 7.3. Hỗ trợ advisor ngoài `@Aspect`

Trong Spring, các chính sách như transaction interception có thể dùng hạ tầng advisor và proxy tương tự. Tùy hạ tầng được bật, auto-proxy creator có thể phối hợp những advisor này; không nên tự tạo một proxy AOP khác ngoài Spring chỉ để thêm logging mà chưa xem advisor hiện hữu.

Cũng cần phân biệt:

- **`BeanNameAutoProxyCreator`**: auto-proxy dựa trên tên bean được cấu hình.
- **`DefaultAdvisorAutoProxyCreator`**: chọn advisors phù hợp cho target beans.
- **`AnnotationAwareAspectJAutoProxyCreator`**: chọn advisors và nhận diện aspects khai báo bằng `@Aspect`.

Đây là các cơ chế lựa chọn trong Spring AOP. Ứng dụng tiêu chuẩn nên cấu hình bằng annotation/XML/starter Spring cung cấp, không tự đăng ký nhiều auto-proxy creators mà không có kiến trúc rõ ràng.

## 8. Một auto-proxy creator hợp nhất không đồng nghĩa chỉ có một advice

Khi dùng nhiều nơi khai báo AOP (Java config, XML, transaction management), Spring có quy tắc **hợp nhất các auto-proxy creator chuẩn trong cùng context**. Ví dụ:

```java
@EnableAspectJAutoProxy(proxyTargetClass = false)
```

và XML:

```xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
```

Khi cùng hiệu lực trong một container, hạ tầng Spring có thể áp dụng lựa chọn proxy mạnh hơn, ví dụ **class-based proxy** đã được yêu cầu bằng `true`. Không thể kết luận rằng câu lệnh annotation với `false` sẽ luôn thắng nếu XML hoặc tính năng Spring khác đã đặt `true`.

Nhưng hợp nhất creator **không loại bỏ các advice trùng chức năng**. Ví dụ:

- Có hai bean khác tên cùng mang class `@Aspect` với một `@Before` y hệt.
- Một Java `@Aspect` và một advisor XML cùng ghi một audit event vào chính method đó.
- Hai aspect khác nhau cố ý ghi log ở cùng join point.

Những trường hợp này có thể chạy nhiều advice. Hãy **đếm các aspect beans/advisors và quan sát method invocation**; không đếm số lượng dòng `@EnableAspectJAutoProxy` rồi suy ra số lần advice chạy.

**Phạm vi Spring Framework:** quy tắc hợp nhất áp dụng cho những hạ tầng proxy tham gia cơ chế chuẩn trong cùng context. Nếu ứng dụng có parent/child contexts, third-party `BeanPostProcessor`, scoped proxy hoặc những proxy được tạo thủ công, cần kiểm tra từng cơ chế và đường gọi cụ thể.

## 9. Những ranh giới của auto-proxy creator trong container

### 9.1. Chỉ nhìn thấy những bean trong phạm vi xử lý của nó

Spring đăng ký `BeanPostProcessor` **theo từng `ApplicationContext`**. Một creator ở parent context không tự post-process những bean chỉ được khởi tạo trong child context, và ngược lại. Với ứng dụng web hoặc hệ thống nhiều context, việc bật `@EnableAspectJAutoProxy` ở một tầng không mặc nhiên áp dụng advice cho mọi controller/service ở tầng khác.

Vì thế khi advice không chạy, hãy kiểm tra **context nào sở hữu target bean và aspect bean** trước khi đổi pointcut.

### 9.2. Bean được tạo quá sớm có thể bỏ lỡ post-processing

Khi `ApplicationContext` khởi động, nó cần tạo và đăng ký `BeanPostProcessor` sớm để áp dụng cho các bean thông thường. Những bean được khởi tạo **trong giai đoạn rất sớm**, đặc biệt chính các `BeanPostProcessor` và dependency trực tiếp của chúng, có thể **không đủ điều kiện để được mọi post-processor xử lý**, bao gồm auto-proxy creator. Log Spring thường cho biết bean không đủ điều kiện được xử lý bởi tất cả post-processors.

Các nguyên nhân hay gặp:

- Tự viết `BeanPostProcessor` và inject service nghiệp vụ vào constructor của nó, khiến service được tạo trước khi toàn bộ hậu xử lý sẵn sàng.
- Một factory method khai báo `BeanPostProcessor` theo cách buộc `@Configuration` class khởi tạo quá sớm.
- Chủ động `getBean()` trong giai đoạn chỉnh bean definitions, làm phá thứ tự lifecycle bình thường.

Cách xử lý là **tránh kéo bean nghiệp vụ vào giai đoạn đăng ký post-processors**. Khi tự viết `@Bean` trả về `BeanPostProcessor`, Spring khuyến nghị method `static` và ít dependency khi phù hợp; đừng áp dụng mẹo này tùy tiện cho mọi `@Bean`.

### 9.3. Self-invocation không đi qua proxy

```java
public class OrderService {
    public void checkout() {
        validate(); // this.validate(), gọi nội bộ trên target.
    }

    public void validate() {
        // Kiểm tra nghiệp vụ.
    }
}
```

Đây là **class fragment minh họa**. Nếu caller gọi `proxy.checkout()`, Spring có thể advice `checkout()`; nhưng lời gọi `validate()` từ bên trong target không đi qua proxy nên advice dành riêng cho `validate()` không chạy nhờ auto-proxy creator.

Creator đã làm nhiệm vụ **bọc bean**; nó không sửa mọi lời gọi `this.method()` trong bytecode. Cách đơn giản thường là chuyển phần được advice sang một bean khác để lời gọi đi qua dependency Spring quản lý.

### 9.4. Constructor và initialization callback không phải “lời gọi đã đi qua proxy”

Spring thường chạy `@PostConstruct`, `InitializingBean.afterPropertiesSet()` hoặc init method trên raw bean trong giai đoạn khởi tạo, trước khi tham chiếu proxy thông thường được trả cho caller. Một lời gọi nội bộ từ init callback không tự chạy Spring AOP advice.

Nếu cần thực hiện nghiệp vụ sau khi context được khởi tạo và đã có proxy, hãy chọn điểm khởi chạy phù hợp với lifecycle ứng dụng (ví dụ một component khác gọi qua bean Spring sau khi context sẵn sàng). Không dùng `@Before`/`@After` để thay thế `@PostConstruct`/`@PreDestroy`.

### 9.5. Object tự `new` hoặc final method

`new OrderService()` bên ngoài Spring container **không được creator xử lý**. Class-based proxy không chặn được method `final`; class `final` cũng không thể được subclass bởi CGLIB. Với JDK dynamic proxy, caller đi qua interface; class-only method không tự có mặt trên proxy interface. Các giới hạn này ảnh hưởng hiệu quả của auto-proxy creator ngay cả khi `@Aspect` và pointcut đúng.

## 10. Cách kiểm tra auto-proxy creator trong dự án đang chạy

### 10.1. Kiểm tra bean hạ tầng trong context

Với cấu hình Spring AOP chuẩn được kích hoạt, có thể dùng:

```java
boolean present = context.containsBean(
    org.springframework.aop.config.AopConfigUtils.AUTO_PROXY_CREATOR_BEAN_NAME
);
System.out.println("auto-proxy creator present = " + present);
```

Đây là **mã chẩn đoán đặt bên trong chương trình đang có biến `context`**, không phải Java file độc lập. Nếu không có bean theo tên hạ tầng này, hãy kiểm tra `@EnableAspectJAutoProxy`, XML hoặc auto-configuration của phiên bản Spring dùng trong ứng dụng. Không dựa duy nhất vào internal bean name cho monitoring sản xuất.

### 10.2. Kiểm tra proxy cho target cụ thể

```java
Object bean = context.getBean("orderService");
boolean isProxy = org.springframework.aop.support.AopUtils.isAopProxy(bean);
System.out.println("proxied = " + isProxy);
```

Nhận diện proxy là bước một. Nếu `true`, cần xác định **advice nào nằm trong proxy và có khớp method cần kiểm tra không**; một bean có thể được proxy bởi transaction hoặc scope mà không có audit advice cụ thể.

### 10.3. Quan sát advisors khi cần

```java
Object bean = context.getBean("orderService");

if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (org.springframework.aop.Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());
    }
}
```

Đoạn trên là **fragment kiểm tra**, không có stdout cố định vì advisor types/order tùy ứng dụng và Spring version. Advisor list không đồng nghĩa số lần chạy advice: một advisor có thể có pointcut không khớp method đang gọi, và advisor chain có thể chứa cả hạ tầng Spring.

### 10.4. Kiểm tra hành vi thay vì chỉ kiểm tra cấu trúc

Một phép thử thuyết phục nên chứng minh:

1. Aspect bean được đăng ký đúng một lần theo thiết kế.
2. Target bean được lấy từ `ApplicationContext`, proxy strategy phù hợp.
3. Một method khớp pointcut chạy đúng số advice kỳ vọng.
4. Một method/bean không khớp pointcut **không** chạy advice này.
5. Exception và giá trị trả về của nghiệp vụ được giữ đúng.
6. Chế độ transaction, security hoặc async khác vẫn hoạt động theo cấu hình dự án.

Nếu advice bị thiếu, xử lý theo thứ tự **bean/context → auto-proxy setup → advisor/pointcut → proxy type → caller đi qua proxy**. Nếu chạy hai lần, kiểm tra có nhiều aspect beans/advisors hay hai lần gọi method; không tự kết luận do có hai dòng bật AOP.

## 11. Các lỗi cấu hình thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `@Aspect` có trong source nhưng không có advice | Aspect chưa đăng ký thành Spring bean; chưa kích hoạt auto-proxy. | Kiểm tra `@Component`/`@Bean`, context và `@EnableAspectJAutoProxy`/Boot starter. |
| Bean được inject nhưng `AopUtils.isAopProxy() = false` | Không có advisor phù hợp, creator chưa được bật, hoặc bean đã tạo quá sớm. | Kiểm tra bean scope, điểm tạo bean, advisor và startup warnings. |
| AOP proxy có nhưng `@Before` không chạy | Pointcut không khớp method, self-invocation hoặc khác context. | Thử một lời gọi public qua proxy trực tiếp rồi đối chiếu pointcut. |
| Bean có tên class `$$SpringCGLIB$$` | Class-based proxy được tạo; đây có thể là kết quả bình thường. | Đối chiếu `proxyTargetClass` và lý do bean được proxy, không dựa vào tên class để đo advice. |
| `ClassCastException` khi ép proxy thành class triển khai | Đang dùng JDK dynamic proxy theo interface. | Inject interface hoặc điều chỉnh proxy strategy theo yêu cầu thật sự. |
| Aspect bị gọi hai lần trên một method | Nhiều aspect beans/advisors cùng khớp, hoặc caller thực sự gọi method hai lần. | Đếm aspect beans, advisor chain và correlation id từng invocation. |
| `Bean ... not eligible for auto-proxying` | Bean sinh quá sớm trong quá trình đăng ký `BeanPostProcessor`. | Kiểm tra các dependency/factory methods của post-processor. |
| AOP trong root context chạy, controller child context không chạy | Creator và target nằm ở context khác nhau. | Kiểm tra cấu trúc parent-child và cấu hình AOP cục bộ. |
| Thay đổi property Boot nhưng proxy vẫn khác kỳ vọng | Java/XML hoặc hạ tầng khác đang yêu cầu proxy strategy mạnh hơn. | Kiểm kê toàn bộ cấu hình proxy trong context. |
| Method `final` không được advice bởi CGLIB | Proxy subclass không override được method. | Thiết kế lại method/class hoặc dùng interface proxy nếu phù hợp. |

## 12. Quy trình triển khai và kiểm chứng thực tế

Trong một ứng dụng Spring mới hoặc khi đưa Spring AOP vào codebase cũ:

1. **Xác định `ApplicationContext` sở hữu bean đích.** Xem nơi tạo context, package scan và các XML được import.
2. **Bật đúng loại auto-proxy support.** Spring thuần với `@AspectJ` thường dùng `@EnableAspectJAutoProxy`; Spring Boot ưu tiên auto-configuration phù hợp dòng Boot.
3. **Đăng ký aspect beans.** `@Aspect` + `@Component` hoặc `@Bean`; kiểm tra không trùng đăng ký.
4. **Giới hạn pointcut.** Chỉ áp dụng advisor vào methods của beans cần hành vi dùng chung.
5. **Kiểm tra proxy policy.** Xác định JDK dynamic proxy hay class-based proxy; không gán `proxyTargetClass=true` một cách máy móc.
6. **Quan sát bean và lời gọi thực tế.** Dùng `AopUtils`, advisor inspection khi cần và một test kiểm tra chính xác advice count.
7. **Đánh giá lifecycle.** Tránh khởi tạo service quá sớm từ custom post-processors, tránh gọi method được advice trong constructor/init callback của chính target.
8. **Kiểm tra cấu hình chồng chéo.** Spring có thể hợp nhất creator, nhưng không tự hợp nhất nội dung của hai advice cùng trách nhiệm.
9. **Kiểm tra sau khi đổi module/context.** Nếu di chuyển service sang child context, đổi cách inject bean hoặc dùng scoped proxy, phải chạy lại test AOP.

### Tài liệu Spring chính thức

- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Declaring an Aspect: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — Auto-proxy facility: https://docs.spring.io/spring-framework/reference/core/aop-api/autoproxy.html
- Spring Framework — Container Extension Points / BeanPostProcessor: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework — AnnotationAwareAspectJAutoProxyCreator API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/aspectj/annotation/AnnotationAwareAspectJAutoProxyCreator.html
- Spring Framework — AbstractAutoProxyCreator API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/framework/autoproxy/AbstractAutoProxyCreator.html

**Vai trò của auto-proxy creator trong `ApplicationContext` là biến cấu hình aspect/advisor của Spring thành các tham chiếu bean có khả năng interception, ngay trong quá trình container tạo và công bố beans.** Spring vẫn quản lý target bean và lifecycle, còn lời gọi thông qua proxy quyết định khi nào advice thực sự được thực thi.
