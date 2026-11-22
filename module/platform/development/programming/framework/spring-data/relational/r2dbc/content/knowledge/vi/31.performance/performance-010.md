# Thiết kế cache cùng chiến lược vô hiệu hóa dữ liệu

Cache lưu tạm dữ liệu đã được đọc hoặc tính toán để giảm số lần truy vấn database, giảm độ trễ và hạn chế tải lên hệ thống nguồn. Với Spring Data R2DBC, cache thường được đặt ở tầng service hoặc read model: service kiểm tra cache trước, nếu không có thì đọc bằng repository, sau đó lưu kết quả vào cache.

Khó khăn lớn nhất không phải là ghi dữ liệu vào cache, mà là giữ cache phù hợp với dữ liệu thật sau khi ứng dụng tạo, sửa hoặc xóa bản ghi. Một chiến lược cache cần xác định rõ dữ liệu nào được cache, key được tạo ra sao, TTL bao lâu, khi nào phải evict, và làm thế nào để nhiều instance cùng nhận biết một thay đổi.

Nguyên tắc nền tảng: **database vẫn là nguồn dữ liệu chính; cache là bản sao có thể được làm mới hoặc loại bỏ.** Hãy ưu tiên tính đúng đắn của thao tác ghi và có một chính sách nhất quán cho cache.

## 1. Vì sao cần cache?

Giả sử một API đọc thông tin sản phẩm được gọi nhiều lần trong một phút, trong khi dữ liệu chỉ thay đổi vài lần mỗi ngày. Nếu mỗi request đều truy vấn R2DBC database, ứng dụng phải thực hiện nhiều round-trip không cần thiết.

Cache có thể giúp:

- Giảm số truy vấn đọc lặp lại.
- Giảm độ trễ khi dữ liệu đã có trong cache.
- Giảm tải database và connection pool.
- Tăng khả năng chịu tải khi có nhiều request đọc cùng một dữ liệu.
- Lưu kết quả tính toán hoặc read model tốn chi phí tạo.

Cache không tự làm mọi request nhanh hơn. Việc lookup cache, serialize/deserialize, network tới Redis, đồng bộ invalidation và quản lý memory đều có chi phí. Dữ liệu thay đổi liên tục hoặc chỉ được đọc một lần có thể không đáng cache.

### 1.1. Cache không phải nguồn dữ liệu chính

Cache có thể hết hạn, bị xóa, bị restart hoặc mất dữ liệu. Ứng dụng phải có thể dựng lại giá trị từ database hoặc nguồn dữ liệu gốc.

Không nên chỉ ghi một giá trị vào cache rồi xem đó là dữ liệu bền vững duy nhất. Nếu cache mất dữ liệu, nghiệp vụ phải tiếp tục hoạt động theo chính sách fallback phù hợp.

### 1.2. Khi nào nên cache?

Những ứng viên phù hợp thường có các đặc điểm:

- Được đọc nhiều hơn được ghi.
- Chi phí truy vấn hoặc tính toán tương đối cao.
- Có thể chấp nhận một khoảng thời gian dữ liệu cũ, hoặc có cách invalidation rõ ràng.
- Có key xác định ổn định.
- Kích thước và số lượng entry có thể giới hạn.

Ví dụ: thông tin danh mục, cấu hình hiển thị, chi tiết sản phẩm, thông tin hồ sơ công khai, bảng giá có phiên bản, kết quả tổng hợp có thể chấp nhận TTL ngắn.

Những dữ liệu như số dư tài khoản, hạn mức, trạng thái thanh toán hoặc tồn kho cần kiểm tra rất cẩn thận. Nếu quyết định nghiệp vụ yêu cầu dữ liệu mới nhất, không nên dựa vào cache cũ như nguồn xác nhận cuối cùng.

## 2. Các kiểu cache thường gặp

### 2.1. Local cache trong một instance

Local cache nằm trong bộ nhớ của một tiến trình ứng dụng. Ví dụ phổ biến là Caffeine.

Ưu điểm:

- Lookup nhanh, không cần network.
- Cấu hình đơn giản cho dữ liệu ít thay đổi.
- Không cần vận hành một cache server riêng.

Hạn chế:

- Mỗi instance có bản cache riêng.
- Invalidation trên instance A không tự xóa cache của instance B.
- Dữ liệu mất khi process restart.
- Memory cần giới hạn theo size/weight và expiration.

Local cache phù hợp với dữ liệu ít thay đổi hoặc chấp nhận stale window ngắn. Với nhiều instance, cần cơ chế broadcast invalidation hoặc TTL đủ ngắn để giới hạn thời gian dữ liệu cũ.

### 2.2. Distributed cache

Distributed cache thường được triển khai bằng Redis hoặc một hệ thống cache tập trung. Nhiều instance ứng dụng đọc cùng một vùng dữ liệu cache.

Ưu điểm:

- Các instance có thể chia sẻ entry.
- Cache không mất ngay khi một instance restart.
- Có thể quản lý TTL và capacity độc lập với ứng dụng.

Hạn chế:

- Lookup cần network.
- Cache server có thể trở thành điểm nghẽn hoặc điểm lỗi.
- Cần xử lý serialization, kết nối, bảo mật và vận hành.
- Invalidation vẫn phải được thiết kế đúng.

Với ứng dụng reactive, có thể dùng Reactive Redis operations để giữ đường truy cập cache bất đồng bộ.

### 2.3. Cache nhiều tầng

Một ứng dụng có thể dùng local cache L1 và Redis L2:

~~~text
Request
  |
  v
Local cache (L1)
  | miss
  v
Redis (L2)
  | miss
  v
R2DBC database
~~~

L1 giảm latency nhưng tạo thêm vấn đề invalidation giữa các instance. Khi dữ liệu thay đổi, cần xóa hoặc cập nhật cả Redis và các local cache liên quan. Có thể dùng pub/sub hoặc message event để broadcast invalidation; TTL chỉ là lớp bảo vệ cuối cùng.

Không thêm nhiều tầng cache nếu chưa có số liệu chứng minh lợi ích. Mỗi tầng làm tăng số trạng thái cần đồng bộ.

## 3. Cache-aside: mẫu phổ biến cho R2DBC

Cache-aside (lazy loading) là mẫu đơn giản và dễ kiểm soát:

1. Tạo cache key từ request.
2. Đọc cache.
3. Nếu có dữ liệu, trả về cache hit.
4. Nếu không có, truy vấn database.
5. Lưu kết quả vào cache với TTL.
6. Trả kết quả cho caller.

~~~mermaid
flowchart TD
    A["Request đọc dữ liệu"]
    B["Lookup cache"]
    C{"Cache hit?"}
    D["Trả dữ liệu cache"]
    E["Query R2DBC repository"]
    F["Lưu cache với TTL"]
    G["Trả dữ liệu từ database"]

    A --> B --> C
    C -->|Có| D
    C -->|Không| E --> F --> G
~~~

Mẫu này phù hợp khi cache có thể bị mất bất cứ lúc nào: request tiếp theo sẽ tự tải lại từ database.

### 3.1. Ví dụ service cache-aside với Reactive Redis

Giả sử đã cấu hình ReactiveRedisTemplate có key serializer và value serializer phù hợp cho ProductView:

~~~java
public record ProductView(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

Service:

~~~java
import java.time.Duration;

import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ProductQueryService {

    private static final Duration TTL = Duration.ofMinutes(5);

    private final ProductRepository repository;
    private final ReactiveRedisTemplate<String, ProductView> cache;

    public ProductQueryService(
            ProductRepository repository,
            ReactiveRedisTemplate<String, ProductView> cache) {
        this.repository = repository;
        this.cache = cache;
    }

    public Mono<ProductView> findById(Long id) {
        String key = "product:v1:" + id;

        return cache.opsForValue()
            .get(key)
            .switchIfEmpty(
                repository.findById(id)
                    .map(ProductView::from)
                    .flatMap(view ->
                        cache.opsForValue()
                            .set(key, view, TTL)
                            .thenReturn(view)
                    )
            );
    }
}
~~~

ProductView.from là factory method do ứng dụng định nghĩa. ReactiveRedisTemplate cần được cấu hình với serializer tương ứng; không nên dựa vào serializer mặc định mà không kiểm tra kiểu dữ liệu được lưu.

Trong ví dụ này:

- Cache hit trả về Mono<ProductView>.
- Cache miss gọi repository.
- Kết quả database được chuyển thành read model.
- Cache được ghi với TTL 5 phút.
- Kết quả vẫn được trả về dưới dạng Mono.

Nếu cache write thất bại, ví dụ trên phát lỗi. Trong một số hệ thống, có thể chọn fail-open: ghi log/metric lỗi cache nhưng vẫn trả dữ liệu database. Khi triển khai fail-open, chỉ bắt lỗi từ thao tác cache; đừng biến lỗi database thành cache miss hoặc dữ liệu rỗng.

### 3.2. Tránh query database hai lần

Không tạo hai publisher độc lập cho cùng một request rồi subscribe cả hai. Hãy đặt thao tác cache miss trong switchIfEmpty/flatMap để chỉ chạy khi cần.

Publisher reactive thường lazy; việc gọi repository method tạo publisher chưa chắc đã gửi SQL. Tuy nhiên, nếu cùng publisher được subscribe nhiều lần, câu query có thể chạy nhiều lần. Hãy tổ chức chain sao cho mỗi request có một lần thực thi mong muốn.

## 4. Cache key phải phản ánh đầy đủ đầu vào

Cache key xác định một giá trị cache tương ứng với request nào. Nếu key thiếu một tham số ảnh hưởng kết quả, ứng dụng có thể trả nhầm dữ liệu.

Ví dụ truy vấn danh sách sản phẩm có filter category, sort và page:

~~~text
products:v2:category=books:sort=price_asc:page=0:size=20
~~~

Một key nên bao gồm mọi yếu tố có thể làm thay đổi kết quả:

- Entity ID hoặc aggregate ID.
- Tenant/customer/account ID nếu dữ liệu phân vùng theo tenant.
- Filter và trạng thái.
- Sort order.
- Page/size hoặc cursor.
- Locale nếu nội dung được bản địa hóa.
- Currency hoặc pricing context.
- Version của schema/serialization nếu cần.

Không dùng key chỉ gồm productId nếu kết quả còn phụ thuộc tenant hoặc quyền truy cập. Thiếu tenant ID có thể làm lộ dữ liệu giữa các tenant.

### 4.1. Dùng namespace và version

Một key có thể có cấu trúc:

~~~text
<application>:<region>:<schema-version>:<identifier>
~~~

Ví dụ:

~~~text
catalog:product:v2:1042
catalog:search:v3:books:price-asc:0:20
~~~

Namespace giúp tránh đụng key với ứng dụng khác. Version giúp thay đổi cấu trúc payload hoặc semantics cache mà không cần cố gắng đọc dữ liệu cũ bằng kiểu mới.

### 4.2. Chuẩn hóa key

Nếu key chứa filter động, hãy chuẩn hóa thứ tự và cách biểu diễn trước khi tạo key. Hai request có cùng ý nghĩa phải tạo cùng key.

Ví dụ map filter có thể có thứ tự field khác nhau nhưng cùng giá trị. Nếu serialize map không ổn định, hai request tương đương có thể tạo hai cache entry khác nhau.

Với key dài hoặc chứa nhiều tham số, có thể tạo chuỗi canonical rồi hash. Hãy giữ prefix dễ quan sát để phục vụ metrics và vận hành.

## 5. TTL và chính sách hết hạn

TTL (time to live) là thời gian một cache entry được giữ trước khi hết hạn. TTL giúp giới hạn thời gian dữ liệu cũ tồn tại ngay cả khi invalidation bị bỏ lỡ.

Ví dụ:

~~~java
cache.opsForValue()
    .set(key, value, Duration.ofMinutes(5));
~~~

Chọn TTL dựa trên:

- Tần suất thay đổi của dữ liệu.
- Mức độ chấp nhận stale data của nghiệp vụ.
- Chi phí truy vấn database.
- Khả năng invalidation chủ động.
- Kích thước cache và memory.
- Tần suất request và nguy cơ cache stampede khi hết hạn đồng loạt.

Không có TTL chung cho mọi dữ liệu. Danh mục ít thay đổi có thể giữ lâu hơn; trạng thái biến động cần TTL ngắn hoặc invalidation ngay sau commit.

### 5.1. TTL không thay thế invalidation

TTL chỉ giới hạn thời gian lưu cache. Nếu giá trị thay đổi ngay sau khi được cache, caller vẫn có thể đọc giá trị cũ trong toàn bộ TTL.

Nếu nghiệp vụ yêu cầu cập nhật phản ánh nhanh, hãy evict/update cache khi ghi thành công và dùng TTL làm lớp bảo vệ khi event invalidation bị mất.

### 5.2. Thêm jitter để tránh hết hạn đồng loạt

Nếu hàng nghìn key được tạo cùng lúc với TTL chính xác 5 phút, chúng có thể hết hạn gần nhau và tạo một đợt truy vấn database lớn.

Có thể cộng một khoảng jitter ngẫu nhiên vào TTL, ví dụ từ 0 đến 30 giây. Jitter phân tán thời điểm hết hạn, giảm nguy cơ nhiều request cùng truy vấn lại một lúc.

### 5.3. Giới hạn kích thước và eviction

TTL không phải cơ chế giới hạn memory duy nhất. Cache cần capacity policy như maximum size/weight hoặc eviction policy của Redis. Nếu cache không giới hạn, nhiều key một lần dùng có thể làm memory tăng không kiểm soát.

Theo dõi hit ratio, eviction count, memory usage và số key theo namespace để chọn capacity phù hợp.

## 6. Vô hiệu hóa cache khi dữ liệu thay đổi

Có ba cách xử lý cache khi dữ liệu được ghi:

1. **Evict**: xóa entry để request tiếp theo đọc lại database.
2. **Update**: ghi giá trị mới vào cache.
3. **Version/bump namespace**: tăng version để key cũ không còn được sử dụng.

Evict thường đơn giản và ít rủi ro hơn update vì không cần tái tạo chính xác mọi cache representation có liên quan.

Ví dụ, khi cập nhật sản phẩm:

~~~java
return productRepository.save(product)
    .flatMap(saved ->
        cache.opsForValue()
            .delete("product:v1:" + saved.id())
            .thenReturn(saved)
    );
~~~

Cách trên thể hiện ý tưởng, nhưng nếu repository save và cache delete nằm trong cùng reactive transaction database, cache delete không rollback cùng database. Cần xác định rõ thời điểm invalidation và cách xử lý nếu transaction rollback.

## 7. Invalidate sau khi database commit

Một lỗi tinh vi là evict cache trước khi transaction database commit:

1. Transaction bắt đầu cập nhật product.
2. Ứng dụng xóa cache.
3. Request khác cache miss và đọc database trước khi transaction đầu commit.
4. Request đó nhận dữ liệu cũ và ghi lại vào cache.
5. Transaction đầu commit dữ liệu mới.
6. Cache lại chứa dữ liệu cũ.

Đây là stale repopulation race. Vì vậy, với cache-aside, cách phổ biến là chỉ invalidation sau khi transaction ghi database đã commit thành công.

### 7.1. Tách writer transactional và bước evict sau commit

Có thể đặt thao tác ghi trong một bean riêng có transaction, rồi thực hiện eviction ở downstream sau khi publisher transaction hoàn tất:

~~~java
@Service
public class ProductWriter {

    private final ProductRepository repository;

    public ProductWriter(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Mono<Product> update(Product product) {
        return repository.save(product);
    }
}
~~~

Service điều phối:

~~~java
@Service
public class ProductCommandService {

    private final ProductWriter writer;
    private final ReactiveRedisTemplate<String, ProductView> cache;

    public ProductCommandService(
            ProductWriter writer,
            ReactiveRedisTemplate<String, ProductView> cache) {
        this.writer = writer;
        this.cache = cache;
    }

    public Mono<Product> update(Product product) {
        return writer.update(product)
            .flatMap(saved ->
                cache.opsForValue()
                    .delete("product:v1:" + saved.id())
                    .thenReturn(saved)
            );
    }
}
~~~

Vì writer là bean khác, lời gọi đi qua transaction proxy. Transaction reactive do writer quản lý hoàn tất trước khi kết quả được phát ra cho downstream. Bước delete cache được thực hiện sau khi writer publisher đã kết thúc thành công.

Không đặt hai phương thức trong cùng class rồi gọi trực tiếp từ method này sang method kia nếu đang dựa vào proxy-based @Transactional; self-invocation có thể bỏ qua transaction interceptor.

Cách này vẫn có một cửa sổ lỗi: database đã commit nhưng cache eviction thất bại. Đối với dữ liệu có thể chấp nhận TTL ngắn, có thể ghi nhận lỗi và dựa vào TTL. Nếu invalidation bắt buộc phải được phát bền vững, hãy dùng outbox.

### 7.2. Vì sao không update cache trước commit?

Nếu cache được cập nhật bằng giá trị mới trước khi database commit, request khác có thể đọc giá trị mới trong khi transaction database sau đó rollback. Cache lúc đó chứa trạng thái chưa từng được commit.

Hãy chỉ publish cache update/evict sau commit, trừ khi có một thiết kế consistency riêng chứng minh việc làm trước commit là an toàn.

### 7.3. Xử lý khi cache eviction lỗi

Có hai chính sách thường gặp:

- **Fail request**: database đã commit nhưng cache eviction lỗi, request báo lỗi. Caller có thể retry dù thao tác ghi đã thành công; cần idempotency.
- **Fail open**: ghi nhận lỗi cache, vẫn trả thành công cho thao tác database. Cache có thể stale đến khi TTL hết hạn hoặc invalidation được retry.

Không có lựa chọn đúng cho mọi hệ thống. Với cache chỉ tối ưu hiệu năng, fail-open thường hợp lý nếu TTL giới hạn stale window. Với dữ liệu mà stale cache gây sai nghiệp vụ, cần invalidation bền vững và cách đọc nhất quán hơn.

## 8. Invalidation khi một bản ghi ảnh hưởng nhiều cache key

Một thay đổi product có thể ảnh hưởng nhiều dạng cache:

- Chi tiết theo ID.
- Danh sách theo category.
- Tìm kiếm theo keyword.
- Danh sách sản phẩm nổi bật.
- Trang tổng hợp giá hoặc tồn kho.

Chỉ xóa product:{id} không đủ nếu các query cache vẫn chứa bản ghi cũ.

Các chiến lược:

### 8.1. Evict cả cache region

Nếu số lượng query cache nhỏ và có thể xóa theo vùng, evict toàn bộ region liên quan:

~~~text
productById
productSearch
featuredProducts
categoryProducts
~~~

Đây là cách đơn giản nhưng có thể làm giảm hit ratio sau mỗi lần ghi.

Với Redis, tránh dùng lệnh KEYS trên keyspace lớn trong request path. Hãy dùng namespace/version, index key được quản lý hoặc SCAN trong tiến trình bảo trì nếu cần tìm và xóa nhiều key.

### 8.2. Dùng versioned namespace

Có thể lưu một version cho vùng cache. Key chứa version hiện tại:

~~~text
product-search:v17:<filter-hash>
~~~

Khi có thay đổi ảnh hưởng kết quả tìm kiếm, tăng version lên v18. Các key cũ tự trở thành không còn được truy cập và sẽ hết hạn theo TTL.

Cách này giúp invalidation một vùng lớn mà không phải xóa từng key. Tuy nhiên, cập nhật version cần atomic và tất cả instance phải đọc cùng version nguồn.

### 8.3. Cache tag hoặc index

Có thể lưu danh sách key phụ thuộc vào một product/category để khi thay đổi, ứng dụng xóa các key liên quan. Cách này linh hoạt nhưng việc duy trì index/tag cũng phải atomic và có thể tạo thêm write amplification.

Chỉ dùng khi cần invalidation chính xác cho nhiều query representation. Với hệ thống đơn giản, TTL ngắn và evict region có thể dễ vận hành hơn.

## 9. Invalidation giữa nhiều application instance

Với local cache, mỗi instance có dữ liệu riêng:

~~~text
Instance A: local cache
Instance B: local cache
Instance C: local cache
         |
         v
      Database
~~~

Khi instance A cập nhật database và chỉ xóa cache của A, instance B/C vẫn giữ giá trị cũ.

Các lựa chọn:

- Dùng distributed cache chung như Redis cho vùng dữ liệu cần chia sẻ.
- Publish invalidation event qua message broker/pub-sub để mỗi instance xóa local entry.
- Dùng TTL ngắn để giới hạn thời gian stale nếu có thể chấp nhận.
- Dùng version key được chia sẻ giữa các instance.

Redis Pub/Sub không phải hàng đợi bền vững: subscriber offline có thể bỏ lỡ message. Nếu invalidation không được phép mất, dùng cơ chế message bền vững hoặc outbox relay. Consumer cần xử lý duplicate và event đến trễ.

## 10. Dùng Outbox để bảo đảm invalidation không bị mất

Một tình huống phổ biến:

1. Database commit dữ liệu mới.
2. Process crash trước khi xóa Redis hoặc publish invalidation.
3. Cache tiếp tục chứa giá trị cũ.

Nếu invalidation phải được gửi bền vững, ghi một outbox event trong cùng transaction với business update:

~~~text
Transaction Orders DB:
  UPDATE product
  INSERT outbox_message(ProductUpdated)
  COMMIT

Relay:
  đọc outbox
  publish ProductUpdated

Cache invalidation consumer:
  evict product detail và các query cache liên quan
~~~

Outbox bảo đảm sự kiện invalidation được lưu cùng business change. Relay có thể publish lại nếu crash, vì vậy consumer phải idempotent.

Với nhiều application instance có local cache, mỗi instance cần nhận invalidation hoặc dùng một cache shared. Cần cân nhắc subscriber restart, replay và event ordering.

Outbox tăng độ tin cậy nhưng không làm invalidation tức thời tuyệt đối. Có một khoảng thời gian giữa database commit và lúc consumer nhận event. Nếu nghiệp vụ yêu cầu read-after-write nhất quán ngay lập tức, caller ghi có thể bypass cache hoặc đọc lại database cho lần đọc tiếp theo.

## 11. Spring Cache abstraction và annotation

Spring cung cấp Cache abstraction để ứng dụng dùng annotation hoặc Cache API mà không gắn chặt với một provider cụ thể.

Các annotation thường gặp:

| Annotation | Vai trò |
|---|---|
| @Cacheable | Đọc cache trước; nếu miss thì gọi method và lưu kết quả |
| @CachePut | Luôn gọi method rồi cập nhật cache với kết quả |
| @CacheEvict | Xóa một hoặc nhiều cache entry |
| @Caching | Kết hợp nhiều thao tác cache |
| @CacheConfig | Cấu hình cache/key mặc định ở cấp class |

Ví dụ:

~~~java
@Cacheable(cacheNames = "productById", key = "#id")
public Mono<ProductView> findById(Long id) {
    return repository.findById(id)
        .map(ProductView::from);
}
~~~

Với Spring Framework 6.1 trở lên, cache annotations hỗ trợ thích ứng với reactive return types như Mono và Flux. Mono được xử lý như một giá trị bất đồng bộ; Flux được thu thập thành List để cache và sau đó phát lại dưới dạng Flux. Điều này có nghĩa cache một Flux lớn có thể cần thu thập toàn bộ kết quả vào bộ nhớ.

Cần kiểm tra phiên bản Spring Framework đang dùng. Ứng dụng ở phiên bản cũ hơn có thể không có hành vi reactive adaptation này.

### 11.1. Cache provider có thể vẫn blocking

Reactive adaptation của annotation không tự biến mọi Cache implementation thành non-blocking. Một provider có API đồng bộ có thể thực hiện lookup/put blocking khi được gọi.

Nếu yêu cầu end-to-end non-blocking quan trọng, hãy xác nhận provider hỗ trợ asynchronous cache retrieval hoặc dùng API reactive trực tiếp, chẳng hạn ReactiveRedisTemplate. Không nên chỉ nhìn thấy method trả Mono rồi kết luận toàn bộ cache path là non-blocking.

### 11.2. Dùng @CacheEvict cho method ghi

Ví dụ đơn giản:

~~~java
@CacheEvict(cacheNames = "productById", key = "#product.id")
public Mono<Product> update(Product product) {
    return repository.save(product);
}
~~~

Cần đặc biệt chú ý thời điểm eviction và reactive transaction. Nếu eviction được thực hiện trước khi database transaction commit, có thể xuất hiện stale repopulation race. Với yêu cầu evict sau commit, dùng after-invocation semantics phù hợp với phiên bản/framework, tách writer transactional và eviction downstream sau commit, hoặc dùng outbox cho invalidation bền vững.

Không dựa vào annotation nếu chưa xác nhận chính xác thứ tự interceptor, transaction boundary và cache provider của phiên bản đang dùng.

### 11.3. Cache key bằng SpEL

Ví dụ:

~~~java
@Cacheable(
    cacheNames = "productByTenant",
    key = "#tenantId + ':' + #productId"
)
public Mono<ProductView> find(
        String tenantId,
        Long productId) {
    // ...
}
~~~

Key bao gồm tenantId để tránh trộn dữ liệu giữa các tenant. Không đưa secret hoặc dữ liệu cá nhân nhạy cảm vào key nếu không cần; key có thể xuất hiện trong Redis monitoring và log.

## 12. Cache dữ liệu reactive bằng Reactive Redis

Nếu muốn thao tác Redis non-blocking, dùng ReactiveRedisTemplate hoặc ReactiveStringRedisTemplate thay cho RedisTemplate đồng bộ.

Một bean template cần cấu hình serializer cho key/value. Ví dụ cấu hình khái niệm:

~~~java
@Bean
ReactiveRedisTemplate<String, ProductView> productCacheTemplate(
        ReactiveRedisConnectionFactory connectionFactory,
        RedisSerializer<ProductView> valueSerializer) {

    RedisSerializationContext<String, ProductView> context =
        RedisSerializationContext
            .<String, ProductView>newSerializationContext(
                RedisSerializer.string()
            )
            .value(valueSerializer)
            .build();

    return new ReactiveRedisTemplate<>(
        connectionFactory,
        context
    );
}
~~~

RedisSerializer<ProductView> cần được tạo với cơ chế JSON serializer phù hợp và có kiểm soát type metadata. API constructor/builder cụ thể có thể khác theo phiên bản Spring Data Redis. Không bật polymorphic default typing rộng cho dữ liệu không tin cậy.

Khi template đã cấu hình:

~~~java
Mono<ProductView> cached =
    productCacheTemplate.opsForValue().get(key);

Mono<Boolean> stored =
    productCacheTemplate.opsForValue()
        .set(key, view, Duration.ofMinutes(5));

Mono<Boolean> removed =
    productCacheTemplate.opsForValue().delete(key);
~~~

Các thao tác trả về publisher reactive, nên có thể kết hợp bằng flatMap, then và switchIfEmpty trong service.

### 12.1. Cache failure và fail-open

Nếu Redis không khả dụng, một cache tối ưu hiệu năng có thể được bỏ qua để truy vấn database:

~~~java
Mono<ProductView> fromCache =
    cache.opsForValue()
        .get(key)
        .onErrorResume(error -> {
            metrics.cacheReadFailure();
            return Mono.empty();
        });
~~~

Sau đó dùng switchIfEmpty để đọc database. Tuy nhiên, cách này coi cả cache miss và cache error là cùng một tín hiệu empty. Hãy ghi metric/log riêng để phân biệt chúng.

Khi ghi cache thất bại, có thể vẫn trả dữ liệu database:

~~~java
return repository.findById(id)
    .map(ProductView::from)
    .flatMap(view ->
        cache.opsForValue()
            .set(key, view, TTL)
            .onErrorResume(error -> {
                metrics.cacheWriteFailure();
                return Mono.just(false);
            })
            .thenReturn(view)
    );
~~~

Chỉ áp dụng fail-open nếu cache không phải yêu cầu nghiệp vụ bắt buộc. Không nuốt lỗi database hoặc lỗi mapping trong cùng nhánh xử lý cache.

## 13. Negative caching: cache kết quả không tồn tại

Một số key được hỏi lặp lại nhưng database không có bản ghi. Nếu mỗi lần đều truy vấn database, request có thể tạo tải không cần thiết.

Negative caching lưu dấu rằng một key không tồn tại trong một thời gian ngắn.

Không thể dùng một cache value null tùy tiện trong Reactive Streams. Có thể dùng một wrapper có trạng thái:

~~~java
public record ProductCacheEntry(
    boolean found,
    ProductView value
) {}
~~~

Nếu found=false, entry biểu thị không tìm thấy. TTL của negative entry thường ngắn hơn positive entry vì một bản ghi mới có thể được tạo sau đó.

Khi tạo product mới, phải evict negative cache key tương ứng. Nếu không, caller có thể tiếp tục nhận kết quả “không tồn tại” cho tới khi TTL hết hạn.

Negative caching phù hợp với ID/key có thể bị truy vấn lặp lại nhưng ít được tạo mới. Cần tránh cache lỗi kỹ thuật như timeout hoặc database unavailable thành “không tồn tại”.

## 14. Cache stampede và request đồng thời

Cache stampede xảy ra khi một key hết hạn hoặc bị evict, nhiều request cùng cache miss rồi đồng thời truy vấn database để dựng lại cùng một giá trị.

~~~mermaid
flowchart TD
    A["Cache key hết hạn"]
    B["Request A: miss"]
    C["Request B: miss"]
    D["Request C: miss"]
    E["Ba query cùng vào database"]
    F["Database tăng tải"]

    A --> B --> E
    A --> C --> E
    A --> D --> E
    E --> F
~~~

Các cách giảm stampede:

- Dùng single-flight/in-flight deduplication để các request cùng key chia sẻ một lần load.
- Dùng distributed lock khi nhiều instance cùng có thể load key.
- Thêm TTL jitter để tránh nhiều key hết hạn đồng thời.
- Làm mới cache trước khi hết hạn (refresh ahead) với dữ liệu phù hợp.
- Giới hạn concurrency của cache miss.
- Dùng stale-while-revalidate nếu nghiệp vụ chấp nhận trả dữ liệu cũ trong lúc refresh.

### 14.1. Single-flight trong một instance

Trong một instance, có thể dùng cơ chế chia sẻ publisher đang tải theo key. Cần quản lý lifecycle của entry để publisher đã hoàn tất hoặc lỗi được loại khỏi map; nếu giữ mãi, lỗi hoặc giá trị cũ có thể bị dùng lại vô hạn.

Không dùng một ConcurrentHashMap đơn giản mà không có cleanup, giới hạn size và xử lý cancellation. Nếu một subscriber hủy, không nên vô tình cancel công việc đang được các subscriber khác dùng chung.

### 14.2. Distributed lock

Với nhiều instance, lock trong memory của một process không đủ. Có thể dùng Redis lock với token duy nhất và TTL, nhưng phải bảo đảm chỉ chủ sở hữu token mới được release lock. Lease hết hạn trong lúc worker cũ còn chạy có thể dẫn tới hai worker cùng load.

Distributed lock làm tăng độ phức tạp và không phải lúc nào cũng cần. Hãy bắt đầu bằng TTL jitter, giới hạn concurrency và cache key hợp lý; chỉ thêm lock khi đo được stampede đáng kể.

## 15. Cache query, pagination và dữ liệu tổng hợp

Cache một entity theo ID thường dễ invalidation hơn cache query có filter.

Ví dụ query cache:

~~~text
product-search:category=books:sort=price:page=0:size=20
~~~

Một product đổi category hoặc price có thể ảnh hưởng nhiều query key. Cần chọn chính sách:

- TTL ngắn cho query cache.
- Evict cả query region khi product thay đổi.
- Version namespace cho category/search.
- Không cache các query có quá nhiều tổ hợp filter hiếm dùng.
- Cache DTO/page đã giới hạn kích thước.

### 15.1. Cache trang dữ liệu

Một page cache nên bao gồm toàn bộ tham số ảnh hưởng kết quả: filter, sort, page/size, tenant và locale. Nếu trả page metadata, cache cả content và total count như một read model nhất quán trong cùng entry.

Nếu content và total được cache riêng, chúng có thể có thời điểm cập nhật khác nhau. Điều đó có thể chấp nhận cho trang dashboard, nhưng cần xác định rõ semantics.

### 15.2. Không cache Flux vô hạn thành một List

Flux có thể đại diện cho một luồng dài hoặc không giới hạn. Thu thập toàn bộ Flux vào cache có thể làm bộ nhớ tăng không giới hạn và khiến request đầu tiên phải chờ hoàn tất toàn bộ nguồn.

Chỉ cache Flux khi đó là một tập hữu hạn có giới hạn kích thước và chính sách TTL rõ ràng. Với dữ liệu lớn, cache từng page/chunk hoặc một snapshot đã được giới hạn.

## 16. Cache và transaction consistency

Database transaction và Redis cache thường không cùng một transaction nguyên tử. Vì vậy, ứng dụng cần xác định thứ tự và mức nhất quán chấp nhận được.

Các lựa chọn phổ biến:

| Chiến lược | Thứ tự | Rủi ro chính |
|---|---|---|
| Evict trước DB commit | Xóa cache rồi ghi DB | Request khác có thể nạp lại dữ liệu cũ |
| Evict sau DB commit | Commit DB rồi xóa cache | Cache có thể stale nếu eviction thất bại |
| Update cache trước commit | Ghi cache rồi commit DB | Cache có thể chứa dữ liệu chưa commit nếu rollback |
| Outbox invalidation | Commit DB và outbox; relay evict sau | Có độ trễ event, cần consumer idempotent |
| TTL-only | Chờ entry hết hạn | Stale data tồn tại tới TTL |

Với cache-aside thông thường, evict sau commit là lựa chọn hợp lý. Với invalidation cần độ tin cậy cao, outbox giúp lưu bền vững yêu cầu invalidation cùng business update.

### 16.1. Read-after-write

Nếu caller cập nhật một product rồi ngay lập tức đọc lại, có thể bypass cache trong một khoảng thời gian hoặc trả trực tiếp giá trị mới từ kết quả update.

Ví dụ service update trả entity vừa lưu thay vì gọi lại read cache:

~~~java
return productWriter.update(command)
    .flatMap(saved ->
        evictRelatedKeys(saved.id())
            .thenReturn(ProductView.from(saved))
    );
~~~

Nếu eviction thất bại và service vẫn fail-open, caller vẫn nhận dữ liệu mới trong response. Request sau có thể còn đọc cache cũ; nếu điều đó không chấp nhận được, cần outbox/invalidation đáng tin cậy hoặc read path bypass cache theo version.

### 16.2. Version-based cache validation

Có thể lưu version của entity cùng cache value. Khi database trả version mới, ứng dụng so sánh để tránh dùng entry có version thấp hơn.

Version giúp phát hiện stale entry nếu ứng dụng có cách đọc version nguồn đáng tin cậy. Tuy nhiên, truy vấn database chỉ để kiểm tra version có thể triệt tiêu lợi ích cache. Hãy dùng khi có một version signal được chia sẻ hoặc event invalidation.

## 17. Cache dữ liệu nhạy cảm và phân quyền

Không cache dữ liệu chỉ theo ID nếu kết quả phụ thuộc người dùng hoặc quyền truy cập.

Ví dụ hồ sơ tài khoản có thể khác nhau tùy:

- Tenant.
- User ID.
- Role/permission.
- Locale.
- Feature flag.
- Phạm vi dữ liệu mà người gọi được phép xem.

Nếu key không bao gồm context phù hợp, một user có thể nhận representation đã được cache cho user khác.

Không cache password, access token, secret, dữ liệu thanh toán nhạy cảm hoặc dữ liệu cá nhân vượt quá nhu cầu. Nếu bắt buộc cache dữ liệu nhạy cảm, cần đánh giá encryption, access control, TTL, logging, retention và yêu cầu pháp lý.

Cache cũng không nên là nơi quyết định authorization cuối cùng nếu quyền có thể thay đổi. Khi quyền bị thu hồi, cần invalidation tương ứng hoặc kiểm tra quyền từ nguồn đáng tin cậy.

## 18. Observability và vận hành cache

Cache cần được đo lường giống database. Các chỉ số cơ bản:

| Metric | Ý nghĩa |
|---|---|
| Hit count / miss count | Tần suất cache phục vụ được request |
| Hit ratio | Tỷ lệ cache hit |
| Lookup latency | Thời gian đọc cache |
| Load latency | Thời gian lấy dữ liệu từ database khi miss |
| Eviction count | Số entry bị xóa/hết hạn |
| Cache write failure | Lỗi khi ghi cache |
| Cache read failure | Lỗi khi đọc cache |
| Entry count / memory usage | Quy mô cache |
| Stale-read incident | Số lần phát hiện cache cũ |
| Stampede/load concurrency | Mức request đồng thời khi miss |

Hit ratio cao không nhất thiết có nghĩa cache hữu ích. Nếu cache trả dữ liệu stale hoặc các key hiếm dùng chiếm memory, hiệu quả tổng thể có thể kém.

Theo dõi cả database query count và latency trước/sau khi bật cache. Đo p95/p99 để thấy tác động lên request tail latency.

### 18.1. Log và trace

Có thể gắn cache region, key namespace (đã loại bỏ dữ liệu nhạy cảm), hit/miss và correlation ID vào trace. Không log toàn bộ payload hoặc credentials.

Khi cache miss gây database query, trace nên thể hiện cả cache lookup và R2DBC query để biết thời gian nằm ở đâu.

### 18.2. Chế độ degraded khi cache lỗi

Nếu Redis là tối ưu hiệu năng chứ không phải dependency nghiệp vụ bắt buộc, ứng dụng có thể chuyển sang database khi Redis lỗi. Nhưng cần có:

- Giới hạn concurrency để database không bị quá tải.
- Circuit breaker hoặc rate limiting nếu phù hợp.
- Metric riêng cho cache unavailable.
- Cảnh báo khi cache mất kết nối kéo dài.
- Kế hoạch phục hồi cache sau khi Redis hoạt động lại.

Fail-open không miễn phí: khi Redis down, mọi request có thể dồn vào database. Một fallback không có giới hạn có thể gây cascading failure.

## 19. Kiểm thử cache và invalidation

Kiểm thử không chỉ xác nhận giá trị được ghi vào cache mà còn phải xác nhận cache bị vô hiệu hóa đúng lúc.

Các kịch bản hữu ích:

- Cache miss đọc repository và lưu kết quả.
- Cache hit không gọi repository lần nữa.
- Entry hết TTL được tải lại.
- Update commit xong thì key chi tiết bị evict.
- Transaction rollback thì không phát invalidation như một thay đổi đã commit.
- Cache eviction lỗi được xử lý theo fail-open/fail-closed đã chọn.
- Một thay đổi ảnh hưởng query cache thì các region/version tương ứng được cập nhật.
- Nhiều request cùng key miss không tạo tải database quá lớn nếu có single-flight.
- Nhiều instance nhận invalidation event.
- Duplicate invalidation event không gây lỗi.
- Tenant/locale/filter khác nhau tạo key riêng.
- Redis mất kết nối không làm ứng dụng trả nhầm cache miss thành kết quả không tồn tại.

Với R2DBC, nên dùng integration test trên database thật hoặc Testcontainers cho transaction và commit timing. Với Redis, có thể dùng Redis Testcontainer để kiểm thử TTL, serialization và invalidation.

Không chỉ mock cache trong mọi test. Mock hữu ích cho unit test logic, nhưng không phát hiện lỗi serializer, TTL, key naming, connection hoặc reactive behavior thực tế.

## 20. Quy trình thiết kế cache cho một use case

1. Xác định dữ liệu nào được đọc lặp lại và chi phí truy vấn hiện tại.
2. Xác định mức stale data mà nghiệp vụ chấp nhận.
3. Chọn local cache hay distributed cache.
4. Xác định representation cần cache: entity view, DTO, page hay aggregate summary.
5. Thiết kế key bao gồm mọi tham số ảnh hưởng kết quả.
6. Chọn TTL, capacity và jitter.
7. Chọn cache-aside hoặc một pattern khác.
8. Xác định mọi thao tác ghi có thể ảnh hưởng entry nào.
9. Evict/update sau commit; dùng outbox nếu invalidation cần bền vững.
10. Thiết kế consumer idempotent và đồng bộ giữa nhiều instance.
11. Giới hạn stampede và concurrency khi cache miss.
12. Đo hit ratio, latency, memory và stale-read.
13. Kiểm thử cache miss/hit, TTL, rollback, invalidation và cache outage.
14. Xem lại hiệu quả thực tế; bỏ cache nếu chi phí vận hành lớn hơn lợi ích.

## 21. Những lỗi thường gặp

**Chỉ cache mà không có invalidation.** Dữ liệu có thể stale tới khi TTL hết hạn. Xác định thao tác ghi và query cache bị ảnh hưởng.

**Evict trước khi transaction commit.** Request khác có thể nạp lại dữ liệu cũ trong lúc transaction ghi chưa commit. Thực hiện eviction sau commit.

**Cache key thiếu tenant hoặc filter.** Có thể trả nhầm dữ liệu giữa tenant, locale hoặc điều kiện tìm kiếm. Đưa đầy đủ context vào key.

**Dùng TTL rất dài để tăng hit ratio.** TTL dài làm tăng cửa sổ stale khi invalidation bị bỏ lỡ. Chọn TTL theo yêu cầu nghiệp vụ.

**Giả định Redis Pub/Sub bảo đảm không mất invalidation.** Subscriber offline có thể bỏ lỡ message. Dùng outbox/broker bền vững nếu không được phép mất.

**Cache một Flux không giới hạn.** Thu thập toàn bộ stream có thể tiêu tốn bộ nhớ và giữ tài nguyên lâu. Cache page hoặc tập hữu hạn.

**Dùng cache annotation nhưng provider blocking.** Reactive return type không tự bảo đảm cache I/O non-blocking. Xác nhận provider hoặc dùng ReactiveRedisTemplate.

**Nuốt mọi lỗi cache và database.** Chỉ fallback khi lỗi cache được xác định; lỗi database phải được truyền đúng semantics.

**Không xử lý cache stampede.** Nhiều request cùng miss có thể tạo tải đột biến lên database. Dùng TTL jitter, single-flight, concurrency limit hoặc lock khi cần.

**Cập nhật cache trước commit.** Rollback database có thể để cache chứa dữ liệu chưa từng commit. Cập nhật sau commit.

**Không giới hạn memory/keyspace.** Key một lần dùng có thể làm cache tăng vô hạn. Dùng capacity, TTL và dọn dẹp phù hợp.

## 22. Nguyên tắc thiết kế

- Xem database là nguồn dữ liệu chính, cache là bản sao có thể dựng lại.
- Chỉ cache dữ liệu có tần suất đọc và yêu cầu latency đủ để bù chi phí vận hành.
- Chọn local cache hoặc distributed cache theo topology và mức nhất quán cần thiết.
- Dùng cache-aside cho nhiều read path đơn giản.
- Thiết kế key bao gồm tenant, filter, sort, page, locale và các tham số ảnh hưởng kết quả.
- Dùng namespace/version để quản lý schema và invalidation theo vùng.
- Chọn TTL theo freshness requirement, thêm jitter và giới hạn capacity.
- Evict sau khi database transaction commit thành công.
- Dùng outbox nếu yêu cầu invalidation không được phép mất.
- Làm consumer invalidation idempotent và xử lý event giữa nhiều instance.
- Tránh cache dữ liệu nhạy cảm hoặc phụ thuộc quyền mà không có key/authorization phù hợp.
- Không collect Flux không giới hạn vào một cache value.
- Kiểm tra cache provider có non-blocking thật sự khi dùng với WebFlux/R2DBC.
- Giới hạn cache miss concurrency để tránh stampede và database overload.
- Đo hit/miss, latency, eviction, memory, lỗi cache và stale-read.
- Kiểm thử cả cache hit, miss, TTL, rollback, invalidation và outage.

## 23. Ghi nhớ

Cache giúp giảm truy vấn lặp và độ trễ, nhưng chỉ có ích khi key, TTL và invalidation được thiết kế cùng nhau. Cache-aside là mẫu dễ áp dụng với Spring Data R2DBC: đọc cache trước, miss thì query repository rồi lưu kết quả. Khi ghi dữ liệu, hãy evict hoặc cập nhật cache sau khi transaction database commit; evict trước commit có thể khiến request khác nạp lại trạng thái cũ.

Với nhiều instance, invalidation cần được chia sẻ qua distributed cache hoặc event bền vững như Outbox. TTL giới hạn thời gian stale nhưng không thay thế invalidation. Hãy xử lý duplicate event, cache stampede, cache outage, key theo tenant và giới hạn memory. Với reactive application, dùng API cache reactive như ReactiveRedisTemplate khi cần giữ I/O non-blocking, và chỉ cache Flux khi tập kết quả hữu hạn, có giới hạn rõ ràng.

