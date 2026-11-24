# Ranh giới giao dịch gắn với đăng ký và ngữ cảnh

Trong ứng dụng reactive, việc gọi một phương thức trả về Mono hoặc Flux thường chỉ tạo ra mô tả công việc. Công việc thực sự bắt đầu khi có subscriber đăng ký. Vì vậy, ranh giới giao dịch phải gắn với vòng đời của Publisher được tiêu thụ: giao dịch được mở khi pipeline được subscribe, giữ hiệu lực trong quá trình xử lý và kết thúc theo tín hiệu mà transaction boundary quan sát được.

Một giao dịch reactive còn cần mang theo ngữ cảnh qua các bước bất đồng bộ. Reactor không dựa vào việc mọi thao tác luôn chạy trên cùng một thread; một pipeline có thể chuyển scheduler nhưng vẫn phải sử dụng đúng connection và transaction. Spring quản lý điều này bằng Reactor Context và các reactive transaction manager. Hiểu mối liên hệ giữa đăng ký, context và transaction giúp tránh những lỗi như query chạy ngoài giao dịch, commit quá sớm, rollback không như mong đợi hoặc giữ connection quá lâu.

Bài học thuộc chương **Dữ liệu và giao dịch** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; nội dung dưới đây áp dụng Mono, Flux, toán tử, scheduler, xử lý lỗi và kiểm thử pipeline Java vào việc xác định ranh giới giao dịch.

Các ví dụ sử dụng Project Reactor và Spring reactive transaction support, đặc biệt với R2DBC. Những tên như orderRepository, inventoryRepository và Order đại diện cho thành phần của ứng dụng; hãy bổ sung import, kiểu miền và cấu hình tương ứng khi áp dụng vào dự án.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao tạo Publisher chưa mở giao dịch và subscription mới kích hoạt công việc.
- Gắn một chuỗi thao tác database vào cùng ranh giới bằng TransactionalOperator hoặc @Transactional.
- Mô tả vai trò của Reactor Context trong việc truyền transaction qua các bước bất đồng bộ và đổi scheduler.
- Phân biệt complete, error và cancel tại ranh giới giao dịch.
- Dự đoán ảnh hưởng của retry, fallback, take, share và nhiều subscription đến transaction.
- Giữ giao dịch ngắn, quản lý connection đúng cách và tránh trộn I/O ngoài database vào một transaction không cần thiết.
- Kiểm thử commit, rollback và cancellation bằng StepVerifier cùng database tích hợp.

## 1. Publisher được tạo trước, giao dịch bắt đầu khi subscribe

Mono và Flux thường là lazy. Khi gọi một phương thức repository, ứng dụng nhận về một Publisher mô tả thao tác cần thực hiện. Nếu chưa có subscription, thao tác reactive thường chưa chạy:

~~~java
Mono<Order> pending =
    orderRepository.findById(orderId);
~~~

Dòng mã trên tạo Publisher. Với reactive repository chuẩn của Spring Data, truy vấn được thực thi khi Publisher được subscribe. Khi đặt Publisher trong một ranh giới giao dịch reactive, transaction manager cũng bắt đầu công việc theo subscription đó.

~~~java
Mono<Order> transactionalOrder =
    transactionalOperator.transactional(
        orderRepository.findById(orderId)
    );
~~~

TransactionalOperator bọc Publisher và điều phối transaction khi có subscriber. Khi Publisher kết thúc, transaction manager quyết định commit hoặc rollback dựa trên kết quả và tín hiệu kết thúc.

Điều này khác với một transaction imperative thường được mở ngay trong lúc phương thức được gọi và gắn với thread hiện tại. Trong reactive code, phương thức có thể trả Publisher trước khi database operation bắt đầu; subscriber có thể đăng ký sau đó, trên một thread khác.

### Mỗi subscription có vòng đời giao dịch riêng

Một Publisher lạnh được bọc bằng transactional thường tạo một transaction cho mỗi subscription:

~~~java
Mono<Order> order =
    transactionalOperator.transactional(
        orderRepository.findById(orderId)
    );

order.subscribe();
order.subscribe();
~~~

Hai subscription độc lập có thể thực hiện hai lần truy vấn và có hai transaction riêng. Nếu nghiệp vụ yêu cầu chỉ thực hiện một lần, cần thiết kế chia sẻ kết quả ở tầng phù hợp; không nên vô tình subscribe nhiều lần chỉ để lấy cùng một kết quả.

Cũng cần thận trọng với share hoặc cache. Chúng thay đổi số subscription upstream và có thể khiến nhiều subscriber quan sát cùng một lần thực thi. Transaction khi đó gắn với subscription upstream được chia sẻ, không còn là một transaction độc lập cho từng subscriber phía sau. Hãy xác định rõ liệu muốn mỗi người tiêu thụ có một giao dịch riêng hay muốn một lần thực thi được chia sẻ.

## 2. TransactionalOperator: xác định ranh giới bằng Publisher

TransactionalOperator là cách tường minh để bọc một Publisher bằng reactive transaction. Nó thường được tạo từ một ReactiveTransactionManager:

~~~java
@Bean
ReactiveTransactionManager transactionManager(
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}

@Bean
TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
~~~

Ví dụ sử dụng R2dbcTransactionManager. Transaction manager và các repository/DatabaseClient tham gia giao dịch cần dùng cùng ConnectionFactory để Spring có thể gắn connection đang giao dịch vào Reactor Context.

### Gộp nhiều thao tác vào một giao dịch

Giả sử tạo đơn hàng cần lưu đơn và trừ tồn kho. Cả hai thao tác phải thành công hoặc cùng rollback:

~~~java
Mono<Order> createOrder(CreateOrder command) {
    Mono<Order> work =
        orderRepository.insert(command.toOrder())
            .flatMap(saved ->
                inventoryRepository.decrease(
                    saved.productId(),
                    saved.quantity()
                ).thenReturn(saved)
            );

    return transactionalOperator.transactional(work);
}
~~~

Pipeline có hai bước database nối tiếp:

1. insert tạo đơn hàng và phát đối tượng đã lưu.
2. decrease cập nhật tồn kho; thenReturn chỉ phát đơn hàng sau khi thao tác cập nhật hoàn tất.

TransactionalOperator bọc toàn bộ chuỗi. Nếu insert thành công nhưng decrease phát lỗi, transaction manager rollback cả thay đổi insert, với điều kiện cả hai repository tham gia cùng transaction manager và cùng cơ chế connection reactive.

Không gọi subscribe bên trong createOrder. Phương thức nên trả Publisher để tầng gọi quyết định lúc đăng ký. Nếu tự subscribe bên trong, thao tác có thể chạy ngoài transaction boundary mà caller đang mong đợi, lỗi không truyền về đúng subscriber và cancellation của request không còn điều khiển được công việc đó.

### Dùng execute khi cần TransactionStatus

TransactionalOperator cũng có thể nhận callback thông qua execute:

~~~java
Flux<Order> createdOrders =
    transactionalOperator.execute(status ->
        orderRepository.insertAll(commands)
            .concatMap(saved ->
                inventoryRepository.decrease(
                    saved.productId(),
                    saved.quantity()
                ).thenReturn(saved)
            )
    );
~~~

Callback trả về Publisher. Toàn bộ Publisher được trả về từ callback thuộc transaction được tạo bởi operator. TransactionStatus có thể dùng cho các thao tác điều khiển transaction được hỗ trợ, nhưng không nên đánh dấu rollback-only tùy tiện nếu chưa hiểu propagation và cách transaction manager xử lý.

execute trả về Flux<T>, kể cả khi callback chỉ phát một phần tử hoặc không phát phần tử. Nếu API bên ngoài cần Mono, có thể dùng singleOrEmpty hoặc các toán tử tương ứng, nhưng phải xác định rõ trường hợp có nhiều kết quả.

## 3. Reactor Context mang transaction qua các bước bất đồng bộ

Một transaction reactive không thể dựa vào ThreadLocal như cách quản lý transaction imperative truyền thống. Pipeline có thể bắt đầu trên một thread, chuyển sang scheduler khác rồi tiếp tục truy vấn database. Thread hiện tại thay đổi nhưng transaction vẫn phải được nhận diện đúng.

Spring reactive transaction support gắn tài nguyên và transaction state vào Reactor Context của subscriber. Khi các toán tử Reactor chuyển tín hiệu qua pipeline, context được truyền theo subscription, không phụ thuộc vào thread cụ thể.

~~~java
Mono<Order> order =
    transactionalOperator.transactional(
        orderRepository.findById(orderId)
            .publishOn(Schedulers.parallel())
            .flatMap(saved ->
                orderRepository.findById(saved.id())
            )
    );
~~~

Ví dụ minh họa rằng publishOn có thể chuyển phần xử lý phía sau sang scheduler khác mà transaction context vẫn được giữ. Tuy nhiên, truy vấn database thường không cần chuyển sang parallel chỉ để tiếp tục reactive I/O; hãy để driver điều phối I/O không chặn và chỉ chuyển scheduler khi có công việc CPU hoặc blocking thực sự cần cô lập.

### Context khác ThreadLocal

| Đặc điểm | ThreadLocal | Reactor Context |
|---|---|---|
| Phạm vi | Thread hiện tại | Subscription |
| Khi đổi scheduler | Giá trị không tự đi theo thread mới | Context đi cùng reactive chain |
| Phù hợp | Một số API imperative gắn với thread | Metadata và tài nguyên gắn với subscriber |
| Transaction reactive của Spring | Không phải cơ chế nền tảng | Dùng để gắn tài nguyên giao dịch |

Không nên tự lưu transaction connection vào ThreadLocal rồi truy cập từ các callback reactive. Cũng không nên lấy connection mới trực tiếp từ ConnectionFactory ở giữa một giao dịch Spring-managed; thao tác đó có thể không dùng connection đã được gắn vào transaction context.

Dùng DatabaseClient, Spring Data R2DBC hoặc ConnectionFactoryUtils theo đúng cơ chế quản lý của Spring để các thao tác tham gia cùng transaction.

### ContextWrite không tự mở transaction

Reactor Context có thể mang metadata ứng dụng:

~~~java
Mono<Order> order =
    orderRepository.findById(orderId)
        .contextWrite(context ->
            context.put("requestId", requestId)
        );
~~~

contextWrite cập nhật context của subscription. Nó không tự tạo transaction. Transaction chỉ được mở khi Publisher được bọc bởi transaction manager hoặc được thực thi trong reactive method có @Transactional phù hợp.

Khi kết hợp metadata và transaction, để transaction manager quản lý các khóa context nội bộ của nó. Không tự ghi đè hoặc xóa các khóa không thuộc ứng dụng.

## 4. @Transactional trên phương thức trả Mono hoặc Flux

Spring hỗ trợ @Transactional cho phương thức trả về reactive Publisher khi có ReactiveTransactionManager phù hợp. Ví dụ:

~~~java
@Service
class OrderService {
    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    @Transactional
    public Mono<Order> createOrder(CreateOrder command) {
        return orderRepository.insert(command.toOrder())
            .flatMap(saved ->
                inventoryRepository.decrease(
                    saved.productId(),
                    saved.quantity()
                ).thenReturn(saved)
            );
    }
}
~~~

Khi phương thức được gọi qua Spring proxy, transaction boundary được áp dụng cho Publisher trả về. Với reactive return type, việc thực thi transaction gắn với subscription và tín hiệu kết thúc của Publisher.

Một số điều kiện cần giữ:

- Phương thức phải được gọi qua cơ chế proxy hoặc interception của Spring đang được cấu hình. Self-invocation trong cùng bean có thể bỏ qua proxy và do đó không áp dụng transaction annotation như mong đợi.
- Phải cấu hình ReactiveTransactionManager, ví dụ R2dbcTransactionManager cho R2DBC.
- Các thao tác tham gia cùng giao dịch cần dùng hạ tầng reactive và ConnectionFactory tương ứng.
- Không gọi block hoặc subscribe bên trong phương thức transactional.
- Không trộn một imperative transaction manager với reactive Publisher rồi giả định transaction context tự truyền qua hai mô hình.

Dùng @Transactional khi ranh giới giao dịch gắn tự nhiên với một service method. Dùng TransactionalOperator khi cần nhìn rõ ranh giới trong pipeline, bọc một đoạn Publisher cụ thể hoặc tạo transaction ở vị trí linh hoạt hơn.

## 5. Complete, error và cancel tại transaction boundary

Transaction manager cần biết Publisher kết thúc như thế nào để quyết định trạng thái giao dịch. Ba đường kết thúc chính có ý nghĩa khác nhau:

| Tín hiệu tại ranh giới | Hành vi giao dịch thường mong đợi |
|---|---|
| Complete bình thường | Commit |
| Error | Rollback |
| Subscriber cancel | Rollback và giải phóng tài nguyên |

Hành vi chi tiết còn phụ thuộc transaction manager, cấu hình rollback rules và cách toán tử phía trong chuyển tín hiệu. Vì vậy, hãy kiểm thử với driver và manager thực tế, đặc biệt đối với cancellation.

### Error phải đến được transaction boundary

Nếu một thao tác database phát lỗi và lỗi đi xuyên qua TransactionalOperator, transaction manager có thể rollback:

~~~java
Mono<Order> result =
    transactionalOperator.transactional(
        orderRepository.insert(order)
            .flatMap(saved ->
                inventoryRepository.decrease(
                    saved.productId(),
                    saved.quantity()
                ).thenReturn(saved)
            )
    );
~~~

Nếu decrease lỗi, lỗi truyền ra ngoài operator sau khi transaction được rollback. Caller có thể xử lý lỗi ở bên ngoài transaction boundary.

### Vị trí onErrorResume làm thay đổi kết quả giao dịch

Hai pipeline sau không tương đương:

~~~java
Mono<Order> handledInside =
    transactionalOperator.transactional(
        orderRepository.insert(order)
            .flatMap(saved -> failIfInventoryUnavailable(saved))
            .onErrorResume(error -> Mono.just(order))
    );

Mono<Order> handledOutside =
    transactionalOperator.transactional(
        orderRepository.insert(order)
            .flatMap(saved -> failIfInventoryUnavailable(saved))
    ).onErrorResume(error -> Mono.just(order));
~~~

Ở handledInside, onErrorResume chuyển lỗi thành một kết quả bình thường trước khi lỗi đến transaction boundary. Transaction manager có thể nhìn thấy complete và commit những thay đổi đã thực hiện, trừ khi transaction đã bị đánh dấu rollback-only hoặc database đã làm transaction thất bại.

Ở handledOutside, lỗi đi qua TransactionalOperator trước. Operator có cơ hội rollback; sau đó fallback mới tạo kết quả thay thế cho caller.

Nếu fallback chỉ nhằm trả thông báo lỗi thân thiện, hãy đặt nó ngoài transaction boundary để lỗi nghiệp vụ vẫn kích hoạt rollback. Nếu chủ ý xử lý lỗi bên trong transaction và tiếp tục, phải quyết định rõ trạng thái rollback-only và tính hợp lệ của các thay đổi đã thực hiện.

### Cancellation và toán tử take

Cancellation của subscriber ở bên ngoài TransactionalOperator khiến operator nhận cancel và thực hiện cleanup/rollback theo transaction manager. Nhưng không phải mọi cancellation upstream đều đồng nghĩa transaction boundary nhận cancel.

Ví dụ:

~~~java
Mono<List<Order>> firstOrders =
    transactionalOperator.transactional(
        orderRepository.findAll()
            .take(10)
            .collectList()
    );
~~~

take(10) hủy subscription upstream sau mười phần tử, nhưng chính toán tử take phát complete xuống collectList. TransactionalOperator có thể quan sát complete bình thường và commit phần công việc đã hoàn thành. Đây có thể là hành vi đúng nếu nghiệp vụ chủ ý xử lý mười đơn đầu; nó không phải rollback chỉ vì take đã hủy upstream.

Ngược lại, nếu subscriber cuối hủy subscription của Publisher được bọc bởi TransactionalOperator, transaction boundary nhận cancel. Hãy phân biệt cancellation nội bộ do một toán tử kết thúc sớm với cancellation của subscriber ở ngoài ranh giới.

## 6. Retry phải đặt đúng phía transaction boundary

Retry đăng ký lại Publisher. Vị trí retry quyết định mỗi lần thử có transaction mới hay chạy lại trong cùng transaction.

~~~java
Mono<Order> retryWithNewTransaction =
    transactionalOperator.transactional(
        createOrderWork(command)
    ).retryWhen(
        Retry.max(2)
            .filter(this::isTransientFailure)
    );
~~~

retryWhen nằm ngoài TransactionalOperator. Khi một lần thử lỗi, transaction boundary kết thúc lần đó; retry đăng ký lại Publisher được bọc và tạo một lần thực thi giao dịch mới. Đây thường là lựa chọn phù hợp cho lỗi tạm thời ở database, với điều kiện thao tác có tính idempotent hoặc được bảo vệ khỏi ghi trùng.

~~~java
Mono<Order> retryInsideTransaction =
    transactionalOperator.transactional(
        createOrderWork(command)
            .retryWhen(
                Retry.max(2)
                    .filter(this::isTransientFailure)
            )
    );
~~~

Ở cách thứ hai, retry nằm trong transaction. Nếu lỗi database đã làm transaction bị đánh dấu rollback-only hoặc khiến connection không còn dùng được, thử lại bên trong cùng transaction có thể không thành công và transaction cuối cùng vẫn rollback.

Không phải mọi lỗi đều nên retry. Chỉ retry lỗi tạm thời được xác định rõ, giới hạn số lần và cân nhắc backoff. Với thao tác ghi, dùng idempotency key, unique constraint hoặc một cơ chế đối soát để lần thử lại không tạo giao dịch trùng.

## 7. Ranh giới giao dịch không nên kéo dài theo luồng vô hạn

Một transaction thường giữ connection, snapshot hoặc lock trong suốt vòng đời. Nếu bọc một Flux dài hạn hoặc nguồn không hoàn tất, transaction có thể giữ tài nguyên rất lâu:

~~~java
Flux<Event> events =
    transactionalOperator.transactional(
        eventRepository.streamAllChanges()
    );
~~~

Nếu stream không hoàn tất, transaction có thể không commit và connection vẫn bị giữ. Với nguồn vô hạn, đây thường là ranh giới không phù hợp.

Nếu cần tổng hợp hoặc ghi dữ liệu theo batch, hãy tạo transaction riêng cho từng batch hữu hạn:

~~~java
Flux<WriteResult> writes =
    eventSource
        .bufferTimeout(200, Duration.ofSeconds(1))
        .concatMap(batch ->
            transactionalOperator.transactional(
                repository.saveBatch(batch)
            )
        );
~~~

Mỗi batch có một transaction riêng. Khi batch được lưu thành công, transaction commit rồi pipeline xử lý batch tiếp theo. Nếu một batch lỗi, transaction của batch đó rollback; chính sách tiếp tục hay dừng cần được quyết định ở tầng ứng dụng.

Thiết kế theo batch không tạo tính nguyên tử cho toàn bộ nguồn. Nếu batch thứ ba lỗi sau khi hai batch đầu đã commit, hai batch trước vẫn tồn tại. Hãy chọn phạm vi giao dịch theo yêu cầu nghiệp vụ: toàn bộ một thao tác nhỏ, một batch, một đơn hàng hoặc một phiên hữu hạn.

## 8. Không trộn thao tác ngoài database vào kỳ vọng atomic

Một transaction database chỉ kiểm soát tài nguyên tham gia cùng transaction manager. Nó không tự rollback một email đã gửi, một HTTP request đã thành công hoặc một message đã được publish ra broker ngoài transaction.

Ví dụ:

~~~java
Mono<Order> unsafeWorkflow =
    transactionalOperator.transactional(
        orderRepository.insert(order)
            .flatMap(saved ->
                emailClient.sendConfirmation(saved)
                    .thenReturn(saved)
            )
    );
~~~

Nếu email gửi thành công nhưng thao tác database sau đó lỗi, database có thể rollback trong khi email không thể thu hồi. Transaction không biến hai hệ thống độc lập thành một giao dịch phân tán.

Với sự kiện cần phát cùng thay đổi database, cân nhắc transactional outbox:

1. Trong cùng database transaction, ghi đơn hàng và một outbox record.
2. Commit cả hai thay đổi.
3. Một worker riêng đọc outbox và gửi message/email.
4. Đánh dấu outbox record đã xử lý theo cơ chế idempotent.
5. Retry gửi khi broker hoặc dịch vụ đích tạm thời lỗi.

Cách này không làm message delivery trở thành exactly-once tuyệt đối; nó tạo một luồng có thể retry và đối soát, thường đạt at-least-once với consumer idempotent.

Cũng nên tránh gọi một API HTTP chậm bên trong transaction nếu không cần. Transaction kéo dài làm connection bị giữ trong lúc chờ mạng và có thể tăng lock duration. Chỉ giữ trong transaction các thao tác cần cùng tính nguyên tử ở tầng database.

## 9. Nhiều thao tác đồng thời trong cùng transaction

flatMap cho phép nhiều Publisher con hoạt động đồng thời. Điều đó không tự bảo đảm driver database có thể thực hiện các thao tác đồng thời trên cùng connection hoặc transaction.

~~~java
Mono<Void> work =
    Flux.fromIterable(commands)
        .flatMap(repository::save, 8)
        .then();
~~~

Nếu tất cả lệnh cần cùng một transaction và repository dùng cùng connection được bind trong Reactor Context, việc chạy đồng thời có thể không phù hợp với khả năng của driver hoặc có thể tạo thứ tự cập nhật khó dự đoán.

Khi các thao tác phụ thuộc nhau hoặc cần thứ tự rõ, dùng concatMap:

~~~java
Mono<Void> work =
    Flux.fromIterable(commands)
        .concatMap(repository::save)
        .then();
~~~

concatMap đăng ký và chờ từng Publisher con theo thứ tự. Điều này thường dễ reasoning hơn cho các thao tác ghi cùng một transaction.

Nếu muốn song song hóa, hãy kiểm tra driver, transaction manager và yêu cầu isolation. Có thể tách các công việc độc lập thành transaction riêng, nhưng khi đó không còn một transaction atomic duy nhất cho toàn bộ nhóm. Đừng tăng concurrency chỉ dựa trên việc các API đều trả Mono.

## 10. Isolation, propagation và connection ownership

Reactive transaction vẫn tuân theo các khái niệm transaction quen thuộc như isolation, propagation, timeout và rollback rules, nhưng việc truyền ngữ cảnh được thực hiện qua Reactor Context.

Một số điểm cần phân biệt:

- **Isolation:** quyết định mức độ nhìn thấy thay đổi đồng thời theo khả năng database và driver.
- **Propagation:** quyết định cách một thao tác tham gia transaction hiện tại, tạo transaction mới hoặc xử lý khi không có transaction.
- **Timeout:** giới hạn thời gian transaction được phép tồn tại theo cấu hình manager.
- **Rollback rules:** quyết định lỗi nào làm transaction rollback trong mô hình annotation/configuration.
- **Connection ownership:** connection thuộc transaction manager trong phạm vi giao dịch; ứng dụng không tự đóng connection đó giữa pipeline.

Không nên tự mở một connection mới bằng API driver rồi mong nó tự tham gia transaction đã được Spring tạo. Hãy dùng Spring Data R2DBC hoặc DatabaseClient được cấu hình với cùng ConnectionFactory, hoặc dùng ConnectionFactoryUtils để lấy connection gắn với context theo đúng API Spring.

Với nhiều database hoặc nhiều ConnectionFactory, một TransactionalOperator không tự tạo atomic transaction xuyên các hệ thống. Cần xác định rõ tài nguyên nào được quản lý bởi transaction manager đó và chọn giải pháp điều phối phù hợp nếu nghiệp vụ cần phối hợp nhiều hệ thống.

## 11. Kiểm thử commit và rollback bằng StepVerifier

Unit test với mock có thể xác nhận pipeline gọi đúng repository, nhưng không chứng minh database thật đã commit hoặc rollback. Với ranh giới giao dịch, nên có integration test dùng database và reactive transaction manager tương ứng.

### Kiểm thử commit

~~~java
StepVerifier.create(orderService.createOrder(command))
    .assertNext(saved -> assertEquals(command.orderId(), saved.id()))
    .verifyComplete();
~~~

Sau khi Publisher hoàn tất, truy vấn bằng một transaction hoặc connection độc lập để xác nhận bản ghi đã tồn tại. Đảm bảo truy vấn xác minh không tham gia transaction đang kiểm thử.

### Kiểm thử rollback khi bước sau lỗi

~~~java
Mono<Void> work =
    databaseClient.sql("""
        INSERT INTO orders(id, status)
        VALUES (:id, 'NEW')
        """)
        .bind("id", orderId)
        .fetch()
        .rowsUpdated()
        .then(Mono.error(
            new IllegalStateException("inventory update failed")
        ));

StepVerifier.create(
        transactionalOperator.transactional(work)
    )
    .expectErrorMessage("inventory update failed")
    .verify();
~~~

Sau khi test nhận lỗi, dùng một truy vấn độc lập để xác nhận hàng orders với orderId không tồn tại. Kiểm thử cần chạy trên database hỗ trợ transaction thật; mock một repository không thể xác nhận rollback ở tầng lưu trữ.

### Kiểm thử cancellation

Có thể tạo Publisher không hoàn tất sau khi đã thực hiện một thay đổi trong transaction:

~~~java
Mono<Void> work =
    databaseClient.sql("""
        INSERT INTO audit_log(id, message)
        VALUES (:id, 'pending')
        """)
        .bind("id", auditId)
        .fetch()
        .rowsUpdated()
        .then(Mono.never());

StepVerifier.create(
        transactionalOperator.transactional(work)
    )
    .thenAwait(Duration.ofMillis(100))
    .thenCancel()
    .verify();
~~~

Sau cancellation, truy vấn bằng connection độc lập để xác nhận thay đổi chưa commit và tài nguyên được trả về. Trong integration test thực tế, không nên dựa vào một thời gian chờ tùy ý để biết câu lệnh đã chạy; hãy dùng tín hiệu đồng bộ kiểm thử, latch hoặc hook xác nhận bước insert đã hoàn tất trước khi gọi thenCancel.

### Kiểm thử context qua scheduler

Nếu pipeline có publishOn hoặc subscribeOn, hãy kiểm tra các thao tác vẫn tham gia cùng transaction bằng cách xác minh rollback/commit trên database. Không chỉ kiểm tra tên thread. Transaction reactive dựa vào subscriber context; việc thread thay đổi không tự làm mất transaction khi các thao tác vẫn ở cùng reactive chain.

## 12. Các lỗi thiết kế thường gặp

**Mở transaction khi tạo Publisher.** Publisher thường lazy; transaction bắt đầu khi subscribe. Đừng dựa vào thời điểm gọi phương thức để suy luận thời điểm database operation chạy.

**Gọi subscribe bên trong service transactional.** Điều này tách công việc khỏi subscription mà transaction boundary đang quản lý. Hãy trả Publisher về caller.

**Dùng ThreadLocal để tìm transaction.** Thread có thể thay đổi giữa các bước. Dùng Spring reactive transaction support và Reactor Context.

**Nuốt lỗi bên trong transaction.** onErrorResume đặt trong boundary có thể biến lỗi thành complete và làm transaction commit. Đặt fallback ngoài boundary nếu lỗi phải gây rollback.

**Retry trong transaction đã hỏng.** Lỗi database có thể khiến transaction rollback-only. Đặt retry ngoài boundary để mỗi lần thử có transaction mới khi đó là yêu cầu.

**Dùng take rồi giả định transaction rollback.** take có thể hủy upstream nhưng phát complete xuống transaction boundary. Phân tích tín hiệu mà boundary thực sự nhận.

**Giữ transaction quanh Flux vô hạn.** Transaction và connection có thể bị giữ không giới hạn. Chia thành các phạm vi hữu hạn như từng batch.

**Dùng flatMap đồng thời trên cùng transaction mà không kiểm tra driver.** Thứ tự và khả năng hỗ trợ connection đồng thời khác nhau. Ưu tiên concatMap khi các bước ghi phụ thuộc nhau.

**Kỳ vọng transaction database rollback email hoặc HTTP call.** Hệ thống ngoài không tham gia transaction đó. Dùng outbox hoặc saga/compensation khi cần phối hợp.

**Tự đóng connection thuộc transaction manager.** Đóng sai thời điểm có thể làm hỏng các thao tác còn lại. Để transaction manager sở hữu connection trong phạm vi giao dịch.

## 13. Quy trình xác định ranh giới giao dịch

Trước khi bọc một pipeline, hãy trả lời:

1. **Đơn vị nghiệp vụ nào phải atomic?** Một thao tác, một đơn hàng, một batch hay một phiên?
2. **Publisher bắt đầu khi nào?** Xác định subscription nào thực sự kích hoạt công việc.
3. **Những thao tác nào dùng cùng database và transaction manager?** Xác minh ConnectionFactory và repository/client.
4. **Context có được giữ xuyên pipeline không?** Tránh tự subscribe, block hoặc chuyển sang callback imperative ngoài chain.
5. **Tín hiệu nào đến transaction boundary?** Complete, error hay cancel; xem cả các toán tử như take và onErrorResume.
6. **Retry nằm ở đâu?** Nếu mỗi lần thử cần transaction mới, đặt retry ngoài transactional wrapper.
7. **Giao dịch kéo dài bao lâu?** Tránh Flux không giới hạn và I/O ngoài database không cần thiết.
8. **Có thao tác ngoài database không?** Tách email, HTTP và publish message bằng outbox hoặc cơ chế bù trừ.
9. **Driver có hỗ trợ concurrency trong transaction không?** Chọn concatMap hoặc chiến lược phù hợp.
10. **Đã xác minh trên database thật chưa?** Kiểm thử commit, rollback, cancel, connection cleanup và context khi đổi scheduler.

Một transaction boundary tốt phải ngắn, có một chủ sở hữu rõ ràng và kết thúc theo tín hiệu có thể dự đoán. Đừng mở transaction rộng chỉ vì nhiều bước cùng xuất hiện trong một phương thức.

## 14. Bài tập vận dụng

Một endpoint tạo đơn hàng cần thực hiện ba thay đổi database: chèn đơn hàng, trừ tồn kho và ghi lịch sử trạng thái. Sau khi commit, hệ thống cần phát sự kiện ORDER_CREATED lên message broker. Client có thể ngắt kết nối trong lúc request đang chạy.

Hãy thiết kế ranh giới và trả lời:

1. Ba thao tác database nào phải nằm trong cùng transaction để giữ invariant?
2. Dùng TransactionalOperator hoặc @Transactional ở đâu để bao trọn các Publisher?
3. Vì sao không gọi subscribe bên trong service method?
4. Nếu trừ tồn kho phát lỗi, transaction phải kết thúc thế nào?
5. Nếu onErrorResume nằm bên trong transaction và thay lỗi bằng giá trị mặc định, điều gì có thể xảy ra với commit?
6. Nếu retry một lỗi tạm thời, đặt retry trong hay ngoài transactional wrapper để mỗi lần thử có transaction mới?
7. Nếu client cancel, làm sao phân biệt cancellation ở ngoài boundary với take kết thúc sớm bên trong pipeline?
8. Vì sao không nên gửi message broker trước khi transaction database commit?
9. Hãy dùng outbox để bảo đảm sự kiện có thể được gửi lại sau commit.
10. Viết StepVerifier integration test cho commit, rollback khi trừ tồn kho lỗi và cancellation giữa chừng.

Bài tập nên được kiểm thử trên database reactive thực tế của dự án. Một mock có thể kiểm tra thứ tự gọi phương thức, nhưng chỉ integration test mới xác nhận được transaction context, connection binding và rollback ở tầng database.

## Kết luận

Ranh giới giao dịch reactive gắn với subscription và Reactor Context. TransactionalOperator hoặc @Transactional điều phối việc mở, commit, rollback và giải phóng tài nguyên theo vòng đời Publisher. Context giúp transaction đi qua các bước bất đồng bộ và thay đổi scheduler mà không phụ thuộc ThreadLocal. Vị trí của onErrorResume, retry, take và share có thể làm thay đổi tín hiệu mà transaction boundary quan sát được. Hãy giữ transaction ngắn, để các thao tác database dùng cùng transaction manager, tách tác vụ ngoài database bằng outbox khi cần và xác minh commit, rollback, cancellation bằng integration test.
