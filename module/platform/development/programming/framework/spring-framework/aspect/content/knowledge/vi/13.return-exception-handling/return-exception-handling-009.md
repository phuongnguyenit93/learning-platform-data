# Phân biệt phương thức đã trả Future/Publisher và công việc đã hoàn tất trong Spring Aspect

## 1. Vấn đề: `@AfterReturning` chạy rồi nhưng tác vụ đã hoàn tất chưa?

Trong **Spring AOP**, `@AfterReturning` chạy khi **lời gọi Java method được Spring proxy chặn đã trả về bình thường**. Nếu kiểu trả về là `Future<T>`, `CompletableFuture<T>`, `CompletionStage<T>`, `Mono<T>`, `Flux<T>` hoặc một `Publisher<T>`, method hoàn toàn có thể **trả ra một handle/mô tả công việc** trước khi kết quả bất đồng bộ hoặc reactive stream hoàn tất.

Ví dụ:

```java
@AfterReturning(
    pointcut = "execution(* com.example.jobs.JobService.start(..))",
    returning = "result",
    argNames = "result"
)
public void afterReturn(Object result) {
    System.out.println("Method đã trả về: " + result.getClass().getName());
}
```

Đây là **fragment trong một Spring `@Aspect` bean**, không phải chương trình Java độc lập. Dòng log này nói rằng lời gọi **`start(..)` qua proxy đã có normal return**. Nó **không tự chứng minh** rằng:

- `CompletableFuture` đã hoàn thành.
- Future đã thành công thay vì hoàn thành exceptionally hoặc bị cancel.
- `Mono`/`Flux` đã được subscribe.
- Publisher đã phát `onNext`, `onComplete` hoặc `onError`.
- Dữ liệu đã được gửi hết tới HTTP client.
- Transaction, remote call, message processing hoặc toàn bộ workflow bên ngoài đã hoàn tất.

Đây là một khác biệt nền tảng giữa **method-execution lifecycle** của Spring Aspect và **asynchronous/reactive processing lifecycle** của giá trị trả về.

**Phạm vi:** Bài tập trung vào `@AfterReturning`, `@AfterThrowing`, `@After`, `@Around`, `ProceedingJoinPoint` và thứ tự quan sát trong **Spring proxy-based AOP**. Những kiến thức Future/Reactive Streams được dùng để giải thích Spring Aspect, không biến bài thành hướng dẫn chung về concurrency hoặc Reactor.

## 2. Ba mốc khác nhau cần đặt tên chính xác

### 2.1. Method invocation kết thúc

Lời gọi qua Spring proxy:

```text
Caller
  -> Spring AOP proxy
     -> advice / target.method()
     <- target trả về một Future hoặc Publisher
     -> @AfterReturning có thể chạy
  <- caller nhận Future hoặc Publisher
```

Điều kiện `@AfterReturning` là **method trả về bình thường**. Nó không chờ một giá trị `T` nằm trong `Future<T>` hoặc Publisher xuất hiện sau này.

### 2.2. Future/CompletionStage hoàn thành

```text
method startFuture()
  |
  +--> tạo CompletableFuture<T> còn pending
  +--> return future                <-- Spring @AfterReturning ở đây
                                      caller đã có handle
...
executor / event / callback xử lý
  |
  +--> complete(value)
      hoặc completeExceptionally(error)
      hoặc cancel()
                                      <-- Future chuyển sang completed state
```

Một `Future` có thể đã complete trước lúc method return, có thể complete rất lâu sau hoặc không bao giờ complete. **Không giả định tất cả Futures luôn pending tại return**; ví dụ `CompletableFuture.completedFuture(value)` trả về object **đã hoàn thành**. Nhưng `@AfterReturning` vẫn **chỉ gắn với normal return của method**, không phải listener theo dõi trạng thái future.

### 2.3. Publisher được subscribe và phát terminal signal

Với một **cold Reactor `Mono`** thông thường:

```text
method makeMono()
  |
  +--> tạo Mono mô tả pipeline
  +--> return Mono                  <-- Spring @AfterReturning ở đây
                                     (có thể chưa xử lý dữ liệu)
...
consumer subscribe()
  |
  +--> onSubscribe / request
  +--> onNext(value) nếu có dữ liệu
  +--> onComplete() hoặc onError(error)
                                     <-- Terminal signal khi có
```

Với `Flux` có thể có **nhiều `onNext`**, terminal signal có thể đến rất lâu sau. Với **hot publisher**, công việc hoặc emission có thể xảy ra **trước khi subscriber mới đăng ký**; không được mô tả mọi Publisher là cold. Một subscription cũng có thể bị **cancel**, không phát terminal success/error cho subscriber theo cách thông thường.

**Bảng mốc tóm tắt:**

| Khái niệm | Mốc mà nó thực sự nói tới | Có đồng nghĩa hoàn tất công việc không? |
| --- | --- | --- |
| `@AfterReturning` | Spring-advised Java method trả bình thường | **Không**, nếu result là Future/Publisher chưa xử lý xong. |
| `@AfterThrowing` | Advised method **thoát ra bằng exception** | **Không tự bắt** lỗi được phát sau đó qua Future hoặc `onError`. |
| `@After` | Advised method thoát bình thường hoặc lỗi | **Không** phải callback terminal của Future/Publisher. |
| `future.isDone()` | Future completed/cancelled state | Có thể là thành công, lỗi hoặc cancellation; **không đồng nghĩa success**. |
| `future.join()` / `get()` | Chờ/đọc kết quả Future | Có thể block; exception wrapping cần xử lý. |
| `CompletionStage.whenComplete` | Callback khi stage hoàn thành | Quan sát thành công **hoặc** lỗi của stage. |
| Reactor `doOnSuccess` | Thành công của một `Mono` subscription | Có thể success rỗng; nhận `null` khi `Mono` complete empty. |
| Reactor `doOnError` | Publisher phát error signal | Là lỗi reactive, không nhất thiết Java method throw. |
| Reactor `doFinally` | Sau termination/cancellation theo semantics Reactor | Có thể thấy `ON_COMPLETE`, `ON_ERROR`, `CANCEL`. |

## 3. `@AfterReturning` bind giá trị nào?

Tài liệu Spring cho phép dùng `returning` để nhận object mà target invocation đã trả:

```java
@AfterReturning(
    pointcut = "execution(* com.example.jobs.JobService.startFuture(..))",
    returning = "future",
    argNames = "future"
)
public void returned(java.util.concurrent.CompletableFuture<?> future) {
    System.out.println("done=" + future.isDone());
}
```

Nếu `startFuture()` trả một `CompletableFuture` chưa hoàn tất, advice in `done=false` rồi **kết thúc**. Khi future complete về sau, **không có lần gọi `@AfterReturning` thứ hai chỉ vì completion**.

Điều tương tự với:

```java
@AfterReturning(
    pointcut = "execution(* com.example.jobs.JobService.makePublisher(..))",
    returning = "publisher",
    argNames = "publisher"
)
public void returned(reactor.core.publisher.Mono<?> publisher) {
    System.out.println("Đã tạo/trả một Mono");
}
```

Advice nhận **đối tượng `Mono`**, không tự nhận phần tử `T` mà Mono có thể emit sau khi subscribe.

**Hai đoạn trên là fragments, không phải project độc lập.** Type của formal parameter trong advice còn **hạn chế matching của return value**: `CompletableFuture<?>` sẽ không phù hợp khi method thực tế trả một loại value khác. Đối với `void`/null/primitive hoặc nhiều subtype, kiểm thử binding thực tế trong Spring context.

### Gán lại parameter advice không thay Future/Publisher caller nhận

```java
@AfterReturning(
    pointcut = "execution(* com.example.jobs.JobService.startFuture(..))",
    returning = "future",
    argNames = "future"
)
public void incorrect(CompletableFuture<String> future) {
    future = CompletableFuture.completedFuture("replacement");
}
```

Đây là **anti-pattern minh họa**. `future = ...` chỉ gán lại biến local của advice; Spring `@AfterReturning` không có hợp đồng thay **reference** trả cho caller. Nếu phải đổi result được caller nhận, sử dụng `@Around` return stage/publisher phù hợp hoặc thiết kế transformation ở service/adapter.

## 4. `@AfterThrowing` không tự quan sát lỗi xuất hiện sau return

Cần phân biệt bốn trường hợp:

| Kịch bản | Lời gọi Java method | Trạng thái công việc về sau | `@AfterThrowing` nhắm method đó? |
| --- | --- | --- | --- |
| Method `throw new IllegalStateException(...)` trước return | Thoát bằng exception | Không trả handle | **Có**, nếu pointcut/type match. |
| Method trả `CompletableFuture` đang pending, sau đó complete exceptionally | **Normal return** | Future lỗi về sau | **Không chỉ vì** future lỗi. |
| Method trả `Mono.error(ex)` bình thường | **Normal return** | Subscription phát `onError` | **Không chỉ vì** `onError`. |
| Method ném lỗi ngay lúc xây dựng Publisher trước `return` | Thoát bằng exception | Publisher chưa được trả | **Có**, nếu advisor và loại exception match. |

Ví dụ:

```java
public CompletableFuture<String> start() {
    CompletableFuture<String> result = new CompletableFuture<>();
    // Một thread hoặc callback khác sẽ gọi:
    // result.completeExceptionally(new IllegalStateException("late"));
    return result;
}
```

Đây là fragment. Target method không throw khi trả future; Spring AOP nhìn thấy **normal return**. Khi future chuyển sang exceptional state về sau, caller gặp lỗi tại `join()` hoặc `get()` (hoặc khi callback chạy), không phải một **method-execution exception** tự động “quay ngược” vào `@AfterThrowing` của `start()`.

Tương tự:

```java
public Mono<String> fetch() {
    return Mono.error(new IllegalStateException("stream-error"));
}
```

Method `fetch()` hoàn toàn có thể trả `Mono` bình thường. Reactive error được phát **khi publisher được subscribe**, không phải Java exception của method `fetch()` trong trường hợp này.

**Lưu ý:** nếu một advice `@Around` hoặc hạ tầng Spring khác ở bên trong biến lỗi thành **synchronous throw** trước khi returning ra ngoài, việc advice nào quan sát gì còn phụ thuộc advisor chain. Các kết luận trên nhắm đúng ranh giới method execution của **Spring AOP thông thường**, không phủ nhận những điều chỉnh do các interceptors khác.

## 5. Khác biệt với `@Async` của Spring

Trong Spring, `@Async` dùng task execution infrastructure và thường được proxy-based. Với một service:

```java
@Async
public CompletableFuture<String> compute() {
    return CompletableFuture.completedFuture("done");
}
```

đây là **fragment**; cần `@EnableAsync` và executor phù hợp. Có hai lớp cần nghĩ tới:

1. **Method/service invocation** bị hạ tầng `@Async` chuyển sang executor.
2. **Future** caller nhận đại diện cho kết quả của công việc được thực thi.

Khi cùng method có custom `@Aspect`, thứ tự giữa **async interceptor** và **custom advisor** ảnh hưởng advice chạy ở thread nào và nhìn thấy **wrapper Future nào**. Nếu custom advice nằm ngoài async interceptor, `@AfterReturning` có thể quan sát Future returned cho caller trước khi worker thực thi xong. Nếu advice nằm bên trong đoạn invocation được executor thực thi, nó có thể quan sát một return value khác ở một thời điểm khác.

**Không suy từ annotation source order** rằng `@AfterReturning` của custom aspect luôn chạy trong executor thread hay luôn chạy sau khi `@Async` task hoàn thành. Muốn hiểu chính xác, phải kiểm tra ordering/proxy chain và test trên configuration thật.

Đối với `@Async void`, caller không nhận Future để `get()`; Spring có `AsyncUncaughtExceptionHandler` cho uncaught async exceptions. `@AfterThrowing` trên một custom aspect không phải phương tiện thay thế tự động cho cấu hình exception-handling của `@Async`.

### Một phân biệt thường bị bỏ quên

`CompletableFuture.supplyAsync(...)` trong target method và Spring `@Async` **không phải cùng một kỹ thuật**. Cả hai có thể làm việc bất đồng bộ, nhưng executor, proxy chain, bean boundary và error routing khác nhau. Bài demo ở phần 9 cố ý **không dùng `@Async` hoặc thread race**: nó tạo pending Future, trả ngay và hoàn thành về sau bằng một method được gọi từ main để stdout có thể kiểm tra chính xác.

## 6. Dùng Future callbacks để quan sát completion, không chặn trong advice

Với `CompletableFuture<T>` hoặc `CompletionStage<T>`, khi mục tiêu là theo dõi **kết quả cuối**, có thể đăng ký completion callback.

Ví dụ trong Spring `@Around`:

```java
@Around("execution(* com.example.jobs.JobService.start(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    CompletionStage<?> stage = (CompletionStage<?>) pjp.proceed();

    return stage.whenComplete((value, failure) -> {
        if (failure == null) {
            metrics.incrementSuccess();
        } else {
            metrics.incrementFailure();
        }
    });
}
```

Đây là **fragment** cần method target trả `CompletionStage`, `metrics` tồn tại và import `CompletionStage`. `@Around` trả về stage sau khi attach callback; callback có thể chạy ở thread **hoàn thành stage**, không nhất thiết cùng thread với method advice.

Các lựa chọn khác:

- `whenComplete`: quan sát success/error, về nguyên tắc giữ result/exception gốc trừ khi callback tự throw.
- `handle`: có thể **biến đổi** success hoặc failure thành giá trị khác.
- `thenApply`: transform **success value**.
- `exceptionally`: xử lý một số exceptional completions.
- `whenCompleteAsync`, `thenApplyAsync`: lên lịch callback bằng executor có thể khác; tránh giả định ThreadLocal/MDC/SecurityContext tự được truyền.

Đừng viết:

```java
@AfterReturning(
    pointcut = "execution(* com.example.jobs.JobService.start(..))",
    returning = "future"
)
public void waitForResult(CompletableFuture<?> future) {
    future.join(); // Có thể block proxy caller thread.
}
```

Đây là **anti-pattern**. `join()` có thể block vô hạn nếu Future không complete, làm mất tính bất đồng bộ, tăng latency và có thể gây deadlock/starvation nếu completion cần resource đang bị caller thread giữ. Nếu chỉ cần metric, đăng ký callback non-blocking phù hợp hơn.

### `Future` thường và `CompletionStage` không tương đương

Interface `java.util.concurrent.Future` chỉ có các operations như `isDone()`, `get()`, `cancel()`. Nó **không có callback API `whenComplete`**.

Nếu một method trả `Future<T>` thuần, muốn quan sát hoàn thành có thể cần API hỗ trợ từ thư viện, một adapter thích hợp hoặc tổ chức completion ở nơi tạo Future. Không nên buộc một aspect generic phải polling liên tục hay gọi `get()` trong request thread chỉ để lấy metric.

### Exception wrapping

- `CompletableFuture.join()` thường ném unchecked `CompletionException` bao quanh cause khi future completed exceptionally.
- `Future.get()` dùng checked `ExecutionException` khi task ném lỗi.
- `CancellationException` là trạng thái đặc biệt, không nên tính như một thành công.
- Callback có thể nhận `Throwable` đại diện lỗi hoặc một wrapper; chính sách log/metric nên normalize cause phù hợp mà không nuốt thông tin.

`future.isDone()==true` chỉ nói future **đã hoàn tất ở một trạng thái**; cần phân biệt normal, exceptional, cancelled nếu nghiệp vụ yêu cầu.

## 7. Reactive `Mono`/`Flux`: method return, subscription, signal và cancellation

### 7.1. Cold publisher

Một ví dụ Reactor:

```java
public Mono<String> load() {
    return Mono.defer(() -> {
        System.out.println("Đang thực hiện công việc");
        return Mono.just("value");
    });
}
```

Đây là method fragment trong một bean. Khi `load()` được gọi:

- Java method tạo `Mono` và **return**.
- Spring `@AfterReturning` có thể chạy ngay sau normal return.
- `Mono.defer` supplier **chỉ được gọi khi có subscription**.
- Nếu không có ai subscribe, supplier không chạy.
- Nếu có **hai subscriptions** vào cold publisher, supplier có thể chạy **hai lần** dù target `load()` chỉ được gọi **một lần**.

Vì vậy hãy phân biệt các counters:

```text
methodInvocations = 1
afterReturningInvocations = 1
subscriptions = 2
workExecutions = 2   (trong ví dụ Mono.defer cold)
```

### 7.2. Hot publisher và nguồn đã bắt đầu xử lý

Không được phát biểu tuyệt đối “Publisher luôn chưa chạy gì trước khi subscribe”. Với hot sources, dữ liệu có thể được phát trước khi subscriber đến. `Mono.just(value)` có thể capture value eagerly lúc assembly; `Mono.fromFuture(future)` có thể wrap một Future đang chạy; kết quả đã được tính toán trước khi `Mono` được trả ra.

Vì thế `@AfterReturning` chỉ cho biết **Java method return bình thường**. Nó không tự nói publisher cold/hot, đang chạy/chưa chạy, còn active/đã complete.

### 7.3. Terminal signals

Theo Reactive Streams, subscriber thường thấy:

```text
onSubscribe
request(...)
onNext(value)   (0..N lần tùy Publisher)
onComplete()    (kết thúc bình thường)
```

hoặc:

```text
onSubscribe
request(...)
onError(error)  (kết thúc bằng lỗi)
```

`Mono<T>` có thể thành công **không có phần tử** (`Mono.empty()`), trong khi `Flux<T>` có thể phát nhiều phần tử trước terminal. **Không dùng riêng `doOnNext` để tính mọi successful completions**, vì empty Publisher không phát `onNext`.

Cancellation cũng là một kết quả quản lý subscription cần quan sát khi dùng timeout/client disconnect; nó không đồng nhất với `onComplete` hoặc `onError`.

### 7.4. `@AfterThrowing` không phải `doOnError`

`@AfterThrowing` là Spring AOP advice về **Java method exception**. `Mono.doOnError`, `Flux.doOnError` chạy trong **reactive signal pipeline** khi subscriber nhận error.

Một `@AfterThrowing` không tự lắng nghe `onError` của tất cả `Mono/Flux` target trả về. Muốn metric hoàn tất theo Publisher lifecycle, dùng reactive hooks/operators trong service hoặc dùng `@Around` **trả về Publisher đã được decorate**, và đảm bảo không thay đổi behavior ngoài ý muốn.

## 8. `@Around` có thể decorate Publisher nhưng phải trả về nó

Ví dụ:

```java
@Around("execution(* com.example.jobs.JobService.stream(..))")
public Object observePublisher(ProceedingJoinPoint pjp) throws Throwable {
    Mono<?> source = (Mono<?>) pjp.proceed();

    // Pipeline được decorate, callbacks chỉ chạy theo reactive lifecycle.
    return source
        .doOnSubscribe(subscription -> metrics.onSubscribe())
        .doOnSuccess(value -> metrics.onSuccess())
        .doOnError(error -> metrics.onError(error))
        .doFinally(signal -> metrics.onFinally(signal));
}
```

Đây là **fragment** dành cho method trả `Mono`, không phải generic code áp dụng vô điều kiện cho `Flux` hoặc bất cứ kiểu `Publisher` nào.

Điểm quan trọng:

1. `pjp.proceed()` chạy **Java method body**, trả `Mono`.
2. `doOn...` tạo ra **publisher chain được decorate**; muốn caller sử dụng chain đó, `@Around` phải **return publisher mới**.
3. Callbacks được gắn vào **subscription lifecycle**, không phải return lifecycle của Java method.
4. `doOnSuccess` là hook của `Mono`; với `Flux` dùng `doOnComplete` để quan sát terminal success và `doOnNext` cho từng phần tử.
5. `doFinally` có signal type như `ON_COMPLETE`, `ON_ERROR`, `CANCEL`; nó phù hợp cho cleanup/metrics theo subscription, nhưng timing của callback so với một số downstream operations cần được test.
6. Nhiều subscriptions vào cold publisher có thể khiến hooks chạy nhiều lần trong **một** method invocation.
7. Nếu `Mono` đã được chia sẻ/cache/hot, semantics có thể khác. Không assume một subscription luôn bằng một upstream job mới.

**Đừng làm như sau trong `@Around`:**

```java
Mono<?> source = (Mono<?>) pjp.proceed();
source.subscribe();  // Tự kích hoạt một subscription phụ.
return source;        // Caller có thể subscribe lần nữa.
```

Đây là **anti-pattern minh họa**. `subscribe()` thủ công bên trong aspect có thể kích hoạt công việc, HTTP call, DB access hoặc side effect **trước khi caller chủ động subscribe**, rồi caller lại kích hoạt một lần nữa. Nó phá ownership của subscription, làm khó error/cancellation propagation và có thể gây duplicate processing.

Nếu cần transform value, dùng `map`/`flatMap` đúng hợp đồng; nếu cần quan sát terminal, dùng phù hợp `doOnSuccess`/`doOnComplete`/`doOnError`/`doFinally`. Không tự block bằng `block()` trong aspect chỉ để “đợi hoàn tất”, đặc biệt trên thread non-blocking của WebFlux.

## 9. Ví dụ Java 17+ chạy được: method return trước Future completion và Mono subscription

Ví dụ dưới đây được thiết kế **để có stdout xác định**. Nó không dùng scheduler races:

- Method `startFuture()` tạo **pending CompletableFuture** và trả về ngay. Caller hoàn thành future sau đó bằng một method khác.
- Một future thứ hai được hoàn thành **exceptionally** sau khi đã return; `@AfterThrowing` không chạy cho lỗi muộn đó.
- Method `failImmediately()` **throw trước return**, nên `@AfterThrowing` chạy.
- Method `coldPublisher()` trả `Mono.defer`, công việc chỉ chạy khi subscribe; hai subscriptions vào cùng Mono làm công việc chạy hai lần.
- Hai methods `observedPublisher()` và `errorPublisher()` được `@Around` decorate để đếm **reactive success/error signals**, không dựa vào `@AfterReturning`.

Project sử dụng **Java 17+, Spring Framework 6.1.14, AspectJ Weaver 1.9.22.1, Reactor Core 3.6.11 và Maven**. Đây là bộ version minh họa cố định, không tuyên bố mới nhất. Chỉ dùng **Spring proxy-based AOP**, không cấu hình AspectJ weaving agent.

### 9.1. Cấu trúc thư mục

```text
spring-aop-completion-boundary/
├── pom.xml
└── src/main/java/com/example/completion/
    ├── JobService.java
    ├── CompletionAspect.java
    ├── AppConfig.java
    └── DemoApp.java
```

### 9.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-completion-boundary</artifactId>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.11</version>
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

`spring-context` cung cấp `ApplicationContext` và kéo những Spring AOP dependencies cần thiết qua dependency tree; `aspectjweaver` dùng cho Spring `@AspectJ` pointcut parser. `reactor-core` cung cấp `Mono` và signal operators. Không cần web server để test sự phân biệt giữa method return và publisher lifecycle.

### 9.3. `src/main/java/com/example/completion/JobService.java`

```java
package com.example.completion;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class JobService {
    private CompletableFuture<String> pending;
    private final AtomicInteger coldSubscriptions = new AtomicInteger();

    public CompletableFuture<String> startFuture() {
        pending = new CompletableFuture<>();
        System.out.println("[TARGET] returned pending Future");
        return pending;
    }

    public void completeFuture(String value) {
        pending.complete(value);
    }

    public void failFuture() {
        pending.completeExceptionally(
                new IllegalArgumentException("late-future"));
    }

    public CompletableFuture<String> failImmediately() {
        System.out.println("[TARGET] throwing before return");
        throw new IllegalStateException("early");
    }

    public Mono<String> coldPublisher() {
        System.out.println("[TARGET] returned cold Publisher");
        return Mono.defer(() -> {
            coldSubscriptions.incrementAndGet();
            System.out.println("[WORK] cold subscription");
            return Mono.just("M-OK");
        });
    }

    public Mono<String> observedPublisher() {
        System.out.println("[TARGET] returned observed Publisher");
        return Mono.defer(() -> Mono.just("OBS-OK"));
    }

    public Mono<String> errorPublisher() {
        System.out.println("[TARGET] returned error Publisher");
        return Mono.error(new IllegalArgumentException("late-mono"));
    }

    public int coldSubscriptions() {
        return coldSubscriptions.get();
    }
}
```

**Giải thích design:** `pending` chỉ là một field hỗ trợ demo chạy tuần tự, không phải cách tổ chức job state production. Trong ứng dụng nhiều requests, dùng per-request job IDs và state ownership phù hợp, không lưu một `pending` có thể bị ghi đè trong singleton service.

`completeFuture` và `failFuture` được caller gọi sau khi `startFuture` đã return. Chúng **không được các pointcuts trong demo chọn**, nên không tạo thêm advice events vào output.

`coldPublisher` tạo `Mono.defer`: phần `[WORK]` chỉ in khi có subscription. `observedPublisher` và `errorPublisher` có return type `Mono<String>` để `@Around` có thể attach reactive operators.

### 9.4. `src/main/java/com/example/completion/CompletionAspect.java`

```java
package com.example.completion;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import reactor.core.publisher.Mono;

@Aspect
public class CompletionAspect {
    private final AtomicInteger futureReturns = new AtomicInteger();
    private final AtomicInteger syncThrows = new AtomicInteger();
    private final AtomicInteger publisherReturns = new AtomicInteger();
    private final AtomicInteger monoSuccesses = new AtomicInteger();
    private final AtomicInteger monoErrors = new AtomicInteger();

    @AfterReturning(
        pointcut = "execution(* com.example.completion.JobService.startFuture(..))",
        returning = "future",
        argNames = "future"
    )
    public void afterFutureReturned(CompletableFuture<?> future) {
        futureReturns.incrementAndGet();
        System.out.println("[AOP after-return] Future done=" + future.isDone());
    }

    @AfterThrowing(
        pointcut = "execution(* com.example.completion.JobService.startFuture(..))"
                 + " || execution(* com.example.completion.JobService.failImmediately(..))",
        throwing = "error",
        argNames = "error"
    )
    public void afterSynchronousThrow(Throwable error) {
        syncThrows.incrementAndGet();
        System.out.println("[AOP after-throw] "
                + error.getClass().getSimpleName());
    }

    @AfterReturning(
        pointcut = "execution(* com.example.completion.JobService.coldPublisher(..))",
        returning = "publisher",
        argNames = "publisher"
    )
    public void afterPublisherReturned(Mono<?> publisher) {
        publisherReturns.incrementAndGet();
        System.out.println("[AOP after-return] Publisher returned");
    }

    @Around(
        "execution(* com.example.completion.JobService.observedPublisher(..))"
        + " || execution(* com.example.completion.JobService.errorPublisher(..))"
    )
    public Object monitorPublisher(ProceedingJoinPoint pjp) throws Throwable {
        Mono<?> source = (Mono<?>) pjp.proceed();
        System.out.println("[AOP around] returned Publisher: "
                + pjp.getSignature().getName());

        return source
                .doOnSuccess(value -> monoSuccesses.incrementAndGet())
                .doOnError(error -> monoErrors.incrementAndGet());
    }

    public int futureReturns() {
        return futureReturns.get();
    }

    public int syncThrows() {
        return syncThrows.get();
    }

    public int publisherReturns() {
        return publisherReturns.get();
    }

    public int monoSuccesses() {
        return monoSuccesses.get();
    }

    public int monoErrors() {
        return monoErrors.get();
    }
}
```

**Ý nghĩa từng advice:**

- `afterFutureReturned` nhận **Future reference** khi `startFuture` normal return. `isDone=false` là trạng thái cố định trong demo vì caller chưa gọi `completeFuture`.
- `afterSynchronousThrow` chỉ quan sát **Java exception từ method execution** tương ứng. Future sau này complete exceptionally **không quay lại gọi** advice này.
- `afterPublisherReturned` đếm **một lần trả Mono**, không đếm subscriptions.
- `monitorPublisher` dùng `@Around` để **return một Mono đã decorate**, nên `monoSuccesses`/`monoErrors` tăng khi subscriber nhận signal thích hợp.
- Các pointcuts trong ví dụ không chồng chéo giữa `@Around` và `@AfterReturning` trên cùng method; vì thế stdout không bị phụ thuộc vào ordering giữa nhiều advice trên một join point.

### 9.5. `src/main/java/com/example/completion/AppConfig.java`

```java
package com.example.completion;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public JobService jobService() {
        return new JobService();
    }

    @Bean
    public CompletionAspect completionAspect() {
        return new CompletionAspect();
    }
}
```

`@EnableAspectJAutoProxy` bật Spring AOP auto-proxy infrastructure. `proxyTargetClass=true` chọn CGLIB class proxy cho `JobService` không implement business interface. `CompletionAspect` là Spring bean do `@Bean`; `@Aspect` đơn lẻ chưa tự đăng ký bean.

### 9.6. `src/main/java/com/example/completion/DemoApp.java`

```java
package com.example.completion;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import reactor.core.publisher.Mono;

public class DemoApp {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {

            JobService jobs = context.getBean(JobService.class);
            CompletionAspect aspect = context.getBean(CompletionAspect.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(jobs));

            CompletableFuture<String> success = jobs.startFuture();
            System.out.println("futureBeforeComplete=" + success.isDone());
            jobs.completeFuture("F-OK");
            System.out.println("futureValue=" + success.join());

            CompletableFuture<String> failure = jobs.startFuture();
            jobs.failFuture();
            try {
                failure.join();
            } catch (CompletionException error) {
                System.out.println("futureFailure="
                        + error.getCause().getClass().getSimpleName());
            }

            try {
                jobs.failImmediately();
            } catch (IllegalStateException error) {
                System.out.println("syncFailure=" + error.getMessage());
            }
            System.out.println("futureReturns=" + aspect.futureReturns());
            System.out.println("syncThrows=" + aspect.syncThrows());

            Mono<String> cold = jobs.coldPublisher();
            System.out.println("coldBeforeSubscribe="
                    + jobs.coldSubscriptions());

            System.out.println("coldValue1=" + cold.block());
            System.out.println("coldValue2=" + cold.block());
            System.out.println("coldAfterSubscribe="
                    + jobs.coldSubscriptions());
            System.out.println("publisherReturns=" + aspect.publisherReturns());

            Mono<String> monitored = jobs.observedPublisher();
            System.out.println("monoSuccessBefore=" + aspect.monoSuccesses());
            System.out.println("monitoredValue=" + monitored.block());
            System.out.println("monoSuccessAfter=" + aspect.monoSuccesses());

            try {
                jobs.errorPublisher().block();
            } catch (IllegalArgumentException error) {
                System.out.println("monoError=" + error.getMessage());
            }

            System.out.println("monoSignalErrors=" + aspect.monoErrors());
            System.out.println("syncThrowsFinal=" + aspect.syncThrows());
        }
    }
}
```

Demo không có background threads trong `JobService` và các `Mono` dùng sync cold sources, nên thứ tự các `System.out.println` do code tạo ra **có thể được đối chiếu trực tiếp**. Trong production, thread scheduling và Reactor schedulers có thể khiến timestamp/log interleave; đó là một vấn đề khác.

### 9.7. Chạy Maven và stdout dự kiến

Với JDK 17+ và Maven tải được dependencies, trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.completion.DemoApp
```

Các dòng của chương trình (bỏ qua thông báo Maven/SLF4J bổ sung):

```text
isAopProxy=true
[TARGET] returned pending Future
[AOP after-return] Future done=false
futureBeforeComplete=false
futureValue=F-OK
[TARGET] returned pending Future
[AOP after-return] Future done=false
futureFailure=IllegalArgumentException
[TARGET] throwing before return
[AOP after-throw] IllegalStateException
syncFailure=early
futureReturns=2
syncThrows=1
[TARGET] returned cold Publisher
[AOP after-return] Publisher returned
coldBeforeSubscribe=0
[WORK] cold subscription
coldValue1=M-OK
[WORK] cold subscription
coldValue2=M-OK
coldAfterSubscribe=2
publisherReturns=1
[TARGET] returned observed Publisher
[AOP around] returned Publisher: observedPublisher
monoSuccessBefore=0
monitoredValue=OBS-OK
monoSuccessAfter=1
[TARGET] returned error Publisher
[AOP around] returned Publisher: errorPublisher
monoError=late-mono
monoSignalErrors=1
syncThrowsFinal=1
```

### 9.8. Đọc đúng các kết quả

1. `startFuture()` **đã return hai lần** nên `futureReturns=2`, và `done=false` tại cả hai `@AfterReturning`. Điều này không nói futures sẽ thành công hay lỗi.
2. Future thứ nhất được caller hoàn thành **sau khi** method và `@AfterReturning` đã chạy, rồi `join()` trả `F-OK`.
3. Future thứ hai hoàn thành exceptionally sau return. `join()` ném `CompletionException` với cause `IllegalArgumentException`, nhưng **`@AfterThrowing` không chạy** cho event completion muộn ấy.
4. `failImmediately()` **ném lỗi trước khi trả Future**, nên `@AfterThrowing` chạy đúng một lần: `syncThrows=1`.
5. `coldPublisher()` chỉ được **gọi một lần**, nên `publisherReturns=1`. Nhưng `cold.block()` hai lần tạo hai **subscriptions**; `[WORK]` xuất hiện hai lần và `coldAfterSubscribe=2`.
6. `monitorPublisher` thực thi khi `observedPublisher()` return, nhưng `monoSuccessBefore=0`. Chỉ khi `monitored.block()` subscribe và Mono success mới thấy `monoSuccessAfter=1`.
7. `errorPublisher()` return bình thường và `@Around` đã trả decorated Publisher. Error xuất hiện khi `block()` subscribe, tăng `monoSignalErrors=1`, **không tăng** `syncThrowsFinal` vì không có synchronous Java throw từ `JobService.errorPublisher()`.
8. Toàn bộ lời gọi target đi qua Spring bean proxy, không phải `new JobService()` bên ngoài context.

Đây là demo cố ý tách **method return**, **Future completion** và **reactive subscription/signal**. Output dự kiến được tính theo source code đã trình bày; Java/Maven cần được chạy trong môi trường thực nếu muốn kiểm tra build artifacts hoặc tương thích dependency mirror.

## 10. Đo duration trong Spring Aspect: bạn đang đo khoảng nào?

Một `@Around` truyền thống:

```java
@Around("execution(* com.example.jobs.JobService.*(..))")
public Object measure(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        metrics.record(elapsed);
    }
}
```

Đây là **fragment**. Với service trả `Future` hoặc Publisher ngay, `elapsed` là **thời gian Java method invocation/assembly**, **không tự đo** thời gian đến completion của Future hoặc terminal signal của Publisher.

Muốn phân biệt đúng, đặt tên metric:

| Metric | Start | End | Đo điều gì? |
| --- | --- | --- | --- |
| `method.return.latency` | Vào Spring advice | Java method return/throw | Invocation/Publisher assembly. |
| `future.completion.latency` | Bắt đầu tác vụ/đăng ký callback | Completion/cancel của Future | Công việc được Future đại diện, theo định nghĩa start. |
| `publisher.subscription.duration` | Subscription bắt đầu | Terminal/cancel signal | Duration của **một subscription**, không nhất thiết lifetime object publisher. |
| `request.duration` | HTTP request bắt đầu | HTTP response/cancellation hoàn tất | Cần HTTP/web instrumentation, không suy từ service `@AfterReturning`. |

Một `Mono` có thể được subscribe nhiều lần. Nếu dùng **một timestamp** tính lúc method assembly rồi đo tới nhiều subscription completions, metrics có thể bao gồm **thời gian chờ trước subscription** và tạo ra kết quả khó diễn giải. Để đo subscriber lifecycle, lấy start time **lúc subscribe** với `Mono.defer`, `doOnSubscribe` hoặc instrumentation có context per-subscription thích hợp.

### ThreadLocal/MDC và Reactor Context

Trong Spring AOP, advice ban đầu chạy trên thread gọi Java method. Completion callbacks có thể chạy trên **thread khác**. Reactor signals có thể đi qua các schedulers khác nhau.

- Không giả định `ThreadLocal`, MDC, transaction context hoặc `SecurityContextHolder` lúc advice thực thi tự xuất hiện ở future callback.
- Reactor có `Context` dành cho dữ liệu gắn với subscription; dùng những cơ chế context propagation tích hợp thích hợp với Spring/Reactor version.
- Tốt nhất gắn correlation ID/trace context theo cơ chế framework đã hỗ trợ, không tự lưu `ProceedingJoinPoint` hoặc request-specific state trong field của singleton aspect.
- Nếu cần ghi log nhạy cảm, không đưa toàn bộ Future result/Publisher elements vào log một cách mặc định.

## 11. Spring WebFlux: hoàn tất method không có nghĩa response đã gửi xong

Giả sử một Spring WebFlux controller hoặc service method trả:

```java
public Mono<ResponseDto> get(String id) {
    return service.fetch(id).map(ResponseDto::from);
}
```

Đây là fragment cần `ResponseDto`, `service` tồn tại. `@AfterReturning` nhắm method `get` hoặc `fetch` có thể thấy **Mono reference** khi Java method return. Nhưng:

1. Dispatcher/HTTP handling vẫn có thể chưa subscribe pipeline tại thời điểm đó.
2. `fetch` có thể được thực thi về sau.
3. `Mono` có thể complete empty/error/cancel.
4. HTTP server còn phải encode/write response; reactive terminal signal **không tự đồng nhất** với “client đã nhận mọi byte”.
5. Một controller/service method có `@Transactional` hoặc các Spring transaction facilities có thể dùng behavior chuyên biệt cho reactive transactions; không suy mọi transaction commit xảy ra ngay lúc Java method return.

Nếu cần observability cho **HTTP request lifecycle**, sử dụng WebFlux filters/observation/tracing facilities ở tầng web; nếu cần observability cho **publisher subscription**, sử dụng Reactor operators hoặc Spring-compatible reactive instrumentation. Spring service AOP `@AfterReturning` đo **method return**, không có nghĩa nó thay thế các facility này.

## 12. Những lỗi suy luận thường gặp

| Triệu chứng / kết luận sai | Điều thực sự đang xảy ra | Hướng kiểm tra |
| --- | --- | --- |
| “`@AfterReturning` đã chạy, vậy async job thành công.” | Method trả Future bình thường, job có thể còn pending hoặc fail về sau. | Đăng ký `whenComplete`/đọc terminal outcome. |
| “`@AfterThrowing` không chạy, vậy CompletableFuture không lỗi.” | Future có thể complete exceptionally **sau** method return. | `whenComplete`, `join()`/`get()`, exception cause. |
| “`@AfterReturning` đã chạy, vậy Mono pipeline đã được subscribe.” | Method có thể chỉ trả cold Publisher chưa có subscriber. | Dùng `doOnSubscribe` và observability trên pipeline. |
| “`Mono.error(ex)` khiến Spring `@AfterThrowing` chạy.” | Method trả Mono bình thường; `onError` là reactive signal về sau. | Dùng `doOnError` hoặc terminal signal subscriber. |
| “Mỗi method invocation tương đương một `Flux` execution.” | Một cold Publisher có thể được subscribe nhiều lần; hot publishers có semantics khác. | Đếm riêng method calls và subscriptions. |
| “Future `isDone=true` nghĩa là success.” | Future có thể exceptional hoặc cancelled. | Kiểm tra completed state/outcome có phân loại. |
| “Gọi `join()` trong `@AfterReturning` để đo completion là vô hại.” | Có thể block caller, phá async và gây deadlock. | Attach callback non-blocking hoặc instrument nơi tạo task. |
| “`@Around` đã gắn `doOnError`, không cần return Mono đã decorate.” | Reactor operators trả publisher mới; bỏ wrapper thì caller không dùng hooks. | `return source.doOnError(...)`. |
| “Subscribe trong aspect chỉ để log.” | Có thể khởi động một subscription phụ và duplicate side effects. | Tránh tự subscribe; return decorated Publisher. |
| “`doOnNext` đủ để đếm mọi Mono success.” | `Mono.empty()` success không phát `onNext`. | `doOnSuccess` hoặc terminal hooks thích hợp. |
| “`doFinally` lúc nào cũng là success.” | Có `CANCEL`, `ON_ERROR`, `ON_COMPLETE`. | Phân loại `SignalType`. |
| “`@Async` và custom AOP advice luôn chạy cùng thread.” | Phụ thuộc proxy/advisor ordering và executor. | Kiểm tra `@EnableAsync`, `@Order`, advisor chain, test thực. |
| “`@AfterReturning` đo HTTP response duration.” | Nó đo Java method return, không phải network write lifecycle. | Instrument WebFlux/HTTP request boundary. |
| “Future callback tự kế thừa MDC/transaction context.” | Completion có thể ở thread khác. | Cấu hình context propagation phù hợp. |
| “`isAopProxy=true` chứng minh advice quan sát terminal signal.” | Proxy chỉ chứng minh đã có hạ tầng interception phù hợp, không tự đăng ký Future/Reactive callbacks. | Assert counters sau completion/subscription thật. |

## 13. Checklist để review một Spring Aspect xử lý Future/Publisher

- [ ] Định nghĩa rõ cần quan sát **method return** hay **actual async/reactive completion**.
- [ ] `@AfterReturning` chỉ được dùng để kết luận **normal method return**, không suy tác vụ đã thành công.
- [ ] `@AfterThrowing` chỉ áp dụng cho **method exception path**, không dùng thay `onError`/future exceptional completion.
- [ ] Với `Future` thuần, không giả định có `whenComplete`; xác định type API thực tế.
- [ ] Với `CompletionStage`, callbacks được attach đúng, không biến đổi result/exception ngoài chủ đích.
- [ ] Không block `join()/get()` trong advice trên đường gọi latency-sensitive.
- [ ] Với Publisher, phân biệt cold/hot, assembly/subscription/emission/terminal/cancellation.
- [ ] Không gọi `subscribe()` trong aspect chỉ để quan sát kết quả.
- [ ] Nếu dùng `@Around` decorate Publisher, **trả về publisher mới** có operators cần thiết.
- [ ] Đo per-subscription metrics khi Publisher có thể nhiều subscribers.
- [ ] Dùng `doOnSuccess`/`doOnComplete`/`doOnError`/`doFinally` đúng loại Publisher và ý nghĩa.
- [ ] Nếu dùng `@Async`, đã xác minh advisor ordering, executor thread và exception policy.
- [ ] Đã đánh giá ThreadLocal/MDC/transaction/security context propagation tới callbacks.
- [ ] Biết proxy boundary: Spring bean, `@EnableAspectJAutoProxy`, không self-invocation hoặc `new` target.
- [ ] Có integration tests cho pending→success, pending→error, synchronous throw, empty/error Publisher, cancellation và multiple subscriptions khi áp dụng.
- [ ] Phân biệt method duration với job/subscription/request duration trong tên metrics.

### Tài liệu tham khảo chính thức

- Spring Framework — **Declaring Advice**, `@AfterReturning`/`@AfterThrowing`/`@Around`: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — **Task Execution and Scheduling**, `@Async`/`Future`/`CompletableFuture`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — **Proxying Mechanisms** và self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Reactor Core — **Hot Versus Cold**: https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html
- Reactor Core — **Introduction to Reactive Programming** và subscription lifecycle: https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html
- Project Reactor — `Mono`/ `Flux` Javadoc: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html

**Kết luận:** Khi Spring Aspect thấy một method **trả về `Future` hoặc `Publisher`**, điều chắc chắn duy nhất theo `@AfterReturning` là **Java method đã normal-return một object handle/publisher**. Công việc mà object đó đại diện có **lifecycle khác**, gồm Future completion hoặc Publisher subscription, signals và cancellation. Muốn audit/metrics cho **completion thực tế**, hãy gắn `CompletionStage` callbacks hoặc trả publisher được decorate bằng Reactor operators (qua `@Around` nếu cần), thay vì suy hoàn tất công việc từ việc `@AfterReturning` đã chạy.
