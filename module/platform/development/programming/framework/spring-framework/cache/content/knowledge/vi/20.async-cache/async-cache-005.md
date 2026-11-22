# Giới hạn với luồng vô hạn hoặc lượng kết quả lớn trong Spring Cache bất đồng bộ

## 1. Bài toán cần giải quyết

Cache giúp bỏ qua các truy vấn/tính toán lặp, nhưng **không phải mọi dữ liệu bất đồng bộ đều phù hợp để lưu trọn vào một cache entry**. Một `CompletableFuture<T>` thường có một kết quả sau khi hoàn tất; `Mono<T>` phát tối đa một phần tử; còn `Flux<T>` có thể phát 0, vài phần tử, hàng triệu phần tử hoặc tiếp tục vô hạn.

Khi cố cache toàn bộ `Flux` bằng việc thu gom các phần tử thành danh sách, có hai trường hợp nguy hiểm:

- **Luồng vô hạn:** không có tín hiệu hoàn tất bình thường (`onComplete`). Không có thời điểm một danh sách “tất cả kết quả” được hoàn thiện. Nếu cứ tích lũy phần tử, bộ nhớ có thể tăng không giới hạn cho tới khi hủy, lỗi hoặc cạn tài nguyên.
- **Luồng hữu hạn nhưng rất lớn:** cuối cùng có thể hoàn tất, nhưng list, cache entry, bản sao serialize và response có thể chiếm quá nhiều heap/RAM, tăng thời gian GC, CPU và mạng.

**Nguyên tắc:** chỉ cache **kết quả có phạm vi, chi phí và vòng đời xác định**. Với sự kiện liên tục, dùng streaming, retention hoặc snapshot có giới hạn; với danh sách lớn, dùng phân trang, projection hay aggregate.

Phạm vi bài: Spring Framework 6.1+ hỗ trợ thích ứng kết quả cache của `CompletableFuture` và các kiểu reactive được nhận biết như Reactor `Mono`/`Flux`. Phiên bản Spring, cache provider và cách cấu hình có thể ảnh hưởng khả năng async caching thực tế; không suy rộng hành vi cho mọi phiên bản.

## 2. Bất đồng bộ khác với dữ liệu vô hạn

“Bất đồng bộ” mô tả **khi nào** có kết quả, không mô tả **bao nhiêu** dữ liệu được tạo ra.

| Kiểu / nguồn | Số phần tử | Mức phù hợp để cache nguyên vẹn |
|---|---|---|
| `CompletableFuture<Product>` | Một kết quả khi future hoàn tất | Thường hợp lý nếu value vừa phải |
| `Mono<Product>` | Tối đa một phần tử | Thường hợp lý khi value không quá lớn |
| `Mono<List<Product>>` | Một emission, nhưng list có thể cực lớn | Phải giới hạn list |
| `Flux<Product>` từ query `LIMIT 20` | Hữu hạn, tối đa 20 | Có thể phù hợp nếu kết quả ổn định |
| `Flux<Product>` trả hàng triệu record | Hữu hạn nhưng rất lớn | Rủi ro bộ nhớ/serialization |
| `Flux.interval(...)` không giới hạn | Vô hạn tới khi cancel | Không cache toàn bộ |
| SSE, WebSocket, CDC, log tail | Thường chạy lâu/vô hạn | Dùng streaming/state store riêng |

Một `Mono<List<T>>` không “nhẹ” chỉ vì chỉ có một emission; object phát ra vẫn có thể rất lớn. Một `Flux<T>` không nhất thiết vô hạn; phải xét **nguồn dữ liệu và điều kiện hoàn tất**.

## 3. Spring 6.1+ xử lý các return type reactive thế nào?

Spring Cache có thể nhận biết asynchronous/reactive return type, thích ứng cache với kết quả được phát ra thay vì chỉ lưu object future/publisher.

Mô hình khái niệm:

~~~text
@Cacheable method trả Mono<T>
   → Mono hoàn tất với giá trị T
   → cache giá trị T nếu provider hỗ trợ

@Cacheable method trả Flux<T>
   → Flux phát T1, T2, ... Tn rồi onComplete
   → kết quả được gom thành List<T>
   → cache List<T>
   → cache hit có thể được thích ứng trở lại thành Flux<T>
~~~

Với `Flux`, **kết quả cần hoàn tất để có danh sách đầy đủ**. Đây là lý do một luồng không kết thúc hoặc danh sách khổng lồ đều không thích hợp cho cơ chế cache cả chuỗi.

Đừng suy luận rằng mọi CacheManager đều hỗ trợ retrieval bất đồng bộ theo cùng một cách, hoặc toàn bộ luồng được phát tới client từng phần trong khi cơ chế cache đang gom list. Phải kiểm thử sự kết hợp **Spring version + CacheManager + Cache provider + return type** thực tế.

Không nên nhầm “cache một chuỗi snapshot hữu hạn” với “giữ kết nối realtime cho subscriber”: hai mục tiêu đó khác nhau.

## 4. Anti-pattern: cache một Flux không có điểm dừng

Ví dụ Reactor:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));

// KHÔNG cố chờ lấy toàn bộ:
// Mono<List<Long>> allTicks = ticks.collectList();
~~~

`Flux.interval` tiếp tục phát phần tử theo thời gian và không tự phát `onComplete`. `collectList()` chỉ có thể tạo danh sách hoàn chỉnh khi nguồn kết thúc bình thường; một nguồn không kết thúc sẽ không tạo kết quả đầy đủ.

Ví dụ **không nên gắn annotation**:

~~~java
// PHẢN VÍ DỤ: đây là nguồn realtime vô hạn.
@Cacheable(cacheNames = "liveTicks")
public Flux<Long> liveTicks() {
    return Flux.interval(Duration.ofSeconds(1));
}
~~~

Đây là mã minh họa tích hợp Spring + Reactor, cần imports và dependency phù hợp. Nếu một adapter cần thu toàn bộ Flux thành List để cache, nó sẽ không có danh sách hoàn chỉnh; việc tích lũy dữ liệu không giới hạn có thể làm tăng bộ nhớ. Cancellation, timeout và lỗi từ publisher/provider cần được xử lý theo pipeline thật.

Các nguồn tương tự: thông báo SSE, giá chứng khoán realtime, telemetry, message bus subscription, CDC, tail log, WebSocket stream.

### Timeout có biến stream vô hạn thành kết quả cache được không?

Không mặc nhiên. `timeout` thường làm pipeline báo lỗi khi vượt điều kiện thời gian, thay vì tạo một danh sách hoàn chỉnh đáng tin. `take(Duration)` có thể khiến luồng kết thúc sau một khoảng thời gian, nhưng **không giới hạn tổng số phần tử hoặc byte** nếu nguồn phát rất nhanh. Muốn cache snapshot an toàn, nên có **giới hạn số phần tử, kích thước và thời gian**.

## 5. Flux hữu hạn nhưng quá lớn vẫn tạo áp lực

~~~java
// Không nên cache cả catalog lớn theo cách này.
@Cacheable(cacheNames = "allProducts")
public Flux<Product> allProducts() {
    return repository.findAll();
}
~~~

Dù database có số record hữu hạn, danh sách gom được có thể cực lớn. Hệ quả:

- **Heap tăng:** object nguồn, list đang gom, cache entry và response có thể cùng sống.
- **GC pressure:** entry khổng lồ giữ nhiều object lâu, gây pause hoặc cấp phát nhiều.
- **Serialization:** provider từ xa phải mã hóa/giải mã và truyền dữ liệu lớn qua mạng.
- **Cache hit cũng chậm:** mỗi lần lấy một entry khổng lồ vẫn phải giải mã, copy và render.
- **Cache stampede:** nhiều request cùng miss/TTL expire có thể đồng thời tạo nhiều bản sao dữ liệu lớn.
- **Chi phí invalidation:** thay một record có thể cần xóa và tính lại cả danh sách.
- **Trùng key theo biến thể:** cùng dataset nhưng nhiều filter/sort/tenant có thể sinh nhiều entry lớn.

Độ lớn trong RAM không thể ước lượng chính xác chỉ bằng size JSON; còn overhead object, serializer, giá trị trung gian và số request đồng thời. Phải đo với profiler, metrics và representative load.

**`Mono<List<T>>` không giải quyết vấn đề kích thước**: list lớn vẫn phải tồn tại trong bộ nhớ. Mục tiêu là giảm lượng dữ liệu mỗi request/cache entry, không chỉ thay đổi kiểu publisher.

## 6. Giới hạn tại nguồn trước khi gom dữ liệu

Một cách viết:

~~~java
Flux<Product> limited = repository.findAll().take(50);
~~~

`take(50)` giới hạn tối đa 50 phần tử được phát xuống downstream rồi hoàn tất. Nhưng nếu repository đã quét/tải quá nhiều bản ghi trước khi phát được 50 phần tử, phần backend vẫn tốn tài nguyên.

Ưu tiên giới hạn **ngay tại DB hoặc API nguồn**. Ví dụ SQL:

~~~sql
SELECT id, name, price
FROM products
WHERE tenant_id = :tenantId
ORDER BY id
LIMIT :pageSize OFFSET :offset;
~~~

Các tham số phải được kiểm tra và bind an toàn. Để phân trang nhất quán, sort phải ổn định; xem index và execution plan. Với dataset biến động hoặc offset lớn, cursor/keyset pagination có thể phù hợp hơn.

Nên giới hạn đồng thời:
1. **Số phần tử**: page size tối đa rõ ràng.
2. **Số byte**: record có thể chứa field quá lớn.
3. **Thời gian**: query timeout, publisher timeout và cancellation.
4. **Tài nguyên**: concurrent requests, connection pool, cache quota.
5. **Thời hạn dữ liệu**: TTL/invalidation/version để tránh stale snapshot.

Một page quá lớn vẫn có thể cần giảm size hoặc chỉ lấy projection.

## 7. Mẫu Spring: cache một page hữu hạn

Giả sử có reactive repository tùy chỉnh `findPage` thực hiện source-side pagination:

~~~java
import java.util.List;
import reactor.core.publisher.Mono;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductPageService {
    private final ProductPageRepository repository;

    public ProductPageService(ProductPageRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productPages")
    public Mono<List<ProductDto>> findPage(
            String tenantId, int page, int size) {

        if (page < 0 || size < 1 || size > 100) {
            return Mono.error(
                    new IllegalArgumentException("Invalid page/size"));
        }

        // Repository PHẢI giới hạn truy vấn ngay tại nguồn.
        return repository.findPage(tenantId, page, size)
                .take(size)
                .map(ProductDto::from)
                .collectList();
    }
}
~~~

Đây là **mã tích hợp minh họa**; `ProductPageRepository`, `ProductDto` và `ProductDto.from` do ứng dụng cung cấp. Cần Spring Cache, Reactor, `@EnableCaching` và provider phù hợp với async/reactive caching.

Ưu điểm:
- Mỗi cache entry là **một page nhỏ**.
- `take(size)` là hàng rào thêm, **không thay thế** limit tại database.
- `Mono<List<ProductDto>>` biểu thị kết quả snapshot hữu hạn.
- Key mặc định cho phương thức có nhiều tham số gồm `tenantId`, `page` và `size`, giúp phân biệt những page khác nhau.

**Quan trọng về authorization:** validation và kiểm tra quyền nên chạy **trước cache interception** tại controller/facade. Nếu đặt toàn bộ kiểm tra trong method được cache, một cache hit có thể bỏ qua thân method và vô tình bỏ qua kiểm tra. Không tin `tenantId` từ client nếu chưa xác thực/ủy quyền; thiết kế key/namespace tránh lẫn dữ liệu giữa tenant.

Nếu kết quả phụ thuộc filter/sort/locale/version/quyền đọc hoặc ngày snapshot, chúng cũng phải được tính vào key hay policy phân vùng tương ứng. Key chỉ bằng `page` là không đủ.

## 8. Có thể cache trực tiếp một Flux hữu hạn không?

Có thể cân nhắc nếu biết chắc kết quả nhỏ và hoàn tất:

~~~java
@Cacheable(cacheNames = "recentEvents")
public Flux<EventDto> recentEvents(String tenantId, int limit) {
    if (limit < 1 || limit > 50) {
        return Flux.error(new IllegalArgumentException("Invalid limit"));
    }

    return eventRepository.findRecent(tenantId, limit)
            .take(limit)
            .map(EventDto::from);
}
~~~

Đây là mã Spring + Reactor minh họa, cần repository và DTO. Với Spring 6.1+ và provider tương thích, `Flux` được thích ứng thành danh sách kết quả để cache. Trường hợp này có giới hạn số phần tử, nên cache một snapshot có thể hợp lý.

Dù vậy, nếu API cam kết **stream từng phần tử ngay khi tới**, việc gom để cache có thể thay đổi độ trễ hoặc đặc tính tiêu thụ. Với API chủ yếu trả snapshot nhỏ, kiểu `Mono<List<EventDto>>` thể hiện ý định rõ hơn. Với SSE/live feed, **không cache toàn bộ**; tạo endpoint snapshot gần đây riêng.

## 9. Caching thay thế: page, summary, per-ID và snapshot

| Nhu cầu | Cách làm tốt hơn | Cache |
|---|---|---|
| Danh mục lớn | DB pagination hoặc cursor | Một page/projection nhỏ |
| Chỉ cần tổng số | Query aggregate | `count`/summary, không kéo mọi record |
| Chi tiết một bản ghi | Cache-aside theo ID | DTO nhỏ |
| Dashboard cập nhật định kỳ | Snapshot có version và TTL | Dữ liệu tổng hợp vừa phải |
| Sự kiện realtime | Streaming + retention riêng | Chỉ metadata hoặc recent snapshot |
| File/video lớn | Object storage/CDN/HTTP cache | URL/metadata/chunk theo giao thức truyền tải |
| Tìm kiếm dài | Page theo query/sort/filters | Các page thường dùng |

Ví dụ cache số lượng thay vì cache cả catalog:

~~~java
@Cacheable(cacheNames = "productCounts")
public Mono<Long> countByTenant(String tenantId) {
    return repository.countByTenant(tenantId);
}
~~~

Mã minh họa chỉ đúng khi `countByTenant` là query aggregate ở nguồn. Nếu bên trong vẫn `findAll().collectList().map(list -> (long)list.size())`, ứng dụng đã kéo toàn bộ dữ liệu vô ích.

### Windowing không tự chữa được outer stream vô hạn

`buffer(100)`/`window(100)` chia dữ liệu thành từng đợt; nhưng nếu annotation vẫn cố lưu **toàn bộ publisher bên ngoài** của một luồng vô hạn, nó vẫn không có điểm hoàn tất. Cần thiết kế **mỗi window/snapshot là một request hữu hạn**, retention và giới hạn dữ liệu có thể đo được.

## 10. Java 17 chạy độc lập: cache page hữu hạn

Chương trình sau **chỉ mô phỏng** cache bằng `ConcurrentHashMap` và `CompletableFuture`; không chạy Spring/Flux hay distributed cache. Nó minh họa chia key theo page/size và lấy hữu hạn từ một stream không có điểm dừng tự nhiên.

Tạo file **`BoundedAsyncCacheDemo.java`**:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

public class BoundedAsyncCacheDemo {
    private static final ConcurrentMap<String, CompletableFuture<List<Integer>>>
            CACHE = new ConcurrentHashMap<>();
    private static final AtomicInteger SOURCE_LOADS = new AtomicInteger();

    private static CompletableFuture<List<Integer>> getPage(
            int page, int size, Executor executor) {
        if (page < 0 || size < 1 || size > 5) {
            throw new IllegalArgumentException("Invalid page/size");
        }
        String key = page + ":" + size;
        return CACHE.computeIfAbsent(key, ignored ->
                CompletableFuture.supplyAsync(() -> {
                    SOURCE_LOADS.incrementAndGet();
                    int start = Math.addExact(Math.multiplyExact(page, size), 1);
                    return IntStream.iterate(start, n -> n + 1)
                            .limit(size)
                            .boxed()
                            .toList();
                }, executor));
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Integer> page0 = getPage(0, 3, pool).join();
            List<Integer> repeat = getPage(0, 3, pool).join();
            List<Integer> page1 = getPage(1, 3, pool).join();
            List<Integer> boundedInfinite = IntStream.iterate(1, n -> n + 1)
                    .limit(4).boxed().toList();

            System.out.printf("page0=%s, repeated=%s%n", page0, repeat);
            System.out.println("page1=" + page1);
            System.out.printf("sourceLoads=%d, cacheEntries=%d%n",
                    SOURCE_LOADS.get(), CACHE.size());
            System.out.println("boundedInfinite=" + boundedInfinite);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac --release 17 BoundedAsyncCacheDemo.java
java BoundedAsyncCacheDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
page0=[1, 2, 3], repeated=[1, 2, 3]
page1=[4, 5, 6]
sourceLoads=2, cacheEntries=2
boundedInfinite=[1, 2, 3, 4]
~~~

Diễn giải:
1. Page 0 và page 1 có key khác; mỗi page chỉ tải tối đa 3 phần tử.
2. Lặp lại page 0 dùng chung future trong map, nên tổng số source load là 2.
3. `IntStream.iterate` là stream không có điểm kết thúc tự nhiên, nhưng `limit(4)` khiến `toList()` hoàn thành.
4. Chương trình **không thực thi** việc gom một stream vô hạn không giới hạn, tránh chạy treo hoặc hết bộ nhớ.
5. `computeIfAbsent` chỉ phối hợp trong **một map/một JVM**. Không suy ra Spring provider có cùng cơ chế sync. Code này cache future như một object để minh họa, không mô phỏng chi tiết Spring 6.1 reactive adaptation.

Nếu future thất bại mà ứng dụng giữ nó trong map mãi, những request sau có thể liên tục nhận lỗi cũ. Thiết kế production cần eviction/retry, timeout và policy cho exceptional completion.

## 11. Xác thực, key và tính nhất quán giữa các page

Pipeline tốt:

~~~text
HTTP request
   |
   v
Auth + validate tenant/page/size/filter/sort
   |
   v
Facade gọi bean Spring qua proxy
   |
   v
@Cacheable page theo key gồm tenant,page,size,sort,version
   |
   +-- HIT: trả page nhỏ từ cache
   |
   +-- MISS: query DB có LIMIT → collectList → cache page
~~~

Với proxy mode, lời gọi nội bộ `this.cachedMethod()` có thể bỏ qua interceptor cache. Test phải gọi qua bean Spring-managed thích hợp.

Page khác nhau phải có key khác nhau. Ngoài tenant/page/size còn có thể cần sort, filter, locale và version. Cache không thay thế authorization.

### Pagination không tự tạo snapshot nhất quán

Nếu dữ liệu bị insert/delete giữa các lần đọc, offset pagination có thể lặp hoặc bỏ sót record. Khi cần snapshot nhất quán, sử dụng sort ổn định, cursor/keyset, version/generation hoặc một token snapshot. TTL/invalidation phải phù hợp với tốc độ thay đổi và nhu cầu freshness.

## 12. Provider bất đồng bộ, TTL, cancellation và stampede

Một số câu hỏi phải xác minh trong môi trường thật:

- Cache có hỗ trợ cách retrieve bất đồng bộ/adapter mà Spring version đang dùng yêu cầu không?
- Tác vụ `CompletableFuture` hoàn thành bất thường hoặc bị cancel thì cache có để lại entry hay không?
- `@Cacheable(sync=true)` có phối hợp các request cùng key trong phạm vi nào, một JVM hay phân tán?
- TTL của page là bao lâu? Ai evict khi nguồn thay đổi?
- Nếu nhiều request cùng miss sau TTL, có tạo đồng thời nhiều list lớn không?
- Cache có giới hạn entry size, tổng dung lượng và metrics theo cache name/key không?

**Timeout không thay thế element/byte limit.** Một nguồn rất nhanh vẫn có thể phát số lượng lớn trước timeout. Nếu subscriber cancel trước khi `Flux` hoàn tất, không nên mặc nhiên coi đã có list hoàn chỉnh để cache; hành vi thực tế cần test với provider và publisher đang dùng.

Không đặt business side effect quan trọng trong cache loader rồi trông chờ cache chỉ cho chạy một lần. Với hai pod dùng local cache riêng, `sync=true` (khi được provider hỗ trợ) cũng không tự tạo distributed single-flight.

## 13. Spring @Cacheable không giống Reactor Flux.cache()

Cùng chữ “cache” nhưng bản chất khác:

- **Spring `@Cacheable`**: cache kết quả method theo key qua `CacheManager`; với `Flux` trong Spring 6.1+ có thể gom emission thành `List` để lưu.
- **Reactor `Flux.cache()`**: operator trên một publisher instance để replay tín hiệu cho subscriber về sau; có overload giới hạn `history` hoặc TTL.

Không nên dùng `Flux.cache()` replay không giới hạn trên stream vô hạn rồi cho rằng có bộ nhớ cố định. Muốn chia sẻ subscription live, lưu snapshot hay ghi lịch sử sự kiện là ba nhu cầu khác nhau, cần cơ chế khác nhau.

## 14. Kiểm thử an toàn

### Test chức năng

1. Query có source-side limit và pipeline có `onComplete`; mỗi page tối đa max size.
2. Page âm, size bằng 0/vượt max bị từ chối **trước cache interception**.
3. Các key tenant/page/size/filter/sort/version được phân biệt.
4. Cache hit lấy đúng snapshot; TTL/eviction phản ánh cập nhật nguồn.
5. Loader error, provider timeout và cancellation không tạo một kết quả “thành công” chưa đầy đủ.

### Test stream vô hạn mà không làm treo process

**Không** chạy `Flux.interval(...).collectList().block()` không có giới hạn trong test. Dùng `StepVerifier` cancel sau một số phần tử hoặc test pipeline hữu hạn:

~~~java
StepVerifier.create(Flux.range(1, 100).take(3).collectList())
    .expectNext(List.of(1, 2, 3))
    .verifyComplete();
~~~

Đoạn này là **test Reactor** (cần imports `StepVerifier`, `Flux`, `List` và dependency `reactor-test`), không phải Java thuần tự chạy. Nó xác minh `take(3)` giúp pipeline hoàn tất; **không chứng minh Spring cache provider đã được kiểm thử**.

### Test hiệu năng

- Đo peak heap, GC pause và kích thước serialized payload của từng cache entry.
- Thử nhiều request đồng thời lúc cache miss/TTL expiry.
- Đo latency, hit rate, băng thông, thời gian deserialize khi cache page so với cache cả dataset.
- Thử nhiều instance và backend thật nếu production chạy cluster.
- Inject lỗi provider, cancel, query timeout và kiểm tra không rò rỉ subscription.

## 15. Những lỗi hiểu sai phổ biến

| Hiểu lầm | Thực tế |
|---|---|
| “Flux bất đồng bộ nên cache được vô hạn” | Cache một chuỗi thường cần kết quả hữu hạn và hoàn tất |
| “Mono phát một phần tử nên chắc nhỏ” | Phần tử có thể là một list/byte array rất lớn |
| “Flux hữu hạn luôn đáng cache” | Entry lớn có thể gây tốn RAM, mạng và GC |
| “collectList tự dừng sau N phần tử” | Thường đợi onComplete; phải dùng `take(N)`/cơ chế kết thúc |
| “take(50) chắc chắn làm DB chỉ quét 50 record” | Cần source-side limit/pushdown |
| “Timeout tương đương giới hạn kích thước” | Timeout không chặn burst hàng triệu phần tử |
| “sync=true khóa mọi JVM” | Phụ thuộc provider; không mặc nhiên là distributed lock |
| “Flux.cache() luôn bounded” | Chỉ bounded khi policy history/TTL phù hợp |
| “Key chỉ cần page index” | Cần tenant/size/filter/sort/version khi ảnh hưởng dữ liệu |
| “Đã test 3 phần tử là đủ” | Còn phải test completion, provider, memory và cancellation |

## 16. Checklist thiết kế

Trước khi thêm `@Cacheable` vào kết quả bất đồng bộ:

1. Publisher có bảo đảm kết thúc bình thường không?
2. Có giới hạn tối đa số phần tử, byte và thời gian không?
3. Giới hạn có thực thi ngay tại DB/API nguồn không?
4. Có nên cache page/summary/per-ID thay vì cả Flux không?
5. Key đã bao gồm tenant, size, page, filter, sort và version chưa?
6. Spring/cache provider có hỗ trợ reactive/CompletableFuture caching theo phiên bản dùng không?
7. TTL và invalidation phản ánh mức stale được chấp nhận chưa?
8. Khi cache miss đồng thời, áp lực RAM/network có được chặn không?
9. Khi timeout/cancel/error, resources/subscriptions có được dọn đúng không?
10. Đã thử tải thật và phân tích heap/entry size chưa?

**Quy tắc:** chỉ cache kết quả **hữu hạn và có chi phí dự đoán được**; giữ live event stream ở cơ chế streaming phù hợp.

## 17. Tự kiểm tra

**1.** Vì sao `@Cacheable` trên `Flux.interval(...)` không phù hợp để lưu toàn bộ kết quả?

**2.** `Mono<List<Product>>` có chắc dùng ít bộ nhớ không?

**3.** `take(50)` có tự bảo đảm database chỉ quét 50 row không?

**4.** Khi cần hiển thị catalog rất lớn, cache toàn bộ Flux hay từng page?

**5.** Từ Java `IntStream.iterate` vô hạn, operator nào giúp `toList()` kết thúc?

**6.** Vì sao key page cần tenant/page/size/filter/sort khi dữ liệu phụ thuộc chúng?

**7.** `Flux.cache()` có giống `@Cacheable` không?

**8.** Timeout có thay được byte limit và item limit không?

**Đáp án:**

1. Nguồn không tự hoàn tất, nên không có list đầy đủ để cache.
2. **Không.** Một emission có thể chứa list rất lớn.
3. **Không.** Cần giới hạn ngay tại nguồn và kiểm tra execution plan.
4. **Phân trang**, hoặc cache summary/DTO nhỏ nếu phù hợp.
5. `limit(n)` hoặc điều kiện dừng hữu hạn.
6. Để tránh cache key trùng, dữ liệu sai và rò rỉ giữa tenant.
7. **Không.** Reactor cache là replay operator, Spring cache là method/result cache abstraction.
8. **Không.** Burst có thể phát rất nhiều dữ liệu trước timeout.

## 18. Tài liệu tham khảo

- Spring Framework Reference — *Declarative Annotation-based Caching*, phần *Caching with CompletableFuture and Reactive Return Types*: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Javadoc — `Cacheable` và `sync`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Javadoc — `Cache` và API retrieve bất đồng bộ: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html
- Reactor Core Reference — `Flux`/`Mono` và các operator: https://projectreactor.io/docs/core/release/reference/
- Reactor Javadoc — `Flux.collectList`, `take`, `cache`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Java 17 Javadoc — `IntStream.iterate` và `limit`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html

**Kết luận:** Spring có thể cache `Flux` bằng cách gom emission thành một danh sách, nhưng **stream vô hạn không có kết quả trọn vẹn** và stream hữu hạn quá lớn gây áp lực tài nguyên. Hãy cache **page/snapshot/summary hữu hạn**, giới hạn tại nguồn, chọn cache key/TTL chính xác và kiểm chứng với provider thật; không cache toàn bộ live stream.