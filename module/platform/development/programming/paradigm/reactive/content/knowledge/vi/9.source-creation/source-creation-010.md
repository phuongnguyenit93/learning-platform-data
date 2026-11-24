# Đọc tệp và nguồn I/O: kiểm tra hành vi chặn của bộ chuyển đổi

Khi đưa một API I/O đồng bộ vào pipeline reactive, việc bọc lời gọi trong `Mono` hoặc `Flux` chưa làm cho thao tác đó trở thành non-blocking. Nếu lời gọi đọc tệp, truy vấn JDBC hoặc gọi một thư viện đồng bộ chạy trên thread xử lý sự kiện, thread đó vẫn bị giữ lại cho đến khi I/O hoàn tất. Một bộ chuyển đổi reactive đúng cần trì hoãn thao tác đến thời điểm subscribe, chạy công việc blocking trên scheduler phù hợp, quản lý vòng đời tài nguyên và có cách kiểm tra hành vi thực tế.

Bài học này thuộc chương **Tạo nguồn** của module **REACTIVE_PROGRAMMING**. Module tập trung vào tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trong phạm vi bài này, ta dùng Project Reactor để chuyển thao tác đọc tệp và I/O đồng bộ thành nguồn reactive có hành vi được kiểm soát.

## Bọc một lời gọi blocking không tự biến nó thành non-blocking

Giả sử ứng dụng cần đọc nội dung một tệp bằng `Files.readString`, một API đồng bộ của Java:

~~~java
Mono<String> unsafeRead(Path path) throws IOException {
    return Mono.just(Files.readString(path));
}
~~~

Đoạn mã này đọc tệp ngay khi biểu thức `Mono.just(...)` được đánh giá. Việc đọc diễn ra trên thread gọi phương thức, trước khi có ai subscribe. Nếu thao tác ném `IOException`, exception cũng được ném ngay tại chỗ tạo publisher thay vì trở thành tín hiệu `onError` của Mono.

`Mono.fromCallable` trì hoãn lời gọi cho đến khi có subscribe và chuyển exception thành tín hiệu lỗi:

~~~java
Mono<String> content = Mono.fromCallable(
    () -> Files.readString(path)
);
~~~

Tuy nhiên, publisher trên vẫn thực thi `Callable` trên thread thực hiện subscription nếu chưa chỉ định scheduler. Nếu một HTTP event loop subscribe vào publisher này, thao tác đọc tệp vẫn có thể chặn event loop. Cần chọn scheduler cho nguồn blocking:

~~~java
Mono<String> readText(Path path) {
    return Mono.fromCallable(() -> Files.readString(path))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`fromCallable` giải quyết việc trì hoãn và chuyển exception thành tín hiệu reactive. `subscribeOn(Schedulers.boundedElastic())` chuyển quá trình thực thi nguồn sang scheduler được thiết kế cho các tác vụ blocking có thời gian chờ không cố định. Khi subscribe, Reactor lên lịch thực thi `Callable` trên một worker của scheduler này; thread gọi subscribe không phải chờ thao tác đọc tệp hoàn tất.

Có thể so sánh ba trường hợp:

| Cách tạo publisher | Thời điểm đọc tệp | Thread thực hiện |
|---|---|---|
| `Mono.just(Files.readString(path))` | Ngay khi tạo biểu thức | Thread gọi phương thức |
| `Mono.fromCallable(() -> Files.readString(path))` | Khi subscribe | Thread thực hiện subscription nếu không đổi scheduler |
| `Mono.fromCallable(...).subscribeOn(boundedElastic())` | Khi subscribe | Worker của `boundedElastic` |

Vì vậy, hai điều kiện cần kiểm tra là **thời điểm thực thi** và **thread thực thi**. Publisher có thể lazy nhưng vẫn blocking trên thread không phù hợp.

## Chọn scheduler đúng cho I/O đồng bộ

Reactor cung cấp một số scheduler với mục đích sử dụng khác nhau:

| Scheduler | Đặc điểm | Cách dùng điển hình |
|---|---|---|
| `Schedulers.parallel()` | Pool có số worker giới hạn, phù hợp với tác vụ tính toán ngắn | Parse dữ liệu, biến đổi CPU-bound |
| `Schedulers.boundedElastic()` | Pool dành cho tác vụ blocking, có giới hạn worker và hàng đợi | Đọc tệp đồng bộ, JDBC, thư viện HTTP đồng bộ, API cũ |
| `Schedulers.immediate()` | Thực thi ngay trên thread hiện tại | Các trường hợp cần chạy trực tiếp, không phải nơi đặt blocking I/O |
| `Schedulers.single()` | Một worker tuần tự dùng chung | Công việc nhẹ cần thứ tự trên một thread, không dùng cho blocking I/O kéo dài |

Không nên chuyển thao tác đọc tệp đồng bộ sang `parallel()` chỉ vì tên gọi nghe có vẻ nhanh. Các worker của `parallel` được dùng cho công việc CPU-bound; chặn chúng bằng I/O có thể làm trì hoãn các pipeline khác dùng chung scheduler.

`boundedElastic` cũng không phải tài nguyên vô hạn. Scheduler giới hạn số worker và lượng tác vụ chờ theo cấu hình của Reactor. Nếu ứng dụng gửi quá nhiều thao tác blocking, tác vụ có thể phải chờ trong hàng đợi. Vì vậy, cần đặt giới hạn concurrency ở tầng gọi, theo dõi độ trễ và tránh tạo hàng triệu thao tác blocking cùng lúc.

### subscribeOn và publishOn có vai trò khác nhau

`subscribeOn` ảnh hưởng đến quá trình subscribe và việc thực thi nguồn upstream. Đây là toán tử cần dùng để chuyển lời gọi blocking nằm trong `fromCallable` sang `boundedElastic`.

`publishOn` chuyển việc xử lý các tín hiệu ở phía downstream sang scheduler được chỉ định. Nó không tự chuyển lời gọi nguồn đã chạy trước nó sang scheduler mới:

~~~java
// Không đủ để chuyển lời gọi Files.readString khỏi thread subscribe.
Mono<String> unsafe = Mono.fromCallable(
        () -> Files.readString(path))
    .publishOn(Schedulers.boundedElastic());

// Chuyển việc thực thi Callable sang boundedElastic.
Mono<String> safe = Mono.fromCallable(
        () -> Files.readString(path))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Có thể kết hợp cả hai khi cần đọc tệp trên worker blocking rồi xử lý nội dung trên scheduler tính toán:

~~~java
Mono<ParsedDocument> document = readText(path)
    .publishOn(Schedulers.parallel())
    .map(this::parseDocument);
~~~

Ở ví dụ này, thao tác đọc tệp được thực hiện bởi `boundedElastic`; phép parse phía sau `publishOn` được thực hiện trên `parallel`. Chỉ chuyển sang scheduler tính toán khi công việc downstream thực sự cần tài nguyên CPU và phù hợp với giới hạn thread của ứng dụng.

## Đọc tệp theo từng dòng và đóng tài nguyên đúng cách

Đọc toàn bộ nội dung bằng `Files.readString` phù hợp với tệp có kích thước vừa phải. Với tệp lớn, đọc từng dòng giúp pipeline xử lý dữ liệu tăng dần và tránh giữ toàn bộ nội dung trong bộ nhớ.

`Files.lines(path)` trả về một `Stream<String>` có tài nguyên hệ thống cần được đóng. Có thể kết hợp `Flux.using` để tạo stream khi subscribe và đóng stream khi publisher hoàn tất hoặc bị hủy:

~~~java
Flux<String> readLines(Path path) {
    return Flux.using(
        () -> Files.lines(path),
        stream -> Flux.fromStream(stream),
        Stream::close
    ).subscribeOn(Schedulers.boundedElastic());
}
~~~

Ba phần của `Flux.using` có vai trò riêng:

1. Resource supplier mở stream khi có subscription.
2. Source factory chuyển stream thành `Flux` để phát từng dòng.
3. Resource cleanup đóng stream khi quá trình tiêu thụ kết thúc hoặc subscription bị cancel.

`subscribeOn(boundedElastic())` giúp việc mở, đọc và đóng tài nguyên diễn ra trong quá trình thực thi nguồn trên scheduler dành cho blocking I/O. Cần giữ cleanup trong publisher; nếu chỉ gọi `Files.lines` rồi bỏ qua `Stream.close`, file descriptor có thể bị giữ lại lâu hơn dự kiến.

Nếu chỉ cần một phần nội dung, Subscriber có thể hủy sau khi nhận đủ số dòng:

~~~java
StepVerifier.create(readLines(path).take(3))
    .expectNext("dòng thứ nhất", "dòng thứ hai", "dòng thứ ba")
    .verifyComplete();
~~~

`take(3)` hủy subscription upstream sau khi nhận ba phần tử. Với cấu trúc `using`, việc hủy này kích hoạt cleanup để đóng stream. Đây là lý do vòng đời tài nguyên phải gắn với vòng đời subscription.

## Chuyển các API I/O đồng bộ khác thành nguồn reactive

Nguyên tắc tương tự áp dụng cho nhiều adapter:

~~~java
Mono<Account> loadAccount(String id) {
    return Mono.fromCallable(() -> jdbcDao.findAccount(id))
        .subscribeOn(Schedulers.boundedElastic());
}

Mono<Response> callLegacyClient(Request request) {
    return Mono.fromCallable(() -> legacyHttpClient.execute(request))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Các ví dụ trên phù hợp khi `jdbcDao` và `legacyHttpClient` là API đồng bộ. Chúng không biến JDBC hay HTTP client thành giao thức non-blocking; chúng cô lập thời gian chờ blocking trên worker phù hợp và đưa kết quả vào hợp đồng Publisher–Subscriber.

Nếu thư viện đã cung cấp driver reactive hoặc API I/O bất đồng bộ thực sự, hãy ưu tiên dùng adapter native của thư viện. Không cần chuyển một API non-blocking sang `boundedElastic` chỉ vì nó thực hiện I/O. Chọn scheduler dựa trên hành vi thực tế của API, không dựa riêng vào việc tên phương thức có chứa từ “read”, “send” hay “query”.

## Kiểm tra hành vi blocking của adapter

Kiểm tra một adapter cần xem xét ít nhất ba khía cạnh:

- **Lazy:** thao tác I/O có chạy khi tạo publisher hay chỉ chạy khi subscribe?
- **Scheduler:** thao tác blocking có chạy trên worker phù hợp không?
- **Resource và lỗi:** tài nguyên có được đóng khi hoàn tất hoặc cancel, exception có trở thành `onError` không?

### Kiểm tra lazy và tín hiệu lỗi bằng StepVerifier

Có thể dùng bộ đếm để xác nhận lời gọi chưa chạy trước khi subscribe:

~~~java
AtomicInteger calls = new AtomicInteger();

Mono<String> source = Mono.fromCallable(() -> {
    calls.incrementAndGet();
    return "nội dung";
}).subscribeOn(Schedulers.boundedElastic());

assertEquals(0, calls.get());

StepVerifier.create(source)
    .expectNext("nội dung")
    .verifyComplete();

assertEquals(1, calls.get());
~~~

Kiểm thử này xác nhận `Callable` chỉ chạy khi có subscription và chỉ được gọi một lần cho subscription đó. Nếu publisher được subscribe nhiều lần, `fromCallable` thông thường sẽ gọi lại `Callable` cho mỗi subscription; hãy cân nhắc cache nếu nghiệp vụ thật sự cần chia sẻ một kết quả đã đọc.

Với đường dẫn không tồn tại hoặc không thể đọc, lỗi I/O được chuyển thành tín hiệu `onError`:

~~~java
StepVerifier.create(readText(Path.of("missing-file.txt")))
    .expectError(IOException.class)
    .verify();
~~~

`Files.readString` ném `IOException`; `Mono.fromCallable` chuyển exception này thành lỗi của publisher. Trong mã ứng dụng, tầng gọi có thể xử lý lỗi bằng `onErrorMap`, `onErrorResume` hoặc để lỗi truyền đến ranh giới xử lý lỗi phù hợp.

### Quan sát thread thực thi

Trong quá trình phát triển, có thể ghi lại tên thread ngay bên trong lời gọi I/O:

~~~java
Mono<String> readTextWithTrace(Path path) {
    return Mono.fromCallable(() -> {
        log.debug("Reading file on {}", Thread.currentThread().getName());
        return Files.readString(path);
    }).subscribeOn(Schedulers.boundedElastic());
}
~~~

Log tại bên trong `Callable` cho biết thread thực sự thực hiện thao tác đọc. Log trong một `doOnNext` đặt sau `publishOn` có thể cho biết thread xử lý downstream, nhưng không chứng minh thread thực hiện I/O là thread nào. Đặt điểm quan sát tại đúng ranh giới cần kiểm tra.

### Phát hiện blocking bằng BlockHound

BlockHound là công cụ kiểm tra ở runtime, có thể phát hiện một số lời gọi blocking đã được instrument khi chúng chạy trên thread được đánh dấu là non-blocking, chẳng hạn worker của `Schedulers.parallel()`. Trong bộ kiểm thử, có thể cài đặt BlockHound một lần:

~~~java
BlockHound.install();
~~~

Sau đó kiểm tra cơ chế phát hiện bằng một lời gọi blocking được nhận diện:

~~~java
Mono<String> blockingProbe = Mono.fromCallable(() -> {
    Thread.sleep(10);
    return "done";
}).subscribeOn(Schedulers.parallel());

StepVerifier.create(blockingProbe)
    .expectError(BlockingOperationError.class)
    .verify();
~~~

Đây là phép thử xác nhận BlockHound đang phát hiện blocking trên scheduler non-blocking. Để kiểm tra adapter cụ thể, hãy chạy chính lời gọi của adapter trên scheduler non-blocking trong môi trường có BlockHound và quan sát lỗi nếu phương thức bên dưới được instrument. Sau đó, chuyển adapter về `boundedElastic` và kiểm thử lại hành vi nghiệp vụ.

BlockHound không phải bằng chứng rằng mọi API I/O đều non-blocking hoặc mọi thao tác blocking đều đã được phát hiện. Khả năng phát hiện phụ thuộc các phương thức được instrument, phiên bản thư viện, JDK và cấu hình tích hợp. Với API native hoặc thư viện không được instrument, cần kết hợp quan sát thread, đo độ trễ và kiểm tra tài liệu của nhà cung cấp.

## Những lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| `Mono.just(blockingCall())` | Thực thi I/O ngay khi tạo publisher | Dùng `Mono.fromCallable` |
| `fromCallable` nhưng không có `subscribeOn` | Blocking có thể chạy trên thread subscribe, kể cả event loop | Dùng `subscribeOn(boundedElastic())` |
| Chỉ đặt `publishOn(boundedElastic())` sau nguồn | Chuyển xử lý downstream nhưng không chuyển lời gọi nguồn | Đặt `subscribeOn` cho nguồn blocking |
| Đưa I/O blocking vào `map` của luồng đang chạy trên `parallel` | Giữ worker tính toán trong thời gian chờ I/O | Tách nguồn blocking bằng `fromCallable` và `subscribeOn` |
| Dùng `Files.lines` nhưng không đóng stream | Có thể rò rỉ file descriptor | Gắn tài nguyên với subscription bằng `Flux.using` |
| Chặn bằng `block()` trong request path | Làm mất lợi ích bất đồng bộ và có thể chặn event loop | Trả về `Mono`/`Flux` cho tầng gọi |
| Dùng `boundedElastic` cho mọi loại I/O | Tốn worker và làm mờ ranh giới blocking/non-blocking | Ưu tiên driver reactive khi có; chỉ cách ly API blocking |

## Quy trình thiết kế một bộ chuyển đổi I/O

Khi chuyển một API đồng bộ thành nguồn reactive, hãy đi theo trình tự:

1. Xác định lời gọi có blocking hay không từ tài liệu và hành vi thực tế của thư viện.
2. Dùng `fromCallable` cho kết quả đơn hoặc `Flux.using` cho nguồn cần quản lý tài nguyên.
3. Dùng `subscribeOn(Schedulers.boundedElastic())` để cách ly thao tác blocking khỏi event loop và scheduler tính toán.
4. Đảm bảo exception trở thành `onError`, tài nguyên được đóng khi complete hoặc cancel.
5. Dùng StepVerifier để kiểm tra lazy, dữ liệu, lỗi và hủy subscription; dùng quan sát thread và BlockHound như các lớp kiểm tra bổ sung.
6. Giới hạn concurrency và theo dõi hàng đợi khi lưu lượng I/O tăng cao.

Một adapter reactive tốt giữ nguyên ý nghĩa nghiệp vụ của API gốc, đồng thời làm rõ thời điểm thực thi, thread thực thi, tín hiệu lỗi và vòng đời tài nguyên. Khi kiểm tra được những đặc điểm đó, việc kết hợp nguồn I/O với `Mono`, `Flux` và các toán tử downstream sẽ an toàn và dễ dự đoán hơn.
