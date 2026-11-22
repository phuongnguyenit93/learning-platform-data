# Thêm, sửa, xóa ACE và kiểm soát người được phép chia sẻ trong Spring Security ACL

## 1. Bài toán: ai được nhận quyền, và ai có quyền cấp quyền?

Giả sử tài liệu `Document#101` thuộc tenant `t1` và do Alice sở hữu. Alice muốn cấp cho Bob quyền xem trước, sau đó nâng lên quyền sửa, rồi thu hồi. Một nhân viên khác có `WRITE` trên tài liệu **không được tự chia sẻ tiếp** cho người khác. Người quản trị tenant có thể được ủy quyền quản lý ACL trong tenant đó, nhưng **không được dùng role quản trị để vượt qua tenant boundary**.

Spring Security ACL sử dụng **Access Control Entry (ACE)** để lưu từng quyền trên đối tượng. Về mặt API, ba thao tác cốt lõi là:

```java
mutableAcl.insertAce(index, permission, sid, true);
mutableAcl.updateAce(index, newPermission);
mutableAcl.deleteAce(index);
aclService.updateAcl(mutableAcl);
```

Đây là **đoạn minh họa API**: cần một `MutableAcl` hợp lệ, `Permission`, `Sid`, index đúng và `MutableAclService`. Các phương thức này **không tự chứng minh người gọi có quyền chia sẻ theo nghiệp vụ**. Cần kiểm tra đồng thời:

1. **Quyền nghiệp vụ của người gọi**: owner hoặc người được cấp quyền quản lý chia sẻ trong tenant.
2. **Quyền sửa cấu trúc ACL của Spring Security**: `AclAuthorizationStrategy` quyết định ai được gọi các mutator trên `MutableAcl`.
3. **Tính hợp lệ của người nhận**: recipient có thuộc đúng tenant, có được phép nhận mức quyền này và có đang hợp lệ không?
4. **Chính sách quyền được cấp**: chỉ cấp READ/WRITE trong phạm vi được phép; không cho user truyền tùy ý bitmask `ADMINISTRATION`.
5. **Tính nhất quán của thay đổi**: transaction, cache eviction, audit, revoke và xử lý cạnh tranh.

Bài học tập trung vào **triển khai thêm/sửa/xóa ACE** và thiết kế API chia sẻ an toàn trên Spring Security ACL 6.5, Java 17 và Spring Boot 3.5.x.

## 2. ACE và ACL: bản ghi nào thực sự được thay đổi?

Trong database ACL mặc định:

```text
acl_sid
  id | principal | sid
  1  | true      | alice
  2  | true      | bob
  3  | true      | manager1

acl_class
  id | class
  7  | com.example.aclshare.Document

acl_object_identity
  id | object_id_class | object_id_identity | owner_sid | entries_inheriting
  10 | 7               | 101                | 1         | false

acl_entry
  id  | acl_object_identity | ace_order | sid | mask | granting
  100 | 10                  | 0         | 3   | 16   | true
```

Đây là dữ liệu minh họa. ACL nội bộ `10` đại diện cho domain object `Document#101`; `acl_entry.acl_object_identity=10` trỏ tới **ACL PK**, không phải document id 101.

`owner_sid=1` nghĩa là Alice là **chủ sở hữu ACL**. ACE đầu tiên cấp `BasePermission.ADMINISTRATION` (mask 16) cho `manager1`; nó minh họa cách một người không phải owner được cấp quyền quản lý ACL. **ADMINISTRATION trên ACL khác với business WRITE trên Document.**

Các khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| `ObjectIdentity` | Định danh type + domain id | `(Document.class, 101L)` |
| `MutableAcl` | ACL có thể thêm/sửa/xóa ACE | ACL của `Document#101` |
| `Sid` | Đối tượng nhận quyền | `PrincipalSid("bob")` |
| `Permission` | Mức quyền, thường là bitmask | `BasePermission.READ`, mask 1 |
| `AccessControlEntry` | Quy tắc trên một SID + permission + allow/deny | Bob được READ |
| `AclAuthorizationStrategy` | Kiểm tra quyền **quản trị ACL** | Owner, admin authority hoặc ADMINISTRATION ACE |
| `MutableAclService` | Đọc/tạo/cập nhật/xóa ACL trong persistence | `JdbcMutableAclService` |
| `AclPermissionEvaluator` | Đánh giá quyền **truy cập tài nguyên** | `hasPermission(#id, ..., READ)` |

Ở đây một user có thể được cấp `BasePermission.WRITE` nhưng vẫn không được sửa danh sách chia sẻ. Phân biệt **quyền sử dụng tài nguyên** và **quyền sửa chính sách quyền** là nguyên tắc chống leo thang đặc quyền.

## 3. Ba phương thức thay đổi ACE

### 3.1. Thêm ACE — insertAce

```java
Sid bob = new PrincipalSid("bob");
Permission read = BasePermission.READ;
acl.insertAce(acl.getEntries().size(), read, bob, true);
mutableAclService.updateAcl(acl);
```

Đây là **đoạn mẫu nằm trong service có đủ dependencies**. `insertAce` nhận:
- `atIndexLocation`: vị trí muốn chèn trong danh sách ACE; cuối danh sách là `acl.getEntries().size()`.
- `permission`: quyền, chẳng hạn `READ`.
- `sid`: principal hoặc authority nhận quyền.
- `granting`: `true` cho phép, `false` là ACE từ chối.

**Không dùng ACE có `granting=false` để biểu diễn “thu hồi share” nếu mục tiêu là bỏ một grant**. Một ACE deny vẫn tồn tại và có thể tương tác với ACE khác theo thứ tự/chiến lược granting; thu hồi một grant thường dùng `deleteAce`. Chỉ dùng deny có chủ đích khi chính sách thật sự yêu cầu phủ định tường minh.

Thêm ACE làm thay đổi `ace_order`. Không coi ID database của ACE là index trong `MutableAcl`; `ace_order` và list index là thứ tự logic mà framework quản lý, còn PK `acl_entry.id` là giá trị khác.

### 3.2. Sửa ACE — updateAce

```java
int index = findGrantIndex(acl, new PrincipalSid("bob"));
acl.updateAce(index, BasePermission.WRITE);
mutableAclService.updateAcl(acl);
```

Đây là **minh họa**, cần hàm `findGrantIndex` được định nghĩa trong ứng dụng. `updateAce(int,Permission)` thay **permission mask** của một ACE đã tồn tại. Nó **không** đổi SID, không đổi `granting` và không phải API “thay tất cả thuộc tính ACE”.

Nếu đổi `READ` thành `WRITE` thì Bob có thể **mất** READ, tùy permission strategy. Muốn mức `EDITOR` bao gồm **cả READ và WRITE**, không thay đơn giản bằng mask 2. Hai cách mô hình hóa:

- Hai ACE riêng, một READ và một WRITE cho cùng SID.
- Một ACE có permission bitmask kết hợp READ|WRITE (=3), ví dụ `CumulativePermission`.

Trong demo ở phần 6, ta chọn **mỗi recipient một grant ACE** cho mỗi document, theo mức:
- `VIEWER` → READ (mask 1).
- `EDITOR` → READ|WRITE (mask 3).

`updateAce` sẽ thay mask 1 bằng mask 3 khi nâng cấp; khi hạ quyền từ editor về viewer sẽ thay mask 3 về 1. Spring Security ACL `DefaultPermissionGrantingStrategy` hỗ trợ đối chiếu các bit của ACE cho **granting ACE**; đồng thời cần test trên đúng phiên bản, bởi chính sách deny/multiple-ACE có ngữ nghĩa riêng.

```java
Permission editor = new CumulativePermission()
    .set(BasePermission.READ)
    .set(BasePermission.WRITE);
```

Với `CumulativePermission`, phép `set` bật các bit tương ứng. Đoạn này có thể đặt trong method và import `org.springframework.security.acls.domain.CumulativePermission`.

### 3.3. Xóa ACE — deleteAce

```java
int index = findGrantIndex(acl, new PrincipalSid("bob"));
if (index >= 0) {
    acl.deleteAce(index);
    mutableAclService.updateAcl(acl);
}
```

Xóa ACE theo **vị trí hiện tại** của list. Nếu xoá nhiều ACE, nên duyệt **từ cuối về đầu** để không làm lệch chỉ số. Sau khi xóa, các index có thể thay đổi. Không lưu index cũ giữa nhiều request để sau đó dùng trực tiếp.

**Điểm quan trọng:** Xóa ACE trực tiếp không đồng nghĩa “Bob không còn bất kỳ đường nào để đọc”. Bob còn có thể được cấp quyền qua một `GrantedAuthoritySid`, ACL cha nếu `entries_inheriting=true`, hoặc chính sách khác. Việc thu hồi **một nguồn quyền** cần được test theo tổng hợp mọi nguồn quyền thực tế.

### 3.4. Persist và cơ chế updateAcl của JDBC

`MutableAcl` sửa trong bộ nhớ trước; `mutableAclService.updateAcl(acl)` mới ghi xuống DB. Theo `JdbcMutableAclService`, một lần `updateAcl` có thể **xóa toàn bộ ACE hiện tại của ACL rồi tạo lại các hàng ACE** theo danh sách mới, thay vì SQL UPDATE đúng một hàng. Điều này dẫn đến:

- Không coi `acl_entry.id` là định danh bền vững của một grant; nó có thể đổi sau mỗi update.
- Ràng buộc `ace_order` cần được thư viện đồng bộ lại.
- Nếu service khác cũng đang sửa ACL, có nguy cơ **lost update**.
- Việc ghi nên nằm trong transaction phù hợp; permission cache cần được invalidate.
- Audit thay đổi ở mức nghiệp vụ phải ghi rõ actor, target, recipient, old level, new level, không chỉ dựa trên row ID.

Không sửa trực tiếp `acl_entry` bằng SQL ở một nhánh rồi quên evict `AclCache`; các quyết định ACL đang cache có thể dùng dữ liệu cũ.

## 4. Ai thực sự được phép chia sẻ?

### 4.1. Hai lớp bảo vệ khác nhau

**Lớp A — chính sách nghiệp vụ** có thể định nghĩa:

```text
canManageShare(actor, document):
  actor là người dùng xác thực và còn hoạt động
  AND actor còn là thành viên tenant của document
  AND (
      actor là owner của document
      OR actor có tenant-admin binding trên đúng tenant
  )
```

**Lớp B — AclAuthorizationStrategy** của framework quyết định actor có quyền sửa `MutableAcl` hay không. `AclAuthorizationStrategyImpl` theo mặc định có thể chấp nhận actor là ACL owner, có system-wide authority đã cấu hình, hoặc có `BasePermission.ADMINISTRATION` phù hợp trên ACL. Đây là **cơ chế quản trị ACL**, không phải một kiểm tra tenant/business owner thay thế cho lớp A.

Dù actor vượt lớp B, vẫn phải vượt lớp A. Cấp `ROLE_ACL_SYSTEM_ADMIN` cho mọi nhân viên “hỗ trợ” rồi bỏ lớp A có thể cho phép sửa ACE trên mọi tài nguyên. Đừng dùng quyền system-wide trừ khi có quy trình break-glass/khóa chặt đặc biệt.

### 4.2. Quy tắc cấp/thu hồi theo người nhận

Ở ví dụ:

| Actor | Document | Recipient | Hành động | Quyết định |
|---|---|---|---|---|
| Alice (owner t1) | 101 / t1 | Bob (member t1) | VIEWER/EDITOR/revoke | Allow |
| Bob (được share EDITOR) | 101 / t1 | manager1 | Chia sẻ tiếp | Deny |
| manager1 (tenant admin t1 + ACL ADMIN ACE) | 101 / t1 | Bob | VIEWER/EDITOR/revoke | Allow |
| manager1 (tenant admin t1) | 201 / t2 | Carol | Chia sẻ | Deny |
| Alice (owner t1) | 101 / t1 | Carol (member t2) | Chia sẻ | Deny |
| Mallory (không thuộc tenant) | 101 / t1 | Bob | Chia sẻ | Deny |
| Alice | 101 / t1 | Alice (owner) | Share theo ACL người nhận | Từ chối như yêu cầu không hợp lệ |
| Alice | 101 / t1 | Bob | Cấp `ADMINISTRATION` qua API share cơ bản | Không có chức năng này |

Điều kiện recipient là thành viên tenant cần được kiểm tra **tại thời điểm cấp**. Điều kiện actor cũng cần được kiểm tra tại thời điểm sửa, vì quyền có thể đã bị thu hồi. Ở production, lưu role binding theo tenant; một role `ROLE_TENANT_ADMIN` trần trong token không đủ để kết luận admin trên tất cả tenant.

### 4.3. Không nhầm quyền WRITE với quyền SHARE

`BasePermission.WRITE` cho phép sửa **nội dung nghiệp vụ** nếu API kiểm tra nó. Nó không cấp quyền gọi `insertAce`, `updateAce` hoặc `deleteAce`. Chính sách chia sẻ thường cần:
- Được nêu thành action riêng (ví dụ `document:share`), hoặc
- Quyền ACL administration trên đúng object kết hợp policy owner/admin, như demo.

Có thể thiết kế “editor có quyền chia sẻ” nếu nghiệp vụ cho phép, nhưng phải khai báo tường minh, giới hạn mức quyền được cấp (không cho cấp mạnh hơn mức đang có), chống delegation loop và có audit.

### 4.4. Cấp cho PrincipalSid khác với GrantedAuthoritySid

```java
Sid user = new PrincipalSid("bob");
Sid groupRole = new GrantedAuthoritySid("ROLE_REVIEWER");
```

Đây là hai kiểu SID khác nhau:
- `PrincipalSid` chỉ nhắm đến một username.
- `GrantedAuthoritySid` cấp cho **mọi Authentication** có authority đó, có thể rộng hơn dự kiến.

API chia sẻ cá nhân ở demo **chỉ nhận username**, không cho client chọn SID type hay truyền trực tiếp `ROLE_ADMIN`. Nếu có chia sẻ cho nhóm/role, tạo endpoint và policy riêng, validate nhóm đúng tenant, cho phép nhóm nhận mức quyền phù hợp và kiểm thử principal hiện có thể được hưởng quyền mới.

## 5. Ma trận quyền và ranh giới của demo

Hệ thống có ba document:

| ID | Tenant | Owner | ACL owner |
|---:|---|---|---|
| 101 | t1 | alice | alice |
| 102 | t1 | bob | bob |
| 201 | t2 | carol | carol |

Thành viên:
- `t1`: Alice, Bob, manager1.
- `t2`: Carol, Dave.
- Tenant-admin: manager1 được quản trị **t1**.

ACL của Document#101 có một ACE ADMINISTRATION cho principal `manager1`, cho phép manager1 sửa ACL ở tầng framework. Document#201 không cấp quyền đó cho manager1. Khi chia sẻ, code chỉ sửa ACE của **recipient được xác minh**, không đổi ACL owner hoặc các ACE khác.

Mức chia sẻ:

| Mức | ACL mask | Read | Write | Share/ACL admin |
|---|---:|---:|---:|---:|
| Không chia sẻ | Không có ACE grant trực tiếp | Deny nếu không có nguồn khác | Deny nếu không có nguồn khác | Không |
| `VIEWER` | 1 (READ) | Allow | Deny | Không |
| `EDITOR` | 3 (READ|WRITE) | Allow | Allow | Không |

**Lưu ý về nguồn quyền khác:** Trên ACL có thể có ACE kế thừa hoặc role. Bảng này giả định không có nguồn READ/WRITE nào khác cho người nhận, và `entries_inheriting=false` trong dữ liệu demo. Không diễn giải “đã revoke = chắc chắn deny” nếu mô hình thực tế vẫn còn role/share/inheritance khác.

## 6. Ví dụ đầy đủ: Java 17, Spring Boot 3.5.6, Spring Security ACL, HSQLDB

Demo có đủ Maven, schema SQL, fixtures, Spring config, policy và service; chạy `mvn test` để kiểm tra hành vi thêm, nâng cấp, hạ cấp, xóa ACE và các đường deny.

### 6.1. Cấu trúc dự án

```text
acl-sharing-demo/
  pom.xml
  src/main/java/com/example/aclshare/
    AclSharingApplication.java
    Document.java
    ShareLevel.java
    TenantDirectory.java
    DocumentRepository.java
    SharePolicy.java
    AclConfig.java
    SharingService.java
    DocumentService.java
  src/main/resources/
    schema.sql
    data.sql
  src/test/java/com/example/aclshare/
    SharingIntegrationTest.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>acl-sharing-demo</artifactId>
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
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-acl</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.hsqldb</groupId>
            <artifactId>hsqldb</artifactId>
            <scope>runtime</scope>
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
```

Không ghi đè version `spring-security-acl` trong demo; Spring Boot 3.5.6 quản lý các module Security tương thích. Java 17 là mức tối thiểu của Spring Boot 3.x. Nếu dự án dùng Spring Boot 4/Spring Security 7, cần đọc API và starter tương ứng; không ép một thư viện major version mới vào BOM cũ.

### 6.3. Schema HSQLDB

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE document (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(50) NOT NULL,
    owner_username VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL
);

CREATE TABLE tenant_member (
    tenant_id VARCHAR(50) NOT NULL,
    username VARCHAR(100) NOT NULL,
    PRIMARY KEY(tenant_id, username)
);

CREATE TABLE tenant_admin (
    tenant_id VARCHAR(50) NOT NULL,
    username VARCHAR(100) NOT NULL,
    PRIMARY KEY(tenant_id, username),
    FOREIGN KEY (tenant_id, username)
        REFERENCES tenant_member(tenant_id, username)
);

CREATE TABLE acl_sid (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000)
        PRIMARY KEY,
    principal BOOLEAN NOT NULL,
    sid VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT uq_sid UNIQUE(sid, principal)
);

CREATE TABLE acl_class (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000)
        PRIMARY KEY,
    class VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT uq_class UNIQUE(class)
);

CREATE TABLE acl_object_identity (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000)
        PRIMARY KEY,
    object_id_class BIGINT NOT NULL,
    object_id_identity VARCHAR_IGNORECASE(36) NOT NULL,
    parent_object BIGINT,
    owner_sid BIGINT,
    entries_inheriting BOOLEAN NOT NULL,
    CONSTRAINT uq_object UNIQUE(object_id_class, object_id_identity),
    FOREIGN KEY (object_id_class) REFERENCES acl_class(id),
    FOREIGN KEY (parent_object) REFERENCES acl_object_identity(id),
    FOREIGN KEY (owner_sid) REFERENCES acl_sid(id)
);

CREATE TABLE acl_entry (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000)
        PRIMARY KEY,
    acl_object_identity BIGINT NOT NULL,
    ace_order INTEGER NOT NULL,
    sid BIGINT NOT NULL,
    mask INTEGER NOT NULL,
    granting BOOLEAN NOT NULL,
    audit_success BOOLEAN NOT NULL,
    audit_failure BOOLEAN NOT NULL,
    CONSTRAINT uq_ace_order UNIQUE(acl_object_identity, ace_order),
    FOREIGN KEY (acl_object_identity) REFERENCES acl_object_identity(id),
    FOREIGN KEY (sid) REFERENCES acl_sid(id)
);
```

Bốn bảng ACL theo cấu trúc HSQLDB mà Spring Security cung cấp, cộng ba bảng nghiệp vụ `document`, `tenant_member` và `tenant_admin`. Các ID ACL seed nhỏ hơn 1000 để phân biệt ID viết tay và ID auto-generated khi tạo ACE mới. Schema production nên dùng migration, index, audit columns và chính sách tenant phù hợp; đây là embedded database trong test.

### 6.4. Fixture ban đầu

**`src/main/resources/data.sql`**

```sql
INSERT INTO document VALUES (101, 't1', 'alice', 'Alice draft');
INSERT INTO document VALUES (102, 't1', 'bob', 'Bob notes');
INSERT INTO document VALUES (201, 't2', 'carol', 'Carol plan');

INSERT INTO tenant_member VALUES ('t1', 'alice');
INSERT INTO tenant_member VALUES ('t1', 'bob');
INSERT INTO tenant_member VALUES ('t1', 'manager1');
INSERT INTO tenant_member VALUES ('t2', 'carol');
INSERT INTO tenant_member VALUES ('t2', 'dave');

INSERT INTO tenant_admin VALUES ('t1', 'manager1');

INSERT INTO acl_sid(id, principal, sid) VALUES (1, TRUE, 'alice');
INSERT INTO acl_sid(id, principal, sid) VALUES (2, TRUE, 'bob');
INSERT INTO acl_sid(id, principal, sid) VALUES (3, TRUE, 'carol');
INSERT INTO acl_sid(id, principal, sid) VALUES (4, TRUE, 'manager1');

INSERT INTO acl_class(id, class)
VALUES (7, 'com.example.aclshare.Document');

INSERT INTO acl_object_identity(
    id, object_id_class, object_id_identity,
    parent_object, owner_sid, entries_inheriting
) VALUES (10, 7, '101', NULL, 1, FALSE);

INSERT INTO acl_object_identity(
    id, object_id_class, object_id_identity,
    parent_object, owner_sid, entries_inheriting
) VALUES (11, 7, '102', NULL, 2, FALSE);

INSERT INTO acl_object_identity(
    id, object_id_class, object_id_identity,
    parent_object, owner_sid, entries_inheriting
) VALUES (20, 7, '201', NULL, 3, FALSE);

-- Cho manager1 quyền ADMINISTRATION trên ACL #101.
INSERT INTO acl_entry(
    id, acl_object_identity, ace_order, sid,
    mask, granting, audit_success, audit_failure
) VALUES (100, 10, 0, 4, 16, TRUE, FALSE, FALSE);
```

`acl_entry.id=100` là ACE cho manager1 trên ACL của Document#101. Nó cho phép **thao tác quản trị ACL** theo `AclAuthorizationStrategyImpl`, không tự cấp READ hoặc WRITE nội dung. Owner Alice có thể sửa ACL do `owner_sid=alice`. Document#102 không có ACE admin cho manager1, dù manager1 là tenant admin trong bảng nghiệp vụ: đây là ví dụ hai lớp quản trị độc lập.

### 6.5. Spring Boot application

**`src/main/java/com/example/aclshare/AclSharingApplication.java`**

```java
package com.example.aclshare;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AclSharingApplication {
    public static void main(String[] args) {
        SpringApplication.run(AclSharingApplication.class, args);
    }
}
```

### 6.6. Document và mức quyền

**`src/main/java/com/example/aclshare/Document.java`**

```java
package com.example.aclshare;

public record Document(Long id, String tenantId,
                       String owner, String title) {
    public Long getId() {
        return id;
    }
}
```

**`src/main/java/com/example/aclshare/ShareLevel.java`**

```java
package com.example.aclshare;

public enum ShareLevel {
    VIEWER,
    EDITOR
}
```

`ShareLevel` cố ý chỉ có hai mức. API **không nhận permission mask integer tùy ý từ client**, không cho tạo ACE `ADMINISTRATION`, `DELETE` hay ACE với `granting=false` qua thao tác chia sẻ cá nhân. Nếu nghiệp vụ cần các mức khác, hãy mở rộng enum và ma trận kiểm thử có chủ đích.

### 6.7. Repository và tenant directory

**`src/main/java/com/example/aclshare/DocumentRepository.java`**

```java
package com.example.aclshare;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {
    private final JdbcTemplate jdbc;

    public DocumentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Document find(Long id) {
        if (id == null) {
            return null;
        }
        List<Document> rows = jdbc.query(
            """
            SELECT id, tenant_id, owner_username, title
            FROM document WHERE id = ?
            """,
            (rs, rowNum) -> new Document(
                rs.getLong("id"),
                rs.getString("tenant_id"),
                rs.getString("owner_username"),
                rs.getString("title")
            ),
            id
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public void rename(Long id, String title) {
        int updated = jdbc.update(
            "UPDATE document SET title = ? WHERE id = ?",
            title, id
        );
        if (updated != 1) {
            throw new IllegalStateException("Document not found");
        }
    }
}
```

**`src/main/java/com/example/aclshare/TenantDirectory.java`**

```java
package com.example.aclshare;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {
    private final JdbcTemplate jdbc;

    public TenantDirectory(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean isMember(String tenant, String user) {
        if (tenant == null || user == null) {
            return false;
        }
        Integer count = jdbc.queryForObject(
            """
            SELECT COUNT(*) FROM tenant_member
            WHERE tenant_id = ? AND username = ?
            """,
            Integer.class, tenant, user
        );
        return count != null && count > 0;
    }

    public boolean isTenantAdmin(String tenant, String user) {
        if (tenant == null || user == null) {
            return false;
        }
        Integer count = jdbc.queryForObject(
            """
            SELECT COUNT(*) FROM tenant_admin
            WHERE tenant_id = ? AND username = ?
            """,
            Integer.class, tenant, user
        );
        return count != null && count > 0;
    }
}
```

Directory được đọc từ DB phía server, không từ form JSON hoặc header mà client tự khai. Trong production, cần đồng bộ IAM, tenant membership và cache/revocation policy.

### 6.8. SharePolicy: kiểm tra ai được quản lý chia sẻ

**`src/main/java/com/example/aclshare/SharePolicy.java`**

```java
package com.example.aclshare;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("sharePolicy")
public class SharePolicy {
    private final DocumentRepository documents;
    private final TenantDirectory directory;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public SharePolicy(
            DocumentRepository documents,
            TenantDirectory directory) {
        this.documents = documents;
        this.directory = directory;
    }

    public boolean canManage(Authentication auth, Long id) {
        if (auth == null || !auth.isAuthenticated()
                || trust.isAnonymous(auth)) {
            return false;
        }

        Document document = documents.find(id);
        if (document == null) {
            return false;
        }

        String user = auth.getName();
        String tenant = document.tenantId();

        if (!directory.isMember(tenant, user)) {
            return false;
        }

        if (document.owner().equals(user)) {
            return true;
        }

        return directory.isTenantAdmin(tenant, user)
            && hasAuthority(auth, "ROLE_TENANT_ADMIN");
    }

    private static boolean hasAuthority(
            Authentication auth, String required) {
        for (GrantedAuthority authority : auth.getAuthorities()) {
            if (required.equals(authority.getAuthority())) {
                return true;
            }
        }
        return false;
    }
}
```

**Ý nghĩa:** owner được chia sẻ nếu còn là member đúng tenant. Tenant admin cần **cả** role trong Authentication lẫn binding ở bảng `tenant_admin`. Đây là luật nghiệp vụ; nó **không thay thế** kiểm tra `AclAuthorizationStrategy` khi `MutableAcl.insertAce/updateAce/deleteAce` chạy.

Đặc biệt, `ROLE_TENANT_ADMIN` không phải `ROLE_ACL_SYSTEM_ADMIN`. Role trước chỉ có hiệu lực cùng binding tenant và ACL administration grant; role sau là quyền framework mức hệ thống mà demo không cấp cho user nào.

### 6.9. Cấu hình ACL framework và Method Security

**`src/main/java/com/example/aclshare/AclConfig.java`**

```java
package com.example.aclshare;

import javax.sql.DataSource;

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
import org.springframework.security.acls.jdbc.LookupStrategy;
import org.springframework.security.acls.model.AclCache;
import org.springframework.security.acls.model.AclService;
import org.springframework.security.acls.model.PermissionGrantingStrategy;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Configuration
@EnableMethodSecurity
public class AclConfig {

    @Bean
    static MethodSecurityExpressionHandler expressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(
            AclService aclService) {
        return new AclPermissionEvaluator(aclService);
    }

    @Bean
    static JdbcMutableAclService aclService(
            DataSource dataSource,
            LookupStrategy lookup,
            AclCache cache) {
        return new JdbcMutableAclService(dataSource, lookup, cache);
    }

    @Bean
    static LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache cache,
            AclAuthorizationStrategy authorization,
            PermissionGrantingStrategy granting) {
        return new BasicLookupStrategy(
            dataSource, cache, authorization, granting
        );
    }

    @Bean
    static AclCache aclCache(
            PermissionGrantingStrategy granting,
            AclAuthorizationStrategy authorization) {
        return new SpringCacheBasedAclCache(
            new ConcurrentMapCache("aclCache"),
            granting,
            authorization
        );
    }

    @Bean
    static AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_SYSTEM_ADMIN")
        );
    }

    @Bean
    static PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger()
        );
    }
}
```

Spring Security ACL infrastructure ở đây gồm `JdbcMutableAclService`, `BasicLookupStrategy`, ACL cache, granting strategy và authorization strategy. `@EnableMethodSecurity` kích hoạt `@PreAuthorize`; expression handler nối `AclPermissionEvaluator` để `hasPermission` kiểm tra chính các ACE trong database.

**Nhấn mạnh:** `ROLE_ACL_SYSTEM_ADMIN` trong constructor là một **cửa quản trị trên toàn hệ thống của framework**. Demo không cấp quyền này; người quản trị tenant được phép sửa Document#101 do có ACE `BasePermission.ADMINISTRATION` riêng. Trong production, tránh cấp authority system-wide một cách rộng rãi; role này cần kiểm soát và audit đặc biệt.

### 6.10. SharingService: thêm, sửa và xóa đúng ACE

**`src/main/java/com/example/aclshare/SharingService.java`**

```java
package com.example.aclshare;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.acls.domain.CumulativePermission;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.domain.PrincipalSid;
import org.springframework.security.acls.model.AccessControlEntry;
import org.springframework.security.acls.model.MutableAcl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.Permission;
import org.springframework.security.acls.model.Sid;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SharingService {
    private final MutableAclService aclService;
    private final DocumentRepository documents;
    private final TenantDirectory directory;

    public SharingService(
            MutableAclService aclService,
            DocumentRepository documents,
            TenantDirectory directory) {
        this.aclService = aclService;
        this.documents = documents;
        this.directory = directory;
    }

    @Transactional
    @PreAuthorize("@sharePolicy.canManage(authentication, #id)")
    public void setShare(
            @P("id") Long id,
            String recipient,
            ShareLevel level) {

        Document document = documents.find(id);
        validateRecipient(document, recipient);

        if (level == null) {
            throw new IllegalArgumentException("Share level required");
        }

        MutableAcl acl = loadAcl(id);
        Sid sid = new PrincipalSid(recipient);
        int index = findSingleGrantIndex(acl, sid);
        Permission permission = permissionFor(level);

        if (index < 0) {
            acl.insertAce(acl.getEntries().size(), permission, sid, true);
        }
        else {
            // Chỉ thay mask của ACE đã có; SID/granting giữ nguyên.
            acl.updateAce(index, permission);
        }

        aclService.updateAcl(acl);
    }

    @Transactional
    @PreAuthorize("@sharePolicy.canManage(authentication, #id)")
    public void revokeShare(
            @P("id") Long id,
            String recipient) {

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException("Recipient required");
        }

        MutableAcl acl = loadAcl(id);
        int index = findSingleGrantIndex(
            acl, new PrincipalSid(recipient)
        );

        if (index >= 0) {
            acl.deleteAce(index);
            aclService.updateAcl(acl);
        }
        // Không có grant: idempotent no-op.
    }

    private void validateRecipient(
            Document document, String recipient) {

        if (document == null
                || recipient == null
                || recipient.isBlank()
                || recipient.equals(document.owner())
                || !directory.isMember(document.tenantId(), recipient)) {
            throw new IllegalArgumentException(
                "Recipient must be another member of the same tenant"
            );
        }
    }

    private MutableAcl loadAcl(Long id) {
        return (MutableAcl) aclService.readAclById(
            new ObjectIdentityImpl(Document.class, id)
        );
    }

    private static Permission permissionFor(ShareLevel level) {
        return switch (level) {
            case VIEWER -> BasePermission.READ;
            case EDITOR -> new CumulativePermission()
                .set(BasePermission.READ)
                .set(BasePermission.WRITE);
        };
    }

    private static int findSingleGrantIndex(
            MutableAcl acl, Sid recipient) {
        int result = -1;

        for (int i = 0; i < acl.getEntries().size(); i++) {
            AccessControlEntry ace = acl.getEntries().get(i);

            if (!recipient.equals(ace.getSid())) {
                continue;
            }

            // Đây là API chia sẻ cá nhân: không được tự ý xử lý
            // ACE deny, ADMIN, hay nhiều ACE cho cùng SID.
            int mask = ace.getPermission().getMask();
            if (!ace.isGranting() || (mask != 1 && mask != 3)) {
                throw new IllegalStateException(
                    "Recipient already has a non-share ACE"
                );
            }

            if (result >= 0) {
                throw new IllegalStateException(
                    "Multiple ACEs need explicit reconciliation"
                );
            }
            result = i;
        }

        return result;
    }
}
```

**Các chi tiết an toàn:**

- `@PreAuthorize` phải đi qua Spring proxy và gọi `sharePolicy` để chặn người không được chia sẻ **trước khi thân method chạy**.
- `@Transactional` bao quanh read ACL + sửa + persist, nhưng order advisor mặc định thường cho preauthorization xảy ra trước transaction. Trong production, nếu owner/tenant có thể thay đổi đồng thời, cần transaction/locking hoặc conditional update bao cả kiểm tra bất biến.
- `validateRecipient` kiểm tra người nhận thuộc tenant và không phải owner.
- `ShareLevel` là enum chặn caller tự chỉ định `ADMINISTRATION` hoặc `granting=false`.
- `findSingleGrantIndex` chỉ sửa **ACE cá nhân** đã biết có mask 1/3; nếu gặp nhiều ACE, deny ACE hoặc một loại quyền khác, từ chối sửa thay vì phá dữ liệu ACL ngoài phạm vi API.
- `insertAce` thêm mới nếu chưa có grant; `updateAce` đổi VIEWER↔EDITOR; `deleteAce` xóa đúng grant cá nhân.
- `updateAcl` persist thay đổi. Với implementation JDBC mặc định, có thể tái tạo các hàng `acl_entry`; do đó luôn tìm theo SID/mask trên ACL hiện tại, không ghi nhớ `acl_entry.id` hoặc index giữa các request.
- Nếu ACL chưa tồn tại, `readAclById` ném `NotFoundException`; demo yêu cầu ACL được tạo cùng resource. Production cần xử lý khởi tạo ACL khi tạo document; **không** tự tạo ACL thiếu trong một request chia sẻ không được xác thực đầy đủ.

**Giới hạn có chủ đích:** Demo không có grant expiration, group sharing, deny ACE, ACL parent inheritance, UI admin, file download hoặc gửi thông báo. Khi gặp ACE phức tạp hơn một grant cá nhân, code fail-closed để tránh âm thầm xóa quyền của nhóm khác.

### 6.11. DocumentService: kiểm tra quyền được chia sẻ thật sự

**`src/main/java/com/example/aclshare/DocumentService.java`**

```java
package com.example.aclshare;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "hasPermission(#id, 'com.example.aclshare.Document', " +
        "T(org.springframework.security.acls.domain.BasePermission).READ)"
    )
    public String read(@P("id") Long id) {
        Document document = documents.find(id);
        if (document == null) {
            throw new IllegalStateException("Document not found");
        }
        return document.title();
    }

    @Transactional
    @PreAuthorize(
        "hasPermission(#id, 'com.example.aclshare.Document', " +
        "T(org.springframework.security.acls.domain.BasePermission).WRITE)"
    )
    public void rename(@P("id") Long id, String title) {
        documents.rename(id, title);
    }
}
```

Đây là tầng **sử dụng tài nguyên**, khác với `SharingService` là tầng **quản lý ACL**. Người được cấp EDITOR có thể vượt `hasPermission(WRITE)` để sửa nội dung, nhưng `@sharePolicy.canManage(...)` vẫn từ chối nếu họ không phải owner/tenant admin.

**Cảnh báo về tenant:** `AclPermissionEvaluator` ở đây kiểm tra ACL permission trong database, nhưng **không tự bổ sung tenant boundary**. Demo cố tình chỉ cấp ACE theo người nhận đã được kiểm tra tenant khi chia sẻ. Ứng dụng production cần thêm điều kiện tenant cho **mọi đường đọc/ghi**, kể cả role-based ACE, ACL inheritance, user rời tenant và tài liệu đổi tenant. Không dùng đoạn `DocumentService` này nguyên xi làm chính sách multi-tenant production.

## 7. Kiểm thử tích hợp: chứng minh ba thao tác và các đường từ chối

Các test tạo Spring context và database HSQLDB thật, dùng `@WithMockUser` để giả lập danh tính. Vì nhiều test thay ACL, `@DirtiesContext(AFTER_EACH_TEST_METHOD)` yêu cầu context/DB embedded khởi tạo lại cho từng test, giảm nguy cơ state leak và cache bị dùng chéo. Cách này **cố ý đơn giản nhưng chậm**; bộ test production có thể dùng transaction rollback, fixture reset và cache eviction có kiểm soát để chạy nhanh hơn.

**`src/test/java/com/example/aclshare/SharingIntegrationTest.java`**

```java
package com.example.aclshare;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.acls.AclPermissionEvaluator;
import org.springframework.security.acls.domain.BasePermission;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SharingIntegrationTest {
    @Autowired SharingService sharing;
    @Autowired DocumentService documents;
    @Autowired AclPermissionEvaluator evaluator;
    @Autowired JdbcTemplate jdbc;

    private static Authentication bob() {
        return UsernamePasswordAuthenticationToken.authenticated(
            "bob", "n/a",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    private static Authentication alice() {
        return UsernamePasswordAuthenticationToken.authenticated(
            "alice", "n/a",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    private static int permissionMask(
            JdbcTemplate jdbc, long documentId, String username) {
        Integer mask = jdbc.queryForObject(
            """
            SELECT e.mask
            FROM acl_entry e
            JOIN acl_object_identity o
                ON o.id = e.acl_object_identity
            JOIN acl_sid s ON s.id = e.sid
            WHERE o.object_id_identity = ?
              AND s.principal = TRUE
              AND s.sid = ?
              AND e.granting = TRUE
            """,
            Integer.class,
            String.valueOf(documentId), username
        );
        return mask.intValue();
    }

    private int recipientAceCount(long documentId, String username) {
        Integer count = jdbc.queryForObject(
            """
            SELECT COUNT(*)
            FROM acl_entry e
            JOIN acl_object_identity o
                ON o.id = e.acl_object_identity
            JOIN acl_sid s ON s.id = e.sid
            WHERE o.object_id_identity = ?
              AND s.principal = TRUE
              AND s.sid = ?
            """,
            Integer.class,
            String.valueOf(documentId), username
        );
        return count.intValue();
    }

    private boolean bobCanRead(long id) {
        return evaluator.hasPermission(
            bob(), id, Document.class.getName(), BasePermission.READ
        );
    }

    private boolean bobCanWrite(long id) {
        return evaluator.hasPermission(
            bob(), id, Document.class.getName(), BasePermission.WRITE
        );
    }

    @Test
    @WithMockUser(username = "alice")
    void addingViewerAceAllowsReadButNotWrite() {
        assertFalse(bobCanRead(101L));
        sharing.setShare(101L, "bob", ShareLevel.VIEWER);
        assertEquals(1, permissionMask(jdbc, 101L, "bob"));
        assertEquals(1, recipientAceCount(101L, "bob"));
        assertTrue(bobCanRead(101L));
        assertFalse(bobCanWrite(101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void upgradingAceToEditorKeepsReadAndAddsWrite() {
        sharing.setShare(101L, "bob", ShareLevel.VIEWER);
        sharing.setShare(101L, "bob", ShareLevel.EDITOR);

        assertEquals(3, permissionMask(jdbc, 101L, "bob"));
        assertEquals(1, recipientAceCount(101L, "bob"));
        assertTrue(bobCanRead(101L));
        assertTrue(bobCanWrite(101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void downgradingEditorToViewerRemovesWrite() {
        sharing.setShare(101L, "bob", ShareLevel.EDITOR);
        sharing.setShare(101L, "bob", ShareLevel.VIEWER);

        assertEquals(1, permissionMask(jdbc, 101L, "bob"));
        assertTrue(bobCanRead(101L));
        assertFalse(bobCanWrite(101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void revokingShareDeletesRecipientAce() {
        sharing.setShare(101L, "bob", ShareLevel.EDITOR);
        assertTrue(bobCanWrite(101L));

        sharing.revokeShare(101L, "bob");

        assertEquals(0, recipientAceCount(101L, "bob"));
        assertFalse(bobCanRead(101L));
        assertFalse(bobCanWrite(101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void duplicateShareRequestDoesNotCreateSecondAce() {
        sharing.setShare(101L, "bob", ShareLevel.VIEWER);
        sharing.setShare(101L, "bob", ShareLevel.VIEWER);
        assertEquals(1, recipientAceCount(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "alice")
    void repeatedRevokeIsIdempotent() {
        sharing.revokeShare(101L, "bob");
        sharing.revokeShare(101L, "bob");
        assertEquals(0, recipientAceCount(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "alice")
    void granteeAccessUsesActualMethodSecurity() {
        sharing.setShare(101L, "bob", ShareLevel.EDITOR);

        SecurityContextHolder.getContext().setAuthentication(bob());
        assertEquals("Alice draft", documents.read(101L));
        documents.rename(101L, "Bob edit");
        assertEquals("Bob edit", documents.read(101L));
    }

    @Test
    @WithMockUser(username = "bob")
    void nonOwnerCannotShareSomebodyElsesDocument() {
        assertThrows(AccessDeniedException.class,
            () -> sharing.setShare(101L, "manager1", ShareLevel.VIEWER));
        assertEquals(0, recipientAceCount(101L, "manager1")
            - countInitialAdminAceForManager());
    }

    private int countInitialAdminAceForManager() {
        return 1;
    }

    @Test
    @WithMockUser(username = "alice")
    void anEditorStillCannotReshare() {
        sharing.setShare(101L, "bob", ShareLevel.EDITOR);
        SecurityContextHolder.getContext().setAuthentication(bob());

        assertThrows(AccessDeniedException.class,
            () -> sharing.setShare(101L, "manager1", ShareLevel.VIEWER));
        assertEquals(1, recipientAceCount(101L, "manager1"));
    }

    @Test
    @WithMockUser(username = "manager1", roles = "TENANT_ADMIN")
    void tenantAdminWithAclAdministrationAceMayShare() {
        sharing.setShare(101L, "bob", ShareLevel.VIEWER);
        assertTrue(bobCanRead(101L));
        assertEquals(1, recipientAceCount(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "manager1", roles = "TENANT_ADMIN")
    void tenantAdminCannotShareAcrossTenants() {
        assertThrows(AccessDeniedException.class,
            () -> sharing.setShare(201L, "dave", ShareLevel.EDITOR));
        assertEquals(0, recipientAceCount(201L, "dave"));
    }

    @Test
    @WithMockUser(username = "manager1", roles = "TENANT_ADMIN")
    void tenantAdminWithoutObjectAclAdminAceCannotChangeAnotherAcl() {
        assertThrows(AccessDeniedException.class,
            () -> sharing.setShare(102L, "alice", ShareLevel.VIEWER));
        assertEquals(0, recipientAceCount(102L, "alice"));
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerCannotShareToUserInDifferentTenant() {
        assertThrows(IllegalArgumentException.class,
            () -> sharing.setShare(101L, "carol", ShareLevel.VIEWER));
        assertEquals(0, recipientAceCount(101L, "carol"));
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerCannotShareWithSelf() {
        assertThrows(IllegalArgumentException.class,
            () -> sharing.setShare(101L, "alice", ShareLevel.EDITOR));
        assertEquals(0, recipientAceCount(101L, "alice"));
    }

    @Test
    @WithMockUser(username = "alice")
    void nullShareLevelRejectedWithoutGrant() {
        assertThrows(IllegalArgumentException.class,
            () -> sharing.setShare(101L, "bob", null));
        assertEquals(0, recipientAceCount(101L, "bob"));
    }

    @Test
    @WithMockUser(username = "alice")
    void unknownDocumentIsDeniedBeforeAclMutation() {
        assertThrows(AccessDeniedException.class,
            () -> sharing.setShare(999L, "bob", ShareLevel.VIEWER));
    }

    @Test
    @WithMockUser(username = "carol", roles = "TENANT_ADMIN")
    void roleWithoutTenantAdminBindingCannotManageT1() {
        assertThrows(AccessDeniedException.class,
            () -> sharing.setShare(101L, "bob", ShareLevel.VIEWER));
    }

    @Test
    @WithMockUser(username = "alice")
    void aclOwnerNotAutomaticallyGrantedBusinessRead() {
        assertThrows(AccessDeniedException.class,
            () -> documents.read(101L));
    }
}
```

Lệnh chạy:

```bash
mvn test
```

**Kỳ vọng theo thiết kế:** 18 test JUnit, tất cả pass. Đây là **kết quả kỳ vọng**, không phải log test đã được thực thi. Test dùng `@DirtiesContext` để tránh trạng thái chia sẻ tồn tại từ test khác; cách này chậm nhưng dễ hiểu. Test dùng `AclPermissionEvaluator` và `@PreAuthorize` thực, còn Authentication được `@WithMockUser` hoặc token in-memory tạo ra; nó **không kiểm tra** password/JWT hoặc membership propagation từ IAM bên ngoài.

### 7.1. Diễn giải kết quả các bài test trọng tâm

| Tình huống | Mask ACE Bob trên #101 | Bob READ | Bob WRITE | Hệ quả |
|---|---:|:---:|:---:|---|
| Chưa có share | Không có | ✗ | ✗ | Default deny nếu không có nguồn khác |
| Alice cấp VIEWER | 1 | ✓ | ✗ | `insertAce` |
| Alice nâng EDITOR | 3 | ✓ | ✓ | `updateAce` |
| Alice hạ VIEWER | 1 | ✓ | ✗ | `updateAce` |
| Alice thu hồi | Không có | ✗ | ✗ | `deleteAce` |

Bài test “Editor cannot reshare” cho thấy Bob có thể sửa nội dung khi được cấp EDITOR nhưng không thể cấp quyền cho người khác, vì `SharePolicy` không công nhận Bob là owner hoặc tenant admin và framework cũng không cấp ADMINISTRATION ACE cho Bob.

Bài test “Tenant admin without object ACL admin ACE” thể hiện hai lớp bảo vệ: người quản trị tenant vượt `SharePolicy` nhưng **không** vượt `AclAuthorizationStrategy` trên một ACL mà họ không phải owner, không có ACE ADMINISTRATION, cũng không có quyền system-wide. Không được tự suy rằng một nhánh hợp lệ đồng nghĩa đủ quyền ở tất cả tầng.

## 8. Các điểm mở rộng trong ứng dụng thật

### 8.1. Cẩn thận với updateAcl xóa và tái tạo ACE

Khi `JdbcMutableAclService.updateAcl` tái tạo toàn bộ `acl_entry`, một dịch vụ đang đồng thời:
- đọc ACL cũ;
- sửa một ACE;
- ghi lại danh sách ACE cũ;
có thể ghi đè grant mới của dịch vụ khác. Đây là vấn đề **lost update**. @Transactional bảo vệ một transaction, nhưng không tự tạo optimistic locking trên đối tượng ACL để phân xử hai request đang sửa đồng thời.

Các cách giảm rủi ro:
- Khóa `acl_object_identity` theo object ID trước khi sửa trong cùng transaction.
- Dùng cơ chế version/optimistic concurrency do ứng dụng bổ sung.
- Gộp thao tác chia sẻ của một document qua một serialization boundary.
- Tạo unique business-level invariant cho các ACE share cá nhân và reconcile rõ các trường hợp dữ liệu đã có.
- Test race khi hai request chia sẻ hoặc revoke cùng một document.

Một schema ACL mặc định không cung cấp cột version cho ACL object identity. Nếu tự bổ sung version, phải thiết kế persistence/queries và update strategy tương thích.

### 8.2. ACL cache và hiệu lực revoke

`SpringCacheBasedAclCache` có thể trả dữ liệu ACL đã đọc trước đó. Thay đổi ACL qua `JdbcMutableAclService` giúp quản lý cache theo implementation; nhưng chỉnh SQL trực tiếp hoặc chạy nhiều node với cache JVM riêng có thể làm revoke hiệu lực trễ.

Test việc thu hồi quyền trên môi trường nhiều instance, xác định invalidation event, TTL hoặc shared cache phù hợp, và kiểm soát quyền bị thu hồi trong JWT/Authentication. **Không coi một test đơn JVM là bằng chứng revoke lập tức trên cả cluster.**

### 8.3. Đổi owner, chuyển tenant và parent ACL

`MutableAcl.setOwner(...)` thay **ACL owner**; nó khác việc thay `document.owner_username` ở domain. Nếu đổi owner chỉ ở một bảng, hai owner có thể lệch nhau, gây quyết định quản trị không nhất quán. Chuyển tenant còn cần xem grants cũ, membership, ACL inheritance và role SID; nên thực hiện một workflow chuyên biệt, không biến thao tác `setShare` thành đường tắt để transfer ownership.

`setParent(...)` và `setEntriesInheriting(...)` có thể làm quyền kế thừa xuất hiện. Khi revoke một ACE con mà ACL cha vẫn grant, user có thể còn quyền. Hãy test tổ hợp các ACL thay vì chỉ đọc hàng `acl_entry` cục bộ.

### 8.4. Quyền chia sẻ theo group và SID authority

`GrantedAuthoritySid("ROLE_TEAM_EDITOR")` cấp quyền cho tập người có authority đó. Đường API cho group share phải xác minh nhóm thuộc đúng tenant và caller được phép cấp cho **toàn bộ tập**. Không cho client truyền một SID string không có whitelist vì có thể dẫn đến cấp cho `ROLE_EVERYONE` hoặc một nhóm nhạy cảm.

Tách action `share:principal` khỏi `share:group` nếu mức rủi ro khác nhau. Với nhóm động, membership thay đổi có thể làm đối tượng nhận quyền mở rộng mà không có ACE mới; cần audit group membership.

### 8.5. Granular permissions và chống tăng quyền

Nếu người chia sẻ chỉ có VIEWER, không được tự cấp EDITOR. Nếu chính sách cho phép EDITOR chia sẻ, tối thiểu phải yêu cầu quyền SHARE và không cho cấp mức mạnh hơn quyền của mình. Đặc biệt, **không đưa một phương thức công khai nhận `Permission` hoặc mask integer tùy ý** rồi gọi `acl.insertAce(index,mask,sid,true)`. Đầu vào phải được ràng buộc theo whitelist nghiệp vụ và kiểm tra trên tài nguyên thật.

### 8.6. Audit hành vi chia sẻ

Một log cấp/revoke quyền nên lưu:
- actor và identity xác thực;
- tenant id và document id;
- recipient SID type + SID value;
- old permission mask / new mask;
- loại sự kiện GRANTED, CHANGED, REVOKED, DENIED;
- thời điểm, request ID, lý do và policy version.

Hai cờ `audit_success`/`audit_failure` trên ACE không tự tạo lịch sử thay đổi ACE. `ConsoleAuditLogger` trong ví dụ là minh họa kỹ thuật, không đủ retention và bất biến audit cho sản phẩm thật. Nếu có yêu cầu tuân thủ, dùng audit log bền vững, chống sửa và thiết kế xử lý lỗi audit rõ ràng.

### 8.7. Transaction và thông báo sau khi commit

Một request có thể vừa cấp share vừa gửi email mời. Nếu gửi email **trước khi transaction commit** và DB rollback, người nhận có thể nhận link không hợp lệ. Nếu gửi email sau commit nhưng process crash trước khi gửi, sự kiện có thể bị mất. Với yêu cầu giao nhận ổn định, dùng transactional outbox hoặc cơ chế retry/idempotency.

**Điểm then chốt:** Đừng dùng `@PostAuthorize` để quyết định người được chia sẻ sau khi đã sửa ACL. Kiểm tra policy trước khi gọi mutator, và chỉ phát notification sau khi thay đổi được ủy quyền đã commit thành công.

## 9. Lỗi thường gặp và sửa như thế nào

| Sai lầm | Kết quả | Cách xử lý |
|---|---|---|
| Dùng `BasePermission.WRITE` như quyền chia sẻ | Editor có thể tự nâng quyền cho người khác | Tách share/ACL admin khỏi business WRITE |
| Gọi `insertAce` mà không kiểm tra actor | API chia sẻ bị lạm dụng | `@PreAuthorize` + `AclAuthorizationStrategy` |
| Có `ROLE_TENANT_ADMIN` là tự đủ sửa mọi ACL | Mở rộng ngoài tenant/object | Role binding theo tenant và ADMINISTRATION ACE hoặc chính sách ACL admin đã chứng minh |
| Bỏ `validateRecipient` | Chia sẻ cho user khác tenant/không tồn tại | Validate grantee từ directory tin cậy |
| Dùng `updateAce(index, WRITE)` để nâng EDITOR | Người nhận có thể mất READ | Dùng mask 3 hoặc hai ACE rõ ràng |
| Chỉ biết `ace_order` cũ rồi update | Sửa nhầm ACE sau insert/delete | Đọc ACL mới, tìm theo SID và policy |
| Dùng ACE deny để thu hồi grant | Có thể gây hiệu ứng precedence/inheritance ngoài ý muốn | `deleteAce` khi thực sự chỉ muốn bỏ grant |
| Sửa nhiều ACE mà xóa từ đầu đến cuối | Index dời, xóa nhầm | Duyệt từ cuối về đầu |
| Gọi `updateAcl` mà tưởng chỉ UPDATE một row | ACE PK đổi, lost update | Hiểu JDBC persistence và bảo vệ concurrency |
| Ghi trực tiếp `acl_entry` không evict cache | Revoke không phản ánh ngay | Dùng service, kiểm tra cache eviction |
| Cho client truyền `Sid` hoặc mask thô | Có thể cấp ADMINISTRATION hoặc group rộng | Whitelist recipient type và share level |
| ACL owner và document owner bị lệch | Quyền quản trị gây bất ngờ | Workflow đổi owner/tenant nguyên tử |
| Bỏ qua quyền kế thừa | Revoke rồi user vẫn truy cập | Kiểm tra parent/inheritance/role ACE |
| Chỉ bảo vệ HTTP endpoint | Service gọi từ job có thể bypass | Kiểm tra tại service boundary |
| Self-invocation trong cùng bean | Bỏ qua Spring AOP | Gọi qua Spring-managed proxy |
| Không có ACL khi tạo document | Không truy cập được hoặc phát sinh lỗi | Khởi tạo ACL có chủ đích khi tạo resource |
| Cache không gắn scope/policy version | Dùng quyết định cũ/sai tenant | Thiết kế invalidation/versioning phù hợp |
| Nắm username nhưng không biết tenant | Chia sẻ xuyên tổ chức | Kiểm tra trên document canonical và tenant directory |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Bob có ACE WRITE trên Document#101. Bob có tự gọi API chia sẻ để cấp WRITE cho Mallory không?

**Trả lời:** Không theo chính sách bài học. WRITE là quyền chỉnh sửa nội dung, còn chia sẻ cần owner/tenant-admin policy và quyền sửa ACL thích hợp. Không được suy quyền quản trị ACL từ business WRITE.

**Câu 2.** `updateAce(index, BasePermission.WRITE)` có thể khiến Bob mất quyền đọc không?

**Trả lời:** Có. Nó thay permission mask của ACE; READ bit có thể không còn. Để biểu diễn EDITOR có cả READ và WRITE, dùng hai ACE hoặc `CumulativePermission` với mask 3 và test.

**Câu 3.** Sau `revokeShare(101L,"bob")`, Bob còn có thể đọc nếu ACL cha cấp READ cho role mà Bob sở hữu?

**Trả lời:** Có thể. Revoke chỉ xóa grant cá nhân; ACL inheritance hoặc authority SID khác vẫn là nguồn quyền. Test tổng hợp các nguồn trước khi tuyên bố deny hoàn toàn.

**Câu 4.** Tenant admin vượt policy nghiệp vụ nhưng không phải ACL owner và không có ADMINISTRATION ACE; cập nhật ACL có luôn thành công không?

**Trả lời:** Không. `AclAuthorizationStrategyImpl` còn thực hiện kiểm tra riêng trên các phương thức sửa ACL; bài test minh họa trường hợp này.

**Câu 5.** Vì sao không dùng `acl_entry.id` làm ID ổn định của share?

**Trả lời:** Với `JdbcMutableAclService.updateAcl`, toàn bộ ACE có thể bị xóa và tạo lại; PK thay đổi. Grant cần được xác định theo object identity, SID, permission/action và chính sách duy nhất rõ ràng.

## 11. Checklist triển khai an toàn

- [ ] Xác định rõ actor nào có quyền quản lý ACL; owner và tenant-admin có phạm vi cụ thể.
- [ ] `@EnableMethodSecurity` đã bật và service được gọi qua Spring-managed proxy.
- [ ] `AclAuthorizationStrategy` được cấu hình tách biệt với quyền nghiệp vụ; không cấp authority system-wide quá rộng.
- [ ] ObjectIdentity dùng đúng class + ID; ACL phải được tạo/đọc qua `MutableAclService`.
- [ ] Recipient đã được xác minh, ở đúng tenant, không tự nhận role/group do client khai.
- [ ] API chia sẻ chỉ cho các mức quyền whitelist; không chấp nhận mask thô hoặc ADMINISTRATION qua cùng endpoint.
- [ ] `insertAce` dùng index trong list, `updateAce` chỉ thay mask, `deleteAce` xóa đúng index.
- [ ] Mọi thay đổi persist qua `updateAcl` trong transaction phù hợp.
- [ ] Có chính sách giải quyết duplicate ACE/deny ACE/inheritance; không silently phá dữ liệu lạ.
- [ ] Có concurrency control khi nhiều request cùng sửa một ACL.
- [ ] Test thực tế allow/deny, viewer/editor, nâng/hạ cấp, thu hồi, người ngoài tenant, role admin thiếu ACE và owner chưa có READ.
- [ ] Cache/cluster có chiến lược revoke và invalidation.
- [ ] Audit hành động chia sẻ bền vững, có actor, recipient, old/new permission, target, lý do.
- [ ] Mọi luồng đọc/ghi dữ liệu đều kiểm tra tenant và business permissions; ACL không mặc định bảo vệ tenant boundary.

## 12. Tài liệu chính thức

- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): thao tác `insertAce`, `MutableAclService`, quyền trên domain object và cấu hình ACL.
- [Spring Security 6.5 — MutableAcl API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/model/MutableAcl.html): `insertAce`, `updateAce`, `deleteAce`, `setOwner`, `setParent`.
- [Spring Security 6.5 — AclAuthorizationStrategyImpl API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/domain/AclAuthorizationStrategyImpl.html): owner, system-wide authority và `BasePermission.ADMINISTRATION` khi sửa ACL.
- [Spring Security 6.5 — JdbcMutableAclService API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/jdbc/JdbcMutableAclService.html): `createAcl`, `updateAcl`, `deleteAcl` và persistence semantics.
- [Spring Security 6.5 — Security Database Schema](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html): bốn bảng ACL và DDL HSQLDB.
- [Spring Security 6.5 — CumulativePermission API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/domain/CumulativePermission.html): biểu diễn quyền theo nhiều bit.
- [Spring Security 6.5 — DefaultPermissionGrantingStrategy API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html): thứ tự ACE, quyết định grant/deny và so khớp permission.

**Ghi nhớ:** `insertAce`, `updateAce` và `deleteAce` chỉ là các thao tác dữ liệu ACL. Một hệ thống chia sẻ an toàn cần kiểm tra **người gọi có quyền chia sẻ, người nhận hợp lệ, mức quyền được cấp không quá phạm vi, transaction/cache nhất quán và hành vi thu hồi thật sự**, bên cạnh kiểm tra quản trị ACL của framework. Quyền sửa nội dung không tự trao quyền quản trị ACE; tenant admin không được phép vượt tenant boundary chỉ vì có role admin.