# Optional: lưu giá trị bên trong hoặc biểu diễn rỗng khi dùng Spring Cache

> **Spring Framework — Cache Abstraction · Chủ điểm: Điều kiện lưu.** Bài này giải thích cách Spring xử lý phương thức trả `java.util.Optional<T>` với `@Cacheable`, cách kết quả không tồn tại được biểu diễn trong cache và khi nào nên dùng `unless` để **không cache kết quả rỗng**.

## 1. Vấn đề: kết quả có thể không tồn tại

Giả sử chương trình tìm sản phẩm theo mã:

~~~java
public Optional<String> findProduct(String sku) {
    return "P-1".equals(sku) ? Optional.of("Keyboard") : Optional.empty();
}
~~~

Đây là ví dụ logic tối giản: mã `"P-1"` trả về `Optional.of("Keyboard")`, các mã khác trả về `Optional.empty()`. Trong ứng dụng thực tế, nhánh tra cứu thường gọi repository hoặc nguồn dữ liệu. `Optional<T>` thể hiện rõ rằng việc không tìm thấy dữ liệu là kết quả hợp lệ, thay vì bắt mọi bên gọi suy đoán từ `null`.

Khi thêm `@Cacheable`, có hai tình huống cần phân biệt:

1. **Tìm thấy:** Có nên cache chính đối tượng `Optional` hay giá trị `T` nằm bên trong?
2. **Không tìm thấy:** `Optional.empty()` có được cache không? Nếu được, vùng cache cần ghi nhận sự vắng mặt bằng cách nào và có gì khác với *cache miss*?

Câu trả lời phụ thuộc vào **cơ chế unwrapping của Spring** và **khả năng lưu giá trị null của backend**. Một kết quả rỗng đã được cache có thể giúp tránh truy vấn lặp đi lặp lại, nhưng cũng có nguy cơ giữ trạng thái “không tìm thấy” sau khi dữ liệu đã xuất hiện.

## 2. Quy tắc của Spring: mở Optional trước khi lưu

Với **`@Cacheable` của Spring Framework**, kết quả kiểu `java.util.Optional<T>` được Spring xử lý đặc biệt:

- Trả `Optional.of(value)` hoặc `Optional.ofNullable(value)` có giá trị: Spring lấy **`value` bên trong Optional** để lưu vào cache.
- Trả `Optional.empty()`: Spring xem **giá trị nghiệp vụ được cache là `null`**, nếu caching operation không bị loại bởi điều kiện và cache backend cho phép biểu diễn null.
- Khi lời gọi sau cùng key là cache hit, Spring trả về kết quả phù hợp với **kiểu khai báo của method**: giá trị hiện diện được bọc thành `Optional.of(value)`, giá trị null đã cache được trả dưới dạng `Optional.empty()`.
- Việc Spring lưu *giá trị nghiệp vụ* không đồng nghĩa mọi provider có thể ghi raw `null` trực tiếp. Một số implementation dùng **sentinel/null holder** nội bộ; một số không chấp nhận cache null.

Ví dụ:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Optional<Product> findProduct(String sku) {
    return repository.findBySku(sku);
}
~~~

Đoạn này mô tả cách dùng trong ứng dụng có lớp `Product` và bean `repository` phù hợp. Nó không phải ví dụ độc lập để chạy. Với `sku = "P-1"`:

| Kết quả từ repository khi cache miss | Giá trị Spring muốn lưu | Lời gọi sau cùng key |
| --- | --- | --- |
| `Optional.of(product)` | `product` (kiểu `Product`) | Cache hit và trả `Optional.of(product)` |
| `Optional.empty()` | `null` ở mức hợp đồng cache, khi provider cho phép | Cache hit và trả `Optional.empty()` |
| Method ném exception | Không có kết quả bình thường để lưu | Lời gọi sau có thể thực thi lại; cơ chế cache này không mặc nhiên cache exception |

**Điểm cần nhớ:** `@Cacheable` thường không lưu nguyên vẹn wrapper `Optional.of(...)` hoặc `Optional.empty()` như một object `Optional` trong vùng cache. Spring mở wrapper để xác định giá trị cần lưu. Đây là hành vi riêng của caching interception; nếu tự gọi `cache.put(key, optional)` bằng API thủ công thì bạn đang trực tiếp đưa đối tượng `Optional` vào cache và không nên suy ra có cùng hành vi tự động.

Tài liệu Spring mô tả chính sách này cho `java.util.Optional`. Không tự mở rộng khẳng định sang mọi dạng wrapper khác như `OptionalInt`, `Future` hay reactive type; chúng có hợp đồng hỗ trợ riêng hoặc khác biệt theo phiên bản.

## 3. Ba trạng thái thường bị nhầm lẫn

Cần phân biệt **không có entry**, **có entry mang giá trị null** và **có entry mang giá trị thực**.

| Trạng thái | `Cache.get(key)` (API lấy `ValueWrapper`) | Ý nghĩa với `@Cacheable` trả Optional |
| --- | --- | --- |
| Cache miss | `null` (không có wrapper) | Spring gọi method nếu không có cơ chế khác ngăn |
| Cached null | `Cache.ValueWrapper` khác null, nhưng `wrapper.get() == null` | Spring có thể trả `Optional.empty()` mà không gọi method |
| Cached value | `Cache.ValueWrapper` khác null, `wrapper.get()` là đối tượng | Spring có thể trả `Optional.of(value)` mà không gọi method |

`Cache.ValueWrapper` là giao diện của Spring; đối tượng cụ thể tùy provider. Với `ConcurrentMapCacheManager` mặc định, Spring chấp nhận cache null dù map `ConcurrentHashMap` vốn không chứa được `null`: implementation thay null bằng một **đối tượng đánh dấu nội bộ** và khôi phục null khi đọc qua cache API.

Sơ đồ thao tác:

~~~text
Lời gọi findProduct("P-404") qua Spring cache proxy
                       |
                       v
                Có entry theo key?
                 /              \
              không              có
               |                 |
        Chạy findProduct()    Đọc giá trị cache
               |                 |
        Optional.empty()     cached null? ------> Optional.empty()
               |                 |
        Spring unwrap         giá trị T --------> Optional.of(T)
               |
        giá trị nghiệp vụ null
               |
   `unless` cho lưu hay từ chối?
      /                    \
    cho lưu               từ chối
      |                     |
 Provider hỗ trợ null?   Không ghi entry
      |
 Ghi nhận cached null
~~~

Trong thực tế, nếu backend không hỗ trợ null hoặc đã được cấu hình từ chối null, việc ghi dữ liệu rỗng có thể gây lỗi. **Không** mặc nhiên coi `Optional.empty()` là thứ mà backend nào cũng sẽ tự bỏ qua.

## 4. `unless`: quyết định có lưu Optional.empty() hay không

Giả sử dữ liệu SKU không tồn tại có thể được thêm sau một vài giây. Khi đó, bạn có thể **không muốn giữ kết quả rỗng**:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    unless = "#result == null"
)
public Optional<Product> findProduct(String sku) {
    return repository.findBySku(sku);
}
~~~

`unless` là điều kiện **từ chối ghi kết quả vào cache sau khi method chạy**. Nếu biểu thức trả `true`, kết quả của lần thực thi đó **không được lưu**.

Với method trả `Optional<Product>`, Spring cung cấp biến `#result` dưới dạng **giá trị `Product` bên trong**, **không phải `Optional<Product>`**:

| Method trả về | `#result` trong `unless` | `#result == null` | Hành vi lưu |
| --- | --- | --- | --- |
| `Optional.of(product)` | `product` | `false` | Được phép cache `product` |
| `Optional.empty()` | `null` | `true` | Không ghi entry cho key này |

Vì vậy, mẫu **`unless = "#result == null"`** là cách rõ ràng để cache thành công nhưng bỏ qua dữ liệu không tồn tại.

### Vì sao không dùng `unless = "#result.isEmpty()"`?

Trong context `@Cacheable`, `#result` đã được **mở Optional**. Khi có `Optional.empty()`, `#result` chính là `null`, nên việc gọi `isEmpty()` trên nó có thể gây lỗi đánh giá SpEL. Khi có `Optional.of(product)`, `#result` là `Product` và có thể không có phương thức `isEmpty()`.

Dấu hiệu đúng là **đối tượng thực có hiện diện không**, thường viết `#result == null`. Nếu cần kiểm tra thuộc tính của `Product`, có thể dùng phép truy cập an toàn, chẳng hạn `unless = "#result?.archived == true"` nếu `Product` thật sự có property boolean `archived` và quy tắc nghiệp vụ chỉ muốn bỏ qua bản ghi đã lưu trữ.

### `condition` không thay thế được `unless`

~~~java
// Minh họa hai giai đoạn đánh giá khác nhau:
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null",
    unless = "#result == null"
)
public Optional<Product> findProduct(String sku) {
    return repository.findBySku(sku);
}
~~~

- `condition` xét **đầu vào trước khi gọi method**. Ở đây, chỉ bật caching khi `sku` khác null.
- `unless` xét **kết quả sau khi gọi method**, nên có thể biết `Optional` rỗng hay không qua `#result`.
- Khi `condition` là false, lời gọi không thực hiện caching; code nghiệp vụ vẫn cần tự xử lý input null.
- Không viết `condition = "#result == null"` để kiểm tra kết quả: vào giai đoạn `condition`, method chưa có kết quả để kiểm tra.

**Giới hạn API:** Không kết hợp `@Cacheable(sync = true)` với `unless`, vì Spring không hỗ trợ `unless` trong chế độ synchronized caching. Nếu cần đồng bộ việc load theo key và lọc kết quả rỗng, phải lựa chọn thiết kế khác dựa trên backend/cấu hình; không giả định hai thuộc tính sẽ hoạt động đồng thời.

## 5. Ví dụ Java 17+ chạy được: cache empty so với bỏ qua empty

Ví dụ chạy trên **Spring Framework 6.2.14**. Nó dùng `ConcurrentMapCacheManager` mặc định (cho phép null) và hai vùng cache tách biệt:

- `allowEmpty`: không có `unless`, vì thế một lần không tìm thấy cũng được nhớ lại.
- `skipEmpty`: có `unless = "#result == null"`, vì thế các lần không tìm thấy luôn phải tải lại.

Tạo dự án Gradle với hai tệp:

**`build.gradle`**

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
    mainClass = 'demo.OptionalCacheDemo'
}
~~~

**`src/main/java/demo/OptionalCacheDemo.java`**

~~~java
package demo;

import java.util.Optional;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class OptionalCacheDemo {

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("allowEmpty", "skipEmpty");
        }

        @Bean
        public BookService bookService() {
            return new BookService();
        }
    }

    public static class BookService {
        private int allowCalls;
        private int skipCalls;

        @Cacheable(cacheNames = "allowEmpty", key = "#p0")
        public Optional<String> allowEmpty(String id) {
            allowCalls++;
            return "found".equals(id)
                    ? Optional.of("Java")
                    : Optional.empty();
        }

        @Cacheable(
            cacheNames = "skipEmpty",
            key = "#p0",
            unless = "#result == null"
        )
        public Optional<String> skipEmpty(String id) {
            skipCalls++;
            return "found".equals(id)
                    ? Optional.of("Java")
                    : Optional.empty();
        }

        public int getAllowCalls() {
            return allowCalls;
        }

        public int getSkipCalls() {
            return skipCalls;
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // Lấy bean do Spring quản lý để @Cacheable được intercept.
            BookService books = context.getBean(BookService.class);
            CacheManager manager = context.getBean(CacheManager.class);

            System.out.println(books.allowEmpty("missing"));
            System.out.println(books.allowEmpty("missing"));
            System.out.println("allow calls: " + books.getAllowCalls());

            Cache allow = manager.getCache("allowEmpty");
            Cache.ValueWrapper cachedEmpty = allow.get("missing");
            System.out.println("empty entry exists: " + (cachedEmpty != null));
            System.out.println("empty raw value: " + cachedEmpty.get());

            System.out.println(books.skipEmpty("missing"));
            System.out.println(books.skipEmpty("missing"));
            System.out.println("skip calls: " + books.getSkipCalls());

            Cache skip = manager.getCache("skipEmpty");
            System.out.println("skipped entry exists: " +
                    (skip.get("missing") != null));

            System.out.println(books.allowEmpty("found"));
            System.out.println(books.allowEmpty("found"));
            System.out.println("stored present value: " +
                    allow.get("found").get());
            System.out.println("allow calls: " + books.getAllowCalls());
        }
    }
}
~~~

Chạy trong thư mục dự án có `build.gradle` và JDK/Gradle tương thích:

~~~bash
gradle run --quiet
~~~

**Stdout do ứng dụng in ra theo thứ tự** (không tính thông báo/lỗi cấu hình môi trường ngoài chương trình):

~~~text
Optional.empty
Optional.empty
allow calls: 1
empty entry exists: true
empty raw value: null
Optional.empty
Optional.empty
skip calls: 2
skipped entry exists: false
Optional[Java]
Optional[Java]
stored present value: Java
allow calls: 2
~~~

### Đọc kết quả

1. Hai lời gọi `allowEmpty("missing")` trả `Optional.empty` nhưng phần thân method chỉ chạy **một lần**; lần hai đọc entry cached null.
2. `allow.get("missing") != null` là `true` vì có **entry**; `cachedEmpty.get()` là `null` vì nội dung entry biểu diễn sự vắng mặt.
3. Hai lời gọi `skipEmpty("missing")` đều chạy phần thân (`skip calls: 2`) vì `unless` đã từ chối ghi null.
4. `skip.get("missing") == null` xác nhận không có entry ứng với key `missing`.
5. `allowEmpty("found")` trả `Optional[Java]` cả hai lần nhưng phía cache lưu **chuỗi `Java`**, không lưu object `Optional`. `allow calls` tăng từ 1 lên 2 do lần đầu truy vấn `found`, còn lần hai của `found` là cache hit.

Ví dụ cố ý dùng hai vùng cache khác nhau để việc cache kết quả rỗng ở trường hợp này không ảnh hưởng trường hợp kia. Trong ứng dụng thực, tên vùng cache và TTL phải được thiết kế theo yêu cầu dữ liệu.

**Lưu ý quan sát:** `Cache.get(key)` trả `ValueWrapper` hoặc null là API kiểm tra mức cache. Đừng dùng `Cache.get(key, String.class) == null` để khẳng định cache miss, vì API trả trực tiếp giá trị có thể cùng là null khi entry đã chứa cached null.

## 6. Nếu backend không chấp nhận null thì sao?

`ConcurrentMapCacheManager` mặc định cho phép null bằng cơ chế null holder; có thể thay đổi bằng:

~~~java
// Đoạn cấu hình minh họa, không phải chương trình độc lập.
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("products");
manager.setAllowNullValues(false);
~~~

Khi vô hiệu hóa null support, không nên mặc định rằng Spring có thể lưu `Optional.empty()`. Với implementation này, nỗ lực cache giá trị null có thể gây **IllegalArgumentException**. Dùng `unless = "#result == null"` nếu muốn bỏ qua kết quả rỗng, hoặc chọn backend có cơ chế **negative caching** rõ ràng nếu thực sự cần ghi nhớ “không tồn tại”.

Khả năng null không thuộc một cấu hình thống nhất trên mọi backend:

| Loại cache | Điều cần kiểm tra |
| --- | --- |
| `ConcurrentMapCacheManager` | `allowNullValues`; mặc định true trong Spring Framework |
| Caffeine qua Spring cache adapter | Cách adapter biểu diễn null và cờ cho phép null; không đánh đồng với native Caffeine |
| Redis/JCache/provider khác | Cấu hình chấp nhận null, serialization, TTL, kích thước vùng cache và contract cụ thể |
| Cache No-Op | Không giữ entry, nên cũng không giữ được cached null có ý nghĩa |

`null` trong bảng này là **giá trị logic ở API Spring Cache**. Backend có thể lưu byte marker, sentinel hoặc biểu diễn riêng; không mặc định byte thực tế trên Redis/JCache là Java `null`, càng không khẳng định có một `Optional.empty()` được serialize.

## 7. Nên cache kết quả rỗng hay bỏ qua?

### Khi cache kết quả rỗng có lợi

Ví dụ mã sản phẩm không hợp lệ thường bị truy vấn lặp hàng nghìn lần. Nếu xác nhận “không tồn tại” tương đối ổn định trong thời gian ngắn, cache một kết quả rỗng là **negative caching**:

- Lần đầu: gọi kho dữ liệu, trả `Optional.empty()` và lưu dấu hiệu vắng mặt.
- Lần sau cùng key: cache hit, không truy vấn kho dữ liệu.
- Hệ quả: giảm tải và độ trễ cho những key không tồn tại.

**Rủi ro:** Nếu sau đó có bản ghi mới cho key đã cached null, hệ thống vẫn có thể trả `Optional.empty()` cho đến khi entry bị evict/expire hoặc được cập nhật. Nên dùng **TTL ngắn**, evict đúng key khi tạo bản ghi, hoặc lựa chọn chiến lược cập nhật cache phù hợp. Spring Cache abstraction không tự đặt TTL thống nhất; cấu hình thời hạn thuộc backend.

### Khi bỏ qua kết quả rỗng có lợi

Với dữ liệu thường được tạo sau lần lookup thất bại (ví dụ trạng thái công việc đang chờ khởi tạo), `unless = "#result == null"` giúp lần gọi tiếp theo thử lại nguồn dữ liệu.

- **Ưu điểm:** dữ liệu mới xuất hiện có thể được nhìn thấy ngay ở lần lookup kế tiếp, miễn các tầng dữ liệu khác không giữ kết quả cũ.
- **Đổi lại:** nhiều lượt miss cùng key vẫn đánh xuống kho dữ liệu, có thể làm tăng chi phí hoặc tải cao (*cache penetration*).

Không có đáp án đúng cho mọi hệ thống. Hãy quyết định từ **tính thay đổi của dữ liệu, chi phí lookup, độ trễ cho phép và cách invalidation**, sau đó cấu hình nhà cung cấp cache.

| Tiêu chí | Cache `Optional.empty()` (nếu hỗ trợ) | Bỏ qua empty bằng `unless` |
| --- | --- | --- |
| Tải truy vấn lặp với key không tồn tại | Giảm đáng kể sau miss đầu tiên | Mỗi lượt miss thường phải truy vấn lại |
| Nhìn thấy record mới tạo | Có thể chậm tới khi evict/expire | Có cơ hội thấy ngay lần lookup sau |
| Yêu cầu provider | Cần hỗ trợ biểu diễn null/negative entry | Không bắt buộc hỗ trợ cache null |
| Vận hành | Cần TTL và quy tắc invalidate dữ liệu âm | Cần bảo vệ nguồn dữ liệu khi nhiều miss |
| Use case phù hợp | Dữ liệu “không tồn tại” ổn định, lookup tốn kém | Dữ liệu thường được bổ sung, yêu cầu nhìn thấy sớm |

Nếu một “không tìm thấy” thực tế có nhiều trạng thái (chưa tải xong, lỗi quyền, không tồn tại thật), đừng dồn mọi trạng thái về `Optional.empty()` rồi cache như nhau. Thiết kế kết quả nghiệp vụ rõ ràng trước khi quyết định chính sách cache.

## 8. Những lỗi phổ biến

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng Spring cache object `Optional.empty()` nguyên vẹn | Hiểu sai dữ liệu bên trong cache | Nhớ quy tắc unwrapping: empty thành cached null logic |
| Dùng `unless = "#result.isEmpty()"` | Đánh giá sai vì `#result` là đối tượng bên trong hoặc null | Dùng `unless = "#result == null"` khi muốn bỏ qua empty |
| Dùng `condition = "#result == null"` | Sai thời điểm đánh giá; chưa có result | Dùng `unless` để ra quyết định sau khi method chạy |
| Coi `cache.get(key) == null` và `cache.get(key).get() == null` là một | Nhầm cache miss với cached null | Kiểm tra `ValueWrapper` trước rồi mới lấy giá trị |
| Tắt null support nhưng vẫn cache Optional.empty | Ghi cache có thể lỗi ở provider | Bỏ qua empty hoặc cấu hình provider phù hợp |
| Cache null quá lâu khi bản ghi được tạo liên tục | Trả “không tìm thấy” sau khi dữ liệu đã tồn tại | TTL ngắn, evict key tại thao tác tạo/cập nhật |
| Bỏ qua empty trên API bị truy vấn nhiều key không tồn tại | Tải xuống database tăng | Rate limit, bảo vệ DB, hoặc negative cache có TTL |
| Dùng trực tiếp `cache.put(key, Optional.empty())` và chờ Spring tự mở wrapper | Lưu cấu trúc khác với caching interceptor | Dùng cache annotation theo contract hoặc tự chuẩn hóa giá trị khi gọi cache API |
| Quên `@EnableCaching` hoặc gọi method nội bộ qua `this` | Annotation không được intercept, khó nhận ra chính sách empty | Bật caching, gọi từ Spring bean khác qua proxy, kiểm tra hit/miss |
| Kết hợp `sync = true` với `unless` | Thuộc tính `unless` không được hỗ trợ trong synchronized caching | Thiết kế lại chính sách đồng bộ và lưu kết quả |

**Phân biệt thêm:** `Optional.empty()` là một kết quả *bình thường*. Ngoại lệ do cơ sở dữ liệu/HTTP thất bại là một sự kiện khác; `@Cacheable` không mặc nhiên cache exception như một “empty”.

## 9. Tự kiểm tra

**Câu 1.** Phương thức:

~~~java
@Cacheable(cacheNames = "books")
public Optional<String> find(String isbn) {
    return Optional.of("Spring");
}
~~~

Trên lần miss, Spring muốn lưu object nào?

**Đáp án:** Chuỗi `"Spring"` (giá trị bên trong `Optional`), không phải wrapper `Optional.of("Spring")`.

**Câu 2.** `Optional.empty()` được cache trong `ConcurrentMapCacheManager` mặc định. Lần sau cùng key có cần chạy method không?

**Đáp án:** Thông thường không: có entry cached null logic nên Spring có cache hit và trả `Optional.empty()`.

**Câu 3.** Khi `unless = "#result == null"`, `Optional.empty()` sẽ được cache không?

**Đáp án:** Không. Spring mở `Optional`, `#result` là null và biểu thức `unless` trở thành true nên thao tác ghi cache bị từ chối.

**Câu 4.** `#result.isEmpty()` có phải cách tổng quát để kiểm tra `Optional.empty()` trong Spring Cache SpEL không?

**Đáp án:** Không, vì `#result` không trỏ tới wrapper `Optional`; nó trỏ tới đối tượng bên trong hoặc null.

**Câu 5.** Dữ liệu trước đây không tồn tại nhưng vừa được thêm vào DB. Vì sao ứng dụng vẫn trả `Optional.empty()`?

**Đáp án:** Có thể key vẫn đang giữ cached null từ negative caching. Cần kiểm tra và xử lý TTL, evict hoặc cập nhật cache khi phát sinh bản ghi mới.

## 10. Ghi nhớ và tài liệu tham khảo

- `Optional.of(value)` → Spring cache **`value`**.
- `Optional.empty()` → Spring cache **`null` ở tầng logic**, nếu thao tác được phép và provider hỗ trợ.
- *Cache miss* khác *cached null*: `Cache.get(key) == null` khác `Cache.get(key).get() == null`.
- `unless = "#result == null"` → **không lưu Optional.empty()**; `#result` là dữ liệu đã mở wrapper.
- Cache “không tìm thấy” giúp giảm truy vấn nhưng cần TTL/invalidation; bỏ qua empty giúp thấy dữ liệu mới sớm hơn nhưng có thể tăng tải.
- Không phối hợp `sync = true` với `unless` trên `@Cacheable`.

**Tài liệu chính thức:**

- [Spring Framework — Declarative Annotation-based Caching (Optional và conditional caching)](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework 6.2 — @Cacheable API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Framework 6.2 — ConcurrentMapCacheManager API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html)
- [Spring Framework 6.2 — Cache và Cache.ValueWrapper API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/Cache.html)
