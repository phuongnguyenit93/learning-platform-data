# `aop:config` và khai báo `aop:aspect` trong Spring AOP bằng XML

## 1. Mục tiêu và ngữ cảnh

Spring Framework cho phép khai báo **Spring AOP proxy, pointcut và advice bằng XML** qua namespace `aop`. Cách này hữu ích khi duy trì dự án cấu hình Spring bằng XML hoặc cần bổ sung hành vi cắt ngang cho bean đã có mà không muốn đặt annotation AOP trên chính lớp nghiệp vụ.

Bài này tập trung vào hai thành phần:

- `<aop:config>`: nơi khai báo pointcut, advisor và aspect để Spring tự tạo proxy cho các bean phù hợp.
- `<aop:aspect>`: ánh xạ **một Spring bean chứa phương thức advice** với pointcut và các loại advice khai báo trong XML.

Ví dụ xuyên suốt là ghi trace cho phương thức thanh toán trong **Spring AOP proxy-based**. Các khái niệm chung về lập trình hướng khía cạnh chỉ được nhắc tới khi cần hiểu chính xác hành vi Spring.

Sau bài học, bạn có thể giải thích vai trò `ref`, `id`, `pointcut-ref`, `method`; viết file XML hoàn chỉnh; chạy một ứng dụng Java 17+; kiểm tra proxy thật sự được tạo; và chẩn đoán trường hợp XML hợp lệ nhưng advice không chạy.

## 2. Thành phần XML và các quan hệ quan trọng

`<aop:config>` tạo các định nghĩa AOP theo schema; `<aop:aspect ref="loggingBean">` gắn **bean advice đã đăng ký** với danh sách method/pointcut tương ứng. Khung sau thể hiện đủ ba loại tên:

~~~xml
<bean id="targetService" class="demo.TargetService"/>
<bean id="loggingBean" class="demo.LoggingAdvice"/>
<aop:config>
    <aop:pointcut id="serviceCall"
                  expression="execution(* demo.TargetService.work(..))"/>
    <aop:aspect id="loggingAspect" ref="loggingBean">
        <aop:before method="beforeWork" pointcut-ref="serviceCall"/>
    </aop:aspect>
</aop:config>
~~~

Đây là fragment, phải có `TargetService.work` và `LoggingAdvice.beforeWork` tương ứng. **`loggingBean`** là Spring bean ID; **`loggingAspect`** là ID khai báo aspect; **`serviceCall`** là pointcut ID. `method="beforeWork"` gọi Java method của bean `loggingBean`; `pointcut-ref="serviceCall"` không trỏ tới method Java. Nếu khai báo thêm `aop:advisor`, giữ thứ tự XSD **pointcut → advisor → aspect**.

Cơ chế thực thi: caller → Spring AOP proxy → advisor phù hợp → advice method → target. Khác với `<aop:aspectj-autoproxy>`, Java POJO `LoggingAdvice` không cần `@Aspect`; metadata advice đã có trong XML.

## 3. Dạng pointcut, phạm vi và lựa chọn khai báo

### Pointcut dùng chung

~~~xml
<aop:config>
    <aop:pointcut id="paymentOperations"
                  expression="execution(public * demo.PaymentService.*(..))"/>
    <aop:aspect ref="auditBean">
        <aop:before method="check" pointcut-ref="paymentOperations"/>
        <aop:after method="finish" pointcut-ref="paymentOperations"/>
    </aop:aspect>
</aop:config>
~~~

Ví dụ là fragment: `auditBean` phải được khai báo thành Spring bean và có hai method phù hợp. Pointcut ở cấp `aop:config` có thể được các aspect/advisor trong cấu hình tham chiếu, giúp tránh lặp lại expression.

Biểu thức `execution(public * demo.PaymentService.*(..))` mô tả các method public, bất kỳ kiểu trả về, bất kỳ tên, số lượng tham số bất kỳ, thuộc class `demo.PaymentService`. Nó **không có nghĩa** “mọi service trong package demo”. Hãy chọn package/class/method thực tế để giới hạn phạm vi.

### Pointcut trực tiếp trong advice

~~~xml
<aop:aspect ref="auditBean">
    <aop:before method="check"
                pointcut="execution(* demo.PaymentService.pay(..))"/>
</aop:aspect>
~~~

`pointcut="..."` phù hợp khi biểu thức chỉ dùng một lần; `pointcut-ref="..."` phù hợp khi muốn tái sử dụng pointcut đã đặt tên. Không đặt cả hai trên cùng một advice.

### Pointcut cục bộ trong aspect

~~~xml
<aop:aspect ref="auditBean">
    <aop:pointcut id="withinPayments"
                  expression="within(demo..*)"/>
    <aop:before method="check" pointcut-ref="withinPayments"/>
</aop:aspect>
~~~

`within(demo..*)` là biểu thức minh họa cho các type dưới package `demo`; trong dự án thật cần thu hẹp nếu không muốn quét quá nhiều bean. Pointcut cục bộ thuộc phạm vi cấu hình của aspect đó.

### Kết hợp điều kiện và escaping XML

~~~xml
<aop:pointcut id="namedPayment"
              expression="execution(* demo.PaymentService.pay(..)) and args(orderId)"/>
~~~

Trong XML, toán tử `&&` phải viết `&amp;&amp;`; Spring cũng hỗ trợ các từ `and`, `or` và `not`, thường dễ đọc hơn. Với expression có `<` hoặc `>` trong giá trị thuộc tính, cũng phải escape đúng cú pháp XML. Đối với biểu thức có binding như `args(orderId)`, method advice phải khai báo tham số/binding tương ứng; fragment trên chỉ nhằm diễn đạt cú pháp pointcut.

## 4. Ví dụ chạy được: tạo proxy và khai báo `aop:aspect`

Ví dụ tối giản dưới đây sử dụng **Spring Framework 6.2.x, Java 17+, Maven**. Không yêu cầu Spring Boot, không chạy web server; mục tiêu là thấy một lời gọi method đi qua Spring AOP proxy và advice trong XML.

### 4.1. Cấu trúc tệp

~~~text
xml-spring-aop/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── BillingService.java
    │   │   ├── TraceAspect.java
    │   │   └── Main.java
    │   └── resources/
    │       └── spring/aop-context.xml
    └── test/java/demo/
        └── XmlAopTest.java
~~~

### 4.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>xml-spring-aop</artifactId>
    <version>1.0-SNAPSHOT</version>
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
            <version>1.9.24</version>
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
~~~

Các phiên bản được cố định để ví dụ có thể tái hiện; trong ứng dụng thực hãy đồng bộ với BOM/framework version của dự án. `aspectjweaver` cung cấp các thành phần AspectJ cần cho biểu thức pointcut của Spring AOP, **không có nghĩa ví dụ đang dùng AspectJ load-time weaving**.

### 4.3. `src/main/java/demo/BillingService.java`

~~~java
package demo;

public class BillingService {
    public String pay(String orderId) {
        System.out.println("service.pay:" + orderId);

        if ("bad".equals(orderId)) {
            throw new IllegalArgumentException("invalid order");
        }
        return "paid:" + orderId;
    }
}
~~~

Method `pay` là public, không final; class cũng không final để ví dụ có thể dùng class-based proxy.

### 4.4. `src/main/java/demo/TraceAspect.java`

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;

public class TraceAspect {
    private final AtomicInteger invocationCount = new AtomicInteger();

    public Object trace(ProceedingJoinPoint joinPoint) throws Throwable {
        invocationCount.incrementAndGet();
        String orderId = (String) joinPoint.getArgs()[0];
        System.out.println("aspect.before:" + orderId);

        try {
            Object result = joinPoint.proceed();
            System.out.println("aspect.after-returning:" + result);
            return result;
        } catch (Throwable exception) {
            System.out.println("aspect.after-throwing:"
                    + exception.getClass().getSimpleName());
            throw exception;
        } finally {
            System.out.println("aspect.finally:" + orderId);
        }
    }

    public int invocationCount() {
        return invocationCount.get();
    }
}
~~~

Đây là một Spring bean Java bình thường: **không có `@Aspect` hay `@Around`**. `trace(ProceedingJoinPoint)` được gọi vì XML khai báo `<aop:around method="trace" .../>`. Dữ liệu `orderId` là biến cục bộ của mỗi invocation; bộ đếm dùng `AtomicInteger` vì aspect bean thường là singleton và có thể phục vụ nhiều lời gọi đồng thời.

Lời gọi `joinPoint.proceed()` quyết định việc thực thi method gốc. Khi thành công, advice trả nguyên kết quả; khi thất bại, advice ghi dấu vết rồi ném lại exception, không nuốt lỗi. Khối `finally` chạy cả ở nhánh thành công và lỗi.

### 4.5. `src/main/resources/spring/aop-context.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="billingService" class="demo.BillingService"/>
    <bean id="traceAspectBean" class="demo.TraceAspect"/>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="payOperation"
                      expression="execution(public * demo.BillingService.pay(..))"/>

        <aop:aspect id="billingTrace" ref="traceAspectBean">
            <aop:around pointcut-ref="payOperation" method="trace"/>
        </aop:aspect>
    </aop:config>
</beans>
~~~

Các điểm đáng chú ý:

- `traceAspectBean` là bean chứa logic advice; `billingTrace` là định danh XML của aspect; `payOperation` là định danh pointcut.
- `proxy-target-class="true"` yêu cầu Spring dùng class-based proxy để ví dụ có thể truy xuất bean qua `BillingService.class`. Với interface và JDK proxy, cách lấy bean/cast có thể khác.
- `pointcut-ref="payOperation"` tránh lặp lại expression.
- `aop:config` đăng ký cơ chế AOP proxy cho các bean Spring phù hợp; không cần thêm `<aop:aspectj-autoproxy/>` vào ví dụ chỉ dùng schema-style này.

### 4.6. `src/main/java/demo/Main.java`

~~~java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                     new ClassPathXmlApplicationContext("spring/aop-context.xml")) {
            BillingService service = context.getBean(BillingService.class);

            System.out.println(service.pay("ok"));

            try {
                service.pay("bad");
            } catch (IllegalArgumentException exception) {
                System.out.println("caller.caught:" + exception.getMessage());
            }
        }
    }
}
~~~

Chạy trong thư mục `xml-spring-aop` với Maven và JDK 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.Main
~~~

**Các dòng stdout do chính mã Java in ra**, theo thứ tự:

~~~text
aspect.before:ok
service.pay:ok
aspect.after-returning:paid:ok
aspect.finally:ok
paid:ok
aspect.before:bad
service.pay:bad
aspect.after-throwing:IllegalArgumentException
aspect.finally:bad
caller.caught:invalid order
~~~

Log của Maven hoặc thư viện (nếu cấu hình logging khác) không thuộc output kiểm chứng trên. Trace thành công và trace lỗi cùng đi qua một Spring AOP proxy được tạo từ XML.

### 4.7. Kiểm thử proxy và advice trong `src/test/java/demo/XmlAopTest.java`

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class XmlAopTest {
    @Test
    void xmlAspectInterceptsSuccessAndFailureThroughProxy() {
        try (var context =
                     new ClassPathXmlApplicationContext("spring/aop-context.xml")) {
            BillingService service = context.getBean(BillingService.class);
            TraceAspect trace = context.getBean("traceAspectBean", TraceAspect.class);

            assertTrue(AopUtils.isAopProxy(service));
            assertTrue(AopUtils.isCglibProxy(service));
            assertEquals(0, trace.invocationCount());

            assertEquals("paid:ok", service.pay("ok"));
            assertThrows(IllegalArgumentException.class,
                    () -> service.pay("bad"));

            assertEquals(2, trace.invocationCount());
        }
    }
}
~~~

Chạy:

~~~bash
mvn -q test
~~~

Kỳ vọng: **1 test thành công, tổng cộng 2 lần advice chạy**. Test đo được cả cấu hình proxy lẫn thực tế Spring gọi advice; chỉ assert kết quả thanh toán mà không assert `invocationCount` sẽ không đủ chứng minh XML AOP đang hoạt động.

## 5. Khai báo các loại advice trong `aop:aspect`

Spring XML schema hỗ trợ các loại advice quen thuộc, không bắt buộc dùng `around`:

| Element XML | Khi chạy | Điều kiện và chữ ký method |
| --- | --- | --- |
| `<aop:before>` | Trước khi gọi target | Method advice thường trả `void`, có thể nhận `JoinPoint`. |
| `<aop:after-returning>` | Target/chuỗi advice hoàn thành bình thường | Có thể dùng `returning="retVal"` để nhận kết quả. |
| `<aop:after-throwing>` | Target/chuỗi advice thoát bằng exception phù hợp | Có thể dùng `throwing="error"` để nhận exception. |
| `<aop:after>` | Sau khi method kết thúc, kể cả thất bại | Giống ý nghĩa `finally`; không dùng để thay thế xử lý trả về. |
| `<aop:around>` | Bao quanh invocation | Method phải nhận `ProceedingJoinPoint` ở vị trí đầu, trả `Object` và gọi `proceed()` nếu muốn thực thi target. |

Ví dụ khai báo thay thế **không phải phần của cấu hình chạy ở mục 4**:

~~~xml
<aop:aspect id="audit" ref="auditAdviceBean">
    <aop:before pointcut-ref="payOperation" method="beforePayment"/>
    <aop:after-returning pointcut-ref="payOperation"
                         method="afterSuccess"
                         returning="result" arg-names="result"/>
    <aop:after-throwing pointcut-ref="payOperation"
                        method="afterError"
                        throwing="error" arg-names="error"/>
    <aop:after pointcut-ref="payOperation" method="cleanup"/>
</aop:aspect>
~~~

Các method tương ứng trong bean `auditAdviceBean`, ví dụ:

~~~java
public void beforePayment() {
    // Chạy trước.
}

public void afterSuccess(Object result) {
    // Nhận giá trị trả về khi thành công.
}

public void afterError(Exception error) {
    // Nhận exception khớp kiểu tham số.
}

public void cleanup() {
    // Chạy khi invocation kết thúc.
}
~~~

Đây là **các method minh họa nằm trong class advice**, chưa là tệp Java độc lập. `returning` và `throwing` đặt tên biến được bind với tham số method advice; `arg-names` giúp khai báo binding rõ khi metadata tên tham số trong bytecode không sẵn. Chữ ký `Exception` chỉ khớp exception tương thích; một advice bắt `Throwable` có phạm vi rộng hơn.

### Advice nào phù hợp?

- Chỉ cần kiểm tra/log trước: ưu tiên `before`.
- Chỉ cần xử lý kết quả trả về: `after-returning`.
- Chỉ cần ghi nhận lỗi: `after-throwing`.
- Cần cleanup dù thành công hay lỗi: `after`.
- Cần đo thời gian bao gồm trước/sau, thay đổi đối số, quyết định retry hoặc chặn gọi target: `around`. Với `around`, quên gọi `proceed()` khiến method đích không chạy.

Nếu nhiều advice cần chạy ở cùng join point, phải xác định thứ tự; không suy ra thứ tự chỉ bằng tên method Java.

## 6. Thứ tự áp dụng aspect và các cấu hình mở rộng

### Thứ tự giữa các aspect

Có thể khai báo `order` trực tiếp:

~~~xml
<aop:config>
    <aop:pointcut id="operation"
                  expression="execution(* demo.BillingService.pay(..))"/>

    <aop:aspect id="security" ref="securityAdviceBean" order="0">
        <aop:before method="verify" pointcut-ref="operation"/>
    </aop:aspect>

    <aop:aspect id="tracing" ref="traceAdviceBean" order="10">
        <aop:around method="trace" pointcut-ref="operation"/>
    </aop:aspect>
</aop:config>
~~~

Đây là fragment minh họa: hai bean advice và method phải tồn tại. **Giá trị order nhỏ hơn có độ ưu tiên cao hơn.** Advice ưu tiên cao chạy trước trên đường vào, sau trên đường ra. Khi nhiều advice ở *cùng một* `<aop:aspect>`, theo tài liệu Spring, thứ tự khai báo các advice element quyết định độ ưu tiên; nếu logic trở nên phức tạp, tách aspect và kiểm thử thứ tự thực tế.

### `aop:advisor` khác gì `aop:aspect`?

~~~xml
<aop:config>
    <aop:pointcut id="serviceOps"
                  expression="execution(* demo.BillingService.pay(..))"/>
    <aop:advisor pointcut-ref="serviceOps" advice-ref="methodInterceptorBean"/>
</aop:config>
~~~

`aop:advisor` kết nối một **bean triển khai interface advice của Spring AOP** (ví dụ `MethodInterceptor`) với pointcut; còn `aop:aspect` cho phép nhóm nhiều phương thức advice Java bình thường vào một aspect bằng XML. Nếu đồng thời có advisor và aspect trong một `aop:config` thì đặt advisor trước aspect như yêu cầu của schema.

### `<aop:aspectj-autoproxy/>` không thay thế `<aop:aspect>`

`<aop:aspectj-autoproxy/>` kích hoạt auto-detection cho các bean khai báo `@Aspect`; `<aop:config>` là cách cấu hình pointcut/advice trực tiếp bằng XML. Hai kiểu đều dùng Spring AOP, nhưng metadata khai báo khác nhau. Với ví dụ ở mục 4, chỉ cần `<aop:config>` và bean Java bình thường.

## 7. Những giới hạn proxy-based AOP cần biết

XML schema-based AOP chỉ can thiệp **method execution đi qua Spring proxy** của bean được quản lý. Tạo đối tượng bằng `new` hoặc gọi `this.inner()` từ target sẽ không tự kích hoạt interceptor mới. JDK proxy thường expose interface methods; CGLIB subclass proxy không override được private/final method hoặc final class.

Một `aop-context.xml` chưa được import/load vào Spring context sẽ không tạo advisor, dù file nằm trên classpath. Lớp advice thường là singleton: lưu dữ liệu riêng invocation trong biến cục bộ, không trong field mutable dùng chung. Bài chuyên sâu về **proxy-target-class/expose-proxy** giải thích và thử từng giới hạn proxy.

## 8. Chẩn đoán khi cấu hình XML không hoạt động

Nếu XML parse được nhưng advice không chạy, xác minh theo thứ tự: (1) context đã nạp đúng XML và các bean ID `ref` đều tồn tại; (2) `method` khớp chữ ký Java trên advice bean; (3) `pointcut-ref`/expression khớp class/method thực tế; (4) target lấy từ Spring context và lời gọi qua proxy; (5) có advisor khác hoặc cấu hình chồng lấn thay đổi hành vi không.

Dùng `AopUtils.isAopProxy(bean)` như phép kiểm tra cấu hình bổ trợ, rồi **assert bộ đếm/event trong advice** cho một method phải match, một method không match, cả success và exception path. Một bean được proxy không có nghĩa tất cả advice đều chạy trên mọi method.

## 9. Checklist triển khai

- [ ] File XML đã khai báo `beans`, `aop` namespace và các XSD phù hợp.
- [ ] Bean target và bean advice được quản lý trong **cùng ApplicationContext phù hợp** hoặc context có khả năng nhìn thấy nhau.
- [ ] Các phần tử con của `aop:config` đúng thứ tự schema; `ref`, `pointcut-ref`, `method` đều tồn tại.
- [ ] Biểu thức pointcut chỉ khớp method/package cần áp dụng; điều kiện kết hợp được escape hợp lệ trong XML.
- [ ] Lựa chọn loại advice ít quyền lực nhất đáp ứng nhu cầu; với `around` có `proceed()` và preserve exception/return value đúng yêu cầu.
- [ ] Kiểm tra class/interface proxy, method public/final, self-invocation và cách caller lấy bean.
- [ ] Test qua `ClassPathXmlApplicationContext` hoặc Spring context thật, đo advice invocation thay vì chỉ xem response.
- [ ] Nếu có nhiều aspect, test thứ tự advice với `order` hoặc `Ordered`.
- [ ] Không lưu dữ liệu request-specific vào mutable field của aspect singleton.

**Kết quả mong đợi:** một bean nghiệp vụ giữ nguyên code, Spring tạo proxy từ `<aop:config>`, chạy phương thức advice của bean tham chiếu bởi `<aop:aspect ref="...">` và trả đúng giá trị/ngoại lệ cho caller. Những điều này được kiểm chứng trong test, không chỉ suy ra từ việc XML parse thành công.

## Tài liệu tham khảo

- Spring Framework Reference — Schema-based AOP Support: https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Spring Framework Reference — AOP Concepts: https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — Declaring a Pointcut: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
