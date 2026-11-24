# Nhiều bên đăng ký và việc phát sinh lặp lại tác vụ bên ngoài

## Vì sao nhiều subscription có thể tạo ra nhiều tác vụ?

Trong Reactor, `Mono` và `Flux` mô tả một nguồn dữ liệu cùng các bước xử lý. Khi một bên gọi `subscribe`, publisher thiết lập một subscription và pipeline bắt đầu thực thi theo hợp đồng Reactive Streams. Nếu cùng một publisher được nhiều subscriber đăng ký, nguồn có thể được thực thi nhiều lần.

Điều này đặc biệt quan trọng khi nguồn đại diện cho một tác vụ bên ngoài: truy vấn cơ sở dữ liệu, gọi HTTP, đọc file, gửi thông báo hoặc tạo giao dịch. Một pipeline có thể trông như một biến dùng chung trong Java, nhưng việc dùng chung tham chiếu publisher không đồng nghĩa với việc dùng chung một lần thực thi.

Ví dụ:

```java
Mono<Product> product = Mono.defer(() -> productClient.findById(productId));

product.subscribe(this::showProduct);
product.subscribe(this::writeAuditLog);
```

Với nguồn cold như `Mono.defer`, mỗi lần đăng ký gọi lại supplier và tạo một lần thực thi mới. Đoạn mã trên có thể gửi hai request đến dịch vụ sản phẩm: một lần cho giao diện và một lần cho audit. Nếu lời gọi bên ngoài tốn chi phí, có side effect hoặc trả về dữ liệu thay đổi theo thời gian, việc lặp lại có thể gây tải thừa hoặc tạo kết quả không nhất quán.

Để hiểu hành vi này, cần phân biệt **publisher** với **subscription**. Publisher mô tả cách tạo và chuyển dữ liệu; subscription là một lần tham gia cụ thể vào luồng dữ liệu, có demand và trạng thái hủy riêng.

## Nguồn cold: mỗi subscriber thường có một lần chạy riêng

Nguồn cold chỉ bắt đầu tạo hoặc phát dữ liệu khi có subscription. Mỗi subscriber thường nhận một lần thực thi độc lập, bắt đầu từ đầu nguồn. Các nguồn thường gặp như `Mono.fromCallable`, `Mono.defer`, `Flux.defer`, `Flux.fromIterable` và `Flux.range` có hành vi cold.

`fromCallable` trì hoãn lời gọi hàm đến khi có subscription, nhưng không tự chia sẻ kết quả giữa các subscriber:

```java
Mono<Account> account = Mono.fromCallable(
    () -> accountRepository.loadAccount(accountId)
);

account.subscribe(this::updateScreen);
account.subscribe(this::recordUsage);
```

Nếu cả hai subscriber đăng ký, `loadAccount` có thể được gọi hai lần. Đây là đặc tính hữu ích khi mỗi subscriber cần một lần đọc độc lập, nhưng cần được nhận diện khi nguồn chứa side effect hoặc lời gọi I/O đắt đỏ.

`defer` cũng tạo nguồn theo từng subscription. Nó hữu ích khi cần đọc trạng thái mới hoặc xây dựng publisher phụ thuộc vào thời điểm đăng ký:

```java
Mono<Quote> quote = Mono.defer(() -> pricingClient.fetchQuote(symbol));
```

Mỗi subscriber gọi `fetchQuote` tại thời điểm đăng ký của mình. Nếu muốn các subscriber cùng nhận một kết quả của một lần gọi, cần chọn cơ chế chia sẻ hoặc lưu đệm phù hợp.

### `just` và `defer` có thời điểm đánh giá khác nhau

`Mono.just(value)` giữ lại giá trị đã được tính tại thời điểm tạo publisher. Biểu thức dùng để tạo `value` được Java đánh giá ngay lúc đó:

```java
import reactor.core.publisher.Mono;

Mono<Config> captured = Mono.just(configService.load());
```

Trong ví dụ này, `configService.load()` được gọi một lần khi dòng lệnh được thực thi. Các subscriber sau đó nhận cùng giá trị đã giữ lại trong `Mono`; đây không phải là chia sẻ một tác vụ I/O lazy mà là giữ một kết quả đã được tính trước.

Nếu cần trì hoãn và tạo publisher riêng cho mỗi subscriber, dùng `defer`:

```java
import reactor.core.publisher.Mono;

Mono<Config> freshPerSubscription = Mono.defer(
    () -> Mono.fromCallable(configService::load)
);
```

Mỗi subscription tạo publisher mới và gọi hàm tải cấu hình khi có nhu cầu. Vì vậy, việc chọn `just`, `fromCallable` hay `defer` ảnh hưởng trực tiếp đến thời điểm và số lần tác vụ được thực thi.

## Nhiều nhánh trong một pipeline và nhiều subscription độc lập

Không phải cứ có nhiều người nhận là nguồn luôn chạy nhiều lần. Nếu các nhánh được kết hợp trong cùng một pipeline, chúng có thể cùng thuộc một subscription. Tuy nhiên, cách ghép nhánh và loại publisher quyết định có bao nhiêu subscription đi ngược về nguồn.

Ví dụ, gọi `subscribe` hai lần tạo hai subscription độc lập:

```java
Flux<Event> events = eventClient.fetchRecentEvents();

events.subscribe(this::updateDashboard);
events.subscribe(this::updateSearchIndex);
```

Nếu `fetchRecentEvents()` trả về publisher cold, mỗi lần đăng ký có thể gọi dịch vụ một lần. Một cách tổ chức khác là ghép các hành động vào một pipeline duy nhất:

```java
eventClient.fetchRecentEvents()
    .doOnNext(this::updateDashboard)
    .doOnNext(this::updateSearchIndex)
    .subscribe();
```

Trong trường hợp này, hai hành động quan sát cùng một tín hiệu trong một subscription. Cách này phù hợp nếu cả hai thao tác thực sự thuộc cùng một luồng xử lý và có thể thực hiện tuần tự trên cùng nhánh. Nếu một nhánh cần xử lý bất đồng bộ độc lập hoặc có chính sách lỗi riêng, hãy cân nhắc tổ chức bằng các toán tử kết hợp publisher, đồng thời xác định rõ thứ tự, concurrency và cách hủy.

Không nên gọi `subscribe()` bên trong từng tầng service chỉ để kích hoạt công việc phụ. Làm như vậy tách pipeline khỏi caller, khiến caller khó phối hợp kết quả, lỗi và vòng đời. Hãy trả về `Mono` hoặc `Flux` để tầng gọi quyết định cách kết hợp và đăng ký subscription tại ranh giới sở hữu công việc.

## Chia sẻ một lần phát với nhiều subscriber

Khi nhiều subscriber cần cùng quan sát một nguồn đang phát, Reactor cung cấp các cơ chế multicast. Thay vì để mỗi subscriber tạo một subscription độc lập đến nguồn cold, một publisher có thể chia sẻ tín hiệu upstream cho nhiều subscriber downstream.

### `publish()` và `connect()`

`publish()` chuyển một `Flux` thành `ConnectableFlux`. Publisher này chưa bắt đầu phát cho đến khi được kết nối bằng `connect()`. Nhờ đó, ứng dụng có thể đăng ký các subscriber trước rồi mới khởi động nguồn:

```java
import java.time.Duration;
import reactor.core.Disposable;
import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;

ConnectableFlux<Long> sharedTicks = Flux.interval(Duration.ofMillis(300))
    .take(5)
    .publish();

sharedTicks.subscribe(value -> System.out.println("Màn hình: " + value));
sharedTicks.subscribe(value -> System.out.println("Giám sát: " + value));

Disposable connection = sharedTicks.connect();
```

Hai subscriber được đăng ký trước khi `connect()` được gọi nên cùng nhận các tín hiệu từ một lần chạy của nguồn. `connect()` trả về `Disposable` đại diện cho kết nối upstream; có thể dùng handle này để ngắt kết nối khi thành phần sở hữu luồng không còn cần nó. Với nguồn hữu hạn trong ví dụ, nguồn tự hoàn tất sau năm phần tử.

`ConnectableFlux` cho phép kiểm soát thời điểm bắt đầu. Nó phù hợp khi cần bảo đảm các bên nhận đã sẵn sàng trước khi nguồn phát dữ liệu, chẳng hạn khi khởi động một luồng sự kiện dùng chung.

### `autoConnect(n)`

`autoConnect(n)` tự kết nối khi có đủ số subscriber tối thiểu. Ví dụ:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux<Long> sharedAfterTwo = Flux.interval(Duration.ofMillis(300))
    .take(5)
    .publish()
    .autoConnect(2);

sharedAfterTwo.subscribe(value -> System.out.println("Consumer A: " + value));
sharedAfterTwo.subscribe(value -> System.out.println("Consumer B: " + value));
```

Nguồn bắt đầu khi subscriber thứ hai đăng ký. Các subscriber tham gia sau thời điểm kết nối không được phát lại những phần tử đã trôi qua; chúng chỉ nhận các tín hiệu từ thời điểm tham gia trở đi. `autoConnect` thích hợp khi kết nối được khởi động một lần và vòng đời nguồn được quản lý ở nơi khác. Với nguồn vô hạn, cần thiết kế rõ cách dừng kết nối; không nên để luồng sống lâu hơn thành phần sở hữu.

### `refCount(n)` và `share()`

`refCount(n)` cũng tự kết nối khi số subscriber đạt ngưỡng, nhưng theo dõi số subscriber đang hoạt động và ngắt kết nối upstream khi số lượng giảm xuống dưới ngưỡng theo chính sách của toán tử. Đây là lựa chọn hữu ích khi vòng đời nguồn nên gắn với nhóm subscriber hiện tại.

```java
Flux<Notification> notifications = notificationSource.events()
    .publish()
    .refCount(1);
```

Với ngưỡng `1`, nguồn được kết nối khi subscriber đầu tiên tham gia và bị ngắt khi subscriber cuối cùng hủy. Khi không còn subscriber, một subscriber mới có thể khiến nguồn được đăng ký lại; vì vậy, một lần gọi bên ngoài vẫn có thể lặp lại qua các chu kỳ kết nối khác nhau.

`share()` là cách viết ngắn cho mô hình chia sẻ dựa trên `publish().refCount(1)` trong Reactor. Nó cho phép nhiều subscriber đang tham gia cùng quan sát một lần phát. Tuy nhiên, `share()` không lưu lịch sử để phát lại cho subscriber đến muộn. Nếu subscriber đầu tiên đã nhận một số phần tử trước khi subscriber thứ hai tham gia, subscriber thứ hai không tự động nhận lại các phần tử cũ.

| Cơ chế | Khi bắt đầu nguồn | Khi subscriber rời đi | Subscriber đến muộn |
|---|---|---|---|
| `publish().connect()` | Khi gọi `connect()` | Kết nối được quản lý qua `Disposable` trả về từ `connect()` | Nhận các tín hiệu tiếp theo, không tự phát lại lịch sử |
| `publish().autoConnect(n)` | Khi đủ `n` subscriber | Không tự ngắt chỉ vì số subscriber giảm; cần quản lý vòng đời kết nối | Nhận tín hiệu từ thời điểm tham gia |
| `publish().refCount(n)` | Khi đạt ngưỡng `n` | Ngắt kết nối khi số subscriber giảm dưới ngưỡng theo chính sách ref-count | Nhận tín hiệu từ thời điểm tham gia |
| `share()` | Khi subscriber đầu tiên tham gia | Ngắt upstream khi không còn subscriber đang tham gia | Không nhận lại tín hiệu đã phát trước khi tham gia |

## Chia sẻ kết quả đã có bằng `cache()`

Chia sẻ trực tiếp một luồng đang phát khác với lưu kết quả để subscriber đến sau có thể nhận lại. `cache()` lưu tín hiệu đã phát và phát lại chúng cho subscriber mới. Với `Mono`, cơ chế này thường phù hợp để chia sẻ kết quả của một phép tính hoặc lời gọi bên ngoài:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<ExchangeRate> rate = Mono.defer(
        () -> exchangeClient.fetchRate("USD", "VND"))
    .cache(Duration.ofSeconds(20));

rate.subscribe(this::updateHeader);
rate.subscribe(this::calculateTotal);
```

Hai subscriber dùng chung kết quả được tạo bởi một lần subscription nguồn trong khoảng cache còn hiệu lực. Subscriber đến sau trong khoảng thời gian đó nhận lại tín hiệu đã cache mà không kích hoạt request mới. Khi TTL hết, một subscription tiếp theo có thể khởi tạo lần tải mới.

Cache có thể giữ tín hiệu kết thúc, bao gồm giá trị, hoàn tất rỗng hoặc lỗi. Vì vậy, nếu một lần gọi thất bại, lỗi đó cũng có thể được phát lại cho các subscriber tiếp theo trong thời gian cache. Cần quyết định rõ có muốn cache lỗi hay muốn thử lại bằng cách đặt toán tử retry và cache đúng thứ tự.

Ví dụ về thứ tự:

```java
Mono<Data> retryThenCache = source
    .retry(2)
    .cache(Duration.ofSeconds(10));

Mono<Data> cacheThenRetry = source
    .cache(Duration.ofSeconds(10))
    .retry(2);
```

Ở cách thứ nhất, nguồn có cơ hội được đăng ký lại tối đa theo chính sách retry trước khi tín hiệu cuối cùng được cache. Ở cách thứ hai, `retry` đăng ký lại vào publisher cache; nếu cache đã lưu lỗi, nó có thể phát lại chính lỗi đó mà không chạy lại nguồn. Vị trí toán tử vì thế ảnh hưởng đến việc tác vụ bên ngoài có được thực hiện lại hay không.

Với `Flux`, `cache()` có thể lưu nhiều phần tử đã phát để phát lại cho subscriber mới. Nếu nguồn là luồng dài hạn hoặc vô hạn, lưu toàn bộ lịch sử có thể làm bộ nhớ tăng liên tục. Hãy cân nhắc giới hạn số phần tử lưu, TTL hoặc chiến lược chia sẻ không lưu lịch sử như `share()`. Cache cũng cần được đặt trong đúng phạm vi dữ liệu: kết quả phụ thuộc người dùng, tenant, quyền truy cập hoặc tham số request không nên bị chia sẻ qua một cache toàn cục thiếu khóa phân vùng phù hợp.

## Chọn giữa chia sẻ và chạy lại

Không phải nguồn nào cũng nên chia sẻ. Nếu mỗi subscriber cần dữ liệu mới nhất tại thời điểm đăng ký, nguồn cold và subscription độc lập là lựa chọn đúng. Nếu nhiều bên cần quan sát cùng một sự kiện đang phát, `share` hoặc `publish` có thể phù hợp. Nếu nhiều bên cần cùng một kết quả đã tính và subscriber đến muộn cần nhận lại kết quả đó, `cache` có thể phù hợp.

| Nhu cầu | Cách tiếp cận thường dùng | Điều cần cân nhắc |
|---|---|---|
| Mỗi subscriber cần lần đọc độc lập | Giữ nguồn cold (`defer`, `fromCallable`) | Số lần gọi dịch vụ tăng theo số subscription |
| Nhiều subscriber cùng nghe một luồng sự kiện trực tiếp | `share()` hoặc `publish().refCount(...)` | Subscriber đến muộn bỏ lỡ tín hiệu đã phát |
| Cần chờ đủ subscriber trước khi bắt đầu | `publish().autoConnect(n)` hoặc `refCount(n)` | Chọn chính sách ngắt kết nối và quản lý nguồn dài hạn |
| Nhiều subscriber cần cùng một kết quả đã hoàn tất | `Mono.cache(...)` | Xác định TTL, cache lỗi và phạm vi dữ liệu |
| Cần phát lại một phần lịch sử | `replay(...)` hoặc cache có giới hạn phù hợp | Giới hạn bộ nhớ và thời gian giữ lịch sử |
| Tác vụ có side effect không được phép chạy trùng | Thiết kế idempotency và cơ chế điều phối ở tầng nghiệp vụ | Chia sẻ publisher không bảo đảm exactly-once trên toàn hệ thống |

## Chia sẻ publisher không bảo đảm tác vụ bên ngoài chỉ xảy ra đúng một lần

Các cơ chế `share`, `refCount` và `cache` điều khiển subscription trong phạm vi một publisher và một tiến trình đang chạy. Chúng không phải cơ chế giao dịch phân tán và không bảo đảm một side effect chỉ xảy ra một lần trên toàn hệ thống.

Ví dụ, một request thanh toán có thể được gửi đi, nhưng kết nối bị ngắt trước khi client nhận được phản hồi. Nếu pipeline retry, nguồn có thể gửi request lần nữa. Tương tự, ứng dụng có thể khởi động lại, chạy trên nhiều instance hoặc tạo publisher mới; cache trong bộ nhớ của một instance không ngăn các instance khác thực hiện cùng tác vụ.

Với side effect quan trọng, hãy dùng cơ chế ở tầng nghiệp vụ:

- **Idempotency key:** gửi một khóa ổn định theo nghiệp vụ để hệ thống đích nhận diện các lần gửi lặp và trả về kết quả đã ghi nhận.
- **Ràng buộc duy nhất hoặc bản ghi xử lý:** lưu định danh sự kiện/tác vụ với constraint phù hợp để tránh xử lý trùng khi nhiều worker cùng nhận.
- **Transactional outbox hoặc inbox:** ghi nhận trạng thái nghiệp vụ và thông điệp cần phát trong một giao dịch phù hợp, sau đó xử lý việc gửi và khử trùng lặp có kiểm soát.
- **Chính sách retry có giới hạn:** chỉ thử lại lỗi có thể phục hồi, đặt timeout và backoff, đồng thời bảo đảm thao tác có thể lặp an toàn.

Chia sẻ publisher có thể giảm số subscription và tránh lặp lại một lần đọc trong một vòng đời cụ thể. Tính đúng đắn của side effect vẫn cần được bảo vệ bằng idempotency, trạng thái bền vững và quy tắc nghiệp vụ.

## Cách kiểm tra số lần subscription và tác vụ nguồn

Khi nghi ngờ một lời gọi bên ngoài bị lặp, hãy quan sát vị trí subscription và nguồn. `doOnSubscribe` có thể ghi nhận số subscription đi qua một publisher; `defer` có thể giúp đặt log ngay tại thời điểm nguồn được tạo:

```java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

AtomicInteger sourceCalls = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    int call = sourceCalls.incrementAndGet();
    System.out.println("Bắt đầu lần gọi nguồn " + call);
    return remoteClient.fetchValue();
});

Mono<String> shared = source.cache();

shared.subscribe(this::consumeA);
shared.subscribe(this::consumeB);
```

Với một publisher `Mono` được cache như trên, hai subscriber sử dụng cùng tín hiệu đã cache trong vòng đời cache của publisher. Bộ đếm giúp kiểm tra số lần supplier nguồn được gọi; trong ứng dụng thật, có thể kết hợp metric, trace ID và log ở adapter HTTP hoặc repository để đối chiếu số request thực tế.

Khi điều tra, cần phân biệt số lần tạo publisher, số lần subscribe, số lần gọi supplier và số lần request thực sự đến hệ thống ngoài. Bốn con số này không nhất thiết bằng nhau. Ví dụ, `Mono.just(remoteClient.fetch())` gọi phương thức ngay khi dựng publisher; `Mono.defer` gọi phương thức mỗi lần subscribe; `cache` có thể gộp nhiều subscriber vào một lần thực thi trong thời gian cache; retry có thể tạo thêm subscription upstream.

## Nguyên tắc thiết kế

Khi xây dựng pipeline có nhiều bên nhận, hãy xác định liệu mỗi bên cần một lần thực thi riêng hay cần cùng quan sát một lần phát. Đặt subscription tại tầng sở hữu vòng đời công việc, chọn `share`, `publish`, `refCount` hoặc `cache` theo yêu cầu về thời điểm kết nối và phát lại, rồi kiểm tra hành vi khi subscriber đến muộn hoặc hủy.

Đối với lời gọi bên ngoài có side effect, hãy đánh giá cả retry, timeout, hủy và khả năng chạy nhiều instance. Chia sẻ publisher giúp kiểm soát việc thực thi trong một tiến trình; idempotency và lưu trạng thái bền vững bảo vệ tính đúng đắn của nghiệp vụ. Khi hai lớp trách nhiệm này được thiết kế rõ, ứng dụng reactive có thể phục vụ nhiều subscriber mà vẫn kiểm soát được chi phí I/O, dữ liệu phát lại và tác động của các lần thực thi lặp.
