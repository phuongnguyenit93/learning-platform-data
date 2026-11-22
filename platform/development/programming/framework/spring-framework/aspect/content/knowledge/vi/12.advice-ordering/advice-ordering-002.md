# Độ ưu tiên bằng @Order và Ordered trong Spring AOP

## 1. Mục tiêu bài học

Một Spring bean có thể phù hợp với nhiều lời advice của các lớp `@Aspect` khác nhau. Ví dụ, trước khi `TransferService.transfer()` thực hiện chuyển tiền, bạn cần có audit; đồng thời muốn thu thập metrics bao quanh cùng lời gọi. Nếu không quy định thứ tự, việc hai aspect cùng match một Spring AOP join point **không mang theo lời bảo đảm rằng Spring sẽ thực thi chúng theo thứ tự khai báo class, đăng ký bean hoặc vị trí trong source file**.

Spring Framework cung cấp hai cách quen thuộc để quy định **precedence giữa các aspect**:

- Đánh dấu class aspect bằng `@Order(value)` từ `org.springframework.core.annotation.Order`.
- Cho class aspect triển khai interface `org.springframework.core.Ordered` và trả về giá trị từ `getOrder()`.

**Quy tắc gốc: giá trị thứ tự càng nhỏ thì độ ưu tiên càng cao.** Một aspect có order `10` được xét có precedence cao hơn aspect order `20`. Khi cả hai advice match một method invocation trên Spring proxy, aspect có precedence cao thường chạy **trước khi đi vào** chuỗi bên trong, và **sau cùng khi đi ra**. Đây là mô hình **bao ngoài – bao trong**, không phải phép sắp xếp mọi dòng log theo số tăng dần.

Bài này tập trung vào **Spring Aspect/Spring AOP dạng proxy** với các mục tiêu:

1. Phân biệt thứ tự *trên đường vào* và *trên đường ra* của invocation.
2. Áp dụng đúng `@Order` và `Ordered.getOrder()` cho các **Spring-managed `@Aspect` beans**.
3. Hiểu `Ordered.HIGHEST_PRECEDENCE`, `Ordered.LOWEST_PRECEDENCE`, giá trị trùng nhau và mặc định khi không khai báo.
4. Phân biệt **thứ tự giữa các aspect** với **thứ tự advice bên trong cùng một aspect**.
5. Biết các giới hạn khi có Spring transaction/cache/security advisors, self-invocation và short-circuit.
6. Chạy một ví dụ **Maven/Java 17+** với một aspect dùng `@Order`, một aspect dùng `Ordered`, kiểm chứng cả success và exception.

**Special Note:** Chỉ giải thích hành vi cụ thể của Spring Aspect/Spring AOP. Các kiến thức Aspect chung đã có ở chủ đề khác nên không lặp lại.

## 2. Spring quyết định thứ tự ở đâu?

Một lời gọi Spring AOP bắt đầu từ **tham chiếu proxy** mà caller nhận được từ container, không phải một method của class gốc được gọi trực tiếp bằng `new`.

~~~text
Caller
   |
   v
Spring AOP proxy
   |
   +--> Aspect A: @Around, order = 10
   |       |  A: enter
   |       v
   |    Aspect B: @Around, order = 20
   |       |  B: enter
   |       v
   |    TargetService.method()
   |       |
   |       v
   |       B: exit
   |       |
   |       v
   |       A: exit
   |
   v
Caller nhận kết quả/exception
~~~

Trong hình, hai aspect đều có around advice và mỗi advice gọi `ProceedingJoinPoint.proceed()` đúng một lần. Khi **order 10 cao precedence hơn order 20**, tầng A bao quanh B.

Điều quan trọng là **order thuộc về aspect/advisor**; nó không thay đổi tên method, tham số, return value hay pointcut. Nếu pointcut của B không khớp, sẽ không có B trong chain bất kể giá trị order của nó. Nếu caller không đi qua proxy, cả hai lời advice đều có thể bị bỏ qua.

### 2.1. “Chạy trước” và “chạy sau” phụ thuộc chiều

Giả sử A có order `10` và B có order `20`:

| Thời điểm | Aspect có precedence cao hơn: A(10) | Aspect có precedence thấp hơn: B(20) |
| --- | --- | --- |
| Đi vào invocation | **Chạy trước B** | Chạy sau A |
| Khi chuyển tiếp qua `proceed()` | Đưa lời gọi đến phần chain có B | Đưa lời gọi đến target hoặc phần chain sâu hơn |
| Đi ra sau normal return | **Chạy sau B** | Chạy trước A |
| Đi ra trong exceptional exit | Finally/catch của A chạy **sau** phần tương ứng của B nếu cả hai đã vào | Finally/catch của B chạy trước A |

Do đó phát biểu “`@Order(10)` luôn thực thi tất cả các dòng code trước `@Order(20)`” là **sai**. Nó có precedence cao và là **wrapper bên ngoài**; những thao tác `finally`/hậu xử lý của nó diễn ra sau khi B đã kết thúc.

## 3. Cách 1: dùng @Order trên lớp Spring aspect

Ví dụ:

~~~java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class AuditAspect {

    @Around("execution(* example.TransferService.transfer(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("audit: enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("audit: exit");
        }
    }
}
~~~

Đây là class aspect minh họa; ví dụ runnable hoàn chỉnh nằm ở mục 7.

- Import **`org.springframework.core.annotation.Order`**, không phải một annotation có tên tương tự của framework khác.
- Đặt `@Order(10)` trên **class `@Aspect`** khi muốn quy định precedence so với những aspect khác.
- Spring phải **đăng ký aspect thành bean** (ví dụ `@Component` trong component scanning, hoặc `@Bean` trong cấu hình). `@Aspect` và `@Order` tự chúng **không** biến class thành Spring bean.
- `@Order` là metadata để Spring sắp xếp các advisor/aspect khi những advisor đó tham gia cùng một chain.
- `@Order` không ép tất cả target beans phải có proxy: chỉ các method/beans tương ứng với advisor mới có thể được advice.
- `@Order` **không điều khiển bean startup/khởi tạo singleton**; thứ tự khởi tạo chủ yếu phụ thuộc dependency graph và `@DependsOn` khi cần. Đây là vấn đề hoàn toàn khác với advice precedence.

Khi code chỉ cần một giá trị ưu tiên tĩnh, `@Order` thường đơn giản và dễ nhìn hơn `implements Ordered`.

## 4. Cách 2: implement Ordered và trả getOrder()

Spring cung cấp interface:

~~~java
package org.springframework.core;

public interface Ordered {
    int getOrder();
}
~~~

Đây là mô tả giản lược chữ ký quan trọng của API, không phải mã để đặt vào project nhằm định nghĩa lại interface Spring.

Trong một Spring aspect:

~~~java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.Ordered;

@Aspect
public class MetricsAspect implements Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Around("execution(* example.TransferService.transfer(..))")
    public Object measure(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("metrics: enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("metrics: exit");
        }
    }
}
~~~

Giá trị `20` ở đây nhỏ hơn hay lớn hơn **không mang nghĩa “tốt/xấu”**; Spring chỉ so sánh precedence. Vì `20 > 10`, MetricsAspect có precedence thấp hơn AuditAspect(10) trong ví dụ.

**Khi nên dùng `Ordered`:** khi aspect muốn cung cấp thứ tự theo một hợp đồng Java rõ ràng hoặc cần cấu hình order lúc khởi tạo bean. Tuy nhiên, đừng hiểu “dynamic” là có thể thay đổi `getOrder()` tùy tiện giữa các lời gọi để Spring tự rebuild chain: thứ tự advisor thường được thiết lập khi auto-proxy infrastructure chuẩn bị proxy/chain, nên thay đổi giá trị ở runtime không phải cách ổn định để đảo precedence. Nếu muốn đổi order của aspect, cấu hình trước khi context tạo proxy rồi kiểm thử lại.

**Tránh khai báo cả `@Order` và `Ordered` trên cùng một aspect** nếu không có lý do và không kiểm tra thuật toán resolve order của phiên bản Spring. Hai nguồn thông tin khác nhau dễ gây hiểu nhầm cho người bảo trì.

## 5. Quy tắc giá trị order

Spring `Ordered` định nghĩa các hằng:

~~~java
Ordered.HIGHEST_PRECEDENCE // Integer.MIN_VALUE
Ordered.LOWEST_PRECEDENCE  // Integer.MAX_VALUE
~~~

Trong ví dụ:

| Giá trị | Ý nghĩa tương đối |
| --- | --- |
| `Ordered.HIGHEST_PRECEDENCE` | Giá trị rất nhỏ; thuộc nhóm precedence cao nhất |
| `@Order(-100)` | Precedence cao hơn `@Order(0)` |
| `@Order(0)` | Precedence cao hơn `@Order(10)` |
| `@Order(10)` | Cao hơn `@Order(20)` |
| `Ordered.LOWEST_PRECEDENCE` | Giá trị rất lớn; thuộc nhóm precedence thấp nhất |

Bạn **không cần** luôn dùng 0 hoặc 1. Đặt một dải giá trị có chủ đích cho từng nhóm, ví dụ audit-tracing, business metrics, custom policy. Tuy nhiên, **đừng tự tuyên bố rằng mọi infrastructure advisor luôn có giá trị thấp/cao hơn nhóm của mình**: transaction/cache/security có thể có ordering và proxy configuration riêng.

### 5.1. Nếu không đặt @Order và không implement Ordered?

Spring không có thông tin precedence riêng để giải quyết giữa các aspect cùng match. Tài liệu Spring nói rõ khi advice nằm trong **những aspect khác nhau** và không cấu hình precedence, **thứ tự thực thi không xác định**. Vì vậy:

- Không dựa vào thứ tự file Java, tên class theo bảng chữ cái, hay thứ tự các method `@Bean`.
- Không dựa vào việc một lần chạy thấy A trước B rồi giả định mọi lần đều vậy.
- Nếu thứ tự ảnh hưởng behavior, phải khai báo rõ bằng `@Order` hoặc `Ordered`.

Ở nhiều API Spring, đối tượng không khai báo order có thể được xét tương đương mức precedence thấp theo comparator. Tuy nhiên, **điều đó không tạo thứ tự ổn định giữa các aspect cùng mức**. Không biến một chi tiết comparator thành hợp đồng business.

### 5.2. Nếu hai aspect cùng order?

Ví dụ A và B đều `@Order(10)`. Khi không có cơ chế tie-break được tài liệu bảo đảm, thứ tự **giữa hai aspect vẫn không nên được dựa vào**. Nếu cần A chắc chắn bao ngoài B, dùng **hai giá trị khác nhau** và viết integration test xác nhận điều đó.

Đừng đặt cùng một order rồi cố kiểm soát bằng tên bean hoặc thứ tự đăng ký trong cấu hình: những cách đó tạo coupling không rõ ràng và dễ gãy sau nâng cấp Spring.

## 6. @Order và Ordered có cần dùng cùng một kiểu không?

Không. Trong **hai aspect khác nhau**, một aspect có `@Order(10)` và aspect kia `implements Ordered { getOrder() -> 20; }` đều có thể tham gia cùng quy tắc precedence.

Ví dụ:

~~~text
AuditAspect:   @Aspect + @Order(10)
MetricsAspect: @Aspect + implements Ordered; getOrder() = 20

=> trên đường vào: audit trước metrics
=> trên đường ra: metrics trước audit
~~~

Bạn không cần đổi mọi class sang `Ordered` chỉ vì một aspect khác đang implement interface. Tuy nhiên, hãy giữ convention nhất quán trong một codebase để người đọc tìm cấu hình ordering dễ hơn.

**Phân biệt với `@Order` ở vị trí khác:** Spring `@Order` còn được một số API dùng để sắp xếp collection beans, event listeners hoặc infrastructure. Ở bài này ta chỉ xét **precedence của Spring AOP aspects**. Không được suy ra từ việc một bean có `@Order` rằng mọi callback và mọi bean phụ thuộc vào nó cũng sẽ khởi tạo hoặc chạy theo thứ tự đó.

## 7. Project Java 17+ chạy được: hai aspect, hai cách khai báo order

Chương trình bên dưới chứng minh:

- Spring Framework 6.2.19, AspectJ Weaver 1.9.25.1, Java 17+, Maven.
- Một `TransferService` là Spring-managed bean.
- `AuditAspect` dùng `@Order(10)` và `@Around`.
- `MetricsAspect` dùng `implements Ordered`, `getOrder() == 20` và `@Around`.
- Cả hai pointcut nhắm tới một public method `transfer(boolean fail)`.
- Normal return và exceptional exit cho thấy **chiều vào tăng dần order**, **chiều ra giảm dần**.
- Hai advice đều gọi `pjp.proceed()` đúng **một lần**, không thay đổi tham số/return/exception. `finally` được dùng để xác nhận đường ra kể cả lúc lỗi.

Đây là Spring AOP **proxy-based**, không cần cấu hình AspectJ weaving.

### 7.1. Cấu trúc project

~~~text
spring-aspect-order-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── TransferService.java
    ├── AuditAspect.java
    ├── MetricsAspect.java
    └── Main.java
~~~

### 7.2. Maven: pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aspect-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.19</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
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
~~~

Dùng Spring Framework BOM để các module Spring thống nhất version. Với dự án Spring Boot, ưu tiên dùng dependency management của Boot; không tự ép version Spring trong một Boot application đã có parent/BOM.

### 7.3. TransferService.java

~~~java
package example;

public class TransferService {

    public String transfer(boolean fail) {
        System.out.println("target: begin");

        if (fail) {
            throw new IllegalArgumentException("denied");
        }

        System.out.println("target: success");
        return "OK";
    }
}
~~~

Method `transfer(false)` trả String `"OK"`; method `transfer(true)` ném `IllegalArgumentException("denied")`. Trong cả hai trường hợp, method được gọi qua một Spring AOP proxy.

### 7.4. AuditAspect.java — sử dụng @Order

~~~java
package example;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class AuditAspect {

    @Around("execution(public * example.TransferService.transfer(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("audit(10): enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("audit(10): exit");
        }
    }
}
~~~

Vì AuditAspect có precedence **10**, nó sẽ bao ngoài MetricsAspect(20). `@Around` trả đúng giá trị của `proceed()` hoặc cho exception gốc tiếp tục lan truyền, không tự short-circuit.

### 7.5. MetricsAspect.java — triển khai Ordered

~~~java
package example;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.Ordered;

@Aspect
public class MetricsAspect implements Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Around("execution(public * example.TransferService.transfer(..))")
    public Object metrics(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("metrics(20): enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("metrics(20): exit");
        }
    }
}
~~~

`Ordered.getOrder()` cung cấp precedence của chính aspect bean này. Trong ví dụ, value được hard-code để stdout chắc chắn; trong hệ thống thật có thể lấy từ cấu hình tại lúc bean được tạo, rồi giữ ổn định.

### 7.6. AppConfig.java — đăng ký aspect beans

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public TransferService transferService() {
        return new TransferService();
    }

    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }

    @Bean
    public MetricsAspect metricsAspect() {
        return new MetricsAspect();
    }
}
~~~

**Vì sao cần @Bean?** Hai class có `@Aspect` nhưng không có `@Component`. `@Bean` tạo **hai Spring aspect beans** để auto-proxy creator khám phá advisor của chúng. `@EnableAspectJAutoProxy` bật Spring AOP support. Với `proxyTargetClass = true`, Spring dùng class-based proxy để client lấy bean theo `TransferService.class`; không có interface bắt buộc trong ví dụ.

**Không cần đảo vị trí các phương thức @Bean để tạo thứ tự:** chính `@Order(10)` và `getOrder()==20` mới là hợp đồng ordering giữa hai aspect.

### 7.7. Main.java

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            TransferService service = context.getBean(TransferService.class);
            System.out.println("spring AOP proxy: "
                + AopUtils.isAopProxy(service));

            System.out.println("-- successful transfer --");
            System.out.println("caller: " + service.transfer(false));

            System.out.println("-- failed transfer --");
            try {
                service.transfer(true);
            } catch (IllegalArgumentException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }
        }
    }
}
~~~

Chạy trong thư mục có pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

### 7.8. Stdout mong đợi

~~~text
spring AOP proxy: true
-- successful transfer --
audit(10): enter
metrics(20): enter
target: begin
target: success
metrics(20): exit
audit(10): exit
caller: OK
-- failed transfer --
audit(10): enter
metrics(20): enter
target: begin
metrics(20): exit
audit(10): exit
caller caught: denied
~~~

Maven hoặc Spring có thể xuất một vài thông báo môi trường; phần trên chỉ ghi những dòng `System.out.println` của project.

### 7.9. Phân tích theo chiều vào và ra

**Success path:**

1. Caller gọi `service.transfer(false)` trên Spring AOP proxy.
2. AuditAspect(10) được vào trước, in `audit(10): enter`.
3. `pjp.proceed()` của audit chuyển sang MetricsAspect(20), in `metrics(20): enter`.
4. `pjp.proceed()` của metrics tới target, in `target: begin` và `target: success`, rồi trả `"OK"`.
5. MetricsAspect chạy `finally`: in `metrics(20): exit`.
6. AuditAspect chạy `finally`: in `audit(10): exit`.
7. Caller nhận `"OK"`. Không aspect nào đã thay return value.

**Failure path:**

1. AuditAspect(10) rồi MetricsAspect(20) vào theo cùng thứ tự.
2. Target in `target: begin` và ném `IllegalArgumentException("denied")`.
3. MetricsAspect(20) thực thi `finally` trước.
4. AuditAspect(10) thực thi `finally` sau.
5. Caller bắt **cùng exception nghiệp vụ** và in `caller caught: denied`.

Hai nhánh đều xác nhận: precedence cao **vào trước**, **ra sau**. Nó không có nghĩa “audit hoàn tất tất cả việc của nó trước khi metrics bắt đầu”.

## 8. Thử đổi thứ tự để kiểm chứng

Thay một dòng trong file `AuditAspect.java`:

~~~java
@Order(30) // Thay cho @Order(10)
~~~

Giữ `MetricsAspect.getOrder() == 20`. **Lúc này MetricsAspect(20) có precedence cao hơn AuditAspect(30)**; tức là metrics bao ngoài audit. Sau khi sửa `@Order`, compile/run lại context mới.

Các dòng nội bộ của success path có thứ tự:

~~~text
metrics(20): enter
audit(10): enter
target: begin
target: success
audit(10): exit
metrics(20): exit
~~~

**Chú ý nhãn log:** nếu bạn chỉ sửa annotation thành `@Order(30)` nhưng **không sửa chuỗi `"audit(10)"` trong `System.out.println`**, chữ `audit(10)` ở output vẫn giữ nguyên — đây là nhãn literal trong code, **không phải order hiện tại**. Để output thể hiện đúng cấu hình đã thay, sửa nhãn thành `audit(30)` đồng thời:

~~~text
metrics(20): enter
audit(30): enter
target: begin
target: success
audit(30): exit
metrics(20): exit
~~~

**Đoạn này là biến thể cấu hình**, không phải stdout mặc định của project mục 7. Việc đảo thứ tự không nhất thiết cần sửa source code của MetricsAspect hay target service.

Tương tự, bạn có thể giữ `@Order(10)` nhưng cho `MetricsAspect.getOrder()` trả 5; khi đó MetricsAspect có precedence cao hơn AuditAspect. Giá trị và chiều so sánh là yếu tố quyết định, không phải cách biểu diễn bằng annotation hay interface.

## 9. Phân biệt ordering giữa aspects và bên trong cùng @Aspect

Spring Framework có quy tắc riêng cho advice methods **khác loại trong cùng một class `@Aspect`**.

Theo tài liệu Spring hiện hành, precedence giữa những advice type **trong cùng một aspect** được gán (từ cao đến thấp):

1. `@Around`
2. `@Before`
3. `@After`
4. `@AfterReturning`
5. `@AfterThrowing`

**Sắc thái đặc biệt:** Mặc dù `@After` có precedence ở trên `@AfterReturning` và `@AfterThrowing` trong cùng aspect, nó có **finally semantics**, nên khi thực thi trên đường ra nó **xuất hiện sau** `@AfterReturning` hoặc `@AfterThrowing` tương ứng. Đừng nhìn bảng precedence mà suy rằng dòng log `@After` luôn in trước các loại after khác.

### 9.1. Nhiều advice cùng loại trong cùng aspect

Nếu bạn khai báo **hai `@Before` hoặc hai `@After` cùng loại**, đều match một join point trong **cùng class `@Aspect`**, thứ tự giữa chúng **không được Spring bảo đảm** vì Java reflection không cung cấp thứ tự khai báo source đáng tin cậy.

Ví dụ không nên dựa vào:

~~~java
@Aspect
public class ProblematicAspect {

    @Before("execution(* example.TransferService.transfer(..))")
    public void stepOne() {
        System.out.println("one");
    }

    @Before("execution(* example.TransferService.transfer(..))")
    public void stepTwo() {
        System.out.println("two");
    }
}
~~~

Bạn không thể chỉ đặt `stepOne` trước `stepTwo` trong source file rồi tuyên bố `one` luôn in trước `two`.

**Cách sửa tốt hơn:**

- Nếu hai thao tác tạo thành một sequence nghiệp vụ, **gộp chúng vào một advice method** và gọi theo thứ tự tường minh.
- Nếu chúng là hai concern độc lập có thứ tự thực sự quan trọng, **tách thành hai Spring aspect classes** rồi dùng `@Order` / `Ordered` để chỉ định precedence.
- Không cố gắn `@Order` lên từng advice method rồi suy rằng Spring AOP sẽ sắp xếp các method ấy như hai aspect độc lập. Ordering được mô tả ở cấp **aspect** và theo **advice type**.

Các snippet trên minh họa lỗi tư duy, không thuộc project chạy hoàn chỉnh ở mục 7.

## 10. Advice precedence không phải thứ tự khởi tạo Spring beans

Dễ nhầm hai khái niệm:

| Câu hỏi | Cơ chế cần xét |
| --- | --- |
| Aspect nào chạy trước trên đường vào `TransferService.transfer()`? | `@Order` / `Ordered.getOrder()` và advisor ordering |
| Singleton bean A có được khởi tạo trước singleton B không? | Dependency injection graph, `@DependsOn` hoặc lifecycle infrastructure |
| Spring inject nhiều beans vào `List<Service>` theo thứ tự nào? | Quy tắc dependency ordering/annotations ở injection point |
| Advice nào chạy sau khi target trả về? | Chiều ra của interceptor chain và advice type |
| Controller nào xử lý request trước? | Web routing/handler mapping và cấu hình web, không phải `@Order` trên aspect |
| Một async job chạy trước job khác không? | Executor/scheduling/concurrency, không được bảo đảm bằng aspect precedence |

Ví dụ, `@Order(1)` trên aspect không bắt buộc Spring phải tạo bean aspect trước tất cả các service, và cũng không đảm bảo một event handler nghiệp vụ khác sẽ chạy theo order ấy.

Nếu muốn việc đăng ký advisor xảy ra đúng và ổn định, hãy đảm bảo aspect được Spring quản lý, auto-proxy được bật, và configuration được tải đầy đủ. Không dùng `@DependsOn` để “vá” thứ tự advice giữa các aspect khi vấn đề thật là precedence.

## 11. Kết hợp với transaction, cache và security advisors

Trong ứng dụng thực tế, Spring AOP proxy có thể mang cả:

- Custom aspect của bạn: audit, tracing, metrics, validation.
- Infrastructure advisors: declarative transactions, caching, method security và các cơ chế khác.
- Proxy/interceptor do framework integration hoặc code dùng `ProxyFactory` tạo ra.

Khi đặt `@Order(10)` trên `AuditAspect`, bạn **đã** mô tả precedence **của aspect ấy**. Nhưng chưa chứng minh được thứ tự cuối cùng giữa audit và **mọi** advisor transaction/cache/security trong hệ thống.

### 11.1. Ví dụ với transaction

Giả sử:

~~~text
Caller
  -> Audit @Around
      -> Transaction interceptor
          -> TransferService.transfer()
          -> commit/rollback
      -> audit exit
~~~

Ở cấu trúc này audit exit diễn ra sau khi transaction interceptor bên trong hoàn tất xử lý commit/rollback. Nhưng nếu thứ tự đảo:

~~~text
Caller
  -> Transaction interceptor
      -> Audit @Around
          -> TransferService.transfer()
      -> transaction commit/rollback
~~~

thì audit exit có thể xảy ra **trước** commit/rollback.

Hệ quả:

- Nếu audit đang log “transaction committed” chỉ vì target trả bình thường, nội dung log có thể sai khi audit nằm **bên trong** transaction advisor và commit xảy ra sau đó.
- Nếu timing aspect cần tính cả commit time, vị trí bên ngoài transaction interceptor có thể quan trọng.
- Nếu caching aspect shortcut phía ngoài, audit/transaction advisor ở trong có thể không được vào.
- Khi lỗi của target được inner transaction advisor xử lý/đổi exception, outer advice có thể quan sát kết quả khác với việc gọi target trực tiếp.

**Không đoán ordering** chỉ từ annotation trong source: xem cấu hình transaction/cache advisors và kiểm thử actual Spring context.

### 11.2. Giá trị mặc định của infrastructure advisors

Các infrastructure components có thể sử dụng `Ordered.LOWEST_PRECEDENCE` hoặc configurable order values, nhưng giá trị cụ thể có thể phụ thuộc annotation/configuration và phiên bản Spring. Ví dụ, `@EnableTransactionManagement(order = ...)` có thuộc tính order để điều chỉnh transaction advisor trong proxy mode.

Đừng tùy tiện đặt tất cả aspects thành `HIGHEST_PRECEDENCE`: một số cơ chế infrastructure như async, validation, transactions hoặc security có các ràng buộc ordering đặc thù. Cần đưa ra **mong đợi nghiệp vụ rõ ràng**, cấu hình chính xác, rồi kiểm thử.

## 12. Điểm giới hạn: chỉ aspect cùng thực sự vào lời gọi mới được sắp xếp

`@Order` không làm advice chạy khi những điều kiện AOP cơ bản không thỏa.

### 12.1. Pointcut không match

Nếu AuditAspect chỉ match `TransferService.transfer(..)` còn MetricsAspect chỉ match `PaymentService.pay(..)`, hai aspect **không cùng tác động** lên một invocation. So sánh 10 và 20 lúc đó không tạo ra trace lồng nhau cho một method đơn lẻ.

### 12.2. Aspect chưa là Spring bean

~~~java
@Aspect
@Order(1)
public class AuditAspect {
    // ...
}
~~~

Chỉ annotation trên class không tự đưa instance vào Spring container. Cần `@Component` trong component scanning hoặc `@Bean` (như project mục 7), cùng cấu hình Spring AOP phù hợp.

### 12.3. Self-invocation và target ngoài container

~~~java
public void outer() {
    this.transfer(false);
}
~~~

Nếu invocation bên ngoài nhắm `outer()`, còn `this.transfer(false)` là lời gọi nội bộ trên target, Spring AOP proxy **không được đi qua lần hai**. Order values không thể cứu self-invocation. Điều này vẫn đúng với JDK dynamic proxy hoặc CGLIB class-based proxy.

Tương tự, `new TransferService().transfer(false)` ở ngoài Spring container không tự chịu AOP advice của các Spring-managed aspects.

### 12.4. Around advice short-circuit

Một aspect có precedence cao hơn có thể dùng `@Around` và **không gọi `proceed()`**, ví dụ khi cache hit hoặc policy từ chối lời gọi. Lúc đó inner aspect và target có thể không chạy dù đã được gán order thấp hơn.

~~~java
// Snippet minh họa, không thuộc project chạy độc lập ở mục 7.
@Around("execution(* example.TransferService.transfer(..))")
public Object shortCircuit(ProceedingJoinPoint pjp) {
    return "CACHED";
}
~~~

Không được suy rằng “aspect B(20) luôn chạy sau A(10)” nếu A(10) đã trả về mà không proceed; B không hề được vào invocation ấy.

### 12.5. Nested proxies và @Order

Nếu lập trình viên **tự bọc một AOP proxy trong một AOP proxy khác** bằng `ProxyFactory`, đó là hai tầng vật lý. `@Order` chỉ sắp xếp các advisors ở nơi Spring quản lý chuỗi thích hợp; nó không tự đảo việc một target source của outer đang trỏ tới inner proxy. Phải xác định client đang giữ proxy nào, rồi đọc advisor chain và target source thực tế.

## 13. Kiểm tra advisor chain qua API của Spring

Trong những bean expose `Advised`, bạn có thể xem danh sách advisors ở **lớp proxy hiện tại**:

~~~java
// Đoạn bổ sung cho Main.java mục 7; không phải chương trình độc lập.
import org.springframework.aop.Advisor;
import org.springframework.aop.framework.Advised;

if (service instanceof Advised advised) {
    int position = 0;
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(position++ + ": "
            + advisor.getClass().getSimpleName());
    }
}
~~~

Các lưu ý:

- Đây là cách inspect runtime, **không dùng output class names làm hợp đồng business**; Spring version có thể thay đổi classes/metadata.
- `Advised.getAdvisors()` liệt kê advisor ở **proxy đang xét**, không nhất thiết các advisors của một inner proxy khác.
- Một Spring AOP proxy có thể chứa advisor đặc biệt hoặc infrastructure advisor khác.
- Dòng đầu tiên trong danh sách không phải lúc nào cũng là một `@Aspect` business advice.
- `AopUtils.isAopProxy(service) == true` không chứng minh method bất kỳ đều match một advisor.
- Một proxy có thể được cấu hình opaque và không expose `Advised`; dùng `instanceof` kiểm tra trước khi cast.
- Không sửa `Advised` hay target source của production proxy chỉ để xem thứ tự.

**Test có giá trị hơn đoán:** Dùng một Spring ApplicationContext thực, gọi method qua bean reference, ghi sự kiện vào một danh sách thread-safe/test sink, và assert chuỗi events trên normal/exceptional paths.

## 14. Kiểm thử precedence và sự ổn định khi nâng cấp Spring

### 14.1. Ma trận kiểm thử

| Trường hợp | Mong đợi |
| --- | --- |
| Hai aspects cùng match, A(10), B(20), target thành công | A enter → B enter → target → B exit → A exit |
| Hai aspects cùng match, A(10), B(20), target ném lỗi | A enter → B enter → target throw → B finally → A finally → caller catch |
| Đổi A thành 30, B giữ 20 | B bao ngoài A |
| B pointcut không match target | Chỉ A advice chạy |
| A return sớm không proceed | B và target không nhất thiết được gọi |
| Hai aspects cùng order nhưng cần thứ tự cố định | **Không được dựa vào**; đặt giá trị khác |
| A và B cùng loại @Before trong **cùng aspect** | Thứ tự method không được bảo đảm chỉ bởi thứ tự khai báo |
| Caller gọi method bằng `this` từ target | Không tạo thêm invocation qua Spring proxy |
| Advisor transaction được thêm vào context | Cần xét actual chain, không giữ giả định chỉ có A và B |

### 14.2. Test không chỉ dựa vào stdout

Trong project bài học, stdout là cách dễ quan sát. Trong codebase lớn, bạn có thể đưa sự kiện vào một `List<String>` trong test-scoped sink rồi assert:

~~~java
// Snippet kiểm thử ý tưởng, cần cấu hình và test sink riêng.
assertEquals(
    List.of(
        "audit-enter", "metrics-enter", "target",
        "metrics-exit", "audit-exit"
    ),
    events
);
~~~

Với failure path, nhớ assert cả **kiểu exception và trạng thái nghiệp vụ**. Không dùng việc các log in đúng thứ tự để suy ra transaction đã commit đúng, security đã chạy đúng hoặc business operation không bị gọi hai lần.

### 14.3. Nên định nghĩa order theo một hợp đồng dễ đọc

Nếu nhiều nhóm phát triển cùng viết aspects, nên thống nhất dải order và lý do, ví dụ:

~~~java
public final class AspectOrder {
    private AspectOrder() {}

    public static final int AUDIT = 10;
    public static final int METRICS = 20;
}
~~~

Sau đó:

~~~java
@Aspect
@Order(AspectOrder.AUDIT)
public class AuditAspect {
    // ...
}
~~~

Đây là **snippet thiết kế**, không thuộc project độc lập ở mục 7. Một hằng giúp tránh “magic numbers” trùng ngẫu nhiên. Tuy nhiên, các dải order chỉ có giá trị khi được review cùng **infrastructure ordering**; không coi chúng là chuẩn mặc định của Spring.

## 15. Những lỗi thường gặp

| Hiện tượng | Cách hiểu sai | Cách xử lý đúng |
| --- | --- | --- |
| @Order(10) in log exit sau @Order(20) | @Order bị đảo | Precedence cao **ra sau**; mô hình wrapper bình thường |
| @Order(10) và Ordered(20) không có thứ tự mong đợi | Annotation và interface không tương thích | Chúng cùng mô tả precedence; kiểm tra pointcut, bean registration và actual chain |
| Có @Order nhưng advice không chạy | Ordering quyết định matching | Check @Aspect bean, proxy, pointcut và đường gọi |
| Dùng @Order trên các advice methods cùng @Aspect | Nghĩ sẽ sắp xếp theo từng method | Dùng quy tắc advice type, gộp method hoặc tách aspects có order riêng |
| Hai aspects cùng @Order(10) | Tưởng order bằng nhau vẫn theo tên class | Khi cần thứ tự xác định, dùng giá trị khác và test |
| Aspect có @Order(1), service vẫn init trước aspect | Tưởng @Order là startup order | Dependency graph/@DependsOn xử lý khởi tạo; không gắn với aspect precedence |
| Audit log “committed” nhưng transaction rollback sau | Quên thứ tự với transaction advisor | Xác minh audit nằm trong/ngoài transaction và commit event đúng |
| Metrics không xuất hiện dù target đã chạy | Pointcut không match hoặc reference gọi bỏ qua proxy | Kiểm tra target bean, pointcut, self-invocation và actual proxy |
| Target không chạy dù outer aspect in “enter” | Inner advisor hoặc outer around short-circuit | Tìm return sớm/không gọi proceed |
| CGLIB đã bật nhưng self-call vẫn không có advice | Tưởng class proxy can thiệp mọi lệnh gọi nội bộ | Spring AOP vẫn proxy-based; gọi qua bean khác khi cần |
| Đổi @Order lúc runtime mà chain không đổi | Cho rằng Spring sắp xếp lại mỗi invocation | Cấu hình ổn định trước khởi tạo proxy, sau đó tạo context mới/test |
| Có hai lần audit | Tưởng do @Order | Kiểm tra duplicate aspect beans, nested proxies, repeated calls và advisors |
| @Order âm bị hiểu là thấp ưu tiên | Nhầm ý nghĩa số lớn hơn | Số nhỏ hơn mới có precedence cao hơn |
| Advice order khác sau nâng cấp | Dựa vào internals/reflection order | Viết integration tests theo contract và ưu tiên nguồn docs phiên bản đang chạy |

## 16. Câu hỏi tự luyện tập

**Câu 1.** AuditAspect có `@Order(5)`, MetricsAspect có `getOrder() == 50`. Aspect nào được vào trước khi caller gọi method qua proxy và cả hai pointcut đều match?

**Đáp án:** AuditAspect có precedence cao hơn vì `5 < 50`, nên được vào trước. Nếu cả hai dùng around/finally, AuditAspect hoàn tất sau MetricsAspect.

**Câu 2.** Vì sao `@Order(5)` “vào trước nhưng ra sau” chứ không phải tất cả code chạy trước?

**Đáp án:** Vì aspect precedence cao bao ngoài chain phía trong. Lệnh `proceed()` chuyển vào các interceptor còn lại, rồi returning/exception đi ngược qua các wrapper.

**Câu 3.** Có hai `@Before` methods trong cùng một `@Aspect`, khai báo `first()` trước `second()`. Spring bảo đảm first chạy trước không?

**Đáp án:** Không. Thứ tự khai báo Java không đủ làm contract. Gộp vào một advice hoặc tách hai aspect classes có precedence khác nhau.

**Câu 4.** Hai aspect khác nhau cùng `@Order(10)`, nhưng trong một lần chạy A in trước B. Có thể ghi quy tắc này vào tài liệu hệ thống không?

**Đáp án:** Không nên. Khi precedence bằng nhau, không dựa vào thứ tự quan sát ngẫu nhiên nếu business cần ổn định; đặt hai order values khác nhau.

**Câu 5.** `@Order(1)` trên một aspect có ép Spring khởi tạo aspect bean trước tất cả service beans không?

**Đáp án:** Không. Advice precedence khác với bean lifecycle ordering. Xem dependency graph hoặc lifecycle/depends-on nếu cần thứ tự tạo bean.

**Câu 6.** Aspect A(10) dùng `@Around` trả về cached value mà không gọi `proceed()`. Aspect B(20) có chắc chạy không?

**Đáp án:** Không. Nếu A bao ngoài B và return sớm, invocation không tới B; order chỉ có ý nghĩa khi phần chain ấy thực sự được vào.

**Câu 7.** Custom audit aspect được đặt `@Order(0)`. Điều này có bảo đảm audit chạy sau commit của transaction không?

**Đáp án:** Không. Phải biết precedence và vị trí của transaction advisor tương ứng; nếu audit chạy bên trong transaction, audit exit có thể trước commit.

**Câu 8.** Nếu `@After` và `@AfterReturning` cùng xuất hiện trong một @Aspect, có thể dùng cách sắp xếp giữa hai aspect để khẳng định @After chạy trước @AfterReturning không?

**Đáp án:** Không. Đó là quy tắc trong cùng aspect, với after-finally semantics: `@After` thực tế chạy sau after-returning hoặc after-throwing tương ứng trên đường ra theo Spring Framework 6.2.

**Câu 9.** Một method được gọi bằng `this.method()` trong target bean. Thay `@Order(10)` thành `@Order(-10)` có làm advice chạy không?

**Đáp án:** Không. Self-invocation vẫn bypass Spring proxy; đổi precedence không sửa đường gọi.

**Câu 10.** Vì sao dùng cả `@Order` và `Ordered` trên cùng một aspect thường không nên?

**Đáp án:** Dễ xuất hiện hai nguồn cấu hình trái nhau. Chọn một convention rõ, tạo bean/config đúng, và test precedence trong context thực.

## 17. Nguồn tham khảo chính thức

- [Spring Framework — Declaring Advice / Advice Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): precedence giữa các aspects; dùng @Order hoặc Ordered; order thấp hơn là precedence cao hơn; quy tắc đi vào/đi ra; thứ tự advice types cùng aspect.
- [Spring Framework — Schema-based AOP / Advice Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/schema.html): các quy tắc tương tự khi dùng AOP XML và phân biệt advisor ordering.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): khai báo @Aspect thành Spring bean và bật @EnableAspectJAutoProxy.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation và ranh giới advice.
- [Spring Javadoc — Ordered](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/Ordered.html): getOrder, HIGHEST_PRECEDENCE và LOWEST_PRECEDENCE.
- [Spring Javadoc — @Order](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/annotation/Order.html): metadata precedence và phân biệt với singleton startup order.
- [Spring Framework — Transaction Management Configuration](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): order của transaction advisor và giới hạn proxy mode.
