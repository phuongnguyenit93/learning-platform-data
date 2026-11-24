# Xử lý riêng khi hoàn thành, phát lỗi hoặc bị hủy

Một pipeline reactive có thể kết thúc theo nhiều cách: nguồn phát đủ dữ liệu rồi hoàn tất, một bước xử lý phát sinh lỗi, hoặc consumer không còn cần kết quả và hủy subscription. Cả ba trường hợp đều kết thúc vòng đời tiêu thụ, nhưng ý nghĩa nghiệp vụ và việc cần làm khi kết thúc có thể khác nhau. Ví dụ, một giao dịch có thể commit khi hoàn tất, rollback khi lỗi hoặc bị hủy; một bộ đếm metric cần ghi nhận loại kết thúc; một file hoặc connection phải được đóng dù pipeline đi theo nhánh nào.

Trong Reactor, các hook như **doOnComplete**, **doOnError**, **doOnCancel** và **doFinally** cho phép quan sát từng kiểu kết thúc. Khi cần quản lý tài nguyên gắn với subscription, **using** và **usingWhen** cung cấp cấu trúc phù hợp hơn để tạo và giải phóng tài nguyên. Chọn đúng công cụ giúp tránh rò rỉ tài nguyên, tránh coi cancellation như lỗi, và giữ cho các thao tác cleanup không làm sai tín hiệu của pipeline.

## 1. Ba cách kết thúc có ý nghĩa khác nhau

Reactive Streams có hai terminal signal đi từ publisher đến subscriber:

- **onComplete:** publisher hoàn tất bình thường, không còn phần tử nào được phát.
- **onError(error):** publisher kết thúc do lỗi.

Cancellation đi theo hướng ngược lại. Subscriber gọi **cancel()** trên Subscription để yêu cầu dừng nhận dữ liệu. Cancellation không phải terminal signal được publisher gửi đến subscriber; subscriber đã yêu cầu ngừng tiêu thụ nên không nhận onComplete chỉ vì nó hủy.

| Trường hợp | Ai khởi tạo? | Tín hiệu hoặc hành động | Ví dụ xử lý thường cần |
| --- | --- | --- | --- |
| Hoàn thành | Publisher | onComplete | Ghi nhận thành công, commit transaction, đóng tài nguyên |
| Phát lỗi | Publisher | onError(error) | Ghi log lỗi, rollback, giải phóng tài nguyên |
| Bị hủy | Subscriber hoặc toán tử downstream | cancel() truyền ngược về upstream | Dừng tác vụ có thể dừng, rollback nếu phù hợp, gỡ listener, đóng tài nguyên |

Ba trường hợp loại trừ nhau đối với một subscription. Sau onComplete hoặc onError, publisher không được phát thêm dữ liệu. Khi subscription bị hủy, publisher phải tôn trọng yêu cầu và dừng phát thêm tín hiệu cho subscriber đó. Tuy nhiên, cancellation có thể đến trong lúc một callback đang chạy hoặc một thao tác I/O đã được gửi ra ngoài; nó không bảo đảm cắt ngang tức thời công việc đang thực hiện.

## 2. Hook riêng cho từng kiểu kết thúc

Reactor cung cấp các toán tử quan sát vòng đời. Chúng giúp ghi log, cập nhật metric hoặc kích hoạt hành động nhẹ gắn với một tín hiệu cụ thể.

| Toán tử | Khi được gọi | Không được gọi khi |
| --- | --- | --- |
| doOnComplete | Publisher phát onComplete | Lỗi hoặc cancellation |
| doOnSuccess trên Mono | Mono hoàn tất thành công, có thể có giá trị hoặc rỗng | Lỗi hoặc cancellation |
| doOnError | Publisher phát onError | Hoàn tất bình thường hoặc cancellation |
| doOnCancel | Subscription nhận yêu cầu cancellation | Hoàn tất bình thường hoặc lỗi |
| doOnTerminate | Trước khi onComplete hoặc onError được chuyển downstream | Cancellation |
| doAfterTerminate | Sau khi onComplete hoặc onError đã được chuyển downstream | Cancellation |
| doFinally | Sau complete, error hoặc cancel | Không bỏ sót ba kiểu kết thúc này |

Ví dụ quan sát riêng từng nhánh:

~~~java
Flux<OrderEvent> observed = orderEvents
    .doOnComplete(() -> metrics.increment("orders.stream.completed"))
    .doOnError(error -> log.error("Order stream failed", error))
    .doOnCancel(() -> metrics.increment("orders.stream.cancelled"))
    .doFinally(signal -> log.debug("Order stream ended: {}", signal));
~~~

doOnComplete chỉ ghi nhận hoàn tất bình thường. doOnError nhận được exception để ghi log hoặc phân loại lỗi. doOnCancel chỉ quan sát yêu cầu hủy. doFinally nhận một SignalType cho biết kết thúc bằng ON_COMPLETE, ON_ERROR hay CANCEL.

Các hook được đặt tại một vị trí trong pipeline và quan sát tín hiệu tại vị trí đó. Thứ tự hook vì vậy có ý nghĩa. Một toán tử phía trên take(1) có thể quan sát cancellation upstream, trong khi toán tử phía dưới take(1) quan sát hoàn tất downstream:

~~~java
Flux<Long> result = Flux.interval(Duration.ofMillis(100))
    .doFinally(signal -> log.info("Upstream: {}", signal))
    .take(1)
    .doFinally(signal -> log.info("Downstream: {}", signal));
~~~

Khi nhận một phần tử, take(1) hoàn tất phía downstream và hủy upstream vì không cần phần tử tiếp theo. Hook phía trên take có thể nhận CANCEL; hook phía dưới quan sát ON_COMPLETE. Cùng một pipeline có thể vì thế có hai góc nhìn vòng đời khác nhau.

## 3. Phân biệt hook quan sát với cleanup tài nguyên

Hook như doOnComplete, doOnError, doOnCancel và doFinally hữu ích để quan sát hoặc thực hiện hành động đồng bộ, nhẹ. Nhưng chúng không tự quản lý quyền sở hữu tài nguyên. Nếu mở connection trước khi tạo publisher rồi đóng connection trong một hook, có thể xảy ra lỗi khi publisher không bao giờ được subscribe, được subscribe nhiều lần hoặc bị hủy giữa chừng.

Ví dụ cần tránh:

~~~java
Connection connection = connectionFactory.open();

return Flux.from(connection.readRows())
    .doFinally(signal -> connection.close());
~~~

Connection được mở ngay khi phương thức chạy, kể cả khi caller không subscribe publisher trả về. Nếu publisher được subscribe nhiều lần, các subscription có thể dùng chung một connection. Nếu cleanup không được gắn đúng với vòng đời tài nguyên, connection có thể bị đóng quá sớm hoặc không được đóng.

Một quy tắc hữu ích:

- Dùng hook để ghi nhận tín hiệu, cập nhật metric hoặc chạy hành động ngắn không sở hữu tài nguyên phức tạp.
- Dùng using khi tài nguyên được tạo đồng bộ cho mỗi subscription và cleanup cũng đồng bộ.
- Dùng usingWhen khi tạo hoặc cleanup tài nguyên là bất đồng bộ, ví dụ session hoặc connection reactive.

Không dùng doFinally để chờ một thao tác cleanup bất đồng bộ. Callback của doFinally là callback đồng bộ và không trả về publisher cleanup để Reactor compose. Nếu việc đóng tài nguyên cần I/O hoặc cần chờ hoàn tất, hãy dùng usingWhen.

## 4. Dùng doFinally để quan sát mọi kiểu kết thúc

doFinally nhận một callback với SignalType. Nó hữu ích khi cùng một hành động quan sát cần chạy sau complete, error và cancel, chẳng hạn giải phóng một permit đồng bộ hoặc ghi nhận thời gian sống của subscription.

~~~java
AtomicLong startedAt = new AtomicLong();

Flux<Result> results = source
    .doOnSubscribe(subscription -> startedAt.set(System.nanoTime()))
    .doFinally(signal -> {
        long elapsed = System.nanoTime() - startedAt.get();
        metrics.record("pipeline.duration.nanos", elapsed);
        metrics.increment("pipeline.termination." + signal.name());
    });
~~~

Đoạn mã minh họa metric thời gian và loại kết thúc. Với publisher được subscribe đồng thời nhiều lần, không dùng một biến mutable dùng chung như AtomicLong cho tất cả subscription vì thời điểm bắt đầu có thể bị ghi đè. Hãy đặt state theo từng subscription, hoặc dùng một đối tượng context riêng cho mỗi lần đăng ký.

doFinally chạy sau khi terminal signal đã được chuyển downstream; với cancellation, nó chạy sau khi yêu cầu hủy được xử lý tại vị trí toán tử. Vì vậy, nếu downstream cần thấy trạng thái đã cập nhật trước khi nhận complete/error, hãy chọn hook trước terminal signal như doOnComplete hoặc doOnError theo mục đích. Nếu chỉ cần quan sát kết thúc tổng thể, doFinally thường phù hợp.

doFinally không thay thế cleanup có thể thất bại hoặc cần bất đồng bộ. Một callback dài, blocking hoặc ném exception có thể làm ảnh hưởng thread đang xử lý tín hiệu và khiến lỗi phụ khó quan sát. Giữ hook ngắn, không blocking và dùng abstraction quản lý tài nguyên cho công việc đóng/mở thực sự.

## 5. Dùng using cho tài nguyên đồng bộ

using gắn một tài nguyên với một subscription. Reactor gọi resource supplier để tạo tài nguyên, gọi source supplier để tạo publisher sử dụng tài nguyên, rồi gọi cleanup khi publisher hoàn tất, phát lỗi hoặc bị hủy.

~~~java
Flux<Row> rows = Flux.using(
    () -> cursorRepository.openCursor(query),
    cursor -> cursor.readRows(),
    Cursor::close
);
~~~

Ví dụ giả định openCursor tạo cursor đồng bộ, readRows trả về Flux<Row> và close giải phóng cursor đồng bộ. Mỗi subscription tạo một cursor riêng; cleanup được gắn với vòng đời của publisher sử dụng cursor đó.

Điều này giải quyết hai vấn đề:

1. Tài nguyên chỉ được tạo khi có subscription, thay vì được mở ngay lúc khai báo pipeline.
2. Cleanup được gọi trên các đường complete, error và cancel, nên caller không phải tự ghép ba hook riêng lẻ.

Nếu việc tạo cursor có thể ném exception, lỗi khởi tạo được truyền thành lỗi của subscription; source supplier không được gọi khi không có tài nguyên để sử dụng. Nếu cleanup đồng bộ có thể blocking, cần xem xét nơi thực thi để không chặn event-loop.

### using không làm cho thao tác blocking trở thành non-blocking

using quản lý vòng đời tài nguyên; nó không thay đổi tính chất của API. Nếu openCursor, readRows hoặc close là blocking, pipeline vẫn có thể chặn thread. Cần cô lập toàn bộ thao tác blocking tại ranh giới phù hợp, thường bằng subscribeOn(Schedulers.boundedElastic()) cho nguồn blocking, và tránh chạy cleanup blocking trên event-loop.

## 6. Dùng usingWhen cho tài nguyên bất đồng bộ

Một số tài nguyên cần được mở hoặc đóng bằng publisher, ví dụ connection R2DBC, session reactive hoặc transaction bất đồng bộ. usingWhen cho phép định nghĩa publisher cleanup riêng cho ba trường hợp:

- asyncComplete: cleanup khi source hoàn tất bình thường.
- asyncError: cleanup khi source phát lỗi; callback nhận cả resource và lỗi gốc.
- asyncCancel: cleanup khi subscription bị hủy.

Ví dụ quản lý một session:

~~~java
Flux<Row> rows = Flux.usingWhen(
    sessionFactory.open(),
    session -> session.query(sql),
    Session::close,
    (session, error) -> session.close(),
    Session::close
);
~~~

Ví dụ giả định open() trả về Publisher<Session>, query trả về publisher các hàng dữ liệu và close() trả về publisher hoàn tất khi đóng session. Mỗi nhánh kết thúc dùng cleanup reactive tương ứng. Trong ví dụ đơn giản, cả ba nhánh đều đóng session; trong một transaction, complete có thể commit rồi đóng, còn error/cancel có thể rollback rồi đóng.

Ví dụ transaction:

~~~java
Flux<Row> rows = Flux.usingWhen(
    connectionFactory.create(),
    connection -> connection.query(sql),
    connection -> connection.commit().then(connection.close()),
    (connection, error) ->
        connection.rollback().then(connection.close()),
    connection ->
        connection.rollback().then(connection.close())
);
~~~

Đây là mẫu minh họa và giả định các phương thức commit, rollback và close trả về publisher hoàn tất. Trong ứng dụng thật, cần bảo đảm connection vẫn được đóng nếu commit hoặc rollback thất bại; cần định nghĩa cách kết hợp lỗi cleanup với lỗi gốc, timeout cho cleanup và metric/cảnh báo khi giải phóng tài nguyên không thành công. Không để một lỗi rollback khiến connection bị bỏ lại mà không có cơ chế đóng hoặc thu hồi.

usingWhen điều phối cleanup bất đồng bộ theo nhánh kết thúc và gắn nó với vòng đời resource. Vì cleanup có thể cần thời gian, tín hiệu kết thúc của source được phối hợp với quá trình cleanup theo semantics của operator. Khi cancellation xảy ra, downstream đã yêu cầu ngừng tiêu thụ nên không nhận một onComplete thay thế; nhánh cleanup cancellation vẫn cần được chạy và kiểm thử riêng.

## 7. Xử lý lỗi cleanup

Cleanup cũng là một thao tác có thể thất bại. Ví dụ, đóng connection có thể gặp lỗi mạng; ghi log audit có thể không truy cập được storage; rollback có thể thất bại vì connection đã mất.

Khi cleanup lỗi, cần xác định chính sách:

- Nếu source hoàn tất nhưng cleanup thất bại, ứng dụng có nên coi toàn bộ thao tác là thất bại không?
- Nếu source đã lỗi và cleanup cũng lỗi, lỗi nào là lỗi chính, lỗi nào được ghi nhận bổ sung?
- Nếu cancellation xảy ra, cleanup lỗi sẽ được quan sát và cảnh báo ở đâu khi downstream không còn nhận terminal signal?
- Có cần retry cleanup không, và retry có an toàn/idempotent không?
- Có cơ chế timeout để cleanup không treo vô hạn không?

Không nên âm thầm bỏ qua lỗi cleanup quan trọng. Với connection pool, lỗi đóng hoặc trả connection có thể gây rò rỉ slot và làm cạn pool. Với transaction, lỗi rollback cần được ghi nhận vì trạng thái dữ liệu có thể không rõ ràng. Cần dùng logging/metric có correlation ID để liên kết lỗi cleanup với subscription và thao tác nghiệp vụ ban đầu.

Với usingWhen, các publisher cleanup phải được thiết kế để hoàn tất hữu hạn và xử lý lỗi rõ ràng. Nếu cần giữ lỗi gốc cùng lỗi cleanup, hãy dùng cách biểu diễn lỗi hoặc logging phù hợp thay vì vô tình ghi đè thông tin nguyên nhân.

## 8. Cancellation không đồng nghĩa với lỗi

Khi consumer gọi dispose() hoặc framework hủy subscription, doOnCancel và doFinally(CANCEL) có thể quan sát việc hủy. doOnError không chạy chỉ vì cancellation; cancellation không phải một exception.

~~~java
Disposable subscription = Flux.interval(Duration.ofSeconds(1))
    .doOnCancel(() -> log.info("Consumer không cần dữ liệu nữa"))
    .doFinally(signal -> log.info("Nguồn kết thúc: {}", signal))
    .subscribe(this::handleTick);

// Khi component kết thúc vòng đời:
subscription.dispose();
~~~

Đối với luồng dài hạn do component tự sở hữu, hãy giữ Disposable và dispose khi component không còn cần dữ liệu. Với request được quản lý bởi Spring WebFlux, thường nên trả publisher để framework truyền cancellation khi client ngắt kết nối. Không tự subscribe trong service chỉ để bắt đầu chạy, vì subscription riêng đó có thể sống lâu hơn request và không còn được caller quản lý.

Cancellation cũng không bảo đảm thu hồi side effect đã gửi ra hệ thống khác. Nếu request thanh toán đã đến server, việc client hủy chờ response không có nghĩa thanh toán đã rollback. Với thao tác có side effect, cần idempotency key, truy vấn trạng thái hoặc quy trình bù trừ nghiệp vụ.

## 9. Toán tử take: downstream hoàn tất, upstream bị hủy

Một trường hợp dễ gây nhầm là toán tử downstream tự kết thúc sau khi nhận đủ dữ liệu. Ví dụ:

~~~java
Flux<Long> firstTick = Flux.interval(Duration.ofSeconds(1))
    .doOnCancel(() -> log.info("Interval bị hủy"))
    .take(1)
    .doOnComplete(() -> log.info("Consumer đã nhận đủ một tick"));
~~~

Sau phần tử đầu tiên, take(1) phát onComplete cho downstream và hủy subscription upstream để ngăn tick tiếp theo. Vì vậy, cùng một luồng có thể quan sát cancellation ở phía nguồn và completion ở phía consumer.

Điều này có ý nghĩa khi quản lý tài nguyên: resource gắn với nguồn cần được giải phóng khi take hủy upstream, dù consumer cuối cùng nhìn thấy hoàn tất bình thường. using và usingWhen giúp gắn cleanup với vòng đời nguồn thay vì chỉ dựa vào terminal signal mà subscriber cuối cùng nhận.

## 10. Không dùng doOnComplete/doOnError để thay thế cleanup chung

Nếu chỉ đóng tài nguyên trong doOnComplete, tài nguyên có thể bị rò rỉ khi publisher phát lỗi hoặc bị hủy. Nếu chỉ đóng trong doOnError, tài nguyên bị rò rỉ khi hoàn tất bình thường hoặc cancellation. Nếu lặp lại cùng một lệnh cleanup trong cả ba hook, rất dễ bỏ sót một nhánh hoặc gọi cleanup nhiều lần khi logic phức tạp.

Mẫu nên tránh:

~~~java
return source
    .doOnComplete(resource::close)
    .doOnError(error -> resource.close())
    .doOnCancel(resource::close);
~~~

Mẫu này còn có nguy cơ close() ném exception hoặc chạy trên thread không phù hợp. Nếu resource được tạo cho subscription, hãy để using hoặc usingWhen quản lý quyền sở hữu và cleanup. Chỉ dùng các hook riêng khi cần hành động quan sát theo từng kiểu kết thúc.

## 11. Cleanup phần tử bị loại bỏ trong pipeline

Ngoài việc cleanup toàn bộ resource của subscription, một số toán tử có thể loại bỏ phần tử đã được prefetch hoặc buffer khi cancellation, filtering hoặc thay đổi luồng xảy ra. Nếu mỗi phần tử giữ một tài nguyên riêng, ví dụ buffer chứa payload có reference-count hoặc đối tượng cần release, cần xem xét hook doOnDiscard tại vị trí phù hợp.

~~~java
Flux<Payload> payloads = source
    .filter(Payload::isValid)
    .doOnDiscard(Payload.class, Payload::release);
~~~

Ví dụ giả định Payload có phương thức release() và các toán tử trên đường đi hỗ trợ discard hook theo semantics của Reactor. doOnDiscard không phải cleanup chung cho mọi object; nó chỉ xử lý những phần tử bị một số toán tử loại bỏ và được thông báo theo cơ chế discard. Hãy kiểm tra toán tử nào hỗ trợ hook này và tránh release một object vẫn còn được consumer khác sở hữu.

## 12. Kiểm thử từng kiểu kết thúc

Một bộ test tốt cần xác minh hành động quan sát và cleanup cho cả complete, error và cancel. StepVerifier cho phép điều khiển terminal signal; AtomicBoolean hoặc counter có thể dùng để kiểm tra hook đã chạy.

### Kiểm tra completion

~~~java
AtomicBoolean completed = new AtomicBoolean();
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

Flux<Integer> source = Flux.just(1, 2)
    .doOnComplete(() -> completed.set(true))
    .doFinally(finalSignal::set);

StepVerifier.create(source)
    .expectNext(1, 2)
    .verifyComplete();

assertTrue(completed.get());
assertEquals(SignalType.ON_COMPLETE, finalSignal.get());
~~~

### Kiểm tra error

~~~java
AtomicBoolean failed = new AtomicBoolean();
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

Flux<Integer> source = Flux.<Integer>error(
        new IllegalStateException("storage unavailable"))
    .doOnError(error -> failed.set(true))
    .doFinally(finalSignal::set);

StepVerifier.create(source)
    .expectError(IllegalStateException.class)
    .verify();

assertTrue(failed.get());
assertEquals(SignalType.ON_ERROR, finalSignal.get());
~~~

### Kiểm tra cancellation

~~~java
AtomicBoolean cancelled = new AtomicBoolean();
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

Flux<Long> source = Flux.interval(Duration.ofSeconds(1))
    .doOnCancel(() -> cancelled.set(true))
    .doFinally(finalSignal::set);

StepVerifier.create(source)
    .thenCancel()
    .verify();

assertTrue(cancelled.get());
assertEquals(SignalType.CANCEL, finalSignal.get());
~~~

Các ví dụ giả định đã import Reactor, Reactor Test, JUnit assertions và các kiểu Java cần thiết. Không dùng Thread.sleep để chờ cancellation; thenCancel điều khiển việc hủy trong test. Với timer, có thể dùng withVirtualTime để kiểm tra thời gian mà không phụ thuộc tốc độ máy.

### Kiểm tra using giải phóng resource

Có thể xác minh cleanup được gọi khi hoàn tất, lỗi và cancellation. Ví dụ kiểm tra cancellation:

~~~java
AtomicBoolean closed = new AtomicBoolean();

class TestResource {
    void close() {
        closed.set(true);
    }
}

StepVerifier.withVirtualTime(() ->
    Flux.using(
        TestResource::new,
        resource -> Flux.interval(Duration.ofSeconds(1)),
        TestResource::close
    )
)
    .thenCancel()
    .verify();

assertTrue(closed.get());
~~~

Nguồn timer được tạo bên trong supplier của withVirtualTime để scheduler ảo được cài trước khi publisher tạo timer. Đoạn minh họa nhấn mạnh việc cleanup khi hủy; nên có test riêng cho complete và error để xác minh cả ba nhánh. Với usingWhen, cần kiểm tra publisher cleanup tương ứng được subscribe và hoàn tất, đồng thời kiểm tra trường hợp cleanup lỗi.

## 13. Checklist chọn hook và resource operator

| Nhu cầu | Công cụ nên cân nhắc |
| --- | --- |
| Chỉ ghi nhận hoàn tất bình thường | doOnComplete hoặc doOnSuccess với Mono |
| Ghi nhận lỗi cùng exception | doOnError |
| Ghi nhận yêu cầu hủy | doOnCancel |
| Ghi nhận mọi kiểu kết thúc | doFinally |
| Hành động sau complete/error, không cần cancel | doAfterTerminate |
| Tạo và đóng resource đồng bộ theo subscription | using |
| Tạo và cleanup resource bất đồng bộ | usingWhen |
| Giải phóng phần tử bị discard bởi toán tử hỗ trợ | doOnDiscard |

Trước khi triển khai, hãy xác định:

1. Ai sở hữu resource và subscription?
2. Resource được tạo khi assembly hay khi subscribe?
3. Cleanup cần chạy ở complete, error và cancel như thế nào?
4. Cleanup là đồng bộ hay bất đồng bộ? Có blocking không?
5. Cleanup có thể thất bại, timeout hoặc cần retry không?
6. Cancellation có thể đến trong khi callback hoặc I/O đang chạy không?
7. Có phần tử bị discard cần giải phóng riêng không?
8. Test có xác minh đủ ba nhánh và lỗi cleanup không?

## 14. Những lỗi thường gặp

- **Coi cancellation là onError:** cancel là yêu cầu từ subscriber, không phải exception terminal.
- **Chỉ cleanup trong doOnComplete:** tài nguyên có thể rò rỉ khi lỗi hoặc bị hủy.
- **Chỉ cleanup trong doOnError:** bỏ sót hoàn tất và cancellation.
- **Dùng doFinally cho cleanup bất đồng bộ:** callback không trả publisher để chờ thao tác đóng; dùng usingWhen.
- **Mở resource trước subscription:** publisher có thể không bao giờ được subscribe hoặc bị subscribe nhiều lần; tạo resource bên trong using/usingWhen.
- **Dùng chung một resource mutable giữa nhiều subscription:** có thể đóng resource khi subscription khác vẫn đang sử dụng.
- **Giả định dispose ngắt callback đang chạy:** cancellation không tự interrupt thread hoặc rollback I/O đã gửi.
- **Không kiểm tra lỗi cleanup:** connection hoặc transaction có thể ở trạng thái không rõ ràng.
- **Nhầm complete downstream với complete upstream:** toán tử như take có thể complete downstream sau khi cancel upstream.
- **Dùng doOnDiscard như cleanup cho mọi object:** chỉ phần tử bị discard qua toán tử hỗ trợ mới được xử lý bởi hook này.
- **Chặn event-loop trong cleanup:** đóng tài nguyên blocking trên thread quan trọng có thể làm nghẽn các request khác.

## 15. Ghi nhớ khi quản lý vòng đời

Hoàn tất, lỗi và cancellation là ba nhánh khác nhau của vòng đời subscription. doOnComplete, doOnError và doOnCancel quan sát riêng từng nhánh; doFinally quan sát tất cả và cho biết loại kết thúc. Các hook phù hợp với logging, metric và hành động đồng bộ nhẹ. Khi tài nguyên được tạo cho từng subscription, using quản lý resource đồng bộ còn usingWhen quản lý resource có cleanup bất đồng bộ và cho phép định nghĩa riêng nhánh complete, error, cancel.

Hãy gắn quyền sở hữu tài nguyên với subscription, giải phóng nó trong mọi đường kết thúc, xác định cách xử lý khi cleanup thất bại và kiểm thử cả ba nhánh. Đặc biệt, cancellation không phải rollback: các side effect đã gửi đến hệ thống bên ngoài cần idempotency, đối soát hoặc cơ chế bù trừ riêng. Thiết kế lifecycle rõ ràng giúp pipeline Reactor giữ được tính đúng đắn khi request hoàn tất, gặp lỗi hoặc không còn consumer cần kết quả.
