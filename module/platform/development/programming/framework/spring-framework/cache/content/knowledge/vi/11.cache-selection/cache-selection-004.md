# Phân biệt `cacheManager` với `cacheResolver` và ràng buộc loại trừ

## 1. Kết luận cốt lõi

Trong Spring Cache, **`cacheManager` và `cacheResolver` đều liên quan đến việc xác định vùng cache**, nhưng chúng đóng hai vai trò khác nhau:

- **`CacheManager`** là thành phần quản lý/tìm đối tượng `Cache` theo tên. Ta thường cấu hình bean `CacheManager` đại diện cho một backend hoặc một nhóm cache, sau đó để Spring dùng cơ chế giải quyết cache mặc định.
- **`CacheResolver`** là chiến lược **quyết định tập hợp đối tượng `Cache` thực sự áp dụng cho một cache operation**. Nó nhận ngữ cảnh lời gọi và có thể chọn cache dựa trên đối số runtime, phương thức và thông tin operation. `CacheResolver` mặc định thường dựa vào một `CacheManager`.
- **`cacheManager = "..."`** và **`cacheResolver = "..."`** là **hai thuộc tính chọn chiến lược phân giải cache** ở cache annotation. Chúng chứa **tên bean trong Spring context**, không phải tên cache hay kết nối Redis.
- **Không đặt đồng thời hai thuộc tính trên *cùng một cache operation*.** Spring quy định chúng *mutually exclusive*; cố chỉ định cả hai cho cùng một `@Cacheable`, `@CachePut` hoặc `@CacheEvict` là cấu hình không hợp lệ và dẫn đến exception khi Spring xử lý operation.
- `@CacheConfig` có thể cung cấp giá trị mặc định **ở cấp lớp**; một lựa chọn cụ thể trên operation có độ ưu tiên cao hơn giá trị mặc định cấp lớp. Do đó, **`@CacheConfig(cacheManager = "...")` kết hợp với một method `@Cacheable(cacheResolver = "...")` là trường hợp override hợp lệ**, không phải khai báo đồng thời hai thuộc tính *trên cùng operation*.

Câu hỏi thực tế nên đặt ra là: **“Tôi chỉ cần dùng một CacheManager đã biết, hay cần tự tính toán cache đích cho từng lời gọi?”** Nếu chỉ cần một manager, `cacheManager` đơn giản hơn; nếu cần routing động, viết `CacheResolver`.

## 2. Cache, CacheManager và CacheResolver khác nhau thế nào?

Hãy phân biệt ba đối tượng:

| Khái niệm | Vai trò | API tiêu biểu | Ví dụ |
| --- | --- | --- | --- |
| `Cache` | Thực hiện thao tác lưu/truy xuất/xóa entry | `get(key)`, `put(key, value)`, `evict(key)` | Một cache tên `books` |
| `CacheManager` | Tra cứu các `Cache` do manager quản lý | `getCache(name)`, `getCacheNames()` | `ConcurrentMapCacheManager` hoặc manager cho Redis |
| `CacheResolver` | Trả tập cache sẽ dùng cho một operation cụ thể | `resolveCaches(context)` | Chọn cache của tenant/nhóm khách hàng tại runtime |

Mối quan hệ thường gặp:

```text
@Cacheable(cacheNames = "books", cacheManager = "libraryManager")
      |
      v
Spring cache interceptor
      |
      v
Default resolver / SimpleCacheResolver
      |
      v
libraryManager.getCache("books")
      |
      v
Cache object -> lookup/put/evict theo operation
```

Với resolver tùy chỉnh:

```text
@Cacheable(cacheResolver = "routingResolver")
      |
      v
Spring cache interceptor
      |
      v
routingResolver.resolveCaches(invocationContext)
      |
      +-- context.getArgs()
      +-- context.getMethod()
      +-- context.getTarget()
      +-- context.getOperation()
      |
      '-- chọn 1 hoặc nhiều Cache object tại thời điểm gọi
                 |
                 v
           lookup / put / evict
```

**Điểm dễ nhầm:** `cacheNames = "books"` là tên cache, còn `cacheManager = "libraryManager"` là **tên bean CacheManager**. Chúng không có cùng ý nghĩa. Việc một manager hỗ trợ cache `"books"` hay không phụ thuộc cấu hình provider.

`CacheManager` và `CacheResolver` cũng không phải hai backend cạnh tranh nhau. Một custom resolver hoàn toàn có thể **sử dụng một hoặc nhiều CacheManager bên trong**. Nó tự quyết định gọi `getCache(...)` trên manager nào và trả về tập cache nào.

## 3. `cacheManager`: chọn một manager cụ thể

Khi ứng dụng có nhiều `CacheManager`, ta có thể chỉ định rõ manager mà operation sử dụng:

```java
@Cacheable(
    cacheNames = "books",
    cacheManager = "libraryCacheManager",
    key = "#p0"
)
public Book findBook(String id) {
    return repository.find(id);
}
```

*Đoạn minh họa; `Book` và `repository` cần được định nghĩa.*

Cách hiểu:

1. Spring xác định cache operation là `@Cacheable`.
2. Thuộc tính `cacheManager` yêu cầu sử dụng bean `CacheManager` tên `libraryCacheManager`.
3. Cơ chế resolver mặc định sử dụng manager này để tìm các cache có tên `books`.
4. Với key từ `#p0`, Spring kiểm tra cache hit/miss rồi thực thi hành vi của `@Cacheable`.

Lựa chọn manager thường là **tĩnh theo cấu hình của operation**. Nếu cùng một method cần chọn backend theo `tenantId`, `region` hoặc loại dữ liệu trong **mỗi lời gọi**, việc chỉ viết `cacheManager = "..."` không tự thực hiện routing runtime đó.

### 3.1. Ví dụ bean manager

```java
@Bean("libraryCacheManager")
CacheManager libraryCacheManager() {
    return new ConcurrentMapCacheManager("books");
}
```

*Đoạn minh họa nằm bên trong một lớp cấu hình Spring; cần import `CacheManager`, `ConcurrentMapCacheManager` và `@Bean`.*

Trong ví dụ này, bean tên `libraryCacheManager` quản lý một cache local `books`. Tên `books` không phải tên bean manager. Cách tạo cache thật và cấu hình TTL, serialization, kích thước hay kết nối backend là trách nhiệm của CacheManager/provider.

### 3.2. Khi nào chỉ định `cacheManager`?

Nên dùng khi:

- Một application có **nhiều manager** (ví dụ RAM local và Redis), nhưng từng phương thức dùng một manager cố định.
- Cần method A dùng manager này, method B dùng manager khác mà không cần điều kiện runtime.
- Cần override cấu hình manager mặc định trên một operation hoặc một lớp cụ thể.

Không cần custom `CacheResolver` nếu nhu cầu chỉ là chọn một bean manager cố định. Hãy tránh tăng độ phức tạp chỉ để thay thế việc chọn manager trực tiếp.

## 4. `cacheResolver`: tự giải quyết cache theo từng invocation

`CacheResolver` là một interface trong gói `org.springframework.cache.interceptor`. Phương thức chính:

```java
Collection<? extends Cache> resolveCaches(
    CacheOperationInvocationContext<?> context
);
```

*Đây là chữ ký API để giải thích; không phải một class Java độc lập.*

`context` cung cấp thông tin operation và lời gọi. Một custom resolver có thể dựa trên:

- `context.getArgs()`: đối số đầu vào, như `tenantId`, `region`, `premium`.
- `context.getOperation()`: metadata cache operation, trong đó có những cache name được khai báo (nếu có).
- `context.getMethod()` và `context.getTarget()`: method và đối tượng đích.
- Cấu hình môi trường, chính sách routing hoặc registry manager của ứng dụng.

Ví dụ dùng một resolver đã đăng ký:

```java
@Cacheable(
    cacheResolver = "routingResolver",
    key = "#p0"
)
public Book findBook(String id, String region) {
    return repository.find(id, region);
}
```

*Đoạn minh họa; `Book` và `repository` chưa được định nghĩa.*

Ở đây **không bắt buộc chỉ định `cacheNames` trên annotation** nếu custom resolver tự chọn được cache phù hợp. Điều này đã được Spring hỗ trợ từ Spring Framework 4.1. Nhưng **không có nghĩa được bỏ mọi cấu hình**: resolver vẫn phải trả về những đối tượng `Cache` thực sự hợp lệ và đảm bảo key/scope phù hợp với dữ liệu.

Resolver có thể chọn **nhiều cache** cho một operation; việc lookup/put và tính nhất quán giữa các cache sẽ theo cơ chế Spring Cache, nên không nên trả một danh sách tùy tiện nếu các vùng cache có ngữ nghĩa khác nhau. Với multi-tenant, cần bảo đảm cách giải quyết cache không làm lộ kết quả của tenant này cho tenant khác.

### 4.1. Cơ chế mặc định thực ra vẫn có resolver

Dùng `cacheManager` **không đồng nghĩa Spring bỏ qua `CacheResolver`**. Spring Cache thường tạo `SimpleCacheResolver` dùng manager đã cấu hình để lấy các cache theo `cacheNames` của operation. Custom resolver chỉ cần khi muốn **thay thế logic lựa chọn** ấy.

Vì vậy sơ đồ đúng là:

```text
Có cacheManager?
    '-- Spring dựng/sử dụng resolver mặc định dựa trên manager

Có cacheResolver tùy chỉnh?
    '-- Spring dùng resolver đó để chọn Cache object trực tiếp
```

Không phải:

```text
cacheManager -> cache implementation
cacheResolver -> một cache implementation khác, độc lập hoàn toàn
```

Một resolver có thể sử dụng chính CacheManager như dependency. Sự khác biệt là **ai quyết định cache đích, lúc nào và theo dữ liệu nào**.

## 5. Ràng buộc loại trừ: không khai báo cả hai ở cùng operation

### 5.1. Ví dụ **SAI**

```java
// SAI: một @Cacheable khai báo đồng thời hai cơ chế resolution
@Cacheable(
    cacheNames = "books",
    cacheManager = "libraryCacheManager",
    cacheResolver = "routingResolver",
    key = "#p0"
)
public Book findBook(String id) {
    return repository.find(id);
}
```

*Đoạn trên cố ý sai về cấu hình Spring, không dùng trong demo chạy được.*

Spring sẽ **báo lỗi khi xử lý cache operation**, bởi vì một resolver tùy chỉnh có quyền tự quyết định cache đích; nếu vẫn khai báo một manager riêng cùng operation, manager đó có thể bị bỏ qua, gây hiểu nhầm. Spring không âm thầm trộn hai chiến lược.

**Không nên khẳng định cứng thời điểm exception ở mọi trường hợp:** tùy quá trình phân tích metadata, bean initialization và khi operation được kích hoạt, lỗi có thể xuất hiện trong lúc khởi tạo hoặc khi lời gọi lần đầu đi qua cache advice. Điều quan trọng là đây **không phải một cấu hình hợp lệ** để triển khai.

### 5.2. Cách sửa 1 — Chỉ dùng `cacheManager`

```java
@Cacheable(cacheNames = "books", cacheManager = "libraryCacheManager",
           key = "#p0")
public Book findBook(String id) {
    return repository.find(id);
}
```

Nếu mỗi lời gọi đều dùng manager `libraryCacheManager` và cache `books`, cách này gọn nhất.

### 5.3. Cách sửa 2 — Chỉ dùng `cacheResolver`

```java
@Cacheable(cacheResolver = "routingResolver", key = "#p0")
public Book findBook(String id) {
    return repository.find(id);
}
```

Resolver chịu trách nhiệm cung cấp cache. Nếu cần tên `books`, có thể khai báo `cacheNames = "books"` để resolver lấy từ operation, hoặc để resolver chọn dựa trên quy tắc nội bộ.

### 5.4. “Hai thuộc tính xuất hiện trong cùng codebase” vẫn có thể hợp lệ

Ràng buộc là **cùng một operation**, không phải “cả ứng dụng chỉ được có đúng một trong hai”. Ví dụ **hợp lệ**:

```java
@Service
public class BookService {
    @Cacheable(cacheNames = "books", cacheManager = "fastCacheManager")
    public Book findFast(String id) {
        return repository.find(id);
    }

    @Cacheable(cacheResolver = "routingResolver")
    public Book findRouted(String id) {
        return repository.find(id);
    }
}
```

*Đoạn minh họa, `Book` và `repository` chưa có định nghĩa.*

Hai method khai báo **hai cache operation riêng**, mỗi operation chọn **một** chiến lược; không vi phạm mutual exclusion.

Cũng cần lưu ý rằng `key` và `keyGenerator` là một cặp thuộc tính có tính loại trừ tương tự ở cấp operation, nhưng đây là **vấn đề tạo khóa**, không phải chọn manager/resolver.

## 6. `@CacheConfig` và độ ưu tiên cấp lớp–cấp phương thức

`@CacheConfig` có thể thiết lập mặc định về `cacheNames`, `keyGenerator`, `cacheManager`, `cacheResolver`. Nó **không tự kích hoạt cache operation**. Spring cho phép override giá trị mặc định của lớp bằng cấu hình cụ thể ở operation.

Ví dụ:

```java
@Service
@CacheConfig(
    cacheNames = "books",
    cacheManager = "libraryCacheManager"
)
public class BookService {
    @Cacheable(key = "#p0")
    public Book findById(String id) {
        return repository.find(id);
    }

    @Cacheable(cacheResolver = "routingResolver", key = "#p0")
    public Book findForRegion(String id, String region) {
        return repository.findForRegion(id, region);
    }
}
```

*Đoạn minh họa; các kiểu/domain chưa được khai báo.*

- `findById` không chỉ định resolver/manager ở operation nên dùng **mặc định cấp lớp**: manager `libraryCacheManager` và cache name `books`.
- `findForRegion` chỉ định **`cacheResolver = "routingResolver"` ở operation**; custom resolver **override lựa chọn manager mặc định từ `@CacheConfig`**. Đây **không phải** “cả `cacheManager` lẫn `cacheResolver` trên cùng một annotation”.
- Với method dùng custom resolver, cache name `books` kế thừa từ class chỉ là metadata mà resolver có thể sử dụng; **custom resolver quyết định đối tượng cache thực tế**.

Chiều ngược lại cũng hợp lệ về ý tưởng override:

```java
@CacheConfig(cacheResolver = "routingResolver")
public class BookService {
    @Cacheable(cacheNames = "books", cacheManager = "libraryCacheManager")
    public Book findFixed(String id) {
        return repository.find(id);
    }
}
```

Ở đây operation-level `cacheManager` override class-level resolver mặc định. Quy tắc ưu tiên là **operation → class → global**. Không nên đặt song song cả manager và resolver trong **một operation**; nếu cần override, thực hiện rõ ở cấp operation.

| Cấp khai báo | Ví dụ | Cách diễn giải |
| --- | --- | --- |
| Global | `CachingConfigurer` cung cấp manager/resolver mặc định | Dùng khi class/operation không override |
| Class | `@CacheConfig(cacheManager = "libraryCacheManager")` | Giá trị mặc định cho các cache operation trong class |
| Operation | `@Cacheable(cacheResolver = "routingResolver")` | Lựa chọn riêng, ưu tiên hơn class default |
| Cùng operation | `@Cacheable(cacheManager = "x", cacheResolver = "y")` | **Không hợp lệ** |

Để tránh nhập nhằng về ràng buộc loại trừ, hãy luôn đánh giá **effective configuration của từng operation**, thay vì chỉ đếm xem hai chuỗi `cacheManager` và `cacheResolver` xuất hiện ở đâu trong source code.

## 7. Ví dụ Java 17+ chạy được với hai CacheManager và một custom CacheResolver

Ví dụ sau dùng Java 17+, Maven, Spring Boot **3.3.5** và hai `ConcurrentMapCacheManager` độc lập. Không cần cài Redis; mục đích là thấy **manager cố định** khác **resolver chọn manager theo đối số lúc chạy** như thế nào.

Thiết kế:

- `cacheManager`: manager cơ sở, chứa `books` và `routedBooks`.
- `premiumCacheManager`: manager dành cho premium, có một cache `routedBooks` **riêng**.
- `@CacheConfig(cacheNames="books", cacheManager="cacheManager")`: default cho class.
- `standard(id)`: `@Cacheable` sử dụng manager mặc định của class.
- `bySegment(id, premium)`: `@Cacheable(cacheNames="routedBooks", cacheResolver="routingResolver")` override manager của class. Resolver chọn **cache có cùng tên `routedBooks`** trên một trong hai manager dựa vào đối số thứ hai.
- Tất cả các lời gọi đều thông qua Spring bean proxy nên annotation có hiệu lực.

### 7.1. Cấu trúc

```text
cache-resolution-demo/
├── pom.xml
└── src/main/java/example/resolution/
    ├── ResolutionApplication.java
    └── BookLookupService.java
```

### 7.2. File `pom.xml`

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
    <artifactId>cache-resolution-demo</artifactId>
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

### 7.3. File `src/main/java/example/resolution/BookLookupService.java`

```java
package example.resolution;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
@CacheConfig(cacheNames = "books", cacheManager = "cacheManager")
public class BookLookupService {
    private final AtomicInteger standardReads = new AtomicInteger();
    private final AtomicInteger routedReads = new AtomicInteger();

    // Dùng manager và cache name từ @CacheConfig.
    @Cacheable(key = "#p0")
    public String standard(String id) {
        System.out.println(
            "BODY standard #" + standardReads.incrementAndGet() + " " + id
        );
        return "STD:" + id;
    }

    // Custom resolver override manager mặc định của class.
    @Cacheable(
        cacheNames = "routedBooks",
        cacheResolver = "routingResolver",
        key = "#p0"
    )
    public String bySegment(String id, boolean premium) {
        String segment = premium ? "VIP" : "BASE";
        System.out.println(
            "BODY routed #" + routedReads.incrementAndGet()
            + " " + id + " " + segment
        );
        return segment + ":" + id;
    }
}
```

### 7.4. File `src/main/java/example/resolution/ResolutionApplication.java`

```java
package example.resolution;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.CacheResolver;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class ResolutionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResolutionApplication.class, args);
    }

    @Bean("cacheManager")
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books", "routedBooks");
    }

    @Bean("premiumCacheManager")
    CacheManager premiumCacheManager() {
        return new ConcurrentMapCacheManager("routedBooks");
    }

    @Bean("routingResolver")
    CacheResolver routingResolver(
        @Qualifier("cacheManager") CacheManager baseManager,
        @Qualifier("premiumCacheManager") CacheManager premiumManager
    ) {
        return context -> {
            // Resolver này chỉ dùng cho method bySegment(id, premium).
            boolean premium = Boolean.TRUE.equals(context.getArgs()[1]);

            // Tên được lấy từ @Cacheable(cacheNames="routedBooks").
            String cacheName = context.getOperation()
                                      .getCacheNames()
                                      .iterator()
                                      .next();

            CacheManager selected = premium ? premiumManager : baseManager;
            Cache selectedCache = Objects.requireNonNull(
                selected.getCache(cacheName),
                "Missing cache: " + cacheName
            );
            return List.of(selectedCache);
        };
    }

    @Bean
    CommandLineRunner demo(
        BookLookupService books,
        @Qualifier("cacheManager") CacheManager baseManager,
        @Qualifier("premiumCacheManager") CacheManager premiumManager
    ) {
        return args -> {
            System.out.println("STANDARD1 => " + books.standard("A"));
            System.out.println("STANDARD2 => " + books.standard("A"));

            System.out.println("BASE1 => " + books.bySegment("R", false));
            System.out.println("BASE2 => " + books.bySegment("R", false));

            System.out.println("VIP1 => " + books.bySegment("R", true));
            System.out.println("VIP2 => " + books.bySegment("R", true));

            Cache baseCache = Objects.requireNonNull(
                baseManager.getCache("routedBooks")
            );
            Cache premiumCache = Objects.requireNonNull(
                premiumManager.getCache("routedBooks")
            );

            System.out.println(
                "BASE_ENTRY => " +
                Objects.requireNonNull(baseCache.get("R")).get()
            );
            System.out.println(
                "VIP_ENTRY => " +
                Objects.requireNonNull(premiumCache.get("R")).get()
            );
        };
    }
}
```

*Lưu ý:* Import `java.util.Collection` ở đây không cần thiết để biên dịch ví dụ; Java cho phép import không được sử dụng. Có thể xóa import đó khi định dạng code theo dự án.

### 7.5. Chạy ứng dụng

Dùng JDK 17+, Maven và kết nối đến Maven repository nếu dependency chưa có sẵn:

```bash
mvn spring-boot:run
```

Những dòng do ví dụ in ra theo thứ tự dưới đây; Spring Boot còn in log khởi động riêng:

```text
BODY standard #1 A
STANDARD1 => STD:A
STANDARD2 => STD:A
BODY routed #1 R BASE
BASE1 => BASE:R
BASE2 => BASE:R
BODY routed #2 R VIP
VIP1 => VIP:R
VIP2 => VIP:R
BASE_ENTRY => BASE:R
VIP_ENTRY => VIP:R
```

### 7.6. Vì sao output thể hiện đúng hai chiến lược?

**STANDARD1:** method `standard("A")` lấy cache name `books` và manager `cacheManager` từ `@CacheConfig`. Lần đầu miss nên method chạy, in `BODY standard #1 A`, trả `STD:A` và lưu vào cache.

**STANDARD2:** cùng cache/key, hit. Method body không chạy, nên không có dòng `BODY standard #2 A`.

**BASE1:** `bySegment("R", false)` chọn operation-level `routingResolver`, nên không dùng manager class-level làm lựa chọn cố định. Resolver thấy `premium=false`, trả `baseManager.getCache("routedBooks")`. Cache đó chưa có key `R`, nên method chạy và trả `BASE:R`.

**BASE2:** resolver lại chọn cache cơ sở; key `R` đã có nên hit, không chạy lại method.

**VIP1:** tham số `premium=true` khiến resolver chọn **manager khác**: `premiumCacheManager`. Dù tên cache vẫn là `routedBooks` và key vẫn là `R`, đây là một đối tượng cache **khác**. Vì thế miss và method chạy, trả `VIP:R`.

**VIP2:** resolver chọn cùng cache premium nên hit, không chạy method. Hai dòng `BASE_ENTRY` và `VIP_ENTRY` chứng minh key `R` tồn tại độc lập trên hai cache do hai manager khác nhau quản lý.

**Điều kiện để demo hoạt động:** `@EnableCaching` bật Spring cache advice; tên bean `routingResolver` khớp annotation; hai manager đều có cache `routedBooks`; `CommandLineRunner` gọi bean `BookLookupService` được Spring inject nên đi qua proxy; `#p0` là tham số `id`. Chương trình dùng `ConcurrentMapCacheManager` để trình diễn trong một JVM, không ngụ ý Redis hoặc cache nhiều node.

Nếu đem cơ chế này vào hệ thống thật, **boolean premium không phải dữ liệu xác thực quyền**. Phân loại/tenant routing phải lấy từ nguồn đáng tin và có kiểm tra quyền ở lớp phù hợp; cache routing không thay thế authorization.

## 8. Tại sao chọn một cache name chưa đủ khi có nhiều CacheManager?

Trong demo, cả hai manager đều có cache tên `routedBooks`:

```text
cacheManager
    '-- routedBooks["R"] = "BASE:R"

premiumCacheManager
    '-- routedBooks["R"] = "VIP:R"
```

Hai entry có **cùng cache name** và **cùng key** nhưng thuộc **hai instance khác nhau**, vì manager/backend khác nhau. Đây là lý do khi debug không nên chỉ hỏi “cache tên gì?”, mà còn phải xác định:

- Bean `CacheManager` thực sự được sử dụng là bean nào?
- Nếu custom resolver: nó chọn cache instance nào ở lời gọi này?
- Backend/namespace có dùng chung giữa các manager không?
- Key có gồm đủ thông tin tenant, loại dữ liệu, phiên bản và quyền truy cập không?

Có thể hai manager khác nhau cùng trỏ đến **một backend/namespace** tùy cấu hình; ngược lại hai cache có cùng tên nhưng nằm ở hai manager local cũng có thể hoàn toàn độc lập. Không được mặc định rằng “cùng tên” = “cùng nơi lưu”, hoặc “khác bean” = “cách ly dữ liệu bảo mật”.

## 9. Các trường hợp ràng buộc và lỗi thường gặp

### 9.1. Dùng cả hai thuộc tính trên cùng annotation

```java
// KHÔNG HỢP LỆ
@CachePut(
    cacheNames = "books",
    cacheManager = "libraryCacheManager",
    cacheResolver = "routingResolver"
)
public Book save(Book book) {
    return repository.save(book);
}
```

`@CachePut` ở đây chỉ để minh họa rằng mutual exclusion không chỉ áp dụng cho `@Cacheable`. Đừng dùng cách này cho `@CacheEvict` hoặc operation khác có cùng cặp thuộc tính.

### 9.2. Nhầm `cacheNames` với `cacheManager`

```java
// "books" là cache name, "libraryCacheManager" là bean manager
@Cacheable(cacheNames = "books", cacheManager = "libraryCacheManager")
public Book find(String id) {
    return repository.find(id);
}
```

Nếu bean `libraryCacheManager` không tồn tại hoặc manager không có cache `books`, Spring có thể báo lỗi lúc chạy. Không nên sửa bằng cách đổi hai giá trị cho nhau.

### 9.3. Tưởng resolver bắt buộc trả đúng một cache

`CacheResolver` trả về một **collection** cache; có thể là nhiều cache nếu operation và ứng dụng thực sự cần. Tuy nhiên, một resolver không nên trả tập cache rỗng hoặc các vùng cache sai ngữ nghĩa; nhiều operation cần ít nhất một cache và Spring có thể báo lỗi nếu không resolve được cache cần thiết.

### 9.4. Dùng custom resolver nhưng vẫn nghĩ `cacheNames` bắt buộc

Spring cho phép bỏ `cacheNames` khi custom resolver tự chọn vùng cache. Nhưng nếu **resolver được viết để đọc `context.getOperation().getCacheNames()`**, giống demo, thì phương thức **phải cung cấp cache name** hoặc resolver phải có một fallback an toàn; không nên gọi `iterator().next()` trên collection rỗng.

### 9.5. Custom resolver không xét đầy đủ đối số ảnh hưởng kết quả

Giả sử method trả dữ liệu theo `region` và `locale`, nhưng resolver chỉ chọn vùng theo `region` trong khi key chỉ là `id`; những lời gọi locale khác nhau có thể lấy sai kết quả. Phải thiết kế **cache routing và cache key** cùng phản ánh mọi chiều dữ liệu ảnh hưởng đầu ra.

### 9.6. Gọi method nội bộ, bỏ qua proxy

`@Cacheable`/`@CachePut`/`@CacheEvict` cần được Spring intercept. Trong **proxy mode** mặc định, lời gọi từ cùng object qua `this.method()` bỏ qua proxy, bất kể manager/resolver được cấu hình đúng đến đâu.

### 9.7. Tưởng `cacheManager` hay `cacheResolver` bật cache tự động

Hai thuộc tính chỉ là cấu hình của một cache operation. Cần có annotation operation, hạ tầng `@EnableCaching` (hoặc tương đương), bean resolver/manager tồn tại và lời gọi thực sự qua Spring proxy. `@CacheConfig(cacheManager="...")` đặt đơn lẻ trên class cũng **không tự biến method thành cacheable**.

### 9.8. Chọn sai thời điểm đánh giá

Custom resolver có thể nhận ngữ cảnh **đối số lúc gọi**. Không mặc định rằng resolver có quyền đọc `#result` như một biểu thức sau khi method trả về; `CacheOperationInvocationContext` không phải SpEL evaluation context chứa return value. Nếu chọn vùng dựa trên dữ liệu chỉ xuất hiện sau khi method chạy, cần thiết kế lại kiến trúc hoặc operation phù hợp thay vì dựa vào một `#result` không tồn tại ở thời điểm tra cache.

### 9.9. Nhầm lỗi cache provider với lỗi cấu hình mutual exclusion

Một operation chọn cả manager và resolver là **sai cấu hình**. Còn một operation chỉ chọn resolver hợp lệ nhưng resolver gọi `getCache(name)` và nhận null là **lỗi resolution/backend**. Cần đọc stack trace và metadata thực tế thay vì coi chúng như một nguyên nhân.

## 10. Thiết kế và kiểm thử đúng cho hệ thống thật

Khi cần chọn vùng cache, có thể dùng checklist này:

1. **Một manager cố định đủ không?** Nếu đủ, dùng `cacheNames` cùng `cacheManager` khi cần chỉ rõ bean.
2. **Có nhiều manager nhưng mỗi method luôn gắn với một manager không?** Dùng `cacheManager` trên từng operation hoặc `@CacheConfig` làm mặc định cấp lớp.
3. **Cache phải thay đổi theo tham số runtime không?** Dùng một `CacheResolver` rõ ràng; không gán đồng thời `cacheManager` cùng operation.
4. **Bean có tồn tại và đúng kiểu không?** `cacheManager` cần bean `CacheManager`; `cacheResolver` cần bean `CacheResolver`.
5. **Cache name có thực sự được resolve không?** Với resolver mặc định, kiểm tra `cacheNames`; với custom resolver, kiểm tra collection `Cache` được trả về.
6. **Key có đủ chiều phân tách dữ liệu không?** Tenant, customer tier, locale, region, version... phải được tính khi có ảnh hưởng kết quả.
7. **Lời gọi có qua proxy không?** Tránh self-invocation trong cấu hình mặc định; chú ý phương thức không-public và các bean tự tạo ngoài context.
8. **Kết quả đọc/ghi/xóa có cùng chiến lược không?** `@Cacheable`, `@CachePut` và `@CacheEvict` cần resolve đúng cùng vùng dữ liệu khi nghiệp vụ yêu cầu nhất quán.
9. **Có concurrency và invalidation không?** Nếu ghi ở manager A nhưng đọc ở manager B, cả hai cache có thể không tự đồng bộ; phải thiết kế invalidation đúng backend/scope.
10. **Kiểm thử cache hit/miss trên từng nhánh routing:** kiểm tra vừa số lần thân method chạy, vừa nội dung trong từng cache instance.

### Bảng chọn phương án

| Yêu cầu | Phương án |
| --- | --- |
| Một manager chung cho ứng dụng | Global default CacheManager/CacheResolver |
| Chọn manager cố định cho một method | `@Cacheable(cacheManager="...")` hoặc annotation operation tương ứng |
| Nhiều method trong một class dùng chung manager | `@CacheConfig(cacheManager="...")` cộng method-level operations |
| Chọn vùng theo tenant/region/feature flag lúc chạy | `@Cacheable(cacheResolver="...")` với custom resolver |
| Chỉ định cả manager và resolver trên cùng operation | **Không được**; chọn một |
| Method không có cache operation | Không tự được cache chỉ vì có `@CacheConfig` hoặc bean manager |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `cacheNames = "books"` khác `cacheManager = "libraryManager"` ra sao?

**Đáp án:** `books` là tên cache logic mà operation cần; `libraryManager` là tên bean manager có thể tìm cache đó. Manager không phải chính entry hoặc tên cache.

**Câu 2.** Khi nào cần custom `CacheResolver` thay vì `cacheManager`?

**Đáp án:** Khi việc chọn `Cache` phụ thuộc ngữ cảnh runtime hoặc logic phức tạp mà resolver mặc định dựa trên tên cache và manager cố định không đủ đáp ứng.

**Câu 3.** Vì sao `@Cacheable(cacheManager="x", cacheResolver="y")` không hợp lệ?

**Đáp án:** Hai thuộc tính là hai phương án chọn cache loại trừ nhau trên **cùng operation**. Một custom resolver có thể bỏ qua manager x, nên Spring từ chối cấu hình nhập nhằng.

**Câu 4.** Lớp khai báo `@CacheConfig(cacheManager="x")`, method có `@Cacheable(cacheResolver="y")`. Có phải cấu hình sai không?

**Đáp án:** Không. `@CacheConfig` chỉ là **mặc định cấp lớp**; lựa chọn `cacheResolver` ở **cấp operation** override lựa chọn manager mặc định đó. Khác với việc đặt cả hai thuộc tính trong chính `@Cacheable`.

**Câu 5.** Một custom resolver trả `Cache` từ manager A hoặc manager B theo `premium`. Cả hai cache đều có tên `routedBooks` và key `R`. Chúng có chắc là một entry không?

**Đáp án:** Không. Tên giống nhau không đủ kết luận cache instance giống nhau; phụ thuộc backend, namespace và manager. Trong demo hai `ConcurrentMapCacheManager` độc lập nên dữ liệu tách biệt.

**Câu 6.** Nếu một operation không khai báo `cacheNames` nhưng custom resolver biết chọn cache, có hợp lệ không?

**Đáp án:** Có thể hợp lệ. Spring cho phép resolver xác định cache mà không cần tên cache trên annotation. Tuy vậy, resolver phải thực sự cung cấp cache hợp lệ; nếu code của resolver tự đọc `cacheNames` thì cần điều chỉnh khi danh sách trống.

**Câu 7.** Cấu hình `@CacheConfig(cacheResolver="routingResolver")` trên class mà không có method-level cache operation có tự cache các method không?

**Đáp án:** Không. `@CacheConfig` chỉ cung cấp metadata mặc định cho operation có khai báo; không tự tạo hành vi caching.

## Tài liệu tham khảo chính thức

- Spring Framework Reference — *Default Cache Resolution* và *Custom Cache Resolution*, giải thích `cacheManager`, `cacheResolver` và mutual exclusion: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `@Cacheable`, các thuộc tính `cacheManager` và `cacheResolver`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework Javadoc — `@CacheConfig`, mặc định và độ ưu tiên cấp operation: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/CacheConfig.html
- Spring Framework Javadoc — `CacheResolver`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/interceptor/CacheResolver.html
- Spring Framework Javadoc — `SimpleCacheResolver`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/interceptor/SimpleCacheResolver.html
