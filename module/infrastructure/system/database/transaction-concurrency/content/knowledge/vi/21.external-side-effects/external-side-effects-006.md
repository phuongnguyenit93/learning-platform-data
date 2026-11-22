# Bộ nhớ đệm và thời điểm cập nhật hoặc vô hiệu hóa sau COMMIT

Bộ nhớ đệm (cache) giúp ứng dụng đọc dữ liệu nhanh hơn bằng cách giữ một bản sao ở gần nơi xử lý, chẳng hạn trong bộ nhớ của ứng dụng hoặc Redis. Nhưng khi một transaction thay đổi dữ liệu trong database, bản sao trong cache cũng cần được xử lý. Nếu cache được cập nhật quá sớm, ứng dụng khác có thể đọc dữ liệu chưa commit. Nếu cache bị bỏ quên sau commit, người dùng có thể tiếp tục nhìn thấy giá trị cũ.

Vì vậy, câu hỏi quan trọng không chỉ là “cập nhật cache hay xóa cache?”, mà còn là **thực hiện việc đó ở thời điểm nào so với COMMIT**. Với cache-aside, một nguyên tắc phổ biến là chỉ cập nhật hoặc vô hiệu hóa cache sau khi database commit thành công. Tuy nhiên, thao tác sau commit có thể thất bại hoặc bị mất khi process dừng đột ngột, và các lần đọc đồng thời có thể tạo ra race condition. Bài học này giải thích các tình huống đó và cách thiết kế cơ chế đồng bộ phù hợp.

## 1. Database và cache có vai trò khác nhau

Trong một ứng dụng thông thường, database là nguồn dữ liệu có thẩm quyền (source of truth). Cache giữ bản sao để giảm thời gian đọc và tải cho database. Cache có thể nằm trong cùng process, trong một Redis cluster hoặc ở nhiều tầng khác nhau.

Ví dụ một sản phẩm có giá 500.000 đồng:

```text
Database: product_id = 10, price = 500000, version = 7
Cache:    product:10 -> { price: 500000, version: 7 }
```

Một transaction đổi giá thành 450.000 đồng. Sau khi commit, trạng thái mong muốn là:

```text
Database: product_id = 10, price = 450000, version = 8
Cache:    product:10 -> bị xóa hoặc chứa price = 450000, version = 8
```

Nếu cache vẫn giữ phiên bản 7, các request đọc cache hit sẽ tiếp tục nhận giá cũ. Nếu ứng dụng ghi giá mới vào cache trước khi database commit, request khác có thể nhìn thấy giá mới dù transaction sau đó rollback.

Cache không nên được xem là nơi xác nhận transaction đã thành công. Việc ghi cache và việc commit database là hai thao tác riêng, trừ khi hệ thống sử dụng một cơ chế transaction phân tán có bảo đảm phù hợp. Phần lớn ứng dụng web không cần ghép database và cache vào một distributed transaction; chúng cần một quy trình nhất quán có thể phục hồi.

## 2. Cache-aside: đọc cache, thiếu thì đọc database

Cache-aside (lazy loading) là mẫu phổ biến: ứng dụng tự kiểm tra cache, nếu không có dữ liệu thì đọc database, sau đó lưu kết quả vào cache.

```text
Client
  |
  v
Application
  |
  +---- GET cache key --------------------+
  |                                      |
  |                                  Cache hit?
  |                                      |
  |                         Có ----------+----> trả dữ liệu
  |                         Không
  |                           |
  |                           v
  |                      SELECT database
  |                           |
  |                           v
  |                      SET cache key
  |                           |
  +---------------------------+----------> trả dữ liệu
```

Ví dụ:

```java
public ProductView getProduct(long id) {
    String key = "product:" + id;

    ProductView cached = cache.get(key);
    if (cached != null) {
        return cached;
    }

    ProductView loaded = repository.findViewById(id)
        .orElseThrow(ProductNotFoundException::new);

    cache.put(key, loaded);
    return loaded;
}
```

Mẫu này dễ triển khai và cache chỉ được nạp khi có lượt đọc. Nhưng khi dữ liệu thay đổi, ứng dụng phải quyết định cập nhật giá trị cache hoặc xóa key để lần đọc sau nạp lại. Thời điểm thao tác này phải gắn với kết quả transaction database.

## 3. Vì sao không nên cập nhật cache trước COMMIT?

Giả sử database đang có giá 500.000 đồng và cache cũng lưu giá đó. T1 muốn đổi giá thành 450.000 đồng.

Nếu T1 ghi cache trước rồi mới commit database:

```text
T1: UPDATE product trong database, chưa COMMIT
T1: SET cache product:10 = 450000
T2: GET cache product:10 -> nhận 450000
T1: ROLLBACK vì validation hoặc lỗi khác
```

Kết quả cuối:

```text
Database: 500000
Cache:    450000
```

Cache đang chứa một giá trị chưa từng được commit. T2 có thể trả giá sai cho người dùng dù database không thay đổi.

Một tình huống khác là transaction ghi cache thành công nhưng database commit thất bại vì constraint, deadlock hoặc lỗi kết nối. Cache vẫn giữ giá trị mới, tạo ra trạng thái không nhất quán.

Vì vậy, với cache-aside thông thường, hãy đợi transaction database commit thành công rồi mới cập nhật hoặc vô hiệu hóa cache. Nếu transaction rollback, không phát hành thay đổi cache như thể dữ liệu đã được lưu.

## 4. Vì sao thao tác sau COMMIT cũng có rủi ro?

Chỉ thực hiện cache operation sau commit là cần thiết, nhưng chưa đủ để bảo đảm cache luôn được đồng bộ. Database và cache không cùng một transaction cục bộ.

Ví dụ:

```text
T1: UPDATE product price = 450000
T1: COMMIT thành công
Process: bị dừng đột ngột trước khi xóa cache

Database: 450000
Cache:    500000
```

Transaction đã commit nhưng cache chưa được invalidate. Nếu process không chạy lại thao tác này, cache có thể giữ giá cũ cho đến khi TTL hết hạn hoặc một sự kiện khác xóa key.

Một lỗi tương tự xảy ra nếu Redis tạm thời không truy cập được sau commit. Không nên rollback hoặc gửi lại transaction database chỉ vì thao tác xóa cache thất bại: database đã commit rồi. Hệ thống cần ghi nhận việc đồng bộ cache chưa hoàn tất và có cách retry độc lập.

## 5. Invalidate hay update cache sau COMMIT?

Có hai cách phổ biến để làm mới cache sau khi database commit.

### Invalidate: xóa key để lần đọc sau nạp lại

```text
Database COMMIT thành công
        |
        v
DEL product:10 trong cache
        |
        v
Lần đọc tiếp theo cache miss
        |
        v
SELECT dữ liệu mới từ database
        |
        v
SET cache với phiên bản mới
```

Ưu điểm của invalidate:

- Không phải tái tạo toàn bộ object cache trong luồng ghi.
- Giảm nguy cơ ghi nhầm một giá trị mới chưa được commit.
- Có thể xử lý nhiều dạng thay đổi bằng cách xóa các key liên quan.
- Phù hợp khi cache là dữ liệu dẫn xuất hoặc object được tạo từ nhiều bảng.

Nhược điểm là lượt đọc tiếp theo phải truy vấn database để nạp lại. Nếu nhiều key cùng bị xóa, database có thể nhận một đợt cache miss lớn (cache stampede). Ngoài ra, các race condition giữa cache miss và invalidate vẫn cần được xử lý.

### Update: ghi giá trị mới vào cache

```text
Database COMMIT thành công
        |
        v
SET product:10 = giá trị mới
```

Update cache có thể giúp request tiếp theo tiếp tục cache hit. Nó phù hợp khi object mới đã được tạo đầy đủ và có thể xác định chắc chắn giá trị cuối cùng. Nhưng cách này có một race condition quan trọng: hai transaction commit theo thứ tự khác với thứ tự chúng ghi cache.

Ví dụ:

```text
T1: commit price = 450000
T2: commit price = 420000
T2: SET cache = 420000
T1: SET cache = 450000 (callback đến muộn)
```

Database cuối cùng là 420.000 đồng, nhưng cache bị ghi lùi về 450.000 đồng. Đây là stale overwrite: callback cũ ghi đè kết quả mới hơn.

Nếu cần update cache thay vì invalidate, nên lưu version tăng đơn điệu và chỉ cho phép ghi cache khi version mới hơn version hiện có. Có thể dùng atomic compare-and-set hoặc script Lua trong Redis để so sánh version và thay đổi value trong một thao tác nguyên tử. Nếu không có cơ chế fencing/version, invalidate thường dễ suy luận hơn.

## 6. Quy tắc thời điểm: chỉ phát cache change sau commit thành công

Với transaction quản lý bởi ứng dụng, cần gắn thao tác cache vào lifecycle của transaction. Trình tự mong muốn:

```text
BEGIN
  đọc và ghi database
  tạo thông tin cần invalidate/update
COMMIT thành công
  thực hiện cache operation
```

Nếu rollback:

```text
BEGIN
  đọc và ghi database
ROLLBACK
  không công bố thay đổi đã rollback lên cache
```

Không nên gọi cache operation ngay giữa transaction chỉ vì câu UPDATE đã chạy. SQL có thể đã flush xuống database nhưng vẫn chưa commit; transaction vẫn có thể rollback.

Nếu cache operation chỉ được gọi sau khi method service trả về, vẫn phải xác định method trả về có đồng nghĩa transaction đã commit hay chưa. Với framework dùng proxy transaction, thân method có thể kết thúc trước khi transaction interceptor thực hiện commit. Callback sau commit hoặc transaction event gắn đúng phase đáng tin cậy hơn việc đặt lệnh xóa cache ngay sau `repository.save()`.

## 7. Spring: thực hiện cache operation trong AFTER_COMMIT

Spring cung cấp `TransactionSynchronization` để đăng ký callback theo vòng đời transaction. Có thể dùng `afterCommit()` để chạy sau khi transaction commit thành công.

Ví dụ:

```java
@Service
public class ProductService {
    private final ProductRepository repository;
    private final CacheManager cacheManager;

    @Transactional
    public void changePrice(long id, BigDecimal newPrice) {
        Product product = repository.findById(id)
            .orElseThrow(ProductNotFoundException::new);

        product.setPrice(newPrice);

        TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    Cache cache = cacheManager.getCache("products");
                    if (cache != null) {
                        cache.evict(id);
                    }
                }
            }
        );
    }
}
```

Callback `afterCommit()` chỉ được gọi sau khi transaction commit thành công. Nếu transaction rollback, callback này không chạy. Đoạn code minh họa việc đăng ký callback trong transaction; trong dự án thực tế cần kiểm tra transaction đang active và bảo đảm cache operation có xử lý lỗi, logging và retry phù hợp.

### Transactional event listener

Một cách khác là phát domain event trong transaction và xử lý event ở phase `AFTER_COMMIT`:

```java
public record ProductPriceChanged(long productId) {}
```

```java
@Service
public class ProductService {
    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    @Transactional
    public void changePrice(long id, BigDecimal newPrice) {
        Product product = repository.findById(id)
            .orElseThrow(ProductNotFoundException::new);

        product.setPrice(newPrice);
        events.publishEvent(new ProductPriceChanged(id));
    }
}
```

```java
@Component
public class ProductCacheListener {
    private final CacheManager cacheManager;

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onPriceChanged(ProductPriceChanged event) {
        Cache cache = cacheManager.getCache("products");
        if (cache != null) {
            cache.evict(event.productId());
        }
    }
}
```

Event được phát trong transaction, nhưng listener chỉ xử lý ở phase `AFTER_COMMIT`. Nếu transaction rollback, listener không chạy. `@TransactionalEventListener` mặc định yêu cầu có transaction; tùy chọn `fallbackExecution` có thể thay đổi hành vi khi không có transaction, nên không bật tùy tiện nếu logic yêu cầu chỉ xử lý sau commit.

### AFTER_COMMIT không làm cache và database trở thành một transaction

Callback chạy sau commit, vì vậy nếu Redis lỗi thì database vẫn đã commit. Exception từ callback không thể biến transaction đã commit thành rollback. Hãy bắt lỗi ở ranh giới phù hợp, ghi log/metric và dùng retry hoặc outbox nếu không được phép bỏ lỡ invalidation.

Nếu callback cần ghi thêm dữ liệu vào database, lưu ý transaction ban đầu đã commit. Tác vụ ghi mới cần một transaction mới phù hợp, thường là `REQUIRES_NEW`; không dựa vào transaction đã kết thúc để ghi dữ liệu bền vững.

## 8. Lưu ý với @CacheEvict và @CachePut

Spring Cache có các annotation tiện lợi:

```java
@CacheEvict(cacheNames = "products", key = "#id")
public void changePrice(long id, BigDecimal newPrice) {
    // cập nhật sản phẩm
}
```

`@CacheEvict` với `beforeInvocation = false` (mặc định) xóa cache sau khi method được gọi thành công. Nhưng “sau khi method target trả về” không tự động có nghĩa “sau khi transaction đã commit”. Thứ tự chạy giữa cache interceptor và transaction interceptor phụ thuộc cấu hình advisor/proxy order.

Nếu cache eviction phải xảy ra chính xác sau commit, hãy dùng transaction synchronization hoặc `@TransactionalEventListener(AFTER_COMMIT)`, hoặc cấu hình và kiểm thử rõ thứ tự interceptor để bảo đảm cache advice chạy sau khi transaction hoàn tất. Không nên chỉ dựa vào tên `afterInvocation` để suy ra phase transaction.

`@CachePut` cũng có vấn đề tương tự: nó cập nhật cache theo kết quả method, nhưng cần chắc chắn method đã commit thành công trước khi cache nhận giá trị mới. Nếu cache được cập nhật trước commit và transaction rollback, cache sẽ giữ dữ liệu chưa commit.

## 9. Race condition: cache miss bắt đầu trước commit, nạp dữ liệu sau invalidate

Ngay cả khi invalidate sau commit, cache-aside vẫn có một race condition tinh vi.

Giả sử cache key `product:10` đang trống hoặc vừa bị miss:

```text
Reader R                         Writer W
--------                         --------
1. GET cache -> miss
2. SELECT DB -> đọc giá cũ 500000
                                 3. UPDATE DB = 450000
                                 4. COMMIT
                                 5. DEL cache key
6. SET cache = 500000
```

Kết quả cuối: database là 450.000 đồng nhưng cache lại được nạp giá cũ 500.000 đồng. Reader đã đọc dữ liệu cũ trước commit, nhưng chỉ ghi nó vào cache sau khi writer xóa key.

Đây là lý do “xóa cache sau commit” chưa đủ để chứng minh cache luôn mới. Hệ thống cần một biện pháp bảo vệ đường nạp cache đồng thời.

### Cách xử lý bằng version hoặc generation

Mỗi bản ghi có version tăng đơn điệu. Cache lưu version cùng value. Khi reader nạp dữ liệu, nó chỉ được ghi cache nếu version của dữ liệu không cũ hơn generation/version hiện tại.

Ví dụ khái quát:

```text
Reader đọc DB: value=500000, version=7
Writer commit: value=450000, version=8
Writer tăng cache generation lên 8 hoặc ghi tombstone version 8
Reader thử SET version 7
Cache từ chối vì 7 < 8
```

Việc so sánh version và ghi cache phải là thao tác nguyên tử. Nếu reader chỉ GET generation, rồi SET cache ở hai lệnh độc lập, writer vẫn có thể thay đổi generation ở giữa hai lệnh. Redis Lua script hoặc primitive atomic tương đương có thể giúp kiểm tra và ghi trong một thao tác.

Một cách khác là dùng khóa nạp cache theo key, nhưng khóa này phải được phối hợp đúng với invalidation và có timeout/lease. Khóa nạp cache chỉ giảm các lượt load trùng nhau; nó không tự giải quyết mọi race với writer nếu thứ tự release và invalidate không được thiết kế cẩn thận.

### Invalidate hai lần (delayed double delete)

Một số hệ thống dùng kỹ thuật xóa cache ngay sau commit rồi xóa lại sau một khoảng trễ để xử lý reader đã đọc dữ liệu cũ trước lần xóa đầu. Kỹ thuật này có thể giảm xác suất stale repopulation trong một số workload, nhưng không phải bảo đảm tuyệt đối: reader có thể chậm hơn khoảng trễ, scheduler có thể trì hoãn, và nhiều writer có thể xen kẽ. Nếu cần bảo đảm mạnh hơn, dùng version/generation hoặc cơ chế tuần tự hóa nạp cache.

## 10. Outbox: bảo đảm không bỏ lỡ cache invalidation

Callback `AFTER_COMMIT` vẫn có một khoảng trống: process có thể dừng ngay sau database commit nhưng trước khi gọi Redis. Nếu invalidation bắt buộc phải được thực hiện cuối cùng, cần lưu ý định vô hiệu hóa cache một cách bền vững trong cùng transaction database.

Transactional Outbox là mẫu phù hợp:

1. Trong cùng transaction, cập nhật dữ liệu nghiệp vụ.
2. Trong cùng transaction, chèn một outbox event như `ProductChanged`.
3. Commit cả dữ liệu và event atomically.
4. Một worker đọc các event chưa xử lý và xóa cache tương ứng.
5. Sau khi cache operation thành công, worker đánh dấu event đã xử lý.
6. Nếu worker lỗi hoặc process dừng, event còn trong outbox và có thể được retry.

Ví dụ:

```sql
BEGIN;

UPDATE product
SET price = 450000,
    version = version + 1
WHERE product_id = 10;

INSERT INTO outbox_event(event_id, event_type, aggregate_id, created_at)
VALUES (:event_id, 'ProductChanged', 10, CURRENT_TIMESTAMP);

COMMIT;
```

Worker xử lý:

```text
đọc outbox event chưa xử lý
        |
        v
DEL cache key product:10
        |
        v
đánh dấu event đã xử lý
```

Nếu worker xóa cache thành công nhưng mất kết nối trước khi đánh dấu event, event có thể được xử lý lại. Vì vậy, cache invalidation nên idempotent: xóa cùng một key nhiều lần vẫn an toàn. Worker cũng cần có cơ chế claim/lease để nhiều worker không xử lý trùng quá mức và có chính sách retry/backoff cho lỗi tạm thời.

Outbox giúp không mất ý định invalidation khi process chết, nhưng không bảo đảm cache được cập nhật ngay lập tức. Trong khoảng từ commit đến khi worker xử lý event, cache có thể còn cũ. Đây là eventual consistency; nếu nghiệp vụ cần đọc sau ghi ngay lập tức, cần thêm cơ chế read-your-writes hoặc bypass cache.

## 11. Cache nhiều tầng và nhiều node

Ứng dụng có thể dùng nhiều tầng cache:

```text
Request
  |
  v
L1: local cache trong từng application instance
  |
  v
L2: Redis/shared cache
  |
  v
Database
```

Xóa key trong Redis không tự xóa bản sao đang nằm trong local cache của các instance khác. Khi dữ liệu thay đổi, hệ thống phải phát invalidation đến tất cả tầng cần cập nhật.

Một số cách thường dùng:

- Dùng Redis pub/sub hoặc message broker để thông báo các node xóa local key.
- Dùng cache có TTL ngắn cho L1 như một giới hạn thời gian stale.
- Dùng version/generation chung để mỗi node nhận ra local entry đã cũ.
- Bỏ L1 cho dữ liệu cần consistency mạnh hơn và chỉ dùng shared cache.

Pub/sub thường không lưu bền thông điệp cho subscriber đang offline. Nếu node bị ngắt kết nối trong lúc nhận invalidation, local cache có thể giữ dữ liệu cũ. Có thể xóa toàn bộ local cache khi node reconnect, dùng stream/log bền vững, hoặc dùng version/generation để phát hiện missed event.

Nếu dùng nhiều key dẫn xuất từ cùng một entity, ví dụ `product:10`, `category:5:products` và `search:keyboard`, cần xác định đầy đủ các key hoặc tag cần invalidation. Chỉ xóa key chi tiết không làm mới cache danh sách hoặc kết quả tìm kiếm đã được tính trước đó.

## 12. Read replica và cache miss

Một rủi ro khác xuất hiện khi database có read replica bất đồng bộ:

```text
Writer: commit giá 450000 trên primary
Writer: invalidate cache
Reader: cache miss
Reader: SELECT từ replica còn giá 500000
Reader: SET cache = 500000
```

Cache đã bị xóa đúng thời điểm, nhưng lần nạp lại đọc từ replica chưa bắt kịp primary nên cache được làm mới bằng dữ liệu cũ.

Các cách xử lý tùy yêu cầu:

- Đọc từ primary sau cache miss nếu cần dữ liệu mới nhất sau ghi.
- Dùng cơ chế read-your-writes hoặc sticky-to-primary cho request vừa cập nhật dữ liệu.
- Theo dõi replication position/LSN và chỉ đọc replica khi nó đã bắt kịp vị trí commit cần thiết, nếu hệ quản trị hỗ trợ.
- Lưu version trong cache và từ chối nạp phiên bản thấp hơn version tối thiểu đã biết.
- Chấp nhận eventual consistency nếu nghiệp vụ cho phép, nhưng đặt TTL và thời gian hội tụ phù hợp.

Không nên dùng một lần đọc replica trả dữ liệu cũ để kết luận transaction ghi thất bại. Primary đã commit có thể đúng trong khi replica chỉ đang trễ.

## 13. TTL: lớp bảo vệ bổ sung, không thay thế invalidation

TTL (time to live) giới hạn thời gian một cache entry tồn tại. Khi TTL hết, entry được xem là hết hạn và lần đọc sau phải nạp lại.

TTL hữu ích để:

- Giới hạn thời gian stale nếu invalidation bị bỏ lỡ.
- Tự dọn cache key không còn được sử dụng.
- Giảm rủi ro dữ liệu tồn tại vô thời hạn do bug hoặc node không nhận được event.

Nhưng TTL không bảo đảm dữ liệu mới xuất hiện ngay sau commit. Nếu TTL là 30 phút, người dùng có thể thấy dữ liệu cũ gần 30 phút khi invalidation thất bại. Với dữ liệu giá, số dư hoặc trạng thái quyền truy cập, thời gian stale như vậy có thể không chấp nhận được.

Có thể thêm jitter vào TTL để tránh nhiều key hết hạn cùng lúc và gây cache stampede. TTL cũng cần được chọn theo đặc tính dữ liệu: dữ liệu ít thay đổi có thể giữ lâu hơn, còn dữ liệu nhạy cảm với thời gian cần TTL ngắn hoặc không cache.

## 14. Cache dữ liệu bị xóa và negative caching

Cache có thể lưu cả kết quả “không tìm thấy” để tránh truy vấn database lặp lại. Đây là negative caching. Nhưng khi một entity mới được tạo, key lưu kết quả not-found phải được xóa hoặc cập nhật sau commit.

Ví dụ:

```text
GET product:99 -> cache lưu NOT_FOUND
INSERT product_id=99
COMMIT
```

Nếu không invalidate negative cache, ứng dụng vẫn trả về not found dù sản phẩm đã tồn tại. Vì vậy, event sau commit cần xử lý cả key dương và key âm.

Khi xóa một entity:

1. Xóa hàng trong database và commit.
2. Sau commit, xóa cache chi tiết và các cache danh sách có thể chứa entity đó.
3. Xóa hoặc cập nhật negative/positive cache theo quy ước.
4. Nếu thao tác cache thất bại, ghi nhận retry để dữ liệu đã xóa không tiếp tục được phục vụ từ cache quá lâu.

Đừng cache `NOT_FOUND` quá lâu nếu dữ liệu có thể được tạo ngay sau đó. Có thể dùng TTL ngắn cho negative cache và vẫn phát invalidation sau commit.

## 15. Thiết kế cache key và phạm vi invalidation

Cache key phải bao gồm mọi yếu tố làm thay đổi kết quả. Ví dụ một sản phẩm có thể được hiển thị khác nhau theo tenant, ngôn ngữ, currency hoặc quyền truy cập.

Một số dạng key:

```text
product:{tenantId}:{productId}
product-view:{tenantId}:{locale}:{productId}
category-products:{tenantId}:{categoryId}
search:{tenantId}:{normalizedQuery}:{page}
```

Nếu giá sản phẩm thay đổi, không chỉ key `product:{tenantId}:{productId}` có thể bị ảnh hưởng. Các cache view, danh sách category và kết quả tìm kiếm cũng có thể chứa giá cũ.

Có thể dùng tag hoặc index phụ để nhóm các key liên quan. Ví dụ `tag:product:10` lưu danh sách cache key phụ thuộc sản phẩm 10. Khi commit thay đổi sản phẩm, worker đọc tag và xóa các key. Nhưng tag/index phụ cũng cần được cập nhật an toàn và có thể trở thành điểm tranh chấp; thiết kế đơn giản hơn đôi khi là dùng version namespace hoặc TTL cho các cache tổng hợp.

Không đưa dữ liệu nhạy cảm hoặc quyền truy cập vào cache key theo cách dễ đoán nếu điều đó làm lộ thông tin. Với cache response theo người dùng, phải bảo đảm key phân tách đúng tenant/user/role và invalidation khi quyền thay đổi.

## 16. Cập nhật cache có version để tránh ghi lùi

Nếu hệ thống muốn update cache sau commit, hãy lưu version database cùng value:

```json
{
  "productId": 10,
  "price": 420000,
  "version": 9
}
```

Khi callback hoặc event đến, cache chỉ chấp nhận version mới hơn version đang lưu. Pseudocode:

```text
function putIfNewer(key, incoming):
    current = cache.get(key)

    if current does not exist:
        cache.set(key, incoming)
    else if incoming.version > current.version:
        cache.set(key, incoming)
    else:
        ignore incoming
```

Pseudocode này chỉ an toàn nếu đọc, so sánh và ghi được thực hiện nguyên tử. Nếu nhiều worker chạy cùng lúc, thao tác GET rồi SET riêng biệt có thể xen kẽ và ghi lùi. Hãy dùng atomic script, compare-and-set hoặc primitive transaction của cache.

Một phương án khác là invalidate thay vì update. Invalidation cũng có race với cache loader như đã mô tả, nên nếu yêu cầu consistency cao, có thể kết hợp tombstone/generation version với cache-aside.

Version cần tăng đơn điệu và không bị tái sử dụng. Nếu một bản ghi bị xóa rồi tạo lại với cùng ID và version quay về 1, cache có thể nhầm dữ liệu mới là cũ hoặc ngược lại. Có thể dùng version sequence bền vững, generation riêng hoặc ID mới.

## 17. Xử lý lỗi cache sau commit

Khi database đã commit nhưng cache operation thất bại, ứng dụng nên giữ nguyên kết quả database và xử lý cache như một công việc đồng bộ hóa chưa hoàn tất.

Các lựa chọn:

- **Retry ngay có giới hạn:** phù hợp với lỗi Redis ngắn hạn, nhưng không retry vô hạn trong request thread.
- **Đưa vào hàng đợi bền vững:** phù hợp khi invalidation không được phép mất; outbox thường là nguồn công việc.
- **Đánh dấu key/generation cần refresh:** lần đọc sau nhận biết cache cũ và nạp lại.
- **TTL làm lớp bảo vệ:** giới hạn thời gian tồn tại của entry stale trong trường hợp bỏ lỡ invalidation.
- **Fallback đọc database:** khi cache unavailable, tiếp tục phục vụ từ database nếu tải và yêu cầu độ trễ cho phép.

Không nên trả lỗi “database transaction thất bại” nếu commit đã thành công chỉ vì Redis không xóa được key. Nếu API trả lỗi và client retry một thao tác không idempotent, nghiệp vụ có thể bị thực hiện lại. Hãy phân biệt trạng thái ghi database với trạng thái cập nhật cache trong logging và phản hồi nội bộ.

## 18. Mức nhất quán cần chọn theo nghiệp vụ

Không phải mọi cache đều cần đồng bộ tức thời. Hãy xác định mức stale mà nghiệp vụ chấp nhận.

| Dữ liệu | Yêu cầu thường gặp | Cách tiếp cận gợi ý |
| --- | --- | --- |
| Ảnh đại diện, nội dung ít thay đổi | Có thể chấp nhận stale ngắn | Cache-aside, TTL, invalidate sau commit |
| Danh sách sản phẩm và mô tả | Eventual consistency ngắn có thể chấp nhận | Invalidate key/tag sau commit, outbox nếu cần độ tin cậy |
| Giá bán và tồn kho | Cần hạn chế stale vì ảnh hưởng quyết định mua | Version, invalidate sau commit, đọc primary cho luồng quan trọng; database vẫn phải kiểm tra khi đặt hàng |
| Số dư tài khoản | Không nên dựa vào cache để quyết định ghi tiền | Database là nguồn quyết định; cache chỉ phục vụ hiển thị có quy ước freshness rõ |
| Quyền truy cập và trạng thái thu hồi | Stale có thể tạo lỗ hổng quyền | Invalidate mạnh, version/generation hoặc không cache quyết định nhạy cảm |
| Kết quả báo cáo tổng hợp | Có thể chấp nhận dữ liệu trễ theo thời điểm làm mới | TTL, materialized view hoặc pipeline refresh có timestamp/version |

Cache không nên là nơi kiểm tra cuối cùng cho điều kiện nghiệp vụ quan trọng như số dư đủ tiền, còn chỗ hay quyền được phép thực hiện hành động. Những quyết định ghi cần được xác nhận lại trong database transaction hoặc một hệ thống có consistency phù hợp.

## 19. Kiểm thử thứ tự cập nhật và vô hiệu hóa cache

Kiểm thử đơn giản gọi service rồi kiểm tra cache chưa đủ để phát hiện race condition. Cần điều khiển thứ tự giữa writer và reader.

### Kiểm thử không công bố dữ liệu trước commit

1. T1 bắt đầu transaction và cập nhật giá trong database nhưng chưa commit.
2. T1 thử thực hiện cache operation.
3. T2 đọc cache trong lúc T1 chưa commit.
4. Xác nhận T2 không nhận được giá chưa commit từ cache.
5. Cho T1 rollback và xác nhận cache vẫn phản ánh giá đã commit trước đó.

### Kiểm thử invalidate sau commit

1. Khởi tạo database và cache cùng version 7.
2. T1 cập nhật database lên version 8.
3. Commit thành công rồi chạy invalidation.
4. Request tiếp theo cache miss và nạp version 8.
5. Xác nhận không có cache entry version 7 sau khi quy trình hoàn tất.

### Kiểm thử stale loader race

1. Reader R cache miss và đọc version 7 từ database.
2. Tạm dừng R trước lệnh SET cache.
3. Writer W commit version 8 và invalidate cache.
4. Cho R tiếp tục ghi version 7.
5. Xác nhận version/generation guard ngăn cache nhận lại version 7, hoặc ghi nhận giới hạn consistency nếu thiết kế chấp nhận race.

### Kiểm thử callback sau commit bị lỗi

1. Cho transaction database commit thành công.
2. Làm Redis unavailable trước callback invalidation.
3. Xác nhận dữ liệu database vẫn được commit và request không bị coi là transaction rollback.
4. Xác nhận lỗi cache được ghi nhận và outbox/retry xử lý lại sau khi Redis hoạt động.

### Kiểm thử nhiều node và replica lag

1. Nạp cùng một key vào local cache của hai application instance.
2. Cập nhật dữ liệu từ instance thứ nhất.
3. Xác nhận invalidation đến cả hai node hoặc version/generation khiến node offline tự phát hiện entry cũ khi reconnect.
4. Nếu có read replica, cố tình tạo replication lag và xác nhận cache miss không nạp lại version cũ cho luồng cần read-your-writes.

## 20. Những điểm cần ghi nhớ

- Database thường là source of truth; cache chỉ là bản sao để tăng tốc đọc.
- Không cập nhật cache bằng dữ liệu chưa commit. Nếu transaction rollback, cache không được giữ thay đổi đó.
- Với cache-aside, invalidate hoặc update cache sau khi database commit thành công.
- `AFTER_COMMIT` tránh chạy cache operation khi transaction rollback, nhưng không làm cache và database thành một transaction nguyên tử.
- `@CacheEvict` chạy sau method invocation không tự động chứng minh đã chạy sau transaction commit; cần kiểm tra thứ tự interceptor hoặc dùng transaction synchronization/event phase.
- Invalidate thường dễ suy luận hơn update, nhưng cache miss có thể nạp dữ liệu cũ nếu reader đọc trước commit rồi ghi cache sau invalidation.
- Update cache có thể ghi lùi nếu callback của transaction cũ đến sau transaction mới; dùng version và thao tác compare-and-set nguyên tử hoặc invalidate.
- Outbox lưu ý định invalidation trong cùng transaction database để process crash không làm mất công việc; worker có thể retry và thao tác xóa cần idempotent.
- Cache nhiều tầng cần invalidation trên mọi node; pub/sub không bền vững có thể bỏ lỡ thông điệp khi node offline.
- Read replica lag có thể làm cache miss nạp dữ liệu cũ; luồng read-your-writes cần đọc primary hoặc kiểm tra replication/version.
- TTL chỉ giới hạn thời gian stale, không thay thế invalidation đáng tin cậy.
- Negative cache, cache danh sách, cache tìm kiếm và cache quyền truy cập đều cần phạm vi invalidation rõ ràng.
- Cache không nên là nơi quyết định cuối cùng cho thao tác quan trọng như trừ tiền, đặt chỗ hoặc kiểm tra quyền ghi.
