# Kiểm thử cache giữa tenant và hiệu lực sau khi quyền thay đổi

## 1. Mục tiêu và phạm vi

Trong ứng dụng đa tenant (multi-tenancy), **cache phải giữ dữ liệu của các tenant tách biệt** và **quyền truy cập phải được kiểm tra với trạng thái chính sách phù hợp tại thời điểm đọc**. Cache đúng về hiệu năng nhưng sai về phạm vi dữ liệu hoặc thời điểm áp dụng quyền có thể gây lộ dữ liệu.

Sau bài này, bạn sẽ:

1. Xây dựng tình huống hai tenant có cùng mã tài liệu nhưng dữ liệu khác nhau, rồi kiểm thử không xảy ra **cross-tenant cache leak**.
2. Kiểm thử **cache hit không bỏ qua authorization**: một người dùng không có quyền vẫn bị từ chối dù người dùng khác đã làm nóng cache.
3. Kiểm thử **thu hồi quyền (revoke)** sau khi cache đã được làm nóng: lần đọc tiếp theo phải bị từ chối theo chính sách yêu cầu hiệu lực tức thì.
4. Kiểm thử **cấp quyền (grant)** sau lần đọc bị từ chối: lần đọc mới thành công khi quyền mới có hiệu lực.
5. Kiểm tra tính độc lập giữa các tenant, số lần gọi nguồn dữ liệu và những giới hạn của cache quyền, TTL, eviction và môi trường nhiều instance.

Bài thuộc phần **Kiểm thử dữ liệu và chính sách** trong **Spring Security – authorization**. Ví dụ sử dụng Java 17+, Spring Boot 3.5.7, Spring Security 6.x, Spring Cache và JUnit 5; đây là bài kiểm thử ở **lớp service**, không có HTTP controller hay cơ sở dữ liệu thật.

## 2. Hai lỗi độc lập cần phát hiện

### 2.1. Trộn dữ liệu giữa các tenant

Giả sử **tenant acme** và **tenant beta** đều có tài liệu ID = **same-id**:

| Tenant | Document ID | Nội dung thực tế |
| --- | --- | --- |
| acme | same-id | ACME: private |
| beta | same-id | BETA: private |

Nếu cache key chỉ dựa vào **documentId**, việc tải acme trước có thể khiến một truy vấn hợp lệ của beta nhận nhầm nội dung acme. Dù người gọi **có quyền với beta**, đó vẫn là rò rỉ dữ liệu giữa tenant.

**Cache key đúng phải chứa tenantId và mọi chiều dữ liệu ảnh hưởng đến kết quả.** Trong ví dụ này, hàm cache nhận hai tham số (tenantId, documentId) và để Spring Cache tạo key mặc định **SimpleKey(tenantId, documentId)**. Khi nhiều tham số được truyền vào, key mặc định bao gồm tất cả tham số. Hãy luôn xem lại key nếu cấu hình **key=...** riêng, dùng custom KeyGenerator hoặc đổi chữ ký hàm.

### 2.2. Dùng quyền cũ sau grant/revoke

Một tài liệu có thể được cache hợp lệ vào thời điểm người dùng được cấp quyền. Nếu sau đó quyền bị **thu hồi**, người dùng không được phép dùng cache hit để vượt qua kiểm tra quyền.

Cần phân biệt hai loại cache:

- **Data cache**: cache dữ liệu tài liệu; có thể dùng chung trong cùng tenant nếu mỗi lần trả kết quả đều qua kiểm tra quyền còn hiệu lực.
- **Authorization decision cache**: cache kết quả **allow/deny**. Nếu cache quyết định quyền, phải có chính sách invalidation/phiên bản quyền/TTL được kiểm soát; riêng data cache đúng key không đảm bảo quyền mới được thấy.

Một cấu trúc dễ kiểm chứng là:

~~~text
Caller đã được xác thực
        |
        v
SecureDocumentService.read(tenantId, documentId)
        |
        v
@PreAuthorize kiểm tra quyền hiện hành theo user + tenant + document
        |
        +---- DENY ----> AccessDeniedException; không gọi nguồn dữ liệu
        |
        v
CachedDocuments.get(tenantId, documentId)
        |
        +---- CACHE HIT ----> Trả dữ liệu đúng tenant
        |
        +---- CACHE MISS ---> DocumentRepository.find(tenantId, documentId)
~~~

Đặt kiểm tra @PreAuthorize trên **facade riêng**, bao ngoài bean đọc dữ liệu có @Cacheable. Nhờ vậy mọi đường gọi service công khai đều đi qua kiểm tra quyền trước khi truy cập cache. Không phụ thuộc vào thứ tự các advisor khi gắn method security và cache trên **cùng một phương thức**.

> **Giả định chủ động của bài test:** mọi thay đổi grant/revoke trong kho quyền mẫu có hiệu lực tức thì, không có cache quyết định quyền. Hệ thống thật dùng policy engine, database replication, JWT hoặc message invalidation bất đồng bộ cần kiểm thử theo hợp đồng nhất quán thực tế của nó, không mặc định rằng mọi cập nhật trên mạng có hiệu lực ngay tức thì.

## 3. Ma trận kiểm thử bắt buộc

| Kịch bản | Điều kiện đầu | Thao tác | Kỳ vọng |
| --- | --- | --- | --- |
| Cùng ID, hai tenant | alice được đọc tài liệu ở cả acme và beta | Đọc acme → beta → lặp lại | Nội dung đúng từng tenant; mỗi tenant có đúng một cache miss |
| Cache đã nóng từ user khác | bob được đọc beta; alice không được đọc beta | Bob đọc beta → alice đọc beta | Alice nhận AccessDeniedException, không nhận dữ liệu |
| Revoke sau cache hit | alice có quyền đọc acme | Alice đọc acme → thu hồi quyền → đọc lại | Lần sau bị từ chối; không query nguồn thêm |
| Grant sau DENY | alice chưa có quyền đọc acme | Đọc bị chặn → cấp quyền → đọc lại | Lần mới trả đúng dữ liệu; query nguồn đúng một lần |
| Revoke chỉ một tenant | alice có quyền acme và beta, hai cache entry đã nóng | Thu hồi acme → đọc acme và beta | Acme bị chặn; beta vẫn đọc được; không lẫn cache |

Mỗi phép kiểm thử cần **assert nội dung**, **assert trạng thái được phép/từ chối** và **assert số lần truy vấn nguồn** khi thích hợp. Chỉ assert không có exception là chưa đủ để phát hiện cache lẫn tenant.

## 4. Ví dụ Maven runnable từ đầu đến cuối

Tạo dự án theo cây sau:

~~~text
tenant-cache-authz/
├── pom.xml
├── src/main/java/com/example/cacheauth/
│   ├── CacheSecurityApplication.java
│   ├── ResourceKey.java
│   ├── Document.java
│   ├── DocumentRepository.java
│   ├── Permissions.java
│   ├── CachedDocuments.java
│   └── SecureDocumentService.java
└── src/test/java/com/example/cacheauth/
    └── CacheAuthorizationTest.java
~~~

### 4.1. Dependencies

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>tenant-cache-authz</artifactId>
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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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
~~~

**CacheSecurityApplication.java**: bật method security và cache. Cache trong ví dụ dùng **ConcurrentMapCacheManager** để test chạy không cần Redis hay kết nối mạng.

~~~java
package com.example.cacheauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
@EnableCaching
public class CacheSecurityApplication {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("documents");
    }

    public static void main(String[] args) {
        SpringApplication.run(CacheSecurityApplication.class, args);
    }
}
~~~

**ResourceKey.java**: key dùng trong nguồn dữ liệu và kho quyền giả lập; record Java tự triển khai equals/hashCode theo cả hai trường.

~~~java
package com.example.cacheauth;

record ResourceKey(String tenantId, String documentId) {
}
~~~

**Document.java**:

~~~java
package com.example.cacheauth;

public record Document(String tenantId, String documentId, String body) {
}
~~~

**DocumentRepository.java**: nguồn dữ liệu in-memory tách theo tenant. Bộ đếm **fetchCount** ghi lại số lần thực sự đến repository (cache hit không tăng).

~~~java
package com.example.cacheauth;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {

    private final Map<ResourceKey, Document> data = new ConcurrentHashMap<>();
    private final Map<ResourceKey, AtomicInteger> fetches = new ConcurrentHashMap<>();

    public void put(String tenantId, String documentId, String body) {
        ResourceKey key = new ResourceKey(tenantId, documentId);
        data.put(key, new Document(tenantId, documentId, body));
    }

    public Document find(String tenantId, String documentId) {
        ResourceKey key = new ResourceKey(tenantId, documentId);
        fetches.computeIfAbsent(key, k -> new AtomicInteger()).incrementAndGet();
        return data.get(key);
    }

    public int fetchCount(String tenantId, String documentId) {
        AtomicInteger count = fetches.get(new ResourceKey(tenantId, documentId));
        return count == null ? 0 : count.get();
    }

    public void reset() {
        data.clear();
        fetches.clear();
    }
}
~~~

**Permissions.java**: nguồn chính sách giả lập. Quyền được xác định bằng bộ ba (username, tenantId, documentId). Mọi lời gọi canRead đọc tập quyền **hiện tại**, không cache allow/deny.

~~~java
package com.example.cacheauth;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component("permissions")
public class Permissions {

    private record Grant(String username, String tenantId, String documentId) {
    }

    private final Set<Grant> grants = ConcurrentHashMap.newKeySet();

    public boolean canRead(String username, String tenantId, String documentId) {
        return grants.contains(new Grant(username, tenantId, documentId));
    }

    public void grant(String username, String tenantId, String documentId) {
        grants.add(new Grant(username, tenantId, documentId));
    }

    public void revoke(String username, String tenantId, String documentId) {
        grants.remove(new Grant(username, tenantId, documentId));
    }

    public void reset() {
        grants.clear();
    }
}
~~~

**CachedDocuments.java**: chỉ cache dữ liệu. **Không** dùng key chỉ có documentId.

~~~java
package com.example.cacheauth;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CachedDocuments {

    private final DocumentRepository repository;

    public CachedDocuments(DocumentRepository repository) {
        this.repository = repository;
    }

    // Hai tham số -> cache key mặc định SimpleKey(tenantId, documentId).
    @Cacheable(cacheNames = "documents")
    public Document get(String tenantId, String documentId) {
        return repository.find(tenantId, documentId);
    }
}
~~~

**SecureDocumentService.java**: điểm vào đọc tài liệu có kiểm soát quyền. Biểu thức dùng **#p0** và **#p1**, nên không phụ thuộc vào việc build có giữ tên tham số Java hay không.

~~~java
package com.example.cacheauth;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class SecureDocumentService {

    private final CachedDocuments cachedDocuments;

    public SecureDocumentService(CachedDocuments cachedDocuments) {
        this.cachedDocuments = cachedDocuments;
    }

    @PreAuthorize("@permissions.canRead(authentication.name, #p0, #p1)")
    public Document read(String tenantId, String documentId) {
        return cachedDocuments.get(tenantId, documentId);
    }
}
~~~

Vì **SecureDocumentService** và **CachedDocuments** là hai Spring bean khác nhau, lời gọi từ facade đến bean cache đi qua proxy của @Cacheable. Quyền được kiểm tra trước khi gọi bean cache; việc cache hit không làm bỏ qua interceptor của phương thức read.

Trong ứng dụng thật, tenantId do client gửi phải được đối chiếu với tenant của phiên đăng nhập hoặc tập tenant mà principal được phép truy cập. Hàm canRead ở ví dụ thực hiện điều đó bằng cách yêu cầu **grant chính xác theo cả ba chiều**, không tin cậy tenantId riêng lẻ.

## 5. Bộ test tích hợp với Spring Security và Spring Cache

**CacheAuthorizationTest.java**: test dùng Spring context thật, bean security proxy thật, bean cache thật và in-memory fixtures. **@WithMockUser** đặt người dùng hiện tại. Mỗi test xóa cache và reset kho dữ liệu/quyền để tránh phụ thuộc thứ tự chạy.

~~~java
package com.example.cacheauth;

import java.util.List;
import java.util.Objects;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.CacheManager;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CacheAuthorizationTest {

    @Autowired private SecureDocumentService service;
    @Autowired private DocumentRepository repository;
    @Autowired private Permissions permissions;
    @Autowired private CacheManager cacheManager;

    @BeforeEach
    void arrange() {
        Objects.requireNonNull(cacheManager.getCache("documents")).clear();
        repository.reset();
        permissions.reset();

        repository.put("acme", "same-id", "ACME: private");
        repository.put("beta", "same-id", "BETA: private");
    }

    @Test
    @WithMockUser(username = "alice")
    void sameDocumentIdMustStayIsolatedAcrossTenants() {
        permissions.grant("alice", "acme", "same-id");
        permissions.grant("alice", "beta", "same-id");

        assertEquals("ACME: private",
                service.read("acme", "same-id").body());
        assertEquals("BETA: private",
                service.read("beta", "same-id").body());

        // Lần đọc thứ hai phải là cache hit ở đúng tenant.
        assertEquals("ACME: private",
                service.read("acme", "same-id").body());
        assertEquals("BETA: private",
                service.read("beta", "same-id").body());

        assertEquals(1, repository.fetchCount("acme", "same-id"));
        assertEquals(1, repository.fetchCount("beta", "same-id"));
    }

    @Test
    @WithMockUser(username = "alice")
    void otherUserCannotReadAlreadyCachedTenantDocument() {
        permissions.grant("bob", "beta", "same-id");

        // Bob gọi đúng facade để làm nóng cache của beta.
        assertEquals("BETA: private",
                readAs("bob", "beta", "same-id").body());

        // Alice không có quyền; cache đang nóng vẫn không được lộ dữ liệu.
        assertThrows(AccessDeniedException.class,
                () -> service.read("beta", "same-id"));
        assertEquals(1, repository.fetchCount("beta", "same-id"));
    }

    @Test
    @WithMockUser(username = "alice")
    void revokeTakesEffectEvenAfterCacheWasWarmed() {
        permissions.grant("alice", "acme", "same-id");
        assertEquals("ACME: private",
                service.read("acme", "same-id").body());
        assertEquals(1, repository.fetchCount("acme", "same-id"));

        permissions.revoke("alice", "acme", "same-id");

        assertThrows(AccessDeniedException.class,
                () -> service.read("acme", "same-id"));
        // Deny trước khi vào cache/repository, dù dữ liệu vẫn nằm trong cache.
        assertEquals(1, repository.fetchCount("acme", "same-id"));
    }

    @Test
    @WithMockUser(username = "alice")
    void newGrantTakesEffectAfterPreviousDenial() {
        assertThrows(AccessDeniedException.class,
                () -> service.read("acme", "same-id"));
        assertEquals(0, repository.fetchCount("acme", "same-id"));

        permissions.grant("alice", "acme", "same-id");

        assertEquals("ACME: private",
                service.read("acme", "same-id").body());
        assertEquals(1, repository.fetchCount("acme", "same-id"));
    }

    @Test
    @WithMockUser(username = "alice")
    void revokingOneTenantDoesNotRemoveAnotherTenantsPermission() {
        permissions.grant("alice", "acme", "same-id");
        permissions.grant("alice", "beta", "same-id");
        service.read("acme", "same-id");
        service.read("beta", "same-id");

        permissions.revoke("alice", "acme", "same-id");

        assertThrows(AccessDeniedException.class,
                () -> service.read("acme", "same-id"));
        assertEquals("BETA: private",
                service.read("beta", "same-id").body());

        assertEquals(1, repository.fetchCount("acme", "same-id"));
        assertEquals(1, repository.fetchCount("beta", "same-id"));
    }

    // Đổi principal trong phạm vi một lần gọi; luôn khôi phục alice.
    private Document readAs(String username, String tenantId, String documentId) {
        SecurityContext previous = SecurityContextHolder.getContext();
        try {
            SecurityContext context = SecurityContextHolder.createEmptyContext();
            context.setAuthentication(
                new UsernamePasswordAuthenticationToken(
                    username,
                    "unused",
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))
                )
            );
            SecurityContextHolder.setContext(context);
            return service.read(tenantId, documentId);
        } finally {
            SecurityContextHolder.setContext(previous);
        }
    }
}
~~~

### Vì sao các assert này chứng minh được điều cần kiểm thử?

- **Hai tenant cùng ID:** nếu ai đó sửa @Cacheable thành key chỉ là documentId, lần đọc beta sau acme có nguy cơ trả nhầm **ACME: private**. Assertion nội dung phát hiện regression ngay cả khi cả hai lời gọi đều được cho phép.
- **Bob làm nóng, Alice bị chặn:** test chứng minh quyền được quyết định theo **người gọi hiện tại**, không theo người đầu tiên đã ghi cache. Bộ đếm bằng một xác nhận dữ liệu được cache trước khi Alice thử đọc.
- **Revoke:** test chứng minh policy lookup còn hiệu lực khi data cache đã nóng; số lần repository gọi không tăng cho request bị chặn.
- **Grant:** test chứng minh deny không bị lưu vĩnh viễn trong data cache hoặc chính sách mẫu. Sau grant, request mới được đánh giá và đi tiếp.
- **Độc lập tenant sau revoke:** sửa quyền một tenant không thay đổi khả năng đọc tenant khác.

Phương thức readAs chỉ mô phỏng việc Bob gọi service trong **cùng một test**, để kiểm tra cache ấm trước khi Alice truy cập. Nó luôn phục hồi SecurityContext bằng **finally**, tránh làm hỏng các kiểm thử khác.

## 6. Chạy kiểm thử và kiểm tra regression

Ở thư mục chứa pom.xml, dùng JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
~~~

Khi tất cả code và dependencies hoạt động đúng, kỳ vọng **5 tests run, 0 failures, 0 errors**. Log khởi tạo Spring context có thể khác nhau giữa môi trường.

Hai mutation hữu ích để tự xác minh sức mạnh của test:

**Mutation A – làm hỏng cache key**: đổi ở CachedDocuments:

~~~java
@Cacheable(cacheNames = "documents", key = "#p1") // SAI: chỉ documentId
public Document get(String tenantId, String documentId) {
    return repository.find(tenantId, documentId);
}
~~~

Lúc này test **sameDocumentIdMustStayIsolatedAcrossTenants** phải FAIL: cache entry của acme có thể bị dùng để trả nội dung cho beta. Hãy khôi phục @Cacheable mặc định sau khi thử.

**Mutation B – bỏ kiểm tra quyền ở facade**: tạm bỏ @PreAuthorize trên SecureDocumentService.read. Các bài **otherUserCannotReadAlreadyCachedTenantDocument**, **revokeTakesEffectEvenAfterCacheWasWarmed**, **newGrantTakesEffectAfterPreviousDenial** (và nhánh deny của bài cuối) sẽ FAIL vì thiếu AccessDeniedException. Khôi phục annotation ngay sau thí nghiệm.

Không cần test kết quả theo tổng thời gian chạy (millisecond) để chứng minh cache hit; bộ đếm fetchCount đáng tin cậy và ổn định hơn kiểm thử thời gian trên CI.

## 7. Nếu hệ thống cũng cache quyết định authorization

Ví dụ runnable ở trên **không cache canRead**. Nếu hệ thống thật cache chính sách cho hiệu năng, cần một hợp đồng rõ ràng về độ mới của quyết định, nhất là khi thu hồi quyền.

### 7.1. Key quyết định quyền và thời điểm invalidation

Một decision cache thường cần ít nhất:

~~~text
decisionKey = (subjectId, tenantId, resourceId, action, policyVersion)
~~~

Các chiều bổ sung có thể gồm tổ chức/role, scope, thuộc tính của tài nguyên và điều kiện môi trường (thời gian, IP, mức rủi ro) nếu thực sự tác động đến kết quả. Tránh dùng key chỉ theo username hoặc chỉ theo resourceId.

Khi cập nhật quyền, các lựa chọn phổ biến là:

1. **Không cache quyết định quyền** cho hành động nhạy cảm: mỗi request đọc quyền hiện tại từ nguồn chính sách có bảo đảm nhất quán phù hợp.
2. **Evict/refresh quyết định bị ảnh hưởng** khi commit grant/revoke thành công; các node/cache instance liên quan phải nhận thông báo invalidation.
3. **Policy version / entitlement version**: key hoặc phép so sánh bắt buộc phiên bản mới, khiến quyết định từ phiên bản cũ không được dùng nữa.
4. **TTL ngắn** nếu nghiệp vụ chấp nhận độ trễ hiệu lực được định lượng; TTL **không chứng minh** thu hồi tức thì và không thể thay thế kiểm thử thời hạn hiệu lực.

Với Redis hoặc distributed cache, test phải xác minh **cả nơi phát cập nhật lẫn node đang giữ quyết định cũ**. Không nên chỉ gọi Cache.clear() thủ công trong test quyền; cách đó che giấu việc ứng dụng không tự invalidation khi quyền đổi.

### 7.2. Thêm bài kiểm thử cho bất đồng bộ và nhiều instance

Nếu sản phẩm cam kết revoke có hiệu lực tối đa **T giây** sau commit, kiểm thử phải đo hợp đồng đó:

~~~text
T0: User A có quyền, request trên instance-1 tạo cache entry.
T1: Admin revoke quyền; ghi nhận commit / policyVersion mới.
T2: Request của A vào instance-2, nơi đang giữ decision cache cũ.
Kỳ vọng: sau hạn T, mọi instance từ chối; trước hạn T ứng xử
         đúng với hợp đồng nhất quán đã công bố.
~~~

Sử dụng test container Redis/message broker hoặc môi trường tích hợp nếu hệ thống dùng chúng. Chờ điều kiện theo version/event acknowledgment hoặc polling **có deadline**, không dùng sleep cố định làm bằng chứng quyền đã cập nhật. Bổ sung test khi **event trễ, duplicate, đảo thứ tự, mất event**; hệ thống cần cơ chế đối chiếu/version hoặc fail-closed phù hợp mức rủi ro.

Nếu quyền nằm trong **JWT tự mang roles/scopes**, revoke ở database không tự động thay claims trong JWT đã phát. Hãy kiểm thử theo cơ chế dự kiến: token mới, introspection, revocation list, phiên bản quyền hoặc TTL token. Không được kỳ vọng test dùng @WithMockUser phản ánh toàn bộ pipeline JWT thực tế.

## 8. Phân biệt cache tài liệu và cache dữ liệu cá nhân hóa

Không phải lúc nào data cache có key (tenantId, documentId) cũng đủ an toàn:

| Loại dữ liệu được cache | Thành phần key tối thiểu thường cần | Điều kiện đi kèm |
| --- | --- | --- |
| Tài liệu gốc giống nhau cho người có quyền | tenantId, documentId | Mỗi lần đọc kiểm tra quyền hiện hành trước khi trả dữ liệu |
| Tài liệu đã lọc field theo role/user | tenantId, documentId, identity/role hoặc policy version cần thiết | Tránh người quyền thấp nhận bản cache của người quyền cao |
| Danh sách tìm kiếm có lọc theo quyền | tenantId, query/filter, principal/scope/policy version phù hợp | Cache đúng tập kết quả theo từng người và trạng thái quyền |
| Quyết định allow/deny | subject, tenant, resource, action, version/chính sách liên quan | Invalidation/TTL theo hợp đồng hiệu lực quyền |

Ngoài key, cần kiểm tra **tenant predicate ở database** (ví dụ WHERE tenant_id = :tenantId AND id = :id), phân tách connection/row-level security nếu dùng, và giới hạn đường gọi trực tiếp vào CachedDocuments/Repository. Kiểm thử facade không thay thế việc kiểm tra tất cả entry point của ứng dụng.

Khi **nội dung tài liệu thay đổi**, cache dữ liệu cũng cần eviction/refresh để tránh stale data; đó là vấn đề khác với thay đổi authorization. Trước khi thêm @CacheEvict hoặc ghi đè cache, xác định đúng key tenant + document và tính nguyên tử của cập nhật.

## 9. Những lỗi phổ biến khi viết test

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Chỉ test một tenant | Không thấy trùng document ID và lẫn key | Tạo hai tenant cùng ID nhưng body khác, assert từng body |
| Cache key chỉ là documentId | Một tenant có thể lấy dữ liệu của tenant khác | Key chứa tenantId và mọi chiều dữ liệu ảnh hưởng |
| @Cacheable đặt trên phương thức có auth mà không kiểm tra proxy/advisor | Có nguy cơ kiểm tra quyền không chạy trên đường cache hit tùy cấu trúc | Tách facade @PreAuthorize và bean @Cacheable; test cache đã nóng + denied |
| Chỉ assert HTTP 403/exception | Không biết request đã chạy query nào và đã lộ body nào | Test giá trị trả về, ngoại lệ và fetchCount |
| Không reset state giữa các test | Lần chạy sau phụ thuộc cache/tập quyền từ test trước | Clear cache + reset kho quyền + seed fixture trong @BeforeEach |
| Test revoke nhưng xóa sạch cache ngay trước lần đọc sau | Đã biến case thành cache miss, chưa kiểm được hot cache | Giữ entry dữ liệu nóng; chỉ thay đổi quyền |
| Cache quyền nhưng test chỉ cập nhật Map trực tiếp | Không kiểm được đường invalidation thực tế | Kích hoạt cùng command/event cập nhật quyền mà production dùng |
| Cho rằng @WithMockUser đại diện cho JWT/tenant thực | Không kiểm claims, tenant resolution, token expiry, revoked token | Thêm test HTTP/JWT/identity provider riêng |
| Dùng sleep tùy ý để chờ invalidate | Test flaky và không phản ánh SLA | Poll đến version/điều kiện có deadline, dùng kiểm thử liên instance |
| Trộn dữ liệu cá nhân hóa vào cache chia sẻ theo tenant | Dữ liệu role cao có thể lộ cho role thấp | Tách dữ liệu gốc với authorized projection hoặc tăng chiều cache key |

## 10. Checklist nghiệm thu

- [ ] Cache key phân biệt **tenantId + documentId**, kể cả khi hai tenant có cùng ID.
- [ ] Test nhận đúng **body của từng tenant**, không chỉ kiểm tra không có exception.
- [ ] Một user không có quyền bị chặn **khi cache đã nóng** từ user khác.
- [ ] Quyền **revoke** khiến lần đọc kế tiếp bị chặn theo hợp đồng; dữ liệu vẫn cache mà không vượt quyền.
- [ ] Quyền **grant** có hiệu lực trong lần đọc mới theo hợp đồng.
- [ ] Revoke ở tenant A không ảnh hưởng nhầm đến tenant B.
- [ ] Test kiểm số lần đến repository để phân biệt hit, miss và denied.
- [ ] Có test riêng cho decision cache invalidation/version, JWT và multi-instance nếu hệ thống thực tế dùng chúng.
- [ ] Chạy **mvn test** và xác minh toàn bộ test pass; test mutation bắt được cache key lỗi và bỏ authorization.

## 11. Tài liệu tham khảo

- Spring Security, **Method Security**: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security, **Testing Method Security**: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Framework, **Declarative Annotation-based Caching / Default Key Generation**: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework, **Cache Abstraction**: https://docs.spring.io/spring-framework/reference/integration/cache.html

**Kết luận kỹ thuật:** phải kiểm chứng riêng hai tính chất **không lẫn dữ liệu tenant** và **không dùng quyền đã hết hiệu lực**. Dùng hai tenant có ID trùng nhau, chủ thể có quyền khác nhau, cache đã nóng và thời điểm grant/revoke rõ ràng là cách phát hiện những lỗi mà bài test “đọc được một lần” thường bỏ sót.