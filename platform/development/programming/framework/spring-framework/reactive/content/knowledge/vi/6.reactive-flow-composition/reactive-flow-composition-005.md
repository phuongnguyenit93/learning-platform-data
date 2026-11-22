# defaultIfEmpty và switchIfEmpty trong Reactor

Trong **Spring WebFlux** và **Project Reactor**, một `Mono<T>` hoặc `Flux<T>` có thể **hoàn tất thành công mà không phát phần tử nào**. Hai operator `defaultIfEmpty` và `switchIfEmpty` xử lý đúng trường hợp đó, nhưng làm hai việc khác nhau:

- **`defaultIfEmpty(defaultValue)`**: nếu nguồn rỗng, phát **một giá trị mặc định** đã được cung cấp; nếu nguồn có dữ liệu, giữ nguyên các phần tử của nguồn.
- **`switchIfEmpty(alternatePublisher)`**: nếu nguồn rỗng, **chuyển sang subscribe một publisher dự phòng**; publisher này có thể tự thực hiện công việc bất đồng bộ và phát 0, 1 hoặc nhiều phần tử tùy loại nguồn.

Cả hai chỉ kích hoạt phương án dự phòng khi **nguồn hoàn tất mà không có bất kỳ `onNext` nào**. Chúng không tự bắt lỗi, không tự retry và không quyết định HTTP 404/204 thay cho ứng dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện luồng **rỗng** qua các tín hiệu Reactive Streams và phân biệt với một phần tử `null`, lỗi hoặc nguồn chưa hoàn tất.
2. Chọn đúng `defaultIfEmpty` khi có một giá trị thay thế, hoặc `switchIfEmpty` khi có một công việc/nguồn dữ liệu thay thế.
3. Giải thích thời điểm tạo publisher dự phòng và thời điểm nó được **subscribe**, dùng `Mono.defer` khi cần trì hoãn việc xây dựng nguồn.
4. Hiểu phạm vi của operator trên `Mono` và `Flux`, cũng như tác động của `filter`, `flatMap`, `then` và `Mono<Void>`.
5. Áp dụng xử lý trường hợp không tìm thấy dữ liệu trong Spring WebFlux, phân biệt dữ liệu rỗng với HTTP 4xx/5xx.
6. Kiểm thử nhánh nguồn có dữ liệu, rỗng, lỗi và nhu cầu phát phần tử bằng `StepVerifier`.

## 2. “Empty” nghĩa là gì trong Reactive Streams?

Reactor xây dựng trên mô hình `Publisher`/`Subscriber`. Một publisher có thể gửi các tín hiệu sau:

~~~text
Có dữ liệu:  onSubscribe -> onNext(value) -> onComplete
Rỗng:       onSubscribe ---------------------> onComplete
Bị lỗi:     onSubscribe ---------------------> onError(error)
Bị hủy:     subscriber gọi cancel() (không đồng nghĩa onComplete)
~~~

Với một `Mono<T>`, số phần tử thành công là 0 hoặc 1. Với một `Flux<T>`, số phần tử là 0 đến nhiều, có thể không giới hạn nếu nguồn không kết thúc.

**Rỗng là một trạng thái kết thúc của publisher:** hoàn tất thành công **không có `onNext`**. Một nguồn đang chờ mãi như `Mono.never()` không phải publisher đã hoàn tất rỗng. Một nguồn báo lỗi qua `onError` cũng không phải publisher hoàn tất rỗng.

`null` không phải một phần tử hợp lệ trong các tín hiệu `onNext` của Reactor:

~~~java
Mono<String> none = Mono.empty();            // Rỗng: hợp lệ.
String nullable = null;
Mono<String> optional = Mono.justOrEmpty(nullable); // Rỗng: hợp lệ.
Mono<String> invalid = Mono.just(null);     // Sai: NullPointerException.
~~~

Dòng cuối **cố ý minh họa lỗi**, không đặt vào chương trình chạy. Dùng `Mono.justOrEmpty(value)` khi muốn biến giá trị Java nullable thành publisher có 0 hoặc 1 phần tử; không phát trực tiếp `null`.

Bảng sau chỉ ra operator nào cần thiết:

| Nguồn | Tín hiệu nguồn | `defaultIfEmpty("guest")` | `switchIfEmpty(Mono.just("guest"))` |
| --- | --- | --- | --- |
| `Mono.just("Alice")` | `onNext("Alice")`, `onComplete` | Phát `"Alice"` | Phát `"Alice"`, không subscribe fallback |
| `Mono.empty()` | `onComplete` | Phát `"guest"`, rồi hoàn tất | Subscribe fallback, phát `"guest"`, rồi hoàn tất |
| `Mono.error(ex)` | `onError(ex)` | Vẫn phát lỗi `ex` | Vẫn phát lỗi `ex` |
| `Mono.never()` | Không có tín hiệu kết thúc | Không tạo giá trị mặc định | Không chuyển sang fallback |

Khi nói “nguồn có dữ liệu”, chỉ cần **ít nhất một** `onNext` trước completion. Với `Flux.just("A", "B")`, cả hai operator đều truyền `"A"`, `"B"` và completion như bình thường.

## 3. `defaultIfEmpty`: thay nguồn rỗng bằng một giá trị

Cú pháp phổ biến:

~~~java
Mono<String> displayName = Mono.<String>empty()
    .defaultIfEmpty("Khách");

Flux<Integer> numbers = Flux.<Integer>empty()
    .defaultIfEmpty(0);
~~~

Kết quả lần lượt là `Mono` phát `"Khách"` và `Flux` phát một phần tử `0`.

Nếu nguồn không rỗng, `defaultIfEmpty` không thêm dữ liệu:

~~~java
Flux<Integer> original = Flux.just(2, 4, 6);
Flux<Integer> result = original.defaultIfEmpty(0);
// Kết quả: 2, 4, 6 — không có phần tử 0 được thêm vào.
~~~

**Đặc điểm:**

- Chỉ cần một **giá trị** dự phòng, không cần thêm lời gọi repository hay HTTP.
- Giá trị mặc định phải phù hợp với kiểu `T` và không thể là `null`.
- Nếu tạo giá trị dự phòng bằng lời gọi phương thức, biểu thức tham số được Java đánh giá **ngay lúc xây dựng pipeline**. Vì vậy `defaultIfEmpty(expensiveValue())` có thể làm công việc tốn kém ngay cả khi nguồn có dữ liệu. Khi dự phòng cần tính toán bất đồng bộ hoặc chỉ nên được tạo khi cần, dùng `switchIfEmpty` với nguồn lazy.
- Nếu nguồn lỗi, lỗi được chuyển tiếp. Nếu nguồn không hoàn tất, giá trị mặc định không xuất hiện.
- Khi nguồn rỗng và downstream chưa yêu cầu phần tử, giá trị dự phòng phải đợi demand phù hợp mới được phát; completion bình thường không tiêu thụ một phần tử demand.

Ví dụ người dùng thiếu tên hiển thị:

~~~java
Mono<String> shownName = userRepository.findById(userId)
    .map(User::displayName)
    .defaultIfEmpty("Người dùng ẩn danh");
~~~

Đây là **đoạn tích hợp**, với `User` và `userRepository` do ứng dụng định nghĩa. Nó thích hợp nếu hợp đồng nghiệp vụ cho phép hiển thị một giá trị mặc định khi không tìm thấy user (hoặc khi các bước biến đổi trả publisher rỗng). Nếu “không tìm thấy” phải gây lỗi, hãy xem mục 9.

### Tác động của các operator trước đó

Một publisher ban đầu có dữ liệu vẫn có thể trở thành **rỗng sau khi lọc**:

~~~java
Mono<Integer> source = Mono.just(3);

Mono<Integer> result = source
    .filter(n -> n % 2 == 0)
    .defaultIfEmpty(-1);

// result phát -1, vì filter bỏ phần tử 3.
~~~

`defaultIfEmpty` kiểm tra **dòng tín hiệu tại đúng vị trí của nó**, không kiểm tra nguồn gốc ban đầu có từng chứa phần tử hay không. Đặt nó trước hay sau `filter` có thể tạo kết quả khác:

~~~java
Mono<Integer> a = Mono.<Integer>empty()
    .defaultIfEmpty(3)
    .filter(n -> n % 2 == 0);   // Rỗng: 3 bị loại.

Mono<Integer> b = Mono.<Integer>empty()
    .filter(n -> n % 2 == 0)
    .defaultIfEmpty(3);         // Phát 3.
~~~

Đây là lý do cần đọc pipeline theo thứ tự từ trên xuống, thay vì xem `defaultIfEmpty` như một quy tắc chung cho toàn ứng dụng.

## 4. `switchIfEmpty`: chuyển sang Publisher dự phòng

Khi không thể thay bằng một hằng số và cần đọc từ cache, tìm từ dịch vụ khác hoặc gọi một tác vụ reactive, dùng `switchIfEmpty`:

~~~java
Mono<User> user = primaryRepository.findById(id)
    .switchIfEmpty(backupRepository.findById(id));
~~~

Đây là đoạn tích hợp. Nếu publisher từ kho chính phát user, nguồn dự phòng **không được subscribe**. Nếu kho chính **hoàn tất rỗng**, Reactor subscribe publisher dự phòng và lấy tín hiệu từ nó. Nếu kho chính báo lỗi, `switchIfEmpty` **không** coi lỗi đó là “không tìm thấy”.

### `switchIfEmpty` và `defaultIfEmpty` khác nhau ở điểm nào?

| Tiêu chí | `defaultIfEmpty(value)` | `switchIfEmpty(publisher)` |
| --- | --- | --- |
| Đối số | Một giá trị `T` hợp lệ | Một `Publisher<? extends T>` phù hợp |
| Kết quả khi nguồn rỗng | Phát đúng một giá trị dự phòng | Phát các tín hiệu từ publisher dự phòng |
| Có thể gọi nguồn bất đồng bộ khác? | Không trực tiếp | Có, khi publisher dự phòng được subscribe |
| `Flux` dự phòng có nhiều phần tử? | Không, chỉ một giá trị | Có, publisher dự phòng có thể phát nhiều phần tử |
| Nguồn ban đầu có `onNext`? | Giữ dữ liệu nguồn | Không subscribe publisher dự phòng |
| Nguồn ban đầu `onError`? | Chuyển lỗi | Chuyển lỗi |
| Có thay thế `onErrorResume`? | Không | Không |

Khi nguồn là `Flux` rỗng, dự phòng có thể là cả một Flux:

~~~java
Flux<String> events = Flux.<String>empty()
    .switchIfEmpty(Flux.just("cached-A", "cached-B"));
// Phát cached-A, cached-B.
~~~

Trong khi đó:

~~~java
Flux<String> events = Flux.<String>empty()
    .defaultIfEmpty("cached-A");
// Chỉ phát cached-A.
~~~

Cần nhớ: `switchIfEmpty` **chỉ đổi nguồn một lần khi nguồn đầu tiên hoàn tất rỗng**; nó không phải cơ chế “đổi nguồn sau từng phần tử bị thiếu”, không kiểm tra từng khóa trong một danh sách và không tự retry với nhiều publisher.

## 5. Quan trọng: Publisher lazy và fallback được xây dựng khi nào?

Một ngộ nhận phổ biến là: “`switchIfEmpty` chỉ gọi mã tạo fallback khi nguồn rỗng”. Đúng hơn phải tách **hai thời điểm**:

1. **Tạo đối tượng publisher:** Java đánh giá biểu thức truyền vào `switchIfEmpty(...)` ngay khi bạn xây dựng pipeline.
2. **Subscribe publisher dự phòng:** `switchIfEmpty` chỉ subscribe nó khi nguồn chính kết thúc rỗng.

Với publisher Reactor được xây dựng theo cách lazy, việc tạo đối tượng thường không có I/O ngay; nhưng side effect trong phương thức tạo publisher có thể xảy ra ngay từ lúc xây dựng.

Ví dụ **không nên làm** khi `createBackupNow()` là phương thức có side effect tốn kém:

~~~java
Mono<String> result = primary
    .switchIfEmpty(Mono.just(createBackupNow()));
// createBackupNow() được Java thực thi ngay khi dòng này chạy,
// cho dù primary về sau có phát dữ liệu.
~~~

Đây là đoạn minh họa với `primary` và `createBackupNow()` do ứng dụng định nghĩa. Nếu không muốn tính giá trị fallback khi nguồn chính có dữ liệu, hãy hoãn việc tạo nó:

~~~java
Mono<String> result = primary
    .switchIfEmpty(Mono.defer(
        () -> Mono.just(createBackupNow())
    ));
~~~

`Mono.defer` nhận supplier tạo một `Mono` mới **khi có subscription vào publisher được defer**. Nhờ `switchIfEmpty`, supplier này chỉ được gọi khi thực sự đi vào nhánh fallback.

Nếu `createBackupNow()` là I/O **blocking**, việc đặt nó trong `Mono.defer` chỉ trì hoãn thời điểm gọi, **không tự chuyển I/O sang thread thích hợp**. Khi phải gọi API blocking, xem phương án `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` cùng giới hạn concurrency; trong WebFlux, ưu tiên API reactive không blocking.

Một dạng có repository:

~~~java
Mono<User> user = cache.find(id)
    .switchIfEmpty(Mono.defer(
        () -> repository.findById(id)
    ));
~~~

Việc tạo publisher từ repository được trì hoãn đến khi cần fallback. Nếu `repository.findById(id)` đã là publisher cold và phương thức xây dựng không làm side effect, có thể truyền trực tiếp; `defer` là lựa chọn rõ ràng khi muốn kiểm soát thời điểm **tạo** publisher hoặc lấy dữ liệu phụ thuộc trạng thái tại thời điểm subscribe.

**Ghi nhớ:** `switchIfEmpty` đã điều kiện hóa việc **subscribe** fallback; `defer` còn điều kiện hóa cả việc **tạo** publisher fallback.

## 6. Ví dụ Java 17 chạy được và stdout xác định

Tạo một dự án Gradle đơn giản với Reactor Core.

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
    mainClass = 'EmptyFallbackDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tệp `src/main/java/EmptyFallbackDemo.java`:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class EmptyFallbackDemo {
    public static void main(String[] args) {
        Mono<String> defaultValue = Mono.<String>empty()
            .defaultIfEmpty("anonymous");

        System.out.println("default = " + defaultValue.block());

        Mono<String> primary = Mono.<String>empty()
            .doOnSubscribe(s -> System.out.println("subscribe primary"))
            .doOnTerminate(() -> System.out.println("primary completed"));

        Mono<String> backup = Mono.defer(() -> {
            System.out.println("create fallback");
            return Mono.just("backup");
        });

        Mono<String> chosen = primary.switchIfEmpty(backup);

        System.out.println("before switch subscription");
        System.out.println("switch = " + chosen.block());

        Flux<String> sequence = Flux.<String>empty()
            .switchIfEmpty(Flux.just("cached", "default"));

        System.out.println("flux = " + sequence.collectList().block());

        Mono<String> present = Mono.just("live")
            .switchIfEmpty(Mono.defer(() -> {
                System.out.println("unexpected fallback");
                return Mono.just("backup");
            }));

        System.out.println("present = " + present.block());
    }
}
~~~

Chạy từ thư mục dự án bằng `gradle run`. Nếu đã có Gradle Wrapper, dùng `./gradlew run` (trên Windows: `gradlew.bat run`). Phần stdout do chương trình in ra, không tính log Gradle:

~~~text
default = anonymous
before switch subscription
subscribe primary
primary completed
create fallback
switch = backup
flux = [cached, default]
present = live
~~~

**Giải thích theo thứ tự:**

1. `defaultValue.block()` subscribe vào Mono rỗng, nên `defaultIfEmpty` phát `"anonymous"`.
2. Việc tạo biến `chosen` chưa subscribe pipeline, vì vậy `before switch subscription` xuất hiện trước log của nguồn chính.
3. Khi `chosen.block()` subscribe, nguồn chính in hai dòng: được subscribe, rồi hoàn tất rỗng.
4. Chỉ sau đó `switchIfEmpty` subscribe `backup`; supplier `Mono.defer` in `create fallback` và trả `Mono.just("backup")`.
5. Với `Flux` rỗng, fallback phát **hai phần tử**, được `collectList()` gom thành danh sách. Đây là nguồn hữu hạn nên gom danh sách an toàn.
6. `present` phát `"live"`; fallback **không được subscribe**, nên dòng `unexpected fallback` không xuất hiện.

`block()` ở ví dụ này chỉ dùng trong **ứng dụng command-line** để in kết quả đồng bộ. Trong controller/service Spring WebFlux chạy trên event-loop, trả publisher để WebFlux subscribe, không gọi `block()` trong handler.

Phiên bản Reactor được chọn để dự án độc lập có thể tái hiện. Với dự án Spring Boot, để Spring Boot BOM quản lý các dependency Reactor tương thích thay vì ghim riêng phiên bản từ ví dụ.

## 7. Trường hợp lỗi: empty khác với error

Ví dụ:

~~~java
Mono<String> failed = Mono.<String>error(
    new IllegalStateException("database unavailable")
);

Mono<String> result = failed.switchIfEmpty(Mono.just("cached"));
// result vẫn phát onError(IllegalStateException).
~~~

`switchIfEmpty` không xử lý lỗi vì upstream không kết thúc bằng `onComplete` rỗng. `defaultIfEmpty` cũng tương tự.

Để đưa lỗi sang publisher dự phòng, dùng `onErrorResume` khi **nghiệp vụ thật sự cho phép**:

~~~java
Mono<String> recovered = failed.onErrorResume(
    error -> Mono.just("cached")
);
~~~

Nếu cần cả hai chính sách:

~~~java
Mono<String> resolved = source
    .switchIfEmpty(Mono.defer(() -> lookupSecondary()))
    .onErrorResume(error -> recoverFromFailure(error));
~~~

Đây là đoạn tích hợp: `source`, `lookupSecondary` và `recoverFromFailure` được định nghĩa bởi ứng dụng, có kiểu trả về tương thích `Mono<String>`. Hành vi:

- Nguồn chính có giá trị: dùng giá trị.
- Nguồn chính rỗng: thử nguồn phụ.
- Nguồn chính hoặc nguồn phụ phát lỗi: `onErrorResume` xử lý lỗi phù hợp chính sách.

**Thứ tự operator thay đổi ý nghĩa.** Nếu viết:

~~~java
Mono<String> resolved = source
    .onErrorResume(error -> Mono.empty())
    .switchIfEmpty(Mono.just("cached"));
~~~

Bất cứ lỗi nào được `onErrorResume` chuyển thành completion rỗng sẽ dẫn tới `switchIfEmpty` chạy; tức các lỗi đã bị biến thành “không có dữ liệu”. Cách này có thể che giấu lỗi database/network nghiêm trọng. Hãy phân biệt “không tìm thấy” (empty) với “hệ thống thất bại” (error) trước khi quyết định phục hồi.

### Cancellation không phải empty

Khi subscriber hủy `Subscription`, điều đó không làm `switchIfEmpty` tự chạy fallback. Fallback chỉ được chọn sau khi nhận tín hiệu completion rỗng từ upstream. Nếu một publisher treo, thêm timeout phù hợp:

~~~java
Mono<String> bounded = source
    .timeout(java.time.Duration.ofSeconds(3))
    .switchIfEmpty(Mono.just("not-found"));
~~~

Trong ví dụ trên, timeout gây **`onError`**, không sinh một completion rỗng, vì vậy `not-found` không được phát chỉ do timeout. Nếu nghiệp vụ cần xử lý timeout thành một giá trị/publisher khác, hãy cấu hình `onErrorResume` có điều kiện theo loại lỗi.

## 8. Với Flux: fallback chỉ xảy ra khi toàn bộ nguồn không có phần tử

`Flux` có thể phát nhiều phần tử trước khi hoàn tất. Hai operator này không kiểm tra từng phần tử, mà kiểm tra **toàn bộ nguồn có từng phát phần tử hay chưa**:

~~~java
Flux<String> main = Flux.just("A", "B");

Flux<String> withDefault = main.defaultIfEmpty("X");
Flux<String> withBackup = main.switchIfEmpty(Flux.just("X", "Y"));

// Cả hai đều chỉ phát A, B.
~~~

Với nguồn rỗng sau khi lọc:

~~~java
Flux<Integer> even = Flux.just(1, 3, 5)
    .filter(n -> n % 2 == 0)
    .switchIfEmpty(Flux.just(2, 4));

// even phát 2, 4, vì filter đã loại toàn bộ phần tử.
~~~

Nếu chỉ một phần tử vượt qua filter, fallback không được subscribe:

~~~java
Flux<Integer> even = Flux.just(1, 2, 3)
    .filter(n -> n % 2 == 0)
    .switchIfEmpty(Flux.just(4, 6));

// Chỉ phát 2; không phát 4 hoặc 6.
~~~

**Không dùng `switchIfEmpty` để tự động bù “các ID bị thiếu” trong một danh sách.** Nếu một Flux chứa kết quả cho ID 1 và ID 3 nhưng thiếu ID 2, nó vẫn là Flux **không rỗng**. Để xử lý từng ID, tạo publisher riêng cho từng khóa:

~~~java
Flux<User> users = Flux.fromIterable(userIds)
    .concatMap(id -> repository.findById(id)
        .switchIfEmpty(Mono.defer(() -> backupRepository.findById(id))));
~~~

Đoạn trên là ví dụ tích hợp: `userIds`, `User` và repository phải được khai báo. Nó thực hiện fallback **riêng cho từng ID** vì mỗi `findById(id)` trả một `Mono` riêng. `concatMap` giữ thứ tự kết quả theo thứ tự input đối với các kết quả thực sự được phát, đồng thời subscribe từng inner theo thứ tự. Nếu muốn cho phép nhiều tìm kiếm bất đồng bộ đang chạy đồng thời, cân nhắc `flatMap` với concurrency phù hợp và chấp nhận thứ tự đầu ra có thể khác.

## 9. Áp dụng trong Spring WebFlux: tìm thấy, không tìm thấy và fallback

Giả sử có endpoint tìm profile theo ID bằng reactive repository. Khi repository trả `Mono.empty()` vì không có dữ liệu, API thường cần HTTP **404 Not Found**. Có thể dùng `switchIfEmpty(Mono.error(...))`:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class ProfileController {
    private final ProfileRepository repository;

    public ProfileController(ProfileRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/profiles/{id}")
    public Mono<ProfileDto> getProfile(@PathVariable String id) {
        return repository.findById(id)
            .map(profile -> new ProfileDto(
                profile.id(), profile.displayName()
            ))
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not found"
                )
            ));
    }
}
~~~

Đây là **đoạn tích hợp Spring WebFlux**, không phải file Java tự chạy: ứng dụng cần dependency `spring-boot-starter-webflux`, `ProfileRepository` trả `Mono<Profile>` và kiểu `ProfileDto` tương ứng. Nếu chưa có DTO, có thể dùng:

~~~java
public record ProfileDto(String id, String displayName) {}
~~~

Hành vi API:

- Repository phát một profile: `map` chuyển thành `ProfileDto`, WebFlux mã hóa response.
- Repository hoàn tất rỗng: `switchIfEmpty` chọn `Mono.error` để WebFlux xử lý thành 404 theo `ResponseStatusException`.
- Repository báo lỗi I/O: lỗi gốc được lan truyền; **không** tự đổi thành 404.

Nếu muốn thử dữ liệu dự phòng trước khi trả 404:

~~~java
public Mono<ProfileDto> getProfile(String id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.defer(() -> cache.findById(id)))
        .map(profile -> new ProfileDto(
            profile.id(), profile.displayName()
        ))
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Profile not found"
            )
        ));
}
~~~

Đây là method minh họa thuộc service/controller có `repository`, `cache` và `ProfileDto` đã khai báo. Nguồn cache chỉ được subscribe khi repository hoàn tất rỗng. Cả hai đều rỗng mới phát 404. Thứ tự đánh giá và fallback được thể hiện trực tiếp trong pipeline.

### Cẩn thận với WebClient và HTTP 404

Một lời gọi WebClient dùng `retrieve().bodyToMono(...)` mặc định biến HTTP **4xx/5xx** thành **tín hiệu lỗi**, không tự biến mọi 404 thành `Mono.empty()`:

~~~java
Mono<ProfileDto> remote = webClient.get()
    .uri("/profiles/{id}", id)
    .retrieve()
    .bodyToMono(ProfileDto.class);
~~~

Vì vậy:

~~~java
Mono<ProfileDto> incorrectAssumption = remote
    .switchIfEmpty(cache.findById(id));
~~~

Trong đoạn trên (đã có `webClient`, `cache`), fallback chỉ kích hoạt khi HTTP response có diễn giải thành Mono rỗng, **không phải khi WebClient báo lỗi 404 mặc định**. Nếu hợp đồng của ứng dụng muốn 404 được coi là “không có dữ liệu”, cần chuyển chính xác loại lỗi đó thành rỗng rồi mới fallback:

~~~java
import org.springframework.web.reactive.function.client.WebClientResponseException;

Mono<ProfileDto> resolved = webClient.get()
    .uri("/profiles/{id}", id)
    .retrieve()
    .bodyToMono(ProfileDto.class)
    .onErrorResume(
        WebClientResponseException.NotFound.class,
        error -> Mono.empty()
    )
    .switchIfEmpty(Mono.defer(() -> cache.findById(id)));
~~~

Đây là **đoạn tích hợp**, cần WebClient và cache đã được cấu hình. Lỗi 404 được chuyển thành rỗng theo chủ đích; lỗi 500, lỗi kết nối hoặc timeout vẫn lan truyền trừ khi có chính sách riêng. Cẩn thận với ý nghĩa nghiệp vụ khi một response HTTP thành công nhưng không có body: nó cũng có thể sinh Mono rỗng và dẫn tới fallback, tùy API.

## 10. Bẫy đặc biệt: `Mono<Void>` và `then()`

`Mono<Void>` thường dùng để biểu diễn **hoàn tất thành công mà không mang dữ liệu** (ví dụ thao tác xóa, ghi, giải phóng tài nguyên). Vì nó không phát `onNext` khi thành công, `switchIfEmpty` xem completion đó là **rỗng**:

~~~java
Mono<Void> save = Mono.fromRunnable(
    () -> System.out.println("Saved")
);

Mono<Void> chain = save.switchIfEmpty(
    Mono.fromRunnable(
        () -> System.out.println("Fallback also runs")
    )
);
~~~

Khi subscribe `chain`, cả hai thao tác có thể chạy: `save` hoàn tất rỗng nên Reactor chuyển sang fallback. Đây là hành vi đúng theo tín hiệu, nhưng **thường sai với ý định “chạy fallback nếu save thất bại”**.

Đối với một hành động tiếp theo sau khi save thành công, hãy dùng:

~~~java
Mono<Void> correct = save.then(
    Mono.fromRunnable(
        () -> System.out.println("Audit after save")
    )
);
~~~

`then` chờ hoàn tất thành công rồi subscribe tác vụ tiếp theo; khi `save` lỗi, lỗi được truyền và tác vụ sau không được chạy theo đường này.

**`then()` cũng cố ý loại bỏ toàn bộ giá trị của nguồn và trả `Mono<Void>`:**

~~~java
Mono<Void> completionOnly = Mono.just("value").then();

Mono<Void> surprising = completionOnly.switchIfEmpty(
    Mono.fromRunnable(
        () -> System.out.println("always after successful empty completion")
    )
);
~~~

Nguồn `completionOnly` hoàn tất rỗng; do đó sau completion thành công, `switchIfEmpty` luôn chọn publisher dự phòng. Không đặt `switchIfEmpty` sau `then()` nếu bạn muốn kiểm tra nguồn **trước khi bỏ giá trị** có rỗng hay không.

`defaultIfEmpty` với `Mono<Void>` cũng không mang ý nghĩa thông thường: không có instance `Void` hợp lệ để truyền làm một giá trị fallback khác `null`. Muốn biến completion thành một giá trị nghiệp vụ, dùng `thenReturn(result)`; muốn chạy tác vụ kế tiếp, dùng `then(nextPublisher)`.

## 11. Khi nào giá trị mặc định nguy hiểm về mặt nghiệp vụ?

Giá trị mặc định giúp UI/API thuận tiện, nhưng cần tránh che giấu tình huống thiếu dữ liệu:

| Tình huống | Hướng xử lý thường hợp lý |
| --- | --- |
| Thiếu tên hiển thị, tên chỉ dùng cho UI | `defaultIfEmpty("Khách")` nếu sản phẩm chấp nhận. |
| Cache miss, còn nguồn dữ liệu đáng tin khác | `switchIfEmpty(Mono.defer(...))` để truy vấn nguồn tiếp theo. |
| Không tìm thấy bản ghi bắt buộc trong REST API | `switchIfEmpty(Mono.error(new ResponseStatusException(...)))`. |
| Không có mục trong danh sách tùy chọn | `Flux.empty()` có thể là kết quả hợp lệ; chỉ fallback nếu có yêu cầu nghiệp vụ. |
| Không tìm thấy đơn hàng thanh toán | Không nên trả một “đơn hàng giả” bằng `defaultIfEmpty`. |
| Database mất kết nối hoặc lỗi authorization | Không tự đổi thành “rỗng”, để lỗi được báo hoặc phục hồi có kiểm soát. |

Nếu dùng số `-1`, chuỗi rỗng hoặc DTO giả làm giá trị sentinel, caller phải có hợp đồng rõ ràng để không hiểu nó là dữ liệu hợp lệ. Khi cần phân biệt trạng thái tìm thấy/không tìm thấy/lỗi, có thể cân nhắc `Mono<Optional<T>>` hoặc một kiểu kết quả miền nghiệp vụ, đồng thời nhớ rằng bản thân `Mono.empty()` đã có ý nghĩa 0 phần tử.

### Lưu ý khi ghép với `zip`

`Mono.zip(a, b)` cần mỗi Mono phát **một giá trị** để tạo tuple. Nếu một nguồn rỗng, zip không có đủ giá trị và có thể hoàn tất rỗng (và việc subscribe/cancel các nguồn còn lại tùy quá trình thực thi).

Nếu có default hợp lệ:

~~~java
Mono<String> name = findName().defaultIfEmpty("Khách");
Mono<Integer> age = findAge().defaultIfEmpty(0);

Mono<String> label = Mono.zip(name, age)
    .map(tuple -> tuple.getT1() + " (" + tuple.getT2() + ")");
~~~

Đây là đoạn tích hợp, `findName()` và `findAge()` được định nghĩa trong ứng dụng. Chỉ dùng `0` làm tuổi mặc định nếu nó có ý nghĩa nghiệp vụ; nếu không, dùng kiểu tùy chọn hoặc kết quả có trạng thái rõ ràng.

## 12. Kiểm thử với StepVerifier

Bổ sung tệp `src/test/java/EmptyFallbackTest.java` vào dự án ở mục 6. Dependency `reactor-test` và JUnit đã có trong `build.gradle`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class EmptyFallbackTest {

    @Test
    void defaultValueEmitsOnlyAfterDemand() {
        Mono<String> result = Mono.<String>empty()
            .defaultIfEmpty("guest");

        StepVerifier.create(result, 0)
            .thenRequest(1)
            .expectNext("guest")
            .verifyComplete();
    }

    @Test
    void switchDoesNotSubscribeFallbackForNonEmptySource() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> fallback = Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.just("backup");
        });

        StepVerifier.create(
                Mono.just("live").switchIfEmpty(fallback))
            .expectNext("live")
            .verifyComplete();

        assertEquals(0, calls.get());

        StepVerifier.create(
                Mono.<String>empty().switchIfEmpty(fallback))
            .expectNext("backup")
            .verifyComplete();

        assertEquals(1, calls.get());
    }

    @Test
    void switchDoesNotSwallowErrors() {
        Mono<String> source = Mono.error(
            new IllegalStateException("db error")
        );

        StepVerifier.create(
                source.switchIfEmpty(Mono.just("backup")))
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "db error".equals(error.getMessage()))
            .verify();
    }

    @Test
    void fluxFallbackMayEmitMultipleValues() {
        Flux<String> result = Flux.<String>empty()
            .switchIfEmpty(Flux.just("cache-1", "cache-2"));

        StepVerifier.create(result)
            .expectNext("cache-1", "cache-2")
            .verifyComplete();
    }
}
~~~

Chạy `gradle test` (hoặc `./gradlew test`/`gradlew.bat test` nếu dùng Gradle Wrapper). Cả bốn test được kỳ vọng **PASS**.

Test đầu dùng initial demand bằng 0 để xác nhận phần tử mặc định vẫn tuân theo yêu cầu Reactive Streams: chỉ phát khi subscriber cấp đủ demand. Test thứ hai kiểm tra **đúng thời điểm fallback được subscribe**, tránh nhầm việc xây dựng publisher với việc thực thi. Test thứ ba bảo đảm lỗi không bị đối xử như empty. Test thứ tư chứng minh `switchIfEmpty` trên Flux có thể phát nhiều phần tử dự phòng.

Nếu nguồn hoặc fallback dùng scheduler thật, network hay thời gian, thêm test cho timeout, cancellation và số lần gọi dependency bằng mock/stub phù hợp; không nên dùng `Thread.sleep` để “đợi chắc đã chạy”.

## 13. Các lỗi thường gặp

| Sai lầm | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| Coi `Mono.empty()` là `Mono.just(null)` | Nhầm mô hình tín hiệu; Reactor không cho phát `null`. | Dùng `Mono.empty()` / `Mono.justOrEmpty`. |
| Dùng `defaultIfEmpty` để gọi API dự phòng | Không nhận publisher làm giá trị fallback; dễ tạo kiểu lồng nhau hoặc thực thi sớm. | Dùng `switchIfEmpty(publisher)`. |
| Đặt `Mono.just(expensiveMethod())` trong `switchIfEmpty` | `expensiveMethod()` được đánh giá ngay khi xây dựng pipeline. | Dùng `Mono.defer` hoặc nguồn lazy thích hợp. |
| Mong `switchIfEmpty` hoạt động khi upstream `onError` | Lỗi vẫn đi theo `onError`. | Dùng `onErrorResume` nếu nghiệp vụ cho phép. |
| Hiểu `switchIfEmpty` là fallback cho từng phần tử bị thiếu trong Flux | Chỉ fallback khi **cả Flux** không phát phần tử. | Đặt fallback trong publisher cho từng ID nếu cần. |
| Đặt `switchIfEmpty` sau `then()` để kiểm tra nguồn trước đó | `then()` đã loại dữ liệu, nên luồng success trở thành rỗng. | Đặt fallback trước `then()` hoặc dùng `then` cho tác vụ tiếp theo. |
| Đặt `switchIfEmpty` sau `Mono<Void>` và xem đó là xử lý lỗi | Completion thành công của `Mono<Void>` vẫn rỗng. | Dùng `then` cho chuỗi thành công, `onErrorResume` cho lỗi. |
| Dùng giá trị mặc định không hợp lệ về nghiệp vụ | Che giấu dữ liệu thiếu hoặc tạo bản ghi giả. | Dùng error/Optional/Result khi cần giữ trạng thái thiếu dữ liệu. |
| Dùng `switchIfEmpty` cho WebClient 404 mặc định | `retrieve()` chuyển 404 thành lỗi, fallback không chạy. | Xử lý cụ thể loại lỗi HTTP rồi mới chuyển sang empty nếu cần. |
| Tự `subscribe()` hoặc `block()` trong WebFlux handler | Sai lifecycle và có thể chặn event-loop. | Trả `Mono`/`Flux` cho framework subscribe. |

## 14. Cách chọn trong công việc thực tế

Trước khi thêm fallback vào pipeline, hãy tự kiểm tra:

1. **Điều kiện kích hoạt là gì?** Nếu là completion không có `onNext`, dùng nhóm operator `...IfEmpty`. Nếu là lỗi, dùng nhóm `onError...`. Nếu là timeout, quyết định có chuyển timeout thành fallback hay báo lỗi.
2. **Fallback cần trả kiểu gì?** Một giá trị có sẵn dùng `defaultIfEmpty`; một publisher thực hiện truy vấn hay trả nhiều phần tử dùng `switchIfEmpty`.
3. **Có side effect lúc tạo fallback không?** Nếu có, hoãn bằng `defer` hoặc một publisher lazy được cấu hình đúng; tránh làm I/O blocking trên event-loop.
4. **Operator đang đứng ở đâu?** Sau `filter`, `flatMap`, `then()` hoặc một bước biến đổi có thể phát rỗng, ý nghĩa “empty” đã khác so với nguồn ban đầu.
5. **Có cần phân biệt missing với failure không?** Không biến mọi lỗi thành rỗng nếu không có chính sách rõ ràng; lựa chọn 404, cache miss và lỗi hệ thống theo hợp đồng API.
6. **Đã kiểm thử đủ các nhánh chưa?** Kiểm tra nguồn có dữ liệu, rỗng, lỗi, fallback có nhiều phần tử, và nguồn không hoàn tất khi cần.

**Ghi nhớ:** `defaultIfEmpty` thay một publisher đã hoàn tất rỗng bằng **một giá trị**; `switchIfEmpty` chuyển sang **một publisher khác** khi nguồn đầu tiên hoàn tất rỗng. Trong cả hai, “rỗng” được xác định bởi **không có `onNext` trước `onComplete`**, không phải bởi giá trị `null`, lỗi hay timeout.

## Tài liệu tham khảo

- Reactor Core Reference Guide: https://projectreactor.io/docs/core/release/reference/
- Reactor Mono API — `defaultIfEmpty`, `switchIfEmpty`, `defer`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Flux API — `defaultIfEmpty` và `switchIfEmpty`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Reactive Streams specification: https://www.reactive-streams.org/
