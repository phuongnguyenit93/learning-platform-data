# Ảnh hưởng collectList, cache và replay tới bộ nhớ trong Project Reactor

## 1. Mục tiêu và bối cảnh

Project Reactor cho phép xử lý dữ liệu theo luồng, nhưng một số operator chủ động giữ lại dữ liệu để tạo kết quả tổng hợp hoặc phục vụ subscriber đến sau. Ba trường hợp thường gặp là:

- **collectList()** giữ tất cả phần tử của Flux trong một List và chỉ phát List khi nguồn complete.
- **cache()** giữ các signal để subscriber sau nhận lại dữ liệu đã phát.
- **replay()** giữ lịch sử signal trong một ConnectableFlux để subscriber đến muộn có thể xem lại.

Các operator này hữu ích khi tập dữ liệu có kích thước nhỏ, hữu hạn và chính sách lưu giữ rõ ràng. Chúng trở thành rủi ro khi áp dụng lên stream dài, stream vô hạn, payload lớn, nhiều request đồng thời hoặc publisher sống lâu như bean singleton.

Một ứng dụng reactive vẫn có thể gặp OutOfMemoryError. Backpressure không tự động ngăn một operator chủ động tích lũy dữ liệu trong bộ nhớ.

Bài học trình bày cách các operator tích lũy dữ liệu, cách giới hạn history, lựa chọn streaming/batching/pagination, ước lượng heap, quan sát memory và viết chương trình kiểm thử với Java 17, Reactor 3.8.8 và JUnit.

## 2. collectList() hoạt động thế nào?

API trả về Mono chứa List:

~~~java
Mono<List<T>> result = source.collectList();
~~~

collectList tiêu thụ toàn bộ phần tử do Flux phát, thêm chúng vào một List rồi phát List đó khi nguồn **complete**. Nếu nguồn rỗng, kết quả là List rỗng.

~~~java
Flux.range(1, 5)
    .collectList()
    .subscribe(System.out::println);
~~~

Output:

~~~text
[1, 2, 3, 4, 5]
~~~

Trong suốt thời gian thu thập, List giữ tham chiếu tới mọi phần tử đã nhận. Chỉ khi source complete, Mono<List<T>> mới phát kết quả cho downstream.

### 2.1. collectList không stream kết quả từng phần tử

~~~java
Flux<Order> orders = repository.findAll();
Mono<List<Order>> allOrders = orders.collectList();
~~~

allOrders không phát từng Order. Nó đợi findAll complete rồi phát một List duy nhất. Nếu nguồn có 5 triệu bản ghi, collectList phải giữ đủ 5 triệu phần tử trong bộ nhớ. Nếu nguồn không bao giờ complete, List tiếp tục lớn dần và Mono không phát kết quả.

### 2.2. collectList trên nguồn vô hạn

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(10));
Mono<List<Long>> neverFinishes = ticks.collectList();
~~~

ticks phát liên tục và không tự complete. collectList giữ các giá trị cho đến khi có complete, error hoặc cancel. Nếu subscription sống lâu, danh sách có thể tiếp tục tăng tới khi hết heap.

Không sử dụng collectList trên event stream vô hạn nếu không có giới hạn số phần tử hoặc cửa sổ rõ ràng.

### 2.3. Giới hạn nguồn trước khi collect

~~~java
Mono<List<Order>> firstHundred =
    repository.findAll()
        .take(100)
        .collectList();
~~~

take(100) giới hạn số phần tử trước khi collectList. Đây là tập hợp hữu hạn và có thể dự đoán hơn. Tuy nhiên, 100 phần tử vẫn có thể rất lớn nếu mỗi Order giữ một object graph nặng. Giới hạn số lượng cần đi cùng giới hạn kích thước dữ liệu.

### 2.4. collectSortedList còn tốn thêm CPU

~~~java
Mono<List<Order>> sorted =
    orders.collectSortedList(
        Comparator.comparing(Order::createdAt)
    );
~~~

collectSortedList phải giữ toàn bộ dữ liệu để sort sau khi complete. Với n phần tử, thao tác sort thường có độ phức tạp O(n log n), trong khi bộ nhớ vẫn O(n). Nếu dữ liệu lớn, hãy sort ở database theo index hoặc đọc theo keyset pagination.

## 3. Các operator collect khác cũng có thể giữ dữ liệu

| Operator | Cấu trúc tích lũy | Mức tăng theo dữ liệu |
| --- | --- | --- |
| collectList() | List chứa mọi phần tử | O(n) |
| collectSortedList() | List chứa mọi phần tử rồi sort | O(n), thêm CPU sort |
| collectMap() | Map theo key, giữ giá trị mới nhất cho mỗi key | O(số key duy nhất) |
| collectMultimap() | Map key -> Collection chứa các giá trị | O(tổng số phần tử) |
| collect(Collector) | Container do Collector định nghĩa | Tùy accumulator |
| distinct() | Tập các key đã gặp | O(số key duy nhất) |
| buffer() | Một buffer giữ toàn bộ phần tử tới khi complete | O(n) |
| replay()/cache() | Lịch sử signal được giữ để subscriber sau đọc lại | Theo history/TTL |

### 3.1. collectMap và collectMultimap

~~~java
Mono<Map<String, User>> usersById =
    users.collectMap(User::id);

Mono<Map<String, Collection<Event>>> eventsByType =
    events.collectMultimap(Event::type);
~~~

collectMap giữ giá trị mới nhất cho mỗi key. Nếu có 10 triệu ID khác nhau, Map vẫn có thể giữ 10 triệu entry. collectMultimap giữ mọi Event trong collection theo key; một key có tần suất cao có thể làm collection tiếp tục tăng.

### 3.2. distinct cũng giữ lịch sử đã thấy

~~~java
Flux<Event> unique = events.distinct(Event::id);
~~~

distinct cần nhớ key đã xuất hiện để phát hiện duplicate. Với nguồn vô hạn có cardinality cao, tập key có thể tăng không giới hạn. Nếu chỉ cần một cửa sổ deduplicate, hãy chọn cơ chế có retention/window rõ ràng.

### 3.3. buffer() không tham số cũng là một dạng collect

~~~java
Flux<List<T>> oneLargeBuffer = source.buffer();
~~~

buffer() gom toàn bộ phần tử thành một List và phát khi nguồn complete. Nó có cùng rủi ro tích lũy như collectList. Dùng buffer(maxSize) hoặc bufferTimeout(maxSize, maxTime) khi cần batch hữu hạn.

## 4. cache() của Flux là bộ nhớ replay

Flux.cache() chuyển nguồn thành một hot, replaying Flux. Subscriber đầu tiên kích hoạt việc subscribe nguồn; những subscriber sau nhận lại các signal đã cache theo chính sách của overload.

~~~java
Flux<Integer> cached = Flux.range(1, 5).cache();
~~~

Nếu có hai subscriber, cả hai có thể nhận các giá trị 1 đến 5; subscriber đến sau được replay dữ liệu đã cache.

### 4.1. cache() không giới hạn history

~~~java
Flux<Event> events = eventSource.cache();
~~~

Overload cache() giữ lịch sử onNext không giới hạn. Với event source phát vô hạn, số signal được giữ có thể tăng mãi.

Đây là nguyên nhân phổ biến của memory retention: code không có vòng lặp vô hạn hay static collection tự viết, nhưng cache operator giữ mọi event để replay.

### 4.2. Cache giữ cả terminal signal

Ngoài onNext, cache còn replay completion và error. Nếu một nguồn đã lỗi, subscriber đến sau có thể nhận lại lỗi đã cache thay vì tạo một lần tải mới. Điều này hữu ích khi muốn chia sẻ một kết quả duy nhất, nhưng cũng có thể khiến lỗi tạm thời bị giữ lại lâu hơn mong đợi.

### 4.3. Cache giữ reference, không deep-copy object

Nếu source phát một object Order, cache giữ tham chiếu tới object đó. Subscriber sau nhận lại object đã được cache, không phải một bản deep-copy độc lập.

- Object lớn giữ toàn bộ object graph reachable.
- Mutating object sau khi cache có thể làm subscriber khác thấy trạng thái đã thay đổi.
- Object chứa DataBuffer/ByteBuf hoặc resource có vòng đời riêng không nên được giữ/replay tùy tiện.
- Cache nên chứa dữ liệu immutable hoặc bản biểu diễn an toàn để chia sẻ.

### 4.4. Cache có thể sống lâu bằng service singleton

~~~java
@Service
public class EventService {
    private final Flux<Event> cached =
        eventRepository.streamAll().cache();
}
~~~

Nếu service là singleton và cached được giữ trong field, cache có thể sống suốt vòng đời ứng dụng. Với nguồn vô hạn, toàn bộ lịch sử có thể tiếp tục được giữ trong heap.

Cần kiểm tra publisher được tạo ở đâu, được giữ bởi bean nào và object tham chiếu tới publisher có thể tồn tại bao lâu.

## 5. cache(int history): giới hạn theo số phần tử

~~~java
Flux<Event> recentEvents = eventSource.cache(1_000);
~~~

Reactor giữ tối đa 1.000 signal onNext gần nhất để replay cho subscriber đến sau. Terminal signal complete/error cũng được replay. cache(0) chỉ cache terminal signal, không lưu các phần tử onNext.

### 5.1. Ví dụ history

~~~java
Flux<Integer> recent = Flux.range(1, 10).cache(3);
~~~

Subscriber đầu tiên nhận toàn bộ nguồn:

~~~text
1, 2, 3, 4, 5, 6, 7, 8, 9, 10
~~~

Subscriber đến sau chỉ nhận ba phần tử gần nhất được lưu:

~~~text
8, 9, 10
~~~

Giới hạn history làm cho số lượng tham chiếu giữ lại có trần, bất kể nguồn đã phát bao nhiêu phần tử.

### 5.2. Giới hạn số lượng không phải giới hạn byte

Nếu một Event chỉ chiếm vài trăm byte, 1.000 event có thể rất nhỏ. Nhưng nếu mỗi Event chứa ảnh 5 MiB hoặc object graph lớn, 1.000 phần tử vẫn có thể vượt nhiều GiB.

Chọn history dựa trên số phần tử, kích thước trung bình/cực đại, object graph, số publisher/cache instance và queue ở các tầng khác. Nếu dữ liệu có kích thước biến thiên mạnh, hãy giới hạn payload trước khi đưa vào cache hoặc dùng cache theo byte budget ở tầng phù hợp.

## 6. cache(Duration ttl): TTL không đồng nghĩa giới hạn số phần tử

~~~java
Flux<Event> recentByTime =
    eventSource.cache(Duration.ofMinutes(5));
~~~

Mỗi item có thời gian lưu theo TTL. Terminal signal cũng được replay cho tới khi TTL tương ứng hết hạn; sau khi hết hạn, subscriber mới có thể kích hoạt subscription nguồn mới.

**Điểm rất quan trọng:** cache(Duration) giữ một history không giới hạn về số lượng và áp dụng per-item expiry. Nếu source phát 100.000 item trong 5 phút, cache có thể giữ rất nhiều item trong cửa sổ thời gian đó.

TTL đơn lẻ không phải hard cap cho memory.

Ví dụ:
- Tốc độ 100 event/giây.
- TTL 300 giây.
- Số event còn trong cửa sổ có thể xấp xỉ 30.000.
- Nếu tốc độ tăng lên 10.000 event/giây, số event trong cùng TTL có thể lên tới 3 triệu.

Khi dùng TTL phải ước lượng peak event rate, không chỉ nhìn thời gian TTL.

## 7. cache(history, ttl): giới hạn kép

~~~java
Flux<Event> bounded =
    eventSource.cache(
        1_000,
        Duration.ofMinutes(5)
    );
~~~

Reactor giữ tối đa history 1.000 item và áp dụng TTL cho từng item. Đây là lựa chọn rõ ràng hơn khi cần giới hạn cả hai chiều.

| Cấu hình | Giới hạn count | Giới hạn thời gian |
| --- | --- | --- |
| cache() | Không | Không |
| cache(history) | Có | Không |
| cache(ttl) | Không có hard cap | Có, per item |
| cache(history, ttl) | Có | Có |
| cache(0) | Không lưu onNext | Không expiry cho terminal |

Overload có Scheduler cho phép chọn clock/timer phù hợp trong các trường hợp cần kiểm soát scheduler.

### 7.1. Chọn history theo tải

Nếu hệ thống phát tối đa 200 event/giây và muốn replay gần nhất khoảng 10 giây, có thể bắt đầu với history xấp xỉ 2.000 item. Sau đó cần kiểm thử với burst, event size và số cache instance thực tế.

Không đặt history bằng một số rất lớn chỉ vì muốn tránh mất dữ liệu. Cache là cơ chế replay ngắn hạn trong memory, không phải event store bền vững.

### 7.2. TTL không xóa object khỏi mọi nơi

Khi item hết hạn trong cache, nó không còn được cache cung cấp cho subscriber mới theo chính sách TTL. Tuy nhiên, object chỉ có thể được GC khi không còn strong reference từ cache, subscriber đang xử lý, collection khác, thread-local hoặc cấu trúc dữ liệu của ứng dụng.

TTL không bảo đảm heap lập tức giảm đúng số byte khi hết hạn.

## 8. replay() và ConnectableFlux

replay() cũng tạo một nguồn hot giữ lịch sử để subscriber đến sau nhận lại các phần tử. Khác biệt quan trọng là replay trả về **ConnectableFlux**; ứng dụng kiểm soát thời điểm bắt đầu source bằng connect() hoặc các chiến lược kết nối.

~~~java
ConnectableFlux<Event> replay =
    eventSource.replay(100);

replay.connect();
~~~

Các subscriber đến sau có thể nhận tối đa 100 phần tử gần nhất theo history đã cấu hình.

### 8.1. replay() không giới hạn

~~~java
ConnectableFlux<Event> allHistory = eventSource.replay();
~~~

replay() giữ lịch sử onNext không giới hạn. Nếu nguồn là event stream lâu dài, memory tăng theo thời gian.

### 8.2. replay(int history)

~~~java
ConnectableFlux<Event> lastHundred = eventSource.replay(100);
~~~

Giữ tối đa 100 phần tử gần nhất, cộng terminal signal khi nguồn complete/error.

### 8.3. replay(Duration ttl)

~~~java
ConnectableFlux<Event> lastFiveMinutes =
    eventSource.replay(Duration.ofMinutes(5));
~~~

TTL theo item không đặt hard cap số phần tử. Một stream có tốc độ rất cao vẫn có thể tích lũy nhiều item trong khoảng thời gian đó.

### 8.4. replay(history, ttl)

~~~java
ConnectableFlux<Event> boundedReplay =
    eventSource.replay(
        1_000,
        Duration.ofMinutes(5)
    );
~~~

Kết hợp giới hạn history và TTL. Đây là lựa chọn phù hợp khi cần kiểm soát cả cửa sổ thời gian lẫn số item replay.

### 8.5. connect, autoConnect và refCount

| Cách kết nối | Hành vi |
| --- | --- |
| connect() | Chủ động bắt đầu nguồn |
| autoConnect(n) | Tự connect sau khi đủ n subscriber; không tự ngắt theo ngưỡng subscriber rời |
| refCount(n) | Kết nối khi đủ subscriber và quản lý disconnect theo số subscriber |
| refCount(n, gracePeriod) | Có thời gian chờ trước khi disconnect khi subscriber giảm dưới ngưỡng |

Các chiến lược kết nối quyết định khi nào source chạy và khi nào subscription upstream được quản lý. Chúng không thay thế chính sách history/TTL. Nếu cần giới hạn memory replay, vẫn phải dùng replay(history) hoặc replay(history, ttl).

## 9. So sánh collectList, cache, replay và share

| Operator | Dữ liệu được giữ | Khi nào phát/replay? | Rủi ro chính |
| --- | --- | --- | --- |
| collectList() | Toàn bộ phần tử trong một List | Khi source complete | O(n), nguồn vô hạn không phát kết quả |
| cache() | Toàn bộ onNext và terminal signals | Subscriber đầu kích hoạt, subscriber sau nhận lịch sử | History không giới hạn |
| cache(history) | Tối đa N onNext gần nhất | Tự động kết nối khi cần | N quá lớn hoặc payload quá nặng |
| cache(ttl) | History trong TTL, không có hard cap count | Tự động kết nối khi cần | Burst lớn vẫn giữ rất nhiều item |
| cache(history, ttl) | Tối đa N item và per-item TTL | Tự động kết nối khi cần | Chọn N/TTL không phù hợp |
| replay() | Toàn bộ history | connect()/autoConnect/refCount | History không giới hạn |
| replay(history) | Tối đa N item | ConnectableFlux, điều khiển connect | History quá lớn |
| share() | Chia sẻ tín hiệu live giữa subscriber active, không phải replay toàn bộ history | Kết nối theo subscriber | Không phù hợp nếu subscriber muộn cần lịch sử |

share() không tương đương cache(). Nếu cần subscriber đến sau nhận lại lịch sử, share không cung cấp semantics replay history như cache/replay.

## 10. collectList kết hợp cache có thể giữ dữ liệu ở nhiều tầng

~~~java
Mono<List<Order>> listOnce = orderFlux.collectList();

Mono<List<Order>> cachedList =
    orderFlux.collectList().cache();
~~~

cachedList cache một terminal signal chứa List. Danh sách và các object bên trong có thể được giữ lâu theo vòng đời của cached Mono.

Một dạng khác:

~~~java
Flux<Order> cachedOrders = orderFlux.cache();

Mono<List<Order>> allOrders =
    cachedOrders.collectList();
~~~

Ở đây Flux cache giữ history; collectList tạo thêm một List chứa tham chiếu tới các Order được phát. Trong thời gian subscriber nhận và xử lý List, cả cache lẫn List có thể cùng giữ reference tới object graph.

Điều này không nhất thiết nhân đôi toàn bộ payload vì List và cache có thể cùng trỏ tới một object. Nhưng nó tạo thêm cấu trúc giữ reference và kéo dài thời gian sống của dữ liệu.

### 10.1. Đừng cache List lớn chỉ để tránh truy vấn lại

Nếu kết quả có hàng triệu dòng, nên cân nhắc lưu kết quả ở database/object storage, cache metadata hoặc summary nhỏ, dùng keyset pagination, chia kết quả theo tenant/partition, giới hạn TTL và số entry ở cache ngoài, chỉ cache phần dữ liệu thật sự được truy cập lặp lại.

### 10.2. Cache không phải deep copy

Nếu một subscriber thay đổi List hoặc object mutable đã nhận từ cache, subscriber khác có thể thấy cùng trạng thái đã bị thay đổi. Nên dùng immutable DTO, bản sao có chủ đích hoặc trả về projection không chứa mutable resource.

## 11. Backpressure không tự giới hạn memory retention

Backpressure điều tiết demand giữa Publisher và Subscriber. Nó không loại bỏ việc một operator cố ý tích lũy dữ liệu.

~~~java
Flux<Event> events = eventSource
    .limitRate(100)
    .cache();
~~~

limitRate điều chỉnh lượng request upstream theo từng đợt. cache vẫn giữ history theo chính sách cache; với cache() không giới hạn, memory vẫn có thể tăng theo tổng số event.

Tương tự:

~~~java
eventSource
    .onBackpressureBuffer()
    .collectList();
~~~

Pipeline này có thể có cả buffer và list accumulation. Nếu source nhanh hơn downstream, backlog có thể tăng ở nhiều tầng.

### 11.1. Những tầng memory cần xem

~~~text
Source / driver prefetch
        |
        v
Reactor operator queues
        |
        v
buffer / flatMap / publishOn
        |
        v
cache / replay history
        |
        v
collectList / collectMap
        |
        v
application references / response serialization
~~~

Một giới hạn tại một operator không đồng nghĩa toàn pipeline có giới hạn tương đương. Cần xem concurrency, prefetch, batch size, cache history và dữ liệu giữ bởi controller/service.

### 11.2. flatMap và concurrency

~~~java
source.flatMap(this::remoteCall, 32, 64);
~~~

Concurrency giới hạn số inner Publisher được xử lý đồng thời; prefetch điều khiển số item được request/giữ theo inner. Nếu mỗi inner trả về một object lớn, tổng memory có thể xấp xỉ theo concurrency × prefetch × kích thước object, cộng queue khác.

Không tăng concurrency và prefetch chỉ để cải thiện throughput mà không đo retained heap.

## 12. Cách thay thế collectList khi dữ liệu lớn

### 12.1. Xử lý streaming từng phần tử

~~~java
return repository.findAll()
    .map(this::toResponse)
    .doOnNext(this::recordMetric);
~~~

Controller có thể trả Flux trực tiếp hoặc tiếp tục compose downstream. Mỗi item được xử lý theo luồng; không cần tạo một List toàn bộ.

### 12.2. Reduce về trạng thái có kích thước cố định

~~~java
Mono<Long> totalQuantity =
    orderLines.map(OrderLine::quantity)
        .reduce(0L, Long::sum);
~~~

Accumulator chỉ là một Long nên bộ nhớ tích lũy không tăng theo số phần tử. Tuy nhiên, nếu accumulator là List/Map không giới hạn thì reduce vẫn có thể tích lũy O(n).

### 12.3. Count, any và all

~~~java
Mono<Long> count = source.count();

Mono<Boolean> hasInvalid =
    source.any(item -> !item.isValid());

Mono<Boolean> allValid =
    source.all(Item::isValid);
~~~

Các operator này không cần giữ toàn bộ lịch sử như collectList. any/all có thể kết thúc sớm khi đã có kết luận và cancel upstream.

### 12.4. take(limit)

~~~java
Mono<List<Event>> firstPage =
    source.take(500)
        .collectList();
~~~

Giới hạn số phần tử trước khi thu thập. Đây là giải pháp đơn giản cho một tập dữ liệu hữu hạn có trần rõ ràng.

### 12.5. buffer(maxSize)

~~~java
Flux<List<Event>> batches = source.buffer(500);
~~~

Mỗi batch tối đa 500 item. Khi batch đầy, nó được phát xuống downstream; batch cuối có thể nhỏ hơn nếu source complete.

~~~java
return source.buffer(500)
    .concatMap(batch ->
        repository.saveBatch(batch)
    );
~~~

concatMap giữ một batch đang xử lý tại một thời điểm, giúp kiểm soát concurrency tốt hơn. Tuy nhiên vẫn phải đánh giá queue/prefetch của operator và driver.

### 12.6. bufferTimeout(maxSize, maxTime)

~~~java
Flux<List<Event>> batches =
    source.bufferTimeout(
        500,
        Duration.ofSeconds(1)
    );
~~~

Batch được phát khi đạt 500 item hoặc khi hết một giây. Điều này giúp tránh giữ một batch nhỏ quá lâu khi nguồn phát chậm.

Giới hạn theo thời gian không thay thế giới hạn kích thước: nếu nguồn phát nhanh, maxSize vẫn là hàng rào quan trọng.

### 12.7. window(maxSize)

~~~java
Flux<Flux<Event>> windows = source.window(500);
~~~

window phát các Flux con, mỗi window chứa tối đa 500 event. Consumer phải compose đúng cách với từng window; không giữ nhiều window chưa được tiêu thụ cùng lúc nếu muốn kiểm soát memory.

## 13. Pagination thay cho findAll().collectList()

Một lỗi thường gặp:

~~~java
return repository.findAll().collectList();
~~~

Nếu bảng tăng theo thời gian, request có thể tải toàn bộ dữ liệu vào heap. Hãy dùng pagination hoặc keyset pagination.

### 13.1. Offset pagination

~~~java
Flux<Order> page =
    repository.findByStatus(
        status,
        PageRequest.of(0, 500)
    );
~~~

Offset pagination đơn giản nhưng offset lớn có thể tốn chi phí database và kết quả có thể thay đổi giữa các page nếu dữ liệu được cập nhật đồng thời.

### 13.2. Keyset pagination

~~~java
Mono<List<Order>> loadPage(long afterId) {
    return repository.findTop500ByIdGreaterThanOrderById(afterId)
        .collectList();
}
~~~

Mỗi page có giới hạn 500; sau đó lấy ID cuối cùng để tải page kế tiếp. Keyset pagination thường ổn định hơn với dữ liệu lớn và index phù hợp.

### 13.3. Không giữ mọi page trong một List cuối cùng

~~~java
Flux<Order> allPages =
    pageIds.concatMap(this::loadPage)
        .flatMapIterable(page -> page);
~~~

Đây là snippet minh họa cần pageIds và loadPage. Nếu cuối pipeline lại gọi collectList(), lợi ích memory của pagination bị mất. Hãy xử lý hoặc ghi từng page, chỉ giữ summary nếu nghiệp vụ cần.

## 14. Ước lượng memory và capacity planning

Một ước lượng đơn giản:

~~~text
Retained payload ≈ item count × average retained bytes
Total memory ≈ retained payload + collection/cache overhead
                 + other operator queues + active request state
~~~

Ví dụ giả định:
- 100.000 record trong một collectList.
- Mỗi record và object graph được giữ trung bình khoảng 1 KiB.
- Một request có thể giữ khoảng 97,7 MiB payload.
- Nếu 50 request chạy đồng thời, phần payload tương đương khoảng 4,8 GiB, chưa tính List array, object header, reference, serializer, queue và các object khác.

Đây chỉ là phép tính ngân sách gần đúng. Kích thước thực tế cần đo bằng heap profiler vì object graph, alignment, shared references và compressed oops ảnh hưởng kết quả.

### 14.1. Concurrency nhân lên bộ nhớ

Một request dùng 50 MiB có thể chấp nhận được trong một môi trường nhỏ. Nhưng 100 request đồng thời cùng giữ 50 MiB sẽ vượt 5 GiB chỉ riêng dữ liệu đó.

Capacity planning phải tính số request đồng thời, số stream/cache instance sống cùng lúc, tốc độ phát dữ liệu, thời gian giữ dữ liệu, kích thước payload trung bình và p95/p99, object graph được giữ gián tiếp và các tầng queue/prefetch khác.

### 14.2. Số lượng và byte budget

History=1.000 chỉ giới hạn số item. Nếu item có kích thước từ 1 KiB đến 10 MiB, memory có thể biến động rất lớn.

Cần giới hạn payload bytes trước khi cache, chỉ cache projection nhỏ, tách blob lớn ra object storage, giữ metadata thay cho binary body, giới hạn cả số entry lẫn TTL và dùng cache ngoài có maximum weight/size nếu cần byte-aware eviction.

## 15. Cancellation, error và discard

### 15.1. collectList khi cancel

collectList có discard support: khi subscription bị cancel hoặc lỗi do data signal, các phần tử trong List đang thu thập có thể bị discard. Tuy nhiên, cancellation không biến việc giữ dữ liệu thành miễn phí: List vẫn đã được cấp phát và các reference cần được giải phóng khỏi operator.

### 15.2. DataBuffer và reference-counted objects

Nếu thu thập các DataBuffer/ByteBuf hoặc tài nguyên có reference counting, cần chú ý release đúng ownership.

~~~java
Mono<List<DataBuffer>> body = dataBuffers
    .collectList()
    .doOnDiscard(
        DataBuffer.class,
        DataBufferUtils::release
    );
~~~

Đây là snippet cho Spring WebFlux; cần import DataBuffer, DataBufferUtils và các API tương ứng.

Hook doOnDiscard chỉ áp dụng với các operator có discard support. Sau khi List đã được phát cho downstream, caller nhận quyền sở hữu và phải release theo contract; hook không thay thế trách nhiệm của consumer đối với dữ liệu đã được giao.

### 15.3. Cache giữ resource lâu hơn vòng đời request

Không cache DataBuffer, ByteBuf, file handle, connection hoặc resource có vòng đời ngắn nếu không có quy tắc retain/release rõ ràng. Cache giữ reference lâu hơn request có thể làm tài nguyên không được giải phóng hoặc bị sử dụng sau khi đã release.

Tốt hơn nên cache DTO/metadata immutable, hoặc cache key/locator để tải resource khi thực sự cần.

### 15.4. Error trong cache

Flux.cache replay error signal. Một lỗi transient có thể được giữ và phát lại cho subscriber sau theo chính sách cache/TTL. Nếu muốn retry trước khi cache, phải thiết kế thứ tự operator và số lần retry phù hợp.

~~~java
Flux<Data> cached =
    remoteSource
        .retryWhen(retryPolicy)
        .cache(500, Duration.ofMinutes(1));
~~~

Đây là snippet minh họa cần retryPolicy. Không dùng retry vô hạn rồi cache nếu upstream có thể lỗi kéo dài hoặc tạo tải retry storm.

## 16. Chọn cache theo vòng đời và semantics

- **Dữ liệu cấu hình nhỏ, ít thay đổi:** có thể dùng Mono.cache(Duration) hoặc cache theo key có TTL rõ ràng; cần tính kích thước object và invalidation.
- **Event stream cần replay ngắn hạn:** dùng cache(history, ttl) hoặc replay(history, ttl) với history dựa trên event rate và payload size.
- **Chỉ cần chia sẻ live stream:** cân nhắc share() hoặc publish().refCount() nếu không cần phát lại lịch sử cho subscriber đến muộn.
- **Cần event history bền vững:** không dùng heap cache thay cho Kafka, database log hoặc event store; dùng retention, offset, pagination và replay theo cursor.
- **Cần cache theo key:** cân nhắc Caffeine hoặc Spring Cache với maximumSize/maximumWeight, expireAfterWrite/expireAfterAccess và chính sách invalidation.

Đừng dùng một publisher cache duy nhất cho nhiều user nếu source phụ thuộc security context của subscriber. Cache có thể chia sẻ dữ liệu đã được tạo theo người đầu tiên và gây rò dữ liệu giữa tenant/user.

## 17. Ví dụ dự án Java 17 và Reactor 3.8.8

Dự án minh họa collectList gom toàn bộ một nguồn hữu hạn, buffer(3) phát các batch có kích thước giới hạn, cache(2) chỉ giữ hai item cuối cho subscriber đến sau, replay(2) giữ hai item gần nhất trong ConnectableFlux và JUnit kiểm tra output cùng số lần source được subscribe.

Cấu trúc:

~~~text
reactor-memory-retention-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/memory/
    │       └── MemoryRetentionDemo.java
    └── test/
        └── java/com/example/memory/
            └── MemoryRetentionTest.java
~~~

### 17.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactor-memory-retention-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.3</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 17.2. MemoryRetentionDemo.java

~~~java
package com.example.memory;

import java.util.List;

import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;

public class MemoryRetentionDemo {

    public static void main(String[] args) {
        List<Integer> all = Flux.range(1, 10)
            .collectList()
            .block();

        System.out.println("collectList=" + all);

        Flux.range(1, 10)
            .buffer(3)
            .doOnNext(batch ->
                System.out.println("batch=" + batch)
            )
            .blockLast();

        Flux<Integer> cached =
            Flux.range(1, 5).cache(2);

        List<Integer> first = cached
            .collectList()
            .block();

        List<Integer> late = cached
            .collectList()
            .block();

        System.out.println("cache first=" + first);
        System.out.println("cache late=" + late);

        ConnectableFlux<Integer> replay =
            Flux.range(1, 5).replay(2);

        replay.connect();

        List<Integer> replayed = replay
            .collectList()
            .block();

        System.out.println("replay late=" + replayed);
    }
}
~~~

Trong chương trình main, block() chỉ dùng ở ranh giới CLI để in kết quả. Không gọi block() trong WebFlux controller, Netty event-loop hoặc một reactive chain production.

### 17.3. MemoryRetentionTest.java

~~~java
package com.example.memory;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class MemoryRetentionTest {

    @Test
    void collectListEmitsAllItemsAtCompletion() {
        StepVerifier.create(
                Flux.range(1, 5).collectList()
            )
            .expectNext(List.of(1, 2, 3, 4, 5))
            .verifyComplete();
    }

    @Test
    void bufferEmitsBoundedBatches() {
        StepVerifier.create(
                Flux.range(1, 7).buffer(3)
            )
            .expectNext(
                List.of(1, 2, 3),
                List.of(4, 5, 6),
                List.of(7)
            )
            .verifyComplete();
    }

    @Test
    void cacheHistoryReplaysOnlyLastNItemsToLateSubscriber() {
        AtomicInteger subscriptions = new AtomicInteger();

        Flux<Integer> source = Flux.defer(() -> {
            subscriptions.incrementAndGet();
            return Flux.range(1, 5);
        });

        Flux<Integer> cached = source.cache(2);

        StepVerifier.create(cached)
            .expectNext(1, 2, 3, 4, 5)
            .verifyComplete();

        StepVerifier.create(cached)
            .expectNext(4, 5)
            .verifyComplete();

        assertEquals(1, subscriptions.get());
    }

    @Test
    void replayHistoryRetainsLastNItemsForLateSubscriber() {
        ConnectableFlux<Integer> replay =
            Flux.range(1, 5).replay(2);

        replay.connect();

        StepVerifier.create(replay)
            .expectNext(4, 5)
            .verifyComplete();
    }

    @Test
    void takeBeforeCollectListBoundsCollectedCount() {
        StepVerifier.create(
                Flux.range(1, 1_000_000)
                    .take(4)
                    .collectList()
            )
            .expectNext(List.of(1, 2, 3, 4))
            .verifyComplete();
    }

    @Test
    void reduceCanKeepOnlyScalarState() {
        StepVerifier.create(
                Flux.range(1, 100)
                    .map(Integer::longValue)
                    .reduce(0L, Long::sum)
            )
            .expectNext(5050L)
            .verifyComplete();
    }
}
~~~

### 17.4. Output chính xác

Chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.memory.MemoryRetentionDemo
~~~

Output:

~~~text
collectList=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
batch=[1, 2, 3]
batch=[4, 5, 6]
batch=[7, 8, 9]
batch=[10]
cache first=[1, 2, 3, 4, 5]
cache late=[4, 5]
replay late=[4, 5]
~~~

Chạy test:

~~~bash
mvn clean test
~~~

Kỳ vọng: 6 JUnit tests PASS. Dự án chỉ dùng Reactor Core/Test, không cần khởi động Spring Boot.

## 18. Kiểm tra memory trong ứng dụng thực tế

### 18.1. JVM metrics

Theo dõi heap used/committed/max, old generation occupancy, allocation rate, GC count/pause, số request đang hoạt động, số cache/publisher instance còn sống, history/TTL theo cấu hình và queue/prefetch của các operator có thể tích lũy dữ liệu.

Có thể dùng Micrometer/Actuator metrics như JVM memory và GC metrics. Không gắn user ID hoặc request ID có cardinality cao vào metric tag.

### 18.2. JFR

Java Flight Recorder giúp quan sát allocation rate, object allocation hot spots, GC và thời gian sống của object. Dùng JFR trong load test để tìm operator hoặc service đang tạo quá nhiều collection/DTO.

### 18.3. Heap dump và dominator tree

Khi heap tăng liên tục:

1. Chụp heap dump ở thời điểm tải cao.
2. Mở bằng Eclipse MAT hoặc công cụ tương đương.
3. Xem dominator tree và retained heap.
4. Tìm các List, Map, cache node hoặc object graph chiếm phần lớn heap.
5. Truy ngược đường tham chiếu về service singleton, field hoặc Reactor publisher.
6. Đối chiếu với code collectList/cache/replay và lifecycle của subscription.

Một List lớn có thể chỉ là triệu chứng; nguyên nhân giữ List có thể là Mono cache hoặc một service field giữ publisher lâu dài.

### 18.4. Load test

Thiết kế test với dataset nhỏ/lớn, event rate bình thường/burst, nhiều request đồng thời, client cancel giữa stream, subscriber đến muộn vào cache/replay, cache TTL hết hạn, source complete/error, nhiều tenant/user/cache instance và payload kích thước p50/p95/p99.

Đo cả heap sau GC và retained heap, không chỉ RSS hoặc heap used tại một thời điểm.

## 19. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| OOM sau khi gọi findAll | collectList giữ toàn bộ kết quả | Pagination hoặc streaming |
| Mono<List<T>> không bao giờ phát | Nguồn vô hạn chưa complete | Giới hạn source hoặc dùng batch/window |
| Heap tăng theo thời gian | Flux.cache()/replay() không giới hạn | cache(history) hoặc replay(history) |
| Dùng cache(Duration) nhưng vẫn OOM | TTL không có hard cap số item | cache(history, ttl) |
| Subscriber muộn nhận toàn bộ event cũ | cache()/replay() không giới hạn history | Đặt history phù hợp |
| cache lỗi và mọi request sau đều lỗi | Error signal được replay | TTL/invalidation và retry policy rõ ràng |
| Dữ liệu user A xuất hiện ở user B | Dùng chung cache cho source phụ thuộc user | Cache key/tenant isolation hoặc không cache |
| Mutable DTO thay đổi giữa subscribers | Cache giữ cùng object reference | Immutable DTO hoặc copy có chủ đích |
| collectSortedList tốn heap/CPU | Giữ và sort toàn bộ dữ liệu | Sort ở database, keyset pagination |
| collectMultimap tăng không dừng | Mỗi value được lưu trong collection | Giới hạn key/window hoặc xử lý từng batch |
| distinct() tăng heap | Lưu tất cả key đã thấy | Giới hạn cửa sổ dedup |
| buffer() gây OOM | Một List buffer đợi complete | buffer(maxSize)/bufferTimeout |
| limitRate không giải quyết memory | Nó điều chỉnh demand, không giới hạn cache/list | Giới hạn operator giữ dữ liệu |
| flatMap làm tăng memory | Concurrency/prefetch quá cao | Giảm concurrency/prefetch, đo payload |
| TTL hết hạn nhưng heap chưa giảm | Reference khác còn giữ object hoặc GC chưa chạy | Heap dump và dominator tree |
| Cache DataBuffer gây leak | Resource reference-counted bị giữ quá lâu | Cache metadata, release đúng ownership |
| Chỉ đo heap hiện tại mà bỏ sót allocation | GC che dấu tốc độ cấp phát cao | JFR và allocation profiling |
| replay(refCount) vẫn giữ lịch sử quá lớn | Lifecycle connect khác history retention | Giới hạn replay history/TTL |
| Chuyển sang buffer nhưng queue vẫn tăng | Downstream chậm và các batch chờ xử lý | Giới hạn concurrency, prefetch và queue |

## 20. Checklist thiết kế

Trước khi đưa collectList/cache/replay vào production:

1. Nguồn có complete hữu hạn không?
2. Số phần tử tối đa có thể dự đoán không?
3. Kích thước payload p95/p99 là bao nhiêu?
4. collectList có thật sự cần một List hoàn chỉnh?
5. Có thể dùng reduce/count/any/all thay thế?
6. Có thể dùng buffer(maxSize) hoặc bufferTimeout?
7. Có thể phân trang database theo keyset?
8. Cache có history count giới hạn?
9. TTL có kết hợp hard count limit khi event rate cao?
10. Cache có giữ lỗi/terminal signal quá lâu?
11. Cache publisher được giữ bởi bean/request nào?
12. Object có immutable và an toàn để replay?
13. Có dữ liệu user/tenant cần cache isolation?
14. Có resource reference-counted trong item?
15. Concurrency/prefetch/queue của các operator khác có được tính?
16. Cancellation/error có cleanup dữ liệu bị discard?
17. Có JVM metrics, JFR hoặc heap dump khi cần?
18. Load test có burst, concurrent requests và late subscribers?
19. Có giới hạn memory theo instance/tenant?
20. Có kế hoạch fallback khi cache vượt budget?

## 21. Bài tập thực hành

**Bài 1 — collectList:** dùng Flux.range(1, 10).collectList() và quan sát Mono chỉ phát List khi source complete.

**Bài 2 — nguồn vô hạn:** dùng Flux.interval().collectList(); giải thích vì sao không phát kết quả và memory tăng theo thời gian.

**Bài 3 — take:** thêm take(100) trước collectList và kiểm tra số phần tử tối đa.

**Bài 4 — collectMap:** tạo 100.000 item với 1.000 key; đo số entry và số object được giữ.

**Bài 5 — collectMultimap:** so sánh memory với collectMap khi nhiều item cùng key.

**Bài 6 — cache unbounded:** tạo Flux.range(...).cache() rồi subscribe lần hai; quan sát replay.

**Bài 7 — cache(history):** thay bằng cache(10), xác minh subscriber muộn chỉ nhận 10 item cuối.

**Bài 8 — TTL:** dùng cache(Duration) và cache(history, Duration), tạo burst event và so sánh số item còn được replay.

**Bài 9 — replay:** dùng replay(5), connect trước subscriber, xác minh history.

**Bài 10 — share:** thay replay bằng share và kiểm tra subscriber đến muộn không nhận toàn bộ history.

**Bài 11 — batch:** dùng buffer(500) và bufferTimeout(500, Duration.ofSeconds(1)); đo batch size và latency.

**Bài 12 — reduce:** thay collectList bằng reduce để tính tổng; so sánh memory.

**Bài 13 — concurrency:** chạy nhiều request collectList đồng thời với dataset lớn và đo heap.

**Bài 14 — object graph:** cache DTO chứa một List lớn, dùng heap dump xác định retained heap.

**Bài 15 — cancellation:** cancel subscription khi collectList đang thu thập và kiểm tra discard cleanup với resource phù hợp.

**Bài 16 — DataBuffer:** thêm doOnDiscard và xác minh release của buffer bị loại bỏ khi cancel/error.

**Bài 17 — keyset pagination:** tải 10.000 bản ghi theo page 500 và xử lý từng page mà không collect tất cả.

**Bài 18 — observability:** bật JFR, tìm allocation hotspot và dominator tree của cache/list trong load test.

## 22. Ghi nhớ

**collectList() giữ toàn bộ phần tử cho tới khi source complete.** Với nguồn vô hạn, nó có thể không bao giờ phát kết quả và tiếp tục tăng memory. collectMap, collectMultimap, collectSortedList, distinct và buffer() cũng có thể giữ dữ liệu theo số phần tử/key đã gặp.

**Flux.cache() và replay() không giới hạn có thể giữ toàn bộ lịch sử signal.** cache(history) và replay(history) giới hạn số phần tử. cache(ttl) và replay(ttl) có per-item expiry nhưng không có hard cap count. Khi cần cả hai, dùng cache(history, ttl) hoặc replay(history, ttl).

Backpressure điều tiết demand, không tự xóa dữ liệu mà operator chủ động giữ. Hãy dùng streaming, reduce, pagination, buffer có maxSize, giới hạn concurrency/prefetch và cache bounded. Đánh giá theo **số lượng × kích thước object graph × số request/cache đồng thời**, sau đó xác minh bằng JFR và heap dump.

## 23. Tài liệu tham khảo

- Project Reactor Core 3.8 Reference — Which operator do I need?: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Reactor Core 3.8.8 API — Flux.collectList: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Core 3.8.8 API — Flux.cache(history, ttl): https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Core 3.8.8 API — Flux.replay(history, ttl): https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Core Reference — Multicasting a Flux to several Subscribers: https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html
- Reactor Core Reference — Backpressure: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Reactor Core Reference — Cleanup and Discard Support: https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html
- Spring Framework Reference — Reactive Data Access: https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
- Spring Framework Reference — WebFlux Reactive Types: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
- Java Flight Recorder — Oracle Documentation: https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html
- Eclipse Memory Analyzer (MAT): https://eclipse.dev/mat/
