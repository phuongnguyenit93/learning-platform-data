# doOnError chỉ quan sát và không phục hồi chuỗi

**Ngữ cảnh:** Spring Framework Reactive → **Lỗi và thử lại**.

Trong Project Reactor, `doOnError(...)` là một **toán tử quan sát (side-effect operator)**: khi luồng nhận tín hiệu lỗi `onError`, callback được gọi để ghi log, tăng metric, bổ sung chẩn đoán hoặc thực hiện hành động quan sát thích hợp. Sau đó **tín hiệu lỗi vẫn được truyền xuống downstream**. `doOnError` **không** tự trả giá trị mặc định, không biến lỗi thành hoàn tất thành công, không đăng ký nguồn dự phòng và không khởi động lại pipeline.

Đây là điểm dễ nhầm khi mới học Reactor:

```java
Mono<String> result = callRemoteService()
        .doOnError(error -> log.error("Remote call failed", error));
```

Đoạn này **ghi log khi lỗi xảy ra, nhưng `result` vẫn kết thúc bằng lỗi**. Nếu không có cơ chế xử lý tiếp theo, subscriber nhận `onError`; trong WebFlux, lỗi có thể đi tới cơ chế xử lý exception của framework. Muốn **phục hồi**, cần các operator có ngữ nghĩa khác như `onErrorReturn`, `onErrorResume` hoặc `onErrorComplete` và phải dùng đúng hợp đồng nghiệp vụ.

Bài học tập trung vào **ranh giới quan sát và phục hồi**, vị trí operator, tương tác với retry, cách ghi log trong Spring WebFlux và các sai lầm khiến lỗi bị che giấu hoặc bị ghi nhiều lần.

## 1. Lỗi là tín hiệu kết thúc của một subscription

Reactive Streams có ba loại tín hiệu dữ liệu/kết thúc quan trọng:

- `onNext(value)`: phát dữ liệu, có thể nhiều lần với `Flux` hoặc tối đa một lần với `Mono`.
- `onComplete()`: kết thúc thành công.
- `onError(Throwable)`: kết thúc thất bại.

Một subscription chỉ có **một terminal signal**, hoặc `onComplete` hoặc `onError`. Sau `onError`, nguồn đó **không tiếp tục phát phần tử kế tiếp**. Nếu muốn xử lý tiếp sau lỗi, cần một publisher dự phòng hoặc subscription mới theo cơ chế recovery/retry.

Mô hình:

```text
Publisher (ví dụ Flux.just(1, 2, 3))
         |
         v
      map(v)   ---- lỗi khi v = 2 ----> onError(IllegalStateException)
         |                                  |
         |                              doOnError
         |                         (log / metric / trace)
         |                                  |
         |                                  v
         |                           downstream.onError
         |
   onNext(1) đã gửi
   phần tử 3 không chạy trong cùng subscription
```

**Không nên hiểu `doOnError` là Java `catch` tự nuốt lỗi.** Nó tương đương về ý tưởng với “nhìn thấy exception, ghi log, rồi để exception tiếp tục đi”, dù triển khai là cơ chế tín hiệu reactive và không phải một lệnh `throw` thủ công trong callback ứng dụng.

## 2. Hợp đồng chính xác của doOnError

Với `Flux<T>` và `Mono<T>`, toán tử `doOnError` đăng ký một callback nhận `Throwable`. Khi upstream phát lỗi:

1. Reactor gọi callback đã cấu hình.
2. Callback có thể ghi log/metric hoặc quan sát lỗi.
3. Nếu callback hoàn thành bình thường, lỗi gốc được truyền tiếp tới subscriber/operator phía sau.
4. `doOnError` không thay đổi kiểu `T`, không thêm phần tử và không đổi `onError` thành `onComplete`.

```java
Flux<Integer> stream = Flux.just(1, 2, 3)
        .map(n -> {
            if (n == 2) {
                throw new IllegalStateException("bad value: 2");
            }
            return n * 10;
        })
        .doOnError(error ->
                System.out.println("Observed: " + error.getMessage()));
```

Đây là **snippet** trong class đã import `Flux`. Khi subscriber yêu cầu đủ dữ liệu, nguồn gửi 10; sau đó lỗi ở phần tử 2, callback quan sát lỗi và downstream nhận `onError`. Phần tử 3 không được map trong subscription đó.

**Ba overload hay dùng:**

```java
// Quan sát mọi lỗi:
publisher.doOnError(error -> log.error("Failed", error));

// Chỉ quan sát lỗi thuộc một kiểu cụ thể:
publisher.doOnError(TimeoutException.class,
        error -> log.warn("Timed out", error));

// Chỉ quan sát lỗi khớp điều kiện:
publisher.doOnError(
        error -> error instanceof IllegalStateException,
        error -> log.warn("Invalid state", error));
```

Đây là những **đoạn minh họa**, cần `publisher`, `log` và import `TimeoutException`. Overload theo kiểu hoặc predicate chỉ quyết định **có gọi callback hay không**, **không lọc hoặc phục hồi tín hiệu lỗi**. Một lỗi không khớp vẫn đi xuống downstream như bình thường.

### Điều gì xảy ra nếu callback tự ném lỗi?

`doOnError` phù hợp với callback quan sát **nhanh, ổn định, ít khả năng thất bại**. Nếu code ghi log/metric **tự ném exception**, nó không còn đơn thuần là một quan sát vô hại: Reactor phải xử lý lỗi phát sinh từ chính operator, và downstream có thể nhận lỗi khác hoặc thông tin lỗi gốc dưới dạng suppressed/cause tùy tình huống.

Bởi vậy, tránh đặt I/O blocking, logic nghiệp vụ quan trọng, chuyển đổi exception hoặc những hành động có thể thất bại trong callback. Nếu cần đổi lỗi, dùng `onErrorMap`; nếu cần phục hồi, dùng `onErrorResume`. Nếu cần đảm bảo một side effect xảy ra chính xác một lần, không dựa đơn thuần vào callback `doOnError` dưới retry/resubscription.

## 3. Ví dụ ngắn: đã ghi log nhưng lỗi vẫn xảy ra

```java
Mono<String> result = Mono.<String>error(
        new IllegalStateException("DB unavailable"))
    .doOnError(error ->
        System.out.println("LOG: " + error.getMessage()));

result.subscribe(
    value -> System.out.println("value=" + value),
    error -> System.out.println("subscriber error=" + error.getMessage()),
    () -> System.out.println("complete")
);
```

Kết quả:

```text
LOG: DB unavailable
subscriber error=DB unavailable
```

**Vì sao không có `complete`?** Nguồn phát `onError`, là terminal signal thất bại. `doOnError` gọi observer trước khi chuyển tiếp lỗi, nên callback đăng ký `error` ở subscriber vẫn chạy. `onComplete` không chạy sau lỗi.

**Vì sao không có `value`?** Nguồn `Mono.error(...)` không phát dữ liệu. `doOnError` không tạo ra giá trị thay thế.

## 4. Quan sát khác với xử lý lỗi

Các toán tử Reactor thường gặp:

| Operator | Vai trò | Downstream sẽ thấy gì? |
|---|---|---|
| **`doOnError(callback)`** | **Quan sát** lỗi | Vẫn nhận `onError` nếu không có bước xử lý khác |
| `onErrorReturn(fallback)` | Phục hồi bằng một giá trị cố định | Nhận giá trị fallback rồi `onComplete` nếu khớp và không có lỗi khác |
| `onErrorResume(error -> publisher)` | Phục hồi bằng publisher dự phòng | Nhận tín hiệu của publisher dự phòng |
| `onErrorComplete()` | Chuyển lỗi thành hoàn tất bình thường | Nhận `onComplete`, không nhận `onError` tương ứng |
| `onErrorMap(error -> newError)` | **Biến đổi loại lỗi** | Vẫn nhận `onError`, nhưng với lỗi đã được ánh xạ |
| `retry(n)` / `retryWhen(...)` | **Đăng ký lại** nguồn khi lỗi phù hợp | Có thể thành công ở lần thử sau, hoặc lỗi sau khi hết lượt |
| `doFinally(signal -> ...)` | Quan sát kết thúc/hủy | Không tự thay đổi outcome, nhận loại terminal/cancel |
| `doOnNext(value -> ...)` | Quan sát phần tử | Không tự thay đổi item |

### 4.1. `onErrorReturn`: có giá trị thay thế

```java
Mono<String> safe = Mono.<String>error(
        new IllegalStateException("temporary failure"))
    .doOnError(error -> log.warn("Primary failed", error))
    .onErrorReturn("fallback");
```

Giả sử `log` là logger đã khai báo. Khi subscribe, `doOnError` ghi log lỗi từ nguồn chính; `onErrorReturn` chặn lỗi khớp và phát `"fallback"` rồi complete. **Chính `onErrorReturn` phục hồi**, không phải `doOnError`.

Lựa chọn này phù hợp khi giá trị mặc định là **chấp nhận được về nghiệp vụ**. Không nên biến lỗi thanh toán, sai dữ liệu hoặc lỗi bảo mật thành một giá trị giả.

### 4.2. `onErrorResume`: chuyển sang nguồn khác

```java
Mono<Product> product = primaryRepository.findById(id)
        .doOnError(error -> log.warn(
                "Primary repository failed for id={}", id, error))
        .onErrorResume(TransientDataAccessException.class,
                error -> backupRepository.findById(id));
```

Đây là **snippet**, cần `Product`, hai repository, `id`, logger và class exception. Chỉ những lỗi khớp `TransientDataAccessException` mới đi vào fallback. Đường dự phòng có thể thành công, trả empty hoặc lại lỗi.

**Không được hiểu `onErrorResume` là chạy tiếp phần còn lại của nguồn bị lỗi.** Nó **thay thế nguồn đã thất bại bằng một publisher khác** tại vị trí operator; những phần tử chưa xử lý của nguồn cũ không tự được phát tiếp.

### 4.3. `onErrorMap`: đổi cách biểu diễn lỗi nhưng không phục hồi

```java
Mono<Product> product = repository.findById(id)
        .onErrorMap(DataAccessException.class,
                error -> new CatalogUnavailableException(
                        "Catalog read failed", error))
        .doOnError(error ->
                log.error("Catalog lookup failed", error));
```

Đây là snippet: các kiểu `Product`, `CatalogUnavailableException`, `DataAccessException` và repository cần có trong project. `onErrorMap` đổi loại exception sang một lỗi có ý nghĩa ở tầng domain; `doOnError` phía sau quan sát **lỗi đã ánh xạ**. Luồng vẫn thất bại nếu không có recovery tiếp theo.

### 4.4. `onErrorComplete`: kết thúc bình thường

```java
Flux<String> events = upstreamEvents()
        .doOnError(error -> log.warn("Feed failed", error))
        .onErrorComplete(FeedUnavailableException.class);
```

Đây là snippet. Nếu gặp lỗi `FeedUnavailableException`, downstream nhận `onComplete` thay vì `onError`. Các lỗi không khớp tiếp tục truyền xuống.

Cẩn trọng: chuyển một lỗi hạ tầng thành complete có thể làm người dùng hiểu nhầm dữ liệu đã tải **đủ** hoặc feed chủ động dừng thành công. Chỉ dùng khi chủ đích nghiệp vụ thật sự cho phép ngừng luồng và coi như thành công.

## 5. Vị trí doOnError quyết định lỗi nào được nhìn thấy

Các toán tử Reactor được đọc theo **hướng dữ liệu/tín hiệu đi từ upstream đến downstream** khi được subscribe. `doOnError` chỉ quan sát lỗi đi **qua vị trí đặt nó**.

### 5.1. Đặt trước recovery: nhìn thấy lỗi đã được phục hồi sau đó

```java
Mono<String> result = remoteCall()
        .doOnError(error -> log.warn("Remote failed", error))
        .onErrorReturn("cached");
```

Nếu `remoteCall()` lỗi, logger được gọi; `onErrorReturn` biến lỗi thành fallback. Subscriber cuối nhìn thấy `"cached"` và hoàn tất thành công.

### 5.2. Đặt sau recovery: thường không còn lỗi để quan sát

```java
Mono<String> result = remoteCall()
        .onErrorReturn("cached")
        .doOnError(error -> log.warn("This will not see recovered error", error));
```

Nếu `onErrorReturn` đã xử lý lỗi từ remote, callback phía sau **không chạy cho lỗi đó**. Tuy nhiên, nếu phía trước vẫn có lỗi **không được recovery khớp**, hoặc có bước khác phía trước observer phát lỗi, callback có thể vẫn chạy; đừng nói rằng `doOnError` sau một operator recovery “không bao giờ chạy” cho mọi trường hợp.

### 5.3. Một lỗi từ operator downstream không đi ngược lên observer upstream

```java
Flux<Integer> result = Flux.just(1, 2, 3)
        .doOnError(error -> log.error("Upstream error", error))
        .map(value -> {
            if (value == 2) throw new IllegalArgumentException("bad 2");
            return value;
        });
```

Đây là snippet. `doOnError` nằm **trước `map`**, còn lỗi được tạo **bên trong `map` phía sau**. Observer trước `map` không nằm trên đường tín hiệu lỗi đó; nếu muốn quan sát lỗi mapper, đặt `doOnError` **sau `map`**:

```java
Flux<Integer> result = Flux.just(1, 2, 3)
        .map(value -> {
            if (value == 2) throw new IllegalArgumentException("bad 2");
            return value;
        })
        .doOnError(error -> log.error("Map failed", error));
```

Vị trí operator là một phần của **thiết kế phạm vi quan sát**, không phải vấn đề trang trí.

## 6. Chương trình Java 17+ chạy độc lập để đối chiếu 3 tình huống và retry

Ví dụ sau sử dụng Reactor Core và Maven; không cần Spring Boot, mạng hoặc cơ sở dữ liệu. Nó minh họa chính xác thứ tự callback, hậu quả của lỗi và vị trí `doOnError` khi recovery/retry.

Cấu trúc:

```text
do-on-error-demo/
├── pom.xml
└── src/main/java/demo/DoOnErrorDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>do-on-error-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/DoOnErrorDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class DoOnErrorDemo {

    private static Flux<Integer> failingSource() {
        return Flux.just(1, 2, 3)
                .map(value -> {
                    if (value == 2) {
                        throw new IllegalStateException("boom at 2");
                    }
                    return value * 10;
                });
    }

    private static void consume(String name, Flux<Integer> flux) {
        flux.subscribe(
                value -> System.out.println(name + ":next=" + value),
                error -> System.out.println(name + ":error="
                        + error.getClass().getSimpleName()
                        + ":" + error.getMessage()),
                () -> System.out.println(name + ":complete")
        );
    }

    public static void main(String[] args) {
        System.out.println("1) observe only");
        consume("observe", failingSource()
                .doOnError(error -> System.out.println(
                        "seen=" + error.getMessage())));

        System.out.println("2) observe, then recover");
        consume("recover", failingSource()
                .doOnError(error -> System.out.println(
                        "logged=" + error.getMessage()))
                .onErrorReturn(-1));

        System.out.println("3) recover, then observe");
        consume("after", failingSource()
                .onErrorReturn(-1)
                .doOnError(error -> System.out.println("unexpected error")));

        System.out.println("4) observe each failed attempt");
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> unstable = Mono.defer(() -> {
            int number = attempts.incrementAndGet();
            System.out.println("attempt=" + number);
            if (number < 3) {
                return Mono.<String>error(
                        new IllegalStateException("temporary-" + number));
            }
            return Mono.just("READY");
        });

        String result = unstable
                .doOnError(error -> System.out.println(
                        "retry-observed=" + error.getMessage()))
                .retry(2)
                .block();

        System.out.println("result=" + result);
    }
}
```

Chạy từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.DoOnErrorDemo
```

**Standard output dự kiến** (không tính log riêng của Maven):

```text
1) observe only
observe:next=10
seen=boom at 2
observe:error=IllegalStateException:boom at 2
2) observe, then recover
recover:next=10
logged=boom at 2
recover:next=-1
recover:complete
3) recover, then observe
after:next=10
after:next=-1
after:complete
4) observe each failed attempt
attempt=1
retry-observed=temporary-1
attempt=2
retry-observed=temporary-2
attempt=3
result=READY
```

### Phân tích đầu ra

**Tình huống 1:** Nguồn gửi `10`, sau đó ném `IllegalStateException` khi xử lý số 2. `doOnError` in `seen=...` và chuyển tiếp tín hiệu lỗi. Subscriber báo `observe:error=...`; không có `observe:complete`, không xuất hiện giá trị 30.

**Tình huống 2:** `doOnError` vẫn in log. `onErrorReturn(-1)` nằm phía sau xử lý lỗi, phát `-1` như một giá trị thay thế rồi `onComplete`. Không phải xử lý số 3 từ nguồn cũ.

**Tình huống 3:** `onErrorReturn` phục hồi trước khi tín hiệu đi tới `doOnError`. Observer sau recovery không thấy lỗi gốc, vì vậy không có dòng `unexpected error`.

**Tình huống 4:** `Mono.defer` tạo lại source cho mỗi subscription, nên mỗi lần retry tăng `attempts`. `retry(2)` cho phép **tối đa hai lần đăng ký lại** sau lần đầu (tổng tối đa ba attempt). `doOnError` nằm **trước `retry`**, nhìn thấy và ghi lại hai attempt thất bại. Lần thứ ba phát `READY` thành công nên không có log lỗi nữa.

**Vì sao thứ tự dòng ở đây xác định?** Các nguồn được tạo bằng `just`/`defer`, các phép biến đổi và retry đồng bộ, không có `publishOn`, `subscribeOn`, timer hay I/O. `subscribe` trong ví dụ phục vụ học tập; trong controller WebFlux, thông thường **trả publisher** cho framework quản lý subscription. `block()` ở cuối `main` chỉ là cầu nối demo lấy kết quả để in ra, không phải hướng dẫn sử dụng `block()` trong event-loop WebFlux.

### Một lưu ý về retry và side effect

`retry` đăng ký lại nguồn. Vì vậy nó có thể **thực thi lại** HTTP call, query, phép biến đổi và các callback trên đoạn upstream. Nếu nguồn chứa side effect không idempotent (ghi đơn hàng, thu tiền...), retry có thể gây tác động lặp ngoài ý muốn. Mỗi lượt retry cần được xét cùng hợp đồng nghiệp vụ, không chỉ sự hiện diện của `doOnError`.

## 7. Ghi log ở đâu khi có retry?

Xét cùng một nguồn có thể lỗi nhiều lần:

```java
Mono<String> result = callRemote()
        .doOnError(error -> log.warn("Attempt failed", error))
        .retry(2);
```

Observer ở **trước retry** có thể ghi log cho **mỗi lần source thất bại**. Nếu cả ba attempt đều thất bại, sẽ có tới ba log cho một subscription downstream (lần đầu + hai retry).

Đổi vị trí:

```java
Mono<String> result = callRemote()
        .retry(2)
        .doOnError(error -> log.error("Request ultimately failed", error));
```

Observer ở **sau retry** chỉ nhận lỗi cuối cùng **nếu retry không phục hồi được**. Nếu lần thử sau thành công, callback `doOnError` phía sau `retry` không chạy.

Với hệ thống thật, thường cần **hai tầng thông tin**, nhưng phải tránh trùng quá mức:

- **Metric mức attempt**: theo dõi mỗi lần thất bại để biết dịch vụ ngoài đang không ổn định.
- **Log/metric kết quả cuối**: theo dõi một request nghiệp vụ thất bại thực sự sau retry.

Nếu muốn biết attempt và nguyên nhân một cách tường minh, cân nhắc `retryWhen(Retry.backoff(...))` với filter cho lỗi transient, giới hạn lượt, jitter và callback `doBeforeRetry`/`doAfterRetry` theo API của Reactor. Không retry vô hạn; ưu tiên chỉ retry lỗi tạm thời, thao tác idempotent hoặc có idempotency key.

```java
Mono<String> result = callRemote()
        .retryWhen(
            reactor.util.retry.Retry.backoff(
                    2, java.time.Duration.ofMillis(100))
                .filter(error -> error instanceof java.io.IOException)
                .doBeforeRetry(signal ->
                    log.warn("Retrying after failure", signal.failure())))
        .doOnError(error -> log.error("Final failure", error));
```

Đây là **snippet** trong project có `Mono`/Reactor, `callRemote` và logger. Nó chỉ retry `IOException` (tối đa hai retry). Nếu lỗi không khớp, downstream có thể nhận lỗi ngay; nếu hết retry, Reactor có thể bọc nguyên nhân vào exception thể hiện retry đã cạn, tùy API. Không dùng số 100 ms làm cấu hình mặc định production mà không xem xét tải, rate limit, timeout và ngân sách latency.

## 8. doOnError không tự chạy chỉ vì tạo ra Mono hoặc Flux

Publisher trong Reactor thường **được mô tả trước**, sau đó hoạt động khi subscription được thiết lập. `doOnError` đăng ký callback quan sát, không chạy callback ngay lúc lắp ráp pipeline.

```java
Mono<String> source = Mono.fromCallable(() -> {
    throw new IllegalArgumentException("bad request");
});

Mono<String> observed = source
        .doOnError(error -> System.out.println("error observed"));

// Chưa subscribe: callback chưa chạy.
// Khi subscribe và nguồn phát onError: callback chạy.
```

Đây là snippet. Nhiều source Reactor là cold, vì vậy hai subscriptions độc lập có thể dẫn đến **hai lần thực thi công việc và hai lần ghi log**. Không kết luận rằng mọi publisher đều cold: publisher nóng, shared source và cache có hành vi khác.

Khi source chỉ hoàn tất thành công hoặc rỗng (`Mono.empty()`, `Flux.empty()`), `doOnError` không chạy, bởi vì **không có tín hiệu lỗi**. Một luồng bị `cancel()` cũng không mặc nhiên trở thành `onError`.

## 9. doOnError có sửa phần tử hoặc làm luồng chạy tiếp không?

Không, nếu callback quan sát chạy bình thường.

```java
Flux<Integer> source = Flux.just(1, 2, 3)
        .map(value -> {
            if (value == 2) {
                throw new IllegalArgumentException("invalid 2");
            }
            return value;
        })
        .doOnError(error -> log.warn("Invalid element", error));
```

Phần tử 3 **không được xử lý tiếp** sau lỗi tại phần tử 2. `doOnError` không phải lệnh “bỏ qua phần tử lỗi rồi tiếp tục với 3”. Muốn bỏ qua dữ liệu lỗi có chủ đích, cần thiết kế **ranh giới xử lý trên từng item**, ví dụ tạo một publisher riêng cho từng item và xử lý lỗi trong publisher đó.

Một mẫu dùng `flatMap` theo từng item:

```java
Flux<Integer> processed = Flux.just(1, 2, 3)
        .concatMap(value ->
            Mono.fromCallable(() -> {
                    if (value == 2) {
                        throw new IllegalArgumentException("invalid 2");
                    }
                    return value * 10;
                })
                .doOnError(error ->
                        log.warn("Invalid value={}", value, error))
                .onErrorResume(IllegalArgumentException.class,
                        error -> Mono.empty()));
```

Đây là snippet, cần `Flux`, `Mono` và logger đã khai báo. Sau xử lý lỗi **bên trong inner Mono cho item=2**, outer `concatMap` vẫn có thể xử lý item=3; kết quả bình thường là 10 và 30. **Không phải `doOnError` đã phục hồi**: chính `onErrorResume` theo từng item biến lỗi của inner publisher thành empty. Đây là lựa chọn có chủ đích cho dữ liệu có thể bỏ; không phù hợp nếu item lỗi cần dừng cả batch hoặc phải lưu vết bắt buộc.

Hạn chế dùng `onErrorContinue` như một giải pháp tổng quát cho lỗi map: ngữ nghĩa của nó phụ thuộc operator nào hỗ trợ và có thể ảnh hưởng upstream theo cách khó lý giải. Tách luồng xử lý và recovery trong inner publisher thường minh bạch hơn khi được phép bỏ item.

## 10. Khi nào quan sát bằng doOnError, khi nào dùng hook khác?

| Điều cần quan sát | Hook phù hợp | Chạy ở trường hợp nào? |
|---|---|---|
| Một item được phát | `doOnNext` | Khi có `onNext` |
| Một lỗi đi qua operator | **`doOnError`** | Khi upstream phát `onError` tại vị trí hook |
| Flux kết thúc thành công | `doOnComplete` | Khi `Flux` nhận `onComplete` |
| Mono thành công hoặc empty | `doOnSuccess` | Khi Mono kết thúc thành công; callback có thể nhận `null` để biểu thị empty |
| Subscription bị hủy | `doOnCancel` | Khi có tín hiệu `cancel()` |
| Mọi kiểu kết thúc/hủy | `doFinally` | Sau complete, error hoặc cancel (nhận `SignalType`) |
| Yêu cầu dữ liệu của downstream | `doOnRequest` | Khi có `request(n)` đi qua vị trí hook |

Một luồng **có lỗi** không gọi `doOnComplete`; một luồng **empty nhưng thành công** không gọi `doOnError`. `Mono.doOnSuccess` có thể nhận Java `null` để thông báo thành công rỗng, nhưng đó **không phải một sự kiện `onNext(null)`**.

Ví dụ quan sát kết thúc:

```java
Mono<String> result = callRemote()
        .doOnError(error -> log.error("failed", error))
        .doFinally(signal ->
                metrics.counter("request.finished",
                        "signal", signal.name()).increment());
```

Đây là snippet: `callRemote` và `metrics` là thành phần giả định. `doFinally` có thể được gọi khi kết thúc thành công, lỗi hoặc cancel. Callback `doFinally` chạy **sau khi terminal signal đã truyền xuống downstream**, nên không nên dùng nó để khẳng định một hệ thống bên ngoài đã ghi log/metric bền vững trước khi subscriber quan sát kết quả.

## 11. Spring WebFlux: ghi log mà vẫn giữ xử lý lỗi đúng HTTP

Giả sử WebFlux controller lấy product từ service reactive. Cần:

1. **Không tìm thấy product**: trả 404 theo chính sách REST.
2. **Service hoặc database lỗi**: ghi log với ngữ cảnh, rồi để tầng xử lý exception quyết định status/body.
3. **Không chặn event loop** bằng `block()`, đồng thời không tự `subscribe()` trong handler.

Ví dụ controller sau **hợp lệ trong một ứng dụng Spring Boot đã cài `spring-boot-starter-webflux` và có bean `CatalogService`**:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/catalog")
public class CatalogController {
    private static final Logger log =
            LoggerFactory.getLogger(CatalogController.class);

    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<ProductDto>> getOne(@PathVariable String id) {
        return service.findById(id)
                .doOnError(error ->
                    log.error("Catalog lookup failed, id={}", id, error))
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound()
                        .<ProductDto>build());
    }
}

record ProductDto(String id, String name) { }

interface CatalogService {
    Mono<ProductDto> findById(String id);
}
```

Đây là **class controller và các kiểu hỗ trợ**, không phải một ứng dụng Spring Boot tự chạy độc lập. Phải có main application, WebFlux starter và bean `CatalogService` thực sự triển khai truy vấn.

Phân tích ba nhánh:

| Service trả gì? | `doOnError` | Phần sau và HTTP |
|---|---|---|
| `Mono.just(product)` | Không chạy | `map` tạo `ResponseEntity` 200 cùng body |
| `Mono.empty()` | Không chạy | `defaultIfEmpty` tạo `ResponseEntity` 404 |
| `Mono.error(error)` | **Chạy callback log** | Lỗi được truyền tiếp; `map` và `defaultIfEmpty` không phục hồi |

Với lỗi service, response HTTP cụ thể phụ thuộc **exception type, error handling, cấu hình Spring và thời điểm response đã được commit**. Đừng khẳng định rằng `doOnError` tự tạo HTTP 500 hoặc 404. Nó chỉ ghi nhận lỗi tại vị trí đó.

Nếu muốn chuyển một lỗi được biết trước thành HTTP status cụ thể, thiết kế mã hóa lỗi/exception handler một cách rõ ràng, ví dụ `onErrorMap` sang `ResponseStatusException` (khi phù hợp), hoặc cơ chế `@RestControllerAdvice`. Nếu muốn fallback một resource từ cache, dùng `onErrorResume` với điều kiện chặt chẽ. Đừng dùng `onErrorComplete()` để biến lỗi truy vấn thành “không tìm thấy” một cách mặc định.

### Kết hợp WebClient

`WebClient.retrieve()` thường biến HTTP 4xx/5xx từ dịch vụ ngoài thành error signal khi nhận body (`WebClientResponseException` hoặc loại liên quan). Vì vậy:

```java
Mono<String> body = webClient.get()
        .uri("/upstream/{id}", id)
        .retrieve()
        .bodyToMono(String.class)
        .doOnError(error ->
            log.warn("Upstream call failed, id={}", id, error));
```

Đây là snippet cần `webClient`/`log`/`id`. `doOnError` quan sát lỗi HTTP/transport/codec đi qua chuỗi này nhưng không thay status, không retry và không đổi failure thành dữ liệu. Nếu muốn xử lý HTTP status riêng khi gọi `WebClient`, cân nhắc `onStatus(...)` của `retrieve()`, hoặc `exchangeToMono(...)` để quyết định response theo nghiệp vụ.

## 12. Logging thực tế: hữu ích nhưng không tạo tác dụng phụ nguy hiểm

`doOnError` phù hợp để ghi log nhưng có vài quy tắc:

- **Ghi kèm context:** operation, endpoint hoặc mã request/correlation ID, mã lỗi, thời gian; tránh chỉ ghi message mà không có stack trace khi cần chẩn đoán.
- **Không ghi dữ liệu nhạy cảm:** access token, mật khẩu, nội dung request riêng tư, thông tin thanh toán hoặc toàn bộ payload nếu không được phép.
- **Tránh log trùng:** controller, service, HTTP filter và global error handler có thể cùng log một lỗi. Chọn một nơi ghi stack trace đầy đủ, những nơi khác dùng metric/context phù hợp.
- **Giữ callback nhanh:** ghi log blocking/dồn quá nhiều sự kiện có thể làm nghẽn thread nhận signal; cân nhắc logging infrastructure và sampling có chủ đích.
- **Không dựa vào thread-local tùy tiện:** pipeline có thể chuyển thread qua `publishOn`/`subscribeOn`; Reactor Context và tracing integration giúp bảo toàn ngữ cảnh theo cơ chế phù hợp.
- **Phân biệt failure với cancellation:** client ngắt kết nối không phải lúc nào cũng phát `onError` đến nơi đặt hook; theo dõi `doFinally`/`doOnCancel` và metric liên quan.
- **Đếm metric đúng ý nghĩa:** một request có nhiều retry có thể tạo nhiều lần `doOnError`; định nghĩa metric là **số lần attempt lỗi** hay **số operation cuối cùng lỗi**.

Mẫu quan sát có phân loại:

```java
Mono<String> result = clientCall()
        .doOnError(TimeoutException.class,
            error -> metrics.counter("remote.timeout").increment())
        .doOnError(error ->
            log.warn("Remote request failed", error));
```

Đây là snippet; nếu lỗi là `TimeoutException`, **cả hai callback có thể chạy** vì overload thứ hai quan sát mọi lỗi. Không có callback nào phục hồi. Nếu hệ thống lớn, nên có một chính sách metric và log tránh đếm trùng cùng mục đích.

## 13. doOnError và kiểm thử: xác nhận lỗi còn truyền tới subscriber

Điều cần chứng minh không chỉ là “callback được gọi”, mà còn là **downstream vẫn thấy lỗi**. Khi viết test cho `doOnError`, nên kiểm tra:

1. Callback được gọi khi có `onError`.
2. Exception mà downstream nhận **vẫn là lỗi dự kiến** nếu observer không ném lỗi.
3. Không có `onComplete` hoặc fallback ngầm.
4. Callback **không** được gọi với nguồn thành công/empty.
5. Vị trí trước/sau recovery hoặc retry dẫn đến số lần gọi đúng như thiết kế.

Ví dụ minh họa dùng `reactor-test` và JUnit 5:

```java
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertSame;

class DoOnErrorTest {
    @Test
    void observesWithoutRecovering() {
        IllegalStateException failure =
                new IllegalStateException("broken");
        AtomicReference<Throwable> observed = new AtomicReference<>();

        Mono<String> sequence = Mono.<String>error(failure)
                .doOnError(observed::set);

        StepVerifier.create(sequence)
                .expectErrorSatisfies(error ->
                        assertSame(failure, error))
                .verify();

        assertSame(failure, observed.get());
    }
}
```

Đây là **test class dành cho một dự án đã có reactor-test và JUnit Jupiter**, không nằm trong demo Maven ở mục 6 trừ khi thêm dependency test và cấu hình surefire phù hợp. Ý nghĩa: assertion kiểm tra **cùng một instance lỗi** được observer và subscriber nhìn thấy khi callback hoàn thành bình thường.

### Kiểm tra thứ tự operator

```java
AtomicInteger seen = new AtomicInteger();

Mono<String> recovered = Mono.<String>error(
        new IllegalArgumentException("bad"))
    .doOnError(error -> seen.incrementAndGet())
    .onErrorReturn("safe");

// Sau khi subscribe/verify thành công: seen == 1.
// Nếu chuyển doOnError xuống sau onErrorReturn: seen == 0
// đối với đúng lỗi đã được recovery ở ví dụ này.
```

Đây là snippet; `AtomicInteger` cần import. Không assert counter trước subscription, vì callback không chạy trong lúc assembly.

## 14. Những lỗi phổ biến và cách sửa

### Lỗi 1 — tưởng doOnError nuốt exception

```java
// Sai nếu mong luồng thành công sau log:
Mono<String> result = remoteCall()
        .doOnError(error -> log.error("Failed", error));
```

**Sửa:** xác định fallback hợp lệ và dùng `onErrorResume` hoặc `onErrorReturn`. Nếu lỗi phải được báo ra, giữ nguyên `doOnError` và để downstream/global handler xử lý.

### Lỗi 2 — ghi log rồi lại ném lỗi thủ công trong callback

```java
// Không cần và dễ làm biến đổi tín hiệu lỗi:
.doOnError(error -> {
    log.error("Failed", error);
    throw new IllegalStateException("new failure");
})
```

**Sửa:** observer chỉ quan sát; khi cần đổi kiểu lỗi, dùng `onErrorMap` ở một operator riêng có kiểm thử. Không dùng `doOnError` để điều khiển control flow.

### Lỗi 3 — đặt doOnError sai vị trí

```java
Mono<String> result = source
        .onErrorResume(error -> Mono.just("fallback"))
        .doOnError(error -> log.warn("Original failed", error));
```

Lỗi đã được `onErrorResume` phục hồi thường không đi qua observer cuối. **Sửa:** nếu mục tiêu là đo lỗi nguồn chính, đặt `doOnError` trước recovery. Nếu mục tiêu là đo lỗi cuối của toàn bộ workflow, đặt sau retry/recovery tương ứng.

### Lỗi 4 — nghĩ doOnError làm tiếp item sau lỗi

`Flux.just(1,2,3).map(...)` lỗi ở 2 rồi kết thúc; callback không giúp item 3 tự được xử lý. **Sửa:** thiết kế recovery theo từng item nếu nghiệp vụ chấp nhận bỏ item lỗi, hoặc fail toàn bộ batch nếu yêu cầu atomicity.

### Lỗi 5 — thêm doOnError sau retry rồi chờ thấy mọi attempt

Nếu retry thành công, observer phía sau retry không thấy lỗi attempt trước. **Sửa:** dùng observer trước retry hoặc callback retry để đếm attempt; dùng observer phía sau để đo thất bại cuối cùng.

### Lỗi 6 — ghi log toàn bộ stack trace ở mọi tầng

Một failure có thể được log tại WebClient, service, controller và global handler; khi có retry, số dòng log tăng rất mạnh. **Sửa:** đặt chiến lược log/metric phân tầng, correlation ID, sampling, phân biệt attempt/final failure.

### Lỗi 7 — chỉ đăng ký onNext rồi bỏ error consumer

`subscribe(value -> ...)` mà không cung cấp xử lý lỗi có thể khiến Reactor báo lỗi chưa được xử lý qua cơ chế `ErrorCallbackNotImplemented`. **Sửa:** trong demo/manual subscriber, truyền consumer xử lý `onError`; trong WebFlux handler, trả `Mono`/`Flux` để framework chịu trách nhiệm subscription.

### Lỗi 8 — hiểu cancel/timeout đều giống nhau

Cancel trực tiếp là một signal vòng đời khác lỗi. `timeout` có thể tạo `TimeoutException` trong pipeline và kích hoạt `doOnError` ở vị trí thích hợp; còn việc subscriber tự cancel không có nghĩa lúc nào cũng có `onError`. **Sửa:** quan sát `doFinally` hoặc `doOnCancel` cho đường hủy, và `doOnError` cho đường lỗi.

### Lỗi 9 — callback logging gây block event loop

Một callback gửi dữ liệu đồng bộ sang dịch vụ log mạng có thể giữ thread reactive, gây latency và throughput thấp. **Sửa:** dùng cơ chế logging/telemetry phù hợp và giới hạn chi phí callback; nếu một tác vụ phải được bảo đảm hoàn thành, đưa nó thành một publisher có policy rõ, không dựa vào side effect best-effort.

### Lỗi 10 — biến mọi lỗi thành fallback vô điều kiện

`onErrorReturn("OK")` cho mọi lỗi có thể che lỗi bảo mật, dữ liệu bị hỏng hoặc outage nghiêm trọng. **Sửa:** phân loại exception, fallback có hợp đồng rõ và theo dõi lý do dùng fallback; lỗi không thể phục hồi tiếp tục đi qua `onError`.

### Lỗi 11 — không tính đến cold subscription

Đặt `doOnError` vào publisher cold rồi subscribe hai lần có thể tạo hai request và hai log. **Sửa:** quản lý số subscription, chia sẻ/caching có chủ đích nếu phù hợp và đo bằng metric ở tầng nghiệp vụ; không mặc định log là exactly-once.

### Lỗi 12 — cho rằng doOnError luôn phát hiện lỗi từ mọi chỗ trong ứng dụng

Observer chỉ nằm trên **đường tín hiệu tại vị trí đặt nó**. Exception xảy ra phía downstream hoặc trong một callback ngoài luồng không nối với publisher có thể không đi qua observer. **Sửa:** đặt hook gần ranh giới cần quan sát, hiểu lifecycle và kiểm thử trường hợp lỗi thật.

## 15. Bài tập tự kiểm tra

**Tình huống A:** `Mono.error(new IOException("offline")).doOnError(log::warn)`, không có recovery. Downstream có nhận `onError` không?

→ **Có**; `doOnError` quan sát và chuyển tiếp lỗi. (Giả định callback/logger viết đúng chữ ký và không tự lỗi.)

**Tình huống B:** `Mono.empty().doOnError(...)` có gọi observer không?

→ **Không**; empty là complete thành công, không phải error.

**Tình huống C:** `Mono.just("OK").doOnError(...)` có gọi observer không?

→ **Không**; source thành công không có tín hiệu lỗi.

**Tình huống D:** `Mono.error(e).doOnError(log).onErrorReturn("default")`, cuối cùng subscriber nhận gì?

→ `"default"` rồi complete; logger chạy cho lỗi nguồn. Operator `onErrorReturn` thực hiện recovery.

**Tình huống E:** `Mono.error(e).onErrorReturn("default").doOnError(log)`, logger có thấy lỗi nguồn không?

→ **Không**, vì lỗi đã được `onErrorReturn` chuyển thành thành công trước khi đến observer.

**Tình huống F:** `Flux.just(1,2,3).map(v -> { if(v == 2) throw ...; return v; }).doOnError(...)` có phát 3?

→ **Không**; lỗi khi xử lý 2 kết thúc subscription đó, nên phần tử 3 không được xử lý tiếp.

**Tình huống G:** `remoteCall().doOnError(log).retry(2)` nếu cả ba lượt đều lỗi: callback có thể được gọi mấy lần?

→ **Ba lần** nếu mỗi subscription phát một lỗi. `retry(2)` là thêm hai lần sau attempt đầu.

**Tình huống H:** `remoteCall().retry(2).doOnError(log)` nếu attempt thứ ba thành công: observer có log các lỗi cũ không?

→ **Không**; lỗi trước đã được retry xử lý, downstream nhận giá trị thành công.

**Tình huống I:** Client SSE đóng kết nối, upstream bị cancel. `doOnError` có nhất thiết chạy không?

→ **Không**; cancellation và error là các signal khác nhau. Dùng `doFinally` hoặc `doOnCancel` để quan sát cancel khi phù hợp.

**Tình huống J:** Một callback `doOnError` ghi log rồi ném exception mới. Có còn bảo đảm subscriber nhận chính lỗi gốc không?

→ **Không**. Đừng để observer làm phát sinh lỗi; dùng `onErrorMap` khi cố ý biến đổi error signal.

## 16. Checklist cho code review

Trước khi chấp nhận một chuỗi có `doOnError`, xác nhận:

1. **Mục tiêu của callback là quan sát?** Không nhầm với fallback, map exception hoặc retry.
2. **Vị trí observer phù hợp?** Đặt trước recovery để thấy lỗi ban đầu; sau recovery/retry để xem lỗi chưa được xử lý.
3. **Đã có đường xử lý lỗi?** Subscriber/global handler hoặc operator recovery đúng ý nghĩa nghiệp vụ.
4. **Log có đủ ngữ cảnh?** Thêm operation, correlation ID, loại lỗi; tránh thông tin nhạy cảm.
5. **Observer có an toàn?** Không làm việc blocking lâu, không ném exception và không chứa side effect bắt buộc exactly-once.
6. **Có retry/resubscription?** Phân biệt metric attempt với metric kết quả cuối, không log trùng.
7. **Có nhầm error với empty/cancel?** Dùng hook quan sát phù hợp từng tín hiệu.
8. **Có dùng fallback chỉ cho lỗi phù hợp?** Không che lỗi dữ liệu và hạ tầng nghiêm trọng.
9. **Có kiểm thử terminal signal?** Xác minh error còn truyền, recovery tạo complete đúng lúc và không xử lý item sau lỗi.
10. **Có phù hợp với WebFlux?** Trả publisher, để framework subscribe, tránh `block()` trong request event loop và tránh ghi log nhiều tầng.

**Ghi nhớ:** `doOnError` giống một điểm **ghi nhận lỗi trên đường tín hiệu**. Nó **không sửa dữ liệu và không phục hồi subscription**; sau callback thành công, `onError` vẫn đi tiếp. Nếu muốn kết quả thay thế, dùng `onErrorReturn`/`onErrorResume`; nếu muốn đổi lỗi, dùng `onErrorMap`; nếu muốn đăng ký lại nguồn, dùng `retry`/`retryWhen`. Thứ tự operator quyết định bạn nhìn thấy **lỗi gốc, lỗi cuối hay không nhìn thấy lỗi đã được xử lý**.

## Tài liệu tham khảo

- Project Reactor — [Handling Errors: Log or React on the Side](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- Project Reactor — [Flux.doOnError: callback runs before error propagates](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor — [Mono API: doOnError, onErrorResume, onErrorReturn, retry](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- Project Reactor — [Retry FAQ, retryWhen và backoff](https://projectreactor.io/docs/core/release/reference/faq.html).
- Spring Framework — [WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework — [WebClient: retrieve, status and error handling](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html).
