# `#result` của `Optional` và toán tử điều hướng an toàn trong Spring Cache

## 1. Mục tiêu bài học

Khi một phương thức Spring Cache trả về `Optional<T>`, điều kiện lưu cache không chỉ cần biết phương thức trả về cái gì mà còn phải biết **Spring biểu diễn kết quả đó trong SpEL như thế nào**. Một lỗi thường gặp là viết `unless = "#result.isEmpty()"` vì cho rằng `#result` là `Optional`. Trong ngữ cảnh cache annotation, điều đó không đúng: với kiểu wrapper được Spring hỗ trợ như `Optional`, **`#result` trỏ tới giá trị nghiệp vụ bên trong wrapper**. `Optional.empty()` được diễn giải như **`null`** khi đánh giá `#result` trong các cache expression có quyền truy cập kết quả.

Bài này giải thích đầy đủ ba điểm liên quan đến **Điều kiện lưu**:

1. `condition` và `unless` được đánh giá ở những thời điểm khác nhau; `#result` chỉ khả dụng ở các vị trí có kết quả.
2. Với `Optional<T>`, cách kiểm tra `#result` phải dựa trên `T` hoặc `null`, không dựa trên API `Optional.isPresent()`/`isEmpty()`.
3. SpEL `?.` (safe navigation) tránh lỗi truy cập đối tượng `null`; nhưng nó chỉ bảo vệ thao tác được gắn toán tử, không tự quyết định có nên lưu kết quả rỗng vào cache.

Kết thúc bài, bạn có thể dự đoán cache hit/miss với `Optional.of(...)` và `Optional.empty()`, viết biểu thức `unless` an toàn, kiểm thử chính xác số lần phương thức thật được gọi và tránh nhầm lẫn giữa quy tắc unwrapping của Spring Cache với tính năng safe navigation trên `Optional` của SpEL ở các phiên bản Spring khác nhau.

## 2. Vị trí của `#result` trong luồng xử lý cache

`@Cacheable` thường thực hiện: đánh giá điều kiện theo arguments → tìm entry bằng key → nếu hit trả ngay kết quả từ cache → nếu miss gọi method → đánh giá `unless` trên **kết quả vừa tính** → lưu khi không bị veto. Lệnh gọi method có thể không diễn ra nếu cache đã hit, do đó không có một “kết quả method mới” để đánh giá `unless` trên nhánh hit thông thường.

~~~mermaid
flowchart TD
  A[Caller gọi bean qua proxy] --> B{condition đúng?}
  B -- Không --> C[Gọi method và trả kết quả]
  B -- Có --> D[Resolve cache và key]
  D --> E{Cache hit?}
  E -- Có --> F[Trả kết quả từ cache]
  E -- Không --> G[Gọi method thật]
  G --> H[Unwrap wrapper được hỗ trợ cho ngữ cảnh kết quả]
  H --> I{unless đánh giá true?}
  I -- Có --> J[Không put; vẫn trả kết quả method]
  I -- Không --> K[Put kết quả theo chính sách provider]
  K --> L[Trả kết quả method]
  J --> L
~~~

Sơ đồ minh họa trường hợp `@Cacheable` đồng bộ thông thường. Thực tế còn nhánh `sync=true`, nhiều operation, cache error, `CompletableFuture`/reactive và điều kiện với nhiều cache. Sơ đồ tập trung vào thời điểm đánh giá `#result`.

| Vị trí expression | Khi nào đánh giá? | Có `#result` không? | Mục đích |
| --- | --- | --- | --- |
| `@Cacheable(condition = "...")` | Trước lookup/call method, dựa vào input | **Không** | Quyết định có áp dụng caching cho invocation này không |
| `@Cacheable(key = "...")` | Khi xác định key để lookup | **Không** | Chọn entry để đọc; thường dùng arguments |
| `@Cacheable(unless = "...")` | Sau khi method hoàn thành trên nhánh cần tạo entry | **Có** | Veto việc ghi kết quả mới vào cache |
| `@CachePut(key = "...")` | Phục vụ ghi kết quả sau invocation | **Có thể dùng** | Chọn key dựa trên kết quả hoặc input |
| `@CachePut(unless = "...")` | Sau invocation | **Có** | Veto việc ghi kết quả |
| `@CacheEvict(key = "...", beforeInvocation = false)` | Sau invocation | **Có** | Chọn entry xóa dựa trên result nếu phù hợp |
| `@CacheEvict(beforeInvocation = true)` | Trước method | **Không** | Không có result để tham chiếu |

`@CacheEvict` **không có thuộc tính `unless`**. Các expression như `condition` là quyết định của operation tại thời điểm thích hợp; đừng dùng `#result` trong `condition` của `@Cacheable` hoặc mong nó xuất hiện trước khi method chạy.

## 3. `#result` với `Optional<T>`: giá trị `T` hay `null`

Xét khai báo sau (snippet cần nằm trong Spring bean có `Book` và `repository` tương ứng):

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null || #result?.archived() == true"
)
public Optional<Book> findBook(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

Giả sử `Book` có method `archived()` trả về `boolean`. Ba trường hợp quan trọng:

| Giá trị Java do method trả | Giá trị `#result` trong `unless` | `#result == null` | `#result?.archived() == true` | Kết quả |
| --- | --- | --- | --- | --- |
| `Optional.of(bookActive)` | `bookActive` (kiểu `Book`) | false | false | Cho phép put |
| `Optional.of(bookArchived)` | `bookArchived` (kiểu `Book`) | false | true | Không put |
| `Optional.empty()` | `null` | true | false (safe navigation trả `null`, so với `true` là false) | Không put |

Chú ý: `#result` **không phải `Optional<Book>`** trong ngữ cảnh trên. Vì vậy:

~~~java
// Sai về mặt ngữ nghĩa khi khai báo trả Optional<Book>:
@Cacheable(cacheNames = "books", unless = "#result.isEmpty()")

// Đúng khi muốn không lưu kết quả Optional.empty():
@Cacheable(cacheNames = "books", unless = "#result == null")

// Đúng khi muốn bỏ cả kết quả rỗng và sách archived:
@Cacheable(
    cacheNames = "books",
    unless = "#result == null || #result?.archived() == true"
)
~~~

Các dòng trên là **snippet annotation minh họa**, không phải source Java độc lập. Biểu thức đầu tiên có thể gây lỗi SpEL khi `#result` là `null` hoặc khi `Book` không có method `isEmpty()`. Không thể suy từ tên API của kiểu trả về method để áp dụng trực tiếp cho `#result`.

**Trường hợp kết quả không phải `Optional`:** với method trả `Book`, `#result` là `Book` hoặc `null` theo kết quả thực. Nếu method trả một wrapper tùy biến mà Spring Cache không có quy tắc unwrap tương ứng, không tự giả định `#result` là phần tử bên trong. Phải xác minh hành vi với framework và loại wrapper thực tế.

### `Optional.empty()` có được cache hay không?

Spring Cache hỗ trợ `Optional`: khi có giá trị, cache xử lý giá trị bên trong; khi rỗng, nó xử lý một kết quả `null` để cache provider có thể lưu nếu được cấu hình hỗ trợ null. **Không có `unless` phủ quyết thì một lookup không tìm thấy có thể được ghi cache** (negative caching). Ví dụ, `ConcurrentMapCacheManager` mặc định có thể lưu giá trị null qua cơ chế nội bộ; lần gọi kế tiếp vẫn có thể hit và được Spring thích ứng thành `Optional.empty()`. Không nên khẳng định mọi provider đều cache null giống nhau: khả năng lưu null, serialization và TTL tùy backend.

Hai chính sách đều hợp lệ tùy nhu cầu:

- **Không cache miss:** `unless = "#result == null"`. Phù hợp khi dữ liệu mới có thể xuất hiện sớm và bạn muốn lần sau thử lại ngay.
- **Cho phép cache miss:** bỏ phủ quyết null nếu provider hỗ trợ. Giảm số truy vấn lặp lại cho ID không tồn tại, nhưng có thể giữ trạng thái “không có dữ liệu” đến hết TTL hoặc đến khi bị evict. Cần thiết kế invalidation khi tạo mới bản ghi.

`unless` quyết định **ghi hay không ghi** sau invocation; nó không biến một `Optional.empty()` thành exception và không thay đổi kết quả trả về cho caller.

## 4. Toán tử SpEL `?.` hoạt động ra sao?

`?.` là toán tử **null-safe navigation** trong Spring Expression Language. Khi đối tượng bên trái null, toán tử trả `null` cho chính thao tác truy cập property/method đó thay vì cố gọi trên null.

Ví dụ về biểu thức:

~~~text
#result.name             // truy cập thông thường; lỗi nếu #result == null
#result?.name            // null khi #result == null
#result?.isArchived()    // null khi #result == null
#result?.price           // lấy price nếu có đối tượng; null nếu không
~~~

Đây là **các biểu thức SpEL minh họa**, không phải cú pháp Java. Với `Book` dùng Java record, cách chắc chắn là gọi accessor `#result?.archived()`; với Java bean có getter `getName()`, property style `#result?.name` phù hợp.

### 4.1. Safe navigation bảo vệ từng mắt xích

Biểu thức:

~~~text
#result?.owner.address.city
~~~

**Chưa an toàn toàn bộ.** Nếu `#result` null, `#result?.owner` tạo `null` nhưng phần còn lại `.address.city` vẫn được đánh giá, có thể dẫn tới lỗi. Nếu `owner` null, `.address` cũng gây lỗi.

Nên dùng:

~~~text
#result?.owner?.address?.city
~~~

Hoặc với method trên record:

~~~text
#result?.owner()?.address()?.city()
~~~

Khi bất kỳ mắt xích nào được đánh dấu `?.` gặp null, thao tác đó trả null; các mắt xích tiếp theo cũng phải dùng safe navigation khi cần. **`?.` không dừng toàn bộ compound expression một cách tự động.**

### 4.2. Kết quả `null` không đồng nghĩa với boolean `false`

Khi expression dùng để ra quyết định caching, hãy nêu rõ chính sách với giá trị null.

Ví dụ:

~~~java
// Chỉ veto khi archived() đúng; kết quả rỗng không bị veto:
@Cacheable(cacheNames = "books",
           unless = "#result?.archived() == true")

// Veto cả kết quả rỗng lẫn archived:
@Cacheable(cacheNames = "books",
           unless = "#result == null || #result?.archived() == true")

// Chỉ cache các Book có status = ACTIVE và khác null:
@Cacheable(cacheNames = "books",
           unless = "#result == null || #result?.status() != 'ACTIVE'")
~~~

Ở ví dụ cuối, giả định `status()` trả về `String`. `#result?.status() != 'ACTIVE'` đúng nếu status khác ACTIVE (kể cả null); vế `#result == null` làm ý định loại bỏ `Optional.empty()` rõ ràng. Với nested null hoặc kiểu enum, cách so sánh cần được điều chỉnh tương ứng.

Việc viết `unless = "#result?.archived()"` xuất hiện trong tài liệu Spring như ví dụ ngắn, nhưng đối với chính sách phức tạp cần kiểm tra rõ cách biểu thức chuyển thành boolean, tính nullable và dữ liệu business. Phong cách `== true` hoặc `== false` kèm quy tắc null rõ ràng thường dễ kiểm thử hơn.

### 4.3. Các toán tử khác dễ bị nhầm

| Cú pháp SpEL | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `?.` | Truy cập null-safe property/method | `#result?.archived()` |
| `?:` | Elvis: chọn giá trị thay thế khi null (theo ngữ nghĩa SpEL) | `#result?.nickname ?: 'N/A'` |
| `?.[]` | Null-safe indexing trong SpEL có hỗ trợ phiên bản tương ứng | `#result?.[0]` |
| `?.?`, `?.!`, `?.^`, `?.$` | Null-safe selection/projection đối với collection, khi phiên bản hỗ trợ | Xem Spring SpEL docs |

**Đừng nhầm `?.` của SpEL với Java `Optional.map(...)` hoặc toán tử của ngôn ngữ khác.** Java 17 không có cú pháp `obj?.member`; nó chỉ hợp lệ **bên trong chuỗi biểu thức SpEL** mà Spring phân tích.

## 5. Chú ý phiên bản: SpEL 7.0 và `Optional` trong biểu thức

Có **hai cơ chế unwrap khác nhau** mà người học dễ đánh đồng.

**Cơ chế A — Spring Cache `#result`:** Trong các expression caching hỗ trợ kết quả, Spring chuyển wrapper được hỗ trợ như `Optional<Book>` về `Book` hoặc `null` trước khi cho expression tham chiếu `#result`. Vì vậy `#result?.archived()` hoạt động theo chính giá trị `Book` hoặc null; đây là hợp đồng của Spring Cache và không cần tự gọi `Optional.get()`.

**Cơ chế B — Toán tử null-safe SpEL trên một biến thực sự kiểu `Optional`:** Tài liệu Spring Framework 7.0 giới thiệu hỗ trợ **transparent unwrapping cho `Optional` khi sử dụng toán tử null-safe**. Ví dụ một biến SpEL `#candidate` đúng nghĩa đang chứa `Optional<Book>`:

~~~text
#candidate?.title
~~~

Trong Spring Framework 7.0+, nếu `#candidate = Optional.of(book)`, toán tử null-safe có thể truy cập `title` trên đối tượng `book`; nếu `Optional.empty()`, nó trả null. Hành vi đó **khác với việc Spring Cache chuẩn bị `#result`**, vốn đã unwrap trước. Không nên đem cú pháp trên áp dụng cho các biến `Optional` bất kỳ ở phiên bản Spring 6.x nếu chưa xác minh tính năng; sự hỗ trợ null-safe trên `Optional` có thay đổi theo phiên bản.

Cũng theo tài liệu SpEL 7.0, các method thuộc API `Optional`, ví dụ `#candidate?.orElse('Unknown')`, vẫn có thể sử dụng. Tuy nhiên, khi nói về `unless` với `#result` trong Spring Cache, **đừng cố gọi `#result.orElse(...)`**: `#result` đã là giá trị nghiệp vụ hoặc null.

## 6. Mẫu biểu thức `condition`/`unless` đúng theo yêu cầu

Giả sử `findBook(String id)` trả `Optional<Book>`, trong đó `Book` có các accessor `archived()`, `price()`, `owner()`. Các mẫu sau chỉ là **phần annotation của Spring**, không phải chương trình độc lập.

### 6.1. Chỉ cache khi ID không rỗng và kết quả hợp lệ

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null || #result?.archived() == true"
)
~~~

`condition` kiểm tra **input** trước khi tra cache. Nếu sai, method vẫn chạy bình thường, cache operation không được áp dụng. `unless` chỉ chạy khi có kết quả mới cần quyết định ghi. Nếu `Optional.empty()`, `#result == null` true nên không cache miss; nếu sách archived, cũng không cache.

### 6.2. Chỉ lưu kết quả khi giá bán nằm trong ngưỡng

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null || #result?.price() > 1000000"
)
~~~

Ví dụ giả định `price()` trả một kiểu số so sánh với literal nguyên theo cách SpEL hỗ trợ, và nghiệp vụ muốn loại các giá trị trên ngưỡng. Với `BigDecimal` và tiền tệ thực tế, nên dùng so sánh phù hợp với kiểu dữ liệu và các ràng buộc tài chính; đừng coi số literal trên là mã hóa nghiệp vụ hoàn chỉnh.

### 6.3. Dựa trên thuộc tính lồng nhau có thể null

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null || #result?.owner()?.suspended() == true"
)
~~~

Nếu `Book.owner()` trả null, biểu thức `?.suspended()` tiếp tục bảo vệ an toàn. Nếu nghiệp vụ yêu cầu **không cache sách thiếu owner**, phải ghi thêm quy tắc rõ ràng, ví dụ:

~~~text
#result == null || #result?.owner() == null
    || #result?.owner()?.suspended() == true
~~~

Có thể đặt biểu thức dài trong một dòng giá trị annotation; xuống dòng ở đoạn text trên chỉ để dễ đọc. Null-safe **ngăn lỗi**, chứ không tự đặt ra chính sách nghiệp vụ cho dữ liệu thiếu.

### 6.4. Kiểm tra trạng thái enum

Với `BookStatus` là enum:

~~~java
@Cacheable(
    cacheNames = "books",
    unless = "#result == null || #result?.status() != T(com.example.BookStatus).ACTIVE"
)
~~~

Đây là snippet yêu cầu enum thực `com.example.BookStatus` trên classpath. Khi đưa vào dự án, thay bằng tên class thật. Có thể dùng `T(package.Enum)` để tham chiếu enum trong SpEL thay vì so sánh tùy tiện với chuỗi. Nếu `status()` null, biểu thức khác `ACTIVE` sẽ đánh giá true, phù hợp chính sách loại khỏi cache.

## 7. Ví dụ runnable Java 17+ với Spring Framework: quan sát `Optional.empty()`

Ví dụ gồm hai policy để phân biệt **veto miss** và **cache miss**. Dùng Spring Framework 7.0.9, JDK 17+ và Maven. Tạo các file theo đúng đường dẫn dưới đây.

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>optional-cache-conditions</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>7.0.9</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.2</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**`src/main/java/demo/OptionalCacheDemo.java`**

~~~java
package demo;

import java.util.Optional;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class OptionalCacheDemo {
    @Bean
    CacheManager cacheManager() {
        // Local cache; mặc định chấp nhận cached null.
        return new ConcurrentMapCacheManager("profiles", "negative");
    }

    @Bean
    ProfileService profileService() {
        return new ProfileService();
    }

    public record Profile(String id, boolean hidden) { }

    public static class ProfileService {
        private int loads;
        private int negativeLoads;

        @Cacheable(
            cacheNames = "profiles",
            key = "#p0",
            unless = "#result?.hidden() == true || #result == null"
        )
        public Optional<Profile> find(String id) {
            System.out.println("DB find #" + (++loads) + " " + id);
            return switch (id) {
                case "public" -> Optional.of(new Profile(id, false));
                case "private" -> Optional.of(new Profile(id, true));
                default -> Optional.empty();
            };
        }

        @Cacheable(cacheNames = "negative", key = "#p0")
        public Optional<Profile> findAllowMissing(String id) {
            System.out.println("DB negative #" + (++negativeLoads));
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             OptionalCacheDemo.class)) {
            var service = context.getBean(ProfileService.class);

            System.out.println(service.find("public"));
            System.out.println(service.find("public"));

            System.out.println(service.find("private"));
            System.out.println(service.find("private"));

            System.out.println(service.find("unknown"));
            System.out.println(service.find("unknown"));

            System.out.println(service.findAllowMissing("unknown"));
            System.out.println(service.findAllowMissing("unknown"));
        }
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.OptionalCacheDemo
~~~

Những dòng do chính chương trình in ra (không tính Maven/framework log):

~~~text
DB find #1 public
Optional[Profile[id=public, hidden=false]]
Optional[Profile[id=public, hidden=false]]
DB find #2 private
Optional[Profile[id=private, hidden=true]]
DB find #3 private
Optional[Profile[id=private, hidden=true]]
DB find #4 unknown
Optional.empty
DB find #5 unknown
Optional.empty
DB negative #1
Optional.empty
Optional.empty
~~~

**Diễn giải chính xác:**

1. Lần đầu `find("public")`: miss, method chạy, `#result` là `Profile(hidden=false)`. `unless` false, cache được ghi. Lần hai hit nên không tăng `loads`.
2. `find("private")`: `#result?.hidden() == true`, kết quả bị veto. Cả hai lời gọi đều chạy method nên có DB find #2 và #3.
3. `find("unknown")`: trả `Optional.empty()`, `#result` trong `unless` là null. Toán tử `?.` trả null, điều kiện `#result == null` true nên **không** cache; mỗi lời gọi lại chạy method (#4 và #5).
4. `findAllowMissing("unknown")`: không có `unless` nên cache cho phép lưu “không tìm thấy” qua khả năng hỗ trợ null của `ConcurrentMapCacheManager`. Lần hai nhận `Optional.empty()` từ cache, **không** in DB negative #2.

Ví dụ có cấu hình `@EnableCaching`, lấy `ProfileService` từ Spring context để bảo đảm lời gọi đi qua proxy. Nếu tự `new ProfileService().find(...)` hoặc gọi trực tiếp method cacheable qua `this` trong cùng bean ở proxy mode mặc định, advice có thể không chạy nên kết quả đo khác đi.

## 8. Tương tác với `@CachePut`, `@CacheEvict` và key SpEL

Mặc dù trọng tâm là điều kiện lưu `@Cacheable`, điều quan trọng là hiểu những vị trí khác có thể xuất hiện `#result`.

**`@CachePut`** luôn gọi business method, sau đó put kết quả theo key/điều kiện phù hợp. Nếu method trả `Optional<Book>`, biểu thức kết quả ở vị trí được hỗ trợ cũng sử dụng giá trị nghiệp vụ bên trong wrapper. Ví dụ:

~~~java
@CachePut(
    cacheNames = "books",
    key = "#result?.isbn()",
    unless = "#result == null"
)
public Optional<Book> save(BookDraft draft) {
    // Ghi dữ liệu và trả Optional<Book>
}
~~~

Đây là **snippet**; nếu `#result` null, key expression `#result?.isbn()` trả null. Một số cache pipeline/kiểu expression có thể reject null key hoặc gây lỗi ngay cả khi bạn kỳ vọng `unless` sẽ veto. **Ưu tiên key ổn định từ input** (ví dụ `key="#p0.isbn()"`) khi có thể, hoặc kiểm thử nhánh null theo phiên bản Spring thực tế; không dựa vào `unless` như một bảo đảm mọi key expression với null đều hợp lệ.

**`@CacheEvict`** mặc định chạy sau method nên có thể tham chiếu `#result` trong key expression. Nếu `beforeInvocation=true`, chưa có result; phải dùng arguments để tính key. Không có thuộc tính `unless`.

**`@Caching`** có thể khai báo nhiều operation trên một method; các operation có thời điểm đánh giá khác nhau. Tránh kết hợp `@Cacheable` và `@CachePut` trên cùng method nếu chưa hiểu điều kiện loại trừ, vì một operation có thể bỏ qua method trong khi operation kia cần chạy method.

## 9. Lỗi phổ biến khi viết `unless` cho `Optional`

| Lỗi | Vì sao sai hoặc nguy hiểm? | Cách viết phù hợp |
| --- | --- | --- |
| `unless="#result.isEmpty()"` | `#result` không phải `Optional`, có thể null | `unless="#result == null"` |
| `unless="#result.get().archived()"` | `#result` đã unwrap; `get()` không hợp lệ cho `Book` | `unless="#result?.archived() == true"` |
| `condition="#result != null"` | `condition` của `@Cacheable` không có result | Chuyển quy tắc kết quả sang `unless` |
| `unless="#result.archived()"` | Lỗi null dereference khi `Optional.empty()` | Dùng `?.` và chính sách null rõ ràng |
| `unless="#result?.owner.address.city == 'X'"` | Safe navigation chỉ bảo vệ `result` tại `owner` | `#result?.owner?.address?.city` nếu property chain phù hợp |
| `unless="#result?.archived() == true"` khi **muốn bỏ cả null** | Null không bằng true; empty vẫn có thể được cache | Thêm `#result == null || ...` |
| `#result.orElse(null)` | `#result` không còn là `Optional` | Truy cập `#result` trực tiếp |
| Cho rằng mọi provider lưu được null | Có backend cấm/khác cách biểu diễn null | Kiểm tra `Cache` implementation và cấu hình |
| Xem `?.` như cơ chế kiểm soát quyền | Chỉ tránh lỗi null, không kiểm tra authorization | Tách kiểm soát quyền và cache key/scope |
| Nhầm `Optional.empty()` với exception | Exception không tạo kết quả thành công cho `unless` | Xử lý lỗi/negative caching theo chính sách riêng |

Ngoài ra, `@Cacheable(sync=true)` **không hỗ trợ `unless`**: nhánh đồng bộ nhằm phối hợp việc tính giá trị theo khả năng provider và có các giới hạn cấu hình riêng. Đừng cố thêm `unless` vào operation synchronized rồi cho rằng lúc nào cũng được thực thi như nhánh thông thường.

## 10. Kiểm thử điều kiện lưu thay vì chỉ đọc annotation

Một bộ kiểm thử Spring thật nên chứng minh:

1. **Hit hợp lệ:** lời gọi đầu lấy `Optional.of(active)`, lời gọi hai không chạy method thật; giá trị trả ra vẫn là `Optional<...>`.
2. **Veto theo thuộc tính:** kết quả `Optional.of(hidden)` bị `unless` loại; method chạy ở mỗi lời gọi.
3. **Veto rỗng:** `Optional.empty()` bị `#result == null` loại; method chạy ở mỗi lời gọi.
4. **Negative caching:** bỏ `unless`, provider hỗ trợ null; lần hai trả `Optional.empty()` mà không chạy method.
5. **Chuỗi null an toàn:** kết quả có nested property null và biểu thức dùng `?.` xuyên suốt; không xuất hiện SpEL exception.
6. **Chuyển phiên bản:** test biểu thức có biến `Optional` thật nếu đang dùng cú pháp null-safe đặc trưng Spring 7; tách khỏi test `#result` đã unwrap.
7. **Invalidation:** khi một entity từng `Optional.empty()` được tạo, entry “không tìm thấy” phải bị evict hoặc hết TTL đúng chính sách.
8. **Proxy:** chắc chắn test gọi bean lấy từ `ApplicationContext` và không vô tình bypass advice bằng self-invocation.

Để kiểm tra đơn vị expression khi không cần cache provider, có thể dùng `SpelExpressionParser` và `StandardEvaluationContext`; nhưng test này chỉ kiểm tra **SpEL thuần**, không tự tạo ngữ cảnh cache hay quy tắc unwrap `#result`. Muốn xác nhận `#result` của `Optional` thực tế, phải gọi phương thức có annotation qua caching infrastructure.

Ví dụ rút gọn của bài kiểm tra SpEL riêng (snippet, cần có dependency `spring-expression`):

~~~java
var parser = new org.springframework.expression.spel.standard.SpelExpressionParser();
var context = new org.springframework.expression.spel.support.StandardEvaluationContext();
context.setVariable("result", null);
Object value = parser.parseExpression("#result?.toString()").getValue(context);
System.out.println(value == null); // true
~~~

Trong test sau, nếu thay `#result` bằng một `Optional` Java nguyên trạng, đó là kiểm thử semantics của toán tử SpEL với `Optional` ở phiên bản thư viện đang chạy, **không phải** mô phỏng `#result` do Spring Cache tự tạo.

## 11. Khi nào nên cache `Optional.empty()`?

Điều này liên quan trực tiếp đến `unless`:

- Với tra cứu một ID sai lặp lại liên tục, negative caching có thể giảm tải database và upstream service. Cần TTL đủ ngắn và cơ chế invalidation nếu bản ghi có thể được tạo sau đó.
- Với dữ liệu mới có thể xuất hiện ngay, không cache `Optional.empty()` giúp lần tiếp theo truy vấn lại, đổi lại tăng tải.
- Với dữ liệu phân quyền/tenant, một “không thấy” có thể có nghĩa **không có quyền thấy**, không hẳn là không tồn tại. Cần đưa scope phù hợp vào key và không để negative cache từ tenant/role này áp dụng sang tenant/role khác.
- Nếu provider không hỗ trợ null hoặc lưu null kém nhất quán, không nên chỉ dựa vào `Optional.empty()` mà chưa kiểm thử. Có thể dùng biểu diễn domain-specific rõ ràng cho negative result hoặc chọn bỏ qua.
- Quan sát hit/miss rate, thời gian sống và số lần truy vấn lặp, thay vì áp dụng mặc định “rỗng thì cache” hay “rỗng thì không cache” cho mọi endpoint.

**Đặc biệt:** `unless = "#result == null"` chỉ kiểm tra **giá trị nghiệp vụ** là null; không dùng điều kiện này để phân biệt mọi loại dữ liệu “không hữu ích” khác như object trạng thái `INVALID`, collection rỗng, số âm, entity đã khóa. Nếu chính sách muốn loại những loại đó, viết quy tắc rõ ràng và test từng nhánh.

## 12. Checklist thực hành

Trước khi merge một cache annotation cho method trả `Optional<T>`, hãy trả lời:

- `#result` đang là `T` hay null? Có đoạn expression nào gọi `Optional.isPresent()`, `isEmpty()`, `get()` một cách sai ngữ cảnh không?
- `condition` chỉ dựa vào argument và ngữ cảnh có sẵn trước invocation chưa? `unless` có chịu trách nhiệm đầy đủ cho chính sách sau khi có result không?
- Mọi chỗ có thể null đã dùng `?.` thích hợp chưa, kể cả chain sau mắt xích đầu tiên?
- Biểu thức có nêu rõ rỗng được **cache** hay **veto** chưa? `?.` không tự giải đáp chính sách đó.
- Provider có hỗ trợ cache null không? Nếu có, TTL và invalidation cho negative entries có hợp lý không?
- Key có đủ tham số, tenant và scope nghiệp vụ để ngăn kết quả sai/người dùng khác nhận nhầm không?
- Có test Spring context đo lần chạy target method ở các nhánh `Optional.of` hợp lệ, bị loại và `Optional.empty()` không?
- Nếu dùng SpEL safe navigation trực tiếp trên biến `Optional` (khác với cache `#result`), phiên bản Spring đã hỗ trợ semantics đó chưa?

## 13. Tài liệu tham khảo chính thức

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `condition`, `unless`, `#result`, quy tắc unwrap `Optional`, ngữ cảnh caching SpEL và các giới hạn.
- [Spring Framework — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html): `?.`, compound expression, null-safe method/property và thay đổi liên quan đến `Optional` từ Spring 7.0.
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html): cú pháp, toán tử và ngữ cảnh đánh giá.
- [Spring Framework — Cacheable Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html): contract `condition`/`unless` và các thuộc tính của annotation.

Điểm cần ghi nhớ khi đọc code: `@Cacheable` trả `Optional<Book>` nhưng trong `unless`, `#result` là **`Book` hoặc `null`**; `#result?.property` bảo vệ truy cập khi null; còn quyết định **có cache `Optional.empty()` hay không** phải được viết ra bằng chính sách `unless` rõ ràng và kiểm thử trên cache provider thật.