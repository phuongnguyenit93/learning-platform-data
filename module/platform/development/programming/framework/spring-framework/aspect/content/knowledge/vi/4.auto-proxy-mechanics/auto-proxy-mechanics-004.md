# Chuỗi interceptor khi một phương thức được gọi qua Spring AOP proxy

## 1. Kết quả cần nắm

Khi một client gọi phương thức **qua Spring AOP proxy**, Spring có thể thực hiện nhiều interceptor/advice trước khi chuyển tới phương thức thực trên target. Mỗi interceptor trong chuỗi quyết định **có gọi tiếp hay không**, đồng thời có cơ hội quan sát hoặc xử lý kết quả/exception khi lời gọi phía trong quay trở ra.

Mô hình tư duy cốt lõi:

```text
Client
  |
  v
Spring AOP proxy
  |
  v
Interceptor A: trước
  |
  +--> Interceptor B: trước
         |
         +--> Interceptor C: trước
                |
                +--> Target.method()
                |
         <-- Interceptor C: sau / xử lý lỗi
  <-- Interceptor B: sau / xử lý lỗi
<-- Interceptor A: sau / xử lý lỗi
  |
  v
Client nhận kết quả hoặc exception
```

Hình dạng gọi lồng nhau tương đương:

```java
return interceptorA.invoke(() ->
        interceptorB.invoke(() ->
                interceptorC.invoke(() ->
                        target.method())));
```

Đoạn này **chỉ là mã giả**, không phải API Java của Spring. Điều cần ghi nhớ là Spring xử lý chuỗi theo cơ chế **lồng lời gọi**: vào từ ngoài đến trong, rồi trở ra từ trong đến ngoài. Do đó interceptor có ưu tiên cao thường chạy logic “trước” sớm hơn và logic “sau” muộn hơn.

**Giới hạn của bài:** giải thích chuỗi interceptor trong cơ chế auto-proxy của **Spring AOP** đối với *method execution* trên Spring bean. Bài không mở rộng sang AspectJ compile-time/load-time weaving hoặc lý thuyết Aspect chung.

## 2. Spring chuẩn bị chuỗi trước khi lời gọi được thực hiện như thế nào?

Trong lúc khởi tạo container, auto-proxy creator của Spring tìm các advisor áp dụng cho bean. Một advisor kết hợp một điều kiện chọn join point (pointcut, với advisor phù hợp) và một advice. Với cấu hình `@AspectJ`, Spring đọc các method advice khai báo trong bean `@Aspect`, dựng advisor tương ứng và có thể tạo proxy cho target bean.

Khi client thực sự gọi method qua proxy, luồng được mô tả như sau:

1. **Proxy tiếp nhận lời gọi**. Có thể là JDK dynamic proxy hoặc class-based proxy (CGLIB), tùy target và cấu hình. Loại proxy khác nhau nhưng nguyên tắc interceptor chain tương tự.
2. **Spring xác định target và method**, rồi thu thập các interceptor/advice phù hợp với phương thức hiện tại. Tập ứng viên có thể được tính/cached theo cấu hình; với một số pointcut động, điều kiện còn được kiểm tra theo lời gọi.
3. **Các advisor được sắp thứ tự** theo độ ưu tiên đã cấu hình. Advice dạng `@Before`, `@AfterReturning`, `@AfterThrowing`, `@After` cũng có thể được Spring thích ứng thành interceptor để tham gia chuỗi.
4. **Đối tượng đại diện cho lời gọi** giữ thông tin method, target, tham số và vị trí hiện tại trong chuỗi interceptor.
5. **Lời gọi tiếp tục qua từng interceptor** nhờ `proceed()`. Đến cuối chuỗi, Spring mới gọi method thật trên target.
6. **Giá trị trả về hoặc exception đi ngược ra ngoài** qua những interceptor đã tiếp tục lời gọi. Mỗi interceptor có thể chạy logic sau, xử lý lỗi, trả kết quả hoặc ném exception.

Chú ý: đây là mô hình hành vi, **không phải cam kết** Spring lúc nào cũng tái dựng nguyên danh sách advisor từ đầu cho mọi method call; triển khai có thể cache kết quả tra cứu và tối ưu nhiều bước. Từ góc nhìn ứng dụng, điều quan trọng là thứ tự advice được chọn, điều kiện pointcut tại invocation và đường đi của `proceed()`.

### Một hình dung gần với Spring AOP API

Ở mức API thấp, Spring hỗ trợ interface:

```java
import org.aopalliance.intercept.MethodInterceptor;
import org.aopalliance.intercept.MethodInvocation;

class TraceInterceptor implements MethodInterceptor {
    @Override
    public Object invoke(MethodInvocation invocation) throws Throwable {
        System.out.println("enter " + invocation.getMethod().getName());
        try {
            Object result = invocation.proceed();
            System.out.println("return " + result);
            return result;
        } catch (Throwable error) {
            System.out.println("throw " + error.getClass().getSimpleName());
            throw error;
        }
    }
}
```

Đây là **đoạn minh họa API, không phải ứng dụng độc lập**. Spring gọi `invoke(MethodInvocation)` cho interceptor được cài trong chuỗi. Khi `invocation.proceed()` chạy, điều khiển chuyển sang **interceptor kế tiếp**, hoặc tới target nếu đã hết chuỗi. Với `@Around` dùng annotation, bạn thường thao tác qua `ProceedingJoinPoint.proceed()`; Spring nối cơ chế đó với chuỗi lời gọi dưới tầng proxy.

## 3. `proceed()` thực chất có ý nghĩa gì?

Trong Spring AOP, `proceed()` **không có nghĩa “gọi ngay target bất chấp advice khác”**. Nó tiếp tục phần **còn lại của chain** ở bên trong interceptor hiện tại.

Nếu thứ tự là `A → B → C → target` thì:

- Khi A gọi `proceed()`, điều khiển vào B.
- Khi B gọi `proceed()`, điều khiển vào C.
- Khi C gọi `proceed()`, Spring tiếp tục tới target nếu không còn interceptor nào nữa.
- Sau khi target trả về, C quay lại đoạn code sau `proceed()` của C; lần lượt B rồi A tiếp tục phần logic sau.
- Nếu target hoặc một interceptor phía trong ném exception, exception đi ngược qua các khung gọi đang mở, trừ khi một interceptor xử lý hoặc thay đổi nó.

Với `@Around`, lời gọi này là tùy chọn do advice quyết định:

| Hành vi trong around advice | Tác động lên lời gọi |
| --- | --- |
| Gọi `proceed()` một lần, trả lại kết quả | Cách thông thường: đi tiếp qua chain rồi trả kết quả |
| Không gọi `proceed()` | **Short-circuit**: các interceptor phía trong và target không được gọi qua nhánh này |
| Gọi `proceed()` nhiều lần | Có thể khiến phần chain còn lại và target thực thi nhiều lần; chỉ nên làm khi chủ đích và an toàn |
| `return` một giá trị khác | Caller nhận giá trị do around advice quyết định, miễn tương thích với hợp đồng method |
| `catch` exception rồi `throw` lại | Caller vẫn nhận lỗi, interceptor phía ngoài có thể quan sát |
| `catch` exception và trả fallback | Caller nhận fallback, interceptor phía ngoài nhìn thấy kết thúc thành công thay vì lỗi |

Đối với `@Before`, Spring chạy advice trước và sau đó tự tiếp tục tới phần còn lại nếu advice không ném exception; người viết `@Before` **không cần và không có quyền gọi `proceed()` trực tiếp**. Tương tự, `@AfterReturning` hoặc `@AfterThrowing` không sử dụng `proceed()` như một `@Around`.

## 4. Ví dụ độc lập: hai around interceptor bao nhau

Ví dụ dưới đây dùng **Java 17+, Maven, Spring Framework 6.2.6**. Ta khai báo hai aspect với thứ tự rõ ràng:

- `OuterAspect`: `@Order(1)`, ưu tiên cao hơn.
- `InnerAspect`: `@Order(2)`, ưu tiên thấp hơn.
- Cả hai `@Around` khớp method `execute(...)` của cùng một Spring service.

Ví dụ in ra toàn bộ đường đi vào/ra, gồm trường hợp method ném exception. Không cần Spring Boot; sử dụng `AnnotationConfigApplicationContext` để quan sát Spring AOP trực tiếp.

Cấu trúc:

```text
spring-interceptor-chain/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── InterceptorChainDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-interceptor-chain</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.6</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.InterceptorChainDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tệp `src/main/java/demo/InterceptorChainDemo.java`:**

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.core.annotation.Order;

public class InterceptorChainDemo {
    public interface WorkService {
        String execute(String value);
    }

    public static class WorkServiceImpl implements WorkService {
        @Override
        public String execute(String value) {
            System.out.println("TARGET " + value);
            if ("fail".equals(value)) {
                throw new IllegalArgumentException("bad request");
            }
            return "DONE:" + value;
        }
    }

    @Aspect
    @Order(1)
    public static class OuterAspect {
        @Around("execution(* demo..*.execute(..))")
        public Object wrap(ProceedingJoinPoint pjp) throws Throwable {
            System.out.println("OUTER enter");
            try {
                Object result = pjp.proceed();
                System.out.println("OUTER return " + result);
                return result;
            } catch (Throwable error) {
                System.out.println("OUTER throw " + error.getMessage());
                throw error;
            } finally {
                System.out.println("OUTER finally");
            }
        }
    }

    @Aspect
    @Order(2)
    public static class InnerAspect {
        @Around("execution(* demo..*.execute(..))")
        public Object wrap(ProceedingJoinPoint pjp) throws Throwable {
            System.out.println("INNER enter");
            try {
                Object result = pjp.proceed();
                System.out.println("INNER return " + result);
                return result;
            } catch (Throwable error) {
                System.out.println("INNER throw " + error.getMessage());
                throw error;
            } finally {
                System.out.println("INNER finally");
            }
        }
    }

    @Configuration
    @EnableAspectJAutoProxy
    public static class Config {
        @Bean
        public WorkService workService() {
            return new WorkServiceImpl();
        }

        @Bean
        public OuterAspect outerAspect() {
            return new OuterAspect();
        }

        @Bean
        public InnerAspect innerAspect() {
            return new InnerAspect();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            WorkService service = context.getBean(WorkService.class);
            System.out.println("AOP_PROXY=" + AopUtils.isAopProxy(service));

            System.out.println("=== SUCCESS ===");
            String result = service.execute("ok");
            System.out.println("CLIENT " + result);

            System.out.println("=== FAILURE ===");
            try {
                service.execute("fail");
            } catch (IllegalArgumentException ex) {
                System.out.println("CLIENT caught " + ex.getMessage());
            }
        }
    }
}
```

**Chạy từ thư mục chứa `pom.xml`:**

```bash
mvn -q compile exec:java
```

**Các dòng stdout do chương trình in, theo thứ tự** (không tính thông báo từ Maven hoặc logging của môi trường):

```text
AOP_PROXY=true
=== SUCCESS ===
OUTER enter
INNER enter
TARGET ok
INNER return DONE:ok
INNER finally
OUTER return DONE:ok
OUTER finally
CLIENT DONE:ok
=== FAILURE ===
OUTER enter
INNER enter
TARGET fail
INNER throw bad request
INNER finally
OUTER throw bad request
OUTER finally
CLIENT caught bad request
```

Vì sao thứ tự lại như vậy?

1. `@EnableAspectJAutoProxy` bật cơ chế auto-proxy; các `@Bean` cung cấp cả target service và hai aspect. Các `@Aspect` phải được đăng ký thành bean để Spring phát hiện.
2. Spring tạo proxy cho `WorkService` vì cả hai pointcut khớp `execute(..)`. Với cấu hình Spring Framework và interface trong ví dụ, proxy thường là JDK dynamic proxy.
3. `@Order(1)` làm `OuterAspect` ưu tiên hơn `@Order(2)`: trên **đường vào**, outer chạy trước inner. Cả hai gọi `proceed()` nên target mới được thực thi.
4. Trong nhánh thành công, target trả `DONE:ok`. Inner xử lý return và finally trước, rồi outer xử lý return và finally, sau cùng client nhận kết quả.
5. Trong nhánh lỗi, target ném `IllegalArgumentException`. Inner bắt, in thông tin rồi ném lại; outer tiếp tục bắt và ném lại; client mới nhận exception. Các khối `finally` vẫn chạy theo thứ tự đi ra.

Ví dụ cố ý có **một around advice trong mỗi aspect** để tránh phụ thuộc vào thứ tự nhiều advice cùng loại hoặc nhiều loại trong cùng aspect.

## 5. `@Order` quyết định thứ tự nào?

Giả sử hai aspect cùng advice một method:

```java
@Aspect
@Order(10)
class MetricsAspect { /* ... */ }

@Aspect
@Order(20)
class AuditAspect { /* ... */ }
```

Đây là **mã minh họa, không phải lớp chạy độc lập**. Trong Spring, giá trị `@Order` **nhỏ hơn có mức ưu tiên cao hơn**. Khi hai around advice này đều khớp cùng method:

```text
metrics.enter          <- ưu tiên cao: vào trước
    audit.enter        <- ưu tiên thấp hơn: vào sau
        target()
    audit.exit         <- ưu tiên thấp hơn: ra trước
metrics.exit           <- ưu tiên cao: ra sau
```

Vì cơ chế lồng nhau, không được hiểu “aspect ưu tiên cao luôn in mọi dòng trước aspect ưu tiên thấp”. Chỉ có **đường vào** là từ ưu tiên cao xuống thấp; **đường ra** diễn ra ngược lại.

Nếu hai aspect khác nhau cùng áp dụng và không chỉ rõ thứ tự, **không có bảo đảm về thứ tự tương đối**. Có thể dùng `org.springframework.core.annotation.Ordered` thay cho `@Order`. Đừng dựa vào thứ tự khai báo method hay thứ tự Spring tình cờ khởi tạo bean để xác lập hợp đồng nghiệp vụ.

### Nhiều advice trong cùng một `@Aspect`

Trong Spring Framework hiện đại, các loại advice của cùng aspect có thứ tự ưu tiên theo loại: `@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing`. Tuy vậy `@After` mang ý nghĩa **finally** nên thực tế được gọi sau `@AfterReturning` hoặc `@AfterThrowing` cùng aspect khi các advice đó áp dụng. Nhiều advice **cùng loại** trong một class `@Aspect` không có thứ tự ổn định chỉ dựa trên thứ tự dòng nguồn Java.

Nếu kết quả phụ thuộc nghiêm ngặt vào thứ tự, ưu tiên tách trách nhiệm sang các aspect riêng có `@Order` rõ ràng, hoặc dùng một `@Around` điều phối trong phạm vi nhỏ. Đừng “khắc phục” bằng cách ngẫu nhiên đổi vị trí khai báo method.

## 6. Các dạng advice đi vào chuỗi như thế nào?

Mỗi advice có hợp đồng khác nhau. Trong Spring AOP, các dạng thường gặp:

| Dạng advice | Thời điểm hiệu lực | Tác động điển hình |
| --- | --- | --- |
| `@Before` | Trước khi chuyển đến target | Kiểm tra, log, xác thực tiền điều kiện; có thể ném exception khiến lời gọi dừng |
| `@Around` | Bao quanh phần còn lại của chain | Quyết định gọi `proceed()`, đổi tham số/giá trị trả về, đo thời gian, retry hoặc short-circuit |
| `@AfterReturning` | Khi execution kết thúc bình thường | Quan sát return value, ghi metric kết quả; không thay được reference trả về chỉ bằng cách `return` từ advice |
| `@AfterThrowing` | Khi execution thoát bằng exception phù hợp | Quan sát exception từ join point; không phải callback tổng quát cho mọi lỗi do các advice khác gây ra |
| `@After` | Kết thúc method execution theo cả đường thường lẫn lỗi | Cleanup kiểu `finally` |

Ví dụ advice được tách thành những đoạn ngắn trong Spring bean `@Aspect`:

```java
@Before("execution(* demo..*.execute(..))")
public void beforeExecution() {
    System.out.println("BEFORE");
}

@AfterReturning(
    pointcut = "execution(* demo..*.execute(..))",
    returning = "result"
)
public void afterSuccess(Object result) {
    System.out.println("RETURNED " + result);
}

@AfterThrowing(
    pointcut = "execution(* demo..*.execute(..))",
    throwing = "error"
)
public void afterFailure(Throwable error) {
    System.out.println("THREW " + error.getClass().getSimpleName());
}

@After("execution(* demo..*.execute(..))")
public void finallyExecuted() {
    System.out.println("AFTER finally");
}
```

Các method trên là **đoạn minh họa**, chưa phải file Java biên dịch độc lập; cần class `@Aspect`, import các annotation AspectJ, bean registration và context. Nếu đặt tất cả vào cùng một aspect, không nên dự đoán thứ tự stdout chỉ bằng cách đọc thứ tự khai báo. Dùng ví dụ hai aspect ở phần 4 khi cần một trace thực sự xác định.

Lưu ý khác: khi một `@Around` phía trong bắt exception và trả fallback bình thường, advice phía ngoài có thể thấy **kết quả thành công**. Khi `@Around` ngoài short-circuit mà không gọi `proceed()`, các interceptor ở trong nó, kể cả `@Before` và `@After` ở phần trong, đều không có cơ hội chạy.

## 7. Giá trị trả về và ngoại lệ xuyên qua các interceptor

Một interceptor không nhận “bản sao độc lập” của lời gọi. Nó tham gia vào **cùng đường thực thi logic** và tạo nên kết quả mà client nhận.

Ví dụ Spring around advice trả fallback khi service lỗi:

```java
@Around("execution(* demo..*.load(..))")
public Object recover(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (IllegalStateException ex) {
        return "FALLBACK";
    }
}
```

Đây là **một advice method minh họa**; kiểu trả về thực tế của target phải tương thích với giá trị fallback. Nếu advice này ở trong một `@Around` khác, interceptor ngoài có thể nhận chuỗi `FALLBACK` như một return bình thường, mặc dù target đã ném exception.

Điều gì xảy ra khi interceptor đổi kết quả?

```text
Caller
  |
  v
Outer interceptor
  |
  v
Recovery interceptor
  |
  v
Target -> throws IllegalStateException
  |
  v
Recovery interceptor catches -> returns "FALLBACK"
  |
  v
Outer interceptor sees normal return "FALLBACK"
  |
  v
Caller receives "FALLBACK"
```

**Không nên nuốt lỗi bừa bãi.** Các interceptor phía ngoài (ví dụ transaction, audit, retry) có thể dựa vào kết quả/exception để quyết định hành vi. Một advice tự chuyển exception thành thành công sẽ thay đổi tín hiệu mà phần còn lại của chain nhìn thấy. Phân tích ranh giới rollback, retry, logging và HTTP error mapping khi đưa fallback vào nghiệp vụ thực tế.

Với `@AfterReturning`, bạn có thể quan sát giá trị trả về, nhưng việc `return` từ method advice **không thay thế** giá trị method target trả cho caller. Muốn thay return value một cách chủ đích, dùng `@Around` và trả object phù hợp.

## 8. Pointcut và method matching nằm ở đâu trong chuỗi?

Khi client gọi proxy, Spring chỉ cần thực thi những interceptor được xác định là phù hợp với method. Hai chuyện phải phân biệt:

- **Có proxy hay không:** auto-proxy creator quyết định bean có cần proxy dựa vào advisor/điều kiện phù hợp.
- **Lời gọi hiện tại khớp advisor nào:** proxy xác định interceptor chain cho method cụ thể; một số pointcut có thể kiểm tra thêm args vào thời điểm gọi.

Với pointcut tĩnh dựa trên method signature, các interceptor có thể được chọn theo method và cached. Với các dạng dynamic matching, bộ kiểm tra có thể sử dụng tham số của chính invocation. Không vì một bean có proxy mà mọi method trên bean đều chạy toàn bộ advisor.

Ví dụ:

```java
@Around("execution(* demo..*.execute(..))")
public Object aroundExecute(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

Đây là **advice minh họa**: biểu thức `execution` khớp *method execution* có tên `execute` trong phạm vi package phù hợp. Nó không mặc nhiên khớp method `cancel` hay `status` của cùng bean. Nếu method không khớp advisor nào, Spring có thể gọi target mà không chạy logic advice đó.

**Spring AOP proxy không chặn constructor, field read/write hay mọi điểm gọi**. Giới hạn chính là *method execution join point* đi qua Spring proxy. Khi target tự gọi `this.anotherMethod()`, lời gọi bên trong chạy trên chính target và thường bỏ qua advice chỉ khớp `anotherMethod()`, vì nó không đi qua proxy.

## 9. Hai hình thức proxy, một nguyên tắc chain

Spring AOP có hai con đường proxy phổ biến:

| Kiểu proxy | Cách client đi vào | Interceptor chain |
| --- | --- | --- |
| JDK dynamic proxy | Gọi qua interface được proxy triển khai | Áp dụng các interceptor/advisor khớp lời gọi |
| CGLIB class-based proxy | Gọi method phù hợp trên subclass proxy | Áp dụng các interceptor/advisor khớp lời gọi |

Cách tạo proxy tác động khả năng intercept method và cách inject bean, nhưng **không thay đổi ý nghĩa `proceed()`**: tiếp tục chain cho tới target.

Một số giới hạn khi dùng class-based proxy: `final class` không thể được subclass để tạo CGLIB proxy; `final method` hoặc `private method` không thể được advice theo cơ chế override. Với JDK proxy, caller tương tác qua interface của proxy; ép kiểu sang implementation có thể thất bại.

Dù chọn JDK hay CGLIB, lời gọi trực tiếp tới một object tự `new` (không lấy qua Spring container) không tự động đi qua Spring AOP interceptor chain. Khi cùng class gọi method của chính nó bằng `this`, đây cũng là lời gọi nằm ngoài entry point proxy.

## 10. Chuỗi interceptor trong Spring transaction, cache và async

Ở ứng dụng Spring thực tế, bạn có thể gặp chuỗi interceptor nhiều nguồn chứ không chỉ các `@Aspect` bạn tự viết:

- **Transaction:** interceptor liên quan `@Transactional` có thể mở hoặc tham gia transaction trước khi phần bên trong chain chạy; khi đi ra, nó commit/rollback theo kết quả, exception và các quy tắc cấu hình.
- **Cache:** interceptor của `@Cacheable` có thể trả kết quả cache mà không gọi target; khi cache miss, nó có thể tiếp tục chain để lấy giá trị.
- **Async:** cơ chế `@Async` có thể chuyển execution qua executor/thread khác; loại interceptor và cách gọi tiếp còn tùy cấu hình, nên không suy thứ tự đồng bộ giống ví dụ console nếu async được bật.

Tất cả đều liên quan đến việc caller tương tác với Spring bean qua proxy, nhưng mỗi tính năng có semantics riêng. **Không nên mặc định** Spring đặt transaction/cache/async và application `@Aspect` của bạn theo một thứ tự cố định trong mọi project: phải xem `@Order`, `Ordered` và cấu hình hiệu lực của các advisor hạ tầng.

Ví dụ nếu around advice có priority cao hơn transaction interceptor, code trước `proceed()` của around sẽ chạy **trước khi** transaction bên trong bắt đầu; code sau `proceed()` của around sẽ chạy **sau khi** transaction bên trong xử lý xong. Nếu muốn metric nằm trong transaction hay ngoài transaction, cần chỉ rõ thứ tự và kiểm tra trace thực tế.

## 11. Gỡ lỗi một chuỗi interceptor chạy không như dự kiến

Khi log không xuất hiện hoặc đảo thứ tự, kiểm tra theo thứ tự sau:

1. **Client có gọi qua Spring proxy không?** Inject hoặc lấy bean từ context; tránh `new Implementation()` và nhận biết self-invocation qua `this`.
2. **Có thực sự là AOP proxy không?** Dùng `AopUtils.isAopProxy(bean)`. Đây chỉ là bước đầu: có proxy không có nghĩa method nào cũng có advice.
3. **Advisor khớp method đang gọi không?** Rà package, method name, access modifier, parameter types, annotation, target type, tên bean và runtime arguments.
4. **Các aspect có là Spring bean không?** `@Aspect` phải được Spring container đăng ký; Spring Framework thuần có thể cần `@EnableAspectJAutoProxy`, Boot có thể tự bật với starter và điều kiện phù hợp.
5. **Thứ tự `@Order` đã rõ chưa?** Số càng thấp vào càng sớm, ra càng muộn. Nếu không quy định thứ tự giữa các aspect khác nhau thì không nên dự đoán stdout cố định.
6. **Có interceptor short-circuit không?** Kiểm tra các `@Around`, cache hit hoặc code trả sớm trước `proceed()`; interceptor/target bên trong sẽ không chạy.
7. **Exception có bị bắt hoặc chuyển thành fallback?** Outer interceptor có thể thấy normal return khi inner đã xử lý exception. Ngược lại, interceptor ném exception mới có thể che khuất kết quả target.
8. **Có gọi `proceed()` nhiều lần không?** Những lần chạy lặp có thể dẫn đến ghi dữ liệu nhiều lần; chỉ dùng có chủ đích như retry có kiểm soát.
9. **Có bao nhiêu advice trong cùng aspect?** Với nhiều advice cùng loại, đừng trông chờ thứ tự dựa vào vị trí source Java.
10. **Có phải lời gọi bất đồng bộ?** Quan sát thread/context và ranh giới executor; một trace nhiều thread không phản ánh call stack tuần tự duy nhất như ví dụ đơn giản.

Nếu cần kiểm tra bằng Java, có thể dùng API `org.springframework.aop.framework.Advised` cho các Spring AOP proxy hỗ trợ để xem advisors:

```java
Object bean = context.getBean(WorkService.class);
if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (var advisor : advised.getAdvisors()) {
        System.out.println(advisor);
    }
}
```

Đây là **đoạn bổ sung** cho ứng dụng có Spring context và `WorkService`, không phải ví dụ standalone. Nó giúp xem advisor đã gắn trên proxy nhưng không thay thế việc xác định **advisor nào thực sự khớp method invocation** hay dynamic runtime condition. Với proxy bị cấu hình frozen/opaque hoặc các proxy khác, cách quan sát có thể thay đổi.

## 12. Tình huống tự kiểm tra

**A.** Chain gồm A `@Order(1)` và B `@Order(5)`, cả hai đều `@Around`, đều gọi `proceed()` một lần. Target trả bình thường. Thứ tự?  
**Đáp án:** A-enter, B-enter, target, B-exit, A-exit.

**B.** A vào trước B nhưng A trả giá trị ngay mà không gọi `proceed()`. B và target có chạy không?  
**Đáp án:** Không. A short-circuit phần chain phía trong.

**C.** Target ném exception, B bắt và trả fallback bình thường. A phía ngoài sẽ nhìn thấy gì khi `proceed()` của A trả về?  
**Đáp án:** Một return value bình thường do B trả; exception đã bị B xử lý. A không tự nhìn thấy lỗi gốc trừ khi được truyền theo cách khác.

**D.** Tại sao một `@AfterReturning` không thay thế return value bằng cách `return "new"`?  
**Đáp án:** Hợp đồng `@AfterReturning` là chạy sau execution thành công và quan sát kết quả; muốn thay kết quả, dùng around advice với giá trị trả về phù hợp.

**E.** Method `process()` trên target gọi `this.save()`, còn advice chỉ khớp `save()`. Advice có chạy nhờ chuỗi interceptor của `process()` không?  
**Đáp án:** Không cho lời gọi nội bộ này. Lời gọi `this.save()` không vào lại Spring proxy.

**F.** Hai aspect có nhiều loại advice nhưng không khai báo `@Order`. Có thể lấy thứ tự khai báo source Java làm thứ tự thực thi tin cậy không?  
**Đáp án:** Không. Đặt thứ tự giữa các aspect và thiết kế rõ việc có nhiều advice cùng loại.

## 13. Tài liệu Spring Framework chính thức

- [Spring AOP — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@Around`, `proceed()`, advice theo return/exception và quy tắc ordering.
- [Spring AOP APIs — Advice](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html): `MethodInterceptor` và `MethodInvocation.proceed()`.
- [Spring AOP — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB, đường đi qua proxy, self-invocation.
- [Spring AOP — Pointcuts](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): method-execution pointcuts và các điều kiện áp dụng.
