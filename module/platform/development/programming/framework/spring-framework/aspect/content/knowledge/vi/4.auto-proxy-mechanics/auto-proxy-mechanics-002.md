# Nhận diện advisor phù hợp với lớp và phương thức đích trong Spring AOP

## 1. Bài toán mà Spring auto-proxy phải giải quyết

Trong một ứng dụng Spring, có thể tồn tại nhiều **advisor** từ các `@Aspect` và từ những thành phần AOP khác, nhưng không phải advisor nào cũng áp dụng lên mọi bean và mọi phương thức. Spring cần trả lời hai câu hỏi khác nhau:

1. **Khi chuẩn bị một Spring bean:** những advisor nào *có khả năng* tác động đến ít nhất một phương thức của lớp đích? Nếu có advisor phù hợp và không bị các quy tắc loại trừ khác ngăn cản, bean có thể được bọc bằng AOP proxy.
2. **Khi client gọi phương thức qua proxy:** trong các advisor đã gắn với proxy, advisor nào thực sự khớp phương thức đang gọi và — nếu pointcut yêu cầu — **đối số runtime** của chính lời gọi đó?

Ví dụ: một `OrderService` có ba phương thức `checkout()`, `status()`, `cancel()`, nhưng advisor chỉ áp dụng cho `checkout()`. Spring có thể proxy **bean OrderService**, trong khi chỉ **lời gọi `checkout()`** đi qua advice của advisor ấy. Sự tồn tại của proxy không đồng nghĩa mọi method đều chạy mọi advice.

Đây là bài về **cơ chế nhận diện advisor trong Spring AOP proxy-based**; tập trung vào Spring auto-proxy, class/method matching, điểm quyết định tạo proxy và thời điểm chạy advice. Kiến thức Aspect tổng quát không được lặp lại.

## 2. Các thành phần tham gia

| Thành phần trong Spring | Chức năng đối với bước matching |
| --- | --- |
| `Advisor` (`org.springframework.aop.Advisor`) | Đại diện cho advice và thông tin bổ sung cần để sử dụng advice. |
| `PointcutAdvisor` | Một dạng advisor có `Pointcut` để xác định **nơi áp dụng advice**. |
| `Pointcut` | Cung cấp hai phần: `ClassFilter` để xét lớp đích, `MethodMatcher` để xét phương thức và đôi khi đối số runtime. |
| `ClassFilter` | Trả lời một lớp `Class<?>` có nằm trong phạm vi pointcut không. |
| `MethodMatcher` | Trả lời method cụ thể trên target class có thể khớp không, và có phải kiểm tra thêm từng lời gọi không. |
| `AopUtils.canApply(...)` | Tiện ích Spring AOP để đánh giá một pointcut/advisor **có thể áp dụng** cho một target class hay không. |
| `AopUtils.findAdvisorsThatCanApply(...)` | Lọc danh sách advisor ứng viên để lấy những advisor có khả năng áp dụng cho target class. |
| `AnnotationAwareAspectJAutoProxyCreator` | Một auto-proxy creator của Spring nhận diện cả advisor bean và advice khai báo trong các Spring-managed `@Aspect` bean. |
| `AopProxy` | Proxy JDK hoặc class-based proxy (CGLIB) thực thi chuỗi interceptor khi một lời gọi đi qua nó. |

Định nghĩa API chính của Spring (chỉ minh họa chữ ký; các interface thật có thêm chi tiết khác):

```java
interface Pointcut {
    ClassFilter getClassFilter();
    MethodMatcher getMethodMatcher();
}

interface ClassFilter {
    boolean matches(Class<?> clazz);
}

interface MethodMatcher {
    boolean matches(Method method, Class<?> targetClass);
    boolean isRuntime();
    boolean matches(Method method, Class<?> targetClass, Object... args);
}
```

Phân biệt rõ:

- `ClassFilter.matches(...)` xét **lớp đích**; chưa khẳng định một phương thức cụ thể sẽ nhận advice.
- `MethodMatcher.matches(method, targetClass)` là bước **kiểm tra tĩnh**, có thể thực hiện trước khi lời gọi chạy.
- Nếu `isRuntime()` trả về `true`, Spring còn có thể gọi `matches(method, targetClass, args)` cho từng lần gọi, vì kết quả còn phụ thuộc đối số thực tế.
- Kết quả `canApply(advisor, targetClass) == true` nghĩa là advisor **có khả năng áp dụng cho một phần của lớp**, chưa chứng minh lời gọi hiện tại chắc chắn kích hoạt advice.

Spring có thể tối ưu/cache các phần matching tĩnh. Không nên hiểu rằng Spring luôn quét lại toàn bộ các advisor beans cho mọi lời gọi.

## 3. Spring chọn advisor như thế nào khi tạo bean proxy?

Sơ đồ dưới là luồng khái niệm dành cho cấu hình Spring AOP có auto-proxy. Tên class/method giúp định hướng khi đọc source Spring; đây **không phải cam kết rằng mọi phiên bản Spring luôn chạy đúng từng bước nội bộ theo một thứ tự bất biến**.

```text
ApplicationContext có Spring AOP auto-proxy creator
        |
        +-- Advisor beans đã đăng ký
        |
        +-- @Aspect beans đã đăng ký
                  -> chuyển các advice @AspectJ thành advisors
        |
        v
Danh sách candidate advisors
        |
        v
Bean đích đang được xem xét: tên bean + target class
        |
        +-- Bỏ qua đối tượng không thuộc phạm vi auto-proxy
        |
        +-- Lọc advisor có khả năng áp dụng cho target class:
        |      ClassFilter + MethodMatcher (kiểm tra tĩnh)
        |
        +-- Sắp xếp / hoàn thiện các advisor phù hợp
        |
        +-- Nếu có advisor phù hợp và đủ điều kiện proxy:
        |      tạo AOP proxy cho bean đích
        |
        +-- Nếu không có advisor phù hợp:
               thường trả về bean gốc, không tạo proxy vì advisor đó
        |
        v
Client gọi method qua proxy
        |
        +-- Chọn interceptor chain cho method
        +-- Kiểm tra điều kiện runtime nếu pointcut yêu cầu
        +-- Chạy advice khớp rồi gọi target method
```

Trong họ `AbstractAdvisorAutoProxyCreator`, các tên phương thức có ích khi cần đọc source hoặc debug là:

```text
findCandidateAdvisors()
findEligibleAdvisors(beanClass, beanName)
findAdvisorsThatCanApply(candidateAdvisors, beanClass, beanName)
sortAdvisors(...)
```

Với hỗ trợ `@AspectJ`, Spring còn đọc advice trên **aspect beans** để đưa chúng vào danh sách advisor ứng viên. Các bước này diễn ra trong vòng đời tạo bean/post-processing của Spring, trước khi caller thông thường nhận tham chiếu proxy.

### 3.1. Candidate advisor khác eligible advisor

- **Candidate advisor** là advisor đã được Spring tìm thấy từ cấu hình AOP, có thể nhắm tới nhiều bean khác nhau.
- **Eligible advisor** là advisor có khả năng áp dụng cho **lớp bean đang xét**, dựa vào pointcut và các điều kiện Spring liên quan.
- **Advice thực thi tại lời gọi** là lớp hẹp hơn nữa: chỉ những interceptor/advice match với method (và điều kiện runtime) của invocation mới chạy.

Một advisor cho `OrderService.checkout()` vẫn là candidate khi Spring đang xét `InvoiceService`, nhưng không trở thành eligible cho lớp không có method phù hợp với biểu thức đó.

### 3.2. Đừng nhầm lọc theo lớp với lọc theo phương thức

Giả sử pointcut là:

```java
@Before("execution(* example.OrderService.checkout(..))")
```

Với `OrderService` chứa cả `checkout()` và `status()`:

- **Ở cấp bean/class:** có ít nhất một method được pointcut nhắm đến, nên advisor *có thể* áp dụng lên bean.
- **Ở cấp method:** `checkout()` khớp, `status()` không khớp.
- **Ở cấp call:** lời gọi `checkout()` phải đi **qua proxy** và thỏa các điều kiện thực thi mới nhận advice.

Spring AOP không tự chèn advice vào mọi phương thức của `OrderService` chỉ vì proxy đã tồn tại.

## 4. Ví dụ Java 17+ chạy được: một bean có proxy, một bean không có

Ví dụ Spring Framework thuần với `@EnableAspectJAutoProxy`. Dùng **Spring Framework 6.2.19** và **AspectJ Weaver 1.9.25.1**. Bản mẫu ngắn này minh họa đồng thời: cách Spring xác định lớp có advisor phù hợp, cách match method và kết quả gọi qua proxy.

### 4.1. Cấu trúc dự án

```text
advisor-matching-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── AuditAspect.java
    ├── OrderService.java
    ├── InvoiceService.java
    └── Main.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>advisor-matching-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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

**`OrderService.java`**

```java
package example;

public class OrderService {
    public void checkout() {
        System.out.println("order: checkout");
    }

    public void status() {
        System.out.println("order: status");
    }
}
```

**`InvoiceService.java`**

```java
package example;

public class InvoiceService {
    public void checkout() {
        System.out.println("invoice: checkout");
    }
}
```

**`AuditAspect.java`**

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.OrderService.checkout(..))")
    public void beforeCheckout() {
        System.out.println("audit: before checkout");
    }
}
```

**`AppConfig.java`**

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy
public class AppConfig {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public InvoiceService invoiceService() {
        return new InvoiceService();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }
}
```

**`Main.java`**

```java
package example;

import java.lang.reflect.Method;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            var order = context.getBean(OrderService.class);
            var invoice = context.getBean(InvoiceService.class);

            System.out.println("order proxy: " + AopUtils.isAopProxy(order));
            System.out.println("invoice proxy: " + AopUtils.isAopProxy(invoice));

            var pointcut = new AspectJExpressionPointcut();
            pointcut.setExpression(
                "execution(* example.OrderService.checkout(..))"
            );

            System.out.println("order class eligible: "
                + AopUtils.canApply(pointcut, OrderService.class));
            System.out.println("invoice class eligible: "
                + AopUtils.canApply(pointcut, InvoiceService.class));

            Method checkout = OrderService.class.getMethod("checkout");
            Method status = OrderService.class.getMethod("status");
            System.out.println("checkout matches: "
                + pointcut.getMethodMatcher().matches(checkout, OrderService.class));
            System.out.println("status matches: "
                + pointcut.getMethodMatcher().matches(status, OrderService.class));

            order.checkout();
            order.status();
            invoice.checkout();
        }
    }
}
```

Tại thư mục có `pom.xml`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Những dòng do chương trình in ra theo thứ tự:

```text
order proxy: true
invoice proxy: false
order class eligible: true
invoice class eligible: false
checkout matches: true
status matches: false
audit: before checkout
order: checkout
order: status
invoice: checkout
```

### 4.2. Phân tích kết quả theo từng tầng

1. `AuditAspect` được đăng ký là Spring bean qua `@Bean`; `@EnableAspectJAutoProxy` bật Spring AOP. `@Aspect` một mình không thay được bước đăng ký bean.
2. Spring thấy advisor từ `@Before` có pointcut khớp `OrderService.checkout()`. `OrderService` có advisor phù hợp nên Spring tạo proxy cho bean đó.
3. `InvoiceService` cũng có một method tên `checkout()`, nhưng **không phải class `example.OrderService`** nên pointcut trong ví dụ không match; `invoice proxy: false` là kết quả khi không có advisor nào khác áp dụng lên nó.
4. `AopUtils.canApply(pointcut, OrderService.class)` cho thấy ở cấp class tồn tại ít nhất một method có khả năng khớp. Kết quả `true` **không có nghĩa** toàn bộ method trên lớp đều khớp.
5. `getMethodMatcher().matches(checkout, OrderService.class)` là `true`, còn với `status()` là `false`.
6. Lời gọi `order.checkout()` qua bean proxy chạy advice, rồi đến method nghiệp vụ. Lời gọi `order.status()` vẫn đi qua cùng proxy nhưng **không có advice tương ứng**. `invoice.checkout()` gọi bean InvoiceService không có proxy trong cấu hình này, nên cũng không có dòng audit.

Ở bước chẩn đoán, `AspectJExpressionPointcut` được tạo thêm để minh họa phép kiểm tra tĩnh theo **cùng biểu thức** với `@Before`; đây là đối tượng kiểm tra độc lập, không phải chính advisor object đang nằm trong proxy. Không nên đồng nhất kết quả `AopUtils.canApply` với việc truy xuất danh sách advisor đã cài đặt lên một proxy cụ thể.

## 5. Quy tắc lọc tĩnh và động trong `MethodMatcher`

### 5.1. Static matching

Một method matcher không cần dữ liệu từng lời gọi có thể quyết định dựa trên method signature và target class. Với pointcut:

```text
execution(* example.OrderService.checkout(..))
```

Spring đủ dữ liệu để nhận diện sự phù hợp của phương thức `checkout()` từ lớp/method. Việc xét kiểu và method trước khi xây proxy giúp tránh làm các phép kiểm tra không cần thiết trên từng invocation.

Trong Spring AOP API, `MethodMatcher.matches(Method, Class)` được dùng để kiểm tra một method **có thể** khớp; `isRuntime() == false` nghĩa là không có bước `matches(Method, Class, Object... args)` trên mỗi lời gọi.

### 5.2. Dynamic matching: điều kiện phụ thuộc đối số thực tế

Một số pointcut phụ thuộc dữ liệu lúc chạy, chẳng hạn ràng buộc `args(...)`. Ví dụ sau chỉ là **đoạn minh họa bổ sung**, không thuộc chương trình độc lập ở mục 4:

```java
// Trong một target bean có phương thức:
public void handle(Object value) {
    System.out.println("handling: " + value);
}
```

Aspect tương ứng:

```java
// Bên trong class @Aspect đã được Spring đăng ký bean:
@Before("execution(* example.OrderService.handle(..)) && args(java.lang.String)")
public void beforeStringValue() {
    System.out.println("argument is String");
}
```

Với phương thức có tham số khai báo là `Object`, `handle("A")` có đối số runtime là `String`, còn `handle(42)` có đối số runtime là `Integer`. Nếu cả hai lời gọi đi qua Spring proxy, phần điều kiện `args(java.lang.String)` có thể chọn chỉ lời gọi đầu tiên. **Một method được chọn làm ứng viên lúc tạo proxy chưa chắc mọi lần gọi đều thỏa điểm cắt.**

Cần phân biệt:

- `execution(...)` thường mô tả method signature và loại method join point.
- `args(...)` liên quan loại đối số **thực tế** lúc gọi và có thể yêu cầu runtime test.
- `@args(...)` liên quan annotation trên kiểu runtime của đối số, khác với `@annotation(...)` trên **phương thức** đang thực thi.
- Nếu pointcut gồm phép `&&`, các phần ràng buộc cùng phải thỏa; với `||`, một nhánh khớp có thể đủ.

Không nên tự suy ra mọi pointcut chứa `args` đều nhất thiết mất đúng một phép so khớp động trong mọi tối ưu nội bộ; hãy dùng `MethodMatcher.isRuntime()` khi thực sự cần khảo sát một instance matcher.

## 6. Những biểu thức Spring AOP thường dùng và ảnh hưởng lên matching

Các biểu thức dưới đây là **mẫu để đặt trong annotation advice như `@Before("...")`**, với các class/package/annotation thực sự tồn tại trong dự án. Không phải các chương trình Java độc lập.

| Biểu thức | Yếu tố dùng để hạn chế phạm vi |
| --- | --- |
| `execution(* com.acme.order.OrderService.checkout(..))` | Method tên `checkout` trên `OrderService` với bất kỳ số tham số; là phép khớp method execution |
| `execution(public * com.acme.order..*Service.*(..))` | Method `public` của các loại có tên kết thúc `Service` trong package phù hợp |
| `within(com.acme.order..*)` | Method execution nằm trong các loại thuộc package tương ứng |
| `@annotation(com.acme.audit.Audited)` | Method execution mang annotation `@Audited` |
| `@within(com.acme.audit.AuditedType)` | Method execution thuộc kiểu có annotation `@AuditedType` theo ngữ nghĩa PCD |
| `target(com.acme.order.OrderService)` | Target object thuộc loại chỉ định |
| `this(com.acme.order.OrderService)` | **Proxy** đáp ứng kiểu chỉ định; khác với target nếu dùng JDK proxy |
| `args(java.lang.String)` | Kiểu của đối số runtime phù hợp |
| `bean(orderService)` | Spring bean **có tên phù hợp**; `bean()` là Spring-specific PCD |

Một số hệ quả đáng nhớ:

- `execution(* ...)` nhắm tới **method execution** trên bean do Spring quản lý; Spring proxy không hỗ trợ mọi join point của AspectJ như constructor/field access.
- `bean(orderService)` có thể quyết định phạm vi dựa vào **tên bean** khi chọn advisor cho một bean cụ thể. Nó không chỉ là kiểm tra Java class.
- Với `this(...)`, phép khớp dựa trên kiểu **proxy**, còn `target(...)` dựa trên target object; hai kết quả có thể khác nhau khi dùng JDK dynamic proxy.
- Pointcut khớp về biểu thức chưa chắc chạy advice khi lời gọi **không đi qua proxy** hoặc method không thể được proxy can thiệp.

### 6.1. Bean name có thể quyết định khả năng áp dụng

Giả sử hai Spring beans đều trả về instance của cùng một class `OrderService`, nhưng mang tên `importantOrderService` và `backupOrderService`. Với advice:

```java
@Before("bean(importantOrderService) && execution(* *.checkout(..))")
public void beforeImportantCheckout() {
    // ...
}
```

Spring có thể chỉ áp dụng advisor cho bean có tên khớp, dù target class giống nhau. Vì vậy ở giai đoạn chọn advisor của auto-proxy, **bean name cũng có thể là một phần ngữ cảnh cần thiết**. Đừng chỉ gọi `AopUtils.canApply(..., OrderService.class)` rồi kết luận mọi bean cùng class sẽ nhận chính xác danh sách advisor giống nhau: phép thử tiện ích theo `Class` riêng lẻ không mang đầy đủ ngữ cảnh bean name.

## 7. Matching không đảm bảo proxy luôn can thiệp

Một advisor có thể được xác định là phù hợp ở cấp class/method, nhưng lời gọi thực tế vẫn không chạy advice nếu vướng ranh giới proxy Spring AOP.

### 7.1. Self-invocation

```java
// Minh họa trong một target bean, không phải chương trình độc lập.
public void checkout() {
    this.finalizeOrder();
}

public void finalizeOrder() {
    // ...
}
```

Nếu caller gọi `proxy.checkout()`, lời gọi ngoài đi qua proxy. Nhưng khi thân `checkout()` gọi `this.finalizeOrder()`, đó là lời gọi trực tiếp bên trong target, **không quay lại proxy**. Do đó advice chỉ nhắm `finalizeOrder()` sẽ không tự chạy cho lời gọi nội bộ đó, dù pointcut xét method `finalizeOrder()` là phù hợp.

Một cách xử lý thông dụng: tách trách nhiệm cần được advice thành một Spring bean riêng, inject bean này và gọi qua tham chiếu Spring cung cấp.

### 7.2. Khả năng proxy hóa phương thức

Với **JDK dynamic proxy**, caller chủ yếu gọi các public method khai báo trên interface của proxy. Với **class-based proxy/CGLIB**, Spring có thể proxy những method phù hợp có thể được override, nhưng:

- `final` class không thể subclass để tạo class-based proxy.
- `final` method không thể override để advice theo cơ chế đó.
- `private` method không thể được advice qua cơ chế proxy method override.
- Constructor, field access và lời gọi `static` không phải method-execution join point của Spring AOP proxy.

Những giới hạn này **tách biệt** với việc pointcut expression có đúng cú pháp hoặc advisor có được tìm thấy hay không.

### 7.3. Spring bean và aspect bean

Spring AOP auto-proxy áp dụng lên các bean phù hợp trong Spring container. Một object được tự tạo bằng `new OrderService()` bên ngoài container không tự nhận proxy của bean cùng lớp. Mặt khác, các lớp `@Aspect` chính chúng không phải target bình thường cho auto-proxying bằng các aspect khác; đừng dùng `AopUtils.isAopProxy(aspectBean)` như phép thử duy nhất để kết luận aspect đã được đăng ký hay chưa.

## 8. Khác biệt giữa “có proxy”, “có advisor” và “advice đã chạy”

| Quan sát | Điều có thể kết luận | Điều **chưa** kết luận được |
| --- | --- | --- |
| `AopUtils.isAopProxy(bean) == true` | Tham chiếu đang cầm là một Spring AOP proxy | Mọi method/mọi lời gọi đều chạy một advice cụ thể |
| `AopUtils.canApply(pointcut, Target.class) == true` | Pointcut **có thể** áp dụng lên ít nhất một method của target class | Pointcut đã được cài vào proxy cho một bean cụ thể hoặc match mọi đối số runtime |
| Một method có static match `true` | Có thể khớp theo chữ ký và class | Lời gọi đi qua proxy và các dynamic conditions đều đúng |
| `AopUtils.isAopProxy(bean) == false` | Tham chiếu không phải Spring AOP proxy | Vì sao bean chưa có proxy; có thể do không có advisor, cấu hình hoặc đối tượng ngoài container |
| Log trong advice xuất hiện | Advice đã thực thi trong đường gọi được quan sát | Những lời gọi khác cũng luôn chạy advice |
| Một bean không có advisor khớp | Không được proxy **bởi tập advisor đó** | Có thể vẫn được proxy do advisor/cơ chế infrastructure khác |

Điểm cần nhấn mạnh khi debug: **Spring quyết định proxy ở cấp bean**, còn **lời gọi chạy advice ở cấp method/invocation**. Hai quyết định liên quan nhưng không đồng nhất.

## 9. Kiểm tra advisor thực tế trên một proxy

Sau khi lấy một bean từ `ApplicationContext`, có thể kiểm tra xem proxy có cho phép truy xuất cấu hình advice hay không bằng `org.springframework.aop.framework.Advised`. Trong cấu hình Spring AOP proxy thông thường, proxy có thể triển khai interface này.

Đoạn minh họa dùng đối tượng `order` của ví dụ mục 4:

```java
// Đoạn bổ sung vào Main.java (không chạy độc lập):
import org.springframework.aop.Advisor;
import org.springframework.aop.PointcutAdvisor;
import org.springframework.aop.framework.Advised;

if (order instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName());

        if (advisor instanceof PointcutAdvisor pcAdvisor) {
            System.out.println(pcAdvisor.getPointcut().getClass().getName());
        }
    }
}
```

Ví dụ trên có thể in tên class của advisor/pointcut tùy phiên bản và cấu hình; **không nên cố định stdout** của cấu trúc hạ tầng Spring trong bài học. Đây là công cụ quan sát, còn nguồn xác nhận hành vi cuối cùng vẫn là việc gọi method qua proxy và thấy advice thực thi.

Một số proxy được cấu hình để không expose `Advised` hoặc không cho phép thay đổi advice; do đó nên dùng kiểm tra `instanceof Advised`, không ép kiểu mù quáng.

### Kiểm tra bằng log và debugger

Nếu muốn theo dõi quá trình chọn advisor trong Spring Framework, có thể dùng debugger đặt breakpoint tại các điểm như:

```text
AbstractAdvisorAutoProxyCreator.findEligibleAdvisors(...)
AbstractAdvisorAutoProxyCreator.findAdvisorsThatCanApply(...)
AopUtils.findAdvisorsThatCanApply(...)
AopUtils.canApply(...)
```

Chú ý:

- Một Spring Boot application có thể có nhiều loại advisor và các bean infrastructure khác; việc thấy nhiều advisor candidates là bình thường.
- Các phiên bản Spring có thể thay đổi chi tiết phương thức nội bộ, cache hoặc thứ tự gọi. Chỉ dùng breakpoint để quan sát phiên bản **thật sự đang chạy**.
- Trong trường hợp có `@Order` hoặc `Ordered`, Spring có thể sắp xếp advisor để xác định thứ tự advice; **sắp xếp không biến một advisor không khớp thành khớp**.
- Nếu bạn chỉ thấy proxy được tạo mà không thấy dòng advice, hãy phân biệt lỗi **advisor chưa được chọn cho bean** và lỗi **method/runtime invocation không match**.

## 10. Chẩn đoán advisor không khớp

Thực hiện kiểm tra có thứ tự để tìm đúng tầng phát sinh vấn đề.

### Bước 1. Xác nhận aspect/advisor được Spring đăng ký

- Với `@Aspect`, kiểm tra class aspect là Spring bean (`@Component` nằm trong phạm vi scan hoặc `@Bean`).
- Với `@EnableAspectJAutoProxy`, kiểm tra annotation nằm trong context phù hợp; trên Spring Boot, kiểm tra starter AOP/AspectJ và auto-configuration.
- Không nhầm aspect class tồn tại trên classpath với advisor đã được Spring tìm ra.

### Bước 2. Xác nhận target bean và type đúng

- `context.getBean(OrderService.class)` có lấy đúng bean không?
- Có nhiều bean cùng interface, bean name hoặc nhiều `ApplicationContext` không?
- Pointcut `execution(* example.OrderService.checkout(..))` sẽ không tự mở rộng sang một class cùng tên method ở package khác.

### Bước 3. Kiểm tra khớp lớp rồi khớp phương thức

- Dùng `AopUtils.canApply(pointcut, Target.class)` để xác định có **khả năng** match method nào của class.
- Dùng `pointcut.getMethodMatcher().matches(method, Target.class)` để xét **một method cụ thể** khi dùng Spring `Pointcut` API.
- Nếu pointcut dùng `bean(name)`, phải kiểm tra chính **bean name/context**, không chỉ type.
- Với `args(...)` hay điều kiện runtime, kiểm tra argument type/value tại thời điểm gọi, thay vì chỉ chữ ký method.

### Bước 4. Kiểm tra proxy và đường đi của lời gọi

- `AopUtils.isAopProxy(context.getBean(...))` kiểm tra tham chiếu từ container.
- Xem code có tự `new`, gọi `this.method()`, gọi method `private`/`final` hoặc truy cập method ngoài interface của JDK proxy không.
- Nếu biểu thức match nhưng lời gọi bỏ qua proxy thì Spring AOP không chạy advice.

### Bước 5. Trường hợp có nhiều advisor

- Advisor khác có thể tạo proxy ngay cả khi advisor đang quan tâm **không khớp**.
- Hãy xác định **advisor nào** đã được chọn, sau đó xem method matcher của advisor ấy.
- Nếu advisor có dynamic match, cùng một method có thể chạy advice ở lời gọi này nhưng không chạy ở lời gọi khác.
- `@Order` chủ yếu điều chỉnh **thứ tự chạy** các advice phù hợp; nó không sửa pointcut sai.

### Bảng lỗi phổ biến

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| `@Aspect` có advice nhưng mọi bean đều không được proxy | Aspect chưa thành bean; auto-proxy chưa bật; dependency AOP chưa đủ |
| Bean có proxy, `checkout()` chạy advice, `status()` không chạy | Hoàn toàn đúng nếu advisor chỉ match `checkout()` |
| Hai bean cùng method name nhưng chỉ một bean nhận advice | Pointcut hạn chế theo package/class, annotation, target type hoặc bean name |
| Cùng method nhưng advice có lúc chạy có lúc không | Pointcut có điều kiện theo runtime arguments; hoặc đường gọi/bean reference khác nhau |
| Pointcut khớp method, nhưng gọi từ `this` không chạy advice | Self-invocation bỏ qua proxy |
| Proxy hiện hữu nhưng advice của bạn không chạy | Proxy có thể do advisor khác tạo; advisor đang xét có thể không eligible hoặc method không match |
| Khớp `ClassFilter` nhưng `MethodMatcher` không khớp | Lớp nằm trong phạm vi rộng, method cụ thể không đúng chữ ký/phạm vi |
| `ClassCastException` khi ép JDK proxy về class implementation | Proxy dạng interface; gọi qua interface hoặc xem chiến lược proxy đang cấu hình |

## 11. Tình huống kiểm tra kiến thức

**Tình huống 1:** Một `PaymentService` có các method `pay()`, `refund()`; chỉ có advisor `execution(* example.PaymentService.pay(..))`. Bean được proxy; gọi `refund()` có chạy advice không?

**Đáp án:** Không chạy advice này nếu `refund()` không khớp. Spring có thể proxy cả bean vì có ít nhất một method phù hợp, nhưng advice phải khớp riêng phương thức thực sự được gọi.

**Tình huống 2:** Hai beans cùng class `PaymentService`, tên `primaryPayment` và `secondaryPayment`. Advice dùng `bean(primaryPayment) && execution(* *.pay(..))`. Hai bean có giống danh sách advisor không?

**Đáp án:** Không nhất thiết. Spring-specific pointcut `bean(...)` xét bean name; advisor có thể eligible cho một bean và không eligible cho bean còn lại dù class giống nhau.

**Tình huống 3:** Method `handle(Object value)` có pointcut `args(java.lang.String)`. Lần lượt gọi qua proxy với `"a"` và `Integer.valueOf(5)`. Có thể có kết quả khác nhau không?

**Đáp án:** Có. Loại đối số runtime khác nhau có thể khiến dynamic matcher chỉ cho phép advice ở lời gọi truyền `String`.

**Tình huống 4:** `AopUtils.canApply(pointcut, PaymentService.class)` là `true`, nhưng `new PaymentService().pay()` không chạy advice. Có mâu thuẫn không?

**Đáp án:** Không. `canApply` chỉ kiểm tra khả năng phù hợp của pointcut với lớp; instance tự tạo ngoài container không tự có Spring AOP proxy.

## 12. Tài liệu Spring chính thức

- [Spring Framework — Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html): `ClassFilter`, `MethodMatcher`, static/dynamic matching và caching.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): những biểu thức `execution`, `within`, `target`, `this`, `args`, `@annotation`, `bean` Spring hỗ trợ.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): cơ chế proxy và giới hạn về method/self-invocation.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): cấu hình auto-proxy cho `@Aspect`.
- [Spring Javadoc — AopUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html): `canApply`, `findAdvisorsThatCanApply`.
- [Spring Javadoc — AbstractAdvisorAutoProxyCreator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/framework/autoproxy/AbstractAdvisorAutoProxyCreator.html): cơ chế tìm candidate/eligible advisors khi tạo proxy.
