# @CacheEvict: Xóa một khóa khi dữ liệu nguồn thay đổi

> **Spring Framework Cache Abstraction · Chủ đề: @CacheEvict.** Mục tiêu là cập nhật nguồn dữ liệu và vô hiệu hóa đúng entry cũ trong cache, để lần đọc tiếp theo lấy bản mới mà vẫn giữ các entry không liên quan.

## 1. Bài toán dữ liệu cũ trong cache

Giả sử hệ thống dùng vùng cache `products` để lưu tên sản phẩm theo mã SKU. Khi gọi `find("A")` lần đầu, dịch vụ lấy `"Keyboard-v1"` từ nguồn, sau đó cache giá trị dưới key `"A"`. Lần đọc kế tiếp cùng key dùng ngay cache, giảm một lần truy vấn.

Nếu thao tác cập nhật đổi nguồn thành `"Keyboard-v2"` mà entry A không bị vô hiệu hóa, lời gọi đọc vẫn có thể nhận `"Keyboard-v1"`. Đó là **stale cache**: bản sao trong cache đã không còn tương ứng với dữ liệu gốc.

Giải pháp *cache-aside* thường dùng:

1. Phương thức cập nhật dữ liệu nguồn thực sự thành công.
2. Spring xóa entry mang key `"A"` trong cache `products`.
3. Lần đọc tiếp theo cùng key trở thành cache miss, tải `"Keyboard-v2"` từ nguồn.
4. `@Cacheable` lưu giá trị mới; các entry khác như `"B"` tiếp tục được giữ.

~~~text
Ban đầu:
  source: A -> Keyboard-v1, B -> Mouse-v1
  products cache: A -> Keyboard-v1, B -> Mouse-v1

Thực thi update("A", "Keyboard-v2"):
  source: A -> Keyboard-v2, B -> Mouse-v1
  @CacheEvict: xóa đúng products["A"]

Sau đó:
  products cache: không có A, B -> Mouse-v1
  find("A") -> cache miss -> source -> Keyboard-v2 -> cache A
  find("B") -> cache hit -> Mouse-v1
~~~

`@CacheEvict` chỉ điều khiển **cache**; nó không thực hiện thao tác ghi dữ liệu nguồn thay cho method. Hành vi cập nhật nguồn phải nằm trong code nghiệp vụ.

## 2. Cú pháp @CacheEvict để xóa một entry

Ví dụ một phương thức thực hiện cập nhật từ ứng dụng có repository:

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void rename(String sku, String newName) {
    repository.updateName(sku, newName);
}
~~~

Đây là **mã minh họa bên trong service**, cần một thành phần `repository` hợp lệ và cấu hình Spring cache của ứng dụng. Phần 5 cung cấp chương trình độc lập.

| Thuộc tính | Chức năng | Mặc định liên quan |
| --- | --- | --- |
| `cacheNames` hoặc `value` | Chọn vùng cache; ở đây tên `products` | Cần khai báo ở annotation hoặc cấu hình chung phù hợp |
| `key` | SpEL tính key cần xóa; `#p0` là đối số đầu tiên | Không đặt thì dùng key generator của Spring |
| `allEntries` | Có xóa toàn bộ vùng cache không? | `false`: chỉ xử lý entry theo key |
| `beforeInvocation` | Có xóa trước khi method chạy không? | `false`: xóa sau khi method thành công |
| `condition` | Biểu thức SpEL cho phép hoặc từ chối eviction | Không đặt: không có điều kiện bổ sung |

`cacheNames = "products"` là **tên vùng cache**, còn `key = "#p0"` là cách chọn **một entry bên trong vùng đó**. Với `rename("A", "Keyboard-v2")`, `#p0` lấy chuỗi `"A"`. Spring tìm cache `products` qua `CacheManager` và xóa entry tương ứng với key ấy.

Phương thức cập nhật có thể trả `void` vì `@CacheEvict` dùng method như một **tác nhân kích hoạt xóa**, không cần đưa kết quả method vào cache.

Không dùng `allEntries = true` khi chỉ một sản phẩm thay đổi. Khi thực sự cần xóa cả vùng, dùng `allEntries = true` mà không kèm `key` vì key không còn ý nghĩa trong thao tác xóa toàn bộ.

## 3. Điều kiện quan trọng nhất: khóa xóa phải khớp khóa đọc

Phương thức đọc và cập nhật thường có **chữ ký khác nhau**:

~~~java
// Hai đoạn method thuộc service có Map<String, String> source.
@Cacheable(cacheNames = "products", key = "#p0")
public String find(String sku) {
    return source.get(sku);
}

@CacheEvict(cacheNames = "products", key = "#p0")
public void rename(String sku, String newName) {
    source.put(sku, newName);
}
~~~

Đây là **mã minh họa cấu trúc service**, chưa là class độc lập. Hai annotation đều chọn SKU ở vị trí 0, nên khi cập nhật A, key bị xóa đúng là key mà reader đang sử dụng.

Ngược lại:

~~~java
// Không phù hợp nếu read method chỉ dùng chuỗi SKU làm key.
@CacheEvict(cacheNames = "products")
public void rename(String sku, String newName) {
    source.put(sku, newName);
}
~~~

Không đặt `key` nghĩa là Spring dùng cơ chế key mặc định. Với **hai tham số**, `SimpleKeyGenerator` tạo key kết hợp cả SKU và tên mới; key này **khác** chuỗi SKU được dùng khi đọc. Khi đó eviction có thể không trúng entry A, khiến cache vẫn giữ giá trị cũ.

### Chọn đúng vị trí trong SpEL

| Biểu thức | Ý nghĩa |
| --- | --- |
| `#p0` hoặc `#a0` | Đối số thứ nhất (index 0) |
| `#p1` hoặc `#a1` | Đối số thứ hai (index 1) |
| `#root.args[0]` | Đối số đầu tiên lấy từ mảng đối số |
| `#sku` | Tham số Java có tên `sku`, khi runtime tìm được metadata tên |

Nếu updater có chữ ký `rename(String newName, String sku)`, SKU nằm ở vị trí 1, do đó phải chọn `key = "#p1"`. Đối với cách viết theo tên như `#sku`, Java thường cần cờ biên dịch `-parameters` để giữ metadata. `#p0` và `#p1` không phụ thuộc vào tên nguồn.

### Key cấu tạo theo quy tắc riêng

Nếu reader dùng `key = "'sku:' + #p0"`, entry thực tế có key `"sku:A"`, không phải `"A"`. Evictor cũng phải sử dụng quy tắc tạo key đó. Nếu một dữ liệu nguồn ảnh hưởng nhiều biểu diễn cache (ví dụ giá theo SKU và loại tiền), có thể cần xóa **nhiều key khác nhau**. Chỉ xóa SKU đơn lẻ là đủ khi thật sự chỉ có một entry đại diện cho dữ liệu được cập nhật.

## 4. Thời điểm xóa: sau hay trước method?

### Sau invocation: mặc định

Với `beforeInvocation = false`, Spring chạy phần thân của method trước. Chỉ khi method kết thúc bình thường, Spring mới tính key và thực hiện eviction.

~~~text
Lời gọi update("A", "Keyboard-v2") qua Spring proxy
                 |
                 v
          Logic cập nhật nguồn
             /         \
       Thành công      Ném exception
           |                 |
           v                 v
  Evict products["A"]    Không evict mặc định
~~~

Điều này phù hợp với nhiều thao tác cập nhật đồng bộ. Nếu update bị từ chối ngay từ bước kiểm tra đầu vào, entry cache cũ được giữ vì nguồn chưa thay đổi.

Nếu update đã tác động một phần lên nguồn rồi ném lỗi, phải xử lý rollback và invalidation dựa trên transaction thực tế; `@CacheEvict` không tự rollback dữ liệu nguồn.

### Trước invocation: dùng có chủ đích

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    beforeInvocation = true
)
public void rename(String sku, String newName) {
    repository.updateName(sku, newName);
}
~~~

Đây là mã minh họa cần repository của ứng dụng. Trong chế độ này, Spring xóa key **trước** khi method chạy, nên entry bị xóa ngay cả nếu method sau đó ném exception.

Một rủi ro: reader chạy đồng thời sau khi evict nhưng trước khi update nguồn hoàn thành có thể tải và cache lại **giá trị cũ**. Do đó không bật `beforeInvocation = true` một cách máy móc cho mọi thao tác update.

`@CacheEvict` còn có `condition`, chẳng hạn `condition = "#p0 != null"` để chỉ evict khi SKU đầu vào không null. Nó **không có thuộc tính `unless`** như `@Cacheable`. Với `beforeInvocation = false`, SpEL ở thời điểm sau method có thể tham chiếu `#result` khi phù hợp; với `beforeInvocation = true` không thể dùng kết quả chưa tồn tại.

## 5. Chương trình Java 17+ minh họa chính xác một key

Ví dụ chạy bằng Spring Framework **6.2.14** và Gradle. Nó dùng `ConcurrentMapCacheManager` cho cache trong một JVM và `ConcurrentHashMap` để đóng vai nguồn dữ liệu. Không cần database hoặc Redis.

**Tệp `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.EvictOneEntryDemo'
}
~~~

**Tệp `src/main/java/demo/EvictOneEntryDemo.java`:**

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class EvictOneEntryDemo {

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public Catalog catalog() {
            return new Catalog();
        }
    }

    public static class Catalog {
        private final Map<String, String> source =
                new ConcurrentHashMap<>(Map.of(
                        "A", "Keyboard-v1",
                        "B", "Mouse-v1"
                ));
        private int sourceReads;

        @Cacheable(cacheNames = "products", key = "#p0")
        public String find(String sku) {
            sourceReads++;
            return source.get(sku);
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void update(String sku, String newName) {
            if (newName == null || newName.isBlank()) {
                throw new IllegalArgumentException("name must not be blank");
            }
            source.put(sku, newName);
        }

        public int sourceReads() {
            return sourceReads;
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Catalog catalog = context.getBean(Catalog.class);
            CacheManager manager = context.getBean(CacheManager.class);
            Cache cache = Objects.requireNonNull(manager.getCache("products"));

            System.out.println("read A: " + catalog.find("A"));
            System.out.println("read B: " + catalog.find("B"));
            System.out.println("read A again: " + catalog.find("A"));
            System.out.println("source reads: " + catalog.sourceReads());

            catalog.update("A", "Keyboard-v2");
            System.out.println("A cached after update: " +
                    (cache.get("A") != null));
            System.out.println("B cached after update: " +
                    (cache.get("B") != null));

            System.out.println("read A after update: " + catalog.find("A"));
            System.out.println("read B after update: " + catalog.find("B"));
            System.out.println("source reads: " + catalog.sourceReads());

            try {
                catalog.update("B", "");
            } catch (IllegalArgumentException ex) {
                System.out.println("update rejected: " + ex.getMessage());
            }
            System.out.println("B cached after rejected update: " +
                    (cache.get("B") != null));
        }
    }
}
~~~

Chạy từ thư mục chứa `build.gradle`, với JDK 17+ và Gradle tương thích:

~~~bash
gradle run --quiet
~~~

**Stdout dự kiến của chương trình (không tính thông báo công cụ build):**

~~~text
read A: Keyboard-v1
read B: Mouse-v1
read A again: Keyboard-v1
source reads: 2
A cached after update: false
B cached after update: true
read A after update: Keyboard-v2
read B after update: Mouse-v1
source reads: 3
update rejected: name must not be blank
B cached after rejected update: true
~~~

**Giải thích:**

1. Hai lần đọc A và B ban đầu gọi nguồn nên bộ đếm `sourceReads` là 2. Lần đọc A lặp lại là cache hit, bộ đếm giữ nguyên.
2. `update("A", "Keyboard-v2")` ghi thay đổi vào map rồi Spring evict key `"A"` sau khi method thành công.
3. `cache.get("A") == null` cho biết entry A đã bị xóa; entry B vẫn có `Cache.ValueWrapper`, nên hai dòng kiểm tra lần lượt in `false` và `true`.
4. Đọc A sau cập nhật lại miss, nạp `Keyboard-v2` từ nguồn. Đọc B vẫn hit, tổng số lần truy cập nguồn tăng lên **3**.
5. `update("B", "")` ném `IllegalArgumentException` trước khi sửa map. Do `beforeInvocation = false`, Spring không evict entry B sau exception.

Chương trình dùng `#p0`, không cần compiler flag `-parameters`. Những method được cache được gọi từ `main` thông qua bean Spring; đây là điều kiện quan trọng trong chế độ proxy mặc định.

**Lưu ý:** `Cache.get(key)` trả `Cache.ValueWrapper` hoặc null. Có wrapper với giá trị bên trong null khác với hoàn toàn không có entry; ví dụ này lưu tên sản phẩm không rỗng nên chỉ cần kiểm tra wrapper.

## 6. Phạm vi một key so với nhiều key

Chỉ xóa một key khi một thay đổi nguồn chỉ làm stale đúng entry tương ứng. Ví dụ đổi tên A nhưng B không đổi: giữ cache B giúp tránh truy vấn lại không cần thiết.

Nếu một bản ghi nguồn xuất hiện ở nhiều cache entry, ví dụ cache chi tiết theo SKU, danh sách theo danh mục và kết quả tìm kiếm theo điều kiện, xóa `products["A"]` chưa đủ bảo đảm mọi biểu diễn đều mới. Khi đó cần xác định **tập key/vùng cache bị ảnh hưởng** và invalidation tương ứng. `@Caching` có thể nhóm nhiều `@CacheEvict`; `allEntries = true` chỉ thích hợp khi muốn xóa cả vùng và chấp nhận chi phí nạp lại.

Nếu đổi mã định danh từ A sang C, cần cân nhắc cả key cũ và key mới. Nếu key gồm nhiều trường (SKU, currency, ngôn ngữ), một update có thể khiến nhiều biến thể phải được vô hiệu hóa.

## 7. Transaction, concurrency và nhiều instance

### Evict sau method chưa chắc là sau commit

Với nguồn là database và method có `@Transactional`, thứ tự giữa caching advice và transaction advice, cùng cách backend cache hỗ trợ transaction, quyết định **thời điểm eviction so với commit**. Có thể xảy ra trường hợp cache bị evict khi transaction ghi chưa commit; reader khác miss cache nhưng vẫn đọc thấy dữ liệu cũ, rồi ghi giá trị cũ trở lại.

Với yêu cầu chặt về nhất quán, hãy thiết kế eviction **sau commit thành công**, cân nhắc cơ chế `TransactionAwareCacheManagerProxy` hoặc sự kiện hậu commit và xác minh cách backend xử lý. Chỉ thêm `@Transactional` không tự bảo đảm cache nhất quán sau commit.

### Một reader có thể ghi dữ liệu cũ sau eviction

Một luồng đọc A bắt đầu trước update, lấy giá trị cũ từ nguồn nhưng chưa kịp cache. Luồng ghi update A và evict thành công. Sau đó luồng đọc đầu mới put giá trị cũ vào cache. Như vậy entry có thể stale dù evict đã được gọi.

`@CacheEvict` không cung cấp tính nguyên tử xuyên suốt nguồn dữ liệu, cache và nhiều request đồng thời. Tùy mức nhất quán yêu cầu, có thể cần versioned key, TTL, đồng bộ truy cập hoặc chiến lược invalidation mạnh hơn.

### Cache cục bộ và các đường ghi khác

`ConcurrentMapCacheManager` trong ví dụ chỉ cache trong JVM hiện tại. Nếu nhiều instance có cache riêng, eviction ở instance A không tự loại bỏ entry trong instance B. Cần backend chia sẻ hoặc phát sự kiện invalidation xuyên instance khi phù hợp.

Nếu dữ liệu nguồn được sửa bởi SQL trực tiếp, batch job hoặc service khác, method gắn annotation không được gọi nên Spring không thể tự biết để evict. Hãy bảo đảm **mọi luồng ghi nguồn có đường invalidation** theo thiết kế ứng dụng.

### Spring proxy và self-invocation

Với `@EnableCaching` trong chế độ proxy mặc định, lời gọi từ method khác trong cùng bean như `this.update("A", "Keyboard-v2")` thường không đi qua caching interceptor. Vì thế annotation có thể không chạy. Lời gọi từ bean khác thông qua proxy, như trong chương trình ở trên, được Spring áp dụng caching advice.

## 8. So sánh với @CachePut và thao tác trực tiếp

| Cách tiếp cận | Hành vi chính | Thích hợp |
| --- | --- | --- |
| `@CacheEvict(cacheNames = "products", key = "#p0")` | Xóa entry sau khi update thành công | Update trả void hoặc dữ liệu cache cần tái tạo từ nguồn |
| `@CachePut(cacheNames = "products", key = "#p0")` | Luôn chạy method, lưu **kết quả trả về** vào cache | Update trả chính giá trị mới phù hợp với reader |
| `cacheManager.getCache("products").evict(sku)` | Xóa entry trực tiếp bằng API | Xử lý sự kiện, thao tác thủ công hoặc tác vụ ngoài interceptor |

Không dùng `@Cacheable` cho method cập nhật vì cache hit có thể khiến code update không chạy. Nếu gọi API thủ công, `getCache(name)` có thể trả null tùy `CacheManager`, nên cần kiểm tra, đồng thời bảo đảm đúng vùng và key.

## 9. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Cập nhật thành công nhưng lần đọc vẫn cũ | Sai `cacheNames` hoặc sai key | So sánh reader và evictor; kiểm tra SpEL/KeyGenerator |
| Update có hai tham số và không đặt `key` | Key mặc định chứa cả hai tham số | Chỉ định key theo định danh dữ liệu cần xóa |
| Eviction không kích hoạt | Chưa bật caching, lời gọi không qua proxy | Kiểm tra `@EnableCaching`, bean và đường gọi |
| Một key đổi nhưng mọi entry bị xóa | Dùng `allEntries = true` | Trở về eviction theo `key` |
| Method ném lỗi nhưng cache vẫn còn | Default evict sau khi method thành công | Kiểm tra update/rollback và thời điểm evict |
| Một server còn dữ liệu cũ | Cache cục bộ theo JVM | Xác minh backend, sự kiện invalidation, TTL |
| Cache lại bị stale sau eviction | Race hoặc eviction trước commit | Kiểm tra transaction, các luồng đọc/ghi và thứ tự thao tác |

Quy trình chẩn đoán ngắn: **xem giá trị nguồn mới → xác nhận method update đã qua Spring proxy → xác nhận key/cache name → kiểm tra entry bị xóa → đọc lại để quan sát cache miss và dữ liệu mới**.

## 10. Câu hỏi tự kiểm tra

**1.** Reader `get(String id)` cache theo `key = "#p0"`; updater `change(String id, String status)` nên dùng key nào để xóa đúng entry?

**Đáp án:** `key = "#p0"` nếu đối số đầu là ID giống reader, cùng `cacheNames`.

**2.** Vì sao bỏ `key` trong updater hai tham số dễ dẫn tới stale?

**Đáp án:** `SimpleKeyGenerator` dùng cả hai tham số để tạo key tổng hợp, khác với key chỉ chứa ID ở reader.

**3.** Với `beforeInvocation = false`, update ném exception có xóa entry không?

**Đáp án:** Không, eviction sau invocation mặc định chỉ thực hiện khi method kết thúc thành công.

**4.** Vì sao không nên dùng `allEntries = true` cho cập nhật một SKU?

**Đáp án:** Nó xóa toàn vùng cache, bao gồm entry của SKU không thay đổi, làm tăng cache miss không cần thiết.

**5.** Vì sao một reader có thể cache lại giá trị cũ sau khi updater đã evict?

**Đáp án:** Reader đó có thể lấy giá trị cũ trước khi cập nhật hoàn tất hoặc trước commit, rồi thực hiện cache put sau thời điểm eviction. Cần chiến lược nhất quán phù hợp.

## 11. Ghi nhớ và tài liệu chính thức

- `@CacheEvict` **vô hiệu hóa entry**, không tự ghi dữ liệu nguồn.
- Với mục tiêu một key, đặt đúng `cacheNames` và `key`, giữ `allEntries = false`.
- **Key reader và evictor phải khớp**; chú ý method update thường có nhiều đối số.
- Mặc định Spring evict **sau method thành công**. `beforeInvocation = true` xóa trước kể cả khi method về sau thất bại.
- Trong hệ thống thực, cần xem thêm transaction/commit, race condition, proxy và phạm vi cache giữa các instance.

Tài liệu tham khảo:

- [Spring Framework 6.2 — Cache Annotations](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)
- [Spring Framework — CacheEvict API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/annotation/CacheEvict.html)
- [Spring Framework — Cache API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework — TransactionAwareCacheManagerProxy](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html)
