# Kiểm tra số lượng instance aspect và trạng thái được chia sẻ trong Spring AOP

## 1. Mục tiêu

Khi một `@Aspect` được đăng ký làm Spring bean, những câu hỏi quan trọng khi chạy ứng dụng là:

- Trong `ApplicationContext` này đang có **bao nhiêu bean aspect** thuộc một class?
- Hai lần lấy bean có trả về **cùng một object** không?
- Một aspect bean có được dùng chung cho **nhiều target service bean**, nhiều lời gọi hay nhiều thread không?
- Một trường mutable trong aspect có tạo ra lỗi **lẫn dữ liệu giữa các lời gọi** không?
- Số **bean definition**, số **aspect instance tại runtime** và số **lần advice được thực thi** khác nhau ra sao?

Bài tập trung vào **cách Spring quản lý instance của bean `@Aspect`**, cách xác nhận tại runtime và cách bảo vệ trạng thái khi advice chạy trên nhiều bean/luồng. Đây là câu chuyện cụ thể của Spring AOP proxy trong `ApplicationContext`; không cần ôn lại AOP tổng quát.

**Kết luận cần kiểm chứng bằng chương trình:** với cấu hình thông dụng **một `@Aspect` bean singleton** trong một Spring context, nhiều target bean có method khớp pointcut có thể dùng **cùng một aspect instance**. Bởi vậy, một trường instance mutable trong aspect cũng được chia sẻ giữa các lời gọi. **Một instance aspect không đồng nghĩa một lần advice, một target, một request hay một thread.**

## 2. Ba loại “số lượng” khác nhau

| Đại lượng | Ý nghĩa đúng trong Spring | Cách kiểm tra | Điều không suy ra được |
| --- | --- | --- | --- |
| Số **bean names / bean definitions** của class aspect trong context | Context đã đăng ký mấy bean cho kiểu `MyAspect` | `context.getBeanNamesForType(MyAspect.class)` hoặc `getBeansOfType(MyAspect.class)` trong trường hợp singleton đơn giản | Không trực tiếp đo số lần advice chạy. Với prototype hoặc mô hình aspect instantiation nâng cao, đếm bean còn không phản ánh tổng instance đang được tạo trong runtime. |
| Số **object identity** được chia sẻ | Hai references có chỉ đến cùng instance không | `first == second`; có thể quan sát thêm `System.identityHashCode` chỉ để debug | Không biết đã có bao nhiêu proxy/target hoặc số lần advice. |
| Số **advice invocations** | Advice đã chạy bao nhiêu lần tại những join point phù hợp | Counter thread-safe, recorder hoặc integration test | Không đồng nhất với số aspect bean, target, request hay số business transaction thành công. |

**Ví dụ cơ bản:** Spring tạo một bean `countingAspect` có scope singleton. Một `OrderService` và một `PaymentService` được tạo hai proxy khác nhau; cả hai được aspect áp dụng. Sau ba lời gọi service qua proxy, kết quả có thể là **1 aspect bean, 1 aspect object, 2 target proxies, 3 lần advice chạy**.

```text
ApplicationContext
│
├── countingAspect  ───────────────┐
│   singleton CountingAspect      │ cùng một object, có AtomicInteger
│                                  │
├── orderService (Spring proxy) ───┼─> advisor -> advice trên CountingAspect
│                                  │
└── paymentService (Spring proxy) ─┘

Caller A và caller B gọi qua hai proxy:
cùng có thể làm advice thay đổi trạng thái của countingAspect.
```

Sơ đồ mô tả một cấu hình Spring AOP thường gặp; không có ý khẳng định Spring tạo một instance advice riêng cho mỗi proxy.

## 3. Scope mặc định: một singleton aspect bean trong mỗi context

Khi khai báo `@Aspect` dưới dạng Spring bean bằng `@Component` hoặc `@Bean` mà không chỉ định scope khác, Spring mặc định dùng **singleton scope**.

```java
@Aspect
@Component
public class CountingAspect {
    // Một Spring bean singleton trong context được scan
}
```

hoặc:

```java
@Configuration
@EnableAspectJAutoProxy
class AopConfig {
    @Bean
    CountingAspect countingAspect() {
        return new CountingAspect();
    }
}
```

Đây là **hai phương án đăng ký riêng**, không áp dụng đồng thời để tạo bean trùng. Với một bean definition singleton, Spring thường tạo một object và dùng lại khi inject/tra cứu bean đó trong **cùng context**. Aspect này có thể chứa các advice áp dụng cho nhiều target methods; Spring không tạo một copy riêng của aspect chỉ vì có thêm proxy.

Spring singleton có phạm vi **theo container và theo bean definition**, không phải singleton toàn JVM hay toàn bộ process:

- Hai bean definitions khác nhau cùng class có thể tạo **hai instance** trong một context; tùy advisor/pointcut, điều này có thể gây advice chạy hai lần.
- Hai `ApplicationContext` độc lập tạo hai bean singleton độc lập; mỗi context có instance riêng.
- Hai tiến trình ứng dụng hoặc hai replica cũng không tự chia sẻ Java object, dù bean trùng tên/class.
- Một context có thể có nhiều target beans/proxies, còn aspect bean singleton vẫn chỉ là một.

**Thận trọng:** Spring hỗ trợ những **mô hình khởi tạo aspect khác singleton**; vì vậy mọi kết luận “một aspect bean = một object” trong bài trước hết áp dụng cho cấu hình singleton mặc định. Mục 8 trình bày phạm vi của các mô hình nâng cao.

## 4. Kiểm tra Spring bean trước khi kiểm tra advice

Trong `ApplicationContext` hiện tại, bắt đầu từ bean registry:

```java
String[] names = context.getBeanNamesForType(CountingAspect.class);
System.out.println(java.util.Arrays.toString(names));

CountingAspect a = context.getBean(CountingAspect.class);
CountingAspect b = context.getBean("countingAspect", CountingAspect.class);
System.out.println(a == b);
```

Đây là **đoạn minh họa**, giả định context có đúng một singleton bean `CountingAspect` tên `countingAspect`. Khi ấy:

```text
[countingAspect]
true
```

Cách hiểu:

1. `getBeanNamesForType` trả về tên các bean tương ứng với type theo tiêu chí tra cứu của Spring container.
2. `getBean(MyAspect.class)` cần một bean duy nhất theo kiểu; nếu có hai bean cùng kiểu và không có phương án lựa chọn phù hợp, Spring có thể ném `NoUniqueBeanDefinitionException`.
3. `a == b` kiểm tra **identity chính xác**; với singleton bean và cùng tên/definition thì kết quả true. `a.equals(b)` không thích hợp để kết luận object identity vì class có thể override `equals`.
4. `getBeansOfType(MyAspect.class).size()` tiện để kiểm tra số bean của singleton phổ biến, nhưng có thể **khởi tạo bean không phải singleton** khi truy vấn. Với các scope nâng cao, tránh coi kết quả này là phép đếm mọi instance đã được tạo/đang được lưu trong AOP runtime.
5. `System.identityHashCode(bean)` hữu ích cho log/debug khi theo dấu object, nhưng mã hash có thể trùng; khi có thể, dùng so sánh `==` để khẳng định hai reference có phải chính xác cùng object.

Một bean tồn tại **không có nghĩa mọi target đã được proxy**. Sau bước đếm bean, kiểm tra riêng:

```java
OrderService order = context.getBean(OrderService.class);
boolean proxied = org.springframework.aop.support.AopUtils.isAopProxy(order);
System.out.println(proxied);
```

`isAopProxy` chỉ xác nhận object là AOP proxy, chưa xác nhận **advice của aspect đang xét** khớp một method cụ thể. Cần gọi method phù hợp và quan sát lời khuyên (advice) thực sự chạy.

## 5. Demo chạy được: một aspect, hai service, ba lời gọi

Ví dụ dùng **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, và Gradle có plugin `application`. Đây là ứng dụng Spring Framework thuần nhằm làm rõ instance và scope, không dựa vào Spring Boot auto-configuration.

### 5.1. Cấu trúc project

```text
spring-aspect-instance-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/aspectstate/
    ├── AppConfig.java
    ├── Counted.java
    ├── CountingAspect.java
    ├── OrderService.java
    ├── PaymentService.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-aspect-instance-demo'
```

**`build.gradle`**

```gradle
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.aspectstate.Main'
}
```

Đây là các versions cố định để có thể chép dự án thành một ví dụ độc lập; trong dự án Spring Boot thực tế nên để BOM/dependency management quản lý các versions Spring/AspectJ tương thích.

### 5.2. Annotation chọn method cần đếm

**`Counted.java`**

```java
package com.example.aspectstate;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Counted {
}
```

Chọn bằng annotation giúp pointcut tập trung vào method có chủ đích, tránh vô tình chặn các method của infrastructure.

### 5.3. Hai target Spring service khác nhau

**`OrderService.java`**

```java
package com.example.aspectstate;

public class OrderService {
    @Counted
    public String submit(String id) {
        return "order:" + id;
    }
}
```

**`PaymentService.java`**

```java
package com.example.aspectstate;

public class PaymentService {
    @Counted
    public String pay(String id) {
        return "payment:" + id;
    }
}
```

Ở đây hai class **không cần** `@Service` bởi chúng sẽ được đăng ký trực tiếp bằng `@Bean` trong cấu hình Spring. Điều quyết định Spring AOP là target phải được container quản lý và được caller gọi qua proxy.

### 5.4. Aspect giữ một counter được chia sẻ

**`CountingAspect.java`**

```java
package com.example.aspectstate;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class CountingAspect {
    private final AtomicInteger invocations = new AtomicInteger();

    @Before("@annotation(com.example.aspectstate.Counted)")
    public void beforeCountedMethod() {
        int number = invocations.incrementAndGet();
        System.out.println("advice#" + number);
    }

    public int getInvocationCount() {
        return invocations.get();
    }
}
```

Đây là một **stateful aspect có chủ đích để minh họa**. `AtomicInteger` làm thao tác increment/read an toàn khi advice bị gọi đồng thời. Nó **không chứng minh mọi trạng thái mutable đều an toàn**, cũng không biến counter trong một JVM thành hệ thống thống kê nhiều replica. Trong production, metric đếm invocation thường thích hợp hơn khi đưa vào Micrometer/Observation; aspect nên tránh tích lũy dữ liệu nghiệp vụ của từng request.

Annotation `@Aspect` mô tả aspect. Class cố ý **không có `@Component`** để bảo đảm chỉ có một nguồn đăng ký trong `AppConfig`.

### 5.5. Chỉ một bean aspect, hai beans target

**`AppConfig.java`**

```java
package com.example.aspectstate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public CountingAspect countingAspect() {
        return new CountingAspect();
    }

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public PaymentService paymentService() {
        return new PaymentService();
    }
}
```

Các bean `countingAspect`, `orderService`, `paymentService` mặc định là singleton. `@EnableAspectJAutoProxy` nhận diện `CountingAspect` và áp dụng pointcut `@annotation` cho hai service. `proxyTargetClass=true` giúp target proxy truy cập được bằng kiểu class concrete trong ví dụ; không ảnh hưởng đến việc singleton aspect được dùng chung.

### 5.6. Đếm và so sánh chính instance Spring đã đăng ký

**`Main.java`**

```java
package com.example.aspectstate;

import java.util.Arrays;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            String[] names = context.getBeanNamesForType(CountingAspect.class);
            CountingAspect first = context.getBean(CountingAspect.class);
            CountingAspect second =
                    context.getBean("countingAspect", CountingAspect.class);

            OrderService order = context.getBean(OrderService.class);
            PaymentService payment = context.getBean(PaymentService.class);

            System.out.println("aspectBeanNames=" + Arrays.toString(names));
            System.out.println("sameAspectInstance=" + (first == second));
            System.out.println("orderProxy=" + AopUtils.isAopProxy(order));
            System.out.println("paymentProxy=" + AopUtils.isAopProxy(payment));

            System.out.println(order.submit("ORD-1"));
            System.out.println(payment.pay("PAY-1"));
            System.out.println(order.submit("ORD-2"));

            System.out.println("adviceInvocations=" + first.getInvocationCount());
        }
    }
}
```

Chạy với Gradle đã cài:

```bash
gradle run --quiet
```

Nếu có Gradle wrapper, dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows.

**Các dòng `System.out` của chương trình theo thứ tự chính xác** (không tính log JVM/Spring/Gradle khác nếu môi trường bật logging):

```text
aspectBeanNames=[countingAspect]
sameAspectInstance=true
orderProxy=true
paymentProxy=true
advice#1
order:ORD-1
advice#2
payment:PAY-1
advice#3
order:ORD-2
adviceInvocations=3
```

### 5.7. Đọc đúng kết quả

- `aspectBeanNames=[countingAspect]`: có một Spring bean đăng ký dưới kiểu `CountingAspect`.
- `sameAspectInstance=true`: hai lần lấy bean qua type/name thực sự trả về **cùng object singleton**.
- `orderProxy=true` và `paymentProxy=true`: Spring tạo proxy cho **hai target khác nhau** vì method của cả hai khớp pointcut.
- `advice#1` và `advice#3` thuộc hai lời gọi `OrderService.submit`; `advice#2` thuộc lời gọi `PaymentService.pay`.
- `adviceInvocations=3`: counter trong **cùng một aspect object** nhận tất cả ba sự kiện. Counter không tự reset khi đổi từ target `OrderService` sang `PaymentService`.

Nếu mục tiêu học là “mỗi service có bộ đếm riêng” thì cấu hình singleton aspect này **không đáp ứng**. Không nên nhầm scope bean target với scope instance aspect; hai service khác nhau vẫn có thể dùng chung counter.

## 6. Kiểm chứng trạng thái được chia sẻ

### 6.1. Trạng thái dùng chung giữa các target

Từ demo, mô tả trạng thái sau từng lời gọi:

| Thời điểm | Bean target được gọi | Trạng thái `CountingAspect.invocations` |
| --- | --- | --- |
| Ngay sau khi lấy bean | Chưa gọi | 0 |
| Sau `order.submit("ORD-1")` | `orderService` proxy | 1 |
| Sau `payment.pay("PAY-1")` | `paymentService` proxy | 2 |
| Sau `order.submit("ORD-2")` | `orderService` proxy | 3 |

Điều này đến từ **aspect singleton được chia sẻ**, không phải vì `OrderService` và `PaymentService` dùng chung cùng một target instance. Khi ứng dụng có nhiều caller, tất cả caller đi vào những method match pointcut đều có thể sử dụng cùng aspect bean.

### 6.2. Trạng thái dùng chung giữa nhiều thread

Một singleton aspect không được Spring tạo riêng theo từng thread. Khi những request hoặc task chạy trên nhiều thread cùng gọi các Spring service beans có method được advice, **chúng có thể cùng truy cập trường instance trong aspect**.

Đoạn code **có lỗi race condition**, dùng để nhận diện anti-pattern:

```java
@Aspect
public class UnsafeCountingAspect {
    private int total;

    @Before("@annotation(com.example.aspectstate.Counted)")
    public void beforeCall() {
        total++; // read-modify-write không atomic
    }

    public int count() {
        return total;
    }
}
```

Đây là **đoạn minh họa**, không thay tệp `CountingAspect.java` trong demo chạy được. Với hai thread tăng `total` đồng thời, các phép đọc/ghi có thể bị chồng lấn và mất cập nhật; giá trị cuối nhỏ hơn số advice thực thi. `volatile int total` vẫn không làm `total++` thành thao tác atomic; `volatile` chỉ có ngữ nghĩa visibility/happens-before phù hợp, không tự bảo vệ chuỗi read-modify-write.

Phiên bản cho **một counter độc lập** như ví dụ `AtomicInteger`:

```java
private final AtomicInteger invocations = new AtomicInteger();

@Before("@annotation(com.example.aspectstate.Counted)")
public void beforeCountedMethod() {
    invocations.incrementAndGet();
}
```

`AtomicInteger` phù hợp khi thực sự muốn đếm tổng số invocation **trong một instance aspect**, nhưng không bảo vệ một tập hợp nhiều field phải cập nhật cùng nhau. Ví dụ “ghi `currentUser` và `currentOrder` rồi đọc cả hai trong advice” không thể sửa chỉ bằng cách biến một field thành atomic.

### 6.3. Lỗi lẫn dữ liệu request trong aspect singleton

Ví dụ nguy hiểm:

```java
@Aspect
@Component
public class UnsafeAuditAspect {
    private String currentOrderId;

    @Before("@annotation(com.example.aspectstate.Counted) && args(id)")
    public void record(String id) {
        currentOrderId = id;
        // Một thread khác có thể thay currentOrderId ngay sau lệnh gán.
    }
}
```

Đây là **mã minh họa độc lập**, giả sử target method có một tham số `String id` và có component scan. Thứ tự xen kẽ có thể là:

```text
Thread A: record("ORD-A") -> currentOrderId = "ORD-A"
Thread B: record("ORD-B") -> currentOrderId = "ORD-B"
Thread A: đọc currentOrderId -> nhìn thấy "ORD-B" (sai request)
```

Lỗi **không xuất phát từ `@Aspect`**, mà từ việc lưu trạng thái request trong object Spring singleton được nhiều thread dùng chung.

Thay bằng tham số/lokal variables của chính advice:

```java
@Aspect
@Component
public class SafeAuditAspect {
    @Before("@annotation(com.example.aspectstate.Counted) && args(id)")
    public void record(String id) {
        String orderId = id; // Giá trị local của mỗi invocation
        System.out.println("audit:" + orderId);
    }
}
```

Hai class `UnsafeAuditAspect`/`SafeAuditAspect` chỉ là các phương án giảng giải. Không thêm cả hai vào project demo vì sẽ làm lời gọi có thêm advisor/log. Với production, loại bỏ thông tin nhạy cảm khỏi log và chuyển công việc audit sang một service/repository/sink phù hợp nếu có persistence, retry, transaction hoặc yêu cầu bảo mật.

### 6.4. Dữ liệu cần per-request: đừng chuyển sang field aspect

Một aspect singleton có thể inject một **service an toàn** để xử lý dữ liệu request, nhưng không lưu request data vào field mutable của chính nó:

```java
@Aspect
@Component
public class AuditAspect {
    private final AuditWriter writer;

    public AuditAspect(AuditWriter writer) {
        this.writer = writer;
    }

    @Before("@annotation(com.example.aspectstate.Counted) && args(id)")
    public void record(String id) {
        writer.write(id); // id là tham số của lần gọi hiện tại
    }
}
```

Đây là **đoạn minh họa**, cần một Spring bean `AuditWriter` do ứng dụng tự định nghĩa. Việc `writer` là `final` chỉ bảo đảm reference của dependency không bị thay; chính `AuditWriter` vẫn phải được thiết kế thread-safe phù hợp. Nếu dùng request-scoped bean/proxy hoặc context dữ liệu bảo mật, cần hiểu request scope và cách truyền ngữ cảnh khi async; không giả định nó hoạt động trong mọi thread hay non-web execution.

Đôi khi `ThreadLocal` được dùng cho context tại một thread, nhưng phải xóa đúng bằng `finally` và không tự truyền qua `@Async`/task executors. Cách an toàn dễ kiểm tra nhất là đưa dữ liệu theo tham số method/advice hoặc công cụ context/observation của chính framework.

## 7. Một bài kiểm tra concurrent có thể lặp lại

Để tránh nhận xét “singleton chắc chỉ chạy một thread”, ta có thể thực hiện thêm một phép thử **gọi cùng service proxy từ nhiều thread**. Sử dụng đúng `AppConfig`/`CountingAspect` của demo, ví dụ dưới đây là một **class Java chạy độc lập** đặt thêm ở `src/main/java/com/example/aspectstate/ConcurrentProbe.java`.

**`ConcurrentProbe.java`**

```java
package com.example.aspectstate;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class ConcurrentProbe {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService order = context.getBean(OrderService.class);
            CountingAspect aspect = context.getBean(CountingAspect.class);

            ExecutorService executor = Executors.newFixedThreadPool(4);
            try {
                List<Future<String>> futures = new ArrayList<>();
                for (int i = 0; i < 100; i++) {
                    final int number = i;
                    futures.add(executor.submit(
                            (Callable<String>) () -> order.submit("N-" + number)
                    ));
                }

                for (Future<String> future : futures) {
                    future.get(); // đợi hoàn tất và lan truyền failure nếu có
                }

                System.out.println("completed=" + futures.size());
                System.out.println("count=" + aspect.getInvocationCount());
            } finally {
                executor.shutdown();
            }
        }
    }
}
```

Để chạy class riêng này với cùng Gradle project, thêm task sau vào cuối `build.gradle`:

```gradle
tasks.register('concurrentProbe', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.aspectstate.ConcurrentProbe'
}
```

Chạy:

```bash
gradle concurrentProbe --quiet
```

Advice từ `CountingAspect` sẽ in **100 dòng `advice#...` theo lịch chạy không cố định**. **Hai dòng cuối do `ConcurrentProbe` in ra** sau khi tất cả futures kết thúc có kết quả chính xác:

```text
completed=100
count=100
```

Mẫu output phía trên chỉ nêu **hai dòng kết thúc**, không phải toàn bộ stdout của phép thử. Thứ tự số trong các dòng advice và thời điểm method từng thread hoàn thành không bảo đảm; `AtomicInteger` bảo đảm tổng count = 100 trong context mới. Đây là đối chứng rằng nhiều thread cùng thay đổi trạng thái của **một aspect bean** và phép tăng counter được atomic.

Để kiểm tra race của `int total++` có thể dùng nhiều vòng lặp đồng thời và quan sát mất cập nhật, nhưng kết quả race **không tất định**; một lần tình cờ đúng 100 không chứng minh code an toàn. Đối với kiểm thử phần mềm, nên dùng concurrency tests/stress tests, và lý giải thiết kế thread safety độc lập với kết quả một lần chạy.

## 8. Scope phức tạp: không tự đồng nhất aspect bean với instance

Trong **cấu hình Spring AOP @AspectJ thông dụng**, mô hình khởi tạo mặc định là **singleton aspect instance trong application context**. Spring còn có những **mô hình aspect instantiation theo đối tượng/loại**, ví dụ `perthis` và `pertarget`, được tài liệu Spring mô tả là tính năng nâng cao.

Ví dụ **cú pháp minh họa**, không ghép vào demo singleton:

```java
@Aspect("perthis(execution(* com.example.aspectstate..*Service.*(..)))")
public class PerProxyAspect {
    // trạng thái gắn theo mỗi proxy object phù hợp pointcut
}
```

- `perthis`: gắn aspect instance theo từng object được ràng buộc với `this` tại join point khớp; với Spring AOP proxy, `this` thường biểu thị proxy object. Instance được tạo theo điều kiện khởi tạo của mô hình này, không phải đơn giản tạo một instance mới trên **mỗi** lần gọi method.
- `pertarget`: gắn theo từng target object phù hợp; khác biệt `this`/`target` quan trọng trong cơ chế Spring proxy.
- Các khả năng nâng cao thay đổi theo phiên bản Spring: ví dụ tài liệu Spring Framework **7.x** còn liệt kê `pertypewithin`, trong khi các tài liệu Spring **6.x** cũ có danh sách hạn chế hơn. Vì vậy, trước khi sử dụng, kiểm tra **tài liệu đúng phiên bản** và thử với context thực của dự án.
- `percflow`/`percflowbelow` không thuộc các mô hình Spring AOP proxy được tài liệu hiện hành hỗ trợ.

**Không kết luận “gắn `@Scope("prototype")` vào một `@Aspect` singleton sẽ tạo một instance theo mỗi request”.** Bean scope Spring và mô hình khởi tạo aspect @AspectJ có hợp đồng riêng; với per-clause, cần kiểm tra cách đăng ký/scope aspect tương thích trong phiên bản Spring của bạn. Kể cả có một aspect instance theo từng target, **nhiều thread gọi vào cùng target vẫn có thể dùng chung aspect instance đó**. Per-target không tương đương request scope hoặc thread isolation.

Nếu bài toán là đếm theo từng user/request/order, một singleton aspect stateless + một service lưu trạng thái được key đúng theo ID thường dễ kiểm soát hơn cố tạo nhiều aspect instances. Trước khi chọn per-clause, cần bằng chứng rõ ràng rằng **lifecycle aspect theo target** là mong muốn nghiệp vụ.

### Context độc lập: mỗi nơi một singleton riêng

Tình huống khác hoàn toàn với `perthis` là tạo hai `ApplicationContext` độc lập:

```java
try (var firstContext = new AnnotationConfigApplicationContext(AppConfig.class);
     var secondContext = new AnnotationConfigApplicationContext(AppConfig.class)) {
    CountingAspect first = firstContext.getBean(CountingAspect.class);
    CountingAspect second = secondContext.getBean(CountingAspect.class);
    System.out.println("sameAcrossContexts=" + (first == second));
}
```

Đây là **đoạn minh họa** đặt trong class có import `AnnotationConfigApplicationContext` và được khai báo `AppConfig` như demo. Nó in:

```text
sameAcrossContexts=false
```

Mỗi context đăng ký một singleton aspect bean riêng. Trong mô hình parent/child context, còn phải xét nơi target/proxy/advisor được tạo, nên không suy “một aspect cho toàn ứng dụng” chỉ dựa vào tên class.

## 9. Quy trình kiểm tra một ứng dụng Spring thực tế

Khi nghi vấn advice trùng, state bị chia sẻ hoặc kết quả không đúng, theo thứ tự:

1. **Xác nhận context đang xem:** lấy từ `ApplicationContext` đúng nơi target bean được tạo; nếu có root/child, xác định parent/child rõ ràng.
2. **Đếm bean names thuộc class aspect:** `getBeanNamesForType(MyAspect.class)`; nếu >1, xem lại `@Component` kết hợp `@Bean`, `@Import` hoặc cấu hình module bị đưa vào context nhiều lần.
3. **Xem scope của bean definition:** `context.isSingleton("beanName")` cho câu hỏi bean scope singleton, hoặc dùng `getBeanFactory().getBeanDefinition("beanName").getScope()` trên context/configurable bean factory phù hợp. Chuỗi scope rỗng ở bean definition thường biểu thị scope mặc định singleton.
4. **So sánh identity:** gọi `getBean("beanName")` hai lần và so `==` khi đang kiểm tra singleton. Đừng nhầm với `equals` hay số proxy objects.
5. **Kiểm tra target proxy:** `AopUtils.isAopProxy(targetBean)`, kiểu JDK/class proxy và pointcut match. Một aspect bean hiện diện không đủ chứng minh advice thực thi.
6. **Đếm advice bằng thread-safe recorder:** tại method cụ thể, chạy tuần tự trước, sau đó thử concurrent và kiểm tra mỗi lời gọi ghi đúng số sự kiện.
7. **Audit mọi mutable field trong aspect:** phân loại config immutable, dependency service, counter, cache, request context, dữ liệu người dùng. Field mutable chứa state mỗi request là dấu hiệu cần thiết kế lại.
8. **Kiểm tra môi trường production:** nhiều threads, async/reactive hand-off, nhiều replicas, tác động của transaction/advisor order và nguồn quan sát/log thực tế.

**Bảng đối chiếu triệu chứng:**

| Hiện tượng | Giải thích có thể xảy ra | Cách xác nhận |
| --- | --- | --- |
| `getBeansOfType(MyAspect.class)` trả về 0 | Aspect chỉ có `@Aspect`, chưa có `@Component`/`@Bean` hoặc scan sai context | Kiểm tra cách đăng ký, package scan và config được import |
| Có một aspect bean nhưng advice chạy 0 lần | Không bật Spring AOP, thiếu dependencies, pointcut không match, target không qua proxy, self-invocation | Kiểm tra `@EnableAspectJAutoProxy`/Boot auto-config, `AopUtils` và actual method call |
| Advice chạy hai lần trên một method | Hai beans/aspects cùng advice hoặc nhiều advisors cùng match | Liệt kê bean names, advisor chain và nơi đăng ký aspect |
| Hai service khác nhau tăng cùng counter | Aspect singleton dùng chung giữa nhiều target beans | Lấy aspect bean, quan sát identity và count sau mỗi lời gọi |
| Dữ liệu của request B xuất hiện trong log request A | Field mutable giữ context request trong aspect singleton | Kiểm tra field, hai lời gọi concurrent và cách truyền id |
| Counter thấp hơn số lời gọi concurrent | `int++` bị race hoặc có calls không thực sự đi qua proxy | Tách kiểm tra match/proxy; dùng `AtomicInteger` hay recorder concurrency-safe |
| Mỗi context có counter khác nhau | Singleton scope là per-bean/per-container | So sánh aspect bean object của từng context |
| Dùng prototype nhưng kết quả instance khó dự đoán | Nhầm Spring bean scope với aspect instantiation model | Kiểm tra `@Aspect` per-clause và lifecycle thực tế trong phiên bản Spring |

### Không nên đếm bằng output console duy nhất

Các dòng log có thể bị interleave khi concurrent; logger có async buffering; một advice có thể log nhiều sự kiện hoặc bị filter; retry và transaction rollback có thể thay đổi quan sát. Với mục tiêu QA, dùng **counter/test sink có xác nhận chính xác** và assert theo số method thực sự đi qua proxy. Counter có thể đếm **attempted method executions** thay vì business successes nếu dùng `@Before`; đừng gọi số này là số giao dịch đã commit.

## 10. Checklist trước khi chấp nhận thiết kế

- [ ] Đã nêu rõ sẽ đếm **bean aspect**, **aspect instance** hay **advice invocation**, không gom ba khái niệm.
- [ ] Aspect được Spring đăng ký bằng `@Component` hoặc `@Bean` và có đúng số lượng bean definitions dự kiến.
- [ ] Đã xác nhận scope mặc định singleton hoặc mô hình instantiation nâng cao với tài liệu đúng version.
- [ ] Đã phân biệt một context, nhiều contexts, nhiều threads và nhiều replicas.
- [ ] Có Spring AOP proxy trên target cần advice; pointcut khớp và lời gọi đi qua proxy.
- [ ] Trường của aspect chứa cấu hình/dependency an toàn; không giữ request-specific mutable data trong singleton.
- [ ] Counter hoặc collection chia sẻ được đồng bộ/thread-safe đúng mức; composite state cần cách bảo vệ đầy đủ.
- [ ] Ví dụ/test sử dụng context thật, so object identity bằng `==`, đếm advice bằng recorder/counter đáng tin.
- [ ] Đã kiểm tra self-invocation, lỗi đăng ký trùng aspect và trường hợp @Aspect không là Spring bean.
- [ ] Nếu cần per-request/per-target state, đã chọn một cơ chế lifecycle phù hợp, không tự suy từ `@Scope("prototype")`.

**Điểm nhớ:** Trong Spring AOP mặc định, **một bean aspect singleton có thể phục vụ nhiều proxy, nhiều lời gọi và nhiều thread**. Phải kiểm tra số bean và object identity ở **đúng context**, kiểm tra lời gọi advice riêng và chủ động bảo vệ hoặc loại bỏ state mutable trong aspect. Không dùng số lần advice hay số target proxy để suy ra số aspect instances.

## Tài liệu chính thức

- [Spring Framework — Aspect Instantiation Models](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html)
