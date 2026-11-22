# Spring Cache, CacheManager và @EnableCaching

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot có thể tích hợp với cơ sở dữ liệu, HTTP API, cache, broker thông điệp và các adapter của Spring Integration. Khi cùng một dữ liệu được đọc nhiều lần từ database hoặc downstream HTTP service, caching giúp giảm tải và rút ngắn độ trễ. Nhưng cache cũng tạo ra một bản sao dữ liệu có thể **cũ hơn nguồn gốc**, nên việc thiết kế phải tính đến hợp đồng dữ liệu, cập nhật, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát.

Bài học thuộc chương **Bộ nhớ đệm**, tập trung vào ba khái niệm:

- **Spring Cache:** abstraction đánh dấu các phương thức cần đọc/ghi/xóa dữ liệu cache bằng annotation.
- **`CacheManager`:** thành phần quản lý các cache theo tên; cầu nối giữa abstraction và cache provider.
- **`@EnableCaching`:** bật cơ chế xử lý cache annotation qua Spring AOP trong application context.

Sau bài này, bạn có thể thiết lập caching trong Spring Boot, lựa chọn cache provider, phân biệt hành vi của `@Cacheable`, `@CachePut`, `@CacheEvict`, thiết kế cache key, kiểm thử cache hit/miss và nhận diện giới hạn của caching trong luồng tích hợp.

## 1. Spring Cache vận hành ra sao?

Spring Cache là **abstraction ở mức gọi phương thức**, không phải một máy chủ lưu trữ và không tự quyết định thời hạn sống (TTL) của dữ liệu. Spring điều phối việc tra cứu kết quả hoặc cập nhật cache; **provider** cụ thể như Caffeine hay Redis chịu trách nhiệm lưu trữ.

Khi một bean được Spring quản lý nhận lời gọi qua **proxy**:

1. Cache interceptor phân tích annotation và xác định cache name, cache key, các điều kiện.
2. Interceptor yêu cầu `CacheManager` lấy cache theo tên; cache triển khai giao diện `org.springframework.cache.Cache`.
3. Với `@Cacheable`, nếu có phần tử phù hợp (cache hit), Spring trả kết quả đã lưu mà không gọi thân phương thức.
4. Nếu thiếu (cache miss), Spring gọi phương thức thật và, tùy điều kiện, đưa kết quả vào cache.
5. Với `@CachePut`, phương thức vẫn chạy; với `@CacheEvict`, phần tử tương ứng được xóa theo quy tắc annotation.

~~~mermaid
flowchart TD
    A["HTTP controller / use case"] --> B["Spring AOP cache proxy"]
    B --> C{"@Cacheable: key đã có?"}
    C -->|"Hit"| D["Cache provider trả bản sao"]
    D --> E["Kết quả cho caller"]
    C -->|"Miss"| F["Gọi service method"]
    F --> G["DB / downstream HTTP adapter"]
    G --> H["Lưu kết quả vào Cache"]
    H --> E
    I["CacheManager"] -.-> C
    I -.-> H
~~~

Ví dụ nghiệp vụ: `ProductQueryService.findById("P-100")` gọi một catalog HTTP API. Lần đầu phải gọi ra ngoài; lần tiếp theo có thể trả dữ liệu đã cache. Nếu sản phẩm đã được cập nhật ở nguồn nhưng cache chưa bị xóa/hết hạn, kết quả đọc lại có thể không còn mới.

**Ranh giới trách nhiệm:** cache cải thiện hiệu năng đọc; cache không phải nguồn dữ liệu chuẩn, không tự tạo ra giao dịch phân tán và không bảo đảm tính nhất quán tức thời giữa các hệ thống.

## 2. Dependency và bật `@EnableCaching`

Ví dụ Gradle (Groovy DSL) cho một Spring Boot application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

`spring-boot-starter-cache` cung cấp các dependency hỗ trợ cơ chế cache của Spring. Để sử dụng provider riêng như Caffeine, cần thêm thư viện tương ứng ở phần sau.

Khai báo cấu hình bật caching ở một `@Configuration` cụ thể:

~~~java
// CacheConfiguration.java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
}
~~~

**Vai trò của `@EnableCaching`:**

- Kích hoạt hạ tầng xử lý các annotation cache như `@Cacheable`, `@CachePut` và `@CacheEvict`.
- Trong chế độ mặc định `mode = AdviceMode.PROXY`, Spring tạo proxy để chặn các lời gọi phù hợp.
- Nếu chưa bật caching, việc thêm `@Cacheable` vào một service **không tự khiến Spring cache dữ liệu**.
- Spring Boot chỉ tự cấu hình hạ tầng cache khi cơ chế caching đã được bật và thỏa các điều kiện auto-configuration.

Nên giữ annotation này ở một cấu hình riêng thay vì gắn mặc định vào lớp `@SpringBootApplication` nếu muốn các bài test hoặc môi trường nhất định có thể chọn bật/tắt caching dễ dàng.

> **Cần nhớ:** `@EnableCaching` bật cơ chế AOP; `CacheManager` quyết định các cache cụ thể được cung cấp; annotation trên phương thức diễn tả khi nào và dùng khóa nào để cache.

## 3. CacheManager, Cache và các provider của Spring Boot

Hai giao diện quan trọng:

~~~java
// Chỉ minh họa các phương thức cốt lõi
public interface CacheManager {
    Cache getCache(String name);
    Collection<String> getCacheNames();
}
~~~

`CacheManager` không phải là dữ liệu cache; nó tìm hoặc quản lý các vùng cache có tên như `productsById`, `inventoryBySku`. Mỗi vùng cache triển khai `Cache`, có các thao tác tra cứu/ghi/xóa như `get`, `put`, `evict` và `clear` (API cụ thể có thêm những phương thức khác tùy phiên bản Spring).

Spring Boot có cơ chế nhận diện provider dựa trên classpath và cấu hình. Nếu không có provider phù hợp khác, Boot có thể dùng **Simple cache** dựa trên `ConcurrentHashMap` trong bộ nhớ tiến trình. Đó là lựa chọn dễ chạy thử, nhưng không nên xem là cấu hình production mặc định: bộ nhớ có thể tăng theo số khóa, không có TTL tự động và không chia sẻ cache giữa các instance.

| Provider | Cách lưu trữ | Trường hợp phù hợp | Điều cần kiểm soát |
| --- | --- | --- | --- |
| Simple (`ConcurrentMapCacheManager`) | Heap của một JVM | Demo, test, thử nhanh annotation | Không có TTL/giới hạn kích thước mặc định; cache riêng từng instance |
| Caffeine | Heap của một JVM, có eviction | Cache tra cứu cục bộ tốc độ cao | Cấu hình TTL/kích thước; cần xử lý stale data giữa nhiều instance |
| Redis | Kho dữ liệu cache qua mạng | Nhiều instance cần chia sẻ cache | Độ trễ mạng, kết nối, TTL, serialization, version của dữ liệu |
| JCache và các provider khác | Theo implementation JSR-107/provider | Tổ chức đã chuẩn hóa provider khác | Quy tắc eviction, cấu hình và hành vi provider |

Không nên giả định rằng mọi tính năng (TTL, atomic operation, async retrieval, distributed lock, serialization) đều được Spring Cache chuẩn hóa. Cần hiểu hành vi của provider đã chọn.

### Cấu hình Caffeine để chạy ví dụ

Thêm Caffeine vào dự án:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

Khai báo `application.yml`:

~~~yaml
spring:
  cache:
    type: caffeine
    cache-names:
      - productsById
    caffeine:
      spec: maximumSize=10000,expireAfterWrite=300s
~~~

Ý nghĩa:

- `spring.cache.type: caffeine` yêu cầu Boot chọn Caffeine khi có dependency hỗ trợ.
- `cache-names` liệt kê các vùng cache được cấu hình trước; ở ví dụ là `productsById`.
- `maximumSize=10000` giới hạn số entry theo chính sách của Caffeine; không đồng nghĩa giới hạn dung lượng bytes chính xác.
- `expireAfterWrite=300s` khiến dữ liệu hết hạn theo thời gian tính từ lần ghi; đọc lại không làm gia hạn mốc đó.

Những cấu hình này minh họa một chính sách cache đọc có thể chấp nhận tối đa khoảng vài phút dữ liệu cũ. **TTL phù hợp phải xuất phát từ yêu cầu nghiệp vụ**: giá vận chuyển có thể khác với mô tả sản phẩm; số dư tài khoản hoặc quyết định cấp quyền đòi hỏi mức nhất quán cao hơn nhiều.

Nếu tự khai báo bean `CacheManager`, cấu hình do Boot tự tạo có thể nhường chỗ cho bean đó; khi ấy phải tự chịu trách nhiệm cấu hình toàn bộ provider. Không cần tự khai báo `CacheManager` nếu auto-configuration của Boot đã đáp ứng được.

### Chủ động xác định provider ở môi trường khác

Để tắt lưu cache thật trong một bài test nhưng vẫn cho phép code dùng annotation:

~~~yaml
spring:
  cache:
    type: none
~~~

Giá trị `none` sử dụng no-op cache manager, nên mỗi lần gọi đều thực thi phương thức thực. Lưu ý kiểm thử cache hit/miss phải chạy với provider thật hoặc giả lập có lưu dữ liệu; đặt `type: none` sẽ không kiểm chứng được caching.

## 4. Một ví dụ đầy đủ: cache kết quả đọc từ HTTP adapter

Giả sử Catalog API cung cấp thông tin sản phẩm. Application cần tránh gọi HTTP lặp lại cho cùng ID trong một thời gian ngắn.

Định nghĩa hợp đồng dữ liệu và cổng truy xuất:

~~~java
// ProductView.java
public record ProductView(
        String id,
        String name,
        long version) {
}
~~~

~~~java
// ProductGateway.java
public interface ProductGateway {
    ProductView fetchById(String productId);
}
~~~

`ProductGateway` có thể được triển khai bởi REST client, database repository hoặc một adapter tích hợp phù hợp; bài này tập trung vào **service có kết quả được cache**, không phụ thuộc chi tiết thư viện HTTP.

~~~java
// ProductQueryService.java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final ProductGateway gateway;

    public ProductQueryService(ProductGateway gateway) {
        this.gateway = gateway;
    }

    @Cacheable(
            cacheNames = "productsById",
            key = "#p0",
            unless = "#result == null")
    public ProductView findById(String productId) {
        return gateway.fetchById(productId);
    }
}
~~~

Phân tích:

- `cacheNames = "productsById"` chọn vùng cache, tương ứng tên đã cấu hình.
- `key = "#p0"` sử dụng đối số đầu tiên làm khóa. Có thể viết `#productId` khi tên tham số được giữ trong bytecode và Spring truy xuất được metadata.
- `unless = "#result == null"` không lưu kết quả `null`, tránh giữ mãi một lần tra cứu chưa thấy dữ liệu.
- Khi `gateway.fetchById(...)` phát sinh exception, lời gọi không có kết quả thành công để đưa vào cache theo cơ chế mặc định.
- Spring chỉ chặn lời gọi đi **qua proxy**; hai lần gọi phương thức từ bean khác tới `ProductQueryService` mới cho thấy caching hoạt động.

Ví dụ hai lần gọi liên tiếp trong TTL:

~~~java
ProductView first = productQueryService.findById("P-100");  // Miss: gọi gateway
ProductView second = productQueryService.findById("P-100"); // Hit: dùng cache
~~~

Nếu phía HTTP trả 404, adapter cần quyết định có biến thành `null`, một đối tượng “không tồn tại” rõ ràng hay exception nghiệp vụ. Không tự mặc định cache kết quả lỗi chỉ vì muốn giảm số lời gọi đến downstream: **negative caching** đòi hỏi TTL và chính sách riêng, tránh che đi dữ liệu mới xuất hiện sau đó.

### Thiết kế theo lớp thay vì gắn cache khắp nơi

Một hệ thống tích hợp dễ bảo trì có thể dùng sơ đồ:

~~~mermaid
flowchart LR
    A["ProductController"] --> B["ProductQueryService (@Cacheable)"]
    B --> C["ProductGateway (contract)"]
    C --> D["HTTP / DB adapter"]
    B -.-> E["CacheManager"]
    E -.-> F["Caffeine / Redis"]
~~~

Đặt `@Cacheable` ở **biên truy vấn ổn định về ý nghĩa nghiệp vụ** giúp phần còn lại của ứng dụng không phải biết provider đang dùng. Tránh cache dữ liệu phụ thuộc request identity, quyền truy cập hoặc tenant bằng một khóa chỉ chứa `productId`.

## 5. Phân biệt các annotation caching

| Annotation | Có gọi thân phương thức? | Tác động đến cache | Tình huống |
| --- | --- | --- | --- |
| `@Cacheable` | Không nếu hit; có nếu miss | Ghi kết quả khi miss và phù hợp điều kiện | Đọc dữ liệu tốn chi phí |
| `@CachePut` | **Luôn gọi** | Ghi/cập nhật kết quả sau khi phương thức chạy thành công | Cập nhật một phần tử cache theo kết quả vừa lưu |
| `@CacheEvict` | Thường có; hành động xóa được áp dụng theo thời điểm quy định | Xóa một key hoặc cả vùng | Bỏ bản sao cũ khi dữ liệu nguồn thay đổi |
| `@Caching` | Theo các annotation lồng bên trong | Kết hợp nhiều tác động cache | Một thay đổi ảnh hưởng nhiều vùng cache |
| `@CacheConfig` | Không kích hoạt cache khi đứng riêng | Đặt mặc định cache name/key generator/manager ở cấp lớp | Giảm lặp cấu hình |

### Xóa cache sau khi cập nhật dữ liệu

Giả sử command service thực hiện thay đổi sản phẩm và caller cần đọc dữ liệu mới:

~~~java
// ProductCommandService.java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;

@Service
public class ProductCommandService {

    private final ProductStore store;

    public ProductCommandService(ProductStore store) {
        this.store = store;
    }

    @CacheEvict(cacheNames = "productsById", key = "#p0")
    public void updateName(String id, String newName) {
        store.updateName(id, newName);
    }
}
~~~

`ProductStore` là một interface adapter lưu dữ liệu được giả định có phương thức `updateName`. Trong mô hình đồng bộ thông thường, `@CacheEvict` mặc định chạy **sau khi phương thức trả về thành công**. Nếu phương thức ném exception, eviction mặc định không thực hiện. Với `beforeInvocation = true`, việc xóa diễn ra trước khi chạy thân phương thức, kể cả thao tác cập nhật thất bại — chỉ dùng khi thực sự cần hành vi đó.

**Điều rất quan trọng về giao dịch:** nếu `updateName` tham gia giao dịch database, thời điểm phương thức trả về **không nhất thiết là thời điểm transaction đã commit**. Một eviction xảy ra trước commit có thể cho phép một reader nạp lại dữ liệu cũ vào cache. Với nghiệp vụ yêu cầu nhất quán, hãy thiết kế invalidation sau commit, hoặc dùng cache transaction-aware phù hợp và kiểm thử rõ thứ tự advice/transaction. Nếu việc cập nhật diễn ra ở hệ thống bên ngoài qua HTTP, `@Transactional` của database tại chỗ không khiến thao tác remote tham gia cùng một giao dịch ACID.

### Ghi kết quả mới bằng `@CachePut`

Nếu phương thức cập nhật trả về chính bản dữ liệu mới và hợp đồng đảm bảo bản đó là dạng dùng cho truy vấn, có thể ghi cache:

~~~java
@CachePut(cacheNames = "productsById", key = "#p0")
public ProductView updateProduct(String id, UpdateProductCommand command) {
    return store.saveAndReturn(id, command);
}
~~~

Ví dụ rút gọn trên giả định `store.saveAndReturn(...)` trả `ProductView` đã lưu thành công. Cũng phải kiểm tra ranh giới commit và tác động của các reader đồng thời. Không gắn `@Cacheable` và `@CachePut` cùng một phương thức rồi kỳ vọng “vừa tránh gọi phương thức vừa luôn thực thi”: hai annotation có mục đích khác nhau và kết hợp trực tiếp thường khó xác định đúng hành vi.

### Xóa cả vùng cache

~~~java
@CacheEvict(cacheNames = "productsById", allEntries = true)
public void refreshEntireCatalog() {
    catalogSynchronizer.refresh();
}
~~~

`allEntries = true` bỏ qua key và ảnh hưởng mọi entry của vùng đã chọn. Đây là biện pháp tốn kém nếu nhiều request cùng miss ngay sau khi xóa. Chỉ dùng khi một sự kiện thực sự làm thay đổi toàn bộ dataset, hoặc có phương án chống tải tăng đột biến.

## 6. Thiết kế cache key, điều kiện và chống trùng tải

### Quy tắc tạo key

Nếu không chỉ định `key`, Spring Cache dùng cơ chế tạo khóa mặc định dựa trên các tham số: không có tham số → `SimpleKey.EMPTY`; một tham số → chính đối tượng đó; nhiều tham số → `SimpleKey` tổng hợp. Quy tắc này tiện lợi, nhưng **khóa đúng về kỹ thuật chưa chắc đúng về nghiệp vụ**.

| Tình huống | Khóa gợi ý | Rủi ro nếu thiếu thông tin |
| --- | --- | --- |
| Sản phẩm công khai theo ID | `productId` | Ít rủi ro nếu dữ liệu thực sự toàn cục |
| Sản phẩm theo tenant | `tenantId + ":" + productId` | Trả nhầm dữ liệu giữa các tenant |
| Giá theo đơn vị tiền tệ | `productId + ":" + currency` | Trả sai đơn vị hoặc giá |
| Dữ liệu tùy quyền xem | Cache tách theo vai trò/người dùng hoặc không cache | Rò rỉ dữ liệu nhạy cảm |
| API có phân trang | `filter + sort + page + size` có dạng canonical | Trùng key hoặc trả sai trang |

Ví dụ khóa theo tenant:

~~~java
@Cacheable(
        cacheNames = "tenantProducts",
        key = "#p0 + ':' + #p1")
public ProductView findForTenant(String tenantId, String productId) {
    return gateway.fetchForTenant(tenantId, productId);
}
~~~

Tham số tenant phải được hệ thống xác thực/ủy quyền xác định đáng tin cậy. Với khóa phức tạp, hoặc khi phân cách chuỗi có thể gây đụng độ, hãy dùng giá trị object key bất biến hoặc một `KeyGenerator` có cấu trúc. Nếu provider là Redis, kiểm tra serializer của key để tránh cấu trúc khó đọc hoặc thiếu tính ổn định sau khi deploy phiên bản mới.

### `condition`, `unless` và `sync`

- `condition` quyết định **trước khi gọi phương thức** có áp dụng caching hay không, dựa vào đối số.
- `unless` quyết định **sau khi có kết quả** có từ chối ghi kết quả vào cache hay không.
- `sync = true` yêu cầu đồng bộ quá trình nạp giá trị cho cùng key trong các trường hợp provider hỗ trợ, nhằm hạn chế nhiều thread tính cùng một kết quả khi cache miss đồng thời.

Ví dụ không cache request tìm kiếm quá rộng:

~~~java
@Cacheable(
        cacheNames = "productsById",
        key = "#p0",
        condition = "#p0 != null && !#p0.isBlank()",
        unless = "#result == null")
public ProductView findById(String productId) {
    return gateway.fetchById(productId);
}
~~~

Nếu ứng dụng có nhu cầu tránh nhiều luồng cùng nạp một key, có thể dùng:

~~~java
@Cacheable(cacheNames = "productsById", key = "#p0", sync = true)
public ProductView findByIdSingleFlight(String productId) {
    return gateway.fetchById(productId);
}
~~~

**Giới hạn:** hỗ trợ đồng bộ phụ thuộc `Cache`/provider và không tương đương distributed lock trên toàn cụm. Với `sync = true`, Spring Cache có giới hạn như không hỗ trợ `unless` và chỉ sử dụng một cache; không sao chép kết hợp `sync = true` với mọi tùy chọn của ví dụ khác. Việc hạn chế “cache stampede” trong một hệ thống nhiều instance còn có thể cần TTL có jitter, cơ chế single-flight/distributed coordination hoặc prewarming theo nhu cầu thực tế.

## 7. Độ nhất quán, TTL, lỗi và xử lý trùng lặp trong tích hợp

### Cache-aside và dữ liệu cũ

`@Cacheable` theo kiểu đọc nếu thiếu rồi điền cache gần với mẫu **cache-aside**:

1. Đọc từ cache nếu có.
2. Nếu miss, gọi adapter tới nguồn dữ liệu.
3. Ghi kết quả và trả cho caller.
4. Khi nguồn thay đổi, phải chủ động invalidate/update hoặc chờ TTL.

TTL là **chính sách giới hạn độ cũ thông thường**, không phải bảo đảm rằng ngay khi nguồn đổi mọi reader nhìn thấy giá trị mới. Đặc biệt trong nhiều instance có cache cục bộ, mỗi instance có vòng đời dữ liệu khác nhau.

### Cập nhật ở ngoài ứng dụng

Nếu một hệ thống khác cũng sửa dữ liệu trong database/remote service, `@CacheEvict` trên command service của ứng dụng hiện tại sẽ **không được kích hoạt**. Cần lựa chọn bổ sung:

- TTL ngắn nếu nghiệp vụ chấp nhận dữ liệu có thể cũ.
- Sự kiện `ProductUpdated(productId, version)` qua broker để các consumer xóa/cập nhật cache liên quan.
- CDC/outbox hoặc đồng bộ dựa trên version nếu cần giảm nguy cơ mất sự kiện.
- Provider cache chung (ví dụ Redis) giúp nhiều instance cùng thấy một vùng cache, nhưng vẫn cần quy tắc invalidate phù hợp.

Sự kiện từ broker có thể bị gửi trùng, tới muộn hoặc đảo thứ tự. Xóa cùng key lặp lại thường an toàn, còn ghi dữ liệu từ sự kiện cần so sánh version/timestamp đáng tin cậy để tránh một sự kiện cũ ghi đè bản mới.

### Cache không thay thế idempotency

Giữ một giá trị trong cache có thể giảm số lời gọi đọc HTTP, nhưng không phải cơ chế **idempotency** cho tạo đơn hàng/thanh toán. Cache entry có thể hết hạn, bị evict, mất khi restart hoặc không đồng bộ giữa instance. Với request ghi có yêu cầu “xử lý đúng một lần theo khóa nghiệp vụ”, cần thiết kế idempotency key, unique constraint và quy trình xử lý trùng lặp tại hệ thống sở hữu dữ liệu.

### Lỗi provider phải được coi là một nhánh thiết kế

Mặc định, lỗi phát sinh từ thao tác cache có thể lan ra caller. Khi cache Redis không sẵn sàng, hệ thống phải quyết định có cho phép đọc trực tiếp từ nguồn hay không. Một `CacheErrorHandler` tùy biến có thể nuốt một số lỗi cache để cho phép fallback, nhưng làm như vậy có thể tăng tải đột biến cho downstream và không phù hợp với dữ liệu dùng cache như điều kiện an toàn.

Không âm thầm “bỏ qua mọi lỗi cache” trên luồng quan trọng. Cần kiểm soát timeout phía provider, giới hạn tải, circuit breaker/rate limit theo nhu cầu, log có cấu trúc và cảnh báo cho hit/miss/error. Tránh ghi dữ liệu nhạy cảm trong cache key và metric label.

## 8. Giới hạn của AOP: các trường hợp annotation không có hiệu lực

### Self-invocation

Ví dụ thường gây nhầm lẫn:

~~~java
@Service
public class ProductFacade {

    public ProductView lookup(String id) {
        return findById(id); // gọi nội bộ qua this, không đi qua cache proxy
    }

    @Cacheable(cacheNames = "productsById", key = "#p0")
    public ProductView findById(String id) {
        return slowLoad(id);
    }

    private ProductView slowLoad(String id) {
        // ...
        throw new UnsupportedOperationException("Minh họa");
    }
}
~~~

Khi `lookup()` gọi `findById()` trên chính đối tượng, lời gọi thường bỏ qua proxy, nên annotation ở `findById` không được xử lý. Đặt phương thức cache trong một bean service khác và gọi qua bean do Spring tiêm; đừng chữa bằng cách gọi proxy của chính mình nếu không thật sự cần.

Các trường hợp cần kiểm tra thêm:

- Phương thức của đối tượng tạo bằng `new` ngoài Spring container không được AOP quản lý.
- Phương thức `private`, hoặc lời gọi nội bộ tới phương thức được annotate, không hoạt động như phương thức public gọi qua proxy.
- Annotation trong giai đoạn khởi tạo như `@PostConstruct` chưa chắc có proxy sẵn để sử dụng.
- Với Java/Kotlin và loại proxy khác nhau, `final` method/class có thể cản trở interception; cần xem cấu hình proxy của dự án.
- Caching và `@Transactional` đều có thể dựa trên AOP; thứ tự advice và timing commit cần được kiểm thử trong luồng cập nhật.

**Cách xác minh nhanh:** instrument adapter/fake gateway bằng bộ đếm; gọi phương thức qua bean đã inject nhiều lần. Nếu bộ đếm vẫn tăng sau khi cùng một key được gọi lại, kiểm tra `@EnableCaching`, proxy, key, điều kiện `unless` và provider.

## 9. Kiểm thử hành vi caching

Không đủ nếu chỉ thấy ứng dụng khởi động và `CacheManager` có bean. Kiểm thử nên xác minh đúng **lời gọi phương thức thực có bị bỏ qua hay không** và **dữ liệu có được invalidation sau thay đổi không**.

### Những kịch bản chính

| Kịch bản | Cách kiểm chứng |
| --- | --- |
| Cache miss rồi hit | Gọi hai lần cùng ID qua service bean; fake gateway được gọi một lần |
| Key khác nhau | Gọi ID khác; fake gateway chạy thêm lần tương ứng |
| Evict sau update thành công | Gọi truy vấn, cập nhật qua command bean, gọi lại; truy vấn phải nạp dữ liệu mới |
| Update thất bại | Giả lập store ném exception; xác minh chính sách không xóa/ghi sai cache |
| TTL hết hạn | Dùng provider có TTL ngắn hoặc fake clock; sau hết hạn phải nạp lại |
| Nhiều tenant | Cùng productId nhưng khác tenantId không dùng chung kết quả |
| Provider mất kết nối | Đảm bảo fallback/failure mode khớp hợp đồng tích hợp |
| Giao dịch đồng thời | Kiểm tra invalidation xảy ra vào thời điểm mong muốn so với commit |

Ví dụ phần assertion trong một `@SpringBootTest` với caching được bật và `ProductGateway` giả có bộ đếm:

~~~java
@Test
void sameProductIsLoadedOnlyOnce() {
    ProductView first = productQueryService.findById("P-100");
    ProductView second = productQueryService.findById("P-100");

    assertEquals(first, second);
    assertEquals(1, countingProductGateway.callsFor("P-100"));
}
~~~

Test trên giả định đã có import JUnit và fixture `countingProductGateway` được Spring tiêm như `ProductGateway`; việc gọi service cần đi qua bean do Spring cung cấp. Đừng gọi `new ProductQueryService(fakeGateway)` để kiểm tra AOP, vì đối tượng đó không được Spring tạo proxy. Cũng cần xóa/reset cache giữa các test nếu dùng chung `ApplicationContext`, tránh kết quả phụ thuộc thứ tự thực thi.

### Đảm bảo test dùng đúng loại cache

- Unit test cho logic map/DTO của adapter không cần Spring cache.
- Integration test cho annotation cần `@EnableCaching` và một `CacheManager` thực sự lưu dữ liệu.
- Contract test cho API ngoài cần HTTP stub riêng, đo cả request count để thấy cache thực sự giảm số lần gọi adapter.
- Test liên quan Redis/transaction phải phản ánh điều kiện thực tế của provider và nhiều instance nếu đây là một yêu cầu chất lượng.

## 10. Quan sát và vận hành

Cache chỉ hữu ích khi biết được hiệu quả và rủi ro. Với Actuator/Micrometer và provider được instrument tương ứng, có thể theo dõi các chỉ số như số cache hit, miss, entry count, eviction, thời gian tải từ nguồn, lỗi backend và độ trễ p95/p99. Tên metric và khả năng xuất hiện phụ thuộc phiên bản Spring Boot/provider, nên xác minh trên môi trường chạy thực.

Gợi ý đặt mục tiêu:

| Chỉ số | Câu hỏi vận hành |
| --- | --- |
| Hit ratio | Có giảm thực sự lượng request tới HTTP/DB downstream không? |
| Miss rate theo cache | Dữ liệu đang churn, khóa quá phân mảnh hay TTL quá ngắn? |
| Eviction count/size | Cache đang bị giới hạn bộ nhớ quá mạnh hay có entry không còn sử dụng? |
| Downstream request rate | Sau khi bật caching, tổng tải vào nguồn có giảm không? |
| Tỷ lệ stale data | Tác động chậm cập nhật có vượt SLA nghiệp vụ không? |
| Cache backend error | Redis/provider có tạo thêm điểm lỗi mới cho luồng tích hợp không? |

`/actuator/caches` có thể cho biết những cache đang được quản lý khi endpoint tương ứng được bật và cho phép truy cập; không nên suy diễn rằng endpoint này trả toàn bộ dữ liệu cache. Không public endpoint quản trị cache một cách tùy tiện. Tên cache và metric tag phải có cardinality kiểm soát được, tránh đưa product ID, tenant ID hoặc thông tin cá nhân trực tiếp thành label.

## 11. Khi nào dùng Spring Cache, khi nào không?

**Nên cân nhắc Spring Cache** khi phương thức đọc lặp lại nhiều, đầu vào tạo khóa rõ ràng, kết quả có thể tái sử dụng và nghiệp vụ chấp nhận một khoảng dữ liệu cũ có kiểm soát. Các ví dụ gồm catalog ít thay đổi, metadata cấu hình theo version, tỷ giá có thời hạn rõ, hoặc bảng tra cứu tĩnh.

**Không nên áp dụng tùy tiện** cho các thao tác ghi, kết quả phụ thuộc ngữ cảnh bảo mật khó thể hiện bằng key, dữ liệu có tính nhất quán tức thời cao, luồng streaming lớn hay những lời gọi có side effect. Với luồng trả `Mono`/`Flux`, cần kiểm tra riêng hỗ trợ caching bất đồng bộ của phiên bản Spring Framework/provider: kể từ Spring Framework 6.1 có cơ chế thích ứng cho `CompletableFuture` và kiểu reactive, nhưng không phải mọi provider đều hỗ trợ retrieval bất đồng bộ giống nhau. Với `Flux`, kết quả có thể được gom thành danh sách để cache, không phù hợp với luồng vô hạn hoặc rất lớn. Nếu caching reactive là yêu cầu trọng tâm, cần kiểm thử end-to-end thay vì giả định annotation chỉ lưu publisher nguyên trạng.

## 12. Checklist trước khi triển khai

- [ ] `@EnableCaching` được đặt ở cấu hình đúng scope, service được gọi qua Spring proxy.
- [ ] Đã chọn provider phù hợp: Simple để thử nghiệm, Caffeine cho local cache, Redis nếu cần cache chia sẻ.
- [ ] Có cache name/key phân biệt tenant, locale, currency hoặc các điều kiện làm thay đổi kết quả.
- [ ] Có kích thước và TTL phù hợp, dựa trên giới hạn dữ liệu cũ nghiệp vụ cho phép.
- [ ] Đã xác định rõ phương thức nào `@Cacheable`, khi nào `@CacheEvict` hoặc `@CachePut`.
- [ ] Đã xét tới transaction commit, cập nhật từ hệ thống khác, sự kiện đến muộn và xử lý trùng lặp.
- [ ] Đã kiểm thử hit/miss, key khác nhau, invalidation, timeout/lỗi provider và ranh giới nhiều instance khi cần.
- [ ] Có chỉ số vận hành, giám sát downstream và chính sách xử lý cache outage.

**Kết luận kỹ thuật:** `@EnableCaching` kích hoạt cơ chế, `CacheManager` cung cấp vùng lưu trữ và `@Cacheable`/`@CachePut`/`@CacheEvict` mô tả hành vi ở ranh giới phương thức. Chất lượng một tích hợp Spring Boot phụ thuộc nhiều hơn vào **cache key, TTL, thời điểm invalidation và hợp đồng dữ liệu** so với việc chỉ thêm annotation.

## Tài liệu tham khảo

- [Spring Boot Reference — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html): auto-configuration, cache provider, Caffeine và cấu hình `spring.cache.*`.
- [Spring Framework Reference — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): tổng quan mô hình cache và các giao diện.
- [Spring Framework Reference — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, cache key, proxy/self-invocation và hành vi reactive.
