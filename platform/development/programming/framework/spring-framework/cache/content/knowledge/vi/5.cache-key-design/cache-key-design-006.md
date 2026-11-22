# Chọn đầy đủ tham số thực sự làm thay đổi kết quả — Thiết kế khóa Spring Cache

## Mục tiêu học tập

Sau bài này, bạn sẽ biết cách xác định **những đầu vào thực sự ảnh hưởng đến kết quả** của một phương thức, biểu diễn chúng thành cache key, phát hiện tham số ẩn ngoài chữ ký method, tránh lấy nhầm dữ liệu giữa tenant/người dùng, và kiểm chứng tính đúng đắn bằng ví dụ Spring Boot Java 17+.

Nguyên tắc của chủ đề **Thiết kế khóa**: **nếu hai lời gọi có thể trả hai kết quả nghiệp vụ khác nhau trong cùng thời gian cache còn hợp lệ, chúng phải có hai khóa khác nhau trong cùng cache**. Nếu chỉ khác thông tin dùng để log hoặc theo dõi request mà kết quả vẫn tương đương, chúng nên dùng chung key.

## 1. “Tham số làm thay đổi kết quả” nghĩa là gì?

Giả sử ứng dụng hiển thị sản phẩm bằng phương thức:

```text
getProductView(productId, tenantId, languageTag, currency,
               membershipTier, traceId) → ProductView
```

Hệ thống có nhiều cửa hàng, nhiều ngôn ngữ, giá theo đơn vị tiền và hạng thành viên. Ta cần tự hỏi: **nếu giữ mọi thứ khác như cũ và chỉ thay đổi một tham số, kết quả có thể thay đổi không?**

| Tham số | Có thể thay đổi kết quả? | Quyết định |
| --- | --- | --- |
| `productId` | Có: sản phẩm khác. | Phải có trong key. |
| `tenantId` | Có: mỗi cửa hàng có thể có sản phẩm, giá hoặc quyền xem khác. | Phải có khi dữ liệu phân vùng theo tenant. |
| `languageTag` | Có: bản dịch hoặc cách trình bày thay đổi. | Phải có khi method trả về nội dung bản địa hóa. |
| `currency` | Có: đơn vị/giá quy đổi thay đổi. | Phải có nếu ảnh hưởng giá trị trả về. |
| `membershipTier` | Có: mức giá hoặc ưu đãi theo hạng khách hàng. | Phải có nếu áp dụng pricing theo tier. |
| `traceId` | Không, nếu chỉ ghi log/correlation. | Bỏ khỏi key. |

Vậy một biểu diễn đúng về mặt ý nghĩa có thể là:

```text
ProductViewKey(tenantId, productId, languageTag, currency, membershipTier)
```

Đừng mặc định “key là tất cả tham số” hoặc “key chỉ là ID”. Quyết định dựa trên **hợp đồng đầu ra** của phương thức và các ngữ cảnh tác động đến nó.

Ta có thể viết khái quát `result = f(businessInputs, context, sourceState)`. Key biểu diễn các input/context cần phân biệt; thay đổi của `sourceState` (database, bảng giá, cấu hình) còn cần chiến lược TTL, invalidation hoặc versioning.

## 2. Điều kiện đúng đắn: không được gộp hai kết quả khác nhau

Ký hiệu `K(x)` là cache key cho lời gọi `x` và `R(x)` là kết quả nghiệp vụ. Trong phạm vi một cache và khoảng thời gian cho phép tái sử dụng entry, ta cần:

```text
K(x) == K(y)  ⇒  R(x) tương đương R(y) theo hợp đồng nghiệp vụ.
```

“Tương đương” không chỉ là tên sản phẩm trông giống nhau: giá, quyền truy cập, đơn vị tiền, thứ tự dữ liệu, phân trang, ngôn ngữ và các field trả về cũng thuộc hợp đồng nếu API có công bố.

Hai lỗi phổ biến:

- **Thiếu key component (under-keying):** hai lời gọi lẽ ra có kết quả khác nhau lại cùng key, gây trả sai thông tin; khi có dữ liệu riêng theo user/tenant, đây có thể là lỗi lộ dữ liệu.
- **Thừa key component (over-keying):** hai lời gọi có thể dùng chung entry lại tạo key khác nhau, ví dụ chỉ vì `requestId` ngẫu nhiên. Cache hit thấp, tăng entry, memory và tải nguồn.

**Ưu tiên đúng dữ liệu hơn tỷ lệ hit.** Một hit rate cao không có giá trị nếu entry đến từ ngữ cảnh sai.

## 3. Cách tìm đủ các input ảnh hưởng kết quả

Không chỉ kiểm tra tham số method. Từ code service, repository, policy và các lời gọi ngoài, lập danh sách những yếu tố có thể ảnh hưởng **nội dung hoặc quyền xem** kết quả:

1. **Định danh dữ liệu:** product ID, category ID, warehouse ID, organization/tenant.
2. **Điều kiện truy vấn:** filter, search query, sort, page, size, field selection, include/exclude flags. Ví dụ cùng category nhưng `includeOutOfStock=true` phải khác kết quả false.
3. **Ngữ cảnh người dùng:** danh tính, role, scope quyền, nhóm khách hàng. Không phải lúc nào cũng cần user ID; chỉ cần khi đầu ra phụ thuộc user hoặc phạm vi của họ.
4. **Bản địa hóa:** language, region, timezone, currency, tax region nếu chúng ảnh hưởng đầu ra.
5. **Chính sách/phiên bản:** experiment cohort, feature flag, pricing rule, schema/API version nếu cùng cache có nhiều phiên bản kết quả không tương thích.
6. **Dữ liệu nguồn thay đổi theo thời gian:** giá, tỷ giá, tồn kho, trạng thái đơn, khuyến mãi. Xác định có cần thêm snapshot/version vào key hay kiểm soát bằng invalidation/TTL.
7. **Tham số phục vụ hạ tầng:** traceId, spanId, correlationId, logging tag thường không cần nếu không tác động kết quả. Với timeout/retry, phải xét chúng có làm thay đổi fallback/giá trị trả về hay không.

Cần xác minh cả **đường đi của dữ liệu**. Ví dụ controller truyền vào user ID, service lấy tenant từ ThreadLocal, repository thêm filter theo tenant. Nếu key chỉ có product ID, cache hit sẽ bỏ qua thân phương thức nên filter theo tenant không còn được chạy cho request đó.

### Ngữ cảnh ẩn là nguồn lỗi nguy hiểm

Ví dụ anti-pattern:

```java
// Minh họa sai; Product và TenantContext là các kiểu giả định.
@Cacheable(cacheNames = "visibleProducts", key = "#p0")
public List<Product> getVisibleProducts(String categoryId) {
    String tenantId = TenantContext.currentTenant();
    // Truy vấn dữ liệu theo categoryId VÀ tenantId...
}
```

Cùng category ở hai tenant có thể dùng chung key và trả dữ liệu của tenant trước. Tương tự khi method đọc `SecurityContextHolder`, `LocaleContextHolder`, clock, feature flag, current currency hoặc một policy từ cấu hình.

**Ưu tiên chuyển phụ thuộc thực sự quan trọng thành input tường minh**, ví dụ `VisibleProductsKey(tenantId, categoryId, languageTag, scope)`, tạo sau khi xác thực và chuẩn hóa. Khi đầu ra mang tính ngẫu nhiên hoặc thay đổi quá nhanh, có thể không nên cache phương thức đó.

**Đặc biệt về bảo mật:** key đủ tenant/user scope không thay thế kiểm tra quyền. Nếu kiểm tra quyền chỉ nằm *bên trong* method có `@Cacheable`, cache hit có thể bỏ qua chính kiểm tra ấy. Đặt kiểm tra quyền ở đường gọi luôn thực thi trước cached method, và chỉ trả dữ liệu phù hợp phạm vi được xác thực. Tránh dùng access token, password hoặc session secret thô làm key hay ghi chúng vào log.

## 4. Spring Cache tạo key mặc định như thế nào?

Spring Cache dùng `SimpleKeyGenerator` theo quy tắc mặc định:

- Không tham số: `SimpleKey.EMPTY`.
- Một tham số: dùng chính đối tượng tham số đó làm key.
- Nhiều tham số: tạo `SimpleKey` chứa tất cả đối số.

Cách này tốt nếu mọi tham số đều cần phân biệt và chúng có `equals/hashCode` ổn định. Nhưng nếu chữ ký có `traceId` hoặc `requestId` chỉ dùng quan sát, key mặc định chứa chúng sẽ làm miss không cần thiết. Và framework không tự nhận ra biến tenant/locale/role được đọc từ context ở bên trong method.

Spring cho phép chỉ định key bằng **SpEL**:

```java
@Cacheable(cacheNames = "catalogViews", key = "#p0")
public String describe(CacheKey businessKey, String requestId) {
    // ...
}
```

`#p0` (hoặc `#a0`) là đối số thứ nhất. Dùng chỉ số khi không muốn phụ thuộc việc trình biên dịch có giữ tên tham số hay không. Nếu nhiều method cần cùng quy tắc phức tạp, có thể dùng bean `KeyGenerator` tùy chỉnh; thuộc tính `key` và `keyGenerator` không được chỉ định đồng thời trên cùng cache operation.

Một cách sạch để tránh phép nối string dễ va chạm là gói các thành phần nghiệp vụ vào Java `record`. Record bất biến có `equals/hashCode` theo từng component, thích hợp làm key cho cache bộ nhớ khi các component cũng ổn định.

## 5. Ví dụ Spring Boot Java 17+ — phân biệt đủ ngữ cảnh, bỏ qua trace

Ví dụ có thể chạy trong **dự án Spring Boot Gradle có sẵn** với Java 17+ và dependency cache starter. Dữ liệu trả về được tạo từ các field của key để quan sát rõ, không cần database.

Thêm vào `build.gradle` (giữ phiên bản plugin và các dependencies khác đang có):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
```

**File `src/main/java/example/keys/CacheKey.java`:**

```java
package example.keys;

import java.util.Objects;

public record CacheKey(
        String tenantId,
        String productId,
        String languageTag,
        String priceTier
) {
    public CacheKey {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(productId, "productId");
        Objects.requireNonNull(languageTag, "languageTag");
        Objects.requireNonNull(priceTier, "priceTier");
    }
}
```

Các field trong `CacheKey` đều thay đổi kết quả của demo. `record` bảo đảm hai instance có cùng bốn component được xem là bằng nhau theo `equals/hashCode`.

**File `src/main/java/example/keys/CacheConfiguration.java`:**

```java
package example.keys;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalogViews");
    }
}
```

`ConcurrentMapCacheManager` là backend đơn giản trong một JVM để quan sát hành vi, không tự cung cấp TTL/giới hạn dung lượng mặc định.

**File `src/main/java/example/keys/CatalogService.java`:**

```java
package example.keys;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final AtomicInteger sourceReads = new AtomicInteger();

    @Cacheable(cacheNames = "catalogViews", key = "#p0")
    public String describe(CacheKey key, String requestId) {
        System.out.println("SOURCE_READ #" + sourceReads.incrementAndGet());
        return key.tenantId() + "/" + key.productId() + "/"
                + key.languageTag() + "/" + key.priceTier();
    }

    public int sourceReadCount() {
        return sourceReads.get();
    }
}
```

`requestId` chỉ là tham số metadata của request, không ảnh hưởng giá trị trả về nên `key="#p0"` loại nó khỏi cache key. Bộ đếm chỉ tăng khi thân `describe` chạy thực sự.

**File `src/main/java/example/keys/KeyDemoApplication.java`:**

```java
package example.keys;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class KeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(KeyDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(CatalogService service) {
        return args -> {
            CacheKey vietnamese = new CacheKey("shopA", "P42", "vi-VN", "standard");
            CacheKey english = new CacheKey("shopA", "P42", "en-US", "standard");
            CacheKey premium = new CacheKey("shopA", "P42", "vi-VN", "premium");
            CacheKey secondTenant = new CacheKey("shopB", "P42", "vi-VN", "standard");

            System.out.println("1: " + service.describe(vietnamese, "req-1"));
            System.out.println("2: " + service.describe(
                    new CacheKey("shopA", "P42", "vi-VN", "standard"), "req-2"));
            System.out.println("3: " + service.describe(english, "req-3"));
            System.out.println("4: " + service.describe(premium, "req-4"));
            System.out.println("5: " + service.describe(secondTenant, "req-5"));
        };
    }
}
```

Chạy trong dự án:

```bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
```

Các dòng `System.out` của demo xuất hiện theo thứ tự (không kể log khởi động Spring):

```text
SOURCE_READ #1
1: shopA/P42/vi-VN/standard
2: shopA/P42/vi-VN/standard
SOURCE_READ #2
3: shopA/P42/en-US/standard
SOURCE_READ #3
4: shopA/P42/vi-VN/premium
SOURCE_READ #4
5: shopB/P42/vi-VN/standard
```

| Lượt | Điều thay đổi | Hành vi |
| --- | --- | --- |
| 1 | Key mới, lần đầu | Miss, thân method chạy (`#1`). |
| 2 | Record mới nhưng cùng bốn field; requestId khác | Hit, không chạy lại thân method. |
| 3 | Thay ngôn ngữ `vi-VN` → `en-US` | Miss (`#2`), nội dung khác. |
| 4 | Thay hạng `standard` → `premium` | Miss (`#3`), nội dung khác. |
| 5 | Thay tenant `shopA` → `shopB` | Miss (`#4`), không lấy cache của tenant trước. |

Nếu bỏ biểu thức `key = "#p0"` trong ví dụ này, key mặc định của method hai tham số sẽ chứa cả `requestId`. Lượt 2 vì thế sẽ miss dù cùng kết quả nghiệp vụ.

**Phạm vi demo:** không mô phỏng transaction, quyền truy cập, TTL và cập nhật dữ liệu thật. `@EnableCaching` chỉ có tác dụng khi gọi method qua proxy của bean do Spring quản lý; tự gọi `this.describe(...)` trong cùng service có thể bỏ qua interceptor ở cấu hình proxy mặc định. Ví dụ là nhiều file Java trong dự án Spring Boot, không phải một file độc lập để chạy bằng `javac`.

## 6. Phản ví dụ: key chỉ có ID làm trả sai giữa tenant

```java
// SAI khi kết quả phụ thuộc cả tenant, locale và tier!
@Cacheable(cacheNames = "catalogViews", key = "#productId")
public ProductView get(String productId, String tenantId,
                       String languageTag, String priceTier) {
    // Logic trả sản phẩm theo bốn tham số...
}
```

`ProductView` chỉ là kiểu minh họa. Khi `get("P42", "shopA", "vi-VN", "standard")` đã ghi entry key `P42`, request `get("P42", "shopB", "en-US", "premium")` có thể hit key đó và nhận dữ liệu của shopA. Thân method không chạy nên logic dựa trên ba tham số còn lại bị bỏ qua.

Không thể sửa **thiếu thành phần key** bằng `unless` hay chỉ giảm TTL. Cần thay đổi hợp đồng key trước: dùng một record đúng đủ field, hoặc `KeyGenerator` với cấu trúc key không nhập nhằng; đồng thời bảo đảm authorization vẫn được kiểm tra trước cached method. Nếu chứng minh được kết quả là danh mục công khai giống nhau cho mọi tenant/locale, key có thể được đơn giản hóa, nhưng đó là quyết định nghiệp vụ có bằng chứng.

## 7. Chuẩn hóa và tính ổn định của cache key

Chọn đúng field là điều kiện cần; cách biểu diễn field cũng rất quan trọng.

- **Chuẩn hóa dữ liệu trước khi tạo key:** `usd`/`USD`, `vi-vn`/`vi-VN`, giá trị mặc định của filter/sort, whitespace thừa. Chỉ chuẩn hóa theo quy tắc miền; không tùy tiện lowercase ID phân biệt hoa/thường.
- **Key bất biến:** dùng `record`, value object bất biến. Nếu key là object mutable, thay đổi field sau khi đưa vào hash-based map có thể làm lookup thất bại.
- **`equals/hashCode` có nghĩa:** hai input được xem là cùng key khi thực sự cùng ý nghĩa. Object mới mỗi request với identity equality mặc định có thể làm miss dù field giống nhau.
- **Không nối chuỗi sơ sài:** tuple `("a:b","c")` và `("a","b:c")` đều có thể tạo chuỗi `a:b:c` nếu chỉ nối bằng dấu `:`. Dùng record/tuple hoặc encoding có phân cách rõ ràng.
- **Cache name là namespace:** hai phương thức dùng cùng cache/key nhưng trả kiểu hoặc ý nghĩa khác nhau có thể xung đột. Đặt tên cache phù hợp hoặc tách domain/version của key.
- **Backend cần được kiểm chứng:** record làm key cho `ConcurrentMapCacheManager` rất thuận tiện. Với Redis/distributed cache, xem serializer/conversion/prefix/key schema và yêu cầu tương thích giữa các instance.
- **Không đưa bí mật vào key/log:** token, password, thông tin phiên nhạy cảm không phải lựa chọn key an toàn. Dùng định danh/phạm vi nghiệp vụ tối thiểu sau xác thực.

## 8. Khác nhau giữa key đầy đủ và dữ liệu mới nhất

Ngay cả khi key hoàn hảo, nguồn dữ liệu vẫn có thể đổi. Chẳng hạn cùng `CacheKey("shopA","P42","vi-VN","standard")` nhưng bảng giá hôm nay đã khác hôm qua.

- Dùng `@CacheEvict` sau khi update/delete thành công để đọc lại ở lượt sau, phối hợp **đúng tên cache và cùng định nghĩa key**.
- Dùng `@CachePut` khi phương thức cập nhật nguồn và trả kết quả tương ứng với entry được cache; kiểm tra ngữ nghĩa key giữa read/write.
- Đặt TTL/expiry qua cache provider khi chấp nhận dữ liệu có thể cũ trong giới hạn.
- Dùng `catalogVersion` hoặc snapshot ID như một key component **nếu** hợp đồng truy vấn có version và yêu cầu đọc lại theo từng snapshot.
- Nếu dữ liệu cần chính xác thời gian thực hoặc kết quả thay đổi liên tục, cân nhắc không cache.

Không thêm `Instant.now()` vào key mỗi lần đọc để “tránh stale”: việc đó tạo key mới liên tục và làm cache gần như vô ích. Với dữ liệu phụ thuộc ngày kinh doanh, có thể dùng khóa theo ngày *khi nghiệp vụ cho phép*, đồng thời xử lý timezone, expiry và cập nhật giữa ngày.

Khi cập nhật trong transaction, evict quá sớm có thể khiến request khác nạp lại dữ liệu cũ trước commit. Cần thiết kế invalidation phù hợp transaction và kiểm tra race condition nếu yêu cầu nhất quán cao; annotation không tự bảo đảm mọi trường hợp.

## 9. Kế hoạch kiểm thử key đúng đủ

Nên tạo test theo **cặp lời gọi chỉ đổi đúng một biến**, reset cache phù hợp để đo chính xác số lần truy cập nguồn:

| Trường hợp | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Một key gọi hai lần | Dùng hai record có field bằng nhau. | Lần đầu miss, lần hai hit; nguồn chỉ chạy một lần. |
| Đổi tenant | Cùng product/lang/tier; tenant khác. | Miss độc lập; không trả dữ liệu tenant trước. |
| Đổi locale | Cùng product/tenant/tier; lang khác. | Miss và trả bản dịch đúng. |
| Đổi currency hoặc tier | Chỉ một thành phần pricing thay đổi. | Key khác; trả đúng giá. |
| Đổi request ID | Mọi input nghiệp vụ giữ nguyên. | Hit; số lần đọc nguồn không tăng. |
| Đổi filter/sort/page | Một điều kiện truy vấn đổi. | Nếu kết quả có thể khác thì key phải khác. |
| Đổi user/scope/flag ẩn | Thay ngữ cảnh có tác động kết quả hoặc quyền. | Không dùng lại entry sai; kiểm tra quyền vẫn chạy. |
| Dữ liệu nguồn update | Thay giá/tên/tồn kho. | Evict/put/TTL theo hợp đồng, không stale ngoài giới hạn. |
| Đầu vào tương đương | Hai biểu diễn được chuẩn hóa theo quy tắc chung. | Dùng cùng key và cùng kết quả. |

Các phép đo hữu ích sau khi đúng dữ liệu: cache hit/miss, số query nguồn, latency, số lượng entry, memory, thời gian tồn tại dữ liệu cũ. **Không đánh đổi correctness hoặc phân quyền để tăng hit rate.**

## 10. Checklist trước khi đưa cache vào service thật

1. Viết ra rõ điều gì quyết định giá trị trả về; rà soát cả tham số và context ẩn.
2. Đổi từng đầu vào, chứng minh khi nào đầu ra có thể khác hoặc cần giới hạn quyền.
3. Đưa tất cả yếu tố có tác động vào key, bỏ những tham số chỉ phục vụ log/tracing.
4. Chuẩn hóa giá trị tương đương; key bất biến và có equality/hash ổn định.
5. Xác minh key generation SpEL/`KeyGenerator`, tên cache, khả năng xung đột giữa các phương thức.
6. Kiểm tra provider, serializer, TTL, update/eviction, thay đổi nguồn và transaction.
7. Đảm bảo authorization chạy cả khi hit; không dùng secret làm key.
8. Có test đồng nhất key, phân biệt tenant/locale/tier, traceId, thay đổi dữ liệu và behavior sau invalidation.

## Tài liệu chính thống

- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
