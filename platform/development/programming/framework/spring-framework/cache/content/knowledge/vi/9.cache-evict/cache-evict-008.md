# @CacheEvict: Xóa các bản sao dữ liệu liên quan ở nhiều khóa

## Mục tiêu bài học

Khi một bản ghi thay đổi, ứng dụng thường không chỉ cache dữ liệu đó tại **một key**. Cùng một sản phẩm có thể xuất hiện trong cache chi tiết, tóm tắt, danh sách theo danh mục, kết quả tìm kiếm hoặc thống kê. Nếu chỉ xóa một entry, các bản sao còn lại có thể tiếp tục trả **dữ liệu cũ (stale data)**.

Bài học này giải thích cách sử dụng **`@CacheEvict`** trong Spring Framework để vô hiệu hóa những bản sao liên quan tại **nhiều key**, trong **một hoặc nhiều cache name**, và cách lựa chọn giải pháp khi tập hợp key không biết trước.

Sau bài học, bạn có thể:

- Phân biệt **một key**, **nhiều key** và **toàn bộ cache region**.
- Dùng `@Caching(evict = {...})` để khai báo nhiều thao tác `@CacheEvict` với các biểu thức key khác nhau.
- Bảo đảm key khi evict **trùng chính xác** với key mà `@Cacheable` đã dùng.
- Nhận diện các phụ thuộc như *detail → summary → category list* và lựa chọn phạm vi xóa phù hợp.
- Xử lý tình huống thay đổi danh mục, nhiều key động, transaction rollback, cạnh tranh đồng thời và hệ thống nhiều instance.
- Chạy ví dụ Java 17 + Spring Cache để kiểm chứng nhiều entry được xóa, trong khi entry không liên quan vẫn giữ nguyên.

> **Nguyên tắc:** Muốn tránh dữ liệu stale, phải tìm đủ những cache entry **phụ thuộc vào dữ liệu vừa thay đổi**. Một lần `@CacheEvict` theo key chỉ xóa key được xác định trong cache name được chỉ định; Spring không tự truy tìm những bản sao logic đang nằm dưới các key khác.

## 1. Vấn đề: Một sản phẩm, nhiều bản sao trong cache

Giả sử hệ thống bán hàng có sản phẩm ID = 42, tên cũ là “Book A”, danh mục “books”. Các phương thức đọc khác nhau lưu những kết quả sau:

| Cache name | Key | Giá trị đang cache | Phụ thuộc vào sản phẩm 42? |
| --- | --- | --- | --- |
| `productViews` | `detail:42` | Thông tin chi tiết chứa “Book A” | Có |
| `productViews` | `summary:42` | Tóm tắt chứa “Book A” | Có |
| `categoryLists` | `category:books` | Danh sách chứa “Book A” | Có |
| `categoryLists` | `category:games` | Danh sách sản phẩm trò chơi | Không |
| `productViews` | `detail:77` | Chi tiết sản phẩm 77 | Không |

Khi đổi tên sản phẩm 42 thành “Book B”:

- Chỉ xóa `productViews[detail:42]` là **chưa đủ**. Lần gọi xem tóm tắt vẫn có thể thấy “Book A”.
- Nếu chỉ xóa hai key chi tiết và tóm tắt, danh sách `category:books` vẫn có thể chứa “Book A”.
- Xóa cả `category:games` hoặc mọi sản phẩm khác sẽ gây cache miss và tăng tải không cần thiết.

Phạm vi xóa đúng trong ví dụ là **ba entry bị ảnh hưởng**: `detail:42`, `summary:42`, `category:books`.

### Mô hình phụ thuộc dữ liệu

~~~text
Bản ghi Product(id=42, category=books)
          |
          +----> productViews[detail:42]
          |
          +----> productViews[summary:42]
          |
          +----> categoryLists[category:books]

Bản ghi Product(id=77, category=games)
          |
          +----> categoryLists[category:games]
                  (không liên quan đến đổi tên Product 42)
~~~

Một thao tác cập nhật cần biết **đồ thị phụ thuộc** này; annotation cache không tự suy luận nó từ database hoặc các câu truy vấn.

## 2. @CacheEvict cơ bản xóa những gì?

Một ví dụ đơn giản:

~~~java
@CacheEvict(cacheNames = "productViews", key = "'detail:' + #p0")
public void renameProduct(long productId, String newName) {
    repository.rename(productId, newName);
}
~~~

Đây là đoạn mã minh họa, yêu cầu `repository` tồn tại trong service thật.

Với `renameProduct(42, "Book B")`, khi phương thức hoàn tất bình thường, Spring có thể yêu cầu xóa entry tương ứng với:

~~~text
cache name = productViews
key        = detail:42
~~~

**Nó không tự xóa** `productViews[summary:42]` hay `categoryLists[category:books]`.

### Tên vùng cache và key là hai thành phần riêng

`productViews[detail:42]` và `categoryLists[detail:42]` là hai entry khác nhau vì cache name khác. Ngược lại, trong cùng `productViews`, `detail:42` và `summary:42` là hai key khác nhau.

Vì thế, muốn làm sạch nhiều bản sao, phải xác định đúng **tập hợp cặp (cache name, key)**. Không đủ nếu chỉ biết ID của đối tượng nguồn.

## 3. Xóa nhiều key với @Caching(evict = {...})

Spring cung cấp `@Caching` để gộp nhiều cache operation trên cùng một phương thức. Đây là cách khai báo thuận tiện khi **các key cần xóa đã biết và số lượng nhỏ**.

~~~java
@Caching(evict = {
    @CacheEvict(
        cacheNames = "productViews",
        key = "'detail:' + #p0"
    ),
    @CacheEvict(
        cacheNames = "productViews",
        key = "'summary:' + #p0"
    ),
    @CacheEvict(
        cacheNames = "categoryLists",
        key = "'category:' + #p2"
    )
})
public void renameProduct(
        long productId,
        String newName,
        String category) {
    repository.rename(productId, newName, category);
}
~~~

Đây là mã minh họa cho service có repository và ràng buộc **category truyền vào phản ánh danh mục hiện tại của sản phẩm**. Nếu category sai hoặc đã đổi, không được giả định phép xóa `categoryLists` đã đủ.

Ba biểu thức SpEL được đánh giá trong ngữ cảnh **tham số của `renameProduct`**, không phải tham số của các phương thức đọc:

- `#p0` là tham số thứ nhất `productId`: tạo `detail:42` và `summary:42`.
- `#p2` là tham số thứ ba `category`: tạo `category:books`.
- `#p1` là `newName`, không được đưa vào key vì các cache đang dùng định danh sản phẩm/danh mục, không dùng tên làm key.

Cách dùng `#p0`, `#p1`, `#p2` không phụ thuộc việc biên dịch Java có giữ tên tham số hay không. Trong dự án thực tế, có thể dùng `#productId` và `#category` khi tên tham số khả dụng.

**Quan trọng:** `@Caching` chỉ **nhóm nhiều thao tác**, không tạo giao dịch nguyên tử giữa các key hay giữa các cache. Nếu một thao tác evict gặp lỗi, Spring Cache abstraction không bảo đảm toàn bộ các thao tác khác được rollback cùng nhau.

### Một annotation có thể chỉ định nhiều cache name khi key giống nhau

Nếu hai vùng cache dùng **cùng một key**, có thể viết:

~~~java
@CacheEvict(
    cacheNames = {"productById", "productSnapshot"},
    key = "#p0"
)
public void update(long productId) {
    repository.update(productId);
}
~~~

Nhưng với `detail:42`, `summary:42` và `category:books`, key khác nhau. Hãy dùng nhiều `@CacheEvict` qua `@Caching` (hoặc chọn cách programmatic phù hợp); **không** trông đợi một `key` tự mở rộng thành nhiều khóa.

## 4. Ví dụ Java 17 chạy được: xóa ba bản sao, giữ một bản sao không liên quan

Ví dụ sau là chương trình console có thể chạy với Java 17+, Maven và **Spring Framework 6.2.10**. Nó dùng `ConcurrentMapCacheManager` để quan sát entry trong bộ nhớ. Ba cache entry liên quan đến sản phẩm ID 42 sẽ bị xóa sau khi đổi tên, nhưng danh sách danh mục “games” vẫn được giữ.

### 4.1. Cấu trúc dự án

~~~text
multi-key-eviction/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MultiKeyEvictionDemo.java
~~~

### 4.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>multi-key-eviction</artifactId>
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

### 4.3. src/main/java/demo/MultiKeyEvictionDemo.java

~~~java
package demo;

import java.util.Comparator;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.Caching;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class MultiKeyEvictionDemo {

    // Immutable value object; used as fake database row.
    public record Product(long id, String category, String name) {}

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                "productViews", "categoryLists");
        }

        @Bean
        public ProductRepository productRepository() {
            return new ProductRepository();
        }

        @Bean
        public ProductService productService(ProductRepository repository) {
            return new ProductService(repository);
        }
    }

    public static class ProductRepository {
        private final Map<Long, Product> products =
                new ConcurrentHashMap<>();

        public ProductRepository() {
            products.put(42L, new Product(42L, "books", "Book A"));
            products.put(77L, new Product(77L, "games", "Game A"));
        }

        public Product get(long id) {
            return Objects.requireNonNull(
                products.get(id), "Unknown product");
        }

        public String namesByCategory(String category) {
            return products.values().stream()
                .filter(p -> p.category().equals(category))
                .sorted(Comparator.comparingLong(Product::id))
                .map(Product::name)
                .collect(Collectors.joining(", "));
        }

        public void rename(
                long id, String newName, String expectedCategory) {
            Product old = get(id);
            if (!old.category().equals(expectedCategory)) {
                throw new IllegalArgumentException(
                    "Category does not match");
            }
            products.put(id, new Product(
                id, old.category(), newName));
        }
    }

    public static class ProductService {
        private final ProductRepository repository;
        private final AtomicInteger detailReads = new AtomicInteger();
        private final AtomicInteger summaryReads = new AtomicInteger();
        private final AtomicInteger listReads = new AtomicInteger();

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @Cacheable(
            cacheNames = "productViews",
            key = "'detail:' + #p0"
        )
        public String detail(long id) {
            detailReads.incrementAndGet();
            Product p = repository.get(id);
            return "Detail " + p.id() + ": " + p.name();
        }

        @Cacheable(
            cacheNames = "productViews",
            key = "'summary:' + #p0"
        )
        public String summary(long id) {
            summaryReads.incrementAndGet();
            Product p = repository.get(id);
            return "Summary " + p.id() + ": " + p.name();
        }

        @Cacheable(
            cacheNames = "categoryLists",
            key = "'category:' + #p0"
        )
        public String categoryList(String category) {
            listReads.incrementAndGet();
            return "Category " + category + ": " +
                    repository.namesByCategory(category);
        }

        @Caching(evict = {
            @CacheEvict(
                cacheNames = "productViews",
                key = "'detail:' + #p0"
            ),
            @CacheEvict(
                cacheNames = "productViews",
                key = "'summary:' + #p0"
            ),
            @CacheEvict(
                cacheNames = "categoryLists",
                key = "'category:' + #p2"
            )
        })
        public void rename(
                long id, String newName, String category) {
            repository.rename(id, newName, category);
        }

        public String counters() {
            return "detail=" + detailReads.get()
                + ", summary=" + summaryReads.get()
                + ", list=" + listReads.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            ProductService service =
                context.getBean(ProductService.class);
            CacheManager cacheManager =
                context.getBean(CacheManager.class);

            Cache views = Objects.requireNonNull(
                cacheManager.getCache("productViews"));
            Cache lists = Objects.requireNonNull(
                cacheManager.getCache("categoryLists"));

            System.out.println(service.detail(42L));
            System.out.println(service.summary(42L));
            System.out.println(service.categoryList("books"));
            System.out.println(service.categoryList("games"));
            System.out.println("Counts before hit: " +
                service.counters());

            service.detail(42L);
            service.summary(42L);
            service.categoryList("books");
            service.categoryList("games");
            System.out.println("Counts after hit: " +
                service.counters());

            service.rename(42L, "Book B", "books");

            System.out.println("Detail evicted: " +
                (views.get("detail:42") == null));
            System.out.println("Summary evicted: " +
                (views.get("summary:42") == null));
            System.out.println("Books list evicted: " +
                (lists.get("category:books") == null));
            System.out.println("Games list still cached: " +
                (lists.get("category:games") != null));

            System.out.println(service.detail(42L));
            System.out.println(service.summary(42L));
            System.out.println(service.categoryList("books"));
            System.out.println(service.categoryList("games"));
            System.out.println("Counts after reread: " +
                service.counters());
        }
    }
}
~~~

### 4.4. Chạy chương trình

Tại thư mục chứa `pom.xml`, sử dụng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MultiKeyEvictionDemo
~~~

Những dòng chương trình in ra (không tính log Maven):

~~~text
Detail 42: Book A
Summary 42: Book A
Category books: Book A
Category games: Game A
Counts before hit: detail=1, summary=1, list=2
Counts after hit: detail=1, summary=1, list=2
Detail evicted: true
Summary evicted: true
Books list evicted: true
Games list still cached: true
Detail 42: Book B
Summary 42: Book B
Category books: Book B
Category games: Game A
Counts after reread: detail=2, summary=2, list=3
~~~

### 4.5. Phân tích kết quả

1. Bốn lời gọi đầu tạo lần lượt cache `detail:42`, `summary:42`, `category:books`, `category:games`. Bộ đếm là `detail=1, summary=1, list=2`.
2. Gọi lại cả bốn phương thức với cùng key tạo **cache hit**. Bộ đếm không tăng, chứng tỏ Spring đã bỏ qua thân phương thức `@Cacheable`.
3. Phương thức `rename` thực sự thay đổi nguồn từ “Book A” sang “Book B”, rồi nhóm `@Caching(evict = {...})` xóa ba entry phụ thuộc.
4. Kiểm tra trực tiếp qua `CacheManager` cho thấy ba entry đã bị xóa. `category:games` vẫn tồn tại vì danh mục games không liên quan.
5. Khi đọc lại, ba entry đã xóa gây miss và được nạp bằng dữ liệu mới “Book B”. Danh sách games vẫn hit; tổng bộ đếm `list` chỉ tăng từ 2 lên 3.

**Vì sao dùng `@EnableCaching`?** Cấu hình này kích hoạt cache advice của Spring. Các phương thức `detail`, `summary`, `categoryList` và `rename` đều được gọi qua `ProductService` lấy từ `ApplicationContext`, nên proxy có cơ hội xử lý annotation.

**Giới hạn ví dụ:** `ConcurrentMapCacheManager` chỉ là cache RAM trong tiến trình. Đây là ví dụ quan sát hành vi; không có database transaction, Redis, TTL, khóa phân tán hoặc cơ chế điều phối nhiều instance. Số dòng output được suy ra từ đúng logic của chương trình và giả định môi trường dependency hoạt động bình thường.

## 5. Trường hợp nào dùng một @CacheEvict, @Caching hoặc allEntries?

| Nhu cầu | Phương án | Phạm vi |
| --- | --- | --- |
| Đã biết một key trong một cache | `@CacheEvict(cacheNames = "...", key = "...")` | Một entry |
| Cùng key phải xóa trong nhiều cache | Một `@CacheEvict` với nhiều `cacheNames` | Một key trên từng cache đã liệt kê |
| Nhiều key khác nhau, số lượng hữu hạn và biết từ tham số/kết quả | `@Caching(evict = { ... })` | Nhiều entry xác định |
| Tất cả entry trong một vùng cache trở nên không hợp lệ | `@CacheEvict(allEntries = true)` | Toàn vùng cache |
| Tập key động, số lượng thay đổi từng lần | `CacheManager`/`Cache.evict(key)` với danh sách key xác định hoặc thiết kế lại mô hình cache | Theo tập key runtime |
| Phụ thuộc của nhiều query khó xác định | Cache riêng theo loại truy vấn, versioning, TTL, hoặc xóa cả vùng phù hợp | Do chính sách ứng dụng quyết định |

### 5.1. allEntries = true không phải wildcard theo tiền tố

Ví dụ:

~~~java
@CacheEvict(cacheNames = "categoryLists", allEntries = true)
public void bulkUpdateProducts() {
    repository.bulkUpdate();
}
~~~

**Mã minh họa** này xóa tất cả entry trong `categoryLists` sau khi `bulkUpdateProducts` thành công, chứ không chỉ `category:books`. Cách này có ích khi một thay đổi ảnh hưởng quá nhiều danh sách và không thể xác định chính xác các key. Nhưng nó gây nhiều cache miss và tăng tải nạp lại.

Spring không mặc định hỗ trợ biểu thức `key = "'category:*'"` để xóa mọi key bắt đầu bằng `category:`. Đó chỉ là **một key literal** khi được biểu thức SpEL tạo ra, không phải pattern matching.

Khi dùng `allEntries = true`, Spring bỏ qua key vì đang xóa toàn vùng; đừng viết kết hợp `key` rồi kỳ vọng nó thu hẹp phạm vi. Nên cân nhắc tách region theo phạm vi phụ thuộc để việc `allEntries` không ảnh hưởng dữ liệu không liên quan.

### 5.2. So sánh độ chính xác và chi phí

- **Xóa chính xác nhiều key:** ít ảnh hưởng hit ratio, nhưng đòi hỏi mô hình phụ thuộc đáng tin cậy và danh sách key đầy đủ.
- **Xóa toàn vùng:** đơn giản hơn khi ảnh hưởng rộng, nhưng có thể gây cache stampede hoặc tăng tải đột biến.
- **TTL ngắn:** làm giới hạn thời gian stale, nhưng không thay thế invalidation khi nghiệp vụ cần thấy dữ liệu mới ngay.
- **Version hóa key:** hữu ích cho những nhóm kết quả có thể đổi phiên bản đồng loạt, nhưng phải quản lý key phiên bản, tránh tăng bộ nhớ không kiểm soát và xử lý entry cũ hết hạn.

## 6. Nếu chuyển sản phẩm từ danh mục cũ sang danh mục mới?

Đổi tên khác với **đổi danh mục**. Khi sản phẩm 42 chuyển từ “books” sang “games”, cần làm mới:

- Chi tiết và tóm tắt sản phẩm 42.
- Danh sách **books cũ** (vì sản phẩm không còn ở đó).
- Danh sách **games mới** (vì sản phẩm vừa được thêm vào).

Nếu chỉ xóa `category:games`, danh sách books có thể vẫn chứa sản phẩm 42. Nếu chỉ xóa `category:books`, danh sách games có thể không có sản phẩm 42.

Khi category cũ chỉ biết sau khi đọc/cập nhật dữ liệu, có thể trả về một kết quả mô tả thay đổi và dùng `#result` trong `@CacheEvict` **sau invocation**. Đoạn sau là **mã minh họa**, giả định repository và phương thức cập nhật đã được định nghĩa; không phải phần của chương trình độc lập ở mục 4:

~~~java
public record MoveResult(
    long productId, String oldCategory, String newCategory) {}

@Caching(evict = {
    @CacheEvict(
        cacheNames = "categoryLists",
        key = "'category:' + #result.oldCategory()"
    ),
    @CacheEvict(
        cacheNames = "categoryLists",
        key = "'category:' + #result.newCategory()"
    ),
    @CacheEvict(
        cacheNames = "productViews",
        key = "'detail:' + #p0"
    ),
    @CacheEvict(
        cacheNames = "productViews",
        key = "'summary:' + #p0"
    )
})
public MoveResult moveProduct(long productId, String newCategory) {
    return repository.moveAndDescribe(productId, newCategory);
}
~~~

Đối với `@CacheEvict` mặc định `beforeInvocation = false`, Spring cho phép `#result` khi tính key sau khi phương thức đã hoàn tất thành công. Trong đoạn code trên, `#result.oldCategory()` và `#result.newCategory()` là các phương thức accessor của Java record.

**Không dùng `#result` khi `beforeInvocation = true`**, vì tại thời điểm trước khi chạy method chưa có kết quả. Đồng thời phải có quy ước rõ ràng với trường hợp `MoveResult` null, thao tác thất bại hoặc category cũ và mới trùng nhau.

Nếu một cập nhật tác động đến nhiều danh mục, bộ lọc hoặc danh sách phân trang, kết quả trả về có thể không liệt kê đủ mọi key cache. Khi đó cần thay đổi mô hình invalidation: index key phụ thuộc, xóa toàn vùng hợp lý, tách vùng cache hoặc quản lý version.

## 7. Nếu số lượng key liên quan không biết trước?

`@Caching(evict = {...})` rất tốt với **một danh sách nhỏ, có thể khai báo tĩnh**. Nhưng giả sử sản phẩm 42 xuất hiện trong 1.000 tổ hợp `search:q=...`, `page:...`, `sort:...` và `filter:...`. Không thể viết một annotation `@CacheEvict` cho từng tổ hợp trong tương lai.

### 7.1. Xác định tập key trước rồi xóa bằng API

Spring `CacheManager` cung cấp truy cập đến `Cache`; cache cung cấp `evict(key)`. Khi ứng dụng **có một tập key đáng tin cậy**, có thể xóa từng entry.

~~~java
import java.util.Collection;
import java.util.Objects;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

public class DependentKeyInvalidator {
    private final CacheManager cacheManager;

    public DependentKeyInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    public void invalidateSearchKeys(Collection<String> affectedKeys) {
        Cache search = Objects.requireNonNull(
            cacheManager.getCache("searchResults"));

        for (String key : affectedKeys) {
            search.evict(key);
        }
    }
}
~~~

Đây là **đoạn mã tái sử dụng trong project Spring**, không phải một chương trình `main` độc lập; cần đăng ký class thành bean và cung cấp `CacheManager`.

Để triển khai đúng, phải biết cách phát hiện `affectedKeys`. Ví dụ, một index quản lý “productId 42 đang ảnh hưởng những search key nào” phải được cập nhật mỗi khi tạo/xóa entry. Nếu index bị thiếu hoặc stale, các bản sao liên quan có thể bị bỏ sót.

**Không coi `CacheManager` là API liệt kê tất cả key trong mọi provider.** Spring Cache abstraction không cung cấp một API chuẩn để quét key theo prefix. Cách duyệt key của Caffeine/Redis hoặc quét Redis `SCAN` là đặc thù provider và cần xem xét chi phí, tính an toàn, cluster và production operations.

### 7.2. Tách cache region để giới hạn phạm vi xóa

Nếu `productDetail` có thể evict chính xác theo ID nhưng mọi danh sách tìm kiếm phụ thuộc quá rộng, có thể đặt detail và search results ở **hai cache names riêng**. Khi một product thay đổi:

- Xóa `productDetail[id]` theo key.
- Xóa `searchResults` bằng `allEntries = true` nếu nghiệp vụ thật sự cho phép và mọi entry tìm kiếm có nguy cơ stale.

Đó là một quyết định đánh đổi: đơn giản hóa tính đúng đổi lấy chi phí làm ấm cache lại. Không nên xóa một vùng rộng vì tiện mà không quan sát hit ratio, tốc độ nạp, traffic và nhu cầu dữ liệu tươi.

### 7.3. Versioning hoặc generation token

Một phương án khác là gắn **generation/version** vào key của một nhóm cache, ví dụ `search:v18:filter=books`. Khi tập dữ liệu thay đổi, tăng generation; các lượt đọc tạo key thuộc thế hệ mới, không dùng kết quả cũ.

Cần có một nguồn version nhất quán giữa các instance, cơ chế hết hạn/xóa entry phiên bản cũ, và kiểm thử race khi một writer tăng version đồng thời với reader. Đây là **thiết kế hệ thống**, không phải chức năng do `@CacheEvict` tự cung cấp.

## 8. Xóa sau khi method thành công hay trước khi gọi?

Mặc định `@CacheEvict` sử dụng `beforeInvocation = false`. Điều này có nghĩa thao tác xóa được kích hoạt **sau khi phương thức đích hoàn tất thành công**. Nếu phương thức ném ngoại lệ ra ngoài, lần gọi đó không kích hoạt eviction hậu kỳ.

~~~java
@CacheEvict(
    cacheNames = "productViews",
    key = "'detail:' + #p0"
)
public void updateProduct(long id) {
    repository.update(id);
}
~~~

**Mã minh họa** trên chỉ là một thao tác xóa hậu kỳ; các bản sao khác vẫn cần được xử lý riêng.

Khi dùng:

~~~java
@CacheEvict(
    cacheNames = "productViews",
    key = "'detail:' + #p0",
    beforeInvocation = true
)
public void refreshProduct(long id) {
    repository.refreshFromRemote(id);
}
~~~

Spring thực hiện eviction **trước khi gọi** method. Nếu method thất bại, entry đã bị xóa không được tự động phục hồi. Đây là lựa chọn phù hợp cho một số thao tác refresh hoặc invalidation phải xảy ra bất kể kết quả, nhưng không phải mặc định an toàn cho mọi cập nhật.

Với `@Caching` gồm nhiều eviction, có thể cấu hình `beforeInvocation` cho từng annotation, nhưng cần tránh chia các thao tác liên quan thành hai mốc thời gian không chủ đích.

### Ngoại lệ bị bắt và kết quả nghiệp vụ thất bại

Nếu method **bắt exception và trả bình thường** (ví dụ `UpdateResult(success=false)`), với cấu hình mặc định Spring vẫn có thể xem invocation là thành công để chạy eviction. Có thể cân nhắc `condition` phù hợp dựa trên kết quả sau invocation hoặc để nghiệp vụ ném ngoại lệ đúng lúc; cần thiết kế theo hợp đồng của method.

## 9. Transaction, đồng thời và nhiều instance

### 9.1. @Transactional không mặc định biến nhiều evict thành một giao dịch nguyên tử

Giả sử update database và nhiều `@CacheEvict` chạy trong một thao tác có `@Transactional`. Hai cơ chế Spring Cache advice và transaction advice có thể bao quanh phương thức theo thứ tự khác nhau; **đừng mặc định mọi cache entry chỉ bị xóa sau khi database commit**.

Nếu eviction xảy ra trước khi transaction commit mà reader khác nạp lại cache từ trạng thái cũ, có thể tái tạo stale entry. Nếu update rollback, các entry có thể đã bị xóa dù dữ liệu thực tế không thay đổi.

Với nghiệp vụ cần nhất quán hơn, cân nhắc cache được trang bị **transaction-aware behavior**, cơ chế `afterCommit` hoặc publication của sự kiện sau commit; kiểm thử provider cụ thể và thời điểm thực tế. Dù vậy, nhiều eviction giữa những cache độc lập không tự trở thành một transaction phân tán.

### 9.2. Race condition sau eviction

Một tình huống khó:

~~~text
Reader A: miss -> bắt đầu đọc bản ghi cũ
Writer B: cập nhật nguồn -> evict các key
Reader A: hoàn tất truy vấn cũ -> put bản cũ vào cache
~~~

Nếu điều phối không phù hợp, dữ liệu stale có thể **được ghi trở lại cache sau eviction**. Các cách giảm rủi ro gồm versioning, khóa/đồng bộ phù hợp, kiểm tra version tại thời điểm cache put, serialization nhất quán và thiết kế read/write path. `@CacheEvict` đơn lẻ không giải quyết mọi race condition.

### 9.3. Nhiều instance

Với cache **in-memory cục bộ**, instance A xóa entry của mình nhưng instance B vẫn có bản sao cũ. Nếu cần invalidation toàn hệ thống, cân nhắc:

- Dùng cache dùng chung như Redis (với cấu hình key, region và serializer nhất quán).
- Dùng cơ chế sự kiện/broadcast cho mỗi instance xóa cache local tương ứng.
- Kết hợp versioning, TTL và metrics khi hệ thống có eventual consistency.

Nếu dùng queue/event để invalidation, phải tính đến event trùng, mất thứ tự, retry, idempotency và tính toàn vẹn của cặp `(cacheName, key)`.

## 10. Những sai lầm phổ biến

1. **Chỉ xóa chi tiết, quên summary/list.** Dữ liệu cũ vẫn xuất hiện ở màn hình khác. Thiết lập ma trận phụ thuộc giữa nguồn và cache keys.
2. **Khác quy tắc sinh key giữa đọc và evict.** Đọc dùng `detail:42` nhưng evict key `42`; thao tác xóa đúng cú pháp nhưng sai entry. So sánh trực tiếp biểu thức `@Cacheable` và `@CacheEvict`.
3. **Dùng một key để đại diện nhiều bản sao.** Một `@CacheEvict(key = "'detail:' + #p0")` không xóa `summary:42`. Dùng `@Caching` khi số key hữu hạn.
4. **Tưởng `allEntries` là xóa theo prefix.** `allEntries=true` xóa cả region, không phải những key trùng mẫu.
5. **Thay danh mục mà chỉ xóa danh mục mới.** Danh mục cũ vẫn có bản ghi đã chuyển đi. Cần cả old/new category.
6. **Phân trang và filter tạo vô số key nhưng không có kế hoạch invalidation.** Cân nhắc thiết kế region, index phụ thuộc hoặc versioning.
7. **Gọi method qua `this.update(...)` trong cùng bean.** Với proxy mode mặc định, self-invocation không đi qua cache advice; `@Caching` không được áp dụng.
8. **Cho rằng nhiều eviction là atomic.** Lỗi provider có thể tạo trạng thái chỉ một phần key được xóa. Cần quan sát, retry/khắc phục nếu nghiệp vụ yêu cầu.
9. **Cho rằng một giao dịch DB commit và cache evict luôn đồng bộ.** Kiểm thử advice ordering, rollback và after-commit.
10. **Xóa mọi vùng để khỏi tính phụ thuộc.** Cách này đơn giản nhưng có thể gây cache stampede, giảm hit ratio và gây đột biến tải database.
11. **Quên version/tenant/locale trong key.** Có thể xóa nhầm hoặc bỏ sót bản sao của cùng tài nguyên theo nhiều biến thể.
12. **Không quan sát đa node.** Evict cache local trên một instance không tự làm sạch các instance khác.
13. **Dùng `#result` với `beforeInvocation=true`.** Khi chưa chạy method, không có kết quả để tham chiếu.
14. **Tin rằng chính sách TTL thay thế hoàn toàn eviction.** TTL chỉ giới hạn thời gian stale; với nghiệp vụ cần tính đúng ngay sau update, phải có chiến lược invalidation tương ứng.

## 11. Checklist trước khi triển khai

- [ ] Xác định từng loại bản sao kết quả phụ thuộc vào bản ghi nguồn (detail, summary, list, aggregate, search).
- [ ] Liệt kê đầy đủ các cặp `(cacheName, key)` cần xóa cho từng loại thay đổi.
- [ ] Xác nhận key trong `@CacheEvict` khớp key mà `@Cacheable` hoặc `@CachePut` tạo ra.
- [ ] Nếu thay đổi nhóm/danh mục, xóa cả danh mục cũ và mới.
- [ ] Dùng `@Caching(evict = {...})` cho các key hữu hạn, xác định được.
- [ ] Dùng `allEntries` chỉ khi đánh đổi về chi phí và phạm vi đã được chấp nhận.
- [ ] Với key động, có index phụ thuộc đáng tin cậy, cơ chế version hoặc chiến lược khác có thể kiểm chứng.
- [ ] Xác định chính sách xóa trước/sau invocation, kể cả trường hợp method ném ngoại lệ.
- [ ] Kiểm thử rollback transaction, cache provider failure, concurrent read/write và nhiều instance.
- [ ] Đảm bảo method được gọi qua Spring proxy có `@EnableCaching`, không self-invocation ngoài ý muốn.
- [ ] Có metrics về hit/miss, eviction, tỷ lệ stale được phát hiện và chi phí nạp lại.

## 12. Bài tập tự kiểm tra

**Câu 1.** Sản phẩm 42 có hai entry `detail:42` và `summary:42` trong cùng cache. Một `@CacheEvict(key="'detail:' + #p0")` có xóa cả hai không?  
**Đáp án:** Không. Nó chỉ nhắm `detail:42`. Cần thêm eviction cho `summary:42`.

**Câu 2.** Ba key cần xóa đã biết từ tham số phương thức, nằm trên hai cache names. Annotation nào giúp nhóm các thao tác?  
**Đáp án:** `@Caching(evict = { @CacheEvict(...), ... })`.

**Câu 3.** `allEntries=true` cùng `cacheNames="categoryLists"` có ý nghĩa gì?  
**Đáp án:** Xóa toàn bộ entry trong vùng `categoryLists`, không chỉ một category hay prefix.

**Câu 4.** Sản phẩm chuyển từ “books” sang “games”. Tại sao cần xóa hai danh sách?  
**Đáp án:** Danh sách books cũ phải bỏ sản phẩm, còn games mới phải thêm sản phẩm.

**Câu 5.** Phương thức update ném exception với `beforeInvocation=false`. Evict hậu kỳ có chạy không?  
**Đáp án:** Không theo cơ chế mặc định khi ngoại lệ thoát ra ngoài.

**Câu 6.** Vì sao xóa ba cache keys chưa đảm bảo ba cache luôn nhất quán ở mọi thời điểm?  
**Đáp án:** Eviction không atomic giữa nhiều key/provider; còn có concurrency, transaction boundary và nhiều node.

**Câu 7.** Có thể yêu cầu Spring xóa mọi key với tiền tố `category:` bằng `key="'category:*'"` không?  
**Đáp án:** Không. Cache abstraction không cung cấp wildcard key eviction phổ quát.

**Câu 8.** Khi số lượng search keys thay đổi liên tục, cách nào tốt hơn việc viết một nghìn annotation?  
**Đáp án:** Tùy hệ thống: theo dõi tập key bị ảnh hưởng rồi evict programmatically; hoặc thiết kế lại các vùng cache, dùng versioning/TTL hoặc clear region phù hợp.

## Tài liệu tham khảo

- Spring Framework Reference — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Spring Framework Javadoc — CacheEvict: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
- Spring Framework Javadoc — Caching: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Caching.html
- Spring Framework Reference — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
