# Ngân sách thời gian chờ và chuỗi lời gọi nhiều tầng

Trong module `REACTIVE_PROGRAMMING`, ta xây dựng các luồng sự kiện bất đồng bộ theo hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams, đồng thời thực hành `Mono`, `Flux`, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi một HTTP request đi qua nhiều service, gateway, database hoặc API bên ngoài, mỗi tầng đều tiêu thụ một phần thời gian. Nếu từng tầng tự đặt timeout độc lập mà không xét thời gian đã dùng, tổng thời gian có thể vượt quá thời hạn mà client chấp nhận.

**Ngân sách thời gian chờ** (*timeout budget*) là tổng thời gian tối đa dành cho một thao tác nghiệp vụ, tính từ lúc request bắt đầu đến khi kết quả cần được trả về. Một **deadline** là thời điểm tuyệt đối mà thao tác phải hoàn tất. Mỗi tầng nhận biết deadline chung, tính thời gian còn lại rồi áp dụng giới hạn riêng của mình. Cách làm này giúp các tầng phối hợp, tránh tiếp tục xử lý một request đã hết thời gian hữu ích.

## 1. Vì sao timeout riêng lẻ không đủ?

Giả sử client chờ tối đa 1.000 ms. Request đi qua gateway, Order Service, Inventory Service và Payment Service. Nếu mỗi tầng đặt timeout 1.000 ms riêng, thời gian toàn tuyến có thể vượt xa 1 giây:

```text
Client budget: 1.000 ms

Gateway:          tối đa 1.000 ms
Order Service:    tối đa 1.000 ms
Inventory:        tối đa 1.000 ms
Payment:          tối đa 1.000 ms
```

Các timeout trên không tạo thành một deadline tổng. Mỗi tầng có thể bắt đầu đồng hồ mới khi nhận request, trong khi client đã tiêu thụ thời gian chờ ở các tầng trước đó.

Ví dụ, gateway mất 150 ms, Order Service mất 250 ms và Inventory Service mất 300 ms. Khi request đến Payment Service, chỉ còn 300 ms trong ngân sách 1.000 ms. Nếu Payment Service vẫn chờ đủ 1.000 ms, response có thể đến sau khi client đã timeout và đóng kết nối.

Một deadline chung giải quyết vấn đề này: mỗi tầng chỉ được dùng phần thời gian còn lại. Thời gian đã tiêu thụ ở gateway, queue, connection pool, các lời gọi trước đó và xử lý hiện tại đều thuộc cùng ngân sách.

## 2. Phân bổ ngân sách cho toàn tuyến

Với chuỗi gọi tuần tự, có thể mô hình hóa tổng ngân sách như sau:

\[
B_{total} = B_{gateway} + B_{service} + B_{dependencies} + B_{response}
\]

Trong đó:

- `B_gateway`: thời gian xác thực, routing và xử lý tại gateway.
- `B_service`: thời gian xử lý nghiệp vụ trong service hiện tại.
- `B_dependencies`: tổng thời gian dành cho các service/database được gọi.
- `B_response`: phần dự phòng để tổng hợp kết quả, serialize response và ghi dữ liệu về client.

Ví dụ với ngân sách 1.000 ms:

| Phần công việc | Ngân sách mục tiêu |
|---|---:|
| Gateway và truyền request | 80 ms |
| Xử lý Order Service | 120 ms |
| Inventory Service | 250 ms |
| Payment Service | 300 ms |
| Tổng hợp và ghi response | 150 ms |
| Dự phòng biến động | 100 ms |
| **Tổng** | **1.000 ms** |

Đây là kế hoạch phân bổ để thiết kế và đo lường, không phải cam kết mỗi tầng luôn tiêu thụ đúng số mili giây đó. Khi request thực tế đến một tầng, thời gian còn lại mới là giới hạn có thẩm quyền. Nếu Inventory chỉ dùng 100 ms thay vì 250 ms, phần thời gian tiết kiệm có thể được dùng ở tầng sau, miễn là deadline tổng vẫn được giữ.

Với các dependency được gọi song song, không cộng thời gian của chúng như chuỗi tuần tự. Thời gian chờ nhánh thường bị chi phối bởi nhánh chậm nhất, cộng với chi phí điều phối và bước xử lý tiếp theo. Dù vậy, mọi nhánh vẫn phải dùng chung deadline để một nhánh không tiếp tục chạy quá lâu sau khi toàn request đã hết hạn.

## 3. Deadline tổng và giới hạn riêng của từng tầng

Một request nên có:

1. **Deadline tổng**: thời điểm cuối cùng mà toàn bộ thao tác còn giá trị.
2. **Per-hop cap**: giới hạn tối đa dành cho một lời gọi đến dependency.
3. **Response reserve**: thời gian giữ lại cho service hiện tại xử lý kết quả và trả response.

Thời hạn của một lời gọi dependency nên là giá trị nhỏ hơn giữa giới hạn riêng và thời gian còn lại:

\[
T_{hop} = \min(T_{hop\_cap}, T_{remaining})
\]

Nếu cần giữ thời gian cho response, service có thể tạo deadline nội bộ sớm hơn deadline client:

\[
D_{internal} = D_{client} - T_{response\_reserve}
\]

Khi `D_internal` đã qua, service ngừng khởi chạy dependency mới để còn thời gian chuyển lỗi, ghi metric và phản hồi. Phần dự phòng cần được đo theo kích thước response và tải thực tế; không nên lấy một tỷ lệ tùy ý áp dụng cho mọi endpoint.

## 4. Đo thời gian còn lại bằng đồng hồ phù hợp

Trong một process Java, dùng `System.nanoTime()` để đo thời gian đã trôi qua và tính deadline nội bộ. Đây là đồng hồ monotonic, không bị điều chỉnh bởi đồng bộ giờ hệ thống như `System.currentTimeMillis()`.

```java
record RequestDeadline(long deadlineNanos) {

    static RequestDeadline after(Duration budget) {
        if (budget.isNegative() || budget.isZero()) {
            throw new IllegalArgumentException("Budget phải lớn hơn 0");
        }
        return new RequestDeadline(System.nanoTime() + budget.toNanos());
    }

    Duration remaining() {
        long nanosLeft = deadlineNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0L, nanosLeft));
    }

    Duration cap(Duration perHopCap) {
        Duration left = remaining();
        return left.compareTo(perHopCap) < 0 ? left : perHopCap;
    }

    boolean isExpired() {
        return remaining().isZero();
    }
}
```

`RequestDeadline` chỉ có ý nghĩa trong process đã tạo nó. Không gửi trực tiếp giá trị `deadlineNanos` sang service khác vì `System.nanoTime()` có mốc tham chiếu riêng trên từng máy. Chỉ dùng hiệu giữa hai lần đọc trong cùng process.

Nếu nhận một `Duration` từ tầng gọi, hãy kiểm tra giá trị hợp lệ và giới hạn nó bằng timeout tối đa do service cho phép. Không để client gửi một budget vô hạn khiến request chiếm tài nguyên không giới hạn.

## 5. Truyền deadline qua ranh giới service

Khi request đi qua nhiều process, các service cần một quy ước truyền deadline. Có hai cách thường gặp:

- **Deadline tuyệt đối**: truyền thời điểm hết hạn theo một chuẩn thời gian chung, ví dụ Unix epoch. Service nhận tính phần còn lại theo đồng hồ của nó. Cách này cần đồng hồ giữa các máy được đồng bộ và phải tính đến clock skew.
- **Timeout còn lại**: truyền thời lượng còn lại và mỗi intermediary giảm phần thời gian đã tiêu thụ trước khi chuyển tiếp. Cách này cần mọi tầng tuân thủ quy ước; nếu chỉ forward nguyên timeout ban đầu, ngân sách có thể bị làm mới ngoài ý muốn.

Với gRPC, deadline là khái niệm được hỗ trợ trực tiếp trong giao thức và client/server API. Khi dùng HTTP nội bộ, tổ chức có thể định nghĩa header deadline hoặc timeout riêng, nhưng phải quy định rõ đơn vị, giới hạn tối đa, cách giảm budget và hành vi khi thiếu header.

Ví dụ một header nội bộ dạng deadline tuyệt đối:

```http
X-Request-Deadline-Epoch-Ms: 1795363200123
```

Service nhận header cần:

1. Chỉ tin header được thêm hoặc xác thực bởi gateway nội bộ đáng tin cậy.
2. Từ chối hoặc áp dụng timeout mặc định nếu giá trị sai định dạng hay đã hết hạn.
3. Clamp deadline vào giới hạn tối đa của service để không cho request kéo dài vô hạn.
4. Tính thời gian còn lại, chuyển sang monotonic deadline nội bộ.
5. Khi gọi tiếp service khác, truyền deadline hoặc timeout còn lại theo cùng hợp đồng.

Không nên tin trực tiếp một header do client bên ngoài tự đặt để bỏ qua giới hạn timeout của hệ thống. Gateway nên xóa giá trị không đáng tin cậy rồi thiết lập deadline dựa trên policy của server.

## 6. Áp dụng deadline trong pipeline Reactor

Với một request-response được biểu diễn bằng `Mono`, có thể đặt timeout tổng ở ngoài cùng pipeline và giới hạn riêng cho từng lời gọi dependency. `Mono.timeout(Duration)` phát `TimeoutException` nếu Mono không phát kết quả trong thời hạn.

```java
Mono<OrderView> loadOrder(
        String orderId,
        RequestDeadline deadline) {

    return Mono.defer(() -> {
        Duration totalRemaining = deadline.remaining();
        if (totalRemaining.isZero()) {
            return Mono.error(new TimeoutException("Request deadline expired"));
        }

        Mono<Order> order = Mono.defer(() -> orderClient.findById(orderId))
            .timeout(deadline.cap(Duration.ofMillis(180)));

        return order.flatMap(found -> {
            Duration inventoryBudget = deadline.cap(Duration.ofMillis(250));
            if (inventoryBudget.isZero()) {
                return Mono.error(new TimeoutException("No budget for inventory"));
            }

            return Mono.defer(() -> inventoryClient.findBySku(found.sku()))
                .timeout(inventoryBudget)
                .map(inventory -> OrderView.from(found, inventory));
        }).timeout(totalRemaining);
    });
}
```

Trong ví dụ:

- `Mono.defer` đọc thời gian còn lại khi subscription bắt đầu, không phải lúc lắp ráp bean hoặc controller.
- Order Service có cap riêng 180 ms nhưng không được vượt deadline còn lại.
- Sau khi Order trả kết quả, Inventory được cấp budget mới dựa trên thời gian còn lại lúc đó, tối đa 250 ms.
- `timeout(totalRemaining)` ở ngoài cùng bảo vệ toàn bộ chuỗi lời gọi.
- Các lời gọi được đặt trong `defer` để việc tạo Publisher và khởi chạy request xảy ra khi pipeline được subscribe.

Trong code production, nên ánh xạ timeout của từng dependency và timeout tổng thành các loại lỗi có mã riêng để metric và API response phân biệt được tầng gây trễ. Không nên biến tất cả timeout thành một giá trị fallback có vẻ thành công nếu nghiệp vụ không cho phép.

Nếu service cần giữ thời gian cho bước serialize và trả response, hãy truyền một deadline nội bộ đã trừ `response reserve` vào `loadOrder`. Deadline client vẫn được giữ để theo dõi tổng thời gian end-to-end.

## 7. Timeout của `Mono` và `Flux` không hoàn toàn giống nhau

`Mono.timeout(Duration)` phù hợp với thao tác cần một kết quả hoặc hoàn tất trong một thời hạn. Với `Flux`, `timeout(Duration)` thường là giới hạn thời gian chờ giữa các tín hiệu: timer được áp dụng cho tín hiệu đầu tiên và được đặt lại khi có phần tử tiếp theo. Đây là **idle timeout**, không nhất thiết là thời hạn tổng của cả stream.

Ví dụ một SSE stream phát đều đặn có thể chạy hàng giờ mà không vi phạm `timeout(Duration.ofSeconds(30))`, miễn là không có khoảng im lặng nào vượt 30 giây. Nếu nghiệp vụ cần giới hạn tổng thời lượng stream, phải thiết kế một deadline tổng riêng. Nếu cần phát hiện stream bị treo, dùng idle timeout. Hai yêu cầu này không nên bị nhầm lẫn.

| Loại giới hạn | Câu hỏi | Ví dụ |
|---|---|---|
| Request deadline | Toàn bộ request phải kết thúc trước khi nào? | API tra cứu hoàn tất trong 800 ms |
| Per-hop timeout | Một dependency được phép mất tối đa bao lâu? | Inventory tối đa 250 ms |
| Idle timeout | Bao lâu không có tín hiệu thì coi là bị treo? | SSE không có event trong 30 giây |
| Total stream lifetime | Một stream được tồn tại tối đa bao lâu? | Subscription báo cáo tối đa 10 phút |

Với stream dài hạn, cần cân nhắc cả chính sách heartbeat, reconnect, cancellation và giới hạn tài nguyên. Không dùng một request-response deadline ngắn cho một subscription vốn được thiết kế để sống lâu.

## 8. Retry phải tiêu thụ cùng ngân sách

Retry là một phần của thời gian request, bao gồm thời gian chờ backoff, thời gian thiết lập kết nối và thời gian thực thi lại. Không được cấp lại toàn bộ timeout ban đầu cho mỗi lần retry.

```java
Mono<Inventory> inventory = Mono.defer(() -> {
    Duration totalRemaining = deadline.remaining();
    if (totalRemaining.isZero()) {
        return Mono.error(new TimeoutException("Request deadline expired"));
    }

    Mono<Inventory> attempts = Mono.defer(() -> {
        Duration attemptBudget = deadline.cap(Duration.ofMillis(250));
        if (attemptBudget.isZero()) {
            return Mono.error(new TimeoutException("No budget for inventory attempt"));
        }
        return Mono.defer(() -> inventoryClient.findBySku(sku))
            .timeout(attemptBudget);
    }).retryWhen(Retry.backoff(2, Duration.ofMillis(40))
        .maxBackoff(Duration.ofMillis(120))
        .filter(this::isTransientFailure));

    return attempts.timeout(totalRemaining);
});
```

Ví dụ này minh họa giới hạn theo deadline và retry có backoff. `Mono.defer` nằm trước `retryWhen`, vì vậy mỗi lần retry đăng ký lại sẽ tính `attemptBudget` mới theo thời gian còn lại. Timeout tổng được tính một lần cho toàn chuỗi retry và bao gồm cả thời gian backoff. Đồng thời, phải bảo đảm thao tác có thể retry an toàn, ví dụ API đọc hoặc thao tác ghi có idempotency key.

Nếu hết budget trong thời gian backoff, không nên bắt đầu attempt mới. Một deadline tổng bên ngoài pipeline sẽ hủy chuỗi khi hết hạn, nhưng việc kiểm tra remaining trước mỗi attempt giúp tránh khởi chạy công việc đã chắc chắn không còn đủ thời gian.

## 9. Fan-out song song và ngân sách chung

Một service có thể gọi nhiều dependency song song bằng `Mono.zip`. Các nhánh không được cấp một deadline mới độc lập; chúng cùng dùng deadline của request:

```java
Mono<OrderSummary> summary = Mono.defer(() -> {
    Duration totalRemaining = deadline.remaining();
    if (totalRemaining.isZero()) {
        return Mono.error(new TimeoutException("Request deadline expired"));
    }

    Mono<Customer> customer = Mono.defer(() ->
        customerClient.findById(customerId)
    ).timeout(deadline.cap(Duration.ofMillis(300)));

    Mono<Inventory> inventory = Mono.defer(() ->
        inventoryClient.findBySku(sku)
    ).timeout(deadline.cap(Duration.ofMillis(300)));

    return Mono.zip(customer, inventory)
        .map(tuple -> new OrderSummary(tuple.getT1(), tuple.getT2()))
        .timeout(totalRemaining);
});
```

Hai nhánh chạy độc lập nên thời gian chờ thường gần với nhánh chậm nhất thay vì tổng hai nhánh. Tuy nhiên, cả hai vẫn tiêu thụ cùng deadline; nếu một nhánh chậm làm hết thời gian, kết quả toàn request không còn hữu ích và các nhánh còn lại cần được hủy theo khả năng của client.

Nếu một nhánh là tùy chọn và có thể fallback, hãy đặt fallback có chủ đích cho nhánh đó. Không nên để một dependency không thiết yếu kéo dài toàn request hoặc âm thầm tạo dữ liệu giả làm sai kết quả nghiệp vụ.

## 10. Cancellation khi deadline hết hạn

Khi `timeout` phát lỗi timeout, Reactor hủy subscription upstream. Cancellation truyền qua các toán tử và Publisher con theo hợp đồng reactive. Một HTTP client reactive thường có thể hủy request hoặc ngừng đọc response; driver database có thể hỗ trợ hủy query tùy implementation.

Cancellation không bảo đảm mọi tác vụ bên dưới dừng tức thời:

- Một callback CPU đang chạy không tự động bị ngắt ở mọi điểm.
- Một thư viện blocking có thể tiếp tục chạy dù subscription đã bị hủy.
- Một thao tác ghi đã được database commit không thể được hoàn tác chỉ vì client timeout sau đó.
- Một dịch vụ ngoài có thể đã thực hiện side effect trước khi kết nối bị hủy.

Do đó, deadline phải đi kèm timeout ở client phụ thuộc, giới hạn concurrency, transaction ngắn và idempotency cho thao tác ghi. Không dựa vào cancellation như cơ chế rollback phổ quát.

Có thể quan sát nguyên nhân kết thúc bằng `doFinally`:

```java
Mono<Result> result = operation
    .doFinally(signalType -> metrics.recordTermination(signalType));
```

`SignalType` cho biết subscription kết thúc do complete, error hay cancel. Nếu cần phân biệt timeout với lỗi khác, hãy ghi nhận exception trước khi nó được chuyển thành fallback hoặc response nghiệp vụ.

## 11. Kiểm thử deadline bằng virtual time

Không cần chờ thời gian thật để kiểm thử timeout. `StepVerifier.withVirtualTime` cho phép tiến đồng hồ giả lập và xác nhận deadline.

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofMillis(800))
            .thenReturn("done")
            .timeout(Duration.ofMillis(700))
    )
    .thenAwait(Duration.ofMillis(700))
    .expectError(TimeoutException.class)
    .verify();
```

Publisher định thời được tạo bên trong supplier để virtual scheduler được cài trước khi pipeline được lắp ráp. Sau khi tiến đồng hồ 700 ms, thao tác chưa hoàn tất nên subscriber nhận `TimeoutException`.

Có thể kiểm thử sự khác biệt giữa timeout từng hop và deadline tổng:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofMillis(400))
            .then(Mono.delay(Duration.ofMillis(400)))
            .thenReturn("ok")
            .timeout(Duration.ofMillis(700))
    )
    .thenAwait(Duration.ofMillis(700))
    .expectError(TimeoutException.class)
    .verify();
```

Hai bước mỗi bước mất 400 ms, nên từng bước có thể nằm trong cap 500 ms riêng, nhưng tổng 800 ms vượt deadline 700 ms. Publisher được tạo bên trong supplier của `withVirtualTime`, bảo đảm các nguồn định thời dùng virtual scheduler. Nên kiểm thử thêm trường hợp bước đầu tiêu thụ gần hết budget khiến bước sau không được khởi chạy.

## 12. Quan sát và vận hành timeout budget

Chỉ đặt timeout mà không đo lường sẽ khó xác định tầng nào tiêu thụ ngân sách. Nên ghi nhận:

- Tổng thời gian end-to-end từ gateway đến response.
- Thời gian tại từng service và từng dependency.
- Budget còn lại khi request đến mỗi tầng.
- Số lần timeout theo dependency và theo endpoint.
- Số lần retry, thời gian backoff và kết quả sau retry.
- Số request bị hủy, request tiếp tục chạy sau khi caller đã timeout và lỗi do pool/queue.
- Phân vị latency như p50, p95 và p99 thay vì chỉ dùng trung bình.

Trace phân tán nên mang trace ID và deadline/budget metadata để có thể so sánh thời gian giữa các span. Tránh log dữ liệu nhạy cảm hoặc header xác thực khi ghi metadata request.

Khi phân tích p99, cần kiểm tra cả thời gian chờ connection pool, thread/worker queue, DNS, TLS handshake, retry và serialization. Một dependency có thời gian xử lý database 20 ms vẫn có thể tiêu thụ 200 ms nếu request chờ connection pool hoặc queue trước đó.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Mỗi tầng bắt đầu lại timeout ban đầu | Tổng thời gian vượt deadline client | Truyền deadline và tính remaining ở mỗi hop |
| Dùng `System.currentTimeMillis()` để đo thời gian nội bộ | Thay đổi đồng hồ hệ thống có thể làm sai phép đo elapsed time | Dùng `System.nanoTime()` trong từng process |
| Truyền trực tiếp giá trị `nanoTime` sang process khác | Mốc monotonic không có ý nghĩa chung giữa máy | Truyền deadline chuẩn hóa hoặc remaining budget theo hợp đồng |
| Không giữ thời gian cho response | Dependency hoàn tất sát deadline, service không kịp trả kết quả | Trừ response reserve khỏi deadline nội bộ |
| Retry với timeout mới đầy đủ | Retry storm và request chạy quá hạn | Mọi attempt và backoff dùng cùng deadline tổng |
| Nhầm `Flux.timeout` với total stream lifetime | Stream hoạt động lâu vẫn không timeout nếu liên tục có tín hiệu | Phân biệt idle timeout và total lifetime |
| Nghĩ cancel luôn dừng side effect | Công việc blocking hoặc thao tác đã commit vẫn có thể tiếp tục | Dùng API hỗ trợ cancellation và idempotency |
| Chỉ đo latency tổng | Không biết tầng nào tiêu thụ budget | Ghi span/metric theo từng hop và remaining budget |

## 14. Quy trình thiết kế timeout budget

Khi thiết kế một chuỗi lời gọi nhiều tầng, hãy thực hiện:

1. **Xác định deadline client** từ yêu cầu trải nghiệm hoặc hợp đồng API.
2. **Giữ response reserve** cho xử lý cuối, serialize và ghi response.
3. **Thiết lập deadline nội bộ** ngắn hơn deadline client theo phần dự phòng đã đo.
4. **Truyền deadline qua từng hop** bằng hợp đồng tin cậy; mỗi tầng clamp vào giới hạn local và tính remaining.
5. **Đặt per-hop cap** không vượt quá thời gian còn lại.
6. **Dùng một deadline cho các nhánh song song** thay vì cấp lại budget riêng.
7. **Tính retry và backoff vào tổng thời gian**; không bắt đầu attempt khi không còn đủ budget.
8. **Phân biệt timeout, idle timeout và total stream lifetime** theo loại Publisher.
9. **Kiểm tra cancellation và side effect** ở HTTP client, driver, database và service ngoài.
10. **Đo p95/p99 và remaining budget** để điều chỉnh phân bổ theo tải thực tế.

Ngân sách thời gian chờ giúp các tầng phối hợp quanh một deadline chung. Trong Reactor, `Mono.timeout` và các toán tử liên quan cung cấp cơ chế giới hạn thời gian ở từng đoạn pipeline; `Mono.defer` giúp tính budget tại thời điểm subscription; cancellation giúp dừng các nhánh còn hoạt động khi request hết hạn. Khi deadline được truyền đúng qua service, retry tiêu thụ cùng ngân sách và thời gian response được dự phòng, hệ thống tránh lãng phí tài nguyên cho những request đã quá hạn và giữ latency end-to-end dễ dự đoán hơn.
