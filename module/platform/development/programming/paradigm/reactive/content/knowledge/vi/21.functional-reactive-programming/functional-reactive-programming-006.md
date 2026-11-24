# Phản ứng hàm

## Tính nhất quán khi một thay đổi kéo theo nhiều cập nhật

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học cách tổ chức ứng dụng quanh các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trong ứng dụng thực tế, một thay đổi nghiệp vụ thường ảnh hưởng đến nhiều phần của hệ thống: cập nhật trạng thái đơn hàng, tính lại tổng tiền, thay đổi lượng tồn cần giữ, làm mới màn hình quản trị và phát thông báo. Thách thức là bảo đảm những cập nhật đó cùng phản ánh một thay đổi nguồn và không tạo ra các trạng thái mâu thuẫn.

Tư duy phản ứng hàm giúp giải quyết vấn đề bằng cách biểu diễn thay đổi thành sự kiện, áp dụng sự kiện lên trạng thái bất biến qua một hàm chuyển trạng thái thuần, rồi tạo các bản chiếu (projection) từ cùng một phiên bản trạng thái. Trong Reactor, `scan` có thể phát trạng thái sau mỗi sự kiện; các toán tử ghép luồng giúp điều phối cập nhật tiếp theo. Tuy nhiên, việc nhiều toán tử chạy trong một pipeline không tự tạo ra giao dịch phân tán. Ta vẫn phải xác định ranh giới transaction, thứ tự, xử lý lỗi, chống trùng và cách phục hồi khi một hệ thống phụ thuộc thất bại.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một thay đổi nghiệp vụ cần tạo nhiều cập nhật nhất quán.
- Phân biệt trạng thái nguồn, trạng thái dẫn xuất và tác dụng phụ bên ngoài.
- Thiết kế reducer thuần để tạo một phiên bản trạng thái mới từ một sự kiện.
- Dùng `scan` để phát trạng thái mới và tạo nhiều projection từ cùng một snapshot.
- Giữ thứ tự cập nhật bằng `concatMap`, version và quy tắc chống sự kiện trùng.
- Nhận diện nguy cơ lệch phiên bản khi ghép nhiều luồng bằng `combineLatest`.
- Phân biệt tính nhất quán trong một transaction với nhất quán cuối cùng giữa các dịch vụ.
- Dùng transaction và transactional outbox để phối hợp cập nhật dữ liệu cùng sự kiện phát ra.
- Kiểm thử các invariant và tình huống lỗi bằng `StepVerifier`.

## 1. Một thay đổi có thể kéo theo nhiều cập nhật

Xét một đơn hàng có số lượng sản phẩm thay đổi. Thay đổi này có thể ảnh hưởng tới:

- Số lượng mặt hàng trong đơn.
- Tạm tính, thuế và tổng tiền.
- Yêu cầu tồn kho cần giữ.
- Điều kiện miễn phí vận chuyển.
- Thông tin hiển thị trong trang chi tiết.
- Số liệu tổng hợp trên dashboard.
- Sự kiện thông báo cho các hệ thống khác.

Nếu mỗi phần tự nhận một lệnh riêng và cập nhật độc lập, hệ thống có thể rơi vào trạng thái một phần đã mới, phần khác vẫn cũ. Ví dụ, màn hình hiển thị tổng tiền mới nhưng hệ thống kho vẫn giữ số lượng cũ; hoặc thông báo đã phát trong khi transaction lưu đơn hàng bị rollback.

Ta cần một khái niệm rõ ràng về **một thay đổi nghiệp vụ**. Thay đổi đó nên có một định danh, một phiên bản và một điểm chuyển trạng thái có thể xác định. Từ cùng kết quả chuyển trạng thái, các dữ liệu dẫn xuất được tính lại theo cùng một phiên bản.

~~~mermaid
flowchart TD
    E[Sự kiện: QuantityChanged] --> R[Reducer thuần]
    S[OrderState phiên bản N] --> R
    R --> N[OrderState phiên bản N+1]
    N --> P1[Projection thanh toán]
    N --> P2[Projection tồn kho]
    N --> P3[Projection dashboard]
    N --> O[Outbox event]
~~~

Sơ đồ thể hiện một thay đổi đầu vào được áp dụng một lần lên trạng thái nguồn. Tất cả projection được tạo từ cùng snapshot mới. Nhờ đó, các phép tính dẫn xuất có cùng version và cùng dữ liệu nền.

## 2. Phân biệt trạng thái nguồn, projection và tác dụng phụ

Ba khái niệm này cần được tách rõ.

**Trạng thái nguồn (canonical state)** là trạng thái nghiệp vụ có thẩm quyền của aggregate, ví dụ đơn hàng có số lượng, giá, thuế suất và version hiện tại. Đây là nơi reducer áp dụng sự kiện theo quy tắc miền.

**Projection hoặc read model** là dữ liệu được tính từ trạng thái nguồn để phục vụ một mục đích đọc cụ thể. Ví dụ, projection thanh toán chứa subtotal và total; projection kho chứa số lượng cần giữ; projection dashboard chứa số liệu tổng hợp. Projection có thể được tính lại từ trạng thái nguồn.

**Tác dụng phụ bên ngoài** là hành động như gửi HTTP request, phát message, gửi email hoặc gọi dịch vụ kho. Các hành động này có vòng đời, lỗi và tính nhất quán riêng. Chúng không phải là phép biến đổi thuần của reducer.

| Loại | Ví dụ | Cách quản lý |
|---|---|---|
| Trạng thái nguồn | Số lượng và version của đơn hàng | Reducer, event log hoặc kho trạng thái có kiểm soát |
| Projection | Tổng tiền, số lượng cần giữ, dữ liệu dashboard | Tính từ cùng snapshot; có version để đối chiếu |
| Tác dụng phụ | Gửi yêu cầu giữ hàng, phát thông báo | Publisher bất đồng bộ, retry có giới hạn, idempotency và theo dõi kết quả |

Không nên gọi dịch vụ bên ngoài bên trong reducer. Reducer cần thuần để cùng trạng thái và sự kiện luôn tạo cùng kết quả. Nếu reducer vừa tính tổng tiền vừa gọi kho để giữ hàng, kết quả của nó sẽ phụ thuộc mạng, thời điểm và trạng thái dịch vụ ngoài; việc phát lại sự kiện cũng có thể thực hiện tác dụng phụ lặp lại.

## 3. Dùng một sự kiện và một reducer để tạo snapshot nhất quán

Giả sử đơn hàng chỉ cần minh họa thay đổi số lượng. Sự kiện có version để phát hiện thứ tự sai hoặc sự kiện trùng:

~~~java
sealed interface OrderEvent {
    String orderId();
    long version();
}

record QuantityChanged(
    String orderId,
    long version,
    int quantity
) implements OrderEvent {}
~~~

Trạng thái đơn hàng được biểu diễn bằng record bất biến:

~~~java
record OrderState(
    String orderId,
    long version,
    int quantity,
    BigDecimal unitPrice,
    BigDecimal taxRate,
    BigDecimal subtotal,
    BigDecimal tax,
    BigDecimal total
) {
    static OrderState initial(
        String orderId,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal taxRate
    ) {
        return calculate(
            orderId, 0, quantity, unitPrice, taxRate
        );
    }

    OrderState apply(OrderEvent event) {
        if (!orderId.equals(event.orderId())) {
            throw new IllegalArgumentException("Event belongs to another order");
        }

        if (event.version() != version + 1) {
            throw new EventSequenceException(
                "Expected version " + (version + 1)
                    + " but received " + event.version()
            );
        }

        if (event instanceof QuantityChanged changed) {
            if (changed.quantity() <= 0) {
                throw new InvalidOrderEventException(
                    "Quantity must be positive"
                );
            }

            return calculate(
                orderId,
                changed.version(),
                changed.quantity(),
                unitPrice,
                taxRate
            );
        }

        throw new IllegalArgumentException("Unsupported order event");
    }

    private static OrderState calculate(
        String orderId,
        long version,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal taxRate
    ) {
        BigDecimal subtotal = unitPrice
            .multiply(BigDecimal.valueOf(quantity))
            .setScale(2, RoundingMode.HALF_UP);

        BigDecimal tax = subtotal
            .multiply(taxRate)
            .setScale(2, RoundingMode.HALF_UP);

        BigDecimal total = subtotal.add(tax);

        return new OrderState(
            orderId, version, quantity, unitPrice, taxRate,
            subtotal, tax, total
        );
    }
}
~~~

Ví dụ dùng `BigDecimal` cho tiền tệ để tránh sai số nhị phân của `double`. Reducer kiểm tra aggregate ID, version và số lượng trước khi tạo record mới. Các trường subtotal, tax và total được tính trong cùng một hàm từ cùng quantity và unit price.

Nếu quantity đổi từ 2 thành 3, một snapshot mới có version tăng một và tất cả giá trị dẫn xuất được tính lại cùng lúc. Không có thời điểm nào trong phép tính thuần mà subtotal đã mới nhưng total vẫn còn giá trị từ version cũ.

Trong ứng dụng thực tế, cần bổ sung các quy tắc như làm tròn theo tiền tệ, giảm giá, phí vận chuyển, thuế theo địa chỉ và chính sách giá. Mục đích của ví dụ là thể hiện một nguyên tắc: **một transition tạo ra một snapshot hoàn chỉnh**.

## 4. Phát trạng thái sau mỗi sự kiện bằng scan

Giả sử event store trả về các sự kiện của một đơn theo đúng thứ tự version:

~~~java
Flux<OrderEvent> events =
    eventStore.readForOrder(orderId);

OrderState initial =
    OrderState.initial(
        orderId,
        1,
        new BigDecimal("25.00"),
        new BigDecimal("0.08")
    );

Flux<OrderState> states =
    events
        .scan(initial, OrderState::apply)
        .skip(1);
~~~

`scan` phát seed ban đầu rồi phát trạng thái mới sau mỗi sự kiện. `skip(1)` bỏ seed nếu downstream chỉ cần các thay đổi phát sinh. Nếu giao diện cần hiển thị ngay trạng thái ban đầu, không bỏ seed hoặc phát snapshot ban đầu riêng theo hợp đồng API.

Giả sử event log có hai sự kiện:

| Version | Sự kiện | Quantity | Subtotal | Tax (8%) | Total |
|---:|---|---:|---:|---:|---:|
| 0 | Snapshot ban đầu | 1 | 25.00 | 2.00 | 27.00 |
| 1 | QuantityChanged(2) | 2 | 50.00 | 4.00 | 54.00 |
| 2 | QuantityChanged(3) | 3 | 75.00 | 6.00 | 81.00 |

Các projection được tạo từ cùng `OrderState`:

~~~java
record BillingView(
    String orderId,
    long version,
    BigDecimal subtotal,
    BigDecimal tax,
    BigDecimal total
) {}

record StockRequirement(
    String orderId,
    long version,
    int quantity
) {}

record DashboardView(
    String orderId,
    long version,
    BigDecimal total,
    boolean qualifiesForFreeShipping
) {}

record OrderUpdate(
    long version,
    BillingView billing,
    StockRequirement stock,
    DashboardView dashboard
) {}
~~~

Một hàm projection tổng hợp có thể tạo tất cả view trong một lần:

~~~java
OrderUpdate project(OrderState state) {
    return new OrderUpdate(
        state.version(),
        new BillingView(
            state.orderId(),
            state.version(),
            state.subtotal(),
            state.tax(),
            state.total()
        ),
        new StockRequirement(
            state.orderId(),
            state.version(),
            state.quantity()
        ),
        new DashboardView(
            state.orderId(),
            state.version(),
            state.total(),
            state.total().compareTo(new BigDecimal("100.00")) >= 0
        )
    );
}

Flux<OrderUpdate> updates =
    states.map(this::project);
~~~

Mỗi `OrderUpdate` mang cùng version ở tất cả projection. Downstream có thể lưu hoặc phát gói cập nhật này như một đơn vị logic. Nếu một projection có version khác, ta có thể phát hiện dữ liệu chưa đồng bộ thay vì âm thầm ghép các giá trị khác thời điểm.

## 5. Tránh tạo nhiều subscription ngoài ý muốn

Một nguồn cold thường thực thi lại cho mỗi subscription. Nếu ta tạo các luồng dẫn xuất riêng và subscribe độc lập:

~~~java
Flux<OrderState> states =
    eventStore.readForOrder(orderId)
        .scan(initial, OrderState::apply);

states.map(this::toBillingView)
    .subscribe(billingRepository::update);

states.map(this::toStockRequirement)
    .subscribe(stockRepository::update);
~~~

Hai subscription có thể khiến event store được đọc hai lần và reducer chạy hai lần. Nếu nguồn thực hiện I/O hoặc có tác dụng phụ, công việc có thể bị lặp. Hai nhánh cũng có thể tiến triển khác nhau do scheduler, lỗi hoặc cancellation, khiến projection không còn được cập nhật cùng nhịp.

Nếu nhiều nhánh thực sự cần dùng chung một lần thực thi, có thể dùng một cấu trúc chia sẻ rõ ràng hoặc tạo một envelope duy nhất như `OrderUpdate` ở trên rồi chuyển nó tới một thành phần điều phối. `share()` có thể chia sẻ subscription upstream giữa các Subscriber đang tham gia, nhưng nó không lưu bền vững dữ liệu, không bảo đảm Subscriber đến muộn nhận lại lịch sử và không tạo giao dịch giữa các nhánh.

Một thiết kế thường dễ kiểm soát hơn là:

1. Subscribe vào event source một lần tại thành phần sở hữu aggregate.
2. Áp dụng reducer một lần để tạo snapshot mới.
3. Tạo một envelope versioned chứa các projection cần thiết.
4. Lưu các projection liên quan trong cùng transaction nếu chúng cùng nằm trong một transactional store.
5. Phát sự kiện outbox sau khi transaction được commit.

Cách này làm rõ ai sở hữu subscription, ai sở hữu trạng thái và điểm nào xác nhận thay đổi đã được lưu.

## 6. Giữ các projection cùng version

Mỗi projection nên mang version của trạng thái nguồn đã tạo ra nó. Version cho phép consumer phát hiện:

- Projection đang xử lý bản cập nhật cũ hơn bản đã lưu.
- Một version bị thiếu.
- Một sự kiện được giao lại.
- Hai worker cùng cố ghi một aggregate.
- Các nhánh cập nhật đang không đồng bộ.

Ví dụ, khi lưu projection, có thể chỉ chấp nhận version mới hơn:

~~~sql
UPDATE order_billing_view
SET version = :version,
    subtotal = :subtotal,
    tax = :tax,
    total = :total
WHERE order_id = :orderId
  AND version < :version;
~~~

Đây là minh họa cho cập nhật có điều kiện. Cần kiểm tra số dòng được cập nhật và xử lý xung đột theo chính sách. Nếu version mới không phải version kế tiếp, có thể cần từ chối và phát lại các sự kiện bị thiếu thay vì bỏ qua khoảng trống.

Một projection có thể được cập nhật lại nhiều lần từ cùng một version nếu thao tác là idempotent. Tuy nhiên, nếu consumer áp dụng delta như "tăng quantity thêm 1", giao lại cùng message có thể làm số lượng tăng hai lần. Ưu tiên cập nhật bằng snapshot/version hoặc lưu event ID đã xử lý để chống trùng.

## 7. Tuần tự hóa cập nhật cho cùng aggregate

Khi sự kiện của cùng một đơn hàng đến liên tiếp, việc xử lý đồng thời có thể gây ghi đè hoặc đảo thứ tự. Ví dụ, event version 2 hoàn tất trước version 1 và projection lưu version 2, sau đó version 1 lại ghi đè dữ liệu mới hơn nếu không có kiểm tra version.

Dùng `concatMap` để tuần tự hóa cập nhật trong một subscription:

~~~java
Mono<Void> processOrderEvents(String orderId) {
    return eventStore.readForOrder(orderId)
        .scan(initialState(orderId), OrderState::apply)
        .skip(1)
        .map(this::project)
        .concatMap(update -> persistUpdate(update))
        .then();
}
~~~

`concatMap` chờ Publisher lưu một update hoàn tất trước khi xử lý update tiếp theo. Đây là lựa chọn phù hợp khi thứ tự cập nhật của cùng aggregate là bắt buộc.

Nếu nhiều aggregate độc lập cần xử lý song song, có thể chia theo aggregate ID và tuần tự hóa bên trong từng nhóm:

~~~java
Flux<Void> processing =
    allEvents
        .groupBy(OrderEvent::orderId)
        .flatMap(group ->
            group.concatMap(event -> processOne(event)),
                16
        );
~~~

Ví dụ này chỉ minh họa nguyên tắc: các sự kiện cùng order đi qua một group tuần tự, trong khi tối đa một số nhóm có thể được xử lý đồng thời. Với `groupBy`, cần quản lý số group, tốc độ tiêu thụ và vòng đời nguồn; không nên dùng tùy tiện cho cardinality không giới hạn.

`flatMapSequential` có thể phát kết quả theo thứ tự nguồn trong khi inner chạy đồng thời. Nhưng nếu các inner cùng ghi vào một projection, thứ tự phát kết quả sau đó không đảo ngược được các tác dụng phụ đã xảy ra song song. Khi chính thao tác ghi phải tuần tự, dùng `concatMap` hoặc một cơ chế khóa/version ở kho lưu trữ.

## 8. combineLatest có thể tạo snapshot pha trộn

Khi các giá trị dẫn xuất được phát từ nhiều luồng riêng, `combineLatest` tạo kết quả mỗi khi một nguồn phát, dùng giá trị mới nhất của các nguồn còn lại. Điều này hữu ích khi các nguồn độc lập và ta muốn kết hợp trạng thái mới nhất của chúng. Tuy nhiên, nếu các luồng đại diện cho nhiều projection của cùng một thay đổi, chúng có thể cập nhật lệch thời điểm.

Ví dụ:

~~~java
Flux.combineLatest(
    billingUpdates,
    stockUpdates,
    dashboardUpdates,
    (billing, stock, dashboard) ->
        new CombinedView(billing, stock, dashboard)
);
~~~

Giả sử billing đã phát version 8, stock vẫn ở version 7 và dashboard ở version 8. `combineLatest` có thể tạo một `CombinedView` chứa dữ liệu của nhiều version. Đây không phải lỗi của toán tử; đó là ngữ nghĩa của nó. Toán tử không biết các nguồn thuộc cùng một transaction nghiệp vụ.

Nếu cần một snapshot nhất quán, hãy phát một envelope được tạo từ cùng `OrderState`, hoặc kiểm tra version trước khi chấp nhận kết quả:

~~~java
Mono<CombinedView> combineSameVersion(
    BillingView billing,
    StockRequirement stock,
    DashboardView dashboard
) {
    boolean sameVersion =
        billing.version() == stock.version()
            && stock.version() == dashboard.version();

    if (!sameVersion) {
        return Mono.error(new InconsistentProjectionVersionException());
    }

    return Mono.just(new CombinedView(billing, stock, dashboard));
}
~~~

Một phương án khác là giữ các projection trong một bảng snapshot hoặc đọc chúng theo một transaction isolation phù hợp. Không nên dùng `zip` thay cho versioning rồi mặc định rằng các phần tử thứ n của mỗi luồng thuộc cùng một thay đổi; tốc độ phát và số lượng phần tử có thể khác nhau.

## 9. Transaction bảo đảm tính nhất quán trong cùng kho dữ liệu

Nếu các projection và outbox cùng nằm trong một cơ sở dữ liệu hỗ trợ transaction, ta có thể lưu chúng trong cùng một transaction. Khi một bước ghi thất bại, toàn bộ transaction rollback; khi commit thành công, tất cả dữ liệu liên quan cùng có hiệu lực.

Ví dụ với `TransactionalOperator` của Spring:

~~~java
Mono<Void> persistUpdate(OrderUpdate update) {
    return transactionalOperator.transactional(
        billingRepository.save(update.billing())
            .then(stockRepository.save(update.stock()))
            .then(dashboardRepository.save(update.dashboard()))
            .then(outboxRepository.append(
                OrderUpdated.from(update)
            ))
    );
}
~~~

Các lệnh được nối bằng `then`, nên thực hiện theo thứ tự trong cùng Publisher transaction. Ví dụ giả định các repository cùng tham gia một transaction manager và cùng transactional resource. Nếu các repository dùng database hoặc transaction manager khác nhau, đoạn mã này không tạo một transaction phân tán tự động.

Transaction bảo đảm các bản ghi trong cùng ranh giới commit/rollback. Nó không làm cho một HTTP request tới dịch vụ kho hoặc một email bên ngoài trở thành một phần của transaction database. Không gọi dịch vụ ngoài rồi kỳ vọng rollback database sẽ hoàn tác tác dụng phụ từ xa.

## 10. Transactional outbox cho cập nhật cần phát ra ngoài

Một tình huống phổ biến là lưu trạng thái đơn hàng và sau đó phát `OrderUpdated` tới broker. Nếu ứng dụng ghi database thành công rồi chết trước khi gửi message, consumer không bao giờ biết thay đổi đã xảy ra. Nếu gửi message trước rồi database rollback, consumer có thể xử lý một thay đổi chưa được commit.

Transactional outbox giải quyết khoảng trống này bằng cách ghi bản ghi outbox trong cùng transaction với trạng thái nguồn và các projection liên quan:

~~~mermaid
sequenceDiagram
    participant A as Reactor pipeline
    participant DB as Database transaction
    participant O as Outbox worker
    participant B as Message broker
    participant C as Consumer
    A->>DB: Lưu state + projections + outbox
    DB-->>A: Commit
    O->>DB: Đọc outbox chưa gửi
    O->>B: Publish OrderUpdated
    B-->>O: Acknowledge
    O->>DB: Đánh dấu outbox đã gửi
    B->>C: Giao message
    C->>DB: Cập nhật projection idempotent
~~~

Worker đọc outbox và gửi message sau khi transaction commit. Nếu worker gửi thành công nhưng chết trước khi đánh dấu đã gửi, message có thể được gửi lại. Vì vậy consumer cần idempotency bằng event ID hoặc version. Outbox thường cung cấp giao nhận ít nhất một lần (at-least-once), không tự bảo đảm exactly-once trên mọi hệ thống.

Điểm quan trọng là thay đổi trạng thái và ý định phát sự kiện được commit cùng nhau. Việc gửi ra broker là bước bất đồng bộ có thể retry và quan sát riêng.

## 11. Nhất quán cuối cùng giữa nhiều dịch vụ

Nếu các cập nhật kéo theo nhiều dịch vụ độc lập, ví dụ order, inventory, payment và notification, thường không thể đặt tất cả vào một transaction ACID duy nhất. Khi đó, hệ thống cần mô hình nhất quán cuối cùng (eventual consistency) và một workflow điều phối như saga.

Ví dụ, thay đổi số lượng đơn hàng có thể tạo yêu cầu điều chỉnh tồn kho. Hệ thống đơn hàng lưu thay đổi và outbox; consumer kho nhận message, kiểm tra version, cập nhật giữ hàng và phát kết quả. Nếu kho từ chối do hết hàng, workflow có thể phát sự kiện thất bại và chuyển đơn về trạng thái cần xử lý.

Một saga cần xác định:

- Các bước và trạng thái trung gian.
- Sự kiện thành công/thất bại của từng bước.
- Timeout và retry có giới hạn.
- Idempotency key cho message và lệnh.
- Hành động bù trừ (compensation) nếu nghiệp vụ yêu cầu.
- Cách đối soát khi không biết hệ thống ngoài đã thực hiện hay chưa.

Hành động bù trừ không phải rollback kỹ thuật. Ví dụ, nếu đã giữ hàng thì bước bù có thể phát lệnh giải phóng giữ hàng. Nó là một thao tác nghiệp vụ mới và cũng có thể thất bại.

Trong Reactor, mỗi bước bất đồng bộ có thể được ghép bằng `flatMap` hoặc `concatMap`; lỗi có thể được phân loại bằng `onErrorResume`, timeout và retry. Tuy nhiên, tính nhất quán cuối cùng đến từ state machine, lưu trữ bền vững, message ID, version và chính sách phục hồi, không chỉ từ các toán tử.

## 12. Backpressure và cập nhật dồn dập

Nếu một aggregate nhận sự kiện nhanh hơn tốc độ tính projection hoặc ghi database, hàng đợi cập nhật có thể tăng. Backpressure giúp điều tiết nguồn Reactive Streams khi nguồn hỗ trợ demand, còn nguồn nóng hoặc broker adapter cần chính sách buffer/ack riêng.

Một số lựa chọn:

- Giới hạn số update đang được ghi bằng `concatMap` hoặc concurrency hữu hạn.
- Chỉ gộp các thay đổi nếu nghiệp vụ cho phép và kết quả cuối tương đương.
- Lưu sự kiện bền vững để worker đọc tiếp khi phục hồi.
- Đặt giới hạn hàng đợi và hành vi khi đầy.
- Theo dõi độ sâu queue, tuổi sự kiện cũ nhất, độ trễ projection và số lần retry.

Không nên bỏ các sự kiện trung gian một cách tùy tiện. Nếu mỗi event là một giao dịch cần kiểm toán, chỉ giữ trạng thái cuối có thể làm mất lịch sử. Nếu event chỉ là cập nhật trạng thái hiển thị, có thể gộp thành snapshot mới nhất. Quyết định phụ thuộc ngữ nghĩa dữ liệu.

## 13. Xử lý lỗi mà không phát trạng thái nửa chừng

Một transition nên được tính hoàn chỉnh trước khi phát snapshot mới. Nếu reducer phát exception vì version sai hoặc dữ liệu không hợp lệ, không nên cập nhật một vài projection rồi bỏ phần còn lại.

Đối với ghi nhiều projection trong cùng database, transaction giúp rollback khi một lệnh ghi thất bại. Với nhiều dịch vụ, cần ghi nhận trạng thái workflow và để saga tiếp tục hoặc bù trừ.

Không nên đặt `onErrorResume(error -> Mono.empty())` ở cuối pipeline chỉ để job tiếp tục. Cách này có thể làm mất một cập nhật mà không có dấu vết. Nếu một event bị từ chối, hãy chuyển nó thành kết quả nghiệp vụ có mã lỗi, ghi vào vùng cách ly hoặc DLQ và giữ thông tin version để có thể điều tra.

Retry chỉ phù hợp khi lỗi có khả năng tạm thời và thao tác an toàn khi lặp. Với cập nhật projection, dùng version hoặc event ID để chống ghi trùng. Với tác dụng phụ bên ngoài, dùng idempotency key ổn định qua các lần retry.

## 14. Kiểm thử tính nhất quán bằng StepVerifier

Kiểm thử reducer thuần trước để xác minh một sự kiện tạo snapshot đầy đủ:

~~~java
@Test
void quantityChangeUpdatesAllDerivedAmountsTogether() {
    OrderState initial = OrderState.initial(
        "order-1",
        1,
        new BigDecimal("25.00"),
        new BigDecimal("0.08")
    );

    OrderState next = initial.apply(
        new QuantityChanged("order-1", 1, 3)
    );

    assertThat(next.version()).isEqualTo(1);
    assertThat(next.quantity()).isEqualTo(3);
    assertThat(next.subtotal()).isEqualByComparingTo("75.00");
    assertThat(next.tax()).isEqualByComparingTo("6.00");
    assertThat(next.total()).isEqualByComparingTo("81.00");
}
~~~

Sau đó kiểm thử pipeline phát snapshot theo từng event:

~~~java
Flux<OrderState> states =
    Flux.just(
        new QuantityChanged("order-1", 1, 2),
        new QuantityChanged("order-1", 2, 3)
    )
    .scan(initial, OrderState::apply)
    .skip(1);

StepVerifier.create(states)
    .assertNext(state -> {
        assertThat(state.version()).isEqualTo(1);
        assertThat(state.quantity()).isEqualTo(2);
        assertThat(state.total()).isEqualByComparingTo("54.00");
    })
    .assertNext(state -> {
        assertThat(state.version()).isEqualTo(2);
        assertThat(state.quantity()).isEqualTo(3);
        assertThat(state.total()).isEqualByComparingTo("81.00");
    })
    .verifyComplete();
~~~

Có thể kiểm thử envelope projection để xác nhận mọi view có cùng version:

~~~java
StepVerifier.create(states.map(this::project))
    .assertNext(update -> {
        assertThat(update.billing().version()).isEqualTo(update.version());
        assertThat(update.stock().version()).isEqualTo(update.version());
        assertThat(update.dashboard().version()).isEqualTo(update.version());
    })
    .thenConsumeWhile(update ->
        update.billing().version() == update.stock().version()
            && update.stock().version() == update.dashboard().version()
    )
    .verifyComplete();
~~~

Các kiểm thử tích hợp nên bao gồm:

- Ghi một projection thất bại; xác minh transaction rollback các projection và outbox cùng transaction.
- Cùng một event ID được giao hai lần; xác minh consumer không áp dụng hai lần.
- Version bị thiếu hoặc đến sai thứ tự; xác minh event bị từ chối hoặc đưa vào retry/replay.
- Outbox worker gửi lại message; xác minh consumer idempotent.
- Một dịch vụ phụ thuộc timeout; xác minh trạng thái workflow chuyển sang nhánh phù hợp.
- Một Subscriber hủy; xác minh nguồn được dừng hoặc vòng đời được giải phóng theo hợp đồng.
- Hai thay đổi liên tiếp của cùng aggregate; xác minh update không bị đảo thứ tự.

Test dùng `StepVerifier` xác minh tín hiệu reactive; transaction rollback, tính nguyên tử của database và giao nhận outbox cần thêm kiểm thử tích hợp với transaction manager và kho lưu trữ thật hoặc môi trường kiểm thử tương đương.

## 15. Những nhầm lẫn thường gặp

- **Một pipeline có nhiều nhánh thì các cập nhật tự động nguyên tử:** Reactor điều phối tín hiệu; tính nguyên tử của dữ liệu cần transaction ở kho lưu trữ hoặc giao thức phân tán phù hợp.
- **Reducer có thể cập nhật database và gọi HTTP:** reducer nên thuần; I/O và tác dụng phụ được ghép ở bước riêng.
- **Mọi projection đều có thể tính độc lập:** nếu chúng cần cùng phản ánh một thay đổi, hãy tạo chúng từ cùng snapshot và mang cùng version.
- **`combineLatest` bảo đảm các nguồn cùng version:** nó kết hợp giá trị mới nhất, có thể tạo snapshot pha trộn khi các nhánh cập nhật lệch nhau.
- **`share()` bảo đảm mọi consumer nhận đủ sự kiện:** share chỉ chia sẻ subscription trong phạm vi Publisher; nó không cung cấp retention, replay bền vững hay exactly-once.
- **`flatMapSequential` bảo đảm tác dụng phụ xảy ra tuần tự:** nó sắp xếp kết quả phát ra, trong khi inner vẫn có thể chạy đồng thời và ghi dữ liệu theo thứ tự khác.
- **Một lần publish thành công nghĩa là consumer đã cập nhật:** broker acknowledgement và việc consumer commit projection là các mốc khác nhau.
- **Outbox bảo đảm exactly-once:** outbox thường hỗ trợ giao ít nhất một lần; consumer vẫn cần idempotency.
- **Retry giải quyết được mọi lỗi cập nhật:** retry dữ liệu sai hoặc lệnh không idempotent có thể làm trạng thái tệ hơn.
- **Snapshot thay thế event log:** snapshot tăng tốc khôi phục; event log vẫn cần thiết nếu nghiệp vụ yêu cầu lịch sử và kiểm toán.

## 16. Bài tập vận dụng

Một đơn hàng có số lượng thay đổi từ 2 lên 4. Thay đổi này cần cập nhật tổng tiền, yêu cầu tồn kho và dashboard; đồng thời phát `OrderQuantityChanged` tới dịch vụ kho.

Hãy thiết kế workflow:

1. Sự kiện đầu vào cần mang những thông tin nào để phát hiện trùng và sai thứ tự?
2. Reducer cần tạo snapshot mới gồm những trường nào?
3. Các projection nên được tạo từ những dữ liệu nào để bảo đảm cùng version?
4. Nếu ba projection nằm trong cùng database, bạn sẽ lưu chúng và outbox trong ranh giới nào?
5. Nếu dịch vụ kho nhận message hai lần, làm thế nào để tránh giữ hàng hai lần?
6. Nếu dashboard cập nhật chậm hơn billing, có thể dùng `combineLatest` trực tiếp không? Cần kiểm tra điều gì?
7. Nếu kho từ chối vì không đủ hàng sau khi đơn đã được cập nhật, saga cần trạng thái hoặc hành động bù nào?
8. Hãy đề xuất các kiểm thử cho rollback, retry, outbox giao lại và version không liên tục.

**Gợi ý:** dùng aggregate ID, event ID và version trên sự kiện. Tạo một snapshot bất biến bằng reducer, sau đó tạo envelope chứa billing, stock requirement và dashboard projection cùng version. Lưu các projection cùng outbox trong một transaction nếu chúng dùng chung transactional resource. Worker phát outbox với event ID ổn định; consumer kho xử lý idempotent. Nếu kho từ chối, ghi nhận kết quả và điều phối trạng thái đơn hàng theo saga thay vì giả định database transaction ban đầu có thể rollback một dịch vụ từ xa.

## Kết luận

Khi một thay đổi kéo theo nhiều cập nhật, tính nhất quán bắt đầu từ một sự kiện có định danh và version, một reducer thuần tạo snapshot bất biến, rồi các projection được tính từ cùng snapshot đó. Reactor `scan` giúp phát trạng thái theo từng sự kiện; `concatMap` giúp tuần tự hóa các cập nhật phụ thuộc; version và idempotency giúp phát hiện sự kiện trùng hoặc sai thứ tự. Transaction bảo vệ các bản ghi cùng một transactional store, còn transactional outbox và saga điều phối thay đổi giữa nhiều dịch vụ với nhất quán cuối cùng. Hãy kiểm thử cả giá trị, version, lỗi, rollback, cancellation và giao lại message để các cập nhật liên quan cùng phản ánh một thay đổi nghiệp vụ một cách có thể kiểm chứng.
