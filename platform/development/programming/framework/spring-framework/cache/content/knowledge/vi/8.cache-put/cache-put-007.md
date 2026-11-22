# Rủi ro kết hợp @CachePut và @Cacheable trên cùng phương thức

> **Chủ đề:** Spring Framework Cache — nhóm `@CachePut`. Trọng tâm: vì sao không nên đặt đồng thời `@Cacheable` và `@CachePut` lên một phương thức, các tình huống có thể sai, ngoại lệ điều kiện loại trừ nhau và cách thay thế bằng hai phương thức đọc/ghi rõ ràng.

## Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích chính xác sự khác biệt giữa một **cache hit** của `@Cacheable` và một lời gọi được đánh dấu `@CachePut`.
2. Nhận biết việc kết hợp hai annotation khiến ý nghĩa “có chạy thân phương thức hay không” trở nên mâu thuẫn.
3. Phân tích rủi ro bỏ qua tác vụ ghi, cache sai key, dữ liệu cũ, sai thứ tự cập nhật và lỗi transaction.
4. Hiểu ngoại lệ hiếm gặp khi hai `condition` loại trừ nhau trước khi gọi phương thức; biết vì sao không dùng `#result` để chứng minh điều kiện loại trừ.
5. Viết và chạy một ví dụ Java 17 Spring Framework 6.x với cách thiết kế đúng, kèm kiểm thử JUnit kiểm chứng luồng hit, cập nhật và đọc lại.

## 1. @Cacheable và @CachePut thực sự làm gì?

Spring Cache là một abstraction gồm `Cache`, `CacheManager` và các interceptor xử lý lời gọi method thông qua Spring proxy. Mỗi annotation có **mục tiêu khác nhau**.

### `@Cacheable` — tối ưu đường đọc

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) {
    return repository.find(id);
}
```

Đây là **đoạn minh họa trong bean có repository**, chưa phải chương trình chạy độc lập. Khi gọi method qua proxy:

- Nếu cache chưa có mục với key `id` (miss), method được chạy; kết quả có thể được đưa vào cache.
- Nếu đã có mục hợp lệ (hit), Spring có thể trả kết quả đã lưu **mà không chạy thân `find`**.
- Do đó chỉ nên dùng cacheable cho xử lý **được phép bỏ qua** khi kết quả cũ còn chấp nhận được, điển hình là read/query không có side effect.

### `@CachePut` — chạy method rồi làm mới cache

```java
@CachePut(cacheNames = "products", key = "#p0")
public Product update(String id, int newPrice) {
    return repository.updatePrice(id, newPrice);
}
```

Đây cũng là đoạn minh họa; nó giả định repository có method cập nhật thực. Với một `@CachePut` được dùng **độc lập**, cache hit không làm Spring bỏ qua nghiệp vụ cập nhật: method **vẫn được thực thi**; kết quả trả về được dùng để cập nhật cache theo cấu hình.

Ví dụ nếu giá từ 100 tăng lên 200, sau `update("P1", 200)` thì cache mục P1 nên phản ánh đối tượng mới trả về (nếu việc cập nhật thành công và chính sách cho phép). `@CachePut` không tự thay thế bước ghi cơ sở dữ liệu.

| Khía cạnh | `@Cacheable` | `@CachePut` |
| --- | --- | --- |
| Ý định chính | Tái sử dụng kết quả khi đọc | Chủ động cập nhật cache từ kết quả xử lý |
| Cache hit | Có thể bỏ qua method body | Vẫn thực thi method body khi dùng riêng |
| Cache miss | Chạy method, có thể điền cache | Chạy method, có thể điền cache |
| Phương thức phù hợp | Query/idempotent read | Command cập nhật, refresh có kiểm soát |
| Rủi ro khi dùng sai | Bỏ qua side effect không được phép bỏ | Ghi đè giá trị hoặc chạy công việc tốn kém vô ích |

**Điểm bản chất:** với `@Cacheable`, việc **không thực thi method** là một tính năng; với `@CachePut`, việc **thực thi method** để tạo dữ liệu mới là mục tiêu.

## 2. Mâu thuẫn khi kết hợp trên cùng phương thức

Mẫu dễ gây sai:

```java
@Cacheable(cacheNames = "products", key = "#p0")
@CachePut(cacheNames = "products", key = "#p0")
public Product loadAndRefresh(String id) {
    return repository.find(id);
}
```

Đây là **anti-pattern để phân tích**; không phải cách triển khai khuyến nghị.

Hai annotation tạo hai yêu cầu đối nghịch:

- “Có cache hit thì bỏ qua `loadAndRefresh`” từ `@Cacheable`.
- “Phải chạy `loadAndRefresh` để lấy kết quả và ghi cache” từ `@CachePut`.

Do Spring phải giải quyết nhiều cache operation trên cùng lời gọi, người viết không có một hợp đồng hành vi đơn giản kiểu “vừa luôn chạy method vừa luôn bỏ qua method khi hit”. Phụ thuộc điều kiện, cache key, provider, advice và đường gọi, hành vi có thể khác kỳ vọng. Không được suy diễn rằng annotation nào “chạy trước” là một cách lập trình đáng tin.

**Tài liệu Spring Framework khuyến cáo mạnh tránh đặt hai annotation này trên cùng phương thức**, trừ một số trường hợp rất đặc biệt khi điều kiện của chúng loại trừ nhau. Lời khuyên đó áp dụng cả khi mã vẫn biên dịch và ứng dụng vẫn khởi động bình thường.

## 3. Những rủi ro thường gặp

### 3.1. Lệnh ghi bị bỏ qua

Nếu method chứa lệnh `repository.save(...)`, trừ tồn kho, gửi thông báo, ghi nhận thanh toán hoặc phát sự kiện nhưng cũng có `@Cacheable`, cache hit có thể tạo đường đi bỏ qua phần nghiệp vụ cần phải chạy. Điều này đặc biệt nguy hiểm vì caller có thể nhận về dữ liệu cũ và lầm tưởng cập nhật đã thành công.

**Quy tắc:** không dùng cached result để thay cho việc thực thi tác vụ có side effect. Phương thức command phải có hành vi thực thi rõ ràng; cache chỉ là lớp bổ trợ.

### 3.2. Không tiết kiệm công việc lặp

Một method có `@CachePut` phải thực thi để đưa giá trị mới vào cache; nếu mục đích gốc là đọc nhanh, việc kết hợp có thể làm mất lợi ích giảm số truy vấn hoặc tính toán từ `@Cacheable`. Không thể đo chất lượng chỉ bằng việc có các annotation; phải đo số lần chạy thân method, số truy vấn DB và độ trễ thực.

### 3.3. Trả stale data hoặc cache bị ghi đè

Nếu nguồn thay đổi trong khi cache vẫn chứa bản cũ, một nhánh cacheable có thể trả stale data thay vì refresh như người viết mong đợi. Trong các cập nhật đồng thời, hai request có thể ghi cache theo thứ tự khác với thứ tự dữ liệu được commit vào nguồn, để lại giá trị cũ. Cần phân tích giao dịch, version, race condition và provider; hai annotation đặt cùng nhau không tự bảo đảm tính nhất quán.

### 3.4. Sai cache key giữa đọc và ghi

Ngay cả khi đã **tách hai method**, để key mặc định có thể tạo bug:

```java
@Cacheable("products")
public Product find(String id) { /* query */ }

@CachePut("products")
public Product update(String id, int price) { /* write */ }
```

Các method trên là **chữ ký minh họa**, không phải code Java hoàn chỉnh. Với `SimpleKeyGenerator` mặc định, method có một đối số như `find(id)` thường dùng chính `id` làm key. Method `update(id, price)` có hai đối số tạo key kết hợp, ví dụ `SimpleKey(id, price)`. Dù cùng tên cache, `@CachePut` có thể cập nhật một mục khác với mục mà `find` đọc. Kết quả: lần đọc tiếp theo vẫn hit dữ liệu cũ.

Giải pháp khi dữ liệu thật sự chỉ xác định bởi ID:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String id) { /* query */ }

@CachePut(cacheNames = "products", key = "#p0")
public Product update(String id, int price) { /* write */ }
```

Hai đoạn minh họa dùng **cùng key `id`**. Trong hệ thống multi-tenant, theo currency, locale hoặc cấp quyền, key cần bao gồm đủ ngữ cảnh ảnh hưởng kết quả; dùng mỗi `id` có thể dẫn đến rò rỉ hoặc trả nhầm dữ liệu.

### 3.5. Giá trị put không phải dữ liệu cần cache

`@CachePut` đưa **giá trị do method trả về** vào cache. Nếu method cập nhật thành công nhưng trả `boolean`, DTO trạng thái hoặc đối tượng chưa được làm mới, việc dùng chung cache `products` với method đọc trả `Product` sẽ khiến kiểu hoặc nội dung cache sai. Lúc đó dùng `@CacheEvict` để xóa key và nạp lại khi đọc có thể rõ ràng hơn.

### 3.6. Khác nhau giữa test và production

Unit test tạo object bằng `new ProductService()` không kích hoạt cache interceptor như bean gọi qua Spring proxy. Self-invocation (`this.find()` hoặc `this.update()`) từ cùng bean cũng bỏ qua advice cache trong proxy mode mặc định. Nhiều instance có local cache độc lập có thể cho kết quả khác nhau dù cùng annotation.

## 4. Ngoại lệ có điều kiện: hai nhánh loại trừ nhau

Theo Spring Framework, một số tình huống hiếm gặp cho phép cùng method chứa hai annotation nếu **hai `condition` loại trừ lẫn nhau**.

Minh họa có chủ đích:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p1 == 'READ'"
)
@CachePut(
    cacheNames = "products",
    key = "#p0",
    condition = "#p1 == 'REFRESH'"
)
public Product load(String id, String mode) {
    return repository.find(id);
}
```

Đây là đoạn minh họa dùng `repository` chưa định nghĩa; không phải ứng dụng chạy độc lập. Giả sử `mode` chỉ là `READ` hoặc `REFRESH`, các điều kiện không thể cùng đúng ở một lời gọi:

- `READ`: operation cacheable được chọn; method có thể bị bỏ qua khi hit.
- `REFRESH`: operation put được chọn; method được gọi để làm mới cache.
- Mode khác: các điều kiện đều false, không có cache operation tương ứng.

Dù như vậy, việc người dùng phải biết một method có hai mode làm API khó hiểu. **Tách method đọc và method refresh thường tốt hơn**, và mọi lựa chọn giữ chung cần có integration test theo phiên bản Spring thực dùng.

### Vì sao không dùng `#result` để chứng minh loại trừ?

Spring phải xét sự loại trừ của các operation **trước khi quyết định có thể bỏ qua lời gọi method**. Kết quả method `#result` chưa tồn tại ở thời điểm đó. Vì vậy không được dựa vào `#result` để phân biệt hai nhánh `@Cacheable`/`@CachePut` trong ngoại lệ này.

`unless` là một cơ chế xét **sau khi đã có kết quả** để từ chối lưu, không phải cách bảo đảm từ trước rằng hai operation sẽ không cùng áp dụng. Một số biểu thức của `@CachePut` có thể dùng `#result` trong giai đoạn cập nhật sau invocation, nhưng điều đó không giải quyết được việc xác nhận điều kiện loại trừ **trước invocation**.

Tương tự, thay hai annotation bằng `@Caching(cacheable = ..., put = ...)` không loại bỏ mâu thuẫn; `@Caching` chỉ tổ chức nhiều cache operation.

## 5. Giải pháp rõ nghĩa: tách truy vấn và lệnh ghi

Thiết kế thông thường:

```text
Client
  |
  +--> findProduct(id)            @Cacheable
  |       HIT  -> trả value cache, không chạy query
  |       MISS -> chạy query và cache kết quả
  |
  +--> updateProduct(id, price)   @CachePut
          chạy nghiệp vụ update nguồn
          lấy Product mới sau update
          ghi Product mới vào cache cùng key id
```

Đây là một kiểu triển khai **tách trách nhiệm đọc và ghi**:

- `findProduct` chỉ đọc và cho phép tối ưu bằng cache hit.
- `updateProduct` thực thi nghiệp vụ update, không bỏ qua chỉ vì đã có dữ liệu cache.
- Hai method thống nhất cache name, key và kiểu value.
- Việc kiểm thử/giám sát có thể xác minh chính xác số lần đọc nguồn và số lần cập nhật nguồn.

Nếu không có dữ liệu canonical để put sau cập nhật, hãy xem xét xóa cache:

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void updateProduct(String id, int price) {
    repository.updatePrice(id, price);
}
```

Đây là ví dụ đặt trong Spring bean có repository. Theo cấu hình mặc định, eviction thường diễn ra sau khi phương thức hoàn tất thành công; lần đọc kế tiếp miss và lấy dữ liệu mới. Nhưng nếu có transaction, **thời điểm hoàn tất method không luôn đồng nghĩa commit đã xong** — hãy kiểm tra thêm ranh giới giao dịch.

## 6. Dự án Java 17 chạy được: Spring Cache với hai phương thức riêng

Ví dụ dùng **Spring Framework 6.2.1**, Maven, `ConcurrentMapCacheManager` trong một JVM. Nó không cần Spring Boot, DB hay Redis. Dữ liệu nguồn được mô phỏng bằng `ConcurrentHashMap`, còn sản phẩm là Java record bất biến.

### 6.1. Cấu trúc

```text
cache-annotation-design/
├── pom.xml
└── src/
    ├── main/java/demo/cache/CacheDemo.java
    └── test/java/demo/cache/CacheDemoTest.java
```

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>cache-annotation-design</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.1</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.cache.CacheDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Maven tải `spring-context` và các dependency Spring liên quan qua Maven Central. `@EnableCaching` bật interceptor; `ConcurrentMapCacheManager` lưu dữ liệu trong JVM. JUnit là thư viện kiểm thử. Dự án Spring Boot thật nên quản lý phiên bản qua BOM/parent tương thích thay vì tự ép một phiên bản Spring khác.

### 6.3. `src/main/java/demo/cache/CacheDemo.java`

```java
package demo.cache;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheDemo {
    public record Product(String id, int price) {}

    public static class ProductRepository {
        private final Map<String, Product> data = new ConcurrentHashMap<>();

        public ProductRepository() {
            data.put("P1", new Product("P1", 100));
        }

        public Product find(String id) {
            return data.get(id);
        }

        public Product save(String id, int price) {
            Product product = new Product(id, price);
            data.put(id, product);
            return product;
        }
    }

    public static class ProductService {
        private final ProductRepository repository;
        private final AtomicInteger readCount = new AtomicInteger();
        private final AtomicInteger writeCount = new AtomicInteger();

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public Product find(String id) {
            int n = readCount.incrementAndGet();
            System.out.println("LOAD " + id + " #" + n);
            return repository.find(id);
        }

        @CachePut(cacheNames = "products", key = "#p0")
        public Product update(String id, int price) {
            int n = writeCount.incrementAndGet();
            System.out.println("UPDATE " + id + " #" + n);
            return repository.save(id, price);
        }

        public int reads() {
            return readCount.get();
        }

        public int writes() {
            return writeCount.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductRepository repository() {
            return new ProductRepository();
        }

        @Bean
        public ProductService productService(ProductRepository repository) {
            return new ProductService(repository);
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            ProductService service = ctx.getBean(ProductService.class);
            System.out.println("read1=" + service.find("P1").price());
            System.out.println("read2=" + service.find("P1").price());
            System.out.println("updated=" + service.update("P1", 200).price());
            System.out.println("read3=" + service.find("P1").price());
            System.out.println("reads=" + service.reads());
            System.out.println("writes=" + service.writes());
        }
    }
}
```

Điểm cốt lõi:
- `Product` là record bất biến; không lo client sửa trực tiếp trường trong object cache.
- `ProductRepository` là nguồn dữ liệu mô phỏng, ban đầu P1 có giá 100.
- `find` chỉ có `@Cacheable`. Bộ đếm `readCount` tăng **bên trong thân method** khi thực sự phải tải dữ liệu.
- `update` chỉ có `@CachePut`. Nó thực hiện nghiệp vụ cập nhật nguồn rồi trả về `Product` mới để lưu vào cache.
- Cả hai cùng dùng cache name `products` và `key = "#p0"` nên cùng định danh P1.
- Lời gọi qua `ctx.getBean(ProductService.class)` đi qua Spring proxy. Tạo `new ProductService(...)` ngoài Spring sẽ bỏ qua caching annotation.

### 6.4. Chạy và dự đoán stdout

Cần JDK 17+, Maven 3.9+ và mạng để tải dependency lần đầu. Tại thư mục `cache-annotation-design`:

```bash
java -version
mvn -q compile exec:java
```

Những dòng **do chính chương trình in ra**, không tính các log Maven/Spring bên ngoài:

```text
LOAD P1 #1
read1=100
read2=100
UPDATE P1 #1
updated=200
read3=200
reads=1
writes=1
```

- `read1`: miss, thực thi `find`, lấy 100 và đưa vào cache.
- `read2`: hit, không xuất hiện một dòng `LOAD` mới.
- `update`: thực thi đúng một lần, thay dữ liệu nguồn thành 200 và put giá trị đó vào cache key P1.
- `read3`: hit với kết quả 200, không thực thi lại `find`.
- `reads=1` và `writes=1` xác nhận hai đường thực thi rõ nghĩa.

Thí nghiệm này là ví dụ một JVM đơn luồng, **không chứng minh** consistency giữa nhiều instance, giao dịch DB hoặc race condition.

## 7. Kiểm thử JUnit để tránh regressions

Tạo `src/test/java/demo/cache/CacheDemoTest.java`:

```java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CacheDemoTest {
    @Test
    void readHitDoesNotSkipUpdateAndPutRefreshesTheSameKey() {
        try (var ctx = new AnnotationConfigApplicationContext(
                CacheDemo.Config.class)) {

            var service = ctx.getBean(CacheDemo.ProductService.class);

            assertEquals(100, service.find("P1").price());
            assertEquals(100, service.find("P1").price());
            assertEquals(1, service.reads());

            assertEquals(200, service.update("P1", 200).price());
            assertEquals(1, service.writes());

            assertEquals(200, service.find("P1").price());
            assertEquals(1, service.reads());
        }
    }
}
```

Chạy:

```bash
mvn -q test
```

Khi mọi assertion đúng, JUnit test thành công và Maven trả exit code 0. Số lần chạy method trong bài test chứng minh:
1. Hit trên method đọc không thực thi lại thân `find`.
2. Method cập nhật vẫn được thực thi.
3. Cache key của hai method trùng nhau, nên đọc lại thấy 200 mà không phải query nguồn thêm lần nữa.

Mỗi test tạo ApplicationContext riêng để không phụ thuộc state của chương trình `main` trước đó. Trong dự án lớn có test song song, cần kiểm soát cache state và concurrency riêng.

## 8. Giao dịch, concurrency và nhiều instance: những giới hạn phải tự xử lý

### 8.1. @Transactional không tự khiến DB và cache nguyên tử

Với database thật, `@Transactional` có thể commit **sau** khi phần thân method hoàn thành; thứ tự advice transaction/cache phụ thuộc cấu hình. Nếu put cache trước khi transaction commit rồi DB rollback, cache có thể giữ giá trị không tồn tại trong DB. Nếu xóa cache trước commit, một request khác có thể miss và nạp bản cũ.

Cần lựa chọn chiến lược rõ ràng: làm mới hoặc invalidation sau commit khi phù hợp, sử dụng transaction-aware cache khi provider hỗ trợ, sự kiện `@TransactionalEventListener(phase = AFTER_COMMIT)`, hoặc cơ chế đồng bộ khác theo yêu cầu hệ thống. Đặt hai annotation trên một method không khắc phục vấn đề giao dịch.

### 8.2. Các cập nhật đồng thời

Hai request ghi cùng key có thể thay đổi DB và put cache theo thứ tự khác nhau; cache cuối cùng có thể stale. Khi cần tính nhất quán cao, cân nhắc optimistic locking/version, kiểm soát thứ tự sự kiện, eviction hoặc cập nhật sau commit. `@CachePut` không tự giải quyết tất cả race condition.

### 8.3. Local cache trên nhiều instance

`ConcurrentMapCacheManager` và Caffeine thường là cache local theo JVM. `@CachePut` ở instance A không cập nhật cache local ở instance B. Nếu cần chia sẻ, dùng provider phân tán như Redis và thiết kế invalidation/TTL phù hợp. Redis dùng chung cũng không biến mọi thao tác thành giao dịch DB + cache nguyên tử.

### 8.4. Tùy chọn @Cacheable(sync = true) không sửa lỗi thiết kế

`@Cacheable(sync = true)` giúp phối hợp tính toán khi nhiều miss cùng key nếu provider hỗ trợ, nhưng nó có hạn chế riêng (như không ghép các cache operation khác và không dùng `unless`). Nó không phải cách dung hòa `@Cacheable` với `@CachePut` trên cùng phương thức.

## 9. Các lỗi hay gặp khi refactor

| Dấu hiệu | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Sau update, find vẫn trả giá cũ | Hai method dùng key khác nhau, provider khác nhau hoặc put trước commit | Đối chiếu cache name/key, thời điểm update và state nguồn |
| `@Cacheable` không giảm số lần query | Không bật `@EnableCaching`, gọi bằng `this.find(...)`, key thay đổi hoặc cache bị xóa | Gọi qua Spring proxy, log số lần method chạy |
| `@CachePut` không cập nhật cache | Self-invocation, thiếu manager, condition false, key sai, provider từ chối value | Kiểm tra bean, advice, key và giá trị trả về |
| Có cả cache hit lẫn side effect bất thường | Cùng method mang hai annotation mục đích trái nhau | Tách read/write, thêm test từng đường |
| Value kiểu sai khi đọc từ cache | Method put trả response trạng thái khác kiểu Product | Put đối tượng canonical hoặc evict |
| Khách hàng khác nhau nhận chung giá trị | Key bỏ sót tenant/role/currency/locale | Thiết kế key đủ ngữ cảnh |
| Test pass nhưng production lỗi | Test không qua Spring proxy, hoặc khác provider và transaction | Integration test trong cấu hình tương ứng |

`@Caching` chỉ gom annotation; nó không sửa bản chất mâu thuẫn nếu vẫn khai báo cả `@Cacheable` và `@CachePut` cho cùng đường gọi.

## 10. Checklist khi gặp method có cả @CachePut và @Cacheable

1. Xác định method là **read** hay **command/write**. Nếu phải thực hiện side effect, tuyệt đối không cho cache hit thay thế nghiệp vụ ghi.
2. Kiểm tra xem có thực sự cần hai operation trên cùng method không. Nếu không, tách `find` và `update`.
3. Xác minh cache name, key và **kiểu value** thống nhất giữa đọc và ghi.
4. Nếu dùng `@CachePut`, kết quả trả về có phản ánh dữ liệu canonical đã persist không?
5. Nếu dùng `@CacheEvict`, sau khi xóa key lần đọc tiếp theo có thể nạp bản mới chứ?
6. Kiểm tra proxy, `@EnableCaching` và `CacheManager` đang dùng.
7. Kiểm tra thời điểm commit, lỗi rollback và yêu cầu về độ tươi.
8. Viết kiểm thử hit/miss/update, ghi nhận số lần thực thi thân method và dữ liệu trả về.
9. Trong hệ thống nhiều instance/tenant, kiểm tra cập nhật chéo node và phân biệt đúng key.
10. Chỉ giữ ngoại lệ hai condition loại trừ nếu có lý do rõ ràng, điều kiện không phụ thuộc `#result`, và được integration test toàn diện.

## 11. Bài tập tự kiểm tra

**Bài 1.** Vì sao `@Cacheable` không nên được dùng cho method thanh toán?  
**Đáp án:** Cache hit có thể bỏ qua method body trong khi thanh toán là tác vụ có side effect bắt buộc phải thực hiện theo nghiệp vụ.

**Bài 2.** `find(id)` và `update(id, newPrice)` cùng cache name nhưng không cấu hình key. Vì sao cache sau update vẫn có thể cũ?  
**Đáp án:** Default key generator tạo key khác nhau cho chữ ký một tham số và hai tham số; cần thống nhất key, ví dụ `#p0` nếu ID đủ xác định dữ liệu.

**Bài 3.** Method cập nhật trả `boolean` thành công, trong khi cache products cần `Product`. Nên dùng `@CachePut` không?  
**Đáp án:** Không nên put boolean vào cache Product; trả Product chuẩn hoặc dùng `@CacheEvict`.

**Bài 4.** Hai `condition` loại trừ nhau dựa trên `#result` có an toàn để kết hợp cả hai annotation không?  
**Đáp án:** Không. Việc xác nhận điều kiện loại trừ phải có thể thực hiện trước invocation; `#result` chỉ có sau khi chạy method.

**Bài 5.** Vì sao hai method đã tách và key giống nhau vẫn có thể chưa bảo đảm dữ liệu tươi ở tất cả instance?  
**Đáp án:** Local cache mỗi JVM có trạng thái riêng; ngoài ra còn có giao dịch, race, TTL và invalidation.

## Tài liệu chính thức

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [Spring Framework — AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)

**Ghi nhớ:** `@Cacheable` có thể bỏ qua method khi cache hit; `@CachePut` phục vụ việc chạy method và ghi kết quả mới vào cache. Kết hợp cả hai trên cùng method tạo kỳ vọng mâu thuẫn và được tài liệu Spring khuyến cáo tránh. Tách phương thức đọc/ghi, thống nhất key và kiểm thử kết quả mới là cách triển khai rõ ràng, dễ bảo trì.