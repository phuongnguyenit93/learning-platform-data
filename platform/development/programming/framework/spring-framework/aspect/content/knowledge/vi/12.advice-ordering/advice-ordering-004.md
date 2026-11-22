# Spring AOP — Chiều đi vào và chiều đi ra của chuỗi interceptor

## 1. Điều cốt lõi: advice tạo thành những lớp bao quanh method đích

Trong **Spring AOP dựa trên proxy**, khi một consumer gọi method trên bean được proxy, Spring kiểm tra những advisor có pointcut phù hợp rồi thực thi chuỗi các interceptor/advice. Những phần xử lý này không phải một danh sách chạy từ đầu tới cuối đúng một lượt. Chúng có thể tạo ra một cấu trúc **lồng nhau**:

- **Chiều đi vào (inbound, before proceeding):** bắt đầu từ interceptor/advice ưu tiên cao hơn ở lớp ngoài, tiến dần tới interceptor lớp trong và cuối cùng là method đích.
- **Chiều đi ra (outbound, after proceeding):** khi target trả về hoặc ném exception, luồng lần lượt đi ngược ra các interceptor lớp trong rồi lớp ngoài. Interceptor đứng ngoài **hoàn tất sau** interceptor đứng trong nếu nó cho luồng đi tiếp một cách bình thường.
- Với `@Around`, hai chiều được nhìn thấy rõ ở các dòng lệnh **trước** và **sau** `ProceedingJoinPoint.proceed()`.
- Với `@Before`, `@AfterReturning`, `@AfterThrowing` và `@After`, Spring áp dụng semantics riêng của từng loại advice trong interceptor chain, không phải đơn thuần chạy tất cả `@Before` rồi đảo ngược một danh sách tùy ý.

Một ví dụ trực quan:

```text
Caller
  |
  v
@Around A  — in
  |
  +--> @Around B  — in
           |
           +--> Target.work()
           |
           +<-- @Around B  — out
  |
  +<-- @Around A  — out
  |
  v
Caller nhận return value
```

**Quy tắc nhớ:** *Aspect ưu tiên cao hơn thường vào trước và ra sau.* Trong Spring, nếu hai aspects được cấu hình bằng `@Order(1)` và `@Order(2)`, aspect có giá trị `1` có precedence cao hơn. Khi cả hai dùng `@Around` và đều gọi `proceed()` đúng một lần, lời gọi chạy theo mô hình:

```text
A before
B before
target
B after
A after
```

Đây là mô hình nền tảng để hiểu Spring AOP advice ordering, logging, metrics, transactions, caching và những hành vi khi có exception.

**Giới hạn phạm vi:** bài này chỉ bàn về **Spring Aspect / Spring AOP proxy**, advisor chain và cách ứng dụng quan sát thứ tự. Không mô tả AspectJ bytecode weaving như một cơ chế thay thế và không trình bày AOP ở mức khái niệm chung.

## 2. Vì sao Spring AOP có interceptor chain?

Spring-managed bean có thể chịu nhiều chính sách cắt ngang. Ví dụ cùng một method service có:

- advice đo thời gian;
- advice logging;
- advice kiểm tra điều kiện trước lời gọi;
- transaction interceptor;
- advice quan sát return value hoặc exception.

Khi consumer gọi qua **Spring AOP proxy**, những advisor phù hợp được sắp thứ tự và tham gia một invocation. Với dạng interceptor bao quanh, phần bên ngoài có thể chạy code, chuyển điều khiển cho phần phía trong, rồi xử lý kết quả hoặc lỗi khi lời gọi trở lại.

```text
Consumer
  |
  v
Spring AOP proxy
  |
  v
Advisor/interceptor số 1  [ngoài nhất]
  |    enter
  v
Advisor/interceptor số 2
  |    enter
  v
Advisor/interceptor số 3  [trong nhất]
  |    enter
  v
Target method execution
  |    return hoặc throw
  ^
Advisor/interceptor số 3
  |    exit / finally / error
  ^
Advisor/interceptor số 2
  |    exit / finally / error
  ^
Advisor/interceptor số 1
  |    exit / finally / error
  ^
Caller
```

Trong Spring AOP, `MethodInvocation.proceed()` chuyển execution tới **phần còn lại của chain**, không nhất thiết nhảy trực tiếp đến target. Tương tự, `ProceedingJoinPoint.proceed()` trong một `@Around` cho các interceptor bên trong và target có cơ hội chạy. Khi invocation bên trong kết thúc, control quay trở lại advice gọi `proceed()`.

### 2.1. Spring AOP proxy chặn những lời gọi nào?

Chuỗi advice không có mặt trong mọi lời gọi Java:

1. Target là Spring-managed bean.
2. Hạ tầng Spring AOP được bật.
3. Aspect/advisor được đăng ký và pointcut khớp method.
4. Consumer sử dụng **proxy do Spring công bố**, thường qua dependency injection.
5. Method có thể bị loại proxy thực tế intercept: JDK proxy dựa trên public interface method; CGLIB dựa trên subclass/override với giới hạn riêng.

Khi trong target có `this.inner()`, lời gọi nội bộ **bypass Spring proxy**. Nó không khởi tạo một interceptor chain mới cho `inner()` mặc dù pointcut có thể match method ấy.

### 2.2. “Chain” không đồng nghĩa với “mọi advisor phải chạy”

Một interceptor bên ngoài có thể **không gọi `proceed()`** hoặc ném exception sớm. Khi đó các interceptor bên trong và target không được thực thi theo đường bình thường. Một outer `@Around` cũng có thể catch exception, trả fallback và làm caller thấy thành công. Vì vậy, sơ đồ đảo chiều đầy đủ chỉ áp dụng khi từng lớp thực sự cho execution đi tiếp.

## 3. `@Around` là cách quan sát hai chiều trực tiếp nhất

Hai advices độc lập:

```java
@Aspect
@Component
@Order(1)
public class OuterAspect {
    @Around("execution(* demo.chain.WorkService.work(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[outer] enter");
        Object result = pjp.proceed();
        System.out.println("[outer] exit");
        return result;
    }
}
```

```java
@Aspect
@Component
@Order(2)
public class InnerAspect {
    @Around("execution(* demo.chain.WorkService.work(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[inner] enter");
        Object result = pjp.proceed();
        System.out.println("[inner] exit");
        return result;
    }
}
```

Đây là **hai fragments**, cần các imports, target, Spring config và các file riêng. Nếu `work()` kết thúc bình thường, trace là:

```text
[outer] enter
[inner] enter
[target] work
[inner] exit
[outer] exit
```

Không phải:

```text
[outer] enter
[inner] enter
[target] work
[outer] exit
[inner] exit
```

Lý do nằm ở call stack: `OuterAspect.trace()` **chưa kết thúc** khi nó gọi `pjp.proceed()`; nó đang đợi tất cả thành phần phía trong, bao gồm `InnerAspect.trace()`, trả điều khiển lại. Chỉ sau khi inner advice return, outer mới in `exit`.

### 3.1. `proceed()` trả về điều gì?

Trong Spring AOP, `ProceedingJoinPoint.proceed()` trả `Object` đại diện cho kết quả của **phần còn lại của chain**, không bắt buộc là kết quả nguyên bản từ target nếu một interceptor bên trong cố ý biến đổi return.

```java
@Around("execution(* demo.chain.WorkService.work(..))")
public Object preserveResult(ProceedingJoinPoint pjp) throws Throwable {
    Object result = pjp.proceed();
    return result;
}
```

Nếu chỉ muốn log/measure, cần chuyển **đúng result** ra ngoài. Nếu method target trả `int`, `Object` có thể chứa `Integer` do boxing; trả `null` có thể phá contract. Nếu method target trả `String`, việc advice đổi `String` thành một type khác có thể gây lỗi runtime.

### 3.2. `try/finally` khác với code chỉ đặt sau `proceed()`

```java
@Around("execution(* demo.chain.WorkService.work(..))")
public Object traceFinally(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("[trace] enter");
    try {
        return pjp.proceed();
    } finally {
        System.out.println("[trace] finally");
    }
}
```

Với success hoặc exception, `finally` **đều** chạy khi stack unwinds, trừ những trường hợp như JVM/process dừng bất thường. Nếu đặt:

```java
Object result = pjp.proceed();
System.out.println("[trace] exit");
return result;
```

dòng `exit` chỉ chạy khi `proceed()` hoàn tất bình thường. Nếu `proceed()` ném exception, Java bỏ qua dòng sau đó trừ khi được catch hoặc có finally.

**Không viết `return` trong `finally`**: nó có thể ghi đè return value và nuốt exception của phần bên trong. Khi cleanup có thể ném lỗi, cũng cần thiết kế để lỗi cleanup không vô tình che exception nghiệp vụ ban đầu.

### 3.3. Khi inner around advice trả fallback

Giả sử `InnerAspect` catch một `IllegalStateException` và trả `"FALLBACK"`, còn `OuterAspect` chỉ đo kết quả sau `proceed()`:

```text
outer enter
inner enter
target throws
inner catches and returns FALLBACK
outer receives FALLBACK
outer exit
caller receives FALLBACK
```

Đối với outer interceptor, inner chain đã kết thúc **bình thường** do inner recover. Không thể nói “target đã throw nên mọi outer @AfterThrowing đều chắc chắn chạy”: còn phụ thuộc **vị trí** observer so với interceptor thực hiện recovery.

## 4. Precedence của các aspects trong Spring

Spring AOP tuân theo quy tắc precedence cho các advices áp dụng cùng một join point:

- Trong **các aspects khác nhau**, nếu không cấu hình precedence, thứ tự không được bảo đảm. Không đoán theo tên class, thứ tự bean scan, file source hoặc tên method.
- Gắn `@Order(n)` trên aspect class hoặc triển khai `org.springframework.core.Ordered` để đặt precedence.
- **Số order nhỏ hơn = precedence cao hơn**.
- Trên đường **đi vào**, aspect ưu tiên cao hơn chạy trước.
- Trên đường **đi ra**, aspect ưu tiên cao hơn chạy sau, vì nó là lớp ngoài.

Ví dụ:

```java
@Aspect
@Component
@Order(10)
public class AuditAspect {
    @Around("execution(* demo.chain.WorkService.work(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("audit-in");
        Object result = pjp.proceed();
        System.out.println("audit-out");
        return result;
    }
}
```

```java
@Aspect
@Component
@Order(20)
public class MetricsAspect {
    @Around("execution(* demo.chain.WorkService.work(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("metrics-in");
        Object result = pjp.proceed();
        System.out.println("metrics-out");
        return result;
    }
}
```

Đây là fragments minh họa. Với invocation thành công:

```text
audit-in
metrics-in
target
metrics-out
audit-out
```

**Thay `@Order(10)` thành `@Order(30)`** có thể đổi aspect trở thành lớp trong, nếu các advisor khác vẫn giữ thứ tự như cũ. Điều này thay đổi điểm quan sát thời gian, return value và exception.

### `@Order` không phải thứ tự khởi tạo bean

`@Order` ở đây là thứ tự ưu tiên trong advisor/aspect ordering, không có nghĩa constructor, `@PostConstruct`, scheduled tasks hoặc HTTP filters luôn chạy theo cùng thứ tự. Thứ tự vòng đời bean và thứ tự invocation của Spring AOP là hai vấn đề khác.

## 5. Các loại advice xuất hiện ở chiều nào?

Không phải loại advice nào cũng có cả “enter” và “exit” trong cùng một method:

| Loại Spring advice | Vị trí quan sát | Điều kiện chạy |
| --- | --- | --- |
| `@Around` | Có phần trước và sau `proceed()` nếu tác giả viết như vậy | Theo pointcut và cách advice điều khiển `proceed()` |
| `@Before` | Trước target method execution | Lời gọi khớp pointcut đi vào nhánh đó của chain |
| `@AfterReturning` | Đường ra **thành công** | Method execution liên quan hoàn tất bình thường và return binding phù hợp |
| `@AfterThrowing` | Đường ra **lỗi** | Execution liên quan kết thúc bất thường với exception type phù hợp |
| `@After` | Khi rời join point theo semantics **finally** | Chạy cả khi success và error trong chain tương ứng |

Như vậy, đường ra **không phải lúc nào cũng chỉ có một `@After`**. Nếu target success, các advice `@AfterReturning` có thể chạy; nếu target throws, các advice `@AfterThrowing` có thể chạy; `@After` áp dụng theo finally semantics.

### 5.1. `@Before` không có quyền thay return

Một `@Before` chạy trên đường vào. Nó có thể quan sát input arguments bằng `JoinPoint` và ném exception khi cần chặn lời gọi. Nhưng không có `ProceedingJoinPoint.proceed()` và không thể return một giá trị thay thế cho target. Nếu `@Before` ném exception, các thành phần bên trong có thể chưa chạy, còn các interceptor bao ngoài có thể bắt lỗi nếu được thiết kế như vậy.

### 5.2. `@AfterReturning` và `@AfterThrowing` loại trừ nhau đối với cùng một kết thúc

Với một execution kết thúc bình thường, `@AfterReturning` liên quan có thể nhận return value. Với một execution ném exception, `@AfterThrowing` liên quan có thể nhận exception. Không xem chúng như hai callback tuần tự luôn chạy cùng nhau cho một execution.

Nếu target tự catch exception và return success, observer ở proxy boundary thấy **normal return**, không phải target-thrown exception. Nếu một inner `@Around` recover trước khi outer advisor quan sát lỗi, outer advisor cũng có thể chỉ thấy normal return. Phân tích phải dựa vào vị trí chain.

### 5.3. `@After` là finally, không phải after-returning

Một `@After` được thiết kế để cleanup logic kiểu finally; nó chạy dù method được advice return hay throw. Không dùng `@After` để giả định target return success. Muốn giá trị trả về, dùng `@AfterReturning(returning="value")` hoặc `@Around`.

### 5.4. Tương tác khi nhiều advice nằm trong **cùng @Aspect class**

Tài liệu Spring Framework mô tả các loại advice của một `@Aspect` có thứ tự precedence riêng khi cùng áp dụng cho một join point: `@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`. Tuy nhiên, đây **không phải một danh sách thời điểm chạy tuyến tính**. Kể từ Spring Framework 5.2.7, `@After` tuân theo **finally semantics** và trong cùng aspect thực tế chạy **sau `@AfterReturning` hoặc `@AfterThrowing`**.

Bởi vậy, với một aspect chứa `@Before`, `@AfterReturning`, `@AfterThrowing` và `@After`, có thể quan sát:

```text
Thành công:
before
target returns
afterReturning
after (finally)

Thất bại:
before
target throws
afterThrowing
after (finally)
```

Ví dụ hoàn chỉnh ở mục 8 sử dụng Spring Framework 6.2.x để thể hiện đúng điều này. Với nhiều advice **cùng loại trong cùng aspect**, thứ tự tương đối không được suy từ thứ tự khai báo Java source do reflection không bảo đảm source declaration order. Khi thứ tự là yêu cầu bắt buộc, nên tách sang các aspects có order rõ hoặc hợp nhất logic.

## 6. Đọc thứ tự theo call stack thay vì chỉ theo tên annotation

Một invocation có ba lớp `@Around`:

```text
A.enter
  B.enter
    C.enter
      target()
    C.exit
  B.exit
A.exit
```

**Nếu target return:** đi ra từ C, rồi B, rồi A. Không có gì “chạy ngược” ở mức Java VM; chỉ là các stack frames return theo cơ chế hàm lồng nhau.

**Nếu target throw:**

```text
A.enter
  B.enter
    C.enter
      target throws
    C.catch/finally
  B.catch/finally
A.catch/finally
caller catches
```

Nếu các advice chỉ có lệnh `println("exit")` đặt **sau** `proceed()` mà không có catch/finally, các dòng exit đó **không xuất hiện** trên đường exception.

**Nếu B không gọi `proceed()`:**

```text
A.enter
  B.enter
  B.return cached-value
A.exit with cached-value
caller sees cached-value
```

C và target không chạy. Các `@Before` / `@After` bên trong B cũng không chạy vì execution không đi vào phạm vi của chúng.

**Nếu B gọi `proceed()` hai lần:** C và target có thể chạy hai lần, với side effects nhân đôi. Retry chỉ nên được thiết kế có chủ đích, kiểm soát idempotency, backoff và transaction scope.

### Phân biệt return của method với kết quả cuối caller nhìn thấy

Outer advice nhận kết quả của **chain bên trong**, có thể là:

- giá trị trả trực tiếp từ target;
- kết quả đã được một inner advice transform;
- cached value khi inner advice bỏ qua target;
- fallback khi inner advice catch exception.

Vì vậy muốn đo/log “target execution result nguyên thủy” và muốn đo/log “kết quả cuối của request qua AOP proxy” có thể là **hai vị trí đặt aspect khác nhau**.

## 7. Thứ tự tác động tới Spring transaction, cache và monitoring

### 7.1. Logging so với transaction boundary

Spring `@Transactional` thường được triển khai qua transaction advisor/interceptor, cũng tham gia vào pipeline method invocation. Một logging `@Around` bên **ngoài** transaction interceptor:

```text
logging enter
  transaction begin
    target method
  transaction commit / rollback
logging exit / catch
```

Nhưng nếu logging interceptor nằm **bên trong** transaction:

```text
transaction begin
  logging enter
    target method
  logging exit / catch
transaction commit / rollback
```

Hai cách đặt cho số liệu duration và khả năng thấy trạng thái transaction khác nhau. Trong thực tế, còn phụ thuộc transaction manager, advisor ordering, AOP config và các interceptor khác. **Không** suy đoán transaction đã mở hay chưa chỉ vì cùng tồn tại `@Around` và `@Transactional`.

### 7.2. Retry và transaction

Nếu retry advice đứng **ngoài** transaction advice, mỗi lần `proceed()` có thể tạo transaction mới (tùy propagation settings). Nếu transaction bao **ngoài** retry, nhiều attempts có thể cùng chịu một transaction boundary, với hậu quả khác về rollback-only và lock lifetime. Đây là một nguyên nhân cần kiểm soát order rõ ràng; không tùy tiện chỉnh `@Order` để “sửa” log order rồi vô tình đổi giao dịch.

### 7.3. Cache và timing

Một caching interceptor đứng ngoài metrics advice có thể trả cache hit **trước khi đi vào** phần metrics/target. Metrics bên trong khi đó không quan sát cache hit. Nếu metrics đứng ngoài cache thì quan sát cả cache hits, nhưng duration đo bao gồm việc kiểm tra cache. Chọn order theo mục tiêu quan sát.

### 7.4. Security và authorization

Nếu một kiểm tra quyền truy cập nằm trong một advice bên trong, một interceptor bên ngoài có thể return sớm mà không gọi `proceed()` khiến kiểm tra bên trong không chạy. Không thiết kế bảo mật ứng dụng chỉ dựa vào giả định “aspect chắc chắn chạy” nếu có thể bypass proxy hoặc outer advice short-circuit. Dùng các Spring Security boundaries thích hợp và kiểm chứng chain thực tế.

## 8. Ví dụ Maven Java 17 Spring Framework 6.2 — nhìn rõ cả hai chiều

Ví dụ đầy đủ, chạy trên **Spring Framework thuần** không cần Boot. Ta có:

- `OuterAspect`: `@Around`, `@Order(1)`, ngoài cùng.
- `InnerAspect`: `@Around`, `@Order(2)`, phía trong Outer.
- `EventAspect`: `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, `@Order(3)`. Bốn advice **khác loại** trong cùng một aspect để minh họa Spring 6.2 semantics.
- `WorkService`: `work("OK")` trả thành công, `work("FAIL")` ném `IllegalStateException`. `batch()` tự gọi `this.work("INNER")`, nên lời gọi nội bộ không tạo interceptor chain mới.

Pointcut của ba aspects **chỉ** match `WorkService.work(..)`, không match `batch()`. Tất cả print logs đều xác định được theo thứ tự và không phụ thuộc thứ tự giữa nhiều advice cùng loại.

### 8.1. Cấu trúc file

```text
spring-aop-chain-order/
├── pom.xml
└── src/main/java/demo/chain/
    ├── AppConfig.java
    ├── WorkPort.java
    ├── WorkService.java
    ├── OuterAspect.java
    ├── InnerAspect.java
    ├── EventAspect.java
    └── Main.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-chain-order</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.12</version>
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

Các dependency trên dùng cho Spring IoC, AOP proxy và parsing của `@AspectJ` pointcuts. Không cần bật AspectJ compile-time weaving hoặc load-time weaving để thực hiện ví dụ.

### 8.3. `AppConfig.java`

```java
package demo.chain;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@ComponentScan` đăng ký service và các aspects có `@Component`. `@EnableAspectJAutoProxy` bật Spring AOP auto-proxy. Với target triển khai interface và `proxyTargetClass=false`, bean được Spring công bố trong ví dụ sẽ là **JDK dynamic proxy**.

### 8.4. `WorkPort.java`

```java
package demo.chain;

public interface WorkPort {
    String work(String input);
    void batch();
}
```

Consumer cần inject/tra cứu `WorkPort`, không ép JDK proxy thành concrete `WorkService`.

### 8.5. `WorkService.java`

```java
package demo.chain;

import org.springframework.stereotype.Service;

@Service
public class WorkService implements WorkPort {
    @Override
    public String work(String input) {
        System.out.println("[target] work " + input);
        if ("FAIL".equals(input)) {
            throw new IllegalStateException("boom");
        }
        return "DONE-" + input;
    }

    @Override
    public void batch() {
        System.out.println("[target] batch");
        this.work("INNER"); // Không qua Spring AOP proxy.
    }
}
```

`work("OK")` in một dòng và trả `"DONE-OK"`. `work("FAIL")` in dòng target rồi ném exception có message `"boom"`. `batch()` tự gọi `work("INNER")` từ target nên lời gọi này bypass advice.

### 8.6. `OuterAspect.java` — lớp ngoài `@Order(1)`

```java
package demo.chain;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(1)
public class OuterAspect {
    @Around("execution(* demo.chain.WorkService.work(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[outer] in");
        try {
            Object result = pjp.proceed();
            System.out.println("[outer] out " + result);
            return result;
        } catch (Throwable ex) {
            System.out.println("[outer] caught " + ex.getMessage());
            throw ex;
        }
    }
}
```

Ở đường success, outer advice in `out` sau khi **toàn bộ** inner chain hoàn tất. Ở đường error, outer bắt exception do phần bên trong ném ra, in `caught` rồi **rethrow** để caller vẫn nhận lỗi. Nó không tự phục hồi.

### 8.7. `InnerAspect.java` — lớp trong `@Order(2)`

```java
package demo.chain;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(2)
public class InnerAspect {
    @Around("execution(* demo.chain.WorkService.work(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("[inner] in");
        try {
            Object result = pjp.proceed();
            System.out.println("[inner] out " + result);
            return result;
        } catch (Throwable ex) {
            System.out.println("[inner] caught " + ex.getMessage());
            throw ex;
        }
    }
}
```

Cả hai aspects gọi `proceed()` **chính xác một lần** trên mỗi invocation và truyền return/exception ra ngoài. Do `@Order(2)` thấp precedence hơn `@Order(1)`, `InnerAspect` đi vào sau nhưng đi ra trước Outer.

### 8.8. `EventAspect.java` — nhóm advice theo outcome

```java
package demo.chain;

import org.aspectj.lang.annotation.After;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(3)
public class EventAspect {
    @Before("execution(* demo.chain.WorkService.work(..))")
    public void beforeWork() {
        System.out.println("[event] before");
    }

    @AfterReturning(
        pointcut = "execution(* demo.chain.WorkService.work(..))",
        returning = "result"
    )
    public void returned(String result) {
        System.out.println("[event] afterReturning " + result);
    }

    @AfterThrowing(
        pointcut = "execution(* demo.chain.WorkService.work(..))",
        throwing = "ex"
    )
    public void failed(IllegalStateException ex) {
        System.out.println("[event] afterThrowing " + ex.getMessage());
    }

    @After("execution(* demo.chain.WorkService.work(..))")
    public void afterWork() {
        System.out.println("[event] after finally");
    }
}
```

Các advice type và mục đích:

- `@Before` in ở chiều vào, ngay trước phần execution tiếp theo.
- `@AfterReturning` nhận `String result` khi `work(..)` return bình thường.
- `@AfterThrowing` nhận `IllegalStateException` khi `work(..)` ném exception phù hợp.
- `@After` chạy theo finally semantics cho cả hai luồng, và với Spring 6.2 ở **cùng aspect này** thực tế được gọi **sau afterReturning/afterThrowing** tương ứng.

Lưu ý `@Order(3)` điều khiển precedence **so với các aspects khác**. Các lời gọi advice bên trong một class `@Aspect` còn theo quy tắc cho advice types của Spring, không phải thứ tự code trong file.

### 8.9. `Main.java`

```java
package demo.chain;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            WorkPort service = context.getBean(WorkPort.class);
            System.out.println("jdkProxy=" + AopUtils.isJdkDynamicProxy(service));

            System.out.println("[caller] begin OK");
            String result = service.work("OK");
            System.out.println("[caller] result " + result);

            System.out.println("[caller] begin FAIL");
            try {
                service.work("FAIL");
            } catch (IllegalStateException ex) {
                System.out.println("[caller] caught " + ex.getMessage());
            }

            System.out.println("[caller] begin batch");
            service.batch();
        }
    }
}
```

Biên dịch và chạy tại thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.chain.Main
```

**Stdout dự kiến từ `System.out` trong chương trình**, không bao gồm log build/framework nếu môi trường có:

```text
jdkProxy=true
[caller] begin OK
[outer] in
[inner] in
[event] before
[target] work OK
[event] afterReturning DONE-OK
[event] after finally
[inner] out DONE-OK
[outer] out DONE-OK
[caller] result DONE-OK
[caller] begin FAIL
[outer] in
[inner] in
[event] before
[target] work FAIL
[event] afterThrowing boom
[event] after finally
[inner] caught boom
[outer] caught boom
[caller] caught boom
[caller] begin batch
[target] batch
[target] work INNER
```

### 8.10. Giải thích thứ tự của nhánh OK

1. Main gọi `service.work("OK")` trên Spring-managed JDK proxy.
2. Aspect ưu tiên cao nhất `@Order(1)` bắt đầu: `[outer] in`.
3. Outer gọi `proceed()` nên đi vào `@Order(2)`: `[inner] in`.
4. Inner gọi `proceed()`, đi vào các advice thuộc `EventAspect @Order(3)`: `[event] before`.
5. Target `WorkService.work("OK")` in `[target] work OK` rồi return `"DONE-OK"`.
6. Advice `@AfterReturning` thấy normal completion: `afterReturning DONE-OK`.
7. Advice `@After` của cùng aspect chạy theo finally semantics sau đó: `after finally`.
8. Điều khiển quay về Inner, in `[inner] out DONE-OK` và return result.
9. Điều khiển quay về Outer, in `[outer] out DONE-OK` và return result.
10. Caller nhận `"DONE-OK"` và in `[caller] result DONE-OK`.

**Bài học:** chiều vào đi Outer → Inner → Event → target; chiều ra từ target → Event outcome/finally → Inner → Outer.

### 8.11. Giải thích thứ tự của nhánh FAIL

1. Outer in → Inner in → Event before → target như nhánh OK.
2. Target in `[target] work FAIL` rồi ném `IllegalStateException("boom")`.
3. `@AfterReturning` **không chạy**, vì method không return bình thường.
4. `@AfterThrowing` match `IllegalStateException` và in `afterThrowing boom`.
5. `@After` trong cùng aspect chạy finally và in `after finally`.
6. Exception tiếp tục đi ra Inner, khối catch của Inner in `caught boom` rồi rethrow.
7. Exception tiếp tục đi ra Outer, catch của Outer in `caught boom` rồi rethrow.
8. Caller catch và in `[caller] caught boom`.

Nếu Inner hoặc Outer **không catch** mà chỉ đặt code log sau `proceed()`, các dòng `out` tương ứng không xuất hiện. Nếu một advice ném exception mới, outer có thể nhìn thấy loại lỗi khác; nếu một advice catch rồi trả fallback, outer có thể thấy normal return.

### 8.12. Giải thích self-invocation trong batch

`batch()` không match pointcut của các aspects và được gọi qua proxy, nên Main in `[caller] begin batch` rồi target in `[target] batch`. Bên trong target, `this.work("INNER")` không đi lại qua proxy; chỉ in `[target] work INNER`.

Vì vậy không có dòng `[outer] in`, `[inner] in` hay `[event] before` cho INNER. **Đổi JDK proxy thành CGLIB không tự sửa self-invocation**.

## 9. Thử nghiệm thay đổi thứ tự và kết quả

### 9.1. Đổi order Outer và Inner

Nếu hoán đổi thành `OuterAspect @Order(2)` và `InnerAspect @Order(1)`, với hai `@Around` vẫn được đăng ký như ví dụ, thứ tự khi success sẽ có dạng:

```text
[inner] in
[outer] in
[event] before
[target] work OK
[event] afterReturning DONE-OK
[event] after finally
[outer] out DONE-OK
[inner] out DONE-OK
```

Không thay đổi logic target hoặc pointcut, nhưng thứ tự logging **ở cả hai chiều** được đảo tương ứng.

### 9.2. Bỏ `proceed()` của Inner

Giả sử Inner thay thành:

```java
@Around("execution(* demo.chain.WorkService.work(..))")
public Object cached(ProceedingJoinPoint pjp) {
    System.out.println("[inner] cached");
    return "CACHED";
}
```

Đây là **fragment thay thế**, không phải code để chạy cùng body Inner cũ. Outer gọi `proceed()` và đi vào Inner; Inner trả ngay `"CACHED"`, vì vậy Event/target không chạy:

```text
[outer] in
[inner] cached
[outer] out CACHED
```

Điều này hợp lệ về return type vì `work()` trả `String`, nhưng có thể sai nghiệp vụ nếu method thật cần side effects. Nếu áp dụng lên method trả `int`, return sai kiểu có thể gây lỗi runtime. Không dùng short circuit tùy tiện.

### 9.3. Inner bắt lỗi và phục hồi

Nếu Inner dùng:

```java
try {
    return pjp.proceed();
} catch (IllegalStateException ex) {
    System.out.println("[inner] recovered");
    return "FALLBACK";
}
```

đây là **fragment thay thế phần try/catch trong Inner**. Khi target ném lỗi, `EventAspect @AfterThrowing` (nằm phía trong Inner) có thể log exceptional exit, sau đó Inner catch và trả thành công. Outer lúc này **nhìn thấy success** và in dòng `out FALLBACK`; caller nhận `"FALLBACK"`. Không phải outer advisor nào cũng nhìn thấy exception khi inner đã xử lý nó.

### 9.4. `@After` cleanup thất bại

Nếu `@After` ném exception của riêng nó, exception ấy có thể thay đổi kết quả mà caller nhìn thấy và che lỗi trước đó. Đừng để logging/cleanup trong finally advice tự ý throw, trừ khi contract yêu cầu và có thiết kế exception rõ ràng. Một `@AfterThrowing` khác trong cùng aspect không phải “global catch” đáng tin cho exception do `@After` sinh ra.

### 9.5. Thêm hai `@Before` trong cùng aspect

Nếu `EventAspect` có hai method `@Before` khác nhau cùng match `work()`, không nên dựa vào thứ tự khai báo của hai method trong class Java để dự đoán dòng log. Spring không đảm bảo source declaration ordering qua reflection. Hãy gộp vào một advice theo trình tự mong muốn hoặc tách chúng thành hai aspects với `@Order` khác nhau.

## 10. Giới hạn khi suy luận order từ logs

### 10.1. Multiple proxy layers

Một Spring bean có thể tham gia nhiều cơ chế proxy/advisor. Có thể có nested proxies trong ứng dụng cấu hình đặc thù, bean scoped proxies, hoặc interceptor từ những module khác. Khi thấy log interleave không giống ví dụ, xác minh **đúng proxy reference**, advisor chain, scope và loại proxy. Không suy luận “@Order bị Spring bỏ qua” chỉ vì có interceptor khác đứng ngoài.

### 10.2. Thực thi bất đồng bộ và thread đổi

Nếu method trả một `CompletableFuture<T>`, reactive publisher hoặc được xử lý qua `@Async`, phần Spring AOP proxy có thể return một wrapper trước khi công việc async kết thúc. Một `@AfterReturning` tại method-execution boundary không tự đồng nghĩa “business đã hoàn thành”, và thứ tự logs across threads không phản ánh một single call stack giống ví dụ đồng bộ.

Nếu quan tâm hoàn thành future hoặc publisher, dùng completion/error operators và context propagation thích hợp. Không dùng mô hình linear synchronous chain để kết luận timeline của mọi async operation.

### 10.3. Transaction rollback dù outer advice trả fallback

Nếu transaction interceptor nằm phía trong Outer, method ném exception khiến nó đánh dấu rollback trước khi Outer catch và return `"FALLBACK"`, việc Outer trả success **không tự hoàn tác rollback**. Việc transaction có commit hay không phụ thuộc boundary, propagation, rules và status rollback-only.

### 10.4. Same-class advice precedence khác inter-aspect order

Trong một class `@Aspect`, có logic precedence theo advice types và đặc biệt `@After` theo finally semantics. Trong **các aspect classes khác nhau**, `@Order` định thứ tự giữa aspects. Đừng chuyển thẳng câu “@Before chạy trước @After” thành cách định thứ tự giữa hai aspects khi mỗi aspect có những loại advice khác nhau — phải xét **thứ tự lớp bao ngoài/lớp trong** trước.

### 10.5. Bean initialization không phải intercepted business invocation

Constructor, `@PostConstruct` và lifecycle callbacks thông thường diễn ra trong quá trình khởi tạo target trước khi ứng dụng dùng proxy hoàn chỉnh. Không đặt kỳ vọng `@Order` của aspects quy định thứ tự constructor hay advice chạy cho mọi callback startup.

## 11. Checklist chẩn đoán thứ tự Spring Aspect

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra / sửa |
| --- | --- | --- |
| Outer in trước Inner nhưng out sau Inner | Đúng nested interceptor semantics | Đọc `proceed()` như một nested call |
| Log chỉ có `in` khi target ném lỗi | Code `out` đặt sau `proceed()`, thiếu catch/finally | Dùng `try/finally` cho cleanup/logging cần chạy cả khi lỗi |
| `@AfterReturning` không chạy khi lỗi | Target/interceptor trong kết thúc bằng exception | Dùng `@AfterThrowing` cho lỗi hoặc `@After` cho finally |
| `@AfterThrowing` không chạy khi có fallback | Exception đã được inner advice xử lý trước khi observer nhìn thấy | Xem advisor order và actual outcome tại observer |
| `@After` chạy sau `@AfterReturning` trong cùng aspect | Spring 5.2.7+ finally semantics | Đây là hành vi đúng, không phải ngẫu nhiên |
| `@Order(1)` thấy duration dài hơn `@Order(2)` | Aspect outer đo cả inner chain | Chọn lớp metrics theo mục tiêu |
| Đổi `@Order` nhưng target logs không đổi | Target logic độc lập; thay đổi thứ tự các aspects | So sánh enter/exit/finally logs |
| Các aspects không có `@Order` chạy bất định | Spring không bảo đảm inter-aspect ordering | Đặt `@Order` nếu thứ tự là requirement |
| Hai `@Before` cùng aspect không có thứ tự mong muốn | Java reflection không bảo đảm thứ tự khai báo | Gộp logic hoặc tách aspect/classes |
| Target bị gọi hai lần | Một around advice gọi `proceed()` nhiều lần | Rà soát retry policy/idempotency |
| Target không được gọi | Outer advice short-circuit hoặc ném trước `proceed()` | Xem cache/security/validation chain |
| `this.inner()` không tạo logs advice | Self-invocation bypass proxy | Tách Spring bean nếu cần policy riêng |
| Order thay đổi khi có transactions | Có transaction/cache/security advisors khác | Kiểm tra actual advisor chain và precedence |
| Code outside Spring không có log aspect | Object không là Spring-managed proxy | Inject bean qua context |
| JDK proxy không advice một method | Method không được interface công bố | Dùng interface API phù hợp hoặc cấu hình proxy có cân nhắc |
| CGLIB không advice `final` method | Không override được | Đổi ranh giới method/bean hoặc dùng JDK interface proxy phù hợp |

**Quy trình xác minh:**

1. Xác nhận target và aspect là Spring beans; AOP hạ tầng đã bật.
2. Kiểm tra `AopUtils.isAopProxy(bean)`, `isJdkDynamicProxy(...)` hoặc `isCglibProxy(...)` trên reference thực tế.
3. Xác minh pointcut có match method và caller có đi qua proxy không.
4. Liệt kê aspects nào cùng áp dụng, có `@Order` hay `Ordered`, có advice cùng loại trong một aspect hay không.
5. Theo `proceed()` của từng around advice: lớp nào in `enter`, lớp nào catch/finally và return kết quả gì.
6. Thử cả case success và case exception; không chỉ nhìn một chiều của log.
7. Kiểm tra các interceptors hạ tầng như transaction, cache, security, async có làm thứ tự thay đổi không.
8. Dùng integration tests trên Spring context thật khi order ảnh hưởng nghiệp vụ hoặc transaction semantics.

## 12. Câu hỏi tự kiểm tra

**1. `@Order(1)` và `@Order(2)` cùng là `@Around` thì ai đi vào trước?** Aspect có số 1, vì precedence cao hơn. Nếu cả hai proceed và return bình thường, aspect số 1 đi ra sau aspect số 2.

**2. Lời gọi `pjp.proceed()` nghĩa là nhảy ngay vào target?** Không nhất thiết. Nó gọi phần còn lại của Spring AOP interceptor chain, có thể chứa các advices khác rồi mới đến target.

**3. Tại sao đặt `println("after")` sau `proceed()` lại không in khi target throws?** Vì exception bỏ qua các dòng sau `proceed()`, trừ khi được catch/finally.

**4. `@After` có tương đương `@AfterReturning` không?** Không. `@After` theo finally semantics, áp dụng cho cả normal và exceptional exit; `@AfterReturning` chỉ dành cho completion bình thường.

**5. Trong cùng Spring `@Aspect`, `@After` có thể chạy sau `@AfterThrowing` không?** Có. Spring Framework 5.2.7+ áp dụng finally semantics, và đây là behavior được tài liệu chính thức xác nhận.

**6. Nếu InnerAspect catch exception rồi return fallback, OuterAspect có bắt được original exception không?** Thông thường không, nếu fallback return bình thường trước khi đến Outer; Outer thấy kết quả của inner chain.

**7. Nếu around advice không gọi `proceed()`, các advices phía trong có chạy không?** Không theo đường invocation đó; target cũng có thể bị bỏ qua.

**8. `@Order` có kiểm soát Java constructor order không?** Không. Nó đặt precedence cho cơ chế ordering áp dụng, không là lịch khởi tạo toàn ứng dụng.

**9. Vì sao `this.work()` không chạy interceptor chain dù có pointcut?** Vì self-invocation gọi trực tiếp target, bỏ qua Spring AOP proxy.

**10. Muốn đo thời gian bao gồm transaction commit/rollback thì đặt metrics aspect ở đâu?** Thường cần metrics bên ngoài transaction interceptor, nhưng phải kiểm tra advisor ordering và transaction configuration thực tế.

## Tham khảo Spring Framework chính thức

- [Spring Framework — Declaring Advice: Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Advice Ordering, @After finally semantics](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework — AOP Advice API / MethodInterceptor.proceed()](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html)
- [Spring Framework — Proxying Mechanisms, JDK/CGLIB/self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — @AspectJ support, enabling Spring AOP](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html)
- [Spring Framework — Declarative transaction rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
