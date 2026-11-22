# `retry`, `retryWhen` và việc đăng ký lại vào nguồn trong Reactor

## 1. Bối cảnh: lỗi là tín hiệu kết thúc, retry là subscription mới

Trong Reactive Streams, một tín hiệu `onError(Throwable)` **kết thúc subscription hiện tại**. Publisher không được phát thêm `onNext` hoặc `onComplete` trên cùng subscription sau `onError`. Vì vậy, khi dùng `retry` hoặc `retryWhen`, Reactor **không hồi sinh subscription đã lỗi**; nó tạo **lần đăng ký mới vào phần upstream** của operator retry.

Đây là điểm cốt lõi của chủ đề **Lỗi và thử lại**: retry là cơ chế tái đăng ký có điều kiện, chứ không phải câu lệnh Java “chạy lại đúng dòng vừa lỗi” hay “tiếp tục từ phần tử kế tiếp”. Cần hiểu nó để tránh lặp dữ liệu, lặp tác vụ ghi và tạo vòng thử lại vô hạn.

Sau bài học, bạn có thể:

- Mô tả chính xác cơ chế `source → onError → retry → subscribe(source)` và ảnh hưởng của vị trí operator.
- Dùng `retry(n)`, `retryWhen(Retry.max(n))`, `Retry.fixedDelay`, `Retry.backoff` và `filter` đúng ngữ nghĩa.
- Tính **tổng số subscription** gồm lần ban đầu và các lần thử lại.
- Phân biệt retry sau lỗi với `repeat` sau hoàn tất; phân biệt `retryWhen` và `onErrorResume`.
- Nhận ra dữ liệu có thể bị phát lặp khi `Flux` đã phát `onNext` rồi lỗi.
- Thiết kế retry có giới hạn, có độ trễ, có lọc loại lỗi và an toàn cho side effect.
- Kiểm thử bằng Java 17+, Reactor và StepVerifier.

**Quy tắc ngắn:** `retry(2)` cho phép **tối đa hai lần đăng ký lại**, vì vậy có thể có **ba lần chạy nguồn** (một lần đầu + hai retry). Nó không có nghĩa tổng cộng chỉ có hai attempts.

## 2. Mô hình tín hiệu và dòng thời gian

Xét một `Mono<String>` lạnh gọi API lần đầu bị lỗi tạm thời, lần hai thành công:

~~~text
Downstream                        retry(1)                  Upstream source
     | ---------- subscribe() ------> |                            |
     |                                | -------- subscribe #1 ----> |
     |                                | <------- onError(E) ------- |
     |                                | -------- subscribe #2 ----> |
     |                                | <------- onNext("OK") ----- |
     | <---------- onNext("OK") ------ |                            |
     |                                | <------- onComplete() ----- |
     | <---------- onComplete() ----- |                            |
~~~

Mỗi nguồn con được đăng ký mới có vòng đời tín hiệu riêng; downstream của `retry` nhìn thấy một chuỗi kết quả **như thể** lỗi trung gian đã bị thay thế bởi lần thử sau. Với ví dụ `Mono` lỗi trước khi phát giá trị, downstream có thể chỉ thấy `onNext("OK")` và `onComplete`.

Các ranh giới cần phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| `Publisher` nguồn | Định nghĩa cách tạo dữ liệu cho mỗi subscription; có thể lạnh, nóng, có trạng thái hoặc dựa trên I/O |
| Subscription lần đầu | Có thể phát giá trị rồi hoàn tất, hoặc phát một số giá trị rồi lỗi |
| `retry(n)` | Khi upstream báo `onError`, cho phép đăng ký lại tối đa n lần |
| `retryWhen(Retry...)` | Khi có `onError`, đưa lỗi vào chiến lược Retry để quyết định có retry, chờ bao lâu, lọc lỗi nào |
| Downstream | Nhận phần tử của các lần thử; có thể thấy trùng lặp nếu upstream đã phát dữ liệu trước khi lỗi |

**Không phải lỗi nào cũng retry được.** Lỗi parse dữ liệu, validation, authentication sai hoặc request không hợp lệ thường không tự khỏi. Những lỗi gián đoạn tạm thời như timeout hoặc dịch vụ trả 503 có thể phù hợp với retry **nếu tác vụ an toàn khi lặp lại**.

## 3. `retry(n)`: số lần retry, tổng số lần gọi nguồn

Với `Mono`:

~~~java
Mono<String> result = callRemote()
    .retry(2);
~~~

Đây là snippet: `callRemote()` trả về `Mono<String>`. Nếu có lỗi, Reactor đăng ký lại tối đa hai lần. Tổng số lần bắt đầu subscription phía upstream có thể là **3**. Nếu nguồn thành công ngay thì chỉ chạy một lần; nếu lần hai thành công thì không dùng hết lượt retry.

| Chiến lược | Tổng subscription tối đa | Mô tả |
| --- | ---: | --- |
| Không retry | 1 | Lỗi đầu tiên đi xuống subscriber |
| `retry(0)` | 1 | Không cho phép lần đăng ký lại |
| `retry(1)` | 2 | Một lần đầu + một retry |
| `retry(2)` | 3 | Một lần đầu + tối đa hai retry |
| `retry(3)` | 4 | Một lần đầu + tối đa ba retry |
| `retry()` | Không đặt giới hạn số lần | Có thể lặp mãi nếu nguồn liên tục lỗi; cần hết sức thận trọng |

Phương thức `retry()` không có tham số trong Reactor dùng chiến lược thử lại không giới hạn. Không nên dùng cho production nếu không có một điều kiện dừng khác rõ ràng: có thể tạo **vòng resubscribe dày đặc**, ăn CPU và gây tải liên tục lên backend đang lỗi.

Với nguồn luôn lỗi, `retry(2)` cuối cùng phát **lỗi của lần thử cuối** cho downstream. Nó không đổi lỗi thành success. Để biến lỗi cuối thành một giá trị thay thế, có thể ghép `onErrorResume` **sau** operator retry khi nghiệp vụ cho phép.

## 4. Ví dụ Java 17+ chạy được: chứng minh nguồn được đăng ký lại

Tạo dự án Gradle với file `build.gradle`:

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

application {
    mainClass = 'RetrySubscriptionDemo'
}
~~~

Tạo file `src/main/java/RetrySubscriptionDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class RetrySubscriptionDemo {
    public static void main(String[] args) {
        AtomicInteger monoSubscriptions = new AtomicInteger();

        Mono<String> unstableMono = Mono.defer(() -> {
            int attempt = monoSubscriptions.incrementAndGet();
            System.out.println("mono subscription #" + attempt);
            if (attempt < 3) {
                return Mono.error(
                    new IllegalStateException("temporary failure")
                );
            }
            return Mono.just("ready");
        });

        String result = unstableMono.retry(2).block();
        System.out.println("mono result=" + result);

        AtomicInteger fluxSubscriptions = new AtomicInteger();

        Flux<Integer> unstableFlux = Flux.defer(() -> {
            int attempt = fluxSubscriptions.incrementAndGet();
            System.out.println("flux subscription #" + attempt);
            return Flux.just(10, 20)
                .concatWith(Mono.<Integer>error(
                    new IllegalStateException("read failed")
                ));
        });

        List<Integer> received = unstableFlux.retry(1)
            .onErrorResume(error -> {
                System.out.println("final error=" + error.getMessage());
                return Flux.empty();
            })
            .collectList()
            .block();

        System.out.println("flux received=" + received);
    }
}
~~~

Chạy `gradle run --quiet` hoặc `./gradlew run --quiet` nếu dự án có Gradle Wrapper. Với chương trình trên, stdout:

~~~text
mono subscription #1
mono subscription #2
mono subscription #3
mono result=ready
flux subscription #1
flux subscription #2
final error=read failed
flux received=[10, 20, 10, 20]
~~~

**Diễn giải nhánh Mono:**

1. `Mono.defer` chưa chạy factory khi assembly; mỗi subscription mới gọi factory.
2. Đăng ký lần #1 và #2 nhận `onError("temporary failure")`.
3. `retry(2)` dùng hai lượt retry cho lần #2 và #3; lần #3 trả `"ready"`.
4. Downstream nhận một kết quả `"ready"`, không nhận hai lỗi tạm thời. Kết quả chứng minh retry thực hiện **đăng ký lại**.

**Diễn giải nhánh Flux:**

1. Subscription #1 phát `10`, `20` rồi `onError("read failed")`.
2. `retry(1)` đăng ký lại nguồn từ đầu; subscription #2 **phát lại `10` và `20`** trước khi tiếp tục lỗi.
3. Hết lượt retry; `onErrorResume` ở phía downstream nhận lỗi cuối, in thông báo và hoàn tất với `Flux.empty()`.
4. `collectList()` thu các giá trị đã nhận trong cùng **subscription downstream**, nên có `[10, 20, 10, 20]`. Đây là ví dụ rõ ràng cho nguy cơ duplicate data.

**Lưu ý:** `block()` ở ví dụ chỉ để chương trình console chờ kết quả và in theo thứ tự xác định. Không gọi `block()` trong một reactive request handler hoặc event-loop Spring WebFlux.

## 5. `retryWhen`: chính sách retry theo tín hiệu lỗi

`retryWhen` nhận một đối tượng chiến lược `reactor.util.retry.Retry`. Trong Reactor hiện đại, nên dùng factory như `Retry.max`, `Retry.fixedDelay` và `Retry.backoff`, sau đó cấu hình filter, logging hoặc ngưỡng.

Ví dụ giới hạn hai lượt retry:

~~~java
Mono<String> result = callRemote()
    .retryWhen(Retry.max(2));
~~~

Về **số lần đăng ký lại**, trường hợp thông thường tương đương `retry(2)`. Tuy nhiên **lỗi cuối khi cạn retry có thể khác**: `retryWhen(Retry.max(2))` mặc định phát một exception biểu thị **retry exhausted**, mang nguyên nhân cuối trong `getCause()`. Có thể kiểm tra bằng `reactor.core.Exceptions.isRetryExhausted(error)`.

Nếu muốn truyền chính lỗi cuối thay vì exception bọc “hết lượt retry”:

~~~java
Mono<String> result = callRemote()
    .retryWhen(
        Retry.max(2)
            .onRetryExhaustedThrow((spec, signal) -> signal.failure())
    );
~~~

Hai đoạn là snippet, giả sử `callRemote()` có sẵn và import `Mono`/`Retry`. Khi log lỗi production, lưu cả lỗi gốc (cause) và số lần retry; đừng mặc định mọi exception sau `retryWhen` đều là lỗi mạng trực tiếp, vì nó có thể là wrapper do policy tạo ra.

Các lựa chọn chính:

| Chiến lược | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| `Retry.max(3)` | Tối đa ba lần retry không định nghĩa delay | Thử lại nhanh, nguồn rẻ, đã có điều kiện giới hạn rõ ràng |
| `Retry.fixedDelay(3, Duration.ofMillis(200))` | Tối đa ba retry, chờ một khoảng cố định giữa các lần | Hệ thống cần khoảng nghỉ tối thiểu mỗi lần |
| `Retry.backoff(3, Duration.ofMillis(200))` | Tối đa ba retry, delay tăng dần dạng exponential backoff | Lỗi quá tải/thất bại tạm thời; tránh dồn request |
| `.filter(predicate)` | Chỉ thử lại các loại lỗi được chọn | Không retry lỗi nghiệp vụ/validation |
| `.doBeforeRetry(signal -> ...)` | Quan sát chính sách đã quyết định retry | Metrics/log về lỗi và số lần retry |
| `.jitter(0.5)` | Ngẫu nhiên hóa khoảng chờ quanh backoff | Tránh nhiều client cùng retry đồng bộ |
| `.onRetryExhaustedThrow(...)` | Chọn exception cuối khi hết lượt retry | Giữ nguyên lỗi gốc hoặc ánh xạ lỗi ứng dụng |

**Số lần retry trong `Retry.max(n)` và `Retry.backoff(n, ...)` vẫn là n lần **đăng ký lại**, cộng một lần subscription ban đầu. Đừng nhầm n là tổng số HTTP requests.

## 6. Backoff, jitter, lọc lỗi và lần thử cuối

Cấu hình điển hình cho một thao tác đọc remote có thể retry:

~~~java
Mono<String> result = callRemote()
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.5)
            .filter(error ->
                error instanceof java.io.IOException ||
                error instanceof java.util.concurrent.TimeoutException
            )
            .doBeforeRetry(signal -> System.out.println(
                "retry #" + (signal.totalRetries() + 1)
                + ", cause=" + signal.failure().getClass().getSimpleName()
            ))
            .onRetryExhaustedThrow(
                (spec, signal) -> signal.failure()
            )
    );
~~~

Snippet trên cần import `java.time.Duration`, `Mono` và `reactor.util.retry.Retry`; `callRemote()` là phương thức nguồn do ứng dụng cung cấp. Ý nghĩa:

- **3** là số lượt retry tối đa; có thể tạo tối đa 4 subscriptions.
- **200 ms** là mức chờ tối thiểu khởi đầu trong chính sách backoff. Những lượt sau có thể chờ lâu hơn theo cấp số nhân, bị chặn bởi `maxBackoff(2s)`.
- **`jitter(0.5)`** làm khoảng chờ thực tế biến động theo chính sách; vì vậy **không dự đoán chính xác mili giây** từng attempt trong log/test.
- **`filter`** chỉ cho phép các lỗi đã liệt kê; lỗi khác truyền thẳng xuống downstream mà không retry.
- **`doBeforeRetry`** quan sát tín hiệu đã được chọn để retry; `Retry.RetrySignal.totalRetries()` là bộ đếm số lần retry **đã xảy ra trước lần xử lý tín hiệu này**, bắt đầu từ 0. Vì vậy khi in số thứ tự retry sắp thực hiện ta cộng 1.
- **`onRetryExhaustedThrow`** ở đây trả về lỗi gốc cuối, tiện cho code bên ngoài cần giữ nguyên loại exception.

`Retry.fixedDelay` không nhân khoảng chờ theo lũy thừa, còn `Retry.backoff` có thể có jitter mặc định; nếu muốn test thời gian chính xác, nên đặt jitter rõ ràng về 0 trong test và dùng virtual time.

**Đừng retry mọi lỗi:** timeout/network reset/503 có thể tạm thời; lỗi validation 400, thiếu quyền 403, mật khẩu sai, dữ liệu hỏng, lỗi cấu hình hoặc sai schema thường sẽ lặp lại và tốn tài nguyên. HTTP 429 cần chính sách giới hạn tốc độ và có thể yêu cầu tôn trọng header `Retry-After`, không cứ thử liên tục.

## 7. Vì sao resubscribe có thể lặp side effect?

Mỗi lần resubscribe upstream có thể **chạy lại toàn bộ quá trình chuẩn bị request, tạo connection, gửi thông tin hoặc ghi dữ liệu**. Ví dụ:

~~~java
Mono<Receipt> createPayment = Mono.defer(() ->
    paymentClient.charge(orderId, amount)
);

Mono<Receipt> retrying = createPayment.retry(3);
~~~

Đây là snippet giả định `paymentClient.charge(...)` trả `Mono<Receipt>`. Nếu server đã **ghi nhận giao dịch** nhưng response bị mất trên mạng, client nhìn thấy lỗi và retry. Request thứ hai có thể thu tiền thêm lần nữa trừ khi API đảm bảo **idempotency**.

Không mặc định `Mono` hoặc `Flux` đảm bảo exactly-once. Retry cho một thao tác hiệu ứng phụ phải có chính sách nghiệp vụ phù hợp:

1. **Idempotency key**: client tạo một khóa cố định cho cùng thao tác logic (ví dụ một mã giao dịch/order) và server từ chối/đưa lại kết quả nếu đã xử lý cùng khóa. **Giữ cùng key qua các attempts**; tạo key mới trong `defer` mỗi retry là sai mục tiêu.
2. **Ràng buộc dữ liệu**: unique constraint, ghi trạng thái transaction và so khớp response để tránh duplicate write.
3. **Giới hạn attempts/delay**: tránh retry storm trong lúc backend quá tải.
4. **Chỉ retry lỗi tạm thời**: yêu cầu đầu vào sai thường không thể sửa nhờ retry.
5. **Quan sát và đối soát**: có correlation ID/attempt number, log và reconciliation nếu server đã xử lý nhưng response thất bại.

Với thao tác **đọc** không có side effect, retry thường an toàn hơn, nhưng vẫn tốn tài nguyên. Với **ghi** hoặc thao tác bên ngoài (thu tiền, gửi email, đặt hàng), không bật retry mù quáng.

## 8. Vị trí operator retry quyết định phần nào chạy lại

Retry chỉ **đăng ký lại vào upstream của chính nó**. Với chuỗi:

~~~java
Flux<Integer> result = fetchNumbers()
    .map(x -> x * 2)
    .retry(2)
    .filter(x -> x > 0);
~~~

Khi `fetchNumbers()` hoặc `map` phía trên `retry` báo lỗi, Reactor resubscribe vào **cả đoạn `fetchNumbers → map`**. `filter` phía sau tiếp tục thuộc cùng chuỗi downstream và không tự thay đổi ngữ nghĩa request.

Ngược lại:

~~~java
Flux<Integer> result = fetchNumbers()
    .retry(2)
    .map(x -> unsafeTransform(x));
~~~

Nếu `unsafeTransform(x)` **ném lỗi ở downstream của retry**, `retry(2)` không nhìn thấy lỗi đó như một tín hiệu từ upstream của chính nó để kích hoạt retry. Muốn cả khâu transform được retry, cần đặt retry **sau** `map`; nhưng khi đó source có thể được gọi lại và dữ liệu trước lỗi có thể phát lại.

Khác biệt này quan trọng khi ghép:

- `doOnError` **trước** `retry`: hook có thể chạy ở từng attempt thất bại.
- `doOnError` **sau** `retry`: hook chỉ thấy lỗi cuối còn lại sau khi policy hết lượt hoặc từ chối retry.
- `onErrorResume` **trước** `retry`: nếu đã biến mọi lỗi thành giá trị/fallback hoàn tất bình thường, retry có thể **không có lỗi nào** để xử lý.
- `onErrorResume` **sau** `retry`: nguồn được retry trước; fallback chỉ xử lý lỗi còn lại khi policy bỏ cuộc.
- `timeout` trước retry: timeout có thể áp dụng riêng từng subscription/attempt.
- `timeout` sau retry: có thể giới hạn thời gian chờ của toàn pipeline retries, tùy phạm vi publisher được bao.

**Ví dụ tương phản về hook:**

~~~java
Mono<String> a = callRemote()
    .doOnError(error -> recordAttemptFailure(error))
    .retry(2)
    .doOnError(error -> recordFinalFailure(error));
~~~

Đây là snippet; hai hàm ghi log/metric là hàm ứng dụng. Một lỗi có thể được ghi nhiều lần ở hook đầu, nhưng chỉ có một tín hiệu lỗi cuối tới hook sau nếu tất cả attempts thất bại.

## 9. Khác biệt với `repeat`, `onErrorResume` và `switchIfEmpty`

| Operator | Điều kiện tác động | Hành vi |
| --- | --- | --- |
| `retry(n)` | `onError` | Resubscribe upstream tối đa n lần |
| `retryWhen(Retry...)` | `onError` | Resubscribe theo chiến lược đếm, delay, filter hoặc tùy biến |
| `repeat(n)` | `onComplete` | Lặp lại subscription upstream sau hoàn tất bình thường, với giới hạn |
| `onErrorResume(fn)` | `onError` | Chuyển sang publisher fallback thay vì thử lại chính nguồn |
| `onErrorReturn(value)` | `onError` | Trả giá trị dự phòng rồi hoàn tất |
| `switchIfEmpty(fallback)` | Nguồn hoàn tất **không phát giá trị** | Dùng fallback; đây không phải phản ứng với lỗi |
| `onErrorMap(fn)` | `onError` | Đổi exception, không tự retry nguồn |
| `doOnError(fn)` | `onError` | Thực hiện side effect quan sát rồi cho lỗi đi tiếp, không phục hồi |

**`retry` và `repeat` không thay thế nhau.** Nguồn `Flux.just(1,2)` hoàn tất thành công sẽ không kích hoạt `retry`; `repeat(1)` có thể phát `1,2,1,2` vì nó lặp sau `onComplete`. Ngược lại, một nguồn luôn phát `onError` sẽ không được `repeat` cứu.

**`onErrorResume` không thực hiện lại nguồn bị lỗi** theo mặc định: nó chuyển sang publisher thay thế. Khi bài toán là trả cache khi request thất bại, cách ghép thường là thử vài lần hợp lý rồi fallback; khi nghiệp vụ không cho phép lặp side effect, có thể bỏ retry và fallback/ghi lỗi ngay.

## 10. Nguồn lạnh (cold) và nóng (hot) khi retry

### Nguồn lạnh: mỗi subscribe thường làm lại công việc

Ví dụ `Mono.defer`, `Mono.fromCallable` và `Flux.range` là các nguồn quen thuộc có khả năng tạo lại chuỗi sự kiện cho từng subscription:

~~~java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> source = Mono.fromCallable(() -> calls.incrementAndGet());

Mono<Integer> result = source
    .flatMap(n -> n < 3
        ? Mono.error(new IllegalStateException("retry me"))
        : Mono.just(n))
    .retry(2);
~~~

Snippet giả định import `AtomicInteger` và `Mono`. Khi subscriber đăng ký và chuỗi chạy bình thường, `calls` lần lượt tăng 1,2,3. Việc tăng bộ đếm là side effect được thực thi ở **lần đăng ký mới**, không phải trạng thái của subscription đã chết được phục hồi.

### Nguồn nóng: retry có thể không phát lại sự kiện đã mất

Publisher hot như `Sinks.Many`, các nguồn callback phát độc lập hoặc pipeline đã `share()` có thể tiếp tục phát khi subscriber lỗi rồi đăng ký lại. `retry` chỉ đăng ký lại theo contract hiện có của source: **không tự phát lại dữ liệu lịch sử** nếu source không lưu/replay. Với một nguồn có replay, những phần tử phát lại phụ thuộc vào chính sách cache/buffer/replay của nguồn.

Vì vậy, không dùng retry như một cơ chế “resume từ offset chính xác” cho stream dữ liệu vô hạn. Khi cần khôi phục một dòng sự kiện/messaging ở đúng vị trí, phải dùng **cursor, checkpoint, offset hoặc token** được source/protocol hỗ trợ. Nếu upstream bắt đầu lại từ đầu, cần deduplicate; nếu upstream không replay, có thể mất sự kiện trong khoảng gián đoạn.

### Source được tạo một lần nhưng đã có side effect

~~~java
String response = legacyHttpCall(); // thực thi ngay
Mono<String> source = Mono.just(response).retry(3);
~~~

Nếu `legacyHttpCall()` đã thành công khi assembly, `retry` không gọi lại hàm ấy. Nếu nó ném exception trước khi `Mono.just` được tạo, không tồn tại publisher để gắn retry và cứu exception tại bước đó.

Cách hoãn lời gọi đồng bộ:

~~~java
Mono<String> source = Mono
    .fromCallable(() -> legacyHttpCall())
    .subscribeOn(Schedulers.boundedElastic())
    .retryWhen(Retry.max(2));
~~~

Đây là snippet có `Schedulers`/`Retry`. `fromCallable` hoãn hành động đến subscription; `subscribeOn(boundedElastic)` cách ly I/O đồng bộ khỏi event-loop WebFlux. `retryWhen` sẽ khiến callable được thực thi lại nếu lỗi hợp lệ. Sử dụng thread worker không biến API blocking thành I/O non-blocking, vì thao tác vẫn chặn worker.

## 11. `RetrySignal` và trạng thái retry

Khi `retryWhen` nhận lỗi, Reactor cung cấp một `Retry.RetrySignal` biểu thị attempt thất bại và thông tin cần thiết cho policy.

Những thành phần hay dùng:

- `signal.failure()`: `Throwable` của lỗi vừa xảy ra.
- `signal.totalRetries()`: số lần retry đã diễn ra trước signal hiện tại, đếm từ 0. Nếu đang chuẩn bị retry đầu tiên, giá trị 0.
- `signal.totalRetriesInARow()`: số retry liên tiếp trong một **đợt lỗi chưa có `onNext` thành công xen giữa**.
- `Retry.max(n).transientErrors(true)` hoặc `Retry.maxInARow(n)`: có thể áp giới hạn theo từng chuỗi lỗi liên tục, thay vì tổng số lần lỗi cả pipeline.

Ví dụ một `Flux` lâu dài phát một vài phần tử thành công, sau đó gặp lỗi tạm thời, retry và sau đó lại có đợt lỗi khác: nếu coi mỗi đợt riêng thì counter theo `totalRetriesInARow()` có thể đặt lại khi có `onNext` thành công sau khi retry. Với `Mono` chỉ có tối đa một `onNext` trước khi hoàn tất, chế độ này thường ít có ý nghĩa hơn một `Flux` dài.

**Cẩn thận về giới hạn retry:** chế độ `transientErrors(true)` có thể làm **tổng số retry suốt đời luồng cao hơn n**, vì mỗi đợt lỗi được tính lại từ đầu. Nó không thích hợp nếu yêu cầu an toàn là “tối đa n HTTP attempts cả đời request” mà không có một bộ đếm tổng riêng.

**Cẩn thận với `Retry.from(...)` tùy biến:** chiến lược retryWhen dùng một publisher “companion” xử lý tín hiệu lỗi. Phát một phần tử từ companion có thể kích hoạt retry; companion phát lỗi sẽ kết thúc với lỗi; companion **hoàn tất bình thường** có thể khiến pipeline retryWhen **hoàn tất thành công**, nuốt lỗi trước đó. Một implementation na ná `companion.take(n)` không tương đương hoàn toàn `retry(n)` lúc cạn lượt. Nên dùng `Retry.max/fixedDelay/backoff` trừ khi có lý do rõ ràng cần viết companion tùy biến.

## 12. Cách đặt độ trễ không gây retry storm

Giả sử 10.000 client đồng thời gọi cùng service và đều nhận 503. Nếu tất cả ngay lập tức gọi `retry(5)`, backend đang yếu sẽ nhận thêm nhiều lần request gần như cùng lúc; điều này được gọi là **retry storm**.

Chính sách vững hơn:

1. Giới hạn retries nhỏ và cụ thể, ví dụ tối đa 2–3 lần cho một yêu cầu đọc.
2. Dùng **backoff tăng dần** để mỗi lỗi không gây request tức thì dồn dập.
3. Dùng **jitter** để các client không đồng loạt thử lại đúng mốc thời gian.
4. Chỉ retry lỗi thuộc nhóm tạm thời, đồng thời tôn trọng điều kiện HTTP/service liên quan.
5. Đặt **timeout toàn bộ request**, không chỉ timeout riêng từng attempt, để tránh tổng thời gian bị kéo dài bởi nhiều lần chờ và backoff.
6. Giới hạn concurrency của luồng request, có bulkhead/circuit breaker khi cần; retry không tự chữa hệ thống vượt tải.
7. Quan sát số attempts, tỉ lệ lỗi cuối và latency tổng, đồng thời giữ correlation ID ổn định qua attempts.

`Retry.backoff` **lên lịch delay** rồi mới cho phép retry; nó không có nghĩa backend đã sẵn sàng ở thời điểm đó. Nếu service vẫn không khỏe, policy sẽ dùng hết lượt và trả lỗi cuối; tầng gọi phải xử lý điều này.

## 13. Ứng dụng với WebClient trong Spring WebFlux

Một ví dụ đọc dữ liệu bằng WebClient (snippet method đặt trong Spring service có `webClient` được inject, và class `ProductDto` của ứng dụng):

~~~java
public Mono<ProductDto> getProduct(String id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(ProductDto.class)
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .filter(error ->
                    error instanceof WebClientRequestException ||
                    (error instanceof WebClientResponseException response
                        && response.getStatusCode().is5xxServerError())
                )
                .onRetryExhaustedThrow(
                    (spec, signal) -> signal.failure()
                )
        );
}
~~~

Các import cần có: `reactor.core.publisher.Mono`, `reactor.util.retry.Retry`, `java.time.Duration`, `org.springframework.web.reactive.function.client.WebClientRequestException` và `WebClientResponseException`. Cách viết kiểm tra exception phù hợp với Java 17.

Diễn giải:

- `webClient.get().retrieve().bodyToMono(...)` tạo publisher HTTP reactive.
- Nếu thất bại do lỗi request liên quan network hoặc server trả **5xx**, filter cho phép retry theo backoff.
- Một lỗi HTTP 4xx như 400/404 thường **không** được retry bởi filter này. 429 có thể yêu cầu policy riêng và xử lý `Retry-After`.
- Sau tối đa ba lượt retry, policy phát lại lỗi cuối (theo `onRetryExhaustedThrow`) để controller/error handler xử lý.
- Không gọi `block()` ở handler WebFlux; trả `Mono<ProductDto>` để framework subscribe.

**Không đồng nhất 5xx với “luôn retry an toàn”.** Một POST/PATCH có side effect có thể đã được server ghi nhận trước khi response 500 hoặc kết nối bị cắt. Chọn retry theo idempotency và hợp đồng server, không chỉ theo status code.

**Retry không thay thế timeout:** WebClient/Netty có cấu hình timeout tầng connect/response riêng; nếu cần giới hạn tổng thời gian pipeline, thiết kế vị trí `timeout(Duration)` phù hợp bên ngoài chuỗi retry. Với timeout đặt trước retry, có thể retry riêng từng attempt; timeout sau retry có thể áp ngân sách tổng cho nguồn retry và các delay.

## 14. Kiểm thử bằng StepVerifier

Để kiểm tra ngữ nghĩa retry, không cần gọi mạng hoặc dùng `Thread.sleep`. Giữ dự án Gradle ở mục 4; thay khối `dependencies` bằng (chỉ có một khối `dependencies`), thêm cấu hình test:

~~~groovy
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
}

test {
    useJUnitPlatform()
}
~~~

Tạo `src/test/java/RetrySubscriptionTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetrySubscriptionTest {
    @Test
    void retryMaxTwoMeansThreeSubscriptionsAtMost() {
        AtomicInteger attempts = new AtomicInteger();
        Mono<String> source = Mono.defer(() -> {
            int n = attempts.incrementAndGet();
            return n < 3
                ? Mono.<String>error(new IllegalStateException("temporary"))
                : Mono.just("OK");
        });

        StepVerifier.create(source.retryWhen(Retry.max(2)))
            .expectNext("OK")
            .verifyComplete();

        assertEquals(3, attempts.get());
    }

    @Test
    void retryDoesNotUndoAlreadyEmittedValues() {
        AtomicInteger attempts = new AtomicInteger();
        Flux<Integer> source = Flux.defer(() -> {
            attempts.incrementAndGet();
            return Flux.just(1, 2)
                .concatWith(Mono.<Integer>error(
                    new IllegalStateException("failed")
                ));
        });

        StepVerifier.create(source.retry(1))
            .expectNext(1, 2, 1, 2)
            .expectError(IllegalStateException.class)
            .verify();

        assertEquals(2, attempts.get());
    }

    @Test
    void nonmatchingErrorIsNotRetried() {
        AtomicInteger attempts = new AtomicInteger();
        Mono<Integer> source = Mono.defer(() -> {
            attempts.incrementAndGet();
            return Mono.error(new IllegalArgumentException("invalid"));
        });

        StepVerifier.create(
                source.retryWhen(
                    Retry.max(3).filter(
                        error -> error instanceof TimeoutException
                    )
                )
            )
            .expectErrorMatches(error ->
                error instanceof IllegalArgumentException
                && "invalid".equals(error.getMessage()))
            .verify();

        assertEquals(1, attempts.get());
    }
}
~~~

Chạy `gradle test` hoặc `./gradlew test`. Cả ba kiểm thử phải PASS:

1. `Retry.max(2)` cho phép lần đầu + hai retry và thành công ở subscription thứ ba.
2. `retry(1)` phát lại những giá trị từ đầu nguồn sau một lỗi; downstream nhìn thấy `1,2,1,2` rồi lỗi.
3. `Retry.filter` từ chối retry `IllegalArgumentException` ngay lần đầu.

Nếu cần kiểm thử một `Retry.fixedDelay` hoặc `Retry.backoff` theo **thời gian**, nên dùng `StepVerifier.withVirtualTime(() -> pipeline...)`, cấu hình nguồn và retry **bên trong supplier** để scheduler được điều khiển bởi virtual time, rồi sử dụng `thenAwait`/`expectNoEvent` thay vì chờ thời gian thật. Tránh kiểm thử khoảng delay jitter với thời gian chính xác khi đang bật ngẫu nhiên.

## 15. Nguyên tắc thiết kế một chính sách retry an toàn

| Câu hỏi | Quyết định cần làm |
| --- | --- |
| Thao tác đang là read hay write? | Với write, xác minh idempotency; không tự retry khi chưa an toàn |
| Lỗi có thể hết nếu thử lại không? | Cho phép timeout/network/5xx phù hợp; không retry dữ liệu hỏng, validation, quyền truy cập sai |
| Giới hạn tổng attempts là bao nhiêu? | Chọn `retry(n)` hoặc `Retry.max(n)`, nhớ n retry + một lần đầu |
| Có cần delay/backoff? | Dùng `Retry.fixedDelay/backoff` với jitter nếu service chịu tải |
| Cần giữ lỗi gốc? | Đọc `getCause()` của retry exhausted hoặc tùy biến `onRetryExhaustedThrow` |
| Có thể phát giá trị trước lỗi không? | Chuẩn bị xử lý duplicate events/side effect khi Flux resubscribe |
| Nguồn cold hay hot? | Cold có thể chạy lại từ đầu; hot không mặc định replay quá khứ |
| Có timeout ngân sách tổng không? | Tránh nhiều attempts và delays kéo dài ngoài SLA |
| Có thể quan sát attempts? | Dùng `doBeforeRetry`, metric/correlation ID và log lỗi cuối |
| Luồng có vô hạn không? | Không để retry mãi thiếu giới hạn; cân nhắc checkpoint/offset và quản trị vòng đời |

## 16. Những lỗi thường gặp

| Nhầm lẫn | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “`retry(3)` nghĩa là ba lần gọi nguồn” | Có thể là **bốn** subscriptions | Đếm lần ban đầu + ba retry |
| “Retry tiếp tục từ phần tử lỗi” | Subscription cũ đã terminal; retry đăng ký lại | Thiết kế cursor/offset hoặc dedupe nếu cần resume |
| “Flux đã phát dữ liệu thì retry không lặp” | Cold source thường phát lại từ đầu | Kiểm thử partial `onNext` trước lỗi |
| “`retry` cứu mọi lỗi trong pipeline” | Chỉ thấy lỗi từ đoạn upstream của nó | Đặt operator retry đúng vị trí |
| “`onErrorResume` trước retry vẫn retry” | Fallback có thể đã nuốt lỗi | Đặt retry trước fallback nếu muốn thử nguồn |
| “`Retry.max(3)` trả nguyên exception gốc” | Khi cạn lượt mặc định có retry-exhausted wrapper | Kiểm tra cause hoặc `onRetryExhaustedThrow` |
| “Retry vô hạn giúp tăng độ tin cậy” | Có thể tạo vòng lặp vô hạn/retry storm | Giới hạn retries, filter, backoff, timeout |
| “Mọi HTTP 5xx đều retry an toàn” | Server có thể đã hoàn thành side effect | Thiết kế idempotency, chọn loại thao tác |
| “`Mono.just(blockingCall())` có thể retry lại call” | Call đã chạy khi tính đối số | Dùng `fromCallable/defer` và scheduler phù hợp |
| “`retryWhen` companion hoàn tất nghĩa là báo lỗi cuối” | Hoàn tất companion có thể khiến pipeline complete, nuốt lỗi | Dùng `Retry.max/backoff` hoặc phát lỗi rõ ràng |
| “Retry tự dừng I/O bị treo” | Retry chỉ kích hoạt sau tín hiệu lỗi, không tự tạo timeout | Cấu hình timeout và cancellation ở I/O |
| “Bật `transientErrors(true)` vẫn giới hạn tổng retries bằng n” | Counter có thể reset sau `onNext` | Giới hạn tổng theo ngân sách riêng nếu cần |
| “Gắn retry là có exactly-once” | Resubscription có thể lặp read/write/callback | Idempotency, dedupe và checkpoint theo source |
| “Gọi `block()` trong controller để biết retry xong chưa” | Chặn thread của WebFlux/event-loop | Trả publisher để framework subscribe |

## 17. Câu hỏi luyện tập và lời giải

**Câu 1.** Một `Mono` luôn báo lỗi. `retry(2)` khiến nguồn được subscribe tối đa mấy lần?

**Đáp án:** Ba lần: một attempt đầu và hai attempts retry. Sau lần thứ ba lỗi, downstream nhận lỗi cuối.

**Câu 2.** `Flux.just(1, 2).concatWith(Mono.error(error)).retry(1)` có thể phát gì?

**Đáp án:** Nó phát `1,2,1,2` rồi `onError`, vì source bị đăng ký lại từ đầu. Bên nhận phải cân nhắc khả năng dữ liệu lặp.

**Câu 3.** Vì sao `onErrorResume` đặt trước `retry` đôi khi khiến `retry` không chạy?

**Đáp án:** Vì `onErrorResume` đã biến lỗi upstream thành một publisher fallback hoàn tất bình thường; phía `retry` không nhìn thấy `onError` để kích hoạt resubscribe.

**Câu 4.** Với `Retry.backoff(3, Duration.ofMillis(100))`, có đảm bảo retry ở chính xác 100, 200, 400 ms không?

**Đáp án:** Không. Backoff có thể áp jitter/mức chặn trên, thời gian scheduling và tải runtime; các con số chính xác không được đảm bảo. Nếu cần test thời gian, cấu hình jitter có chủ đích và dùng virtual time.

**Câu 5.** API chuyển tiền đã ghi nhận giao dịch nhưng trả lỗi mạng. Retry request có chắc an toàn không?

**Đáp án:** Không. Response bị mất không chứng minh server chưa xử lý. Cần idempotency key/transaction ID và khả năng tra cứu trạng thái, hoặc cơ chế phục hồi nghiệp vụ khác.

**Câu 6.** Một `Flux` có hot source vừa lỗi vừa có producer tiếp tục phát. `retry` có tự phát lại mọi event bị bỏ lỡ không?

**Đáp án:** Không. Retry chỉ tạo subscription mới; replay phụ thuộc nguồn. Với stream đáng tin cậy cần cursor/checkpoint/offset hoặc cơ chế replay của hệ thống nguồn.

**Câu 7.** Khi nào `repeat` phù hợp hơn `retry`?

**Đáp án:** Khi muốn lặp lại subscription sau **hoàn tất thành công** (ví dụ phát lại một chuỗi hữu hạn theo quy định). `retry` dùng khi có **onError**.

**Câu 8.** `retryWhen(Retry.max(2).filter(t -> t instanceof TimeoutException))` gặp `IllegalArgumentException` ngay đầu. Tổng subscriptions là mấy?

**Đáp án:** Một. Filter từ chối loại lỗi này nên truyền lỗi xuống downstream mà không có lần đăng ký lại.

## 18. Ghi nhớ và nguồn tham khảo

- **`retry` và `retryWhen` không khôi phục subscription đã lỗi; chúng **đăng ký lại upstream** sau `onError`.**
- **`retry(n)` = tối đa n lần retry ngoài lần subscribe đầu.**
- **`Flux` phát giá trị rồi lỗi có thể phát trùng giá trị sau resubscribe.**
- **`retryWhen` hỗ trợ delay, backoff, jitter, lọc lỗi, quan sát attempts và tùy biến lỗi cuối.**
- **Nguồn hot không tự replay, nguồn cold thường bắt đầu lại;** việc retry thành công/phát lại phụ thuộc contract nguồn.
- **Retry không đồng nghĩa exactly-once.** Với write hoặc tác vụ có side effect cần idempotency/dedupe và ranh giới timeout/giới hạn tải.

Tài liệu chính thức:

1. [Reactor Reference — Handling Errors: Retrying](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) — retry do resubscribe, cách hoạt động `retryWhen`, companion và transient errors.
2. [Reactor Retry API](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html) — `Retry.max`, `maxInARow`, `fixedDelay`, `backoff`.
3. [Reactor RetryBackoffSpec API](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html) — `jitter`, `filter`, `doBeforeRetry`, `onRetryExhaustedThrow`.
4. [Reactor Reference — Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html) — vòng đời nguồn theo subscription.
5. [Spring Framework WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html) — WebFlux và cách xử lý publisher trong HTTP stack.
