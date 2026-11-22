# Kiểm tra Mono, Flux và dữ liệu nhiều phần tử trong Spring WebFlux

Trong **Spring WebFlux**, một service thường trả `Mono<T>` hoặc `Flux<T>` thay vì trả trực tiếp một object hay một `List<T>`. Vì vậy, một test đúng không chỉ hỏi “giá trị là gì?” mà còn phải hỏi **khi subscribe, publisher phát bao nhiêu phần tử, theo thứ tự nào, có hoàn tất hay phát lỗi, và có tuân thủ nhu cầu nhận dữ liệu (backpressure) hay không**.

Công cụ chuyên dụng để kiểm tra các hợp đồng đó là **`StepVerifier`** thuộc thư viện `reactor-test`. StepVerifier tạo subscriber kiểm thử, chủ động đặt kỳ vọng về các tín hiệu reactive và chỉ thực sự xác minh khi gọi `verify()` hoặc terminal helper như `verifyComplete()`.

Bài này tập trung vào **kiểm tra `Mono`, `Flux` và dữ liệu nhiều phần tử** với ví dụ Java 17+ chạy được trong dự án Spring Boot/WebFlux. Các phần giải thích gồm giá trị đơn/luồng rỗng/lỗi, thứ tự và số lượng, `Mono<List<T>>` so với `Flux<T>`, batching, thời gian ảo, backpressure và giới hạn của test chỉ ở tầng Reactor so với HTTP qua `WebTestClient`.

## 1. Cơ chế: test tín hiệu, không so sánh publisher object

Reactor dựa trên mô hình Reactive Streams: publisher phát tín hiệu cho subscriber sau khi có subscription.

```text
Subscriber                     Publisher
    |                              |
    |---------- subscribe -------->|
    |<--------- onSubscribe -------|
    |---------- request(n) ------->|
    |<--------- onNext(A) ---------|
    |<--------- onNext(B) ---------|
    |<--------- onComplete --------|
    |
    +-- hoặc nhận onError(exception) thay onComplete
    +-- hoặc cancel subscription trước khi nguồn tự kết thúc
```

Một sequence tuân thủ đặc tả kết thúc với **`onComplete` hoặc `onError`**, không có cả hai. Sau terminal signal sẽ không còn `onNext`. Trước khi subscribe, nhiều publisher được tạo theo kiểu **lazy**, chưa thực hiện logic mà bạn định kiểm tra.

| Publisher | Số `onNext` | Terminal signal | Ý nghĩa |
| --- | ---: | --- | --- |
| `Mono.just("A")` | 1 | complete | Có một kết quả |
| `Mono.empty()` | 0 | complete | Không có kết quả, không phải lỗi |
| `Mono.error(ex)` | 0 | error | Kết thúc thất bại |
| `Flux.just("A","B","C")` | 3 | complete | Có nhiều phần tử |
| `Flux.empty()` | 0 | complete | Danh sách luồng không có phần tử |
| `Flux.concat(Flux.just(1,2), Flux.error(ex))` | 2 | error | Phát dữ liệu rồi lỗi |
| `Flux.never()` | 0 | không tự hoàn tất | Cần giới hạn/cancel để test không treo |
| `Mono<List<String>>` phát `List.of("A","B")` | **1** | complete | Một phần tử là cả danh sách |

**`Flux<T>` có thể phát 0, 1, nhiều phần tử hoặc vô hạn**; tên Flux không buộc phải luôn có từ hai phần tử. **`Mono<T>` phát tối đa một phần tử**, kể cả trường hợp hoàn tất rỗng. Reactor không cho phép `null` làm giá trị `onNext`: `Mono.just(null)` không phải cách biểu diễn kết quả vắng mặt.

So sánh hai publisher trực tiếp:

```java
assertEquals(Mono.just("A"), someService.find("A"));
```

không chứng minh chuỗi phát đúng `"A"`. Đây là so sánh **hai object mô tả publisher** chứ không xác nhận tín hiệu sau subscribe. Test phù hợp:

```java
StepVerifier.create(someService.find("A"))
        .expectNext("A")
        .verifyComplete();
```

Hai đoạn chỉ minh họa cách dùng: `someService.find("A")` ở đây được giả định trả `Mono<String>`. Các ví dụ runnable ở phần dưới có mã production cụ thể và imports đầy đủ.

## 2. Những API StepVerifier cần biết

Mẫu cơ bản:

```java
StepVerifier.create(publisher)
        .expectNext(expectedFirst, expectedSecond)
        .verifyComplete();
```

`StepVerifier.create(...)` thiết lập script kiểm tra. Khi gọi `verifyComplete()`, StepVerifier subscribe và yêu cầu lần lượt hai `onNext` có đúng nội dung/thứ tự, rồi nhận `onComplete`. Phần tử bị thiếu/thừa, sai giá trị, tín hiệu lỗi hoặc không hoàn tất theo kịch bản sẽ khiến verification thất bại.

| API | Mục đích | Giới hạn cần nhớ |
| --- | --- | --- |
| `expectNext(a,b)` | Kiểm tra từng giá trị đúng thứ tự | Không phù hợp nếu hợp đồng không bảo đảm thứ tự |
| `expectNextSequence(iterable)` | Kiểm tra chuỗi giá trị theo Iterable | Cũng yêu cầu đúng thứ tự |
| `expectNextCount(n)` | Xác minh có n phần tử tiếp theo | **Không kiểm tra nội dung** của n phần tử |
| `assertNext(item -> ...)` | Chạy assertion chi tiết trên một phần tử | Mỗi `assertNext` tiêu thụ một `onNext` |
| `expectNextMatches(predicate)` | Phần tử kế tiếp thỏa điều kiện | Chỉ xác minh predicate đã viết |
| `recordWith(...).consumeRecordedWith(...)` | Ghi các `onNext` và assert tập dữ liệu | Có chi phí bộ nhớ |
| `verifyComplete()` | Kiểm tra kết thúc bằng complete sau các giá trị kỳ vọng | Không dùng cho luồng vô hạn không kết thúc |
| `expectErrorMatches(...).verify()` | Kiểm tra kết thúc bằng lỗi phù hợp | Sau error không có complete |
| `thenRequest(n)` | Tăng lượng data subscriber được phép nhận | Dùng với source tôn trọng backpressure |
| `thenCancel()` | Hủy subscription | Không có nghĩa source đã tự hoàn tất |
| `withVirtualTime(() -> publisher)` | Kiểm thử timer/delay qua đồng hồ ảo | Phải tạo publisher trong supplier |

Đừng quên terminal verification: nếu chỉ viết `StepVerifier.create(publisher).expectNext(...)` rồi kết thúc method, bạn **chưa thực thi lời khẳng định**. Với test lỗi, ví dụ:

```java
StepVerifier.create(
                Mono.error(new IllegalStateException("down")))
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "down".equals(error.getMessage()))
        .verify();
```

Test trên đòi `onError`, không đòi `onComplete`. Không dùng `assertThrows` quanh lời gọi trả `Mono.error` nếu exception được gửi **bất đồng bộ sau subscribe**, không ném đồng bộ từ Java method.

## 3. Cài đặt JUnit Jupiter và reactor-test

Trong dự án Spring Boot có Gradle, dependency management và plugin phù hợp, phần cần thiết trong `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình bổ sung**, không phải toàn bộ file `build.gradle` có thể dùng độc lập. Starter WebFlux cung cấp Reactor Core, còn `reactor-test` cung cấp `StepVerifier`. Project không dùng starter WebFlux vẫn có thể test Reactor nếu cung cấp `reactor-core` và `reactor-test` phiên bản tương thích trên đúng classpath.

Imports thường gặp:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
```

Nếu chỉ cần kiểm thử pipeline Java thuần thì **không cần `@SpringBootTest`, `@WebFluxTest`, HTTP server hay database**. Spring Boot chỉ trở thành một phần của test khi bạn cần xác minh bean wiring, WebFlux HTTP infrastructure, security, persistence hoặc một tích hợp khác.

## 4. Ví dụ production Java 17+: danh mục SKU

Để nhìn thấy rõ nhiều dạng publisher, ta xây một class có dữ liệu cố định:

| Vị trí | SKU | Đơn vị |
| ---: | --- | ---: |
| 1 | `JAVA-1` | 2 |
| 2 | `JAVA-2` | 5 |
| 3 | `SPRING-1` | 7 |
| 4 | `JAVA-3` | 0 |

Chọn prefix `JAVA` trả ba SKU theo thứ tự nguồn: `JAVA-1, JAVA-2, JAVA-3`. Chọn prefix `NO` trả Flux rỗng. Trong ví dụ, prefix hợp lệ chỉ gồm một hoặc nhiều chữ in hoa ASCII `A–Z`.

Các phương thức:

- `find(code)`: `Mono<Sku>` có một SKU, rỗng nếu không tìm thấy hoặc onError nếu code blank.
- `list(prefix)`: `Flux<Sku>` có 0 hoặc nhiều SKU; prefix không hợp lệ trả `Flux.error(...)`.
- `count(prefix)`: `Mono<Long>` đếm số SKU phù hợp.
- `collect(prefix)`: `Mono<List<Sku>>` phát một danh sách.
- `batches(prefix,size)`: `Flux<List<Sku>>` phát một hoặc nhiều danh sách theo từng batch.

Cấu trúc file:

```text
src/
├── main/java/example/testing/webflux/
│   ├── SkuRule.java
│   ├── SkuRuleDemo.java
│   └── SkuCatalog.java
└── test/java/example/testing/webflux/
    ├── SkuCatalogTest.java
    └── StepVerifierAdvancedTest.java
```

### 4.1. Quy tắc Java thuần: SkuRule.java

Tạo `src/main/java/example/testing/webflux/SkuRule.java`:

```java
package example.testing.webflux;

public final class SkuRule {
    private SkuRule() {
    }

    public static boolean validPrefix(String prefix) {
        return prefix != null
                && prefix.matches("[A-Z]+");
    }
}
```

Tách rule khỏi reactive pipeline để kiểm tra dễ hơn. Regex `[A-Z]+` chỉ chấp nhận chuỗi ít nhất một chữ in hoa, không chấp nhận chữ thường, số, khoảng trắng hoặc null. Đây là **quy tắc đặt cho ví dụ**, không đại diện cho mọi chuẩn đặt mã SKU.

### 4.2. Dữ liệu Reactor: SkuCatalog.java

Tạo `src/main/java/example/testing/webflux/SkuCatalog.java`:

```java
package example.testing.webflux;

import java.util.List;
import java.util.Objects;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class SkuCatalog {
    private final List<Sku> source;

    public SkuCatalog(List<Sku> source) {
        this.source = List.copyOf(
                Objects.requireNonNull(source, "source"));
    }

    public Mono<Sku> find(String code) {
        if (code == null || code.isBlank()) {
            return Mono.error(new IllegalArgumentException(
                    "code must not be blank"));
        }

        return Flux.fromIterable(source)
                .filter(sku -> sku.code().equals(code))
                .next();
    }

    public Flux<Sku> list(String prefix) {
        if (!SkuRule.validPrefix(prefix)) {
            return Flux.error(new IllegalArgumentException(
                    "prefix must use A-Z"));
        }

        return Flux.fromIterable(source)
                .filter(sku -> sku.code().startsWith(prefix));
    }

    public Mono<Long> count(String prefix) {
        return list(prefix).count();
    }

    public Mono<List<Sku>> collect(String prefix) {
        return list(prefix).collectList();
    }

    public Flux<List<Sku>> batches(
            String prefix, int batchSize) {
        if (batchSize <= 0) {
            return Flux.error(new IllegalArgumentException(
                    "batchSize must be positive"));
        }

        return list(prefix).buffer(batchSize);
    }
}

record Sku(String code, int units) {
}
```

Mã trên có **một top-level public class** trùng tên file và một record package-private, hợp lệ với Java 17. Các test sẽ nằm cùng package để sử dụng `Sku`. `Sku` là record nên có value-based `equals/hashCode`, thuận tiện cho `expectNext(new Sku(...))`.

Giải thích một số đặc điểm:

- `List.copyOf(...)` giữ một danh sách không thể sửa qua reference của service. Test sử dụng `List.of(...)` và các `Sku` bất biến để data mỗi lần subscribe có tính quyết định.
- `Flux.fromIterable(source)` phát từng SKU theo thứ tự iteration của List. `filter(...)` giữ thứ tự của các phần tử còn lại.
- `next()` chọn phần tử đầu tiên thành `Mono<Sku>`; nếu không có phần tử, Mono hoàn tất rỗng.
- `Mono.error(...)` và `Flux.error(...)` gửi lỗi khi subscribe, khác với việc `throw` ngay trong Java method.
- `count()` trả một `Long` duy nhất, kể cả `0L` khi Flux nguồn rỗng.
- `collectList()` trả một `List` duy nhất, kể cả khi List rỗng.
- `buffer(2)` của một luồng 3 phần tử phát hai `List`: danh sách 2 phần tử và danh sách 1 phần tử cuối.

### 4.3. Chạy kiểm chứng quy tắc bằng javac/java

Tạo `src/main/java/example/testing/webflux/SkuRuleDemo.java`:

```java
package example.testing.webflux;

public class SkuRuleDemo {
    public static void main(String[] args) {
        System.out.println(SkuRule.validPrefix("JAVA"));
        System.out.println(SkuRule.validPrefix("java"));
        System.out.println(SkuRule.validPrefix(null));
        System.out.println(SkuRule.validPrefix("JAVA2"));
    }
}
```

Biên dịch/chạy từ thư mục gốc project với JDK 17+:

```bash
javac -d out src/main/java/example/testing/webflux/SkuRule.java src/main/java/example/testing/webflux/SkuRuleDemo.java
java -cp out example.testing.webflux.SkuRuleDemo
```

Stdout **chính xác**:

```text
true
false
false
false
```

Lệnh `javac` ở đây **chỉ chứng minh rule Java thuần**, không chạy `SkuCatalog` hay StepVerifier vì hai thành phần kia cần Reactor dependencies từ build. Các test Reactor có thể chạy đầy đủ bằng Gradle ở mục sau.

## 5. Bộ JUnit test đầy đủ cho Mono, Flux và collection

Tạo `src/test/java/example/testing/webflux/SkuCatalogTest.java`:

```java
package example.testing.webflux;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SkuCatalogTest {
    private static final Sku FIRST =
            new Sku("JAVA-1", 2);
    private static final Sku SECOND =
            new Sku("JAVA-2", 5);
    private static final Sku OTHER =
            new Sku("SPRING-1", 7);
    private static final Sku THIRD =
            new Sku("JAVA-3", 0);

    private SkuCatalog catalog;

    @BeforeEach
    void setUp() {
        catalog = new SkuCatalog(
                List.of(FIRST, SECOND, OTHER, THIRD));
    }

    @Test
    void monoEmitsOneSkuThenCompletes() {
        StepVerifier.create(catalog.find("JAVA-2"))
                .expectNext(SECOND)
                .verifyComplete();
    }

    @Test
    void missingSkuYieldsEmptyMono() {
        StepVerifier.create(catalog.find("MISSING"))
                .verifyComplete();
    }

    @Test
    void invalidSkuEmitsErrorInsteadOfValue() {
        StepVerifier.create(catalog.find(" "))
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "code must not be blank"
                            .equals(error.getMessage()))
                .verify();
    }

    @Test
    void fluxEmitsThreeSkusInSourceOrder() {
        StepVerifier.create(catalog.list("JAVA"))
                .expectNext(FIRST, SECOND, THIRD)
                .verifyComplete();
    }

    @Test
    void fluxWithoutMatchesCompletesEmpty() {
        StepVerifier.create(catalog.list("NO"))
                .verifyComplete();
    }

    @Test
    void invalidPrefixIsReactiveError() {
        StepVerifier.create(catalog.list("java"))
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "prefix must use A-Z"
                            .equals(error.getMessage()))
                .verify();
    }

    @Test
    void assertsFirstElementAndCountsTheRest() {
        StepVerifier.create(catalog.list("JAVA"))
                .assertNext(sku -> {
                    assertEquals("JAVA-1", sku.code());
                    assertEquals(2, sku.units());
                })
                .expectNextCount(2)
                .verifyComplete();
    }

    @Test
    void collectListEmitsOneListOfThreeItems() {
        StepVerifier.create(catalog.collect("JAVA"))
                .expectNext(List.of(FIRST, SECOND, THIRD))
                .verifyComplete();
    }

    @Test
    void collectEmptyFluxStillEmitsAnEmptyList() {
        StepVerifier.create(catalog.collect("NO"))
                .expectNext(List.of())
                .verifyComplete();
    }

    @Test
    void countEmitsOneLongValue() {
        StepVerifier.create(catalog.count("JAVA"))
                .expectNext(3L)
                .verifyComplete();
    }

    @Test
    void batchesEmitTwoLists() {
        StepVerifier.create(catalog.batches("JAVA", 2))
                .expectNext(
                        List.of(FIRST, SECOND),
                        List.of(THIRD))
                .verifyComplete();
    }

    @Test
    void onErrorResumeReplacesErrorWithFallbackValue() {
        Flux<Sku> recovered = catalog.list("bad")
                .onErrorResume(IllegalArgumentException.class,
                        error -> Flux.just(new Sku("FALLBACK", 0)));

        StepVerifier.create(recovered)
                .expectNext(new Sku("FALLBACK", 0))
                .verifyComplete();
    }

    @Test
    void coldFluxCanBeSubscribedTwice() {
        Flux<Sku> flux = catalog.list("JAVA");

        StepVerifier.create(flux)
                .expectNext(FIRST, SECOND, THIRD)
                .verifyComplete();

        StepVerifier.create(flux)
                .expectNext(FIRST, SECOND, THIRD)
                .verifyComplete();
    }
}
```

**Class trên có 13 method test** (đếm theo từng `@Test`). Mỗi method khai báo kỳ vọng rồi kích hoạt verification. Không có Spring context, DB hoặc WebFlux HTTP server. Các trường hợp quan trọng được bảo vệ:

- **Mono có một giá trị:** `expectNext(SECOND).verifyComplete()`.
- **Mono không tìm thấy:** `verifyComplete()` không có `expectNext`, nghĩa là rỗng và thành công.
- **Mono lỗi:** `expectErrorMatches(...).verify()`, không bắt exception đồng bộ từ lời gọi `find(...)`.
- **Flux ba phần tử:** `expectNext(FIRST, SECOND, THIRD)` kiểm tra chính xác nội dung và thứ tự; `verifyComplete()` cũng phát hiện phần tử thừa.
- **Flux rỗng:** không có `onNext`, nhưng có `onComplete`.
- **Assertion chi tiết:** `assertNext` kiểm tra fields phần tử đầu; `expectNextCount(2)` chỉ kiểm tra **số lượng hai phần tử tiếp theo**, không chứng minh chúng có giá trị gì.
- **`Mono<List<Sku>>`:** một `onNext` là một List chứa ba Sku. Không được kỳ vọng ba `Sku` riêng.
- **List rỗng:** `collectList()` trên Flux rỗng vẫn phát một `List.of()` trước khi complete.
- **Count:** `count("JAVA")` phát một `Long` `3L`, không phải ba lần `onNext`.
- **Batches:** `Flux<List<Sku>>` phát hai Lists, một có 2 và một có 1 phần tử.
- **Recovery:** `onErrorResume` biến error thành fallback value + normal completion; downstream không còn nhìn thấy lỗi gốc.
- **Cold stream:** source từ List có thể được subscribe lại và phát dữ liệu từ đầu. Không giả định mọi publisher hot/shared làm được điều này.

**Điều không được suy diễn:** một test gọi `SkuCatalog.list(...)` trực tiếp không chứng minh endpoint HTTP trả JSON array hay status đúng; cần kiểm tra riêng bằng WebTestClient nếu hợp đồng bao gồm HTTP.

## 6. Đọc đúng Mono<List<T>>, Flux<T>, Flux<List<T>>

Đây là điểm then chốt khi làm việc với **dữ liệu nhiều phần tử**:

```text
Flux<Sku>:
  onNext(Sku1)
  onNext(Sku2)
  onNext(Sku3)
  onComplete()

Mono<List<Sku>>:
  onNext([Sku1, Sku2, Sku3])
  onComplete()

Flux<List<Sku>> với buffer(2):
  onNext([Sku1, Sku2])
  onNext([Sku3])
  onComplete()
```

| Publisher | Bao nhiêu onNext cho 3 SKU? | Cách kiểm tra |
| --- | ---: | --- |
| `Flux<Sku>` | 3 | `expectNext(sku1,sku2,sku3)` |
| `Mono<List<Sku>>` | 1 | `expectNext(List.of(sku1,sku2,sku3))` |
| `Flux<List<Sku>>` sau `buffer(2)` | 2 | `expectNext(List.of(sku1,sku2), List.of(sku3))` |
| `Mono<Long>` sau `count()` | 1 | `expectNext(3L)` |

**Trường hợp rỗng khác nhau:**

- `Flux.empty()`: 0 `onNext`, complete.
- `Mono.empty()`: 0 `onNext`, complete.
- `Flux.empty().collectList()`: **1 `onNext` chứa List rỗng**, complete.
- `Flux.empty().count()`: **1 `onNext` chứa `0L`**, complete.
- `Flux.empty().buffer(2)`: không tạo batch `onNext` nào, complete.

Khi DTO trả `Mono<PageDto>` có field `items: List<ItemDto>`, StepVerifier chỉ thấy **một PageDto**. Muốn xác minh số item bên trong, dùng `assertNext(page -> assertEquals(n, page.items().size()))`, không dùng `expectNextCount(n)` vì đó là số **onNext**, không phải số phần tử nội bộ.

## 7. Kiểm tra nhiều phần tử theo thứ tự hay không theo thứ tự

### 7.1. Nếu thứ tự là một phần hợp đồng

Nguồn List có thứ tự, query có `ORDER BY` ổn định hoặc API cam kết kết quả được sắp xếp cần assertion giữ thứ tự:

```java
StepVerifier.create(Flux.just("A", "B", "C"))
        .expectNext("A", "B", "C")
        .verifyComplete();
```

Hoặc với nhiều giá trị kỳ vọng:

```java
StepVerifier.create(Flux.just("A", "B", "C"))
        .expectNextSequence(List.of("A", "B", "C"))
        .verifyComplete();
```

Cả hai đoạn là snippet bên trong test method đã import `Flux`/`StepVerifier`/`List`. Nếu source phát `B,A,C`, test phải fail khi thứ tự thực sự là requirement.

Với `flatMap` trên các inner publishers bất đồng bộ, thứ tự emission **có thể thay đổi** do concurrency/scheduler. Nếu phải giữ thứ tự, xem `concatMap` hoặc `flatMapSequential` theo mục tiêu concurrency; sau đó kiểm tra sequence đúng. Không dựa vào thứ tự “tình cờ” quan sát được trong một lần chạy.

### 7.2. Nếu thứ tự không phải hợp đồng

Khi dữ liệu đến từ các tác vụ song song mà business chỉ yêu cầu đủ các phần tử, so **multiset/tần suất** hoặc sắp xếp một bản sao collection. Không vội chuyển sang Set vì Set bỏ số lần lặp.

Ví dụ:

```java
StepVerifier.create(
                Flux.just("B", "A", "A").collectList())
        .assertNext(values -> {
            List<String> sorted = values.stream()
                    .sorted()
                    .toList();
            assertEquals(List.of("A", "A", "B"), sorted);
        })
        .verifyComplete();
```

Bài test này không phụ thuộc thứ tự ban đầu, nhưng vẫn bắt được trường hợp thiếu/thừa một chữ `A`. Ngược lại, chỉ so `Set.of("A","B")` có thể làm mất lỗi duplicate.

Có thể dùng `recordWith(...).consumeRecordedWith(...)` thay vì `collectList()`; nó ghi `onNext` ngay trong StepVerifier và cho phép assertion trên collection đã ghi. Đừng thu thập vô hạn một Flux không kết thúc vào List.

### 7.3. Nếu chỉ cần số lượng

Với luồng lớn hữu hạn, `expectNextCount` giúp kiểm tra số sự kiện:

```java
StepVerifier.create(Flux.range(1, 1_000))
        .expectNextCount(1_000)
        .verifyComplete();
```

Test xác nhận có đúng 1.000 `onNext` và complete, **không xác nhận nội dung các số**. Nếu pipeline có thể đổi giá trị nhưng vẫn giữ count, bổ sung assertion cho giá trị/biên cần bảo vệ.

## 8. Kết thúc bằng complete, error hoặc cancellation

### 8.1. Completion là một phần của hợp đồng

Viết `expectNextCount(3).verifyComplete()` xác minh nguồn phát đủ ba phần tử **rồi complete**. Nếu có phần tử thứ tư hoặc phát lỗi, verification fail. Vì thế terminal assertion quan trọng không kém giá trị.

### 8.2. Reactive error xảy ra khi subscribe

Ví dụ:

```java
Flux<Integer> stream = Flux.concat(
        Flux.just(1, 2),
        Flux.error(new IllegalStateException("offline")));

StepVerifier.create(stream)
        .expectNext(1, 2)
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "offline".equals(error.getMessage()))
        .verify();
```

Đoạn này có thể đặt trong method test với import `Flux` và `StepVerifier`. Nếu thay `expectErrorMatches(...).verify()` bằng `verifyComplete()`, test phải fail vì luồng kết thúc bằng error.

**Không lấy `assertThrows(IllegalStateException.class, () -> methodReturningFlux())` để kiểm tra `Flux.error`:** `methodReturningFlux()` có thể trả object bình thường, còn lỗi chỉ xảy ra trong sequence lúc subscribe. Đây là khác biệt trọng yếu giữa **throw đồng bộ** và **error signal**.

### 8.3. Recovery thay đổi outcome downstream

`onErrorResume` có thể chuyển một error thành giá trị dự phòng:

```java
Flux<String> recovered = Flux.<String>error(
        new IllegalStateException("offline"))
        .onErrorResume(ex -> Flux.just("cached"));

StepVerifier.create(recovered)
        .expectNext("cached")
        .verifyComplete();
```

Ở downstream, nguồn mới đã hoàn tất bình thường; kỳ vọng error cũ tại đây sẽ sai. Nếu nghiệp vụ yêu cầu retry 2 lần, cần test số attempts hoặc subscription count bằng fake/counter bên ngoài, không suy diễn số retry chỉ từ giá trị cuối.

### 8.4. Nguồn vô hạn hoặc kéo dài phải có điểm dừng

`Flux.never()` không hoàn tất; `Flux.interval(...)` có thể chạy vô hạn. Test phải biết khi nào cancel hoặc đặt timeout, thay vì chờ hoàn tất mãi. `thenCancel()` không chứng minh source đã tự onComplete; nó kiểm chứng **subscriber chủ động hủy** ở thời điểm mong muốn.

## 9. Backpressure: kiểm tra demand thay vì chỉ số phần tử

Subscriber của Reactive Streams dùng `Subscription.request(n)` để cho phép nguồn phát dữ liệu. Với `StepVerifier.create(publisher, 0)`, ban đầu không request phần tử nào; tiếp đó sử dụng `thenRequest(n)`:

```java
StepVerifier.create(Flux.range(1, 5), 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(3)
        .expectNext(3, 4, 5)
        .verifyComplete();
```

Kỳ vọng: sau lần request đầu, nhận 1 và 2; sau request thứ hai, nhận 3, 4, 5 rồi complete. `Flux.range` là nguồn đồng bộ tuân thủ demand, nên ví dụ không cần scheduler hoặc network.

**Đừng nhầm demand với pagination:** Backpressure kiểm soát số sự kiện trong một subscription; phân trang HTTP/DB là một hợp đồng khác về page/cursor/limit. Một test `thenRequest(2)` không chứng minh API hỗ trợ `?page=2`.

Kiểm thử demand phức tạp trên nguồn bên ngoài cần giữ nguyên operator và nguồn cần chứng minh: nếu dùng `Flux.just(...)` thay cho một HTTP streaming adapter, kết quả chỉ nói về Flux trong test, không đảm bảo adapter production tôn trọng backpressure.

## 10. Virtual time: kiểm tra delay và interval không ngủ thật

Một số pipeline phụ thuộc `delayElements`, `Flux.interval`, `Mono.delay`, retry backoff hoặc timeout. Nếu test sử dụng `Thread.sleep`, kết quả phụ thuộc scheduler và tải CI, vừa chậm vừa dễ flaky. Reactor Test có `StepVerifier.withVirtualTime(...)` để điều khiển thời gian ảo khi scheduler tương thích.

Ví dụ **hai tick cách nhau một giờ ảo**:

```java
@Test
void intervalWithVirtualTime() {
    StepVerifier.withVirtualTime(
                    () -> Flux.interval(Duration.ofHours(1))
                            .take(2))
            .expectSubscription()
            .expectNoEvent(Duration.ofHours(1))
            .expectNext(0L)
            .thenAwait(Duration.ofHours(1))
            .expectNext(1L)
            .verifyComplete();
}
```

**Ý nghĩa:** `Flux.interval(Duration.ofHours(1))` phát `0L` sau tick đầu tiên, `1L` sau tick thứ hai. `take(2)` khiến sequence hoàn tất sau hai phần tử. Đây không phải test chờ hai giờ thực; nó điều khiển **đồng hồ ảo**.

Những điểm cần làm đúng:

1. **Tạo Publisher trong supplier** `() -> Flux.interval(...).take(2)`, không tạo `Flux.interval` trước rồi capture object đã có scheduler trong lambda.
2. `expectNoEvent(duration)` cũng coi subscription là một event, nên đặt `expectSubscription()` trước khi đòi một khoảng không phát event.
3. Virtual time chỉ điều khiển những operators/schedulers tương thích với VirtualTimeScheduler. I/O thật, scheduler được tạo riêng hoặc blocking code không tự chuyển thành thời gian ảo. Pipeline phức tạp có thể bị starvation nếu thời gian chưa được advance đúng thứ tự.
4. Khi test timer không thuộc business rule, đừng thêm delay chỉ vì muốn kiểm thử scheduler. Ưu tiên những test đơn giản, deterministic.

## 11. Bộ test nâng cao runnable: record, virtual time, demand

Tạo `src/test/java/example/testing/webflux/StepVerifierAdvancedTest.java`:

```java
package example.testing.webflux;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StepVerifierAdvancedTest {

    @Test
    void countsLargeFiniteSequence() {
        StepVerifier.create(Flux.range(1, 1_000))
                .expectNextCount(1_000)
                .verifyComplete();
    }

    @Test
    void recordsRepeatedValuesWithoutLosingDuplicates() {
        StepVerifier.create(Flux.just("B", "A", "A"))
                .recordWith(ArrayList::new)
                .expectNextCount(3)
                .consumeRecordedWith(values -> {
                    List<String> sorted = values.stream()
                            .sorted()
                            .toList();
                    assertEquals(
                            List.of("A", "A", "B"), sorted);
                })
                .verifyComplete();
    }

    @Test
    void intervalWithVirtualTime() {
        StepVerifier.withVirtualTime(
                        () -> Flux.interval(
                                Duration.ofHours(1))
                                .take(2))
                .expectSubscription()
                .expectNoEvent(Duration.ofHours(1))
                .expectNext(0L)
                .thenAwait(Duration.ofHours(1))
                .expectNext(1L)
                .verifyComplete();
    }

    @Test
    void honorsDemandInTwoSteps() {
        StepVerifier.create(Flux.range(1, 5), 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .verifyComplete();
    }

    @Test
    void cancelsWithoutDrainingLargeSource() {
        StepVerifier.create(
                        Flux.range(1, 1_000_000), 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();
    }
}
```

Class trên có **5 test methods**. Tổng cộng hai class JUnit trong ví dụ chứa **18 method test** (13 ở `SkuCatalogTest` và 5 ở `StepVerifierAdvancedTest`). Mỗi test độc lập; không cần Spring context hoặc HTTP request.

Đọc kỹ:

- Test `countsLargeFiniteSequence` kiểm tra count 1.000 và completion, không kiểm tra giá trị từng số.
- Test `recordsRepeatedValuesWithoutLosingDuplicates` dùng `recordWith(ArrayList::new)` rồi kiểm tra sorted copy, nhờ đó phát hiện thiếu/thừa giá trị trùng nhau.
- Test `intervalWithVirtualTime` tránh `Thread.sleep` và bảo đảm builder tạo publisher trong supplier.
- Test demand sử dụng `initialRequest=0`, sau đó cấp request theo hai lượt.
- Test cancellation chỉ nhận hai phần tử rồi cancel, **không đòi one million events được phát**. Nó không tự chứng minh cleanup tài nguyên ngoài; nếu real source giữ DB cursor/socket thì cần test resource lifecycle riêng.

### Chạy cả hai class bằng Gradle

Từ thư mục gốc dự án có Gradle wrapper:

```bash
./gradlew test --tests example.testing.webflux.SkuCatalogTest
./gradlew test --tests example.testing.webflux.StepVerifierAdvancedTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.webflux.SkuCatalogTest"
.\gradlew.bat test --tests "example.testing.webflux.StepVerifierAdvancedTest"
```

**Kỳ vọng:** cả 18 method pass nếu source files đúng như trên, Java 17+ và dependencies Reactor/JUnit tương thích. Gradle/JUnit logging thay đổi theo build, nên không gán một chuỗi stdout cố định cho lệnh test. Với test trong subproject, chọn đúng test task của subproject đó.

## 12. Cold và hot publisher: đừng lấy một dạng làm mặc định cho mọi nguồn

Trong `SkuCatalog`, `Flux.fromIterable(source)` trên một List không đổi là một **cold publisher**: mỗi subscription có thể nhận chuỗi dữ liệu từ đầu. Bởi vậy `coldFluxCanBeSubscribedTwice` chạy hai StepVerifier trên cùng instance Flux và cả hai đều nhận đúng ba SKU.

Nhưng publisher **hot** (ví dụ multicast sink hoặc luồng sự kiện thời gian thực) có thể phát sự kiện **trước khi người dùng mới subscribe**; subscriber tới muộn có thể không nhận các sự kiện ấy. Test hot publisher phải:

- Tạo source mới cho mỗi test, tránh giữ sink dùng chung giữa test methods.
- Kiểm soát việc subscribe **trước khi** phát sự kiện nếu hợp đồng yêu cầu subscriber nhận chúng.
- Có thể dùng bước `StepVerifier.then(...)` để phát sự kiện sau subscription, thay vì đẩy event trước rồi mới tạo subscriber.
- Xác định rõ hot publisher có replay/cache hay chỉ multicast các sự kiện mới.
- Không dùng `expectNext("A","B","C")` nếu dữ liệu có thể đến trước khi verifier subscribe và không có cơ chế replay.

Với một số cold publishers, subscribe lại có thể **gây lại side effect** (gọi API, ghi log, thực thi truy vấn). Do đó test không nên subscribe nhiều lần chỉ để “xem” dữ liệu khi nguồn thực có tác động ngoại vi. Nếu số lần subscribe là yêu cầu nghiệp vụ, dùng fake/counter phù hợp để assert chính xác.

## 13. Khi nào dùng StepVerifier và khi nào dùng WebTestClient?

**`StepVerifier` xác minh contract của `Publisher`**, còn **`WebTestClient` xác minh HTTP exchange** của Spring WebFlux.

| Câu hỏi | Công cụ thường phù hợp |
| --- | --- |
| `Mono<Sku>` trả đúng một item hoặc empty? | StepVerifier |
| `Flux<Sku>` trả đúng thứ tự và đủ phần tử? | StepVerifier |
| `collectList()/buffer()/count()` tạo bao nhiêu event? | StepVerifier |
| Pipeline phát lỗi hay phục hồi `onErrorResume`? | StepVerifier |
| Test delay, virtual time, request demand? | StepVerifier |
| `GET /skus` trả HTTP status và JSON array đúng? | WebTestClient |
| Binding, validation, exception handler của WebFlux controller đúng? | `@WebFluxTest` + WebTestClient |
| Controller-service-repository phối hợp thực? | Integration test có context/hạ tầng thực thích hợp |

Ví dụ **chỉ minh họa HTTP** với một controller `GET /skus?prefix=JAVA` đã có trong ứng dụng, trả JSON array, và biến `webTestClient` được inject:

```java
webTestClient.get()
        .uri("/skus?prefix=JAVA")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$[0].code").isEqualTo("JAVA-1");
```

Đoạn này **không phải class chạy độc lập**: phải có controller/router function, `WebTestClient`, endpoint đúng và serializer WebFlux. Nó xác minh body HTTP, **không thay thế** StepVerifier khi bạn cần kiểm soát request/demand hoặc terminal events của service.

`@WebFluxTest` có thể tải một **slice** chỉ gồm WebFlux infrastructure và controllers; service không thuộc slice có thể được cung cấp bằng mock bean phù hợp phiên bản Spring Test. Test web slice không chứng minh database đã ghi nếu repository/service đều mock. Với luồng HTTP streaming thực, media type (JSON array, NDJSON, SSE), encoders, backpressure và kết nối mạng là những ranh giới khác nhau; nếu cần xác nhận network behavior, sử dụng integration test có server/client thích hợp.

Không dùng `@SpringBootTest` cho mọi phép `map/filter/collectList`. Một unit test Reactor thuần chạy nhanh và rõ nguyên nhân lỗi hơn; context chỉ cần khi thực sự kiểm chứng Spring bean wiring/proxy/web infrastructure hoặc adapter.

## 14. Timeout, cancellation và test không bị treo

Với publisher không có terminal signal hoặc luồng thực bất đồng bộ, có thể dùng timeout của verifier:

```java
StepVerifier.create(Flux.just(1, 2, 3))
        .expectNext(1, 2, 3)
        .expectComplete()
        .verify(Duration.ofSeconds(3));
```

Đây là ví dụ đặt **giới hạn thời gian thực cho test**, không phải business rule “Flux phải hoàn tất trong 3 giây”. Đừng đặt timeout quá sát tải trung bình của CI khi pipeline dùng thread scheduler hoặc I/O thật; khi đó test dễ flaky. Nếu cần test một delay/backoff được định nghĩa, dùng virtual time như mục 10.

Với stream vô hạn, nên lựa chọn có chủ đích: `take(n)` nếu business logic thực sự cần n phần tử đầu, hoặc `thenCancel()` khi muốn xác minh hủy subscription. Nếu publisher quản lý tài nguyên (file, DB cursor, network stream), cần thêm assertion chứng minh callback cleanup/resource release sau cancel; `thenCancel()` một mình không chứng minh điều ấy.

Tránh `block()` trong reactive processing thread: có thể vi phạm mô hình non-blocking và gây lỗi hoặc chậm. Trong test Reactor, StepVerifier thường cho bằng chứng đầy đủ hơn `block()` vì giữ nguyên các event `onNext`/`onComplete`/`onError`.

## 15. Các lỗi phổ biến

**1. So sánh `Mono`/`Flux` như object kết quả.** Dùng StepVerifier để subscribe và kiểm tra signals, không chỉ `assertEquals(publisherA,publisherB)`.

**2. Quên `verify()` hoặc `verifyComplete()`.** Khi thiếu bước verify, kịch bản chưa được chạy.

**3. Dùng `expectNext(a,b,c)` cho `Mono<List<T>>`.** Publisher chỉ phát một List; phải assert một List thay vì ba T.

**4. Nhầm `Flux.empty().collectList()` là `Mono.empty()`.** `collectList` phát một empty list rồi complete.

**5. Dùng `expectNextCount(n)` để kết luận nội dung đúng.** Count không kiểm tra values; cần `expectNext`/`assertNext`/recording thêm.

**6. Cho rằng Flux luôn phát nhiều phần tử.** Flux có thể phát 0, 1, nhiều hoặc vô hạn; test phải dựa vào contract cụ thể.

**7. Quên assert thứ tự hoặc assert sai thứ tự.** `flatMap` bất đồng bộ có thể reorder. Nếu order quan trọng dùng operator/expectation đúng; nếu không quan trọng so multiset giữ duplicates.

**8. Dùng Set để so kết quả có duplicate.** Set làm mất số lần xuất hiện; chọn sorted list hoặc frequency map.

**9. Dùng `assertThrows` quanh `Mono.error`.** Error phát lúc subscribe. `expectErrorMatches(...).verify()` đúng tín hiệu.

**10. Kỳ vọng `verifyComplete` khi publisher kết thúc bằng error.** `onError` và `onComplete` là hai terminal outcomes khác nhau.

**11. Kỳ vọng lỗi cũ sau `onErrorResume`.** Downstream có thể nhận fallback + complete; test đúng vị trí trong pipeline.

**12. Dùng `Thread.sleep` để kiểm tra `interval/delay`.** Test chậm, nhạy scheduler; dùng virtual time khi tương thích.

**13. Tạo publisher có scheduler ngoài lambda `withVirtualTime`.** Scheduler có thể đã được chọn trước lúc đổi virtual clock; tạo nó trong supplier.

**14. Test `Flux.never` rồi đợi completion.** Không có terminal event; dùng cancel/timeout rõ ràng.

**15. Không kiểm soát thời điểm subscribe của hot publisher.** Event có thể đến trước subscriber và bị bỏ lỡ; test phải chủ động sắp đặt subscription/emission.

**16. Dùng StepVerifier service để tuyên bố HTTP response đúng.** Status, JSON, SSE, security filter cần WebTestClient/integration test theo boundary.

**17. Lạm dụng `@SpringBootTest` cho logic thuần.** Không cần context để test Flux.map/filter với StepVerifier; khởi động hạ tầng ngoài chỉ tăng độ phức tạp.

**18. Gọi `block()` để “giải quyết” mọi dữ liệu rồi assert List.** Có thể che terminal-signal behavior, block thread hoặc treo khi nguồn không complete; ưu tiên StepVerifier hoặc thu thập có giới hạn.

## 16. Checklist khi review test Mono/Flux

Trước khi viết:

- Method trả `Mono<T>`, `Flux<T>`, `Mono<List<T>>` hay `Flux<List<T>>`?
- Có thể phát **0, 1, nhiều phần tử** hoặc stream vô hạn? Có terminal event theo hợp đồng?
- Thiếu dữ liệu là `empty` hay `onError`? Error có cần kiểm tra class/message không?
- Thứ tự có thuộc hợp đồng không? Nếu không, cách so có giữ duplicate không?

Khi viết:

- `expectNext` kiểm tra đúng giá trị/thứ tự; `expectNextCount` chỉ đếm.
- `assertNext` có assertion có nghĩa trên record/DTO, không chỉ nhận phần tử rồi bỏ qua.
- Với `collectList()/count()/buffer()`, đã tách biệt **số onNext** và **số phần tử bên trong** chưa?
- Có kiểm tra complete hoặc error **và gọi verify**?
- Có test cả empty, data biên, error và recovery khi cần không?

Với bất đồng bộ:

- Nếu có time operators, đã dùng virtual time với publisher tạo trong supplier?
- Nếu kiểm tra demand, đã dùng initial request / thenRequest đúng?
- Nguồn có thể không kết thúc? Đã có cancel/timeout?
- Hot stream có được tạo mới và kiểm soát subscription/emission trong từng test?
- Có resource cleanup và tránh blocking bất ngờ trong reactive thread?

Với Spring Boot:

- Test này chứng minh **publisher signal contract** hay **HTTP response**?
- Nếu cần routing/JSON/validation của WebFlux, đã dùng WebTestClient/test slice thích hợp?
- Nếu cần transaction/DB/HTTP client thật, đã có integration test đúng hạ tầng?
- Có giữ service/pipeline cần kiểm tra là object thật, chỉ mock collaborator ngoài boundary?

**Ghi nhớ:** `StepVerifier` cho phép kiểm tra **đúng số lượng, thứ tự, nội dung, completion/error và demand** của một Mono/Flux. Với `Flux<T>`, `Mono<List<T>>` và `Flux<List<T>>`, luôn phân biệt **số sự kiện onNext với số phần tử trong dữ liệu**. Dùng virtual time cho operator thời gian; dùng WebTestClient khi mục tiêu là HTTP. Chọn đúng công cụ và ranh giới quan sát sẽ giúp test WebFlux đáng tin, nhanh và dễ sửa khi code thay đổi.

## 17. Tài liệu tham khảo

- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): tổng quan StepVerifier, virtual time, backpressure và các publisher thử nghiệm.
- [Reactor Test — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): create, withVirtualTime và verify.
- [Reactor Test — StepVerifier.Step API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Step.html): expectNextSequence, expectNextCount, recordWith và consumeRecordedWith.
- [Spring Boot — Testing WebFlux Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): WebFlux test slice và WebTestClient.
