# doOnCancel, doOnTerminate và doFinally

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Hủy và tài nguyên

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt ba kết cục của một subscription trong Reactor: **hoàn tất thành công**, **kết thúc bằng lỗi** và **bị hủy**.
2. Giải thích đúng lúc nào `doOnCancel`, `doOnTerminate` và `doFinally` chạy trên `Mono`/`Flux`, cùng thứ tự tương đối giữa callback và tín hiệu đi qua operator.
3. Sử dụng `SignalType.ON_COMPLETE`, `SignalType.ON_ERROR` và `SignalType.CANCEL` để thống kê hoặc dọn dẹp nhất quán theo kết cục.
4. Hiểu khác biệt khi đặt hook **trước hay sau** `take`, `timeout`, `onErrorResume` và các ranh giới khác.
5. Phân biệt side-effect hook dùng để **quan sát** với cơ chế **sở hữu, đóng tài nguyên** như `using`, `usingWhen`, `doOnDiscard`.
6. Áp dụng trong Spring WebFlux mà không tự gọi `subscribe()` trong controller; hiểu giới hạn thực tế khi client ngắt kết nối.

## 1. Tại sao phải quan tâm cả hủy, hoàn tất và lỗi?

Ứng dụng reactive không chỉ xử lý giá trị `onNext`. Khi kết nối HTTP đóng, người dùng ngừng xem stream, timeout xảy ra hoặc toàn bộ dữ liệu đã được gửi xong, vòng đời subscription có thể kết thúc theo những con đường khác nhau. Nếu chỉ dọn tài nguyên lúc `onComplete`, bạn có thể bỏ sót cancellation. Nếu chỉ xử lý `onError`, bạn cũng bỏ sót trường hợp downstream không muốn nhận tiếp dù nguồn không lỗi.

Một pipeline Reactor được xây dựng từ những publisher như `Mono<T>` (tối đa một giá trị) và `Flux<T>` (0 đến nhiều giá trị). Theo Reactive Streams, subscriber nhận `onSubscribe` và các `onNext` hợp lệ, sau đó có thể nhận một trong hai tín hiệu terminal:

- **`onComplete`:** nguồn hoàn tất thành công; không có thêm phần tử.
- **`onError(Throwable)`:** nguồn kết thúc bằng lỗi; không phát tiếp `onNext` hay `onComplete`.
- **`Subscription.cancel()`:** hướng điều khiển **từ downstream ngược về upstream**, thể hiện việc subscriber không còn nhu cầu. Đây không phải `onComplete` hoặc `onError` được phát xuống subscriber.

Do đó, khi nói “kết thúc”, phải hỏi rõ **kết thúc theo cách nào**. Reactor cung cấp ba hook liên quan, nhưng **không thể xem chúng là đồng nghĩa**.

```text
                        Subscription đang hoạt động
                                   |
           +-----------------------+----------------------+
           |                       |                      |
        onComplete               onError                 cancel()
           |                       |                      |
   doOnTerminate chạy     doOnTerminate chạy      doOnCancel chạy
           |                       |                      |
       downstream                downstream              upstream
       hoàn tất                  nhận lỗi                nhận cancel
           |                       |                      |
   doFinally(ON_COMPLETE)  doFinally(ON_ERROR)     doFinally(CANCEL)
```

Sơ đồ là mô hình khái niệm cho **một vị trí hook** trong pipeline; thứ tự thực thi cụ thể còn phụ thuộc vị trí các operator, nguồn đồng bộ/bất đồng bộ và đoạn pipeline được quan sát. Điều cốt lõi là:

- `doOnCancel` chỉ quan sát **cancel**.
- `doOnTerminate` chỉ quan sát **complete hoặc error**, không quan sát cancel.
- `doFinally` quan sát **cả complete, error và cancel**, đồng thời biết loại kết thúc.

## 2. So sánh nhanh ba operator

| Toán tử | Callback | Khi hoàn tất thành công | Khi lỗi | Khi cancel | Nhận lý do? |
| --- | --- | --- | --- | --- | --- |
| `doOnCancel(Runnable)` | `() -> ...` | Không | Không | **Có** | Không; biết đó là nhánh cancel. |
| `doOnTerminate(Runnable)` | `() -> ...` | **Có** | **Có** | Không | Không; dùng hook khác để biết error hay complete. |
| `doFinally(Consumer<SignalType>)` | `signal -> ...` | **Có** | **Có** | **Có** | **Có**, qua `SignalType`. |

Tất cả là những **side-effect operator**: chúng trả về một publisher mới, giữ dạng dữ liệu của pipeline; callback không biến một giá trị thành giá trị khác và cũng không tự “khôi phục” lỗi. Ví dụ:

```java
Flux<String> observed = source
        .doOnCancel(() -> metrics.incrementCancelled())
        .doOnTerminate(() -> metrics.incrementTerminated())
        .doFinally(signal -> metrics.recordFinalSignal(signal));
```

Đây là **đoạn minh họa**, cần có `Flux<String> source` và `metrics` do ứng dụng định nghĩa. Việc viết chuỗi toán tử chưa chạy callback của những subscription lazy; callback chạy khi subscription đi tới tín hiệu tương ứng. Nếu không có subscriber hoặc pipeline không bao giờ nhận kết cục phù hợp, callback có thể không chạy.

### 2.1. doOnCancel: quan sát yêu cầu hủy

Chữ ký thường gặp:

```java
Flux<T> doOnCancel(Runnable onCancel)
Mono<T> doOnCancel(Runnable onCancel)
```

Khi cancellation đi ngược qua operator này, Reactor chạy callback `onCancel` **trước**, sau đó mới chuyển `cancel` ngược về upstream tại vị trí ấy. Đây là hook tốt cho việc ghi log, tăng bộ đếm hủy hoặc báo cho thành phần sở hữu tài nguyên rằng downstream không muốn nhận tiếp.

```java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1))
        .doOnCancel(() -> System.out.println("subscriber cancelled"));
```

Đây là **đoạn minh họa**, cần import `java.time.Duration` và `Flux`. Câu lệnh này không tự khởi chạy timer; phải có subscription. Khi subscriber hủy, hook quan sát cancellation. Không suy ra từ hook rằng mọi tác vụ I/O đang thực hiện đều đã dừng ngay hoặc các side effect trước đó được rollback.

**Không dùng `doOnCancel` để phát hiện lỗi.** Nếu upstream phát `onError`, không có lý do để callback cancel chạy chỉ vì lỗi. Tương tự, một nguồn hoàn tất bình thường không tự biến completion thành cancellation.

### 2.2. doOnTerminate: quan sát complete hoặc error

Chữ ký:

```java
Flux<T> doOnTerminate(Runnable onTerminate)
Mono<T> doOnTerminate(Runnable onTerminate)
```

`doOnTerminate` chạy khi publisher ở vị trí đó hoàn tất thành công hoặc báo lỗi. Callback được thực thi **trước khi** tín hiệu kết thúc được chuyển tiếp xuống downstream. Nó **không** chạy đơn thuần vì subscriber hủy.

```java
Flux<Integer> observed = Flux.range(1, 3)
        .doOnTerminate(() -> System.out.println("source terminated"));
```

Đoạn trên là **minh họa**: khi có subscriber tiêu thụ hết ba phần tử, callback chạy một lần do completion. Khi nguồn báo lỗi, callback cũng chạy, nhưng từ một `Runnable` bạn không nhận được `Throwable` hay cờ phân biệt hai trường hợp.

Nếu cần phân biệt:

```java
Flux<Integer> observed = source
        .doOnComplete(() -> metrics.completed())
        .doOnError(error -> metrics.failed(error))
        .doOnTerminate(() -> metrics.terminated());
```

Đây là **đoạn minh họa**, `source` và `metrics` do ứng dụng định nghĩa. `doOnComplete` là hook của `Flux` khi hoàn tất thành công, `doOnError` nhận exception; `doOnTerminate` có thể đếm tổng kết cục không bao gồm cancel. Tránh đếm cùng một sự kiện hai lần nếu dashboard của bạn cộng các metric có ý nghĩa khác nhau.

**Lưu ý riêng cho Mono:** `Mono` phát một phần tử thành công thì về ngữ nghĩa đã biết nó sẽ hoàn tất, vì vậy `Mono.doOnTerminate` được gọi **trước khi phần tử `onNext` được chuyển tiếp** xuống downstream, khác với `Flux.doOnTerminate` vốn chỉ chạy khi có `onComplete` hoặc `onError`. Với `Mono.empty()`, hook chạy trước `onComplete`; với `Mono.error(...)`, hook chạy trước `onError`. Đây là khác biệt quan trọng khi bạn kiểm tra thứ tự log.

### 2.3. doFinally: xử lý chung mọi kết cục

Chữ ký:

```java
Flux<T> doFinally(Consumer<SignalType> onFinally)
Mono<T> doFinally(Consumer<SignalType> onFinally)
```

`doFinally` nhận loại kết cục:

| `SignalType` | Ý nghĩa |
| --- | --- |
| `ON_COMPLETE` | Subscription ở vị trí operator đã hoàn tất thành công. |
| `ON_ERROR` | Subscription ở vị trí operator đã kết thúc bằng lỗi. |
| `CANCEL` | Downstream đã hủy qua subscription tại vị trí operator. |

Ví dụ:

```java
Flux<String> traced = source.doFinally(signal -> {
    switch (signal) {
        case ON_COMPLETE -> metrics.record("completed");
        case ON_ERROR -> metrics.record("failed");
        case CANCEL -> metrics.record("cancelled");
        default -> metrics.record("other");
    }
});
```

Đây là **đoạn minh họa Java 17**, cần `Flux<String> source` và `metrics` do ứng dụng định nghĩa. Reactor gọi callback **sau khi đã chuyển tiếp tín hiệu kết thúc theo hướng thích hợp** (hoàn tất/lỗi đi downstream; cancel truyền upstream). Vì thế, `doFinally` hữu ích cho cleanup/metrics theo loại kết cục; nhưng không dùng callback này để “đổi” lỗi thành response khác.

Nếu gắn nhiều `doFinally` liên tiếp, callback thường được gọi theo **thứ tự ngược với thứ tự khai báo** khi một terminal event lan qua chuỗi:

```java
Flux.just("x")
    .doFinally(signal -> System.out.println("first " + signal))
    .doFinally(signal -> System.out.println("second " + signal));
```

Đây là **đoạn minh họa chưa subscribe**; khi được subscribe và hoàn tất, hook `second` chạy trước hook `first`. Đừng dựa vào việc callback `doFinally` đã kịp cập nhật một bộ đếm ngay sau khi một lệnh `block()` hoặc `blockLast()` trả về trong trường hợp khác: terminal signal có thể đến downstream **trước khi** `doFinally` hoàn thành, đặc biệt trong pipeline bất đồng bộ. Với test cần xác nhận cleanup, hãy đợi tín hiệu cleanup riêng hoặc dùng cơ chế kiểm thử có đồng bộ phù hợp.

## 3. Chương trình Java 17+ chạy được: bốn kết cục quan sát được

Ví dụ dùng **Java 17+**, **Maven** và **Project Reactor Core 3.8.8**. Để output có thứ tự dễ kiểm tra, chúng ta sử dụng nguồn đồng bộ (`Flux.just`, `Flux.range`, `Flux.error` và `Mono.just`) thay vì HTTP/timer. Mỗi kịch bản có subscriber riêng.

Tạo cấu trúc:

```text
termination-hooks-demo/
├── pom.xml
└── src/main/java/demo/
    └── TerminationHooksDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>termination-hooks-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
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

### src/main/java/demo/TerminationHooksDemo.java

```java
package demo;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class TerminationHooksDemo {
    private static void successfulFlux() {
        System.out.println("=== COMPLETE ===");
        Flux.range(1, 2)
                .doOnCancel(() ->
                        System.out.println("source: cancel"))
                .doOnTerminate(() ->
                        System.out.println("source: terminate"))
                .doFinally(signal ->
                        System.out.println("source: finally " + signal.name()))
                .subscribe(
                        value -> System.out.println("downstream: " + value),
                        error -> System.out.println("downstream error"),
                        () -> System.out.println("downstream: complete"));
    }

    private static void failingFlux() {
        System.out.println("=== ERROR ===");
        Flux.concat(
                    Flux.just(7),
                    Flux.<Integer>error(
                            new IllegalStateException("broken")))
                .doOnCancel(() ->
                        System.out.println("source: cancel"))
                .doOnTerminate(() ->
                        System.out.println("source: terminate"))
                .doFinally(signal ->
                        System.out.println("source: finally " + signal.name()))
                .subscribe(
                        value -> System.out.println("downstream: " + value),
                        error -> System.out.println("downstream: error " +
                                error.getClass().getSimpleName()),
                        () -> System.out.println("downstream: complete"));
    }

    private static void cancelledFlux() {
        System.out.println("=== CANCEL ===");
        Flux.range(1, 5)
                .doOnCancel(() ->
                        System.out.println("source: cancel"))
                .doOnTerminate(() ->
                        System.out.println("source: terminate"))
                .doFinally(signal ->
                        System.out.println("source: finally " + signal.name()))
                .subscribe(new BaseSubscriber<Integer>() {
                    @Override
                    protected void hookOnSubscribe(Subscription subscription) {
                        request(1);
                    }

                    @Override
                    protected void hookOnNext(Integer value) {
                        System.out.println("downstream: " + value);
                        cancel();
                    }

                    @Override
                    protected void hookOnError(Throwable error) {
                        System.out.println("downstream: error");
                    }
                });
    }

    private static void successfulMono() {
        System.out.println("=== MONO ===");
        Mono.just("OK")
                .doOnTerminate(() ->
                        System.out.println("mono: terminate"))
                .doOnNext(value ->
                        System.out.println("mono: doOnNext " + value))
                .doFinally(signal ->
                        System.out.println("mono: finally " + signal.name()))
                .subscribe(
                        value -> System.out.println("mono subscriber: " + value),
                        error -> System.out.println("mono subscriber error"),
                        () -> System.out.println("mono subscriber complete"));
    }

    public static void main(String[] args) {
        successfulFlux();
        failingFlux();
        cancelledFlux();
        successfulMono();
    }
}
```

Chạy trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TerminationHooksDemo
```

**Stdout của chính chương trình** (không tính log hoặc cảnh báo của Maven):

```text
=== COMPLETE ===
downstream: 1
downstream: 2
source: terminate
downstream: complete
source: finally ON_COMPLETE
=== ERROR ===
downstream: 7
source: terminate
downstream: error IllegalStateException
source: finally ON_ERROR
=== CANCEL ===
downstream: 1
source: cancel
source: finally CANCEL
=== MONO ===
mono: terminate
mono: doOnNext OK
mono subscriber: OK
mono subscriber complete
mono: finally ON_COMPLETE
```

**Vì sao chương trình in như vậy?**

- **COMPLETE:** `Flux.range(1, 2)` phát 1, 2 rồi báo hoàn tất. `doOnTerminate` chạy trước khi `onComplete` đến subscriber, còn `doFinally` chạy sau. Không có `source: cancel`.
- **ERROR:** `Flux.concat` phát 7 rồi chuyển sang `Flux.error`. `doOnTerminate` chạy trước khi lỗi đến subscriber, `doFinally` nhận `ON_ERROR`. Không có `downstream: complete`.
- **CANCEL:** `BaseSubscriber` ban đầu chỉ xin 1, nhận 1 rồi gọi `cancel()`. `doOnCancel` chạy; `doFinally` nhận `CANCEL`. `doOnTerminate` **không chạy**, vì không có complete/error ở đoạn nguồn được quan sát.
- **MONO:** `Mono.just("OK")` đã biết sẽ thành công với một phần tử. Với `Mono`, `doOnTerminate` chạy **trước** khi `onNext("OK")` được chuyển tiếp, vì vậy dòng `mono: terminate` đứng trước `mono: doOnNext OK`. Đây là khác biệt quan trọng so với `Flux`.
- Trong cả ba trường hợp cuối, `doFinally` biết được **loại** kết thúc qua `signal.name()`. Việc ví dụ đồng bộ cho ra thứ tự dễ dự đoán không có nghĩa callback ở các publisher async sẽ chạy trên cùng một thread.

**Lưu ý:** Các lời gọi `subscribe(...)` trong `main` chỉ phục vụ bài học CLI độc lập. Trong handler Spring WebFlux, thông thường trả lại publisher cho HTTP framework thay vì tự subscribe.

## 4. Đọc bảng tín hiệu: hook nào chạy khi nào?

Giả sử mỗi publisher được subscribe đúng một lần, các hook được đặt trên cùng một đoạn pipeline và không có operator downstream đổi nghĩa kết thúc:

| Tình huống | doOnCancel | doOnTerminate | doFinally |
| --- | --- | --- | --- |
| `Flux.just(1, 2).subscribe(...)` nhận hết | Không | Có, một lần | `ON_COMPLETE` |
| `Mono.empty()` hoàn tất | Không | Có, một lần | `ON_COMPLETE` |
| `Mono.just("ok")` phát một phần tử thành công | Không | Có, một lần, trước `onNext` | `ON_COMPLETE` |
| `Flux.error(new RuntimeException(...))` | Không | Có, một lần | `ON_ERROR` |
| `Flux.never()` bị subscriber hủy | Có | Không | `CANCEL` |
| `Flux.range(1, 10)` được hủy sau hai giá trị | Có | Không | `CANCEL` |
| Publisher không bao giờ phát terminal và không bị hủy | Không | Không | Không |
| Chỉ tạo publisher nhưng chưa subscribe | Không | Không | Không |

Bảng dùng mô hình một subscription đơn giản. **Vị trí operator rất quan trọng**: một pipeline có thể hoàn tất bình thường ở downstream nhờ `take` hoặc `onErrorResume` trong khi đoạn upstream kết thúc vì cancel hoặc error. Bạn phải trả lời câu hỏi: “Tôi gắn hook ở đoạn nào?” trước khi diễn giải log.

## 5. Trường hợp dễ nhầm: take(n) và cancellation

`take(n)` có thể hoàn tất **publisher kết quả** sau `n` phần tử, nhưng để không nhận thêm dữ liệu từ nguồn, nó thường **hủy upstream**. Vì vậy, hai hook ở hai phía của `take` có thể quan sát hai kết cục khác nhau.

```java
Flux<Integer> observed = Flux.range(1, 10)
        .doOnCancel(() ->
                System.out.println("UPSTREAM cancelled"))
        .doOnTerminate(() ->
                System.out.println("UPSTREAM terminated"))
        .doFinally(signal ->
                System.out.println("UPSTREAM finally: " + signal))
        .take(2)
        .doOnTerminate(() ->
                System.out.println("DOWNSTREAM terminated"))
        .doFinally(signal ->
                System.out.println("DOWNSTREAM finally: " + signal));
```

Đây là **đoạn minh họa**, cần import `Flux` và có subscription để kích hoạt. Với nguồn cold `range` không cạn sau hai phần tử:

- Phía **trước `take(2)`**, nguồn nhận cancellation: `doOnCancel` và `doFinally(CANCEL)` có thể được ghi nhận. `doOnTerminate` upstream không chạy chỉ vì bị hủy.
- Phía **sau `take(2)`**, kết quả phát hai phần tử và **hoàn tất thành công**: `doOnTerminate` downstream và `doFinally(ON_COMPLETE)` tương ứng chạy.
- Không mâu thuẫn: **cùng một thao tác** có thể là “cancel upstream” nhưng là “complete downstream”.

Không lấy một `doFinally(CANCEL)` từ upstream để khẳng định HTTP request thất bại. Cancellation đôi khi là **cơ chế tối ưu bình thường** của operator như `take`, `next`, `timeout` hoặc chiến lược chỉ lấy một kết quả. Cần phân biệt hủy do client, hủy do toán tử giới hạn phần tử và hủy do lỗi ở nhánh khác bằng ngữ cảnh và tracing phù hợp.

### 5.1. Mono từ first/next cũng có thể cancel nguồn

Nếu `Flux` có nhiều phần tử và bạn gọi `next()`, kết quả là `Mono` lấy phần tử đầu tiên. Khi đã có một giá trị, toán tử có thể hủy subscription upstream vì không cần phần còn lại. Tương tự với `take(1)`. `doOnCancel` upstream có thể chạy dù subscriber bên ngoài nhận được kết quả hoàn toàn bình thường.

### 5.2. doFinally không chỉ có một “câu trả lời” cho cả pipeline

```java
source
    .doFinally(signal -> log("source-side", signal))
    .take(1)
    .doFinally(signal -> log("response-side", signal));
```

Đây là **đoạn minh họa**, cần có `source` và hàm `log` do ứng dụng định nghĩa. Hai callback nói về **hai subscription segment** khác nhau. Với nguồn còn nhiều giá trị, phía source có thể thấy `CANCEL`, phía response thấy `ON_COMPLETE`. Hãy đặt hook sát thành phần bạn muốn đo.

## 6. Trường hợp dễ nhầm: lỗi được phục hồi bằng onErrorResume

`onErrorResume` có thể chặn lỗi upstream và chuyển sang publisher dự phòng. Từ điểm nhìn trước recovery, nguồn đã lỗi; từ điểm nhìn sau recovery, toàn bộ output có thể hoàn tất thành công.

```java
Mono<String> result = remoteCall()
        .doOnTerminate(() -> metrics.rawTerminated())
        .doFinally(signal -> metrics.rawFinally(signal))
        .onErrorResume(error -> Mono.just("fallback"))
        .doOnTerminate(() -> metrics.responseTerminated())
        .doFinally(signal -> metrics.responseFinally(signal));
```

Đây là **đoạn minh họa**, `remoteCall()` trả `Mono<String>`, `metrics` do ứng dụng định nghĩa. Nếu `remoteCall` lỗi và fallback thành công:

1. `doOnTerminate` trước recovery chạy vì upstream lỗi.
2. `doFinally` ở đoạn nguồn nhận `ON_ERROR`.
3. `onErrorResume` thay lỗi bằng `Mono.just("fallback")`.
4. `doOnTerminate` phía downstream chạy vì publisher kết quả thành công.
5. `doFinally` phía downstream nhận `ON_COMPLETE`.

**Thứ tự log chính xác giữa các callback** vẫn phụ thuộc vị trí và tính đồng bộ, nhưng cách phân loại ở từng vị trí là điểm cần nhớ. Nếu dashboard muốn đo **số lỗi gốc**, đặt `doOnError` trước recovery. Nếu muốn đo **tỷ lệ response cuối thành công**, đặt `doFinally`/`doOnTerminate` sau recovery. Tránh tính hai tập này như hai mẫu đo cùng nghĩa.

### 6.1. timeout có thể tạo error downstream và cancel upstream

`timeout(Duration.ofSeconds(...))` khi quá hạn có thể hủy subscription đang chờ của nguồn và phát một `TimeoutException` downstream. Một `doFinally` **trước** `timeout` có thể thấy `CANCEL`; một `doFinally` **sau** `timeout` có thể thấy `ON_ERROR`, trừ khi có recovery khác đổi kết cục. Đây là lý do không diễn giải tất cả `CANCEL` là người dùng ngắt kết nối.

### 6.2. retry làm tăng số subscription và số lần chạy hook

`retry(2)` có thể đăng ký lại upstream khi lỗi, tối đa hai lần thử lại ngoài lần đầu. Hook **trước** `retry` nằm trong mỗi lượt subscription, có thể chạy nhiều lần, trong khi hook **sau** `retry` quan sát kết cục cuối của toàn bộ pipeline ở vị trí đó. Khi thống kê lỗi, hãy phân biệt `attempts`, `retries` và `requests`; nếu không, số lượng sự kiện sẽ dễ bị đếm sai.

## 7. doFinally và việc giải phóng tài nguyên

`doFinally` rất tiện để giải phóng tài nguyên do một subscriber/bộ đo lường sở hữu; nhưng đây là một **callback side effect**, không phải transaction manager hay resource scope tự động.

Ví dụ đếm số subscription đang hoạt động:

```java
AtomicInteger active = new AtomicInteger();

Flux<String> tracked = source
        .doOnSubscribe(subscription ->
                active.incrementAndGet())
        .doFinally(signal ->
                active.decrementAndGet());
```

Đây là **đoạn minh họa**, cần `java.util.concurrent.atomic.AtomicInteger`, `Flux<String> source` do ứng dụng định nghĩa. Mỗi subscription vào đoạn tracked tăng một lần, rồi giảm một lần khi kết thúc. Với logic thống kê production, cần xem hook có nằm đúng chỗ, nguồn có retry/share hay không, metric có thể được quan sát muộn đến đâu và callback có ném lỗi không. Nếu `doFinally` chưa chạy kịp vào thời điểm một test đọc biến `active`, kết quả tạm thời có thể gây nhầm.

### 7.1. Chọn hook nào cho cleanup?

- **Chỉ khi cancel:** `doOnCancel` phù hợp với log/thống kê hoặc giải phóng thứ riêng của nhánh hủy.
- **Chỉ complete/error:** `doOnTerminate` phù hợp khi không cần quan tâm cancel, nhưng **không đủ** để cleanup tài nguyên phải đóng trong mọi trường hợp.
- **Mọi kết cục:** `doFinally` phù hợp để chốt metric, giải phóng một handle do callback quản lý hoặc quan sát `SignalType`.
- **Nguồn thực sự mở tài nguyên:** thường nên dùng `Flux.using`/`Mono.using` (resource sync) hoặc `usingWhen` (resource cleanup reactive/async) để đảm bảo scope và thứ tự cleanup gắn với publisher.

**Không đặt thao tác cleanup blocking lâu trong `doFinally`** chạy trên đường tín hiệu của event-loop WebFlux. Callback có thể chạy trên thread I/O và làm chậm toàn bộ ứng dụng. Nếu cần đóng connection, transaction hoặc session bằng tác vụ async, hãy dùng abstraction thích hợp thay vì chỉ gọi `subscribe()` lồng bên trong `doFinally`.

### 7.2. using với tài nguyên đóng đồng bộ

```java
Flux<String> lines = Flux.using(
        () -> openReader(),                  // tạo tài nguyên mỗi subscription
        reader -> readLinesReactive(reader),  // trả Flux<String>
        reader -> closeReader(reader));       // đóng tài nguyên theo scope
```

Đây là **đoạn minh họa về cấu trúc**: `openReader`, `readLinesReactive` và `closeReader` do ứng dụng định nghĩa; nếu `readLinesReactive` trực tiếp đọc file blocking thì không được tự xem nó là nonblocking chỉ vì trả `Flux`. `using` có các overload về eager cleanup; cần đọc API và chọn phù hợp nếu việc đóng tài nguyên trước/sau phát terminal signal là quan trọng.

Điểm chính: publisher **sở hữu resource** và có trách nhiệm đóng nó theo scope của từng subscription, thay vì dựa vào việc một subscriber bên ngoài nhớ gọi đúng hook.

### 7.3. usingWhen với cleanup bất đồng bộ

```java
Flux<Result> queryResults = Flux.usingWhen(
        pool.acquire(),                     // Mono<Resource>
        resource -> query(resource),        // Flux<Result>
        resource -> resource.release(),     // Publisher<?> khi complete
        (resource, error) -> resource.release(), // cleanup khi error
        resource -> resource.release());    // cleanup khi cancel
```

Đây là **đoạn minh họa**, cần định nghĩa `Result`, `pool`, `Resource`, `query` và `release()` trả publisher reactive. API có overload truyền riêng cleanup cho complete/error/cancel. Chính sách thực tế có thể là commit khi thành công, rollback khi lỗi, rollback khi hủy; không mặc định cả ba nhánh cùng “release” nếu transaction đòi hỏi xử lý khác nhau.

`usingWhen` có quy tắc riêng về việc đợi publisher cleanup hoàn tất, cũng như cách truyền lỗi cleanup; hãy dùng nó khi **thời điểm cleanup và tính bất đồng bộ** có ý nghĩa đối với kết quả, thay vì mở một subscription độc lập trong `doFinally`.

### 7.4. Tài nguyên bị loại bỏ do filter/prefetch: doOnDiscard

Khi operator `filter` loại một object, hoặc buffer/prefetch bị bỏ vì cancel/error, một số tài nguyên như pooled buffer có thể phải được giải phóng dù chúng **chưa từng tới subscriber**. `doFinally` cho biết subscription kết thúc, nhưng không tự có danh sách mọi item đã bị discard.

```java
Flux<Buffer> values = source
        .filter(this::shouldKeep)
        .doOnDiscard(Buffer.class, Buffer::release);
```

Đây là **đoạn minh họa**, giả sử `Buffer`, `source` và `shouldKeep` do ứng dụng định nghĩa; chỉ dùng nếu Buffer đúng là kiểu resource cần release và operator hỗ trợ discard. `doOnDiscard` không được tất cả operator bảo đảm hỗ trợ; callback phải an toàn khi được gọi lặp hoặc với phần tử cần dọn và không được giải phóng một buffer vẫn còn thuộc sở hữu của downstream.

## 8. Trong Spring WebFlux, client ngắt kết nối thì sao?

Một endpoint streaming có thể tạo `Flux` kéo dài:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(index -> "event-" + index)
            .doOnCancel(() -> logger.info("stream cancelled"))
            .doOnTerminate(() -> logger.info("stream terminated"))
            .doFinally(signal ->
                    logger.info("stream finally: {}", signal));
}
```

Đây là **đoạn minh họa trong `@RestController`**, cần import `Flux`, `Duration`, `GetMapping`, `MediaType` và có logger. WebFlux cùng HTTP runtime thường sở hữu subscriber của response. Khi client kết thúc stream bằng đóng kết nối, cancellation **có thể** lan ngược đến `Flux` và kích hoạt `doOnCancel`/`doFinally(CANCEL)`. Tuy nhiên:

- Việc phát hiện disconnect phụ thuộc reactive HTTP server, bộ đệm, transport và thời điểm ghi dữ liệu. Không cam kết hook sẽ chạy ngay tại mili-giây client đóng tab.
- Nếu stream tự kết thúc bình thường, `doOnTerminate` và `doFinally(ON_COMPLETE)` có thể chạy, không phải cancel.
- Nếu nguồn lỗi, `doOnTerminate` và `doFinally(ON_ERROR)` chạy, nhưng HTTP response có thể đã gửi header/body nên không thể tùy tiện đổi status thành 500.
- Một `CANCEL` **không chứng minh** chỉ riêng client đã ngắt. Operator như `take`, `next` hay `timeout` cũng có thể hủy upstream có chủ đích.
- Không gọi `.subscribe()` trong handler để “bật” callback. Việc đó tạo subscription riêng tách khỏi response, khiến cancel/error của HTTP không tự đi theo nhánh mới.

Nếu cần xử lý khi HTTP request kết thúc để ghi metric, có thể gắn `doFinally` ở đoạn publisher trả về sau các bước xử lý chính. Nếu cần cleanup tài nguyên mở trong service, hãy giữ cơ chế đóng tài nguyên **tại chính nguồn/service**, không phụ thuộc toàn bộ vào việc controller có gắn hook hay không.

### 8.1. doFinally không biến side effect thành tác vụ nền đáng tin cậy

Nếu trong `doFinally` bạn gọi:

```java
.doFinally(signal -> auditService.writeEvent(signal).subscribe())
```

Đây là **đoạn minh họa về cách làm không nên dùng** trong pipeline nghiệp vụ. Nó mở một subscription tách rời, không bảo đảm đã lưu audit khi response kết thúc, không tự quản lý retry hay shutdown, và có thể mất dữ liệu nếu ứng dụng dừng. Với audit bắt buộc trước khi xác nhận thành công, compose publisher audit trong luồng kết quả. Với audit nền thật sự, dùng queue/outbox hoặc consumer có vòng đời, lỗi và retry được quản lý.

### 8.2. Không được chặn event-loop khi cleanup

`doOnCancel`/`doOnTerminate`/`doFinally` có thể được gọi trên thread phát tín hiệu hoặc thread gọi cancel. Vì vậy, đừng viết `Thread.sleep`, JDBC đồng bộ hay `block()` trong callback của WebFlux. Dùng API resource reactive hoặc một chiến lược scheduler được thiết kế phù hợp nếu phải xử lý tác vụ blocking. **Không mặc định `doFinally` chạy trên thread nền.**

## 9. Thứ tự callback và khả năng nhìn thấy kết quả

Các hook không phải là “try/finally Java được gọi tại cùng một stack frame” trong mọi tình huống. Subscription có thể phân tán qua nhiều toán tử và scheduler:

1. `doOnCancel` chạy **trước** khi chuyển `cancel` lên upstream ở vị trí operator ấy.
2. `doOnTerminate` chạy **trước** khi chuyển tiếp `onComplete`/`onError` xuống downstream; với `Mono` có giá trị, nó có thể chạy trước `onNext`.
3. `doFinally` chạy **sau** khi đã truyền tín hiệu kết thúc. Với nhiều `doFinally` liên tiếp, callback thực thi theo thứ tự ngược với khai báo.
4. `doAfterTerminate` (nếu dùng) chỉ quan sát complete/error **sau** khi terminal signal đã truyền xuống downstream; nó vẫn không xử lý cancel như `doFinally`.
5. `doOnSuccess` là hook của `Mono` cho thành công: nhận giá trị `T` khi Mono hoàn tất với dữ liệu, nhận `null` **trong callback** nếu Mono hoàn tất rỗng. Điều này **không có nghĩa** Reactor phát `null` qua `onNext`.

Nếu test một bộ đếm bên trong `doFinally`, đừng mặc định kiểm tra ngay sau `block()` sẽ luôn nhìn thấy increment/decrement. Do `doFinally` chạy sau terminal được truyền xuống, test với publisher bất đồng bộ có thể cần một `CountDownLatch`, `StepVerifier` kết hợp cơ chế chờ, hoặc tín hiệu riêng cho cleanup. Không nên “chữa” bằng `Thread.sleep` ngẫu nhiên.

### 9.1. Một subscription không phải toàn bộ vòng đời ứng dụng

Với `retry`, mỗi lượt thử có thể tạo subscription mới cho nguồn và callback ở đó chạy nhiều lần. Với `share`, `publish`, `cache` hoặc nguồn hot, cách các subscriber dùng chung upstream có thể thay đổi số lượt gọi callback tại mỗi vị trí. Luôn đo đúng scope: một subscriber, một connection, một request hay một nguồn dùng chung. Nếu muốn đếm request HTTP, không đơn giản suy ra từ số lần `doFinally` của mọi publisher lồng nhau.

## 10. Kiểm thử hoàn tất, lỗi và hủy

Thư viện `reactor-test` có `StepVerifier`, hữu ích để xác nhận kết cục. Thêm dependency phiên bản cùng nhánh với `reactor-core`:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <version>3.8.8</version>
    <scope>test</scope>
</dependency>
```

Đây là các **đoạn mã nằm trong phương thức test**, không phải chương trình Java độc lập; cần import `StepVerifier`, `Flux` và `Mono`.

### 10.1. Xác nhận complete

```java
StepVerifier.create(
        Flux.just(1, 2).doOnTerminate(() -> record("terminated")))
    .expectNext(1, 2)
    .verifyComplete();
```

Cần định nghĩa `record` trong test. Khi nguồn hoàn tất, callback `doOnTerminate` chạy. `verifyComplete()` xác nhận tín hiệu terminal đúng là `onComplete`.

### 10.2. Xác nhận error

```java
StepVerifier.create(
        Flux.<Integer>error(new IllegalStateException("bad"))
            .doOnTerminate(() -> record("terminated")))
    .expectError(IllegalStateException.class)
    .verify();
```

`doOnTerminate` vẫn chạy dù nguồn không thành công, vì nó quan sát cả complete/error. Nếu cần kiểm tra chi tiết exception, dùng `doOnError` hoặc assertion riêng.

### 10.3. Xác nhận cancel

```java
StepVerifier.create(
        Flux.range(1, 10)
            .doOnCancel(() -> record("cancelled"))
            .doFinally(signal -> record(signal.name())),
        0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify();
```

Kịch bản tạo subscriber với **initial request = 0**, sau đó xin 2 phần tử và cancel. Vì không yêu cầu đủ 10 phần tử, đoạn nguồn bị hủy; `doOnCancel` quan sát cancellation, `doFinally` nhận `CANCEL`. Hàm `record` chỉ là phần bổ sung do test tự định nghĩa. Nếu muốn assert chính xác **thời điểm** record được lưu, phải đồng bộ với callback cuối; `verify()` kiểm tra subscription đã thực hiện kịch bản, không thay thế thiết kế đồng bộ khi kiểm tra tài nguyên async.

Trong Spring WebFlux, có thể dùng `WebTestClient` để kiểm thử status/body của endpoint hoàn tất/lỗi; đối với client ngắt SSE thật, cần integration test có khả năng kiểm soát subscription/connection, không chỉ unit test với `Flux.range`.

## 11. Lỗi thường gặp và cách sửa

| Sai lầm | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Dùng `doOnTerminate` để “bắt mọi kiểu kết thúc” | Bỏ sót cancel, dễ rò rỉ tài nguyên | Dùng `doFinally` nếu muốn bao gồm cancel. |
| Dùng `doOnCancel` để bắt lỗi service | Callback không chạy khi upstream phát `onError` | Dùng `doOnError`, `doOnTerminate` hoặc `doFinally` đúng mục tiêu. |
| Hiểu `cancel` là `onComplete` | Ghi metric “thành công” sai; cleanup sai nhánh | Phân biệt `CANCEL` và `ON_COMPLETE`. |
| Xem `doFinally(CANCEL)` upstream là chắc chắn client disconnect | `take`/`next`/`timeout` có thể hủy upstream hợp lệ | Gắn hook gần HTTP boundary và dùng tracing/context. |
| Đặt hook sau `onErrorResume` rồi mong thấy lỗi upstream | Recovery có thể biến output thành complete | Gắn `doOnError`/`doFinally` trước recovery để quan sát lỗi nguồn. |
| Dùng `doFinally` rồi ngay sau `block()` đọc counter và giả định đã cập nhật | Callback có thể đến sau terminal/downstream unblock | Đồng bộ hóa việc đợi callback khi kiểm thử. |
| Nghĩ `Mono.doOnTerminate` giống thứ tự của `Flux.doOnTerminate` với `onNext` | Thứ tự log bất ngờ | Ghi nhớ Mono có giá trị kích hoạt doOnTerminate trước onNext. |
| Gọi `subscribe()` bên trong `doFinally` để ghi audit bắt buộc | Tạo nhánh không được quản lý, không bảo đảm audit hoàn tất | Compose publisher hoặc dùng outbox/consumer riêng. |
| Gọi JDBC/blocking I/O trong callback doFinally của WebFlux | Chặn thread I/O và giảm throughput | Sử dụng cleanup reactive/async theo resource scope. |
| Gắn doFinally nhiều nơi rồi coi tất cả callback là một request | Một request có thể có nhiều subscription và inner publisher | Đo scope chính xác, tránh đếm trùng. |
| Dùng doFinally để dọn từng buffer bị filter loại | Callback không biết mọi item bị discard | Sử dụng doOnDiscard và cơ chế sở hữu buffer phù hợp. |
| Dùng doOnTerminate như cơ chế rollback transaction | Bỏ sót cancel và không quản lý rollback thực sự | Dùng transaction/resource API có cleanup cho complete/error/cancel. |
| Callback ném exception và giả định lỗi được “xử lý đẹp” | Có thể làm rối đường xử lý terminal hoặc tạo lỗi bổ sung | Giữ hook ngắn, đáng tin, không ném; ghi log lỗi side effect phù hợp. |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `Flux.just(1, 2).doOnCancel(...).doOnTerminate(...).doFinally(...)` được subscribe và nhận đủ hai phần tử. Hook nào chạy?  
**Đáp án:** `doOnTerminate` và `doFinally(ON_COMPLETE)`; `doOnCancel` không chạy chỉ vì hoàn tất bình thường.

**Câu 2.** `Flux.error(new RuntimeException("boom"))` phát gì vào `doFinally`? `doOnTerminate` có chạy không?  
**Đáp án:** `doFinally` nhận `SignalType.ON_ERROR`, `doOnTerminate` có chạy vì nguồn kết thúc bằng lỗi. `doOnCancel` không chạy chỉ vì có lỗi.

**Câu 3.** `Flux.never()` bị subscriber `cancel()`. Hook nào có thể chạy?  
**Đáp án:** `doOnCancel` và `doFinally(CANCEL)` ở vị trí cancel đi qua; `doOnTerminate` không chạy vì nguồn không complete/error.

**Câu 4.** Một `Flux.range(1, 10).take(2)` có `doFinally` trước và sau `take`. Hai hook có nhất thiết nhận cùng loại không?  
**Đáp án:** Không. Phía upstream có thể nhận `CANCEL` sau khi hai phần tử đã đủ, còn phía downstream nhận `ON_COMPLETE` vì `take(2)` kết thúc output thành công.

**Câu 5.** Vì sao `Mono.just("ok").doOnTerminate(...).doOnNext(...)` có thể ghi log terminate trước log next?  
**Đáp án:** Với `Mono`, việc phát một giá trị đã hàm ý completion. `Mono.doOnTerminate` chạy trước khi value được đẩy xuống downstream, khác với `Flux` thông thường.

**Câu 6.** Một lỗi được `onErrorResume` đổi thành `Mono.just("fallback")`. `doFinally` đặt trước và sau recovery sẽ quan sát gì?  
**Đáp án:** Hook trước recovery quan sát `ON_ERROR` của nguồn; hook sau recovery quan sát `ON_COMPLETE` nếu publisher fallback thành công.

**Câu 7.** Dùng `doFinally` để đóng resource bằng một `Mono<Void> release()` rồi tự gọi `subscribe()` trong callback có ổn cho cleanup bắt buộc không?  
**Đáp án:** Không nên. Đó là một subscription tách rời, không bảo đảm cleanup hoàn tất trước khi kết quả chính được quan sát; nên dùng `usingWhen` hoặc scope quản lý tài nguyên reactive thích hợp.

**Câu 8.** Vì sao không được dựa vào việc `doOnCancel` chạy ngay khi người dùng đóng trình duyệt?  
**Đáp án:** HTTP server có thể phát hiện disconnect muộn, dữ liệu có thể nằm trong bộ đệm và cancellation không phải thông báo đồng bộ trên mọi tầng. Cần đo bằng integration test và quan sát transport thực tế.

## Ghi nhớ

- **`doOnCancel`:** quan sát **hủy**, callback chạy trước khi chuyển cancellation lên upstream tại vị trí hook.
- **`doOnTerminate`:** quan sát **hoàn tất hoặc lỗi**, không bao gồm hủy; callback chạy trước khi terminal signal được chuyển xuống downstream. Với `Mono` có giá trị, hook có thể chạy trước `onNext`.
- **`doFinally`:** quan sát **cả ba kết cục** và nhận `SignalType.ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`; chạy sau khi tín hiệu được chuyển tiếp, phù hợp để phân loại kết cục/cleanup gọn.
- **Đặt hook đúng chỗ.** `take`, `timeout`, `retry` và `onErrorResume` có thể khiến upstream và downstream nhìn thấy loại kết thúc khác nhau.
- Với tài nguyên thực sự, ưu tiên `using`/`usingWhen` và xử lý discard theo API; đừng biến `doFinally` thành nơi thực hiện blocking I/O hay mở một subscription nền không được quản lý.
- Trong Spring WebFlux controller, **trả publisher** để framework xử lý subscription và cancellation HTTP; không tự `subscribe` để kích hoạt pipeline.

### Tài liệu tham khảo

1. [Project Reactor – Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `doOnCancel`, `doOnTerminate`, `doFinally`, `doAfterTerminate` và `doOnDiscard`.
2. [Project Reactor – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): sự khác nhau của `Mono.doOnTerminate` và `Mono.doOnSuccess`.
3. [Project Reactor – Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `doFinally`, `onErrorResume` và mô hình terminal signal.
4. [Project Reactor – Using a Resource](https://projectreactor.io/docs/core/release/reference/advancedFeatures/using.html): các cách quản lý tài nguyên reactive, `using` và `usingWhen`.
5. [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm): hợp đồng `Publisher`/`Subscriber`/`Subscription`.
6. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): xử lý response HTTP reactive, streaming và cancellation.
