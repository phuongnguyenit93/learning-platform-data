# Nguồn phát theo từng đăng ký và nguồn phát dùng chung (cold/hot)

Trong lập trình reactive, một nguồn dữ liệu có thể tạo ra một luồng riêng cho từng người đăng ký, hoặc phát cùng một luồng sự kiện cho nhiều người đăng ký. Hai cách tổ chức này thường được gọi là **cold publisher** và **hot publisher**. Chọn đúng kiểu nguồn phát ảnh hưởng trực tiếp đến số request được gửi qua RSocket, thời điểm người dùng nhận sự kiện, cách hủy kết nối và cách hệ thống xử lý backpressure.

Trong bài này, ta dùng Reactor để làm rõ vòng đời của publisher, sau đó áp dụng vào các tương tác RSocket như request-response và request-stream. Các ví dụ tập trung vào Java và Spring RSocket.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa cold và hot publisher dựa trên vòng đời subscription.
- Nhận biết những đoạn code tạo publisher cold, publisher hot và publisher dùng chung.
- Chọn giữa **share**, **publish**, **replay** và **cache** theo yêu cầu của luồng dữ liệu.
- Dự đoán ảnh hưởng của nhiều subscriber đến request RSocket, backpressure và việc hủy stream.
- Tạo nguồn sự kiện hot bằng **Sinks.Many** và xử lý kết quả phát sự kiện.

## 1. Publisher và subscription

Reactive Streams mô hình hóa dữ liệu bất đồng bộ bằng ba vai trò chính:

- **Publisher** phát ra các tín hiệu **onNext**, **onError** hoặc **onComplete**.
- **Subscriber** đăng ký nhận tín hiệu và yêu cầu số phần tử mà nó có thể xử lý thông qua **request(n)**.
- **Subscription** nối hai phía, cho phép subscriber yêu cầu thêm dữ liệu hoặc hủy việc nhận dữ liệu bằng **cancel()**.

Trong Reactor, **Mono<T>** biểu diễn tối đa một phần tử và **Flux<T>** biểu diễn không, một hoặc nhiều phần tử. Cả hai đều là publisher. Bản thân kiểu **Mono** hay **Flux** không quyết định nguồn là cold hay hot; điều đó phụ thuộc vào cách publisher tạo và phân phối tín hiệu.

Một pipeline reactive thường trải qua hai thời điểm:

1. **Assembly time**: chương trình khai báo publisher và nối các operator thành pipeline.
2. **Subscription time**: một subscriber gọi **subscribe**; publisher bắt đầu thực thi hoặc kết nối với nguồn dữ liệu theo semantics của nó.

Sự khác biệt giữa cold và hot thể hiện rõ ở thời điểm subscription: subscriber mới nhận một lần thực thi độc lập, hay tham gia vào một nguồn sự kiện đang được chia sẻ.

## 2. Cold publisher: mỗi subscriber có một lần thực thi riêng

Cold publisher thường chỉ bắt đầu tạo dữ liệu khi có subscriber. Mỗi lần đăng ký tạo một lần thực thi độc lập. Subscriber thứ hai không tiếp tục từ vị trí mà subscriber thứ nhất đã đọc; nó bắt đầu một lượt mới.

Ví dụ đơn giản:

~~~java
Flux<Integer> numbers = Flux.range(1, 3);

numbers.subscribe(value -> System.out.println("A: " + value));
numbers.subscribe(value -> System.out.println("B: " + value));
~~~

Cả A và B đều nhận **1, 2, 3**. Mỗi subscription chạy qua nguồn **Flux.range** của riêng nó.

Một ví dụ thể hiện rõ hơn việc thực thi lại:

~~~java
Mono<String> quote = Mono.fromCallable(() -> {
    System.out.println("Đang gọi dịch vụ báo giá");
    return pricingService.fetchQuote("ACME");
});

quote.subscribe(value -> System.out.println("A: " + value));
quote.subscribe(value -> System.out.println("B: " + value));
~~~

Hàm lấy báo giá được gọi một lần cho mỗi subscription. Vì vậy, hai subscriber có thể nhận kết quả khác nhau nếu dữ liệu ở dịch vụ thay đổi giữa hai lần gọi.

### 2.1. Phân biệt tạo giá trị sớm và tạo giá trị khi subscribe

Không phải mọi biểu thức tạo **Mono** đều trì hoãn công việc đến subscription:

~~~java
// fetchQuote được gọi ngay khi dòng này được thực thi.
Mono<Quote> eager = Mono.just(pricingService.fetchQuote("ACME"));

// fetchQuote được gọi cho mỗi subscription.
Mono<Quote> deferred =
        Mono.fromCallable(() -> pricingService.fetchQuote("ACME"));
~~~

**Mono.just(value)** nhận một giá trị đã được tính trước. Nếu lời gọi dịch vụ nằm bên trong đối số của **just**, lời gọi đó diễn ra ở assembly time. **fromCallable** trì hoãn việc gọi hàm đến subscription và gọi lại cho subscription tiếp theo.

Với một publisher khác cần được tạo mới cho mỗi subscriber, dùng **defer**:

~~~java
Mono<Quote> quote = Mono.defer(() ->
        pricingService.fetchQuoteReactive("ACME")
);
~~~

**defer** gọi supplier khi có subscription và lấy publisher do supplier trả về. Đây là cách hữu ích khi cần tạo request, đọc cấu hình hiện tại hoặc khởi tạo tài nguyên theo từng subscriber.

### 2.2. Cold publisher trong RSocket

Với một request-response, ứng dụng thường muốn mỗi subscriber thực hiện một request độc lập. Có thể biểu diễn rõ ý định đó bằng **defer**:

~~~java
Mono<Quote> quote = Mono.defer(() ->
        requester
                .route("pricing.quote")
                .data(new QuoteRequest("ACME"))
                .retrieveMono(Quote.class)
);
~~~

Mỗi subscription vào **quote** tạo một lần thực thi request. Điều này phù hợp khi mỗi người gọi cần một kết quả riêng, hoặc khi request có dữ liệu đầu vào và quyền truy cập riêng.

Tương tự, một request-stream có thể được tạo theo từng subscriber:

~~~java
Flux<PriceTick> prices = Flux.defer(() ->
        requester
                .route("market.prices")
                .retrieveFlux(PriceTick.class)
);
~~~

Hai subscriber của **prices** có thể tạo hai request-stream RSocket riêng. Mỗi stream có subscription, nhu cầu dữ liệu và vòng đời hủy riêng. Đây là hành vi phù hợp khi từng client cần một phiên stream độc lập.

## 3. Hot publisher: nhiều subscriber quan sát cùng nguồn sự kiện

Hot publisher phân phối tín hiệu từ một nguồn đang hoạt động. Các subscriber cùng quan sát nguồn đó thay vì mỗi subscriber tạo một lần thực thi độc lập. Nguồn có thể nhận sự kiện từ cảm biến, message broker, callback, bộ thu thập giá hoặc một luồng RSocket khác.

Một subscriber đến muộn thường chỉ nhận các tín hiệu được phát sau thời điểm nó đăng ký. Những tín hiệu đã phát trước đó không tự động được gửi lại, trừ khi publisher có cơ chế lưu và phát lại.

Ví dụ, một sink phát sự kiện giá:

~~~java
Sinks.Many<PriceTick> priceSink =
        Sinks.many().multicast().onBackpressureBuffer();

Flux<PriceTick> livePrices = priceSink.asFlux();

livePrices.subscribe(tick -> System.out.println("A: " + tick));
livePrices.subscribe(tick -> System.out.println("B: " + tick));

priceSink.tryEmitNext(new PriceTick("ACME", 101.25));
~~~

A và B cùng nhận sự kiện được phát sau khi cả hai đã đăng ký. Sink chỉ có một nguồn sự kiện; nó không gọi lại logic tạo giá cho từng subscriber.

**Sinks.Many** là API để đẩy tín hiệu vào một publisher. **asFlux()** cung cấp view dạng **Flux** cho subscriber. Với sink multicast, các subscriber hiện tại nhận cùng các sự kiện mới. Subscriber đăng ký sau không mặc nhiên nhận toàn bộ lịch sử.

### 3.1. Kiểm tra kết quả phát sự kiện

Không nên bỏ qua kết quả của **tryEmitNext**. Việc phát có thể thất bại, chẳng hạn khi sink đã kết thúc, buffer đầy hoặc có xung đột phát đồng thời:

~~~java
Sinks.EmitResult result =
        priceSink.tryEmitNext(new PriceTick("ACME", 101.25));

if (result.isFailure()) {
    log.warn("Không thể phát PriceTick: {}", result);
}
~~~

Nếu nhiều thread cùng phát, cần chọn cách xử lý xung đột phù hợp với nguồn dữ liệu. Có thể tuần tự hóa thao tác phát, kiểm tra **EmitResult**, hoặc dùng **emitNext** với failure handler được thiết kế rõ ràng. Không nên coi việc gọi sink là một thao tác luôn thành công.

### 3.2. Subscriber đến muộn và replay

Hot publisher không đồng nghĩa với việc lưu lịch sử. Nếu dashboard mở sau khi nguồn đã phát nhiều sự kiện, dashboard có thể chỉ thấy dữ liệu mới. Khi nghiệp vụ cần một phần lịch sử gần nhất, có thể dùng replay:

~~~java
Sinks.Many<PriceTick> recentPriceSink =
        Sinks.many().replay().limit(20);

Flux<PriceTick> recentPrices = recentPriceSink.asFlux();
~~~

Sink replay giữ lại tối đa 20 tín hiệu gần nhất để subscriber mới có thể nhận lại. Cần chọn giới hạn dựa trên dung lượng, tần suất phát và nhu cầu nghiệp vụ. Lưu toàn bộ lịch sử của một stream không giới hạn có thể làm bộ nhớ tăng liên tục.

## 4. Chuyển một nguồn cold thành nguồn dùng chung trong Reactor

Một publisher cold có thể được chia sẻ bằng các operator multicast. Khi đó nhiều subscriber tham gia cùng một lần subscription đến nguồn upstream.

### 4.1. **share()**

**share()** là lựa chọn ngắn gọn để chia sẻ một nguồn giữa các subscriber đang hoạt động. Nguồn upstream được kết nối khi subscriber đầu tiên đến; khi subscriber cuối cùng hủy, kết nối upstream được hủy. Với một stream RSocket dài hạn, điều này có nghĩa là nhiều thành phần trong cùng ứng dụng có thể cùng dùng một request-stream.

~~~java
Flux<PriceTick> sharedPrices = prices.share();

Disposable dashboard = sharedPrices.subscribe(this::updateDashboard);
Disposable alerting = sharedPrices.subscribe(this::checkAlert);
~~~

Khi dashboard và alerting cùng đăng ký trong lúc stream đang chạy, chúng nhận các tín hiệu từ cùng một subscription upstream. Nếu cả hai cùng hủy và không còn subscriber nào, **share()** hủy upstream. Một nhóm subscriber mới có thể làm nguồn được đăng ký lại.

**share()** không replay dữ liệu đã phát trước khi subscriber tham gia. Nếu dashboard đăng ký sau alerting, dashboard chỉ nhận các tín hiệu tiếp theo kể từ lúc nó tham gia.

### 4.2. **publish()** và **ConnectableFlux**

**publish()** tạo một **ConnectableFlux**. Publisher này cho phép ứng dụng quyết định thời điểm kết nối đến nguồn:

~~~java
ConnectableFlux<PriceTick> connectable = prices.publish();

connectable.subscribe(this::updateDashboard);
connectable.subscribe(this::checkAlert);

// Bắt đầu subscription đến nguồn upstream sau khi đã đăng ký các consumer.
connectable.connect();
~~~

Cách này hữu ích khi cần đăng ký một nhóm consumer trước khi bắt đầu nhận dữ liệu. Nếu quên gọi **connect()**, nguồn upstream sẽ chưa được kết nối.

Có thể tự động kết nối sau một số subscriber nhất định:

~~~java
Flux<PriceTick> sharedAfterTwoSubscribers =
        prices.publish().autoConnect(2);
~~~

**autoConnect(2)** bắt đầu kết nối sau khi có đủ hai subscriber. Kết nối được duy trì theo chính sách của **autoConnect**; nó không tự ngắt chỉ vì số subscriber giảm về không.

### 4.3. **refCount()**

**refCount(n)** kết nối sau khi có ít nhất **n** subscriber và hủy kết nối khi số subscriber giảm xuống dưới ngưỡng. Ví dụ:

~~~java
Flux<PriceTick> sharedWhenObserved =
        prices.publish().refCount(1);
~~~

Với ngưỡng một, hành vi thường dùng tương đương **share()**: bắt đầu khi có subscriber đầu tiên và ngắt khi subscriber cuối cùng rời đi. Một số overload của **refCount** cho phép đặt khoảng chờ trước khi ngắt, hữu ích khi subscriber có thể rời và quay lại trong thời gian ngắn.

### 4.4. So sánh các lựa chọn phổ biến

| Cơ chế | Khi nào kết nối nguồn | Dữ liệu cho subscriber đến muộn | Vòng đời kết nối |
|---|---|---|---|
| Cold publisher | Mỗi lần subscribe | Bắt đầu một lượt riêng | Mỗi subscription độc lập |
| **share()** | Subscriber đầu tiên | Chỉ tín hiệu từ lúc tham gia | Ngắt khi subscriber cuối cùng hủy |
| **publish().connect()** | Khi gọi connect() | Chỉ tín hiệu từ lúc tham gia | Ứng dụng chủ động quản lý |
| **publish().autoConnect(n)** | Khi đủ n subscriber | Chỉ tín hiệu từ lúc tham gia | Tự kết nối, không tự ngắt theo số subscriber |
| **publish().refCount(n)** | Khi đủ n subscriber | Chỉ tín hiệu từ lúc tham gia | Ngắt khi số subscriber thấp hơn ngưỡng |
| **replay(n)** | Khi được kết nối theo chính sách đã chọn | Có thể nhận lại tối đa n tín hiệu gần nhất | Phụ thuộc cách kết nối và quản lý |
| **cache()** | Khi subscriber đầu tiên đăng ký | Phát lại tín hiệu đã cache | Cache giữ dữ liệu theo cấu hình; cần cân nhắc với stream vô hạn |

**cache()** thường phù hợp với kết quả hữu hạn cần tái sử dụng. Với một stream sự kiện vô hạn, cache không giới hạn có thể giữ quá nhiều dữ liệu và khiến nguồn tiếp tục hoạt động lâu hơn mong muốn. Hãy chọn giới hạn lịch sử hoặc cơ chế replay có vòng đời rõ ràng.

## 5. Áp dụng vào một luồng giá realtime qua RSocket

Giả sử một dịch vụ cung cấp giá thị trường qua route **market.prices**. Dashboard, bộ cảnh báo và bộ ghi nhận dữ liệu đều cần đọc giá.

### 5.1. Mỗi consumer tạo một request-stream riêng

~~~java
Flux<PriceTick> pricesPerSubscriber = Flux.defer(() ->
        requester
                .route("market.prices")
                .retrieveFlux(PriceTick.class)
);

Disposable dashboard =
        pricesPerSubscriber.subscribe(this::updateDashboard);

Disposable alerting =
        pricesPerSubscriber.subscribe(this::checkAlert);
~~~

Mỗi subscriber tạo một request-stream riêng. Cách này hữu ích khi consumer có bộ lọc, metadata, quyền truy cập hoặc nhu cầu backpressure riêng. Đổi lại, server có thể phải phục vụ nhiều stream và nhiều công việc upstream hơn.

### 5.2. Chia sẻ một request-stream trong cùng ứng dụng

Nếu các consumer cần cùng một tập dữ liệu và cùng chính sách truy cập, có thể chia sẻ stream:

~~~java
Flux<PriceTick> upstreamPrices = Flux.defer(() ->
        requester
                .route("market.prices")
                .retrieveFlux(PriceTick.class)
);

Flux<PriceTick> sharedPrices = upstreamPrices.share();

Disposable dashboard =
        sharedPrices.subscribe(this::updateDashboard);

Disposable alerting =
        sharedPrices.subscribe(this::checkAlert);
~~~

Khi hai consumer cùng hoạt động, chúng quan sát cùng một request-stream upstream. Điều này có thể giảm số request đến RSocket server và tránh tạo nhiều nguồn đọc giống nhau. Khi consumer cuối cùng hủy subscription, **share()** hủy upstream; nếu sau đó có consumer mới, publisher có thể tạo một request-stream mới.

Chỉ chia sẻ khi các consumer thực sự có thể dùng chung một nguồn. Nếu mỗi người dùng cần dữ liệu đã lọc theo tài khoản, tenant hoặc quyền truy cập, hãy tạo nguồn riêng hoặc áp dụng bộ lọc và kiểm tra quyền trước khi phân phối. Một hot stream dùng chung sai phạm vi có thể làm lộ dữ liệu giữa các người dùng.

### 5.3. Phát một nguồn hot từ RSocket endpoint

Ở phía server, một nguồn sự kiện nội bộ có thể được cung cấp cho nhiều client thông qua endpoint request-stream:

~~~java
@Controller
public class MarketController {

    private final Sinks.Many<PriceTick> priceSink =
            Sinks.many().multicast().onBackpressureBuffer();

    @MessageMapping("market.prices")
    public Flux<PriceTick> prices() {
        return priceSink.asFlux();
    }

    public void publish(PriceTick tick) {
        Sinks.EmitResult result = priceSink.tryEmitNext(tick);
        if (result.isFailure()) {
            log.warn("Không phát được tick: {}", result);
        }
    }
}
~~~

Mỗi client đăng ký route **market.prices** sẽ trở thành subscriber của cùng sink. Các client đang đăng ký nhận những tick mới từ nguồn đó. Client kết nối muộn không tự nhận lại toàn bộ tick cũ vì đây là multicast sink không có replay.

Đây chỉ là ví dụ về cách nối một nguồn hot với endpoint. Trong ứng dụng thực tế, cần xác định rõ ai được phép đăng ký, dữ liệu nào được phép phát cho từng client, cách đóng sink khi ứng dụng dừng và cách xử lý khi consumer không theo kịp tốc độ phát.

## 6. Backpressure khi chia sẻ nguồn

Reactive Streams cho phép subscriber yêu cầu số phần tử mà nó sẵn sàng xử lý. Với một cold publisher, mỗi subscription có luồng demand riêng. Với một nguồn hot được chia sẻ, nguồn phát có thể tiếp tục nhận sự kiện trong khi một hoặc nhiều subscriber xử lý chậm.

Khi đưa dữ liệu hot vào RSocket request-stream, hãy quyết định rõ chính sách khi consumer không theo kịp:

- **Giữ mọi sự kiện**: dùng buffer có giới hạn và xác định hành vi khi đầy. Cách này phù hợp khi mỗi sự kiện đều quan trọng, nhưng cần tính dung lượng và chính sách overflow.
- **Chỉ cần trạng thái mới nhất**: có thể dùng chiến lược latest để bỏ qua giá trị cũ khi consumer chậm. Phù hợp với màn hình hiển thị trạng thái hiện tại.
- **Cho phép bỏ sự kiện**: dùng drop khi sự kiện mất đi không ảnh hưởng đến tính đúng đắn của nghiệp vụ, chẳng hạn một số mẫu telemetry.
- **Tách consumer**: nếu dashboard và bộ ghi nhận có yêu cầu khác nhau, cân nhắc các subscription hoặc pipeline riêng để một consumer không làm ảnh hưởng consumer còn lại.

Không nên dùng buffer không giới hạn như giải pháp mặc định. Nếu tốc độ phát luôn cao hơn tốc độ xử lý, hàng đợi sẽ tăng liên tục và cuối cùng gây áp lực bộ nhớ. Hãy đo tốc độ phát, tốc độ tiêu thụ, độ trễ và số lần overflow trong môi trường gần với thực tế.

RSocket có cơ chế flow control cho các tương tác dạng stream. Khi ứng dụng chuyển một publisher thành request-stream, demand ở phía nhận ảnh hưởng đến lượng dữ liệu được yêu cầu qua stream. Khi nhiều subscriber cùng chia sẻ một upstream, cần hiểu operator multicast đang phối hợp demand và buffer như thế nào; không giả định mỗi subscriber luôn có một bản sao upstream độc lập.

## 7. Chọn cold hay hot theo yêu cầu

| Nhu cầu | Hướng lựa chọn | Lý do |
|---|---|---|
| Mỗi lần đọc cần gọi dịch vụ và nhận kết quả mới | Cold (**defer**, **fromCallable**, publisher request) | Mỗi subscription có lần thực thi riêng |
| Mỗi client cần một RSocket stream độc lập | Cold | Mỗi client có vòng đời và demand riêng |
| Nhiều consumer trong một tiến trình cần cùng một stream | **share()** hoặc **publish().refCount(...)** | Chia sẻ một subscription upstream |
| Cần đăng ký consumer xong mới bắt đầu nguồn | **publish()** rồi **connect()** | Chủ động chọn thời điểm kết nối |
| Cần đủ một số consumer mới bắt đầu nguồn | **autoConnect(n)** hoặc **refCount(n)** | Chờ đủ subscriber theo ngưỡng |
| Subscriber mới cần xem lại một phần sự kiện gần nhất | Replay có giới hạn | Phát lại lịch sử đã lưu |
| Kết quả hữu hạn cần dùng lại | **cache()** có cân nhắc | Lưu tín hiệu để subscriber sau nhận lại |
| Mỗi tenant hoặc người dùng có dữ liệu riêng | Nguồn riêng hoặc pipeline được phân quyền | Tránh chia sẻ nhầm dữ liệu giữa các phạm vi bảo mật |

Trước khi chọn operator, hãy trả lời bốn câu hỏi:

1. Subscriber mới có cần tạo một request mới không?
2. Subscriber đến muộn có cần nhận lại dữ liệu cũ không?
3. Khi subscriber cuối cùng rời đi, nguồn upstream có cần dừng không?
4. Khi một consumer xử lý chậm, hệ thống phải giữ, bỏ hay tách dữ liệu?

Các câu trả lời này xác định phần lớn thiết kế cold/hot và chính sách backpressure.

## 8. Những lỗi thiết kế thường gặp

### Gọi dịch vụ ngay trong **Mono.just**

Đặt một lời gọi có side effect bên trong **Mono.just** khiến lời gọi chạy ở assembly time. Dùng **fromCallable** hoặc **defer** nếu công việc phải chạy khi subscribe.

### Nghĩ rằng **Flux** luôn là cold

**Flux** chỉ là kiểu publisher nhiều phần tử. Nó có thể cold, hot, hoặc là một view được multicast từ publisher khác. Cần kiểm tra cách nguồn được tạo và các operator được áp dụng.

### Dùng **share()** nhưng mong subscriber đến muộn nhận lịch sử

**share()** phân phối tín hiệu trong thời gian các subscriber cùng tham gia. Nó không phải kho lưu lịch sử. Nếu cần dữ liệu cũ, hãy chọn replay có giới hạn hoặc truy vấn lịch sử từ nơi lưu trữ phù hợp.

### Cache một stream vô hạn

Cache toàn bộ tín hiệu của một stream không kết thúc có thể làm bộ nhớ tăng không giới hạn và giữ nguồn hoạt động lâu hơn dự kiến. Hãy dùng giới hạn lịch sử, TTL hoặc một cơ chế lưu trữ có kiểm soát.

### Chia sẻ stream trước khi xác định phạm vi quyền

Một publisher hot dùng chung cho nhiều client có thể phát cùng dữ liệu cho tất cả subscriber. Xác thực và lọc theo người dùng hoặc tenant phải được thiết kế trước điểm multicast.

### Không quản lý subscription

Các subscription dài hạn cần được giữ và hủy đúng vòng đời. Khi một component dừng, hãy hủy **Disposable** tương ứng hoặc để framework quản lý lifecycle. Nếu không, consumer đã rời màn hình vẫn có thể tiếp tục nhận dữ liệu và giữ tài nguyên.

## 9. Tóm tắt

Cold publisher tạo một lần thực thi độc lập cho mỗi subscription. Đây thường là lựa chọn phù hợp cho request-response và request-stream mà từng client cần vòng đời riêng. Hot publisher phân phối tín hiệu từ một nguồn chung; nó phù hợp với sự kiện realtime và các consumer cần cùng dữ liệu. Reactor cung cấp **share**, **publish**, **autoConnect**, **refCount**, **replay** và **cache** để điều khiển cách kết nối và phát lại. Khi dùng chúng với RSocket, hãy thiết kế đồng thời số lượng stream, vòng đời hủy, backpressure, replay và phạm vi bảo mật của dữ liệu.
