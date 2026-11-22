# Spring AOP XML: aop:before, aop:after-returning, aop:after-throwing, aop:after và aop:around

## 1. Mục tiêu và phạm vi

Spring Framework cung cấp **schema-based Spring AOP** cho những dự án muốn khai báo pointcut và advice **trong XML** thay vì ghi các annotation `@Aspect`, `@Before`, `@Around` trực tiếp vào class Java.

Năm phần tử advice quan trọng trong namespace `aop` là:

- `<aop:before>`: chạy trước method execution được pointcut chọn.
- `<aop:after-returning>`: chạy sau khi method execution **trả về bình thường**.
- `<aop:after-throwing>`: chạy khi method execution **kết thúc bằng exception phù hợp**.
- `<aop:after>`: dạng **after finally**, chạy khi method execution thoát ra theo cả hai cách.
- `<aop:around>`: bao quanh invocation, được quyền gọi `ProceedingJoinPoint.proceed()`, trả kết quả hoặc ném lại lỗi.

Tất cả là cơ chế **Spring Aspect trong Spring AOP**: chúng chặn những method executions trên **Spring-managed proxy**, không phải full AspectJ bytecode weaving.

Khác với cách dùng `@Aspect`:

```java
@Aspect
public class MyAspect {
    @Before("execution(* com.example.service.*.*(..))")
    public void before() { }
}
```

ở XML style, class giữ **các method Java thông thường**, không cần `@Aspect` hoặc `@Before`. Spring đọc cấu hình XML, tham chiếu Java object qua thuộc tính `ref`, rồi biến các method tương ứng thành advice:

```xml
<aop:aspect ref="auditAdvice">
    <aop:before pointcut-ref="businessOperation" method="before"/>
</aop:aspect>
```

Hai đoạn trên là **fragments**, không phải hai cấu hình cần kích hoạt cùng lúc. Bài đi sâu vào cách khai báo năm advice types, liên kết XML/Java, binding return/exception, ordering, kết quả chạy, lỗi cấu hình và các giới hạn của Spring proxy.

## 2. Hệ thống thành phần của XML AOP

Spring XML schema nối **target bean**, **advice POJO bean** và **pointcut** qua `<aop:config>`:

~~~xml
<bean id="paymentService" class="com.example.xmlaop.PaymentService"/>
<bean id="auditAdvice" class="com.example.xmlaop.AuditAdvice"/>
<aop:config>
    <aop:pointcut id="paymentOperation"
                  expression="execution(* com.example.xmlaop.PaymentService.pay(..))"/>
    <aop:aspect ref="auditAdvice">
        <aop:before method="before" pointcut-ref="paymentOperation"/>
    </aop:aspect>
</aop:config>
~~~

Đây là fragment: backing bean phải có method `before`. XML không đòi Java class chứa advice mang `@Aspect`. Trong `aop:config`, giữ thứ tự XSD **pointcut → advisor → aspect**; trong **cùng** `aop:aspect`, thứ tự khai báo advice có ảnh hưởng precedence (mục 8).

`pointcut-ref` chỉ chọn method execution được áp dụng; `method` là tên Java advice callback; `ref` trên `aop:aspect` là bean ID. Dùng `pointcut` inline thay vì `pointcut-ref` nếu biểu thức chỉ cần một lần. Các thẻ này không làm Spring AOP thoát giới hạn proxy.

## 3. `<aop:before>` — chạy trước invocation

Before advice chạy trước method execution được chọn. Nó phù hợp cho logging nhẹ, đếm số lượt gọi, validate những điều kiện cho phép chặn bằng exception, hoặc đặt metadata cần thiết trước khi đi vào target.

XML:

```xml
<aop:before
    pointcut-ref="paymentOperation"
    method="before"/>
```

Java backing method:

```java
public void before() {
    System.out.println("[BEFORE]");
}
```

Đây là fragments của Java advice bean và XML aspect. Spring gọi `before()` khi có match. Nếu `before()` ném exception, target có thể **không được chạy** vì execution bị chặn trước khi chuyển tiếp.

**Giới hạn:** `before()` không có `ProceedingJoinPoint` để quyết định gọi target bao nhiêu lần, và không thể return một replacement method result. Nếu chỉ cần chạy trước method, `before` đơn giản và ít nguy cơ hơn `around`.

Muốn biết tên method hoặc arguments, Spring XML advice có thể nhận `JoinPoint` làm tham số đầu:

```java
public void before(org.aspectj.lang.JoinPoint jp) {
    System.out.println("method=" + jp.getSignature().getName());
}
```

Đây là fragment. Không cache raw `JoinPoint` vào mutable singleton advice bean field để dùng chung giữa các requests; mỗi invocation có metadata riêng.

## 4. `<aop:after-returning>` — chỉ khi trả về bình thường

After-returning advice chạy khi method execution **không ném lỗi ra ngoài** và có normal return. Nó không chạy trên exception path tương ứng.

XML không bind return value:

```xml
<aop:after-returning
    pointcut-ref="paymentOperation"
    method="returned"/>
```

Java:

```java
public void returned() {
    System.out.println("[RETURNED]");
}
```

Nếu cần nhận kết quả trả về, thêm thuộc tính `returning`:

```xml
<aop:after-returning
    pointcut-ref="paymentOperation"
    method="returnedValue"
    returning="result"
    arg-names="result"/>
```

Java:

```java
public void returnedValue(Object result) {
    System.out.println("[RETURNED] result=" + result);
}
```

Các fragments này không được dùng đồng thời với cả hai method nếu không chủ đích muốn **hai return advices**. `returning="result"` là **binding identifier**, cần được ánh xạ tới Java advice parameter. `arg-names="result"` khai báo tên tường minh, tránh phụ thuộc vào compiler metadata hoặc parameter name inference. Kiểu của Java parameter có thể **giới hạn các return values được binding/matching**; dùng type phù hợp với target method.

### 4.1. Phân biệt return value và final outcome

Ví dụ service:

```java
public CompletableFuture<String> start() {
    return new CompletableFuture<>();
}
```

`<aop:after-returning>` có thể chạy ngay khi method đã trả về một **pending Future**. Nó **không chứng minh async task đã xong**; một Future còn có thể hoàn thành exceptionally về sau.

Tương tự, method trả `Mono` hoặc `Flux` có thể return **Publisher** trước subscription. `after-returning` quan sát việc Java method trả Publisher, không phải reactive `onComplete`/`onError`.

Nếu cần quan sát async completion, dùng `CompletionStage.whenComplete` hoặc Reactor operators phù hợp, không suy từ XML advice lifecycle.

### 4.2. Không thay replacement result bằng gán lại local

```java
public void returnedValue(Object result) {
    result = "different";  // Chỉ gán biến local.
}
```

Đây là anti-pattern fragment: caller **không tự nhận** chuỗi mới. Muốn thay kết quả được trả cho caller, nên dùng `around` và return replacement tương thích contract, hoặc thiết kế transformation trong service.

## 5. `<aop:after-throwing>` — chỉ khi invocation thoát bằng exception

After-throwing advice chạy khi method execution bị lỗi và thoát qua exception. Để bind exception, dùng thuộc tính `throwing`:

```xml
<aop:after-throwing
    pointcut-ref="paymentOperation"
    method="thrown"
    throwing="error"
    arg-names="error"/>
```

Backing method:

```java
public void thrown(Throwable error) {
    System.out.println("[THROW] "
            + error.getClass().getSimpleName());
}
```

`throwing="error"` map exception được quan sát vào Java parameter tên `error`. Nếu Java type là `IllegalArgumentException`, advice chỉ áp dụng cho exceptions phù hợp kiểu ấy theo Spring type restriction; `Throwable` rộng hơn.

**Không suy rằng `after-throwing` sẽ nuốt lỗi hoặc phục hồi kết quả.** Sau khi advice ghi log, exception thông thường vẫn được propagate. Muốn retry, fallback hoặc đổi exception, dùng `around` một cách có kiểm soát; không nên dùng after-throwing như một cách lặng lẽ thay đổi control flow.

### 5.1. Lỗi nào được quan sát?

| Kịch bản | `after-throwing` nhắm method? |
| --- | --- |
| Target method ném `IllegalStateException`, lỗi thoát ra | Có, nếu pointcut/type match |
| Target method trả bình thường | Không |
| Method trả pending `CompletableFuture`, Future fail sau return | Không tự chạy theo future completion |
| Method trả `Mono.error(ex)` bình thường, sau đó subscribe mới phát error | Không tự chạy chỉ vì reactive `onError` |
| Method ném lỗi ngay lúc xây dựng Publisher trước return | Có, nếu lỗi thoát từ invocation |
| Inner advice bắt một lỗi và return fallback, outer advice thấy normal return | Phụ thuộc vị trí advisor chain; lỗi có thể không vượt ranh giới được quan sát |

Trong project demo bên dưới, `PaymentService.pay("fail")` ném `IllegalStateException` **đồng bộ**, nên `<aop:after-throwing>` được kích hoạt như dự kiến.

## 6. `<aop:after>` — after finally, không chỉ sau thành công

`<aop:after>` có **finally semantics**:

```xml
<aop:after
    pointcut-ref="paymentOperation"
    method="afterFinally"/>
```

Java:

```java
public void afterFinally() {
    System.out.println("[FINALLY]");
}
```

Nó chạy khi method invocation thoát ra **normal return hoặc exception**, phù hợp để release resource/clear trạng thái có lifecycle cùng invocation.

**Không nhầm** `after` với `after-returning`:

| Tình huống | `after-returning` | `after-throwing` | `after` |
| --- | --- | --- | --- |
| Normal return | Có | Không | Có |
| Exception được propagate | Không | Có nếu type phù hợp | Có |
| Method không được gọi vì outer `around` short-circuit | Inner advice/target không chạy, nên thường không có các advice inner | Tương tự | Tương tự |
| Future trả ra bình thường nhưng fail về sau | Đã chạy ở mốc method return | Không chạy vì future late failure | Đã chạy ở mốc method return |

**Exception từ chính advice khác:** kết quả quan sát còn phụ thuộc precedence/chain; đừng coi mọi advice luôn áp trực tiếp target mà không có các advisors khác. Khi cleanup cần bảo toàn lỗi gốc, logic cleanup cũng cần được thiết kế để không vô tình ném lỗi mới che mất nguyên nhân ban đầu.

## 7. `<aop:around>` — điều khiển `proceed()`, return và throw

Around advice bao quanh method execution. Nó có thể ghi log trước/sau target, trả fallback, rút ngắn lời gọi hoặc retry theo policy. Đó là advice có quyền điều khiển mạnh nhất, nên chỉ dùng khi `before/after` không đủ.

XML:

```xml
<aop:around
    pointcut-ref="paymentOperation"
    method="around"/>
```

Java:

```java
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("[AROUND] enter");
    try {
        Object result = pjp.proceed();
        System.out.println("[AROUND] return");
        return result;
    } catch (Throwable error) {
        System.out.println("[AROUND] throw");
        throw error;
    }
}
```

Đây là method fragment dành cho backing aspect bean. Phương thức around advice **phải** nhận `ProceedingJoinPoint` làm **tham số đầu tiên**, thông thường return `Object` và khai báo `throws Throwable` vì `proceed()` có thể ném Throwable.

### 7.1. `proceed()` không phải bước tự động

`pjp.proceed()` chuyển tiếp invocation vào phần interceptor chain còn lại. Nếu không gọi `proceed()`, target có thể **không được thực thi** và caller chỉ nhận giá trị do around advice tự trả (nếu return type hợp lệ).

```java
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    if (cacheHit()) {
        return cachedValue();
    }
    return pjp.proceed();
}
```

Đây là fragment minh họa cache short-circuit, cần hai helpers có hợp đồng cache rõ ràng. Không dùng kiểu ngắt này cho phương thức có side effects nếu cache policy chưa chứng minh tương đương.

### 7.2. `proceed()` nhiều lần

Trong Spring AOP, around advice được phép gọi `proceed()` 0, 1 hoặc nhiều lần. Nhiều lần có thể dùng để retry, nhưng cũng có thể **lặp target và downstream advices, lặp side effects**:

```java
public Object retry(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (TemporaryFailure ex) {
        return pjp.proceed();
    }
}
```

Đây là fragment yêu cầu `TemporaryFailure` do ứng dụng định nghĩa. Retry phải có giới hạn, classification transient errors, idempotency/transaction boundaries và observability. Không gọi lại `proceed()` để “kiểm thử” target trên operation trừ tiền, gửi email hoặc publish event nếu operation không an toàn để lặp.

### 7.3. `proceed(Object[] arguments)`

Với Spring proxy-based AOP, overload `proceed(Object[])` cho phép chuyển tiếp arguments được thay thế; mảng phải phù hợp **số lượng và kiểu của underlying Java method arguments**:

```java
Object[] args = pjp.getArgs().clone();
args[0] = normalize((String) args[0]);
return pjp.proceed(args);
```

Đây là fragment, cần `normalize`. Không tự cho rằng chỉ gán lại Java parameter local trong advice làm caller/target nhận argument mới; phải truyền đúng `args` tới `proceed(args)`.

### 7.4. Timing an toàn trong around

```java
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        metrics.record(elapsed);
    }
}
```

Đây là fragment. `started` là **local variable**, tránh race khi backing advice bean dùng singleton scope. Nếu target trả Future/Publisher, duration trên chỉ đo **Java method invocation**, không tự đo eventual async/reactive completion.

## 8. Thứ tự advice trong **cùng** XML `<aop:aspect>`

Đây là điểm khác biệt dễ sai nhất khi chuyển giữa XML và `@AspectJ` annotation-style.

**Spring XML schema AOP có quy tắc: khi nhiều advice elements trong cùng `<aop:aspect>` cùng match join point, precedence từ cao đến thấp được xác định bởi **thứ tự khai báo các phần tử advice trong XML**.**

Ví dụ:

```xml
<aop:aspect ref="auditAdvice">
    <!-- Precedence cao nhất trong aspect XML này -->
    <aop:around method="around" pointcut-ref="paymentOperation"/>
    <aop:before method="before" pointcut-ref="paymentOperation"/>
    <aop:after method="afterFinally" pointcut-ref="paymentOperation"/>
    <aop:after-returning method="returnedValue"
        returning="result" arg-names="result"
        pointcut-ref="paymentOperation"/>
    <aop:after-throwing method="thrown"
        throwing="error" arg-names="error"
        pointcut-ref="paymentOperation"/>
</aop:aspect>
```

Với sequence XML trên, `around` là outer advice; `before` chạy trên đường vào; `after` có precedence cao hơn các advice return/throw được đặt sau nó, nên theo mô hình nested finally nó chạy **sau** `after-returning` hoặc `after-throwing` trên đường ra.

Đối chiếu một normal return:

```text
[AROUND] enter
[BEFORE]
[TARGET] execute
[RETURNED] result=...
[FINALLY]
[AROUND] return
```

Với exception:

```text
[AROUND] enter
[BEFORE]
[TARGET] throws exception
[THROW] IllegalStateException
[FINALLY]
[AROUND] throw
```

Nếu đổi thứ tự các XML advice elements, precedence/relative execution có thể thay đổi. **Đừng hoán đổi order tùy ý chỉ để nhóm các tag theo alphabet**, nhất là khi around/after/throwing được dùng cùng lúc.

### 8.1. Không đem quy tắc XML áp dụng cho annotation-style `@Aspect`

Trong một Java class `@Aspect` có hai `@Before` advice cùng match, Spring **không bảo đảm** thứ tự dựa trên vị trí khai báo hai Java methods. Java reflection không cung cấp source declaration order như một contract. Spring annotation-style có quy tắc ordering theo loại advice và `@After` finally semantics riêng.

**Riêng XML `<aop:aspect>`**, Spring docs quy định rõ declaration order của **các advice elements** dùng để quyết định precedence trong cùng aspect. Đây là ngoại lệ chủ ý, không phải mâu thuẫn.

### 8.2. Giữa **nhiều aspects** thì dùng `order`

```xml
<aop:aspect ref="securityAdvice" order="1">
    <aop:before method="check" pointcut-ref="paymentOperation"/>
</aop:aspect>

<aop:aspect ref="auditAdvice" order="10">
    <aop:around method="around" pointcut-ref="paymentOperation"/>
</aop:aspect>
```

Đây là fragment; các bean `securityAdvice`/`auditAdvice` và pointcut phải tồn tại. Aspect với **giá trị order nhỏ hơn** có precedence **cao hơn**. High-precedence advice chạy trước trên đường vào, sau trên đường ra.

Có thể dùng `@Order` trên backing bean hoặc implement `Ordered` theo cơ chế Spring, nhưng không nên trộn các cơ chế với giá trị mâu thuẫn rồi tự đoán thứ tự cuối. `<aop:advisor>` cũng có thuộc tính `order`, ảnh hưởng chain khi kết hợp transaction/caching/security advisors.

**Khuyến nghị:** Nếu một `<aop:aspect>` có quá nhiều advice cùng join point mà order khó hiểu, cân nhắc gom logic vào một method advice rõ ràng hoặc tách thành nhiều aspects có `order` tường minh.

## 9. Binding parameters trong XML: `returning`, `throwing` và `arg-names`

Ba khái niệm có vai trò khác nhau:

| XML attribute | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `method` | `method="returnedValue"` | Tên Java method trên backing advice bean |
| `pointcut` | `pointcut="execution(...)"` | Expression chọn method execution |
| `pointcut-ref` | `pointcut-ref="paymentOperation"` | Dùng named pointcut đã khai báo |
| `returning` | `returning="result"` | Bind **normal return value** vào parameter |
| `throwing` | `throwing="error"` | Bind **thrown exception** vào parameter |
| `arg-names` | `arg-names="result"` | Ánh xạ formal parameter names tường minh |
| `ref` ở `<aop:aspect>` | `ref="auditAdvice"` | Bean chứa Java advice methods |
| `order` ở `<aop:aspect>` | `order="10"` | Precedence giữa aspects |

### 9.1. Bind Java method argument

XML:

```xml
<aop:before
    method="beforeWithArgument"
    pointcut="execution(* com.example.xmlaop.PaymentService.pay(..)) and args(reference)"
    arg-names="reference"/>
```

Java:

```java
public void beforeWithArgument(String reference) {
    System.out.println("reference=" + reference);
}
```

Hai fragments dùng `args(reference)` như một **binding identifier**; nó không phải tên tham số “tự động đọc” từ target method. `args` match **argument position và type** phù hợp, rồi chuyển giá trị vào Java advice method.

Nếu Java advice có leading `JoinPoint`, Spring có quy tắc đặc biệt cho phép bỏ tên leading join point khỏi `arg-names`. Với around advice, leading `ProceedingJoinPoint` cũng được xử lý tương ứng. Tránh dùng overload advice Java methods cùng tên khiến matching/binding khó dự đoán.

### 9.2. Return type/exception type làm điều kiện binding

`returnedValue(String result)` chỉ hợp với những return values Spring có thể bind vào `String`. `thrown(IllegalStateException error)` quan sát loại lỗi tương ứng; `thrown(Throwable error)` rộng hơn. Không dùng type restriction vô tình loại bỏ các exceptions/results cần logging.

`returning` và `throwing` **không phải** cách thay thế kết quả/exception bằng gán lại advice parameter. Nếu thật sự cần transform, hãy dùng around với behavior contract rõ ràng.

### 9.3. Tên parameter và compiler

`arg-names` trong XML tương đương ý định của `argNames` trong annotation-style, cho phép tránh phụ thuộc vào Java `-parameters` và cơ chế suy luận tên parameter. Dù vậy, Java parameter **thứ tự, số lượng và type** vẫn phải khớp. Khi tăng/giảm parameters, cần cập nhật cả XML declaration và Java method signature rồi kiểm thử context startup.

## 10. Ví dụ chạy được: Maven + Java 17 + Spring Framework XML AOP

Project này minh họa **đủ cả năm loại advice trong cùng `<aop:aspect>`**, thứ tự XML được chủ động thiết kế để có stdout xác định.

Bộ phiên bản cố định: Java 17+, Spring Framework 6.1.14, AspectJ Weaver 1.9.22.1, Maven. Đây là phiên bản minh họa, **không khẳng định phiên bản mới nhất**. Không dùng Spring Boot hoặc AspectJ weaving để giữ trọng tâm vào schema-based Spring AOP.

### 10.1. Cấu trúc thư mục

```text
spring-xml-five-advices/
├── pom.xml
└── src/main/
    ├── java/com/example/xmlaop/
    │   ├── PaymentService.java
    │   ├── AuditAdvice.java
    │   └── DemoApp.java
    └── resources/
        └── applicationContext.xml
```

### 10.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-xml-five-advices</artifactId>
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

Spring `spring-context` kéo `spring-aop` cùng nhóm dependencies liên quan qua dependency tree cho ví dụ; `aspectjweaver` hỗ trợ pointcut expression parser. Không cần thêm `@Aspect` trên Java advice POJO.

### 10.3. `src/main/java/com/example/xmlaop/PaymentService.java`

```java
package com.example.xmlaop;

public class PaymentService {
    public String pay(String mode) {
        System.out.println("[TARGET] pay " + mode);

        if ("fail".equals(mode)) {
            throw new IllegalStateException("simulated");
        }
        return "paid:" + mode;
    }

    public String health() {
        System.out.println("[TARGET] health");
        return "UP";
    }
}
```

`pay("ok")` trả bình thường; `pay("fail")` ném đồng bộ; `health()` dùng để chứng minh **pointcut chỉ nhắm pay()**, không chặn mọi method trên bean.

### 10.4. `src/main/java/com/example/xmlaop/AuditAdvice.java`

```java
package com.example.xmlaop;

import org.aspectj.lang.ProceedingJoinPoint;

public class AuditAdvice {

    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[AROUND] enter");
        try {
            Object result = pjp.proceed();
            System.out.println("[AROUND] normal exit");
            return result;
        } catch (Throwable ex) {
            System.out.println("[AROUND] exceptional exit");
            throw ex;
        }
    }

    public void before() {
        System.out.println("[BEFORE]");
    }

    public void afterFinally() {
        System.out.println("[FINALLY]");
    }

    public void returnedValue(Object result) {
        System.out.println("[RETURNED] result=" + result);
    }

    public void thrown(Throwable error) {
        System.out.println("[THROW] "
                + error.getClass().getSimpleName());
    }
}
```

Đây là **Java POJO thuần**. Không có `@Aspect` hoặc `@Around` annotations. Spring XML sẽ chọn từng method bằng `method` attribute.

`around(ProceedingJoinPoint)` dùng local variable để giữ result/exception; `afterFinally()` không có tham số. `returnedValue(Object result)` và `thrown(Throwable error)` nhận binding thông qua XML `returning`/`throwing`. Có cả success và exception paths nhưng **không nuốt exception**.

### 10.5. `src/main/resources/applicationContext.xml`

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

    <!-- Target được Spring quản lý -->
    <bean id="paymentService"
          class="com.example.xmlaop.PaymentService"/>

    <!-- Backing advice POJO: không cần @Aspect -->
    <bean id="auditAdvice"
          class="com.example.xmlaop.AuditAdvice"/>

    <aop:config proxy-target-class="true">
        <!-- Pointcut hẹp, chỉ chọn pay(String) -->
        <aop:pointcut
            id="paymentOperation"
            expression="execution(public * com.example.xmlaop.PaymentService.pay(..))"/>

        <aop:aspect id="paymentAudit" ref="auditAdvice">
            <!-- Precedence cao xuống thấp, XML declaration order -->
            <aop:around
                method="around"
                pointcut-ref="paymentOperation"/>
            <aop:before
                method="before"
                pointcut-ref="paymentOperation"/>
            <aop:after
                method="afterFinally"
                pointcut-ref="paymentOperation"/>
            <aop:after-returning
                method="returnedValue"
                returning="result"
                arg-names="result"
                pointcut-ref="paymentOperation"/>
            <aop:after-throwing
                method="thrown"
                throwing="error"
                arg-names="error"
                pointcut-ref="paymentOperation"/>
        </aop:aspect>
    </aop:config>
</beans>
```

**Lý do chọn XML order này:** `aop:around` ở ngoài cùng; `aop:before` chạy trước target; `aop:after` có precedence cao hơn các after-returning/after-throwing elements được khai báo sau nó nên cleanup/finally theo đường unwind diễn ra sau chúng. Vị trí các child XML tags **không phải thứ tự thời gian giản đơn**, vì có chiều đi vào và đi ra.

`proxy-target-class="true"` chọn class-based CGLIB proxy, giúp `PaymentService` không implement interface vẫn được lấy bằng concrete class từ context. Dù proxy style khác, logic Java advice bean vẫn là POJO.

### 10.6. `src/main/java/com/example/xmlaop/DemoApp.java`

```java
package com.example.xmlaop;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class DemoApp {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                 new ClassPathXmlApplicationContext("applicationContext.xml")) {

            PaymentService service =
                    context.getBean("paymentService", PaymentService.class);

            System.out.println("isAopProxy="
                    + AopUtils.isAopProxy(service));

            System.out.println("[CALLER] success");
            String success = service.pay("ok");
            System.out.println("[CALLER] result=" + success);

            System.out.println("[CALLER] failure");
            try {
                service.pay("fail");
            } catch (IllegalStateException ex) {
                System.out.println("[CALLER] caught="
                        + ex.getMessage());
            }

            System.out.println("[CALLER] health");
            System.out.println("[CALLER] result=" + service.health());
        }
    }
}
```

Caller lấy Spring bean từ XML context nên lời gọi `pay` đi **qua Spring proxy**, khác với `new PaymentService().pay(...)` ngoài container.

### 10.7. Chạy Maven

Từ thư mục root có `pom.xml` và JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.xmlaop.DemoApp
```

Các dòng do chương trình tự in, theo source và XML declarations của demo, **không tính log Maven/Spring bổ sung tùy môi trường**:

```text
isAopProxy=true
[CALLER] success
[AROUND] enter
[BEFORE]
[TARGET] pay ok
[RETURNED] result=paid:ok
[FINALLY]
[AROUND] normal exit
[CALLER] result=paid:ok
[CALLER] failure
[AROUND] enter
[BEFORE]
[TARGET] pay fail
[THROW] IllegalStateException
[FINALLY]
[AROUND] exceptional exit
[CALLER] caught=simulated
[CALLER] health
[TARGET] health
[CALLER] result=UP
```

### 10.8. Vì sao có thứ tự này?

**Success path:**

1. Spring AOP proxy chọn `paymentOperation` cho `pay("ok")`.
2. XML around element có precedence cao nhất nên in `[AROUND] enter`.
3. `pjp.proceed()` chuyển tiếp tới before element, in `[BEFORE]`.
4. Target chạy, in `[TARGET] pay ok` và trả chuỗi.
5. Return advice nhận `result="paid:ok"`, in `[RETURNED]`.
6. Finally advice in `[FINALLY]`.
7. Around lấy kết quả từ `proceed()`, in `normal exit` và return đúng chuỗi cho caller.

**Failure path:**

1. Around in `enter`; before in `[BEFORE]`; target in `[TARGET] pay fail`.
2. Target ném `IllegalStateException`, không có normal return nên `after-returning` không chạy.
3. After-throwing bind `Throwable error` và in tên loại exception.
4. After-finally vẫn chạy.
5. Lỗi propagate đến catch của outer around, được log rồi ném lại cho caller.
6. Caller catch và in message `simulated`.

**Unmatched method:** `health()` không khớp `execution(...pay(..))` nên không có bất kỳ advice log nào khi `health()` chạy.

Stdout là **kết quả dự kiến từ code đã rà soát tĩnh**. Khi chạy project trên máy thật, nên xác minh bằng Maven/integration test đúng Spring version và config; không dùng kết quả này làm cam kết cho application có thêm advisors hoặc order khác.

## 11. Những lưu ý khi XML advice cùng xuất hiện với infrastructure advisors

Trong một ứng dụng có transaction, cache, security hoặc XML/`@Aspect` advice khác, **vị trí của advisor trong chain** ảnh hưởng kết quả được quan sát. Ví dụ logging advisor bên trong transaction interceptor có thể ghi success trước khi transaction commit ngoài cùng; `after-returning` chưa chứng minh commit thành công.

Nếu outer `around` bắt lỗi rồi trả fallback, outer after-returning có thể thấy normal return; nếu `proceed()` lặp nhiều lần, downstream target/advice cũng có thể chạy nhiều lần. Vì vậy cần xác định `order`, phạm vi transaction, retry idempotency và assert event trace của context thật. Bài **“Kết hợp XML với Java configuration…”** xét riêng nguy cơ đăng ký trùng advisor và bean.

## 12. Spring proxy boundaries vẫn tồn tại dù dùng XML

Dù dùng XML, Spring AOP vẫn xử lý **method execution của Spring-managed bean qua proxy**. `this.method()` trong target và `new Target()` ngoài container không kích hoạt một lần proxy interception mới. Với JDK proxy, caller dùng interface; với class proxy, final/private targets không thể override; Future/Publisher completion xảy ra ngoài thời điểm Java method trả về.

Những giới hạn này ảnh hưởng tất cả năm advice types. Bài **“proxy-target-class và expose-proxy trong cấu hình XML”** đưa thí nghiệm đo loại proxy, self-invocation và `AopContext.currentProxy()` cụ thể.

## 13. Khi nào XML AOP thích hợp?

XML configuration có giá trị trong các dự án:

- Dùng XML bean definitions và muốn gắn advice vào POJOs **không sửa class Java**.
- Có các aspects legacy vốn giữ methods bình thường.
- Muốn bật/tắt pointcuts/advice bindings theo configuration đang quản lý có kiểm soát.
- Đang migration giữa schema-based XML AOP và `@AspectJ` annotations.

Ưu điểm gồm tách configuration khỏi Java source và không cần advice bean mang AspectJ annotations. Đổi lại, Java method names trong XML strings **không được Java compiler type-check trực tiếp**; refactor tên method/package phải cập nhật XML và integration tests. Càng nhiều advices cùng join point thì declaration order càng khó kiểm soát.

### So sánh với annotation-style

| Ý định | Spring XML AOP | Spring `@AspectJ` style |
| --- | --- | --- |
| Aspect source | Backing Java POJO + `<aop:aspect ref=...>` | Java `@Aspect` class được Spring quản lý |
| Before | `<aop:before>` | `@Before` |
| After returning | `<aop:after-returning>` | `@AfterReturning` |
| After throwing | `<aop:after-throwing>` | `@AfterThrowing` |
| After finally | `<aop:after>` | `@After` |
| Around | `<aop:around>` | `@Around` |
| Named pointcut | `<aop:pointcut id=...>` | `@Pointcut` |
| Explicit parameter names | XML `arg-names` | Annotation `argNames` |
| Precedence between aspects | XML `order` / Spring ordering | `@Order` / `Ordered` |
| Within same aspect | **XML advice element order** | Precedence by advice type; two same-type advice methods have undefined order |
| Join points | Spring proxy method execution | Spring proxy method execution |

**Không phải** cứ chuyển sang `@Aspect` là Spring AOP có thể chặn private methods/constructor/field get-set; proxy boundary vẫn giữ nguyên.

## 14. Lỗi thường gặp khi dùng năm XML advice tags

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Context load lỗi vì không biết namespace `aop` | Thiếu `xmlns:aop`/schemaLocation `spring-aop.xsd` | Khai báo đúng namespace và XSD |
| XML parsing lỗi ở `&&` | Dấu `&` chưa escape trong attribute | Dùng `&amp;&amp;` hoặc `and` phù hợp |
| `ref="auditAdvice"` không resolve | Chưa đăng ký backing advice bean hoặc sai ID | Định nghĩa `<bean id="auditAdvice" .../>` |
| `method="returnedValue"` không được tìm thấy | Sai Java method name/signature | Đồng bộ XML với backing bean Java |
| `pointcut-ref` không resolve | Sai/missing named pointcut ID | Khai báo đúng `<aop:pointcut id=...>` |
| `after-returning` không chạy trên exception | Chỉ áp dụng normal return | Dùng `after-throwing` cho exception |
| `after-throwing` không chạy dù Future lỗi muộn | Spring AOP nhìn method normal return | Quan sát Future completion separately |
| `after` chạy cả thành công và lỗi | Đây là finally semantics | Dùng đúng theo mục đích cleanup |
| `around` khiến target không chạy | Quên `pjp.proceed()` hoặc short-circuit | Gọi `proceed()` khi muốn chuyển tiếp |
| Caller không nhận kết quả target | Around quên return result | `return pjp.proceed()` hoặc replacement hợp lệ |
| `returning` không bind đúng | Sai `arg-names`/type, method result type khác | Đồng bộ identifiers và Java signature |
| `throwing` không bind | Parameter không đúng tên/type | Đồng bộ XML `throwing`/`arg-names` và Java method |
| Thứ tự logs khác từ XML tag order | Đọc precedence như thứ tự thời gian đơn chiều | Phân biệt đường vào/ra interceptor chain |
| Hai aspects chạy thứ tự không rõ | Không có `order`/Spring precedence | Khai báo distinct `order` values |
| `health()` bị advice dù chỉ muốn `pay()` | Pointcut quá rộng | Dùng `execution` hẹp, negative tests |
| XML aspect không chạy cho bean tự `new` | Caller bypass Spring proxy | Lấy bean từ context |
| Method self-invocation không có advice | `this.method()` bypass proxy | Refactor giao tiếp giữa Spring beans |
| Không lấy được concrete class type | JDK dynamic proxy chỉ expose interface | Inject interface hoặc đổi proxy strategy phù hợp |
| CGLIB không advice `final` method | Không override được method | Điều chỉnh contract/proxy strategy |
| Trộn XML AOP với auto-proxy creator cấu hình thủ công | Hạ tầng proxy conflict | Chọn một cách cấu hình nhất quán |
| XML references cũ sau refactor | Compiler không kiểm tra string XML | Chạy context-start/integration tests trong CI |

## 15. Checklist review và test

Trước khi đưa XML AOP advice vào module, kiểm tra:

1. XML `beans`, `aop` namespaces và schema locations hợp lệ.
2. `<aop:config>` có đúng pointcuts/advisors/aspects và đúng XSD declaration order.
3. Target và backing advice Java objects đều là Spring beans trong đúng context.
4. Pointcut expression chọn đúng class/method, tránh vô tình match toàn bộ service layer.
5. `method` trỏ đúng tên/signature trên backing advice bean.
6. `pointcut-ref` trỏ đúng named pointcut ID, không nhầm Java method name.
7. `returning`/`throwing`/`arg-names` ánh xạ đúng Java formal parameters.
8. `around` có `ProceedingJoinPoint` đầu tiên và return value/exception contract đúng.
9. Thứ tự **XML advice declarations trong một `<aop:aspect>`** có chủ ý.
10. `order` giữa nhiều aspects/advisors được khai báo nếu có dependency thực tế.
11. Integration test cho normal return, exception, method không match và target không được advice khi bypass proxy.
12. Nếu có transaction/cache/security, test chain/commit behavior trong context thật.
13. Các metrics dùng local start/actor state, không giữ `JoinPoint` vào fields singleton.
14. Không log user tokens/PII hoặc toàn bộ result object không được phép.
15. Không dùng after-returning để suy Future/Publisher đã complete.
16. Khi XML/Java refactor, integration test phải **load XML resource từ classpath** để phát hiện sai configuration strings.

### Nguồn chính thức

- Spring Framework — **Schema-based AOP Support**, đầy đủ ví dụ năm `aop` advice tags, parameter binding và ordering: https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Spring Framework — **Declaring Advice** và precedence trong `@AspectJ` style: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — **AOP Concepts**: https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html
- Spring Framework — **XML Schema-based Configuration**: https://docs.spring.io/spring-framework/reference/core/appendix/xsd-schemas.html

**Kết luận:** Spring XML AOP dùng `<aop:before>`, `<aop:after-returning>`, `<aop:after-throwing>`, `<aop:after>` và `<aop:around>` để liên kết **Java advice methods thông thường** với **Spring proxy method-execution join points**. Năm loại giữ đúng semantics của Spring `@AspectJ`, nhưng có một quy tắc cần nhớ: **trong cùng `<aop:aspect>`, thứ tự khai báo advice elements quyết định precedence**. Thiết kế đúng `returning`/`throwing` binding, return/throw contract và proxy boundary giúp cấu hình XML chạy đúng, an toàn và có thể kiểm chứng bằng integration tests.
