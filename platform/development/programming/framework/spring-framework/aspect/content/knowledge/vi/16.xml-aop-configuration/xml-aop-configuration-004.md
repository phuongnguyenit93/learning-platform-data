# Pointcut có tên và `pointcut-ref` trong cấu hình XML của Spring AOP

## 1. Vấn đề cần giải quyết

Trong Spring AOP, một ứng dụng có thể cần áp dụng nhiều hành vi cắt ngang cho cùng nhóm phương thức: kiểm tra đầu vào, ghi nhận sự kiện, đo thời gian, hoặc quản lý giao dịch. Nếu mỗi advice tự viết lại biểu thức pointcut, phạm vi chặn dễ bị lệch sau khi đổi tên phương thức hoặc tổ chức lại gói.

**Pointcut có tên (named pointcut)** là cách khai báo biểu thức chọn phương thức một lần trong cấu hình Spring XML:

```xml
<aop:pointcut id="orderOperations"
              expression="execution(* example.OrderService.place(..))"/>
```

Các advice và advisor sau đó dùng **`pointcut-ref="orderOperations"`**. `pointcut-ref` là tham chiếu tới **`id` của phần tử `aop:pointcut`**, không phải tên phương thức Java, tên aspect bean hay biểu thức AspectJ.

```text
                  <aop:pointcut id="orderOperations">
                                 |
                    +------------+------------+
                    |                         |
     <aop:before pointcut-ref>    <aop:after-returning pointcut-ref>
                    |                         |
            Trước khi thực thi        Khi trả về bình thường
                    +------------+------------+
                                 |
                  Spring AOP proxy chọn
                  OrderService.place(..)
```

Điểm cốt lõi là **một định nghĩa phạm vi, nhiều vị trí sử dụng**. Spring vẫn chặn các lời gọi đi qua **proxy Spring**; XML không biến Spring AOP thành bộ công cụ chặn mọi điểm thực thi trong JVM.

### Ba phần tử cần phân biệt

| Phần tử XML | Vai trò | Giá trị thuộc tính quan trọng |
| --- | --- | --- |
| `<aop:pointcut>` | Đặt tên cho một biểu thức chọn join point | `id`, `expression` |
| `<aop:aspect>` | Gắn các advice XML với **một Spring bean** có phương thức advice | `ref` trỏ tới bean; có thể có `order` |
| `<aop:before>`, `<aop:after-returning>`, `<aop:around>`... | Chọn lúc chạy advice và phương thức Java xử lý | `method`, **`pointcut-ref` hoặc `pointcut`** |
| `<aop:advisor>` | Gắn một bean `Advice`/interceptor với pointcut | `advice-ref`, `pointcut-ref`, có thể có `order` |

Một `<aop:aspect ref="traceAdvice">` tham chiếu **bean chứa phương thức advice thông thường**, còn `<aop:advisor advice-ref="someInterceptor">` đòi bean phù hợp với giao diện `Advice`/interceptor. Không hoán đổi hai cách khai báo chỉ vì chúng cùng có thuộc tính `ref`.

## 2. Cú pháp Spring XML chính xác

Trong Spring XML schema, một named pointcut có **ID** và **biểu thức**; advice dùng một trong hai thuộc tính `pointcut-ref="id"` hoặc `pointcut="expression"`, không dùng cả hai:

~~~xml
<aop:config>
    <aop:pointcut id="placeCalls"
                  expression="execution(* example.OrderService.place(..))"/>
    <aop:aspect ref="traceAdvice">
        <aop:before method="before" pointcut-ref="placeCalls"/>
    </aop:aspect>
</aop:config>
~~~

Đây là fragment cần các bean `OrderService`, `traceAdvice` và Java method `before`. `pointcut-ref` phải là tên ID `placeCalls`, **không có `()`**. Trong `aop:config`, các phần tử ở cấp cao nhất có thứ tự **pointcut → advisor → aspect**. Kết hợp Boolean trong thuộc tính XML dùng `and`, `or`, `not` hoặc escape `&&` thành `&amp;&amp;`.

`proxy-target-class="true"` là tùy chọn nếu cần class proxy, không phải điều kiện để pointcut có tên hoạt động. Ví dụ runnable ở mục 5 khai báo một pointcut và hai aspect cùng tham chiếu nó.

## 3. Pointcut mức `aop:config` và pointcut bên trong `aop:aspect`

**Pointcut chung (top-level)** được khai báo là phần tử con trực tiếp của `aop:config`:

```xml
<aop:config>
    <aop:pointcut id="serviceCalls"
                  expression="execution(public * example..*Service.*(..))"/>

    <aop:aspect ref="auditAdvice">
        <aop:before method="recordAttempt"
                    pointcut-ref="serviceCalls"/>
    </aop:aspect>

    <aop:aspect ref="metricsAdvice">
        <aop:after-returning method="recordSuccess"
                             pointcut-ref="serviceCalls"/>
    </aop:aspect>
</aop:config>
```

Đây là **đoạn XML minh họa**, chỉ có thể dùng khi bạn đã khai báo các bean và phương thức tương ứng. Cả hai aspect chọn cùng một tập join point; thay biểu thức ở `serviceCalls` cập nhật phạm vi cho cả hai.

**Pointcut cục bộ của một aspect** được khai báo bên trong `aop:aspect`:

```xml
<aop:config>
    <aop:aspect ref="auditAdvice">
        <aop:pointcut id="localWrites"
                      expression="execution(* example..*Service.save*(..))"/>

        <aop:before method="recordAttempt"
                    pointcut-ref="localWrites"/>
        <aop:after-returning method="recordSuccess"
                             pointcut-ref="localWrites"/>
    </aop:aspect>
</aop:config>
```

Ở đây pointcut nằm cùng phần khai báo aspect, phù hợp khi chỉ các advice của aspect đó cần dùng. Nếu nhiều aspect/advisor phải dùng chung, đưa pointcut lên mức `aop:config` để hợp đồng phạm vi tập trung và dễ đọc hơn.

**Lưu ý quan trọng:** `id` của pointcut XML dùng để liên kết bằng `pointcut-ref`. Không thể viết một expression kiểu `expression="serviceCalls() and ..."` chỉ để gọi `id="serviceCalls"` như gọi một named `@Pointcut` trong Java. Theo tài liệu Spring, named pointcut được định nghĩa bằng XML **không được dùng như tên hàm để cấu thành một pointcut expression mới**. Nếu muốn composition qua tên hàm, có thể tham chiếu một phương thức `@Pointcut` đã được định nghĩa trong kiểu `@Aspect` bằng tên đủ điều kiện, ví dụ `example.SharedPointcuts.businessMethods()`, khi kiến trúc thực sự cần cách kết hợp đó. Cách đơn giản nhất trong XML thuần là khai báo expression cuối cùng dưới một `id` mới.

## 4. Phân biệt `pointcut-ref`, `pointcut`, `ref` và `advice-ref`

Ghi nhớ sự khác biệt nằm ở **loại định danh**:

| Thuộc tính | Giá trị là gì? |
| --- | --- |
| `<aop:pointcut id="placeCalls">` | ID của định nghĩa pointcut XML |
| `<aop:before pointcut-ref="placeCalls">` | Tham chiếu đúng pointcut ID |
| `<aop:before pointcut="execution(...)">` | Pointcut expression inline |
| `<aop:aspect ref="traceAdvice">` | ID của **Spring bean** chứa Java advice method |
| `<aop:advisor advice-ref="interceptorBean">` | ID bean implement Spring `Advice`/`MethodInterceptor` |
| `<aop:before method="before">` | Tên Java method trên bean `traceAdvice` |

`pointcut-ref="placeCalls()"` và `expression="placeCalls()"` không tham chiếu được **XML ID** bằng cú pháp named Java method. Một ID top-level dùng chung qua `pointcut-ref`; nếu cần kết hợp điều kiện, hãy viết biểu thức hoàn chỉnh trong định nghĩa pointcut.

## 5. Ví dụ chạy được: hai aspect cùng chia sẻ một named pointcut

Ví dụ dùng Java 17+, Spring Framework 6.2.8, AspectJ Weaver và Maven. Một pointcut mức `aop:config` chọn duy nhất `OrderService.place(..)`. Aspect kiểm tra số lượng và aspect ghi nhận sự kiện cùng dùng `pointcut-ref="placeCalls"`. Phương thức `status()` không bị chọn.

Cấu trúc thư mục:

```text
named-pointcut-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── App.java
    │   │   ├── EventRecorder.java
    │   │   ├── OrderService.java
    │   │   ├── GuardAdvice.java
    │   │   └── TraceAdvice.java
    │   └── resources/spring-aop.xml
    └── test/java/example/XmlPointcutTest.java
```

### 5.1. Khai báo dependencies

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>named-pointcut-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.2. Java: đối tượng đích và hai bean advice

`src/main/java/example/EventRecorder.java`:

```java
package example;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class EventRecorder {
    private final List<String> events = new CopyOnWriteArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
```

`src/main/java/example/OrderService.java`:

```java
package example;

public class OrderService {
    private final EventRecorder recorder;

    public OrderService(EventRecorder recorder) {
        this.recorder = recorder;
    }

    public String place(String sku, int quantity) {
        recorder.add("target:place");
        return "PLACED:" + sku + ":" + quantity;
    }

    public String status() {
        recorder.add("target:status");
        return "READY";
    }
}
```

`src/main/java/example/GuardAdvice.java`:

```java
package example;

import org.aspectj.lang.JoinPoint;

public class GuardAdvice {
    private final EventRecorder recorder;

    public GuardAdvice(EventRecorder recorder) {
        this.recorder = recorder;
    }

    public void check(JoinPoint joinPoint) {
        int quantity = (Integer) joinPoint.getArgs()[1];
        if (quantity <= 0) {
            recorder.add("reject:" + quantity);
            throw new IllegalArgumentException("quantity must be positive");
        }
        recorder.add("guard:" + quantity);
    }
}
```

`src/main/java/example/TraceAdvice.java`:

```java
package example;

import org.aspectj.lang.JoinPoint;

public class TraceAdvice {
    private final EventRecorder recorder;

    public TraceAdvice(EventRecorder recorder) {
        this.recorder = recorder;
    }

    public void before(JoinPoint joinPoint) {
        recorder.add("before:" + joinPoint.getSignature().getName());
    }

    public void afterSuccess(JoinPoint joinPoint) {
        recorder.add("after:" + joinPoint.getSignature().getName());
    }
}
```

Hai class `GuardAdvice` và `TraceAdvice` ở đây **không có `@Aspect`**, vì chúng được kết nối thành schema-based aspects trong XML. Điều kiện chặn nằm trong `<aop:pointcut>`; phương thức Java chỉ chứa hành vi. `JoinPoint` là tham số mà Spring/AspectJ cung cấp cho advice và ở ví dụ này được dùng để xem method đang chặn và đối số.

### 5.3. XML: khai báo pointcut một lần, tham chiếu từ hai aspect

`src/main/resources/spring-aop.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="eventRecorder" class="example.EventRecorder"/>

    <bean id="orderService" class="example.OrderService">
        <constructor-arg ref="eventRecorder"/>
    </bean>

    <bean id="guardAdvice" class="example.GuardAdvice">
        <constructor-arg ref="eventRecorder"/>
    </bean>

    <bean id="traceAdvice" class="example.TraceAdvice">
        <constructor-arg ref="eventRecorder"/>
    </bean>

    <aop:config proxy-target-class="true">
        <!-- Pointcut có tên ở mức config: dùng chung cho nhiều aspect. -->
        <aop:pointcut id="placeCalls"
                      expression="execution(* example.OrderService.place(..))"/>

        <!-- Order thấp hơn nghĩa là precedence cao hơn. -->
        <aop:aspect id="guard" ref="guardAdvice" order="0">
            <aop:before method="check" pointcut-ref="placeCalls"/>
        </aop:aspect>

        <aop:aspect id="trace" ref="traceAdvice" order="1">
            <aop:before method="before" pointcut-ref="placeCalls"/>
            <aop:after-returning method="afterSuccess"
                                 pointcut-ref="placeCalls"/>
        </aop:aspect>
    </aop:config>
</beans>
```

**Điểm cần quan sát:** `placeCalls` xuất hiện đúng một lần ở thuộc tính `id` của pointcut nhưng được tham chiếu trong cả hai aspect và nhiều advice. Nếu muốn chọn thêm một method khác, đổi expression tại một nơi. `order="0"` của `guard` làm kiểm tra chạy trước `trace` ở `place()`; lỗi kiểm tra ngăn method đích và advice nằm phía trong thực thi.

### 5.4. Chạy context và kiểm tra hành vi

`src/main/java/example/App.java`:

```java
package example;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class App {
    public static void main(String[] args) {
        try (var context = new ClassPathXmlApplicationContext("spring-aop.xml")) {
            OrderService service = context.getBean("orderService", OrderService.class);
            EventRecorder events = context.getBean(EventRecorder.class);

            System.out.println("value=" + service.place("A-1", 2));
            System.out.println("status=" + service.status());

            try {
                service.place("A-1", 0);
            } catch (IllegalArgumentException ex) {
                System.out.println("error=" + ex.getMessage());
            }

            System.out.println("events=" + events.snapshot());
        }
    }
}
```

Lệnh chạy tại gốc `named-pointcut-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.App
```

Stdout của phần logic (không tính log môi trường Maven/Spring nếu có):

```text
value=PLACED:A-1:2
status=READY
error=quantity must be positive
events=[guard:2, before:place, target:place, after:place, target:status, reject:0]
```

Diễn giải từng trường hợp:

- `place("A-1", 2)` khớp `execution(* example.OrderService.place(..))`; guard ghi `guard:2`, trace ghi `before:place`, target ghi `target:place`, sau khi trả về bình thường trace ghi `after:place`.
- `status()` **không khớp** pointcut nên chỉ ghi `target:status`. Đây là bằng chứng phạm vi chặn đủ hẹp.
- `place("A-1", 0)` khớp, nhưng guard có precedence cao hơn ném ngoại lệ trước khi target và trace chạy; `after-returning` cũng không chạy vì không có kết quả thành công.

Trong ứng dụng thực, tránh phụ thuộc vào thứ tự giữa nhiều advice nếu không khai báo precedence rõ. `order` điều khiển thứ tự aspect; không thay đổi nội dung expression. Và đây là một ví dụ kiểm tra tiền điều kiện trong advice để thấy interceptor order, không phải khuyến nghị đưa toàn bộ kiểm tra nghiệp vụ vào Spring AOP.

## 6. Kiểm thử tự động: named pointcut chỉ chặn đúng phương thức

`src/test/java/example/XmlPointcutTest.java`:

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class XmlPointcutTest {
    @Test
    void namedPointcutIsSharedAndOnlyMatchesPlace() {
        try (var context = new ClassPathXmlApplicationContext("spring-aop.xml")) {
            OrderService service = context.getBean("orderService", OrderService.class);
            EventRecorder recorder = context.getBean(EventRecorder.class);

            assertTrue(AopUtils.isAopProxy(service));
            assertEquals("PLACED:A-1:2", service.place("A-1", 2));
            assertEquals("READY", service.status());

            assertEquals(List.of(
                    "guard:2",
                    "before:place",
                    "target:place",
                    "after:place",
                    "target:status"), recorder.snapshot());
        }
    }

    @Test
    void failingGuardStopsTargetAndInnerAdvice() {
        try (var context = new ClassPathXmlApplicationContext("spring-aop.xml")) {
            OrderService service = context.getBean("orderService", OrderService.class);
            EventRecorder recorder = context.getBean(EventRecorder.class);

            IllegalArgumentException error = assertThrows(
                    IllegalArgumentException.class,
                    () -> service.place("A-1", 0));

            assertEquals("quantity must be positive", error.getMessage());
            assertEquals(List.of("reject:0"), recorder.snapshot());
        }
    }
}
```

Chạy:

```bash
mvn -q test
```

Hai phép thử bổ sung nhau:

1. `AopUtils.isAopProxy(service)` kiểm tra bean thực sự được proxy. Kiểm tra danh sách sự kiện chứng minh cả guard và trace dùng đúng **cùng một named pointcut**; `status()` không bị ảnh hưởng.
2. Lần gọi lỗi chứng minh precedence đã thiết kế và việc không vô tình gọi target/advice sau khi guard từ chối. Nếu xóa `pointcut-ref` hoặc gõ nhầm tên `placeCalls`, application context có thể không khởi tạo; nếu nới expression thành `execution(* example.OrderService.*(..))`, test phạm vi sẽ phát hiện `status()` bị chặn.

Với hệ thống lớn, nên có test tương tự trên một interface/proxy JDK nếu cấu hình thực dùng `proxy-target-class="false"`. Test cấu hình XML chỉ gọi Java object tự tạo bằng `new OrderService(...)` sẽ không chứng minh Spring proxy đã chặn.

## 7. `pointcut-ref` trên advisor khác gì trên aspect?

Trong Spring XML có hai cách kết nối:

**Cách A — schema aspect**: một bean Java chứa nhiều method advice; `aop:before` và `aop:after-returning` gọi các method qua `method`.

```xml
<aop:aspect ref="traceAdvice">
    <aop:before method="before" pointcut-ref="placeCalls"/>
</aop:aspect>
```

**Cách B — Spring advisor**: một bean chuyên trách thực thi advice, ví dụ một implementation của `org.aopalliance.intercept.MethodInterceptor`, gắn với pointcut:

```xml
<!-- Trích đoạn để thêm bên trong <beans> và <aop:config> tương ứng. -->
<bean id="metricsInterceptor" class="example.MetricsInterceptor"/>

<aop:config>
    <aop:pointcut id="placeCalls"
                  expression="execution(* example.OrderService.place(..))"/>

    <aop:advisor advice-ref="metricsInterceptor"
                 pointcut-ref="placeCalls"
                 order="2"/>
</aop:config>
```

`MetricsInterceptor` cần triển khai `MethodInterceptor.invoke(MethodInvocation)` và gọi `invocation.proceed()` để tiếp tục chuỗi chặn. Trích đoạn trên **không thuộc bộ ví dụ runnable ở mục 5**; muốn dùng thì tạo bean/class thật và tránh lặp định nghĩa `placeCalls` trong cùng cấu hình.

Với giao dịch khai báo bằng XML, Spring còn dùng cách phối hợp `<tx:advice id="txAdvice">...</tx:advice>` rồi `<aop:advisor advice-ref="txAdvice" pointcut-ref="..."/>`. Khi ấy `pointcut-ref` vẫn chọn tập phương thức; `advice-ref` chọn chính sách giao dịch. Chúng không thay thế nhau.

**Điều kiện schema:** trong một `aop:config`, đặt `aop:advisor` **sau** các `aop:pointcut` và **trước** các `aop:aspect`. Đây là điểm khác với thứ tự Java annotation, bởi XML schema xác định vị trí phần tử.

## 8. Các lỗi cấu hình thường gặp và cách xử lý

Các lỗi riêng của named pointcut gồm: sai `pointcut-ref` ID làm Spring không resolve; di chuyển `<aop:pointcut>` sai vị trí XSD; nhầm XML ID với named Java method `pc()`; và sửa expression dùng chung nhưng thiếu negative tests cho những aspect khác. Sửa `pointcut-ref` bằng đúng ID không kèm `()`, kiểm tra vị trí/cấu trúc pointcut ở scope phù hợp, rồi khởi tạo context thật.

Khi đổi tên `id`, rà mọi `pointcut-ref`; khi đổi expression mà giữ ID, kiểm tra tác động với **tất cả consumer advisors/aspects**. Nếu advice không chạy dù ID hợp lệ, phân biệt mismatch của expression với việc caller bypass proxy. Với các toán tử `&&` trong XML, viết `and` hoặc `&amp;&amp;`.

## 9. Cách đặt tên và bảo trì pointcut XML

Nên đặt tên nói rõ **tập phương thức được chặn**, như `orderWrites`, `invoiceServiceOperations` hoặc `publicBusinessMethods`. Tên `pointcut1` hay `allMethods` không giúp reviewer phát hiện expression quá rộng. Chú ý ba loại thay đổi:

1. **Đổi expression mà giữ `id`:** mọi advice/advisor đang dùng `pointcut-ref` nhận phạm vi mới. Cần cập nhật test của cả những aspect tiêu thụ pointcut.
2. **Đổi `id`:** phải cập nhật mọi `pointcut-ref`; nếu bỏ sót, context có thể lỗi khi khởi tạo.
3. **Chuyển pointcut từ cục bộ ra mức `aop:config`:** giữ nguyên expression, điều chỉnh vị trí phần tử và tham chiếu để nhiều aspect có thể dùng chung; chạy kiểm thử hồi quy.

Nên gom các pointcut mang cùng ý nghĩa nghiệp vụ, nhưng đừng tái sử dụng một pointcut quá rộng cho các chính sách cần đối tượng khác nhau (chẳng hạn audit mọi service so với transaction chỉ áp dụng thao tác ghi). Một name có vẻ chung nhưng expression chứa danh sách method rất cụ thể cũng dễ bị stale khi refactor; test bảo vệ phạm vi chọn là cần thiết.

Nếu muốn tách cấu hình thành nhiều file XML, có thể dùng `<import resource="other-aop.xml"/>` theo cơ chế cấu hình Spring; bảo đảm nơi định nghĩa pointcut và nơi tham chiếu thực sự nằm trong phạm vi XML/schema và bean definition có thể được Spring xử lý. Với cấu hình phức tạp, test khởi tạo `ApplicationContext` là bằng chứng tốt hơn suy đoán rằng tên `id` toàn cục sẽ có hiệu lực bất kể nơi khai báo.

## 10. Bài tập kiểm chứng

Từ bộ ví dụ runnable, thực hiện theo trình tự:

1. Chạy `mvn -q test` rồi đổi expression `placeCalls` thành `execution(* example.OrderService.*(..))`. Quan sát test chặn ngoài dự kiến `status()`; trả lại expression ban đầu.
2. Đổi `pointcut-ref="placeCalls"` trong riêng `trace` thành một tên không tồn tại. Quan sát lỗi khởi tạo context; sửa lại đúng tên.
3. Trong aspect `trace`, thử khai báo một pointcut cục bộ dành cho `status()` và một advice riêng dùng `pointcut-ref` của nó. Kiểm tra `place()` và `status()` sinh các sự kiện đúng phạm vi.
4. Đổi `order` của các aspect và cập nhật test để thấy khác biệt thứ tự. Riêng trường hợp guard ném lỗi, hãy giải thích advice nào có cơ hội chạy trước.
5. Bổ sung một `MethodInterceptor` hợp lệ rồi gắn bằng `aop:advisor` vào **cùng top-level pointcut**. Chứng minh bằng test rằng advisor và schema aspect chia sẻ đúng tập lời gọi.

**Kết quả cần đạt:** bạn đọc được XML và xác định được expression nào chọn phương thức, `pointcut-ref` trỏ tới `id` nào, advice thuộc bean nào, trình tự thực thi ra sao, và test nào chứng minh không chặn thừa.

### Tài liệu chính thức

- Spring Framework 6.2 — *Schema-based AOP Support* (named pointcuts, scope, advisor, thứ tự): https://docs.spring.io/spring-framework/reference/6.2/core/aop/schema.html
- Spring Framework — *Spring AOP Proxies* (self-invocation, giới hạn proxy): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — *Pointcut Expressions* (cú pháp `execution`, `args`, v.v.): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
