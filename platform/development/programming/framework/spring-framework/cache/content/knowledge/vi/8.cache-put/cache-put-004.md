# Giữ thống nhất khóa giữa đọc và cập nhật với `@CachePut` trong Spring Cache

## 1. Mục tiêu và tình huống

Trong Spring Cache, `@Cacheable` đọc lại một kết quả đã lưu, còn `@CachePut` thực thi phương thức rồi cập nhật cache bằng **giá trị trả về**. Hai annotation chỉ phối hợp đúng khi chúng cùng trỏ đến **đúng mục cache**. Sau bài này, bạn sẽ biết cách thiết kế khóa chung, phân biệt khóa với tên cache, chọn giữa `@CachePut` và `@CacheEvict`, xử lý các chữ ký phương thức khác nhau và kiểm thử kết quả sau cập nhật.

Giả sử có sản phẩm `P1` trong tổ chức `acme`:

~~~text
find("acme", "P1")
    -> Product(name="Pen", version=1)

update("acme", "P1", "Blue Pen")
    -> Product(name="Blue Pen", version=2)

find("acme", "P1")
    -> phải trả Product(name="Blue Pen", version=2)
~~~

Nếu lời gọi `find` cuối vẫn trả phiên bản 1, nguyên nhân phổ biến là đường đọc và đường cập nhật tạo **khác khóa**, khác cache name, hoặc chưa làm mất hiệu lực entry cũ. Đây là vấn đề về ánh xạ lời gọi sang cache identity, không tự hết khi thêm TTL.

## 2. Thống nhất toàn bộ cache identity

Một mục cache được định danh về mặt logic bởi:

~~~text
(CacheManager hoặc backend, cacheName, key) -> value
~~~

Ví dụ cần thống nhất:

~~~text
READ:
  manager: mainCacheManager
  cache:   products
  key:     (acme, P1)
  value:   Product(..., version=1)

PUT:
  manager: mainCacheManager
  cache:   products
  key:     (acme, P1)
  value:   Product(..., version=2)
~~~

Sau `@CachePut`, cùng cặp tên cache/khóa phải trả phiên bản mới. Chỉ khai báo `cacheNames = "products"` ở cả hai method **chưa đủ**: có thể mỗi phương thức tính khóa theo cách khác nhau, hoặc hai `CacheManager` riêng biệt đều chứa cache cùng tên nhưng dữ liệu không chia sẻ.

| Thành phần | Điều kiện đồng nhất | Ví dụ sai |
| --- | --- | --- |
| Manager/Resolver | Cùng kho dữ liệu/cache có thể truy cập chung | Đọc Redis A nhưng ghi vào local ConcurrentMap |
| `cacheNames` | Đường đọc và put nhắm cùng vùng | Đọc `productsById`, ghi `products` |
| Key | Cùng kiểu, giá trị và quy tắc `equals/hashCode` | Đọc `SimpleKey(tenant,id)`, put `SimpleKey(tenant,id,name)` |
| Projection/value | Giá trị put tương thích với kiểu read mong đợi | Read `Product`, update trả `boolean` |
| Phạm vi nghiệp vụ | Gồm các yếu tố thực sự ảnh hưởng kết quả | Thiếu `tenantId`, `locale`, `viewerId` nếu chúng thay đổi kết quả |

Đừng chỉ so sánh chuỗi `key.toString()`: hai đối tượng Java khác kiểu có thể in giống nhau nhưng không bằng nhau. Với cache phân tán, còn phải xét serializer, tiền tố namespace và cách provider chuyển đối tượng key thành key vật lý.

## 3. Tại sao khóa mặc định thường gây lỗi cho read và update?

Nếu không cấu hình `key`/`keyGenerator`, Spring dùng `SimpleKeyGenerator`:

- Không có đối số: `SimpleKey.EMPTY`.
- Một đối số khác `null` và không phải mảng: chính đối tượng ấy.
- Hai đối số trở lên: một `SimpleKey` chứa toàn bộ đối số theo thứ tự.

Ví dụ sau có vấn đề dù cùng `cacheNames`:

~~~java
// Minh họa trên một service có repository và lớp Product.
@Cacheable(cacheNames = "products")
public Product find(String tenantId, String productId) {
    return repository.find(tenantId, productId);
}

@CachePut(cacheNames = "products")
public Product update(String tenantId, String productId, String newName) {
    return repository.update(tenantId, productId, newName);
}
~~~

Khóa thực tế về mặt logic:

~~~text
find("acme", "P1")
    -> SimpleKey("acme", "P1")

update("acme", "P1", "Blue Pen")
    -> SimpleKey("acme", "P1", "Blue Pen")
~~~

`@CachePut` đưa `Product` mới vào **mục khác** với mục đã được `find` cache. Lần `find` sau có thể hit entry cũ. Cần xây dựng một quy tắc khóa chỉ dựa trên **định danh kết quả**; ở đây là `(tenantId, productId)`. `newName` là nội dung cập nhật nên không được tham gia khóa sản phẩm.

Một sai lầm tương tự là `find(String id)` dùng key chuỗi `"P1"`, nhưng `update(ProductRequest dto)` mặc định dùng chính DTO làm key. Hai key không tự bằng nhau dù `dto.productId()` trả `"P1"`.

## 4. Quy tắc quan trọng: định nghĩa identity trước khi viết annotation

Trước khi viết `key="#p0"`, xác định hai lời gọi có thực sự có thể dùng chung một kết quả hay không.

| Operation | Dữ liệu đầu vào | Key mong muốn |
| --- | --- | --- |
| `find(tenantId, productId)` | Tổ chức, mã sản phẩm | `(tenantId, productId)` |
| `update(tenantId, productId, newName)` | Có thêm tên mới | `(tenantId, productId)` |
| `delete(tenantId, productId)` | Tổ chức, mã sản phẩm | `(tenantId, productId)` |
| `findBySku(tenantId, sku)` | Định danh kiểu SKU | Khác vùng hoặc khác namespace nếu khác ngữ nghĩa |
| `find(tenantId, productId, currency)` | Giá theo tiền tệ | Thêm currency nếu kết quả thay đổi |
| `list(tenantId, category, page)` | Kết quả danh sách | Key truy vấn riêng, không tự cập nhật khi put theo ID |

Thông tin ảnh hưởng **nội dung trả về** như tổ chức, nhóm quyền, locale, currency hay phiên bản projection phải được xét. Thông tin không ảnh hưởng kết quả như `requestId`, `traceId`, thời gian gọi hay `auditLogId` thường nên bỏ khỏi key. Không dựa vào định danh tenant do client tự khai báo khi thiếu kiểm tra quyền: cần xác minh scope trong logic nghiệp vụ trước khi trả dữ liệu, kể cả cache hit.

Tại thời điểm cập nhật, khóa định danh phải giữ nguyên. Nếu một thuộc tính **dùng làm key** có thể bị đổi, ví dụ SKU, bạn cần xóa hoặc di chuyển **key cũ** ngoài việc ghi key mới; một `@CachePut` vào key mới không tự dọn mục cũ.

## 5. Cách 1: dùng cùng biểu thức `key` (SpEL)

Nếu cả hai method nhận `tenantId` và `productId` tại hai vị trí đầu tiên, khai báo chung:

~~~java
// Đoạn minh họa trong lớp service, repository là phụ thuộc ứng dụng.
@Cacheable(cacheNames = "products", key = "#p0 + ':' + #p1")
public Product find(String tenantId, String productId) {
    return repository.find(tenantId, productId);
}

@CachePut(cacheNames = "products", key = "#p0 + ':' + #p1")
public Product update(String tenantId, String productId, String newName) {
    return repository.update(tenantId, productId, newName);
}
~~~

`#p0` là tham số thứ nhất, `#p1` là tham số thứ hai. `#a0`, `#a1` và `#root.args[0]`, `#root.args[1]` là các cách truy cập tương ứng. Biểu thức dùng tên `#tenantId` chỉ hoạt động khi metadata tên tham số được Spring phát hiện được; cách dùng chỉ số độc lập hơn với cấu hình biên dịch.

**Lưu ý về dấu phân cách:** nếu định danh có thể chứa `:`, `(tenant="a:b", id="c")` và `(tenant="a", id="b:c")` cùng cho `"a:b:c"`. Đây là va chạm khóa. Với input tổng quát, dùng cách mã hóa có escape/độ dài rõ ràng hoặc một đối tượng khóa cấu trúc bất biến.

Nếu thứ tự tham số khác, biểu thức phải thay đổi:

~~~java
// productId ở vị trí 0, tenantId ở vị trí 2.
@CachePut(cacheNames = "products", key = "#p2 + ':' + #p0")
public Product update(String productId, UpdateRequest request,
                      String tenantId) {
    return repository.update(tenantId, productId, request);
}
~~~

Đừng sao chép `#p0 + ':' + #p1` giữa các method có chữ ký khác nhau. Nếu nhiều method phải phối hợp, một `KeyGenerator` dùng chung hoặc hàm tạo key thuần thường dễ duy trì hơn.

## 6. Cách 2: một `KeyGenerator` chung cho read, put và evict

`KeyGenerator` nhận đối tượng đích, phương thức và các đối số:

~~~java
// Chữ ký giao diện Spring để tham khảo; không tạo lại trong dự án.
Object generate(Object target, java.lang.reflect.Method method,
                Object... params);
~~~

Một generator cho bài toán này chỉ lấy hai định danh đầu, bỏ qua `newName` hoặc metadata cập nhật:

~~~java
// Minh họa Bean trong lớp cấu hình có các import Spring tương ứng.
@Bean("productKeyGenerator")
KeyGenerator productKeyGenerator() {
    return (target, method, params) -> {
        if (params.length < 2
                || !(params[0] instanceof String tenant)
                || !(params[1] instanceof String id)) {
            throw new IllegalArgumentException("Expected tenantId and productId");
        }
        return new ProductKey(tenant, id);
    };
}

private record ProductKey(String tenantId, String productId) {}
~~~

`ProductKey` là Java record bất biến, có `equals()` và `hashCode()` theo hai trường. `method.getName()` **không** được cộng vào khóa trong ví dụ này: tên `find`, `update`, `delete` khác nhau, trong khi cả ba đều phải nhắm cùng mục. Tên phương thức chỉ có ý nghĩa khi bạn **chủ đích** phân tách các loại kết quả, và khi ấy cần chính sách invalidation riêng.

Dùng generator:

~~~java
// Mã minh họa vị trí annotation; thân method phụ thuộc repository.
@Cacheable(cacheNames = "products", keyGenerator = "productKeyGenerator")
public Product find(String tenantId, String productId) {
    return repository.find(tenantId, productId);
}

@CachePut(cacheNames = "products", keyGenerator = "productKeyGenerator")
public Product update(String tenantId, String productId, String newName) {
    return repository.update(tenantId, productId, newName);
}

@CacheEvict(cacheNames = "products", keyGenerator = "productKeyGenerator")
public void delete(String tenantId, String productId) {
    repository.delete(tenantId, productId);
}
~~~

`key` và `keyGenerator` là hai thuộc tính loại trừ nhau trong cùng một annotation. `@CacheConfig(cacheNames="products", keyGenerator="productKeyGenerator")` có thể khai báo mặc định ở cấp class, nhưng không tự kích hoạt caching trên các method. Dù dùng một generator chung, bạn phải kiểm tra mọi method đều có các tham số định danh đúng thứ tự/kiểu mà generator yêu cầu.

## 7. Ví dụ hoàn chỉnh có thể chạy với Java 17 và Spring Boot

Ví dụ dùng **JDK 17+, Maven, Spring Boot 3.3.5** và cache nội bộ `ConcurrentMapCacheManager`. Một `ConcurrentHashMap` giả lập nguồn dữ liệu; bộ đếm cho biết bao nhiêu lần `find` phải đọc nguồn. Bean `CatalogService` được gọi từ `CommandLineRunner` để Spring proxy xử lý annotation.

Cấu trúc thư mục:

~~~text
consistent-cache-key/
├── pom.xml
└── src/main/java/example/cache/
    ├── DemoApplication.java
    └── CatalogService.java
~~~

### `pom.xml`

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
    <artifactId>consistent-cache-key</artifactId>
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

### `src/main/java/example/cache/DemoApplication.java`

~~~java
package example.cache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean("productKeyGenerator")
    KeyGenerator productKeyGenerator() {
        return (target, method, params) -> {
            if (params.length < 2
                    || !(params[0] instanceof String tenant)
                    || !(params[1] instanceof String id)) {
                throw new IllegalArgumentException(
                        "Expected tenantId and productId");
            }
            return new ProductKey(tenant, id);
        };
    }

    private record ProductKey(String tenantId, String productId) {}

    @Bean
    CommandLineRunner demo(CatalogService catalog) {
        return args -> {
            System.out.println(catalog.find("acme", "P1"));
            System.out.println(catalog.find("acme", "P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            System.out.println(catalog.update("acme", "P1", "Blue Pen"));
            System.out.println(catalog.find("acme", "P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            System.out.println(catalog.find("beta", "P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            catalog.delete("acme", "P1");
            System.out.println(catalog.find("acme", "P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());
        };
    }
}
~~~

### `src/main/java/example/cache/CatalogService.java`

~~~java
package example.cache;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final ConcurrentMap<Identity, Product> store =
            new ConcurrentHashMap<>();
    private final AtomicInteger reads = new AtomicInteger();

    public record Product(String tenantId, String productId,
                          String name, int version) {}
    private record Identity(String tenantId, String productId) {}

    public CatalogService() {
        store.put(new Identity("acme", "P1"),
                new Product("acme", "P1", "Pen", 1));
        store.put(new Identity("beta", "P1"),
                new Product("beta", "P1", "Marker", 1));
    }

    @Cacheable(cacheNames = "products", keyGenerator = "productKeyGenerator")
    public Product find(String tenantId, String productId) {
        reads.incrementAndGet();
        return store.get(new Identity(tenantId, productId));
    }

    @CachePut(cacheNames = "products", keyGenerator = "productKeyGenerator")
    public Product update(String tenantId, String productId, String newName) {
        Identity identity = new Identity(tenantId, productId);
        return store.compute(identity, (key, previous) -> {
            if (previous == null) {
                throw new IllegalArgumentException("Product does not exist");
            }
            return new Product(tenantId, productId, newName,
                    previous.version() + 1);
        });
    }

    @CacheEvict(cacheNames = "products", keyGenerator = "productKeyGenerator")
    public void delete(String tenantId, String productId) {
        store.remove(new Identity(tenantId, productId));
    }

    public int sourceReads() {
        return reads.get();
    }
}
~~~

### Chạy và quan sát kết quả

Từ thư mục `consistent-cache-key`:

~~~bash
mvn -q spring-boot:run
~~~

Các dòng do `CommandLineRunner` in (log khởi động Spring có thể xuất hiện thêm):

~~~text
Product[tenantId=acme, productId=P1, name=Pen, version=1]
Product[tenantId=acme, productId=P1, name=Pen, version=1]
sourceReads=1
Product[tenantId=acme, productId=P1, name=Blue Pen, version=2]
Product[tenantId=acme, productId=P1, name=Blue Pen, version=2]
sourceReads=1
Product[tenantId=beta, productId=P1, name=Marker, version=1]
sourceReads=2
null
sourceReads=3
~~~

**Đọc từng bước:**

1. Lần đầu `find(acme,P1)` miss nên đọc nguồn (`sourceReads=1`) và cache `Pen/v1`. Lần thứ hai hit nên vẫn thấy `v1` mà bộ đếm không tăng.
2. `update(acme,P1,Blue Pen)` **luôn chạy** và trả `Blue Pen/v2`. `@CachePut` ghi kết quả mới dưới key `(acme,P1)`, vì generator bỏ qua tham số `newName`.
3. `find(acme,P1)` ngay sau update hit `v2` nên `sourceReads` vẫn bằng `1`. Đây là hành vi cần kiểm chứng khi xây dựng read/update.
4. `find(beta,P1)` khác tenant nên miss, trả `Marker/v1` và tăng số đọc lên `2`; không lấy nhầm kết quả Acme.
5. `delete(acme,P1)` xóa dữ liệu nguồn và `@CacheEvict` xóa đúng mục. Đọc lại miss, thấy `null`, số lần đọc tăng lên `3`. Theo cấu hình mặc định của `ConcurrentMapCacheManager`, kết quả `null` có thể được cache; chính sách negative caching là vấn đề riêng.

Ví dụ này dùng in-memory source và cache trong một JVM, chưa mô phỏng transaction database, TTL, nhiều replica hoặc concurrency thực. Những điều kiện đó cần kiểm thử thêm với provider lựa chọn.

## 8. Sử dụng `#result` trong `@CachePut` có đúng không?

Khác với `@Cacheable` phải tính key để **lookup trước khi chạy method**, `@CachePut` tính key trong ngữ cảnh sau khi method trả kết quả và có thể dùng biến SpEL `#result`.

~~~java
// Minh họa: Product có phương thức id(), SaveRequest do ứng dụng định nghĩa.
@CachePut(cacheNames = "productsById", key = "#result.id()")
public Product save(SaveRequest request) {
    return repository.save(request);
}

@Cacheable(cacheNames = "productsById", key = "#p0")
public Product findById(String id) {
    return repository.findById(id);
}
~~~

Nếu `save` trả một `Product` với `id() == "P1"`, phương thức `findById("P1")` và `save` có cùng key `"P1"` trong vùng `"productsById"`. Cách này hữu ích khi cơ sở dữ liệu tạo ID **sau khi lưu**.

Điều kiện để dùng an toàn:

- `id()` trả đúng **cùng kiểu** key mà phương thức đọc sử dụng (ví dụ đều `String`); record key và chuỗi không tự bằng nhau.
- Nếu dữ liệu có tenant/scope, key cũng cần chứa tenant/scope hoặc tên cache tách vùng phù hợp.
- `#result` có thể `null`; không gọi `#result.id()` khi chưa xác định kết quả hợp lệ. Thiết kế method trả object hợp lệ hoặc exception, hoặc áp dụng điều kiện phù hợp và kiểm thử.
- `#result` trong `@CachePut` tham chiếu giá trị sau khi method hoàn thành; wrapper hỗ trợ như `Optional` được xử lý theo ngữ nghĩa cache abstraction.
- Nếu rename đổi từ ID cũ sang ID mới, put bằng ID mới **không xóa key cũ**.

Một `@Cacheable(key="#result.id()")` là sai ý tưởng, vì trước khi lookup method chưa có kết quả mới. Đường đọc phải xây identity từ input hoặc context sẵn có. Cũng không nên gắn `@Cacheable` và `@CachePut` trên cùng một method: cái thứ nhất có thể bỏ qua method khi hit, cái thứ hai đòi method luôn thực thi.

## 9. `@CachePut` không phải lúc nào cũng tốt hơn `@CacheEvict`

Với update trả **đúng một DTO hoàn chỉnh** mà read cần, `@CachePut` giúp lần đọc sau thấy kết quả mới ngay mà không cần truy vấn lại nguồn. Nhưng nếu update chỉ trả một status, payload hoặc kết quả không phải projection của read, put có thể khiến cache sai loại dữ liệu.

~~~java
// Phản ví dụ: update trả boolean, còn find mong Product.
@CachePut(cacheNames = "products", key = "#p0")
public boolean updateName(String productId, String name) {
    return repository.updateName(productId, name);
}
~~~

Ở đây `Boolean` bị đưa vào cache có thể được `find` đọc như `Product`, gây lỗi. Nếu method chỉ trả `boolean`/`void`, thường nên `@CacheEvict`:

~~~java
// Minh họa: chỉ xóa cache sau khi thao tác update thành công.
@CacheEvict(cacheNames = "products", key = "#p0")
public void updateName(String productId, String name) {
    repository.updateName(productId, name);
}
~~~

Đoạn minh họa giả định key là `productId` và không có nhiều tenant; trong hệ thống thực vẫn cần thống nhất identity với read.

| Kết quả update | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| DTO mới đầy đủ, cùng projection read | `@CachePut` | Có thể thay entry đúng nội dung |
| Không có DTO mới, chỉ `void`/`boolean` | `@CacheEvict` | Read sau đó nạp lại kiểu dữ liệu chính xác |
| Một update ảnh hưởng nhiều view | Put vùng chắc chắn, evict các vùng phụ thuộc | Tránh giữ cache danh sách/chi tiết stale |
| Tài nguyên đổi ID hoặc chuyển tenant | Evict key cũ và put/evict key mới | Một put đơn lẻ không dọn key cũ |
| Kết quả đôi lúc `null` | Xác định rõ negative caching, veto và eviction | Không để entry cũ tồn tại ngoài ý muốn |

`@CacheEvict` mặc định xóa sau khi phương thức thành công. `beforeInvocation=true` đổi thời điểm thực hiện, cần lựa chọn theo chính sách khi thao tác nguồn thất bại. `allEntries=true` xóa toàn bộ vùng, bỏ qua key của từng mục. Trên cache dùng chung nhiều tenant, xóa toàn vùng có thể quá rộng.

Nếu dùng `@CachePut(unless="#result == null")`, biểu thức `unless` có thể **từ chối put** khi kết quả null, nhưng **không xóa entry cũ**. Nếu null biểu thị dữ liệu vừa bị xóa hoặc không còn hợp lệ, chỉ veto put có thể giữ dữ liệu stale; cần eviction theo key.

## 10. Đừng bỏ sót những cache chịu ảnh hưởng gián tiếp

Ví dụ product P1 xuất hiện trong:

~~~text
productsById(acme, P1)
productsByCategory(acme, stationery, page=0)
productsBySearch(acme, "pen", sort=price)
dashboardCounts(acme, today)
~~~

`@CachePut` vào `productsById(acme,P1)` **không làm mới tự động** các vùng khác. Nếu tên hoặc giá thay đổi, danh sách/search/thống kê có thể stale. Cần xác định các operation phụ thuộc và chọn chính sách:

- `@CacheEvict` đúng key của các kết quả bị ảnh hưởng nếu có thể xác định.
- `@Caching` để gom nhiều annotation khi một update cần tác động nhiều vùng đã biết.
- Evict toàn vùng có kiểm soát khi không thể liệt kê mọi key query.
- Sử dụng version, event invalidation, TTL hay cơ chế đồng bộ chuyên biệt theo yêu cầu nghiệp vụ.

Hai bản chiếu `ProductSummary` và `ProductDetail` cũng không nhất thiết dùng chung cache name/key; dù cùng sản phẩm, kiểu giá trị khác nhau. Hãy tách vùng/namespace và cập nhật hoặc xóa từng bản chiếu cần thiết.

## 11. Transaction, đồng thời và cache phân tán

Đồng nhất key **chưa bảo đảm** database và cache luôn nhất quán khi có nhiều thread hoặc rollback.

Một race có thể xảy ra:

~~~text
T1: Reader A bắt đầu lấy product v1 từ database (chưa put).
T2: Writer B ghi product v2 vào database rồi put v2 vào cache.
T3: Reader A hoàn tất chậm, put v1 vào cùng key.
T4: Lời gọi sau có thể hit v1 dù DB hiện là v2.
~~~

`@CachePut` không tự cung cấp tính nguyên tử giữa database và cache. Cần kiểm tra yêu cầu nhất quán, cấu hình transaction, thứ tự advice và provider thực. Có thể dùng phiên bản dữ liệu/optimistic locking, chính sách ghi sau commit, transaction-aware cache manager, event `AFTER_COMMIT` hoặc outbox nếu nghiệp vụ đòi hỏi. Đừng giả định gọi method có `@Transactional` thì mọi cache put mặc định sẽ chờ commit.

Với nhiều replica JVM, `ConcurrentMapCacheManager` của ví dụ là **cục bộ từng instance**; put ở một JVM không tự cập nhật JVM khác. Nếu chuyển sang Redis hoặc cache phân tán, cần kiểm chứng serializer, key codec, namespace, TTL và khả năng quan sát cùng cache qua nhiều instance. Tránh dùng object mutable hoặc hash code trần làm key.

Với dữ liệu liên quan phân quyền, key chứa đúng tenant/user không thay cho kiểm tra quyền mỗi request. `@Cacheable` có thể trả cache hit mà không chạy method; không đặt kiểm tra quyền duy nhất trong thân method đọc rồi cho rằng luôn được thực thi.

## 12. Bộ kiểm thử cần có

Đừng chỉ kiểm tra rằng hai annotation có cùng `cacheNames`; kiểm thử **hành vi sau cập nhật** qua Spring-managed proxy.

| Ca kiểm thử | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Hit bình thường | `find(acme,P1)` hai lần | Source chỉ đọc một lần |
| Put cùng identity | `update(acme,P1,newName)` rồi `find(acme,P1)` | Giá trị mới xuất hiện, source không đọc thêm |
| Khác tenant | `find(beta,P1)` | Không nhận bản cập nhật của Acme |
| Thêm tham số update | `update(acme,P1,newName,auditId)` | Không đổi key nếu auditId không ảnh hưởng dữ liệu |
| Evict | `delete(acme,P1)` rồi `find(acme,P1)` | Không nhận entry đã xóa |
| Cùng tên nhưng khác manager | Put vào manager A, đọc manager B | Không được giả định chung dữ liệu |
| Sai kiểu | Update trả Boolean, read cần Product | Phát hiện sai lựa chọn put/evict |
| Lỗi update | Phương thức ném exception | Không có kết quả cập nhật thành công để put |
| Transaction rollback | Dữ liệu nguồn không commit | Cache không được để lộ dữ liệu chưa commit |
| Race read/write | Read chậm và update chạy đồng thời | Bảo đảm đúng mức nhất quán đã công bố |

Với ví dụ chạy được, quan sát `sourceReads` là test hữu ích: sau lần đầu, `update` tăng version, còn `find` kế tiếp vẫn giữ số lần đọc nguồn bằng `1`, chứng minh cache đã chứa DTO mới. Có thể viết integration test với `@SpringBootTest` và `CacheManager`, nhưng nên dùng cùng key factory chính thức nếu kiểm tra trực tiếp một entry; đừng tự dựng key có kiểu khác.

Trong hệ thống thực tế, cần thêm test trên provider mà production dùng, đặc biệt khi key là record hoặc đối tượng phức tạp; cách chuyển đổi key trong Redis/Caffeine có thể khác nhau.

## 13. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
| --- | --- | --- |
| Cập nhật thành công, đọc vẫn cũ | Update có payload trong key mặc định | So sánh key logic của read và put |
| Generator chung nhưng key khác | Generator dùng `method.getName()` hoặc sai vị trí tham số | Kiểm tra các thành phần record/key |
| Hai key in giống nhau nhưng miss | Khác kiểu, thiếu `equals/hashCode` | So sánh key object và serializer |
| Cùng key nhưng không thấy update | Khác cache name, manager/resolver/backend | Log có kiểm soát cacheName, manager, key |
| Product bị biến thành Boolean | `@CachePut` trên method trả status | Dùng eviction hoặc trả DTO đầy đủ |
| Sai dữ liệu tenant | Key bỏ qua tenant hoặc scope | Cô lập identity và xác minh quyền |
| `@CachePut` không kích hoạt | Thiếu `@EnableCaching`, self-invocation, bean không do Spring quản lý | Gọi qua bean proxy từ nơi khác |
| Cache chi tiết mới nhưng trang list cũ | Chỉ put một entry theo ID | Evict/version các cache truy vấn liên quan |
| Put v2 nhưng sau đó thấy v1 | Race hoặc cache ghi trước rollback | Kiểm tra transaction/đồng thời/version |
| Key thay đổi sau refactor | Sửa chữ ký method hoặc codec không đồng bộ | Dùng identity chung và có kế hoạch migration |

Trong proxy mode mặc định, gọi `this.update(...)` hoặc `this.find(...)` từ **chính bean** không đi qua cache interceptor. Mã chạy ở demo gọi `CatalogService` từ một bean khác (`CommandLineRunner`) để annotation có hiệu lực.

## 14. Bài tập tự kiểm tra

**Bài 1.** `find(String id)` dùng `"products"` và không khai báo `key`. `update(String id, String name)` dùng cùng vùng và cũng không khai báo `key`. Vì sao có thể stale?  
**Đáp án:** `find` mặc định dùng key chuỗi `id`, `update` dùng `SimpleKey(id,name)`. Cần một key chung chỉ theo định danh dữ liệu.

**Bài 2.** Reader dùng `(tenantId,productId)`, updater dùng `(productId,tenantId)`. Hai tuple có thể coi là bằng nhau không?  
**Đáp án:** không; thứ tự thành phần tham gia `equals`. Hãy chuẩn hóa thứ tự và kiểu trong một key factory hoặc generator.

**Bài 3.** `@CachePut(key="#result.id()")` có thể phù hợp khi nào?  
**Đáp án:** khi ID đáng tin chỉ có sau khi save trả kết quả và reader dùng cùng cache name, cùng kiểu key. Với nhiều tenant phải bổ sung scope.

**Bài 4.** `updateName` chỉ trả `boolean`. Có nên put giá trị đó vào cache mà `findById` trả `Product` không?  
**Đáp án:** không. Dùng `@CacheEvict` hoặc sửa update trả `Product` đầy đủ.

**Bài 5.** `@CachePut` ghi đúng bản chi tiết P1. Vì sao kết quả `searchProducts` vẫn có thể cũ?  
**Đáp án:** cache truy vấn có key và vùng riêng. Cần invalidation cho các projection chịu ảnh hưởng.

**Bài 6.** Một generator thêm tên method vào key cho cả `find` và `update`. Kết quả?  
**Đáp án:** hai method có tên khác nhau, nên key không bằng nhau; put không thay mục mà read đang dùng.

## Tài liệu tham khảo chính thức

- Spring Framework – Declarative Annotation-based Caching (`@Cacheable`, `@CachePut`, `@CacheEvict`, key generation, `@CacheConfig`, proxy): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework – `@CachePut` Javadoc, `key`, `#result`, `unless`: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Boot – Caching provider configuration: https://docs.spring.io/spring-boot/reference/io/caching.html

**Ghi nhớ:** `@Cacheable` và `@CachePut` phải đồng nhất **manager/backend, cache name, kiểu/giá trị key và projection được lưu**. Khóa nên dựa trên định danh nghiệp vụ ổn định; kiểm thử bằng cách cập nhật rồi đọc lại qua Spring proxy, đồng thời có kế hoạch invalidation cho các kết quả phụ thuộc.