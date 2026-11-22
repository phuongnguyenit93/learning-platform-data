# Phương thức void làm tác nhân xóa cache với @CacheEvict

## Mục tiêu

Khi một phương thức làm thay đổi dữ liệu gốc (cập nhật giá, xóa sản phẩm, nhập lại cấu hình…), giá trị đã được lưu bởi Spring Cache có thể trở nên cũ. `@CacheEvict` cho phép biến chính **lời gọi phương thức nghiệp vụ** thành tác nhân loại bỏ entry cũ. Điều quan trọng: phương thức đó **có thể trả về `void`**, vì xóa cache không cần lấy giá trị trả về để lưu.

Sau bài này, bạn có thể:

- Giải thích vì sao `void` phù hợp với `@CacheEvict` nhưng không phù hợp để tạo giá trị cache bằng `@Cacheable`/`@CachePut`.
- Theo dõi thứ tự **ghi dữ liệu gốc → xóa entry cache → lần đọc tiếp theo nạp lại**.
- Chọn `cacheNames`, `key`, `allEntries`, `beforeInvocation` đúng phạm vi.
- Hiểu tác động của exception, transaction, proxy AOP và nhiều instance.
- Chạy một demo Java 17 kiểm chứng trạng thái cache trước và sau khi gọi một phương thức `void`.

## 1. Tại sao phương thức void vẫn xóa được cache?

Giả sử hệ thống đọc giá sản phẩm từ cơ sở dữ liệu:

~~~java
@Cacheable(cacheNames = "prices", key = "#p0")
public int getPrice(String sku) {
    return repository.findPrice(sku);
}
~~~

Đây là đoạn minh họa; `repository` do ứng dụng cung cấp. Với SKU `"A"`, sau lần đọc đầu, cache có thể chứa:

~~~text
Cache "prices"
    key "A" -> value 100
~~~

Nếu sau đó giá trong database thay đổi thành 120 nhưng entry chưa bị loại bỏ, lần gọi `getPrice("A")` có thể **hit** và trả 100. Một phương thức cập nhật không cần trả dữ liệu:

~~~java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updatePrice(String sku, int newPrice) {
    repository.updatePrice(sku, newPrice);
}
~~~

Khi một caller gọi `updatePrice("A", 120)` qua Spring proxy và phương thức chạy **thành công**, Spring xóa entry `"A"` trong cache `"prices"`. Lần đọc sau miss, tải lại 120 và có thể cache giá trị mới.

Ở đây `void` có ý nghĩa: phương thức chỉ **kích hoạt việc loại bỏ entry**. `@CacheEvict` không cần đọc `return` để biết phải xóa cái gì; cache name và key được suy ra từ annotation và đối số. Ngược lại, `@Cacheable` và `@CachePut` thường cần kết quả trả về để đưa vào cache.

**Đừng hiểu nhầm:** `void` không tự xóa cache. Chính `@CacheEvict` được xử lý bởi cơ chế caching của Spring mới làm điều đó. Phương thức `void` không có annotation (hoặc không đi qua interceptor) sẽ không tự động thay đổi cache.

## 2. Luồng xử lý chuẩn: void + @CacheEvict mặc định

Giả sử cả getter và updater đều sử dụng `cacheNames = "prices"` và key `#p0`.

~~~text
1) getPrice("A")
       |
       v
   Cache("prices").get("A")
       |
       +-- MISS -> đọc DB: 100 -> put("A", 100) -> trả 100

2) updatePrice("A", 120)   [phương thức void]
       |
       v
   Spring cache interceptor
       |
       v
   Gọi phần thân: cập nhật DB thành 120
       |
       +-- thành công --> evict("A") --> return void
       |
       +-- ném exception -> mặc định KHÔNG evict

3) getPrice("A")
       |
       v
   Cache("prices").get("A")
       |
       +-- MISS -> đọc DB: 120 -> put("A", 120) -> trả 120

4) getPrice("A")
       |
       +-- HIT -> trả 120, không chạy getter
~~~

Một điểm quan trọng về vị trí: `@CacheEvict` mặc định có `beforeInvocation = false`, tức eviction xảy ra **sau khi phương thức được gọi thành công**. `@CacheEvict` không đảm bảo database transaction đã commit (phân tích ở mục 7).

### Có cần cache đang chứa key hay không?

Không. Gọi một updater `void` mang `@CacheEvict` vẫn hợp lệ nếu cache chưa có entry tương ứng. Thao tác xóa entry vắng mặt thông thường không có thay đổi dữ liệu cache; mục đích là đảm bảo lần đọc về sau không tái sử dụng giá trị cũ.

Phương thức gắn `@CacheEvict` **không bị bỏ qua chỉ vì cache đã hit**. Nó khác với một getter `@Cacheable`: updater phải được thực thi để thực hiện nghiệp vụ, sau đó eviction được xử lý theo cấu hình.

## 3. Ba lớp trách nhiệm phải tách bạch

| Lớp | Chịu trách nhiệm | Ví dụ |
| --- | --- | --- |
| Nghiệp vụ | Ghi/xóa dữ liệu gốc, validate đầu vào, phân quyền | `repository.updatePrice(sku, newPrice)` |
| Spring Cache | Xác định cache, tạo key, điều phối `evict` theo annotation | `@CacheEvict(cacheNames="prices", key="#p0")` |
| Cache provider | Thực hiện xóa entry thực tế; quyết định đặc tính phân tán/tồn tại | ConcurrentMap, Caffeine, Redis |

`@CacheEvict` không có nghĩa Spring sẽ tự cập nhật database. Nếu thân phương thức chỉ in log hoặc không ghi dữ liệu thật, cache vẫn có thể bị xóa nhưng dữ liệu gốc không đổi. Lần đọc sau sẽ lấy lại đúng dữ liệu cũ từ nguồn.

Ngược lại, cập nhật database mà quên evict/refresh cache có thể làm hệ thống tiếp tục trả giá trị stale.

## 4. Lựa chọn key: trỏ đúng entry cần xóa

### 4.1. Cùng cache name và cùng quy tắc key với getter

~~~java
// Đọc: dùng SKU làm key.
@Cacheable(cacheNames = "prices", key = "#p0")
public int getPrice(String sku) {
    return repository.findPrice(sku);
}

// Ghi: SKU cũng là đối số thứ nhất; xóa chính key đó.
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updatePrice(String sku, int newPrice) {
    repository.updatePrice(sku, newPrice);
}
~~~

Cả hai đoạn là minh họa, chưa độc lập vì thiếu `repository`. `#p0` là tham số thứ nhất của từng phương thức. Trong updater, tham số thứ hai `newPrice` **không** tham gia key vì đã chỉ định `key = "#p0"`.

Nếu bỏ `key`, Spring mặc định dùng `SimpleKeyGenerator`. Getter có **một** tham số `sku` có thể sử dụng chính chuỗi `sku` làm key; updater có **hai** tham số `sku` và `newPrice` sẽ tạo một composite key gồm cả hai. Khi ấy updater có nguy cơ xóa nhầm key (thực tế không xóa entry mà getter đang dùng). Vì vậy, với các phương thức nhận tham số khác nhau, **hãy chỉ định key rõ ràng**.

### 4.2. Bảng những lỗi không khớp key

| Getter | Void updater | Hậu quả |
| --- | --- | --- |
| `prices` / `#p0` | `prices` / `#p0` | Xóa đúng entry theo SKU |
| `prices` / `#p0` | `prices` / mặc định 2 tham số | Có thể xóa sai key; bản cũ còn tồn tại |
| `prices` / `#p0` | `products` / `#p0` | Xóa ở sai vùng cache |
| Key dạng `tenant + ":" + sku` | Chỉ key `sku` | Entry theo tenant không bị xóa |
| Getter theo mã đã chuẩn hóa | Updater dùng mã chưa chuẩn hóa | Có thể không khớp ký tự key |

Đối với hệ thống đa tenant, key nên chứa tenant ID hoặc cách phân vùng cache phù hợp để việc xóa không ảnh hưởng dữ liệu của tenant khác. Trường hợp có nhiều cache cùng chứa thông tin phụ thuộc vào một thực thể, cần thiết kế chính sách invalidation cho **tất cả vùng liên quan**, thay vì chỉ một entry.

### 4.3. Sử dụng SpEL đúng ngữ cảnh

~~~java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updatePrice(String sku, int price) { /* ... */ }

// Cách khác: tham số đầu qua root.args.
@CacheEvict(cacheNames = "prices", key = "#root.args[0]")
public void deletePrice(String sku) { /* ... */ }
~~~

Đây là snippet minh họa. `#p0`/`#root.args[0]` tránh phụ thuộc tên tham số Java có được lưu trong bytecode hay không. Nếu dùng `#sku`, hãy chắc chắn cấu hình biên dịch có metadata tên tham số (ví dụ `-parameters`). Với phương thức `void`, **không dựa vào `#result`** để tạo key: không có kết quả nghiệp vụ nào đáng dùng. Hãy dựa vào đối số, đối tượng/ngữ cảnh phù hợp hoặc custom `KeyGenerator`.

### 4.4. Điều kiện trước khi xóa

~~~java
@CacheEvict(
    cacheNames = "prices",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()"
)
public void updatePrice(String sku, int price) { /* ... */ }
~~~

`condition` là biểu thức SpEL xác định operation có cần thực hiện hay không. Nếu condition false, thân phương thức nghiệp vụ vẫn có thể chạy, nhưng eviction đó bị bỏ qua. Điều kiện sai có thể gây stale cache, đặc biệt nếu dữ liệu gốc vẫn được cập nhật. Cần kiểm tra logic này cẩn thận.

## 5. beforeInvocation: xóa sau hay trước phần thân void?

Hai cấu hình phổ biến:

~~~java
// Mặc định: xóa nếu phương thức hoàn tất bình thường.
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updateAfter(String sku, int price) { /* ghi DB */ }

// Xóa TRƯỚC khi gọi phương thức, bất kể thân method có lỗi sau đó.
@CacheEvict(cacheNames = "prices", key = "#p0", beforeInvocation = true)
public void invalidateFirst(String sku) { /* làm việc tiếp */ }
~~~

Cả hai là snippet, không phải file runnable.

| Thuộc tính | Mặc định: `beforeInvocation=false` | `beforeInvocation=true` |
| --- | --- | --- |
| Thời điểm evict | Sau khi method thực thi thành công | Trước khi method bắt đầu chạy |
| Method ném exception | Không evict theo operation này | Eviction đã được yêu cầu thực hiện |
| Cache có thể bị xóa dù cập nhật thất bại? | Thông thường không do chính operation đó | Có |
| Khi thích hợp | Cập nhật/xóa thành công rồi invalidate | Muốn buộc invalidation không phụ thuộc kết quả method |

Ví dụ quy trình cập nhật giá: **thường dùng mặc định**, vì không muốn xóa cache khi yêu cầu bị chặn trước khi thay đổi dữ liệu gốc. Tuy vậy, chỉ đánh giá “xóa sau là an toàn” khi xem đầy đủ transaction và concurrency.

Trường hợp `beforeInvocation=true` có thể dùng cho tác vụ khởi động làm mới, chủ động xóa dữ liệu dẫn xuất trước một hoạt động; nhưng nếu ngay sau eviction có người đọc trong lúc database chưa cập nhật, họ có thể cache lại giá cũ. Do đó, xóa trước không tự khắc phục race condition.

### Exception và side effect

Giả sử một phương thức `void` ghi dữ liệu gốc một phần rồi ném exception:

~~~java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void riskyUpdate(String sku, int price) {
    repository.savePrice(sku, price);
    downstreamService.notifyChange(sku); // có thể lỗi
}
~~~

Đây là đoạn minh họa. Nếu `notifyChange` ném exception mà dữ liệu gốc **đã lưu thành công và không rollback**, `@CacheEvict` mặc định **không xóa** entry, dẫn đến stale cache. Với transaction có rollback nhất quán, dữ liệu gốc cũng có thể trở về trạng thái cũ; đó là một tình huống khác. Hãy thiết kế ranh giới transaction, lệnh gọi bên ngoài và chính sách invalidation dựa trên trường hợp thực tế.

## 6. Xóa một key hay toàn bộ vùng cache?

### Xóa một entry: phù hợp với cập nhật một đối tượng

~~~java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void changePrice(String sku, int price) { /* ... */ }
~~~

Ví dụ cập nhật `"A"` chỉ invalidate cache entry tương ứng. Các entry `"B"`, `"C"` không cần tải lại.

### Xóa toàn bộ: allEntries = true

~~~java
@CacheEvict(cacheNames = "prices", allEntries = true)
public void reloadCatalog() {
    repository.reloadAllPrices();
}
~~~

Snippet minh họa; `repository` không được định nghĩa. Sau khi method thành công, Spring yêu cầu cache xóa toàn bộ entries trong vùng `"prices"`. Với `allEntries=true`, không cần tính một key riêng. Không nên kết hợp thêm `key` để kỳ vọng chỉ xóa một vài entry: `allEntries` biểu diễn ý định xóa toàn bộ vùng, không theo key.

**Đánh đổi:** `allEntries=true` đơn giản nhưng có thể khiến nhiều request sau đó đồng loạt miss, tạo tải lớn lên DB hoặc API. Dùng key cụ thể nếu bạn biết chính xác entry bị ảnh hưởng; dùng xóa toàn vùng khi nhiều entry dẫn xuất bị thay đổi hoặc không thể xác định tập key chịu tác động.

## 7. Void eviction, giao dịch DB và tính nhất quán dữ liệu

**Phân biệt hai khái niệm:**

- **Method completion:** thân method hoàn tất bình thường, không ném exception.
- **Transaction commit:** database thật sự chốt thay đổi.

`beforeInvocation=false` chỉ nói về thời điểm tương đối với **lời gọi method được interception**; nó không tự bảo đảm việc xóa cache diễn ra **sau commit** trong mọi kết hợp AOP/transaction. Khi dùng `@Transactional`, thứ tự advice, đường gọi và cache manager có thể ảnh hưởng thời điểm.

Một race điển hình:

~~~text
T1: Bắt đầu cập nhật giá A từ 100 -> 120 trong transaction
T1: Xóa entry cache A khi transaction chưa commit
T2: Đọc A -> cache miss
T2: DB vẫn nhìn thấy 100 -> cache.put(A, 100)
T1: Commit thành công giá 120
T3: Đọc A -> cache hit 100 (stale)
~~~

Để phòng ngừa, hãy cân nhắc **evict sau commit** khi ứng dụng cần nhất quán mạnh hơn: dùng transaction-aware cache phù hợp, transaction synchronization hoặc phát sự kiện sau commit để invalidation. Đây không phải tự động xảy ra chỉ nhờ thêm `@CacheEvict`. Nếu hệ thống phân tán, còn cần tính đến các instance, replication, thời gian truyền và khả năng cache stampede.

Cũng cần phân biệt `@CacheEvict` với `@CachePut`:

| Annotation | Mục đích | Có bỏ qua thân method khi hit? | Hành động cache |
| --- | --- | --- | --- |
| `@Cacheable` | Tái sử dụng kết quả | Có thể | Đọc, và lưu kết quả khi miss |
| `@CachePut` | Chạy method rồi lưu kết quả mới | Không | Put kết quả trả về |
| `@CacheEvict` | Invalidate kết quả cũ | Không | Evict key hoặc clear cache |

Dùng `void` với `@CacheEvict` vì output không quan trọng đối với eviction. Nếu muốn **thay** entry bằng dữ liệu mới mà không đợi một lần đọc tiếp theo, hãy cân nhắc `@CachePut` trên một phương thức **trả về giá trị cần cache**, hoặc chủ động quản lý cache phù hợp với kiến trúc. Đừng giả định annotation có thể tự suy ra giá trị mới từ một method `void`.

## 8. Demo đầy đủ Java 17 + Maven: void updater khiến lần đọc sau miss

Demo này chạy Spring Framework 6.2.x bằng Java 17, dùng `ConcurrentMapCacheManager` để lưu trong bộ nhớ. Map `database` mô phỏng nguồn dữ liệu gốc, bộ đếm chứng minh getter thực sự được gọi hay bị bỏ qua. Không cần Spring Boot hay Redis.

### 8.1. Cấu trúc thư mục

~~~text
void-cache-evict/
├── pom.xml
└── src/main/java/demo/VoidEvictDemo.java
~~~

### 8.2. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>void-cache-evict</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. File src/main/java/demo/VoidEvictDemo.java

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class VoidEvictDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class AppConfig {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("prices");
        }

        @Bean
        public PriceService priceService() {
            return new PriceService();
        }
    }

    public static class PriceService {
        // Mô phỏng database: là nguồn dữ liệu, KHÔNG phải cache.
        private final Map<String, Integer> database =
                new ConcurrentHashMap<>();
        private final AtomicInteger dbReads = new AtomicInteger();

        public PriceService() {
            database.put("A", 100);
        }

        @Cacheable(cacheNames = "prices", key = "#p0")
        public int getPrice(String sku) {
            Integer price = database.get(sku);
            if (price == null) {
                throw new IllegalArgumentException("Unknown SKU: " + sku);
            }
            int n = dbReads.incrementAndGet();
            System.out.println("DB_READ " + sku + " #" + n + " = " + price);
            return price;
        }

        // Đầu ra void: Spring dùng SKU làm key, KHÔNG dùng return.
        @CacheEvict(cacheNames = "prices", key = "#p0")
        public void updatePrice(String sku, int newPrice) {
            database.put(sku, newPrice);
            System.out.println("DB_WRITE " + sku + " = " + newPrice);
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                AppConfig.class)) {
            PriceService service = context.getBean(PriceService.class);
            Cache cache = Objects.requireNonNull(
                    context.getBean(CacheManager.class).getCache("prices"));

            System.out.println(
                    "Before read, cache A? " + (cache.get("A") != null));

            System.out.println("read1 = " + service.getPrice("A"));
            System.out.println("read2 = " + service.getPrice("A"));

            service.updatePrice("A", 120);
            System.out.println(
                    "After update, cache A? " + (cache.get("A") != null));

            System.out.println("read3 = " + service.getPrice("A"));
            System.out.println("read4 = " + service.getPrice("A"));
        }
    }
}
~~~

### 8.4. Chạy thử

Trong thư mục `void-cache-evict`, cần JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.VoidEvictDemo
~~~

Stdout do chương trình in ra (không tính các thông báo riêng của Maven/môi trường):

~~~text
Before read, cache A? false
DB_READ A #1 = 100
read1 = 100
read2 = 100
DB_WRITE A = 120
After update, cache A? false
DB_READ A #2 = 120
read3 = 120
read4 = 120
~~~

Giải thích:

1. Trước `read1`, chưa có mapping `"A"`. Getter miss, đọc nguồn một lần và lưu 100.
2. `read2` hit nên không xuất hiện dòng `DB_READ A #2` vào lúc này.
3. `updatePrice` **không trả kết quả**. Body ghi 120, sau đó `@CacheEvict` xóa entry `"A"`. `After update, cache A? false` chứng minh việc xóa.
4. `read3` miss và nạp 120; `dbReads` tăng thành 2.
5. `read4` hit với 120, không có thêm `DB_READ`.

Dù bộ nhớ cache và “database” đều nằm trong ứng dụng demo, chúng là **hai đối tượng riêng**. Demo chỉ minh họa đúng luồng Spring cache; nó không thay thế kiểm chứng tính nhất quán của database thật, Redis, transaction và nhiều node.

### 8.5. Vì sao phải lấy bean từ ApplicationContext?

Ví dụ cố ý gọi:

~~~java
PriceService service = context.getBean(PriceService.class);
service.updatePrice("A", 120);
~~~

Nhờ vậy lời gọi đi qua Spring-managed bean và proxy caching. Nếu bạn viết `new PriceService().updatePrice(...)` bên ngoài container, hoặc dùng `this.updatePrice(...)` từ chính class `PriceService` trong chế độ proxy mặc định, interceptor có thể không chạy, nên annotation không tạo hiệu ứng xóa cache. Trong cùng class, nên tổ chức lời gọi qua một bean/service khác hoặc thiết kế lại boundary thay vì trông chờ self-invocation.

## 9. Phương thức void không nhất thiết phải thay đổi database

Một phương thức `void` cũng có thể chỉ là hành động invalidation tường minh:

~~~java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void invalidatePrice(String sku) {
    // Không cần trả về giá trị và không cần tự gọi Cache.evict().
}
~~~

Đây là snippet minh họa. Một caller có thể gọi method này khi biết dữ liệu bên ngoài vừa đổi. Tuy nhiên, nếu chỉ cần xóa cache, ứng dụng cũng có thể dùng `CacheManager`/`Cache` programmatically; điều quan trọng là chọn một ranh giới rõ ràng, tránh một “method giả” bị gọi nội bộ làm proxy không có tác dụng.

Một biến thể khác, khi cập nhật cả danh mục:

~~~java
@CacheEvict(cacheNames = "prices", allEntries = true)
public void importNewPriceList() {
    repository.importPrices();
}
~~~

Method `void` vẫn được chấp nhận; lần này trigger yêu cầu xóa **toàn bộ cache "prices"**, không cần xác định từng SKU. Các snippet trên không độc lập và cần tích hợp vào service, repository và cấu hình Spring cụ thể.

## 10. Tác động của exception, cache provider và môi trường chạy

### 10.1. Nếu không tìm thấy entry

Một lời gọi `evict("A")` không tạo value mới và không tự chạy getter. Nếu entry `"A"` không có, thao tác chỉ loại bỏ khả năng dùng lại entry đó; lần đọc tiếp theo mới quyết định hit/miss theo trạng thái thực tế khi tra cache.

### 10.2. Nếu provider evict lỗi

Lỗi từ backend cache (Redis mất kết nối, permission, serialization…) không giống lỗi nghiệp vụ. Spring có `CacheErrorHandler` để tùy chỉnh phản ứng khi thao tác cache thất bại; mặc định các lỗi cache có thể bị truyền lên caller. Chính sách bỏ qua lỗi cache có thể giúp API tiếp tục, nhưng cần đánh giá rủi ro **trả dữ liệu stale** nếu eviction thất bại.

### 10.3. Nếu có nhiều instance

`ConcurrentMapCacheManager` trong demo giữ dữ liệu trong JVM, không tự đồng bộ với các JVM khác. Nếu instance A cập nhật DB và chỉ evict cache local của A, instance B có thể vẫn có bản cũ. Có thể dùng backend chia sẻ (ví dụ Redis), cơ chế phân phối invalidation, hay thiết kế TTL phù hợp. **Cùng annotation không đồng nghĩa mọi instance đều thấy cùng kết quả eviction.**

### 10.4. Nếu nhiều người đọc/ghi cùng lúc

`@CacheEvict` không tự tạo khóa đồng bộ toàn cục giữa việc ghi DB và đọc cache. Một reader có thể nạp giá cũ đúng lúc updater chưa commit. Đánh giá transaction boundary, key strategy, cache provider và đường cập nhật bất đồng bộ khi cần yêu cầu consistency cao hơn.

## 11. Bảng kiểm thử nên có

| Test case | Các bước | Kết quả mong đợi |
| --- | --- | --- |
| Xóa đúng key | Cache A=100, B=200; gọi updater cho A | Entry A mất; B còn |
| Không có entry | Cache rỗng; gọi updater cho A | Method vẫn chạy; không phát sinh entry từ evict |
| Updater thành công | Cache A=100; DB đổi A=120 | Lần đọc A tiếp theo miss và lấy 120 |
| Updater ném exception, mặc định | Cache A=100; method ném exception | Eviction mặc định không chạy |
| `beforeInvocation=true` | Cache A=100; method ném exception | Eviction đã xảy ra trước khi method ném lỗi |
| Khác key | Getter key SKU, updater key SKU+price | Không xóa đúng entry getter đã lưu |
| Xóa toàn vùng | A/B có entry; gọi `allEntries=true` | Các entry trong cache tương ứng bị loại bỏ |
| Gọi nội bộ không qua proxy | Method trong cùng class gọi `this.updatePrice(...)` | Không nên kỳ vọng advice của `@CacheEvict` chạy |
| Cập nhật trước commit | Reader miss khi DB transaction còn mở | Cần kiểm tra nguy cơ repopulate dữ liệu cũ |

Một unit test chỉ khởi tạo đối tượng bằng `new` không kiểm tra được Spring AOP. Để test annotation thật sự, dùng Spring application context và cache manager thực hoặc test double, khởi động bean có `@EnableCaching` rồi gọi qua proxy như demo. Khi test tích hợp database/Redis, cần thiết lập dữ liệu sạch, kiểm chứng đúng key/TTL và xem transaction commit thực tế.

## 12. Lỗi thường gặp và cách sửa

**Lỗi: “Vì update method trả void nên Spring không biết phải xóa gì”.** Sai. Annotation chỉ định cache name và key; return value không cần thiết. Nếu sau khi gọi vẫn còn entry, kiểm tra key, proxy, thời điểm evict và provider.

**Lỗi: “Mọi method cập nhật nên dùng @Cacheable”.** Sai. `@Cacheable` có thể bỏ qua body khi hit; một lệnh cập nhật nghiệp vụ không được phép bị bỏ qua. Dùng `@CacheEvict` để invalidation sau cập nhật, hoặc `@CachePut` để put một kết quả có giá trị khi phù hợp.

**Lỗi: “Không chỉ định key cũng giống getter một tham số”.** Sai nếu updater nhận nhiều tham số. Mặc định key lấy từ **toàn bộ danh sách tham số**, có thể không trùng với key của getter. Khai báo `key="#p0"` khi nghiệp vụ định danh theo SKU.

**Lỗi: “beforeInvocation=false nghĩa là sau commit DB”.** Không có bảo đảm chung như vậy. Nó chỉ là sau khi method được invoke thành công theo cache interceptor. Nếu cần after-commit semantics, hãy thiết kế rõ.

**Lỗi: “allEntries=true chỉ xóa entry của tham số hiện tại”.** Sai. Nó là xóa toàn bộ các entries trong vùng cache khai báo; cần tránh dùng tùy tiện khi tải lớn.

**Lỗi: “Gọi this.updatePrice(...) vẫn chạy @CacheEvict”.** Không đúng trong proxy mode thông dụng. Gọi từ bên ngoài qua Spring proxy mới được interception.

**Lỗi: “Xóa cache chính là cập nhật dữ liệu”.** Eviction **không thay đổi giá trong DB** và **không lưu giá mới vào cache**. Nó chỉ ngăn đọc lại entry cũ; getter lần sau có thể repopulate.

## 13. Câu hỏi tự kiểm tra

1. **Vì sao `void` hợp lệ với `@CacheEvict`?** Vì kết quả trả về bị bỏ qua; lời gọi phương thức chỉ là trigger để xóa entry dựa trên cấu hình cache/key.
2. **Getter có một tham số SKU, updater có SKU và giá mới: có nên bỏ `key` ở cả hai?** Không nên. Default key generator của hai lời gọi tạo key khác cấu trúc; nên dùng cùng key expression, ví dụ `#p0`.
3. **Method void ném exception thì `@CacheEvict` mặc định có xóa không?** Không, eviction sau invocation thông thường chỉ chạy khi method hoàn tất thành công. Với `beforeInvocation=true`, eviction diễn ra trước khi body chạy.
4. **Sau evict, cache có tự chứa giá mới chưa?** Không. Việc nạp lại thường diễn ra khi gọi getter `@Cacheable` sau đó, hoặc bằng một quy trình populate khác.
5. **@CacheEvict có tự đồng bộ dữ liệu nhiều instance không?** Không. Phụ thuộc backend cache, transaction và cách phân phối invalidation.

## Kết luận

Một phương thức `void` mang `@CacheEvict` là **tác nhân xóa cache**, không phải hàm cung cấp giá trị mới. Quy tắc đọc luồng là: **chạy nghiệp vụ → (mặc định, nếu thành công) evict đúng cache/key → lần đọc tiếp theo miss và nạp lại**. Khi áp dụng thực tế, tập trung vào sự khớp giữa key của getter/updater, `beforeInvocation`, ngoại lệ, transaction và môi trường nhiều instance. Đây là những yếu tố quyết định việc eviction có giúp tránh dữ liệu cũ thật sự hay không.

## Tài liệu chính thức

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Annotation-based Caching (`@CacheEvict`, `@Cacheable`, `@CachePut`): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Javadoc `@CacheEvict`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
- Javadoc `Cache` interface: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/Cache.html
