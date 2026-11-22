# `@CacheEvict`: khóa dựa trên `#result` chỉ khả dụng đúng thời điểm

## 1. Vấn đề: khóa xóa cache đôi khi phụ thuộc vào kết quả của phương thức

`@CacheEvict` của Spring Framework đánh dấu phương thức có nhiệm vụ **xóa một entry hoặc toàn bộ một cache**. Thông thường, ta dùng tham số đầu vào để xác định entry cần xóa:

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void update(String id, String newPrice) {
    // Cập nhật dữ liệu nguồn
}
~~~

Trong trường hợp này, `#p0` đã có ngay từ lúc gọi phương thức, nên có thể tính key trước hoặc sau khi thân phương thức chạy.

Nhưng có những phương thức chỉ biết **ID cần xóa sau khi thực hiện xong**: ví dụ xóa một hàng dựa trên mã bên ngoài rồi trả về ID nội bộ, chuyển một tài nguyên và trả về khóa cũ, hoặc thao tác cập nhật trả về ID chính xác đã thay đổi. Lúc đó ta có thể muốn viết:

~~~java
@CacheEvict(cacheNames = "products", key = "#result")
public String changePrice(String externalCode, String newPrice) {
    // Ghi vào nguồn dữ liệu và trả lại ID thực tế của sản phẩm.
    return "p1";
}
~~~

`#result` là biến SpEL tham chiếu **giá trị phương thức trả về**, và chỉ xuất hiện **sau khi có kết quả**. Với `@CacheEvict`, cách dùng `#result` làm key chỉ hợp lệ khi `beforeInvocation = false` (mặc định), tức Spring xử lý eviction sau khi phương thức thực thi thành công. Nếu đặt `beforeInvocation = true`, phương thức còn chưa được gọi lúc tính key, vì vậy không có kết quả để dùng.

Đây là sự khác biệt giữa **dữ liệu đã biết trước lời gọi** (`#p0`, `#a0`, `#root.args[0]`) và **dữ liệu chỉ biết sau lời gọi** (`#result`).

## 2. Hai chế độ thời điểm của `@CacheEvict`

`@CacheEvict` có thuộc tính `beforeInvocation` quyết định thời điểm thực hiện:

| Thuộc tính | Khi nào eviction diễn ra? | Khi phương thức ném ngoại lệ | Dùng `#result` trong `key`? |
| --- | --- | --- | --- |
| `beforeInvocation = false` (mặc định) | Sau khi phương thức thực thi thành công. | Không thực hiện eviction cho lượt gọi thất bại thông thường. | **Có**, vì kết quả đã có. |
| `beforeInvocation = true` | Trước khi gọi phương thức. | Entry vẫn đã bị xóa dù thân phương thức sau đó ném ngoại lệ. | **Không**, vì kết quả chưa tồn tại. |

Luồng thông thường cho việc xóa một entry:

~~~text
@CacheEvict(key = "#result", beforeInvocation = false)

Gọi method -> thực thi logic -> trả kết quả
                                  |
                                  v
                            SpEL thấy #result
                                  |
                                  v
                            Tính key -> evict


@CacheEvict(key = "#p0", beforeInvocation = true)

Gọi method -> SpEL đọc đối số #p0 -> tính key -> evict
                                             |
                                             v
                                        Thực thi method
                                        (có thể thất bại)
~~~

Các bước trên là mô hình khi phương thức trả giá trị đồng bộ thông thường. Với `CompletableFuture` hoặc kiểu reactive, các bản Spring Framework hỗ trợ sẽ xét tới thời điểm hoàn thành bất đồng bộ; không nên nhầm việc **trả về đối tượng Future/Publisher** với lúc **có kết quả nghiệp vụ**. Bài học này dùng phương thức đồng bộ Java để quan sát chính xác thứ tự.

### 2.1. Khi `beforeInvocation=false`

Giả sử một phương thức `changePrice(...)` cập nhật giá và trả ID thực tế `"p1"`. Khi nó thành công, `#result` mang giá trị `"p1"`; Spring dùng giá trị đó để xóa `products[p1]`. Nếu phương thức ném ngoại lệ trước lúc trả về, hoạt động xóa sau lời gọi thường không xảy ra.

~~~java
@CacheEvict(cacheNames = "products",
            key = "#result",
            beforeInvocation = false)
public String changePrice(String externalCode, String newPrice) {
    // Cập nhật dữ liệu nguồn thành công.
    return "p1";
}
~~~

Đây là **trích đoạn minh họa**; ví dụ đầy đủ, có thể chạy, xuất hiện ở phần tiếp theo.

Điểm cần kiểm tra trước khi triển khai: kiểu và giá trị của `#result` phải **khớp chính xác với cache key ở đường đọc**. Nếu đường đọc lưu `products[p1]`, thì kết quả trả về phải đại diện cho `"p1"`. Nếu phương thức trả số lượng bản ghi đã cập nhật `1`, `#result` sẽ là `1` và xóa sai key.

### 2.2. Khi `beforeInvocation=true`

Chế độ này dành cho trường hợp cần xóa trước khi phương thức chạy, **không phụ thuộc kết quả thành công hay thất bại**:

~~~java
@CacheEvict(cacheNames = "products",
            key = "#p0",
            beforeInvocation = true)
public void refresh(String id) {
    // Phần thân được thực thi sau khi cache entry đã bị xóa.
}
~~~

Trong `key`, dùng những giá trị có trước lời gọi như `#p0`, `#root.args[0]`, hoặc tên tham số khi Spring có thể khám phá được. Viết `key = "#result"` cùng `beforeInvocation=true` là lỗi thiết kế: biểu thức đòi một giá trị chưa tồn tại ở thời điểm Spring tính key. Đừng coi kết quả `null` hay ngoại lệ SpEL cụ thể là hành vi được đảm bảo để ứng dụng dựa vào.

### 2.3. `beforeInvocation=false` không đồng nghĩa đã commit database

Cụm “sau khi thực thi thành công” mô tả thời điểm lời gọi do cache interceptor quản lý hoàn tất. Nó **không tự động bảo đảm database transaction đã commit** trước eviction trong mọi cách kết hợp `@Transactional`, advice ordering và `CacheManager`.

Nếu ứng dụng đòi hỏi dữ liệu cache luôn phản ánh bản đã commit, cần thiết kế cơ chế invalidation sau commit, hoặc cache manager/transaction integration phù hợp; đồng thời kiểm thử tình huống rollback và đọc đồng thời. Tránh suy luận rằng chỉ đặt hai annotation cạnh nhau là đủ bảo đảm thứ tự transaction.

## 3. Ví dụ Spring Boot 3 / Java 17+ có thể chạy

Ví dụ sau dùng một `ConcurrentMapCacheManager` giữ cache `products` trong bộ nhớ. Ta so sánh ba tình huống:

1. Ghi thành công, trả ID `p1`, dùng `#result` xóa entry sau lời gọi.
2. Phương thức ném ngoại lệ với `beforeInvocation=false`, nên entry cũ còn.
3. Phương thức ném ngoại lệ với `beforeInvocation=true`, entry đã bị xóa trước khi lỗi xảy ra.

Tạo dự án Gradle Java 17 với `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Tạo `src/main/java/demo/EvictResultApplication.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class EvictResultApplication {
    public static void main(String[] args) {
        SpringApplication.run(EvictResultApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    ProductStore productStore() {
        return new ProductStore();
    }

    @Bean
    ProductService productService(ProductStore store) {
        return new ProductService(store);
    }

    @Bean
    CommandLineRunner demo(ProductService service) {
        return args -> {
            System.out.println("read1 = " + service.find("p1"));
            System.out.println("read2 = " + service.find("p1"));

            System.out.println("changed = "
                    + service.changePrice("p1", "Gia 120"));
            System.out.println("read3 = " + service.find("p1"));

            try {
                service.rejectAfter("p1");
            } catch (IllegalStateException ex) {
                System.out.println("after error caught");
            }
            System.out.println("read4 = " + service.find("p1"));

            try {
                service.rejectBefore("p1");
            } catch (IllegalStateException ex) {
                System.out.println("before error caught");
            }
            System.out.println("read5 = " + service.find("p1"));
        };
    }
}

class ProductStore {
    private final Map<String, String> prices =
            new ConcurrentHashMap<>(Map.of("p1", "Gia 100"));

    String get(String id) {
        return prices.get(id);
    }

    void put(String id, String price) {
        prices.put(id, price);
    }
}

class ProductService {
    private final ProductStore store;

    ProductService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public String find(String id) {
        System.out.println("LOAD " + id);
        return store.get(id);
    }

    @CacheEvict(cacheNames = "products",
                key = "#result",
                beforeInvocation = false)
    public String changePrice(String id, String newPrice) {
        store.put(id, newPrice);
        System.out.println("UPDATE " + id + " to " + newPrice);
        return id;
    }

    @CacheEvict(cacheNames = "products",
                key = "#result",
                beforeInvocation = false)
    public String rejectAfter(String id) {
        System.out.println("REJECT_AFTER " + id);
        throw new IllegalStateException("rejected");
    }

    @CacheEvict(cacheNames = "products",
                key = "#p0",
                beforeInvocation = true)
    public void rejectBefore(String id) {
        System.out.println("REJECT_BEFORE " + id);
        throw new IllegalStateException("rejected");
    }
}
~~~

Chạy `./gradlew bootRun` nếu dự án có Gradle Wrapper hoặc `gradle bootRun` với Gradle tương thích đã cài (trên Windows dùng `gradlew.bat bootRun`). Bỏ qua log khởi động của Spring Boot, **những dòng demo chủ động in ra** theo đúng thứ tự là:

~~~text
LOAD p1
read1 = Gia 100
read2 = Gia 100
UPDATE p1 to Gia 120
changed = p1
LOAD p1
read3 = Gia 120
REJECT_AFTER p1
after error caught
read4 = Gia 120
REJECT_BEFORE p1
before error caught
LOAD p1
read5 = Gia 120
~~~

Giải thích kết quả:

- **`read1`**: `find("p1")` là cache miss. Method thực thi, in `LOAD p1` và lưu giá `Gia 100` theo key `p1`.
- **`read2`**: cùng key nên hit; không xuất hiện thêm `LOAD`.
- **`changePrice`**: method cập nhật nguồn thành `Gia 120`, rồi trả `"p1"`. `beforeInvocation=false` cho phép SpEL dùng `#result = "p1"`; Spring xóa đúng entry `products[p1]`.
- **`read3`**: cache miss sau eviction, nên in `LOAD p1` rồi lưu `Gia 120`.
- **`rejectAfter`**: ném ngoại lệ. Eviction sau lời gọi không chạy; `read4` vẫn hit, không in `LOAD`.
- **`rejectBefore`**: dùng `key="#p0"`, evict `p1` ngay trước lời gọi. Dù sau đó ném ngoại lệ, key đã bị xóa nên `read5` miss và lại in `LOAD p1`.

Chú ý hai thông tin khác nhau: **khi nào xác định được key** và **khi nào xóa entry**. Với `#result`, key chỉ có thể xác định sau lúc method trả kết quả; với `#p0`, key có sẵn trước khi chạy. Việc `@CacheEvict` áp dụng lựa chọn nào phụ thuộc `beforeInvocation`.

`ProductService` là bean được Spring tạo bằng `@Bean`, và `CommandLineRunner` gọi qua bean do Spring quản lý. Ở chế độ proxy thông dụng, nếu `ProductService` gọi `this.changePrice(...)` bên trong chính nó, lời gọi nội bộ có thể bỏ qua cache interceptor; demo tránh trường hợp đó.

## 4. Các cách thiết kế key theo kết quả

### 4.1. Kết quả là ID thuần

Nếu method trả trực tiếp ID khóa cache, `key = "#result"` đủ rõ:

~~~java
@CacheEvict(cacheNames = "products", key = "#result")
public String updateAndReturnId(String id, String value) {
    // Update thành công.
    return id;
}
~~~

Trích đoạn này thể hiện kiểu dữ liệu và SpEL; khi triển khai cần có logic cập nhật nguồn thực sự. `beforeInvocation` mặc định là `false` nên `#result` khả dụng sau lời gọi.

### 4.2. Kết quả là object có ID

Nếu kết quả trả về một `Product` có getter `getId()`, có thể viết:

~~~java
@CacheEvict(cacheNames = "products",
            key = "#result.id",
            beforeInvocation = false)
public Product replace(Product input) {
    // Lưu dữ liệu rồi trả Product thực tế.
    return input;
}
~~~

SpEL truy cập `#result.id` thông qua thuộc tính JavaBean `id` tương ứng với `getId()`. **Không sao chép nguyên biểu thức này vào một method trả `void`, `String` hay `Integer`**: các kiểu kết quả đó không cung cấp cùng thuộc tính.

Nếu phương thức có thể trả `null`, trước khi dùng `#result.id` cần có chiến lược rõ ràng: định nghĩa rằng thao tác thất bại phải ném ngoại lệ, trả một kết quả có ID hợp lệ, hoặc thiết kế key theo tham số đầu vào thay vì kết quả. Tránh truyền key `null` cho cache; nhiều provider và đường xử lý của Spring không chấp nhận khóa rỗng.

### 4.3. Kết quả là `Optional<Product>`

Trong ngữ cảnh cache SpEL của Spring, với các wrapper được hỗ trợ như `Optional`, `#result` tham chiếu **giá trị bên trong wrapper**, không phải đối tượng `Optional` bên ngoài. Nếu `Optional.empty()`, giá trị nghiệp vụ có thể là `null`.

Vì vậy `#result.id` chỉ an toàn khi chắc chắn có `Product`. Có thể dùng key từ `#p0` nếu tham số vốn đã chứa ID và không cần đợi kết quả, hoặc thiết kế cách xử lý rõ ràng cho trường hợp không tìm thấy. Việc dùng safe navigation `#result?.id` có thể tránh dereference `null`, nhưng **không tự biến khóa `null` thành một eviction hợp lệ**.

### 4.4. Phương thức trả `void`

`@CacheEvict` dùng được trên method `void` vì nó là hành động xóa cache, không cần kết quả trả về. Tuy nhiên, nếu khóa dựa trên kết quả thì method `void` không có ID để cung cấp: hãy dùng `#p0`, `#root.args[0]` hoặc `KeyGenerator` phù hợp. Tránh viết `key="#result.id"` trên phương thức `void`.

### 4.5. `allEntries=true` không dùng key riêng

Khi `@CacheEvict(allEntries = true)`, mục đích là xóa **toàn bộ entry** của cache được chỉ định; thuộc tính `key` không có ý nghĩa trong thao tác này và Spring bỏ qua nó. Vì vậy không thể dùng `#result` để chọn một entry cụ thể trong cùng cấu hình xóa toàn bộ.

~~~java
@CacheEvict(cacheNames = "products", allEntries = true)
public void refreshCatalog() {
    // Cập nhật toàn bộ nguồn dữ liệu.
}
~~~

Hãy lựa chọn `allEntries=true` khi toàn bộ vùng cache thật sự mất hiệu lực; nếu chỉ một ID thay đổi thì eviction theo key sẽ tiết kiệm hơn.

## 5. So sánh ngữ cảnh `#result` giữa các annotation

Việc `#result` tồn tại phụ thuộc vào **thời điểm đánh giá biểu thức**, không đơn thuần vì method có kiểu trả về.

| Annotation / thuộc tính | Khi đánh giá | Có thể dùng `#result`? |
| --- | --- | --- |
| `@Cacheable(key=...)` | Trước khi biết kết quả, để tra cache. | Không. |
| `@Cacheable(condition=...)` | Trước khi quyết định sử dụng cache. | Không. |
| `@Cacheable(unless=...)` | Sau khi gọi method, để quyết định có lưu kết quả không. | Có. |
| `@CachePut(key=...)` | Sau khi method chạy, để lưu kết quả vào cache. | Có. |
| `@CacheEvict(key=...)`, `beforeInvocation=false` | Sau khi method thành công. | Có. |
| `@CacheEvict(key=...)`, `beforeInvocation=true` | Trước khi gọi method. | Không. |

Với `@CacheEvict`, nếu `condition` cần dùng thông tin hậu thực thi, hãy kiểm tra cụ thể khả năng và thứ tự đánh giá của **phiên bản Spring đang chạy**. Ở mức thiết kế cơ bản, dùng `key="#result"` sau lời gọi và dùng `condition` dựa trên tham số là cách rõ ràng nhất. Tránh lẫn `condition` (quyết định có áp dụng thao tác) với `key` (chỉ ra entry).

Các thuộc tính `#root.methodName`, `#root.targetClass`, `#root.args`, `#root.caches` là metadata của lời gọi và có thể dùng để tính key thích hợp; chúng **không phải** kết quả nghiệp vụ và không thay thế `#result`.

## 6. Những sai lầm thường gặp

| Sai lầm | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| `@CacheEvict(key="#result", beforeInvocation=true)` | Chưa có kết quả tại thời điểm tính key. | Đổi sang `beforeInvocation=false` hoặc dùng tham số `#p0`. |
| `@CacheEvict(key="#result.id")` trên method `void`. | Không có kết quả chứa thuộc tính `id`. | Dùng tham số ID hoặc đổi contract trả về một object phù hợp. |
| Nghĩ `#result` luôn là object `Optional`. | Spring unwrap các wrapper được hỗ trợ trong cache SpEL. | Dùng thuộc tính của giá trị bên trong, xét trường hợp rỗng. |
| Method trả status `true` nhưng cache key là ID. | `#result=true` không tương ứng key `p1`. | Trả ID hoặc dùng `#p0`. |
| Nghĩ `beforeInvocation=false` là eviction sau commit DB. | Thứ tự transaction/advice và backend cache cần xử lý riêng. | Thiết kế cache invalidation sau commit nếu yêu cầu nhất quán. |
| Bất kỳ exception nào cũng xóa cache. | Đây chỉ là semantics của eviction trước lời gọi; eviction sau lời gọi không chạy khi method đồng bộ ném exception thông thường. | Chọn `beforeInvocation` dựa trên yêu cầu nghiệp vụ. |
| Sao chép key đọc và key xóa nhưng hai quy tắc khác nhau. | Cache không xóa đúng entry. | So sánh key thực tế ở cả đường đọc và ghi; kiểm thử hit/miss. |
| Gọi method có annotation thông qua `this.method()` trong cùng bean. | Proxy Spring mặc định không intercept self-invocation. | Gọi qua bean được Spring quản lý hoặc thiết kế cơ chế interception khác. |

## 7. Câu hỏi tự ôn và tình huống thực tế

**Tình huống 1:** `@CacheEvict(cacheNames="products", key="#result")` đặt trên method `String update(...)`, trả `"p1"` sau khi lưu thành công. Khi nào key được tính?

**Đáp án:** Sau khi method trả kết quả, vì `beforeInvocation` mặc định là `false`. Spring dùng `"p1"` để xóa entry tương ứng.

**Tình huống 2:** Thêm `beforeInvocation=true` nhưng vẫn giữ `key="#result"`. Điều gì không ổn?

**Đáp án:** Key bị yêu cầu trước khi kết quả tồn tại. Cần key từ đối số, chẳng hạn `#p0`, hoặc đổi về eviction sau lời gọi nếu nghiệp vụ cho phép.

**Tình huống 3:** Method cập nhật giá rồi ném `IllegalStateException` trước khi trả kết quả, với cấu hình `beforeInvocation=false`. Cache có bị evict không?

**Đáp án:** Thông thường **không**; eviction sau lời gọi chỉ thực hiện khi lời gọi thành công. Cần đánh giá riêng nếu phương thức đã tạo side effect mà không rollback được, vì cache có thể giữ dữ liệu cũ.

**Tình huống 4:** Method xóa cache trước lời gọi rồi ném exception. Điều gì đã xảy ra với key cũ?

**Đáp án:** Key đã bị xóa trước khi ngoại lệ được ném. Yêu cầu đọc sau đó có thể miss và tải lại dữ liệu nguồn.

**Tình huống 5:** Đường đọc lưu key `"p1"`, method update trả về `Product("p1",...)`. Nên dùng `#result` hay `#result.id`?

**Đáp án:** Dùng `#result.id` khi result là object `Product` có thuộc tính `id`, bởi key đọc là chuỗi `"p1"`, không phải cả object.

**Điểm mấu chốt:** Chỉ dùng dữ liệu làm cache key **khi dữ liệu ấy thực sự tồn tại tại thời điểm đánh giá**. Với `@CacheEvict`, `#result` là lựa chọn hợp lệ cho eviction **sau lời gọi thành công**; `beforeInvocation=true` cần khóa xác định được **trước lời gọi**. Dù dùng cách nào, key xóa phải trùng với key đã dùng để lưu entry.

Tài liệu tham khảo:
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework 6.1 — `CacheEvict` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.22-SNAPSHOT/javadoc-api/org/springframework/cache/annotation/CacheEvict.html)
