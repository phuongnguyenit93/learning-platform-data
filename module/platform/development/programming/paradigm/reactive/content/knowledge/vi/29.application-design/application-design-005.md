# Lựa chọn toán tử theo thứ tự, số lượng, thời gian và nhu cầu

Một pipeline Reactor thường có nhiều cách biểu diễn cùng một luồng dữ liệu. Chọn toán tử chỉ vì tên gọi quen thuộc có thể làm thay đổi thứ tự kết quả, số phần tử được phát, thời gian chờ hoặc lượng công việc mà upstream phải thực hiện. Khi thiết kế ứng dụng reactive, hãy bắt đầu từ hợp đồng mà consumer cần: cần bao nhiêu kết quả, có yêu cầu giữ thứ tự không, thời gian nào được phép chờ và downstream có thể tiêu thụ với tốc độ nào.

Trong hệ sinh thái Java, `Mono` biểu diễn tối đa một kết quả còn `Flux` biểu diễn từ không đến nhiều kết quả. Các toán tử của Reactor cho phép kết hợp hai kiểu này thành pipeline bất đồng bộ. Việc lựa chọn đúng toán tử giúp hệ thống tận dụng backpressure, giới hạn tài nguyên, xử lý thời gian và giữ semantics rõ ràng từ service đến API.

## 1. Bốn câu hỏi trước khi chọn toán tử

Trước khi viết pipeline, hãy trả lời bốn câu hỏi:

1. **Thứ tự:** kết quả có phải giữ thứ tự đầu vào, hay có thể phát theo thứ tự hoàn tất?
2. **Số lượng:** cần một kết quả, tối đa N kết quả, toàn bộ kết quả hay một nhóm kết quả?
3. **Thời gian:** cần timeout, trì hoãn, lấy mẫu, gom theo cửa sổ hay phát định kỳ?
4. **Nhu cầu:** downstream yêu cầu dữ liệu theo từng đợt hay nguồn có thể phát nhanh hơn consumer?

Các câu hỏi này liên quan với nhau. Ví dụ, `flatMap` tăng concurrency và có thể làm kết quả đến không theo thứ tự; `take(n)` giới hạn số phần tử và hủy upstream khi đã đủ; `bufferTimeout` gom phần tử theo cả kích thước lẫn thời gian; `limitRate` điều tiết cách request được truyền upstream.

## 2. Chọn Mono hay Flux theo cardinality

Cardinality là số lượng kết quả mà publisher có thể phát. Hãy chọn kiểu trả về theo hợp đồng của thao tác:

| Nhu cầu | Kiểu phù hợp | Ví dụ |
| --- | --- | --- |
| Tối đa một kết quả | `Mono<T>` | Tìm một order theo ID |
| Không hoặc một kết quả | `Mono<T>` | Tìm profile có thể không tồn tại |
| Nhiều kết quả | `Flux<T>` | Đọc danh sách order hoặc event stream |
| Chỉ quan tâm hoàn tất/lỗi | `Mono<Void>` | Lưu audit record hoặc gửi một command |

Ví dụ tìm một đơn hàng:

~~~java
Mono<Order> findOrder(String id) {
    return orderRepository.findById(id);
}
~~~

Repository có thể phát một order rồi complete, complete rỗng nếu không tìm thấy hoặc phát lỗi. `Mono<Order>` diễn tả đúng ba khả năng đó.

Ví dụ đọc nhiều đơn hàng:

~~~java
Flux<Order> findOrdersByCustomer(String customerId) {
    return orderRepository.findByCustomerId(customerId);
}
~~~

Không chuyển `Flux` thành `Mono` chỉ để tiện gọi `block()`. Việc chuyển đổi phải thể hiện rõ chính sách với các phần tử còn lại.

### Các toán tử chuyển cardinality

| Toán tử | Kết quả | Hành vi |
| --- | --- | --- |
| `next()` | `Mono<T>` | Lấy phần tử đầu tiên; complete rỗng nếu nguồn không có phần tử và hủy phần còn lại |
| `single()` | `Mono<T>` | Yêu cầu chính xác một phần tử; lỗi nếu nguồn rỗng hoặc có hơn một phần tử |
| `singleOrEmpty()` | `Mono<T>` | Cho phép không hoặc một phần tử; lỗi nếu có hơn một phần tử |
| `collectList()` | `Mono<List<T>>` | Gom tất cả phần tử vào một List rồi phát một lần |
| `count()` | `Mono<Long>` | Đếm số phần tử rồi phát tổng |
| `then()` | `Mono<Void>` | Bỏ các giá trị, chỉ giữ completion hoặc error |
| `thenReturn(value)` | `Mono<R>` | Bỏ giá trị nguồn và phát một giá trị sau khi nguồn complete |

Ví dụ:

~~~java
Mono<Order> firstOrder = orderRepository.findAll()
    .filter(Order::isReady)
    .next();

Mono<Order> exactlyOneOrder = orderRepository.findByExternalId(externalId)
    .single();

Mono<List<Order>> allOrders = orderRepository.findByCustomerId(customerId)
    .collectList();
~~~

`next()` phù hợp khi chỉ cần phần tử đầu tiên. `single()` phù hợp khi nhiều hơn một kết quả là vi phạm hợp đồng và cần được phát hiện. `collectList()` phù hợp với tập dữ liệu hữu hạn, có giới hạn. Nếu nguồn có thể phát vô hạn hoặc rất lớn, gom toàn bộ vào List có thể làm cạn bộ nhớ; hãy dùng pagination, `buffer` có giới hạn hoặc xử lý từng phần tử.

`Mono.from(publisher)` cũng lấy tối đa một phần tử và hủy phần còn lại. Nó không xác minh nguồn chỉ có đúng một phần tử. Khi cần xác minh cardinality, dùng `single()` hoặc `singleOrEmpty()` theo hợp đồng mong muốn.

## 3. Giữ thứ tự hay ưu tiên concurrency?

Các toán tử biến đổi đơn giản như `map` và `filter` giữ thứ tự tín hiệu đầu vào. Khi mỗi phần tử cần gọi một publisher bất đồng bộ, lựa chọn giữa `concatMap`, `flatMap` và `flatMapSequential` quyết định quan hệ giữa thứ tự và concurrency.

| Toán tử | Chạy publisher con | Thứ tự phát kết quả | Đánh đổi |
| --- | --- | --- | --- |
| `concatMap` | Tuần tự, chờ publisher con trước hoàn tất | Theo thứ tự đầu vào | Dễ kiểm soát thứ tự nhưng giảm concurrency |
| `flatMap` | Có thể chạy đồng thời | Theo thứ tự publisher con phát kết quả | Throughput cao hơn nhưng kết quả có thể xen kẽ |
| `flatMapSequential` | Subscribe publisher con đồng thời | Theo thứ tự đầu vào | Giữ thứ tự nhưng có thể phải đệm kết quả đã hoàn tất sớm |

### Dùng concatMap khi thứ tự là yêu cầu nghiệp vụ

~~~java
Flux<Receipt> receipts = orderEvents.concatMap(event ->
    receiptService.createReceipt(event)
);
~~~

Publisher con cho event sau chỉ được xử lý tiếp sau khi publisher con trước hoàn tất. Cách này hữu ích khi các thao tác phụ thuộc thứ tự, ví dụ cập nhật cùng một aggregate hoặc ghi tuần tự các bước của một quy trình.

### Dùng flatMap khi các phần tử độc lập

~~~java
Flux<Profile> profiles = userIds.flatMap(
    profileClient::fetchProfile,
    16
);
~~~

Tham số concurrency giới hạn số publisher con được subscribe đồng thời. Kết quả có thể đến theo thứ tự hoàn tất request, không nhất thiết theo thứ tự `userIds`. Đây là lựa chọn phù hợp khi các request độc lập và consumer không cần giữ thứ tự.

### Dùng flatMapSequential khi cần cả concurrency và thứ tự

~~~java
Flux<EnrichedOrder> enriched = orderIds.flatMapSequential(
    orderClient::fetchAndEnrich,
    8
);
~~~

Các publisher con có thể được thực thi đồng thời, nhưng kết quả được phát theo thứ tự nguồn. Nếu publisher con đầu tiên chậm trong khi các publisher sau đã hoàn tất, kết quả sau phải chờ trong hàng đợi. Do đó, giữ thứ tự có thể làm tăng bộ nhớ và độ trễ quan sát được.

### Ghép nhiều nguồn: concat, merge, zip và combineLatest

| Toán tử | Cách kết hợp | Dùng khi |
| --- | --- | --- |
| `concat` | Đăng ký nguồn lần lượt, phát hết nguồn trước rồi mới đến nguồn sau | Cần thứ tự theo từng nguồn |
| `merge` | Đăng ký các nguồn và phát tín hiệu khi chúng đến | Các nguồn độc lập, thứ tự xen kẽ chấp nhận được |
| `zip` | Ghép phần tử thứ N của mỗi nguồn thành một tuple | Cần một tập giá trị tương ứng theo vị trí |
| `combineLatest` | Sau khi mỗi nguồn có ít nhất một giá trị, phát tổ hợp mới mỗi khi một nguồn cập nhật | Cần trạng thái mới nhất của nhiều nguồn |

Ví dụ `zip` ghép thông tin hồ sơ và cấu hình:

~~~java
Mono<AccountView> accountView = Mono.zip(
        accountClient.findAccount(accountId),
        preferenceClient.findPreferences(accountId)
    )
    .map(tuple -> new AccountView(tuple.getT1(), tuple.getT2()));
~~~

`zip` cần các nguồn cung cấp giá trị để tạo tuple. Nếu một nguồn complete rỗng, không thể tạo tuple tương ứng và kết quả có thể complete rỗng. Không dùng `zip` khi ý nghĩa nghiệp vụ là “lấy giá trị mới nhất” hoặc “chờ mọi nguồn phát hết”; hãy chọn `combineLatest` hay `concat` nếu semantics phù hợp hơn.

## 4. Giới hạn số lượng phần tử

Các toán tử giới hạn số lượng giúp kiểm soát payload, thời gian xử lý và lượng dữ liệu downstream phải tiêu thụ.

| Toán tử | Ý nghĩa |
| --- | --- |
| `take(n)` | Chỉ phát tối đa n phần tử đầu tiên rồi complete downstream và hủy upstream |
| `skip(n)` | Bỏ n phần tử đầu tiên |
| `takeWhile(predicate)` | Phát phần tử khi điều kiện còn đúng; dừng khi gặp phần tử đầu tiên không thỏa |
| `takeUntil(predicate)` | Phát cả phần tử đầu tiên thỏa điều kiện dừng rồi hoàn tất |
| `distinct()` | Chỉ phát giá trị chưa từng xuất hiện theo equality |
| `distinctUntilChanged()` | Loại bỏ giá trị liên tiếp trùng nhau |
| `limitRate(n)` | Điều tiết các request upstream theo từng đợt; không giới hạn tổng số phần tử |

Ví dụ API chỉ trả tối đa 20 kết quả:

~~~java
Flux<SearchResult> search(String query) {
    return searchRepository.search(query)
        .take(20);
}
~~~

`take(20)` giới hạn số kết quả được phát cho consumer. Khi đủ 20 phần tử, upstream nhận cancellation. Nếu nguồn đã thực hiện side effect hoặc gọi I/O không hỗ trợ cancel, công việc bên dưới có thể vẫn tiếp tục; cần hiểu khả năng cancellation của adapter.

`distinct()` có thể phải giữ tập giá trị đã thấy để phát hiện trùng. Với stream dài hạn có cardinality lớn, bộ nhớ của tập này có thể tăng liên tục. `distinctUntilChanged()` chỉ cần so sánh với giá trị liền trước, phù hợp hơn khi chỉ muốn loại bỏ các cập nhật liên tiếp giống nhau.

## 5. Gom phần tử theo kích thước hoặc thời gian

`buffer` và `window` đều nhóm phần tử, nhưng cách phát nhóm khác nhau:

- `buffer` gom phần tử vào collection, sau đó phát collection.
- `window` phát một publisher con đại diện cho nhóm phần tử.

Ví dụ gom tối đa 100 event hoặc hết một giây:

~~~java
Flux<List<Event>> batches = eventSource.events()
    .bufferTimeout(100, Duration.ofSeconds(1));
~~~

Mỗi batch được phát khi đủ 100 phần tử hoặc khi cửa sổ thời gian kết thúc. `bufferTimeout` hữu ích khi gửi batch đến một hệ thống đích có chi phí mỗi lần gọi cao. Tuy nhiên, kích thước batch, số batch đang chờ và tốc độ xử lý downstream vẫn cần được giới hạn.

Nếu cần xử lý từng phần tử trong nhóm mà không tạo một List lớn:

~~~java
Flux<Flux<Event>> windows = eventSource.events()
    .windowTimeout(100, Duration.ofSeconds(1));

Flux<ProcessedEvent> processed = windows.concatMap(window ->
    window.concatMap(event -> processor.process(event))
);
~~~

`windowTimeout` phát các Flux con. Consumer phải subscribe và tiêu thụ các window đó; trong ví dụ, `concatMap` xử lý tuần tự từng window và từng event trong window. Nếu xử lý đồng thời, hãy giới hạn concurrency và đánh giá áp lực lên connection pool hoặc dịch vụ đích.

## 6. Chọn toán tử theo thời gian

Toán tử thời gian phục vụ các nhu cầu khác nhau. Không nên thay thế chúng cho nhau chỉ vì đều nhận `Duration`.

| Toán tử | Hành vi | Trường hợp phù hợp |
| --- | --- | --- |
| `delayElements(duration)` | Trì hoãn từng phần tử trước khi phát | Làm chậm nhịp phát hoặc mô phỏng độ trễ |
| `timeout(duration)` | Phát lỗi nếu không nhận được tín hiệu trong khoảng thời gian cho phép; có thể dùng fallback | Giới hạn thời gian chờ |
| `interval(duration)` | Phát số tăng dần theo chu kỳ | Polling hoặc phát tick định kỳ |
| `elapsed()` | Phát cặp thời gian đã trôi qua và phần tử | Đo khoảng cách giữa các tín hiệu |
| `timestamp()` | Gắn timestamp với phần tử | Ghi nhận thời điểm phát |
| `sample(duration)` | Định kỳ phát giá trị mới nhất đã nhận | Snapshot trạng thái có tần suất cao |
| `sampleTimeout(factory)` | Chỉ phát phần tử nếu publisher thời gian của nó hoàn tất trước khi phần tử mới thay thế | Debounce, ví dụ chờ người dùng ngừng nhập |

### Timeout là giới hạn chờ, không phải trì hoãn

~~~java
Mono<Product> product = productClient.find(productId)
    .timeout(Duration.ofSeconds(2));
~~~

Nếu nguồn không phát tín hiệu trong khoảng thời gian được cấu hình, `timeout` phát `TimeoutException` và yêu cầu hủy upstream. Có thể cung cấp fallback:

~~~java
Mono<Product> product = productClient.find(productId)
    .timeout(
        Duration.ofSeconds(2),
        productCache.find(productId)
    );
~~~

Với `Flux`, timeout được áp dụng cho khoảng chờ tín hiệu tiếp theo, không đơn giản là tổng thời lượng của toàn bộ stream. Nếu cần giới hạn tổng thời gian, hãy thiết kế một deadline ở ranh giới request hoặc dùng cơ chế timeout phù hợp với toàn bộ thao tác.

### Debounce cho luồng thay đổi liên tục

Trong Reactor, `sampleTimeout` có thể dùng để giữ giá trị cuối cùng sau một khoảng yên lặng:

~~~java
Flux<String> searchQueries = queryChanges
    .map(String::trim)
    .filter(query -> !query.isBlank())
    .sampleTimeout(query ->
        Mono.delay(Duration.ofMillis(300))
    );
~~~

Nếu một query mới đến trước khi timer của query trước phát tín hiệu, query trước bị bỏ. Khi người dùng dừng nhập đủ lâu, query cuối cùng được phát. Đây là cách giảm số lần gọi tìm kiếm trong UI. Không dùng debounce cho event cần xử lý đầy đủ, như giao dịch, audit event hoặc message cần bảo đảm không mất.

### Sample để lấy snapshot định kỳ

~~~java
Flux<MetricSnapshot> snapshots = liveMetrics
    .sample(Duration.ofSeconds(5));
~~~

`sample` phát giá trị mới nhất ở mỗi chu kỳ. Các giá trị trung gian có thể không được phát; nó phù hợp với dashboard trạng thái hiện tại nhưng không phù hợp với luồng cần giữ toàn bộ biến động.

## 7. Phân biệt demand với giới hạn số lượng

Trong Reactive Streams, subscriber gửi `request(n)` để báo số phần tử có thể nhận. Demand là tín hiệu điều khiển luồng, không phải yêu cầu lấy tổng cộng n phần tử rồi kết thúc.

Ví dụ, một subscriber có thể request 10 phần tử, nhận đủ 10, rồi request thêm 10. Publisher có thể tiếp tục phát trong toàn bộ vòng đời subscription.

`limitRate(n)` định hình các request được truyền upstream thành các đợt nhỏ hơn. Nó giúp tránh một downstream request quá lớn ngay lập tức khiến nguồn phải chuẩn bị lượng dữ liệu lớn. `limitRate` không đặt giới hạn tổng số phần tử và cũng không thay thế `take(n)`.

~~~java
Flux<Event> controlled = eventSource.events()
    .limitRate(64);
~~~

Nếu downstream yêu cầu nhiều phần tử, Reactor chia demand upstream thành các đợt theo cấu hình `limitRate`. Chọn kích thước dựa trên throughput, độ trễ và khả năng của nguồn; giá trị nhỏ có thể làm tăng số lần request và giảm throughput.

### Backpressure strategy khi nguồn không thể chờ demand

Một số nguồn nóng hoặc callback API có thể phát dữ liệu theo tốc độ riêng. Khi nguồn không thể điều chỉnh theo demand, cần xác định cách xử lý phần tử đến lúc downstream chưa sẵn sàng:

| Toán tử | Hành vi khi downstream thiếu demand | Rủi ro/đánh đổi |
| --- | --- | --- |
| `onBackpressureBuffer()` | Đệm phần tử chờ consumer | Buffer có thể tăng bộ nhớ nếu producer luôn nhanh hơn consumer |
| `onBackpressureDrop()` | Bỏ phần tử đến trong lúc không có demand | Mất dữ liệu; chỉ phù hợp khi nghiệp vụ cho phép |
| `onBackpressureLatest()` | Giữ phần tử mới nhất và thay giá trị đang chờ | Bỏ qua các giá trị trung gian |
| `onBackpressureError()` | Phát lỗi khi không thể đáp ứng demand | Quá tải trở thành lỗi rõ ràng cần xử lý |

Ví dụ giới hạn buffer:

~~~java
Flux<SensorEvent> events = sensorSource.events()
    .onBackpressureBuffer(1_000);
~~~

Overload giới hạn kích thước buffer có thể phát lỗi overflow khi vượt giới hạn. Hãy xác minh chính sách overflow và bổ sung metric/cảnh báo nếu dữ liệu có giá trị cao. Một buffer hữu hạn giúp giới hạn bộ nhớ nhưng không làm producer chậm lại.

Ví dụ bỏ dữ liệu cũ và giữ trạng thái mới nhất:

~~~java
Flux<DeviceStatus> latestStatus = deviceStatusSource
    .onBackpressureLatest();
~~~

Cách này phù hợp khi consumer chỉ cần trạng thái hiện tại của thiết bị. Nếu cần lịch sử mọi lần đổi trạng thái, phải dùng buffer có giới hạn, durable queue hoặc một cơ chế lưu trữ khác.

`onBackpressureBuffer`, `onBackpressureDrop` và `onBackpressureLatest` thường yêu cầu upstream phát nhanh theo khả năng của nguồn và xử lý phần tử ở phía operator. Chúng là chính sách khi downstream chưa có demand; chúng không tự tạo ra một nguồn có thể backpressure.

## 8. Kết hợp thứ tự, số lượng, thời gian và demand trong một pipeline

Giả sử một màn hình tìm kiếm nhận chuỗi query do người dùng nhập. Ứng dụng muốn:

- Bỏ query rỗng.
- Chờ người dùng ngừng nhập 300 ms.
- Chỉ giữ kết quả của query mới nhất.
- Giới hạn thời gian chờ dịch vụ tìm kiếm.
- Không phát quá 50 kết quả cho mỗi luồng hiển thị.
- Điều tiết demand downstream theo từng đợt.

~~~java
Flux<SearchResult> results = queryChanges
    .map(String::trim)
    .filter(query -> !query.isBlank())
    .sampleTimeout(query ->
        Mono.delay(Duration.ofMillis(300))
    )
    .distinctUntilChanged()
    .switchMap(query ->
        searchClient.search(query)
            .timeout(Duration.ofSeconds(2))
            .onErrorResume(
                TimeoutException.class,
                error -> Flux.empty()
            )
    )
    .take(50)
    .limitRate(32);
~~~

Ở đây, `sampleTimeout` giảm số lần gọi khi người dùng đang nhập; `switchMap` hủy publisher tìm kiếm cũ khi query mới được phát; `timeout` giới hạn khoảng chờ kết quả; `take(50)` giới hạn số phần tử đầu ra; `limitRate(32)` điều tiết request upstream. Mỗi toán tử giải quyết một yêu cầu khác nhau.

Nếu dịch vụ tìm kiếm cần trả kết quả theo thứ tự query đầu vào hoặc phải xử lý mọi query, `switchMap` không phù hợp vì nó hủy publisher con cũ. Khi đó cần `concatMap` hoặc `flatMap` với concurrency được chọn theo yêu cầu.

## 9. Bảng quyết định nhanh

| Câu hỏi thiết kế | Toán tử thường phù hợp | Cần kiểm tra |
| --- | --- | --- |
| Chỉ cần phần tử đầu tiên? | `next()` hoặc `take(1)` | Nguồn có được hủy sau phần tử đầu không |
| Phải có đúng một phần tử? | `single()` | Empty và nhiều hơn một phần tử đều là lỗi |
| Xử lý tuần tự, giữ thứ tự? | `concatMap` | Throughput và thời gian chờ publisher con |
| Xử lý đồng thời, không cần thứ tự? | `flatMap` | Giới hạn concurrency và interleaving |
| Xử lý đồng thời nhưng giữ thứ tự? | `flatMapSequential` | Buffer và độ trễ khi publisher đầu chậm |
| Ghép giá trị tương ứng từ nhiều nguồn? | `zip` | Nguồn empty hoặc tốc độ phát khác nhau |
| Chỉ giữ trạng thái mới nhất? | `combineLatest` hoặc `sample` tùy nhu cầu | Cần chờ mỗi nguồn phát giá trị đầu tiên không |
| Giới hạn tổng số phần tử? | `take(n)` | Cancellation upstream |
| Gom theo số lượng hoặc thời gian? | `bufferTimeout` / `windowTimeout` | Kích thước batch và concurrency xử lý |
| Giới hạn thời gian chờ tín hiệu? | `timeout` | Timeout giữa tín hiệu hay deadline toàn request |
| Chờ người dùng ngừng thay đổi? | `sampleTimeout` | Không dùng nếu phải giữ mọi event |
| Điều tiết demand upstream? | `limitRate` | Không phải giới hạn tổng số phần tử |
| Nguồn không backpressure được? | `onBackpressureBuffer/Drop/Latest/Error` | Chính sách mất dữ liệu và giới hạn bộ nhớ |

## 10. Các lỗi thiết kế thường gặp

- **Dùng `flatMap` rồi giả định thứ tự đầu vào:** publisher con có thể hoàn tất theo thứ tự khác; dùng `concatMap` hoặc `flatMapSequential` nếu thứ tự quan trọng.
- **Dùng `concatMap` cho tác vụ độc lập có thể chạy đồng thời:** pipeline có thể giảm throughput không cần thiết.
- **Dùng `collectList()` cho stream lớn hoặc vô hạn:** toàn bộ phần tử được giữ trong bộ nhớ cho đến khi nguồn complete.
- **Dùng `next()` khi cần xác minh đúng một phần tử:** `next()` chỉ lấy phần tử đầu; dùng `single()` nếu nhiều kết quả là lỗi.
- **Nhầm `limitRate` với `take`:** `limitRate` điều tiết request, `take` giới hạn tổng số phần tử.
- **Dùng `onBackpressureBuffer()` không giới hạn:** producer nhanh hơn consumer có thể làm heap tăng liên tục.
- **Dùng `onBackpressureLatest()` cho event cần kiểm toán:** các giá trị trung gian có thể bị thay thế.
- **Dùng `sampleTimeout` cho command cần xử lý đầy đủ:** các phần tử trước có thể bị bỏ khi phần tử mới đến.
- **Dùng `timeout` như giới hạn tổng thời gian của Flux:** timeout thường đo khoảng chờ tín hiệu; deadline tổng cần được thiết kế riêng.
- **Gom transaction hoặc connection quanh Flux sống lâu:** tài nguyên có thể bị giữ trong thời gian dài.
- **Không giới hạn concurrency của `flatMap`:** nhiều request I/O đồng thời có thể làm cạn pool hoặc gây quá tải dịch vụ đích.
- **Dựa vào operator để sửa nguồn không tuân thủ hợp đồng:** cần kiểm tra adapter và publisher ở ranh giới nguồn.

## 11. Kiểm thử quyết định chọn toán tử

`StepVerifier` giúp xác minh dữ liệu và terminal signal. Với thứ tự, hãy viết expectation theo đúng thứ tự cần bảo đảm:

~~~java
StepVerifier.create(
        Flux.just("A", "B", "C")
            .concatMap(value -> Mono.just(value + "-done"))
    )
    .expectNext("A-done", "B-done", "C-done")
    .verifyComplete();
~~~

Với giới hạn số lượng và cancellation:

~~~java
StepVerifier.create(Flux.range(1, 100), 0)
    .thenRequest(3)
    .expectNext(1, 2, 3)
    .thenCancel()
    .verify();
~~~

Với thời gian, dùng virtual time để không phải chờ đồng hồ thật:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(3)
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

Khi test publisher có timer, tạo publisher bên trong supplier của `withVirtualTime` để scheduler ảo được cài trước khi publisher lắp ráp. Nếu cần xác minh demand, dùng `StepVerifier.create(publisher, 0)` và `thenRequest(n)`. Nếu cần xác minh I/O thật sự bị hủy, phải kiểm tra adapter hoặc driver; `thenCancel()` chỉ xác nhận subscriber đã gửi yêu cầu hủy.

## 12. Quy trình lựa chọn toán tử trong code review

Khi review một pipeline, đọc từ nguồn đến consumer và đánh dấu:

1. Cardinality đầu vào và đầu ra: `Mono`, `Flux`, empty hay nhiều phần tử?
2. Operator nào có thể thay đổi số lượng hoặc hủy upstream?
3. Các publisher con có độc lập không; concurrency có giới hạn không?
4. Thứ tự kết quả có được đảm bảo hay chỉ tình cờ đúng trong test?
5. Có gom toàn bộ dữ liệu vào bộ nhớ không?
6. Timeout đo khoảng chờ giữa tín hiệu hay deadline tổng?
7. Có operator nào bỏ dữ liệu như `sample`, `sampleTimeout`, `drop` hoặc `latest` không?
8. Demand được truyền thế nào; nguồn có hỗ trợ backpressure không?
9. Cancellation có được truyền đến client/driver và giải phóng resource không?
10. Test có xác minh đúng hợp đồng dữ liệu, thứ tự, số lượng, thời gian và terminal signal không?

Chọn toán tử theo hợp đồng của consumer giúp pipeline dễ dự đoán và dễ vận hành. Dùng `Mono`/`Flux` để biểu đạt cardinality; `concatMap`, `flatMap` hoặc `flatMapSequential` để chọn thứ tự và concurrency; `take`, `single`, `collectList` hoặc `bufferTimeout` để kiểm soát số lượng; các toán tử thời gian để giới hạn chờ hoặc gom tín hiệu; `limitRate` và backpressure strategy để quản lý chênh lệch tốc độ. Không có toán tử nào phù hợp cho mọi trường hợp. Hãy nêu rõ dữ liệu có được phép bỏ, thứ tự nào được bảo đảm, bộ nhớ tối đa là bao nhiêu và điều gì xảy ra khi downstream hủy; sau đó kiểm thử chính các cam kết đó bằng `StepVerifier`.
