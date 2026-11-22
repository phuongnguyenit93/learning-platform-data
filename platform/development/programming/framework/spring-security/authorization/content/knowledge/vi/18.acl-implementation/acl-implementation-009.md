# AclCache, vô hiệu hóa cache và nhiều instance

> **Chủ đề:** Spring Security – authorization → **Triển khai ACL**. Bài này giải thích API `AclCache`, lớp `SpringCacheBasedAclCache`, cách JDBC ACL đọc và làm mới cache, và tại sao quyền bị thu hồi có thể vẫn được cho phép ở một instance khác. Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Security 6.x và HSQLDB. Phần event broker, transactional outbox và cache phân tán được trình bày là thiết kế triển khai bổ sung, không phải tính năng tự động của `AclCache`.

## 1. Cache ACL giúp nhanh hơn, nhưng có thể giữ quyền đã bị thu hồi

Giả sử `Document#101` có ACE:

~~~text
ObjectIdentity = demo.aclcache.Document / 101
PrincipalSid("alice") -> READ -> granting=true
~~~

Mỗi lần đánh giá quyền, Spring Security ACL có thể phải dựng `Acl` từ nhiều bảng. Cache giúp tái sử dụng ACL đã tải, giảm truy vấn SQL. Nhưng nếu admin xóa ACE grant READ mà instance phục vụ request vẫn có snapshot cũ trong bộ nhớ, Alice có thể được phép đọc tài liệu sau khi quyền đã bị thu hồi.

~~~text
T1: Node A đọc ACL từ DB, cache READ=grant của alice
T2: Node B thực hiện revoke, cập nhật DB
T3: Cache của Node B được invalidated
T4: Node A không biết và vẫn dùng cached ACL cũ
T5: Node A có nguy cơ trả allow sai
~~~

Vấn đề là **stale authorization**, không đơn thuần là độ trễ. Khi chọn cache, phải xác định được: sau một lệnh revoke đã commit, **bao lâu** mọi node ngừng sử dụng ACL cũ? Nếu không có cam kết nào về câu trả lời, cache có thể là một rủi ro bảo mật.

## 2. ACL được cache ở tầng nào?

~~~text
HTTP / Service call
       |
       v
AclPermissionEvaluator hoặc authorization service
       |
       v
     AclService
       |
       v
   JdbcAclService
       |
       v
  LookupStrategy / BasicLookupStrategy
       |
       +--------- cache hit --------> AclCache
       |
       +--------- cache miss -------> SQL database
                                       |
                                     Acl/ACE
                                       |
                                     AclCache
       |
       v
Acl.isGranted(permission, applicableSids, false)
       |
    ALLOW hoặc DENY
~~~

`AclCache` lưu thông tin ACL: ObjectIdentity, ACE, SID, permission, owner ACL, parent/inheritance. Nó không phải bảng kết quả `user+object+action → true/false` của ứng dụng. Một ACL đã cache có thể được dùng để xét nhiều người với các SID khác nhau.

| Loại dữ liệu | Ví dụ | Khi thay đổi cần xử lý |
| --- | --- | --- |
| **ACL cache** | ACE cho `Document#101` | Cấp/thu hồi ACE, thay ACL owner/parent |
| **Authentication/JWT/session** | Alice mang `ROLE_EDITOR` | Thu hồi role, khóa user, refresh token |
| **Custom decision cache**, nếu có | Alice được WRITE `Document#101` | Thay ACL **hoặc** authority, tenant, policy |

Vô hiệu hóa ACL cache không tự xóa `ROLE_EDITOR` còn nằm trong JWT cũ. Ngược lại, refresh token không tự cập nhật ACL cũ đang ở cache. Với ACE theo `GrantedAuthoritySid`, cả hai nguồn dữ liệu này đều tham gia quyết định.

## 3. API `AclCache` chính xác

Gói:

~~~java
import org.springframework.security.acls.model.AclCache;
~~~

| Phương thức | Vai trò |
| --- | --- |
| `getFromCache(ObjectIdentity oid)` | Lấy `MutableAcl` đã cache theo type + domain ID |
| `getFromCache(Serializable aclPk)` | Lấy ACL theo primary key nội bộ của ACL |
| `putInCache(MutableAcl acl)` | Thêm ACL đã dựng vào cache |
| `evictFromCache(ObjectIdentity oid)` | Vô hiệu hóa ACL qua ObjectIdentity |
| `evictFromCache(Serializable aclPk)` | Vô hiệu hóa ACL qua database PK |
| `clearCache()` | Xóa toàn bộ ACL trong backend/instance cache này |

### Phân biệt hai khóa

~~~text
Document ID = 101
ObjectIdentity(type="demo.aclcache.Document", id=101)
                       |
                       v
                   ACL record
                       |
                       v
ACL primary key trong bảng acl_object_identity = 1472 (ví dụ)
~~~

Document ID 101 **không mặc nhiên** là ACL primary key 1472. `SpringCacheBasedAclCache` hỗ trợ lookup/eviction theo cả hai loại khóa. Nếu tự thao tác underlying `org.springframework.cache.Cache` và chỉ evict một alias, dữ liệu cũ có thể còn truy xuất được qua alias còn lại. Ưu tiên gọi `AclCache.evictFromCache(...)` thay vì tự suy luận key nội bộ.

Một cache miss (giá trị null) chỉ nói rằng cache hiện không có ACL; **không chứng minh ACL không tồn tại trong DB**. Lookup phải truy vấn nguồn dữ liệu có thẩm quyền.

### ACL cache có thể chứa mutable objects

`AclCache` làm việc với `MutableAcl`. Không sửa `getEntries()` của cached object rồi kỳ vọng database được cập nhật hoặc mọi thread nhận cùng một trạng thái nhất quán. Để quản trị quyền, dùng `MutableAclService`, thay ACE rồi `updateAcl`; để đọc quyền, dùng `AclService` cùng `Acl.isGranted`. Đừng biến cache thành nơi ghi nguồn sự thật.

## 4. `SpringCacheBasedAclCache` và Spring Cache abstraction

Ví dụ adapter thông dụng:

~~~java
import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.model.AclCache;

// ĐOẠN MINH HỌA: đã có hai bean strategy.
Cache springCache = new ConcurrentMapCache("acl-cache");
AclCache aclCache = new SpringCacheBasedAclCache(
        springCache,
        permissionGrantingStrategy,
        aclAuthorizationStrategy);
~~~

Constructor của `SpringCacheBasedAclCache` nhận một Spring `Cache` cùng `PermissionGrantingStrategy` và `AclAuthorizationStrategy`. Nó hỗ trợ khôi phục các thông tin runtime của `AclImpl` khi tải từ cache, và theo Javadoc giả định các ACL dùng nhất quán những strategy đó.

### Backend quyết định cache có chia sẻ được không

- `ConcurrentMapCache`: cache **trong JVM**; các node khác không thể tự thấy lệnh evict.
- Caffeine local cache: thường cũng chỉ thuộc JVM hiện tại.
- Backend Redis/Hazelcast thông qua Spring Cache: có khả năng chia sẻ nhưng phải kiểm chứng serialization, eviction, key aliases, tenant scope và race khi reload.
- Không dùng cache: bỏ một lớp stale ACL nhưng tăng tải SQL; vẫn phải xử lý transaction/race và Authentication hiện hành.

Không được gọi `ConcurrentMapCache` là distributed cache chỉ vì ứng dụng chạy trên Kubernetes với nhiều replica.

## 5. Khi nào phải làm mới hoặc vô hiệu ACL?

| Thao tác | ACL trực tiếp | Ảnh hưởng lan truyền |
| --- | --- | --- |
| `createAcl(oid)` | ACL mới | Một negative cache tùy biến trước đó có thể đã nhớ missing ACL |
| `updateAcl(acl)` thêm READ grant | ACL này | Cache cũ có thể tiếp tục deny |
| `updateAcl(acl)` xóa READ grant | ACL này | Cache cũ có thể tiếp tục **allow** |
| `updateAcl(acl)` thêm DENY | ACL này | Nếu stale, lệnh deny có thể không được áp dụng |
| Thay `getOwner()` / parent / inheritance | ACL này | Có thể ảnh hưởng cả ACL con |
| `deleteAcl(oid, false)` | ACL này | Nếu có con thì có thể ném `ChildrenExistException` |
| `deleteAcl(oid, true)` | ACL này và child liên quan | Không được xóa cây ACL thiếu kiểm soát |
| Thu hồi `ROLE_REVIEWER` của một user | Không nhất thiết thay ACL | Cập nhật Authentication/JWT/session |
| Đổi chính sách grant/deny chung | Nhiều ACL đang cache | Có thể cần clear/đổi version cache namespace |
| Cập nhật bảng ACL trực tiếp qua SQL | Những ACL liên quan | Bypass cơ chế invalidation của service |

**Revoke là trường hợp cần ưu tiên.** Với grant mới chưa lan truyền, người dùng có thể tạm bị từ chối sai (availability). Với revoke chưa lan truyền, người dùng có thể **tiếp tục được phép sai** (confidentiality/integrity).

### Không phải mọi update domain object đều cần evict ACL

Nếu tài liệu chỉ đổi tiêu đề mà ACL hoàn toàn không phụ thuộc tiêu đề, không nhất thiết phải evict ACL. Tuy vậy, nếu policy còn xét `tenantId`, `locked`, owner, trạng thái legal hold hoặc workflow, chính sách nghiệp vụ cũng phải đọc trạng thái đáng tin cậy; cached ACL không thay thế những điều kiện ngoài ACL.

## 6. `JdbcMutableAclService` xử lý invalidation đến mức nào?

`JdbcMutableAclService` được tạo với:

~~~java
new JdbcMutableAclService(
        dataSource, lookupStrategy, aclCache);
~~~

Khi ghi thông qua `MutableAclService`, implementation JDBC có cơ chế làm sạch cache được inject cùng nó. Với `updateAcl`, triển khai chuẩn còn xử lý các ACL con phụ thuộc do permission có thể được kế thừa từ parent. Những bản cũ/cụ thể nên được kiểm tra bằng test và source của version đang dùng.

**Giới hạn then chốt:** cache được evict là **cache mà writer đang giữ reference**. Nếu Node A có `ConcurrentMapCache("nodeA")` và Node B có `ConcurrentMapCache("nodeB")`, cập nhật ACL ở Node A không tự gọi method Java trên cache của Node B.

### Thứ tự transaction và cache có thể tạo cửa sổ stale

~~~text
T1: Transaction A cập nhật ACL trong DB (chưa commit)
T2: A evict cache và có thể nạp lại ACL mới trong transaction của A
T3: B cache miss, đọc từ DB theo isolation của B
T4: B có thể vẫn thấy ACL cũ nếu A chưa commit
T5: Transaction A commit
T6: B vẫn có thể giữ snapshot cũ
~~~

`@Transactional` hỗ trợ tính nguyên tử của lệnh DB ở một transaction, nhưng **không tự biến cache thành transactional cache**. Do đó thiết kế event phân tán nên phát invalidation **sau commit**; với yêu cầu thu hồi tức thì, even after-commit async event vẫn chưa phải strong consistency.

## 7. Demo đầy đủ: hai cache độc lập, một HSQLDB chung

Chương trình mẫu dùng Java 17+, Spring Boot 3.x, Spring Security 6.x. Nó tạo **cache Node A** trong Spring Context; integration test tạo thêm **cache Node B** qua các instance khác của `SpringCacheBasedAclCache` và `JdbcMutableAclService` nhưng dùng chung DataSource.

Hai cache trong một JVM chỉ là **mô phỏng hai node**; nó cho thấy chính xác vấn đề cache độc lập mà không đòi hỏi hai server. Trên production, các node/JVM thật còn có networking và cơ chế triển khai khác.

### 7.1. Dependencies

Trong project Gradle Spring Boot đã có plugins Java, Spring Boot và dependency management tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.security:spring-security-acl'
    runtimeOnly 'org.hsqldb:hsqldb'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Ví dụ cần module `spring-security-acl` riêng; starter Security không tự cung cấp hệ thống JDBC ACL. Spring Security version phải cùng dòng với Boot.

### 7.2. DataSource và schema

**`src/main/resources/application.properties`**

~~~properties
spring.datasource.url=jdbc:hsqldb:mem:acl_cache_demo
spring.datasource.driver-class-name=org.hsqldb.jdbc.JDBCDriver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

**`src/main/resources/schema.sql`**

~~~sql
create table acl_sid (
    id bigint generated by default as identity(start with 100) not null primary key,
    principal boolean not null,
    sid varchar_ignorecase(100) not null,
    constraint uk_acl_sid unique (sid, principal)
);

create table acl_class (
    id bigint generated by default as identity(start with 100) not null primary key,
    class varchar_ignorecase(100) not null,
    constraint uk_acl_class unique (class)
);

create table acl_object_identity (
    id bigint generated by default as identity(start with 100) not null primary key,
    object_id_class bigint not null,
    object_id_identity varchar_ignorecase(36) not null,
    parent_object bigint,
    owner_sid bigint,
    entries_inheriting boolean not null,
    constraint uk_acl_identity unique (object_id_class, object_id_identity),
    constraint fk_acl_parent foreign key (parent_object)
        references acl_object_identity(id),
    constraint fk_acl_class foreign key (object_id_class)
        references acl_class(id),
    constraint fk_acl_owner foreign key (owner_sid)
        references acl_sid(id)
);

create table acl_entry (
    id bigint generated by default as identity(start with 100) not null primary key,
    acl_object_identity bigint not null,
    ace_order integer not null,
    sid bigint not null,
    mask integer not null,
    granting boolean not null,
    audit_success boolean not null,
    audit_failure boolean not null,
    constraint uk_acl_entry unique (acl_object_identity, ace_order),
    constraint fk_acl_entry_object foreign key (acl_object_identity)
        references acl_object_identity(id),
    constraint fk_acl_entry_sid foreign key (sid)
        references acl_sid(id)
);
~~~

Đây là DDL theo kiểu HSQLDB phục vụ demo; với PostgreSQL/H2/MySQL cần điều chỉnh schema và query lấy generated ID của JDBC ACL. Production nên dùng migration thay vì chạy `schema.sql` lặp.

### 7.3. Application và model

**`src/main/java/demo/aclcache/AclCacheApplication.java`**

~~~java
package demo.aclcache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class AclCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(AclCacheApplication.class, args);
    }
}
~~~

**`src/main/java/demo/aclcache/Document.java`**

~~~java
package demo.aclcache;

public record Document(long id, String title) {
}
~~~

ObjectIdentity trong ví dụ sẽ là `new ObjectIdentityImpl(Document.class.getName(), id)`. Với Java record, tránh mặc định constructor `ObjectIdentityImpl(object)` tự đọc accessor `id()`.

### 7.4. Cấu hình cache Node A và JDBC service

**`src/main/java/demo/aclcache/AclInfrastructure.java`**

~~~java
package demo.aclcache;

import javax.sql.DataSource;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.jdbc.LookupStrategy;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
public class AclInfrastructure {

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ACL_ADMIN"));
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger());
    }

    @Bean
    AclCache aclCache(
            PermissionGrantingStrategy permissionGrantingStrategy,
            AclAuthorizationStrategy aclAuthorizationStrategy) {

        return new SpringCacheBasedAclCache(
                new ConcurrentMapCache("node-a-acls"),
                permissionGrantingStrategy,
                aclAuthorizationStrategy);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache aclCache,
            AclAuthorizationStrategy aclAuthorizationStrategy,
            PermissionGrantingStrategy permissionGrantingStrategy) {

        return new BasicLookupStrategy(
                dataSource, aclCache, aclAuthorizationStrategy,
                permissionGrantingStrategy);
    }

    @Bean
    JdbcMutableAclService aclService(
            DataSource dataSource,
            LookupStrategy lookupStrategy,
            AclCache aclCache) {

        return new JdbcMutableAclService(
                dataSource, lookupStrategy, aclCache);
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclService aclService) {

        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(
                new AclPermissionEvaluator(aclService));
        return handler;
    }
}
~~~

Các bean `lookupStrategy` và `aclService` nhận **cùng `AclCache`**. Nếu writer và reader trong một process vô tình dùng hai cache khác nhau, writer có thể evict cache A trong khi request vẫn đọc từ cache B.

Bean `MethodSecurityExpressionHandler` giúp nối `AclPermissionEvaluator` nếu app dùng `hasPermission`. Test dưới đây quan sát trực tiếp `AclService` để thấy dữ liệu stale, không phụ thuộc controller.

### 7.5. Service grant/revoke có chốt admin và transaction

**`src/main/java/demo/aclcache/AclWriterService.java`**

~~~java
package demo.aclcache;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AclWriterService {

    private final MutableAclService writer;

    public AclWriterService(MutableAclService writer) {
        this.writer = writer;
    }

    private ObjectIdentity oid(long id) {
        return new ObjectIdentityImpl(Document.class.getName(), id);
    }

    @Transactional
    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    public void grantRead(long id, String username) {
        ObjectIdentity object = oid(id);
        MutableAcl acl;

        try {
            acl = (MutableAcl) writer.readAclById(object);
        }
        catch (NotFoundException missing) {
            acl = writer.createAcl(object);
        }

        Sid sid = new PrincipalSid(username);
        boolean exists = acl.getEntries().stream().anyMatch(ace ->
                ace.getSid().equals(sid)
                && ace.getPermission().getMask()
                    == BasePermission.READ.getMask()
                && ace.isGranting());

        if (!exists) {
            acl.insertAce(
                    acl.getEntries().size(),
                    BasePermission.READ,
                    sid,
                    true);
            writer.updateAcl(acl);
        }
    }

    @Transactional
    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    public void revokeRead(long id, String username) {
        MutableAcl acl;

        try {
            acl = (MutableAcl) writer.readAclById(oid(id));
        }
        catch (NotFoundException missing) {
            return;
        }

        Sid sid = new PrincipalSid(username);
        boolean changed = false;

        for (int i = acl.getEntries().size() - 1; i >= 0; i--) {
            var ace = acl.getEntries().get(i);
            if (ace.getSid().equals(sid)
                    && ace.getPermission().getMask()
                       == BasePermission.READ.getMask()
                    && ace.isGranting()) {
                acl.deleteAce(i);
                changed = true;
            }
        }

        if (changed) {
            writer.updateAcl(acl);
        }
    }

    @Transactional
    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    public void deleteAcl(long id) {
        writer.deleteAcl(oid(id), false);
    }
}
~~~

`@Transactional` bao quanh việc cập nhật SQL; `@PreAuthorize` kiểm tra caller có `ACL_ADMIN` tại public service boundary. Private helper không có annotation cần proxy. Grant idempotent ở mức kiểm tra ACE đã có, nhưng **không tự ngăn hai giao dịch cạnh tranh**. Thu hồi một ACE của user không thu hồi grant còn tồn tại qua role hoặc parent ACL.

### 7.6. Test: một database, hai `AclCache` độc lập

**`src/test/java/demo/aclcache/AclCacheIntegrationTest.java`**

~~~java
package demo.aclcache;

import java.util.List;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.jdbc.LookupStrategy;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(classes = AclCacheApplication.class)
class AclCacheIntegrationTest {

    @Autowired AclWriterService writer;
    @Autowired AclService nodeAReader;
    @Autowired AclCache nodeACache;
    @Autowired DataSource dataSource;
    @Autowired AclAuthorizationStrategy aclAuthorizationStrategy;
    @Autowired PermissionGrantingStrategy permissionGrantingStrategy;

    private ObjectIdentity oid(long id) {
        return new ObjectIdentityImpl(Document.class.getName(), id);
    }

    private boolean canRead(Acl acl, String username) {
        List<Sid> sids = List.of(new PrincipalSid(username));
        try {
            return acl.isGranted(List.of(BasePermission.READ), sids, false);
        } catch (NotFoundException noMatchingAce) {
            return false;
        }
    }

    private record Node(AclCache cache, AclService reader) {
    }

    private Node createNodeB() {
        // Cache Node B tách hoàn toàn khỏi cache A.
        AclCache cacheB = new SpringCacheBasedAclCache(
                new ConcurrentMapCache("node-b-acls"),
                permissionGrantingStrategy,
                aclAuthorizationStrategy);

        LookupStrategy lookupB = new BasicLookupStrategy(
                dataSource,
                cacheB,
                aclAuthorizationStrategy,
                permissionGrantingStrategy);

        AclService readerB =
                new JdbcMutableAclService(dataSource, lookupB, cacheB);

        return new Node(cacheB, readerB);
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void localWriterInvalidatesLocalCachedAcl() {
        ObjectIdentity object = oid(1101L);

        writer.grantRead(1101L, "alice");
        assertTrue(canRead(nodeAReader.readAclById(object), "alice"));
        assertNotNull(nodeACache.getFromCache(object));

        writer.revokeRead(1101L, "alice");

        assertFalse(canRead(nodeAReader.readAclById(object), "alice"));
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void nodeBRemainsStaleUntilItEvictsItsOwnCache() {
        ObjectIdentity object = oid(1202L);
        Node nodeB = createNodeB();

        writer.grantRead(1202L, "alice");

        // Warm cache B bằng lần đọc qua reader B.
        assertTrue(canRead(nodeB.reader().readAclById(object), "alice"));
        assertNotNull(nodeB.cache().getFromCache(object));

        // Writer A thu hồi trong DB và invalidates cache A.
        writer.revokeRead(1202L, "alice");

        // B chưa nhận event, nên vẫn dùng ACL cũ.
        assertTrue(canRead(nodeB.reader().readAclById(object), "alice"));

        // Giả lập sự kiện AFTER_COMMIT tới Node B:
        nodeB.cache().evictFromCache(object);

        // B phải lấy ACL mới từ DB: không còn ACE READ.
        assertFalse(canRead(nodeB.reader().readAclById(object), "alice"));
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void deletionNeedsInvalidationInTheOtherNode() {
        ObjectIdentity object = oid(1303L);
        Node nodeB = createNodeB();

        writer.grantRead(1303L, "alice");
        assertTrue(canRead(nodeB.reader().readAclById(object), "alice"));

        writer.deleteAcl(1303L);

        // ACL ở B vẫn còn do cache cũ:
        assertTrue(canRead(nodeB.reader().readAclById(object), "alice"));

        nodeB.cache().evictFromCache(object);

        assertThrows(NotFoundException.class,
                () -> nodeB.reader().readAclById(object));
    }
}
~~~

Các test **không** tạo hai JVM, nhưng dùng hai `JdbcMutableAclService` có cache riêng và chung DataSource, qua đó cố tình tái hiện nguyên nhân stale. Test thứ hai yêu cầu quan sát kết quả allow **trước khi evict** và deny **sau khi evict**. Test thứ ba chứng minh một ACL đã xóa khỏi DB vẫn có thể tiếp tục hiện diện ở cache của node khác.

Chạy:

~~~text
./gradlew test --tests demo.aclcache.AclCacheIntegrationTest
~~~

Windows:

~~~text
gradlew.bat test --tests demo.aclcache.AclCacheIntegrationTest
~~~

Mã ví dụ không có `System.out.println`; không có stdout nghiệp vụ cố định. Mục tiêu là Gradle hoàn tất với các assertion thành công. Nếu dùng JDBC dialect khác hoặc project đã đổi phiên bản Security, chạy lại trên stack thực tế trước khi triển khai.

## 8. Làm thế nào invalidation lan tới mọi instance?

Một thiết kế production thường có luồng:

~~~text
       Shared ACL Database
               ▲
         +-----+------+
         |            |
       Node A       Node B
       cache A      cache B
         |            |
         +-----+------+
               |
          Event broker
       (stream/pubsub/outbox)
~~~

Một lệnh revoke diễn ra như sau:

1. Node A kiểm tra actor có quyền sửa ACL **trên đúng object và tenant**.
2. Node A sửa ACL trong transaction DB, gọi `MutableAclService.updateAcl(...)`.
3. Transaction commit thành công.
4. Node A phát sự kiện `ACL_CHANGED` kèm ObjectIdentity và revision.
5. Node B nhận sự kiện, evict ACL tương ứng (và các child có kế thừa nếu cần).
6. Request sau đó ở B cache miss và đọc ACL mới từ source of truth.

Bước 4–5 **không tự có** trong `JdbcMutableAclService`. Cần bổ sung broker/consumer, retry, khả năng hồi phục và quan sát lag.

### 8.1. Cấu trúc event

~~~java
// Bản ghi minh họa; không phải listener/broker hoàn chỉnh.
public record AclChanged(
        String objectType,
        long objectId,
        String tenantId,
        long revision,
        String changeId) {
}
~~~

Event nên mang **định danh ACL**, không phát toàn bộ nội dung ACE, token hoặc dữ liệu nhạy cảm cho mọi subscriber. `tenantId` phải đến từ nguồn tin cậy; `revision` giúp xử lý event đến sai thứ tự hoặc truy vấn version mới hơn; `changeId` hỗ trợ idempotency/tracing.

### 8.2. Tại sao phải publish sau commit?

Nếu publish trước commit:

~~~text
T1: Node A sửa ACL nhưng chưa commit.
T2: Node B nhận event, evict cache.
T3: Node B SELECT dữ liệu còn ở phiên bản cũ.
T4: Node B cache lại dữ liệu cũ.
T5: Node A commit ACL mới.
T6: Node B tiếp tục giữ ACL sai.
~~~

Với Spring, có thể phát một application event trong transaction và chạy callback sau commit:

~~~java
// ĐOẠN MINH HỌA: gọi từ phương thức có @Transactional thật.
applicationEventPublisher.publishEvent(
        new AclChanged(
                Document.class.getName(),
                documentId,
                trustedTenantId,
                revision,
                changeId));
~~~

~~~java
// ĐOẠN MINH HỌA: externalBroker là adapter cần triển khai riêng.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void publishAfterCommit(AclChanged event) {
    externalBroker.publish(event);
}
~~~

Imports:

~~~java
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.event.TransactionPhase;
~~~

`@TransactionalEventListener` chỉ quyết định **thời điểm callback trong một JVM**, không tự gửi sang JVM khác. Nếu process chết sau khi DB commit nhưng trước khi publish, event có thể mất. Với yêu cầu tin cậy cao, dùng **transactional outbox**: cùng DB transaction ghi thay đổi ACL và một row outbox, sau đó publisher riêng retry tới broker, consumer xử lý idempotent.

### 8.3. Evict phải đúng ObjectIdentity và đúng cache instance

~~~java
// MINH HỌA ở consumer Node B:
ObjectIdentity object = new ObjectIdentityImpl(
        Document.class.getName(),
        event.objectId());

nodeBaclCache.evictFromCache(object);
~~~

`nodeBaclCache` ở đây là bean `AclCache` của Node B; không phải cache object của Node A được serialize chuyển sang. Không cần chép ACE vào sự kiện vì ACL trong DB mới là nguồn sự thật.

Nếu event chứa ObjectIdentity dưới dạng String mà hệ thống tra cứu dùng Long, phải chuyển kiểu đúng; cache key không khớp sẽ để lại entry stale. Khi có multi-tenant, định danh object cũng phải phân biệt tenant nhất quán.

### 8.4. Parent và child ACL

~~~text
Folder#8 ACL: ROLE_REVIEWER -> READ:grant
  |
  +-- Document#101, entriesInheriting=true
  +-- Document#202, entriesInheriting=true
~~~

Nếu Node B cache ACL của child với parent snapshot cũ, chỉ evict folder có thể chưa đủ. Writer JDBC có đường invalidation cho child trong cache của chính nó; trong hệ thống nhiều node, consumer phải evict tương ứng toàn bộ subtree hoặc chọn `clearCache()` có kiểm soát.

Có hai chiến lược:
- **Targeted:** tra cứu descendant ObjectIdentity và evict từng ACL; cần xử lý nhiều tầng, pagination và tránh vòng lặp.
- **Conservative:** clear toàn ACL cache của node/tenant sau thay đổi ở parent quan trọng; đơn giản về correctness nhưng có thể gây SQL burst.

Không mặc định `AclCache.evictFromCache(parent)` tự invalidate toàn bộ child khi gọi trực tiếp từ một consumer.

## 9. Shared Redis cache và những race vẫn còn

Thay local cache bằng backend dùng chung:

~~~text
Node A -----+
            +-- SpringCacheBasedAclCache --> Shared cache --> ACL DB on miss
Node B -----+
~~~

Khi eviction đúng key ở cache chung, cả hai node có thể thấy dữ liệu bị xóa. Nhưng vẫn phải kiểm tra: kiểu serialize `AclImpl`, phiên bản class/strategy, cấu trúc key OID/PK, parent inheritance, backend outage, tenant namespace, eviction policy và race.

**Race refill sau evict:**

~~~text
T1: B cache miss và bắt đầu SELECT ACL cũ.
T2: A commit revoke ACL.
T3: A evict shared cache.
T4: B hoàn tất SELECT cũ, đặt ACL cũ vào cache.
T5: C cache hit ACL cũ và ALLOW sai.
~~~

Shared cache **không tự đạt strong consistency**. Cách xử lý nghiêm ngặt có thể cần revision theo ACL/tenant, kiểm soát version khi put, kiểm tra revision từ DB lúc quyết định, hoặc bỏ cache ở đường cần thu hồi tức thì. TTL chỉ giới hạn tối đa cửa sổ stale trong điều kiện bình thường, không loại bỏ hoàn toàn.

## 10. So sánh chiến lược cache nhiều node

| Chiến lược | Lợi ích | Giới hạn |
| --- | --- | --- |
| Không cache ACL | Gần nguồn DB hơn, dễ tránh stale ACL local | Tải SQL tăng; DB transaction vẫn cần quản lý |
| Một JVM + ConcurrentMapCache | Dễ học và cấu hình | Không phù hợp multi-instance cần revoke nhanh |
| Local cache + pub/sub | Nhanh, không cần serialize toàn bộ ACL | Message drop, lag và event order |
| Local cache + transactional outbox | Retry/replay đáng tin cậy hơn | Vẫn eventual consistency nếu event async |
| Shared cache (Redis...) | Invalidation có thể chia sẻ qua backend | Serialization, alias key, refill race, network |
| Versioned ACL cache | Phát hiện/mất hiệu lực snapshot lỗi thời | Cần version source of truth và atomic checks |
| Short TTL + fallback DB | Giới hạn thời gian stale | Không bảo đảm revoke tức thì; tăng SQL |
| Không dùng cache ở endpoint nhạy cảm | Giảm phụ thuộc vào invalidation async | Chậm hơn, cần tối ưu query |

Chọn theo yêu cầu thu hồi: chẳng hạn “sau commit, không request nào được tiếp tục đọc tài liệu” đòi hỏi cơ chế mạnh hơn event async đơn thuần. Ngược lại, nghiệp vụ ít nhạy cảm có thể chọn một **cửa sổ eventual consistency được đo và chấp nhận**.

## 11. Fail closed khi ACL hoặc cache không thể xác minh

| Tình huống | Cách hiểu | Hành vi gợi ý |
| --- | --- | --- |
| `getFromCache(oid) == null` | Cache miss | Lookup DB |
| `AclService.readAclById` ném `NotFoundException` | Không có ACL | Deny |
| `Acl.isGranted` ném `NotFoundException` | Không có ACE đưa ra quyết định | Deny |
| `UnloadedSidException` | Thiếu SID đã tải để xét | Xử lý lookup đúng; không allow |
| Cache backend timeout | Không dùng cache được | DB fallback an toàn hoặc lỗi 503 |
| DB không đọc được | Không xác minh được quyền | Deny/503, không dùng grant cache không đáng tin |
| Broker mất kết nối | Có thể thiếu invalidation | Bật recovery/reconcile, đo lag |
| Event không parse được OID | Không biết evict key nào | Log/alert, retry hoặc clear có kiểm soát |
| Auth token role đã cũ | Cache ACL không giải quyết | Revocation/refresh token và auth lookup |

Không bắt mọi exception rồi trả `true` vì muốn hệ thống tiếp tục phục vụ. Việc không xác minh được quyền có thể dẫn đến HTTP 503 (lỗi dịch vụ) thay vì 403 (đã biết không có quyền); mục tiêu là không lộ tài nguyên.

Ví dụ check theo API:

~~~java
// ĐOẠN MINH HỌA trong service đã inject aclService.
public boolean canRead(
        ObjectIdentity object,
        Authentication authentication) {

    if (authentication == null || !authentication.isAuthenticated()) {
        return false;
    }

    List<Sid> sids =
            new SidRetrievalStrategyImpl().getSids(authentication);

    try {
        Acl acl = aclService.readAclById(object, sids);
        return acl.isGranted(
                List.of(BasePermission.READ), sids, false);
    } catch (NotFoundException noDecision) {
        return false;
    }
}
~~~

Với production, phân biệt anonymous token qua `AuthenticationTrustResolver` hoặc cơ chế xác thực tin cậy; method minh họa chỉ cho thấy cách xử lý ACL NotFound.

## 12. Monitoring và kiểm thử hậu deploy

Cache hit rate cao chưa nói lên an toàn. Nên đo:

- Cache hit/miss, số entry, eviction, clear, memory và SQL query latency.
- Lệnh cấp/thu hồi đã commit, version và Change ID.
- Độ trễ từ **ACL revoke commit** đến **mỗi node bắt đầu deny**.
- Event broker backlog, retry, consumer lag, dead-letter messages.
- Số thất bại do cache/DB, fallback count và lỗi deserialize.
- Tỷ lệ bản ghi cache với revision thấp hơn DB.
- Số lượng ACL child phải evict khi thay parent, và SQL load sau clear.
- Trường hợp stale grant được phát hiện bằng probe trong pre-production/canary.

**Kiểm thử nhiều node** cần chạy với ít nhất hai cache thật sự độc lập, không chỉ một Mockito spy của chung bean. Các kịch bản: warm cache rồi revoke từ node khác; grant mới, delete ACL, thay parent inheritance, đổi role trong Authentication, event mất/trễ/đến sai thứ tự, cache backend outage, DB timeout, rolling upgrade.

## 13. Troubleshooting

| Triệu chứng | Khả năng cao | Cách khắc phục |
| --- | --- | --- |
| Chỉ Node A biết quyền mới | Cache B không được evict | Kiểm tra event và địa chỉ cache B |
| Revoke đã commit nhưng Node B vẫn allow | Stale ACL hoặc role/token cũ | Kiểm tra đồng thời cache ACL và Authentication |
| Restart node làm hết lỗi | Local cache cũ | Sửa propagation, không dùng restart làm giải pháp |
| `evictFromCache` xong vẫn đọc ACL cũ | Key không đúng, alias PK/OID, child/parent | Kiểm tra type/ID, dùng AclCache API và subtree |
| SQL trực tiếp sửa `acl_entry` không thay permission | Bỏ qua writer/invalidation | Dùng MutableAclService hoặc clear/reconcile |
| Cache hit cao nhưng permission sai | Stale refill, TTL quá dài | Version gate, test revoke lag |
| Cache clear làm DB load tăng vọt | Stampede | Batch loading, TTL jitter, giới hạn đồng thời |
| Redis deserialize `AclImpl` thất bại | Serializer/class version không tương thích | Versioned namespace, cache flush khi deploy |
| Chỉ những tài liệu con bị sai | Parent ACL cũ vẫn nằm trong child cache | Evict child subtree hoặc clear |
| Người bị bỏ role vẫn đọc được | JWT/session chứa role cũ | Token revocation/refresh |
| Grant bị mất khi nhiều admin sửa cùng lúc | Lost update ACL | Lock/version/serialize theo ObjectIdentity |
| Event có nhưng node không invalidate | Consumer lỗi, route sai, parse OID sai | Retry, alert và quan sát event lag |
| Cache backend down lại cho phép tất cả | Fail-open fallback | Deny/503 hoặc DB fallback có kiểm soát |
| Tenant B nhận ACL của tenant A | Cache identity không phân biệt tenant | Partition cache và ObjectIdentity đúng |

## 14. Bài tập thực hành

**Bài 1 – Hai loại cache key.** Sau khi warm `AclCache`, thử `getFromCache(oid)` và `getFromCache(acl.getId())`. Giải thích vì sao domain ID không nhất thiết là database ACL PK.

**Bài 2 – Xóa grant ở hai node.** Chạy `AclCacheIntegrationTest`. Xóa dòng `nodeB.cache().evictFromCache(object)` trong bản thực hành riêng; quan sát Node B vẫn có grant. Bổ sung event consumer giả lập và xác minh hết stale sau evict.

**Bài 3 – Parent/child.** Tạo folder ACL có READ grant và hai child ACL kế thừa. Warm cả ba, sửa parent, rồi thiết kế invalidation cho con ở Node B.

**Bài 4 – Sau commit.** Phát `AclChanged` trong transaction, dùng `@TransactionalEventListener(phase=AFTER_COMMIT)`. Test rollback không phát thành công. Mô tả tình huống crash sau commit cần outbox.

**Bài 5 – Shared backend.** Thử Redis Spring Cache, đo key aliases, kiểm thử serialize và mô phỏng SELECT ACL cũ kết thúc sau khi event evict. Đề xuất revision check.

**Bài 6 – Revocation SLA.** Xác định một mức trễ tối đa chấp nhận được khi admin revoke READ. Đo trên nhiều node với broker delay, node restart và DB/cache outage. Nếu cần tức thì, đề xuất path kiểm tra DB/revision.

**Bài 7 – Authentication.** Thu hồi `ROLE_REVIEWER` của người dùng nhưng giữ JWT cũ. Chứng minh evict ACL cache không tự cập nhật token, rồi thêm cơ chế auth revocation phù hợp.

**Tiêu chí hoàn thành:** sử dụng đúng `AclCache`, hiểu `SpringCacheBasedAclCache` và hai loại key, chứng minh cache local stale sau revoke, giải thích event after commit và outbox, thiết kế invalidation parent/child và đa node, không nhầm cached ACL với Authentication hoặc nguồn dữ liệu quyền.

## Tài liệu tham khảo chính thức

- Spring Security – Domain Object Security (ACLs), cấu hình `SpringCacheBasedAclCache`: https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html
- Spring Security 6.5 – AclCache API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/AclCache.html
- Spring Security 6.5 – SpringCacheBasedAclCache API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/SpringCacheBasedAclCache.html
- Spring Security 6.5 – JdbcMutableAclService API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html
- Spring Security 6.5 – BasicLookupStrategy API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/BasicLookupStrategy.html
- Spring Framework – Transaction-bound Events, `@TransactionalEventListener`: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Security – ACL JDBC Schema: https://docs.spring.io/spring-security/reference/servlet/appendix/database-schema.html
