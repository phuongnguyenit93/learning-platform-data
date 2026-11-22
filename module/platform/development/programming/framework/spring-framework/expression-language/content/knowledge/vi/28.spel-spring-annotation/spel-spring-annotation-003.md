# SpEL trong `@Cacheable`, `@CachePut` và `@CacheEvict`

## Mục tiêu

Spring Cache annotations cho phép dùng Spring Expression Language (SpEL) để quyết định cache key, điều kiện áp dụng cache và việc có lưu kết quả hay không. Mỗi annotation có một mục đích riêng:

- `@Cacheable` kiểm tra cache trước; nếu có giá trị phù hợp thì trả về giá trị đó và bỏ qua việc gọi method.
- `@CachePut` luôn gọi method rồi cập nhật cache bằng kết quả trả về.
- `@CacheEvict` xóa một entry hoặc toàn bộ cache để loại bỏ dữ liệu cũ.

SpEL giúp các quyết định này phụ thuộc vào tham số, property lồng nhau, metadata của method hoặc kết quả trả về. Để viết biểu thức đúng, cần hiểu thời điểm expression được đánh giá và biến nào có sẵn ở thời điểm đó.

## 1. Bật annotation-based caching

Đặt `@EnableCaching` trên một class cấu hình để bật xử lý các cache annotations:

```java
@Configuration
@EnableCaching
public class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }
}
```

Ví dụ trên tạo một cache manager đơn giản với cache tên `books`. Trong ứng dụng thực tế, có thể dùng Caffeine, Redis hoặc một implementation khác tùy nhu cầu. `@Cacheable`, `@CachePut` và `@CacheEvict` chỉ được xử lý khi caching infrastructure đã được bật và method được gọi qua cơ chế interception tương ứng.

## 2. SpEL evaluation context dành riêng cho cache

Spring tạo một evaluation context dành cho từng cache operation. Ngoài method arguments, context có root object chứa metadata về lời gọi và các cache được sử dụng.

| Tham chiếu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `#root.methodName` | Tên method đang được gọi. | `#root.methodName == 'findBook'` |
| `#root.method` | Đối tượng `Method` đang được gọi. | `#root.method.name` |
| `#root.target` | Target object nhận lời gọi. | `#root.target` |
| `#root.targetClass` | Class thực tế của target. | `#root.targetClass` |
| `#root.args` | Mảng các đối số method. | `#root.args[0]` |
| `#root.caches` | Các cache được chọn cho operation. | `#root.caches[0].name` |
| `#result` | Kết quả method, chỉ có ở một số expression sau invocation. | `#result?.id` |

Root object có thể được tham chiếu bằng `#root`; các argument cũng có thể được truy cập theo tên nếu Spring tìm được tên tham số.

## 3. Truy cập method arguments

Giả sử method có chữ ký:

```java
public Book findBook(ISBN isbn, boolean checkWarehouse, boolean includeUsed) {
    // ...
}
```

Trong cache expression, có thể truy cập các tham số theo tên:

```java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findBook(ISBN isbn, boolean checkWarehouse, boolean includeUsed) {
    // ...
}
```

Hoặc truy cập property lồng nhau:

```java
@Cacheable(cacheNames = "books", key = "#isbn.rawNumber")
public Book findBook(ISBN isbn, boolean checkWarehouse, boolean includeUsed) {
    // ...
}
```

Nếu tên tham số không có trong metadata mà Spring sử dụng được, dùng alias theo vị trí:

```java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(ISBN isbn) {
    // ...
}
```

`#p0` và `#a0` đều chỉ tham số đầu tiên; `#p1` và `#a1` chỉ tham số thứ hai. Có thể dùng `#root.args[0]` để tham chiếu cùng đối số. Tên tham số thường cần được giữ trong bytecode, ví dụ biên dịch với tùy chọn `-parameters`; alias theo vị trí là lựa chọn ổn định khi không chắc tên tham số có sẵn.

## 4. `@Cacheable`: dùng SpEL để tạo key và điều kiện

`@Cacheable` kiểm tra cache trước khi chạy method. Nếu cache có entry cho key đã tính, Spring trả về giá trị cache và method không được gọi. Nếu không có entry, method chạy và kết quả có thể được lưu.

### Tạo key bằng SpEL

```java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findBook(ISBN isbn) {
    return repository.findByIsbn(isbn);
}
```

Key expression có thể chọn một argument, property của argument hoặc tính một giá trị từ nhiều tham số:

```java
@Cacheable(cacheNames = "books", key = "#isbn.rawNumber")
public Book findBook(ISBN isbn, boolean includeUsed) {
    // ...
}
```

```java
@Cacheable(cacheNames = "bookSearch", key = "#p0 + ':' + #p1")
public List<Book> search(String category, String language) {
    // ...
}
```

Expression `key` có thể trả về một object làm cache key, không bắt buộc phải là String. Key cần có semantics ổn định và `equals()`/`hashCode()` phù hợp với cache provider. Với key phức tạp hoặc được dùng ở nhiều method, cân nhắc một `KeyGenerator` riêng thay vì tạo chuỗi thủ công.

Nếu không chỉ định `key`, Spring dùng `SimpleKeyGenerator`: không có tham số thì dùng `SimpleKey.EMPTY`; một tham số thì dùng chính tham số đó; nhiều tham số thì dùng `SimpleKey` chứa các tham số. Nếu chỉ một vài tham số ảnh hưởng kết quả, expression `key` giúp bỏ qua các tham số chỉ phục vụ logic khác.

`key` và `keyGenerator` là hai cách chọn key loại trừ lẫn nhau trong cùng một cache operation; không khai báo cả hai.

### Điều kiện `condition`

`condition` được đánh giá trước khi method chạy. Nếu expression trả về true, cache operation được áp dụng; nếu false, method vẫn chạy nhưng caching behavior của operation bị bỏ qua.

```java
@Cacheable(cacheNames = "books", condition = "#name.length() < 32")
public Book findBook(String name) {
    // ...
}
```

Ví dụ chỉ cache các tên ngắn hơn 32 ký tự. `condition` có thể dùng arguments, properties và metadata của root object.

### Điều kiện loại trừ `unless`

`unless` được đánh giá sau khi method đã chạy. Nếu expression trả về true, kết quả không được thêm vào cache:

```java
@Cacheable(
    cacheNames = "books",
    key = "#isbn",
    unless = "#result == null"
)
public Book findBook(ISBN isbn) {
    // ...
}
```

Trong ví dụ này, kết quả null không được cache. `unless` phù hợp khi cần quyết định dựa trên kết quả thực tế, chẳng hạn chỉ cache object đã được xác minh hoặc không cache dữ liệu tạm thời.

## 5. `condition` và `unless` khác nhau ở thời điểm

Đây là khác biệt quan trọng nhất khi viết cache expressions:

| Thuộc tính | Thời điểm đánh giá | Có thể dùng `#result`? | Nếu biểu thức trả về true |
| --- | --- | --- | --- |
| `condition` | Trước khi method được gọi. | Không. | Cho phép cache operation tiếp tục. |
| `unless` | Sau khi method đã chạy. | Có. | Veto việc lưu kết quả vào cache. |

Không dùng `#result` trong `condition`, vì method chưa chạy và chưa có kết quả. Nếu quyết định cache phụ thuộc kết quả, dùng `unless` khi annotation hỗ trợ thuộc tính này.

Ví dụ với kết quả `Optional<Book>`:

```java
@Cacheable(
    cacheNames = "books",
    key = "#isbn",
    unless = "#result?.hardback"
)
public Optional<Book> findBook(ISBN isbn) {
    // ...
}
```

Với các wrapper được Spring Cache hỗ trợ như `Optional`, `#result` tham chiếu đến business object bên trong chứ không phải wrapper. Khi không có giá trị, `#result` có thể là null; dùng safe navigation `?.` nếu cần.

## 6. `@CachePut`: luôn chạy method rồi cập nhật cache

`@CachePut` dùng khi method phải thực thi mỗi lần, nhưng kết quả vẫn cần được ghi vào cache. Không giống `@Cacheable`, nó không bỏ qua method chỉ vì cache đã có entry.

```java
@CachePut(cacheNames = "books", key = "#isbn")
public Book updateBook(ISBN isbn, BookDescriptor descriptor) {
    return repository.update(isbn, descriptor);
}
```

Method chạy, trả về `Book`, rồi Spring dùng key expression để cập nhật entry tương ứng trong cache.

Vì method đã được gọi, `#result` có thể được dùng trong key expression của `@CachePut`:

```java
@CachePut(cacheNames = "books", key = "#result.isbn")
public Book updateBook(BookUpdate update) {
    return repository.update(update);
}
```

Trong trường hợp này key được lấy từ object trả về. Dùng `#result` chỉ khi method chắc chắn trả về một object phù hợp và expression xử lý đúng trường hợp null.

`@CachePut` cũng hỗ trợ `condition` và `unless`: condition được đánh giá trước invocation; unless được đánh giá sau invocation để có thể veto việc ghi kết quả. Không nên đặt `@Cacheable` và `@CachePut` trên cùng method nếu không có điều kiện loại trừ được thiết kế rõ ràng, vì một annotation muốn bỏ qua method còn annotation kia bắt buộc method phải chạy.

## 7. `@CacheEvict`: xóa entry theo key hoặc xóa toàn cache

`@CacheEvict` loại bỏ dữ liệu cache đã cũ. Dùng `key` để xóa một entry cụ thể:

```java
@CacheEvict(cacheNames = "books", key = "#isbn")
public void deleteBook(ISBN isbn) {
    repository.delete(isbn);
}
```

Mặc định `beforeInvocation` là false, nghĩa là eviction xảy ra sau khi method hoàn tất thành công. Nếu method ném exception, eviction sau invocation không được thực hiện.

Muốn xóa toàn bộ entry trong cache, dùng `allEntries = true`:

```java
@CacheEvict(cacheNames = "books", allEntries = true)
public void reloadBookCatalog() {
    repository.reloadCatalog();
}
```

Khi `allEntries = true`, Spring xóa toàn bộ cache; key cụ thể không còn áp dụng cho thao tác đó. Dùng `allEntries` khi thay đổi dữ liệu ảnh hưởng toàn bộ vùng cache.

### Evict trước khi method chạy

```java
@CacheEvict(cacheNames = "books", key = "#isbn", beforeInvocation = true)
public void refreshBook(ISBN isbn) {
    repository.refresh(isbn);
}
```

Với `beforeInvocation = true`, cache entry bị xóa trước khi method chạy, kể cả khi method sau đó ném exception. Dùng chế độ này khi việc xóa cache phải xảy ra bất kể kết quả method.

Khi eviction diễn ra sau invocation (`beforeInvocation = false`), `#result` có thể được dùng trong cache-evict expression. Khi eviction diễn ra trước invocation, chưa có kết quả nên không thể dựa vào `#result`.

`@CacheEvict` không có thuộc tính `unless`; nếu cần điều kiện thực hiện eviction, dùng `condition`.

## 8. `#result` có sẵn ở đâu?

`#result` là giá trị business được method trả về, nhưng chỉ khả dụng ở các expression chạy sau invocation:

| Vị trí expression | `#result` khả dụng? | Lý do |
| --- | --- | --- |
| `@Cacheable(key = ...)` | Không. | Key được tính trước khi method chạy để tra cache. |
| `@Cacheable(condition = ...)` | Không. | Condition được đánh giá trước invocation. |
| `@Cacheable(unless = ...)` | Có. | Unless chạy sau khi method trả về. |
| `@CachePut(key = ...)` | Có. | Method luôn chạy trước khi cache được cập nhật. |
| `@CachePut(condition = ...)` | Không. | Condition được đánh giá trước invocation. |
| `@CachePut(unless = ...)` | Có. | Unless chạy sau invocation. |
| `@CacheEvict(key/condition)` với `beforeInvocation = true` | Không. | Cache eviction được thực hiện trước method. |
| `@CacheEvict(key/condition)` với `beforeInvocation = false` | Có trong cache-evict expressions sau invocation. | Kết quả đã có khi operation chạy. |

Với `Optional` và các wrapper được hỗ trợ, `#result` là business object bên trong wrapper. Có thể dùng `#result?.property` để tránh lỗi khi không có giá trị.

## 9. Cache metadata trong biểu thức

Ngoài method arguments và `#result`, có thể dùng metadata của cache operation:

```java
@Cacheable(
    cacheNames = "books",
    key = "#root.methodName + ':' + #p0",
    condition = "#root.targetClass.simpleName == 'BookService'"
)
public Book findBook(ISBN isbn) {
    // ...
}
```

Ví dụ dùng cache metadata:

```spel
#root.methodName
#root.method.name
#root.targetClass
#root.args[0]
#root.caches[0].name
```

`#root.caches` là các cache đã được resolve cho operation. Chỉ dùng index `[0]` khi operation thực sự có cache tương ứng ở vị trí đó; nếu có nhiều cache, hãy hiểu rõ thứ tự và cấu hình resolution của ứng dụng.

## 10. Dùng `@Caching` và `@CacheConfig`

`@Caching` gom nhiều cache operations vào cùng một method, ví dụ xóa nhiều cache với key expression khác nhau:

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "books", key = "#p0"),
    @CacheEvict(cacheNames = "bookSearch", allEntries = true)
})
public void deleteBook(ISBN isbn) {
    // ...
}
```

`@CacheConfig` đặt cấu hình chung ở cấp class, như cache names, `KeyGenerator`, `CacheManager` hoặc `CacheResolver`:

```java
@CacheConfig(cacheNames = "books")
public class BookService {

    @Cacheable(key = "#isbn")
    public Book findBook(ISBN isbn) {
        // ...
    }
}
```

`@CacheConfig` chỉ chia sẻ cấu hình; nó không tự bật caching. Cấu hình ở cấp operation có thể ghi đè cấu hình chung ở class.

## 11. Proxy, self-invocation và method được intercept

Trong cấu hình mặc định, Spring xử lý cache annotations bằng proxy AOP. Chỉ các lời gọi đi qua proxy mới được intercept. Nếu một method trong cùng class gọi trực tiếp một method khác cũng có `@Cacheable`, lời gọi nội bộ đó thường không đi qua proxy nên caching annotation trên method được gọi không có hiệu lực.

Ví dụ:

```java
public Book loadForPage(ISBN isbn) {
    return findBook(isbn); // self-invocation: không đi qua proxy
}

@Cacheable(cacheNames = "books", key = "#isbn")
public Book findBook(ISBN isbn) {
    // ...
}
```

Để caching hoạt động, gọi method qua Spring-managed proxy từ một bean khác hoặc tách logic cacheable sang một bean riêng. AspectJ mode là lựa chọn khác khi ứng dụng cần interception ngoài proxy semantics, nhưng đòi hỏi cấu hình weaving.

Trong proxy mode, nên đặt cache annotations trên public methods của concrete class theo khuyến nghị Spring. Không nên dựa vào annotation trên private method hoặc self-invocation.

## 12. Key design và những điều cần tránh

Cache key cần đại diện cho toàn bộ input có ảnh hưởng đến kết quả. Nếu bỏ sót một tham số quan trọng, hai lời gọi khác nhau có thể dùng chung cache entry và trả về dữ liệu sai.

Ví dụ method:

```java
public Book findBook(ISBN isbn, String language) {
    // Kết quả phụ thuộc cả ISBN và language.
}
```

Key chỉ dùng `#isbn` có thể không đủ nếu cùng ISBN có nhiều bản dịch. Có thể dùng:

```java
@Cacheable(cacheNames = "books", key = "#isbn.rawNumber + ':' + #language")
```

Tránh các key:

- Dựa trên object mutable mà `equals()`/`hashCode()` thay đổi sau khi được đưa vào cache.
- Dùng `System.currentTimeMillis()`, random value hoặc trạng thái không ổn định khiến mỗi lần gọi tạo key khác.
- Ghép chuỗi mà không có delimiter hoặc encoding rõ ràng, gây va chạm giữa các cặp giá trị.
- Bỏ qua tenant, locale, user scope hoặc version nếu chúng ảnh hưởng dữ liệu trả về.
- Gọi method đắt tiền hoặc có side effect trong key expression.

Nếu logic key phức tạp, dùng `KeyGenerator` chuyên biệt để dễ kiểm thử và quản lý hơn. Key expression nên ngắn, có thể đọc và không thực hiện I/O.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `#isbn` không được phân giải | Tên tham số không có trong metadata. | Dùng `#p0`, `#a0` hoặc `#root.args[0]`; bật `-parameters` nếu cần tên. |
| `#result` null hoặc không có trong expression | Expression chạy trước method invocation. | Chỉ dùng `#result` trong `unless`, `@CachePut` key hoặc `@CacheEvict` sau invocation. |
| `@Cacheable` vẫn chạy method mỗi lần | Cache không hit, key khác nhau, condition false hoặc annotation không được intercept. | Kiểm tra key, cache name, condition, cache provider và proxy invocation. |
| `unless` lưu nhầm hoặc loại nhầm kết quả | Điều kiện veto bị đảo logic. | Nhớ `unless = true` nghĩa là không lưu kết quả; kiểm tra bằng ví dụ có kết quả cụ thể. |
| `@CachePut` không bỏ qua method khi cache có entry | Đây là hành vi đúng của `@CachePut`. | Dùng `@Cacheable` nếu mục tiêu là bỏ qua method khi cache hit. |
| Cache không bị xóa khi method lỗi | `beforeInvocation` mặc định là false và method không hoàn tất thành công. | Dùng `beforeInvocation = true` nếu cần xóa trước bất kể kết quả. |
| Toàn cache không được xóa | Đang dùng key eviction thay vì `allEntries = true`. | Bật `allEntries = true` cho cache-wide eviction. |
| Cùng method vừa cacheable vừa cache put có hành vi khó đoán | Hai operation có mục đích trái ngược. | Tách method hoặc dùng condition loại trừ rõ ràng; không dựa vào `#result` trong các condition được kiểm tra trước. |
| Caching annotation không hoạt động khi gọi nội bộ | Self-invocation không đi qua proxy mặc định. | Gọi qua Spring proxy hoặc tách method sang bean khác. |
| Dữ liệu của tenant/ngôn ngữ khác bị dùng chung | Cache key thiếu một phần input ảnh hưởng kết quả. | Bổ sung tenant, locale hoặc tham số cần thiết vào key. |

## Ghi nhớ

- `@Cacheable` kiểm tra cache trước và có thể bỏ qua method; `@CachePut` luôn chạy method rồi cập nhật cache; `@CacheEvict` xóa entry hoặc toàn cache.
- Cache annotation cần được bật bằng `@EnableCaching` hoặc cấu hình XML tương ứng.
- `key`, `condition` và `unless` là các SpEL expressions trong cache annotations; không cần bọc bằng `#{...}`.
- Dùng `#p0`, `#a0` hoặc `#root.args[0]` khi tên tham số không khả dụng.
- `condition` chạy trước invocation; `unless` chạy sau invocation và true sẽ veto việc lưu.
- `#result` chỉ có ở expression sau invocation: `unless`, `@CachePut` key và `@CacheEvict` khi `beforeInvocation=false`.
- `@CacheEvict` mặc định xóa sau khi method thành công; `beforeInvocation=true` xóa trước method; `allEntries=true` xóa toàn cache.
- `@CachePut` không bỏ qua method khi cache hit; tránh kết hợp tùy tiện với `@Cacheable` trên cùng method.
- `@CacheConfig` chia sẻ cấu hình class-level; `@Caching` gom nhiều cache operations; cả hai không tự bật caching.
- Proxy mode không intercept self-invocation; gọi qua proxy hoặc dùng thiết kế bean phù hợp.
- Cache key phải bao gồm mọi input ảnh hưởng kết quả và có semantics equals/hashCode ổn định.

## Tài liệu tham khảo

- [Spring Framework Reference — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework Reference — Cache SpEL Evaluation Context](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html#cache-spel-context)
- [Spring Framework API — Cacheable](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Framework API — CachePut](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html)
- [Spring Framework API — CacheEvict](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html)
- [Spring Framework API — CacheConfig](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheConfig.html)