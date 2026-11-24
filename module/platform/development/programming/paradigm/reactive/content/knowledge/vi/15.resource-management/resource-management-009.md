# Kiểm tra không rò rỉ tệp, kết nối và bộ lắng nghe

Một pipeline reactive có thể chạy trong thời gian dài, được đăng ký nhiều lần hoặc bị hủy giữa chừng. Mỗi subscription có thể mở tệp, mượn kết nối từ connection pool hoặc đăng ký một listener nhận sự kiện. Nếu tài nguyên không được giải phóng khi pipeline hoàn tất, phát lỗi hoặc bị hủy, ứng dụng có thể dần cạn file descriptor, cạn kết nối hoặc tiếp tục nhận sự kiện sau khi không còn người tiêu thụ.

Kiểm tra rò rỉ tài nguyên vì vậy cần xem toàn bộ vòng đời subscription, bao gồm cả những đường kết thúc bất thường. Project Reactor cung cấp `using` và `usingWhen` để gắn việc cấp phát tài nguyên với việc tiêu thụ Publisher; các công cụ kiểm thử và metrics giúp xác nhận rằng tài nguyên được đóng đúng số lần và đúng thời điểm.

Bài học thuộc chương **Tài nguyên** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; nội dung dưới đây kết nối vòng đời Publisher–Subscriber với Mono, Flux, scheduler, xử lý lỗi và kiểm thử pipeline Java.

Các đoạn mã sử dụng Project Reactor. Những tên như eventBus, connectionFactory, Session hoặc logger đại diện cho thành phần của ứng dụng; hãy thay bằng API thực tế của dự án và bổ sung import tương ứng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện tài nguyên cần được đóng hoặc hủy theo từng subscription.
- Giải thích vì sao `try-with-resources` thông thường không phù hợp khi Publisher chỉ được tiêu thụ sau khi phương thức đã trả về.
- Dùng `Flux.using` hoặc `Mono.using` cho tài nguyên có thao tác giải phóng đồng bộ.
- Dùng `usingWhen` cho tài nguyên cần giải phóng bất đồng bộ khi complete, error hoặc cancel.
- Thiết kế cleanup an toàn cho tệp, kết nối và listener, kể cả khi bước xử lý lỗi.
- Viết kiểm thử cho các đường kết thúc và theo dõi metrics để phát hiện rò rỉ trong vận hành.

## 1. Tài nguyên phải sống cùng subscription

Trong mã đồng bộ, vòng đời tài nguyên thường được thể hiện bằng một khối `try/finally` hoặc `try-with-resources`:

~~~java
try (var input = Files.newInputStream(path)) {
    return input.readAllBytes();
}
~~~

Tệp được mở, đọc và đóng trong cùng một lần gọi phương thức. Khi phương thức kết thúc, tài nguyên đã được giải phóng.

Publisher reactive hoạt động lười. Việc xây dựng một `Flux` hoặc `Mono` thường chỉ mô tả công việc; việc đọc dữ liệu và phát tín hiệu bắt đầu khi có subscriber. Do đó, đoạn mã sau có lỗi vòng đời:

~~~java
Flux<String> lines;

try (Stream<String> fileLines = Files.lines(path)) {
    lines = Flux.fromStream(fileLines);
}

return lines;
~~~

Khối `try` kết thúc ngay sau khi tạo Publisher. Stream của tệp đã bị đóng trước khi subscriber tiêu thụ `lines`. Nếu cố giữ Stream mở bên ngoài, ứng dụng lại phải tự xác định subscriber nào sở hữu nó và khi nào đóng, kể cả khi có nhiều subscription hoặc cancellation.

Cách phù hợp là cấp phát tài nguyên khi subscription bắt đầu và gắn thao tác giải phóng với vòng đời của Publisher. Khi đó mỗi subscription có phạm vi tài nguyên riêng, và cleanup được thực hiện khi đường tiêu thụ kết thúc theo hợp đồng.

Những tài nguyên thường cần quản lý:

| Tài nguyên | Cấp phát | Giải phóng |
|---|---|---|
| Tệp hoặc stream đọc tệp | Mở file descriptor, tạo input stream | Đóng stream hoặc channel |
| Kết nối cơ sở dữ liệu | Mượn connection từ pool hoặc mở connection | Trả connection về pool hoặc đóng |
| Listener | Đăng ký callback với event bus, socket hoặc SDK | Hủy đăng ký và ngừng nhận callback |
| Cursor hoặc result set | Mở cursor khi truy vấn | Đóng cursor và giải phóng statement |
| Session hoặc transaction | Bắt đầu session/transaction | Commit hoặc rollback, sau đó đóng |
| Tài nguyên hệ điều hành | Mở socket, channel, process handle | Đóng hoặc dừng tài nguyên tương ứng |

Điểm cần xác định trước khi viết pipeline là **ai sở hữu tài nguyên**. Nếu một tài nguyên được chia sẻ giữa nhiều subscriber, một subscriber hủy không được tùy tiện đóng tài nguyên mà các subscriber khác vẫn cần. Trong trường hợp đó, cần một chủ sở hữu ở tầng cao hơn, cơ chế reference counting hoặc một vòng đời chia sẻ được thiết kế rõ ràng.

## 2. `using`: cấp phát và đóng tài nguyên đồng bộ

`Flux.using` và `Mono.using` nhận ba thành phần:

1. Resource supplier: tạo tài nguyên cho subscription.
2. Resource closure: tạo Publisher sử dụng tài nguyên đó.
3. Cleanup: giải phóng tài nguyên khi quá trình tiêu thụ kết thúc.

Ví dụ với một tệp:

~~~java
Flux<String> readLines(Path path) {
    return Flux.using(
        () -> {
            try {
                return Files.lines(path);
            } catch (IOException error) {
                throw new UncheckedIOException(error);
            }
        },
        Flux::fromStream,
        Stream::close
    );
}
~~~

Mỗi lần subscribe, supplier mở một Stream mới. Resource closure chuyển Stream thành Flux để các dòng được phát theo nhu cầu. Khi nguồn hoàn tất, phát lỗi hoặc bị hủy, cleanup gọi `Stream.close()`.

Cách này phù hợp với tài nguyên có thao tác đóng đồng bộ, nhanh và không cần chờ một Publisher khác hoàn tất. Có thể dùng cùng mẫu cho input stream, cursor hoặc một handle có phương thức `close()`.

### Kiểm tra tài nguyên được mở và đóng đúng số lần

Có thể bọc tài nguyên bằng một lớp theo dõi số lần đóng:

~~~java
final class TrackedHandle implements AutoCloseable {
    private final AtomicInteger closeCount;

    TrackedHandle(AtomicInteger closeCount) {
        this.closeCount = closeCount;
    }

    @Override
    public void close() {
        closeCount.incrementAndGet();
    }
}
~~~

Một pipeline dùng handle đó:

~~~java
AtomicInteger closeCount = new AtomicInteger();

Flux<String> source = Flux.using(
    () -> new TrackedHandle(closeCount),
    handle -> Flux.just("one", "two"),
    TrackedHandle::close
);
~~~

Kiểm thử hoàn tất:

~~~java
StepVerifier.create(source)
    .expectNext("one", "two")
    .verifyComplete();

assertEquals(1, closeCount.get());
~~~

Kiểm thử xác nhận cleanup được gọi một lần sau khi subscription hoàn tất. Nếu cùng Publisher được đăng ký hai lần, supplier tạo hai handle khác nhau và mỗi handle cần được đóng một lần. Vì vậy, không nên tạo tài nguyên bên ngoài supplier rồi chia sẻ ngầm cho nhiều subscription.

### Kiểm tra đường hủy

Nguồn có thể không bao giờ hoàn tất tự nhiên. Ví dụ, một listener hoặc luồng sự kiện có thể chạy đến khi người dùng rời màn hình. Cleanup vẫn phải chạy khi subscriber hủy:

~~~java
AtomicInteger closeCount = new AtomicInteger();

Flux<String> source = Flux.using(
    () -> new TrackedHandle(closeCount),
    handle -> Flux.concat(
        Flux.just("connected"),
        Flux.never()
    ),
    TrackedHandle::close
);

StepVerifier.create(source)
    .expectNext("connected")
    .thenCancel()
    .verify();

assertEquals(1, closeCount.get());
~~~

Sau khi nhận `connected`, StepVerifier hủy subscription. `using` gọi cleanup để đóng handle. Đây là kiểu kiểm thử quan trọng với listener, socket và stream dài hạn vì những nguồn này thường không phát `onComplete` trong hoạt động bình thường.

## 3. `usingWhen`: giải phóng tài nguyên bất đồng bộ

Một số thao tác cleanup cũng là bất đồng bộ. Ví dụ, đóng một session từ xa, trả connection qua driver reactive hoặc rollback transaction có thể trả về `Mono<Void>` hay một Publisher khác. Không thể gọi cleanup đồng bộ rồi giả định tài nguyên đã được giải phóng ngay.

`usingWhen` gắn cleanup Publisher với ba đường kết thúc riêng:

- Async complete: khi resource closure hoàn tất bình thường.
- Async error: khi resource closure phát lỗi.
- Async cancel: khi subscriber hủy subscription.

Ví dụ minh họa một transaction reactive:

~~~java
Mono<Customer> customer =
    Mono.usingWhen(
        transactionFactory.begin(),
        transaction -> transaction.findCustomer(customerId),
        transaction -> transaction.commitAndClose(),
        (transaction, error) -> transaction.rollbackAndClose(),
        transaction -> transaction.rollbackAndClose()
    );
~~~

Giả sử `begin()` trả về `Mono<Transaction>`, còn các phương thức cleanup trả về `Mono<Void>`:

- Nếu truy vấn thành công, `commitAndClose()` commit rồi đóng transaction.
- Nếu truy vấn phát lỗi, `rollbackAndClose()` rollback rồi đóng.
- Nếu subscriber hủy, callback cancel cũng rollback rồi đóng.

Trong ứng dụng thực tế, các phương thức `commitAndClose` và `rollbackAndClose` cần bảo đảm vẫn thử đóng tài nguyên nếu commit hoặc rollback thất bại. Không nên viết cleanup theo kiểu `rollback().then(close())` mà không xem xét lỗi rollback: nếu rollback phát lỗi, `then` sẽ không chạy và connection có thể bị giữ lại. Hãy đóng trong nhánh lỗi hoặc đóng bằng một helper bảo đảm cleanup cuối cùng luôn được thử; đồng thời ghi nhận lỗi cleanup để điều tra.

### Chọn `using` hay `usingWhen`?

| Tiêu chí | `using` | `usingWhen` |
|---|---|---|
| Cleanup | Consumer đồng bộ | Publisher cleanup bất đồng bộ |
| Complete | Gọi cleanup khi nguồn kết thúc | Chạy callback async complete |
| Error | Gọi cleanup khi nguồn lỗi | Chạy callback async error |
| Cancel | Gọi cleanup khi bị hủy | Chạy callback async cancel |
| Ví dụ | `Stream.close()`, `InputStream.close()` | Đóng session reactive, trả connection bất đồng bộ, rollback transaction |
| Cần chờ cleanup Publisher | Không | Có, theo cơ chế cleanup của toán tử |

Nếu thao tác đóng có thể chặn đáng kể, không nên thực hiện nó trên event loop. Với cleanup đồng bộ nhưng có khả năng chặn, cân nhắc chuyển việc đóng sang scheduler phù hợp hoặc bọc nó trong một Publisher cleanup của `usingWhen` và chạy trên `Schedulers.boundedElastic()`.

Ví dụ:

~~~java
Mono<Void> closeOffEventLoop(AutoCloseable resource) {
    return Mono.fromRunnable(() -> {
        try {
            resource.close();
        } catch (Exception error) {
            throw new IllegalStateException("Không thể đóng tài nguyên", error);
        }
    }).subscribeOn(Schedulers.boundedElastic());
}
~~~

Hàm này minh họa cách biến thao tác đóng đồng bộ thành Publisher để có thể chờ trong cleanup bất đồng bộ. Cần giữ nguyên nguyên nhân lỗi và ghi log phù hợp; không nên bỏ qua lỗi đóng chỉ để pipeline có vẻ hoàn tất thành công.

## 4. Tệp: kiểm tra file descriptor và Stream

Tệp là một nguồn rò rỉ phổ biến vì mỗi lần mở có thể giữ file descriptor, bộ đệm hoặc khóa hệ điều hành. Những lỗi thường gặp:

- Mở tệp khi xây dựng Publisher thay vì khi subscribe.
- Không đóng Stream khi subscriber hủy giữa lúc đọc.
- Dùng lại một Java Stream đã tiêu thụ hoặc đã đóng cho subscription tiếp theo.
- Tạo nhiều subscription nhưng chỉ đóng tài nguyên sau subscription cuối cùng theo một logic không an toàn.
- Nuốt lỗi đọc hoặc lỗi đóng, khiến việc kiểm tra không nhận ra tài nguyên bị kẹt.

Mẫu `Flux.using` ở phần trước xử lý việc cấp phát theo subscription. Để kiểm tra trong ứng dụng:

1. Đếm số lần mở và đóng ở lớp wrapper hoặc adapter sở hữu tệp.
2. Kiểm thử đọc hết tệp, tệp rỗng, lỗi đọc và hủy sau một vài dòng.
3. Đăng ký lặp lại để xác nhận mỗi lượt có Stream riêng.
4. Quan sát số file descriptor đang mở ở cấp tiến trình trong kiểm thử tích hợp hoặc môi trường vận hành.
5. Kiểm tra file có thể được đổi tên, xóa hoặc mở lại sau khi subscription kết thúc, đặc biệt trên hệ điều hành giữ khóa tệp.

Một bài kiểm thử tích hợp có thể tạo tệp tạm, tiêu thụ một phần rồi hủy, sau đó thử mở lại hoặc xóa tệp. Cách này xác nhận hành vi của file handle thực tế thay vì chỉ xác nhận một bộ đếm giả lập.

## 5. Kết nối cơ sở dữ liệu: trả connection về pool trên mọi đường kết thúc

Khi dùng driver reactive, connection thường được mượn từ pool và cần được trả lại. Không trả connection sau complete, error hoặc cancel có thể làm số connection đang sử dụng tăng dần cho đến khi request mới phải chờ hoặc timeout.

Ví dụ minh họa quản lý một session reactive:

~~~java
Mono<Customer> loadCustomer(String customerId) {
    return Mono.usingWhen(
        connectionFactory.openSession(),
        session -> session.findCustomer(customerId),
        session -> session.close(),
        (session, error) -> session.close(),
        session -> session.close()
    );
}
~~~

`openSession()` trả về `Mono<Session>`; `findCustomer` trả về `Mono<Customer>`; `close()` trả về `Mono<Void>`. Tài nguyên được tạo khi có subscription và cleanup được thực hiện ở cả ba đường kết thúc.

Nếu session đại diện cho transaction, cleanup có thể cần commit khi thành công và rollback khi lỗi hoặc hủy. Hãy tách các chính sách đó như ví dụ `commitAndClose` / `rollbackAndClose`, đồng thời bảo đảm đóng session ngay cả khi thao tác transaction thất bại.

### Metrics giúp phát hiện rò rỉ connection

Theo dõi các chỉ số của connection pool theo thời gian:

- **Active connections:** số connection đang được mượn.
- **Idle connections:** số connection sẵn sàng được mượn.
- **Pending acquire:** số yêu cầu đang chờ connection.
- **Acquire latency:** thời gian chờ để lấy connection.
- **Acquire timeout và lỗi đóng:** số lần không lấy được connection hoặc cleanup thất bại.
- **Usage duration:** thời gian một connection nằm trong tay subscriber.

Nếu số connection active tăng liên tục nhưng không giảm sau khi tải kết thúc, cần kiểm tra những subscription chưa kết thúc hoặc nhánh cleanup không được gọi. Nếu active ổn định nhưng pending tăng, nguyên nhân cũng có thể là tải vượt năng lực pool; cần đối chiếu throughput và thời gian truy vấn trước khi kết luận có rò rỉ.

Không nên tăng kích thước pool để che giấu việc không trả connection. Hãy xác nhận mọi đường complete, error và cancel đều có cleanup, sau đó mới điều chỉnh pool theo tải thực tế.

## 6. Listener: hủy đăng ký khi subscriber rời đi

Listener thường được đăng ký với event bus hoặc SDK bên ngoài. Nếu không hủy đăng ký, callback vẫn có thể giữ tham chiếu đến subscriber, service hoặc UI đã không còn sử dụng. Điều này vừa gây rò rỉ bộ nhớ vừa khiến ứng dụng tiếp tục xử lý sự kiện không cần thiết.

Có thể biểu diễn đăng ký listener như một tài nguyên:

~~~java
Flux<Event> events =
    Flux.using(
        () -> eventBus.register(listener),
        registration -> registration.events(),
        Registration::close
    );
~~~

Giả sử `register` trả về một Registration có phương thức `events()` để chuyển sự kiện và `close()` để hủy đăng ký. Khi subscriber hủy hoặc nguồn kết thúc, Registration được đóng.

Một số SDK trả về handle như `Disposable`, `Cancellable` hoặc `AutoCloseable`. Hãy bọc handle đó thành resource của `using`, rồi gọi đúng phương thức dispose/cancel/removeListener trong cleanup.

Nếu API đăng ký listener tự phát callback và không cung cấp Publisher, có thể tạo adapter bằng `Flux.create`. Khi đó cần gắn việc hủy đăng ký với lifecycle của sink:

~~~java
Flux<Event> events = Flux.create(sink -> {
    Registration registration =
        eventBus.register(sink::next);

    sink.onDispose(registration::close);
});
~~~

Ví dụ adapter này cần bổ sung xử lý nếu việc đăng ký thất bại và nếu callback có thể phát sau khi sink đã bị hủy. `onDispose` là nơi gắn hành động dọn dẹp với vòng đời sink; cần bảo đảm thao tác đóng idempotent nếu có nhiều đường gọi dispose. Với tài nguyên có logic sở hữu phức tạp, dùng `using` để thể hiện resource scope rõ ràng thường dễ kiểm tra hơn.

### Kiểm tra listener không còn nhận sự kiện

Trong kiểm thử, hãy dùng một event bus giả có thể đếm số listener đã đăng ký và hủy:

1. Subscribe vào Flux adapter.
2. Phát một sự kiện và xác nhận subscriber nhận được.
3. Hủy subscription.
4. Phát thêm sự kiện và xác nhận subscriber không nhận dữ liệu mới.
5. Xác nhận số listener đang đăng ký trở về mức ban đầu.

Đừng chỉ kiểm tra callback `close()` đã được gọi. Hãy xác nhận listener thực sự bị gỡ khỏi event bus, vì một cleanup giả có thể tăng bộ đếm nhưng vẫn để callback tồn tại.

## 7. Các lỗi cleanup thường gặp

### Chỉ cleanup khi hoàn tất bình thường

Một số mã chỉ gọi close trong `doOnComplete`. Cách này bỏ sót đường lỗi và cancellation. Dùng `using` hoặc `usingWhen` để gắn cleanup với toàn bộ vòng đời.

### Dùng `doFinally` làm chủ sở hữu tài nguyên

`doFinally` hữu ích để đếm trạng thái complete/error/cancel hoặc ghi metrics. Tuy nhiên, nó không tự biểu đạt việc cấp phát tài nguyên theo subscription và cleanup bất đồng bộ. Nếu tài nguyên được tạo trong pipeline, hãy ưu tiên `using` hoặc `usingWhen`; dùng hook để quan sát thêm.

### Đóng tài nguyên quá sớm

Tạo Stream hoặc connection trước khi Publisher được subscribe rồi đóng ngay sau khi trả Publisher sẽ khiến resource closure dùng tài nguyên đã đóng. Cấp phát trong resource supplier.

### Dùng chung một tài nguyên cho nhiều subscriber

Một Java Stream chỉ có thể tiêu thụ một lần. Một connection hoặc listener có thể có chính sách chia sẻ riêng. Không đưa một resource đơn lẻ vào nhiều subscription nếu chưa xác định rõ quyền sở hữu và đồng bộ.

### Cleanup chặn event loop

Nếu close gọi I/O đồng bộ và chạy trên event loop, các request khác có thể bị chậm. Chuyển thao tác chặn sang scheduler phù hợp hoặc dùng API cleanup bất đồng bộ.

### Cleanup thất bại nhưng bị bỏ qua

Lỗi đóng tệp, trả connection hoặc hủy listener cần được ghi nhận. Nếu cleanup thất bại, tài nguyên có thể vẫn bị giữ. Đừng dùng `onErrorResume(error -> Mono.empty())` một cách vô điều kiện chỉ để che lỗi; nếu cần tiếp tục, hãy log, tăng metric và có chính sách xử lý rõ ràng.

### Giả định cancellation luôn dừng tác vụ vật lý ngay lập tức

Cancellation là tín hiệu điều khiển. Một lời gọi native, driver hoặc thao tác bên ngoài có thể không dừng ngay. Hãy kiểm tra khả năng hủy của API, đặt timeout và bảo đảm cleanup có thể chạy an toàn khi công việc đang kết thúc đồng thời.

## 8. Kiểm thử đủ ba đường kết thúc

Một bộ kiểm thử resource lifecycle nên bao gồm ít nhất:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Complete | Resource được đóng hoặc trả về đúng một lần |
| Error | Resource vẫn được đóng; lỗi gốc được quan sát |
| Cancel | Cleanup được gọi dù nguồn chưa hoàn tất |
| Empty completion | Resource vẫn được giải phóng dù không có onNext |
| Nhiều subscription | Mỗi subscription có resource riêng và cleanup tương ứng |
| Cleanup error | Lỗi cleanup được ghi nhận và không bị che khuất ngoài ý muốn |

Ví dụ kiểm thử cancellation với `usingWhen`:

~~~java
AtomicInteger closeCount = new AtomicInteger();

Flux<String> source = Flux.usingWhen(
    Mono.fromSupplier(() -> new AsyncHandle(closeCount)),
    handle -> Flux.concat(
        Flux.just("ready"),
        Flux.never()
    ),
    AsyncHandle::closeAsync,
    (handle, error) -> handle.closeAsync(),
    AsyncHandle::closeAsync
);

StepVerifier.create(source)
    .expectNext("ready")
    .thenCancel()
    .verify();

assertEquals(1, closeCount.get());
~~~

Trong ví dụ, `AsyncHandle.closeAsync()` trả về `Mono<Void>` và tăng bộ đếm sau khi cleanup hoàn tất. Test chỉ kết thúc sau khi StepVerifier thực hiện cancellation; việc kiểm tra bộ đếm xác nhận callback cleanup đã được thực thi.

Ví dụ giả định `closeAsync()` hoàn tất ngay khi được subscribe. Với cleanup thực sự bất đồng bộ, cancellation không tạo terminal signal cho subscriber để chờ; hãy phát một tín hiệu kiểm thử riêng khi cleanup hoàn tất (chẳng hạn `CountDownLatch` hoặc `Sinks.Empty`) rồi đợi tín hiệu đó với timeout trước khi kiểm tra bộ đếm. Điều này giúp test xác nhận việc giải phóng đã hoàn tất, không chỉ xác nhận callback đã được khởi chạy.

Để kiểm tra error path, thay resource closure bằng `Flux.error(new IllegalStateException("read failed"))`, dùng `verifyErrorMessage("read failed")`, rồi xác nhận handle đã đóng. Với complete path, dùng `Flux.just(...)` và `verifyComplete()`. Nên tách mỗi trường hợp thành test độc lập để lỗi ở một đường không che kết quả của đường khác.

Với cleanup bất đồng bộ, hãy kiểm tra cả thời gian cleanup và lỗi cleanup. Nếu callback đóng trả về Publisher không bao giờ hoàn tất, pipeline có thể không phát terminal signal theo cơ chế của `usingWhen`. Vì vậy, thao tác cleanup cần có timeout và chính sách xử lý khi dịch vụ đóng tài nguyên không phản hồi.

## 9. Quy trình kiểm tra rò rỉ trong ứng dụng

Khi một dịch vụ có dấu hiệu tăng file descriptor, cạn connection hoặc tăng số listener, hãy kiểm tra theo trình tự:

1. **Xác định chủ sở hữu:** tìm nơi tạo tệp, connection, cursor, session hoặc listener. Mỗi resource cần một thành phần chịu trách nhiệm đóng.
2. **Xác định phạm vi subscription:** resource được tạo một lần cho ứng dụng, một lần cho request hay một lần cho mỗi subscriber? Việc chia sẻ phải có quy tắc rõ.
3. **Liệt kê đường kết thúc:** complete, error, cancel và trường hợp nguồn rỗng. Đường nào cũng cần có chính sách cleanup.
4. **Chọn cơ chế quản lý:** dùng `using` cho cleanup đồng bộ nhanh; dùng `usingWhen` khi cleanup trả về Publisher hoặc cần commit/rollback.
5. **Kiểm thử từng đường:** dùng StepVerifier và resource giả đếm số lần open/close, đồng thời có kiểm thử tích hợp cho handle thật.
6. **Đo trong vận hành:** đối chiếu số resource mở/đóng, active/idle connection, pending acquire, file descriptor và số listener.
7. **Kiểm tra lỗi cleanup:** ghi nhận lỗi và thời gian cleanup; đặt timeout cho thao tác đóng bất đồng bộ.
8. **Thử tải và hủy:** chạy nhiều subscription, hủy giữa luồng, làm chậm downstream và gây lỗi nguồn để quan sát resource có trở về mức ổn định không.

Không nên kết luận có rò rỉ chỉ từ một ảnh chụp số lượng resource đang mở. Một pool có thể giữ connection idle để tái sử dụng; một listener có thể tồn tại đúng vòng đời của service. Hãy so sánh xu hướng trước và sau khi tải kết thúc, đối chiếu với số subscription đang hoạt động và chính sách pool.

## 10. Bài tập vận dụng

Một endpoint trả về Flux<Event> từ một SDK bên ngoài. Khi có subscriber, ứng dụng đăng ký listener với SDK. Mỗi sự kiện được chuyển đổi rồi gửi xuống client. Client có thể ngắt kết nối bất cứ lúc nào; SDK cung cấp một Registration có phương thức `dispose()`. Một nhánh khác đọc dữ liệu từ tệp để bổ sung thông tin, và một nhánh reactive truy vấn cơ sở dữ liệu.

Hãy thiết kế vòng đời tài nguyên cho endpoint:

1. Dùng `Flux.using` hoặc adapter tương đương để tạo Registration khi subscribe và dispose khi complete, error hoặc cancel.
2. Quản lý Stream tệp theo từng subscription; kiểm tra rằng tệp được đóng nếu client hủy sau một vài sự kiện.
3. Dùng `usingWhen` nếu connection hoặc session cần cleanup bất đồng bộ.
4. Xác định điều gì xảy ra nếu đọc tệp lỗi sau khi listener đã đăng ký: listener có được dispose không?
5. Viết ba kiểm thử cho complete, error và cancel, xác nhận listener và file handle đều được giải phóng.
6. Đề xuất metrics để phân biệt resource đang hoạt động hợp lệ với resource bị rò rỉ.

Khi hoàn thành, hãy chứng minh rằng mỗi tài nguyên có một chủ sở hữu, mỗi subscription có vòng đời rõ ràng và mọi đường kết thúc đều kích hoạt cleanup. Nếu một pipeline kết hợp nhiều resource, hãy quản lý chúng bằng các scope lồng nhau hoặc một đối tượng composite có cleanup theo thứ tự ngược với thứ tự cấp phát.

## Kết luận

Rò rỉ tài nguyên trong ứng dụng reactive thường xuất hiện khi việc cấp phát và giải phóng không cùng phạm vi subscription. `using` phù hợp với tài nguyên có cleanup đồng bộ; `usingWhen` quản lý cleanup bất đồng bộ trên complete, error và cancel. Với tệp, kết nối và listener, cần kiểm thử cả đường thành công lẫn lỗi và hủy, đồng thời theo dõi số resource đang mở trong vận hành. Khi xác định đúng chủ sở hữu và kiểm tra được mọi đường cleanup, pipeline dài hạn có thể hoạt động ổn định mà không tích lũy file handle, connection hoặc listener ngoài ý muốn.
