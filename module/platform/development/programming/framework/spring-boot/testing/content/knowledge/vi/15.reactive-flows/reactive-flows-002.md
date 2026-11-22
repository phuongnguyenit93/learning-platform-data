# Luồng Reactive — StepVerifier: giá trị, hoàn tất và tín hiệu lỗi

## Mục tiêu

Khi làm việc với Spring WebFlux, một service thường không trả trực tiếp `Order`, `List<Order>` hoặc ném exception ngay tại thời điểm gọi method. Thay vào đó, nó trả **`Mono<T>` hoặc `Flux<T>`** — một `Publisher` mô tả những tín hiệu sẽ được gửi khi có subscriber. Test đúng cần kiểm **các tín hiệu và thứ tự tín hiệu**, chứ không chỉ nhìn vào đối tượng publisher được tạo.

`StepVerifier` thuộc thư viện **`reactor-test`** của Project Reactor. Nó cho phép viết một kịch bản: subscribe → dự kiến những `onNext` nào → nhận `onComplete` **hoặc** `onError` → thực hiện `verify`. Đây là công cụ trọng tâm để kiểm logic reactive trong Java/Spring Boot.

Sau bài này, bạn có thể:

- Phân biệt `onSubscribe`, `onNext`, `onComplete`, `onError` và cancellation.
- Kiểm **giá trị được phát**, số lượng, thứ tự, điều kiện trên dữ liệu và giá trị không được phát.
- Kiểm `Mono.empty()`, `Flux.empty()` và sự khác biệt giữa **trống bình thường** với **lỗi**.
- Dùng `expectError`, `expectErrorMatches`, `expectErrorSatisfies`, `verifyError` để bảo vệ hợp đồng lỗi.
- Hiểu `verifyComplete()` không tương đương “đã nhận một giá trị”; nó còn yêu cầu luồng **kết thúc thành công** và không có tín hiệu thừa.
- Kiểm luồng chịu **backpressure** với `initialRequest` và `thenRequest`.
- Kiểm delay/timeout mà không phải đợi thời gian thật bằng `withVirtualTime`.
- Phân biệt unit test `StepVerifier` với kiểm thử HTTP bằng `WebTestClient`.
- Chạy ví dụ đầy đủ với **Java 17, Spring Boot 3.3.x, Reactor Core, reactor-test, Gradle và JUnit Jupiter**.

**Tư tưởng then chốt:** Reactor test phải khẳng định đúng **kết quả cuối cùng của chuỗi tín hiệu**: một publisher phát dữ liệu đúng rồi báo complete, hoặc phát một số dữ liệu rồi báo error, hoặc complete ngay mà không phát dữ liệu. Nếu bỏ kiểm terminal signal, test có thể không bảo vệ được hợp đồng mong muốn.

## 1. Mô hình tín hiệu của Reactive Streams

Với một subscription bình thường, Reactive Streams có dạng:

~~~text
Subscriber                      Publisher
    |                               |
    |---- subscribe() ------------->|
    |<--- onSubscribe(subscription)-|
    |---- request(n) -------------->|
    |<--- onNext(value_1) ----------|
    |<--- onNext(value_2) ----------|
    |<--- ... ----------------------|
    |<--- onComplete() -------------|  thành công

hoặc

    |<--- onError(exception) -------|  thất bại
~~~

Những quy tắc cần nhớ:

1. **`onSubscribe`** thiết lập một subscription.
2. **`onNext(T)`** mang theo giá trị. `Flux` có thể phát 0, 1 hoặc nhiều giá trị; `Mono` thông thường phát **tối đa một** giá trị.
3. **`onComplete()`** kết thúc thành công, kể cả khi trước đó **không có giá trị nào**.
4. **`onError(Throwable)`** kết thúc vì lỗi. Nó **không đi kèm `onComplete` sau đó** trong cùng một subscription.
5. Sau terminal signal (`onComplete`/`onError`), publisher hợp lệ không tiếp tục phát `onNext`.
6. Subscriber có thể **cancel** trước khi nhận terminal; cancel không đồng nghĩa “luồng tự complete”.
7. Số lượng `onNext` chịu ràng buộc bởi demand (`request(n)`) đối với publisher tôn trọng backpressure.

Ví dụ tín hiệu của những publisher quen thuộc:

| Publisher | Tín hiệu quan sát được |
| --- | --- |
| `Mono.just("A")` | `onNext("A")` → `onComplete` |
| `Mono.empty()` | `onComplete` (không có `onNext`) |
| `Mono.error(new IllegalArgumentException("bad"))` | `onError(IllegalArgumentException)` |
| `Flux.just("A", "B")` | `onNext("A")` → `onNext("B")` → `onComplete` |
| `Flux.concat(Flux.just("A"), Flux.error(...))` | `onNext("A")` → `onError` |
| `Flux.never()` | Không `onNext`, không terminal cho tới khi cancel hoặc dừng bên ngoài |

Vì `onComplete` và `onError` **loại trừ nhau**, một test mong chờ error không nên đồng thời mong complete. Với luồng không kết thúc, một test gọi `verifyComplete()` mà không có timeout có thể đợi rất lâu. Tùy mục tiêu, hãy dùng cancellation, timeout hữu hạn hoặc virtual time.

### Publisher chưa chắc đã chạy khi method được gọi

~~~java
Mono<String> greeting = Mono.fromSupplier(() -> {
    System.out.println("supplier executed");
    return "xin chao";
});
~~~

Đoạn này là snippet: chỉ tạo `Mono` chưa chạy supplier. Supplier thường thực thi **khi có subscription**. `StepVerifier.create(greeting)` dựng kịch bản, còn một trong các thao tác như `verifyComplete()`, `verifyError(...)` hoặc `verify()` mới kích hoạt subscription và việc kiểm tra tín hiệu.

Không dùng `assertNotNull(greeting)` để kết luận logic reactive đã đúng. Assertion ấy chỉ xác nhận Java object `Mono` tồn tại.

## 2. Dependency và import đúng

**Gradle** trong module Spring Boot dùng WebFlux:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
~~~

Đây là đoạn dependency để ghép vào `build.gradle` đã dùng Spring Boot plugin và dependency management tương thích. Project runnable đầy đủ nằm ở mục 7.

**Các import quan trọng**:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import org.junit.jupiter.api.Test;
~~~

`StepVerifier` thuộc package `reactor.test`, không nằm trong `reactor.core.publisher` và cũng không thuộc JUnit mặc định. Nếu IDE báo không tìm thấy `reactor.test.StepVerifier`, hãy kiểm dependency `io.projectreactor:reactor-test` có trong **test classpath** và không bị exclude.

Nếu chỉ kiểm Reactor thuần, không cần chạy `@SpringBootTest`. Một unit test có thể tạo service bằng `new` và dùng `StepVerifier` để kiểm `Mono`/`Flux` ngay lập tức. `@SpringBootTest` chỉ cần khi test muốn chứng minh **Spring bean wiring, auto-configuration hoặc các tầng ứng dụng tương tác**.

## 3. Cấu trúc một kịch bản `StepVerifier`

Kịch bản căn bản:

~~~java
StepVerifier.create(Flux.just("BOOK", "PEN"))
        .expectNext("BOOK")
        .expectNext("PEN")
        .expectComplete()
        .verify();
~~~

Đây là snippet có thể đặt trong một method `@Test` cùng import. Mỗi bước có nhiệm vụ:

| Phần | Ý nghĩa |
| --- | --- |
| `StepVerifier.create(publisher)` | Chuẩn bị subscribe vào Publisher khi verify |
| `expectSubscription()` | Đòi quan sát tín hiệu subscribe |
| `expectNext(value)` | Đòi đúng giá trị `onNext` kế tiếp |
| `expectNextCount(n)` | Đòi có đúng `n` giá trị ở đoạn kế tiếp, không kiểm từng nội dung |
| `expectNextMatches(predicate)` | Kiểm giá trị kế tiếp bằng predicate |
| `assertNext(consumer)` | Thực hiện assertions tùy biến trên giá trị kế tiếp |
| `expectComplete()` | Đòi tín hiệu terminal `onComplete` |
| `expectError(...)` | Đòi terminal `onError` phù hợp |
| `thenCancel()` | Cancel subscription khi đã đạt bước cần kiểm |
| `verify()` | **Thực sự subscribe và thực thi** kịch bản kiểm |
| `verifyComplete()` | Viết ngắn cho kỳ vọng complete + verify |
| `verifyError(...)` | Viết ngắn cho kỳ vọng error + verify |

Trong ví dụ trên, hai `expectNext` kiểm cả **nội dung và thứ tự**, còn `expectComplete` đảm bảo sau `PEN` không có thêm item nào và publisher kết thúc bình thường. `verify()` là bước kích hoạt.

### Cách viết ngắn

Hai kịch bản sau có ý nghĩa tương đương:

~~~java
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .expectComplete()
        .verify();
~~~

~~~java
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .verifyComplete();
~~~

Trong code mới, `verifyComplete()` khá dễ đọc: “sau những giá trị đã mong đợi, luồng phải complete”. Nhưng không dùng nó cho luồng **được thiết kế để báo error**.

### Trường hợp rỗng hoàn toàn

~~~java
StepVerifier.create(Mono.empty())
        .verifyComplete();
~~~

Test này pass **dù không có bất kỳ `onNext` nào**. Nếu yêu cầu “phải tìm thấy một hóa đơn”, đừng chỉ viết `verifyComplete()`; cần có `expectNext(...)` hoặc assertion để phát hiện việc publisher vô tình chuyển thành empty.

Nếu dùng `Mono.justOrEmpty(null)`, kết quả cũng là completion rỗng. Reactive Streams **không cho phép phát `null` như giá trị `onNext`**; muốn biểu diễn “không có dữ liệu”, dùng empty hoặc một cấu trúc dữ liệu mô tả trạng thái.

## 4. Kiểm giá trị: exact match, predicate, custom assertion và số lượng

### `expectNext` cho hợp đồng giá trị chính xác

~~~java
StepVerifier.create(Flux.just("A", "B", "C"))
        .expectNext("A", "B", "C")
        .verifyComplete();
~~~

Có ba yêu cầu: đúng **3 giá trị**, **đúng thứ tự** và **kết thúc thành công ngay sau đó**. Nếu publisher phát `A`, `C`, `B` hoặc phát thêm `D`, test fail.

Với Java record có `equals` theo các thành phần, `expectNext(new Quote(...))` rất hữu ích. Với object mutable/không có `equals`, kiểm qua predicate hoặc `assertNext` sẽ rõ hợp đồng hơn.

### `expectNextMatches` kiểm điều kiện

~~~java
StepVerifier.create(Mono.just("INV-2026-001"))
        .expectNextMatches(id ->
                id.startsWith("INV-")
                        && id.length() > 5)
        .verifyComplete();
~~~

Predicate trả `true` khi giá trị thỏa yêu cầu. Ưu điểm: không cần hardcode toàn bộ ID biến động. Hạn chế: predicate quá yếu (ví dụ chỉ `id != null`) có thể để lọt hành vi sai; nếu hợp đồng đòi đúng ID, dùng `expectNext(expectedId)`.

### `assertNext` kiểm nhiều trường trong object

~~~java
StepVerifier.create(Mono.just(
        new Quote("BOOK", 24000L)))
        .assertNext(quote -> {
            assertEquals("BOOK", quote.sku());
            assertEquals(24000L, quote.totalCents());
        })
        .verifyComplete();
~~~

Snippet giả định có `Quote` record và static import `assertEquals`, như project ở mục 7. `assertNext` lấy đúng một giá trị và cho phép dùng nhiều assertion JUnit/AssertJ. Nếu assertion bên trong fail, StepVerifier sẽ báo test fail thay vì bỏ qua lỗi.

### `expectNextCount` chỉ kiểm số lượng

~~~java
StepVerifier.create(Flux.just("A", "B", "C"))
        .expectNextCount(3)
        .verifyComplete();
~~~

Nó chứng minh có ba `onNext` trước completion, **không chứng minh** ba giá trị là `A, B, C`. Dùng khi nội dung không thuộc hợp đồng hoặc đã được kiểm ở nơi khác; tránh lạm dụng vì nó làm giảm sức mạnh của test.

### Khi array/collection là **một** giá trị reactive

~~~java
Mono<java.util.List<String>> result =
        Mono.just(java.util.List.of("A", "B"));

StepVerifier.create(result)
        .assertNext(list -> {
            assertEquals(2, list.size());
            assertEquals("A", list.get(0));
        })
        .verifyComplete();
~~~

Publisher trên phát **một `List`**, không phải hai tín hiệu `onNext("A")` và `onNext("B")`. Nếu API là `Flux<String>`, mới kiểm từng phần tử. Phân biệt **`Mono<List<T>>`** và **`Flux<T>`** để viết kịch bản đúng kiểu và đúng số tín hiệu.

## 5. Kiểm hoàn tất: `onComplete` không phải “có data”

Một `Mono<T>` có thể:

- Phát **một T** rồi complete;
- Complete **rỗng**;
- Error **không có giá trị**.

Vì thế test cần xác định hợp đồng:

| Hợp đồng | Kịch bản phù hợp |
| --- | --- |
| Phải trả đúng một quote | `expectNext(expectedQuote).verifyComplete()` |
| Không tìm thấy → complete rỗng | `verifyComplete()` và **không có `expectNext`** |
| Không tìm thấy → error | `verifyError(NotFoundException.class)` |
| Trả nhiều item theo thứ tự | `expectNext(...).verifyComplete()` |
| Trả 0 hoặc nhiều item, chỉ cần biết hoàn tất | `expectNextCount(n).verifyComplete()` khi n đã biết |
| Luồng sống lâu không có completion tự nhiên | `thenCancel().verify()` theo trường hợp |

Vấn đề thường gặp: test một repository `Mono<Order>` chỉ viết:

~~~java
StepVerifier.create(repository.findById("42"))
        .verifyComplete();
~~~

Nếu repository trả empty vì truy vấn sai, test vẫn pass. Khi hợp đồng **phải tìm thấy Order 42**, hãy assert đúng ID và các trường quan trọng bằng `expectNext`/`assertNext`, rồi mới `verifyComplete`.

Một test cũng có thể fail vì giả định publisher hoàn tất, trong khi API **được thiết kế là stream liên tục** (ví dụ event subscription). Khi đó, test phải kiểm một đoạn dữ liệu rồi cancel hoặc dùng giới hạn ở logic production theo yêu cầu; không áp đặt completion không tồn tại.

## 6. Kiểm lỗi: `onError` là tín hiệu kết thúc

Trong Reactor, nhiều lỗi phát sinh **bên trong pipeline khi được subscribe**, không phải exception ném trực tiếp tại dòng tạo publisher. Ví dụ:

~~~java
Mono<Integer> division =
        Mono.fromCallable(() -> 10 / 0);

StepVerifier.create(division)
        .verifyError(ArithmeticException.class);
~~~

Snippet này là method-body Java hợp lệ khi có import `Mono`, `StepVerifier`. Phép chia nằm trong `fromCallable`, được gọi lúc subscribe, sau đó lỗi được chuyển thành `onError(ArithmeticException)`. Test bằng `assertThrows(ArithmeticException.class, () -> division)` **không đúng mục tiêu**, vì lambda ấy chỉ trả Mono object mà không chạy phép tính.

### `verifyError(Class)` — đúng loại lỗi

~~~java
StepVerifier.create(Mono.error(
        new IllegalArgumentException("invalid")))
        .verifyError(IllegalArgumentException.class);
~~~

Kiểm loại exception và terminal error, nhưng **không kiểm message**.

### `expectErrorMatches` — đúng loại và đặc điểm lỗi

~~~java
StepVerifier.create(Mono.error(
        new IllegalArgumentException("quantity must be positive")))
        .expectErrorMatches(error ->
                error instanceof IllegalArgumentException
                        && "quantity must be positive"
                                .equals(error.getMessage()))
        .verify();
~~~

Predicate nên kiểm điều kiện có ý nghĩa, không được viết `error -> true` khiến test pass với mọi lỗi. Tránh assert toàn bộ stack trace hoặc message nội bộ dễ thay đổi nếu chúng không thuộc hợp đồng; kiểm error class, status/code nghiệp vụ, hoặc payload ổn định.

### `expectErrorSatisfies` — nhiều assertion về lỗi

~~~java
StepVerifier.create(Mono.error(
        new IllegalArgumentException("sku is required")))
        .expectErrorSatisfies(error -> {
            assertInstanceOf(IllegalArgumentException.class, error);
            assertEquals("sku is required", error.getMessage());
        })
        .verify();
~~~

Đoạn này cần static imports JUnit Jupiter tương ứng. Đây là cách kiểm một terminal error với nhiều điều kiện. **Không có `expectComplete()` phía sau**, vì error đã là terminal.

### Một số giá trị có thể phát trước khi lỗi

~~~java
Flux<String> result = Flux.concat(
        Flux.just("FIRST"),
        Flux.error(new IllegalStateException("upstream failed")));

StepVerifier.create(result)
        .expectNext("FIRST")
        .verifyError(IllegalStateException.class);
~~~

Test chứng minh **`FIRST` đã phát trước lỗi**. Nếu yêu cầu là “hễ có lỗi thì không trả dữ liệu nào”, pipeline kiểu này có thể không đáp ứng và cần thay logic hoặc định nghĩa lại contract. Với `Flux`, **lỗi sau một phần dữ liệu** là điều có thể xảy ra; test không nên giả định toàn bộ chuỗi là transaction nguyên tử.

### Lỗi được `onErrorResume` xử lý sẽ không còn là terminal error

~~~java
Mono<String> result =
        Mono.<String>error(new IllegalStateException("temporary"))
                .onErrorResume(ex -> Mono.just("fallback"));

StepVerifier.create(result)
        .expectNext("fallback")
        .verifyComplete();
~~~

Vì `onErrorResume` **chuyển lỗi thành một publisher khác**, downstream quan sát được giá trị `fallback` rồi completion. Test ở phía sau recovery không nên mong `verifyError`. Nếu yêu cầu là audit/ghi log lỗi trước recovery, kiểm side effect riêng tại đúng boundary.

**Không che lỗi một cách tùy tiện.** `onErrorResume(ex -> Mono.empty())` sẽ khiến mọi lỗi có thể trở thành completion rỗng nếu predicate không giới hạn. Test chỉ viết `verifyComplete()` có thể xanh ngay cả khi nghiệp vụ bị hỏng. Hãy có test riêng cho các nhánh error và recovery, và chỉ fallback với loại lỗi được phép.

## 7. Project hoàn chỉnh: Java 17 + Spring Boot + Reactor Test

Project này có service xử lý giá đơn hàng theo đồng xu/cent (số nguyên `long`), một controller WebFlux nhỏ và các JUnit tests. Các class Java dùng cùng package `com.example.reactive`.

**Hợp đồng của service:**

- Một line hợp lệ có `sku` không rỗng, `quantity > 0`, `unitPriceCents >= 0`.
- Thành tiền là `quantity × unitPriceCents` và phải không tràn `long`.
- `quote(line)` trả **`Mono<Quote>` có đúng một Quote rồi complete**, hoặc `onError` khi input sai.
- `quoteAll(lines)` trả `Flux<Quote>` **theo thứ tự input**, và khi gặp phần tử sai thì dừng với `onError`.
- Danh sách rỗng hợp lệ → `Flux` complete rỗng.
- `quoteOrDefault` chỉ fallback cho lỗi `IllegalArgumentException` thành một Quote đã định nghĩa; **ArithmeticException do overflow không bị nuốt**.

### 7.1. Cấu trúc thư mục

~~~text
reactor-stepverifier-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/reactive/
    │   ├── ReactorDemoApplication.java
    │   ├── PricingService.java
    │   └── QuoteController.java
    └── test/java/com/example/reactive/
        ├── PricingServiceStepVerifierTest.java
        └── QuoteControllerWebFluxTest.java
~~~

Gradle Wrapper cần có từ repository hoặc tạo bằng Gradle đã cài tương thích. File `gradle-wrapper.jar` là nhị phân, không tự chép nội dung bằng tay. Nếu đang ở module có Wrapper, dùng version của repo.

**`settings.gradle`**

~~~groovy
rootProject.name = 'reactor-stepverifier-demo'
~~~

**`build.gradle`** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-webflux` đem theo Reactor Core và Spring WebFlux. `spring-boot-starter-test` đem các thư viện Spring Test/JUnit; `reactor-test` **được khai báo rõ ràng** để dùng `StepVerifier`. Hệ thống dependency management của Spring Boot 3.3.5 quản lý các version Reactor/JUnit tương thích, không cần tự ghim một Reactor Test khác phiên bản Reactor Core.

Đối với Spring Boot 4 hoặc bộ Reactor mới hơn, cần dùng dependency/test starter tương ứng với version thực tế; đây là **ví dụ cho Boot 3.3.5**, không phải lệnh đổi version của một repository hiện hữu.

### 7.2. Spring Boot application

**`src/main/java/com/example/reactive/ReactorDemoApplication.java`**

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactorDemoApplication.class, args);
    }
}
~~~

Boot application ở cùng package gốc với controller và service. Khi chạy riêng **unit test `PricingServiceStepVerifierTest`**, không cần `SpringApplication.run` hay tạo application context. Khi chạy `@WebFluxTest` ở mục 7.5, Spring khởi tạo một **WebFlux slice** để kiểm mapping và JSON.

### 7.3. Service reactive thật

**`src/main/java/com/example/reactive/PricingService.java`**

~~~java
package com.example.reactive;

import java.util.List;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public final class PricingService {

    public record OrderLine(
            String sku,
            int quantity,
            long unitPriceCents) {
    }

    public record Quote(String sku, long totalCents) {
    }

    public Mono<Quote> quote(OrderLine line) {
        return Mono.defer(() -> {
            if (line == null) {
                return Mono.error(new IllegalArgumentException(
                        "line is required"));
            }
            if (line.sku() == null || line.sku().isBlank()) {
                return Mono.error(new IllegalArgumentException(
                        "sku is required"));
            }
            if (line.quantity() <= 0) {
                return Mono.error(new IllegalArgumentException(
                        "quantity must be positive"));
            }
            if (line.unitPriceCents() < 0) {
                return Mono.error(new IllegalArgumentException(
                        "price must be non-negative"));
            }

            // Tràn số long được Reactor chuyển thành onError.
            long total = Math.multiplyExact(
                    (long) line.quantity(),
                    line.unitPriceCents());

            return Mono.just(new Quote(line.sku(), total));
        });
    }

    public Flux<Quote> quoteAll(List<OrderLine> lines) {
        return Flux.defer(() -> {
            if (lines == null) {
                return Flux.error(new IllegalArgumentException(
                        "lines is required"));
            }

            // concatMap giữ thứ tự output và phát lỗi
            // khi một line không hợp lệ.
            return Flux.fromIterable(lines)
                    .concatMap(this::quote);
        });
    }

    public Mono<Quote> quoteOrDefault(OrderLine line) {
        return quote(line)
                .onErrorResume(
                        IllegalArgumentException.class,
                        error -> Mono.just(new Quote("DEFAULT", 0L)));
    }
}
~~~

**Giải thích từng điểm:**

- `Mono.defer` trì hoãn tạo publisher/hành vi tới lúc subscribe. Nếu `Math.multiplyExact` ném `ArithmeticException` trong callback, Reactor biểu diễn thành `onError`; method `quote(...)` không cần ném ngay trước khi trả Mono.
- Validation tạo `Mono.error(...)` có thông điệp xác định, giúp test kiểm **đúng lý do** thay vì chỉ kiểm bất kỳ error nào.
- `concatMap(this::quote)` subscribe từng line theo thứ tự, nên kết quả xuất hiện đúng thứ tự input. Nếu thay bằng `flatMap` cho các publisher bất đồng bộ, output có thể không giữ thứ tự; khi đó hợp đồng/test cần điều chỉnh.
- `quoteAll(List.of())` tạo Flux không có item và complete bình thường, không phải lỗi.
- `onErrorResume(IllegalArgumentException.class, ...)` chỉ xử lý đúng loại validation error. Overflow là `ArithmeticException` vẫn được phát downstream dưới dạng `onError`.
- Tính tiền bằng **đơn vị cent** thay vì `double` chỉ để tránh sai số floating-point trong bài demo; ứng dụng tài chính thật cần đặc tả đơn vị, rounding, giới hạn và kiểm soát overflow đầy đủ.

### 7.4. Test logic reactive bằng StepVerifier

**`src/test/java/com/example/reactive/PricingServiceStepVerifierTest.java`**

~~~java
package com.example.reactive;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import com.example.reactive.PricingService.OrderLine;
import com.example.reactive.PricingService.Quote;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class PricingServiceStepVerifierTest {

    private final PricingService service = new PricingService();

    @Test
    void quoteEmitsOneValueThenCompletes() {
        Mono<Quote> result =
                service.quote(new OrderLine("BOOK", 2, 12000L));

        StepVerifier.create(result)
                .expectNext(new Quote("BOOK", 24000L))
                .verifyComplete();
    }

    @Test
    void quoteCanBeCheckedWithPredicate() {
        StepVerifier.create(
                service.quote(new OrderLine("PEN", 3, 250L)))
                .expectNextMatches(quote ->
                        "PEN".equals(quote.sku())
                                && quote.totalCents() == 750L)
                .verifyComplete();
    }

    @Test
    void quoteCanBeCheckedWithSeveralAssertions() {
        StepVerifier.create(
                service.quote(new OrderLine("BAG", 1, 500L)))
                .assertNext(quote -> {
                    assertEquals("BAG", quote.sku());
                    assertEquals(500L, quote.totalCents());
                })
                .verifyComplete();
    }

    @Test
    void quoteAllEmitsValuesInInputOrderThenCompletes() {
        List<OrderLine> lines = List.of(
                new OrderLine("PEN", 1, 250L),
                new OrderLine("BOOK", 2, 12000L));

        StepVerifier.create(service.quoteAll(lines))
                .expectNext(
                        new Quote("PEN", 250L),
                        new Quote("BOOK", 24000L))
                .verifyComplete();
    }

    @Test
    void emptyListCompletesWithoutValues() {
        StepVerifier.create(service.quoteAll(List.of()))
                .verifyComplete();
    }

    @Test
    void invalidQuantityEmitsErrorWithoutValue() {
        StepVerifier.create(
                service.quote(new OrderLine("BOOK", 0, 12000L)))
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                                && "quantity must be positive"
                                        .equals(error.getMessage()))
                .verify();
    }

    @Test
    void invalidSkuHasSpecifiedErrorMessage() {
        StepVerifier.create(
                service.quote(new OrderLine("  ", 1, 100L)))
                .expectErrorSatisfies(error -> {
                    assertInstanceOf(
                            IllegalArgumentException.class, error);
                    assertEquals(
                            "sku is required", error.getMessage());
                })
                .verify();
    }

    @Test
    void firstValidLineMayArriveBeforeNextLineErrors() {
        List<OrderLine> lines = List.of(
                new OrderLine("PEN", 1, 250L),
                new OrderLine("BOOK", -1, 100L));

        StepVerifier.create(service.quoteAll(lines))
                .expectNext(new Quote("PEN", 250L))
                .verifyError(IllegalArgumentException.class);
    }

    @Test
    void arithmeticOverflowBecomesErrorSignal() {
        StepVerifier.create(
                service.quote(new OrderLine(
                        "BIG", 2, Long.MAX_VALUE)))
                .verifyError(ArithmeticException.class);
    }

    @Test
    void validationFailureCanRecoverToFallback() {
        StepVerifier.create(
                service.quoteOrDefault(new OrderLine(
                        "BOOK", 0, 100L)))
                .expectNext(new Quote("DEFAULT", 0L))
                .verifyComplete();
    }

    @Test
    void overflowIsNotSwallowedByValidationFallback() {
        StepVerifier.create(
                service.quoteOrDefault(new OrderLine(
                        "BIG", 2, Long.MAX_VALUE)))
                .verifyError(ArithmeticException.class);
    }

    @Test
    void nullListEmitsValidationError() {
        StepVerifier.create(service.quoteAll(null))
                .verifyError(IllegalArgumentException.class);
    }

    @Test
    void zeroInitialDemandRequiresExplicitRequests() {
        StepVerifier.create(Flux.range(1, 3), 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(1)
                .expectNext(3)
                .verifyComplete();
    }

    @Test
    void virtualTimeChecksDelayWithoutRealHour() {
        StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofHours(1))
                          .map(tick -> "sent"))
                .expectSubscription()
                .expectNoEvent(Duration.ofMinutes(59))
                .thenAwait(Duration.ofMinutes(1))
                .expectNext("sent")
                .verifyComplete();
    }

    @Test
    void emptyMonoHasCompletionButNoNextValue() {
        StepVerifier.create(Mono.<String>empty())
                .verifyComplete();
    }

    @Test
    void infiniteFluxCanBeCancelled() {
        StepVerifier.create(Flux.never())
                .expectSubscription()
                .thenCancel()
                .verify();
    }

    @Test
    void emittedValueCanBeFollowedByErrorNotComplete() {
        Flux<String> source = Flux.concat(
                Flux.just("FIRST"),
                Flux.error(new IllegalStateException("upstream failed")));

        StepVerifier.create(source)
                .expectNext("FIRST")
                .verifyError(IllegalStateException.class);
    }
}
~~~

**Tổng class này có 17 method `@Test`.** Không sử dụng `@SpringBootTest`, Mockito hoặc port HTTP vì mục tiêu là kiểm logic của một service Java **và các tín hiệu Reactor**. Object `PricingService` là instance thật, không bị mock, nên nếu thay công thức `quantity × unitPrice` thành phép cộng, test giá sẽ fail.

### Giải thích các nhóm kiểm thử

| Nhóm | Method tiêu biểu | Hợp đồng được bảo vệ |
| --- | --- | --- |
| Giá trị + complete | `quoteEmitsOneValueThenCompletes` | Một Quote đúng, không có giá trị thừa, kết thúc thành công |
| Predicate | `quoteCanBeCheckedWithPredicate` | Thuộc tính Quote đáp ứng điều kiện nghiệp vụ |
| Nhiều assertion | `quoteCanBeCheckedWithSeveralAssertions` | SKU và tổng tiền đều chính xác |
| Nhiều giá trị theo thứ tự | `quoteAllEmitsValuesInInputOrderThenCompletes` | Từng Quote đúng và thứ tự bảo toàn |
| Completion rỗng | `emptyListCompletesWithoutValues` | Không có đơn vẫn kết thúc bình thường |
| Error validation | `invalidQuantityEmitsErrorWithoutValue` | Sai quantity báo lỗi và không phát Quote |
| Error detail | `invalidSkuHasSpecifiedErrorMessage` | Loại và thông điệp lỗi phù hợp |
| Giá trị rồi lỗi | `firstValidLineMayArriveBeforeNextLineErrors` | `Flux` có thể phát kết quả từng phần trước terminal error |
| Overflow | `arithmeticOverflowBecomesErrorSignal` | Không trả tổng tiền sai khi tràn `long` |
| Recovery | `validationFailureCanRecoverToFallback` | Validation error được chuyển thành fallback rồi complete |
| Lỗi không recovery | `overflowIsNotSwallowedByValidationFallback` | Không nuốt lỗi overflow ngoài phạm vi fallback |
| Input null | `nullListEmitsValidationError` | Lỗi được truyền qua onError thay vì trả Flux null |
| Backpressure | `zeroInitialDemandRequiresExplicitRequests` | Có demand mới phát onNext; đúng số lượng |
| Virtual time | `virtualTimeChecksDelayWithoutRealHour` | Không phát trước một giờ và phát sau khi thời gian ảo tiến |
| Mono empty | `emptyMonoHasCompletionButNoNextValue` | Complete không tương đương phát một giá trị |
| Cancellation | `infiniteFluxCanBeCancelled` | Kết thúc test một stream không có terminal tự nhiên |
| Partial result + error | `emittedValueCanBeFollowedByErrorNotComplete` | Error là terminal riêng, không phải complete |

Với `firstValidLineMayArriveBeforeNextLineErrors`, `concatMap` đảm bảo item đầu được phát trước khi dòng thứ hai gây error. Nếu code chuyển sang một operator concurrent như `flatMap` và nguồn trở thành bất đồng bộ, thứ tự có thể thay đổi; lúc đó test phải dựa vào hợp đồng thực (có hay không yêu cầu thứ tự), không đơn giản “nới” matcher để giữ màu xanh.

### 7.5. Controller WebFlux và test HTTP slice riêng

`StepVerifier` kiểm một `Publisher`, nhưng nó **không kiểm HTTP routing, status code hay JSON serialization**. Để minh họa sự khác biệt, thêm controller và một test `WebTestClient`.

**`src/main/java/com/example/reactive/QuoteController.java`**

~~~java
package com.example.reactive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    private final PricingService pricingService;

    public QuoteController(PricingService pricingService) {
        this.pricingService = pricingService;
    }

    @GetMapping("/{sku}")
    public Mono<PricingService.Quote> quote(
            @PathVariable("sku") String sku,
            @RequestParam("quantity") int quantity,
            @RequestParam("unitPriceCents") long unitPriceCents) {

        return pricingService.quote(
                new PricingService.OrderLine(
                        sku, quantity, unitPriceCents));
    }
}
~~~

Controller trả `Mono<Quote>` để WebFlux serialize khi publisher phát value rồi complete. Khi publisher phát `onError`, Spring WebFlux cần exception handler/error-handling policy để xác định HTTP status/body mong muốn. **Không suy luận “`IllegalArgumentException` trong Mono luôn thành 400”** nếu chưa có exception mapping: ứng dụng mặc định có thể trả lỗi server tùy cấu hình.

**`src/test/java/com/example/reactive/QuoteControllerWebFluxTest.java`**

~~~java
package com.example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(QuoteController.class)
@Import(PricingService.class)
class QuoteControllerWebFluxTest {

    @Autowired
    private WebTestClient client;

    @Test
    void httpResponseContainsCalculatedQuote() {
        client.get()
                .uri(
                    "/api/quotes/BOOK"
                    + "?quantity=2&unitPriceCents=12000")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.sku").isEqualTo("BOOK")
                .jsonPath("$.totalCents").isEqualTo(24000);
    }
}
~~~

**`@WebFluxTest`** khởi tạo WebFlux slice và cấu hình `WebTestClient` mà không cần một HTTP server trên cổng thật. Vì service thông thường không tự được scan trong slice, `@Import(PricingService.class)` thêm implementation thật để test controller. Test này chứng minh request mapping và JSON response thành công; nó **không thay** 17 StepVerifier tests cho các nhánh validation, error, empty và cancellation.

**Số test của project:** 17 test methods từ `PricingServiceStepVerifierTest` + 1 test `QuoteControllerWebFluxTest` = **18 test methods**, không có `@ParameterizedTest`. Khi mọi file được tạo đúng và dependencies hợp lệ, dự kiến **18 test pass**. Đây là kết quả mong đợi theo mã, không phải kết quả chạy được ghi lại từ môi trường người học.

## 8. Thực thi project và đọc báo cáo

Trong thư mục gốc có `gradlew`/`gradlew.bat`:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng unit tests StepVerifier:

~~~bash
./gradlew test --tests 'com.example.reactive.PricingServiceStepVerifierTest'
~~~

Chạy riêng WebFlux slice:

~~~bash
./gradlew test --tests 'com.example.reactive.QuoteControllerWebFluxTest'
~~~

Gradle report thông dụng:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.reactive.PricingServiceStepVerifierTest.xml
    └── TEST-com.example.reactive.QuoteControllerWebFluxTest.xml
~~~

Không có `System.out.println` trong test runnable; **không có stdout nghiệp vụ cố định**. Gradle có thể báo `BUILD SUCCESSFUL` và cache task `UP-TO-DATE` khi chạy lại. Nếu muốn buộc chạy lại để điều tra, có thể dùng:

~~~bash
./gradlew test --rerun-tasks
~~~

Để tạo Gradle Wrapper cho project demo khi đã cài Gradle phù hợp, ví dụ:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó giữ các file Wrapper theo chính sách repository. Java toolchain đòi JDK 17 sẵn có hoặc cơ chế provisioning tương ứng; Wrapper không tự đảm bảo một JDK phù hợp. Trong dự án thực, **dùng version Wrapper đang được team quy định**, không nâng Gradle chỉ để sao chép bài ví dụ.

Nếu build fail ở dependency `reactor-test`, kiểm `testImplementation` và mạng/repository Maven; nếu fail ở compilation của controller test, kiểm rằng `spring-boot-starter-webflux` có mặt, không chỉ `spring-boot-starter-web`. Nếu báo 0 test, kiểm đường dẫn `src/test/java`, import `org.junit.jupiter.api.Test` và `useJUnitPlatform()`.

## 9. Backpressure: `request(n)` và StepVerifier

Reactive Streams cho phép subscriber kiểm soát số item nó sẵn sàng nhận qua demand. Mặc định, `StepVerifier.create(publisher)` thường request lượng lớn, phù hợp test giá trị cơ bản. Khi cần kiểm publisher **không phát onNext trước khi có demand**, dùng overload với `initialRequest=0`:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(1)
        .expectNext(3)
        .verifyComplete();
~~~

Diễn giải:

1. Subscribe với **0 item demand ban đầu**.
2. `thenRequest(2)` yêu cầu hai phần tử.
3. Dự kiến nhận `1`, rồi `2`.
4. `thenRequest(1)` cấp thêm demand.
5. Dự kiến nhận `3` và completion.

Test này kiểm cách `Flux.range` tôn trọng request. Với một publisher custom, cần bảo vệ cả trường hợp **không phát vượt request**; StepVerifier có cơ chế báo lỗi nếu publisher vi phạm tín hiệu/request theo các check của nó, nhưng những vấn đề concurrency/backpressure phức tạp vẫn có thể cần kiểm sâu hơn.

**Đừng dùng `initialRequest=0` rồi `expectNext(...)` mà quên `thenRequest`**: publisher hợp lệ sẽ không phát item, khiến test bị treo chờ giá trị chưa được yêu cầu. Dùng `verify(Duration)` hoặc cancellation phù hợp để tránh test CI kẹt vô hạn.

### `thenCancel` kiểm streaming không có completion

~~~java
StepVerifier.create(Flux.never())
        .expectSubscription()
        .thenCancel()
        .verify();
~~~

`Flux.never()` không phát value hay terminal. `thenCancel` là hành động của subscriber chứ không phải `onComplete`. Test trên không thể được thay bằng `verifyComplete()`, vì publisher **không có completion tự nhiên**.

Với các luồng sự kiện dài hạn, kịch bản thực tế có thể là “nhận 3 events, kiểm payload, sau đó cancel”. Nhưng nếu dùng `Flux.interval`, nên kiểm soát scheduler/virtual time để tránh flaky test theo timing thật.

## 10. Virtual time: không ngủ thật để test delay

Một test xử lý timeout/retry/delay có thể chờ 1 giờ theo logic, nhưng không thể để CI chạy 1 giờ chỉ vì phép thử. `StepVerifier.withVirtualTime` cho phép thay scheduler dùng bởi các operator Reactor bằng scheduler thời gian ảo trong phạm vi phép thử, khi được cấu hình đúng.

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(1)))
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(59))
        .thenAwait(Duration.ofMinutes(1))
        .expectNext(0L)
        .verifyComplete();
~~~

**Những chi tiết dễ sai:**

- **Publisher phải được tạo bên trong supplier** `() -> Mono.delay(...)`. Nếu tạo `Mono.delay` **trước khi bật virtual time**, nó có thể giữ scheduler thật và khiến test mất một giờ hoặc treo.
- `expectSubscription()` nên đứng trước `expectNoEvent(...)` vì subscription **cũng là một event** trong kịch bản; nếu gọi `expectNoEvent` ngay đầu, nó có thể fail vì thấy `onSubscribe`.
- `expectNoEvent(59 phút)` xác nhận chưa có onNext/terminal trong khoảng đó, trong khi `thenAwait(1 phút)` chỉ **tiến đồng hồ** mà không đòi vắng event trong khoảng.
- `Mono.delay` phát `0L` khi timer hoàn tất trong trường hợp này; test business với `map(tick -> "sent")` sẽ mong `"sent"`, như project runnable.
- Virtual time chỉ hoạt động như mong đợi khi operator dùng scheduler được virtualize. Sử dụng một scheduler được tự tạo/khởi động riêng, I/O thật, sleep thật hoặc HTTP network không tự chuyển thành thời gian ảo.
- Các chuỗi vô hạn hoặc operators lập lịch phức tạp có thể gây deadlock nếu kịch bản không cho clock tiến đúng bước. Test nên nhỏ, rõ và tránh tạo global schedulers ngoài supplier.

### Không dùng `Thread.sleep` để chứng minh reactive timing

Ví dụ này chậm và dễ flaky:

~~~java
// Không phải chiến lược kiểm thử khuyến nghị:
Thread.sleep(1000);
assertEquals("done", sharedState.get());
~~~

Ngoài tốn thời gian, nó dựa vào thread scheduling và không trực tiếp xác minh `onNext/onError/onComplete`. Dùng `withVirtualTime` cho operator Reactor dựa trên scheduler; dùng test timeout/clock/fake khác khi logic phụ thuộc external systems hoặc clock không do Reactor kiểm soát.

## 11. Timeouts cho `verify()`

Một pipeline có thể không bao giờ kết thúc do bug, thiếu request hoặc upstream không trả lời. Nhiều dạng `verify()`/`verifyComplete()` không tự đảm bảo một thời hạn đủ ngắn cho CI theo mong muốn của bạn. Khi có rủi ro treo, dùng overload có timeout:

~~~java
StepVerifier.create(Flux.just("A", "B"))
        .expectNext("A", "B")
        .expectComplete()
        .verify(Duration.ofSeconds(3));
~~~

Đây là snippet cần imports Reactor/JDK. Timeout 3 giây chỉ là minh họa cho publisher **không cần I/O**. Với integration test mạng thật, phải chọn timeout theo môi trường và SLA. Timeout quá ngắn khiến CI chập chờn; timeout không có giới hạn khiến lỗi reactive trở thành job treo lâu.

Một cách khác với pipeline cần hoàn tất trong 2 giây là sử dụng operator `timeout(Duration)`, nhưng nó **thay đổi behavior của publisher** và tạo lỗi timeout nếu chậm — khác với **timeout của StepVerifier**, là giới hạn thời gian dành cho phép thử. Đừng dùng hai loại timeout như thể cùng mục tiêu.

### `StepVerifierOptions.scenarioName` và nhãn chẩn đoán

Với các kịch bản dài, StepVerifier hỗ trợ đặt tên scenario hoặc một bước kỳ vọng (`as("...")` ở các điểm API phù hợp) để khi fail dễ nhận biết. Tuy nhiên, tên đẹp không thay assertion. Ưu tiên một method test có tên diễn tả quy tắc: `firstValidLineMayArriveBeforeNextLineErrors` rõ hơn `testFlux1`.

## 12. Test publisher do bạn điều khiển bằng `TestPublisher`

Khi cần chủ động phát `onNext`, `onComplete` hoặc `onError` vào một pipeline đang được subscribe, `reactor-test` cung cấp `TestPublisher`. Nó khác `StepVerifier`:

- **`StepVerifier`** là subscriber kiểm các tín hiệu nhận được.
- **`TestPublisher`** là nguồn dữ liệu thử nghiệm do test có thể điều khiển để phát tín hiệu.

Ví dụ:

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
        .then(() -> source.next("A", "B"))
        .expectNext("A", "B")
        .then(source::complete)
        .verifyComplete();
~~~

Đây là snippet trong một method test; thêm import `reactor.test.publisher.TestPublisher`. `then(...)` chạy callback **sau khi StepVerifier đã subscribe**. Việc phát `A`, `B` rồi complete được điều phối trong chính kịch bản, giúp kiểm publisher không bị phụ thuộc thread ngủ hoặc sự kiện bên ngoài.

Ví dụ phát lỗi:

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux())
        .then(() -> source.next(1))
        .expectNext(1)
        .then(() -> source.error(
                new IllegalStateException("broken")))
        .verifyError(IllegalStateException.class);
~~~

Khi test behavior operator như `retry`, `onErrorResume`, `switchIfEmpty`, `takeUntilOther`, dùng TestPublisher hoặc `Sinks` theo mục tiêu. Không dùng TestPublisher chỉ để thay `Flux.just("A")` ở mọi test; điều đó tăng độ dài và có thể làm kịch bản khó đọc.

**Cảnh báo:** TestPublisher còn có những chế độ đặc biệt để tạo các tình huống **vi phạm specification** nhằm thử khả năng chống lỗi của operator. Không bật chế độ noncompliant tùy tiện khi mục tiêu là test một publisher thông thường; nó có thể tạo tín hiệu mà một publisher hợp lệ không được phép phát.

## 13. Error recovery và các toán tử dễ làm test “xanh giả”

Khi mã có nhiều nhánh lỗi, các toán tử sau có ngữ nghĩa khác nhau:

| Toán tử | Đường tín hiệu downstream | Rủi ro nếu test yếu |
| --- | --- | --- |
| `map(...)` ném exception | Thường chuyển thành `onError` | Chỉ test dữ liệu đúng, không test lỗi mapping |
| `onErrorResume(...)` | Chuyển lỗi thành publisher khác | `verifyComplete` có thể che lỗi nếu fallback empty |
| `onErrorReturn(value)` | Thay lỗi bằng giá trị rồi complete | Có thể trả giá trị giả như dữ liệu thật |
| `onErrorMap(...)` | Đổi loại/đặc điểm lỗi rồi vẫn onError | Test sai class, không kiểm thông tin lỗi |
| `switchIfEmpty(...)` | Fallback khi **complete rỗng**, không phải onError | Lẫn “không tìm thấy” với “hệ thống lỗi” |
| `defaultIfEmpty(value)` | Phát giá trị nếu upstream empty | Test chỉ complete không kiểm fallback |
| `retry(n)` | Subscribe lại khi lỗi, có thể tạo lại side effect | Test không kiểm số lần hoặc điều kiện retry |
| `onErrorContinue(...)` | Có thể bỏ qua phần tử lỗi trong operator hỗ trợ | Dữ liệu mất mà test số lượng yếu không phát hiện |

Một bộ test tốt phân biệt rõ:

- **Thành công:** `onNext(expected) → onComplete`.
- **Không có dữ liệu hợp lệ:** `onComplete` không có `onNext`, nếu contract cho phép.
- **Lỗi hợp đồng:** `onError` đúng loại/thuộc tính.
- **Lỗi có thể phục hồi:** `onNext(fallback) → onComplete` và không “nuốt” lỗi ngoài phạm vi.
- **Lỗi sau partial data:** `onNext` đã phát trước `onError`, không tự rollback những item đã tới subscriber.

### `switchIfEmpty` không chạy khi có lỗi

~~~java
Mono<String> source = Mono.<String>error(
        new IllegalStateException("db unavailable"));

Mono<String> fallback = source.switchIfEmpty(
        Mono.just("not-found"));

StepVerifier.create(fallback)
        .verifyError(IllegalStateException.class);
~~~

`switchIfEmpty` chỉ phản ứng với **empty completion**, không thay error. Nếu API muốn chuyển DB unavailable thành một mã lỗi cụ thể, phải có error handling tương ứng; không dùng `switchIfEmpty` như một cách xử lý mọi lỗi.

### `onErrorResume` phải được test nhánh đúng và nhánh sai

Trong project, `quoteOrDefault` chỉ bắt `IllegalArgumentException`. Test `validationFailureCanRecoverToFallback` xác minh đúng nhánh recovery; test `overflowIsNotSwallowedByValidationFallback` xác minh `ArithmeticException` vẫn đi qua. Nếu chỉ có test fallback, một thay đổi sai thành `onErrorResume(error -> Mono.just(DEFAULT))` có thể lọt qua.

## 14. StepVerifier và `WebTestClient` là hai lớp test khác nhau

Một controller WebFlux có thể trả `Mono<ResponseDto>` hoặc `Flux<ResponseDto>`. Có hai mục tiêu khác nhau:

| Mục tiêu | Dùng | Nó chứng minh được gì? |
| --- | --- | --- |
| Service phát giá trị gì | `StepVerifier` | onNext, kiểu/value, thứ tự |
| Service complete/error đúng chưa | `StepVerifier` | Terminal signals |
| Service xử lý delay/backpressure | `StepVerifier` + virtual time/request | Reactive behavior |
| Route HTTP đúng chưa | `WebTestClient` | HTTP method/path/status |
| JSON response đúng chưa | `WebTestClient` | Serialization, headers, JSON body |
| Security filter/validation HTTP | `WebTestClient` với test context phù hợp | Contract HTTP khi filter/bean tham gia |
| HTTP server thật với port | `@SpringBootTest(RANDOM_PORT)` + client | Network/container behavior |
| Kết nối database/remote adapter | Integration test tương ứng | Hạ tầng thật theo phạm vi fixture |

`StepVerifier` **không tự biết HTTP status 404 hay 500**. Một `Mono.error(new IllegalArgumentException(...))` chỉ là **error signal** ở tầng reactive. HTTP status/body là kết quả của controller, exception handlers, Spring WebFlux và cấu hình error handling. Vì vậy test service bằng StepVerifier có thể đúng, trong khi HTTP API vẫn trả sai status.

Ngược lại, một test WebTestClient chỉ kiểm `expectStatus().isOk()` không bảo vệ các nhánh error của service. Dùng cả hai ở **đúng tầng**, không gộp mọi kịch bản vào full-context test.

### Điều gì xảy ra với `Flux` phát một phần rồi error qua HTTP?

Với reactive HTTP streaming, server có thể đã gửi headers và một số dữ liệu trước khi source phát `onError`. Khi headers/body đã commit, server không thể luôn đổi HTTP status từ 200 sang 500 và gửi một JSON lỗi chuẩn ở cuối như response thông thường. Đó là lý do test service cần xác nhận **chuỗi tín hiệu thực**, còn test HTTP streaming cần kiểm protocol/framing/error semantics của API thật.

## 15. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Test chạy nhưng không kiểm gì | Chỉ `StepVerifier.create(...)` mà quên terminal + `verify` | Kết thúc kịch bản bằng `verifyComplete`, `verifyError`, hoặc `expect...().verify()` |
| Test pass dù Mono rỗng, lẽ ra có data | Chỉ dùng `verifyComplete()` | Thêm `expectNext(expected)`/`assertNext` |
| Test mong complete nhưng nhận `onError` | SUT/mapper/validation phát exception | Kiểm root cause; viết test lỗi riêng nếu error là contract |
| Test mong error nhưng nhận complete | `onErrorResume`/`onErrorReturn` đã phục hồi | Assert fallback/empty theo hợp đồng, kiểm nhánh lỗi không phục hồi |
| Test fail vì thừa item | `expectNext` đã kiểm xong nhưng source còn onNext | Kiểm logic source hoặc đổi expected nếu hợp đồng cho phép |
| Test fail vì thứ tự | Dùng `flatMap` với xử lý bất đồng bộ | Kiểm yêu cầu ordering; `concatMap` khi cần bảo toàn |
| `verifyComplete` treo | Flux không hoàn tất hoặc source chưa có demand | Dùng `thenCancel`, `thenRequest`, timeout hoặc kiểm operator |
| Test dùng `expectNoEvent` đầu tiên và fail | Subscription cũng là tín hiệu được kiểm | Gọi `expectSubscription()` trước |
| Virtual time vẫn chờ thật | Publisher/scheduler tạo ngoài supplier hoặc dùng scheduler riêng | Tạo operator trong `withVirtualTime(() -> ...)`, kiểm scheduler |
| `NoClassDefFoundError: StepVerifier` | Thiếu `reactor-test` ở test classpath | Thêm test dependency tương ứng, kiểm exclude/version |
| StepVerifier báo sai số lượng request | `initialRequest=0` nhưng thiếu `thenRequest` | Cấp demand rõ ràng và kỳ vọng đúng số item |
| `NullPointerException` với `Mono.just(null)` | Reactor không cho `null` onNext | Dùng `Mono.empty`/`justOrEmpty` hoặc model trạng thái |
| `assertThrows` không thấy exception | Error xảy ra khi subscribe, không phải khi tạo Mono | Dùng `verifyError`/`expectErrorMatches` |
| Test pass khi service tính sai số | Mock chính publisher/service để trả expected | Dùng service thật và expected độc lập từ đặc tả |
| Error message test giòn | Test bám stack trace/string nội bộ | Kiểm type/error code ổn định, message khi là contract |
| WebFlux test trả 500 thay 400 | Reactive onError chưa được map thành HTTP error | Thêm/test exception handler phù hợp, không đổi StepVerifier để che |
| CI flaky do `Thread.sleep` | Phụ thuộc scheduling/time thật | Virtual time, controlled scheduler hoặc fake clock |
| `TestPublisher` phát trước subscriber | Test emit dữ liệu trước bước subscribe/then | Dùng `then(() -> source.next(...))` sau subscribe |
| Test lỗi ở startup Boot context | Dùng full Spring context không cần thiết/thiếu bean | Test reactive service thuần trước, chỉ mở context khi kiểm DI/WebFlux |
| Test chỉ assert `expectNextCount` | Bỏ qua nội dung item | Dùng `expectNext`, predicate hoặc `assertNext` nếu giá trị quan trọng |

### Quy trình đọc một thất bại StepVerifier

1. Đọc **“expected next signal”** trong AssertionError: kịch bản mong `onNext`, `onComplete` hay `onError`?
2. Đọc **“actual signal”**: có extra onNext, complete sớm, error bất ngờ hoặc không có tín hiệu?
3. Xác định publisher đang test có **lazy execution** không: dữ liệu/mapping chỉ chạy khi subscribe?
4. Kiểm operator **đổi ngữ nghĩa tín hiệu**: `onErrorResume`, `switchIfEmpty`, `retry`, `take`, `concatMap/flatMap`.
5. Nếu test treo, xem **backpressure demand, completion, scheduler và timeouts**.
6. Nếu test HTTP status khác expected, chuyển sang kiểm WebFlux exception mapping và server behavior; StepVerifier chỉ phản ánh reactive source.
7. Đổi code tạo một lỗi nhỏ có chủ đích để xác nhận test liên quan thực sự đỏ, rồi hoàn nguyên. Không sửa expected để chỉ giữ test xanh.

## 16. Thiết kế test bền vững với refactor

Một test tốt nên fail khi **hợp đồng tín hiệu** thay đổi nhưng vẫn pass nếu code được refactor hợp lệ.

| Thay đổi | Kết quả mong muốn |
| --- | --- |
| `quote` tính 2 × 12000 thành 12002 | **Fail** do expected Quote khác |
| `quote` trả Mono.empty với line hợp lệ | **Fail** vì thiếu onNext |
| `quote` phát Quote rồi `onError` thay complete | **Fail** vì terminal không đúng |
| `quoteAll` đổi thứ tự hai Quote trong khi hợp đồng cần thứ tự input | **Fail** |
| `quoteAll` bỏ qua line không hợp lệ rồi complete | **Fail** ở test mong onError |
| `quoteOrDefault` nuốt cả overflow | **Fail** ở test overflow không phục hồi |
| Tách helper validation thành private methods, giữ output/signals | **Pass** |
| Đổi cách tạo Mono/Flux nhưng giữ số và thứ tự tín hiệu | **Pass** |
| Đổi nội dung internal log mà contract không yêu cầu | **Pass** |
| Thay source thành infinite stream trong khi contract phải complete | **Fail/timeout**, sau đó sửa source chứ không xóa completion assertion |

Tránh test chỉ lặp lại implementation:

~~~java
// MẪU YẾU: expected tự gọi lại cùng công thức của SUT.
long expected = quantity * unitPriceCents;
StepVerifier.create(service.quote(line))
        .expectNext(new Quote(sku, expected))
        .verifyComplete();
~~~

Đây là snippet minh họa với biến đã có sẵn. Phép tính expected **không luôn sai** trong mọi trường hợp, nhưng nếu chỉ copy logic production (đặc biệt các điều kiện/rounding sai) thì test có thể xanh cùng bug. Dùng ví dụ nghiệp vụ đã được xác nhận và ca biên độc lập như `2 × 12000 = 24000`, `quantity=0` error, `Long.MAX_VALUE×2` overflow.

## 17. Bài tập tự luyện

**Bài A — nhánh empty:** Thêm method `findQuoteById(String id)` trả `Mono.empty()` khi ID không tồn tại. Viết một test mong **complete rỗng** và một test mong đúng Quote khi ID tồn tại. Kiểm rằng test tìm thấy không chỉ dùng `verifyComplete()`.

**Bài B — error trước và sau onNext:** Dùng `Flux.concat(Flux.just("A"), Flux.error(...))`. Viết `expectNext("A")`, sau đó `verifyError(IllegalStateException.class)`. Đổi thứ tự concatenation để lỗi xảy ra trước `A` và quan sát test fail.

**Bài C — message và type:** Với `OrderLine("BOOK", 0, 100)`, dùng `expectErrorMatches` kiểm cả class và message. Đổi validation trả một exception khác để test đỏ; hoàn nguyên.

**Bài D — fallback có giới hạn:** Thay `quoteOrDefault` để fallback cho mọi Throwable. Kiểm test overflow bắt buộc fail; sửa `onErrorResume` để chỉ fallback lỗi validation đã thỏa thuận.

**Bài E — virtual time:** Dùng `Mono.delay(Duration.ofHours(2))`. Test rằng 1 giờ 59 phút không có onNext, sau đó tiến 1 phút và mong giá trị. Tạo publisher trong supplier `withVirtualTime`, không tạo scheduler trước.

**Bài F — backpressure:** Dùng `Flux.range(1, 5)`, initialRequest=0, `thenRequest(3)`/`expectNext(1,2,3)` rồi `thenRequest(2)`/`expectNext(4,5)`, sau đó complete. Giải thích tại sao bỏ lần request thứ hai có thể làm test không hoàn tất.

**Bài G — controller boundary:** Trong `QuoteController`, thêm một `@RestControllerAdvice` chuyển `IllegalArgumentException` thành status 400 với JSON error code ổn định. Viết WebTestClient test cho response 400; đồng thời giữ StepVerifier test service mong đúng `onError`. Giải thích vì sao hai test có expected khác nhau ở hai tầng.

**Bài H — TestPublisher:** Tạo một nguồn TestPublisher, phát một item, sau đó error. Dùng StepVerifier kiểm value rồi error và xác nhận không có completion sau error. Tránh phát tín hiệu trước khi StepVerifier subscribe.

**Bài I — timeout:** Tạo `Flux.never()` và mô tả vì sao `verifyComplete` không phù hợp. Dùng `thenCancel().verify()` để kiểm kịch bản cancellation hoặc một `verify(Duration)` hữu hạn nếu mục tiêu test cần fail khi không hoàn tất.

## 18. Checklist kiểm thử StepVerifier

- [ ] Tôi đã hiểu Publisher phát **value**, **empty complete** hay **error** theo hợp đồng?
- [ ] Mỗi kịch bản kết thúc bằng `verify`, `verifyComplete`, `verifyError` hoặc biến thể kích hoạt tương đương?
- [ ] Với dữ liệu bắt buộc, tôi có `expectNext`/`assertNext` thay vì chỉ `verifyComplete`?
- [ ] Với nhiều giá trị, tôi kiểm số lượng **và thứ tự** khi hợp đồng yêu cầu?
- [ ] Với lỗi, tôi kiểm class/error code/message ổn định và không mong `onComplete` sau `onError`?
- [ ] Tôi có test nhánh `onErrorResume` và lỗi **không được** phục hồi?
- [ ] Tôi phân biệt `Mono<List<T>>` (một item) với `Flux<T>` (nhiều item)?
- [ ] Tôi không dùng `block()`, `subscribe()` thủ công hoặc `Thread.sleep` một cách thừa khi StepVerifier kiểm được tín hiệu?
- [ ] Với initialRequest=0, tôi có `thenRequest(n)` trước khi mong dữ liệu?
- [ ] Với virtual time, publisher/timed operator được tạo trong supplier và subscription được kỳ vọng trước `expectNoEvent`?
- [ ] Với infinite stream, tôi dùng cancellation hoặc giới hạn phù hợp thay vì đòi completion không tồn tại?
- [ ] Test service reactive có sử dụng logic thật, expected độc lập với implementation?
- [ ] Nếu cần kiểm HTTP status/JSON, tôi dùng WebTestClient hoặc integration test riêng, không kết luận từ StepVerifier?
- [ ] Test không phụ thuộc scheduler/time/network không kiểm soát khi có thể tránh?
- [ ] Gradle/JUnit report xác nhận test đã được thực thi, không chỉ task cache?

## 19. Tài liệu tham khảo chính thức

Đối chiếu API theo **bộ phiên bản Reactor và Spring Boot thực tế** của dự án. Ví dụ runnable dùng Spring Boot 3.3.5, vốn quản lý một bộ Reactor 3.6.x tương ứng.

- [Project Reactor 3.6 — Reference: Testing](https://projectreactor.io/docs/core/3.6.8/reference/#testing): ví dụ `StepVerifier`, terminal expectations, virtual time và TestPublisher.
- [Project Reactor — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `create`, `withVirtualTime`, `expectNext`, `expectError`, `verify`.
- [Project Reactor — Reactor Test Reference](https://projectreactor.io/docs/core/release/reference/testing.html): cách sử dụng `reactor-test` và các giới hạn của virtual time.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): test `@WebFluxTest`/`WebTestClient` và cách tổ chức integration tests.
- [Reactive Streams Specification](https://www.reactive-streams.org/): hợp đồng subscribe/request/onNext/onError/onComplete/cancel.

**Ghi nhớ:** `StepVerifier` không chỉ hỏi “Mono/Flux trả giá trị nào?”, mà hỏi “**cả chuỗi tín hiệu** có đúng hợp đồng không?”. Hãy kiểm nội dung `onNext`, số lượng/thứ tự, `onComplete` khi thành công và `onError` khi thất bại; dùng backpressure/virtual time khi cần. Việc đưa `verify` vào cuối kịch bản là bắt buộc để phép kiểm thực sự được chạy.
