# Kết hợp thao tác bằng map, flatMap, concatMap và then

Spring Data Redis hỗ trợ lập trình **phản ứng (reactive)** thông qua các API như `ReactiveRedisTemplate` và `ReactiveStringRedisTemplate`. Thay vì bắt luồng gọi chờ phản hồi Redis bằng `block()`, mỗi thao tác trả về một publisher của Project Reactor, thường là `Mono<T>` hoặc `Flux<T>`. Ứng dụng ghép các publisher thành một luồng xử lý rồi để subscriber kích hoạt chúng.

Khi viết nghiệp vụ thực tế, khác biệt giữa **`map`, `flatMap`, `concatMap` và `then`** quyết định luồng làm việc có trả đúng dữ liệu, thực thi đúng thứ tự và tránh chờ chặn không cần thiết hay không:

- **`map`:** biến đổi *đồng bộ* giá trị được phát ra.
- **`flatMap`:** dùng giá trị đầu vào để tạo và đăng ký một publisher khác; rất hữu ích để gọi Redis bất đồng bộ phụ thuộc kết quả trước đó.
- **`concatMap`:** xử lý một `Flux` bằng các publisher con **nối tiếp**, giữ thứ tự phát kết quả theo nguồn.
- **`then`:** đợi upstream hoàn tất thành công, **bỏ giá trị upstream** rồi hoàn tất hoặc chạy một publisher tiếp theo.

Bài học thuộc chủ đề **Redis phản ứng** của Spring Data Redis, dùng Java 21, Spring Boot, Reactor và Redis để xây dựng các ví dụ có thể đưa vào service. Trọng tâm là ngữ nghĩa luồng, không phải thay các phép gọi đồng bộ bằng một chuỗi callback khó theo dõi.

## 1. Mô hình căn bản: Redis trả publisher, không trả ngay giá trị

Ví dụ trong API đồng bộ:

~~~java
String value = stringRedisTemplate.opsForValue().get("profile:42");
~~~

Đối với API reactive:

~~~java
Mono<String> value =
    reactiveRedisTemplate.opsForValue().get("profile:42");
~~~

`value` là một **mô tả thao tác bất đồng bộ**, không phải chuỗi đã được đọc. Spring Data Redis reactive thường phát lệnh Redis khi có subscription. Với các publisher lạnh (*cold*) được tạo từ thao tác Redis, **mỗi lần subscribe có thể tạo một lần truy cập Redis mới**.

~~~text
ReactiveStringRedisTemplate
            |
            | get("profile:42")
            v
      Mono<String>         chưa có giá trị String để dùng ngay
            |
            | map / flatMap / then / ...
            v
      Mono<?> / Flux<?>    mô tả chuỗi thao tác
            |
            | subscribe bởi WebFlux, StepVerifier hoặc subscriber khác
            v
      Gửi lệnh Redis
            |
            v
      Phát onNext / onComplete hoặc onError
~~~

Với `Mono<T>`, một lần subscription có tối đa một giá trị `onNext(T)` rồi `onComplete`, hoặc chỉ `onComplete` nếu rỗng, hoặc `onError`. Với `Flux<T>`, có thể có nhiều `onNext` trước tín hiệu kết thúc.

Ba tín hiệu cần phân biệt:

| Tín hiệu | Ý nghĩa | Ảnh hưởng đến operator |
| --- | --- | --- |
| `onNext(value)` | Có giá trị để xử lý | `map` và `flatMap` áp dụng mapper cho giá trị |
| `onComplete()` | Luồng hoàn tất không lỗi | `then` có thể chuyển sang publisher tiếp theo |
| `onError(error)` | Luồng thất bại | Mặc định truyền lỗi xuống dưới; `then` không chạy bước sau |

Một `Mono.empty()` không phải `Mono.just(null)`. Reactor không cho phép phát `null` như giá trị. Ví dụ Redis `GET` một key không tồn tại có thể trả `Mono.empty()`; các mapper của `map` hoặc `flatMap` **không được gọi** vì không có `onNext`.

## 2. API reactive Redis cần dùng

Trong dự án Spring Boot, dependency minh họa (Gradle Groovy với phiên bản do Spring Boot quản lý):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

Starter reactive Redis sử dụng driver phù hợp cho thao tác bất đồng bộ, phổ biến là Lettuce. Dự án chỉ cần reactive Redis và không chạy WebFlux server vẫn có thể xây dựng reactive pipeline; WebFlux ở đây minh họa cách trả publisher tới HTTP layer.

Khai báo service:

~~~java
package com.example.redis.reactive;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ReactiveProfileService {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveProfileService(
            ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }
}
~~~

Một số phương thức thường gặp:

| Thao tác | Publisher thường trả về | Ý nghĩa |
| --- | --- | --- |
| `redis.opsForValue().get(key)` | `Mono<String>` | Giá trị chuỗi hoặc complete rỗng khi key không tồn tại |
| `redis.opsForValue().set(key, value)` | `Mono<Boolean>` | Kết quả ghi theo API |
| `redis.opsForValue().set(key, value, Duration)` | `Mono<Boolean>` | Ghi giá trị kèm TTL |
| `redis.opsForValue().increment(key)` | `Mono<Long>` | Giá trị đếm sau khi tăng |
| `redis.delete(key)` | `Mono<Long>` | Số key được xóa theo thao tác |
| `redis.hasKey(key)` | `Mono<Boolean>` | Kiểm tra key có tồn tại |

Loại phần tử và semantics chi tiết có thể thay đổi theo operation/template sử dụng; không nên tự cast giữa `Boolean`, `Long` và `String` vì cùng gọi Redis.

## 3. `map` — biến đổi một giá trị đồng bộ

`map` nhận mỗi giá trị từ upstream, chạy một hàm biến đổi đồng bộ, rồi phát giá trị đã biến đổi. Nó **không tự mở thêm Redis operation** và không cung cấp một cơ chế chờ publisher khác.

Ví dụ chuẩn hóa tên hiển thị sau khi đọc Redis:

~~~java
import java.util.Locale;
import reactor.core.publisher.Mono;

public Mono<String> displayName(String userId) {
    return redis.opsForValue()
        .get("user:" + userId + ":name")
        .map(String::trim)
        .map(name -> name.toUpperCase(Locale.ROOT));
}
~~~

Luồng:

~~~text
GET user:42:name
      |
      v
Mono<String> ("  Lan  ")
      |
      v map(String::trim)
    "Lan"
      |
      v map(toUpperCase)
    "LAN"
      |
      v subscriber
~~~

Mỗi mapper nhận một **giá trị thật**, không phải `Mono`. Đây là phép biến đổi phù hợp cho:

- Cắt khoảng trắng, chuẩn hóa ký tự.
- Chuyển chuỗi sang DTO hoặc số khi thao tác là đồng bộ.
- Chọn một trường của object.
- Tính toán nhỏ tại CPU mà không yêu cầu I/O bất đồng bộ.

Ví dụ parse:

~~~java
Mono<Long> count = redis.opsForValue()
    .get("metrics:page-views")
    .map(Long::parseLong);
~~~

Nếu chuỗi không phải số hợp lệ, `Long.parseLong` có thể ném `NumberFormatException`. Reactor chuyển exception này thành `onError` để downstream xử lý. Không nên mặc định giá trị thiếu hoặc sai định dạng sẽ được chuyển thành số 0 nếu nghiệp vụ chưa quy định.

### Trường hợp key không tồn tại

~~~java
Mono<String> name = redis.opsForValue()
    .get("user:missing:name")
    .map(String::trim)
    .defaultIfEmpty("Khách chưa có tên");
~~~

Khi `GET` phát `Mono.empty()`, `map` không chạy; `defaultIfEmpty` cung cấp giá trị fallback. Điều này quan trọng hơn việc kiểm tra `name == null` bên trong mapper: trong Reactor, mapper không nhận giá trị null.

### Lỗi thường gặp: `map` trả về `Mono<Mono<T>>`

Đoạn sau không thực hiện thứ tự như mong muốn:

~~~java
Mono<Mono<String>> nested = redis.opsForValue()
    .get("user:42:email")
    .map(email -> redis.opsForValue().get("email:owner:" + email));
~~~

`map` chỉ biến `email` thành một **đối tượng Mono**; kiểu kết quả là `Mono<Mono<String>>`. Inner publisher chưa được tự động đăng ký để lấy dữ liệu owner. Để gọi tiếp Redis theo giá trị email, dùng `flatMap`.

## 4. `flatMap` — phụ thuộc kết quả trước để gọi I/O bất đồng bộ

`flatMap` dùng giá trị upstream để tạo một publisher con, đăng ký publisher con và phát kết quả của nó qua một publisher phẳng.

Ví dụ đọc email rồi tra cứu tên chủ sở hữu qua một key khác:

~~~java
public Mono<String> ownerName(String userId) {
    return redis.opsForValue()
        .get("user:" + userId + ":email")
        .flatMap(email ->
            redis.opsForValue().get("email:owner-name:" + email)
        )
        .switchIfEmpty(Mono.just("Không tìm thấy"));
}
~~~

Luồng thực thi:

~~~text
GET user:42:email
       |
       v
 "lan@example.test"
       |
       v flatMap(email -> GET email:owner-name:<email>)
       |
       v
    "Nguyễn Lan"
       |
       v
 subscriber
~~~

Lệnh `GET email:owner-name:...` **chỉ có đủ key để thực hiện sau khi** lệnh đọc email trả kết quả. `flatMap` biểu diễn sự phụ thuộc dữ liệu này. Nó không chặn thread và không cần gọi `block()`.

### Lưu Redis rồi lấy lại giá trị

~~~java
import java.time.Duration;

public Mono<String> storeThenRead(String key, String value) {
    return redis.opsForValue()
        .set(key, value, Duration.ofMinutes(5))
        .flatMap(saved -> {
            if (!Boolean.TRUE.equals(saved)) {
                return Mono.error(new IllegalStateException(
                    "Redis did not accept the write"
                ));
            }
            return redis.opsForValue().get(key);
        });
}
~~~

`set` trả `Mono<Boolean>`, rồi `flatMap` nhận kết quả ghi và quyết định có tạo một lệnh `GET` khác không. Nếu ghi thất bại, publisher phát lỗi. Nếu ghi thành công, lệnh đọc được thực hiện **sau** khi ghi hoàn tất.

Điều này khác:

~~~java
Mono<String> incorrect = redis.opsForValue()
    .set("example:key", "new")
    .map(saved -> redis.opsForValue().get("example:key"))
    .map(Object::toString);
~~~

Đoạn `map` trên đang chuyển một publisher thành chuỗi đại diện cho object publisher, không trả nội dung key Redis.

### Khi upstream rỗng, `flatMap` không chạy

~~~java
Mono<String> result = redis.opsForValue()
    .get("user:missing:email")
    .flatMap(email -> redis.opsForValue().get("owner:" + email))
    .switchIfEmpty(Mono.error(
        new java.util.NoSuchElementException("User not found")
    ));
~~~

Nếu bước đầu trả `Mono.empty()`, lambda trong `flatMap` không được gọi. `switchIfEmpty` xử lý thiếu dữ liệu một cách tường minh.

## 5. `flatMap` với `Flux`: nhiều inner publisher có thể chạy đồng thời

Khi nguồn là `Flux<T>`, `flatMap` có thể đăng ký nhiều inner publisher cùng lúc. Kết quả được phát **theo thời điểm hoàn tất**, không nhất thiết theo thứ tự phần tử đầu vào.

Ví dụ lấy trạng thái cache của nhiều sản phẩm:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;

public Flux<String> loadProductNames(List<String> ids) {
    return Flux.fromIterable(ids)
        .flatMap(id ->
            redis.opsForValue()
                .get("product:" + id + ":name")
                .map(value -> id + "=" + value)
                .defaultIfEmpty(id + "=(missing)"),
            8 // Tối đa 8 inner publisher hoạt động theo cấu hình operator.
        );
}
~~~

Với đầu vào `["p-1", "p-2", "p-3"]`, kết quả có thể lần lượt là:

~~~text
p-2=Keyboard
p-1=Monitor
p-3=Mouse
~~~

Điều đó **không có nghĩa Redis xử lý sai**: `flatMap` cho phép việc chờ phản hồi diễn ra đồng thời và merge kết quả theo lúc có dữ liệu.

Lưu ý hai giới hạn:

1. `concurrency=8` là giới hạn ở cấp operator cho số publisher con đang hoạt động, không phải cam kết chính xác số socket hay số lệnh Redis đồng thời trên server.
2. Phép merge không bảo toàn thứ tự kết quả đầu vào. Nếu nghiệp vụ cần duy trì thứ tự, phải chọn operator khác.

### Khi nào nên dùng `flatMap`?

Phù hợp khi:

- Mỗi phần tử của nguồn có một thao tác Redis độc lập.
- Thứ tự kết quả không quan trọng hoặc có thể gắn ID và sắp xếp sau.
- Muốn có concurrency hữu hạn để tăng throughput.
- Có thể giới hạn tải Redis và các downstream resource.

Không nên dùng `flatMap` không giới hạn trong luồng có số lượng item lớn rồi mặc định Redis, driver và bộ nhớ luôn chịu được tải. `Flux.flatMap` có tham số `concurrency` và `prefetch` ở những overload tương ứng; hãy lựa chọn theo nhu cầu thay vì dựa hoàn toàn vào mặc định.

## 6. `concatMap` — xử lý từng publisher theo thứ tự

`concatMap` dành cho `Flux`. Nó biến mỗi phần tử thành một publisher con, nhưng **chỉ đăng ký publisher tiếp theo sau khi publisher trước hoàn tất**. Kết quả vì vậy giữ thứ tự các publisher con theo nguồn, trong phạm vi các phần tử thực sự được phát.

Ví dụ ghi nhật ký trạng thái theo thứ tự phát sinh:

~~~java
public Flux<Boolean> writeStatusesInOrder(List<String> statuses) {
    return Flux.fromIterable(statuses)
        .concatMap(status ->
            redis.opsForValue()
                .set("demo:current-status", status)
        );
}
~~~

Với đầu vào `["RECEIVED", "VALIDATED", "COMPLETED"]`, ứng dụng gửi lệnh `SET` nối tiếp: lệnh tiếp theo chỉ được đăng ký sau khi lệnh trước hoàn tất. Nhờ đó, **trong luồng này** các thao tác được xếp theo thứ tự dự kiến.

~~~text
Flux:       RECEIVED    VALIDATED    COMPLETED
                |           |            |
                v           |            |
           SET RECEIVED     |            |
                |           |            |
           complete         |            |
                |           v            |
                |      SET VALIDATED     |
                |           |            |
                |      complete          |
                |           |            v
                |           |      SET COMPLETED
                |           |            |
                v           v            v
           Kết quả 1   Kết quả 2    Kết quả 3
~~~

Ví dụ này **không phải transaction** và không khóa key khỏi những client khác. Một service khác vẫn có thể thay đổi `demo:current-status` giữa các thao tác; `concatMap` chỉ đảm bảo thứ tự subscription và hoàn tất **trong pipeline đang xét**.

### So sánh trên cùng nguồn `Flux`

~~~java
Flux<String> keys = Flux.just("a", "b", "c");

Flux<String> concurrently = keys.flatMap(key ->
    redis.opsForValue()
        .get(key)
        .defaultIfEmpty("(missing)")
);

Flux<String> sequentially = keys.concatMap(key ->
    redis.opsForValue()
        .get(key)
        .defaultIfEmpty("(missing)")
);
~~~

| Thuộc tính | `flatMap` | `concatMap` |
| --- | --- | --- |
| Inner publisher được thực thi | Có thể đồng thời | Nối tiếp từng inner publisher |
| Thứ tự kết quả | Có thể đảo thứ tự | Giữ thứ tự inner theo nguồn |
| Thông lượng khi I/O độc lập | Có thể cao hơn | Có thể thấp hơn vì chờ từng thao tác |
| Khi xử lý có phụ thuộc thứ tự | Cần thêm thiết kế | Phù hợp hơn nếu thứ tự là yêu cầu |
| Giới hạn concurrency | Dùng tham số concurrency | Về ngữ nghĩa xử lý một inner tại một thời điểm |

Trong Reactor còn có `flatMapSequential`: nó có thể đăng ký một số inner publisher đồng thời nhưng **phát kết quả theo thứ tự nguồn**, vì cần buffer kết quả đến sớm. Hữu ích khi muốn cân bằng throughput và thứ tự đầu ra, song có thêm chi phí bộ nhớ. `concatMap` là lựa chọn dễ suy luận nhất khi bản thân **thao tác phụ** cần được thực hiện nối tiếp.

### `concatMap` và đảm bảo thứ tự nghiệp vụ

Không nên suy ra rằng chỉ cần `concatMap` là toàn bộ hệ thống xử lý sự kiện có thứ tự:

- Hai HTTP request khác nhau có thể tạo **hai subscription** và chạy song song.
- Nhiều instance ứng dụng có các pipeline độc lập.
- Một subscriber khác có thể ghi cùng key Redis.
- Retry sau lỗi có thể thực hiện lại một thao tác cũ.

Nếu cần một thứ tự toàn cục hoặc ràng buộc trạng thái giữa nhiều writer, cần thiết kế thêm single-writer, version, optimistic locking, Lua script hoặc giao thức phù hợp với nghiệp vụ.

## 7. `then` — chờ hoàn tất, bỏ qua giá trị upstream

`then` khác `map` và `flatMap` vì nó quan tâm tới **tín hiệu hoàn tất** hơn là giá trị dữ liệu:

~~~java
Mono<Void> completed = redis.opsForValue()
    .set("demo:key", "value")
    .then();
~~~

`set` thường phát `Boolean`; `then()` **bỏ giá trị đó** và trả `Mono<Void>` khi upstream hoàn tất thành công. Nếu upstream lỗi, lỗi vẫn truyền xuống.

Đặc biệt chú ý: nếu upstream phát `Boolean.FALSE` nhưng **hoàn tất bình thường**, `then()` vẫn coi luồng đã complete; nó không hiểu `false` là thất bại nghiệp vụ. Nếu cần xác nhận `Boolean.TRUE`, phải kiểm tra trước `then()`.

~~~java
Mono<Void> safelyWritten = redis.opsForValue()
    .set("demo:key", "value")
    .flatMap(ok -> Boolean.TRUE.equals(ok)
        ? Mono.<Void>empty()
        : Mono.<Void>error(
            new IllegalStateException("Write not accepted")
        )
    );
~~~

### Nối thao tác A rồi thao tác B bằng `then(Mono)`

Ví dụ ghi dấu audit trước khi xóa cache:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;

public Mono<Long> auditThenDelete(String id) {
    String auditKey = "audit:last-invalidated:" + id;
    String cacheKey = "cache:profile:" + id;

    return redis.opsForValue()
        .set(auditKey, "INVALIDATE", Duration.ofDays(1))
        .flatMap(ok -> Boolean.TRUE.equals(ok)
            ? Mono.just(true)
            : Mono.<Boolean>error(
                new IllegalStateException("Audit write failed")
            )
        )
        .then(redis.delete(cacheKey));
}
~~~

Kết quả của `auditThenDelete` là `Mono<Long>`, phát số key cache đã xóa. Không phát giá trị `Boolean` của lệnh audit vì `then(...)` bỏ kết quả upstream.

~~~text
SET audit ... (có TTL)
         |
         v
    Kiểm tra Boolean
         |
         +-- false/error --> onError, không chạy DELETE
         |
         v
   upstream complete
         |
         v
   DELETE cache:profile:id
         |
         v
     Mono<Long>
~~~

**`then` tạo thứ tự thực hiện bên trong cùng một subscription, không tạo transaction nguyên tử.** Nếu ghi audit thành công rồi Redis gặp lỗi trước `DELETE`, audit có thể tồn tại trong khi cache chưa bị xóa. Nếu nghiệp vụ yêu cầu cả hai thay đổi atomically, phải thiết kế cơ chế Redis chuyên biệt hoặc một cách điều phối khác.

### `thenReturn` và `thenMany`

Các biến thể thường gặp:

~~~java
Mono<String> confirmation = redis.opsForValue()
    .set("demo:flag", "READY")
    .thenReturn("Đã gửi yêu cầu ghi");
~~~

`thenReturn(value)` bỏ giá trị upstream và phát một giá trị cố định sau khi upstream complete. Chú ý chuỗi trên chỉ biểu thị thao tác upstream complete, **không kiểm tra `Boolean.TRUE`**. Nếu cần kiểm tra, thêm logic trước `thenReturn`.

~~~java
Flux<String> values = redis.opsForValue()
    .set("demo:prepared", "1")
    .thenMany(
        Flux.just("key:a", "key:b")
            .concatMap(key ->
                redis.opsForValue()
                    .get(key)
                    .defaultIfEmpty("(missing)")
            )
    );
~~~

`thenMany` chờ publisher trước complete rồi chuyển sang một `Flux` khác. Trường hợp này thích hợp cho chuỗi “chuẩn bị” rồi “phát nhiều kết quả”.

### Khác biệt giữa `then` và `flatMap` khi upstream rỗng

~~~java
Mono<String> missing =
    redis.opsForValue().get("nonexistent");

Mono<String> viaFlatMap =
    missing.flatMap(value -> redis.opsForValue().get("fallback"));

Mono<String> viaThen =
    missing.then(redis.opsForValue().get("fallback"));
~~~

Nếu `missing` complete rỗng:

- `viaFlatMap` cũng complete rỗng, **không gọi** `GET fallback`.
- `viaThen` vẫn gọi `GET fallback`, vì nó chỉ chờ upstream **hoàn tất thành công**, không yêu cầu một `onNext`.

Vì vậy, khi yêu cầu “nếu Redis không có key thì tra nguồn khác”, operator phù hợp thường là **`switchIfEmpty`**, không phải `then`:

~~~java
Mono<String> value = redis.opsForValue()
    .get("cache:key")
    .switchIfEmpty(loadFromSource());
~~~

Nếu `loadFromSource()` có side effect ngay khi **tạo publisher**, có thể dùng `Mono.defer(() -> loadFromSource())` để hoãn việc tạo nguồn dự phòng cho tới khi thật sự cần. Với một API trả publisher lạnh đúng chuẩn, việc subscribe vào fallback vốn chỉ diễn ra khi upstream rỗng.

## 8. Bảng chọn operator theo mục đích

| Nhu cầu | Operator chính | Ví dụ |
| --- | --- | --- |
| Chuẩn hóa kết quả GET | `map` | `get(key).map(String::trim)` |
| Parse JSON thành DTO bằng code đồng bộ nhẹ | `map` | `get(key).map(jsonMapper::read...)` với xử lý exception thích hợp |
| Từ ID đọc một key Redis khác | `flatMap` | `get(userKey).flatMap(v -> get(otherKey(v)))` |
| Ghi Redis rồi lấy lại dữ liệu theo kết quả ghi | `flatMap` | `set(...).flatMap(ok -> get(...))` |
| Với nhiều key độc lập, cho phép concurrency | `Flux.flatMap` | `Flux.fromIterable(ids).flatMap(this::load, 8)` |
| Xử lý các thay đổi theo thứ tự đầu vào | `Flux.concatMap` | `Flux.fromIterable(events).concatMap(this::apply)` |
| Đợi thao tác A hoàn thành rồi chạy B, không cần giá trị A | `then` | `writeAudit().then(deleteCache())` |
| Chỉ cần tín hiệu hoàn tất | `then()` | `delete(key).then()` |
| Hoàn tất A rồi phát giá trị cố định | `thenReturn` | `write().thenReturn("ok")` |
| Hoàn tất A rồi phát nhiều phần tử từ B | `thenMany` | `initialize().thenMany(loadAll())` |
| Khi GET không có dữ liệu | `switchIfEmpty` | `get(key).switchIfEmpty(load())` |

Câu hỏi ngắn để chọn:

~~~text
Có một giá trị upstream?
         |
         +-- Cần biến đổi đồng bộ giá trị? --------> map
         |
         +-- Cần gọi publisher khác phụ thuộc nó? -> flatMap
         |
         +-- Có nhiều giá trị, cần thứ tự xử lý? --> concatMap
         |
         +-- Chỉ chờ hoàn tất, bỏ giá trị? -------> then
~~~

## 9. Một ví dụ nghiệp vụ kết hợp nhiều operator

Giả sử dịch vụ nhận danh sách ID sản phẩm và cần:

1. Đọc tên từng sản phẩm từ Redis.
2. Chuẩn hóa tên bằng `trim()`.
3. Ghi một bản ghi “đã xem” cho từng ID.
4. Trả kết quả theo đúng thứ tự ID đầu vào.

Một cách triển khai reactive:

~~~java
package com.example.redis.reactive;

import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductViewService {

    private final ReactiveStringRedisTemplate redis;

    public ProductViewService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public record ProductView(String id, String name) {
    }

    public Flux<ProductView> loadAndRecordViews(List<String> ids) {
        return Flux.fromIterable(ids)
            .concatMap(id -> {
                String productKey = "product:" + id + ":name";
                String viewKey = "product:" + id + ":last-viewed";

                return redis.opsForValue()
                    .get(productKey)
                    .map(String::trim)
                    .filter(name -> !name.isBlank())
                    .flatMap(name ->
                        redis.opsForValue()
                            .set(
                                viewKey,
                                "viewed",
                                Duration.ofMinutes(1)
                            )
                            .flatMap(saved -> Boolean.TRUE.equals(saved)
                                ? Mono.just(new ProductView(id, name))
                                : Mono.<ProductView>error(
                                    new IllegalStateException(
                                        "Cannot write view marker for " + id
                                    )
                                )
                            )
                    )
                    .switchIfEmpty(
                        Mono.just(new ProductView(id, "(missing)"))
                    );
            });
    }
}
~~~

Với mỗi ID, pipeline thực hiện:

~~~text
id
 |
 v
GET product:<id>:name
 |
 +-- không có/chuỗi trống --> ProductView(id, "(missing)")
 |
 v
map(trim) + filter
 |
 v
flatMap(SET last-viewed kèm TTL)
 |
 +-- trả false --> onError
 |
 v
ProductView(id, name)
 |
 v
concatMap chuyển sang ID kế tiếp
~~~

Phân tích operator:

- `map(String::trim)` xử lý giá trị đã có, không gọi thêm Redis.
- `filter` có thể biến chuỗi trắng thành complete rỗng.
- `flatMap` viết marker Redis trước khi phát `ProductView`.
- `switchIfEmpty` tạo bản ghi đại diện cho sản phẩm không có tên trong cache. Nó chỉ xử lý **empty**, không che lỗi Redis.
- `concatMap` cho phép chuỗi đọc/ghi của **ID sau** chỉ bắt đầu khi publisher của ID trước complete.

Với ứng dụng chỉ cần hiển thị dữ liệu và không đòi thứ tự side effect, có thể chuyển `concatMap` sang `flatMap(..., concurrency)` để đọc nhiều key đồng thời. Khi đó kết quả có thể không còn theo thứ tự ID đầu vào.

### Vì sao không dùng `then` trong ví dụ này?

Chúng ta cần giữ tên sản phẩm để tạo `ProductView`. Nếu thay toàn bộ khối ghi bằng `thenReturn(new ProductView(id, name))` mà không kiểm tra `Boolean`, một lệnh `SET` trả `false` nhưng complete bình thường vẫn tạo kết quả thành công. `flatMap` phù hợp hơn vì cần **giá trị trả về của Redis SET** để ra quyết định.

Tuy nhiên, nếu nghiệp vụ chỉ cần chờ một lệnh đã được xác nhận qua operator kiểm tra rồi trả DTO, có thể kết hợp `thenReturn` sau bước kiểm tra:

~~~java
Mono<ProductViewService.ProductView> result =
    redis.opsForValue()
        .set("view:key", "1")
        .filter(Boolean.TRUE::equals)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("SET rejected")
        ))
        .thenReturn(new ProductViewService.ProductView(
            "p-1", "Keyboard"
        ));
~~~

## 10. Điều gì xảy ra khi có lỗi?

Trong pipeline reactive, một lỗi Redis hoặc lỗi mapper có thể tạo tín hiệu `onError`. Mặc định, lỗi này chấm dứt chuỗi downstream:

~~~java
Flux<String> results = Flux.just("a", "b", "c")
    .concatMap(key -> redis.opsForValue().get(key));
~~~

Nếu truy vấn `b` phát lỗi, chuỗi có thể dừng trước khi xử lý `c`. Trong `flatMap` có concurrency, các inner publisher khác có thể đã bắt đầu trước lúc lỗi được quan sát; hủy downstream **không bảo đảm** mọi lệnh Redis đã gửi sẽ được hoàn tác.

### Phục hồi theo từng phần tử hay theo cả pipeline?

Nếu một key không đọc được nhưng vẫn muốn tiếp tục những key còn lại:

~~~java
Flux<String> resilient = Flux.just("a", "b", "c")
    .concatMap(key ->
        redis.opsForValue()
            .get(key)
            .defaultIfEmpty("(missing)")
            .onErrorResume(error ->
                Mono.just("(error reading " + key + ")")
            )
    );
~~~

Đặt `onErrorResume` **bên trong** `concatMap` để lỗi một key được xử lý ở cấp item. Nếu đặt ở cuối toàn bộ chuỗi, lỗi đầu tiên có thể thay toàn bộ phần còn lại bằng một giá trị fallback và kết thúc luồng.

Không nên dùng `onErrorResume(e -> Mono.empty())` cho mọi lỗi rồi coi việc thiếu dữ liệu là bình thường, đặc biệt khi lỗi là timeout, authentication hoặc Redis bị down. Cần phân biệt key không tồn tại (`Mono.empty()`) với thao tác Redis thất bại (`Mono.error(...)`).

### Retry có thể làm thao tác chạy lại

~~~java
Mono<Long> incremented = redis.opsForValue()
    .increment("counter:orders")
    .retry(1);
~~~

Ví dụ này **nguy hiểm nếu timeout xảy ra sau khi Redis đã thực hiện `INCR` nhưng trước khi client nhận phản hồi**: lần retry có thể tăng hai lần.

Retry thường cần thiết cho lỗi mạng tạm thời, nhưng nên dựa trên phân loại lỗi, backoff, idempotency và khả năng quan sát trạng thái thực tế. `retry` không chuyển một thao tác không lũy đẳng thành an toàn.

Nếu cần cập nhật nguyên tử theo điều kiện, hãy dùng thao tác Redis phù hợp hoặc script/giao thức tương ứng; tổ hợp `get().flatMap(current -> set(...))` tự nó **không phải** phép read-modify-write nguyên tử khi có nhiều writer.

## 11. Subscription, backpressure và tránh `block()`

Một pipeline Reactor cần có subscriber:

~~~java
Mono<String> name = redis.opsForValue()
    .get("user:42:name")
    .map(String::trim);

// Mới tạo publisher, chưa thu được kết quả String.
~~~

Trong WebFlux Controller, cách dùng thường là **trả publisher**:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/users")
class UserController {

    private final ReactiveProfileService service;

    UserController(ReactiveProfileService service) {
        this.service = service;
    }

    @GetMapping("/{id}/name")
    Mono<String> name(@PathVariable String id) {
        return service.displayName(id);
    }
}
~~~

Đây là ví dụ phần controller; `ReactiveProfileService` cần triển khai phương thức `displayName` như ví dụ trước. Spring WebFlux đăng ký và tiêu thụ publisher trong vòng đời HTTP request.

Không nên viết:

~~~java
// Anti-pattern trong đường xử lý reactive:
String value = redis.opsForValue().get("user:42:name").block();
~~~

`block()` chặn thread chờ Redis, làm mất lợi ích chính của non-blocking I/O. Trong những thread non-blocking của Reactor/Netty, gọi `block()` có thể gây exception hoặc giảm đáng kể khả năng phục vụ đồng thời. Chỉ dùng trong ranh giới đồng bộ được kiểm soát đặc biệt, không phải cách kết hợp mặc định.

Một anti-pattern khác:

~~~java
public Mono<String> updateAndRead(String key) {
    redis.opsForValue().set(key, "NEW").subscribe();
    return redis.opsForValue().get(key);
}
~~~

Ở đây có **hai subscription độc lập**. Không có bảo đảm `SET` hoàn tất trước `GET`. Lỗi ở subscription ghi cũng có thể bị tách khỏi luồng xử lý mà HTTP caller đang chờ. Để giữ thứ tự và truyền lỗi, phải **compose**:

~~~java
public Mono<String> updateAndRead(String key) {
    return redis.opsForValue()
        .set(key, "NEW")
        .filter(Boolean.TRUE::equals)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("SET rejected")
        ))
        .then(redis.opsForValue().get(key));
}
~~~

### Backpressure không tự giới hạn mọi nguồn tải

Reactor hỗ trợ cơ chế request-demand giữa publisher và subscriber, nhưng điều đó không có nghĩa Redis sẽ tự tạo một hàng đợi vô hạn an toàn cho mọi operator. Nếu `Flux` đầu vào có hàng triệu phần tử và dùng `flatMap` với concurrency cao, áp lực tới Redis và bộ nhớ ứng dụng vẫn đáng kể.

Thực hành phù hợp:

- Dùng `flatMap(mapper, concurrency)` khi thao tác I/O độc lập nhưng cần giới hạn số publisher đang hoạt động.
- Dùng `concatMap` khi cần thứ tự hoặc muốn thực thi từng inner publisher nối tiếp.
- Không gom `collectList()` toàn bộ luồng lớn nếu chỉ cần xử lý streaming.
- Đặt timeout theo yêu cầu nghiệp vụ; có chính sách retry có giới hạn.
- Quan sát connection pool, số request đang chờ, latency Redis và memory.

## 12. Cần hiểu tính nguyên tử khi kết hợp thao tác Redis

Các operator Reactor tạo quan hệ **phụ thuộc dữ liệu và thứ tự subscription**, không phải transaction Redis.

Ví dụ:

~~~java
Mono<String> sequence = redis.opsForValue()
    .get("stock:sku-42")
    .flatMap(raw -> {
        long stock = Long.parseLong(raw);
        long updated = stock - 1;
        return redis.opsForValue()
            .set("stock:sku-42", Long.toString(updated))
            .thenReturn("done");
    });
~~~

Hai client cùng đọc giá trị 10 có thể cùng ghi 9; kết quả bị **lost update**. `flatMap` chỉ đảm bảo lần ghi của một request phụ thuộc lần đọc của chính request đó; nó không khóa Redis key khỏi request khác.

Nếu chỉ cần giảm số đếm và Redis đã lưu giá trị số, dùng một lệnh nguyên tử:

~~~java
Mono<Long> stockAfter =
    redis.opsForValue().decrement("stock:sku-42");
~~~

Nếu cần kiểm tra không được giảm dưới 0, `DECR` đơn lẻ chưa đủ; có thể cân nhắc Lua script kiểm tra điều kiện và giảm trong cùng thao tác Redis, hoặc cơ chế concurrency khác phù hợp topology.

Tương tự:

~~~java
redis.opsForValue().set("session:42", "ACTIVE")
    .then(redis.expire("session:42", Duration.ofMinutes(30)));
~~~

Mặc dù `then` xếp hai lệnh theo thứ tự, nếu `SET` thành công nhưng connection lỗi trước `EXPIRE`, key có thể không có TTL. Với trường hợp này, ưu tiên lệnh ghi **kèm TTL**:

~~~java
Mono<Boolean> result = redis.opsForValue()
    .set("session:42", "ACTIVE", Duration.ofMinutes(30));
~~~

Mọi lệnh trong ví dụ sử dụng `ReactiveStringRedisTemplate`, nên key/value là chuỗi. Khi dùng `ReactiveRedisTemplate<K, V>` với serializer tùy biến, cần xem lại các phép ánh xạ và kiểu publisher tương ứng.

## 13. Kiểm thử operator bằng StepVerifier

`StepVerifier` là công cụ của `reactor-test` dùng đăng ký publisher và kiểm tra các tín hiệu `onNext`, `onComplete`, `onError`. Với bài học này, nên tách:

1. **Unit test về ngữ nghĩa operator** không cần Redis, dùng `Mono`/`Flux` mô phỏng publisher.
2. **Integration test** chạy Redis thật để kiểm chứng đường ghi/đọc và composition của Spring Data Redis.

### 13.1. Unit test: `map`, `flatMap`, `concatMap` và `then`

~~~java
import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import org.junit.jupiter.api.Test;

class ReactorCompositionTest {

    @Test
    void mapTransformsValue() {
        Mono<String> result = Mono.just("  Lan  ")
            .map(String::trim);

        StepVerifier.create(result)
            .expectNext("Lan")
            .verifyComplete();
    }

    @Test
    void flatMapFlattensAnotherPublisher() {
        Mono<String> result = Mono.just("42")
            .flatMap(id -> Mono.just("user:" + id));

        StepVerifier.create(result)
            .expectNext("user:42")
            .verifyComplete();
    }

    @Test
    void concatMapKeepsSourceOrder() {
        Flux<String> result = Flux.just("first", "second", "third")
            .concatMap(value ->
                Mono.just(value)
                    .delayElement(Duration.ofMillis(
                        "first".equals(value) ? 30 : 5
                    ))
            );

        StepVerifier.create(result)
            .expectNext("first", "second", "third")
            .verifyComplete();
    }

    @Test
    void thenIgnoresValueAndRunsNextPublisher() {
        Mono<String> result = Mono.just("ignored")
            .then(Mono.just("after"));

        StepVerifier.create(result)
            .expectNext("after")
            .verifyComplete();
    }

    @Test
    void flatMapSkipsMapperWhenUpstreamIsEmpty() {
        Mono<String> result = Mono.<String>empty()
            .flatMap(value -> Mono.just("should-not-run"))
            .defaultIfEmpty("fallback");

        StepVerifier.create(result)
            .expectNext("fallback")
            .verifyComplete();
    }
}
~~~

Thời gian delay trong ví dụ `concatMap` chỉ để tạo tình huống inner publisher có độ trễ khác nhau; **assertion kiểm tra thứ tự**, không đo hiệu năng mạng và không phụ thuộc vào việc `Thread.sleep` đúng tuyệt đối.

### 13.2. Integration test Spring Data Redis với Testcontainers

Ví dụ Spring Boot + Redis thật, kiểm tra một lệnh `SET` được compose với `GET` bằng `then` và dữ liệu cuối cùng:

~~~java
package com.example.redis.reactive;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Testcontainers
@SpringBootTest(classes = ReactiveRedisCompositionTest.TestApp.class)
class ReactiveRedisCompositionTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    ReactiveStringRedisTemplate redis;

    @Test
    void writeThenReadIsOrderedWithinSubscription() {
        String key = "test:reactive:" + UUID.randomUUID();

        Mono<String> workflow = redis.opsForValue()
            .set(key, "hello")
            .filter(Boolean.TRUE::equals)
            .switchIfEmpty(Mono.error(
                new IllegalStateException("SET rejected")
            ))
            .then(redis.opsForValue().get(key));

        try {
            StepVerifier.create(workflow)
                .expectNext("hello")
                .verifyComplete();
        } finally {
            // Cleanup test: subscribe để xóa key; không gọi block()
            // trong đường request reactive của production.
            StepVerifier.create(redis.delete(key))
                .expectNextCount(1)
                .verifyComplete();
        }
    }
}
~~~

Đoạn ví dụ giả định auto-configuration tạo `ReactiveStringRedisTemplate` cho cấu hình Redis test; máy chạy integration test cần Docker hoặc môi trường container tương thích. `try/finally` dọn key dù assertion thất bại. Test này chứng minh thứ tự các thao tác trong một subscription, **không chứng minh chúng tạo thành một Redis transaction**.

### 13.3. Kiểm thử trường hợp lỗi không chạy bước sau

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

AtomicBoolean secondStarted = new AtomicBoolean(false);

Mono<String> sequence = Mono.<String>error(
        new IllegalStateException("first step failed")
    )
    .then(Mono.defer(() -> {
        secondStarted.set(true);
        return Mono.just("second");
    }));

StepVerifier.create(sequence)
    .expectError(IllegalStateException.class)
    .verify();

assertThat(secondStarted.get()).isFalse();
~~~

Trong đoạn test, `assertThat` là assertion của AssertJ. `Mono.defer` cho phép quan sát chính xác rằng publisher thứ hai không được tạo/subscribe sau khi upstream phát `onError`.

## 14. Những lỗi thường gặp khi phối hợp các thao tác

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Trả ra `Mono<Mono<T>>` | Dùng `map` để tạo publisher bên trong | Dùng `flatMap` khi cần đăng ký thao tác reactive khác |
| `map`/`flatMap` không chạy | `GET` trả `Mono.empty()` | Xử lý bằng `defaultIfEmpty` hoặc `switchIfEmpty` |
| Kết quả của nhiều key bị đảo thứ tự | Dùng `Flux.flatMap` với inner publisher chạy đồng thời | Dùng `concatMap` nếu cần thực thi tuần tự; cân nhắc `flatMapSequential` nếu chỉ cần thứ tự kết quả |
| Chỉ thấy Publisher object thay vì dữ liệu Redis | Không subscribe hoặc đang log `Mono.toString()` | Trả publisher cho WebFlux hoặc dùng StepVerifier trong test |
| Ghi và đọc cùng key nhưng đọc thấy dữ liệu cũ | Dùng hai lời gọi `subscribe()` độc lập | Compose bằng `flatMap` hoặc `then` |
| Thao tác trả `false` vẫn chạy bước sau | `then` bỏ qua giá trị upstream | Kiểm tra `Boolean` bằng `flatMap`/`filter` trước `then` |
| `then` bỏ mất dữ liệu cần trả | Operator có chủ đích bỏ `onNext` | Dùng `map`/`flatMap` nếu phải giữ giá trị |
| Một lỗi làm toàn bộ `Flux` dừng | `onError` phát ra ngoài inner publisher | Đặt `onErrorResume` đúng phạm vi item nếu nghiệp vụ cho phép |
| Retry tạo thêm một lần `INCR` | Lỗi timeout sau khi Redis đã xử lý lệnh | Thiết kế idempotency và retry có kiểm soát |
| `block()` làm WebFlux chậm hoặc lỗi | Chặn thread non-blocking | Compose publisher; để WebFlux subscribe |
| `concatMap` chạy chậm hơn mong đợi | Cố ý đợi từng inner publisher hoàn tất | Chọn concurrency với `flatMap` nếu các thao tác độc lập |
| Ghép `get().flatMap(set())` nhưng vẫn có race | Các operator không tạo transaction | Dùng Redis atomic operation/script hoặc cơ chế versioning |
| `SET` rồi `EXPIRE` bằng `then` vẫn mất TTL | Hai command không nguyên tử nếu có lỗi giữa chúng | Dùng `set(key, value, Duration)` |
| Publisher được subscribe hai lần tạo hai ghi Redis | Cold publisher được thực hiện cho mỗi subscription | Thiết kế lifecycle subscription; không subscribe lặp tùy tiện |
| Flux nhiều item gây quá tải Redis | Không giới hạn concurrency và downstream buffering | Đặt concurrency, quan sát heap/connection/latency |

## 15. Nguyên tắc áp dụng trong dự án

Khi triển khai reactive Redis với Spring Data Redis:

1. **Viết service trả publisher.** Không gọi `block()` hoặc `subscribe()` thủ công trong một request reactive chỉ để lấy kết quả.
2. **Dùng `map` cho biến đổi đồng bộ nhẹ.** Với các tác vụ blocking như JDBC hoặc file I/O đồng bộ, cần lớp tích hợp và scheduler thích hợp; không biến code blocking thành non-blocking chỉ bằng `map`.
3. **Dùng `flatMap` khi thao tác sau phụ thuộc kết quả trước.** Kiểm soát trường hợp empty và error.
4. **Dùng `concatMap` khi thứ tự của các inner operation thực sự quan trọng.** Nếu chỉ cần phát kết quả theo thứ tự nhưng muốn concurrency, đánh giá `flatMapSequential` và chi phí buffer.
5. **Dùng `then` khi chỉ cần tín hiệu hoàn tất.** Nếu publisher trước trả `Boolean` hoặc một trạng thái nghiệp vụ, phải kiểm tra trước khi bỏ nó.
6. **Giới hạn mức đồng thời.** Khi duyệt nhiều key, dùng concurrency rõ ràng và không tạo hàng triệu subscription cùng lúc.
7. **Thiết kế lỗi và retry.** Không che mọi Redis error bằng giá trị mặc định; phân biệt miss, timeout và lỗi dữ liệu.
8. **Không nhầm composition với atomicity.** Thứ tự do `then`/`concatMap` tạo ra chỉ là thứ tự trong pipeline, không bảo đảm không có writer khác can thiệp và không rollback các bước đã hoàn thành.
9. **Kiểm thử các tín hiệu Reactor.** `StepVerifier` chứng minh value, empty, error, completion và thứ tự; integration test xác nhận Redis thực thi các lệnh mong đợi.

## 16. Kết luận

`map`, `flatMap`, `concatMap` và `then` là những công cụ thiết yếu để ghép các thao tác Spring Data Redis phản ứng thành một luồng rõ ràng:

- **`map`** thay đổi giá trị đã có.
- **`flatMap`** chuyển giá trị sang một publisher bất đồng bộ khác và làm phẳng kết quả.
- **`concatMap`** xử lý tuần tự những publisher được tạo từ một `Flux`, giữ thứ tự nguồn.
- **`then`** đợi hoàn tất, bỏ kết quả trước và tiếp tục một bước khác khi thành công.

Thiết kế tốt không chỉ dừng ở việc chọn đúng operator. Cần hiểu `Mono.empty()` khác lỗi, subscription kích hoạt thao tác Redis, retry có thể thực hiện lại side effect, và các operator **không tự tạo Redis transaction**. Khi các ranh giới này được giữ rõ, code reactive dễ đọc hơn, kiểm thử dễ hơn và có thể khai thác I/O không chặn mà không hy sinh tính đúng đắn của nghiệp vụ.
