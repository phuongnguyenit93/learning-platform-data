# AclService, MutableAclService và JdbcMutableAclService

> **Ngữ cảnh:** Spring Security – authorization → **Triển khai ACL**. Bài này tập trung vào API đọc `AclService`, API đọc/ghi `MutableAclService`, và implementation lưu dữ liệu qua JDBC `JdbcMutableAclService`. Người học sẽ cấu hình các thành phần ACL, quản lý vòng đời quyền của một tài nguyên và kiểm thử grant/revoke với Java 17+, Spring Boot 3.x, Spring Security 6.x và HSQLDB in-memory.

## 1. Tại sao cần ba thành phần này?

Kiểm tra `hasAuthority('DOC_READ')` chỉ xét quyền chung của người gọi. Một ứng dụng chia sẻ tài liệu có thể cần những quy tắc chi tiết hơn:

- Alice được đọc `Document#101`.
- Bob được đọc `Document#202`.
- Người có `ROLE_REVIEWER` được đọc `Document#303`.
- Không tự suy ra quyền WRITE hay READ trên tài liệu khác chỉ vì có một grant.

Spring Security ACL gắn **Access Control Entry (ACE)** vào ACL của từng **ObjectIdentity**:

~~~text
Document#101 / ACL
  ├── PrincipalSid("alice") → READ: grant
  └── PrincipalSid("bob")   → WRITE: deny

Document#303 / ACL
  └── GrantedAuthoritySid("ROLE_REVIEWER") → READ: grant
~~~

Một quyết định ACL phối hợp bốn yếu tố: tài nguyên nào (ObjectIdentity), ai (Sid), làm gì (Permission), cho phép hay từ chối (granting). Không chỉ có SID hay quyền là đủ.

Khi triển khai, hệ thống cần **đọc quyền để trả quyết định**, **cấp/thu hồi quyền khi nghiệp vụ thay đổi** và **persist quyền bền vững trong database**. Đó là vai trò của `AclService`, `MutableAclService`, `JdbcMutableAclService`.

## 2. Quan hệ giữa interface và JDBC implementation

~~~text
               AclService
               (interface)
                 ▲      ▲
                 │      │
    MutableAclService   JdbcAclService
        (interface)       (class)
                 ▲      ▲
                 │      │
                 └── JdbcMutableAclService
                       (class)
                         │
             DataSource / JDBC + LookupStrategy
                                    │
                            BasicLookupStrategy
                                    │
                                 AclCache
~~~

| Thành phần | Vai trò | Những operation chính |
| --- | --- | --- |
| `AclService` | Hợp đồng **đọc** ACL | `readAclById`, `readAclsById`, `findChildren` |
| `MutableAclService` | Interface **mở rộng AclService** để quản lý quyền | `createAcl`, `updateAcl`, `deleteAcl` và mọi thao tác đọc |
| `JdbcAclService` | Implementation JDBC chỉ đọc | Dùng `LookupStrategy` và `DataSource` |
| `JdbcMutableAclService` | JDBC service **đọc và ghi**, kế thừa `JdbcAclService` | Tạo/cập nhật/xóa ACL trong bốn bảng |
| `BasicLookupStrategy` | Thực thi `LookupStrategy` mặc định | Đọc ACL hiệu quả, hỗ trợ batch và cache |
| `AclCache` | Tăng tốc đọc ACL | Cache, evict và clear |
| `AclPermissionEvaluator` | Nối biểu thức `hasPermission` với `AclService` | Sử dụng ACL khi method security đánh giá quyền |

Một instance `JdbcMutableAclService` có thể được inject dưới kiểu `AclService` **hoặc** `MutableAclService`. Lớp chỉ kiểm tra quyền nên nhận `AclService`; lớp quản trị ACE nhận `MutableAclService`. Đây là cách giảm bề mặt API, **không tự thay thế** kiểm tra quyền trên endpoint cấp quyền.

### Những đối tượng mà ba API thao tác

~~~text
ObjectIdentity("demo.acl.Document", 101L)
             │
             ▼
            Acl
      ┌──────┴────────┐
      │               │
   owner SID       ACE list
                     │
                SID + Permission
                + grant/deny
                     │
                  parent ACL?
~~~

`ObjectIdentity` gồm type và ID. Nó không giống PK auto-generated của bảng `acl_object_identity`. `Acl` chứa các ACE và metadata; `MutableAcl` là ACL có thể chỉnh sửa trước khi persist.

## 3. `AclService`: chỉ đọc và đánh giá một ACL

Interface:

~~~java
import org.springframework.security.acls.model.AclService;
~~~

| Phương thức | Ý nghĩa |
| --- | --- |
| `readAclById(ObjectIdentity oid)` | Lấy ACL cho một ObjectIdentity |
| `readAclById(ObjectIdentity oid, List<Sid> sids)` | Đọc ACL với danh sách SID mà caller quan tâm |
| `readAclsById(List<ObjectIdentity> oids)` | Đọc nhiều ACL |
| `readAclsById(List<ObjectIdentity> oids, List<Sid> sids)` | Đọc nhiều ACL, hỗ trợ lookup theo SID/batch |
| `findChildren(ObjectIdentity parent)` | Tìm các object có parent ACL là object này, có thể trả `null` |

`readAclById` trả **`Acl`**, không trả `boolean`. Để quyết định quyền dùng `Acl.isGranted(...)`:

~~~java
// ĐOẠN MINH HỌA: aclService và authentication đã được cung cấp.
ObjectIdentity oid =
        new ObjectIdentityImpl("demo.acl.Document", 101L);

List<Sid> sids = new SidRetrievalStrategyImpl()
        .getSids(authentication);

Acl acl = aclService.readAclById(oid, sids);

boolean allowed = acl.isGranted(
        List.of(BasePermission.READ),
        sids,
        false);
~~~

`SidRetrievalStrategyImpl` tạo các SID ứng với principal và authorities của Authentication. `Acl.isGranted` so khớp permission + SID với ACE thực tế, theo `PermissionGrantingStrategy` và parent inheritance khi có.

**Không dùng**:

~~~java
// SAI: một ACE grant của người khác cũng khiến kết quả true.
boolean allowed = acl.getEntries().stream()
        .anyMatch(entry -> entry.isGranting());
~~~

Vì cách đó bỏ qua SID, permission, thứ tự, ACE deny và parent ACL.

### Đọc thiếu ACL, thiếu ACE và SID chưa được tải

- `readAclById` có thể ném `NotFoundException` khi chưa có ACL cho ObjectIdentity.
- `Acl.isGranted` cũng có thể ném `NotFoundException` khi ACL tồn tại nhưng không có entry đủ để đưa ra quyết định cho permission/SID đang hỏi.
- `UnloadedSidException` báo việc hỏi một SID không có trong dữ liệu ACL được tải một phần.

Khi xác minh **quyền**, thiếu ACL hoặc ACE phải dẫn tới **từ chối theo mặc định**. Nếu database lỗi hoặc có `UnloadedSidException` do lookup sai, không trả allow để “cứu” hệ thống. Cần xử lý lỗi hạ tầng riêng và giữ fail closed.

### Dùng batch đúng cách

Khi cần xét nhiều ObjectIdentity:

~~~java
// ĐOẠN MINH HỌA: các biến đã tồn tại trong service.
Map<ObjectIdentity, Acl> aclByObject =
        aclService.readAclsById(objectIdentities, sids);
~~~

`BasicLookupStrategy` có khả năng truy vấn batch; với số lượng object lớn, cách này thường giảm chi phí so với việc gọi 100 lần `readAclById`. Tuy nhiên, phải xét permission cho **từng ACL** bằng `isGranted`; một batch read không có nghĩa mọi object trong map đều được phép.

## 4. `MutableAclService`: tạo, cập nhật và xóa ACL

Interface này kế thừa `AclService` và thêm:

| Phương thức | Kết quả | Điều cần nhớ |
| --- | --- | --- |
| `createAcl(oid)` | Tạo một ACL rỗng và trả `MutableAcl` | Không phải upsert; đã tồn tại có thể ném `AlreadyExistsException` |
| `updateAcl(mutableAcl)` | Persist ACL đã thay đổi | ACL phải tồn tại trước; có thể ném `NotFoundException` |
| `deleteAcl(oid, deleteChildren)` | Xóa ACL và xử lý con tùy cờ | `deleteChildren=false` có thể ném `ChildrenExistException` |
| Các phương thức từ `AclService` | Đọc ACL như thường | Nên dùng trước khi sửa ACE |

**Quy trình tạo và cấp READ:**

~~~java
// ĐOẠN MINH HỌA trong service có quyền sửa ACL và transaction.
ObjectIdentity oid =
        new ObjectIdentityImpl("demo.acl.Document", 101L);

MutableAcl acl = mutableAclService.createAcl(oid);

acl.insertAce(
        acl.getEntries().size(),
        BasePermission.READ,
        new PrincipalSid("alice"),
        true
);

mutableAclService.updateAcl(acl);
~~~

`insertAce(index, permission, sid, granting)` **sửa ACL trong bộ nhớ**; `updateAcl` mới persist. `granting=true` là cho phép, `false` là từ chối. Một ACL vừa được tạo rỗng không tự cho owner đọc tài liệu; `Acl.getOwner()` gắn với quyền quản trị ACL theo strategy, **không đồng nghĩa** với READ/WRITE nội dung.

**Quy trình sửa ACL đã tồn tại:**

~~~java
MutableAcl acl = (MutableAcl) mutableAclService.readAclById(oid);

acl.insertAce(
        acl.getEntries().size(),
        BasePermission.WRITE,
        new GrantedAuthoritySid("ROLE_EDITOR"),
        true
);

mutableAclService.updateAcl(acl);
~~~

Nếu thu hồi một ACE, tìm đúng vị trí trong `acl.getEntries()` rồi gọi `acl.deleteAce(index)`, cuối cùng gọi `updateAcl`. Đừng xóa nhầm mọi entry vì một object có thể đang có grant khác, deny, group permission hoặc parent inheritance.

### Tính lặp lại và cạnh tranh

Một API chia sẻ tài liệu có thể nhận cùng sự kiện hai lần. Trước khi thêm ACE, nên kiểm tra quyền/SID tương ứng đã tồn tại để thao tác idempotent và tránh entry trùng. Nhưng kiểm tra trước khi insert **không tự loại bỏ race condition**: hai giao dịch cùng đọc ACL và cùng cập nhật vẫn có thể gây lost update hoặc lỗi unique/order. Dùng locking, optimistic version hoặc serialize theo ObjectIdentity khi cần.

## 5. `JdbcMutableAclService` và những phụ thuộc tối thiểu

`JdbcMutableAclService` extends `JdbcAclService` implements `MutableAclService`.

Constructor quan trọng:

~~~java
new JdbcMutableAclService(
        dataSource,
        lookupStrategy,
        aclCache);
~~~

Ba dependency:

- `DataSource`: kết nối tới database chứa ACL.
- `LookupStrategy`: chọn cách tra cứu ACL, thường là `BasicLookupStrategy`.
- `AclCache`: cache ACL đã tải.

Một instance không tự tạo schema hay tự áp dụng Method Security. Cần cấu hình database, lookup, permission strategy, ACL authorization strategy và (nếu dùng annotation) expression handler.

### Bốn bảng ACL

| Bảng | Vai trò | Cột cần hiểu |
| --- | --- | --- |
| `acl_sid` | Principal/authority SID | `id`, `principal`, `sid` |
| `acl_class` | Loại domain object | `id`, `class` |
| `acl_object_identity` | Danh tính từng object ACL, owner, parent | `object_id_class`, `object_id_identity`, `owner_sid`, `parent_object`, `entries_inheriting` |
| `acl_entry` | ACE cụ thể | `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting`, audit flags |

PK của bảng ACL khác domain object ID. Một tài liệu ID 101 có thể được tham chiếu trong cột `object_id_identity`, còn PK ACL auto-generated thuộc bảng `acl_object_identity`.

### Chọn đúng database dialect

`JdbcMutableAclService` mặc định được thiết kế với SQL/identity query cho **HSQLDB**. Nếu dùng PostgreSQL, tài liệu Spring chỉ rõ hai query nhận generated ID sau khi insert:

~~~sql
select currval(pg_get_serial_sequence('acl_class', 'id'));
select currval(pg_get_serial_sequence('acl_sid', 'id'));
~~~

Khi đó cấu hình:

~~~java
// CHỈ DÙNG CHO POSTGRESQL; các biến bean đã tồn tại.
JdbcMutableAclService jdbc =
        new JdbcMutableAclService(dataSource, lookupStrategy, aclCache);

jdbc.setClassIdentityQuery(
        "select currval(pg_get_serial_sequence('acl_class', 'id'))");
jdbc.setSidIdentityQuery(
        "select currval(pg_get_serial_sequence('acl_sid', 'id'))");
~~~

Với H2, MySQL/MariaDB, SQL Server hoặc Oracle, kiểm tra schema và identity SQL của dialect đó. Không chỉ thay JDBC URL rồi mong default HSQLDB hoạt động.

### Đặc điểm của `updateAcl` qua JDBC

Javadoc `JdbcMutableAclService.updateAcl` cho biết implementation JDBC có thể **xóa toàn bộ row ACE của ACL rồi tạo lại** theo danh sách ACE đang có. Do đó:

- Transaction cho update ACL là bắt buộc nếu cần atomicity.
- `ace_order` và thứ tự xét ACE phải được hiểu rõ.
- Hai writer đồng thời có thể ghi đè thay đổi của nhau.
- Không dựa vào PK của từng ACE như một định danh bền vững qua update.
- Cần cache invalidation, nhất là khi nhiều service instance cùng dùng dữ liệu ACL.

## 6. Ví dụ chạy được: Spring Boot + HSQLDB + JDBC ACL

Bài mẫu dùng Java 17+, Spring Boot 3.x và Spring Security 6.x. Các file Java đều ở package `demo.acl`. HSQLDB được chọn vì phù hợp với identity query và DDL mặc định được Spring Security mô tả, giúp bài tập không cần cấu hình theo PostgreSQL.

### 6.1. Gradle dependencies

Trong dự án Spring Boot Gradle đã cấu hình plugin `java`, `org.springframework.boot` và dependency management tương thích:

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

`spring-security-acl` là module riêng, không được tự suy ra đã có từ `spring-boot-starter-security`. Không cần controller/web starter cho bài kiểm thử service.

### 6.2. Datasource

**`src/main/resources/application.properties`**

~~~properties
spring.datasource.url=jdbc:hsqldb:mem:acl_demo
spring.datasource.driver-class-name=org.hsqldb.jdbc.JDBCDriver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

Spring Boot sẽ chạy `schema.sql` khi khởi tạo database. HSQLDB in-memory dành cho demo/test; production nên dùng migration quản lý bằng Flyway/Liquibase để theo dõi thay đổi schema và tránh chạy DDL lặp trên database thật.

### 6.3. ACL schema HSQLDB

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

Bốn bảng cùng các foreign keys/unique constraints là phần cốt lõi. Với `JdbcMutableAclService` mặc định, tên cột và cách lấy generated ID phải tương thích. Đừng thay `varchar_ignorecase` bằng kiểu của database khác rồi giả định vẫn là HSQLDB.

### 6.4. Spring Boot application và model

**`src/main/java/demo/acl/AclDemoApplication.java`**

~~~java
package demo.acl;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class AclDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AclDemoApplication.class, args);
    }
}
~~~

**`src/main/java/demo/acl/Document.java`**

~~~java
package demo.acl;

public record Document(long id, String title) {
}
~~~

`Document.class.getName()` sẽ là `"demo.acl.Document"`. Ví dụ tạo `ObjectIdentityImpl(Document.class.getName(), id)` để cung cấp rõ **type + ID**. Không dùng constructor nhận domain object trên Java record rồi mặc nhiên trông đợi accessor `getId()`; record ở đây có accessor `id()`.

### 6.5. Cấu hình các bean ACL

**`src/main/java/demo/acl/AclInfrastructure.java`**

~~~java
package demo.acl;

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
                new ConcurrentMapCache("aclCache"),
                permissionGrantingStrategy,
                aclAuthorizationStrategy);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache cache,
            AclAuthorizationStrategy authorizationStrategy,
            PermissionGrantingStrategy grantingStrategy) {

        return new BasicLookupStrategy(
                dataSource, cache, authorizationStrategy, grantingStrategy);
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
        handler.setPermissionEvaluator(new AclPermissionEvaluator(aclService));
        return handler;
    }
}
~~~

Các bean có nhiệm vụ khác nhau:

- `aclAuthorizationStrategy`: quyết định ai **được phép chỉnh ACL**. Authority `ACL_ADMIN` chỉ là lựa chọn minh họa, không tự đồng nghĩa READ mọi domain object.
- `permissionGrantingStrategy`: cách `Acl.isGranted` xử lý các ACE grant/deny.
- `aclCache`: cache trong một Spring Context, chưa có distributed invalidation.
- `lookupStrategy`: đọc ACL qua JDBC theo strategy mặc định.
- `aclService`: instance `JdbcMutableAclService` vừa đọc vừa ghi.
- `methodSecurityExpressionHandler`: nối `AclPermissionEvaluator` để SpEL `hasPermission` dùng `AclService`; bean static giúp cấu hình handler sớm theo Spring docs.

Bộ imports ở đây có chủ đích: `AclPermissionEvaluator` nằm trong package `org.springframework.security.acls`, còn `AclAuthorizationStrategy` ở `org.springframework.security.acls.domain`. Đây là hai package **khác** `org.springframework.security.acls.model`.

### 6.6. Service tạo, grant, revoke, kiểm tra và xóa ACL

**`src/main/java/demo/acl/DocumentAclService.java`**

~~~java
package demo.acl;

import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.SidRetrievalStrategyImpl;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.Sid;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentAclService {
    private final AclService reader;
    private final MutableAclService writer;

    public DocumentAclService(AclService reader, MutableAclService writer) {
        this.reader = reader;
        this.writer = writer;
    }

    private ObjectIdentity documentId(long id) {
        return new ObjectIdentityImpl(Document.class.getName(), id);
    }

    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    @Transactional
    public void grantReadToPrincipal(long id, String principal) {
        grantRead(id, new PrincipalSid(principal));
    }

    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    @Transactional
    public void grantReadToAuthority(long id, String authority) {
        grantRead(id, new GrantedAuthoritySid(authority));
    }

    private void grantRead(long id, Sid sid) {
        ObjectIdentity oid = documentId(id);
        MutableAcl acl;

        try {
            acl = (MutableAcl) writer.readAclById(oid);
        }
        catch (NotFoundException missing) {
            acl = writer.createAcl(oid);
        }

        boolean alreadyGranted = acl.getEntries().stream().anyMatch(ace ->
                ace.getSid().equals(sid)
                && ace.getPermission().getMask() == BasePermission.READ.getMask()
                && ace.isGranting());

        if (!alreadyGranted) {
            acl.insertAce(
                    acl.getEntries().size(),
                    BasePermission.READ, sid, true);
            writer.updateAcl(acl);
        }
    }

    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    @Transactional
    public void revokeReadFromPrincipal(long id, String principal) {
        MutableAcl acl;
        try {
            acl = (MutableAcl) writer.readAclById(documentId(id));
        }
        catch (NotFoundException missing) {
            return;
        }

        Sid sid = new PrincipalSid(principal);
        boolean changed = false;

        for (int i = acl.getEntries().size() - 1; i >= 0; i--) {
            var ace = acl.getEntries().get(i);
            if (ace.getSid().equals(sid)
                    && ace.getPermission().getMask() == BasePermission.READ.getMask()
                    && ace.isGranting()) {
                acl.deleteAce(i);
                changed = true;
            }
        }

        if (changed) {
            writer.updateAcl(acl);
        }
    }

    @PreAuthorize("hasAuthority('ACL_ADMIN')")
    @Transactional
    public void deleteAcl(long id) {
        writer.deleteAcl(documentId(id), false);
    }

    public boolean canRead(long id, Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        List<Sid> sids =
                new SidRetrievalStrategyImpl().getSids(authentication);

        try {
            Acl acl = reader.readAclById(documentId(id), sids);
            return acl.isGranted(
                    List.of(BasePermission.READ), sids, false);
        }
        catch (NotFoundException noAclOrNoAce) {
            return false;
        }
    }
}
~~~

Đoạn service cho thấy **cả hai interface được dùng đúng vai trò**:

1. `writer` có API `createAcl`/`updateAcl`/`deleteAcl`; `reader` chỉ đọc.
2. Phương thức public grant/revoke có `@PreAuthorize("hasAuthority('ACL_ADMIN')")`; người không có authority không được phép cấp quyền.
3. Transaction bao quanh phần thay đổi, còn helper private chỉ làm logic bên trong; không kỳ vọng annotation riêng của một private method được Spring AOP xử lý.
4. `createAcl` được gọi khi không tìm thấy ACL; `insertAce` là thay đổi trong RAM; `updateAcl` persist.
5. Khi retry cùng grant, ví dụ không thêm một ACE `READ:grant` trùng SID. Nếu có ACE deny xung đột, việc xử lý phải theo chính sách riêng, không tự xóa deny.
6. Thu hồi grant của principal không thu hồi grant qua role hoặc ACL cha. Muốn quyết định cuối cùng là deny, phải xét toàn bộ các nguồn cấp quyền.
7. `canRead` lấy SIDs từ Authentication và hỏi `Acl.isGranted`; missing ACL/missing ACE được xử lý thành false.

Trong ứng dụng thật, chỉ nhận Authentication từ security context đã được xác thực; không cho request body tự tạo Authentication. Việc truyền Authentication như tham số ở bài mẫu nhằm tạo test riêng cho Alice và Bob dễ dàng.

### 6.7. Dùng ACL qua `hasPermission`

**`src/main/java/demo/acl/DocumentReader.java`**

~~~java
package demo.acl;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentReader {

    @PreAuthorize(
            "hasPermission(#id, 'demo.acl.Document', 'READ')")
    public String read(@P("id") long id) {
        // Minh họa; production phải tải document thật và kiểm tra tenant/state.
        return "document:" + id;
    }
}
~~~

Biểu thức ba đối số `hasPermission(#id, 'demo.acl.Document', 'READ')` sử dụng overload nhận **ID + type** của `AclPermissionEvaluator`; handler ở mục 6.5 đã kết nối evaluator với JDBC AclService. `@P("id")` tránh phụ thuộc compiler flags khi đọc tên tham số.

Service mẫu chưa có repository tài liệu nghiệp vụ nên chỉ trả một chuỗi. **ACL là một ranh giới quyền**, không thay cho kiểm tra tài liệu tồn tại, tenant đúng và dữ liệu vẫn hợp lệ tại thời điểm truy vấn/ghi.

## 7. Integration tests với Spring Context và database thật

Các tests dùng HSQLDB đã khởi tạo schema, Spring Method Security proxy và `@WithMockUser`; không chỉ giả lập bằng một `Map` tự viết.

**`src/test/java/demo/acl/DocumentAclIntegrationTest.java`**

~~~java
package demo.acl;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.AlreadyExistsException;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(classes = AclDemoApplication.class)
class DocumentAclIntegrationTest {

    @Autowired DocumentAclService documentAcl;
    @Autowired DocumentReader documentReader;
    @Autowired AclService reader;
    @Autowired MutableAclService writer;

    private Authentication user(String name, String... authorities) {
        List<SimpleGrantedAuthority> granted =
                java.util.Arrays.stream(authorities)
                        .map(SimpleGrantedAuthority::new)
                        .toList();
        return new UsernamePasswordAuthenticationToken(
                name, "demo-only", granted);
    }

    private ObjectIdentity oid(long id) {
        return new ObjectIdentityImpl(Document.class.getName(), id);
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void createReadAndRevokePrincipalGrant() {
        assertFalse(documentAcl.canRead(101L, user("alice")));

        documentAcl.grantReadToPrincipal(101L, "alice");
        assertTrue(documentAcl.canRead(101L, user("alice")));
        assertFalse(documentAcl.canRead(101L, user("bob")));

        // Cùng request chạy lại không tạo ACE grant trùng.
        documentAcl.grantReadToPrincipal(101L, "alice");
        Acl acl = reader.readAclById(oid(101L));
        assertEquals(1, acl.getEntries().size());

        documentAcl.revokeReadFromPrincipal(101L, "alice");
        assertFalse(documentAcl.canRead(101L, user("alice")));
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void grantToAuthorityAppliesToMultipleUsers() {
        documentAcl.grantReadToAuthority(202L, "ROLE_REVIEWER");

        assertTrue(documentAcl.canRead(
                202L, user("alice", "ROLE_REVIEWER")));
        assertTrue(documentAcl.canRead(
                202L, user("bob", "ROLE_REVIEWER")));
        assertFalse(documentAcl.canRead(
                202L, user("carol", "ROLE_VIEWER")));
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void createAclIsNotAnUpsert() {
        writer.createAcl(oid(303L));
        assertThrows(AlreadyExistsException.class,
                () -> writer.createAcl(oid(303L)));
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void deleteAclRemovesPersistedRecord() {
        documentAcl.grantReadToPrincipal(404L, "alice");
        assertTrue(documentAcl.canRead(404L, user("alice")));

        documentAcl.deleteAcl(404L);
        assertThrows(NotFoundException.class,
                () -> reader.readAclById(oid(404L)));
    }

    @Test
    @WithMockUser(username = "acl-admin", authorities = "ACL_ADMIN")
    void permissionEvaluatorProtectsMethod() {
        assertThrows(AccessDeniedException.class,
                () -> documentReader.read(505L));

        documentAcl.grantReadToPrincipal(505L, "acl-admin");
        assertEquals("document:505", documentReader.read(505L));
    }

    @Test
    @WithMockUser(username = "mallory", authorities = "DOC_READ")
    void userWithoutAclAdminCannotGrant() {
        assertThrows(AccessDeniedException.class,
                () -> documentAcl.grantReadToPrincipal(606L, "mallory"));

        assertThrows(NotFoundException.class,
                () -> reader.readAclById(oid(606L)));
    }
}
~~~

**Tại sao phải có integration tests?** Unit test của một policy class không chứng minh JDBC ACL schema, cache, expression handler hay AOP proxy được nối đúng. Với Spring Context, các test trên kiểm tra grant/revoke thật, ID theo object, quyền role/cá nhân, tạo trùng, xóa, và một lời gọi `@PreAuthorize` thực tế.

Các bài test dùng ID khác nhau (101/202/303/404/505/606) để không vô tình phụ thuộc thứ tự chạy. Với production DB, cần test thêm transaction isolation và khả năng thu hồi khi nhiều node dùng cache.

### Chạy test

Trên macOS/Linux:

~~~text
./gradlew test --tests demo.acl.DocumentAclIntegrationTest
~~~

Trên Windows:

~~~text
gradlew.bat test --tests demo.acl.DocumentAclIntegrationTest
~~~

Mã ví dụ không in `System.out.println` nên không có stdout nghiệp vụ cố định. Thành công nghĩa là tất cả assertion đạt và Gradle hoàn thành task test. Với thay đổi version Spring Boot/Security hoặc database dialect, biên dịch và chạy lại các test trước khi dùng cấu hình vào production.

## 8. Xây vòng đời ACL cùng vòng đời tài nguyên

Một hệ thống thực không nên tạo ACL trong controller bằng một loạt lệnh rời rạc thiếu transaction:

~~~text
Controller / Consumer (đã xác thực)
                  |
                  v
        DocumentApplicationService
                  |
              transaction
                  |
            +-----+------+
            |            |
     DocumentRepository  MutableAclService
            |            |
       domain tables   acl_sid, acl_class,
                       acl_object_identity,
                       acl_entry
~~~

**Khi tạo tài liệu:** xác minh user được tạo, persist Document để lấy ID, tạo ObjectIdentity, gọi `createAcl`, thêm ACE theo chính sách và `updateAcl` trong cùng transaction phù hợp. Nếu một trong các bước lỗi, rollback để tránh tài liệu không có ACL hoặc ACL trỏ tới object chưa tạo.

**Khi chia sẻ:** xác minh actor có quyền chia sẻ **đúng tài liệu** và recipient hợp lệ, đọc ACL hiện tại, thêm ACE tương ứng, persist, audit và xử lý cache.

**Khi thu hồi:** tìm đúng ACE, xóa hoặc đặt deny theo nghiệp vụ, cập nhật ACL và kiểm tra còn quyền qua role/parent inheritance không. Xóa grant trực tiếp không có nghĩa user mất mọi quyền nếu ACL cha vẫn cấp.

**Khi xóa:** xem các ACL con, chọn giá trị `deleteChildren` có chủ đích, xóa ACL/document trong transaction, loại bỏ cache và các reference còn lại.

## 9. Parent ACL, ACE order và quyền sở hữu ACL

### Parent và inheritance

ACL có thể có parent, ví dụ thư mục và tài liệu con:

~~~text
Folder#8 ACL
  ROLE_REVIEWER → READ:grant
       |
       | parent
       v
Document#202 ACL
  entriesInheriting = true
~~~

Con chỉ kế thừa entry từ cha khi cờ `entriesInheriting` và chiến lược lookup cho phép. Nếu con đã có ACE cụ thể phù hợp, `PermissionGrantingStrategy` có thể đưa ra quyết định trước khi kiểm tra parent. Không suy ra “admin được đọc mọi con” từ việc admin được phép quản trị ACL cha.

### Thứ tự và deny

`DefaultPermissionGrantingStrategy` đánh giá các permission và SID theo thứ tự, xét ACE grant/deny và có thể tiếp tục parent nếu chưa đủ kết luận. Không đơn giản hóa thành “có ít nhất một grant thì allow” hoặc “mọi deny đều thắng bất kể thứ tự”. Khi principal vừa có SID user vừa có SID role, phải test case ACE chồng lấn theo strategy thật.

### Owner ACL không phải READ owner

`Acl.getOwner()` ghi nhận SID có quyền sở hữu/quản trị ACL theo strategy. Nó không tự bảo đảm `Acl.isGranted(READ, ...)` trả true cho owner. Nếu nghiệp vụ yêu cầu owner đọc tài liệu, phải đưa điều kiện đó vào chính sách hoặc cấp ACE tương ứng.

## 10. Cache, lookup và performance

### Tại sao cần `BasicLookupStrategy`?

`JdbcAclService` ủy quyền việc tra cứu cho `LookupStrategy`. `BasicLookupStrategy` sử dụng truy vấn SQL, batch và `AclCache` để tránh mỗi lần kiểm tra lại dựng toàn bộ ACL không cần thiết.

Khi kiểm tra nhiều ObjectIdentity:

~~~java
// Minh họa khi reader, objectIdentities và sids đã tồn tại.
Map<ObjectIdentity, Acl> found =
        reader.readAclsById(objectIdentities, sids);
~~~

Dù dùng batch, vẫn phải gọi `isGranted` trên **đúng** ObjectIdentity. Với phân trang và khối lượng rất lớn, cân nhắc truy vấn quyền ngay tại repository thay vì tải hàng chục nghìn object rồi hậu lọc.

### Cache invalidation

Giả sử node A cache ACL có READ cho Alice, node B xóa ACE trong database; nếu cache node A chưa invalid, Alice có thể tạm thời vẫn được grant. `JdbcMutableAclService` quản lý invalidation của cache mà nó biết, nhưng **không tự bảo đảm** mọi node hoặc application khác nhận thay đổi.

Một hệ thống phân tán cần cache invalidation/version/TTL phù hợp, và chiến lược cập nhật auth session/JWT khi role membership thay đổi. Không nhầm “DB đã thay” với “mọi request đều lập tức nhìn thấy quyền mới”.

### Transaction không tự chống lost update

`updateAcl` theo implementation JDBC có thể xóa và ghi lại toàn bộ ACE. Nếu hai quản trị viên cùng đọc ACL cũ rồi cập nhật theo hai snapshot khác nhau, kết quả một người có thể bị người kia ghi đè. `@Transactional` bảo vệ atomicity của **một** lần ghi nhưng không tự đảm bảo serialization giữa hai writers. Cân nhắc locking, versioning và kiểm tra retry ở tầng use case.

## 11. Multi-tenant, audit và ranh giới bảo mật

### Multi-tenant

`ObjectIdentityImpl("demo.acl.Document", 101L)` chỉ gồm type và ID. Nếu tenant A/B có hai document cùng ID 101 trong database riêng, không được dùng chung bảng ACL mà không phân vùng danh tính một cách rõ ràng. Tương tự `PrincipalSid("alice")` không tự chứa tenant. Một người trùng username ở tenant khác có thể khớp SID nếu cách cấu hình principal không đảm bảo uniqueness.

Dùng user ID bất biến toàn cục, resource ID định danh duy nhất hoặc phân vùng ACL theo tenant, và luôn xét tenant từ nguồn đã xác thực. Không coi tenant trong HTTP header tự khai là nguồn tin cậy.

### Quyền quản trị ACL và escalation

Một user có `READ` trên document không nên được gọi API `grantReadToAuthority` để cấp quyền cho toàn bộ nhóm nếu nghiệp vụ chưa cho phép. `@PreAuthorize("hasAuthority('ACL_ADMIN')")` ở ví dụ chỉ minh họa một chốt; production có thể yêu cầu actor vừa là admin tenant, vừa có quyền chia sẻ đúng ObjectIdentity, vừa không cấp permission vượt mức.

Thêm audit: ai cấp, cho ai, object nào, permission gì, từ thời điểm nào, transaction id và kết quả. Không log token hay dữ liệu nhạy cảm khi báo cáo quyền.

### Quyền trong ACL và policy nghiệp vụ có thể khác nhau

Một ACL có `READ:grant` nhưng document đang bị khóa pháp lý, bị xóa hoặc đang ở tenant khác thì ứng dụng vẫn có thể cần từ chối. `Acl.isGranted` trả lời theo ACE, không tự biết mọi invariant của document. Ngược lại, `@PostAuthorize` kiểm tra sau thân method nên không bảo vệ được side effect đã xảy ra.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Lỗi `Table not found: ACL_SID` | Chưa chạy schema, sai datasource | Kiểm tra `schema.sql` và migration |
| `call identity()` lỗi trên PostgreSQL/H2 | Dùng default query dành cho HSQLDB | Đặt identity query theo dialect và schema |
| `AlreadyExistsException` khi tạo ACL | ObjectIdentity đã có ACL | Đọc và cập nhật, hoặc xử lý race có kiểm soát |
| `NotFoundException` khi đọc | Không có ACL hoặc sai type/ID | Fail closed, kiểm tra lifecycle |
| `NotFoundException` khi `isGranted` | ACL có nhưng không có ACE phù hợp | Không trả allow; kiểm tra đúng SID/mask |
| `UnloadedSidException` | Lookup chỉ tải subset SID | Tải đủ SID và kiểm tra strategy |
| Grant rồi không có quyền | Quên `updateAcl`, dùng sai SID hoặc mask | Persist rồi readback và test `isGranted` |
| Revoke user nhưng còn READ | Có role grant hoặc parent inheritance | Tính toàn bộ nguồn cấp quyền |
| `hasPermission` không chạy | Chưa bật Method Security hoặc thiếu handler | `@EnableMethodSecurity` và `AclPermissionEvaluator` |
| User thiếu quyền sửa vẫn thay ACL | Endpoint quản trị không có chốt hoặc gọi ngoài proxy | Bảo vệ public service method, test denied |
| Cache vẫn giữ quyền cũ | Invalidation thiếu, nhiều node | Evict/broadcast/version theo hệ thống |
| Hai writers làm mất ACE | Race/lost update ở `updateAcl` | Transaction + locking/version |
| Xóa ACL cha bị lỗi | Child ACL tồn tại | Xem `ChildrenExistException` và cây ACL |
| HSQLDB test pass nhưng production fail | Dialect/SQL isolation khác | Chạy integration test trên DB đích |
| Người khác tenant nhận quyền | SID/ObjectIdentity không phân biệt tenant | ID toàn cục hoặc ACL partition |
| Tạo document nhưng chưa có ACL | Vòng đời domain và ACL không chung transaction | Dùng application service và rollback phù hợp |

## 13. Checklist review và bài tập

Trước khi hoàn thành triển khai:

1. Schema ACL đủ bốn bảng, FK, unique constraints, index và identity đúng database chưa?
2. `JdbcMutableAclService` được cấu hình với `DataSource`, `BasicLookupStrategy` và `AclCache` đúng chưa?
3. Có test `createAcl`/`updateAcl`/`deleteAcl` và `readAclById`/`readAclsById` chưa?
4. Chỉ nơi quản trị mới inject `MutableAclService` và actor được kiểm tra trước khi thay quyền chưa?
5. Có xử lý thiếu ACL, thiếu ACE bằng deny thay vì allow chưa?
6. Có phân biệt `PrincipalSid` và `GrantedAuthoritySid` chưa?
7. Có kiểm tra role prefix, tenant, ObjectIdentity type và ID không?
8. Có test ACL inheritance, deny, xóa parent và revocation chưa?
9. `updateAcl` có được bảo vệ bởi transaction và chiến lược concurrency không?
10. Cache/invalidation có hoạt động giữa nhiều node không?
11. `@PreAuthorize("hasPermission(...)")` có test người thiếu quyền qua proxy thật không?
12. Chính sách ACL có phối hợp với trạng thái document và SQL transaction thực tế không?

**Bài tập 1:** Thêm `grantWriteToPrincipal` cho `BasePermission.WRITE`. Test alice chỉ READ không tự có WRITE, và user có WRITE không tự có DELETE.

**Bài tập 2:** Cho Bob có `ROLE_REVIEWER`, thêm ACE READ theo authority trên Document#707. Chứng minh reviewer khác cũng có thể đọc đúng object đó nhưng không đọc Document#101.

**Bài tập 3:** Thêm một deny ACE cho Alice trên object đã có grant role. Test bằng `Acl.isGranted` và thay thứ tự SID/ACE để quan sát strategy thật. Không dùng `anyMatch` để giả làm kết quả.

**Bài tập 4:** Tạo ACL cha cho Folder#8 và ACL con cho Document#808. Bật/tắt `entriesInheriting`, thử `deleteAcl(parent,false)`, giải thích khi nào cần `deleteChildren=true`.

**Bài tập 5:** Chạy integration tests trên PostgreSQL bằng Testcontainers, thay `schema.sql` và identity queries. Đặc biệt kiểm tra create/update/revoke và rollback khi SQL lỗi.

**Bài tập 6:** Chạy hai transaction đồng thời để update cùng ObjectIdentity. Thêm version hoặc khóa, bảo đảm không làm mất ACE từ writer còn lại.

**Bài tập 7:** Thiết kế ACL cho hai tenant có trùng username và document ID. Đưa ra ID/SID strategy ngăn đọc chéo; kiểm thử cả quyền cá nhân và quyền nhóm.

**Tiêu chí hoàn thành:** giải thích được sự khác biệt giữa hợp đồng đọc, hợp đồng mutation và implementation JDBC; nối đúng DataSource/LookupStrategy/AclCache; tạo, cập nhật và đọc ACL thực; áp dụng `Acl.isGranted` hoặc `hasPermission` để ra quyết định; fail closed với missing ACL/ACE; hiểu giới hạn transaction, cache, tenant và JDBC dialect.

## Tài liệu tham khảo chính thức

- Spring Security – Domain Object Security (ACLs), thành phần và cấu hình JDBC: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html
- Spring Security – Database Schema, DDL HSQLDB và SQL PostgreSQL: https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html
- Spring Security – AclService API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/AclService.html
- Spring Security – MutableAclService API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/MutableAclService.html
- Spring Security – JdbcMutableAclService API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html
- Spring Security – BasicLookupStrategy API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/BasicLookupStrategy.html
- Spring Security – AclPermissionEvaluator API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/AclPermissionEvaluator.html
