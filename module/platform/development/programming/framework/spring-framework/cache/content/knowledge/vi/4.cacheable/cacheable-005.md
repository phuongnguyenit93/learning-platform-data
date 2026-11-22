# @Cacheable: Thời điểm lưu kết quả sau lời gọi thành công

## Mục tiêu bài học

Bài này giải thích chính xác **khi nào Spring ghi một kết quả vào cache** đối với phương thức đánh dấu @Cacheable, điều gì xảy ra khi phương thức thành công, ném ngoại lệ, trả về null hoặc hoàn tất bất đồng bộ, và cách kiểm chứng hành vi đó bằng Java 17+. Sau bài học, bạn có thể phân biệt **thời điểm phương thức trả về**, **thời điểm cache ghi giá trị**, **thời điểm giao dịch database commit**, và **thời điểm một tác vụ bất đồng bộ hoàn tất**.

> Quy tắc trung tâm: Với lời gọi đồng bộ đi qua Spring Cache proxy, khi **cache miss** và phương thức **trả về bình thường**, Spring mới cân nhắc ghi kết quả vào cache. Việc ghi còn tùy thuộc condition, unless và khả năng thực tế của cache provider. Khi phương thức ném ngoại lệ ra ngoài, Spring không lấy ngoại lệ đó làm kết quả để cache bằng @Cacheable.

## 1. @Cacheable xử lý lời gọi ở những thời điểm nào?

Spring Cache là cơ chế cache theo kết quả phương thức. Cấu hình @EnableCaching kích hoạt xử lý các annotation cache trên Spring bean; mặc định Spring dùng cơ chế proxy/AOP để bao quanh lời gọi phương thức.

Xét ví dụ trong một Spring-managed service:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product findProduct(long productId) {
    return repository.findById(productId);
}
~~~

Đây là **đoạn mã minh họa**, giả định Product và repository đã tồn tại; chưa phải chương trình độc lập.

### 1.1. Lần gọi đầu: cache miss

1. Client gọi findProduct(42) **qua Spring proxy**.
2. Spring xác định vùng cache "products" và khóa 42; nếu có condition thì đánh giá điều kiện trước.
3. Spring tra khóa 42. Chưa có entry → cache miss.
4. Spring gọi **phương thức thật**. Database được truy vấn; phương thức trả về một đối tượng Product bình thường.
5. Spring đánh giá unless nếu có. Nếu không bị từ chối, Spring yêu cầu cache provider ghi kết quả với key 42.
6. Lời gọi qua proxy hoàn tất và client nhận Product.

Đối với nhánh đồng bộ thông thường, thao tác đưa kết quả vào cache diễn ra **sau khi phương thức đích trả về thành công** và **trong quá trình lời gọi qua proxy hoàn tất**. Không nên hiểu đây là “đợi HTTP response gửi xong”, “đợi database transaction commit”, hoặc “đợi thêm một request mới”.

~~~text
Client -> Spring proxy -> Cache.get(42)
                              |
                           cache miss
                              |
                         findProduct(42)
                              |
                      trả về Product thành công
                              |
                    kiểm tra unless (nếu có)
                              |
                           Cache.put(42, Product)
                              |
                         trả kết quả cho client
~~~

Sơ đồ trên là luồng logic của phương thức **đồng bộ**, với điều kiện hoạt động cache hợp lệ và không có lỗi provider.

### 1.2. Lần gọi kế tiếp: cache hit

Spring đọc được giá trị đã lưu theo khóa 42 và trả về mà **không gọi lại thân phương thức**. Như vậy lần cache hit không phải là lần chạy lại logic truy vấn rồi mới ghi cache. Nếu khai báo nhiều vùng cache trong cùng @Cacheable, Spring có thể bổ sung giá trị cho các vùng chưa chứa entry sau khi tìm thấy hit ở vùng khác; đó là hành vi phối hợp nhiều cache, không phải thực thi lại phương thức nguồn.

~~~text
Client -> Spring proxy -> Cache.get(42)
                              |
                           cache hit
                              |
                     trả Product từ cache
                      (không chạy repository)
~~~

### 1.3. Phương thức ném ngoại lệ

Nếu phương thức đích ném một ngoại lệ lan ra ngoài thay vì trả kết quả bình thường, đường xử lý @Cacheable **không tạo cache entry mới từ lời gọi thất bại đó**. Lần gọi sau với cùng key có thể tiếp tục là cache miss và thử thực thi lại nguồn.

~~~text
Cache miss -> findProduct(42) -> throw IllegalStateException
                                          |
                                ngoại lệ lan tới client
                                KHÔNG Cache.put kết quả
~~~

Cần phân biệt trường hợp phương thức **bắt ngoại lệ bên trong và trả giá trị dự phòng**: khi đó, dưới góc nhìn của Spring, phương thức đã trả về bình thường. Giá trị dự phòng **có thể bị cache** nếu không có unless hoặc chính sách ngăn lưu tương ứng.

## 2. “Lời gọi thành công” thực sự nghĩa là gì?

Trong ngữ cảnh @Cacheable đồng bộ, “thành công” trước hết nghĩa là phương thức đích **kết thúc bình thường và tạo một kết quả có thể xử lý**, thay vì để ngoại lệ thoát ra ngoài. Điều này **không tự động đồng nghĩa** với tất cả mệnh đề sau:

- **Không đồng nghĩa nghiệp vụ thành công:** một đối tượng Result(success=false, error="NOT_FOUND") vẫn là một giá trị trả về bình thường. Nếu không có điều kiện lọc, nó có thể được lưu.
- **Không đồng nghĩa HTTP 2xx:** cache interceptor hoạt động ở ranh giới lời gọi phương thức Spring bean; trạng thái HTTP có thể được quyết định tại layer khác sau đó.
- **Không đồng nghĩa dữ liệu database đã commit:** advice của transaction và advice của cache là hai cơ chế khác nhau; thứ tự AOP, transaction boundary và cấu hình cache quyết định quan hệ thực tế.
- **Không đồng nghĩa cache chắc chắn ghi thành công:** unless có thể từ chối kết quả; provider có thể phát sinh lỗi; giá trị có thể bị loại bỏ ngay vì TTL, giới hạn dung lượng hoặc một lời gọi đồng thời.

Do đó phát biểu chính xác là: **Spring xét lưu kết quả sau khi phương thức trả về thành công; chỉ thực hiện việc lưu khi các điều kiện cache cho phép và thao tác lưu thành công.**

## 3. condition và unless: kiểm tra trước và sau khi chạy phương thức

Hai thuộc tính này thường quyết định vì sao một phương thức **chạy thành công nhưng không có entry**.

| Thuộc tính | Thời điểm đánh giá | Có thể đọc kết quả #result? | Tác động |
| --- | --- | --- | --- |
| condition | Trước khi thực thi phương thức / trước thao tác caching | Không | False → bỏ qua hành vi caching, vẫn thực thi phương thức |
| unless | Sau khi phương thức được gọi và có kết quả | Có | True → từ chối lưu kết quả vừa tính |

Ví dụ:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 > 0",
    unless = "#result == null"
)
public Product findProduct(long id) {
    return repository.findById(id);
}
~~~

Đây là **đoạn mã minh họa**; repository và Product cần được định nghĩa trong ứng dụng thật.

- Với id <= 0, condition là false nên Spring không áp dụng caching cho lần gọi đó, bất kể phương thức trả về gì.
- Với id > 0, cache miss và phương thức trả Product: unless là false, kết quả có thể được ghi.
- Với id > 0, cache miss và phương thức trả null: unless là true, Spring **không ghi null**.
- Với id > 0 và phương thức ném ngoại lệ: không có kết quả bình thường để đưa vào cache.

**Lưu ý về null:** Nếu không dùng unless, việc một giá trị null có thể được cache hay không phụ thuộc cấu hình và khả năng của Cache provider. Ví dụ ConcurrentMapCache mặc định hỗ trợ giá trị null thông qua giá trị thay thế nội bộ. Vì thế, “không tìm thấy” **không đương nhiên** đồng nghĩa cache miss ở lần tiếp theo.

**Lưu ý về Optional:** Spring hỗ trợ Optional trong kết quả cache: Optional có giá trị được xử lý theo giá trị bên trong; Optional.empty() tương ứng với null theo cơ chế Spring Cache, nếu provider cho phép lưu. Trong biểu thức unless, #result đại diện cho đối tượng nghiệp vụ đã mở wrapper; với Optional.empty() thì #result là null. Muốn tránh negative caching ngoài ý muốn, có thể dùng unless = "#result == null".

## 4. Ví dụ Java 17 chạy được: quan sát ngay trước và sau khi lưu

Chương trình sau dùng **Spring Framework 6.2.10**, Java 17+ và Maven. Có ba tình huống: phương thức trả về bình thường, ném ngoại lệ, và trả null bị unless loại bỏ. Dùng ConcurrentMapCacheManager để dễ quan sát; đây là cache RAM minh họa, không cung cấp chính sách TTL/max size production theo mặc định.

### 4.1. Cấu trúc tệp

~~~text
cache-write-timing/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CacheWriteTimingDemo.java
~~~

### 4.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-write-timing</artifactId>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.3. CacheWriteTimingDemo.java

~~~java
package demo;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheWriteTimingDemo {

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private final AtomicInteger sourceCalls = new AtomicInteger();

        @Cacheable(cacheNames = "products",
                   key = "#p0",
                   unless = "#result == null")
        public String load(String sku) {
            int call = sourceCalls.incrementAndGet();

            if ("ERR".equals(sku)) {
                throw new IllegalStateException("simulated failure");
            }
            if ("NONE".equals(sku)) {
                return null;
            }
            return sku + "|load=" + call;
        }

        public int sourceCalls() {
            return sourceCalls.get();
        }
    }

    private static boolean isCached(Cache cache, String key) {
        return cache.get(key) != null;
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            ProductService service = context.getBean(ProductService.class);
            Cache cache = Objects.requireNonNull(
                context.getBean(CacheManager.class).getCache("products"));

            System.out.println("A before: " + isCached(cache, "A"));
            System.out.println("A first: " + service.load("A"));
            System.out.println("A after: " + isCached(cache, "A"));
            System.out.println("A second: " + service.load("A"));
            System.out.println("Calls after hit: " + service.sourceCalls());

            try {
                service.load("ERR");
            } catch (IllegalStateException exception) {
                System.out.println("Error: " + exception.getMessage());
            }
            System.out.println("ERR cached: " + isCached(cache, "ERR"));

            System.out.println("NONE first: " + service.load("NONE"));
            System.out.println("NONE cached: " + isCached(cache, "NONE"));
            System.out.println("NONE second: " + service.load("NONE"));
            System.out.println("Source calls: " + service.sourceCalls());
        }
    }
}
~~~

### 4.4. Chạy chương trình

Tại thư mục có pom.xml, dùng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheWriteTimingDemo
~~~

Các dòng **do chương trình in ra** (log Maven, nếu có, không tính vào đây):

~~~text
A before: false
A first: A|load=1
A after: true
A second: A|load=1
Calls after hit: 1
Error: simulated failure
ERR cached: false
NONE first: null
NONE cached: false
NONE second: null
Source calls: 4
~~~

### 4.5. Giải thích output theo thứ tự

1. **A before: false:** chưa có entry key "A".
2. **A first: A|load=1:** cache miss, thân load("A") thực thi và trả về bình thường.
3. **A after: true:** ngay sau khi lời gọi qua proxy hoàn tất, kiểm tra cache thấy entry được ghi. Điều này quan sát được trong cùng thread, không phải phải chờ một request khác.
4. **A second: A|load=1:** cache hit; chuỗi trả về giữ số load 1 vì phương thức nguồn không chạy lại.
5. **Calls after hit: 1:** xác nhận hit đã tránh lượt thực thi thứ hai.
6. **Error: simulated failure / ERR cached: false:** phương thức nguồn ném ngoại lệ; @Cacheable không lưu một kết quả mới cho key "ERR".
7. **NONE first: null / NONE cached: false:** phương thức trả về bình thường nhưng unless thấy #result == null nên ngăn lưu.
8. **NONE second: null / Source calls: 4:** key "NONE" tiếp tục miss nên nguồn chạy lần nữa. Tổng số lượt chạy nguồn: A một lần + ERR một lần + NONE hai lần = 4.

Trong ví dụ, @EnableCaching bật cache advice; service được lấy từ ApplicationContext để đi qua Spring proxy. Phương thức load là public, class ProductService không phải final và không được gọi bằng this.load(...) từ chính bean.

## 5. Ngoại lệ, kết quả lỗi nghiệp vụ và chính sách lưu kết quả

### 5.1. Ngoại lệ thoát khỏi phương thức

~~~java
@Cacheable("profiles")
public Profile getProfile(long id) {
    return remoteClient.fetchProfile(id); // có thể throw
}
~~~

Nếu fetchProfile ném exception và phương thức không bắt, invocation không tạo kết quả thành công cho cache. Lời gọi kế tiếp thường tiếp tục truy xuất nguồn. Đây là **đoạn mã minh họa** phụ thuộc Profile/remoteClient, không chạy độc lập.

### 5.2. Exception bị bắt và chuyển thành giá trị dự phòng

~~~java
@Cacheable(cacheNames = "rates",
           unless = "#result == null")
public Rate getRate(String currency) {
    try {
        return exchangeProvider.fetch(currency);
    } catch (RuntimeException failure) {
        return null; // unless sẽ từ chối lưu null
    }
}
~~~

Phương thức đã **trả bình thường** sau khi bắt exception. Nếu trả một DTO đại diện lỗi và không có điều kiện veto, DTO đó có thể bị cache. Do vậy phải định nghĩa rõ có nên lưu kết quả lỗi hay không; nếu cần negative caching, phải quản lý TTL ngắn, retry và khả năng phục hồi dịch vụ nguồn một cách có chủ đích.

### 5.3. Đầu ra có thể thay đổi sau khi cache put

Cache lưu một tham chiếu hoặc bản sao/serialization tùy provider. Trả về một object mutable rồi thay đổi nó tại nơi khác có thể tạo hành vi khó đoán với cache in-memory; provider phân tán có thể lại trả đối tượng đã deserialize. Ưu tiên DTO bất biến hoặc quy định rõ quyền sở hữu dữ liệu. Cache abstraction không tự bảo đảm snapshot bất biến của giá trị.

## 6. Thời điểm lưu kết quả bất đồng bộ: CompletableFuture và Reactor

Từ **Spring Framework 6.1**, @Cacheable hiểu các kiểu trả về CompletableFuture và kiểu phản ứng Reactor được hỗ trợ; thời điểm “có kết quả” **không còn đơn thuần là lúc phương thức Java trả về wrapper**.

| Kiểu trả về | Khi giá trị có thể được đưa vào cache |
| --- | --- |
| Product (đồng bộ) | Sau khi phương thức trả về Product bình thường |
| CompletableFuture<Product> | Khi future hoàn tất thành công với giá trị |
| Mono<Product> | Khi publisher phát ra giá trị được hỗ trợ để lưu |
| Flux<Product> | Khi chuỗi phần tử hoàn tất; Spring gom thành List rồi lưu danh sách |

Ví dụ khai báo phương thức bất đồng bộ (**mã minh họa**, cần backend và Product):

~~~java
@Cacheable(cacheNames = "productsAsync", key = "#p0")
public CompletableFuture<Product> getProductAsync(long id) {
    return backend.fetchAsync(id);
}
~~~

Một CompletableFuture được trả về khi tác vụ còn đang chạy **không có nghĩa kết quả Product đã được lưu**. Spring xử lý kết quả khi future hoàn tất; future hoàn tất lỗi không phải là kết quả Product thành công để lưu. Tương tự, Flux cần hoàn tất toàn bộ trước khi danh sách kết quả được dùng làm giá trị cache; cách này không phù hợp cho stream vô hạn hoặc luồng phản ứng đòi hỏi back-pressure chi tiết.

Các cơ chế này yêu cầu cache provider có khả năng retrieval/put bất đồng bộ thích hợp. ConcurrentMapCacheManager của Spring hỗ trợ cách thích nghi với CompletableFuture; CaffeineCacheManager cần cấu hình async cache mode tương ứng để tận dụng hỗ trợ native. **Không tự suy diễn “đã lưu” ngay khi lệnh return CompletableFuture chạy.**

## 7. Ghi cache sau lời gọi thành công chưa chắc là sau transaction commit

Giả sử một phương thức vừa đọc/ghi dữ liệu trong @Transactional, đồng thời dùng annotation cache:

~~~java
@Transactional
@Cacheable(cacheNames = "accountSummary", key = "#p0")
public AccountSummary calculateSummary(long accountId) {
    return repository.buildSummary(accountId);
}
~~~

Đây là **mã minh họa**, AccountSummary và repository chưa được định nghĩa.

Cần kiểm tra hai mốc khác nhau: (1) phương thức target trả về một AccountSummary; (2) transaction thực sự commit. Spring Cache advice và transaction advice đều có thể bao quanh phương thức qua AOP, với thứ tự phụ thuộc cấu hình. **@Cacheable không tự tuyên bố “cache put luôn xảy ra sau commit”**. Nếu cache ghi dữ liệu trước một transaction về sau rollback, có rủi ro cache không phản ánh database.

Khi có yêu cầu nhất quán chặt, cân nhắc:
- Cấu hình cache transaction-aware hoặc trì hoãn thao tác cache đến sau commit nếu đúng với provider và loại thao tác.
- Đặt các thao tác evict/put vào bước after-commit phù hợp.
- Kiểm thử rollback, concurrent read, nhiều instance và transaction boundary thực tế.

Cũng đừng nhầm thao tác @Cacheable với @CacheEvict: với @CacheEvict, mặc định eviction chạy **sau khi phương thức kết thúc thành công**; beforeInvocation = true chủ động xóa trước khi chạy bất kể kết quả phương thức. Việc chọn chiến lược cập nhật là một quyết định nghiệp vụ khác với cơ chế cache kết quả truy vấn.

## 8. So sánh thời điểm chạy của ba annotation thường gặp

| Annotation | Phương thức nguồn có luôn chạy không? | Thời điểm tác động cache |
| --- | --- | --- |
| @Cacheable | Không; hit có thể bỏ qua | Miss + kết quả trả bình thường, sau đó kiểm tra unless và đưa kết quả vào cache nếu hợp lệ |
| @CachePut | Có | Sau khi phương thức đã cho ra kết quả, ghi kết quả mới theo cấu hình |
| @CacheEvict | Có trong luồng thông thường | Mặc định xóa sau khi phương thức chạy thành công; có thể dùng beforeInvocation=true để xóa trước |

Điểm khác biệt thiết yếu: @Cacheable tối ưu đường đọc nhờ **bỏ qua thực thi khi hit**; @CachePut phù hợp với thao tác cần **luôn chạy rồi cập nhật cache**. Không tùy ý đặt đồng thời @Cacheable và @CachePut lên cùng một phương thức vì hai mục tiêu thực thi trái nhau.

## 9. Vì sao “phương thức chạy thành công nhưng cache vẫn trống”?

Dùng các bước kiểm tra theo thứ tự sau:

1. **Có đi qua proxy không?** @EnableCaching phải được bật, bean phải do Spring quản lý, và lời gọi phải đi qua proxy. Self-invocation kiểu this.load(id) bỏ qua cache advice trong proxy mode mặc định.
2. **condition có false không?** Nếu false, Spring bỏ qua hành vi caching cho lời gọi, dù phương thức vẫn chạy thành công.
3. **unless có true không?** Một kết quả bình thường như null hoặc DTO lỗi có thể bị từ chối lưu.
4. **Key có đúng không?** Cùng phương thức nhưng key được sinh khác (locale/tenant/tham số/equals-hashCode) sẽ khiến việc kiểm tra tưởng như cache trống.
5. **Cache provider có nhận put không?** Xem cấu hình CacheManager, loại cache, serialization, capacity, TTL, eviction và error handler. Mặc định lỗi cache operation có thể lan ra caller.
6. **Có đồng thời thay đổi/xóa entry không?** @CacheEvict từ luồng khác, TTL ngắn hoặc tranh chấp put/evict có thể khiến entry biến mất ngay.
7. **Có đang dùng async không?** Với CompletableFuture/Mono/Flux, thời điểm có kết quả hoàn chỉnh có thể muộn hơn lời gọi Java return.
8. **Có chờ transaction commit không?** Kiểm tra AOP advisor ordering và transaction-aware cache nếu hệ thống cần lưu sau commit.

Để quan sát, đo count số lần chạy thân phương thức, hit/miss/put của provider và truy vấn entry qua CacheManager trong môi trường test. Đừng xác định kết quả chỉ từ log “method completed” của tầng ứng dụng.

## 10. Kiểm thử nên có

Một bài test hành vi cache có giá trị khi xác nhận ít nhất những tình huống sau:

- **Miss → success → hit:** lần đầu chạy thân phương thức, sau đó entry tồn tại; lần hai cùng key không chạy lại thân hàm.
- **Miss → throw:** không ghi kết quả mới; lần sau cùng key có thể chạy lại.
- **Miss → return null + unless true:** không lưu null; lần sau tiếp tục miss.
- **condition false:** phương thức được thực thi theo cách thông thường, cache lookup/put không áp dụng.
- **Result mang lỗi nghiệp vụ:** xác minh unless ngăn lưu nếu chính sách không cho phép negative caching.
- **Async hoàn tất thành công/thất bại:** chỉ đánh giá cache sau khi future/publisher đã thực sự có giá trị hoặc hoàn tất lỗi.
- **Rollback transaction:** kết quả cache cuối cùng phải nhất quán với chính sách transaction đã thiết kế.
- **Concurrent misses:** @Cacheable mặc định không đảm bảo một lần tính duy nhất; khi cần có thể xem xét sync = true với khả năng hỗ trợ và giới hạn của provider.

### Tự kiểm tra

**1.** Một phương thức @Cacheable chưa có entry, chạy xong trả về String "OK". Khi nào Spring cân nhắc put?  
**Đáp án:** Sau khi thân phương thức trả về thành công, rồi đánh giá unless nếu có.

**2.** Phương thức ném IllegalStateException ra ngoài. Spring có ghi exception làm cache value không?  
**Đáp án:** Không theo hành vi @Cacheable thông thường.

**3.** Phương thức trả null nhưng không có unless. Có chắc lần sau phải miss không?  
**Đáp án:** Không; một số provider cho phép cache null. Cần xem cấu hình.

**4.** Lời gọi trả CompletableFuture chưa hoàn tất. Có chắc Product đã được lưu không?  
**Đáp án:** Không; kết quả được xử lý khi future hoàn tất.

**5.** @Transactional + @Cacheable có bảo đảm cache put luôn sau database commit không?  
**Đáp án:** Không. Phải xét thứ tự AOP advice, transaction boundary và cấu hình cache.

**6.** Một phương thức bên trong cùng service gọi this.findProduct(42). @Cacheable có chắc được áp dụng không?  
**Đáp án:** Không với proxy mode mặc định; lời gọi phải đi qua proxy.

## Tài liệu tham khảo

- Spring Framework Reference — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Spring Framework Reference — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework Reference — Cache TTL/TTI/Eviction: https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html
