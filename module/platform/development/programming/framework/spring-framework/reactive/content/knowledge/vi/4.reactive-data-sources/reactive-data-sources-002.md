# justOrEmpty cho giá trị có thể thiếu (Project Reactor / Spring WebFlux)

## 1. Mục tiêu và bài toán

Trong Java, tra cứu một khóa, đọc một cấu hình hoặc tích hợp API cũ có thể trả về `null` hay `Optional.empty()` khi không có giá trị. Trong Reactive Streams, `Publisher` không được gọi `onNext(null)`. `Mono.justOrEmpty(...)` của Project Reactor chuyển dữ liệu đơn **có thể thiếu** thành một nguồn `Mono<T>` hợp lệ: có phần tử thì phát phần tử đó, không có thì hoàn thành rỗng.

Mục tiêu sau bài: biết dùng hai overload nhận giá trị nullable và `Optional`; phân biệt empty với error; hiểu thời điểm đánh giá giá trị; chọn fallback; tránh blocking trong WebFlux; kiểm thử được cả trường hợp có và không có dữ liệu.

`Mono<T>` phát tối đa một phần tử. Ba tình huống chính:

~~~text
Có giá trị:  onSubscribe → onNext(value) → onComplete
Không có:    onSubscribe → onComplete
Thất bại:    onSubscribe → onError(cause)
~~~

**Hoàn thành rỗng không phải là lỗi.** `Mono.empty()` không phát `onNext`, trong khi `Mono.error(...)` phát `onError`. `Mono.never()` lại không phát dữ liệu lẫn terminal, nên khác hoàn toàn với empty.

## 2. Cú pháp và cơ chế

Hai dạng của API Reactor:

~~~java
static <T> Mono<T> justOrEmpty(T data)
static <T> Mono<T> justOrEmpty(Optional<? extends T> data)
~~~

Đây là chữ ký giản lược, bỏ qua các annotation về nullable ở các phiên bản Reactor. Chúng đều trả về `Mono<T>`, không tạo phần tử `null` hay một wrapper `Optional` trong luồng.

### 2.1. Giá trị nullable

~~~java
String nickname = "Linh";
Mono<String> present = Mono.justOrEmpty(nickname);

String missingNickname = null;
Mono<String> missing = Mono.justOrEmpty(missingNickname);
~~~

`present` sẽ phát `onNext("Linh")` rồi `onComplete` khi được subscribe. `missing` chỉ phát `onComplete`, vì giá trị đưa vào là `null`. Không nên viết `Mono.just(missingNickname)`: `just` yêu cầu dữ liệu khác `null` và ném `NullPointerException` ngay lúc tạo nguồn nếu đầu vào là `null`.

### 2.2. Optional

~~~java
Optional<String> name = Optional.of("Mai");
Optional<String> absent = Optional.empty();

Mono<String> first = Mono.justOrEmpty(name);
Mono<String> second = Mono.justOrEmpty(absent);
~~~

Với `Optional.of("Mai")`, nguồn phát `"Mai"`. Với `Optional.empty()`, nguồn không có `onNext` và hoàn thành bình thường.

So sánh hai biểu thức dễ nhầm:

~~~java
Mono<Optional<String>> boxed = Mono.just(Optional.empty());
Mono<String> unboxed = Mono.justOrEmpty(Optional.<String>empty());
~~~

`boxed` **vẫn phát một phần tử** là đối tượng `Optional.empty()`. `unboxed` không phát phần tử nào. Vì vậy, các toán tử `map`, `zip`, `hasElement` và fallback sẽ xử lý hai nguồn khác nhau.

### 2.3. Bảng đối chiếu

| Cách tạo nguồn | Dữ liệu | Kết quả |
| --- | --- | --- |
| `Mono.just("A")` | Khác null | Phát `"A"` rồi complete |
| `Mono.just(null)` | Null | Ném `NullPointerException` khi tạo nguồn |
| `Mono.justOrEmpty("A")` | Khác null | Phát `"A"` rồi complete |
| `Mono.justOrEmpty((String) null)` | Null | Chỉ complete |
| `Mono.justOrEmpty(Optional.of("A"))` | Optional có giá trị | Phát `"A"` rồi complete |
| `Mono.justOrEmpty(Optional.empty())` | Optional rỗng | Chỉ complete |
| `Mono.empty()` | Chủ động nguồn rỗng | Chỉ complete |
| `Mono.error(exception)` | Lỗi | `onError` |

Nếu truyền literal `null` trực tiếp, các overload có thể khiến cách suy luận kiểu khó rõ ràng. Khi minh họa, dùng biến đã khai báo kiểu hoặc cast như `(String) null`. Không dùng `null` như một phần tử được gửi xuống Subscriber.

## 3. Ví dụ đầy đủ với Java 17+ và Reactor

Ví dụ sau dùng nguồn `Mono` đồng bộ để đầu ra ổn định. Trong dự án Spring Boot đã có `spring-boot-starter-webflux`, có thể chạy lớp bằng IDE với Reactor trên classpath. Hoặc tạo dự án Gradle nhỏ:

~~~text
just-or-empty-demo/
├── build.gradle
└── src/main/java/JustOrEmptyDemo.java
~~~

Nội dung `build.gradle` (dùng Gradle có hỗ trợ Java toolchain):

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'JustOrEmptyDemo'
}
~~~

Nội dung `src/main/java/JustOrEmptyDemo.java`:

~~~java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import reactor.core.publisher.Mono;

public class JustOrEmptyDemo {

    private static void observe(String label, Mono<String> mono) {
        System.out.println("[" + label + "]");
        mono.subscribe(
                value -> System.out.println("onNext=" + value),
                error -> System.out.println(
                        "onError=" + error.getClass().getSimpleName()),
                () -> System.out.println("onComplete")
        );
    }

    public static void main(String[] args) {
        observe("present", Mono.justOrEmpty("Linh"));
        observe("null", Mono.justOrEmpty((String) null));
        observe("optional", Mono.justOrEmpty(Optional.of("Mai")));
        observe("optional empty",
                Mono.justOrEmpty(Optional.<String>empty()));

        observe("default", Mono.justOrEmpty((String) null)
                .defaultIfEmpty("Guest"));

        observe("required", Mono.justOrEmpty((String) null)
                .switchIfEmpty(
                    Mono.error(new IllegalArgumentException("missing"))));

        AtomicReference<String> value = new AtomicReference<>("before");
        Mono<String> snapshot = Mono.justOrEmpty(value.get());
        Mono<String> fresh = Mono.defer(
                () -> Mono.justOrEmpty(value.get()));
        value.set("after");

        observe("snapshot", snapshot);
        observe("fresh", fresh);
    }
}
~~~

Chạy tại thư mục có `build.gradle` bằng Gradle đã cài đặt; nếu dự án có wrapper thì thay `gradle` bằng `./gradlew`:

~~~bash
gradle -q run
~~~

Các dòng stdout của **chương trình** (không tính log từ Gradle):

~~~text
[present]
onNext=Linh
onComplete
[null]
onComplete
[optional]
onNext=Mai
onComplete
[optional empty]
onComplete
[default]
onNext=Guest
onComplete
[required]
onError=IllegalArgumentException
[snapshot]
onNext=before
onComplete
[fresh]
onNext=after
onComplete
~~~

Không có dòng `onNext=null` ở bất cứ trường hợp nào. `required` phát lỗi nên không gọi callback `onComplete`. Trong các nguồn đồng bộ này, callback chạy theo thứ tự như trên. Không áp dụng nhận định đó cho thứ tự log giữa nhiều subscriptions hoạt động song song hoặc các nguồn có scheduler khác nhau.

## 4. Giá trị được đọc lúc nào: eager snapshot và lazy lookup

Viết:

~~~java
Mono<String> source = Mono.justOrEmpty(readCurrentNickname());
~~~

thì Java gọi `readCurrentNickname()` **ngay khi đánh giá biểu thức** để xây dựng nguồn. `justOrEmpty` nhận giá trị đã được tính sẵn, không tự trì hoãn công việc. Mọi subscription sau đó thấy snapshot đã lưu (hoặc thấy nguồn rỗng).

Điều này được thể hiện trong ví dụ trên: giá trị ban đầu `"before"`, sau đó đổi thành `"after"`. `snapshot` vẫn phát `"before"` còn `fresh` phát `"after"`, vì nó chỉ đọc lại qua `Mono.defer` khi subscribe.

Khi muốn lấy dữ liệu tại thời điểm subscribe, có các lựa chọn:

~~~java
// Các đoạn minh họa này giả định đã có readCurrentNickname().
Mono<String> fromSupplier =
        Mono.fromSupplier(() -> readCurrentNickname());

Mono<String> fromCallable =
        Mono.fromCallable(() -> readCurrentNickname());

Mono<String> fromDefer =
        Mono.defer(() -> Mono.justOrEmpty(readCurrentNickname()));
~~~

- `fromSupplier` gọi `Supplier` khi subscribe; kết quả `null` được diễn giải là Mono rỗng.
- `fromCallable` chạy `Callable` khi subscribe; kết quả `null` là rỗng, ngoại lệ của Callable trở thành `onError`.
- `defer` cho phép trì hoãn **việc lựa chọn hoặc tạo ra cả một Mono**, rất hữu ích khi mỗi subscription cần nguồn khác.
- `justOrEmpty` thích hợp khi đã có `nullable T`/`Optional<T>` trong tay, ví dụ giá trị đọc tức thời từ bộ nhớ.

**Tính lazy không đồng nghĩa với chạy bất đồng bộ hay không blocking.** Các factory lazy mặc định không đưa thao tác chặn I/O sang thread khác. Nếu tra cứu cần chờ JDBC, file hoặc HTTP đồng bộ, phải cân nhắc scheduler và kiến trúc phù hợp.

## 5. Điều gì xảy ra với các toán tử khi Mono rỗng?

Ví dụ:

~~~java
Mono<String> result =
        Mono.justOrEmpty((String) null)
            .map(String::trim)
            .doOnNext(System.out::println);
~~~

Không có phần tử nên `map` không gọi `String.trim` và `doOnNext` không in gì. Tương tự, nhánh `flatMap`, `filter` hoặc `zipWhen` cần phần tử đầu vào sẽ không tạo được dữ liệu mới từ một nguồn rỗng nếu thiếu nguồn thay thế.

Đặc biệt:

- `doOnNext` chỉ chạy khi phát được phần tử.
- `doOnSuccess` của `Mono` **vẫn chạy khi hoàn thành rỗng**; tham số callback là `null` trong trường hợp này. Không dùng `doOnSuccess(value -> value.toString())` mà không xử lý `value == null`.
- `Mono.zip(a, b)` cần dữ liệu từ cả hai nguồn để tạo kết quả; nếu một Mono rỗng, không có cặp giá trị đầy đủ để phát. Đừng giả định zip sẽ chờ hoặc phát kết quả một phần.
- `Mono.empty()` đã phát tín hiệu hoàn tất bình thường, khác `Mono.never()` vốn không kết thúc.
- `block()` trong thử nghiệm có thể trả `null` khi Mono rỗng, nhưng không nên dùng `block()` trong luồng xử lý HTTP của WebFlux.

Trước khi chọn toán tử, xác định đúng ngữ nghĩa: `nullable đầu vào → empty`, `empty → fallback`, `error → xử lý ngoại lệ`.

## 6. Xử lý trường hợp không có giá trị

### 6.1. Một giá trị dự phòng: defaultIfEmpty

~~~java
Mono<String> displayName =
        Mono.justOrEmpty((String) null)
            .defaultIfEmpty("Khách");
~~~

Khi nguồn rỗng, kết quả phát `"Khách"`. Khi nguồn có giá trị, giá trị gốc được giữ nguyên. Phù hợp cho tên hiển thị, nhãn tùy chọn hoặc cấu hình có mặc định hợp lệ.

### 6.2. Một nguồn dự phòng: switchIfEmpty

~~~java
// primaryName và backupLookup() do ứng dụng cung cấp.
Mono<String> displayName =
        Mono.justOrEmpty(primaryName)
            .switchIfEmpty(
                Mono.defer(() -> backupLookup())
            );
~~~

`switchIfEmpty` đăng ký Mono dự phòng **chỉ khi nguồn chính hoàn thành rỗng**. Nó không chạy để xử lý `onError`. Sử dụng `Mono.defer` nếu chỉ nên **tạo hoặc tính nguồn dự phòng** khi thật sự thiếu dữ liệu, tránh thực hiện công việc đắt đỏ tại lúc ráp pipeline.

### 6.3. Thiếu dữ liệu là lỗi nghiệp vụ: switchIfEmpty + error

~~~java
Mono<String> requiredName =
        Mono.justOrEmpty((String) null)
            .switchIfEmpty(
                Mono.error(new IllegalArgumentException("name required"))
            );
~~~

Kết quả bây giờ là `onError(IllegalArgumentException)`. Quyết định này phụ thuộc nghiệp vụ; tìm không thấy một nickname tùy chọn có thể bình thường, nhưng thiếu một định danh bắt buộc có thể cần được chuyển thành lỗi.

### 6.4. Lỗi khác với empty

`onErrorResume` và `onErrorReturn` là cơ chế xử lý **tín hiệu lỗi**; chúng không chạy khi `Mono.justOrEmpty(null)` hoàn thành rỗng. Ngược lại, `defaultIfEmpty` và `switchIfEmpty` xử lý **thiếu phần tử**, không che các lỗi phát sinh từ kết nối, timeout hoặc xác thực.

Bảng mục đích:

| Nhu cầu | Toán tử |
| --- | --- |
| Thiếu giá trị thì dùng phần tử mặc định | `defaultIfEmpty(value)` |
| Thiếu giá trị thì thử nguồn khác | `switchIfEmpty(fallbackMono)` |
| Thiếu giá trị thì báo lỗi nghiệp vụ | `switchIfEmpty(Mono.error(...))` |
| Nguồn thật sự phát lỗi và cần phục hồi | `onErrorResume(...)` |

## 7. Áp dụng thực tế trong Spring WebFlux

### 7.1. Cache trong bộ nhớ: chuyển kết quả nullable thành HTTP 200/404

Đoạn controller dưới đặt **bên trong dự án Spring Boot WebFlux**, không phải một ứng dụng `main` độc lập:

~~~java
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class AliasController {
    private final Map<String, String> aliases = Map.of(
            "u1", "Linh",
            "u2", "Mai"
    );

    @GetMapping("/aliases/{id}")
    Mono<ResponseEntity<String>> findAlias(@PathVariable String id) {
        return Mono.justOrEmpty(aliases.get(id))
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
~~~

`Map.get(id)` trả `null` khi không có khóa, vì vậy `Mono.justOrEmpty` tạo nguồn rỗng. Nhánh `map` không chạy; `defaultIfEmpty` tạo phản hồi 404. Với khóa tồn tại, nhánh `map` trả 200 kèm tên.

~~~text
GET /aliases/u1       → HTTP 200, body: Linh
GET /aliases/missing  → HTTP 404, body rỗng
~~~

Không tự gọi `subscribe()` hoặc `block()` trong controller: Spring WebFlux tiếp nhận Publisher và quản lý subscription khi xử lý request.

### 7.2. Repository đã reactive: không bọc lại

Một kho dữ liệu reactive có thể trả `Mono<User>` trực tiếp:

~~~java
// Đoạn minh họa, User và repository thuộc ứng dụng:
Mono<User> user = reactiveUserRepository.findById(id);
~~~

Hãy dùng chính `Mono<User>` này rồi nối các toán tử cần thiết. Bọc bằng `Mono.justOrEmpty(user)` sẽ tạo nguồn lồng `Mono<Mono<User>>` hoặc làm sai kiểu kỳ vọng. Với API reactive, không cần ép dữ liệu trở lại `Optional` chỉ để gọi `justOrEmpty`.

### 7.3. Đổi API blocking cũ bằng fromCallable và scheduler

Giả sử `legacyRepository.findById(id)` truy cập JDBC đồng bộ và trả `Optional<User>`. Cách sau sẽ thực hiện blocking ngay khi ráp pipeline (nguy hiểm trên event loop):

~~~java
Mono<User> wrong =
        Mono.justOrEmpty(legacyRepository.findById(id));
~~~

Nếu chưa thể thay bằng client/database driver reactive, có thể tạo biên an toàn hơn:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

// Đoạn minh họa; User, id và legacyRepository có sẵn trong ứng dụng.
Mono<User> user =
        Mono.fromCallable(
                () -> legacyRepository.findById(id).orElse(null))
            .subscribeOn(Schedulers.boundedElastic());
~~~

`fromCallable` chờ đến subscription để thực thi lookup; `subscribeOn(boundedElastic())` bố trí thao tác có thể chặn trên scheduler phù hợp. Khi không tìm thấy, callable trả `null` nên hoàn thành rỗng; khi DAO ném exception, nguồn phát `onError`. Bounded elastic chỉ là cầu nối cho API blocking, không làm thao tác JDBC trở thành I/O nonblocking thực sự.

## 8. Kiểm thử hành vi bằng StepVerifier

Trong dự án có `reactor-test` và JUnit 5 ở test scope, có thể kiểm tra trực tiếp:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class JustOrEmptyTest {

    @Test
    void presentEmitsOneValue() {
        StepVerifier.create(Mono.justOrEmpty(Optional.of("Linh")))
                .expectNext("Linh")
                .verifyComplete();
    }

    @Test
    void nullCompletesAndMapDoesNotRun() {
        AtomicInteger calls = new AtomicInteger();
        Mono<String> source = Mono.justOrEmpty((String) null)
                .map(value -> {
                    calls.incrementAndGet();
                    return value.toUpperCase();
                });

        StepVerifier.create(source).verifyComplete();
        assertEquals(0, calls.get());
    }

    @Test
    void emptyOptionalUsesFallback() {
        StepVerifier.create(
                    Mono.justOrEmpty(Optional.<String>empty())
                        .defaultIfEmpty("Guest"))
                .expectNext("Guest")
                .verifyComplete();
    }

    @Test
    void missingCanBecomeError() {
        StepVerifier.create(
                    Mono.justOrEmpty((String) null)
                        .switchIfEmpty(
                            Mono.error(new IllegalArgumentException("missing"))))
                .expectError(IllegalArgumentException.class)
                .verify();
    }
}
~~~

`verifyComplete()` với Mono rỗng chứng minh không có `onNext` nhưng vẫn có `onComplete`. `expectNext` kiểm tra đúng giá trị duy nhất. `expectError` xác nhận trường hợp chuyển absence thành error thực sự phát `onError`, không phải complete.

## 9. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| `Mono.just(nullable)` | Ném NPE khi đầu vào null. | `Mono.justOrEmpty(nullable)` nếu thiếu giá trị là hợp lệ. |
| `Mono.just(Optional.empty())` rồi đợi source rỗng | Mono phát một đối tượng Optional. | `Mono.justOrEmpty(optional)` để unbox. |
| `Mono.justOrEmpty(expensiveLookup())` rồi nghĩ lookup chạy sau | Đối số được đánh giá trước lời gọi factory. | `fromSupplier`/`fromCallable` hoặc `defer`. |
| Mong `map` nhận null để tự xử lý | Empty không kích hoạt `map`. | `defaultIfEmpty` / `switchIfEmpty` cho absence. |
| Dùng `onErrorResume` để xử lý empty | Complete rỗng không phải error. | Chọn toán tử xử lý empty. |
| Dùng `doOnSuccess(v -> v.length())` vô điều kiện | `v` là null khi Mono rỗng. | Kiểm tra null hoặc dùng `doOnNext` khi cần phần tử thật. |
| `Mono.justOrEmpty(mono)` với đầu vào đã là Mono | Tạo Mono lồng và làm sai ý nghĩa pipeline. | Nối toán tử vào Mono gốc. |
| Đưa lookup blocking vào `justOrEmpty` trong WebFlux | Blocking đã xảy ra trước subscribe, có thể chặn event loop. | API reactive hoặc `fromCallable(...).subscribeOn(boundedElastic())`. |
| Coi dữ liệu thiếu tương đương exception | Làm sai luồng xử lý tùy chọn. | Xác định rõ điều kiện absent và điều kiện error theo nghiệp vụ. |

Để quan sát, thêm `.log("lookup")` vào nguồn trước khi subscribe. Với đầu vào null, log sẽ cho thấy terminal `onComplete` mà không có `onNext`. Khi chẩn đoán lỗi thời điểm đọc dữ liệu, nhớ phân biệt lúc *lắp ghép* pipeline với lúc *subscribe*.

## 10. Tự kiểm tra

1. `Mono.justOrEmpty((String) null)` phát tín hiệu nào? **Chỉ `onComplete`.**
2. `Mono.just(Optional.empty())` có empty không? **Không; nó phát một `Optional.empty()` làm giá trị.**
3. `Mono.justOrEmpty(cache.get(key))` có gọi `cache.get` mỗi lần subscribe không? **Không; lời gọi xảy ra khi xây dựng Mono.**
4. Nếu nguồn rỗng, `map(String::trim)` có chạy không? **Không.**
5. Khi thiếu dữ liệu muốn gọi API dự phòng, chọn toán tử nào? **`switchIfEmpty`; thêm `defer` nếu cần hoãn tạo nguồn dự phòng.**
6. Nếu lookup ném exception thì `defaultIfEmpty` có phục hồi không? **Không; nó chỉ xử lý completion rỗng.**
7. `fromCallable` có tự chuyển một lời gọi JDBC blocking khỏi event loop không? **Không; phải bố trí scheduler hoặc dùng API thực sự nonblocking.**

**Điểm cần nhớ:** `Mono.justOrEmpty` là cầu nối giữa `null` / `Optional.empty()` của Java và nguồn Reactive Streams có **0 hoặc 1 phần tử**. Có giá trị thì phát `onNext` và hoàn thành; thiếu giá trị thì hoàn thành rỗng. Khi thời điểm đọc hoặc tính chất blocking của nguồn mới là vấn đề, hãy dùng factory lazy và scheduler phù hợp, đồng thời giữ riêng logic xử lý empty và error.

## Tài liệu tham khảo

- [Project Reactor Mono Javadoc — justOrEmpty, fromSupplier, fromCallable, doOnSuccess](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- [Project Reactor Reference Guide — Which operator do I need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html).
- [Reactive Streams JVM specification](https://github.com/reactive-streams/reactive-streams-jvm).
- [Spring Framework WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html).
