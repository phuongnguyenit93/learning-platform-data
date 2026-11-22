# onErrorReturn và giá trị thay thế cố định

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Lỗi và thử lại

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác `onErrorReturn` biến một tín hiệu lỗi terminal thành **một giá trị dự phòng cố định** rồi hoàn tất thành công như thế nào đối với `Mono` và `Flux`.
2. Dùng các overload nhận giá trị trực tiếp, loại exception hoặc `Predicate<Throwable>` để giới hạn những lỗi được phép thay thế.
3. Phân biệt `onErrorReturn` với `defaultIfEmpty`, `switchIfEmpty`, `onErrorResume`, `onErrorComplete`, `onErrorMap` và `retry`.
4. Dự đoán dữ liệu nào còn được phát khi `Flux` đã phát một số phần tử rồi gặp lỗi; hiểu tại sao các phần tử phía sau lỗi không tự động được xử lý tiếp.
5. Chọn giá trị dự phòng phù hợp cho nghiệp vụ, giữ thông tin quan sát lỗi, tránh biến sự cố nghiêm trọng thành một response thành công gây hiểu nhầm trong Spring WebFlux.
6. Viết và chạy ví dụ Java 17+ có cả trường hợp thành công, lỗi phù hợp, lỗi không khớp và publisher rỗng.

## 1. Khi nào cần một giá trị dự phòng?

Giả sử một ứng dụng hiển thị nhiệt độ từ cảm biến. Khi dữ liệu cảm biến không lấy được do một lỗi đã xác định, màn hình có thể cần một giá trị dự phòng hoặc một trạng thái rõ ràng như `"unavailable"`. Nhưng nếu lỗi xuất hiện khi xử lý thanh toán hoặc phân quyền, âm thầm biến nó thành kết quả “thành công” có thể gây hậu quả nghiêm trọng.

Trong Reactive Streams, publisher có ba loại tín hiệu cơ bản:

- `onNext(value)`: có một giá trị dữ liệu.
- `onComplete()`: kết thúc thành công, không phát thêm giá trị nào.
- `onError(error)`: kết thúc bằng lỗi, không phát `onNext` hay `onComplete` tiếp theo từ subscription đó.

Một `Mono<T>` phát tối đa một phần tử; một `Flux<T>` có thể phát nhiều phần tử. Cả hai đều có operator `onErrorReturn` của Project Reactor.

**`onErrorReturn(fallback)`** được đặt sau một phần pipeline để *chặn lỗi từ upstream*, phát một giá trị `fallback` thay cho tín hiệu lỗi, rồi phát `onComplete`. Nó **không sửa nguyên nhân lỗi**, không chạy lại nguồn và cũng không phải lời hứa rằng dữ liệu dự phòng tương đương dữ liệu thật.

Sơ đồ cho một `Flux`:

```text
Upstream:
  onNext(10) -> onNext(20) -> onError(TimeoutException)
                                  |
                                  v
                     onErrorReturn(-1)
                                  |
Downstream:
  onNext(10) -> onNext(20) -> onNext(-1) -> onComplete()
```

Nếu upstream phát `onComplete` bình thường, operator chỉ chuyển tiếp completion và **không thêm** `fallback`. Nếu upstream phát `Mono.empty()`, operator vẫn hoàn tất rỗng. Chỉ **lỗi khớp điều kiện** mới kích hoạt giá trị dự phòng.

## 2. Hợp đồng của onErrorReturn

Dạng cơ bản:

```java
Mono<T> recoveredMono = sourceMono.onErrorReturn(fallbackValue);
Flux<T> recoveredFlux = sourceFlux.onErrorReturn(fallbackValue);
```

Đây là **cú pháp minh họa**: `sourceMono`, `sourceFlux` và `fallbackValue` phải cùng kiểu dữ liệu thích hợp. Có ba cách thường dùng:

| Dạng | Khi nào thay lỗi? | Ví dụ |
| --- | --- | --- |
| `onErrorReturn(T fallbackValue)` | Bất kỳ lỗi upstream nào | `mono.onErrorReturn("N/A")` |
| `onErrorReturn(Class<E> exceptionType, T fallbackValue)` | Lỗi thuộc kiểu exception chỉ định | `mono.onErrorReturn(TimeoutException.class, cachedValue)` |
| `onErrorReturn(Predicate<? super Throwable> predicate, T fallbackValue)` | Khi predicate trả `true` cho lỗi | `mono.onErrorReturn(e -> isTemporary(e), fallback)` |

`Class`-based overload kiểm tra loại exception, bao gồm subtype của loại được chỉ định. Predicate cho phép chính sách chọn lỗi linh hoạt hơn nhưng phải ngắn, đáng tin và không chặn thread. Nếu điều kiện **không khớp**, lỗi gốc vẫn tiếp tục đi xuống `onError`; `onErrorReturn` không phải một bộ chuyển lỗi vô điều kiện khi dùng các overload có điều kiện.

### 2.1. Trường hợp với Mono

```java
Mono<Integer> parsed = Mono.just("invalid")
        .map(Integer::parseInt)
        .onErrorReturn(NumberFormatException.class, -1);
```

Đây là **đoạn minh họa**. `Integer.parseInt("invalid")` ném `NumberFormatException` trong `map`; Reactor chuyển exception thành `onError`, `onErrorReturn` bắt đúng loại rồi phát `-1`. Downstream nhìn thấy một `onNext(-1)` và `onComplete` thay vì `onError`.

Ngược lại:

```java
Mono<Integer> ok = Mono.just("25")
        .map(Integer::parseInt)
        .onErrorReturn(-1);
// Giá trị nhận được là 25; fallback -1 không được phát.
```

Với nguồn đã phát giá trị thành công, không có lý do để sử dụng fallback.

### 2.2. Trường hợp với Flux: chỉ thay phần cuối bị lỗi

```java
Flux<Integer> results = Flux.just(6, 3, 0, 2)
        .map(n -> 12 / n)
        .onErrorReturn(-1);
```

Khi có subscriber yêu cầu đầy đủ dữ liệu, dãy tín hiệu logic là:

```text
6 -> 12 / 6 -> onNext(2)
3 -> 12 / 3 -> onNext(4)
0 -> 12 / 0 -> onError(ArithmeticException)
     onErrorReturn(-1) -> onNext(-1) -> onComplete()
2 -> không được xử lý trong subscription này
```

**Kết quả: `[2, 4, -1]`**, không phải `[2, 4, -1, 6]`. Một khi nguồn đã kết thúc vì lỗi, `onErrorReturn` không quay lại nguồn cũ để “bỏ phần tử sai và tiếp tục”. Nó chuyển từ nhánh lỗi sang một giá trị thay thế cuối rồi kết thúc.

Trong ứng dụng trả danh sách, hành vi này rất đáng cân nhắc: downstream có thể nhận **một phần dữ liệu thật và một phần tử dự phòng**. Nếu API cần kết quả “toàn bộ hoặc không có gì”, hãy chuyển sang `collectList()` trước khi xử lý lỗi; `Mono<List<T>>` chỉ phát danh sách sau khi nguồn hoàn tất bình thường.

## 3. Ví dụ Java 17+ chạy được

Ví dụ dưới đây minh họa mọi kết quả quan trọng của `onErrorReturn` mà không phụ thuộc Spring WebFlux runtime. Dùng **Java 17+**, **Maven** và **Project Reactor Core 3.8.8**.

Tạo hai tệp:

```text
on-error-return-demo/
├── pom.xml
└── src/main/java/demo/
    └── OnErrorReturnDemo.java
```

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>on-error-return-demo</artifactId>
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

### src/main/java/demo/OnErrorReturnDemo.java

```java
package demo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class OnErrorReturnDemo {
    private static int buildFallback() {
        System.out.println("fallback created");
        return -9;
    }

    public static void main(String[] args) {
        // A. Các giá trị đã phát được giữ; lỗi thay bằng đúng một phần tử.
        Flux<Integer> numbers = Flux.just(6, 3, 0, 2)
                .map(value -> 12 / value)
                .doOnError(error -> System.out.println(
                        "source error = " + error.getClass().getSimpleName()))
                .onErrorReturn(-1);
        System.out.println("flux = " + numbers.collectList().block());

        // B. Chỉ lỗi NumberFormatException mới được thay.
        Mono<Integer> valid = Mono.just("12")
                .map(Integer::parseInt)
                .onErrorReturn(NumberFormatException.class, -1);
        Mono<Integer> invalid = Mono.just("abc")
                .map(Integer::parseInt)
                .onErrorReturn(NumberFormatException.class, -1);
        System.out.println("mono valid = " + valid.block());
        System.out.println("mono invalid = " + invalid.block());

        // C. Nguồn rỗng không phải lỗi.
        Mono<Integer> empty = Mono.<Integer>empty().onErrorReturn(-1);
        System.out.println("empty has value = " + empty.hasElement().block());
        System.out.println("empty default = " +
                Mono.<Integer>empty().defaultIfEmpty(-1).block());

        // D. Lỗi không khớp Class vẫn đi xuống onError.
        Mono<Integer> unmatched = Mono.<Integer>error(
                        new IllegalStateException("service down"))
                .onErrorReturn(IllegalArgumentException.class, 99);
        try {
            unmatched.block();
        } catch (IllegalStateException error) {
            System.out.println("unmatched = " +
                    error.getClass().getSimpleName());
        }

        // E. Predicate chọn đúng loại lỗi.
        Mono<Integer> predicate = Mono.<Integer>error(
                        new IllegalStateException("temporary"))
                .onErrorReturn(
                        error -> error instanceof IllegalStateException,
                        0);
        System.out.println("predicate fallback = " + predicate.block());

        // F. Đối số fallback được tính ngay khi lắp pipeline.
        Mono<Integer> alreadySuccessful =
                Mono.just(42).onErrorReturn(buildFallback());
        System.out.println("success = " + alreadySuccessful.block());
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.OnErrorReturnDemo
```

**Stdout của chương trình**, không tính log riêng của Maven:

```text
source error = ArithmeticException
flux = [2, 4, -1]
mono valid = 12
mono invalid = -1
empty has value = false
empty default = -1
unmatched = IllegalStateException
predicate fallback = 0
fallback created
success = 42
```

Các điểm cần kiểm tra:

1. `doOnError` đặt **trước** `onErrorReturn` vẫn quan sát lỗi chia cho 0. Sau đó operator thay lỗi thành `-1` nên `collectList().block()` thành công và trả `[2, 4, -1]`.
2. `valid.block()` trả 12 vì không có lỗi. `invalid.block()` trả -1 vì `NumberFormatException` khớp overload đã chỉ định.
3. `Mono.empty()` kết thúc bình thường không có giá trị, nên `onErrorReturn` không kích hoạt; `hasElement().block()` là `false`. Trong khi đó `defaultIfEmpty(-1)` xử lý đúng tình huống không có phần tử.
4. `IllegalStateException` **không** khớp `IllegalArgumentException.class`, vì vậy được ném tại `block()` trong chương trình CLI và được nhánh `catch` in ra. Nó không bị biến thành 99.
5. Predicate nhận `Throwable` thực tế và trả `true` cho `IllegalStateException`, nên downstream nhận 0.
6. `buildFallback()` là lời gọi Java bình thường trong biểu thức `onErrorReturn(buildFallback())`. Nó chạy khi **tạo pipeline**, in `fallback created` dù `Mono.just(42)` sẽ thành công. Điều này cho thấy “giá trị thay thế cố định” đã được tính trước.

**Vì sao có `block()` trong ví dụ?** Đây là `main` của ứng dụng CLI nên ta cố ý chờ kết quả để kiểm tra stdout. Trong controller Spring WebFlux dùng I/O nonblocking, tránh `block()`; hãy trả `Mono`/`Flux` để framework quản lý subscription.

## 4. “Giá trị thay thế cố định” nghĩa là gì?

`onErrorReturn(fallbackValue)` nhận một **đối tượng `T` đã có**. Đối tượng hoặc kết quả biểu thức này được truyền vào operator tại thời điểm lắp chuỗi (assembly). Khi xảy ra lỗi phù hợp, Reactor dùng giá trị đó làm một tín hiệu `onNext`. Nó không gọi một supplier mới để tính giá trị dự phòng mỗi lần lỗi.

Ví dụ:

```java
int fallback = expensiveComputation();  // chạy ngay
Mono<Integer> result = source.onErrorReturn(fallback);
```

Đây là **đoạn minh họa**, `source` và `expensiveComputation()` do ứng dụng định nghĩa. Dù `source` không lỗi, việc tính fallback đã xảy ra. Tương tự, truyền `new ArrayList<>()` trực tiếp tạo danh sách ngay khi assembly; nếu các subscription dùng chung chuỗi, cùng object fallback đó có thể bị chia sẻ. Vì vậy, với `onErrorReturn`, **ưu tiên hằng số, record/value object bất biến hoặc giá trị không bị sửa**.

### 4.1. Khi giá trị dự phòng phải được tính tại thời điểm lỗi

Dùng `onErrorResume` để trả một publisher mới theo lỗi:

```java
Mono<String> result = source.onErrorResume(error ->
        Mono.fromSupplier(() -> createFallback(error)));
```

Đây là **đoạn minh họa**: `source` là `Mono<String>`, `createFallback(error)` trả `String` và do ứng dụng định nghĩa. Supplier được kích hoạt khi publisher dự phòng được subscribe sau một lỗi phù hợp. Nếu quá trình tạo fallback cũng thất bại, lỗi mới có thể đi xuống downstream. Với logic đơn giản, có thể dùng `onErrorResume(error -> Mono.just(createFallback(error)))`; biểu thức `createFallback(error)` chỉ chạy khi callback được gọi vì có lỗi, nhưng không được trì hoãn thêm bên trong callback.

**So sánh:**

| Mong muốn | Cách viết |
| --- | --- |
| Dùng một giá trị bất biến có sẵn khi lỗi | `onErrorReturn(FALLBACK)` |
| Chỉ thay lỗi timeout, giữ lỗi khác | `onErrorReturn(TimeoutException.class, FALLBACK)` |
| Chọn fallback khác nhau theo exception hoặc người dùng | `onErrorResume(error -> ...)` |
| Cần một lời gọi HTTP/database reactive khác khi lỗi | `onErrorResume(error -> backupService.fetch())` |
| Cần đổi một kết thúc rỗng thành giá trị | `defaultIfEmpty(FALLBACK)` |
| Cần đổi một kết thúc rỗng thành publisher mới | `switchIfEmpty(Mono.defer(() -> alternateSource()))` |

`onErrorReturn` **không** phải toán tử cache. Dù fallback là hằng số, nguồn ban đầu vẫn được đăng ký riêng theo semantics cold/hot của nó. Nếu một cold request luôn thất bại thì mỗi lần subscribe có thể vẫn thử request đó trước khi phát fallback.

### 4.2. Không thể dùng null làm fallback

Reactive Streams không cho phép `null` trong tín hiệu `onNext`. `onErrorReturn(null)` không phải cách biểu diễn “lỗi thì phát null” và có thể bị từ chối ngay khi lắp pipeline. Hãy dùng một giá trị hợp lệ, một DTO mang trạng thái (ví dụ `unavailable`), hoặc giữ lỗi để phía HTTP xử lý. Nếu một giá trị tùy chọn thực sự không tồn tại, `Mono.empty()` là cách biểu diễn khác với fallback.

### 4.3. Fallback và kiểu dữ liệu phải có ý nghĩa

Giả sử `Mono<Integer>` trả nhiệt độ hợp lệ. Chọn `-1` làm fallback có thể gây nhầm nếu -1 vẫn là một nhiệt độ có nghĩa. Tốt hơn là trả một kiểu biểu diễn trạng thái:

```java
record Reading(Integer value, boolean available) {}

Mono<Reading> reading = sensorService.read()
        .map(value -> new Reading(value, true))
        .onErrorReturn(new Reading(null, false));
```

Đây là **đoạn minh họa**, `sensorService.read()` trả `Mono<Integer>` do ứng dụng định nghĩa. `Reading` không phải giá trị `null` phát qua Reactor: đối tượng `Reading` khác null; trường `value` chỉ không có dữ liệu khi `available=false`. Thiết kế thực tế có thể dùng sealed types, `Optional` trong DTO hoặc cấu trúc lỗi riêng. Đừng coi fallback 0 hoặc false là giá trị “không có” nếu nó có thể trùng với dữ liệu nghiệp vụ hợp lệ.

## 5. Đặt onErrorReturn ở đâu trong chuỗi?

Operator chỉ xử lý lỗi được truyền từ **upstream của chính nó**. Vị trí quyết định lỗi nào sẽ được chặn, cũng như các giá trị trước lỗi có được quan sát không.

### 5.1. Đặt sau bước có thể lỗi

```java
Flux<Integer> safe = Flux.just("1", "bad")
        .map(Integer::parseInt)
        .onErrorReturn(-1);
```

Đoạn trên sẽ phát 1 rồi -1 và complete. `map` ở upstream phát lỗi nên handler nhìn thấy lỗi.

### 5.2. Đặt trước bước có thể lỗi: không bắt lỗi downstream

```java
Flux<Integer> notProtected = Flux.just(1, 0)
        .onErrorReturn(-1)
        .map(n -> 10 / n);
```

Đây là **đoạn minh họa**. `onErrorReturn` chỉ bảo vệ `Flux.just` ở phía trước nó (nguồn này không lỗi); khi `map` gặp 0 và ném `ArithmeticException` ở phía sau handler, handler phía trên không có cơ hội xử lý. Để xử lý lỗi chia cho 0, cần đưa `onErrorReturn(-1)` **sau** `map`.

### 5.3. Ghi log trước khi thay lỗi

```java
Mono<String> visible = remoteService.fetch()
        .doOnError(error -> metrics.record(error))
        .onErrorReturn("temporarily unavailable");
```

Đây là **đoạn minh họa**, cần định nghĩa `remoteService` và `metrics`. `doOnError` quan sát lỗi từ upstream nhưng không thay hoặc khôi phục lỗi. Nếu đặt `doOnError` **sau** `onErrorReturn`, callback sẽ **không thấy lỗi đã được thay** vì downstream chỉ nhận giá trị fallback và `onComplete`. Theo dõi lỗi trước khi recovery, với log/metrics đủ thông tin và tránh lộ dữ liệu nhạy cảm.

### 5.4. Vị trí so với retry: khác nhau hoàn toàn

```java
Mono<String> a = source.retry(2).onErrorReturn("offline");
Mono<String> b = source.onErrorReturn("offline").retry(2);
```

Đây là **đoạn minh họa**, `source` là một `Mono<String>` được ứng dụng định nghĩa.

- Ở `a`, `retry(2)` có thể đăng ký lại nguồn tối đa hai lần **ngoài lượt đầu** sau các lỗi. Khi vẫn lỗi sau các lần thử, `onErrorReturn` phát `"offline"`.
- Ở `b`, nếu lỗi đã được `onErrorReturn` thay bằng một giá trị bình thường, `retry(2)` ở downstream **không còn thấy lỗi đó** nên không kích hoạt retry vì lỗi ấy.

`retry` có thể làm lặp thao tác mạng, ghi dữ liệu hoặc side effect. Chỉ retry khi nguồn, idempotency, timeout và chính sách nghiệp vụ cho phép. Nếu lỗi không phù hợp để retry, đừng thêm retry chỉ vì đã có fallback.

## 6. So sánh onErrorReturn với các toán tử dễ nhầm

| Toán tử | Kích hoạt bởi | Kết quả điển hình |
| --- | --- | --- |
| `onErrorReturn(fallback)` | `onError` phù hợp | Phát **một giá trị cố định**, rồi complete. |
| `onErrorResume(error -> publisher)` | `onError` phù hợp | Chuyển sang publisher dự phòng (có thể 0, 1 hoặc nhiều giá trị). |
| `onErrorComplete()` | `onError` phù hợp | Chuyển lỗi thành `onComplete` **không phát thêm giá trị**. |
| `onErrorMap(error -> mapped)` | `onError` | Đổi loại/nội dung lỗi; downstream vẫn nhận `onError`. |
| `defaultIfEmpty(defaultValue)` | `onComplete` mà chưa có giá trị | Phát một giá trị nếu nguồn rỗng, **không** khôi phục lỗi. |
| `switchIfEmpty(alternate)` | `onComplete` mà chưa có giá trị | Chuyển sang publisher khác khi rỗng; không xử lý lỗi mặc định. |
| `retry(n)` | `onError` | Đăng ký lại nguồn khi được phép; không tự tạo giá trị thay thế. |
| `doOnError(action)` | `onError` | Quan sát lỗi để log/metrics; không tự thay tín hiệu lỗi. |

Một cách đọc đúng và ngắn:

```text
source = Mono.just(5)
  .onErrorReturn(-1)     -> 5

source = Mono.empty()
  .onErrorReturn(-1)     -> empty
  .defaultIfEmpty(-1)    -> -1

source = Mono.error(E)
  .onErrorReturn(-1)     -> -1 rồi complete
  .onErrorComplete()     -> complete rỗng
  .onErrorResume(e -> Mono.just(10)) -> 10 rồi complete
```

Những dòng trên là **sơ đồ hành vi cho từng trường hợp riêng**, không phải Java copy-paste độc lập. `onErrorReturn` không phù hợp với mọi lỗi; nếu bạn cần trả mã lỗi HTTP, ghi nhận lý do thất bại hoặc giữ khả năng retry, chọn operator thích hợp với hợp đồng xử lý.

## 7. Thận trọng với Flux đã phát một phần dữ liệu

Khi `Flux` phát hai giá trị rồi lỗi, `onErrorReturn` sẽ thêm fallback **sau** hai giá trị đó (nếu downstream còn demand). Điều này tạo một luồng trông có vẻ hoàn tất bình thường dù phần cuối có thể thiếu nhiều giá trị mong đợi.

Ví dụ dữ liệu nghiệp vụ:

```text
Dữ liệu mong muốn:  A, B, C, D
Đã phát:           A, B
Lỗi xảy ra trước:  C
onErrorReturn(?):  A, B, FALLBACK, onComplete
```

Nếu một màn hình chấp nhận một dòng cuối như `"stream interrupted"`, mẫu trên có thể được thiết kế như một loại event trạng thái riêng. Nhưng nếu client nghĩ mỗi phần tử đều là `Order` thực, việc chèn một `Order` giả ở cuối danh sách có thể dẫn đến báo cáo sai.

### 7.1. All-or-nothing bằng collectList()

```java
Mono<List<Item>> all = sourceFlux
        .collectList()
        .onErrorReturn(List.of());
```

Đây là **đoạn minh họa**, giả sử đã import `java.util.List` và ứng dụng định nghĩa `Item`, `sourceFlux`. `collectList()` chỉ phát danh sách khi nguồn hoàn tất thành công; nếu upstream phát một số Item rồi lỗi, danh sách chưa được phát, Mono lỗi và `onErrorReturn` cung cấp danh sách rỗng. Đây là hành vi **toàn bộ hoặc dự phòng**, khác với `sourceFlux.onErrorReturn(fallbackItem)` sẽ phát các Item đã đến trước lỗi.

Tuy nhiên, `List.of()` là fallback **rỗng** có thể bị hiểu là “thực sự không có đơn hàng”. Nếu lỗi kết nối và tình huống không có dữ liệu cần được phân biệt, hãy trả DTO chứa `available=false` hoặc giữ lỗi cho HTTP status thích hợp.

### 7.2. Backpressure và thời điểm phát fallback

`onErrorReturn` phát fallback qua `onNext`, do đó nó phải tôn trọng **demand** của downstream. Lỗi terminal của upstream không cần demand để báo, nhưng một phần tử fallback chỉ có thể được downstream nhận khi đủ nhu cầu. Nếu downstream chưa request hoặc đã cancel, đừng mặc định giá trị fallback sẽ được quan sát ngay. Ngoài ra, `onErrorReturn` không cung cấp cơ chế backpressure cho nguồn hot hoặc tự giới hạn kích thước buffer ở những operator khác.

### 7.3. Không biến lỗi per-item thành “tiếp tục nguồn cũ”

```java
Flux<Integer> parsed = Flux.just("10", "oops", "30")
        .map(Integer::parseInt)
        .onErrorReturn(-1);
```

Kết quả là `10, -1` rồi complete; `"30"` không còn được xử lý trong subscription này.

Nếu hợp đồng cho phép **bỏ riêng bản ghi sai và tiếp tục**, đưa xử lý lỗi vào mỗi phép parse:

```java
Flux<Integer> parsed = Flux.just("10", "oops", "30")
        .concatMap(raw ->
                Mono.fromCallable(() -> Integer.parseInt(raw))
                    .onErrorResume(NumberFormatException.class,
                            error -> Mono.empty()));
// Kết quả khi tiêu thụ: 10, 30 rồi complete.
```

Hai đoạn trên là **minh họa**, dùng Reactor và Java. `onErrorReturn` phù hợp để **thay toàn bộ tín hiệu lỗi** bằng giá trị dự phòng, không phải cơ chế skip từng bản ghi rồi tiếp tục upstream. Nếu cần giữ lý do từng lỗi để audit, trả một kiểu `ParseResult` chứa trạng thái thành công/thất bại thay vì xóa thông tin.

## 8. Áp dụng trong Spring WebFlux

Trong WebFlux controller, thông thường hãy **trả `Mono` hoặc `Flux`**. Hạ tầng WebFlux và reactive HTTP server sẽ tiêu thụ publisher và quyết định response, error, cancellation. Đừng gọi `subscribe()` hoặc `block()` trong handler chỉ để kích hoạt `onErrorReturn`.

### 8.1. Giá trị dự phòng an toàn cho dữ liệu tùy chọn

Giả sử endpoint hiển thị một nhãn thông tin phụ; không có nhãn vẫn có thể hiển thị giao diện:

```java
@GetMapping("/display-label")
public Mono<String> displayLabel() {
    return labelService.fetchCurrentLabel()
            .doOnError(error -> logLabelFailure(error))
            .onErrorReturn("temporarily unavailable");
}
```

Đây là **đoạn minh họa trong một Spring controller**, cần import `@GetMapping` và ứng dụng định nghĩa `labelService`/`logLabelFailure`. Nếu upstream lỗi, HTTP handler vẫn có một giá trị `String` hợp lệ để encode. Theo mặc định, response có thể là HTTP **200 OK** vì lỗi đã được biến thành giá trị thành công. Điều này chỉ hợp lý khi endpoint và client **chấp nhận** việc hiển thị giá trị dự phòng.

Nếu endpoint thực chất là API thanh toán, cấp quyền truy cập, báo cáo tiền hoặc quyết định đặt hàng, không nên trả một “giá trị thành công” giả để che giấu lỗi. Với thông tin nhạy cảm, fallback Boolean `true` có thể trở thành **fail-open** không an toàn. Chỉ dùng dự phòng khi semantics và chính sách an toàn đã được xác định.

### 8.2. Thay lỗi bằng giá trị có điều kiện

```java
@GetMapping("/availability")
public Mono<String> availability() {
    return stockService.check()
            .onErrorReturn(
                    java.util.concurrent.TimeoutException.class,
                    "unknown");
}
```

Đây là **đoạn minh họa**: `stockService.check()` trả `Mono<String>`. Timeout được coi là trạng thái `unknown`, không phải `in-stock` hay `out-of-stock`. Lỗi khác vẫn được báo theo đường lỗi của WebFlux. Cần kiểm tra exception thật mà service phát: một lỗi HTTP client có thể được bọc trong một exception khác thay vì chính `TimeoutException`; nếu không khớp loại, operator không thay lỗi.

### 8.3. Khi cần HTTP status khác 200

Nếu việc không truy xuất được dữ liệu là lỗi dịch vụ, giữ response semantic bằng HTTP status:

```java
@GetMapping("/catalog")
public Mono<ResponseEntity<List<String>>> catalog() {
    return catalogService.streamNames()
            .collectList()
            .map(names -> ResponseEntity.ok(names))
            .onErrorResume(
                    java.util.concurrent.TimeoutException.class,
                    error -> Mono.just(
                            ResponseEntity
                                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                                    .body(java.util.Collections.<String>emptyList())));
}
```

Đây là **đoạn minh họa trong controller**, cần import Spring `ResponseEntity`, `HttpStatus`, `Mono`, `List` và định nghĩa `catalogService`. Ta dùng `onErrorResume` thay vì `onErrorReturn(List.of())` vì mục tiêu là thay cả **status lẫn body** khi timeout. HTTP 503 báo rõ lỗi dịch vụ; body rỗng chỉ là định dạng đi kèm, không phải kết quả kinh doanh “không có sản phẩm”.

Lưu ý với `Flux` streaming đã commit response: nếu lỗi đến sau khi server gửi header/body, không thể tùy ý chuyển status HTTP thành 503. Lựa chọn fallback, chuyển sang response gói toàn bộ hay định nghĩa event báo lỗi phải xét tính chất streaming và hợp đồng của client.

### 8.4. Empty và not found trong API

`repository.findById(id)` thường trả `Mono.empty()` khi không tìm thấy bản ghi; `onErrorReturn` **không** biến trường hợp đó thành giá trị dự phòng hay HTTP 404.

```java
return repository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Item not found")));
```

Đây là **đoạn minh họa**, giả sử `repository` và `id` đã có. `switchIfEmpty` xử lý việc thiếu phần tử, còn `onErrorReturn` xử lý lỗi upstream. Không gộp trường hợp “không tìm thấy” với “server/database bị lỗi” nếu API phải phân biệt chúng.

## 9. Chọn lỗi nào được thay: thực hành an toàn và dễ bảo trì

### 9.1. Bắt tất cả lỗi có thể che giấu lỗi lập trình

`source.onErrorReturn(FALLBACK)` sẽ bắt cả lỗi ngoài dự kiến như `NullPointerException` hay `IllegalStateException` từ bug trong pipeline. Điều này có thể khiến lỗi logic bị che khuất trong production. Với một fallback nghiệp vụ, thường nên chỉ định **loại lỗi được phép khôi phục**:

```java
Mono<String> response = service.fetch()
        .onErrorReturn(
                java.util.concurrent.TimeoutException.class,
                "unavailable");
```

Đoạn này **minh họa**, yêu cầu `service.fetch()` trả `Mono<String>`. Không tự mở rộng whitelist sang lỗi xác thực, lỗi bảo mật hoặc integrity failure. Trường hợp lỗi bị bọc cần kiểm tra cấu trúc exception và mapping của service, không chuyển bừa tất cả lỗi thành fallback.

### 9.2. Retry rồi fallback hay fallback ngay?

Nếu lỗi mạng tạm thời có thể thử lại:

```java
Mono<String> result = service.fetch()
        .retry(2)
        .onErrorReturn("temporarily unavailable");
```

Đây là đoạn **minh họa**: đúng khi thử lại an toàn, có giới hạn và không làm lặp side effect nguy hiểm. Hai lần retry cộng với lần đầu có thể thành **ba subscription** tới một cold source. Với HTTP POST/ghi database, cần đánh giá idempotency trước. Khi cần giới hạn loại lỗi và backoff, có thể dùng `retryWhen(Retry.backoff(...).filter(...))` cùng timeout/circuit breaker theo chính sách; ví dụ đơn giản ở trên chỉ nhằm minh họa thứ tự toán tử.

### 9.3. Quan sát sự cố trước khi recover

Nên đo lỗi đã phục hồi thay vì để metric chỉ nhìn thấy downstream complete:

```java
return remoteService.fetch()
        .doOnError(error -> {
            logger.warn("Remote source failed", error);
            metrics.incrementFallbackCandidate();
        })
        .onErrorReturn("unavailable");
```

Đây là **đoạn minh họa**, các biến do ứng dụng sở hữu. Đặt `doOnError` trước handler để thống kê lỗi thật. Nếu metrics cần thống kê **chỉ những lỗi đã được khôi phục**, dùng overload lọc phù hợp và metric có cùng điều kiện hoặc một `onErrorResume` có callback khi recovery xảy ra; `doOnError` đứng trước handler có thể đếm cả lỗi không khớp.

### 9.4. Giá trị fallback phải nhất quán với domain

| Domain | Fallback có thể hợp lý | Fallback nguy hiểm |
| --- | --- | --- |
| Nhãn UI phụ | `"temporarily unavailable"` | Chuỗi trống bị hiểu là nhãn thật. |
| Gợi ý nội dung không thiết yếu | Danh sách rỗng **nếu giao diện phân biệt trạng thái lỗi** | Danh sách rỗng ngụ ý chắc chắn không có kết quả. |
| Cảm biến/đo lường | DTO `available=false` | Số 0 nếu 0 là số đo hợp lệ. |
| Quyết định phân quyền | Thường giữ lỗi hoặc fail closed theo chính sách rõ | `true` khi service kiểm tra quyền lỗi. |
| Thanh toán, tồn kho, giao dịch | Báo lỗi có thể xử lý lại và giữ tính toàn vẹn | Giá trị “đã thành công” giả, khiến client bỏ qua thất bại. |

## 10. Kiểm thử hành vi, không chỉ giá trị cuối

Dùng `reactor-test` để xác nhận cả dữ liệu và tín hiệu kết thúc. Thêm dependency test vào `pom.xml` khi viết unit test:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <version>3.8.8</version>
    <scope>test</scope>
</dependency>
```

Các đoạn **minh họa trong phương thức test**, cần import `reactor.test.StepVerifier` và `reactor.core.publisher.*`:

```java
StepVerifier.create(
        Flux.just(6, 3, 0, 2)
            .map(n -> 12 / n)
            .onErrorReturn(-1))
    .expectNext(2, 4, -1)
    .verifyComplete();

StepVerifier.create(
        Mono.<Integer>empty().onErrorReturn(-1))
    .verifyComplete();

StepVerifier.create(
        Mono.<Integer>error(new IllegalArgumentException("bad"))
            .onErrorReturn(IllegalStateException.class, 99))
    .expectError(IllegalArgumentException.class)
    .verify();
```

Ba kiểm thử phân biệt rất rõ:

1. Sau lỗi trong Flux, một fallback được phát rồi complete.
2. Mono rỗng không hề kích hoạt fallback.
3. Lỗi không khớp loại được giữ dưới dạng `onError`.

Nếu kiểm thử publisher có retry, hãy đo số subscription bằng bộ đếm hoặc `StepVerifier` kết hợp publisher giả lập. Nếu muốn kiểm thử lỗi trong Spring WebFlux, dùng `WebTestClient` để kiểm tra **status và body**; việc `block()` trả đúng fallback trong CLI chưa đủ chứng minh endpoint HTTP có semantics mong muốn.

## 11. Các lỗi thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `onErrorReturn` để xử lý `Mono.empty()` | Fallback không chạy, publisher vẫn rỗng | Dùng `defaultIfEmpty`/`switchIfEmpty`. |
| Nghĩ `Flux.onErrorReturn` tiếp tục các phần tử sau lỗi | Các phần tử còn lại của upstream không được xử lý | Dùng phục hồi theo từng item nếu cần continue; hoặc retry có chủ đích. |
| Dùng fallback không cùng kiểu dữ liệu | Code không biên dịch hoặc semantics sai | Chọn cùng `T` hoặc chuyển dữ liệu sang DTO hợp lệ. |
| Truyền `null` làm fallback | Reactor không cho phép `null` trong `onNext` | Dùng giá trị hợp lệ, publisher rỗng hoặc kết quả trạng thái rõ ràng. |
| Tạo fallback bằng hàm đắt tiền ngay trong tham số | Hàm được gọi khi assembly dù nguồn không lỗi | Với fallback động, dùng `onErrorResume`/`Mono.fromSupplier`. |
| Dùng đối tượng mutable làm fallback trên publisher dùng chung | Các subscription có thể chia sẻ và sửa cùng object | Ưu tiên fallback bất biến hoặc tạo mới khi khôi phục. |
| Đặt `onErrorReturn` trước operator gây lỗi | Không bắt được lỗi ở downstream | Đặt sau đoạn cần bảo vệ. |
| Đặt `retry` sau `onErrorReturn` rồi kỳ vọng retry | Lỗi đã biến thành complete nên không còn lỗi để retry | Xác định thứ tự và tính an toàn của retry. |
| Bắt toàn bộ `Throwable` rồi trả “thành công” | Có thể che lỗi lập trình, lỗi bảo mật và lỗi dữ liệu | Giới hạn loại lỗi, giữ observability, chọn status hợp lệ. |
| Đặt `doOnError` sau fallback rồi chờ thấy lỗi gốc | Callback không thấy lỗi đã được chuyển thành giá trị | Ghi log/metrics trước recovery. |
| Xem fallback 0 hoặc false là “không có dữ liệu” | Lẫn giá trị hợp lệ với trạng thái lỗi | Trả DTO có trạng thái hoặc giữ error. |
| Dùng `block()` trong controller WebFlux để lấy fallback | Có thể chặn event-loop, mất lợi ích reactive | Trả publisher để WebFlux tiêu thụ. |
| Trả HTTP 200 khi dịch vụ quan trọng đang lỗi | Client có thể hiểu nhầm thao tác thành công | Giữ error hoặc trả ResponseEntity với HTTP status thích hợp. |
| Dùng fallback trong stream đã phát một phần như dữ liệu thật | Trộn dữ liệu đúng với phần tử giả, báo cáo sai | Định nghĩa event lỗi riêng hoặc xử lý all-or-nothing. |

## 12. Tự kiểm tra

**Câu 1.** `Mono.just(5).onErrorReturn(0)` cho kết quả gì?  
**Đáp án:** Phát `5` rồi complete. Không có lỗi nên không dùng 0.

**Câu 2.** `Mono.<Integer>empty().onErrorReturn(0)` có phát 0 không?  
**Đáp án:** Không. Publisher rỗng hoàn tất bình thường. `defaultIfEmpty(0)` mới phát 0.

**Câu 3.** `Flux.just(4, 2, 0, 1).map(n -> 8 / n).onErrorReturn(-1)` phát những gì?  
**Đáp án:** `2, 4, -1` rồi complete. Phần tử `1` sau `0` không được xử lý vì upstream đã lỗi tại `0`.

**Câu 4.** `Mono.error(new IllegalStateException()).onErrorReturn(IllegalArgumentException.class, "N/A")` phát `"N/A"` không?  
**Đáp án:** Không, nếu kiểu của chuỗi được khai báo tương thích; vì exception là `IllegalStateException`, không phải `IllegalArgumentException`, lỗi vẫn truyền xuống. Trong Java thực tế cần khai báo generic rõ để khớp kiểu fallback; ví dụ `Mono.<String>error(...)`.

**Câu 5.** Tại sao `onErrorReturn(createFallback())` có thể gọi `createFallback()` khi nguồn chưa bao giờ lỗi?  
**Đáp án:** Java tính đối số phương thức ngay khi tạo chuỗi. `onErrorReturn` nhận giá trị đã tạo, không nhận supplier. Nếu cần tính có điều kiện, dùng `onErrorResume`.

**Câu 6.** `source.retry(1).onErrorReturn("offline")` khác `source.onErrorReturn("offline").retry(1)` ở đâu?  
**Đáp án:** Cách đầu cho một lần retry trước khi dùng fallback nếu vẫn lỗi; cách thứ hai đã chuyển lỗi thành thành công nên retry không thấy lỗi khớp để kích hoạt.

**Câu 7.** Vì sao không nên dùng `onErrorReturn(true)` khi service kiểm tra quyền bị lỗi?  
**Đáp án:** Nó có thể cấp quyền khi chưa xác minh được (fail-open). Quyết định truy cập cần bảo đảm an toàn theo chính sách; lỗi hệ thống không mặc nhiên là quyền hợp lệ.

**Câu 8.** Với endpoint trả `Flux<Order>`, lỗi xảy ra sau khi đã gửi hai order. `onErrorReturn(fallbackOrder)` có nghĩa là client nhận “danh sách đầy đủ” không?  
**Đáp án:** Không. Nó chỉ thay lỗi bằng một phần tử dự phòng rồi complete; các order chưa được phát vẫn thiếu. Client cần phân biệt trạng thái lỗi hoặc API cần trả kết quả toàn bộ sau khi có đủ dữ liệu.

## Ghi nhớ

- **`onErrorReturn(fallback)` chỉ kích hoạt khi upstream phát `onError` phù hợp.** Nó phát đúng **một giá trị thay thế cố định** rồi hoàn tất thành công.
- **Empty khác Error:** không có giá trị thì dùng `defaultIfEmpty`/`switchIfEmpty`; nguồn lỗi thì dùng các operator nhóm `onError...` hoặc `retry` theo chính sách.
- Với `Flux` đã phát vài phần tử, `onErrorReturn` **không quay lại nguồn** để tiếp tục các phần tử sau lỗi.
- Fallback được tạo **trước khi lỗi xảy ra** nếu biểu thức đối số được tính ngay; ưu tiên giá trị bất biến và có semantics nghiệp vụ rõ ràng. Nếu phải tính động theo lỗi, dùng `onErrorResume`.
- Giới hạn phạm vi lỗi được thay thế, log/metrics trước recovery và không che lỗi bảo mật/giao dịch. Trong WebFlux, trả publisher để hạ tầng HTTP tiêu thụ và chọn status/body phù hợp.

### Tài liệu tham khảo

1. [Project Reactor – Flux API: onErrorReturn](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html) – overload giá trị, loại exception và predicate.
2. [Project Reactor – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) – error recovery cho Mono.
3. [Project Reactor – Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) – onErrorReturn, onErrorResume, onErrorComplete và đặc tính lỗi terminal.
4. [Project Reactor – Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html) – demand khi phát phần tử.
5. [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm) – hợp đồng onNext/onError/onComplete và Subscription.
6. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) – pipeline HTTP reactive, tiêu thụ response và error handling.
