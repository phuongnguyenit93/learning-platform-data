# Tác dụng phụ tại thời điểm lắp ráp và thời điểm đăng ký

Trong **REACTIVE_PROGRAMMING**, pipeline `Mono` và `Flux` mô tả cách dữ liệu bất đồng bộ đi từ `Publisher` đến `Subscriber`, được biến đổi qua các toán tử và chịu sự điều tiết của backpressure. Để pipeline hoạt động đúng, cần phân biệt hai thời điểm: **lắp ráp (assembly)** là lúc chương trình tạo chuỗi toán tử; **đăng ký (subscription)** là lúc một Subscriber kết nối vào Publisher để bắt đầu nhận tín hiệu.

Sự phân biệt này đặc biệt quan trọng khi pipeline có tác dụng phụ như gọi API, truy vấn cơ sở dữ liệu, tạo mã định danh, ghi log hoặc cập nhật trạng thái. Một lời gọi đặt sai thời điểm có thể chạy dù không ai đăng ký, chỉ chạy một lần thay vì mỗi lần đăng ký, hoặc giữ lại dữ liệu cũ ngoài ý muốn.

## 1. Hai giai đoạn trong vòng đời pipeline

Khi viết một biểu thức Reactor, Java thực thi các lời gọi phương thức để tạo Publisher và nối các toán tử. Đây là giai đoạn lắp ráp. Với một nguồn lạnh (cold Publisher), việc tạo pipeline thường chưa thực hiện công việc phát dữ liệu; công việc bắt đầu khi có Subscriber đăng ký và yêu cầu dữ liệu.

```text
Giai đoạn lắp ráp (assembly)
  Mono/Flux nguồn -> map -> filter -> doOn... -> Publisher kết quả
                         |
                         | chưa subscribe: nguồn lạnh chưa chạy
                         v
Giai đoạn đăng ký (subscription)
  Subscriber -> subscribe -> Subscription -> request(n)
                                      |
                                      v
                             nguồn bắt đầu phát tín hiệu
                                      |
                       onNext ... onComplete / onError
```

Lắp ráp và đăng ký có thể xảy ra ở hai thời điểm cách xa nhau. Một pipeline có thể được tạo khi ứng dụng khởi động, lưu trong một field rồi được đăng ký nhiều lần khi có yêu cầu. Vì thế, cần biết chính xác câu lệnh nào thực thi ngay khi tạo pipeline và câu lệnh nào chỉ thực thi trong vòng đời subscription.

Lưu ý: việc tạo Publisher không đồng nghĩa mọi biểu thức Java trong câu lệnh đó đều được trì hoãn. Java đánh giá đối số phương thức trước khi gọi phương thức. Đây là nguyên nhân phổ biến khiến tác dụng phụ xảy ra ngay ở assembly dù ta đang dùng `Mono` hoặc `Flux`.

## 2. Tác dụng phụ xảy ra tại assembly

Xét ví dụ sau:

```java
Mono<String> token = Mono.just(authClient.refreshToken());
```

`authClient.refreshToken()` là lời gọi Java thông thường. Nó được thực thi ngay khi dòng lệnh được chạy để tạo đối số cho `Mono.just`. `Mono.just` giữ lại giá trị đã nhận và phát giá trị đó cho các Subscriber sau này. Vì vậy:

- Token được làm mới ngay khi pipeline được lắp ráp.
- Nếu không có ai subscribe, lời gọi làm mới token vẫn đã xảy ra.
- Nếu cùng một `Mono` được subscribe nhiều lần, các Subscriber nhận giá trị đã được tạo ở assembly; `refreshToken()` không tự chạy lại cho từng subscription.

Điều này có thể phù hợp khi muốn chụp một giá trị cố định tại thời điểm xây dựng pipeline. Tuy nhiên, nó thường sai khi mục tiêu là gọi dịch vụ mỗi lần có yêu cầu.

Một ví dụ khác là tạo dữ liệu ngẫu nhiên hoặc thời gian hiện tại:

```java
Mono<Instant> createdAt = Mono.just(Instant.now());
```

`Instant.now()` được tính ngay tại assembly. Mọi subscription dùng lại Publisher này sẽ nhận cùng một thời điểm đã chụp. Nếu cần thời điểm riêng cho mỗi subscription, hãy trì hoãn việc tính toán.

Tác dụng phụ tại assembly không phải lúc nào cũng sai. Việc tạo một đối tượng bất biến, chuẩn hóa cấu hình hoặc dựng cấu trúc toán tử thường là công việc bình thường ở giai đoạn này. Điều cần tránh là vô tình đặt thao tác I/O hoặc cập nhật trạng thái vào biểu thức được đánh giá ngay khi lắp ráp trong khi nghiệp vụ yêu cầu nó chỉ chạy khi có người đăng ký.

## 3. Trì hoãn công việc đến subscription

Reactor cung cấp các nguồn tạo dữ liệu lười để thực hiện công việc trong vòng đời subscription. Hai công cụ thường dùng là `Mono.fromCallable` và `Mono.defer`.

### Dùng `fromCallable` hoặc `fromSupplier` cho một giá trị

Khi tác dụng phụ tạo ra một giá trị, có thể dùng `Mono.fromCallable`:

```java
Mono<String> token = Mono.fromCallable(authClient::refreshToken);
```

Lời gọi `refreshToken()` được giữ trong Callable và chỉ được thực thi khi subscription yêu cầu dữ liệu. Với một nguồn lạnh như vậy, mỗi subscription độc lập sẽ gọi Callable để tạo kết quả mới.

`Mono.fromSupplier` cũng phù hợp khi công việc được biểu diễn bằng `Supplier` và không cần khai báo checked exception:

```java
Mono<Instant> createdAt = Mono.fromSupplier(Instant::now);
```

Callable có thể ném checked exception; Reactor chuyển ngoại lệ đó thành `onError`. Nếu Callable hoặc Supplier trả về `null`, Mono hoàn tất rỗng thay vì phát một phần tử `null`, vì Reactive Streams không cho phép `null` làm dữ liệu.

### Dùng `defer` khi cần tạo Publisher cho từng subscription

Nếu phương thức nghiệp vụ đã trả về `Mono` hoặc `Flux`, hãy dùng `defer` để trì hoãn cả việc gọi phương thức tạo Publisher:

```java
Mono<Customer> customer = Mono.defer(
    () -> customerRepository.findById(customerId)
);
```

Hàm bên trong `defer` được gọi khi có subscription. Publisher trả về từ hàm đó được nối vào subscription tương ứng. Điều này hữu ích khi mỗi lần đăng ký cần tạo một nguồn mới, đọc trạng thái hiện tại hoặc lựa chọn nhánh xử lý dựa trên dữ liệu tại thời điểm chạy.

Với `Flux`, cách dùng tương tự:

```java
Flux<Event> events = Flux.defer(
    () -> eventStore.readFrom(checkpointService.currentCheckpoint())
);
```

Ở mỗi subscription, Reactor gọi hàm tạo Publisher và lấy checkpoint tại thời điểm đó. Nếu viết lời gọi `checkpointService.currentCheckpoint()` bên ngoài `defer`, checkpoint sẽ được đọc ngay khi lắp ráp.

## 4. So sánh các cách tạo nguồn

| Cách tạo nguồn | Khi nào biểu thức công việc được gọi? | Hành vi khi subscribe nhiều lần |
|---|---|---|
| `Mono.just(value)` | `value` được tính trước khi gọi `just`, tại assembly | Phát lại giá trị đã giữ |
| `Mono.fromCallable(callable)` | Khi subscription yêu cầu dữ liệu | Callable được gọi cho mỗi subscription độc lập |
| `Mono.fromSupplier(supplier)` | Khi subscription yêu cầu dữ liệu | Supplier được gọi cho mỗi subscription độc lập |
| `Mono.defer(factory)` | Factory được gọi khi subscribe | Tạo Publisher cho từng subscription |
| `Flux.defer(factory)` | Factory được gọi khi subscribe | Tạo Publisher cho từng subscription |

`defer` trì hoãn việc tạo Publisher bên trong, nhưng không tự biến mọi nguồn bên trong thành cold source. Nếu factory luôn trả về cùng một hot Publisher hoặc Publisher đã được chia sẻ, các subscription vẫn tuân theo ngữ nghĩa của nguồn đó.

## 5. Callback quan sát vòng đời subscription và tín hiệu

Không phải mọi tác dụng phụ trong pipeline đều là công việc tạo nguồn. Reactor có các toán tử `doOn...` để quan sát những sự kiện trong vòng đời. Các callback này phù hợp cho logging, metrics, tracing và cập nhật trạng thái phụ trợ.

```java
Mono<Customer> customer = Mono.defer(
        () -> customerRepository.findById(customerId)
    )
    .doOnSubscribe(subscription -> log.info("Customer lookup subscribed"))
    .doOnNext(value -> log.info("Customer found: {}", value.id()))
    .doOnError(error -> log.error("Customer lookup failed", error))
    .doOnSuccess(value -> log.info("Customer lookup completed"))
    .doFinally(signal -> log.info("Lookup finished: {}", signal));
```

Các callback được kích hoạt theo sự kiện tương ứng:

| Toán tử | Thời điểm callback |
|---|---|
| `doFirst` | Khi subscription bắt đầu, trước khi tín hiệu subscribe được chuyển lên nguồn |
| `doOnSubscribe` | Khi toán tử nhận được Subscription từ upstream |
| `doOnRequest` | Khi downstream gửi yêu cầu demand qua subscription |
| `doOnNext` | Khi phần tử đi qua vị trí đặt toán tử |
| `doOnComplete` | Khi upstream hoàn tất bình thường |
| `doOnError` | Khi upstream phát lỗi |
| `doFinally` | Sau khi luồng kết thúc hoặc bị hủy; callback nhận loại tín hiệu kết thúc |

Các callback quan sát không thay thế việc xử lý dữ liệu. Ví dụ, `doOnError` cho phép ghi log lỗi nhưng không khôi phục luồng. Muốn thay lỗi bằng kết quả khác, cần toán tử xử lý như `onErrorResume` hoặc `onErrorReturn`.

Với `Mono`, `doOnSuccess` chạy khi Mono hoàn tất thành công. Tham số của callback là giá trị phát ra, hoặc `null` nếu Mono hoàn tất rỗng. `null` ở đây chỉ là giá trị callback dùng để biểu thị không có phần tử; Mono không phát `null` qua `onNext`.

`doFinally` đặc biệt hữu ích để giải phóng tài nguyên hoặc ghi nhận kết quả vòng đời vì nó nhận cả tín hiệu hoàn tất, lỗi và hủy. Nếu chỉ dùng `doOnComplete` hoặc `doOnError`, trường hợp Subscriber gọi `cancel()` sẽ không được quan sát bằng các callback đó.

## 6. Một pipeline có thể được subscribe nhiều lần

Mỗi lần gọi `subscribe` tạo một subscription mới. Với nguồn lạnh, công việc nguồn thường được thực hiện lại cho từng subscription. Ví dụ:

```java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> lazyValue = Mono.fromSupplier(calls::incrementAndGet);

lazyValue.subscribe(value -> log.info("first = {}", value));
lazyValue.subscribe(value -> log.info("second = {}", value));
```

Hai subscription độc lập lần lượt nhận `1` và `2`, vì Supplier được gọi lại mỗi lần. Nếu thay nguồn bằng `Mono.just(calls.incrementAndGet())`, bộ đếm tăng một lần tại assembly và cùng giá trị được phát cho cả hai subscription.

Đây là điểm cần cân nhắc khi pipeline thực hiện thanh toán, gửi email, tạo đơn hàng hoặc cập nhật dữ liệu. Việc subscribe hai lần vào một nguồn lạnh có thể thực hiện nghiệp vụ hai lần. Cần kiểm soát nơi gọi `subscribe`, tránh tạo subscription trùng lặp và dùng cơ chế idempotency ở ranh giới nghiệp vụ khi phù hợp.

Không phải mọi Publisher đều là cold. Một hot Publisher có thể phát dữ liệu độc lập với từng Subscriber; các toán tử chia sẻ hoặc lưu kết quả như `share` và `cache` cũng thay đổi cách các subscription dùng chung nguồn hoặc kết quả. Vì vậy, không nên suy luận rằng mọi lần subscribe đều gọi lại toàn bộ tác dụng phụ upstream. Hãy xác định ngữ nghĩa nguồn và các toán tử chia sẻ đang sử dụng.

## 7. Kết hợp lazy evaluation với scheduler

Trì hoãn công việc và chọn scheduler là hai quyết định khác nhau. `fromCallable` hoặc `defer` quyết định **khi nào** công việc được tạo hoặc thực thi theo subscription. `subscribeOn` và `publishOn` quyết định **ở đâu** một phần công việc được thực thi trong Reactor.

Với một client cũ thực hiện I/O blocking, có thể kết hợp như sau:

```java
Mono<Response> response = Mono.fromCallable(
        () -> legacyClient.fetch(requestId)
    )
    .subscribeOn(Schedulers.boundedElastic());
```

Callable trì hoãn lời gọi đến subscription; `subscribeOn` chuyển quá trình thực thi nguồn sang scheduler phù hợp cho tác vụ blocking. Chỉ thêm `subscribeOn` không làm cho biểu thức Java đã chạy ở assembly trở nên lazy:

```java
// fetch() vẫn chạy ngay khi lắp ráp pipeline.
Mono<Response> wrong = Mono.just(legacyClient.fetch(requestId))
    .subscribeOn(Schedulers.boundedElastic());
```

Trong ví dụ sai, `fetch` được đánh giá trước khi `Mono.just` được gọi. Scheduler chỉ tác động đến subscription của Publisher đã được tạo sau đó; nó không thể chuyển ngược lời gọi đã xảy ra ở assembly sang một thread khác.

Đối với API vốn đã reactive và non-blocking, hãy ưu tiên sử dụng trực tiếp Publisher mà API trả về. Không cần bọc một Publisher reactive trong `fromCallable`; dùng `defer` nếu cần trì hoãn việc gọi phương thức tạo Publisher.

## 8. Những lỗi thường gặp và cách khắc phục

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| API bị gọi dù không có ai subscribe | Lời gọi nằm trong đối số của `Mono.just` hoặc `Flux.just` | Dùng `fromCallable`, `fromSupplier` hoặc `defer` |
| Nhiều Subscriber nhận cùng một kết quả cũ | Giá trị đã được chụp tại assembly bằng `just` | Tạo giá trị trong nguồn lazy nếu cần kết quả mới mỗi subscription |
| Nghiệp vụ chạy hai lần | Có hai subscription độc lập vào nguồn lạnh | Kiểm tra nơi subscribe, chia sẻ nguồn có chủ đích hoặc bảo vệ nghiệp vụ bằng idempotency |
| Tác vụ blocking vẫn chạy trên thread gọi lắp ráp | Lời gọi blocking đã được thực hiện trước `subscribeOn` | Đặt lời gọi bên trong `fromCallable` rồi chọn scheduler phù hợp |
| Chỉ ghi log lỗi nhưng pipeline vẫn lỗi | `doOnError` chỉ quan sát tín hiệu lỗi | Dùng `onErrorResume` hoặc toán tử phục hồi khi cần thay đổi luồng |

## 9. Kiểm thử thời điểm thực thi

Có thể dùng `AtomicInteger` để xác nhận công việc chưa chạy khi assembly, chạy khi subscription và được gọi lại với từng subscription:

```java
AtomicInteger executions = new AtomicInteger();

Mono<Integer> source = Mono.fromCallable(executions::incrementAndGet);

assertEquals(0, executions.get()); // mới assembly, chưa subscribe

StepVerifier.create(source)
    .expectNext(1)
    .verifyComplete();

assertEquals(1, executions.get());

StepVerifier.create(source)
    .expectNext(2)
    .verifyComplete();

assertEquals(2, executions.get());
```

Để kiểm tra khác biệt với `Mono.just`, có thể tạo giá trị trước khi dựng Publisher:

```java
AtomicInteger eagerExecutions = new AtomicInteger();

Mono<Integer> eager = Mono.just(eagerExecutions.incrementAndGet());

assertEquals(1, eagerExecutions.get()); // đã chạy tại assembly

StepVerifier.create(eager)
    .expectNext(1)
    .verifyComplete();

StepVerifier.create(eager)
    .expectNext(1)
    .verifyComplete();

assertEquals(1, eagerExecutions.get());
```

Các kiểm thử này làm rõ sự khác nhau giữa tạo Publisher và kích hoạt nguồn. Trong dự án thực tế, có thể mở rộng bằng cách kiểm tra callback `doOnSubscribe`, số lần gọi repository giả lập, hành vi khi cancel và việc không gọi nguồn khi subscription không yêu cầu dữ liệu.

## 10. Quy tắc lựa chọn

- Dùng `Mono.just` hoặc `Flux.just` khi giá trị đã có sẵn tại assembly và việc phát lại đúng giá trị đó là chủ đích.
- Dùng `fromCallable` hoặc `fromSupplier` khi cần tạo một giá trị theo từng subscription.
- Dùng `defer` khi cần tạo Publisher hoặc quyết định nguồn cho từng subscription.
- Dùng `doOn...` để quan sát tín hiệu và vòng đời; dùng toán tử biến đổi hoặc xử lý lỗi khi cần thay đổi kết quả pipeline.
- Dùng scheduler phù hợp cho tác vụ blocking, nhưng đặt lời gọi blocking bên trong nguồn lazy trước khi chọn scheduler.
- Xác định rõ cold, hot, shared và cached source trước khi giả định số lần tác dụng phụ được thực hiện.

Khi xem một pipeline, hãy lần theo biểu thức Java được đánh giá ở assembly, nguồn được tạo ở subscription và các callback chạy theo tín hiệu. Phân biệt được ba vị trí này giúp kiểm soát số lần thực thi tác dụng phụ, tránh gọi dịch vụ quá sớm và giữ cho vòng đời `Publisher–Subscriber` có thể dự đoán được.
