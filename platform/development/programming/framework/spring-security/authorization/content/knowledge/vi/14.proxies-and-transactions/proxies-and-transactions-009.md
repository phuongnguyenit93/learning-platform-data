# Cache kết quả phương thức và nguy cơ chia sẻ dữ liệu giữa người dùng

## 1. Bài toán: cùng một cache key, hai người dùng

Một service trả về trang tài liệu có dữ liệu phụ thuộc vào người đang đăng nhập:

- `alice` xem tài liệu `#10` và thấy nội dung riêng của mình.
- `bob` gọi cùng phương thức với ID `10`.
- Cả hai đi qua một bộ nhớ đệm chung của ứng dụng.

Nếu phương thức dùng `@Cacheable(cacheNames = "documentViews", key = "#p0")`, cache chỉ nhận **ID tài liệu** làm key. Lần gọi của `alice` lưu kết quả với key `10`; lần gọi của `bob` có thể nhận lại **chính kết quả của `alice` mà không thực thi thân phương thức**, tùy vị trí kiểm tra quyền, cách tạo kết quả và cấu trúc lời gọi. Đây là nguy cơ lộ dữ liệu giữa các principal/tenant, kể cả khi nghiệp vụ truy xuất từ database vốn viết đúng.

Vấn đề không nằm ở chỗ cache tự biết quyền của người gọi; **cache không phải hệ thống phân quyền**. Cache tìm kết quả dựa trên `cacheNames` và key. Nếu key không biểu diễn đầy đủ những yếu tố làm thay đổi kết quả, hoặc authorization không được kiểm tra trên đường lấy cache hit, ranh giới bảo mật có thể bị phá vỡ.

Bài học giúp bạn:

1. Hiểu `@Cacheable`, `@CachePut`, `@CacheEvict`, `@EnableCaching` và vòng đời cache hit/miss.
2. Phân biệt cache key theo **tham số**, **người dùng**, **tenant**, **quyền**, **phiên bản dữ liệu**.
3. Phân tích điểm giao giữa Spring Cache, Spring Method Security và Spring AOP proxy.
4. Thiết kế một **secured facade kiểm tra quyền ở mọi lời gọi** rồi mới dùng cache nội bộ.
5. Viết ví dụ Spring Boot Java 17+ chạy được, kiểm thử quyền đúng/sai, cache hit và invalidation.
6. Nhận biết dữ liệu nào có thể cache chung, dữ liệu nào phải tách theo người dùng hoặc tránh cache.

**Ngữ cảnh:** Spring Security Method Security trên Spring Boot/Spring Framework dùng AOP proxy; cache trong ví dụ là `ConcurrentMapCacheManager` để dễ quan sát. Triển khai Redis/Caffeine, hệ thống nhiều instance và transaction cần các biện pháp bổ sung ở phần sau.

## 2. Spring Cache thực sự làm gì?

Khi bật `@EnableCaching`, Spring đăng ký hạ tầng interception cho những bean có annotation cache. Với một phương thức được gọi **qua Spring proxy**:

```java
@Cacheable(cacheNames = "products")
public Product findProduct(long id) {
    return repository.findById(id).orElseThrow();
}
```

- **Cache miss:** interceptor tính key, truy vấn cache không thấy mục, gọi thân phương thức, lưu kết quả rồi trả cho caller.
- **Cache hit:** interceptor tìm được kết quả theo key, trả kết quả đã cache; **thân phương thức thường không chạy lại**.
- **Bộ cache** không tự kiểm tra `SecurityContextHolder`, chủ sở hữu dữ liệu, role, tenant hay chính sách ACL nếu bạn không thiết kế chúng vào đường gọi/khóa cache.
- `@Cacheable` và `@PreAuthorize` là hai cơ chế advice có thể cùng tồn tại; cách lồng các advisor ảnh hưởng đến điểm kiểm tra trước khi trả dữ liệu.

Các annotation chính:

| Annotation | Tác dụng | Điều cần thận trọng |
| --- | --- | --- |
| `@Cacheable` | Tìm cache trước, cache miss mới gọi thân phương thức | Cache hit có thể bỏ qua các bước tính toán/kiểm tra nằm **bên trong** thân method |
| `@CachePut` | Vẫn gọi phương thức, sau đó cập nhật cache theo kết quả | Cần thống nhất key với phương thức đọc và thời điểm ghi |
| `@CacheEvict` | Xóa một key hoặc toàn bộ cache | Xử lý cache stale sau khi sửa/xóa dữ liệu và khi đổi ACL |
| `@Caching` | Gom nhiều thao tác cache | Không giải quyết phân quyền |
| `@EnableCaching` | Bật annotation cache trên Spring bean | Chỉ thêm thư viện hoặc annotation vào method chưa đủ |

`@Cacheable` không phải HTTP cache và không mặc nhiên tương đương `Cache-Control: private`. Trình duyệt/CDN có một tầng cache khác; một hệ thống có thể cùng lúc có Spring Cache, Hibernate cache, Redis, CDN và HTTP response cache. Mỗi tầng cần key, scope và chính sách riêng.

## 3. Default cache key không tự gồm principal

Nếu không cung cấp `key` hoặc `keyGenerator`, Spring Cache mặc định dựa trên **đối số của phương thức** (qua `SimpleKeyGenerator`):

| Chữ ký method | Giá trị mặc định dùng làm key (ý nghĩa) |
| --- | --- |
| `find()` | `SimpleKey.EMPTY` |
| `find(10L)` | `10L` |
| `find("alice", 10L)` | `SimpleKey("alice", 10L)` |
| `find(10L, "vi")` | `SimpleKey(10L, "vi")` |

Với phương thức `find(long id)` nhưng kết quả lại phụ thuộc `SecurityContextHolder.getContext().getAuthentication().getName()`, **principal không phải một đối số** nên không xuất hiện trong default key.

Ví dụ dễ mắc lỗi:

```java
@Cacheable(cacheNames = "personalDashboard", key = "#p0")
public Dashboard dashboard(long workspaceId) {
    String username = SecurityContextHolder.getContext()
        .getAuthentication().getName();
    return buildDashboard(workspaceId, username);
}
```

Hai người cùng dùng `workspaceId` sẽ có cùng key, mặc dù kết quả phụ thuộc username. Mã trên chỉ là **mảnh minh họa có lỗ hổng**, không dùng trong hệ thống thật. Nếu kết quả chứa dữ liệu cá nhân, việc trả lại cache entry của người khác có thể làm lộ dữ liệu.

`key = "#p0"` là biểu thức SpEL của **Spring Cache**; `#p0` chỉ tham số thứ nhất, dùng được ngay cả khi tên tham số không được giữ trong bytecode. Có thể viết `key = "#workspaceId"` nếu Spring phân giải được tên tham số, ví dụ khi biên dịch với `-parameters`.

## 4. Hai nguy cơ độc lập: chia sẻ kết quả và bỏ qua kiểm tra quyền

### 4.1. Cache chung một kết quả vốn được cá nhân hóa

Giả sử đầu vào chỉ là `reportId`, còn thân method trả report đã loại bỏ/ẩn cột khác nhau cho từng vai trò. Nếu cache kết quả theo `reportId`, user A có thể làm đầy cache bằng một góc nhìn rộng; user B nhận lại góc nhìn ấy. **Ngay cả khi cả hai đều được đọc báo cáo**, B vẫn có thể thấy thông tin không dành cho mình.

Một key an toàn phải bao phủ **những biến ảnh hưởng đến kết quả**: tài liệu, người dùng, tenant, quyền/role hoặc policy version, ngôn ngữ, chế độ che dữ liệu, các lựa chọn hiển thị… tùy nghiệp vụ. Không tự thêm mọi trường một cách máy móc; chỉ thêm những yếu tố thực sự cần để phân biệt output, đồng thời đánh giá chi phí cache.

### 4.2. Cache hit đi tắt vào thân phương thức có kiểm tra quyền

Ví dụ:

```java
@Cacheable(cacheNames = "userViews", key = "#p0")
public String loadForCurrentUser(long id) {
    // Kiểm tra quyền tại đây là quá muộn nếu cache hit không gọi thân method.
    enforceOwner(id);
    return renderForCurrentUser(id);
}
```

Nếu user đầu tiên tạo cache entry rồi user thứ hai gọi cùng key, phần `enforceOwner(id)` trong thân method có thể **không chạy**. Kiểm tra quyền **chỉ ở cache miss** là không đủ.

Nếu gắn cả `@PreAuthorize` và `@Cacheable` trên **cùng một phương thức**, phải xét thứ tự advisor. Mô hình khái niệm:

```text
A) Security advice bọc ngoài cache advice
   request -> @PreAuthorize -> cache hit/miss -> return
   => Quyền vẫn được kiểm tra trước cache hit.

B) Cache advice bọc ngoài security advice
   request -> cache hit ----------------------> return
                    \ cache miss -> @PreAuthorize -> method
   => Hit có thể bỏ qua security advice bên trong.
```

Trong các cấu hình phổ biến của Spring Security 6.x, advisor `@PreAuthorize` mặc định có order `200`, còn advisor cache thường có mặc định ưu tiên thấp (`LOWEST_PRECEDENCE`), nhưng **order có thể bị thay đổi bằng cấu hình, custom advisor hoặc môi trường khác**. Không dùng một giả định chưa kiểm thử về thứ tự làm ranh giới bảo mật duy nhất.

Mô hình dễ kiểm tra hơn là **hai bean riêng**: facade có `@PreAuthorize` và **không cache kết quả của facade**, trong khi bean bên trong chỉ phụ trách cache dữ liệu đã được xác định phạm vi.

## 5. Cấu trúc khuyến nghị: kiểm tra quyền mỗi lần, cache phía sau

```text
HTTP Controller / Job / Service khác
                  |
                  v
       SecuredDocumentService
       (bean/proxy riêng)
       @PreAuthorize trên public method
                  |
      check Authentication + ACL
          |               |
         deny            allow
          |               |
  AccessDeniedException  |
                          v
                   OwnerViewCache
                   (bean/proxy riêng)
                    @Cacheable
                   key = (viewer, id)
                          |
                     hit / miss
                          |
                        return
```

Với mọi request vào `SecuredDocumentService`, authorization được xét trước khi gọi `OwnerViewCache`. Dù cache inner trả hit, việc kiểm tra quyền ở facade **đã diễn ra**. Đồng thời cache key chứa đầy đủ viewer và document ID nên những chuỗi cá nhân hóa không bị trộn.

Có hai chiến lược chính:

**A. Cache dữ liệu dùng chung, phân quyền ở facade.** Nếu dữ liệu nền giống nhau với mọi người và việc cache không nhúng thông tin riêng của viewer, có thể cache theo `(tenantId, documentId, dataVersion)` trong một bean nội bộ. Facade xác thực quyền mỗi lần trước khi lấy cache. Tránh tạo đường gọi ngoài facade có thể truy cập bean này mà không được kiểm tra.

**B. Cache dữ liệu đã cá nhân hóa theo từng người.** Nếu giá trị chứa username, redaction theo quyền hoặc trường khác phụ thuộc viewer, key phải phân biệt viewer/tenant/policy. Cũng cần kiểm tra quyền mỗi lần; **key theo user không tự thay thế authorization**. Khi quyền thay đổi, phải invalidation hoặc versioning phù hợp.

**C. Không cache dữ liệu rất nhạy cảm hoặc biến động nhanh.** Nếu khó bảo đảm thu hồi quyền, TTL, key composition và xóa dữ liệu trên mọi node, cân nhắc bỏ cache tầng này hoặc chỉ cache dữ liệu đã loại bỏ PII.

## 6. Ví dụ chạy được: Java 17+ / Spring Boot 3.5.x

Bài demo dùng Spring Boot **3.5.8** với Gradle, Spring Security và cache trong bộ nhớ. Không có HTTP endpoint hay database. Mục tiêu là quan sát các điều kiện sau:

- `alice` được đọc tài liệu `#1` của mình, lần đọc lặp lại trả cache hit.
- `bob` bị từ chối khi đọc `#1`, **kể cả lúc dữ liệu của `alice` đã nằm trong cache**.
- `bob` đọc tài liệu `#2` của mình; output có tên `bob`.
- Sau khi `alice` sửa `#1`, cache được xóa và lần đọc sau trả nội dung mới.
- Caller đi qua bean Spring; `@PreAuthorize`, `@Cacheable`, `@CacheEvict` có hiệu lực.

Với ứng dụng thật, dùng phiên bản Spring Boot đang được duy trì và cache provider phù hợp môi trường. Demo cố định phiên bản để đường build dễ tái lập; nó không phụ thuộc API cache của phiên bản Spring Framework 7.

### 6.1. Cấu trúc thư mục

```text
secure-cache-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── SecureCacheApplication.java
    │   ├── Document.java
    │   ├── DocumentStore.java
    │   ├── DocumentPolicy.java
    │   ├── OwnerViewCache.java
    │   └── SecuredDocumentService.java
    └── test/java/demo/
        └── SecuredDocumentServiceTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'secure-cache-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-cache` cung cấp hạ tầng caching phù hợp Spring Boot. Ở ví dụ này, ứng dụng còn định nghĩa rõ một `ConcurrentMapCacheManager` trong cấu hình, tránh phụ thuộc vào provider mặc định suy đoán từ classpath.

### 6.2. Domain và kho dữ liệu phía server

**`src/main/java/demo/Document.java`:**

```java
package demo;

public record Document(long id, String owner, String title) {
}
```

**`src/main/java/demo/DocumentStore.java`:**

```java
package demo;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

@Component
public class DocumentStore {

    private final Map<Long, Document> records = new ConcurrentHashMap<>();

    public DocumentStore() {
        records.put(1L, new Document(1L, "alice", "Alpha"));
        records.put(2L, new Document(2L, "bob", "Beta"));
    }

    public Optional<Document> find(long id) {
        return Optional.ofNullable(records.get(id));
    }

    public Document rename(long id, String newTitle) {
        Document updated = records.computeIfPresent(
            id,
            (key, old) -> new Document(old.id(), old.owner(), newTitle)
        );
        if (updated == null) {
            throw new NoSuchElementException("No document: " + id);
        }
        return updated;
    }
}
```

Dữ liệu ownership nằm trong `DocumentStore` của server. Nếu người gọi tự gửi `owner="alice"` trong JSON, backend **không được coi đó là bằng chứng sở hữu**. Trong triển khai thật, repository/ACL phải xác định quyền từ database theo ID và tenant.

### 6.3. Chính sách phân quyền ở một bean riêng

**`src/main/java/demo/DocumentPolicy.java`:**

```java
package demo;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentStore store;

    public DocumentPolicy(DocumentStore store) {
        this.store = store;
    }

    public boolean canRead(Authentication authentication, long id) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }
        return store.find(id)
            .map(doc -> authentication.getName().equals(doc.owner()))
            .orElse(false);
    }

    public boolean canWrite(Authentication authentication, long id) {
        // Demo: quyền write trùng ownership; thực tế có thể tách policy.
        return canRead(authentication, id);
    }
}
```

Cả `canRead` và `canWrite` đều **fail closed** nếu authentication không hợp lệ, tài liệu không tồn tại hoặc chủ sở hữu không khớp. Ứng dụng đa tenant cần thêm điều kiện tenant từ principal **và** dữ liệu server, thay vì tin tenant ID do client gửi.

### 6.4. Bean chỉ làm cache giá trị cá nhân hóa

**`src/main/java/demo/OwnerViewCache.java`:**

```java
package demo;

import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class OwnerViewCache {

    private final DocumentStore store;
    private final AtomicInteger actualLoads = new AtomicInteger();

    public OwnerViewCache(DocumentStore store) {
        this.store = store;
    }

    @Cacheable(cacheNames = "ownerViews")
    public String load(String viewer, long id) {
        actualLoads.incrementAndGet();

        Document doc = store.find(id)
            .orElseThrow(() -> new NoSuchElementException("No document: " + id));

        return "For " + viewer + ": " + doc.title();
    }

    @CacheEvict(cacheNames = "ownerViews", allEntries = true)
    public void clearViews() {
        // Cache interceptor evicts after this method returns.
    }

    public int actualLoads() {
        return actualLoads.get();
    }
}
```

**Tại sao không ghi `key = "#p1"`?** Vì `#p1` chỉ là `id`, khiến `viewer` bị bỏ qua. Trong ví dụ, default `SimpleKeyGenerator` tạo key chứa **cả hai đối số** `viewer` và `id`, nên `(alice, 1)` khác `(bob, 1)`.

`actualLoads` chỉ tăng khi **thân `load` chạy thật**, tức cache miss. Lượt cache hit không làm tăng biến đếm. `clearViews()` xóa **toàn bộ** cache `ownerViews` sau khi method trả về; chiến lược này dễ kiểm chứng nhưng có thể gây mất hiệu năng với cache lớn. Ứng dụng thật cần eviction đúng key hoặc cơ chế version/invalidation có đồng bộ.

Bean cache này là thành phần nội bộ dành cho facade. **Không expose trực tiếp `OwnerViewCache.load` thành controller endpoint**, vì phương thức đó chỉ định dạng/caching, không có annotation phân quyền. Nếu thêm một caller khác, phải đi qua ranh giới authorization phù hợp.

### 6.5. Facade: quyền kiểm tra trên mọi lời gọi

**`src/main/java/demo/SecuredDocumentService.java`:**

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class SecuredDocumentService {

    private final DocumentStore store;
    private final OwnerViewCache cache;

    public SecuredDocumentService(DocumentStore store, OwnerViewCache cache) {
        this.store = store;
        this.cache = cache;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
    public String view(long id) {
        // Đọc viewer từ Authentication đã được xác thực bởi Spring.
        String viewer = SecurityContextHolder.getContext()
            .getAuthentication().getName();

        // Cache advice chạy trong bean khác, sau khi facade đã kiểm tra quyền.
        return cache.load(viewer, id);
    }

    @PreAuthorize("@documentPolicy.canWrite(authentication, #p0)")
    public String rename(long id, String newTitle) {
        Document changed = store.rename(id, newTitle);

        // Gọi qua proxy bean cache riêng, tránh self-invocation.
        cache.clearViews();

        return changed.title();
    }
}
```

`#p0` trong `@PreAuthorize` là tham số đầu tiên của method (`id`), không phụ thuộc compiler giữ tên tham số. `authentication` là biến do Method Security cung cấp. `@PreAuthorize` trên facade **không cache**, nên mỗi lời gọi `view`/`rename` từ caller ngoài bean phải qua authorization advisor trước khi vào thân method.

Trong `view`, username lấy từ `SecurityContextHolder` của Spring, **không phải `viewer` do client tự gửi**. Đường gọi được thiết kế sao cho tên dùng để tạo cache key trùng danh tính đã được kiểm tra.

Trong `rename`, dữ liệu được cập nhật trước rồi cache mới bị xóa; ví dụ không dùng transaction hay external cache. Với database thật, hãy quan tâm đến commit, rollback, concurrency và cluster invalidation ở mục 10.

### 6.6. Khởi động: bật caching và method security

**`src/main/java/demo/SecureCacheApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableCaching
@EnableMethodSecurity
public class SecureCacheApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecureCacheApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("ownerViews");
    }

    @Bean
    @Profile("!test")
    CommandLineRunner demo(
            SecuredDocumentService service,
            OwnerViewCache cache) {
        return args -> {
            try {
                authenticate("alice");
                System.out.println("ALICE_FIRST: " + service.view(1L));
                System.out.println("ALICE_AGAIN: " + service.view(1L));
                System.out.println("LOADS_AFTER_ALICE: " + cache.actualLoads());

                authenticate("bob");
                try {
                    service.view(1L);
                    System.out.println("BOB_OTHER: UNEXPECTED");
                } catch (AccessDeniedException denied) {
                    System.out.println("BOB_OTHER: DENIED");
                }
                System.out.println("LOADS_AFTER_DENIAL: " + cache.actualLoads());
                System.out.println("BOB_OWN: " + service.view(2L));

                authenticate("alice");
                System.out.println("ALICE_UPDATE: "
                    + service.rename(1L, "Alpha revised"));
                System.out.println("ALICE_REFRESHED: " + service.view(1L));
                System.out.println("LOADS_AFTER_EVICTION: " + cache.actualLoads());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void authenticate(String username) {
        var token = new UsernamePasswordAuthenticationToken(
            username,
            "demo-only",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
        SecurityContextHolder.getContext().setAuthentication(token);
    }
}
```

Vì `@Profile("!test")`, đoạn demo khởi động khi chạy ứng dụng bình thường; khi chạy test với profile `test`, `CommandLineRunner` không tự sửa dữ liệu dùng cho test.

Vào thư mục chứa `build.gradle` và chạy:

```bash
./gradlew bootRun
```

Trên Windows PowerShell: `.\gradlew.bat bootRun`. Nếu dự án chưa có Gradle Wrapper, sử dụng Gradle tương thích đã cài sẵn bằng `gradle bootRun`, hoặc tạo Wrapper từ môi trường Gradle đã có.

**Output mong đợi do code demo in ra**, ngoài log Spring Boot:

```text
ALICE_FIRST: For alice: Alpha
ALICE_AGAIN: For alice: Alpha
LOADS_AFTER_ALICE: 1
BOB_OTHER: DENIED
LOADS_AFTER_DENIAL: 1
BOB_OWN: For bob: Beta
ALICE_UPDATE: Alpha revised
ALICE_REFRESHED: For alice: Alpha revised
LOADS_AFTER_EVICTION: 3
```

Giải thích:

1. `alice` đọc `#1` hai lần: lần đầu là miss, lần sau là hit, `actualLoads == 1`.
2. `bob` đọc `#1`: facade kiểm tra quyền và từ chối **trước khi gọi bean cache**, nên số lần load vẫn là `1`.
3. `bob` đọc `#2`: được phép; key `(bob,2)` tạo một cache miss mới, tổng lần load là `2`.
4. `alice` sửa `#1`, facade cho phép rồi gọi `cache.clearViews()` qua proxy để evict.
5. Đọc `#1` lại sau eviction trả `Alpha revised` và tổng lần load thành `3`.

**Quan trọng:** `UsernamePasswordAuthenticationToken` tự dựng chỉ để mô phỏng một `SecurityContext` trong demo. Ứng dụng thật phải dùng flow xác thực đáng tin cậy (session, OAuth2 resource server, …); không nhận username do client cung cấp rồi tạo token đã xác thực.

## 7. Kiểm thử qua Spring context và security proxy

Tạo file **`src/test/java/demo/SecuredDocumentServiceTest.java`**:

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SecuredDocumentServiceTest {

    @Autowired SecuredDocumentService service;
    @Autowired OwnerViewCache cache;

    @Test
    @WithMockUser(username = "alice")
    void sameViewerGetsCacheHit() {
        assertEquals("For alice: Alpha", service.view(1L));
        assertEquals("For alice: Alpha", service.view(1L));
        assertEquals(1, cache.actualLoads());
    }

    @Test
    @WithMockUser(username = "bob")
    void deniedRequestCannotReuseAllicesData() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.view(1L)
        );
        assertEquals(0, cache.actualLoads());
    }

    @Test
    @WithMockUser(username = "alice")
    void renameEvictsOldSnapshot() {
        assertEquals("For alice: Alpha", service.view(1L));
        assertEquals("Alpha revised", service.rename(1L, "Alpha revised"));
        assertEquals("For alice: Alpha revised", service.view(1L));
        assertEquals(2, cache.actualLoads());
    }
}
```

Chạy test:

```bash
./gradlew test
```

`@WithMockUser` được cung cấp bởi `spring-security-test`. `@Autowired` dùng Spring-managed bean/proxy, khác với việc `new SecuredDocumentService(...)` thủ công. `@DirtiesContext` làm mới context sau mỗi test để dữ liệu trong `DocumentStore` và `ConcurrentMapCacheManager` không ảnh hưởng qua lại giữa các test; cách này đơn giản nhưng khá tốn thời gian với test suite lớn.

Có thể bổ sung một test trong **cùng một test method** chuyển identity từ `alice` sang `bob` sau khi `alice` đã đưa kết quả vào cache để trực tiếp kiểm chứng cross-user cache hit vẫn bị chặn. Ví dụ phần `CommandLineRunner` đã thể hiện đúng kịch bản ấy.

### Khi test phản ánh lỗi gì?

- Nếu xóa `@EnableCaching`, lần đọc thứ hai sẽ tăng số lần chạy thân cache method, khiến test cache hit thất bại.
- Nếu xóa `@EnableMethodSecurity` hoặc đi vòng qua facade, `bob` có thể đọc tài liệu không thuộc mình, khiến test từ chối thất bại.
- Nếu xóa eviction sau `rename`, giá trị cũ có thể còn nằm trong cache; test đọc sau sửa sẽ thất bại.
- Nếu dùng cache key chỉ theo `id` mà cho một endpoint khác gọi cache trực tiếp, nội dung đã được cá nhân hóa có nguy cơ trả nhầm viewer.

**Không nên dựng test chỉ bằng mock cả `SecuredDocumentService`**, vì lúc đó bạn đang test mock, không kiểm chứng advisor Spring Security hoặc cache interception.

## 8. Khi nào cache chung vẫn hợp lệ?

Cache chung một document snapshot **có thể an toàn** nếu snapshot là giá trị không cá nhân hóa và luôn có authorization trên đường vào:

```java
// Pseudocode kiến trúc, không phải file Java độc lập.
@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
public DocumentView read(long id) {
    return sharedSnapshotCache.load(currentTenantId(), id);
}
```

Trong `sharedSnapshotCache.load(...)`, cache key cần chứa tenant (nếu ID không globally unique) và ID bản ghi. Dữ liệu trong cache có thể là **bản lưu nội bộ** cần thiết cho người được phép truy cập. Điều kiện không thể bỏ qua: caller **không có đường nào lấy dữ liệu cache trực tiếp** nếu chưa được cấp quyền, và dữ liệu sau cache không mang dấu vết riêng của người dùng khác.

Nếu cùng một bản ghi trả nội dung khác nhau theo viewer (ví dụ tài liệu có trường được che tùy quyền), cần tạo view sau bước authorize hoặc dùng key theo **đúng mức quyền/viewer**. Với role, key chỉ `"ADMIN"` hoặc `"USER"` có thể vẫn thiếu nếu ACL cấp quyền riêng theo từng bản ghi. Với tenant, key chỉ `documentId` là nguy hiểm khi ID trùng giữa tenant.

Không lưu access token, refresh token hoặc mật khẩu vào cache key/log để “đại diện user”. Dùng một định danh nội bộ ổn định, không nhạy cảm ở mức chấp nhận được (ví dụ opaque user ID và tenant ID). Cache nội dung nhạy cảm còn cần mã hóa ở tầng lưu trữ, chính sách truy cập Redis, retention và quản lý dữ liệu theo yêu cầu của hệ thống.

## 9. Thiết kế cache key theo các yếu tố quyết định output

Một mô hình key có thể là:

```text
cache-name = documentView
cache-key  = (tenantId, documentId, viewerId, viewPolicyVersion, locale)
```

Đây là **mô hình khái niệm**; không phải yêu cầu bắt buộc key phải chứa đúng năm trường trong mọi ứng dụng.

| Yếu tố | Khi cần đưa vào key | Nếu bỏ sót |
| --- | --- | --- |
| `tenantId` | ID bản ghi chỉ duy nhất trong tenant; dữ liệu tách tenant | Có thể đọc nhầm dữ liệu tenant khác |
| `documentId` | Cache theo từng bản ghi | Trộn tài liệu |
| `viewerId` | Output được cá nhân hóa hoặc quyền theo từng người | Trộn dữ liệu người dùng |
| `scope/role/policyVersion` | Output thay đổi theo quyền hoặc ACL | Trả dữ liệu theo quyền cũ |
| `locale` | Chuỗi/format được dịch theo ngôn ngữ | Trả nội dung sai ngôn ngữ |
| `dataVersion` | Cần giữ nhiều bản chụp nhất quán | Trả snapshot cũ sau update |
| `redactionMode` | Có nhiều mức che trường nhạy cảm | Lộ trường bị che của người khác |

Nếu phương thức chỉ nhận `id` mà key cần `viewerId`, có thể **thêm tham số viewer do server xác thực rồi truyền vào cache bean** như demo. Một `KeyGenerator` hoặc SpEL gọi bean identity cũng khả thi, nhưng dễ ẩn phụ thuộc vào `SecurityContext`; cần kiểm thử khi chạy trong async, job và khi quyền thay đổi. Tránh lấy principal từ HTTP header do client tự gửi như nguồn tin cậy.

Với `@Cacheable`, key expression chạy trong **cache SpEL context**, khác với security expression root. Biểu thức `authentication.name` sử dụng được trong `@PreAuthorize` không có nghĩa mặc nhiên có biến `authentication` tương tự trong `@Cacheable`. Nếu cần, dùng đối số `#p0`, `#p1` rõ ràng hoặc một bean/key generator được cấu hình chủ động.

## 10. Invalidation: thay đổi nội dung và quyền truy cập

### 10.1. Dữ liệu thay đổi

Sau thao tác `update`, `delete`, `publish` hoặc `move`, entry tương ứng có thể stale. Các cách phổ biến:

1. `@CacheEvict(cacheNames="...", key="...")` để xóa đúng key khi biết danh tính.
2. `allEntries = true` để xóa toàn bộ cache khi không biết những viewer có entry; dễ đúng nhưng có chi phí.
3. Versioning key/snapshot (`documentVersion`, `ACLVersion`) để tạo key mới khi dữ liệu hoặc quyền thay đổi.
4. TTL ngắn như **lớp giảm rủi ro**, không thể thay thế sự kiện thu hồi quyền ngay lập tức.

Cẩn trọng `@CacheEvict(beforeInvocation = true)`: eviction trước khi cập nhật có thể làm cache mất dữ liệu dù thao tác ghi sau đó thất bại. Mặc định eviction sau khi method thành công phù hợp nhiều luồng đơn giản, nhưng **không tự bảo đảm sau DB commit** nếu transaction bao trùm một lớp advice khác.

### 10.2. Đổi quyền/ACL

Các thao tác `revoke`, `removeMember`, đổi role, khóa tài khoản, chuyển owner hoặc chuyển tenant phải được đánh giá như **sự kiện invalidation bảo mật**.

- Nếu authorization ở facade được kiểm tra **mỗi lần** bằng nguồn chính sách mới, user đã bị thu hồi quyền sẽ bị chặn trước khi dùng cache. Tuy nhiên thay đổi ACL vẫn có thể làm biến đổi **hình dạng dữ liệu được phép nhìn** của một user còn quyền đọc; cache personalized cần xóa/version.
- Nếu cache **cả kết quả authorization** (`canRead`/`hasPermission`), chính sách này cũng cần key theo principal/tenant/target/action và invalidation ngay khi quyền đổi. Authorization cache quá hạn là nguy cơ lớn.
- Khi người dùng logout, một key theo user không biến thành dữ liệu công khai; nhưng quy tắc hết hạn của cache và thu hồi quyền cần rõ ràng. Không dùng logout như cơ chế xóa cache duy nhất trong hệ thống nhiều thiết bị.

### 10.3. Transaction và race condition

Một ví dụ có thể sai:

```text
DB update bắt đầu
cache entry bị xóa
một request khác cache miss và đọc dữ liệu cũ chưa commit
DB update commit
cache nay giữ lại bản cũ
```

Khi dùng `@Transactional`, `@CacheEvict` và Redis/Caffeine, phải xét thứ tự advisor, isolation, commit/rollback. Các giải pháp tùy hệ thống gồm giao sự kiện invalidation **sau commit**, cache manager transaction-aware, versioned key, hoặc cơ chế đồng bộ/atomic update với DB. Không cam kết `@CacheEvict` luôn chạy sau commit chỉ vì hai annotation nằm trên cùng method.

Spring AOP proxy cũng có giới hạn self-invocation: `this.loadCached(...)` hoặc `this.clearCache()` trong cùng bean có thể bypass advice. Demo gọi `cache.clearViews()` trên **một bean riêng** để đảm bảo được intercept.

## 11. Hệ thống nhiều instance, Redis và tenant

`ConcurrentMapCacheManager` trong demo là cache **theo process**. Hai application instance có hai bộ nhớ cache khác nhau; eviction trên instance A không mặc nhiên xóa entry trên B. Với Redis/CDN/các backend chia sẻ, lại có rủi ro người dùng ở nhiều instance cùng truy xuất namespace không được phân tách.

Checklist cho sản phẩm:

- **Namespace:** tiền tố môi trường, phiên bản schema, service, tenant khi cần; không tái sử dụng cache key giữa các loại dữ liệu khác semantics.
- **Identity:** viewer/tenant từ principal đã được xác thực; nếu service-to-service, xác định identity của service và end-user delegation.
- **TTL:** dựa trên độ nhạy dữ liệu và tốc độ thay đổi quyền; không coi TTL là biện pháp duy nhất bảo vệ revoke.
- **Invalidation fan-out:** bảo đảm update/ACL change truyền tới mọi node hoặc cache backend chung.
- **Serializer:** dùng định dạng/schema có quản lý phiên bản; tránh tự động deserialize class tùy ý từ dữ liệu cache không tin cậy.
- **Observability:** metric hit/miss/eviction/denial theo dạng tổng hợp; tránh log nội dung cache hoặc token; log user/tenant ID có kiểm soát riêng.
- **Capacity:** cache theo từng user làm tăng cardinality; cân bằng hit rate, memory và bảo mật. Nếu quá lớn, cache phần dữ liệu chung rồi dựng phần cá nhân hóa sau khi authorize.
- **Isolation tests:** kiểm thử hai principal, hai tenant có ID trùng, thay đổi role/owner, revoke và truy cập chéo qua các instance.

Khi một user có quyền nhìn bản ghi nhưng chỉ được thấy trường hạn chế, **chỉ kiểm tra `canRead` boolean chưa đủ**. Cần kiểm tra quyền mức trường hoặc tạo DTO/redaction mới sau authorization; output đã che trường phải được key đúng theo permission context.

## 12. Các lỗi phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| B nhìn thấy tên/nội dung riêng của A | `@Cacheable` key chỉ theo ID, trong khi output cá nhân hóa | Thêm viewer/tenant/policy context vào key hoặc cache dữ liệu chung và render theo viewer sau |
| User đã mất quyền vẫn thấy dữ liệu | Authorization chỉ kiểm tra ở cache miss, hoặc cache kết quả cho phép quá lâu | Check quyền ở facade mỗi lần; invalidation/version ACL |
| Cache hit không gọi logic kiểm tra trong method | Kiểm tra nằm trong thân method được cache | Đưa quyền ra ranh giới trước cache, kiểm thử hit với user khác |
| `@PreAuthorize` dường như không chạy | Chưa `@EnableMethodSecurity`, self-invocation, caller dùng `new` | Gọi qua Spring proxy, test deny/allow |
| `@Cacheable` không hoạt động | Chưa `@EnableCaching`, self-invocation hoặc thiếu cache provider | Kiểm tra config, bean, proxy, provider |
| Cache key trả lỗi SpEL | Dùng `authentication` như security expression trong cache context | Truyền identity tin cậy thành tham số hoặc cấu hình bean/key generator |
| `@CacheEvict` không xóa entry đúng | Sai tên cache, key không khớp hoặc gọi nội bộ qua `this` | Dùng key thống nhất, gọi qua proxy, test read-after-write |
| Entry cũ tái xuất hiện sau commit | Race giữa eviction, cache miss và transaction commit | Invalidate sau commit/version key |
| Test pass một user nhưng lộ dữ liệu thật | Thiếu test cross-user/cache-hit hoặc dùng mock thay proxy | Test A làm ấm cache rồi B truy cập, assert cả body và denied |
| Khác biệt giữa application nodes | In-memory cache per-node, eviction không propagate | Dùng distributed cache / sự kiện invalidation |
| Cache quá lớn khi key theo user | Cardinality tăng theo `(user × resource × policy)` | Cache dữ liệu chung sau auth, giảm personalization, TTL hợp lý |
| Dữ liệu lộ qua CDN dù Spring cache đúng | HTTP cache public thiếu `Vary`, `private`/`no-store` | Cấu hình riêng tầng HTTP, không dùng Spring Cache làm bảo đảm HTTP |

Điểm then chốt là **phân tách hai câu hỏi**: *ai được truy cập tài nguyên?* do authorization quyết định; *giá trị đã tính nào có thể tái sử dụng?* do caching quyết định. Hai câu trả lời phải nhất quán cả khi cache hit, khi quyền thay đổi và khi ứng dụng chạy nhiều node.

## 13. Bài tập áp dụng

**Tình huống 1:** Phương thức `getInvoices(long teamId)` đọc user hiện tại từ `SecurityContextHolder` và dùng `@Cacheable(key="#p0")`. Hai user trong team có quyền xem các hóa đơn khác nhau.  
**Hỏi:** lỗi gì?  
**Đáp:** Cache key chỉ `teamId`, trong khi kết quả thay đổi theo viewer/quyền. Cần authorize mỗi lần và key cá nhân hóa theo user/policy, hoặc cache dữ liệu nền rồi lọc quyền ở một lớp bảo vệ không bị bỏ qua.

**Tình huống 2:** `@PreAuthorize` được đặt trên cùng method với `@Cacheable`; developer kết luận luôn an toàn.  
**Hỏi:** cần kiểm tra gì?  
**Đáp:** Kiểu proxy, đường gọi, việc bật cả hai hạ tầng, advisor ordering trong cấu hình chạy thật, cache hit với user khác, và nội dung cache có phân biệt viewer hay không. Nếu cần ranh giới rõ ràng, tách secured facade và cached bean.

**Tình huống 3:** `alice` vừa bị thu hồi quyền đối với tài liệu. Cache key đã có username.  
**Hỏi:** username trong key có đủ?  
**Đáp:** Không. Key theo viewer giúp tránh trộn dữ liệu, nhưng phải kiểm tra quyền hiện tại; các snapshot phụ thuộc ACL/role có thể cần invalidation hoặc versioning.

**Tình huống 4:** Cache một DTO giống nhau cho mọi người, nhưng chỉ user có quyền mới được lấy.  
**Hỏi:** có bắt buộc cache theo từng user?  
**Đáp:** Không nếu DTO thực sự giống nhau cho người được phép và mọi đường lấy DTO đều kiểm tra quyền trước cache. Tuy nhiên phải tách tenant/namespace và xử lý invalidation.

**Tình huống 5:** Một app đang dùng `ConcurrentMapCacheManager` trên ba pod. Cập nhật tài liệu ở pod A đã xóa cache tại A.  
**Hỏi:** pod B có nhất định nhận dữ liệu mới?  
**Đáp:** Không. Cache trong bộ nhớ là riêng mỗi process, nên cần cơ chế invalidation liên pod hoặc cache backend chung.

**Tình huống 6:** Muốn xác nhận dữ liệu không lộ khi cache hit, chỉ cần assertion `AopUtils.isAopProxy(service)`?  
**Đáp:** Không. Proxy tồn tại chưa chứng minh đúng advisor, đúng đường gọi, đúng policy hay đúng key. Cần kiểm thử nhiều principal trên cùng resource, cả hit/miss và sau revoke/update.

## 14. Kiến thức tổng kết và nguồn đọc thêm

- Cache key phải bao phủ những yếu tố **làm khác kết quả**: tenant, resource, viewer, policy/view version… tùy trường hợp.
- Authorization phải được thực thi trên **mọi đường truy cập**, kể cả khi cache có sẵn dữ liệu; kiểm tra chỉ nằm trong thân method có cache là không đủ.
- Trên Spring proxy, thiết kế **facade bảo mật riêng** và bean cache phía sau giúp ranh giới rõ ràng, giảm rủi ro do advisor ordering.
- Cache kết quả đã cá nhân hóa phải phân biệt identity; cache dữ liệu chung vẫn có thể dùng nếu quyền được kiểm tra trước, nội dung không phụ thuộc viewer và không có đường đi vòng.
- Cập nhật dữ liệu và ACL kéo theo chính sách eviction/versioning; với transaction và nhiều instance, cần xem xét sau commit và invalidation phân tán.
- Không đưa token/password vào key, không dùng DTO owner/tenant do client tự khai làm bằng chứng, không coi TTL là bảo đảm revoke.

Tài liệu chính thức:

1. [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): khái niệm cache và phạm vi abstraction.
2. [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, default key, `condition`, `unless`, `@CacheEvict`, proxy/self-invocation.
3. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, interceptor/advisor order.
4. [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): giới hạn Spring AOP proxy và self-invocation.
5. [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser` và kiểm thử lời gọi có method security.

**Ghi nhớ thực hành:** cache làm nhanh việc trả dữ liệu cũ; nó không biết dữ liệu ấy còn được phép hiển thị cho caller hay không. Mỗi cache hit là một đường trả dữ liệu cần được phân quyền đúng và tách biệt giá trị theo đúng ngữ cảnh người dùng.