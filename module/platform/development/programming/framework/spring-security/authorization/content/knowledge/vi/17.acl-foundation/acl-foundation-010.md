# Thư viện ACL, DataSource và các thành phần cấu hình cần thiết

## 1. Giải quyết bài toán gì?

Trong một ứng dụng có nhiều tài liệu, dự án, hợp đồng hoặc hồ sơ, `ROLE_EDITOR` không đủ để kết luận người dùng được sửa **mọi** tài liệu. Cần một cơ chế gắn quyền với **từng đối tượng**: Alice được đọc Document #42, Bob bị từ chối đọc Document #42, còn thành viên nhóm REVIEWER được đọc nhưng không được xóa.

**Spring Security Access Control List (ACL)** cung cấp hạ tầng để lưu và kiểm tra các quy tắc đó. Muốn chạy được ACL trong Spring Boot, bạn cần nhiều hơn annotation `@PreAuthorize`: thư viện `spring-security-acl`, JDBC `DataSource`, bốn bảng cơ sở dữ liệu, `LookupStrategy`, `AclService`, `AclCache`, hai chiến lược kiểm soát và `AclPermissionEvaluator` được đăng ký với method-security expression handler.

Sau bài học thuộc nhóm **Nền tảng ACL**, bạn sẽ biết:

1. Thư viện nào cung cấp API ACL và dependency nào tạo `DataSource`/transaction.
2. Vì sao phải có **bốn bảng** `acl_sid`, `acl_class`, `acl_object_identity`, `acl_entry`.
3. Cách nối `JdbcMutableAclService`, `BasicLookupStrategy`, `SpringCacheBasedAclCache`, `AclAuthorizationStrategy` và `PermissionGrantingStrategy`.
4. Cách cấu hình `AclPermissionEvaluator` cho `hasPermission(...)` trong `@PreAuthorize`.
5. Vì sao truy vấn lấy ID mới và schema khác nhau giữa HSQLDB/PostgreSQL.
6. Cách test bằng Java 17+, HSQLDB và Spring Security thật qua proxy — không chỉ test một bean được khởi tạo.
7. Những rủi ro production: nhiều nguồn dữ liệu, quyền quản trị ACL, N+1 query, invalidation cache và mất đồng bộ khi xóa tài nguyên.

**Phiên bản minh họa:** Spring Boot 3.5.0, Spring Security 6.5.x, Java 17+, Gradle. Các ví dụ Java test phía dưới là mã đầy đủ để chạy trong project thử, nhưng phần kết quả được ghi là **kỳ vọng**, không phải log đã thực thi.

## 2. Sơ đồ toàn bộ đường gọi

Dòng **đọc quyền** khi service dùng `@PreAuthorize`:

```text
Caller
  |
  v
Spring-managed bean qua AOP proxy
  |
  v
@PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
  |
  v
PreAuthorizeAuthorizationManager
  |
  v
DefaultMethodSecurityExpressionHandler
  |
  v
AclPermissionEvaluator
  |
  v
AclService = JdbcMutableAclService hoặc JdbcAclService
  |
  v
LookupStrategy = BasicLookupStrategy ----> AclCache
  |
  v
DataSource ---> SQL ---> acl_sid / acl_class
                      acl_object_identity / acl_entry
  |
  v
Acl + PermissionGrantingStrategy
  |
  +--> ALLOW: chạy thân phương thức
  +--> DENY: không chạy thân phương thức; AccessDeniedException
```

Dòng **ghi quyền**:

```text
Service quản trị ACL đã kiểm tra authorization
  |
  v
MutableAclService = JdbcMutableAclService
  |
  +-- createAcl(ObjectIdentity)
  +-- MutableAcl.insertAce(index, Permission, Sid, granting)
  +-- updateAcl(MutableAcl)
  +-- deleteAcl(ObjectIdentity, deleteChildren)
  |
  v
DataSource + transaction ---> bảng ACL
  |
  v
Cache được cập nhật / evict theo cơ chế triển khai
```

Spring Security không mặc nhiên tạo ACL cho mọi entity vừa được thêm vào database. **Lifecycle tạo, chia sẻ, thu hồi quyền và xóa ACL phải do ứng dụng thiết kế**.

## 3. Các thành phần và trách nhiệm riêng

| Thành phần | Implementation thường dùng | Nhiệm vụ |
| --- | --- | --- |
| ACL model | `Acl`, `MutableAcl`, `ObjectIdentity`, `Sid`, `Permission`, `AccessControlEntry` | Biểu diễn tài nguyên, người/nhóm và các ACE grant/deny |
| ACL read API | `AclService` | Tải ACL của một hoặc nhiều `ObjectIdentity` |
| ACL read JDBC | `JdbcAclService` | Dùng JDBC và `LookupStrategy` để đọc |
| ACL write API | `MutableAclService` | Tạo, sửa, xóa ACL/ACE |
| ACL read/write JDBC | `JdbcMutableAclService` | Triển khai cả `AclService` lẫn `MutableAclService` |
| Truy vấn ACL | `LookupStrategy`, `BasicLookupStrategy` | Tải, xây dựng và batch lookup ACL từ DB |
| Cache ACL | `AclCache`, `SpringCacheBasedAclCache` | Cache ACL theo ID, giảm đọc DB |
| Chiến lược sửa ACL | `AclAuthorizationStrategy` | Kiểm soát quyền quản trị/sửa ACL |
| Chiến lược quyết định ACE | `PermissionGrantingStrategy` | Áp dụng các quy tắc grant/deny |
| Tích hợp expression | `AclPermissionEvaluator` | Kiểm tra `hasPermission` |
| Method Security | `MethodSecurityExpressionHandler` | Cấp evaluator vào ngữ cảnh SpEL |
| Connection | `javax.sql.DataSource` | Kết nối đến database chứa bảng ACL |

**Hai chiến lược tuyệt đối không nhầm:** `AclAuthorizationStrategy` không phải là quyền `READ` tài liệu. Một user có `ROLE_ACL_ADMIN` được thiết kế cho mục đích quản lý ACL vẫn có thể **không có ACE READ** để xem tài liệu. Việc cho ai sửa ACL phải được bảo vệ độc lập với việc họ được làm gì trên tài nguyên.

`JdbcMutableAclService` kế thừa `JdbcAclService`, nên khi đã đăng ký mutable JDBC service cho một DataSource, bạn không bắt buộc đăng ký thêm một `JdbcAclService` đọc riêng. Inject theo interface `AclService` trong service chỉ cần đọc; inject `MutableAclService` ở tác vụ quản trị.

## 4. Thư viện và dependencies

### 4.1. Gradle với Spring Boot

Trong dự án Spring Boot đang sử dụng BOM/plugin phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.security:spring-security-acl'

    // Driver production chỉ khi dùng PostgreSQL:
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.hsqldb:hsqldb'
}
```

Đây là **fragment `build.gradle`**, không phải project đầy đủ.

- `spring-security-acl`: chứa `Acl`, `JdbcMutableAclService`, `BasicLookupStrategy`, các strategy, `AclPermissionEvaluator`.
- `spring-boot-starter-security`: chứa hạ tầng authentication, authorization và method-security config. **Không bao gồm toàn bộ ACL module theo mặc định**.
- `spring-boot-starter-jdbc`: Spring JDBC, `DataSource`, connection pool và transaction infrastructure. Không cần JPA `EntityManager` để dùng ACL JDBC.
- `org.postgresql:postgresql`: chỉ dành cho PostgreSQL; nếu dự án dùng MySQL/MariaDB/SQL Server/Oracle, thay driver thích hợp.
- `spring-security-test`: cung cấp `@WithMockUser` và các tiện ích test security.
- `org.hsqldb:hsqldb`: database embedded để chạy test đúng với JDBC ACL default SQL.

Nếu không dùng Spring Boot, bạn phải tự tạo `DataSource`, transaction manager, dependency Spring JDBC/Context/Security và quản lý version. Nếu dùng Boot, hãy giữ **cùng dòng version** cho mọi module Spring Security; không ép version của `spring-security-acl` khác `spring-security-config` đang được BOM quản lý.

### 4.2. Maven tương đương

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-acl</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
  </dependency>
  <dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
  </dependency>
</dependencies>
```

Fragment này **giả định có Spring Boot parent hoặc dependencyManagement/BOM**. Không copy trần vào POM không quản lý version rồi kỳ vọng Maven tự tìm các version tương thích.

## 5. DataSource và bốn bảng ACL bắt buộc

Spring Security ACL dùng **bốn bảng JDBC chuẩn**:

| Bảng | Vai trò | Khóa/thuộc tính quan trọng |
| --- | --- | --- |
| `acl_sid` | Principal hoặc authority | `id`, `principal`, `sid`, unique theo cặp principal/sid |
| `acl_class` | Loại đối tượng | `id`, `class`, unique theo tên loại |
| `acl_object_identity` | Một tài nguyên cụ thể | `object_id_class`, `object_id_identity`, `owner_sid`, `parent_object`, `entries_inheriting` |
| `acl_entry` | Các ACE cho đối tượng | `acl_object_identity`, `ace_order`, `sid`, `mask`, `granting`, `audit_success`, `audit_failure` |

Quan hệ:

```text
acl_class 1 ---- * acl_object_identity 1 ---- * acl_entry
                           |                       |
                     parent_object                 sid
                     owner_sid                     |
                           |                       v
                           +------------------> acl_sid
```

**Object ID khác ACL row ID.** Với Document có primary key 42, một hàng `acl_object_identity` có thể có PK 100, tham chiếu type `demo.Document`, và chứa `object_id_identity='42'`. SID Alice, Bob và ROLE_REVIEWER lại là các hàng khác nhau trong `acl_sid`. Không dùng mask READ=1 để suy ra ID tài liệu.

### 5.1. Schema HSQLDB để chạy được demo

Spring Security cung cấp schema mẫu theo từng database. **HSQLDB** được chọn ở đây vì các truy vấn generated-key mặc định của `JdbcMutableAclService` dùng `call identity()` phù hợp HSQLDB. Tạo `src/test/resources/schema.sql`:

```sql
CREATE TABLE acl_sid (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    principal BOOLEAN NOT NULL,
    sid VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT uq_acl_sid UNIQUE (sid, principal)
);

CREATE TABLE acl_class (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    class VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT uq_acl_class UNIQUE (class)
);

CREATE TABLE acl_object_identity (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    object_id_class BIGINT NOT NULL,
    object_id_identity VARCHAR_IGNORECASE(36) NOT NULL,
    parent_object BIGINT,
    owner_sid BIGINT,
    entries_inheriting BOOLEAN NOT NULL,
    CONSTRAINT uq_acl_object UNIQUE (object_id_class, object_id_identity),
    CONSTRAINT fk_acl_object_class
        FOREIGN KEY (object_id_class) REFERENCES acl_class(id),
    CONSTRAINT fk_acl_object_parent
        FOREIGN KEY (parent_object) REFERENCES acl_object_identity(id),
    CONSTRAINT fk_acl_object_owner
        FOREIGN KEY (owner_sid) REFERENCES acl_sid(id)
);

CREATE TABLE acl_entry (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 100)
        NOT NULL PRIMARY KEY,
    acl_object_identity BIGINT NOT NULL,
    ace_order INTEGER NOT NULL,
    sid BIGINT NOT NULL,
    mask INTEGER NOT NULL,
    granting BOOLEAN NOT NULL,
    audit_success BOOLEAN NOT NULL,
    audit_failure BOOLEAN NOT NULL,
    CONSTRAINT uq_acl_entry UNIQUE (acl_object_identity, ace_order),
    CONSTRAINT fk_acl_entry_object
        FOREIGN KEY (acl_object_identity) REFERENCES acl_object_identity(id),
    CONSTRAINT fk_acl_entry_sid
        FOREIGN KEY (sid) REFERENCES acl_sid(id)
);
```

Schema giữ đủ cột và ràng buộc cốt lõi theo phần **ACL Schema** trong tài liệu Spring Security 6.5. `VARCHAR_IGNORECASE` và cú pháp identity trên là **theo HSQLDB**, không phải DDL dùng chung mọi hệ quản trị.

**Lưu ý thực tế:**

- Production dùng Flyway/Liquibase/migration riêng; không cấu hình schema khởi tạo lại và làm mất dữ liệu ACL sau mỗi lần deploy.
- Nếu DB có schema/search path riêng, đặt đúng namespace cho các bảng hoặc điều chỉnh SQL/connection configuration nhất quán.
- Bảo đảm foreign key, unique index và `ace_order` để không ghi trùng ACE hoặc lẫn đối tượng.
- Khởi tạo bảng ACL **khác** với bảng `users`, `authorities` của `JdbcUserDetailsManager`; hai nhóm bảng có chức năng khác nhau.
- Thiết kế xóa ACL khi xóa domain object hoặc thay ownership; Spring Security không tự đồng bộ ACL với vòng đời ORM/DAO của bạn.

### 5.2. Truy vấn lấy ID vừa chèn phụ thuộc dialect

`JdbcMutableAclService` phải lấy ID mới sau khi insert `acl_class` và `acl_sid`. Hai thuộc tính:

- `classIdentityQuery`, mặc định `call identity()`.
- `sidIdentityQuery`, mặc định `call identity()`.

Với **PostgreSQL**, tài liệu Spring Security hướng dẫn:

```java
JdbcMutableAclService service =
    new JdbcMutableAclService(dataSource, lookupStrategy, aclCache);

service.setClassIdentityQuery(
    "select currval(pg_get_serial_sequence('acl_class', 'id'))"
);
service.setSidIdentityQuery(
    "select currval(pg_get_serial_sequence('acl_sid', 'id'))"
);
```

Đây là **mảnh minh họa chỉ dành cho PostgreSQL**, không chạy độc lập vì `dataSource`/`lookupStrategy`/`aclCache` chưa được tạo trong snippet. Với PostgreSQL phải dùng **schema PostgreSQL** thay vì SQL HSQLDB ở trên. Với MySQL/MariaDB/SQL Server/Oracle, tra chính xác DDL/query của dialect và version đang triển khai.

Không thay bằng `SELECT MAX(id)`: trong hệ thống nhiều request, có thể lấy ID của bản ghi khác và làm sai liên kết ACL/SID. `currval(...)` của PostgreSQL phụ thuộc session hiện hành; thực thi insert và lấy ID phải dùng kết nối tương ứng.

## 6. Tạo các bean theo chuỗi phụ thuộc

Một cấu hình Spring Boot tiêu chuẩn cho ACL JDBC có các bean:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.LookupStrategy;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class AclConfiguration {

    @Bean
    static MethodSecurityExpressionHandler expressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler h =
            new DefaultMethodSecurityExpressionHandler();
        h.setPermissionEvaluator(evaluator);
        return h;
    }

    @Bean
    static AclPermissionEvaluator permissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    JdbcMutableAclService aclService(
            DataSource dataSource, LookupStrategy lookupStrategy,
            AclCache cache) {
        return new JdbcMutableAclService(
            dataSource, lookupStrategy, cache);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource, AclCache cache,
            AclAuthorizationStrategy aclAuthorizationStrategy,
            PermissionGrantingStrategy permissionGrantingStrategy) {
        return new BasicLookupStrategy(
            dataSource, cache,
            aclAuthorizationStrategy, permissionGrantingStrategy);
    }

    @Bean
    AclCache aclCache(
            PermissionGrantingStrategy permissionGrantingStrategy,
            AclAuthorizationStrategy aclAuthorizationStrategy) {
        Cache cache = new ConcurrentMapCache("aclCache");
        return new SpringCacheBasedAclCache(
            cache, permissionGrantingStrategy,
            aclAuthorizationStrategy);
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger());
    }
}
```

Đây là **class cấu hình hoàn chỉnh**, nhưng không phải một ứng dụng tự chạy: cần DataSource/driver/schema và Spring Boot app context đã được cung cấp. Đây là cách nối bean tương ứng mẫu của tài liệu chính thức Spring Security 6.5.

### 6.1. Giải thích các quyết định

- **`@EnableMethodSecurity`** bật các interceptor của `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` theo mặc định. Nếu tắt pre/post, `hasPermission` trong `@PreAuthorize` không được thực thi theo cấu hình mẫu.
- **`static @Bean MethodSecurityExpressionHandler`** công bố handler sớm trong quá trình Spring Security cấu hình Method Security. `setPermissionEvaluator(evaluator)` là bước kết nối quan trọng: nếu không nối, evaluator do bạn tạo có thể không được dùng.
- **`AclPermissionEvaluator(AclService)`** thực thi hai dạng `hasPermission(target, permission)` và `hasPermission(id, targetType, permission)`; nó cần AclService có thể đọc được bảng ACL.
- **`JdbcMutableAclService`** là đường đọc lẫn cập nhật ACL, phụ thuộc DataSource + LookupStrategy + AclCache. Nếu ứng dụng chỉ đọc ACL, `JdbcAclService` là lựa chọn gọn hơn.
- **`BasicLookupStrategy`** là phần tối ưu truy vấn và xây `Acl`, hỗ trợ cache/batch retrieval. Nó cũng cần hai chiến lược ACL.
- **`SpringCacheBasedAclCache`** dùng `ConcurrentMapCache` trong ví dụ, chỉ có tác dụng trong một JVM. Nhiều pod/instance cần kế hoạch invalidation.
- **`AclAuthorizationStrategyImpl`** hạn chế thay đổi ACL theo authority, ví dụ `ROLE_ACL_ADMIN`. Đừng cấp role này cho mọi người dùng.
- **`DefaultPermissionGrantingStrategy`** đánh giá ACE grant/deny. `ConsoleAuditLogger` chỉ là cách ghi audit đơn giản cho demo.

### 6.2. Không tạo hai bean ACL đọc trùng nhau

`JdbcMutableAclService` triển khai `AclService` và `MutableAclService`. Khi project đã dùng nó, có thể inject `AclService` vào `AclPermissionEvaluator` mà không cần tạo `JdbcAclService` khác. Nếu dùng hai DataSource, hãy đặt qualifier rõ ràng cho từng bean; việc có nhiều candidate không rõ ràng có thể làm Spring Boot startup lỗi hoặc — nguy hiểm hơn — đọc nhầm ACL database.

### 6.3. Sửa bean khi dùng PostgreSQL

Thay đúng bean `aclService(...)` trong cấu hình trên bằng:

```java
@Bean
JdbcMutableAclService aclService(
        DataSource dataSource, LookupStrategy lookupStrategy,
        AclCache cache) {
    JdbcMutableAclService service =
        new JdbcMutableAclService(dataSource, lookupStrategy, cache);
    service.setClassIdentityQuery(
        "select currval(pg_get_serial_sequence('acl_class', 'id'))");
    service.setSidIdentityQuery(
        "select currval(pg_get_serial_sequence('acl_sid', 'id'))");
    return service;
}
```

**Không khai báo đồng thời hai phương thức `@Bean aclService` trùng tên.** Ở project test HSQLDB bên dưới, giữ cấu hình mặc định; PostgreSQL là ví dụ thay thế cho môi trường khác.

## 7. Project Java 17+ tự đủ để kiểm thử hạ tầng ACL

Project dưới đây kiểm chứng:

- `DataSource` đã kết nối được cả bốn bảng.
- `JdbcMutableAclService` tạo và đọc lại ACL/ACE.
- `AclPermissionEvaluator` thực sự được method-security expression handler dùng.
- Alice được READ, Bob bị DENY, thành viên REVIEWER được READ, còn người chỉ có ACL_ADMIN không tự được READ.
- WRITE chưa grant, type khác và object không có ACL không được truy cập.
- Xóa một ACE rồi cập nhật ACL phải làm quyền vừa bị thu hồi không còn hiệu lực, ngay cả sau một lần đọc/cache.

### 7.1. Các tệp của project

```text
acl-infrastructure-demo/
├── settings.gradle
├── build.gradle
└── src/test/
    ├── java/demo/AclInfrastructureTest.java
    └── resources/schema.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'acl-infrastructure-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-acl'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.hsqldb:hsqldb'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Tệp `src/test/resources/schema.sql`:** chép nguyên toàn bộ SQL ở mục 5.1. Trong test-only project này, HSQLDB là database in-memory và Spring Boot sẽ chạy schema vì `spring.sql.init.mode=always` và `schema-locations=classpath:schema.sql` được khai báo trong test class.

### 7.2. File Java kiểm thử hoàn chỉnh

Tạo `src/test/java/demo/AclInfrastructureTest.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.AclAuthorizationStrategy;
import org.springframework.security.acls.domain.AclAuthorizationStrategyImpl;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.ConsoleAuditLogger;
import org.springframework.security.acls.domain.DefaultPermissionGrantingStrategy;
import org.springframework.security.acls.domain.GrantedAuthoritySid;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.domain.SpringCacheBasedAclCache;
import org.springframework.security.acls.jdbc.BasicLookupStrategy;
import org.springframework.security.acls.jdbc.JdbcMutableAclService;
import org.springframework.security.acls.model.Acl;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.LookupStrategy;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = AclInfrastructureTest.Config.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:schema.sql"
    }
)
@WithMockUser(username = "alice", roles = "ACL_ADMIN")
public class AclInfrastructureTest {

    private static final AtomicLong IDS = new AtomicLong(10000L);

    @Autowired DataSource dataSource;
    @Autowired JdbcMutableAclService aclService;
    @Autowired AclCache cache;
    @Autowired DocumentService documents;
    @Autowired Probe probe;

    private Long id;
    private ObjectIdentity identity;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    public static class Config {

        @Bean
        static MethodSecurityExpressionHandler expressionHandler(
                AclPermissionEvaluator evaluator) {
            DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
            handler.setPermissionEvaluator(evaluator);
            return handler;
        }

        @Bean
        static AclPermissionEvaluator evaluator(
                JdbcMutableAclService service) {
            return new AclPermissionEvaluator(service);
        }

        @Bean
        JdbcMutableAclService aclService(
                DataSource source, LookupStrategy lookup,
                AclCache aclCache) {
            return new JdbcMutableAclService(source, lookup, aclCache);
        }

        @Bean
        LookupStrategy lookup(
                DataSource source, AclCache aclCache,
                AclAuthorizationStrategy authStrategy,
                PermissionGrantingStrategy permissionStrategy) {
            return new BasicLookupStrategy(
                source, aclCache, authStrategy, permissionStrategy);
        }

        @Bean
        AclCache aclCache(
                PermissionGrantingStrategy permissionStrategy,
                AclAuthorizationStrategy authStrategy) {
            Cache springCache = new ConcurrentMapCache("aclCache");
            return new SpringCacheBasedAclCache(
                springCache, permissionStrategy, authStrategy);
        }

        @Bean
        AclAuthorizationStrategy authStrategy() {
            return new AclAuthorizationStrategyImpl(
                new SimpleGrantedAuthority("ROLE_ACL_ADMIN"));
        }

        @Bean
        PermissionGrantingStrategy permissionStrategy() {
            return new DefaultPermissionGrantingStrategy(
                new ConsoleAuditLogger());
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean DocumentService documents(Probe probe) {
            return new DocumentService(probe);
        }
    }

    public static class Probe {
        private final AtomicInteger calls = new AtomicInteger();

        void mark() { calls.incrementAndGet(); }
        int count() { return calls.get(); }
        void reset() { calls.set(0); }
    }

    public static class DocumentService {
        private final Probe probe;

        public DocumentService(Probe probe) {
            this.probe = probe;
        }

        @PreAuthorize("hasPermission(#id, 'demo.Document', 'READ')")
        public String read(@P("id") Long id) {
            probe.mark();
            return "DOC:" + id;
        }

        @PreAuthorize("hasPermission(#id, 'demo.Document', 'WRITE')")
        public String write(@P("id") Long id) {
            probe.mark();
            return "WRITTEN:" + id;
        }

        @PreAuthorize("hasPermission(#id, 'demo.Invoice', 'READ')")
        public String invoice(@P("id") Long id) {
            probe.mark();
            return "INVOICE:" + id;
        }
    }

    @BeforeEach
    void setUp() {
        id = IDS.incrementAndGet();
        identity = new ObjectIdentityImpl("demo.Document", id);
        probe.reset();

        MutableAcl acl = aclService.createAcl(identity);
        acl.insertAce(0, BasePermission.READ,
            new PrincipalSid("alice"), true);
        acl.insertAce(1, BasePermission.READ,
            new PrincipalSid("bob"), false);
        acl.insertAce(2, BasePermission.READ,
            new GrantedAuthoritySid("ROLE_REVIEWER"), true);
        aclService.updateAcl(acl);
    }

    @AfterEach
    void tearDown() {
        aclService.deleteAcl(identity, true);
    }

    @Test
    void infrastructureUsesSpringBeansAndProxy() {
        assertThat(dataSource).isNotNull();
        assertThat(aclService).isNotNull();
        assertThat(cache).isNotNull();
        assertThat(AopUtils.isAopProxy(documents)).isTrue();
    }

    @Test
    void schemaContainsFourQueryableAclTables() {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        assertThat(jdbc.queryForObject(
            "select count(*) from acl_sid", Long.class)).isNotNull();
        assertThat(jdbc.queryForObject(
            "select count(*) from acl_class", Long.class)).isNotNull();
        assertThat(jdbc.queryForObject(
            "select count(*) from acl_object_identity", Long.class))
            .isNotNull();
        assertThat(jdbc.queryForObject(
            "select count(*) from acl_entry", Long.class)).isNotNull();
    }

    @Test
    void aclIsPersistedWithThreeEntries() {
        Acl loaded = aclService.readAclById(identity);
        assertThat(loaded.getObjectIdentity()).isEqualTo(identity);
        assertThat(loaded.getEntries()).hasSize(3);
    }

    @Test
    void aliceCanReadHerGrantedDocument() {
        assertThat(documents.read(id)).isEqualTo("DOC:" + id);
        assertThat(probe.count()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "bob", roles = "ACL_ADMIN")
    void bobIsExplicitlyDeniedBeforeMethodBody() {
        assertThatThrownBy(() -> documents.read(id))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
    }

    @Test
    @WithMockUser(username = "carol", roles = {"ACL_ADMIN", "REVIEWER"})
    void reviewerAuthorityMayRead() {
        assertThat(documents.read(id)).isEqualTo("DOC:" + id);
        assertThat(probe.count()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "carol", roles = "ACL_ADMIN")
    void aclAdminRoleDoesNotAutomaticallyGrantDomainRead() {
        assertThatThrownBy(() -> documents.read(id))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
    }

    @Test
    void writeHasNoGrantAndIsDenied() {
        assertThatThrownBy(() -> documents.write(id))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
    }

    @Test
    void wrongObjectTypeCannotReuseSameIdAcl() {
        assertThatThrownBy(() -> documents.invoice(id))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
    }

    @Test
    void readForMissingAclDoesNotAllow() {
        assertThatThrownBy(() -> documents.read(id + 100000L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isZero();
    }

    @Test
    void revokeIsVisibleAfterUpdate() {
        assertThat(documents.read(id)).isEqualTo("DOC:" + id);

        MutableAcl mutable = (MutableAcl) aclService.readAclById(identity);
        mutable.deleteAce(0); // Bỏ grant READ của Alice.
        aclService.updateAcl(mutable);

        assertThatThrownBy(() -> documents.read(id))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count()).isEqualTo(1);
    }
}
```

### 7.3. Những điểm quan trọng trong test

**DataSource thật:** `@SpringBootTest` chạy Spring context với Boot auto-configuration cho embedded HSQLDB. HSQLDB nhận schema do SQL initializer chạy trước test. Đây không phải đơn thuần `new JdbcMutableAclService(...)` rồi trả mock.

**SecurityContext:** `@WithMockUser(username = "alice", roles = "ACL_ADMIN")` tạo principal Alice với `ROLE_ACL_ADMIN`, dùng để cho phép các thao tác tạo/cập nhật/xóa fixture ACL. Test Bob/Carol ghi đè username và role cho từng trường hợp. Trong production, không cấp ACL admin cho mọi người; test dùng role này để chuẩn bị và dọn database.

**ACL dữ liệu thực:** `setUp()` tạo một `ObjectIdentity` ID mới, ghi ba ACE rồi gọi `updateAcl`. `@AfterEach` xóa ACL để tránh test khác đọc dữ liệu còn lại. Mỗi test nhận một ID khác nhau nên không trùng unique key trong `acl_object_identity`.

**Phân biệt quyền quản trị và quyền tài nguyên:** Carol có `ROLE_ACL_ADMIN` nhưng không có SID được grant READ nên phải deny. Carol có thêm `ROLE_REVIEWER` mới được READ nhờ `GrantedAuthoritySid`.

**Kiểm tra method security:** `DocumentService` được inject qua Spring, `AopUtils.isAopProxy` phải true. `@P("id")` giữ tên `#id` để SpEL không phụ thuộc cờ `-parameters`. `Probe` chứng minh khi `@PreAuthorize` deny, thân method không chạy.

**Kiểm tra cache/revoke:** test cuối đọc một lần để nạp ACL, xóa ACE grant của Alice, cập nhật ACL và gọi lại. Kết quả phải deny; đây là một test thực tế hơn việc chỉ xác nhận cache bean tồn tại.

### 7.4. Chạy và kết quả mong đợi

Trong thư mục `acl-infrastructure-demo` có Gradle và JDK 17+:

```bash
gradle test --tests demo.AclInfrastructureTest
```

Nếu đã có Gradle Wrapper, dùng `./gradlew test --tests demo.AclInfrastructureTest` (Linux/macOS) hoặc `gradlew.bat test --tests demo.AclInfrastructureTest` (Windows).

Khi wiring và database đúng, kỳ vọng **11 test** thành công, Gradle kết thúc `BUILD SUCCESSFUL`. Đây là **kết quả mong đợi theo thiết kế**, chưa phải kết quả từ một lần chạy thực tế. Báo cáo HTML nằm tại `build/reports/tests/test/index.html`.

| Test | Điểm xác nhận |
| --- | --- |
| Infrastructure | Bean và Spring AOP proxy có thật |
| Schema | Truy vấn được bốn bảng ACL |
| Persistence | `ObjectIdentity` và ba ACE được đọc lại |
| Alice READ | Allow, body chạy 1 lần |
| Bob READ | Deny tường minh, body không chạy |
| Carol + REVIEWER | Allow bởi authority SID |
| Carol chỉ ACL_ADMIN | Deny domain READ |
| WRITE chưa cấp | Deny |
| Cùng numeric ID, type khác | Deny |
| ObjectIdentity không tồn tại | Không cấp quyền |
| Revoke READ | Lời gọi sau `updateAcl` phải deny |

Đối với test production, nên bổ sung PostgreSQL/MySQL Testcontainers, transaction commit/rollback, quyền hạn đa tenant và chạy đồng thời từ nhiều application node.

## 8. DataSource production và transaction

### 8.1. Cấu hình DataSource PostgreSQL

Một mẫu `application.yml` cho dự án đã có migration:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.example.internal:5432/appdb
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
  sql:
    init:
      mode: never
```

Các chuỗi `DB_USER`, `DB_PASSWORD` là **biến môi trường minh họa**, không phải thông tin truy cập thật. Dùng secret manager/env var. DDL production do Flyway/Liquibase hoặc quy trình migration đã kiểm soát đảm nhận. Đừng dùng HSQLDB schema trong PostgreSQL: `VARCHAR_IGNORECASE` không tương thích, generated-key query cũng khác.

Nếu ứng dụng có **nhiều DataSource**, dùng qualifier rõ ràng cho ACL; `JdbcMutableAclService` và `BasicLookupStrategy` phải đọc cùng database/schema ACL. Nếu nguồn dữ liệu domain và nguồn ACL khác database, một `@Transactional` trên một transaction manager **không đủ** đảm bảo atomic commit ở cả hai bên.

### 8.2. Transaction cho cập nhật ACL

Tạo ACL và thêm ACE có thể cần nhiều SQL: tạo class/SID mới, tạo object identity, thêm entry, cập nhật owner/inheritance. Cần ranh giới transaction rõ ràng ở service quản trị. Theo mô hình Spring proxy mặc định, `@Transactional` chỉ intercept lời gọi qua bean/proxy, không tự áp dụng cho `this.innerMethod()`.

Cũng phải xác định thứ tự cập nhật database và evict cache ACL. Một số cache không cùng transaction với database; trong hệ thống nhiều instance, quyền đã bị thu hồi không được tiếp tục được cấp vì cache cũ quá lâu.

## 9. Cache, hiệu năng và tính nhất quán

`BasicLookupStrategy` hỗ trợ batch đọc ACL từ database và `AclCache` giảm chi phí truy vấn. Tuy nhiên, không có nghĩa `@PostFilter("hasPermission(filterObject, 'READ')")` trên hàng nghìn tài liệu tự biến thành SQL phân trang an toàn.

Những tình huống cần xử lý:

- **N+1 truy vấn:** mỗi phần tử gọi evaluator, kéo theo lookup riêng nếu không batch/cache đúng.
- **Phân trang:** lọc trong RAM sau khi lấy page có thể làm thiếu phần tử, lệch `totalElements` và lộ metadata. Ưu tiên ràng buộc quyền ngay khi query.
- **Thu hồi quyền:** `updateAcl`, `deleteAcl` hoặc sửa ACE phải được cache evict; test grant → revoke → deny.
- **Nhiều pod:** `ConcurrentMapCache` là cache cục bộ từng JVM; có thể cần distributed invalidation hoặc TTL cùng yêu cầu nhất quán.
- **Thay đổi SID/role:** user mất role nhưng authentication cũ vẫn mang authority thì kết quả có thể sai; quản lý lifecycle session/token và cache phù hợp.
- **Kế thừa ACL:** thay đổi parent hoặc `entriesInheriting` có thể ảnh hưởng nhiều ACL con; test invalidation theo quan hệ phụ thuộc.
- **Multi-tenant:** cùng ID nghiệp vụ ở hai tenant không được map vào một ObjectIdentity vô tình; phân tách đúng type/identifier/schema và test quyền chéo tenant.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| Không có class `Acl` hoặc `JdbcMutableAclService` | Thiếu `spring-security-acl` hoặc version lệch | Kiểm tra dependency tree và BOM |
| Không có bean DataSource | Thiếu JDBC starter, driver hoặc config | Kiểm tra connection URL, driver, credentials |
| `Table acl_sid not found` | Chưa chạy schema hoặc sai search_path | Chạy migration đúng database/schema |
| DDL báo lỗi `VARCHAR_IGNORECASE` | Dùng HSQLDB SQL trên PostgreSQL | Dùng schema PostgreSQL |
| SQL lỗi `call identity()` | Mặc định HSQLDB nhưng chạy DB khác | Cấu hình `classIdentityQuery`, `sidIdentityQuery` |
| `hasPermission` luôn deny | Evaluator chưa nối với method expression handler | `static @Bean`, `setPermissionEvaluator`, test qua proxy |
| `@PreAuthorize` không chạy | Thiếu `@EnableMethodSecurity`, self-invocation, `new` | Gọi Spring-managed bean từ bên ngoài |
| `#id` bị `null` | Không có parameter metadata/`@P` | Dùng `@P("id")` hoặc `-parameters` |
| ACE nằm trong DB nhưng deny | Sai type/ID, SID, permission hoặc role string | So dữ liệu thực với `ObjectIdentity` và `Sid` |
| Có ACL_ADMIN mà không đọc được tài liệu | Nhầm quyền quản trị ACL và grant READ | Kiểm tra ACE của đúng tài nguyên |
| Không có ACE nhưng mong `Acl.isGranted` luôn trả false | No-match có thể ném `NotFoundException` | Phân biệt no-rule với deny tường minh; fail closed |
| Grant/revoke không có tác dụng ngay | Cache ACL hoặc authentication không refresh | Test eviction, nhiều pod, lifecycle token |
| Có ACL nhưng write thất bại | Thiếu quyền quản trị ACL, transaction hoặc FK | Kiểm tra `AclAuthorizationStrategy` và SQL |
| Prod lỗi trong khi HSQLDB test pass | Dialect khác, generated-key query khác | Test thực tế bằng PostgreSQL Testcontainers |
| ACL cũ tồn tại khi xóa entity | Không có lifecycle hook | Thiết kế cleanup bằng `MutableAclService` |
| Lọc danh sách chậm | Gọi `hasPermission` trên từng item | Batch lookup, cache, query scoped |
| Cần sửa dữ liệu nhưng sau cùng bị deny | `@PostAuthorize` chạy sau body | Chặn trước side effect bằng `@PreAuthorize` |

### Quy trình debug nên làm từ dưới lên

1. **Kết nối:** DataSource có nối đúng database/schema? Có quyền SQL cần thiết?
2. **DDL:** bốn bảng có tồn tại, đúng kiểu dữ liệu, khóa ngoại/unique và generated-ID strategy?
3. **Ghi/đọc:** `createAcl`, `insertAce`, `updateAcl`, `readAclById` có hoạt động khi gọi trực tiếp trên service đã cấu hình?
4. **Chiến lược:** `Acl.isGranted(...)` với đúng SID/permission được giải thích theo grant, explicit deny hay no-match?
5. **Evaluator:** `AclPermissionEvaluator.hasPermission` có thể đọc đúng object ID/type và permission?
6. **Expression handler:** bean `MethodSecurityExpressionHandler` có nối đúng evaluator?
7. **Proxy:** method được gọi qua Spring bean với `@EnableMethodSecurity`, hay đang bị self-invocation?
8. **Tính mới:** sau grant/revoke, cache và token authentication có được cập nhật đúng?
9. **Môi trường:** khác nhau ở dialect, migration, nhiều instance hoặc transaction manager?

## 11. Bài tập và checklist nghiệm thu

**Bài tập A — thêm WRITE:** Trong test, thêm ACE `BasePermission.WRITE` cho Alice, `updateAcl`, sau đó `documents.write(id)` phải chuyển từ deny sang allow.

**Bài tập B — tách quản trị và đọc:** Cho Carol chỉ có `ROLE_ACL_ADMIN`, xác minh không có ACE READ vẫn deny. Sau đó cấp `ROLE_REVIEWER` và xác minh allow.

**Bài tập C — thay dialect:** Chuyển HSQLDB sang PostgreSQL, áp dụng SQL schema đúng và cập nhật hai generated-key queries. Chạy test trên PostgreSQL Testcontainers thay vì chỉ kiểm tra project khởi động.

**Bài tập D — thu hồi quyền:** Lặp grant → read → revoke → read với hai instance và cache khác nhau. Xác định cơ chế bảo đảm không còn trả dữ liệu đã bị thu hồi.

**Bài tập E — fail closed:** Thử ID không có ACL, type sai, permission không tồn tại, SID chưa nạp và DB lỗi; không trường hợp nào được vô tình cấp quyền.

Checklist trước khi triển khai:

- [ ] `spring-security-acl` tương thích version Spring Security toàn hệ thống.
- [ ] DataSource đúng và driver có mặt; transaction manager đúng nguồn dữ liệu.
- [ ] Bốn bảng ACL có đủ constraints, identity/sequence queries theo đúng dialect.
- [ ] `JdbcMutableAclService`, `BasicLookupStrategy`, `AclCache` và các strategy được wired đúng.
- [ ] `AclPermissionEvaluator` đăng ký bằng `setPermissionEvaluator` trên method-security expression handler.
- [ ] `@EnableMethodSecurity` bật và service được gọi qua Spring AOP proxy.
- [ ] Có test grant, deny, no-ACL, role SID, wrong type, WRITE chưa cấp và revoke/cache.
- [ ] Có cơ chế quản trị ACL, audit, migration, cleanup khi xóa entity và invalidation nhiều instance.
- [ ] Không xem HSQLDB test là thay thế cho test PostgreSQL/MySQL đúng môi trường triển khai.

## 12. Ghi nhớ

**Thứ tự cấu hình:** thêm ACL dependency → tạo đúng `DataSource` → migrate bốn bảng ACL → cấu hình `BasicLookupStrategy`/`JdbcMutableAclService`/`AclCache` → hai authorization strategies → `AclPermissionEvaluator` → `DefaultMethodSecurityExpressionHandler` → `@EnableMethodSecurity` và kiểm thử Spring proxy.

ACL không chỉ là một annotation. Toàn bộ chuỗi phải hoạt động và được test **từ SQL đến quyết định quyền theo từng tài nguyên**, đặc biệt khi quyền đã bị thu hồi hoặc ứng dụng có nhiều instance.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Domain Object Security (ACLs), bean configuration: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html
- Spring Security 6.5 — Security Database Schema, ACL DDL cho từng database: https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html
- Spring Security 6.5 — Method Security, custom expression handler: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 API — `JdbcMutableAclService` generated-ID queries: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html
- Spring Security 6.5 API — `AclPermissionEvaluator`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/AclPermissionEvaluator.html
- Spring Security 6.5 API — `SpringCacheBasedAclCache`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/SpringCacheBasedAclCache.html
