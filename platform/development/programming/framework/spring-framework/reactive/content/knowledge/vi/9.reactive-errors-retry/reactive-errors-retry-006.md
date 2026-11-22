# Vị trí xử lý lỗi trong từng phần tử so với toàn chuỗi

Trong **Spring Framework Reactive** và **Project Reactor**, vị trí đặt `onErrorResume`, `onErrorReturn`, `retry` hoặc `retryWhen` quyết định **phạm vi công việc chịu ảnh hưởng khi xảy ra lỗi**. Cùng một exception, xử lý bên trong publisher của từng phần tử có thể giữ cho các phần tử khác tiếp tục; xử lý ở cuối toàn bộ `Flux` thường **thay thế phần còn lại của chuỗi bằng một nhánh fallback**, vì lỗi đã là tín hiệu kết thúc của subscription upstream.

Đây là một quyết định nghiệp vụ, không chỉ là lựa chọn cú pháp:

- **Xử lý từng phần tử:** “ID số 2 lỗi, hãy ghi nhận thất bại riêng cho ID số 2; các ID khác vẫn được xử lý.”
- **Xử lý toàn chuỗi:** “Một bước bắt buộc lỗi thì dừng đợt xử lý này và trả lỗi hoặc kết quả dự phòng chung.”

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `onError` là tín hiệu terminal của Reactive Streams và vì sao `onErrorResume` không “quay lại” nguồn upstream đã lỗi.
2. Xác định phạm vi xử lý lỗi theo **vị trí operator** trong chuỗi Reactor.
3. Viết fallback cho từng ID bên trong `flatMap` hoặc `concatMap` và phân biệt ba chính sách: thay bằng kết quả, bỏ phần tử, hoặc lan truyền lỗi.
4. Hiểu giới hạn của fallback theo phần tử khi lỗi phát sinh **từ nguồn outer**, hoặc từ mã ném exception trước khi publisher được tạo.
5. Đặt `retryWhen` đúng cấp độ để tránh chạy lại hàng loạt công việc đã thành công.
6. Phân biệt `doOnError`, `onErrorMap`, `onErrorReturn`, `onErrorComplete`, `onErrorContinue` và `onErrorResume`.
7. Thiết kế phản hồi WebFlux cho batch processing, kể cả khi chỉ một phần kết quả thành công, đồng thời kiểm thử đúng các nhánh bằng `StepVerifier`.

## 2. Nền tảng: lỗi kết thúc một subscription

Reactive Streams dùng các tín hiệu chính:

~~~text
onSubscribe(subscription)
    |
    +-- onNext(item1) -- onNext(item2) -- ... -- onComplete()
    |
    +-- onNext(item1) -- onError(exception)
~~~

`onNext` có thể xảy ra nhiều lần trong `Flux`; chỉ có **một tín hiệu kết thúc**: `onComplete` hoặc `onError`. Sau một `onError` hợp lệ, nguồn không được tiếp tục phát `onNext` trong **cùng subscription**.

Ví dụ:

~~~java
Flux<Integer> source = Flux.just(1, 2)
    .concatWith(Flux.error(
        new IllegalStateException("broken")
    ))
    .concatWith(Flux.just(3, 4));
~~~

Khi subscribe, nguồn phát `1` và `2`, sau đó báo lỗi. Các phần tử `3` và `4` **không được phát tiếp trong subscription đó**. `concatWith` sau lỗi không thể giúp “nối tiếp” như thể lỗi là một phần tử bình thường.

Reactor có thể khôi phục bằng publisher dự phòng:

~~~java
Flux<Integer> recovered = source
    .onErrorResume(error -> Flux.just(99, 100));
~~~

Kết quả nhận được: `1, 2, 99, 100` rồi hoàn tất. Các phần tử `99`, `100` đến từ **fallback publisher**; Reactor không quay trở lại đọc `3, 4` từ đoạn nguồn đã lỗi.

**Phân biệt quan trọng:** “pipeline sau khi recover vẫn có phần tử” không có nghĩa “publisher gốc tiếp tục phát sau lỗi”. `onErrorResume` **chuyển sang một luồng thay thế** ở vị trí đặt nó.

## 3. Hai phạm vi xử lý khác nhau

Giả sử có ba ID cần truy vấn. Với ID số 2, hàm truy vấn trả `Mono.error(...)`:

~~~text
IDs:       1      2      3
           |      |      |
          OK     ERROR   OK
~~~

### A. Xử lý lỗi bên trong từng inner publisher

~~~java
Flux<String> local = Flux.just(1, 2, 3)
    .concatMap(id ->
        findValue(id)
            .onErrorResume(error ->
                Mono.just("fallback-" + id)
            )
    );
~~~

`findValue(id)` là phương thức minh họa trả `Mono<String>`. Khi ID 2 lỗi, `onErrorResume` nằm **trên Mono tương ứng với ID 2**, nên lỗi được đổi thành `"fallback-2"` trước khi đi ra `concatMap`. Outer Flux không nhận `onError` từ inner đó; nó có thể tiếp tục với ID 3.

~~~text
Outer ID 1 -> Mono thành công: "ok-1" ------+
Outer ID 2 -> Mono lỗi -> fallback: "fb-2" -+--> Flux tiếp tục
Outer ID 3 -> Mono thành công: "ok-3" ------+
~~~

### B. Xử lý lỗi ở cuối toàn chuỗi

~~~java
Flux<String> global = Flux.just(1, 2, 3)
    .concatMap(id -> findValue(id))
    .onErrorResume(error ->
        Flux.just("global-fallback")
    );
~~~

Ở đây lỗi từ inner ID 2 đi qua `concatMap` và kết thúc subscription vào chuỗi trước `onErrorResume`. Operator ngoài cùng chuyển sang fallback chung. Với ví dụ đồng bộ và `concatMap` tuần tự, ID 3 không được xử lý; output là `"ok-1", "global-fallback"`.

**Mấu chốt:** vị trí `onErrorResume` **trong mapper** xử lý lỗi của một inner, còn vị trí **sau operator merge/concat** xử lý lỗi đã lan ra cả Flux. Không nên dùng một fallback chung ở cuối rồi kỳ vọng mọi phần tử phía sau vẫn được xử lý.

## 4. Bảng so sánh nhanh

| Tiêu chí | Bắt lỗi từng phần tử | Bắt lỗi toàn chuỗi |
| --- | --- | --- |
| Vị trí điển hình | `flatMap(id -> call(id).onErrorResume(...))` | `flatMap(this::call).onErrorResume(...)` |
| Phạm vi lỗi được chặn | Publisher inner ứng với một ID | Bất kỳ lỗi nào từ toàn bộ upstream tại vị trí đó |
| Các ID khác | Có cơ hội tiếp tục khi lỗi inner đã được đổi thành dữ liệu/completion | Nguồn upstream đã bị kết thúc/hủy khi lỗi lan ra |
| Kết quả lỗi | Giá trị dự phòng riêng, phần tử kết quả lỗi, hoặc không phát phần tử | Dòng fallback chung hoặc terminal error cho cả đợt |
| Độ chính xác theo ID | Thường giữ được context `id` trong lambda | Phải tự mang context trong exception nếu muốn biết ID |
| Tác động của concurrency | Inner khác có thể đang chạy và có thể hoàn tất | Các inner khác có thể bị hủy; kết quả đã tới downstream không bị thu hồi |
| Phù hợp | Batch có phần tử độc lập, best-effort | Tác vụ all-or-nothing theo quy ước API, lỗi khiến toàn pipeline không còn hợp lệ |

`concatMap` xử lý inner tuần tự, nên minh họa dễ dự đoán. `flatMap` có thể subscribe nhiều inner đồng thời, và thứ tự phần tử đến downstream **không được bảo đảm**. Khi một inner không được recover và gây lỗi toàn Flux, một số inner khác có thể đã phát kết quả hoặc đang thực hiện side effect trước khi nhận hủy. Không mô tả `flatMap` là “đảm bảo ID đứng sau chưa từng bắt đầu”.

## 5. Ví dụ Java 17 chạy độc lập, có stdout xác định

Dự án sử dụng Reactor Core, Gradle và Java 17+. Ta dùng `concatMap` để minh họa phạm vi lỗi một cách xác định, tránh phụ thuộc lịch của nhiều request bất đồng bộ.

Tạo file `build.gradle`:

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
    mainClass = 'ErrorScopeDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tạo file `src/main/java/ErrorScopeDemo.java`:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ErrorScopeDemo {

    static Mono<String> load(int id) {
        if (id == 2) {
            return Mono.error(
                new IllegalStateException("failed-" + id)
            );
        }
        return Mono.just("ok-" + id);
    }

    public static void main(String[] args) {
        List<String> perItem = Flux.range(1, 3)
            .concatMap(id ->
                load(id).onErrorResume(error ->
                    Mono.just("fallback-" + id)
                )
            )
            .collectList()
            .block();

        List<String> wholeStream = Flux.range(1, 3)
            .concatMap(ErrorScopeDemo::load)
            .onErrorResume(error ->
                Flux.just("global-fallback")
            )
            .collectList()
            .block();

        List<String> skipped = Flux.range(1, 3)
            .concatMap(id ->
                load(id).onErrorResume(error ->
                    Mono.empty()
                )
            )
            .collectList()
            .block();

        System.out.println("perItem = " + perItem);
        System.out.println("wholeStream = " + wholeStream);
        System.out.println("skipped = " + skipped);
    }
}
~~~

Chạy `gradle run` từ thư mục dự án. Nếu có Gradle Wrapper, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows. Các dòng chương trình in ra (không tính log của Gradle):

~~~text
perItem = [ok-1, fallback-2, ok-3]
wholeStream = [ok-1, global-fallback]
skipped = [ok-1, ok-3]
~~~

**Giải thích chi tiết:**

1. `load(2)` trả `Mono.error`; các ID khác trả `Mono.just("ok-...")`.
2. `perItem` biến lỗi ở ID 2 thành một `Mono.just("fallback-2")` ngay bên trong mapper, vì vậy outer tiếp tục ID 3.
3. `wholeStream` để lỗi ID 2 lan tới `onErrorResume` của toàn Flux. Dòng upstream dừng ở ID 2; fallback chung phát một phần tử, và không có `ok-3`.
4. `skipped` đổi lỗi ID 2 thành `Mono.empty()`, nghĩa là **cố ý không trả phần tử cho ID đó**. Outer vẫn tiếp tục ID 3.
5. `concatMap` đợi inner hiện tại hoàn tất trước khi subscribe inner kế tiếp, bảo đảm thứ tự trong ví dụ. Nếu thay bằng `flatMap` có concurrency lớn, không dùng stdout này làm cam kết thứ tự.
6. `block()` ở đây chỉ có trong ứng dụng console để lấy kết quả in; trong Spring WebFlux controller/service, trả publisher cho framework, tránh gọi `block()` trên event loop.

**Lưu ý:** `Mono.error` chỉ tạo publisher phát lỗi khi được subscribe; chương trình không ném lỗi ra ngoài lúc tạo `load(2)`. Trong project Spring Boot thực tế, để Spring Boot BOM quản lý phiên bản Reactor thay vì buộc phiên bản độc lập trong ví dụ này.

## 6. Ba chính sách xử lý lỗi của từng phần tử

Không phải tình huống nào cũng nên “nuốt” lỗi. Khi đã quyết định xử lý cấp inner, chọn chính sách theo yêu cầu dữ liệu.

### 6.1. Dự phòng bằng một giá trị hợp lệ

~~~java
Flux<String> result = ids.flatMap(id ->
    remoteLookup(id)
        .onErrorResume(error ->
            Mono.just("unavailable-" + id)
        ),
    8
);
~~~

Đây là đoạn tích hợp: `ids` là `Flux<Integer>` và `remoteLookup` trả `Mono<String>`. Mỗi lỗi được đổi thành một chuỗi có gắn ID. Lưu ý cách này **chuyển lỗi thành thành công trên pipeline**, vì vậy caller không còn nhận `onError` của inner đó; cần có trạng thái/mã lỗi rõ nếu dữ liệu trả về phục vụ quyết định quan trọng.

### 6.2. Bỏ qua riêng phần tử lỗi

~~~java
Flux<String> result = ids.flatMap(id ->
    remoteLookup(id)
        .doOnError(error -> recordFailure(id, error))
        .onErrorResume(error -> Mono.empty()),
    8
);
~~~

`Mono.empty()` làm inner lỗi kết thúc thành công nhưng không có giá trị; outer tiếp tục. `recordFailure` là hàm đo lường/ghi log do ứng dụng định nghĩa; tránh thực hiện I/O blocking trực tiếp trong callback.

Chỉ dùng nếu nghiệp vụ **cho phép mất kết quả cho ID đó**. Nếu phải xử lý đủ 100/100 bản ghi, việc bỏ qua có thể tạo báo cáo thiếu mà không ai phát hiện. Một cách an toàn hơn là tạo **kết quả có trạng thái**.

### 6.3. Giữ mỗi lỗi như một kết quả có kiểu

Thay vì phát chuỗi sentinel hay bỏ phần tử, dùng một DTO/record mô tả thành công hoặc lỗi:

~~~java
record ItemResult(
    int id,
    String status,
    String value,
    String reason
) {}

Flux<ItemResult> result = ids.flatMap(id ->
    remoteLookup(id)
        .map(value -> new ItemResult(id, "OK", value, ""))
        .onErrorResume(error ->
            Mono.just(new ItemResult(
                id, "FAILED", "", error.getClass().getSimpleName()
            ))
        ),
    8
);
~~~

Đây là đoạn tích hợp; `ids`, `remoteLookup` và kiểu kết quả phải được khai báo cùng ngữ cảnh. Một bản ghi `ItemResult` được phát cho mỗi ID **chỉ khi upstream có đúng một giá trị hoặc lỗi được chuyển thành một kết quả**. Nếu `remoteLookup(id)` có thể hoàn tất rỗng (`Mono.empty()`), đoạn trên sẽ không phát kết quả cho ID ấy; khi yêu cầu đủ một kết quả cho mỗi ID, thêm nhánh `switchIfEmpty`:

~~~java
Mono<ItemResult> one = remoteLookup(id)
    .map(value -> new ItemResult(id, "OK", value, ""))
    .switchIfEmpty(Mono.just(
        new ItemResult(id, "NOT_FOUND", "", "")
    ))
    .onErrorResume(error ->
        Mono.just(new ItemResult(
            id, "FAILED", "", error.getClass().getSimpleName()
        ))
    );
~~~

Tách rõ **không tìm thấy** (empty) và **truy vấn thất bại** (error) giúp API giữ đầy đủ kết quả và tránh che giấu lỗi hệ thống.

## 7. Bắt lỗi trước, trong và sau flatMap: phạm vi không giống nhau

Thứ tự operator xác định những lỗi đi tới handler:

~~~java
Flux<String> chain = source
    .onErrorResume(error -> Flux.just(0))
    .flatMap(id -> remoteLookup(id));
~~~

`onErrorResume` ở trước `flatMap` chỉ xử lý lỗi được truyền từ **`source` và những operator upstream của nó**. Nếu `remoteLookup(id)` báo lỗi trong mapper phía sau, handler ở trước không quay ngược xuống để bắt lỗi đó.

Xử lý bên trong:

~~~java
Flux<String> chain = source
    .flatMap(id ->
        remoteLookup(id)
            .onErrorResume(error ->
                Mono.just("fallback-" + id)
            )
    );
~~~

Handler inner giữ context `id` và chặn những lỗi phát ra từ publisher `remoteLookup(id)`. **Lỗi từ outer source** vẫn có thể kết thúc toàn chuỗi vì nó không đi qua một inner publisher nào.

Xử lý cuối pipeline:

~~~java
Flux<String> chain = source
    .flatMap(id -> remoteLookup(id))
    .onErrorResume(error ->
        Flux.just("global-fallback")
    );
~~~

Handler cuối có thể thấy lỗi được truyền từ outer, mapper hoặc inner phía trên; sau khi fallback được chọn, **upstream đã kết thúc**. Nó không có cách tự khôi phục điểm duyệt còn dở từ nguồn ban đầu.

### Lỗi trong mapper trước khi tạo Mono

Đây là một khác biệt dễ bỏ sót:

~~~java
Flux<String> risky = ids.flatMap(id ->
    legacyFactory(id).onErrorResume(error ->
        Mono.just("fallback-" + id)
    )
);
~~~

Nếu chính **lời gọi `legacyFactory(id)` ném exception trước khi trả về một Mono**, phần `.onErrorResume(...)` ở phía sau trong lambda chưa kịp được tạo. `flatMap` sẽ nhận lỗi từ mapper và có thể kết thúc **toàn Flux**.

Khi cần bắt lỗi cả trong lúc tạo publisher, trì hoãn lời gọi bằng `Mono.defer`:

~~~java
Flux<String> guarded = ids.flatMap(id ->
    Mono.defer(() -> legacyFactory(id))
        .onErrorResume(error ->
            Mono.just("fallback-" + id)
        ),
    8
);
~~~

`Mono.defer` chuyển exception không fatal của supplier thành tín hiệu lỗi của **inner publisher**, để handler nội bộ có thể xử lý. Nếu `legacyFactory(id)` thực thi **I/O blocking**, `defer` chỉ trì hoãn việc gọi, **không tự chuyển sang thread khác**.

Nếu hàm đồng bộ trả giá trị hoặc ném exception, dùng `Mono.fromCallable`:

~~~java
Flux<String> guarded = ids.flatMap(id ->
    Mono.fromCallable(() -> blockingLookup(id))
        .subscribeOn(Schedulers.boundedElastic())
        .onErrorResume(error ->
            Mono.just("fallback-" + id)
        ),
    8
);
~~~

Đây là đoạn tích hợp, cần import `reactor.core.scheduler.Schedulers` và `blockingLookup` trả `String`. `boundedElastic` cô lập blocking khỏi event loop, còn `concurrency = 8` giúp giới hạn số inner hoạt động. Phải giới hạn cả connection pool, timeout và hàng đợi thực tế; dùng Reactor không biến API blocking thành non-blocking.

## 8. Vì sao lỗi trong flatMap đồng thời khó dự đoán hơn?

Với `Flux.flatMap`, nhiều inner có thể đang được subscribe đồng thời:

~~~java
Flux<ItemResult> result = ids.flatMap(
    id -> fetch(id).map(value -> toResult(id, value)),
    8
);
~~~

Đây là đoạn minh họa: `fetch`, `toResult` và `ItemResult` do ứng dụng định nghĩa. Nếu inner ID 2 lỗi:

- **Không có fallback nội bộ:** lỗi thường được chuyển tới toàn Flux và các subscription còn hoạt động có thể bị hủy. Một số inner đã phát phần tử hoặc đã gây side effect trước khi bị hủy. **Không bảo đảm** rằng những ID sau ID 2 chưa khởi chạy.
- **Có fallback nội bộ:** lỗi ID 2 được chuyển thành giá trị hoặc completion. Các inner khác có cơ hội tiếp tục. Tuy nhiên outer vẫn có thể lỗi riêng, hoặc fallback lại ném lỗi.
- **Thứ tự:** ngay cả khi mọi inner đã recover, `flatMap` không bảo đảm đầu ra theo thứ tự ID đầu vào. Dùng `flatMapSequential` nếu muốn các inner được khởi chạy chồng lấp nhưng kết quả phát theo thứ tự outer; dùng `concatMap` khi cần thực thi phụ thuộc tuần tự.

Nếu một lỗi là lý do dừng cả batch, đừng coi cancellation là **rollback**. HTTP request, email đã gửi, ghi database hoặc thao tác với broker có thể đã xảy ra trước lỗi. Cần transaction/idempotency/saga hoặc cơ chế bù trừ thích hợp nếu nghiệp vụ đòi hỏi atomicity.

### Backpressure và lỗi

`request(n)` điều tiết số phần tử mà downstream yêu cầu, nhưng **không quyết định phạm vi xử lý lỗi**. `flatMap` còn có prefetch/queue/concurrency riêng. Một hàng đợi có giới hạn có thể tràn; lỗi tràn là lỗi upstream thực sự và phải được xử lý theo hợp đồng. Đừng dùng fallback để che dấu OOM hoặc các lỗi hệ thống không thể phục hồi.

## 9. Các operator xử lý lỗi: chọn đúng chức năng

| Operator | Chức năng | Tín hiệu sau xử lý |
| --- | --- | --- |
| `doOnError(handler)` | Quan sát/log/metrics lỗi | **Vẫn giữ lỗi** cho downstream |
| `onErrorMap(mapper)` | Chuyển lỗi thành loại/exception khác | Vẫn kết thúc bằng `onError` mới |
| `onErrorReturn(value)` | Thay lỗi bằng một giá trị fallback | Phát một giá trị rồi hoàn tất |
| `onErrorResume(fn)` | Thay lỗi bằng một publisher fallback | Phát tín hiệu của publisher mới |
| `onErrorComplete()` | Chuyển lỗi thành completion rỗng | Dừng luồng tại vị trí đó, không phát fallback value |
| `retry(n)` | Subscribe lại nguồn đã lỗi với số lần retry cho phép | Có thể phát lại phần tử của nguồn từ lần trước |
| `retryWhen(Retry...)` | Subscribe lại theo chính sách retry, backoff/filter | Tác động tới toàn bộ upstream ở vị trí đặt |
| `onErrorContinue(...)` | Cho một số operator upstream được hỗ trợ bỏ qua phần tử gây lỗi | Cơ chế đặc biệt, khó dự đoán phạm vi; tránh dùng mặc định |

**`doOnError` không phải recovery.** Nếu code có `doOnError(error -> log(...))` nhưng không có xử lý khác, pipeline vẫn nhận `onError`.

**`onErrorComplete` ở cuối Flux** chuyển lỗi thành kết thúc thành công, nhưng cũng **kết thúc phần upstream còn lại**; nó không có nghĩa “bỏ ID lỗi và duyệt tiếp”.

**`onErrorContinue` có phạm vi khác thường:** nó tác động tới các operator **upstream hỗ trợ chế độ này**, có thể ảnh hưởng cả code thư viện ngoài dự kiến. Project Reactor chính thức khuyến nghị trong đa số trường hợp dùng `onErrorResume(... -> Mono.empty())` **bên trong từng inner publisher** để bỏ riêng phần tử lỗi. Không dựa vào `onErrorContinue` như một try/catch tổng quát cho toàn bộ chain.

Ví dụ so sánh:

~~~java
// Bỏ riêng lỗi của mỗi lời gọi:
Flux<String> local = ids.flatMap(id ->
    remoteLookup(id)
        .doOnError(error -> recordFailure(id, error))
        .onErrorResume(error -> Mono.empty())
);

// Kết thúc luồng hiện tại khi gặp lỗi:
Flux<String> global = ids
    .flatMap(id -> remoteLookup(id))
    .onErrorComplete();
~~~

Hai đoạn này khác nhau về dữ liệu, lỗi và khả năng tiếp tục xử lý. Trong pipeline quan trọng, hãy cân nhắc lọc lỗi theo loại thay vì nuốt tất cả exception:

~~~java
Mono<String> recovered = remoteLookup(id)
    .onErrorResume(
        java.util.concurrent.TimeoutException.class,
        error -> cachedValue(id)
    );
~~~

Đây là đoạn tích hợp, với `cachedValue(id)` trả `Mono<String>`. Nó chỉ thay lỗi đúng loại `TimeoutException` (hoặc subtype), các lỗi khác tiếp tục được phát. Loại lỗi timeout cụ thể có thể do Reactor hoặc client/driver phát ra; đọc hợp đồng của nguồn khi chọn predicate.

## 10. Vị trí retry: một phần tử hay toàn batch?

`retry` và `retryWhen` **subscribe lại upstream** tại vị trí chúng được gắn. Vì vậy việc đặt chúng **bên trong** hay **bên ngoài** mapper có hệ quả rất lớn.

### Retry từng ID, chỉ chạy lại lời gọi của ID đó

~~~java
Flux<String> result = ids.concatMap(id ->
    remoteLookup(id)
        .retryWhen(
            reactor.util.retry.Retry.backoff(
                2, java.time.Duration.ofMillis(100)
            )
        )
        .onErrorResume(error ->
            Mono.just("failed-" + id)
        )
);
~~~

Đây là đoạn tích hợp. Khi inner ID 2 lỗi, Reactor có thể subscribe lại **inner ID 2** tối đa hai lần retry sau lần đầu (tối đa ba lần subscribe cho ID 2). Nếu vẫn lỗi, fallback cho ID 2 phát giá trị rồi outer có thể tiếp tục ID 3.

### Retry toàn chuỗi, có thể lặp lại cả ID đã xong

~~~java
Flux<String> result = ids
    .concatMap(id -> remoteLookup(id))
    .retryWhen(
        reactor.util.retry.Retry.backoff(
            2, java.time.Duration.ofMillis(100)
        )
    );
~~~

Nếu lỗi ở ID 2 sau khi ID 1 đã phát `ok-1`, `retryWhen` ngoài `concatMap` **subscribe lại toàn upstream**. Với `ids` là Flux cold duyệt danh sách từ đầu, ID 1 có thể bị gọi lại và phần tử `ok-1` có thể được phát lần nữa. Nếu các lời gọi có side effect (tạo đơn hàng, chuyển tiền, gửi email), retry toàn batch có nguy cơ **thực hiện trùng**.

Một retry không tự động xóa các `onNext` đã gửi ở lần trước, và không bảo đảm tính nguyên tử của thao tác bên ngoài.

### Quyết định retry theo loại lỗi

Không phải lỗi nào cũng đáng thử lại. Lỗi mạng tạm thời, timeout, HTTP 429/503 có thể phù hợp tùy quy ước; 400/401/403 hoặc lỗi validation thường không nên retry tự động.

~~~java
Mono<String> retried = remoteLookup(id)
    .retryWhen(
        reactor.util.retry.Retry.backoff(
            2, java.time.Duration.ofMillis(200)
        ).filter(error -> isRetryable(error))
    )
    .onErrorResume(error ->
        fallbackOrError(id, error)
    );
~~~

Đây là đoạn tích hợp: `isRetryable` là predicate do ứng dụng định nghĩa, còn `fallbackOrError` trả `Mono<String>` theo hợp đồng nghiệp vụ. `Retry.backoff` có cơ chế trì hoãn và jitter theo Reactor; đừng hiểu rằng các lượt retry sẽ luôn cách nhau chính xác 200 ms.

**Thứ tự operator quan trọng:** `retryWhen(...).onErrorResume(...)` nghĩa là **thử lại trước, rồi fallback nếu vẫn thất bại**. Ngược lại `onErrorResume(...).retryWhen(...)` có thể đã thay exception bằng completion/giá trị, nên không còn lỗi để retry.

**Lưu ý:** lỗi cuối cùng từ `retryWhen` khi hết số lần retry có thể là một exception báo retry exhaustion, với lỗi ban đầu nằm ở `cause`. Nếu cần phân loại lỗi cho fallback sau retry, hãy xét cấu trúc lỗi sau khi hết retry hoặc cấu hình `onRetryExhaustedThrow` phù hợp, tránh mặc định mọi handler theo class gốc đều bắt được lỗi cuối.

## 11. Đừng quên nguồn rỗng và nguồn outer lỗi

`onErrorResume` chỉ kích hoạt với `onError`, không chạy khi một `Mono` hoàn tất rỗng:

~~~java
Mono<String> missing = Mono.<String>empty()
    .onErrorResume(error -> Mono.just("fallback"));
// Vẫn rỗng.
~~~

Khi cần phân biệt không tìm thấy và lỗi:

~~~java
Mono<String> one = remoteLookup(id)
    .switchIfEmpty(Mono.just("not-found-" + id))
    .onErrorResume(error -> Mono.just("failed-" + id));
~~~

Đây là đoạn tích hợp. `switchIfEmpty` xử lý completion không có `onNext`, còn `onErrorResume` xử lý lỗi. Với nguồn chỉ trả `Mono<Void>` (thành công không phát giá trị), `switchIfEmpty` sau đó **vẫn được kích hoạt ngay cả khi tác vụ thành công**; dùng `then(...)` để nối công việc sau completion nếu đó mới là mục đích.

### Nếu outer Flux lỗi

Ví dụ:

~~~java
Flux<Integer> ids = Flux.just(1, 2)
    .concatWith(Flux.error(
        new IllegalStateException("ID feed unavailable")
    ));

Flux<String> result = ids.concatMap(id ->
    remoteLookup(id)
        .onErrorResume(error -> Mono.just("failed-" + id))
);
~~~

Các handler bên trong chỉ bảo vệ việc xử lý những ID **đã được phát**. Khi `ids` phát `onError`, không có inner dành cho “ID tiếp theo” để xử lý sự cố đó. Lỗi outer vẫn kết thúc pipeline trừ khi được xử lý bằng operator ở cấp phù hợp với outer.

Khi xử lý lỗi outer cần tách khỏi lỗi inner, có thể đặt một handler rõ ràng trên nguồn IDs:

~~~java
Flux<Integer> safeIds = idSource
    .onErrorResume(error -> {
        reportSourceFailure(error);
        return Flux.empty();
    });
~~~

Đây là đoạn tích hợp. Việc hoàn tất rỗng trong fallback nghĩa là **không còn ID nào tiếp theo**, không phải “khôi phục lại kết nối nguồn ID và tiếp tục ở vị trí cũ”. Chỉ dùng khi quy ước nghiệp vụ cho phép kết thúc batch sớm; nếu source phải đầy đủ, cần để lỗi lan truyền và báo batch thất bại.

## 12. Áp dụng Spring WebFlux: phản hồi theo từng item trong batch

Một endpoint nhận danh sách ID có thể phục vụ hai hợp đồng hoàn toàn khác nhau:

- **Best effort:** trả kết quả riêng cho từng ID, gồm cả trạng thái lỗi/không tìm thấy; HTTP có thể trả 200 cho **request xử lý batch thành công ở mức giao thức**, trong khi từng item có status riêng.
- **All or nothing:** một lỗi cần khiến toàn request thất bại, ví dụ trả HTTP 5xx/4xx hoặc hủy cả giao dịch. Khi các side effect đã xảy ra, “all or nothing” không thể chỉ dựa trên `onErrorResume` hoặc cancel; phải dùng biện pháp giao dịch/bù trừ phù hợp.

Dưới đây là **đoạn tích hợp Spring Boot WebFlux**, giả định `WebClient` đã được cấu hình với base URL phù hợp. Những record đặt cuối ví dụ mô tả dữ liệu phản hồi; cần thêm module/dependency `spring-boot-starter-webflux` và một ứng dụng Spring Boot thực sự.

~~~java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class CatalogController {
    private final WebClient client;

    public CatalogController(WebClient client) {
        this.client = client;
    }

    @GetMapping("/catalog/batch")
    public Flux<LookupResult> batch(@RequestParam List<String> ids) {
        return Flux.fromIterable(ids)
            .flatMap(id -> client.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(ItemDto.class)
                .map(item ->
                    new LookupResult(id, "OK", item.name()))
                .switchIfEmpty(Mono.just(
                    new LookupResult(id, "NOT_FOUND", "")))
                .onErrorResume(
                    WebClientResponseException.NotFound.class,
                    error -> Mono.just(
                        new LookupResult(id, "NOT_FOUND", "")
                    )
                )
                .onErrorResume(
                    WebClientRequestException.class,
                    error -> Mono.just(
                        new LookupResult(id, "UNAVAILABLE", "")
                    )
                ), 8);
    }
}

record ItemDto(String name) {}
record LookupResult(String id, String status, String name) {}
~~~

**Hành vi và giới hạn của ví dụ:**

1. Mỗi ID tạo một lời gọi HTTP reactive, `flatMap(..., 8)` giới hạn số inner subscription đang hoạt động do operator quản lý.
2. HTTP 200 với body hợp lệ tạo kết quả `OK`. Nếu body được diễn giải thành `Mono.empty()`, `switchIfEmpty` tạo `NOT_FOUND` theo **quy ước minh họa**; ứng dụng thực tế phải quyết định xem 200 không có body có thật sự tương đương “không tìm thấy” hay không.
3. Với `retrieve()`, HTTP 404 mặc định tạo `WebClientResponseException.NotFound`; handler **bên trong từng inner** đổi thành `NOT_FOUND` cho ID tương ứng.
4. Lỗi mạng kiểu `WebClientRequestException` được đổi thành `UNAVAILABLE` cho ID đó. Các lỗi không khớp, như một số phản hồi HTTP 5xx, vẫn có thể lan ra và kết thúc toàn chuỗi. Điều này là chủ ý minh họa chính sách lọc theo loại lỗi.
5. `flatMap` có thể thay đổi thứ tự kết quả. Nếu cần cùng thứ tự input nhưng vẫn muốn cho phép nhiều request chồng lấp, cân nhắc `flatMapSequential`. Nếu các thao tác phụ thuộc nhau, chọn `concatMap`.
6. Nếu trả response dưới dạng streaming và một lỗi ngoài dự kiến xuất hiện **sau khi HTTP headers/body đã được commit**, server có thể không còn đổi trạng thái HTTP thành một 500 sạch. Khi hợp đồng đòi hỏi một response tổng hợp có mã trạng thái duy nhất, có thể cần thu thập kết quả hữu hạn trước khi gửi, chấp nhận chi phí bộ nhớ/độ trễ và thiết kế fail-fast rõ ràng.

**Không tự gọi `subscribe()` trong controller** để khởi động request, rồi trả một `Flux.empty()` hoặc `Mono.just("done")` ngay. Làm vậy tách việc xử lý thật khỏi vòng đời HTTP, làm khó truyền lỗi và cancellation. Trả publisher đã ghép để WebFlux quản lý subscription.

## 13. Quan sát lỗi theo đúng phạm vi

Đo lường và log cũng phải phản ánh chính sách:

~~~java
Flux<String> result = ids.flatMap(id ->
    remoteLookup(id)
        .doOnError(error ->
            logItemFailure(id, error)
        )
        .onErrorResume(error ->
            Mono.just("failed-" + id)
        ),
    8
).doOnError(error ->
    logBatchFailure(error)
);
~~~

Đây là đoạn tích hợp, với hai hàm log do ứng dụng định nghĩa.

- `doOnError` **bên trong** ghi nhận lỗi của từng lời gọi trước khi fallback che tín hiệu lỗi đó.
- `doOnError` **bên ngoài** chỉ thấy lỗi **thực sự thoát** khỏi các inner, lỗi outer, hoặc lỗi phát sinh ở những bước khác phía trên nó.
- Nếu mọi lỗi inner đã được recover, không nên mong counter lỗi toàn batch tự tăng tương ứng.
- Nếu chính callback log gây lỗi, pipeline có thể nhận lỗi mới; trong thực tế, logging/metrics cần nhẹ, an toàn và không blocking event loop.

Nên đo các chỉ số như: tổng số ID, số thành công, số không tìm thấy, số lỗi theo loại, số lần retry, timeout, queue/concurrency và số batch thất bại. Đừng chỉ đo HTTP 200 để kết luận mọi item đều thành công.

Một thiết kế rõ ràng có thể lưu `status` trên mỗi kết quả (ví dụ `OK`, `NOT_FOUND`, `RETRY_EXHAUSTED`) và xây báo cáo tổng hợp từ những kết quả đó. Tránh trả lỗi kỹ thuật thô hoặc dữ liệu nhạy cảm trong thông báo gửi client; ghi chi tiết vào log/tracing có kiểm soát.

## 14. Kiểm thử với StepVerifier: bảo vệ hợp đồng phạm vi lỗi

Tạo file `src/test/java/ErrorScopeTest.java` trong dự án Gradle ở mục 5. Dependency `reactor-test` và JUnit đã được khai báo.

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ErrorScopeTest {

    @Test
    void innerFallbackKeepsLaterIds() {
        Flux<String> result = Flux.range(1, 3)
            .concatMap(id ->
                ErrorScopeDemo.load(id)
                    .onErrorResume(error ->
                        Mono.just("fallback-" + id)
                    )
            );

        StepVerifier.create(result)
            .expectNext("ok-1", "fallback-2", "ok-3")
            .verifyComplete();
    }

    @Test
    void outerFallbackStopsOriginalSequence() {
        AtomicInteger visited = new AtomicInteger();

        Flux<String> result = Flux.range(1, 3)
            .concatMap(id -> {
                visited.incrementAndGet();
                return ErrorScopeDemo.load(id);
            })
            .onErrorResume(error -> Flux.just("global-fallback"));

        StepVerifier.create(result)
            .expectNext("ok-1", "global-fallback")
            .verifyComplete();

        assertEquals(2, visited.get());
    }

    @Test
    void innerHandlerDoesNotCatchOuterSourceError() {
        Flux<Integer> ids = Flux.just(1)
            .concatWith(Flux.error(
                new IllegalStateException("outer failed")
            ));

        Flux<String> result = ids.concatMap(id ->
            ErrorScopeDemo.load(id)
                .onErrorResume(error ->
                    Mono.just("fallback-" + id)
                )
        );

        StepVerifier.create(result)
            .expectNext("ok-1")
            .expectErrorMessage("outer failed")
            .verify();
    }

    @Test
    void retryResubscribesOneColdPublisher() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> flaky = Mono.defer(() ->
            attempts.incrementAndGet() == 1
                ? Mono.<String>error(
                    new IllegalStateException("temporary")
                )
                : Mono.just("ok")
        );

        StepVerifier.create(flaky.retry(1))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(2, attempts.get());
    }
}
~~~

Chạy `gradle test` hoặc Gradle Wrapper tương ứng. Cả bốn test được kỳ vọng **PASS**:

- Test 1: fallback của inner ID 2 không ngăn outer xử lý ID 3.
- Test 2: khi lỗi đã ra ngoài `concatMap`, fallback chung thay thế phần còn lại. Bộ đếm `visited` bằng 2 vì `concatMap` tuần tự và không đến ID 3.
- Test 3: lỗi từ **outer IDs source** không được handler đặt trong inner bảo vệ.
- Test 4: `retry(1)` subscribe lại cùng publisher cold **một lần** sau lỗi đầu, tổng cộng hai lần.

Bài test dùng `concatMap` để xác định thứ tự. Khi test `flatMap` với nhiều inner bất đồng bộ, tránh viết `expectNext` theo một thứ tự không được bảo đảm; có thể dùng `expectNextCount`/`recordWith`/`consumeRecordedWith` và kiểm tra tập đa phần tử hoặc dùng `flatMapSequential` nếu nghiệp vụ yêu cầu thứ tự.

**Không coi những test này là bằng chứng rằng retry side effect ngoài hệ thống sẽ an toàn.** Phải kiểm thử cả kết nối, hủy, timeout, deduplication và idempotency nếu ứng dụng ghi dữ liệu ra bên ngoài.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý phù hợp |
| --- | --- | --- |
| Đặt `onErrorResume` cuối `Flux` rồi mong tiếp tục sau ID lỗi | Lỗi đã kết thúc upstream; chỉ có fallback mới được phát | Đặt recovery trong từng publisher inner nếu các item độc lập |
| Dùng `onErrorComplete` cuối để “bỏ đúng một phần tử lỗi” | Kết thúc toàn bộ upstream tại lỗi đầu tiên | Đặt `onErrorResume(e -> Mono.empty())` trong mỗi inner |
| Cho rằng mọi lỗi được inner bắt, kể cả outer source lỗi | Lỗi outer không đi qua handler inner | Tách chính sách lỗi outer và inner |
| Gọi hàm có thể ném lỗi trước khi tạo publisher inner | `onErrorResume` trong lambda chưa được gắn | Dùng `Mono.defer`/`fromCallable` để chuyển lỗi thành tín hiệu inner |
| Dùng `retryWhen` sau toàn `flatMap` cho các thao tác có side effect | Có thể gọi lại ID đã thành công khi retry cả nguồn | Đặt retry trong từng inner; dùng idempotency và giới hạn retry |
| Đặt `onErrorResume` trước `retryWhen` rồi nghĩ retry đã chạy | Error có thể đã được thay bằng completion/giá trị | Retry trước, fallback sau |
| Coi `doOnError` là cơ chế bắt lỗi | Lỗi vẫn lan ra downstream | Dùng `onErrorResume` hoặc operator recovery thích hợp nếu muốn recover |
| Lạm dụng `onErrorContinue` | Phạm vi upstream/phụ thuộc hỗ trợ operator khó dự đoán | Viết xử lý lỗi trong từng inner rõ ràng |
| Dùng `flatMap` song song mà dự đoán ID sau chưa từng chạy khi lỗi | Inner khác có thể đã bắt đầu/side effect đã xảy ra | Chọn `concatMap` cho tuần tự bắt buộc; thiết kế idempotency |
| Bắt tất cả exception và trả `Mono.empty()` | Mất thông tin lỗi, thiếu dữ liệu mà không báo | Lọc lỗi, log/metrics, trả ItemResult có status |
| Không phân biệt `Mono.empty()` và `Mono.error` | “Không tìm thấy” và “hệ thống lỗi” bị trộn | `switchIfEmpty` cho empty, `onErrorResume` cho error |
| Chỉ nhìn HTTP 200 để kết luận batch thành công | Item có thể lỗi và được biểu diễn trong body | Định nghĩa status per-item, success count, batch contract |

## 16. Checklist thiết kế một pipeline xử lý nhiều phần tử

Khi gặp một yêu cầu như “đọc 1.000 ID và làm giàu dữ liệu từ API khác”, hãy xác định:

1. **Mỗi item độc lập hay bắt buộc thành công cùng nhau?** Nếu độc lập, ưu tiên recovery riêng trong inner; nếu cả batch phải fail khi một item lỗi, cho lỗi lan truyền và xử lý ở boundary phù hợp.
2. **Nguồn nào có thể lỗi?** Tách outer (đọc danh sách ID, kết nối nguồn) khỏi inner (tra từng ID), và cả bước mapper/định dạng/response downstream.
3. **Kết quả khi item thất bại là gì?** Bỏ item, lấy cache, trả DTO chứa lỗi hay fail batch? Không tự ý chuyển lỗi nghiệp vụ quan trọng thành kết quả hợp lệ.
4. **Có cần retry không?** Retry đúng inner nếu chỉ muốn thử lại ID thất bại; lọc transient errors, thêm backoff, timeout và idempotency.
5. **Có cần giữ thứ tự không?** `flatMap` ưu tiên merge khi có kết quả; `concatMap` tuần tự; `flatMapSequential` giữ thứ tự đầu ra với chi phí buffer.
6. **Làm sao quan sát?** Đo lỗi trước khi recovery làm mất tín hiệu, báo trạng thái rõ trong kết quả, và ghi nhận các lỗi outer/batch riêng.
7. **Đã thử tình huống biên?** Item đầu lỗi, item giữa lỗi, nhiều item lỗi cùng lúc, nguồn outer lỗi, nguồn trả empty, retry kiệt, hủy sớm và side effect đã xảy ra.

**Ghi nhớ:** **đặt `onErrorResume` bên trong `flatMap`/`concatMap`** khi muốn khôi phục lỗi của một phần tử và cho các phần tử khác tiếp tục. **Đặt sau toàn Flux** khi muốn thay thế toàn chuỗi đã thất bại bằng một fallback chung. Tương tự, vị trí của `retryWhen` quyết định bạn thử lại **một inner** hay **toàn upstream**. Trong Reactor, lỗi là tín hiệu terminal; phạm vi recovery phải xuất phát từ hợp đồng nghiệp vụ.

## Tài liệu đối chiếu

- Reactor Core Reference Guide — Error Handling: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Reactor `Flux` API — `onErrorResume`, `onErrorContinue`, `flatMap`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor `Mono` API — `onErrorResume` và `retryWhen`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Reference — FAQ, retry và các tình huống thường gặp: https://projectreactor.io/docs/core/release/reference/faq.html
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Reactive Streams specification: https://www.reactive-streams.org/
