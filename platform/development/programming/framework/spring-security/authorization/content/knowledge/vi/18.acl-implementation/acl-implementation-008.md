# Xóa đối tượng, xóa ACL và tính nhất quán giao dịch trong Spring Security

## 1. Bài toán: xóa một tài liệu chưa chắc đã xóa quyền truy cập

Giả sử ứng dụng có một tài liệu `Document#101` thuộc tenant `t1`, một hàng dữ liệu nghiệp vụ `document`, một hàng `acl_object_identity` và một ACE trong `acl_entry` cấp Bob quyền READ. Khi Alice yêu cầu xóa tài liệu, điều gì sẽ xảy ra nếu chỉ xóa từ bảng nghiệp vụ?

```java
documentRepository.deleteById(101L);
```

Dòng này là ví dụ API, không phải chương trình biên dịch độc lập. **ACL vẫn có thể tồn tại** vì schema Spring Security ACL mặc định không đặt foreign key từ `acl_object_identity.object_id_identity` đến mỗi bảng domain. Hàng ACL mồ côi có thể gây nhiễu audit/cache, và đặc biệt nguy hiểm nếu ID domain được tái sử dụng: một tài liệu mới mang cùng `ObjectIdentity` có thể chịu tác động của ACE cũ.

Trường hợp ngược lại cũng nguy hiểm:

```java
mutableAclService.deleteAcl(
    new ObjectIdentityImpl(Document.class, 101L), false
);
```

Lệnh này xóa **dữ liệu ACL**, không tự gọi `DELETE FROM document`. Nếu bước xóa domain phía sau thất bại và hai bước không cùng transaction, bản ghi vẫn sống nhưng quyền theo ACL đã biến mất.

**Mục tiêu bài học:** thực hiện xóa domain object và ACL **cùng nhau hoặc rollback cùng nhau**, có phân biệt ACL con/domain con, kiểm soát actor được phép xóa, xử lý lỗi, cache và tác động ngoài transaction. Nội dung áp dụng cho Spring Security ACL 6.5.x, Java 17 và Spring Boot 3.5.x.

## 2. Hai vòng đời khác nhau

Spring Security ACL dùng bốn bảng:

| Bảng | Lưu gì? |
|---|---|
| `acl_sid` | SID của principal hoặc authority có thể nhận quyền |
| `acl_class` | Loại Java/domain object được bảo vệ |
| `acl_object_identity` | ACL cho một instance `(type, domain ID)`; có owner, parent và cờ inheritance |
| `acl_entry` | ACE: SID, permission mask, granting/denying, thứ tự và audit flags |

Ví dụ:

```text
document:
  id=101, tenant=t1, owner=alice, title=Leaf

acl_class:
  id=7, class=com.example.acldelete.Document

acl_object_identity:
  id=11, object_id_class=7, object_id_identity=101,
  parent_object=NULL, owner_sid=1, entries_inheriting=FALSE

acl_entry:
  id=101, acl_object_identity=11, ace_order=0,
  sid=2 (bob), mask=1 (READ), granting=TRUE
```

Phân biệt **ACL primary key** `acl_object_identity.id=11` với **domain ID** `object_id_identity=101`. `acl_entry.acl_object_identity` trỏ đến 11, không trỏ thẳng đến `document.id=101`. Không có quan hệ FK mặc định buộc một domain row và ACL tồn tại/biến mất đồng thời; service chịu trách nhiệm điều phối.

### 2.1. Hai dạng dữ liệu lỗi

| Trạng thái | Nguyên nhân | Hệ quả |
|---|---|---|
| Domain đã mất, ACL còn | Chỉ xóa `document` | Orphan ACL, ACE cũ có thể ảnh hưởng khi tái sử dụng ID |
| Domain còn, ACL đã mất | Xóa ACL rồi xóa domain thất bại ngoài transaction | `hasPermission` có thể deny vì không tìm thấy ACL |
| Cả hai còn | Xóa bị chặn hoặc rollback đúng | Dữ liệu/ACL nhất quán với trạng thái ban đầu |
| Cả hai mất | Xóa vật lý được ủy quyền và commit đúng | Đích mong muốn cho thao tác xóa vật lý hoàn chỉnh |

Schema ACL mặc định không tự tạo/xóa ACL khi JPA/JDBC repository lưu/xóa domain object. Spring Security khuyến nghị ứng dụng tích hợp lifecycle ACL ở tầng service.

### 2.2. Khi nào không nên xóa ACL?

**Soft delete** thường chỉ đổi `deleted_at`/`status=DELETED` để phục hồi hoặc tuân thủ retention. Khi đó có thể giữ ACL làm lịch sử, nhưng mọi đường truy cập phải từ chối nội dung đã soft-delete. `AclPermissionEvaluator` chỉ xét ACL; nó không tự biết domain record đã bị đánh dấu xóa. Với tài liệu bị legal hold, thường phải từ chối hard-delete bất kể chủ sở hữu hay quyền ACL.

## 3. MutableAclService.deleteAcl và cờ deleteChildren

Spring Security 6.5 công bố:

```java
void deleteAcl(
    ObjectIdentity objectIdentity,
    boolean deleteChildren
) throws ChildrenExistException;
```

Đây là chữ ký API rút gọn. `ObjectIdentityImpl(Document.class, id)` ánh xạ type đầy đủ và ID; phải khớp cách tạo ACL và cột `acl_class.class`. Không nhầm type `"Document"` với tên đầy đủ nếu lookup được cấu hình dựa trên FQCN.

### 3.1. deleteChildren=false

```java
ObjectIdentity oid = new ObjectIdentityImpl(Document.class, 101L);
mutableAclService.deleteAcl(oid, false);
```

Với ACL không có con, JDBC implementation xóa các ACE của ACL rồi xóa hàng `acl_object_identity`. Metadata `acl_class` hoặc `acl_sid` được dùng chung có thể vẫn còn; **không nên xóa SID/class chỉ vì một object biến mất**.

Nếu ACL có con, API ném `ChildrenExistException`. Đây là cơ chế bảo vệ cấu trúc ACL; nếu lệnh nằm trong transaction thì exception unchecked có thể làm rollback.

### 3.2. deleteChildren=true

```java
mutableAclService.deleteAcl(oid, true);
```

Nó cho phép xóa **nhánh ACL con**. Nó **không** có nhiệm vụ xóa domain children, file, search index, email, dòng queue hoặc dữ liệu ở một database khác. Nếu Document#100 có ACL child Document#102, lệnh `deleteAcl(oid(100),true)` có thể xóa ACL của 100 và 102, nhưng vẫn để nguyên hai hàng `document`. Đó là điều phải kiểm thử.

**Không dùng true chỉ để “tránh lỗi ChildrenExistException”**. Một thao tác xóa subtree thật sự phải thu thập toàn bộ descendants, kiểm tra quyền trên từng đối tượng, legal hold, tenant scope, xóa domain rows theo thứ tự FK (thường leaf trước parent) và xóa ACL subtree trong cùng transaction.

### 3.3. Những lỗi cần phân biệt

| Ngoại lệ | Phản ánh điều gì? | Xử lý |
|---|---|---|
| `ChildrenExistException` | ACL parent còn ACL child, gọi với `false` | Từ chối, reparent hoặc thiết kế xóa cả nhánh |
| `NotFoundException` của ACL | ObjectIdentity không có ACL | Fail-closed; không âm thầm xóa domain |
| `DataIntegrityViolationException` | FK/constraint của DB không cho phép xóa | Kiểm tra domain children, FK hoặc thứ tự DML |
| `AccessDeniedException` | Actor thiếu quyền xóa | Không chạy target method |
| Runtime exception sau các bước DML | Lỗi transaction | Rollback nếu exception đến transaction interceptor trước commit |

`AclAuthorizationStrategy` là thành phần liên quan đến quyền sửa các MutableAcl. Không được mặc định coi `MutableAclService.deleteAcl` là policy bảo vệ tenant, owner, retention hoặc business DELETE. **Ứng dụng phải kiểm tra quyền xóa domain một cách tường minh**.

## 4. Transaction bao quanh cả ACL và domain

Mẫu an toàn về mặt kiến trúc:

```java
@Transactional
@PreAuthorize("@deletePolicy.canDelete(authentication, #id)")
public void deleteDocument(@P("id") Long id) {
    Document document = repository.require(id);
    ObjectIdentity oid = new ObjectIdentityImpl(Document.class, id);

    aclService.readAclById(oid);
    aclService.deleteAcl(oid, false);

    int changed = repository.deleteMatching(document);
    if (changed != 1) {
        throw new IllegalStateException("Record changed");
    }
}
```

Đây là **mẫu service**, cần đủ bean, imports và class để chạy. Cách làm:
1. Authorize người gọi trước khi target method thực thi.
2. Đọc domain record canonical và ACL tồn tại.
3. Xóa ACL và ACE.
4. Xóa domain row có predicate owner/tenant đáng tin.
5. Commit cả hai; nếu exception phát sinh trước commit, rollback cả hai.

`@Transactional` đạt mục tiêu khi **cả `JdbcMutableAclService` và domain repository sử dụng cùng DataSource/transaction manager** và không có `REQUIRES_NEW` hay auto-commit độc lập. Nếu ACL ở database A còn domain ở database B, một annotation gắn với manager A không tạo transaction nguyên tử trên cả hai.

### 4.1. Vì sao không xóa domain rồi trả HTTP 200 ngay?

Một HTTP response không phải bằng chứng DB nhất quán. Phải kiểm tra sau commit:
- Domain row biến mất.
- ACL object identity biến mất.
- ACE của ACL biến mất.
- Mọi ACL child/domain child được xử lý theo chính sách.
- Cache không trả quyền trên object đã bị xóa.
- External side effects được điều phối riêng.

### 4.2. Thứ tự xóa nào đúng?

Với một ACL leaf đơn giản, có thể xóa ACL trước rồi xóa domain trong **cùng transaction**. Nếu `deleteAcl(false)` từ chối vì ACL con, domain chưa bị đụng tới. Nếu domain DELETE thất bại sau khi đã xóa ACL, rollback vẫn phục hồi ACL.

Tuy nhiên FK đặc thù có thể buộc một thứ tự khác; điểm cốt lõi là cùng transaction. Đừng tách làm hai transactions rồi hy vọng một exception sẽ rollback commit trước đó.

### 4.3. Rollback rules và catch exception

Với Spring Framework 6.x, rollback mặc định trên `RuntimeException` và `Error` khi các exception truyền ra transaction interceptor. Checked exception thường cần `rollbackFor`:

```java
@Transactional(rollbackFor = Exception.class)
public void deleteWithCheckedFailure() throws Exception {
    // Lỗi checked Exception đi ra ngoài cũng rollback
}
```

Nếu bạn bắt exception rồi trả bình thường, transaction advice có thể không biết phải rollback. Không viết:

```java
@Transactional
public void unsafeDelete() {
    try {
        aclService.deleteAcl(oid, false);
    } catch (Exception ex) {
        logger.warn("ACL error", ex);
    }
    repository.deleteById(id);
}
```

Đây là **phản ví dụ**, chưa độc lập vì thiếu biến/bean. Nó có thể xóa domain dù ACL delete lỗi. Khi có lỗi phải fail-closed, ném exception ra ngoài transaction hoặc chủ động đánh dấu rollback-only nếu đã có quy trình xử lý phù hợp.

### 4.4. AOP, TOCTOU và concurrency

`@PreAuthorize` trong Spring Security 6.x thường nằm ngoài transaction advice theo thứ tự mặc định; chính sách có thể được kiểm tra trước khi transaction bắt đầu. Nếu owner/tenant thay đổi giữa authorize và DELETE thì có nguy cơ **TOCTOU**. Ví dụ runnable bên dưới recheck trong transaction và dùng predicate ID/tenant/owner, nhưng production cần thêm row lock, version, isolation hoặc query có điều kiện chặt hơn tùy rủi ro.

`@Transactional` và `@PreAuthorize` không chạy nếu caller bỏ qua Spring proxy theo cách self-invocation. Không tự tạo service bằng `new` rồi kỳ vọng annotation có tác dụng.

## 5. Quan hệ ACL con khác quan hệ domain con

```text
Business domain tree             ACL inheritance tree

Document#100                     ACL(Document#100)
   └── Document#102                 └── ACL(Document#102)
       parent_id=100                  parent_object=10
```

Bài học dùng hai cây cùng dạng để dễ kiểm tra, nhưng Spring Security không bắt chúng trùng nhau. Quan hệ `document.parent_id` có FK nghiệp vụ; quan hệ `acl_object_identity.parent_object` có self-FK ACL. Việc đặt `entries_inheriting=true` cho child cho phép xét ACE cha theo ACL policy, nhưng không tự tạo quan hệ domain.

Khi xóa parent:
- `deleteAcl(parent,false)` ném `ChildrenExistException` nếu còn ACL child.
- SQL `DELETE document(parent)` có thể ném `DataIntegrityViolationException` nếu còn domain child.
- `deleteAcl(parent,true)` có thể dọn ACL subtree, **không** dọn domain subtree.
- Nếu chỉ muốn giữ child mà xóa parent, xem xét reparent ACL và domain child có kiểm soát, kiểm tra lại quyền sau inheritance changes.

Với multi-tenant, không được xóa ACL child thuộc tenant khác chỉ vì có thể truy cập ACL parent; trước khi xóa subtree phải verify mọi resource descendant.

## 6. Java 17 + Spring Boot 3.5.6 + HSQLDB: dự án chạy được

Ví dụ dùng database HSQLDB trong bộ nhớ và JDBC thực cho **cả domain lẫn Spring Security ACL**. Mục tiêu là kiểm tra xóa thành công, rollback có chủ đích, ACL/domain children, orphan và quyền người gọi. Không cần web server hoặc JWT.

### 6.1. Cây file

```text
acl-delete-consistency/
  pom.xml
  src/main/java/com/example/acldelete/
    AclDeleteApplication.java
    Document.java
    DocumentRepository.java
    DeletePolicy.java
    AclConfig.java
    DocumentDeletionService.java
    DocumentReadService.java
  src/main/resources/
    schema.sql
    data.sql
  src/test/java/com/example/acldelete/
    AclDeletionIntegrationTest.java
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
  <artifactId>acl-delete-consistency</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
      <artifactId>spring-boot-starter-aop</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-acl</artifactId>
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
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

Spring Boot 3.5.6 quản lý dependency Spring Security 6.5.x tương thích; không ép một version riêng cho `spring-security-acl`. Demo không dùng tính năng của Spring Security 7.

### 6.3. schema.sql

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE document (
  id BIGINT PRIMARY KEY,
  tenant_id VARCHAR(64) NOT NULL,
  owner_username VARCHAR(100) NOT NULL,
  parent_id BIGINT,
  title VARCHAR(255) NOT NULL,
  FOREIGN KEY(parent_id) REFERENCES document(id)
);

CREATE TABLE tenant_membership (
  tenant_id VARCHAR(64) NOT NULL,
  username VARCHAR(100) NOT NULL,
  PRIMARY KEY(tenant_id, username)
);

CREATE TABLE tenant_admin (
  tenant_id VARCHAR(64) NOT NULL,
  username VARCHAR(100) NOT NULL,
  PRIMARY KEY(tenant_id, username),
  FOREIGN KEY(tenant_id, username)
    REFERENCES tenant_membership(tenant_id, username)
);

CREATE TABLE acl_sid (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 5000)
    PRIMARY KEY,
  principal BOOLEAN NOT NULL,
  sid VARCHAR_IGNORECASE(100) NOT NULL,
  UNIQUE(sid, principal)
);

CREATE TABLE acl_class (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 5000)
    PRIMARY KEY,
  class VARCHAR_IGNORECASE(100) NOT NULL,
  UNIQUE(class)
);

CREATE TABLE acl_object_identity (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 5000)
    PRIMARY KEY,
  object_id_class BIGINT NOT NULL,
  object_id_identity VARCHAR_IGNORECASE(36) NOT NULL,
  parent_object BIGINT,
  owner_sid BIGINT,
  entries_inheriting BOOLEAN NOT NULL,
  UNIQUE(object_id_class, object_id_identity),
  FOREIGN KEY(object_id_class) REFERENCES acl_class(id),
  FOREIGN KEY(parent_object) REFERENCES acl_object_identity(id),
  FOREIGN KEY(owner_sid) REFERENCES acl_sid(id)
);

CREATE TABLE acl_entry (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 5000)
    PRIMARY KEY,
  acl_object_identity BIGINT NOT NULL,
  ace_order INTEGER NOT NULL,
  sid BIGINT NOT NULL,
  mask INTEGER NOT NULL,
  granting BOOLEAN NOT NULL,
  audit_success BOOLEAN NOT NULL,
  audit_failure BOOLEAN NOT NULL,
  UNIQUE(acl_object_identity, ace_order),
  FOREIGN KEY(acl_object_identity) REFERENCES acl_object_identity(id),
  FOREIGN KEY(sid) REFERENCES acl_sid(id)
);
```

Đây là schema **HSQLDB** có cùng cột/quan hệ ACL mặc định. PostgreSQL, MySQL, SQL Server hoặc Oracle dùng identity syntax và cấu hình truy vấn ID khác. Production nên dùng migration và DDL khớp với version ACL đang chạy. HSQLDB schema được chọn để test đúng Spring Security JDBC implementation, không chỉ mô phỏng ACL bằng một map.

### 6.4. data.sql

**`src/main/resources/data.sql`**

```sql
INSERT INTO document VALUES (100,'t1','alice',NULL,'Root');
INSERT INTO document VALUES (101,'t1','alice',NULL,'Leaf');
INSERT INTO document VALUES (102,'t1','alice',100,'Child');
INSERT INTO document VALUES (200,'t2','carol',NULL,'Other tenant');
INSERT INTO document VALUES (300,'t1','alice',NULL,'Missing ACL');

INSERT INTO tenant_membership VALUES ('t1','alice');
INSERT INTO tenant_membership VALUES ('t1','bob');
INSERT INTO tenant_membership VALUES ('t1','manager1');
INSERT INTO tenant_membership VALUES ('t2','carol');
INSERT INTO tenant_membership VALUES ('t2','dave');

INSERT INTO tenant_admin VALUES ('t1','manager1');

INSERT INTO acl_sid(id,principal,sid) VALUES (1,TRUE,'alice');
INSERT INTO acl_sid(id,principal,sid) VALUES (2,TRUE,'bob');
INSERT INTO acl_sid(id,principal,sid) VALUES (3,TRUE,'carol');
INSERT INTO acl_sid(id,principal,sid) VALUES (4,TRUE,'manager1');

INSERT INTO acl_class(id,class)
VALUES (7,'com.example.acldelete.Document');

INSERT INTO acl_object_identity(
  id,object_id_class,object_id_identity,
  parent_object,owner_sid,entries_inheriting
) VALUES (10,7,'100',NULL,1,FALSE);
INSERT INTO acl_object_identity(
  id,object_id_class,object_id_identity,
  parent_object,owner_sid,entries_inheriting
) VALUES (11,7,'101',NULL,1,FALSE);
INSERT INTO acl_object_identity(
  id,object_id_class,object_id_identity,
  parent_object,owner_sid,entries_inheriting
) VALUES (12,7,'102',10,1,TRUE);
INSERT INTO acl_object_identity(
  id,object_id_class,object_id_identity,
  parent_object,owner_sid,entries_inheriting
) VALUES (20,7,'200',NULL,3,FALSE);

-- Bob đọc leaf #101.
INSERT INTO acl_entry(
  id,acl_object_identity,ace_order,sid,
  mask,granting,audit_success,audit_failure
) VALUES (101,11,0,2,1,TRUE,FALSE,FALSE);

-- Alice đọc root #100.
INSERT INTO acl_entry(
  id,acl_object_identity,ace_order,sid,
  mask,granting,audit_success,audit_failure
) VALUES (102,10,0,1,1,TRUE,FALSE,FALSE);

-- Bob đọc child #102.
INSERT INTO acl_entry(
  id,acl_object_identity,ace_order,sid,
  mask,granting,audit_success,audit_failure
) VALUES (103,12,0,2,1,TRUE,FALSE,FALSE);

-- Carol đọc document #200.
INSERT INTO acl_entry(
  id,acl_object_identity,ace_order,sid,
  mask,granting,audit_success,audit_failure
) VALUES (104,20,0,3,1,TRUE,FALSE,FALSE);
```

Có năm domain rows nhưng chỉ bốn ACLs: `Document#300` cố ý thiếu ACL để test fail-closed. ACL của Document#102 là child của ACL Document#100, không phải child của ACL Document#101. Các ID ACL seed nằm dưới 5000, tách khỏi ID auto-generated.

### 6.5. Application và domain

**`src/main/java/com/example/acldelete/AclDeleteApplication.java`**

```java
package com.example.acldelete;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AclDeleteApplication {
    public static void main(String[] args) {
        SpringApplication.run(AclDeleteApplication.class, args);
    }
}
```

**`src/main/java/com/example/acldelete/Document.java`**

```java
package com.example.acldelete;

public record Document(
        Long id,
        String tenantId,
        String owner,
        Long parentId,
        String title) {
    public Long getId() {
        return id;
    }
}
```

### 6.6. DocumentRepository

**`src/main/java/com/example/acldelete/DocumentRepository.java`**

```java
package com.example.acldelete;

import java.util.List;
import java.util.NoSuchElementException;
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
            SELECT id,tenant_id,owner_username,parent_id,title
            FROM document WHERE id = ?
            """,
            (rs, n) -> new Document(
                rs.getLong("id"),
                rs.getString("tenant_id"),
                rs.getString("owner_username"),
                rs.getObject("parent_id", Long.class),
                rs.getString("title")
            ),
            id
        );
        return rows.isEmpty() ? null : rows.get(0);
    }

    public Document require(Long id) {
        Document d = find(id);
        if (d == null) {
            throw new NoSuchElementException("Missing document");
        }
        return d;
    }

    public int deleteMatching(Document d) {
        return jdbc.update(
            """
            DELETE FROM document
            WHERE id=? AND tenant_id=? AND owner_username=?
            """,
            d.id(), d.tenantId(), d.owner()
        );
    }
}
```

`deleteMatching` dùng predicate tenant/owner từ record canonical (không dùng header/request làm nguồn quyền), và trả affected rows để service phát hiện record biến đổi. Đây **chưa** thay thế row lock/version hoặc isolation phù hợp khi nhiều request đồng thời thay ACL/owner.

### 6.7. DeletePolicy: chỉ owner hoặc tenant admin thật được xóa

**`src/main/java/com/example/acldelete/DeletePolicy.java`**

```java
package com.example.acldelete;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component("deletePolicy")
public class DeletePolicy {
    private final JdbcTemplate jdbc;
    private final DocumentRepository docs;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public DeletePolicy(JdbcTemplate jdbc, DocumentRepository docs) {
        this.jdbc = jdbc;
        this.docs = docs;
    }

    public boolean inTenant(Authentication auth, Long id) {
        if (auth == null || !auth.isAuthenticated()
                || trust.isAnonymous(auth)) {
            return false;
        }
        Document d = docs.find(id);
        if (d == null) {
            return false;
        }
        String username = auth.getName();
        String tenant = d.tenantId();

        Integer count = jdbc.queryForObject(
            """
            SELECT COUNT(*) FROM tenant_membership
            WHERE tenant_id=? AND username=?
            """,
            Integer.class, tenant, username
        );

        return count != null && count > 0
            && hasAuthority(auth, "tenant:" + tenant);
    }

    public boolean canDelete(Authentication auth, Long id) {
        if (!inTenant(auth, id)) {
            return false;
        }

        Document d = docs.find(id);
        String username = auth.getName();

        if (username.equals(d.owner())) {
            return true;
        }

        Integer admins = jdbc.queryForObject(
            """
            SELECT COUNT(*) FROM tenant_admin
            WHERE tenant_id=? AND username=?
            """,
            Integer.class, d.tenantId(), username
        );

        return admins != null && admins > 0
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

Policy chỉ cho phép:
- owner đang là thành viên tenant với authority tenant đúng;
- hoặc tenant admin có **cả** role `ROLE_TENANT_ADMIN` lẫn binding server-side trong `tenant_admin` của tenant hiện tại.

Vì vậy user giả mạo authority trong Authentication test mà không có membership/binding ở database vẫn bị từ chối. Production phải bảo đảm Authentication được tạo bởi provider đáng tin cậy, thêm retention/legal hold checks và hành vi khi tenant/owner đổi.

### 6.8. ACL Configuration

**`src/main/java/com/example/acldelete/AclConfig.java`**

```java
package com.example.acldelete;

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
import org.springframework.security.acls.model.MutableAclService;
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
            AclService service) {
        return new AclPermissionEvaluator(service);
    }

    @Bean
    MutableAclService mutableAclService(
            DataSource dataSource,
            LookupStrategy lookup,
            AclCache cache) {
        return new JdbcMutableAclService(dataSource, lookup, cache);
    }

    @Bean
    LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache cache,
            AclAuthorizationStrategy authorization,
            PermissionGrantingStrategy granting) {
        return new BasicLookupStrategy(
            dataSource, cache, authorization, granting
        );
    }

    @Bean
    AclCache aclCache(
            PermissionGrantingStrategy granting,
            AclAuthorizationStrategy authorization) {
        return new SpringCacheBasedAclCache(
            new ConcurrentMapCache("aclCache"),
            granting,
            authorization
        );
    }

    @Bean
    AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_SYSTEM_ADMIN")
        );
    }

    @Bean
    PermissionGrantingStrategy permissionGrantingStrategy() {
        return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger()
        );
    }
}
```

`@EnableMethodSecurity` kích hoạt `@PreAuthorize`; `AclPermissionEvaluator` đánh giá `hasPermission(...)` của read service. `BasicLookupStrategy` và `SpringCacheBasedAclCache` đọc/cache ACL. `JdbcMutableAclService` sử dụng **cùng DataSource** của `JdbcTemplate` để transaction bảo vệ cả ACL DML và domain DML.

`ROLE_ACL_SYSTEM_ADMIN` chỉ là system-wide authority của ACL administration strategy ở cấu hình này, không thay thế tenant/owner policy. Demo không cấp authority này cho người dùng nào.

### 6.9. DocumentDeletionService: transaction thật

**`src/main/java/com/example/acldelete/DocumentDeletionService.java`**

```java
package com.example.acldelete;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentDeletionService {
    private final MutableAclService acls;
    private final DocumentRepository docs;
    private final DeletePolicy policy;

    public DocumentDeletionService(
            MutableAclService acls,
            DocumentRepository docs,
            DeletePolicy policy) {
        this.acls = acls;
        this.docs = docs;
        this.policy = policy;
    }

    @Transactional
    @PreAuthorize("@deletePolicy.canDelete(authentication, #id)")
    public void deleteDocument(
            @P("id") Long id, boolean simulateFailure) {

        Document d = docs.require(id);

        // Recheck trong transaction để giảm TOCTOU.
        if (!policy.canDelete(
                SecurityContextHolder.getContext().getAuthentication(),
                id)) {
            throw new AccessDeniedException("Permission changed");
        }

        ObjectIdentity identity =
            new ObjectIdentityImpl(Document.class, id);

        // Fail-closed nếu còn document nhưng thiếu ACL.
        acls.readAclById(identity);

        // Chỉ xóa một leaf ACL; không xóa ACL descendants.
        acls.deleteAcl(identity, false);

        // Domain DELETE và ACL DELETE nằm cùng JDBC transaction.
        int affected = docs.deleteMatching(d);
        if (affected != 1) {
            throw new IllegalStateException("Document changed");
        }

        // Công tắc cố ý gây lỗi để test rollback; bỏ trong sản phẩm.
        if (simulateFailure) {
            throw new IllegalStateException(
                "Simulated failure after both deletes"
            );
        }
    }
}
```

**Phân tích:** `@PreAuthorize` từ chối trước khi thân chạy. `@Transactional` bọc hai thao tác JDBC; ngoại lệ unchecked trước commit làm rollback. `readAclById` đảm bảo domain không bị xóa nếu thiếu ACL. `deleteAcl(false)` từ chối khi có ACL child. `deleteMatching` đòi đúng một domain row bị xóa. Cờ `simulateFailure` chỉ phục vụ bài kiểm thử, **không nên có trên API production**.

Quan trọng: nếu tách `deleteAcl` sang phương thức có `REQUIRES_NEW`, ACL có thể commit sớm và outer rollback không khôi phục được. Nếu dùng hai DataSource, phải xem lại transaction manager chứ không mặc định transaction có thể rollback xuyên DB.

### 6.10. DocumentReadService: ACL và tenant cùng quyết định

**`src/main/java/com/example/acldelete/DocumentReadService.java`**

```java
package com.example.acldelete;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentReadService {
    private final DocumentRepository docs;

    public DocumentReadService(DocumentRepository docs) {
        this.docs = docs;
    }

    @PreAuthorize(
        "@deletePolicy.inTenant(authentication, #id) and " +
        "hasPermission(#id, 'com.example.acldelete.Document', " +
        "T(org.springframework.security.acls.domain.BasePermission).READ)"
    )
    public String read(@P("id") Long id) {
        return docs.require(id).title();
    }
}
```

Chỉ `hasPermission` không tự bảo vệ tenant; ta phải ghép `inTenant` trước. Tham số `@P("id")` giúp SpEL tìm đúng `#id` ngay cả khi metadata tên tham số Java không được giữ trong bytecode.

## 7. Integration tests: rollback, child, orphan và từ chối quyền

Mỗi test khởi tạo embedded database mới bằng `@DirtiesContext(AFTER_EACH_TEST_METHOD)`. Điều này chậm nhưng dễ xác minh vì không có test nào phải dọn ACL cache/rows của test khác. Không đặt `@Transactional` lên test class, vì outer test transaction có thể che giấu thời điểm commit và rollback thật của service.

**`src/test/java/com/example/acldelete/AclDeletionIntegrationTest.java`**

```java
package com.example.acldelete;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.acls.domain.ObjectIdentityImpl;
import org.springframework.security.acls.model.ChildrenExistException;
import org.springframework.security.acls.model.MutableAclService;
import org.springframework.security.acls.model.NotFoundException;
import org.springframework.security.acls.model.ObjectIdentity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class AclDeletionIntegrationTest {
    @Autowired DocumentDeletionService deletion;
    @Autowired DocumentReadService reader;
    @Autowired MutableAclService acls;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager transactionManager;

    private static ObjectIdentity oid(long id) {
        return new ObjectIdentityImpl(Document.class, id);
    }

    private int domainRows(long id) {
        Integer n = jdbc.queryForObject(
            "SELECT COUNT(*) FROM document WHERE id = ?",
            Integer.class, id);
        return n.intValue();
    }

    private int aclRows(long id) {
        Integer n = jdbc.queryForObject(
            """
            SELECT COUNT(*)
            FROM acl_object_identity o
            JOIN acl_class c ON c.id=o.object_id_class
            WHERE c.class=? AND o.object_id_identity=?
            """,
            Integer.class,
            Document.class.getName(), String.valueOf(id));
        return n.intValue();
    }

    private int aceRows(long id) {
        Integer n = jdbc.queryForObject(
            """
            SELECT COUNT(*)
            FROM acl_entry e
            JOIN acl_object_identity o
              ON o.id=e.acl_object_identity
            JOIN acl_class c ON c.id=o.object_id_class
            WHERE c.class=? AND o.object_id_identity=?
            """,
            Integer.class,
            Document.class.getName(), String.valueOf(id));
        return n.intValue();
    }

    @Test
    @WithMockUser(username="alice", authorities="tenant:t1")
    void leafDeleteRemovesDomainAclAndAce() {
        assertEquals(1, domainRows(101));
        assertEquals(1, aclRows(101));
        assertEquals(1, aceRows(101));

        deletion.deleteDocument(101L, false);

        assertEquals(0, domainRows(101));
        assertEquals(0, aclRows(101));
        assertEquals(0, aceRows(101));
        assertThrows(NotFoundException.class,
            () -> acls.readAclById(oid(101)));
    }

    @Test
    @WithMockUser(username="alice", authorities="tenant:t1")
    void runtimeFailureRollsBackDomainAndAcl() {
        assertThrows(IllegalStateException.class,
            () -> deletion.deleteDocument(101L, true));

        assertEquals(1, domainRows(101));
        assertEquals(1, aclRows(101));
        assertEquals(1, aceRows(101));
        acls.readAclById(oid(101));
    }

    @Test
    @WithMockUser(username="alice", authorities="tenant:t1")
    void parentCannotBeDeletedWhileChildAclExists() {
        assertThrows(ChildrenExistException.class,
            () -> deletion.deleteDocument(100L, false));

        assertEquals(1, domainRows(100));
        assertEquals(1, domainRows(102));
        assertEquals(1, aclRows(100));
        assertEquals(1, aclRows(102));
    }

    @Test
    void aclCascadeDoesNotDeleteDomainObjects() {
        new TransactionTemplate(transactionManager)
            .executeWithoutResult(
                status -> acls.deleteAcl(oid(100), true));

        assertEquals(0, aclRows(100));
        assertEquals(0, aclRows(102));
        assertEquals(0, aceRows(100));
        assertEquals(0, aceRows(102));
        assertEquals(1, domainRows(100));
        assertEquals(1, domainRows(102));
    }

    @Test
    void directDomainDeleteLeavesOrphanAcl() {
        jdbc.update("DELETE FROM document WHERE id=?", 101L);
        assertEquals(0, domainRows(101));
        assertEquals(1, aclRows(101));
        assertEquals(1, aceRows(101));
    }

    @Test
    @WithMockUser(username="bob", authorities="tenant:t1")
    void readAceDoesNotAuthorizeDeletion() {
        assertEquals("Leaf", reader.read(101L));
        assertThrows(AccessDeniedException.class,
            () -> deletion.deleteDocument(101L, false));
        assertEquals(1, domainRows(101));
    }

    @Test
    @WithMockUser(username="manager1",
        authorities={"tenant:t1","ROLE_TENANT_ADMIN"})
    void tenantAdminDeletesLeafInOwnTenant() {
        deletion.deleteDocument(101L, false);
        assertEquals(0, domainRows(101));
        assertEquals(0, aclRows(101));
    }

    @Test
    @WithMockUser(username="manager1",
        authorities={"tenant:t1","ROLE_TENANT_ADMIN"})
    void tenantAdminCannotDeleteOtherTenant() {
        assertThrows(AccessDeniedException.class,
            () -> deletion.deleteDocument(200L, false));
        assertEquals(1, domainRows(200));
    }

    @Test
    @WithMockUser(username="carol", authorities="tenant:t2")
    void ownerMayDeleteFromOwnTenant() {
        deletion.deleteDocument(200L, false);
        assertEquals(0, domainRows(200));
        assertEquals(0, aclRows(200));
    }

    @Test
    @WithMockUser(username="alice")
    void missingTenantAuthorityDeniesDelete() {
        assertThrows(AccessDeniedException.class,
            () -> deletion.deleteDocument(101L, false));
        assertEquals(1, domainRows(101));
    }

    @Test
    @WithMockUser(username="mallory",
        authorities={"tenant:t1","ROLE_TENANT_ADMIN"})
    void forgedRoleWithoutMembershipIsDenied() {
        assertThrows(AccessDeniedException.class,
            () -> deletion.deleteDocument(101L, false));
        assertEquals(1, aclRows(101));
    }

    @Test
    @WithMockUser(username="manager1", authorities="tenant:t1")
    void tenantAdminBindingWithoutRoleIsInsufficient() {
        assertThrows(AccessDeniedException.class,
            () -> deletion.deleteDocument(101L, false));
    }

    @Test
    @WithMockUser(username="alice", authorities="tenant:t1")
    void nonexistentDocumentDeniesBeforeMutation() {
        assertThrows(AccessDeniedException.class,
            () -> deletion.deleteDocument(999L, false));
    }

    @Test
    @WithMockUser(username="alice", authorities="tenant:t1")
    void missingAclCannotSilentlyDeleteDomain() {
        assertEquals(1, domainRows(300));
        assertEquals(0, aclRows(300));
        assertThrows(NotFoundException.class,
            () -> deletion.deleteDocument(300L, false));
        assertEquals(1, domainRows(300));
    }

    @Test
    @WithMockUser(username="bob", authorities="tenant:t1")
    void bobCanReadBeforeAnyDeletion() {
        assertEquals("Leaf", reader.read(101L));
    }

    @Test
    @WithMockUser(username="alice", authorities="tenant:t1")
    void aclOwnerWithoutReadAceIsNotImplicitlyAllowed() {
        assertThrows(AccessDeniedException.class,
            () -> reader.read(101L));
    }

    @Test
    void domainForeignKeyAlsoBlocksParentDelete() {
        assertThrows(
            org.springframework.dao.DataIntegrityViolationException.class,
            () -> jdbc.update("DELETE FROM document WHERE id=?",100L));
        assertEquals(1, domainRows(100));
        assertEquals(1, domainRows(102));
    }
}
```

Chạy từ thư mục có `pom.xml`:

```bash
mvn test
```

**Kết quả kỳ vọng theo thiết kế:** 17 JUnit tests pass, không có failures/errors. Đây là kết quả **dự kiến**, không phải tuyên bố Maven đã chạy. Spring context, HSQLDB schema và cache khởi tạo lại sau mỗi test qua `@DirtiesContext`. Các test dùng `@WithMockUser` để thử authorization, không thay thế test xác minh JWT/password thật.

### 7.1. Ma trận quan sát

| Thử nghiệm | Domain | ACL/ACE | Chứng minh |
|---|---|---|---|
| Xóa leaf thành công | Xóa | Xóa | Hai tài nguyên cùng commit |
| Exception cố ý sau cả hai bước xóa | Còn | Còn | Rollback atomic trên cùng JDBC transaction |
| Xóa parent với `deleteChildren=false` | Còn parent/child | Còn cả hai ACL | Bị `ChildrenExistException` chặn |
| Chỉ gọi `deleteAcl(root,true)` | Còn parent/child | ACL cả nhánh mất | Cascade ACL không phải cascade domain |
| Chỉ xóa domain bằng SQL | Domain mất | ACL còn | Orphan ACL |
| Domain còn nhưng thiếu ACL | Còn | Thiếu | Fail-closed |
| Bob chỉ có READ ACE | Còn | Còn | READ không đồng nghĩa DELETE |
| Tenant admin khác tenant | Còn | Còn | Quản trị không vượt tenant scope |

Không kết luận “rollback thành công” chỉ từ HTTP 403, exception log hoặc sự tồn tại của một bảng; phải quan sát **cả domain rows, ACL identity rows và ACE rows** sau transaction.

## 8. Sản xuất thật: các rủi ro vượt ra ngoài demo

### 8.1. External side effects không rollback theo JDBC

Xóa file ở object storage, xóa search index, gửi email và publish message trực tiếp không tự tham gia JDBC transaction. Nếu DB rollback nhưng file đã xóa, dữ liệu không còn đồng bộ. Nếu DB commit nhưng tiến trình crash trước khi phát event, hệ thống khác không nhận được tin xóa.

Có thể dùng **transactional outbox**:

```text
BEGIN JDBC TRANSACTION
  ├── DELETE acl_entry + acl_object_identity
  ├── DELETE document
  └── INSERT outbox_event(DOCUMENT_DELETED, id=101)
COMMIT
      ↓
Worker đọc outbox đã commit
      ↓
Xóa file/index, gửi event, retry với idempotency key
```

Outbox giúp lưu ý định phát event cùng commit, không biến mạng và email thành một transaction nguyên tử. Với xóa file không thể đảo ngược, cân nhắc tombstone và trì hoãn xóa vật lý tới sau retention.

### 8.2. Transaction manager và REQUIRES_NEW

Nếu `aclService` dùng DataSource A nhưng domain repository dùng DataSource B, hoặc helper xóa ACL mở `REQUIRES_NEW` và commit riêng, rollback của transaction domain không phục hồi được ACL. Cần **cùng DataSource/TX** hoặc coordinator/phương án eventual consistency có reconciliation. Kiểm thử trên đúng production configuration, không suy luận từ annotation một mình.

### 8.3. Concurrent deletes, child mới và quyền đổi giữa chừng

Những race thường gặp:
- Owner/tenant đổi giữa `@PreAuthorize` và DELETE.
- Một request thêm ACL child khi request khác đang xóa ACL parent.
- Một request thêm ACE vào ACL sắp bị xóa.
- Hai request cùng xóa một ID và cùng thao tác cache.

Dùng row lock, optimistic version, FK, unique constraints, tenant-qualified DML, isolation phù hợp và kiểm tra affected-row count. Demo chỉ kiểm tra lại quyền trong transaction và predicate domain, chưa đảm bảo serializable outcome trong mọi cạnh tranh.

### 8.4. ACL cache, cluster và quyền cũ

JDBC ACL dùng cache. Cache eviction trong một JVM không đồng nghĩa cache của tất cả node đã đồng bộ, nhất là khi xóa rồi rollback. Cần invalidation theo sự kiện hoặc shared cache/TTL đã xác định, kiểm tra quyền sau revoke/delete trên nhiều node. Một cache hit ACL không thay việc kiểm tra domain record vẫn tồn tại và chưa soft-delete.

### 8.5. Soft delete, legal hold và audit

Nếu dữ liệu có retention hoặc legal hold, không xóa vật lý ngay chỉ vì owner yêu cầu. Dùng soft delete/tombstone và policy chặn đọc, giữ audit theo quy định. ACL metadata và `acl_sid` có thể vẫn liên quan tới điều tra lịch sử; dọn theo retention thay vì xoá mù. Log việc xóa với actor, object identity, tenant, lý do, thời gian, kết quả, affected rows và policy version; bảo vệ log khỏi chỉnh sửa trái phép.

### 8.6. Xóa batch và quản lý lifecycle

Đừng gọi method `@Transactional` trên cùng bean bằng `this.method()` rồi cho rằng mỗi thao tác được quản lý qua proxy. Với batch delete, xác định rõ atomic-all hoặc partial success, kiểm tra quyền trên **từng record**, điều phối ACL/domain children, giới hạn transaction size và quản lý retry. Đôi khi soft-delete trước và background purge có kiểm soát tốt hơn một transaction dài khóa nhiều ACL.

## 9. Checklist code review

- [ ] Có chính sách xóa theo tenant, owner/admin binding và trạng thái record.
- [ ] Xác thực người gọi qua Spring-managed proxy, không chỉ từ UI hoặc một HTTP route.
- [ ] Phân biệt ACL owner, ACE READ/WRITE và quyền xóa nghiệp vụ.
- [ ] Dùng đúng `ObjectIdentity(type, ID)` mà ACL đã lưu.
- [ ] Xác định có ACL con trước khi chọn `deleteChildren`.
- [ ] Không dùng `deleteChildren=true` để xóa nhầm domain subtree.
- [ ] ACL/domain cùng DataSource và transaction; không commit ACL trong `REQUIRES_NEW`.
- [ ] Exception truyền ra qua transaction interceptor với rollback rule phù hợp.
- [ ] Khi ACL thiếu, domain không bị xóa thầm; có kế hoạch khắc phục bất nhất.
- [ ] Domain delete có điều kiện và kiểm tra affected-row count.
- [ ] Kiểm tra FK domain và ACL, thứ tự DML, locking khi có concurrency.
- [ ] Cache và invalidation được thử sau commit/rollback và trên nhiều node nếu có.
- [ ] Soft delete vẫn bị chặn truy cập qua mọi service/query.
- [ ] File, broker, email, search index có outbox/retry/compensation.
- [ ] Integration test chứng minh domain + ACL + ACE cùng commit/rollback, không chỉ HTTP status.
- [ ] Có audit, retention và quy trình reconciliation orphan ACL.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Xóa bảng `document` có tự xóa các `acl_entry` tương ứng không?

**Trả lời:** Không theo schema ACL mặc định; `acl_object_identity` dùng type + domain ID nhưng không có FK trực tiếp tới mọi bảng domain. Ứng dụng phải điều phối xóa ACL.

**Câu 2.** `deleteAcl(root,false)` khi còn ACL child sẽ thế nào?

**Trả lời:** Ném `ChildrenExistException`; nếu diễn ra trong transaction đang xóa domain và ngoại lệ truyền ra, có thể rollback toàn bộ.

**Câu 3.** `deleteAcl(root,true)` có tự xóa hàng `document` của child không?

**Trả lời:** Không. Đây là cascade ACL. Domain subtree cần lifecycle riêng và kiểm tra quyền trên từng descendant.

**Câu 4.** Hai DELETE cùng DataSource/TX, rồi runtime exception phát sinh trước commit. Kết quả?

**Trả lời:** Spring Framework 6.x mặc định rollback đối với unchecked exception truyền qua transaction interceptor; cả domain và ACL/ACE chưa commit được phục hồi.

**Câu 5.** Vì sao owner trong `acl_object_identity.owner_sid` không tự có business READ/DELETE?

**Trả lời:** ACL owner là metadata quản trị ACL, không mặc nhiên là ACE hoặc quyền nghiệp vụ trên document. Chính sách phải định nghĩa rõ hành động được phép và bối cảnh tenant.

## 11. Tài liệu chính thức

- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html) — bốn bảng ACL, lifecycle không tự tích hợp với repository và `AclPermissionEvaluator`.
- [Spring Security 6.5 — MutableAclService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/MutableAclService.html) — `deleteAcl(ObjectIdentity,boolean)` và `ChildrenExistException`.
- [Spring Security 6.5 — JdbcMutableAclService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html) — JDBC deletion và cấu hình schema/dialect.
- [Spring Security 6.5 — AclService](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/AclService.html) — đọc ACL và `findChildren`.
- [Spring Security 6.5 — Database Schema](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html) — DDL/foreign keys của module ACL.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) — proxy, propagation và transaction boundary.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html) — rollback rules mặc định và `rollbackFor`.

**Ghi nhớ:** Xóa domain object **không tự xóa ACL**, còn `MutableAclService.deleteAcl` **không tự xóa domain object**. Một service an toàn phải kiểm tra quyền trước, phân biệt ACL children với domain children, phối hợp hai DELETE trong **cùng JDBC transaction**, xác nhận rollback bằng test trên cả bảng nghiệp vụ và bảng ACL, và xử lý riêng cache/các tác động ngoài database.