# Cache và hợp đồng thao tác trên từng vùng dữ liệu trong Spring Framework

## 1. Vấn đề cần giải quyết

Khi một chức năng phải đọc dữ liệu tốn thời gian (cơ sở dữ liệu, dịch vụ bên ngoài, phép tính nặng), cache giúp tái sử dụng kết quả cho những lần gọi tương đương. Tuy nhiên, câu hỏi kiến trúc quan trọng không chỉ là “có cache hay không” mà còn là: **dữ liệu nào thuộc vùng cache nào, khóa nào đại diện cho một kết quả, lúc nào được đọc/ghi/xóa và ai chịu trách nhiệm giữ dữ liệu đúng sau khi nguồn thay đổi?**

Trong Spring Framework, mỗi **vùng cache (cache region)** được truy cập bằng một tên logic, chẳng hạn `products`, `productPrices` hay `categorySummary`. Vùng này không phải vùng heap/JVM: nó là một không gian ánh xạ `key → value` do một `Cache` cụ thể quản lý. Cache provider quyết định nơi lưu vật lý (bộ nhớ trong tiến trình, bộ nhớ phân tán...), tuổi thọ, khả năng đồng bộ và chính sách loại bỏ dữ liệu.

Mục tiêu sau bài học:

- Phân biệt `CacheManager`, một `Cache`/region và từng entry theo key.
- Hiểu hợp đồng của thao tác đọc, nạp khi thiếu, ghi đè, xóa một key và làm trống toàn vùng.
- Ánh xạ hợp đồng đó sang `@Cacheable`, `@CachePut`, `@CacheEvict` và quản lý vòng đời dữ liệu.
- Thiết kế key, invalidation, concurrency và ranh giới giao dịch để tránh trả kết quả cũ hoặc chồng lẫn dữ liệu.

## 2. Mô hình vùng dữ liệu và đường đi của một request

```text
Client → Spring bean proxy / CacheInterceptor
               │
               ├─ Resolve cache name / CacheManager / CacheResolver
               ├─ Tính key (KeyGenerator hoặc biểu thức SpEL)
               └─ Cache("products") ── key "P1" ──> Product(P1, "Bút")
                       │ miss
                       └─ Gọi phương thức thật → nguồn dữ liệu → ghi kết quả → trả về
```

Ví dụ cùng key `"P1"` nhưng khác region:

| Vùng | Key | Ý nghĩa value |
| --- | --- | --- |
| `products` | `"P1"` | Thông tin sản phẩm |
| `productPrices` | `"P1"` | Giá bán đã tính |
| `productStock` | `"P1"` | Tồn kho hoặc snapshot tồn kho |

Xóa `"P1"` trong `products` **không tự xóa** entry tương ứng ở hai vùng còn lại. Hai vùng có tên khác nhau là hai không gian logic; điều này không tự hứa hẹn hai bộ lưu trữ vật lý độc lập. Một cập nhật nguồn có thể khiến nhiều region mất hiệu lực cùng lúc, vì vậy quan hệ phụ thuộc dữ liệu phải được mô tả rõ.

Kiến trúc gồm hai hợp đồng bổ sung nhau:

1. **Hợp đồng truy cập:** cùng một tên region và cách tạo key phải dẫn đến đúng kiểu dữ liệu mong đợi; các thao tác có ngữ nghĩa rõ ràng.
2. **Hợp đồng nhất quán:** khi dữ liệu gốc được tạo/sửa/xóa, chương trình phải cập nhật hoặc vô hiệu hóa mọi cache chịu ảnh hưởng; TTL chỉ là lớp phòng vệ bổ sung, không mặc nhiên thay thế việc làm mới dữ liệu.

Cache là bản sao có thể tái tạo, **không phải nguồn sự thật**. Dữ liệu nghiệp vụ phải được lưu ở nơi có hợp đồng bền vững riêng, như database.

## 3. Hai interface cốt lõi

`org.springframework.cache.CacheManager` cung cấp `getCache(String name)` và `getCacheNames()`. `getCache(name)` trả một `Cache` tương ứng hoặc `null` nếu không có region đó; việc tự tạo vùng mới theo tên hay chỉ chấp nhận tên đã khai báo tùy implementation/cấu hình. `CacheManager` không phải bản thân kho chứa từng entry.

`org.springframework.cache.Cache` là hợp đồng thao tác **trong đúng một vùng**:

| API | Hợp đồng đáng nhớ |
| --- | --- |
| `get(key)` | Trả `Cache.ValueWrapper` nếu có mapping, hoặc `null` nếu miss. Wrapper có thể chứa value `null`, nên phân biệt được “đã cache null” với “chưa có entry”. |
| `get(key, Type.class)` | Lấy giá trị theo kiểu; kết quả `null` không phân biệt được cached-null và miss. Kiểu không khớp có thể gây lỗi. |
| `get(key, Callable<T> loader)` | Khi thiếu, gọi loader và lưu kết quả; provider có thể đồng bộ việc nạp cùng key, nhưng cần kiểm tra khả năng thực tế của backend. |
| `put(key, value)` | Gắn/thay thế mapping trong region; hiệu lực có thể bị trì hoãn với decorator hoặc backend bất đồng bộ. |
| `putIfAbsent(key, value)` | Chỉ thêm khi chưa có mapping; mong muốn thao tác nguyên tử, nhưng phải kiểm tra bảo đảm của provider cụ thể. |
| `evict(key)` | Loại bỏ mapping của đúng key; có thể được thực hiện trễ. |
| `evictIfPresent(key)` | Yêu cầu loại bỏ sao cho tra cứu tiếp theo không thấy entry ngay; `boolean` cho biết trước đó có mapping hay không khi có thể xác định. |
| `clear()` | Làm trống **toàn bộ region**, có thể có độ trễ. |
| `invalidate()` | Yêu cầu mọi entry của region lập tức không còn nhìn thấy; trả thông tin có từng chứa entry hay không khi có thể xác định. |
| `getName()`, `getNativeCache()` | Xem tên logic và đối tượng provider nền. |

Các từ “ngay” hay “nguyên tử” ở trên là kỳ vọng trong hợp đồng API; backend, transaction decorator và cấu hình triển khai quyết định mức bảo đảm thực tế. Không được suy ra rằng `put`, `evict`, `clear` là giao dịch nguyên tử với database. Spring Cache cũng có các biến thể `retrieve(...)` dựa trên `CompletableFuture` cho cache hỗ trợ truy cập bất đồng bộ (Spring Framework 6.1+).

Đọc trực tiếp bằng Java khi thật sự cần thao tác programmatic:

```java
Cache products = cacheManager.getCache("products");
if (products == null) {
    throw new IllegalStateException("Missing cache region: products");
}

Cache.ValueWrapper entry = products.get("P1");
if (entry == null) {
    // Chưa có key P1 (cache miss).
} else {
    Object value = entry.get(); // Có thể null: đây vẫn là một cache hit.
}

products.evict("P1"); // Chỉ entry P1 trong region products.
products.clear();     // Mọi entry của region products.
```

Đoạn trên là minh họa trong ngữ cảnh đã có biến `cacheManager`, không phải một file Java chạy độc lập.

## 4. Hợp đồng thiết kế cho từng region

Trước khi thêm annotation, hãy trả lời đủ các câu hỏi sau cho **mỗi vùng**.

| Thuộc tính | Cần quyết định | Ví dụ |
| --- | --- | --- |
| Tên và mục đích | Region biểu diễn dữ liệu nào, ai sở hữu? | `products` chỉ chứa `Product` theo SKU |
| Key | Các tham số nào khiến kết quả khác nhau? | `tenantId + ":" + sku` nếu dữ liệu theo tenant |
| Value | Kiểu, độ bất biến, mức có thể chia sẻ | `Product` immutable/record thay vì entity mutable |
| Nguồn sự thật | Kết quả xuất phát từ đâu? | Bảng `products` trong database |
| Đọc và nạp | Đọc trượt (miss) thì làm gì? | Query database, lưu khi thành công |
| Cập nhật | Write-through bằng `@CachePut` hay evict để lần sau tải lại? | Save database rồi put entry mới |
| Xóa và làm trống | Key nào bị ảnh hưởng, có cần nhiều vùng? | Sửa giá cũng evict `productPrices` |
| Hết hạn/dung lượng | TTL, max size, eviction policy ở đâu? | Caffeine/Redis config, không nằm ở `Cache` API chung |
| Độ nhất quán | Chấp nhận stale bao lâu? Có nhiều node? | Dữ liệu giá nhạy hơn catalog |
| Quan sát và lỗi | Đo hit/miss, eviction, latency, lỗi backend ra sao? | Metrics theo region, cảnh báo miss tăng |

**Key phải ổn định, đầy đủ và đúng phạm vi dữ liệu.** Nếu kết quả phụ thuộc vào user, tenant, ngôn ngữ, filter, phiên bản hoặc quyền truy cập, thiếu thành phần đó trong key có thể gây trả nhầm dữ liệu. Đừng dùng mỗi tên method hay một tham số nếu những yếu tố khác cũng ảnh hưởng tới kết quả. Đối với nhiều tham số, mặc định Spring dùng `SimpleKeyGenerator`; muốn định dạng chia sẻ hoặc thống nhất giữa các method thì khai báo key rõ ràng hoặc `KeyGenerator` dùng chung.

Không ép hai kiểu dữ liệu không tương thích vào cùng region/key. Tránh lưu đối tượng có thể bị thay đổi tại chỗ: cache bản sao mutable rồi sửa trực tiếp có thể làm thay đổi kết quả quan sát được ngay cả khi không gọi `put`. Dùng DTO/record bất biến hoặc sao chép/serialize có chủ đích.

## 5. Hợp đồng annotation: đọc, ghi, xóa trên một vùng

| Annotation | Có chạy method thật không? | Tác động cache |
| --- | --- | --- |
| `@Cacheable(cacheNames="products", key="#p0")` | Miss: có; hit: thông thường không | Hit trả dữ liệu cache; miss chạy method và cache kết quả |
| `@CachePut(cacheNames="products", key="#p0.sku()")` | **Luôn chạy** | Sau khi method thành công, đưa kết quả trả về vào cache |
| `@CacheEvict(cacheNames="products", key="#p0")` | Có | Mặc định xóa một entry **sau** khi method hoàn tất thành công |
| `@CacheEvict(cacheNames="products", allEntries=true)` | Có | Xóa mọi entry của một region, bỏ qua key |
| `@Caching(evict={...})` | Theo các annotation bên trong | Gom các thao tác, ví dụ evict đồng thời hai region |
| `@CacheConfig(cacheNames="products")` | Chỉ đặt cấu hình chung ở lớp | Giảm lặp tên region/key generator/manager; tự nó không cache |

Các thuộc tính cần đọc cẩn thận:

- `cacheNames` (tương đương `value`) xác định tên region; có thể khai báo nhiều nhưng không nên xem việc ghi nhiều vùng là một giao dịch.
- `key` là biểu thức SpEL. `#p0` là tham số đầu tiên, không phụ thuộc việc biên dịch có lưu tên tham số; `#result` có thể dùng ở nơi được Spring hỗ trợ **sau** lời gọi (ví dụ `unless`, key của `@CachePut`).
- `condition` được đánh giá trước để quyết định có áp dụng caching hay không; `unless` được đánh giá sau khi method chạy để từ chối lưu kết quả, ví dụ `unless="#result == null"`.
- `@CacheEvict(beforeInvocation=true)` xóa **trước** khi thực thi method, kể cả khi method sau đó lỗi. Mặc định `false` xóa sau khi method thành công, phù hợp hơn khi cần giữ dữ liệu cũ nếu thao tác cập nhật thất bại.
- `@Cacheable(sync=true)` yêu cầu phối hợp nạp cùng một key để giảm nhiều lượt tải song song; provider phải hỗ trợ. Khi dùng `sync=true`, chỉ khai báo một cache, không dùng `unless` và không phối hợp với thao tác caching khác trên cùng method.
- `cacheManager` chọn manager khi có nhiều backend; `cacheResolver` tùy biến chọn cache động. Không chỉ định hai thuộc tính này cùng lúc trên một thao tác.

**Quy ước CRUD thường dùng:** đọc bằng `@Cacheable`; ghi mới/sửa bằng `@CachePut` **nếu biết chắc value vừa trả về đúng cache representation**, hoặc `@CacheEvict` **nếu cần tải lại do nhiều dữ liệu phụ thuộc**; xóa bản ghi gốc bằng `@CacheEvict`. Đừng ghép `@Cacheable` và `@CachePut` trên cùng method: một annotation muốn bỏ qua lời gọi trên hit, annotation kia lại muốn luôn chạy.

## 6. Ví dụ đầy đủ: một region, chu trình read → update → delete

Ví dụ tối giản sau dùng Java 17, Spring Framework 6.2.x và `ConcurrentMapCacheManager` trong tiến trình. Dữ liệu gốc được mô phỏng bằng một repository; code thực tế thay repository đó bằng database. Chỉ có một region `products`; mỗi SKU là một key. Lớp service là Spring bean được gọi từ bên ngoài proxy, nên annotation hoạt động.

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-region-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/CacheRegionDemo.java`:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheRegionDemo {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    ProductRepository productRepository() {
        return new ProductRepository();
    }

    @Bean
    ProductService productService(ProductRepository repository) {
        return new ProductService(repository);
    }

    public record Product(String sku, String name) {}

    public static class ProductRepository {
        private final Map<String, Product> data = new ConcurrentHashMap<>();
        private final AtomicInteger loads = new AtomicInteger();

        public ProductRepository() {
            data.put("P1", new Product("P1", "Bút"));
        }

        public Product find(String sku) {
            loads.incrementAndGet();
            return data.get(sku);
        }

        public Product save(Product product) {
            data.put(product.sku(), product);
            return product;
        }

        public void delete(String sku) {
            data.remove(sku);
        }

        public int loadCount() {
            return loads.get();
        }
    }

    public static class ProductService {
        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @Cacheable(cacheNames = "products", key = "#p0",
                   unless = "#result == null")
        public Product find(String sku) {
            return repository.find(sku);
        }

        @CachePut(cacheNames = "products", key = "#p0.sku()")
        public Product save(Product product) {
            return repository.save(product);
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void delete(String sku) {
            repository.delete(sku);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(CacheRegionDemo.class)) {
            var repository = context.getBean(ProductRepository.class);
            var service = context.getBean(ProductService.class);

            System.out.println("Lần đọc 1: " + service.find("P1"));
            System.out.println("Lần đọc 2: " + service.find("P1"));
            System.out.println("Số lần đọc nguồn: " + repository.loadCount());

            service.save(new Product("P1", "Bút xanh"));
            System.out.println("Sau cập nhật: " + service.find("P1"));
            System.out.println("Số lần đọc nguồn: " + repository.loadCount());

            service.delete("P1");
            System.out.println("Sau xóa: " + service.find("P1"));
            System.out.println("Số lần đọc nguồn: " + repository.loadCount());
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml` (đã cài JDK 17+ và Maven):

```bash
mvn -q compile exec:java -Dexec.mainClass=CacheRegionDemo
```

Dòng in từ chương trình (không tính log riêng của Maven nếu môi trường bật log):

```text
Lần đọc 1: Product[sku=P1, name=Bút]
Lần đọc 2: Product[sku=P1, name=Bút]
Số lần đọc nguồn: 1
Sau cập nhật: Product[sku=P1, name=Bút xanh]
Số lần đọc nguồn: 1
Sau xóa: null
Số lần đọc nguồn: 2
```

Giải thích từng bước:

1. Lần đầu `find("P1")` miss: Spring thực thi repository một lần, rồi lưu kết quả `Product(P1, "Bút")`.
2. Lần thứ hai hit: repository không được gọi, bộ đếm vẫn là 1.
3. `save(...)` luôn thực thi cập nhật nguồn, rồi `@CachePut` thay entry `products/P1` bằng product mới. `find` tiếp theo hit giá trị mới.
4. `delete("P1")` xóa nguồn và evict đúng entry. `find` tiếp theo miss và gọi repository, nên bộ đếm thành 2. Kết quả `null` không được cache do `unless`.

`ConcurrentMapCacheManager` phù hợp để minh họa/test; nó không tự cấu hình TTL, giới hạn bộ nhớ hay lan truyền invalidation giữa các JVM. Nếu phương thức `save` trả về DTO khác kiểu cached value hoặc cần cập nhật nhiều vùng liên quan, hãy chọn evict các vùng thay vì put một value sai hợp đồng.

## 7. Mở rộng hợp đồng khi một lần sửa ảnh hưởng nhiều region

Giả sử trang chi tiết sản phẩm sử dụng region `products`, còn trang danh mục dùng `productListByCategory`. Sửa tên sản phẩm làm thay đổi cả bản ghi chi tiết và danh sách theo danh mục. Việc evict một key ở `products` không làm danh sách tự mới.

Ví dụ minh họa (các phương thức/đối tượng trong hệ thống thực cần được định nghĩa tương ứng):

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "products", key = "#p0.sku()"),
    @CacheEvict(cacheNames = "productListByCategory", allEntries = true)
})
public Product rename(Product changedProduct) {
    return repository.save(changedProduct);
}
```

Đây là **đoạn minh họa, không phải phần bổ sung tự chạy** của file `CacheRegionDemo.java` ở trên. Làm trống toàn bộ danh sách có thể tốn chi phí khi lưu lượng cao; nếu đã biết chính xác category cũ/mới và key danh sách, chỉ evict các key đó. Đặc biệt khi thay đổi tenant hoặc chuyển category, phải tính cả cache theo giá trị **trước và sau** cập nhật.

Chọn chính sách theo dữ liệu:

| Tình huống | Phương án điển hình | Đánh đổi |
| --- | --- | --- |
| Detail by id, kết quả ghi đã là DTO cuối | `@CachePut` cùng key | Lần đọc tiếp theo nhanh, nhưng cần bảo đảm value đúng |
| Ghi thay đổi nhiều projection/danh sách | `@CacheEvict` các key/region liên quan | Miss kế tiếp phải tải lại nhưng ít nguy cơ sai value |
| Thao tác batch đổi phần lớn region | `allEntries=true` có chủ đích | Dễ đúng, có thể gây nhiều miss đồng thời |
| Chỉ cho phép dữ liệu tồn tại tối đa một khoảng | TTL ở provider | TTL giới hạn tuổi thọ, không bảo đảm thấy cập nhật tức thì |
| Đọc dữ liệu gần như bất biến | `@Cacheable` với key đầy đủ | Hiệu quả cao, vẫn cần chính sách khi nguồn đổi |

## 8. Tính nhất quán, giao dịch và cạnh tranh

**Cache miss không mặc nhiên an toàn với race condition.** Khi hai request cùng miss `products/P1`, cả hai có thể gọi nguồn; một request đọc dữ liệu cũ rồi ghi cache sau khi request khác đã cập nhật hoặc evict. `@Cacheable(sync=true)` giúp giảm nạp trùng cùng key nếu provider hỗ trợ, nhưng không giải quyết toàn bộ cuộc đua giữa read và write. Cần kiểm soát ở cấp dữ liệu (version, transaction, thứ tự sự kiện, chính sách invalidation) theo yêu cầu nhất quán.

**Ranh giới giao dịch:** `@CacheEvict` mặc định chạy sau khi phương thức được gọi thành công; điều đó không tự đồng nghĩa với “database đã commit” trong mọi thứ tự AOP/transaction. Nếu cần cập nhật cache sau commit, có thể dùng `TransactionAwareCacheManagerProxy` hoặc cơ chế sự kiện sau commit (`@TransactionalEventListener(phase = AFTER_COMMIT)`), nhưng vẫn phải xét lỗi cache, giao dịch lồng nhau và nhiều node. Cache và database không tự tham gia một atomic commit chung.

**Nhiều tiến trình:** `ConcurrentMapCacheManager` là cache local; node A evict entry không xóa bản sao trên node B. Với hệ thống nhiều instance, chọn shared cache như Redis hoặc cơ chế phát thông báo invalidation và có phương án xử lý event chậm/mất. Phạm vi nhất quán phải được định nghĩa riêng cho từng region: catalog có thể chấp nhận stale ngắn, quyền truy cập/số dư/tồn kho thường cần kiểm tra nguồn hoặc quy trình chặt chẽ hơn.

**TTL và dung lượng:** Spring Cache API chuẩn không có nút bật TTL chung cho mọi provider. Cấu hình `expireAfterWrite`/`maximumSize` (ví dụ Caffeine) hoặc TTL của Redis ở phần cache storage. Đừng tưởng `@Cacheable` tự đặt TTL; và đừng coi expiration là cơ chế đồng bộ tức thời giữa các node.

**Lỗi backend/cache:** Cần quyết định lỗi get/put/evict có làm hỏng request hay chỉ fallback qua nguồn. `CacheErrorHandler` có thể tùy chỉnh xử lý lỗi, nhưng bỏ qua lỗi evict trong lúc nguồn đã đổi có thể để lại stale data. Theo dõi số hit/miss, thời gian tải nguồn, số evict, lỗi provider và kích thước theo từng region để phát hiện mất hiệu quả hoặc sai nhất quán.

## 9. Các lỗi thực tế thường gặp

1. **Quên `@EnableCaching` hoặc gọi cùng lớp:** annotation không được áp dụng trong proxy mặc định nếu gọi `this.find(...)` nội bộ, gọi method ngoài Spring bean, hoặc chạy quá sớm khi proxy chưa sẵn sàng. Thiết kế method được gọi qua bean Spring; proxy có những giới hạn đối với `private`/`final` và self-invocation.
2. **Dùng key thiếu ngữ cảnh:** `findPrice(sku, currency)` chỉ key theo `sku` khiến đơn vị tiền tệ bị lẫn. Thêm `currency` (và tenant/user nếu cần) vào key.
3. **Dùng sai key giữa đọc và ghi:** `@Cacheable(key="#p0")` mà `@CacheEvict(key="#p0.id")` với `p0` khác kiểu, kết quả key không khớp và stale entry còn nguyên.
4. **Tin rằng `@CachePut` bỏ qua method:** thực tế nó **luôn chạy**. Dùng để làm mới cache sau nghiệp vụ, không để tiết kiệm lần đọc.
5. **Evict một region trong khi dữ liệu phụ thuộc nằm ở region khác:** stale danh sách, tìm kiếm, tổng hợp. Lập ma trận thao tác ghi → các vùng cần invalidation.
6. **Đọc cached-null như một miss:** `Cache.get(key)` trả wrapper khi đã cache null; `Cache.get(key, Type.class)` không phân biệt được hai trường hợp.
7. **Cache dữ liệu thay đổi liên tục hoặc rất nhạy cảm:** cache có thể trả dữ liệu cũ. Hãy yêu cầu mức nhất quán rõ ràng và cân nhắc đọc trực tiếp nguồn ở bước quyết định quan trọng.
8. **Xem clear/evict là thao tác toàn hệ thống:** chúng chỉ tác động tới region trên backend/manager đang dùng; không mặc nhiên làm mới cache trong mọi instance hoặc cache phụ thuộc.
9. **Không quan tâm object mutable, dung lượng và TTL:** lưu reference mutable dễ tạo hành vi khó dự đoán; cache local không giới hạn có thể giữ dữ liệu lâu, tăng áp lực bộ nhớ.
10. **Dựa vào eviction sau phương thức như bảo đảm commit:** xem lại thứ tự AOP và transaction; cân nhắc phát invalidation sau commit khi cần.

## 10. Kiểm tra hợp đồng trước khi triển khai

Với từng region, kiểm chứng bằng test hoặc quan sát thực tế:

- **Hit/miss:** gọi cùng key hai lần, số lần gọi nguồn chỉ tăng ở lần đầu; gọi key khác phải tạo entry riêng.
- **Write:** sửa nguồn rồi đọc lại phải thấy value đúng; các projection phụ thuộc cũng phải được làm mới theo thiết kế.
- **Delete:** xóa đúng key không vô tình làm mất key khác; `allEntries=true` chỉ dùng khi thực sự muốn xóa cả region.
- **Boundary:** hai tenant, currency hoặc locale khác nhau không dùng chung key; quyền truy cập không dựa vào cache cũ để vượt kiểm tra.
- **Failure:** thao tác nguồn thất bại có còn xóa cache không? Mất kết nối provider sẽ fallback thế nào? Giao dịch rollback có để lại value mới trong cache không?
- **Concurrency/multi-node:** thử request đọc và ghi đồng thời; kiểm tra tốc độ hồi phục của từng instance sau invalidation và mức stale chấp nhận được.
- **Policy:** đo TTL, tỷ lệ hit, số entry, chi phí miss và cache stampede; bảo đảm memory/latency phù hợp tải thực tế.

Một thiết kế cache tốt có thể diễn tả trong một câu cho mỗi region: **“Region này lưu kiểu dữ liệu gì theo key nào, ai nạp, ai cập nhật/xóa, khi nào hết hạn và chấp nhận stale bao lâu.”** Nếu chưa trả lời được, annotation dễ làm chương trình chạy nhanh hơn nhưng khó chứng minh kết quả đúng.

## Tài liệu tham khảo chính thức

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Cache Annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Storage Configuration: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — TTL/TTI and provider-specific policies: https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html
- Spring Framework — `Cache` API contract: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html
