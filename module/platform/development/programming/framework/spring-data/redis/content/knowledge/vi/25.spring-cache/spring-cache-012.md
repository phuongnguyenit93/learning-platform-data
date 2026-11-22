# Giới hạn proxy, tự gọi phương thức và khả năng đồng bộ tải dữ liệu trong Spring Cache với Redis

## 1. Mục tiêu và bối cảnh

Spring Cache cung cấp các annotation như `@Cacheable`, `@CachePut` và `@CacheEvict` để thêm hành vi cache vào phương thức Java. Khi tích hợp **Spring Data Redis**, kết quả phương thức có thể được lưu trong Redis để nhiều instance ứng dụng cùng đọc. Tuy nhiên, ba khái niệm sau cần được hiểu riêng:

1. **Proxy Spring AOP:** xác định lời gọi phương thức có đi qua logic cache hay không.
2. **Self-invocation (tự gọi phương thức):** lời gọi từ một phương thức của object đến phương thức khác trên chính object đó thường bỏ qua proxy; vì vậy annotation cache có thể không chạy.
3. **Đồng bộ tải dữ liệu:** khi cache chưa có giá trị, nhiều request có thể cùng gọi nguồn dữ liệu gốc. `@Cacheable(sync = true)` đưa ra yêu cầu đồng bộ, nhưng phạm vi và mức bảo đảm thực tế phụ thuộc `Cache` provider, cấu hình Redis và kiến trúc nhiều instance.

Bài học này giải thích cách ba chủ đề tương tác với nhau. Mục đích là tránh tình trạng “đã thêm `@Cacheable` nhưng vẫn truy vấn dữ liệu gốc liên tục”, hoặc “đã thêm `sync = true` nhưng hệ thống nhiều node vẫn xảy ra cache stampede”.

Sau khi học, bạn có thể:

- Vẽ được đường đi của một lời gọi đến bean có annotation cache.
- Nhận biết các lời gọi **đi qua proxy** và **đi thẳng vào target object**.
- Tổ chức service để `@Cacheable` và `@CacheEvict` thực sự được áp dụng.
- Giải thích cách một cache miss có thể kích hoạt nhiều lượt tải dữ liệu đồng thời.
- Hiểu hợp đồng `@Cacheable(sync = true)` và những điều nó **không tự bảo đảm** trong Redis phân tán.
- Phân biệt đồng bộ trong JVM, đồng bộ ở tầng cache provider và khóa phân tán.
- Chọn chiến lược giảm cache stampede, TTL đồng loạt và tải cao lên database.
- Xác định các chỉ số cần quan sát để biết cache hoạt động như kỳ vọng.

## 2. Spring Cache là abstraction, Redis là cache backend

Spring Cache định nghĩa một giao diện thống nhất cho các thao tác như lấy kết quả từ cache, đưa kết quả vào cache và xóa dữ liệu cache. Các annotation không trực tiếp gửi lệnh Redis. Chúng mô tả **khi nào** Spring cần tương tác với cache.

Ví dụ:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto getProduct(String productId) {
    return catalogGateway.loadProduct(productId);
}
```

Nếu lời gọi được Spring Cache chặn thành công, luồng xử lý logic là:

```text
Caller
  |
  v
Spring bean proxy
  |
  +-- Tính cache key
  |
  +-- Cache.get(key) ----------------------> Redis
        |                                      |
        | cache HIT                            |
        +----> trả giá trị đã lưu <-------------+
        |
        | cache MISS
        v
    Thực thi getProduct(...) trên target
        |
        v
    catalogGateway.loadProduct(...) --> DB/API gốc
        |
        v
    Cache.put(key, result) --------------> Redis
        |
        v
    Trả kết quả cho caller
```

Với Redis, một cache entry có thể dùng tên key dạng `products::42`, tùy cấu hình prefix, `KeyGenerator`, serializer và tên cache. Không nên gắn logic nghiệp vụ vào một tên key vật lý được đoán trước khi xác nhận cấu hình thực tế.

Có hai khối tách biệt:

- **Interceptor/proxy**: quyết định method call có cần tra cache hay không.
- **CacheManager/Cache**: thực hiện đọc/ghi, chẳng hạn bằng `RedisCacheManager` và `RedisCache`.

Nếu lời gọi **không đi qua proxy**, Redis có thể hoàn toàn không được hỏi. Trong trường hợp này, thay TTL hoặc đổi serializer Redis không sửa được nguyên nhân.

## 3. Cấu hình Spring Cache dùng Redis trong Spring Boot

Ví dụ Maven sử dụng Spring Boot và Redis:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Với Gradle:

```gradle
implementation 'org.springframework.boot:spring-boot-starter-cache'
implementation 'org.springframework.boot:spring-boot-starter-data-redis'
```

Có thể cấu hình kết nối Redis qua `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Bật annotation caching ở lớp cấu hình:

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
}
```

Spring Boot có thể tự cấu hình `RedisCacheManager` nếu Redis và caching infrastructure có mặt, không có một cache manager khác phù hợp được ưu tiên, và các điều kiện auto-configuration đáp ứng. **Đặt Redis dependency không đồng nghĩa annotation `@Cacheable` tự được kích hoạt nếu chưa bật annotation caching**.

Có thể điều chỉnh TTL bằng cấu hình đơn giản của Spring Boot:

```yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 10m
      cache-null-values: false
      use-key-prefix: true
```

Đây là ví dụ cấu hình chung; tên property, giá trị hỗ trợ và ưu tiên khi tự cấu hình có thể phụ thuộc phiên bản Spring Boot. Khi cấu hình `RedisCacheManager` bean thủ công, cần thiết lập chính sách tương ứng trên bean đó.

Nếu chỉ muốn minh họa mà không vận hành Redis, có thể thay cache manager bằng một implementation bộ nhớ cục bộ để quan sát proxy. Nhưng **kết luận về đồng bộ tải khi nhiều instance dùng chung Redis phải dựa trên RedisCache và cấu hình writer thực tế**, không suy từ bộ nhớ cục bộ.

## 4. Ví dụ dịch vụ: method được cache

Xét đối tượng trả về:

```java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductDto(
    String id,
    String name,
    BigDecimal price
) {}
```

Một cổng truy cập nguồn dữ liệu gốc:

```java
package com.example.catalog;

public interface CatalogGateway {
    ProductDto loadProduct(String productId);
}
```

`CatalogGateway` có thể được triển khai bằng Spring Data JPA, JDBC, một API khác hoặc hệ thống nội bộ. Bài học không phụ thuộc cách nó tải dữ liệu.

Service cache:

```java
package com.example.catalog;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductLookupService {

    private final CatalogGateway catalogGateway;

    public ProductLookupService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    @Cacheable(cacheNames = "products", key = "#productId")
    public ProductDto getProduct(String productId) {
        return catalogGateway.loadProduct(productId);
    }
}
```

Controller hoặc một bean khác tiêm `ProductLookupService`:

```java
package com.example.catalog;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductLookupService productLookup;

    public ProductController(ProductLookupService productLookup) {
        this.productLookup = productLookup;
    }

    @GetMapping("/{id}")
    public ProductDto find(@PathVariable("id") String id) {
        return productLookup.getProduct(id);
    }
}
```

Lời gọi `productLookup.getProduct(id)` đi qua bean do Spring quản lý, thông thường là proxy chứa cache interceptor. Khi cache HIT, thân phương thức `getProduct` không chạy; `catalogGateway.loadProduct` cũng không chạy.

Trong ví dụ, key SpEL `#productId` phụ thuộc metadata tên tham số được Spring nhận biết. Nếu cần biểu thức ổn định không phụ thuộc tên tham số, có thể dùng `#p0` hoặc `#a0` cho tham số đầu tiên:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto getProduct(String productId) {
    return catalogGateway.loadProduct(productId);
}
```

Các tên tham số trong SpEL cần được cung cấp phù hợp qua biên dịch và cách Spring khám phá metadata; việc chọn `#p0` giúp ví dụ không phụ thuộc đến cấu hình đó.

## 5. Proxy Spring AOP hoạt động ở ranh giới lời gọi

Chế độ mặc định của annotation cache thường sử dụng **proxy**. Spring tạo hoặc cung cấp một đối tượng trung gian bọc bean gốc. Khi caller gọi phương thức qua tham chiếu proxy, Spring có cơ hội chạy `CacheInterceptor` trước/sau khi gọi target.

```text
Đường A — gọi từ bean khác:

ProductController
    |
    v
ProductLookupService proxy
    |
    +--> CacheInterceptor (@Cacheable)
    |       | hit -> trả kết quả
    |       | miss
    v       v
ProductLookupService target
    |
    v
CatalogGateway


Đường B — tự gọi trong target:

ProductLookupService target
    |
    | this.getProduct(id)
    v
ProductLookupService target
    |
    +--> Bỏ qua CacheInterceptor
```

Tùy ứng dụng, Spring có thể sử dụng **JDK dynamic proxy** (proxy theo interface) hoặc **class-based proxy** (thường dựa trên CGLIB). Cả hai đều dựa trên ý tưởng lời gọi đến đối tượng proxy. Việc proxy một class không biến tất cả lời gọi qua `this` thành lời gọi được interception.

### 5.1. Hệ quả của proxy mode

Phương thức có annotation cache chỉ được áp dụng khi caller thực sự đi qua proxy phù hợp. Đối với chế độ proxy thông dụng:

- Phương thức **public** được gọi từ bean khác là lựa chọn an toàn và dễ dự đoán nhất.
- Lời gọi nội bộ bằng `this.someMethod()` thường bỏ qua interceptor.
- Lời gọi đến phương thức **private** không thể được override/intercept bằng proxy class thông thường.
- Phương thức `final` của class không thể được override bởi class-based proxy.
- Phương thức gọi trong constructor hoặc giai đoạn khởi tạo quá sớm có thể xảy ra trước khi proxy có thể áp dụng hành vi mong muốn.
- Đối tượng tự tạo bằng `new` không phải bean Spring được bọc bằng cache proxy.
- Những khác biệt về JDK proxy, CGLIB, method visibility, interface và phiên bản Spring có thể ảnh hưởng hành vi ở các trường hợp biên. Nên thiết kế API cache dưới dạng phương thức public của Spring-managed bean được gọi từ bên ngoài.

Một annotation xuất hiện trong source không đủ chứng minh interceptor đang chạy. Cần nhìn **đường lời gọi thực tế**.

## 6. Self-invocation: lỗi dễ mắc nhất

Xét service sau:

```java
@Service
public class ProductService {

    private final CatalogGateway catalogGateway;

    public ProductService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    public ProductDto checkoutProduct(String productId) {
        // Lời gọi ở đây thực hiện trong target object.
        return getProduct(productId);
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public ProductDto getProduct(String productId) {
        return catalogGateway.loadProduct(productId);
    }
}
```

Một bean khác gọi:

```java
productService.checkoutProduct("p-42");
```

`checkoutProduct` không có annotation cache. Sau khi proxy chuyển lời gọi đến target, dòng `getProduct(productId)` là lời gọi nội bộ trên chính target object. Nó **không đi qua cache interceptor của `getProduct`**.

Nếu gọi `checkoutProduct("p-42")` mười lần, `catalogGateway.loadProduct` có thể chạy mười lần, dù `getProduct` đã đánh dấu `@Cacheable`.

Trong khi đó, lời gọi từ bean khác:

```java
productService.getProduct("p-42");
```

đi qua proxy và có thể dùng cache đúng như kỳ vọng.

### 6.1. Bảng phân biệt lời gọi

| Đường gọi | Có đi qua proxy cache thông thường? | Kết quả |
|---|---|---|
| Controller tiêm service rồi gọi `service.getProduct(id)` | Có | `@Cacheable` có cơ hội hoạt động |
| Bean A tiêm Bean B rồi gọi `beanB.getProduct(id)` | Có | `@Cacheable` có cơ hội hoạt động |
| Trong cùng bean gọi `this.getProduct(id)` | Không | Bỏ qua annotation trên phương thức đích |
| Trong cùng bean gọi `getProduct(id)` | Không | Vẫn là lời gọi nội bộ |
| Constructor gọi phương thức cache | Không nên trông đợi | Chưa có đường đi proxy ổn định |
| `@PostConstruct` tự gọi phương thức cache của bean | Không nên trông đợi | Thường đi trực tiếp trong vòng đời target |
| `new ProductService(...).getProduct(id)` | Không | Object không do Spring quản lý |
| Gọi một phương thức private có `@Cacheable` | Không được hỗ trợ an toàn ở proxy mode | Annotation không đem lại hành vi mong muốn |

Điểm quan trọng: đổi từ `getProduct(id)` thành `this.getProduct(id)` **không sửa được gì**. Cả hai đều dùng chính target object.

### 6.2. Vì sao đôi khi thấy cache vẫn có dữ liệu?

Một key Redis có thể tồn tại vì được tạo từ lời gọi khác đi qua proxy, từ luồng prewarm, từ test trước hoặc từ một instance khác. Việc nhìn thấy key **không chứng minh** lời gọi self-invocation đang dùng cache.

Để điều tra đúng, cần quan sát số lần method tải dữ liệu gốc được gọi trong từng đường gọi. Một endpoint có thể hit Redis, trong khi một job nền tự gọi cùng phương thức lại bypass cache.

## 7. Cách sửa ưu tiên: tách method cache sang bean khác

Cách rõ ràng nhất là đưa method cần cache vào một bean chuyên trách, rồi inject bean đó vào nơi cần dùng.

Service tải có cache:

```java
package com.example.catalog;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CachedProductReader {

    private final CatalogGateway catalogGateway;

    public CachedProductReader(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public ProductDto getProduct(String productId) {
        return catalogGateway.loadProduct(productId);
    }
}
```

Service điều phối:

```java
package com.example.catalog;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final CachedProductReader cachedProducts;

    public CheckoutService(CachedProductReader cachedProducts) {
        this.cachedProducts = cachedProducts;
    }

    public ProductDto prepareCheckout(String productId) {
        ProductDto product = cachedProducts.getProduct(productId);
        // Các bước nghiệp vụ còn lại.
        return product;
    }
}
```

Luồng mới:

```text
CheckoutService target
        |
        | gọi bean được inject
        v
CachedProductReader proxy
        |
        v
CacheInterceptor
        |
        +-- HIT --> trả ProductDto
        |
        +-- MISS -> CatalogGateway -> lưu Redis -> trả ProductDto
```

**Lợi ích:** ranh giới cache có thể nhìn thấy trong kiến trúc. Bean điều phối không cần biết mình đang dùng proxy hay Redis; nó chỉ gọi một dependency công khai.

Điều này cũng giúp test dễ định hướng: kiểm tra đường đi qua `CachedProductReader` bean thay vì phụ thuộc hành vi gọi nội bộ khó nhìn thấy.

### 7.1. Tách bean và trách nhiệm

Không cần biến mỗi method thành một class riêng. Tách bean có ý nghĩa khi nhóm phương thức đó có một trách nhiệm rõ ràng, ví dụ:

- `CachedProductReader` xử lý đọc có cache.
- `ProductWriteService` xử lý cập nhật dữ liệu gốc.
- `CheckoutService` điều phối nghiệp vụ.

Nếu nhiều method cùng thuộc giao diện đọc dữ liệu và có cùng chính sách cache, chúng có thể sống chung trong một reader bean. Mục đích là tạo **lời gọi qua Spring bean proxy**, không phải tăng số lượng class vô cớ.

## 8. Những cách sửa khác và giới hạn

### 8.1. Tự inject proxy của chính mình

Một số dự án sử dụng self-injection hoặc `ObjectProvider` để lấy proxy của bean:

```java
@Service
public class ProductService {

    private final ObjectProvider<ProductService> selfProvider;

    public ProductService(ObjectProvider<ProductService> selfProvider) {
        this.selfProvider = selfProvider;
    }

    public void process(String id) {
        selfProvider.getObject().getProduct(id);
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public ProductDto getProduct(String id) {
        // Tải dữ liệu từ nguồn.
        return null;
    }
}
```

Đây là **minh họa cơ chế**, không phải khuyến nghị mặc định. Self-injection gắn mã nghiệp vụ chặt vào vòng đời Spring proxy, có thể tạo vòng phụ thuộc hoặc khác biệt giữa JDK proxy và class proxy. Các cấu hình cho phép circular reference không nên được bật chỉ để “sửa” việc tự gọi.

Nếu cần giữ một bean, hãy cân nhắc nguyên nhân kiến trúc trước; đa số trường hợp tách reader/service là rõ ràng hơn.

### 8.2. `AopContext.currentProxy()`

Spring AOP có cơ chế truy cập proxy hiện tại khi proxy được cấu hình expose. Mã có thể gọi qua `AopContext.currentProxy()` thay vì qua `this`. Nhưng nó phụ thuộc vào cấu hình AOP, phạm vi thread và việc lời gọi hiện tại thực sự đang ở trong invocation được proxied.

Cách này làm business code biết trực tiếp về Spring AOP và dễ phát sinh lỗi khi refactor hoặc thay đổi cấu hình. Không nên dùng nó làm giải pháp đầu tiên cho self-invocation.

### 8.3. AspectJ weaving

Spring Cache có thể hoạt động với chế độ advice `ASPECTJ` khi được cấu hình và weaving đúng cách. Với AspectJ, advice được dệt vào mã nên self-invocation có thể được interception.

Tuy nhiên, nó yêu cầu dependency và compile-time hoặc load-time weaving phù hợp, có khác biệt về classloader, build, vận hành và khả năng phát hiện annotation. Đặt `mode = AdviceMode.ASPECTJ` một mình **không tự động bật weaving hoàn chỉnh**.

Đây là lựa chọn khi ứng dụng có lý do cụ thể dùng weaving cho nhiều cross-cutting concern. Với một method cache thông thường, tách bean vẫn dễ hiểu và bảo trì hơn.

## 9. Các giới hạn proxy thường gặp

| Tình huống | Lý do dễ xảy ra lỗi | Hướng thiết kế |
|---|---|---|
| `@Cacheable` trên `private` method | Proxy không intercept lời gọi private như một API ngoài | Đưa method cache thành public trong bean chuyên trách |
| `@Cacheable` trên `final` method | Class-based proxy không thể override method | Bỏ final nếu có thể, hoặc chuyển ranh giới cache |
| Class `final` trong cấu hình class proxy | CGLIB không thể subclass | Dùng interface/JDK proxy thích hợp hoặc cấu trúc bean khác |
| Tự gọi cùng object | Bỏ qua proxy | Tách bean/call qua dependency |
| Object tạo bằng `new` | Không có proxy Spring | Sử dụng Spring-managed bean |
| Tự gọi trong `@PostConstruct` | Chưa đi qua đường gọi bean khác | Khởi động từ bean điều phối qua dependency, đúng lifecycle |
| Annotation thiếu `@EnableCaching` | Không kích hoạt hạ tầng cache annotation | Bật caching trong cấu hình |
| Gọi method không thuộc interface khi dùng JDK proxy | Proxy chỉ phơi bày API interface | Tiêm qua interface hợp lệ hoặc chọn chiến lược proxy phù hợp |
| Annotation đặt trên interface trong cách weaving không phù hợp | Cách phát hiện annotation có thể khác | Đặt annotation trên method implementation rõ ràng |
| Kotlin class/method final mặc định | Proxy theo class khó override | Dùng cấu hình all-open/plugin tương thích hoặc thiết kế interface |

Spring có những thay đổi về khả năng intercept non-public method ở các phiên bản và kiểu proxy khác nhau. Vì vậy, tài liệu đào tạo nên dùng **public method của Spring bean được gọi bên ngoài** để tránh phụ thuộc vào một góc trường hợp cụ thể.

### 9.1. Vì sao proxyTargetClass không sửa self-invocation?

Ví dụ bật class-based proxy:

```java
@EnableCaching(proxyTargetClass = true)
```

Điều này chọn cơ chế proxy theo class trong tình huống thích hợp. Nó không biến `this.cachedMethod()` bên trong target thành lời gọi qua proxy. Nếu nguyên nhân là self-invocation, đổi JDK proxy sang CGLIB chỉ thay kỹ thuật proxy chứ không khắc phục ranh giới lời gọi.

## 10. Cùng một method nhưng bị gọi từ các luồng ứng dụng khác nhau

Ứng dụng thường có nhiều đường vào:

```text
HTTP Controller -------+
                       |
Scheduled Job ---------+--> ProductService
                       |
Message Listener ------+
```

Nếu cả ba cùng được inject `CachedProductReader` và gọi `reader.getProduct(id)` thì cache interceptor có thể hoạt động trên các đường gọi đó.

Nếu scheduled job nằm trong cùng `ProductService` và tự gọi `getProduct`, trong khi controller gọi qua proxy, có thể xuất hiện:

```text
HTTP request    -> cache HIT
Scheduled job   -> bypass cache, luôn tải nguồn
Message handler -> cache HIT
```

Lúc này chỉ nhìn Redis hit rate chung sẽ khó xác định tại sao database vẫn tải cao. Nên quan sát số lần tải nguồn theo endpoint/job hoặc theo luồng gọi.

Một **self-invocation bỏ qua cả `@Cacheable(sync = true)`**: nếu annotation không được interception, ý định đồng bộ tải đặt trên nó cũng không được thực thi.

## 11. Cache miss đồng thời và hiện tượng cache stampede

Giả sử một key `products::p-42` đã hết hạn. Có 100 request cùng gọi `getProduct("p-42")` trong một khoảng thời gian rất ngắn.

Nếu mỗi request quan sát cache MISS và đều chạy loader:

```text
Time  Request A    Request B    Request C       ... Request 100
----  ----------   ----------   -------------       ------------
t0    GET -> MISS  GET -> MISS  GET -> MISS          GET -> MISS
t1    DB load      DB load      DB load             DB load
t2    SET cache    SET cache    SET cache           SET cache
t3    respond      respond      respond             respond
```

Một cache miss ban đầu có thể biến thành hàng chục hoặc hàng trăm lần gọi database/API gốc. Đây là **cache stampede**, còn gọi là thundering herd khi nhiều request cùng đổ về nguồn sau khi cache biến mất.

Nguy cơ tăng khi:

- Key rất nóng (hot key).
- Loader chậm, ví dụ phải gọi API có độ trễ cao.
- Nhiều key có TTL giống nhau và cùng hết hạn.
- Ứng dụng có nhiều instance hoặc request đồng thời cao.
- Redis vừa khởi động lại, cache trống do deploy hoặc invalidation.
- Không cache kết quả “không tìm thấy”, khiến các request tới ID không tồn tại liên tục miss.
- Sự cố Redis khiến cache liên tục không khả dụng và ứng dụng chuyển tải trực tiếp xuống nguồn.

Các chiến lược giảm stampede có thể dùng ở những tầng khác nhau. Cần bắt đầu bằng việc xác định **bao nhiêu request cùng key** và **bao nhiêu instance** thực hiện loader.

## 12. `@Cacheable(sync = true)` có nghĩa gì?

Spring Cache cho phép:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true
)
public ProductDto getProduct(String productId) {
    return catalogGateway.loadProduct(productId);
}
```

Theo hợp đồng Spring Cache, `sync = true` **đề nghị cache provider đồng bộ việc tính giá trị cho cùng cache key khi xảy ra miss**. Thay vì để mọi thread cùng chạy loader, cache có thể điều phối sao cho một thread thực hiện tính toán, các thread khác nhận giá trị kết quả khi cache được điền.

Luồng mong muốn:

```text
Nhiều request cùng key "p-42"
             |
             v
      Cache.get(key, loader)
             |
             +--> Thread A: chạy loader và lưu giá trị
             |
             +--> Thread B: đợi/kết hợp lượt tải
             |
             +--> Thread C: đợi/kết hợp lượt tải
             |
             v
     Các request nhận kết quả phù hợp
```

Spring Cache diễn đạt ý định này qua API dạng `Cache.get(key, Callable<T> valueLoader)` hoặc cơ chế tương ứng của provider. **Khả năng đồng bộ thực tế do implementation của cache quyết định**.

### 12.1. `sync = true` không biến phương thức thành synchronized Java

Annotation không tương đương với:

```java
public synchronized ProductDto getProduct(String id) { ... }
```

` synchronized ` khóa monitor của object trong JVM và không tự biết cache key; tất cả ID khác nhau có thể bị chặn cùng nhau nếu khóa cùng object. Trong khi đó, `sync = true` là yêu cầu phối hợp **cache value loading**, có thể chỉ áp dụng khi cache miss và theo cách provider chọn.

Cũng không thể suy ra rằng `sync = true` luôn là một **distributed lock** có khả năng chịu sự cố, timeout, failover và fencing trên toàn Redis Cluster. Cần xem RedisCache implementation và cấu hình writer của ứng dụng.

### 12.2. Những giới hạn annotation khi sync=true

Spring Cache có những ràng buộc được mô tả cho `@Cacheable(sync = true)`:

- Chỉ được chỉ định **một cache** cho phương thức có synchronized loading.
- Không dùng `unless` trong cùng `@Cacheable(sync = true)`.
- Không kết hợp method đó với các cache operation khác có ngữ nghĩa mâu thuẫn.
- Cache implementation cần hỗ trợ cách tính giá trị đồng bộ; nếu không, kết quả có thể không như kỳ vọng hoặc sinh lỗi tùy provider/phiên bản.

Ví dụ không phù hợp:

```java
@Cacheable(
    cacheNames = {"products", "productBackup"},
    key = "#p0",
    sync = true
)
public ProductDto load(String id) { ... }
```

vì cấu hình đồng bộ tải chỉ hỗ trợ một cache trong contract annotation.

Ví dụ khác:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true,
    unless = "#result == null"
)
public ProductDto load(String id) { ... }
```

`unless` không được hỗ trợ khi `sync = true`. Nếu cần chính sách không cache null, hãy xem khả năng cấu hình null caching của cache manager/provider và kiểm tra tác động lên mô hình đồng bộ.

### 12.3. Exception trong loader

Khi loader báo lỗi, cache không nên biến lỗi đó thành một giá trị nghiệp vụ thành công tùy ý. Caller sẽ nhận exception hoặc phản hồi lỗi theo cách cache/provider thực hiện. Một key có loader liên tục thất bại có thể tạo nhiều đợt miss mới.

Cần xử lý:

- Timeout nguồn dữ liệu.
- Retry có giới hạn và backoff hợp lý.
- Không đánh đồng lỗi Redis với “sản phẩm không tồn tại”.
- Không log/đưa exception nhạy cảm vào cache như một payload thành công.
- Với nguồn không ổn định, cân nhắc fallback hoặc circuit breaker ở tầng phù hợp.

Không nên coi `sync = true` là giải pháp thay thế cho quản lý lỗi của loader.

## 13. Đồng bộ trong một JVM khác với nhiều instance

Xét hai kiểu triển khai.

### 13.1. Một instance ứng dụng

```text
            JVM A
   Thread 1  Thread 2  Thread 3
       \        |        /
        \       |       /
         CachedProductReader proxy
                   |
              RedisCache
                   |
           Redis / database
```

Nếu provider hỗ trợ synchronized cache loading cho cùng key, các thread trong một JVM có thể tránh gọi loader trùng lặp. Nhưng điều này vẫn cần được đánh giá theo implementation và cấu hình `CacheManager` cụ thể.

### 13.2. Nhiều instance ứng dụng cùng dùng Redis

```text
       Application A                  Application B
       Thread A1, A2                  Thread B1, B2
             |                               |
       Cache interceptor                Cache interceptor
             |                               |
             +------------ Redis ------------+
                            |
                          MISS
                            |
               +------------+------------+
               |                         |
       A chạy nguồn dữ liệu      B chạy nguồn dữ liệu
               |                         |
               +------------> ghi Redis <+
```

Cả hai instance có thể quan sát miss gần như cùng lúc và đều gọi nguồn dữ liệu. Khóa Java local trong instance A **không ngăn** instance B chạy loader.

`@Cacheable(sync = true)` với Redis **không tự chứng minh** rằng chỉ một instance trong toàn hệ thống chạy loader. Mức bảo đảm phụ thuộc `RedisCache`, `RedisCacheWriter`, cơ chế lock được chọn và cách ứng dụng xử lý lỗi/timeout.

### 13.3. Bảng phân biệt phạm vi

| Giải pháp | Phạm vi phối hợp | Giới hạn |
|---|---|---|
| `synchronized` trên method Java | Các thread dùng cùng object monitor trong một JVM | Không biết key; không bao trùm instance khác |
| `ConcurrentHashMap` single-flight cục bộ | Thường trong một JVM, theo key | Không phối hợp nhiều JVM |
| `@Cacheable(sync = true)` | Hợp đồng đồng bộ loading của cache provider | Phụ thuộc implementation; không mặc nhiên là lock phân tán bền vững |
| Redis locking cache writer | Cơ chế khóa ở tầng RedisCacheWriter theo cấu hình/phiên bản | Phải xem granularity, latency và failure handling |
| Distributed lock ứng dụng | Có thể phối hợp nhiều instance khi thiết kế đúng | Lock TTL, ownership, retry, fencing, lỗi mạng |
| Prewarm/stale-while-revalidate/TTL jitter | Giảm hoặc dàn trải cache miss | Không phải giao dịch hay mutex tuyệt đối |

Bảng này nhấn mạnh rằng mục tiêu của caching thường là **giảm tải trung bình**, trong khi mục tiêu “chính xác một lần tải cho mọi key và mọi instance trong mọi điều kiện lỗi” là một cam kết hệ thống mạnh hơn rất nhiều.

## 14. RedisCacheWriter: non-locking và locking

Trong Spring Data Redis, `RedisCacheManager` dùng `RedisCache` và `RedisCacheWriter` để tương tác Redis. Một lựa chọn mặc định phổ biến là **non-locking writer**, ưu tiên throughput và tránh một số chi phí chờ khóa khi thao tác cache.

Spring Data Redis còn cung cấp **locking writer**. Khi chọn locking writer, các hoạt động nhất định của cache có thể dùng cơ chế khóa để ngăn sự chồng lấp theo thiết kế của writer. Tuy nhiên:

- Phạm vi khóa trong implementation có thể ở **cấp cache**, rộng hơn một cache key.
- Điều này có thể làm các key **không liên quan** bị chờ nhau trong một số thao tác.
- Không nên suy từ tên `lockingRedisCacheWriter` rằng có khóa công bằng, có fencing, bảo vệ mọi lỗi network hoặc giải quyết distributed exactly-once.
- Hành vi cụ thể đối với `@Cacheable(sync = true)`, `get(key, loader)`, các lệnh multi-step và thời gian khóa cần kiểm tra theo **phiên bản Spring Data Redis và driver** đang chạy.
- Nếu writer khóa rộng, throughput có thể giảm mạnh dưới tải cao mặc dù ý định ban đầu chỉ là giảm stampede.

Một cấu hình có thể dùng khi ứng dụng đã quyết định lựa chọn locking writer, với API được phiên bản hiện hành hỗ trợ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class RedisCacheWriterConfiguration {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory connectionFactory) {
        RedisCacheWriter writer =
            RedisCacheWriter.lockingRedisCacheWriter(connectionFactory);

        return RedisCacheManager.builder(writer)
            .cacheDefaults(RedisCacheConfiguration.defaultCacheConfig())
            .build();
    }
}
```

Đoạn mã minh họa việc lựa chọn writer, không hàm ý đây là cấu hình tối ưu cho mọi hệ thống. Việc khai báo một bean `RedisCacheManager` riêng cũng thay đổi cách auto-configuration trước đó được áp dụng; nếu cần TTL, serializer hoặc prefix, phải cấu hình các thuộc tính đó trong `RedisCacheConfiguration`.

**Điều cần thiết trước khi bật locking writer:** xác nhận rằng ứng dụng đang chịu stampede thật, xác định granularity khóa, đo contention và benchmark p95/p99 latency. Bật khóa mà không đo có thể chuyển vấn đề từ “quá nhiều loader” thành “quá nhiều request chờ nhau”.

## 15. `sync = true` không phải Redis transaction và không thay cho atomic update

`@Cacheable(sync = true)` điều phối **việc tính cache value khi miss**. Nó không tự biến mọi thao tác đọc/sửa/ghi nghiệp vụ thành transaction.

Ví dụ không an toàn về concurrency:

```java
@Cacheable(cacheNames = "accountBalances", key = "#p0", sync = true)
public long readBalance(String accountId) {
    return accountRepository.readBalance(accountId);
}
```

Annotation có thể giúp giảm số lần đọc nguồn cho cùng key, nhưng **không ngăn hai giao dịch nghiệp vụ cập nhật số dư đồng thời** hoặc bảo đảm cache luôn nhất quán với database.

Đối với counter, số dư, quota hoặc tồn kho, cần thiết kế atomic update ở hệ thống sở hữu dữ liệu. Cache chỉ là một lớp tăng tốc đọc; đồng bộ cache miss không thay thế optimistic locking, transaction hoặc Redis atomic command của dữ liệu nguồn.

Tương tự:

- `@Cacheable` không tự mở `MULTI`/`EXEC`.
- `sync = true` không làm một chuỗi nhiều key trên Redis Cluster thành transaction xuyên slot.
- Khóa writer có thể giảm chồng lấp thao tác cache nhưng không bảo đảm tính nhất quán của dữ liệu nghiệp vụ trong database.
- Kết quả đã được tải và đưa vào Redis có thể trở thành stale ngay sau đó nếu dữ liệu gốc thay đổi.

## 16. `@CachePut`, `@CacheEvict` và đường gọi qua proxy

Cache không chỉ gồm đọc. Khi cập nhật dữ liệu gốc, ứng dụng phải có chính sách làm mới hoặc loại bỏ entry đã lưu.

### 16.1. `@CacheEvict`: xóa giá trị cache

Ví dụ:

```java
@Service
public class ProductWriteService {

    private final CatalogGateway catalogGateway;

    public ProductWriteService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    @CacheEvict(cacheNames = "products", key = "#p0")
    public void updateProduct(String productId, ProductDto newValue) {
        catalogGateway.updateProduct(productId, newValue);
    }
}
```

Đây là ví dụ API: `CatalogGateway` cần định nghĩa thêm method `updateProduct(...)` khi dùng thật.

`@CacheEvict` cũng dựa trên proxy trong chế độ thông thường. Nếu cùng class có method `updateProduct` được gọi trực tiếp qua `this.updateProduct(...)`, lời gọi có thể **bỏ qua việc evict**, khiến cache vẫn còn dữ liệu cũ.

### 16.2. `@CachePut`: chạy method rồi cập nhật cache

```java
@CachePut(cacheNames = "products", key = "#result.id")
public ProductDto refreshProduct(String productId) {
    return catalogGateway.loadProduct(productId);
}
```

Khác với `@Cacheable`, `@CachePut` thường **luôn thực thi thân method** rồi đưa kết quả vào cache. Vì vậy, dùng `@CachePut` khi mục đích là cập nhật cache, không phải tránh tải nguồn.

Lời gọi nội bộ bỏ qua proxy cũng bỏ qua `@CachePut`.

### 16.3. Eviction và race với loader

Giả sử:

```text
t1: Thread A thấy MISS và bắt đầu tải product cũ.
t2: Thread B cập nhật product mới trong DB, rồi evict cache.
t3: Thread A hoàn tất, put product cũ vào cache.
```

Sau `t3`, cache có thể chứa dữ liệu cũ dù mutation ở `t2` đã evict. Chỉ dùng `@CacheEvict` hoặc `sync = true` không luôn giải quyết thứ tự race giữa việc tải và việc ghi dữ liệu gốc.

Nếu tính tươi mới rất quan trọng, hãy thiết kế chiến lược nhất quán bổ sung như versioned cache key, invalidation có điều kiện, đọc theo phiên bản hoặc yêu cầu nguồn dữ liệu hỗ trợ kiểm tra version. Với cache thuần tăng tốc đọc và chấp nhận stale ngắn, TTL thấp có thể đủ.

### 16.4. Giao dịch database và cache

Nếu update method tham gia transaction, thời điểm cache eviction so với lúc database commit rất quan trọng. Một số thiết kế cần trì hoãn eviction đến sau commit hoặc dùng cơ chế transaction-aware cache manager/điều phối tương ứng.

Không nên mặc định `@Transactional` trên service làm Redis cache và database commit nguyên tử cùng nhau. Với source-of-truth là database, chính sách invalidation phải phù hợp với transaction và mức nhất quán yêu cầu.

## 17. Những trường hợp đặc biệt có thể làm cache miss lặp lại

### 17.1. Null value caching

Nếu loader thường trả `null` cho sản phẩm không tồn tại và Redis cache **không lưu null**, mọi request cho ID đó có thể miss rồi gọi lại database.

Ví dụ:

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public ProductDto getProductOrNull(String id) {
    return catalogGateway.loadProduct(id);
}
```

Nếu cache manager được cấu hình không cho null, chính sách đối với kết quả `null` và việc đồng bộ của provider phải được kiểm tra. `sync = true` không cho phép kết hợp `unless = "#result == null"` như một giải pháp loại bỏ null.

Có thể thay đổi API thành kết quả không-null có nghĩa rõ ràng, hoặc dùng negative caching với TTL ngắn phù hợp. Tuy nhiên, việc cache “không tồn tại” quá lâu có thể làm hệ thống chưa nhìn thấy sản phẩm vừa được tạo.

### 17.2. Cache key không đồng nhất

Ví dụ hai biểu thức:

```java
@Cacheable(cacheNames = "products", key = "#p0")
```

và

```java
@Cacheable(cacheNames = "products", key = "'product:' + #p0")
```

tạo hai cache key khác nhau, nên không chia sẻ cache entry ngay cả khi cùng product ID.

Tương tự, `getProduct("42")`, `getProduct("042")` hoặc `getProduct(" 42 ")` có thể tạo ba key riêng nếu không chuẩn hóa ID. Đồng bộ theo key chỉ có ích khi mọi lời gọi cùng một thực thể dùng cùng key.

### 17.3. TTL quá ngắn

Nếu TTL là 1 giây trong khi loader mất 3 giây, nhiều request có thể liên tục gặp miss. Hệ thống phải cân nhắc TTL theo độ biến động dữ liệu và latency nguồn.

### 17.4. Evict allEntries quá thường xuyên

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void clearProductCache() { }
```

Nếu gọi thường xuyên, rất nhiều hot key có thể mất cùng lúc; các request sau đó cùng tải nguồn. Trong Redis, xóa cả vùng cache còn tạo chi phí key scanning hoặc delete tùy cấu hình writer.

Cần tránh dùng eviction toàn bộ để sửa một product nếu bài toán cho phép xóa key riêng.

### 17.5. Kết quả không serializable hoặc serializer sai

Với RedisCache, giá trị method cần được serializer cấu hình chuyển thành bytes. Nếu một DTO không thể serialize/deserialize đúng, thao tác cache có thể lỗi dù proxy đã interception.

Phải phân biệt:

- **Không interception**: loader chạy do lời gọi bypass proxy.
- **Cache MISS thật**: không có key hoặc TTL hết hạn.
- **Cache read/write error**: Redis connection/serializer/permissions gặp lỗi.
- **Key mismatch**: thực thể giống nhau nhưng key khác nhau.
- **Cache manager mismatch**: method dùng provider hoặc tên cache khác với dự kiến.

Giải pháp cho từng nhóm khác nhau.

## 18. Giảm cache stampede ngoài sync=true

Không có một kỹ thuật duy nhất phù hợp mọi workload. Có thể kết hợp các chiến lược sau.

### 18.1. Prewarm cho dữ liệu nóng

Trước khi đưa traffic lớn vào hệ thống, chủ động tải một tập hot key. Việc prewarm có thể chạy qua bean được Spring inject để tận dụng `@Cacheable`, hoặc trực tiếp dùng API cache manager nếu muốn chủ động điền cache.

Nếu job prewarm tự gọi `this.getProduct()` trong cùng bean, nó có thể bypass proxy. Cần kiểm tra lại đường gọi.

### 18.2. TTL jitter để tránh hết hạn đồng loạt

Nếu mọi cache entry được tạo cùng lúc với TTL bằng nhau, nhiều key có thể hết hạn trong cùng một thời điểm. Dùng TTL dao động trong một khoảng được kiểm soát có thể dàn trải tải nguồn.

Ví dụ logic:

```text
TTL cơ sở: 600 giây
TTL thực:   khoảng 540 đến 660 giây cho mỗi entry
```

Các con số chỉ minh họa. Spring Data Redis `RedisCacheConfiguration` có các tùy chọn TTL theo phiên bản; để tính TTL động theo entry có thể cần API được phiên bản đó hỗ trợ hoặc chiến lược cache phù hợp. Không nên giả định một property YAML `time-to-live` tự thêm jitter.

### 18.3. Stale-while-revalidate

Nếu dữ liệu cho phép hơi cũ trong thời gian ngắn, có thể phục vụ giá trị cache còn chấp nhận được và làm mới ở phía sau theo một cơ chế có kiểm soát.

Mô hình:

```text
Request tới hot key
     |
     +-- giá trị còn mới: trả ngay
     |
     +-- giá trị stale nhưng trong ngưỡng cho phép:
     |       trả giá trị stale
     |       lên lịch refresh có giới hạn
     |
     +-- không có dữ liệu sử dụng được:
             chờ loader hoặc dùng fallback
```

Đây là **mẫu thiết kế bổ sung**, không phải hành vi mặc định của `@Cacheable` với RedisCacheManager.

### 18.4. Single-flight theo key trong ứng dụng

Trong một JVM, ứng dụng có thể có một bảng trạng thái đang tải theo key để các caller cùng key chia sẻ một `Future` hoặc kết quả của một lượt load. Cách này hữu ích khi provider hiện tại không đáp ứng mong muốn hoặc luồng tải không đi qua Spring Cache.

Tuy nhiên, phải dọn entry khi future hoàn tất, truyền lỗi đúng cách, giới hạn số key đang chờ và tránh giữ future lỗi vĩnh viễn. Một single-flight local không phối hợp giữa nhiều instance.

### 18.5. Distributed lock khi thật sự cần phối hợp nhiều instance

Nếu một hot key gây chi phí nguồn rất lớn, có thể dùng một khóa phân tán riêng theo key, ví dụ:

```redis
SET lock:product:p-42 <unique-owner-token> NX PX 30000
```

Chỉ instance lấy được lock mới thực hiện load; các instance khác chờ có giới hạn, kiểm tra lại cache hoặc dùng fallback. Nhưng triển khai đúng đòi hỏi:

- Lock key được tính thống nhất cho cùng cache key.
- Token sở hữu riêng và xóa lock bằng cách **kiểm tra token**, tránh xóa nhầm lock của request khác.
- TTL lock phù hợp thời gian load, có xử lý loader treo, timeout và failover.
- Cơ chế chờ/retry có jitter và hạn mức, tránh thác request.
- Kiểm tra lại cache sau khi giành lock vì một instance khác có thể đã điền.
- Nếu nghiệp vụ yêu cầu tính đúng đắn mạnh, cân nhắc fencing/version; một Redis lease hết hạn không đủ để ngăn worker cũ tiếp tục ghi.

Khóa phân tán đưa thêm độ phức tạp vận hành. Nếu chỉ muốn giảm tải cache ở mức thông thường, có thể bắt đầu bằng `sync = true` phù hợp provider, prewarm, TTL hợp lý và quan sát metrics.

### 18.6. Hạn chế concurrent load ở nguồn

Có thể dùng semaphore, bulkhead, rate limiter hoặc queue để giới hạn số yêu cầu vào backend gốc khi cache gặp miss. Điều này giúp tránh làm sập nguồn ngay cả khi chưa kiểm soát tuyệt đối việc trùng load.

Khi giới hạn, ứng dụng phải xác định deadline, timeout và phương án trả lỗi/fallback; không để request chờ không thời hạn.

## 19. So sánh ba tình huống thường gặp

| Tình huống | Triệu chứng | Nguyên nhân trọng tâm | Hướng xử lý |
|---|---|---|---|
| Method có `@Cacheable` nhưng nội bộ gọi nhiều lần vẫn tải DB | Cache hit rate thấp trong một luồng cụ thể | Self-invocation bỏ qua proxy | Tách method cache sang bean khác |
| Có nhiều request đồng thời cho một key vừa hết hạn | Nhiều lượt gọi loader dù method được intercept | Cache miss đồng thời | `sync = true` nếu provider hỗ trợ, single-flight, prewarm |
| Hai instance cùng tải dữ liệu từ nguồn cho cùng key | Dư thừa loader qua nhiều JVM | Không có phối hợp phân tán đủ mạnh | Xác minh Redis writer, dùng distributed strategy khi cần |
| Nhiều key hết hạn trong cùng phút | Tải DB tăng đột ngột theo chu kỳ | TTL đồng loạt | TTL jitter, prewarm, refresh có giới hạn |
| Cache không còn cập nhật sau mutation | Trả dữ liệu cũ | Eviction bypass proxy hoặc race với loader | Tách write service, xử lý thời điểm invalidation |
| Redis có key nhưng method vẫn tải nguồn | Lời gọi bypass, key khác, cache manager khác hoặc lỗi | Chưa xác định | Quan sát proxy, key, hit/miss và serializer |

Bảng này cho thấy một triệu chứng “cache không hiệu quả” có thể đến từ **hai tầng hoàn toàn khác nhau**: lời gọi Java không bị interception hoặc cache provider đang xử lý miss với concurrency.

## 20. Cách quan sát để chẩn đoán chính xác

### 20.1. Đếm lượt gọi nguồn dữ liệu

Trong môi trường kiểm soát, thêm metric hoặc bộ đếm vào implementation của `CatalogGateway.loadProduct`. Sau đó gọi cùng một ID nhiều lần.

Kết quả cần phân biệt:

```text
Lời gọi qua proxy, cache HIT:
    số lần load nguồn gần với số cache miss.

Lời gọi tự gọi target:
    số lần load nguồn có thể gần với số method call.

Nhiều request đồng thời:
    số lần load nguồn có thể lớn hơn số cache key bị miss
    nếu chưa có cơ chế phối hợp phù hợp.
```

Metrics có ích: cache hit/miss (nếu provider/instrumentation hỗ trợ), số lần gọi gateway theo key hoặc nhóm, latency nguồn, Redis read/write errors, thời gian loader và số concurrent loads.

### 20.2. Quan sát key trong Redis

Nếu tên cache là `products`, với prefix mặc định và key String đơn giản, có thể thấy key gần dạng:

```text
products::p-42
```

Nhưng key thực phụ thuộc key prefix và serializer. Với môi trường phát triển, sau khi gọi service qua proxy, có thể quan sát Redis bằng công cụ quản lý phù hợp hoặc Redis CLI.

Trên Redis có nhiều key, dùng `SCAN` thay vì chạy `KEYS *` như thói quen trên production. Nếu serializer là nhị phân, output có thể không phải chuỗi dễ đọc.

### 20.3. Xác nhận bean được proxied

Trong một công cụ chẩn đoán dành cho developer, có thể kiểm tra:

```java
import org.springframework.aop.support.AopUtils;

boolean proxied = AopUtils.isAopProxy(productLookupService);
```

Kết quả `true` cho biết object đang được xét là AOP proxy, **không tự chứng minh mọi method đều có cache advice**. Cần kiểm tra annotation được phát hiện, đường gọi và cache manager.

Một lời gọi `this.getProduct(id)` vẫn bỏ qua proxy ngay cả khi bean bên ngoài đã được wrap.

### 20.4. Test qua ApplicationContext

Với cơ chế proxy, test gọi trực tiếp một object tạo bằng constructor hoặc `@InjectMocks` sẽ không chứng minh hành vi Spring Cache. Khi cần kiểm tra annotation, test phải dùng **bean được lấy từ Spring ApplicationContext** với caching enabled và cache manager phù hợp.

Một bài kiểm tra hành vi có thể thực hiện:

1. Gọi hai lần `cachedProductReader.getProduct("p-42")` qua Spring bean.
2. Ghi số lượt gọi `CatalogGateway`.
3. Kỳ vọng loader được gọi một lần nếu cache entry được lưu và không hết hạn.
4. Gọi đường self-invocation của ví dụ lỗi, quan sát loader bị gọi lại.
5. Sau khi tách bean, gọi lại đường điều phối, quan sát cache được sử dụng.

Đây là hướng dẫn bài thực hành, không phải yêu cầu chạy test đối với tài liệu Markdown này.

## 21. Phân tích đồng thời bằng một kịch bản cụ thể

Giả sử có ba instance ứng dụng: A, B, C. Mỗi instance phục vụ 100 request/giây cùng yêu cầu thông tin của sản phẩm `p-42`. TTL cache là 60 giây và load từ database mất 800 ms.

Khi entry hết hạn:

```text
t0:
    Redis không có products::p-42.

t0 + 10ms:
    A có nhiều request cùng MISS.
    B có nhiều request cùng MISS.
    C có nhiều request cùng MISS.

t0 + 20ms:
    Nếu không có cơ chế coalescing:
        nhiều thread trên cả A, B, C bắt đầu query DB.

t0 + 800ms:
    một số loader hoàn tất và ghi Redis.

Sau đó:
    request mới có thể HIT,
    nhưng các loader đã khởi chạy trước đó vẫn chiếm tài nguyên.
```

Nếu `sync = true` hoạt động tốt trong phạm vi từng instance nhưng **không phối hợp xuyên instance**, có thể vẫn có ít nhất một lượt load ở A, một lượt ở B và một lượt ở C. Nếu một writer có cơ chế đồng bộ xuyên instance theo cách phù hợp, số lượt load có thể giảm nữa; nhưng cần xác nhận qua cách writer thực thi và các điều kiện lỗi.

Lợi ích của coalescing phụ thuộc **độ dài cửa sổ cache miss**. Loader càng chậm, càng có nhiều request cùng nhìn thấy MISS. Nếu hệ thống cần yêu cầu nghiêm ngặt không bao giờ tính cùng một giá trị hai lần, bài toán vượt xa việc thêm một thuộc tính annotation.

### 21.1. Tại sao tăng số instance chưa chắc giảm stampede?

Tăng từ 3 lên 10 instance tăng năng lực xử lý request nhưng cũng có thể tăng số request cùng quan sát miss và số loader cạnh tranh. Redis dùng chung chỉ giúp chia sẻ **giá trị đã được ghi**; nó không mặc nhiên đồng bộ quá trình tính giá trị **trước lúc cache được điền**.

### 21.2. Ngay cả khi đã có lock vẫn có thể stale

Tình huống khác:

```text
t1: Loader A lấy lock và bắt đầu đọc dữ liệu gốc.
t2: Dữ liệu gốc bị cập nhật.
t3: Một luồng khác evict key.
t4: Loader A ghi kết quả cũ vào cache.
```

Khóa phục vụ cache loading không tự ràng buộc thứ tự với transaction cập nhật nguồn. Khi yêu cầu tính nhất quán mạnh, phải thiết kế versioning hoặc cơ chế cache update/eviction tương thích với dữ liệu nguồn.

## 22. Kết hợp cache với @Async, @Transactional và lifecycle

Spring có nhiều tính năng dựa trên AOP. Khi một method vừa có `@Cacheable`, vừa có `@Async` hoặc `@Transactional`, cần hiểu:

- Lời gọi phải đi qua proxy phù hợp để advice được áp dụng.
- Self-invocation có thể làm mất **nhiều advice cùng lúc**, không chỉ cache.
- Thứ tự advice và luồng thực thi có thể ảnh hưởng đến hành vi thực tế.
- Spring và cache provider có hỗ trợ riêng cho kiểu trả về bất đồng bộ/reactive ở các phiên bản mới; không được suy rằng mọi `CompletableFuture` hoặc reactive publisher được đồng bộ và cache giống một object thông thường.

Ví dụ không nên dùng để xác nhận cache hoạt động:

```java
@PostConstruct
public void initialize() {
    getProduct("p-42"); // Tự gọi, có thể bỏ qua cache proxy.
}
```

Có thể chuyển phần prewarm sang bean điều phối được chạy sau khi các bean liên quan đã khởi tạo xong và gọi `CachedProductReader` được inject. Chọn hook lifecycle phù hợp với yêu cầu khởi động của ứng dụng.

Với `@Transactional`, cần xem liệu cache entry bị xóa trước khi database commit hoặc lỗi rollback hay không. Tránh coi việc gắn nhiều annotation là một bảo đảm nhất quán xuyên Redis và database.

## 23. Những lỗi thường gặp và hướng xử lý

### “@Cacheable có trên method nhưng database vẫn bị gọi mỗi lần”

Kiểm tra `@EnableCaching`, Spring-managed bean, method public, lời gọi từ bean khác và đúng method được annotation. Tìm self-invocation trước khi thay serializer hoặc TTL.

### “Bật proxyTargetClass=true vẫn không cache khi this.method()”

Class-based proxy không biến lời gọi nội bộ thành lời gọi qua proxy. Tách method cache sang bean riêng hoặc cân nhắc cơ chế weaving khi có lý do rõ ràng.

### “sync=true rồi nhưng vẫn có nhiều request gọi nguồn”

Xác minh lời gọi có bị interception không; tiếp theo xem cache provider, RedisCacheWriter, số instance và cách xử lý loader. Kiểm tra key có thực sự giống nhau và TTL có đủ dài không.

### “sync=true không kết hợp được với unless”

Đây là ràng buộc của Spring Cache synchronized loading. Dùng chính sách null caching của provider hoặc thay đổi hợp đồng trả về, tùy yêu cầu nghiệp vụ.

### “Tăng số replica ứng dụng khiến database bị dồn tải lúc TTL hết hạn”

Nhiều instance có thể cùng quan sát MISS. Cần đo số loader xuyên node và cân nhắc prewarm, jitter, khóa phù hợp hoặc giới hạn concurrent loads.

### “Một cache bị chậm toàn bộ sau khi bật locking writer”

Khóa writer có thể có phạm vi rộng hơn một entry và tạo contention. Kiểm tra đặc điểm phiên bản, độ trễ, key nóng và độ đồng thời; cân nhắc thiết kế khóa hẹp hơn khi phù hợp.

### “@CacheEvict không xóa key sau khi update”

Có thể update được gọi nội bộ, method không qua proxy hoặc sai cache name/key. Cũng có thể có race khi loader cũ ghi lại cache sau eviction.

### “Lúc chạy test annotation không có tác dụng”

Kiểm tra test có dùng bean từ Spring ApplicationContext hay chỉ tạo object bằng `new`/Mockito. Annotation AOP không hoạt động trên object không được Spring proxy.

### “Lúc gọi lần đầu trả null, các lần sau vẫn gọi backend”

Xem cấu hình cache null values và cách loader xử lý kết quả không tồn tại. Phân biệt nil hợp lệ với exception do backend/serializer.

### “Cache trả dữ liệu cũ sau khi cập nhật”

Xem TTL, key design, eviction strategy, thứ tự commit và race giữa loader với writer. `sync=true` không phải cơ chế đồng bộ toàn bộ nguồn dữ liệu.

## 24. Bài thực hành

### Bài 1: Minh họa self-invocation

Tạo service:

```java
@Service
public class DemoService {

    private final SlowGateway gateway;

    public DemoService(SlowGateway gateway) {
        this.gateway = gateway;
    }

    @Cacheable(cacheNames = "demo", key = "#p0")
    public String load(String id) {
        return gateway.fetch(id);
    }

    public String loadInside(String id) {
        return load(id);
    }
}
```

Thực hiện qua Spring bean:

1. Gọi hai lần `demoService.load("x")`, quan sát số lần `gateway.fetch`.
2. Gọi hai lần `demoService.loadInside("y")`, quan sát số lần `gateway.fetch`.
3. Giải thích vì sao hai đường có thể cho kết quả khác nhau.
4. Tách `load` sang bean `CachedDemoReader`, inject vào `DemoService`, gọi lại `loadInside`.
5. So sánh số lần tải nguồn sau khi tách bean.

### Bài 2: Cùng một cache key và hai key khác nhau

Sử dụng:

```java
@Cacheable(cacheNames = "demo", key = "#p0", sync = true)
public String load(String id) {
    return gateway.fetch(id);
}
```

Cho nhiều thread cùng gọi `"x"` và một nhóm khác gọi `"y"`. Hãy phân biệt coalescing theo key với khóa chung toàn method. Quan sát số lần `fetch` và thời gian chờ trong cache provider đang sử dụng.

### Bài 3: Đặt sync=true trên Redis

Dùng `RedisCacheManager` thực của ứng dụng:

1. Xóa cache entry thử nghiệm.
2. Cho nhiều thread trong cùng instance gọi một key.
3. Đếm số lần loader chạy.
4. Lặp lại với hai instance dùng chung Redis.
5. Ghi rõ phiên bản Spring Data Redis và cấu hình writer.
6. So sánh số lần loader, latency và log lỗi Redis trước khi kết luận phạm vi đồng bộ.

### Bài 4: TTL đồng loạt

Chuẩn bị 100 hot key có TTL bằng nhau. Tạo traffic đều và quan sát số lượt load nguồn sau thời điểm TTL hết hạn. Sau đó thiết kế cơ chế phân tán TTL (jitter) hoặc prewarm theo từng nhóm; dự đoán ảnh hưởng đến đỉnh tải.

### Bài 5: Eviction bị bypass

Viết bean có phương thức `updateProduct` được đánh dấu `@CacheEvict`, sau đó gọi nó từ method khác trong cùng bean. Quan sát cache có còn dữ liệu cũ hay không. Chuyển cập nhật sang một bean khác hoặc gọi bằng đường đi qua proxy và so sánh.

### Bài 6: Race giữa loader và cập nhật

Dựng tình huống loader đọc dữ liệu cũ và chờ trước khi ghi cache; đồng thời cập nhật nguồn và evict. Mô tả thứ tự khiến kết quả cũ có thể xuất hiện lại. Đề xuất versioned key hoặc kiểm tra version khi publish cache nếu nghiệp vụ không chấp nhận stale.

## 25. Những câu hỏi tự đánh giá

1. Vì sao annotation `@Cacheable` trên một public method vẫn có thể không chạy?
2. Thay `getProduct(id)` bằng `this.getProduct(id)` có giải quyết self-invocation không?
3. Vì sao một bean được Spring AOP proxy không có nghĩa mọi lời gọi đến mọi method đều được interception?
4. `@Cacheable(sync = true)` đồng bộ ở tầng nào và phụ thuộc vào thành phần nào?
5. Vì sao nhiều instance cùng dùng Redis vẫn có thể cùng gọi database khi cache miss?
6. `RedisCacheWriter` locking có phải một mutex theo từng key với bảo đảm exactly-once cho mọi lỗi không?
7. Khi nào nên dùng prewarm, TTL jitter, single-flight hoặc distributed lock?
8. Vì sao `@CacheEvict` có thể bỏ sót invalidation hoặc vẫn để dữ liệu cũ xuất hiện lại?
9. Vì sao unit test dùng `new MyService(...)` không đủ để kiểm tra cache annotation?
10. Nếu chỉ cần đọc nhanh dữ liệu, tại sao không nên dùng `sync=true` để thay một transaction cập nhật số dư?

## 26. Ghi nhớ

- Spring Cache trong proxy mode chỉ can thiệp khi lời gọi **đi qua Spring AOP proxy**. `this.method()` trong cùng target thường bỏ qua `@Cacheable`, `@CachePut`, `@CacheEvict` và cả `sync=true` đi kèm.
- Cách sửa dễ bảo trì nhất là **tách method cache sang một bean được inject** và gọi nó qua dependency rõ ràng.
- JDK proxy, CGLIB, `proxyTargetClass`, `final`, `private`, `@PostConstruct` và object tạo bằng `new` là những yếu tố cần cân nhắc khi annotation không có tác dụng.
- `@Cacheable(sync = true)` là **yêu cầu đồng bộ cache value loading** gửi tới provider. Nó không tự trở thành distributed lock có bảo đảm tuyệt đối trên mọi instance Redis.
- Một lần Redis cache miss có thể khiến nhiều request cùng tải nguồn; cần hiểu **cache stampede**, thời gian loader, key nóng và TTL.
- `RedisCacheWriter` non-locking/locking có các trade-off khác nhau. Nếu chọn locking writer phải xem phạm vi khóa, phiên bản và đo contention.
- Để giảm stampede, có thể kết hợp synchronized loading, TTL jitter, prewarm, stale-while-revalidate, single-flight hoặc khóa phân tán được thiết kế đúng khi cần.
- Cache loading synchronization **không thay thế transaction, cơ chế bảo vệ dữ liệu gốc hay chiến lược invalidation**.
- Khi chẩn đoán, đếm số lần loader thực sự chạy, kiểm tra đường gọi qua proxy, cache key, Redis hit/miss, serializer, TTL và số instance.

### Tài liệu tham khảo chính thức

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/)
