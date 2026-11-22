# Điều kiện tĩnh với @SQLRestriction và phạm vi áp dụng trong Hibernate

Trong ứng dụng dùng Hibernate, nhiều bảng có những dòng **vẫn tồn tại vật lý nhưng không nên hiển thị trong các truy vấn thông thường**. Ví dụ: tài liệu đã xóa mềm, tài khoản đã khóa hoặc một liên kết many-to-many không còn hiệu lực.

Nếu mọi repository đều tự viết `where deleted = false`, rất dễ có một query bị quên điều kiện. Hibernate cung cấp **`org.hibernate.annotations.SQLRestriction`** để khai báo một **predicate SQL cố định ở cấp ánh xạ entity hoặc collection**. Khi Hibernate sinh SQL cho phạm vi mà annotation áp dụng, predicate được đưa vào câu truy vấn.

~~~java
import jakarta.persistence.*;
import org.hibernate.annotations.SQLRestriction;

@Entity
@Table(name = "document")
@SQLRestriction("deleted = false")
public class Document {

    @Id
    private Long id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private boolean deleted;

    // Constructor và accessors.
}
~~~

JPQL:

~~~java
List<Document> documents = entityManager.createQuery(
    "select d from Document d order by d.id",
    Document.class
).getResultList();
~~~

SQL có ý nghĩa tương đương:

~~~sql
SELECT d.id, d.title, d.deleted
FROM document d
WHERE d.deleted = false
ORDER BY d.id;
~~~

**Điểm cần nhớ:** `@SQLRestriction` là một **read-visibility condition**. Nó không tự biến `DELETE` thành `UPDATE`, không chặn mọi đường SQL/JDBC ngoài ORM và không tạo cơ chế phân quyền. Predicate **luôn áp dụng trong phạm vi mapping tương ứng**, không thể tắt hoặc truyền tham số runtime như `@Filter`.

> **Phạm vi phiên bản:** `@SQLRestriction` được giới thiệu từ Hibernate ORM **6.3**, không thuộc chuẩn Jakarta Persistence. Ví dụ lấy Hibernate 6.3–6.6, Java 17+ và PostgreSQL làm bối cảnh minh họa. Hibernate 6.4+ bổ sung `@SoftDelete` cho xóa mềm built-in. Hành vi to-one associations, inheritance, caching và bulk DML có những điểm phụ thuộc phiên bản cần xác minh.

---

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Hiểu cú pháp và tính không tham số hóa của `@SQLRestriction`.
2. Phân biệt **class-level entity restriction** với **field/getter-level collection restriction**.
3. Dùng đúng `@SQLJoinTableRestriction` khi predicate nhắm **bảng liên kết**, thay vì bảng entity đích.
4. Nắm các đường đọc có thể chịu restriction: HQL/JPQL, entity loading, collections và associations.
5. Nhận biết native SQL, bulk mutation, first-level cache và second-level cache **không được bảo đảm** hành xử như một câu SELECT mới đã gắn restriction.
6. Phân biệt read restriction với `@SQLDelete`, `@SoftDelete` và `@Filter`.
7. Hiểu SQL NULL, enum status, dialect, indexing và security caveats.
8. Xây dựng integration tests để xác nhận kết quả và SQL được Hibernate phát thực tế.

## 2. Tình huống: bảng document có hàng bị xóa mềm

Giả sử database:

~~~sql
CREATE TABLE document (
    id BIGINT PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    deleted BOOLEAN NOT NULL DEFAULT false
);

INSERT INTO document(id, owner_id, title, deleted)
VALUES
    (1, 10, 'Tài liệu hoạt động', false),
    (2, 10, 'Tài liệu đã xóa mềm', true),
    (3, 20, 'Hướng dẫn API', false);
~~~

Các chức năng thông thường chỉ nên thấy row 1 và 3; riêng quản trị mới có thể xem row 2.

Nếu khai báo điều kiện theo từng query:

~~~java
entityManager.createQuery(
    """
    select d from Document d
    where d.deleted = false
    """,
    Document.class
).getResultList();
~~~

thì mọi chỗ tìm kiếm/danh sách/export cần nhớ cùng predicate. Class-level restriction có thể giảm nguy cơ bỏ sót **trên các SQL loads do entity mapping chi phối**.

Một thao tác SQL ngoài Hibernate hoặc native query không tự nhận điều kiện đó; đây là ranh giới cần hiểu ngay từ đầu.

## 3. Cú pháp đúng của annotation

Hibernate định nghĩa annotation `@SQLRestriction` nhận một chuỗi **native SQL predicate**:

~~~java
@SQLRestriction("deleted = false")
~~~

Một số cách dùng khác:

~~~java
@SQLRestriction("deleted_at IS NULL")
~~~

~~~java
@SQLRestriction("status = 'ACTIVE'")
~~~

~~~java
@SQLRestriction("status IN ('ACTIVE', 'PENDING')")
~~~

~~~java
@SQLRestriction("valid_until > CURRENT_TIMESTAMP")
~~~

Mỗi đoạn là một ví dụ **thay thế**, không phải gắn tất cả lên cùng entity.

Không viết:

~~~java
@SQLRestriction("WHERE deleted = false") // Sai: không cần WHERE.
~~~

Hoặc:

~~~java
@SQLRestriction("deleted == false") // Sai: biểu thức Java, không phải SQL.
~~~

Hibernate tự kết hợp predicate với các phần SQL do nó sinh ra.

## 4. Dùng tên cột database, không dùng tên Java property

Mapping:

~~~java
@Column(name = "deleted_at")
private Instant deletedAt;
~~~

JPQL đúng:

~~~java
select d from Document d where d.deletedAt is null
~~~

SQLRestriction đúng:

~~~java
@SQLRestriction("deleted_at IS NULL")
~~~

Không viết:

~~~java
@SQLRestriction("d.deletedAt is null")
~~~

Đây là SQL fragment, không phải JPQL expression. Hibernate có thể sử dụng alias `d1_0`, `d2_0` và aliases khác tùy query/dialect. Thường nên viết tên cột vật lý đúng table của mapping, không hard-code alias xuất hiện tình cờ ở SQL log.

## 5. Điều kiện tĩnh là cố định trong mapping

~~~java
@SQLRestriction("deleted = false")
~~~

Không thể đổi thành `deleted = true` theo từng request qua `Session.enableFilter()` vì API đó dành cho Hibernate `@Filter`.

Không thể parameterize:

~~~java
@SQLRestriction("owner_id = :ownerId") // Không có bind parameter.
~~~

Khi predicate phụ thuộc người dùng đăng nhập, tenant, thời gian “as-of”, quyền role hoặc khu vực, hãy dùng `@Filter`, parameterized HQL/Criteria hoặc tenant strategy tương ứng.

**Không dùng annotation static để viết SQL dựa trên user input.** Đây là metadata lúc build/boot mapping.

## 6. Tĩnh không nhất thiết nghĩa kết quả bất biến theo thời gian

~~~java
@SQLRestriction("expires_at > CURRENT_TIMESTAMP")
~~~

Fragment SQL cố định nhưng `CURRENT_TIMESTAMP` được database đánh giá mỗi lần thực thi. Điều đó có thể tạo một **loaded view phụ thuộc thời gian**.

Hệ quả:

- Cache có thể giữ một result đã hết hạn, vì cache entry không tự thay đổi cùng đồng hồ.
- SQL function và timezone phụ thuộc DB.
- Query plan/index có thể khác với một điều kiện được bind parameter.
- Test dễ bị flaky.
- Không thể chọn “xem dữ liệu tại thời điểm X” thông qua parameter runtime trong annotation.

Nếu cần historical-as-of queries, cân nhắc truy vấn/filter parameter động. Nếu muốn dùng time-dependent static predicate, kiểm soát cache và thời điểm evaluation.

## 7. Entity-level restriction

~~~java
@Entity
@Table(name = "account")
@SQLRestriction("active = true")
public class Account {
    @Id private Long id;
    private boolean active;

    // Other fields.
}
~~~

Predicate được gắn với entity table khi Hibernate load Account trong các paths tương ứng.

Ví dụ:

~~~java
List<Account> accounts = entityManager.createQuery(
    "select a from Account a order by a.id",
    Account.class
).getResultList();
~~~

SQL có ý nghĩa:

~~~sql
SELECT a.*
FROM account a
WHERE a.active = true
ORDER BY a.id;
~~~

Class-level restriction phù hợp khi điều kiện là **mặc định visibility của cả loại entity**. Nếu chỉ một association cần lọc theo subtype, đừng đặt điều kiện subtype lên toàn entity.

## 8. Collection-level restriction

Nếu một Client có nhiều Account nhưng chỉ muốn hiển thị debit accounts ở một collection:

~~~java
@OneToMany(mappedBy = "client")
@SQLRestriction("account_type = 'DEBIT'")
private List<Account> debitAccounts;
~~~

Predicate thuộc **collection `debitAccounts`**, không tự ràng buộc mọi `from Account` query trở thành chỉ DEBIT.

Một entity có thể xuất hiện qua một association restricted và vẫn hiện trong query root khác nếu entity-level mapping không có cùng predicate. Phải xác định đúng scope.

## 9. Ví dụ có hai collection restrictions

~~~java
public enum AccountType {
    DEBIT,
    CREDIT
}

@Entity
@Table(name = "account")
@SQLRestriction("active = true")
public class Account {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "client_id")
    private Client client;

    @Enumerated(EnumType.STRING)
    @Column(name = "account_type")
    private AccountType type;

    private boolean active;

    public boolean isActive() { return active; }
    public AccountType getType() { return type; }
}
~~~

~~~java
@Entity
@Table(name = "client")
public class Client {

    @Id
    private Long id;

    @OneToMany(mappedBy = "client")
    @SQLRestriction("account_type = 'DEBIT'")
    private List<Account> debitAccounts;

    @OneToMany(mappedBy = "client")
    @SQLRestriction("account_type = 'CREDIT'")
    private List<Account> creditAccounts;

    public List<Account> getDebitAccounts() { return debitAccounts; }
    public List<Account> getCreditAccounts() { return creditAccounts; }
}
~~~

Khi lazy-load `client.debitAccounts`, SQL có ý nghĩa:

~~~sql
SELECT a.*
FROM account a
WHERE a.client_id = ?
  AND a.active = true
  AND a.account_type = 'DEBIT';
~~~

Khi load `creditAccounts`, predicate thành `account_type = 'CREDIT'`.

**Hai điều kiện cùng tham gia:** entity `Account` chỉ visible nếu active và collection chỉ chứa loại được khai báo.

## 10. Truy vấn trực tiếp Account vẫn có phạm vi khác

~~~java
List<Account> allActive = entityManager.createQuery(
    "select a from Account a",
    Account.class
).getResultList();
~~~

Query root Account chịu `active = true`, nhưng **không** tự thêm DEBIT hay CREDIT bởi các association restrictions của Client.

Nguyên tắc:

~~~text
Query root Account
  -> Điều kiện entity-level: active = true

Client.debitAccounts
  -> Điều kiện entity-level: active = true
  -> Điều kiện collection-level: account_type = 'DEBIT'
~~~

Vì vậy, không dùng collection annotation thay cho policy toàn entity.

## 11. OneToMany với child visibility

Giả sử Order có nhiều OrderLine, nhưng collection chỉ chứa line chưa hủy:

~~~java
@Entity
class PurchaseOrder {
    @Id Long id;

    @OneToMany(mappedBy = "order")
    @SQLRestriction("cancelled = false")
    List<OrderLine> activeLines;
}
~~~

SQL khi load association có ý nghĩa:

~~~sql
SELECT l.*
FROM order_line l
WHERE l.order_id = ?
  AND l.cancelled = false;
~~~

Predicate nhắm **bảng entity con**. Nếu query `from OrderLine` mà OrderLine không có entity-level restriction, các line cancelled vẫn có thể xuất hiện.

Thêm OrderLine đã cancelled vào Java collection cũng không bị `@SQLRestriction` tự từ chối: annotation là loaded-view condition, không phải validation.

## 12. ManyToMany có hai loại bảng

Ví dụ quan hệ Document–Tag:

~~~text
document
    |
document_tag       <- join table, chứa trạng thái liên kết
    |
tag                <- entity table, chứa trạng thái Tag
~~~

Hai câu hỏi khác nhau:

1. Bản thân Tag có còn active/visible không?
2. Mối quan hệ giữa Document và Tag có còn active không?

Nếu Tag archived, lọc **tag entity table**.

Nếu Document–Tag link bị revoked, lọc **document_tag join table**.

Không dùng một annotation để nhắm nhầm bảng.

## 13. SQLJoinTableRestriction lọc join table

Bảng:

~~~sql
CREATE TABLE document_tag (
    document_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    relation_status VARCHAR(20) NOT NULL,
    PRIMARY KEY (document_id, tag_id)
);
~~~

Mapping:

~~~java
@ManyToMany
@JoinTable(
    name = "document_tag",
    joinColumns = @JoinColumn(name = "document_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id")
)
@SQLJoinTableRestriction("relation_status = 'ACTIVE'")
private Set<Tag> tags = new HashSet<>();
~~~

Generated SQL có ý nghĩa:

~~~sql
SELECT t.*
FROM document_tag dt
JOIN tag t ON t.id = dt.tag_id
WHERE dt.document_id = ?
  AND dt.relation_status = 'ACTIVE';
~~~

`@SQLJoinTableRestriction` dùng khi column thuộc **association table**, không phải bảng entity đích. Annotation này cũng được giới thiệu ở Hibernate 6.3.

## 14. Kết hợp target restriction và join restriction

Entity Tag:

~~~java
@Entity
@Table(name = "tag")
@SQLRestriction("archived = false")
public class Tag {
    @Id private Long id;
    private boolean archived;
}
~~~

Document.tags:

~~~java
@ManyToMany
@JoinTable(
    name = "document_tag",
    joinColumns = @JoinColumn(name = "document_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id")
)
@SQLJoinTableRestriction("relation_status = 'ACTIVE'")
private Set<Tag> tags;
~~~

Collection chỉ nên hiển thị Tag khi:

- Join row: `relation_status = 'ACTIVE'`.
- Target Tag row: `archived = false`.

SQL minh họa:

~~~sql
SELECT t.*
FROM document_tag dt
JOIN tag t ON t.id = dt.tag_id
WHERE dt.document_id = ?
  AND dt.relation_status = 'ACTIVE'
  AND t.archived = false;
~~~

Đây là cách kết hợp restrictions trên **hai bảng riêng biệt**.

## 15. SQLRestriction trên ManyToMany nhắm target entity rows

Có thể thấy dạng:

~~~java
@ManyToMany
@JoinTable(name = "document_tag")
@SQLRestriction("archived = false")
@SQLJoinTableRestriction("relation_status = 'ACTIVE'")
private Set<Tag> tags;
~~~

Trong mapping này:

- `@SQLRestriction` nhắm predicate bảng target Tag.
- `@SQLJoinTableRestriction` nhắm predicate bảng document_tag.

Không viết `@SQLRestriction("relation_status='ACTIVE'")` với kỳ vọng Hibernate tự tìm column chỉ nằm trong join table; có thể xảy ra SQL alias/cột sai.

## 16. ElementCollection và collection table

Ví dụ:

~~~java
@ElementCollection
@CollectionTable(
    name = "document_note",
    joinColumns = @JoinColumn(name = "document_id")
)
@Column(name = "note_text")
@SQLRestriction("visible = true")
private List<String> visibleNotes;
~~~

Ở đây condition nhắm rows của collection table theo khả năng mapping Hibernate.

Cần phân biệt:

- SQL restriction cho **đọc note rows**.
- Default giá trị `visible` khi INSERT.
- Cách thêm/xóa phần tử collection.
- Collection cache và SQL generated.
- Schema đảm bảo column tồn tại và có kiểu phù hợp.

Annotation lọc không tự định nghĩa database default hoặc thay đổi mutation semantics của collection.

## 17. To-one association và target bị hidden

Ví dụ:

~~~java
@Entity
@SQLRestriction("active = true")
class Customer {
    @Id Long id;
    boolean active;
}
~~~

~~~java
@Entity
class PurchaseOrder {
    @Id Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    Customer customer;
}
~~~

Database có thể giữ `purchase_order.customer_id=42` trỏ Customer inactive. FK vẫn hợp lệ, nhưng entity-level restriction có thể làm target không visible.

**Hành vi trong eager/lazy/fetch join/to-one loading có khác biệt giữa các Hibernate versions.** Một bản có thể trả NULL cho hidden association ở một path; phiên bản khác hoặc path khác có thể throw khi initialize proxy.

Phải kiểm thử:

- `find()` load parent.
- LAZY to-one initialization.
- EAGER to-one.
- Fetch join.
- Entity graph.
- Target đã nằm trong persistence context/cache.

Không tự dựa vào `optional=false` để kết luận hidden target sẽ được load.

## 18. LEFT JOIN và vị trí predicate

SQL:

~~~sql
SELECT o.*, c.*
FROM purchase_order o
LEFT JOIN customer c
  ON c.id = o.customer_id
 AND c.active = true;
~~~

giữ Order khi Customer không hợp lệ, phần Customer có thể NULL.

SQL khác:

~~~sql
SELECT o.*, c.*
FROM purchase_order o
LEFT JOIN customer c
  ON c.id = o.customer_id
WHERE c.active = true;
~~~

có thể loại Order vì WHERE không chấp nhận `c.active=NULL`.

Hibernate đặt mapping restrictions vào SQL theo join plan của từng version/mapping. Với optional to-one và collection fetch joins, **hãy inspect SQL và test parent retention**, đừng suy luận từ annotation syntax rằng vị trí predicate luôn giống nhau.

## 19. JPQL/HQL kết hợp predicate bằng AND

~~~java
@SQLRestriction("deleted = false")
~~~

và HQL:

~~~java
select d
from Document d
where d.ownerId = :ownerId
order by d.id
~~~

cho ý nghĩa:

~~~sql
WHERE d.owner_id = ?
  AND d.deleted = false
~~~

Hibernate có thể thêm ngoặc, aliases và các conditions khác. Bạn không cần gõ lại `d.deleted=false` trong mọi HQL khi mapping đã có restriction.

Tuy nhiên, nếu một query explicit predicate phục vụ query contract hoặc migration portable giữa JPA providers, có thể giữ theo convention. Đừng để lặp predicate đánh lạc hướng rằng một trong hai điều kiện thực ra không được áp dụng.

## 20. Load by ID và @SQLRestriction

~~~java
Document d = entityManager.find(Document.class, id);
~~~

Hành vi phải xét:

- Khi cần SQL mới, Hibernate có entity restriction ở mapping.
- Nếu entity **đã managed**, first-level cache có thể trả cùng object mà không SELECT.
- L2 cache có thể tham gia tùy cấu hình/version.
- `getReference()` có thể chỉ tạo proxy trước khi load thật.
- Path của to-one association đã thay đổi qua Hibernate versions.

**Không chỉ kiểm thử `from Document` rồi kết luận tất cả `find()/getReference()` và association loads đều có cùng semantics.** Dùng fresh persistence context và SQL logs để kiểm tra.

## 21. Restriction không tự lọc Java objects đang ở memory

Ví dụ:

~~~java
Document d = entityManager.find(Document.class, id);

// Một transaction khác đánh dấu row deleted=true.
// Biến Java d không tự biến mất khỏi persistence context.
~~~

Một collection đã initialized cũng không tự chạy SQL predicate lại mỗi khi thuộc tính của phần tử được thay đổi.

Restriction là **SQL loading condition**, không phải `Predicate<Document>` được chạy liên tục trên heap.

Nếu cần quan sát dữ liệu DB mới:

1. Flush/commit thay đổi.
2. Kết thúc hoặc clear persistence context.
3. Load lại trong transaction/context mới.
4. Test với native SQL row state nếu cần.
5. Xem transaction isolation và cache policy.

## 22. Second-level cache và query cache

Hibernate có:

- L1 cache per Session.
- L2 cache theo SessionFactory/cache provider.
- Query cache khi được bật.

SQLRestriction không tự xử lý mọi stale-cache scenario:

- Native SQL/ETL cập nhật deleted flag.
- External application sửa database.
- `CURRENT_TIMESTAMP` khiến visibility đổi theo thời gian mà không UPDATE.
- Entity đã được managed trước khi condition không còn thỏa.

Đừng khẳng định cache luôn bypass hoặc luôn reevaluate restriction. Behavior phụ thuộc load path, provider version và cache invalidation.

Khi visibility phụ thuộc thời gian hoặc external writers, kiểm tra TTL, invalidation và integration tests đa transaction/cache-enabled.

## 23. SQLRestriction không kiểm tra data invariants khi ghi

~~~java
@Entity
@SQLRestriction("active = true")
class Account {
    @Id Long id;
    boolean active;
}
~~~

Annotation không ngăn application tạo row với `active=false`:

~~~java
Account a = new Account();
a.setActive(false);
entityManager.persist(a);
~~~

DB có chấp nhận hay không tùy constraints. Sau khi clear context, row có thể bị ẩn khi query bằng restricted entity.

**Không thấy row sau khi persist không đồng nghĩa INSERT thất bại.** Query visibility và validation/mutation là các mối quan tâm khác nhau.

## 24. Chỉ dùng SQLRestriction không phải soft delete

~~~java
@Entity
@SQLRestriction("deleted = false")
class Document {
    // ...
}
~~~

Nếu gọi:

~~~java
entityManager.remove(document);
~~~

Hibernate vẫn có thể phát **physical DELETE** theo entity mapping mặc định.

Để thực hiện soft delete cần cơ chế mutation riêng:

- `@SQLDelete` custom SQL.
- `@SoftDelete` built-in từ Hibernate 6.4+.
- Service/DB trigger policy nếu được thiết kế rõ.

**Read visibility không tự tạo write semantics.**

## 25. Custom soft delete: SQLDelete + SQLRestriction

~~~java
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.SQLRestriction;

@Entity
@Table(name = "document")
@SQLDelete(
    sql = "UPDATE document SET deleted = true WHERE id = ?"
)
@SQLRestriction("deleted = false")
public class Document {
    @Id
    private Long id;

    private String title;

    private boolean deleted = false;
}
~~~

Với entity removal phù hợp, Hibernate có thể dùng custom UPDATE thay cho DELETE. Restriction giúp các entity reads ẩn row deleted.

Cần chú ý:

- Ví dụ không khai báo `@Version`. Với versioned entity, custom SQL parameter ordering/optimistic lock semantics cần điều chỉnh theo version.
- SQL custom có thể cần affected-row verification.
- Entity callbacks/cascades và second-level cache cần test.
- Bulk SQL/JPQL/native DELETE có thể bypass custom entity DELETE.
- Java field `deleted` không tự thay đổi trong mọi scope chỉ vì SQL custom đã chạy.

Pattern này hữu ích với legacy versions hoặc custom business rules; không được coi là một dòng annotation là đủ cho toàn hệ soft delete.

## 26. Hibernate @SoftDelete từ 6.4+

Hibernate 6.4 giới thiệu built-in annotation:

~~~java
import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.SoftDeleteType;

@Entity
@Table(name = "document")
@SoftDelete(
    strategy = SoftDeleteType.DELETED,
    columnName = "deleted"
)
public class Document {
    @Id
    private Long id;
    private String title;
}
~~~

Với `SoftDeleteType.DELETED`, indicator `true` nghĩa là đã xóa, `false` nghĩa là active.

Built-in support có thể quản lý predicate và soft-delete mutation thay cho việc ghép thủ công SQLDelete/SQLRestriction.

Không đồng thời gắn mọi annotation soft-delete có vẻ tương tự vào cùng entity mà không hiểu conflicts. Test mapping với DB indicator type, converters, inheritance, cache và mutation paths.

## 27. SoftDelete trên collection có giới hạn riêng

Hibernate hỗ trợ built-in soft delete trên một số collection-table mappings, chẳng hạn ElementCollection hoặc ManyToMany join table.

~~~java
@ElementCollection
@CollectionTable(
    name = "document_label",
    joinColumns = @JoinColumn(name = "document_id")
)
@Column(name = "label")
@SoftDelete(columnName = "deleted")
private List<String> labels;
~~~

Với `@OneToMany`, child rows là entities có lifecycle riêng. Theo Hibernate User Guide, đặt `@SoftDelete` trực tiếp trên one-to-many association không được hỗ trợ như trên collection table trong các phiên bản được mô tả.

Đừng nhầm **soft-delete indicator mutation** của `@SoftDelete` với read-only join-table condition của `@SQLJoinTableRestriction`.

## 28. SQLRestriction so với Filter

| Thuộc tính | SQLRestriction | Filter |
|---|---|---|
| Condition cố định trong mapping | Có | Condition khai báo nhưng activation runtime |
| Có thể disable tại Session | Không | Có |
| Runtime parameters | Không | Có thể |
| Phù hợp với | Always-on loaded-view predicate | User/time/tenant scoped query |
| Cần nhớ bật | Không | Có |
| Admin tạm xem cả hidden rows | Không với cùng entity mapping | Có thể disable nếu được phép |
| Chuẩn JPA | Không | Không |

Nếu predicate cần `currentUserId`, `visibleAt`, `region` hoặc configuration đổi theo request, `@Filter`/query parameters phù hợp hơn.

## 29. Ví dụ Filter động

~~~java
import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.ParamDef;

@Entity
@FilterDef(
    name = "byOwner",
    parameters = @ParamDef(
        name = "ownerId",
        type = Long.class
    )
)
@Filter(
    name = "byOwner",
    condition = "owner_id = :ownerId"
)
public class Document {
    // ...
}
~~~

Trong Session:

~~~java
Session session = entityManager.unwrap(Session.class);

session.enableFilter("byOwner")
    .setParameter("ownerId", currentUserId);

try {
    List<Document> docs = session.createQuery(
        "from Document",
        Document.class
    ).getResultList();
    process(docs);
} finally {
    session.disableFilter("byOwner");
}
~~~

Filter có các edge cases với load-by-key/lazy associations và cache theo Hibernate version. Nó không tự là database security boundary. Nếu class còn có SQLRestriction, static predicate tiếp tục áp dụng dù Filter bị disable.

## 30. FilterJoinTable khác SQLJoinTableRestriction

Nếu join-table condition cần một tham số thời gian:

~~~java
@ManyToMany
@JoinTable(name = "document_tag")
@FilterJoinTable(
    name = "activeAt",
    condition = "valid_from <= :moment AND valid_until > :moment"
)
private Set<Tag> tags;
~~~

Cần định nghĩa FilterDef và enable parameter `moment` theo Session.

Nếu chỉ cần static status:

~~~java
@SQLJoinTableRestriction("relation_status = 'ACTIVE'")
~~~

Chọn công cụ theo hai câu hỏi: **predicate thuộc bảng nào?** và **có cần tham số/toggle không?**

## 31. SQL NULL có thể làm row bị ẩn không mong muốn

Nếu cột `deleted` có thể NULL:

~~~sql
SELECT *
FROM document
WHERE deleted = false;
~~~

rows có `deleted=NULL` không match vì `NULL = false` là `UNKNOWN`, không phải TRUE.

Lựa chọn:

- Migration NULL sang false.
- Schema `NOT NULL DEFAULT false`.
- Predicate tường minh `deleted IS NULL OR deleted = false`.

Tương tự:

~~~java
@SQLRestriction("status <> 'DELETED'")
~~~

không hiển thị rows `status=NULL`.

Ưu tiên xác định ý nghĩa NULL trong domain và có database constraints, thay vì để SQL three-valued logic quyết định một cách vô thức.

## 32. Whitelist vs blacklist trạng thái

Blacklist:

~~~java
@SQLRestriction("status <> 'DELETED'")
~~~

Whitelist:

~~~java
@SQLRestriction("status IN ('ACTIVE', 'PENDING')")
~~~

Khi xuất hiện trạng thái mới:

- Blacklist có thể cho hiển thị nó ngay.
- Whitelist chỉ cho hiển thị khi được bổ sung.
- Cả hai thường loại NULL.

Không có mẫu nào luôn đúng. Cần biết state machine và policy hiển thị. Với `EnumType.STRING`, dùng đúng chuỗi được lưu trong database.

## 33. SQL dialect và Boolean storage

Trên PostgreSQL:

~~~sql
WHERE deleted = false
~~~

Một DB khác có thể dùng:

~~~sql
WHERE deleted = 0
~~~

hoặc:

~~~sql
WHERE deleted = 'N'
~~~

SQLRestriction là **native SQL**, không phải JPQL được Hibernate chuyển đổi đầy đủ theo property type. Nếu dự án hỗ trợ nhiều dialect:

- Test thực tế trên từng DB.
- Dùng predicates đủ portable.
- Xem khả năng DialectOverride.SQLRestriction trong phiên bản hỗ trợ.
- Không hard-code vendor functions/aliases tùy tiện.
- Kiểm tra naming strategy và physical column names.

## 34. Mapping nhiều bảng và inheritance

Entity có thể dùng:

- `@SecondaryTable`.
- `@Inheritance(strategy=JOINED)`.
- `SINGLE_TABLE` với discriminator.
- `TABLE_PER_CLASS`.
- HQL polymorphic root queries.

Một restriction có thể cần được diễn giải trên SQL gồm nhiều aliases/tables. Đặc biệt nếu cột nằm ở secondary table hoặc hierarchy subclass, hãy test query/load paths riêng theo Hibernate version.

Không dùng alias từ một SQL log làm cố định cho mọi path. Test root/subtype queries, associations, `find()`, fetch joins và soft-delete DML khi liên quan.

## 35. LEFT JOIN FETCH và collection cardinality

~~~java
List<Client> clients = entityManager.createQuery(
    """
    select distinct c
    from Client c
    left join fetch c.debitAccounts
    """,
    Client.class
).getResultList();
~~~

Khi collection restricted, Hibernate có thể ghép predicate để chỉ hydrate active DEBIT accounts. Nhưng các vấn đề ORM vẫn tồn tại:

- To-many joins tạo nhiều SQL rows cho một parent.
- Pagination với collection fetch có hạn chế; có thể bị cảnh báo hoặc thực hiện in-memory tùy version/config.
- Predicate ở ON vs WHERE ảnh hưởng parent retention.
- Collection đã initialized trong persistence context không tự reload.
- Lazy collection load có thể dùng SQL khác với fetch join.

Cần quan sát SQL và test parent không có visible children.

## 36. Native SQL không tự thêm WHERE

~~~java
List<?> rows = entityManager.createNativeQuery(
    """
    SELECT id, title, deleted
    FROM document
    ORDER BY id
    """
).getResultList();
~~~

Native SQL do developer viết không được Hibernate tự động rewrite mọi câu lệnh để thêm entity SQLRestriction.

Nếu muốn query native cùng visibility:

~~~java
List<?> rows = entityManager.createNativeQuery(
    """
    SELECT id, title
    FROM document
    WHERE deleted = false
    ORDER BY id
    """
).getResultList();
~~~

Khi native result được map thành entity, provider có thể còn bước hydration/association resolution theo version; không nên suy luận rằng raw SQL text được bảo vệ bởi annotation.

Đây là lý do SQLRestriction **không đủ cho authorization/security**.

## 37. Bulk JPQL/HQL mutation và custom delete

~~~java
entityManager.createQuery(
    """
    delete from Document d
    where d.ownerId = :ownerId
    """
)
.setParameter("ownerId", ownerId)
.executeUpdate();
~~~

Bulk DML không tương đương gọi `entityManager.remove()` trên từng entity managed. Nó có thể bypass lifecycle callbacks, entity custom delete SQL và cascade semantics.

Không mặc định entity SQLRestriction sẽ biến mọi bulk mutation thành “chỉ tác động active rows”. Nếu business rule yêu cầu, thêm predicate rõ và kiểm tra SQL thật:

~~~sql
UPDATE document
SET deleted = true
WHERE owner_id = :ownerId
  AND deleted = false;
~~~

Tách rõ **read visibility** khỏi **mutation policy**.

## 38. Spring Data batch delete cũng phải kiểm tra

Spring Data JPA:

~~~java
repository.deleteAllInBatch();
~~~

có thể sử dụng bulk delete SQL chứ không gọi entity remove trên từng row. Khi đó:

- `@PreRemove`/`@PostRemove` có thể không được gọi như entity lifecycle.
- `@SQLDelete` không có cơ hội thay SQL của từng entity theo cùng cách.
- ORM cascades/orphan removal có thể không chạy.
- Soft-delete row có thể bị xóa vật lý nếu SQL không được thiết kế đúng.

Test riêng `delete`, `deleteAll`, `deleteAllInBatch` và custom bulk queries trong ứng dụng có soft-delete requirement.

## 39. SQLRestriction không phải tenant isolation

Ví dụ hard-code:

~~~java
@SQLRestriction("tenant_id = 100")
~~~

không phù hợp với tenantId thay đổi theo request. Càng không đủ làm security boundary:

- Native SQL/JDBC có thể bypass.
- ETL/reporting queries ngoài Hibernate không nhận annotation.
- Cache/context đã load cần lifecycle riêng.
- Không đảm bảo UPDATE/DELETE của mọi đường SQL bị ràng buộc.
- DB user vẫn có thể có quyền truy cập tenant khác.

Để cách ly dữ liệu, dùng multi-tenancy support thích hợp, authorization, DB permissions và row-level security (RLS) khi cần enforcement mạnh. Hibernate Filter chỉ là một lớp hỗ trợ, không thay DB authorization.

## 40. Restore dữ liệu đã bị ẩn

Vì `@SQLRestriction("deleted=false")` không disable được, một admin có thể không load Document đã deleted qua entity query thông thường.

Một restore path có quyền rõ ràng:

~~~java
@Transactional
public int restoreDocument(Long id) {
    return entityManager.createNativeQuery(
        """
        UPDATE document
        SET deleted = false
        WHERE id = :id AND deleted = true
        """
    )
    .setParameter("id", id)
    .executeUpdate();
}
~~~

Sau native mutation, kiểm soát cache invalidation/persistence context.

Cần kiểm tra:

- Actor có quyền restore không?
- Có xung đột unique keys với active rows mới không?
- Có khôi phục child/links không?
- Audit và domain event `DocumentRestored` cần ghi ở đâu?
- Retention policy có cho restore nữa không?

Không mở native SQL bypass restriction cho user thông thường.

## 41. Soft delete và foreign keys

Row bị soft-delete vẫn còn trong DB:

- FK từ child đến parent vẫn hợp lệ.
- DB ON DELETE CASCADE thường không chạy với UPDATE flag.
- ORM restriction có thể ẩn parent entity qua association.
- Một Java association có thể trông như null/missing dù FK khác null.
- Restore không tự restore entire graph.

Ví dụ:

~~~text
order.customer_id = 42
customer#42.active = false

DB foreign key hợp lệ,
nhưng Hibernate Customer @SQLRestriction(active=true)
có thể khiến association không visible tùy load path/version.
~~~

Không nhầm **referential integrity vật lý** và **ORM visibility**.

## 42. Soft delete và UNIQUE constraints

Nếu bảng Account có email unique, row deleted vẫn nằm trong DB. SQLRestriction không làm unique index tự bỏ qua row đó.

PostgreSQL có thể dùng partial unique index nếu domain cho phép tái sử dụng email sau khi soft-delete:

~~~sql
CREATE UNIQUE INDEX uq_account_email_live
ON account (lower(email))
WHERE deleted = false;
~~~

Cần cân nhắc:

- Có thật sự cho phép tái sử dụng identifier/email?
- Restore old account có xung đột không?
- FK và audit còn trỏ Account cũ?
- Collation/case sensitivity đúng chưa?
- DB có hỗ trợ partial indexes không?

Visibility là một khái niệm; database data integrity là khái niệm khác.

## 43. Index cho predicate phổ biến

Query:

~~~sql
SELECT id, title
FROM document
WHERE owner_id = ?
  AND deleted = false
ORDER BY id;
~~~

Có thể xem xét composite index:

~~~sql
CREATE INDEX ix_document_owner_deleted
ON document (owner_id, deleted, id);
~~~

Hoặc PostgreSQL partial index:

~~~sql
CREATE INDEX ix_document_live_owner
ON document (owner_id, id)
WHERE deleted = false;
~~~

Hiệu quả còn phụ thuộc phân bố deleted rows, selectivity của owner, kích thước bảng, ORDER BY/LIMIT và write costs. Đo qua EXPLAIN/ANALYZE trên dataset đại diện; không khẳng định một index luôn tốt hơn.

## 44. SQL logging giúp nhìn phạm vi áp dụng

Spring Boot/Hibernate 6:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Quan sát:

- HQL root query có entity restriction không?
- Lazy collection load có entity-level và collection-level predicates không?
- ManyToMany join-table predicate gắn đúng alias không?
- Optional LEFT JOIN giữ parent như kỳ vọng không?
- Native SQL có tự thêm restriction không?
- Remove có phát UPDATE hay DELETE?
- Bulk DELETE có SQL khác entity delete không?

Bind logging có thể lộ PII/secrets, chỉ bật có kiểm soát. SQL log là nguồn quan sát, không thay kết quả integration test.

## 45. Test entity-level restriction

Fixture:

~~~sql
INSERT INTO document(id, owner_id, title, deleted)
VALUES
  (1, 10, 'A', false),
  (2, 10, 'B', true),
  (3, 20, 'C', false);
~~~

JUnit/AssertJ:

~~~java
@Test
void hidesDeletedDocumentsInEntityQuery() {
    entityManager.clear();

    List<Document> docs = entityManager.createQuery(
        "select d from Document d order by d.id",
        Document.class
    ).getResultList();

    assertThat(docs)
        .extracting(Document::getId)
        .containsExactly(1L, 3L);
}
~~~

Đối chứng native SQL:

~~~java
@Test
void nativeSqlStillCountsPhysicalRows() {
    Number count = (Number) entityManager.createNativeQuery(
        "select count(*) from document"
    ).getSingleResult();

    assertEquals(3L, count.longValue());
}
~~~

Test cần fixture được commit và persistence context được quản lý rõ, tránh dùng object managed từ test setup làm sai quan sát.

## 46. Test collection-specific restrictions

Fixture Account:

| Type | Active | Debit collection | Credit collection |
|---|---|---|---|
| DEBIT | true | Có | Không |
| DEBIT | false | Không | Không |
| CREDIT | true | Không | Có |
| CREDIT | false | Không | Không |

Test:

~~~java
@Test
void composesEntityAndCollectionRestrictions() {
    entityManager.clear();

    Client c = entityManager.find(Client.class, clientId);

    assertThat(c.getDebitAccounts())
        .allMatch(a -> a.isActive()
                 && a.getType() == AccountType.DEBIT);

    assertThat(c.getCreditAccounts())
        .allMatch(a -> a.isActive()
                 && a.getType() == AccountType.CREDIT);
}
~~~

Đừng chỉ test Java list; inspect SQL để biết `active` và `account_type` đều được đưa vào collection query.

## 47. Test ManyToMany hai lớp

Với Tag archived và document_tag relation_status:

| Link | Target Tag | Kỳ vọng |
|---|---|---|
| ACTIVE | archived=false | Có |
| INACTIVE | archived=false | Không |
| ACTIVE | archived=true | Không |
| INACTIVE | archived=true | Không |

Khi test đủ bốn trường hợp, bạn xác minh được cả `@SQLJoinTableRestriction` lẫn `@SQLRestriction` trên target entity. Nếu chỉ test một Tag inactive và tất cả links active, chưa chứng minh link-table restriction.

## 48. Test fresh persistence context và cache

Sau khi đổi field deleted:

~~~java
Document d = entityManager.find(Document.class, id);

d.setDeleted(true);
entityManager.flush();

// d vẫn là object Java trong context hiện tại.
entityManager.clear();

Document freshlyLoaded =
    entityManager.find(Document.class, id);
~~~

Test cần phân biệt:

1. SQL UPDATE deleted flag đã thực hiện chưa?
2. Persistence context có clear không?
3. Load-by-ID có gắn restriction trong version đang chạy không?
4. Query cache/L2 cache có bật không?
5. Test transaction có rollback tự động ở cuối không?

Không dùng chỉ một assertion vào Java field `d.isDeleted()` để kết luận restriction chạy đúng. Nếu cần xác nhận dữ liệu durable, commit scenario rồi đọc bằng transaction/EntityManager mới.

## 49. Test soft-delete operation

Khi dùng SQLDelete+SQLRestriction hoặc SoftDelete:

1. Persist active entity và commit.
2. Mở transaction mới, load entity.
3. Gọi `entityManager.remove()`.
4. Commit.
5. Native SQL xem row còn vật lý không và deleted flag có đổi không.
6. JPQL/HQL xác nhận không còn visible.
7. Test bulk delete riêng trên database test được reset.
8. Test entity có `@Version` nếu áp dụng.
9. Test association FK và cache behavior.

Chỉ kiểm tra `findAll().size()` giảm **không đủ** để chứng minh soft-delete: physical DELETE cũng làm kết quả giảm.

## 50. @Where cũ và @SQLRestriction mới

Trước Hibernate 6.3, nhiều codebases có:

~~~java
import org.hibernate.annotations.Where;

@Entity
@Where(clause = "deleted = false")
public class Document {
    // ...
}
~~~

Từ Hibernate 6.3, `@Where` được đánh dấu deprecated, javadoc hướng dẫn dùng:

~~~java
@SQLRestriction("deleted = false")
~~~

Tương tự `@WhereJoinTable` có counterpart `@SQLJoinTableRestriction`.

Khi migrate:

- Đổi import/annotation đúng version.
- Test HQL root, collections và find.
- Test optional to-one fetch paths.
- Test many-to-many join table filtering.
- Test cache behavior và bulk/native mutation.
- Nếu dùng soft delete, cân nhắc Hibernate 6.4+ `@SoftDelete`.

Đừng coi migration là đổi tên thuần túy nếu application có graph phức tạp.

## 51. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ SQLRestriction tự soft delete | Remove vẫn có thể physical DELETE | SQLDelete/SoftDelete |
| Dùng `:ownerId` trong restriction | Không bind được | Filter/query param |
| Nhầm target entity với join table | Predicate sai cột | SQLJoinTableRestriction |
| Đặt collection restriction rồi tưởng root query cũng lọc | Root query thấy rows khác | Chọn đúng entity-level |
| Dùng Java property trong SQL fragment | SQL sai tên cột | Physical column names |
| `status <> 'DELETED'` với NULL | NULL bị loại | NOT NULL/migration |
| Hard-code alias | Alias đổi theo query | Để Hibernate chọn alias |
| Native SQL không thêm WHERE | Hidden rows vẫn có thể thấy | SQL predicate/authorization |
| Bulk DELETE bypass custom DML | Physical delete/lost callbacks | Test từng mutation path |
| Dùng restriction cho tenant động | Không parameterize | Tenant strategy/RLS |
| Dùng restriction làm bảo mật | SQL/JDBC khác bypass | Authorization/DB policy |
| Cache với CURRENT_TIMESTAMP | Visibility stale | TTL/invalidation |
| Test trong cùng EntityManager | Managed entity che SQL behavior | New context |
| Assume to-one loading giống mọi version | Null/exception khác nhau | Version-specific tests |
| Quên unique/FK khi soft delete | Restore conflicts | DB constraints/domain policy |

## 52. Bảng chọn giải pháp

| Tình huống | Lựa chọn |
|---|---|
| Luôn ẩn deleted entity rows | SQLRestriction |
| Hai filtered collections DEBIT/CREDIT | SQLRestriction trên association |
| ManyToMany chỉ hiện active links | SQLJoinTableRestriction |
| Điều kiện thay đổi theo user/time | Filter hoặc query parameters |
| Dynamic condition trên join table | FilterJoinTable |
| Xóa mềm entity, Hibernate 6.4+ | SoftDelete |
| Legacy soft-delete với SQL riêng | SQLDelete + read restriction |
| Admin restore hoặc audit hidden rows | Authorized native/DTO read model |
| Multi-tenant isolation mạnh | Tenant strategy + DB RLS/permissions |
| JDBC/reporting ngoài Hibernate | Database policy/SQL conditions |
| Native/bulk mutation | Explicit DML predicate và tests |
| Time-based loaded view | Cache/expiry design riêng |

## 53. Checklist triển khai

**Mapping**

- [ ] Hibernate version hỗ trợ SQLRestriction (6.3+)?
- [ ] Predicate viết bằng SQL physical columns?
- [ ] Không cần runtime parameter/enable-disable?
- [ ] Entity-level hay collection-level đúng phạm vi?
- [ ] Join-table dùng SQLJoinTableRestriction?
- [ ] NULL/default/status behavior rõ?
- [ ] Không hard-code Hibernate aliases?
- [ ] Inheritance/secondary tables được kiểm tra nếu có?

**Soft delete và bảo mật**

- [ ] Có mutation mechanism nếu muốn soft delete?
- [ ] SQLDelete/SoftDelete theo đúng Hibernate version?
- [ ] Bulk/native/JDBC paths được kiểm soát?
- [ ] Restore/admin query có authorization?
- [ ] Không coi restriction là tenant/security policy?
- [ ] DB unique/FK/retention rules phù hợp với hidden rows?

**Runtime**

- [ ] Test HQL root, `find`, lazy collection, fetch join?
- [ ] Test to-one hidden target theo lazy/eager?
- [ ] Test L1/L2/query caches?
- [ ] Index/query plan được đánh giá?
- [ ] SQL logs xác nhận predicates đúng bảng/alias?
- [ ] Test NULL, enum statuses, multi-dialect nếu cần?

## 54. Bài tập thực hành

1. Tạo Document với 3 rows, 1 deleted. Gắn `@SQLRestriction("deleted=false")`; query HQL và native SQL, giải thích số lượng khác nhau.
2. Tạo Client/Account với 2 collections DEBIT/CREDIT; xác nhận kết hợp entity-level và association-level restrictions.
3. Tạo ManyToMany Document–Tag với join table `relation_status`; chỉ hiển thị ACTIVE links.
4. Gắn entity restriction `archived=false` lên Tag, kiểm tra bốn tổ hợp link/target statuses.
5. Cho deleted nullable, insert NULL; so sánh `deleted=false` với `deleted IS NULL OR deleted=false`.
6. Thử bind `:ownerId` trong SQLRestriction rồi giải thích vì sao cần Filter hoặc query parameter.
7. So sánh SQL của entity remove khi chỉ có SQLRestriction, khi dùng SQLDelete và khi dùng SoftDelete trên Hibernate 6.4+.
8. Test repository bulk DELETE trên database thử nghiệm để phát hiện hành vi bypass.
9. Đọc entity trong một persistence context, sau đó đổi deleted flag; so sánh reference cũ và load từ context mới.
10. Tạo Order FK tới Customer inactive; test LAZY, EAGER, fetch join theo version Hibernate cụ thể.
11. Dùng PostgreSQL EXPLAIN so sánh composite index và partial index trên active rows.
12. Thiết kế quy trình admin restore với authorization, audit và xử lý unique conflicts.

## 55. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Muốn lọc dữ liệu khi ORM đọc"] --> B{"Điều kiện có cố định không?"}
    B -- "Không" --> C["@Filter / JPQL parameter / tenant policy"]
    B -- "Có" --> D{"Predicate thuộc bảng nào?"}
    D -- "Entity table" --> E["@SQLRestriction trên entity"]
    D -- "Một association collection" --> F["@SQLRestriction trên collection"]
    D -- "Many-to-many join table" --> G["@SQLJoinTableRestriction"]
    E --> H{"Có cần soft-delete mutation?"}
    F --> H
    G --> H
    H -- "Có" --> I["@SoftDelete 6.4+ hoặc @SQLDelete custom"]
    H -- "Không" --> J["Static loaded-view rule"]
    I --> K["Test SQL, native/bulk/cache/restore"]
    J --> K
    C --> K
    K --> L["Authorization và DB policy nếu dữ liệu nhạy cảm"]
~~~

## 56. Tài liệu đối chiếu chính thức

- [Hibernate ORM 6.6 — SQLRestriction Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/SQLRestriction.html) — điều kiện cho entities/collections, always applied, không disable và không parameterize.
- [Hibernate ORM 6.3 — SQLJoinTableRestriction Javadoc](https://docs.hibernate.org/orm/6.3/javadocs/org/hibernate/annotations/SQLJoinTableRestriction.html) — predicate trên join table khác target entity table.
- [Hibernate ORM 6.3 — Where Javadoc](https://docs.hibernate.org/orm/6.3/javadocs/org/hibernate/annotations/Where.html) — `@Where` bị deprecated từ 6.3, thay bằng SQLRestriction.
- [Hibernate User Guide — Filtering entities and associations](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html) — class-level/association-level restrictions, Filter/FilterJoinTable.
- [Hibernate User Guide — Soft Delete](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html) — built-in SoftDelete từ 6.4, strategies và collections.

Online documentation có thể mô tả một Hibernate version mới hơn ứng dụng hiện tại. Những nơi phụ thuộc version như to-one association loading, bulk mutation và soft delete cần được xác nhận bằng tests trên đúng major/minor đang sử dụng.

## 57. Tổng kết

**`@SQLRestriction`** là một **predicate native SQL tĩnh** gắn với entity hoặc collection mapping. Hibernate đưa predicate vào SQL reads thuộc phạm vi đó; không có runtime parameter và không thể tắt như Filter.

Bốn ranh giới cần nắm:

1. **Entity vs collection:** Restriction trên entity mô tả loaded visibility của loại entity đó; trên association mô tả loaded view của collection cụ thể.
2. **Entity table vs join table:** SQLRestriction áp dụng predicate cho entity/collection rows, còn SQLJoinTableRestriction nhắm association join table.
3. **Đọc vs ghi:** SQLRestriction không tự chuyển DELETE thành UPDATE. Muốn soft delete, dùng SQLDelete cấu hình đúng hoặc built-in SoftDelete 6.4+.
4. **ORM visibility vs security:** Native SQL, bulk DML, JDBC, caching, tenant isolation và database authorization có phạm vi riêng.

Hãy xác định **predicate cố định hay động, nhắm bảng nào, có cần mutation soft-delete không**, sau đó kiểm tra SQL/HQL, entity/find/association paths và cache trên đúng Hibernate version. Cách dùng `@SQLRestriction` tốt nhất là hiểu rõ **điều nó đảm bảo và những việc vẫn phải thiết kế ngoài annotation**.
