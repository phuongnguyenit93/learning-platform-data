# Tạo, đọc, lưu, xóa phiên trong chuỗi `Mono`

Với Spring Session reactive, repository cung cấp các thao tác tạo, tìm, lưu và xóa session dưới dạng `Mono`. Điều này cho phép ứng dụng WebFlux kết hợp thao tác session với truy vấn reactive khác mà không chặn event-loop. Mỗi thao tác chỉ thực sự chạy khi publisher được subscribe; vì vậy, cách ghép `Mono` quyết định thứ tự thực thi, cách truyền dữ liệu và cách lỗi được xử lý.

Các API chính nằm trong `ReactiveSessionRepository<S extends Session>`:

- `createSession()` tạo session mới và trả `Mono<S>`.
- `findById(id)` tìm session theo ID và trả `Mono<S>`; nếu không có phiên hợp lệ, publisher hoàn tất rỗng.
- `save(session)` lưu trạng thái session và trả `Mono<Void>`.
- `deleteById(id)` xóa session và trả `Mono<Void>`.

Trong bài này, các thao tác được ghép bằng `flatMap`, `map`, `then`, `switchIfEmpty` và `onErrorResume`. Ví dụ dùng Redis reactive làm kho lưu trữ, nhưng cách ghép publisher cũng áp dụng cho repository reactive khác. Trong ứng dụng WebFlux thông thường, controller nên ưu tiên `WebSession`; gọi repository trực tiếp phù hợp với service hạ tầng, tác vụ quản trị, kiểm thử hoặc luồng cần kiểm soát rõ thao tác lưu trữ.

## 1. Vì sao các thao tác trả về `Mono`?

`Mono<T>` biểu diễn một kết quả bất đồng bộ có thể phát ra tối đa một phần tử kiểu `T`, hoặc hoàn tất mà không phát phần tử nào. `Mono<Void>` biểu diễn một thao tác chỉ cần báo hoàn tất hoặc lỗi, không trả dữ liệu.

| API | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `createSession()` | `Mono<S>` | Một session mới khi tạo thành công |
| `findById(id)` | `Mono<S>` | Session tìm được hoặc `Mono.empty()` |
| `save(session)` | `Mono<Void>` | Hoàn tất khi lưu xong, hoặc phát lỗi |
| `deleteById(id)` | `Mono<Void>` | Hoàn tất khi xóa xong, hoặc phát lỗi |

Các publisher thường lazy: gọi `repository.save(session)` chỉ tạo mô tả thao tác. Việc truy cập Redis được thực hiện khi publisher được subscribe, chẳng hạn khi WebFlux ghi response hoặc khi test gọi `StepVerifier`.

Vì vậy, đoạn code sau không lưu session:

```java
repository.save(session); // Tạo Mono nhưng không ai subscribe.
return Mono.just("Đã xử lý");
```

Publisher lưu session đã bị bỏ đi. Phải trả publisher đó hoặc nối nó vào chuỗi đang được trả về:

```java
return repository.save(session)
        .thenReturn("Đã lưu phiên");
```

Không gọi `subscribe()` thủ công trong service chỉ để ép thao tác chạy. Việc đó tách thao tác khỏi vòng đời request, làm caller không còn chờ kết quả và khó xử lý lỗi. Hãy để framework hoặc tầng gọi cao hơn subscribe vào publisher được trả về.

## 2. Tạo session bằng `createSession()`

`createSession()` tạo một đối tượng session mới với ID và các giá trị ban đầu do implementation cung cấp. Ở bước này, session có thể chưa được ghi xuống Redis; việc lưu bền vững được thực hiện qua `save(session)` theo hợp đồng repository.

Ví dụ tạo session chứa mã giỏ hàng:

```java
import java.time.Duration;

import org.springframework.session.ReactiveSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveSessionService<S extends Session> {
    private final ReactiveSessionRepository<S> repository;

    ReactiveSessionService(
            ReactiveSessionRepository<S> repository) {
        this.repository = repository;
    }

    Mono<String> createCheckoutSession(String cartId) {
        return repository.createSession()
                .flatMap(session -> {
                    session.setMaxInactiveInterval(Duration.ofMinutes(30));
                    session.setAttribute("checkout.cartId", cartId);
                    session.setAttribute("checkout.step", 1);
                    return repository.save(session)
                            .thenReturn(session.getId());
                });
    }
}
```

Trong ví dụ, `flatMap` nhận session được tạo, gán timeout và attribute, sau đó đợi `save` hoàn tất mới phát session ID. `thenReturn` bỏ kết quả `Void` của thao tác lưu và phát ra ID đã tạo.

Không nên trả ID cho client trước khi lưu thành công nếu client sẽ dùng ID đó để đọc session ngay. Nếu `save` thất bại, chuỗi sẽ phát lỗi và không phát ID như một kết quả thành công.

### `map` hay `flatMap`?

`map` dùng khi chuyển đổi đồng bộ một giá trị thành giá trị khác. `flatMap` dùng khi hàm chuyển đổi trả về một publisher khác và cần nối publisher đó vào chuỗi.

```java
Mono<String> id = repository.createSession()
        .map(Session::getId);
```

Đoạn trên chỉ lấy ID từ session; nó không lưu session. Khi cần lưu trước khi trả ID, dùng `flatMap`:

```java
Mono<String> id = repository.createSession()
        .flatMap(session -> repository.save(session)
                .thenReturn(session.getId()));
```

## 3. Đọc session bằng `findById()`

`findById(id)` trả về session nếu repository tìm thấy phiên còn hợp lệ. Nếu ID không tồn tại, session đã hết hạn hoặc đã bị xóa, publisher thường hoàn tất rỗng thay vì phát `null`.

```java
Mono<SessionView> findSession(String sessionId) {
    return repository.findById(sessionId)
            .map(session -> new SessionView(
                    session.getId(),
                    session.getCreationTime(),
                    session.getLastAccessedTime(),
                    session.getAttribute("checkout.cartId")));
}
```

Trong ví dụ, `map` chỉ chạy khi repository phát ra session. Nếu repository trả `Mono.empty()`, kết quả cũng là `Mono.empty()`.

Một DTO có thể định nghĩa như sau:

```java
import java.time.Instant;

record SessionView(
        String sessionId,
        Instant createdAt,
        Instant lastAccessAt,
        String cartId) {
}
```

Đây là DTO minh họa cho service nội bộ. Không nên trả session ID thực ra API công khai nếu không có nhu cầu và cơ chế bảo vệ rõ ràng; session ID là thông tin mang quyền sử dụng phiên. API cho người dùng nên trả metadata đã chọn lọc, không trả toàn bộ session attributes.

### Xử lý `Mono.empty()` bằng `switchIfEmpty`

Nếu nghiệp vụ cần báo lỗi khi không tìm thấy session, dùng `switchIfEmpty`:

```java
Mono<SessionView> findRequiredSession(String sessionId) {
    return repository.findById(sessionId)
            .switchIfEmpty(Mono.error(
                    new SessionNotFoundException("Không tìm thấy phiên")))
            .map(session -> new SessionView(
                    session.getId(),
                    session.getCreationTime(),
                    session.getLastAccessedTime(),
                    session.getAttribute("checkout.cartId")));
}
```

`switchIfEmpty` chỉ chạy nhánh thay thế khi publisher hoàn tất mà không phát phần tử. Nó không bắt lỗi kết nối Redis; lỗi được xử lý bằng các toán tử error như `onErrorResume`.

Nếu việc tạo lỗi thay thế cần tính toán lazy hoặc tốn chi phí, dùng `Mono.defer(...)` để chỉ tạo publisher khi nhánh đó thực sự được chọn.

## 4. Cập nhật và lưu session bằng `save()`

Khi đã tải được session, có thể thay đổi attribute rồi gọi `save(session)`. Repository lưu trạng thái mới theo semantics của implementation.

```java
Mono<Void> updateCheckoutStep(String sessionId, int nextStep) {
    return repository.findById(sessionId)
            .switchIfEmpty(Mono.error(
                    new SessionNotFoundException("Phiên không còn tồn tại")))
            .flatMap(session -> {
                session.setAttribute("checkout.step", nextStep);
                return repository.save(session);
            });
}
```

Chuỗi xử lý gồm ba bước:

1. `findById` tải session.
2. `flatMap` cập nhật attribute khi đã có session.
3. `save` được subscribe như một phần của publisher trả về; `Mono<Void>` chỉ hoàn tất sau khi thao tác lưu kết thúc.

Không dùng `map` để trả về `repository.save(session)` vì khi đó kết quả sẽ là `Mono<Mono<Void>>`, tức publisher lồng nhau. Dùng `flatMap` để làm phẳng publisher.

### Lưu attribute và object mutable

Nếu attribute là object mutable, cần hiểu repository và save mode phát hiện thay đổi như thế nào. Ví dụ:

```java
CartState cart = session.getAttribute("cart");
cart.addItem(productId);
session.setAttribute("cart", cart);
return repository.save(session);
```

Việc đặt lại attribute sau khi sửa object giúp thể hiện rõ thay đổi với các cơ chế theo dõi thao tác set attribute. Tốt hơn nữa, giữ session nhỏ: lưu `cartId` trong session và lưu chi tiết giỏ hàng trong database nghiệp vụ.

## 5. Xóa session bằng `deleteById()`

`deleteById(id)` xóa session theo ID ở tầng repository và trả `Mono<Void>`. Không có phần tử kết quả để ánh xạ; caller quan tâm đến việc thao tác hoàn tất hay phát lỗi.

```java
Mono<Void> deleteSession(String sessionId) {
    return repository.deleteById(sessionId);
}
```

Có thể nối hành động sau khi xóa thành công bằng `then`:

```java
Mono<String> deleteAndConfirm(String sessionId) {
    return repository.deleteById(sessionId)
            .thenReturn("Đã gửi thao tác xóa phiên");
}
```

Thông điệp xác nhận chỉ nên được phát sau khi publisher xóa hoàn tất. Nếu Redis lỗi, publisher phát lỗi và `thenReturn` không chạy.

`deleteById` là thao tác ở tầng repository. Nếu đang xử lý request WebFlux và muốn kết thúc session hiện tại cùng lúc hết hạn cookie/header, hãy dùng `WebSession.invalidate()` để `WebSessionManager` và `WebSessionIdResolver` xử lý cả trạng thái server lẫn định danh client. Xóa trực tiếp repository không tự xóa cookie trong response.

## 6. Ghép nhiều thao tác theo đúng thứ tự

Reactive chain giúp mô tả thứ tự bất đồng bộ mà không chặn thread. Ví dụ, tạo session, lưu, rồi đọc lại:

```java
Mono<SessionView> createThenRead(String cartId) {
    return repository.createSession()
            .flatMap(session -> {
                session.setAttribute("checkout.cartId", cartId);
                return repository.save(session)
                        .then(repository.findById(session.getId()));
            })
            .map(session -> new SessionView(
                    session.getId(),
                    session.getCreationTime(),
                    session.getLastAccessedTime(),
                    session.getAttribute("checkout.cartId")));
}
```

`then(...)` chờ thao tác trước hoàn tất rồi mới subscribe publisher tiếp theo. Nếu `save` lỗi, `findById` không chạy. Nếu `findById` hoàn tất rỗng, cả chuỗi cũng rỗng.

Một số toán tử thường dùng:

| Toán tử | Dùng khi |
|---|---|
| `map` | Chuyển một giá trị đồng bộ |
| `flatMap` | Chuyển giá trị thành publisher và nối publisher đó |
| `then(next)` | Bỏ giá trị trước, đợi hoàn tất rồi chạy publisher kế tiếp |
| `thenReturn(value)` | Bỏ giá trị trước, sau khi hoàn tất phát một giá trị cố định |
| `switchIfEmpty(alternative)` | Dùng publisher thay thế khi không có phần tử |
| `defaultIfEmpty(value)` | Cung cấp giá trị mặc định khi publisher rỗng |
| `onErrorResume(...)` | Chuyển lỗi thành publisher thay thế |
| `doOnNext(...)` | Quan sát phần tử bằng side effect đồng bộ ngắn |
| `doOnError(...)` | Quan sát lỗi, ví dụ ghi metric |
| `doFinally(...)` | Quan sát kết thúc do complete, error hoặc cancel |

Không dùng `then` nếu cần giữ giá trị session để thao tác tiếp; dùng `flatMap` hoặc lưu giá trị trong lambda. Không dùng `map` cho một hàm trả `Mono`.

## 7. Xử lý lỗi Redis trong chuỗi `Mono`

Lỗi kết nối, timeout, xác thực Redis hoặc lỗi serialization sẽ đi theo nhánh error của publisher. Nếu không xử lý tại chỗ, lỗi truyền lên controller hoặc global error handler của WebFlux.

Có thể quan sát lỗi và giữ nguyên việc truyền lỗi:

```java
Mono<Void> saveWithMetrics(Session session) {
    return repository.save(session)
            .doOnError(error -> metrics.counter("session.save.failure").increment());
}
```

`doOnError` chỉ quan sát lỗi; nó không chuyển lỗi thành thành công. Nếu muốn chuyển một lỗi hạ tầng thành lỗi nghiệp vụ, có thể dùng `onErrorMap` hoặc `onErrorResume` có chọn lọc.

```java
Mono<SessionView> loadSession(String sessionId) {
    return repository.findById(sessionId)
            .map(this::toView)
            .onErrorMap(RedisConnectionFailureException.class,
                    error -> new SessionStoreUnavailableException(
                            "Kho session tạm thời không khả dụng", error));
}
```

Không nên biến mọi lỗi Redis thành `Mono.empty()`. Làm vậy khiến ứng dụng nhầm lỗi hạ tầng với session không tồn tại, có thể tạo session mới và làm mất ngữ cảnh đăng nhập mà không có thông báo phù hợp.

### Retry có chọn lọc

Có thể retry lỗi tạm thời nếu thao tác an toàn để lặp và chính sách retry có giới hạn:

```java
Mono<Void> saveWithRetry(Session session) {
    return repository.save(session)
            .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                    .maxBackoff(Duration.ofSeconds(1)));
}
```

Đây là ví dụ minh họa; cần import và cấu hình `Retry` theo Reactor đang dùng. Không retry vô hạn. Retry làm tăng tải trong lúc Redis đang lỗi và có thể khuếch đại sự cố. Đánh giá timeout tổng, backoff, jitter, circuit breaker và số lần thử phù hợp.

Với `save`, cần xem xét khả năng lặp an toàn của repository và serialization. Với một chuỗi gồm nhiều thao tác, retry toàn bộ chuỗi có thể tạo session mới lần nữa nếu lần trước đã ghi thành công nhưng response bị mất. Đặt ranh giới retry đúng thao tác và dùng ID/khóa idempotency khi nghiệp vụ cần tránh tạo trùng.

## 8. Tạo session có điều kiện và tránh tạo trùng

Một luồng có thể đọc session theo ID và tạo phiên mới nếu không tìm thấy. Dùng `switchIfEmpty`:

```java
Mono<String> getOrCreate(String sessionId) {
    return repository.findById(sessionId)
            .map(Session::getId)
            .switchIfEmpty(Mono.defer(() ->
                    repository.createSession()
                            .flatMap(session -> repository.save(session)
                                    .thenReturn(session.getId()))));
}
```

`Mono.defer` bảo đảm thao tác tạo chỉ được khởi tạo khi nhánh `findById` rỗng. Nếu đặt `repository.createSession()` trực tiếp vào biểu thức được tạo sớm, publisher vẫn lazy, nhưng `defer` làm rõ ranh giới và hữu ích khi việc tạo publisher có side effect hoặc tính toán cần thực hiện đúng lúc subscribe.

Tuy nhiên, `getOrCreate` không phải thao tác nguyên tử. Hai request đồng thời có thể cùng không tìm thấy ID rồi cùng tạo session mới. Nếu nghiệp vụ cần duy nhất một session cho một khóa, cần cơ chế đồng bộ hoặc unique constraint/atomic operation ở kho dữ liệu. Không giả định một chuỗi `Mono` tự bảo đảm tính nguyên tử giữa nhiều request hoặc nhiều instance.

## 9. Phân biệt `Mono.empty()`, `Mono<Void>` và lỗi

Ba trạng thái này có ý nghĩa khác nhau:

| Trạng thái | Ví dụ | Cách hiểu |
|---|---|---|
| Có phần tử | `Mono<Session>` phát session | Đã tìm thấy hoặc tạo được session |
| Rỗng | `findById` trả `Mono.empty()` | Không có session tương ứng |
| Hoàn tất không giá trị | `save`/`deleteById` trả `Mono<Void>` | Thao tác hoàn tất thành công |
| Error | Redis timeout hoặc deserialize lỗi | Thao tác không hoàn tất bình thường |

`Mono<Void>` thường không phát phần tử nhưng vẫn có thể hoàn tất thành công. Vì vậy, không dùng `switchIfEmpty` sau `save()` để kết luận lưu thất bại; publisher `Void` hoàn tất thành công mà không phát giá trị là hành vi bình thường.

Ví dụ đúng:

```java
return repository.save(session)
        .then(Mono.just("saved"));
```

Ví dụ sai về ý nghĩa:

```java
return repository.save(session)
        .switchIfEmpty(Mono.error(new IllegalStateException("Save failed")));
```

`switchIfEmpty` không phải cách phát hiện lỗi của thao tác `save`; lỗi thực sự được truyền qua error signal.

## 10. Không chặn bằng `block()` hoặc `subscribe()` thủ công

Trong WebFlux, không dùng `block()` để lấy session đồng bộ:

```java
// Không làm như vậy trong controller/service reactive.
Session session = repository.findById(sessionId).block();
```

`block()` chờ thread hiện tại và có thể chặn event-loop, làm giảm khả năng xử lý đồng thời hoặc gây lỗi khi gọi trên thread không cho phép blocking. Thay vào đó, tiếp tục chuỗi:

```java
return repository.findById(sessionId)
        .map(this::toView);
```

Tương tự, không làm:

```java
repository.deleteById(sessionId).subscribe();
return Mono.just("Đã đăng xuất");
```

Cách này trả response trước khi xóa hoàn tất và tách lỗi khỏi request. Hãy nối thao tác:

```java
return repository.deleteById(sessionId)
        .thenReturn("Đã đăng xuất");
```

Với logout dựa trên `WebSession`, dùng `session.invalidate()` và trả `Mono<Void>` đó cho WebFlux/Spring Security để cookie hoặc header ID được xử lý cùng vòng đời session.

## 11. Tác động đến cookie và `WebSession`

Repository chỉ biết session ID và dữ liệu lưu trữ. Nó không trực tiếp phát hành hay hết hạn cookie. Trong ứng dụng WebFlux, `WebSessionManager` và `WebSessionIdResolver` quản lý việc trao đổi ID với client.

Vì vậy:

- Tạo session trực tiếp bằng `ReactiveSessionRepository` không tự phát `Set-Cookie`.
- `deleteById(id)` xóa dữ liệu server nhưng không tự xóa cookie đang nằm trong trình duyệt.
- `WebSession.invalidate()` là thao tác ở tầng web session; manager/resolver có thể hết hạn ID phía client trong response.
- Nếu dùng header resolver, client phải ngừng gửi header ID cũ khi logout.

Nếu service quản trị xóa session của một thiết bị khác, trình duyệt thiết bị đó có thể vẫn giữ cookie. Request sau gửi ID cũ sẽ không tìm được session trong repository và phải được xử lý như chưa có phiên hợp lệ. Không ghi session ID đầy đủ vào log hoặc gửi ID của người dùng khác ra giao diện quản trị.

## 12. Đồng thời và thứ tự cập nhật

Mỗi `Mono` mô tả một chuỗi thao tác, nhưng không tự biến nhiều request thành một giao dịch. Hai request dùng cùng session có thể tải hai bản snapshot, sửa attribute và lưu theo thứ tự khác nhau.

Ví dụ, request A đọc `counter = 4`, request B cũng đọc `counter = 4`; A ghi 5 và B ghi 5. Kết quả cuối là 5 thay vì 6. Đây là lost update. Cách xử lý tùy yêu cầu:

- Tránh dùng session cho bộ đếm hoặc dữ liệu nghiệp vụ cần cập nhật nguyên tử.
- Lưu dữ liệu chuẩn trong database có transaction/optimistic locking.
- Dùng atomic operation của kho dữ liệu nếu phù hợp và có thể bảo đảm semantics.
- Giữ thao tác session đơn giản, ít cập nhật và attribute nhỏ.
- Kiểm thử request đồng thời, logout cùng lúc với update và request đến nhiều instance.

Nếu một request đã tải session trước khi request khác xóa nó, request đang chạy vẫn có thể giữ bản session trong bộ nhớ. Xóa repository không hủy request đang thực thi. Với thao tác nhạy cảm, cần kiểm tra trạng thái quyền tại thời điểm thực hiện nghiệp vụ.

## 13. Kiểm thử chuỗi `Mono` bằng StepVerifier

Reactor `StepVerifier` cho phép kiểm tra publisher mà không cần gọi `block()` trong code ứng dụng. Có thể kiểm tra các trường hợp tạo, đọc, lưu và xóa bằng repository test hoặc Redis Testcontainer.

Ví dụ kiểm thử thứ tự tạo và lưu:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class ReactiveSessionServiceTest {

    @Test
    void createsAndPersistsSession() {
        StepVerifier.create(service.createCheckoutSession("cart-2048"))
                .assertNext(id -> assertThat(id).isNotBlank())
                .verifyComplete();
    }
}
```

Đoạn mã giả định `service` đã được cấu hình với repository test. `assertNext` xác nhận publisher phát ID; `verifyComplete` xác nhận chuỗi hoàn tất. Nếu `save` phát lỗi, test sẽ thất bại thay vì nhận ID thành công.

Các tình huống nên kiểm thử:

1. `createSession` tạo ID mới và `save` hoàn tất trước khi ID được trả về.
2. `findById` tìm được session đã lưu.
3. `findById` với ID không tồn tại trả `Mono.empty()` hoặc lỗi nghiệp vụ theo service contract.
4. Cập nhật attribute rồi lưu; request sau đọc được giá trị mới.
5. `deleteById` hoàn tất và lần đọc sau không tìm thấy session.
6. Lỗi Redis được truyền lên hoặc chuyển đổi theo chính sách đã định.
7. Retry có giới hạn và không tạo session trùng ngoài dự kiến.
8. Publisher không bị bỏ quên hoặc subscribe thủ công ngoài luồng.
9. Nhiều request cùng session không làm mất cập nhật quan trọng.

Với Redis thật, dùng database/namespace riêng cho test. Không chạy `FLUSHDB` hoặc `FLUSHALL` trên Redis dùng chung. Kiểm thử timeout nên chờ theo điều kiện và có thời gian chờ hợp lý, vì expiration không nhất thiết được xử lý đúng mili giây TTL về 0.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Session không được lưu | Tạo `Mono` từ `save` nhưng không trả/nối publisher | Trả `Mono<Void>` hoặc dùng `then`/`flatMap` |
| `Mono<Mono<Void>>` | Dùng `map` cho hàm trả publisher | Đổi sang `flatMap` |
| Không tìm thấy session bị biến thành lỗi Redis | Dùng sai nhánh `switchIfEmpty` hoặc bắt lỗi quá rộng | Tách rõ empty và error signal |
| Save bị coi là rỗng nên báo lỗi | Áp dụng `switchIfEmpty` lên `Mono<Void>` | Dùng `then` để xác nhận hoàn tất |
| Logout trả response trước khi xóa xong | Gọi `subscribe()` thủ công rồi trả response | Nối delete/invalidate vào publisher trả về |
| Request bị nghẽn | Gọi `block()` hoặc dùng JDBC blocking trên event-loop | Dùng reactive chain và client reactive |
| Redis lỗi nhưng app tạo session mới | `onErrorResume` đổi mọi lỗi thành empty | Chỉ fallback cho lỗi được xác định rõ |
| Session bị ghi đè khi nhiều request | Read-modify-save không nguyên tử | Đưa dữ liệu quan trọng ra kho có concurrency control |
| Cookie còn sau `deleteById` | Repository không quản lý response cookie | Dùng `WebSession.invalidate()` cho request hiện tại hoặc xử lý resolver/client riêng |

## 15. Checklist xây dựng service reactive session

- Inject `ReactiveSessionRepository` đúng implementation và kiểu session.
- Tạo session bằng `createSession()`, đặt timeout và attribute trước khi lưu.
- Nối `save()` vào publisher và chỉ phát kết quả sau khi lưu hoàn tất.
- Dùng `findById()` và xử lý `Mono.empty()` riêng với error signal.
- Dùng `flatMap` khi bước tiếp theo trả publisher; dùng `map` cho chuyển đổi đồng bộ.
- Dùng `then`/`thenReturn` với thao tác `Mono<Void>`.
- Dùng `deleteById()` cho xóa ở tầng repository; dùng `WebSession.invalidate()` khi cần xử lý cả client ID.
- Không gọi `block()` hoặc `subscribe()` thủ công trong đường xử lý request.
- Xử lý timeout, retry, backoff và lỗi Redis có giới hạn, không che lỗi hạ tầng thành session không tồn tại.
- Kiểm thử empty, error, create/read/save/delete, concurrency và nhiều instance bằng `StepVerifier` cùng integration test.

Trong Spring Session reactive, tạo, đọc, lưu và xóa session đều là các thao tác bất đồng bộ. Ghép chúng đúng bằng `map`, `flatMap`, `then` và `switchIfEmpty` giúp giữ thứ tự và truyền lỗi nhất quán mà không chặn event-loop. Phân biệt rõ `Mono.empty()`, `Mono<Void>` và error signal, đồng thời để publisher được subscribe trong đúng vòng đời request, là nền tảng để quản lý session Redis ổn định trong ứng dụng WebFlux.
