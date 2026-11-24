# Mô hình luồng

## Tính khai báo, tính lười và thời điểm phát sinh tác dụng phụ

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học cách xây dựng ứng dụng quanh các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams. Với Reactor, `Mono` và `Flux` cho phép mô tả một chuỗi xử lý bằng các toán tử kết hợp. Để sử dụng mô hình này đúng cách, cần hiểu ba đặc điểm liên quan chặt chẽ: **tính khai báo**, **tính lười** và **thời điểm tác dụng phụ thực sự xảy ra**.

Một pipeline reactive thường được tạo ra trước khi nó chạy. Các lời gọi như `map`, `filter`, `flatMap` mô tả cách dữ liệu sẽ được biến đổi khi có subscription và demand phù hợp. Vì vậy, việc nhìn thấy một biểu thức `Mono` hoặc `Flux` được khởi tạo chưa có nghĩa là công việc bên trong đã được thực thi. Tuy nhiên, Java vẫn đánh giá các biểu thức thông thường ngay tại thời điểm gọi phương thức; không phải mọi thứ viết cạnh một Publisher đều tự động trở nên lazy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích tính khai báo trong pipeline reactive và phân biệt giai đoạn lắp ráp với giai đoạn thực thi.
- Phân biệt việc đánh giá biểu thức Java tức thời với việc thực thi được trì hoãn bên trong Publisher.
- Xác định tác dụng phụ xảy ra khi lắp ráp, subscribe, nhận demand, nhận tín hiệu hay hủy subscription.
- Chọn giữa `Mono.just`, `Mono.fromSupplier`, `Mono.defer` và các toán tử phù hợp.
- Đặt tác dụng phụ quan sát ở đúng vị trí và biểu diễn tác vụ nghiệp vụ bất đồng bộ trong chuỗi Publisher.
- Nhận biết ảnh hưởng của nhiều subscription, retry, cache, chia sẻ luồng và cancellation.

## 1. Tính khai báo: mô tả việc cần làm

Trong cách lập trình mệnh lệnh, ta thường viết các câu lệnh theo thứ tự thực hiện:

~~~java
Order order = repository.findById(orderId);
if (order != null && order.isValid()) {
    inventory.reserve(order);
    payment.authorize(order);
}
~~~

Đoạn mã thể hiện trực tiếp các bước cần chạy. Các lời gọi phương thức được thực thi khi luồng điều khiển đi qua chúng.

Trong cách lập trình reactive, ta thường mô tả cách một giá trị hoặc tín hiệu sẽ đi qua các bước xử lý:

~~~java
Mono<Order> workflow = repository.findById(orderId)
    .filter(Order::isValid)
    .flatMap(order ->
        inventory.reserve(order)
            .then(payment.authorize(order))
            .thenReturn(order)
    );
~~~

Biểu thức này mô tả một workflow: lấy đơn hàng, chỉ giữ đơn hợp lệ, đặt chỗ tồn kho, sau đó yêu cầu thanh toán và phát lại đơn hàng khi chuỗi hoàn tất. Các toán tử định nghĩa mối quan hệ giữa các bước. Việc thực thi được điều khiển bởi subscription và nhu cầu của Subscriber.

Tính khai báo giúp đọc luồng xử lý theo cấu trúc dữ liệu và tín hiệu, ghép các thao tác bất đồng bộ mà không phải tự quản lý callback lồng nhau. Nó cũng cho Reactor cơ hội điều phối subscription, demand, cancellation và tín hiệu theo hợp đồng Reactive Streams.

Tính khai báo không có nghĩa là chương trình không có tác dụng phụ. Đọc cơ sở dữ liệu, gửi thanh toán, ghi log hay cập nhật chỉ số đều có thể là tác dụng phụ. Điểm quan trọng là biểu diễn những công việc đó trong pipeline để thời điểm bắt đầu, kết quả, lỗi và việc hủy có thể được quản lý cùng nhau.

## 2. Ba giai đoạn cần phân biệt

Khi làm việc với Reactor, hãy tách ít nhất ba mốc sau:

1. **Assembly (lắp ráp):** ứng dụng gọi các phương thức tạo Publisher và toán tử để xây dựng pipeline.
2. **Subscription (đăng ký):** Subscriber đăng ký với Publisher; chuỗi xử lý bắt đầu thiết lập việc phát tín hiệu.
3. **Signal và demand (tín hiệu và nhu cầu):** Subscriber yêu cầu phần tử bằng `request(n)`; các tín hiệu như `onNext`, `onComplete`, `onError` được truyền qua pipeline theo hợp đồng.

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng
    participant P as Publisher / pipeline
    participant S as Subscriber
    A->>P: Tạo Mono / Flux và toán tử
    Note over A,P: Assembly: mô tả pipeline
    A->>S: Subscribe
    S->>P: onSubscribe
    Note over P,S: Subscription được thiết lập
    S->>P: request(n)
    P-->>S: onNext(...)
    P-->>S: onComplete hoặc onError
~~~

| Mốc | Điều gì diễn ra? | Ví dụ tác dụng phụ |
|---|---|---|
| Assembly | Tạo Publisher và nối toán tử | Gọi hàm Java để tính đối số cho `Mono.just` |
| Subscription | Subscriber đăng ký; nguồn deferred có thể được tạo | Khởi tạo phiên truy vấn trong `defer`, ghi nhận bắt đầu |
| Demand | Subscriber yêu cầu số phần tử | Nguồn tạo phần tử theo nhu cầu |
| Signal | Giá trị, lỗi hoặc hoàn tất đi qua pipeline | Ghi nhận kết quả ở `doOnNext`, xử lý lỗi ở `doOnError` |
| Cancellation | Subscriber hủy việc nhận thêm tín hiệu | Giải phóng tài nguyên, dừng công việc còn có thể dừng |

Đây là mô hình khái niệm để xác định thời điểm. Chi tiết chính xác phụ thuộc loại Publisher và toán tử nguồn. Chẳng hạn, một nguồn có thể phát đồng bộ ngay trong quá trình subscribe sau khi demand được gửi; nguồn khác có thể phát tín hiệu bất đồng bộ về sau. Không nên suy ra thread hoặc thời điểm chạy chỉ từ việc pipeline đã được lắp ráp.

## 3. Tính lười và đánh giá biểu thức Java

Tính lười của Publisher có nghĩa là công việc được mô tả bởi nguồn có thể được trì hoãn cho đến khi có subscription hoặc demand theo cách triển khai của nguồn. Điều đó không làm Java thay đổi quy tắc đánh giá biểu thức.

### `just`: giá trị đã được tính trước

~~~java
Profile profile = loadProfile(userId);
Mono<Profile> source = Mono.just(profile);
~~~

`loadProfile(userId)` được gọi ngay khi dòng đầu tiên chạy. `Mono.just` nhận một giá trị đã tồn tại và phát giá trị đó cho Subscriber. Nếu viết gọn:

~~~java
Mono<Profile> source = Mono.just(loadProfile(userId));
~~~

thì `loadProfile(userId)` vẫn được thực thi trong giai đoạn assembly, trước khi có subscription.

Điều tương tự xảy ra với `Flux.just`:

~~~java
Flux<String> names = Flux.just(loadName(1), loadName(2));
~~~

Cả hai lời gọi `loadName` được đánh giá để tạo đối số cho phương thức `Flux.just`. Publisher không trì hoãn các lời gọi Java đó.

### `fromSupplier` và `fromCallable`: trì hoãn việc gọi hàm

Khi muốn trì hoãn việc lấy giá trị, có thể truyền một hàm:

~~~java
Mono<Profile> source =
    Mono.fromSupplier(() -> loadProfile(userId));
~~~

Hàm supplier được Reactor gọi khi nguồn được thực thi theo subscription và demand. Nhờ đó, `loadProfile` không chạy trong lúc lắp ráp pipeline. `Mono.fromCallable` cũng biểu diễn một phép tính có thể trả về giá trị hoặc ném exception:

~~~java
Mono<Profile> source =
    Mono.fromCallable(() -> loadProfileFromLegacySystem(userId));
~~~

Exception phát sinh từ callable được chuyển thành tín hiệu `onError` của Publisher. Nếu callable thực hiện I/O blocking, việc trì hoãn không tự biến nó thành non-blocking; cần cô lập tác vụ blocking trên scheduler phù hợp, ví dụ `subscribeOn(Schedulers.boundedElastic())`, và đặt timeout theo yêu cầu.

### `defer`: tạo Publisher cho từng subscription

Dùng `defer` khi chính việc tạo Publisher cũng cần được trì hoãn hoặc cần tạo một nguồn mới cho mỗi Subscriber:

~~~java
Mono<Profile> source =
    Mono.defer(() -> profileRepository.findById(userId));
~~~

Hàm supplier của `defer` được gọi khi có subscription. Publisher được trả về từ supplier sau đó tham gia vào chuỗi xử lý. Nếu có hai Subscriber đăng ký riêng, supplier được gọi cho mỗi subscription, vì vậy mỗi lần có thể tạo một truy vấn hoặc nguồn mới.

So sánh nhanh:

| Cách tạo nguồn | Giá trị / Publisher được tạo khi nào? | Khi nào phù hợp? |
|---|---|---|
| `Mono.just(value)` | Đối số `value` đã được đánh giá trước lời gọi | Giá trị đã có sẵn và có thể dùng lại |
| `Mono.fromSupplier(fn)` | Gọi hàm để lấy giá trị khi nguồn được thực thi | Một phép tính đồng bộ cần trì hoãn |
| `Mono.fromCallable(fn)` | Gọi callable khi nguồn được thực thi; lỗi thành `onError` | Phép tính có thể ném exception |
| `Mono.defer(fn)` | Gọi hàm để tạo Publisher cho mỗi subscription | Cần tạo nguồn mới hoặc chọn nguồn theo thời điểm subscribe |
| `Flux.defer(fn)` | Tạo Flux cho từng subscription | Nguồn nhiều phần tử thay đổi theo mỗi lần đăng ký |

Ví dụ, nếu danh sách được đọc từ bộ nhớ tại thời điểm tạo pipeline thì:

~~~java
List<String> initial = loadNames();
Flux<String> fixed = Flux.fromIterable(initial);
~~~

danh sách được nạp ngay trong assembly và được dùng lại bởi các Subscriber. Nếu cần đọc danh sách mới mỗi lần đăng ký:

~~~java
Flux<String> refreshed =
    Flux.defer(() -> Flux.fromIterable(loadNames()));
~~~

Hàm `loadNames()` chỉ được gọi khi có subscription và được gọi lại cho subscription tiếp theo.

## 4. Tác dụng phụ xảy ra ở đâu?

Tác dụng phụ là hành động quan sát hoặc làm thay đổi trạng thái bên ngoài phép biến đổi dữ liệu thuần túy. Ví dụ gồm ghi log, tăng bộ đếm, ghi cơ sở dữ liệu, gửi thông báo, gọi dịch vụ thanh toán hoặc thay đổi trạng thái trong bộ nhớ.

Khi đọc một pipeline, hãy hỏi: tác dụng phụ nằm ở biểu thức Java được đánh giá ngay, trong supplier của nguồn, trong callback nhận tín hiệu, hay trong Publisher con được ghép bằng toán tử?

### Tác dụng phụ trong assembly

~~~java
Mono<Receipt> receipt = Mono.just(paymentClient.chargeNow(request));
~~~

Giả sử `chargeNow` là lời gọi đồng bộ trả về `Receipt`. Lời gọi này xảy ra ngay khi xây dựng biểu thức. Nếu đây là thao tác thu tiền, việc chỉ tạo biến `receipt` đã có thể làm giao dịch bắt đầu. Nếu pipeline chưa được subscribe hoặc bị bỏ đi, hành động đã xảy ra nhưng kết quả reactive chưa được tiêu thụ.

Cách trì hoãn và đưa thao tác vào pipeline:

~~~java
Mono<Receipt> receipt =
    Mono.defer(() -> paymentClient.charge(request));
~~~

Giả sử `charge` trả về `Mono<Receipt>`; `defer` gọi phương thức khi có subscription và ghép Publisher được trả về vào luồng.

### Tác dụng phụ quan sát bằng các toán tử `doOn...`

Reactor cung cấp các toán tử callback để quan sát vòng đời và tín hiệu:

| Toán tử | Thời điểm callback | Công dụng điển hình |
|---|---|---|
| `doOnSubscribe` | Khi có subscription | Ghi nhận bắt đầu, gắn theo dõi |
| `doOnRequest` | Khi có yêu cầu demand | Quan sát nhu cầu được gửi |
| `doOnNext` | Khi một phần tử được phát | Log hoặc ghi metric cho phần tử |
| `doOnSuccess` | Khi Mono hoàn tất thành công, kể cả trường hợp rỗng | Quan sát kết quả Mono |
| `doOnError` | Khi lỗi đi qua vị trí toán tử | Ghi nhận lỗi |
| `doOnComplete` | Khi Flux hoàn tất thành công | Ghi nhận hoàn tất Flux |
| `doFinally` | Khi kết thúc bằng complete, error hoặc cancel | Kết thúc đo thời gian, giải phóng tài nguyên quan sát |

Ví dụ:

~~~java
Mono<Profile> profile = profileRepository.findById(userId)
    .doOnSubscribe(subscription -> metrics.recordStarted())
    .doOnNext(value -> log.debug("Loaded profile {}", value.id()))
    .doOnError(error -> metrics.recordFailure(error))
    .doFinally(signal -> metrics.recordFinished(signal));
~~~

Các callback này không thay thế giá trị hay Publisher trong pipeline; chúng quan sát quá trình xử lý. Chú ý `doOnSuccess` của `Mono` có thể nhận `null` khi Mono hoàn tất mà không phát giá trị. Nếu chỉ muốn quan sát phần tử thực sự được phát, `doOnNext` thường diễn đạt rõ ý hơn.

### Tác vụ nghiệp vụ bất đồng bộ nên được ghép vào luồng

Giả sử sau khi nhận đơn hàng, ứng dụng cần đặt chỗ tồn kho và thực hiện thanh toán. Không nên khởi chạy một Publisher con bên trong callback quan sát rồi bỏ qua nó:

~~~java
// Không nên: Publisher trả về từ reserve không được ghép vào workflow.
orders.findById(orderId)
    .doOnNext(order -> inventory.reserve(order));
~~~

Nếu `reserve` trả về `Mono<Void>`, đoạn trên chỉ tạo Publisher rồi bỏ qua; tác vụ có thể không chạy vì chưa có subscription cho Publisher con. Cách biểu diễn đúng là ghép tác vụ bất đồng bộ bằng `flatMap`, `then` hoặc toán tử tương ứng:

~~~java
Mono<Order> workflow = orders.findById(orderId)
    .filter(Order::isValid)
    .flatMap(order ->
        inventory.reserve(order)
            .then(payment.authorize(order))
            .thenReturn(order)
    )
    .doOnNext(order -> log.info("Order {} authorized", order.id()))
    .doOnError(error -> log.warn("Order workflow failed", error));
~~~

Trong pipeline này, `flatMap` kết hợp Publisher con do thao tác nghiệp vụ trả về. `then` chờ Publisher trước hoàn tất rồi mới tiếp tục Publisher sau. Lỗi của bước đặt tồn kho hoặc thanh toán đi theo kênh `onError`, nhờ đó bên gọi có thể xử lý lỗi, timeout hoặc retry theo chính sách.

`doOnNext` phù hợp cho quan sát như log và metric. Với tác dụng phụ nghiệp vụ có kết quả bất đồng bộ, hãy trả về Publisher và ghép nó vào pipeline để thứ tự, lỗi và cancellation được quản lý đúng.

## 5. Nhiều subscription có thể làm tác dụng phụ lặp lại

Một pipeline reactive có thể được subscribe nhiều lần. Với nguồn cold như `defer`, `fromSupplier` và phần lớn lời gọi repository, mỗi subscription thường khởi động một lần thực thi độc lập. Vì thế, tác dụng phụ trong pipeline có thể xảy ra nhiều lần.

~~~java
AtomicInteger counter = new AtomicInteger();

Mono<Integer> sequence =
    Mono.defer(() -> Mono.just(counter.incrementAndGet()));

sequence.subscribe(value -> log.info("First: {}", value));
sequence.subscribe(value -> log.info("Second: {}", value));
~~~

Subscription thứ nhất nhận giá trị 1, subscription thứ hai nhận giá trị 2. Supplier của `defer` được gọi riêng cho mỗi subscription.

Ngược lại:

~~~java
Mono<Integer> fixed =
    Mono.just(counter.incrementAndGet());
~~~

`incrementAndGet` chỉ chạy một lần trong assembly. Các subscription sau nhận cùng giá trị đã được tạo sẵn.

### Retry cũng có thể chạy lại tác dụng phụ

`retry` thực hiện subscription lại khi gặp lỗi phù hợp. Nếu một lời gọi dịch vụ đã tạo tác dụng phụ ở phía xa nhưng phản hồi bị mất, lần subscribe lại có thể gửi thao tác đó thêm lần nữa. Với các thao tác như tạo đơn, thu tiền hoặc gửi thông báo, điều này có thể tạo bản ghi hoặc giao dịch trùng.

Hãy thiết kế thao tác có khả năng retry với khóa idempotency hoặc cơ chế chống trùng phù hợp. Chỉ retry lỗi có thể khắc phục, giới hạn số lần, áp dụng backoff và cân nhắc tổng ngân sách thời gian. Việc đặt `retry` ở đâu cũng quan trọng vì nó quyết định đoạn pipeline nào được subscribe lại.

### Chia sẻ hoặc lưu kết quả thay đổi hành vi thực thi

Nếu nhiều Subscriber cần dùng chung một kết quả hoặc cùng quan sát một nguồn, Reactor có các cơ chế như `cache()` hoặc `share()`. Chúng thay đổi cách nguồn được subscribe và cách tín hiệu được phân phối. Ví dụ, `cache()` có thể lưu tín hiệu đã phát để Subscriber đến sau nhận lại kết quả mà không thực hiện lại nguồn như một cold Publisher thông thường.

~~~java
Mono<Configuration> configuration =
    Mono.defer(configClient::load)
        .cache();
~~~

Ở đây, `defer` tạo nguồn theo subscription, còn `cache` lưu kết quả theo chính sách cache của toán tử. Vì vậy không thể kết luận rằng cứ có thêm một Subscriber là dịch vụ cấu hình sẽ được gọi lại. Khi chọn cache hoặc share, cần hiểu vòng đời dữ liệu, thời hạn hiệu lực, lỗi được lưu và hành vi khi không còn Subscriber.

Một **hot source** có thể phát sự kiện độc lập với subscription của từng người nhận. Subscriber đến muộn có thể bỏ lỡ những sự kiện đã phát trước đó, trừ khi nguồn có chính sách lưu hoặc replay. Vì thế, cold/hot, cache và share là các quyết định về vòng đời và phân phối dữ liệu, không chỉ là lựa chọn cú pháp.

## 6. Cancellation và scheduler không làm mất quy tắc về tác dụng phụ

Subscriber có thể hủy subscription. Khi cancellation truyền tới nguồn và các toán tử, pipeline có thể ngừng phát thêm tín hiệu và giải phóng tài nguyên. Tuy nhiên, cancellation không bảo đảm hoàn tác một tác dụng phụ đã xảy ra. Một yêu cầu HTTP đã được gửi hoặc một giao dịch đã được hệ thống từ xa xác nhận có thể không thể thu hồi chỉ bằng cách hủy subscription phía client.

Dùng `doFinally` để quan sát cả complete, error và cancel:

~~~java
Mono<Result> result = remoteClient.fetch()
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            metrics.recordCancelled();
        }
    });
~~~

Nếu cần quản lý tài nguyên có bước mở và đóng bất đồng bộ, hãy dùng các toán tử quản lý vòng đời như `usingWhen` thay vì dựa vào một callback tùy ý. Với các thao tác ghi dữ liệu, hãy xác định rõ điểm commit và cách xử lý khi client hủy sau khi yêu cầu đã đến server.

Scheduler quyết định nơi một phần công việc được thực thi. `subscribeOn` ảnh hưởng tới quá trình subscribe và nguồn upstream; `publishOn` chuyển việc xử lý các tín hiệu downstream sang scheduler được chọn. Chúng không thay đổi việc biểu thức Java đã được đánh giá trong assembly hay chưa:

~~~java
Mono<Profile> profile =
    Mono.fromCallable(() -> legacyClient.load(userId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Callable được trì hoãn bởi nguồn và được thực thi trên scheduler phù hợp cho blocking. Nếu thay bằng `Mono.just(legacyClient.load(userId))`, lời gọi `load` vẫn xảy ra trước khi pipeline được tạo; thêm `subscribeOn` sau đó không thể đưa lời gọi đã xảy ra trong assembly quay ngược về scheduler.

## 7. Kiểm thử thời điểm thực thi

Có thể dùng `StepVerifier` trong Reactor Test để xác minh pipeline chỉ thực thi khi được subscribe và tác dụng phụ được gọi đúng số lần.

~~~java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> source =
    Mono.defer(() -> Mono.just(calls.incrementAndGet()));

// Assembly chưa gọi supplier.
assertThat(calls.get()).isZero();

StepVerifier.create(source)
    .expectNext(1)
    .verifyComplete();

assertThat(calls.get()).isEqualTo(1);

// Subscription thứ hai tạo một lần thực thi mới.
StepVerifier.create(source)
    .expectNext(2)
    .verifyComplete();

assertThat(calls.get()).isEqualTo(2);
~~~

Ví dụ dùng AssertJ cho các phép kiểm tra. `StepVerifier.create(...)` subscribe vào Publisher để xác minh các tín hiệu; do đó bộ đếm tăng trong lúc verifier thực hiện subscription.

Có thể viết một kiểm thử đối chứng để thấy `Mono.just` đánh giá đối số ngay:

~~~java
AtomicInteger eagerCalls = new AtomicInteger();

Mono<Integer> eager =
    Mono.just(eagerCalls.incrementAndGet());

assertThat(eagerCalls.get()).isEqualTo(1);

StepVerifier.create(eager)
    .expectNext(1)
    .verifyComplete();

assertThat(eagerCalls.get()).isEqualTo(1);
~~~

Các trường hợp nên kiểm thử thêm:

- Hai subscription độc lập có tạo hai lần gọi nguồn hay không.
- `retry` có thực hiện lại đúng đoạn pipeline dự kiến hay không.
- `cache` hoặc `share` có tạo số lần gọi nguồn đúng với vòng đời mong muốn hay không.
- Cancellation có kích hoạt cleanup và metric tương ứng hay không.
- Publisher hoàn tất rỗng có được phân biệt với Publisher phát một giá trị hay không.
- Lỗi từ tác dụng phụ nghiệp vụ có truyền tới nơi xử lý lỗi như mong đợi hay không.

## 8. Những nhầm lẫn thường gặp

- **Tạo `Mono` nghĩa là công việc đã chạy:** assembly thường chỉ xây dựng mô tả pipeline; nguồn eager hoặc biểu thức Java làm đối số vẫn có thể chạy ngay.
- **`Mono.just(methodCall())` là lazy:** phương thức được gọi trước khi `Mono.just` nhận giá trị. Dùng `fromSupplier`, `fromCallable` hoặc `defer` tùy trường hợp.
- **Mọi callback trong pipeline đều là tác vụ reactive:** `doOnNext` là callback quan sát. Publisher bất đồng bộ trả về từ callback không tự động được ghép vào chuỗi.
- **Một pipeline chỉ thực thi một lần:** cold Publisher thường chạy lại theo từng subscription; retry cũng tạo subscription mới.
- **Hủy subscription sẽ hoàn tác tác dụng phụ:** cancellation có thể dừng công việc còn lại nhưng không tự đảo ngược thao tác đã được hệ thống bên ngoài thực hiện.
- **Đổi scheduler sẽ làm một lời gọi eager trở thành lazy:** scheduler không thay đổi thời điểm Java đánh giá đối số.
- **Retry an toàn với mọi thao tác:** thao tác ghi hoặc thanh toán có thể bị lặp nếu lần thực hiện trước thành công nhưng phản hồi không đến được client.

## 9. Bài tập vận dụng

Một service tạo pipeline xử lý đơn hàng như sau:

~~~java
Mono<Receipt> receipt =
    Mono.just(paymentClient.charge(request))
        .doOnNext(value -> log.info("Payment result: {}", value.id()));
~~~

Đây là đoạn mã cần phân tích và sửa. Nếu `charge` trả về `Mono<Receipt>`, biểu thức còn tạo ra `Mono<Mono<Receipt>>`, không khớp kiểu `Mono<Receipt>` đã khai báo. Nếu `charge` trả về `Receipt`, lời gọi vẫn diễn ra ngay trong assembly. Cả kiểu dữ liệu lẫn thời điểm thực thi đều cần được xem xét.

Hãy phân tích và đề xuất cách sửa:

1. `paymentClient.charge(request)` xảy ra ở giai đoạn nào? Điều gì xảy ra nếu biến `receipt` được tạo nhưng không bao giờ subscribe?
2. Nếu `charge` trả về `Mono<Receipt>`, tại sao `Mono.just` ở đây không phù hợp?
3. Viết lại pipeline để lời gọi thanh toán chỉ được tạo khi có subscription.
4. Nếu cần ghi metric bắt đầu, thành công, lỗi và cancellation, bạn sẽ đặt các toán tử nào?
5. Nếu client retry khi timeout, làm thế nào tránh thu tiền hai lần?
6. Nếu hai thành phần cùng subscribe vào pipeline, bạn mong đợi thanh toán chạy một lần hay hai lần? Cần cơ chế nào nếu nghiệp vụ yêu cầu dùng chung kết quả?

**Gợi ý:** nếu `charge` trả về `Mono<Receipt>`, hãy cân nhắc `Mono.defer(() -> paymentClient.charge(request))`. Dùng `doOnSubscribe`, `doOnNext`, `doOnError` và `doFinally` cho metric quan sát; giữ thao tác thanh toán trong Publisher để lỗi và cancellation đi theo chuỗi. Thiết kế idempotency cho thao tác thanh toán trước khi bật retry hoặc chia sẻ kết quả.

## Kết luận

Tính khai báo giúp mô tả cách dữ liệu và tín hiệu đi qua pipeline; tính lười cho phép trì hoãn việc tạo hoặc thực thi nguồn đến subscription và demand phù hợp. Tuy nhiên, biểu thức Java vẫn được đánh giá theo quy tắc thông thường, nên `Mono.just(methodCall())` có thể thực hiện tác dụng phụ ngay trong assembly. Hãy dùng `fromSupplier`, `fromCallable` hoặc `defer` đúng mục đích, đặt callback quan sát ở các toán tử `doOn...`, và ghép tác vụ nghiệp vụ bất đồng bộ bằng `flatMap` hoặc `then`. Khi đã hiểu vòng đời subscription, nhiều subscription, retry và cancellation, ta có thể xây dựng pipeline `Mono`/`Flux` dễ dự đoán, kiểm thử được và an toàn hơn trước các tác dụng phụ.
