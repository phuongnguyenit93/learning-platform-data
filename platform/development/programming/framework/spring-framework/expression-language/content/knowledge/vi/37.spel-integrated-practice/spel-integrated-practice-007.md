# Tích hợp SpEL vào @Value hoặc annotation cache

## 1. Tổng quan

Spring cho phép dùng Spring Expression Language (SpEL) trong nhiều annotation để lấy cấu hình, tính giá trị hoặc điều khiển hành vi ở runtime. Hai nơi thường gặp là:

- `@Value`: inject property bên ngoài hoặc giá trị được tính bằng SpEL vào field, constructor parameter hay method parameter.
- Cache annotations như `@Cacheable`, `@CachePut`, `@CacheEvict`: dùng SpEL để tạo cache key, quyết định có cache hay không và kiểm tra kết quả trước khi lưu.

Cùng dùng SpEL nhưng hai nơi này có EvaluationContext khác nhau:

| Vị trí | Mục đích | Dữ liệu SpEL có thể truy cập |
|---|---|---|
| `@Value` | Tính giá trị để inject vào bean. | Property placeholder, system properties, bean reference và các biểu thức SpEL được cấu hình trong ApplicationContext. |
| Cache annotation | Tạo key hoặc điều kiện cho một lần gọi method. | Method arguments, method/target metadata, danh sách cache và trong một số pha là `#result`. |

Không nên sao chép expression từ một annotation sang annotation khác mà không xem lại context. Ví dụ `#isbn` trong `@Cacheable` là tham số method; nó không tự tồn tại trong một `@Value` thông thường.

## 2. Điều kiện để annotation được xử lý

Các annotation phải được Spring xử lý trong ApplicationContext. Với `@Value`, bean phải được Spring tạo và xử lý bởi container. Với cache annotations, cần bật caching:

```java
@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books", "authors");
    }
}
```

`@EnableCaching` đăng ký infrastructure xử lý các annotation cache. Chỉ đặt `@Cacheable` lên method mà không bật caching thì method không tự được cache.

Ví dụ service:

```java
@Service
public class BookService {

    @Cacheable(cacheNames = "books", key = "#isbn")
    public Book findBook(ISBN isbn) {
        return repository.findByIsbn(isbn);
    }
}
```

CacheManager xác định cache provider và các cache mà annotation sử dụng. Trong ứng dụng thực tế, có thể dùng Caffeine, Redis hoặc provider khác; cú pháp SpEL của annotation không thay thế cấu hình cache provider.

## 3. Phân biệt property placeholder và SpEL trong @Value

Hai cú pháp thường gặp:

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| `${...}` | Lấy giá trị từ Environment/PropertySource. | `${catalog.name}` |
| `#{...}` | Đánh giá biểu thức SpEL. | `#{systemProperties['user.region']}` |

Dùng placeholder khi chỉ cần lấy cấu hình:

```properties
catalog.name=MovieCatalog
catalog.page-size=24
```

```java
@Component
public class MovieRecommender {

    private final String catalog;

    public MovieRecommender(
            @Value("${catalog.name}") String catalog) {
        this.catalog = catalog;
    }
}
```

Spring phân giải placeholder rồi chuyển giá trị sang kiểu đích nếu cần. Nếu property là `Integer`, `Boolean`, `Duration` hoặc kiểu có converter phù hợp, không nhất thiết phải tự parse chuỗi trong constructor.

Dùng SpEL khi cần tính toán hoặc truy cập cấu trúc dữ liệu:

```java
@Component
public class CatalogSettings {

    private final String catalog;

    public CatalogSettings(
            @Value("#{systemProperties['user.catalog'] + 'Catalog'}")
            String catalog) {
        this.catalog = catalog;
    }
}
```

Ở đây SpEL đọc system property `user.catalog`, nối thêm hậu tố `Catalog`, rồi inject kết quả.

## 4. Giá trị mặc định và chuyển đổi kiểu trong @Value

Placeholder hỗ trợ default value bằng dấu `:`:

```java
@Value("${catalog.page-size:20}")
private int pageSize;
```

Nếu `catalog.page-size` không được khai báo, Spring dùng giá trị mặc định 20. Giá trị String được chuyển thành `int` thông qua ConversionService.

Có thể inject collection hoặc array từ cấu hình:

```properties
catalog.supported-languages=en,vi,ja
```

```java
@Value("${catalog.supported-languages}")
private String[] supportedLanguages;
```

Với cấu hình nhiều trường liên quan, `@ConfigurationProperties` thường dễ tổ chức và kiểm tra hơn nhiều `@Value` rời rạc. `@Value` phù hợp cho một vài giá trị đơn lẻ hoặc biểu thức tính toán ngắn.

### 4.1. Placeholder không phân giải được

Trong cấu hình Spring thông thường, embedded value resolver mặc định có thể xử lý placeholder theo chế độ lenient. Nếu cần fail fast khi property bắt buộc bị thiếu, đăng ký `PropertySourcesPlaceholderConfigurer`:

```java
@Configuration
public class PropertyConfiguration {

    @Bean
    public static PropertySourcesPlaceholderConfigurer
            propertyPlaceholderConfigurer() {
        return new PropertySourcesPlaceholderConfigurer();
    }
}
```

Với Java configuration, method `@Bean` tạo configurer cần là `static`. Spring Boot mặc định cấu hình `PropertySourcesPlaceholderConfigurer` để đọc `application.properties` và `application.yml`.

Không đặt default cho một property bắt buộc chỉ để ứng dụng khởi động được. Với cấu hình quan trọng, fail fast thường giúp phát hiện lỗi triển khai sớm hơn.

## 5. Dùng SpEL để truy cập bean, static method và collection trong @Value

SpEL có thể tham chiếu bean trong ApplicationContext bằng cú pháp `@beanName`:

```java
@Component
public class DisplaySettings {

    private final String welcomeMessage;

    public DisplaySettings(
            @Value("#{@messageSettings.welcomeMessage}")
            String welcomeMessage) {
        this.welcomeMessage = welcomeMessage;
    }
}
```

Có thể gọi method hoặc đọc property trên bean nếu bean và method được phép truy cập trong expression context:

```java
@Value("#{ @regionSettings.defaultRegion().toUpperCase() }")
private String region;
```

Có thể gọi static method qua type reference:

```java
@Value("#{T(java.lang.Math).max(10, 25)}")
private int minimumPageSize;
```

SpEL cũng hỗ trợ literal collection:

```java
@Value("#{{'en': 'English', 'vi': 'Vietnamese'}}")
private Map<String, String> languageNames;
```

Các biểu thức này được đánh giá trong quá trình Spring xử lý việc inject bean. Giá trị field/constructor parameter không tự được tính lại mỗi khi property bên ngoài thay đổi. Nếu cần cấu hình thay đổi động, hãy dùng một bean cấu hình có cơ chế refresh rõ ràng hoặc truy vấn Environment/ConfigurationProperties theo thiết kế phù hợp.

## 6. Kết hợp placeholder và SpEL

Trong `@Value`, placeholder có thể được phân giải trước khi phần còn lại được đánh giá như SpEL. Điều này hữu ích khi muốn lấy một giá trị cấu hình rồi dùng nó trong phép tính:

```properties
catalog.page-size=24
```

```java
@Value("#{T(java.lang.Math).max(${catalog.page-size:20}, 10)}")
private int effectivePageSize;
```

Nếu property là 24, expression tính `max(24, 10)` và inject 24. Nếu property không có, placeholder cung cấp 20.

Cần giữ biểu thức ngắn và dễ đọc. Nếu công thức dài hoặc chứa nhiều điều kiện, chuyển logic vào một bean cấu hình có tên rõ ràng thay vì lồng nhiều placeholder và SpEL trong một annotation.

## 7. SpEL trong @Cacheable: tạo cache key

Cache key xác định một kết quả được lưu và tìm lại như thế nào. Nếu key không phản ánh đầy đủ các tham số ảnh hưởng đến kết quả, ứng dụng có thể trả dữ liệu cũ hoặc dữ liệu thuộc request khác.

Ví dụ method nhận ISBN cùng hai cờ:

```java
@Cacheable(
    cacheNames = "books",
    key = "#isbn.rawNumber"
)
public Book findBook(
        ISBN isbn,
        boolean checkWarehouse,
        boolean includeUsed) {
    return repository.findBook(
            isbn, checkWarehouse, includeUsed);
}
```

Expression `#isbn.rawNumber` chỉ lấy mã ISBN làm key. Cách này chỉ đúng nếu `checkWarehouse` và `includeUsed` không làm thay đổi kết quả. Nếu hai cờ có ảnh hưởng tới kết quả, chúng phải nằm trong key:

```java
@Cacheable(
    cacheNames = "books",
    key = "{#isbn.rawNumber, #checkWarehouse, #includeUsed}"
)
public Book findBook(
        ISBN isbn,
        boolean checkWarehouse,
        boolean includeUsed) {
    // ...
}
```

Có thể truy cập nested property, gọi method hoặc dùng static method:

```java
@Cacheable(cacheNames = "books", key = "#isbn.rawNumber")
public Book findBook(ISBN isbn) {
    // ...
}

@Cacheable(cacheNames = "books", key = "T(com.example.Keys).normalize(#isbn)")
public Book findBookByNormalizedIsbn(ISBN isbn) {
    // ...
}
```

Static helper nên thuần (pure), xác định và không có side effect. Key cần ổn định giữa các lần gọi và phải phân biệt mọi đầu vào có thể làm thay đổi kết quả.

## 8. Default key và khi nào cần SpEL

Nếu không khai báo `key` hoặc `keyGenerator`, Spring dùng `SimpleKeyGenerator` với quy tắc:

- Method không có tham số: dùng `SimpleKey.EMPTY`.
- Method có một tham số: dùng chính tham số đó.
- Method có nhiều tham số: dùng `SimpleKey` chứa tất cả tham số.

Default key phù hợp nếu các tham số có `equals()` và `hashCode()` ổn định, đồng thời tất cả tham số đều ảnh hưởng tới kết quả. Dùng SpEL khi chỉ một số tham số cần tham gia key hoặc cần lấy một nested property.

Hai thuộc tính `key` và `keyGenerator` loại trừ lẫn nhau. Không khai báo cả hai trên cùng một cache operation.

Ví dụ custom KeyGenerator:

```java
@Cacheable(
    cacheNames = "books",
    keyGenerator = "bookKeyGenerator"
)
public Book findBook(ISBN isbn, boolean includeUsed) {
    // ...
}
```

Nếu logic tạo key có thể dùng lại ở nhiều method hoặc quá phức tạp cho một expression ngắn, custom KeyGenerator thường dễ kiểm thử hơn.

## 9. Cache annotation có EvaluationContext riêng

SpEL trong cache annotations được đánh giá trên context do Spring Cache tạo ra. Root object cung cấp metadata về method đang được gọi:

| Biểu thức | Ý nghĩa |
|---|---|
| `#root.methodName` | Tên method. |
| `#root.method` | Method đang được gọi. |
| `#root.target` | Target object. |
| `#root.targetClass` | Class của target. |
| `#root.args` | Mảng các đối số truyền vào method. |
| `#root.args[0]` | Đối số đầu tiên. |
| `#root.caches` | Các cache được dùng cho operation hiện tại. |
| `#root.caches[0].name` | Tên cache đầu tiên. |
| `#isbn` | Tham số method có tên isbn, nếu tên tham số được phát hiện. |
| `#a0`, `#p0` | Alias truy cập tham số đầu tiên theo index. |
| `#result` | Kết quả method, chỉ có trong các expression phase được hỗ trợ. |

Ví dụ dùng index để không phụ thuộc tên tham số:

```java
@Cacheable(cacheNames = "books", key = "#a0.rawNumber")
public Book findBook(ISBN isbn) {
    // ...
}
```

Nếu muốn dùng tên tham số như `#isbn`, cần bảo đảm metadata tên tham số được giữ trong bytecode (thường bật compiler option `-parameters`). Khi không chắc tên có sẵn, dùng `#a0` hoặc `#p0`.

Root object của cache expression không phải root domain object mà SpEL thường nhận trong một expression độc lập. Ví dụ `#root.target` là bean đang được gọi; `#root.args[0]` là đối số method.

## 10. condition và unless khác nhau

`@Cacheable` có hai thuộc tính để điều khiển việc lưu:

- `condition` được đánh giá trước khi method chạy. Nếu false, Spring bỏ qua caching cho invocation đó và method vẫn được gọi.
- `unless` được đánh giá sau khi method chạy. Nếu true, kết quả không được đưa vào cache.

Ví dụ chỉ cache tên ngắn:

```java
@Cacheable(
    cacheNames = "books",
    condition = "#name.length() < 32"
)
public Book findBook(String name) {
    // ...
}
```

Ví dụ không cache sách bìa cứng:

```java
@Cacheable(
    cacheNames = "books",
    key = "#isbn",
    unless = "#result.hardback"
)
public Book findBook(ISBN isbn) {
    // ...
}
```

Không dùng `#result` trong `condition` của `@Cacheable`, vì condition được đánh giá trước khi method được gọi. Dùng `#result` trong `unless`, khi kết quả đã có.

Với return type `Optional<Book>`, cache abstraction unwrap giá trị business object cho `#result`. Vì kết quả có thể null, dùng safe navigation:

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

## 11. @CachePut: luôn gọi method rồi cập nhật cache

Khác với `@Cacheable`, `@CachePut` không bỏ qua method khi cache đã có dữ liệu. Method luôn được thực thi và kết quả được đưa vào cache theo key được tính:

```java
@CachePut(cacheNames = "books", key = "#isbn")
public Book updateBook(ISBN isbn, BookDescriptor descriptor) {
    return repository.update(isbn, descriptor);
}
```

Có thể dùng SpEL trong `key`, `condition` và `unless` tương tự các cache operation khác. `#result` có thể được dùng ở các pha mà kết quả đã có.

Không nên đặt `@Cacheable` và `@CachePut` lên cùng một method một cách tùy tiện. Một annotation muốn bỏ qua method khi cache hit, annotation kia buộc method phải chạy. Hai hành vi có thể xung đột. Nếu cần phối hợp, điều kiện của chúng phải loại trừ nhau rõ ràng và được kiểm thử.

## 12. @CacheEvict: xóa cache theo key hoặc toàn bộ vùng cache

`@CacheEvict` xóa một entry theo key:

```java
@CacheEvict(cacheNames = "books", key = "#isbn")
public void deleteBook(ISBN isbn) {
    repository.delete(isbn);
}
```

Có thể xóa toàn bộ cache region:

```java
@CacheEvict(cacheNames = "books", allEntries = true)
public void importBooks(InputStream batch) {
    repository.importBooks(batch);
}
```

Thuộc tính `beforeInvocation` quyết định thời điểm xóa:

- Mặc định `false`: xóa sau khi method chạy thành công.
- `true`: xóa trước khi method được gọi, bất kể method sau đó thành công hay ném exception.

Ví dụ xóa cache trước khi thực hiện thao tác có thể làm dữ liệu cũ không còn được đọc trong lúc cập nhật:

```java
@CacheEvict(
    cacheNames = "books",
    key = "#isbn",
    beforeInvocation = true
)
public void rebuildBookIndex(ISBN isbn) {
    // ...
}
```

Khi `beforeInvocation=true`, không thể dùng `#result` trong expression key/condition vì method chưa được thực thi. `allEntries=true` xóa toàn bộ cache; key riêng không còn ý nghĩa trong trường hợp này.

## 13. @Caching và @CacheConfig

Dùng `@Caching` khi một method cần nhiều thao tác cache hoặc nhiều key/condition khác nhau:

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "books", key = "#isbn"),
    @CacheEvict(cacheNames = "book-search", allEntries = true)
})
public void updateBook(ISBN isbn, BookDescriptor descriptor) {
    // ...
}
```

Dùng `@CacheConfig` để chia sẻ cấu hình cache ở cấp class:

```java
@Service
@CacheConfig(cacheNames = "books")
public class BookService {

    @Cacheable(key = "#isbn")
    public Book findBook(ISBN isbn) {
        // ...
    }

    @CacheEvict(key = "#isbn")
    public void deleteBook(ISBN isbn) {
        // ...
    }
}
```

`@CacheConfig` chỉ cung cấp cấu hình chung; bản thân annotation này không bật caching. Cấu hình ở operation-level sẽ ghi đè cấu hình chung khi có khai báo tương ứng.

## 14. Kích hoạt caching và giới hạn proxy

Trong chế độ mặc định, Spring áp dụng cache annotations thông qua AOP proxy. Vì vậy:

- Lời gọi từ bên ngoài đi qua proxy mới được intercept.
- Self-invocation (method trong cùng class gọi method khác của chính object) không đi qua proxy và không kích hoạt cache advice.
- Với proxy mode, nên đặt cache annotation trên public method của concrete class.
- Không dựa vào cache proxy trong `@PostConstruct` hoặc giai đoạn bean chưa khởi tạo xong.

Ví dụ self-invocation không kích hoạt cache như mong đợi:

```java
@Service
public class BookService {

    public Book load(String isbn) {
        return findCached(isbn); // Gọi nội bộ trên this.
    }

    @Cacheable(cacheNames = "books", key = "#isbn")
    public Book findCached(String isbn) {
        return repository.findByIsbn(isbn);
    }
}
```

Có thể tách method cache sang một bean khác để lời gọi đi qua proxy:

```java
@Service
public class CachedBookLookup {

    @Cacheable(cacheNames = "books", key = "#isbn")
    public Book findCached(String isbn) {
        return repository.findByIsbn(isbn);
    }
}
```

Hoặc cân nhắc AspectJ weaving nếu ứng dụng cần intercept self-invocation/non-public method và chấp nhận cấu hình weaving tương ứng.

## 15. Chọn cache key đúng và an toàn

Cache key là một phần của tính đúng đắn và bảo mật dữ liệu. Nếu key thiếu tham số có ảnh hưởng đến kết quả, cache có thể trả nhầm dữ liệu.

Các nguyên tắc:

- Bao gồm mọi tham số làm thay đổi kết quả.
- Bao gồm tenant, locale, user scope hoặc version nếu chúng ảnh hưởng kết quả.
- Không đưa token, password hoặc dữ liệu bí mật vào key/log.
- Ưu tiên key bất biến với `equals()`/`hashCode()` ổn định.
- Tránh gọi method có side effect hoặc I/O trong key expression.
- Không dùng `#root.target` làm key nếu target object không có identity semantics ổn định.
- Không dùng cùng cache region cho hai loại dữ liệu có cấu trúc/ý nghĩa khác nhau nếu key có thể va chạm.

Ví dụ key có tenant và ISBN:

```java
@Cacheable(
    cacheNames = "tenant-books",
    key = "{#tenantId, #isbn.rawNumber}"
)
public Book findBook(String tenantId, ISBN isbn) {
    // ...
}
```

Nếu tenant không nằm trong key trong khi kết quả phụ thuộc tenant, dữ liệu của tenant này có thể bị trả cho tenant khác. Đây là lỗi correctness và có thể trở thành rò rỉ dữ liệu.

## 16. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `@Value` inject nguyên chuỗi `${...}` | Placeholder chưa được cấu hình/phân giải hoặc resolver đang lenient. | Kiểm tra PropertySource và PropertySourcesPlaceholderConfigurer. |
| `@Value` SpEL không tìm thấy bean | Sai bean name hoặc bean chưa nằm trong ApplicationContext. | Kiểm tra tên bean và context chứa bean. |
| `#isbn` không được nhận diện trong cache key | Parameter name metadata không có. | Dùng `#a0`/`#p0` hoặc biên dịch với `-parameters`. |
| Cache key va chạm hoặc trả dữ liệu sai | Key bỏ sót tham số ảnh hưởng kết quả. | Bổ sung các tham số cần thiết vào key. |
| `#result` không dùng được trong condition | Condition chạy trước method invocation. | Dùng `#result` trong unless hoặc pha sau invocation được hỗ trợ. |
| `@CachePut` và `@Cacheable` gây hành vi khó hiểu | Một annotation bỏ qua method, annotation kia buộc method chạy. | Tách method hoặc thiết kế điều kiện loại trừ nhau rõ ràng. |
| Cache annotation không có tác dụng | Chưa bật `@EnableCaching` hoặc bean không được proxy. | Kiểm tra cache configuration và ApplicationContext. |
| Lời gọi nội bộ không cache | Self-invocation không đi qua proxy. | Tách method sang bean khác hoặc dùng AspectJ. |
| `@CacheEvict` không xóa khi method lỗi | Mặc định eviction diễn ra sau khi method thành công. | Dùng `beforeInvocation=true` nếu nghiệp vụ yêu cầu. |
| `key` và `keyGenerator` cùng được khai báo | Hai thuộc tính loại trừ lẫn nhau. | Chọn một cách tạo key. |
| `cacheManager` và `cacheResolver` cùng được khai báo | Hai cơ chế phân giải cache loại trừ lẫn nhau. | Chọn CacheManager hoặc CacheResolver. |
| SpEL trong @Value không cập nhật khi property thay đổi | Giá trị được inject trong vòng đời khởi tạo bean. | Dùng cơ chế refresh/configuration động phù hợp. |

## 17. Quy trình tích hợp SpEL vào annotation

1. Xác định annotation cần dùng là `@Value` hay cache annotation.
2. Với `@Value`, dùng placeholder cho cấu hình đơn giản và SpEL cho phép tính/bean reference.
3. Khai báo default value có chủ đích; cấu hình strict placeholder nếu property bắt buộc.
4. Xác định kiểu đích và ConversionService nếu cần converter tùy chỉnh.
5. Với cache, bật `@EnableCaching` và cấu hình CacheManager/CacheResolver.
6. Xác định key phản ánh đầy đủ mọi đầu vào ảnh hưởng kết quả.
7. Dùng `#a0`/`#p0` nếu tên tham số không được giữ trong bytecode.
8. Phân biệt `condition` (trước invocation) với `unless` (sau invocation).
9. Chỉ dùng `#result` trong các pha mà cache abstraction cung cấp kết quả.
10. Chọn đúng annotation: `@Cacheable` để đọc/điền cache, `@CachePut` để luôn chạy method và cập nhật cache, `@CacheEvict` để xóa.
11. Kiểm tra proxy semantics, public method và self-invocation.
12. Test cache hit/miss, key, condition, unless, eviction, property resolution và conversion.

## 18. Ghi nhớ

- `@Value` dùng `${...}` để lấy property và `#{...}` để đánh giá SpEL.
- `@Value` có thể đọc system property, bean, static member và collection literal.
- Giá trị `@Value` được inject trong quá trình xử lý bean; không tự refresh khi cấu hình đổi.
- Cache annotations có EvaluationContext riêng với `#root.method`, `#root.target`, `#root.args`, argument variables và `#result` theo từng phase.
- Dùng SpEL `key` để chọn tham số hoặc nested property tạo cache key.
- `condition` được đánh giá trước method; `unless` được đánh giá sau method.
- `#result` chỉ có trong các expression phase được hỗ trợ, không có trong condition của `@Cacheable`.
- `@Cacheable` có thể bỏ qua method khi cache hit; `@CachePut` luôn chạy method; `@CacheEvict` xóa cache.
- `@EnableCaching` bật annotation-driven caching; proxy mode không intercept self-invocation.
- Cache key phải chứa mọi yếu tố làm thay đổi kết quả, bao gồm tenant/locale nếu có liên quan.

## Tài liệu tham khảo

- [Spring Framework Reference — Using @Value](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)
- [Spring Framework Reference — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework Reference — SpEL Evaluation Context](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Javadoc — Cacheable](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Framework Javadoc — CachePut](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html)
- [Spring Framework Javadoc — CacheEvict](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html)
