# @Caching để nhóm nhiều thao tác trên một phương thức

**@Caching** của Spring Framework cho phép **nhóm nhiều annotation cache trên cùng một phương thức**. Một hành động nghiệp vụ thường phải tác động tới nhiều vùng lưu: cập nhật cache tra cứu theo ID, cập nhật cache tra cứu theo SKU và xóa danh sách tổng hợp đã cũ. Nếu chỉ thay một entry, những đường đọc khác có thể trả dữ liệu không nhất quán. **@Caching** khai báo các hành động liên quan với cùng một lời gọi, thay vì tạo những method giả chỉ để gắn annotation.

Ba nhóm được hỗ trợ là **cacheable**, **put** và **evict**, tương ứng chứa **@Cacheable**, **@CachePut**, **@CacheEvict**. Tuy nhiên, **@Caching không phải transaction**, không tự giải quyết key sai, không đảm bảo cập nhật nguyên tử giữa nhiều cache hoặc đồng bộ qua nhiều node. Những việc đó cần được thiết kế và kiểm thử riêng.

## 1. Cấu trúc và ý nghĩa

~~~java
@Caching(
    cacheable = { /* các @Cacheable */ },
    put = { /* các @CachePut */ },
    evict = { /* các @CacheEvict */ }
)
public ReturnType method(Arguments args) {
    // Xử lý nghiệp vụ
}
~~~

| Nhóm | Ý nghĩa | Hành vi đặc trưng |
| --- | --- | --- |
| **cacheable** | Đọc kết quả từ cache nếu đã tồn tại; nếu miss, thực thi và lưu | Một cache hit có thể bỏ qua thân method |
| **put** | Chạy method và đưa kết quả trả về vào cache | Method phải chạy để sinh kết quả cho @CachePut |
| **evict** | Xóa một key hoặc toàn bộ entries của cache | Mặc định xóa sau khi method kết thúc bình thường |

Mỗi annotation con có thể có **cacheNames**, **key**, **condition** và những thuộc tính riêng phù hợp. Ví dụ **@CacheEvict** có **allEntries** và **beforeInvocation**; **@CachePut** có **unless** và có thể dùng **#result** trong key sau khi method trả kết quả.

**@Caching chỉ là annotation gom nhóm.** Nếu một hành động đơn lẻ đã đủ, hãy dùng trực tiếp **@Cacheable**, **@CachePut** hoặc **@CacheEvict**. Nếu cùng key và cùng loại thao tác áp dụng cho nhiều cache, một annotation có nhiều cacheNames có thể ngắn hơn:

~~~java
@CacheEvict(cacheNames = {"productsById", "productsBySku"}, key = "#p0")
public void invalidate(String id) {
    // Chỉ đúng khi cả hai cache thật sự sử dụng cùng key id.
}
~~~

Nếu một vùng dùng key **id** còn vùng kia dùng key **sku**, annotation đơn này không đủ. Khi đó **@Caching** cho phép mô tả riêng từng key.

## 2. @Caching(evict): vô hiệu hóa nhiều cache liên quan

Ví dụ thay tên một Product có thể làm cũ cache chi tiết và các view tổng hợp:

~~~java
@Caching(evict = {
    @CacheEvict(cacheNames = "productById", key = "#p0"),
    @CacheEvict(cacheNames = "productSummary", key = "#p0"),
    @CacheEvict(cacheNames = "productCatalog", allEntries = true)
})
public void rename(String productId, String newName) {
    repository.rename(productId, newName);
}
~~~

Sau khi method chạy thành công, Spring yêu cầu xóa entry của **productById** và **productSummary** theo productId, đồng thời xóa **mọi entry trong riêng cache productCatalog**. Lần đọc tiếp theo phải nạp lại dữ liệu theo quy tắc của các method đọc.

**allEntries = true** là eviction của cả vùng cache được chỉ định, không phải xóa toàn bộ cache thuộc CacheManager. Khi dùng **allEntries**, không khai báo key riêng với kỳ vọng xóa chọn lọc. Cần cân nhắc chi phí: một danh sách có nhiều entry có thể gây nhiều cache miss cùng lúc sau khi xóa toàn vùng.

### Thời điểm xóa: beforeInvocation

~~~java
@Caching(evict = {
    @CacheEvict(
        cacheNames = "reportSnapshot",
        key = "'latest'",
        beforeInvocation = true),
    @CacheEvict(
        cacheNames = "reportStats",
        allEntries = true,
        beforeInvocation = true)
})
public void rebuildReport() {
    reportService.rebuild();
}
~~~

Mặc định **beforeInvocation = false**: eviction diễn ra sau khi method hoàn tất bình thường. Nếu method ném exception, eviction sau lời gọi thường không diễn ra. Với **beforeInvocation = true**, cache bị xóa **trước** khi method chạy, kể cả khi method sau đó thất bại.

Không thể dùng **#result** trong key của eviction chạy **trước invocation**, vì kết quả chưa tồn tại. Eviction sau invocation có thể dùng **#result** theo ngữ cảnh hỗ trợ, nhưng hãy tránh phụ thuộc vào kết quả null và kiểm thử chính xác.

Trong ứng dụng có database transaction, việc method trả thành công và việc transaction **commit** không nhất thiết trùng thời điểm. Eviction trước commit có thể khiến luồng khác miss rồi nạp dữ liệu DB cũ. **@Caching không tự giải quyết race này**; khi yêu cầu nhất quán cao, cần chọn chính sách after-commit, invalidation bằng sự kiện hoặc cách phối hợp transaction-cache phù hợp.

## 3. @Caching(put): ghi một kết quả vào nhiều cache

Nếu một Product được tra cứu theo **id** và **sku**, mỗi vùng có key riêng. Một method lưu Product có thể làm nóng hai cache:

~~~java
@Caching(put = {
    @CachePut(cacheNames = "productById", key = "#result.id()"),
    @CachePut(cacheNames = "productBySku", key = "#result.sku()")
})
public Product save(Product product) {
    return repository.save(product);
}
~~~

**@CachePut** yêu cầu chạy thân **save(...)**, rồi lưu kết quả trả về; **#result** có giá trị ở giai đoạn này. Ví dụ giả định **Product** là Java record có hai accessor **id()** và **sku()**, kết quả không null và hai định danh đã được repository xác định đúng.

Điều cần kiểm tra:

- **Phương thức đọc có cùng key hay không?** **findById(id)** phải đọc từ **productById[id]**, còn **findBySku(sku)** đọc từ **productBySku[sku]**.
- **Giá trị cache có cùng kiểu/ý nghĩa không?** Nếu một cache lưu Product, không thể dùng method khác kỳ vọng String theo cùng key.
- **SKU có thể thay đổi không?** Ghi key SKU mới không xóa entry SKU cũ; phải evict key cũ hoặc thay cơ chế index.
- **Nếu method trả null thì sao?** Có thể cần **unless = "#result == null"** để bỏ qua việc lưu và tránh truy cập accessor trên null.
- **Nếu một put thất bại thì sao?** Những put thành công trước đó không mặc nhiên được rollback.

Khi các cache có cùng key, cùng value và cùng chính sách, **@CachePut(cacheNames = {"A", "B"}, key = "#p0")** có thể ngắn gọn hơn. Khi key khác nhau, **@Caching(put = {...})** minh bạch hơn.

## 4. Kết hợp @Caching(put = ..., evict = ...)

Một method cập nhật Product có thể đồng thời:

1. Ghi Product mới vào **productById** theo ID.
2. Ghi Product mới vào **productBySku** theo SKU.
3. Xóa cache danh sách **productList**, vì danh sách phụ thuộc nhiều Product.

~~~java
@Caching(
    put = {
        @CachePut(cacheNames = "productById", key = "#result.id()"),
        @CachePut(cacheNames = "productBySku", key = "#result.sku()")
    },
    evict = {
        @CacheEvict(cacheNames = "productList", allEntries = true)
    }
)
public Product rename(String id, String newTitle) {
    return repository.rename(id, newTitle);
}
~~~

Đây là một cách dùng **@Caching** dễ lý giải: hai cache chỉ mục được cập nhật với giá trị mới, cache tổng hợp phải tính lại. Các annotation con đều có hợp đồng rõ ràng.

Không nên cố ý vừa **put** vừa **evict** đúng *cùng một cache/key* trong một lời gọi rồi dựa vào thứ tự chi tiết để đoán entry cuối cùng có tồn tại hay không. Hãy thiết kế các thao tác không mâu thuẫn và viết test xác nhận trạng thái mong muốn.

## 5. @Caching(cacheable = ...): nhiều điều kiện tra cứu

~~~java
@Caching(cacheable = {
    @Cacheable(
        cacheNames = "catalogPublic",
        key = "#p0",
        condition = "#p1 == true"),
    @Cacheable(
        cacheNames = "catalogInternal",
        key = "#p0",
        condition = "#p1 == false")
})
public Catalog catalog(String category, boolean publicView) {
    return repository.load(category, publicView);
}
~~~

Hai **condition** loại trừ nhau theo publicView, nên lời gọi chủ đích chỉ dùng một trong hai vùng cache. Đây là ví dụ minh họa, không phải cơ chế phân quyền: dữ liệu nội bộ vẫn phải có kiểm tra authorization trước khi truy cập.

Nếu nhiều annotation **@Cacheable** cùng đủ điều kiện, cache hit ở một vùng có thể ảnh hưởng đến việc method có thực thi hoặc các cache còn lại được điền thế nào. Không nên nhóm một cách tùy tiện; kiểm thử cả trường hợp cache A hit, B miss và ngược lại. Nếu hai method/luồng dữ liệu độc lập, nhiều khi tách method hoặc dùng một chiến lược key rõ ràng sẽ dễ bảo trì hơn.

### Không nhầm với @CacheConfig

**@CacheConfig** khai báo mặc định ở cấp class như cacheNames, keyGenerator hay cacheManager. **@Caching** nhóm nhiều annotation ở một method. Chúng giải quyết hai nhu cầu khác nhau và có thể được sử dụng cùng nhau khi cần.

## 6. Vì sao không nên tùy tiện nhóm @Cacheable với @CachePut?

Cấu hình sau có mục tiêu mâu thuẫn:

~~~java
@Caching(
    cacheable = { @Cacheable(cacheNames = "items", key = "#p0") },
    put = { @CachePut(cacheNames = "items", key = "#p0") }
)
public Item load(String id) {
    return repository.findById(id);
}
~~~

**@Cacheable** cho phép bỏ qua thân method khi đã có dữ liệu; **@CachePut** hướng tới chạy method để có kết quả mới. Spring khuyến nghị tránh phối hợp hai annotation này trên cùng method, ngoại trừ trường hợp các **condition** loại trừ nhau được thiết kế đặc biệt và đã kiểm thử. Bọc trong **@Caching** không loại bỏ xung đột semantics.

Cấu trúc thông thường rõ ràng hơn:

~~~java
@Cacheable(cacheNames = "items", key = "#p0")
public Item find(String id) {
    return repository.findById(id);
}

@CachePut(cacheNames = "items", key = "#result.id()")
public Item save(Item item) {
    return repository.save(item);
}
~~~

Một method đọc có cache hit/miss, một method ghi luôn chạy và làm mới cache. Không đặt **@Cacheable** lên method bắt buộc phải chạy side effect như thanh toán, gửi email hoặc cập nhật DB.

## 7. Ví dụ Java 17/Spring chạy được: hai put + một evict

Ví dụ tối giản dùng **Spring Framework 6.1.14**, **Java 17+** và **ConcurrentMapCacheManager**. Dữ liệu nguồn nằm trong Map để quan sát rõ cache hit/miss; mỗi method đọc tăng bộ đếm **chỉ khi thân method thực thi**. Method rename trả Product mới và có **@Caching(put = {...}, evict = {...})**.

Thư mục dự án:

~~~text
spring-caching-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/cache/CachingDemo.java
└── src/test/java/demo/cache/CachingDemoTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-caching-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    testImplementation 'org.springframework:spring-test:6.1.14'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.cache.CachingDemo'
}

test {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/cache/CachingDemo.java**

~~~java
package demo.cache;

import java.util.HashMap;
import java.util.Map;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Caching;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CachingDemo {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager(
                "productsById", "productsBySku", "productList");
    }

    @Bean
    public CatalogService catalogService() {
        return new CatalogService();
    }

    public record Product(String id, String sku, String title) {}

    public static class CatalogService {
        private final Map<String, Product> source = new HashMap<>(
                Map.of("P01", new Product("P01", "SKU-1", "Tea")));

        private int idLoads;
        private int skuLoads;
        private int listLoads;

        @Cacheable(cacheNames = "productsById", key = "#p0")
        public Product byId(String id) {
            idLoads++;
            return source.get(id);
        }

        @Cacheable(cacheNames = "productsBySku", key = "#p0")
        public Product bySku(String sku) {
            skuLoads++;
            return source.values().stream()
                    .filter(p -> p.sku().equals(sku))
                    .findFirst().orElse(null);
        }

        @Cacheable(cacheNames = "productList", key = "'all'")
        public String list() {
            listLoads++;
            return source.get("P01").title() + "|listLoads=" + listLoads;
        }

        @Caching(
            put = {
                @CachePut(
                    cacheNames = "productsById",
                    key = "#result.id()"),
                @CachePut(
                    cacheNames = "productsBySku",
                    key = "#result.sku()")
            },
            evict = {
                @CacheEvict(
                    cacheNames = "productList",
                    key = "'all'")
            }
        )
        public Product rename(String id, String title) {
            Product previous = source.get(id);
            if (previous == null) {
                throw new IllegalArgumentException("Unknown id: " + id);
            }
            Product updated = new Product(previous.id(), previous.sku(), title);
            source.put(id, updated);
            return updated;
        }

        public String loads() {
            return "id=" + idLoads + ",sku=" + skuLoads
                    + ",list=" + listLoads;
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                CachingDemo.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("id1=" + service.byId("P01"));
            System.out.println("idHit=" + service.byId("P01"));
            System.out.println("sku1=" + service.bySku("SKU-1"));
            System.out.println("list1=" + service.list());
            System.out.println("listHit=" + service.list());
            System.out.println("updated=" + service.rename("P01", "Coffee"));
            System.out.println("idAfter=" + service.byId("P01"));
            System.out.println("skuAfter=" + service.bySku("SKU-1"));
            System.out.println("listAfter=" + service.list());
            System.out.println("loads=" + service.loads());
        }
    }
}
~~~

Tại thư mục dự án, chạy bằng Gradle cài sẵn (hoặc Gradle wrapper của project nếu đã có):

~~~bash
gradle run --quiet
~~~

Những dòng **System.out.println** dự kiến, theo đúng thứ tự:

~~~text
id1=Product[id=P01, sku=SKU-1, title=Tea]
idHit=Product[id=P01, sku=SKU-1, title=Tea]
sku1=Product[id=P01, sku=SKU-1, title=Tea]
list1=Tea|listLoads=1
listHit=Tea|listLoads=1
updated=Product[id=P01, sku=SKU-1, title=Coffee]
idAfter=Product[id=P01, sku=SKU-1, title=Coffee]
skuAfter=Product[id=P01, sku=SKU-1, title=Coffee]
listAfter=Coffee|listLoads=2
loads=id=1,sku=1,list=2
~~~

Lời gọi **byId** lần hai hit nên **idLoads** vẫn 1; **bySku** đã tải một lần. **list** hit lần thứ hai nên **listLoads** vẫn 1. Sau **rename**, hai **@CachePut** đưa Product mới vào cache theo ID/SKU, nên hai đường đọc vẫn hit mà không tăng số lần tải. **@CacheEvict** xóa key **"all"** của **productList**, khiến **list()** chạy lại và tăng **listLoads** thành 2.

Kết quả chính là **loads=id=1,sku=1,list=2**: chứng minh hai cache chỉ mục đã được làm mới bằng put, trong khi cache danh sách được invalidate.

**Lưu ý:** **#result.id()** và **#result.sku()** gọi accessor của Java record trên kết quả trả về. Code giả định id/sku không đổi và kết quả không null. Nếu update thay SKU, entry với SKU cũ vẫn có thể tồn tại và cần xóa riêng.

### Kiểm thử Spring bằng JUnit 5

**src/test/java/demo/cache/CachingDemoTest.java**

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.CacheManager;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(CachingDemo.class)
class CachingDemoTest {

    @Autowired
    CachingDemo.CatalogService service;

    @Autowired
    CacheManager cacheManager;

    @Test
    void renameRefreshesTwoIndexesAndEvictsTheList() {
        CachingDemo.Product original = service.byId("P01");

        assertEquals(original, service.byId("P01"));
        assertEquals(original, service.bySku("SKU-1"));
        assertEquals("Tea|listLoads=1", service.list());
        assertEquals("Tea|listLoads=1", service.list());
        assertEquals("id=1,sku=1,list=1", service.loads());

        assertNotNull(cacheManager.getCache("productList").get("all"));

        CachingDemo.Product updated = service.rename("P01", "Coffee");

        assertEquals(updated,
                cacheManager.getCache("productsById")
                        .get("P01", CachingDemo.Product.class));
        assertEquals(updated,
                cacheManager.getCache("productsBySku")
                        .get("SKU-1", CachingDemo.Product.class));
        assertNull(cacheManager.getCache("productList").get("all"));

        assertEquals(updated, service.byId("P01"));
        assertEquals(updated, service.bySku("SKU-1"));
        assertEquals("Coffee|listLoads=2", service.list());
        assertEquals("id=1,sku=1,list=2", service.loads());
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kỳ vọng:** một test JUnit thành công. Test xác minh **cả ba hậu quả** của một lần gọi rename: cache theo ID được cập nhật, cache theo SKU được cập nhật, cache danh sách mất entry cũ và lần đọc tiếp theo nạp lại. Chỉ kiểm tra byId sẽ không chứng minh hai cache khác cũng đúng.

Đây là project Spring thật với lời gọi qua bean Spring, không phải một tệp Java đơn lẻ chỉ cần javac. **ConcurrentMapCacheManager** là cache trong JVM dùng để minh họa, không có TTL/eviction theo dung lượng như những provider được cấu hình riêng.

## 8. Thời điểm xử lý, điều kiện và lỗi cần chú ý

### Điều kiện của annotation con

Mỗi annotation con có điều kiện riêng. Ví dụ:

~~~java
@Caching(put = {
    @CachePut(
        cacheNames = "productsById",
        key = "#result.id()",
        unless = "#result == null"),
    @CachePut(
        cacheNames = "productsBySku",
        key = "#result.sku()",
        unless = "#result == null")
})
public Product save(Product input) {
    return repository.save(input);
}
~~~

**condition** được xét dựa trên ngữ cảnh trước method, phù hợp để quyết định cache theo input. **unless** ở **@Cacheable/@CachePut** cho phép xét kết quả sau method. **@CacheEvict** không có **unless**, mà có condition, beforeInvocation và allEntries. Nếu các annotation con có điều kiện khác nhau, không mặc định rằng cả nhóm luôn cùng được kích hoạt.

### Cache hit và tác dụng phụ

Với **@Caching(cacheable = {...})**, cache hit có thể làm method không được gọi. Không đưa side effect bắt buộc vào thân method nếu có thể bị short-circuit. Với **@Caching(put = {...})**, thân method vẫn phải chạy để tạo dữ liệu, nhưng điều đó không tự đảm bảo các put tới nhiều cache đều thành công.

### Proxy và self-invocation

Cần **@EnableCaching**, **CacheManager** và lời gọi qua Spring-managed proxy. Trong proxy mode, **this.method()** từ cùng bean thường bỏ qua cache interceptor; gọi trực tiếp bằng **new CatalogService()** cũng không kích hoạt annotation. Test tích hợp phải lấy bean từ ApplicationContext như ví dụ.

### Transaction và lỗi từng phần

Một nhóm gồm ba annotation không phải transaction nguyên tử: nếu Redis hoặc cache thứ hai bị lỗi, cache thứ nhất có thể đã đổi. Hành vi exception phụ thuộc CacheErrorHandler và provider. Thứ tự invalidation so với DB commit có thể tạo race condition; với yêu cầu consistency chặt, cân nhắc transaction-aware cache, after-commit invalidation, sự kiện/outbox hoặc kiểm tra lại nguồn dữ liệu.

## 9. Quy tắc key, thay đổi định danh và dữ liệu đa tenant

Một lỗi thường gặp là cache đọc với key **id**, nhưng method ghi thêm tham số **(id, newName)** và quên chỉ định key cho **@CacheEvict**. Khi đó key mặc định của method ghi là tổ hợp **(id, newName)** chứ không phải **id**; entry cũ không được xóa.

Tương tự, **@CachePut(key = "#result.sku()")** cập nhật SKU mới nhưng không tự xóa SKU cũ nếu SKU thay đổi. Cần nắm cả giá trị **trước** và **sau** khi update. Nếu kết quả phụ thuộc **tenantId, locale, currency hoặc quyền truy cập**, key phải phân biệt những yếu tố đó; không để chung một entry giữa hai tenant có cùng ID. Đưa tenant vào key không thay thế authorization.

Nên đảm bảo các cache có kiểu giá trị, serializer, TTL và vòng đời tương thích với cách dùng. Trong Redis, kiểm tra prefix theo cache name, chuyển đổi key và cơ chế invalidation giữa các node; trong local cache, mỗi JVM có state riêng. **@Caching** không tự cung cấp cơ chế broadcast invalidation cho cache local ở những node khác.

## 10. So sánh cách chọn annotation

| Yêu cầu | Cách phù hợp |
| --- | --- |
| Chỉ đọc một kết quả có cache | **@Cacheable** |
| Chỉ ghi một kết quả cache | **@CachePut** |
| Chỉ xóa một entry | **@CacheEvict** |
| Cùng hành động, cùng key ở nhiều vùng | Một annotation với nhiều **cacheNames** |
| Xóa nhiều vùng với key/condition khác nhau | **@Caching(evict = {...})** |
| Ghi một kết quả theo nhiều chỉ mục (id, sku) | **@Caching(put = {...})** |
| Ghi hai index, invalidate danh sách | **@Caching(put = {...}, evict = {...})** |
| Nhiều cacheable loại trừ nhau theo input | **@Caching(cacheable = {...})** nếu thiết kế/kiểm thử rõ |
| Thiết lập cache name hoặc keyGenerator mặc định ở class | **@CacheConfig** |
| Cần thao tác nhiều cache có tính nguyên tử giao dịch | Thiết kế consistency/transaction riêng; **@Caching không đủ** |

Một annotation nhóm quá lớn có thể là dấu hiệu nhiều dữ liệu phụ thuộc vào nhau quá phức tạp. Có thể cần chia ranh giới cache, dùng sự kiện invalidation hoặc một tầng service nghiệp vụ rõ hơn.

## 11. Checklist kiểm thử khi dùng @Caching

1. **Seed các cache trước test**: nếu cache danh sách vốn trống, assert sau update nó vẫn trống không chứng minh eviction đã chạy.
2. **Gọi method qua Spring bean**: xác minh annotation thực sự được interceptor xử lý.
3. **Kiểm tra method ghi thực thi**: đặc biệt khi có @CachePut, side effect không được bị mất.
4. **Kiểm tra từng entry vừa put**: đúng cache name, key và kiểu Product.
5. **Kiểm tra từng entry cần xóa**: sau update, giá trị cũ không còn; lần read sau tải dữ liệu hiện tại.
6. **Kiểm tra dữ liệu không liên quan**: nếu chỉ đổi P01, P02 hoặc tenant khác không được dùng nhầm entry.
7. **Kiểm tra lỗi**: method exception, beforeInvocation true/false, cache provider mất kết nối.
8. **Kiểm tra transaction/concurrency**: một luồng đọc có nạp dữ liệu cũ vào cache trong khoảng commit không?
9. **Kiểm tra thay key**: khi ID/SKU đổi hoặc cache name thay, cơ chế xóa entry cũ đã có chưa?
10. **Kiểm tra với provider production-like**: Redis, Caffeine, nhiều replica, serializer/TTL khác cache demo.

Test chỉ xác minh giá trị cuối của một đường đọc là chưa đủ. Một nhóm **@Caching** phải được kiểm thử **theo từng thao tác con** và theo trạng thái tổng thể sau lời gọi.

## 12. Lỗi phổ biến và tự kiểm tra

- **Bỏ quên một vùng cache liên quan:** làm sơ đồ các đường đọc và danh sách invalidation cần thiết.
- **Sai key khi đọc/ghi/xóa:** so sánh expression của từng annotation với method đọc thực tế.
- **Lạm dụng allEntries = true:** có thể gây thác cache miss và tăng tải DB.
- **Mong @Caching là transaction:** cần handling cho lỗi từng phần, commit và retry/invalidation.
- **Phối hợp cacheable và put mâu thuẫn:** tách phương thức đọc/ghi nếu không chứng minh được điều kiện loại trừ.
- **Truy cập #result khi chưa có:** chỉ dùng trong các operation giai đoạn sau method phù hợp.
- **Quên SKU cũ khi đổi SKU:** entry index cũ không tự biến mất.
- **Self-invocation:** annotation có thể bị bỏ qua nếu gọi method trong cùng bean ở proxy mode.
- **Không kiểm thử exception path:** beforeInvocation thay đổi thời điểm eviction khi method thất bại.
- **Nhầm @CacheConfig với @Caching:** một cái là cấu hình mặc định cấp class, một cái nhóm hành động cấp method.

Câu hỏi ôn tập:

1. Khi nào **@CacheEvict(cacheNames = {"A", "B"})** đủ, và khi nào cần nhóm **@Caching(evict = {...})**?
2. Vì sao **@CachePut** cho hai cache theo ID/SKU có thể dùng hai biểu thức **#result** khác nhau?
3. Sau khi đổi SKU, vì sao put theo SKU mới không đảm bảo entry SKU cũ bị xóa?
4. **beforeInvocation = true** làm gì nếu method ném exception?
5. Vì sao không nên nhóm **@Cacheable** và **@CachePut** vô điều kiện lên cùng method?
6. Vì sao một test chỉ kiểm tra **byId** sau rename chưa chứng minh nhóm ba thao tác đúng?
7. Khi thao tác cache thứ hai thất bại sau khi cache thứ nhất đã put, **@Caching** có tự rollback không?

**Kết luận:** **@Caching** giúp khai báo một nhóm hành động cache cho cùng một method, đặc biệt hữu ích khi **cập nhật nhiều chỉ mục và vô hiệu hóa các view phụ thuộc**. Tính đúng đắn phụ thuộc key, tên cache, điều kiện, thời điểm eviction, tính nhất quán của nguồn dữ liệu và kiểm thử đầy đủ từng cache, không phải chỉ phụ thuộc vào việc nhóm annotation.

### Tài liệu chính thức

- Spring Framework — Annotation-based caching, @Caching, @CachePut, @CacheEvict: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — AOP proxy semantics: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — @Caching Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Caching.html
- Spring Framework — @CachePut Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework — @CacheEvict Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
