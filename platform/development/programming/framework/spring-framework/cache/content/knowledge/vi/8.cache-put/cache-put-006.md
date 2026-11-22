# Hành vi khi phương thức phát sinh ngoại lệ với `@CachePut`

## 1. Kết luận cần nhớ

Trong Spring Framework, `@CachePut` đánh dấu phương thức mà **kết quả trả về sau khi thực thi thành công** sẽ được đưa vào cache, tùy `condition` và `unless`. Khác với `@Cacheable`, `@CachePut` **không dùng cache hit để bỏ qua thân phương thức**: mỗi lời gọi được Spring intercept theo cơ chế cache thông thường vẫn gọi phương thức đích.

Nếu **thân phương thức ném ngoại lệ thay vì trả về bình thường**, Spring **không thực hiện thao tác cache put cho kết quả của lời gọi bị lỗi đó**. Ngoại lệ được truyền lên bên gọi theo cơ chế ngoại lệ thông thường, trừ khi một tầng khác bắt/xử lý nó.

Ba ý không được đánh đồng:

1. **Không có cache put mới:** vì phương thức không trả về kết quả bình thường để lưu.
2. **Không tự xóa entry cũ:** `@CachePut` không phải `@CacheEvict`; entry đã có có thể vẫn còn và tiếp tục được đọc.
3. **Không bảo đảm rollback dữ liệu ngoài cache:** nếu phương thức đã thay đổi database, gọi API, ghi file hoặc phát event *trước khi ném ngoại lệ*, các tác dụng phụ đó có thể đã xảy ra nếu không có cơ chế giao dịch/bù trừ phù hợp.

Ví dụ ngắn:

```java
@CachePut(cacheNames = "products", key = "#p0")
public Product updateProduct(String id, String title) {
    repository.save(id, title);
    throw new IllegalStateException("Cannot finish update");
}
```

*Đây là minh họa hành vi, không phải chương trình độc lập: `Product` và `repository` chưa được định nghĩa.*

Khi lệnh `throw` được thực thi, phương thức không trả về `Product`; do đó **không có kết quả để `@CachePut` ghi vào cache**. Tuy nhiên, lệnh `repository.save(...)` đã được gọi; việc thay đổi ấy có được rollback không phụ thuộc transaction, repository và hạ tầng đang dùng, **không phải do `@CachePut` tự quyết định**.

## 2. Luồng thực thi bình thường và luồng phát sinh ngoại lệ

Trong kịch bản đồng bộ, lời gọi đi từ một bean khác qua Spring proxy:

```text
Caller
  |
  v
Spring cache advice của @CachePut
  |
  |  (có thể xét condition dựa trên dữ liệu đầu vào)
  v
Thực thi phương thức đích
  |
  +-- Hoàn thành bình thường, có return value
  |      |
  |      +-- unless hoặc điều kiện cache từ chối lưu? -> bỏ qua put
  |      |
  |      '-- được phép lưu -> tính key thích hợp -> cache.put(key, result)
  |                                      |
  |                                      '-- trả kết quả cho caller
  |
  '-- Ném exception
         |
         +-- KHÔNG chạy cache put của @CachePut cho lời gọi thất bại
         |
         '-- exception truyền lên caller (nếu không có tầng bắt khác)
```

Trong một số cấu hình, Spring có thể phân giải cache hoặc kiểm tra `condition` **trước** khi gọi method; vì vậy không nên diễn đạt rằng interceptor hoàn toàn không làm bất cứ việc gì khi method lỗi. Điều bảo đảm trong mô hình mặc định là **không có thao tác ghi kết quả thành công từ `@CachePut` sau một lời gọi ném ngoại lệ**.

| Trường hợp | Phương thức có chạy? | Kết quả của `@CachePut` | Điều bên gọi quan sát |
| --- | --- | --- | --- |
| Hoàn thành bình thường, cho phép cache | Có | Ghi/thay thế entry theo key | Nhận return value |
| Hoàn thành bình thường, `condition=false` | Có | Không ghi cache theo operation | Nhận return value |
| Hoàn thành bình thường, `unless=true` | Có | Không ghi cache | Nhận return value |
| Ném `IllegalArgumentException` trước khi sửa dữ liệu | Có | Không ghi cache từ lần gọi lỗi | Nhận ngoại lệ |
| Ném ngoại lệ sau khi sửa dữ liệu ngoài cache | Có | Không ghi cache từ lần gọi lỗi | Nhận ngoại lệ; side effect có thể vẫn còn |
| `cache.put` hoặc key expression lỗi **sau khi method trả về** | Có, có thể đã hoàn thành | Có thể không ghi thành công | Ngoại lệ ở tầng cache (phân biệt với ngoại lệ thân method) |

Dòng cuối rất quan trọng khi chẩn đoán: **“caller nhận exception” không luôn đồng nghĩa “method đích đã ném exception”**. Lỗi có thể đến từ kết nối Redis, serializer, key expression hoặc cache adapter sau khi method đã chạy xong.

## 3. Entry cũ trong cache sẽ ra sao?

`@CachePut` **cập nhật** cache bằng kết quả mới của phương thức, nhưng chỉ khi việc xử lý theo annotation có đủ dữ liệu và điều kiện để ghi. Xét cache đã có entry:

```text
products["P1"] = Product("P1", "Tên cũ", revision=1)
```

Lời gọi `updateProduct("P1", "Tên mới")` ném ngoại lệ. Nếu không có thao tác cache nào khác, `@CachePut` thất bại **không tự thay thế** entry cũ bằng `"Tên mới"` và cũng **không tự xóa** entry:

```text
Trước: cache["P1"] = Tên cũ
Gọi update -> method throws
Sau:   cache["P1"] = Tên cũ   (nếu không có thao tác thay đổi nào khác)
```

Hệ quả:

- Một phương thức đọc có `@Cacheable(cacheNames="products", key="#p0")` vẫn có thể **cache hit** và trả dữ liệu cũ.
- Nếu cache vốn chưa có key `"P1"`, lời gọi `@CachePut` bị lỗi không tự tạo ra key đó.
- Đây là hành vi của **operation `@CachePut` bị lỗi**, không phải cam kết mọi cache bất biến. Nếu một thread khác đồng thời ghi hoặc evict cùng key, trạng thái cuối vẫn phụ thuộc cạnh tranh giữa các thao tác.

Vì vậy cần phân biệt hai câu hỏi: **Có ghi dữ liệu mới không?** và **Dữ liệu cũ có bị xóa không?** Với `@CachePut` phát sinh ngoại lệ, câu trả lời mặc định là **không ghi kết quả mới** và **không tự evict entry cũ**.

## 4. Ngoại lệ trước và sau khi thay đổi database

Hai trường hợp có cùng kết quả ở tầng `@CachePut` (không ghi cache mới) nhưng hậu quả về dữ liệu nguồn rất khác nhau.

### 4.1. Ném ngoại lệ trước thay đổi dữ liệu

```java
@CachePut(cacheNames = "products", key = "#p0")
public Product rename(String id, String newTitle) {
    if (newTitle.isBlank()) {
        throw new IllegalArgumentException("Title is required");
    }
    return repository.rename(id, newTitle);
}
```

Nếu `newTitle` rỗng và method throw ngay tại kiểm tra đầu vào, repository không được gọi. Giả sử không có side effect khác, database và cache đều chưa thay đổi.

### 4.2. Ném ngoại lệ sau thay đổi dữ liệu

```java
@CachePut(cacheNames = "products", key = "#p0")
public Product rename(String id, String newTitle) {
    Product saved = repository.rename(id, newTitle);
    externalNotifier.send(saved);  // có thể thất bại
    return saved;
}
```

*Hai ví dụ trên chỉ minh họa. Cần định nghĩa `Product`, `repository` và `externalNotifier` mới biên dịch được.*

Nếu repository đã ghi thành công mà `externalNotifier.send(...)` ném ngoại lệ, phương thức `rename` **không trả về `saved`**, dù biến `saved` đã có giá trị nội bộ. `@CachePut` không ghi cache dựa trên biến cục bộ ấy; Spring chỉ có thể quan sát một lần hoàn thành bình thường hoặc một ngoại lệ. Nếu ghi dữ liệu không được rollback, database có thể là `"Tên mới"` trong khi cache vẫn còn `"Tên cũ"`.

**Sai lầm phổ biến:** nghĩ rằng `@CachePut` có trách nhiệm đồng bộ database và cache theo nguyên tắc all-or-nothing. Nó không cung cấp transaction phân tán hay rollback tự động cho side effect của method.

Nếu method thuộc transaction và exception kích hoạt rollback, thay đổi database có thể được hoàn tác theo quy tắc của transaction manager. Mặc định, Spring transaction thường rollback với `RuntimeException` và `Error`, còn checked exception cần cấu hình thích hợp (ví dụ `rollbackFor`), tùy phiên bản/cấu hình. Không suy luận rollback chỉ từ việc có `@CachePut`.

## 5. `#result`, `key`, `condition`, `unless` khi có exception

Spring Cache dùng SpEL cho key và điều kiện, nhưng biểu thức lấy **giá trị trả về** chỉ có dữ liệu nếu phương thức đã tạo ra kết quả:

```java
@CachePut(
    cacheNames = "products",
    key = "#result.id()",
    unless = "#result == null"
)
public Product saveProduct(ProductDraft draft) {
    return repository.save(draft);
}
```

*Đoạn minh họa: các kiểu và repository chưa được khai báo.*

Nếu `repository.save(draft)` trả `Product` bình thường, Spring có thể lấy `#result.id()` làm khóa và đánh giá `unless` để quyết định lưu. Nếu `saveProduct` ném exception:

- Không có `#result` thành công của method để tạo key ghi mới.
- Biểu thức `unless` không phải một khối `catch` hoặc bộ xử lý lỗi; nó không được dùng để biến exception thành result hợp lệ.
- Cache put không được thực hiện cho lời gọi ném exception.
- Ngoại lệ vẫn truyền lên; cần xử lý tại nơi thích hợp của tầng nghiệp vụ/API.

Bảng phân biệt:

| Thành phần | Vai trò khi method **trả về bình thường** | Vai trò khi method **throw** |
| --- | --- | --- |
| `condition` | Quyết định có áp dụng thao tác cache hay không, thường từ dữ liệu đầu vào | Không bắt exception; nếu false, method vẫn chạy và vẫn có thể throw |
| `key = "#p0"` | Tạo key từ đối số | Không khiến cache put xảy ra nếu không có return value |
| `key = "#result.id()"` | Tạo key từ kết quả khi có kết quả | Không có result thành công để tạo khóa put |
| `unless = "#result == null"` | Từ chối ghi khi method trả `null` | **Không phải** kiểm tra exception hay rollback |
| `@CachePut` | Gọi method và có thể put | Không put kết quả của lời gọi ném ngoại lệ |

Lưu ý: ngay cả khi chọn key từ đối số thay vì từ `#result`, một lời gọi thất bại cũng không có giá trị return thành công để lưu. Vấn đề không nằm ở cú pháp key mà ở **kết quả thực thi phương thức**.

## 6. Ví dụ Java 17+ chạy được: ba tình huống đối chiếu

Ví dụ dùng **Java 17**, **Spring Boot 3.3.5**, Maven và `ConcurrentMapCacheManager` trong một JVM. Một map đóng vai “database” để minh họa chủ ý việc **đã sửa dữ liệu nhưng lại throw**, không có transaction tự động.

Ta có:

- `find` dùng `@Cacheable` để thấy cache hit.
- `rename` dùng `@CachePut(key="#result.id()")` để cập nhật entry sau khi method trả về bình thường.
- Ba chế độ: lỗi **BEFORE** (trước ghi dữ liệu), lỗi **AFTER** (đã ghi dữ liệu nhưng throw), và **SUCCESS** (trả về bình thường).

### 6.1. Cấu trúc dự án

```text
cacheput-exception-demo/
├── pom.xml
└── src/main/java/example/cacheputerrors/
    ├── Application.java
    ├── Product.java
    └── ProductService.java
```

### 6.2. File `pom.xml`

```xml
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
    <artifactId>cacheput-exception-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
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
```

### 6.3. File `src/main/java/example/cacheputerrors/Product.java`

```java
package example.cacheputerrors;

public record Product(String id, String title, int revision) {}
```

### 6.4. File `src/main/java/example/cacheputerrors/ProductService.java`

```java
package example.cacheputerrors;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    public enum Mode {
        BEFORE, AFTER, SUCCESS
    }

    private final Map<String, Product> database = new ConcurrentHashMap<>();

    public ProductService() {
        database.put("P1", new Product("P1", "Original", 1));
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public Product find(String id) {
        System.out.println("DB_READ " + id);
        return database.get(id);
    }

    @CachePut(cacheNames = "products", key = "#result.id()")
    public Product rename(String id, String title, Mode mode) {
        System.out.println("METHOD_" + mode + " " + id);

        if (mode == Mode.BEFORE) {
            throw new IllegalStateException("before mutation");
        }

        Product current = database.get(id);
        if (current == null) {
            throw new IllegalArgumentException("Unknown product: " + id);
        }

        Product changed = new Product(id, title, current.revision() + 1);
        database.put(id, changed);

        if (mode == Mode.AFTER) {
            throw new IllegalStateException("after mutation");
        }

        return changed;
    }
}
```

### 6.5. File `src/main/java/example/cacheputerrors/Application.java`

```java
package example.cacheputerrors;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    CommandLineRunner demo(ProductService products) {
        return args -> {
            System.out.println("READ1 -> " + products.find("P1"));
            System.out.println("READ2 -> " + products.find("P1"));

            try {
                products.rename("P1", "Rejected", ProductService.Mode.BEFORE);
            } catch (IllegalStateException ex) {
                System.out.println("ERROR1 -> " + ex.getMessage());
            }

            System.out.println("READ3 -> " + products.find("P1"));

            try {
                products.rename("P1", "DatabaseOnly", ProductService.Mode.AFTER);
            } catch (IllegalStateException ex) {
                System.out.println("ERROR2 -> " + ex.getMessage());
            }

            System.out.println("READ4 -> " + products.find("P1"));

            System.out.println(
                "PUT -> " +
                products.rename("P1", "Committed", ProductService.Mode.SUCCESS)
            );
            System.out.println("READ5 -> " + products.find("P1"));
        };
    }
}
```

### 6.6. Lệnh chạy và stdout

Tại thư mục `cacheput-exception-demo`, dùng JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Các dòng do chương trình ví dụ phát ra theo **đúng thứ tự** (Spring Boot có thêm log khởi động):

```text
DB_READ P1
READ1 -> Product[id=P1, title=Original, revision=1]
READ2 -> Product[id=P1, title=Original, revision=1]
METHOD_BEFORE P1
ERROR1 -> before mutation
READ3 -> Product[id=P1, title=Original, revision=1]
METHOD_AFTER P1
ERROR2 -> after mutation
READ4 -> Product[id=P1, title=Original, revision=1]
METHOD_SUCCESS P1
PUT -> Product[id=P1, title=Committed, revision=3]
READ5 -> Product[id=P1, title=Committed, revision=3]
```

### 6.7. Giải thích output theo từng bước

**Bước 1 — READ1 và READ2.** Lần đọc đầu miss nên `find` in `DB_READ P1`, trả `Product(... Original, revision=1)` và lưu vào cache `products["P1"]`. Lần đọc thứ hai hit, không chạy thân `find` nên không in thêm `DB_READ`.

**Bước 2 — BEFORE.** `rename(..., BEFORE)` vẫn vào thân method dù cache đang có key `P1`: `@CachePut` không bỏ qua method vì hit. Sau khi in `METHOD_BEFORE P1`, method ném `IllegalStateException` trước khi ghi map. Spring không ghi cache mới; caller bắt lỗi và in `ERROR1`. `READ3` vẫn hit entry `Original, revision=1`.

**Bước 3 — AFTER.** `rename(..., AFTER)` tạo `Product(... DatabaseOnly, revision=2)` rồi cập nhật map **trước** khi throw. Vì không có transaction trong demo, thay đổi map tồn tại. Nhưng `@CachePut` không được chạy phần put cho lời gọi lỗi, vì method không return. Vì thế `READ4` vẫn hit **cache cũ** `Original, revision=1`. Đây là ví dụ chủ ý về trạng thái **database giả lập mới nhưng cache cũ**.

**Bước 4 — SUCCESS.** `rename(..., SUCCESS)` đọc revision hiện tại trong map là **2**, tăng lên **3**, đổi title thành `Committed` và trả `Product` bình thường. `@CachePut(key="#result.id()")` lấy ID `"P1"` từ result rồi ghi đè cache key `P1` bằng `revision=3`. `READ5` hit kết quả mới, không có dòng `DB_READ` mới.

**Lưu ý về tính chạy được:** ba file Java có package khớp vị trí tệp; Spring Boot scan bean `ProductService`; `@EnableCaching` bật interceptor; đối tượng được gọi qua Spring-managed bean do `CommandLineRunner` injection nên không vướng self-invocation. Mã in dự kiến đã được đối chiếu theo thứ tự thực thi Java và cache operation; cấu hình Maven đầy đủ để chạy trong môi trường có JDK/Maven và tải được dependencies. Mẫu này không mô phỏng transaction thực tế; `ConcurrentHashMap` được dùng riêng để cho thấy side effect còn tồn tại sau exception.

## 7. Ngoại lệ bị bắt bên trong method thì sao?

Hợp đồng `@CachePut` xét việc phương thức **kết thúc bằng một giá trị trả về bình thường**, không xét nội bộ đã có bao nhiêu lần `catch`.

```java
@CachePut(cacheNames = "products", key = "#p0")
public Product updateWithFallback(String id, String title) {
    try {
        return repository.update(id, title);
    } catch (TemporaryServiceException ex) {
        return new Product(id, "Fallback", 0);
    }
}
```

*Đoạn trên minh họa, cần khai báo `repository` và `TemporaryServiceException`.*

Nếu exception được bắt trong phương thức và phương thức **trả về `Product(..., "Fallback", 0)`**, Spring thấy một lần hoàn thành **bình thường**. Nếu không có `condition`/`unless` loại trừ, `@CachePut` có thể **ghi giá trị fallback vào cache**. Đây có thể là quyết định nghiệp vụ chủ động hoặc một lỗi nghiêm trọng nếu fallback không được phép thay thế dữ liệu thực.

Nếu không muốn cache fallback, cần một hợp đồng thể hiện rõ kết quả nào có thể lưu, chẳng hạn:

- Trả đối tượng chứa trạng thái `success` rồi dùng `unless = "!#result.success()"` khi method trả về bình thường.
- Dùng `unless` để veto kết quả `null`/placeholder khi phù hợp.
- Hoặc cho exception truyền lên khi thao tác thất bại thật sự và để tầng caller xử lý.

Ví dụ khái niệm với result được gắn cờ:

```java
public record UpdateOutcome(String id, boolean success, String message) {}

@CachePut(cacheNames = "outcomes", key = "#result.id()",
          unless = "!#result.success()")
public UpdateOutcome tryUpdate(String id) {
    return new UpdateOutcome(id, false, "Cannot update");
}
```

*Đây là code minh họa trong một class/service Spring, không phải một file Java độc lập.*

Vì method trên **return bình thường** với `success=false`, `unless` quyết định không ghi; đây là cơ chế khác với **ném ngoại lệ**. Nên thiết kế key/đối tượng trả về sao cho biểu thức không dereference `null`.

## 8. `@Transactional` và thời điểm cache update

Giả sử thao tác cập nhật chạy trong transaction:

```java
@Transactional
@CachePut(cacheNames = "products", key = "#result.id()")
public Product updateProduct(String id, String title) {
    Product saved = repository.rename(id, title);
    validateAfterWrite(saved);  // có thể ném ngoại lệ
    return saved;
}
```

*Đoạn này minh họa, chưa chạy độc lập.*

Nếu `validateAfterWrite` ném runtime exception, transaction manager thông thường có thể đánh dấu rollback và không commit thay đổi database. Còn cache put của `@CachePut` sẽ không thực hiện vì method ném exception.

Nhưng cần phân biệt **phương thức hoàn thành** và **transaction đã commit**:

- `@CachePut` được xử lý bởi cache advice; `@Transactional` bởi transaction advice. Thứ tự advice và cách cache manager phối hợp transaction **ảnh hưởng thời điểm put so với commit**.
- Không mặc định rằng chỉ cần gắn hai annotation là có một giao dịch nguyên tử bao trùm cả database và Redis.
- Nếu method trả bình thường nhưng commit sau đó thất bại, một cache put được thực hiện quá sớm có thể đã chứa giá trị của transaction chưa commit.
- Khi cần cache chỉ cập nhật **sau commit**, cân nhắc cache manager có khả năng transaction-aware (ví dụ `TransactionAwareCacheManagerProxy` hoặc lựa chọn phù hợp của provider), đăng ký hành động sau commit, hoặc mô hình outbox/invalidation có điều phối. Phải kiểm tra cả concurrency, khả năng retry và failure mode của hệ thống.

**Các quy tắc rollback cũng không đồng nhất:** mặc định `@Transactional` thường rollback với unchecked exception (`RuntimeException`) và `Error`; checked exception thường cần cấu hình `rollbackFor` nếu muốn rollback. Nếu method đã bắt lỗi và trả bình thường thì transaction có thể commit (trừ khi bị đánh dấu rollback-only). Vì vậy hành vi database và cache cần được xác định bằng transaction policy thực tế, không suy đoán chỉ từ từ khóa `throw`.

## 9. Phân biệt lỗi nghiệp vụ và lỗi tầng cache

Có ít nhất ba vị trí phát sinh lỗi:

| Lỗi xuất hiện ở đâu? | Method đích đã chạy? | Cache entry và kết quả |
| --- | --- | --- |
| Trong method, **trước khi trả về** | Có, nhưng thất bại | `@CachePut` không ghi kết quả từ lần gọi đó |
| Trong expression/key hoặc trong `Cache.put` **sau khi method trả về** | Method có thể đã chạy xong | Put có thể thất bại; trạng thái entry phụ thuộc tiến độ/lỗi của provider |
| Trong các advice/logic khác trước hoặc sau method | Phụ thuộc thứ tự áp dụng | Cần trace stack và điểm lỗi để kết luận |

Spring Cache có cơ chế xử lý lỗi của cache provider, như `CacheErrorHandler` khi áp dụng. Cấu hình mặc định thường truyền lỗi của các thao tác cache, nhưng ứng dụng có thể dùng handler riêng để bỏ qua hoặc ghi nhận lỗi. **Đừng nhầm lỗi cache store với exception nghiệp vụ của method.**

Ví dụ phương thức đã cập nhật database và trả `Product` thành công, nhưng Redis bị lỗi mạng khi `put`:

- Có thể cache vẫn chưa cập nhật, dù database đã thay đổi.
- Caller có thể nhận exception từ tầng cache, tùy cách xử lý lỗi.
- Retry toàn bộ thao tác một cách mù quáng có thể tạo side effect lặp (ví dụ tạo đơn, tăng version, gửi sự kiện).

Hệ thống cần xử lý idempotency, retry có kiểm soát và quan sát telemetry. Không nên chỉ nhìn loại exception mà kết luận “method chưa chạy”; hãy theo dõi log điểm bắt đầu/kết thúc method, database transaction và cache operation.

## 10. Có nên xóa cache khi cập nhật thất bại?

Không có một đáp án áp dụng mọi hệ thống. Xóa cache phụ thuộc **dữ liệu nguồn thực sự thay đổi hay chưa**.

**Trường hợp A — transaction rollback hoàn toàn:** dữ liệu nguồn vẫn là phiên bản cũ. Cache cũ có thể vẫn đúng; không cần xóa chỉ vì một exception đã xuất hiện.

**Trường hợp B — thay đổi dữ liệu đã commit hoặc side effect tồn tại dù method lỗi:** cache cũ có thể đã sai. Cần cơ chế xác định trạng thái thật và invalidation/cập nhật phù hợp. Ví dụ dùng một service điều phối cập nhật và xóa đúng key sau khi biết commit thành công, hoặc một cơ chế đồng bộ sự kiện đáng tin cậy.

**Trường hợp C — kết quả cập nhật không xác định (timeout gọi dịch vụ ngoài):** không nên tự cho rằng thất bại đồng nghĩa “chưa có thay đổi”. Có thể phải kiểm tra lại nguồn, dùng mã yêu cầu idempotent hoặc làm mới cache theo chính sách an toàn.

So sánh nhanh với `@CacheEvict`:

- `@CachePut`: mục đích là **ghi kết quả mới**; khi method throw, không có kết quả bình thường để put.
- `@CacheEvict(beforeInvocation = false)`: mặc định xóa **sau khi method hoàn thành thành công**; method throw thì không có eviction hậu xử lý.
- `@CacheEvict(beforeInvocation = true)`: xóa **trước khi chạy method**, nên vẫn có thể xóa dù method sau đó ném exception.

Không tùy tiện dùng `beforeInvocation=true` để “chữa” mọi tình huống: nó có thể xóa cache ngay cả khi dữ liệu nguồn không hề thay đổi, làm tăng số lượt miss hoặc gây hành vi không mong muốn. Chọn chính sách dựa trên tính nhất quán cần đạt.

## 11. Những lỗi thường gặp khi sử dụng `@CachePut`

1. **Cho rằng cache hit sẽ ngăn update.** `@CachePut` luôn thực thi method được intercept; không giống `@Cacheable`.
2. **Kỳ vọng exception tự động xóa cache cũ.** Không; `@CachePut` không tự evict entry chỉ vì method lỗi.
3. **Kỳ vọng exception tự rollback database.** Rollback là trách nhiệm của transaction/cơ sở dữ liệu, không phải của `@CachePut`.
4. **Bắt ngoại lệ rồi trả placeholder nhưng vẫn put vào cache.** Với return bình thường, `@CachePut` có thể cache placeholder; dùng `unless` hoặc hợp đồng lỗi rõ ràng.
5. **Đặt `key="#result.id()"` nhưng nghĩ key vẫn tính được sau khi method throw.** Không có result thành công để ghi mới.
6. **Dùng cache key đọc/ghi không tương thích.** Nếu đọc theo `"P1"` nhưng put theo object khác kiểu, phương thức đọc có thể hit entry cũ khác key hoặc miss.
7. **Đặt `@CachePut` vào method không được Spring proxy intercept.** Self-invocation (`this.rename(...)`) hoặc tạo object bằng `new` trong proxy mode mặc định có thể bỏ qua cache advice; kết quả thành công cũng không được put.
8. **Dựa vào `condition`/`unless` để bắt exception.** Chúng quyết định cache operation, không phải Java exception handlers.
9. **Cho rằng đã ghi cache thì transaction đã commit.** Thứ tự advice và transaction awareness cần được kiểm chứng.
10. **Retry cập nhật không idempotent khi thấy exception từ cache.** Method có thể đã thực hiện side effect thành công trước khi phần ghi cache thất bại.
11. **Đánh đồng mọi kiểu trả về là đồng bộ.** Với `CompletableFuture` hoặc reactive return type, Spring Framework 6.1+ có hỗ trợ cập nhật cache khi giá trị được tạo ra; cần xem phiên bản framework, adapter và cách biểu diễn completion/failure trước khi áp dụng máy móc sơ đồ đồng bộ của bài này.

## 12. Cách chẩn đoán trong dự án thật

Khi một API update có `@CachePut` trả lỗi nhưng dữ liệu đọc vẫn cũ, kiểm tra theo thứ tự:

1. **Lời gọi có đi qua Spring bean proxy không?** Xác nhận `@EnableCaching` (hoặc cấu hình cache tương ứng), Spring-managed bean và không có self-invocation.
2. **Method có thực sự được gọi?** Đặt log tại điểm bắt đầu, trước/sau repository, trước return và trước throw.
3. **Ngoại lệ xuất hiện ở đâu?** Phân biệt exception trong method với lỗi key SpEL, serialization, backend cache hoặc advice khác.
4. **Giao dịch đã commit hay rollback?** Không nhìn mỗi response HTTP; kiểm tra transaction logs và trạng thái database.
5. **Entry cũ còn không?** Dùng metrics/cache provider để kiểm tra tên cache và key cụ thể, tránh xóa toàn bộ cache tùy tiện.
6. **Điều kiện cache đã thỏa?** `condition` và `unless` có thể ngăn put **ngay cả khi method trả bình thường**.
7. **Key có trùng giữa read và update?** So sánh SpEL và kiểu dữ liệu, bao gồm tenant/locale/version khi liên quan.
8. **Có concurrent writer hoặc TTL/eviction?** Tránh kết luận từ một request đơn lẻ khi hệ thống nhiều instance.
9. **Có cơ chế khôi phục sau failure không?** Xác định khi nào evict/refresh, chỉ sau khi biết dữ liệu thực tế ở trạng thái nào.

### Checklist thiết kế

- **Operation có thể ném exception:** mô tả rõ thay đổi nào được rollback và thay đổi nào cần bù.
- **Cache put key ổn định:** key ghi và key đọc cùng ý nghĩa, cùng namespace.
- **Không cache kết quả lỗi bình thường:** dùng `unless`/kiểu kết quả rõ ràng.
- **Cập nhật sau commit nếu cần:** chọn transaction-aware caching/invalidation đáng tin.
- **Quan sát được:** có metrics cho method invocation, cache put/hit, transaction outcome và lỗi provider.
- **Có test cho cả đường thành công lẫn thất bại:** kiểm tra trạng thái cache và dữ liệu nguồn, không chỉ HTTP response.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Cache có `products["P1"] = "Old"`. Method `@CachePut` muốn cập nhật thành `"New"` nhưng ném `IllegalStateException` trước khi return. Cache có tự chứa `"New"` không?

**Đáp án:** Không. `@CachePut` không put kết quả cho lời gọi ném exception. Entry `"Old"` không tự bị xóa bởi annotation đó.

**Câu 2.** Method ghi database thành công, rồi một lời gọi dịch vụ ngoài ném exception. Database có chắc chắn rollback không?

**Đáp án:** Không thể kết luận chỉ từ `@CachePut`. Cần xem transaction có bao trùm thay đổi, exception có kích hoạt rollback, dữ liệu đã commit chưa và side effect ngoài transaction nào đã xảy ra.

**Câu 3.** Một method bắt exception nội bộ và trả về `Product("P1", "Fallback", 0)`. `@CachePut` có thể lưu `Fallback` không?

**Đáp án:** Có. Ở góc nhìn interceptor, method đã **trả về bình thường**; nếu cache condition/`unless` cho phép, fallback có thể được put.

**Câu 4.** Caller nhận exception sau update. Có thể khẳng định `@CachePut` không ghi gì vì method chắc chắn throw không?

**Đáp án:** Không. Exception có thể phát sinh **sau khi method hoàn thành**, chẳng hạn từ cache provider hoặc key expression. Phải xác định nguồn lỗi bằng log/stack trace.

**Câu 5.** `@CachePut(key="#result.id()")` có đánh giá thành công `#result.id()` sau khi method ném ngoại lệ không?

**Đáp án:** Không có giá trị return bình thường để tính khóa cache put trong trường hợp đó. Đổi sang `key="#p0"` cũng không khiến phương thức lỗi trở thành một lần put thành công.

## Tài liệu tham khảo

- Spring Framework Reference — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `@CachePut`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework Reference — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework Javadoc — `TransactionAwareCacheManagerProxy`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html
