# Mono<Void> biểu diễn hoàn tất mà không mang dữ liệu

Trong **Project Reactor** và **Spring WebFlux**, `Mono<Void>` là một `Mono` dùng để báo rằng **một thao tác đã hoàn tất thành công hoặc thất bại**, trong khi **không cung cấp giá trị kết quả cho subscriber**. Loại này đặc biệt hữu ích với các lệnh ghi, xóa, giải phóng tài nguyên, gửi tín hiệu kết thúc HTTP hoặc thực hiện một chuỗi thao tác mà người gọi chỉ cần biết khi nào tất cả hoàn tất.

Điểm mấu chốt: **“không có dữ liệu” không đồng nghĩa “không thực hiện công việc”.** Một `Mono<Void>` vẫn có thể đại diện cho I/O bất đồng bộ, nhiều tác vụ phối hợp, lỗi và hủy subscription.

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ có thể:

- Phân biệt `Mono<Void>`, `Mono.empty()`, `Mono<T>`, `Mono.never()` và `void` của Java.
- Giải thích các tín hiệu `onSubscribe`, `onComplete`, `onError`, `cancel`; hiểu vì sao một `Mono<Void>` thành công không có `onNext`.
- Tạo `Mono<Void>` bằng `Mono.empty()`, `Mono.fromRunnable(...)` hoặc `then()` và hiểu thời điểm tác vụ thực sự chạy.
- Kết hợp công việc tuần tự với `then`, `thenEmpty`, `thenReturn`; kết hợp nhiều nguồn chỉ quan tâm hoàn tất bằng `Mono.when`.
- Dùng `Mono<Void>` đúng trong Spring WebFlux, xử lý lỗi, quan sát luồng và kiểm thử completion bằng `StepVerifier`.

## 2. Giao thức tín hiệu: hoàn tất không mang giá trị

`Mono<T>` có thể phát **tối đa một** phần tử kiểu `T`, rồi hoàn tất; cũng có thể hoàn tất mà không phát phần tử hoặc kết thúc bằng lỗi. Hai đường thành công cơ bản là:

~~~text
Mono<T> có dữ liệu:
onSubscribe -> onNext(value) -> onComplete

Mono<T> rỗng, hoặc Mono<Void> thành công:
onSubscribe -> onComplete

Đường thất bại:
onSubscribe -> onError(error)
~~~

`Mono<Void>` theo quy ước biểu diễn đường thành công **không có `onNext`**, tức không có `Void` instance nào được giao cho downstream. Java có `java.lang.Void` nhưng không cho ứng dụng tạo instance theo cách thông thường; Reactor cũng **không chấp nhận `null` như một tín hiệu `onNext`**. Vì thế:

~~~java
Mono<Void> done = Mono.empty(); // Hợp lệ: hoàn tất rỗng.
Mono<Void> invalid = Mono.just(null); // Sai: ném NullPointerException.
~~~

Dòng `Mono.just(null)` ở đây **cố ý minh họa lỗi**, không đưa vào chương trình chạy. Nếu API Java trả về `null` và muốn coi đó là không có phần tử, `Mono.justOrEmpty(nullableValue)` có thể tạo một Mono rỗng; tuy nhiên `null` **không bao giờ trở thành phần tử được phát**.

Các tín hiệu có ý nghĩa riêng:

| Tín hiệu | Ý nghĩa với `Mono<Void>` |
| --- | --- |
| `onSubscribe(subscription)` | Đăng ký đã hình thành; công việc có thể bắt đầu tùy nguồn và scheduler. |
| `onNext(value)` | Không có trong trường hợp `Mono<Void>` thành công thông thường. |
| `onComplete()` | Công việc đã kết thúc thành công, không cần trả dữ liệu. |
| `onError(error)` | Công việc thất bại; không tiếp theo bằng `onComplete`. |
| `cancel()` | Subscriber yêu cầu dừng; việc hủy có thể giải phóng công việc/tài nguyên nếu nguồn hợp tác, không phải tín hiệu thành công. |

**Đừng suy luận rằng `Mono<Void>` nào cũng hoàn tất.** Ví dụ `Mono.never()` có thể không phát cả dữ liệu, kết thúc lẫn lỗi; một thao tác I/O cũng có thể treo nếu thiếu timeout. `Mono<Void>` diễn tả **kiểu đầu ra**, không phải cam kết thời gian hoặc tính thành công.

## 3. `Mono<Void>` khác `void` và `Mono<T>` rỗng ra sao?

| Biểu thức | Kiểu | Điều người gọi nhận được |
| --- | --- | --- |
| `void delete()` | `void` Java | Phương thức kết thúc lời gọi; không có publisher để chờ/ghép, trừ khi API khác cung cấp cơ chế riêng. |
| `Mono<Void> delete()` | Publisher Reactor | Tín hiệu hoàn tất hoặc lỗi khi publisher được subscribe; có thể ghép với pipeline khác. |
| `Mono<String> find()` phát `"ok"` | `Mono<String>` | Một giá trị `String`, rồi hoàn tất. |
| `Mono<String> find()` trả `Mono.empty()` | `Mono<String>` | Không tìm thấy giá trị/không có kết quả, rồi hoàn tất (ý nghĩa cụ thể do API quy định). |
| `Mono<Void> save()` hoàn tất | `Mono<Void>` | Thao tác hoàn tất, không có giá trị dữ liệu. |
| `Mono<Void> save()` lỗi | `Mono<Void>` | Nhận `onError`, không nhận tín hiệu thành công. |

**Điểm tinh tế:** Cả `Mono<String>` rỗng và `Mono<Void>` thành công đều có cùng luồng tín hiệu `onComplete` không có `onNext`. Sự khác nhau nằm ở **hợp đồng API và ý nghĩa nghiệp vụ**: `Mono<String>` thường hàm ý có thể có một kết quả; `Mono<Void>` thông báo người gọi không được trông đợi một kết quả.

Không dùng `Mono<Void>` để biểu diễn “đã lưu thành công hay chưa” bằng một giá trị `true/false`: khi cần trạng thái nghiệp vụ có thể kiểm tra, dùng `Mono<Boolean>`, `Mono<Result>` hoặc một phản hồi có kiểu rõ ràng. `Mono<Void>` thành công chỉ xác nhận thao tác **đã hoàn thành theo hợp đồng của publisher**; nó không tự bảo đảm giao dịch được commit, dữ liệu đã bền vững, hoặc bên thứ ba đã xác nhận, nếu những cam kết đó không có trong API nguồn.

## 4. Ví dụ chạy được với Java 17 và Reactor

Tạo dự án Gradle nhỏ, gồm hai file sau. **`Mono.fromRunnable`** chuyển một `Runnable` không trả giá trị thành `Mono<Void>`; hành động được thực thi khi có subscription. **`then`** ghép công việc kế tiếp sau khi công việc trước hoàn tất thành công.

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

application {
    mainClass = 'MonoVoidDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tệp `src/main/java/MonoVoidDemo.java`:

~~~java
import reactor.core.publisher.Mono;

public class MonoVoidDemo {
    public static void main(String[] args) {
        Mono<Void> save = Mono.fromRunnable(
            () -> System.out.println("Đã lưu")
        );
        Mono<Void> audit = Mono.fromRunnable(
            () -> System.out.println("Đã ghi audit")
        );

        Mono<Void> process = save
            .then(audit)
            .doOnNext(value -> System.out.println("onNext: " + value))
            .doOnSuccess(value -> System.out.println("doOnSuccess: " + value));

        System.out.println("Đã tạo pipeline");

        process.subscribe(
            value -> System.out.println("Subscriber onNext: " + value),
            error -> System.out.println("Subscriber onError: " + error),
            () -> System.out.println("Subscriber onComplete")
        );
    }
}
~~~

Chạy `gradle run` (hoặc `./gradlew run` nếu dự án có Gradle Wrapper; trên Windows dùng `gradlew.bat run`). Phần stdout của **chính chương trình**, không tính log Gradle:

~~~text
Đã tạo pipeline
Đã lưu
Đã ghi audit
doOnSuccess: null
Subscriber onComplete
~~~

**Vì sao ra đúng các dòng này?**

1. Khi xây dựng `save`, `audit` và `process`, `Mono.fromRunnable` chưa chạy; do đó log đầu tiên là “Đã tạo pipeline”.
2. `subscribe` kích hoạt pipeline đồng bộ của ví dụ. `save` hoàn tất, tiếp theo mới thực hiện `audit`.
3. `doOnNext` và callback `onNext` trong `subscribe` **không được gọi**, vì không có giá trị nào được phát.
4. `doOnSuccess` của Reactor được gọi khi `Mono` thành công. Với `Mono` rỗng, đối số của callback này là **`null` để biểu thị không có giá trị**, dù không có sự kiện `onNext(null)`.
5. Cuối cùng subscriber nhận `onComplete`. Trong ví dụ này hành động đồng bộ được chạy ngay trên luồng gọi `subscribe`; dùng `Mono<Void>` tự nó không tạo thread mới.

**Lưu ý về dependency:** ví dụ dùng một phiên bản Reactor được chỉ định riêng để chạy độc lập. Trong Spring Boot, hãy để Spring Boot BOM quản lý phiên bản tương thích của Reactor thay vì ép một phiên bản riêng như ví dụ này.

## 5. Các cách tạo `Mono<Void>`

### 5.1. Hoàn tất ngay và không thực hiện gì: `Mono.empty()`

~~~java
Mono<Void> ready = Mono.empty();
~~~

Đây là tín hiệu thành công rỗng sẵn có. Không nhầm với “tác vụ lưu đã hoàn tất”: nếu chưa hề thực hiện thao tác cần thiết, trả `Mono.empty()` có thể làm caller tin rằng công việc đã xong.

### 5.2. Bao bọc công việc đồng bộ: `Mono.fromRunnable`

~~~java
Mono<Void> cleanup = Mono.fromRunnable(
    () -> System.out.println("Đóng tài nguyên tạm")
);
~~~

Hành động bắt đầu khi subscribe. Nếu `Runnable` ném exception, exception trở thành tín hiệu `onError`. Không đưa I/O chặn kéo dài trực tiếp lên event-loop WebFlux; cần chọn tích hợp reactive hoặc scheduler phù hợp và giới hạn tài nguyên.

### 5.3. Chuyển publisher có dữ liệu sang chỉ quan tâm hoàn tất: `then()`

~~~java
Mono<Void> done = Mono.just("payload")
    .doOnNext(text -> System.out.println("Đang xử lý " + text))
    .then();
~~~

`then()` **bỏ qua kết quả `onNext` ở phía downstream**, đợi upstream hoàn tất thành công rồi phát `onComplete`; nếu upstream lỗi thì downstream nhận lỗi. `then()` **không hủy bỏ việc chạy upstream**. Với `Flux<T>`, `then()` cũng đợi toàn bộ nguồn hoàn tất, nên áp dụng lên luồng vô hạn sẽ không tự sinh completion.

### 5.4. Chuyển tín hiệu của tác vụ bất đồng bộ sang `Mono<Void>`

~~~java
Mono<Void> doneLater = Mono.delay(
    java.time.Duration.ofMillis(100)
).then();
~~~

`Mono.delay(...)` phát một giá trị kiểu `Long` sau khoảng thời gian định trước; `then()` bỏ giá trị này và chỉ giữ hoàn tất. Đây là minh họa điều khiển tín hiệu, **không phải cách chờ I/O thực tế**.

## 6. Ghép nhiều công việc đúng cách

Khi công việc A phải xong trước B, dùng `then`:

~~~java
Mono<Void> stepA = Mono.fromRunnable(
    () -> System.out.println("A xong")
);
Mono<Void> stepB = Mono.fromRunnable(
    () -> System.out.println("B xong")
);

Mono<Void> sequential = stepA.then(stepB);
~~~

`stepB` chỉ được subscribe sau khi `stepA` hoàn tất **thành công**. Nếu `stepA` lỗi, `stepB` không được chạy theo đường này.

Để chuyển sang một publisher **có giá trị** sau khi hoàn tất:

~~~java
Mono<String> result = stepA.thenReturn("OK");
// "OK" chỉ được phát sau khi stepA hoàn tất thành công.
~~~

Hoặc chuyển sang publisher được xác định động/tạo sẵn:

~~~java
Mono<String> result = stepA.then(Mono.just("OK"));
~~~

Với một publisher chỉ mang completion:

~~~java
Mono<Void> full = stepA.thenEmpty(stepB);
~~~

`thenEmpty(Publisher<Void>)` đợi upstream hoàn tất rồi đợi publisher kế tiếp hoàn tất, vẫn không phát giá trị. Khi cả hai đều có kiểu `Mono<Void>`, `stepA.then(stepB)` cũng dễ đọc.

Nếu hai tác vụ **không phụ thuộc thứ tự** và chỉ cần biết khi nào cả hai kết thúc:

~~~java
Mono<Void> both = Mono.when(stepA, stepB);
~~~

`Mono.when` subscribe các nguồn tham gia, hoàn tất khi **tất cả** nguồn hoàn tất thành công, và theo mặc định báo lỗi khi một nguồn thất bại (có thể hủy các nguồn còn lại). Nó **không bảo đảm hai Runnable đồng bộ chạy trên hai thread**; song song thật sự phụ thuộc tính bất đồng bộ/scheduler của từng nguồn. Nếu cần chờ tất cả nguồn kết thúc trước khi gom lỗi, tìm hiểu `Mono.whenDelayError`.

**Không dùng `Mono.zip(stepA, stepB)` để đợi hai `Mono<Void>`.** `zip` cần mỗi nguồn phát **một giá trị** để kết hợp; khi một nguồn hoàn tất rỗng, phép zip không có cặp giá trị để tạo kết quả và có thể hoàn tất sớm/hủy các nguồn khác. Đợi completion thì dùng `when`, hoặc tạo thứ tự rõ ràng bằng `then`.

## 7. Bẫy thường gặp khi dùng operator phụ thuộc vào dữ liệu

Vì `Mono<Void>` thành công không phát phần tử, những operator chỉ thực hiện khi có `onNext` sẽ không chạy callback:

~~~java
Mono<Void> task = Mono.fromRunnable(
    () -> System.out.println("Task chạy")
);

// Hành động trong flatMap KHÔNG chạy khi task thành công rỗng:
Mono<String> wrong = task.flatMap(ignored -> Mono.just("next"));

// Thực hiện sau khi task hoàn tất:
Mono<String> correct = task.thenReturn("next");
~~~

Tương tự:

- `map(...)`, `filter(...)`, `flatMap(...)`, `doOnNext(...)` chờ phần tử; nếu upstream rỗng thì callback tương ứng không chạy.
- `doOnSuccess(value -> ...)` **có chạy** khi `Mono` hoàn tất thành công; `value == null` cho trường hợp rỗng. Không dùng callback này để giả vờ có giá trị `Void`.
- `doOnTerminate(...)` có thể quan sát kết thúc thành công hoặc lỗi; `doFinally(signalType -> ...)` còn quan sát đường hủy. Đây là hook quan sát, không thay thế propagation của pipeline.
- `switchIfEmpty(fallback)` được kích hoạt khi upstream **không phát giá trị**. Vì `Mono<Void>` thành công vốn rỗng, dùng `switchIfEmpty` sau một `Mono<Void>` thường kích hoạt fallback **ngay cả khi tác vụ đầu đã thành công**. Nếu muốn chạy việc kế tiếp sau completion, hãy dùng `then` hoặc `thenEmpty`.
- `defaultIfEmpty(value)` cần một giá trị hợp lệ để phát. Không thể dùng `null` làm “giá trị mặc định” trong Reactor, và `Mono<Void>` không phải nơi mang dữ liệu mặc định. Dùng `thenReturn(result)` khi cần trả một giá trị sau thành công.

Ví dụ minh họa bẫy `switchIfEmpty`:

~~~java
Mono<Void> saved = Mono.fromRunnable(
    () -> System.out.println("Đã lưu")
);

Mono<Void> surprising = saved.switchIfEmpty(
    Mono.fromRunnable(
        () -> System.out.println("Fallback cũng chạy")
    )
);
~~~

Nếu subscribe `surprising`, **cả hai** dòng có thể được in theo thứ tự trên, vì `saved` hoàn tất mà không có `onNext`. Không nhầm việc hoàn tất rỗng với một kết quả thất bại. Muốn xử lý lỗi, dùng `onErrorResume` hoặc một chính sách lỗi được định nghĩa rõ.

## 8. Xử lý lỗi, hủy và timeout

`Mono<Void>` vẫn có đầy đủ khả năng lan truyền lỗi:

~~~java
Mono<Void> task = Mono.fromRunnable(() -> {
    throw new IllegalStateException("Không thể lưu");
});

Mono<Void> logged = task.doOnError(error ->
    System.err.println("Lỗi: " + error.getMessage())
);
~~~

`doOnError` chỉ quan sát, **không nuốt lỗi**. Downstream vẫn nhận `onError`. Nếu có fallback hợp lệ:

~~~java
Mono<Void> recovered = task.onErrorResume(error -> {
    System.err.println("Dùng chính sách phục hồi: " + error);
    return Mono.empty();
});
~~~

Sau recovery, pipeline sẽ hoàn tất thành công. Cách này **cố ý chuyển lỗi thành thành công**, chỉ phù hợp khi nghiệp vụ cho phép; không lạm dụng với lỗi cần báo về client. Nếu muốn giữ lỗi sau khi ghi log, chỉ dùng `doOnError` hoặc trả `Mono.error(error)` trong nhánh recovery.

Với tác vụ có thể không kết thúc:

~~~java
Mono<Void> bounded = someOperation
    .timeout(java.time.Duration.ofSeconds(5));
~~~

Ở ví dụ trên, `someOperation` là một biến `Mono<Void>` có sẵn từ hệ thống (đoạn tích hợp, không phải chương trình độc lập). `timeout` chuyển việc chờ quá hạn thành lỗi và hủy upstream theo hợp đồng của operator; khả năng ngắt thao tác I/O vật lý phụ thuộc nguồn/driver. `cancel()` cũng là tín hiệu hợp tác: không thể mặc định rằng ngoại tác đã thực hiện sẽ được rollback.

Một hành động có thể hoàn tất thành công, lỗi hoặc bị hủy; **cancellation không tương đương với `onComplete`**. Khi cần cleanup, cân nhắc `doFinally`, `usingWhen` hay API quản lý tài nguyên phù hợp, đồng thời kiểm tra các đường success/error/cancel trong kiểm thử.

## 9. `Mono<Void>` trong Spring WebFlux

### 9.1. Endpoint trả 204 No Content sau khi xóa

Nhiều interface Spring Data Reactive, chẳng hạn `ReactiveCrudRepository.deleteById(...)`, trả `Mono<Void>`: caller quan tâm thao tác xóa đã kết thúc, không cần một đối tượng làm response body.

Đây là **đoạn tích hợp vào ứng dụng Spring Boot WebFlux có sẵn**, trong đó `accountRepository` là repository reactive đã khai báo và inject:

~~~java
@DeleteMapping("/accounts/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public Mono<Void> deleteAccount(@PathVariable String id) {
    return accountRepository.deleteById(id);
}
~~~

Các import tương ứng:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.ResponseStatus;
import reactor.core.publisher.Mono;
~~~

Khi controller **trả publisher cho WebFlux**, framework chịu trách nhiệm subscribe, chờ completion và hoàn tất HTTP response; nếu publisher lỗi, lỗi đi qua cơ chế xử lý ngoại lệ của WebFlux. `@ResponseStatus(HttpStatus.NO_CONTENT)` đặt trạng thái **204**; **`Mono<Void>` tự nó không đồng nghĩa status 204**. Mã ví dụ không tự kiểm tra bản ghi có tồn tại; nếu nghiệp vụ cần phân biệt “không tìm thấy” và “đã xóa”, bổ sung bước truy vấn và chuyển sang lỗi HTTP 404 theo quy ước API.

**Không gọi `.subscribe()` trong controller rồi trả `Mono.empty()` ngay.** Làm vậy tách công việc ra khỏi lifecycle HTTP, response có thể hoàn tất trước khi ghi/xóa xong; lỗi, timeout và hủy cũng khó được truyền về đúng nơi.

### 9.2. Chuỗi lọc và hoàn tất response

Trong WebFlux, `WebFilterChain.filter(exchange)` trả `Mono<Void>`, biểu thị quá trình xử lý request qua chain đã kết thúc. `ServerHttpResponse.setComplete()` cũng trả `Mono<Void>`, cho phép framework biết khi nào việc hoàn tất response kết thúc. Ở đây **tín hiệu completion** quan trọng hơn một đối tượng trả về.

Ví dụ *khái niệm* trong một `WebFilter`:

~~~java
@Override
public Mono<Void> filter(
    ServerWebExchange exchange,
    WebFilterChain chain
) {
    return chain.filter(exchange)
        .doFinally(signal -> recordCompletion(signal));
}
~~~

Đoạn trên cần class và phương thức `recordCompletion` do ứng dụng định nghĩa; không phải file Java chạy độc lập. `doFinally` quan sát cả hoàn tất/lỗi/hủy. Hook đo lường nên đủ nhanh và an toàn; không thực hiện I/O chặn trực tiếp trong callback của event-loop.

### 9.3. WebClient khi chỉ cần biết request hoàn tất

Với một `WebClient` đã cấu hình, có thể dùng:

~~~java
Mono<Void> finished = webClient.post()
    .uri("/notifications")
    .bodyValue(new Notification("hello"))
    .retrieve()
    .toBodilessEntity()
    .then();
~~~

Đây là đoạn tích hợp, cần khai báo `Notification` và `webClient` trong ứng dụng. `toBodilessEntity()` tạo `Mono<ResponseEntity<Void>>` (có thể đọc status/header), sau đó `then()` cố ý loại bỏ giá trị response entity để chỉ giữ tín hiệu hoàn tất/lỗi. Nếu cần kiểm tra mã trạng thái thành công theo chính sách nghiệp vụ, **giữ `ResponseEntity<Void>` để xử lý trước khi gọi `then()`**. Với `retrieve()`, các phản hồi lỗi HTTP 4xx/5xx mặc định được chuyển thành lỗi Reactor trừ khi được cấu hình lại.

## 10. Kiểm thử completion, lỗi và thời điểm side effect

Thư viện `reactor-test` cung cấp `StepVerifier` để kiểm tra tín hiệu chính xác, thay vì đoán theo thời gian chờ hay log. Dependency test đã có trong `build.gradle` ở mục 4.

Tạo `src/test/java/MonoVoidTest.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MonoVoidTest {
    @Test
    void runsOnSubscriptionAndCompletesWithoutItem() {
        AtomicInteger counter = new AtomicInteger();
        Mono<Void> operation = Mono.fromRunnable(
            counter::incrementAndGet
        );

        assertEquals(0, counter.get()); // Chưa subscribe.

        StepVerifier.create(operation)
            .verifyComplete();          // Không có expectNext.

        assertEquals(1, counter.get()); // Đã chạy đúng một lần.
    }

    @Test
    void failureDoesNotCompleteSuccessfully() {
        Mono<Void> operation = Mono.fromRunnable(() -> {
            throw new IllegalStateException("failed");
        });

        StepVerifier.create(operation)
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "failed".equals(error.getMessage()))
            .verify();
    }

    @Test
    void thenReturnEmitsValueAfterCompletion() {
        Mono<String> operation = Mono.<Void>empty()
            .thenReturn("OK");

        StepVerifier.create(operation)
            .expectNext("OK")
            .verifyComplete();
    }
}
~~~

Chạy `gradle test` (hoặc lệnh Gradle Wrapper tương ứng). Ba test mong đợi **PASS**:

- `Mono<Void>` hoàn tất mà không có `expectNext`, và side effect chỉ chạy sau subscription.
- Ngoại lệ trong `Runnable` được chuyển thành `onError`.
- `thenReturn` cho phép chuyển từ completion-only sang publisher có giá trị.

Có thể kiểm tra completion không phụ thuộc số lượng phần tử đã yêu cầu bằng `StepVerifier.create(Mono.<Void>empty(), 0).verifyComplete()`: `onComplete` không phải một `onNext`, nên không tiêu thụ demand. Tuy nhiên công việc của một publisher bất kỳ vẫn có thể đòi hỏi demand để tiến triển; ví dụ `Flux.range(...).then()` cần tiêu thụ nguồn trước khi hoàn tất.

## 11. Sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `Mono.just(null)` để “trả Void” | `NullPointerException`; Reactor không cho phát `null`. | Dùng `Mono.empty()`, `Mono.fromRunnable(...)` hoặc `then()`. |
| Dùng `flatMap` sau `Mono<Void>` để chạy tác vụ tiếp theo | Callback không chạy vì không có `onNext`. | Dùng `then(nextMono)` hoặc `thenEmpty(nextPublisher)`. |
| Dùng `Mono.zip` để chờ nhiều `Mono<Void>` | Không có giá trị để ghép, có thể hoàn tất sớm. | Dùng `Mono.when` cho nhiều nguồn completion-only. |
| Coi `doOnSuccess(null)` là đã phát một phần tử null | Hiểu sai giao thức, gây logic kiểm tra sai. | Nhận biết đây là callback báo success trên Mono rỗng. |
| Dùng `switchIfEmpty` để “chạy khi thao tác thất bại” | Fallback được gọi cả sau completion thành công của `Mono<Void>`. | Dùng `onErrorResume` cho lỗi; `then` cho việc tiếp theo. |
| Tự `subscribe` trong service/controller rồi trả `Mono.empty()` | Mất chuỗi quản lý lỗi, chờ hoàn tất và cancellation. | Trả pipeline `Mono<Void>` để WebFlux subscribe và quản lý. |
| Coi `Mono<Void>` là luôn HTTP 204 | Trạng thái HTTP do controller/response quyết định. | Đặt `@ResponseStatus(NO_CONTENT)` hoặc `ResponseEntity` phù hợp. |
| Gọi `block()` trên luồng xử lý WebFlux | Có thể nghẽn event-loop và phá tính phản ứng. | Trả publisher từ handler; dùng các API reactive có khả năng kết hợp. |
| Chỉ kiểm thử “không ném exception” | Bỏ qua subscription, completion, error và cleanup. | Dùng `StepVerifier.verifyComplete()`, `expectError...` và kiểm tra side effect. |

## 12. Nguyên tắc thiết kế API với `Mono<Void>`

Hãy chọn `Mono<Void>` khi câu hỏi mà caller cần trả lời là: **“Khi nào việc này kết thúc, hoặc vì sao nó thất bại?”** Ví dụ thao tác xóa, ghi, gửi lệnh hoặc đóng response không cần trả dữ liệu. Khi người gọi còn cần số bản ghi bị ảnh hưởng, mã xác nhận nghiệp vụ, ID mới hay phiên bản sau cập nhật, chọn `Mono<Long>`, `Mono<Id>`, `Mono<UpdateResult>` hoặc kiểu kết quả phù hợp.

Khi xây dựng pipeline, kiểm tra theo thứ tự:

1. **Có side effect thật không?** Tạo đúng publisher mô tả công việc; đừng trả `Mono.empty()` trước khi công việc đã được ghép vào pipeline.
2. **Ai subscribe?** Trong WebFlux, thường framework là subscriber cuối; trong test dùng `StepVerifier`. Tránh subscribe nội bộ rồi đánh mất lỗi/completion.
3. **Cần giá trị hay chỉ cần hoàn tất?** Dùng `map/flatMap` cho nguồn có giá trị; dùng `then/when` cho luồng chỉ cần hoàn tất.
4. **Lỗi đi đâu?** Giữ `onError` nếu caller cần biết thất bại; recovery chỉ khi nghiệp vụ cho phép.
5. **Công việc có thể hủy/chờ quá lâu không?** Cấu hình timeout, cleanup và kiểm thử cancel/error với nguồn phù hợp.

**Ghi nhớ:** `Mono<Void>` là **publisher của tín hiệu hoàn tất**, không phải “một `Mono` phát ra đối tượng `Void`”. Thành công rỗng thể hiện bằng `onComplete`; thất bại bằng `onError`. Để nối tác vụ sau completion hãy dùng `then`; để chờ nhiều tác vụ completion-only hãy dùng `when`.

## Tài liệu tham khảo

- Reactor Core Reference Guide: https://projectreactor.io/docs/core/release/reference/
- Reactor `Mono` API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Reactive Streams specification: https://www.reactive-streams.org/
