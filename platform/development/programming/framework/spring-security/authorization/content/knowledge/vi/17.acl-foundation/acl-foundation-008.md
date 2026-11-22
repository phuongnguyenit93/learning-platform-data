# Các bảng acl_sid, acl_class, acl_object_identity và acl_entry trong Spring Security ACL

## 1. Vì sao một hệ thống ACL cần bốn bảng?

Giả sử ứng dụng quản lý `Document`. Tài liệu 42 do Alice sở hữu. Bob chỉ được xem; thành viên có authority `ROLE_EDITOR` được sửa; Mallory bị từ chối đọc. Tài liệu 43 thuộc cùng một nhánh và có thể kế thừa một phần quyền của tài liệu 42. Một bảng `user_role` thông thường không biểu diễn đủ các quyền **theo từng bản ghi**, thứ tự cấp/từ chối hoặc quan hệ ACL cha–con.

**Spring Security ACL** (*Access Control List*) lưu quyền trên **một instance của domain object** bằng bốn bảng chuẩn:

1. **`acl_sid`**: chủ thể nhận quyền (*security identity* – principal cụ thể hoặc authority).
2. **`acl_class`**: loại đối tượng có ACL (thường là tên Java class).
3. **`acl_object_identity`**: một instance của loại đối tượng, ví dụ `Document#42`, cùng ACL owner và thông tin kế thừa.
4. **`acl_entry`**: từng quy tắc cấp hoặc từ chối quyền (*Access Control Entry — ACE*) cho một SID trên một object identity.

Spring Security mô tả schema này trong module riêng **`spring-security-acl`**; không phải cứ thêm `spring-boot-starter-security` là có sẵn bốn bảng hoặc dữ liệu ACL. Cần khởi tạo schema, cấu hình `DataSource`, `AclService`/`LookupStrategy` và tích hợp `AclPermissionEvaluator` nếu muốn dùng `hasPermission(...)` trong Method Security.

Bài học tập trung **cấu trúc bốn bảng**, khóa, ràng buộc, cách dữ liệu liên kết, bitmask, kế thừa, truy vấn kiểm tra và một demo Java 17 chạy với Spring Boot 3.5.6, HSQLDB và Spring Security 6.5.x. Những chính sách owner/tenant phức tạp hơn được nhắc đến tại vị trí cần thiết, không đồng nhất với ACL schema mặc định.

### 1.1. Sơ đồ quan hệ

```text
              acl_class
         (id PK, class UNIQUE)
                  │ 1
                  │
                  ▼ N
          acl_object_identity ──────┐
        (id PK, type, object ID,     │
         parent, owner, inherit)    │ self-FK parent_object
                  │ 1               │
                  ▼ N               ┘
               acl_entry
         (id PK, ace_order,
          sid FK, mask, grant)
                  │ N
                  ▼ 1
                acl_sid
     (id PK, principal flag, sid)
                  ▲
                  │ 1
                  └── owner_sid FK từ acl_object_identity
```

Bảng chính và quan hệ:

| Bảng | Một hàng đại diện | Khóa/ràng buộc quan trọng |
|---|---|---|
| `acl_sid` | Một principal hoặc một GrantedAuthority được ACL nhận diện | PK `id`; unique `(sid, principal)` |
| `acl_class` | Một domain type có ACL | PK `id`; unique `class` |
| `acl_object_identity` | Một instance cụ thể của domain type | PK `id`; unique `(object_id_class, object_id_identity)`; FK đến class, owner SID, parent ACL |
| `acl_entry` | Một ACE theo thứ tự cho một SID và object | PK `id`; unique `(acl_object_identity, ace_order)`; FK đến object identity và SID |

**Hai cặp ID dễ nhầm:** `acl_object_identity.id` là **khóa nội bộ của hàng ACL**; `acl_object_identity.object_id_identity` là **ID của bản ghi nghiệp vụ**, ví dụ 42. `acl_entry.acl_object_identity` luôn trỏ tới **ID nội bộ** của ACL, không trỏ thẳng đến `document.id`.

## 2. acl_sid — lưu SID (Security Identity) nhận quyền

Một SID đại diện cho **người dùng** hoặc **GrantedAuthority**. Các cột:

| Cột | Kiểu điển hình | Ý nghĩa |
|---|---|---|
| `id` | BIGINT, PK | ID nội bộ do database sinh |
| `principal` | BOOLEAN NOT NULL | `TRUE`: principal cụ thể; `FALSE`: authority |
| `sid` | VARCHAR(100) NOT NULL | Tên principal hoặc tên GrantedAuthority |
| unique `(sid, principal)` | Ràng buộc | Không có hai SID cùng tên và cùng loại |

Ví dụ:

| id | principal | sid |
|---:|:---:|---|
| 1 | true | alice |
| 2 | true | bob |
| 3 | true | mallory |
| 4 | false | ROLE_EDITOR |

**`principal = true`** ánh xạ tới `PrincipalSid("bob")`; **`principal = false`** ánh xạ tới `GrantedAuthoritySid("ROLE_EDITOR")`. Đây là hai kiểu SID khác nhau dù cùng thuộc một hệ thống. Nếu có cả `(true, "alice")` và `(false, "alice")` thì hai hàng hợp lệ về mặt unique constraint; ứng dụng cần có naming convention để tránh hiểu nhầm.

Bảng `acl_sid` **không phải bảng user** và không lưu password, thông tin đăng nhập hoặc mọi role membership. Nó chỉ định nghĩa **danh tính có thể nhận ACE**. Việc một user sở hữu GrantedAuthority nào đến từ `Authentication` do security provider/converter tạo, không phải từ quan hệ mặc định trong `acl_sid`.

Khi một ACE trỏ tới SID `ROLE_EDITOR`, **bất kỳ Authentication hợp lệ nào chứa authority đó** có thể được xem xét theo ACE của role, tùy thứ tự đánh giá và chính sách quyền. Điều này tiết kiệm số lượng ACE khi nhiều principal cùng được cấp một role.

**Lưu ý:** SID string thường khớp theo danh tính trong `Authentication`; nếu thay username hoặc đổi quy ước `ROLE_`, phải xem xét migration ACL. Không coi việc chỉ đổi tên hiển thị trên UI là không ảnh hưởng tới các hàng `acl_sid`.

## 3. acl_class — loại tài nguyên mà ACL bảo vệ

Cột:

| Cột | Kiểu điển hình | Ý nghĩa |
|---|---|---|
| `id` | BIGINT, PK | ID nội bộ cho domain type |
| `class` | VARCHAR(100) UNIQUE | Định danh Java type, thường là **tên đầy đủ có package** |

Ví dụ:

```text
id=7
class=com.example.acldemo.Document
```

Định danh này cần **khớp loại mà ObjectIdentity sử dụng**:

```java
ObjectIdentity identity =
    new ObjectIdentityImpl(Document.class, 42L);
```

Đây là **đoạn API minh họa**, cần import `org.springframework.security.acls.domain.ObjectIdentityImpl`, `org.springframework.security.acls.model.ObjectIdentity`, và lớp `Document` trong ứng dụng. Cách khởi tạo bằng `Document.class` cho kiểu `com.example.acldemo.Document`; bằng constructor `ObjectIdentityImpl(String type, Serializable identifier)` thì `type` là chuỗi developer quy định. Nếu trong DB ghi `com.example.legacy.Document` nhưng lúc runtime tra `com.example.acldemo.Document`, ACL có thể không được tìm thấy.

**Không nhầm `acl_class.id` với document ID.** `acl_class` có một dòng cho **một loại**, có thể hàng triệu `acl_object_identity` trỏ về dòng ấy.

Các trường hợp cần chú ý:
- Refactor package/class name ảnh hưởng tới `class` trong ACL; lập kế hoạch migration khi rename domain type.
- Nhiều module có lớp `Document` khác package là **hai** type khác nhau.
- Nếu muốn alias ổn định thay cho tên class Java, cần dùng `ObjectIdentityImpl(String, id)` thống nhất từ tạo ACL đến truy vấn, và kiểm tra tương thích với các service/lookup.
- Unique constraint trên `class` ngăn các bản ghi loại trùng nhau, nhưng không tự đảm bảo code sẽ chọn đúng type.

## 4. acl_object_identity — “địa chỉ” ACL của từng bản ghi

Bảng này liên kết domain type với **một đối tượng cụ thể** và lưu metadata kế thừa.

| Cột | Kiểu điển hình | Ý nghĩa |
|---|---|---|
| `id` | BIGINT, PK | ID nội bộ của ACL object identity |
| `object_id_class` | BIGINT NOT NULL | FK đến `acl_class.id` |
| `object_id_identity` | VARCHAR(36) NOT NULL trong schema mẫu 6.5 | ID domain object được lưu thành chuỗi |
| `parent_object` | BIGINT NULL | Self-FK đến `acl_object_identity.id` của ACL cha |
| `owner_sid` | BIGINT NULL | FK đến `acl_sid.id` đại diện ACL owner |
| `entries_inheriting` | BOOLEAN NOT NULL | Cho phép xét ACE được kế thừa từ ACL cha |
| unique `(object_id_class, object_id_identity)` | Ràng buộc | Một object thuộc một type chỉ có một hàng object identity |

Ví dụ:

| id | object_id_class | object_id_identity | parent_object | owner_sid | entries_inheriting |
|---:|---:|---|---:|---:|:---:|
| 10 | 7 | 42 | null | 1 | false |
| 11 | 7 | 43 | 10 | 1 | true |

Theo dữ liệu này:
- ACL nội bộ `10` đại diện cho `Document#42`.
- ACL nội bộ `11` đại diện cho `Document#43`.
- `parent_object=10` nghĩa là ACL của `Document#43` có ACL cha là `Document#42`.
- `entries_inheriting=true` nghĩa là các ACE từ cha có thể được xét khi tìm quyết định trên child; việc grant/deny còn phụ thuộc các ACE và permission granting strategy.
- `owner_sid=1` trỏ tới Alice; đây là **ACL owner**, không mặc nhiên đồng nghĩa với trường `document.created_by` hay owner nghiệp vụ.

### 4.1. Owner của ACL có quyền gì?

**ACL owner không mặc nhiên có `READ` hoặc `WRITE` đối với domain record.** `Acl#getOwner()` diễn tả chủ sở hữu của đối tượng ACL; `AclAuthorizationStrategy` có thể dùng owner để quyết định ai được **thay đổi ACL/ACE**. Quyền **đọc/sửa nội dung nghiệp vụ** vẫn phải được mô hình hóa bởi ACE hoặc chính sách ứng dụng, trừ khi hệ thống chủ động đưa ra quy tắc khác.

Đây là nhầm lẫn có thể tạo lỗ hổng: thấy `owner_sid=alice` rồi tự cho rằng mọi API đều có thể bỏ qua `hasPermission` đối với Alice. Hãy phân biệt:
1. **ACL administration**: ai được chỉnh sửa cấu hình chia sẻ ACE?
2. **Business authorization**: ai được đọc/xóa/sửa document?

Hai loại quyền không đồng nhất.

### 4.2. Kế thừa ACL và self-FK

`parent_object` cung cấp quan hệ cây/chuỗi parent ACL, còn `entries_inheriting` quyết định ACL con có **xét ACE cha** không. Một con có `parent_object` nhưng `entries_inheriting=false` sẽ không tự sử dụng quyền cha.

Để tránh lỗi:
- Không tạo chu trình `A → B → A`. Self-FK chỉ đảm bảo parent tồn tại; nó **không tự cấm vòng lặp**.
- Không cho parent ACL vượt tenant/project scope nếu nghiệp vụ không cho phép.
- Xác định rõ sự ưu tiên giữa ACE cục bộ và ACE kế thừa; thứ tự ACE/permission strategy ảnh hưởng tới quyết định.
- Khi chuyển owner hoặc di chuyển document qua tenant, phải xét lại `owner_sid`, `parent_object` và các ACE kế thừa.

### 4.3. Kiểu ID trong cơ sở dữ liệu

Tài liệu schema PostgreSQL 6.5 dùng `object_id_identity VARCHAR(36)`, trong khi ví dụ Java thường truyền `Long`. `ObjectIdentityImpl` biểu diễn identity nội bộ bằng dữ liệu có thể ánh xạ thành chuỗi để truy vấn; tuy nhiên một **UUID, BigInteger hoặc ID dài trên 36 ký tự** cần được đánh giá lại về độ dài cột và khả năng hỗ trợ của phiên bản ACL/JDBC đang triển khai. Đừng tự đổi type cột ở production mà không kiểm tra SQL và cache identity assumptions của `JdbcAclService`.

Một ứng dụng multi-tenant dùng ID trùng giữa tenant A/B cần đảm bảo ID domain **unique trong cùng Java type**, hoặc thiết kế composite identity/alias tương thích. Unique `(object_id_class,object_id_identity)` mặc định **không có tenant_id**: nếu hai tenant cùng có `Document#42` trong một bảng chung thì không thể ghi hai ACL object identity với cùng type và id. Hãy chọn ID toàn cục, phân loại type hoặc thiết kế schema/identity riêng sau khi hiểu giới hạn này.

## 5. acl_entry — các quy tắc cấp/từ chối quyền có thứ tự

Mỗi hàng là một **Access Control Entry (ACE)** gắn một SID với một object identity và một quyền/mask.

| Cột | Kiểu điển hình | Ý nghĩa |
|---|---|---|
| `id` | BIGINT, PK | ID nội bộ của ACE |
| `acl_object_identity` | BIGINT NOT NULL | FK đến `acl_object_identity.id` |
| `ace_order` | INTEGER NOT NULL | Vị trí ACE trong ACL của object |
| `sid` | BIGINT NOT NULL | FK đến `acl_sid.id` (principal/authority) |
| `mask` | INTEGER NOT NULL | Bitmask quyền (ví dụ 1=READ, 2=WRITE) |
| `granting` | BOOLEAN NOT NULL | `true`: cho phép; `false`: từ chối |
| `audit_success` | BOOLEAN NOT NULL | Cờ yêu cầu audit khi ACE được áp dụng và thành công |
| `audit_failure` | BOOLEAN NOT NULL | Cờ yêu cầu audit khi ACE được áp dụng và thất bại |
| unique `(acl_object_identity, ace_order)` | Ràng buộc | Trong một ACL, thứ tự ACE không được trùng |

Ví dụ trên ACL nội bộ `10` (Document#42):

| id | acl_object_identity | ace_order | sid | mask | granting | Ý nghĩa |
|---:|---:|---:|---:|---:|:---:|---|
| 100 | 10 | 0 | 2 (bob) | 1 | true | Bob được READ |
| 101 | 10 | 1 | 3 (mallory) | 1 | false | Mallory bị DENY READ |
| 102 | 10 | 2 | 4 (ROLE_EDITOR) | 2 | true | User có authority ROLE_EDITOR được WRITE |

ACL `11` (Document#43) có thêm:

| id | acl_object_identity | ace_order | sid | mask | granting | Ý nghĩa |
|---:|---:|---:|---:|---:|:---:|---|
| 103 | 11 | 0 | 2 (bob) | 2 | true | Bob được WRITE trực tiếp trên child |

Vì ACL của Document#43 có `entries_inheriting=true`, Bob có thể được xét READ thừa hưởng từ ACL cha, đồng thời có WRITE trực tiếp từ child. Chúng ta kiểm thử bằng ACL runtime ở phần demo chứ không kết luận chỉ từ SQL JOIN.

### 5.1. Bitmask của BasePermission

Spring Security ACL dùng bitmask integer. Các permission mặc định của `BasePermission`:

| Permission | Bit | Mask hệ thập phân | Dùng cho |
|---|---:|---:|---|
| `BasePermission.READ` | 0 | 1 | Đọc |
| `BasePermission.WRITE` | 1 | 2 | Sửa |
| `BasePermission.CREATE` | 2 | 4 | Tạo |
| `BasePermission.DELETE` | 3 | 8 | Xóa |
| `BasePermission.ADMINISTRATION` | 4 | 16 | Quản trị ACL |

Giá trị bitmask là **các bit quyền**, không phải role hoặc document id. Ví dụ `mask=3` có bit 0 và bit 1 bật (1 OR 2); cách engine so khớp một yêu cầu gồm nhiều quyền còn phụ thuộc `PermissionFactory` và `PermissionGrantingStrategy`. **Không tự diễn giải một mask trong SQL rồi coi đó là quyết định cuối cùng.** Spring Security có các lớp `BasePermission`, `CumulativePermission` và chiến lược granting để giải quyết theo chính sách ACL.

### 5.2. Thứ tự ACE quan trọng hơn vị trí hàng vật lý

`ace_order` là vị trí logic, không phải PK hoặc timestamp. Khi ACE cùng khớp nhiều SID/quyền hoặc có cả allow và deny, **thứ tự ACE** có thể ảnh hưởng tới kết quả theo `DefaultPermissionGrantingStrategy`. Đừng dựa vào thứ tự `id`, thứ tự INSERT, hoặc thứ tự một query chưa có `ORDER BY` để xác định quyền.

Một ACL có thể chứa **nhiều ACE cho cùng một SID**, nếu mỗi ACE ở một `ace_order` khác nhau; unique constraint là `(acl_object_identity,ace_order)` chứ **không phải** `(acl_object_identity,sid,mask)`. Việc gộp trùng, diễn giải deny và quyền tổng hợp thuộc policy/strategy.

### 5.3. Hai cờ audit không tự tạo cơ sở dữ liệu audit log

`audit_success` và `audit_failure` là **metadata** để `PermissionGrantingStrategy`/`AuditLogger` có thể dùng khi một ACE được xét. Chúng **không** phải bảng audit log và không chứng minh rằng mọi request đã được ghi log bền vững. Trong demo, cả hai cờ để `false`; một ứng dụng production phải cấu hình logger, retention và bảo vệ thông tin nhạy cảm riêng.

## 6. DDL tham khảo cho PostgreSQL: đủ bốn bảng và quan hệ

Đây là **DDL được viết lại theo schema mặc định Spring Security 6.5**, dành cho PostgreSQL, không phải SQL phổ dụng chạy trên mọi database. Các tên cột phải giữ đúng hợp đồng với các JDBC ACL queries của thư viện. Chạy bằng database role có quyền tạo schema, dùng migration Flyway/Liquibase ở production.

```sql
CREATE TABLE acl_sid (
    id BIGSERIAL PRIMARY KEY,
    principal BOOLEAN NOT NULL,
    sid VARCHAR(100) NOT NULL,
    CONSTRAINT uq_acl_sid_identity UNIQUE (sid, principal)
);

CREATE TABLE acl_class (
    id BIGSERIAL PRIMARY KEY,
    class VARCHAR(100) NOT NULL,
    CONSTRAINT uq_acl_class_name UNIQUE (class)
);

CREATE TABLE acl_object_identity (
    id BIGSERIAL PRIMARY KEY,
    object_id_class BIGINT NOT NULL
        REFERENCES acl_class(id),
    object_id_identity VARCHAR(36) NOT NULL,
    parent_object BIGINT NULL
        REFERENCES acl_object_identity(id),
    owner_sid BIGINT NULL
        REFERENCES acl_sid(id),
    entries_inheriting BOOLEAN NOT NULL,
    CONSTRAINT uq_acl_object
        UNIQUE (object_id_class, object_id_identity)
);

CREATE TABLE acl_entry (
    id BIGSERIAL PRIMARY KEY,
    acl_object_identity BIGINT NOT NULL
        REFERENCES acl_object_identity(id),
    ace_order INTEGER NOT NULL,
    sid BIGINT NOT NULL
        REFERENCES acl_sid(id),
    mask INTEGER NOT NULL,
    granting BOOLEAN NOT NULL,
    audit_success BOOLEAN NOT NULL,
    audit_failure BOOLEAN NOT NULL,
    CONSTRAINT uq_acl_ace_order
        UNIQUE (acl_object_identity, ace_order)
);
```

**Ý nghĩa của ràng buộc:**

1. `acl_sid(sid,principal)` unique vì principal và authority có thể có cùng chuỗi tên nhưng là hai SID riêng.
2. `acl_class(class)` unique vì mỗi type chỉ cần một ID.
3. `acl_object_identity(object_id_class,object_id_identity)` unique, chống hai ACL identity trùng đối tượng/type.
4. `acl_entry(acl_object_identity,ace_order)` unique, chống trùng vị trí ACE trong một object ACL.
5. FKs buộc ACE không thể trỏ tới SID/object không tồn tại; owner và parent vẫn có thể null.

**Cảnh báo thứ tự xóa:** Nếu muốn xóa ACL object identity, cần xử lý `acl_entry` của nó và các ACL con đang trỏ `parent_object`; các FK mặc định ở trên không dùng `ON DELETE CASCADE`. Không tự xóa hàng `acl_sid` được nhiều ACE/ACL owner tham chiếu.

### 6.1. PostgreSQL và JdbcMutableAclService: identity queries

Theo tài liệu chính thức, `JdbcMutableAclService` mặc định cấu hình câu lấy ID sinh ra cho **HSQLDB** (kiểu `call identity()`). Trên PostgreSQL, khi sử dụng `JdbcMutableAclService` để tạo SID/class mới, cần đặt:

```java
jdbcMutableAclService.setClassIdentityQuery(
    "select currval(pg_get_serial_sequence('acl_class', 'id'))"
);
jdbcMutableAclService.setSidIdentityQuery(
    "select currval(pg_get_serial_sequence('acl_sid', 'id'))"
);
```

Đây là **đoạn cấu hình**, chưa phải class chạy riêng; biến `jdbcMutableAclService` là instance được đăng ký làm bean. Không đưa hai câu query PostgreSQL này vào demo HSQLDB bên dưới: HSQLDB có cú pháp identity retrieval khác. Với MySQL/MariaDB, SQL Server, Oracle hoặc H2, xem schema và identity query đúng dialect/version.

### 6.2. Index và vận hành

Unique constraints thường tạo index cho key tương ứng nhưng **không tự đảm bảo mọi FK đều có index tối ưu**. Trước khi có nhiều ACL, xem execution plan và cân nhắc index trên:
- `acl_entry.sid` khi lọc theo recipient hoặc điều tra grant.
- `acl_object_identity.parent_object` khi duyệt ACL con.
- Các cột FK có truy vấn thường xuyên.
- Trường nghiệp vụ `tenant_id`, `owner_id` ở bảng domain (không thuộc bốn bảng mặc định).

Không đổi tùy ý độ dài, kiểu, tên cột nếu đang dùng các query mặc định của `JdbcAclService`. Kiểm tra schema shipped kèm đúng phiên bản `spring-security-acl` và dùng migration có rollback plan.

## 7. Truy vấn SQL để đọc bốn bảng cùng nhau

Đây là các **truy vấn phục vụ chẩn đoán và audit**, không phải phương pháp tự thay thế `Acl#isGranted`. SQL join không tự triển khai đầy đủ ACE order, inheritance, SID hierarchy và logic deny.

### 7.1. Tìm ACL object identity của Document#42

```sql
SELECT
    o.id AS acl_pk,
    c.class AS domain_type,
    o.object_id_identity AS domain_id,
    o.parent_object,
    o.entries_inheriting,
    s.sid AS acl_owner
FROM acl_object_identity o
JOIN acl_class c ON c.id = o.object_id_class
LEFT JOIN acl_sid s ON s.id = o.owner_sid
WHERE c.class = 'com.example.acldemo.Document'
  AND o.object_id_identity = '42';
```

**Đọc kết quả:** `acl_pk` là ID nội bộ của object ACL; `domain_id` là ID ở database nghiệp vụ; `acl_owner` là SID của ACL owner, không phải một ACE READ.

### 7.2. Liệt kê ACE theo thứ tự cho một object

```sql
SELECT
    e.ace_order,
    s.principal,
    s.sid,
    e.mask,
    e.granting,
    e.audit_success,
    e.audit_failure
FROM acl_entry e
JOIN acl_object_identity o
    ON o.id = e.acl_object_identity
JOIN acl_class c ON c.id = o.object_id_class
JOIN acl_sid s ON s.id = e.sid
WHERE c.class = 'com.example.acldemo.Document'
  AND o.object_id_identity = '42'
ORDER BY e.ace_order;
```

Nếu các seed rows giống phần demo, kết quả logic gồm: Bob READ=1 grant; Mallory READ=1 deny; ROLE_EDITOR WRITE=2 grant, theo `ace_order` 0, 1, 2. SQL chỉ hiển thị dữ liệu, chưa cộng SID authority của Authentication hay kế thừa.

### 7.3. Tìm các ACE trực tiếp cấp READ cho principal

```sql
SELECT
    c.class,
    o.object_id_identity,
    s.sid,
    e.ace_order,
    e.mask
FROM acl_entry e
JOIN acl_sid s ON s.id = e.sid
JOIN acl_object_identity o
    ON o.id = e.acl_object_identity
JOIN acl_class c ON c.id = o.object_id_class
WHERE s.principal = TRUE
  AND s.sid = 'bob'
  AND e.granting = TRUE
  AND (e.mask & 1) = 1
ORDER BY c.class, o.object_id_identity;
```

**Chỉ để thống kê trực tiếp.** Nó có thể bỏ sót READ được kế thừa hoặc qua authority, và không áp dụng đầy đủ deny/ACE precedence. Không dùng kết quả này làm “tất cả tài liệu Bob được đọc” tại API production; cần truy vấn ACL phù hợp hoặc `AclService`/policy đã được kiểm thử.

## 8. Ví dụ Java 17 chạy được: Spring Security ACL + HSQLDB

Để thấy dữ liệu bốn bảng thực sự được thư viện đọc, ta tạo ứng dụng không có HTTP endpoint, dùng Spring Boot **3.5.6**, Java 17, Spring Security **6.5.x do Boot quản lý**, `spring-security-acl`, Spring JDBC, HSQLDB và JUnit 5.

**Tại sao chọn HSQLDB?** Bộ JDBC ACL của Spring Security cung cấp schema HSQLDB và identity query mặc định phù hợp dialect này. DDL demo được điều chỉnh để dễ đọc nhưng giữ đúng cột/ràng buộc của schema ACL 6.5. Không áp dụng nguyên DDL này cho PostgreSQL: phần 6 là biến thể PostgreSQL riêng.

**Giới hạn:** Đây là integration test ACL và SQL schema. Không có database nghiệp vụ `document` thật, không xây user/password login thật, không có JWT/tenant policy. Các method giả trả về chuỗi để minh họa authorization.

### 8.1. Cấu trúc thư mục

```text
acl-four-tables-demo/
  pom.xml
  src/main/java/com/example/acldemo/
    AclTablesApplication.java
    Document.java
    AclSecurityConfig.java
    DocumentService.java
  src/main/resources/
    schema.sql
    data.sql
  src/test/java/com/example/acldemo/
    AclIntegrationTest.java
```

### 8.2. pom.xml

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
    <artifactId>acl-four-tables-demo</artifactId>
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

### 8.3. schema.sql — HSQLDB, đủ bốn bảng

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE acl_sid (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000) PRIMARY KEY,
    principal BOOLEAN NOT NULL,
    sid VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT uq_sid UNIQUE (sid, principal)
);

CREATE TABLE acl_class (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000) PRIMARY KEY,
    class VARCHAR_IGNORECASE(100) NOT NULL,
    CONSTRAINT uq_class UNIQUE (class)
);

CREATE TABLE acl_object_identity (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000) PRIMARY KEY,
    object_id_class BIGINT NOT NULL,
    object_id_identity VARCHAR_IGNORECASE(36) NOT NULL,
    parent_object BIGINT,
    owner_sid BIGINT,
    entries_inheriting BOOLEAN NOT NULL,
    CONSTRAINT uq_object_type_id
        UNIQUE (object_id_class, object_id_identity),
    CONSTRAINT fk_object_class
        FOREIGN KEY (object_id_class) REFERENCES acl_class(id),
    CONSTRAINT fk_object_parent
        FOREIGN KEY (parent_object) REFERENCES acl_object_identity(id),
    CONSTRAINT fk_object_owner
        FOREIGN KEY (owner_sid) REFERENCES acl_sid(id)
);

CREATE TABLE acl_entry (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY(START WITH 1000) PRIMARY KEY,
    acl_object_identity BIGINT NOT NULL,
    ace_order INTEGER NOT NULL,
    sid BIGINT NOT NULL,
    mask INTEGER NOT NULL,
    granting BOOLEAN NOT NULL,
    audit_success BOOLEAN NOT NULL,
    audit_failure BOOLEAN NOT NULL,
    CONSTRAINT uq_entry_order
        UNIQUE (acl_object_identity, ace_order),
    CONSTRAINT fk_entry_object
        FOREIGN KEY (acl_object_identity) REFERENCES acl_object_identity(id),
    CONSTRAINT fk_entry_sid
        FOREIGN KEY (sid) REFERENCES acl_sid(id)
);
```

Vì dùng `GENERATED BY DEFAULT AS IDENTITY`, file seed bên dưới có thể đặt ID cố định nhỏ hơn 1000 để bài test dễ đọc; các ID mới do DB sinh bắt đầu từ 1000. Khác với schema HSQLDB trong tài liệu chính thức ở tên constraints và điểm bắt đầu identity, các **tên cột và quan hệ** đều theo hợp đồng ACL. Trong ứng dụng thực, nên dùng chính schema đi kèm version thư viện và quản lý thay đổi bằng migration, không đổi tùy tiện SQL mặc định.

### 8.4. data.sql — một ví dụ minh bạch và có parent ACL

**`src/main/resources/data.sql`**

```sql
INSERT INTO acl_sid(id, principal, sid)
VALUES (1, TRUE, 'alice');
INSERT INTO acl_sid(id, principal, sid)
VALUES (2, TRUE, 'bob');
INSERT INTO acl_sid(id, principal, sid)
VALUES (3, TRUE, 'mallory');
INSERT INTO acl_sid(id, principal, sid)
VALUES (4, FALSE, 'ROLE_EDITOR');

INSERT INTO acl_class(id, class)
VALUES (7, 'com.example.acldemo.Document');

INSERT INTO acl_object_identity(
    id, object_id_class, object_id_identity,
    parent_object, owner_sid, entries_inheriting
) VALUES (
    10, 7, '42', NULL, 1, FALSE
);

INSERT INTO acl_object_identity(
    id, object_id_class, object_id_identity,
    parent_object, owner_sid, entries_inheriting
) VALUES (
    11, 7, '43', 10, 1, TRUE
);

INSERT INTO acl_entry(
    id, acl_object_identity, ace_order, sid,
    mask, granting, audit_success, audit_failure
) VALUES (100, 10, 0, 2, 1, TRUE, FALSE, FALSE);

INSERT INTO acl_entry(
    id, acl_object_identity, ace_order, sid,
    mask, granting, audit_success, audit_failure
) VALUES (101, 10, 1, 3, 1, FALSE, FALSE, FALSE);

INSERT INTO acl_entry(
    id, acl_object_identity, ace_order, sid,
    mask, granting, audit_success, audit_failure
) VALUES (102, 10, 2, 4, 2, TRUE, FALSE, FALSE);

INSERT INTO acl_entry(
    id, acl_object_identity, ace_order, sid,
    mask, granting, audit_success, audit_failure
) VALUES (103, 11, 0, 2, 2, TRUE, FALSE, FALSE);
```

Từ `data.sql`:
- `acl_sid.id=2` là Bob, `principal=true`.
- `acl_sid.id=4` là authority `ROLE_EDITOR`, `principal=false`.
- `acl_class.id=7` là Java type `com.example.acldemo.Document`.
- `acl_object_identity.id=10` đại diện cho domain id `42`, owner SID Alice.
- `acl_object_identity.id=11` đại diện cho domain id `43`, parent ACL 10 và bật inheritance.
- ACE 100 cấp READ=1 cho Bob trên 42.
- ACE 101 từ chối READ=1 cho Mallory trên 42.
- ACE 102 cấp WRITE=2 cho ROLE_EDITOR trên 42.
- ACE 103 cấp WRITE=2 trực tiếp cho Bob trên 43.

**Thứ tự tạo seed:** tạo SID + class trước, object identity cha trước con, rồi ACE. Nếu đảo chiều sẽ vi phạm FK; đây chính là lợi ích của ràng buộc quan hệ.

### 8.5. Spring Boot và đối tượng domain

**`src/main/java/com/example/acldemo/AclTablesApplication.java`**

```java
package com.example.acldemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AclTablesApplication {
    public static void main(String[] args) {
        SpringApplication.run(AclTablesApplication.class, args);
    }
}
```

**`src/main/java/com/example/acldemo/Document.java`**

```java
package com.example.acldemo;

public record Document(Long id, String title) {
    // ObjectIdentityImpl(Object) tìm public getId() qua reflection.
    public Long getId() {
        return id;
    }
}
```

Tên package **phải đúng** với `acl_class.class` trong `data.sql`. Nếu bạn đổi package thành `com.example.other` nhưng không đổi seed ACL, kết quả sẽ không đúng.

### 8.6. Cấu hình Spring Security ACL thật

**`src/main/java/com/example/acldemo/AclSecurityConfig.java`**

```java
package com.example.acldemo;

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
public class AclSecurityConfig {

    @Bean
    static MethodSecurityExpressionHandler expressionHandler(
            AclPermissionEvaluator evaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(evaluator);
        return handler;
    }

    @Bean
    static AclPermissionEvaluator aclPermissionEvaluator(AclService service) {
        return new AclPermissionEvaluator(service);
    }

    @Bean
    static JdbcMutableAclService aclService(
            DataSource dataSource,
            LookupStrategy lookupStrategy,
            AclCache aclCache) {
        return new JdbcMutableAclService(
            dataSource, lookupStrategy, aclCache
        );
    }

    @Bean
    static LookupStrategy lookupStrategy(
            DataSource dataSource,
            AclCache aclCache,
            AclAuthorizationStrategy aclAuthorizationStrategy,
            PermissionGrantingStrategy permissionGrantingStrategy) {
        return new BasicLookupStrategy(
            dataSource, aclCache,
            aclAuthorizationStrategy, permissionGrantingStrategy
        );
    }

    @Bean
    static AclCache aclCache(
            PermissionGrantingStrategy permissionGrantingStrategy,
            AclAuthorizationStrategy aclAuthorizationStrategy) {
        return new SpringCacheBasedAclCache(
            new ConcurrentMapCache("aclCache"),
            permissionGrantingStrategy,
            aclAuthorizationStrategy
        );
    }

    @Bean
    static AclAuthorizationStrategy aclAuthorizationStrategy() {
        return new AclAuthorizationStrategyImpl(
            new SimpleGrantedAuthority("ROLE_ACL_ADMIN")
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

Các thành phần trong cấu hình:

| Thành phần | Công việc |
|---|---|
| `AclPermissionEvaluator` | Biến câu hỏi `hasPermission(...)` thành kiểm tra ACL |
| `DefaultMethodSecurityExpressionHandler` | Cho Method Security sử dụng evaluator ở biểu thức SpEL |
| `JdbcMutableAclService` | Đọc ACL và có thể tạo/cập nhật ACL trong DB |
| `BasicLookupStrategy` | Truy xuất ACL/ACE theo object identity, tối ưu truy vấn theo lô |
| `SpringCacheBasedAclCache` | Cache ACL với Spring Cache |
| `AclAuthorizationStrategyImpl` | Kiểm soát **ai được sửa ACL metadata/ACE**, khác business WRITE |
| `DefaultPermissionGrantingStrategy` | Đánh giá thứ tự ACE, SID và permission mask |
| `ConsoleAuditLogger` | Cách ghi audit minh họa; không tự tạo bảng audit log |

**Cần chú ý:** `@EnableMethodSecurity` kích hoạt interceptor của `@PreAuthorize`/`@PostAuthorize`; chỉ có ACL service bean mà không bật Method Security thì annotation không tự được bảo vệ. Cấu hình trên bám theo mẫu 6.5; trong ứng dụng thật, thay cache/audit logger và cân nhắc eviction khi thay đổi ACE.

### 8.7. Service dùng dạng ID và object

**`src/main/java/com/example/acldemo/DocumentService.java`**

```java
package com.example.acldemo;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    @PreAuthorize(
        "hasPermission(#id, 'com.example.acldemo.Document', " +
        "T(org.springframework.security.acls.domain.BasePermission).READ)"
    )
    public String read(@P("id") Long id) {
        return "read:" + id;
    }

    @PreAuthorize(
        "hasPermission(#id, 'com.example.acldemo.Document', " +
        "T(org.springframework.security.acls.domain.BasePermission).WRITE)"
    )
    public String write(@P("id") Long id) {
        return "write:" + id;
    }

    @PostAuthorize(
        "hasPermission(returnObject, " +
        "T(org.springframework.security.acls.domain.BasePermission).READ)"
    )
    public Document load(@P("id") Long id) {
        return new Document(id, "sample");
    }
}
```

Hai method `read`/`write` dùng `#id`, chuỗi **đúng Java class name** và `BasePermission.READ`/`WRITE`. `@P("id")` bảo đảm biến tham số được giải quyết ổn định kể cả khi class không giữ tên parameter khi biên dịch.

Method `load` minh họa hậu kiểm qua object: `ObjectIdentityImpl(Object)` có thể lấy ID từ `getId()` của `Document`. Vì `load` chỉ tạo object demo (không ghi database/gửi mạng), nó an toàn để minh họa hậu kiểm. **Không dùng `@PostAuthorize` làm lớp bảo vệ duy nhất cho mutation có side effects.**

Với code hệ thống thật, `write` phải thêm logic cập nhật record, tenant scope, transaction và optimistic locking; demo này chỉ xác minh ACL decision.

### 8.8. JUnit integration tests — kiểm tra bốn bảng và quyết định

**`src/test/java/com/example/acldemo/AclIntegrationTest.java`**

```java
package com.example.acldemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class AclIntegrationTest {
    @Autowired DocumentService service;
    @Autowired JdbcTemplate jdbc;

    private int count(String table) {
        Integer total = jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + table, Integer.class
        );
        return total.intValue();
    }

    @Test
    void fourTablesContainExpectedRows() {
        assertEquals(4, count("acl_sid"));
        assertEquals(1, count("acl_class"));
        assertEquals(2, count("acl_object_identity"));
        assertEquals(4, count("acl_entry"));
    }

    @Test
    void principalAndAuthoritySidAreDifferentKinds() {
        Boolean bobIsPrincipal = jdbc.queryForObject(
            "SELECT principal FROM acl_sid WHERE sid = ?",
            Boolean.class, "bob"
        );
        Boolean editorIsPrincipal = jdbc.queryForObject(
            "SELECT principal FROM acl_sid WHERE sid = ?",
            Boolean.class, "ROLE_EDITOR"
        );
        assertTrue(bobIsPrincipal);
        assertFalse(editorIsPrincipal);
    }

    @Test
    void identityRelatesClassToDomainId() {
        String type = jdbc.queryForObject(
            """
            SELECT c.class
            FROM acl_object_identity o
            JOIN acl_class c ON c.id = o.object_id_class
            WHERE o.object_id_identity = ?
            """,
            String.class, "42"
        );
        assertEquals("com.example.acldemo.Document", type);
    }

    @Test
    void childHasParentAndInheritanceEnabled() {
        Long parent = jdbc.queryForObject(
            "SELECT parent_object FROM acl_object_identity WHERE id = 11",
            Long.class
        );
        Boolean enabled = jdbc.queryForObject(
            "SELECT entries_inheriting FROM acl_object_identity WHERE id = 11",
            Boolean.class
        );
        assertEquals(10L, parent);
        assertTrue(enabled);
    }

    @Test
    void duplicateAceOrderViolatesUniqueConstraint() {
        assertThrows(DataIntegrityViolationException.class, () ->
            jdbc.update(
                """
                INSERT INTO acl_entry(
                    acl_object_identity, ace_order, sid,
                    mask, granting, audit_success, audit_failure
                ) VALUES (10, 0, 2, 1, TRUE, FALSE, FALSE)
                """
            )
        );
    }

    @Test
    @WithMockUser(username = "bob")
    void bobCanReadDocument42() {
        assertEquals("read:42", service.read(42L));
    }

    @Test
    @WithMockUser(username = "bob")
    void bobCannotWriteDocument42() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.write(42L)
        );
    }

    @Test
    @WithMockUser(username = "mallory")
    void explicitReadDenyRejectsMallory() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.read(42L)
        );
    }

    @Test
    @WithMockUser(username = "carol", roles = "EDITOR")
    void authoritySidGrantsWriteToEditor() {
        assertEquals("write:42", service.write(42L));
    }

    @Test
    @WithMockUser(username = "carol", roles = "EDITOR")
    void roleEditorDoesNotAutomaticallyGrantRead() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.read(42L)
        );
    }

    @Test
    @WithMockUser(username = "bob")
    void bobInheritsReadFromParentAcl() {
        assertEquals("read:43", service.read(43L));
    }

    @Test
    @WithMockUser(username = "bob")
    void bobHasDirectWriteOnChildAcl() {
        assertEquals("write:43", service.write(43L));
    }

    @Test
    @WithMockUser(username = "alice")
    void aclOwnerWithoutReadAceIsNotAutomaticallyAllowed() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.read(42L)
        );
    }

    @Test
    @WithMockUser(username = "bob")
    void objectBasedPostAuthorizeReadsIdFromGetId() {
        assertEquals(42L, service.load(42L).getId());
    }

    @Test
    @WithMockUser(username = "mallory")
    void objectBasedPostAuthorizeRejectsRead() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.load(42L)
        );
    }
}
```

**Vì sao các test có ý nghĩa?**
- `fourTablesContainExpectedRows` kiểm tra số lượng hàng seed: 4 SID, 1 class, 2 object identities, 4 ACE.
- `principalAndAuthoritySidAreDifferentKinds` phân biệt người dùng Bob và authority ROLE_EDITOR.
- `identityRelatesClassToDomainId` kiểm tra liên kết class + object ID, không nhầm ACL PK 10 với domain ID 42.
- `childHasParentAndInheritanceEnabled` kiểm tra parent pointer và cờ inheritance.
- `duplicateAceOrderViolatesUniqueConstraint` chứng minh DB bảo vệ thứ tự ACE trong cùng ACL.
- Các test `@WithMockUser` đi qua **Spring-managed service proxy** và `AclPermissionEvaluator`, không tự tính quyền bằng SQL JOIN.
- `@WithMockUser(username="carol",roles="EDITOR")` tạo `GrantedAuthority("ROLE_EDITOR")`, nên kiểm tra đúng kiểu SID authority (`principal=false`).
- Test Alice chỉ ra ACL owner **không tự có READ** đối với record; chủ sở hữu ACL có vai trò riêng khi sửa ACL.
- `@PostAuthorize` kiểm tra object sau khi target trả về; ở đây không có side effect nên ví dụ an toàn.

**Kỳ vọng theo cấu hình mẫu:** 15 test pass; 0 failures/errors. Đây là **kết quả mong đợi theo thiết kế**, chưa phải log Maven đã chạy. Nếu test thất bại vì dialect, identity mapping hoặc phiên bản dependency khác, đọc root cause của `JdbcAclService`/`BasicLookupStrategy`, so sánh schema với file DDL shipped của đúng bản ACL và không “sửa” bằng cách tắt Method Security.

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Hoặc khởi động ứng dụng không có HTTP endpoint:

```bash
mvn spring-boot:run
```

**Ghi chú về kiểm thử:** Test không đặt `@Transactional` trên cả class để tránh làm nhiễu quan sát dữ liệu. HSQLDB được khởi tạo bằng `schema.sql`/`data.sql` trong embedded datasource. Test duplicate ACE dự kiến làm DB từ chối statement; các dòng seed gốc không thay đổi.

## 9. Tạo ACL và thêm ACE đúng qua API (mẫu tích hợp)

Một ứng dụng thực không nên thao tác trực tiếp các bảng ACL ở mọi nơi. Thư viện có `MutableAclService`/`JdbcMutableAclService` để tạo và cập nhật object identity, ACE và cache. Ví dụ mô tả thao tác **trong Spring-managed service/transaction**, sau khi đã được xác thực và kiểm tra quyền admin phù hợp:

```java
ObjectIdentity identity = new ObjectIdentityImpl(
    Document.class, 99L
);

// Đọc ACL nếu có; hoặc tạo ACL mới cho domain object 99.
MutableAcl acl;
try {
    acl = (MutableAcl) mutableAclService.readAclById(identity);
} catch (NotFoundException ex) {
    acl = mutableAclService.createAcl(identity);
}

// Cấp READ cho bob qua PrincipalSid.
// ACE được chèn ở cuối danh sách; thứ tự sẽ được ghi trong ace_order.
Sid bob = new PrincipalSid("bob");
acl.insertAce(
    acl.getEntries().size(),
    BasePermission.READ,
    bob,
    true
);
mutableAclService.updateAcl(acl);
```

Đây là **đoạn tích hợp** (chưa là method Java độc lập): cần imports từ `org.springframework.security.acls.domain`/`model` và biến `mutableAclService` đã inject; đồng thời DB schema/ACL cache/transaction phải được cấu hình. Nếu `createAcl` tạo dòng mới, thư viện phải lấy identity vừa sinh từ database. Với PostgreSQL cần cấu hình `classIdentityQuery`/`sidIdentityQuery` như phần 6.1.

**Quan trọng:** Spring Security ACL không tự tạo một ACL khi repository save một entity hoặc tự xóa ACL khi entity bị xóa. Ứng dụng phải kết hợp vòng đời domain record với vòng đời ACL **một cách có chủ đích**:

1. Khi tạo domain record, lưu record và khởi tạo ACL/owner/ACE theo chính sách.
2. Khi chia sẻ, thêm ACE cho SID người nhận/role và update ACL; validate ai được cấp và phạm vi tenant.
3. Khi thu hồi, xóa hoặc đổi ACE trong danh sách, update ACL và invalidation cache.
4. Khi xóa domain record, xử lý ACE, object ACL và các quan hệ parent; tránh ACL mồ côi.
5. Audit ai thay đổi ACE, trước/sau, lý do và thời gian, ngoài cờ `audit_success`/`audit_failure`.

Không đưa quyền tự sửa ACL ra ngoài API chỉ vì user được READ/WRITE business resource. `AclAuthorizationStrategy` kiểm tra quyền quản trị ACL, khác `BasePermission.WRITE`.

## 10. Cách bốn bảng tham gia vào một quyết định đọc

Giả sử user Bob gọi:

```java
@PreAuthorize(
    "hasPermission(#id, 'com.example.acldemo.Document', " +
    "T(org.springframework.security.acls.domain.BasePermission).READ)"
)
public String read(@P("id") Long id) {
    return "read:" + id;
}
```

Với `id=42`, luồng ý tưởng:

```text
1) Authentication hiện tại: bob, authorities [...]
                  ↓
2) AclPermissionEvaluator nhận (42, Document, READ)
                  ↓
3) ObjectIdentity = (com.example.acldemo.Document, 42)
                  ↓
4) acl_class: tìm row type
   acl_object_identity: tìm ACL nội bộ 10
                  ↓
5) acl_sid: tìm các SID ứng với bob và authorities hiện tại
   acl_entry: đọc ACE theo thứ tự cho ACL 10
                  ↓
6) PermissionGrantingStrategy:
   ACE bob mask=1, granting=true
                  ↓
7) Quyết định cho phép; Spring AOP chạy method đích
```

Đối với `Document#43`, `BasicLookupStrategy` lấy ACL con và có thể truy vấn cha, nhờ `parent_object` và `entries_inheriting`. Nếu không tìm thấy ACE con phù hợp mà có inheritance, engine xét ACE parent tùy implementation/strategy. Nếu một ACE có `granting=false` khớp, quyết định có thể bị từ chối. Nên **kiểm thử cả deny lẫn inheritance**, không chỉ hỏi “SQL có row grant nào không?”.

## 11. Các lỗi thường gặp khi triển khai bốn bảng

| Sai lầm | Vì sao nguy hiểm hoặc sai kết quả | Cách xử lý |
|---|---|---|
| Coi `acl_sid` là bảng user/password | SID không lưu thông tin xác thực | Dùng Authentication provider/IAM, giữ SID chỉ cho ACL |
| Coi `principal=false` là “không có quyền” | `false` nghĩa là SID đại diện authority | Ghép đúng `PrincipalSid` hoặc `GrantedAuthoritySid` |
| Dùng `object_id_identity` thay cho `acl_object_identity.id` khi insert ACE | FK trỏ sai ID hoặc báo lỗi | Xác định đúng ACL PK nội bộ |
| Dùng `acl_class.class = "Document"` nhưng runtime dùng FQCN | ACL lookup không khớp type | Đồng nhất `ObjectIdentity` và tên type trong DB |
| Trùng `(class,domain ID)` giữa nhiều tenant | Unique constraint đụng nhau | Dùng ID toàn cục hoặc chiến lược object identity phân tenant |
| Hiểu `owner_sid` là quyền đọc mọi tài liệu | ACL owner không tự có business READ | Tách ACL admin và content permission |
| Có `parent_object` là mặc định kế thừa | Cần `entries_inheriting=true` | Test parent/child grant/deny |
| Tạo vòng lặp ACL parent | Self-FK không chống cycle | Validation logic và test tree |
| Bỏ qua `ace_order` khi tự phân quyền | Có thể sai precedence grant/deny | Dùng `Acl#isGranted` và chiến lược phù hợp |
| Coi `mask=3` là “mọi quyền” | Mask chỉ chứa bit READ/WRITE | Định nghĩa rõ `BasePermission` và custom masks |
| Dùng SQL JOIN thay cho ACL engine | Bỏ sót role SID, deny, inheritance, order | Dùng `AclService`/`AclPermissionEvaluator` |
| Quên `spring-security-acl` dependency | Thiếu classes và schema ACL | Thêm module phù hợp phiên bản |
| Dùng schema PostgreSQL trên HSQLDB nguyên văn | Sai dialect identity/DDL | Chọn schema và identity query tương thích |
| Quên tạo/xóa ACL khi tạo/xóa entity | ACL mồ côi hoặc entity không có ACL | Quản lý lifecycle theo transaction |
| Sửa ACE trực tiếp nhưng không clear cache | Decision cũ còn tồn tại | Dùng `MutableAclService`/evict cache, test revoke |
| `hasPermission` trên method ghi nhưng đặt `@PostAuthorize` | Tác dụng phụ đã xảy ra trước kiểm tra | Ưu tiên `@PreAuthorize` khi đủ ID |
| ACL quá lớn, N+1 query | Tăng độ trễ và hỏng phân trang | Batch lookup, cache và lọc sớm |
| Coi ACL tự kiểm tra tenant | Bốn bảng mặc định không có tenant_id | Thêm ranh giới tenant trong policy/query |

### 11.1. Caching, hiệu năng và độ nhất quán

`JdbcAclService` thường sử dụng `LookupStrategy` có batched retrieval; `SpringCacheBasedAclCache` cache ACL để giảm query. Khi thay ACE/parent/owner, **cache invalidation** là bắt buộc để tránh quyền bị thu hồi nhưng vẫn được chấp nhận. Với nhiều instance ứng dụng, cache chỉ trong JVM không tự đồng bộ với node khác. Cần cơ chế phát sự kiện invalidation, shared cache hoặc TTL rõ ràng theo mức rủi ro.

ACL per-object có thể rất nhiều hàng: mỗi domain object một `acl_object_identity` và nhiều ACE. Số bit permission không giới hạn số object; nó chỉ giới hạn cách biểu diễn các loại permission theo bit. Trong ứng dụng list/lookup lớn, tìm ACL theo từng hàng không tối ưu; dùng batch lookup, query có điều kiện permission hoặc chiến lược dữ liệu phù hợp.

### 11.2. Transaction và quyền trên tenant

ACL schema không thay thế transaction. Việc tạo entity rồi tạo ACL nên có chiến lược atomicity phù hợp: nếu entity được tạo mà ACL thất bại, đối tượng có thể bị mất khả năng truy cập; nếu xóa entity nhưng giữ ACL, ACL mồ côi có thể gây rối. Trong cùng DB, kết hợp thao tác trong transaction khi có thể và xác định chính sách rollback/cleanup.

Bốn bảng không có cột `tenant_id` mặc định. Nếu một user có `ROLE_EDITOR` thuộc tenant A, một ACE cho `ROLE_EDITOR` trên object tenant B **có thể** ảnh hưởng nếu không có thêm kiểm tra scope. Do đó model multi-tenant cần giới hạn SID theo tenant, truy vấn object identity an toàn, hoặc bổ sung một lớp kiểm tra membership/tenant trước `AclPermissionEvaluator`.

### 11.3. Dữ liệu sai kiểu, rename và UUID

Nếu refactor `Document` thành `KnowledgeDocument`, tên `acl_class.class` cũ sẽ không còn khớp `ObjectIdentityImpl(KnowledgeDocument.class, id)`. Nếu chuyển từ `Long` sang UUID hoặc ID chuỗi dài, xem tương thích `ObjectIdentity`, type cột `object_id_identity` và lookup strategy trước khi migrate. Test readAclById bằng chính class và ID được ứng dụng sử dụng để tránh “schema đã có row nhưng người dùng đều 403”.

## 12. Checklist kiểm định một ACL schema đã triển khai

- [ ] Chỉ có bốn bảng ACL bắt buộc theo module: `acl_sid`, `acl_class`, `acl_object_identity`, `acl_entry`.
- [ ] Có PK và auto-generated ID phù hợp database dialect.
- [ ] Unique `(sid,principal)`, `(class)`, `(object_id_class,object_id_identity)` và `(acl_object_identity,ace_order)`.
- [ ] Có FK từ object identity đến class, owner SID, parent object; từ ACE đến object và recipient SID.
- [ ] Phân biệt `acl_object_identity.id` (ACL PK) với `object_id_identity` (domain ID).
- [ ] `principal=true/false` được hiểu đúng là principal/authority, không phải allow/deny.
- [ ] `granting=true/false` ở `acl_entry` mới là grant/deny của một ACE.
- [ ] Mask `1/2/4/8/16` được hiểu theo `BasePermission`; custom masks được tài liệu hóa và kiểm thử.
- [ ] `ace_order` và `entries_inheriting` được áp dụng qua ACL engine, không tự nối SQL rồi kết luận allow.
- [ ] `acl_class.class` khớp ObjectIdentity type lúc runtime.
- [ ] Schema phù hợp PostgreSQL/HSQLDB/MySQL/SQL Server/Oracle đang dùng; các identity queries cho `JdbcMutableAclService` đúng dialect.
- [ ] `AclService`, `LookupStrategy`, `AclCache`, `PermissionGrantingStrategy`, `AclPermissionEvaluator` và `MethodSecurityExpressionHandler` được cấu hình khi cần Method Security.
- [ ] Seed/test xác minh principal SID vs authority SID, grant vs deny, quyền cha–con, unique/FK và missing ACL.
- [ ] Cấp/thu hồi ACE có transaction và cache eviction; không thay ACL bằng cách sửa DB trực tiếp không có invalidation.
- [ ] Có chính sách owner/tenant thực sự theo nghiệp vụ; ACL owner không bị dùng làm “superuser” tùy tiện.
- [ ] Hành vi fail-closed khi không tìm thấy ACL, sai class/id, lỗi policy DB hoặc thiếu membership được kiểm thử.

## 13. Nguồn chính thức để đối chiếu

- [Spring Security 6.5 — Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html): bốn bảng, SID, ACE, `AclService`, `MutableAclService`, lookup strategy và cấu hình `AclPermissionEvaluator`.
- [Spring Security 6.5 — Security Database Schema](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html): DDL theo HSQLDB, PostgreSQL, MySQL/MariaDB, SQL Server và Oracle cùng lưu ý identity query.
- [Spring Security 6.5 — JdbcMutableAclService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/jdbc/JdbcMutableAclService.html): tạo/cập nhật ACL qua JDBC và identity queries.
- [Spring Security 6.5 — AclPermissionEvaluator API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/AclPermissionEvaluator.html): quyền trên domain object hoặc ID + type.
- [Spring Security 6.5 — ObjectIdentityImpl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/domain/ObjectIdentityImpl.html): khái niệm type + identifier và cách lấy ID từ domain object.
- [Spring Security 6.5 — Acl API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/acls/model/Acl.html): owner, parent, entries, `isGranted(...)` và inheritance.

**Ghi nhớ:** `acl_sid` trả lời **“ai/nhóm quyền nào?”**; `acl_class` trả lời **“loại tài nguyên gì?”**; `acl_object_identity` trả lời **“bản ghi cụ thể nào, owner ACL nào, có kế thừa không?”**; `acl_entry` trả lời **“SID được cấp hay từ chối permission nào, ở thứ tự nào?”**. Bốn bảng tạo cấu trúc dữ liệu ACL, còn quyết định cuối cùng thuộc `AclService`/`PermissionGrantingStrategy` và chính sách bảo mật của ứng dụng.