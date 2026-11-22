# Phân biệt chuỗi rỗng, chuỗi lỗi và chuỗi không kết thúc trong Mono và Flux

Trong Project Reactor và Spring WebFlux, **“không có dữ liệu ngay lúc này” không đồng nghĩa với “đã hoàn tất”, và “đã hoàn tất mà không có dữ liệu” không đồng nghĩa với “gặp lỗi”**. Một `Mono<T>` hoặc `Flux<T>` có thể kết thúc bình thường mà không phát phần tử, kết thúc bằng lỗi hoặc không kết thúc. Ba trạng thái này dẫn đến các hành vi rất khác nhau đối với fallback, timeout, HTTP response, kiểm thử và việc giải phóng tài nguyên.

Bài học tập trung vào **ngữ nghĩa tín hiệu và cách xử lý ba loại chuỗi**, trong ngữ cảnh cha **Mono và Flux** của module Spring Framework - reactive.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận biết `Mono.empty()`, `Flux.empty()`, `Mono.error(...)`, `Flux.error(...)`, `Mono.never()` và `Flux.never()`.
- Phân biệt kết quả **hoàn thành rỗng**, **kết thúc bằng lỗi** và **đang chờ vô hạn** dựa trên `onNext`, `onError`, `onComplete`.
- Hiểu vì sao `defaultIfEmpty`/`switchIfEmpty` chỉ xử lý luồng **kết thúc rỗng**, còn `onErrorResume` xử lý **lỗi**, và `timeout` xử lý tình trạng **không có tín hiệu đúng hạn**.
- Phân biệt nguồn im lặng không kết thúc với nguồn phát nhiều phần tử nhưng không kết thúc.
- Viết và kiểm thử pipeline có giới hạn thời gian, xử lý hủy đăng ký và ánh xạ kết quả sang HTTP phù hợp trong Spring WebFlux.

## 2. Giao thức tín hiệu là nền tảng

Reactor dựa trên Reactive Streams. Một `Publisher` được `Subscriber` đăng ký, gửi `onSubscribe(subscription)`, sau đó có thể gửi dữ liệu qua `onNext(value)` và một tín hiệu kết thúc qua **`onComplete()`** hoặc **`onError(error)`**. Hai tín hiệu kết thúc loại trừ nhau: sau `onComplete` hoặc `onError`, luồng đó không còn phát phần tử hợp lệ nào nữa.

`Subscription.request(n)` thể hiện nhu cầu dữ liệu từ downstream; `Subscription.cancel()` thể hiện yêu cầu hủy. **Cancel không phải một lời gọi `onComplete` hay `onError` gửi tới subscriber.** Một publisher tuân thủ giao thức không phát giá trị `null` trong `onNext`; thiếu giá trị được biểu diễn bằng completion rỗng hoặc dạng dữ liệu hợp lệ khác, tùy bài toán.

`Mono<T>` phát tối đa một `onNext`; `Flux<T>` phát từ không đến nhiều `onNext`. Cả hai đều có thể rỗng, lỗi hoặc chờ mãi.

```text
Rỗng (empty):        onSubscribe  ──────────────────→ onComplete
Lỗi (error):         onSubscribe  ──────────────────→ onError(E)
Không kết thúc:      onSubscribe  ────────────────→  (không terminal signal)
Có dữ liệu:          onSubscribe → onNext(A) → onNext(B) → onComplete
Dữ liệu rồi lỗi:     onSubscribe → onNext(A) ────────→ onError(E)
Dữ liệu mãi:         onSubscribe → onNext(A) → onNext(B) → ... (chưa terminal)
```

Sơ đồ là thứ tự logic; trong ứng dụng thật, tín hiệu có thể đến theo thời gian, trên các scheduler khác nhau. Với nguồn rỗng hoặc lỗi, tín hiệu kết thúc có thể xuất hiện ngay sau đăng ký mà không cần chờ một phần tử dữ liệu. Tuy nhiên, việc **khai báo** pipeline bằng toán tử thường chưa thực thi công việc: nguồn lạnh phổ biến chỉ bắt đầu khi có `subscribe`.

## 3. Ba loại chuỗi: bảng so sánh

| Tính chất | Chuỗi rỗng (empty) | Chuỗi lỗi (error) | Chuỗi không kết thúc (never) |
| --- | --- | --- | --- |
| Nhà máy Reactor | `Mono.empty()`, `Flux.empty()` | `Mono.error(ex)`, `Flux.error(ex)` | `Mono.never()`, `Flux.never()` |
| `onNext` | Không | Không đối với nguồn `error` tạo trực tiếp; luồng khác có thể phát dữ liệu trước khi lỗi | Không đối với nguồn `never` tạo trực tiếp |
| `onComplete` | **Có** | Không | Không |
| `onError` | Không | **Có** | Không |
| Có terminal signal? | Có, hoàn thành thành công | Có, thất bại | Không |
| `defaultIfEmpty` / `switchIfEmpty` | Được kích hoạt | Không | Không |
| `onErrorResume` | Không | Được kích hoạt | Không |
| `timeout` | Thường không cần vì đã hoàn tất | Không “chữa” lỗi đã xảy ra | Có thể tạo lỗi timeout khi quá hạn |
| `block()` trong demo | Trả về `null` nếu hoàn thành rỗng | Ném exception tương ứng/được Reactor bọc khi cần | Chờ vô hạn nếu không có timeout/cancel |

**Quan trọng:** “empty” là **hoàn thành thành công với 0 phần tử**. “error” là **một kết cục thất bại** chứ không phải một phần tử bình thường. “never” mô tả **sự vắng mặt của cả tín hiệu dữ liệu lẫn tín hiệu cuối**; một phiên đăng ký sẽ không tự hoàn tất trừ khi có tác động như cancel hoặc một toán tử như `timeout`.

## 4. Chuỗi rỗng: kết thúc thành công, không có giá trị

`Mono.empty()` là trường hợp một thao tác kết thúc thành công nhưng không trả dữ liệu; `Flux.empty()` là trường hợp chuỗi có 0 phần tử và hoàn thành. Một số nguồn rỗng hợp lệ:

- Tìm kiếm theo khóa không tìm thấy kết quả: repository trả `Mono.empty()`.
- Lọc loại hết phần tử: `Flux.just(1, 3).filter(n -> n % 2 == 0)` hoàn thành rỗng.
- Danh sách đầu vào rỗng: `Flux.fromIterable(List.of())` hoàn thành rỗng.
- Tác vụ chỉ cần báo “đã xong”: `Mono<Void>`, ví dụ `Mono.fromRunnable(task)` hoặc kết quả sau `then()`.

Một ví dụ đọc nhanh:

```java
Mono<String> emptyMono = Mono.empty();
Flux<Integer> emptyFlux = Flux.empty();

emptyMono.subscribe(
    value -> System.out.println("next " + value),
    error -> System.out.println("error"),
    () -> System.out.println("complete")
);
// In: complete
```

Dù không có `onNext`, callback `onComplete` vẫn được gọi. Từ khóa “rỗng” **không** có nghĩa là publisher chưa chạy; nó có thể đã kiểm tra xong và xác nhận không có kết quả.

### Sinh Mono rỗng từ giá trị có thể thiếu

`Mono.just(value)` yêu cầu `value` khác `null` và lỗi ngay nếu truyền `null`. Nếu đầu vào có thể là `null`, dùng `Mono.justOrEmpty(value)` hoặc `Mono.justOrEmpty(optional)`. `Mono.fromCallable(() -> null)` cũng biểu diễn completion rỗng khi `Callable` trả `null`; đây là cơ chế từ adapter nguồn, không phải cho phép `onNext(null)`.

Một chi tiết dễ gây nhầm:

- `doOnNext(value -> ...)` **không** chạy khi `Mono` rỗng.
- `doOnSuccess(value -> ...)` của `Mono` **có thể được gọi với `value == null`** khi Mono hoàn thành rỗng. Không dùng callback này như bằng chứng đã có dữ liệu.
- `switchIfEmpty` nhận publisher dự phòng; với logic dự phòng có chi phí hoặc side effect, có thể bọc bằng `Mono.defer(() -> lookupFallback())` để trì hoãn việc tạo nguồn.

### Chọn fallback cho chuỗi rỗng

```java
Mono<String> a = Mono.<String>empty()
    .defaultIfEmpty("khong-co-du-lieu");

Mono<String> b = Mono.<String>empty()
    .switchIfEmpty(Mono.just("nguon-du-phong"));
```

`defaultIfEmpty` cung cấp một **giá trị** thay thế. `switchIfEmpty` chuyển sang một **publisher** thay thế, nên phù hợp với một truy vấn dự phòng bất đồng bộ. Nếu upstream có giá trị thì không dùng fallback; nếu upstream phát lỗi thì không dùng hai toán tử này để xử lý lỗi.

Không thể áp dụng `defaultIfEmpty(null)` như cách biểu diễn “không có gì”, vì Reactor không chấp nhận `null` làm phần tử. Với `Mono<Void>`, nên dùng `then`/`thenReturn` hoặc tổ hợp publisher phù hợp để nối tiếp công việc, thay vì kỳ vọng có `onNext` của kiểu `Void`.

## 5. Chuỗi lỗi: kết thúc bất thường bằng onError

`Mono.error(new IllegalStateException("bad state"))` và `Flux.error(...)` phát tín hiệu lỗi khi có đăng ký. Một pipeline cũng có thể phát một số dữ liệu **trước** khi gặp lỗi:

```java
Flux<Integer> result = Flux.just(2, 1, 0, 5)
    .map(n -> 10 / n);
```

Bên tiêu thụ có thể nhận `5`, rồi `10`, sau đó `onError(ArithmeticException)`. Giá trị từ phần tử nguồn `5` ở cuối **không được xử lý**, vì `onError` là terminal signal. Không có `onComplete` sau đó.

Xử lý đúng phụ thuộc ý nghĩa lỗi:

- `doOnError(log::error)` để quan sát; nó **không** phục hồi luồng.
- `onErrorReturn(fallback)` thay lỗi bằng một giá trị.
- `onErrorResume(ex -> anotherPublisher)` chuyển sang publisher dự phòng khi lỗi xảy ra.
- `onErrorMap(ex -> new DomainException(...))` chuyển loại lỗi để tầng trên xử lý.
- `onErrorComplete()` cố ý chuyển lỗi thành **completion rỗng**; phải dùng thận trọng để không che lỗi thật.
- `retry(n)` đăng ký lại nguồn khi lỗi; có thể lặp lại side effect, vì vậy cần cân nhắc idempotency, loại lỗi và giới hạn số lần thử.

Ví dụ:

```java
Mono<String> recovered =
    Mono.<String>error(new IllegalArgumentException("invalid"))
        .onErrorResume(error -> Mono.just("recovered"));
```

Nguồn bị lỗi đã **kết thúc**; `onErrorResume` không “tiếp tục ở phần tử tiếp theo” trong nguồn cũ, mà dùng publisher thay thế. Không nhầm việc đăng ký lại trong `retry` với việc sửa lỗi rồi đi tiếp đúng vị trí cũ.

Một tín hiệu lỗi của Reactor khác với một sự kiện nghiệp vụ như `PaymentDeclined` được gửi bằng `onNext`. Nếu hệ thống cần giữ cả dữ liệu thất bại và thành công trong cùng một stream, hãy thiết kế một kiểu kết quả có trạng thái (ví dụ sealed interface hoặc record), chứ không lạm dụng terminal error cho mọi quyết định nghiệp vụ thông thường.

## 6. Chuỗi không kết thúc: chưa có tín hiệu cuối

`Mono.never()` và `Flux.never()` **không phát `onNext`, `onComplete` hay `onError`**. Subscriber vẫn có thể nhận `onSubscribe`, nhưng nếu không có cancel hoặc toán tử làm thay đổi vòng đời, phiên đăng ký có thể chờ mãi. Vì không có terminal signal:

- `defaultIfEmpty` không chạy: toán tử này cần biết chắc nguồn **đã hoàn thành rỗng**.
- `switchIfEmpty` không chạy vì upstream chưa hoàn thành.
- `onErrorResume` không chạy vì upstream chưa báo lỗi.
- `doFinally` không được kích hoạt chỉ vì thời gian đã trôi qua; nó cần complete, error hoặc cancellation.
- `block()` không có timeout sẽ chờ vô hạn. Tránh dùng trong WebFlux event loop và tránh viết test có thể treo.

**Không kết thúc không nhất thiết là im lặng.** `Flux.interval(Duration.ofSeconds(1))` phát `0, 1, 2, ...` đều đặn và có thể tiếp tục vô hạn; đây là chuỗi **có dữ liệu nhưng không có terminal signal**. Tương tự, `Flux.just(1).concatWith(Flux.never())` phát 1 rồi chờ mãi. Ngược lại, `Flux.interval(...).take(3)` hoàn thành sau ba phần tử vì `take` chủ động giới hạn lượng dữ liệu.

```text
Flux.never():           ───────────────────────────── (im lặng, không hoàn thành)
Flux.interval(...):     ──0──1──2──3──4──...         (có phần tử, không tự hoàn thành)
Flux.just(1) + never:   ──1────────────────────────── (một phần tử rồi im lặng)
Flux.empty():           ──[onComplete]               (hoàn thành ngay)
```

Trong một hệ thống streaming liên tục (SSE, WebSocket, giám sát), luồng kéo dài có thể là **thiết kế có chủ ý**. Điều quan trọng là vòng đời kết nối, cancel, backpressure, heartbeat và timeout phải được quản lý. `Flux.never()` là ví dụ cực đoan để kiểm tra semantics; không nên coi nó là cách xây dựng một hệ thống lắng nghe sự kiện thực tế.

## 7. Ví dụ Java 17+ chạy được: quan sát từng tín hiệu

Có thể chạy Reactor độc lập với Spring để xem tín hiệu rõ ràng. Tạo project Maven:

```text
reactor-signals/
├── pom.xml
├── src/main/java/SignalKindsDemo.java
└── src/test/java/SignalKindsTest.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>reactor-signals</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.9</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>3.6.9</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.3</version>
      <scope>test</scope>
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
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
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

Đây là bộ phiên bản minh họa thống nhất cho ví dụ độc lập. Trong ứng dụng Spring Boot thực tế, ưu tiên để Spring Boot BOM quản lý các dependency Reactor tương thích.

Nội dung `src/main/java/SignalKindsDemo.java`:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class SignalKindsDemo {

    public static void main(String[] args) {
        show("EMPTY", Flux.<Integer>empty(), false);
        show("ERROR", Flux.<Integer>error(
            new IllegalStateException("boom")), false);
        show("NEVER", Flux.<Integer>never(), true);

        String emptyFallback = Mono.<String>empty()
            .defaultIfEmpty("empty-fallback")
            .block();

        String errorFallback = Mono.<String>error(
                new IllegalArgumentException("invalid"))
            .onErrorResume(e -> Mono.just("error-fallback"))
            .block();

        String timeoutFallback = Mono.<String>never()
            .timeout(Duration.ofMillis(50))
            .onErrorResume(TimeoutException.class,
                e -> Mono.just("timeout-fallback"))
            .block();

        System.out.println("empty fallback: " + emptyFallback);
        System.out.println("error fallback: " + errorFallback);
        System.out.println("never timeout: " + timeoutFallback);
    }

    private static void show(
            String label, Flux<Integer> source, boolean cancel) {

        System.out.println("== " + label + " ==");

        Disposable subscription = source
            .doOnSubscribe(s -> System.out.println("onSubscribe"))
            .doOnNext(value ->
                System.out.println("onNext " + value))
            .doOnComplete(() -> System.out.println("onComplete"))
            .doOnError(error ->
                System.out.println("onError "
                    + error.getClass().getSimpleName()
                    + ": " + error.getMessage()))
            .doOnCancel(() -> System.out.println("onCancel"))
            .subscribe(
                value -> { },
                error -> { },
                () -> { }
            );

        if (cancel) {
            subscription.dispose();
        }
    }
}
```

Chạy trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=SignalKindsDemo
```

Stdout dự kiến từ chính chương trình:

```text
== EMPTY ==
onSubscribe
onComplete
== ERROR ==
onSubscribe
onError IllegalStateException: boom
== NEVER ==
onSubscribe
onCancel
empty fallback: empty-fallback
error fallback: error-fallback
never timeout: timeout-fallback
```

Cách đọc kết quả:

1. **EMPTY:** subscribe thành công và hoàn thành ngay. Không có `onNext`, nên fallback rỗng hoạt động.
2. **ERROR:** subscribe xong nhận `onError`. Không gọi `onComplete`; nhánh phục hồi lỗi tạo giá trị thay thế.
3. **NEVER:** chỉ có `onSubscribe`. `show` gọi `dispose()` một cách chủ động nên `doOnCancel` chạy; nếu không cancel thì nguồn này không tự phát kết thúc.
4. Với `Mono.never().timeout(...)`, toán tử timeout phát lỗi `TimeoutException` khi hết hạn, rồi `onErrorResume` biến lỗi đó thành giá trị `timeout-fallback`. Fallback không đến từ `Mono.never()` nguyên thủy.
5. `block()` chỉ được dùng trong hàm `main` minh họa, ngoài đường xử lý reactive server. Không dùng `block()`/`blockLast()` trong controller hoặc code chạy trên event loop của Spring WebFlux.

Mã sử dụng `Flux.never()` **không tự tạo scheduler chờ**; chính ví dụ chủ động hủy ngay sau đăng ký. Với một publisher đang giữ socket, subscription hoặc timer, cancel còn là bước quan trọng để giải phóng tài nguyên.

## 8. Quy tắc chọn toán tử theo tín hiệu

Các toán tử khác nhau phản ứng với **điều kiện khác nhau**:

| Tình huống upstream | Toán tử phù hợp | Điều kiện kích hoạt | Kết quả mong muốn |
| --- | --- | --- | --- |
| Không có bản ghi, hoàn thành bình thường | `defaultIfEmpty(value)` | `onComplete` với 0 phần tử | Phát giá trị mặc định |
| Không có bản ghi, cần truy vấn nguồn khác | `switchIfEmpty(otherPublisher)` | `onComplete` với 0 phần tử | Đăng ký nguồn dự phòng |
| Gặp lỗi có thể phục hồi | `onErrorResume(handler)` | `onError` | Chuyển sang publisher dự phòng |
| Muốn thay lỗi bằng giá trị cố định | `onErrorReturn(value)` | `onError` | Phát giá trị và hoàn thành |
| Không có tín hiệu mới đúng hạn | `timeout(duration)` | Quá thời hạn của toán tử | Phát `TimeoutException` |
| Quá hạn, muốn chuyển sang dữ liệu dự phòng | `timeout(duration, fallback)` | Quá thời hạn | Chuyển sang fallback publisher |
| Cần giới hạn stream vô hạn | `take(n)` | Đã phát đủ `n` phần tử | Downstream hoàn thành, hủy upstream |
| Client không còn quan tâm | `cancel()` / `dispose()` | Hành động từ subscriber | Ngừng subscription; không phát terminal tới subscriber |

So sánh ba câu dễ nhầm:

```java
Mono<String> a = Mono.<String>empty()
    .switchIfEmpty(Mono.just("A")); // "A"

Mono<String> b = Mono.<String>error(
        new IllegalStateException("failure"))
    .onErrorResume(e -> Mono.just("B")); // "B"

Mono<String> c = Mono.<String>never()
    .timeout(Duration.ofMillis(100),
             Mono.just("C")); // "C" sau timeout
```

Dấu chú thích kết quả ở đây mô tả giá trị mà subscriber nhận; các câu chỉ **tạo publisher** cho tới khi có đăng ký.

Không nên viết `Mono.never().switchIfEmpty(...)` rồi kỳ vọng fallback chạy, vì không có completion để xác nhận là rỗng. Cũng không nên viết `Mono.never().onErrorResume(...)` rồi kỳ vọng một lỗi tự sinh ra. Muốn giới hạn thời gian, thêm `timeout` hoặc cơ chế hủy từ phía subscriber/transport. Thời gian timeout phải phù hợp đặc tính luồng; với SSE lâu dài, thời gian im lặng hợp lệ có thể lớn và cần heartbeat.

### Lưu ý về request và backpressure

Một subscriber có thể đã gọi `request(n)` nhưng vẫn **không nhận phần tử**: upstream rỗng, đang chờ I/O, chưa có dữ liệu, hoặc là `never`. Ngược lại, upstream có dữ liệu nhưng downstream chưa yêu cầu có thể phải chờ nhu cầu. **Chỉ quan sát một khoảng im lặng không đủ để suy ra stream là empty, error hay never**; phải đợi tín hiệu kết thúc, lỗi, timeout hoặc kiểm tra chính nguồn đã thiết kế.

## 9. Phân biệt “chưa có dữ liệu” và “hoàn thành rỗng” trong chuỗi toán tử

Cách sắp xếp toán tử ảnh hưởng nghĩa của kết quả.

### Lọc hết phần tử

```java
Mono<Integer> result = Mono.just(3)
    .filter(n -> n % 2 == 0)
    .defaultIfEmpty(0);
// Khi subscribe, kết quả là 0.
```

Giá trị 3 không thỏa bộ lọc, nên downstream của `filter` nhận completion rỗng; `defaultIfEmpty` mới được kích hoạt. Không có lỗi xảy ra.

### Dữ liệu trước khi lỗi

```java
Flux<Integer> result = Flux.just(10, 0, 5)
    .map(n -> 100 / n)
    .onErrorResume(error -> Flux.just(-1));
// Khi subscribe: onNext(10), onNext(-1), onComplete.
```

Kết quả chia cho 0 làm upstream lỗi; `onErrorResume` thay phần còn lại bằng publisher phát -1. Phần tử nguồn cuối 5 không được đi qua `map`.

### Phát một phần tử rồi chờ vô hạn

```java
Flux<Integer> result = Flux.just(7)
    .concatWith(Flux.<Integer>never())
    .defaultIfEmpty(0);
// Khi subscribe: onNext(7), rồi chờ; không onComplete.
```

Fallback rỗng không kích hoạt vì luồng đã có giá trị **và** chưa kết thúc. `timeout` có thể cắt quãng chờ, nhưng khi đó phát lỗi, không tự biến quá trình chờ thành completion rỗng.

### Nối tiếp tác vụ bằng then

`Mono<Void>` rất hữu ích để báo “hoàn thành công việc” mà không mang dữ liệu. Ví dụ `repository.save(...).then()` (tùy kiểu trả về) bỏ qua giá trị và hoàn thành không dữ liệu khi upstream thành công; nếu upstream lỗi thì lỗi được truyền; nếu upstream không hoàn thành thì `then()` cũng không thể tự hoàn thành. Với `thenReturn(value)`, chỉ khi upstream **hoàn thành thành công** mới phát `value`.

Một điều cần nhớ khi dùng `zip`/`zipWith`: ghép dữ liệu cần có giá trị từ các nguồn. Nếu một nguồn hoàn thành rỗng trước khi có giá trị, kết quả ghép có thể hoàn thành rỗng và không tạo được bộ giá trị; không thể coi nguồn rỗng như một giá trị `null` để ghép.

## 10. Áp dụng trong Spring WebFlux: HTTP cần ánh xạ trạng thái đúng

Xét một API tìm tài khoản. Repository reactive có thể trả:

- `Mono.just(account)` nếu tìm thấy;
- `Mono.empty()` nếu không tìm thấy;
- `Mono.error(ex)` nếu truy vấn thất bại;
- publisher không có terminal signal nếu thao tác bị treo hoặc một mock được viết với `Mono.never()`.

Đó là bốn trạng thái **khác nhau**. Một HTTP API thông thường cần biến “không tìm thấy” thành **404 Not Found**, lỗi hạ tầng thành phản hồi lỗi phù hợp và sự chờ quá lâu thành timeout có chính sách. **Trả `Mono.empty()` từ controller không mặc nhiên mang nghĩa 404.**

Ví dụ controller sau là một đoạn trong ứng dụng Spring WebFlux đã có `AccountService` và `AccountDto`; đây **không phải chương trình Java độc lập**, vì các kiểu service/DTO phải được ứng dụng khai báo:

```java
import java.time.Duration;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/accounts")
public class AccountController {
    private final AccountService service;

    public AccountController(AccountService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<AccountDto>> find(
            @PathVariable String id) {

        return service.findById(id)
            .timeout(Duration.ofSeconds(3))
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
```

Nếu service hoàn thành rỗng, `defaultIfEmpty` trả phản hồi **404**. Nếu service phát lỗi, lỗi được chuyển tiếp đến cơ chế xử lý exception của WebFlux (chính sách HTTP lỗi cụ thể do ứng dụng cấu hình). Nếu quá hạn ba giây không có tín hiệu phù hợp, `timeout` tạo lỗi timeout, **không tự động trả 404**. Ứng dụng có thể ánh xạ loại lỗi timeout sang 504 Gateway Timeout hoặc mã thích hợp với vai trò và chính sách API; không nên coi nó là “không có tài khoản”.

Để thực sự non-blocking, `service.findById` phải dùng nguồn I/O non-blocking, hoặc cô lập đoạn blocking theo cách có kiểm soát. Việc chỉ trả về kiểu `Mono` không tự biến JDBC đồng bộ hoặc lời gọi `Thread.sleep` thành non-blocking.

Với SSE/WebSocket, luồng dài không có terminal signal có thể là hợp lệ trong toàn bộ thời gian client đăng ký. Server cần quản lý client disconnect → cancellation, stream lỗi → chính sách retry/reconnect, và các khoảng lặng → heartbeat/timeout hợp lý. Một kết nối chưa gửi sự kiện không có nghĩa “empty”; chỉ khi stream hoàn thành không dữ liệu mới gọi là “empty” theo semantics Reactor.

## 11. Kiểm thử đúng ba kết cục bằng StepVerifier

Kiểm thử reactive cần kiểm tra **tín hiệu cuối**, không chỉ giá trị in ra. Với `reactor-test` và JUnit trong `pom.xml` ở trên, tạo `src/test/java/SignalKindsTest.java`:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class SignalKindsTest {

    @Test
    void emptyCompletesWithoutValue() {
        StepVerifier.create(Mono.<String>empty())
            .verifyComplete();
    }

    @Test
    void errorTerminatesInsteadOfCompleting() {
        StepVerifier.create(Flux.<Integer>error(
                new IllegalStateException("boom")))
            .expectError(IllegalStateException.class)
            .verify();
    }

    @Test
    void neverEmitsNothingUntilCancelled() {
        StepVerifier.create(Flux.<Integer>never())
            .expectSubscription()
            .expectNoEvent(Duration.ofMillis(50))
            .thenCancel()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void timeoutCanRecoverFromNever() {
        Mono<String> source = Mono.<String>never()
            .timeout(Duration.ofMillis(30))
            .onErrorResume(TimeoutException.class,
                e -> Mono.just("fallback"));

        StepVerifier.create(source)
            .expectNext("fallback")
            .verifyComplete();
    }
}
```

Chạy:

```bash
mvn -q test
```

Maven thoát với mã **0** khi cả bốn test thành công; dùng `-q` nên bình thường không cần có dòng stdout riêng của ứng dụng. Test `neverEmitsNothingUntilCancelled` có `expectNoEvent` để xác minh khoảng im lặng và `thenCancel` để kết thúc có kiểm soát. Nếu chỉ gọi `verifyComplete()` trên `Flux.never()`, test sẽ chờ mãi trừ khi có timeout bên ngoài. Test timeout cho thấy tín hiệu lỗi được **toán tử timeout tạo ra**, rồi fallback xử lý lỗi đó.

Trong test thực tế, khi kiểm tra luồng theo thời gian với `Flux.interval` hoặc nhiều timer, cân nhắc `StepVerifier.withVirtualTime(...)` để điều khiển thời gian ảo và giảm thời gian chờ. Khi dùng virtual time phải tạo publisher một cách trì hoãn bên trong supplier để scheduler ảo được áp dụng đúng.

## 12. Những lỗi thường gặp

1. **“Không có `onNext` thì là empty.”** Sai: `error` và `never` cũng có thể không có `onNext`. Cần xác định terminal signal.
2. **“`onError` rồi vẫn có thể `onComplete`.”** Sai: mỗi subscription kết thúc bằng một loại terminal signal. Có thể xử lý lỗi bằng publisher dự phòng, nhưng đó là một đường xử lý mới.
3. **“`defaultIfEmpty` cứu được thao tác treo.”** Sai: nó chỉ xử lý khi upstream hoàn thành mà không có dữ liệu.
4. **“`onErrorResume` tự chạy khi lâu quá chưa có giá trị.”** Sai: cần một tín hiệu lỗi, chẳng hạn từ `timeout`.
5. **“`Flux.never()` giống `Flux.interval(...)`.”** Sai: một loại im lặng hoàn toàn; loại kia tiếp tục phát phần tử theo thời gian.
6. **“Không tìm thấy bản ghi và database timeout đều là 404.”** Sai: thiếu bản ghi là trường hợp kết quả rỗng có thể ánh xạ 404; timeout là lỗi thời gian/chất lượng dịch vụ phải xử lý riêng.
7. **“Cancel chính là complete.”** Sai: `cancel()` là điều khiển của subscriber; phía upstream có thể được hủy, còn downstream không nhận thêm `onComplete` chỉ do thao tác hủy.
8. **“`block()` dùng được mọi nơi để xem publisher có dữ liệu không.”** Sai: với nguồn never có thể treo; với server reactive có thể chặn event loop. Trong bài demo ngoài server, nếu bắt buộc block thì đặt giới hạn thời gian thích hợp.
9. **“`onErrorComplete()` luôn vô hại.”** Sai: nó chuyển lỗi thành thành công rỗng và có thể che mất lỗi hạ tầng.
10. **“Một `Mono<Void>` không có phần tử tức là chưa làm việc.”** Sai: một thao tác hoàn thành thành công có thể chủ đích chỉ phát completion, chẳng hạn việc ghi dữ liệu rồi `then()`.
11. **“Không cần quản lý nguồn không kết thúc.”** Sai: với stream thực tế phải xử lý cancellation, kết nối đóng, timeout, backpressure và tài nguyên.

## 13. Tình huống luyện tập và đáp án

**Bài 1.** `Mono.<String>empty().defaultIfEmpty("guest")` phát gì?  
**Đáp án:** Khi đăng ký, phát `guest` rồi hoàn thành. Vì nguồn rỗng **đã gửi `onComplete`**, fallback hoạt động.

**Bài 2.** `Mono.<String>error(new RuntimeException()).defaultIfEmpty("guest")` phát gì?  
**Đáp án:** `onError`, không phát `guest`. Muốn phục hồi lỗi, dùng `onErrorResume`/`onErrorReturn` theo chính sách.

**Bài 3.** `Mono.<String>never().switchIfEmpty(Mono.just("guest"))` có hoàn tất không?  
**Đáp án:** Không, nếu không có timeout/cancel hoặc can thiệp khác. Upstream không gửi `onComplete` nên fallback không được kích hoạt.

**Bài 4.** `Flux.just("A").concatWith(Flux.never())` nhận được những gì?  
**Đáp án:** Nhận `A` rồi chờ không có terminal signal. Nó **khác** `Flux.empty()` và khác `Flux.just("A")` hoàn thành bình thường.

**Bài 5.** Một repository trả `Mono.empty()` vì không có ID; một lần khác trả `Mono.error(new TimeoutException())` vì database chậm. Hai trường hợp có cùng ý nghĩa HTTP không?  
**Đáp án:** Không. Trường hợp đầu có thể ánh xạ 404; trường hợp sau là lỗi truy cập/thời gian cần xử lý bằng chính sách timeout và error mapping.

**Bài 6.** Sau `Flux.interval(Duration.ofMillis(100)).take(3)`, downstream có nhận `onComplete` không?  
**Đáp án:** Có, sau ba phần tử. `take(3)` giới hạn luồng và thường hủy upstream để dừng phát thêm.

**Bài 7.** Vì sao `StepVerifier.create(Flux.never()).verifyComplete()` không phải test tốt?  
**Đáp án:** Vì publisher không có terminal signal; phép xác minh có thể chờ mãi. Hãy dùng `expectNoEvent`, `thenCancel` và/hoặc giới hạn thời gian xác minh.

## 14. Checklist khi thiết kế một pipeline

Khi xem một `Mono` hoặc `Flux`, hãy tự trả lời bốn câu:

1. **Có thể rỗng không?** Nếu có, empty là trường hợp nghiệp vụ thành công hợp lệ hay cần trả 404, giá trị mặc định hoặc nguồn thay thế?
2. **Có thể lỗi không?** Lỗi nào được xử lý, lỗi nào cần truyền lên HTTP, lỗi nào được retry an toàn?
3. **Có thể kéo dài hoặc treo không?** Timeout, heartbeat, cancellation và giới hạn tài nguyên đặt ở đâu?
4. **Ai đăng ký và ai hủy?** Trong Spring WebFlux handler, thông thường trả publisher cho framework quản lý subscription; không gọi `subscribe()` tùy tiện rồi bỏ qua vòng đời request.

Ba nguồn `empty`, `error` và `never` là những công cụ tối giản để kiểm tra logic xử lý tín hiệu. Trong thực tế, pipeline có thể phát dữ liệu trước khi lỗi hoặc im lặng vô hạn; muốn xác định chính xác trạng thái, phải nhìn vào **toàn bộ chuỗi tín hiệu**, không chỉ số phần tử đã nhận được.

### Tài liệu tham khảo

- Project Reactor, [Reactor Core Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- Project Reactor, [Javadoc: Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) và [Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor, [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- Spring Framework, [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
- [Reactive Streams Specification](https://www.reactive-streams.org/).
