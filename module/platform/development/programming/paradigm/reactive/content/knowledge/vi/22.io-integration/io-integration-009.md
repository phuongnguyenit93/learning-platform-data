# Hủy chuỗi và khả năng hủy tác vụ I/O ở lớp bên dưới

Một pipeline reactive có thể bị hủy khi người dùng rời trang, client HTTP ngắt kết nối, request hết thời gian chờ hoặc một toán tử không còn cần kết quả từ publisher con. Việc hủy subscription giúp dừng công việc không còn cần thiết và giải phóng tài nguyên. Tuy nhiên, hủy một chuỗi Reactor không đồng nghĩa mọi thao tác I/O đã gửi xuống network, database hoặc thư viện blocking đều lập tức dừng lại.

Trong Reactive Streams, subscriber gọi `Subscription.cancel()` để yêu cầu publisher ngừng phát dữ liệu cho subscription đó. Reactor truyền yêu cầu hủy qua các toán tử upstream và các adapter có khả năng hỗ trợ. Tác vụ I/O bên dưới chỉ dừng thực sự nếu API, driver hoặc transport có cơ chế cancellation và adapter kết nối đúng cơ chế đó. Vì vậy, cần phân biệt **hủy chuỗi tín hiệu**, **hủy subscription upstream** và **hủy tác vụ I/O thực tế**.

## 1. Cancellation là một yêu cầu trong hợp đồng Reactive Streams

Một subscriber nhận `Subscription` qua `onSubscribe`. Subscription cung cấp hai thao tác chính:

- `request(n)` yêu cầu publisher phát thêm tối đa n phần tử.
- `cancel()` yêu cầu publisher dừng việc phát dữ liệu cho subscriber đó.

Cancellation đi từ downstream ngược về upstream, theo chiều ngược với `onNext`, `onError` và `onComplete`.

~~~mermaid
sequenceDiagram
    participant D as Downstream
    participant O as Reactor operators
    participant U as Upstream publisher
    participant IO as I/O client hoặc driver
    D->>O: subscribe / request(n)
    O->>U: subscribe / request(n)
    U->>IO: bắt đầu I/O
    IO-->>U: dữ liệu
    U-->>O: onNext
    O-->>D: onNext
    D->>O: cancel()
    O->>U: cancel()
    U->>IO: yêu cầu hủy nếu adapter hỗ trợ
~~~

`cancel()` là yêu cầu best-effort. Publisher cần ngừng phát tín hiệu cho subscription đã bị hủy và giải phóng tài nguyên mà nó sở hữu, nhưng cancellation không phải terminal signal. Subscriber không nhận `onComplete` chỉ vì nó đã gọi cancel; publisher cũng không gửi `onError` để báo rằng cancellation xảy ra.

Sau cancellation, một callback hoặc I/O đã bắt đầu có thể vẫn đang chạy. Cancellation không tự động rollback side effect, thu hồi một gói tin đã gửi hoặc đảm bảo server chưa xử lý request. Đây là ranh giới quan trọng giữa điều khiển luồng reactive và tác động bên ngoài.

## 2. Phân biệt hủy downstream và hủy upstream

Một toán tử có thể kết thúc phía downstream bằng một tín hiệu, đồng thời hủy upstream vì không còn cần dữ liệu.

Ví dụ `take(1)`:

~~~java
Flux<Long> firstTick = Flux.interval(Duration.ofSeconds(1))
    .doOnCancel(() -> log.info("Nguồn interval nhận cancel"))
    .take(1)
    .doOnComplete(() -> log.info("Downstream đã nhận đủ một tick"));
~~~

Khi phần tử đầu tiên đến, `take(1)` phát `onComplete` cho downstream và hủy upstream để không nhận các tick tiếp theo. Do đó, hook phía trên take quan sát cancellation, còn hook phía dưới quan sát completion. Hai kết quả này không mâu thuẫn; chúng mô tả hai phía của toán tử.

Các toán tử thường có thể hủy publisher con hoặc upstream:

| Toán tử/tình huống | Hành vi liên quan đến cancellation |
| --- | --- |
| `take(n)` | Hủy upstream sau khi đã nhận đủ n phần tử và hoàn tất downstream |
| `timeout(...)` | Hủy nguồn đang chờ khi hết thời gian; thường phát `TimeoutException` xuống downstream nếu không có fallback |
| `switchMap(...)` | Hủy publisher con trước khi chuyển sang publisher con mới |
| `flatMap(...)` | Khi downstream hủy, yêu cầu hủy các publisher con đang hoạt động và upstream |
| `first`, `next` hoặc lấy một phần tử | Có thể hủy nguồn sau khi đã có kết quả cần thiết |
| Client hủy HTTP response | Framework có thể hủy subscription của response body |

Một số toán tử có chế độ trì hoãn lỗi hoặc chính sách đặc biệt; hãy đọc semantics của overload đang dùng. Không nên suy luận rằng mọi operator đều hủy ngay mọi công việc con trong mọi trường hợp.

## 3. timeout hủy nguồn nhưng downstream nhận lỗi

`timeout` là ví dụ quan trọng vì downstream có thể nhận lỗi trong khi upstream nhận cancellation:

~~~java
Mono<Profile> profile = profileClient.fetch(userId)
    .timeout(Duration.ofSeconds(2));
~~~

Nếu nguồn không phát tín hiệu trong thời gian cho phép, `timeout` yêu cầu hủy subscription upstream và phát `TimeoutException` xuống downstream. Nếu có fallback, downstream có thể nhận kết quả fallback thay vì lỗi:

~~~java
Mono<Profile> profile = profileClient.fetch(userId)
    .timeout(
        Duration.ofSeconds(2),
        profileCache.find(userId)
    );
~~~

Timeout giới hạn thời gian chờ ở tầng reactive. Việc request mạng hoặc truy vấn database có thật sự dừng hay không còn phụ thuộc adapter, transport và driver. Nếu API bên dưới không hỗ trợ cancellation, công việc có thể tiếp tục chạy sau khi downstream đã nhận timeout. Trong trường hợp đó, cần thêm timeout ở chính client/driver hoặc giới hạn tài nguyên tại lớp I/O.

## 4. Khi nào cancellation dừng được I/O thực tế?

Khả năng dừng I/O phụ thuộc vào loại API và adapter.

| Lớp I/O | Khả năng cancellation thường gặp | Điều cần xác minh |
| --- | --- | --- |
| HTTP client reactive như WebClient/Reactor Netty | Cancellation của response subscription thường được truyền đến request/response transport | Request đã được gửi chưa, connection có được tái sử dụng an toàn không, server đã thực hiện side effect chưa |
| Database reactive như R2DBC | Driver có thể gửi tín hiệu hủy statement hoặc dừng đọc kết quả | Driver, database và protocol có hỗ trợ hủy truy vấn không; server đã bắt đầu commit chưa |
| `CompletableFuture` | Adapter có thể gọi `cancel` trên future khi subscription bị hủy | Công việc thực tế có quan sát cancellation không; `CompletableFuture.cancel` không bảo đảm interrupt tác vụ đã chạy |
| API callback có `Cancellable`/`Disposable` | Có thể gọi phương thức cancel/dispose của API | Phương thức đó có dừng producer, gỡ listener và giải phóng tài nguyên không |
| API blocking/JDBC | Thường không có liên kết cancellation tự động với Reactor | Driver có hỗ trợ `Statement.cancel`, interrupt hay timeout không; thread có thể đang bị chặn trong native I/O |

Không thể kết luận I/O đã dừng chỉ vì `doOnCancel` được gọi. Hook đó chứng minh subscription đã nhận yêu cầu hủy tại vị trí hook; nó không chứng minh server, database hoặc thread blocking đã ngừng công việc.

## 5. HTTP reactive: client ngắt kết nối không thu hồi side effect

Trong Spring WebFlux, response body thường được trả dưới dạng publisher. Khi client ngắt kết nối hoặc không còn tiêu thụ response, framework có thể hủy subscription và Reactor Netty có thể dừng việc đọc/ghi tiếp theo khi transport còn khả năng làm vậy.

~~~java
Mono<ServerResponse> streamEvents(ServerRequest request) {
    Flux<Event> events = eventService.events()
        .doOnCancel(() -> log.info("Client ngừng nhận event stream"));

    return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(events, Event.class);
}
~~~

Nếu client đóng kết nối, việc hủy response body có thể truyền ngược đến `eventService.events()`. Nguồn có thể dừng polling hoặc gỡ đăng ký listener nếu được thiết kế để phản ứng với cancellation.

Nhưng với request tạo đơn hàng hoặc thanh toán, việc client đóng kết nối sau khi server đã nhận request không có nghĩa nghiệp vụ được hủy. Server có thể đã ghi dữ liệu hoặc gửi lệnh đến hệ thống thanh toán. Nếu client thử lại vì không nhận response, thao tác có thể bị thực hiện hai lần. Các API có side effect cần idempotency key, lưu trạng thái giao dịch và cơ chế truy vấn kết quả sau timeout.

## 6. Database reactive: cancellation phụ thuộc driver và database

R2DBC cung cấp API non-blocking và tích hợp với Reactive Streams. Khi downstream hủy một publisher truy vấn, adapter/driver có thể dừng phát hàng tiếp theo và có thể yêu cầu database hủy statement nếu protocol hỗ trợ.

~~~java
Flux<Order> orders = databaseClient.sql("""
        SELECT id, status
        FROM orders
        WHERE tenant_id = :tenantId
        """)
    .bind("tenantId", tenantId)
    .map(row -> mapOrder(row))
    .all()
    .doOnCancel(() -> log.debug("Truy vấn orders bị hủy"));
~~~

`doOnCancel` chỉ quan sát cancellation ở pipeline. Muốn biết truy vấn đã bị database dừng hay chưa, cần kiểm tra khả năng của driver, database và protocol, đồng thời quan sát metric phía database. Một truy vấn có thể đã hoàn tất ở server trước khi tín hiệu cancel đến.

Với transaction, cancellation cần được xử lý theo semantics của transaction manager. Không tự coi cancellation là commit hoặc rollback thành công. Dùng abstraction transaction reactive và kiểm tra nhánh cleanup của nó; nếu trạng thái commit không rõ do mất kết nối, cần đối soát theo transaction ID hoặc khóa nghiệp vụ.

## 7. API blocking: boundedElastic không làm I/O có thể hủy

Một API blocking có thể được cô lập khỏi event-loop bằng `subscribeOn(Schedulers.boundedElastic())`:

~~~java
Mono<LegacyResult> result = Mono.fromCallable(
        () -> legacyClient.callBlocking()
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

Điều này giúp thread event-loop không bị chặn bởi lời gọi blocking. Tuy nhiên, việc chuyển sang boundedElastic không tự biến API thành non-blocking và không bảo đảm cancellation sẽ dừng lời gọi đang chạy. Một số tác vụ có thể bị interrupt khi worker bị hủy; nhiều thư viện blocking bỏ qua interrupt hoặc đang chặn trong socket/native call.

Nếu thư viện hỗ trợ timeout riêng, hãy cấu hình timeout ở client hoặc socket. Nếu thư viện hỗ trợ `Statement.cancel`, `Future.cancel` hoặc một handle hủy riêng, hãy nối handle đó vào subscription. Nếu không có cơ chế dừng, hãy giới hạn concurrency, pool size và thời gian chờ để công việc bỏ hoang không chiếm hết tài nguyên.

Không dùng `dispose()` hoặc cancellation như bằng chứng rằng một lệnh blocking đã dừng. Cần đo thời gian tác vụ còn chạy sau khi subscriber rời đi và kiểm tra hành vi thực tế của driver.

## 8. Nối cancellation của callback API bằng Flux.create

Một API callback có thể cung cấp handle để hủy đăng ký. Khi bọc nó thành Flux, phải nối cancellation của Flux vào handle đó.

~~~java
Flux<SensorEvent> events = Flux.create(sink -> {
    Cancellable registration = sensorClient.listen(
        sink::next,
        sink::error,
        sink::complete
    );

    sink.onCancel(registration::cancel);
    sink.onDispose(registration::dispose);
});
~~~

Ví dụ giả định API `listen` trả về một đối tượng `Cancellable` có `cancel()` để ngừng phát sự kiện và `dispose()` để giải phóng đăng ký. Kiểu thực tế của handle phụ thuộc SDK. Nếu SDK chỉ có một thao tác hủy, có thể dùng cùng thao tác đó theo hợp đồng của API.

`onCancel` phù hợp với hành động riêng khi subscriber hủy. `onDispose` chạy khi sink được dispose sau các đường kết thúc, gồm complete, error và cancel; nó phù hợp để giải phóng tài nguyên cần cleanup ở mọi nhánh. Nếu cả hai hook cùng gọi một thao tác, thao tác đó phải idempotent hoặc được bảo vệ để không giải phóng hai lần.

### Cẩn thận với callback đến sau cancellation

Một callback có thể đã được xếp hàng trước khi `cancel()` đến. Adapter cần chịu được callback đến muộn:

- Không phát dữ liệu vào sink sau khi nguồn đã bị hủy nếu API cho phép kiểm tra trạng thái.
- Không truy cập resource đã đóng trong callback đang chạy.
- Đảm bảo cleanup thread-safe nếu cancel và callback xảy ra đồng thời.
- Ghi nhận lỗi không thể chuyển tới downstream theo chính sách của thư viện.

Không tự gọi `subscribe()` trong callback chỉ để xử lý từng sự kiện; hãy phát tín hiệu vào sink và để pipeline downstream quản lý demand, lỗi và cancellation.

## 9. Nối cancellation với CompletableFuture

Reactor có thể chuyển `CompletableFuture` thành Mono:

~~~java
Mono<Result> result = Mono.fromFuture(client.startAsync());
~~~

Khi subscription bị hủy, adapter Reactor mặc định có thể truyền cancellation đến future. Một số overload cho phép chọn không hủy future khi Mono bị cancel, ví dụ overload có tham số `suppressCancel` ở các phiên bản Reactor hỗ trợ:

~~~java
Mono<Result> result = Mono.fromFuture(
    client.startAsync(),
    true
);
~~~

Trong ví dụ này, `true` yêu cầu adapter không gọi cancel trên future khi subscription bị hủy. Hãy kiểm tra chữ ký API của phiên bản Reactor đang dùng trước khi áp dụng overload này.

Dù future nhận `cancel`, điều đó không bảo đảm công việc nền dừng. Theo hợp đồng `CompletableFuture`, tham số interrupt trong `cancel(boolean)` không có nghĩa là tác vụ đang chạy chắc chắn bị interrupt; `CompletableFuture` không nhất thiết kiểm soát executor hoặc API I/O thực hiện công việc. Nếu client cung cấp handle hủy riêng, nên giữ handle đó và nối trực tiếp với cancellation.

## 10. Hủy một publisher con trong flatMap và switchMap

Khi dùng `flatMap`, Reactor có thể subscribe nhiều publisher con cùng lúc. Nếu downstream hủy toàn bộ pipeline, operator yêu cầu hủy upstream và các inner subscription đang hoạt động. Nếu một inner publisher đã gửi request I/O, việc I/O thực tế dừng vẫn phụ thuộc adapter của inner publisher.

~~~java
Flux<Detail> details = ids.flatMap(
    id -> detailClient.fetch(id),
    8
);
~~~

Tham số `8` giới hạn số publisher con được subscribe đồng thời theo semantics của flatMap. Nó giúp giới hạn concurrency, nhưng không phải giới hạn thời gian chạy của từng request. Có thể kết hợp timeout ở mỗi publisher con:

~~~java
Flux<Detail> details = ids.flatMap(
    id -> detailClient.fetch(id)
        .timeout(Duration.ofSeconds(3)),
    8
);
~~~

`switchMap` phù hợp khi chỉ kết quả từ input mới nhất còn cần thiết, ví dụ tìm kiếm khi người dùng nhập:

~~~java
Flux<SearchResult> results = queryChanges
    .switchMap(query ->
        searchClient.search(query)
            .timeout(Duration.ofSeconds(2))
    );
~~~

Khi query mới đến, `switchMap` hủy publisher con trước đó. Điều này ngăn kết quả cũ tiếp tục đi xuống downstream sau khi đã có truy vấn mới. Nó chỉ dừng request mạng nếu client adapter thực sự hỗ trợ cancellation. Với thao tác có side effect, không dùng switchMap như cơ chế rollback; nó phù hợp hơn với tác vụ đọc hoặc tính toán có thể bỏ kết quả.

## 11. Cleanup khi cancellation xảy ra

Tài nguyên gắn với subscription cần được giải phóng trên complete, error và cancel. Với tài nguyên đồng bộ, `using` có thể quản lý vòng đời:

~~~java
Flux<Row> rows = Flux.using(
    () -> cursorFactory.open(query),
    cursor -> cursor.readRows(),
    Cursor::close
);
~~~

Với tài nguyên có cleanup bất đồng bộ, dùng `usingWhen` để định nghĩa nhánh complete, error và cancel:

~~~java
Flux<Row> rows = Flux.usingWhen(
    connectionFactory.create(),
    connection -> connection.query(sql),
    connection -> connection.close(),
    (connection, error) -> connection.rollback().then(connection.close()),
    connection -> connection.rollback().then(connection.close())
);
~~~

Ví dụ giả định các phương thức trả về publisher và transaction đã được mở trước đó. Trong ứng dụng thật, phải bảo đảm connection vẫn được đóng nếu rollback thất bại; cần xác định cách giữ lỗi gốc, lỗi cleanup và timeout cho quá trình giải phóng. Không để cancellation làm mất dấu tài nguyên đang được mượn.

`doOnCancel` phù hợp để quan sát hoặc gọi hành động đồng bộ nhẹ:

~~~java
source.doOnCancel(() -> metrics.increment("stream.cancelled"));
~~~

Không dùng `doFinally` để chờ cleanup bất đồng bộ vì callback này không trả publisher cleanup để Reactor compose. Dùng `usingWhen` khi đóng tài nguyên cần I/O hoặc cần đợi hoàn tất.

## 12. Cancellation không phải rollback

Cancellation chỉ nói rằng consumer không còn muốn nhận tín hiệu. Nó không bảo đảm một side effect bên ngoài bị đảo ngược.

Ví dụ:

1. Client gửi yêu cầu thanh toán.
2. Server nhận yêu cầu và gửi lệnh đến cổng thanh toán.
3. Client đóng kết nối trước khi nhận response.
4. Subscription bị hủy nhưng cổng thanh toán có thể đã xử lý giao dịch.
5. Client thử lại và có nguy cơ tạo thanh toán thứ hai.

Để xử lý đúng, API có side effect nên dùng:

- Idempotency key để cùng một yêu cầu logic không tạo thao tác trùng.
- Mã giao dịch để truy vấn trạng thái sau timeout hoặc mất kết nối.
- Transaction boundary và cơ chế commit/rollback do hệ thống sở hữu.
- Quy trình bù trừ (compensation) nếu side effect không thể rollback trực tiếp.
- Audit log để đối soát thao tác đã được chấp nhận ở lớp bên dưới.

Không nên gắn logic “rollback nghiệp vụ” vào `doOnCancel` một cách đơn giản. Cancellation có thể đến sau khi thao tác đã commit hoặc khi trạng thái bên ngoài chưa xác định. Cần dựa vào trạng thái giao dịch và hợp đồng của dịch vụ đích.

## 13. Quan sát cancellation qua log và metric

Nên đo cancellation ở nhiều ranh giới để biết yêu cầu hủy đã đi đến đâu:

~~~java
Mono<Response> response = client.fetch()
    .doOnCancel(() ->
        metrics.increment("client.subscription.cancelled")
    )
    .doFinally(signal ->
        log.debug("Client publisher terminated with {}", signal)
    );
~~~

Các metric hữu ích:

- Số subscription bị hủy.
- Số request I/O đã gửi cancel đến transport/driver.
- Thời gian từ lúc nhận cancel đến khi tài nguyên được giải phóng.
- Số tác vụ blocking vẫn chạy sau cancellation.
- Số lỗi cleanup hoặc callback đến muộn.
- Số request timeout và tỷ lệ request hoàn tất sau khi caller đã rời đi.

Không gắn nhãn metric bằng request ID, user ID hoặc giá trị cardinality cao. Dùng trace/log để điều tra một request cụ thể; metric nên dùng nhãn có tập giá trị giới hạn như loại client, loại operation hoặc kết quả.

`doOnCancel` xác nhận cancellation tại vị trí hook. Muốn xác nhận I/O thực tế dừng, cần metric từ client/driver hoặc quan sát ở server/database. Tránh dùng một metric duy nhất để đại diện cho cả ba lớp.

## 14. Kiểm thử cancellation của chuỗi

`StepVerifier` có thể yêu cầu cancel và xác minh hook được gọi:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .doOnCancel(() -> cancelled.set(true))
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(0L, 1L)
    .thenCancel()
    .verify();

assertTrue(cancelled.get());
~~~

Test xác minh subscription upstream nhận cancellation sau khi downstream hủy. Nó chưa chứng minh một socket hoặc database query thực tế đã dừng.

### Kiểm thử adapter callback

Với API callback, dùng một fake client giữ lại callback và handle hủy:

~~~java
AtomicBoolean registrationCancelled = new AtomicBoolean();

Flux<Event> events = Flux.create(sink -> {
    FakeRegistration registration =
        fakeClient.listen(sink::next, sink::error, sink::complete);

    sink.onCancel(() -> {
        registrationCancelled.set(true);
        registration.cancel();
    });
});

StepVerifier.create(events)
    .thenCancel()
    .verify();

assertTrue(registrationCancelled.get());
~~~

Test này xác minh adapter gọi cancel trên registration. Một integration test riêng cần xác minh fake hoặc client thật thực sự ngừng callback và giải phóng resource.

### Kiểm thử timeout

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(Duration.ofSeconds(5))
    )
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify();
~~~

Test xác minh timeout phát lỗi xuống downstream. Có thể thêm `doOnCancel` trước `timeout` để xác minh nguồn nhận cancellation. Virtual time kiểm tra semantics của pipeline mà không phải chờ năm giây thực.

## 15. Những lỗi thường gặp

- **Cho rằng cancel đồng nghĩa I/O đã dừng:** cancellation chỉ được truyền đến mức adapter và API bên dưới hỗ trợ.
- **Coi cancellation là onComplete hoặc onError:** cancel là yêu cầu từ subscriber, không phải terminal signal.
- **Dùng doOnCancel làm bằng chứng server đã hủy request:** hook chỉ quan sát subscription tại vị trí của nó.
- **Cho rằng boundedElastic làm API blocking có thể hủy:** scheduler chỉ cô lập blocking; thư viện có thể bỏ qua interrupt.
- **Dùng timeout như timeout của database/client:** timeout reactive có thể kết thúc downstream trong khi tác vụ bên dưới còn chạy.
- **Coi client disconnect là rollback:** side effect có thể đã được thực hiện ở server.
- **Dùng switchMap cho command có side effect:** hủy kết quả cũ không đảo ngược lệnh đã gửi.
- **Không nối callback handle vào sink cancellation:** Flux dừng phát nhưng listener bên ngoài vẫn hoạt động.
- **Gọi cleanup hai lần:** onCancel và onDispose có thể cùng chạy; cleanup cần idempotent hoặc có cơ chế bảo vệ.
- **Không xử lý callback đến muộn:** callback có thể chạy đồng thời với cancellation và cleanup.
- **Không giới hạn concurrency:** tác vụ I/O không hủy được có thể tích tụ dù downstream đã rời đi.
- **Giả định cancel transaction là rollback thành công:** cần dùng transaction manager và đối soát trạng thái khi kết quả không rõ.

## 16. Quy trình thiết kế khả năng hủy đầu-cuối

Trước khi tuyên bố một thao tác I/O có thể hủy, hãy kiểm tra:

1. Ai có thể hủy subscription: client HTTP, timeout, operator hay component sở hữu Disposable?
2. Cancellation được truyền qua những operator và adapter nào?
3. API I/O có handle cancel, dispose, statement cancel hoặc timeout riêng không?
4. Driver/transport có thực sự gửi lệnh hủy xuống server không?
5. Nếu tác vụ không thể dừng, concurrency và thời gian chạy có được giới hạn không?
6. Resource nào cần cleanup khi cancel và cleanup có bất đồng bộ không?
7. Callback có thể đến sau cancellation không, và adapter có thread-safe không?
8. Side effect đã gửi có cần idempotency hoặc compensation không?
9. Metric nào xác nhận cancellation ở tầng subscription, client và server?
10. Test có phân biệt cancellation của pipeline với việc I/O thật sự dừng không?

Cancellation là một phần thiết yếu của hợp đồng Reactive Streams, giúp downstream ngừng nhận dữ liệu và yêu cầu upstream dừng công việc. Reactor truyền yêu cầu này qua các toán tử và adapter, nhưng khả năng dừng tác vụ I/O phụ thuộc API, transport và driver ở lớp bên dưới. Hãy nối cancellation vào handle của callback/future, dùng `using` hoặc `usingWhen` để giải phóng tài nguyên, cấu hình timeout ở cả tầng reactive lẫn client khi cần, và không xem cancellation là rollback nghiệp vụ. Kiểm thử riêng từng ranh giới sẽ giúp xác định chính xác điều gì đã dừng, điều gì vẫn chạy và tài nguyên nào đã được thu hồi.
