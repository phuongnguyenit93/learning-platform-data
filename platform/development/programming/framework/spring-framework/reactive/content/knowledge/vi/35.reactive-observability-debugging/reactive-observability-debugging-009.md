# Nhận diện dropped error, rò rỉ bộ đệm và chuỗi không được đăng ký

## 1. Ba sự cố khác nhau trong ứng dụng Reactor

Một ứng dụng reactive có thể trả kết quả sai, log lỗi không rõ nguồn, tăng direct memory hoặc không thực hiện câu SQL/HTTP mà lập trình viên tưởng rằng đã gọi. Ba khái niệm trong đề bài liên quan nhau nhưng không đồng nghĩa:

1. **Dropped error:** một lỗi đến quá muộn hoặc không còn đường truyền hợp lệ tới subscriber, thường vì sequence đã complete, error hoặc bị cancel. Lỗi đó không còn được chuyển qua tín hiệu onError của chuỗi như một lỗi thông thường.
2. **Buffer leak:** một DataBuffer/Netty ByteBuf được giữ reference count lớn hơn 0 sau khi không còn ai cần dùng. Bộ nhớ native/direct không được trả về pool.
3. **Unsubscribed chain:** một Mono/Flux đã được tạo và có thể đã ghép nhiều operator, nhưng không có subscriber nào bắt đầu thực thi nó. Với cold Publisher, side effect như gọi database, HTTP hoặc đọc file chưa xảy ra.

| Triệu chứng | Câu hỏi cần đặt ra | Công cụ/điểm kiểm tra |
| --- | --- | --- |
| Log Dropped error hoặc lỗi đến sau timeout | Có error signal đến sau complete/cancel không? | Hooks.onErrorDropped, doFinally, callback lifecycle |
| Netty báo LEAK: ByteBuf.release() was not called | Ai đang sở hữu buffer và ai phải release? | DataBufferUtils, doOnDiscard, Netty leak detector |
| Không có request SQL/HTTP, doOnSubscribe không chạy | Publisher đã được subscribe chưa? | StepVerifier, PublisherProbe, doOnSubscribe |
| Direct memory tăng nhưng heap bình thường | Có buffer pooled chưa release, hay pool chỉ đang giữ vùng nhớ tái sử dụng? | Active direct memory metric, leak detector, ref count |

**Nguyên tắc chẩn đoán:** xác định lifecycle trước, sau đó xác định quyền sở hữu resource. Không dùng một global hook để che lỗi nghiệp vụ, không release buffer chỉ vì thấy nó trong log, và không gọi subscribe() để ép Publisher chạy khi chưa hiểu ai quản lý subscription.

## 2. Vòng đời Publisher: assembly, subscription và termination

### 2.1. Tạo chuỗi chưa có nghĩa là chuỗi đã chạy

Reactor operator thường tạo một Publisher mới. Cold Publisher chỉ thực thi khi có subscriber:

~~~java
AtomicInteger executions = new AtomicInteger();

Mono<Integer> source = Mono.defer(() -> {
    executions.incrementAndGet();
    return Mono.just(21);
});

Mono<Integer> result = source.map(value -> value * 2);

System.out.println(executions.get()); // 0
~~~

Khi chưa subscribe, Mono.defer chưa chạy. Khi subscriber yêu cầu dữ liệu:

~~~java
StepVerifier.create(result)
    .expectNext(42)
    .verifyComplete();

System.out.println(executions.get()); // 1
~~~

Trong Spring WebFlux, framework subscribe Publisher được trả về từ handler/controller. Với Spring Data R2DBC, câu SQL thường bắt đầu khi Publisher repository được subscribe. Không cần tự gọi subscribe() trong controller/service rồi trả Mono.empty().

Không phải mọi Publisher đều cold: Sinks.Many, event listener và một số hot source có thể phát dữ liệu độc lập với subscriber. Cần hiểu semantics của source thay vì mặc định mọi Publisher đều lazy.

### 2.2. Các giai đoạn chính

~~~text
ASSEMBLY
  Flux.just(...).map(...).filter(...).checkpoint(...)
      |
      | chỉ tạo cấu trúc Publisher
      v
SUBSCRIBE
  subscriber đăng ký, source bắt đầu thực thi
      |
      v
REQUEST(n)
  downstream yêu cầu số item có thể nhận
      |
      +------ onNext(item) ------> 0..n lần
      |
      +------ onError(error) ----> lỗi bình thường
      |
      +------ onComplete --------> hoàn tất thành công
      |
      +------ cancel ------------> downstream không còn cần dữ liệu
~~~

Một chuỗi có thể được tạo mà không subscribe; cũng có thể subscribe rồi cancel trước khi source hoàn tất. Hai trường hợp có lifecycle và tác động resource khác nhau.

### 2.3. doOnSubscribe và doFinally

~~~java
Mono<String> pipeline = remoteCall()
    .doOnSubscribe(subscription -> log.info("subscribed"))
    .doOnError(error -> log.error("pipeline failed", error))
    .doFinally(signal -> log.info("terminated: {}", signal));
~~~

- doOnSubscribe chạy khi subscriber đăng ký.
- doOnError quan sát error signal nhưng vẫn để lỗi đi tiếp downstream.
- doFinally chạy khi sequence kết thúc hoặc bị cancel; SignalType phân biệt ON_COMPLETE, ON_ERROR và CANCEL.

Đây là công cụ chẩn đoán lifecycle hữu ích. Đừng đặt log chứa token, payload cá nhân hoặc dữ liệu nhạy cảm trong callback dùng chung.

## 3. Dropped error: lỗi không còn đường truyền tới subscriber

### 3.1. Error bình thường khác dropped error

Một lỗi trong operator thông thường vẫn có thể được truyền qua Reactive Streams onError:

~~~java
Mono<Integer> result = Mono.just("not-a-number")
    .map(Integer::parseInt)
    .doOnError(error -> log.warn("parse failed", error))
    .onErrorResume(NumberFormatException.class, error -> Mono.just(0));
~~~

map phát sinh NumberFormatException; doOnError quan sát lỗi; onErrorResume thay thế lỗi bằng giá trị 0. Đây là error handling bình thường, không phải dropped error.

Hooks.onOperatorError là hook dành cho exception phát sinh trong lúc operator xử lý tín hiệu. Reactor có thể biến đổi/quan sát exception rồi tiếp tục truyền nó qua onError. Nó khác với Hooks.onErrorDropped.

### 3.2. Khi nào một error bị drop?

Sau khi subscriber đã nhận onComplete hoặc onError, không được gửi thêm terminal signal thứ hai. Tương tự, nếu subscriber đã cancel, một callback bất đồng bộ đến muộn có thể cố phát error trong lúc downstream không còn nhận tín hiệu.

Ví dụ về source sai hợp đồng:

~~~java
Flux<String> malformed = Flux.create(sink -> {
    sink.complete();
    sink.error(new IllegalStateException("late callback error"));
});
~~~

complete() đã kết thúc sequence. error(...) đến sau đó không thể trở thành onError thứ hai cho subscriber. Reactor chuyển lỗi đó qua dropping strategy; đây là trường hợp phù hợp để quan sát bằng Hooks.onErrorDropped.

Các nguồn gốc thực tế:

- Callback từ SDK bên thứ ba phát lỗi sau khi request đã timeout/cancel.
- Bridge giữa callback API và Flux.create không dừng listener sau khi downstream hủy.
- Một Publisher/custom operator vi phạm quy tắc chỉ có một terminal signal.
- Resource cleanup hoặc async callback phát error sau khi downstream đã kết thúc.
- Nhiều nguồn cạnh tranh; một nguồn đã thắng và kết thúc sequence, nguồn khác phát lỗi muộn.

Cancel tự nó không phải lỗi. Một Publisher tuân thủ cancellation sẽ ngừng phát tín hiệu; chỉ tín hiệu đến muộn hoặc vi phạm lifecycle mới tạo tình huống dropped.

### 3.3. Hooks.onErrorDropped

~~~java
Hooks.onErrorDropped(error ->
    log.error("Reactor dropped a late error", error)
);
~~~

Hook này là global cho Reactor trong JVM. Có thể dùng để ghi nhận late error, thống kê, hoặc cleanup resource gắn với một lỗi bị drop. Các điểm cần nhớ:

- Đây không phải nơi thay thế onErrorResume cho lỗi nghiệp vụ.
- Nó không thể đưa lỗi quay lại subscriber đã kết thúc.
- Đăng ký một lần tại bootstrap/configuration, tránh đăng ký lặp làm log trùng.
- Hook có tính cộng dồn; test phải dọn hook global sau khi chạy.
- Không ghi raw payload/secret trong log.
- Khi cleanup object reference-counted, phải kiểm tra đúng kiểu và bảo đảm cleanup idempotent.

Trong Reactor 3.7, dropped error mặc định thường được ghi log ở mức ERROR nếu không có consumer tùy chỉnh. Hành vi mặc định có thể thay đổi theo version; hãy đối chiếu Javadoc của Reactor version mà ứng dụng đang chạy.

### 3.4. Phân biệt ba hook

| Hook | Được gọi khi | Vai trò |
| --- | --- | --- |
| Hooks.onErrorDropped | Error không thể truyền tiếp vì đã terminal/cancel hoặc nguồn phát tín hiệu không hợp lệ | Quan sát/cleanup late error |
| Hooks.onNextDropped | Item đến khi operator không còn chờ item, thường sau terminal signal hoặc cancellation | Quan sát/cleanup item bị drop |
| Hooks.onOperatorError | Exception phát sinh khi operator xử lý onNext/onError/onComplete | Quan sát/biến đổi lỗi vẫn có thể truyền qua onError |
| doOnDiscard | Operator chủ động loại bỏ item theo semantics bình thường hoặc dọn queue khi cancel/error | Cleanup item bị discard trong một chain cụ thể |

onNextDropped không phải hook cho mọi item bị filter loại bỏ. Với các trường hợp filter/skip bình thường, dùng doOnDiscard nếu kiểu dữ liệu cần cleanup.

### 3.5. Không nhầm dropped error với subscribe() thiếu error consumer

~~~java
Mono.error(new IllegalStateException("failure"))
    .subscribe();
~~~

Overload subscribe() này không cung cấp consumer xử lý error. Reactor phải dùng default error handling strategy; vì thế lỗi có thể được log/bubble theo cấu hình/version. Không nên kết luận rằng mọi lỗi từ subscribe() thiếu error consumer đều chính là onErrorDropped.

Cách rõ ràng hơn nếu thật sự sở hữu subscription ở ranh giới imperative:

~~~java
Disposable task = operation.subscribe(
    value -> handle(value),
    error -> log.error("background task failed", error)
);
~~~

Caller phải quản lý Disposable, cancellation, shutdown và error policy. Trong business service/controller, ưu tiên trả Publisher cho caller/framework thay vì tự subscribe.

## 4. Xử lý late callback và cleanup đúng lifecycle

### 4.1. Bridge callback API

Khi chuyển một callback API thành Flux, phải liên kết cancellation/disposal của Reactor với việc dừng callback listener:

~~~java
Flux<Event> events = Flux.create(sink -> {
    ExternalListener listener = externalApi.register(
        event -> {
            if (!sink.isCancelled()) {
                sink.next(event);
            }
        },
        error -> {
            if (!sink.isCancelled()) {
                sink.error(error);
            } else {
                log.warn("Late callback error after cancellation", error);
            }
        }
    );

    sink.onDispose(listener::close);
});
~~~

Đây là đoạn minh họa; ExternalListener và externalApi đại diện API bên ngoài. Trong code thực tế:

- close()/cancel() phải dừng đăng ký listener và giải phóng resource.
- Cleanup nên idempotent vì có thể được gọi ở nhiều nhánh lifecycle.
- Không gửi onNext hoặc onError sau terminal signal.
- Nếu API có callback đồng thời, cần serialize tín hiệu hoặc dùng đúng sink flavor.
- Không chỉ kiểm tra isCancelled() rồi bỏ qua error mà không ghi nhận; lỗi muộn vẫn cần observability phù hợp.

### 4.2. onCancel và onDispose

FluxSink.onCancel(...) chỉ dành cho cancellation. onDispose(...) chạy khi sink kết thúc hoặc bị cancel. Chọn callback theo lifecycle của resource; nếu cả hai cùng đóng một resource, implementation close phải an toàn khi gọi lặp.

~~~java
Flux<String> bridge = Flux.create(sink -> {
    ExternalSubscription subscription = externalApi.subscribe(sink::next);

    sink.onCancel(subscription::cancel);
    sink.onDispose(subscription::close);
});
~~~

Đoạn trên chỉ là cấu trúc minh họa. Nếu cancel() và close() cùng tác động một resource, phải bảo đảm hai thao tác không gây double-free hoặc lỗi do đóng hai lần.

### 4.3. doFinally không thay thế cleanup của resource sở hữu

doFinally phù hợp để đo thời gian, ghi signal type hoặc kích hoạt cleanup idempotent. Với resource có quy tắc ownership cụ thể, ưu tiên using, usingWhen, doOnDiscard hoặc API quản lý resource chuyên dụng. Đừng dựa vào một callback logging để thay thế release buffer.

### 4.4. Error recovery phải có chủ đích

- doOnError: quan sát, sau đó error tiếp tục đi downstream.
- onErrorMap: đổi loại exception rồi vẫn phát error.
- onErrorResume: subscribe Publisher dự phòng và thay thế error.
- onErrorComplete: biến error thành completion; chỉ dùng nếu nghiệp vụ thật sự cho phép bỏ qua lỗi.
- Hooks.onErrorDropped: quan sát error đã không còn đường truyền; không phải recovery.

Nuốt lỗi bằng onErrorComplete hoặc onErrorResume(... -> Mono.empty()) có thể che giấu lỗi nghiệp vụ. Log, metric và kết quả trả về cần phản ánh rõ việc một phần tử đã bị bỏ qua.

## 5. Rò rỉ bộ đệm: DataBuffer, ByteBuf và direct memory

### 5.1. Vì sao buffer cần quản lý thủ công?

Netty dùng ByteBuf reference-counted để tái sử dụng vùng nhớ, đặc biệt là direct/off-heap memory cho network I/O. Spring WebFlux cung cấp abstraction DataBuffer; một implementation như NettyDataBuffer có thể bọc ByteBuf pooled.

Quy tắc reference count cơ bản:

~~~text
allocate buffer
    refCnt = 1
       |
       +-- retain()  -> refCnt = 2
       |
       +-- release() -> refCnt = 1
       |
       +-- release() -> refCnt = 0
                         |
                         v
                 buffer được deallocate/return pool
~~~

- retain() tăng reference count khi một component cần giữ thêm ownership.
- release() giảm reference count.
- Khi count về 0, vùng nhớ được trả về allocator/pool.
- Đọc buffer sau khi count đã về 0 có thể gây IllegalReferenceCountException.
- Không release buffer mà framework/consumer khác vẫn đang sở hữu.
- Không quên release buffer mà custom code đã nhận quyền sở hữu cuối cùng.

Một object đã không còn reachable trên Java heap nhưng reference count vẫn lớn hơn 0 vẫn có thể giữ native memory; garbage collector không thay thế việc release.

### 5.2. Khi nào WebFlux application cần quan tâm?

Các codec chuẩn thường tự quản lý DataBuffer khi chuyển đổi sang DTO, String hoặc byte array. Ứng dụng thường chỉ cần chú ý khi:

- Tự đọc/ghi DataBuffer trực tiếp.
- Viết custom encoder/decoder.
- Giữ buffer trong field, collection hoặc queue.
- Dùng filter, skip, prefetch hoặc operator có thể discard item.
- Hủy stream khi buffer đã được prefetch nhưng chưa phát downstream.
- Tạo buffer thủ công hoặc gọi retain().

Không tự release buffer đã được codec/framework tiêu thụ hoặc chuyển ownership cho nơi khác. Double-release cũng là bug.

### 5.3. DataBufferUtils.release và retain

~~~java
DataBufferUtils.release(buffer);
DataBufferUtils.retain(buffer);
~~~

Các utility này chỉ áp dụng reference counting khi DataBuffer hỗ trợ pooled lifecycle (PooledDataBuffer). Chúng giúp tránh cast và gọi Netty ByteBuf trực tiếp trong phần lớn code ứng dụng.

Nguyên tắc ownership: component cuối cùng sử dụng buffer mà không chuyển tiếp quyền sở hữu phải release. Nếu giữ buffer lâu hơn vòng đời hiện tại, retain trước khi giữ và release đúng một lần cho mỗi reference mà mình sở hữu.

### 5.4. Đọc nhiều DataBuffer bằng DataBufferUtils.join

~~~java
Mono<String> readUtf8(Publisher<? extends DataBuffer> source) {
    return DataBufferUtils.join(source)
        .map(buffer -> {
            try {
                byte[] bytes = new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return new String(bytes, StandardCharsets.UTF_8);
            } finally {
                DataBufferUtils.release(buffer);
            }
        });
}
~~~

DataBufferUtils.join gom source thành một buffer (có thể là composite/zero-copy tùy implementation). Các buffer nguồn được xử lý như thành phần của composite; caller chịu trách nhiệm release buffer kết quả sau khi đọc. Nếu source lỗi hoặc bị cancel trong lúc join, utility có cơ chế release các buffer đã tích lũy.

Đừng gọi release từng input buffer sau khi join đã nhận ownership của chúng; điều đó có thể double-release.

### 5.5. Buffer bị filter hoặc discard

~~~java
Flux<DataBuffer> nonEmpty =
    incoming
        .filter(buffer -> buffer.readableByteCount() > 0)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

filter loại các buffer rỗng khỏi downstream. Nếu buffer bị loại là pooled, cần release. doOnDiscard là local cleanup hook; nó cũng có ích khi operator phía upstream đã prefetch/queue item và phải bỏ chúng do cancellation hoặc error.

**Vị trí quan trọng:** đặt doOnDiscard ở phía downstream của các operator có thể discard, để các operator upstream nhìn thấy cleanup hook. Không phải mọi operator đều hỗ trợ discard; kiểm tra mục Discard Support trong Javadoc của operator đang dùng.

### 5.6. Cleanup phải idempotent

Reactor có thể gọi discard hook ở nhiều nhánh cleanup. Hàm cleanup nên an toàn nếu cùng object đi qua nhiều đường xử lý hoặc bị gọi nhiều lần theo semantics của hook.

Không dùng doOnDiscard để release một object mà application đã chuyển ownership sang framework. Cũng không thêm retain() cho chắc mà không có cặp release() tương ứng.

## 6. Phân biệt discard, dropped item và lỗi khi operator xử lý

| Tình huống | Ví dụ | Cơ chế phù hợp |
| --- | --- | --- |
| filter loại item bình thường | Buffer không đạt điều kiện | doOnDiscard |
| skip bỏ các item đầu | Byte stream đã bỏ phần header | doOnDiscard nếu item cần cleanup |
| Operator prefetch rồi bị cancel | Queue còn buffer chưa phát | doOnDiscard nếu operator hỗ trợ |
| Source phát onNext sau complete | Publisher sai Reactive Streams contract | Hooks.onNextDropped |
| Source phát onError sau complete/cancel | Callback đến muộn | Hooks.onErrorDropped |
| Mapper map ném exception | Lỗi trong xử lý item | onOperatorError, rồi error tiếp tục qua onError |
| Business service trả lỗi bình thường | DB/API fail | onError, onErrorResume, retry hoặc propagate |

### 6.1. doOnDiscard không phải universal cleanup

doOnDiscard chỉ tác động lên các operator có hỗ trợ discard và các item đúng kiểu được đăng ký. Nó không tự tìm mọi object bị bỏ ở mọi thư viện hoặc mọi custom operator.

~~~java
source
    .filter(this::isUseful)
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release)
    .map(this::decode);
~~~

Nếu custom operator tự giữ DataBuffer trong collection riêng, custom operator phải tự định nghĩa cleanup cho collection khi error/cancel. Không thể mặc định Reactor biết object đang nằm ở đâu.

### 6.2. onNextDropped và onErrorDropped là global hook

Global hook có phạm vi toàn JVM và có thể ảnh hưởng nhiều module. Dùng nó cho observability hoặc trường hợp protocol-level cleanup thực sự cần thiết, không thay thế cleanup local cho filter, skip hay queue.

~~~java
Hooks.onNextDropped(value -> {
    if (value instanceof DataBuffer buffer) {
        DataBufferUtils.release(buffer);
    }
});
~~~

Đây là ví dụ nâng cao, chỉ dùng khi ứng dụng thực sự sở hữu các DataBuffer có thể đến muộn. Consumer phải lọc đúng kiểu, xử lý ownership chính xác và idempotent. Trong luồng bình thường, ưu tiên doOnDiscard theo từng chain.

### 6.3. onOperatorError không phải onErrorDropped

~~~java
Flux<Integer> values = Flux.just(1, 2, 0)
    .map(value -> 10 / value);
~~~

Khi map gặp số 0, ArithmeticException có thể được chuyển thành onError tới subscriber. Nếu subscriber đã cancel trước đó hoặc source phát terminal signal trái contract, một error đến muộn có thể bị drop. Hai tình huống cần chẩn đoán khác nhau.

### 6.4. onErrorContinue cần thận trọng

onErrorContinue là operator chuyên biệt, tác động lên upstream và chỉ hoạt động với operator có hỗ trợ. Nó có thể làm phạm vi xử lý lỗi khó đọc và khiến library code không dự kiến việc tiếp tục. Thường rõ ràng hơn nếu xử lý lỗi bên trong đúng inner Publisher:

~~~java
Flux<Result> results = ids.flatMap(id ->
    repository.findById(id)
        .doOnError(error -> log.warn("Cannot load {}", id, error))
        .onErrorResume(NotFoundException.class, error -> Mono.empty())
);
~~~

Chỉ bỏ qua NotFoundException nếu hợp đồng nghiệp vụ cho phép. Lỗi khác vẫn đi tiếp downstream.

## 7. Chuỗi không được đăng ký: các lỗi assembly thường gặp

### 7.1. Gọi operator nhưng bỏ Publisher trả về

Sai:

~~~java
Mono<Void> saveAndAudit(Mono<Void> save, Mono<Void> audit) {
    save.then(audit); // Publisher mới bị bỏ đi
    return Mono.empty();
}
~~~

then trả về Publisher mới; nó không sửa source tại chỗ. Do không return/subscribe Publisher mới, không có subscriber nào chạy save hoặc audit.

Đúng:

~~~java
Mono<Void> saveAndAudit(Mono<Void> save, Mono<Void> audit) {
    return save.then(audit);
}
~~~

### 7.2. Tạo inner Publisher nhưng không trả nó từ callback

Sai:

~~~java
return orders.flatMap(order -> {
    auditRepository.save(toAudit(order)); // cold Publisher bị bỏ
    return Mono.just(order);
});
~~~

Đúng:

~~~java
return orders.flatMap(order ->
    auditRepository.save(toAudit(order))
        .thenReturn(order)
);
~~~

Inner Publisher phải được trả về cho operator như flatMap, concatMap hoặc then. Chỉ gọi method tạo Mono không có nghĩa thao tác database đã được subscribe.

### 7.3. subscribe() nội bộ tạo luồng tách rời

~~~java
public Mono<Order> create(Order order) {
    auditRepository.save(toAudit(order)).subscribe();
    return orderRepository.save(order);
}
~~~

Audit bắt đầu bằng subscription riêng, trong khi caller chỉ quản lý Publisher lưu order. Hậu quả:

- Lỗi audit không đi theo chuỗi trả về.
- Caller không thể phối hợp thứ tự, cancellation hoặc retry.
- Test có thể kết thúc trước khi audit hoàn tất.
- Transaction/reactive context không tự chia sẻ giữa hai subscription.
- Shutdown có thể xảy ra khi tác vụ detached vẫn đang chạy.

Đúng hơn:

~~~java
public Mono<Order> create(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            auditRepository.save(toAudit(saved))
                .thenReturn(saved)
        );
}
~~~

### 7.4. subscribe() không phải operator để ghép chuỗi

subscribe() là điểm bắt đầu execution và trả về Disposable; nó không trả Mono/Flux để tiếp tục compose. Thông thường, application boundary như command-line runner, listener hoặc integration imperative mới sở hữu subscription.

Trong controller WebFlux/service reactive, trả Publisher cho framework/caller. Nếu thật sự cần background task độc lập, hãy thiết kế owner, error consumer, cancellation, lifecycle và metrics rõ ràng.

### 7.5. Không nhầm không có onNext với không subscribe

Một Mono<Void> có thể đã chạy đầy đủ nhưng không phát item; nó chỉ complete. Để xác minh subscription, dùng doOnSubscribe, PublisherProbe hoặc probe trong test. Đừng suy luận từ việc không thấy onNext.

### 7.6. publishOn/subscribeOn không tạo subscription

Hai operator này thay đổi scheduler thực thi của một chuỗi khi chuỗi được subscribe. Chúng không tự khởi chạy một cold Publisher. Thêm subscribeOn(Schedulers.boundedElastic()) vào chain nhưng không ai subscribe thì vẫn không có công việc nào chạy.

### 7.7. Spring WebFlux tự subscribe Publisher được trả về

~~~java
@GetMapping("/orders/{id}")
public Mono<Order> getOrder(@PathVariable long id) {
    return orderRepository.findById(id);
}
~~~

Framework subscribe Publisher được trả về trong lifecycle HTTP. Nếu method tự subscribe rồi trả Mono.empty(), framework chỉ nhìn thấy Publisher rỗng và không quản lý phần work detached.

## 8. Chẩn đoán chain không chạy và lỗi đến muộn

### 8.1. Thêm lifecycle probes ở đúng vị trí

~~~java
return repository.findById(id)
    .doOnSubscribe(subscription -> log.debug("findById subscribed"))
    .doOnNext(value -> log.debug("findById emitted"))
    .doOnError(error -> log.error("findById failed", error))
    .doFinally(signal -> log.debug("findById finished: {}", signal))
    .checkpoint("OrderService.findById");
~~~

Nếu không có log subscribed, hãy tìm xem Publisher có được return tới framework/caller hay không. Nếu có subscribed nhưng không onNext, kiểm tra nguồn có thể complete rỗng, đang chờ demand, bị timeout hay bị cancel.

### 8.2. checkpoint để gắn dấu assembly

checkpoint("OrderService.findById") gắn description vào traceback khi lỗi đi qua chain. Nó nhẹ hơn việc bật global full assembly tracing.

~~~java
return service.loadOrder(id)
    .checkpoint("OrderController.loadOrder");
~~~

Biến thể:

~~~java
return service.loadOrder()
    .checkpoint("OrderController.loadOrder", true);
~~~

Tham số true yêu cầu full stack trace tại checkpoint, hữu ích khi cần định vị assembly site nhưng tốn chi phí hơn.

### 8.3. Hooks.onOperatorDebug()

~~~java
Hooks.onOperatorDebug();
~~~

Bật assembly tracing toàn cục. Phải bật trước khi tạo những chain cần debug; nếu bật sau, chain đã assemble không có thông tin stack tương ứng.

Đây là chế độ chẩn đoán có overhead vì Reactor thu thập stack trace khi assemble operator. Dùng có kiểm soát ở môi trường debug/test; không bật vô điều kiện trong production nếu chưa đánh giá chi phí.

### 8.4. log() và doOnEach

~~~java
Flux<String> traced = source
    .log("orders.pipeline")
    .doOnEach(signal -> log.debug("signal: {}", signal.getType()));
~~~

log() có thể in subscription, request và các signal. Chỉ bật tạm thời hoặc trên chain giới hạn; tránh log payload/token và tránh làm log volume tăng đột biến.

### 8.5. StepVerifier và TestPublisher

- StepVerifier tạo subscription và kiểm tra signal theo kịch bản.
- TestPublisher cho phép phát onNext, onComplete, onError có kiểm soát, kể cả tạo source cố tình vi phạm contract.
- PublisherProbe kiểm tra nhánh Publisher có subscribe/request/cancel hay không.

Không gọi subscribe() trong test rồi assert tức thì nếu không chờ lifecycle hoàn tất. Dùng verifyComplete(), verify() hoặc verify(Duration) để có điểm kết thúc rõ ràng.

### 8.6. Phân tích log dropped error

Khi có dropped error, ghi nhận exception type/message và stack trace, route/operation/correlation id (không log secret), thời điểm complete/error/cancel, timeout/client disconnect/retry, callback nào phát error và callback đó đã được deregister chưa.

Không chỉ tăng log level rồi coi lỗi đã được xử lý. Dùng thông tin để sửa lifecycle hoặc quản lý cancellation.

## 9. Chẩn đoán Netty DataBuffer leak và direct memory

### 9.1. Bật Netty leak detector

Trong lần tái hiện lỗi hoặc test chuyên biệt, có thể chạy JVM với:

~~~bash
java -Dio.netty.leakDetection.level=advanced -jar app.jar
~~~

Các mức phổ biến:

| Mức | Hành vi | Dùng khi |
| --- | --- | --- |
| DISABLED | Tắt leak detection | Không khuyến nghị |
| SIMPLE | Sampling nhẹ, thường là mặc định | Theo dõi thông thường |
| ADVANCED | Báo thêm nơi buffer được truy cập gần đây | Điều tra leak |
| PARANOID | Theo dõi mọi allocation, overhead rất cao | Test ngắn/chuyên biệt |

Không bật PARANOID cho production traffic lớn. Leak detector có sampling và overhead; việc không thấy log leak không chứng minh ứng dụng không có leak.

### 9.2. Reactor Netty leak logger

~~~properties
logging.level._reactor.netty.channel.LeakDetection=DEBUG
~~~

Logger này giúp phân biệt leak nằm bên trong Reactor Netty hay buffer ownership đã được chuyển sang application/framework. Kết hợp với Netty leak detector để truy vết allocation/access.

### 9.3. Theo dõi active memory metrics

Khi Reactor Netty metrics được bật, các gauge hữu ích gồm:

- reactor.netty.bytebuf.allocator.active.heap.memory
- reactor.netty.bytebuf.allocator.active.direct.memory

Đây là lượng byte đang được sử dụng trong các pooled buffer heap/direct. Nếu active memory tăng liên tục qua tải tương tự và không giảm sau khi request/stream kết thúc, đó là dấu hiệu cần điều tra.

Phân biệt:
- Pool có thể giữ vùng nhớ đã cấp phát để tái sử dụng; RSS/direct memory không nhất thiết giảm ngay.
- Active memory đo buffer còn đang được dùng; đây là tín hiệu gần với leak hơn.
- Một đợt traffic tăng hoặc response lớn có thể tạo peak hợp lệ.
- So sánh sau khi workload kết thúc, pool ổn định và qua nhiều chu kỳ tải.

### 9.4. Heap dump không đủ cho direct buffer leak

Netty direct memory có thể nằm ngoài Java heap. Heap dump không phải lúc nào cũng chỉ ra ownership sai của ByteBuf. Kết hợp leak detector, allocator metrics, native memory metrics và request/connection tracing.

### 9.5. IllegalReferenceCountException

Lỗi này thường báo buffer đã được release về 0 nhưng code vẫn đọc/ghi, hoặc bị release nhiều lần. Nó khác với leak:

- Leak: ref count không về 0 khi không còn owner.
- Use-after-release: code truy cập sau khi ref count về 0.
- Double-release: một ownership bị release nhiều hơn số retain tương ứng.

Tìm chỗ chuyển ownership, retain(), release() và callback nào chạy trong cả error lẫn cancel path.

## 10. Lỗi thiết kế phổ biến và cách sửa

**1 — Gọi repository nhưng bỏ Publisher.** Method trả Mono không tự chạy. Hãy return hoặc compose Publisher đó.

**2 — Gọi operator nhưng bỏ giá trị trả về.** Reactor chain bất biến; lưu/return chain mới được tạo.

**3 — Tạo inner Publisher nhưng không return từ flatMap.** Inner cold Publisher không được subscribe. Return nó hoặc nối bằng then.

**4 — Gọi subscribe() trong service/controller.** Tạo luồng detached; trả Publisher để caller/framework quản lý.

**5 — Nghĩ publishOn/subscribeOn tự khởi chạy công việc.** Chúng chỉ điều chỉnh execution khi có subscription.

**6 — Bỏ error consumer ở background subscription.** Lỗi có thể đi theo default handler và khó quan sát. Nếu thật sự sở hữu subscription, cung cấp error consumer và quản lý Disposable.

**7 — Dùng onErrorDropped để thay onErrorResume.** Hook global không khôi phục kết quả cho subscriber; xử lý lỗi nghiệp vụ trong chain.

**8 — Xem mọi onError là dropped error.** Lỗi bình thường có thể đi qua onError. Dropped error là tín hiệu không còn đường truyền sau terminal/cancel hoặc do source sai contract.

**9 — Dùng doOnDiscard như hook cho mọi lỗi.** Hook chỉ chạy ở các operator có discard support. Kiểm tra Javadoc và đặt hook ở vị trí phù hợp.

**10 — Release DataBuffer sau khi đã chuyển ownership.** Có thể double-release. Chỉ release khi component hiện tại sở hữu reference cần trả.

**11 — Quên release DataBuffer khi custom decoder giữ buffer.** Native memory bị giữ. Dùng try/finally, DataBufferUtils.join hoặc doOnDiscard theo trường hợp.

**12 — Dùng filter trên DataBuffer mà không cleanup discarded item.** Buffer bị loại khỏi downstream nhưng vẫn còn reference. Thêm doOnDiscard nếu operator hỗ trợ.

**13 — Retain mà không release.** Reference count không bao giờ về 0. Ghép mỗi retain với một lần release.

**14 — Release cùng buffer ở nhiều callback không idempotent.** Error/cancel có thể gọi cleanup lặp. Thiết kế ownership và cleanup rõ ràng.

**15 — Cho rằng heap dump sẽ thấy mọi leak Netty.** Direct memory có thể nằm ngoài heap. Bật leak detector và xem active direct memory.

**16 — Bật PARANOID leak detection trên production.** Overhead rất cao. Dùng SIMPLE/ADVANCED phù hợp với mục tiêu và chỉ dùng PARANOID trong test ngắn.

**17 — Nhầm pooled memory còn reserved với leak.** Pool có thể giữ vùng nhớ để tái sử dụng. Theo dõi active memory, không chỉ RSS.

**18 — Bỏ qua cancellation của callback bridge.** Listener tiếp tục phát sau khi downstream rời đi. Hủy đăng ký, đóng resource và chặn late signal.

**19 — Dùng global Hooks ở từng request.** Hook global tích lũy và ảnh hưởng toàn JVM. Cấu hình một lần, reset trong test.

**20 — Chỉ log lỗi mà không có context.** Thiếu correlation id, route và lifecycle làm khó truy vết. Gắn checkpoint và metadata an toàn.

## 11. Project Maven hoàn chỉnh: Java 17, Spring Boot 3.5.7 và Reactor Test

Project này minh họa ba phần: Publisher bị bỏ, dropped error sau terminal signal và pooled DataBuffer cleanup. Project dùng JUnit 5 + StepVerifier; không cần khởi động HTTP server hoặc kết nối database.

### 11.1. Cấu trúc

~~~text
reactor-diagnostics-demo/
├── pom.xml
├── src/main/java/example/diagnostics/
│   └── ReactiveDiagnostics.java
└── src/test/java/example/diagnostics/
    └── ReactiveDiagnosticsTest.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>reactor-diagnostics-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.5.7 quản lý version của Spring Framework, Reactor Core, Reactor Netty và Netty. reactor-test chỉ dùng trong test scope. Spring WebFlux starter cung cấp Spring Core DataBuffer API và Netty buffer implementation.

### 11.3. ReactiveDiagnostics.java

~~~java
package example.diagnostics;

import java.nio.charset.StandardCharsets;

import org.reactivestreams.Publisher;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveDiagnostics {

    // Deliberately broken: the composed Publisher is ignored.
    public Mono<Void> brokenSequence(
        Mono<Void> save,
        Mono<Void> audit
    ) {
        save.then(audit);
        return Mono.empty();
    }

    // Correct: the caller receives the complete chain.
    public Mono<Void> correctSequence(
        Mono<Void> save,
        Mono<Void> audit
    ) {
        return save.then(audit);
    }

    // A local discard hook releases pooled buffers filtered out upstream.
    public Flux<DataBuffer> keepNonEmpty(
        Publisher<? extends DataBuffer> source
    ) {
        return Flux.from(source)
            .filter(buffer -> buffer.readableByteCount() > 0)
            .doOnDiscard(
                DataBuffer.class,
                DataBufferUtils::release
            );
    }

    // join owns the source buffers; this method releases the joined result.
    public Mono<String> readUtf8(
        Publisher<? extends DataBuffer> source
    ) {
        return DataBufferUtils.join(source)
            .map(buffer -> {
                try {
                    byte[] bytes =
                        new byte[buffer.readableByteCount()];
                    buffer.read(bytes);
                    return new String(
                        bytes, StandardCharsets.UTF_8);
                } finally {
                    DataBufferUtils.release(buffer);
                }
            });
    }

    public Mono<String> withCheckpoint(Mono<String> source) {
        return source.checkpoint("ReactiveDiagnostics.withCheckpoint");
    }
}
~~~

brokenSequence cố ý lắp ráp save.then(audit) nhưng không return Publisher mới. correctSequence trả toàn bộ chuỗi. Hai method giúp test thấy rõ sự khác nhau giữa assembly và subscription.

keepNonEmpty dùng doOnDiscard để release buffer bị filter loại bỏ. readUtf8 dùng DataBufferUtils.join, đọc nội dung rồi release buffer aggregate trong finally.

### 11.4. ReactiveDiagnosticsTest.java

~~~java
package example.diagnostics;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import io.netty.buffer.UnpooledByteBufAllocator;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.NettyDataBuffer;
import org.springframework.core.io.buffer.NettyDataBufferFactory;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Hooks;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class ReactiveDiagnosticsTest {

    private final ReactiveDiagnostics diagnostics =
        new ReactiveDiagnostics();

    private final NettyDataBufferFactory bufferFactory =
        new NettyDataBufferFactory(
            UnpooledByteBufAllocator.DEFAULT);

    @AfterEach
    void afterEach() {
        // Global Reactor hooks must not leak into another test.
        Hooks.resetOnErrorDropped();
    }

    private NettyDataBuffer buffer(String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        NettyDataBuffer result =
            bufferFactory.allocateBuffer(bytes.length);
        result.write(bytes);
        return result;
    }

    @Test
    void coldPublisherDoesNotExecuteBeforeSubscription() {
        AtomicInteger executions = new AtomicInteger();

        Mono<Integer> source = Mono.defer(() -> {
            executions.incrementAndGet();
            return Mono.just(21);
        });

        Mono<Integer> result = source.map(value -> value * 2);

        assertEquals(0, executions.get());

        StepVerifier.create(result)
            .expectNext(42)
            .verifyComplete();

        assertEquals(1, executions.get());
    }

    @Test
    void ignoredChainLeavesBothPublishersUnsubscribed() {
        PublisherProbe<Void> save = PublisherProbe.empty();
        PublisherProbe<Void> audit = PublisherProbe.empty();

        StepVerifier.create(
                diagnostics.brokenSequence(
                    save.mono(), audit.mono()))
            .verifyComplete();

        save.assertWasNotSubscribed();
        audit.assertWasNotSubscribed();
    }

    @Test
    void returnedChainSubscribesBothPublishers() {
        PublisherProbe<Void> save = PublisherProbe.empty();
        PublisherProbe<Void> audit = PublisherProbe.empty();

        StepVerifier.create(
                diagnostics.correctSequence(
                    save.mono(), audit.mono()))
            .verifyComplete();

        save.assertWasSubscribed();
        audit.assertWasSubscribed();
    }

    @Test
    void errorAfterCompleteIsSentToDroppedErrorHook() {
        List<Throwable> dropped =
            new CopyOnWriteArrayList<>();

        Hooks.onErrorDropped(dropped::add);

        Flux<String> malformed = Flux.create(sink -> {
            sink.complete();
            sink.error(
                new IllegalStateException("late callback error"));
        });

        StepVerifier.create(malformed)
            .verifyComplete();

        assertEquals(1, dropped.size());
        assertEquals(
            "late callback error",
            dropped.get(0).getMessage()
        );
    }

    @Test
    void filteredDataBufferIsReleasedByDiscardHook() {
        NettyDataBuffer kept = buffer("keep");
        NettyDataBuffer discarded =
            bufferFactory.allocateBuffer(8);

        StepVerifier.create(
                diagnostics.keepNonEmpty(
                    Flux.<DataBuffer>just(kept, discarded)))
            .expectNext(kept)
            .verifyComplete();

        assertEquals(0, discarded.getNativeBuffer().refCnt());

        // The emitted buffer is now owned by this test.
        DataBufferUtils.release(kept);
        assertEquals(0, kept.getNativeBuffer().refCnt());
    }

    @Test
    void joinedDataBuffersAreReleasedAfterReading() {
        NettyDataBuffer first = buffer("reactive ");
        NettyDataBuffer second = buffer("buffers");

        StepVerifier.create(
                diagnostics.readUtf8(Flux.just(first, second)))
            .expectNext("reactive buffers")
            .verifyComplete();

        assertEquals(0, first.getNativeBuffer().refCnt());
        assertEquals(0, second.getNativeBuffer().refCnt());
    }
}
~~~

**Điểm quan trọng của test:**

- coldPublisherDoesNotExecuteBeforeSubscription xác nhận source chỉ chạy sau khi StepVerifier subscribe.
- ignoredChainLeavesBothPublishersUnsubscribed bắt lỗi gọi operator nhưng bỏ Publisher mới.
- returnedChainSubscribesBothPublishers xác nhận cả hai bước thực sự được đăng ký.
- errorAfterCompleteIsSentToDroppedErrorHook tạo một source cố ý gửi error sau complete; hook global ghi nhận late error.
- filteredDataBufferIsReleasedByDiscardHook kiểm tra reference count của buffer bị filter loại về 0.
- joinedDataBuffersAreReleasedAfterReading xác nhận buffer đầu vào được giải phóng khi aggregate được release.

Hook Hooks.onErrorDropped là global nên test reset trong @AfterEach. Không chạy các test sửa global hooks song song với test khác đang dùng cùng hook.

### 11.5. Chạy test

Yêu cầu JDK 17+ và Maven:

~~~bash
java -version
mvn test
~~~

Kết quả dự kiến khi tất cả test pass:

~~~text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là kết quả mong đợi từ ví dụ, không phải log đã thực thi. Project không cần HTTP server, database hay kết nối Internet; test chạy trực tiếp trên Reactor và Netty DataBuffer.

## 12. Quy trình điều tra theo triệu chứng

### 12.1. Không thấy database hoặc HTTP request

1. Tìm method tạo Mono/Flux.
2. Kiểm tra method có return Publisher mới sau các operator không.
3. Kiểm tra inner Publisher có được return từ flatMap/concatMap không.
4. Gắn doOnSubscribe và doFinally.
5. Dùng PublisherProbe hoặc StepVerifier để xác nhận subscription.
6. Tìm subscribe() nội bộ hoặc một chain bị bỏ quên.

### 12.2. Thấy Dropped error

1. Xác định lỗi có nằm trong onError thông thường hay đã bị drop.
2. Tìm timeout, cancellation, client disconnect và competing source.
3. Kiểm tra callback ngoài có tiếp tục gửi error sau dispose không.
4. Gắn Hooks.onErrorDropped ở môi trường điều tra.
5. Kiểm tra source/custom Publisher có gửi terminal signal nhiều lần không.
6. Sửa lifecycle hoặc deregister callback; không chỉ thêm global logger.

### 12.3. Thấy LEAK: ByteBuf.release() was not called

1. Bật Netty leak detection advanced.
2. Bật logger Reactor Netty leak detection ở DEBUG.
3. Tìm code trực tiếp dùng DataBuffer/ByteBuf hoặc custom codec.
4. Lập ownership map: allocate → retain → transfer → release.
5. Kiểm tra filter/skip/prefetch/cancel có discard buffer không.
6. Thêm doOnDiscard hoặc release trong finally đúng chỗ.
7. Theo dõi active direct/heap memory qua workload tương đương.
8. Kiểm tra lại để tránh double-release và use-after-release.

### 12.4. Direct memory tăng nhưng không thấy leak log

- Leak detector mặc định có sampling, nên không phát hiện mọi allocation.
- Pool có thể giữ memory để tái sử dụng; active memory và allocated/reserved memory là hai khái niệm khác nhau.
- Tăng leak detection level ở môi trường tái hiện.
- So sánh active direct memory sau khi request/stream đã hoàn tất.
- Dùng tải lặp lại và kiểm tra memory có tăng tuyến tính hay đạt plateau.

### 12.5. Test reactive bị treo

- Có source nào không complete (ví dụ Flux.never) không?
- Có initial request bằng 0 mà quên thenRequest(n) không?
- Có Publisher nào chưa subscribe không?
- Có callback nào chờ signal từ chính chuỗi đang bị chặn không?
- Có blocking call trên event-loop không?
- Thêm verify(Duration) để test thất bại hữu hạn thay vì treo vô thời hạn.

## 13. Checklist phòng ngừa trong production

### Publisher lifecycle

1. Method reactive trả Publisher hoàn chỉnh, không bỏ kết quả operator.
2. Inner Publisher được return/compose, không chỉ gọi factory.
3. Controller/service không tự subscribe nếu framework/caller phải quản lý.
4. Background subscription có owner, error consumer, Disposable và shutdown lifecycle.
5. Callback bridge dừng khi cancel/dispose.
6. Có doOnSubscribe/doFinally ở những boundary quan trọng.

### Error handling

7. Lỗi nghiệp vụ được propagate hoặc recover bằng onErrorResume đúng policy.
8. doOnError không bị hiểu nhầm là đã xử lý error.
9. onErrorDropped chỉ dùng cho lỗi ngoài normal signal path.
10. Global Hooks được đăng ký một lần, reset trong test và không ghi dữ liệu nhạy cảm.
11. Late callback được deregister/cancel hoặc ghi nhận riêng.
12. checkpoint có tên nghiệp vụ để dễ đọc traceback.

### Buffer ownership

13. Mỗi DataBuffer/ByteBuf có owner rõ ràng.
14. Mỗi retain() có một release() tương ứng.
15. Custom decoder/encoder xử lý buffer trong error và cancellation path.
16. Buffer bị filter/skip/prefetch discard được cleanup nếu operator hỗ trợ.
17. Không release buffer sau khi ownership đã chuyển sang framework.
18. Không double-release hoặc sử dụng sau khi ref count về 0.
19. Direct memory được giám sát cùng active memory metrics.
20. Leak detector được dùng phù hợp với môi trường và chi phí.

### Kiểm thử và vận hành

21. StepVerifier kiểm tra complete/error/cancel và có timeout.
22. Test xác nhận subscription, không chỉ kiểm tra giá trị cuối.
23. Test dùng DataBuffer reference count để xác minh cleanup khi phù hợp.
24. Có test late error và global hook isolation.
25. Có load test để phát hiện buffer/queue giữ memory theo thời gian.
26. onBackpressureBuffer có giới hạn dung lượng và policy overflow rõ ràng.
27. Log/metric có correlation id nhưng không chứa token/payload nhạy cảm.
28. Không bật full operator stacktrace hoặc PARANOID leak detection lâu dài mà chưa đánh giá overhead.

## 14. Câu hỏi tự kiểm tra

1. Tạo Mono có chạy SQL ngay không? **Không; cold Publisher chạy khi subscribe.**
2. Assembly và subscription khác nhau thế nào? **Assembly lắp ráp chuỗi operator; subscription bắt đầu thực thi và truyền demand.**
3. Vì sao source.map(...); return source; có thể bỏ logic map? **map trả Publisher mới và source gốc không bị thay đổi.**
4. subscribe() nội bộ gây vấn đề gì? **Tạo subscription detached, tách lỗi/cancel/lifecycle khỏi caller.**
5. Dropped error khác normal onError thế nào? **Dropped error đến khi subscriber không còn nhận terminal signal; normal onError vẫn truyền qua chain.**
6. Hook nào quan sát dropped error? **Hooks.onErrorDropped.**
7. Hook nào quan sát dropped item sau terminal? **Hooks.onNextDropped.**
8. Hooks.onOperatorError làm gì? **Quan sát/biến đổi lỗi phát sinh trong xử lý operator nhưng vẫn có thể truyền qua onError.**
9. doOnDiscard xử lý tình huống nào? **Cleanup item bị operator hỗ trợ discard loại bỏ hoặc queue dọn do cancel/error.**
10. doOnError có thay thế lỗi không? **Không; nó quan sát rồi error tiếp tục downstream.**
11. onErrorResume khác onErrorDropped thế nào? **onErrorResume recovery trong chain; onErrorDropped xử lý lỗi không còn đường truyền.**
12. Vì sao DataBuffer có thể gây direct-memory leak? **Pooled buffer reference count không về 0.**
13. retain() làm gì? **Tăng reference count.**
14. release() làm gì? **Giảm reference count và trả buffer về pool khi count về 0.**
15. Khi nào cần doOnDiscard(DataBuffer.class, DataBufferUtils::release)? **Khi operator hỗ trợ discard và buffer có thể bị filter/skip/prefetch/cancel bỏ.**
16. DataBufferUtils.join có yêu cầu release input riêng sau khi join không? **Input được quản lý như thành phần của aggregate; caller release buffer kết quả.**
17. IllegalReferenceCountException thường gợi ý gì? **Use-after-release hoặc double-release.**
18. Vì sao heap dump không đủ để tìm Netty direct buffer leak? **Direct memory nằm ngoài Java heap.**
19. Metric nào giúp theo dõi active direct buffer memory? **reactor.netty.bytebuf.allocator.active.direct.memory.**
20. checkpoint("name") giúp gì? **Gắn marker assembly vào traceback khi lỗi xảy ra.**
21. Khi nào dùng Hooks.onOperatorDebug()? **Điều tra cần assembly stack toàn cục; phải bật trước khi tạo chain và chấp nhận overhead.**
22. Vì sao global Hook phải reset trong test? **Hook tác động toàn JVM và có thể làm test khác nhiễu.**
23. Có nên bật PARANOID leak detection lâu dài trên production? **Không; overhead rất cao, phù hợp test chuyên biệt.**
24. Buffer pool còn giữ memory có luôn là leak không? **Không; cần xem active memory và xu hướng sau khi workload hoàn tất.**

## 15. Tóm tắt và tài liệu tham khảo

- **Dropped error** là error đến khi sequence không còn khả năng chuyển tiếp onError, thường sau terminal/cancel hoặc do source sai contract. Hooks.onErrorDropped chỉ giúp quan sát/cleanup; lỗi nghiệp vụ bình thường phải được xử lý trong chain.
- **Discard** là item bị operator loại bỏ theo semantics bình thường hoặc dọn queue khi cancel/error. Dùng doOnDiscard với kiểu resource cần cleanup và operator có hỗ trợ.
- **Buffer leak** xảy ra khi reference count của pooled DataBuffer/ByteBuf không về 0. Phải xác định ownership và ghép retain/release đúng.
- **Unsubscribed chain** là Publisher đã assemble nhưng không có subscriber; cold side effect chưa chạy. Return/composition Publisher thay vì bỏ kết quả hoặc subscribe detached.
- StepVerifier, TestPublisher, PublisherProbe, checkpoint, doOnSubscribe và doFinally là các công cụ hữu ích để xác nhận lifecycle.
- Netty leak detector, Reactor Netty leak logger và active memory gauges giúp điều tra direct memory.
- Không dùng global Hooks như error recovery, không dùng subscribe() để ép chain chạy và không release buffer đã chuyển ownership.

**Tài liệu chính thức**

1. [Project Reactor 3.7 — Using Global Hooks](https://docs.spring.io/projectreactor/reactor-core/docs/3.7.x/reference/html/advancedFeatures/hooks.html): onErrorDropped, onNextDropped, onOperatorError và assembly hooks.
2. [Project Reactor 3.7 — Dealing with Objects that Need Cleanup](https://projectreactor.io/docs/core/3.7.x/reference/html/advancedFeatures/cleanup.html): doOnDiscard, onOperatorError, onNextDropped và cleanup operator-specific.
3. [Project Reactor 3.7 — Debugging Reactor](https://projectreactor.io/docs/core/3.7.x/reference/html/debugging.html): checkpoint, Hooks.onOperatorDebug và assembly traceback.
4. [Project Reactor 3.7 — Testing](https://docs.spring.io/projectreactor/reactor-core/docs/3.7.x/reference/html/testing.html): StepVerifier, TestPublisher và kiểm tra subscription.
5. [Spring Framework 6.2 — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html): PooledDataBuffer, DataBufferUtils, retain/release và cleanup khi discard/cancel.
6. [Spring Framework 6.2 — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): DataBuffer ownership trong WebFlux.
7. [Netty — Reference Counted Objects](https://netty.io/wiki/reference-counted-objects.html): ByteBuf lifecycle, retain/release và troubleshooting buffer leaks.
8. [Reactor Netty — Frequently Asked Questions: Memory Leak](https://docs.spring.io/projectreactor/reactor-netty/docs/current/reference/html/index.html#faq.memory): leak detector, logger _reactor.netty.channel.LeakDetection_ và active memory metrics.
