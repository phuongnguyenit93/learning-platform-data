# `unless` và từ chối lưu sau khi có kết quả trong Spring Cache

## Mục tiêu học tập

Trong Spring Cache, không phải kết quả nào của một phương thức cũng nên được giữ lại. Sau bài học, bạn sẽ biết cách dùng `@Cacheable(unless = "...")` để **từ chối ghi kết quả vừa tính** vào cache; giải thích thời điểm đánh giá `unless`, sử dụng biến SpEL `#result` an toàn với `null` và `Optional`, phân biệt nó với `condition`, và kiểm thử hành vi hit/miss. Bạn cũng sẽ nhận ra giới hạn quan trọng: **`unless` không xóa dữ liệu cũ, không biến kết quả thành lỗi và không được dùng như cơ chế phân quyền**.

Ví dụ xuyên suốt là một dịch vụ tra cứu báo giá: kết quả hợp lệ có thể dùng lại, kết quả đang chờ xử lý phải tính lại, còn kết quả không tồn tại có thể được chủ động từ chối cache.

## 1. `unless` giải quyết vấn đề gì?

Với annotation cơ bản:

~~~java
// Đoạn minh họa trên một service do Spring quản lý.
@Cacheable(cacheNames = "quotes", key = "#p0")
public Quote findQuote(String code) {
    return loadQuote(code);
}
~~~

Khi một lời gọi có khóa chưa tồn tại, Spring chạy thân phương thức rồi thường ghi kết quả vào cache. Lần gọi sau với cùng khóa có thể trả kết quả đã lưu mà không chạy lại `loadQuote`. Nhưng sẽ có những kết quả **không nên dùng lại**:

- Báo giá có trạng thái `PENDING` hoặc `TEMPORARY`, rất dễ thay đổi ngay sau khi phương thức trả về.
- Kết quả `null` hoặc `Optional.empty()` khi nghiệp vụ muốn lần sau truy vấn nguồn thêm một lần nữa.
- Phản hồi được đánh dấu `cacheable = false` theo quy tắc chất lượng dữ liệu.
- Kết quả thiếu các trường cần thiết hoặc thuộc một loại không nằm trong chính sách cache.

`unless` chính là **điều kiện từ chối ghi**. Nó nhận một biểu thức Spring Expression Language (SpEL) trả về boolean:

~~~java
// Có kết quả rồi mới quyết định có lưu hay không.
@Cacheable(cacheNames = "quotes",
           key = "#p0",
           unless = "#result == null || !#result.cacheable()")
public Quote findQuote(String code) {
    return loadQuote(code);
}
~~~

Nếu biểu thức `unless` đánh giá **`true`**, Spring **không đưa kết quả vừa trả về** vào cache. Nếu biểu thức là `false`, kết quả có thể được lưu theo cơ chế cache bình thường. Trong ví dụ, kết quả `null` hoặc có `cacheable()` trả `false` đều bị từ chối.

> Cách đọc dễ nhớ: `condition` hỏi **“có dùng cache cho lời gọi này không?”** trước khi thực hiện phương thức; `unless` hỏi **“có nên giữ lại kết quả vừa nhận không?”** sau khi thực hiện phương thức.

## 2. Luồng chạy: `condition` trước, `unless` sau

~~~text
Gọi service.findQuote(code) qua Spring proxy
                 |
                 v
       Kiểm tra condition (nếu có)
          /                  \
       false                true
         |                    |
  Chạy method trực tiếp    Tìm cache theo key
  (không lookup/put)         /             \
                           HIT            MISS
                            |               |
                      Trả giá trị       Chạy method
                       trong cache         |
                                           v
                                     Có kết quả?
                                           |
                                           v
                                    Tính unless
                                    /         \
                                  true       false
                                    |          |
                              Không ghi     Ghi cache
                              cache          |
                                    \        /
                                     Trả kết quả
~~~

Các bước trên mô tả `@Cacheable` thông thường khi `sync=false`, phương thức chạy đồng bộ và provider hỗ trợ thao tác phù hợp.

- **Cache hit:** phương thức không chạy; không có kết quả mới để đưa qua bước veto `unless`. Giá trị đã có trong cache được trả lại theo hành vi cache hit.
- **Cache miss, `unless=false`:** method chạy, Spring đưa kết quả vào cache; lần gọi sau có cơ hội hit.
- **Cache miss, `unless=true`:** method vẫn chạy và **kết quả vẫn trả cho caller**; chỉ việc ghi cache bị chặn. Lần sau có thể tiếp tục miss và method lại chạy.
- **Method ném exception:** không có kết quả trả về thành công để ghi theo luồng thông thường; `unless` không phải bộ bắt hoặc chuyển đổi exception.
- **`condition=false`:** operation không dùng cache cho lời gọi đó, kể cả lookup; không nên dùng `unless` để thay thế hoàn toàn `condition`.

Một lỗi hiểu sai phổ biến là nghĩ `unless=true` sẽ **trả `null` hoặc từ chối trả response**. Không đúng: nó từ chối *lưu kết quả*, không từ chối *trả kết quả*.

## 3. Bảng quyết định `condition` và `unless`

| `condition` | Có cache hit? | Kết quả từ method | `unless` | Hành vi chính |
| --- | --- | --- | --- | --- |
| `false` | Không tra cứu | Giá trị bất kỳ | Không cần veto | Chạy method, bỏ qua cache cho lời gọi |
| `true` | Có | Method không chạy | Không veto kết quả mới | Trả entry đã cache |
| `true` | Không | `Quote` hợp lệ | `false` | Chạy method, ghi entry, trả kết quả |
| `true` | Không | `Quote` tạm thời | `true` | Chạy method, **không ghi**, vẫn trả kết quả |
| `true` | Không | `null` | `#result == null` là `true` | Không cache kết quả `null` |
| `true` | Không | Ném exception | Không có kết quả thành công | Exception lan truyền; không có kết quả mới để cache |

Nếu không khai báo `condition`, hãy xem điều kiện sử dụng cache là mặc định **được phép**. Nếu không khai báo `unless`, không có quy tắc veto hậu xử lý bổ sung.

`unless` không xử lý thời gian sống của một entry. Dù kết quả vừa trả về hợp lệ, về sau nó vẫn có thể trở nên cũ; khi đó cần `@CacheEvict`, `@CachePut`, TTL hoặc chính sách invalidation phù hợp.

## 4. Viết biểu thức `unless` với `#result`

`#result` là biến trong ngữ cảnh SpEL của Spring Cache biểu thị **giá trị kết quả đã được phương thức tạo ra**. Trong `unless` của `@Cacheable`, nó sẵn có sau lúc method thực thi thành công.

### Từ chối cache `null`

~~~java
// Minh họa: phương thức trả về Product hoặc null.
@Cacheable(cacheNames = "products",
           key = "#p0",
           unless = "#result == null")
public Product findById(String id) {
    return repository.findById(id).orElse(null);
}
~~~

Đây là trường hợp **không cache kết quả vắng mặt** (*không negative caching*). Nếu sản phẩm chưa tồn tại, mỗi lần gọi sẽ truy vấn lại nguồn. Hãy chọn chính sách này khi việc nhìn thấy dữ liệu mới xuất hiện nhanh hơn quan trọng hơn giảm truy vấn miss.

Không phải lúc nào cũng nên từ chối cache `null`: với dữ liệu ít thay đổi và traffic lớn, negative caching trong thời gian ngắn có thể giảm tải đáng kể. Spring cache provider có thể biểu diễn giá trị null hoặc không tùy cấu hình. Cần quyết định theo nghiệp vụ và provider.

### Từ chối dựa trên thuộc tính kết quả

~~~java
// Minh họa: Product có accessor status().
@Cacheable(cacheNames = "products",
           key = "#p0",
           unless = "#result == null || #result.status() == 'DRAFT'")
public Product load(String id) {
    return repository.load(id);
}
~~~

Biểu thức `||` dừng đánh giá khi vế trái đã đúng. Vì thế nếu `#result == null`, Spring không gọi `status()` trên null. Với một thuộc tính boolean, có thể viết `unless = "!#result.cacheable()"` **chỉ khi chắc chắn kết quả không bao giờ null**; nếu có khả năng null, thêm nhánh kiểm tra trước.

Phương thức accessor của Java record như `result.cacheable()` là một method và có thể gọi từ SpEL. Với Java bean thông thường, bạn có thể dùng `#result.active` (getter theo convention) hoặc gọi `#result.isActive()`, miễn đó là API thật của đối tượng và tương thích Spring Expression Language.

### Kết hợp đầu vào với kết quả

~~~java
// Không cache kết quả preview, hoặc kết quả có cờ không hợp lệ.
@Cacheable(cacheNames = "reports",
           key = "#p0 + ':' + #p1",
           unless = "#p1 == 'preview' || #result == null || !#result.valid()")
public Report load(String reportId, String mode) {
    return generateReport(reportId, mode);
}
~~~

`#p0` là đối số đầu, `#p1` là đối số thứ hai; cách này không phụ thuộc metadata tên tham số khi biên dịch. `#root.args[0]` cũng truy cập đối số đầu; `#root.methodName`, `#root.targetClass`, `#root.caches` cung cấp metadata lời gọi. Nối chuỗi bằng dấu `:` chỉ dùng để minh họa; nếu đối số có thể chứa `:`, cần encoding không nhập nhằng hoặc khóa cấu trúc.

Khi tiêu chí từ chối **chỉ dựa trên input** và có thể quyết định trước khi tính kết quả, thường nên dùng `condition` để tránh thực hiện cache lookup không cần thiết. Khi tiêu chí cần trạng thái của giá trị vừa tính, `unless` mới có vai trò riêng.

## 5. Ví dụ chạy được: kết quả hợp lệ được cache, kết quả tạm thời bị từ chối

Dự án mẫu dùng **Java 17+, Spring Boot 3.3.5, Maven** và `ConcurrentMapCacheManager` để bạn thấy số lần method thật sự chạy. Có bốn trường hợp: `OK` được cache, `PENDING` trả về nhưng không cache, `MISSING` trả `null` và không cache, `BYPASS` bị `condition` loại khỏi cache từ đầu.

Cấu trúc thư mục:

~~~text
unless-demo/
├── pom.xml
└── src/main/java/example/unlessdemo/
    ├── DemoApplication.java
    └── QuoteService.java
~~~

**`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>unless-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/example/unlessdemo/DemoApplication.java`**:

~~~java
package example.unlessdemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("quotes");
    }

    @Bean
    CommandLineRunner demo(QuoteService quotes) {
        return args -> {
            print(quotes.find("OK"));
            print(quotes.find("OK"));

            print(quotes.find("PENDING"));
            print(quotes.find("PENDING"));

            print(quotes.find("MISSING"));
            print(quotes.find("MISSING"));

            print(quotes.find("BYPASS"));
            print(quotes.find("BYPASS"));
        };
    }

    private static void print(QuoteService.Quote quote) {
        if (quote == null) {
            System.out.println("null");
        } else {
            System.out.println(quote.code() + " -> " + quote.payload()
                    + ", cacheable=" + quote.cacheable());
        }
    }
}
~~~

**`src/main/java/example/unlessdemo/QuoteService.java`**:

~~~java
package example.unlessdemo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private final AtomicInteger loads = new AtomicInteger();

    public record Quote(String code, String payload, boolean cacheable) {}

    @Cacheable(
            cacheNames = "quotes",
            key = "#p0",
            condition = "#p0 != 'BYPASS'",
            unless = "#result == null || !#result.cacheable()"
    )
    public Quote find(String code) {
        int attempt = loads.incrementAndGet();

        if ("MISSING".equals(code)) {
            return null;
        }

        boolean eligible = !"PENDING".equals(code);
        return new Quote(code, "load#" + attempt, eligible);
    }
}
~~~

Chạy trong thư mục `unless-demo` (JDK 17+ và Maven đã cài):

~~~bash
mvn -q spring-boot:run
~~~

Các dòng ứng dụng **chủ động in từ `CommandLineRunner`** sẽ là (log Spring có thể xuất hiện thêm):

~~~text
OK -> load#1, cacheable=true
OK -> load#1, cacheable=true
PENDING -> load#2, cacheable=false
PENDING -> load#3, cacheable=false
null
null
BYPASS -> load#6, cacheable=true
BYPASS -> load#7, cacheable=true
~~~

Cách đọc output:

1. `OK` lần đầu miss, method chạy (`load#1`); `unless` là `false` nên cache được ghi. Lần thứ hai hit, vẫn `load#1`.
2. `PENDING` có `cacheable=false`; `unless` là `true` nên không ghi. Lần thứ hai phải chạy method tiếp và tăng từ `load#2` lên `load#3`.
3. `MISSING` trả `null` ở cả hai lần. Vế `#result == null` khiến mỗi lần đều bị từ chối ghi; phương thức đã chạy ở lần thứ 4 và thứ 5, dù output chỉ hiện `null`.
4. `BYPASS` có `condition=false`, Spring bỏ qua cache ngay từ đầu, nên hai lần lần lượt tạo `load#6` và `load#7`. Dù đối tượng `cacheable=true`, condition đã quyết định không tham gia cache.

`ConcurrentMapCacheManager("quotes")` tạo vùng cache tĩnh trong bộ nhớ JVM, không có TTL tích hợp như các provider chuyên dụng. `AtomicInteger` chỉ để đếm lần thực thi, không tham gia tính khóa. Ứng dụng chạy qua bean Spring: nếu `this.find("OK")` được gọi **từ chính `QuoteService`** trong proxy mode mặc định, cache interceptor có thể bị bỏ qua.

### Thử chứng minh cache chỉ có entry được chấp nhận

Để quan sát trực tiếp, bạn có thể thêm các dòng sau **sau tám lời gọi** trong `CommandLineRunner` (giả sử thêm tham số `CacheManager cacheManager` vào chữ ký bean):

~~~java
// Đoạn bổ sung trong demo đã có cacheManager; không phải file độc lập.
var cache = cacheManager.getCache("quotes");
System.out.println("OK cached: " + (cache.get("OK") != null));
System.out.println("PENDING cached: " + (cache.get("PENDING") != null));
System.out.println("MISSING cached: " + (cache.get("MISSING") != null));
System.out.println("BYPASS cached: " + (cache.get("BYPASS") != null));
~~~

Kết quả kỳ vọng của **bốn dòng kiểm tra bổ sung**:

~~~text
OK cached: true
PENDING cached: false
MISSING cached: false
BYPASS cached: false
~~~

Trong ứng dụng thực, test nên kiểm tra cache entry theo cả cache name và key, đồng thời kiểm tra số lần đọc nguồn; việc log chỉ một chuỗi giá trị chưa chứng minh cache đã thực sự được ghi.

## 6. `Optional<T>` và `#result`: có một chi tiết dễ nhầm

Spring Cache hỗ trợ kết quả `Optional<T>`. Trong các biểu thức hậu xử lý như `unless`, **`#result` chỉ đối tượng bên trong `Optional`**, không phải wrapper `Optional`:

- `Optional.of(book)` → `#result` trỏ tới `book`.
- `Optional.empty()` → `#result` là `null`.
- Nếu không veto, Spring có thể lưu giá trị bên trong hoặc biểu diễn null theo khả năng provider; khi gọi lại, Spring tái dựng wrapper tương ứng.

Ví dụ:

~~~java
// Đoạn minh họa trên service, repository không được khai báo trong đoạn này.
@Cacheable(cacheNames = "books",
           key = "#p0",
           unless = "#result == null || #result.hardback()")
public Optional<Book> findBook(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

Giả sử `Book` có phương thức `boolean hardback()`: sách bìa cứng hoặc không tìm thấy sẽ không được cache; sách bìa mềm được phép. **Đừng viết `#result.isEmpty()` ở đây** với ý định kiểm tra `Optional.empty()`, vì `#result` không phải đối tượng `Optional`.

Tài liệu Spring cũng cho ví dụ cú pháp null-safe `#result?.hardback`. Bạn có thể dùng phép kiểm tra rõ `#result == null || ...` khi cần biểu thức boolean dễ đọc, đặc biệt nếu muốn từ chối kết quả trống. Nếu biểu thức gọi thuộc tính trên `null` mà không có bảo vệ, bạn có thể gặp lỗi đánh giá SpEL.

`Optional.empty()` không nhất thiết luôn nên bị từ chối lưu: có những truy vấn thất bại rất thường xuyên, nên cache vắng mặt với TTL ngắn để giảm tải. Chính sách ấy gọi là **negative caching**; nếu muốn áp dụng, không đặt một biểu thức `unless` loại `null` một cách vô điều kiện.

## 7. `unless` khác kiểm tra `condition` ở đâu?

Đặt cùng một quy tắc vào hai thuộc tính có thể dẫn tới cách chạy khác nhau.

~~~java
// Chỉ dùng cache nếu input hợp lệ: kiểm tra trước method.
@Cacheable(cacheNames = "searches",
           key = "#p0",
           condition = "#p0.length() <= 16")
public SearchResult search(String query) {
    return performSearch(query);
}
~~~

`condition` nhìn được input, có thể tránh hoàn toàn lookup/put khi input dài. Nếu cần nhìn kết quả, dùng `unless`:

~~~java
// Cần kết quả tính xong mới biết có phù hợp cache hay không.
@Cacheable(cacheNames = "searches",
           key = "#p0",
           unless = "#result == null || #result.truncated()")
public SearchResult search(String query) {
    return performSearch(query);
}
~~~

Trong cả hai đoạn, `SearchResult` và `performSearch` là kiểu/hàm minh họa của ứng dụng, **không phải ví dụ chạy độc lập**.

| Tiêu chí | `condition` | `unless` |
| --- | --- | --- |
| Thời điểm | Trước khi truy cập/ghi cache cho lời gọi | Sau khi method đã trả kết quả để quyết định ghi |
| Ý nghĩa khi biểu thức `true` | **Cho phép** cache | **Từ chối** cache |
| Sử dụng `#result` của `@Cacheable` | Không | Có |
| Khi biểu thức `false` | Bỏ qua cache, gọi method | Có thể ghi kết quả vào cache |
| Cache hit trước đó | Condition có thể chặn sử dụng cache ngay | Unless không tái kiểm tra kết quả mới vì method không chạy |
| Trường hợp điển hình | Lọc theo tham số, ngữ cảnh lời gọi | Lọc theo trạng thái, chất lượng, null, dữ liệu vừa tính |

Vì hai điều kiện có ý nghĩa ngược nhau về boolean, đặt nhầm `condition="#result..."` hay `unless="#p0..."` có thể khiến code hoạt động khác dự kiến. `condition` của `@Cacheable` **không được dựa vào kết quả mới**, vì tại thời điểm đánh giá chưa chạy method.

## 8. `unless` có thay đổi hoặc xóa giá trị đã nằm trong cache không?

**Không.** `unless` chỉ quyết định có **ghi giá trị mới** vào cache tại một lần miss hay không. Nếu key đã có entry, Spring có thể trả entry đó ngay mà không thực thi lại method hoặc kiểm tra lại giá trị kết quả bằng `unless`.

Ví dụ tình huống nghiệp vụ:

~~~text
T0: read("Q1") -> APPROVED, trúng quy tắc được cache.
T1: nguồn đổi "Q1" thành PENDING.
T2: read("Q1") -> vẫn có thể trả APPROVED từ cache hit.
~~~

`unless="#result.status() == 'PENDING'"` **không giải quyết được T2**, vì method không chạy lại để tạo `PENDING`. Cần cơ chế **invalidation** khi nguồn thay đổi:

~~~java
// Đoạn minh họa; updateQuote(...) cập nhật dữ liệu nguồn.
@CacheEvict(cacheNames = "quotes", key = "#p0")
public void updateQuoteStatus(String code, String status) {
    repository.updateStatus(code, status);
}
~~~

Nếu muốn update trực tiếp cache thay vì evict, dùng `@CachePut` theo chính sách dữ liệu; cần bảo đảm kết quả và key phù hợp. Một phương thức `@CachePut` vẫn chạy để tính kết quả mới, khác với `@Cacheable` có thể bỏ qua method. Tránh gắn `@CachePut` và `@Cacheable` lên cùng một method trong trường hợp thông thường.

### Lưu ý với dữ liệu nhạy cảm

`unless` **không phải** kiểm tra quyền truy cập. Nếu một kết quả nhạy cảm từng được cache cho một user rồi quyền bị thu hồi, `unless` không đảm bảo cache hit cũ bị chặn. Cần kiểm tra quyền ở nơi chắc chắn chạy cho mọi request và thiết kế cache key, invalidation/TTL phù hợp. Không dùng `unless` để biến dữ liệu chưa được cấp quyền thành “an toàn”.

## 9. Những điều kiện không phù hợp để đặt trong `unless`

Không nên lạm dụng `unless` cho mọi loại kiểm tra:

1. **Đầu vào không được phép:** nếu từ input đã biết lời gọi không nên cache, cân nhắc `condition`; nếu input trái nghiệp vụ, trả lỗi từ validation/authorization, không chỉ veto cache.
2. **Lỗi hệ thống hoặc exception:** mặc định phương thức ném lỗi thì không có giá trị trả về để cache. `unless` không bắt exception; dùng exception handling riêng nếu muốn chuyển lỗi thành kết quả nghiệp vụ.
3. **Quy tắc TTL:** `unless` không đặt “chỉ cache 10 giây” cho entry. TTL thuộc provider/configuration, hoặc cần chiến lược expiration rõ ràng.
4. **Kết quả thay đổi nhanh:** `unless` có thể tránh lưu trạng thái tạm thời, nhưng trạng thái hợp lệ được cache vẫn cần invalidation khi dữ liệu nguồn đổi.
5. **Side effect trong SpEL:** đừng gọi DB, HTTP, thay đổi state hoặc hàm nặng chỉ để quyết định có cache hay không. Biểu thức nên nhanh, xác định và không gây side effect.
6. **Đầu vào có secrets:** tránh đưa access token, mật khẩu, dữ liệu nhạy cảm vào key/log để dựng biểu thức; một biểu thức `unless` không che giấu dữ liệu trong key vật lý.
7. **Kỳ vọng đồng bộ theo key:** `@Cacheable(sync=true)` không hỗ trợ `unless`. Không thể ghép hai thuộc tính để vừa khóa việc tính toán vừa veto kết quả theo cách ấy.

### Tại sao `sync=true` không kết hợp được với `unless`?

`sync=true` là gợi ý để provider đồng bộ việc tính cùng key khi nhiều thread cùng gặp miss, thường dựa trên thao tác load-atomically của cache. Trong khi đó `unless` cần kết quả chạy xong mới quyết định **không ghi**. API `@Cacheable` quy định rõ `unless` không được hỗ trợ ở chế độ synchronized caching.

~~~java
// Phản ví dụ: cấu hình không hợp lệ cho @Cacheable.
@Cacheable(cacheNames = "quotes",
           sync = true,
           unless = "#result == null")
public Quote findQuote(String code) {
    return loadQuote(code);
}
~~~

Nếu mục tiêu là hạn chế nhiều thread cùng truy vấn nguồn và tránh cache kết quả tạm thời, hãy thiết kế cơ chế single-flight/locking ở tầng dịch vụ hoặc cơ chế loader/refresh của provider phù hợp, và kiểm thử riêng. Chỉ cần `@Cacheable(sync=true)` khi không dùng `unless` và provider hỗ trợ đúng ngữ nghĩa mong đợi.

## 10. Kết quả không đồng bộ và reactive

Từ Spring Framework 6.1, cache abstraction có hỗ trợ thích ứng cho `CompletableFuture` và các kiểu reactive thường dùng: giá trị hoàn tất mới là dữ liệu lưu; provider cần đáp ứng cơ chế truy vấn bất đồng bộ tương ứng.

~~~java
// Minh họa: phương thức trả về CompletableFuture.
@Cacheable(cacheNames = "quotes",
           key = "#p0",
           unless = "#result == null")
public CompletableFuture<Quote> asyncQuote(String code) {
    return fetchAsync(code);
}
~~~

Đoạn này minh họa cú pháp, không phải file Java độc lập; `fetchAsync` do ứng dụng định nghĩa. Với xử lý bất đồng bộ, thời điểm có kết quả và lúc ghi cache có thể khác với lúc method trả `CompletableFuture`. Không suy luận `#result` luôn là object `CompletableFuture` chỉ vì kiểu trả về của Java method: Spring có cơ chế unwrap giá trị được hỗ trợ. Hãy kiểm thử SpEL hậu xử lý và caching trên **phiên bản Spring/provider thực tế**.

Các chuỗi reactive phức tạp có thể liên quan backpressure, stream nhiều phần tử và biến đổi ngữ cảnh. Annotation caching phù hợp với các kết quả đã tính có ngữ nghĩa rõ; đừng mặc định có thể cache nguyên một luồng vô hạn hay một đối tượng publisher tùy ý. Với `Flux`, Spring có thể thu gom giá trị thành danh sách để cache. Những tương tác đặc thù cần chiến lược cache được thiết kế theo pipeline.

## 11. Kiểm thử `unless` đúng cách

Dùng mock/repository stub hoặc bộ đếm như ví dụ để kiểm chứng **khác biệt giữa kết quả được trả và kết quả được lưu**. Bộ test cơ bản nên bao gồm:

| Ca kiểm thử | Lời gọi | Mong đợi |
| --- | --- | --- |
| Kết quả hợp lệ | `find("OK")` hai lần | Method chạy một lần; lần thứ hai hit |
| Kết quả `cacheable=false` | `find("PENDING")` hai lần | Method chạy hai lần; cả hai vẫn trả `Quote` |
| Kết quả `null` | `find("MISSING")` hai lần | Method chạy hai lần; không có entry `MISSING` |
| `condition=false` | `find("BYPASS")` hai lần | Không dùng cache; method chạy hai lần |
| Sai key/cache name | Cùng input nhưng vùng/khóa khác | Đừng kết luận `unless` hỏng; kiểm tra key trước |
| Giá trị cũ đã tồn tại | Cache đang có `OK`, nguồn đổi trạng thái | Có thể hit entry cũ; cần test eviction |
| Nhiều thread cùng miss | Cùng key, `sync=false` | Có thể có nhiều lần tính; test theo provider thực tế |
| Return `Optional.empty()` | Biểu thức `#result == null` | Không cache kết quả vắng mặt |
| Truy cập proxy | Service được gọi từ bean khác | Cache advice hoạt động |
| Self-invocation | `this.find(...)` trong cùng object | Có thể bỏ qua proxy mặc định |

Trong kiểm thử tích hợp thực, nên lấy `Cache` bằng `CacheManager.getCache("quotes")` và kiểm tra `get(key)`: `null` từ `Cache.get(key)` biểu thị không có entry, còn `Cache.ValueWrapper` với `get()` trả `null` có thể biểu thị **entry được cache với giá trị null**. Phân biệt hai trường hợp này quan trọng khi viết test negative caching.

Có thể thêm test kiểm tra biểu thức SpEL với `null` để tránh lỗi `EL1007E`/đọc thuộc tính trên null. Cũng nên kiểm thử các điều kiện ranh giới như chuỗi rỗng, trạng thái mới và tên cache có cấu hình serializer khác nhau.

## 12. Sai lầm phổ biến

| Dấu hiệu | Cách hiểu sai hoặc nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Kết quả vẫn được trả dù `unless=true` | Tưởng `unless` chặn response | `unless` chỉ chặn **ghi cache**, kết quả vẫn trả |
| Không thấy thay đổi sau khi đổi `unless` | Key cũ đã nằm trong cache | Evict hoặc clear entry theo kế hoạch; test từ cache sạch |
| `#result.property` gây lỗi | Kết quả có thể null hoặc không có getter/accessor | Kiểm tra `#result == null` trước; xác nhận tên accessor |
| `Optional.empty()` không bị chặn như mong muốn | Dùng `#result.isEmpty()` vì nghĩ result là Optional | Dùng `#result == null` cho empty |
| `condition` và `unless` cho kết quả khác | Nhầm thời điểm và ý nghĩa boolean | `condition=true` cho dùng cache; `unless=true` veto put |
| Luôn truy vấn lại nguồn | Biểu thức `unless` luôn true, hoặc `condition` luôn false | Log trạng thái an toàn, test đếm lần method chạy |
| `unless` không chạy trong self-invocation | Method gọi từ cùng bean nên không qua cache proxy | Gọi qua Spring-managed bean khác hoặc cân nhắc AspectJ |
| Lỗi cấu hình với `sync=true` | Sync mode không hỗ trợ veto result | Không ghép `sync=true` với `unless` |
| Dữ liệu đã cache trở nên stale | Không có invalidation khi dữ liệu nguồn thay đổi | Dùng `@CacheEvict`, `@CachePut`, TTL hoặc version policy |
| Bỏ sót dữ liệu phân quyền | Chỉ dựa `unless` mà không kiểm tra authorization | Đặt check quyền trên mọi request, key theo scope hợp lệ |

Đối với production, hãy giữ biểu thức ngắn và dễ kiểm thử. Nếu chính sách đủ phức tạp để cần truy vấn DB, biến đổi payload hoặc phụ thuộc nhiều service, cân nhắc tính một cờ `cacheable` từ tầng nghiệp vụ rồi kiểm tra cờ đó bằng `unless`, đồng thời bảo đảm không làm rò dữ liệu khi một entry cũ vẫn hit.

## 13. Bài tập tự kiểm tra

**Bài 1.** `@Cacheable(unless="#result == null")` trả `null` ở lần đầu. Lần gọi sau với cùng key có cần chạy method không?  
**Đáp án:** có, nếu trước đó không có entry khác và hoạt động theo `@Cacheable` thông thường. `unless` đã veto ghi kết quả `null`.

**Bài 2.** `unless="#result.status() == 'DRAFT'"` có an toàn nếu method có thể trả `null`?  
**Đáp án:** không. Hãy kiểm tra null trước, ví dụ `#result == null || #result.status() == 'DRAFT'`; hoặc chọn cú pháp null-safe hợp lệ theo kiểu kết quả.

**Bài 3.** Một báo giá `"Q1"` đã được cache lúc còn trạng thái `READY`. Sau đó DB đổi thành `DRAFT`. Tại sao `unless` không làm lần đọc kế tiếp thấy `DRAFT`?  
**Đáp án:** lần đọc có thể hit bản `READY` và method không chạy. `unless` không kiểm tra lại giá trị cũ; cần eviction/TTL/version theo nghiệp vụ.

**Bài 4.** Khi nào dùng `condition="#p0.length() <= 16"`, khi nào dùng `unless="#result.truncated()"`?  
**Đáp án:** điều kiện phụ thuộc đối số và có thể biết **trước khi chạy** thì dùng `condition`; phụ thuộc kết quả vừa tạo thì dùng `unless`.

**Bài 5.** Có thể đặt `@Cacheable(sync=true, unless="#result == null")` để chỉ một thread tính dữ liệu và không ghi null không?  
**Đáp án:** không, `sync=true` không hỗ trợ `unless`. Cần thiết kế chiến lược đồng thời và veto khác hoặc bỏ một trong hai yêu cầu.

## Tài liệu tham khảo chính thức

- Spring Framework – Declarative Annotation-based Caching, mục *Conditional Caching*, *Available Caching SpEL Evaluation Context* và *Synchronized Caching*: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – Javadoc `@Cacheable` (Spring 6.2), hợp đồng `condition`, `unless`, `sync`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework – Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Boot – Caching providers: https://docs.spring.io/spring-boot/reference/io/caching.html

**Ghi nhớ:** `unless` là **quy tắc veto việc lưu kết quả mới sau khi method hoàn thành**. `true` nghĩa là không cache, nhưng vẫn trả kết quả. Dùng `#result` với kiểm tra `null`, phân biệt với `condition`, và luôn có kế hoạch invalidation cho dữ liệu đã được cache trước đó.