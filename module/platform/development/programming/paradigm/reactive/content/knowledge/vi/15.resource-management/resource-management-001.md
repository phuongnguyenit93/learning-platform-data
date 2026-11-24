# Gắn vòng đời tài nguyên với vòng đời của chuỗi xử lý

Một pipeline reactive có thể sử dụng nhiều tài nguyên bên ngoài: file, stream đọc dữ liệu, kết nối cơ sở dữ liệu, session, socket, cursor hoặc một lease được cấp từ dịch vụ khác. Những tài nguyên này cần được đóng hoặc giải phóng đúng lúc, kể cả khi pipeline hoàn tất bình thường, phát lỗi hay bị subscriber hủy.

Trong lập trình imperative, `try-with-resources` thường gắn việc đóng tài nguyên với phạm vi một khối lệnh. Với `Mono` và `Flux`, công việc có thể tiếp tục bất đồng bộ sau khi phương thức tạo publisher đã trả về. Vì vậy, phạm vi của phương thức không còn trùng với vòng đời xử lý. Cần gắn việc tạo và giải phóng tài nguyên trực tiếp với subscription và các tín hiệu kết thúc của publisher.

Bài học thuộc module `REACTIVE_PROGRAMMING`, nơi người học thực hành các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời sử dụng `Mono`, `Flux`, kết hợp operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Nội dung tập trung vào cách sở hữu tài nguyên trong pipeline, chọn `using` hay `usingWhen`, xử lý cancel và kiểm thử việc giải phóng.

## 1. Vì sao phạm vi tài nguyên phải theo subscription?

Publisher thường được xây dựng trước khi có subscriber. Nếu mở tài nguyên ngay lúc assembly, tài nguyên có thể được tạo từ lâu trước khi xử lý bắt đầu, bị dùng chung ngoài ý muốn hoặc không được đóng nếu publisher không bao giờ được subscribe.

Ví dụ không an toàn:

```java
Stream<String> lines = Files.lines(path);

Flux<String> content = Flux.fromStream(lines);
```

`Files.lines(path)` mở file ngay khi đoạn mã được chạy. Nếu không có subscriber, stream vẫn mở. Nếu nhiều subscriber cùng dùng publisher này, họ có thể cùng truy cập một `Stream`, trong khi Java Stream chỉ được tiêu thụ một lần và không được dùng lại sau khi đã đóng.

Thay vào đó, hãy tạo tài nguyên khi subscription bắt đầu và giải phóng nó khi subscription kết thúc:

```java
Flux<String> content = Flux.using(
    () -> Files.lines(path),
    Flux::fromStream,
    Stream::close
);
```

`Flux.using` quản lý tài nguyên theo từng subscription. Mỗi subscriber có một stream file riêng; Reactor gọi hàm cleanup khi luồng kết thúc hoặc bị hủy. Việc tạo publisher chưa mở file.

### Vòng đời cơ bản

```text
Assembly: tạo mô tả pipeline
             |
             v
Subscription bắt đầu
             |
             v
Resource supplier tạo tài nguyên
             |
             v
Resource closure tạo Publisher xử lý
             |
             v
       onNext ...
             |
       +-----+------+----------------+
       |            |                |
   onComplete    onError           cancel
       |            |                |
       +------------+----------------+
                    |
                    v
             Cleanup resource
```

Một subscription sở hữu tài nguyên mà nó tạo ra. Tài nguyên cần được giải phóng khi nhánh xử lý kết thúc theo mọi cách có thể. Đây là nguyên tắc quan trọng khi làm việc với publisher bất đồng bộ.

## 2. `using`: quản lý tài nguyên có cleanup đồng bộ

`Flux.using` và `Mono.using` phù hợp với tài nguyên có thao tác giải phóng đồng bộ, chẳng hạn `Stream`, reader, cursor hoặc một đối tượng triển khai `AutoCloseable`.

Về mặt khái niệm, `using` nhận ba hàm:

1. **Resource supplier:** tạo tài nguyên khi có subscription.
2. **Resource closure:** dùng tài nguyên để tạo `Publisher` phát kết quả.
3. **Cleanup consumer:** giải phóng tài nguyên sau khi xử lý kết thúc.

Ví dụ đọc file theo từng dòng:

```java
Flux<String> readLines(Path path) {
    return Flux.using(
        () -> Files.lines(path),
        Flux::fromStream,
        Stream::close
    ).subscribeOn(Schedulers.boundedElastic());
}
```

`Files.lines` và việc đọc từ stream là thao tác I/O có thể blocking. `subscribeOn(Schedulers.boundedElastic())` chuyển quá trình subscribe và công việc nguồn tương ứng sang scheduler phù hợp cho tác vụ blocking. Cleanup cũng thuộc vòng đời nguồn; hãy tránh chuyển phần đọc sang một luồng rồi đóng tài nguyên từ một nơi không được phối hợp với quá trình đọc.

### Tài nguyên được tạo riêng cho từng subscriber

```java
AtomicInteger opened = new AtomicInteger();
AtomicInteger closed = new AtomicInteger();

Flux<Integer> values = Flux.using(
    () -> {
        opened.incrementAndGet();
        return new StringReader("10\n20\n30");
    },
    reader -> Flux.generate(sink -> {
        try {
            int value = reader.read();
            if (value == -1) {
                sink.complete();
            } else {
                sink.next(value);
            }
        } catch (IOException error) {
            sink.error(error);
        }
    }),
    reader -> {
        try {
            reader.close();
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        } finally {
            closed.incrementAndGet();
        }
    }
);
```

Mỗi lần `values.subscribe(...)` tạo một `StringReader` mới, đọc nội dung theo demand và cleanup reader tương ứng. Hai lần đăng ký tạo hai vòng đời tài nguyên độc lập. `Flux.generate` chỉ đọc thêm một ký tự khi downstream yêu cầu phần tử tiếp theo.

### Cleanup mặc định và chế độ eager

`using` có overload cho phép chỉ định `eager`. Với chế độ eager, cleanup được thực hiện trước khi tín hiệu kết thúc được chuyển xuống subscriber. Đây là hành vi mặc định của overload thông dụng. Khi đặt `eager` là `false`, terminal signal được chuyển trước rồi cleanup được thực hiện sau đó.

Thông thường nên giữ cleanup eager để subscriber chỉ quan sát việc hoàn tất sau khi tài nguyên đã được giải phóng. Nếu cleanup ném exception, cần hiểu rằng lỗi cleanup có thể ảnh hưởng đến tín hiệu kết thúc; hãy ghi log và xử lý theo chính sách lỗi của ứng dụng.

### Khi nào dùng `using`?

- Tài nguyên được tạo bằng một lời gọi đồng bộ.
- Việc đóng tài nguyên là thao tác đồng bộ như `close()`.
- Một subscription sở hữu một instance tài nguyên riêng.
- Có thể biểu diễn toàn bộ công việc sử dụng tài nguyên thành một `Mono` hoặc `Flux`.

Nếu thao tác cleanup là bất đồng bộ và trả về `Publisher`, hãy cân nhắc `usingWhen`.

## 3. `usingWhen`: quản lý cleanup bất đồng bộ

Một số tài nguyên cần được giải phóng bằng thao tác reactive: kết nối R2DBC, session từ client bất đồng bộ, lease phân tán hoặc tài nguyên phải gửi yêu cầu mạng để đóng. Không nên gọi một hàm cleanup bất đồng bộ rồi bỏ qua publisher mà nó trả về; nếu làm vậy, Reactor không thể phối hợp vòng đời cleanup với terminal signal.

`usingWhen` nhận publisher tạo tài nguyên, hàm sử dụng tài nguyên và các hàm cleanup riêng cho ba trường hợp:

- Hoàn tất bình thường (`onComplete`).
- Xử lý lỗi (`onError`).
- Subscriber hủy (`cancel`).

Ví dụ với một session bất đồng bộ:

```java
interface AsyncSession {
    Mono<String> fetch(String key);
    Mono<Void> release();
}

Mono<String> load(String key) {
    return Mono.usingWhen(
        sessionFactory.open(),
        session -> session.fetch(key),
        AsyncSession::release,
        (session, error) -> session.release(),
        AsyncSession::release
    );
}
```

`sessionFactory.open()` trả về publisher tạo session. Resource closure sử dụng session để tải dữ liệu. `release()` trả về `Mono<Void>` nên Reactor có thể điều phối thao tác giải phóng trong cả ba nhánh. Với complete và error, tín hiệu kết thúc downstream được phát sau khi cleanup hoàn tất; với cancel, cleanup được đăng ký và thực thi dù subscriber đã yêu cầu hủy.

Trong hệ thống thật, cleanup theo từng nhánh có thể khác nhau. Ví dụ với transaction, nhánh complete cần commit rồi đóng connection; nhánh error và cancel cần rollback rồi đóng connection. Hãy biểu diễn toàn bộ chuỗi thao tác bằng publisher và bảo đảm việc đóng tài nguyên vẫn được thực hiện nếu commit hoặc rollback thất bại.

### Phân biệt cleanup đồng bộ và bất đồng bộ

| Tiêu chí | `using` | `usingWhen` |
|---|---|---|
| Tạo tài nguyên | Supplier đồng bộ khi subscribe. | Publisher tạo tài nguyên khi subscribe. |
| Dùng tài nguyên | Trả về `Publisher` từ resource closure. | Trả về `Publisher` từ resource closure. |
| Cleanup | `Consumer` đồng bộ. | Các hàm cleanup trả về `Publisher`. |
| Nhánh kết thúc | Một hàm cleanup chung. | Có thể định nghĩa riêng complete, error và cancel. |
| Ví dụ | `Stream`, reader, cursor đồng bộ. | Session reactive, lease bất đồng bộ, connection R2DBC. |

Nếu cleanup cần thực hiện nhiều bước bất đồng bộ, `usingWhen` cho phép kết hợp chúng bằng `then`, `onErrorResume` và các operator khác. Cleanup publisher cũng có thể phát lỗi; đừng giả định việc đóng tài nguyên luôn thành công.

## 4. Hủy subscription cũng phải giải phóng tài nguyên

Một lỗi thường gặp là chỉ đóng tài nguyên trong nhánh hoàn tất hoặc lỗi. Nhưng một subscriber có thể rời đi trước khi nguồn kết thúc bằng cách gọi `cancel()` hoặc dispose `Disposable`.

Ví dụ, một endpoint HTTP có thể bị client ngắt kết nối trong lúc đang đọc file hoặc truy vấn dữ liệu. Nếu tài nguyên chỉ được đóng trong `onComplete`, connection hoặc file descriptor có thể bị giữ lại.

Với `using`, cleanup được gọi khi subscription bị cancel. Với `usingWhen`, nhánh cleanup dành riêng cho cancel được chạy và publisher cleanup được Reactor phối hợp trong vòng đời kết thúc.

```java
Flux<Long> ticks = Flux.using(
    () -> openSubscriptionLease(),
    lease -> Flux.interval(Duration.ofSeconds(1))
        .map(ignored -> lease.nextValue()),
    SubscriptionLease::close
);
```

Nếu downstream hủy `ticks`, lease được đóng. Đây là điều cần thiết với nguồn dài hạn như WebSocket, message listener hoặc stream cảm biến: subscription có thể tồn tại lâu và không tự hoàn tất.

### Cancel không phải terminal signal

`cancel()` là yêu cầu điều khiển từ subscriber. Publisher không gửi `onComplete` chỉ để xác nhận việc hủy. Vì thế, cleanup không được phụ thuộc duy nhất vào callback quan sát `onComplete`.

`doOnTerminate` chạy khi complete hoặc error nhưng không bao gồm cancel. `doFinally` quan sát complete, error và cancel, nên hữu ích để ghi metric hoặc thực hiện side effect đồng bộ sau khi subscription kết thúc. Tuy nhiên, `doFinally` không nhận publisher cleanup và không phải công cụ thay thế `using`/`usingWhen` cho việc quản lý tài nguyên bất đồng bộ.

## 5. Không mở tài nguyên trước khi pipeline được subscribe

Hãy tránh tạo tài nguyên ở bên ngoài resource supplier:

```java
// Không nên: mở file ngay khi xây dựng publisher.
Stream<String> stream = Files.lines(path);
Flux<String> unsafe = Flux.fromStream(stream);
```

Tạo tài nguyên bên trong resource supplier. `using` vừa trì hoãn việc mở file đến lúc subscribe, vừa gắn cleanup với vòng đời của publisher:

```java
Flux<String> safe = Flux.using(
    () -> Files.lines(path),
    Flux::fromStream,
    Stream::close
);
```

`defer` cũng có thể trì hoãn một phép tạo tài nguyên, nhưng bản thân nó không định nghĩa cleanup. Nếu dùng `defer`, vẫn phải kết hợp với `using` hoặc `usingWhen` để bảo đảm tài nguyên được giải phóng khi complete, error và cancel. `doFinally` có thể quan sát cancel và terminal signal, nhưng callback của nó không thể trả về publisher cleanup bất đồng bộ; exception phát sinh trong callback cũng không phải cơ chế đáng tin cậy để báo lỗi cleanup cho subscriber.

Không gọi `subscribe()` bên trong resource closure để chạy một tác vụ độc lập rồi trả về ngay. Khi đó, publisher bên ngoài có thể hoàn tất và đóng tài nguyên trước khi tác vụ con hoàn tất. Hãy trả về publisher con để nó trở thành một phần của chuỗi xử lý:

```java
Mono<Result> safe = Mono.usingWhen(
    sessionFactory.open(),
    session -> session.execute(command),
    AsyncSession::release,
    (session, error) -> session.release(),
    AsyncSession::release
);
```

Reactor chỉ quản lý được vòng đời của công việc nằm trong publisher được trả về. Tác vụ fire-and-forget được subscribe riêng nằm ngoài chuỗi ownership đó.

## 6. Tài nguyên và các operator chia sẻ nguồn

Resource supplier của `using` hoặc `usingWhen` chạy theo subscription upstream. Nếu publisher được chia sẻ bằng `share`, `publish().refCount()` hoặc `cache`, nhiều subscriber downstream có thể dùng chung một subscription upstream và do đó dùng chung một tài nguyên.

Ví dụ:

```java
Flux<Event> shared = Flux.using(
    this::openEventStream,
    EventStream::events,
    EventStream::close
).share();
```

Khi subscriber đầu tiên đến, nguồn upstream được subscribe và mở một event stream. Các subscriber cùng tham gia có thể nhận dữ liệu từ cùng stream đó. Hủy một subscriber không nhất thiết đóng tài nguyên nếu vẫn còn subscriber khác và chính sách chia sẻ giữ upstream hoạt động. Khi upstream được ngắt hoặc kết thúc, cleanup mới chạy.

Với `cache`, tài nguyên được giữ trong lúc upstream nạp dữ liệu. Khi upstream kết thúc, cleanup chạy; subscriber đến sau nhận tín hiệu đã cache và không mở lại tài nguyên nếu cache vẫn còn hiệu lực. Điều này có thể phù hợp với kết quả hữu hạn, nhưng không phù hợp nếu muốn một nguồn live được mở mới cho mỗi người quan sát.

Hãy xác định rõ phạm vi ownership:

- Tài nguyên riêng cho mỗi subscriber: giữ nguồn cold và không chia sẻ subscription upstream.
- Một tài nguyên dùng chung cho nhiều subscriber đồng thời: chia sẻ upstream và quy định khi nào subscriber cuối cùng rời đi thì nguồn được đóng.
- Kết quả được lưu để phát lại: cache/replay và quy định TTL, giới hạn bộ nhớ cùng vòng đời dữ liệu.

Không giả định mỗi lần gọi `subscribe` luôn mở một tài nguyên mới. Operator chia sẻ có thể thay đổi số lần subscription upstream.

## 7. Tài nguyên dài hạn và nguồn không hoàn tất

Một `Flux` có thể không bao giờ phát `onComplete`, chẳng hạn nguồn WebSocket hoặc luồng sự kiện liên tục. Khi đó, tài nguyên gắn với subscription sẽ được giữ cho đến khi có lỗi hoặc subscriber hủy.

Điều này không phải rò rỉ nếu subscription vẫn còn hoạt động và tài nguyên vẫn cần thiết. Nhưng nếu subscriber bị mất mà không cancel, tài nguyên có thể bị giữ lâu hơn dự kiến.

Với nguồn dài hạn, cần thiết kế:

- Hủy subscription khi client rời đi hoặc khi service dừng.
- Timeout hoặc heartbeat nếu nguồn cần phát hiện kết nối mất.
- Giải phóng listener, socket, timer và connection trong cleanup.
- Không tạo subscription phụ mà không giữ `Disposable` hoặc không có cơ chế cancel.
- Giới hạn buffer và prefetch để nguồn chậm không giữ lượng dữ liệu vô hạn.
- Theo dõi số tài nguyên đang mở, thời gian sống subscription và số lần cleanup lỗi.

Nếu ứng dụng sở hữu một subscription lâu dài ở tầng service, hãy lưu handle của subscription và hủy nó trong lifecycle shutdown của service. Tránh tạo tài nguyên trong một bean singleton rồi để từng request sử dụng mà không có quy tắc chia sẻ rõ ràng.

## 8. Xử lý lỗi trong lúc sử dụng và giải phóng tài nguyên

Có ít nhất ba nguồn lỗi cần xem xét:

1. **Lỗi tạo tài nguyên:** resource supplier hoặc publisher acquisition thất bại. Khi không tạo được tài nguyên, không có instance để cleanup.
2. **Lỗi trong resource closure:** truy vấn, đọc file hoặc xử lý dữ liệu phát `onError`. Cleanup vẫn phải được thực hiện cho tài nguyên đã tạo.
3. **Lỗi cleanup:** thao tác đóng hoặc release thất bại. Lỗi này có thể ảnh hưởng đến terminal signal cuối cùng.

Với `using`, cleanup là một `Consumer`, nên lỗi cleanup được ném đồng bộ. Với `usingWhen`, cleanup trả về publisher nên có thể thất bại bất đồng bộ. Hãy quyết định cách ghi log, giữ lỗi gốc, thêm lỗi cleanup làm suppressed exception hoặc chuyển lỗi cleanup thành lỗi vận hành theo chính sách ứng dụng.

Ví dụ xử lý lỗi rollback nhưng vẫn cố gắng đóng session:

```java
Mono<Void> rollbackAndClose(AsyncSession session) {
    return session.rollback()
        .onErrorResume(rollbackError -> {
            log.warn("Rollback failed", rollbackError);
            return Mono.empty();
        })
        .then(session.release());
}
```

Trong nhánh error của `usingWhen`, có thể gọi hàm cleanup như trên. Nếu rollback thất bại, publisher vẫn tiếp tục đến bước release. Hãy cân nhắc cách giữ lại lỗi rollback để phục vụ điều tra, đặc biệt khi một lỗi xử lý ban đầu đã xảy ra.

Không nên dùng `onErrorResume(error -> Mono.empty())` một cách rộng rãi quanh toàn bộ pipeline chỉ để đảm bảo cleanup. Cách đó có thể biến lỗi nghiệp vụ thành hoàn tất bình thường và che giấu việc dữ liệu chưa được xử lý.

## 9. Kiểm thử việc giải phóng tài nguyên

Kiểm thử không chỉ xác minh dữ liệu đầu ra; cần xác minh cleanup chạy đúng khi complete, error và cancel.

Ví dụ kiểm tra cleanup khi cancel:

```java
AtomicBoolean closed = new AtomicBoolean();

Flux<Long> source = Flux.using(
    () -> new SubscriptionLease(closed),
    lease -> Flux.interval(Duration.ofSeconds(1)),
    SubscriptionLease::close
);

StepVerifier.withVirtualTime(() -> source)
    .thenCancel()
    .verify();

assertTrue(closed.get());
```

Giả sử `SubscriptionLease.close()` đặt cờ `closed` thành `true`. Bài kiểm thử xác minh rằng khi subscription bị cancel, cleanup đồng bộ đã được gọi.

Với cleanup bất đồng bộ, hãy xác minh terminal signal chỉ xuất hiện sau khi publisher cleanup hoàn tất:

```java
AtomicBoolean released = new AtomicBoolean();

Mono<String> source = Mono.usingWhen(
    Mono.just(new AsyncLease(released)),
    lease -> Mono.just("done"),
    AsyncLease::release,
    (lease, error) -> lease.release(),
    AsyncLease::release
);

StepVerifier.create(source)
    .expectNext("done")
    .verifyComplete();

assertTrue(released.get());
```

Ví dụ giả định `AsyncLease.release()` trả về `Mono<Void>` và chỉ đặt cờ sau khi thao tác release hoàn tất. Trong dự án thật, nên kiểm thử thêm khi acquisition lỗi, resource closure lỗi, cleanup lỗi, rollback lỗi và cancel xảy ra khi cleanup bất đồng bộ đang chạy.

Một bộ kiểm thử vòng đời nên bao gồm:

- Hoàn tất bình thường: tài nguyên được đóng đúng một lần.
- Nguồn phát lỗi: tài nguyên vẫn được đóng.
- Subscriber cancel: tài nguyên được đóng dù không có `onComplete`.
- Acquisition lỗi hoặc rỗng: không gọi cleanup trên tài nguyên không tồn tại.
- Cleanup bất đồng bộ: kết quả terminal tuân theo kết quả cleanup.
- Nhiều subscriber: số tài nguyên mở phù hợp với cold/shared semantics.
- Retry: mỗi lần subscription mới tạo và giải phóng đúng instance tài nguyên.
- Nguồn dài hạn: tài nguyên còn mở khi subscription hoạt động và được đóng khi cancel.

## 10. Tình huống thực tế: quản lý session khi xử lý yêu cầu

Một dịch vụ cần mở session đến hệ thống tìm kiếm, truy vấn dữ liệu rồi giải phóng session. Session được cấp bất đồng bộ và thao tác đóng cũng trả về `Mono<Void>`.

```java
Mono<SearchResult> search(String query) {
    return Mono.usingWhen(
        searchSessionFactory.open(),
        session -> session.search(query),
        SearchSession::close,
        (session, error) -> session.abort()
            .onErrorResume(abortError -> {
                log.warn("Session abort failed", abortError);
                return Mono.empty();
            })
            .then(session.close()),
        session -> session.cancel()
            .onErrorResume(cancelError -> {
                log.warn("Session cancellation failed", cancelError);
                return Mono.empty();
            })
            .then(session.close())
    );
}
```

Nhánh complete đóng session bình thường. Nhánh error hủy thao tác dang dở rồi đóng session. Nhánh cancel gửi tín hiệu hủy đến session rồi đóng. Các phương thức `abort`, `cancel` và `close` ở ví dụ là API minh họa; trong ứng dụng thực tế, cần dùng đúng giao thức của client và bảo đảm close vẫn được gọi nếu bước abort/cancel thất bại.

Nếu truy vấn có thể chạy lâu, client HTTP có thể ngắt kết nối trước khi truy vấn hoàn tất. Khi subscription downstream bị cancel, `usingWhen` chạy nhánh cleanup cancel, giúp session được thu hồi. Không cần đợi truy vấn tự hoàn tất mới giải phóng tài nguyên.

## 11. Checklist thiết kế ownership tài nguyên

- Tạo tài nguyên bên trong resource supplier hoặc `defer`, không mở ở assembly time.
- Xác định một subscription sở hữu tài nguyên nào và ai có quyền đóng nó.
- Dùng `using` cho cleanup đồng bộ; dùng `usingWhen` cho acquisition/cleanup bất đồng bộ.
- Định nghĩa cleanup cho complete, error và cancel.
- Trả về publisher từ resource closure; không gọi `subscribe()` fire-and-forget bên trong.
- Đưa blocking I/O lên scheduler phù hợp như `boundedElastic`.
- Hiểu operator `share`, `refCount` và `cache` thay đổi số subscription upstream và phạm vi tài nguyên ra sao.
- Với nguồn dài hạn, lưu handle subscription và hủy khi client rời đi hoặc service shutdown.
- Quy định cách xử lý lỗi cleanup và cách giữ lỗi gốc.
- Kiểm thử cleanup trên complete, error, cancel, retry và nhiều subscriber.
- Theo dõi số tài nguyên đang mở, thời gian sống và lỗi giải phóng.

Khi tài nguyên được tạo và giải phóng trong cùng một phạm vi subscription, pipeline có thể xử lý bất đồng bộ mà vẫn giữ ownership rõ ràng. `using` phù hợp với tài nguyên có cleanup đồng bộ; `usingWhen` phối hợp các thao tác cleanup bất đồng bộ theo từng nhánh kết thúc. Kết hợp hai công cụ này với cancel, scheduler và kiểm thử vòng đời giúp tránh rò rỉ file descriptor, connection, session và các tài nguyên ngoài bộ nhớ heap.
