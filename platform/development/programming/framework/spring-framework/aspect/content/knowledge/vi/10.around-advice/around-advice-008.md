# Đo thời gian thực thi mà không làm thay đổi kết quả nghiệp vụ trong Spring AOP

## 1. Vấn đề cần giải quyết

Bạn muốn biết một method nghiệp vụ mất bao nhiêu thời gian mà không phải chèn các câu lệnh đo vào từng service, đồng thời **không được thay đổi giá trị trả về, kiểu ngoại lệ hay số lần chạy phương thức**. Trong Spring AOP, một advice dạng `@Around` có thể bao quanh method execution trên Spring-managed bean, ghi dấu thời gian trước khi gọi `ProceedingJoinPoint.proceed()` và ghi nhận thời gian sau khi invocation kết thúc.

Mẫu cốt lõi:

~~~java
@Around("execution(public * example.TaskService.*(..))")
public Object measure(ProceedingJoinPoint pjp) throws Throwable {
    long startedAt = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsedNanos = System.nanoTime() - startedAt;
        // Ghi metrics ở đây, không thay đổi kết quả từ proceed().
    }
}
~~~

**Ba cam kết quan trọng:**

1. **Normal return:** giá trị mà chuỗi interceptor phía trong trả về được chuyển nguyên vẹn tới caller qua `return pjp.proceed()`.
2. **Exceptional exit:** exception từ chuỗi phía trong được truyền ra ngoài; `finally` chạy nhưng advice không tự chuyển exception thành kết quả “thành công”.
3. **Chỉ một invocation:** chỉ gọi `proceed()` **một lần**; không retry, không sửa arguments và không short-circuit nếu mục đích chỉ là đo thời gian.

Bài học chỉ tập trung vào **Spring Aspect và Spring AOP proxy-based**: cách triển khai `@Around`, ranh giới phép đo, metadata metrics và các giới hạn của Spring proxy. Những kiến thức Aspect tổng quát nằm ngoài phạm vi.

## 2. Vì sao `@Around` phù hợp cho bài toán đo thời gian?

Spring Framework mô tả around advice là loại advice có thể thực hiện logic **trước và sau** method execution, đồng thời giữ trạng thái cục bộ theo từng invocation an toàn hơn khi nhiều thread cùng gọi. Đo thời gian cần cùng một cặp mốc bắt đầu/kết thúc, nên `@Around` với biến `startedAt` cục bộ diễn đạt ý định rõ ràng.

| Cách viết | Đặc điểm | Phù hợp với đo duration? |
| --- | --- | --- |
| `@Before` đơn lẻ | Chạy trước invocation | Không có mốc kết thúc trong cùng advice |
| `@After` đơn lẻ | Chạy khi method thoát bình thường hoặc ném lỗi | Không có mốc bắt đầu trong cùng advice |
| Hai advice `@Before` + `@After` dùng field `long start` của singleton aspect | Field có thể bị ghi đè bởi các invocation/thread khác | **Không an toàn** cho nhiều lời gọi đồng thời |
| `@Around` với biến `long startedAt` cục bộ và `try/finally` | Giữ một cặp mốc thời gian theo invocation; ghi nhận cả success/failure | **Nên dùng** |
| `@Around` nhưng bỏ `proceed()` | Không chuyển lời gọi đến chuỗi phía trong | **Sai mục tiêu** nếu chỉ muốn quan sát |
| `@Around` nhưng bắt lỗi và trả giá trị mặc định | Che giấu lỗi nghiệp vụ | **Sai mục tiêu** nếu cần giữ nguyên kết quả |

**Lưu ý:** `@Around` có quyền thay đổi luồng gọi, nhưng trong bài toán đo thời gian thuần túy ta **cố ý không sử dụng** quyền đó. Quan sát là phụ; contract nghiệp vụ của method phải được giữ nguyên.

### 2.1. Sơ đồ thực thi

~~~text
Caller
   |
   v
Spring AOP proxy cho TaskService
   |
   +-- @Around bắt đầu: startedAt = System.nanoTime()
   |
   +-- pjp.proceed()
   |        |
   |        +-- những advisors/interceptors còn lại
   |        |
   |        +-- method target, nếu invocation đến được target
   |        |
   |        +-- trả result hoặc ném Throwable
   |
   +-- finally: elapsed = System.nanoTime() - startedAt
   |             ghi nhận metrics
   |
   v
Caller nhận đúng result hoặc Throwable của đường gọi được bao quanh
~~~

Cụm “đo thời gian thực thi” ở đây cần hiểu là **đo khoảng thời gian lời gọi đi qua đoạn chuỗi Spring AOP nằm bên trong advice**. Nó có thể gồm thời gian của advisor phía trong và target, không mặc nhiên bằng thời gian CPU thực tế chỉ chạy các câu lệnh của thân method.

## 3. Chọn đồng hồ: `System.nanoTime()`, không phải `currentTimeMillis()`

Khi cần đo **thời lượng**, sử dụng:

~~~java
long start = System.nanoTime();
// Gọi thao tác được đo.
long elapsedNanos = System.nanoTime() - start;
~~~

`System.nanoTime()` cung cấp nguồn thời gian phù hợp để đo **khoảng chênh lệch** (*elapsed time*). Mốc trả về là tùy ý, **không phải timestamp** có ý nghĩa lịch/giờ.

Phân biệt:

| API | Mục đích hợp lý | Không nên suy ra |
| --- | --- | --- |
| `System.nanoTime()` | Đo khoảng thời gian giữa hai mốc trong cùng JVM | Không suy ra thời điểm ngày/giờ, không bảo đảm độ chính xác đo đến từng nano-giây |
| `System.currentTimeMillis()` | Lấy thời gian lịch theo epoch millisecond | Không tối ưu để so độ dài vì clock hệ thống có thể bị điều chỉnh |
| `Instant.now()` | Timestamp phục vụ log sự kiện hoặc audit thời điểm | Không phải lựa chọn mặc định cho benchmark elapsed time |

**Đơn vị:** `elapsedNanos` có đơn vị nanosecond theo giá trị API; đổi sang mili-giây bằng:

~~~java
double elapsedMillis = elapsedNanos / 1_000_000.0;
~~~

Không nên làm tròn về số nguyên milli-second cho một method ngắn rồi kết luận “0 ms tức là không tốn thời gian”. Đồng hồ có độ phân giải hữu hạn, overhead của đo đạc/logging và JIT/GC/scheduling đều ảnh hưởng kết quả.

Phép trừ `System.nanoTime() - start` là cách Java khuyến nghị để đo khoảng thời gian ngắn; không so sánh trực tiếp giá trị nanoTime tuyệt đối với một timestamp khác. Không sử dụng cách này làm clock phân tán giữa các JVM hoặc các host.

## 4. Cấu trúc around advice bảo toàn nghiệp vụ

Mẫu đầy đủ ở dạng một class Spring AOP aspect (snippet; dự án chạy độc lập ở mục 6):

~~~java
package example;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TimingAspect {

    private final TimingMetrics metrics;

    public TimingAspect(TimingMetrics metrics) {
        this.metrics = metrics;
    }

    @Around("execution(public * example.TaskService.*(..))")
    public Object measure(ProceedingJoinPoint pjp) throws Throwable {
        String operation = pjp.getSignature().getName();
        long startedAt = System.nanoTime();

        try {
            return pjp.proceed();
        } finally {
            long elapsed = System.nanoTime() - startedAt;
            metrics.record(operation, elapsed);
        }
    }
}
~~~

Trong code này, `TimingMetrics` là một bean lưu số lần gọi và thời gian đo; định nghĩa chính thức nằm ở mục 6. Điểm quan trọng nằm ở **cấu trúc luồng gọi**:

- `@Around` kết nối Spring advice với **method execution** được pointcut chọn.
- Tham số đầu tiên là `ProceedingJoinPoint`.
- `Object` là kiểu trả về được khuyến nghị cho around advice dùng chung nhiều kiểu return.
- `throws Throwable` giúp truyền cả checked lẫn unchecked Throwable do invocation phía trong phát ra.
- `return pjp.proceed();` trả nguyên đối tượng kết quả, không `toString()`, không biến đổi, không wrap/cast.
- `finally` thực hiện ghi nhận trong cả **normal return** và **exceptional exit**.
- Không sửa `pjp.getArgs()`, không dùng `proceed(Object[])`, không gọi `proceed()` nhiều lần.
- `startedAt` và `operation` là biến cục bộ theo invocation nên không có race do cùng một field start-time trong singleton aspect.

**Giới hạn rất quan trọng:** `finally` bảo đảm code ghi nhận **được thử thực thi** trên hai nhánh, nhưng nếu `metrics.record(...)` tự ném exception, nó **có thể thay đổi hành vi mà caller thấy** — chẳng hạn biến một method thành công thành lỗi, hoặc che mất exception gốc. Muốn quan sát thật sự không làm thay đổi contract nghiệp vụ, phải thiết kế metrics sink đủ an toàn và đặt chính sách xử lý lỗi instrumentation rõ ràng (xem mục 8).

## 5. Ba mức “không thay đổi kết quả nghiệp vụ”

Cụm này thường bị hiểu quá hẹp thành “phương thức vẫn trả đúng chuỗi”. Trong Spring AOP có ít nhất ba lớp cần giữ:

### 5.1. Giữ nguyên return value và exception

~~~java
try {
    return pjp.proceed();
} finally {
    metrics.record(operation, System.nanoTime() - startedAt);
}
~~~

Trong trường hợp `metrics.record` hoàn tất bình thường:

- Nếu phần invocation bên trong trả `String "OK"`, caller nhận đúng `"OK"`.
- Nếu phần invocation bên trong trả về **cùng một object instance**, caller nhận chính instance đó; timing advice không tạo một wrapper kết quả mới.
- Nếu phần invocation bên trong ném `IllegalStateException("boom")`, caller nhận cùng exception theo luồng lan truyền thông thường; timing advice không chuyển nó thành `null` hoặc một result giả.
- Nếu target có return type `void`, lời gọi proceed ở tầng `Object` thường trả `null`; advice vẫn giữ semantic của method void.
- Nếu target trả primitive, Spring xử lý boxing/unboxing ở ranh giới thích hợp; lời advice không được trả `null` hoặc kiểu khác thay kết quả primitive.

### 5.2. Giữ nguyên arguments và số lần gọi

~~~java
Object result = pjp.proceed();
return result;
~~~

Đoạn này không thay thế arguments. Nếu gọi `pjp.proceed(modifiedArgs)`, bạn đang thay data của invocation. Nếu gọi `pjp.proceed()` **hai lần**, có thể target được thực thi hai lần và gây side effects. Hai cách đều không phù hợp khi yêu cầu chỉ quan sát.

### 5.3. Không biến metrics thành tác dụng phụ đáng kể

Một advice chỉ “đo” nhưng ghi log đồng bộ lên console, gọi mạng trong mỗi request, ném exception khi exporter lỗi, log toàn bộ arguments hoặc gắn thread state sai cũng có thể ảnh hưởng hành vi vận hành. Do đó:

- Không gửi dữ liệu nhạy cảm vào labels/logs.
- Không dùng metrics backend có thể ném lỗi tùy ý lên caller nếu business cần độc lập với observability.
- Không giữ mutable start-time field dùng chung trên aspect singleton.
- Tránh high-cardinality labels từ user ID, full URL, email, request payload.
- Hạn chế blocking I/O trên hot path.
- Có metrics counter/timer phù hợp với mức độ chính xác cần thiết, không tự suy đoán từ một vài lần đo.

## 6. Ví dụ Java 17+ hoàn chỉnh: đo ba lời gọi và giữ nguyên kết quả

Ví dụ dưới đây có thể chạy trong **Spring Framework 6.2.19**, Java **17+**, Maven, AspectJ Weaver **1.9.25.1**. Đây là một dự án độc lập (không cần Spring Boot, web server, database hoặc test container).

Ba đường gọi cần quan sát:

1. `taskService.greet("Lan")` trả `"Hello Lan"` bình thường.
2. `taskService.fail()` ném `IllegalStateException("boom")`; metrics vẫn nhận một sample.
3. `taskService.callInternally()` gọi `this.greet("Self")`; Spring AOP đo **lời gọi ngoài `callInternally`** nhưng không có sample riêng cho `greet` bên trong do self-invocation.

Để stdout có thể kiểm chứng, project **lưu giá trị nano-giây thật** nhưng chỉ in **nhãn sự kiện** và số lượng samples. Giá trị số nano-giây được lưu trong registry và khác nhau ở mỗi lần chạy, nên không bịa ra một con số duration cố định.

### 6.1. Cấu trúc thư mục

~~~text
spring-aop-timing/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── TaskService.java
    ├── TimingMetrics.java
    ├── TimingAspect.java
    └── Main.java
~~~

### 6.2. Maven: `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-timing</artifactId>
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

Spring Framework BOM giúp những dependency `spring-*` tương thích phiên bản. Project Spring Boot thực tế nên để Boot BOM hoặc starter quản lý dependency, không sao chép version của demo một cách máy móc.

### 6.3. `TaskService.java`

~~~java
package example;

public class TaskService {

    public String greet(String name) {
        System.out.println("target: greet " + name);
        return "Hello " + name;
    }

    public void fail() {
        System.out.println("target: fail");
        throw new IllegalStateException("boom");
    }

    public String callInternally() {
        System.out.println("target: callInternally");
        return this.greet("Self");
    }
}
~~~

`TaskService` là target Spring bean; không có logic đo thời gian trong service. `greet` và `fail` để kiểm tra normal/exception flows; `callInternally` thể hiện giới hạn self-invocation Spring AOP.

### 6.4. `TimingMetrics.java` — lưu duration và sample count an toàn cho concurrency

~~~java
package example;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.LongAdder;

public final class TimingMetrics {

    private final ConcurrentMap<String, LongAdder> counts =
        new ConcurrentHashMap<>();

    private final ConcurrentMap<String, LongAdder> totalNanos =
        new ConcurrentHashMap<>();

    public void record(String operation, long elapsedNanos) {
        counts.computeIfAbsent(operation, key -> new LongAdder()).increment();
        totalNanos.computeIfAbsent(operation, key -> new LongAdder())
            .add(elapsedNanos);

        // Chỉ in nhãn để ví dụ có stdout ổn định.
        System.out.println("metric: " + operation + " recorded");
    }

    public long count(String operation) {
        LongAdder value = counts.get(operation);
        return value == null ? 0L : value.sum();
    }

    public long totalNanos(String operation) {
        LongAdder value = totalNanos.get(operation);
        return value == null ? 0L : value.sum();
    }
}
~~~

**Lý do thiết kế:**

- `LongAdder` phù hợp để tích lũy counters/tổng thời gian trong các thao tác concurrent đơn giản; tránh một mutable `long` bị race khi nhiều thread ghi.
- `ConcurrentHashMap` cho phép sử dụng đồng thời nhiều operation names.
- `record` chỉ được gọi từ timing aspect khi invocation đi tới nhánh finally.
- `totalNanos(operation)` giữ **giá trị số thật** của tổng duration; in số này ra console sẽ khác nhau giữa các lần chạy.
- Đây là instrumentation toy registry: việc cập nhật **hai map độc lập không phải một transaction nguyên tử**. Nếu cần snapshot count và duration đồng thời nhất quán hoặc histogram/percentiles chính xác, dùng thư viện observability/metrics chuyên dụng.
- Hàm `record` in log để minh họa; **production không nên System.out.println ở mọi invocation**, nhất là hot path.
- Một out-of-memory error hoặc exception hiếm trong chính metrics subsystem vẫn có thể làm sai contract; bài này dùng sink in-memory nhỏ để minh họa trường hợp thành công bình thường, không hứa “không thể xảy ra lỗi instrumentation”.

### 6.5. `TimingAspect.java` — chỉ đo, không chỉnh business result

~~~java
package example;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TimingAspect {

    private final TimingMetrics metrics;

    public TimingAspect(TimingMetrics metrics) {
        this.metrics = metrics;
    }

    @Around("execution(public * example.TaskService.*(..))")
    public Object measure(ProceedingJoinPoint pjp) throws Throwable {
        String operation = pjp.getSignature().getName();
        long startedAt = System.nanoTime();

        try {
            return pjp.proceed();
        } finally {
            long elapsedNanos = System.nanoTime() - startedAt;
            metrics.record(operation, elapsedNanos);
        }
    }
}
~~~

Ở đây:

- `@Aspect` đánh dấu class có Spring AOP advice; nó **không tự khiến class thành Spring bean**.
- `@Around` chọn các **public method executions** thuộc `example.TaskService`, bao gồm `greet`, `fail`, `callInternally`.
- `pjp.proceed()` được gọi đúng **một lần**.
- `return` chuyển nguyên kết quả của chain phía trong về caller.
- Không catch exception, không tạo exception mới, không đổi arguments hoặc target.
- `finally` ghi nhận metric ở cả hai nhánh thoát của invocation **đã đi vào advice**.
- `operation` chỉ là method name cố định của class, không chứa arguments hay nội dung nhạy cảm. Với nhiều service hoặc overloaded methods cần tên được chuẩn hóa rõ hơn để tránh gộp nhầm các phép đo.

**Ranh giới đo:** Mốc kết thúc được lấy **trước** lệnh `metrics.record`, nên duration không gồm chi phí ghi metric của chính advice. Nó vẫn có thể gồm thời gian của những interceptors nằm **bên trong** advice và công việc target.

### 6.6. `AppConfig.java`

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public TaskService taskService() {
        return new TaskService();
    }

    @Bean
    public TimingMetrics timingMetrics() {
        return new TimingMetrics();
    }

    @Bean
    public TimingAspect timingAspect(TimingMetrics timingMetrics) {
        return new TimingAspect(timingMetrics);
    }
}
~~~

Spring Framework thuần cần kích hoạt `@EnableAspectJAutoProxy` và có thư viện AspectJ cần thiết trên classpath. `TimingAspect` được đăng ký **qua `@Bean`**, không cần thêm `@Component`. Target được Spring đăng ký và nhận proxy khi có advisor match.

`proxyTargetClass = true` ép class-based proxy để chương trình có thể lấy bean theo `TaskService.class`. CGLIB được chọn vì thuận tiện demo; nó **không làm self-invocation chạy timing advice**.

### 6.7. `Main.java`

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            TaskService task = context.getBean(TaskService.class);
            TimingMetrics metrics = context.getBean(TimingMetrics.class);

            System.out.println("spring AOP proxy: " + AopUtils.isAopProxy(task));

            System.out.println("-- success --");
            System.out.println("caller: " + task.greet("Lan"));

            System.out.println("-- exception --");
            try {
                task.fail();
            } catch (IllegalStateException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }

            System.out.println("-- self invocation --");
            System.out.println("caller: " + task.callInternally());

            System.out.println("count greet: " + metrics.count("greet"));
            System.out.println("count fail: " + metrics.count("fail"));
            System.out.println("count callInternally: "
                + metrics.count("callInternally"));
            System.out.println("total samples: "
                + (metrics.count("greet") + metrics.count("fail")
                   + metrics.count("callInternally")));
        }
    }
}
~~~

Chạy tại thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

### 6.8. Stdout xác định được từ code

~~~text
spring AOP proxy: true
-- success --
target: greet Lan
metric: greet recorded
caller: Hello Lan
-- exception --
target: fail
metric: fail recorded
caller caught: boom
-- self invocation --
target: callInternally
target: greet Self
metric: callInternally recorded
caller: Hello Self
count greet: 1
count fail: 1
count callInternally: 1
total samples: 3
~~~

**Vì sao không in duration cố định?** Giá trị `System.nanoTime()` phụ thuộc môi trường chạy, JIT, GC, scheduling, trạng thái CPU và các tầng interceptor; không thể dự đoán chính xác. Giá trị thật được lưu trong `TimingMetrics.totalNanos("greet")` v.v., người học có thể tự in chúng khi chạy để quan sát.

### 6.9. Giải thích ba đường gọi

**Lời gọi thành công:**

1. Caller gọi `task.greet("Lan")` qua Spring AOP proxy.
2. Timing aspect ghi `startedAt` rồi `proceed()`.
3. Target in `target: greet Lan` và trả `"Hello Lan"`.
4. Finally đo elapsed, gọi `metrics.record("greet", ...)` và in nhãn metric.
5. Caller nhận đúng `"Hello Lan"`: timing advice **không sửa return value**.

**Lời gọi ném exception:**

1. Proxy vào timing aspect và sau đó chạy target `fail()`.
2. Target ném `IllegalStateException("boom")`.
3. `finally` vẫn ghi một sample `fail`.
4. Cùng exception tiếp tục đi tới caller và được bắt ở `Main`.
5. Timing aspect **không biến lỗi thành một giá trị mặc định**, nên hành vi lỗi nghiệp vụ được giữ nguyên.

**Self-invocation:**

1. Caller gọi `task.callInternally()` qua proxy, nên timing aspect bắt đầu một phép đo cho method **callInternally**.
2. Bên trong target, code gọi `this.greet("Self")` — **không đi qua proxy lần hai**.
3. Do vậy không có dòng `metric: greet recorded` thứ hai; chỉ có `metric: callInternally recorded`.
4. Caller nhận `"Hello Self"` như bản thân business method trả về. Sau ba lời gọi ngoài, count `greet=1`, `fail=1`, `callInternally=1`.

Điểm mấu chốt: **một lời gọi nội bộ vẫn tiêu tốn thời gian thực thi**, nhưng vì không tạo thêm một invocation qua proxy cho method con, nó **không sinh thêm một timing sample riêng** theo pointcut.

## 7. Đo thời gian thành công và thất bại mà không đổi exception

Có hai cách thường thấy.

### 7.1. `try/finally` — đo cả hai nhánh, không phân biệt outcome

~~~java
long start = System.nanoTime();
try {
    return pjp.proceed();
} finally {
    metrics.record(operation, System.nanoTime() - start);
}
~~~

Đơn giản, phù hợp khi chỉ cần **duration và số lượt method đã đi qua advice**, không cần nhãn success/failure. Với ví dụ, case `fail()` có một sample dù target ném exception.

### 7.2. `try/catch/finally` — nếu metrics còn cần trạng thái kết quả

~~~java
// Snippet bổ sung; metrics.record là API minh họa, không phải project mục 6.
long started = System.nanoTime();
boolean failed = false;
try {
    return pjp.proceed();
} catch (Throwable error) {
    failed = true;
    throw error;
} finally {
    recordOutcome(operation, System.nanoTime() - started, failed);
}
~~~

Trong snippet, `recordOutcome(...)` là hàm giả định của metrics subsystem (cần được định nghĩa riêng). Đây **không phải mã độc lập** để sao chép và chạy ngay. Nó minh họa nguyên tắc:

- Nếu `proceed()` ném `Throwable` thì gắn outcome=failed.
- **Rethrow chính Throwable đó**, không tạo exception khác nếu mục tiêu là preserve behavior.
- `finally` vẫn chạy một lần.
- Tránh log toàn bộ exception message hoặc arguments, vì có thể chứa dữ liệu nhạy cảm.

**Sắc thái:** Nếu target tự bắt exception và return bình thường thì từ góc nhìn outer proxy, `proceed()` trả bình thường: state “failed” trong snippet là `false`. Nếu một interceptor ở trong bắt exception rồi trả fallback thì outer cũng quan sát fallback (không biết lỗi phía trong đã được xử lý). Muốn phân biệt cấp độ nghiệp vụ cần một hợp đồng trạng thái riêng chứ không suy từ Throwable duy nhất.

## 8. Tránh lỗi instrumentation làm thay đổi nghiệp vụ

Mặc dù `return pjp.proceed()` và `finally` đúng về luồng, **code đo/ghi metric cũng là Java code**, có thể gây lỗi hoặc blocking. Ví dụ:

~~~java
finally {
    metricsBackend.sendHttp(elapsedNanos); // Có thể timeout hoặc throw!
}
~~~

Nếu backend metrics ném exception, caller có thể thấy lỗi instrumentation thay vì kết quả/exception của target. Để giữ nghiệp vụ độc lập, có thể sử dụng **best-effort instrumentation** với một sink được thiết kế non-throwing, đo đạc rõ ràng và đường ghi có backpressure/timeout phù hợp.

Snippet minh họa cho lỗi thông thường:

~~~java
finally {
    long elapsed = System.nanoTime() - startedAt;
    try {
        metrics.record(operation, elapsed);
    } catch (RuntimeException instrumentationFailure) {
        // Best effort: báo lỗi bằng kênh an toàn, không làm hỏng nghiệp vụ.
        // Không log vô hạn hoặc truy xuất mạng đồng bộ ở đây.
    }
}
~~~

**Lưu ý thật rõ:**

- Đoạn trên **cố ý không nuốt Throwable từ `proceed()`**; nó chỉ xử lý lỗi của phần metrics trong `finally`.
- Một `Error` nghiêm trọng như OutOfMemoryError hoặc JVM termination không thể được hứa sẽ xử lý “an toàn tuyệt đối” bằng một `catch(RuntimeException)`.
- Empty catch không nên được sao chép vào production mà thiếu chính sách observability; cần một kênh giám sát không làm hỏng luồng nghiệp vụ, nhưng không tái tạo lỗi vào caller.
- Sử dụng metric recording nhanh, thread-safe và ít side effects. Với Java service thật nên cân nhắc **Micrometer Observation/Timer** hoặc SDK observability của hệ thống, thay vì tự làm bộ đếm in-memory cho production.
- Việc in log ngay trong `record()` của ví dụ nhỏ là để giúp học cơ chế; không phải thiết kế hiệu năng cho endpoint thường xuyên được gọi.

Như vậy “không làm thay đổi kết quả nghiệp vụ” là **một mục tiêu thiết kế có điều kiện**, không phải điều được `@Around` tự động bảo đảm trong mọi tình huống.

## 9. Dữ liệu nào nên gắn vào metric?

Các label gợi ý:

| Label | Ví dụ | Đánh giá |
| --- | --- | --- |
| Operation name cố định | `TaskService.greet` | Thường phù hợp, cardinality hữu hạn |
| Outcome | `success` / `failure` | Phù hợp nếu xác định rõ tại proxy boundary |
| Service/module | `payment`, `checkout` | Phù hợp với tập giá trị hữu hạn |
| Exception type | `IllegalStateException` | Có thể cân nhắc, nhưng kiểm soát cardinality |
| User email hoặc request payload | `user@example.com`, JSON body | **Không đưa vào metrics label** |
| Customer ID, order ID, full dynamic URL | Giá trị duy nhất mỗi request | Tránh high cardinality, nguy cơ lộ dữ liệu |
| Raw argument có thông tin bí mật | Token/password/API key | **Không log hoặc gắn metrics** |

Trong Spring Aspect, `pjp.getSignature().getName()` là cách đơn giản lấy tên method, nhưng method overload cùng tên sẽ chia sẻ một label. Trong production, bạn có thể chuẩn hóa key theo **class/method được allowlist** hoặc annotation nghiệp vụ riêng, thay vì nối `pjp.getArgs()` hoặc `toString()` của object đầu vào.

**Không sử dụng full arguments để “phân biệt” mỗi metric sample**: điều đó làm cardinality nở theo số request, gây quá tải metric backend và có thể tiết lộ dữ liệu.

## 10. Đặt pointcut đủ hẹp, tránh đo cả hạ tầng Spring

Trong ví dụ, pointcut là:

~~~java
@Around("execution(public * example.TaskService.*(..))")
~~~

Nó giới hạn vào các public method executions của class `TaskService`, không match mọi bean trong context. Một expression quá rộng như:

~~~java
@Around("execution(* *(..))")
~~~

có thể làm Spring xét/match rất nhiều target methods không thuộc nhu cầu profiling, thêm proxy hoặc overhead ngoài ý muốn. Trong app lớn, nó còn khiến log/metrics bị trộn giữa nghiệp vụ và infrastructure.

Một số cách xây scope rõ hơn:

~~~java
// Snippet trong một Spring-managed @Aspect:
@Around(
    "within(com.acme.payment.service..*)"
    + " && execution(public * *(..))"
)
public Object timePaymentService(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        recordPaymentLatency(System.nanoTime() - started);
    }
}
~~~

Trong snippet này, `recordPaymentLatency` là method minh họa cần định nghĩa ở class aspect; đoạn code **không phải project độc lập**.

Nếu chỉ một số method được đánh dấu rõ, có thể dùng một custom annotation opt-in:

~~~java
@Around("@annotation(com.acme.metrics.TimedOperation)")
~~~

Đây chỉ là biểu thức annotation placeholder cho một annotation type do dự án tự định nghĩa (cần `@Target(METHOD)`, `@Retention(RUNTIME)`). Khi dùng JDK proxy hoặc annotation trên interface/implementation, cần **test match thực tế** trong Spring AOP context; đừng dựa vào tên annotation ở source mà suy ra tự động match trong mọi chiến lược proxy.

**Quy tắc:** Chọn cả positive targets và negative targets. Một test chỉ xác nhận “TaskService.greet được đo” chưa chứng minh không có bean khác bị đo nhầm.

## 11. Đo thời gian ở vị trí nào trong chuỗi advisor?

Một Spring-managed bean có thể chịu nhiều advisors:

~~~text
Client
 -> [Timing @Around advisor]
     -> [Transaction interceptor]
         -> [Cache / Security / Other interceptors]
             -> TargetService.method()
~~~

Nếu timing advice ở **ngoài** transaction interceptor, khoảng thời gian measured có thể bao gồm cả thời gian begin/commit/rollback được thực hiện **trong** transaction interceptor, tùy advisor order.

Nếu timing advice ở **trong** transaction interceptor:

~~~text
Client
 -> [Transaction interceptor]
     -> [Timing @Around advisor]
         -> TargetService.method()
~~~

thì phép đo có thể **không bao gồm** một số chi phí mở/đóng transaction ở ngoài advice. Vì vậy cùng một service có thể có “method duration” và “transaction-inclusive duration” khác nhau, không phải vì hệ đo bị hỏng.

### 11.1. `@Order`

Spring AOP cho phép sắp xếp aspect bằng `@Order` hoặc `Ordered`:

~~~java
@Aspect
@Order(10)
public class TimingAspect {
    // ...
}
~~~

Đây là snippet, cần import `org.springframework.core.annotation.Order` và class body hợp lệ. Số order **nhỏ hơn** có precedence cao hơn đối với aspects; trên đường đi vào, aspect precedence cao hơn chạy trước, và trên đường quay ra nó chạy sau.

Tuy vậy, thứ tự với infrastructure advisors như `@Transactional`, `@Cacheable` còn phụ thuộc cấu hình Spring thực tế. Không giả định `@Order(10)` có nghĩa “luôn đo cả transaction” trong mọi context. Hãy ghi rõ định nghĩa latency, sau đó xác minh advisor chain và hành vi qua integration test.

### 11.2. Đo thời gian thực thi target hay đo latency caller quan sát?

Cần phân biệt:

- **Target body duration:** lý tưởng chỉ tính thời gian trong code nghiệp vụ.
- **Inner chain duration:** tính target cùng một số interceptor phía trong timing advice.
- **End-to-end request latency:** có thể gồm HTTP routing, authentication, serialization, network waits và hàng đợi không thuộc phạm vi method advice.
- **Async completion latency:** tính đến lúc future/publisher/task thật sự hoàn thành.

`System.nanoTime()` quanh `pjp.proceed()` trên Spring AOP đo **một lời gọi method theo ranh giới proxy**, không tự đại diện cho tất cả bốn chỉ số. Nên đặt tên metric phản ánh đúng phạm vi đo để tránh diễn giải sai dashboard.

## 12. Spring AOP proxy boundaries: trường hợp không được đo riêng

### 12.1. Self-invocation qua `this`

~~~java
public String outer() {
    return this.inner();
}
~~~

Nếu caller gọi `outer()` trên Spring proxy, timing aspect có thể đo lời gọi `outer`. Nhưng trong target, `this.inner()` **không đi qua proxy lần nữa**, nên `inner` không tự có một timing sample riêng. Ví dụ mục 6 cho thấy rõ điều này qua `callInternally()`.

CGLIB **không chữa** self-invocation theo cơ chế Spring AOP proxy-based. Nếu phải đo riêng `inner`, một cách thông dụng là tách nó sang **Spring bean khác** và gọi qua Spring-injected proxy; cần kiểm tra pointcut match đúng bean mới.

### 12.2. Tự `new` instance ngoài Spring

~~~java
TaskService service = new TaskService();
service.greet("Lan");
~~~

Method nghiệp vụ vẫn chạy, nhưng đối tượng này không phải bean proxy mà Spring AOP tạo. Timing advice trên Spring context **không tự áp dụng** lên object tự new ngoài container.

### 12.3. Method không thể proxy hóa hoặc pointcut không match

- JDK dynamic proxy chủ yếu can thiệp các public method trên interfaces được proxy expose.
- Class-based CGLIB không thể override method `final` và không thể intercept `private` theo cơ chế subclass.
- Nếu pointcut chọn `TaskService.greet(..)`, các method khác không tự nhận metric chỉ vì bean đã có proxy.
- Bean có AOP proxy từ transaction/cache/advisor khác **không đồng nghĩa** timing advice đang match.

### 12.4. Inner interceptor short-circuit

Một `@Around`/cache interceptor nằm **bên trong** timing advice có thể trả kết quả mà không gọi target. Timing aspect vẫn có thể ghi một sample cho **interceptor-chain latency**, vì `proceed()` đã đi tới inner interceptor và trả về. Điều đó **không chứng minh target đã thực thi**.

Nếu timing advice nằm **bên trong** interceptor shortcut và inner timing layer chưa được đi vào, **không có sample**. Đây là lý do phải hiểu advisor order khi định nghĩa metric.

## 13. Method bất đồng bộ và reactive: duration nào được ghi nhận?

Một method Spring bean có thể trả về `CompletableFuture<T>`, `Future<T>`, `Mono<T>` hoặc `Flux<T>`. Đặc biệt:

~~~java
public CompletableFuture<String> startJob() {
    return CompletableFuture.supplyAsync(() -> performBusinessJob());
}
~~~

Đây là snippet minh họa, giả định `performBusinessJob()` tồn tại. Với một method trả CompletableFuture **nhanh**, `pjp.proceed()` có thể trả về **future object** trước khi job thực sự hoàn tất; `finally` trong `@Around` lập tức ghi duration cho **thời gian method trả future**.

Tương tự, một method reactive trả về `Mono`/`Flux` có thể chỉ tạo publisher; công việc bắt đầu khi subscriber subscribe. Duration đo bằng `proceed()` **không tự bằng thời gian publisher hoàn tất**.

**Cần xác định đo cái gì:**

| Chỉ số mong muốn | Cách phù hợp |
| --- | --- |
| Thời gian method tạo/trả Future hoặc Publisher | `@Around` quanh `proceed()` |
| Thời gian cho đến Future hoàn thành | Hook hoàn tất như `whenComplete` hoặc công cụ instrumentation của async abstraction |
| Thời gian đến khi một reactive pipeline kết thúc/cancel | Operator lifecycle như Reactor `doFinally` trong pipeline phù hợp |
| Thời gian end-to-end của web request | HTTP/server observation thay vì chỉ method advice |

Không tự attach callbacks vào một Future rồi thay thế return object nếu hợp đồng business yêu cầu giữ chính object gốc; instrumentation phải xem xét identity và exception/timeout semantics. Với method `@Async` của Spring, advisor ordering và kiểu proxy cũng có thể làm metric scope khác với dự tính; cần kiểm thử trong context thật.

## 14. Ngưỡng hiệu năng, phân phối thời gian và độ chính xác

Đo thời gian một lần chưa đủ kết luận tối ưu hóa. Đặc biệt đối với code ngắn:

- JIT compilation, class loading và warm-up làm những lần đầu thường khác các lần sau.
- Garbage collection và OS scheduling ảnh hưởng wall-clock elapsed time.
- `System.nanoTime()` có overhead; precision được biểu diễn bằng nanoseconds nhưng resolution thực tế tùy nền tảng.
- Trong ứng dụng nhiều thread, mỗi invocation có state start/end riêng nhưng việc tổng hợp metrics vẫn có chi phí.
- Average không đủ cho tail latency; có thể cần p95/p99 hoặc histogram nếu yêu cầu SLO.
- Cache hit và cache miss có thể làm phân phối thời gian khác nhau đáng kể; nên có nhãn outcome hữu hạn và phân nhóm đúng ngữ nghĩa.
- Thời gian của transaction commit, remote I/O và queueing có thể nằm ngoài hoặc trong khoảng đo tùy vị trí advisor.

Với production, sử dụng thư viện được quản lý như **Micrometer Timer/Observation** phù hợp Spring Boot ecosystem sẽ hữu ích hơn tự triển khai nhiều aggregator. Nhưng nguyên tắc Spring AOP vẫn là: `@Around` mở mốc, `proceed()`, đo trong `finally`, và **không thay return/throw contract**.

## 15. Kiểm thử “không làm thay đổi nghiệp vụ”

Một bài test đầy đủ phải kiểm cả **kết quả nghiệp vụ** lẫn **số lượng samples**.

| Test case | Kỳ vọng nghiệp vụ | Kỳ vọng timing |
| --- | --- | --- |
| Caller gọi `task.greet("Lan")` qua proxy | Đúng chuỗi `"Hello Lan"` | `count("greet")` tăng một |
| Caller gọi `task.fail()` qua proxy | Exception `IllegalStateException("boom")` tiếp tục ném | `count("fail")` tăng một |
| Caller gọi `task.callInternally()` | Trả `"Hello Self"` | `count("callInternally")` tăng một; `count("greet")` **không** tăng thêm |
| Caller tạo `new TaskService()` và gọi `greet()` | Kết quả Java bình thường | Không ghi thêm vào metrics của Spring context |
| Một method khác không nằm trong pointcut | Kết quả nghiệp vụ bình thường | Không có timing sample cho method đó |
| Metrics sink báo lỗi | Kết quả mong muốn do chính sách instrumentation quyết định | Test xác minh lỗi không làm hỏng business theo policy đã định |
| Gọi concurrent | Mỗi lời gọi có kết quả đúng | Số samples bằng số invocation qua proxy; counter không lost updates |
| Method trả Future | Future object/behavior không bị đổi | Duration quanh `proceed()` không mặc nhiên đo đến async completion |

### 15.1. Assertions minh họa trong context

Sau khi tạo `AnnotationConfigApplicationContext` và lấy `TaskService` cùng `TimingMetrics` như mục 6, ta có thể kiểm tra:

~~~java
String result = task.greet("Mai");
if (!"Hello Mai".equals(result)) {
    throw new AssertionError("return value changed");
}
if (metrics.count("greet") != 1L) {
    throw new AssertionError("wrong timing sample count");
}
~~~

Đây là **snippet kiểm thử bổ sung**, không phải chương trình độc lập và không được trộn trực tiếp vào `Main.java` nếu bạn muốn giữ stdout ở mục 6. Với exception, dùng `try/catch` hoặc `assertThrows` trong JUnit; test cả exception type và message/identity khi contract yêu cầu.

**Không assert giá trị nano-giây chính xác**: duration là số đo runtime. Nếu cần kiểm tra phương pháp ghi metric hoàn toàn xác định, có thể inject một clock abstraction giả lập và một metrics sink in-memory cho test đơn vị, nhưng integration test vẫn nên chứng minh advice thực sự được Spring AOP áp dụng.

## 16. Những lỗi Spring AOP profiling phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Method trả `null` dù target vốn có kết quả | `@Around` quên `return pjp.proceed()` hoặc method advice khai báo `void` | Trả nguyên value từ proceed |
| Không thấy metric và target cũng không chạy | Around advice return sớm, không gọi proceed | Kiểm tra điều kiện shortcut, không dùng shortcut cho timing-only advice |
| Lỗi từ target bị biến thành giá trị mặc định | Around advice `catch` nhưng không rethrow | Rethrow original Throwable nếu cần preserve exception contract |
| Exception từ metrics thay thế exception gốc | `metrics.record` ném lỗi trong `finally` | Thiết kế sink best-effort và policy lỗi instrumentation |
| Thời gian của mọi thread trộn lẫn sai | Lưu `startTime` làm field mutable chung trên singleton aspect | Dùng local variable trong around advice |
| Count ghi hai lần cho một method | Gọi `proceed()` hai lần, đăng ký aspect trùng hoặc có nested proxies | Kiểm tra invocation/advisor chain và lần gọi thật |
| Target method chưa chạy nhưng vẫn có metric | Inner interceptor/cache short-circuit; timing advice đo chain | Xác định metric scope và advisor order |
| `this.method()` không có timing sample riêng | Spring AOP self-invocation bỏ qua proxy | Tách method thành bean khác và gọi qua DI nếu cần |
| Bean không được đo dù có `@Aspect` | Aspect chưa thành Spring bean, AOP chưa bật hoặc pointcut không khớp | Kiểm tra `@Bean`/`@Component`, `@EnableAspectJAutoProxy`/Boot auto-config |
| Value `elapsedMillis` in thành 0 | Ép số nguyên làm mất độ phân giải với operation ngắn | Lưu nano-giây, dùng phân số khi chuyển đơn vị |
| Stopwatch dùng `currentTimeMillis` đôi lúc có số âm/bất thường | Clock hệ thống bị điều chỉnh; không phù hợp làm elapsed timer | Dùng `System.nanoTime()` |
| Timing sau `proceed()` nhưng không trong `finally` | Exceptional exit làm bỏ qua record | Đặt record trong finally |
| Timing của async task quá ngắn | `proceed()` chỉ trả Future/Publisher | Đo completion bằng lifecycle callback phù hợp |
| Cardinality tăng không kiểm soát | Dùng user ID/request body làm metric label | Chuẩn hóa labels hữu hạn |
| Tăng latency nhiều sau khi thêm metric | Ghi log/I/O đồng bộ hoặc pointcut quá rộng | Giảm overhead, dùng metrics backend phù hợp và narrow pointcut |

## 17. Câu hỏi vận dụng

**Câu 1.** Vì sao đoạn `long start=System.nanoTime(); return pjp.proceed();` chưa đo hoàn chỉnh khi target có thể ném exception?

**Đáp án:** Chưa ghi nhận mốc kết thúc. Nếu ghi record bằng câu lệnh sau proceed mà không có finally, exceptional exit sẽ bỏ qua câu lệnh đó. Dùng `try/finally` để record cả hai nhánh.

**Câu 2.** Aspect timing trả `"OK"` bất kể `pjp.proceed()` trả gì. Có đáp ứng “không thay đổi kết quả nghiệp vụ” không?

**Đáp án:** Không. Nó thay return value của caller. Timing-only advice phải trả nguyên kết quả của proceed.

**Câu 3.** `pjp.proceed()` đã được gọi một lần, nhưng timing sample có thể xuất hiện khi target không chạy không?

**Đáp án:** Có. Một interceptor phía trong, chẳng hạn cache, có thể trả kết quả sớm. Timing đo khoảng thời gian chuỗi bên trong mà advice đi qua, không tự chứng minh target body đã chạy.

**Câu 4.** Trong singleton aspect, lưu `startTime` ở một field rồi @Before set, @After subtract. Cách này có an toàn concurrency không?

**Đáp án:** Không nếu field dùng chung cho nhiều invocation. Một thread có thể ghi đè start time của thread khác. Dùng biến cục bộ trong một @Around advice.

**Câu 5.** Target ném `IllegalStateException("boom")`; metrics record thành công trong finally. Caller có còn nhận exception không?

**Đáp án:** Có, nếu timing advice không catch/đổi exception. Finally record xong và exception gốc tiếp tục lan truyền.

**Câu 6.** `metrics.record(...)` ném RuntimeException trong finally sau khi target đã trả về bình thường. Caller có chắc chắn nhận kết quả không?

**Đáp án:** Không. Lỗi từ instrumentation có thể thay thế kết quả. Để giữ contract, metrics sink và chính sách xử lý lỗi phải tránh propagate lỗi đo đạc ngoài ý muốn.

**Câu 7.** `callInternally()` gọi `this.greet()` và được caller gọi qua Spring proxy. Timing có đếm riêng `greet` bên trong không?

**Đáp án:** Không. Self-invocation không tạo một lời gọi mới qua proxy cho greet, nên chỉ có sample của method ngoài nếu advisor match nó.

**Câu 8.** Có nên đo thời gian giữa hai lần `System.currentTimeMillis()` nếu yêu cầu độ ổn định của elapsed time không?

**Đáp án:** Nên dùng `System.nanoTime()` cho elapsed duration. Clock lịch có thể bị hiệu chỉnh và thường có độ phân giải thấp hơn.

**Câu 9.** Nếu advisor timing ở ngoài transaction interceptor, mẫu đo có thể gồm transaction commit không?

**Đáp án:** Có thể có, tùy các interceptor nằm bên trong timing advice. Muốn định nghĩa “method time” hay “transaction-inclusive time” thì phải kiểm tra advisor order và cách transaction thực sự thực thi.

**Câu 10.** Method trả `CompletableFuture`, timing finally đã chạy nhưng future còn pending. Có lỗi không?

**Đáp án:** Không. Nó đo thời điểm method trả Future, không nhất thiết là hoàn tất công việc async. Dùng completion instrumentation nếu cần latency của toàn bộ tác vụ.

## 18. Tài liệu chính thức và hướng tìm hiểu tiếp

- [Spring Framework 6.2 — Declaring Advice / Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): around advice dùng `ProceedingJoinPoint`, tiến hành `proceed()`, lưu state theo invocation và bảo toàn return value.
- [Spring Framework — An AOP Example](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/example.html): quanh method để ghi profiling và điều phối behavior.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): ranh giới Spring proxies, JDK/CGLIB và self-invocation.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): bật Spring AOP, yêu cầu aspect bean và classpath.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): giới hạn method execution để không tạo overhead ngoài phạm vi.
- [Oracle Java SE API — System.nanoTime()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): clock dùng đo elapsed time, mốc tùy ý, độ phân giải phụ thuộc nền tảng.
