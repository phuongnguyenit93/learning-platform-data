# Lưu trạng thái khả biến dùng chung giữa nhiều đăng ký

Một pipeline Reactor thường được khai báo một lần rồi được nhiều request, subscriber hoặc tác vụ nền sử dụng. Nếu pipeline giữ một object mutable bên ngoài các operator, nhiều lần đăng ký có thể cùng thay đổi object đó. Kết quả là dữ liệu của request này ảnh hưởng request khác, bộ đếm không bắt đầu lại, danh sách tích lũy lớn dần hoặc các thao tác đồng thời tạo ra race condition.

Lỗi này dễ bị bỏ qua vì publisher có thể là cold. Cold publisher thường chạy lại nguồn cho mỗi subscription, nhưng điều đó không tự tạo lại những object mutable đã được tạo khi lắp ráp pipeline. Một lambda map hoặc doOnNext có thể được dùng lại giữa nhiều subscription và tiếp tục đóng trên cùng một biến.

Trong lập trình reactive, cần xác định rõ trạng thái thuộc về ai và tồn tại trong bao lâu. Trạng thái có thể thuộc một phần tử, một subscription, một request nghiệp vụ hoặc toàn ứng dụng. Khi phạm vi sở hữu không rõ ràng, pipeline có thể cho kết quả sai dù không có lỗi biên dịch.

## 1. Vì sao trạng thái khả biến dễ bị chia sẻ?

Xét một service tạo pipeline một lần:

    class OrderService {
        private final Flux<Order> orders;
        private final AtomicLong sequence = new AtomicLong();

        OrderService(Flux<Order> orders) {
            this.orders = orders;
        }

        Flux<SequencedOrder> sequencedOrders() {
            return orders.map(order ->
                new SequencedOrder(
                    sequence.incrementAndGet(),
                    order
                )
            );
        }
    }

    record SequencedOrder(long sequence, Order order) {}

AtomicLong được tạo cùng service. Mỗi lần gọi sequencedOrders() tạo một Flux mới, nhưng tất cả Flux đều tham chiếu đến cùng bộ đếm. Nếu hai request subscribe, request thứ hai có thể tiếp tục từ số thứ tự mà request thứ nhất đã dùng.

AtomicLong bảo đảm thao tác tăng là atomic khi nhiều thread cùng gọi, nhưng nó không thay đổi phạm vi sở hữu. Giá trị vẫn được chia sẻ giữa mọi subscription. Nếu yêu cầu nghiệp vụ là mỗi request bắt đầu từ 1, dùng AtomicLong chỉ che race condition mà không sửa lỗi ngữ nghĩa.

Một ví dụ khác:

    List<Event> observed = new ArrayList<>();

    Flux<Event> monitored =
        eventSource.events()
            .doOnNext(observed::add);

Danh sách observed được tạo bên ngoài pipeline. Mỗi subscriber có thể thêm phần tử vào cùng danh sách. Danh sách không có giới hạn nên có thể tăng mãi; nếu các subscription chạy đồng thời, ArrayList còn có thể bị cập nhật không an toàn.

## 2. Phân biệt assembly time và subscription time

Reactor xây dựng pipeline theo hai thời điểm:

- Assembly time: các operator được nối với nhau, lambda và biến capture được tạo, publisher kết quả được mô tả.
- Subscription time: subscriber đăng ký, nguồn được kích hoạt theo semantics của publisher, demand và tín hiệu bắt đầu đi qua pipeline.

Ví dụ:

    AtomicInteger calls = new AtomicInteger();

    Flux<Integer> pipeline =
        Flux.range(1, 3)
            .map(value -> {
                int call = calls.incrementAndGet();
                return call * 100 + value;
            });

    // Chưa có subscription, calls vẫn bằng 0.

    StepVerifier.create(pipeline)
        .expectNext(101, 202, 303)
        .verifyComplete();

    StepVerifier.create(pipeline)
        .expectNext(401, 502, 603)
        .verifyComplete();

Flux.range là nguồn cold và phát lại các số 1, 2, 3 cho mỗi subscription. Tuy nhiên, biến calls được tạo bên ngoài operator và vẫn được dùng chung. Lần đăng ký thứ hai tiếp tục bộ đếm từ lần thứ nhất.

Không phải mọi state bên trong Reactor đều bị chia sẻ. Các operator built-in thường tạo state nội bộ theo subscription. Rủi ro chính xuất hiện khi ứng dụng tự tạo object mutable bên ngoài operator rồi capture object đó trong lambda hoặc giữ nó trong field dùng chung.

## 3. Cold publisher không tự cô lập closure

Cold publisher mô tả rằng mỗi subscription có thể kích hoạt một lần thực thi nguồn riêng. Nó không có nghĩa mọi object trong biểu thức Java đều được tạo lại cho mỗi subscription.

Ví dụ:

    AtomicLong sharedCounter = new AtomicLong();

    Flux<Long> values =
        Flux.range(1, 2)
            .map(ignored -> sharedCounter.incrementAndGet());

Hai subscription đều kích hoạt Flux.range riêng, nhưng mapper dùng chung sharedCounter.

    StepVerifier.create(values)
        .expectNext(1L, 2L)
        .verifyComplete();

    StepVerifier.create(values)
        .expectNext(3L, 4L)
        .verifyComplete();

Nếu muốn mỗi subscriber nhận 1, 2, cần tạo bộ đếm trong phạm vi subscription. Operator defer giải quyết đúng việc này.

## 4. Tạo state riêng bằng Flux.defer

Flux.defer nhận một supplier được gọi khi có subscription. Đặt việc khởi tạo state bên trong supplier để mỗi subscription nhận object mới:

    Flux<SequencedOrder> sequencedOrders =
        Flux.defer(() -> {
            AtomicLong sequence = new AtomicLong();

            return orderSource
                .map(order ->
                    new SequencedOrder(
                        sequence.incrementAndGet(),
                        order
                    )
                );
        });

Mỗi subscription gọi supplier một lần, tạo một AtomicLong mới rồi xây dựng pipeline cho subscription đó. Các subscriber không dùng chung bộ đếm.

Nếu nguồn phát hai đơn hàng:

    StepVerifier.create(sequencedOrders)
        .expectNextMatches(item -> item.sequence() == 1)
        .expectNextMatches(item -> item.sequence() == 2)
        .verifyComplete();

    StepVerifier.create(sequencedOrders)
        .expectNextMatches(item -> item.sequence() == 1)
        .expectNextMatches(item -> item.sequence() == 2)
        .verifyComplete();

defer không tự biến nguồn hot thành cold. Nó trì hoãn việc gọi supplier cho từng subscription; publisher được supplier trả về vẫn giữ semantics riêng của nó. Nếu supplier trả về cùng một nguồn hot bên ngoài, các subscription vẫn tiêu thụ nguồn hot đó.

## 5. Dùng Mono.defer cho state của một kết quả

Quy tắc tương tự áp dụng với Mono:

    Mono<RequestResult> result =
        Mono.defer(() -> {
            RequestContext context =
                new RequestContext(UUID.randomUUID());

            return service.execute(context)
                .map(value ->
                    new RequestResult(context.requestId(), value)
                );
        });

Mỗi subscription tạo một RequestContext mới. Đây là lựa chọn phù hợp khi context thuộc một lần thực thi, ví dụ correlation ID nội bộ, bộ đếm cục bộ hoặc accumulator của request.

Không tạo context trong field của singleton service nếu nó phải riêng cho từng request. Spring service thường là singleton; field mutable trong service vì thế thường được chia sẻ giữa các request.

## 6. Đóng gói phép biến đổi có state bằng transformDeferred

Khi cần tái sử dụng một nhóm operator nhưng state phải riêng cho từng subscription, có thể dùng transformDeferred:

    Function<Flux<Order>, Flux<SequencedOrder>> addSequence =
        flux -> {
            AtomicLong sequence = new AtomicLong();

            return flux.map(order ->
                new SequencedOrder(
                    sequence.incrementAndGet(),
                    order
                )
            );
        };

    Flux<SequencedOrder> sequenced =
        orderSource.transformDeferred(addSequence);

transformDeferred áp dụng hàm biến đổi khi từng subscription bắt đầu. Vì AtomicLong được tạo bên trong hàm, mỗi subscription có một bộ đếm riêng.

Nếu dùng transform thay thế:

    Flux<SequencedOrder> sharedSequence =
        orderSource.transform(flux -> {
            AtomicLong sequence = new AtomicLong();

            return flux.map(order ->
                new SequencedOrder(
                    sequence.incrementAndGet(),
                    order
                )
            );
        });

Hàm biến đổi được áp dụng lúc lắp ráp. Bộ đếm tạo trong hàm có thể được chia sẻ bởi các subscription của publisher kết quả. Hãy chọn theo thời điểm cần khởi tạo state:

| Operator | Khi hàm biến đổi được áp dụng | State tạo bên trong hàm |
|---|---|---|
| transform | Assembly time | Có thể dùng chung giữa subscription |
| transformDeferred | Mỗi subscription | Riêng cho từng subscription |
| defer | Mỗi subscription gọi supplier | Riêng nếu supplier tạo object mới |

Nếu state cần đọc Reactor Context của từng subscriber, cân nhắc transformDeferredContextual để lấy ContextView trong lúc áp dụng phép biến đổi.

## 7. Ưu tiên accumulator bất biến

Không phải lúc nào cũng cần mutable state. Với phép tính tích lũy, một accumulator bất biến thường dễ hiểu và an toàn hơn:

    record Balance(long cents) {}

    Flux<Balance> balances =
        transactions
            .scan(
                new Balance(0),
                (balance, transaction) ->
                    new Balance(
                        balance.cents() + transaction.amountCents()
                    )
            )
            .skip(1);

Mỗi bước tạo một Balance mới. Không có object accumulator bị thay đổi rồi chia sẻ giữa các tín hiệu hoặc subscription.

Một ví dụ sai thường gặp:

    List<Order> collected = new ArrayList<>();

    Flux<List<Order>> snapshots =
        orderSource
            .scan(collected, (list, order) -> {
                list.add(order);
                return list;
            });

Mỗi tín hiệu phát ra cùng một List đã bị thay đổi. Subscriber giữ tham chiếu đến snapshot cũ có thể thấy nội dung thay đổi về sau. Nhiều subscription cũng có thể cùng mutate danh sách đó.

Nếu cần snapshot tích lũy, tạo danh sách mới hoặc dùng cấu trúc bất biến:

    Flux<List<Order>> snapshots =
        orderSource.scan(
            List.<Order>of(),
            (previous, order) -> {
                List<Order> next =
                    new ArrayList<>(previous);
                next.add(order);
                return List.copyOf(next);
            }
        ).skip(1);

Ví dụ này an toàn về chia sẻ tham chiếu nhưng mỗi bước sao chép danh sách nên chi phí CPU và bộ nhớ tăng theo số phần tử. Với tập dữ liệu lớn, hãy chọn aggregate nhỏ, batch hoặc lưu trạng thái ở nơi phù hợp thay vì tạo snapshot đầy đủ sau mỗi tín hiệu.

## 8. reduce và collect: state nội bộ theo subscription

Các operator như collectList, collectMap và reduceWith được thiết kế để duy trì accumulator trong quá trình một subscription:

    Mono<Long> total =
        orderAmounts.reduce(0L, Long::sum);

    Mono<List<Order>> page =
        orderSource
            .take(100)
            .collectList();

collectList tạo danh sách cho subscription và chỉ phát nó khi nguồn hoàn tất. reduce giữ accumulator trong quá trình subscription. Chúng không giống việc ứng dụng tạo một List hoặc Map ở field rồi capture vào lambda.

Nếu accumulator là mutable và cần tạo mới mỗi lần đăng ký, dùng supplier:

    Mono<List<Order>> allOrders =
        orderSource.reduceWith(
            ArrayList::new,
            (list, order) -> {
                list.add(order);
                return list;
            }
        );

reduceWith gọi supplier để tạo accumulator theo subscription. Tuy nhiên, accumulator vẫn tăng theo số phần tử; tạo riêng không đồng nghĩa với giới hạn bộ nhớ. Hãy giới hạn nguồn hoặc dùng batch khi tập dữ liệu lớn.

## 9. Atomic không thay thế việc xác định ownership

Các lớp như AtomicInteger, AtomicLong, LongAdder và ConcurrentHashMap giúp bảo vệ một số thao tác khi nhiều thread truy cập cùng state. Chúng không quyết định state nên được chia sẻ hay cô lập.

Ví dụ, đây là state dùng chung có chủ đích:

    private final AtomicLong totalRequests = new AtomicLong();

    Mono<Response> handle(Request request) {
        return process(request)
            .doOnSubscribe(ignored ->
                totalRequests.incrementAndGet()
            );
    }

Nếu mục tiêu là metric toàn service, bộ đếm dùng chung là hợp lý. Cần dùng metric library có lifecycle và cách export phù hợp trong ứng dụng thật.

Ngược lại, đây là state thuộc request:

    Mono<Response> handle(Request request) {
        return Mono.defer(() -> {
            AtomicLong localSteps = new AtomicLong();

            return process(request)
                .doOnNext(ignored ->
                    localSteps.incrementAndGet()
                );
        });
    }

Không nên đưa localSteps thành field chỉ vì AtomicLong đã thread-safe. Việc đó sẽ biến state riêng request thành state toàn service.

Hãy tự hỏi: Nếu hai request chạy đồng thời, chúng có được phép nhìn thấy và thay đổi cùng giá trị này không? Nếu câu trả lời là không, hãy tạo state trong defer hoặc transformDeferred.

## 10. Signals được tuần tự hóa trong một subscription, nhưng nhiều subscription có thể chạy đồng thời

Reactive Streams yêu cầu các tín hiệu tới một subscriber tuân theo quy tắc tuần tự hóa. Điều này giúp một state cục bộ được cập nhật bởi callback của cùng một subscription không bị gọi đồng thời theo cách tùy tiện.

Tuy nhiên, hai subscription khác nhau có thể chạy đồng thời trên các thread khác nhau. Nếu chúng capture cùng một ArrayList hoặc HashMap, các callback vẫn có thể mutate object cùng lúc.

Ngoài ra, flatMap có thể chạy nhiều inner publisher đồng thời. Nếu mỗi inner publisher gọi một callback có side effect lên cùng object mutable, các thao tác đó có thể cạnh tranh:

    List<Receipt> receipts = new ArrayList<>();

    Flux<Receipt> result =
        orders.flatMap(order ->
            paymentClient.charge(order)
                .doOnNext(receipts::add)
        );

Nhiều inner publisher có thể phát trên các thread khác nhau. ArrayList không an toàn cho cập nhật đồng thời. Cách đơn giản hơn là để kết quả đi theo pipeline:

    Flux<Receipt> receipts =
        orders.flatMap(
            paymentClient::charge,
            8
        );

Nếu cần xử lý side effect sau khi có tất cả kết quả, đặt operator ở downstream:

    Mono<List<Receipt>> allReceipts =
        orders.flatMap(paymentClient::charge, 8)
            .collectList();

collectList quản lý accumulator cho subscription hiện tại. Nếu cần giữ thứ tự theo đơn hàng đầu vào, dùng concatMap hoặc flatMapSequential tùy semantics và chi phí mong muốn.

## 11. State trong flatMap và mỗi inner publisher

Đôi khi mỗi phần tử cần một accumulator riêng cho inner publisher. Hãy tạo state bên trong callback của flatMap hoặc dùng defer nếu việc tạo nguồn cần được trì hoãn:

    Flux<ProcessedOrder> processed =
        orders.flatMap(order ->
            Mono.defer(() -> {
                AtomicInteger attempts = new AtomicInteger();

                return paymentClient.charge(order)
                    .doOnSubscribe(ignored ->
                        attempts.incrementAndGet()
                    )
                    .map(receipt ->
                        new ProcessedOrder(order, receipt)
                    );
            }),
            8
        );

Mỗi inner publisher có state riêng cho order tương ứng. Concurrency 8 cho phép tối đa tám inner publisher hoạt động cùng lúc; mỗi inner state vẫn thuộc một order, không dùng chung giữa các order.

Không tạo một AtomicInteger bên ngoài flatMap nếu bộ đếm phải riêng từng order. Ngược lại, nếu cần đếm tổng số lần gọi cho toàn pipeline, một metric dùng chung có thể là đúng semantics.

## 12. Retry và việc khởi tạo lại state

Retry tạo subscription mới đến publisher upstream. State được capture bên ngoài defer có thể tồn tại qua các lần retry:

    AtomicInteger attempts = new AtomicInteger();

    Mono<Result> result =
        remoteCall()
            .doOnSubscribe(ignored ->
                attempts.incrementAndGet()
            )
            .retry(2);

Ở đây attempts có thể tiếp tục tăng qua các lần subscribe do retry tạo ra. Nếu biến này là metric tổng số lần thử của request, điều đó có thể được chủ ý.

Nếu state phải được tạo lại cho mỗi lần subscription/retry, đặt nó bên trong defer:

    Mono<Result> result =
        Mono.defer(() -> {
            AtomicInteger localAttempts = new AtomicInteger();

            return remoteCall()
                .doOnSubscribe(ignored ->
                    localAttempts.incrementAndGet()
                );
        })
        .retry(2);

Vị trí của defer so với retry quyết định supplier có được gọi lại khi retry resubscribe hay không. Với ví dụ trên, retry resubscribe vào Mono.defer nên supplier chạy lại và tạo state mới cho mỗi lần thử. Nếu cần đếm số lần thử trong cùng một logical request, hãy đặt bộ đếm ở phạm vi request bên ngoài phần được retry và ghi rõ ownership đó.

Có thể kết hợp hai lớp defer để state riêng cho một lần gọi bên ngoài nhưng được giữ qua các attempt retry:

    Mono<Result> logicalOperation =
        Mono.defer(() -> {
            AtomicInteger attemptsForThisCall =
                new AtomicInteger();

            return Mono.defer(() ->
                    remoteCall()
                        .doOnSubscribe(ignored ->
                            attemptsForThisCall.incrementAndGet()
                        )
                )
                .retry(2)
                .map(value ->
                    new Result(value, attemptsForThisCall.get())
                );
        });

Lớp defer ngoài tạo counter mới cho mỗi subscription của caller. Lớp defer trong tạo publisher remoteCall mới mỗi khi retry resubscribe. Counter được giữ qua các lần thử của cùng một logical operation, nhưng không bị chia sẻ với subscription tiếp theo.

Đừng nhầm một subscription của caller với một subscription upstream. Retry, repeat, timeout fallback và một số operator chia nhánh có thể tạo thêm subscription ở phía trên. Xác định state thuộc logical operation hay thuộc từng attempt.

## 13. share và cache làm thay đổi ranh giới chia sẻ

Các operator chia sẻ nguồn như share, publish().refCount() và cache làm thay đổi số subscription đến upstream:

- share() multicast tín hiệu hiện tại cho các subscriber đang kết nối.
- cache() lưu tín hiệu để subscriber đến sau có thể nhận lại theo chính sách cache.
- publish().refCount() chia sẻ một kết nối upstream trong khi số subscriber đáp ứng điều kiện refCount.

Ví dụ:

    AtomicLong sequence = new AtomicLong();

    Flux<SequencedEvent> shared =
        eventSource.events()
            .map(event ->
                new SequencedEvent(
                    sequence.incrementAndGet(),
                    event
                )
            )
            .share();

Các subscriber đang cùng kết nối nhận cùng những tín hiệu đã được đánh số từ một upstream subscription. Bộ đếm thuộc luồng chia sẻ, không phải mỗi subscriber.

Nếu đặt map sau share, mỗi subscriber có subscription downstream riêng nhưng mapper lambda vẫn có thể capture cùng một bộ đếm đã tạo lúc assembly. Vì vậy, việc đặt operator trước hay sau share không tự làm object mutable trong closure trở nên riêng biệt.

Hãy vẽ ranh giới chia sẻ của pipeline trước khi thêm state. Xác định state thuộc upstream dùng chung, từng downstream subscriber hay từng request nghiệp vụ.

## 14. Reactor Context không phải nơi tự động clone object

Reactor Context gắn metadata với subscription và phù hợp cho correlation ID, tenant ID hoặc thông tin xác thực bất biến:

    Mono<Response> response =
        service.call()
            .flatMap(value ->
                Mono.deferContextual(context -> {
                    String requestId =
                        context.get("requestId");
                    return enrich(value, requestId);
                })
            )
            .contextWrite(context ->
                context.put("requestId", "req-123")
            );

Context có tính bất biến ở cấu trúc key/value, nhưng value có thể là một object mutable. Nếu nhiều subscription cùng đưa vào một List hoặc Map rồi giữ tham chiếu đó trong Context, object vẫn có thể bị chia sẻ.

Ưu tiên lưu giá trị bất biến trong Context. Nếu cần mutable state theo subscription, tạo nó bên trong deferContextual hoặc transformDeferredContextual và không đưa tham chiếu đó ra phạm vi dùng chung.

## 15. Không dùng ThreadLocal để giả lập state theo subscription

ThreadLocal gắn dữ liệu với thread, trong khi một pipeline reactive có thể chuyển qua nhiều thread vì publishOn, subscribeOn, connector hoặc scheduler. Một subscription cũng có thể tiếp tục trên thread khác ở những tín hiệu khác nhau.

Vì vậy, ThreadLocal không phải cách đáng tin cậy để lưu request state trong pipeline Reactor. Nó có thể gây mất context hoặc giữ dữ liệu cũ trên thread pool nếu không được dọn đúng lúc.

Dùng Reactor Context cho metadata theo subscription. Dùng defer để tạo object mutable theo subscription. Với logging context, dùng cơ chế context propagation tương thích với phiên bản Reactor/Spring của ứng dụng thay vì tự quản lý ThreadLocal trong operator.

## 16. Quản lý vòng đời của state và tài nguyên

State thuần như counter hoặc accumulator thường có thể được giải phóng khi subscription kết thúc và không còn tham chiếu. Nhưng nếu state giữ tài nguyên bên ngoài như file, socket, cursor hoặc session, cần gắn cleanup với lifecycle.

Với tài nguyên đồng bộ, Reactor có using; với tài nguyên reactive có cleanup bất đồng bộ, cân nhắc usingWhen:

    Mono<String> readFile() {
        return Mono.using(
            this::openReader,
            reader -> Mono.fromCallable(reader::readAll),
            Reader::close
        );
    }

Ví dụ minh họa ownership tài nguyên; nếu readAll là blocking, cần chạy trên scheduler phù hợp cho tác vụ blocking. Cleanup phải được thực hiện khi complete, error hoặc cancel theo contract của API resource.

Không giữ tài nguyên trong field singleton rồi để từng subscription tự sử dụng nếu lifecycle và concurrency chưa được thiết kế. Một tài nguyên dùng chung cần có cơ chế đồng bộ, giới hạn và shutdown rõ ràng.

## 17. Kiểm thử state có bị chia sẻ ngoài ý muốn

Một test tốt nên subscribe nhiều lần vào cùng publisher instance và xác minh state bắt đầu lại theo yêu cầu:

    AtomicLong shared = new AtomicLong();

    Flux<Long> incorrect =
        Flux.range(1, 2)
            .map(ignored -> shared.incrementAndGet());

    StepVerifier.create(incorrect)
        .expectNext(1L, 2L)
        .verifyComplete();

    StepVerifier.create(incorrect)
        .expectNext(3L, 4L)
        .verifyComplete();

Test trên thể hiện hành vi state dùng chung. Nếu đó là bug, sửa bằng defer:

    Flux<Long> isolated =
        Flux.defer(() -> {
            AtomicLong local = new AtomicLong();
            return Flux.range(1, 2)
                .map(ignored -> local.incrementAndGet());
        });

    StepVerifier.create(isolated)
        .expectNext(1L, 2L)
        .verifyComplete();

    StepVerifier.create(isolated)
        .expectNext(1L, 2L)
        .verifyComplete();

Có thể kiểm tra subscription đồng thời bằng StepVerifier hoặc Flux.merge trên hai subscription. Dùng state mutable và counter trong test để xác minh chúng không ảnh hưởng lẫn nhau. Khi test race condition, ưu tiên stress test có kiểm soát hoặc công cụ concurrency chuyên biệt; một test tuần tự không chứng minh thread safety.

## 18. Những lỗi thường gặp

**Cho rằng cold publisher đồng nghĩa state được tạo lại.** Nguồn có thể chạy lại nhưng closure vẫn capture cùng object đã tạo lúc assembly.

**Dùng AtomicLong để sửa state bị chia sẻ sai phạm vi.** Atomic bảo vệ phép tăng, không tạo counter riêng cho từng subscriber.

**Đặt List hoặc Map mutable trong field singleton.** Nhiều request có thể cùng thay đổi và dữ liệu có thể tồn tại lâu hơn dự kiến.

**Tạo accumulator mutable bên ngoài scan hoặc reduce.** Nhiều subscription có thể dùng chung seed hoặc cùng nhìn thấy một object đã bị mutate. Dùng accumulator bất biến hoặc supplier tạo mới như reduceWith.

**Mutate cùng collection trong flatMap.** Inner publisher có thể chạy đồng thời. Trả kết quả qua pipeline rồi collect downstream, hoặc dùng cấu trúc concurrent khi chia sẻ là yêu cầu thực sự.

**Dùng ThreadLocal làm request context.** Pipeline có thể đổi thread. Dùng Reactor Context và cơ chế context propagation.

**Không xét retry và repeat.** Chúng có thể resubscribe upstream; xác định state thuộc logical operation hay từng attempt.

**Quên ranh giới share/cache.** Nhiều subscriber có thể nhận cùng một upstream state hoặc capture cùng mapper closure dù operator được đặt sau share.

**Giữ collection không giới hạn để debug.** Side effect doOnNext có thể âm thầm giữ mọi phần tử. Dùng metric, sampling hoặc buffer có giới hạn.

**Không dọn tài nguyên khi cancel.** File, cursor và session cần cleanup theo lifecycle bằng using/usingWhen hoặc API quản lý phù hợp.

## 19. Checklist xác định ownership của state

Trước khi đưa state mutable vào pipeline, hãy trả lời:

1. State thuộc một phần tử, một inner publisher, một subscription, một request hay toàn service?
2. Object được tạo ở assembly time hay subscription time?
3. Lambda có capture field hoặc biến mutable bên ngoài không?
4. Hai subscription có thể chạy đồng thời và cùng thay đổi object không?
5. Atomic hoặc concurrent collection có giải quyết đúng race, hay chỉ che lỗi ownership?
6. Có thể thay state mutable bằng record hoặc accumulator bất biến không?
7. Có thể tạo state mới bằng defer, Mono.defer hoặc transformDeferred không?
8. Retry/repeat có tạo subscription mới và cần reset state không?
9. share, cache hoặc refCount có làm thay đổi ranh giới upstream dùng chung không?
10. Reactor Context đang giữ value bất biến hay một object mutable được chia sẻ?
11. State có giữ tài nguyên cần cleanup khi complete, error hoặc cancel không?
12. Test đã subscribe nhiều lần và đồng thời để xác minh phạm vi state chưa?

Trạng thái khả biến không phải lúc nào cũng sai. Bộ đếm metric toàn service hoặc cache dùng chung có thể là thiết kế hợp lệ khi ownership, đồng bộ, giới hạn và invalidation được xác định. Lỗi xuất hiện khi state cần riêng cho từng subscription nhưng lại được tạo ở assembly time hoặc đặt trong field dùng chung. Hãy đặt state đúng phạm vi, ưu tiên giá trị bất biến, dùng defer hoặc transformDeferred để tạo state theo subscription và kiểm thử nhiều lần đăng ký trên cùng publisher instance.
