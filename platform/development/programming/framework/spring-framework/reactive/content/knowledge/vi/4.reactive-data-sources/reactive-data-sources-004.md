# Tạo tín hiệu hoàn tất, lỗi và `never` trong Project Reactor (Spring WebFlux)

## 1. Mục tiêu bài học

Khi tạo nguồn dữ liệu reactive, không phải lúc nào ta cũng có một giá trị để phát ra. Một tác vụ có thể **hoàn thành thành công mà không sinh dữ liệu**, **thất bại**, hoặc **tiếp tục chờ mà không phát tín hiệu kết thúc**. Project Reactor cung cấp ba nhóm factory tương ứng cho cả `Mono` và `Flux`:

- `Mono.empty()` / `Flux.empty()`: hoàn tất thành công và không phát phần tử.
- `Mono.error(Throwable)` / `Flux.error(Throwable)`: kết thúc bằng lỗi.
- `Mono.never()` / `Flux.never()`: không phát phần tử, không phát tín hiệu hoàn tất và cũng không phát lỗi.

Bài này tập trung vào **ngữ nghĩa của tín hiệu**, cách tạo từng nguồn, tác động đến toán tử ở phía sau, cách kiểm thử, giới hạn thời gian, hủy subscription và cách áp dụng trong Spring WebFlux. Ba nguồn trên thể hiện ba trạng thái rất khác nhau; không nên hoán đổi chúng chỉ vì cùng “không có dữ liệu”.

## 2. Nắm hợp đồng tín hiệu trước khi viết code

`Mono<T>` biểu diễn tối đa một phần tử; `Flux<T>` biểu diễn từ không đến nhiều phần tử. Publisher tương tác với subscriber qua các tín hiệu thuộc giao thức Reactive Streams.

```text
Đăng ký:           onSubscribe(subscription)

Hoàn tất rỗng:     onSubscribe -> onComplete
Hoàn tất có dữ liệu (Mono):
                   onSubscribe -> onNext(value) -> onComplete
Hoàn tất có dữ liệu (Flux):
                   onSubscribe -> onNext(a) -> onNext(b) -> ... -> onComplete
Kết thúc lỗi:      onSubscribe -> [có thể có onNext trước đó] -> onError(error)
Chưa kết thúc:     onSubscribe -> ... không có onNext/onComplete/onError
```

Những nguyên tắc phải nhớ:

1. `onSubscribe` là bước thiết lập subscription; `request(n)` từ subscriber thể hiện nhu cầu nhận dữ liệu. Với `never()`, việc đăng ký vẫn diễn ra, nhưng không có tín hiệu dữ liệu hoặc tín hiệu kết thúc tiếp theo.
2. `onComplete` và `onError` là hai tín hiệu **terminal**, loại trừ nhau trong một subscription. Sau một trong hai tín hiệu, nguồn không được phát tiếp `onNext`.
3. `Mono.empty()` **có** tín hiệu terminal `onComplete`; `Mono.never()` thì **không**.
4. Lỗi là một **tín hiệu trong pipeline**, không đồng nghĩa với việc một phương thức Java bắt buộc phải `throw` ra ngay ở thời điểm tạo publisher.
5. `cancel()` là hành động từ phía subscriber để ngừng theo dõi/nhận dữ liệu. Nó khác `onComplete` và `onError`: cancel không có nghĩa một kết quả thành công hay thất bại đã được phát.

### So sánh chính xác ba nguồn

| Nguồn | `onNext` | `onComplete` | `onError` | Mặc định có tự kết thúc? |
|---|---|---|---|---|
| `Mono.empty()` | Không | Có, ngay khi subscription được xử lý | Không | Có |
| `Mono.error(e)` | Không | Không | Có, với `e` | Có |
| `Mono.never()` | Không | Không | Không | Không |
| `Flux.empty()` | Không | Có | Không | Có |
| `Flux.error(e)` | Không | Không | Có | Có |
| `Flux.never()` | Không | Không | Không | Không |

Với các factory trực tiếp này, **không có thread mới được tạo chỉ vì gọi `empty()`, `error()` hoặc `never()`**. Nguồn reactive mô tả luồng tín hiệu; scheduler và hoạt động bất đồng bộ đến từ những toán tử hoặc nguồn khác nếu có.

## 3. Tạo nguồn hoàn tất rỗng: `empty()`

Một kết quả thành công đôi khi không mang giá trị: không tìm thấy phần tử tùy chọn, không còn phần tử trong stream, hoặc một lệnh chỉ cần thông báo đã xong.

```java
Mono<String> noUser = Mono.empty();
Flux<Integer> noNumbers = Flux.empty();

Mono<Void> completedCommand = Mono.empty();
```

`noUser` **không phát `null`**. Nó hoàn thành bằng `onComplete` mà không phát bất kỳ `onNext` nào. Vì Reactor không cho phép phần tử `null` trong các publisher, `Mono.just(null)` không phải cách biểu diễn “không có dữ liệu”.

Tình huống với giá trị có thể vắng mặt:

```java
String optionalName = null;
Mono<String> userName = Mono.justOrEmpty(optionalName);
```

`Mono.justOrEmpty(null)` tạo nguồn hoàn tất rỗng; nếu đầu vào không `null`, nó tạo nguồn phát một giá trị rồi hoàn tất. Với `Optional<T>`, cũng có thể dùng `Mono.justOrEmpty(optional)`.

### `Mono<Void>` có ý nghĩa gì?

`Mono<Void>` thường dùng cho hành động mà client **chỉ cần biết việc thực thi đã hoàn tất hoặc thất bại**, không cần giá trị trả về:

```java
Mono<Void> auditAction = Mono.fromRunnable(
        () -> System.out.println("Audit finished")
);
```

Khi có subscriber, `Runnable` chạy; nếu trả về bình thường, `Mono<Void>` hoàn tất rỗng. Nếu `Runnable` ném exception, Reactor chuyển thành `onError`. Đây là **snippet minh họa**, cần import `reactor.core.publisher.Mono` và chạy trong chương trình có Reactor Core; đừng tự gọi `.subscribe()` trong service/controller WebFlux chỉ để kích hoạt nó.

Phân biệt hai câu hỏi:

- `Mono<Void>`: hợp đồng **kiểu dữ liệu** nói rằng publisher không truyền payload có ý nghĩa.
- `Mono.empty()` hoặc một `Mono<T>` kết thúc rỗng: **hành vi** hoàn tất mà không phát `onNext`. `Mono<String>` vẫn hoàn tất rỗng hoàn toàn hợp lệ.

Một nguồn phát giá trị cũng có thể chuyển thành tín hiệu chỉ báo kết thúc:

```java
Mono<Void> finished = Mono.just("temporary-result").then();
```

`.then()` bỏ qua giá trị thành công ở upstream, chờ upstream hoàn tất rồi hoàn thành rỗng; nếu upstream lỗi, lỗi tiếp tục truyền xuống; nếu upstream không bao giờ kết thúc, `.then()` cũng không thể kết thúc.

### Xử lý luồng rỗng

```java
Mono<String> value = Mono.<String>empty()
        .defaultIfEmpty("anonymous");
```

Khi upstream hoàn tất rỗng, `defaultIfEmpty` phát `"anonymous"` và hoàn tất. Nếu cần một pipeline thay thế, dùng `switchIfEmpty`:

```java
Mono<String> value = Mono.<String>empty()
        .switchIfEmpty(Mono.just("from-fallback"));
```

`defaultIfEmpty` cần một giá trị mặc định **không null**; `switchIfEmpty` cho phép nguồn thay thế có logic bất đồng bộ hoặc phát lỗi. Cả hai chỉ kích hoạt khi upstream **hoàn tất rỗng**; chúng không cứu một nguồn `error()` hoặc một nguồn `never()`.

## 4. Tạo nguồn kết thúc lỗi: `error()`

Dùng `Mono.error` hoặc `Flux.error` khi hệ thống **không thể cung cấp kết quả thành công**: dữ liệu đầu vào không hợp lệ, thao tác bị từ chối, hoặc một dependency thất bại.

```java
Mono<String> failedLookup =
        Mono.error(new IllegalArgumentException("invalid id"));

Flux<String> failedStream =
        Flux.error(new IllegalStateException("source unavailable"));
```

Subscriber nhận `onError`. Đối với chính nguồn `error()` ở trên, **không có `onNext` và không có `onComplete`**.

### Phân biệt tạo lỗi và phát tín hiệu lỗi

```java
Mono<String> eager = Mono.error(
        new IllegalArgumentException("invalid id")
);

Mono<String> lazy = Mono.error(
        () -> new IllegalArgumentException("invalid id")
);
```

- Ở `eager`, đối tượng exception được tạo ngay khi chạy biểu thức `new IllegalArgumentException(...)`; **tín hiệu** lỗi chỉ được phát khi có subscriber.
- Ở `lazy`, `Supplier` tạo exception **mỗi lần subscription**. Cách này hữu ích khi cần lỗi mới kèm ngữ cảnh được xác định ở thời điểm đăng ký hoặc không muốn khởi tạo exception trước.
- Cả hai **không** tương đương `throw new IllegalArgumentException(...)` từ ngay bên ngoài pipeline: `throw` có thể làm phương thức Java kết thúc trước khi trả về publisher.

Ví dụ nhánh từ chối trong một service reactive:

```java
Mono<String> findUsername(boolean permitted) {
    if (!permitted) {
        return Mono.error(
                new SecurityException("access denied")
        );
    }
    return Mono.just("alice");
}
```

Đoạn trên là **phương thức minh họa trong một class có Reactor**, không phải file Java độc lập. Caller nhận một `Mono<String>` và quyết định cách quan sát hoặc xử lý lỗi.

### Lỗi có thể xuất hiện sau một vài phần tử `Flux`

```java
Flux<String> stream = Flux.concat(
        Flux.just("A", "B"),
        Flux.error(new IllegalStateException("failed")),
        Flux.just("C")
);
```

Khi subscribe bình thường, stream phát `"A"`, `"B"`, rồi `onError`; `"C"` **không được phát**, vì lỗi đã kết thúc chuỗi. `Flux.empty()` ở cùng vị trí chỉ hoàn tất thành công, cho phép `concat` tiếp tục với nguồn kế tiếp.

```text
concat(just(A,B), empty(), just(C))   -> A, B, C, complete
concat(just(A,B), error(e), just(C))  -> A, B, error(e)
concat(just(A,B), never(), just(C))   -> A, B, rồi chờ mãi nếu không cancel/timeout
```

`concat` lần lượt subscribe các nguồn theo thứ tự và cần nguồn trước **hoàn thành thành công** để đi tiếp.

### Xử lý lỗi là một nhánh khác xử lý empty

```java
Mono<String> recovered = failedLookup
        .onErrorResume(IllegalArgumentException.class,
                error -> Mono.just("guest"));
```

`onErrorResume` chạy khi upstream phát `onError` phù hợp. Có thể dùng `onErrorReturn` để trả giá trị dự phòng, hoặc `onErrorMap` để chuyển exception thành loại lỗi phù hợp hơn.

```java
Mono<String> ignoredError = failedLookup.onErrorComplete();
```

`onErrorComplete` biến lỗi thành hoàn tất rỗng; việc này **làm mất thông tin lỗi ở downstream**, nên chỉ dùng khi nghiệp vụ có chủ ý coi lỗi đó là không có dữ liệu. Không thay mọi lỗi thành empty vì sẽ che đi hỏng hóc hệ thống.

Để *chuyển empty thành lỗi*:

```java
Mono<String> requiredUser = Mono.<String>empty()
        .switchIfEmpty(Mono.error(
                new java.util.NoSuchElementException("user not found")
        ));
```

Điều này khác `onErrorResume`: toán tử `switchIfEmpty` chỉ phản ứng với `onComplete` mà không có `onNext`, còn `onErrorResume` phản ứng với `onError`.

## 5. Tạo nguồn không bao giờ phát hoặc kết thúc: `never()`

```java
Mono<String> waitingOne = Mono.never();
Flux<String> waitingMany = Flux.never();
```

Sau khi subscribe, một nguồn `never()` không phát `onNext`, `onComplete` hay `onError`. Nó chỉ tồn tại như subscription đang chờ cho đến khi **bị hủy**, **bị thay thế bởi logic giới hạn thời gian**, hoặc phía ngoài ngừng theo dõi. `never()` không tự thực hiện công việc nền hoặc tự tạo một thread chờ.

`never()` có ích chủ yếu trong **kiểm thử luồng điều khiển**, thử hành vi cancel, timeout hoặc ghép nguồn. Trong logic nghiệp vụ thực tế, một nguồn never vô tình có thể làm request HTTP hoặc tác vụ chờ không có hồi kết.

### Phân biệt `never()` và chuỗi vô hạn

| Biểu thức | Điều gì xảy ra? |
|---|---|
| `Flux.never()` | Không phát phần tử nào; không hoàn tất, không lỗi |
| `Flux.interval(Duration.ofSeconds(1))` | Phát lần lượt các số `0`, `1`, `2`, ... theo nhịp; không tự hoàn tất nếu không giới hạn |
| `Mono.delay(Duration.ofSeconds(1))` | Sau khoảng hẹn phát một giá trị `Long`, rồi hoàn tất |
| `Mono.empty()` | Hoàn tất ngay, không cần chờ |
| `Mono.never().take(Duration.ofSeconds(2))` | Có thể hoàn tất rỗng do **toán tử `take`** áp thời hạn; bản thân `never()` vẫn không tự hoàn tất |
| `Mono.never().timeout(Duration.ofSeconds(2))` | Đưa ra **lỗi timeout** nếu không có tín hiệu thích hợp trước hạn |

Đừng gọi “không phát dữ liệu” và “hoàn thành rỗng” là cùng một trạng thái. Với `never()`, toán tử cần `onComplete` như `then`, `collectList` hoặc `switchIfEmpty` sẽ không có cơ hội hoàn thành nếu không có cơ chế can thiệp.

### Hủy subscription bằng `dispose()`

Khi dùng overload `.subscribe(...)`, Reactor trả một `Disposable`. Người sở hữu subscription có thể gọi `dispose()` để hủy:

```java
Disposable subscription = Mono.never()
        .doFinally(signal ->
                System.out.println(signal.name()))
        .subscribe();

subscription.dispose();
```

Khi hủy thành công trong ví dụ, `doFinally` quan sát `CANCEL`. Tín hiệu này **không phải** `onComplete` gửi cho subscriber. Nếu gọi `dispose()` trên subscription đã hoàn tất, không có một terminal mới nào được sinh ra.

Trong ứng dụng WebFlux, framework thường sở hữu subscription của response: controller nên **trả `Mono`/`Flux`**, để framework quản lý đăng ký, kết thúc và việc ngắt kết nối. Không tự subscribe thủ công trong controller chỉ để “cho code chạy”.

### Chặn việc chờ vô hạn bằng timeout

```java
Mono<String> guarded = Mono.<String>never()
        .timeout(
                Duration.ofSeconds(2),
                Mono.just("fallback")
        );
```

Với overload có fallback, khi hết thời hạn mà chưa có kết quả, Reactor chuyển sang publisher dự phòng, thay vì phát lỗi `TimeoutException`. Với `timeout(Duration)` **không có fallback**, luồng kết thúc bằng lỗi timeout; khi đó có thể dùng `onErrorResume` để quyết định xử lý.

Tác động ở ranh giới thời gian do operator thêm vào: `never()` không đổi bản chất. Timeout không bảo đảm mọi tác vụ ngoài Reactor dừng ngay lập tức nếu chúng không hỗ trợ cancellation.

**Cảnh báo:** đừng gọi `.block()` không giới hạn trên `Mono.never()`; thread gọi có thể chờ vô thời hạn. Trong event loop WebFlux, nói chung không nên gọi `.block()` ngay cả với nguồn sẽ hoàn tất.

## 6. Chương trình Java 17+ chạy được: quan sát `empty`, `error`, `never`

Ví dụ này sử dụng **Reactor Core độc lập**, không cần khởi động Spring Boot. Java 17+, Maven và khả năng tải dependency Maven là đủ. Reactor `3.6.6` được cố định để ví dụ có phiên bản xác định; dự án Spring Boot thực tế nên dùng phiên bản Reactor do Spring Boot quản lý để tránh xung đột.

Tạo cấu trúc:

```text
reactor-signal-demo/
├── pom.xml
└── src/main/java/edu/demo/SignalDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-signal-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
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

Nội dung `src/main/java/edu/demo/SignalDemo.java`:

```java
package edu.demo;

import java.time.Duration;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;

public final class SignalDemo {
    public static void main(String[] args) {
        trace("empty", Mono.<String>empty(), false);
        trace("error", Mono.<String>error(
                new IllegalArgumentException("bad-id")), false);
        trace("never", Mono.<String>never(), true);

        String emptyFallback = Mono.<String>empty()
                .defaultIfEmpty("anonymous")
                .block();
        System.out.println("emptyFallback=" + emptyFallback);

        String errorFallback = Mono.<String>error(
                        new IllegalStateException("down"))
                .onErrorReturn("cached")
                .block();
        System.out.println("errorFallback=" + errorFallback);

        String timeoutFallback = Mono.<String>never()
                .timeout(
                        Duration.ofMillis(150),
                        Mono.just("timed-out"))
                .block(Duration.ofSeconds(2));
        System.out.println("timeoutFallback=" + timeoutFallback);
    }

    private static void trace(
            String label, Mono<String> publisher, boolean cancel) {
        System.out.println("[" + label + "]");

        Disposable subscription = publisher
                .doOnSubscribe(ignored ->
                        System.out.println("subscribe"))
                .doFinally(signal ->
                        System.out.println("finally=" + signal.name()))
                .subscribe(
                        value -> System.out.println("next=" + value),
                        error -> System.out.println(
                                "error=" + error.getClass().getSimpleName()
                                + ":" + error.getMessage()),
                        () -> System.out.println("complete")
                );

        if (cancel) {
            subscription.dispose();
        }
    }
}
```

Từ thư mục chứa `pom.xml`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=edu.demo.SignalDemo
```

Các dòng `System.out` kỳ vọng theo thứ tự (Maven có thể in thông tin riêng tùy cấu hình):

```text
[empty]
subscribe
complete
finally=ON_COMPLETE
[error]
subscribe
error=IllegalArgumentException:bad-id
finally=ON_ERROR
[never]
subscribe
finally=CANCEL
emptyFallback=anonymous
errorFallback=cached
timeoutFallback=timed-out
```

Giải thích:

1. `empty`: subscriber đã được đăng ký, nhận `onComplete` không kèm `onNext`; `doFinally` thấy `ON_COMPLETE`.
2. `error`: subscriber nhận `onError` và không nhận `onComplete`; `doFinally` thấy `ON_ERROR`.
3. `never`: không có callback `next`, `complete` hay `error`; `dispose()` tạo kết thúc vòng đời subscription theo đường `CANCEL`, và `doFinally` thấy `CANCEL`.
4. `defaultIfEmpty` chỉ xử lý empty; `onErrorReturn` chỉ xử lý lỗi; `timeout` thêm cơ chế giới hạn thời gian cho never. `.block(Duration.ofSeconds(2))` trong ví dụ là cách chờ **ở chương trình console**; không dùng kỹ thuật đó trên event-loop thread trong controller WebFlux.

Không gọi `.block()` để quan sát `Mono.never()` trực tiếp. Ở ví dụ này, `never` được hủy hoặc có timeout rõ ràng nên chương trình có thể kết thúc.

## 7. `Flux.empty`, `Flux.error`, `Flux.never` cũng tuân thủ cùng quy tắc

`Flux` có thể phát nhiều `onNext` trước terminal, nhưng các factory rỗng/lỗi/never vẫn dùng cùng ngữ nghĩa:

```java
Flux<Integer> emptyNumbers = Flux.empty();
Flux<Integer> failedNumbers =
        Flux.error(new IllegalStateException("bad source"));
Flux<Integer> waitingNumbers = Flux.never();
```

Các đoạn này cần import `reactor.core.publisher.Flux`. Để thấy tác động khi ghép nguồn:

```java
Flux<String> continues = Flux.concat(
        Flux.just("one"),
        Flux.empty(),
        Flux.just("two")
);

Flux<String> stops = Flux.concat(
        Flux.just("one"),
        Flux.error(new IllegalStateException("stop")),
        Flux.just("two")
);

Flux<String> waits = Flux.concat(
        Flux.just("one"),
        Flux.never(),
        Flux.just("two")
);
```

`continues` phát `one`, `two`, rồi complete. `stops` phát `one`, rồi error. `waits` phát `one`, sau đó không hoàn tất nếu không có giới hạn/hủy bên ngoài, nên phần `two` sẽ không được phát. Các đoạn này là **snippet**, không phải chương trình chạy độc lập; kiểu `Flux<String>` được suy ra từ nguồn `just` và toán tử `concat`.

Với `Flux.error(...)` nằm sau một nguồn dữ liệu, các phần tử đã phát **không bị thu hồi**. Error là terminal kể từ thời điểm nó được phát, không phải thao tác rollback các sự kiện `onNext` mà subscriber đã nhận.

## 8. Kiểm thử phản ứng tín hiệu bằng `StepVerifier`

Kiểm thử nguồn reactive nên xác nhận **đúng tín hiệu**, thay vì chỉ gọi `.block()` rồi so sánh giá trị. `reactor-test` cung cấp `StepVerifier` để kỳ vọng thứ tự sự kiện. Đặc biệt, với `never`, test cần **cancel hoặc áp timeout/virtual time**, nếu không có thể treo.

Để bổ sung kiểm thử cho dự án Maven ở mục 6, thêm dependencies vào phần `<dependencies>`:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <version>3.6.6</version>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.10.2</version>
    <scope>test</scope>
</dependency>
```

Thêm `maven-surefire-plugin` vào danh sách `<plugins>`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
</plugin>
```

Tạo `src/test/java/edu/demo/SignalDemoTest.java`:

```java
package edu.demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class SignalDemoTest {
    @Test
    void emptyCompletesWithoutAValue() {
        StepVerifier.create(Mono.<String>empty())
                .verifyComplete();

        StepVerifier.create(Flux.<Integer>empty())
                .verifyComplete();
    }

    @Test
    void errorTerminatesTheSequence() {
        Flux<String> source = Flux.concat(
                Flux.just("A"),
                Flux.<String>error(
                        new IllegalArgumentException("invalid")),
                Flux.just("B")
        );

        StepVerifier.create(source)
                .expectNext("A")
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "invalid".equals(error.getMessage()))
                .verify();
    }

    @Test
    void neverCanBeCancelledOrTimedOut() {
        StepVerifier.create(Mono.<String>never())
                .expectSubscription()
                .thenCancel()
                .verify();

        StepVerifier.withVirtualTime(() ->
                        Mono.<String>never()
                                .timeout(Duration.ofSeconds(5)))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(5))
                .expectError(TimeoutException.class)
                .verify();
    }
}
```

Chạy:

```bash
mvn test
```

Khi các assertion đúng, cả ba phương thức test sẽ thành công; `StepVerifier.withVirtualTime` mô phỏng việc trôi qua 5 giây trên scheduler ảo mà không phải chờ 5 giây thực tế. Luôn dựng pipeline có toán tử thời gian **bên trong supplier** của `withVirtualTime`, như ví dụ, để scheduler ảo được thiết lập trước.

Test thứ ba cố ý có hai cách thoát khỏi never:

- `.thenCancel()` gửi tín hiệu hủy và kiểm tra việc đóng subscription.
- `.timeout(Duration.ofSeconds(5))` tạo `TimeoutException` sau thời hạn ảo; lúc này **toán tử timeout** là nguồn của `onError`, chứ không phải `Mono.never()` tự phát lỗi.

Nếu kiểm tra `never()` bằng `StepVerifier.create(Mono.never()).verifyComplete()`, test không có cơ chế kết thúc và có thể bị kẹt.

## 9. Áp dụng trong Spring WebFlux

Trong controller WebFlux, `Mono`/`Flux` là cách mô tả công việc để Spring theo dõi và chuyển thành HTTP response. Ba loại tín hiệu không tự động đồng nghĩa với ba HTTP status cụ thể.

Ví dụ **snippet tích hợp** trong một class `@RestController` đã import `Mono`, `ResponseEntity`, `ResponseStatusException`, `HttpStatus`, `Duration`, `@GetMapping` và `@PathVariable`:

```java
@GetMapping("/items/{id}")
public Mono<ResponseEntity<String>> item(@PathVariable String id) {
    Mono<String> found = "42".equals(id)
            ? Mono.just("item-42")
            : Mono.empty();

    return found
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}

@GetMapping("/reject")
public Mono<String> reject() {
    return Mono.error(new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "invalid request"));
}

@GetMapping("/guarded")
public Mono<String> guarded() {
    return Mono.<String>never()
            .timeout(Duration.ofSeconds(2), Mono.just("fallback"));
}
```

Đây là snippet minh họa **cần đặt trong một WebFlux controller thực tế**, chưa phải ứng dụng Spring Boot độc lập; endpoint `/guarded` sử dụng `never` chỉ để biểu diễn việc xử lý timeout. Trong hệ thống thực, hãy áp timeout cho publisher từ HTTP client, database hoặc service thật.

- `/items/42`: phát `ResponseEntity` chứa `"item-42"` và HTTP 200.
- `/items/other`: nhánh rỗng kích hoạt `defaultIfEmpty`, tạo `ResponseEntity` với HTTP 404.
- `/reject`: Reactor phát tín hiệu lỗi `ResponseStatusException`, để cơ chế xử lý HTTP của Spring WebFlux chuyển thành phản hồi lỗi phù hợp (HTTP 400 trong cấu hình chuẩn).
- `/guarded`: sau khoảng 2 giây, trả body `"fallback"` do toán tử timeout, không giữ request chờ vô hạn.

**Không mặc định coi `Mono.empty()` là HTTP 404.** Nó là tín hiệu hoàn tất không có payload; muốn quyết định mã HTTP, hãy trả `Mono<ResponseEntity<T>>`, ném/map lỗi phù hợp, hoặc xử lý trên controller/advice theo hợp đồng API.

### Dùng empty, error, never đúng theo mục đích

| Nghiệp vụ | Biểu diễn phù hợp | Điều kiện |
|---|---|---|
| Tìm kiếm cho phép không tìm thấy | `Mono.empty()` | Caller chủ động quyết định giá trị thay thế hoặc 404 |
| Tác vụ cập nhật thành công, không cần payload | `Mono<Void>` hoàn tất | Lỗi vẫn truyền bằng `onError` |
| ID sai, truy cập bị từ chối, dependency lỗi | `Mono.error(...)` | Dùng loại exception/HTTP mapping rõ ràng |
| Thử hành vi cancellation hoặc timeout | `Mono.never()` trong test | Test bắt buộc cancel/timeout |
| Thao tác mạng thực tế có thể treo | Publisher từ client thật + `.timeout(...)` | Cấu hình timeout, retry và fallback theo nghiệp vụ |

Tránh tạo `Mono.never()` như cách thay thế cho “chưa có kết quả”. Với kết quả chưa sẵn sàng, nguồn reactive cần **thực sự phát dữ liệu, complete hoặc error khi điều kiện thay đổi**; `never()` tự nó không theo dõi bất kỳ sự kiện nào.

## 10. Quan sát và chẩn đoán tín hiệu

Các operator quan sát giúp xác định nguồn đang ở trạng thái nào:

- `doOnSubscribe`: có subscriber đăng ký.
- `doOnNext`: một giá trị được phát; không chạy với ba factory trực tiếp `empty`, `error`, `never`.
- `doOnComplete`: dành cho `Flux`, chạy khi `Flux` hoàn tất thành công.
- `doOnSuccess`: dành cho `Mono`, chạy khi hoàn tất thành công; nếu Mono rỗng thì tham số có thể là **`null`**. Đây là callback quan sát, **không có nghĩa Mono phát `onNext(null)`**.
- `doOnError`: quan sát lỗi.
- `doOnCancel`: quan sát yêu cầu cancel.
- `doFinally`: quan sát kiểu kết thúc vòng đời (`ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`), nên hữu ích để phân biệt các tình huống.

Ví dụ:

```java
Mono.<String>empty()
    .doOnSuccess(value ->
            System.out.println(value == null ? "empty" : value))
    .subscribe();
```

Đoạn snippet này in `empty` vì `doOnSuccess` nhận `null` khi `Mono` hoàn tất không có giá trị; nó **không thể** dùng để chứng minh đã có `onNext`.

Đừng ghi log và nuốt lỗi một cách vô tình. Khi gọi `.subscribe(...)` thủ công với publisher có khả năng phát lỗi, nên truyền `errorConsumer`; nếu thiếu, lỗi không được ứng dụng xử lý đúng có thể bị Reactor báo là lỗi chưa có error callback. Trong Spring WebFlux, phần lớn controller trả thẳng publisher để framework xử lý subscription và lỗi qua tầng HTTP.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Dùng `Mono.just(null)` để đại diện không có dữ liệu | Reactor không cho phép `null` phần tử | Dùng `Mono.empty()` hoặc `Mono.justOrEmpty(...)` |
| Dùng `Mono.never()` thay cho `Mono.empty()` | `switchIfEmpty`, `then`, `collectList` không thể hoàn tất | Nếu không có phần tử mà tác vụ đã kết thúc, dùng `empty()` |
| Dùng `Mono.empty()` thay `Mono.error()` khi dependency thất bại | Lỗi thực bị hiểu như kết quả vắng mặt | Trả tín hiệu lỗi và map lỗi theo nghiệp vụ |
| Cho rằng `error()` chạy `throw` ngay lúc tạo publisher | Nhầm thời điểm thực thi và subscribe | Phân biệt khởi tạo Throwable với phát `onError` |
| Gọi `.block()` trên `never()` | Thread chờ không giới hạn | Dùng timeout/cancel; tránh `.block()` trên WebFlux event loop |
| Quên error callback ở `.subscribe(...)` thủ công | Lỗi không được xử lý đúng | Truyền error consumer hoặc để framework sở hữu subscription |
| Dùng `defaultIfEmpty` để chữa lỗi | Operator không chạy khi nhận `onError` | Dùng `onErrorResume`/`onErrorReturn` theo chính sách |
| Dùng `onErrorResume` cho nguồn `empty()` | Không có `onError` để kích hoạt | Dùng `switchIfEmpty` hoặc `defaultIfEmpty` |
| Chờ `never()` tự bị `timeout` dù chưa thêm operator | Publisher không có cơ chế timeout nội tại | Thêm `.timeout(...)` hoặc timeout của tầng I/O |
| Xem `cancel()` là `onComplete` | Sai ý nghĩa vòng đời | Quan sát `doFinally(CANCEL)` và hủy tài nguyên hợp lý |

## 12. Bài tập tự kiểm tra

**Bài 1.** Dự đoán tín hiệu từ:

```java
Mono.<String>empty()
    .switchIfEmpty(Mono.just("guest"));
```

Kết quả: phát `"guest"` rồi complete, vì upstream kết thúc rỗng.

**Bài 2.** Dự đoán tín hiệu từ:

```java
Mono.<String>error(new IllegalStateException("failure"))
    .defaultIfEmpty("guest");
```

Kết quả: `onError(IllegalStateException)`. `defaultIfEmpty` không chạy vì upstream **lỗi**, không hoàn tất rỗng.

**Bài 3.** Dự đoán tín hiệu từ:

```java
Mono.<String>never()
    .switchIfEmpty(Mono.just("guest"));
```

Kết quả: không phát `"guest"`, không complete, không error nếu không có cancellation/timeout từ bên ngoài. `switchIfEmpty` cần thấy một `onComplete` rỗng nhưng chưa bao giờ nhận được.

**Bài 4.** Vì sao đoạn `Flux.concat(Flux.just("A"), Flux.error(e), Flux.just("B"))` không phát `"B"`?

Kết quả: `concat` phải chờ nguồn thứ hai hoàn tất thành công mới subscribe nguồn thứ ba. Nguồn thứ hai phát `onError`, khiến toàn bộ concat kết thúc lỗi.

**Bài 5.** Muốn kiểm thử một publisher mãi không phát dữ liệu mà không treo test, nên dùng cách nào?

Kết quả: `StepVerifier` với `.thenCancel()` hoặc bọc `.timeout(...)` và xác nhận `TimeoutException` (ưu tiên virtual time cho kiểm thử thời gian).

## 13. Tổng kết kiến thức

Ba factory khác nhau ở **tín hiệu kết thúc**, không chỉ ở số lượng giá trị:

- `empty()` nghĩa là *không có dữ liệu và đã hoàn tất thành công*.
- `error(e)` nghĩa là *đã thất bại; truyền lỗi đến subscriber*.
- `never()` nghĩa là *không có dữ liệu và cũng không thông báo kết thúc hay thất bại*.

Khi xây pipeline, hãy xác định liệu downstream cần xử lý **empty** (`defaultIfEmpty`, `switchIfEmpty`), **error** (`onErrorResume`, `onErrorReturn`) hay **chờ không có tín hiệu** (`timeout`, cancellation). Quan sát `doFinally` và viết `StepVerifier` để xác nhận chính xác ba nhánh.

## Tài liệu chính thức

- Project Reactor, **Mono API** (`empty`, `error`, `never`, `doFinally`, `timeout`): https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Project Reactor, **Flux API**: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Project Reactor, **Simple Ways to Create a Flux or Mono and Subscribe to It**: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Project Reactor, **Handling Errors**: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Project Reactor, **Testing**: https://projectreactor.io/docs/core/release/reference/testing.html
- Spring Framework, **WebFlux `ResponseEntity`**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html