# Thời gian

## `timeout`: giới hạn thời gian chờ và lựa chọn hành vi thay thế

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi một bước xử lý phụ thuộc vào mạng, cơ sở dữ liệu hoặc một luồng sự kiện, nó có thể chờ lâu hơn thời gian nghiệp vụ cho phép. Reactor cung cấp toán tử **`timeout`** để đặt giới hạn thời gian chờ và quyết định hệ thống phải làm gì khi nguồn không phát tín hiệu kịp thời.

`timeout` có thể biến một thao tác chậm thành lỗi `TimeoutException`, hoặc chuyển sang một Publisher thay thế như cache, dịch vụ dự phòng hay một giá trị mặc định. Với `Mono`, giới hạn thường áp dụng từ lúc subscribe cho tới tín hiệu đầu tiên hoặc tín hiệu kết thúc. Với `Flux`, timeout theo `Duration` thường áp dụng cho khoảng chờ tín hiệu đầu tiên và khoảng thời gian im lặng giữa hai phần tử. Sự khác biệt này rất quan trọng: một luồng phát đều đặn có thể chạy vô hạn mà không timeout, dù tổng thời gian chạy đã rất dài.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích thời điểm bộ đếm timeout bắt đầu và được làm mới trong `Mono` và `Flux`.
- Phân biệt giới hạn thời gian cho một lần chờ tín hiệu, từng lời gọi con và toàn bộ workflow.
- Dùng `timeout(Duration)` để phát lỗi và `timeout(Duration, fallback)` để chuyển sang nguồn thay thế.
- Kết hợp `timeout` với `onErrorResume`, retry và các Publisher dự phòng.
- Chọn scheduler cho bộ định thời và hiểu giới hạn của cancellation.
- Kiểm thử timeout và fallback bằng `StepVerifier` cùng thời gian ảo.
- Tránh những lỗi thường gặp khi đặt timeout ở sai vị trí trong pipeline.

## 1. Vì sao cần giới hạn thời gian chờ?

Một Publisher bất đồng bộ có thể không phát tín hiệu trong thời gian dài. Nguyên nhân có thể là:

- Dịch vụ từ xa phản hồi chậm hoặc mất kết nối.
- Truy vấn cơ sở dữ liệu đang chờ khóa hoặc cạn connection pool.
- Một API callback không gọi success/error do lỗi ở thư viện tích hợp.
- Một luồng sự kiện không phát dữ liệu trong thời gian dài.
- Một Publisher con không hoàn tất, khiến các bước sau phải chờ.

Nếu không có giới hạn, request có thể giữ tài nguyên như kết nối, bộ nhớ, slot xử lý và trạng thái chờ lâu hơn mức nghiệp vụ cho phép. Một request bị treo cũng có thể giữ các phần tử phía sau trong pipeline tuần tự như `concatMap`.

Timeout tạo một ranh giới thời gian rõ ràng. Khi nguồn không đáp ứng điều kiện tín hiệu trước hạn, toán tử hủy subscription upstream và thực hiện hành vi timeout đã cấu hình.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant T as timeout
    participant P as Publisher nguồn
    C->>T: subscribe
    T->>P: subscribe upstream
    Note over T,P: Bắt đầu đếm thời gian
    alt Nguồn phát kịp hạn
        P-->>T: onNext / onComplete
        T-->>C: chuyển tín hiệu nguồn
    else Quá thời hạn
        T-xP: cancel upstream
        T-->>C: TimeoutException hoặc subscribe fallback
    end
~~~

Timeout là một tín hiệu điều khiển ở phía ứng dụng. Nó không chứng minh rằng hệ thống từ xa chưa thực hiện thao tác. Ví dụ, server có thể đã ghi dữ liệu thành công nhưng phản hồi bị trễ; client timeout rồi retry có thể tạo thao tác trùng. Với các lệnh ghi, thanh toán hoặc gửi thông báo, cần idempotency key và cơ chế đối soát trạng thái.

## 2. Timeout cơ bản với Mono

`Mono<T>` phát tối đa một phần tử rồi kết thúc, hoặc hoàn tất rỗng, hoặc phát lỗi. Với `timeout(Duration)`, Reactor bắt đầu tính thời gian khi có subscription. Nếu Mono không phát tín hiệu thích hợp trước hạn, downstream nhận lỗi timeout.

~~~java
Mono<Customer> customer =
    customerClient.findById(customerId)
        .timeout(Duration.ofSeconds(2));
~~~

Trong ví dụ, nếu nguồn không phát tín hiệu đầu tiên trong hai giây, Mono kết quả phát lỗi `java.util.concurrent.TimeoutException`.

Một số trường hợp cần phân biệt:

- Nếu nguồn phát một Customer trong thời hạn, giá trị được chuyển xuống và Mono kết thúc bình thường.
- Nếu nguồn hoàn tất rỗng trước hạn, kết quả vẫn là Mono rỗng; không có timeout.
- Nếu nguồn phát lỗi trước hạn, lỗi gốc được chuyển xuống.
- Nếu nguồn không phát bất kỳ tín hiệu nào, chẳng hạn `Mono.never()`, timeout sẽ xảy ra.
- Nếu nguồn phát giá trị trước hạn, timeout chờ tín hiệu đầu tiên đã được hủy và giá trị được chuyển xuống. `timeout(Duration)` trên Mono không tạo thêm một deadline riêng cho khoảng chờ `onComplete` sau giá trị đó.

Ví dụ một Publisher không bao giờ phát:

~~~java
Mono<String> never = Mono.<String>never()
    .timeout(Duration.ofMillis(500));
~~~

Khi được subscribe, Publisher kết quả sẽ phát lỗi timeout sau khoảng thời gian cấu hình. Thời điểm thực tế có thể lệch đôi chút do scheduler, tải CPU và độ phân giải của bộ định thời; không nên xem timeout như một đồng hồ thời gian thực chính xác tới từng mili giây.

## 3. Timeout với Flux: khoảng im lặng giữa các phần tử

Với `Flux<T>`, một luồng có thể phát nhiều phần tử. Khi dùng `timeout(Duration)`, thời hạn được áp dụng cho việc chờ phần tử đầu tiên và được đặt lại sau mỗi `onNext`. Vì thế, toán tử này thường được hiểu là **idle timeout**: luồng bị timeout nếu không có phần tử mới trong khoảng thời gian quy định.

~~~java
Flux<Price> prices =
    marketData.priceUpdates(symbol)
        .timeout(Duration.ofSeconds(5));
~~~

Nếu phần tử đầu tiên đến sau hơn năm giây, hoặc khoảng cách giữa hai phần tử liên tiếp vượt quá năm giây, luồng phát lỗi timeout. Nếu mỗi phần tử đến cách nhau dưới năm giây, luồng có thể tiếp tục vô hạn mà không timeout.

Ví dụ nguồn phát ba phần tử với khoảng cách khác nhau:

~~~java
Flux<String> events =
    Flux.just("connected", "heartbeat", "updated")
        .delayElements(Duration.ofSeconds(2))
        .timeout(Duration.ofSeconds(3));
~~~

Khoảng cách giữa các phần tử là hai giây, nhỏ hơn timeout ba giây, nên luồng hoàn tất bình thường.

Nếu đổi timeout thành một giây, khoảng chờ giữa các phần tử vượt hạn và luồng sẽ lỗi trước khi nhận đủ dữ liệu.

**Timeout của Flux không phải giới hạn tổng thời gian sống của luồng.** Một luồng có thể phát mỗi giây một sự kiện và tiếp tục hàng giờ mà không timeout nếu idle timeout là năm giây.

## 4. Chuyển sang Publisher thay thế

Nhiều tình huống không muốn trả lỗi ngay khi nguồn chính chậm. Có thể cung cấp một Publisher dự phòng:

~~~java
Mono<Customer> customer =
    customerClient.findById(customerId)
        .timeout(
            Duration.ofSeconds(2),
            customerCache.findById(customerId)
        );
~~~

Nếu nguồn chính không phát kịp trong hai giây, Reactor hủy subscription nguồn chính và subscribe vào Publisher fallback. Kết quả của fallback trở thành kết quả của pipeline.

Fallback có thể là:

- Giá trị mặc định bằng `Mono.just(...)`.
- Kết quả cache hoặc bản sao đọc.
- Một dịch vụ dự phòng.
- Một Publisher báo lỗi nghiệp vụ khác.
- Một Publisher rỗng nếu nghiệp vụ cho phép không có kết quả.

Ví dụ dùng giá trị mặc định:

~~~java
Mono<FeatureFlags> flags =
    configClient.load()
        .timeout(
            Duration.ofSeconds(1),
            Mono.just(FeatureFlags.safeDefaults())
        );
~~~

Cách này hữu ích nếu cấu hình mặc định an toàn và nghiệp vụ chấp nhận chạy với cấu hình đó. Không nên dùng fallback mặc định để che giấu một lỗi quan trọng nếu điều đó khiến ứng dụng âm thầm vận hành sai.

### Fallback nên được tạo khi cần

Nếu tạo fallback có tác dụng phụ ngay lúc lắp ráp pipeline, biểu thức Java vẫn được đánh giá theo quy tắc thông thường. Dùng `Mono.defer` hoặc `Flux.defer` khi muốn chỉ tạo Publisher dự phòng vào thời điểm timeout:

~~~java
Mono<Customer> customer =
    customerClient.findById(customerId)
        .timeout(
            Duration.ofSeconds(2),
            Mono.defer(() -> customerCache.findById(customerId))
        );
~~~

Supplier của `defer` chỉ được gọi khi fallback được subscribe. Điều này tránh gọi cache hoặc dịch vụ dự phòng khi nguồn chính đã trả kết quả đúng hạn.

Nếu fallback cũng cần giới hạn thời gian, hãy đặt timeout riêng cho fallback:

~~~java
Mono<Customer> customer =
    customerClient.findById(customerId)
        .timeout(
            Duration.ofSeconds(2),
            Mono.defer(() ->
                customerCache.findById(customerId)
                    .timeout(Duration.ofMillis(500))
            )
        );
~~~

Giới hạn hai giây ở đây áp dụng cho nguồn chính; fallback có giới hạn riêng 500 ms. Nếu cache cũng không phản hồi, lỗi timeout của fallback sẽ đi xuống downstream.

## 5. Phân loại timeout và chọn hành vi thay thế

Không phải timeout nào cũng nên được xử lý giống nhau. Hành vi cần chọn dựa trên loại công việc và hậu quả khi dữ liệu không đến đúng hạn.

| Tình huống | Hành vi thường cân nhắc | Lý do |
|---|---|---|
| Đọc dữ liệu có cache hợp lệ | Chuyển sang cache | Giữ trải nghiệm đọc khi nguồn chính chậm |
| Tính năng tùy chọn | Trả giá trị mặc định an toàn | Không để tính năng phụ làm chậm luồng chính |
| Lệnh ghi quan trọng | Báo lỗi và đối soát trạng thái | Không giả định thao tác từ xa chưa xảy ra |
| Luồng heartbeat | Báo mất kết nối hoặc tái kết nối | Khoảng im lặng có thể biểu thị kết nối bị gián đoạn |
| Gọi dịch vụ dự phòng | Chuyển sang replica/fallback | Duy trì dịch vụ trong giới hạn cho phép |
| Workflow vượt ngân sách thời gian | Hủy và trả lỗi phù hợp | Giải phóng tài nguyên và tuân thủ SLO |

Fallback không nhất thiết là thành công. Nếu Publisher thay thế cũng phát lỗi, lỗi đó được truyền xuống. Nếu fallback hoàn tất rỗng, kết quả sẽ rỗng. Nếu fallback phát giá trị, downstream nhận giá trị đó như kết quả của pipeline.

Cần ghi nhận timeout bằng metric riêng, phân biệt với lỗi kết nối, lỗi nghiệp vụ và phản hồi rỗng. Nếu tất cả đều bị chuyển thành một giá trị mặc định mà không có log hoặc metric, hệ thống có thể che khuất sự suy giảm của dịch vụ chính.

## 6. Xử lý TimeoutException bằng onErrorResume

Thay vì truyền fallback trực tiếp vào `timeout`, có thể để timeout phát lỗi rồi xử lý ở bước sau:

~~~java
Mono<Customer> customer =
    customerClient.findById(customerId)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(
            TimeoutException.class,
            error -> customerCache.findById(customerId)
        );
~~~

Cách này hữu ích khi cần phân biệt timeout với các lỗi khác. Chỉ `TimeoutException` mới chuyển sang cache; lỗi xác thực, lỗi dữ liệu hoặc lỗi kết nối khác vẫn được truyền xuống.

Nếu muốn log và giữ nguyên lỗi:

~~~java
Mono<Customer> customer =
    customerClient.findById(customerId)
        .timeout(Duration.ofSeconds(2))
        .doOnError(TimeoutException.class, error ->
            metrics.recordCustomerTimeout()
        );
~~~

`doOnError` chỉ quan sát lỗi, không thay thế hoặc phục hồi nó. Dùng `onErrorResume` khi muốn chuyển sang Publisher khác; dùng `doOnError` khi muốn ghi nhận hoặc quan sát.

Tránh bắt mọi lỗi rồi trả fallback nếu nghiệp vụ chỉ cho phép fallback khi timeout. Một lỗi 401 hoặc lỗi dữ liệu không hợp lệ không nên bị hiểu thành "dịch vụ chậm".

## 7. Timeout theo từng lần gọi và timeout toàn workflow

Vị trí đặt toán tử quyết định phần công việc nào bị giới hạn.

### Giới hạn từng lời gọi con

~~~java
Flux<Result> results =
    requests.flatMap(request ->
        remoteClient.call(request)
            .timeout(Duration.ofSeconds(2)),
        16
    );
~~~

Mỗi Publisher con có giới hạn chờ hai giây riêng. Một lời gọi chậm có thể timeout trong khi các lời gọi khác vẫn hoàn tất. `flatMap` vẫn có thể tiếp tục xử lý các phần tử khác theo chính sách lỗi và recovery đã cấu hình.

Nếu dùng `concatMap`, timeout cho từng inner giúp một lời gọi không giữ lượt tuần tự mãi mãi:

~~~java
Flux<Result> results =
    requests.concatMap(request ->
        remoteClient.call(request)
            .timeout(Duration.ofSeconds(2))
    );
~~~

Khi một inner timeout, theo mặc định lỗi có thể kết thúc cả luồng. Nếu cần tiếp tục các request sau, xử lý timeout bên trong mapper và chuyển thành kết quả lỗi hoặc fallback phù hợp.

### Giới hạn toàn bộ một Mono workflow

~~~java
Mono<OrderReceipt> receipt =
    orderRepository.findById(orderId)
        .flatMap(inventoryService::reserve)
        .flatMap(paymentService::authorize)
        .timeout(Duration.ofSeconds(5));
~~~

Toán tử timeout ở cuối chuỗi áp dụng từ khi subscription bắt đầu tới khi workflow Mono phát tín hiệu kết thúc. Nếu tổng thời gian đọc đơn, đặt chỗ và thanh toán vượt năm giây, workflow bị timeout.

Đặt timeout ở từng bước sẽ tạo ngân sách riêng cho mỗi bước. Ví dụ, đọc đơn tối đa một giây, đặt chỗ tối đa hai giây, thanh toán tối đa ba giây; tổng thời gian có thể lớn hơn ba giây. Đặt timeout ở cuối giúp giới hạn tổng thời gian của cả chuỗi Mono.

### Giới hạn tổng thời gian của Flux

Với Flux, `timeout(Duration)` là idle timeout chứ không phải deadline tổng. Nếu cần đợi toàn bộ luồng hoàn tất trong một khoảng thời gian, có thể thu thập nó thành Mono rồi đặt timeout:

~~~java
Mono<List<Event>> allEvents =
    eventSource.events()
        .collectList()
        .timeout(Duration.ofSeconds(10));
~~~

Ở đây, Mono chỉ phát danh sách khi Flux hoàn tất. Nếu toàn bộ quá trình chưa kết thúc trong mười giây, Mono timeout.

Nếu mục tiêu là dừng một luồng đang chạy sau một khoảng thời gian và hoàn tất bình thường, có thể dùng `take(Duration)`:

~~~java
Flux<Event> firstThirtySeconds =
    eventSource.events()
        .take(Duration.ofSeconds(30));
~~~

`take(Duration)` giới hạn thời gian thu thập rồi hoàn tất luồng; nó không phát `TimeoutException`. Chọn `timeout` khi quá thời hạn là một điều kiện lỗi hoặc cần fallback; chọn `take` khi muốn kết thúc luồng theo thời gian một cách bình thường.

## 8. Timeout theo tín hiệu tùy chỉnh

Ngoài overload nhận `Duration`, Reactor cho phép chỉ định Publisher đóng vai trò bộ định thời. Điều này hữu ích khi khoảng chờ đầu tiên khác với khoảng chờ giữa các phần tử.

~~~java
Flux<Event> events =
    eventSource.events()
        .timeout(
            Mono.delay(Duration.ofSeconds(5)),
            event -> Mono.delay(Duration.ofSeconds(2))
        );
~~~

Trong ví dụ:

- Subscriber chờ tối đa năm giây để nhận tín hiệu đầu tiên.
- Sau mỗi phần tử, Reactor tạo một Publisher timeout mới với thời hạn hai giây.
- Nếu Publisher timeout tương ứng phát tín hiệu trước khi nguồn phát phần tử kế tiếp, luồng bị timeout.
- Nếu nguồn phát kịp, bộ định thời cũ được thay bằng bộ định thời cho phần tử tiếp theo.

Cách này cho phép mô tả giao thức có thời gian khởi động và heartbeat khác nhau. Ví dụ, kết nối WebSocket có thể mất vài giây để phát sự kiện đầu tiên, nhưng sau khi đã kết nối thì heartbeat phải xuất hiện thường xuyên hơn.

Có thể cung cấp fallback cho dạng timeout tùy chỉnh nếu muốn chuyển sang nguồn khác khi bộ định thời phát tín hiệu. Hãy bảo đảm Publisher timeout thực sự chỉ phát khi hết hạn; nếu nó hoàn tất hoặc phát ngay, nguồn chính có thể timeout ngay lập tức.

## 9. Scheduler của bộ định thời

Timeout cần một bộ định thời để phát hiện thời hạn đã hết. Các overload thông dụng dùng scheduler mặc định của Reactor. Khi cần kiểm soát rõ scheduler, có thể truyền scheduler tường minh:

~~~java
Mono<Response> response =
    apiClient.fetch()
        .timeout(
            Duration.ofSeconds(2),
            Schedulers.parallel()
        );
~~~

Scheduler được truyền vào đây phục vụ việc lên lịch kiểm tra timeout. Nó không tự chuyển toàn bộ thao tác upstream sang scheduler đó. Nếu cần điều khiển nơi thực thi nguồn hoặc downstream, hãy dùng `subscribeOn` hoặc `publishOn` theo đúng mục đích.

Trong kiểm thử, thời gian ảo giúp kiểm tra timeout mà không phải chờ thật. Khi dùng `StepVerifier.withVirtualTime`, hãy tạo Publisher bên trong supplier để Reactor có thể áp dụng scheduler ảo trước khi pipeline được lắp ráp.

Không nên dùng scheduler blocking cho bộ định thời. Một scheduler bị chặn bởi tác vụ lâu có thể làm callback timeout chạy trễ. Với tác vụ blocking, cô lập phần blocking trên `boundedElastic`; giữ bộ định thời ở scheduler thích hợp và quan sát độ trễ thực tế của timer trong môi trường tải.

## 10. Kết hợp timeout với retry

Timeout có thể được xem là lỗi tạm thời và retry, nhưng phải cân nhắc hậu quả của việc thực hiện lại thao tác.

~~~java
Mono<Quote> quote =
    Mono.defer(() -> pricingClient.fetchQuote(productId))
        .timeout(Duration.ofSeconds(1))
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .filter(TimeoutException.class::isInstance)
        );
~~~

Trong ví dụ, mỗi lần subscribe lại tạo một Publisher request mới nhờ `defer`. Mỗi lần gọi có giới hạn một giây. `Retry.backoff(2, ...)` cho phép tối đa hai lần retry sau lần thử ban đầu, với khoảng nghỉ tăng dần. Bộ lọc chỉ retry lỗi timeout.

Cần lưu ý:

- Retry làm tăng tổng thời gian chờ vì mỗi lần thử có timeout và khoảng backoff.
- Nếu timeout xảy ra sau khi server đã thực hiện thao tác, retry có thể lặp tác dụng phụ.
- Retry không giới hạn có thể tạo thêm tải khi dịch vụ đang quá tải.
- Chỉ retry lỗi có khả năng khắc phục và đặt ngân sách thời gian tổng.
- Với thao tác ghi, dùng idempotency key hoặc kiểm tra trạng thái trước khi gửi lại.

Thứ tự toán tử ảnh hưởng đến ý nghĩa timeout. Trong ví dụ trên, timeout nằm trước retry nên mỗi lần thử có deadline riêng; tổng thời gian của toàn bộ chuỗi có thể dài hơn một giây. Nếu cần deadline tổng, đặt một timeout ngoài cùng sau retry:

~~~java
Mono<Quote> quote =
    Mono.defer(() -> pricingClient.fetchQuote(productId))
        .timeout(Duration.ofSeconds(1))
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .filter(TimeoutException.class::isInstance)
        )
        .timeout(Duration.ofSeconds(3));
~~~

Timeout ngoài cùng giới hạn tổng thời gian của Mono workflow, bao gồm cả các lần retry và thời gian backoff. Với Flux, hãy nhớ timeout theo Duration ở cấp Flux vẫn là idle timeout; để giới hạn tổng thời gian một luồng phải hoàn tất, hãy áp dụng deadline lên Mono đại diện cho việc hoàn tất như `collectList()`, hoặc dùng cơ chế deadline phù hợp với yêu cầu.

## 11. Cancellation khi timeout xảy ra

Khi timeout kích hoạt, toán tử gửi cancellation upstream rồi phát lỗi hoặc subscribe fallback. Điều này giúp giải phóng tài nguyên nếu nguồn tôn trọng cancellation.

Tuy nhiên, cancellation chỉ là tín hiệu. Có ba tình huống thường gặp:

1. **Nguồn hỗ trợ hủy thực sự:** client HTTP hoặc driver có thể hủy request đang chờ và giải phóng kết nối.
2. **Nguồn chỉ ngừng phát cho Subscriber:** công việc nền vẫn chạy, nhưng kết quả không còn được tiêu thụ.
3. **Tác dụng phụ đã được xác nhận:** thao tác đã commit ở phía server; cancellation không thể rollback.

Vì vậy, timeout không nên được hiểu là "server chắc chắn chưa làm gì". Với lệnh ghi, hãy dùng request ID hoặc idempotency key ổn định qua các lần retry. Khi client timeout và không biết kết quả, có thể cần truy vấn trạng thái giao dịch trước khi gửi lại.

Nếu fallback được subscribe sau timeout, fallback có vòng đời riêng trong pipeline kết quả. Cancellation của Subscriber cuối vẫn truyền tới fallback đang chạy. Nếu fallback cũng là một request từ xa, cần đặt timeout riêng và có chính sách retry phù hợp.

## 12. Kiểm thử timeout bằng StepVerifier

Không nên dùng `Thread.sleep` để kiểm thử timeout vì test chậm và phụ thuộc lịch chạy của máy. Reactor Test hỗ trợ thời gian ảo.

### Kiểm thử timeout phát lỗi

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(Duration.ofSeconds(5))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify();
~~~

Publisher được tạo bên trong supplier. Sau khi tiến thời gian ảo năm giây, test xác minh lỗi timeout.

### Kiểm thử fallback

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(
                Duration.ofSeconds(3),
                Mono.just("cached")
            )
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext("cached")
    .verifyComplete();
~~~

Khi nguồn chính không phát trong ba giây, fallback phát giá trị `cached` và hoàn tất.

### Kiểm thử Flux idle timeout

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.concat(
                Mono.delay(Duration.ofSeconds(1)).map(i -> "A"),
                Mono.delay(Duration.ofSeconds(4)).map(i -> "B")
            )
            .timeout(Duration.ofSeconds(2))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(1))
    .expectNext("A")
    .thenAwait(Duration.ofSeconds(2))
    .expectError(TimeoutException.class)
    .verify();
~~~

Sau khi A được phát, Publisher tiếp theo cần bốn giây mới phát B. Idle timeout hai giây xảy ra trước khi B đến. Test minh họa timeout được đặt lại sau mỗi phần tử.

Các kiểm thử quan trọng khác:

- Nguồn hoàn tất rỗng trước hạn; xác minh kết quả vẫn rỗng.
- Nguồn phát lỗi trước hạn; xác minh lỗi gốc được giữ.
- Fallback cũng timeout hoặc phát lỗi; xác minh lỗi fallback được truyền xuống.
- Cancellation upstream được gọi khi timeout; dùng nguồn giả có thể quan sát hook cleanup.
- Retry thực hiện đúng số lần và chỉ retry loại lỗi được phép.
- Deadline tổng vẫn được tuân thủ khi có nhiều lần retry và backoff.

## 13. Những nhầm lẫn thường gặp

- **Timeout của Flux là giới hạn tổng thời gian:** `timeout(Duration)` trên Flux thường đo khoảng chờ tín hiệu đầu tiên và khoảng im lặng giữa các phần tử.
- **Nguồn hoàn tất rỗng là timeout:** `onComplete` trước hạn là hoàn tất bình thường, dù không có phần tử nào.
- **Fallback luôn thành công:** Publisher fallback có thể rỗng hoặc lỗi; kết quả của nó được truyền xuống như mọi Publisher khác.
- **Timeout chứng minh server chưa xử lý request:** server có thể đã commit nhưng phản hồi bị trễ hoặc mất.
- **Timeout tự chuyển tác vụ sang scheduler khác:** bộ định thời chỉ điều khiển thời điểm timeout; dùng `subscribeOn`/`publishOn` riêng nếu cần chuyển nơi thực thi.
- **Retry hai lần nghĩa là tổng thời gian tối đa bằng timeout:** mỗi lần thử có thể tiêu thụ toàn bộ timeout cộng backoff; cần deadline tổng riêng.
- **`take(Duration)` giống `timeout(Duration)`:** take kết thúc luồng bình thường sau thời gian; timeout phát lỗi hoặc chuyển fallback khi thiếu tín hiệu.
- **Đặt timeout ở cuối Flux luôn giới hạn toàn bộ luồng:** nó vẫn đo khoảng im lặng giữa các phần tử; hãy chuyển thành Mono hoàn tất hoặc dùng toán tử giới hạn thời gian phù hợp.
- **Cancellation chắc chắn dừng tác dụng phụ:** thư viện hoặc hệ thống từ xa phải hỗ trợ hủy; thao tác đã commit không tự rollback.

## 14. Bài tập vận dụng

Một API lấy trạng thái thanh toán trả về `Mono<PaymentStatus>`. Dịch vụ yêu cầu:

- Chờ tối đa 800 ms cho lần gọi chính.
- Nếu timeout, thử đọc trạng thái từ cache.
- Nếu cache cũng không phản hồi trong 300 ms, trả lỗi timeout để tầng API chuyển thành HTTP 503.
- Không retry thao tác ghi thanh toán vì không biết server đã commit hay chưa.

Hãy thiết kế pipeline và giải thích:

1. Viết `Mono<PaymentStatus>` dùng `timeout` để giới hạn nguồn chính.
2. Làm thế nào để chỉ gọi cache khi nguồn chính timeout?
3. Đặt timeout riêng cho cache ở đâu?
4. Nếu nguồn chính trả lỗi 401 hoặc 404 trước 800 ms, cache có được gọi không? Vì sao?
5. Vì sao không nên retry lệnh ghi thanh toán chỉ vì client timeout?
6. Nếu API cần giới hạn tổng thời gian phản hồi, bạn sẽ đặt thêm deadline ở đâu?
7. Hãy viết kiểm thử `StepVerifier.withVirtualTime` cho trường hợp nguồn chính timeout rồi cache trả kết quả.

**Gợi ý:** dùng `timeout(Duration, Mono.defer(...))` để tạo fallback khi cần; bên trong fallback đặt `timeout(Duration)` riêng. Nếu muốn ánh xạ timeout sang HTTP 503, thực hiện ở tầng biên API. Chỉ chuyển sang cache khi lỗi đúng loại timeout; không nuốt lỗi xác thực hoặc lỗi nghiệp vụ khác.

## Kết luận

`timeout` đặt giới hạn cho việc chờ tín hiệu và cho phép chọn giữa phát `TimeoutException` hoặc chuyển sang Publisher thay thế. Với `Mono`, timeout theo Duration thường giới hạn thời gian từ subscription tới tín hiệu đầu tiên; với `Flux`, nó thường giới hạn khoảng chờ tín hiệu đầu tiên và khoảng im lặng giữa các phần tử. Vị trí toán tử quyết định giới hạn áp dụng cho từng lời gọi hay toàn workflow. Khi kết hợp fallback, retry và cancellation, hãy xem xét idempotency, deadline tổng và khả năng hủy thực sự của nguồn. Kiểm thử bằng thời gian ảo giúp xác nhận hành vi timeout mà không phụ thuộc vào thời gian chờ thực tế.
