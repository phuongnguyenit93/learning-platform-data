# Truyền ngữ cảnh qua luồng, tác vụ bất đồng bộ và Reactor

## 1. Vì sao đổi luồng làm mất mối liên hệ giữa các thao tác?

Một yêu cầu HTTP có thể đang được quan sát trên luồng xử lý ban đầu, sau đó gửi công việc sang executor hoặc tiếp tục trong một chuỗi Reactor. Mã nghiệp vụ vẫn chạy đúng, nhưng thao tác ở nơi mới có thể không biết nó thuộc yêu cầu nào. Khi đó, các phép đo hoặc span con có thể thiếu mối liên hệ cha–con; log cũng có thể thiếu thông tin tương quan nếu hạ tầng logging dựa vào ngữ cảnh hiện tại.

Ngữ cảnh quan sát là thông tin để xác định thao tác đang diễn ra và mối liên hệ của nó với các thao tác khác. Cần phân biệt ba việc:

- **Tạo observation:** bắt đầu một phép quan sát cho một thao tác.
- **Đưa observation vào scope:** làm cho observation đó trở thành observation hiện tại trong một phạm vi thực thi.
- **Truyền ngữ cảnh:** đưa thông tin ngữ cảnh hiện có qua một ranh giới thực thi, rồi khôi phục nó ở nơi cần sử dụng.

Truyền ngữ cảnh không tự tạo thêm một phép đo cho mọi tác vụ. Nếu cần đo riêng công việc con, hãy tạo observation con khi ngữ cảnh cha đã được khôi phục. Micrometer cũng phân biệt rõ việc truyền ngữ cảnh với việc tạo observation. [Micrometer: instrumentation và context propagation](https://docs.micrometer.io/micrometer/reference/1.13/observation/instrumenting.html).

Trong mã đồng bộ, observation hiện tại thường được truy cập qua trạng thái gắn với luồng. Sang luồng khác, không thể giả định trạng thái ấy đã có sẵn. Trong Reactor, cùng một chuỗi còn có thể chạy qua nhiều luồng, còn một luồng có thể phục vụ nhiều subscription. Vì vậy, chọn đúng nơi lưu ngữ cảnh là điều quyết định.

## 2. Ba cơ chế lưu giữ ngữ cảnh cần phân biệt

| Cơ chế | Ngữ cảnh gắn với đâu? | Điều cần lưu ý |
| --- | --- | --- |
| `ThreadLocal` | Luồng đang chạy | Đổi luồng không tự có giá trị của luồng gửi; thread pool còn tái sử dụng luồng |
| `ContextSnapshot` | Các giá trị được chụp tại một thời điểm | Chỉ chứa thông tin mà accessor đã đăng ký có thể đọc; phải khôi phục trong phạm vi được đóng đúng |
| Reactor `Context` | Subscriber/subscription trong chuỗi reactive | Dữ liệu đi theo chuỗi xử lý, không phụ thuộc một luồng cố định |

`ObservationRegistry` và `ContextRegistry` cũng là hai loại registry khác nhau:

- `ObservationRegistry` phục vụ observation: handler, cấu hình và observation hiện tại.
- `ContextRegistry` biết cách đọc/ghi các loại ngữ cảnh thông qua accessor.
- `ObservationThreadLocalAccessor` là cầu nối cho observation hiện tại.
- `ContextSnapshotFactory` dùng các accessor đã đăng ký để tạo snapshot.
- `ContextSnapshot.Scope` giới hạn thời gian khôi phục các giá trị lên luồng đích.

Một snapshot không quét và sao chép mọi `ThreadLocal` trong JVM. Nó cũng không phải bản sao sâu của toàn bộ đối tượng nghiệp vụ: giá trị được mang đi có thể vẫn là tham chiếu đến cùng một đối tượng. Không xem propagation là cơ chế đồng bộ hóa dữ liệu dùng chung. [Mục đích và các thành phần của Context Propagation](https://docs.micrometer.io/context-propagation/reference/1.1/purpose.html).

Không nên dùng `InheritableThreadLocal` như cách sửa tổng quát cho thread pool: sự kế thừa khi tạo luồng khác với việc truyền ngữ cảnh cho từng tác vụ gửi vào một luồng đã tồn tại. Chuyển sang virtual thread cũng không tự thay thế việc xác định ranh giới và vòng đời ngữ cảnh.

## 3. Quy trình đúng: capture → gửi tác vụ → khôi phục → dọn phạm vi

```text
Luồng gửi, đang có ngữ cảnh A
  -> capture snapshot A tại ranh giới gửi công việc
  -> gửi tác vụ đã được bọc

Luồng thực thi
  -> nhớ trạng thái trước đó
  -> khôi phục A
  -> chạy công việc
  -> finally: khôi phục trạng thái trước đó

Tác vụ tiếp theo trên cùng luồng
  -> không được nhìn thấy A do tác vụ trước để sót
```

### 3.1. Capture khi ngữ cảnh mong muốn còn hiện tại

Chỉ gọi `Observation.start(...)` chưa đồng nghĩa với việc observation đó đã trở thành hiện tại trên luồng. Trong mã theo lệnh (imperative), cần một scope đang mở, hoặc một lời gọi như `observe(...)` quản lý scope, trước khi capture giá trị hiện tại.

Ví dụ cốt lõi, dùng trong một phương thức đã có `parent`, `factory` và executor:

```java
try (Observation.Scope scope = parent.openScope()) {
    var snapshot = factory.captureAll();
    executor.submit(snapshot.wrap(task));
}
```

Đây là đoạn minh họa ranh giới capture, không phải một chương trình độc lập. Việc đợi tác vụ và quản lý vòng đời `parent` phải được quyết định ở lớp bao quanh; không suy ra rằng đóng scope ở luồng gửi đã kết thúc công việc bất đồng bộ.

Không chụp snapshot một lần khi ứng dụng khởi động rồi tái sử dụng cho mọi yêu cầu. Factory và executor có thể dùng lâu dài, nhưng snapshot ngữ cảnh của từng yêu cầu phải được lấy tại thời điểm phù hợp.

### 3.2. Scope phải được mở và đóng tại nơi thực thi

Có thể để `snapshot.wrap(...)` quản lý phạm vi hoặc tự khôi phục bằng:

```java
try (var restored = snapshot.setThreadLocals()) {
    runBusinessWork();
}
```

`snapshot` và `runBusinessWork()` thuộc mã bao quanh. Khi ra khỏi khối, các giá trị trước đó của luồng được khôi phục; nếu trước đó không có giá trị thì không được để sót giá trị vừa truyền vào. Khối vẫn phải đóng khi công việc ném ngoại lệ. Không mở một scope trên luồng A rồi chuyển chính scope đó sang luồng B để đóng. [Ví dụ capture và khôi phục bằng scope](https://docs.micrometer.io/context-propagation/reference/1.1/usage.html).

Tùy chính sách, factory có thể dùng `clearMissing(true)` để tạm xóa các giá trị của accessor đã đăng ký nhưng vắng trong snapshot. Đó là cách tránh việc tác vụ mới vô tình dùng một giá trị cũ trên luồng đích trong phạm vi được khôi phục. Nó không thay thế trách nhiệm đóng scope, và không xóa mọi `ThreadLocal` ngoài các accessor mà factory biết.

### 3.3. Scope và thời gian sống của observation là hai việc khác nhau

Đóng scope không phải `stop()` observation. Snapshot cũng không tự kéo dài thời gian sống của observation, tự kết thúc nó hoặc tự ghi nhận lỗi nghiệp vụ.

Nếu tác vụ phải thuộc một observation cha còn sống, bên quản lý cần đợi hoặc phối hợp để observation cha kết thúc đúng thời điểm. Với công việc thực sự tách rời vòng đời yêu cầu, cần thiết kế observation riêng và quan hệ nhân quả phù hợp. Không giữ đối tượng request hoặc snapshot của request vô thời hạn chỉ để làm cho log có cùng mã tương quan.

Khi nhiều tác vụ chạy song song, không sửa tùy tiện cùng một `Observation.Context` như một bản đồ dùng chung. Propagation giúp tìm ngữ cảnh; nó không khiến các thao tác cập nhật tùy ý trở nên an toàn khi chạy đồng thời.

## 4. Executor, CompletableFuture và @Async

### 4.1. Executor thô không có nghĩa là executor đã được nối ngữ cảnh

Gửi một `Runnable` hoặc `Callable` sang `ExecutorService` thông thường chỉ gửi công việc. Lambda có thể giữ tham chiếu tới registry, nhưng `registry.getCurrentObservation()` vẫn được đánh giá trên luồng thực thi.

Có hai cách thường dùng:

- Capture snapshot ở bên gửi, rồi bọc từng tác vụ.
- Dùng executor hoặc decorator thực hiện capture cho mỗi lần gửi công việc.

Micrometer có các wrapper executor; với Spring Framework 6.1, `ContextPropagatingTaskDecorator` cung cấp cơ chế bọc tác vụ dựa trên snapshot. Phải gắn decorator vào executor thực sự được sử dụng. Chỉ tạo một đối tượng decorator mà không nối nó với executor chưa làm thay đổi đường chạy. [API ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.1.5/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html).

### 4.2. CompletableFuture có nhiều ranh giới khác nhau

`CompletableFuture.supplyAsync(...)` không truyền ngữ cảnh chỉ vì bên gọi đang có observation. Khi không chỉ định executor, nó thường sử dụng hạ tầng mặc định của JDK; hạ tầng đó không tự biết cấu hình decorator riêng của ứng dụng.

Ví dụ dưới đây chọn executor rõ ràng; `raw`, `factory` và `work` đã được khai báo trong mã bao quanh:

```java
Executor propagated = task -> raw.execute(factory.captureAll().wrap(task));
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(work, propagated);
```

Ở đây snapshot được lấy mỗi lần `execute` nhận tác vụ, trên luồng đang gọi `execute`.

Đối với các callback nối sau như `thenApplyAsync`, phải xét thêm **luồng nào gửi callback vào executor**. Một callback có thể được đăng ký khi ngữ cảnh A đang mở, nhưng chỉ được gửi vào executor sau đó bởi luồng hoàn tất future nguồn. Capture ở thời điểm executor nhận tác vụ sẽ phản ánh ngữ cảnh của luồng gửi lúc ấy, không mặc nhiên là ngữ cảnh A lúc đăng ký callback.

Nếu yêu cầu là giữ ngữ cảnh tại thời điểm đăng ký, cần chụp rõ ở thời điểm đó và khôi phục trong callback:

```java
var captured = factory.captureAll();
var next = source.thenApplyAsync(value -> {
    try (var scope = captured.setThreadLocals()) {
        return transform(value);
    }
}, raw);
```

Đây là mã minh họa trong phương thức đã có `source`, `factory`, `raw` và `transform`. Bên quản lý vẫn phải bảo đảm vòng đời ngữ cảnh được tham chiếu là phù hợp.

Callback không có hậu tố `Async` cũng không bảo đảm luôn chạy trên luồng đã đăng ký nó: nó có thể chạy trên luồng hoàn tất future. Hãy kiểm thử đường chạy thực tế thay vì suy luận từ tên phương thức.

### 4.3. @Async phải trỏ tới executor đã cấu hình

Với Spring, `@Async` thường hoạt động qua proxy. Cần gọi phương thức từ bean khác hoặc qua bean lấy từ context; một lời gọi nội bộ bằng `this` không tự đổi thành lời gọi bất đồng bộ qua proxy.

Cấu hình rõ tên executor và dùng `@Async("observedExecutor")` giúp xác định đúng đường chạy. Một decorator trên executor A không tự áp dụng cho executor B, `new Thread(...)`, common pool, mọi scheduler Reactor hoặc mọi lời gọi `parallelStream()`.

Propagation cũng không xử lý thay kết quả và ngoại lệ của `CompletableFuture`. Bên gọi vẫn cần quan sát future trả về. Nếu bắt ngoại lệ ở bên gọi, đừng giả định observation cha đã được tự đánh dấu lỗi chỉ nhờ việc khôi phục ngữ cảnh.

## 5. Thực nghiệm 1: thread pool, CompletableFuture và @Async

### 5.1. Chuẩn bị dependency

Hai chương trình trong bài dùng JDK 21, Spring Framework 6.1.8, Micrometer 1.13.0, Context Propagation 1.1.1 và Reactor 3.6.6. Các phiên bản thuộc thế hệ thư viện của Boot 3.3.0, được cố định cho thư mục thực nghiệm độc lập.

Tạo `pom.xml` trong một thư mục riêng:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>context-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.8</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-observation</artifactId>
            <version>1.13.0</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>context-propagation</artifactId>
            <version>1.1.1</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
        </dependency>
    </dependencies>
</project>
```

Maven giải quyết các dependency bắc cầu như `micrometer-commons` và `reactive-streams`. Đây là thí nghiệm Spring thuần để thấy rõ cơ chế. Trong ứng dụng Boot hiện có, hãy dùng dependency management của Boot thay vì sao chép toàn bộ danh sách phiên bản này.

### 5.2. Toàn bộ ThreadContextDemo.java

Lưu ở cùng thư mục với `pom.xml`, không khai báo package:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ThreadContextDemo {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(Config.class);
             var raw = Executors.newSingleThreadExecutor()) {
            var registry = context.getBean(ObservationRegistry.class);
            var factory = context.getBean(ContextSnapshotFactory.class);
            var asyncWork = context.getBean(AsyncWork.class);

            System.out.println("worker.before=" + await(raw.submit(() -> name(registry))));
            Observation parent = Observation.start("request.a", registry);
            try (var scope = parent.openScope()) {
                System.out.println("caller=" + name(registry));
                System.out.println("worker.raw=" + await(raw.submit(() -> name(registry))));

                var snapshot = factory.captureAll();
                Callable<String> read = () -> name(registry);
                System.out.println("worker.snapshot="
                        + await(raw.submit(snapshot.wrap(read))));

                Executor propagated = task ->
                        raw.execute(factory.captureAll().wrap(task));
                System.out.println("future.raw=" + await(CompletableFuture
                        .supplyAsync(() -> name(registry), raw)));
                System.out.println("future.propagated=" + await(CompletableFuture
                        .supplyAsync(() -> name(registry), propagated)));
                System.out.println("async=" + await(asyncWork.currentName()));

                try {
                    await(raw.submit(snapshot.wrap((Callable<String>) () -> {
                        throw new IllegalStateException("demo");
                    })));
                    throw new AssertionError("Expected task failure");
                } catch (ExecutionException ex) {
                    System.out.println("failure=" + ex.getCause().getClass().getSimpleName());
                }
                String after = await(raw.submit(() -> name(registry)));
                System.out.println("worker.after.failure=" + after);
                if (!"<none>".equals(after)) {
                    throw new AssertionError("Worker context leaked");
                }
            } finally {
                parent.stop();
            }
            String nextTask = await(asyncWork.currentName());
            System.out.println("async.next.task=" + nextTask);
            System.out.println("caller.after=" + name(registry));
            if (!"<none>".equals(nextTask) || registry.getCurrentObservation() != null) {
                throw new AssertionError("Unexpected next task context");
            }
        }
    }

    static String name(ObservationRegistry registry) {
        Observation current = registry.getCurrentObservation();
        return current == null ? "<none>" : current.getContext().getName();
    }

    static <T> T await(Future<T> future) throws Exception {
        return future.get(5, TimeUnit.SECONDS);
    }

    public static class AsyncWork {
        private final ObservationRegistry registry;

        public AsyncWork(ObservationRegistry registry) {
            this.registry = registry;
        }

        @Async("observedExecutor")
        public CompletableFuture<String> currentName() {
            return CompletableFuture.completedFuture(name(registry));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        ObservationRegistry observationRegistry() {
            var registry = ObservationRegistry.create();
            registry.observationConfig().observationHandler(
                    new ObservationHandler<Observation.Context>() {
                        @Override
                        public boolean supportsContext(Observation.Context context) {
                            return true;
                        }
                    });
            return registry;
        }

        @Bean
        ContextSnapshotFactory snapshots(ObservationRegistry registry) {
            var contexts = new ContextRegistry();
            contexts.registerThreadLocalAccessor(
                    new ObservationThreadLocalAccessor(registry));
            return ContextSnapshotFactory.builder()
                    .contextRegistry(contexts).clearMissing(true).build();
        }

        @Bean
        ThreadPoolTaskExecutor observedExecutor(ContextSnapshotFactory factory) {
            var executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("observed-");
            executor.setTaskDecorator(new ContextPropagatingTaskDecorator(factory));
            return executor;
        }

        @Bean
        AsyncWork asyncWork(ObservationRegistry registry) {
            return new AsyncWork(registry);
        }
    }
}
```

Handler tối giản làm cho registry thực sự xử lý observation trong thí nghiệm; nó không xuất metric hoặc trace ra hệ thống giám sát. `ContextRegistry` riêng chỉ đăng ký accessor cho observation, giúp thấy rõ loại dữ liệu nào đang được truyền.

Chương trình đợi tác vụ trong scope cha và dừng observation ở `finally`. Vì thế, các tác vụ trong thí nghiệm không bị bỏ chạy sau khi observation cha đã kết thúc.

### 5.3. Lệnh chạy và stdout

Trong PowerShell, chọn JDK 21 cho cả `javac` và `java`, rồi chạy lần lượt khi lệnh trước thành công:

```powershell
mvn org.apache.maven.plugins:maven-dependency-plugin:3.7.0:build-classpath "-Dmdep.outputFile=classpath.txt"
$demoClasspath = (Get-Content -Raw classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp "$demoClasspath" ThreadContextDemo.java
java -cp ".;$demoClasspath" ThreadContextDemo
```

Lần đầu cần tải dependency từ kho Maven. Dấu `;` là dấu phân cách classpath trên Windows; Linux/macOS dùng `:`.

Stdout của chương trình, không tính thông báo của Maven:

```text
worker.before=<none>
caller=request.a
worker.raw=<none>
worker.snapshot=request.a
future.raw=<none>
future.propagated=request.a
async=request.a
failure=IllegalStateException
worker.after.failure=<none>
async.next.task=<none>
caller.after=<none>
```

Các bằng chứng cần đọc cùng nhau:

| Kết quả | Điều được kiểm chứng |
| --- | --- |
| `caller=request.a` nhưng `worker.raw=<none>` | Observation hiện tại ở luồng gửi không tự có mặt trên luồng executor |
| `worker.snapshot=request.a` | Snapshot bọc callable khôi phục được observation |
| `future.raw=<none>`, `future.propagated=request.a` | CompletableFuture dùng đúng executor có propagation thì tìm được ngữ cảnh |
| `async=request.a` | Lời gọi qua proxy `@Async` sử dụng executor có decorator |
| `failure=IllegalStateException` | Ngoại lệ tác vụ vẫn đến bên chờ future |
| `worker.after.failure=<none>` | Tác vụ thô tiếp theo trên cùng executor không thấy observation bị để sót sau lỗi |
| `async.next.task=<none>` | Tác vụ `@Async` gửi sau khi scope cha đã đóng không mang ngữ cảnh của request trước |
| `caller.after=<none>` | Scope ở luồng gửi đã được đóng |

Không dùng tên thread hoặc thời gian chạy làm stdout cố định: chúng phụ thuộc môi trường. Kết quả về observation và phạm vi mới là điều thí nghiệm cần chứng minh.

## 6. Áp dụng executor đã cấu hình trong Spring Boot

Trong ứng dụng Boot, dùng registry do hạ tầng Actuator cung cấp. Không sao chép bean `observationRegistry()` của thí nghiệm để thay registry đã được Boot nối với metric/tracing.

Với build đã có plugin/BOM Boot, bảo đảm có các dependency phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:context-propagation'
}
```

Ứng dụng dùng Reactor còn cần dependency Reactor từ lựa chọn hạ tầng reactive của nó. Không cần chuyển một ứng dụng sang WebFlux chỉ để dùng task decorator.

Ví dụ cấu hình trong phạm vi quét bean của ứng dụng:

```java
package example.context;

import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncObservationConfig {
    @Bean("observedExecutor")
    ThreadPoolTaskExecutor observedExecutor(ObservationRegistry observations) {
        var contexts = new ContextRegistry();
        contexts.registerThreadLocalAccessor(
                new ObservationThreadLocalAccessor(observations));
        var snapshots = ContextSnapshotFactory.builder()
                .contextRegistry(contexts)
                .clearMissing(true)
                .build();

        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("observed-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator(snapshots));
        return executor;
    }
}
```

Trong bean dịch vụ khác, dùng `@Async("observedExecutor")` như lớp `AsyncWork` trong thí nghiệm. Spring quản lý khởi tạo và đóng `ThreadPoolTaskExecutor` khi nó là bean; không gọi `initialize()` thêm lần nữa trong phương thức tạo bean trên.

Factory ở đây dùng một `ContextRegistry` riêng, đăng ký rõ accessor với registry của Boot. Cấu hình này chủ động truyền **observation** cho executor này. Nếu ứng dụng dùng registry toàn cục và nhiều accessor đã được cấu hình sẵn, có thể dùng factory/decorator chung phù hợp; phải kiểm tra thực tế các accessor cần thiết đã có mặt.

Không suy ra rằng mọi giá trị MDC, ngữ cảnh bảo mật, giao dịch hoặc đối tượng request đều được sao chép. Tương quan log cần tích hợp tracing/logging phù hợp; những loại ngữ cảnh khác cần cơ chế riêng hoặc accessor được thiết kế đúng. Truyền observation không mở một giao dịch cơ sở dữ liệu ở luồng mới.

Thông số kích thước pool và hàng đợi ở ví dụ chỉ phục vụ cấu hình minh họa. Chọn lại theo loại công việc và cách xử lý quá tải của ứng dụng. Việc capture/khôi phục có chi phí; nên đo tác động với khối lượng tác vụ thực tế, nhất là khi có rất nhiều tác vụ cực nhỏ.

## 7. Reactor Context và cầu nối tới ThreadLocal

### 7.1. Ngữ cảnh của subscription khác ngữ cảnh của luồng lắp ráp chuỗi

Trong Reactor, subscription là một lượt đăng ký thực thi chuỗi; subscriber là bên đăng ký nhận tín hiệu. Nên dùng `Context`/`ContextView` để mang thông tin theo subscription. `Context` là cấu trúc bất biến theo nghĩa các thao tác thêm/xóa trả về một context mới; giá trị chứa bên trong vẫn có thể là đối tượng có thể thay đổi.

`Mono.deferContextual(...)` đọc context khi subscribe. `contextWrite(...)` bổ sung context cho các operator phía upstream trong phạm vi chuỗi tương ứng. Vị trí đặt operator vì vậy có ý nghĩa; một biến được đặt trên ThreadLocal khi tạo `Mono` không tự thành dữ liệu của mọi subscription sau này.

`publishOn` và `subscribeOn` có thể thay đổi nơi thực thi, nhưng không biến ThreadLocal thành nơi lưu ngữ cảnh đáng tin cho toàn bộ pipeline. Tham chiếu ngữ cảnh cần đi theo subscription và được khôi phục khi mã imperative cần đọc nó.

### 7.2. Chế độ mặc định và chế độ tự động

Khi có thư viện `context-propagation` tương thích, Reactor có cầu nối giữa Reactor Context và các ThreadLocal đã đăng ký.

- Ở chế độ mặc định có giới hạn, một số operator như `handle` và `tap` có hỗ trợ khôi phục; không giả định mọi callback trong mọi operator đều có ThreadLocal đúng.
- Chế độ tự động được bật bằng `Hooks.enableAutomaticContextPropagation()`, hoặc cấu hình tương ứng của Boot. Cơ chế này khôi phục các ThreadLocal đã đăng ký dựa vào Reactor Context trong các phạm vi Reactor hỗ trợ.

Trong Boot 3.3.x, cấu hình:

```yaml
spring:
  reactor:
    context-propagation: auto
```

Thuộc tính này dành cho cầu nối Reactor; nó không tự gắn task decorator lên mọi executor mà ứng dụng tự tạo. [Spring Boot: context propagation](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Trong chương trình Reactor độc lập, bật hook một lần khi khởi động, trước các subscription cần áp dụng. Hook tác động toàn cục trong JVM và áp dụng cho subscription mới; không bật/tắt nó cho từng request. [Reactor 3.6.6: context propagation](https://projectreactor.io/docs/core/3.6.6/reference/#context.propagation).

### 7.3. contextWrite và contextCapture giải quyết hai hướng khác nhau

| Operator | Nguồn dữ liệu | Thời điểm và mục đích |
| --- | --- | --- |
| `contextWrite` | Giá trị đã biết hoặc context đang có | Đặt dữ liệu vào Reactor Context cho phạm vi upstream tương ứng |
| `contextCapture` | ThreadLocal đã đăng ký trên luồng subscribe | Chụp khi subscribe và đưa các giá trị vào Reactor Context |

Khi đưa observation đã biết vào Reactor Context, dùng khóa mà accessor hiểu, chẳng hạn `ObservationThreadLocalAccessor.KEY`. Khi đi từ mã imperative đang có scope sang Reactor, `contextCapture()` là một lựa chọn để đưa giá trị hiện tại vào context.

Cần phân biệt thời điểm tạo pipeline với thời điểm subscribe. Nếu scope chỉ mở khi tạo `Mono` rồi đã đóng trước lúc subscribe, `contextCapture()` không quay ngược thời gian để tìm ngữ cảnh cũ.

Trong chế độ tự động, các operator chặn như `Mono.block()` có hỗ trợ capture ngầm. Điều đó có thể khiến ví dụ dùng `block()` chạy đúng dù một ranh giới subscribe khác trong ứng dụng vẫn thiếu dữ liệu. Không suy ra rằng một lời gọi `subscribe()` tùy ý cũng có cùng cơ chế capture. Trong WebFlux, trả về chuỗi reactive để framework subscribe và bảo toàn context đã có, thay vì tự tạo một nhánh `subscribe()` tách rời.

Nếu chỉ cần đọc thông tin từ Reactor Context bằng `deferContextual`, không nhất thiết phải chuyển mọi thứ về ThreadLocal. Cầu nối hữu ích khi gọi thư viện imperative vốn trông đợi observation hiện tại ở luồng.

## 8. Thực nghiệm 2: cùng Reactor Context, hai chế độ khác nhau

Chương trình sau dùng các dependency ở phần 5. Nó chạy trong một JVM riêng, nên có thể chủ động bật/tắt hook để so sánh mà không ảnh hưởng ứng dụng khác.

### 8.1. Toàn bộ ReactorContextDemo.java

Lưu cạnh `pom.xml`:

```java
import java.time.Duration;

import io.micrometer.context.ContextRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import reactor.core.publisher.Hooks;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class ReactorContextDemo {
    public static void main(String[] args) {
        var registry = ObservationRegistry.create();
        registry.observationConfig().observationHandler(
                new ObservationHandler<Observation.Context>() {
                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return true;
                    }
                });

        var accessor = ObservationThreadLocalAccessor.getInstance();
        accessor.setObservationRegistry(registry);
        ContextRegistry.getInstance().registerThreadLocalAccessor(accessor);

        Scheduler worker = Schedulers.newSingle("reactor-demo");
        Observation parent = Observation.start("reactor.parent", registry);
        try {
            String limited = read(registry, worker)
                    .contextWrite(ctx -> ctx.put(ObservationThreadLocalAccessor.KEY, parent))
                    .block(Duration.ofSeconds(5));
            System.out.println("limited: " + limited);

            Hooks.enableAutomaticContextPropagation();

            String automatic = read(registry, worker)
                    .contextWrite(ctx -> ctx.put(ObservationThreadLocalAccessor.KEY, parent))
                    .block(Duration.ofSeconds(5));
            System.out.println("automatic: " + automatic);

            try (var scope = parent.openScope()) {
                String captured = read(registry, worker)
                        .contextCapture()
                        .block(Duration.ofSeconds(5));
                System.out.println("captured: " + captured);
            }

            String clean = Mono.fromCallable(() -> name(registry))
                    .subscribeOn(worker)
                    .block(Duration.ofSeconds(5));
            System.out.println("worker.next.subscription=" + clean);
            System.out.println("caller.after=" + name(registry));

            if (!"context=reactor.parent, current=<none>".equals(limited)
                    || !"context=reactor.parent, current=reactor.parent".equals(automatic)
                    || !"<none>".equals(clean)
                    || registry.getCurrentObservation() != null) {
                throw new AssertionError("Unexpected Reactor context");
            }
        } finally {
            parent.stop();
            worker.dispose();
            Hooks.disableAutomaticContextPropagation();
            ContextRegistry.getInstance()
                    .removeThreadLocalAccessor(ObservationThreadLocalAccessor.KEY);
        }
    }

    static Mono<String> read(ObservationRegistry registry, Scheduler worker) {
        return Mono.deferContextual(ctx -> Mono.fromCallable(() -> {
            Observation fromContext = ctx.get(ObservationThreadLocalAccessor.KEY);
            return "context=" + fromContext.getContext().getName()
                    + ", current=" + name(registry);
        }).subscribeOn(worker));
    }

    static String name(ObservationRegistry registry) {
        Observation current = registry.getCurrentObservation();
        return current == null ? "<none>" : current.getContext().getName();
    }
}
```

Registry được gắn với accessor để lời gọi `getCurrentObservation()` và cầu nối dùng cùng hệ quan sát. Việc đăng ký accessor và điều khiển hook ở đây là cấu hình tường minh cho chương trình độc lập. Trong Boot, hãy dùng tích hợp và registry mà ứng dụng đã thiết lập; không chạy các thao tác dọn hook toàn cục này trong xử lý request.

`read(...)` đọc observation từ Reactor Context qua `deferContextual`; phần callable chạy trên scheduler riêng và đồng thời đọc observation hiện tại từ registry. Cùng một kết quả trả về vì vậy cho thấy cả dữ liệu trong Context lẫn trạng thái ThreadLocal ở nơi xử lý.

### 8.2. Biên dịch và chạy

Dùng `classpath.txt` đã tạo ở thí nghiệm trước:

```powershell
$demoClasspath = (Get-Content -Raw classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp "$demoClasspath" ReactorContextDemo.java
java -cp ".;$demoClasspath" ReactorContextDemo
```

Stdout:

```text
limited: context=reactor.parent, current=<none>
automatic: context=reactor.parent, current=reactor.parent
captured: context=reactor.parent, current=reactor.parent
worker.next.subscription=<none>
caller.after=<none>
```

Giải thích:

1. **Limited:** Context đã chứa observation, nên đọc trực tiếp từ `ContextView` vẫn thành công. Callback callable trên luồng khác không tự có observation hiện tại ở chế độ này.
2. **Automatic:** Với subscription mới sau khi bật hook, observation trong Context được khôi phục để mã trong callback đọc qua registry.
3. **Captured:** Scope đang mở khi subscribe; `contextCapture()` đưa observation hiện tại vào Context. Trong chế độ tự động, `block()` cũng có capture ngầm, nên dòng này minh họa một ranh giới capture hợp lệ, không chứng minh rằng `contextCapture()` luôn bắt buộc trước `block()`.
4. **Next subscription:** Subscription tiếp theo trên cùng scheduler, không cung cấp observation cha, đọc được `<none>`. Không được dùng observation của subscription trước như ngữ cảnh mặc định.
5. **Caller after:** Scope imperative đã đóng và luồng gọi không còn observation hiện tại.

Ví dụ chỉ truyền một observation đang tồn tại, không tạo observation mới cho từng operator. Hai lần đọc được cùng tên không phải bằng chứng rằng đã tạo thêm hai span.

## 9. Những ranh giới mà propagation không tự xử lý thay

### 9.1. Lỗi, hủy và thời điểm kết thúc

Một scope propagation phải được dọn cả khi có lỗi. Với reactive, còn cần xét tín hiệu hủy. Nếu tự tạo observation cho một subscription, phải thiết kế việc tạo theo từng subscription và kết thúc đúng khi hoàn tất, lỗi hoặc hủy; không dùng một observation có trạng thái thay đổi được tạo sẵn ngoài pipeline cho mọi lượt subscribe.

Không mở một scope imperative rồi trả về một `Mono` chưa chạy và cho rằng scope ấy sẽ tự sống đến khi chuỗi hoàn tất. Hãy dùng Reactor Context và tích hợp reactive phù hợp. Trường hợp framework đã quản lý observation thì tránh thêm một vòng đời cạnh tranh.

Khôi phục ngữ cảnh cũng không tự hủy tác vụ con khi request bị hủy, không tự áp dụng timeout và không tự biến lỗi future thành lỗi observation. Những việc đó cần chính sách điều phối và instrumentation riêng.

### 9.2. Log, trace, transaction và bảo mật là những hợp đồng riêng

Quan sát được cùng một observation trên luồng mới chỉ chứng minh ngữ cảnh đó được truyền. Để có span xuất hiện ở backend còn cần tracing bridge, handler, exporter và cấu hình lấy mẫu. Để log có mã tương quan còn cần tích hợp logging tương ứng.

Không coi một snapshot observation là cách mang mọi quyền truy cập, phiên đăng nhập hoặc transaction sang luồng mới. Nếu ứng dụng cần truyền loại ngữ cảnh khác, hãy cấu hình và kiểm thử riêng cơ chế cho loại đó.

Qua ranh giới mạng hoặc message broker còn cần inject/extract ngữ cảnh bằng header/carrier và instrumentation của giao thức. `ContextSnapshot` dùng trong JVM không tự gửi thông tin qua HTTP hoặc Kafka.

## 10. Kiểm thử và khoanh vùng lỗi

Bộ kiểm thử thực tế nên bao gồm:

- Yêu cầu A truyền được đúng ngữ cảnh qua ranh giới cần hỗ trợ.
- Yêu cầu B chạy lại trên cùng pool/scheduler nhận đúng B, không nhận A.
- Tác vụ không có ngữ cảnh không dùng giá trị của yêu cầu trước.
- Tác vụ ném ngoại lệ vẫn khôi phục trạng thái của luồng.
- Các scope lồng nhau trả lại ngữ cảnh ngoài sau khi đóng.
- Chuỗi Reactor được subscribe lại, phát sinh lỗi và bị hủy đều có vòng đời phù hợp khi ứng dụng tự quản lý observation.
- Callback future hoàn tất trên một luồng khác vẫn theo đúng chính sách capture đã chọn.

Dùng đồng bộ hóa rõ ràng, timeout và assertion về observation/context; tránh dùng `Thread.sleep(...)` làm bằng chứng rằng propagation đúng.

| Hiện tượng | Cần kiểm tra |
| --- | --- |
| Luồng gửi có observation nhưng executor không có | Tác vụ có được capture/bọc không, có dùng đúng executor không |
| Snapshot không chứa observation mong muốn | Capture có diễn ra khi scope đang mở; accessor có trỏ đúng registry không |
| @Async chạy nhưng mất ngữ cảnh | Tên executor và decorator được gắn thực tế; không chỉ kiểm tra annotation |
| @Async không đổi luồng | Có gọi qua proxy, có bật cơ chế async, có tự gọi bằng `this` không |
| Future ban đầu đúng nhưng callback sau sai | Luồng gửi callback và thời điểm capture của từng giai đoạn |
| Reactor Context có giá trị nhưng registry trả null | Chế độ khôi phục, accessor, operator và vị trí ranh giới cần ThreadLocal |
| Reactor có lúc đúng khi block, có lúc sai khi subscribe khác | Capture khi subscribe và việc block có capture ngầm ở chế độ tự động |
| Dữ liệu của yêu cầu trước xuất hiện ở yêu cầu sau | Scope không đóng, snapshot dùng lại sai phạm vi, hoặc trạng thái có thể thay đổi bị dùng chung |
| Đã bật chế độ Reactor tự động nhưng executor riêng vẫn sai | Hai cơ chế độc lập; executor riêng vẫn cần nối propagation |
| Có ngữ cảnh nhưng không thấy span ở backend | Kiểm tra riêng cấu hình tracing và xuất dữ liệu |

## 11. Bài tập thực hành

1. Chạy nguyên bản hai chương trình và đối chiếu stdout.
2. Bỏ `setTaskDecorator(...)` trong thí nghiệm 1. Dự đoán và kiểm tra riêng dòng `async`; không thay đổi đường chạy của snapshot và executor bọc.
3. Chụp snapshot trước khi mở scope cha. Giải thích vì sao công việc bọc không nhận được observation mong muốn.
4. Thêm observation `request.b`, gửi tác vụ vào cùng pool rồi gửi một tác vụ không có scope. Kiểm tra lần lượt B và `<none>`.
5. Trong thí nghiệm Reactor, giữ `contextWrite` nhưng không bật hook. Giải thích vì sao đọc Context vẫn đúng trong khi đọc observation hiện tại ở callback có thể là `<none>`.
6. Thiết kế một callback `thenApplyAsync` được đăng ký ở luồng A nhưng future nguồn hoàn tất ở luồng B. So sánh capture lúc đăng ký với capture khi executor nhận tác vụ.

Khi đánh giá kết quả, hãy chỉ rõ ngữ cảnh được lấy từ đâu, được capture lúc nào, được khôi phục trong phạm vi nào và được dọn ở đâu.
