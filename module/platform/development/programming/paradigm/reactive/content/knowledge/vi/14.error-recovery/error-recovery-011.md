# Lỗi và phục hồi

## Tín hiệu lỗi không thể chuyển tiếp và các cơ chế quan sát toàn cục

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học cách xây dựng ứng dụng quanh các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Một pipeline có thể phát lỗi bình thường tới Subscriber, nhưng cũng có lúc lỗi xuất hiện sau khi Subscriber đã hủy hoặc luồng đã kết thúc. Khi đó không còn Subscriber nào có thể nhận lỗi. Reactor gọi đây là **lỗi bị loại bỏ (dropped error)** và cung cấp các hook toàn cục để quan sát những tín hiệu không thể chuyển tiếp.

Cần phân biệt lỗi bị loại bỏ với lỗi thông thường. Lỗi thông thường đi qua `onError` và có thể được xử lý bằng `onErrorResume`, `onErrorMap` hoặc ghi nhận bằng `doOnError`. Lỗi bị loại bỏ không còn đường đi tới downstream; một hook toàn cục có thể giúp ghi nhận nó, nhưng không thể quay lại Subscriber đã hủy để tiếp tục workflow. Việc hiểu rõ ranh giới này giúp ta phát hiện race condition, lỗi callback đến muộn và những vi phạm vòng đời trong adapter bất đồng bộ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt lỗi được truyền qua `onError`, lỗi bị loại bỏ và lỗi do thiếu error callback ở `subscribe`.
- Nhận diện các nguyên nhân khiến một tín hiệu lỗi không thể chuyển tiếp tới Subscriber.
- Cấu hình `Hooks.onErrorDropped` và hiểu phạm vi toàn cục của hook.
- Phân biệt `onErrorDropped`, `onNextDropped`, `onOperatorError` và các hook lắp ráp toán tử.
- Chọn vị trí quan sát phù hợp giữa `doOnError`, `doFinally`, Reactor Context và hook toàn cục.
- Thiết kế logging, metric và cleanup an toàn cho lỗi đến muộn.
- Kiểm thử dropped error mà không để trạng thái hook rò rỉ giữa các bài test.

## 1. Lỗi thông thường và lỗi không thể chuyển tiếp

Trong Reactive Streams, `onError(Throwable)` là tín hiệu kết thúc của một Subscription. Khi Publisher phát `onError`, Subscriber nhận lỗi và luồng đó kết thúc. Nếu pipeline có toán tử phục hồi, lỗi có thể được thay bằng một Publisher khác trước khi tới Subscriber cuối.

~~~java
Mono<Customer> customer =
    customerRepository.findById(customerId)
        .doOnError(error -> metrics.recordFailure())
        .onErrorResume(DependencyUnavailableException.class,
            error -> customerCache.findById(customerId));
~~~

Ở đây, lỗi được phát trong luồng thông thường. `doOnError` quan sát lỗi, còn `onErrorResume` có thể chuyển sang cache. Subscriber cuối vẫn nhận được giá trị cache hoặc lỗi từ fallback.

Tình huống khác xảy ra khi Subscriber đã hủy hoặc đã nhận tín hiệu kết thúc. Nếu một callback bất đồng bộ sau đó cố phát lỗi vào cùng sink, không còn Subscriber hợp lệ để nhận lỗi đó. Reactor không thể chuyển tín hiệu này qua `onError` của Subscriber cũ. Lỗi trở thành dropped error.

~~~mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Publisher / adapter
    participant L as Callback thư viện ngoài
    participant H as onErrorDropped hook
    S->>P: subscribe
    P-->>S: onSubscribe
    S->>P: cancel
    Note over P,S: Subscription đã kết thúc
    L-->>P: callback lỗi đến muộn
    P-->>H: lỗi không thể chuyển tiếp
~~~

Các trường hợp thường dẫn đến dropped error:

- Subscriber đã gọi `cancel()`, nhưng callback từ thư viện ngoài vẫn chạy.
- Publisher đã phát `onComplete` hoặc `onError`, sau đó một callback khác lại gọi `sink.error(...)`.
- Hai thread cạnh tranh phát tín hiệu kết thúc; chỉ một tín hiệu được chấp nhận, tín hiệu lỗi còn lại không còn nơi nhận.
- Một adapter callback không dừng listener khi dispose, khiến callback tiếp tục gửi tín hiệu sau khi pipeline đã kết thúc.
- Một nguồn hoặc toán tử phát tín hiệu vi phạm giao thức sau khi đã terminal.

Không phải mọi lỗi xuất hiện gần thời điểm cancellation đều chắc chắn là dropped error. Kết quả phụ thuộc thứ tự tín hiệu và việc Publisher đã chuyển lỗi tới Subscriber hay chưa. Khi điều tra, hãy quan sát cả vòng đời subscription và trạng thái nguồn.

## 2. Dấu hiệu của dropped error

Một dropped error không đi qua chuỗi xử lý lỗi thông thường của downstream. Vì vậy, những toán tử như `doOnError` hoặc `onErrorResume` ở phía Subscriber cuối có thể không nhìn thấy nó.

Ví dụ, một adapter tạo Publisher từ listener:

~~~java
Flux<String> events = Flux.create(sink -> {
    Listener listener = new Listener() {
        @Override
        public void onEvent(String value) {
            sink.next(value);
        }

        @Override
        public void onFailure(Throwable error) {
            sink.error(error);
        }
    };

    sink.onDispose(() -> eventSource.removeListener(listener));
    eventSource.addListener(listener);
});
~~~

Nếu thư viện gọi `onFailure` sau khi subscription đã bị hủy hoặc đã kết thúc, `sink.error(error)` không thể gửi lỗi tới Subscriber đó. Hook dropped error có thể ghi nhận tình huống. Tuy nhiên, việc hook được gọi không thay thế trách nhiệm gỡ listener; adapter vẫn phải dừng nguồn và xử lý callback đến muộn đúng cách.

Một lỗi bị loại bỏ thường chỉ ra một trong các vấn đề:

- Vòng đời callback không gắn đúng với subscription.
- Nguồn phát tín hiệu trễ sau cancellation.
- Có nhiều nơi cùng cố kết thúc một Publisher.
- Một lỗi phụ phát sinh trong quá trình cleanup hoặc callback.
- Một thư viện tích hợp không tuân thủ kỳ vọng về thứ tự hoặc số lần callback.

Hook giúp ta thấy dấu hiệu. Để tìm nguyên nhân, cần kết hợp log theo nguồn, metric cancellation, số listener đang đăng ký và trạng thái kết thúc của pipeline.

## 3. Hooks.onErrorDropped: quan sát lỗi bị loại bỏ

Reactor cung cấp API toàn cục `Hooks.onErrorDropped` để đăng ký callback nhận các lỗi bị loại bỏ:

~~~java
Hooks.onErrorDropped(error ->
    log.error("Reactive error could not be delivered downstream", error)
);
~~~

Callback này là nơi cuối cùng để quan sát một lỗi không còn được chuyển tiếp tới Subscriber. Có thể dùng nó để:

- Ghi log có cấu trúc và stack trace.
- Tăng counter cho dropped error.
- Phân loại loại exception thường xuất hiện sau cancellation.
- Gửi tín hiệu tới hệ thống giám sát để điều tra.
- Phát hiện lỗi callback đến muộn trong adapter.

Một cấu hình thực tế có thể ghi nhận loại lỗi và metric:

~~~java
Hooks.onErrorDropped(error -> {
    Throwable cause = Exceptions.unwrap(error);

    droppedErrorCounter.increment(
        Tags.of("exception", cause.getClass().getSimpleName())
    );

    log.error("Undeliverable reactive error: {}",
        cause.getClass().getName(), cause);
});
~~~

`Exceptions.unwrap` giúp bóc một số wrapper exception do Reactor sử dụng. Không nên dùng message tùy ý làm nhãn metric vì message có thể chứa ID, URL hoặc dữ liệu biến thiên, tạo cardinality rất cao.

Hook này không nhận Subscriber để tiếp tục luồng. Khi lỗi đã bị loại bỏ, không thể gọi `onErrorResume` trên pipeline cũ để phục hồi. Nếu nghiệp vụ cần xử lý lỗi đó, phải thiết kế một kênh xử lý độc lập có chủ sở hữu rõ ràng, ví dụ hàng đợi lỗi hoặc worker giám sát.

### Cấu hình hook ở thời điểm khởi động

Các hook trong `Hooks` có phạm vi toàn cục trong tiến trình. Nên cài đặt chúng ở giai đoạn khởi động ứng dụng, trước khi các pipeline cần được quan sát bắt đầu chạy:

~~~java
@Configuration
class ReactorObservabilityConfiguration {
    @PostConstruct
    void installReactorHooks() {
        Hooks.onErrorDropped(error -> {
            Throwable cause = Exceptions.unwrap(error);
            log.error("Dropped Reactor error", cause);
        });
    }
}
~~~

Đây là ví dụ minh họa cấu hình khởi động. Trong ứng dụng thực tế, hãy bảo đảm chỉ có một thành phần chịu trách nhiệm đăng ký hook, tránh nhiều module thay thế hoặc chồng callback ngoài ý muốn.

## 4. onErrorDropped khác với doOnError

Hai cơ chế có mục đích khác nhau:

| Cơ chế | Quan sát loại tín hiệu nào? | Phạm vi | Có thể phục hồi pipeline hiện tại? |
|---|---|---|---|
| `doOnError` | Lỗi đang đi qua vị trí toán tử | Một pipeline | Không; chỉ quan sát |
| `onErrorResume` | Lỗi được truyền tới toán tử | Một pipeline | Có thể thay bằng Publisher khác |
| `onErrorMap` | Lỗi được truyền tới toán tử | Một pipeline | Chuyển thành exception khác |
| `Hooks.onErrorDropped` | Lỗi không còn nơi nhận downstream | Toàn cục | Không |
| `Hooks.onOperatorError` | Lỗi phát sinh khi toán tử thực thi callback hoặc logic nội bộ theo đường xử lý lỗi của Reactor | Toàn cục | Có thể biến đổi exception được phát ra, không phải cơ chế fallback |

Ví dụ lỗi thông thường:

~~~java
Mono<String> result =
    Mono.<String>error(new IllegalStateException("database unavailable"))
        .doOnError(error -> log.warn("Request failed", error))
        .onErrorResume(error -> Mono.just("cached"));
~~~

`doOnError` được gọi và `onErrorResume` thay lỗi bằng giá trị cache.

Ngược lại, nếu Subscriber đã hủy rồi nguồn cố phát lỗi, lỗi đó không đi qua downstream `doOnError` hoặc `onErrorResume`. Khi đó `Hooks.onErrorDropped` là điểm quan sát thích hợp.

Không nên chuyển mọi xử lý lỗi sang hook toàn cục. Lỗi nghiệp vụ và lỗi hạ tầng bình thường cần được xử lý ở pipeline hoặc ranh giới ứng dụng nơi có đủ ngữ cảnh để quyết định retry, fallback hay phản hồi caller.

## 5. Phân biệt các hook toàn cục chính

Reactor cung cấp nhiều hook phục vụ những điểm khác nhau trong vòng đời tín hiệu và toán tử:

| Hook | Vai trò | Khi nào cần quan tâm |
|---|---|---|
| `Hooks.onErrorDropped` | Quan sát lỗi không thể chuyển tới Subscriber | Callback lỗi đến muộn, lỗi sau cancel/terminal |
| `Hooks.onNextDropped` | Quan sát phần tử không thể chuyển tới Subscriber | Nguồn phát giá trị sau cancel/terminal |
| `Hooks.onOperatorError` | Biến đổi hoặc bổ sung xử lý cho lỗi do đường thực thi toán tử phát sinh | Callback trong `map`, `filter` hoặc toán tử ném exception |
| `Hooks.onEachOperator` | Áp dụng hook tại thời điểm lắp ráp mỗi toán tử | Instrumentation, tracing hoặc quan sát pipeline |
| `Hooks.onLastOperator` | Áp dụng hook ở toán tử cuối trong quá trình lắp ráp | Tích hợp ở ranh giới Subscriber hoặc instrumentation chuyên biệt |

Các hook không thay thế nhau. Đặc biệt, `onOperatorError` không phải bộ thu mọi lỗi upstream và `onEachOperator` không phải một error handler.

### onNextDropped

Nếu một nguồn phát giá trị sau khi Subscriber đã hủy hoặc luồng đã kết thúc, giá trị đó có thể bị loại bỏ. Có thể quan sát bằng:

~~~java
Hooks.onNextDropped(value ->
    log.warn("Reactive value could not be delivered: type={}",
        value == null ? "null" : value.getClass().getName())
);
~~~

Không nên ghi toàn bộ giá trị nếu nó chứa dữ liệu cá nhân hoặc payload lớn. Một số kiểu dữ liệu quản lý tài nguyên như buffer có thể cần được giải phóng khi bị loại bỏ. Với việc loại bỏ phần tử do toán tử cụ thể như filter hoặc take, hãy cân nhắc `doOnDiscard` tại pipeline để cleanup theo kiểu dữ liệu:

~~~java
Flux<ByteBuf> payloads =
    incomingPayloads
        .filter(this::isRelevant)
        .doOnDiscard(ByteBuf.class, ByteBuf::release);
~~~

`doOnDiscard` là cơ chế cleanup theo pipeline cho những toán tử hỗ trợ discard; nó không giống hook toàn cục `onNextDropped`. Dùng đúng cơ chế giúp tránh giải phóng tài nguyên hai lần hoặc bỏ sót tài nguyên.

### onOperatorError

`Hooks.onOperatorError` cho phép quan sát hoặc chuyển đổi exception phát sinh khi Reactor xử lý lỗi ở một toán tử, ví dụ callback người dùng ném exception trong `map`:

~~~java
Hooks.onOperatorError((error, data) -> {
    log.error("Operator failed while processing data type={}",
        data == null ? "unknown" : data.getClass().getName(),
        error);
    return error;
});
~~~

Hook nhận exception và đối tượng dữ liệu liên quan nếu có, rồi trả về exception sẽ tiếp tục đi qua pipeline. Nếu chỉ muốn quan sát, hãy trả lại chính exception. Nếu muốn chuyển đổi, giữ cause và ngữ nghĩa gốc:

~~~java
Hooks.onOperatorError((error, data) ->
    new PipelineMappingException("A mapping operation failed", error)
);
~~~

Không nên biến mọi lỗi thành một exception chung nếu việc đó làm mất loại lỗi gốc cần thiết cho recovery. Hook này cũng không bắt mọi lỗi được phát từ upstream: một Publisher có thể phát `onError` trực tiếp mà không phát sinh lỗi trong callback của toán tử hiện tại.

## 6. Hook lắp ráp toán tử và instrumentation

`Hooks.onEachOperator` và `Hooks.onLastOperator` tác động trong giai đoạn lắp ráp Publisher. Chúng cho phép tích hợp instrumentation hoặc bọc Subscriber/Publisher ở quy mô ứng dụng. Đây là cơ chế nâng cao, thường được thư viện tracing, metrics hoặc công cụ debug sử dụng.

Khác với `doOnError`, hook lắp ráp không chỉ gắn callback quan sát một tín hiệu. Nó có thể thay đổi cách các toán tử được bọc và ảnh hưởng đến nhiều pipeline được tạo sau khi hook được cài đặt. Vì vậy:

- Chỉ cài hook khi thực sự cần instrumentation xuyên suốt ứng dụng.
- Đăng ký hook sớm, trước khi tạo những Publisher cần được instrument.
- Dùng key riêng nếu API overload được chọn hỗ trợ key, để quản lý hook của từng thành phần.
- Không bọc Publisher hoặc Subscriber theo cách làm thay đổi demand, cancellation hay thứ tự tín hiệu.
- Đo overhead và kiểm tra tương thích với các thư viện khác cũng sử dụng hook.

Không dùng `onEachOperator` chỉ để ghi log mọi lỗi. Đối với một pipeline cụ thể, `doOnError`, `doOnEach` hoặc tracing ở tầng ứng dụng thường dễ hiểu và ít tác động hơn.

## 7. Lỗi do thiếu error callback khi subscribe

Một nguồn nhầm lẫn khác là gọi overload `subscribe` mà không cung cấp error consumer:

~~~java
somePublisher.subscribe(value -> process(value));
~~~

Overload này có callback xử lý giá trị nhưng không có callback lỗi do ứng dụng cung cấp. Khi Publisher phát lỗi thông thường, Reactor dùng hành vi mặc định để báo rằng lỗi không có error callback phù hợp; ứng dụng có thể thấy `Exceptions.ErrorCallbackNotImplemented` bao quanh lỗi gốc.

Đây là tình huống khác với dropped error:

- **Thiếu error callback:** lỗi được phát tới cơ chế Subscriber mặc định nhưng ứng dụng không cung cấp nơi xử lý lỗi.
- **Dropped error:** không còn Subscriber hợp lệ để nhận lỗi vì luồng đã hủy hoặc kết thúc, hoặc tín hiệu không thể được chuyển tiếp.

Ở điểm subscribe do ứng dụng tự quản lý, hãy cung cấp cả callback thành công và lỗi:

~~~java
Disposable task = somePublisher.subscribe(
    value -> process(value),
    error -> log.error("Background task failed", error),
    () -> log.info("Background task completed")
);
~~~

Nếu không cần tự quản lý subscription, tốt hơn là trả Publisher về caller hoặc framework để lỗi vẫn nằm trong pipeline và được xử lý tại ranh giới phù hợp.

Đừng dùng `Hooks.onErrorDropped` như một cách thay thế error consumer bị thiếu. Hai tình huống có ngữ nghĩa khác nhau và cần được theo dõi riêng.

## 8. Quan sát lỗi toàn cục mà không làm hệ thống tệ hơn

Hook toàn cục có thể được gọi trên thread phát tín hiệu hoặc thread của thư viện tích hợp. Callback nên ngắn, không chặn và an toàn khi được gọi đồng thời.

Một số nguyên tắc vận hành:

1. **Không thực hiện I/O blocking trong hook.** Ghi log qua logger bất đồng bộ hoặc đẩy một bản ghi nhỏ vào hàng đợi có giới hạn.
2. **Không ném exception từ hook.** Nếu chính callback quan sát lỗi ném lỗi mới, việc điều tra sẽ khó hơn và có thể làm mất thông tin ban đầu.
3. **Không bỏ qua lỗi một cách im lặng.** Hook rỗng hoặc chỉ tăng metric không có ngữ cảnh có thể khiến lỗi quan trọng biến mất khỏi khả năng điều tra.
4. **Giới hạn cardinality của metric.** Dùng loại exception, dependency hoặc mã lỗi ổn định; tránh tag theo message, request ID hay payload.
5. **Không ghi dữ liệu nhạy cảm.** Log stack trace và metadata đã lọc, không ghi token, mật khẩu hoặc nội dung message nguyên vẹn.
6. **Tách lỗi vận hành khỏi lỗi nghiệp vụ.** Dropped error thường là tín hiệu vòng đời hoặc race; không nên tính chung với lỗi validation của request.
7. **Có cảnh báo theo ngưỡng.** Một vài callback đến muộn có thể là race được dự kiến; tỷ lệ tăng đột biến có thể chỉ ra rò rỉ listener hoặc nguồn không dừng.

Ví dụ một hook nhẹ:

~~~java
Hooks.onErrorDropped(error -> {
    Throwable cause = Exceptions.unwrap(error);

    droppedErrors.increment(
        Tags.of("type", cause.getClass().getSimpleName())
    );

    logger.error("Undeliverable reactive error", cause);
});
~~~

Trong hệ thống có lưu lượng cao, nên cân nhắc rate limit log hoặc lấy mẫu để tránh một lỗi lặp lại tạo ra lượng log quá lớn. Không được rate limit theo cách làm mất metric tổng; metric có thể ghi nhận mọi lần trong khi log chi tiết được lấy mẫu.

## 9. Dùng Reactor Context cho ngữ cảnh theo subscription

Hook toàn cục có phạm vi tiến trình và thường không biết đầy đủ ngữ cảnh nghiệp vụ của từng request. Nếu cần ghi correlation ID, tenant hoặc trace context, hãy ưu tiên mang thông tin đó theo Reactor Context và quan sát lỗi trong pipeline nơi context còn sẵn.

Ví dụ:

~~~java
Mono<Response> response =
    remoteClient.fetch()
        .doOnEach(signal -> {
            if (signal.isOnError()) {
                String requestId = signal.getContextView()
                    .getOrDefault("requestId", "unknown");

                log.error("Request {} failed", requestId, signal.getThrowable());
            }
        })
        .contextWrite(context -> context.put("requestId", requestId));
~~~

`doOnEach` nhận tín hiệu và có thể đọc ContextView gắn với tín hiệu đó. Đây là vị trí thích hợp để ghi lỗi thông thường cùng ngữ cảnh của subscription.

Không nên giả định hook toàn cục `onErrorDropped` tự động có cùng Context như một callback `doOnEach` của pipeline. Nếu cần liên kết dropped error với request, hãy thiết kế adapter hoặc nguồn phát để ghi nhận metadata an toàn ngay khi callback được tạo, hoặc ghi nhận trạng thái vòng đời bằng cơ chế riêng. Tránh lưu mutable request context trong biến static dùng chung giữa các subscription.

## 10. Kiểm thử dropped error và quản lý trạng thái hook

Các hook trong `Hooks` là trạng thái toàn cục. Một bài test cài hook phải khôi phục trạng thái sau khi chạy để không ảnh hưởng test khác.

Ví dụ, ta có thể dùng `Flux.create` để giữ sink, hủy subscription rồi mô phỏng callback lỗi đến muộn:

~~~java
AtomicReference<FluxSink<String>> sinkRef = new AtomicReference<>();
AtomicReference<Throwable> dropped = new AtomicReference<>();

Hooks.onErrorDropped(dropped::set);

try {
    Flux<String> source = Flux.create(sink -> sinkRef.set(sink));

    Disposable subscription = source.subscribe(value -> {});

    subscription.dispose();

    sinkRef.get().error(new IllegalStateException("late callback"));

    assertThat(dropped.get())
        .isInstanceOf(IllegalStateException.class);
} finally {
    Hooks.resetOnErrorDropped();
}
~~~

Ví dụ minh họa việc kiểm tra lỗi được phát sau cancellation. Trong test thực tế, cần bảo đảm callback lỗi thật sự xảy ra sau khi dispose và kiểm tra thêm kết quả phát của nguồn nếu adapter cung cấp trạng thái phát. Việc reset phải nằm trong `finally` để kể cả assertion thất bại, hook toàn cục cũng được khôi phục.

Có thể kiểm thử thêm các trường hợp:

- Callback lỗi xảy ra sau `onComplete`.
- Hai callback cạnh tranh gọi `sink.error`.
- Listener được gỡ khi Subscriber hủy và callback đến muộn không tiếp tục tạo tác dụng phụ.
- Lỗi thông thường vẫn được `doOnError` hoặc error consumer nhận.
- Dropped error được ghi nhận nhưng không làm phát sinh exception mới từ hook.
- Hook không rò rỉ sang test chạy tiếp theo.

Không nên chạy các test thay đổi global hook song song nếu chúng có thể cài/reset cùng một hook. Có thể tuần tự hóa nhóm test này hoặc cô lập cấu hình hook ở fixture có vòng đời rõ ràng.

## 11. Reset và quản lý hook

Reactor cung cấp các phương thức reset để khôi phục hành vi hook mặc định, ví dụ:

~~~java
Hooks.resetOnErrorDropped();
Hooks.resetOnNextDropped();
Hooks.resetOnOperatorError();
~~~

Một số hook lắp ráp có cơ chế reset riêng. Hãy dùng đúng phương thức tương ứng với hook đã cài và đọc API của phiên bản Reactor đang dùng trước khi quản lý hook có key hoặc nhiều thành phần cùng đăng ký.

Không gọi `Hooks.reset()` tùy tiện trong ứng dụng đang chạy vì nó có thể xóa cấu hình hook do framework hoặc thư viện khác cài đặt. Reset toàn cục phù hợp hơn trong test hoặc môi trường khởi tạo được kiểm soát, nơi thành phần sở hữu hook chịu trách nhiệm cài và khôi phục.

Nếu ứng dụng có nhiều module cần quan sát lỗi, nên thống nhất một cấu hình hook ở cấp ứng dụng và cho các module gửi metric/log qua thành phần đó. Việc nhiều module tự ý cài rồi reset hook có thể gây mất callback hoặc thay đổi thứ tự quan sát khó dự đoán.

## 12. Những nhầm lẫn thường gặp

- **Dropped error giống lỗi bình thường:** lỗi bình thường được truyền qua `onError`; dropped error không còn Subscriber hợp lệ để nhận.
- **`doOnError` nhìn thấy mọi exception:** nó chỉ thấy lỗi đi qua vị trí toán tử; lỗi đến sau cancellation có thể không đi qua pipeline.
- **`onErrorDropped` có thể phục hồi workflow:** hook chỉ quan sát lỗi không thể chuyển tiếp; muốn phục hồi phải thiết kế kênh xử lý độc lập.
- **Thiếu error callback là dropped error:** `ErrorCallbackNotImplemented` xuất hiện khi subscribe không cung cấp error consumer; đó là trường hợp khác.
- **`onOperatorError` nhận tất cả lỗi:** hook này liên quan đến lỗi phát sinh trong đường thực thi toán tử, không thay thế handler cho mọi lỗi upstream.
- **`onNextDropped` giống `doOnDiscard`:** một hook quan sát phần tử bị loại bỏ toàn cục, còn `doOnDiscard` xử lý cleanup phần tử bị discard ở những toán tử hỗ trợ trong một pipeline.
- **Hook toàn cục chỉ ảnh hưởng một request:** hook `Hooks` có phạm vi tiến trình và có thể ảnh hưởng nhiều pipeline.
- **Có thể log mọi payload trong hook:** payload có thể chứa dữ liệu nhạy cảm và tạo log/metric quá lớn.
- **Reset hook là thao tác vô hại:** reset có thể xóa cấu hình của module khác; cần có một chủ sở hữu rõ ràng.
- **Callback đến muộn có thể bỏ qua cleanup:** dropped error là tín hiệu cần điều tra vòng đời listener, request và cancellation.

## 13. Bài tập vận dụng

Một adapter tích hợp thư viện cảm biến. Mỗi subscription đăng ký một listener; khi Subscriber hủy, adapter gọi `removeListener`. Tuy nhiên, đôi khi thư viện vẫn gọi callback lỗi sau khi listener đã bị gỡ.

Hãy thiết kế cách quan sát và xử lý:

1. Vì sao callback lỗi sau cancellation có thể trở thành dropped error?
2. Vì sao `doOnError` ở cuối pipeline có thể không nhận được lỗi này?
3. Cài `Hooks.onErrorDropped` để ghi metric và log an toàn như thế nào?
4. Những metadata nào có thể dùng để điều tra mà không ghi payload nhạy cảm?
5. Làm sao phân biệt lỗi này với trường hợp code gọi `subscribe` mà không cung cấp error consumer?
6. Ngoài hook, adapter cần kiểm tra hoặc cải thiện điều gì để giảm callback đến muộn?
7. Viết một test cài hook, hủy subscription, phát lỗi muộn và reset hook trong `finally`.

**Gợi ý:** hook toàn cục là điểm quan sát cuối cùng, không phải giải pháp thay thế cleanup. Adapter vẫn cần gỡ listener, đánh dấu trạng thái đã dispose và tránh kích hoạt thêm tác dụng phụ từ callback đến muộn. Test phải reset hook để không ảnh hưởng test khác.

## Kết luận

Dùng `onError` cho lỗi còn nằm trong vòng đời của Subscription; dùng `onErrorDropped` để quan sát lỗi không thể chuyển tiếp vì Subscriber đã hủy, luồng đã kết thúc hoặc tín hiệu đến muộn. `Hooks.onErrorDropped`, `onNextDropped` và `onOperatorError` phục vụ các điểm khác nhau, còn hook lắp ráp toán tử dành cho instrumentation nâng cao. Hook toàn cục cần được cài đặt có chủ sở hữu, callback nhẹ và an toàn đồng thời, đồng thời phải bảo vệ dữ liệu nhạy cảm. Hãy kết hợp hook với `doOnError`, Reactor Context, metric vòng đời và cleanup listener để vừa quan sát được lỗi, vừa sửa đúng nguyên nhân tạo ra tín hiệu không thể chuyển tiếp.
