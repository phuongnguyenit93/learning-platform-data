# `using` và `usingWhen` cho vòng đời tài nguyên trong Project Reactor / Spring WebFlux

## 1. Tại sao vòng đời tài nguyên lại quan trọng trong reactive?

Một publisher có thể chưa được subscribe ngay lúc phương thức Java trả về; khi đã subscribe, nó có thể **hoàn tất**, **phát lỗi**, hoặc bị **hủy trước khi xong**. Nếu code mở file, tạo connection, lấy lock, đăng ký listener hoặc giữ một session mà chỉ đóng trong nhánh thành công, tài nguyên có thể rò rỉ khi request bị hủy, timeout hay upstream thất bại.

Trong lập trình mệnh lệnh, `try/finally` hoặc `try-with-resources` bao trọn thời gian chạy công việc:

```java
try (SomeResource resource = openResource()) {
    return useResource(resource);
}
```

Trong reactive, việc trả về `Mono`/`Flux` **không đồng nghĩa công việc đã chạy xong**. Nếu đóng tài nguyên trước khi subscribe thì nguồn reactive có thể sử dụng một tài nguyên đã bị đóng. Project Reactor có các factory chuyên dụng để quản lý tài nguyên **theo từng subscription**:

- **`Mono.using` / `Flux.using`**: lấy tài nguyên bằng `Callable`, dùng nó để tạo publisher, thực hiện **cleanup đồng bộ** (callback `Consumer<D>` hoặc `AutoCloseable.close()`).
- **`Mono.usingWhen` / `Flux.usingWhen`**: lấy tài nguyên từ một **Publisher<D>**, tạo publisher sử dụng tài nguyên, thực hiện **cleanup qua Publisher bất đồng bộ**, có thể tách riêng nhánh thành công, lỗi và hủy.

Đây là chủ đề thuộc nhóm **Hủy và tài nguyên**. Trọng tâm không chỉ là “có gọi close hay không” mà còn là **lúc nào close diễn ra**, **downstream nhận tín hiệu gì**, **hủy subscription có chạy cleanup hay không**, **xử lý lỗi cleanup thế nào** và **chọn đúng API cho connection/transaction**.

### Mục tiêu

Sau bài này, bạn có thể:

1. Mô tả chính xác acquire → use → release trên ba đường `onComplete`, `onError`, `cancel`.
2. Phân biệt cleanup đồng bộ của `using` và cleanup theo publisher của `usingWhen`.
3. Hiểu `eager` / non-eager khi dùng `using`, đặc biệt sự khác nhau giữa `Mono` có giá trị và `Flux` nhiều phần tử.
4. Hiểu vì sao `Mono.usingWhen` phải **chờ cleanup xong trước khi phát giá trị**, trong khi `Flux.usingWhen` có thể chuyển `onNext` trong quá trình stream rồi mới đợi cleanup ở terminal.
5. Viết kiểm thử với `StepVerifier` cho thành công, lỗi, cancellation và cleanup thất bại.
6. Áp dụng chính xác vào WebFlux và nhận biết khi nên dùng cơ chế transaction/resource management có sẵn của Spring.

## 2. Mô hình tín hiệu: cleanup là một phần của subscription

Giả sử publisher dùng một connection:

```text
subscribe
   |
   v
acquire resource
   |
   v
resourceClosure(resource) -> publisher công việc
   |
   +---- onNext ... -> onComplete ----> complete cleanup
   |
   +---- onNext ... -> onError(e) ----> error cleanup
   |
   +---- subscriber.cancel() --------> cancel cleanup
```

Ba đường này khác nhau:

- **Hoàn tất (`onComplete`)**: tác vụ kết thúc bình thường, có thể đã phát 0, 1 hoặc nhiều phần tử.
- **Lỗi (`onError`)**: tác vụ kết thúc thất bại; cleanup phải được thực hiện mà không đánh mất bối cảnh lỗi gốc.
- **Hủy (`cancel`)**: subscriber không còn yêu cầu dữ liệu, chẳng hạn client HTTP ngắt kết nối, `take(n)` đã đủ phần tử hoặc timeout hủy upstream. **Cancel không phải `onComplete` và không phải `onError` gửi cho subscriber.**

`using` và `usingWhen` quản lý phần tài nguyên mà **operator trực tiếp sở hữu**. Chúng không thể bảo đảm lập tức dừng tác vụ vật lý phía ngoài nếu driver/SDK không tôn trọng cancellation. Vì vậy cần timeout và cấu hình driver phù hợp.

### Tại sao không chỉ dùng `doFinally`?

`doFinally` quan sát lúc sequence kết thúc qua `SignalType.ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`, rất hữu ích để ghi metrics, nhưng callback của nó là **đồng bộ**, không phải một cơ chế chờ publisher cleanup bất đồng bộ trước khi công bố terminal. Nếu `close()` cần trả về `Mono<Void>` hoặc transaction phải commit/rollback qua async I/O, `usingWhen` phù hợp hơn.

Bên cạnh đó, `doFinally` đặt sai vị trí có thể không bao trọn thao tác tạo tài nguyên hay không cô lập mỗi subscription. `using`/`usingWhen` ràng buộc **acquire, use, cleanup** thành một cấu trúc rõ ràng.

## 3. Bảng so sánh `using` và `usingWhen`

| Đặc tính | `using` | `usingWhen` |
|---|---|---|
| Cách cấp tài nguyên | `Callable<? extends D>` | `Publisher<D>` |
| Cách tạo công việc | Hàm từ resource → `Mono`/`Publisher` | Hàm từ resource → `Mono`/`Publisher` |
| Cleanup | `Consumer<D>` đồng bộ hoặc `AutoCloseable.close()` | Một `Publisher<?>` được subscribe để cleanup |
| Chờ async cleanup? | Không; callback chạy đồng bộ | Có; terminal thường được trì hoãn cho đến khi cleanup kết thúc |
| Tách nhánh complete/error/cancel? | Callback dọn dẹp chung | Có overload 5 tham số tách ba nhánh |
| Phù hợp | `close()` đồng bộ, file handle, buffer/lock dùng đồng bộ | R2DBC connection, commit/rollback, close trả `Publisher` |
| Có cleanup khi cancel? | Có, sau khi resource được cấp thành công | Có khi resource đã được cấp, qua nhánh cancel cleanup |
| Một resource cho nhiều subscriber? | Tạo **mới theo từng subscription** qua callable | Publisher cung cấp resource được subscribe **theo từng subscription** |
| Eager/non-eager | Có cờ `eager` ở overload tương ứng | Không dùng cờ `eager`; phụ thuộc publisher cleanup |

**Không dùng `.block()` bên trong callback cleanup async chỉ để ép `using`.** Điều này biến một thao tác I/O bất đồng bộ thành blocking, có thể làm nghẽn event loop WebFlux. Chọn `usingWhen` để Reactor subscribe và phối hợp cleanup theo tín hiệu.

## 4. `using`: nguồn tài nguyên đồng bộ, cleanup đồng bộ

Chữ ký điển hình (các kiểu rút gọn để dễ đọc):

```java
Flux.using(
    Callable<D> resourceSupplier,
    Function<D, Publisher<T>> sourceSupplier,
    Consumer<D> resourceCleanup,
    boolean eager
);

Mono.using(
    Callable<D> resourceSupplier,
    Function<D, Mono<T>> sourceSupplier,
    Consumer<D> resourceCleanup,
    boolean eager
);
```

Trong API thực, các generic dùng wildcard để chấp nhận subtype. Reactor cũng có overload không cần `eager` và overload dành cho resource `AutoCloseable` để gọi `close()` tự động. Khi muốn kiểm soát chính xác thứ tự, hãy chỉ định `eager` tường minh.

Ví dụ một tài nguyên quản lý cache snapshot đồng bộ:

```java
Mono<String> snapshot = Mono.using(
        () -> openSnapshot(),                  // acquire lúc subscribe
        resource -> Mono.fromSupplier(
                () -> resource.readValue()),   // use khi thực thi
        resource -> resource.close(),          // release đồng bộ
        true                                   // eager cleanup
);
```

Đây là **snippet minh họa**, yêu cầu `openSnapshot()`, `readValue()` và `close()` đồng bộ được định nghĩa trong ứng dụng. Publisher tạo ra là **cold**: mỗi subscription sẽ chạy supplier để lấy resource riêng; chưa gọi `openSnapshot()` chỉ vì tạo biến `snapshot`.

Vòng đời tương ứng:

```text
Tạo biến Mono             : chưa acquire
Subscriber đăng ký        : acquire
Nguồn bên trong thực thi  : use
Nguồn hoàn tất / lỗi      : cleanup
Gửi terminal downstream   : tùy eager
```

### `eager=true` và `eager=false` nghĩa là gì?

Với `eager=true`, cleanup chạy **trước khi chuyển terminal thành công/lỗi xuống downstream**. Với `eager=false`, cleanup thường xảy ra **sau terminal** và lỗi cleanup ở đường non-eager không thể thay đổi terminal đã gửi; Reactor báo/drop lỗi theo chính sách tương ứng.

Sự khác biệt đáng chú ý giữa `Mono` và `Flux`:

- `Mono.using(..., eager=true)` có **một giá trị tối đa**. Nếu nguồn có giá trị, cleanup eager diễn ra **trước cả `onNext(value)`** gửi xuống downstream; nếu cleanup thất bại, giá trị đó có thể bị bỏ và downstream nhận lỗi cleanup.
- `Flux.using(..., eager=true)` có thể **đã phát nhiều `onNext`** trong lúc resource còn mở; cleanup diễn ra trước **terminal**, không thể thu hồi các `onNext` đã phát.
- `eager=false` không phải “không cần cleanup”. Nó vẫn thực hiện cleanup, nhưng không đồng bộ nó với terminal theo cùng cách eager.

Ví dụ quan sát thứ tự `Mono`:

```java
Mono<String> one = Mono.using(
        () -> new Handle(),
        handle -> Mono.fromSupplier(handle::read),
        Handle::close,
        true
);
```

Ở đây `Handle` là **class minh họa**, không phải API Reactor. Nếu downstream nhận `"abc"`, cleanup eager đã được thực hiện thành công trước khi giá trị được chuyển xuống; cách này hữu ích khi `close` có thể làm thay đổi quyết định cuối cùng về thành công/thất bại.

### Dùng `AutoCloseable` khi thích hợp

Với kiểu triển khai `AutoCloseable`, có thể dùng overload:

```java
Mono<String> result = Mono.using(
        () -> new MyAutoCloseableResource(),
        resource -> Mono.just(resource.read()),
        true
);
```

Overload này sẽ gọi `close()` từ `AutoCloseable`. Đoạn mã chỉ minh họa: phải định nghĩa `MyAutoCloseableResource`. Chú ý biểu thức `resource.read()` trong mapper được gọi khi source supplier chạy sau acquire; nếu thao tác đọc blocking, hãy bảo đảm toàn bộ subscription chạy trên scheduler thích hợp.

**Không tự tạo resource ở ngoài `using` để dùng lại bừa bãi**:

```java
// Sai nếu nhiều subscription dùng chung một handle không được phép tái sử dụng:
MyAutoCloseableResource handle = new MyAutoCloseableResource();
Mono<String> wrong = Mono.using(
        () -> handle,
        h -> Mono.just(h.read()),
        true
);
```

Subscription thứ nhất có thể đóng `handle`; subscription thứ hai nhận lại tài nguyên đã đóng. Nếu muốn mỗi subscriber có resource riêng, factory **phải tạo resource bên trong callable**.

## 5. `usingWhen`: cấp và giải phóng tài nguyên bằng Publisher

`usingWhen` là lựa chọn khi acquire hoặc cleanup thực hiện bằng Publisher không thể gọi đồng bộ an toàn. Hai dạng đáng nhớ:

```java
Flux.usingWhen(
    Publisher<D> resourceSupplier,
    Function<D, Publisher<T>> resourceClosure,
    Function<D, Publisher<?>> asyncCleanup
);
```

Và dạng phân biệt ba kết thúc:

```java
Flux.usingWhen(
    Publisher<D> resourceSupplier,
    Function<D, Publisher<T>> resourceClosure,
    Function<D, Publisher<?>> asyncComplete,
    BiFunction<D, Throwable, Publisher<?>> asyncError,
    Function<D, Publisher<?>> asyncCancel
);
```

`Mono.usingWhen` cũng có hai dạng tương ứng, nhưng `resourceClosure` trả `Mono<? extends T>`. Mã signature trên là **sơ đồ loại tham số**, wildcard cụ thể xem Javadoc ở cuối bài.

Ví dụ đơn giản với một connection reactive:

```java
Mono<String> loaded = Mono.usingWhen(
        acquireConnection(),                  // Mono<Connection>
        connection -> connection.fetchName(), // Mono<String>
        connection -> connection.closeAsync() // Mono<Void>
);
```

Đoạn này là **snippet giả định**: `acquireConnection`, `Connection.fetchName` và `closeAsync` đại diện API dự án, không phải tên method chung của R2DBC hay Spring. Điều cần hiểu là cleanup trả `Mono<Void>` và Reactor **subscribe nó**, không cần tự `.subscribe()` hay `.block()`.

### Vì sao cleanup phải là Publisher?

Một connection pool/reactive transaction có thể cần I/O để trả connection, flush, commit hoặc rollback. Nếu dùng:

```java
resource -> {
    resource.closeAsync();    // chỉ tạo Mono, chưa subscribe
}
```

thì bạn **không** hoàn tất cleanup chỉ bằng việc tạo publisher. `usingWhen` mong callback **trả về** publisher để nó có thể subscribe và đợi terminal.

Đúng về hình thức:

```java
resource -> resource.closeAsync()
```

Nếu callback có nhiều việc, dùng composition `.then(...)`, `onErrorResume(...)` hoặc `Mono.defer(...)` theo chính sách, nhưng phải trả publisher đúng ngữ nghĩa. Đừng nuốt lỗi cleanup một cách vô ý.

## 6. Phân nhánh `asyncComplete`, `asyncError`, `asyncCancel`

Overload 5 tham số dùng khi cleanup phụ thuộc vào nguyên nhân kết thúc:

```java
Flux<String> flow = Flux.usingWhen(
        openSession(),                       // Publisher<Session>
        session -> session.stream(),         // Publisher<String>
        session -> session.commit(),         // complete -> commit
        (session, error) -> session.rollback(), // error -> rollback
        session -> session.rollback()        // cancel -> rollback
);
```

Đây là **snippet thiết kế** với `Session` giả định. Nó chỉ biểu thị ý nghĩa của ba nhánh; ở hệ thống thật cần thêm giải phóng/đóng session theo hợp đồng API (ví dụ trong các publisher `commit/rollback` hoặc dùng `then(closeAsync())`). Không thể coi một lệnh commit/rollback đơn thuần chắc chắn đã trả connection về pool.

Tình huống:

| Sự kiện từ `resourceClosure` | Callback cleanup được chọn | Kết quả nếu cleanup hoàn tất thành công |
|---|---|---|
| `onComplete` (có hoặc không có phần tử) | `asyncComplete(resource)` | Downstream nhận terminal thành công |
| `onError(originalError)` | `asyncError(resource, originalError)` | Downstream nhận lỗi gốc |
| Subscriber `cancel()` | `asyncCancel(resource)` | Cleanup được kích hoạt; không gửi `onComplete`/`onError` mới cho subscriber đã hủy |

**Không đánh đồng cancel với success.** Một streaming transaction bị khách hàng ngắt giữa chừng thường không thể tự động coi là commit hợp lệ. Với các API có transaction, cancel có thể cần rollback. Quyết định cụ thể thuộc nghiệp vụ và hợp đồng driver.

Reactor cho phép `asyncCancel` bằng `null` ở overload tương ứng để dùng nhánh `asyncComplete` khi cancel, nhưng đó không phải là lựa chọn an toàn mặc định cho transaction: nếu cần rollback khi hủy, hãy cung cấp callback cancel riêng.

### Một cleanup chung có đủ không?

Dạng 3 tham số:

```java
Flux.usingWhen(
        acquire(),
        resource -> work(resource),
        resource -> release(resource)
);
```

sử dụng cùng callback cleanup cho complete, error và cancel. Phù hợp khi mọi đường đều chỉ cần `close`/`release` cùng một cách. Dùng dạng 5 tham số khi success cần commit còn error/cancel cần rollback hoặc các đường có metric/release khác nhau.

## 7. Tín hiệu downstream khi cleanup bất đồng bộ

Đây là điểm khác biệt dễ dẫn đến bug nếu chỉ so sánh hai API bằng tên.

### `Mono.usingWhen`: đợi cleanup trước khi phát kết quả

Nếu resource closure là một `Mono<String>` phát `"OK"`, Reactor không thể gửi `"OK"` xuống downstream rồi sau đó bảo rằng cleanup thất bại mà vẫn giữ hợp đồng Mono thành công. Vì vậy `Mono.usingWhen` **hoãn cả tín hiệu thành công có giá trị** tới khi cleanup kết thúc.

```text
t=0:    acquire resource
t=1:    use -> kết quả nội bộ "OK"
t=2:    bắt đầu async cleanup
t=5:    async cleanup hoàn tất
t=5:    downstream nhận onNext("OK"), onComplete()
```

Nếu cleanup thất bại ở `t=5`, downstream nhận `onError(cleanupFailure)` thay vì `"OK"`. Giá trị nội bộ đã tạo có thể bị discard.

Đối với `Mono.empty()`, downstream cũng chờ cleanup rồi mới nhận `onComplete`; đối với `Mono.error(original)`, cleanup chạy rồi downstream nhận lỗi gốc nếu cleanup thành công.

### `Flux.usingWhen`: có thể stream phần tử trước cleanup

Một `Flux` có thể phát nhiều phần tử trong lúc resource còn mở:

```text
acquire -> onNext(A) -> onNext(B) -> source onComplete
                                                |
                                                v
                                         async cleanup
                                                |
                                                v
                                      downstream onComplete
```

Với `Flux.usingWhen`, các phần tử `A`, `B` **có thể đã đến downstream** trước khi cleanup bắt đầu. Nếu cleanup cuối cùng lỗi, downstream nhận `onError(cleanupFailure)` thay cho terminal success; **A và B đã nhận không bị thu hồi**.

Do đó, không hứa “cả Flux sẽ không hiện dữ liệu cho đến khi commit xong”. Nếu nghiệp vụ cần **chỉ công bố dữ liệu sau commit**, thiết kế một Mono/buffer/transaction boundary thích hợp; streaming và cam kết atomic visibility là hai yêu cầu khác nhau.

### Bảng tín hiệu quan sát được

| `resourceClosure` | Cleanup | `Mono.usingWhen` | `Flux.usingWhen` |
|---|---|---|---|
| Thành công có giá trị | Hoàn tất | Giá trị → complete, sau cleanup | Có thể nhiều giá trị trước cleanup; complete sau cleanup |
| Empty completion | Hoàn tất | Complete sau cleanup | Complete sau cleanup |
| Thành công | Lỗi | Chỉ error cleanup, giá trị Mono bị bỏ | Có thể đã nhận một số `onNext`; terminal error cleanup |
| Error gốc | Hoàn tất | Error gốc sau cleanup | Error gốc sau cleanup |
| Error gốc | Error cleanup | Lỗi cleanup thay thế hoặc bao bọc, lỗi gốc được giữ làm suppressed/cause theo implementation | Tương tự, không còn terminal success |
| Cancel | Cleanup cancel được kích hoạt | Không gửi terminal mới cho subscriber đã hủy | Không gửi terminal mới cho subscriber đã hủy |

Nên dùng `doOnDiscard`, metrics hoặc logging có kiểm soát khi các phần tử chứa tài nguyên cần thu hồi và có thể bị discard do cleanup thất bại.

## 8. Lỗi acquire và lỗi cleanup: đừng bỏ sót

### Acquire chưa cấp được resource

`usingWhen` nhận một publisher tài nguyên, nên bản thân bước acquire có thể:

- **Hoàn tất rỗng** mà không cấp resource: flow hoàn tất rỗng; `resourceClosure` và cleanup không chạy vì không có resource.
- **Phát lỗi trước khi cấp resource**: downstream nhận lỗi acquire; không gọi cleanup của resource chưa tồn tại.
- **Được hủy trước khi cấp resource**: subscription acquire được cancel; việc dọn dẹp bên trong publisher acquire là trách nhiệm của publisher đó.

Vì vậy publisher acquire lý tưởng nên phát **một resource duy nhất**. Tránh dùng `Flux` phát nhiều connection làm `resourceSupplier`: `usingWhen` chỉ dùng một resource; các resource phát thêm có thể bị drop mà không đi qua resource-closure cleanup thông thường.

```java
Mono<Handle> acquisition = Mono.fromSupplier(Handle::new);
```

Đây là snippet với `Handle` minh họa. Nếu acquire thực sự là I/O reactive, trả publisher I/O từ driver thay vì ép nó bằng `.block()`.

### Cleanup thất bại

Giả sử công việc xử lý chính thành công nhưng `asyncComplete` trả `Mono.error(closeError)`. `usingWhen` không được báo success như thể close đã xong; downstream sẽ thấy lỗi cleanup. Trong các overload, Reactor có thể **bao bọc** cleanup failure hoặc đặt lỗi gốc làm suppressed; không nên viết test dựa vào message string của wrapper mà chưa đối chiếu đúng phiên bản Reactor.

Nếu công việc chính lỗi và cleanup cũng lỗi, lỗi cleanup thường trở thành tín hiệu cuối cùng; để bảo toàn chẩn đoán cần log/gắn nguyên nhân gốc và theo dõi `suppressed`/`cause` theo API.

**Không viết `onErrorResume(e -> Mono.empty())` sau cleanup chỉ để làm dashboard xanh.** Làm vậy có thể biến việc trả connection thất bại thành một kết quả trông như thành công. Nếu có fallback/retry, hãy đặt chính sách theo loại lỗi và tính idempotent của công việc dọn dẹp.

### Có nên retry cleanup?

Retry có thể hợp lý khi cleanup là thao tác idempotent và tài nguyên cho phép thử lại, nhưng cũng có thể gây ra side effect nhiều lần (đặc biệt commit). Không tự động `.retry()` mọi thao tác commit/rollback; phải hiểu trạng thái transaction có thể không xác định sau lỗi mạng và quyết định phục hồi phù hợp.

## 9. Cancellation, `take(n)`, timeout và client HTTP ngắt kết nối

Một request WebFlux có thể không kết thúc bằng terminal của nguồn mà bị cancel từ phía downstream. Ví dụ:

```java
Flux<String> limited = Flux.usingWhen(
        open(),
        resource -> resource.stream(),
        resource -> resource.closeAsync()
).take(3);
```

Đây là snippet giả định `open()` và `stream()` trả Publisher. Nếu nguồn có nhiều hơn ba phần tử, `take(3)` thường **hủy subscription upstream** sau khi lấy đủ ba phần tử. `usingWhen` cần đi vào đường cancel cleanup; **không được giả định nhánh `asyncComplete` được gọi** nếu dùng overload có nhánh cancel riêng.

Điều tương tự xảy ra khi:

- Client đóng kết nối SSE/WebSocket/HTTP streaming.
- Subscriber gọi `Disposable.dispose()` hoặc `Subscription.cancel()`.
- Một số operator chọn nguồn khác (`switchMap`, `take`, timeout, v.v.) và hủy nguồn hiện tại.

### Timeout có làm cleanup hoàn tất không?

```java
Mono<String> guarded = Mono.usingWhen(
        acquire(),
        resource -> useAsync(resource),
        resource -> releaseAsync(resource)
).timeout(Duration.ofSeconds(2));
```

Timeout có thể cancel upstream `usingWhen` khi quá thời hạn, kích hoạt cleanup cancel. Nhưng `timeout` **không bảo đảm một SDK I/O không hỗ trợ cancellation dừng ngay**. Nếu cleanup cũng chậm/hỏng, cần quan sát bằng metrics và cấu hình timeout tại driver/pool.

Đặt `timeout` **bên trong hay bên ngoài** `usingWhen` có thể làm thay đổi việc upstream được xem là `onError` hay `cancel`:

- `usingWhen(...).timeout(...)`: timeout nằm downstream; nó có thể cancel `usingWhen`, chọn nhánh cancel.
- `usingWhen(acquire, resource -> useAsync(resource).timeout(...), ...)`: timeout nằm **trong `resourceClosure`**, thường phát `onError(TimeoutException)` tới usingWhen, chọn nhánh error cleanup.

Sự khác biệt này đặc biệt quan trọng nếu cleanup tương ứng với commit/rollback. Không thay đổi vị trí operator một cách cơ học mà không kiểm thử ba đường.

### Cleanup bất đồng bộ khi subscriber đã hủy

Sau cancel, subscriber không còn chờ kết quả; cleanup async vẫn cần được triển khai để trả tài nguyên. Trong ứng dụng thực, đừng dựa vào việc một callback bên ngoài có thể `await` cleanup chỉ bằng `dispose()`. Hãy kiểm tra qua publisher cleanup, trace, metric, pool resource count và test có latch/probe.

## 10. Chương trình Java 17+ chạy được: kiểm thử đầy đủ ba đường vòng đời

Ví dụ này chạy độc lập với **Project Reactor Core 3.6.6**, JUnit Jupiter và `reactor-test`. Không cần khởi động Spring Boot hay database. Một tài nguyên giả `Tracked` ghi log vào danh sách thread-safe để kiểm tra khi nào mở, dùng và đóng. `StepVerifier` xác nhận tín hiệu, `CountDownLatch` giúp xác minh cleanup sau cancellation mà không dựa vào một thứ tự thread ngẫu nhiên.

### 10.1. Cấu trúc file

```text
reactor-resource-lifecycle/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── edu/
                └── demo/
                    └── ResourceLifecycleTest.java
```

Tạo file `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-resource-lifecycle</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.6.6</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/test/java/edu/demo/ResourceLifecycleTest.java`:

```java
package edu.demo;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class ResourceLifecycleTest {

    static final class Tracked implements AutoCloseable {
        private final List<String> events;
        private boolean closed;

        Tracked(List<String> events) {
            this.events = events;
            events.add("acquire");
        }

        String read() {
            if (closed) {
                throw new IllegalStateException("already closed");
            }
            events.add("use");
            return "VALUE";
        }

        @Override
        public void close() {
            closed = true;
            events.add("close");
        }
    }

    @Test
    void monoUsingEagerClosesBeforeDownstreamSeesValue() {
        List<String> events = new CopyOnWriteArrayList<>();

        Mono<String> mono = Mono.using(
                () -> new Tracked(events),
                handle -> Mono.fromSupplier(handle::read),
                Tracked::close,
                true
        ).doOnNext(value -> events.add("seen:" + value));

        StepVerifier.create(mono)
                .expectNext("VALUE")
                .verifyComplete();

        assertEquals(
                List.of("acquire", "use", "close", "seen:VALUE"),
                events
        );
    }

    @Test
    void fluxUsingClosesOnBusinessError() {
        List<String> events = new CopyOnWriteArrayList<>();

        Flux<String> flux = Flux.using(
                () -> new Tracked(events),
                handle -> Flux.concat(
                        Flux.just(handle.read()),
                        Flux.<String>error(
                                new IllegalStateException("business"))
                ),
                Tracked::close,
                true
        );

        StepVerifier.create(flux)
                .expectNext("VALUE")
                .expectErrorMessage("business")
                .verify();

        assertEquals(List.of("acquire", "use", "close"), events);
    }

    @Test
    void fluxUsingClosesOnCancellation() {
        List<String> events = new CopyOnWriteArrayList<>();

        Flux<String> never = Flux.using(
                () -> new Tracked(events),
                handle -> Flux.<String>never(),
                Tracked::close,
                true
        );

        StepVerifier.create(never)
                .expectSubscription()
                .thenCancel()
                .verify();

        assertEquals(List.of("acquire", "close"), events);
    }

    @Test
    void monoUsingWhenDelaysValueUntilCleanupIsDone() {
        List<String> events = new CopyOnWriteArrayList<>();

        Mono<String> mono = Mono.usingWhen(
                Mono.fromSupplier(() -> new Tracked(events)),
                handle -> Mono.fromSupplier(handle::read),
                handle -> Mono.fromRunnable(handle::close)
        ).doOnNext(value -> events.add("seen:" + value));

        StepVerifier.create(mono)
                .expectNext("VALUE")
                .verifyComplete();

        assertEquals(
                List.of("acquire", "use", "close", "seen:VALUE"),
                events
        );
    }

    @Test
    void usingWhenRunsErrorCleanupAndPreservesOriginalError() {
        List<String> events = new CopyOnWriteArrayList<>();

        Flux<String> flux = Flux.usingWhen(
                Mono.fromSupplier(() -> new Tracked(events)),
                handle -> Flux.<String>error(
                        new IllegalArgumentException("invalid")),
                handle -> Mono.fromRunnable(() -> {
                    events.add("complete-path");
                    handle.close();
                }),
                (handle, error) -> Mono.fromRunnable(() -> {
                    events.add("error-path:" + error.getMessage());
                    handle.close();
                }),
                handle -> Mono.fromRunnable(() -> {
                    events.add("cancel-path");
                    handle.close();
                })
        );

        StepVerifier.create(flux)
                .expectErrorMessage("invalid")
                .verify();

        assertEquals(
                List.of("acquire", "error-path:invalid", "close"),
                events
        );
    }

    @Test
    void usingWhenRunsCancelCleanup() throws InterruptedException {
        List<String> events = new CopyOnWriteArrayList<>();
        CountDownLatch closeDone = new CountDownLatch(1);

        Flux<String> flux = Flux.usingWhen(
                Mono.fromSupplier(() -> new Tracked(events)),
                handle -> Flux.<String>never(),
                handle -> Mono.fromRunnable(() -> {
                    events.add("complete-path");
                    handle.close();
                }),
                (handle, error) -> Mono.fromRunnable(() -> {
                    events.add("error-path");
                    handle.close();
                }),
                handle -> Mono.fromRunnable(() -> {
                    events.add("cancel-path");
                    handle.close();
                    closeDone.countDown();
                })
        );

        StepVerifier.create(flux)
                .expectSubscription()
                .thenCancel()
                .verify();

        assertTrue(closeDone.await(2, TimeUnit.SECONDS));
        assertEquals(
                List.of("acquire", "cancel-path", "close"),
                events
        );
    }

    @Test
    void usingWhenCleanupErrorDiscardsMonoValue() {
        List<String> events = new CopyOnWriteArrayList<>();

        Mono<String> mono = Mono.usingWhen(
                Mono.fromSupplier(() -> new Tracked(events)),
                handle -> Mono.fromSupplier(handle::read),
                handle -> Mono.fromRunnable(() -> {
                    handle.close();
                    throw new IllegalStateException("cleanup-failed");
                })
        );

        StepVerifier.create(mono)
                .expectErrorMatches(error ->
                        "cleanup-failed".equals(error.getMessage())
                        || (error.getCause() != null
                            && "cleanup-failed".equals(
                                error.getCause().getMessage())))
                .verify();

        assertEquals(List.of("acquire", "use", "close"), events);
    }

    @Test
    void virtualTimeProvesAsyncCleanupDelaysMonoSuccess() {
        StepVerifier.withVirtualTime(() ->
                Mono.usingWhen(
                        Mono.just("resource"),
                        resource -> Mono.just("OK"),
                        resource -> Mono.delay(Duration.ofSeconds(5)).then()
                ))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(4))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("OK")
                .verifyComplete();
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi khi tải được dependency và các assertion đúng: **8 test thành công, không có failure/error**. Đây là chương trình kiểm thử Java 17+ độc lập; không có output business trên stdout, vì `StepVerifier` và `assertEquals` **báo thành công bằng trạng thái test**. Phần summary Maven Surefire thường có dạng:

```text
Tests run: 8, Failures: 0, Errors: 0, Skipped: 0
```

Các dòng Maven khác (thời gian, version, build logs) có thể thay đổi theo môi trường.

### Vì sao các test được thiết kế như vậy?

1. `monoUsingEager...`: nhấn mạnh resource được đóng **trước khi downstream quan sát `onNext`** của `Mono.using(..., true)`.
2. `fluxUsingClosesOnBusinessError`: kiểm tra cleanup đồng bộ xảy ra trước terminal lỗi; các phần tử đã phát không bị xóa.
3. `fluxUsingClosesOnCancellation`: kiểm tra cancel cũng giải phóng resource, không cần nguồn phát `onComplete`.
4. `monoUsingWhenDelaysValue...`: kiểm tra `usingWhen` không phát giá trị Mono trước cleanup.
5. `usingWhenRunsErrorCleanup...`: đảm bảo đường lỗi đi qua `asyncError`, không nhầm sang complete.
6. `usingWhenRunsCancelCleanup`: đảm bảo cancel chọn `asyncCancel`; `CountDownLatch` tránh giả định cleanup async đã hoàn tất chỉ vì test cancel vừa kết thúc.
7. `usingWhenCleanupError...`: kiểm tra cleanup lỗi **thay thế đường thành công** và giá trị Mono bị bỏ. Bài test chấp nhận lỗi cleanup trực tiếp hoặc một lớp wrapper có cause tương ứng.
8. `virtualTime...`: kiểm tra chờ cleanup bất đồng bộ 5 giây bằng virtual time, không chờ 5 giây thực tế.

Các test dùng `Mono.fromRunnable` để mô phỏng Publisher cleanup hoàn tất đồng bộ. Trong ứng dụng thật, `closeAsync` có thể phát tín hiệu muộn hơn, lỗi, timeout hoặc phản ứng với cancellation khác nhau. Cần thêm integration test với driver/pool thực tế cho tài nguyên quan trọng.

## 11. Tài nguyên blocking: đặt scheduler đúng chỗ

`using` không tự chuyển code blocking sang thread khác. Ví dụ đọc file bằng một API đồng bộ có thể chặn event loop nếu subscribe trong WebFlux controller:

```java
Flux<String> fileLines(Path path) {
    return Flux.using(
            () -> new java.util.Scanner(
                    path, java.nio.charset.StandardCharsets.UTF_8),
            scanner -> Flux.<String>generate(sink -> {
                if (scanner.hasNextLine()) {
                    sink.next(scanner.nextLine());
                } else {
                    sink.complete();
                }
            }),
            java.util.Scanner::close,
            true
    ).subscribeOn(Schedulers.boundedElastic());
}
```

Đây là **snippet phương thức có thể biên dịch trong class Java** nếu import `java.nio.file.Path`, `reactor.core.publisher.Flux`, `reactor.core.scheduler.Schedulers`. `Scanner(Path, Charset)` tồn tại từ Java hiện đại; `hasNextLine` / `nextLine` là thao tác blocking, nên dùng `subscribeOn(boundedElastic())` để cách ly việc đọc khỏi event loop WebFlux.

`boundedElastic` cũng **không tạo thread vô hạn**: phải quan sát giới hạn worker, hàng đợi và khả năng chịu tải của file system. Nếu số file lớn, chọn concurrency thích hợp và cân nhắc streaming buffer. Với các tác vụ blocking có thể ném `IOException`, hãy trả tín hiệu lỗi và bảo toàn cleanup; `Scanner` có API `ioException()` cần xem xét nếu cần phát hiện lỗi I/O bị Scanner giữ lại.

Đừng dùng:

```java
Mono.usingWhen(
        Mono.just(resource),
        r -> Mono.fromCallable(r::blockingRead),
        r -> Mono.fromRunnable(r::blockingClose)
);
```

mà giả định vì có chữ `Mono` nên tất cả không blocking. `Mono.fromCallable` và `Mono.fromRunnable` **chỉ mô tả việc chạy callback lúc subscribe**, không tự tách thread. Nếu callback blocking thì vẫn cần scheduler phù hợp, nhưng tốt hơn là dùng driver reactive thực sự khi có thể.

## 12. R2DBC trong Spring WebFlux: đóng connection bất đồng bộ

Một `io.r2dbc.spi.Connection` được tạo bởi `ConnectionFactory.create()` thông qua Publisher và `close()` cũng trả `Publisher<Void>`. Do đó **`usingWhen` phù hợp về mặt ngữ nghĩa**.

Đoạn sau là một **phương thức minh họa tích hợp R2DBC**; cần dependency R2DBC SPI và driver thực tế, import `Flux`, `Mono`, `ConnectionFactory`. Đây không phải ứng dụng Spring Boot độc lập:

```java
record User(Long id, String name) {}

Flux<User> findUsers(ConnectionFactory factory) {
    return Flux.usingWhen(
            Mono.from(factory.create()),
            connection ->
                    Flux.from(
                        connection.createStatement(
                                "SELECT id, name FROM users")
                            .execute()
                    ).flatMap(result ->
                        Flux.from(result.map((row, meta) ->
                                new User(
                                    row.get("id", Long.class),
                                    row.get("name", String.class)
                                )
                        ))
                    ),
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

Ý nghĩa:

- `Mono.from(factory.create())`: subscribe vào bước acquire connection khi downstream đăng ký.
- `resourceClosure`: chạy SQL bằng connection vừa cấp và map `Result` thành dữ liệu **khi connection còn mở**.
- Cleanup complete/error/cancel đều gọi `connection.close()` theo SPI; với pool, lời close có thể trả connection về pool tùy implementation.
- Nếu truy vấn lỗi, cleanup vẫn được thực hiện rồi chuyển tiếp lỗi nếu cleanup thành công; nếu consumer hủy sớm, nhánh cancel cleanup được kích hoạt.

**Điều kiện của snippet:** bảng `users` phải có các cột phù hợp và giá trị `id`/`name` hợp lệ theo schema; driver có thể có quy định về số statement/result đang hoạt động, isolation và việc xử lý row. Phương thức không bao gồm transaction commit/rollback: ví dụ chỉ minh họa cấp/phóng connection.

### Spring đã có công cụ quản lý connection, đừng tự làm lại vô cớ

Nếu đang dùng `DatabaseClient`, `R2dbcEntityTemplate`, Spring Data R2DBC hoặc `R2dbcTransactionManager`, **ưu tiên cơ chế quản lý connection/transaction của Spring**. Những công cụ này dùng Reactor Context để gắn connection vào transaction đang hoạt động. Trực tiếp `factory.create()` ở nơi cần tham gia transaction có thể lấy một connection khác và **không tham gia transaction hiện tại**.

Spring cung cấp `ConnectionFactoryUtils` cho các integration cần tự quản lý connection mà vẫn tương tác với transaction theo Reactor Context. Đặc biệt, `ConnectionFactoryUtils.releaseConnection(connection, factory)` có thể tránh đóng một connection do transaction manager đang sở hữu; logic này khác việc gọi `connection.close()` mù quáng. Dùng tài liệu API của Spring đúng phiên bản để tích hợp.

Tư duy chọn lựa:

- Tự quản lý một resource async không được Spring quản lý: `usingWhen` có thể hợp lý.
- Nghiệp vụ truy vấn chuẩn trong Spring Data R2DBC: dùng `DatabaseClient`/repository/template; để framework xử lý acquisition và release.
- Transaction nhiều thao tác: dùng `TransactionalOperator` hoặc cơ chế reactive transaction của Spring nếu phù hợp, thay vì tự viết commit/rollback bằng callback chưa đủ.

## 13. Transaction reactive: commit, rollback và cancellation

Trong nghiệp vụ ghi dữ liệu, cleanup có thể là:

- **`asyncComplete` → commit** sau khi tất cả thao tác liên quan thành công.
- **`asyncError` → rollback** nếu có lỗi.
- **`asyncCancel` → rollback** nếu subscriber ngừng theo dõi trước khi transaction hoàn tất.

`usingWhen` là một nền tảng phù hợp để mô hình hóa các đường này. Tuy nhiên, việc mở transaction, commit, rollback và close connection đúng chuẩn driver/transaction manager là một bài toán lớn hơn một lệnh `close()`.

Ví dụ **ý tưởng**, không phải code độc lập:

```java
Flux.usingWhen(
        acquireTransactionalSession(),
        session -> session.runBusinessFlow(),
        session -> session.commitAndRelease(),
        (session, failure) -> session.rollbackAndRelease(),
        session -> session.rollbackAndRelease()
);
```

Ở đây `commitAndRelease`/`rollbackAndRelease` được **giả định** bao gồm cả giải phóng resource, xử lý lỗi cleanup và trạng thái transaction theo hợp đồng của hệ thống. Nếu commit lỗi, trạng thái của remote transaction có thể không xác định; retry tùy tiện có thể nhân đôi side effect.

### Cách dùng transaction manager của Spring

Với Spring reactive transaction, ứng dụng thường làm việc qua `ReactiveTransactionManager` và `TransactionalOperator`:

```java
TransactionalOperator tx =
        TransactionalOperator.create(transactionManager);

Mono<Void> operation =
        databaseClient.sql(
                "UPDATE inventory SET reserved = reserved + 1 WHERE id = :id")
            .bind("id", itemId)
            .fetch()
            .rowsUpdated()
            .then();

Mono<Void> transactional = tx.transactional(operation);
```

Đây là **snippet tích hợp**: `transactionManager` phải là bean quản lý transaction reactive; `databaseClient` được cấu hình tham gia cùng transaction và `itemId` đã có giá trị. `TransactionalOperator` thuộc `org.springframework.transaction.reactive.TransactionalOperator`.

`tx.transactional(operation)` ràng buộc Publisher vào transaction do Spring quản lý, thay vì phải tự bắt mọi lỗi và hủy để đóng connection. Các API Spring xây trên Reactor Context, vì vậy không thay chúng bằng một JDBC transaction truyền thống dùng `ThreadLocal` khi đang viết code reactive.

**Cảnh báo cancellation trong transaction:** với publisher transactional bị cancel giữa chừng, nhánh rollback có thể được kích hoạt theo cơ chế transaction manager. Không dùng `.take(1)` trong một transaction streaming lớn mà mặc định tin toàn bộ business flow vẫn hoàn tất và được commit; phải quyết định rõ ranh giới transaction và kiểm thử hành vi.

## 14. Đặt mọi bước cần tài nguyên bên trong `resourceClosure`

Một nguyên tắc rất dễ bỏ quên nằm trong Javadoc của `usingWhen`: những operator **cần tài nguyên còn mở và ổn định** phải được mô tả bên trong `resourceClosure`.

Không tốt:

```java
Flux<RowData> rows = Flux.usingWhen(
        acquireConnection(),
        connection -> streamRawRows(connection),
        connection -> closeConnection(connection)
);

// Nếu thao tác map dưới đây cần connection còn mở, nó có thể quá muộn.
Flux<String> mapped = rows.map(row -> row.readLobFromConnection());
```

Đây là **sơ đồ minh họa**, không phải các API có sẵn; `RowData.readLobFromConnection()` được giả định cần connection. Ở downstream, `usingWhen` có thể hoàn tất cleanup trước khi những xử lý bất đồng bộ được lên lịch bên ngoài sử dụng lại resource.

Nên đưa xử lý phụ thuộc resource vào scope:

```java
Flux<String> mapped = Flux.usingWhen(
        acquireConnection(),
        connection -> streamRawRows(connection)
                .concatMap(row -> readLobWhileOpen(connection, row)),
        connection -> closeConnection(connection)
);
```

Các hàm trong snippet là **giả định**; ý tưởng là publisher sử dụng tài nguyên phải bao gồm cả bước đọc LOB, encode hoặc flush thật sự cần connection. Nếu downstream nhận object có tham chiếu tới resource, tốt nhất chuyển thành DTO độc lập trước khi cleanup.

Không giữ một `Connection`/cursor trong trường singleton rồi chia sẻ giữa nhiều subscription trừ khi driver explicitly cho phép. Mỗi subscription có resource scope riêng là mô hình an toàn hơn.

## 15. Xử lý lỗi cleanup và bảo toàn thông tin chẩn đoán

Ba loại lỗi nên phân biệt:

| Loại lỗi | Thời điểm | Nguyên tắc xử lý |
|---|---|---|
| Acquire error | Trước khi có resource | Chuyển lỗi cho downstream; không close resource chưa tồn tại |
| Business/use error | Trong resourceClosure | Chạy error cleanup; truyền lỗi gốc nếu cleanup thành công |
| Cleanup error | Trong callback close/commit/rollback | Không lặng lẽ tuyên bố success; giữ nguyên nhân để điều tra |

Đối với `using(eager=true)`, lỗi cleanup đồng bộ có thể **thay thế terminal** và với `Mono` valued có thể bỏ giá trị. Với `using(eager=false)`, terminal đã đi xuống nên lỗi cleanup không thể biến chuỗi thành lỗi mới cho subscriber đó; Reactor có thể drop/báo qua hook/log. Vì vậy nếu thành công chỉ hợp lệ khi close thành công, ưu tiên eager hoặc thiết kế `usingWhen`.

Đối với `usingWhen`, nếu cleanup publisher phát `onError(t)`, lỗi cleanup trở thành terminal được quan sát (có thể được Reactor bọc trong exception thông báo cleanup thất bại). Nếu nguồn use cũng đã lỗi, nguyên nhân gốc thường được giữ trong cause/suppressed. Khi ghi log, đừng chỉ log `error.getMessage()` rồi bỏ mất `getCause()` và `getSuppressed()`.

Nếu cleanup **không bao giờ hoàn tất**, terminal có thể không đến downstream, đặc biệt rõ trong `Mono.usingWhen`. Hãy xem xét timeout ở **publisher cleanup** khi driver có thể treo, cùng chính sách lỗi rõ ràng. Nhưng đừng thêm retry vô hạn cho cleanup vì điều đó có thể giữ connection mãi không trả pool.

### Không `subscribe()` thủ công trong cleanup

Sai:

```java
resource -> {
    closeAsync(resource).subscribe();
    return Mono.empty();
}
```

Đây là callback minh họa, nhưng cách làm sai vì trả `Mono.empty()` khiến `usingWhen` tưởng cleanup đã xong, trong khi close đang chạy trên subscription khác. Lỗi close có thể bị mất; scope resource có thể kết thúc sớm.

Đúng:

```java
resource -> closeAsync(resource)
```

Phải trả publisher thật cho `usingWhen`. Nếu cần hai cleanup theo thứ tự:

```java
resource -> flushAsync(resource)
        .then(closeAsync(resource))
```

Nếu `flushAsync` lỗi, `.then(closeAsync(...))` sẽ **không** tự chạy close; để vẫn đóng khi flush lỗi, cần xây chính sách giải phóng đặc biệt và kiểm thử. Không dùng `.then` bừa bãi với giả định close luôn diễn ra.

## 16. So sánh `using` / `usingWhen` với những cách khác

| Kỹ thuật | Phù hợp khi | Giới hạn |
|---|---|---|
| Java `try-with-resources` | Công việc đồng bộ thực thi xong trong lexical scope | Nếu trả publisher lazy ra ngoài scope, resource có thể đóng quá sớm |
| `doFinally` | Quan sát terminal/cancel; metrics, cleanup đồng bộ đơn giản | Không đợi publisher cleanup async |
| `doOnCancel` | Chỉ cần phản ứng với cancellation | Không thay thế cleanup khi complete/error |
| `Flux.using` / `Mono.using` | Acquire và release có callback đồng bộ | Không nên `.block()` cleanup async |
| `Flux.usingWhen` / `Mono.usingWhen` | Acquire/release bằng Publisher; commit/rollback async | Phải tính đến lỗi cleanup, cancellation và trì hoãn terminal |
| `@Transactional` / `TransactionalOperator` reactive | Công việc nằm trong transaction do Spring quản lý | Cần cấu hình reactive transaction manager và Reactor Context |
| `ConnectionFactoryUtils` | Integration R2DBC cần tham gia quản lý connection của Spring | Cần theo đúng protocol của Spring/driver |
| Pool/SDK API riêng | Driver đã có scope lifecycle chuyên biệt | Không tự đóng connection do framework đang sở hữu |

Không phải mọi object tạm thời đều cần `usingWhen`. Chỉ cần dùng khi thực sự sở hữu một tài nguyên cần giải phóng hoặc một transaction cần cleanup rõ ràng.

## 17. Checklist thiết kế API quản lý tài nguyên

Trước khi viết code production:

1. **Ai sở hữu resource?** Ứng dụng, pool, Spring transaction manager hay một driver nội bộ? Không tự close resource do một scope khác quản lý.
2. **Acquire là blocking hay reactive?** Blocking có thể dùng `using` cộng scheduler phù hợp; reactive dùng `usingWhen`.
3. **Release trả gì?** `void`/`close()` đồng bộ hay `Mono<Void>`/`Publisher<?>`? Nếu async, tránh `.block()` hoặc `.subscribe()` thủ công.
4. **Mỗi subscription có resource riêng?** Tránh dùng `Mono.just(precreatedHandle)` nếu cùng handle không được phép chia sẻ.
5. **Các bước cần resource còn mở nằm trong closure?** Không trả cursor/LOB/lazy view ra ngoài rồi giải phóng quá sớm.
6. **Complete/error/cancel có cùng hành vi không?** Nếu transaction thì thường complete/commit khác error/cancel/rollback.
7. **Cleanup lỗi sẽ được xử lý ra sao?** Không biến lỗi thực thành success; có logging/metrics và chính sách phục hồi.
8. **Có khả năng bị cancel/timeout không?** Kiểm thử disconnect, `take(n)`, timeout và cancel trong acquire/use.
9. **Resource có giới hạn pool/quota không?** Giới hạn concurrency, hàng đợi và timeout ở client/driver; `usingWhen` không tự tạo thêm connection.
10. **Có integration test với driver thật không?** Unit test giả resource xác minh vòng đời logic, nhưng không chứng minh connection pool thực trả tài nguyên đúng cách.

## 18. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng `try-with-resources` quanh hàm trả `Flux` lazy | Đóng resource trước khi subscription dùng nó | Đưa acquire/use/cleanup vào `using`/`usingWhen` |
| Tạo resource bên ngoài rồi tái sử dụng cho nhiều subscriber | Subscription sau dùng handle đã đóng | Tạo resource mới theo từng subscription |
| Gọi `.block()` trong cleanup reactive | Nghẽn event loop, mất non-blocking | Trả publisher cleanup cho `usingWhen` |
| Gọi `closeAsync().subscribe()` rồi trả `Mono.empty()` | Operator không đợi cleanup; lỗi có thể bị mất | Trả trực tiếp `closeAsync()` |
| Chỉ dọn khi `onComplete` | Rò resource khi error/cancel | Bao trọn cả ba đường |
| Coi cancellation là commit transaction | Ghi một phần nghiệp vụ chưa hoàn tất | Thiết kế rollback khi cancel theo contract |
| Cho `Mono.usingWhen` trả giá trị trước cleanup | Hiểu sai tín hiệu, không nhận ra cleanup có thể đổi success thành error | Nhớ Mono giữ giá trị đến khi cleanup hoàn tất |
| Cho `Flux.usingWhen` luôn giữ mọi phần tử đến sau cleanup | Hiểu sai streaming và side effect | Flux có thể phát `onNext` trước khi cleanup chạy |
| Nuốt lỗi cleanup bằng `onErrorComplete()` ở ngoài | Che mất leak/commit failure | Ghi nhận và xử lý theo chính sách lỗi |
| Đọc LOB/cursor ngoài resourceClosure | Dùng tài nguyên đã đóng | Hoàn tất xử lý phụ thuộc resource trong closure |
| `Flux` resourceSupplier phát nhiều resource | Resource dư bị drop, nguy cơ leak | Dùng publisher cấp đúng một resource |
| Dùng `ThreadLocal` transaction trong luồng reactive | Mất context khi đổi scheduler | Dùng reactive transaction + Reactor Context |
| Giả định `dispose()` luôn đợi cleanup async xong | Kiểm thử flaky, có thể bỏ sót dọn dẹp | Quan sát publisher cleanup/latch/metrics |
| Tự gọi `connection.close()` khi Spring đang quản lý transaction | Phá transaction/pool scope | Dùng `DatabaseClient`/`ConnectionFactoryUtils` phù hợp |

## 19. Bài tập tự kiểm tra

**Bài 1.** Tại sao đoạn sau có thể sai?

```java
try (FileHandle file = openFile()) {
    return file.toFlux();
}
```

**Đáp án:** Nếu `toFlux()` là publisher lazy, `try-with-resources` đóng file trước khi subscriber bắt đầu đọc. Dùng `Flux.using` để mở file khi subscribe và đóng khi nguồn kết thúc/cancel, hoặc dùng API file publisher tự quản lý lifecycle.

**Bài 2.** Sự khác nhau quan trọng nhất giữa `Mono.using` và `Mono.usingWhen` là gì?

**Đáp án:** `using` nhận resource đồng bộ và chạy cleanup đồng bộ; `usingWhen` nhận publisher cấp tài nguyên và đợi publisher cleanup. Với `Mono.usingWhen`, giá trị thành công được giữ đến khi cleanup hoàn tất.

**Bài 3.** `Flux.usingWhen` đã phát `A`, `B` thì cleanup thất bại. Downstream có thể đã nhận gì?

**Đáp án:** Đã có thể nhận `A`, `B` và sau đó nhận `onError(cleanupFailure)` thay vì `onComplete`; phần tử đã quan sát không bị thu hồi.

**Bài 4.** Một stream bị `take(1)` hủy upstream sau phần tử đầu. Với overload 5 tham số của `usingWhen`, cleanup nào cần chạy?

**Đáp án:** Thông thường là **`asyncCancel`**, không phải nhánh `asyncComplete` của resource closure. Cần kiểm thử chính xác ranh giới `take`/cancel.

**Bài 5.** Một transaction do Spring R2DBC quản lý. Có nên dùng `factory.create()` rồi `close()` trực tiếp ở giữa transaction?

**Đáp án:** Không nên mặc định làm vậy. Connection tự tạo có thể không thuộc transaction hiện tại; dùng `DatabaseClient`, `R2dbcEntityTemplate`, `ConnectionFactoryUtils` hoặc `TransactionalOperator` theo thiết kế transaction.

**Bài 6.** `asyncComplete` trả `Mono.delay(Duration.ofSeconds(5)).then()`; `Mono.usingWhen` có giá trị `"OK"`. Khi nào subscriber nhận `"OK"`?

**Đáp án:** Sau khi publisher cleanup hoàn tất, khoảng 5 giây theo scheduler nếu không có lỗi hoặc hủy; trước đó chưa nhận `onNext("OK")`.

**Bài 7.** Nếu acquire kết thúc rỗng, `usingWhen` có gọi close không?

**Đáp án:** Không có resource đã cấp để close; publisher chính kết thúc rỗng và callback xử lý resource không được gọi.

**Bài 8.** Vì sao code sau không đảm bảo close xảy ra?

```java
resource -> flush(resource).then(close(resource))
```

**Đáp án:** Nếu `flush` phát `onError`, toán tử `.then` không subscribe vào `close`. Cần thiết kế cleanup bảo đảm close cả khi flush lỗi, với cơ chế bảo toàn hai lỗi.

## 20. Tổng kết

`using` và `usingWhen` tạo ra **ranh giới sở hữu tài nguyên** rõ ràng trong reactive:

- **`using`** dành cho acquire/release đồng bộ. Cờ `eager` điều chỉnh thứ tự cleanup và tín hiệu downstream; với `Mono` có giá trị, eager cleanup thành công trước khi phát `onNext`.
- **`usingWhen`** dành cho acquire/release bằng Publisher, có thể tách ba đường **complete, error, cancel**. Với `Mono`, cleanup hoàn tất trước khi downstream nhận giá trị; với `Flux`, các phần tử đã stream có thể đến trước cleanup, nhưng terminal cần chờ cleanup.
- **Đừng quên cancel**: client disconnect, timeout và các toán tử như `take(n)` có thể hủy nguồn dù business code chưa chạy xong.
- **Đừng đánh mất lỗi cleanup**: nếu close/commit/rollback thất bại, đó là một lỗi đáng quan sát, không phải thành công.
- **Ưu tiên framework quản lý resource khi đã có**: dùng Spring reactive transaction / DatabaseClient / ConnectionFactoryUtils thay vì tái triển khai connection management.

Hãy nhìn vào **ai sở hữu resource, ai subscribe cleanup, và khi nào terminal được phát**. Ba câu hỏi đó giúp tránh phần lớn resource leak và lỗi transaction trong Spring WebFlux.

## Tài liệu chính thức

- Project Reactor Core 3.6.6, **`Mono` API – `using` và `usingWhen`**: https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Mono.html
- Project Reactor Core 3.6.6, **`Flux` API – `using` và `usingWhen`**: https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Flux.html
- Project Reactor, **Resource handling in operator choice**: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Project Reactor, **Testing with StepVerifier**: https://projectreactor.io/docs/core/release/reference/testing.html
- Spring Framework, **R2DBC data access**: https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
- Spring Framework, **Programmatic transaction management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework, **WebFlux**: https://docs.spring.io/spring-framework/reference/web/webflux.html