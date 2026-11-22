# Thiết kế tên cache và biểu thức khóa bằng SpEL

Trong Spring Boot, **Spring Cache** cho phép ứng dụng khai báo việc lưu và tái sử dụng kết quả phương thức bằng các annotation như `@Cacheable`, `@CachePut` và `@CacheEvict`. Khi dùng **Spring Data Redis**, `RedisCacheManager` có thể triển khai những cache đó trên Redis, cho phép nhiều instance ứng dụng sử dụng chung dữ liệu cache.

Một cấu hình cache đúng không chỉ cần Redis hoạt động. Ứng dụng phải trả lời được hai câu hỏi:

1. **Tên cache (cache name) biểu diễn tập dữ liệu nào?** Chẳng hạn hồ sơ sản phẩm theo ID, giá đã tính theo đơn vị tiền hoặc kết quả tìm kiếm.
2. **Khóa cache (cache key) phân biệt những kết quả nào?** Nếu cùng phương thức có thể trả kết quả khác nhau theo tenant, ngôn ngữ, loại tiền hay quyền truy cập, những yếu tố đó phải được xem xét trong khóa.

Đặt tên cache quá chung hoặc viết biểu thức SpEL thiếu tham số có thể khiến ứng dụng trả **dữ liệu sai**, thậm chí trả dữ liệu thuộc tenant khác. Ngược lại, một khóa đưa vào quá nhiều thông tin không ổn định sẽ làm tỷ lệ cache hit thấp, khó xóa đúng bản ghi và tạo nhiều key trong Redis.

Bài học giải thích cách phối hợp **`cacheNames`, `key` và cấu hình Redis key prefix**, cách viết biểu thức **Spring Expression Language (SpEL)**, và cách thiết kế cache để việc đọc, cập nhật, xóa, phân vùng và nâng cấp dữ liệu giữ được tính nhất quán.

## 1. Một kết quả cache được xác định bởi tên cache và khóa

Xét dịch vụ tra cứu sản phẩm:

~~~java
@Cacheable(cacheNames = "catalog.productById.v1", key = "#productId")
public ProductView findProduct(String productId) {
    return repository.findProduct(productId);
}
~~~

Ở đây:

- `cacheNames = "catalog.productById.v1"` chọn **vùng cache logic** do Spring Cache quản lý.
- `key = "#productId"` là biểu thức SpEL; Spring đánh giá biểu thức với các tham số của lời gọi phương thức và dùng kết quả làm cache key.
- Nếu cache đã có một giá trị hợp lệ cho cặp *(tên cache, khóa)*, Spring thường trả kết quả đã lưu mà không gọi phần thân phương thức.
- Nếu chưa có, Spring gọi phương thức, rồi lưu kết quả theo chính sách của cache và các thuộc tính annotation.

Mô hình:

~~~text
   Lời gọi findProduct("p-42")
                 |
                 v
        Cache Interceptor
                 |
                 +--> cacheNames = catalog.productById.v1
                 |
                 +--> key SpEL = "p-42"
                 |
                 v
           RedisCacheManager
                 |
                 v
    Redis key: catalog.productById.v1::p-42
                 |
         +-------+--------+
         |                |
      Cache hit        Cache miss
         |                |
         v                v
    Trả giá trị       Gọi repository
                          |
                          v
                      Ghi cache
                          |
                          v
                      Trả giá trị
~~~

Với cấu hình `RedisCacheConfiguration` mặc định dùng prefix tên cache, Redis key thường có dạng:

~~~text
<cacheName>::<cacheKey>
~~~

Ví dụ `catalog.productById.v1::p-42`. Đây là cách Spring Data Redis tạo không gian key trong cấu hình thông thường, không phải cú pháp bắt buộc của Redis. Ứng dụng có thể tùy biến prefix, cách chuyển key thành chuỗi và serializer.

**Cache name không phải Redis key hoàn chỉnh.** Cache name là định danh logic trong Spring; cache key là kết quả của biểu thức SpEL hoặc `KeyGenerator`; `RedisCacheManager` kết hợp hai thành phần đó và serializer/prefix để xác định key vật lý.

## 2. Đặt tên cache theo ý nghĩa và vòng đời dữ liệu

Tên cache nên mô tả **loại kết quả được lưu** và có quy tắc nhất quán giữa các service. Ví dụ:

| Tên cache | Dữ liệu dự kiến | Ngữ nghĩa |
| --- | --- | --- |
| `catalog.productById.v1` | Một sản phẩm theo ID | Đối tượng chi tiết sản phẩm |
| `catalog.productPrice.v1` | Giá tính cho sản phẩm và đơn vị tiền | Có thể có TTL ngắn hơn thông tin sản phẩm |
| `catalog.categoryTree.v1` | Cây danh mục theo ngôn ngữ | Dữ liệu đọc thường xuyên, ít thay đổi |
| `account.profileById.v1` | Hồ sơ tài khoản | Có yêu cầu phân quyền và vô hiệu hóa riêng |
| `catalog.searchPage.v1` | Kết quả tìm kiếm có filter/page/sort | Nhiều biến thể khóa, dễ tăng số lượng key |

Một quy ước có thể là:

~~~text
<boundedContext>.<resultType>.v<schemaVersion>
~~~

Trong đó:

- **Bounded context**: khu vực nghiệp vụ sở hữu dữ liệu, chẳng hạn `catalog` hoặc `account`.
- **Result type**: loại kết quả cần cache, chẳng hạn `productById`, `categoryTree`, `searchPage`.
- **Version**: phiên bản khi cấu trúc dữ liệu hoặc ngữ nghĩa cache thay đổi không tương thích.

Không cần gắn phiên bản mới cho mỗi lần sửa code; version hữu ích khi bản cache cũ có thể bị đọc sai bởi ứng dụng mới. Ví dụ giá trị trước đây là chuỗi JSON tự viết, phiên bản mới là object với cấu trúc khác; đổi tên cache sang `catalog.productById.v2` tạo một namespace mới, tránh va chạm trong giai đoạn triển khai cuốn chiếu.

### Đặt cache name quá chung gây ra vấn đề gì?

Ví dụ:

~~~java
@Cacheable(cacheNames = "data", key = "#id")
public ProductView product(String id) { ... }

@Cacheable(cacheNames = "data", key = "#id")
public CustomerView customer(String id) { ... }
~~~

Hai phương thức đang chia sẻ **cùng tên cache và cùng biểu thức khóa**. Nếu cùng nhận `"42"`, chúng có thể dùng chung một mục cache dù dữ liệu thực tế hoàn toàn khác nhau. Điều này có thể gây lỗi ép kiểu, lỗi deserialize hoặc trả sai dữ liệu.

Tách thành `catalog.productById.v1` và `account.customerById.v1` giúp mỗi loại kết quả có không gian riêng. Không nên dựa vào tên class Java hay tên phương thức để tự động phân biệt khi đã chỉ định cùng một `cacheNames` và `key`.

### Tránh đưa thông tin có độ biến thiên cao vào tên cache

Thông thường không nên tạo cache name như `catalog.product.p-42`, `catalog.product.p-43` cho từng sản phẩm. Những giá trị biến thiên theo bản ghi nên nằm trong **key**, còn cache name diễn đạt nhóm dữ liệu có cùng chính sách.

Điều này giúp cấu hình TTL, prefix, metric và thao tác xóa theo cache name rõ ràng hơn. Với dữ liệu đa tenant, cách tách theo tenant có thể được thiết kế ở prefix hoặc key; việc tạo hàng nghìn cache name động cần có lý do quản lý rõ ràng.

## 3. Biểu thức SpEL trong `@Cacheable`

Spring sử dụng SpEL để tính khóa ở thời điểm gọi phương thức. Những biểu thức thường gặp:

~~~java
// Khóa bằng một tham số.
@Cacheable(cacheNames = "catalog.productById.v1", key = "#productId")
public ProductView findById(String productId) { ... }

// Khóa kết hợp các tham số.
@Cacheable(
    cacheNames = "catalog.productById.v1",
    key = "#tenantId + ':' + #productId"
)
public ProductView findByTenantAndId(
        String tenantId, String productId) { ... }

// Chỉ lấy một thuộc tính của đối tượng tham số.
@Cacheable(cacheNames = "catalog.productById.v1", key = "#request.productId")
public ProductView find(ProductRequest request) { ... }

// Dùng chỉ số tham số, không phụ thuộc metadata tên tham số Java.
@Cacheable(cacheNames = "catalog.productById.v1", key = "#p0")
public ProductView findByIdWithIndex(String productId) { ... }
~~~

Các tham chiếu trong SpEL:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `#productId` | Tham số phương thức có tên `productId`, nếu tên tham số khả dụng |
| `#p0` hoặc `#a0` | Tham số thứ nhất, chỉ số bắt đầu từ 0 |
| `#p1` hoặc `#a1` | Tham số thứ hai |
| `#root.args[0]` | Đối số thứ nhất theo ngữ cảnh gốc |
| `#root.methodName` | Tên phương thức được cache |
| `#root.targetClass` | Lớp đích của lời gọi |
| `#request.productId` | Thuộc tính `productId` của đối tượng tham số `request` |
| `#request?.productId` | Truy cập property an toàn khi `request` có thể là `null` |
| `T(java.util.Locale).ROOT` | Tham chiếu tới hằng `Locale.ROOT` qua toán tử type của SpEL |

Để dùng `#productId` theo tên, Java phải lưu metadata tên tham số để Spring đọc được, thường thông qua tùy chọn compiler `-parameters`. Nếu dự án không đảm bảo điều đó, các alias `#p0`, `#a0`, `#root.args[0]` có thể giúp tránh việc SpEL không tìm được tên biến.

Ví dụ Gradle Groovy nếu cần bật rõ ràng:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += '-parameters'
}
~~~

Với Spring Boot, cần kiểm tra cấu hình build thực tế vì plugin/toolchain có thể đã áp dụng tùy chọn này. Không nên bật trùng vô ích chỉ vì một đoạn ví dụ.

### Nếu bỏ trống `key` thì chuyện gì xảy ra?

Spring Cache sử dụng `KeyGenerator` mặc định, thường là `SimpleKeyGenerator`:

- Không có đối số: một khóa đặc biệt `SimpleKey.EMPTY`.
- Có đúng một đối số: sử dụng chính đối số đó làm khóa.
- Có từ hai đối số: tạo `SimpleKey` từ toàn bộ các đối số.

Ví dụ:

~~~java
@Cacheable("catalog.productById.v1")
public ProductView findById(String id) { ... }
~~~

Với một `String id`, khóa mặc định có thể hoàn toàn phù hợp. Tuy nhiên, khi phương thức nhận một object mutable, `Pageable`, một request DTO chứa trường không ảnh hưởng kết quả, hoặc các tham số không có cấu trúc bằng nhau ổn định, khóa mặc định có thể kém rõ ràng. Với các API nghiệp vụ quan trọng, biểu thức SpEL tường minh thường giúp người bảo trì hiểu cache identity ngay trên phương thức.

## 4. Nguyên tắc cốt lõi: cùng đầu vào có ý nghĩa phải cho cùng khóa

Một cache key tốt phải thỏa hai điều:

1. **Ổn định**: hai lời gọi tương đương về nghiệp vụ tạo cùng khóa.
2. **Đủ phân biệt**: hai lời gọi có thể tạo kết quả khác nhau không vô tình tạo cùng khóa.

Ví dụ một phương thức tính giá:

~~~java
public PriceView calculatePrice(
    String tenantId,
    String productId,
    String currency,
    String membershipTier
) { ... }
~~~

Nếu tính giá phụ thuộc cả bốn yếu tố, khóa `#productId` là sai. Hai khách hàng có tier khác nhau hoặc hai đồng tiền khác nhau có thể nhận giá của nhau.

Một biểu thức rõ ràng:

~~~java
@Cacheable(
    cacheNames = "catalog.productPrice.v1",
    key = "'tenant=' + #tenantId"
        + " + ';product=' + #productId"
        + " + ';currency=' + #currency"
        + " + ';tier=' + #membershipTier"
)
public PriceView calculatePrice(
        String tenantId,
        String productId,
        String currency,
        String membershipTier) { ... }
~~~

Đoạn mã nối chuỗi Java annotation trong cách viết trên nhằm tạo một biểu thức SpEL duy nhất. Một cách đơn giản hơn là viết toàn bộ một dòng:

~~~java
@Cacheable(cacheNames = "catalog.productPrice.v1",
    key = "'t=' + #tenantId + ';p=' + #productId + ';c=' + #currency + ';tier=' + #membershipTier")
public PriceView calculatePrice(
    String tenantId, String productId, String currency, String membershipTier
) { ... }
~~~

Ví dụ khóa có thể trở thành:

~~~text
t=shop-a;p=p-42;c=VND;tier=GOLD
t=shop-a;p=p-42;c=USD;tier=GOLD
t=shop-a;p=p-42;c=VND;tier=BASIC
~~~

Ba kết quả ở trên có định danh cache khác nhau.

**Lưu ý về dấu phân cách:** Nếu giá trị đầu vào tự do có thể chứa `;` hoặc `=`, phép nối chuỗi đơn giản có thể gây nhập nhằng. Trong hệ thống thực tế, cần ràng buộc/chuẩn hóa ID theo định dạng xác định hoặc sử dụng một `KeyGenerator` tạo khóa có mã hóa thành phần rõ ràng. Không nên giả định cách ghép chuỗi nào cũng không có va chạm.

### Những thứ thường bị quên trong key

| Yếu tố ảnh hưởng kết quả | Rủi ro nếu bỏ khỏi key |
| --- | --- |
| Tenant / tổ chức | Có thể đọc dữ liệu của tenant khác |
| Ngôn ngữ / locale | Trả bản dịch sai ngôn ngữ |
| Đơn vị tiền | Trả giá khác đơn vị |
| Phân khúc khách hàng / quyền truy cập | Trả dữ liệu không đúng quyền |
| Bộ lọc tìm kiếm | Kết quả bộ lọc này bị dùng cho bộ lọc khác |
| Trang và kích thước trang | Trang 2 dùng lại kết quả trang 1 |
| Trường sắp xếp và chiều sắp xếp | Trả danh sách sai thứ tự |
| Phiên bản quy tắc tính toán | Dùng kết quả được tạo theo quy tắc cũ |

Không phải yếu tố nào cũng nên trực tiếp thành một chuỗi trong Redis key. Chẳng hạn, quyền truy cập nhiều chiều có thể khiến số khóa tăng quá mạnh; với dữ liệu nhạy cảm, đôi khi **không cache kết quả theo user** là quyết định an toàn và đơn giản hơn. Trước hết phải xác định chính xác tập đầu vào thực sự ảnh hưởng đến kết quả.

## 5. Thiết kế cache đa tenant bằng tên cache và SpEL

Ví dụ một hệ thống cung cấp sản phẩm cho nhiều cửa hàng. Hai tenant có thể cùng dùng `productId = "p-42"` nhưng chứa thông tin sản phẩm khác nhau.

Thiết kế sai:

~~~java
@Cacheable(cacheNames = "catalog.productById.v1", key = "#productId")
public ProductView getProduct(String tenantId, String productId) {
    return store.findByTenantAndId(tenantId, productId)
        .orElse(null);
}
~~~

Vì `tenantId` bị bỏ khỏi khóa, hai lời gọi:

~~~text
getProduct("shop-a", "p-42")
getProduct("shop-b", "p-42")
~~~

cùng kiểm tra mục cache `catalog.productById.v1::p-42`. Nếu dữ liệu giữa hai tenant khác nhau, ứng dụng có thể trả sai dữ liệu.

Thiết kế tốt hơn:

~~~java
@Cacheable(
    cacheNames = "catalog.productById.v1",
    key = "'tenant=' + #tenantId + ';product=' + #productId",
    unless = "#result == null"
)
public ProductView getProduct(String tenantId, String productId) {
    return store.findByTenantAndId(tenantId, productId)
        .orElse(null);
}
~~~

Các khóa logic:

~~~text
tenant=shop-a;product=p-42
tenant=shop-b;product=p-42
~~~

Để cách này an toàn, `tenantId` phải là định danh đã được **xác thực** và **ủy quyền** trong ngữ cảnh request; không được mặc định người dùng có quyền truy vấn tenant chỉ vì họ gửi tenant ID trong URL. Cache key ngăn va chạm dữ liệu giữa tenant nhưng không thay thế kiểm tra phân quyền.

Nếu muốn ngăn dữ liệu nhạy cảm lộ qua Redis key, có thể dùng định danh nội bộ đã được chuẩn hóa hoặc mã hóa một chiều theo chính sách hệ thống. Không nên đưa token truy cập, số thẻ, thông tin cá nhân hoặc query nhạy cảm nguyên văn vào tên key chỉ để dễ debug.

## 6. Cách viết key cho bộ lọc, trang và sắp xếp

Với một endpoint tìm kiếm sản phẩm:

~~~java
public SearchPage search(
    String tenantId,
    String category,
    String locale,
    int page,
    int size,
    String sortBy,
    String sortDirection
) { ... }
~~~

Nếu kết quả phụ thuộc các tham số trên, khóa nên phản ánh chúng:

~~~java
@Cacheable(
    cacheNames = "catalog.searchPage.v1",
    key = "'t=' + #tenantId"
        + " + ';cat=' + #category"
        + " + ';lang=' + #locale"
        + " + ';page=' + #page"
        + " + ';size=' + #size"
        + " + ';sort=' + #sortBy"
        + " + ';dir=' + #sortDirection"
)
public SearchPage search(
        String tenantId, String category, String locale,
        int page, int size, String sortBy, String sortDirection) {
    // ...
}
~~~

Những biểu thức như `#page` và `#size` dùng giá trị số nhưng SpEL có thể nối chúng vào chuỗi khóa qua toán tử cộng chuỗi. Nên xác định giá trị hợp lệ và chuẩn hóa `sortBy`, `sortDirection` trước khi gọi phương thức được cache.

Tuy vậy, việc cache mọi tổ hợp tìm kiếm không phải lúc nào cũng có lợi: quá nhiều bộ lọc, nhiều trang và thứ tự làm **độ phân biệt của key (cardinality)** rất lớn. Khi mỗi truy vấn gần như chỉ được gọi một lần, cache hit thấp nhưng vẫn tiêu tốn bộ nhớ Redis. Với kết quả tìm kiếm, thường nên:

- Chỉ cache các bộ lọc phổ biến, trang đầu hoặc những câu hỏi được lặp lại nhiều.
- Đặt TTL ngắn hơn cache chi tiết sản phẩm nếu dữ liệu thay đổi thường xuyên.
- Giới hạn page/size và các biến thể sort được phép, tránh sinh key vô hạn từ input tùy ý.
- Chuẩn hóa những giá trị tương đương, ví dụ `"vi-VN"` và `"vi-vn"` theo một quy tắc thống nhất.

### Không đưa nguyên một đối tượng request mutable vào cache key nếu không cần

Ví dụ:

~~~java
@Cacheable(cacheNames = "catalog.searchPage.v1", key = "#request")
public SearchPage search(SearchRequest request) { ... }
~~~

Nếu `SearchRequest` là một class mutable không định nghĩa `equals` và `hashCode` theo nội dung, hoặc serializer chuyển object thành chuỗi không ổn định, hai request tương đương có thể không tạo cùng cache key. Ngay cả khi dùng record có equality theo field, request vẫn có thể chứa `traceId`, `timestamp` hoặc trường không ảnh hưởng kết quả, làm giảm hit rate.

Giải pháp là viết một biểu thức chọn đúng các thuộc tính ảnh hưởng kết quả hoặc tạo một kiểu khóa bất biến và `KeyGenerator` được thiết kế riêng.

## 7. Chuẩn hóa giá trị trước khi tạo cache key

Nếu hai đầu vào tương đương về nghiệp vụ nhưng khác cách viết, cache có thể bị phân mảnh:

~~~text
getBySku(" abc-42 ")
getBySku("ABC-42")
getBySku("abc-42")
~~~

Nếu hệ thống xác định SKU không phân biệt chữ hoa và khoảng trắng ở hai đầu, hãy chuẩn hóa theo một chính sách thống nhất **trước khi kiểm tra cache**:

~~~java
import java.util.Locale;

public String canonicalSku(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("sku must not be blank");
    }
    return raw.trim().toUpperCase(Locale.ROOT);
}
~~~

Có thể biểu diễn phép chuẩn hóa đơn giản ngay bằng SpEL:

~~~java
@Cacheable(
    cacheNames = "catalog.productBySku.v1",
    key = "#sku.trim().toUpperCase(T(java.util.Locale).ROOT)"
)
public ProductView getBySku(String sku) {
    // Nội dung phương thức vẫn cần dùng cùng quy tắc chuẩn hóa.
    return store.findBySku(canonicalSku(sku)).orElse(null);
}
~~~

Nhưng có một vấn đề thiết kế: nếu SpEL tự chuẩn hóa còn business logic xử lý theo quy tắc khác, khóa cache và truy vấn nguồn có thể không đồng nhất. Vì thế, với quy tắc phức tạp, nên chuẩn hóa dữ liệu **ở biên hệ thống hoặc service điều phối** rồi gọi phương thức được cache bằng giá trị đã chuẩn hóa.

Ví dụ:

~~~java
public ProductView lookupSku(String rawSku) {
    String canonical = canonicalSku(rawSku);
    return cachedCatalog.getByCanonicalSku(canonical);
}
~~~

`cachedCatalog` là **một bean Spring khác** để lời gọi đi qua Spring Cache proxy. Điều này cũng giúp tránh lỗi self-invocation được giải thích ở phần sau.

Đừng chuẩn hóa tùy tiện các identifier có phân biệt chữ hoa/chữ thường, ví dụ token, hash hoặc ID mà casing có ý nghĩa. Mọi quy tắc chuẩn hóa phải bắt nguồn từ hợp đồng nghiệp vụ.

## 8. Tùy biến tiền tố Redis key với `RedisCacheManager`

Trong một Redis instance dùng chung cho nhiều môi trường hoặc nhiều ứng dụng, chỉ dùng tên cache `catalog.productById.v1` có thể chưa đủ phân biệt phạm vi vận hành.

Có thể thêm prefix theo ứng dụng và môi trường:

~~~text
shop:prod:catalog.productById.v1::tenant=shop-a;product=p-42
shop:staging:catalog.productById.v1::tenant=shop-a;product=p-42
~~~

Ví dụ cấu hình Spring Boot / Spring Data Redis:

~~~java
package com.example.redis.cache;

import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory connectionFactory) {
        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .computePrefixWith(
                    cacheName -> "shop:prod:" + cacheName + "::"
                )
                .entryTtl(Duration.ofMinutes(10))
                .disableCachingNullValues();

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaults)
            .withCacheConfiguration(
                "catalog.productById.v1",
                defaults.entryTtl(Duration.ofMinutes(5))
            )
            .withCacheConfiguration(
                "catalog.searchPage.v1",
                defaults.entryTtl(Duration.ofSeconds(30))
            )
            .build();
    }
}
~~~

Ví dụ sử dụng cố định `shop:prod:` để làm rõ ý tưởng. Trong ứng dụng thực tế, prefix nên được nạp từ cấu hình môi trường đáng tin cậy, không hardcode `prod` rồi vô tình chạy trên staging. Một số hệ thống dùng Redis/Redis database riêng cho từng môi trường; prefix vẫn hữu ích để người vận hành phân biệt loại dữ liệu nhưng **không phải biện pháp cách ly bảo mật độc lập**.

Với cấu hình trên, `@Cacheable(cacheNames = "catalog.productById.v1", key = "'tenant=' + #tenantId + ';product=' + #productId")` tạo key vật lý tương đương:

~~~text
shop:prod:catalog.productById.v1::tenant=shop-a;product=p-42
~~~

**Tên cache cần đồng nhất** giữa annotation, `withCacheConfiguration(...)`, metric và thao tác invalidate. Nếu annotation trỏ `catalog.productsById.v1` trong khi cấu hình TTL dành cho `catalog.productById.v1`, Spring có thể sử dụng cache khác hoặc default configuration, dẫn tới TTL không như mong đợi.

### Đừng vô hiệu hóa prefix một cách tùy tiện

Spring Data Redis cho phép tùy biến hoặc tắt key prefix. Nếu vô hiệu hóa, hai cache logic khác nhau mà tạo cùng khóa có thể chồng lên nhau trong Redis, và thao tác clear theo cache có thể có ảnh hưởng khó kiểm soát tùy cấu hình. Giữ prefix rõ ràng là lựa chọn phù hợp cho đa số ứng dụng.

### Prefix, khóa và serializer là các lớp khác nhau

Tên cache và SpEL xác định *identity*; serializer quyết định cách chuyển key/value thành dữ liệu Redis. Đổi serializer hoặc định dạng object có thể khiến dữ liệu cũ không còn đọc được dù cache name và key không đổi. Khi thay đổi schema/serializer không tương thích, cân nhắc đổi version của cache name hoặc chiến lược migration/clear có kiểm soát.

## 9. `@Cacheable`, `@CachePut` và `@CacheEvict` phải dùng cùng hợp đồng khóa

Một lỗi phổ biến: đọc dùng khóa kết hợp tenant và product, nhưng cập nhật chỉ xóa theo product.

~~~java
// Đọc:
@Cacheable(
    cacheNames = "catalog.productById.v1",
    key = "'tenant=' + #tenantId + ';product=' + #productId"
)
public ProductView get(String tenantId, String productId) { ... }

// Sai: chỉ xóa theo productId, không khớp khóa đọc.
@CacheEvict(
    cacheNames = "catalog.productById.v1",
    key = "#productId"
)
public void update(String tenantId, String productId,
                   UpdateProductRequest request) { ... }
~~~

Sau cập nhật, mục cache cũ vẫn nằm tại key `tenant=shop-a;product=p-42`. Người dùng tiếp tục nhận dữ liệu cũ cho đến khi TTL hết hạn hoặc một cơ chế khác xóa mục đó.

Thiết kế nhất quán:

~~~java
@CacheEvict(
    cacheNames = "catalog.productById.v1",
    key = "'tenant=' + #tenantId + ';product=' + #productId"
)
public void update(String tenantId, String productId,
                   UpdateProductRequest request) {
    store.update(tenantId, productId, request);
}
~~~

Mặc định `@CacheEvict` thực hiện vô hiệu hóa sau khi phương thức hoàn thành thành công. Với thao tác ghi dữ liệu quan trọng, nên xác định thứ tự commit ở nguồn dữ liệu và thời điểm invalidate. Nếu một giao dịch database chưa commit nhưng cache đã xóa, một request khác có thể đọc dữ liệu cũ rồi ghi lại vào cache. Cách phối hợp cache với transaction cần được thiết kế theo khả năng chịu dữ liệu cũ của nghiệp vụ.

### `@CachePut` cần khớp chính xác khóa đọc

`@CachePut` luôn chạy phần thân phương thức và ghi kết quả vào cache theo key:

~~~java
@CachePut(
    cacheNames = "catalog.productById.v1",
    key = "'tenant=' + #tenantId + ';product=' + #result.id"
)
public ProductView save(String tenantId, ProductDraft draft) {
    return store.save(tenantId, draft);
}
~~~

Đối với `@CachePut`, kết quả phương thức có thể được dùng trong biểu thức `key` sau khi method chạy. Ví dụ chỉ đúng khi `store.save(...)` trả một `ProductView` khác `null` có thuộc tính `id`, và ID đó chính là ID mà `get` dùng.

Không dùng `#result` trong `@Cacheable.key` để xây cache lookup ban đầu: khi cần tra cache trước khi gọi phương thức, kết quả chưa tồn tại. Trong `@Cacheable`, `#result` có thể được dùng ở `unless` sau khi thực thi để quyết định có lưu hay không.

### Khi một thay đổi ảnh hưởng nhiều cache

Cập nhật sản phẩm có thể ảnh hưởng cả chi tiết sản phẩm và trang tìm kiếm:

~~~java
@Caching(evict = {
    @CacheEvict(
        cacheNames = "catalog.productById.v1",
        key = "'tenant=' + #tenantId + ';product=' + #productId"
    ),
    @CacheEvict(
        cacheNames = "catalog.searchPage.v1",
        allEntries = true
    )
})
public void updateProduct(
        String tenantId, String productId,
        UpdateProductRequest request) {
    store.update(tenantId, productId, request);
}
~~~

`allEntries = true` xóa **toàn bộ vùng cache logic** `catalog.searchPage.v1`, có thể ảnh hưởng mọi tenant trong vùng đó. Đây có thể là lựa chọn chấp nhận được cho cache nhỏ, TTL ngắn hoặc số lần cập nhật thấp, nhưng là thao tác tốn kém khi cache nhiều key. Nó cũng không đồng nghĩa chỉ xóa kết quả tìm kiếm của tenant hiện tại.

Nếu cần invalidate theo tenant hoặc danh sách truy vấn cụ thể, phải thiết kế cơ chế mapping/nhóm khóa riêng hoặc tránh cache một tập kết quả khó vô hiệu hóa chính xác. Không thể yêu cầu `@CacheEvict` tự suy ra tất cả bộ lọc có chứa sản phẩm vừa thay đổi.

## 10. Điều kiện `condition` và `unless`

Cache không phải lúc nào cũng phù hợp cho mọi lời gọi. Có thể dùng điều kiện SpEL:

~~~java
@Cacheable(
    cacheNames = "catalog.searchPage.v1",
    key = "'tenant=' + #tenantId + ';page=' + #page",
    condition = "#page == 0",
    unless = "#result == null"
)
public SearchPage firstPageOrOtherPage(String tenantId, int page) {
    return store.search(tenantId, page);
}
~~~

Trong ví dụ:

- `condition = "#page == 0"` được kiểm tra trước khi sử dụng cache; chỉ trang 0 mới đi qua logic cache.
- `unless = "#result == null"` được đánh giá sau khi phương thức trả kết quả, ngăn lưu kết quả `null`.
- Nếu `page != 0`, phương thức vẫn chạy nhưng không sử dụng cache cho lời gọi đó.

Không nên lấy `#result` làm căn cứ trong `condition` vì ở thời điểm quyết định dùng cache, phương thức có thể chưa được gọi. Với `unless`, cần nhớ nó không làm các lệnh phía sau “quay ngược thời gian”; đây chỉ là điều kiện có lưu kết quả vào cache hay không.

Nếu muốn cache sự vắng mặt của dữ liệu để tránh lặp lại truy vấn tốn kém (negative caching), cần thiết kế biểu diễn kết quả không tồn tại và TTL phù hợp. Ví dụ `unless = "#result == null"` sẽ **không** cache trường hợp không tìm thấy, khiến mỗi lần gọi đều truy cập nguồn dữ liệu.

## 11. Những nguồn dữ liệu không ổn định làm khóa cache sai lệch

### 11.1. Phụ thuộc vào đồng hồ

Ví dụ:

~~~java
@Cacheable(
    cacheNames = "catalog.discount.v1",
    key = "#productId + ':' + T(java.lang.System).currentTimeMillis()"
)
public DiscountView discount(String productId) { ... }
~~~

Biểu thức này tạo khóa gần như mới cho mỗi lời gọi; cache hầu như không được tái sử dụng. Nếu giá chiết khấu phụ thuộc một phiên chương trình khuyến mãi, hãy dùng **promotion ID/version** hoặc thời kỳ nghiệp vụ rõ ràng làm thành phần khóa, kết hợp TTL.

### 11.2. Dùng `toString()` của object không có hợp đồng ổn định

Nếu object dùng `Object.toString()` mặc định, chuỗi thường gắn với định danh instance trong JVM. Cùng dữ liệu nhưng hai object khác nhau có thể tạo hai key. Nếu cần mã hóa cấu trúc nhiều field, hãy dùng một key type bất biến với hợp đồng chuẩn hóa rõ ràng hoặc một `KeyGenerator`.

### 11.3. Dùng `hashCode()` làm định danh duy nhất

~~~java
@Cacheable(cacheNames = "catalog.searchPage.v1",
           key = "#request.hashCode()")
public SearchPage search(SearchRequest request) { ... }
~~~

`hashCode()` không phải định danh duy nhất và có thể va chạm. Một số cách tính hash còn phụ thuộc trạng thái mutable. Chỉ dùng hash trong cache key nếu thiết kế đã xử lý đầy đủ yêu cầu chống collision; một biểu diễn canonical của dữ liệu đầu vào thường minh bạch hơn.

### 11.4. Trộn tham số ẩn trong body phương thức

Ví dụ phương thức `getCurrentUserDashboard()` không nhận tham số nhưng lấy user hiện tại từ `SecurityContextHolder`:

~~~java
@Cacheable(cacheNames = "dashboard.v1")
public DashboardView getCurrentUserDashboard() { ... }
~~~

Vì phương thức không có đối số, khóa mặc định giống nhau cho mọi user. Nếu kết quả khác nhau theo tài khoản, điều này có thể gây rò rỉ dữ liệu. Cách thiết kế rõ ràng là truyền định danh user đã xác thực vào một **bean cache service**:

~~~java
@Cacheable(
    cacheNames = "account.dashboard.v1",
    key = "#userId"
)
public DashboardView getDashboard(String userId) { ... }
~~~

Quyền truy cập phải được kiểm tra ở ranh giới nghiệp vụ; việc đưa `userId` vào khóa chỉ phân biệt dữ liệu trong cache.

## 12. Khi SpEL quá phức tạp: dùng `KeyGenerator`

Một biểu thức SpEL dài dễ có lỗi nhập nhằng dấu phân cách hoặc bỏ quên tham số. Khi nhiều phương thức dùng chung quy tắc khóa, có thể tạo `KeyGenerator` riêng.

Ví dụ quy tắc **hai tham số String** gồm tenant ID và product ID. Để tránh va chạm khi ID chứa ký tự phân cách, encode từng thành phần bằng Base64 URL-safe:

~~~java
package com.example.redis.cache;

import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.stereotype.Component;

@Component("tenantProductKeyGenerator")
public class TenantProductKeyGenerator implements KeyGenerator {

    private static String encode(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Cache key component is blank");
        }
        return Base64.getUrlEncoder().withoutPadding()
            .encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }

    @Override
    public Object generate(Object target, Method method, Object... params) {
        if (params.length != 2
                || !(params[0] instanceof String tenantId)
                || !(params[1] instanceof String productId)) {
            throw new IllegalArgumentException(
                "Expected (String tenantId, String productId)"
            );
        }

        return "t:" + encode(tenantId) + ":p:" + encode(productId);
    }
}
~~~

Sử dụng:

~~~java
@Cacheable(
    cacheNames = "catalog.productById.v1",
    keyGenerator = "tenantProductKeyGenerator"
)
public ProductView getProduct(String tenantId, String productId) {
    // ...
}
~~~

Tương tự, phương thức `@CacheEvict` cho cùng cặp tham số phải dùng **chính KeyGenerator đó**, nếu không sẽ không xóa đúng mục cache:

~~~java
@CacheEvict(
    cacheNames = "catalog.productById.v1",
    keyGenerator = "tenantProductKeyGenerator"
)
public void invalidate(String tenantId, String productId) {
    // Thao tác nghiệp vụ hoặc chủ động invalidate.
}
~~~

Một annotation cache không nên đồng thời chỉ định `key` và `keyGenerator`; hãy chọn một cơ chế cho mỗi thao tác. Base64 trong ví dụ là **cách mã hóa tránh nhập nhằng**, không phải cơ chế mã hóa bảo mật: người có quyền đọc Redis key có thể giải mã nó. Nếu ID nhạy cảm, cần chiến lược bảo vệ riêng.

`KeyGenerator` nên có hợp đồng rõ ràng về thứ tự và kiểu tham số. Đổi thứ tự phương thức từ `(tenantId, productId)` thành `(productId, tenantId)` mà không sửa generator sẽ tạo khóa sai dù cả hai đều là `String`. Nếu dùng generator cho nhiều phương thức, cân nhắc một kiểu request ID rõ ràng hoặc kiểm thử hợp đồng đầu vào.

## 13. Ví dụ service với cache read và invalidate nhất quán

Ví dụ dưới tách service đọc và service cập nhật để làm rõ cơ chế Spring Cache Proxy.

~~~java
package com.example.redis.catalog;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogQueryService {

    private final ProductStore store;

    public CatalogQueryService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(
        cacheNames = "catalog.productById.v1",
        key = "'tenant=' + #tenantId + ';product=' + #productId",
        unless = "#result == null"
    )
    public ProductView getById(String tenantId, String productId) {
        return store.findByTenantAndId(tenantId, productId).orElse(null);
    }
}
~~~

~~~java
package com.example.redis.catalog;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;

@Service
public class CatalogCommandService {

    private final ProductStore store;

    public CatalogCommandService(ProductStore store) {
        this.store = store;
    }

    @CacheEvict(
        cacheNames = "catalog.productById.v1",
        key = "'tenant=' + #tenantId + ';product=' + #productId"
    )
    public void update(
            String tenantId,
            String productId,
            UpdateProductRequest request) {
        store.update(tenantId, productId, request);
    }
}
~~~

Giả sử `ProductStore` là abstraction truy cập dữ liệu chính:

~~~java
import java.util.Optional;

public interface ProductStore {
    Optional<ProductView> findByTenantAndId(
        String tenantId, String productId
    );

    void update(
        String tenantId, String productId,
        UpdateProductRequest request
    );
}
~~~

`ProductView` và `UpdateProductRequest` là các DTO/domain type của ứng dụng. Với Redis Cache dùng Java serialization mặc định, kiểu value cần tương thích với serializer được cấu hình; nhiều hệ thống chủ động chọn serializer JSON và kiểm soát schema/version để các instance đọc được dữ liệu lẫn nhau.

Luồng:

~~~text
          HTTP Controller / Application Service
                         |
                  +------+------+
                  |             |
                  v             v
         CatalogQueryService  CatalogCommandService
            getById(...)         update(...)
                  |                  |
                  v                  v
          @Cacheable          Ghi nguồn dữ liệu
                  |                  |
              Cache hit?             v
              /       \         @CacheEvict
            Có        Không          |
             |           |            |
         Dùng cache   ProductStore     |
                         |             |
                         v             v
                    Lưu cache     Xóa đúng cache key
~~~

**Lưu ý Spring AOP proxy:** Trong chế độ proxy thông thường, một phương thức gọi một phương thức `@Cacheable` khác **trong cùng instance bằng `this.method()`** sẽ không đi qua cache interceptor. Nên để điểm gọi được cache đi qua một Spring bean/proxy hoặc cấu trúc dịch vụ phù hợp. Chỉ có annotation trên phương thức chưa đủ nếu lời gọi thực tế bỏ qua proxy.

## 14. Kiểm thử khóa cache với Redis thật

Kiểm thử cache nên chứng minh ba thuộc tính:

1. Gọi lại cùng cặp tham số dùng kết quả cache, không gọi nguồn dữ liệu lần thứ hai.
2. Cùng `productId` nhưng khác `tenantId` là hai mục cache riêng.
3. Xóa cache cho một cặp tenant/product không làm mất mục của tenant khác.

Có thể xây dựng một integration test với Spring Boot, Testcontainers và một service đếm số lần thực thi. Service dưới trả chuỗi để ví dụ không phụ thuộc serializer của một DTO tùy biến.

~~~java
package com.example.redis.cachetest;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;

public class CountingCatalogService {

    private final AtomicInteger databaseCalls = new AtomicInteger();

    @Cacheable(
        cacheNames = "catalog.productById.v1",
        key = "'tenant=' + #p0 + ';product=' + #p1"
    )
    public String load(String tenantId, String productId) {
        databaseCalls.incrementAndGet();
        return tenantId + "/" + productId;
    }

    @CacheEvict(
        cacheNames = "catalog.productById.v1",
        key = "'tenant=' + #p0 + ';product=' + #p1"
    )
    public void invalidate(String tenantId, String productId) {
        // Chủ động xóa cache cho cặp định danh được chỉ định.
    }

    public int databaseCalls() {
        return databaseCalls.get();
    }
}
~~~

Trong ví dụ test dùng alias `#p0` và `#p1` để không phụ thuộc metadata tên tham số.

~~~java
package com.example.redis.cachetest;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(classes = CacheKeyIntegrationTest.TestApp.class)
class CacheKeyIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableCaching(proxyTargetClass = true)
    static class TestApp {
        @Bean
        CountingCatalogService countingCatalogService() {
            return new CountingCatalogService();
        }
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port", () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    CountingCatalogService service;

    @Test
    void keysMustSeparateTenantsAndMatchEviction() {
        String suffix = UUID.randomUUID().toString();
        String id = "product-" + suffix;
        String tenantA = "a-" + suffix;
        String tenantB = "b-" + suffix;

        int before = service.databaseCalls();

        assertThat(service.load(tenantA, id))
            .isEqualTo(tenantA + "/" + id);
        assertThat(service.load(tenantA, id))
            .isEqualTo(tenantA + "/" + id);

        // Cùng product ID nhưng tenant khác phải gọi nguồn lần nữa.
        assertThat(service.load(tenantB, id))
            .isEqualTo(tenantB + "/" + id);
        assertThat(service.databaseCalls() - before).isEqualTo(2);

        service.invalidate(tenantA, id);

        // Tenant B vẫn được cache.
        service.load(tenantB, id);
        assertThat(service.databaseCalls() - before).isEqualTo(2);

        // Tenant A phải tải lại sau invalidate.
        service.load(tenantA, id);
        assertThat(service.databaseCalls() - before).isEqualTo(3);

        // Chủ động dọn key tạo bởi test để không chờ TTL mặc định.
        service.invalidate(tenantA, id);
        service.invalidate(tenantB, id);
    }
}
~~~

Để chạy, dự án cần những dependency phù hợp, ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

Ở đây `@EnableCaching` kích hoạt cache interception; `RedisCacheManager` được Spring Boot auto-configure khi Redis Cache được chọn làm cache provider theo cấu hình ứng dụng. Nếu dự án có nhiều provider cache trên classpath, hãy cấu hình/chỉ định Redis Cache rõ ràng để integration test không vô tình kiểm thử một provider khác. Redis Testcontainers cần Docker hoặc môi trường container tương thích.

Với test cần kiểm chứng chính **tên Redis key vật lý**, có thể đọc key theo prefix trong Redis test riêng bằng `StringRedisTemplate` hoặc kiểm tra `CacheManager` được cấu hình, tránh kiểm thử dựa vào một định dạng key ngầm định khi dự án đã tùy biến prefix/serializer.

## 15. Những lỗi thường gặp khi đặt tên và viết SpEL

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Hai tenant nhận cùng sản phẩm cache | Khóa chỉ dùng `productId` | Đưa tenant ID đã xác thực vào khóa hoặc tách namespace đúng thiết kế |
| Thay đổi dữ liệu nhưng vẫn trả bản cũ | `@CacheEvict` dùng khác tên cache hoặc khác công thức key | Dùng cùng hợp đồng tên cache và key cho đọc/ghi/xóa |
| Biểu thức `#productId` không phân giải | Không có metadata tên tham số Java | Bật `-parameters` hoặc dùng `#p0` / `#a0` |
| Cache hit rất thấp dù dữ liệu ít đổi | Key chứa timestamp, trace ID hoặc object mutable | Chỉ dùng đầu vào ảnh hưởng kết quả và chuẩn hóa |
| Dùng cache key trống cho mọi user | Phương thức không có đối số nhưng lấy user từ context | Truyền định danh user/tenant có kiểm soát vào method được cache |
| Xóa cache tìm kiếm khiến nhiều tenant mất cache | Dùng `allEntries = true` trên cache name chung | Xem xét chính sách invalidate và mô hình read cache riêng |
| SpEL truy cập property của null bị lỗi | Không có validation hoặc truy cập không an toàn | Xác thực input, dùng `?.` hoặc default có ngữ nghĩa rõ ràng |
| Tham số bị nối chuỗi gây collision | Dấu phân cách xuất hiện trong dữ liệu đầu vào | Ràng buộc định dạng hoặc KeyGenerator với mã hóa thành phần |
| `@Cacheable` không chạy khi gọi từ cùng class | Self-invocation bỏ qua Spring AOP proxy | Tách bean hoặc gọi qua proxy theo kiến trúc đã chọn |
| Một instance giải mã cache của instance khác bị lỗi | Schema/serializer thay đổi nhưng dùng cùng key namespace | Version cache và quản lý triển khai/migration |
| Cache key ghi lộ thông tin nhạy cảm | Đưa token, email hay bộ lọc nhạy cảm nguyên văn vào key | Dùng ID nội bộ hoặc chiến lược mã hóa khóa phù hợp |
| Null result bị lưu/không lưu khác dự kiến | `unless`, cache configuration hoặc null-value policy | Quy định rõ negative caching và TTL |
| TTL sai dù đã khai báo cache cụ thể | Tên cache trong cấu hình khác `cacheNames` | Giữ hằng số/quy ước tên nhất quán và kiểm thử TTL |
| SpEL dựa vào `#result` trong lookup key | Kết quả chỉ có sau khi method chạy | Dùng tham số cho `@Cacheable.key`; `#result` chỉ nơi được hỗ trợ sau invocation |
| Cache search ngày càng lớn | Filter/page/sort tạo quá nhiều tổ hợp khóa | Giới hạn cardinality, giảm TTL hoặc chỉ cache truy vấn phổ biến |

## 16. Quy trình thiết kế trước khi thêm một cache mới

Một cách tiếp cận có hệ thống:

**Bước 1 — Xác định kết quả thực sự được cache.** Đây là entity theo ID, DTO đã dịch ngôn ngữ, bảng giá, danh sách hay dữ liệu phụ thuộc quyền? Không dùng chung cache name cho hai loại kết quả có ngữ nghĩa hoặc serializer khác nhau.

**Bước 2 — Liệt kê mọi đầu vào làm thay đổi kết quả.** Bao gồm các tham số rõ ràng và các yếu tố ngầm như tenant, user, locale, currency, phiên bản quy tắc, quyền truy cập, trạng thái đang hoạt động. Chỉ cache khi có cách xác định identity an toàn và ổn định.

**Bước 3 — Chọn tên cache có chủ sở hữu rõ ràng.** Ví dụ `catalog.productById.v1`. Thiết kế prefix theo ứng dụng/môi trường nếu Redis dùng chung, và đặt TTL phù hợp với vòng đời dữ liệu.

**Bước 4 — Chọn biểu thức key hoặc KeyGenerator.** Ưu tiên các ID đã chuẩn hóa, bất biến và đủ phân biệt. Kiểm soát ký tự phân cách, đầu vào null và việc lộ thông tin nhạy cảm qua tên Redis key.

**Bước 5 — Thiết kế invalidate cùng lúc với cache read.** Xác định thao tác nào cập nhật dữ liệu và cache name/key nào phải xóa hoặc ghi mới. Nếu một cập nhật ảnh hưởng nhiều bộ lọc kết quả, xem xét TTL ngắn hoặc cơ chế index/invalidate thay vì giả định có thể xóa đúng một key.

**Bước 6 — Thử nghiệm tính đúng trước khi tối ưu hit rate.** Cùng đầu vào phải hit; khác tenant, ngôn ngữ hoặc currency phải miss khi kết quả khác; cập nhật phải khiến lần đọc sau thấy dữ liệu mới trong giới hạn nhất quán đã chọn.

**Bước 7 — Quan sát khi chạy thật.** Theo dõi số key, dung lượng Redis, hit/miss, tần suất eviction, serialization errors, TTL và cardinality theo cache name. Nếu một cache sinh số lượng biến thể quá lớn nhưng hit thấp, cần thu hẹp phạm vi hoặc thay đổi chiến lược cache.

### Ví dụ quyết định tổng hợp

Giả sử một API trả thông tin sản phẩm theo tenant và ngôn ngữ:

~~~text
GET /tenants/shop-a/products/p-42?lang=vi-VN
~~~

Một hợp đồng cache có thể là:

~~~text
Cache name:
    catalog.localizedProduct.v1

Key:
    tenant=shop-a;product=p-42;lang=vi-VN

Redis prefix:
    shop:prod:

Redis key vật lý:
    shop:prod:catalog.localizedProduct.v1::tenant=shop-a;product=p-42;lang=vi-VN

TTL:
    5 phút (minh họa, do yêu cầu nghiệp vụ quyết định)

Invalidate:
    Khi cập nhật nội dung hiển thị, xóa các biến thể ngôn ngữ
    chịu ảnh hưởng hoặc dùng chính sách version/TTL phù hợp.
~~~

Hợp đồng trên chỉ đúng khi giá trị locale được chuẩn hóa, quyền truy cập tenant được xác thực và cách invalidate xử lý được tất cả biến thể ngôn ngữ. Nếu bản dịch theo ngôn ngữ mới được bổ sung hoặc product DTO đổi schema, có thể phải điều chỉnh cache name/version và cơ chế xóa dữ liệu cũ.

## 17. Kết luận

Trong Spring Cache kết hợp Spring Data Redis, **cache name xác định nhóm kết quả, cache key xác định một kết quả cụ thể trong nhóm đó, còn Redis prefix/serializer xác định cách nhóm và khóa được biểu diễn trên Redis**. Một thiết kế đáng tin cậy cần cả ba lớp đồng nhất.

SpEL cho phép viết khóa rõ ràng từ tham số như `#productId`, `#tenantId`, `#p0` hoặc property của request. Điều quan trọng không nằm ở độ dài biểu thức mà ở **hợp đồng identity**: hai lời gọi tương đương phải dùng chung khóa, hai lời gọi có thể trả dữ liệu khác nhau phải được phân biệt, và thao tác `@CacheEvict`/`@CachePut` phải theo cùng quy tắc.

Với hệ thống nhiều tenant, nhiều ngôn ngữ và nhiều chính sách giá, sai cache key có thể gây hậu quả lớn hơn một lần cache miss. Hãy chuẩn hóa đầu vào, tách namespace rõ ràng, giới hạn số biến thể, kiểm thử cách đọc và vô hiệu hóa cùng nhau, đồng thời kết hợp TTL và versioning để dữ liệu cache không trở thành nguồn sai lệch khó kiểm soát.
