# Kết nối Reactor với Java Flow, CompletionStage và thư viện khác

Một ứng dụng Java hiếm khi chỉ sử dụng một mô hình bất đồng bộ. Dự án có thể dùng Reactor cho pipeline chính, nhưng vẫn phải gọi API trả về CompletableFuture, tích hợp thư viện dựa trên java.util.concurrent.Flow, hoặc tiếp nhận publisher từ một thư viện khác. Khả năng kết nối các mô hình này quyết định liệu ứng dụng có giữ được backpressure, cancellation, xử lý lỗi và quyền sở hữu subscription qua các ranh giới hay không.

Project Reactor cung cấp các điểm chuyển đổi để đưa những API bất đồng bộ phổ biến vào Mono và Flux, hoặc xuất dữ liệu Reactor cho thành phần bên ngoài. Khi tích hợp, cần xem xét cardinality, thời điểm bắt đầu công việc, cách truyền lỗi, khả năng hủy và chính sách điều tiết dữ liệu. Chuyển đổi kiểu dữ liệu chỉ là một phần; hợp đồng vòng đời giữa hai thư viện cũng cần được hiểu rõ.

## 1. Các mô hình bất đồng bộ trong Java

Những API thường gặp biểu diễn các dạng công việc khác nhau:

| API | Mô hình | Số kết quả | Điều tiết nhu cầu |
|---|---|---:|---|
| Mono<T> | Reactor Publisher | 0 hoặc 1 | Reactive Streams |
| Flux<T> | Reactor Publisher | 0 đến nhiều | Reactive Streams |
| Flow.Publisher<T> | JDK Flow | 0 đến nhiều | Có Subscription.request(n) |
| CompletionStage<T> | Kết quả hoàn tất bất đồng bộ | Một kết quả hoặc lỗi | Không có backpressure |
| CompletableFuture<T> | Một implementation của CompletionStage | Một kết quả hoặc lỗi | Không có backpressure |
| Callback API | Hàm callback được gọi khi có kết quả hoặc sự kiện | Tùy API | Tùy thư viện |

Mono và Flux tuân theo Reactive Streams. Flow.Publisher của JDK 9 trở lên có giao thức tương tự nhưng dùng các kiểu trong package java.util.concurrent.Flow. Hai hệ kiểu này có quan hệ về đặc tả nhưng không thể truyền trực tiếp cho nhau vì chữ ký Java khác package.

CompletionStage biểu diễn một kết quả sẽ có trong tương lai. Nó phù hợp với một truy vấn bất đồng bộ hoặc một thao tác trả về một giá trị. Nó không biểu diễn chuỗi nhiều phần tử và không có cơ chế request từng phần tử như Reactive Streams.

Khi chọn adapter, hãy bắt đầu bằng câu hỏi: API bên ngoài trả một kết quả, một chuỗi dữ liệu hay callback nhiều lần? Chọn đúng cardinality giúp tránh gom nhầm một stream thành một future hoặc biến một kết quả đơn thành một luồng không cần thiết.

## 2. Kết nối với Java Flow

Java 9 giới thiệu Flow.Publisher, Flow.Subscriber và Flow.Subscription trong java.util.concurrent.Flow. Giao thức này được thiết kế tương thích về mặt khái niệm với Reactive Streams: subscriber nhận subscription, yêu cầu số phần tử và có thể hủy.

Tuy nhiên, java.util.concurrent.Flow.Publisher<T> không phải cùng kiểu với org.reactivestreams.Publisher<T>. Khi thư viện bên ngoài chỉ cung cấp Java Flow, dùng adapter của Reactor để chuyển đổi.

Reactor cung cấp JdkFlowAdapter trong module adapter. Với phiên bản Reactor tương ứng, thêm dependency reactor-adapter cùng version với reactor-core:

    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-adapter</artifactId>
        <!-- Version được quản lý bởi BOM hoặc dependencyManagement. -->
    </dependency>

Ví dụ chuyển một Flow publisher thành Flux:

    import java.util.concurrent.Flow;
    import reactor.adapter.JdkFlowAdapter;
    import reactor.core.publisher.Flux;

    Flow.Publisher<String> jdkPublisher = jdkClient.events();

    Flux<String> events =
        JdkFlowAdapter.flowPublisherToFlux(jdkPublisher);

Sau chuyển đổi, pipeline có thể dùng các operator Reactor:

    Flux<Event> processed =
        JdkFlowAdapter.flowPublisherToFlux(jdkClient.events())
            .map(this::decode)
            .filter(Event::isRelevant)
            .publishOn(Schedulers.parallel())
            .map(this::enrich);

Chiều ngược lại, khi một API cần Flow.Publisher, chuyển publisher Reactor bằng publisherToFlowPublisher:

    import java.util.concurrent.Flow;
    import reactor.adapter.JdkFlowAdapter;
    import reactor.core.publisher.Flux;

    Flux<Event> reactorEvents = eventService.events();

    Flow.Publisher<Event> flowPublisher =
        JdkFlowAdapter.publisherToFlowPublisher(reactorEvents);

    jdkConsumer.consume(flowPublisher);

Adapter chuyển đổi giao thức và tín hiệu giữa hai hệ kiểu. Nó không biến một nguồn không hỗ trợ backpressure thành nguồn có khả năng phát chậm vật lý; khả năng điều tiết cuối cùng vẫn phụ thuộc publisher gốc.

### 2.1. Điều cần kiểm tra khi chuyển Flow

Java Flow và Reactive Streams cùng có mô hình request(n), cancel, onNext, onError và onComplete. Tuy nhiên, khi tích hợp một thư viện cụ thể, cần xác minh:

- Publisher có tuân thủ giao thức Flow và quy tắc nhu cầu hay không.
- Việc gọi cancel() có dừng nguồn bên dưới hay chỉ ngừng chuyển tín hiệu đến subscriber.
- Publisher có phát tín hiệu đồng thời không đúng hợp đồng hay không.
- Lỗi được chuyển nguyên dạng hay được bọc bởi adapter.
- Thư viện có yêu cầu một executor hoặc scheduler riêng không.

Đừng tạo thêm một hàng đợi không giới hạn chỉ để nối hai API. Nếu nguồn có thể phát nhanh hơn downstream, xác định rõ buffer, drop, latest hoặc chính sách overflow ở ranh giới tích hợp.

## 3. Chuyển CompletionStage và CompletableFuture thành Mono

CompletionStage<T> đại diện cho một kết quả bất đồng bộ đơn lẻ. Reactor có thể chuyển nó thành Mono<T> bằng Mono.fromCompletionStage.

Ví dụ:

    import java.util.concurrent.CompletionStage;
    import reactor.core.publisher.Mono;

    CompletionStage<User> userStage =
        userClient.fetchUser(userId);

    Mono<User> userMono =
        Mono.fromCompletionStage(userStage);

Kết quả stage được chuyển thành một trong các trường hợp:

- Hoàn tất với giá trị: Mono phát một onNext, sau đó onComplete.
- Hoàn tất với null: Mono không thể phát null theo Reactive Streams; adapter xem đây là kết quả rỗng.
- Hoàn tất exceptionally: Mono phát onError.
- Hủy stage hoặc future: hành vi phụ thuộc implementation và cách adapter được cấu hình.

CompletableFuture<T> cũng là một CompletionStage<T>, vì vậy có thể dùng cùng adapter:

    CompletableFuture<Inventory> future =
        inventoryClient.fetchAsync(sku);

    Mono<Inventory> inventory =
        Mono.fromFuture(future);

Mono.fromFuture là lựa chọn thuận tiện khi API trả về CompletableFuture. Nếu API khai báo kiểu tổng quát CompletionStage, Mono.fromCompletionStage thể hiện đúng kiểu đầu vào hơn.

### 3.1. Công việc bắt đầu trước hay sau subscribe?

Nhiều API tạo CompletableFuture sẽ bắt đầu công việc ngay khi gọi phương thức:

    CompletableFuture<User> future =
        userClient.fetchUserAsync(userId);

    Mono<User> user = Mono.fromFuture(future);

Trong trường hợp này, future đã được tạo trước khi subscriber đăng ký vào Mono. Mono chỉ bọc kết quả đang chạy; nó không làm cho thao tác bên ngoài trở nên lazy.

Nếu muốn tạo một future mới cho mỗi subscription, hãy trì hoãn lời gọi API:

    Mono<User> user =
        Mono.defer(() ->
            Mono.fromFuture(
                userClient.fetchUserAsync(userId)
            )
        );

Mỗi lần subscribe, supplier trong defer được gọi và tạo future tương ứng. Điều này quan trọng khi:

- Mỗi subscriber cần một request độc lập.
- Có retry và muốn mỗi lần retry tạo thao tác mới.
- Tham số hoặc context được xác định tại thời điểm subscribe.
- Không muốn bắt đầu công việc nếu không có subscriber.

Không phải mọi CompletionStage đều lazy. Nếu stage đã được khởi chạy trước đó, bọc nó trong Mono.defer không thể quay ngược thời gian để trì hoãn công việc đã bắt đầu; phải trì hoãn cả lời gọi tạo stage.

### 3.2. Ánh xạ lỗi từ CompletionStage

Khi stage hoàn tất exceptionally, Reactor chuyển lỗi thành onError. Một số implementation bọc lỗi gốc trong CompletionException hoặc ExecutionException. Khi phân loại lỗi, cần xem nguyên nhân gốc thay vì giả định kiểu exception luôn là kiểu domain ban đầu.

Có thể chuyển lỗi ở ranh giới:

    Mono<User> user =
        Mono.fromCompletionStage(
            userClient.fetchUser(userId)
        )
        .onErrorMap(
            error -> new UserLookupException(
                "Không thể tải người dùng",
                unwrapCompletionException(error)
            )
        );

unwrapCompletionException trong ví dụ là hàm tiện ích của ứng dụng để lấy cause khi lỗi được bọc. Hãy giữ exception gốc làm cause để log và truy vết. Chỉ chuyển đổi các lỗi mà tầng hiện tại có đủ ngữ cảnh để phân loại.

## 4. Chuyển Mono thành CompletableFuture

Khi thư viện hoặc interface bên ngoài yêu cầu CompletableFuture<T>, có thể chuyển Mono bằng toFuture():

    Mono<User> userMono = userService.findById(userId);

    CompletableFuture<User> userFuture =
        userMono.toFuture();

Việc gọi toFuture() đăng ký vào Mono để hoàn tất future. Future sẽ:

- Hoàn tất với giá trị khi Mono phát phần tử.
- Hoàn tất với null nếu Mono hoàn tất rỗng.
- Hoàn tất exceptionally nếu Mono phát lỗi.

Khác biệt về empty cần được lưu ý: Reactive Streams không phát null qua onNext, còn CompletableFuture có thể hoàn tất với null. Nếu tầng gọi cần phân biệt rõ “không tìm thấy” với giá trị null, hãy chuyển sang kiểu kết quả tường minh, chẳng hạn Optional<T>:

    CompletableFuture<Optional<User>> userFuture =
        userService.findById(userId)
            .map(Optional::of)
            .defaultIfEmpty(Optional.empty())
            .toFuture();

Khi cần chuyển cả một Flux thành future chứa danh sách, hãy gom dữ liệu trước:

    CompletableFuture<List<Event>> allEvents =
        eventService.events()
            .collectList()
            .toFuture();

Việc collectList() chờ nguồn hoàn tất và giữ các phần tử trong bộ nhớ. Không dùng cách này cho stream vô hạn hoặc luồng có kích thước không giới hạn; trong trường hợp đó, tiếp tục xử lý dưới dạng publisher hoặc ghi dữ liệu theo từng phần.

### 4.1. Cancellation hai chiều

Khi chuyển Mono thành CompletableFuture, future đại diện cho subscription đã được tạo. Nếu caller hủy future, adapter Reactor có thể truyền cancellation về subscription. Ngược lại, khi subscriber hủy một Mono được tạo từ CompletableFuture, Reactor có thể yêu cầu hủy future bên dưới nếu future hỗ trợ và adapter không được cấu hình để bỏ qua cancellation.

Tuy nhiên, cancellation không đồng nghĩa thao tác bên ngoài chắc chắn đã dừng:

- CompletableFuture.cancel() thay đổi trạng thái future và có thể yêu cầu hủy công việc.
- Công việc đang chạy chỉ dừng nếu implementation hợp tác với cancellation hoặc interruption.
- Request đã đến server từ xa có thể vẫn được xử lý.
- Một CompletionStage tổng quát không nhất thiết có API hủy.

Các factory từ future và completion stage có overload cho phép cấu hình việc bỏ qua cancellation của nguồn. Dùng tùy chọn suppress cancellation khi future được chia sẻ hoặc thuộc quyền sở hữu của thành phần khác. Không hủy một future dùng chung chỉ vì một subscriber không còn quan tâm đến kết quả.

## 5. Chọn đúng ranh giới cancellation và quyền sở hữu

Khi bọc một future, cần xác định ai sở hữu nó:

| Trường hợp | Cách xử lý |
|---|---|
| Future được tạo riêng cho một subscription | Cho phép cancellation truyền xuống nếu API hỗ trợ |
| Future được chia sẻ giữa nhiều subscriber | Không để một subscriber hủy công việc của tất cả bên còn lại |
| Future được quản lý bởi component bên ngoài | Thống nhất rõ ai có quyền cancel |
| Future đại diện một side effect đã gửi đến server | Xem cancellation là ngừng chờ; không giả định rollback |
| Future chỉ là phép tính có thể dừng an toàn | Có thể truyền cancellation và kiểm tra trạng thái dừng |

Ví dụ future được chia sẻ:

    CompletableFuture<Configuration> sharedLoad =
        configurationClient.loadOnce();

    Mono<Configuration> configuration =
        Mono.fromFuture(sharedLoad, true);

Ở overload này, tham số true yêu cầu adapter bỏ qua việc hủy future bên dưới khi Mono bị cancel. Điều đó tránh để một subscriber làm hỏng công việc mà các subscriber khác còn cần. Đổi lại, công việc có thể tiếp tục dù subscriber hiện tại đã hủy; component sở hữu future phải chịu trách nhiệm vòng đời của nó.

Nếu cần một thao tác riêng cho từng subscriber, không dùng future chia sẻ. Tạo future bên trong defer và để subscription sở hữu thao tác đó.

## 6. Kết hợp CompletionStage với các operator Reactor

Sau khi chuyển stage thành Mono, có thể kết hợp nó với các nguồn reactive khác bằng operator:

    Mono<Order> order =
        orderRepository.findById(orderId);

    Mono<Customer> customer =
        Mono.defer(() ->
            Mono.fromCompletionStage(
                customerClient.fetchAsync(customerId)
            )
        );

    Mono<OrderView> view =
        order.zipWith(customer, OrderView::new);

zipWith chờ cả hai Mono có giá trị rồi kết hợp. Nếu một nguồn empty, kết quả zip cũng có thể empty; nếu một nguồn lỗi, lỗi được truyền theo semantics của operator.

Có thể dùng flatMap khi kết quả stage phụ thuộc vào phần tử của publisher:

    Flux<EnrichedOrder> enriched =
        orders.flatMap(order ->
            Mono.fromCompletionStage(
                customerClient.fetchAsync(order.customerId())
            )
            .map(customer ->
                new EnrichedOrder(order, customer)
            ),
            16
        );

Tham số concurrency giới hạn số thao tác customer đang được thực hiện đồng thời qua inner publisher. Nếu mỗi lời gọi tạo future ngay trong mapper, thao tác tương ứng bắt đầu khi mapper được gọi. Giới hạn concurrency của flatMap giúp giới hạn số inner publisher được xử lý đồng thời; không nên tạo future trước ở một nơi khác rồi mới đưa chúng vào pipeline nếu muốn giới hạn thời điểm bắt đầu.

## 7. Tích hợp publisher từ thư viện Reactive Streams khác

Nhiều thư viện Java cung cấp kiểu org.reactivestreams.Publisher<T>. Vì Flux và Mono cũng triển khai giao diện này, có thể chuyển đổi bằng các factory:

    org.reactivestreams.Publisher<Message> external =
        messagingClient.receive();

    Flux<Message> messages = Flux.from(external);

Nếu chỉ cần tối đa một phần tử:

    Mono<Message> firstMessage = Mono.from(external);

Flux.from giữ chuỗi phần tử của publisher. Mono.from biểu diễn tối đa một phần tử; nó phù hợp khi chỉ cần phần tử đầu tiên và chấp nhận việc dừng subscription sau đó. Nếu cần xử lý toàn bộ chuỗi, không dùng Mono.from vì các phần tử còn lại không thuộc kết quả Mono.

Nếu thư viện trả về kiểu riêng nhưng có adapter Reactive Streams, ưu tiên adapter chính thức của thư viện. Ví dụ, các hệ sinh thái như RxJava, Akka/Pekko hoặc thư viện messaging có thể cung cấp cầu nối riêng. Adapter chính thức thường hiểu rõ hơn cách chuyển backpressure, scheduler, lỗi và cancellation so với việc tự viết một hàng đợi callback.

Khi dùng RxJava, cần phân biệt kiểu hỗ trợ backpressure như Flowable với kiểu không có backpressure như Observable. Chuyển một Observable thành Flux không tự tạo ra khả năng tạm dừng nguồn; cần chọn chính sách buffer, drop hoặc giới hạn ở adapter tương ứng.

## 8. Tích hợp callback API bằng create và push

Không phải thư viện nào cũng trả Publisher hoặc CompletionStage. Một API cũ có thể nhận callback khi có dữ liệu. Reactor cung cấp Flux.create, Flux.push và Mono.create để chuyển callback thành publisher.

Ví dụ API callback chỉ trả một kết quả:

    Mono<Profile> profile =
        Mono.create(sink ->
            legacyClient.fetchProfile(
                userId,
                sink::success,
                sink::error
            )
        );

Với callback có thể phát nhiều sự kiện:

    import reactor.core.publisher.FluxSink;

    Flux<Event> events =
        Flux.create(sink -> {
            Listener listener = sink::next;
            legacyClient.addListener(listener);

            sink.onDispose(() ->
                legacyClient.removeListener(listener)
            );
        }, FluxSink.OverflowStrategy.ERROR);

Đoạn mã minh họa việc đăng ký listener khi có subscriber và tháo listener khi subscription bị dispose. Trong thực tế, cần bảo đảm listener có kiểu callback tương thích, xử lý lỗi từ API, và không gọi next sau khi sink đã kết thúc.

Flux.create phù hợp khi callback có thể được gọi từ nhiều thread hoặc có thể phát nhiều phần tử theo cơ chế push. Flux.push phù hợp hơn khi nguồn phát tuần tự từ một thread. Nếu không chỉ định chiến lược, Flux.create mặc định buffer tín hiệu đang chờ; với nguồn không thể tạm dừng, buffer không giới hạn có thể làm tăng bộ nhớ liên tục. Ví dụ dùng OverflowStrategy.ERROR để biến tình trạng vượt khả năng tiếp nhận thành lỗi có thể quan sát và xử lý.

Không giữ listener toàn cục cho tất cả subscriber nếu mỗi subscription cần vòng đời riêng. Nếu listener được chia sẻ, hãy dùng một cơ chế chia sẻ có chủ đích và quản lý việc đăng ký/hủy theo số subscriber.

## 9. Scheduler và ranh giới thread

Adapter không tự động làm mọi callback chạy trên scheduler mong muốn. Một CompletionStage có thể hoàn tất trên thread của HTTP client, ForkJoinPool hoặc executor do thư viện chọn. Khi pipeline cần chuyển sang scheduler khác, dùng publishOn hoặc subscribeOn đúng vị trí.

Ví dụ:

    Mono<Result> result =
        Mono.fromCompletionStage(client.calculateAsync(input))
            .publishOn(Schedulers.parallel())
            .map(this::cpuIntensiveTransform);

publishOn chuyển việc xử lý các tín hiệu downstream phía sau nó sang scheduler đã chọn. Nó không nhất thiết thay đổi executor mà CompletionStage dùng để hoàn tất công việc.

Nếu gọi API blocking, hãy đưa lời gọi đó lên boundedElastic:

    Mono<Document> document =
        Mono.fromCallable(
            () -> legacyClient.loadDocument(documentId)
        )
        .subscribeOn(Schedulers.boundedElastic());

Không dùng publishOn sau một lời gọi blocking đã chạy trên event loop để giả định lời gọi blocking được chuyển đi; phải đặt subscribeOn quanh nguồn blocking để thay đổi nơi supplier được thực thi.

## 10. Context không tự động vượt qua mọi adapter

Reactor Context gắn với subscription và được các operator Reactor truy cập bằng deferContextual hoặc transformDeferredContextual. Một thư viện bên ngoài hoặc callback trên thread riêng không mặc nhiên biết Context đó.

Ví dụ lấy correlation ID trước khi gọi CompletionStage:

    Mono<Response> response =
        Mono.deferContextual(context -> {
            String correlationId =
                context.get("correlationId");

            return Mono.fromCompletionStage(
                remoteClient.callAsync(
                    request,
                    correlationId
                )
            );
        });

    response.contextWrite(context ->
        context.put("correlationId", "req-42")
    );

Cần truyền metadata tường minh vào API bên ngoài nếu API đó cần dùng trong callback hoặc request. Không giả định ThreadLocal, MDC hoặc Reactor Context sẽ tự động xuất hiện trên thread do thư viện khác quản lý.

Nếu ứng dụng dùng cơ chế context propagation của Reactor và thư viện tích hợp tương ứng, hãy cấu hình theo hướng dẫn của phiên bản đang dùng. Dù có propagation, vẫn nên phân biệt metadata gắn với subscription với trạng thái toàn cục của thread.

## 11. Backpressure qua ranh giới tích hợp

Khi cả hai phía hỗ trợ Reactive Streams hoặc Java Flow, adapter có thể chuyển tiếp nhu cầu giữa các subscription. Nhưng khi nối với CompletionStage hoặc callback API, không có nhu cầu từng phần tử để truyền xuống.

| Ranh giới | Hành vi điều tiết |
|---|---|
| Reactor ↔ Java Flow | Có thể chuyển tiếp request/cancel qua adapter |
| Reactor ↔ Reactive Streams Publisher | Dùng trực tiếp hợp đồng Publisher/Subscriber |
| Reactor ↔ CompletionStage | Một kết quả; không có request(n) |
| Reactor ↔ Callback push API | Cần buffer, drop, latest hoặc cơ chế pause riêng |
| Reactor ↔ API blocking | Điều tiết số tác vụ đồng thời và thread thực thi |

Một Mono bọc future chỉ có một kết quả nên không cần backpressure theo số phần tử. Nhưng nếu hàng nghìn future được tạo đồng thời, ứng dụng vẫn có thể cạn connection, thread hoặc bộ nhớ. Hãy giới hạn concurrency ở nơi tạo thao tác, dùng rate limiter hoặc semaphore phù hợp và áp dụng timeout theo deadline nghiệp vụ.

Với callback stream không thể tạm dừng, Flux.create có thể dùng overflow strategy. Chọn chính sách dựa trên ý nghĩa dữ liệu:

- Buffer nếu cần giữ dữ liệu trong tải đột biến và có giới hạn rõ.
- Drop nếu một số sự kiện có thể bỏ.
- Latest nếu chỉ cần trạng thái mới nhất.
- Error nếu overflow biểu thị vi phạm giới hạn cần xử lý.

## 12. Lỗi và cancellation khi kết hợp nhiều mô hình

Khi kết nối các API, hãy xác định cách mỗi loại lỗi đi vào pipeline:

- CompletionStage exceptional completion trở thành onError.
- Publisher Reactive Streams hoặc Flow phát onError.
- Callback API cần gọi nhánh error của sink.
- Exception đồng bộ khi tạo publisher cần được chuyển thành tín hiệu lỗi bằng defer, fromCallable hoặc factory phù hợp.

Ví dụ bắt cả lỗi đồng bộ khi tạo stage và lỗi bất đồng bộ khi stage hoàn tất:

    Mono<User> user =
        Mono.defer(() ->
            Mono.fromCompletionStage(
                userClient.fetchAsync(userId)
            )
        )
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(
            UserServiceUnavailable.class,
            error -> userCache.find(userId)
        );

defer đưa lỗi phát sinh đồng bộ từ fetchAsync vào trong quá trình subscribe của Reactor. timeout giới hạn thời gian chờ tín hiệu và hủy upstream khi hết hạn. Việc thao tác từ xa thực sự dừng vẫn phụ thuộc client và server hỗ trợ cancellation đến đâu.

Không chuyển mọi exception thành empty bằng onErrorComplete nếu tầng gọi cần phân biệt “không có dữ liệu” với “dịch vụ thất bại”. Giữ nguyên hoặc ánh xạ lỗi theo hợp đồng nghiệp vụ.

## 13. Ví dụ tổng hợp: dùng CompletionStage trong pipeline Reactor

Giả sử một hệ thống đọc đơn hàng bằng Reactor, gọi dịch vụ hồ sơ khách hàng trả về CompletionStage, rồi lưu kết quả qua reactive repository:

    record Order(String id, String customerId) {}
    record Customer(String id, String name) {}
    record OrderView(Order order, Customer customer) {}

    Flux<OrderView> orderViews =
        orderRepository.findRecentOrders()
            .flatMap(order ->
                Mono.defer(() ->
                    Mono.fromCompletionStage(
                        customerClient.fetchAsync(
                            order.customerId()
                        )
                    )
                )
                .map(customer ->
                    new OrderView(order, customer)
                )
                .timeout(Duration.ofSeconds(2))
                .onErrorResume(
                    CustomerUnavailableException.class,
                    error -> customerCache.find(order.customerId())
                        .map(customer ->
                            new OrderView(order, customer)
                        )
                ),
                12
            );

Trong pipeline này:

1. Repository phát đơn hàng theo kiểu Flux.
2. flatMap tạo một inner Mono cho từng đơn hàng và giới hạn tối đa 12 thao tác đồng thời.
3. defer tạo CompletionStage khi inner Mono được subscribe.
4. Stage được chuyển thành Mono để có thể dùng map, timeout và onErrorResume.
5. Nếu dịch vụ hồ sơ gặp lỗi thuộc loại được phép fallback, cache cung cấp kết quả thay thế.
6. Các lỗi khác tiếp tục truyền xuống downstream.

Ví dụ giả định repository và cache đều trả publisher Reactor, còn fetchAsync trả CompletionStage. Trong production cần xác định timeout phù hợp, loại lỗi có thể fallback, hành vi cancellation của HTTP client và tính nhất quán dữ liệu giữa cache với dịch vụ chính.

## 14. Kiểm thử adapter và hợp đồng tích hợp

Nên kiểm thử hành vi quan sát được ở hai phía của adapter:

- Giá trị thành công được chuyển đúng kiểu.
- CompletionStage lỗi được chuyển thành onError.
- Empty Mono được chuyển thành null khi dùng toFuture, hoặc thành Optional nếu đã ánh xạ.
- Cancellation có truyền xuống nguồn theo cấu hình không.
- Callback listener được tháo khi subscription bị hủy.
- Backpressure hoặc overflow được xử lý theo chính sách đã chọn.

Ví dụ kiểm thử CompletionStage thành công:

    CompletableFuture<String> future =
        CompletableFuture.completedFuture("ready");

    StepVerifier.create(Mono.fromFuture(future))
        .expectNext("ready")
        .verifyComplete();

Kiểm thử lỗi:

    CompletableFuture<String> failed =
        new CompletableFuture<>();
    failed.completeExceptionally(
        new IllegalStateException("remote failed")
    );

    StepVerifier.create(Mono.fromFuture(failed))
        .expectError(IllegalStateException.class)
        .verify();

Kiểm thử Java Flow nên dùng publisher kiểm thử hoặc publisher mẫu có thể ghi nhận request và cancel. Xác nhận số phần tử được yêu cầu, tín hiệu terminal và cancellation ở đúng ranh giới. Với callback API, dùng cờ hoặc mock để xác nhận đăng ký listener một lần và tháo listener khi cancel.

## 15. Checklist trước khi tích hợp thư viện khác

Trước khi nối một API ngoài vào Reactor, hãy xác định:

1. API trả một giá trị, một chuỗi phần tử hay callback nhiều lần?
2. Kiểu của nó là Flow Publisher, Reactive Streams Publisher, CompletionStage hay callback riêng?
3. Có adapter chính thức và dependency tương ứng không?
4. Công việc bắt đầu khi gọi API hay khi subscribe?
5. Cancellation có truyền xuống nguồn không, và nguồn có thực sự dừng được không?
6. Lỗi đồng bộ và lỗi bất đồng bộ được chuyển thành onError như thế nào?
7. Backpressure được hỗ trợ, bị mất hay phải thay bằng buffer/drop/latest?
8. Callback và future hoàn tất trên thread nào; có cần chuyển scheduler không?
9. Context, correlation ID và security metadata có được truyền tường minh không?
10. Ai sở hữu tài nguyên và subscription khi caller hủy hoặc ứng dụng shutdown?
11. Kiểm thử đã xác nhận thành công, lỗi, empty, cancellation và overflow chưa?

Kết nối Reactor với Java Flow, CompletionStage và thư viện khác cho phép một ứng dụng dùng chung một pipeline xử lý mà vẫn tận dụng các API hiện có. Để tích hợp an toàn, cần giữ rõ khác biệt giữa stream có backpressure và kết quả đơn, giữa cancellation của subscription và việc dừng tác vụ bên ngoài, cũng như giữa assembly và thời điểm công việc thực sự bắt đầu. Adapter đúng kết hợp với chính sách về lỗi, scheduler, context và quyền sở hữu sẽ giúp các ranh giới bất đồng bộ dễ kiểm soát và kiểm thử hơn.
