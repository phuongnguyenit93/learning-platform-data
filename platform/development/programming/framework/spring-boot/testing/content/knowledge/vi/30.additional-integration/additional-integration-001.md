# Kiểm thử @Cacheable, @CachePut, @CacheEvict qua bean proxy trong Spring Boot

## 1. Vấn đề: annotation có trong mã nhưng cache có thật sự hoạt động?

Spring Cache cho phép bổ sung caching vào các phương thức service mà không phải tự viết `Map.get`/`Map.put` trong từng method. Ví dụ:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Book find(String isbn) {
    return repository.load(isbn);
}
~~~

Với lời gọi đi qua **Spring-managed proxy**, lần đầu đọc cùng key là *cache miss*: thực thi method và lưu kết quả. Các lần tiếp theo là *cache hit*: proxy trả kết quả từ cache mà **không chạy method body**.

Tuy nhiên, có ít nhất bốn cách khiến một bài test kết luận sai:

1. Test dùng `new BookService(...)` rồi gọi method, không đi qua Spring proxy.
2. Method trong bean gọi `this.find(isbn)`, self-invocation bỏ qua advice ở proxy mode.
3. Test đặt `spring.cache.type=none` hoặc dùng một no-op CacheManager rồi chỉ assert giá trị trả về.
4. Test chỉ so sánh hai giá trị bằng nhau, không kiểm **số lần truy cập dependency**, trạng thái cache và tính đúng của `@CachePut`/`@CacheEvict`.

Bài này kiểm **behavior + proxy wiring + cache state** trong một ứng dụng Java 17+/Spring Boot 3.5.x:

- `@Cacheable`: miss → chạy phương thức; hit → bỏ qua phương thức.
- `@CachePut`: luôn chạy phương thức, dùng result để cập nhật đúng key trong cache.
- `@CacheEvict`: xóa entry hoặc toàn bộ region, mặc định sau thành công, có thể trước method.
- `@Caching` và `@CacheConfig`: ghép nhiều thao tác và dùng cache names chung.
- `condition` và `unless`: quyết định **trước** và **sau** invocation có dùng cache không.
- Self-invocation và raw object: chứng minh test phải gọi **bean qua proxy**.
- Test isolation: xóa cache và reset fake repository giữa các test, không phá ApplicationContext.

### Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt Spring Cache abstraction với một cache store cụ thể.
2. Bật `@EnableCaching` và xác nhận bean thực sự được proxy.
3. Kiểm cả result, backend invocation count, cache entry và cache key.
4. Test cache hit, miss, key khác nhau, exception không được cache mặc định.
5. Kiểm update/invalidation từ `@CachePut`, `@CacheEvict`, `allEntries` và `beforeInvocation`.
6. Kiểm `@Caching` xóa nhiều cache regions.
7. Chứng minh `condition` không cache theo input, `unless` veto theo result.
8. Xác định vì sao self-invocation bypass proxy và cách refactor.
9. Cô lập cache giữa các bài trong Spring TestContext được cache.
10. Biết khi nào bài test ConcurrentMap là đủ và khi nào cần Redis/Caffeine/transaction/concurrency integration.

## 2. Spring Cache abstraction gồm những thành phần nào?

Spring Cache chủ yếu có:

- `Cache`: giao diện đọc/ghi/evict entry, ví dụ `get`, `put`, `evict` và `clear`.
- `CacheManager`: tìm cache theo tên, ví dụ region `books`.
- `CacheResolver`: có thể xác định một hoặc nhiều caches dựa vào context của lời gọi.
- `KeyGenerator`: tạo key khi không khai báo `key`.
- Cache interceptor / AOP advice: được kích hoạt bởi annotation trên method đi **qua proxy**.
- Cache provider: ConcurrentMap, Caffeine, Redis, JCache, Hazelcast, v.v. với TTL/serialization/cluster semantics khác nhau.

Sơ đồ:

~~~text
JUnit / Controller / Other bean
             |
             v
   BookQueryService Spring PROXY
             |
             +-- Compute key "A"
             |
             +-- CacheManager -> Cache "books"
             |                      |
             |                  Cache.get("A")
             |                      |
             |                +-----+------+
             |                |            |
             |               HIT          MISS
             |                |            |
             |                |     target BookQueryService.get("A")
             |                |            |
             |                |         BookCatalog.load("A")
             |                |            |
             |                |       Cache.put("A", Book)
             |                |            |
             +----------------+------------+
                              |
                              v
                           Book result
~~~

**Cache hit không phải “target method chạy nhanh hơn”**. Với `@Cacheable`, target method body thường **không được gọi** khi entry có sẵn. Vì vậy test phải assert repository/load count giữ nguyên trên cache hit.

### 2.1 Cache là optimization, không thay database

Cache có thể chứa stale data nếu không được invalidate/update đúng. Source of truth vẫn là database/remote service (trong ví dụ là `BookCatalog`), không phải cache. Không dùng cache như một cơ chế bảo mật: quyền truy cập phải được kiểm đúng, đặc biệt khi cache key cần chứa tenant/user scope.

## 3. Ba annotation chính

| Annotation | Cache miss | Cache hit | Tác dụng với cache |
| --- | --- | --- | --- |
| `@Cacheable` | Chạy method, lưu result | Trả cached result, bỏ qua method | Cache population/lookup |
| `@CachePut` | Luôn chạy method | **Vẫn chạy** method | Đặt/update cache bằng result |
| `@CacheEvict` | Chạy method (thường) | Không dùng cache để skip method | Xóa key hoặc toàn region |

Ví dụ đơn giản:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Book find(String isbn) {
    return catalog.load(isbn);
}

@CachePut(cacheNames = "books", key = "#result.isbn()")
public Book save(Book book) {
    return catalog.store(book);
}

@CacheEvict(cacheNames = "books", key = "#p0")
public void remove(String isbn) {
    catalog.delete(isbn);
}
~~~

Đây là **trích đoạn minh họa**; phần sau có toàn bộ file và tests độc lập.

Cùng region `books` và cùng key (ISBN) là **điều kiện bắt buộc** nếu muốn `save` cập nhật giá trị mà `find` đọc, hoặc `remove` xóa giá trị mà `find` lưu. Một test riêng cho `@CachePut` có thể PASS nếu nó cập nhật một region sai mà không hề ảnh hưởng cache dùng ở `@Cacheable`. Vì thế phải test **cross-method interaction**.

## 4. @EnableCaching và proxy thật

### 4.1 Bật cache annotations

~~~java
@Configuration(proxyBeanMethods = false)
@EnableCaching(proxyTargetClass = true)
class CachingConfiguration {
    // @Bean CacheManager ...
}
~~~

`@EnableCaching` đăng ký caching infrastructure. `proxyTargetClass=true` yêu cầu class-based proxies; đây là lựa chọn rõ ràng cho ví dụ inject concrete service classes. Không có nghĩa mọi final/private method đều được intercept.

Spring Boot cũng có auto-configuration cho `CacheManager` khi bật cache support; nhưng ví dụ cung cấp `ConcurrentMapCacheManager` riêng để test deterministic, không phụ thuộc provider vô tình có trên classpath.

Tài liệu Spring Boot khuyến nghị không gắn `@EnableCaching` trực tiếp lên main application class nếu không muốn caching là requirement cho **mọi** test/slice. Tách ra một configuration class giúp kiểm soát khi cần test với/không với cache.

### 4.2 Proxy mode và self-invocation

Khi caller gọi:

~~~java
Book b = springBean.get("A");
~~~

và `springBean` là proxy, caching interceptor được chạy. Nhưng bên trong target bean:

~~~java
public Book getTwice(String isbn) {
    Book a = this.get(isbn);
    Book b = this.get(isbn);
    return b;
}
~~~

các `this.get` là self-invocations lên target object, **không đi qua proxy** theo AOP proxy mode. Hai lần truy cập catalog vẫn xảy ra dù method `get` có `@Cacheable`.

Điều này **không** phải “cache của Spring hỏng”. Nó là hệ quả của đường gọi. Cách sửa tốt là tách cached method sang bean khác, để bean orchestration inject bean cached và gọi qua proxy. Có thể dùng AspectJ weaving, nhưng đó là một deployment/design khác với proxy mặc định và cần kiểm riêng.

### 4.3 Không chỉ assert annotation tồn tại

~~~java
assertTrue(AopUtils.isAopProxy(bookQueries));
~~~

Đây là assertion kỹ thuật hữu ích để biết bean được wrapped. Tuy nhiên **chỉ có proxy cũng chưa đủ**: proxy có thể phục vụ transaction, security hoặc một advice khác. Vẫn phải kiểm cache hit không gọi `BookCatalog.load` lần nữa, và cache entry được thêm/xóa đúng.

## 5. Chọn CacheManager đúng cho test

| Test mục tiêu | CacheManager đề xuất | Lưu ý |
| --- | --- | --- |
| Kiểm annotation/proxy/key/eviction logic | `ConcurrentMapCacheManager` | Nhanh, in-memory, deterministic |
| Không cần caching trong ordinary tests | `NoOpCacheManager` hoặc `spring.cache.type=none` | **Không** chứng minh @Cacheable có tác dụng |
| Kiểm TTL/max size/eviction policy của Caffeine | `CaffeineCacheManager` | Cần provider thật, kiểm timer/expiry phù hợp |
| Kiểm serialization, key prefix, TTL, Redis network | `RedisCacheManager` + Testcontainers | In-memory map không tương đương Redis |
| Kiểm JCache/Hazelcast/etc. | Provider cụ thể | Test contract/provider config riêng |
| Kiểm production DB transaction + cache consistency | Cache thật + database integration | Cần test commit/rollback boundaries |

Spring Boot 3.5 có thể chọn simple provider dựa trên concurrent maps nếu không tìm provider khác. Nhưng **bài cần cache thật đang hoạt động**, nên dùng explicit `CacheManager` bean.

Không vô tình đặt:

~~~properties
spring.cache.type=none
~~~

trong bộ test đang muốn chứng minh behavior cache: khi cache là no-op, gọi `@Cacheable` hai lần vẫn thực thi method hai lần. Thuộc tính đó rất hữu ích ở **các test không kiểm caching** để tránh test pollution, nhưng không phải trong cache proxy integration test.

## 6. Chọn key chính xác: không vô tình chia sẻ dữ liệu giữa users/tenants

Spring mặc định dùng `SimpleKeyGenerator`:

| Tham số method | Key mặc định |
| --- | --- |
| Không có tham số | `SimpleKey.EMPTY` |
| Một tham số (khác null) | Chính đối tượng tham số đó |
| Nhiều tham số | `SimpleKey` chứa các tham số |

Để test rõ ràng, bài dùng `key="#p0"`: đối số đầu tiên là ISBN. So với `key="#isbn"`, `#p0` không phụ thuộc tên parameter được ghi vào bytecode bằng compiler flag `-parameters`.

Ví dụ:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Book get(String isbn) {
    return catalog.load(isbn);
}
~~~

### 6.1 Một cache, nhiều keys

Khi gọi `get("A")` hai lần thì catalog chỉ chạy một lần. Nhưng `get("B")` phải có **cache entry khác**. Test chỉ kiểm một key có thể bỏ sót lỗi key cố định:

~~~java
// Sai: mọi ISBN dùng cùng một cache entry.
@Cacheable(cacheNames = "books", key = "'singleton'")
~~~

Annotation này là **anti-pattern minh họa**, không được dùng trong project runnable.

### 6.2 Multi-tenant keys

Nếu một method:

~~~java
public Book getForTenant(String tenantId, String isbn)
~~~

và cache dùng key chỉ là `isbn` thì tenant A và tenant B có thể chia sẻ cached result. Điều này vừa sai dữ liệu vừa có nguy cơ lộ thông tin. Key phải bao gồm **tenant scope đã xác thực**, ví dụ:

~~~java
@Cacheable(cacheNames = "tenantBooks", key = "#p0 + ':' + #p1")
public Book getForTenant(String tenantId, String isbn) {
    // Truy vấn vẫn phải enforce tenant permission.
}
~~~

Đây là fragment minh họa. Nếu values chứa ký tự delimiter, hãy dùng composite typed key/KeyGenerator tránh collision; không coi cache key là lớp authorization. Cần negative test tenant A không lấy được kết quả của tenant B.

## 7. @Cacheable: cache hit, miss, exception, condition và unless

`@Cacheable` hỏi cache trước:

~~~text
get("A") first call
    cache.get("A") -> miss
    catalog.load("A") -> Book("A", "Alpha")
    cache.put("A", Book)
    return Book

get("A") second call
    cache.get("A") -> hit
    catalog.load NOT CALLED
    return cached Book
~~~

Đó là test quan trọng nhất:

~~~java
assertEquals(new Book("A", "Alpha"), queries.get("A"));
assertEquals(new Book("A", "Alpha"), queries.get("A"));
assertEquals(1, catalog.reads());
assertNotNull(cache("books").get("A"));
~~~

### 7.1 Exception mặc định không được lưu như một cached success

Nếu `catalog.load("UNKNOWN")` ném `NoSuchElementException`, lời gọi `@Cacheable` không sinh ra giá trị thành công để lưu. Hai lời gọi cùng key sau đó thường chạy catalog hai lần và ném exception hai lần. Test kiểm `reads()==2` và cache không có entry.

**Lưu ý:** một số application cố ý chuyển “not found” thành `null` hoặc `Optional.empty()`, có thể kích hoạt null/negative caching tùy provider và cấu hình. Đừng gộp hành vi đó với uncaught exception.

### 7.2 condition được xét trước method

~~~java
@Cacheable(
    cacheNames = "conditionalBooks",
    key = "#p0",
    condition = "#p0.startsWith('C-')")
~~~

Với ISBN không có prefix `C-`, cache advice không sử dụng cache; target method chạy mỗi lần. Ví dụ `getConditional("A")` hai lần → `catalog.reads()==2`.

### 7.3 unless được xét sau khi có result

~~~java
@Cacheable(
    cacheNames = "conditionalBooks",
    key = "#p0",
    unless = "#result.title().startsWith('Skip')")
~~~

Với result có title bắt đầu `Skip`, method vẫn chạy nhưng cache put bị veto. Gọi lần nữa sẽ chạy catalog nữa. Với title hợp lệ, lần đầu cache put, lần hai là hit.

**Phân biệt:**

- `condition` dùng input, quyết định trước target invocation có xét cache không.
- `unless` dùng return value, chỉ có thể veto cache population **sau khi method trả result**.
- `#result` trong `unless` là giá trị sau invocation, không dùng trong cache key cần tính trước gọi.
- Nếu result có thể null, dùng null-safe SpEL hoặc condition phù hợp; ví dụ trong bài không trả null.

### 7.4 sync=true

~~~java
@Cacheable(cacheNames = "books", key = "#p0", sync = true)
public Book getSynchronized(String isbn) {
    return catalog.load(isbn);
}
~~~

Đây là **mẫu minh họa riêng**, không phải method của mini-project. `sync=true` gợi ý cache provider chỉ tính một lần khi nhiều threads đồng thời miss cùng key. Có hạn chế khi kết hợp với `unless`, nhiều cache names và một số provider. Không suy ra **distributed lock** trên mọi JVM/Redis instance; phải test concurrency/provider thật nếu có yêu cầu chống cache stampede.

## 8. @CachePut: method luôn chạy và result cập nhật cache

Ví dụ:

~~~java
@CachePut(cacheNames = "books", key = "#result.isbn()")
public Book save(Book book) {
    return catalog.store(book);
}
~~~

Khi gọi `save(new Book("A","New"))`:

1. Method `catalog.store(...)` **luôn chạy**, dù `books["A"]` đã có giá trị.
2. Sau khi thành công, cache put dùng ISBN lấy từ `#result.isbn()`.
3. `get("A")` lần kế tiếp trả Book mới từ cache mà **không load catalog**.

Test phải chứng minh cả hai:

~~~java
assertEquals(2, catalog.writes()); // Hai lời gọi save.
assertEquals(new Book("A", "New 2"), queries.get("A"));
assertEquals(1, catalog.reads());  // Không cần đọc lại.
~~~

`@CachePut` khác `@Cacheable` ở chỗ nó **không skip method trên hit**.

### 8.1 Key alignment

Nếu `@Cacheable(key="#p0")` lưu theo ISBN nhưng `@CachePut` lưu theo `Book` object, một update có thể ghi vào **key khác**:

~~~text
Cacheable: books["A"] = old Book
CachePut: books[Book("A","New")] = new Book
next get("A") -> old Book
~~~

Do đó bài dùng `@CachePut(key="#result.isbn()")` để đồng nhất với `@Cacheable(key="#p0")`. Một bài test chỉ assert `cache entry mới tồn tại` có thể bỏ sót stale entry ở key cũ; phải test `queries.get("A")` ngay sau update.

### 8.2 Không kết hợp @CachePut và @Cacheable trên cùng method tùy tiện

Hai annotation có behavior đối lập: `@Cacheable` có thể bỏ qua method, `@CachePut` yêu cầu method luôn thực thi. Spring Framework không khuyến nghị kết hợp chúng trên cùng một method trừ trường hợp conditions được thiết kế loại trừ nhau rõ ràng. Tách read/cacheable và write/cacheput thành methods riêng sẽ dễ kiểm hơn.

## 9. @CacheEvict: xóa key, toàn region, trước hay sau method

### 9.1 Evict một key sau thành công (mặc định)

~~~java
@CacheEvict(cacheNames = "books", key = "#p0")
public void remove(String isbn) {
    catalog.delete(isbn);
}
~~~

Default `beforeInvocation=false`. Nếu method chạy **thành công**, Spring evict key từ cache sau đó. Lần `get("A")` tiếp theo sẽ miss và đọc repository: có thể thấy bản ghi mới hoặc nhận not-found.

### 9.2 Evict không đổi source of truth

~~~java
@CacheEvict(cacheNames = "books", key = "#p0")
public void invalidate(String isbn) {
    // Chỉ invalidate cache; catalog dữ liệu không đổi.
}
~~~

Method này hữu ích khi source data được thay bởi một thao tác khác, ví dụ integration event. Test có thể sửa fake catalog trực tiếp, gọi invalidate, rồi assert lần đọc sau lấy giá trị mới. Đừng nhầm "evict" là "delete database record": `@CacheEvict` chỉ thao tác với cache abstraction.

### 9.3 allEntries=true

~~~java
@CacheEvict(cacheNames = "books", allEntries = true)
public void invalidateAll() {
}
~~~

Xóa **toàn bộ region books**. Không khai báo `key` đồng thời với `allEntries=true`; key không có ý nghĩa khi clear tất cả. Với cache phân vùng theo tenant, một `allEntries=true` có thể xóa của nhiều tenant, ảnh hưởng hiệu năng và concurrency; chỉ dùng khi policy yêu cầu.

### 9.4 beforeInvocation=false và exception

~~~java
@CacheEvict(cacheNames = "books", key = "#p0")
public void failAfter(String isbn) {
    throw new IllegalStateException("after failure");
}
~~~

Nếu method ném exception, **evict không diễn ra** ở chế độ mặc định. Test cache được seed từ trước, gọi failAfter rồi kiểm entry vẫn ở đó.

### 9.5 beforeInvocation=true và exception

~~~java
@CacheEvict(
    cacheNames = "books",
    key = "#p0",
    beforeInvocation = true)
public void failBefore(String isbn) {
    throw new IllegalStateException("before failure");
}
~~~

Cache entry bị xóa **trước** khi chạy method, dù method sau đó ném exception. Điều này khác biệt lớn nếu method có transaction chưa commit hoặc validation có thể fail. Test phải kiểm entry không còn và lần đọc sau thực sự reload.

**Đừng mặc định beforeInvocation=true là “an toàn hơn”.** Với update thất bại và rollback DB, việc evict trước có thể gây unnecessary misses; với transaction khác, eviction timing có thể tạo stale reads. Chọn chính sách nhất quán theo business.

## 10. @CacheConfig và @Caching

### 10.1 @CacheConfig

Nếu nhiều methods dùng region `books`, có thể đặt ở class:

~~~java
@Service
@CacheConfig(cacheNames = "books")
public class BookQueryService {

    @Cacheable(key = "#p0")
    public Book get(String isbn) {
        // ...
    }
}
~~~

Đây là snippet, file đầy đủ bên dưới. Method-level `cacheNames` có thể ghi đè class-level khi dùng cache region khác. Class-level `@CacheConfig` chỉ chia sẻ cấu hình (cacheNames, keyGenerator, cacheManager, cacheResolver), **không tự tạo caching operation** cho method chưa có `@Cacheable`/`@CachePut`/`@CacheEvict`.

### 10.2 @Caching cho nhiều operations

Một command có thể cần invalidate hai regions:

~~~java
@Caching(evict = {
    @CacheEvict(cacheNames = "books", allEntries = true),
    @CacheEvict(cacheNames = "conditionalBooks", allEntries = true)
})
public void invalidateBoth() {
}
~~~

Test phải kiểm **cả hai** regions đều trống. Nếu chỉ kiểm `books`, sai cache name ở `conditionalBooks` có thể không bị phát hiện.

### 10.3 Nhiều CacheManagers

Nếu project vừa dùng Caffeine local vừa dùng Redis distributed, cần chọn rõ `cacheManager` hoặc `cacheResolver` cho operation, ví dụ `@CacheConfig(cacheManager="catalogCacheManager")`. Không chỉ dùng đúng cache name; test phải đọc đúng provider/manager. Bài dùng **một CacheManager** để tránh ambiguity.

## 11. Chiến lược test: result + count + cache state + proxy

Bốn assertion groups là nền tảng:

| Nhóm | Ví dụ | Phát hiện được |
| --- | --- | --- |
| Business result | `assertEquals(new Book(...), queries.get("A"))` | Giá trị cache trả có đúng không |
| Backend execution count | `catalog.reads()==1` sau hai gets | Cache hit có thật sự skip load không |
| Cache entry state | `cache.get("A", Book.class)` | Key đúng và put/evict đúng |
| Proxy verification | `AopUtils.isAopProxy(queries)` | Test gọi bean qua Spring advice boundary |

**Không chỉ dùng Mockito verify trên facade**: khi cache hit, invocation đi vào **proxy** vẫn xảy ra, nhưng invocation tới **target method/repository** bị skip. Nếu verify sai layer, bạn có thể tưởng có hai cache misses vì proxy được gọi hai lần.

Cách chính xác là đếm số lần target collaborator (catalog/repository/remote client) thực sự được gọi, đồng thời xem cache state.

### 11.1 Why not use a pure unit test for cache annotations?

~~~java
BookQueryService raw = new BookQueryService(catalog);
raw.get("A");
raw.get("A");
~~~

Không có Spring proxy nên cả hai lần gọi đều vào catalog. Test raw object có giá trị để kiểm *business method body*, nhưng không chứng minh @Cacheable hoạt động. Bài runnable có negative demonstration này để thấy khác biệt.

## 12. Bộ ví dụ độc lập Java 17+ / Spring Boot 3.5.x

Bài dùng một mini-project có source of truth giả lập in-memory và cache thật `ConcurrentMapCacheManager`; **không** kết nối external Redis/DB và không cần Docker.

~~~text
spring-cache-proxy-demo/
  settings.gradle
  build.gradle
  src/main/java/example/cache/
    CacheDemoApplication.java
    CachingConfiguration.java
    Book.java
    BookCatalog.java
    BookQueryService.java
    BookCommandService.java
  src/test/java/example/cache/
    BookCacheProxyTest.java
~~~

Bộ kiểm thử có **15 phương thức JUnit Jupiter**. Mỗi test reset catalog và clear hai caches tại `@BeforeEach`. Đây là một integration/component test của Spring Cache proxy, không phải performance benchmark.

### 12.1 settings.gradle

~~~groovy
rootProject.name = 'spring-cache-proxy-demo'
~~~

### 12.2 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các phiên bản được pin để minh họa, không khẳng định đó là phiên bản mới nhất. Khi chạy project cần Gradle wrapper hoặc Gradle phù hợp. `spring-boot-starter-cache` cung cấp Spring cache infrastructure; `starter-test` có JUnit Jupiter và AssertJ/Mockito. Code test dưới đây dùng JUnit assertions trực tiếp và không cần Mockito.

**Không cần thêm Caffeine/Redis dependency**: provider in-memory được khởi tạo chủ động trong `CachingConfiguration`.

## 13. CacheDemoApplication.java

~~~java
package example.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }
}
~~~

Main application chỉ chứa `@SpringBootApplication`. Caching được bật trong config riêng để rõ ranh giới với test slices.

## 14. CachingConfiguration.java

~~~java
package example.cache;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching(proxyTargetClass = true)
public class CachingConfiguration {

    @Bean
    CacheManager cacheManager() {
        ConcurrentMapCacheManager manager =
                new ConcurrentMapCacheManager(
                        "books", "conditionalBooks");

        manager.setAllowNullValues(false);
        return manager;
    }
}
~~~

Hai regions có tên đúng:

- `books`: read/write/invalidate thông thường.
- `conditionalBooks`: kiểm `condition`/`unless` và multi-cache invalidation.

`setAllowNullValues(false)` làm demo không âm thầm lưu null; `BookCatalog.load` trả Book hoặc throw, không trả null. ConcurrentMapCacheManager **không có TTL/max-size eviction mặc định**, nên trong bài phải clear cache thủ công giữa tests; nó không phải lựa chọn tương đương Redis/Caffeine production.

`proxyTargetClass=true` chủ động chọn class-based proxy để test inject concrete services. Không đánh dấu `BookQueryService`/`BookCommandService` là `final` trong project: class-based proxy cần khả năng tạo subclass.

## 15. Book.java: domain record bất biến

~~~java
package example.cache;

import java.util.Objects;

public record Book(String isbn, String title) {
    public Book {
        Objects.requireNonNull(isbn, "isbn");
        Objects.requireNonNull(title, "title");
    }
}
~~~

Record phù hợp với cache demo vì dữ liệu bất biến. Khi title thay đổi, catalog tạo **Book record mới**. Nếu cache giữ một entity mutable, test có thể cho kết quả sai do mutation của object đã được cache mà không cần @CachePut/@CacheEvict; tránh dùng mutable shared objects để chứng minh invalidation.

## 16. BookCatalog.java: source of truth và bộ đếm thực thi

~~~java
package example.cache;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Repository;

@Repository
public class BookCatalog {

    private final Map<String, Book> data =
            new ConcurrentHashMap<>();

    private final AtomicInteger reads = new AtomicInteger();
    private final AtomicInteger writes = new AtomicInteger();
    private final AtomicInteger deletes = new AtomicInteger();

    public Book load(String isbn) {
        reads.incrementAndGet();

        Book value = data.get(isbn);
        if (value == null) {
            throw new NoSuchElementException(
                    "Book not found: " + isbn);
        }
        return value;
    }

    public Book store(Book book) {
        writes.incrementAndGet();
        data.put(book.isbn(), book);
        return book;
    }

    public void delete(String isbn) {
        deletes.incrementAndGet();
        data.remove(isbn);
    }

    // Fixture setup: cố ý đi thẳng tới source-of-truth,
    // không tính là business write của service.
    public void seed(Book book) {
        data.put(book.isbn(), book);
    }

    public void reset() {
        data.clear();
        reads.set(0);
        writes.set(0);
        deletes.set(0);
    }

    public int reads() {
        return reads.get();
    }

    public int writes() {
        return writes.get();
    }

    public int deletes() {
        return deletes.get();
    }
}
~~~

`BookCatalog` không có cache annotations; đây là nơi ghi nhận **target collaborator calls**. Nó cho phép test phát hiện cache hit bằng `reads()` thay vì ước đoán theo thời gian chạy. `ConcurrentHashMap` an toàn cho truy cập cơ bản từ nhiều threads, nhưng reset chung không phù hợp chạy song song những tests cùng dùng singleton context.

Trong ứng dụng thực, `BookCatalog` có thể là JPA repository/HTTP gateway. Bài giữ nó in-memory để tập trung vào Spring proxy semantics.

## 17. BookQueryService.java: @Cacheable và self-invocation

~~~java
package example.cache;

import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
@CacheConfig(cacheNames = "books")
public class BookQueryService {

    private final BookCatalog catalog;

    public BookQueryService(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @Cacheable(key = "#p0")
    public Book get(String isbn) {
        return catalog.load(isbn);
    }

    @Cacheable(
        cacheNames = "conditionalBooks",
        key = "#p0",
        condition = "#p0.startsWith('C-')",
        unless = "#result.title().startsWith('Skip')")
    public Book getConditional(String isbn) {
        return catalog.load(isbn);
    }

    public String getTwiceInsideSameBean(String isbn) {
        // Self-invocation: lời gọi this.get không qua proxy.
        Book first = this.get(isbn);
        Book second = this.get(isbn);
        return first.title() + "|" + second.title();
    }
}
~~~

Giải thích:

- `@CacheConfig(cacheNames="books")` làm `get` mặc định dùng region books.
- `key="#p0"` đảm bảo key là ISBN.
- `getConditional` ghi đè cacheNames sang `conditionalBooks`; condition chỉ cho keys prefix `C-`, unless loại result có title bắt đầu `Skip`.
- `getTwiceInsideSameBean` cố tình **không** cache được hai internal calls; đây là negative demonstration cho proxy. Không nên dùng implementation này ở production khi kỳ vọng cache hits giữa các internal calls.

### 17.1 Tại sao @Cacheable trên public method?

Spring proxy-based caching chuẩn áp dụng tốt nhất cho public methods gọi từ bên ngoài bean. Private/final methods và self-invocation không phải điểm interception đáng tin trong proxy mode; nếu cần khác, phải chọn thiết kế khác như AspectJ weaving và test đúng cấu hình.

## 18. BookCommandService.java: @CachePut, @CacheEvict và @Caching

~~~java
package example.cache;

import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Caching;
import org.springframework.stereotype.Service;

@Service
@CacheConfig(cacheNames = "books")
public class BookCommandService {

    private final BookCatalog catalog;

    public BookCommandService(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @CachePut(key = "#result.isbn()")
    public Book save(Book book) {
        return catalog.store(book);
    }

    @CacheEvict(key = "#p0")
    public void remove(String isbn) {
        catalog.delete(isbn);
    }

    // Invalidate only; intentionally leaves catalog intact.
    @CacheEvict(key = "#p0")
    public void invalidate(String isbn) {
    }

    @CacheEvict(allEntries = true)
    public void invalidateAll() {
    }

    @CacheEvict(key = "#p0")
    public void failAfter(String isbn) {
        throw new IllegalStateException("after failure");
    }

    @CacheEvict(key = "#p0", beforeInvocation = true)
    public void failBefore(String isbn) {
        throw new IllegalStateException("before failure");
    }

    @Caching(evict = {
        @CacheEvict(cacheNames = "books", allEntries = true),
        @CacheEvict(
            cacheNames = "conditionalBooks",
            allEntries = true)
    })
    public void invalidateBoth() {
    }
}
~~~

Tất cả methods là `public` và class không final, nên Spring class-based caching proxy có thể advise. `@CacheConfig` chia sẻ region books. `@CachePut` lấy key từ result của `save`, không từ toàn bộ Book input; do đó nó trùng với key của `get(String)`.

### 18.1 Ý nghĩa các lệnh

- `save`: business store luôn chạy, cache entry sau đó được cập nhật.
- `remove`: xóa source data và evict cùng ISBN.
- `invalidate`: chỉ xóa cache, không đụng source data.
- `invalidateAll`: xóa mọi entry trong region books, không xóa conditionalBooks.
- `failAfter`: exception làm default post-invocation eviction không chạy.
- `failBefore`: evict trước method, ngay cả khi method ném exception.
- `invalidateBoth`: xóa hai regions để minh họa `@Caching`.

**Chú ý:** `@CachePut`/`@CacheEvict` có thể được thực thi qua AOP quanh methods `@Transactional`. Timing đối với database commit không tự được bảo đảm chỉ bằng annotation; phần về transaction consistency bên dưới phân tích rủi ro.

## 19. BookCacheProxyTest.java: kiểm tra 15 tình huống

File `src/test/java/example/cache/BookCacheProxyTest.java`:

~~~java
package example.cache;

import java.util.NoSuchElementException;
import java.util.Objects;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class BookCacheProxyTest {

    @Autowired BookQueryService queries;
    @Autowired BookCommandService commands;
    @Autowired BookCatalog catalog;
    @Autowired CacheManager manager;

    private Cache cache(String name) {
        return Objects.requireNonNull(
                manager.getCache(name),
                "Missing cache: " + name);
    }

    @BeforeEach
    void resetCacheAndCatalog() {
        // Cùng ApplicationContext có thể dùng lại giữa tests.
        cache("books").clear();
        cache("conditionalBooks").clear();

        catalog.reset();
        catalog.seed(new Book("A", "Alpha"));
        catalog.seed(new Book("B", "Beta"));
        catalog.seed(new Book("C-OK", "Cache me"));
        catalog.seed(new Book("C-SKIP", "Skip this"));
    }

    @Test
    void springServicesAreActuallyProxied() {
        assertTrue(AopUtils.isAopProxy(queries));
        assertTrue(AopUtils.isAopProxy(commands));
    }

    @Test
    void cacheableHitSkipsSecondCatalogLoad() {
        assertEquals(new Book("A", "Alpha"), queries.get("A"));
        assertEquals(new Book("A", "Alpha"), queries.get("A"));

        assertEquals(1, catalog.reads());
        assertEquals(new Book("A", "Alpha"),
                cache("books").get("A", Book.class));
    }

    @Test
    void distinctKeysHaveIndependentEntries() {
        queries.get("A");
        queries.get("B");
        queries.get("A");
        queries.get("B");

        assertEquals(2, catalog.reads());
        assertNotNull(cache("books").get("A"));
        assertNotNull(cache("books").get("B"));
    }

    @Test
    void cachePutAlwaysExecutesAndReplacesCachedValue() {
        assertEquals(new Book("A", "Alpha"), queries.get("A"));
        assertEquals(1, catalog.reads());

        assertEquals(new Book("A", "Updated 1"),
                commands.save(new Book("A", "Updated 1")));
        assertEquals(1, catalog.writes());

        assertEquals(new Book("A", "Updated 1"),
                queries.get("A"));
        assertEquals(1, catalog.reads());

        commands.save(new Book("A", "Updated 2"));
        assertEquals(2, catalog.writes());
        assertEquals(new Book("A", "Updated 2"),
                cache("books").get("A", Book.class));
        assertEquals(new Book("A", "Updated 2"),
                queries.get("A"));
        assertEquals(1, catalog.reads());
    }

    @Test
    void evictOneKeyForcesReloadButKeepsOtherKey() {
        queries.get("A");
        queries.get("B");
        assertEquals(2, catalog.reads());

        // External change bypasses cache deliberately.
        catalog.seed(new Book("A", "Alpha changed"));
        assertEquals(new Book("A", "Alpha"), queries.get("A"));
        assertEquals(2, catalog.reads());

        commands.invalidate("A");
        assertNull(cache("books").get("A"));
        assertNotNull(cache("books").get("B"));

        assertEquals(new Book("A", "Alpha changed"),
                queries.get("A"));
        assertEquals(3, catalog.reads());

        queries.get("B");
        assertEquals(3, catalog.reads());
    }

    @Test
    void removeEvictsEntryAndNextLoadSeesMissingSource() {
        queries.get("A");
        assertEquals(1, catalog.reads());

        commands.remove("A");
        assertEquals(1, catalog.deletes());
        assertNull(cache("books").get("A"));

        assertThrows(NoSuchElementException.class,
                () -> queries.get("A"));
        assertEquals(2, catalog.reads());
        assertNull(cache("books").get("A"));
    }

    @Test
    void afterInvocationEvictDoesNotRunOnException() {
        queries.get("A");
        catalog.seed(new Book("A", "New source value"));

        assertThrows(IllegalStateException.class,
                () -> commands.failAfter("A"));

        assertEquals(new Book("A", "Alpha"),
                cache("books").get("A", Book.class));
        assertEquals(new Book("A", "Alpha"), queries.get("A"));
        assertEquals(1, catalog.reads());
    }

    @Test
    void beforeInvocationEvictRunsEvenOnException() {
        queries.get("A");
        catalog.seed(new Book("A", "After failure"));

        assertThrows(IllegalStateException.class,
                () -> commands.failBefore("A"));

        assertNull(cache("books").get("A"));
        assertEquals(new Book("A", "After failure"),
                queries.get("A"));
        assertEquals(2, catalog.reads());
    }

    @Test
    void allEntriesClearsOnlyItsOwnCacheRegion() {
        queries.get("A");
        queries.get("B");
        queries.getConditional("C-OK");
        assertEquals(3, catalog.reads());

        commands.invalidateAll();

        assertNull(cache("books").get("A"));
        assertNull(cache("books").get("B"));
        assertNotNull(cache("conditionalBooks").get("C-OK"));

        queries.getConditional("C-OK"); // remains cached
        assertEquals(3, catalog.reads());

        queries.get("A");
        queries.get("B");
        assertEquals(5, catalog.reads());
    }

    @Test
    void cachingAnnotationEvictsBothRegions() {
        queries.get("A");
        queries.getConditional("C-OK");
        assertEquals(2, catalog.reads());

        commands.invalidateBoth();

        assertNull(cache("books").get("A"));
        assertNull(cache("conditionalBooks").get("C-OK"));

        queries.get("A");
        queries.getConditional("C-OK");
        assertEquals(4, catalog.reads());
    }

    @Test
    void conditionFalseDisablesCachingForGivenInput() {
        queries.getConditional("A");
        queries.getConditional("A");

        assertEquals(2, catalog.reads());
        assertNull(cache("conditionalBooks").get("A"));
    }

    @Test
    void unlessVetoesCachingOnlyForSpecificResult() {
        queries.getConditional("C-SKIP");
        queries.getConditional("C-SKIP");

        assertEquals(2, catalog.reads());
        assertNull(cache("conditionalBooks").get("C-SKIP"));

        queries.getConditional("C-OK");
        queries.getConditional("C-OK");

        assertEquals(3, catalog.reads());
        assertEquals(new Book("C-OK", "Cache me"),
                cache("conditionalBooks")
                        .get("C-OK", Book.class));
    }

    @Test
    void selfInvocationBypassesCacheAdvice() {
        assertEquals("Alpha|Alpha",
                queries.getTwiceInsideSameBean("A"));

        // this.get(...) trong target được gọi hai lần.
        assertEquals(2, catalog.reads());
        assertNull(cache("books").get("A"));

        // External call qua proxy mới bắt đầu population.
        assertEquals(new Book("A", "Alpha"), queries.get("A"));
        assertEquals(new Book("A", "Alpha"), queries.get("A"));
        assertEquals(3, catalog.reads());
    }

    @Test
    void rawNewInstanceDoesNotActivateCaching() {
        BookQueryService raw = new BookQueryService(catalog);

        raw.get("A");
        raw.get("A");

        assertEquals(2, catalog.reads());
        assertNull(cache("books").get("A"));
    }

    @Test
    void failedLoadsAreNotCachedByDefault() {
        assertThrows(NoSuchElementException.class,
                () -> queries.get("UNKNOWN"));
        assertThrows(NoSuchElementException.class,
                () -> queries.get("UNKNOWN"));

        assertEquals(2, catalog.reads());
        assertNull(cache("books").get("UNKNOWN"));
    }
}
~~~

**15 JUnit Jupiter `@Test` methods**, dùng Spring context và Spring caching proxy thật, không mock `BookQueryService`.

### 19.1 Những điểm được cố ý kiểm bằng hai tín hiệu

- `springServicesAreActuallyProxied`: proxy exists.
- `cacheableHitSkipsSecondCatalogLoad`: result đúng, backend reads=1, cache entry đúng.
- `cachePutAlwaysExecutesAndReplacesCachedValue`: writes tăng sau mỗi `save`, cached value đổi, `get` không tăng reads.
- `evictOneKeyForcesReloadButKeepsOtherKey`: stale cache được refresh sau invalidation, key B không mất.
- `afterInvocationEvictDoesNotRunOnException` và `beforeInvocationEvictRunsEvenOnException`: exception semantics của eviction.
- `selfInvocationBypassesCacheAdvice` và `rawNewInstanceDoesNotActivateCaching`: negative demonstrations cho proxy boundary.
- `conditionFalseDisablesCachingForGivenInput` và `unlessVetoesCachingOnlyForSpecificResult`: điều kiện trước/sau invocation.

### 19.2 Vì sao mỗi test clear cả hai caches?

Spring TestContext có thể cache `ApplicationContext` giữa test methods/classes. Cache entries là **mutable state của singleton cache manager**, không tự rollback cùng JUnit lifecycle. Nếu test A từng cache ISBN "A", test B có thể nhận cache hit ngay từ đầu và `catalog.reads()==0`, tạo flaky behavior hoặc false positives.

`@BeforeEach` gọi `cache.clear()` và `catalog.reset()` để cô lập dữ liệu, giữ chính bean/proxy để kiểm. Không cần `@DirtiesContext` cho mỗi method; nó tạo lại context tốn kém nhưng vẫn không thay việc hiểu ownership của external Redis cache.

**Không chạy song song** những tests cùng share static/application cache region và cùng keys khi `@BeforeEach` đang clear. Nếu bật JUnit parallelism, phải tạo unique namespace/key/test context hoặc cô lập CacheManager.

## 20. Chạy Gradle và kết quả dự kiến

Linux/macOS:

~~~bash
./gradlew test --tests example.cache.BookCacheProxyTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.cache.BookCacheProxyTest
~~~

Toàn suite:

~~~bash
./gradlew clean test
~~~

**Kết quả kỳ vọng theo thiết kế:** Gradle phát hiện **15 phương thức JUnit Jupiter** và chúng PASS trên Java 17+/Spring Boot 3.5.x với source/dependencies như trong bài. Đây là kết quả **dự kiến từ static review**, **không** phải stdout đã quan sát từ một lần build. Báo cáo thật nằm ở `build/reports/tests/test/index.html` sau khi chạy.

Các test không dùng `Thread.sleep`, không phụ thuộc external Redis/DB và không in log giả. Chúng kiểm **số lần gọi collaborator** thay vì tốc độ (cache hit nhanh hơn) vì timing benchmark trong CI thường flaky.

### 20.1 Ma trận kết quả

| Test | Catalog reads/writes/deletes quan trọng | Cache state |
| --- | --- | --- |
| Proxy presence | Không yêu cầu backend call | Hai service beans được proxy |
| Repeated get A | reads=1 | books["A"] có Book Alpha |
| Distinct A/B keys | reads=2 | Hai entries độc lập |
| CachePut save hai lần | writes=2, reads giữ 1 | books["A"] thành Updated 2 |
| Evict một key | reads tăng từ 2 lên 3 | A reload, B vẫn cached |
| Remove | deletes=1, missing load tăng reads | books["A"] bị evict |
| Evict after failure | reads giữ 1 | Entry vẫn còn |
| Evict before failure | reads tăng lên 2 sau reload | Entry đã bị xóa |
| allEntries trên books | reads 3 → 5 | books trống, conditionalBooks còn |
| @Caching evict cả hai | reads 2 → 4 | Hai regions trống |
| condition false | reads=2 | Không lưu entry |
| unless veto | C-SKIP đọc 2 lần; C-OK 1 lần | Chỉ C-OK được lưu |
| self-invocation | reads=2 trước external call | Internal calls không populate |
| new raw instance | reads=2 | Không populate |
| load exception | reads=2 | Không cache exception |

### 20.2 Khi test fail

Kiểm theo thứ tự:

1. `@EnableCaching` có thực sự được load không?
2. `@Autowired BookQueryService` là Spring proxy hay raw target?
3. `@CacheConfig`/`cacheNames` có đúng region, `CacheManager` có đúng bean không?
4. `#p0` có trỏ đúng ISBN input, `#result.isbn()` có trỏ đúng return Book?
5. `@BeforeEach` đã clear **cả hai caches** chưa?
6. Có test chạy song song/cùng context với fixture keys giống nhau không?
7. Có `spring.cache.type=none`/NoOpCacheManager đè lên provider thật không?
8. Có self-invocation hoặc method private/final không được advised không?
9. Có data mutation ngoài cache khiến result stale mà thiếu eviction không?
10. Có transaction/async behavior khiến update/eviction xảy ra trước/ngoài commit không?

## 21. So sánh @SpringBootTest với @WebMvcTest và unit tests

### 21.1 @SpringBootTest

Bài dùng `@SpringBootTest` để nạp:

- `CachingConfiguration` với `@EnableCaching`.
- CacheManager thật.
- BookCatalog, BookQueryService, BookCommandService.
- Spring cache advisor và proxy.

Đây là cách trực tiếp để chứng minh annotation semantics trong context tương tự application.

### 21.2 @WebMvcTest

`@WebMvcTest` là MVC slice, chủ yếu tập trung controller/filter/serialization. Nó không mặc định nạp toàn bộ service/cache config. Nếu mock cached service với Mockito, test có thể PASS nhưng **không kiểm caching proxy**.

Khi mục tiêu là cache integration, phải import components/cache configuration cần thiết, hoặc dùng `@SpringBootTest` như ví dụ. Đừng suy từ một `@WebMvcTest` với mocked service rằng `@CachePut`/`@CacheEvict` trong production chạy đúng.

### 21.3 Pure unit tests

~~~java
BookQueryService service = new BookQueryService(fakeCatalog);
service.get("A");
service.get("A");
~~~

Test này kiểm logic target method, không kiểm AOP. Vẫn hữu ích cho branching/error handling, nhưng phải có ít nhất một Spring proxy integration suite khi caching là contract quan trọng.

### 21.4 Mockito spy: cần verify đúng tầng

Nếu dùng `@MockitoSpyBean` trên một bean trong Spring Boot 3.4+/Framework 6.2, phải phân biệt spy target method với wrapper/proxy interaction. Có thể dùng spy cho collaborator khi mong skip target work, nhưng đừng lấy `verify(proxy).get("A")` làm chứng cứ cache miss count: proxy vẫn nhận hai external calls. Một catalog có counter thật, như bài, dễ giải thích hơn và tránh nhầm spy target/proxy.

## 22. Khi cache provider là Redis/Caffeine thay vì ConcurrentMap

Bộ test in-memory xác minh **Spring caching advice**, không xác minh đầy đủ production provider.

### 22.1 Caffeine

Caffeine có size eviction, TTL/expire-after-access, stats và concurrency semantics riêng. Nếu business phụ thuộc TTL, dùng `CaffeineCacheManager` với cấu hình thật, Clock/Ticker có thể điều khiển để tránh ngủ. Test phải chứng minh:

- Trước TTL: cache hit.
- Sau TTL: loader chạy lại.
- Max size: entry cũ có thể bị evict.
- Tính đúng khi concurrent miss.

Simple ConcurrentMap cache trong ví dụ không tự expire, nên **không thể** thay thế TTL test.

### 22.2 Redis

Redis là distributed store, có serialization, key prefixes, TTL, network failures và nhiều application instances. Test nên chạy Redis thực qua Testcontainers hoặc môi trường integration cô lập, dùng namespace/prefix riêng theo suite. Cần kiểm:

- Cache key prefix có phân vùng region/tenant hợp lệ.
- Serializer giữ đúng data type/version.
- TTL và invalidation hiển thị qua các JVM instances.
- Redis unavailable: application fallback/error policy đúng.
- Evict allEntries có scope/chi phí hợp lý, tránh xóa dữ liệu test khác.

Đừng dùng `FLUSHALL` trên Redis server dùng chung hoặc production; cleanup theo prefix/DB riêng và môi trường ephemeral.

### 22.3 CacheManager nào được auto-configure?

Boot kiểm dependency và bean availability trước khi chọn provider. Nếu dự án vô tình thêm Redis/Caffeine dependencies, CacheManager được chọn có thể thay đổi. Việc bài dùng explicit CacheManager bean giúp test predictable; production nên có configuration/test riêng cho provider thực sự deploy.

## 23. Cache và transaction: rủi ro stale data khó thấy

Một method:

~~~java
@Transactional
@CachePut(cacheNames = "books", key = "#result.isbn()")
public Book save(Book book) {
    return repository.save(book);
}
~~~

Đây là đoạn mô phỏng. Cache update và DB commit có thể không xảy ra **atomically** chỉ vì bạn đặt hai annotations. Tùy thứ tự AOP advices và CacheManager, cache có thể nhận giá trị trước khi transaction DB commit, hoặc DB transaction rollback sau cache operation làm cache chứa dữ liệu **chưa commit**.

### 23.1 Vì sao test @Transactional dễ PASS giả?

Một test `@SpringBootTest @Transactional` thường rollback database state trong test thread, nhưng cache entry là state **ngoài DB transaction**. Nếu `@CachePut` cập nhật cache trong test, cuối test DB rollback mà cache entry vẫn còn. Test sau có thể đọc dữ liệu đã rollback từ cache.

Các cách xử lý phụ thuộc kiến trúc:

- Dùng transaction-aware cache decorator/manager khi phù hợp, trì hoãn cache puts/evicts tới after commit.
- Thực hiện invalidation trong `@TransactionalEventListener(phase=AFTER_COMMIT)` khi business yêu cầu chỉ invalidate sau commit.
- Với outbox/eventual consistency, xác minh event delivery và cache invalidation sau commit thực.
- Tạo integration tests có **commit thật**, test rollback và cache readback trên connection/transaction độc lập.
- Tránh tin rằng `@Rollback` dọn CacheManager; nó không tự clear Redis/Caffeine/ConcurrentMap entries.

**Không phải cứ bật transaction-aware caching là có distributed atomicity** giữa DB và Redis. Vẫn cần xử lý crash windows, retry và event semantics nếu nhất quán cao quan trọng.

### 23.2 Concurrency/cross-node invalidation

Một instance update DB và evict local cache không tự evict cache của instance khác. Với replicated applications, dùng distributed cache/pub-sub/invalidation strategy hoặc TTL có ràng buộc business. Bài proxy test trên một context không đủ chứng minh cross-node consistency.

## 24. Cache key bảo mật và dữ liệu nhạy cảm

Với `@Cacheable` ở service trả data theo user/tenant:

- Key phải gồm tất cả parameters xác định kết quả, ví dụ tenantId, locale, permissions version khi cần.
- TenantId phải đến từ **identity đã xác thực**, không chỉ query param không tin cậy.
- Nếu kết quả phụ thuộc role/authority nhưng key chỉ gồm resource ID, có thể lộ dữ liệu giữa users.
- Không lưu tokens, passwords, secrets hoặc PII không cần thiết vào key/value/logs.
- Cache content có thể cần encryption, TTL và invalidation khi thay quyền.
- Khi quyền bị thu hồi, phải kiểm cache có phục vụ data cũ vượt policy hay không.

Một test cross-tenant tốt dùng hai principals với tenant A/B, cùng ISBN, và assert hai cache keys/data scopes tách biệt; nó cần authentication/authorization setup đúng ngoài phần cơ bản của bài.

## 25. @Cacheable(sync=true), thundering herd và timing tests

Khi nhiều threads cùng cache miss, default caching có thể khiến nhiều loaders chạy song song trước khi có entry. `@Cacheable(sync=true)` được Spring hỗ trợ để yêu cầu phối hợp loading trong những cache providers có khả năng thực hiện.

**Những điều cần kiểm trước khi áp dụng:**

1. Provider có hỗ trợ synchronized loading semantics không?
2. Operation có một cache name và không dùng unsupported `unless`/multi-cache setup không?
3. Có nhiều JVM instances không? Một lock local không đủ ngăn thundering herd toàn cluster.
4. Loader có timeout và failure handling không?
5. Test concurrency có dùng `CountDownLatch`/`CyclicBarrier`, không dùng `Thread.sleep` để đồng bộ?
6. Có kiểm backend call count theo key đúng không?

Một test mẫu có thể tạo hai concurrent requests cùng key, kiểm loader chỉ chạy một lần khi `sync=true` và provider cho phép. Cần đảm bảo executor được shutdown/awaitTermination trong `finally` và không share cache instance với tests parallel khác. Đây là **hướng dẫn advanced test**, không nằm trong 15 methods của demo.

**Không benchmark cache hit bằng so sánh nanoseconds của hai lời gọi trong CI**. Số lần backend load và cache state mới là tiêu chí xác định behavior; benchmark throughput/latency cần môi trường đo khác.

## 26. Những lỗi phổ biến khi kiểm thử caching proxy

**1. Gọi `new BookQueryService(...)` và mong cache hoạt động.**  
Raw object không có Spring proxy. Dùng @Autowired bean và AopUtils assert.

**2. Method gọi `this.get()` trong cùng bean.**  
Self-invocation bypass proxy; refactor sang cached bean khác.

**3. Chỉ assert hai kết quả bằng nhau.**  
Repository có thể load hai lần và vẫn bằng nhau. Assert reads count.

**4. Chỉ assert bean là proxy.**  
Proxy có thể vì advice khác; kiểm behavior + cache store.

**5. Test đặt `spring.cache.type=none`.**  
No-op provider làm annotation không có hiệu quả cache thật; phù hợp test không kiểm cache.

**6. Quên @EnableCaching.**  
Annotations nằm trên source nhưng không được advised.

**7. @CachePut dùng key khác @Cacheable.**  
Cache chứa stale entry theo key cũ; test read-after-write phải phát hiện.

**8. Mong @CachePut skip method khi key đã tồn tại.**  
Sai: @CachePut luôn chạy.

**9. @CacheEvict được coi là xóa record DB.**  
Nó chỉ xóa cache; source-of-truth cần mutation riêng.

**10. Giả định @CacheEvict luôn chạy khi method ném exception.**  
Mặc định beforeInvocation=false, chỉ evict sau success.

**11. Dùng beforeInvocation=true mà không hiểu rollback.**  
Evict có thể xảy ra dù command thất bại/DB rollback.

**12. Khai báo key cùng allEntries=true.**  
Không có ý nghĩa hoặc không hợp lệ; allEntries là toàn region.

**13. Clear sai cache name.**  
Nếu query dùng "books" nhưng command evict "book", stale entry vẫn còn.

**14. Không clear cache giữa test methods.**  
Spring context cache reuse khiến test order-dependent.

**15. Dùng @DirtiesContext để che shared cache pollution.**  
Tốn startup; clear cache/namespace theo ownership phù hợp.

**16. Bật JUnit parallel trên shared CacheManager cùng keys.**  
Test A clear khi B đang assert; dùng unique keys/contexts hoặc disable parallel.

**17. Không kiểm condition false/unless true.**  
Một annotation viết nhầm SpEL có thể cache dữ liệu không được phép.

**18. Dùng mutable entity được cache rồi mutate object trực tiếp.**  
Test có thể “thấy dữ liệu mới” dù không có put/evict.

**19. Cache key không gồm tenant/user scope.**  
Có nguy cơ lộ dữ liệu; test cross-tenant cùng resource ID.

**20. Coi ConcurrentMap là Redis/Caffeine.**  
Không kiểm TTL, serialization, cross-node consistency hoặc network failures.

**21. Test @WebMvcTest mock cached service rồi claim proxy hoạt động.**  
Mock bỏ qua thật Spring cache advisor; cần integration test.

**22. Coi rollback test transaction là rollback cache.**  
Cache bên ngoài DB transaction không tự rollback.

**23. Dùng @Cacheable và @CachePut trên cùng method tùy tiện.**  
Cơ chế skip/vẫn chạy xung đột; tách read/write methods.

**24. @Cacheable trên private/final method trong proxy mode.**  
Có thể không intercept; dùng public non-final proxied bean hoặc thiết kế khác.

**25. Multiple CacheManagers nhưng không chỉ định cacheManager/cacheResolver đúng.**  
Key/entries có thể ở provider khác với nơi test đọc.

**26. Exceptions được convert thành null mà không xem policy.**  
Một số providers cache null/negative response; phải kiểm nếu nghiệp vụ không cho stale-not-found.

**27. Thấy cache hit trong một thread rồi suy ra multi-node cache consistency.**  
Cần distributed provider integration và test invalidation qua instances.

**28. Dùng cache như lớp bảo mật.**  
Cache key/isolation không thay authorization/row-level security.

## 27. Quy trình xây bộ kiểm thử cache trong dự án thật

1. Xác định cached methods và source-of-truth (DB/remote API).
2. Liệt kê cache names, CacheManager/provider, cache key expression và TTL.
3. Kiểm Spring thực sự bật caching và bean được gọi qua proxy.
4. Chọn test layer: unit cho business logic, Spring proxy integration cho annotations, provider integration cho Redis/Caffeine.
5. Cô lập cache keys/cache instance và dữ liệu repository trong `@BeforeEach`.
6. Kiểm `@Cacheable` miss→hit và exact backend load count.
7. Kiểm keys A/B hoặc tenant A/B không đè nhau.
8. Kiểm result type, Optional/null/exception policy rõ.
9. Kiểm `condition` và `unless` bằng positive + negative cases.
10. Kiểm `@CachePut` luôn invoke và cập nhật entry đọc bởi @Cacheable.
11. Kiểm `@CacheEvict` theo key, allEntries, after success, before exception.
12. Kiểm `@Caching` khi một action phải clear nhiều regions.
13. Test self-invocation/raw instance để hiểu proxy boundary; refactor nếu production code kỳ vọng caching nội bộ.
14. Kiểm full context có CacheManager thật, không NoOpCacheManager.
15. Nếu có `@Transactional`, test commit/rollback và cache state sau transaction.
16. Nếu có TTL/serialization/distributed cache, dùng provider thật trong integration tests.
17. Nếu data sensitive, kiểm tenant/permission scopes của cache keys.
18. Tránh performance assertions bằng clock thực ở CI; dùng call counts/controlled time.
19. Chạy suite lặp lại, xác định không có order dependency/parallel race.
20. Ghi chú rõ test nào chứng minh Spring caching advice, test nào chứng minh production provider.

### Checklist cuối

- [ ] @EnableCaching được load ở context kiểm caching.
- [ ] @Autowired bean được kiểm AOP proxy hoặc behavior tương đương.
- [ ] Backend load count chứng minh cache hit skip target method.
- [ ] Cache entries/keys được assert chính xác.
- [ ] @CachePut luôn chạy và cập nhật đúng cache key.
- [ ] @CacheEvict xóa đúng key hoặc allEntries; test exception semantics.
- [ ] @Caching bao phủ mọi cache regions cần invalidate.
- [ ] condition và unless được kiểm từng nhánh.
- [ ] Self-invocation không bị nhầm là external proxy call.
- [ ] Test context cache không làm rò entries giữa methods.
- [ ] NoOp provider không được dùng làm bằng chứng caching.
- [ ] Nếu có DB rollback, cache cleanup/consistency có test riêng.
- [ ] Nếu có Redis/Caffeine, provider behavior được kiểm trên provider tương ứng.
- [ ] Tenant/user key scope không gây cross-tenant leakage.
- [ ] Ví dụ JUnit không dựa vào timing/sleep hoặc network thật.

## 28. Kết luận

**Kiểm thử Spring Cache phải đi qua Spring bean proxy**, vì annotations `@Cacheable`, `@CachePut`, `@CacheEvict` không tự thay đổi hành vi của một object tạo bằng `new`, cũng không tự kích hoạt trên self-invocation trong AOP proxy mode. Một bài test tốt chứng minh đồng thời:

1. **Giá trị**: kết quả nào được trả.
2. **Lời gọi thực**: source-of-truth/repository có được gọi hay bị skip.
3. **Cache state**: entry, key và cache region được put/evict đúng.
4. **Proxy**: caller đi qua bean được Spring advise.

Trong demo, `@Cacheable` giảm số reads, `@CachePut` cập nhật cached Book mà vẫn luôn gọi store, `@CacheEvict` giải quyết invalidation và before/after exception, còn `@Caching` phối hợp nhiều regions. Khi mở rộng sang Redis/Caffeine, database transaction hoặc nhiều tenants, cần test thêm TTL, serialization, commit timing và security isolation thay vì coi bộ test ConcurrentMap là đủ cho production.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Cache Abstraction](https://docs.spring.io/spring-framework/reference/6.2/integration/cache.html): cache/cache-manager/key abstraction và AOP integration.
- [Spring Framework 6.2 — Declarative Cache Annotations](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html): @Cacheable, @CachePut, @CacheEvict, @Caching, @CacheConfig, sync, condition/unless.
- [Spring Framework 6.2 — AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): external proxy calls, self-invocation và alternatives.
- [Spring Framework 6.2 — Cacheable API](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/annotation/Cacheable.html): key, condition, unless, sync và result caching.
- [Spring Framework 6.2 — CachePut API](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/annotation/CachePut.html): always invoke và #result.
- [Spring Framework 6.2 — CacheEvict API](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/annotation/CacheEvict.html): allEntries, beforeInvocation và exception handling.
- [Spring Boot 3.5 — Caching](https://docs.spring.io/spring-boot/3.5/reference/io/caching.html): starter-cache, provider selection, no-op mode và testing.
- [Spring Framework — Transaction-aware Cache Decorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html): cache operation timing sau commit khi phù hợp.
