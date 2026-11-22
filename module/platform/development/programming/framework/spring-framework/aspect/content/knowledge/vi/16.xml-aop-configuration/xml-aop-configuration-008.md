# `proxy-target-class` và `expose-proxy` trong cấu hình XML của Spring AOP

## 1. Vì sao cần hai thuộc tính này?

Trong Spring Framework, một bean được áp dụng Spring AOP thường được cung cấp cho nơi gọi dưới dạng **proxy**. Khi ứng dụng cấu hình aspect bằng XML, hai thuộc tính có ảnh hưởng quan trọng nhưng giải quyết **hai vấn đề khác nhau**:

- `proxy-target-class`: quyết định Spring ưu tiên loại proxy nào cho bean có thể được proxy, đặc biệt khi class triển khai interface. `true` yêu cầu proxy dựa trên class (CGLIB); `false` cho phép cơ chế mặc định của Spring chọn JDK dynamic proxy nếu có interface thích hợp, còn class không có interface vẫn cần class proxy.
- `expose-proxy`: quyết định proxy hiện tại có được Spring công bố tạm thời cho `AopContext.currentProxy()` trong **luồng đang thực thi lời gọi qua proxy** hay không. `true` mở khả năng truy cập đó; `false` là mặc định và không bảo đảm đọc được proxy.

Hai thuộc tính đều có trong **`<aop:config>`** (schema-based aspect) và **`<aop:aspectj-autoproxy>`** (tự tìm bean `@Aspect`). Chúng là các setting của cơ chế **Spring AOP proxy**, không phải kỹ thuật AspectJ compile-time weaving hay load-time weaving.

### Bảng đối chiếu nhanh

| XML | Tác dụng chính | Không làm được |
| --- | --- | --- |
| `proxy-target-class="false"` | Dùng quy tắc chọn proxy thông thường; bean có interface thường nhận JDK proxy, bean không có interface dùng class proxy. | Không ép JDK proxy cho class không có interface; không sửa self-invocation. |
| `proxy-target-class="true"` | Ép dùng class proxy (CGLIB) cho các bean do auto-proxy creator tương ứng xử lý. | Không intercept `private`, `final` method hoặc self-invocation qua `this`. |
| `expose-proxy="false"` | Không bật khả năng tra cứu proxy hiện tại qua `AopContext.currentProxy()`. | Không có nghĩa advice bị tắt; lời gọi qua proxy vẫn được intercept. |
| `expose-proxy="true"` | Cho phép `AopContext.currentProxy()` hoạt động trong lời gọi được quản lý bởi AOP proxy. | Không tự đổi `this.method()` thành lời gọi proxy; không truyền proxy sang thread khác. |

## 2. Viết XML đúng schema Spring

Ví dụ một file `src/main/resources/aop.xml` dùng Spring AOP schema:

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

    <bean id="orderService" class="com.example.springxml.OrderService"/>
    <bean id="traceAdvice" class="com.example.springxml.TraceAdvice"/>

    <aop:config proxy-target-class="false" expose-proxy="true">
        <aop:aspect ref="traceAdvice">
            <aop:pointcut id="orderMethods"
                          expression="execution(* com.example.springxml.OrderService.*(..))"/>
            <aop:around method="around" pointcut-ref="orderMethods"/>
        </aop:aspect>
    </aop:config>
</beans>
```

Ý nghĩa trong Spring:

1. `<aop:config>` đăng ký hạ tầng tự tạo proxy khi có advisor phù hợp với bean.
2. `<aop:aspect ref="traceAdvice">` trỏ đến bean chứa method advice thuần Java; **bean advice này không bắt buộc có `@Aspect`** vì XML đã khai báo aspect.
3. `<aop:pointcut>` xác định method execution của `OrderService` cần áp dụng; `<aop:around>` liên kết method `around` với pointcut đã đặt tên.
4. `proxy-target-class="false"` cho phép chọn JDK proxy cho `OrderService` vì ví dụ bên dưới có interface. `expose-proxy="true"` cho phép service lấy proxy trong lúc đang chạy thông qua lời gọi đã được advice.

Cú pháp XML dùng tên `proxy-target-class`, `expose-proxy` (kebab-case), khác với tên thuộc tính Java `proxyTargetClass` và `exposeProxy`. Không viết `proxyTargetClass` trực tiếp trong tag XML.

### Khi dùng `@Aspect` thay cho aspect khai báo trong XML

Nếu aspect là một bean Java có `@Aspect`, có thể bật cơ chế nhận diện nó bằng:

```xml
<aop:aspectj-autoproxy proxy-target-class="true"
                       expose-proxy="true"/>
```

Các bean `@Aspect` vẫn cần được đăng ký bằng `<bean>` hoặc component scanning. Tag này **không tự tạo bean aspect** và khác với `<aop:config><aop:aspect ...>`. Thông thường chọn cách khai báo phù hợp với dự án; tránh tạo advisor trùng nhau khi cấu hình cả hai đường. Cả hai cần phần Spring AOP trên classpath và khả năng phân tích biểu thức AspectJ (thường có `aspectjweaver`).

## 3. Ví dụ Java 17+ quan sát loại proxy và self-invocation

Ví dụ sau chạy với **Spring Framework + Spring AOP được khởi tạo trực tiếp bằng XML**, không dựa vào Spring Boot auto-configuration; nhờ đó việc so sánh `proxy-target-class` có kết quả dễ kiểm soát. Cấu trúc mã:

```text
src/main/java/com/example/springxml/
  OrderOperations.java
  OrderService.java
  TraceAdvice.java
  Demo.java
src/main/resources/aop.xml
```

**`OrderOperations.java`** — interface được caller sử dụng:

```java
package com.example.springxml;

public interface OrderOperations {
    void place();
    void reserve();
}
```

**`OrderService.java`** — hai cách gọi cùng method `reserve()`:

```java
package com.example.springxml;

import org.springframework.aop.framework.AopContext;

public class OrderService implements OrderOperations {

    @Override
    public void place() {
        System.out.println("service: place");

        // Gọi trực tiếp trên 'this': không đi qua Spring proxy.
        this.reserve();

        // Đi qua Spring proxy đang được expose trong lời gọi place().
        ((OrderOperations) AopContext.currentProxy()).reserve();
    }

    @Override
    public void reserve() {
        System.out.println("service: reserve");
    }
}
```

**`TraceAdvice.java`** — POJO chứa advice được tham chiếu trong XML:

```java
package com.example.springxml;

import org.aspectj.lang.ProceedingJoinPoint;

public class TraceAdvice {

    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();
        System.out.println("before: " + method);
        try {
            return pjp.proceed();
        } finally {
            System.out.println("after: " + method);
        }
    }
}
```

**`Demo.java`** — lấy bean qua interface và kiểm tra proxy:

```java
package com.example.springxml;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Demo {

    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("aop.xml")) {

            OrderOperations orders =
                    context.getBean("orderService", OrderOperations.class);

            System.out.println("aopProxy=" + AopUtils.isAopProxy(orders));
            System.out.println("jdkProxy=" + AopUtils.isJdkDynamicProxy(orders));
            orders.place();
        }
    }
}
```

**Các dependency cần có:** `spring-context`, `spring-aop` và `org.aspectj:aspectjweaver`, ở các phiên bản tương thích với nhau (có thể quản lý bằng BOM Spring/Boot). Ví dụ Java trên cần classpath chứa các thư viện đó; không thể chỉ dùng `javac` với JDK thuần. Trong dự án Maven đã cấu hình `exec-maven-plugin`, có thể chạy main với `mvn compile exec:java -Dexec.mainClass=com.example.springxml.Demo`. Trong Gradle có plugin `application`, đặt main class là `com.example.springxml.Demo` và chạy task `run`. Các lệnh này giả định dự án đã được khai báo dependency/plugin phù hợp.

Với XML ở mục 2, những dòng do mã ví dụ in ra (không tính logging khác do cấu hình runtime) theo thứ tự sẽ là:

```text
aopProxy=true
jdkProxy=true
before: place
service: place
service: reserve
before: reserve
service: reserve
after: reserve
after: place
```

Giải thích: `orders.place()` gọi vào JDK proxy và đi qua `around`. Lệnh `this.reserve()` được thực hiện trực tiếp trên target, nên chỉ có dòng `service: reserve`. Lần gọi `AopContext.currentProxy().reserve()` quay lại proxy, vì thế có cả `before: reserve` và `after: reserve`. `AopContext.currentProxy()` được gọi trong cùng thread và bên trong method mà proxy đang xử lý; nếu gọi ngoài hoàn cảnh đó, Spring có thể ném `IllegalStateException`.

## 4. Thay `proxy-target-class`: kết quả nào thay đổi?

Đổi duy nhất thuộc tính trong file XML:

```xml
<aop:config proxy-target-class="true" expose-proxy="true">
    <!-- Giữ nguyên aspect, pointcut và các bean của ví dụ -->
</aop:config>
```

**Đây là đoạn rút gọn minh họa vị trí thuộc tính:** trong file runnable vẫn phải giữ nguyên các phần tử con `<aop:aspect>` và `<aop:pointcut>` như mục 2, không thay thế chúng bằng comment. Sau khi đổi, Spring tạo proxy dựa trên subclass của `OrderService`; các dòng đầu thành:

```text
aopProxy=true
jdkProxy=false
```

Phần log `before/after/service` của ví dụ vẫn như trước. Trong cấu hình CGLIB này, `context.getBean("orderService", OrderService.class)` có thể dùng được vì proxy là subclass của target class; ở chế độ JDK proxy, bean được inject/cast qua `OrderOperations`, còn lookup đòi chính `OrderService.class` có thể không khớp type.

Điểm cần nhớ:

- `false` không phải cam kết “luôn là JDK proxy”. Không có interface thích hợp thì Spring cần class proxy.
- `true` yêu cầu class proxy ngay cả khi target có interface. Nó **không** biến Spring AOP thành bytecode weaving hoặc làm method `final`/`private` intercept được.
- CGLIB dùng subclass của target; class `final` không thể subclass để proxy. `final` method không override được; `private` method không được advice trong cơ chế này. JDK proxy chỉ cung cấp các method của interface được proxy cho caller.
- Khi chương trình inject qua interface, việc đổi sang CGLIB thường không cần thiết chỉ để gọi các method đã công bố trên interface. Nếu đổi cho mục đích inject target concrete type hoặc intercept method chỉ nằm ở class, cần kiểm thử đầy đủ.
- Có thể dùng `AopUtils.isCglibProxy(bean)` và `AopUtils.isJdkDynamicProxy(bean)` trong integration test; tránh giả định class runtime có tên cố định.

### Cấu hình nhiều XML và cơ chế “strongest wins”

Spring hợp nhất các cấu hình auto-proxy creator trong **cùng ApplicationContext**. Nếu một `<aop:config>` bật `proxy-target-class="true"` trong khi cấu hình khác để `false`, việc bật class proxy có thể ảnh hưởng tất cả bean được các cơ chế AOP đó proxy, bao gồm các cấu hình tương tác như `<aop:aspectj-autoproxy>` và `<tx:annotation-driven>`. Giá trị `false` cục bộ không phải cách bảo đảm ghi đè một setting `true` từ cấu hình khác.

Vì vậy khi kết quả thực tế không giống ví dụ, kiểm tra toàn bộ XML được import cùng hạ tầng Spring AOP và transaction. Trong Spring Boot, auto-configuration có thể chọn class proxy mặc định tùy phiên bản/cấu hình; `spring.aop.proxy-target-class` là property ở lớp Spring Boot, còn các thuộc tính XML ở đây thuộc Spring Framework. Không lấy mặc định của ứng dụng Boot để suy luận kết quả của một ví dụ `ClassPathXmlApplicationContext` thuần.

## 5. Thay `expose-proxy`: tác động và ranh giới

Nếu đổi riêng `expose-proxy` thành `false`:

```xml
<aop:config proxy-target-class="false" expose-proxy="false">
    <!-- Giữ nguyên aspect và pointcut của ví dụ -->
</aop:config>
```

Câu lệnh `this.reserve()` trong `place()` vẫn thực thi trực tiếp và không có advice. Nhưng lệnh `AopContext.currentProxy()` không có proxy hiện tại được expose theo cấu hình này, nên ném `IllegalStateException`. Do `TraceAdvice.around` có `finally`, log trước khi lỗi được ném khỏi caller (bỏ qua phần startup) sẽ là:

```text
aopProxy=true
jdkProxy=true
before: place
service: place
service: reserve
after: place
```

Sau đó stack trace có thể xuất hiện nếu exception được để lan ra ngoài `main`. Đây là **hành vi có chủ đích để phân biệt setting**: bật/tắt `expose-proxy` không quyết định bean có được advice hay không; nó chỉ quyết định có thể tra cứu proxy trong ngữ cảnh lời gọi đang được intercept.

### Vì sao Spring không tự sửa self-invocation?

Trong Spring AOP, lời gọi bên ngoài vào proxy mới kích hoạt interceptor chain. Bên trong body của target, `this` vẫn là đối tượng target; `this.reserve()` bỏ qua proxy. Dùng `proxy-target-class="true"` cũng không đổi điều này.

Khi cần advice chạy trên một lời gọi nội bộ, thứ tự lựa chọn hợp lý là:

1. **Tách method cần intercept sang một Spring bean khác**, để bean hiện tại gọi qua reference được inject; cách này dễ test và không gắn business code với API Spring AOP.
2. Nếu kiến trúc đòi giữ trong class, có thể tổ chức lời gọi qua self-reference trỏ đến bean proxy, nhưng cần xử lý dependency cycle và kiểu proxy cẩn thận.
3. Chỉ khi cần thiết mới bật `expose-proxy="true"` và gọi `AopContext.currentProxy()`. Đây là cách ràng buộc source nghiệp vụ trực tiếp với Spring AOP, làm khó unit test thuần Java và tăng chi phí truy cập proxy hiện tại.

**Hạn chế của `AopContext.currentProxy()`:**

- Proxy được expose thông qua ngữ cảnh gắn với thread của lời gọi AOP hiện tại; không mang nguyên sang `CompletableFuture`, `@Async`, `ExecutorService` hoặc thread khác.
- Gọi từ constructor, từ đối tượng được tạo bằng `new`, trước khi vào lời gọi proxy hoặc sau khi ra khỏi lời gọi proxy không có bảo đảm lấy được proxy.
- Kiểu trả về là `Object`. Với JDK proxy, cast sang **interface có được proxy**; cast sang class implementation gây `ClassCastException`.
- Proxy lấy được phải là proxy Spring liên quan đúng lời gọi hiện tại; `expose-proxy` không cấp global singleton lookup.
- Bật `true` chỉ để “phòng trường hợp cần” là không cần thiết. Nó tạo coupling và overhead ngay cả khi ứng dụng không dùng `AopContext`.

## 6. So sánh `<aop:config>`, `<aop:aspectj-autoproxy>` và Java config

| Ngữ cảnh | Cấu hình | Khi nào sử dụng |
| --- | --- | --- |
| Aspect thuần Java khai báo bằng Spring XML | `<aop:config proxy-target-class="true" expose-proxy="true"> ... </aop:config>` | Advice/pointcut nằm trong XML, tham chiếu bean bằng `ref`. |
| Bean `@Aspect` được Spring nhận diện | `<aop:aspectj-autoproxy proxy-target-class="true" expose-proxy="true"/>` | Advice/pointcut nằm trong Java `@Aspect`, XML bật auto-proxy. |
| Spring `@Configuration` | `@EnableAspectJAutoProxy(proxyTargetClass = true, exposeProxy = true)` | Cùng hai ý nghĩa ở Java configuration. |
| Programmatic AOP | `ProxyFactory.setProxyTargetClass(true)` và `ProxyFactory.setExposeProxy(true)` | Tạo proxy thủ công qua `ProxyFactory`, khác với auto-proxy XML toàn context. |

Lưu ý `<aop:scoped-proxy proxy-target-class="..."/>` thuộc cơ chế scoped proxy cho bean theo scope; đừng đánh đồng nó với `expose-proxy` trên `<aop:config>`/`<aop:aspectj-autoproxy>`.

Trong ứng dụng Boot nhập XML bằng `@ImportResource("classpath:aop.xml")` nếu cần tích hợp cấu hình kiểu cũ vào Java configuration; sau đó kiểm tra các bean và auto-proxy settings có thể đã được Boot hay module khác đăng ký. Đây không phải lý do để lặp lại tag AOP ở nhiều nơi.

## 7. Kiểm tra cấu hình và chẩn đoán lỗi

| Triệu chứng | Kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `getBean(..., OrderService.class)` không lấy được bean, nhưng inject interface được | Bean là JDK dynamic proxy | Inject interface; chỉ ép class proxy khi có yêu cầu thực tế. |
| Method không có advice dù đã đặt pointcut | Proxy được tạo chưa, method không match, hoặc lời gọi đi qua `this` | Kiểm tra `AopUtils.isAopProxy`, expression, cách caller nhận bean từ context. |
| `AopContext.currentProxy()` ném `IllegalStateException` | `expose-proxy` chưa bật hoặc đang ngoài lời gọi qua proxy | Ưu tiên gọi sang bean khác; nếu phải dùng `AopContext`, bật đúng setting và kiểm tra thread/call path. |
| `ClassCastException` với `(OrderService) AopContext.currentProxy()` | Actual proxy là JDK interface proxy | Cast sang `OrderOperations` hoặc cân nhắc class proxy. |
| Chọn `proxy-target-class="true"` rồi Spring không tạo được proxy | Target class `final`, method `final`, hạn chế Java module/class loading hoặc conflict hạ tầng | Điều chỉnh khả năng proxy của target và kiểm tra bean definition, JVM/runtime. |
| Đã đặt `proxy-target-class="false"` nhưng vẫn thấy CGLIB | Target không có interface hoặc có một config khác ép `true` | Rà soát cùng `ApplicationContext`, `<tx:annotation-driven>`, `<aop:aspectj-autoproxy>` và Boot. |
| Viết XML nhưng Spring báo không biết `aop:` | Thiếu `xmlns:aop`, schemaLocation hoặc dependency AOP | Khai báo đúng Spring AOP XSD và thư viện tương thích. |
| Advice bị gọi hai lần | Đăng ký hai advisor/aspect trùng, hai bean aspect hoặc pointcut chồng nhau | Kiểm tra các config XML/Java cùng context, giữ một đường đăng ký rõ ràng. |

Có thể kiểm thử proxy bằng integration test sau khi context khởi động:

```java
Object bean = context.getBean("orderService");

assert org.springframework.aop.support.AopUtils.isAopProxy(bean);
assert org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean);
```

Hai `assert` trên thuộc **kịch bản XML `proxy-target-class="false"` của ví dụ** và cần bật assertions với `-ea` nếu chạy như Java code thông thường; trong test JUnit nên dùng `assertTrue(...)`. Cần test thêm dấu vết advice (counter hoặc log collector) vì chỉ kiểm tra lớp proxy chưa chứng minh biểu thức pointcut thực sự áp dụng.

### Checklist review khi thay đổi XML thật

1. Xác định `<aop:config>` hay `<aop:aspectj-autoproxy>` đang được sử dụng và đã đăng ký các bean aspect/advice chưa.
2. Liệt kê interface mà các consumer dùng để inject bean; chỉ bật class proxy khi có yêu cầu về class/method bên ngoài interface.
3. Xác định self-invocation có thật sự cần intercept hay không. Nếu có, ưu tiên tách bean; nếu dùng `AopContext`, kiểm tra `expose-proxy` và lời gọi qua proxy.
4. Kiểm tra ảnh hưởng của `<tx:annotation-driven>`, Spring Boot AOP, `@EnableAspectJAutoProxy` hay nhiều file XML lên auto-proxy creator hợp nhất.
5. Chạy test với bean lấy từ Spring context, thử nhánh thành công/lỗi, so sánh loại proxy, đếm advice và kiểm tra những caller inject qua concrete class.

## 8. Tài liệu Spring chính thức để tra cứu

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): cách chọn JDK/CGLIB, self-invocation và `AopContext`.
- [Spring Framework 6.2 — Schema-based AOP Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/schema.html): `<aop:config>`, khai báo aspect, pointcut và advice XML.
- [Spring AOP XSD](https://www.springframework.org/schema/aop/spring-aop.xsd): xác nhận `proxy-target-class` và `expose-proxy` đều được hỗ trợ trên `config` và `aspectj-autoproxy`.

**Điểm cần ghi nhớ:** `proxy-target-class` điều khiển **kiểu proxy**; `expose-proxy` điều khiển **khả năng lấy proxy hiện tại qua `AopContext`**. Cả hai đều hoạt động trong cơ chế proxy của Spring AOP và không tự giải quyết self-invocation qua `this`.
