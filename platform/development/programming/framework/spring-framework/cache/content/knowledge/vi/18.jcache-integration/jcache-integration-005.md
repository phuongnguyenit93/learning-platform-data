# Ánh xạ tham số khóa và giá trị bằng annotation JCache

> **Ngữ cảnh:** Spring Framework Cache — nhóm **JCache (JSR-107)**. Bài học tập trung vào cách JCache dùng `@CacheKey` để chọn tham số tạo **cache key** và `@CacheValue` để xác định **giá trị được ghi vào cache** trong JCache `@CachePut`. Từ đó, ta xây dựng các luồng `@CacheResult` (đọc), `@CachePut` (ghi) và `@CacheRemove` (xóa) dùng cùng một hợp đồng khóa.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt các annotation của **JCache** (`javax.cache.annotation.*`) với annotation gần giống của **Spring Cache** (`org.springframework.cache.annotation.*`).
2. Giải thích các quy tắc sinh key mặc định: không có `@CacheKey` thì dùng tất cả tham số phù hợp; có ít nhất một `@CacheKey` thì chỉ chọn các tham số được đánh dấu.
3. Hiểu `@CacheValue` là tham số **giá trị cần lưu** của JCache `@CachePut`, và tham số đó không được tính vào key.
4. Đảm bảo `@CacheResult`, `@CachePut` và `@CacheRemove` cùng cache name, cùng tập key parameters và cùng key generator.
5. Hiểu rõ JCache `@CachePut` ghi **đối số `@CacheValue`**, không ghi giá trị trả về của method như Spring `@CachePut`.
6. Biên dịch và chạy một dự án Java 17 + Spring Framework 6.2.x, dùng JCache annotation nhưng kho lưu trữ là `ConcurrentMapCacheManager` của Spring.
7. Kiểm thử được cache hit/miss, trace parameter không ảnh hưởng key, cập nhật và invalidation, cùng các lỗi thường gặp về equality, null và dữ liệu phân quyền.

## 1. JCache/JSR-107 nằm ở đâu trong Spring?

JCache là một bộ API chuẩn hóa cho caching, thường được gọi là **JSR-107**. Trong Spring, người lập trình có thể chọn dùng annotation Spring hoặc annotation chuẩn JCache. Spring hỗ trợ các JCache annotation từ Spring Framework 4.1 và tích hợp chúng với Spring caching abstraction.

Các annotation đáng nhớ:

| Ý định | Spring Cache | JCache (JSR-107) |
| --- | --- | --- |
| Cache kết quả method | `@Cacheable` | `@CacheResult` |
| Đặt/cập nhật cache | `@CachePut` | `@CachePut` |
| Xóa một key | `@CacheEvict` | `@CacheRemove` |
| Xóa cả cache | `@CacheEvict(allEntries = true)` | `@CacheRemoveAll` |
| Cấu hình chung ở lớp | `@CacheConfig` | `@CacheDefaults` |
| Chọn tham số để tạo key | SpEL `key = ...`, `KeyGenerator` | `@CacheKey` trên tham số |
| Chọn dữ liệu để ghi từ tham số | Không có `@CacheValue` tương đương trực tiếp | `@CacheValue` trên tham số `@CachePut` |

**Điểm dễ nhầm nhất:** cả Spring và JCache đều có một annotation tên `@CachePut`, nhưng **khác package và khác ngữ nghĩa giá trị lưu**.

Import JCache chuẩn trong ví dụ:

```java
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CacheValue;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheRemove;
```

Đối với JCache 1.1.1, namespace là **`javax.cache.annotation`**, không tự đổi thành `jakarta.cache.annotation` vì đang dùng Java 17 hoặc Spring Framework 6.x. Trong cùng tệp, nếu cần dùng cả hai annotation `@CachePut` từ hai package, phải tránh import gây trùng tên; thường chỉ chọn một loại, hoặc sử dụng tên đầy đủ.

### Dùng JCache annotation có nhất thiết phải chuyển sang JCache provider?

**Không.** Spring Framework có lớp tích hợp để xử lý JCache annotation trên **Spring Cache abstraction**. Bạn có thể dùng JCache annotation trên bean Spring, trong khi `CacheManager` vẫn là `ConcurrentMapCacheManager` hoặc provider khác được Spring hỗ trợ.

Đây là hai khái niệm khác nhau:

- **JCache annotation/API:** cách biểu đạt caching trên method và tham số.
- **JCache caching provider:** implementation của chuẩn `javax.cache.CacheManager`, ví dụ một provider hỗ trợ JSR-107.
- **Spring `org.springframework.cache.CacheManager`:** abstraction Spring có thể được dùng để thực thi cả annotation Spring lẫn JCache thông qua tích hợp tương ứng.

Không được suy luận rằng cứ thêm `javax.cache:cache-api` là có bộ lưu trữ cache vận hành tự động. Nó cung cấp **API**, còn lưu trữ và interception phải được cấu hình/bật.

## 2. @CacheKey — chọn tham số cấu thành cache key

### 2.1. Không đánh dấu @CacheKey: mặc định dùng các đối số

Ví dụ một phương thức đọc sách:

```java
@CacheResult(cacheName = "books")
public Book find(String isbn, boolean includeUsed, String locale) {
    return repository.load(isbn, includeUsed, locale);
}
```

Đây là **mã minh họa**, giả định repository và Book tồn tại. Vì không tham số nào có `@CacheKey`, JCache mặc định xét tất cả ba tham số làm key:

```text
(isbn="ISBN-1", includeUsed=false, locale="vi")
(isbn="ISBN-1", includeUsed=true,  locale="vi")
(isbn="ISBN-1", includeUsed=false, locale="en")
```

Ba bộ tham số có thể tạo ba key khác nhau. Điều này hợp lý **nếu** các tham số đều thực sự ảnh hưởng dữ liệu trả về.

Với `@CachePut`, có một ngoại lệ đặc biệt: tham số `@CacheValue` **không được** đưa vào key mặc định, ngay cả khi không khai báo `@CacheKey`. Quy tắc đó giúp ngăn việc key thay đổi khi dữ liệu mới được đưa vào cache.

### 2.2. Có @CacheKey: chỉ các tham số được đánh dấu tham gia key

```java
@CacheResult(cacheName = "books")
public Book find(@CacheKey String isbn, String traceId) {
    return repository.loadByIsbn(isbn);
}
```

Ở đây `traceId` chỉ để quan sát request; nó không làm thay đổi sách trả về. Tham số duy nhất được dùng cho cache key là `isbn`.

Vì vậy:

```text
find("ISBN-1", "request-A") → MISS → chạy method và lưu sách
find("ISBN-1", "request-B") → HIT  → trả cùng sách
find("ISBN-2", "request-C") → MISS → đọc sách khác
```

**Không phải** Spring mặc định bỏ qua tất cả tham số không được đánh dấu. Đó là **quy tắc JCache khi có ít nhất một `@CacheKey`**. Nếu không có dấu đó, các tham số (ngoại trừ `@CacheValue` trên put) có thể cùng tham gia key.

### 2.3. Nhiều tham số @CacheKey

Nếu một sản phẩm được định danh theo **tenant** và **SKU**:

```java
@CacheResult(cacheName = "tenantProducts")
public Product find(
        @CacheKey String tenantId,
        @CacheKey String sku,
        String requestId) {

    return repository.find(tenantId, sku);
}
```

Hai giá trị `tenantId` và `sku` cùng tham gia key. `requestId` không tham gia.

Điều này có ý nghĩa an toàn: nếu cache chứa dữ liệu của nhiều tenant mà key chỉ là `sku`, hai tenant có thể vô tình nhận chung dữ liệu. Không bao giờ bỏ một chiều phân biệt kết quả hoặc quyền truy cập chỉ vì muốn tăng tỷ lệ cache hit.

### 2.4. Tham số không được chọn phải thật sự không ảnh hưởng kết quả

Ví dụ nguy hiểm:

```java
@CacheResult(cacheName = "prices")
public int price(@CacheKey String sku, String currency) {
    return repository.priceInCurrency(sku, currency);
}
```

Nếu `currency` làm thay đổi kết quả, việc chỉ dùng `sku` làm key là sai. Sau một lần cache giá VND, một lượt yêu cầu USD có thể hit dữ liệu VND.

Cách đúng có thể là đánh dấu cả hai:

```java
public int price(
        @CacheKey String sku,
        @CacheKey String currency) {
    return repository.priceInCurrency(sku, currency);
}
```

Đây là phần chữ ký minh họa; khi sử dụng thật phải đặt `@CacheResult(cacheName = "prices")` lên method và khai báo repository tương ứng.

**Tiêu chuẩn chọn key:** cùng key thì dữ liệu phải có thể tái sử dụng **đúng về nghiệp vụ, tenant và quyền truy cập**, không chỉ trùng một vài tham số kỹ thuật.

## 3. @CacheValue — chọn tham số được ghi vào cache

`@CacheValue` **không phải** một loại `@CacheKey` và **không áp dụng với `@CacheResult` để chọn return value**. Trong JCache, nó đánh dấu tham số chứa **giá trị mà `@CachePut` phải put**.

Ví dụ:

```java
@CachePut(cacheName = "books")
public void save(
        @CacheKey String isbn,
        @CacheValue Book book,
        String auditId) {

    repository.save(isbn, book);
}
```

Hợp đồng là:
- **Cache name:** `books`.
- **Cache key:** sinh từ `isbn` vì `isbn` có `@CacheKey`.
- **Cache value:** đối tượng `book` vì tham số này có `@CacheValue`.
- **`auditId`:** không nằm trong key vì đã có `@CacheKey` khác.
- **Thân method:** thực thi nghiệp vụ `repository.save`; caching không thay thế lưu DB.
- **Thời điểm put:** JCache `@CachePut` mặc định `afterInvocation = true`, tức put sau khi method chạy hoàn tất thành công theo quy tắc exception của annotation.

### Dữ liệu @CacheValue không được đưa vào key

Khi dùng JCache `@CachePut`, thuật toán tham số key áp dụng quy tắc:

| Khai báo tham số | Những gì được dùng làm key |
| --- | --- |
| `save(String isbn, @CacheValue Book book)`, không có `@CacheKey` | `isbn`; bỏ `book` |
| `save(@CacheKey String isbn, @CacheValue Book book, String auditId)` | Chỉ `isbn` |
| `save(@CacheKey String tenant, @CacheKey String sku, @CacheValue Book book)` | `tenant` và `sku` |
| `save(String isbn, String locale, @CacheValue Book book)`, không có `@CacheKey` | `isbn` và `locale` |

Vì vậy, **không cần đặt `@CacheKey` chỉ để loại tham số `@CacheValue` khỏi key**, nhưng nên dùng `@CacheKey` khi muốn tường minh hóa hợp đồng và tránh các tham số phụ như trace/audit làm thay đổi khóa.

Trong một method được đánh dấu JCache `@CachePut` phải có tham số giá trị `@CacheValue` hợp lệ; thiếu hoặc đánh dấu sai khiến metadata method không thể xác định giá trị cần put, có thể dẫn đến lỗi xử lý annotation. Tránh gắn `@CacheValue` vào nhiều tham số hoặc dùng nó trên method không phù hợp.

### JCache @CachePut không tự lấy return value để lưu

Đây là khác biệt cốt lõi:

```java
// JCache: dùng @CacheValue để biết nên cache đối số nào
@javax.cache.annotation.CachePut(cacheName = "books")
public String save(
        @CacheKey String isbn,
        @CacheValue Book book) {

    repository.save(isbn, book);
    return "saved:" + isbn;
}
```

Với JCache, **`Book book` được cache**, còn String `"saved:..."` chỉ là kết quả trả cho caller.

So sánh với Spring:

```java
// Spring: cache kết quả trả về của method
@org.springframework.cache.annotation.CachePut(
        cacheNames = "books", key = "#p0")
public Book save(String isbn, Book book) {
    return repository.save(isbn, book);
}
```

Đây là hai **mẫu code minh họa khác nhau** trong bean Spring có repository tương ứng, không thể ghép chúng trên một method với ý định chúng là cùng một annotation. Ở bản Spring, return value sau khi method chạy mới được dùng làm value; ở bản JCache, tham số `@CacheValue` là nguồn value.

Nếu phương thức JCache thực hiện chuẩn hóa hoặc biến đổi bản ghi trong DB nhưng `@CacheValue` vẫn là đối tượng đầu vào chưa được chuẩn hóa, cache có thể lưu một bản **khác với DB**. Hãy quyết định nguồn dữ liệu canonical và khi cần thì dùng phương thức khác trả về giá trị chuẩn hoặc chiến lược invalidate/reload phù hợp.

## 4. Làm sao ba operation đọc, put và remove dùng cùng key?

Một thiết kế hợp lý cho cache `books`:

```java
@CacheResult(cacheName = "books")
public Book find(@CacheKey String isbn, String traceId) {
    return repository.load(isbn);
}

@CachePut(cacheName = "books")
public void save(
        @CacheKey String isbn,
        @CacheValue Book book,
        String auditId) {
    repository.save(isbn, book);
}

@CacheRemove(cacheName = "books")
public void invalidate(@CacheKey String isbn, String reason) {
    audit.log("invalidate", isbn, reason);
}
```

Đây là **một cụm method minh họa**; cần Book, repository và audit có thật.

Cả ba method chọn **cùng một tập tham số key**: ISBN. Tham số trace và audit bị bỏ qua. `@CacheResult` đặt kết quả đọc vào key ISBN; `@CachePut` dùng chính key đó để cập nhật Book; `@CacheRemove` dùng chính key đó để xóa.

Khi cùng tồn tại trong một ứng dụng, phải chú ý cả **key generator thực tế**. JCache mặc định sinh một `GeneratedCacheKey` đại diện cho các tham số được chọn. Nếu một method Spring `@Cacheable(key="#p0")` sử dụng trực tiếp String ISBN, còn JCache tạo GeneratedCacheKey từ ISBN, **hai key có thể khác nhau dù giá trị đầu vào trông giống nhau**.

Đừng tùy tiện dùng `cache.get("ISBN-1")` trên Spring `Cache` để kiểm tra xem một thao tác JCache mặc định đã cache hay chưa; key thực tế có thể là một object `GeneratedCacheKey`, không phải String trần.

### Các điều kiện cần đúng đồng thời

1. Cùng tên vùng cache (`cacheName="books"`).
2. Cùng những chiều dữ liệu tạo key (ví dụ ISBN, tenant, locale nếu phù hợp).
3. Cùng thuật toán/key generator và quy tắc `equals/hashCode`.
4. Giá trị cache có kiểu thích hợp với method đọc.
5. Lệnh cập nhật nguồn xảy ra thành công; giá trị put phản ánh trạng thái nguồn mà phương thức đọc kỳ vọng.
6. Gọi qua Spring proxy và hạ tầng caching đã bật.

Một thay đổi ở bất kỳ phần nào có thể làm lần đọc sau put vẫn miss, hoặc tệ hơn là hit nhầm dữ liệu.

## 5. Quy tắc lựa chọn key — bảng nhớ nhanh

| Khai báo | Tập tham số tạo key | Giá trị put |
| --- | --- | --- |
| `@CacheResult find(String sku, String locale)` | Cả `sku` và `locale` | Return value của `find` |
| `@CacheResult find(@CacheKey String sku, String trace)` | Chỉ `sku` | Return value của `find` |
| `@CacheResult find(@CacheKey String tenant, @CacheKey String sku, String trace)` | `tenant` và `sku` | Return value của `find` |
| `@CachePut save(String sku, @CacheValue Product product)` | `sku` | `product` |
| `@CachePut save(@CacheKey String sku, @CacheValue Product product, String audit)` | Chỉ `sku` | `product` |
| `@CachePut save(String sku, String locale, @CacheValue Product product)` | `sku` và `locale` | `product` |
| `@CacheRemove remove(@CacheKey String sku, String reason)` | Chỉ `sku` | Không put; xóa entry |
| `@CacheRemoveAll clear()` | Không chọn key cụ thể | Không put; xóa toàn bộ cache |

Trong bảng, các tên annotation là **JCache**. Các chữ ký là **mẫu diễn giải quy tắc**, không phải chương trình Java có đủ phần thân và import.

### GeneratedCacheKey và equality

JSR-107 sử dụng `CacheKeyGenerator` để sinh `GeneratedCacheKey`. Key generator mặc định của Spring dành cho JCache tuân thủ ý tưởng chuẩn, lựa chọn tham số từ `CacheKeyInvocationContext.getKeyParameters()` và tạo key tổ hợp.

Đối với các tham số làm key:
- Sử dụng value object có `equals()`/`hashCode()` đúng với định danh nghiệp vụ.
- Java record với các trường thích hợp thường là lựa chọn tốt cho key bất biến.
- Tránh sửa một đối tượng key mutable sau khi đã put: hash/equality thay đổi có thể khiến entry không thể tra lại đúng.
- Với array, collection hoặc nested object, cần kiểm chứng semantics của key generator, deep equality và provider (đặc biệt khi serialization khác đi).
- Không sử dụng các giá trị chỉ phục vụ tracing, timestamp ngẫu nhiên hoặc request ID làm key nếu chúng không thay đổi kết quả.
- Không bỏ `tenantId` hay security scope nếu chúng ảnh hưởng dữ liệu được phép nhận.

Một custom `CacheKeyGenerator` có thể được khai báo trên operation JCache thông qua thuộc tính `cacheKeyGenerator` và thường là class đáp ứng interface `javax.cache.annotation.CacheKeyGenerator`. Nó **khác interface** `org.springframework.cache.interceptor.KeyGenerator` của Spring Cache. Khi viết custom generator, cần kiểm chứng đầu ra là một key ổn định, so sánh được, và phù hợp với cache provider.

## 6. @CacheResult, @CachePut và @CacheRemove: thời điểm thực thi

### @CacheResult — đọc qua cache

Mặc định, `@CacheResult` thử lấy kết quả từ cache; hit có thể bỏ qua thân method, miss chạy method rồi cache kết quả. JCache hỗ trợ các cấu hình bổ sung, ví dụ `skipGet = true` để buộc chạy method mà vẫn xử lý caching theo ngữ nghĩa của annotation; nó không có nghĩa “tắt cache toàn bộ ứng dụng”.

### @CachePut — làm mới bằng đối số

Method được gọi để xử lý nghiệp vụ; JCache lấy tham số `@CacheValue` để put vào cache. Mặc định:

```java
@CachePut(cacheName = "books", afterInvocation = true)
public void save(@CacheKey String isbn, @CacheValue Book book) {
    repository.save(isbn, book);
}
```

Dạng `afterInvocation = true` giúp tránh put trước khi thân method thất bại theo quy tắc exception mặc định.

Có thể cấu hình:

```java
@CachePut(cacheName = "books", afterInvocation = false)
public void save(@CacheKey String isbn, @CacheValue Book book) {
    repository.save(isbn, book);
}
```

Nhưng **cần cân nhắc kỹ**: put trước invocation có thể tạo mục cache mới **trước khi cập nhật DB thực sự thành công**; nếu nghiệp vụ lỗi hoặc transaction rollback, cache có thể chứa bản không đúng. Đừng đổi mặc định chỉ để “tăng tốc”.

JCache hỗ trợ một số tùy chọn `cacheFor` và `noCacheFor` theo class exception để quyết định có put hay không khi invocation ném lỗi. Đây là chính sách của JCache, không phải phép bảo đảm tính nguyên tử giữa DB và cache.

### @CacheRemove — xóa entry

`@CacheRemove` dùng tập key parameters được chọn để xóa một mục cache. Theo hành vi mặc định, eviction xảy ra sau invocation thành công; cấu hình thời điểm và exception handling có thể thay đổi theo annotation.

`@CacheRemoveAll` xóa toàn bộ entry trong cache mục tiêu, **không phụ thuộc một `@CacheKey` riêng**. Nó phù hợp với sự kiện thay đổi khiến mọi entry của vùng cache không còn hợp lệ, nhưng tốn kém khi số mục lớn.

## 7. Bật JCache annotations trong Spring Framework

Để dùng JCache annotation trên một Spring bean **không cần phải triển khai JCache provider riêng** khi bạn đã dùng Spring Cache abstraction.

Những thành phần cần có cho ví dụ Java 17:
- `javax.cache:cache-api:1.1.1` — khai báo chuẩn `@CacheResult`, `@CacheKey`, `@CacheValue`, `@CachePut`, `@CacheRemove`.
- `org.springframework:spring-context-support` — tích hợp JCache annotation vào Spring caching infrastructure.
- `org.springframework:spring-context` — được `spring-context-support` kéo về như dependency; chứa `@EnableCaching` và `ConcurrentMapCacheManager`.
- Một bean kiểu Spring `CacheManager`, ví dụ `ConcurrentMapCacheManager("catalog")`.
- `@EnableCaching` để bật interception và lời gọi đến **bean qua Spring proxy**, không tạo object bằng `new` rồi gọi trực tiếp.

Ví dụ cấu hình ngắn:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
class CacheConfig {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }
}
```

Đây là **mảnh cấu hình**, cần import Spring Cache/Context và đặt trong context thích hợp. Khi dùng Spring Framework thuần, package `javax.cache.annotation` và `spring-context-support` cùng có trong classpath thì `@EnableCaching` kích hoạt cả việc nhận diện JCache annotations.

### Vì sao @EnableCaching quan trọng?

Annotation tự nó chỉ là metadata. Caching được thực hiện bởi interceptor/advice do Spring thiết lập. Trong proxy mode mặc định:

- Gọi method qua bean do `ApplicationContext` trả về: advice có thể chạy.
- Tạo `new CatalogService(...)` rồi gọi: không qua proxy, annotation không có tác dụng.
- Gọi `this.find(...)` bên trong chính bean: self-invocation có thể bỏ qua proxy.
- Method private/final hoặc class final có thể cản trở cách tạo proxy; ví dụ chọn một public, non-final service class cho rõ ràng.

Nếu thiếu JCache API hoặc `spring-context-support`, việc `@EnableCaching` bật Spring annotations không tự bảo đảm JCache annotations được nhận diện như mong đợi.

## 8. Ví dụ hoàn chỉnh: Java 17 + Spring + JCache trên ConcurrentMap

Thí nghiệm có một kho sách giả trong JVM. Một dịch vụ dùng **chỉ JCache annotations** nhưng provider là `ConcurrentMapCacheManager` của Spring.

Các bước kiểm chứng:

1. Hai lần đọc cùng ISBN với trace ID khác nhau chỉ gọi repository **một lần**.
2. Nguồn bị sửa từ bên ngoài sẽ làm cache trả **bản cũ** khi chưa invalidation.
3. JCache `@CachePut` nhận một `Book` có `@CacheValue`, cập nhật nguồn và cache bằng Book đó dù method trả về **một String biên nhận**.
4. JCache `@CacheRemove` loại đúng key; lần đọc sau sẽ nạp bản mới từ nguồn.
5. Cả ba operation dùng cache name `catalog` và cùng key parameter ISBN.

### 8.1. Cấu trúc

```text
jcache-parameter-mapping/
├── pom.xml
└── src/
    ├── main/java/demo/jcache/JCacheMappingDemo.java
    └── test/java/demo/jcache/JCacheMappingDemoTest.java
```

### 8.2. Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>jcache-parameter-mapping</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.16</version>
        </dependency>
        <dependency>
            <groupId>javax.cache</groupId>
            <artifactId>cache-api</artifactId>
            <version>1.1.1</version>
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
                    <mainClass>demo.jcache.JCacheMappingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

POM dùng Spring Framework 6.2.16 và JCache 1.1.1 tương thích JDK 17. `spring-context-support` kéo theo Spring Context. Chúng ta **không cần Redis hay Ehcache**: Spring JCache annotation integration có thể làm việc với `ConcurrentMapCacheManager` của Spring.

### 8.3. src/main/java/demo/jcache/JCacheMappingDemo.java

```java
package demo.jcache;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheRemove;
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheValue;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class JCacheMappingDemo {

    public record Book(String isbn, String title) {}

    public static class BookRepository {
        private final Map<String, Book> data = new ConcurrentHashMap<>();
        private final AtomicInteger loads = new AtomicInteger();

        public BookRepository() {
            data.put("B1", new Book("B1", "Spring Handbook"));
        }

        public Book load(String isbn) {
            loads.incrementAndGet();
            return data.get(isbn);
        }

        public void save(String isbn, Book book) {
            data.put(isbn, book);
        }

        public int loadCount() {
            return loads.get();
        }
    }

    public static class CatalogService {
        private final BookRepository repository;
        private final AtomicInteger invalidations = new AtomicInteger();

        public CatalogService(BookRepository repository) {
            this.repository = repository;
        }

        @CacheResult(cacheName = "catalog")
        public Book find(@CacheKey String isbn, String traceId) {
            return repository.load(isbn);
        }

        @CachePut(cacheName = "catalog")
        public String replace(
                @CacheKey String isbn,
                @CacheValue Book book,
                String auditId) {
            repository.save(isbn, book);
            return "stored:" + isbn;
        }

        @CacheRemove(cacheName = "catalog")
        public void invalidate(@CacheKey String isbn, String reason) {
            invalidations.incrementAndGet();
        }

        public int invalidationCount() {
            return invalidations.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("catalog");
        }

        @Bean
        public BookRepository bookRepository() {
            return new BookRepository();
        }

        @Bean
        public CatalogService catalogService(BookRepository repository) {
            return new CatalogService(repository);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            var service = context.getBean(CatalogService.class);
            var repository = context.getBean(BookRepository.class);
            var manager = context.getBean(CacheManager.class);

            System.out.println("manager="
                    + manager.getClass().getSimpleName());
            System.out.println("first="
                    + service.find("B1", "trace-A").title());
            System.out.println("second="
                    + service.find("B1", "trace-B").title());
            System.out.println("loads1="
                    + repository.loadCount());

            // Thay nguồn ngoài đường đi JCache annotation:
            repository.save("B1", new Book("B1", "Changed Outside"));
            System.out.println("stale="
                    + service.find("B1", "trace-C").title());

            System.out.println("receipt="
                    + service.replace(
                            "B1",
                            new Book("B1", "Updated Via JCache Put"),
                            "audit-1"));
            System.out.println("afterPut="
                    + service.find("B1", "trace-D").title());
            System.out.println("loads2="
                    + repository.loadCount());

            // Nguồn lại thay đổi; lần này chủ động invalidation.
            repository.save("B1", new Book("B1", "After Invalidation"));
            service.invalidate("B1", "source-changed");

            System.out.println("afterRemove="
                    + service.find("B1", "trace-E").title());
            System.out.println("loads3="
                    + repository.loadCount());
            System.out.println("invalidations="
                    + service.invalidationCount());
        }
    }
}
```

### 8.4. Biên dịch và chạy

Cần JDK 17+, Maven 3.9+ và mạng để Maven tải dependencies lần đầu. Từ thư mục `jcache-parameter-mapping` chạy:

```bash
java -version
mvn -q compile exec:java
```

Các dòng **do chính chương trình in ra** (không bao gồm thông báo Maven hay log Spring):

```text
manager=ConcurrentMapCacheManager
first=Spring Handbook
second=Spring Handbook
loads1=1
stale=Spring Handbook
receipt=stored:B1
afterPut=Updated Via JCache Put
loads2=1
afterRemove=After Invalidation
loads3=2
invalidations=1
```

Diễn giải:

1. `first` miss, JCache `@CacheResult` gọi repository rồi lưu Book dưới key được tạo từ `@CacheKey isbn`.
2. `second` có `traceId` khác nhưng `isbn` giống nhau, nên **hit**; `loads1=1` chứng minh repository chỉ được gọi một lần.
3. Sửa repository trực tiếp thành `Changed Outside` không có thao tác invalidate cache, nên `stale` vẫn là `Spring Handbook`.
4. `replace` thực thi nghiệp vụ lưu Book mới, đồng thời JCache `@CachePut` put **Book từ tham số `@CacheValue`**, **không** put String `"stored:B1"` mà method trả về.
5. `afterPut` nhận Book mới ngay từ cache; `loads2` vẫn 1. Ba operation dùng cùng key vì cùng đánh dấu `isbn` bằng `@CacheKey`.
6. Sau khi nguồn chuyển sang `After Invalidation`, `@CacheRemove` xóa entry cùng key. `afterRemove` miss nên đọc lại nguồn và `loads3=2`.
7. `invalidations=1` xác nhận thân method xóa cache đã chạy một lần. Việc cache bị xóa là do interceptor JCache, không phải code gọi `Cache.evict` thủ công.

**Phạm vi:** demo chỉ chạy trong một JVM với `ConcurrentMapCacheManager`, không kiểm chứng TTL, DB transaction hay distributed consistency. Nó minh họa Spring **xử lý JCache annotation bằng Spring CacheManager**, chứ không chứng minh có một javax.cache provider riêng.

## 9. JUnit 5 kiểm chứng chính xác mapping key/value

Tạo tệp `src/test/java/demo/jcache/JCacheMappingDemoTest.java`:

```java
package demo.jcache;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JCacheMappingDemoTest {

    @Test
    void onlyCacheKeyParameterDeterminesReadKey() {
        try (var context = new AnnotationConfigApplicationContext(
                JCacheMappingDemo.Config.class)) {

            var service = context.getBean(
                    JCacheMappingDemo.CatalogService.class);
            var repository = context.getBean(
                    JCacheMappingDemo.BookRepository.class);

            assertEquals(
                    "Spring Handbook",
                    service.find("B1", "trace-first").title());
            assertEquals(
                    "Spring Handbook",
                    service.find("B1", "trace-second").title());
            assertEquals(1, repository.loadCount());
        }
    }

    @Test
    void cachePutUsesCacheValueParameterNotMethodReturn() {
        try (var context = new AnnotationConfigApplicationContext(
                JCacheMappingDemo.Config.class)) {

            var service = context.getBean(
                    JCacheMappingDemo.CatalogService.class);
            var repository = context.getBean(
                    JCacheMappingDemo.BookRepository.class);

            service.find("B1", "trace-read");
            assertEquals(1, repository.loadCount());

            var newBook = new JCacheMappingDemo.Book("B1", "New Title");
            assertEquals(
                    "stored:B1",
                    service.replace("B1", newBook, "audit-99"));

            // Sau JCache @CachePut, @CacheResult phải đọc Book,
            // KHÔNG đọc String biên nhận "stored:B1".
            assertEquals(
                    "New Title",
                    service.find("B1", "trace-after-put").title());
            assertEquals(1, repository.loadCount());
        }
    }

    @Test
    void cacheRemoveUsesSameSelectedKey() {
        try (var context = new AnnotationConfigApplicationContext(
                JCacheMappingDemo.Config.class)) {

            var service = context.getBean(
                    JCacheMappingDemo.CatalogService.class);
            var repository = context.getBean(
                    JCacheMappingDemo.BookRepository.class);

            assertEquals(
                    "Spring Handbook",
                    service.find("B1", "first").title());
            repository.save("B1",
                    new JCacheMappingDemo.Book("B1", "Fresh"));

            assertEquals(
                    "Spring Handbook",
                    service.find("B1", "still-cached").title());
            service.invalidate("B1", "update");

            assertEquals(
                    "Fresh",
                    service.find("B1", "after-remove").title());
            assertEquals(2, repository.loadCount());
            assertEquals(1, service.invalidationCount());
        }
    }
}
```

Chạy:

```bash
mvn -q test
```

Khi các assertion đúng, Maven trả exit code 0. Vì dùng `-q`, Maven không nhất thiết in “BUILD SUCCESS” trên console.

**Điểm đặc biệt của các test này:** chúng không đo thời gian chạy mà đo số lần đọc nguồn và giá trị trả về. Mỗi test tạo một ApplicationContext mới, không phụ thuộc cache còn lại từ một test trước. Quan trọng hơn, chúng xác nhận cả ba phương thức JCache **thực sự trỏ tới cùng key**, thay vì chỉ trùng tên vùng cache.

## 10. Những lỗi thường gặp với @CacheKey và @CacheValue

### 10.1. Quên @CacheKey khi có tham số không liên quan

```java
@CacheResult(cacheName = "books")
public Book find(String isbn, String traceId) {
    return repository.load(isbn);
}
```

Không có `@CacheKey`, JCache mặc định dùng **cả hai** tham số. Hai trace ID khác nhau sẽ thành hai key và dẫn đến miss liên tục dù ISBN giống nhau.

**Sửa:** `find(@CacheKey String isbn, String traceId)`, nhưng chỉ nếu traceId **không ảnh hưởng** kết quả.

### 10.2. Bỏ tham số làm thay đổi dữ liệu hoặc phạm vi truy cập

Nếu method `find(String tenantId, String isbn)` được đánh dấu chỉ `isbn`, hai tenant có thể hit cùng entry. Đây không chỉ là lỗi hiệu năng, mà có thể thành lỗi **cô lập dữ liệu**. Hãy dùng cả `@CacheKey tenantId` và `@CacheKey isbn` khi kết quả có phạm vi tenant.

### 10.3. Thiếu @CacheValue trên JCache @CachePut

```java
@CachePut(cacheName = "books")
public void save(@CacheKey String isbn, Book book) {
    repository.save(isbn, book);
}
```

**Đoạn sai để nhận diện:** JCache không biết tham số nào là giá trị cần put. Không mặc định lấy method return hoặc đoán Book từ kiểu tham số. Phải đánh dấu tham số value bằng `@CacheValue`.

### 10.4. Dùng nhầm Spring @CachePut

Một import nhầm:

```java
import org.springframework.cache.annotation.CachePut;
```

thay cho:

```java
import javax.cache.annotation.CachePut;
```

có thể thay đổi hoàn toàn behavior. Spring `@CachePut` lưu **return value**; JCache `@CachePut` lưu **argument `@CacheValue`**. Cùng tên annotation không làm chúng tương đương.

### 10.5. Đánh dấu @CacheValue nhưng lại đọc key là giá trị String thuần

Với JCache default key generator, `cache.get("B1")` trên `org.springframework.cache.Cache` không nhất thiết thấy entry mà `@CacheResult` sinh ra từ `@CacheKey String isbn`, vì object key có thể là kiểu `GeneratedCacheKey`. Nếu cần kiểm thử chính xác key, dùng cùng đường gọi annotation hoặc kiểm tra qua generator thực tế; đừng tự suy diễn key nội bộ.

### 10.6. @CachePut ghi tham số trước khi dữ liệu nguồn thành công

`afterInvocation = false` có thể put trước khi repository.save hoàn thành. Nếu DB rollback hoặc lỗi, cache chứa value không có ở nguồn. Ngay cả default `afterInvocation = true` cũng cần cân nhắc ranh giới Spring transaction: method return không phải lúc nào đồng nghĩa transaction đã commit.

### 10.7. Cache value không khớp kiểu mà @CacheResult mong đợi

Nếu JCache `@CachePut` lưu một DTO khác `Book`, trong khi `@CacheResult` trên cùng cache/key khai báo trả `Book`, lần hit sau có thể lỗi cast hoặc đem dữ liệu sai. Đặt hợp đồng **cache value type** thống nhất giữa các operation.

### 10.8. Thay đổi object key sau khi lưu

Dùng key là một object mutable rồi sửa các trường trong `equals/hashCode` có thể làm key không còn tra được. Dùng ID bất biến, record phù hợp hoặc một immutable key object.

### 10.9. Nhầm cache annotation với tự động bật caching

Chỉ thêm `@CacheResult` hoặc `@CachePut` mà quên `@EnableCaching`/phụ thuộc tích hợp sẽ không cho behavior mong muốn. Gọi bằng `this.method()` hoặc `new` cũng có thể bỏ qua Spring proxy.

### 10.10. Dùng chung cache name nhưng hai loại key generator khác nhau

Một method Spring `@Cacheable(key = "#p0")` và method JCache `@CachePut` có thể cùng tham số ISBN nhưng tạo **key vật lý không tương đương**. Việc dùng chung cache name chưa đủ. Nên thống nhất toàn bộ key strategy; khi migration từ annotation Spring sang JCache, phải kiểm thử hit/readback thực tế.

## 11. Các trường hợp nâng cao

### 11.1. @CacheDefaults ở cấp lớp

JCache `@CacheDefaults` có thể chỉ định cache name mặc định để tránh lặp:

```java
@CacheDefaults(cacheName = "books")
public class BookService {
    @CacheResult
    public Book find(@CacheKey String isbn) {
        return repository.load(isbn);
    }
}
```

Đây là **đoạn minh họa trong ứng dụng có repository**, cần import `CacheDefaults`. Annotation ở method có thể ghi đè một số mặc định. Nếu không khai báo cacheName ở method hoặc `@CacheDefaults`, JCache có quy tắc sinh tên từ thông tin class, method và parameter types; tên đó có thể không trùng với cache mà `CacheManager` đã đăng ký.

Khi phối hợp nhiều operation và muốn chúng dùng đúng một vùng, việc đặt tên cache tường minh thường dễ kiểm tra hơn.

### 11.2. CacheResolverFactory

JSR-107 có `javax.cache.annotation.CacheResolverFactory` và `CacheResolver` để chọn cache. Trong tích hợp Spring, bạn có thể tùy chỉnh cách resolve vùng cache, nhưng lưu ý JCache chuẩn làm việc với **một cache cho một operation** thay vì danh sách nhiều cache như một số tính năng Spring Cache. Một resolver không đúng có thể khiến thao tác đọc và ghi trỏ sang vùng khác dù cùng tên nghiệp vụ.

### 11.3. Tùy chỉnh CacheKeyGenerator

`@CacheResult` và JCache `@CachePut` có thuộc tính `cacheKeyGenerator` để dùng class sinh key tùy chỉnh. Dùng khi key cần chuẩn hóa, ví dụ chuẩn hóa ISBN, tenant scope hoặc sử dụng composite immutable ID.

Thiết kế custom key generator cần:
- Dựa trên đúng tập `getKeyParameters()` đã được chọn.
- Cho cùng input logic ra key bằng nhau qua các operation.
- Tránh đưa thông tin bí mật vào log/toString của key.
- Tránh so sánh key theo identity thay vì value.
- Kiểm tra serialization khi provider là Redis/Ehcache hoặc cache khác JVM.

Không cần viết custom generator chỉ để bỏ một traceId: `@CacheKey` là cơ chế chuẩn và đơn giản hơn.

### 11.4. Exception caching

JCache `@CacheResult` có khả năng cấu hình cache exception được chọn bằng `cachedExceptions` và `exceptionCacheName`. Nó không thay đổi quy tắc chọn key bởi `@CacheKey`, nhưng làm ứng dụng có thể trả lại ngoại lệ đã cache thay vì thực thi method ở những lần gọi sau. Chỉ dùng với exception có tính chất phù hợp và có chính sách hết hạn/invalidation rõ ràng.

### 11.5. Null values và provider

Các provider có chính sách null key/null value khác nhau. `ConcurrentMapCacheManager` của Spring có thể biểu diễn cached null value bằng object đại diện; một JCache provider khác có thể từ chối null value. Đừng suy ra annotation `@CacheValue` làm mọi null value trở nên hợp lệ. Khi dữ liệu có thể không tồn tại, phải xác nhận provider, key strategy và chính sách negative caching.

### 11.6. TTL, TTI và invalidation

JCache annotations chỉ định operation và key/value mapping; thời gian sống, idle expiry, capacity và serialization thuộc cấu hình của provider. Nếu nguồn đổi mà không qua `@CachePut` hoặc `@CacheRemove`, `@CacheResult` có thể trả dữ liệu cũ. TTL giúp giới hạn tuổi cache nhưng không tự đồng bộ ngay khi DB đổi.

## 12. Checklist khi thiết kế ánh xạ key/value

1. **Đúng package:** đã import `javax.cache.annotation.CachePut` hay vô tình import Spring `@CachePut`?
2. **Key dimensions:** tập `@CacheKey` có gồm đủ tenant, ID, locale/currency và phạm vi quyền ảnh hưởng dữ liệu không?
3. **Tham số phụ:** traceId, auditId không ảnh hưởng kết quả đã được loại khỏi key chưa?
4. **Không có @CacheKey:** có hiểu rằng mặc định JCache dùng các tham số (ngoại trừ `@CacheValue` trên put) không?
5. **CacheValue:** JCache `@CachePut` có một tham số chứa chính xác value cần cache không?
6. **Return value:** có đang nhầm giá trị method trả về với giá trị `@CacheValue` không?
7. **Consistency:** read/put/remove có cùng cache name, cùng tập key và key generator không?
8. **Value type:** giá trị put có cùng kiểu mà method `@CacheResult` mong chờ không?
9. **Nguồn dữ liệu:** value đưa vào cache có phản ánh dữ liệu canonical đã persist không?
10. **Thời điểm put:** có cần đổi `afterInvocation` không, và có ảnh hưởng transaction/rollback không?
11. **Proxy:** các method có được gọi qua Spring bean và `@EnableCaching` có hiệu lực không?
12. **Provider:** hạ tầng Spring JCache integration có mặt chưa? Cache manager thực sự là gì?
13. **Kiểm thử:** với traceId khác nhau, có hit cùng ISBN không? Sau put có đọc đúng Book không? Sau remove có miss không?
14. **Vận hành:** có TTL/invalidation phù hợp và cơ chế cô lập dữ liệu multi-tenant không?

## 13. Bài tập tự luyện

**Bài 1.** Với `find(String isbn, String requestId)` không có `@CacheKey`, hai requestId khác nhau có thể tạo cùng key không?  
**Đáp án:** Theo key generator mặc định của JCache, hai tham số đều tham gia nên thường tạo **hai key khác nhau**. Nếu requestId không ảnh hưởng kết quả, đánh dấu `@CacheKey` chỉ trên ISBN.

**Bài 2.** `save(@CacheKey String isbn, @CacheValue Book book, String auditId)` dùng những dữ liệu gì?  
**Đáp án:** Key chọn ISBN; value là Book; auditId không tham gia key.

**Bài 3.** Vì sao `save(String isbn, @CacheValue Book book)` không tự lấy Book làm một phần key khi không có `@CacheKey`?  
**Đáp án:** Quy tắc JCache loại `@CacheValue` khỏi key cho `@CachePut`.

**Bài 4.** JCache `@CachePut` method trả `String "OK"` nhưng `@CacheValue` nằm trên `Book book`. Cache nhận gì?  
**Đáp án:** Book, không phải String biên nhận.

**Bài 5.** Một method `@CacheResult` dùng `@CacheKey ISBN`, nhưng method Spring `@CachePut(key = "#p0")` dùng String ISBN trực tiếp. Vì sao có thể không cùng entry?  
**Đáp án:** Hai framework/key generator có thể tạo object key khác loại, dù ISBN có cùng text. Cần đồng nhất chiến lược sinh key.

**Bài 6.** Một service trả giá theo `tenantId` và `sku` nhưng chỉ đánh dấu `@CacheKey sku`. Lỗi gì?  
**Đáp án:** Dữ liệu của các tenant khác nhau có thể dùng chung key; cần gồm cả tenantId vào key.

**Bài 7.** Tại sao không thể coi `@CacheValue` như `@CacheResult`?  
**Đáp án:** `@CacheValue` chỉ đánh dấu tham số được put bởi JCache `@CachePut`; còn `@CacheResult` lấy **return value** của method để cache trên đường miss.

## Nguồn tham khảo chính thức

- [Spring Framework — JCache (JSR-107) Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [JSR-107 API — CacheKey](https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheKey.html)
- [JSR-107 API — CacheValue](https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheValue.html)
- [JSR-107 API — CachePut](https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CachePut.html)
- [JSR-107 API — CacheKeyInvocationContext](https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheKeyInvocationContext.html)
- [Spring Boot — Caching and JCache Provider](https://docs.spring.io/spring-boot/reference/io/caching.html)

**Ghi nhớ:** Trong JCache, **`@CacheKey` chọn các tham số để sinh key**, còn **`@CacheValue` chọn tham số được put vào cache**. JCache `@CachePut` **không lấy giá trị trả về của method** như Spring `@CachePut`. Muốn đọc, cập nhật và xóa cùng một entry, hãy thống nhất **cache name + key parameters + key generator + value type**, đồng thời kiểm thử qua Spring proxy và provider thực tế.