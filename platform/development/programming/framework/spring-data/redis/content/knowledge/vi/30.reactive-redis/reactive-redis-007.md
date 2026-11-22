# Đăng ký thực thi, lệnh chạy lặp và tránh subscribe thủ công trong Spring Data Redis Reactive

Trong Spring Data Redis Reactive, lời gọi như `redis.opsForValue().set(key, value)` thường không gửi lệnh Redis ngay. Nó trả về một **Publisher** của Project Reactor, ví dụ `Mono<Boolean>`, mô tả việc cần thực hiện **khi có subscription**. Vì vậy, cùng một đoạn mã có thể có ba kết quả rất khác nhau:

- Chỉ tạo `Mono` mà không có ai đăng ký: **chưa có lệnh Redis nào được thực hiện**.
- Một subscriber đăng ký: lệnh Redis được thực hiện theo luồng reactive.
- Hai subscriber đăng ký độc lập vào một Publisher cold: **lệnh có thể được thực hiện hai lần**.

Điều này vừa là ưu điểm của lập trình reactive, vừa là nguồn lỗi khó phát hiện. Một lệnh `GET` chạy thêm có thể chỉ tốn tài nguyên, nhưng `INCR`, `LPUSH`, `PUBLISH` hoặc thao tác xóa key bị kích hoạt lặp có thể làm sai dữ liệu nghiệp vụ.

Bài học tập trung vào **vòng đời subscription**, **sự lặp lại lệnh do subscribe/retry/repeat**, và **cách viết Spring WebFlux/Reactive Redis theo lối composition** để framework quản lý việc thực thi thay cho gọi `subscribe()` thủ công trong tầng service.

## 1. Mono, Flux và ý nghĩa của subscription

Reactive Streams định nghĩa hai vai trò quan trọng:

- **Publisher:** nguồn phát phần tử, lỗi hoặc tín hiệu hoàn tất.
- **Subscriber:** bên đăng ký nhận các tín hiệu, đồng thời có khả năng yêu cầu dữ liệu và hủy đăng ký.

Project Reactor cung cấp:

| Kiểu | Số phần tử tối đa | Thường dùng với Redis |
|---|---|---|
| `Mono<T>` | 0 hoặc 1 | `GET`, `SET`, `INCR`, `DEL` |
| `Mono<Void>` | Không phát dữ liệu, chỉ hoàn tất hoặc lỗi | Một chuỗi lệnh chỉ cần xác nhận hoàn tất |
| `Flux<T>` | 0 đến nhiều | `SCAN`, đọc tập hợp, danh sách, stream hoặc Pub/Sub |

Khi viết:

```java
Mono<Boolean> write =
        redis.opsForValue().set("demo:332:state", "READY");
```

`write` là **mô tả một thao tác bất đồng bộ**. Nó không phải `Boolean` cho biết Redis đã lưu thành công. Trong mô hình cold publisher của các thao tác Reactive Redis thông thường, lệnh được phát khi có subscription.

### 1.1. Ba giai đoạn: assembly, subscription, signal

```text
Giai đoạn 1 — Assembly
  ReactiveStringRedisTemplate
       |
       +-- opsForValue().set(...)
                |
                v
             Mono<Boolean>
       (xây pipeline, thường chưa gọi Redis)

Giai đoạn 2 — Subscription
  Subscriber / WebFlux / StepVerifier
                |
                v
             subscribe
                |
                v
          driver gửi lệnh Redis

Giai đoạn 3 — Signal
  Redis phản hồi
       |
       +--> onNext(Boolean) (nếu có giá trị)
       +--> onComplete()
       +--> hoặc onError(exception)
```

Trong Reactive Streams, subscriber còn có cơ chế yêu cầu dữ liệu (`request(n)`) và hủy (`cancel()`). Reactor và các lớp tích hợp của Spring thường quản lý những tín hiệu này giúp ứng dụng; không cần viết một `Subscriber` low-level cho mỗi lệnh Redis.

**Không đồng nhất “đã tạo Publisher” với “đã chạy lệnh”.** Đây là khác biệt cốt lõi so với `RedisTemplate` dạng blocking: phương thức imperative thường thực hiện công việc ngay trong lời gọi và trả kết quả hoặc ném exception trực tiếp.

## 2. Thiết lập ví dụ Spring Data Redis Reactive

Một ứng dụng Spring Boot WebFlux có thể khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Ví dụ kết nối Redis test trong `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 3s
```

Với cấu hình phù hợp, Spring Boot có thể tạo bean `ReactiveStringRedisTemplate`. Các ví dụ sử dụng template này vì key/value đều là String, dễ theo dõi bằng Redis CLI và tránh phải giải thích thêm serializer JSON. Trong ứng dụng có model phức tạp, có thể dùng `ReactiveRedisTemplate<K,V>` cùng `RedisSerializationContext` phù hợp.

Service minh họa:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveStatusService {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveStatusService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> save(String id, String status) {
        return redis.opsForValue().set("status:" + id, status);
    }

    public Mono<String> find(String id) {
        return redis.opsForValue().get("status:" + id);
    }
}
```

Các phương thức **trả Publisher cho caller** thay vì tự gọi `subscribe()`. Caller quyết định cách ghép lệnh với luồng còn lại và framework quyết định điểm subscription.

## 3. Publisher chưa được subscribe: không có tác dụng phụ

Xét:

```java
public void wrongSave(String id) {
    Mono<Boolean> ignored =
            redis.opsForValue().set("status:" + id, "READY");

    // Không subscribe, không return, không ghép vào pipeline.
}
```

Mặc dù source có `set(...)`, tác dụng ghi của publisher này không được kích hoạt. Redis key có thể vẫn chưa tồn tại:

```redis
GET status:332
# (nil) nếu chưa có ai ghi key này
```

Tình huống tương tự xảy ra khi dùng những toán tử chỉ mô tả thao tác:

```java
Mono<String> source = redis.opsForValue().get("status:332");

source.map(String::toUpperCase);
// Chỉ tạo một Publisher mới rồi bỏ đi, không có ai subscribe.
```

Hoặc một tác dụng phụ chỉ được xây Publisher ở trong callback:

```java
return redis.opsForValue().get("status:332")
        .doOnNext(value -> {
            redis.opsForValue().set("audit:332", value);
            // Mono<Boolean> bị bỏ đi, không có lệnh ghi audit.
        });
```

`doOnNext` chạy callback khi có dữ liệu, nhưng callback tạo ra một Publisher khác rồi không đưa nó vào pipeline. Phương thức `set` ở đây sẽ không được chạy chỉ vì nó xuất hiện trong lambda.

### Viết đúng bằng flatMap

```java
public Mono<String> readAndAudit(String id) {
    String statusKey = "status:" + id;
    String auditKey = "audit:" + id;

    return redis.opsForValue().get(statusKey)
            .flatMap(value ->
                    redis.opsForValue().set(auditKey, value)
                            .thenReturn(value));
}
```

`flatMap` ghép Publisher lồng bên trong vào chuỗi hiện tại, còn `thenReturn(value)` chỉ phát lại giá trị sau khi thao tác ghi hoàn tất thành công. Khi caller subscribe luồng ngoài, cả `GET` lẫn `SET` đều nằm trên đường thực thi.

**Nguyên tắc:** nếu một tác vụ trả `Mono` hoặc `Flux` mà kết quả của nó phải được thực hiện, hãy **compose** bằng `flatMap`, `concatMap`, `then`, `zipWhen`, `when` hoặc toán tử phù hợp; không chỉ gọi phương thức rồi bỏ Publisher.

## 4. Một lần subscribe, một lần thực thi; subscribe lặp có thể gửi lệnh lặp

Với đa số thao tác Redis thông thường, Publisher là **cold**: mỗi subscriber đi từ đầu luồng và khiến source làm lại công việc.

Ví dụ:

```java
Mono<Long> increment =
        redis.opsForValue().increment("counter:332");

increment.subscribe(result ->
        System.out.println("first = " + result));

increment.subscribe(result ->
        System.out.println("second = " + result));
```

Hai lời gọi `subscribe` trên cùng một `Mono<Long>` có thể tạo **hai lệnh `INCR`**:

```text
counter:332 ban đầu = 0

Subscriber A --------> INCR counter:332 ---> 1
Subscriber B --------> INCR counter:332 ---> 2

Giá trị cuối trong Redis: 2
```

Vì thực thi bất đồng bộ, không nên suy luận subscriber A nhất định nhận số 1 và subscriber B nhất định nhận số 2. Điều chắc chắn trong kịch bản không lỗi là có hai lần tăng từ hai subscription, còn thứ tự hoàn tất phụ thuộc lịch thực thi thực tế.

### 4.1. Một lỗi rất hay gặp trong WebFlux

```java
public Mono<Long> wrongIncrement() {
    Mono<Long> operation =
            redis.opsForValue().increment("counter:332");

    operation.subscribe(value ->
            System.out.println("log value = " + value));

    return operation;
}
```

Trong WebFlux, framework sẽ subscribe vào Publisher trả về để tạo HTTP response. Do service đã tự subscribe thêm một lần, có thể xảy ra **hai lệnh `INCR`**: một từ thao tác log thủ công, một từ WebFlux.

Đúng:

```java
public Mono<Long> incrementAndLog() {
    return redis.opsForValue()
            .increment("counter:332")
            .doOnNext(value ->
                    System.out.println("counter = " + value));
}
```

`doOnNext` không tự tạo subscription. Khi HTTP layer subscribe một lần, chuỗi gồm một lệnh tăng và một hành động log đi kèm. Dùng logging framework thay `System.out` trong production.

### 4.2. Dùng doOnSubscribe để quan sát, không kích hoạt nguồn

```java
Mono<Long> increment =
        redis.opsForValue().increment("counter:332")
                .doOnSubscribe(subscription ->
                        System.out.println("A subscription started"));
```

Không có dòng log nào từ `doOnSubscribe` nếu không có subscriber. Nếu Publisher được subscribe hai lần, log có thể xuất hiện hai lần. `doOnSubscribe` hữu ích để điều tra số subscription, nhưng không nên đặt logic nghiệp vụ có tác dụng ghi dữ liệu trong callback này.

## 5. Trả Mono/Flux từ WebFlux, không subscribe trong controller/service

Một endpoint reactive nên trả Publisher:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/counters")
public class CounterController {

    private final ReactiveStringRedisTemplate redis;

    public CounterController(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    @PostMapping("/{name}/increment")
    public Mono<Long> increment(@PathVariable String name) {
        return redis.opsForValue().increment("counter:" + name);
    }

    @GetMapping("/{name}")
    public Mono<ResponseEntity<String>> read(@PathVariable String name) {
        return redis.opsForValue().get("counter:" + name)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
```

Luồng đúng:

```text
HTTP POST /api/counters/demo/increment
      |
      v
Controller trả Mono<Long>
      |
      v
Spring WebFlux xử lý response và subscribe
      |
      v
Reactive Redis gửi INCR
      |
      v
Mono phát số counter mới
      |
      v
WebFlux ghi HTTP response
```

Việc trả `Mono` để WebFlux xử lý giúp:

- Lỗi Redis đi vào chuỗi xử lý lỗi của request.
- Đường đời subscription gắn với request/response.
- Cancellation có thể lan từ downstream.
- Trace context và các operator như `timeout`, `retryWhen`, `onErrorResume` được ghép trong cùng một luồng.
- Không phải giữ `Disposable` thủ công cho mỗi HTTP request.

**Không bao giờ trả `Mono.just("OK")` sau khi tự `subscribe()` một thao tác ghi Redis rồi coi như đã hoàn tất.** Khi đó HTTP response có thể báo thành công trước khi Redis ghi xong hoặc ngay cả khi ghi thất bại.

Ví dụ sai:

```java
@PostMapping("/wrong")
public Mono<String> wrong() {
    redis.opsForValue()
            .set("order:332", "APPROVED")
            .subscribe();

    return Mono.just("OK");
}
```

Sửa lại:

```java
@PostMapping("/correct")
public Mono<ResponseEntity<Void>> correct() {
    return redis.opsForValue()
            .set("order:332", "APPROVED")
            .thenReturn(ResponseEntity.noContent().build());
}
```

`thenReturn` chỉ chạy khi `set` hoàn tất thành công. Nó không biến Redis thành transaction với database hay hệ thống khác, nhưng bảo đảm response của luồng này phụ thuộc kết quả thao tác Redis.

## 6. Cách ghép nhiều thao tác Redis mà vẫn chỉ subscribe ở biên

### 6.1. Ghi xong rồi mới đọc: then

```java
public Mono<String> saveThenRead(String id, String value) {
    String key = "status:" + id;

    return redis.opsForValue().set(key, value)
            .then(redis.opsForValue().get(key));
}
```

Khi có subscription, Spring thực hiện `SET`, đợi nó hoàn tất rồi mới subscribe `GET`. Giá trị Boolean từ `SET` được bỏ đi bởi `then`.

### 6.2. Chạy lệnh có điều kiện: flatMap

```java
public Mono<Boolean> markDoneIfPending(String id) {
    String key = "task:" + id;

    return redis.opsForValue().get(key)
            .flatMap(current -> {
                if (!"PENDING".equals(current)) {
                    return Mono.just(false);
                }

                return redis.opsForValue().set(key, "DONE");
            })
            .defaultIfEmpty(false);
}
```

Đoạn mã trên **chỉ minh họa composition** và vẫn có race condition: một client khác có thể sửa key giữa `GET` và `SET`. Nếu nghiệp vụ cần kiểm tra và cập nhật nguyên tử, dùng lệnh nguyên tử phù hợp hoặc Lua script/kiểm soát cạnh tranh. Reactor không tự biến hai Redis commands thành một thao tác nguyên tử.

### 6.3. Một chuỗi nhiều key và thứ tự: concatMap

```java
import reactor.core.publisher.Flux;

public Flux<Long> incrementInOrder(Iterable<String> ids) {
    return Flux.fromIterable(ids)
            .concatMap(id ->
                    redis.opsForValue().increment("counter:" + id));
}
```

`concatMap` chờ Publisher trước hoàn tất rồi mới chuyển tới phần tử tiếp theo, giúp thứ tự thực thi dễ dự đoán. Với các thao tác **độc lập**, có thể cân nhắc `flatMap(..., concurrency)` để tăng throughput:

```java
public Flux<Long> incrementWithBoundedConcurrency(
        Iterable<String> ids) {
    return Flux.fromIterable(ids)
            .flatMap(
                    id -> redis.opsForValue()
                            .increment("counter:" + id),
                    8
            );
}
```

`flatMap` có thể thực thi nhiều lệnh cùng lúc và phát kết quả không theo thứ tự đầu vào. Chọn concurrency phù hợp tải Redis và số kết nối, không đặt vô hạn. Dù dùng operator nào, nếu caller subscribe lại toàn bộ `Flux` cold thì **các thao tác nguồn cũng có thể lặp lại**.

### 6.4. zip/when không phải giao dịch Redis

`Mono.zip(a, b)` đợi kết quả từ hai Publisher. `Mono.when(a, b)` đợi hai Publisher hoàn tất mà không cần giữ giá trị. Chúng hữu ích khi công việc độc lập, nhưng:

- Không bảo đảm hai Redis commands là một transaction.
- Nếu một lệnh lỗi, lệnh kia có thể đã chạy hoặc đang chạy.
- Các operator có thể hủy upstream chưa hoàn tất khi có lỗi.
- Nếu một nguồn `Mono` rỗng, `zip` có semantics kết thúc sớm cần lưu ý.

Với chuỗi phải chạy **theo thứ tự**, dùng `then` hoặc `flatMap`; với yêu cầu atomicity của Redis, chọn cơ chế dữ liệu khác phù hợp, không dựa vào `zip`.

## 7. Lỗi lồng Publisher: Mono<Mono<T>>

`map` chỉ biến đổi **giá trị**, không tự subscribe Publisher trả về từ lambda:

```java
Mono<Mono<Boolean>> nested =
        redis.opsForValue().get("status:332")
                .map(value ->
                        redis.opsForValue().set("audit:332", value));
```

Nếu caller chỉ subscribe `nested`, nó nhận một `Mono<Boolean>` làm phần tử. Publisher ghi `audit` ở bên trong vẫn chưa chạy, trừ khi có một subscription khác vào publisher đó.

Cách sửa:

```java
Mono<Boolean> composed =
        redis.opsForValue().get("status:332")
                .flatMap(value ->
                        redis.opsForValue().set("audit:332", value));
```

Quy tắc:

| Toán tử | Lambda trả | Kết quả |
|---|---|---|
| `map(value -> transform(value))` | Một giá trị `R` | `Mono<R>` |
| `map(value -> redisCall(value))` | `Mono<R>` | `Mono<Mono<R>>`, dễ bỏ sót thực thi |
| `flatMap(value -> redisCall(value))` | `Mono<R>` | `Mono<R>`, được ghép vào pipeline |
| `flatMapMany(value -> redisFlux(value))` | `Flux<R>` | `Flux<R>` |
| `then(redisCall)` | Publisher tiếp theo | Chờ upstream hoàn tất rồi chạy publisher tiếp |

Một biểu hiện của lỗi này là thấy log ở đầu pipeline nhưng không có Redis key phụ được cập nhật. Đừng sửa bằng cách thêm `subscribe()` trong lambda; hãy sửa cấu trúc composition.

## 8. repeat và retry làm Redis command chạy lặp

Điểm nguy hiểm không chỉ đến từ việc viết hai dòng `subscribe()`. Một số operator của Reactor **tự resubscribe upstream** theo điều kiện.

### 8.1. repeat: chạy lại sau khi hoàn tất bình thường

```java
Mono<Long> increment =
        redis.opsForValue().increment("counter:332");

Flux<Long> values = increment.repeat(2);
```

Nếu subscriber chạy `values` và mọi lần đều thành công, `repeat(2)` tạo **hai lần lặp thêm sau lần đầu**, tức tổng cộng **ba lần `INCR`**. Không có lỗi nào xảy ra nhưng counter vẫn tăng ba lần.

```text
subscribe vào Flux repeat(2)
    |
    +--> INCR lần 1 --> hoàn tất
    +--> INCR lần 2 --> hoàn tất
    +--> INCR lần 3 --> hoàn tất
```

Một `repeat()` không giới hạn trên nguồn hoàn tất nhanh có thể phát lệnh liên tục tới Redis. Nếu muốn polling, cần có khoảng chờ và giới hạn số lần/điều kiện kết thúc; không dùng repeat vô hạn như một vòng lặp thăm dò không kiểm soát.

### 8.2. retry: chạy lại khi có lỗi

```java
Mono<Long> incrementWithRetry =
        redis.opsForValue().increment("counter:332")
                .retry(2);
```

`retry(2)` cho phép tối đa **hai lần retry** ngoài lần đầu, tức có thể có **ba subscription** vào upstream.

Giả sử Redis đã thực hiện `INCR` nhưng phản hồi bị mất do timeout. Ứng dụng nhìn thấy lỗi rồi retry, dẫn tới `INCR` lần nữa. Kết quả cuối của counter có thể lớn hơn số thao tác nghiệp vụ mà caller nghĩ đã thực hiện.

**Retry không tương đương “chạy lại phần nhận phản hồi”.** Về ngữ nghĩa Reactor, retry đăng ký lại upstream, nên công việc nguồn được thực thi lại nếu Publisher cold.

### 8.3. retryWhen với exponential backoff

```java
import java.time.Duration;
import reactor.util.retry.Retry;

Mono<String> readWithRetry =
        redis.opsForValue().get("status:332")
                .retryWhen(
                        Retry.backoff(3, Duration.ofMillis(200))
                                .maxBackoff(Duration.ofSeconds(2))
                                .jitter(0.5)
                );
```

`Retry.backoff(3, ...)` cho phép tối đa ba lần **retry** sau lần gọi đầu, nếu nguồn liên tục báo lỗi. Operator này phù hợp hơn với `GET` thuần đọc hoặc thao tác được xác định rõ là có thể thử lại an toàn, với điều kiện lỗi thuộc loại transient và giới hạn tải cho phép.

Trong ứng dụng thật, thêm bộ lọc loại lỗi:

```java
Mono<String> guardedRead =
        redis.opsForValue().get("status:332")
                .retryWhen(
                        Retry.backoff(3, Duration.ofMillis(200))
                                .filter(this::isTransientConnectionFailure)
                );
```

`isTransientConnectionFailure(Throwable)` là phương thức **do ứng dụng tự định nghĩa**, không phải API có sẵn của Spring. Không retry lỗi sai serializer, sai kiểu dữ liệu hoặc lỗi nghiệp vụ vĩnh viễn chỉ vì có thể gọi `retryWhen`.

### 8.4. Bảng về khả năng phát lệnh lặp

| Cấu trúc | Có thể phát Redis command bao nhiêu lần? | Cẩn trọng |
|---|---|---|
| Tạo `Mono`, không có subscriber | 0 | Công việc bị bỏ quên |
| Một subscriber vào Mono cold | Thường 1 | Luồng phải xử lý lỗi |
| Hai subscriber vào cùng Mono cold | Thường 2 | Ghi/trừ/tăng bị lặp |
| `repeat(2)` | Tối đa 3 lần khi mỗi lần hoàn tất | Lặp dù không có lỗi |
| `retry(2)` | Tối đa 3 lần nếu lỗi liên tục | Có thể nhân đôi tác dụng phụ |
| `retryWhen(Retry.backoff(3,...))` | Tối đa 4 lần | Chọn lỗi retry, backoff, idempotency |
| `cache()` với Mono cold | Thường chia sẻ một subscription và nhớ kết quả cho người đăng ký sau | Cache cả lỗi/hoàn tất; thay đổi semantics |
| `share()` với Flux | Có thể chia sẻ một upstream khi nhiều subscriber đồng thời | Không phải cơ chế lưu bền/replay mặc định |

Các con số mô tả một Publisher nguồn được subscription thành công theo cơ chế điển hình; không phải cam kết số lệnh đã được Redis server **xử lý thành công** nếu mạng lỗi hoặc cancellation xảy ra.

## 9. Vì sao retry thao tác ghi cần idempotency?

Hãy tách hai lớp:

- **Lỗi phía client:** không nhận được phản hồi `INCR`.
- **Thực tế phía Redis:** `INCR` có thể đã chạy rồi, hoặc có thể chưa chạy.

```text
Ứng dụng                   Redis
    |                        |
    | INCR payment:counter   |
    |----------------------->| (tăng counter)
    |      X kết nối lỗi      |
    |< - - - - - - - - - - - |
    |                        |
    | retry / resubscribe    |
    | INCR payment:counter   |
    |----------------------->| (tăng lần thứ hai)
    |<-----------------------| trả kết quả
```

Từ phía client, lỗi lần đầu không đủ để kết luận lệnh chưa chạy.

### 9.1. So sánh lệnh

| Redis command | Tính an toàn khi gửi lại cùng request |
|---|---|
| `GET key` | Thuần đọc; tương đối an toàn với retry, dù có thể đọc trạng thái mới |
| `SET key fixedValue` | Thường idempotent nếu không có ghi xen vào; phải xét thứ tự cập nhật |
| `DEL key` | Thường có hiệu ứng trạng thái idempotent; giá trị trả và tình huống key được tạo lại có thể khác |
| `INCR key` | Không idempotent: mỗi lần chạy làm tăng |
| `LPUSH key value` | Không idempotent: có thể thêm phần tử lặp |
| `PUBLISH channel value` | Không bảo đảm người nhận không nhận hai lần khi publisher retry |
| `XADD stream * ...` | Có thể sinh bản ghi mới với ID mới ở mỗi lần gửi |

Các nhận xét trên là định hướng, không thay thế phân tích luồng ghi đồng thời.

### 9.2. Một cách làm an toàn hơn: khóa yêu cầu + xử lý nguyên tử

Nếu nghiệp vụ nói “chỉ tăng điểm một lần cho một eventId”, cần cơ chế có định danh:

```text
eventId = evt-332-abc
counter key = points:{user-7}
dedupe key = processed:{user-7}:evt-332-abc
```

Có thể viết một Lua script (các key cùng slot khi dùng Cluster) để:

1. Kiểm tra `eventId` đã được áp dụng chưa.
2. Nếu đã xử lý, trả kết quả “already applied”.
3. Nếu chưa, cập nhật counter và đánh dấu event đã áp dụng.

Điều này giúp một request được gửi lại có thể được nhận diện, nhưng script phải thiết kế TTL, lỗi sau ghi và quy tắc trả kết quả rõ ràng. Nếu tác dụng phụ nằm ở một database hoặc dịch vụ ngoài Redis, cần phối hợp idempotency ở **hệ thống sở hữu tác dụng phụ**, không chỉ đặt một key Redis là đủ.

**Không dùng `retryWhen` cho mọi lệnh ghi như một chính sách toàn cục**. Chọn retry theo từng loại lệnh và tính chất nghiệp vụ.

## 10. Dùng cache, share và defer đúng mục đích

Hai subscription vào một Mono cold thường chạy lại Redis command. Đôi khi cần chia sẻ kết quả của **một lần thực thi** cho nhiều bên sử dụng trong cùng một scope:

```java
Mono<String> readOnce =
        redis.opsForValue()
                .get("status:332")
                .cache();
```

`cache()` làm Mono trở thành nguồn có thể chia sẻ/ký nhớ kết quả: nhiều subscriber có thể dùng cùng terminal signal thay vì đọc lại Redis. Nhưng đây là **cache ở phía Reactor trong bộ nhớ của Publisher object**, không phải TTL của Redis key.

### 10.1. Hai mặt của cache()

```text
Không cache():
  Subscriber A --> Redis GET
  Subscriber B --> Redis GET

Có cache():
  Subscriber A --+
                 +--> một subscription nguồn --> Redis GET
  Subscriber B --+           |
                             v
                      kết quả được chia sẻ
```

Nhưng `cache()` có các đánh đổi:

- Có thể giữ giá trị **lỗi thời** ngay cả khi Redis key đã đổi.
- Có thể nhớ cả **error** và completion; subscriber sau không nhất thiết kích hoạt lại GET.
- Nếu dùng một Publisher lâu sống như singleton với `cache()` vô hạn, giá trị có thể tồn tại trong JVM suốt đời bean.
- Không phù hợp để “vá” thao tác `INCR` hoặc chuyển trạng thái có tác dụng phụ mà không xác định rõ scope và lifecycle.

Nếu muốn cache kết quả một khoảng thời gian ở Reactor:

```java
Mono<String> shortLived =
        redis.opsForValue()
                .get("status:332")
                .cache(Duration.ofSeconds(2));
```

Đây là TTL **in-memory của Mono**, không thay đổi Redis `EXPIRE` hoặc `TTL` của key. Trong ứng dụng nhiều instance, mỗi instance có bộ nhớ riêng.

### 10.2. share() với Flux và ngoại lệ nguồn hot

Với `Flux` cold, mỗi subscriber thông thường tạo một lần chạy upstream. `share()` có thể biến một luồng thành **multicast** khi subscriber đồng thời:

```java
Flux<String> shared =
        Flux.defer(() ->
                    redis.opsForSet().members("active:users"))
                .share();
```

Ví dụ này chỉ minh họa cơ chế chia sẻ một `Flux` hữu hạn, không phải một API cache ổn định để làm nguồn dữ liệu chung cho toàn ứng dụng. Subscriber đến sau có thể **bỏ lỡ phần tử đã phát trước** và khi mọi subscriber rời đi, kết nối upstream có thể được tạo lại. `share()` không tự lưu lịch sử như Redis Stream và không bảo đảm một truy vấn Redis chỉ chạy duy nhất một lần trong suốt vòng đời ứng dụng.

### 10.3. defer: tạo lại logic khi subscription bắt đầu

`Mono.defer` làm một factory chạy **ở thời điểm subscribe**:

```java
Mono<String> newRequestIdPerSubscription =
        Mono.defer(() -> {
            String requestId = java.util.UUID.randomUUID().toString();
            return redis.opsForValue()
                    .set("request:" + requestId, "CREATED")
                    .thenReturn(requestId);
        });
```

Mỗi subscription mới có thể tạo requestId mới. Điều này khác:

```java
String requestId = java.util.UUID.randomUUID().toString();

Mono<String> sameIdForEverySubscription =
        redis.opsForValue()
                .set("request:" + requestId, "CREATED")
                .thenReturn(requestId);
```

Ở cách thứ hai, UUID được sinh ngay khi **assembly** và mọi subscription dùng cùng ID. Chọn hành vi theo nghiệp vụ: có những trường hợp cùng một requestId là mục tiêu để retry idempotent, không phải lỗi. `defer` không làm thao tác Redis “chỉ chạy một lần”; nó có thể làm **nhiều bước của factory lặp lại** ở mỗi subscription.

## 11. subscribe(), block() và các hành vi gây hiểu nhầm

### 11.1. subscribe() không có đối số

```java
redis.opsForValue().set("demo:332", "READY").subscribe();
```

Lệnh có thể được khởi chạy bất đồng bộ, nhưng:

- Caller không nhận được giá trị `Boolean` xác nhận.
- Lỗi có thể không được quan sát đúng nơi nghiệp vụ cần xử lý.
- Request hoặc job có thể kết thúc trước thao tác ghi.
- Không có cơ chế quản lý `Disposable`, timeout hoặc cancellation thích hợp.

Ngay cả `subscribe(value -> log.info(...))` chỉ bổ sung callback giá trị; nếu thiếu error handler và lifecycle vẫn là fire-and-forget không được quản lý.

### 11.2. block() cũng tạo subscription

```java
String value =
        redis.opsForValue().get("demo:332").block();
```

`block()` **subscribe rồi chờ** kết quả, không phải chỉ “đọc thuộc tính đã có trong Mono”. Gọi `block()` hai lần vào một source cold có thể tạo hai lệnh Redis.

Không dùng `block()` trong request path WebFlux hoặc trên Netty event-loop/threads được đánh dấu non-blocking: có thể chặn tài nguyên và Reactor có thể báo lỗi. Ở bài test hoặc ranh giới imperative được kiểm soát, `block()` có thể được dùng có chủ đích, nhưng không nên trộn vào service reactive.

### 11.3. subscribeOn và publishOn không biến logic thành blocking

`subscribeOn(scheduler)` điều khiển ngữ cảnh subscription và `publishOn(scheduler)` chuyển ngữ cảnh xử lý tín hiệu downstream. Chúng không có nghĩa “Redis command sẽ được gửi ngay” và không tự thêm một subscriber.

```java
Mono<String> source =
        redis.opsForValue()
                .get("demo:332")
                .publishOn(reactor.core.scheduler.Schedulers.parallel())
                .map(String::toUpperCase);
```

Chuỗi vẫn cần subscription để chạy. Với driver Redis reactive (thường là Lettuce/Netty), các lệnh I/O đã là non-blocking nên thường không cần bọc từng lệnh Redis trong `Schedulers.boundedElastic()`. `boundedElastic` phù hợp hơn khi phải cô lập API legacy **blocking**, không phải giải pháp mặc định cho mọi luồng reactive.

## 12. Lỗi cancellation và timeout: “ngừng chờ” không đồng nghĩa “undo”

Xét:

```java
Mono<Long> write =
        redis.opsForValue()
                .increment("counter:332")
                .timeout(Duration.ofMillis(150));
```

Nếu timeout phát sinh, Reactor hủy upstream subscription theo cơ chế của operator và phát lỗi cho downstream. Tuy nhiên:

- Redis command có thể đã được gửi và thậm chí đã được thực thi.
- Việc hủy subscription không bảo đảm server có thể hoàn tác lệnh.
- Retry sau timeout có thể tăng counter lần nữa.
- Việc client nhận `TimeoutException` không đủ để suy ra lệnh chưa chạy.

Điều này đặc biệt nguy hiểm khi controller nhận request không còn cần response (client HTTP đóng kết nối), nhưng tác dụng phụ đã được gửi tới Redis. Với các nghiệp vụ thay đổi trạng thái quan trọng, thiết kế idempotency và cơ chế xác minh kết quả.

### 12.1. Phân biệt empty, error và cancel

| Tín hiệu Reactor | Ý nghĩa | Ví dụ Redis |
|---|---|---|
| `onNext(value)` | Publisher phát một kết quả | `GET` thấy String |
| `onComplete` | Publisher kết thúc bình thường | `GET` trả rỗng khi không có key |
| `onError(error)` | Có lỗi được phát | Mất kết nối hoặc command error |
| `cancel` | Downstream không muốn nhận tiếp | HTTP client ngắt, timeout hoặc operator cắt luồng |

`Mono.empty()` **không phải** lỗi Redis. Nếu key không tồn tại, `GET` thường hoàn tất rỗng. Dùng `switchIfEmpty` hoặc `defaultIfEmpty` nếu cần fallback:

```java
public Mono<String> getOrDefault(String id) {
    return redis.opsForValue().get("status:" + id)
            .defaultIfEmpty("UNKNOWN");
}
```

Không dùng `retryWhen` để giải quyết kết quả rỗng: retry chỉ kích hoạt khi có `onError`, không phải khi publisher hoàn tất mà không có giá trị.

## 13. Side-effect operators: doOnNext, doOnSuccess, doFinally

Reactor có nhiều operator phục vụ quan sát:

```java
public Mono<Boolean> saveWithSignals(String key, String value) {
    return redis.opsForValue().set(key, value)
            .doOnSubscribe(s ->
                    log.debug("Subscribed to Redis SET {}", key))
            .doOnNext(result ->
                    log.debug("Redis SET result={}", result))
            .doOnError(error ->
                    log.warn("Redis SET failed for {}", key, error))
            .doFinally(signal ->
                    log.debug("Redis SET terminated with {}", signal));
}
```

Ví dụ giả định lớp có SLF4J `log` được khai báo trước. `doFinally` chạy khi luồng kết thúc do complete, error hoặc cancel; thích hợp để giải phóng/ghi metric theo subscription.

Điểm cần nhớ:

- `doOnNext` chỉ chạy khi thực sự có phần tử. Nó không chạy cho `Mono.empty()`.
- `doOnSuccess` của Mono chạy khi Mono hoàn tất thành công; giá trị có thể là `null` nếu Mono không phát phần tử.
- `doOnError` không tự xử lý lỗi hoặc biến lỗi thành thành công; lỗi vẫn truyền xuống trừ khi có `onErrorResume`/`onErrorReturn` hoặc operator khác.
- `doOnSubscribe` và `doFinally` có thể được gọi **nhiều lần** nếu có nhiều subscriptions hoặc resubscription do retry/repeat.

Đừng đưa những tác vụ nghiệp vụ quan trọng trả Publisher vào `doOnNext` rồi bỏ kết quả. Dùng `flatMap` hoặc `then` để tạo quan hệ phụ thuộc rõ ràng.

## 14. Logging và đo số lần thực thi lệnh Redis

Khi nghi ngờ có lệnh chạy lặp, có thể chèn một hook gần source:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger subscriptions = new AtomicInteger();

Mono<Long> operation =
        redis.opsForValue()
                .increment("counter:332")
                .doOnSubscribe(s -> {
                    int n = subscriptions.incrementAndGet();
                    System.out.println("Source subscription #" + n);
                });
```

Giả sử:

```java
Flux<Long> repeated = operation.repeat(2);
```

Khi một downstream subscriber chạy `repeated`, hook gần source được gọi ba lần trong tình huống bình thường. Nó cho biết số lần **subscription tới upstream**, không phải bằng chứng chắc chắn server thực thi thành công đúng ba Redis commands nếu có lỗi mạng.

Để điều tra:

1. Log `requestId`, `eventId`, Redis key và số lần subscription.
2. Đặt `doOnSubscribe` gần nguồn để nhìn thấy resubscribe do `retry`/`repeat`.
3. Ghi lại exception và operator đang sử dụng.
4. So sánh trạng thái Redis với số lần tác dụng phụ dự kiến.
5. Trong test, dùng key riêng và `StepVerifier` để xác định chính xác kết quả từng subscription.

Không in credential, token hoặc payload nhạy cảm trong log. Tránh dùng `MONITOR` trên Redis production để tìm lệnh lặp nếu chưa xét chi phí và rủi ro lộ dữ liệu; ưu tiên metrics và log ứng dụng.

## 15. Test subscription bằng Reactor StepVerifier

Trong test có kiểm soát, `StepVerifier` là **subscriber** cho Publisher cần kiểm tra. Chỉ tạo Publisher mà không gọi `verify()` thì test chưa kích hoạt thao tác.

Ví dụ một bài integration test với Redis test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest
class ReactiveRedisSubscriptionTest {

    @Autowired
    ReactiveStringRedisTemplate redis;

    @Test
    void sameColdMonoCanIncrementTwice() {
        String key = "test:332:counter";

        StepVerifier.create(redis.opsForValue().set(key, "0"))
                .expectNext(true)
                .verifyComplete();

        Mono<Long> increment = redis.opsForValue().increment(key);

        // Tạo Mono chưa tăng counter.
        StepVerifier.create(increment)
                .expectNext(1L)
                .verifyComplete();

        // Subscribe lần nữa -> INCR thêm lần nữa.
        StepVerifier.create(increment)
                .expectNext(2L)
                .verifyComplete();

        StepVerifier.create(redis.opsForValue().get(key))
                .expectNext("2")
                .verifyComplete();
    }
}
```

Dependency test:

```groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'io.projectreactor:reactor-test'
```

Đoạn test dùng Redis test và key dành riêng, không chạy trên dữ liệu production. Mẫu ở trên có import `assertThat` không bắt buộc vì assertion được thực hiện trong `StepVerifier`; dự án thực tế có thể bỏ import nếu không dùng.

### 15.1. Một test về repeat

```java
StepVerifier.create(
        redis.opsForValue()
                .increment("test:332:counter")
                .repeat(2)
)
    .expectNext(3L, 4L, 5L)
    .verifyComplete();
```

Ví dụ tiếp nối test trước khi counter đang là `2`. Một subscription vào `repeat(2)` thực thi source thêm ba lần, nên giá trị thành `5`. Không dùng `StepVerifier` để ẩn việc retry không an toàn: các lệnh test phải có tác dụng rõ ràng và dữ liệu được cô lập.

### 15.2. Thử phát hiện Publisher bị bỏ quên

```java
Mono<Boolean> write =
        redis.opsForValue().set("test:332:not-subscribed", "YES");

// Chưa subscribe write, nên đây chỉ là assembly.
StepVerifier.create(redis.opsForValue().get("test:332:not-subscribed"))
        .verifyComplete();

StepVerifier.create(write)
        .expectNext(true)
        .verifyComplete();

StepVerifier.create(redis.opsForValue().get("test:332:not-subscribed"))
        .expectNext("YES")
        .verifyComplete();
```

Trước test phải bảo đảm key không có sẵn, ví dụ xóa riêng key đó trong phần setup. Nếu không, `get` ban đầu có thể phát giá trị từ lần chạy trước, khiến test thiếu tính độc lập.

## 16. Ngoại lệ quan trọng: Redis Pub/Sub trả Flux hot

Đến đây, bài tập trung vào các **lệnh thao tác dữ liệu Redis** theo mô hình cold Publisher. Nhưng không phải mọi `Flux` đều cold. Redis Pub/Sub là ví dụ cần phân biệt.

Một luồng nghe Redis Pub/Sub là **dòng sự kiện đang phát theo thời gian**, nơi message từ publisher không được lưu để replay cho subscriber mới. Spring Data Redis mô tả reactive message stream là **hot sequence**: sự kiện có thể đến ngay cả khi subscriber phía ứng dụng chưa sẵn sàng tiêu thụ.

Ví dụ:

```java
Flux<?> messages =
        reactiveRedisTemplate.listenToChannel("app:updates");
```

Luồng trên không có cùng semantics với `redis.opsForValue().get(key)`:

- `GET` là thao tác hữu hạn; cold subscription khác thường gây đọc lại.
- Pub/Sub là luồng sự kiện sống; subscriber đến muộn không được Redis phát lại sự kiện cũ.
- Cơ chế lắng nghe dùng connection/subscription tài nguyên riêng và cần quản lý vòng đời.
- Khi cần nhiều consumer ứng dụng nghe chung một subscription, phải thiết kế chia sẻ luồng và backpressure, không mặc định mỗi `subscribe` tương đương một lần `GET`.

Spring Data Redis có `ReactiveRedisMessageListenerContainer` để quản lý việc đăng ký, chuyển message và tài nguyên. Với ứng dụng cần nhiều channel, nên sử dụng container thay vì tạo nhiều lời gọi `listenToChannel` tùy tiện.

### 16.1. Chỉ định rõ “subscribe” đang có nghĩa nào

Hai khái niệm khác nhau thường cùng dùng từ subscribe:

| Thuật ngữ | Ý nghĩa |
|---|---|
| `Mono/Flux.subscribe()` | Đăng ký **Reactive Streams subscriber**, kích hoạt/nhận tín hiệu từ Publisher |
| Redis `SUBSCRIBE channel` | Đăng ký **Redis Pub/Sub channel** trên Redis connection |

Một application có thể dùng Reactor subscription để bắt đầu luồng Redis Pub/Sub, nhưng chúng là hai tầng API khác nhau. Quy tắc “tránh `subscribe()` thủ công trong service” **không có nghĩa ứng dụng không bao giờ được lắng nghe Redis Pub/Sub**.

### 16.2. Trường hợp subscribe thủ công được phép: ranh giới có lifecycle

Với HTTP request, WebFlux quản lý subscription. Nhưng một thành phần nền tự chạy khi ứng dụng khởi động — ví dụ một consumer Pub/Sub hoặc scheduled processor — cần có một **chủ sở hữu subscription** và cách hủy khi ứng dụng dừng.

Ví dụ ý tưởng:

```java
import jakarta.annotation.PreDestroy;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Component;
import reactor.core.Disposable;

@Component
public class UpdateSubscriptionLifecycle {

    private final ReactiveStringRedisTemplate redis;
    private Disposable subscription;

    public UpdateSubscriptionLifecycle(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    @EventListener(ApplicationReadyEvent.class)
    public synchronized void start() {
        if (subscription != null && !subscription.isDisposed()) {
            return;
        }

        subscription = redis.listenToChannel("app:updates")
                .subscribe(
                        msg -> handleUpdate(msg.getMessage()),
                        error -> reportListenerFailure(error)
                );
    }

    @PreDestroy
    public synchronized void stop() {
        if (subscription != null) {
            subscription.dispose();
            subscription = null;
        }
    }

    private void handleUpdate(String payload) {
        // Chỉ minh họa: không dùng callback này cho blocking I/O.
    }

    private void reportListenerFailure(Throwable error) {
        // Log và kích hoạt chính sách khôi phục thực tế.
    }
}
```

Ví dụ dùng `subscribe` **ở ranh giới top-level của ứng dụng**, không nằm ẩn trong service được WebFlux gọi. Có `Disposable`, xử lý lỗi và dọn tài nguyên khi shutdown. Trong production còn cần chiến lược reconnect/resubscribe, xác nhận subscription đã sẵn sàng, kiểm soát tốc độ xử lý và xử lý lỗi của handler. Pub/Sub là **at-most-once**, nên reconnect không replay message đã mất.

Nếu `handleUpdate` cần gọi một API reactive khác, không mở thêm `subscribe()` trong callback một cách tùy tiện. Cần biến việc xử lý thành chuỗi `concatMap` hoặc `flatMap(..., concurrency)` có xử lý lỗi và lifecycle rõ ràng.

## 17. Khi nào thực sự cần subscribe thủ công?

“Không subscribe thủ công” là một **nguyên tắc kiến trúc**, không phải lệnh cấm tuyệt đối.

| Vị trí | Ai nên sở hữu subscription? | Khuyến nghị |
|---|---|---|
| WebFlux controller trả `Mono`/`Flux` | Spring WebFlux | **Trả Publisher**, không gọi `subscribe()` |
| Service được controller gọi | Caller/downstream | **Compose và return** |
| Repository hoặc Redis adapter reactive | Downstream | Trả Mono/Flux mô tả thao tác |
| Reactor test | `StepVerifier` | `verify()` là điểm subscription có chủ đích |
| Reactive application runner / background processor | Thành phần quản lý lifecycle | Có thể subscribe một lần, giữ `Disposable`, quản lý lỗi |
| Pub/Sub long-lived listener | Container hoặc lifecycle component | Cấu hình quản lý subscription/recovery |
| Code imperative muốn chờ kết quả | Biên tích hợp rõ ràng | `block()` có thể dùng có kiểm soát, tránh WebFlux event loop |

Với job định kỳ, không nên tự gọi `subscribe()` mỗi lần timer chạy nếu job trước có thể chưa hoàn tất. Có thể cần hàng đợi, `concatMap`, trạng thái running, giới hạn concurrency hoặc scheduler quản lý toàn bộ pipeline để tránh các lượt job chồng lên nhau.

## 18. Những lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `SET` được gọi trong code nhưng không có key | Publisher bị tạo rồi bỏ, không có subscription | Trả/compose Mono vào luồng caller |
| `INCR` tăng hai lần cho một HTTP request | Service `subscribe()` rồi WebFlux subscribe thêm | Bỏ subscribe thủ công; dùng `doOnNext` để log |
| Redis nhận lệnh nhiều lần dù chỉ có một HTTP request | `retry`/`repeat` hoặc nhiều downstream subscriptions | Đặt `doOnSubscribe` gần source, xem operator chain |
| `doOnNext` chạy nhưng audit key chưa ghi | Lambda tạo `Mono` rồi bỏ đi | Dùng `flatMap` hoặc `then` |
| Code tạo `Mono<Mono<Boolean>>` | Dùng `map` thay `flatMap` | Làm phẳng Publisher bằng `flatMap` |
| HTTP trả OK trước khi Redis ghi | Fire-and-forget `subscribe()` trong controller | Trả Mono của lệnh ghi; dùng `thenReturn` |
| Retry gây trừ/tăng dữ liệu lặp | Redis đã chạy lệnh nhưng client mất response | Thiết kế idempotency, không retry mù lệnh ghi |
| `GET` không có key nhưng không vào `onErrorResume` | Nguồn hoàn tất rỗng, không báo lỗi | Dùng `defaultIfEmpty`/`switchIfEmpty` |
| `block()` gây lỗi trên event loop | Blocking trong luồng non-blocking | Trả Mono/Flux, bỏ `block()` khỏi WebFlux |
| `cache()` trả dữ liệu cũ sau khi Redis đổi | Cache ở Mono, không có invalidation | Chọn scope/TTL cho cache, hoặc đọc Redis mỗi lần |
| `share()` làm subscriber đến sau thiếu phần tử | Hot multicast không replay lịch sử | Chọn replay/cache nếu thực sự cần, xác định memory/lifecycle |
| Listener Pub/Sub bỏ lỡ sự kiện | Hot stream, subscriber offline hoặc chưa sẵn sàng | Quản lý readiness/recovery; dùng Stream nếu cần replay |
| Một job tạo hàng trăm subscription đang chạy | Mỗi vòng gọi `subscribe()`, không quản lý concurrency | Ghép một pipeline duy nhất và giới hạn số lệnh in-flight |
| Lỗi bị che khuất | `subscribe()` không có error handler | Đưa lỗi vào pipeline và xử lý ở biên có chủ sở hữu |

## 19. Thực hành tự học

### Bài 1 — Chưa subscribe, chưa ghi

1. Xóa key `lab:332:state` trong Redis test.
2. Tạo `Mono<Boolean> write = redis.opsForValue().set("lab:332:state", "READY")` nhưng **không** subscribe.
3. Kiểm tra key bằng Redis CLI `GET lab:332:state`; nó vẫn không tồn tại.
4. Dùng `StepVerifier.create(write).expectNext(true).verifyComplete()`.
5. Kiểm tra lại Redis CLI; key đã có giá trị `READY`.

### Bài 2 — Hai subscriptions, hai lần tăng

1. `SET lab:332:counter 0`.
2. Tạo một `Mono<Long>` từ `increment("lab:332:counter")`.
3. Đăng ký hai lần bằng `StepVerifier` hoặc một test có subscription được quản lý.
4. Xác nhận counter cuối là `2`.
5. Ghi chú tại sao cùng một Java object `Mono` không có nghĩa chỉ một Redis command được gửi.

### Bài 3 — Lệnh bị bỏ quên trong callback

1. Đọc `lab:332:state`.
2. Trong `doOnNext` tạo `redis.opsForValue().set("lab:332:audit", value)` nhưng bỏ Publisher.
3. Chạy luồng đọc qua `StepVerifier`.
4. Quan sát key audit không được tạo.
5. Thay bằng `flatMap(value -> redis.opsForValue().set(...).thenReturn(value))` và thử lại.

### Bài 4 — Retry và repeat

1. Chuẩn bị key counter bằng `0`.
2. Subscribe một lần vào `increment(...).repeat(2)` rồi kiểm tra counter thành `3`.
3. Giải thích vì sao số lần thực thi là 3, không phải 2.
4. Đối với `retry(2)`, xây một nguồn test giả lập lỗi để nhìn thấy số lần resubscribe; không cố tạo lỗi mạng Redis production.
5. Đề xuất chính sách an toàn cho một `GET` và cho một `INCR` sau timeout.

### Bài 5 — Viết WebFlux controller đúng kiến trúc

1. Tạo endpoint POST trả `Mono<Long>` từ `increment(...)`.
2. Thêm `doOnNext` để log giá trị.
3. Không gọi `subscribe()` trong controller/service.
4. Gửi một HTTP request và quan sát Redis counter tăng đúng một lần trong điều kiện không retry.
5. Thử thêm `subscribe()` vào service trên môi trường test để thấy nguy cơ tăng hai lần, rồi bỏ nó.

### Bài 6 — Phân biệt Pub/Sub với Redis GET

1. Tạo một `Mono<String>` cho `GET` và so sánh tác động khi subscribe hai lần.
2. Tạo luồng lắng nghe `app:updates` qua reactive listener.
3. Phát message trước và sau lúc listener sẵn sàng.
4. Quan sát message phát trước subscription không được replay.
5. Giải thích vì sao hot Pub/Sub không thể dùng như Redis Stream có lịch sử và ACK.

## 20. Nguyên tắc ghi nhớ

1. **Publisher là mô tả**, không phải kết quả lệnh Redis. Với các lệnh reactive Redis thông thường, hành động được kích hoạt khi có subscription.
2. **Mỗi subscription vào nguồn cold có thể chạy lại Redis command.** Đặc biệt cẩn thận với `INCR`, `LPUSH`, `XADD`, `PUBLISH` và các tác dụng phụ không idempotent.
3. **retry/repeat là resubscribe.** `repeat(2)` thường tạo ba lượt thực thi khi source hoàn tất; `retry(2)` có thể tạo ba lượt nếu liên tục lỗi.
4. **Compose, không fire-and-forget.** Dùng `flatMap`, `then`, `concatMap` và trả Publisher cho WebFlux; không gọi `subscribe()` ngầm trong service.
5. **Cancellation và timeout không hoàn tác Redis.** Một lệnh có thể đã chạy dù client nhìn thấy lỗi; thiết kế retry và idempotency theo ngữ nghĩa nghiệp vụ.
6. **cache/share/defer thay đổi phạm vi lặp và chia sẻ.** Dùng có chủ đích, không coi là cách sửa mọi lỗi duplicate.
7. **Pub/Sub là trường hợp luồng hot riêng.** Subscription tới dòng message cần quản lý lifetime/readiness, khác với subscription tới một Mono lệnh GET.
8. **subscribe thủ công chỉ nên ở ranh giới được sở hữu rõ ràng**, ví dụ một background listener có lifecycle và `Disposable`; trong HTTP request để framework đăng ký.

## Tài liệu tham khảo

- [Spring Data Redis — Reactive Redis Support](https://docs.spring.io/spring-data/redis/reference/redis/redis-reactive.html): `ReactiveRedisTemplate` và mô hình thao tác Redis không chặn luồng.
- [Spring Data Redis API — ReactiveRedisTemplate](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/ReactiveRedisTemplate.html): `Mono`/`Flux` và các phương thức reactive Redis.
- [Spring Data Redis — Reactive Pub/Sub](https://docs.spring.io/spring-data/redis/reference/redis/pubsub-receiving.html): `ReactiveRedisMessageListenerContainer`, `listenToChannel` và quản lý subscriptions.
- [Project Reactor — Introduction to Reactive Programming](https://projectreactor.io/docs/core/release/reference/coreFeatures.html): cold/hot publisher, assembly và subscription.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `retry`, `retryWhen`, `onErrorResume` và các cách xử lý lỗi.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `subscribeOn`, `publishOn` và blocking vs non-blocking.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` như một subscriber có kiểm soát.
- [Spring Framework — WebFlux Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): controller trả reactive types để WebFlux xử lý.
- [Redis — INCR](https://redis.io/docs/latest/commands/incr/): lệnh tăng có tác dụng phụ khi thực thi nhiều lần.
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): đặc tính nhận message và không có replay mặc định.
