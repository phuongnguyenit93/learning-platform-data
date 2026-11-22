# Dùng `key` để chọn đối số hoặc thuộc tính của đối số trong Spring Cache (SpEL)

## 1. Bài toán: nhiều tham số nhưng chỉ một phần quyết định dữ liệu

Trong Spring Framework, `@Cacheable` thường lấy kết quả của một phương thức để lưu vào cache. Cache cần một **khóa (cache key)** để phân biệt các lời gọi nào có thể dùng chung kết quả. Nếu hai lời gọi có cùng tên vùng cache và cùng key, một lần gọi sau có thể nhận ngay kết quả đã lưu mà không chạy phương thức thật.

Ví dụ:

```java
Product findProduct(String sku, String requestId)
```

Nếu `sku` xác định sản phẩm còn `requestId` chỉ để theo dõi yêu cầu, hai lượt gọi có cùng `sku` nhưng khác `requestId` nên nhận cùng dữ liệu. Có thể chọn riêng `sku` làm key, tránh tạo nhiều entry không cần thiết cho cùng sản phẩm.

Ngược lại:

```java
Price findPrice(String sku, String currency)
```

Giá trả về phụ thuộc cả `sku` lẫn `currency`; chọn mỗi `sku` làm key sẽ có nguy cơ trả giá USD cho yêu cầu VND. Quy tắc trung tâm là:

> **Đưa vào key tất cả yếu tố làm thay đổi kết quả cần cache, và bỏ những tham số thực sự không làm thay đổi kết quả.**

Bài này tập trung vào cách dùng thuộc tính `key` của các annotation Spring Cache để **chọn đối số, đọc thuộc tính/field, gọi accessor, truy cập phần tử lồng nhau và tạo key từ nhiều thành phần bằng SpEL**.

## 2. `key` là một biểu thức SpEL, không phải tên biến Java thuần túy

Cú pháp:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) { /* ... */ }
```

Trong annotation này:

- `cacheNames="products"` chọn **vùng cache**. Tên vùng và giá trị key cùng nhau quyết định vị trí logic của entry.
- `key="#p0"` là biểu thức **Spring Expression Language (SpEL)**. Dấu `#` tham chiếu biến trong ngữ cảnh đánh giá biểu thức, ở đây `p0` là đối số thứ nhất (chỉ số bắt đầu từ 0).
- Giá trị key được tính tại thời điểm gọi phương thức qua Spring caching interceptor, **không** phải chuỗi ký tự `"#p0"` được dùng làm khóa.
- Không cần viết `#{...}` bao quanh biểu thức trong thuộc tính `key`. Ví dụ `key="#p0"` là đúng; `key="'#p0'"` tạo chuỗi literal `#p0` và có thể làm mọi request đụng cùng một key.

Nếu bỏ thuộc tính `key`, Spring dùng `KeyGenerator` mặc định: không tham số → `SimpleKey.EMPTY`; một tham số → chính tham số đó; nhiều tham số → `SimpleKey` chứa toàn bộ tham số. Điều này có thể tạo nhiều key không cần thiết nếu có metadata thừa, hoặc phụ thuộc vào cách đối tượng cài đặt `equals()/hashCode()`.

**Điểm cần nhớ:** tùy biến `key` điều chỉnh tính đồng nhất của lời gọi. Nó không thay đổi dữ liệu được lấy từ nguồn và cũng không tự làm mới entry khi dữ liệu gốc thay đổi.

## 3. Chọn một đối số bằng tên hoặc vị trí

Các cách tham chiếu sau đều được Spring hỗ trợ trong ngữ cảnh cache:

| Biểu thức SpEL | Chọn gì? | Khi nên dùng |
| --- | --- | --- |
| `#sku` | Đối số có tên Java `sku` | Khi tên tham số có sẵn ở runtime |
| `#p0` | Đối số thứ nhất | Ổn định ngay cả khi runtime không lấy được tên |
| `#a0` | Đối số thứ nhất | Alias tương đương `#p0` |
| `#p1` hoặc `#a1` | Đối số thứ hai | Chỉ lấy tham số thứ hai làm key |
| `#root.args[0]` | Phần tử thứ nhất của mảng arguments | Diễn tả tường minh qua root context |
| `#root.args[1]` | Phần tử thứ hai | Hữu ích khi cần đọc theo vị trí |

Ví dụ hai cách trỏ cùng một tham số:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku, String requestId) {
    return repository.findBySku(sku);
}

@Cacheable(cacheNames = "products", key = "#sku")
public Product findBySku(String sku, String requestId) {
    return repository.findBySku(sku);
}
```

Hai ví dụ trên là **mảnh minh họa trong service đã có `repository`**, không phải hai phương thức cần chép nguyên vào chương trình chạy bên dưới. Chúng có thể dùng chung entry vì cùng region `products` và cùng key SKU, miễn là trả về cùng kiểu và cùng ý nghĩa dữ liệu.

Với `#sku`, Spring cần biết tên tham số khi chạy; trong Java nên biên dịch có cờ `-parameters` (ví dụ cấu hình `<maven.compiler.parameters>true</maven.compiler.parameters>`). Nếu thiếu tên tham số, biểu thức có thể không đánh giá đúng. `#p0`/`#a0` không phụ thuộc cờ này. **Đừng nhầm `#p1` với tham số thứ nhất.** Chỉ số bắt đầu ở 0.

Ví dụ chọn đúng đối số thứ hai:

```java
@Cacheable(cacheNames = "products", key = "#p1")
public Product lookup(String requestId, String sku) {
    return repository.findBySku(sku);
}
```

Với `lookup("trace-A", "P1")` và `lookup("trace-B", "P1")`, cả hai đánh giá được key `"P1"`. Nếu dùng `#p0`, chúng lại có hai key khác nhau (`"trace-A"` và `"trace-B"`) dù muốn cache theo sản phẩm.

**Điều kiện để bỏ qua một đối số:** đối số bị bỏ qua thật sự không ảnh hưởng đến giá trị phương thức trả về, quyền truy cập, tenant, locale, trạng thái phiên hay các ràng buộc an toàn. Nếu method còn dùng metadata đó để ghi log hoặc side effect, lưu ý cache hit có thể **bỏ qua toàn bộ thân method**, nghĩa là side effect ấy cũng không chạy.

## 4. Chọn thuộc tính hoặc accessor của một đối số

Khi method nhận một request object, cache theo **toàn bộ object** có thể không tối ưu, nhất là nếu object chứa trace ID, timestamp hoặc thông tin không ảnh hưởng tới kết quả. SpEL có thể lấy một thuộc tính bên trong object.

### 4.1. JavaBean với getter

```java
public class ProductQuery {
    private final String sku;
    private final String requestId;

    public ProductQuery(String sku, String requestId) {
        this.sku = sku;
        this.requestId = requestId;
    }
    public String getSku() { return sku; }
    public String getRequestId() { return requestId; }
}

@Cacheable(cacheNames = "products", key = "#p0.sku")
public Product find(ProductQuery query) {
    return repository.findBySku(query.getSku());
}
```

`#p0.sku` đọc property `sku` theo quy ước JavaBean, thông qua getter `getSku()`. Không cần cho field là `public`.

### 4.2. Java record với accessor rõ ràng

```java
public record ProductQuery(String sku, String requestId) {}

@Cacheable(cacheNames = "products", key = "#p0.sku()")
public Product find(ProductQuery query) {
    return repository.findBySku(query.sku());
}
```

Record sinh phương thức `sku()`, vì vậy có thể gọi **accessor method** trong SpEL bằng `#p0.sku()`. Cách viết này cũng thể hiện rõ khác biệt giữa truy cập property và gọi method. Đừng giả định mọi cấu trúc Java đều có getter `getSku()`.

### 4.3. Thuộc tính lồng nhau

Giả sử:

```java
record Customer(String id) {}
record OrderQuery(Customer customer, String orderId) {}
```

Key là mã khách hàng:

```java
@Cacheable(cacheNames = "ordersByCustomer", key = "#p0.customer().id()")
public java.util.List<Order> findOrders(OrderQuery query) {
    return repository.findByCustomerId(query.customer().id());
}
```

Truy cập đi từng bước: `#p0` → `customer()` → `id()`. Tuy nhiên, nếu phương thức trả về **danh sách đơn hàng** còn phụ thuộc filter, trang, quyền người dùng hoặc khoảng thời gian, chỉ mã khách hàng là **chưa đủ**. Phải đưa thêm các yếu tố ảnh hưởng kết quả vào key.

### 4.4. Map và index

Với đối số kiểu `Map<String, String>`:

```java
@Cacheable(cacheNames = "products", key = "#p0['sku']")
public Product find(Map<String, String> params) {
    return repository.findBySku(params.get("sku"));
}
```

Dấu `['sku']` truy cập entry theo key của Map. Với `List` hoặc mảng, có thể lấy vị trí: `#p0[0]`. Đây là lựa chọn khi dữ liệu đầu vào có cấu trúc phù hợp; vẫn phải kiểm tra khóa tồn tại và kiểu dữ liệu.

### 4.5. Null và navigation

`#p0.customer().id()` sẽ lỗi khi `query.customer() == null`. SpEL có toán tử truy cập an toàn `?.`, ví dụ `#p0.customer()?.id()`, nhưng **trả ra null không tự trở thành một key hợp lệ**: Spring Cache thông thường yêu cầu key khác null. Nếu mã khách hàng bắt buộc, nên kiểm tra/đảm bảo tính hợp lệ của đối số trước khi đi qua cache interceptor, hoặc thiết kế biểu thức trả key dự phòng không gây trùng dữ liệu. Đừng dùng một giá trị mặc định như `"unknown"` để vô tình gom các khách hàng khác nhau vào cùng một entry.

## 5. Chọn nhiều thuộc tính để tạo key tổng hợp

Giả sử `findPrice(PriceQuery query)` trả giá khác nhau theo tenant, SKU và đơn vị tiền tệ:

```java
public record PriceQuery(String tenantId, String sku, String currency) {}

@Cacheable(
    cacheNames = "prices",
    key = "#p0.tenantId() + ':' + #p0.sku() + ':' + #p0.currency()"
)
public Price findPrice(PriceQuery query) {
    return priceRepository.find(
        query.tenantId(), query.sku(), query.currency());
}
```

Đây là mảnh minh họa, với `Price` và `priceRepository` do ứng dụng thực tế cung cấp. Key của yêu cầu `("T1", "P1", "VND")` là `"T1:P1:VND"`. Nếu đổi currency hoặc tenant, key phải khác.

**Giới hạn của cách nối chuỗi:** nếu một thành phần có thể chứa dấu phân cách `:`, các bộ dữ liệu khác nhau đôi khi tạo cùng key (ví dụ `("a:b", "c")` và `("a", "b:c")` khi nối hai phần). Với dữ liệu không được kiểm soát, nên dùng mã hóa không nhập nhằng hoặc một `KeyGenerator` riêng tạo khóa có cấu trúc như `SimpleKey(tenantId, sku, currency)`. Cần bảo đảm key có `equals()/hashCode()` ổn định và tương thích serialization của provider (đặc biệt cache phân tán).

Một key tổng hợp cũng có thể kết hợp **hai đối số khác nhau**:

```java
@Cacheable(
    cacheNames = "prices",
    key = "#p0 + ':' + #p1"
)
public Price findPrice(String sku, String currency) {
    return priceRepository.find(sku, currency);
}
```

Nếu method đã nhận cả `tenantId`, phải bổ sung nó vào key; **không** chỉ dựa vào hai tham số `sku` và `currency` khi giá còn phụ thuộc tenant. Ví dụ về hai đối số trên giả định giá không phân biệt tenant và các chuỗi thành phần đã được giới hạn để không thể chứa dấu phân cách.

Đối với đối số kiểu tham chiếu, key mặc định dùng cả object có thể có vấn đề: hai instance chứa cùng SKU nhưng không có `equals()/hashCode()` theo giá trị sẽ thành hai key khác nhau trong cache local; khi key được lấy bằng `#p0.sku()`, cả hai cùng trở về key SKU ổn định. Tương tự, không nên đưa chính đối tượng có thể bị sửa đổi (mutable) vào key.

## 6. Ví dụ chạy được: chọn đối số thứ hai và thuộc tính của đối số đầu tiên

Chương trình Java 17 dưới đây có hai cache region để tách riêng hai hợp đồng chọn key:

- `namesBySku`: `byLookup(Lookup request)` dùng `#p0.sku()`. Khác `traceId` vẫn hit cùng SKU.
- `namesById`: `byId(String traceId, String sku)` dùng `#p1`. Giá trị đối số thứ hai mới là key.
- `invalidate(Lookup request)` dùng **cùng biểu thức key** với `byLookup` để xóa đúng entry.

Hai region được tách riêng để số lần đọc nguồn và luồng kiểm tra dễ thấy, không phải vì bản thân SpEL cần nhiều region.

**Cấu trúc tệp:**

```text
cache-spel-key/
├── pom.xml
└── src/main/java/CacheKeySpelDemo.java
```

**`pom.xml`** (Spring Framework 6.2.x, Java 17):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-spel-key</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/CacheKeySpelDemo.java`:**

```java
import java.util.Map;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheKeySpelDemo {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("namesBySku", "namesById");
    }

    @Bean
    CatalogService catalogService() {
        return new CatalogService();
    }

    public record Lookup(String sku, String traceId) {}

    public static class CatalogService {
        private final Map<String, String> names =
                Map.of("P1", "Bút", "P2", "Sổ");

        private int sourceReads = 0;

        @Cacheable(cacheNames = "namesBySku", key = "#p0.sku()")
        public String byLookup(Lookup request) {
            sourceReads++;
            return names.get(request.sku());
        }

        @Cacheable(cacheNames = "namesById", key = "#p1")
        public String byId(String traceId, String sku) {
            sourceReads++;
            return names.get(sku);
        }

        @CacheEvict(cacheNames = "namesBySku", key = "#p0.sku()")
        public void invalidate(Lookup request) {
            // Ví dụ: một thao tác làm mất hiệu lực dữ liệu theo SKU.
        }

        public int sourceReads() {
            return sourceReads;
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(CacheKeySpelDemo.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("Query trace 1: " +
                    service.byLookup(new Lookup("P1", "trace-001")));
            System.out.println("Query trace 2: " +
                    service.byLookup(new Lookup("P1", "trace-002")));
            System.out.println("Query P2: " +
                    service.byLookup(new Lookup("P2", "trace-003")));
            System.out.println("Reads query: " + service.sourceReads());

            System.out.println("Positional arg 1: " +
                    service.byId("trace-A", "P1"));
            System.out.println("Positional arg 2: " +
                    service.byId("trace-B", "P1"));
            System.out.println("Reads positional: " + service.sourceReads());

            service.invalidate(new Lookup("P1", "invalidate"));
            System.out.println("After eviction: " +
                    service.byLookup(new Lookup("P1", "trace-004")));
            System.out.println("Reads final: " + service.sourceReads());
        }
    }
}
```

Chạy ở thư mục `cache-spel-key` bằng JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=CacheKeySpelDemo
```

**Các dòng do chương trình in ra** (không tính log Maven/Spring do môi trường có thể cấu hình riêng):

```text
Query trace 1: Bút
Query trace 2: Bút
Query P2: Sổ
Reads query: 2
Positional arg 1: Bút
Positional arg 2: Bút
Reads positional: 3
After eviction: Bút
Reads final: 4
```

Giải thích:

1. `byLookup(P1, trace-001)` là cache miss đầu tiên: gọi nguồn một lần, lưu key `"P1"` trong `namesBySku`.
2. `byLookup(P1, trace-002)` dùng cùng `#p0.sku()` → hit, không tăng `sourceReads` dù record request khác.
3. `byLookup(P2, ...)` có key `"P2"` → miss, bộ đếm bằng 2.
4. `byId(trace-A, P1)` là miss trong **region khác**; `#p1` trỏ đúng SKU `"P1"`, tăng bộ đếm lên 3. `byId(trace-B, P1)` dùng lại entry đó.
5. `invalidate(P1)` xóa key `"P1"` trong `namesBySku`; `byLookup(P1, ...)` sau đó miss và gọi nguồn lần thứ 4.

Đây là ứng dụng console dùng `ConcurrentMapCacheManager` trong một JVM, không mô phỏng TTL hay cache phân tán. `CatalogService` là Spring bean; các lời gọi trong `main` đi qua proxy để kích hoạt annotation. Cố ý dùng `#p0`/`#p1` nên không phụ thuộc vào việc biên dịch có lưu tên tham số.

## 7. Kết hợp `key` với các annotation khác

Biểu thức `key` có mặt ở `@Cacheable`, `@CachePut`, `@CacheEvict`, nhưng thời điểm và tác dụng của mỗi annotation khác nhau:

| Annotation | Thời điểm chính | Điều cần thống nhất |
| --- | --- | --- |
| `@Cacheable` | Đánh giá key để tra cache trước khi quyết định chạy method | Các lần gọi trả cùng kết quả phải có cùng key |
| `@CachePut` | Method luôn chạy; sau đó đưa kết quả vào cache | Key khi ghi phải khớp key khi đọc |
| `@CacheEvict` | Xóa entry; mặc định sau khi method chạy thành công | Key khi xóa phải khớp key đã lưu; `allEntries=true` bỏ qua key |
| `condition` | Điều kiện để kích hoạt caching theo tham số/ngữ cảnh | Điều kiện khác với việc chọn key |
| `unless` trên `@Cacheable` | Kiểm tra kết quả sau khi chạy method để từ chối lưu | Không phải một phần của key |

Ví dụ hai method có **chữ ký khác nhau** nhưng thống nhất key SKU:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String sku) {
    return repository.findBySku(sku);
}

@CacheEvict(cacheNames = "products", key = "#p0.sku()")
public void delete(DeleteProduct command) {
    repository.delete(command.sku());
}
```

Nếu đọc dùng `key="#p0"` với `sku="P1"` nhưng xóa dùng `key="#p0"` với một **DeleteProduct object**, hai key không tương đương. Phải truy cập `sku()` của command ở đường xóa.

Biến `#result` chỉ có trong những ngữ cảnh Spring hỗ trợ **sau khi gọi method**: chẳng hạn `unless`, chọn key cho `@CachePut`, hoặc `@CacheEvict` với `beforeInvocation=false`. **Không dùng `#result` làm key của `@Cacheable`**, vì lúc tra cache chưa có kết quả method. Với `@CacheEvict(beforeInvocation=true)`, chưa có `#result`; lỗi method có thể xảy ra sau khi entry đã bị xóa.

`key` và `keyGenerator` là hai cách chọn khóa **loại trừ nhau** trên cùng annotation. Biểu thức gọn, có thể hiểu ngay thường phù hợp cho `key`; logic có nhiều quy tắc/chuẩn hóa/bảo mật/serialization nên chuyển sang `KeyGenerator` được kiểm thử riêng.

## 8. Lỗi phổ biến và cách kiểm tra

### Lỗi 1 — Chọn sai chỉ số tham số

```java
// Sai: key là requestId, không phải sku.
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(String requestId, String sku) { /* ... */ }

// Đúng khi kết quả chỉ phụ thuộc sku.
@Cacheable(cacheNames = "products", key = "#p1")
public Product find(String requestId, String sku) { /* ... */ }
```

### Lỗi 2 — Bỏ sót tham số có ảnh hưởng kết quả

Nếu `findPrice(sku, currency, tenantId)` chỉ cache theo `sku`, các loại tiền và tenant sẽ dùng chung entry ngoài ý muốn. Cần key chứa đủ tham số có ảnh hưởng giá; đồng thời không dùng dữ liệu cache như cách thay thế kiểm tra quyền thực tế.

### Lỗi 3 — Tên tham số bị mất khi biên dịch

`key="#sku"` chỉ đúng khi runtime biết tên tham số. Dùng `#p0`/`#p1` hoặc bật `-parameters`; tránh khẳng định mọi bản build đều giữ tên tham số.

### Lỗi 4 — Nhầm literal với biểu thức

`key="#p0.sku()"` đánh giá SKU từ request. `key="'#p0.sku()'"` trả **chuỗi cố định** `#p0.sku()`, làm các request dễ dùng chung một key sai.

### Lỗi 5 — Truy cập thuộc tính null hoặc sai accessor

`#p0.customer().id()` lỗi nếu `customer()` null; `#p0.sku()` yêu cầu đối tượng có method `sku()`. Với JavaBean chuẩn dùng property `#p0.sku` nếu tồn tại getter `getSku()`. Xác thực request và kiểm thử biểu thức với kiểu dữ liệu thật.

### Lỗi 6 — Key của đọc, cập nhật và xóa không trùng

Đọc `#p0.sku()`, còn xóa `#p0` với kiểu request khác sẽ không xóa entry mong muốn. Lập bảng “đọc/put/evict → region/key” cho cùng dữ liệu và viết test.

### Lỗi 7 — Key không ổn định hoặc có nguy cơ collision

Không cache theo object mutable hay dữ liệu có `toString()` thay đổi theo thời gian; không nối chuỗi với dấu phân cách chưa được escape. Chọn giá trị định danh bất biến và key chuẩn hóa thống nhất giữa các đường gọi.

### Lỗi 8 — Quên giới hạn proxy Spring

`@EnableCaching`, bean được Spring quản lý và lời gọi qua proxy là điều kiện thông thường để annotation có hiệu lực. Self-invocation như `this.find(...)` trong cùng bean thường bỏ qua caching trong proxy mode mặc định; `private` hoặc `final` method cũng có giới hạn khi interception bằng proxy. Đặt thao tác cache trên phương thức có thể được Spring intercept.

## 9. Bài tập tự kiểm tra

**Tình huống A.** Method `getProduct(String sku, String requestId)`; `requestId` chỉ định danh log, không ảnh hưởng product. Dùng key gì?

Đáp án: `#p0` (hoặc `#sku` khi tên tham số được giữ). Hai lượt gọi với cùng SKU được cache chung.

**Tình huống B.** Method `getPrice(PriceQuery query)` với record `PriceQuery(String tenantId, String sku, String currency)`. Dùng `#p0.sku()` có đủ không?

Đáp án: Không. Cần đồng thời phân biệt `tenantId`, `sku` và `currency` nếu cả ba ảnh hưởng giá. Key phải tránh collision và nhất quán với cách xác định giá.

**Tình huống C.** Method `lookup(String requestId, ProductQuery query)` và `ProductQuery` là record có accessor `sku()`. Cách lấy SKU?

Đáp án: `#p1.sku()` hoặc `#root.args[1].sku()`. `#p0.sku()` sai vì đối số đầu là chuỗi `requestId`.

**Tình huống D.** Hai request object khác `traceId` nhưng cùng `sku`; tại sao `key="#p0"` có thể tạo hai entry?

Đáp án: key là toàn bộ object. Nếu quy tắc `equals()/hashCode()` tính cả `traceId` (đặc biệt record), hai request khác key. `key="#p0.sku()"` chọn riêng SKU, nếu SKU đủ quyết định kết quả.

## 10. Checklist trước khi đưa vào production

1. Liệt kê mọi yếu tố ảnh hưởng đến kết quả: định danh, tenant, locale/currency, scope quyền, filter, phân trang, phiên bản dữ liệu.
2. Xác định key của từng region dưới dạng **bảng mẫu input → expected key**, gồm trường hợp khác tenant/locale và dữ liệu trùng phần chữ.
3. Chọn cách truy cập phù hợp kiểu dữ liệu: `#p0`, `#p1`, `#p0.sku` với JavaBean, `#p0.sku()` với record, `#p0['sku']` với Map.
4. Đảm bảo mọi đường `@Cacheable`/`@CachePut`/`@CacheEvict` của cùng dữ liệu tạo đúng cùng loại key; chạy test hit/miss và invalidation.
5. Xử lý null, object mutable, lỗi thiếu `-parameters`, collision của key dạng chuỗi, khả năng serializer của backend và side effect bị bỏ qua trên cache hit.
6. Theo dõi metrics hit/miss theo region và xác nhận các thay đổi từ nguồn không để entry stale lâu hơn hợp đồng cho phép.

Lựa chọn key đúng nhất là một hàm từ **những đầu vào quyết định kết quả** sang **một định danh cache ổn định, duy nhất trong region và có thể tái tạo trên các đường đọc/ghi/xóa**.

## Tài liệu chính thức

- Spring Framework — Custom Key Generation và Caching SpEL Context: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — `Cacheable` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework — SpEL Reference: https://docs.spring.io/spring-framework/reference/core/expressions.html
