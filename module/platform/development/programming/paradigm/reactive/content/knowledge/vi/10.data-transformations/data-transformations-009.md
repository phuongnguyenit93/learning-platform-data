# Đóng gói một chuỗi toán tử thành phép biến đổi tái sử dụng

Trong một ứng dụng reactive, nhiều luồng dữ liệu thường cần áp dụng cùng một nhóm bước xử lý: chuẩn hóa dữ liệu đầu vào, kiểm tra điều kiện, ghi nhận metric, làm giàu thông tin hoặc chuyển đổi sang kiểu dữ liệu mà tầng tiếp theo cần. Nếu lặp lại toàn bộ chuỗi toán tử map, filter, flatMap và xử lý lỗi ở nhiều nơi, mã nguồn nhanh chóng khó đọc và khó giữ hành vi nhất quán.

Reactor cho phép đóng gói một chuỗi toán tử thành một phép biến đổi có thể tái sử dụng. Với Flux và Mono, phương thức transform nhận một hàm biến đổi publisher hiện tại thành publisher khác. Ta có thể đặt tên cho nhóm thao tác, kiểm thử độc lập và áp dụng nó ở nhiều pipeline. Khi cần tạo cấu hình hoặc trạng thái riêng cho từng subscriber, transformDeferred cung cấp cách áp dụng hàm biến đổi vào thời điểm đăng ký.

## 1. Ý tưởng về phép biến đổi có thể tái sử dụng

Một chuỗi toán tử reactive vốn đã là một phép biến đổi từ publisher đầu vào sang publisher đầu ra. Chẳng hạn:

    Flux<Order> validOrders =
        orders
            .map(Order::normalize)
            .filter(Order::isValid);

Hai bước map và filter nhận một Flux<Order> rồi trả về Flux<Order> mới. Ta có thể gom chúng thành một hàm:

    Function<Flux<Order>, Flux<Order>> normalizeAndValidate =
        source -> source
            .map(Order::normalize)
            .filter(Order::isValid);

Sau đó áp dụng hàm vào nguồn bằng transform:

    Flux<Order> validOrders =
        orders.transform(normalizeAndValidate);

Hàm này mô tả cách biến đổi luồng, không thực hiện subscription. Khi subscriber đăng ký vào kết quả, pipeline mới thực thi và các toán tử xử lý từng tín hiệu theo nhu cầu của subscriber.

Một phép biến đổi tốt thường có tên thể hiện mục đích, có đầu vào và đầu ra rõ ràng, không tự gọi subscribe và không giữ trạng thái dùng chung ngoài ý muốn. Nhờ vậy, nhóm toán tử trở thành một đơn vị có thể đọc, ghép nối và kiểm thử.

## 2. transform trên Flux và Mono

Về mặt khái quát, transform nhận một hàm áp dụng lên publisher:

    Publisher đầu vào
        |
        v
    transform(hàm biến đổi)
        |
        v
    Publisher đầu ra

Với Flux, hàm biến đổi thường nhận Flux<T> và trả về một Publisher<R> hoặc Flux<R>. Với Mono, hàm nhận Mono<T> và trả về một Publisher<R> hoặc Mono<R>. Kiểu đầu ra có thể giữ nguyên hoặc thay đổi kiểu dữ liệu.

Ví dụ với Flux:

    Function<Flux<String>, Flux<String>> normalizeNames =
        source -> source
            .map(String::trim)
            .filter(name -> !name.isEmpty())
            .map(String::toUpperCase);

    Flux<String> names =
        Flux.just(" An ", "", "Bình ")
            .transform(normalizeNames);

Kết quả là hai phần tử AN và BÌNH. Nhóm bước chuẩn hóa được đặt tên một lần và có thể áp dụng cho nhiều nguồn chuỗi khác nhau.

Ví dụ với Mono:

    Function<Mono<User>, Mono<User>> requireActiveUser =
        source -> source
            .filter(User::isActive)
            .switchIfEmpty(
                Mono.error(new IllegalStateException("User is inactive"))
            );

    Mono<User> user =
        userRepository.findById(userId)
            .transform(requireActiveUser);

Ở đây, phép biến đổi giữ kiểu Mono<User>, nhưng thêm chính sách chỉ cho phép user đang hoạt động đi tiếp. Nếu Mono rỗng hoặc user không hoạt động, downstream nhận lỗi theo chính sách đã định nghĩa.

## 3. Tách chuỗi toán tử thành các hàm có tên

Khi pipeline có nhiều trách nhiệm, có thể chia thành nhiều phép biến đổi nhỏ thay vì tạo một hàm lớn. Mỗi hàm nên thể hiện một ý nghĩa cụ thể của nghiệp vụ.

Ví dụ mô hình đơn hàng:

    import java.math.BigDecimal;
    import java.util.Locale;
    import reactor.core.publisher.Flux;

    record Order(String id, String email, BigDecimal amount) {
        Order normalized() {
            String normalizedId = id == null ? "" : id.trim();
            String normalizedEmail = email == null
                ? ""
                : email.trim().toLowerCase(Locale.ROOT);
            return new Order(normalizedId, normalizedEmail, amount);
        }

        boolean isValid() {
            return !id.isBlank()
                && !email.isBlank()
                && amount != null
                && amount.signum() >= 0;
        }
    }

    record OrderSummary(String orderId, BigDecimal amount) {}

Ta có thể định nghĩa phép chuẩn hóa và kiểm tra:

    Function<Flux<Order>, Flux<Order>> normalizeAndValidate =
        source -> source
            .map(Order::normalized)
            .filter(Order::isValid);

Và phép chuyển đổi sang summary:

    Function<Flux<Order>, Flux<OrderSummary>> toSummary =
        source -> source.map(
            order -> new OrderSummary(order.id(), order.amount())
        );

Áp dụng từng phép biến đổi:

    Flux<OrderSummary> summaries =
        incomingOrders
            .transform(normalizeAndValidate)
            .transform(toSummary);

Pipeline thể hiện rõ thứ tự nghiệp vụ: chuẩn hóa, loại dữ liệu không hợp lệ, rồi chuyển sang summary. Hai phép biến đổi có thể được dùng riêng ở những luồng cần cùng chính sách.

Một lưu ý với ví dụ trên: record Order cần được khởi tạo với các giá trị đầu vào có thể null; phương thức normalized chuyển id và email null thành chuỗi rỗng trước khi isValid được gọi. Nếu dữ liệu có quy tắc chuẩn hóa phức tạp hơn, hãy tách phần xác thực thành một hàm thuần để dễ kiểm thử.

## 4. Ghép các phép biến đổi bằng Function

Các phép biến đổi cùng kiểu có thể được ghép bằng Function.andThen hoặc Function.compose của Java. andThen áp dụng hàm thứ hai sau khi hàm thứ nhất hoàn tất; compose áp dụng hàm được truyền vào trước hàm hiện tại.

Ví dụ:

    Function<Flux<Order>, Flux<Order>> normalizeAndValidate =
        source -> source
            .map(Order::normalized)
            .filter(Order::isValid);

    Function<Flux<Order>, Flux<OrderSummary>> toSummary =
        source -> source.map(
            order -> new OrderSummary(order.id(), order.amount())
        );

    Function<Flux<Order>, Flux<OrderSummary>> orderSummaryPipeline =
        normalizeAndValidate.andThen(toSummary);

    Flux<OrderSummary> summaries =
        incomingOrders.transform(orderSummaryPipeline);

Đầu ra của normalizeAndValidate là Flux<Order>, đúng với kiểu đầu vào của toSummary. Vì hai hàm tương thích về kiểu, andThen tạo ra một hàm tổng hợp.

Khi các phép biến đổi thay đổi kiểu dữ liệu, cần kiểm tra thứ tự và generic type. Không thể ghép hai Function tùy ý nếu kiểu đầu ra của hàm trước không tương thích với kiểu đầu vào của hàm sau.

Không nhất thiết phải tạo một Function tổng hợp cho mọi pipeline. Nếu việc ghép làm tên biến hoặc generic quá phức tạp, gọi transform theo từng bước thường dễ đọc hơn:

    Flux<OrderSummary> summaries =
        incomingOrders
            .transform(normalizeAndValidate)
            .transform(toSummary);

Hai cách có cùng mục đích; hãy chọn cách giúp người đọc thấy rõ ranh giới nghiệp vụ.

## 5. transform áp dụng hàm biến đổi khi nào?

transform áp dụng hàm biến đổi khi pipeline được lắp ráp. Hàm nhận publisher nguồn và trả về publisher đã được bọc bởi các toán tử. Kết quả publisher vẫn lazy: các thao tác xử lý dữ liệu chỉ chạy khi có subscriber.

Sự khác nhau giữa thời điểm áp dụng hàm và thời điểm xử lý phần tử rất quan trọng:

| Thời điểm | Điều xảy ra |
|---|---|
| Assembly | Hàm truyền vào transform được áp dụng để tạo cấu trúc pipeline |
| Subscribe | Subscriber đăng ký vào publisher; nguồn bắt đầu thực thi theo demand |
| Signal | Các toán tử xử lý onNext, onError hoặc onComplete theo thứ tự |

Nếu hàm biến đổi tạo một đối tượng trạng thái bên ngoài các callback như AtomicLong, đối tượng đó có thể được tạo một lần lúc assembly và được giữ trong pipeline cho nhiều subscriber. Điều này có thể là chủ ý, nhưng thường không phù hợp nếu trạng thái phải độc lập cho từng subscriber.

Ví dụ minh họa trạng thái được tạo khi assembly:

    Flux<String> numbered =
        Flux.just("A", "B")
            .transform(source -> {
                AtomicLong counter = new AtomicLong();
                return source.map(
                    value -> counter.incrementAndGet() + ":" + value
                );
            });

Nếu cùng publisher numbered được subscribe nhiều lần, counter ở trên được giữ trong pipeline đã lắp ráp. Subscriber sau có thể tiếp tục số đếm từ subscriber trước. Nếu các subscriber chạy đồng thời, AtomicLong bảo đảm phép tăng nguyên tử nhưng vẫn là một bộ đếm dùng chung.

## 6. transformDeferred cho cấu hình riêng từng subscriber

Khi cần tạo trạng thái mới hoặc áp dụng logic riêng mỗi lần có subscriber, dùng transformDeferred. Hàm biến đổi được gọi cho mỗi subscription, nên có thể khởi tạo tài nguyên hoặc trạng thái gắn với subscriber đó.

Ví dụ:

    Flux<String> numberedPerSubscriber =
        Flux.just("A", "B")
            .transformDeferred(source -> {
                AtomicLong counter = new AtomicLong();
                return source.map(
                    value -> counter.incrementAndGet() + ":" + value
                );
            });

Mỗi lần subscribe, hàm truyền cho transformDeferred tạo một AtomicLong mới. Vì vậy, mỗi subscriber bắt đầu từ 1:

    numberedPerSubscriber.subscribe(System.out::println);
    numberedPerSubscriber.subscribe(System.out::println);

Mỗi subscription lần lượt nhận 1:A và 2:B. Subscriber thứ hai cũng bắt đầu lại từ 1:A vì trạng thái được tạo riêng cho lần đăng ký đó.

So sánh:

| Tiêu chí | transform | transformDeferred |
|---|---|---|
| Thời điểm gọi hàm biến đổi | Khi assembly | Mỗi lần subscribe |
| Trạng thái tạo trong hàm | Được chia sẻ qua các subscription của pipeline đã lắp ráp | Mỗi subscription có trạng thái riêng |
| Mục đích thường gặp | Đóng gói cấu trúc toán tử cố định | Tạo logic hoặc trạng thái theo subscriber |
| Chi phí | Hàm biến đổi được áp dụng một lần | Hàm biến đổi được áp dụng lại cho mỗi subscriber |

Không dùng transformDeferred chỉ vì muốn pipeline lazy; cả transform và transformDeferred đều tạo publisher lazy. Chọn transformDeferred khi chính việc xây dựng nhánh pipeline cần diễn ra riêng cho từng subscription.

## 7. Tách chính sách theo Context của subscriber

Trong Reactor, Context là dữ liệu gắn với subscription, thường dùng để truyền metadata như correlation ID, tenant hoặc thông tin xác thực qua pipeline mà không phải thêm tham số vào mọi phương thức.

Khi logic biến đổi cần đọc Context, có thể dùng transformDeferredContextual. Hàm này nhận publisher hiện tại và ContextView của subscription:

    Flux<Event> taggedEvents =
        eventSource.events()
            .transformDeferredContextual((source, context) -> {
                String tenantId =
                    context.getOrDefault("tenantId", "public");

                return source.doOnNext(
                    event -> log.debug(
                        "tenant={} event={}", tenantId, event.id()
                    )
                );
            });

    taggedEvents
        .contextWrite(context -> context.put("tenantId", "tenant-42"))
        .subscribe(this::handleEvent);

Context được đọc khi subscription được thiết lập, vì vậy mỗi subscriber có thể cung cấp tenantId khác nhau. transformDeferredContextual hữu ích khi việc xây dựng nhánh pipeline phụ thuộc metadata của subscriber. Hãy tránh lưu ContextView vào biến toàn cục hoặc dùng nó sau khi subscription đã kết thúc.

Không dùng Context thay cho dữ liệu nghiệp vụ cần truyền rõ ràng trong model. Context phù hợp cho metadata xuyên suốt pipeline; dữ liệu cần được kiểm tra, lưu trữ hoặc trả về vẫn nên nằm trong kiểu dữ liệu của ứng dụng.

## 8. Xử lý lỗi bên trong phép biến đổi

Một phép biến đổi có thể thêm chính sách lỗi chung cho nhiều pipeline. Ví dụ, một nhóm thao tác có thể chuyển lỗi kỹ thuật sang lỗi miền nghiệp vụ:

    Function<Flux<Order>, Flux<Order>> mapOrderErrors =
        source -> source.onErrorMap(
            error -> new OrderProcessingException(
                "Không thể xử lý luồng đơn hàng",
                error
            )
        );

    Flux<Order> processed =
        incomingOrders
            .transform(normalizeAndValidate)
            .transform(mapOrderErrors);

onErrorMap chuyển lỗi upstream thành lỗi mới và giữ nguyên nguyên nhân làm cause. Lỗi vẫn là tín hiệu terminal nếu không có toán tử phục hồi ở phía sau.

Nếu có fallback chung, có thể đóng gói onErrorResume:

    Function<Flux<Price>, Flux<Price>> useCachedPrices =
        source -> source.onErrorResume(
            PriceServiceUnavailable.class,
            error -> cache.latestPrices()
        );

    Flux<Price> prices =
        remotePrices.transform(useCachedPrices);

Hãy đặt chính sách lỗi ở đúng ranh giới. Một phép biến đổi dùng chung không nên nuốt mọi lỗi bằng một giá trị mặc định nếu các pipeline có yêu cầu nghiệp vụ khác nhau. Những lỗi cần retry, fallback hoặc trả lỗi cho caller nên được phân loại rõ ràng.

## 9. Không subscribe bên trong phép biến đổi

Hàm truyền cho transform chỉ nên xây dựng và trả về publisher mới. Không gọi subscribe bên trong hàm đó:

    // Không nên: tạo một subscription tách khỏi pipeline bên ngoài.
    Function<Flux<Order>, Flux<Order>> wrong =
        source -> {
            source.subscribe(this::saveOrder);
            return source;
        };

Đoạn mã trên tạo một subscription phụ ngay khi hàm biến đổi được áp dụng. Khi subscriber của publisher kết quả đăng ký, nguồn có thể chạy trong subscription riêng và lại chạy lần nữa trong subscription ngoài. Lỗi, cancellation và backpressure của pipeline bên ngoài cũng không còn quản lý được subscription phụ đó.

Hãy trả về publisher đã gắn toán tử:

    Function<Flux<Order>, Flux<Order>> saveOrders =
        source -> source.doOnNext(this::saveOrder);

    Flux<Order> result = incomingOrders.transform(saveOrders);

Trong trường hợp lưu dữ liệu bất đồng bộ, dùng flatMap để đưa publisher lưu vào cùng pipeline:

    Function<Flux<Order>, Flux<Order>> persistOrders =
        source -> source.flatMap(
            orderRepository::save,
            16
        );

flatMap cho phép giới hạn số thao tác lưu đồng thời ở mức 16 trong ví dụ. Lỗi và cancellation của nhánh vẫn thuộc cùng subscription được quản lý từ bên ngoài.

## 10. Kiểm thử phép biến đổi độc lập

Vì phép biến đổi là một hàm nhận publisher và trả publisher, ta có thể kiểm thử nó bằng một nguồn nhỏ mà không cần dựng toàn bộ ứng dụng.

Ví dụ kiểm tra chuẩn hóa và xác thực đơn hàng:

    Order valid = new Order(
        " order-1 ",
        " USER@EXAMPLE.COM ",
        new BigDecimal("125.00")
    );

    Order invalid = new Order(
        " ",
        "bad@example.com",
        new BigDecimal("10.00")
    );

    StepVerifier.create(
            Flux.just(valid, invalid)
                .transform(normalizeAndValidate)
        )
        .expectNextMatches(order ->
            order.id().equals("order-1")
                && order.email().equals("user@example.com")
        )
        .verifyComplete();

Bài kiểm thử xác nhận phần tử hợp lệ được chuẩn hóa và phần tử không hợp lệ bị loại bỏ. Phép biến đổi có thể được kiểm thử độc lập với các nguồn khác nhau, ví dụ Flux.just, Flux.fromIterable hoặc publisher từ client mạng.

Kiểm tra transformDeferred tạo trạng thái riêng cho từng subscriber:

    StepVerifier.create(numberedPerSubscriber)
        .expectNext("1:A", "2:B")
        .verifyComplete();

    StepVerifier.create(numberedPerSubscriber)
        .expectNext("1:A", "2:B")
        .verifyComplete();

Cả hai subscription đều bắt đầu từ 1. Nếu dùng transform với counter được tạo trong hàm biến đổi, subscription thứ hai sẽ tiếp tục trạng thái đã dùng ở subscription đầu tiên; kết quả đó khác với ý định của ví dụ.

Có thể kiểm tra lỗi và fallback bằng expectError hoặc expectNext cùng verifyComplete tùy chính sách được đóng gói. Khi phép biến đổi dùng Context, hãy kiểm thử ít nhất hai subscription với Context khác nhau để xác nhận dữ liệu của chúng không bị trộn.

## 11. Tổ chức thư viện phép biến đổi trong ứng dụng

Khi một dự án có nhiều pipeline, nên đặt các phép biến đổi theo miền nghiệp vụ hoặc chức năng thay vì gom tất cả vào một lớp tiện ích chung.

Ví dụ cấu trúc:

    order/
      OrderTransforms.java
      OrderRepository.java
      OrderService.java

OrderTransforms có thể cung cấp các hàm như normalizeAndValidate, enrichWithCustomer và mapOrderErrors. OrderService ghép chúng theo luồng nghiệp vụ; repository chỉ chịu trách nhiệm truy cập dữ liệu.

Một phép biến đổi nên:

- Có tên diễn đạt kết quả hoặc chính sách mà nó áp dụng.
- Giữ kiểu đầu vào và đầu ra rõ ràng.
- Chỉ làm một nhóm trách nhiệm liên quan.
- Không tự subscribe hoặc chặn để chờ kết quả.
- Không giữ trạng thái mutable dùng chung trừ khi đó là chủ ý được kiểm soát.
- Có kiểm thử cho dữ liệu hợp lệ, dữ liệu không hợp lệ và lỗi.

Không cần đóng gói một map đơn giản chỉ dùng đúng một lần. transform hữu ích khi nhóm toán tử có ý nghĩa riêng, được tái sử dụng hoặc cần kiểm thử như một đơn vị. Nếu chia quá nhỏ, người đọc phải nhảy qua nhiều hàm để hiểu một pipeline; hãy giữ ranh giới ở mức có ích cho nghiệp vụ.

## 12. Những nhầm lẫn thường gặp

**Cho rằng transform subscribe vào nguồn.** transform chỉ áp dụng hàm để xây dựng publisher mới. Subscription vẫn do bên sử dụng publisher kết quả quyết định.

**Cho rằng transform và transformDeferred giống nhau.** transform áp dụng hàm lúc assembly; transformDeferred áp dụng lại hàm cho mỗi subscription. Sự khác nhau thể hiện rõ khi hàm tạo trạng thái hoặc cấu hình.

**Dùng transformDeferred để sửa trạng thái dùng chung.** Trạng thái cần riêng từng subscriber nên được tạo bên trong hàm deferred hoặc trong nguồn defer phù hợp.

**Gọi subscribe bên trong hàm biến đổi.** Việc đó tạo subscription phụ và tách nó khỏi backpressure, lỗi và cancellation của pipeline chính.

**Đóng gói quá nhiều trách nhiệm vào một Function.** Một phép biến đổi khổng lồ khó tái sử dụng và kiểm thử. Chia theo chính sách nghiệp vụ, rồi ghép theo thứ tự cần thiết.

**Cho rằng mọi lỗi đều nên được fallback giống nhau.** Lỗi nghiệp vụ, lỗi dữ liệu và lỗi hạ tầng có ý nghĩa khác nhau. Chọn onErrorMap, onErrorResume hoặc truyền lỗi tiếp tùy hợp đồng của tầng gọi.

## 13. Checklist trước khi tái sử dụng một phép biến đổi

Trước khi đưa một chuỗi toán tử vào thư viện dùng chung, hãy xác định:

1. Phép biến đổi nhận kiểu publisher nào và trả về kiểu nào?
2. Các bước trong hàm có cùng một trách nhiệm nghiệp vụ không?
3. Hàm được áp dụng lúc assembly hay cần được tạo riêng theo subscriber?
4. Có trạng thái mutable nào được giữ lại giữa các subscription không?
5. Hàm có giữ nguyên backpressure và cancellation bằng cách trả về publisher không?
6. Lỗi được truyền tiếp, chuyển đổi hay fallback theo chính sách nào?
7. Có gọi subscribe hoặc thực hiện thao tác blocking bên trong hàm không?
8. StepVerifier đã kiểm tra đầu ra, lỗi và hành vi theo từng subscription chưa?

Khi dùng transform để đặt tên cho một chuỗi toán tử và transformDeferred cho logic cần tạo riêng theo subscription, các pipeline Mono và Flux trở nên dễ đọc, nhất quán và dễ kiểm thử. Phép biến đổi tái sử dụng vẫn giữ nguyên mô hình reactive: publisher mô tả công việc, subscriber quyết định thời điểm tiêu thụ, còn backpressure và cancellation được truyền qua cùng một chuỗi publisher.
