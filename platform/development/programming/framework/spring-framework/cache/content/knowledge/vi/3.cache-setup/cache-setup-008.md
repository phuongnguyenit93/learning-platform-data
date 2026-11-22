# Xây dựng ví dụ tối thiểu chứng minh cache đã hoạt động trong Spring Framework

## Kết quả cần đạt

Bài này hướng dẫn xây dựng **một ứng dụng Java 17 chạy độc lập với Spring Framework Cache** để kiểm chứng `@Cacheable` thực sự ngăn phương thức nghiệp vụ chạy lại khi cùng một khóa đã có trong cache.

Sau khi hoàn thành, bạn sẽ:
- Tạo được một dự án Maven nhỏ, không cần cơ sở dữ liệu, Docker, Redis hoặc Spring Boot.
- Đăng ký `CacheManager`, bật `@EnableCaching`, khai báo `@Cacheable` và gọi bean qua Spring container.
- Dùng **bộ đếm số lần phương thức thật thực thi** để phân biệt cache miss với cache hit.
- Chạy lại lệnh và đối chiếu stdout theo từng bước; biết điều gì là bằng chứng và điều gì chưa đủ để kết luận cache hoạt động.
- Nhận ra những lỗi thiết lập phổ biến như quên `@EnableCaching` hoặc tự gọi phương thức trong cùng một object.

> **Đề bài trực tiếp:** xây dựng ví dụ **tối thiểu chứng minh cache đã hoạt động**. Vì vậy, ta dùng cache bộ nhớ sẵn có của Spring (`ConcurrentMapCacheManager`), một phương thức được cache, và phép đo kết quả xác định. TTL, Redis, phân tán và tối ưu hiệu năng là những chủ đề tiếp theo, không phải điều kiện cần của bài thực hành này.

## 1. Thế nào là “cache đã hoạt động”?

Không thể kết luận cache chạy chỉ vì đã thêm annotation `@Cacheable` hoặc vì hai lần gọi cho ra cùng một chuỗi. Một phương thức không dùng cache cũng có thể trả cùng kết quả.

Ta cần quan sát **mã nghiệp vụ thật có được bỏ qua hay không**. Giả sử phương thức tìm sách nhận `bookId`; mỗi lần thực sự chạy, nó tăng biến `realLoads` và in một dòng bắt đầu bằng `LOAD`.

Kịch bản kiểm chứng:

| Lần gọi | Tham số | Kỳ vọng | Số lần chạy phương thức thật sau lượt gọi |
| --- | --- | --- | ---: |
| 1 | `find("A")` | Cache miss: tải dữ liệu và ghi entry cho khóa A | 1 |
| 2 | `find("A")` | Cache hit: trả kết quả đã lưu, **không chạy lại** thân phương thức | 1 |
| 3 | `find("B")` | Cache miss: khóa B khác khóa A | 2 |
| 4 | `find("A")` | Cache hit lần nữa cho khóa A | 2 |

Vậy dấu hiệu then chốt là **bốn lời gọi từ `main` nhưng chỉ có hai lần thực thi phương thức thật**. Ta còn thêm phép kiểm tra tự động: nếu số lần thực thi không phải 2 hoặc kết quả dành cho A khác nhau, chương trình ném lỗi.

### Các thành phần tham gia

~~~text
main()
  |
  | gọi bean do Spring quản lý
  v
Spring proxy (CacheInterceptor)
  |
  | @Cacheable(cacheNames = "books")
  | tạo key từ tham số bookId
  v
CacheManager -> cache "books" (ConcurrentMapCache)
  |
  +-- key có sẵn (HIT)  -> trả lại giá trị đã cache
  |
  +-- key chưa có (MISS)-> chạy phương thức find(bookId)
                           -> tăng realLoads, in LOAD
                           -> lưu kết quả, trả về
~~~

`@EnableCaching` bật xử lý annotation cache; `CacheManager` cung cấp kho `books`; `@Cacheable` khai báo phương thức và tên kho cần dùng. Trong cấu hình mặc định theo proxy, chỉ lời gọi đi **qua Spring proxy** mới được đánh chặn. <https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html>

## 2. Yêu cầu môi trường và cấu trúc dự án

- **JDK 17+** (ví dụ JDK 17 hoặc 21).
- **Apache Maven** hoạt động trong terminal.
- Có mạng khi chạy Maven lần đầu để lấy dependency chưa có trong kho local.

Kiểm tra:

~~~bash
java -version
mvn -version
~~~

Tạo thư mục và hai tệp như sau:

~~~text
spring-cache-proof/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CacheProof.java
~~~

Tên class `CacheProof` phải trùng với tên tệp `CacheProof.java`; `package demo;` tương ứng thư mục `demo/`.

Ví dụ sử dụng **Spring Framework 6.2.16** (chạy trên Java 17+) với duy nhất dependency Spring `spring-context`. Thành phần cache bằng `ConcurrentMapCacheManager` nằm trong Spring Framework, nên bài này không cần thư viện cache bên thứ ba.

## 3. Tệp `pom.xml`

Tạo tệp `pom.xml` ngay trong thư mục `spring-cache-proof/`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-cache-proof</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
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

`spring-context` mang theo các dependency Spring cần thiết, bao gồm hạ tầng AOP mà cache annotation sử dụng. `maven.compiler.release=17` yêu cầu biên dịch cho Java 17. Plugin `exec-maven-plugin` giúp chạy `main` bằng một lệnh Maven, không phải tự ghép classpath.

## 4. Mã Java đầy đủ: `CacheProof.java`

Tạo tệp `src/main/java/demo/CacheProof.java` với **toàn bộ** nội dung sau:

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheProof {

    @Configuration
    @EnableCaching
    public static class CacheConfig {

        @Bean
        public CacheManager cacheManager() {
            // Tạo cache tên "books" ngay trong bộ nhớ JVM.
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public BookCatalog bookCatalog() {
            // Để Spring quản lý và tạo proxy cho bean này.
            return new BookCatalog();
        }
    }

    public static class BookCatalog {
        private int realLoads = 0;

        @Cacheable(cacheNames = "books")
        public String find(String bookId) {
            realLoads++;
            System.out.println("LOAD bookId=" + bookId
                    + " count=" + realLoads);
            return "book-" + bookId + "-version-" + realLoads;
        }

        public int realLoads() {
            return realLoads;
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {

            // Quan trọng: lấy bean qua Spring container, không new BookCatalog().
            BookCatalog catalog = context.getBean(BookCatalog.class);

            String first = catalog.find("A");
            System.out.println("first=" + first);

            String second = catalog.find("A");
            System.out.println("second=" + second);

            String other = catalog.find("B");
            System.out.println("other=" + other);

            String again = catalog.find("A");
            System.out.println("again=" + again);

            System.out.println("realLoads=" + catalog.realLoads());

            if (!first.equals(second)
                    || !first.equals(again)
                    || catalog.realLoads() != 2) {
                throw new IllegalStateException("Cache verification FAILED");
            }

            System.out.println("CACHE_OK");
        }
    }
}
~~~

Mã này là **chương trình đầy đủ** có thể biên dịch và chạy, không phụ thuộc database thật. Biến `realLoads` đại diện cho số lần truy vấn nguồn dữ liệu: đủ để chứng minh cache bỏ qua công việc ở những lần hit. Trong hệ thống thật, phần `return` của `find` có thể được thay bằng truy vấn DB hoặc một lời gọi HTTP có thể kiểm chứng.

### Giải nghĩa bốn điểm cấu hình

1. **`@Configuration`** đánh dấu `CacheConfig` là lớp khai báo các Spring bean.
2. **`@EnableCaching`** kích hoạt hạ tầng đánh chặn method có cache annotation. Chỉ gắn `@Cacheable` mà thiếu kích hoạt này không tạo hiệu ứng cache theo annotation.
3. **`@Bean CacheManager`** trả về `ConcurrentMapCacheManager("books")`: manager cung cấp kho cache mang tên `books`, lưu dữ liệu trong bộ nhớ tiến trình hiện tại.
4. **`@Cacheable(cacheNames = "books")`** bảo Spring: với mỗi lời gọi `find`, tìm kết quả theo key trong `books`; nếu hit thì trả trực tiếp, nếu miss mới chạy thân phương thức rồi lưu kết quả.

Với phương thức chỉ có **một tham số không null** `String bookId`, key mặc định là chính chuỗi `bookId`. Vì vậy `"A"` và `"B"` là hai entry khác nhau.

`BookCatalog` là lớp `public`, không `final`; `find` cũng `public`, không `final`. Mô hình này tương thích với proxy theo lớp khi bean không khai báo interface. **Không gọi `new BookCatalog()` từ `main`**: nếu tạo object thủ công, lời gọi sẽ không đi qua proxy của Spring.

## 5. Chạy và đối chiếu kết quả chính xác

Mở terminal tại thư mục chứa `pom.xml`, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheProof
~~~

Phần **stdout do chương trình ghi ra** phải gồm đúng tám dòng sau (không tính thông báo riêng từ Java/Maven nếu môi trường in thêm log):

~~~text
LOAD bookId=A count=1
first=book-A-version-1
second=book-A-version-1
LOAD bookId=B count=2
other=book-B-version-2
again=book-A-version-1
realLoads=2
CACHE_OK
~~~

Diễn giải từng lần gọi:

| Lời gọi | Spring làm gì? | Bằng chứng trực tiếp |
| --- | --- | --- |
| `find("A")` lần 1 | Miss; chạy thân `find`, cache kết quả `book-A-version-1` | Xuất hiện `LOAD bookId=A count=1` |
| `find("A")` lần 2 | Hit; trả giá trị đã lưu | `second=book-A-version-1`; **không có dòng LOAD thứ hai cho A** |
| `find("B")` | Miss vì key B chưa tồn tại | Xuất hiện `LOAD bookId=B count=2` |
| `find("A")` lần 3 | Hit của A; vẫn là giá trị từ lần đầu | `again=book-A-version-1`; **không có dòng LOAD thứ ba cho A** |

Hai chứng cứ độc lập bổ trợ nhau:

- **Dấu vết thực thi:** chỉ có hai dòng `LOAD` dù `find` được gọi bốn lần.
- **Bộ đếm và điều kiện kiểm tra:** `realLoads=2`, kết thúc với `CACHE_OK`. Nếu kiểm tra thất bại, chương trình ném `IllegalStateException` thay vì in `CACHE_OK`.

`CACHE_OK` có nghĩa là **cache đã hoạt động trong một ApplicationContext, với các lời gọi tuần tự và hai key của ví dụ**. Nó không tự chứng minh hiệu quả dưới tải cao, TTL, đồng bộ giữa nhiều máy hay tính nhất quán với database.

### Tại sao cần bộ đếm?

Nếu mã nghiệp vụ luôn trả `"book-A"`, hai lượt gọi cho cùng một kết quả ngay cả khi không có cache. Trong ví dụ này, `realLoads` chỉ tăng khi **thân method thật được chạy**. Sự khác biệt giữa bốn lần gọi và hai lần tăng là bằng chứng quan sát được, không chỉ là suy luận dựa trên sự tồn tại của annotation.

Để bằng chứng càng rõ ràng, bạn có thể ghi lại cả ba thông tin: input key, mỗi dòng `LOAD`, và số lần chạy method thật. Khi thay nguồn giả bằng database, một bộ đếm truy vấn hoặc log SQL có thể đóng vai trò tương tự.

## 6. Kiểm tra đối chứng: tắt caching để thấy phép thử phát hiện lỗi

Mục tiêu của đối chứng là trả lời: **Nếu cache không hoạt động, phép thử trên có phát hiện không?**

Trong lớp `CacheConfig`, tạm **xóa hoặc comment `@EnableCaching`**, sau đó chạy lại cùng lệnh. Lúc này `@Cacheable` không được kích hoạt qua hạ tầng annotation; các lần gọi `find` đều chạy thân phương thức. Bạn sẽ thấy bốn dòng `LOAD`, `realLoads=4` và lỗi:

~~~text
java.lang.IllegalStateException: Cache verification FAILED
~~~

Bốn lời gọi lần lượt làm `realLoads` tăng 1, 2, 3, 4. Vì phép kiểm tra `realLoads() != 2` đúng, chương trình ném ngoại lệ, nên **không in `CACHE_OK`**. Đối chứng này giúp phát hiện tình trạng annotation không hoạt động.

Khôi phục `@EnableCaching` sau thí nghiệm để quay lại chương trình ban đầu. Chỉ cần khởi động lại process để có một ApplicationContext và kho cache mới, do đó không cần thao tác xóa dữ liệu thủ công cho bài này.

> **Lưu ý:** `@Cacheable` là khai báo ý định, còn `@EnableCaching` và proxy là cơ chế thực thi. Một bean `CacheManager` tồn tại trong context chưa đủ để kết luận annotation caching đã bật.

## 7. Xác minh cache còn chứa entry (tùy chọn)

Bộ đếm ở mục 5 đã chứng minh hành vi cache. Nếu muốn nhìn trực tiếp entry, bạn có thể thêm đoạn sau **bên trong khối `try` của `main` sau các lời gọi `find`**:

~~~java
CacheManager manager = context.getBean(CacheManager.class);
org.springframework.cache.Cache books = manager.getCache("books");

if (books == null) {
    throw new IllegalStateException("Missing cache: books");
}

System.out.println("cachedA="
        + books.get("A", String.class));
~~~

Với dữ liệu đã tạo, dòng bổ sung là:

~~~text
cachedA=book-A-version-1
~~~

Đoạn trích này là phần mở rộng, **không nằm trong stdout chuẩn tám dòng ở mục 5**. Nó dùng `CacheManager` để truy cập `books` và lấy đúng key `"A"`. Việc có entry chứng minh kết quả đã lưu; việc phương thức thật được bỏ qua vẫn nên xác nhận bằng `realLoads`.

`getCache("books")` có thể trả `null` nếu manager không biết tên kho; vì vậy đoạn kiểm tra xử lý trường hợp đó rõ ràng.

## 8. Vì sao ví dụ này chạy được mà không cần Spring Boot hoặc Redis?

Spring Framework cung cấp **Cache Abstraction** (`Cache`, `CacheManager`, `@Cacheable`, `@EnableCaching`) và implementation cơ bản `ConcurrentMapCacheManager`. Ta tự đăng ký hai bean `CacheManager` và `BookCatalog` trong `CacheConfig`, rồi tạo `AnnotationConfigApplicationContext`.

Đây là đủ để kiểm chứng cache trong một JVM. **Spring Boot không bắt buộc**. Nếu dùng Spring Boot, starter, auto-configuration và các property `spring.cache.*` có thể giảm mã cấu hình, nhưng đó là lộ trình thiết lập khác. Để bài kiểm chứng tối thiểu dễ phân tích, ta khai báo rõ mọi thành phần quan trọng.

Giới hạn cố ý của `ConcurrentMapCacheManager` trong ví dụ:

- Lưu entry trong RAM của **một JVM**; khởi động lại process thì dữ liệu cache mất.
- Không tự có TTL/hết hạn theo thời gian hay giới hạn dung lượng; đừng diễn giải việc dữ liệu cũ vẫn tồn tại như một lỗi.
- Không tự đồng bộ entry giữa nhiều instance ứng dụng.
- Phù hợp để hiểu cơ chế hoặc kiểm tra cơ bản. Với yêu cầu TTL, chính sách loại bỏ, observability và chia sẻ giữa instance, cân nhắc provider thích hợp như Caffeine/Redis và cấu hình riêng.

`@Cacheable(cacheNames = "books")` chỉ chọn nơi lưu logic và cách dùng kết quả. **Tên cache không đặt TTL, giới hạn số entry hay chiến lược distributed cache.**

## 9. Những lỗi dễ khiến thí nghiệm cho kết quả sai

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý đúng |
| --- | --- | --- |
| Mỗi lần gọi A lại in `LOAD` | Thiếu `@EnableCaching` hoặc phương thức không được proxy đánh chặn | Kiểm tra annotation tại lớp `@Configuration`; luôn gọi bean lấy từ Spring context |
| `new BookCatalog().find("A")` không cache | Object được tạo thủ công, không đi qua Spring proxy | Dùng `context.getBean(BookCatalog.class)` |
| Từ một method cùng class gọi `this.find("A")`, cache không hit | **Self-invocation** bỏ qua proxy trong chế độ mặc định | Di chuyển lời gọi sang bean khác hoặc thiết kế lại ranh giới service |
| `@Cacheable("books")` nhưng Spring không tìm được cache | Tên kho trên annotation không khớp cấu hình cache manager | Đối chiếu `books` trong `ConcurrentMapCacheManager("books")` |
| Hai lượt thử cho cùng input vẫn chạy lại sau mỗi lần restart | Cache chỉ tồn tại trong process hiện tại | Thực hiện các lời gọi liên tiếp trong **cùng** một ApplicationContext |
| Dùng hai key khác nhau và kỳ vọng kết quả được chia sẻ | Key mặc định dựa trên tham số | Dùng cùng chuỗi `"A"` khi thử hit; `"B"` chỉ để minh họa miss |
| Chỉ nhìn hai chuỗi kết quả bằng nhau rồi kết luận hit | Hàm gốc có thể trả kết quả ổn định | Dùng bộ đếm, log tại thân phương thức hoặc số truy vấn thật |
| Dán annotation lên private method hoặc method không proxy được | Giới hạn của cơ chế proxy (visibility/final/self-invocation) | Dùng public method, lớp không final, gọi qua bean proxy |
| Kỳ vọng một entry tự hết hạn sau vài giây | Ví dụ không cấu hình TTL | Muốn test TTL phải đổi sang provider hỗ trợ TTL và đặt policy riêng |

Cũng tránh dùng `Thread.sleep` hay thời gian chạy ngẫu nhiên làm chứng cứ duy nhất. Một bộ đếm xác định cho phép tái lập kết quả nhanh và đáng tin cậy hơn. Khi đã cần đo hiệu năng, hãy thực hiện nhiều lượt với warm-up, tải ổn định và metrics phù hợp; bài tối thiểu này tập trung kiểm chứng **ngữ nghĩa cache hit/miss**.

## 10. Bài thực hành tự kiểm tra

### Bài 1 — Đổi key để tạo miss mới

Trong `main`, thử thêm một lời gọi `catalog.find("C")` **trước dòng in `realLoads`**. Dự đoán số lần chạy method thật sẽ tăng từ 2 lên 3. Đồng thời sửa điều kiện kiểm chứng tương ứng nếu muốn chương trình kết thúc `CACHE_OK`. Nguyên nhân: C chưa có entry trong `books`.

### Bài 2 — Gọi lại B

Thêm `catalog.find("B")` sau khi đã gọi B một lần trong cùng context. Vì entry B đã tồn tại, bộ đếm **không tăng**. Như vậy cache lưu các kết quả theo từng key, không phải chỉ nhớ giá trị của lần gọi cuối cùng.

### Bài 3 — So sánh chạy qua Spring và chạy trực tiếp

Giữ code chuẩn để có đối chứng. Sau đó trong một thí nghiệm riêng, thay bean lấy từ `context.getBean` bằng `new BookCatalog()`. Mọi lời gọi sẽ chạy method thật; bộ đếm không còn bằng 2. Điều này minh họa vai trò của proxy Spring.

### Bài 4 — Tự trả lời

1. Vì sao không thể kết luận cache hoạt động chỉ từ việc có `@Cacheable`?
2. Trong code trên, thành phần nào cung cấp cache `books` và thành phần nào kích hoạt xử lý annotation?
3. Vì sao gọi `find("A")` rồi `find("B")` không được xem là cache hit?
4. Nếu bỏ `@EnableCaching`, kết quả kiểm tra cuối chương trình là gì?
5. Vì sao test này không chứng minh một hệ thống nhiều instance có shared cache?

**Đáp án cốt lõi:** (1) Cần bằng chứng bỏ qua method thật; (2) `ConcurrentMapCacheManager` và `@EnableCaching`; (3) hai key khác nhau; (4) `realLoads=4`, kiểm tra thất bại; (5) dữ liệu lưu trong RAM từng JVM.

## 11. Checklist hoàn thành

- [ ] Chạy được `java -version` và `mvn -version`.
- [ ] Tạo đúng `pom.xml` và `src/main/java/demo/CacheProof.java`.
- [ ] Chương trình có `@Configuration`, `@EnableCaching`, bean `CacheManager` và bean `BookCatalog`.
- [ ] Phương thức `find` có `@Cacheable(cacheNames = "books")`; `main` gọi bean qua `context.getBean`.
- [ ] Khi chạy cùng context: bốn lời gọi `find` tạo **hai** dòng `LOAD`.
- [ ] Stdout có `realLoads=2` và `CACHE_OK`.
- [ ] Hiểu vì sao tắt `@EnableCaching` hoặc bỏ proxy thì phép kiểm tra thất bại.

Khi đạt các điều kiện trên, bạn đã có một **bằng chứng chạy được, quan sát được và có đối chứng** cho việc Spring Cache Abstraction đã hoạt động trong cấu hình tối thiểu.

### Tài liệu chính thức

- [Spring Framework — Declarative annotation-based caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Configuring cache storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — Cache abstraction overview](https://docs.spring.io/spring-framework/reference/integration/cache.html)
