# Phối hợp tín hiệu hoàn thành khi không cần giữ giá trị

Trong nhiều quy trình, điều quan trọng là biết tất cả công việc đã hoàn tất, chứ không cần thu thập kết quả của từng công việc. Ví dụ, sau khi lưu đơn hàng, hệ thống có thể đồng thời ghi audit, cập nhật chỉ mục tìm kiếm và phát một sự kiện nội bộ. Nếu các thao tác này chỉ trả về tín hiệu hoàn thành, việc ghép chúng thành một tuple dữ liệu là không cần thiết. Reactor cung cấp `Mono.when` và các toán tử liên quan để phối hợp vòng đời của nhiều Publisher mà không phải giữ các giá trị `onNext` làm kết quả tổng hợp.

Bài học thuộc chương **Ghép luồng** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là phối hợp tín hiệu hoàn thành, phân biệt cách chạy đồng thời với tuần tự và lựa chọn chính sách khi một nhánh gặp lỗi.

Sau bài học, bạn có thể:

- Giải thích vì sao `Mono<Void>` biểu diễn hoàn thành mà không có giá trị.
- Dùng `Mono.when` để đợi nhiều Publisher hoàn tất mà không ghép dữ liệu đầu ra.
- Chọn `whenDelayError` khi cần chờ mọi nhánh kết thúc trước khi báo lỗi.
- Dùng `then`, `thenEmpty`, `thenMany` và `thenReturn` để nối các bước sau tín hiệu hoàn thành.
- Phân biệt `when` với `zip` và chọn toán tử theo mục tiêu nghiệp vụ.
- Kiểm thử completion, error, cancellation và thứ tự thực thi bằng `StepVerifier`.

## 1. Khi chỉ cần biết công việc đã xong

Hãy xét một quy trình xử lý đơn hàng. Sau khi nhận lệnh, dịch vụ cần lưu đơn hàng, ghi audit và cập nhật chỉ mục tìm kiếm. Mỗi thao tác có thể trả về `Mono<Void>` vì caller chỉ cần biết thao tác thành công hay thất bại.

```java
Mono<Void> saveOrder(Order order) {
    return orderRepository.save(order).then();
}

Mono<Void> writeAudit(Order order) {
    return auditRepository.append(order).then();
}

Mono<Void> refreshIndex(Order order) {
    return searchIndex.refresh(order.id());
}
```

`Mono<Void>` là một Publisher hoàn tất mà không phát giá trị `onNext`. Nó vẫn có thể kết thúc bình thường bằng `onComplete` hoặc kết thúc bằng `onError`. `Void` ở đây biểu thị rằng không có payload để tiêu thụ; nó không có nghĩa là Publisher không có kết quả về mặt trạng thái.

Nếu ba thao tác cần bắt đầu mà không phụ thuộc kết quả của nhau, ta có thể phối hợp chúng bằng `Mono.when`:

```java
Mono<Void> finalizeOrder(Order order) {
    return Mono.when(
        saveOrder(order),
        writeAudit(order),
        refreshIndex(order)
    );
}
```

Khi subscribe vào `finalizeOrder`, Reactor subscribe các nguồn được truyền vào `when`. Mono kết quả chỉ hoàn tất khi tất cả nguồn hoàn tất thành công. Giá trị phát ra từ các nguồn được bỏ qua; kết quả tổng hợp chỉ là tín hiệu hoàn thành hoặc lỗi.

`when` không tự tạo thread hay ép các nguồn chạy song song trên scheduler riêng. Nó phối hợp các subscription. Nếu mỗi nguồn thực hiện công việc bất đồng bộ hoặc có scheduler riêng, các công việc có thể tiến triển đồng thời. Nếu nguồn thực hiện công việc blocking ngay trên thread subscribe, thao tác subscribe có thể bị chặn. Hãy chọn scheduler phù hợp cho công việc blocking và giữ đúng semantics của từng nguồn.

## 2. `Mono.when`: đợi tất cả nguồn hoàn tất

`Mono.when(Publisher<?>...)` nhận nhiều Publisher, subscribe chúng và tạo một `Mono<Void>` đại diện cho việc tất cả nguồn đã hoàn tất. Dữ liệu `onNext` từ nguồn được bỏ qua; `when` không tạo tuple chứa các giá trị đó.

```java
Mono<Void> completed = Mono.when(
    sendMetrics(),
    writeAuditLog(),
    updateCache()
);
```

Một số đặc điểm quan trọng:

- Mỗi Publisher được subscribe khi `completed` được subscribe.
- Nếu tất cả nguồn hoàn tất bình thường, `completed` phát `onComplete`.
- Nguồn empty được xem là đã hoàn tất thành công; nó không ngăn `when` hoàn tất.
- Nếu một nguồn báo lỗi, `when` kết thúc bằng lỗi và hủy các nguồn còn lại theo chính sách fail-fast.
- Nếu downstream hủy subscription, các subscription nguồn được hủy theo cơ chế cancellation của Reactor.

Ví dụ với các nguồn phát giá trị nhưng chỉ cần chờ chúng kết thúc:

```java
Mono<Void> refreshAll = Mono.when(
    loadCustomers().doOnNext(this::warmCustomerCache),
    loadProducts().doOnNext(this::warmProductCache),
    loadPrices().doOnNext(this::warmPriceCache)
);
```

Các phần tử vẫn được xử lý trong `doOnNext`, nhưng `refreshAll` không phát ra danh sách customer, product hay price. Nó chỉ biểu diễn trạng thái hoàn tất của ba nhánh.

### Không cần giữ các giá trị để ghép tuple

`Mono.zip` phù hợp khi cần giá trị từ mỗi nguồn để tạo một kết quả mới:

```java
Mono<Dashboard> dashboard = Mono.zip(
    loadRevenue(),
    loadActiveUsers(),
    Dashboard::new
);
```

Ngược lại, nếu chỉ cần đợi cả ba thao tác hoàn thành:

```java
Mono<Void> refreshDashboard = Mono.when(
    recalculateRevenue(),
    refreshActiveUsers(),
    clearDashboardCache()
);
```

Đừng dùng `zip` chỉ để chờ các `Mono<Void>`. `Mono<Void>` không phát giá trị `onNext`, nên `zip` không có giá trị từ mỗi nhánh để tạo tuple; tổ hợp có thể hoàn tất empty. `when` được thiết kế cho việc phối hợp completion mà không cần payload.

| Nhu cầu | Toán tử phù hợp | Kết quả |
|---|---|---|
| Cần một giá trị từ mỗi nguồn | `Mono.zip` / `Flux.zip` | Tuple hoặc giá trị được kết hợp. |
| Chỉ cần tất cả nguồn hoàn tất | `Mono.when` | `Mono<Void>`. |
| Cần nối bước B sau khi A hoàn tất | `then` / `thenEmpty` | Publisher của bước tiếp theo. |
| Cần chạy tiếp một luồng nhiều phần tử sau A | `thenMany` | `Flux` của bước tiếp theo. |

## 3. Xử lý lỗi: fail-fast hay đợi tất cả nhánh kết thúc

Trong phối hợp nhiều thao tác, chính sách lỗi cần được chọn rõ. Mặc định, `Mono.when` sử dụng hành vi fail-fast: khi một nguồn báo lỗi, Mono kết quả báo lỗi và các nguồn còn lại bị hủy. Cách này phù hợp khi những công việc còn lại không cần tiếp tục sau khi quy trình đã thất bại.

```java
Mono<Void> updateCustomerViews(Customer customer) {
    return Mono.when(
        updateSearchDocument(customer),
        invalidateCustomerCache(customer.id()),
        publishCustomerChanged(customer)
    );
}
```

Nếu một nhánh thất bại, các nhánh khác có thể nhận cancellation. Điều này không đảm bảo một thao tác bên ngoài đã bắt đầu sẽ được rollback. Với HTTP request, message đã gửi hoặc lệnh ghi đã được database chấp nhận, cancellation ở phía reactive không tự đảo ngược tác động đã xảy ra. Nếu cần tính nguyên tử, hãy dùng transaction hoặc một quy trình bù trừ phù hợp với hệ thống.

### `Mono.whenDelayError`: đợi mọi nhánh kết thúc rồi báo lỗi

Có tình huống bạn muốn cho tất cả nhánh có cơ hội hoàn tất, kể cả khi một hoặc nhiều nhánh lỗi. `Mono.whenDelayError` trì hoãn việc phát lỗi tổng hợp cho đến khi các nguồn đã kết thúc.

```java
Mono<Void> runAllMaintenanceTasks() {
    return Mono.whenDelayError(
        compactDatabase(),
        rebuildSearchIndex(),
        rotateAuditFiles()
    );
}
```

Nếu mọi nguồn thành công, kết quả hoàn tất bình thường. Nếu một hoặc nhiều nguồn lỗi, Reactor đợi các nguồn còn lại kết thúc rồi mới phát lỗi. Khi có nhiều lỗi, chúng có thể được tổng hợp thành một lỗi kết hợp; caller nên kiểm tra nguyên nhân và các lỗi thành phần theo API exception của Reactor.

Sự khác biệt:

| Tình huống | `Mono.when` | `Mono.whenDelayError` |
|---|---|---|
| Tất cả nguồn hoàn tất thành công | Hoàn tất | Hoàn tất |
| Một nguồn lỗi | Báo lỗi sớm và hủy các nguồn còn lại | Ghi nhận lỗi, tiếp tục đợi các nguồn còn lại kết thúc |
| Nhiều nguồn lỗi | Thường chỉ lỗi đầu tiên quyết định việc kết thúc fail-fast | Có thể tổng hợp nhiều lỗi sau khi các nguồn kết thúc |
| Downstream hủy | Hủy các nguồn | Hủy các nguồn |

Chỉ dùng `whenDelayError` khi các nhánh còn lại thực sự nên tiếp tục sau lỗi của một nhánh. Nếu một nhánh phụ thuộc vào kết quả hoặc trạng thái của nhánh khác, việc để chúng tiếp tục có thể không an toàn.

### Phục hồi lỗi trước khi phối hợp

Nếu lỗi của một nhánh có thể được chuyển thành trạng thái thành công theo chính sách nghiệp vụ, hãy xử lý ở nhánh đó trước khi đưa vào `when`:

```java
Mono<Void> refreshViews(Customer customer) {
    Mono<Void> optionalCache = invalidateCache(customer.id())
        .onErrorResume(CacheUnavailableException.class, error -> {
            log.warn("Cache chưa sẵn sàng", error);
            return Mono.empty();
        });

    return Mono.when(
        updateSearchDocument(customer),
        optionalCache,
        publishCustomerChanged(customer)
    );
}
```

Trong ví dụ, lỗi cache được ghi nhận và chuyển thành completion empty; hai nhánh còn lại vẫn được phối hợp. Chỉ phục hồi lỗi khi nghiệp vụ chấp nhận kết quả đó. Không nên dùng `onErrorResume(error -> Mono.empty())` một cách tổng quát vì nó có thể che giấu lỗi nghiêm trọng.

## 4. Nối các bước tuần tự bằng `then`

`then` bỏ qua các giá trị từ Publisher trước và chỉ subscribe Publisher tiếp theo sau khi nguồn trước hoàn tất bình thường. Nó giúp biểu diễn chuỗi thao tác mà kết quả dữ liệu trung gian không cần thiết.

```java
Mono<Void> processOrder(Order order) {
    return validateOrder(order)
        .then(saveOrder(order))
        .then(writeAudit(order))
        .then(refreshIndex(order));
}
```

Thứ tự là validate, save, audit, refresh. Mỗi bước chỉ bắt đầu sau khi bước trước hoàn tất. Nếu `validateOrder` hoặc một bước sau báo lỗi, các bước tiếp theo không được subscribe.

### `thenReturn`: hoàn tất rồi phát một giá trị cố định

Nếu bước trước chỉ trả về tín hiệu hoàn thành nhưng caller cần một giá trị xác nhận, dùng `thenReturn`:

```java
Mono<String> createOrder(Order order) {
    return saveOrder(order)
        .thenReturn(order.id());
}
```

Giá trị `order.id()` được phát sau khi `saveOrder` hoàn tất bình thường. Nếu save lỗi, giá trị không được phát và lỗi tiếp tục truyền xuống.

### `thenEmpty`: nối với một Publisher không có giá trị

`thenEmpty` làm rõ rằng bước tiếp theo cũng chỉ cần hoàn tất:

```java
Mono<Void> completeShipment(Shipment shipment) {
    return reserveCarrier(shipment)
        .thenEmpty(sendDispatchCommand(shipment));
}
```

`sendDispatchCommand` chỉ được subscribe sau khi `reserveCarrier` hoàn tất. Nếu bước đầu empty nhưng hoàn tất bình thường, bước tiếp theo vẫn được chạy; empty là completion thành công, không phải lỗi.

### `thenMany`: nối với một luồng nhiều phần tử

Khi bước sau phát nhiều phần tử, dùng `thenMany`:

```java
Flux<InvoiceLine> invoiceLines(String invoiceId) {
    return authorizeInvoice(invoiceId)
        .thenMany(loadInvoiceLines(invoiceId));
}
```

`loadInvoiceLines` chỉ được subscribe sau khi `authorizeInvoice` hoàn tất. Các giá trị từ Publisher trước bị bỏ qua; các phần tử từ `loadInvoiceLines` trở thành đầu ra của pipeline.

`then`, `thenEmpty`, `thenMany` không tự chạy song song. Chúng thể hiện quan hệ phụ thuộc tuần tự: bước sau đợi completion của bước trước.

## 5. Kết hợp song song và tuần tự trong cùng quy trình

Một quy trình thực tế thường có cả hai loại quan hệ. Ví dụ, sau khi lưu đơn hàng, có thể cập nhật cache và search index đồng thời; chỉ sau khi cả hai hoàn tất mới gửi thông báo.

```java
Mono<Void> completeOrder(Order order) {
    Mono<Void> save = saveOrder(order);

    Mono<Void> updateProjections = Mono.when(
        invalidateOrderCache(order.id()),
        refreshOrderIndex(order.id())
    );

    return save
        .then(updateProjections)
        .then(sendOrderConfirmation(order));
}
```

Pipeline này có ba giai đoạn:

1. `saveOrder` hoàn tất trước.
2. Cache và search index được subscribe trong cùng giai đoạn phối hợp bởi `when`; pipeline đợi cả hai hoàn tất.
3. Chỉ sau đó `sendOrderConfirmation` mới được subscribe.

Nếu một nhánh cập nhật projection lỗi, `when` mặc định fail-fast; thông báo xác nhận không được gửi. Nếu yêu cầu nghiệp vụ là luôn thử cả hai cập nhật projection trước khi báo lỗi, có thể thay `when` bằng `whenDelayError`.

Sơ đồ luồng:

```text
          saveOrder
              |
          onComplete
              |
        +-----+-----+
        |           |
 invalidateCache  refreshIndex
        |           |
        +-----+-----+
              |
       cả hai hoàn tất
              |
      sendConfirmation
              |
          onComplete
```

Điều phối completion không có nghĩa các thao tác độc lập đã được đảm bảo chạy trên hai thread riêng. Nếu cần concurrency thực sự cho các công việc blocking, hãy đưa từng nhánh lên scheduler phù hợp. Với I/O reactive non-blocking, các nhánh có thể cùng tiến triển mà không cần một thread riêng cho mỗi nhánh.

## 6. Nguồn rỗng, nguồn lỗi và nguồn không kết thúc trong `when`

Các nguồn tham gia `when` vẫn giữ semantics Reactive Streams riêng:

- **Empty:** được xem là hoàn tất thành công. `Mono.when(Mono.empty(), task())` vẫn đợi `task()`.
- **Error:** với `when`, lỗi làm kết quả lỗi sớm và các nhánh còn lại bị hủy; với `whenDelayError`, lỗi được trì hoãn cho đến khi các nhánh kết thúc.
- **Never:** không phát tín hiệu và không hoàn tất, nên `when` sẽ chờ nhánh đó mãi nếu không có timeout hoặc cancellation bên ngoài.

Ví dụ giới hạn thời gian cho toàn bộ nhóm thao tác:

```java
Mono<Void> boundedRefresh = Mono.when(
    refreshCatalog(),
    refreshPricing(),
    refreshRecommendations()
).timeout(Duration.ofSeconds(10));
```

Nếu cả nhóm không hoàn tất trong thời hạn, `timeout` phát lỗi timeout và hủy subscription upstream. Đây là giới hạn thời gian cho cả nhóm, không phải timeout độc lập cho từng nhánh. Nếu cần từng nhánh có deadline riêng, hãy đặt timeout trong từng Publisher trước khi đưa vào `when`.

```java
Mono<Void> boundedEach = Mono.when(
    refreshCatalog().timeout(Duration.ofSeconds(4)),
    refreshPricing().timeout(Duration.ofSeconds(6)),
    refreshRecommendations().timeout(Duration.ofSeconds(8))
);
```

Khi một nhánh timeout trong `when`, hành vi mặc định là fail-fast và các nhánh còn lại có thể bị hủy. Nếu dùng `whenDelayError`, timeout của một nhánh được ghi nhận như lỗi và các nhánh còn lại được đợi kết thúc.

## 7. Kiểm thử phối hợp completion với StepVerifier

`StepVerifier` cho phép xác nhận tín hiệu đầu cuối mà không cần nhận payload.

### Đợi nhiều nguồn hoàn tất

```java
StepVerifier.create(Mono.when(
        Mono.delay(Duration.ofMillis(20)).then(),
        Mono.delay(Duration.ofMillis(40)).then()
    ))
    .verifyComplete();
```

Kết quả chỉ hoàn tất sau nhánh chậm hơn. Không có giá trị nào được phát ra từ `Mono.when`.

### Lỗi fail-fast

```java
StepVerifier.create(Mono.when(
        Mono.delay(Duration.ofMillis(20)).then(),
        Mono.delay(Duration.ofMillis(10))
            .then(Mono.error(new IllegalStateException("failed")))
    ))
    .expectErrorMessage("failed")
    .verify();
```

Kiểm thử xác nhận lỗi được truyền đến subscriber. Có thể bổ sung `doOnCancel` ở nhánh còn lại để xác minh cancellation nếu cần kiểm tra chính sách hủy.

### Nối tuần tự bằng `then`

```java
AtomicInteger order = new AtomicInteger();

Mono<Void> first = Mono.fromRunnable(() -> order.compareAndSet(0, 1));
Mono<Void> second = Mono.fromRunnable(() -> order.compareAndSet(1, 2));

StepVerifier.create(first.then(second))
    .verifyComplete();

assertThat(order.get()).isEqualTo(2);
```

Ví dụ dùng một trạng thái đơn giản để minh họa bước thứ hai chỉ chạy sau khi bước thứ nhất hoàn tất. Trong kiểm thử thực tế, có thể dùng mock hoặc `PublisherProbe` để xác nhận Publisher tiếp theo được subscribe đúng thời điểm.

### Kiểm thử `whenDelayError`

```java
StepVerifier.create(Mono.whenDelayError(
        Mono.delay(Duration.ofMillis(10))
            .then(Mono.error(new IllegalStateException("first"))),
        Mono.delay(Duration.ofMillis(30)).then()
    ))
    .expectError()
    .verify();
```

Nhánh thứ hai vẫn có thời gian hoàn tất trước khi lỗi tổng hợp được phát. Nếu cần xác minh lỗi thành phần, hãy kiểm tra loại exception và danh sách nguyên nhân theo phiên bản Reactor đang dùng.

### Kiểm thử timeout cho một nhóm

```java
StepVerifier.withVirtualTime(() ->
        Mono.when(Mono.never())
            .timeout(Duration.ofSeconds(5))
    )
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify();
```

Virtual time giúp xác minh deadline mà không phải chờ thời gian thực. Hãy tạo pipeline bên trong supplier của `withVirtualTime` để scheduler ảo được áp dụng đúng lúc.

## 8. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `zip` cho nhiều `Mono<Void>` | Các nguồn không phát giá trị để tạo tuple; tổ hợp có thể empty. | Dùng `Mono.when` để phối hợp completion. |
| Nghĩ `when` trả về giá trị của nguồn | Các giá trị `onNext` bị bỏ qua; kết quả là `Mono<Void>`. | Dùng `zip` nếu cần kết quả dữ liệu. |
| Nghĩ `when` tự tạo thread cho mỗi nhánh | Blocking source có thể chặn thread subscribe. | Điều phối blocking bằng scheduler phù hợp. |
| Dùng `when` nhưng mong mọi nhánh tiếp tục sau lỗi | Fail-fast có thể hủy các nhánh còn lại. | Dùng `whenDelayError` khi cần đợi mọi nhánh kết thúc. |
| Dùng `whenDelayError` cho các nhánh không nên tiếp tục sau lỗi | Công việc phụ thuộc có thể vẫn chạy khi trạng thái đã thất bại. | Xác định dependency và chọn fail-fast hoặc xử lý lỗi theo từng nhánh. |
| Dùng `then` khi cần giữ giá trị upstream | `then` bỏ qua giá trị của nguồn trước. | Dùng `flatMap` hoặc `zip` nếu bước sau cần dữ liệu đó. |
| Nghĩ empty là lỗi nên bước `then` không chạy | Empty là completion bình thường, nên bước tiếp theo vẫn được subscribe. | Dùng `switchIfEmpty` nếu cần nhánh riêng cho empty. |
| Không đặt timeout cho nhánh có thể never | `when` hoặc chuỗi `then` có thể chờ vô hạn. | Đặt timeout theo deadline của nhóm hoặc từng nhánh. |

## 9. Checklist chọn toán tử

Trước khi ghép các Publisher, hãy xác định:

- Có cần giá trị từ từng nguồn hay chỉ cần biết chúng hoàn tất?
- Các thao tác độc lập có thể được subscribe trong cùng giai đoạn không?
- Bước tiếp theo có phụ thuộc completion của bước trước không?
- Khi một nhánh lỗi, các nhánh khác nên bị hủy hay tiếp tục đến khi kết thúc?
- Có nhánh nào có thể empty hoặc never không?
- Cần deadline chung cho nhóm hay deadline riêng cho từng nhánh?
- Cancellation có dừng được công việc bên ngoài hay cần cơ chế bù trừ/transaction?
- Kiểm thử đã xác nhận completion, error, cancellation và thứ tự subscribe chưa?

Khi phối hợp đúng tín hiệu hoàn thành, pipeline reactive có thể điều khiển các thao tác độc lập và các bước phụ thuộc một cách rõ ràng mà không phải tạo tuple hoặc giữ payload không cần thiết. `when` phù hợp để đợi nhiều nguồn, `whenDelayError` phù hợp khi cần thu thập kết quả lỗi sau khi mọi nhánh kết thúc, còn `then` và các biến thể giúp nối các bước theo thứ tự completion.
