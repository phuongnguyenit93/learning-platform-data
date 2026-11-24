# Mở, sử dụng và đóng tài nguyên trên mọi đường kết thúc

Một pipeline reactive thường đọc file, giữ cursor database, mượn kết nối, mở response body hoặc chiếm một lease từ pool. Những tài nguyên này cần được giải phóng khi luồng hoàn tất, phát lỗi hoặc bị hủy. Nếu mở tài nguyên ở thời điểm lắp ráp pipeline rồi quên quản lý vòng đời subscription, ứng dụng có thể rò rỉ connection, file descriptor hoặc slot trong pool. Reactor cung cấp `using` và `usingWhen` để gắn vòng đời tài nguyên với vòng đời Publisher.

Bài học thuộc chương **Tài nguyên** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là mở tài nguyên đúng thời điểm, giữ tài nguyên trong lúc tiêu thụ dữ liệu và đóng tài nguyên trên mọi đường kết thúc, bao gồm cancellation.

Sau bài học, bạn có thể:

- Giải thích vì sao thời gian sống của tài nguyên phải gắn với subscription.
- Dùng `Flux.using` hoặc `Mono.using` cho tài nguyên có thao tác cleanup đồng bộ.
- Dùng `usingWhen` khi việc giải phóng tài nguyên trả về một Publisher bất đồng bộ.
- Phân biệt cleanup khi hoàn tất, khi lỗi và khi cancellation.
- Đặt fallback, timeout và scheduler sao cho không giữ tài nguyên lâu hơn cần thiết.
- Kiểm thử việc mở và đóng tài nguyên trên các đường thành công, lỗi và hủy.

## 1. Vòng đời tài nguyên trong pipeline reactive

Trong code imperative, ta thường dùng `try-with-resources` để giới hạn phạm vi sử dụng tài nguyên:

```java
try (InputStream input = Files.newInputStream(path)) {
    return readAll(input);
}
```

Khối `try` bao trùm toàn bộ thao tác đọc. Khi rời khỏi khối, stream được đóng dù thao tác thành công hay ném exception.

Với reactive, phương thức xây dựng pipeline thường trả về `Mono` hoặc `Flux` trước khi dữ liệu thực sự được tiêu thụ. Đoạn mã sau là sai:

```java
Flux<Row> rows;
try (Cursor cursor = database.openCursor()) {
    rows = cursor.rows();
}

return rows;
```

Cursor bị đóng ngay khi phương thức trả về, trong khi `rows` có thể chưa được subscribe hoặc chưa đọc xong. Publisher chỉ mô tả công việc sẽ thực hiện; nó không nhất thiết tiêu thụ dữ liệu tại thời điểm lắp ráp.

Hãy để Reactor quản lý phạm vi tài nguyên:

```text
subscribe
   |
   v
acquire resource
   |
   v
consume Publisher
   |
   +---- onComplete ----+
   |                    |
   +---- onError -------+----> cleanup resource
   |                    |
   +---- cancel --------+
                        |
                        v
                   release resource
```

Mỗi subscription có vòng đời riêng. Tài nguyên nên được mở khi subscription bắt đầu và được giải phóng khi subscription kết thúc hoặc bị hủy. Đây là lý do các toán tử quản lý tài nguyên nhận một hàm tạo tài nguyên, một hàm tạo Publisher sử dụng tài nguyên và một hàm cleanup.

## 2. `using`: quản lý tài nguyên có cleanup đồng bộ

`Flux.using` và `Mono.using` phù hợp khi thao tác giải phóng tài nguyên là đồng bộ. Có thể hình dung chữ ký cơ bản như sau:

```java
using(
    resourceSupplier,
    sourceFactory,
    resourceCleanup
)
```

- `resourceSupplier` tạo tài nguyên khi có subscription.
- `sourceFactory` nhận tài nguyên và trả về Publisher sử dụng tài nguyên đó.
- `resourceCleanup` giải phóng tài nguyên khi Publisher kết thúc hoặc bị hủy.

Ví dụ dùng cursor đồng bộ:

```java
interface Cursor extends AutoCloseable {
    Flux<Row> rows();

    @Override
    void close(); // API này không khai báo checked exception.
}

Flux<Row> readRows(CursorFactory cursorFactory) {
    return Flux.using(
        cursorFactory::open,
        Cursor::rows,
        Cursor::close
    );
}
```

`cursorFactory.open()` chỉ được gọi khi subscribe. Reactor đưa cursor vào `Cursor::rows`, phát các dòng từ Publisher trả về và gọi `close()` khi luồng hoàn tất, lỗi hoặc bị hủy. Mỗi lần subscribe sẽ tạo một cursor mới, thay vì chia sẻ một cursor đã mở từ trước giữa nhiều subscriber.

Với `Mono`, cách dùng tương tự:

```java
Mono<Report> readReport(ReportReaderFactory factory) {
    return Mono.using(
        factory::open,
        ReportReader::read,
        ReportReader::close
    );
}
```

Ở đây, `ReportReader::read` trả về `Mono<Report>`, còn `close()` giải phóng reader đồng bộ. Hãy chọn `using` khi cleanup thực sự có thể hoàn tất ngay trong lời gọi đồng bộ và không cần chờ một Publisher khác.

### Phạm vi cleanup và chế độ eager

Overload cơ bản của `using` thực hiện cleanup khi nguồn kết thúc. Reactor cũng có overload nhận tham số `eager` để điều khiển thời điểm cleanup tương đối với việc truyền tín hiệu kết thúc xuống downstream:

```java
Flux<Row> rows = Flux.using(
    cursorFactory::open,
    Cursor::rows,
    Cursor::close,
    true // eager cleanup
);
```

Với cleanup eager, Reactor thực hiện cleanup trước khi truyền tín hiệu terminal xuống downstream. Với cleanup không eager, tín hiệu terminal được truyền xuống trước rồi cleanup được thực hiện. Nếu cleanup có thể ném exception, chế độ eager có thể làm lỗi cleanup trở thành lỗi quan sát được của pipeline; chế độ không eager có thể khiến lỗi cleanup không còn thay đổi tín hiệu terminal đã được truyền. Hãy chọn dựa trên việc caller có cần biết cleanup thất bại hay không.

Cleanup nên ngắn, an toàn khi được gọi ở đường hủy và không dựa vào việc downstream còn tiếp tục xử lý dữ liệu. Nếu thao tác đóng có thể block, không thực hiện nó trên event-loop thread; cân nhắc API cleanup bất đồng bộ hoặc điều phối phần blocking sang scheduler phù hợp.

## 3. `usingWhen`: quản lý cleanup bất đồng bộ

Một số tài nguyên không thể giải phóng bằng một lời gọi đồng bộ đơn giản. Ví dụ, đóng connection reactive, rollback transaction, trả lease qua một dịch vụ từ xa hoặc giải phóng tài nguyên cần I/O. Khi cleanup trả về `Publisher`, dùng `usingWhen`.

`usingWhen` cho phép chỉ định cleanup riêng cho ba đường kết thúc:

```java
usingWhen(
    resourcePublisher,
    resourceToPublisher,
    asyncComplete,
    asyncError,
    asyncCancel
)
```

- `resourcePublisher` phát tài nguyên được cấp.
- `resourceToPublisher` sử dụng tài nguyên và tạo luồng dữ liệu chính.
- `asyncComplete` trả về Publisher cleanup khi nguồn hoàn tất bình thường.
- `asyncError` nhận tài nguyên và lỗi để cleanup khi nguồn lỗi.
- `asyncCancel` trả về Publisher cleanup khi subscription bị hủy.

Ví dụ với một cursor có thao tác đóng bất đồng bộ:

```java
interface AsyncCursor {
    Flux<Row> rows();
    Mono<Void> closeAsync();
}

Mono<AsyncCursor> acquireCursor();

Flux<Row> readRows() {
    return Flux.usingWhen(
        acquireCursor(),
        AsyncCursor::rows,
        AsyncCursor::closeAsync,
        (cursor, error) -> cursor.closeAsync(),
        AsyncCursor::closeAsync
    );
}
```

Khi nguồn `rows()` hoàn tất, Reactor subscribe Publisher do `closeAsync()` trả về và phối hợp việc kết thúc với cleanup. Khi nguồn lỗi, callback `asyncError` nhận cả cursor lẫn exception. Khi downstream hủy, callback `asyncCancel` được dùng để giải phóng cursor.

Ví dụ trên dùng cùng một thao tác đóng cho cả ba đường. Trong ứng dụng có transaction, cleanup thường khác nhau:

```java
Flux<Row> queryInTransaction() {
    return Flux.usingWhen(
        connectionFactory.create(),
        connection -> connection.beginTransaction()
            .thenMany(executeQuery(connection)),
        connection -> connection.commitTransaction()
            .then(connection.close()),
        (connection, error) -> rollbackAndClose(connection, error),
        connection -> rollbackAndClose(connection, null)
    );
}
```

`rollbackAndClose` ở ví dụ là hàm ứng dụng cần triển khai để bảo đảm connection được đóng kể cả khi rollback gặp lỗi. Khi transaction kết thúc bình thường, commit rồi đóng connection. Khi lỗi hoặc cancellation, rollback theo chính sách rồi đóng connection. Tên API cụ thể của connection phụ thuộc driver, chẳng hạn R2DBC.

Điểm quan trọng là cleanup bất đồng bộ phải được biểu diễn thành Publisher để Reactor có thể subscribe và phối hợp vòng đời. Không gọi một hàm async rồi bỏ qua Publisher mà nó trả về; nếu không subscribe, thao tác cleanup có thể không được thực hiện.

## 4. Vì sao cancellation cũng phải giải phóng tài nguyên?

Một subscription không chỉ kết thúc bằng `onComplete` hoặc `onError`. Subscriber có thể gọi `cancel()` khi người dùng rời trang, request HTTP bị ngắt, timeout xảy ra hoặc downstream không còn cần dữ liệu.

Nếu cleanup chỉ được đặt trong `doOnComplete` hoặc `doOnError`, tài nguyên có thể bị giữ lại khi cancellation xảy ra. `using` và `usingWhen` gắn cleanup với cả đường cancellation.

```java
Flux<Row> rows = Flux.usingWhen(
    acquireCursor(),
    AsyncCursor::rows,
    AsyncCursor::closeAsync,
    (cursor, error) -> cursor.closeAsync(),
    cursor -> cursor.closeAsync()
);
```

Trong ví dụ, callback cuối cùng là cleanup dành cho cancellation. Nếu nguồn là một luồng dài hoặc có thể không hoàn tất, đường này đặc biệt quan trọng.

### `doFinally` để quan sát vòng đời

`doFinally` nhận `SignalType` sau khi subscription kết thúc bằng complete, error hoặc cancel:

```java
Flux<Event> events = eventSource
    .doFinally(signalType ->
        log.debug("Subscription kết thúc với {}", signalType)
    );
```

`doFinally` phù hợp để ghi metric, log hoặc cập nhật bộ đếm. Callback của nó là đồng bộ và không nhận Publisher cleanup để chờ. Vì vậy, không dùng `doFinally` làm cơ chế chính để đóng tài nguyên cần cleanup bất đồng bộ. Với tài nguyên thực, hãy dùng `using` hoặc `usingWhen`.

`doOnTerminate` quan sát complete và error nhưng không bao phủ cancellation. `doOnCancel` quan sát cancellation. Nếu cần quan sát cả ba tín hiệu kết thúc bằng một hook, `doFinally` thường rõ ràng hơn.

## 5. Đặt fallback bên ngoài phạm vi tài nguyên

Vị trí của toán tử phục hồi lỗi ảnh hưởng đến thời điểm tài nguyên được đóng. Nếu nguồn chính sử dụng cursor và có thể lỗi, thường nên để `using`/`usingWhen` kết thúc và giải phóng cursor trước khi chạy fallback không cần cursor.

```java
Flux<Row> rows = readRowsFromPrimaryStore()
    .onErrorResume(StoreUnavailableException.class,
        error -> readRowsFromBackupStore());
```

Nếu `readRowsFromPrimaryStore()` được xây dựng bằng `usingWhen`, lỗi của nguồn chính đi qua ranh giới quản lý tài nguyên; cleanup của cursor được thực hiện rồi lỗi mới đến `onErrorResume` bên ngoài. Sau đó Publisher dự phòng được subscribe.

Ngược lại, nếu đặt fallback bên trong `resourceToPublisher`, phạm vi tài nguyên chính có thể còn mở trong lúc fallback chạy:

```java
Flux<Row> rows = Flux.usingWhen(
    acquireCursor(),
    cursor -> cursor.rows()
        .onErrorResume(error -> readRowsFromBackupStore()),
    AsyncCursor::closeAsync,
    (cursor, error) -> cursor.closeAsync(),
    AsyncCursor::closeAsync
);
```

Trong cấu trúc này, nhánh fallback là một phần của Publisher sử dụng cursor. Nếu fallback không cần cursor, việc giữ tài nguyên trong suốt thời gian fallback có thể làm pool cạn nhanh hơn. Hãy đặt fallback ngoài phạm vi resource khi không cần tài nguyên đó nữa.

## 6. Tài nguyên blocking và scheduler

`using` không tự chuyển công việc sang scheduler khác. Nếu `resourceSupplier`, source hoặc cleanup thực hiện blocking I/O, chúng có thể chạy trên thread subscribe hoặc thread đang phát tín hiệu. Với ứng dụng Reactor dùng event loop, điều đó có thể làm chậm nhiều request khác.

Nếu API mở/đọc/đóng là blocking, hãy điều phối phần công việc đó sang scheduler phù hợp. Ví dụ đơn giản cho một thao tác blocking tạo kết quả:

```java
Mono<Report> report = Mono.fromCallable(() -> {
        try (ReportReader reader = reportReaderFactory.open()) {
            return reader.read();
        }
    })
    .subscribeOn(Schedulers.boundedElastic());
```

Ở đây, toàn bộ vòng đời imperative nằm trong `Callable`, nên `try-with-resources` bao trọn thao tác đọc và đóng. `boundedElastic` phù hợp cho công việc blocking có giới hạn; không nên chuyển mọi toán tử sang scheduler này nếu nguồn vốn đã non-blocking.

Nếu cần phát một luồng dài từ tài nguyên blocking, hãy dùng `using` để giữ tài nguyên theo subscription và bảo đảm cả thao tác đọc lẫn cleanup chạy ở scheduler phù hợp. Tránh tự tạo thread cho từng phần tử hoặc gọi blocking trong `map`/`doOnNext` trên event loop.

## 7. Kiểm thử việc giải phóng tài nguyên

Một kiểm thử tốt cần xác nhận tài nguyên được mở đúng số lần và cleanup chạy trên mọi đường kết thúc. Có thể dùng `AtomicInteger` để quan sát số lần acquire và release.

### Cleanup khi hoàn tất

```java
AtomicInteger opened = new AtomicInteger();
AtomicInteger closed = new AtomicInteger();

Flux<Integer> source = Flux.using(
    () -> {
        opened.incrementAndGet();
        return new Object();
    },
    resource -> Flux.just(1, 2, 3),
    resource -> closed.incrementAndGet()
);

StepVerifier.create(source)
    .expectNext(1, 2, 3)
    .verifyComplete();

assertThat(opened.get()).isEqualTo(1);
assertThat(closed.get()).isEqualTo(1);
```

### Cleanup khi lỗi

```java
AtomicInteger closed = new AtomicInteger();

Flux<Integer> source = Flux.using(
    Object::new,
    resource -> Flux.concat(
        Flux.just(1),
        Flux.error(new IllegalStateException("broken"))
    ),
    resource -> closed.incrementAndGet()
);

StepVerifier.create(source)
    .expectNext(1)
    .expectErrorMessage("broken")
    .verify();

assertThat(closed.get()).isEqualTo(1);
```

### Cleanup khi cancellation

```java
AtomicInteger closed = new AtomicInteger();

Flux<Integer> source = Flux.using(
    Object::new,
    resource -> Flux.<Integer>never(),
    resource -> closed.incrementAndGet()
);

StepVerifier.create(source)
    .expectSubscription()
    .thenCancel()
    .verify();

assertThat(closed.get()).isEqualTo(1);
```

### Cleanup bất đồng bộ với `usingWhen`

```java
AtomicInteger closed = new AtomicInteger();

Flux<Integer> source = Flux.usingWhen(
    Mono.fromSupplier(Object::new),
    resource -> Flux.just(1, 2),
    resource -> Mono.fromRunnable(closed::incrementAndGet),
    (resource, error) -> Mono.fromRunnable(closed::incrementAndGet),
    resource -> Mono.fromRunnable(closed::incrementAndGet)
);

StepVerifier.create(source)
    .expectNext(1, 2)
    .verifyComplete();

assertThat(closed.get()).isEqualTo(1);
```

Trong các ví dụ kiểm thử, cleanup được mô phỏng bằng `AtomicInteger`. Với cleanup thực, hãy kiểm tra cả Publisher cleanup hoàn tất, cleanup lỗi và cleanup có thể bị chậm. Nếu cleanup có thể lỗi, cần xác định lỗi đó được truyền xuống, ghi nhận hay xử lý theo chính sách nào.

Ngoài ra, nên kiểm thử nhiều subscription để xác nhận mỗi subscriber có tài nguyên riêng và mỗi tài nguyên chỉ được giải phóng một lần. Dùng `StepVerifier` để chủ động cancel thay vì chờ một nguồn vô hạn tự kết thúc.

## 8. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Mở tài nguyên khi lắp ráp pipeline | Tài nguyên có thể bị chia sẻ giữa subscriber hoặc mở quá sớm. | Tạo tài nguyên trong `using`/`usingWhen` khi subscribe. |
| Đóng tài nguyên trước khi Publisher được tiêu thụ | Downstream đọc trên tài nguyên đã đóng. | Để phạm vi quản lý bao trọn việc subscribe và tiêu thụ. |
| Chỉ cleanup trong `doOnComplete` | Cancellation hoặc error có thể bỏ sót cleanup. | Dùng `using` hoặc `usingWhen`. |
| Dùng `using` cho cleanup bất đồng bộ | Không chờ Publisher cleanup hoàn tất. | Dùng `usingWhen` với callback cleanup trả về Publisher. |
| Bỏ qua Publisher trả về từ hàm close async | Cleanup có thể không được subscribe nên tài nguyên chưa được giải phóng. | Trả Publisher cleanup cho `usingWhen` để Reactor điều phối. |
| Đặt fallback không cần tài nguyên bên trong resource scope | Giữ cursor/connection trong suốt thời gian fallback. | Đặt fallback bên ngoài `usingWhen` nếu không còn cần tài nguyên. |
| Thực hiện blocking cleanup trên event loop | Làm chậm các subscription khác. | Dùng API async hoặc điều phối blocking sang scheduler phù hợp. |
| Không kiểm thử đường cancellation | Rò rỉ chỉ xuất hiện khi client ngắt hoặc timeout. | Thêm kiểm thử cancel và xác minh cleanup. |

## 9. Checklist quản lý tài nguyên

Trước khi đưa pipeline vào production, hãy xác nhận:

- Tài nguyên được tạo khi subscribe, không bị mở sớm khi lắp ráp pipeline.
- Mỗi subscription có quyền sở hữu tài nguyên rõ ràng.
- Cleanup chạy khi complete, error và cancel.
- Dùng `using` cho cleanup đồng bộ, `usingWhen` cho cleanup bất đồng bộ.
- Cleanup async được trả về dưới dạng Publisher và được subscribe.
- Fallback không giữ tài nguyên không cần thiết trong lúc chạy.
- Blocking open/read/close không chạy trên event-loop thread.
- Lỗi trong cleanup có chính sách quan sát và xử lý rõ ràng.
- Kiểm thử có đường thành công, lỗi, cancellation, nhiều subscription và cleanup lỗi.

Quản lý tài nguyên đúng cách giúp pipeline `Mono`/`Flux` duy trì vòng đời rõ ràng ngay cả khi nguồn lỗi hoặc downstream hủy. `using` và `usingWhen` gắn việc mở và giải phóng với subscription, còn việc đặt fallback và scheduler đúng chỗ giúp tài nguyên được giữ đúng thời gian cần thiết mà không làm nghẽn các luồng xử lý khác.
