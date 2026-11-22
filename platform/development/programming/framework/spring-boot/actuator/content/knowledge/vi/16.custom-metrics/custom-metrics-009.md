# Sử dụng @Timed và @Counted với cơ chế aspect phù hợp

## 1. Annotation mô tả điều cần đo; aspect thực hiện phép đo

Một phương thức có `@Timed` chưa chắc đã tạo ra timer. Tương tự, thêm `@Counted` vào mã nguồn chưa đủ để số lần gọi tự xuất hiện trong Actuator.

Hai annotation của Micrometer là **thông tin mô tả tại thời gian chạy**. Phải có thành phần hiểu chúng và chặn lời gọi phương thức để bắt đầu/dừng phép đo hoặc tăng bộ đếm. Với service Spring thông thường, cách tiếp cận trong bài là dùng:

- `TimedAspect` để xử lý `io.micrometer.core.annotation.Timed`.
- `CountedAspect` để xử lý `io.micrometer.core.annotation.Counted`.
- Spring AOP tạo đối tượng đại diện, gọi là **proxy**, đứng trước bean cần đo.
- `MeterRegistry` nhận số liệu; Spring Boot Actuator cho phép kiểm tra hoặc xuất số liệu tùy cấu hình.

Cơ chế gọi có dạng:

```text
Bean gọi
   -> proxy của bean được đo
       -> aspect bắt đầu quan sát
           -> phương thức nghiệp vụ
       -> aspect kết thúc quan sát và ghi MeterRegistry
   -> trả kết quả hoặc ném tiếp ngoại lệ
```

**Điều kiện quan trọng là lời gọi phải đi qua proxy có gắn aspect tương ứng.** Nếu gọi trực tiếp đối tượng gốc, annotation vẫn tồn tại nhưng không có thành phần thực hiện phép đo cho lời gọi đó.

Các cấu hình bean aspect được Micrometer mô tả tại phần [@Timed](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html#_the_timed_annotation) và [@Counted](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html#_the_counted_annotation). Bài này tập trung vào service tùy chỉnh của Spring Boot 3.3 và ví dụ kiểm chứng bằng Micrometer 1.13.0, Spring Framework 6.1.8.

## 2. Chọn @Timed hay @Counted theo câu hỏi cần trả lời

| Nhu cầu | Công cụ | Dữ liệu chính |
| --- | --- | --- |
| Một lần thực thi mất bao lâu? | `@Timed` với timer thường | Số lần đã hoàn tất, tổng thời lượng; thêm thống kê khác tùy registry/cấu hình |
| Một phương thức hoàn tất bao nhiêu lần? | `@Counted` | Bộ đếm theo kết quả thực thi |
| Chỉ đếm các lần kết thúc bằng ngoại lệ | `@Counted(recordFailuresOnly = true)` | Bộ đếm lỗi |
| Hiện có bao nhiêu công việc dài đang chạy và đã chạy bao lâu? | `@Timed(longTask = true)` | `LongTaskTimer`, với ngữ nghĩa khác timer hoàn tất thông thường |

Timer thường đã có `count`. Nếu cùng một ranh giới nghiệp vụ đã được đo bằng timer, không cần thêm một counter chỉ để đếm lại đúng các sự kiện đó. Một counter riêng chỉ có giá trị khi nó trả lời câu hỏi khác, ví dụ số lần từ chối xử lý, hoặc có cách phân loại thực sự cần thiết.

Trong thí nghiệm bên dưới, timer và counter đồng thời được đặt lên phương thức bất đồng bộ để so sánh **thời điểm ghi** của hai aspect. Đây là chủ đích của thí nghiệm; khi áp dụng thật, lựa chọn công cụ đủ trả lời câu hỏi của mình.

### Tên, mô tả và các nhãn cố định

Ví dụ khai báo trên một phương thức có sẵn:

```java
@Timed(
    value = "app.invoice.generate",
    description = "Time spent generating an invoice",
    extraTags = {"format", "pdf"}
)
```

Hoặc:

```java
@Counted(
    value = "app.invoice.rejected",
    recordFailuresOnly = true,
    extraTags = {"channel", "batch"}
)
```

`extraTags` là các cặp khóa/giá trị, nên số phần tử phải chẵn. Tên nên ổn định, diễn tả một hoạt động; tag diễn tả các chiều phân loại có tập giá trị hữu hạn. Không dùng mã hóa đơn, email, nội dung ngoại lệ hay giá trị tham số tùy ý làm nhãn.

Với aspect mặc định trong ví dụ, timer có các nhãn như `class`, `method`, `exception`; counter có thêm `result`. Tránh tự định nghĩa nhãn cùng tên nhưng mang nghĩa khác. Các annotation không tự tạo dashboard hay cảnh báo.

## 3. Cấu hình đúng trong Spring Boot 3.3

### 3.1. Có thư viện AOP và có aspect bean là hai điều kiện riêng

Trong dự án Spring Boot đã có cơ chế quản lý phiên bản phụ thuộc:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Actuator cung cấp hạ tầng metrics và registry phù hợp với ứng dụng. Starter AOP cung cấp các phụ thuộc cho cơ chế proxy/aspect. Để các service tùy chỉnh được xử lý rõ ràng, đăng ký hai aspect dùng **chính MeterRegistry do Spring quản lý**:

Tệp `MethodMetricsConfiguration.java`, nằm trong phạm vi quét cấu hình:

```java
package demo;

import io.micrometer.core.aop.CountedAspect;
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MethodMetricsConfiguration {
    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }

    @Bean
    CountedAspect countedAspect(MeterRegistry registry) {
        return new CountedAspect(registry);
    }
}
```

Mỗi loại aspect chỉ đăng ký một lần trong cấu hình hiệu lực. Nếu ứng dụng hoặc thư viện nội bộ đã cung cấp aspect, hãy dùng cấu hình đó thay vì thêm một bản thứ hai.

Không dùng `new SimpleMeterRegistry()` trong cấu hình trên chỉ để constructor biên dịch được. Registry riêng đó không mặc nhiên là registry mà Actuator hoặc bộ xuất Prometheus đang đọc. Trong ứng dụng thật, dùng bean `MeterRegistry` được inject.

### 3.2. Có cần @EnableAspectJAutoProxy hoặc javaagent không?

Spring Boot 3.3 tự cấu hình AOP khi điều kiện classpath/cấu hình phù hợp. Mặc định Boot dùng proxy dựa trên lớp; `spring.aop.proxy-target-class=false` chuyển sang proxy dựa trên interface. Khi cơ chế tự cấu hình hoạt động, không cần thêm `@EnableAspectJAutoProxy` chỉ để lặp lại việc đã được Boot thực hiện. Xem [Aspect-Oriented Programming của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/aop.html).

Trong ví dụ **Spring thuần**, không chạy Spring Boot, ta khai báo `@EnableAspectJAutoProxy` rõ ràng.

Spring AOP có thể hiểu các aspect viết bằng annotation AspectJ. Điều đó không có nghĩa là ví dụ đang sửa bytecode bằng AspectJ weaving. Cách dùng proxy ở đây không cần bật `-javaagent:aspectjweaver`. Compile-time weaving và load-time weaving là những cơ chế khác, có cấu hình và hệ quả khác; không trộn chúng vào ứng dụng chỉ để làm annotation hoạt động.

## 4. Ranh giới proxy quyết định lời gọi nào được ghi

### 4.1. Lời gọi từ bean khác qua tham chiếu được inject

Khi bean A nhận bean B qua Spring và gọi phương thức được đo của B, tham chiếu B có thể là proxy. Aspect có cơ hội chặn lời gọi đó:

```text
A -> proxy B -> aspect -> B.work()
```

Đây là ranh giới phù hợp để đo một thao tác service. Giữ lớp và phương thức đủ điều kiện được proxy; ví dụ dùng lớp Java thường, phương thức `public`, không `final`.

### 4.2. Tự gọi trong cùng đối tượng bỏ qua aspect của phương thức được gọi

Giả sử cùng một service có:

```java
public void outer() {
    inner();
}

@Timed("app.inner")
public void inner() {
    // Phần xử lý nội bộ.
}
```

Đoạn này minh họa ranh giới gọi, không phải lớp chạy độc lập. Khi `outer()` thực thi trên đối tượng đích, `inner()` là lời gọi qua `this`. Nó không đi qua proxy lần nữa. Vì vậy, aspect của `inner()` không được áp dụng chỉ nhờ annotation.

Nếu cần đo `inner` như một thao tác độc lập, có thể tách thao tác đó sang một bean cộng tác và gọi qua bean được inject. Nếu thực chất chỉ cần đo toàn bộ `outer`, đặt annotation ở `outer`. Nếu cần đo một đoạn nội bộ nhỏ, dùng `Timer` trực tiếp ở ranh giới đó cũng có thể rõ ràng hơn việc tổ chức lại toàn bộ cấu trúc chỉ để đi qua proxy.

### 4.3. Các trường hợp cần phân biệt

| Cách gọi/khai báo | Hệ quả với Spring AOP |
| --- | --- |
| Gọi bean được inject từ bên ngoài | Có thể được aspect chặn khi cấu hình và phương thức phù hợp |
| `this.inner()` hoặc `inner()` trong cùng đối tượng | Bỏ qua advice của lời gọi inner |
| `new SomeService(...).work()` | Đối tượng tạo trực tiếp không phải proxy do Spring quản lý |
| Phương thức `private` hoặc `static` | Không phải điểm chặn phù hợp của cơ chế proxy thông thường |
| Lớp/phương thức `final` với proxy dựa trên lớp | Không thể tạo lớp con/ghi đè theo cách cần thiết để áp dụng advice |
| Proxy JDK | Các lời gọi đi qua interface được proxy; cần kiểm tra cách tra cứu annotation ở phương thức thực thi |
| Gọi trong constructor hoặc giai đoạn khởi tạo bean | Không nên dựa vào việc proxy đã sẵn sàng để đo lời gọi đó |

Không kết luận rằng mọi phương thức `final` đều bất khả thi với mọi loại proxy: proxy JDK đại diện interface nên có đặc điểm khác proxy tạo lớp con. Với bài thử và service thông thường, lựa chọn dễ kiểm chứng là phương thức public không final trên lớp không final. Cơ chế proxy và self-invocation được giải thích trong [tài liệu Spring AOP](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).

## 5. Thí nghiệm Java: chứng minh các điều kiện bằng số liệu

Chương trình sau chạy Spring thuần để nhìn rõ việc đăng ký aspect và tạo proxy. Không cần máy chủ HTTP hay hệ giám sát bên ngoài. Nó dùng đồng hồ giả `MockClock` để kiểm chứng thời lượng mà không cần `Thread.sleep`.

### 5.1. Dự án Gradle riêng

Dùng JDK 17 trở lên; có thể dùng JDK 21. Tạo một dự án thí nghiệm riêng với `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.8'
    implementation 'org.springframework:spring-aop:6.1.8'
    implementation 'org.aspectj:aspectjweaver:1.9.22'
    implementation 'io.micrometer:micrometer-core:1.13.0'
}

application {
    mainClass = 'demo.MetricsAspectDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
    options.compilerArgs += ['-parameters']
}

tasks.register('copyRuntimeDependencies', Copy) {
    from configurations.runtimeClasspath
    into layout.buildDirectory.dir('runtime-libs')
}
```

`settings.gradle`:

```groovy
rootProject.name = 'metrics-aspect-demo'
```

Trong ứng dụng Boot thật, để Boot quản lý các phiên bản phụ thuộc. Những phiên bản tường minh ở đây chỉ phục vụ dự án Spring thuần được kiểm chứng.

### 5.2. Chương trình đầy đủ

Tệp `src/main/java/demo/MetricsAspectDemo.java`:

```java
package demo;

import io.micrometer.core.annotation.Counted;
import io.micrometer.core.annotation.Timed;
import io.micrometer.core.aop.CountedAspect;
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class MetricsAspectDemo {
    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class Config {
        @Bean
        MockClock clock() {
            return new MockClock();
        }

        @Bean
        SimpleMeterRegistry meterRegistry(MockClock clock) {
            return new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        }

        @Bean
        TimedAspect timedAspect(MeterRegistry registry) {
            return new TimedAspect(registry);
        }

        @Bean
        CountedAspect countedAspect(MeterRegistry registry) {
            return new CountedAspect(registry);
        }

        @Bean
        WorkService workService(MockClock clock) {
            return new WorkService(clock);
        }
    }

    public static class WorkService {
        private final MockClock clock;

        public WorkService(MockClock clock) {
            this.clock = clock;
        }

        @Timed(value = "demo.work", extraTags = {"channel", "local"})
        public void work(boolean fail) {
            clock.add(Duration.ofMillis(fail ? 5 : 10));
            if (fail) {
                throw new IllegalArgumentException("Invalid work");
            }
        }

        public void selfInvoke() {
            work(false);
        }

        @Counted(value = "demo.events", extraTags = {"channel", "local"})
        public void event(boolean fail) {
            if (fail) {
                throw new IllegalArgumentException("Invalid event");
            }
        }

        @Counted(value = "demo.failures", recordFailuresOnly = true)
        public void failuresOnly(boolean fail) {
            if (fail) {
                throw new IllegalStateException("Failed operation");
            }
        }

        @Timed("demo.async")
        @Counted("demo.async.completed")
        public CompletableFuture<String> await(CompletableFuture<String> source) {
            return source;
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            SimpleMeterRegistry registry = context.getBean(SimpleMeterRegistry.class);
            MockClock clock = context.getBean(MockClock.class);
            WorkService service = context.getBean(WorkService.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));

            service.work(false);
            try {
                service.work(true);
            } catch (IllegalArgumentException expected) {
                // Bên gọi vẫn nhận được ngoại lệ nghiệp vụ.
            }
            printTimer(registry, "demo.work", "none");
            printTimer(registry, "demo.work", "IllegalArgumentException");

            service.selfInvoke();
            new WorkService(clock).work(false);
            System.out.println("after bypass: timed.count=" + timerCount(registry, "demo.work"));

            service.event(false);
            try {
                service.event(true);
            } catch (IllegalArgumentException expected) {
                // Tiếp tục các bước kiểm chứng.
            }
            System.out.printf(Locale.ROOT, "events: success=%.0f failure=%.0f%n",
                    registry.get("demo.events").tag("result", "success").counter().count(),
                    registry.get("demo.events").tag("result", "failure").counter().count());

            service.failuresOnly(false);
            try {
                service.failuresOnly(true);
            } catch (IllegalStateException expected) {
                // Chỉ lần thất bại này được đếm.
            }
            System.out.printf(Locale.ROOT, "failures.only=%.0f success.series.present=%s%n",
                    counterCount(registry, "demo.failures"),
                    registry.find("demo.failures").tag("result", "success").counter() != null);

            CompletableFuture<String> source = new CompletableFuture<>();
            CompletableFuture<String> observed = service.await(source);
            System.out.printf(Locale.ROOT, "async before: timed=%d counted=%.0f%n",
                    timerCount(registry, "demo.async"),
                    counterCount(registry, "demo.async.completed"));
            clock.add(Duration.ofMillis(25));
            source.complete("done");
            System.out.println("async result=" + observed.join());
            printTimer(registry, "demo.async", "none");

            CompletableFuture<String> failedSource = new CompletableFuture<>();
            CompletableFuture<String> failedObserved = service.await(failedSource);
            clock.add(Duration.ofMillis(7));
            failedSource.completeExceptionally(new IllegalStateException("Async failure"));
            try {
                failedObserved.join();
            } catch (CompletionException expected) {
                // Bên gọi vẫn quan sát được lỗi qua future trả về.
            }
            printTimer(registry, "demo.async", "IllegalStateException");
            System.out.printf(Locale.ROOT, "async after: timed=%d counted=%.0f%n",
                    timerCount(registry, "demo.async"),
                    counterCount(registry, "demo.async.completed"));
        }
    }

    private static long timerCount(MeterRegistry registry, String name) {
        return registry.find(name).timers().stream().mapToLong(Timer::count).sum();
    }

    private static double counterCount(MeterRegistry registry, String name) {
        return registry.find(name).counters().stream().mapToDouble(counter -> counter.count()).sum();
    }

    private static void printTimer(MeterRegistry registry, String name, String exception) {
        Timer timer = registry.get(name).tag("exception", exception).timer();
        System.out.printf(Locale.ROOT, "%s exception=%s count=%d total.ms=%.0f%n",
                name, exception, timer.count(), timer.totalTime(TimeUnit.MILLISECONDS));
    }
}
```

Chạy bằng Gradle đã cài, hoặc wrapper của chính dự án thí nghiệm nếu có:

```shell
gradle -q run
```

Để kiểm tra trực tiếp bằng `javac`/`java`, trước hết chạy `gradle -q copyRuntimeDependencies`, rồi dùng lệnh Windows:

```shell
javac --release 17 -encoding UTF-8 -parameters -cp "build/runtime-libs/*" -d build/manual-classes src/main/java/demo/MetricsAspectDemo.java
java -cp "build/manual-classes;build/runtime-libs/*" demo.MetricsAspectDemo
```

Trên Linux/macOS, thay dấu `;` ngăn các thành phần classpath của lệnh `java` bằng `:`.

### 5.3. Stdout của chương trình

```text
proxy=true
demo.work exception=none count=1 total.ms=10
demo.work exception=IllegalArgumentException count=1 total.ms=5
after bypass: timed.count=2
events: success=1 failure=1
failures.only=1 success.series.present=false
async before: timed=0 counted=0
async result=done
demo.async exception=none count=1 total.ms=25
demo.async exception=IllegalStateException count=1 total.ms=7
async after: timed=2 counted=2
```

`Locale.ROOT` giúp định dạng số ổn định. Đồng hồ giả chỉ thay đổi thời gian mà meter nhìn thấy; chương trình không thực sự ngủ 10, 25 hay 7 mili giây. Đóng Spring context cũng đóng các bean có vòng đời tương ứng.

## 6. Giải thích từng bằng chứng

### 6.1. Có proxy, có aspect, có số liệu

`proxy=true` chứng minh bean lấy từ context là AOP proxy. Tuy nhiên, riêng việc có proxy vẫn chưa đủ chứng minh có phép đo: một bean có thể được proxy cho transaction nhưng chưa có TimedAspect. Bằng chứng hoàn chỉnh là lời gọi qua proxy cộng với meter và kết quả đúng sau lời gọi.

Hai lần gọi `work` qua proxy tạo hai chuỗi timer theo tag `exception`:

| Kết quả | Nhãn exception | Count | Tổng thời lượng |
| --- | --- | --- | --- |
| Hoàn tất bình thường | `none` | 1 | 10 ms |
| Ném ngoại lệ | `IllegalArgumentException` | 1 | 5 ms |

Timer thường ghi cả lần thành công và lần kết thúc bằng ngoại lệ. Aspect không nuốt ngoại lệ nghiệp vụ: bên gọi vẫn bắt được `IllegalArgumentException`.

Nếu muốn tổng số lần thực thi, cộng count của các chuỗi thuộc đúng tên/phạm vi cần xét. Nếu chỉ lấy chuỗi `exception=none`, đang đếm các lần kết thúc bình thường.

### 6.2. Hai lần bypass vẫn chạy nghiệp vụ nhưng không được đo

Sau đó chương trình gọi:

```java
service.selfInvoke();
new WorkService(clock).work(false);
```

Lần đầu đi qua proxy vào `selfInvoke`, nhưng lời gọi tiếp tới `work` diễn ra trong đối tượng đích. Lần sau gọi một đối tượng được tạo trực tiếp. Cả hai đều làm đồng hồ giả tiến thêm, nhưng timer `demo.work` vẫn có tổng count bằng 2.

Không có số liệu không đồng nghĩa nghiệp vụ không chạy. Đây là lý do cần kiểm tra đường đi của lời gọi khi annotation “không có tác dụng”.

### 6.3. @Counted phân loại theo kết thúc phương thức

Trong ví dụ:

```text
event(false) -> result=success, exception=none
event(true)  -> result=failure, exception=IllegalArgumentException
```

Mỗi chuỗi có count bằng 1. “Success” ở đây là **phương thức/aspect quan sát thấy việc hoàn tất bình thường**, không tự xác nhận mọi điều kiện thành công của nghiệp vụ.

Ví dụ, phương thức trả `false`, trả HTTP response mang mã lỗi như một giá trị bình thường, hoặc tự bắt ngoại lệ rồi trả kết quả dự phòng vẫn có thể được aspect coi là success. Muốn đếm trạng thái nghiệp vụ như “từ chối thanh toán” khi không có ngoại lệ, hãy đặt phép đo theo trạng thái nghiệp vụ rõ ràng thay vì suy ra từ tag `result`.

### 6.4. recordFailuresOnly không tạo counter thành công để chờ ở 0

`failuresOnly(false)` không tăng counter. `failuresOnly(true)` tạo/tăng counter lỗi lên 1. Trong chương trình mới chạy, không có chuỗi `result=success` cho meter này:

```text
failures.only=1 success.series.present=false
```

Phân biệt “chưa có meter/chuỗi” với “chuỗi tồn tại và có giá trị 0”. Sự khác biệt này ảnh hưởng truy vấn dashboard, nhất là trước lần thực thi đầu tiên.

## 7. Phương thức bất đồng bộ: đợi hoàn tất công việc hay chỉ đợi trả về?

Một phương thức có thể trả future rất nhanh trong khi công việc chỉ hoàn tất sau đó. Nếu chỉ đo tới lúc trả về, số liệu có thể chỉ phản ánh thời gian tạo/lên lịch future.

Với kiểu trả về được khai báo là `CompletionStage` hoặc kiểu con như `CompletableFuture`, các aspect dùng trong bài có cơ chế gắn xử lý khi stage hoàn tất:

```text
Gọi qua proxy
    -> tạo mốc bắt đầu
    -> phương thức trả future đang chờ
    -> chưa ghi lần hoàn tất
    -> future hoàn tất bình thường hoặc bằng lỗi
    -> ghi timer/counter theo kết quả
```

Trong thí nghiệm, `await` không tự tạo luồng mới; nó trả future do bên gọi cung cấp. Điều này tách rõ **vòng đời kết quả bất đồng bộ** khỏi **cách lập lịch luồng**.

| Thời điểm | Timer count | Counter count | Ý nghĩa |
| --- | --- | --- | --- |
| Sau khi lấy future đầu tiên, future còn chờ | 0 | 0 | Chưa có lần hoàn tất |
| Sau khi future đầu tiên hoàn tất bình thường | 1 | 1 | Timer thành công có 25 ms |
| Sau khi future thứ hai hoàn tất bằng lỗi | 2 | 2 | Thêm timer lỗi 7 ms |

Chương trình chờ **future được trả ra từ proxy** bằng `join()`, bảo đảm các bước xử lý hoàn tất của chuỗi trả về đã chạy trước khi đọc số liệu. Không mặc định đối tượng future trả ra có cùng định danh tham chiếu với future nội bộ, vì aspect có thể trả một stage nối tiếp.

### Những giới hạn cần kiểm tra

- **Kiểu trả về trong chữ ký quan trọng.** Nếu chữ ký là `Object` hoặc chỉ là `Future`, không mặc định aspect nhận ra vòng đời `CompletionStage` dù đối tượng thực tế có thể liên quan tới xử lý bất đồng bộ.
- **Future không bao giờ hoàn tất:** timer thường/counter hoàn tất chưa có mẫu. Nếu cần theo dõi công việc đang chạy, phải chọn phép đo phù hợp cho trạng thái đó.
- **Hủy future:** thường biểu hiện qua hoàn tất đặc biệt/ngoại lệ; kiểm tra cách phân loại trên phiên bản và đường hủy cụ thể trước khi xây cảnh báo.
- **Reactor Mono/Flux:** không mặc định các aspect trên chờ publisher hoàn tất. Luồng reactive có vòng đời subscription riêng và cần phép đo bám vào vòng đời đó.
- **`@Async`:** là cơ chế lập lịch thực thi khác. Muốn dùng nó phải có cấu hình async tương ứng; thêm `@Timed` không tự tạo executor hoặc chạy phương thức trên luồng nền.

Trong ví dụ lỗi được hoàn tất bằng `IllegalStateException`; kết quả đã kiểm chứng có tag tương ứng. Không suy diễn rằng mọi lớp bọc ngoại lệ ở mọi đường async đều được bóc giống hệt nhau: dùng tên/tag thực tế của registry khi xây truy vấn.

## 8. Annotation phải phù hợp với kiểu meter và kết quả cần đọc

### 8.1. Timer thường và long-task timer có câu hỏi khác nhau

Mặc định `@Timed` dùng timer của các lần hoàn tất. Cấu hình:

```java
@Timed(value = "app.catalog.rebuild.active", longTask = true)
```

chọn `LongTaskTimer` cho phương thức được gắn annotation. Nó hữu ích khi cần biết có bao nhiêu tác vụ dài đang hoạt động và thời lượng hiện tại của chúng, không phải bộ đếm lịch sử hoàn tất tương đương timer thường.

Không đọc `LongTaskTimer` bằng giả định `Timer.count()` hay trộn cùng tên với timer thường. Nếu cần cả lịch sử hoàn tất và trạng thái đang chạy, thiết kế hai phép đo có tên và mục đích rõ ràng.

### 8.2. Bật phân vị hoặc histogram có chủ đích

Ví dụ khai báo khi thực sự cần phân bố thời lượng:

```java
@Timed(
    value = "app.search.execute",
    histogram = true,
    percentiles = {0.50, 0.95}
)
```

Đây là ví dụ các thuộc tính có trên annotation Micrometer dùng trong bài. Histogram phục vụ phân tích phân bố ở hệ giám sát có hỗ trợ; các percentile do ứng dụng tính không thể lấy trung bình đơn giản để ra p95 gộp nhiều instance. Bật thêm thống kê làm tăng chi phí, nên chọn theo câu hỏi quan sát thay vì bật mọi thứ cho mọi phương thức.

### 8.3. Annotation ghép và tag lấy từ tham số

Không tự gói `@Timed`/`@Counted` vào annotation riêng rồi mặc định aspect gốc sẽ nhận ra mọi meta-annotation. Tài liệu Micrometer 1.13 nêu giới hạn hỗ trợ này; cách dễ kiểm chứng là đặt trực tiếp annotation được aspect hiểu lên phương thức thực thi.

`@MeterTag` cũng không tự bảo đảm tham số xuất hiện thành tag. Với TimedAspect, cần cấu hình `MeterTagAnnotationHandler` phù hợp. Đó là phần mở rộng riêng; ví dụ chính chỉ dùng `extraTags` cố định để giới hạn số chuỗi và tập trung kiểm chứng cơ chế aspect.

Nếu bổ sung tag từ tham số, chuẩn hóa về tập hữu hạn như loại tác vụ hoặc kết quả phân loại. Tạo một chuỗi mới cho từng ID yêu cầu làm số lượng chuỗi tăng theo lượng dữ liệu.

## 9. Thứ tự aspect quyết định ý nghĩa phép đo

Ngoài metrics, cùng phương thức có thể chịu ảnh hưởng của retry, transaction, async hoặc các interceptor khác.

Ví dụ với retry:

```text
Timer ở ngoài Retry:
    timer bắt đầu -> thử 1 -> thử 2 -> thành công -> timer dừng
    => một lần thao tác tổng thể

Timer ở trong Retry:
    thử 1 -> timer lần 1
    thử 2 -> timer lần 2
    => hai lần thử
```

Hai cách đều có thể hợp lý nhưng trả lời câu hỏi khác nhau. Tương tự, vị trí đo so với transaction ảnh hưởng việc thời gian commit có nằm trong phép đo và lỗi commit có được quan sát ở ranh giới đó hay không. Vị trí so với async ảnh hưởng phạm vi thời gian được nhìn thấy, chẳng hạn thời gian chờ lập lịch.

Không dựa vào thứ tự viết annotation trên mã nguồn để kết luận thứ tự advice. Khi nhiều cơ chế phối hợp, kiểm tra cấu hình proxy/advisor và thử một tình huống có kết quả xác định. Nếu cần phân biệt “toàn thao tác” và “từng lần thử”, đặt tên meter theo đúng hai ranh giới đó.

Các số liệu của thí nghiệm không phụ thuộc thứ tự tương đối giữa TimedAspect và CountedAspect: trên phương thức async, cả hai cuối cùng đều theo dõi sự hoàn tất của chuỗi kết quả. Với nghiệp vụ có thêm interceptor khác, phải xác minh lại ranh giới thực tế.

## 10. Xác minh qua Actuator và chẩn đoán khi thiếu số liệu

Trong ứng dụng web Spring Boot đã tích hợp cấu hình aspect, có thể mở endpoint metrics cho cấu hình cục bộ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Sau khi gọi một phương thức nghiệp vụ qua bean được inject, kiểm tra bằng **tên Micrometer trong mã**, không phải tên đã đổi sang định dạng Prometheus:

```shell
curl "http://localhost:8080/actuator/metrics/app.invoice.generate"
curl "http://localhost:8080/actuator/metrics/app.invoice.generate?tag=exception:none"
```

Đây là yêu cầu kiểm tra cho ứng dụng đã có phương thức mang tên meter tương ứng, không phải endpoint do chương trình Spring thuần tự tạo. Địa chỉ, cổng, base path và yêu cầu xác thực phụ thuộc ứng dụng đang chạy.

Registry thường chỉ có meter sau khi đã có lần ghi phù hợp. Với timer async, hãy hoàn tất công việc trước khi tìm số liệu hoàn tất. Lọc theo `exception`, `method` hoặc các tag đã xác minh để đọc đúng chuỗi.

| Triệu chứng | Điều cần kiểm tra trước | Hướng sửa |
| --- | --- | --- |
| Có annotation nhưng không có meter | Có bean TimedAspect/CountedAspect và AOP hoạt động không? | Bổ sung cấu hình còn thiếu, dùng registry của ứng dụng |
| Bean có proxy nhưng vẫn không có số liệu | Proxy có advisor của đúng metrics aspect không? | Không dùng việc có proxy làm bằng chứng duy nhất |
| Chỉ lời gọi ngoài lớp được đo | Có self-invocation không? | Đặt ranh giới đo ở phương thức ngoài hoặc bean cộng tác phù hợp |
| Đối tượng chạy nhưng không có metrics | Có đang dùng `new` ở nơi gọi không? | Dùng tham chiếu bean qua Spring |
| Bật proxy dựa trên lớp thì khởi tạo lỗi | Lớp có final hoặc không thể tạo proxy không? | Chọn cấu trúc lớp/phương thức phù hợp hoặc kiểm tra phương án proxy interface |
| Counter success vẫn tăng khi nghiệp vụ báo thất bại | Phương thức có thực sự ném lỗi hay chỉ trả một giá trị? | Định nghĩa phép đo theo trạng thái nghiệp vụ cần đếm |
| Timer async quá ngắn | Chữ ký trả về, vòng đời stage và ranh giới advisor | Theo dõi stage phù hợp hoặc đo trực tiếp ở vòng đời thật |
| Số lần ghi tăng gấp đôi | Aspect đăng ký nhiều lần hoặc đã có cơ chế đo khác | Giữ đúng một cơ chế cho mỗi ranh giới cần đo |
| Actuator không thấy số liệu nhưng registry khác có | Có tạo registry riêng ngoài registry được xuất không? | Dùng registry được inject thống nhất |

HTTP server, client hoặc thư viện đã có instrumentation riêng có thể đo các ranh giới khác với service. Trước khi gắn aspect rộng lên controller hoặc toàn ứng dụng, kiểm tra metrics đã có để tránh đo trùng hoặc đặt cùng tên cho hai loại meter. Tài liệu [Metrics của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint) giải thích cách đọc endpoint theo tên và tag.

## 11. Thực hành để kiểm tra hiểu đúng cơ chế

1. **Xóa bean TimedAspect trong thí nghiệm, giữ CountedAspect.** Các counter vẫn có thể hoạt động, nhưng các lệnh đọc timer sẽ không tìm thấy meter. Điều này tách được “AOP có hoạt động” khỏi “đúng aspect đã được đăng ký”.
2. **Đặt @Timed lên selfInvoke bằng một tên khác.** Lời gọi ngoài vào selfInvoke tạo timer cho phương thức ngoài; timer demo.work vẫn không được tăng bởi lời gọi nội bộ. Giải thích vì sao không có mâu thuẫn.
3. **Gọi event(false) ba lần và event(true) một lần trên context mới.** Kỳ vọng counter success bằng 3 và failure bằng 1. Nếu đổi phương thức lỗi thành trả false bình thường, phải đánh giá lại ý nghĩa tag result.
4. **Lấy future rồi chưa complete.** Xác nhận chưa có lần hoàn tất; sau đó hoàn tất và chờ future trả từ proxy trước khi đọc count.
5. **So sánh nhu cầu đếm và đo thời gian.** Nếu timer đã trả lời đủ cả thời lượng và số lần hoàn tất, giải thích vì sao có thể bỏ counter trùng ranh giới.

Mục tiêu là xác định được annotation nào được aspect nào xử lý, lời gọi nào thực sự đi qua proxy và thời điểm nào được coi là hoàn tất. Khi ba điều này rõ ràng, số liệu mới có ý nghĩa để kiểm tra và vận hành.
