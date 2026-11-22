# Flux: thu thập toàn bộ kết quả thành danh sách trước khi lưu trong Spring Cache

> **Chủ đề:** Spring Framework – Cache · **Nhóm:** Bất đồng bộ.  
> **Mục tiêu:** hiểu chính xác vì sao một method khai báo trả về `reactor.core.publisher.Flux<T>` có thể được Spring Cache lưu dưới dạng **một danh sách các phần tử đã phát** thay vì cache lần lượt từng phần tử; nắm cơ chế từ Spring Framework 6.1+, yêu cầu của cache backend bất đồng bộ, hệ quả lên streaming/backpressure/bộ nhớ, cũng như cách kiểm thử và chọn thiết kế phù hợp.

## 1. Khác biệt giữa kiểu trả về `Flux<T>` và dữ liệu thực sự được cache

`Flux<T>` là một `Publisher` có thể phát **0 đến N phần tử**, rồi hoàn thành (`onComplete`), hoặc kết thúc bằng lỗi (`onError`). Nó không đồng nghĩa với một `List<T>` đã được tính sẵn. Một cold `Flux` thông thường chỉ chạy tác vụ nguồn khi có subscriber.

Ví dụ một service phản ứng:

```java
@Cacheable(cacheNames = "searchResults", key = "#p0")
public Flux<String> search(String query) {
    return repository.findMatchingNames(query);
}
```

Đây là **snippet trong Spring-managed service** có repository phản ứng phù hợp, không phải file độc lập.

Kể từ **Spring Framework 6.1**, cơ chế caching annotation hỗ trợ thích nghi các kiểu trả về bất đồng bộ, bao gồm `CompletableFuture`, Reactor `Mono` và `Flux`, với điều kiện đường lưu trữ async tương ứng được cache provider hỗ trợ.

Đối với `Flux<T>`, một cache operation không giữ một `Flux` tùy ý để subscriber sau tự subscribe lại. Thay vào đó, Spring **thu thập toàn bộ các giá trị mà Flux phát ra thành một `List<T>`**, chờ nguồn hoàn tất, rồi cache kết quả tập hợp đó. Khi cache hit, các giá trị trong danh sách được phát lại cho subscriber dưới dạng một `Flux<T>`.

Sơ đồ ở mức logic:

```text
Client gọi search("java")
  │
  ▼
Spring @Cacheable, key="java"
  │
  ├── Hit: lấy danh sách đã cache
  │           ["JDK", "Spring", "Reactor"]
  │               │
  │               └── chuyển thành Flux phát lại lần lượt các phần tử
  │
  └── Miss: gọi publisher nguồn
                │
                ├── onNext("JDK")
                ├── onNext("Spring")
                ├── onNext("Reactor")
                └── onComplete()
                        │
                        ▼
                collectList() theo semantics tương đương
                        │
                        ▼
                List ["JDK", "Spring", "Reactor"]
                        │
                        ▼
                cache dưới MỘT key "java"
                        │
                        ▼
                phát lại thành Flux cho caller
```

**Điểm quan trọng:** mỗi cache key tương ứng **một tập kết quả hoàn chỉnh** (snapshot logic của một lần subscription), không phải một key cho từng phần tử `onNext`. Khi phương thức được gọi với query khác, Spring sinh key khác nếu biểu thức `key`/`KeyGenerator` có phân biệt query đó.

### 1.1. Tại sao phải đợi hoàn thành?

Với một tập kết quả hữu hạn, nếu cache một danh sách chưa đầy đủ ngay lúc mới có phần tử đầu, subscriber sau có thể nhìn thấy kết quả nửa chừng mà không biết có bao nhiêu phần tử còn thiếu. Thu thập tới `onComplete` cho phép cache một kết quả nhất quán ở mức **danh sách đã được nguồn phát hoàn chỉnh**.

Đổi lại, việc gom danh sách đòi hỏi **buffer các phần tử trong bộ nhớ** và có thể trì hoãn việc phát kết quả cho caller khi đi qua tầng cache. Đây là sự đánh đổi lớn đối với các API được thiết kế để truyền dữ liệu từng phần tử ngay khi có.

### 1.2. So sánh `Mono<T>`, `Flux<T>`, và `List<T>`

| Method trả về | Điều được cache theo cơ chế thích nghi | Điểm cần lưu ý |
|---|---|---|
| `T` đồng bộ | Giá trị `T` | Thường xử lý trong lời gọi đồng bộ |
| `CompletableFuture<T>` | Giá trị tương lai được hoàn thành bất đồng bộ | Backend cần hỗ trợ async retrieval |
| `Mono<T>` | Tối đa một giá trị khi Mono hoàn tất | Không cache publisher như một object bất biến thông thường |
| `Flux<T>` | **Danh sách giá trị** từ Flux đã hoàn tất | Tập hợp toàn bộ kết quả, có rủi ro về kích thước và streaming |
| `List<T>` đồng bộ | Một object `List<T>` do method trả về | Chính method đã chịu chi phí tạo danh sách |

Với `Flux` và `Mono`, cách thích nghi phụ thuộc hạ tầng cache annotation của Spring Framework 6.1+ và backend được cấu hình; **không nên mặc định suy tính năng này có trong Spring Framework 5.x hoặc mọi custom Cache implementation**.

## 2. Cơ chế khi cache miss: từ publisher thành danh sách

Một `Flux` có thể chỉ là mô tả của một công việc, chưa chạy. Để cache được **kết quả**, tầng cache phải theo dõi quá trình hoàn tất của publisher và thu gom phần tử.

Ví dụ nguồn có ba phần tử:

```java
Flux<String> names = Flux.just("Ada", "Bob", "Chi");
```

Về mặt Reactor, cách gom thành danh sách:

```java
Mono<List<String>> allNames = names.collectList();
```

Đoạn này là **minh họa khái niệm Reactor**, không phải code nội bộ chính xác từng dòng của Spring Cache. `collectList()` chờ `onComplete` rồi mới phát một `List` chứa đầy đủ phần tử. Spring Cache dùng một chiến lược thích nghi tương đương để giữ các giá trị được phát ra bởi `Flux` trước khi cache.

Trong Spring 6.1+:

1. Cache interceptor xác định cache name và key từ method/arguments.
2. Với cache hit, dữ liệu đã hoàn chỉnh được lấy từ cache qua đường hỗ trợ async và **biến trở lại Flux phát các phần tử**.
3. Với cache miss, publisher do target method cung cấp được subscribe trong chuỗi xử lý thích nghi.
4. Các `onNext` được tập hợp vào một danh sách; `onComplete` là điều kiện để có **kết quả danh sách thành công**.
5. Danh sách được đưa vào cache như một giá trị logic của key.
6. Subscriber nhận các phần tử từ danh sách sau khi công việc bất đồng bộ hoàn tất.

**Không nói rằng Spring tạo một cache entry mới cho từng `onNext`.** Phạm vi cache operation là **kết quả của cả method invocation** ứng với một key.

### 2.1. Một Flux hai phần tử vẫn là một cached result

```java
@Cacheable(cacheNames = "codes", key = "#p0")
public Flux<String> codes(String locale) {
    return Flux.just(locale + "-A", locale + "-B");
}
```

Nếu `locale="vi"`, kết quả logic được cache là danh sách hai item `["vi-A","vi-B"]` dưới key `"vi"`. Lần sau gọi cùng locale có thể nhận hai item từ cache mà không thực thi lại nguồn.

### 2.2. Cache key là của lời gọi, không của từng item

```java
@Cacheable(
    cacheNames = "ordersByCustomer",
    key = "#p0 + ':' + #p1"
)
public Flux<Order> orders(String tenantId, String customerId) {
    return repository.findByTenantAndCustomer(tenantId, customerId);
}
```

Đây là snippet minh họa, cần `Order` và repository. Key phân biệt tenant + customer; cả **danh sách orders của customer** được lưu cùng một key. Nếu bỏ `tenantId` khỏi key khi kết quả khác nhau theo tenant, việc cache cả danh sách có thể khiến dữ liệu nhạy cảm của một tenant bị trả sang tenant khác.

Nếu method phụ thuộc locale, quyền truy cập, bộ lọc, trang, sort, version hoặc feature flag, các thành phần làm thay đổi kết quả phải xuất hiện trong cache key hoặc namespace phù hợp.

## 3. Hệ quả lớn: không còn streaming theo phần tử tới người dùng như trước

Cần phân biệt **API trả về kiểu `Flux`** với **đường đi thực tế của dữ liệu**.

Khi không có tầng cache gom kết quả, một endpoint WebFlux có thể nhận và phát từng record ngay lúc repository tạo ra record đó. Khi có `@Cacheable` thích nghi `Flux` bằng cách gom thành danh sách:

- Tầng cache cần chờ toàn bộ upstream hoàn tất để có danh sách.
- Giá trị cache chưa thể được xem là thành công đầy đủ khi nguồn mới phát vài phần tử.
- Dữ liệu phải được buffer trong memory trước khi thành tập cacheable.
- Kết quả có thể được phát lại theo danh sách; semantics end-to-end không còn là "nhận record đầu từ upstream rồi chuyển ngay đến client".

Tình huống:

```text
Nguồn phát:
t=0.1s: item 1
t=0.2s: item 2
t=0.3s: item 3
t=4.0s: item 4 + onComplete

Nếu đi qua caching kiểu gom danh sách:
    Phải chờ nguồn hoàn tất để có danh sách [1,2,3,4].
    Không thể giả định item 1 đã tới client tại t=0.1s.
```

Các mốc trên là **ví dụ minh họa**, không phải benchmark của Reactor hoặc một provider cụ thể. Điểm đúng về cơ chế là **yêu cầu materialize toàn bộ danh sách** khiến kết quả không còn đặc tính truyền trực tiếp từng item của streaming upstream.

### 3.1. Backpressure bị thay đổi ý nghĩa

Reactive Streams có cơ chế `request(n)`: downstream có thể yêu cầu số phần tử phù hợp khả năng xử lý. Nhưng `collectList` cần tiêu thụ **toàn bộ upstream** để hoàn tất danh sách. Vì vậy việc downstream tiêu thụ chậm từng item sau khi cache hit **không tương đương** khả năng giảm mức đọc dữ liệu upstream của lần cache miss.

Không nên đưa `@Cacheable` lên một Flux rất lớn chỉ vì method trả về Reactive type. Việc gom nhiều giá trị có thể chiếm heap đáng kể dù downstream chỉ cần vài item đầu tiên.

### 3.2. Tương tác với timeout và kết nối client

Giả sử một request chỉ muốn xem 10 record đầu trong 1.000.000 record, nhưng method cacheable trả toàn bộ `Flux`. Nếu cache adapter cố gom toàn bộ, có thể tạo thời gian chờ dài và lưu một danh sách không cần thiết. `take(10)` ở phía subscriber **sau** tầng cache không phải biện pháp chắc chắn giới hạn công việc của upstream, vì upstream của cache đã cần được thu hết.

Hãy giới hạn tại **query hoặc nguồn trước khi tầng cache gom**, ví dụ phân trang SQL, giới hạn record hoặc nhận tham số `limit` hợp lệ ở method.

### 3.3. Một số loại luồng không phù hợp

| Loại Flux | Cache toàn bộ danh sách có phù hợp? | Vì sao |
|---|---|---|
| `Flux.just(a,b,c)` hữu hạn, nhỏ | Thường phù hợp | Ít dữ liệu, có `onComplete` |
| Kết quả query đã phân trang 20 record | Thường phù hợp | Budget rõ ràng, một key cho một page |
| `Flux.empty()` | Có thể biểu diễn bằng danh sách rỗng | Phải kiểm tra empty/null policy của provider |
| `Flux.error(...)` | Không có danh sách hoàn tất thành công | Không nên coi lỗi là dữ liệu thành công được cache |
| `Flux.never()` | Không phù hợp | Không có `onComplete` để hoàn tất danh sách |
| `Flux.interval(...)` vô hạn | Không phù hợp | Không kết thúc; nguy cơ lưu giữ/buffer lâu dài |
| SSE/WebSocket live stream | Không phù hợp | Luồng hoạt động liên tục, không phải snapshot hữu hạn |
| Export hàng triệu bản ghi | Thường không phù hợp | Mất lợi ích streaming, nguy cơ OOM và latency |
| Trang tìm kiếm 50 dòng cố định | Phù hợp hơn | Kích thước, key và TTL có thể kiểm soát |

## 4. Vì sao cần cache backend có khả năng truy xuất bất đồng bộ?

Hỗ trợ `Flux` không chỉ là việc Spring nhận ra kiểu trả về. Cơ chế cache phải có khả năng tích hợp với **giá trị sẽ hoàn tất trong tương lai**.

Spring Cache API có các thao tác bất đồng bộ, tiêu biểu:

```java
CompletableFuture<?> retrieve(Object key);

<T> CompletableFuture<T> retrieve(
    Object key, Supplier<CompletableFuture<T>> valueLoader);
```

Đây là **chữ ký minh họa** của giao diện `org.springframework.cache.Cache`. Từng provider có thể hỗ trợ khác nhau; `Cache.retrieve` được thiết kế cho đường truy xuất không chặn khi dữ liệu hoặc computation còn đang chờ.

Đối với `Flux<T>`, cache operation gắn với một giá trị logic kiểu **`List<T>` được tạo bất đồng bộ**. Thường có thể hình dung:

```text
Flux<T> source
   -> collect toàn bộ
   -> CompletableFuture<List<T>> hoàn tất
   -> async cache storage
   -> cache hit: List<T>
   -> Flux phát lại T từ List
```

Không nên dùng sơ đồ này để khẳng định mọi implementation nội bộ của Spring đều có đúng một class/future giống nhau; đây là **mô hình tư duy đúng cho việc cache kết quả theo danh sách và async retrieval**.

### 4.1. `ConcurrentMapCacheManager` và `CaffeineCacheManager`

Spring Framework hỗ trợ đường tương thích với async cache trong các implementation chuẩn, ví dụ:

- `ConcurrentMapCache` có các phương thức async retrieval thích hợp cho trường hợp thông dụng.
- `CaffeineCacheManager` có **async cache mode** từ Spring Framework 6.1; bật bằng `setAsyncCacheMode(true)` để dùng Caffeine `AsyncCache`.

Khi dùng một `CacheManager` tùy chỉnh hoặc provider bên ngoài, đừng mặc định `retrieve` được hỗ trợ chỉ vì `get`/`put` có sẵn. Hãy đọc Javadoc, adapter implementation và viết integration test với return type `Flux<T>` thật.

### 4.2. Caffeine async mode là gì?

Ví dụ Java configuration:

```java
@Bean
public CacheManager cacheManager() {
    CaffeineCacheManager manager =
            new CaffeineCacheManager("resultPages");
    manager.setAsyncCacheMode(true);
    manager.setCaffeine(Caffeine.newBuilder()
            .maximumSize(500)
            .expireAfterWrite(Duration.ofMinutes(5)));
    return manager;
}
```

Đây là snippet nằm trong một Spring `@Configuration` class, yêu cầu các import và Caffeine dependency thích hợp; ví dụ source hoàn chỉnh ở mục 7.

`setAsyncCacheMode(true)` yêu cầu manager sử dụng native Caffeine asynchronous cache để hỗ trợ phù hợp cho kết quả future/reactive. Nó **không biến một Flux vô hạn thành hữu hạn**, không tự đặt giới hạn số item trong một danh sách, và không áp dụng một quota tổng số item trong tất cả các list.

### 4.3. Hai giới hạn capacity khác nhau

`maximumSize(500)` trên Caffeine có nghĩa là **tối đa khoảng 500 cache entries/keys**, không phải 500 phần tử tổng cộng của các `List<T>` được cache.

Ví dụ một cache giữ 500 key, mỗi key chứa list 10.000 records:

```text
500 keys × 10.000 elements / list
   = 5.000.000 referenced elements
```

Đây là ước lượng ở mức số phần tử, không phải heap bytes. Cần budget cả object graph, overhead, key và các copy trung gian. Để giới hạn tổng dung lượng tốt hơn, cân nhắc weighted Caffeine cache bằng `maximumWeight` + `weigher` nếu có cách cân kích thước snapshot đáng tin, hoặc giới hạn trực tiếp số item/page/response ở tầng dữ liệu.

## 5. Ví dụ nghiệp vụ: nên cache kết quả Flux nào?

### 5.1. Trang kết quả tìm kiếm hữu hạn

```java
@Cacheable(
    cacheNames = "productPages",
    key = "#tenantId + ':' + #page + ':' + #size"
)
public Flux<Product> findPage(
        String tenantId, int page, int size) {
    int safeSize = Math.min(size, 50);
    return repository.findPage(tenantId, page, safeSize);
}
```

Đây là snippet trong service có `Product`/repository, không phải file runnable. Trong production nên validate `size >= 1` và giới hạn **trước** khi tính key, hoặc key phản ánh đúng `safeSize` để tránh key dư thừa. Hãy chuẩn hóa sort/filter, bao gồm quyền truy cập và tenant khi ảnh hưởng kết quả.

Với một trang cỡ tối đa 50 item và TTL ngắn, việc gom danh sách tương đối dễ kiểm soát.

### 5.2. Lịch sử sự kiện theo cửa sổ thời gian

```java
@Cacheable(
    cacheNames = "recentEvents",
    key = "#customerId + ':' + #from + ':' + #to"
)
public Flux<EventDto> events(
        String customerId, Instant from, Instant to) {
    return repository.findEvents(customerId, from, to);
}
```

Snippet này chỉ nên dùng nếu cửa sổ thời gian được giới hạn và số bản ghi tối đa hợp lý. Nếu client có thể truyền khoảng 30 năm, danh sách có thể rất lớn. Cần giới hạn range, số item và phân trang ở database; không chỉ dùng `timeout` để hy vọng giữ memory trong giới hạn.

### 5.3. Dữ liệu tài chính hoặc quyền truy cập

Với dữ liệu cần độ tươi rất cao (quyền tài khoản, số dư...), cache toàn bộ Flux có thể nguy hiểm khi cùng key được dùng sau cập nhật, nhất là với TTL dài hoặc invalidation thiếu. Cache snapshot theo list không tự đảm bảo consistency; phải có version/tenant/permission scope đúng và đường invalidation sau commit khi nghiệp vụ yêu cầu.

### 5.4. Khi `Mono<List<T>>` biểu đạt nghiệp vụ rõ hơn

Nếu endpoint về bản chất luôn trả một **tập kết quả hữu hạn** có giới hạn, việc khai báo rõ `Mono<List<T>>` có thể giúp người viết code nhận ra đây là một aggregate chứ không phải unbounded stream:

```java
@Cacheable(cacheNames = "productPages", key = "#p0")
public Mono<List<Product>> findSnapshot(String pageKey) {
    return repository.findPage(pageKey).collectList();
}
```

Đây là snippet minh họa, không phải file độc lập. Spring vẫn cần một provider phù hợp với reactive cache. Lựa chọn kiểu `Mono<List<T>>` không tự làm kết quả nhỏ hơn; bạn vẫn phải **giới hạn dữ liệu nguồn**. Nhưng semantics API rõ ràng hơn cho người dùng: một snapshot được xử lý như một khối.

## 6. Cơ chế hoàn thành, lỗi, hủy và cache rỗng

### 6.1. `onComplete` đánh dấu kết quả thành công

Một Flux hữu hạn phát `A`, `B`, `C` rồi `onComplete` có một kết quả cacheable hoàn chỉnh là `[A,B,C]`. Khi cache hit, các phần tử này được phát lại theo thứ tự ban đầu cho subscriber.

Nếu Flux kết thúc với **0 phần tử**, kết quả tập hợp về mặt ngữ nghĩa là danh sách rỗng. Với cache backend hỗ trợ caching reactive results, danh sách rỗng có thể được lưu như một giá trị hoàn tất hợp lệ. Đừng nhầm điều này với việc method trả về `null` hoặc cache không tìm thấy key.

### 6.2. `onError` không tạo một danh sách thành công

```java
Flux<String> broken = Flux.concat(
        Flux.just("A", "B"),
        Flux.error(new IllegalStateException("upstream failed")));
```

Đây là ví dụ Reactor. Luồng phát A, B rồi error, không phát `onComplete`. Không được coi `[A,B]` là snapshot thành công hoàn chỉnh để cache theo cơ chế collect-then-store. Việc retry sau đó có thể subscribe lại nguồn và gây side effects/costs; cần thiết kế retry, idempotency và error handling riêng.

**Không khẳng định mọi loại error được Spring Cache lưu như một item bình thường.** Nếu nghiệp vụ muốn negative caching hoặc cached failure policy, phải thiết kế rõ kiểu dữ liệu biểu diễn trạng thái lỗi và điều kiện chỉ cache những kết quả an toàn.

### 6.3. `Flux.never()` và dữ liệu vô hạn

```java
Flux<Long> numbers = Flux.interval(Duration.ofMillis(100));
```

Đoạn này tạo một luồng **không có điểm kết thúc**. Nếu áp `@Cacheable` và tầng cache thu gom toàn bộ Flux để tạo `List`, sẽ không có `onComplete` để hoàn tất danh sách. Buffer có thể tăng cho đến khi bị hủy, hết tài nguyên hoặc gặp lỗi.

Nếu thực sự cần lấy một snapshot hữu hạn, **cắt ngay trong method được cache**:

```java
@Cacheable(cacheNames = "sample", key = "#p0")
public Flux<Long> sample(String group) {
    return Flux.interval(Duration.ofMillis(100)).take(10);
}
```

Đây là snippet minh họa; `take(10)` khiến Flux kết thúc sau 10 item. Với dữ liệu thực, tốt hơn giới hạn query/loader từ nguồn và đặt timeout có cơ chế cleanup, thay vì tải vô hạn rồi chỉ cắt ở downstream controller.

### 6.4. Cancel từ client và tài nguyên nguồn

Trong reactive systems, client có thể hủy subscription. Tính chất materialize/caching không tạo cam kết rằng giá trị đã được cache đầy đủ khi chỉ một phần kết quả được phát hoặc khi publisher bị cancel. Hành vi subscription sharing/cancellation có thể phụ thuộc đường adapter/provider.

**Đừng dựa vào một cache hit cho Flux chưa hoàn tất.** Kiểm tra chắc chắn cache chỉ chứa snapshot hoàn chỉnh, đặc biệt khi dùng custom Cache implementation hoặc có retry/resubscribe phức tạp.

### 6.5. `null` không phải một phần tử của Flux

Reactive Streams không cho phép `onNext(null)`. `Flux.just(null)` sẽ lỗi, không có “list chứa null” theo cách phát phần tử bình thường. Đây là khác biệt so với cache dữ liệu đồng bộ có thể có null policy hoặc sentinel. Nếu dữ liệu nghiệp vụ có optional item, biểu diễn bằng domain type rõ ràng thay vì phát null.

## 7. Demo Java 17+ chạy được: cache một Flux hữu hạn với Caffeine async

Ví dụ độc lập dùng **Java 17+**, **Maven**, **Spring Framework 6.2.12**, **Reactor Core 3.7.12** và **Caffeine 3.2.2**. Không cần Spring Boot, Redis hoặc database.

Mục đích là chứng minh, theo **lời gọi tuần tự, hoàn tất đầy đủ**:

1. Lần đầu với key `P42`: method phát ba phần tử; nguồn thực sự được subscribe một lần.
2. Lần hai cùng key `P42`: kết quả được lấy từ cache, vẫn phát đủ ba phần tử, không subscribe lại nguồn.
3. Key `P99` khác: tạo snapshot riêng và subscribe nguồn lần thứ hai.
4. Xóa `P42` một cách tường minh; lời gọi tiếp theo phải lấy snapshot mới.
5. Dữ liệu được cache như **kết quả tổng thể theo key**, không phải mỗi item một key.

### 7.1. Cấu trúc

```text
spring-reactive-flux-cache/
├── pom.xml
└── src/main/java/dev/example/fluxcache/FluxCacheDemo.java
```

### 7.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>spring-reactive-flux-cache</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.7.12</version>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
            <version>3.2.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>dev.example.fluxcache.FluxCacheDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context-support` cung cấp `CaffeineCacheManager` và kéo theo Spring Context/Cache core tương ứng. `reactor-core` cung cấp `Flux`. Trong dự án Boot, hãy dùng dependency management/BOM tương thích của Boot thay vì tùy tiện khóa từng version.

### 7.3. Java source hoàn chỉnh

**`src/main/java/dev/example/fluxcache/FluxCacheDemo.java`**

```java
package dev.example.fluxcache;

import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;

public class FluxCacheDemo {

    private static List<String> await(Flux<String> values) {
        return Objects.requireNonNull(
                values.collectList().block(Duration.ofSeconds(5)));
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            FeedService service = context.getBean(FeedService.class);
            CacheManager manager = context.getBean(CacheManager.class);
            Cache cache = Objects.requireNonNull(manager.getCache("feeds"));

            System.out.println("first=" + await(service.find("P42")));
            System.out.println("second=" + await(service.find("P42")));
            System.out.println("loadsAfterHit=" + service.loadCount());

            System.out.println("another=" + await(service.find("P99")));
            System.out.println("loadsAfterNewKey=" + service.loadCount());

            // Tương ứng invalidate một snapshot, không xóa các key khác.
            cache.evictIfPresent("P42");
            System.out.println("afterEvict=" + await(service.find("P42")));
            System.out.println("loadsAfterEvict=" + service.loadCount());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class AppConfig {

        @Bean
        public CacheManager cacheManager() {
            CaffeineCacheManager manager =
                    new CaffeineCacheManager("feeds");

            // Dùng đường cache async cho kết quả reactive.
            manager.setAsyncCacheMode(true);
            manager.setCaffeine(Caffeine.newBuilder()
                    .maximumSize(100));

            return manager;
        }

        @Bean
        public FeedService feedService() {
            return new FeedService();
        }
    }

    public static class FeedService {
        private final AtomicInteger sourceSubscriptions =
                new AtomicInteger();

        @Cacheable(cacheNames = "feeds", key = "#p0")
        public Flux<String> find(String id) {
            return Flux.defer(() -> {
                // Chỉ tăng khi thực sự subscribe nguồn.
                int load = sourceSubscriptions.incrementAndGet();

                return Flux.just(
                        id + "-A-" + load,
                        id + "-B-" + load,
                        id + "-C-" + load
                );
            });
        }

        public int loadCount() {
            return sourceSubscriptions.get();
        }
    }
}
```

Lệnh chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**Stdout dự kiến từ các lệnh `System.out.println` của ứng dụng** trên context/cache mới (không tính log phụ Maven hoặc SLF4J):

```text
first=[P42-A-1, P42-B-1, P42-C-1]
second=[P42-A-1, P42-B-1, P42-C-1]
loadsAfterHit=1
another=[P99-A-2, P99-B-2, P99-C-2]
loadsAfterNewKey=2
afterEvict=[P42-A-3, P42-B-3, P42-C-3]
loadsAfterEvict=3
```

Đây là chương trình minh họa **lời gọi tuần tự** với cache đã hoàn tất snapshot trước lời gọi tiếp theo, không phải stress test đồng thời hoặc bằng chứng cross-node. Với provider khác, yêu cầu async cache phải được kiểm chứng riêng.

### 7.4. Phân tích output

- `first`: key `P42` chưa có snapshot, source `Flux.defer` được subscribe lần đầu và phát A/B/C gắn số `1`. Tầng cache lưu kết quả hoàn tất tương ứng một danh sách có ba item.
- `second`: cùng key được phục vụ từ snapshot đã cache, nên output không tăng số lên `2`; `loadsAfterHit=1` xác nhận nguồn không được subscribe lần nữa.
- `another`: key `P99` khác `P42` nên có một lần lấy dữ liệu mới, đưa load count lên `2`.
- `cache.evictIfPresent("P42")`: yêu cầu loại entry P42. Không xóa P99.
- `afterEvict`: P42 bị miss trở lại, nguồn phát A/B/C với số load `3`, rồi tạo snapshot mới.

**Vì sao đếm subscription thay vì đếm method entry?** Trong Reactive Java, method có thể chỉ tạo một publisher lạnh (`Flux.defer`) còn tác vụ thực chạy khi subscription xảy ra. Đếm trong defer thể hiện số lần công việc nguồn thật được kích hoạt. Với các publisher khác, subscription và method invocation có thể không trùng nhau.

### 7.5. Tại sao ví dụ sử dụng `block`?

`block(Duration)` chỉ dùng ở **hàm main demo / kiểm thử**, nhằm chờ kết quả hoàn tất để in stdout xác định. **Không copy `block()` vào event-loop request handler WebFlux trong production**: chặn thread reactive làm giảm throughput hoặc phát sinh lỗi trong ngữ cảnh nonblocking.

Trong WebFlux controller thật, nên trả `Flux`/`Mono` cho runtime quản lý subscription, và dùng `StepVerifier` hay integration tests để kiểm tra behavior.

### 7.6. Tại sao cache dùng `setAsyncCacheMode(true)`?

Spring Framework hỗ trợ cache reactive từ 6.1 và cần backend tương thích với asynchronous caching. Caffeine async mode là cấu hình rõ ràng cho tình huống này. Không nên chỉ tạo Caffeine native cache sync rồi giả định mọi đường reactive caching sẽ dùng lại future/list đúng cách.

### 7.7. Vì sao method phải nằm trên Spring bean?

`@Cacheable` trong proxy mode cần lời gọi qua Spring-managed bean. Trong demo, `context.getBean(FeedService.class)` là điểm lấy bean đã được intercept. Nếu code tạo `new FeedService()` ngoài container hoặc self-invocation kiểu `this.find("P42")` trong cùng instance, annotation có thể bị bỏ qua, làm kết quả demo khác.

## 8. Một số lỗi thiết kế với `Flux` được cache thành danh sách

### 8.1. Cache một luồng vô hạn

Sai:

```java
@Cacheable(cacheNames = "notifications", key = "#p0")
public Flux<Notification> liveNotifications(String userId) {
    return notificationBroker.liveStream(userId);
}
```

Đây là **snippet anti-pattern**. Luồng live thường không phát `onComplete`; việc thu toàn bộ Flux không thể hoàn tất danh sách. Cần cơ chế streaming thực sự, replay buffer hữu hạn hoặc một tầng state/snapshot khác; **không dùng cache toàn kết quả để giữ một live stream**.

### 8.2. Cache kết quả export hàng triệu records

Sai về kiến trúc nếu mục tiêu là streaming không tải hết dữ liệu vào RAM:

```java
@Cacheable(cacheNames = "exports", key = "#p0")
public Flux<RowDto> exportAll(String reportId) {
    return repository.streamAllRows(reportId);
}
```

Tầng cache sẽ tìm cách gom danh sách rất lớn trước khi cache. Thay bằng export streaming trực tiếp, phân trang có giới hạn, chunked object storage hoặc job tạo file. Nếu muốn cache metadata của file xuất, cache **một object nhỏ mô tả kết quả**, không nhất thiết cache toàn bộ row objects.

### 8.3. Không phân biệt query/page trong cache key

`@Cacheable(cacheNames="search", key="#query")` sai nếu method còn có `page`, `size`, `sort` nhưng key chỉ dựa vào query. Hai lời gọi cùng query với page khác nhau có thể cùng nhận **danh sách của page trước**.

Giải pháp: key phải bao gồm mọi tham số làm thay đổi danh sách và phạm vi người dùng. Với dữ liệu phụ thuộc quyền, tránh chỉ cache theo query mà bỏ qua tenant/principal.

### 8.4. Cache một object mutable

Danh sách đã cache hoặc các item bên trong có thể là object mutable. Khi subscriber sửa object, những subscriber sau có thể quan sát trạng thái đã bị sửa tùy provider/object reference semantics. Ưu tiên immutable DTO và mapping rõ ràng trước khi cache; không coi Spring Cache là deep-copy mechanism.

### 8.5. Không có TTL hoặc giới hạn kích thước

Nếu hàng triệu truy vấn có key khác nhau, dù mỗi Flux chỉ 50 items thì tổng cache có thể rất lớn. Phải cấu hình `maximumSize`/`maximumWeight`/TTL ở provider thích hợp; đồng thời giới hạn tối đa số items cho **một key**. Quota 100 cache keys không phải quota 100 items.

### 8.6. Mặc định nghĩ cache tự xử lý error/timeout

Khi nguồn thất bại, phải xử lý error path, cancellation, retry policy và fallback riêng. Nếu dùng `retryWhen` trên Flux nguồn, những phần tử đã được thu thập trước lỗi có thể được tính lại theo cách khác; cần xác định liệu retry có làm trùng/lặp items không. Không cache kết quả chưa hoàn tất làm snapshot chính thức.

## 9. Phân biệt Spring Cache Flux và Reactor `Flux.cache()`

Hai API có chữ “cache” nhưng mục đích không giống nhau.

### 9.1. Spring `@Cacheable`: cache theo business key

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Flux<Product> findProducts(String category) {
    return repository.findByCategory(category);
}
```

- Key tạo từ method arguments.
- Cache backend được chọn qua `CacheManager`/`CacheResolver`.
- Với adapter phù hợp, Flux hoàn tất được thu thành một danh sách và lưu như kết quả của key.
- TTL và capacity thuộc backend.
- Dùng được giữa nhiều lời gọi method với cùng key nếu cache còn entry.

### 9.2. Reactor `Flux.cache()`: replay tín hiệu trong một publisher

```java
Flux<String> shared = expensiveSource.cache();
```

- Operator `cache()` lưu/replay các tín hiệu đã phát (giá trị và terminal signal) của **publisher instance đó**.
- Không tự tạo cache key từ method arguments cho toàn ApplicationContext.
- Có overload để giới hạn lịch sử replay và/hoặc TTL cho tín hiệu, ví dụ `cache(int history, Duration ttl)`; cần chọn kích thước và thời gian phù hợp.
- Với một Flux sống lâu, cache không giới hạn có thể tiêu tốn nhiều memory.
- Thích hợp khi muốn chia sẻ một nguồn đã tạo và phát lại cho nhiều subscribers cùng tham chiếu publisher đó, không phải thay thế một distributed cache hay cache theo business key.

Ví dụ replay hữu hạn:

```java
Flux<String> source =
        Flux.just("A", "B", "C")
            .cache(3, Duration.ofMinutes(1));
```

Đây là snippet Reactor không phụ thuộc Spring Cache. Nó giữ lịch sử tối đa 3 phần tử trong phạm vi publisher này với TTL theo semantics của operator, nhưng không đồng nghĩa với việc lưu một `List` trong `CacheManager`.

### 9.3. Khi nên dùng cách nào?

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Cache toàn bộ trang kết quả theo filter/page với TTL | `@Cacheable` trên kết quả hữu hạn, provider async thích hợp |
| Replay những tín hiệu của cùng publisher cho nhiều subscriber | Reactor `Flux.cache(...)` hoặc share/replay strategy |
| WebSocket/SSE live stream không hoàn tất | Reactive streaming với bounded replay/backpressure policy |
| Export dữ liệu cực lớn | Stream trực tiếp hoặc chunked export, không materialize một List lớn |
| Cache một file báo cáo đã tạo xong | Cache metadata hoặc đường dẫn object storage |
| Cần shared cache giữa nhiều node | Provider phân tán và protocol/versioning rõ ràng |
| Dữ liệu cực kỳ nhạy cảm về tươi mới | Kiểm soát invalidation/version và thận trọng với snapshot caching |

**Đừng chỉ dựa vào tên operator.** Spring `@Cacheable` giải quyết **business key / backend**, Reactor `cache()` giải quyết **replay publisher signals** ở tầng reactive pipeline.

## 10. `@Cacheable(sync=true)` có giải quyết mọi request Flux đồng thời không?

`sync=true` yêu cầu cache provider phối hợp load cùng key khi miss, nhằm giảm duplicate computation. Trong hệ thống hỗ trợ async retrieval, có thể dùng nó theo giới hạn của Spring:

```java
@Cacheable(cacheNames = "productPages", key = "#p0", sync = true)
public Flux<Product> page(String pageKey) {
    return repository.findPage(pageKey);
}
```

Đây là snippet, cần repository/domain thật. Spring `@Cacheable(sync=true)` có các giới hạn đã được Javadoc nêu:

- Không hỗ trợ thuộc tính `unless` để veto kết quả sau khi load.
- Chỉ được dùng **một Cache** cho operation.
- Không kết hợp với các cache operation khác trên cùng method.

**Không suy rằng `sync=true` luôn tạo khóa phân tán giữa nhiều JVM.** Nếu mỗi pod giữ Caffeine local riêng, mỗi pod vẫn có thể có một load cho cùng key. Nếu cache backend không hỗ trợ async atomic retrieval như kỳ vọng, cần test thực tế.

Với cache Flux, ngay cả khi chỉ chạy một loader cho mỗi key, những request đang chờ kết quả **vẫn phải chờ nguồn phát hết và hoàn tất danh sách**. Do đó `sync=true` có thể giảm DB QPS nhưng không tự cải thiện time-to-first-item.

## 11. Kết hợp với `@CacheEvict`, cập nhật dữ liệu và transaction

### 11.1. Snapshot list có thể stale

Giả sử cache đang giữ danh sách đơn hàng của customer `C42`. Một đơn hàng mới được tạo trong database, nhưng danh sách cũ vẫn trong cache. Không có cơ chế tự cập nhật phần tử thứ 11 vào list chỉ vì DB thay đổi. Cần TTL, eviction theo key hoặc version.

Ví dụ:

```java
@Cacheable(
    cacheNames = "ordersByCustomer",
    key = "#p0"
)
public Flux<OrderDto> findOrders(String customerId) {
    return repository.findByCustomerId(customerId);
}

@CacheEvict(
    cacheNames = "ordersByCustomer",
    key = "#p0"
)
public Mono<Void> refreshOrders(String customerId) {
    return repository.recompute(customerId);
}
```

Đây là **đoạn minh họa**, không phải lời bảo đảm rằng `@CacheEvict` sẽ đợi toàn bộ một `Mono<Void>` hoàn tất trong mọi đường xử lý: cần kiểm tra phiên bản Spring/cache annotation adapter và semantics của method phản ứng thực. Với thao tác cập nhật DB phản ứng, invalidation tốt nhất phải được gắn với **tín hiệu transaction commit thành công** và test end-to-end.

### 11.2. Thời điểm xóa không tự đồng bộ với DB

Nếu xóa entry trước transaction commit, reader khác có thể miss rồi nạp lại **danh sách cũ**, sau đó cache giữ snapshot cũ ngay cả khi transaction đã commit. Điều này tương tự các vấn đề với cache dữ liệu đồng bộ, nhưng ở đây việc nạp snapshot có thể kéo dài tới lúc Flux hoàn tất.

Cách tiếp cận tùy yêu cầu:

- Xóa cache **sau commit thành công**, hoặc publish event invalidation từ outbox.
- Dùng key có version/generation để tránh late loader đặt snapshot cũ vào key mới.
- Kiểm tra đúng cache key/namespace theo tenant/customer/filter.
- Đặt TTL không quá dài nếu dữ liệu thay đổi liên tục.
- Test 2 request đọc/ghi cạnh tranh vào cùng key với nguồn dữ liệu thật.

### 11.3. Synchronous transaction manager không giống reactive transaction manager

Trong ứng dụng Reactor/R2DBC, transaction context thường gắn với **Reactor context**, không phải chỉ ThreadLocal như transaction JDBC truyền thống. Không được mặc định rằng `TransactionAwareCacheManagerProxy` sẽ tự hoãn mọi cache put khi transaction R2DBC reactive hoàn tất. Cần đối chiếu transaction manager, cache adapter và event/transaction synchronization phù hợp cho reactive stack, rồi test commit/rollback.

## 12. Thiết kế key và giới hạn kết quả cho một Flux có thể cache

Một bài toán thường gặp là trang tìm kiếm có nhiều tham số:

```java
public record SearchKey(
        String tenantId,
        String query,
        int page,
        int size,
        String sort
) { }
```

Một method có thể dùng chính object immutable này làm key:

```java
@Cacheable(cacheNames = "searchPages", key = "#p0")
public Flux<ProductDto> search(SearchKey criteria) {
    return repository.findPage(
            criteria.tenantId(),
            criteria.query(),
            criteria.page(),
            Math.min(criteria.size(), 50),
            criteria.sort());
}
```

Hai snippet ở đây cần `ProductDto`/repository thật. Record trong Java 17 cung cấp `equals/hashCode` theo giá trị thành phần, phù hợp với cache key local khi dữ liệu immutable. Với Redis/shared cache, cần xem serializer/key conversion; không tự cho rằng object record sẽ encode giống nhau giữa deployments.

**Validation bắt buộc:**

- `tenantId` không null/trống và đến từ authentication context đáng tin.
- `page >= 0`, `1 <= size <= 50` sau khi chuẩn hóa.
- `sort` thuộc whitelist, không nhét raw SQL.
- Query được chuẩn hóa theo yêu cầu nghiệp vụ.
- Cache key dùng **giá trị đã canonicalize**; đừng cache `size=9999` vào key khác dù method cắt xuống 50.
- Dữ liệu nguồn trả về thực sự có giới hạn, ví dụ SQL `LIMIT 50`, không phải lấy hàng triệu record về rồi mới `take(50)` một cách tốn kém.
- Khi query filter có tính user-scoped, key/namespace không được trộn kết quả các quyền khác nhau.

### 12.1. Danh sách không cần bị serialize trong local cache

Local Caffeine thường giữ reference tới object/list trong JVM, còn Redis sẽ cần representation serialized. Sự khác biệt này ảnh hưởng memory, network, schema evolution và rủi ro mutable object. Khi cache danh sách DTO qua Redis, cần:

- Serializer rõ ràng, versioning DTO hoặc schema.
- TTL/expiration hợp lý.
- Giới hạn tổng bytes cho một entry, không chỉ số key.
- Giải pháp khi cached list vượt giới hạn mạng/storage.
- Khả năng invalidate khi deployment thay đổi representation.

## 13. Monitoring: phải đo cả cache hit và chi phí materialize list

Một cache Flux hoàn tất có thể tăng hit rate nhưng làm thời gian lần miss rất cao. Theo dõi:

| Nhóm | Chỉ số / quan sát | Lý do |
|---|---|---|
| Cache | Hit/miss ratio, eviction, cache key count | Đánh giá hiệu quả backend và key cardinality |
| Flux source | Số subscriptions nguồn theo key/nhóm key | Xác nhận cache hit có tránh đọc upstream |
| Materialization | Số item/list, kích thước serialized, max payload bytes | Tránh list quá lớn |
| Latency | Thời gian tới phần tử đầu, thời gian hoàn tất, P95/P99 | Phát hiện mất streaming do collect |
| Memory | Heap used, allocation rate, GC pause, OOM | Đo chi phí giữ danh sách và các buffer |
| Downstream | DB QPS, R2DBC connections, API fanout | Kiểm tra giảm tải nguồn thật |
| Cancellation | Số subscriptions bị hủy, timeout, error | Phát hiện list không bao giờ hoàn thành |
| Consistency | Cache age, invalidation lag, stale hits | Phát hiện snapshot cũ sau update |
| Distributed | Loader count trên các pod, Redis latency | Phân biệt local async cache và cluster-wide coordination |

### 13.1. Đừng chỉ đo số lần gọi method

`Flux.defer` hoặc repository reactive có thể chỉ thực hiện IO khi có subscriber. Một counter tại **đầu method** có thể tăng vì method được tạo publisher, nhưng không tương đương số lần DB query. Đếm tại source subscription/actual DB calls, hoặc dùng metrics ở database.

### 13.2. Test end-to-end cho finite Flux

Bộ test tối thiểu:

1. Cùng key, lần đầu miss: source subscription một lần, nhận danh sách đúng thứ tự.
2. Cùng key, lần sau hit: không subscribe nguồn mới; nhận cùng snapshot.
3. Key khác: tạo snapshot độc lập.
4. Evict key A: A miss, B không bị xóa.
5. `Flux.empty()`: kiểm tra xử lý danh sách rỗng theo provider.
6. `Flux.error(...)`: kiểm tra không trả snapshot thành công thiếu phần tử.
7. Source vô hạn hoặc lâu: timeout/memory guard và cancellation.
8. Result có hàng chục nghìn items: đo heap, response latency và backpressure.
9. Concurrent same-key miss: đo nguồn được subscribe bao nhiêu lần dưới provider thật.
10. Hai pod, cache local/shared: không nhầm local single-flight là distributed.
11. Update trong transaction: thử invalidation sau commit và late reader refill stale.
12. Dùng WebFlux endpoint thật: test time-to-first-byte/time-to-first-item, không chỉ tổng thời gian.
13. Tên cache, SpEL key và tenant scope: không phát lại danh sách của người khác.
14. Không dùng `block()` trong reactive request path production.

## 14. Các lỗi phổ biến khi cache `Flux`

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Bật `@Cacheable` rồi streaming trở nên chậm | Toàn Flux bị gom thành List trước khi phát lại | Chỉ cache dữ liệu hữu hạn nhỏ; dùng streaming thuần cho export/live |
| Flux vô hạn không có cache hit hoàn chỉnh | Không có `onComplete` | Không cache toàn bộ live stream; giới hạn snapshot hoặc dùng bounded replay |
| JVM tăng memory mạnh | Danh sách lớn bị buffer/lưu | Giới hạn query/page size, TTL, capacity, entry bytes |
| Cache hit nhưng dữ liệu stale | Snapshot list không tự cập nhật khi DB thay đổi | Evict/version đúng key sau commit |
| Cùng một Flux được phát cho tenant khác | Cache key không có tenant/authorization scope | Sửa cache key và data isolation |
| Có `@Cacheable` nhưng source vẫn bị subscribe mỗi lần | Cache adapter không phù hợp, method không đi qua proxy, key khác hoặc cache entry không được giữ | Kiểm tra `@EnableCaching`, Spring bean, async mode và storage |
| Provider báo unsupported async retrieval | `Cache.retrieve`/future path chưa được hỗ trợ | Dùng adapter hỗ trợ, ví dụ Caffeine async |
| Có `sync=true` nhưng DB vẫn nạp trùng giữa pod | Local cache instance độc lập, hoặc provider không có distributed coordination | Test cross-node, chọn distributed single-flight khi cần |
| Flux trả lỗi giữa chừng, lần sau tải lại | Kết quả không có `onComplete` thành công | Xử lý lỗi có chủ đích, tránh lưu partial snapshot |
| Đọc từ cache nhưng thứ tự khác dự kiến | Nguồn data/order không deterministic, adapter hoặc serialization | Đảm bảo ORDER BY và danh sách snapshot xác định |
| Client hủy request nhưng nguồn còn tốn tài nguyên | Subscription/cancellation dưới adapter không đúng kỳ vọng | Test cancellation và cleanup trên provider thật |
| Caffeine `maximumSize(100)` mà heap vẫn cao | Mỗi entry là List nhiều item | Đặt max items per entry hoặc weighted/byte budget |
| Tính toán `unless` với Flux không như tưởng | Kết quả tương lai cần được thích nghi, semantics SpEL/provider khác đồng bộ | Kiểm tra Javadoc, viết test cho result-based veto |
| Method trả Flux nhưng vẫn dùng JDBC blocking | Reactive return type không làm blocking IO thành nonblocking | Chuyển source phù hợp hoặc isolate scheduler đúng cách |
| Cache một bản ghi đơn lẻ dưới cả Flux và Mono | Semantics snapshot, null/empty và key không thống nhất | Chọn một hợp đồng return type phù hợp nghiệp vụ |

## 15. Checklist quyết định có cache một Flux hay không

1. **Flux có hữu hạn không?** Nếu không có điểm kết thúc, không dùng cache toàn danh sách.
2. **Có giới hạn tối đa số phần tử không?** Giới hạn tại query/source, không chỉ ở client.
3. **Client có cần streaming sớm không?** Nếu cần từng record tức thì, cache danh sách toàn bộ có thể sai kiến trúc.
4. **Có thể chấp nhận list snapshot stale trong TTL không?** Nếu không, phải thiết kế invalidation/version.
5. **Cache key có đủ tham số tenant/permission/filter/page/sort không?**
6. **Provider có async retrieval tương thích không?** Caffeine async hoặc adapter phù hợp đã được kiểm thử?
7. **Cấu hình Spring là 6.1+ và reactive cache adaptation có bật theo mặc định không?** Kiểm tra version, flags và cấu hình.
8. **Nếu có `@EnableCaching`, lời gọi có đi qua Spring-managed bean proxy không?** Tránh self-invocation.
9. **Cache entry size có thể quá lớn không?** Quota key count không thay max size của một List.
10. **Nguồn có thể phát error, empty hoặc cancel không?** Mỗi trường hợp được test chưa?
11. **Đã đo subscriptions nguồn và DB queries, không chỉ count method?**
12. **Đã test đa node, concurrent miss và hot-key expiry chưa?**
13. **Có dùng `block()` sai chỗ trên reactive event loop không?** Chỉ block ở demo/test hoặc ranh giới phù hợp.
14. **Spring Cache có thực sự là công cụ cần dùng?** Nếu mục tiêu là replay một publisher hiện có, cân nhắc Reactor `Flux.cache(...)`; nếu là streaming dài, không cố materialize.
15. **Có dashboard cho TTL, payload size, latency P99, GC và stale snapshot không?**

### Tổng kết

Với hỗ trợ caching reactive của **Spring Framework 6.1+**, một method `@Cacheable` trả `Flux<T>` được thích nghi bằng cách **gom toàn bộ các phần tử thành một `List<T>` khi Flux hoàn tất**, rồi lưu danh sách đó dưới **một cache key**. Khi hit, danh sách được phát lại dưới dạng Flux. Cách này phù hợp với **kết quả hữu hạn, nhỏ, có key rõ ràng**, ví dụ một trang tìm kiếm, nhưng có thể làm mất lợi ích streaming của dữ liệu lớn hoặc luồng vô hạn.

Muốn áp dụng an toàn, cần một cache backend hỗ trợ bất đồng bộ, giới hạn số phần tử/bytes cho mỗi snapshot, cấu hình capacity/TTL, thiết kế key/invalidation đúng và kiểm thử subscription, latency, memory, concurrency. **Không nhầm `Flux` trả về trên API với bảo đảm hệ thống vẫn truyền trực tiếp từng phần tử không cần gom danh sách.**

### Tài liệu tham khảo

- Spring Framework — Declarative annotation-based caching, mục reactive/`CompletableFuture` return types: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework 6.2 — `Cacheable` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework 6.2 — `Cache.retrieve` và asynchronous access: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework 6.2 — `CaffeineCacheManager.setAsyncCacheMode`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Project Reactor — Reactor reference guide, Flux/Mono, backpressure, `collectList` và `cache`: https://projectreactor.io/docs/core/release/reference/
- Caffeine — Population/AsyncCache: https://github.com/ben-manes/caffeine/wiki/Population
