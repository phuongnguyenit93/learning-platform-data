# @CachePut: Điều kiện cập nhật và thời điểm có kết quả

## Mục tiêu học tập

Trong Spring Framework Cache Abstraction, **@CachePut** dùng để ghi hoặc thay thế một entry bằng **giá trị mà phương thức vừa trả về**. Bài này giúp bạn nắm vững: (1) khi nào phương thức vẫn chạy; (2) lúc nào **condition** và **unless** được đánh giá; (3) lúc nào có **#result** để tạo khóa hoặc chặn cập nhật; (4) ảnh hưởng đối với entry đang tồn tại; và (5) cách kiểm thử hành vi thực tế mà không nhầm lẫn giữa cập nhật nguồn dữ liệu và cập nhật cache.

Ngữ cảnh: Spring Framework 6.x với annotation caching qua Spring AOP proxy. Ví dụ chạy độc lập dùng Java 17, Maven và ConcurrentMapCacheManager; các nhận định về trình tự được tách khỏi chính sách TTL, eviction hay tính phân tán của provider.

## 1. Phân biệt phương thức nghiệp vụ và thao tác ghi cache

Xét lệnh cập nhật một sản phẩm. Phương thức có thể sửa nguồn dữ liệu, trả về đối tượng sau cập nhật, sau đó Spring quyết định có đưa đối tượng ấy vào cache hay không.

~~~text
Caller gọi bean qua Spring proxy
          |
          v
Spring đọc @CachePut và xét condition (trước khi có #result)
          |
          v
Phương thức nghiệp vụ LUÔN được gọi trong lời gọi @CachePut bình thường
          |
          +-- Ném exception --> không có kết quả thành công để put
          |
          +-- Trả về result
                   |
                   v
             Nếu condition cho phép, xét unless
                   |
           +-------+--------+
           |                |
      unless = true    unless = false
       bỏ thao tác      tính key (có thể
       put cache        dùng #result) và put
           |                |
           +-------+--------+
                   |
                   v
          Trả kết quả cho caller
~~~

Sơ đồ mô tả **phương thức đồng bộ trả về bình thường**, nơi operation không có xử lý bất đồng bộ đặc biệt. Spring Framework 6.1+ còn hỗ trợ kiểu trả về CompletableFuture và reactive; cách xác định thời điểm hoàn thành được nêu ở mục 10.

Điểm cốt lõi:

- **@CachePut luôn thực thi phương thức đích khi lời gọi đi qua caching interceptor.** Một cache hit đã tồn tại không ngăn thực thi như @Cacheable.
- **condition** chỉ quyết định operation **có đủ điều kiện ghi cache** dựa trên context trước lời gọi. Khi false, **phương thức vẫn chạy** nhưng Spring bỏ qua thao tác put của annotation đó.
- **unless** là điều kiện **phủ quyết** thao tác ghi: sau khi có kết quả, nếu biểu thức trả true thì **không put**.
- Nếu cả condition cho phép và unless không phủ quyết, Spring đưa **kết quả phương thức** vào cache theo key được tạo.
- Bỏ qua put **không đồng nghĩa xóa một entry cũ**. Một cache có thể tiếp tục giữ dữ liệu cũ theo đúng key.

Điều này giúp bạn xác định đúng nơi đặt điều kiện: có thể dựa vào đầu vào để chọn condition; nếu điều kiện phụ thuộc đối tượng đã tạo/cập nhật, dùng unless.

## 2. Bảng thời điểm: condition, unless, key và #result

| Thành phần @CachePut | Được đánh giá khi nào? | Truy cập #result? | Mục đích |
| --- | --- | --- | --- |
| **condition** | Trước khi thực thi phương thức | **Không** | Chỉ cho phép put nếu điều kiện đầu vào đúng |
| **unless** | Sau khi phương thức trả kết quả thành công | **Có** | Phủ quyết put dựa vào kết quả |
| **key** dạng SpEL | Khi chuẩn bị ghi cache, sau khi có kết quả | **Có** | Chọn danh tính entry sẽ được cập nhật |
| **keyGenerator** | Khi Spring cần key và không chọn key SpEL | Nhận tham số target, method, params; **không** nhận result qua signature | Tính key bằng Java |
| **Kết quả method** | Sau khi phương thức hoàn thành | Chính là dữ liệu được put | Cache value |

**#result** là biến đặc biệt trong caching SpEL context; nó **không** phải biến cục bộ Java. Spring cho phép dùng #result trong **@CachePut key** và **unless** vì tại thời điểm ấy phương thức đã tạo ra giá trị trả về. Với **condition**, không có kết quả để xét: dùng #result trong condition là một thiết kế sai thời điểm.

Một số biểu thức SpEL:

~~~java
// Đoạn annotation minh họa. Mỗi @CachePut thuộc một method riêng.
@CachePut(cacheNames = "products", condition = "#p1")
@CachePut(cacheNames = "products", unless = "#result == null")
@CachePut(cacheNames = "products", key = "#result.id()")
~~~

Trong đó **#p1** là đối số thứ hai (chỉ số 1), **#result.id()** gọi accessor của kết quả trả về theo cú pháp SpEL. Các dòng trên thể hiện **ba thuộc tính trên những ví dụ độc lập**. Trên cùng một method, bạn có thể phối hợp chúng trong **một annotation** khi thuộc tính và khóa nhất quán.

### Quy tắc true/false rất dễ nhầm

- **condition = true:** cho phép đi tiếp quy trình put; vẫn có thể bị **unless** phủ quyết.
- **condition = false:** bỏ qua put; **không bỏ qua** phương thức.
- **unless = true:** **không ghi cache**.
- **unless = false:** **ghi cache** nếu condition cho phép và không có lỗi khác.

Do đó, **unless không phải một condition thứ hai cùng ý nghĩa**; nó có tính chất phủ định và chạy sau lời gọi.

## 3. condition: kiểm tra trước khi phương thức chạy

Ví dụ một API chỉ cho phép ghi cache với dữ liệu công khai:

~~~java
@CachePut(cacheNames = "products", key = "#p0",
          condition = "#p2")
public Product save(String productId, ProductData data, boolean cacheAllowed) {
    return repository.save(productId, data);
}
~~~

Đây là đoạn minh họa, phụ thuộc lớp Product, ProductData và repository do ứng dụng định nghĩa. Ở đây:

1. **#p2** là tham số boolean cacheAllowed.
2. Nếu **cacheAllowed = true**, Spring tiếp tục xử lý put sau khi method trả về thành công.
3. Nếu **cacheAllowed = false**, **repository.save vẫn chạy**, dữ liệu gốc vẫn có thể được cập nhật, nhưng @CachePut **không ghi kết quả** vào cache.
4. Nếu cache đã có entry tương ứng từ trước, entry ấy **không tự biến mất** chỉ vì condition false.

Ví dụ khác, chỉ cache cho một tenant không thuộc nhóm nhạy cảm:

~~~java
@CachePut(cacheNames = "publicProfiles",
          key = "#p0",
          condition = "#p1 == 'PUBLIC'")
public Profile update(String id, String visibility) {
    return updateInStore(id, visibility);
}
~~~

Đây là minh họa, không chạy độc lập. Biểu thức so sánh đầu vào có thể thực hiện trước khi gọi phương thức. Nhưng với dữ liệu nhạy cảm, chỉ dùng condition để bỏ qua put là **chưa đủ**: nếu entry trước đó đã được cache, cần chiến lược invalidation tương ứng để tránh giữ profile cũ.

### Sai: cố dùng #result trong condition

~~~java
// SAI: condition được xét trước khi có kết quả.
@CachePut(cacheNames = "products",
          condition = "#result.approved()")
public Product save(ProductInput input) { ... }
~~~

Đoạn cố ý sai này không thể đáp ứng yêu cầu kiểm tra trạng thái trả về theo đúng trình tự. Khi cần xét trường approved **của kết quả**, hãy chuyển logic sang **unless**.

## 4. unless: phủ quyết sau khi có kết quả

Giả sử phương thức trả về bản ghi sản phẩm có cờ approved. Chỉ muốn cache kết quả approved = true:

~~~java
@CachePut(
    cacheNames = "products",
    key = "#result.id()",
    unless = "#result == null || !#result.approved()"
)
public Product save(ProductInput input) {
    return repository.save(input);
}
~~~

Đây là đoạn minh họa; Product cung cấp các phương thức id() và approved(), ví dụ là Java record. Thứ tự xử lý:

1. Gọi phương thức **save** để thay đổi nguồn dữ liệu.
2. Nếu gọi thành công, nhận result.
3. Kiểm tra **unless** trên result. Nếu null hoặc approved = false, không ghi.
4. Nếu approved = true, tính key từ result.id(), rồi cập nhật entry với giá trị result.

Kiểm tra **#result == null** trước giúp biểu thức không gọi approved() trên null. Với loại trả về có thể null, phải tự chọn policy phù hợp; nếu provider cho phép cache null, việc cache null cũng cần được cân nhắc riêng.

**Lưu ý:** unless chỉ phủ quyết **lần put đang xét**. Nếu trước đó cache đã chứa sản phẩm approved = true, còn lần cập nhật mới trả về approved = false, entry approved = true cũ **vẫn có thể còn trong cache**. Nếu chính sách yêu cầu “dữ liệu không được duyệt thì không được xuất hiện trong cache”, cần **xóa entry cũ** sau thay đổi, chứ không chỉ bỏ put mới.

### Phân biệt với unless của @Cacheable

Cả @CachePut và @Cacheable đều có unless chạy sau khi có result, nhưng:

| Annotation | Trước khi chạy method | Sau khi có result |
| --- | --- | --- |
| **@Cacheable** | Thường tra cứu cache và có thể trả ngay nếu hit | Nếu miss và unless false, đưa kết quả vào cache |
| **@CachePut** | Không dùng hit để bỏ qua method | Nếu condition cho phép và unless false, **put/replace** bằng kết quả mới |

Đừng dùng @CachePut như một cách tăng tốc phương thức đọc. Nó thường phù hợp với **phương thức tạo/cập nhật dữ liệu** mà mỗi lần gọi cần thực thi thực sự.

## 5. key dùng #result: biết khóa khi đã có kết quả

Một trường hợp phổ biến: khi tạo mới sản phẩm, ID được sinh ra **sau khi** ghi vào cơ sở dữ liệu. Trước lời gọi không thể biết ID đó; sau khi có Product result, có thể đặt khóa:

~~~java
@CachePut(cacheNames = "products", key = "#result.id()")
public Product create(ProductRequest request) {
    return repository.insert(request);
}
~~~

Đây là đoạn minh họa; ProductRequest và repository cần do ứng dụng cung cấp. Với Product record có accessor id(), biểu thức key trỏ tới **ID cuối cùng** do phương thức trả về.

Ví dụ dùng mã chuẩn hóa:

~~~java
@CachePut(
    cacheNames = "products",
    key = "#result.normalizedSku()",
    condition = "#p1",
    unless = "#result == null || !#result.visible()"
)
public Product update(String submittedSku, boolean cacheAllowed) {
    return repository.updateAndReturnNormalized(submittedSku);
}
~~~

**condition** chỉ xét cacheAllowed từ input. **unless** xét visible của output. **key** chọn normalizedSku từ output. Cả ba có thể đặt cùng @CachePut vì chúng có chức năng khác nhau và được xử lý ở thời điểm phù hợp.

Để một phương thức đọc **@Cacheable** tìm đúng entry mà @CachePut đã ghi, hai operation phải dùng **cùng cache name** và **cùng khóa logic**. Chẳng hạn:
- @CachePut ghi bằng **#result.normalizedSku()**.
- @Cacheable đọc bằng **#p0** nếu tham số đầu là SKU đã chuẩn hóa.
- Nếu @Cacheable nhận SKU thô, nó phải chuẩn hóa **tương đương**; nếu không, sẽ miss dù bản ghi đã được put.

### Đừng dùng #result trong @Cacheable(key=...)

@Cacheable cần tính key **trước khi tra cứu cache**. Vì vậy, **#result** không phải nguồn hợp lệ cho việc chọn lookup key trong @Cacheable. Khác biệt này là một lý do bài học cần phân biệt “thời điểm có kết quả” theo từng annotation, không áp dụng chung một quy tắc.

## 6. Ví dụ chạy được: Spring Framework + Java 17

Demo sẽ chứng minh trực tiếp:
- Method **save** luôn chạy dù condition=false hay unless=true.
- condition=true và unless=false ghi result vào cache với key lấy từ **#result.id()**.
- condition=false bỏ put nhưng **không xóa dữ liệu đã cache trước đó**.
- unless=true bỏ put nhưng **entry cũ có thể còn**.
- @Cacheable đọc cùng cache name/key có thể hit entry được @CachePut tạo.

Ví dụ dùng ConcurrentMapCacheManager trong **một JVM**. Không mô phỏng transaction hoặc TTL.

Cấu trúc:

~~~text
cache-put-timing/
├── pom.xml
└── src/main/java/demo/CachePutTimingDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-put-timing</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
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

**src/main/java/demo/CachePutTimingDemo.java**:

~~~java
package demo;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

public class CachePutTimingDemo {
    public record Item(String id, int amount, boolean approved) {}

    public static class ItemService {
        private final ConcurrentMap<String, Item> database =
            new ConcurrentHashMap<>();
        private final AtomicInteger updates = new AtomicInteger();
        private final AtomicInteger loads = new AtomicInteger();

        @CachePut(
            cacheNames = "items",
            condition = "#p2",
            unless = "!#result.approved()",
            key = "#result.id()"
        )
        public Item save(String submittedId, int amount,
                         boolean allowCachePut) {
            updates.incrementAndGet(); // Method luôn chạy.
            String id = submittedId.trim()
                .toUpperCase(Locale.ROOT);
            Item item = new Item(id, amount, amount >= 0);
            database.put(id, item);
            return item;
        }

        @Cacheable(cacheNames = "items", key = "#p0")
        public Item find(String normalizedId) {
            loads.incrementAndGet(); // Chỉ chạy nếu cache miss.
            return database.get(normalizedId);
        }

        public int updateCalls() { return updates.get(); }
        public int loadCalls() { return loads.get(); }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("items");
        }

        @Bean
        public ItemService itemService() {
            return new ItemService();
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            ItemService service = context.getBean(ItemService.class);
            Cache cache = context.getBean(CacheManager.class)
                .getCache("items");

            System.out.println("A1=" + service.save("a", 10, true));
            System.out.println("A find=" + service.find("A"));

            System.out.println("B1=" + service.save("b", 20, false));
            System.out.println("B in cache=" + (cache.get("B") != null));
            System.out.println("B find=" + service.find("B"));
            System.out.println("B2=" + service.save("b", 21, false));
            System.out.println("B find again=" + service.find("B"));

            System.out.println("C1=" + service.save("c", 5, true));
            System.out.println("C2=" + service.save("c", -1, true));
            System.out.println("C cached="
                + cache.get("C", Item.class));

            System.out.println("A2=" + service.save("a", 11, true));
            System.out.println("A find again=" + service.find("A"));
            System.out.println("updateCalls=" + service.updateCalls()
                + ", loadCalls=" + service.loadCalls());
        }
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CachePutTimingDemo
~~~

**Stdout từ các println trong chương trình** (không tính log của Maven nếu môi trường có in):

~~~text
A1=Item[id=A, amount=10, approved=true]
A find=Item[id=A, amount=10, approved=true]
B1=Item[id=B, amount=20, approved=true]
B in cache=false
B find=Item[id=B, amount=20, approved=true]
B2=Item[id=B, amount=21, approved=true]
B find again=Item[id=B, amount=20, approved=true]
C1=Item[id=C, amount=5, approved=true]
C2=Item[id=C, amount=-1, approved=false]
C cached=Item[id=C, amount=5, approved=true]
A2=Item[id=A, amount=11, approved=true]
A find again=Item[id=A, amount=11, approved=true]
updateCalls=6, loadCalls=1
~~~

Giải thích:

1. **A1:** allowCachePut=true, amount hợp lệ → condition true, unless false; result id "A" được ghi vào cache. **find("A")** hit nên không tăng loads.
2. **B1:** allowCachePut=false → condition false; method vẫn ghi Item B20 vào database nhưng **không put**. Kiểm tra trực tiếp cache cho thấy chưa có B. **find("B")** miss, tải B20 và tăng loads lên 1; @Cacheable lưu B20.
3. **B2:** allowCachePut=false nên database được cập nhật thành B21 nhưng @CachePut vẫn **bỏ ghi**. Entry B20 được @Cacheable lưu trước đó không bị xóa; **find("B")** tiếp tục hit B20. Đây là minh chứng về **stale cache** do bỏ put mà không invalidation.
4. **C1:** amount=5 → approved=true, C5 được ghi vào cache. **C2:** amount=-1 → approved=false, trượt điều kiện unless (unless true nên phủ quyết put); entry C5 còn trong cache, dù database đã đổi thành C-1.
5. **A2:** update tiếp A11 với điều kiện cho phép; cache entry A10 được **thay thế** bằng A11. **find("A")** trả A11 từ cache.
6. Có **sáu** lời gọi save nên updateCalls=6, kể cả các trường hợp condition=false hoặc unless=true. Chỉ có **một** lần find bị miss (B lần đầu), nên loadCalls=1.

Demo chủ đích giữ entry cũ để **lộ rõ lỗi stale khi bỏ put**. Ứng dụng thực tế cần thiết kế invalidation phù hợp, tránh trả dữ liệu cũ hoặc dữ liệu không còn được phép hiển thị.

### Vì sao @CachePut không đọc cache trước?

Annotation không dùng cache hit để bỏ qua lời gọi. Một phương thức update cần thực thi thao tác nghiệp vụ, nên Spring không được thay thế hành động update bằng giá trị từ cache như với @Cacheable. Việc get trực tiếp Cache trong demo chỉ phục vụ **kiểm thử**; đây không phải thao tác tự động của @CachePut.

## 7. Điều kiện cập nhật không phải cơ chế xóa cache

Bảng so sánh các tình huống khi **entry đã tồn tại**:

| Tình huống | Phương thức chạy? | Spring @CachePut có put mới? | Entry cũ |
| --- | --- | --- | --- |
| condition=true, unless=false, method thành công | Có | Có, ghi/thay thế | Được cập nhật theo key |
| condition=false | Có | Không | **Có thể còn** |
| condition=true, unless=true | Có | Không | **Có thể còn** |
| Method ném exception trước khi trả kết quả | Có và lỗi | Không có kết quả thành công để put | Thường vẫn còn nếu không có thao tác khác xóa |
| condition=true, method trả về null, unless không chặn | Có | Phụ thuộc khả năng xử lý null của Cache implementation | Có thể thành null/value wrapper hoặc gặp lỗi provider |

Muốn xóa entry khi dữ liệu không được phép cache nữa, cần một hành động xóa có chủ đích, chẳng hạn **@CacheEvict**, hoặc cập nhật cache nhất quán theo một chiến lược khác. @CacheEvict có thuộc tính **beforeInvocation** để chọn xóa trước/sau lời gọi, nhưng **@CachePut không có beforeInvocation**.

Ví dụ một operation xóa rõ ràng:

~~~java
@CacheEvict(cacheNames = "items", key = "#p0")
public void invalidate(String normalizedId) {
    // Phương thức xử lý yêu cầu invalidation.
}
~~~

Đoạn trên không độc lập, cần được đặt trong Spring bean và có @EnableCaching. Khi method invalidate được gọi qua proxy, cache "items" sẽ xóa entry có key là normalizedId sau khi method thành công, theo mặc định của @CacheEvict. Nếu database cũng cần thay đổi, thao tác nghiệp vụ và thời điểm invalidation phải được thiết kế phù hợp.

**Không nên tự động thêm @CacheEvict cùng @CachePut vào mọi method** mà không phân tích thứ tự AOP, điều kiện, tính nhất quán và transaction. Điều quan trọng là bảo đảm mọi lần cập nhật nguồn đều có chiến lược làm mới hoặc vô hiệu hóa dữ liệu cache tương ứng.

## 8. Các lỗi SpEL điển hình về thời điểm #result

| Khai báo | Đánh giá |
| --- | --- |
| **@CachePut(condition="#p0 != null")** | Hợp lệ: xét đầu vào trước lời gọi |
| **@CachePut(unless="#result == null")** | Hợp lệ: chặn lưu kết quả null sau lời gọi |
| **@CachePut(key="#result.id()")** | Hợp lệ nếu result khác null và có id() |
| **@CachePut(condition="#result.approved()")** | **Sai thời điểm:** condition không có result |
| **@CachePut(unless="#p1 == false")** | Hợp lệ về cú pháp: có thể xét input sau lời gọi; nhưng thường condition dễ diễn đạt hơn |
| **@Cacheable(key="#result.id()")** | **Sai thời điểm:** key cần có trước cache lookup |
| **@CacheEvict(beforeInvocation=true, key="#result.id()")** | **Sai thời điểm:** evict trước khi có result |
| **@CacheEvict(beforeInvocation=false, key="#result.id()")** | Có thể hợp lệ: mặc định xóa sau lời gọi, có result |

Nếu một SpEL expression yêu cầu property/method không tồn tại hoặc cố gọi thuộc tính của null, operation có thể ném lỗi đánh giá biểu thức. Những lỗi này không chứng minh method nghiệp vụ có vấn đề; cần kiểm tra chính xác context Spring cung cấp tại thời điểm evaluation.

**Đừng nhầm #result với tham số tên result.** Nếu method thật có tham số result, có thể tham chiếu theo **#p0**, **#p1**... hoặc tên được compiler giữ lại. Trong caching SpEL, **#result** là biến đặc biệt biểu diễn giá trị trả về sau method ở các phase được hỗ trợ.

Với tên tham số như **#productId**, trình biên dịch có thể cần cờ **-parameters**. **#p0**, **#a0** và **#root.args[0]** tránh phụ thuộc tên biến trong bytecode.

## 9. Thứ tự so với transaction và hành vi bất đồng bộ

### Transaction: “method trả về” chưa chắc “đã commit”

Khi có @Transactional, Spring Cache và Transaction là các advice khác nhau. **Thứ tự advice và cách tích hợp CacheManager với transaction ảnh hưởng việc cache được put trước hay sau commit**. Nếu cache đã ghi kết quả nhưng transaction sau đó rollback, cache có thể không phản ánh cơ sở dữ liệu.

Cần phân biệt:
- **Phương thức trả về thành công**: Spring đã có một result để xét unless và key.
- **Giao dịch đã commit**: dữ liệu nguồn đã được chấp nhận bền vững theo chính sách transaction.

Hai thời điểm này **không đương nhiên trùng nhau**. Với nghiệp vụ cần nhất quán cao, nên cân nhắc cập nhật/invalidation **sau commit**, cấu hình cache hỗ trợ transaction-aware (nếu phù hợp) hoặc sự kiện/outbox sau commit, rồi kiểm thử các trường hợp rollback. Không suy rằng @CachePut tự bảo đảm tính nguyên tử giữa database và kho cache.

### Future/Reactive (Spring Framework 6.1+)

Với các kiểu trả về được hỗ trợ như **CompletableFuture** và kiểu reactive, Spring Framework 6.1+ có khả năng thực hiện put **khi đối tượng kết quả được tạo ra/hoàn tất**, thay vì đơn thuần lưu wrapper đang chờ. Khi diễn giải #result, phải xét loại kết quả thực sự Spring cung cấp và phiên bản/framework configuration đang chạy. Không suy rằng callback put thành công ngay sau khi phương thức trả về CompletableFuture còn pending.

Lỗi thường gặp là kiểm thử một phương thức bất đồng bộ như thể kết quả đã được cache ngay khi có wrapper. Hãy đợi completion, sau đó mới kiểm tra cache và xử lý trường hợp future hoàn tất exceptional. Ví dụ ở mục 6 dùng phương thức đồng bộ để xác minh trình tự condition/unless/key một cách ổn định.

## 10. Chọn condition hay unless trong thực tế

| Yêu cầu | Cách diễn đạt thường phù hợp | Vì sao |
| --- | --- | --- |
| Chỉ cho phép put với request đã bật cache | **condition="#p2"** | Input có sẵn trước lời gọi |
| Chỉ put nếu kết quả được duyệt | **unless="!#result.approved()"** | approved nằm ở result |
| Bỏ put với result null | **unless="#result == null"** | Không có result trước lời gọi |
| Key là ID do database cấp | **key="#result.id()"** | ID chỉ biết sau khi insert |
| Không ghi cache cho tenant đặc biệt | **condition="#p0 != 'PRIVATE'"** | Tenant là đầu vào |
| Có thể trả về null, key dựa trên result | **unless="#result == null"** và key "#result.id()" | Tránh tạo key từ null khi put bị phủ quyết |
| Muốn xóa cache khi nguồn thay đổi | **@CacheEvict / invalidation sau commit phù hợp** | Bỏ put không tự xóa entry cũ |

Các biểu thức trên là ví dụ định hướng; cần thay #pN theo đúng chữ ký method và định nghĩa nghiệp vụ. **Cache key phải thống nhất** giữa @CachePut, @Cacheable và @CacheEvict nếu chúng cùng xử lý một entry. Tạo key String bằng nối chuỗi thiếu chuẩn hóa, bỏ tenant/currency hoặc thiếu namespace có thể gây cache miss hoặc hit sai.

### Checklist tự kiểm chứng

1. Xác nhận phương thức được gọi **qua Spring proxy**; self-invocation thường không được intercept theo proxy mode mặc định.
2. Quan sát **số lần chạy phương thức thật**, không dùng một lần cache hit để suy rằng @CachePut đã bỏ gọi.
3. Kiểm tra **condition** chỉ dựa trên dữ liệu có trước lời gọi.
4. Kiểm tra **unless** có xét đúng result và giá trị boolean phủ quyết hay không.
5. Kiểm tra **key** với kết quả thực tế, nhất là khi ID được sinh ra hoặc chuẩn hóa trong method.
6. Kiểm tra **entry đã có từ trước** khi condition false/unless true; không chỉ kiểm tra cache rỗng lúc ban đầu.
7. Kiểm tra hành vi khi **ném exception, rollback, future thất bại** nếu nghiệp vụ có các trường hợp ấy.
8. Khi dùng nhiều instance/provider, kiểm tra serialization và invalidation giữa các node; cache local mỗi JVM có bản sao riêng.

## 11. Câu hỏi tự kiểm tra

**1.** Một method được đánh dấu @CachePut có condition=false. Method có chạy không?

**Có.** @CachePut không bỏ qua phương thức chỉ vì condition false. Điều kiện đó bỏ qua thao tác put của cache annotation.

**2.** Vì sao điều kiện “chỉ lưu khi result.approved=true” không nên viết ở condition?

Vì **condition được đánh giá trước khi có result**. Dùng **unless="!#result.approved()"** sau khi method trả về, đồng thời kiểm tra null nếu result có thể null.

**3.** Tạo sản phẩm mới với ID do database cấp: @CachePut có thể dùng key="#result.id()" không?

**Có**, khi result khác null và có phương thức id() hợp lệ. @CachePut cho phép tính key sau khi đã có kết quả.

**4.** Cache đang giữ Product phiên bản 1. Method cập nhật thành phiên bản 2, nhưng unless=true. Cache có tự xóa phiên bản 1 không?

**Không.** Bỏ put lần này không đồng nghĩa evict. Phiên bản 1 có thể còn cho tới khi hết hạn hoặc được vô hiệu hóa chủ động.

**5.** Đọc dữ liệu cùng key nhưng dùng @Cacheable, còn cập nhật dùng @CachePut. Hai annotation có thể phối hợp không?

**Có**, trên **các phương thức phù hợp riêng biệt**, với cùng cache name và key logic. @Cacheable có thể tận dụng entry mà @CachePut đã ghi. Gắn đồng thời @Cacheable và @CachePut lên **cùng một method** nói chung không được khuyến khích vì semantics khác nhau và có thể gây hành vi khó đoán.

**6.** Method update trả về thành công có bảo đảm cache đã phản ánh một transaction commit thành công không?

**Không mặc nhiên.** Cần kiểm tra thứ tự advice và cơ chế transaction-aware/invalidation theo commit.

## Ghi nhớ

**@CachePut luôn thực thi method. condition xét trước, unless xét sau; #result có thể được dùng trong unless và key của @CachePut khi có kết quả.** Một lần put bị bỏ qua không xóa entry cũ. Tính đúng đắn đòi hỏi cả **điều kiện ghi**, **khóa tương ứng** và **chiến lược làm mới/xóa cache khi dữ liệu gốc thay đổi**.

### Tài liệu tham khảo

- Spring Framework – Annotation-based caching (condition, unless, #result, @CachePut): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – @CachePut API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework – SpEL: https://docs.spring.io/spring-framework/reference/core/expressions.html
- Spring Framework – Transaction-aware Cache Decorator: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
