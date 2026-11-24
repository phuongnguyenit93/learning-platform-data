# Mỗi đăng ký tạo một lần thực thi hay dùng chung một nguồn

Trong Reactive Streams, mỗi lần gọi `subscribe` đều tạo một subscription riêng giữa publisher và subscriber tương ứng. Tuy nhiên, điều đó không có nghĩa mọi lần đăng ký đều khởi chạy một nguồn dữ liệu độc lập. Kết quả phụ thuộc vào cách publisher được xây dựng: nguồn *cold* thường tạo luồng dữ liệu mới cho từng subscriber, còn nguồn *hot* có thể phát một luồng sự kiện đang diễn ra cho nhiều subscriber cùng quan sát.

Sự khác biệt này ảnh hưởng trực tiếp đến số lần gọi dịch vụ, việc có nhận lại dữ liệu cũ hay không, cách hủy subscription và cách điều phối backpressure. Trong module `REACTIVE_PROGRAMMING`, người học thực hành các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams, đồng thời sử dụng `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline Java. Hiểu đúng vòng đời subscription giúp chọn được cách chia sẻ nguồn phù hợp cho từng pipeline.

## 1. Hai câu hỏi cần tách biệt

Khi có nhiều subscriber, hãy phân biệt hai điều:

- **Subscription downstream:** mỗi subscriber có `Subscription` riêng, có thể gọi `request(n)` và `cancel()` độc lập.
- **Subscription upstream:** publisher có thể tạo một lần đăng ký mới lên nguồn cho mỗi subscriber, hoặc chia sẻ một subscription upstream giữa nhiều subscriber.

Vì vậy, hai subscriber luôn có hai quan hệ downstream riêng, nhưng chúng có thể cùng nhận dữ liệu từ một lần thực thi upstream.

```text
Cold: mỗi subscriber có một lần thực thi nguồn

Subscriber A <-- Subscription A <-- Nguồn chạy lần 1
Subscriber B <-- Subscription B <-- Nguồn chạy lần 2

Shared: nhiều subscriber dùng chung một lần thực thi nguồn

Subscriber A <-- Subscription A --+
                                  +--> Một subscription upstream --> Nguồn
Subscriber B <-- Subscription B --+
```

Sơ đồ shared mô tả cách chia sẻ một nguồn upstream. Mỗi subscriber vẫn có demand và vòng đời downstream riêng; publisher chịu trách nhiệm phân phối tín hiệu theo chính sách của operator hoặc sink.

## 2. Nguồn cold: mỗi subscriber có một luồng dữ liệu riêng

Một publisher cold thường bắt đầu tạo hoặc lấy dữ liệu khi có subscriber. Mỗi lần đăng ký mới sẽ tạo một lần thực thi upstream mới và subscriber đó nhận chuỗi dữ liệu của riêng mình, thường bắt đầu từ đầu.

Các nguồn như `Flux.range`, `Flux.fromIterable` và `Mono.fromCallable` thường phù hợp với mô hình này. Ví dụ:

```java
AtomicInteger execution = new AtomicInteger();

Flux<Integer> cold = Flux.defer(() -> {
    int runId = execution.incrementAndGet();
    System.out.println("Start source run " + runId);
    return Flux.range(1, 3)
        .map(value -> runId * 10 + value);
});

cold.subscribe(value -> System.out.println("A: " + value));
cold.subscribe(value -> System.out.println("B: " + value));
```

Mỗi lần `subscribe` gọi supplier bên trong `defer` một lần. Subscriber A nhận `11, 12, 13`; subscriber B nhận `21, 22, 23`. Nguồn được tạo riêng cho từng lần đăng ký.

### `defer` và thời điểm tạo dữ liệu

Không phải mọi biểu thức đặt cạnh `Mono` hoặc `Flux` đều được thực thi khi subscriber đăng ký. Ví dụ:

```java
Mono<Profile> eager = Mono.just(loadProfile());

Mono<Profile> lazy = Mono.defer(() ->
    Mono.just(loadProfile())
);
```

`loadProfile()` trong `Mono.just(loadProfile())` được gọi ngay khi biểu thức tạo publisher được thực thi. Các subscriber sau đó nhận lại giá trị đã được chụp tại thời điểm assembly. `Mono.just` không gọi lại `loadProfile()` cho từng subscriber.

Với `Mono.defer`, supplier được gọi khi có subscription; mỗi subscription gọi supplier một lần. `Mono.fromCallable` cũng phù hợp khi muốn thực thi một lời gọi đồng bộ theo từng subscription:

```java
Mono<Profile> lazyCall = Mono.fromCallable(this::loadProfile);
```

Nếu `loadProfile` là thao tác blocking, hãy đặt nó trên scheduler dành cho tác vụ blocking, chẳng hạn:

```java
Mono<Profile> profile = Mono.fromCallable(this::loadProfile)
    .subscribeOn(Schedulers.boundedElastic());
```

### Khi nào nên chọn cold?

- Mỗi người dùng hoặc mỗi yêu cầu cần kết quả riêng.
- Mỗi subscriber phải đọc lại toàn bộ dữ liệu từ đầu.
- Một thao tác cần được thực thi lại cho mỗi lần đăng ký, chẳng hạn truy vấn theo ngữ cảnh riêng.
- Muốn việc hủy một subscription chỉ ảnh hưởng đến lần thực thi tương ứng.

Hãy chú ý tác dụng phụ. Nếu một cold `Mono` bọc thao tác ghi cơ sở dữ liệu, hai lần đăng ký có thể thực hiện thao tác ghi hai lần. Nếu một cold `Flux` gọi API bên ngoài, mỗi subscriber có thể tạo thêm một yêu cầu mạng. Việc gọi `subscribe` nhiều lần vì thế có thể làm tăng chi phí hoặc lặp lại thao tác nghiệp vụ.

## 3. Nguồn hot: subscriber tham gia vào luồng sự kiện đang diễn ra

Nguồn hot đại diện cho một luồng sự kiện tồn tại độc lập với từng subscriber. Một sự kiện có thể được phát ra khi chưa có subscriber hoặc trước khi một subscriber mới tham gia. Subscriber đến sau thường chỉ nhận các sự kiện từ thời điểm tham gia, trừ khi nguồn có cơ chế lưu và phát lại lịch sử.

Ví dụ thường gặp là sự kiện chuột, cập nhật giá, thông báo trạng thái kết nối hoặc sự kiện từ message broker. Trong Reactor, có thể dùng `Sinks` để tạo một nguồn phát chủ động:

```java
Sinks.Many<String> bus = Sinks.many()
    .multicast()
    .onBackpressureBuffer();

Flux<String> liveEvents = bus.asFlux();

liveEvents.subscribe(value -> System.out.println("A: " + value));

Sinks.EmitResult first = bus.tryEmitNext("order-created");
if (first != Sinks.EmitResult.OK) {
    throw new IllegalStateException("Cannot emit first event: " + first);
}

liveEvents.subscribe(value -> System.out.println("B: " + value));

Sinks.EmitResult second = bus.tryEmitNext("order-shipped");
if (second != Sinks.EmitResult.OK) {
    throw new IllegalStateException("Cannot emit second event: " + second);
}
```

Subscriber A nhận cả `order-created` và `order-shipped`. Subscriber B tham gia sau sự kiện đầu tiên nên chỉ nhận `order-shipped`. Sink multicast này phát đến các subscriber hiện tại; nó không tự phát lại toàn bộ lịch sử cho subscriber đến muộn.

### Hot không nhất thiết phải bỏ toàn bộ lịch sử

Nếu subscriber mới cần một phần lịch sử gần nhất, có thể dùng replay sink:

```java
Sinks.Many<String> recentEvents = Sinks.many()
    .replay()
    .limit(2);

recentEvents.tryEmitNext("created");
recentEvents.tryEmitNext("paid");
recentEvents.tryEmitNext("shipped");

recentEvents.asFlux().subscribe(System.out::println);
```

Subscriber đăng ký sau sẽ nhận hai sự kiện gần nhất (`paid`, `shipped`) rồi tiếp tục nhận sự kiện mới. Giới hạn lịch sử giúp kiểm soát bộ nhớ và xác định rõ dữ liệu nào còn có thể được phát lại.

## 4. Chia sẻ một nguồn cold bằng `publish`, `share` và `cache`

Một nguồn cold có thể được chuyển thành nguồn dùng chung. Khi đó, nhiều subscriber cùng tham gia một lần thực thi upstream thay vì mỗi người khởi chạy một lần riêng. Các operator chia sẻ có chính sách kết nối và lưu lịch sử khác nhau.

### `publish`: chủ động quyết định thời điểm kết nối

`publish()` tạo một `ConnectableFlux`. Subscriber có thể đăng ký trước, sau đó ứng dụng gọi `connect()` để bắt đầu nguồn upstream:

```java
ConnectableFlux<Integer> connectable = Flux.range(1, 3)
    .doOnSubscribe(s -> System.out.println("Upstream subscribed"))
    .publish();

connectable.subscribe(value -> System.out.println("A: " + value));
connectable.subscribe(value -> System.out.println("B: " + value));

connectable.connect();
```

Nguồn chỉ được đăng ký khi `connect()` được gọi. Vì cả A và B đã đăng ký trước khi kết nối, cả hai nhận các giá trị `1, 2, 3` từ cùng một lần thực thi upstream. Nếu subscriber đến sau khi nguồn đã phát một số phần tử, `publish()` không tự phát lại các phần tử trước đó.

`connect()` hữu ích khi ứng dụng cần kiểm soát chính xác thời điểm bắt đầu phát, chẳng hạn chờ đủ các subscriber quan sát đã sẵn sàng.

### `share`: tự kết nối khi có subscriber

`share()` chia sẻ một subscription upstream cho các subscriber cùng tham gia vào nguồn đang chạy. Nguồn được kết nối khi subscriber đầu tiên đến. Với nguồn đang hoạt động, subscriber đến sau tham gia vào luồng hiện tại và không nhận lại các sự kiện đã phát trước thời điểm đăng ký.

```java
Flux<Long> sharedClock = Flux.interval(Duration.ofMillis(500))
    .doOnSubscribe(s -> System.out.println("Clock source subscribed"))
    .share();

Disposable first = sharedClock.subscribe(value ->
    System.out.println("A: " + value)
);

Disposable second = sharedClock.subscribe(value ->
    System.out.println("B: " + value)
);
```

Hai subscriber cùng quan sát một clock source đang chạy. Mỗi subscriber có thể hủy subscription của mình bằng `dispose()`. Khi subscriber cuối cùng rời khỏi một nguồn đang hoạt động, cơ chế `refCount` bên dưới `share()` có thể ngắt subscription upstream. Với nguồn hữu hạn đã kết thúc, cần xem xét riêng hành vi terminal signal và vòng đời của lần kết nối đó.

### `autoConnect` và `refCount`: điều khiển vòng đời kết nối

Có thể điều chỉnh số subscriber cần thiết trước khi nguồn bắt đầu:

```java
Flux<Event> sharedAfterTwoSubscribers = eventSource
    .publish()
    .autoConnect(2);
```

`autoConnect(2)` kết nối upstream khi có đủ hai subscriber. Sau khi kết nối, nó không tự ngắt chỉ vì số subscriber giảm xuống dưới hai.

Nếu muốn kết nối và ngắt kết nối theo số subscriber đang hoạt động, dùng `refCount`:

```java
Flux<Event> sharedWhileObserved = eventSource
    .publish()
    .refCount(2);
```

Với `refCount(2)`, nguồn được kết nối khi số subscriber đạt ngưỡng hai và bị ngắt khi số subscriber giảm xuống dưới ngưỡng. `share()` là cách viết ngắn cho trường hợp chia sẻ với ngưỡng một subscriber. Một số overload của `refCount` cho phép thêm khoảng chờ trước khi ngắt kết nối để tránh kết nối lại liên tục khi subscriber đến và rời đi sát nhau.

### `cache`: thực thi một lần và phát lại kết quả

`cache()` giữ lại các tín hiệu đã nhận để subscriber đến sau có thể nhận lại chúng. Subscriber đầu tiên kích hoạt nguồn; các subscriber tiếp theo nhận dữ liệu đã cache và tiếp tục nhận tín hiệu mới nếu nguồn còn hoạt động.

```java
Mono<Configuration> cachedConfig = Mono.fromCallable(this::loadConfiguration)
    .cache();

cachedConfig.subscribe(config -> System.out.println("A: " + config));
cachedConfig.subscribe(config -> System.out.println("B: " + config));
```

Với `Mono.cache()`, kết quả terminal của nguồn được lưu để những lần đăng ký sau nhận lại. Điều này có thể tránh gọi lại một thao tác tải cấu hình, nhưng cũng có nghĩa dữ liệu có thể cũ nếu cấu hình thay đổi.

Với `Flux`, có thể giới hạn số phần tử lịch sử được giữ:

```java
Flux<Event> recent = eventSource.cache(100);
```

Subscriber đến muộn nhận tối đa 100 phần tử đã lưu gần nhất rồi theo dõi các phần tử mới. Cần cân nhắc TTL hoặc giới hạn lịch sử khi dữ liệu có thể tăng liên tục. `cache()` không giới hạn trên một `Flux` dài vô hạn có thể giữ lại quá nhiều dữ liệu trong bộ nhớ.

## 5. So sánh các lựa chọn

| Cách tạo nguồn | Lần thực thi upstream | Subscriber đến muộn | Vòng đời chia sẻ |
|---|---|---|---|
| Cold publisher | Mỗi subscriber thường tạo một lần thực thi riêng. | Nhận chuỗi dữ liệu riêng, thường từ đầu. | Mỗi subscription có vòng đời upstream riêng. |
| Hot multicast | Nguồn phát theo dòng sự kiện đang diễn ra. | Thường chỉ nhận sự kiện từ lúc tham gia. | Nguồn có thể tiếp tục phát độc lập với một subscriber cụ thể. |
| `publish().connect()` | Một lần cho mỗi lần kết nối. | Không tự nhận lại tín hiệu đã phát. | Ứng dụng chủ động gọi `connect()`. |
| `share()` | Dùng chung lần upstream đang hoạt động. | Tham gia phần còn lại của luồng. | Tự kết nối; có thể ngắt khi subscriber cuối cùng rời nguồn đang chạy. |
| `publish().autoConnect(n)` | Một lần sau khi đạt ngưỡng subscriber. | Nhận phần dữ liệu từ lúc tham gia. | Kết nối sau ngưỡng và giữ kết nối sau đó. |
| `publish().refCount(n)` | Một lần trong mỗi giai đoạn kết nối. | Nhận phần dữ liệu từ lúc tham gia. | Kết nối khi đạt ngưỡng, ngắt khi số subscriber xuống dưới ngưỡng. |
| `cache()` | Nguồn được kích hoạt để nạp cache; subscriber sau dùng dữ liệu đã lưu. | Nhận lại lịch sử trong phạm vi cache. | Lịch sử được giữ theo chính sách cache/TTL. |

Không nên chọn chỉ dựa vào số lần thực thi. Hãy xác định subscriber cần nhận toàn bộ dữ liệu hay chỉ sự kiện mới, chi phí nguồn là bao nhiêu, và khi nào nguồn được phép dừng.

## 6. Backpressure khi nhiều subscriber dùng chung nguồn

Mỗi subscriber vẫn có demand riêng. Ví dụ, subscriber A gọi `request(10)` trong khi subscriber B mới gọi `request(1)`. Khi hai subscriber dùng chung một nguồn upstream, publisher phải phối hợp nhu cầu của chúng theo chính sách chia sẻ.

Với các operator multicast có hỗ trợ backpressure như `publish` và `share`, nhu cầu của các subscriber có thể ảnh hưởng đến tốc độ phát upstream. Một subscriber chậm có thể làm nguồn tạm dừng hoặc làm tăng lượng phần tử phải chờ, tùy operator và cấu hình. Với `Sinks`, hành vi còn phụ thuộc loại sink và chiến lược overflow.

Một số lựa chọn thường gặp:

- **Buffer:** giữ phần tử cho subscriber xử lý chậm; phải giới hạn dung lượng hoặc có chính sách quá tải.
- **Drop:** bỏ phần tử không thể chuyển xuống theo chính sách đã chọn; chỉ phù hợp nếu mất sự kiện được nghiệp vụ chấp nhận.
- **Latest:** giữ giá trị mới nhất, phù hợp với trạng thái có thể thay thế giá trị cũ như nhiệt độ hoặc vị trí hiện tại.
- **Error:** báo lỗi khi không thể tiếp nhận thêm dữ liệu.

Đối với sự kiện đơn hàng, thanh toán hoặc kiểm toán, bỏ sự kiện có thể làm sai dữ liệu nghiệp vụ. Cần chọn buffer có giới hạn, lưu trữ bền vững hoặc điều tiết producer. Với dữ liệu trạng thái liên tục, `LATEST` đôi khi phù hợp hơn vì subscriber chỉ cần trạng thái mới nhất.

Hủy một subscription downstream cũng cần được hiểu trong bối cảnh chia sẻ. Với nguồn cold, hủy subscriber thường hủy lần thực thi upstream riêng của subscriber đó. Với `share`/`refCount`, hủy một subscriber không nên làm dừng nguồn khi các subscriber khác vẫn còn tham gia; nguồn được ngắt theo ngưỡng vòng đời đã cấu hình. Với `autoConnect`, kết nối có thể tiếp tục ngay cả khi không còn subscriber. Với cache, mục tiêu là giữ kết quả cho các lần đăng ký sau, nên chính sách hủy và lưu cache khác với chia sẻ trực tiếp.

## 7. Kiểm thử số lần thực thi và hành vi phát lại

Có thể dùng `AtomicInteger` để quan sát số lần supplier được gọi, kết hợp `StepVerifier` để kiểm tra kết quả.

### Cold: mỗi subscription gọi supplier một lần

```java
AtomicInteger executions = new AtomicInteger();

Mono<Integer> cold = Mono.defer(() ->
    Mono.just(executions.incrementAndGet())
);

StepVerifier.create(cold)
    .expectNext(1)
    .verifyComplete();

StepVerifier.create(cold)
    .expectNext(2)
    .verifyComplete();

assertEquals(2, executions.get());
```

Hai lần verify tạo hai subscription, vì vậy supplier được gọi hai lần.

### Cache: các subscription dùng chung kết quả đã nạp

```java
AtomicInteger loads = new AtomicInteger();

Mono<Integer> cached = Mono.defer(() ->
    Mono.just(loads.incrementAndGet())
).cache();

StepVerifier.create(cached)
    .expectNext(1)
    .verifyComplete();

StepVerifier.create(cached)
    .expectNext(1)
    .verifyComplete();

assertEquals(1, loads.get());
```

Subscription đầu tiên kích hoạt supplier. Subscription thứ hai nhận kết quả đã cache, vì vậy `loads` vẫn bằng một.

Khi kiểm thử `share()` hoặc sink multicast, cần kiểm tra cả thời điểm subscriber tham gia. Một kiểm thử hữu ích nên xác minh subscriber đầu tiên nhận sự kiện nào, subscriber đến muộn bỏ lỡ sự kiện nào, và nguồn có dừng khi subscriber cuối cùng hủy hay không. Với nguồn bất đồng bộ, hãy dùng scheduler ảo hoặc tín hiệu đồng bộ hóa phù hợp để tránh phụ thuộc vào thời gian chạy ngẫu nhiên.

## 8. Tình huống thực tế: nhiều màn hình cùng theo dõi trạng thái đơn hàng

Một dịch vụ nhận sự kiện trạng thái đơn hàng từ message broker. Nhiều màn hình quản trị cùng theo dõi một đơn hàng. Mỗi màn hình không cần tạo một kết nối broker riêng; chúng cần quan sát cùng một luồng cập nhật trong thời gian màn hình hoạt động.

Một thiết kế có thể thực hiện như sau:

1. Tạo một nguồn adapter từ message broker, phát sự kiện theo cơ chế hot multicast.
2. Chia sẻ subscription upstream trong phạm vi một đơn hàng hoặc một nhóm subscriber quan sát.
3. Mỗi màn hình có subscription downstream riêng và có thể hủy khi người dùng rời màn hình.
4. Nếu màn hình mới cần trạng thái hiện tại ngay khi mở, cung cấp một snapshot hoặc replay giới hạn trước khi tiếp tục nhận sự kiện mới.
5. Chọn chính sách backpressure để subscriber chậm không làm mất dữ liệu quan trọng hoặc khiến bộ đệm tăng không kiểm soát.

Một lựa chọn khác là giữ nguồn repository ở dạng cold khi mỗi yêu cầu cần tải snapshot độc lập, sau đó kết hợp snapshot với một luồng hot chứa các cập nhật tiếp theo. Cách này tách rõ hai nhu cầu: lấy trạng thái hiện tại và theo dõi sự kiện mới.

## 9. Quy trình chọn mô hình subscription

Trước khi gọi `subscribe` ở nhiều nơi, hãy trả lời lần lượt:

1. Mỗi subscriber có cần nhận lại toàn bộ dữ liệu từ đầu không? Nếu có, giữ nguồn cold.
2. Nguồn có đại diện cho sự kiện đang diễn ra mà subscriber chỉ cần quan sát từ lúc tham gia không? Nếu có, dùng hot multicast.
3. Nhiều subscriber đồng thời có cần dùng chung một lần gọi upstream không? Cân nhắc `share`, `publish` hoặc `refCount`.
4. Subscriber đến muộn có cần nhận lại lịch sử không? Cân nhắc `replay` hoặc `cache` với giới hạn/TTL phù hợp.
5. Khi subscriber cuối cùng rời đi, nguồn phải tiếp tục hay dừng? Chọn `autoConnect`, `refCount` hoặc vòng đời sink tương ứng.
6. Nếu một subscriber xử lý chậm, nguồn sẽ buffer, drop, giữ latest hay báo lỗi? Chọn chính sách theo yêu cầu dữ liệu và giới hạn tài nguyên.

Một nguyên tắc thực hành quan trọng là chỉ gọi `subscribe` tại ranh giới thực sự cần bắt đầu xử lý hoặc kết nối với hệ thống bên ngoài. Ở phần lớn pipeline ứng dụng, nên trả về `Mono` hoặc `Flux` để tầng gọi quyết định thời điểm và số lần đăng ký. Việc gọi `subscribe` sớm bên trong service có thể làm mất quyền kiểm soát vòng đời, lỗi và backpressure của tầng sử dụng.

Khi phân biệt rõ subscription downstream với subscription upstream, người thiết kế có thể quyết định chính xác lúc nào cần thực thi riêng, lúc nào nên chia sẻ nguồn và lúc nào phải phát lại lịch sử. Đây là nền tảng để quản lý chi phí, tính nhất quán và vòng đời của các pipeline reactive.
