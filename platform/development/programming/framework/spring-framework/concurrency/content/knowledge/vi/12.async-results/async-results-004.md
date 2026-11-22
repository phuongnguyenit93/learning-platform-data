# Vai trò giá trị Future tạm từ phương thức đích với Future do proxy trả về trong Spring @Async

## 1. Vấn đề: tại sao một phương thức @Async phải tự trả về Future nếu proxy đã trả Future?

Trong Spring Framework, một phương thức gắn `@Async` có thể khai báo kiểu trả về `Future<T>` hoặc `CompletableFuture<T>`. Khi gọi qua Spring AOP proxy, **caller nhận một Future đại diện cho lần thực thi bất đồng bộ**; Future này do hạ tầng Spring/executor tạo để theo dõi tác vụ, không nhất thiết là chính đối tượng Future được tạo trong phần thân phương thức đích.

Đọc đoạn mã sau:

```java
@Async("workExecutor")
public CompletableFuture<String> calculate() {
    String value = expensiveCalculation();
    return CompletableFuture.completedFuture(value);
}
```

Đây là fragment, cần một Spring-managed bean, cấu hình `@EnableAsync`, executor tên `workExecutor` và hàm `expensiveCalculation()` có thật. Hai câu hỏi thường xuất hiện:

1. Nếu method đã trả `CompletableFuture.completedFuture(value)` — một future **đã hoàn tất** — tại sao caller vẫn có thể thấy Future **đang pending**?
2. Nếu đã có `CompletableFuture` do target tạo ra, Spring còn phải tạo Future của proxy để làm gì?

Câu trả lời: có **hai vai trò** và thường có **hai đối tượng**.

- **Future tạm của target (target-side temporary Future):** object trả về từ phần thân method sau khi nó đã tính toán, dùng để chuyển giá trị hoặc lỗi cho cơ chế advice đang xử lý task trên worker.
- **Future thực tế của proxy (caller-facing async Future):** object Spring trả ngay cho caller khi chuyển lời gọi thành task trên executor; nó đại diện cho quá trình thực thi bao gồm cả việc method đích chưa bắt đầu hoặc vẫn đang chạy.

Đây là điểm được giải thích ngay trong Javadoc `org.springframework.scheduling.annotation.Async` của Spring 6.2: method đích vẫn cần thỏa chữ ký `Future`, nên có thể trả một handle tạm chỉ mang giá trị sau khi tính toán; proxy cung cấp handle bất đồng bộ thật cho client.

**Nguyên tắc nhớ nhanh:** *Future tạm giúp method giữ đúng hợp đồng trả về và chuyển kết quả; Future proxy giúp caller quan sát thời gian hoàn tất của lần gọi bất đồng bộ.*

## 2. Hai tầng xử lý: call boundary và result handoff

Để hiểu đúng, cần chia lời gọi `@Async` thành hai phần.

### 2.1. Lời gọi đi qua proxy

Một service khác hoặc caller nhận bean từ Spring context:

```java
Future<String> clientFuture = workService.calculate();
```

Nếu `workService` là proxy của Spring và method đủ điều kiện được advice, async interceptor chọn executor rồi **submit** phần gọi method đích. Nó trả về một `Future` tương ứng với task đã gửi. Điều này không phải khẳng định caller đã có kết quả; task có thể còn nằm trong queue hoặc đang chạy.

### 2.2. Phần thân method thực thi ở worker

Trên worker, Spring gọi target method. Method phải tuân thủ kiểu trả về đã khai báo:

```java
@Async("workExecutor")
public Future<String> calculate() {
    String computed = doWork();
    return CompletableFuture.completedFuture(computed);
}
```

Đây là fragment: `doWork()` là logic nghiệp vụ, không phải lời gọi tự sinh của Spring. Sau khi chạy `doWork()`, target trả một `Future<String>` đã hoàn tất, mang `computed`.

### 2.3. Async interceptor chuyển kết quả ra Future của caller

Trong mô hình Spring Framework 6.2, sau khi target method trả về:

1. Advice lấy object kết quả từ invocation.
2. Nếu đó là `Future<?>`, advice có thể gọi `get()` trên Future target để lấy giá trị hoặc lỗi.
3. Kết quả/exception này được dùng để hoàn tất task trong executor.
4. `Future` mà caller đã nhận từ proxy trở thành completed/failed tương ứng.

Hình dung:

```text
Caller thread                        Spring proxy                Worker thread
    |                                     |                            |
    | call @Async method                  |                            |
    |------------------------------------>|                            |
    |                                     | submit invocation task     |
    |                                     |--------------------------->|
    |<------------------------------------|                            |
    | caller-facing Future<T>             |                   invoke target method
    | (often still pending)               |                            |
    |                                     |                   compute business value
    |                                     |                            |
    |                                     |                 return temporary Future<T>
    |                                     |                            |
    |                                     |                   unwrap temporary future
    |                                     |                     (get value or error)
    |                                     |                            |
    | caller Future completes             |<-------- completion -------|
    |                                     |                            |
    | callerFuture.get() -> T             |                            |
```

**Không hiểu sai:** target không trực tiếp “gửi” object Future tạm cho caller bằng Java return theo đường gọi thông thường. Trong proxy mode, Spring intercept lời gọi và cung cấp **một kết quả proxy-level**. Giá trị cuối cùng có thể giống nhau, nhưng object identity, thời điểm hoàn tất và trách nhiệm theo dõi khác nhau.

## 3. Future tạm có bắt buộc đã hoàn thành không?

Trong pattern phổ biến, **nên trả Future đã hoàn tất** sau khi tính toán:

```java
return CompletableFuture.completedFuture(value);
```

Nó không tạo task mới và không tự chuyển công việc sang thread khác. Bản thân method đã được chuyển sang worker **nhờ @Async proxy**, vì vậy tạo một `CompletableFuture.completedFuture(...)` ở cuối method là cách hợp lý để thỏa chữ ký và bàn giao kết quả.

Tuy nhiên một target method có thể trả một `Future` chưa hoàn thành. Trong cơ chế interceptor của Spring 6.2, worker có thể phải chờ `targetFuture.get()`, khiến worker bị chiếm cho đến khi Future tạm hoàn tất.

Ví dụ sai về hiệu quả sử dụng pool (đây là **minh họa anti-pattern**, không phải chương trình độc lập):

```java
@Async("workExecutor")
public CompletableFuture<String> load() {
    return CompletableFuture.supplyAsync(
            () -> slowBlockingCall(),
            anotherExecutor);
}
```

Ở đây lời gọi bên ngoài đã được đưa vào `workExecutor`, còn `supplyAsync` lại gửi công việc sang `anotherExecutor`. Với Spring proxy/execution bridge, worker đầu tiên có thể phải chờ kết quả của Future bên trong. Đó là **hai lần scheduling**, không phải tự động tối ưu hay nonblocking.

Nếu `anotherExecutor` là chính một pool nhỏ đang bị task cha chiếm hết, việc chờ Future con có thể gây **thread starvation deadlock**. Nếu thực sự cần pipeline bất đồng bộ nhiều bước, hãy thiết kế rõ tầng orchestration, chọn executor phù hợp, hoặc dùng `CompletableFuture` composition/async APIs ngoài cách bọc một `@Async` method không cần thiết.

**Ngoại lệ hợp lý:** có những tích hợp trả Future từ API hiện có. Khi đó vẫn phải hiểu worker sẽ xử lý kết quả đó ra sao và kiểm tra tải; không mặc nhiên kỳ vọng mọi tầng là nonblocking.

## 4. Chữ ký trả về: void, Future và CompletableFuture

Spring `@Async` trong proxy mode thông thường chỉ hỗ trợ các nhóm kiểu trả về phù hợp:

| Kiểu method khai báo | Future do target cần trả | Caller quan sát | Điểm lưu ý |
| --- | --- | --- | --- |
| `void` | Không có | Không có result handle từ method | Exception không thể truyền bằng Future; dùng error handler/monitoring |
| `Future<T>` | Một `Future<T>` tạm, thường đã hoàn tất | `Future<T>` thực tế của proxy | Caller dùng `get()`, `isDone()`, `cancel()` |
| `CompletableFuture<T>` | Một `CompletableFuture<T>` tạm, thường `completedFuture(value)` | `CompletableFuture<T>` thực tế của proxy | Có thể chain `thenApply`, `thenCompose`, `exceptionally` |

`CompletableFuture<T>` là một subtype của `Future<T>` nên được hỗ trợ. Ngược lại, một method khai báo riêng `CompletionStage<T>` (không phải subtype của `Future`), `String`, `Mono<T>` hay đối tượng nghiệp vụ không được mặc định coi là kiểu trả về hợp lệ cho Spring `@Async` thông thường. Reactor có cơ chế concurrency riêng, không nên nhầm API.

### 4.1. Khi nào chọn Future<T>?

Dùng khi caller chỉ cần đợi và lấy kết quả bằng `get()`:

```java
@Async("workExecutor")
public Future<Integer> count() {
    int count = calculateCount();
    return CompletableFuture.completedFuture(count);
}
```

Đây là fragment cần `calculateCount()`. Dù target dùng `CompletableFuture` tạm, caller chỉ có thể dựa vào contract `Future<Integer>` nếu method được khai báo như vậy. Không ép kiểu Future proxy thành `CompletableFuture` rồi mặc định nó tương thích — hãy khai báo `CompletableFuture<Integer>` từ đầu nếu cần composition.

### 4.2. Khi nào chọn CompletableFuture<T>?

Dùng nếu caller muốn kết hợp kết quả mà không gọi `get()` ngay:

```java
@Async("workExecutor")
public CompletableFuture<Integer> countAsync() {
    int count = calculateCount();
    return CompletableFuture.completedFuture(count);
}
```

Caller có thể:

```java
CompletableFuture<String> displayed = service.countAsync()
        .thenApply(number -> "count=" + number)
        .exceptionally(ex -> "unavailable");
```

Các fragment yêu cầu `calculateCount()` và biến `service` thích hợp. `thenApply` không nhất thiết chạy trên worker khác; callback có thể chạy trên thread hoàn tất stage nếu dùng biến thể không có hậu tố `Async`. Vì vậy chọn `CompletableFuture` để **kết hợp kết quả**, không nên suy ra mỗi stage sẽ tạo thread mới.

### 4.3. Không yêu cầu tự tạo thread trong target

Khi đã dùng `@Async` qua proxy, target không cần `new Thread(...)` hay `CompletableFuture.supplyAsync(...)` chỉ để “làm cho nó async”. Phần chuyển sang executor đã xảy ra trước khi target bắt đầu chạy.

## 5. Ví dụ thực nghiệm chạy được: so sánh Future tạm và Future proxy

Ví dụ sau dùng **Java 21, Maven và Spring Framework 6.2.1**, không cần Spring Boot. Nó kiểm chứng bốn tình huống:

1. Method khai báo `Future<String>` trả Future tạm hoàn tất, trong khi Future proxy vẫn pending vì worker còn chờ một latch.
2. Method khai báo `CompletableFuture<String>` cũng có hai object và hai thời điểm hoàn tất có thể khác nhau.
3. Method đích trả một CompletableFuture **chưa hoàn tất**; Future proxy chỉ hoàn tất khi Future đích được giải phóng.
4. Future tạm hoàn tất lỗi; caller nhìn thấy lỗi tương ứng qua Future proxy.

### 5.1. Cấu trúc Maven

```text
spring-async-future-bridge-demo/
├── pom.xml
└── src/main/java/demo/FutureBridgeDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-async-future-bridge-demo</artifactId>
  <version>1.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
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
          <mainClass>demo.FutureBridgeDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

### 5.2. Tệp Java hoàn chỉnh

**Tệp `src/main/java/demo/FutureBridgeDemo.java`:**

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class FutureBridgeDemo {
    public static class Signals {
        final AtomicReference<Future<String>> targetFuture = new AtomicReference<>();
        final AtomicReference<CompletableFuture<String>> targetCompletable =
                new AtomicReference<>();
        final AtomicReference<CompletableFuture<String>> targetPending =
                new AtomicReference<>();
        final CountDownLatch futureReady = new CountDownLatch(1);
        final CountDownLatch futureRelease = new CountDownLatch(1);
        final CountDownLatch completableReady = new CountDownLatch(1);
        final CountDownLatch completableRelease = new CountDownLatch(1);
        final CountDownLatch pendingReady = new CountDownLatch(1);
    }

    public static class WorkService {
        private final Signals signals;

        public WorkService(Signals signals) {
            this.signals = signals;
        }

        @Async("workExecutor")
        public Future<String> loadFuture() throws InterruptedException {
            Future<String> temporary = CompletableFuture.completedFuture("F:42");
            signals.targetFuture.set(temporary);
            signals.futureReady.countDown();
            signals.futureRelease.await();
            return temporary;
        }

        @Async("workExecutor")
        public CompletableFuture<String> loadCompletable()
                throws InterruptedException {
            CompletableFuture<String> temporary =
                    CompletableFuture.completedFuture("CF:ok");
            signals.targetCompletable.set(temporary);
            signals.completableReady.countDown();
            signals.completableRelease.await();
            return temporary;
        }

        @Async("workExecutor")
        public CompletableFuture<String> pendingTarget() {
            CompletableFuture<String> temporary = new CompletableFuture<>();
            signals.targetPending.set(temporary);
            signals.pendingReady.countDown();
            return temporary;
        }

        @Async("workExecutor")
        public CompletableFuture<String> failedTarget() {
            return CompletableFuture.failedFuture(
                    new IllegalArgumentException("bad-input"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {
        @Bean("workExecutor")
        public ThreadPoolTaskExecutor workExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("async-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        public Signals signals() {
            return new Signals();
        }

        @Bean
        public WorkService workService(Signals signals) {
            return new WorkService(signals);
        }
    }

    private static void await(CountDownLatch latch, String label)
            throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timeout waiting for " + label);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            WorkService service = context.getBean(WorkService.class);
            Signals signals = context.getBean(Signals.class);
            try {
                Future<String> callerFuture = service.loadFuture();
                await(signals.futureReady, "futureReady");
                System.out.println("futureTargetDone=" +
                        signals.targetFuture.get().isDone());
                System.out.println("futureProxyPending=" + !callerFuture.isDone());
                System.out.println("futureDistinct=" +
                        (callerFuture != signals.targetFuture.get()));
                signals.futureRelease.countDown();
                System.out.println("futureValue=" +
                        callerFuture.get(5, TimeUnit.SECONDS));

                CompletableFuture<String> callerCompletable =
                        service.loadCompletable();
                await(signals.completableReady, "completableReady");
                System.out.println("completableTargetDone=" +
                        signals.targetCompletable.get().isDone());
                System.out.println("completableProxyPending=" +
                        !callerCompletable.isDone());
                System.out.println("completableDistinct=" +
                        (callerCompletable != signals.targetCompletable.get()));
                signals.completableRelease.countDown();
                System.out.println("completableValue=" +
                        callerCompletable.get(5, TimeUnit.SECONDS));

                CompletableFuture<String> callerPending = service.pendingTarget();
                await(signals.pendingReady, "pendingReady");
                System.out.println("pendingProxyBefore=" +
                        !callerPending.isDone());
                signals.targetPending.get().complete("P:ready");
                System.out.println("pendingValue=" +
                        callerPending.get(5, TimeUnit.SECONDS));

                CompletableFuture<String> failure = service.failedTarget();
                try {
                    failure.get(5, TimeUnit.SECONDS);
                    throw new AssertionError("Expected failure");
                } catch (ExecutionException ex) {
                    System.out.println("failedCause=" +
                            ex.getCause().getClass().getSimpleName());
                }
            } finally {
                signals.futureRelease.countDown();
                signals.completableRelease.countDown();
                CompletableFuture<String> pending = signals.targetPending.get();
                if (pending != null && !pending.isDone()) {
                    pending.completeExceptionally(
                            new IllegalStateException("cleanup"));
                }
            }
        }
    }
}
```

**Vì sao có bean `Signals` riêng?** Đây là harness kiểm chứng hai phía của lời gọi. `WorkService` bị Spring proxy; việc đọc trực tiếp các field gắn với object proxy không nhất thiết đọc cùng state của target instance. Do đó test đặt `CountDownLatch` và `AtomicReference` vào một **bean Signals riêng**, được inject vào target và cũng lấy từ context ở caller. Đây là kỹ thuật test/điều phối minh họa, **không phải lời khuyên lưu toàn bộ state tác vụ production trong một singleton**.

### 5.3. Lệnh chạy

Trong thư mục dự án có `pom.xml`:

```bash
mvn -q -DskipTests compile exec:java
```

Yêu cầu Maven và JDK 21 trở lên. Thuộc tính `maven.compiler.release=21` khiến mã Java được biên dịch theo mức ngôn ngữ Java 21.

**Output đã kiểm chứng với Spring Framework 6.2.1:**

```text
futureTargetDone=true
futureProxyPending=true
futureDistinct=true
futureValue=F:42
completableTargetDone=true
completableProxyPending=true
completableDistinct=true
completableValue=CF:ok
pendingProxyBefore=true
pendingValue=P:ready
failedCause=IllegalArgumentException
```

Các dòng in từ chương trình, không bao gồm log phụ nếu môi trường Maven/JVM tự xuất thông báo.

## 6. Giải thích từng nhóm kết quả

### 6.1. Future<T>: target hoàn tất nhưng proxy chưa

Lúc worker vào `loadFuture()`:

```java
Future<String> temporary = CompletableFuture.completedFuture("F:42");
signals.targetFuture.set(temporary);
signals.futureReady.countDown();
signals.futureRelease.await();
return temporary;
```

`temporary.isDone()` là `true` ngay sau `completedFuture(...)`. Nhưng worker vẫn chờ `futureRelease`, nên **phương thức đích chưa trả** và task của interceptor chưa hoàn tất. Vì thế:

```text
futureTargetDone=true
futureProxyPending=true
futureDistinct=true
```

Hai đối tượng độc lập có trạng thái khác nhau tại cùng thời điểm. Sau khi caller mở latch, target trả Future tạm, interceptor lấy giá trị và đưa nó ra Future proxy. Caller nhận `F:42`.

### 6.2. CompletableFuture<T>: vẫn có hai vai trò

`loadCompletable()` lặp lại ý tưởng, chỉ đổi chữ ký sang `CompletableFuture<String>`:

```text
completableTargetDone=true
completableProxyPending=true
completableDistinct=true
completableValue=CF:ok
```

Dù cùng một kiểu `CompletableFuture<String>`, object mà target tạo **không phải** object được caller nhận từ proxy trong ví dụ. Cả hai đều là Future, nhưng có trách nhiệm khác nhau.

Điều này giải thích vì sao code `return CompletableFuture.completedFuture(value)` ở cuối `@Async` method **không vô hiệu hóa tính bất đồng bộ** của lời gọi: việc chạy trên executor được quyết định ở proxy boundary; target chỉ đóng gói giá trị sau khi xử lý.

### 6.3. Future tạm còn pending

Method `pendingTarget()` tạo một `CompletableFuture<>` chưa hoàn tất rồi trả nó. Lúc đó:

```text
pendingProxyBefore=true
```

Khi caller hoàn tất temporary bằng:

```java
signals.targetPending.get().complete("P:ready");
```

interceptor có thể lấy giá trị và hoàn tất proxy Future; caller đọc được:

```text
pendingValue=P:ready
```

Phép thử cho thấy **proxy Future phụ thuộc vào trạng thái hoàn tất của target Future** trong cơ chế bridge của Spring 6.2. Với Future tạm chưa xong, worker có thể đang phải chờ `get()`. Đây là lý do nên cảnh giác với method trả Future nền khác rồi chờ lồng nhau trên pool nhỏ.

### 6.4. Future tạm hoàn tất lỗi

`failedTarget()` trả:

```java
return CompletableFuture.failedFuture(
        new IllegalArgumentException("bad-input"));
```

Caller gọi `failure.get(...)` trên Future proxy và nhận `ExecutionException` với nguyên nhân `IllegalArgumentException`, nên chương trình in:

```text
failedCause=IllegalArgumentException
```

Không hiểu rằng target và proxy có cùng một exception wrapper object. Điểm cần quan sát là **nguyên nhân nghiệp vụ** có thể được chuyển qua ranh giới proxy/worker và xuất hiện khi caller đọc kết quả.

## 7. Các thời điểm hoàn tất khác nhau và vì sao test dễ sai

Giả sử caller gọi `service.calculate()` khi pool chưa có worker rảnh. Lời gọi thường trả về proxy Future sau khi task được chấp nhận, nhưng việc chạy trên worker có thể chưa bắt đầu.

Có thể xảy ra chuỗi:

1. `t0`: caller nhận Future proxy trạng thái pending.
2. `t1`: worker bắt đầu chạy target method.
3. `t2`: target tính xong và tạo temporary `completedFuture(value)`.
4. `t3`: target trả temporary.
5. `t4`: interceptor unwrap kết quả.
6. `t5`: Future proxy hoàn tất để caller nhận được `value`.

Trong ví dụ có latch, `t2 < t3` được kéo giãn có chủ đích để chứng minh `temporary.isDone() == true` trong khi `proxyFuture.isDone() == false`.

Trong ứng dụng thực, một phép tính rất nhanh có thể khiến proxy Future đã `isDone()==true` ngay khi caller nhìn vào, mà lời gọi **vẫn thật sự đã được chạy qua executor**. Vì thế, không thể dùng duy nhất `isDone()` ngay sau call để kết luận proxy đã hoặc chưa thực thi bất đồng bộ.

Để kiểm chứng concurrency, ưu tiên latch/Phaser kiểm soát mốc hoặc instrumentation đo thời điểm submit/bắt đầu/hoàn tất; đừng chỉ dựa vào `Thread.sleep(...)`.

## 8. Exception từ target Future được chuyển thế nào?

Có hai nguồn lỗi cần phân biệt.

### 8.1. Lỗi phát sinh trong phần thân target

Ví dụ:

```java
@Async("workExecutor")
public CompletableFuture<String> failFast() {
    throw new IllegalStateException("invalid");
}
```

Khi đi qua proxy, method body chạy trên executor. Với kiểu `Future`/`CompletableFuture`, caller thường quan sát lỗi qua handle async, chẳng hạn `future.get()` ném `ExecutionException` hoặc `future.join()` ném `CompletionException`.

### 8.2. Target trả Future đã hoàn tất lỗi

Ví dụ đã kiểm chứng với `failedFuture(...)`. Interceptor lấy kết quả từ temporary Future; nếu Future tạm báo lỗi, lỗi được chuyển vào kết quả async dành cho caller. Đừng để ý quá mức đến lớp exception bao ngoài: hãy xem `getCause()` phù hợp.

### 8.3. Lỗi ngay ở thời điểm submit

Nếu executor/queue quá tải hoặc đã shutdown, Spring có thể từ chối task **trước khi proxy trả một Future hữu ích** bằng `TaskRejectedException`. Đây không phải lỗi tính toán trong Future tạm của method, bởi method chưa chắc đã chạy.

Mẫu kiểm soát:

```java
try {
    CompletableFuture<String> result = service.calculateAsync();
    // Tiếp tục xử lý result khi nó hoàn thành.
} catch (TaskRejectedException ex) {
    // Xử lý trường hợp executor không nhận task.
}
```

Đây là fragment cần service có method `calculateAsync()` và import `TaskRejectedException`. Retry phải có giới hạn; không dùng retry vô hạn khiến quá tải tăng thêm.

## 9. Vì sao không nên trả CompletableFuture.supplyAsync(...) trong @Async tùy tiện?

Khi method `@Async` đã được Spring chuyển lên pool A, lời gọi `CompletableFuture.supplyAsync(..., poolB)` bên trong tạo thêm một tác vụ trên pool B. Nếu target trả Future của pool B mà chưa hoàn tất, bridge ở worker pool A có thể chờ kết quả pool B.

Hệ quả:

- Mất một worker của pool A để chờ công việc ở pool B.
- Nếu pool B cũng có giới hạn chặt hoặc chính là pool A, việc chờ có thể gây starvation/deadlock.
- Khó theo dõi timeout, cancellation, MDC, transaction và exception vì có thêm boundary.
- Không tự tạo ra I/O nonblocking: tác vụ gọi JDBC/HTTP blocking vẫn chiếm một worker nào đó.

**Hướng tốt hơn:** nếu công việc là đồng bộ và muốn đưa nó sang worker, chỉ tính toán trong `@Async` method rồi `return CompletableFuture.completedFuture(value)`. Nếu đã có API tự trả `CompletableFuture` và mục tiêu là composition không chặn worker, cân nhắc bỏ bọc `@Async` dư thừa và trả/combine future theo đúng API composition.

Với pipeline nhiều bước thực sự, thiết kế rõ executor ownership và cách nối stage thay vì vô thức kết hợp cả annotation và `supplyAsync`.

## 10. Proxy boundary: khi không có Future do proxy tạo

Toàn bộ so sánh target Future/proxy Future ở trên **chỉ đúng khi lời gọi thực sự qua Spring async advice**. Nếu caller gọi method trực tiếp trên đối tượng không được Spring quản lý hoặc target tự gọi method nội bộ:

```java
public CompletableFuture<String> selfCall() {
    return this.calculateAsync(); // Bỏ qua proxy trong AdviceMode.PROXY.
}
```

Đây là fragment; `calculateAsync()` phải thuộc cùng class. Ở chế độ `@EnableAsync` mặc định (`AdviceMode.PROXY`), `this.calculateAsync()` không tạo một lượt interceptor mới. Method chạy theo lời gọi Java bình thường và có thể trả **chính Future do method tạo**, vì không có proxy bridge tại điểm gọi.

Không nên kết luận rằng “Future proxy và Future tạm là cùng object” chỉ vì quan sát một ca self-invocation; đó là đường gọi **khác cơ chế**.

Checklist cho proxy:

- Có `@EnableAsync` hoặc XML `<task:annotation-driven>` trong context?
- Bean có được lấy/inject qua Spring container, thay vì `new` thủ công?
- Method có được gọi **từ bên ngoài** qua bean reference/proxy?
- Method/return type có phù hợp proxy mode? Method private/final không phải chỗ đặt `@Async` đáng tin.
- `@Async("workExecutor")` có khớp bean executor?
- Có gọi `Future.get()` ngay trên request thread khiến caller vẫn block không?

Nếu self-invocation là vấn đề, ưu tiên tách async method sang bean khác hoặc gửi task tường minh bằng `AsyncTaskExecutor`; đừng chỉ tăng kích thước pool để chữa lỗi call path.

## 11. Future proxy có bảo đảm cùng object hoặc cùng triển khai với target không?

**Không.** Object Future target có thể là một `CompletableFuture.completedFuture(...)`; Future proxy được tạo theo kiểu trả về khai báo và executor thực tế.

Trong Spring Framework 6.2:

- Nếu method khai báo `Future<T>`, Spring có thể dùng `AsyncTaskExecutor.submit(...)` để tạo Future của task.
- Nếu method khai báo `CompletableFuture<T>`, Spring có thể dùng `AsyncTaskExecutor.submitCompletable(...)` để cung cấp handle phù hợp cho caller.
- Bên trong worker, advice lấy giá trị/exception từ Future target rồi kết thúc task.

Vì vậy, không giả định `targetFuture == proxyFuture`, không làm business logic phụ thuộc class thực tế của Future, không ép kiểu `Future<T>` sang `CompletableFuture<T>` khi method chỉ hứa `Future<T>`. Chỉ dựa vào hợp đồng kiểu public đã khai báo.

**Chú ý khả năng thay đổi phiên bản:** cấu trúc bridge chi tiết và wrapper class là implementation detail của Spring; các bất biến cần dựa trên hợp đồng `@Async` và kết quả thực thi, không phải tên class nội bộ.

## 12. Timeout và cancel ở hai lớp Future

Giả sử caller có:

```java
CompletableFuture<String> callerFuture = service.calculateAsync();
```

Caller có thể dùng `get(2, TimeUnit.SECONDS)`, `orTimeout(...)`, `cancel(...)` hoặc các stage xử lý lỗi. Nhưng những thao tác này chủ yếu tác động lên **handle caller đang cầm**. Không tự suy rằng tất cả Future bên dưới hoặc tác vụ downstream sẽ được hủy/rollback.

Những ranh giới cần phân biệt:

- **Caller timeout:** hết thời gian đợi kết quả, không đồng nghĩa worker đã dừng.
- **Caller Future cancellation:** trạng thái cancel của proxy handle; mức độ interrupt worker phụ thuộc implementation và loại Future.
- **Target temporary Future cancellation:** trạng thái của Future được trả từ target; không phải lúc nào cũng được nối tự động hai chiều với proxy Future.
- **I/O/network cancellation:** có thể cần timeout/cancel ở chính HTTP client, JDBC, socket hoặc API bên ngoài.

Riêng `CompletableFuture.cancel(true)` của JDK không bảo đảm interrupt thread đang chạy chỉ vì tham số `mayInterruptIfRunning=true`; không nên dựa vào đó làm cơ chế dừng chắc chắn. Đối với những công việc có side effect, thiết kế idempotency, cleanup, timeout ở downstream và cách lưu trạng thái cuối cùng.

Đừng cho rằng Future tạm là nguồn sự thật để client hủy công việc, vì client thông thường **không cầm** Future tạm đó trong proxy mode.

## 13. Đoạn code xử lý kết quả cho caller

Caller có thể lựa chọn blocking get có timeout:

```java
try {
    String value = result.get(3, TimeUnit.SECONDS);
    apply(value);
} catch (ExecutionException ex) {
    Throwable original = ex.getCause();
    // Ghi nhận lỗi nghiệp vụ.
} catch (TimeoutException ex) {
    // Có thể task vẫn chạy; quyết định timeout/cancel/retry.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Cho caller kết thúc theo chính sách interruption.
}
```

Đây là fragment; `result` là `Future<String>`, `apply` là hàm xử lý nghiệp vụ, các import java.util.concurrent thích hợp phải có.

Nếu method khai báo `CompletableFuture<String>`, bạn có thể chọn:

```java
service.calculateAsync()
       .thenApply(String::trim)
       .thenAccept(value -> save(value))
       .exceptionally(ex -> {
           logError(ex);
           return null;
       });
```

Đây là fragment, cần `save(...)` và `logError(...)`. Với CompletableFuture, phương thức `exceptionally` ở cuối nhận `Throwable` và phải trả giá trị khớp kiểu stage tại vị trí đó (ở đây stage từ `thenAccept` là `Void`, nên `return null` phù hợp). Không giả định callback tự sử dụng executor `@Async` ban đầu; các stage không hậu tố `Async` có thể chạy trên thread hoàn tất future.

Nếu muốn caller không bị chặn, ưu tiên composition/callback hơn là `get()` ngay sau lời gọi.

## 14. Quan sát thread, lỗi và tính nhất quán

Sau khi gọi qua proxy, code target chạy trên worker của executor (với cấu hình async pool như bài). Do đó:

- **ThreadLocal, MDC, SecurityContext:** không mặc nhiên được copy từ caller. Cần propagation phù hợp cho correlation/log/security nếu nghiệp vụ yêu cầu.
- **Transaction:** giao dịch gắn với thread của caller không tự chuyển nguyên vẹn vào worker. Nếu task có DB work, cấu hình transaction boundary riêng ở worker.
- **Side effects:** khi caller nhận Future proxy, công việc có thể còn chưa chạy. Không trả lời “đã xử lý thành công” chỉ vì không có exception tại thời điểm gọi method.
- **Rejection:** executor có queue và max workers; quá tải có thể ném lỗi từ chối ở đường submit.
- **Shutdown:** in-memory executor không có durability. Nếu tiến trình chết trước khi Future hoàn tất, không tự có khả năng replay.
- **Error reporting:** với method trả `Future`, caller cần đọc kết quả hoặc có chỗ khác quan sát completion. Với `void` async method, dùng `AsyncUncaughtExceptionHandler` hoặc cơ chế log/metrics phù hợp.

Những vấn đề này thuộc vòng đời của **proxy Future và task thật**, không được giải quyết chỉ bằng cách target trả `completedFuture(value)`.

## 15. Vì sao ví dụ dùng Signals bean riêng thay vì field của proxy?

Spring AOP có thể đưa ra một **proxy object** khác với **target object**. Với class-based proxy, việc đọc trực tiếp field qua reference proxy không tương đương một method getter đang được advice/delegate vào target.

Ví dụ minh họa nguy cơ:

```java
WorkService service = context.getBean(WorkService.class);
// Đừng mặc định service.someField là cùng field instance
// mà method của target đọc/ghi khi gọi qua proxy.
```

Trong phép thử bài này, ta muốn quan sát cả Future target và Future proxy. Vì vậy `Signals` là một **bean riêng**:

- Target nhận `Signals` qua constructor injection.
- Caller lấy **cùng bean Signals** từ ApplicationContext.
- Các `CountDownLatch` và `AtomicReference` nằm trên object Signals được chia sẻ có chủ đích.
- Caller không phải đọc field của proxy để suy trạng thái target.

Đây là một kỹ thuật kiểm thử rõ ràng, cho phép so sánh identity và timing có kiểm soát. Trong business code thực tế, tránh để một singleton Signals chứa state của nhiều request; phải gắn task ID, state riêng cho từng request và bảo đảm thread-safety.

## 16. Những lỗi phổ biến

| Hiểu sai/thiết kế sai | Hậu quả | Cách hiểu hoặc sửa |
| --- | --- | --- |
| Thấy `completedFuture(value)` trong target nên nghĩ lời gọi không async | Nhầm Future tạm với Future proxy | Async được quyết định ở proxy boundary; target chỉ chuyển giá trị |
| Nghĩ target Future và caller Future luôn cùng object | Sai identity và thời điểm hoàn tất | So sánh theo contract/kết quả, không dựa identity |
| Target trả `new CompletableFuture<>()` rồi không ai complete | Worker có thể chờ mãi và caller Future pending | Trả completedFuture sau khi tính xong hoặc hoàn tất future có chiến lược rõ |
| Bọc `supplyAsync(...)` bên trong mọi method `@Async` | Double scheduling, worker chờ Future con | Không tạo tầng async thứ hai nếu không cần |
| Chờ Future con trên cùng pool một worker | Starvation deadlock | Tránh nested blocking, dùng composition đúng |
| Cast proxy `Future<T>` thành `CompletableFuture<T>` khi method chỉ hứa Future | Có thể `ClassCastException` | Khai báo `CompletableFuture<T>` từ API nếu cần chaining |
| Gọi `this.asyncMethod()` và so sánh Future | Không qua advice; Future của target có thể được trả trực tiếp | Gọi qua Spring-managed bean khác |
| Dùng `isDone()` làm phép thử duy nhất | Task nhanh có thể hoàn tất trước khi kiểm tra | Dùng latch/instrumentation chứng minh trình tự |
| Nghĩ `get(timeout)` tự hủy task | Worker có thể tiếp tục chạy | Quyết định cancel/cleanup riêng |
| Nghĩ `cancel(true)` chắc chắn dừng mọi work | Nhiều tác vụ/CF không hỗ trợ interrupt như mong đợi | Thiết kế cooperative cancellation và timeout downstream |
| Bỏ qua `ExecutionException.getCause()` | Không thấy lỗi thực sự từ target | Truy nguyên exception cause, log đúng chỗ |
| Coi kết quả submit thành công là đã xử lý xong | Có thể task còn trong queue | Theo dõi Future proxy, metrics và trạng thái nghiệp vụ |
| Đọc field của Spring proxy như field target | Test sai/hang vì state không trùng | Sử dụng state bean riêng hoặc API getter đúng ý đồ |
| Dùng in-memory Future thay cho durable job tracking | Không có replay qua restart | Dùng outbox/broker/status store khi cần |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Method `@Async` trả `CompletableFuture.completedFuture("done")`. Caller có thể nhận một Future `isDone() == false` không?

Có. Future tạm của target đã hoàn tất, nhưng task proxy còn có thể chưa chạy đến đoạn đó hoặc chưa kết thúc. Hai Future có vai trò và thời điểm hoàn tất khác nhau.

**Câu 2.** Nếu method khai báo `Future<Integer>`, có nên cast Future proxy sang `CompletableFuture<Integer>` để dùng `thenApply` không?

Không nên. Hợp đồng public chỉ hứa `Future<Integer>`; object thực tế do executor/proxy quyết định. Hãy khai báo kiểu `CompletableFuture<Integer>` ngay từ đầu nếu cần composition.

**Câu 3.** Vì sao target vẫn phải trả Future dù có async interceptor?

Vì Java method phải tuân thủ chữ ký trả về. Future tạm là cách target bàn giao giá trị/lỗi để hạ tầng Spring chuyển sang Future do proxy cung cấp.

**Câu 4.** Nếu target trả một `CompletableFuture` chưa hoàn tất từ executor khác, chuyện gì có thể xảy ra?

Bridge trên worker Spring có thể phải chờ Future target hoàn tất. Điều này tiêu tốn worker, đặc biệt dễ gây starvation khi các task phụ thuộc nhau trong pool nhỏ.

**Câu 5.** Timeout trên Future proxy có đảm bảo Future tạm được hủy không?

Không. Timeout khi đọc `get(timeout)` chỉ áp dụng cho thời gian chờ của caller. Cancellation và propagate đến target/downstream phụ thuộc thiết kế và implementation; không mặc định là hai chiều.

**Câu 6.** Nếu thấy proxy bean tồn tại mà `this.asyncMethod()` chạy đồng bộ, có mâu thuẫn với kiến thức hai Future không?

Không. Self-invocation bypass proxy, nên không có caller-facing proxy Future mới cho lời gọi đó. Đó là một call path khác.

**Câu 7.** Test cần chứng minh hai Future khác trạng thái thì dùng gì?

Tạo Future tạm hoàn tất trong worker, dùng latch giữ target trước khi return, lấy Future proxy từ caller, sau đó so sánh trạng thái/identity và giải phóng latch. Không dùng sleep với thời lượng ngẫu nhiên.

## 18. Checklist khi thiết kế @Async có kết quả

- **Chữ ký:** `Future<T>` hay `CompletableFuture<T>`? Có thực sự cần nhận/chains kết quả không?
- **Target method:** tính toán công việc trên worker rồi trả một Future tạm thích hợp, thường `CompletableFuture.completedFuture(value)`.
- **Caller:** giữ Future của proxy và dùng nó để lấy kết quả/exception; không trông đợi object identity bằng Future tạm.
- **Proxy boundary:** đã bật `@EnableAsync`, bean do Spring quản lý, không phải self-invocation?
- **Không nested blocking:** target có vô tình gửi thêm task vào chính pool rồi đợi Future con không?
- **Timeout/cancel:** có timeout ở caller và ở I/O thực tế, biết ý nghĩa cancellation của từng tầng?
- **Exception:** có phân biệt lỗi trong target/temporary Future với `TaskRejectedException` tại submit?
- **Vận hành:** quan sát queue wait, execution time, active workers, rejection, errors, shutdown?
- **Context:** transaction/MDC/security và dữ liệu input có được xử lý đúng ở thread worker?
- **Độ bền:** nếu tác vụ phải tồn tại qua restart, đã dùng cơ chế lưu trạng thái/durable queue phù hợp?

## 19. Kết luận

Trong Spring `@Async`, **Future tạm do phương thức đích trả về** và **Future do Spring proxy trả về cho caller** không có cùng trách nhiệm:

1. Future tạm giữ đúng chữ ký method và chuyển giá trị hoặc lỗi từ lúc worker hoàn thành phần tính toán.
2. Future proxy là kết quả của lời gọi bất đồng bộ ở ranh giới AOP/executor; caller dùng nó để chờ, kiểm tra trạng thái, xử lý lỗi và composition.
3. Chúng có thể khác object, khác thời điểm hoàn tất; Future tạm đã completed **không có nghĩa** proxy Future cũng đã completed.
4. Trả một Future tạm chưa xong có thể làm worker phải chờ kết quả; tránh double scheduling và nested blocking nếu không có yêu cầu thực sự.
5. Toàn bộ bridge chỉ xảy ra nếu lời gọi được Spring async advice chặn; self-invocation trong chế độ proxy là một trường hợp khác.

### Tài liệu tham khảo

- [Spring Framework 6.2.1 — @Async Javadoc](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework 6.2.1 — @EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2.1 — AsyncExecutionAspectSupport](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/aop/interceptor/AsyncExecutionAspectSupport.html)
- [Java 21 — CompletableFuture API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)