# Phân biệt @CachePut với @Cacheable trong Spring Cache

## Mục tiêu bài học

Hai annotation `@Cacheable` và `@CachePut` đều có thể ghi kết quả của một phương thức vào cache, nhưng chúng **khác nhau ở việc có thực thi phương thức hay không**. Nắm đúng khác biệt này giúp bạn chọn annotation phù hợp cho luồng đọc và luồng cập nhật dữ liệu, tránh cache cũ, mất side effect hoặc ghi nhầm giá trị.

Sau bài này, bạn sẽ:

- Giải thích chính xác hành vi của `@Cacheable` khi cache hit và cache miss.
- Giải thích vì sao `@CachePut` **luôn thực thi phương thức** và cập nhật cache bằng kết quả sau thực thi.
- Chọn đúng annotation cho phương thức đọc, cập nhật và xóa dữ liệu.
- Bảo đảm `cacheNames` và `key` nhất quán giữa thao tác đọc và cập nhật.
- Hiểu ảnh hưởng của `condition`, `unless`, ngoại lệ, `null`, transaction, Spring proxy và các lời gọi bất đồng bộ.
- Chạy ví dụ Java 17 với Spring Cache và đối chiếu bộ đếm số lần thực thi phương thức.

> **Quy tắc trọng tâm:** `@Cacheable` là công cụ **tái sử dụng kết quả để tránh chạy lại phương thức khi có cache hit**. `@CachePut` là công cụ **luôn chạy phương thức rồi ghi kết quả mới vào cache**, kể cả khi key tương ứng đã có dữ liệu.

## 1. Cùng là cache annotation, nhưng hai mục tiêu khác nhau

Giả sử `findProduct(id)` truy vấn database để trả sản phẩm. Nếu 100 yêu cầu liên tiếp đều hỏi cùng ID và dữ liệu chưa thay đổi, chạy 100 truy vấn có thể lãng phí. Đây là trường hợp có thể dùng `@Cacheable`: lần đầu đọc nguồn, các lần sau lấy kết quả lưu sẵn.

Trong khi đó `renameProduct(id, newName)` có nhiệm vụ **thực sự sửa tên sản phẩm**. Dù trước đó đã có cache entry theo ID, thao tác đổi tên vẫn phải thực thi. Nếu phương thức cập nhật trả về **đầy đủ giá trị mới** đúng với cache mà các lượt đọc đang dùng, `@CachePut` có thể dùng kết quả ấy để cập nhật entry.

Ví dụ minh họa, giả định `ProductRepository` và `Product` đã được định nghĩa:

~~~java
// Đọc có thể lấy kết quả đã lưu, bỏ qua truy vấn nguồn khi hit.
@Cacheable(cacheNames = "products", key = "#p0")
public Product findProduct(long id) {
    return repository.findById(id);
}

// Ghi phải chạy; kết quả trả về được đưa vào cùng cache/key.
@CachePut(cacheNames = "products", key = "#p0")
public Product renameProduct(long id, String newName) {
    repository.rename(id, newName);
    return repository.findById(id);
}
~~~

Đây là **đoạn minh họa trong một Spring-managed service**, chưa phải một chương trình Java độc lập. `@CachePut` không thực hiện thao tác ghi database thay bạn: code bên trong phương thức vẫn phải gọi repository.

## 2. Bảng so sánh hành vi

| Tiêu chí | `@Cacheable` | `@CachePut` |
| --- | --- | --- |
| Mục đích chính | Tăng tốc đọc nhờ tái sử dụng kết quả | Làm mới/thêm kết quả trong cache sau khi chạy phương thức |
| Cache hit, cùng key | Thường **không gọi phương thức đích**; trả giá trị cache | **Vẫn gọi phương thức đích**; ghi đè entry bằng kết quả mới nếu điều kiện cho phép |
| Cache miss | Gọi phương thức, cân nhắc lưu kết quả | Vẫn gọi phương thức và cân nhắc lưu kết quả |
| Có dựa vào cache hit để bỏ thực thi không? | Có | Không |
| Có dùng cho thao tác ghi có side effect không? | Không phù hợp khi mỗi lần gọi phải thực thi | Có thể phù hợp nếu phương thức cần luôn chạy và trả giá trị đúng cho cache |
| Kết quả từ phương thức ném ngoại lệ ra ngoài | Không có giá trị thành công mới để ghi | Không có giá trị thành công mới để ghi |
| `condition` / `unless` | Có thể điều khiển việc áp dụng và lưu cache | Có thể điều khiển việc ghi cache, nhưng không khiến phương thức bị bỏ qua |
| Đòi hỏi một cache key đúng | Có | Có; nếu làm mới entry của `@Cacheable`, phải dùng đúng cache name và key |
| Khi không nên dùng | Khi thân phương thức có side effect bắt buộc mỗi lần gọi | Khi chỉ muốn trả lại dữ liệu có sẵn mà không chạy phương thức |

Đừng hiểu `@CachePut` là một dạng “`@Cacheable` mạnh hơn”. Cả hai giải quyết các nhu cầu khác nhau.

## 3. Luồng xử lý của @Cacheable

Giả sử `getProduct(42)` được đánh dấu `@Cacheable(cacheNames = "products", key = "#p0")`.

~~~text
Client
  |
  v
Spring caching proxy
  |
  +--> tạo key từ id = 42
  |
  +--> kiểm tra products[42]
         |
         +--> HIT --> trả về giá trị đã lưu
         |            (không chạy getProduct)
         |
         +--> MISS --> chạy getProduct(42)
                      |
                      +--> phương thức trả về bình thường
                      |
                      +--> xét unless/điều kiện liên quan
                      |
                      +--> nếu được phép: put products[42] = result
                      |
                      +--> trả result về client
~~~

**Điểm cần nhớ:** trên cache hit, phần code bên trong `getProduct` có thể hoàn toàn không chạy. Điều đó phù hợp với một phép đọc không có side effect, nhưng nguy hiểm nếu đặt annotation trên một thao tác bắt buộc ghi dữ liệu hoặc thực hiện sự kiện nghiệp vụ mỗi lần gọi.

Ví dụ không phù hợp:

~~~java
@Cacheable(cacheNames = "payments", key = "#p0")
public Receipt chargeCard(String idempotencyKey, Payment payment) {
    return paymentGateway.charge(payment);
}
~~~

Đây là **phản ví dụ**, không phải khuyến nghị sử dụng. Quản lý tính idempotent và chống thu tiền trùng cần thiết kế nghiệp vụ/transaction riêng; không thể coi `@Cacheable` là cơ chế đảm bảo chính xác một lần thanh toán.

## 4. Luồng xử lý của @CachePut

Giả sử `renameProduct(42, "Tên mới")` được đánh dấu `@CachePut(cacheNames = "products", key = "#p0")`.

~~~text
Client
  |
  v
Spring caching proxy
  |
  +--> luôn gọi renameProduct(42, "Tên mới")
           |
           +--> thực hiện logic cập nhật thực tế
           |
           +--> trả về đối tượng Product mới
           |
           +--> xét condition/unless theo cấu hình
           |
           +--> nếu được phép: put products[42] = Product mới
           |
           +--> trả Product mới về client
~~~

Không có nhánh “nếu key 42 đã có thì bỏ qua đổi tên” như `@Cacheable`. Khi phương thức trả về thành công, Spring cân nhắc đặt kết quả vào vùng cache theo key đã cấu hình.

**Giới hạn quan trọng:** `@CachePut` lưu **giá trị phương thức trả về**, không tự nạp lại dữ liệu theo một phương thức `@Cacheable` khác. Nếu `renameProduct` trả `boolean`, `void`, mã trạng thái hoặc DTO chỉ chứa một phần dữ liệu, đưa trực tiếp kết quả đó vào cache dành cho `Product` có thể làm sai kiểu hoặc sai nội dung của entry. Khi không có kết quả trả về thích hợp để cập nhật chính xác cache, hãy cân nhắc **`@CacheEvict`** và để lần đọc sau nạp lại dữ liệu đầy đủ.

## 5. Ví dụ Java 17 chạy được: so sánh hit, miss và update

Ứng dụng console sau dùng **Spring Framework 6.2.10**, Java 17+, Maven, `@EnableCaching` và `ConcurrentMapCacheManager`. Một repository in-memory giả lập nguồn dữ liệu. Hai biến đếm cho thấy:

- `@Cacheable` chỉ chạy thân phương thức khi cache miss.
- `@CachePut` chạy thân phương thức mỗi lần gọi, kể cả khi key đã có entry.
- Khi `@CachePut` dùng cùng cache name và key với `@Cacheable`, lần đọc tiếp theo nhận giá trị mới mà không phải đọc lại repository.
- Khi phương thức cập nhật ném ngoại lệ trước khi ghi nguồn, giá trị cũ trong cache không bị thay bởi một kết quả từ lời gọi thất bại.

### 5.1. Cấu trúc thư mục

~~~text
cacheable-vs-cacheput/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CacheableVsCachePutDemo.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>cacheable-vs-cacheput</artifactId>
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
        <version>3.14.0</version>
        <artifactId>maven-compiler-plugin</artifactId>
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

### 5.3. src/main/java/demo/CacheableVsCachePutDemo.java

~~~java
package demo;

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

public class CacheableVsCachePutDemo {

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("productNames");
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
        private final Map<Long, String> names = new ConcurrentHashMap<>();

        public ProductRepository() {
            names.put(42L, "Book");
        }

        public String findName(long id) {
            return names.get(id);
        }

        public String saveName(long id, String newName) {
            names.put(id, newName);
            return newName;
        }
    }

    public static class ProductService {
        private final ProductRepository repository;
        private final AtomicInteger sourceReads = new AtomicInteger();
        private final AtomicInteger sourceWrites = new AtomicInteger();

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @Cacheable(cacheNames = "productNames", key = "#p0",
                   unless = "#result == null")
        public String getName(long productId) {
            sourceReads.incrementAndGet();
            return repository.findName(productId);
        }

        @CachePut(cacheNames = "productNames", key = "#p0",
                  unless = "#result == null")
        public String rename(long productId, String newName) {
            if ("INVALID".equals(newName)) {
                throw new IllegalArgumentException("invalid product name");
            }
            sourceWrites.incrementAndGet();
            return repository.saveName(productId, newName);
        }

        public int sourceReads() {
            return sourceReads.get();
        }

        public int sourceWrites() {
            return sourceWrites.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            ProductService service = context.getBean(ProductService.class);

            System.out.println("Read #1: " + service.getName(42L));
            System.out.println("Read #2: " + service.getName(42L));
            System.out.println("Source reads: " + service.sourceReads());

            System.out.println("Rename #1: " +
                    service.rename(42L, "Notebook"));
            System.out.println("Read #3: " + service.getName(42L));
            System.out.println("Source reads: " + service.sourceReads());

            System.out.println("Rename #2: " +
                    service.rename(42L, "Guide"));
            System.out.println("Source writes: " + service.sourceWrites());
            System.out.println("Read #4: " + service.getName(42L));

            try {
                service.rename(42L, "INVALID");
            } catch (IllegalArgumentException ex) {
                System.out.println("Failure: " + ex.getMessage());
            }

            System.out.println("Read after failure: " +
                    service.getName(42L));
            System.out.println("Final source reads: " + service.sourceReads());
            System.out.println("Final source writes: " + service.sourceWrites());
        }
    }
}
~~~

**Tại sao có thể chạy?** `@EnableCaching` bật Spring cache interception; `ProductService` được Spring tạo thành bean, phương thức public được gọi thông qua bean lấy từ `ApplicationContext`. `spring-context` kéo theo các dependency Spring cần thiết cho cache abstraction và proxy ở cấu hình này. Để làm ví dụ dễ kiểm chứng, nguồn được mô phỏng bằng `ConcurrentHashMap`; đây không phải một phương thức cập nhật database production.

### 5.4. Cách chạy

Từ thư mục chứa `pom.xml`, với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheableVsCachePutDemo
~~~

Các dòng **chương trình in ra** sẽ là:

~~~text
Read #1: Book
Read #2: Book
Source reads: 1
Rename #1: Notebook
Read #3: Notebook
Source reads: 1
Rename #2: Guide
Source writes: 2
Read #4: Guide
Failure: invalid product name
Read after failure: Guide
Final source reads: 1
Final source writes: 2
~~~

### 5.5. Giải thích từng giai đoạn

**Hai lần đọc đầu:** `getName(42L)` lần thứ nhất là cache miss, chạy repository và ghi "Book" vào `productNames[42L]`. Lần thứ hai là hit, Spring trả "Book" từ cache; bộ đếm đọc nguồn vẫn là 1.

**Lần đổi tên thứ nhất:** `rename(42L, "Notebook")` chạy thật, repository đổi tên và trả "Notebook". `@CachePut` ghi "Notebook" vào **cùng key 42L** trong `productNames`, thay nội dung trước đó.

**Lần đọc thứ ba:** `getName(42L)` nhận "Notebook" từ cache; không tăng số lần đọc nguồn. Điều này chỉ đúng vì hai annotation dùng đúng **cùng tên vùng cache và cùng key**.

**Lần đổi tên thứ hai:** dù key 42L đã được cache và lần đọc trước là cache hit, `rename(42L, "Guide")` **vẫn thực thi**. Bộ đếm ghi nguồn thành 2 và cache được cập nhật thành "Guide".

**Thao tác lỗi:** `rename(42L, "INVALID")` ném ngoại lệ trước khi thay đổi repository. Không có kết quả thành công mới để `@CachePut` lưu; cache vẫn chứa "Guide". Bộ đếm `sourceWrites` không tăng vì nhánh validation đã ngăn thao tác ghi.

**Hạn chế của ví dụ:** nếu thao tác ghi database đã thực hiện nhưng **sau đó ném exception**, Spring không tự hoàn tác side effect hoặc toàn bộ transaction thay bạn. Cần thiết kế transaction và cơ chế phục hồi riêng. Cache provider cũng có thể ném lỗi sau khi nghiệp vụ đã hoàn tất; `@CachePut` không phải giao dịch nguyên tử giữa cache và database.

## 6. Tại sao cacheNames và key phải khớp giữa read và update?

Trong demo, hai phương thức có chữ ký khác nhau:

~~~java
getName(long productId)
rename(long productId, String newName)
~~~

Nếu để Spring dùng key mặc định:

- `getName(42L)` có một tham số → key là `42L`.
- `rename(42L, "Notebook")` có hai tham số → key là `SimpleKey(42L, "Notebook")`.

Lúc đó `@CachePut` sẽ ghi vào **một entry khác**. Entry cũ theo key `42L` có thể vẫn chứa "Book", khiến `getName(42L)` tiếp tục nhận dữ liệu cũ.

Vì vậy ví dụ dùng cùng `key = "#p0"`: cả hai đều chọn tham số thứ nhất là `productId`. Đồng thời cả hai dùng `cacheNames = "productNames"`.

**Không chỉ cần cùng key; còn phải cùng cache name.** Cặp `(cacheName, key)` xác định đúng entry cần cập nhật.

Với dữ liệu đa tenant, khóa chỉ dùng `productId` có thể không đủ: nếu kết quả phụ thuộc `tenantId`, `locale`, `currency` hoặc chính sách phân quyền, mọi yếu tố ảnh hưởng giá trị phải được xét trong key, namespace và kiểm soát truy cập. Đặc biệt, caching không thay thế authorization theo request.

Nếu nhiều phương thức cần quy tắc khóa chung, cân nhắc một `KeyGenerator` được Spring quản lý hoặc `@CacheConfig` để tránh copy/paste biểu thức tạo khóa.

## 7. Khi nào chọn @Cacheable, @CachePut hoặc @CacheEvict?

| Tình huống | Gợi ý |
| --- | --- |
| `findById(id)` chỉ đọc, kết quả có thể tái sử dụng | `@Cacheable` |
| `getCategories(locale)` được gọi lặp, dữ liệu ít đổi | `@Cacheable` với thời gian sống phù hợp |
| `updateProduct(id, input)` cần luôn ghi DB và trả **Product mới đầy đủ** | `@CachePut` nếu kết quả khớp giá trị cache của đường đọc |
| `renameProduct(id, name)` trả về `void` hoặc `boolean` | `@CacheEvict` thường an toàn hơn việc put giá trị không tương thích |
| Xóa một sản phẩm và loại entry đọc cũ | `@CacheEvict` |
| Cập nhật một sản phẩm ảnh hưởng danh sách, thống kê, bộ lọc | Cần evict hoặc cập nhật **các cache phụ thuộc** theo thiết kế |
| Thu tiền, gửi email, tạo đơn có side effect bắt buộc | Không dùng `@Cacheable` để bỏ qua thao tác; cân nhắc transaction và idempotency nghiệp vụ |
| Tính toán đắt đỏ nhưng đầu vào không lặp | Cân nhắc không cache hoặc chỉ cache subset phổ biến |

Một bản cập nhật có thể thay đổi nhiều vùng cache: ví dụ thay giá sản phẩm ảnh hưởng `productById`, `productList`, `priceSummary`. `@CachePut` chỉ đưa **một kết quả** vào những vùng/key được khai báo; nó không tự khám phá mọi truy vấn phụ thuộc. Những vùng khác cần chính sách invalidation hoặc cập nhật riêng.

### Ví dụ phối hợp Cacheable với CacheEvict

Đây là **mã minh họa** trong Spring service có repository và ProductDto:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto getProduct(long id) {
    return repository.findDtoById(id);
}

@CacheEvict(cacheNames = "products", key = "#p0")
public void updateProduct(long id, ProductUpdateRequest request) {
    repository.update(id, request);
}
~~~

Khi `updateProduct` hoàn tất thành công, Spring mặc định xóa entry theo key. Lần đọc kế tiếp sẽ tạo một giá trị mới. Nếu cần đồng bộ tuyệt đối sau transaction commit, phải xét thời điểm evict so với transaction, không chỉ nhìn annotation.

## 8. Điều kiện ghi: condition, unless, null và exception

Cả hai annotation có thể sử dụng `condition` và `unless`, nhưng **ý nghĩa đối với việc thực thi phương thức vẫn khác nhau**.

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 > 0",
    unless = "#result == null"
)
public Product findProduct(long id) {
    return repository.find(id);
}

@CachePut(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 > 0",
    unless = "#result == null"
)
public Product updateProduct(long id, ProductUpdateRequest request) {
    return repository.updateAndReturn(id, request);
}
~~~

Đây là các đoạn minh họa, không phải chương trình hoàn chỉnh.

- **`condition`:** quyết định có áp dụng hành vi cache cho lời gọi theo biểu thức hay không. Với `@Cacheable`, nếu không áp dụng caching, phương thức vẫn chạy; với `@CachePut`, phương thức vẫn luôn chạy dù có put hay không.
- **`unless`:** kiểm tra sau khi có kết quả để từ chối lưu, chẳng hạn từ chối lưu `null`. `#result` được dùng trong `unless`; trên cache put cũng có thể dùng để tính key khi cần.
- **Trả `null`:** nếu không có unless, khả năng lưu null phụ thuộc cấu hình/cache provider. Không mặc định cho rằng null luôn là cache miss về sau.
- **Ném exception:** khi phương thức đích không trả về bình thường, thao tác cache put cho kết quả thành công đó không được thực hiện. Nhưng nếu phương thức bắt lỗi nội bộ rồi trả DTO chứa lỗi, DTO vẫn có thể được lưu nếu điều kiện cho phép.

### Khác biệt khi kết quả cũ đã được cache

`@Cacheable` với một key **đang có giá trị** thường không chạy phương thức; vì vậy `unless` không phải cách buộc Spring gọi lại nguồn khi cache hit. Ngược lại, `@CachePut` luôn chạy thân phương thức và chỉ dùng `unless` để xét **có ghi kết quả vừa tạo** vào cache hay không. Nếu `unless` từ chối lưu, entry cũ có thể vẫn tồn tại; Spring không tự xóa nó.

### Lưu ý về Optional và bất đồng bộ

Spring có cơ chế xử lý `Optional<T>`: giá trị hiện diện được lưu dưới dạng giá trị bên trong, còn `Optional.empty()` tương ứng với null nếu provider cho phép. Trong biểu thức `unless`, `#result` đại diện cho giá trị nghiệp vụ đã mở wrapper. Từ Spring Framework 6.1, hỗ trợ `CompletableFuture` và các kiểu trả về reactive giúp `@Cacheable`/`@CachePut` xử lý kết quả khi có giá trị hoàn tất; đừng đồng nhất lúc trả về wrapper với lúc cache chứa kết quả cuối.

## 9. Những điều Spring proxy và transaction không tự bảo đảm

### 9.1. Self-invocation

Trong **proxy mode mặc định**, annotation caching chỉ áp dụng nếu lời gọi đi qua Spring proxy. Một lời gọi nội bộ kiểu `this.rename(id, name)` từ phương thức khác trong cùng bean sẽ bỏ qua interceptor, nên `@CachePut` có thể **không cập nhật cache** dù database đã thay đổi.

Tương tự, `this.getName(id)` có thể bỏ qua `@Cacheable`. Đặt các điểm truy cập ở ranh giới bean phù hợp hoặc dùng cơ chế interception khác khi thực sự cần; kiểm thử với bean được lấy từ `ApplicationContext`.

### 9.2. Transaction commit

`@CachePut` thông thường cân nhắc ghi cache sau khi phương thức đích trả về thành công. Điều này **không tự chứng minh database transaction đã commit**. Thứ tự cache advice/transaction advice và transaction-aware cache quyết định thời điểm thực tế. Nếu cache được cập nhật trước commit rồi transaction rollback, dữ liệu trong cache có thể không phản ánh trạng thái nguồn.

Với cập nhật nghiệp vụ quan trọng, cần thiết kế after-commit, transaction-aware cache hoặc chính sách evict/reload phù hợp; kiểm thử rõ trường hợp commit, rollback và concurrent read. Cache và database không mặc định tạo thành một giao dịch nguyên tử phân tán.

### 9.3. Nhiều instance và độ mới

`ConcurrentMapCacheManager` trong ví dụ chỉ lưu trong RAM tiến trình. Nếu ứng dụng chạy nhiều instance với cache local riêng, một `@CachePut` trên instance A **không tự cập nhật** cache của instance B. Khi cần mọi node nhìn thấy cùng dữ liệu cập nhật, chọn cache dùng chung (ví dụ Redis) hoặc cơ chế phát sự kiện invalidation với hợp đồng nhất quán phù hợp.

`@CachePut` cũng không quy định TTL, giới hạn số entry hay thời gian dữ liệu tồn tại; những việc đó thuộc cache provider.

### 9.4. Lỗi cache provider

Sau khi phương thức ghi database thành công, một lỗi `Cache.put` có thể xảy ra. Tùy cấu hình `CacheErrorHandler`, lỗi cache có thể lan ra caller hoặc được xử lý riêng. Vì vậy đừng dựa vào `@CachePut` như bằng chứng rằng thao tác cache và nguồn đều thành công nguyên tử.

## 10. Vì sao không nên đặt @Cacheable và @CachePut trên cùng phương thức?

Một annotation cố gắng **bỏ qua thực thi khi có cache hit**; annotation kia yêu cầu **luôn thực thi để tạo giá trị mới**. Trộn cả hai lên cùng một method làm ý nghĩa luồng thực thi khó dự đoán và dễ gây kết quả bất ngờ.

**Cách viết không nên dùng:**

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
@CachePut(cacheNames = "products", key = "#p0")
public Product updateAndRead(long id) {
    return repository.updateAndRead(id);
}
~~~

Đây là **phản ví dụ**, không phải khuyến nghị. Tài liệu Spring cảnh báo mạnh việc kết hợp cả hai trên cùng một phương thức; chỉ một số trường hợp đặc biệt có điều kiện loại trừ lẫn nhau được xem xét, và các điều kiện đó không được phụ thuộc `#result` khi Spring cần xác minh trước.

**Cách rõ ràng hơn:** `@Cacheable` trên phương thức đọc; `@CachePut` trên phương thức cập nhật trả đúng DTO; hoặc `@CacheEvict` nếu cần xóa cache để lần đọc tới nạp lại. Mỗi phương thức có một hợp đồng thực thi minh bạch.

## 11. Các lỗi thường gặp và cách khắc phục

1. **Dùng `@Cacheable` trên phương thức ghi.** Trên cache hit, method có thể bị bỏ qua và dữ liệu không được cập nhật. Tách đường đọc và đường ghi; dùng `@CachePut` hoặc `@CacheEvict` cho đường ghi theo kết quả trả về.
2. **Dùng `@CachePut` để tăng tốc phương thức đọc.** Method vẫn chạy mỗi lần nên không tiết kiệm truy vấn nguồn. Dùng `@Cacheable` nếu mục tiêu là reuse kết quả.
3. **Để key mặc định của hai method có số tham số khác nhau.** `@Cacheable` và `@CachePut` tạo ra hai key khác nhau, dẫn tới stale. Khai báo key thống nhất hoặc KeyGenerator chung.
4. **Cùng key nhưng khác cache name.** Put vào vùng này không cập nhật entry ở vùng khác. Xác định đúng `cacheNames` và các vùng phụ thuộc.
5. **CachePut trả `void`/boolean trong cache dành cho DTO.** Giá trị lưu không phù hợp với kiểu mà phương thức đọc mong chờ. Dùng `@CacheEvict` hoặc trả DTO hoàn chỉnh.
6. **Quên `unless` trên kết quả không hợp lệ.** Một giá trị null/DTO lỗi có thể bị lưu theo provider. Định nghĩa rõ chính sách negative caching.
7. **Nghĩ `condition=false` sẽ bỏ qua phương thức `@CachePut`.** Điều kiện chỉ ảnh hưởng caching; thân phương thức vẫn được gọi.
8. **Gọi từ cùng bean qua `this`.** Proxy mode mặc định không chặn self-invocation. Tách bean/ranh giới lời gọi phù hợp.
9. **Mặc định cache cập nhật sau commit.** Thiết kế thời điểm cache put/evict gắn transaction thực tế, kiểm thử rollback.
10. **Quên nhiều instance hoặc những cache phụ thuộc.** Một put không cập nhật mọi bản sao local hay tất cả query cache khác.
11. **Nhầm lỗi nghiệp vụ và ngoại lệ Java.** Nếu method bắt exception rồi trả DTO lỗi, Spring có thể coi đó là giá trị trả về bình thường để cache nếu không có veto.
12. **Chỉ đo hit ratio mà bỏ qua tính đúng.** Cache hit cao không có ý nghĩa nếu người dùng nhận dữ liệu stale hoặc bị lẫn tenant. Cần kiểm thử kết quả sau cập nhật.

## 12. Câu hỏi tự kiểm tra

**1.** Key 42 đã có trong cache. Khi gọi một phương thức `@Cacheable` với key đó, Spring có nhất thiết chạy thân phương thức không?  
**Đáp án:** Không. Với cache hit hợp lệ, Spring thường trả giá trị từ cache và bỏ qua thân phương thức.

**2.** Key 42 đã có trong cache. Khi gọi một phương thức `@CachePut` với key đó, phương thức có được bỏ qua không?  
**Đáp án:** Không. Phương thức vẫn chạy; kết quả có thể thay thế entry cũ nếu điều kiện cho phép.

**3.** Vì sao `@Cacheable get(long id)` và `@CachePut update(long id, String name)` dễ tạo key khác nhau khi không khai báo key?  
**Đáp án:** Spring mặc định dùng một tham số làm key trực tiếp nhưng dùng `SimpleKey` gồm cả hai tham số cho method update.

**4.** `updateProduct` trả `boolean` nhưng cache chứa `ProductDto`. Nên chọn gì?  
**Đáp án:** Thường chọn `@CacheEvict` để xóa entry và đọc lại DTO sau đó, hoặc sửa contract để method update trả DTO đầy đủ đúng với cache.

**5.** `@CachePut(unless = "#result == null")` khi method trả null có nghĩa method không chạy?  
**Đáp án:** Không. Method đã chạy và trả null; `unless` chỉ từ chối cache put.

**6.** Vì sao `@CachePut` không đảm bảo tự động nhất quán với database trong một transaction đang rollback?  
**Đáp án:** Cache advice không mặc định là giao dịch nguyên tử cùng database; cần xét commit order và transaction-aware policy.

**7.** Có nên đặt đồng thời `@Cacheable` và `@CachePut` trên một method để “có cả hai lợi ích”?  
**Đáp án:** Nói chung không. Hai annotation có mục tiêu thực thi mâu thuẫn; nên tách phương thức đọc và cập nhật.

**8.** Một lần `@CachePut` thành công trên instance A có tự thay cache local instance B không?  
**Đáp án:** Không. Cần shared cache hoặc cơ chế đồng bộ/invalidation đa node.

## Tài liệu tham khảo

- Spring Framework Reference — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Spring Framework Reference — Configuring the Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework Javadoc — CachePut: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework Javadoc — Cacheable: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html
