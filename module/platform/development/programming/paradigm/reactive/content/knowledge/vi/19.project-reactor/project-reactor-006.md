# ConnectableFlux, share và cache trong quản lý nguồn dùng chung

Trong Project Reactor, một publisher cold thường tạo hoặc thực thi nguồn dữ liệu riêng cho mỗi subscription. Điều này phù hợp khi mỗi consumer cần một lần truy vấn hoặc một phép tính độc lập. Tuy nhiên, có những trường hợp nhiều consumer cần quan sát cùng một lần phát dữ liệu, chẳng hạn nhiều màn hình cùng theo dõi một feed sự kiện hoặc nhiều thành phần cùng dùng kết quả tải cấu hình. Khi đó, việc subscribe nhiều lần vào nguồn cold có thể tạo nhiều kết nối, request hoặc tác vụ trùng lặp.

Reactor cung cấp ConnectableFlux, share() và cache() để điều khiển cách nhiều subscriber dùng chung một nguồn. Các công cụ này có semantics khác nhau về thời điểm kết nối, ngắt kết nối, phát lại dữ liệu và lưu giữ terminal signal. Chọn đúng công cụ đòi hỏi phải xác định consumer cần nhận dữ liệu trực tiếp từ thời điểm đăng ký hay cần xem lại dữ liệu cũ, ai sở hữu vòng đời upstream và dữ liệu được giữ trong bộ nhớ bao lâu.

## 1. Vì sao cần chia sẻ nguồn?

Một publisher cold thường bắt đầu công việc khi có subscriber. Mỗi subscription có thể tạo một lần thực thi mới:

~~~java
Mono<Configuration> configuration = webClient.get()
    .uri("/configuration")
    .retrieve()
    .bodyToMono(Configuration.class);

configuration.subscribe(this::updateDashboard);
configuration.subscribe(this::updateAuditView);
~~~

Nếu publisher này là cold, hai subscription có thể tạo hai HTTP request riêng. Điều đó có thể hợp lý nếu mỗi consumer cần dữ liệu mới độc lập. Nhưng nếu cả hai cần dùng cùng một kết quả tải cấu hình, việc gọi nguồn hai lần có thể lãng phí tài nguyên và tạo hai kết quả khác nhau nếu cấu hình thay đổi giữa hai request.

Một nguồn dùng chung có thể giúp:

- Chỉ tạo một subscription upstream cho nhiều subscriber đang cùng tham gia.
- Phân phối cùng một luồng sự kiện đến nhiều consumer.
- Kiểm soát thời điểm nguồn bắt đầu chạy.
- Giữ lại một phần hoặc toàn bộ tín hiệu để subscriber đến muộn có thể nhận lại.
- Giảm số lần gọi dịch vụ hoặc tính toán khi nhiều consumer cần cùng kết quả.

Tuy nhiên, chia sẻ nguồn cũng làm thay đổi semantics. Consumer không còn nhất thiết sở hữu một lần thực thi độc lập. Subscriber có thể bỏ lỡ phần tử đã phát trước khi nó đăng ký; một consumer hủy subscription có thể ảnh hưởng đến kết nối upstream nếu chính sách là ref-count; dữ liệu cache có thể cũ hoặc không phù hợp với ngữ cảnh bảo mật. Vì vậy, cần chọn theo yêu cầu vòng đời và tính mới của dữ liệu.

## 2. ConnectableFlux trì hoãn thời điểm kết nối

Toán tử publish() chuyển một Flux thành ConnectableFlux. Việc gọi subscribe() trên ConnectableFlux đăng ký consumer nhưng chưa tự khởi động nguồn upstream. Nguồn chỉ bắt đầu khi caller gọi connect().

~~~java
ConnectableFlux<Long> sharedTicks = Flux.interval(Duration.ofSeconds(1))
    .publish();

Disposable first = sharedTicks.subscribe(
    tick -> System.out.println("A: " + tick)
);

Disposable second = sharedTicks.subscribe(
    tick -> System.out.println("B: " + tick)
);

Disposable connection = sharedTicks.connect();
~~~

Hai subscriber được đăng ký trước khi nguồn bắt đầu. Khi connect() được gọi, Reactor thiết lập một kết nối upstream và phân phối các tick đến những subscriber đang tham gia. connect() trả về một Disposable đại diện cho kết nối; caller có thể dispose nó để yêu cầu ngắt nguồn dùng chung.

Mô hình vòng đời:

~~~mermaid
sequenceDiagram
    participant A as Subscriber A
    participant B as Subscriber B
    participant C as ConnectableFlux
    participant P as Upstream
    A->>C: subscribe
    B->>C: subscribe
    Note over C,P: Chưa kết nối nguồn
    C->>P: connect()
    P-->>C: onNext(...)
    C-->>A: onNext(...)
    C-->>B: onNext(...)
    Note over C,P: Một nguồn dùng chung
~~~

### Khi nào cần điều khiển connect thủ công?

ConnectableFlux hữu ích khi ứng dụng muốn đợi một số subscriber đăng ký xong rồi mới bắt đầu nguồn. Ví dụ, một dashboard có nhiều widget cần cùng nhận một feed; ứng dụng có thể tạo các subscription trước, sau đó gọi connect() khi màn hình đã sẵn sàng.

Nó cũng hữu ích khi cần tách thời điểm lắp ráp pipeline khỏi thời điểm kích hoạt nguồn. Caller có thể quyết định lúc nào bắt đầu, giữ handle kết nối và chủ động ngắt khi phạm vi sử dụng kết thúc.

Nếu không có thành phần nào chịu trách nhiệm gọi connect(), các subscriber sẽ không nhận dữ liệu từ nguồn. Đây là lỗi thường gặp khi dùng publish() nhưng quên bước kết nối.

## 3. autoConnect tự kết nối khi đủ subscriber

Nếu không cần gọi connect() thủ công, có thể dùng autoConnect(n). Toán tử này tự kết nối upstream khi số subscriber đạt ngưỡng n.

~~~java
Flux<Long> sharedTicks = Flux.interval(Duration.ofSeconds(1))
    .publish()
    .autoConnect(2);
~~~

Nguồn chỉ bắt đầu khi có ít nhất hai subscriber đăng ký. Điều này hữu ích khi một luồng chỉ nên chạy khi đủ các consumer bắt buộc. Với autoConnect(1), nguồn bắt đầu khi subscriber đầu tiên đăng ký.

autoConnect phù hợp khi muốn tự động kích hoạt một lần và để kết nối tiếp tục hoạt động. Nó không phải chính sách tự ngắt khi tất cả subscriber rời đi. Nếu cần tự ngắt upstream khi không còn đủ subscriber, hãy xem xét refCount hoặc share.

Có thể nhận handle kết nối qua overload nhận callback:

~~~java
Flux<Long> sharedTicks = Flux.interval(Duration.ofSeconds(1))
    .publish()
    .autoConnect(2, connection ->
        connectionRegistry.register(connection)
    );
~~~

Ví dụ giả định connectionRegistry quản lý Disposable theo vòng đời ứng dụng. Cần có chủ sở hữu rõ ràng cho handle này nếu nguồn có thể chạy vô hạn; nếu không, kết nối có thể tiếp tục hoạt động lâu hơn thời gian cần thiết.

## 4. refCount quản lý kết nối theo số subscriber đang hoạt động

refCount(n) kết nối upstream khi số subscriber đạt ngưỡng n và ngắt kết nối khi số subscriber còn hoạt động giảm xuống dưới ngưỡng đó.

~~~java
Flux<Long> sharedTicks = Flux.interval(Duration.ofSeconds(1))
    .publish()
    .refCount(2);
~~~

Trong ví dụ, hai subscriber cần cùng tham gia để nguồn bắt đầu. Nếu một subscriber hủy và số subscriber còn lại thấp hơn hai, kết nối upstream được ngắt theo chính sách ref-count.

| Cơ chế | Khi nào kết nối? | Khi subscriber rời đi |
| --- | --- | --- |
| connect() thủ công | Khi caller gọi connect() | Caller quản lý Disposable kết nối |
| autoConnect(n) | Khi đạt ít nhất n lần đăng ký | Không tự ngắt chỉ vì số subscriber giảm |
| refCount(n) | Khi số subscriber đang hoạt động đạt n | Ngắt khi số subscriber giảm dưới n |
| share() | Khi subscriber đầu tiên đăng ký | Dùng ref-count để ngắt khi không còn subscriber |

refCount(1) thường được dùng để biểu diễn chia sẻ bắt đầu ở subscriber đầu tiên và ngắt khi subscriber cuối cùng hủy. share() là cách viết ngắn cho kiểu chia sẻ này trong các trường hợp thông thường.

Một số overload của refCount cho phép cấu hình thời gian chờ trước khi ngắt kết nối. Grace period hữu ích khi subscriber có thể rời đi trong thời gian ngắn rồi đăng ký lại, ví dụ chuyển màn hình hoặc reconnect. Trong khoảng chờ, kết nối có thể được giữ để tránh tạo lại nguồn liên tục. Cần đối chiếu overload và semantics với phiên bản Reactor đang dùng.

## 5. share chia sẻ luồng trực tiếp

share() giúp nhiều subscriber dùng chung một subscription upstream. Nguồn bắt đầu khi subscriber đầu tiên tham gia; kết nối được quản lý theo số subscriber đang hoạt động. Subscriber đến khi luồng đã chạy thường chỉ nhận những phần tử được phát từ thời điểm nó đăng ký.

~~~java
Flux<MarketPrice> prices = marketDataClient.prices()
    .share();

Disposable screenA = prices.subscribe(this::renderPrice);
Disposable screenB = prices.subscribe(this::updateWatchlist);
~~~

Hai consumer đang cùng tham gia có thể nhận dữ liệu từ một nguồn upstream. Nếu screen B đăng ký sau khi một số giá đã được phát, B không tự động nhận lại các giá cũ. share() tập trung vào phân phối trực tiếp, không phải lưu lịch sử.

### share phù hợp với dữ liệu nào?

Các ví dụ phù hợp:

- Feed giá hoặc telemetry mà consumer hiện tại chỉ cần cập nhật mới.
- Một nguồn sự kiện dùng chung cho nhiều widget đang mở.
- Một nguồn polling được chia sẻ trong thời gian có ít nhất một consumer.
- Một luồng thông báo tạm thời mà subscriber đến muộn không cần lịch sử.

Nếu mỗi consumer cần toàn bộ lịch sử hoặc cần giá trị mới nhất ngay khi đăng ký, share() đơn thuần không đáp ứng. Hãy xem xét replay, cache hoặc snapshot từ kho trạng thái.

### share không phải cache

share() không lưu lại các phần tử đã phát để phát lại cho subscriber đến muộn. Nó cũng không bảo đảm một kết quả được lưu bền sau khi mọi subscriber rời đi. Nếu kết nối bị ngắt và một subscription mới xuất hiện sau đó, nguồn có thể được đăng ký lại theo lifecycle của ref-count. Không dựa vào share() để lưu kết quả hoặc đảm bảo dữ liệu tồn tại qua restart.

## 6. cache lưu tín hiệu để phát lại cho subscriber sau

cache() biến publisher thành nguồn chia sẻ có lưu giữ tín hiệu. Khi subscriber đầu tiên kích hoạt nguồn, Reactor subscribe upstream và cache các tín hiệu; subscriber tiếp theo có thể nhận lại tín hiệu đã lưu thay vì tạo một lần thực thi upstream mới.

Với Mono, cache thường phù hợp để chia sẻ một kết quả đơn lẻ:

~~~java
Mono<Configuration> cachedConfiguration = configClient.load()
    .cache();
~~~

Subscriber đầu tiên kích hoạt việc tải cấu hình. Các subscriber sau nhận lại tín hiệu đã cache. Với Mono, tín hiệu được cache có thể là giá trị, hoàn tất rỗng hoặc lỗi. Vì vậy, cache() không chỉ lưu kết quả thành công.

Có thể giới hạn thời gian lưu một kết quả:

~~~java
Mono<Configuration> cachedConfiguration = configClient.load()
    .cache(Duration.ofMinutes(2));
~~~

Sau thời hạn cache, một subscription tiếp theo có thể kích hoạt lần tải mới. TTL cần phù hợp với tốc độ thay đổi của dữ liệu và yêu cầu freshness. Nếu dữ liệu thay đổi nhanh hơn hai phút, consumer có thể nhận cấu hình cũ trong khoảng TTL.

### Cache cho Flux

Với Flux, cache có thể lưu các tín hiệu đã phát để subscriber mới nhận lại lịch sử được giữ. Một số overload cho phép giới hạn số phần tử lịch sử:

~~~java
Flux<AuditEvent> recentEvents = auditEventSource
    .cache(100);
~~~

Subscriber mới có thể nhận lại tối đa 100 phần tử gần nhất đã cache, cùng terminal signal khi nguồn đã kết thúc. cache() không giới hạn lịch sử có thể giữ toàn bộ phần tử trong vòng đời nguồn; với một stream vô hạn, điều này có thể làm bộ nhớ tăng không giới hạn. Chỉ dùng cache lịch sử không giới hạn cho nguồn hữu hạn và có kích thước được kiểm soát.

## 7. Phân biệt share, replay và cache

Ba cách dùng này thường bị nhầm lẫn vì đều có thể khiến nhiều subscriber quan sát cùng một nguồn.

| Cơ chế | Subscriber hiện tại | Subscriber đến muộn | Lưu giữ dữ liệu |
| --- | --- | --- | --- |
| share() | Nhận phần tử mới từ nguồn dùng chung | Thường chỉ nhận phần tử phát sau khi tham gia | Không replay lịch sử |
| replay() qua ConnectableFlux | Nhận phần tử mới | Có thể nhận lại lịch sử theo giới hạn replay | Giữ các tín hiệu theo replay policy |
| cache() | Dùng chung lần thực thi nguồn | Nhận lại tín hiệu đã cache | Lưu tín hiệu theo semantics và giới hạn đã chọn |

Ví dụ dùng replay có giới hạn:

~~~java
ConnectableFlux<AuditEvent> replayed = auditEventSource
    .replay(50);

replayed.connect();
~~~

Nguồn được kết nối và giữ tối đa 50 phần tử gần nhất cho subscriber đến muộn. Với replay(), cần chọn giới hạn phù hợp; replay toàn bộ lịch sử của một nguồn vô hạn cũng có nguy cơ tăng bộ nhớ giống cache không giới hạn.

replay() trên ConnectableFlux cho phép điều khiển thời điểm kết nối giống publish(), nhưng khác ở việc phát lại các phần tử đã giữ. cache() thuận tiện hơn khi muốn nguồn tự khởi động ở subscription đầu tiên và lưu tín hiệu cho những subscription sau. Nếu cần quản lý kết nối thủ công, replay ConnectableFlux có thể phù hợp hơn.

## 8. Cache và cancellation có semantics khác ref-count

Với share()/refCount, số subscriber đang hoạt động quyết định khi nào upstream được kết nối hoặc ngắt kết nối. Khi subscriber cuối cùng hủy, ref-count có thể hủy upstream.

Với cache(), mục tiêu là thu nhận và lưu tín hiệu để phát lại. Đặc biệt với Mono.cache, sau khi subscription đầu tiên kích hoạt nguồn, quá trình nạp và cache tín hiệu không bị hủy chỉ vì subscriber đầu tiên dispose. Điều này giúp subscriber sau vẫn có thể nhận kết quả, nhưng cũng có nghĩa là caller không nên dùng cache như cơ chế quản lý vòng đời của một nguồn cần dừng ngay khi không còn consumer.

Hãy chọn theo ownership:

- Nếu nguồn chỉ nên chạy khi có consumer và phải dừng khi consumer cuối rời đi, dùng share() hoặc refCount.
- Nếu nguồn phải bắt đầu khi có consumer đầu tiên rồi tiếp tục tạo dữ liệu để lưu lại cho subscriber sau, cân nhắc cache() với giới hạn phù hợp.
- Nếu caller muốn quyết định lúc kết nối và ngắt nguồn, dùng ConnectableFlux cùng handle Disposable.

Đối với Flux.cache, hãy kiểm tra semantics của overload và phiên bản Reactor cụ thể trước khi dựa vào hành vi cancellation hoặc TTL. Không giả định cache có cùng lifecycle với ref-count.

## 9. Vị trí của retry, timeout và fallback

Thứ tự toán tử ảnh hưởng trực tiếp đến việc lỗi được cache hay được thử lại. Ví dụ:

~~~java
Mono<Configuration> retriedThenCached = configClient.load()
    .retry(2)
    .cache(Duration.ofMinutes(1));
~~~

Ở đây, retry nằm trước cache. Nguồn có thể được thử lại theo chính sách retry; tín hiệu cuối cùng sau các lần thử được cache. Subscriber sau nhận lại kết quả hoặc lỗi đã cache trong TTL.

Ngược lại:

~~~java
Mono<Configuration> cachedThenRetried = configClient.load()
    .cache(Duration.ofMinutes(1))
    .retry(2);
~~~

Trong trường hợp cache đã lưu lỗi, retry phía sau có thể subscribe lại vào cache và nhận lại cùng lỗi đã lưu, thay vì tạo một request nguồn mới. Vì vậy, retry đặt sau cache thường không có tác dụng thử lại nguồn theo cách người đọc dễ kỳ vọng.

Fallback cũng nên được đặt theo ý nghĩa mong muốn:

~~~java
Mono<Configuration> configuration = configClient.load()
    .onErrorResume(error -> loadDefaultConfiguration())
    .cache(Duration.ofMinutes(1));
~~~

Mẫu này cache cả kết quả fallback. Nếu fallback chỉ nên áp dụng riêng cho một consumer, hãy đặt xử lý lỗi phía sau cache thay vì cache kết quả đã phục hồi. Vị trí toán tử phải phản ánh rõ liệu fallback là một phần của dữ liệu dùng chung hay chính sách riêng của từng consumer.

Timeout đặt trước cache có thể làm timeout trở thành tín hiệu được cache; timeout đặt sau cache giới hạn thời gian chờ của consumer nhưng không nhất thiết thay đổi kết quả nguồn đang được cache. Cần xác định timeout thuộc thao tác tải dữ liệu hay thuộc yêu cầu chờ của từng consumer.

## 10. Cache không tự giải quyết invalidation

Cache chỉ giữ tín hiệu theo chính sách đã cấu hình. Nó không biết khi nào dữ liệu nghiệp vụ thay đổi. Với dữ liệu thay đổi thường xuyên, cần một chiến lược invalidation hoặc refresh:

- TTL ngắn để giới hạn thời gian dữ liệu cũ được sử dụng.
- Làm mới cache khi nhận sự kiện thay đổi cấu hình.
- Tạo publisher cache mới khi version dữ liệu đổi.
- Dùng một cache bên ngoài có key, TTL và invalidation rõ ràng nếu cần quản lý nhiều thực thể.
- Đọc trạng thái mới từ nguồn chính khi yêu cầu freshness cao.

Không nên cache vô thời hạn dữ liệu có thể thay đổi mà không có cơ chế làm mới. Một cache giữ lỗi vô thời hạn cũng có thể khiến lỗi tạm thời trở thành lỗi kéo dài cho mọi subscriber sau.

## 11. Rủi ro bộ nhớ và dữ liệu dùng chung

Chia sẻ và cache giảm công việc lặp lại nhưng có thể tăng thời gian sống của object. Nếu cache giữ một object mutable, nhiều subscriber có thể nhận cùng tham chiếu và thay đổi dữ liệu mà consumer khác đang đọc. Ưu tiên DTO bất biến hoặc copy dữ liệu ở ranh giới consumer nếu cần chỉnh sửa.

Với dữ liệu phụ thuộc tenant, user hoặc quyền truy cập, không chia sẻ một publisher cache giữa các ngữ cảnh khác nhau nếu cache key không thể hiện đầy đủ phạm vi. Ví dụ, không dùng một biến Mono<UserProfile> toàn cục để cache hồ sơ của người dùng hiện tại; subscriber khác có thể nhận dữ liệu sai người dùng. Hãy tạo cache theo khóa tenant/user hoặc theo lifecycle của request/session phù hợp.

Các rủi ro chính:

- Cache không giới hạn: giữ quá nhiều phần tử hoặc object graph trong heap.
- TTL quá dài: consumer nhận dữ liệu cũ.
- Không invalidation: cập nhật từ nguồn chính không được phản ánh.
- Cache lỗi: lỗi tạm thời được phát lại cho nhiều consumer.
- Chia sẻ mutable object: consumer này làm thay đổi dữ liệu consumer khác đang dùng.
- Sai phạm vi bảo mật: dữ liệu của tenant/user này được chia sẻ sang tenant/user khác.
- Nguồn vô hạn: replay hoặc cache toàn bộ stream liên tục làm bộ nhớ tăng.

## 12. Ví dụ chọn cơ chế theo bài toán

### Nhiều widget cùng xem một feed trực tiếp

~~~java
Flux<MarketPrice> livePrices = marketDataClient.prices()
    .share();
~~~

Chọn share() nếu widget chỉ cần giá mới từ lúc tham gia và nguồn nên dừng khi không còn widget nào đăng ký. Nếu widget mới cần giá gần nhất ngay, có thể kết hợp snapshot hoặc replay latest.

### Một lần tải cấu hình dùng chung trong thời gian ngắn

~~~java
Mono<Configuration> configuration = configClient.load()
    .cache(Duration.ofMinutes(2));
~~~

Chọn Mono.cache(Duration) nếu nhiều consumer cần cùng một kết quả trong TTL. Xác định rõ cache có bao gồm lỗi/empty hay không và TTL có phù hợp freshness không.

### Một nguồn chỉ bắt đầu khi đủ hai consumer

~~~java
Flux<Alert> alerts = alertSource.alerts()
    .publish()
    .autoConnect(2);
~~~

Chọn autoConnect(2) nếu nguồn chỉ được khởi động khi hai subscriber đã đăng ký và không cần tự ngắt chỉ vì subscriber rời đi. Nếu cần tự ngắt khi số subscriber giảm, dùng refCount(2).

### Điều khiển nguồn bằng lifecycle của component

~~~java
ConnectableFlux<Metric> metrics = metricSource.metrics()
    .publish();

Disposable connection = metrics.connect();

// Khi component sở hữu nguồn kết thúc:
connection.dispose();
~~~

Chọn kết nối thủ công nếu component có trách nhiệm rõ ràng trong việc bắt đầu và dừng nguồn. Không để handle kết nối bị mất nếu nguồn có thể chạy vô hạn.

## 13. Kiểm thử việc chia sẻ nguồn

Có thể dùng AtomicInteger để đếm số lần nguồn cold được subscribe. Ví dụ, cache() nên chỉ kích hoạt nguồn một lần trong thời gian cache còn hiệu lực:

~~~java
AtomicInteger subscriptions = new AtomicInteger();

Mono<Integer> cached = Mono.fromSupplier(() -> {
    subscriptions.incrementAndGet();
    return 42;
}).cache();

StepVerifier.create(cached)
    .expectNext(42)
    .verifyComplete();

StepVerifier.create(cached)
    .expectNext(42)
    .verifyComplete();

assertEquals(1, subscriptions.get());
~~~

Test xác minh hai subscriber tuần tự nhận cùng giá trị và supplier chỉ được gọi một lần. Có thể bổ sung test cho empty và error để xác minh terminal signal cũng được cache theo semantics của Mono.cache.

### Kiểm thử ConnectableFlux

~~~java
ConnectableFlux<Integer> connectable = Flux.range(1, 3)
    .publish();

List<Integer> firstValues = new ArrayList<>();
List<Integer> secondValues = new ArrayList<>();

connectable.subscribe(firstValues::add);
connectable.subscribe(secondValues::add);

Disposable connection = connectable.connect();

assertEquals(List.of(1, 2, 3), firstValues);
assertEquals(List.of(1, 2, 3), secondValues);

connection.dispose();
~~~

Hai subscriber đăng ký trước khi connect nên đều nhận đủ ba phần tử. Với nguồn đồng bộ hữu hạn, nguồn có thể hoàn tất ngay trong lần gọi connect(). Với nguồn vô hạn, giữ handle connection và dispose khi test kết thúc để không để tác vụ chạy nền.

### Kiểm thử share và vòng đời subscriber

Với share(), nên kiểm tra số lần subscribe nguồn, hành vi khi subscriber đầu tiên đến, khi subscriber cuối hủy và khi một subscriber mới tham gia sau đó. Có thể dùng TestPublisher, doOnSubscribe và doOnCancel để quan sát lifecycle. Điều khiển thứ tự subscribe/phát rõ ràng; không dùng Thread.sleep để giả định một subscriber đã kịp tham gia.

Các trường hợp nên bao phủ:

1. Hai subscriber cùng hoạt động nhận một lần phát upstream.
2. Subscriber đến muộn không nhận lại lịch sử khi dùng share().
3. Subscriber cuối hủy làm ref-count ngắt upstream theo cấu hình.
4. Subscriber mới sau khi ngắt kết nối kích hoạt lifecycle mới theo semantics của phiên bản đang dùng.
5. autoConnect(n) không kết nối trước khi đạt ngưỡng.
6. Cache replay lại value, empty hoặc error theo chính sách đã chọn.
7. TTL hết hạn khiến nguồn được tải lại như kỳ vọng.
8. Retry đặt trước/sau cache có hành vi đúng với chính sách lỗi.

## 14. Bảng chọn nhanh

| Yêu cầu | Cơ chế phù hợp |
| --- | --- |
| Muốn đăng ký nhiều subscriber rồi tự quyết định lúc bắt đầu nguồn | publish() + connect() |
| Tự kết nối khi đủ số subscriber và giữ kết nối sau đó | autoConnect(n) |
| Kết nối khi đủ subscriber và ngắt khi số lượng giảm dưới ngưỡng | refCount(n) |
| Chia sẻ trực tiếp, kết nối ở subscriber đầu tiên và ngắt khi không còn consumer | share() |
| Phát lại lịch sử đã giữ cho subscriber đến muộn, đồng thời điều khiển connect | replay() + connect() |
| Cache kết quả Mono để dùng lại, có thể đặt TTL | Mono.cache(...) |
| Cache một phần lịch sử Flux | Flux.cache(history) hoặc replay có giới hạn |
| Cần dữ liệu bền qua restart hoặc chia sẻ giữa nhiều instance | Cache/broker/store bên ngoài, không chỉ in-memory Reactor |

## 15. Những lỗi thường gặp

- Gọi publish() nhưng quên connect(): nguồn không bắt đầu nên subscriber không nhận dữ liệu.
- Dùng autoConnect rồi mong nguồn tự dừng: autoConnect không phải chính sách ref-count; cần quản lý connection hoặc dùng refCount/share.
- Dùng share() khi cần phát lại lịch sử: subscriber đến muộn không tự nhận các phần tử đã phát.
- Dùng cache() cho nguồn vô hạn không giới hạn: lịch sử có thể giữ trong heap và tăng không ngừng.
- Cho rằng cache chỉ lưu giá trị thành công: Mono.cache có thể cache cả empty và error.
- Đặt retry sau cache và mong nguồn chạy lại: cache có thể phát lại lỗi đã lưu; retry có thể lặp trên cùng tín hiệu lỗi.
- Không đặt TTL hoặc invalidation: consumer có thể nhận dữ liệu cũ trong thời gian dài.
- Chia sẻ cache giữa nhiều tenant/user: có nguy cơ dùng sai dữ liệu hoặc vi phạm phạm vi truy cập.
- Dùng object mutable trong cache: nhiều subscriber có thể quan sát cùng một object đã bị thay đổi.
- Không quản lý Disposable của connect: nguồn vô hạn có thể tiếp tục chạy sau khi component kết thúc.
- Cho rằng cache là lưu trữ bền vững: cache trong bộ nhớ mất khi process dừng và không thay thế database/event store.

## 16. Quy trình chọn và vận hành nguồn dùng chung

Trước khi chọn một operator, hãy xác định:

1. Mỗi subscriber có cần một lần thực thi độc lập hay tất cả dùng chung một lần thực thi?
2. Subscriber đến muộn có cần lịch sử, giá trị mới nhất hay chỉ dữ liệu tương lai?
3. Ai quyết định thời điểm kết nối nguồn?
4. Khi subscriber cuối hủy, upstream cần tiếp tục chạy hay phải dừng?
5. Nguồn là hữu hạn hay vô hạn? Có giới hạn lịch sử và bộ nhớ không?
6. Cache cần TTL, invalidation hoặc refresh theo sự kiện nào?
7. Value, empty và error có được cache như nhau không?
8. Retry và fallback nằm trước hay sau cache theo semantics mong muốn?
9. Dữ liệu có phụ thuộc tenant, người dùng hoặc quyền truy cập không?
10. Ai sở hữu Disposable của kết nối và chịu trách nhiệm giải phóng nó?
11. Test có xác minh số lần subscribe, replay, disconnect, TTL và terminal signal không?

ConnectableFlux cho phép điều khiển rõ thời điểm kết nối; autoConnect tự kết nối khi đủ subscriber; refCount và share gắn vòng đời nguồn với số consumer đang hoạt động; cache lưu tín hiệu để phát lại cho subscriber sau. Chúng giải quyết những nhu cầu khác nhau. Hãy chọn theo cách dữ liệu cần được chia sẻ, thời điểm consumer tham gia, chính sách hủy và thời gian lưu giữ. Giới hạn cache, quản lý connection handle, bảo vệ phạm vi dữ liệu và kiểm thử lifecycle sẽ giúp nguồn dùng chung trong Reactor tiết kiệm tài nguyên mà vẫn giữ đúng semantics của ứng dụng.
