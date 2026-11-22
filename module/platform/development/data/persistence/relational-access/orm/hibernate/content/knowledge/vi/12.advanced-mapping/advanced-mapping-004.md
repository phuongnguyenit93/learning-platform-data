# `@Immutable` cho thực thể hoặc tập hợp và giới hạn bảo đảm

Trong Hibernate ORM, `@Immutable` là một annotation riêng của Hibernate dùng để khai báo rằng một đối tượng được ánh xạ **không nên được cập nhật qua cơ chế quản lý trạng thái tương ứng**. Nó thường xuất hiện ở những entity biểu diễn dữ liệu tham chiếu, bản ghi lịch sử không chỉnh sửa, báo cáo đọc từ SQL view, hoặc collection có thành viên cố định sau khi khởi tạo.

Điểm quan trọng nhất là **`@Immutable` có hành vi khác nhau tùy vị trí đặt annotation**:

- **Trên entity:** thay đổi thuộc tính của entity managed trong bộ nhớ thường **bị Hibernate bỏ qua khi đồng bộ**, không phát `UPDATE` và **không tự ném lỗi** chỉ vì sửa field đó.
- **Trên collection:** nếu thêm hoặc gỡ phần tử khỏi collection persistent được đánh dấu immutable, Hibernate **phát hiện thay đổi và ném `HibernateException`**.
- **Trên thuộc tính cơ bản:** Hibernate có thể bỏ qua thay đổi của riêng thuộc tính đó trong dirty checking.
- **Trên kiểu/converter:** annotation có thể diễn đạt đặc tính bất biến của **giá trị Java**, phục vụ cơ chế sao chép và kiểm tra thay đổi, không đồng nghĩa mọi entity dùng kiểu đó đều read-only.

`@Immutable` **không phải constraint của database, không làm đối tượng Java bất biến, không phải cơ chế phân quyền và không thay thế quy tắc nghiệp vụ**. Bài học giải thích cách dùng, những gì annotation bảo đảm và những lỗ hổng cần bảo vệ ở các tầng khác.

## 1. Cần phân biệt nhiều nghĩa của “bất biến”

Trong ứng dụng có Hibernate, từ *immutable* có thể nói tới bốn thứ khác nhau:

| Khái niệm | Câu hỏi đặt ra | Ví dụ |
| --- | --- | --- |
| **Java object immutable** | Code có thể đổi trạng thái object sau khi tạo không? | `String`, value object không setter, `record` trong nhiều tình huống |
| **ORM immutable mapping** | Hibernate có theo dõi và ghi thay đổi vào database qua entity/collection mapping không? | `org.hibernate.annotations.Immutable` |
| **Database read-only** | Một SQL `UPDATE`/`DELETE` có được database cho phép không? | View không thể update, quyền chỉ đọc, trigger chặn |
| **Business immutable rule** | Nghiệp vụ có cho phép đổi/xóa dữ liệu ở một thời điểm không? | Hóa đơn đã phát hành không được chỉnh sửa |

Một entity có thể khai báo `@Immutable` nhưng vẫn có public setter; setter vẫn gán giá trị vào object Java. Ngược lại, class Java không có setter chưa chắc dữ liệu ở database được bảo vệ khỏi SQL do công cụ khác gửi.

### 1.1. Phạm vi tác động

```text
                          ỨNG DỤNG JAVA
                         ┌─────────────────────┐
                         │ Entity / Collection │
                         │ @Immutable          │
                         └──────────┬──────────┘
                                    │
                     Hibernate Session / EntityManager
                     ├─ dirty checking
                     ├─ flush và SQL scheduling
                     └─ collection synchronization
                                    │
                       JDBC / SQL thực thi
                                    │
                         DATABASE / TABLE
                         ├─ quyền tài khoản
                         ├─ PK/FK/CHECK/trigger
                         └─ transaction / audit
```

`@Immutable` chủ yếu tác động ở **tầng Hibernate mapping và persistence context**. Lệnh SQL trực tiếp hoặc một ứng dụng khác kết nối tới database có thể đi vòng qua tầng này.

## 2. Khai báo đúng annotation

Import:

```java
import org.hibernate.annotations.Immutable;
```

Đây là **annotation đặc thù Hibernate**, không phải `jakarta.persistence.Immutable`. Các annotation `@Entity`, `@Id`, `@ElementCollection`, `@OneToMany` vẫn thuộc `jakarta.persistence.*` trong các phiên bản Jakarta Persistence hiện đại.

Có thể đặt `@Immutable` trên:

```java
// Entity
@Entity
@Immutable
class LookupValue {
    // ...
}

// Collection của entity
@ElementCollection
@Immutable
private Set<String> labels;

// Thuộc tính đơn
@Immutable
private String sourceSystem;
```

Trong tài liệu và Javadoc Hibernate, ý nghĩa của annotation thay đổi theo loại target. Không nên viết một helper/qui ước suy luận rằng **mọi nơi dùng `@Immutable` sẽ cùng ném lỗi khi bị sửa**.

Đặc biệt, `@Immutable` ở entity và `@Immutable` ở collection có cơ chế báo lỗi **khác nhau**.

## 3. `@Immutable` trên entity: thay đổi state bị bỏ qua

Ví dụ một entity lưu sự kiện lịch sử:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Immutable;

import java.time.Instant;
import java.util.Objects;

@Entity
@Immutable
@Table(name = "audit_events")
public class AuditEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "event_type", nullable = false, length = 80)
    private String eventType;

    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    @Column(name = "message", nullable = false, length = 500)
    private String message;

    protected AuditEvent() {
        // Constructor cho Jakarta Persistence.
    }

    public AuditEvent(String eventType, Instant occurredAt, String message) {
        this.eventType = Objects.requireNonNull(eventType);
        this.occurredAt = Objects.requireNonNull(occurredAt);
        this.message = Objects.requireNonNull(message);
    }

    public Long getId() {
        return id;
    }

    public String getMessage() {
        return message;
    }

    // Cố tình để một method thay đổi để thấy giới hạn của @Immutable.
    public void changeMessageInMemory(String newMessage) {
        this.message = Objects.requireNonNull(newMessage);
    }
}
```

Giả sử hàng sau đã tồn tại:

```sql
INSERT INTO audit_events(id, event_type, occurred_at, message)
VALUES (10, 'LOGIN', CURRENT_TIMESTAMP, 'User logged in');
```

Đọc và sửa trong transaction:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    AuditEvent event = em.find(AuditEvent.class, 10L);
    event.changeMessageInMemory("Changed in memory");

    System.out.println(event.getMessage());
    // "Changed in memory"

    em.flush();
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Với entity `@Immutable`, Hibernate **không lập `UPDATE` chỉ vì thay đổi `message` ở managed instance**. Vì vậy:

```text
Trong object Java (cùng persistence context):
    event.getMessage() == "Changed in memory"

Trong hàng database sau transaction:
    message == "User logged in"
```

Đây là **hành vi cần lưu ý**, không phải cách để bảo vệ ứng dụng khỏi code gọi setter. Entity đã bị biến đổi trong bộ nhớ dù dữ liệu database không đổi. Hibernate không tự khôi phục lại giá trị cũ ngay sau `flush()`.

### 3.1. “Không throw” khác “cấm chỉnh sửa”

`@Immutable` trên entity có thể tạo ra một lỗi logic khó nhìn thấy:

```java
AuditEvent event = em.find(AuditEvent.class, 10L);
event.changeMessageInMemory("Approved");

// Ứng dụng tưởng update thành công vì không có exception.
// Các request khác vẫn đọc "User logged in" từ database.
```

Nếu nghiệp vụ cần **báo lỗi ngay khi cố sửa**, phải thiết kế domain API không cho sửa, hoặc đặt validation/authorization rõ ràng. `@Immutable` không thay thế việc kiểm soát thao tác trong service.

### 3.2. Vì sao Hibernate có thể tối ưu hiệu năng?

Đối với entity thông thường, persistence context giữ thông tin về trạng thái đã tải để so sánh với trạng thái hiện tại khi flush (**dirty checking**). Đối với entity immutable:

- Hibernate không cần thực hiện dirty checking thuộc tính cơ bản như entity mutable.
- Hibernate không cần giữ toàn bộ snapshot loaded-state cho cùng mục đích đó.
- Với nhiều entity chỉ đọc được tải trong cùng persistence context, điều này có thể giảm bộ nhớ và chi phí flush.

Đây là tối ưu **có điều kiện**, phụ thuộc số entity và workload. Không thể suy ra rằng thêm `@Immutable` sẽ giảm một tỷ lệ thời gian cố định, tăng tốc SQL SELECT hay làm database không còn phải đọc dữ liệu.

## 4. Persist mới và remove entity immutable

`@Immutable` **không đồng nghĩa với chỉ cho phép `SELECT`**. Theo semantics ORM, entity immutable có thể được tạo mới và xóa qua lifecycle khi mapping, database và các quy tắc khác cho phép; điều bị vô hiệu hóa là cơ chế **UPDATE state của entity managed**.

Ví dụ:

```java
AuditEvent event = new AuditEvent(
    "PAYMENT_RECEIVED",
    Instant.now(),
    "Payment was received"
);

em.persist(event); // Có thể INSERT entity mới.
```

Nếu cần lịch sử audit **chỉ thêm, không được xóa**, `@Immutable` **chưa đủ**. Cần thiết kế phương thức repository/service, quyền truy cập DB, FK, retention policy và audit trail riêng. `EntityManager.remove(event)` không bị `@Immutable` biến thành thao tác không thể thực hiện trong mọi hoàn cảnh.

Phân biệt:

| Thao tác | Entity `@Immutable` |
| --- | --- |
| `new` + `persist()` | Có thể INSERT nếu entity mới và DB cho phép |
| `find()` / query | Đọc entity bình thường |
| Gán lại field managed + `flush()` | Thay đổi state entity thường bị bỏ qua, không UPDATE |
| `remove(managedEntity)` | Có thể DELETE theo lifecycle và constraints |
| `refresh()` | Có thể tải lại trạng thái DB theo ngữ nghĩa API |
| Native SQL từ ứng dụng khác | Annotation không ngăn được |

Những ngoại lệ phát sinh do constraint/transaction/driver không phải bằng chứng `@Immutable` bảo vệ quyền truy cập.

## 5. Entity immutable có được dùng public setter không?

Hibernate không bắt buộc class phải không có setter khi entity được khai báo `@Immutable`. Tuy nhiên từ góc nhìn thiết kế domain, nếu state thật sự không được phép sửa, nên hạn chế API:

```java
@Entity
@Immutable
public class CountryCode {

    @Id
    private String code;

    @Column(nullable = false)
    private String displayName;

    protected CountryCode() {
    }

    public CountryCode(String code, String displayName) {
        this.code = code;
        this.displayName = displayName;
    }

    public String getCode() {
        return code;
    }

    public String getDisplayName() {
        return displayName;
    }

    // Không có setter sửa code hoặc displayName.
}
```

Các object được Hibernate load vẫn là object Java; reflection, một framework khác hoặc method mới vô tình được thêm vẫn có thể thay state của object. Vì vậy **ngăn từ API** giúp người phát triển nhìn thấy ý định domain, còn **ngăn ở DB** bảo vệ dữ liệu trước các lối ghi ngoài ORM.

### 5.1. Có nên dùng `final`?

Không cần biến toàn bộ class/field thành `final` để dùng `@Immutable`. Theo quy tắc entity portable của Jakarta Persistence, lớp entity thông thường không nên là `final` và các persistent field không nên là `final`; Hibernate proxy/lazy loading cũng có những hạn chế với các class hoặc method `final`.

Nếu muốn một **value object Java bất biến hoàn toàn**, có thể dùng kiểu giá trị riêng ở tầng domain và mapping qua `@Embeddable`, converter hoặc giải pháp được ORM hỗ trợ. Đừng nhầm `@Immutable` với cơ chế tạo `record`/immutable object theo ngôn ngữ Java.

## 6. Entity immutable trong inheritance hierarchy

Hibernate Javadoc quy định khi một entity thuộc **một hệ phân cấp kế thừa có mapping**, `@Immutable` phải đặt trên **root entity** của hệ đó và có hiệu lực cho các subtype.

Ví dụ:

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@Immutable
public abstract class HistoricalRecord {
    @Id
    private Long id;
}

@Entity
public class HistoricalLogin extends HistoricalRecord {
    private String loginDevice;
}
```

Với thiết kế này, các entity trong hierarchy được xem immutable theo khai báo trên root. Nếu chỉ muốn một số thuộc tính của subtype không cập nhật, có thể xem xét `@Immutable` trên các thuộc tính tương ứng; **không tùy ý đặt `@Immutable` trên một subclass để hy vọng thay riêng mutability của subclass**.

Hệ thống hiện có cần xem inheritance mapping và chính sách update thực tế trước khi áp dụng annotation ở root, vì nó có thể vô hiệu hóa update của **tất cả subtype**.

## 7. `@Immutable` trên collection: thêm/xóa phần tử gây lỗi

Đây là điểm khác biệt quan trọng nhất so với entity.

Ví dụ owner có một tập quyền được ấn định khi tạo:

```java
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;
import org.hibernate.annotations.Immutable;

import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

@Entity
@Table(name = "policy_snapshots")
public class PolicySnapshot {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "policy_name", nullable = false)
    private String policyName;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "policy_snapshot_permissions",
        joinColumns = @JoinColumn(name = "snapshot_id")
    )
    @Column(name = "permission_code", nullable = false)
    @Immutable
    private Set<String> permissions = new HashSet<>();

    protected PolicySnapshot() {
    }

    public PolicySnapshot(String policyName, Set<String> permissions) {
        this.policyName = Objects.requireNonNull(policyName);
        this.permissions.addAll(Objects.requireNonNull(permissions));
    }

    public Long getId() {
        return id;
    }

    public Set<String> getPermissions() {
        return java.util.Collections.unmodifiableSet(permissions);
    }
}
```

Các quyền được đặt lúc tạo snapshot, sau đó collection không được thay đổi qua Hibernate. Quan hệ trong database:

```sql
CREATE TABLE policy_snapshots (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    policy_name VARCHAR(255) NOT NULL
);

CREATE TABLE policy_snapshot_permissions (
    snapshot_id BIGINT NOT NULL,
    permission_code VARCHAR(255) NOT NULL,
    PRIMARY KEY (snapshot_id, permission_code),
    FOREIGN KEY (snapshot_id) REFERENCES policy_snapshots(id)
);
```

Đây là DDL minh họa; tên constraint và cú pháp identity có thể khác theo database.

### 7.1. Khởi tạo collection khi entity mới

```java
PolicySnapshot snapshot = new PolicySnapshot(
    "policy-v1",
    Set.of("READ", "EXPORT")
);

em.persist(snapshot); // Lưu owner và các phần tử ban đầu.
```

Annotation `@Immutable` **không ngăn việc tạo nội dung ban đầu của một entity mới**. Dữ liệu có thể được insert khi snapshot được persist, sau đó Hibernate coi tập hợp đã persistent là bất biến.

### 7.2. Sửa collection persistent

Giả sử đã có snapshot ID 10:

```java
PolicySnapshot snapshot = em.find(PolicySnapshot.class, 10L);

// Ví dụ này giả định ứng dụng có quyền truy cập mutable collection,
// hoặc entity cung cấp method sửa bên trong:
snapshot.getMutablePermissionsForExample().add("ADMIN");

em.flush(); // Hibernate có thể ném HibernateException
```

`getMutablePermissionsForExample()` **không được cung cấp** trong class an toàn phía trên; đoạn này chỉ minh họa một thao tác nếu API cho phép sửa. Trong thiết kế domain thực, getter trả unmodifiable view và không có mutation method để chặn lỗi sớm.

Nếu Hibernate phát hiện add/remove phần tử của collection persistent được đánh dấu `@Immutable`, một **`HibernateException`** có thể xuất hiện lúc flush/commit (hoặc tại thời điểm provider xử lý mutation). **Không nên dựa vào thời điểm exception cố định** chỉ từ `Set.add()`.

### 7.3. Vì sao entity và collection có hành vi khác?

| Đặt `@Immutable` ở đâu? | Ứng dụng gán/sửa state | Hành vi Hibernate |
| --- | --- | --- |
| `@Entity @Immutable` | `entity.setName("new")` | Thường **bỏ qua** thay đổi khi flush, không ném lỗi chỉ vì setter |
| `@ElementCollection @Immutable` | `tags.add("new")` | Phát hiện đổi thành viên, **ném `HibernateException`** |
| `@OneToMany @Immutable` | `children.remove(child)` | Thay đổi membership của collection bị coi không hợp lệ |
| `@ManyToMany @Immutable` | `roles.add(role)` | Thay đổi membership bị coi không hợp lệ |
| `@Basic @Immutable` | `entity.setSource("new")` | Bỏ qua update của riêng thuộc tính được đánh dấu |

Điểm cần nhớ: **không thể áp dụng cùng một kết luận “im lặng bỏ qua” cho collection**.

## 8. `@Immutable` với `@ElementCollection`, `@OneToMany` và `@ManyToMany`

Hibernate cho phép đánh dấu **plural attribute** bất biến trong các kiểu collection mapping thông thường.

### 8.1. `@ElementCollection`

```java
@ElementCollection
@CollectionTable(
    name = "report_labels",
    joinColumns = @JoinColumn(name = "report_id")
)
@Column(name = "label")
@Immutable
private Set<String> labels = new HashSet<>();
```

Mỗi phần tử là **value** như `String`, không có entity ID riêng. Sau khi collection persistent, thêm hoặc xóa một label sẽ bị Hibernate xử lý như thay đổi collection immutable.

### 8.2. `@OneToMany`

```java
@OneToMany(mappedBy = "catalog", fetch = FetchType.LAZY)
@Immutable
private List<CatalogItem> items = new ArrayList<>();
```

Collection `items` có thành viên cố định theo mapping. Tuy nhiên, `CatalogItem` vẫn là **entity riêng**. Đánh dấu collection immutable **không tự biến mọi `CatalogItem` thành entity immutable**.

Ví dụ:

```java
CatalogItem item = entityManager.find(CatalogItem.class, itemId);
item.rename("Tên mới");  // Có thể UPDATE CatalogItem nếu entity đó vẫn mutable.
```

Điều bị hạn chế là **thay đổi quan hệ membership** qua collection. Nếu các entity con cũng phải read-only, cần chính sách immutable riêng trên lớp con hoặc ràng buộc nghiệp vụ/database.

### 8.3. `@ManyToMany`

```java
@ManyToMany(fetch = FetchType.LAZY)
@JoinTable(
    name = "published_article_topics",
    joinColumns = @JoinColumn(name = "article_id"),
    inverseJoinColumns = @JoinColumn(name = "topic_id")
)
@Immutable
private Set<Topic> topics = new HashSet<>();
```

Một `Topic` có thể được nhiều article tham chiếu; annotation ở `Article.topics` đánh dấu **association collection** của article bất biến. Nó không có nghĩa:

- Bảng `topics` hoàn toàn bị khóa update.
- Thuộc tính `Topic.name` không thể đổi.
- Mọi association tới `Topic` trong toàn hệ thống đều immutable.
- Mọi SQL vào join table đều bị database ngăn.

Nếu cần danh sách topic bất biến cho một bản phát hành, hãy lưu quyền sở hữu, thời điểm publish và các ràng buộc cần thiết ở tầng domain/database.

## 9. Entity immutable có làm collection bên trong tự immutable không?

**Không nên suy luận như vậy.** Theo Hibernate, trạng thái scalar của entity và trạng thái association/collection là các cơ chế theo dõi riêng.

Ví dụ:

```java
@Entity
@Immutable
public class ProductCatalog {
    @Id
    private Long id;

    @OneToMany(mappedBy = "catalog")
    private Set<CatalogItem> items = new HashSet<>();
}
```

`@Immutable` trên `ProductCatalog` nói rằng **state entity** không được update theo dirty checking bình thường. Nó không nhất thiết biến `items` thành collection được đánh dấu `@Immutable`, và cũng không ngăn mọi thay đổi trên entity `CatalogItem`.

Nếu cả **membership** lẫn **state của các con** phải bất biến, cần thể hiện rõ:

```java
@Entity
@Immutable
public class ProductCatalog {
    @Id
    private Long id;

    @OneToMany(mappedBy = "catalog")
    @Immutable
    private Set<CatalogItem> items = new HashSet<>();
}

@Entity
@Immutable
public class CatalogItem {
    @Id
    private Long id;

    private String title;

    // Quan hệ owning side cần map phù hợp.
}
```

Đây là **ví dụ cấu trúc rút gọn**, không phải hai entity hoàn chỉnh. Đặc biệt với quan hệ hai chiều, phía owning `@ManyToOne` của con quyết định FK. Nếu cần bất biến thật sự ở mức database, phải bảo vệ cả **đường ghi thông qua phía con**; chỉ đánh dấu collection ở inverse side có thể không đủ.

## 10. Bất biến collection là bất biến membership hay toàn bộ object graph?

Hãy tách các tình huống:

```text
@Immutable trên Set<Permission>
    ├─ Set.add(permission)        → cố đổi membership
    ├─ Set.remove(permission)     → cố đổi membership
    └─ permission.setDescription  → cố đổi state của entity Permission
```

Hai dòng đầu thay đổi **collection**. Dòng cuối chỉ đổi state của một entity phần tử. Nếu `Permission` là entity mutable, Hibernate có thể UPDATE nó bình thường. Ngược lại, `@Immutable` trên entity `Permission` không tự ngăn `Set.add/remove` ở một collection được map mutable.

Tương tự đối với `@ElementCollection` của embeddable, sửa trực tiếp field bên trong phần tử có thể được provider xem như thay đổi nội dung collection hoặc state của value, tùy cách dirty checking và mapping. Để bảo đảm quy tắc “snapshot không thay đổi”, nên dùng **value objects không công khai setter**, tránh chỉnh sửa phần tử tại chỗ và bảo vệ ở database nếu dữ liệu thật sự cần chỉ đọc.

Một quy tắc hữu ích:

> Muốn khóa danh sách thành viên thì đánh dấu **collection**; muốn khóa state của từng entity thì đánh dấu **entity**; muốn mọi con đường ghi đều bị cấm thì cần thêm **ràng buộc/phân quyền ở database và chính sách nghiệp vụ**.

## 11. `@Immutable` không phải `Collections.unmodifiableSet`

Trong Java, getter có thể trả một view chỉ đọc:

```java
public Set<String> getPermissions() {
    return Collections.unmodifiableSet(permissions);
}
```

Khi code gọi:

```java
snapshot.getPermissions().add("ADMIN");
```

Java sẽ ném `UnsupportedOperationException` **ngay tại lời gọi add**, vì view không cho sửa.

Với `@Immutable` của Hibernate:

```java
@ElementCollection
@Immutable
private Set<String> permissions = new HashSet<>();
```

nếu ứng dụng có một method thực sự làm:

```java
permissions.add("ADMIN");
```

thì lỗi Hibernate có thể chỉ xuất hiện khi flush hoặc khi provider xử lý thay đổi persistent collection.

Hai cơ chế bổ sung cho nhau:

| Cơ chế | Tầng thực thi | Khi nào có thể báo lỗi |
| --- | --- | --- |
| `Collections.unmodifiableSet()` | Java API | Ngay khi gọi sửa qua view |
| Không public setter/mutation method | Domain API | Chặn cách sửa thông thường từ bên ngoài |
| `@Immutable` trên collection | Hibernate ORM | Khi Hibernate phát hiện membership bị sửa |
| DB trigger/permission/constraint | Database | Khi SQL trái quy tắc được thực thi |

Không có cơ chế đơn lẻ nào đủ cho mọi yêu cầu bất biến.

## 12. Khác biệt với `@Column(updatable = false)`

Một thuộc tính entity có thể được map:

```java
@Column(name = "created_at", updatable = false, nullable = false)
private Instant createdAt;
```

`updatable = false` thuộc Jakarta Persistence, chỉ báo cho provider rằng **cột không được đưa vào SQL UPDATE do provider sinh**. Nó không bảo đảm:

- Không được sửa field Java.
- Một câu native SQL không thể update cột.
- Database sẽ từ chối UPDATE.
- Cả entity trở thành immutable.

So sánh:

| Cấu hình | Phạm vi | Mục tiêu |
| --- | --- | --- |
| `@Immutable` trên entity | State của toàn entity | Hibernate bỏ qua cập nhật state theo dirty checking |
| `@Immutable` trên collection | Thành viên của collection | Hibernate từ chối thay đổi membership |
| `@Immutable` trên basic attribute | Thuộc tính cụ thể | Hibernate bỏ qua thay đổi thuộc tính đó |
| `@Column(updatable=false)` | Một cột mapped | Loại cột khỏi SQL UPDATE sinh bởi JPA provider |
| `@NaturalId(mutable=false)` | Natural ID của entity | Khai báo natural ID không thay đổi |
| `@Version` | Cạnh tranh cập nhật | Phát hiện một số xung đột optimistic locking |

Khi chỉ có `createdAt` cần giữ nguyên còn các field khác cần update, dùng `@Column(updatable=false)` hoặc API/domain rule thích hợp thường hợp lý hơn đánh dấu **toàn entity** immutable.

### 12.1. `@NaturalId(mutable = false)` có thay `@Immutable` không?

Không. `@NaturalId` biểu diễn khóa nghiệp vụ như `isbn` hoặc `code` và cho Hibernate cơ chế natural-id lookup/caching. `mutable=false` là cam kết rằng natural ID không đổi, chứ không có nghĩa toàn bộ entity không được update.

Ví dụ sách có ISBN không đổi nhưng giá hoặc tiêu đề có thể cập nhật:

```java
@NaturalId(mutable = false)
@Column(nullable = false, unique = true)
private String isbn;

private String title;
private BigDecimal price;
```

Đặt `@Immutable` lên toàn bộ `Book` sẽ chặn cập nhật cả `title` và `price` qua dirty checking, trái với nhu cầu này.

## 13. `Session` read-only và query read-only khác annotation

Hibernate có các API đặt read-only cho **instance hoặc truy vấn trong một session cụ thể**, ví dụ:

```java
org.hibernate.Session session = em.unwrap(org.hibernate.Session.class);

session.setDefaultReadOnly(true);

AuditEvent event = session.find(AuditEvent.class, eventId);
```

Hoặc:

```java
session.setReadOnly(event, true);
```

Tùy phiên bản Hibernate, còn có:

```java
session.createQuery(
        "from AuditEvent e where e.eventType = :type",
        AuditEvent.class
    )
    .setParameter("type", "LOGIN")
    .setReadOnly(true)
    .getResultList();
```

Khác nhau:

- **`@Immutable` trên entity class:** quy tắc tĩnh của entity mapping; mọi session dùng mapping đó biết đây là entity immutable.
- **`Session.setDefaultReadOnly(true)`:** thay mặc định cho các entity được load **sau khi** cấu hình cờ trong session; không biến class thành immutable toàn cục.
- **`Session.setReadOnly(entity, true)`:** đánh dấu **instance cụ thể** trong session; có thể dùng khi cùng entity type vừa cần đọc vừa cần chỉnh ở các luồng khác nhau.
- **`Query.setReadOnly(true)`:** yêu cầu các entity trả về được quản lý theo chế độ read-only trong scope query, theo API Hibernate.

Đừng hiểu `setDefaultReadOnly(true)` như một “DB read-only transaction”: nó chủ yếu điều khiển cách Hibernate theo dõi state entity được load. Các thao tác khác như native SQL, collection mutation, explicit remove hoặc persist có semantics riêng.

### 13.1. Spring `@Transactional(readOnly = true)` có phải `@Immutable`?

Không. Trong Spring, `@Transactional(readOnly = true)` là thuộc tính của **transaction**, có thể ảnh hưởng tới flush mode, read-only hints và tích hợp ORM tùy phiên bản/configuration.

```java
@Transactional(readOnly = true)
public List<AuditEvent> listEvents() {
    return repository.findAll();
}
```

Điều này khác với:

```java
@Entity
@Immutable
public class AuditEvent {
    // ...
}
```

Không nên giả định Spring chỉ cần `readOnly=true` là database chắc chắn chặn mọi DML. Việc transaction, connection, SQL driver và database thực sự có bảo vệ read-only hay không phụ thuộc transaction manager và hệ quản trị.

Nếu muốn **loại entity khỏi đường cập nhật thông thường trên mọi session Hibernate**, annotation mapping rõ ràng hơn một hint theo transaction. Nếu muốn **một giao dịch đọc dữ liệu hiệu quả**, read-only transaction/query có thể là tối ưu bổ sung nhưng không thay constraint domain/database.

## 14. Bulk HQL/JPQL UPDATE/DELETE: điểm thay đổi quan trọng từ Hibernate 7

`@Immutable` trên entity được thiết kế chủ yếu cho dirty checking của **managed instances**. Bulk HQL/JPQL mutation là một con đường khác: statement được gửi tới database để ảnh hưởng hàng loạt record, **không đi qua set field trên từng entity đang managed**.

Ví dụ:

```java
int count = em.createQuery(
    "update AuditEvent e " +
    "set e.message = :message " +
    "where e.eventType = :type"
)
.setParameter("message", "rewritten")
.setParameter("type", "LOGIN")
.executeUpdate();
```

**Hành vi phụ thuộc phiên bản Hibernate.** Đây là khác biệt có thể ảnh hưởng trực tiếp đến độ an toàn khi nâng cấp:

| Phiên bản Hibernate | Hành vi mặc định được tài liệu mô tả đối với bulk mutation trên immutable entity |
| --- | --- |
| **Hibernate 6.x đời trước 7.0** | Với nhiều phiên bản, cảnh báo khi query update ảnh hưởng immutable entity, nhưng bulk query vẫn có thể thực thi. Kiểm tra patch/setting thực tế. |
| **Hibernate 7.0 trở lên** | Theo migration guide, mặc định **báo exception** đối với bulk update và delete queries nhắm vào immutable entity. |
| **Hibernate 7 với cấu hình cho phép** | Có thể bật lại việc cho phép bulk mutation thông qua setting `hibernate.query.immutable_entity_update_query_handling_mode=allow`. |

Hibernate 7.0 Migration Guide ghi rõ thay đổi default này. Nếu phải chấp nhận mutation có chủ đích cho một luồng quản trị, cấu hình minh họa:

```properties
hibernate.query.immutable_entity_update_query_handling_mode=allow
```

Nhưng thiết lập này **nới lỏng hành vi bảo vệ mặc định**. Không nên dùng nó như cách sửa nhanh một query đang cố cập nhật dữ liệu “đáng lẽ bất biến”; cần đánh giá nghiệp vụ và đặt API quản trị riêng, với authorization/audit và schema phù hợp.

### 14.1. Native SQL vẫn có thể bỏ qua `@Immutable`

Ví dụ:

```java
em.createNativeQuery(
    "update audit_events set message = :message where id = :id"
)
.setParameter("message", "changed via SQL")
.setParameter("id", 10L)
.executeUpdate();
```

Câu SQL này không biến thành phép set property trên immutable entity. Nếu database account có quyền UPDATE và schema cho phép, **Hibernate annotation không phải hàng rào bảo mật chắc chắn trước native SQL**.

Tương tự, JDBC trực tiếp, migration tool, SQL console, procedure, trigger hay hệ thống ETL đều có thể thay dữ liệu theo quyền database.

### 14.2. Persistence context và cache có thể bị cũ

Một bulk SQL/JPQL mutation hoặc cập nhật từ ứng dụng khác có thể thay hàng database trong khi `EntityManager` vẫn giữ instance loaded cũ:

```text
Session A đã load AuditEvent(id=10, message="original")
Session B hoặc native SQL đổi DB message thành "new"
Session A vẫn có object AuditEvent message="original"
```

`@Immutable` không buộc Hibernate reload tất cả immutable entity sau mỗi external UPDATE. Nếu thay đổi dữ liệu ngoài Hibernate, cân nhắc `refresh()`, `clear()`, đóng session, và cơ chế invalidation second-level cache phù hợp.

**Immutability và caching là hai vấn đề khác nhau**. Gắn `@Immutable` không đảm bảo dữ liệu bất biến ở nguồn và không tự làm cache luôn đồng bộ với sửa đổi ngoài ORM.

## 15. `@Immutable` với `@Subselect` và SQL view

Hibernate thường dùng `@Immutable` với **entity ánh xạ từ truy vấn chỉ đọc** hoặc view tổng hợp.

Ví dụ dashboard tổng chi tiêu theo khách hàng:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.annotations.Immutable;
import org.hibernate.annotations.Subselect;
import org.hibernate.annotations.Synchronize;

import java.math.BigDecimal;

@Entity
@Immutable
@Subselect("""
    select
        o.customer_id as customer_id,
        count(*) as order_count,
        sum(o.total_amount) as total_amount
    from orders o
    group by o.customer_id
    """)
@Synchronize("orders")
public class CustomerOrderSummary {

    @Id
    @Column(name = "customer_id")
    private Long customerId;

    @Column(name = "order_count")
    private Long orderCount;

    @Column(name = "total_amount")
    private BigDecimal totalAmount;

    protected CustomerOrderSummary() {
    }

    public Long getCustomerId() {
        return customerId;
    }

    public Long getOrderCount() {
        return orderCount;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

Giả định `orders` có các cột `customer_id`, `total_amount` và mỗi `customer_id` xuất hiện tối đa một hàng trong kết quả `GROUP BY`. `@Id` là cần thiết vì đây vẫn là **entity mapping** và mỗi hàng kết quả phải có định danh duy nhất. Với kết quả tổng hợp không có khóa duy nhất, phải thiết kế lại projection/ID trước khi dùng entity.

Ý nghĩa:

- `@Subselect` cung cấp câu SELECT dùng làm nguồn mapping entity.
- `@Immutable` nói entity tổng hợp không được UPDATE theo dirty checking bình thường.
- `@Synchronize("orders")` giúp Hibernate biết những bảng liên quan để cân nhắc flush các thay đổi đang chờ trước khi truy vấn dạng subselect. Nó không biến kết quả thành live object luôn tự refresh.

Đây là **một pattern Hibernate-specific**, không phải mapping JPQL/Jakarta Persistence portable cho mọi provider.

### 15.1. Vì sao `@Immutable` chưa đủ cho view?

Một SQL view có thể được DBMS cho phép update hay không tùy loại view và quy tắc database. `@Immutable` ngăn cập nhật tự động qua Hibernate entity state, **không tạo quyền `SELECT`-only trên view**.

Nếu hệ thống bắt buộc chỉ đọc, hãy xét:

- Database role chỉ có `SELECT` trên bảng/view liên quan.
- SQL view hoặc materialized view theo policy DBMS.
- Trigger/constraint chặn đường ghi không hợp lệ nếu cần.
- API và service không cung cấp mutation.
- Test xác nhận write attempts bị chặn ở đúng tầng.

### 15.2. Materialized view cần chiến lược refresh

Với materialized view, dữ liệu phản ánh snapshot ở một thời điểm và chỉ thay đổi khi database refresh. `@Immutable` trên entity Hibernate **không tự refresh materialized view** và không làm kết quả truy vấn luôn mới.

Khi refresh từ DB, cần thiết kế invalidation first-level/second-level cache nếu ứng dụng đã load dữ liệu cũ.

## 16. Read-only entity và `@Version` / optimistic locking

Một entity mutable có thể dùng:

```java
@Version
private long version;
```

để Hibernate kiểm tra xung đột khi UPDATE/DELETE theo cơ chế optimistic locking.

Với entity `@Immutable`, Hibernate **không dự kiến gửi UPDATE do dirty checking**, vì thế không thể xem `@Version` là một cơ chế bảo đảm rằng “mọi thay đổi trên entity immutable sẽ bị phát hiện và rollback”. Thay đổi scalar trong object có thể bị bỏ qua mà không có UPDATE nào để kiểm tra version.

Nếu nghiệp vụ cần **được phép sửa trong trạng thái DRAFT nhưng khóa sau khi PUBLISHED**, annotation `@Immutable` tĩnh trên class thường không phù hợp:

```text
DRAFT      → được sửa nội dung, có @Version
PUBLISHED  → cấm sửa nội dung, chỉ một số hành động nghiệp vụ được phép
```

Một số lựa chọn thiết kế:

1. Dùng entity mutable và kiểm tra trạng thái trong service/domain, kết hợp optimistic locking, SQL constraint/trigger nếu cần bảo vệ mạnh.
2. Tách entity **bản nháp mutable** và **bản phát hành snapshot immutable** có schema/vòng đời rõ ràng.
3. Chọn mô hình versioned records/append-only nếu phải giữ lịch sử bất biến.

`@Immutable` phù hợp hơn với loại entity **luôn** được xem là bất biến sau khi được persist/load theo mapping, không phải cờ trạng thái thay đổi tùy từng hàng nếu muốn Hibernate tự nhận biết và ném lỗi.

## 17. Giới hạn về bảo mật và toàn vẹn dữ liệu

`@Immutable` không đáp ứng một mình các yêu cầu như “không ai được chỉnh sửa bảng audit” hay “hóa đơn đã phát hành phải không thể xóa”. Những giới hạn thường gặp:

### 17.1. Ghi ngoài Hibernate

SQL console, JDBC thuần, ETL, migration, scheduled job hoặc một service khác có thể UPDATE bảng nếu DB cho phép.

### 17.2. Cùng database nhưng đường đi ORM khác

Native SQL, stored procedure hoặc bulk HQL/JPQL với cấu hình/version cho phép có thể thay dữ liệu mà không thông qua dirty checking entity immutable.

### 17.3. Xóa/insert vẫn có thể được phép

`@Immutable` không đồng nghĩa cấm `DELETE` và `INSERT` ở mọi API. Nếu audit trail phải append-only, cần giải pháp ở service/database.

### 17.4. Đối tượng Java vẫn có thể thay đổi

Public setter, reflection hoặc mutable nested value cho phép object đổi trong bộ nhớ. Code tiếp tục dùng object đó có thể thấy trạng thái **khác database**.

### 17.5. Collection bị chỉnh qua owning side khác

Với quan hệ hai chiều, annotation immutable trên collection inverse không nhất thiết tự bảo vệ mọi SQL cập nhật FK được phát sinh từ **entity con owning side**. Cần thiết kế mapping và quyền ghi trên các đường liên kết.

### 17.6. Cache có thể cũ sau external writes

Nếu database đổi mà Hibernate không biết, entity/collection trong persistence context và cache có thể tiếp tục trả snapshot cũ.

### 17.7. “Không đổi” có thể là quy tắc theo thời gian

Khi phải đóng băng một hóa đơn sau thời điểm phát hành nhưng trước đó cần sửa, áp `@Immutable` vào cùng entity class có thể làm mất khả năng cập nhật ở giai đoạn draft.

Cần quyết định **bất biến ở lớp nào và tại thời điểm nào**.

## 18. Thiết kế append-only cho lịch sử

Giả sử nghiệp vụ cần ghi nhật ký hệ thống mà không được sửa hoặc xóa:

```text
events
  id
  occurred_at
  event_type
  payload
```

`@Immutable` hữu ích để Hibernate không tự UPDATE event đã load. Nhưng thiết kế append-only mạnh hơn cần:

- API chỉ cho phép `appendEvent`, không công khai update/remove.
- Transaction tách biệt với đối tượng nghiệp vụ theo yêu cầu.
- Database role dành cho service chỉ có quyền phù hợp (có thể INSERT/SELECT, không UPDATE/DELETE).
- Chính sách retention, audit truy cập, quản lý tài khoản quản trị và sao lưu.
- Nếu cần chống sửa/xóa có tính chứng cứ, cân nhắc cơ chế log bất biến, chữ ký/hash chain hoặc lưu trữ WORM theo yêu cầu hệ thống.

**Một bảng chỉ được đánh dấu `@Immutable` trong Java chưa trở thành kho lưu chứng cứ chống giả mạo.**

### 18.1. Trường hợp có chính sách xóa dữ liệu

Một số hệ thống vẫn cần xóa dữ liệu vì retention hoặc nghĩa vụ pháp lý. Nếu áp cứng bất biến “vĩnh viễn” vào mọi tầng mà không có quy trình dữ liệu, có thể làm việc vận hành và tuân thủ khó khăn. Vì thế cần tách:

- Chỉnh sửa nội dung nghiệp vụ: có thể bị cấm sau khi ghi.
- Xóa theo chính sách retention: có thể được phép bởi quy trình được kiểm soát.
- Truy cập/quản trị: yêu cầu role và audit riêng.

Annotation ORM không thể tự giải quyết cả ba.

## 19. So sánh các công cụ trong một thiết kế

| Cơ chế | Scope | Ngăn update qua managed entity? | Ngăn direct SQL? | Có thể báo lỗi khi sửa? |
| --- | --- | --- | --- | --- |
| `@Immutable` trên entity | Type mapping | Có, bằng cách bỏ qua dirty check | Không | Thường không khi gán scalar |
| `@Immutable` trên collection | Plural attribute | Ngăn đồng bộ thay đổi membership | Không | `HibernateException` khi Hibernate xử lý mutation |
| `@Immutable` trên basic field | Một thuộc tính | Bỏ qua update của field đó | Không | Thường không khi gán |
| `@Column(updatable=false)` | Một cột | Không đưa cột vào generated UPDATE | Không | Thường không |
| Read-only session/query | Instance hoặc query scope | Có thể bỏ qua dirty check ở scope đã cấu hình | Không | Không phải cơ chế báo lỗi nghiệp vụ |
| `Collections.unmodifiableSet` | API Java | Chỉ ngăn sửa qua view; không tự điều khiển SQL | Không | `UnsupportedOperationException` ngay qua view |
| Không public mutation methods | Domain API | Giảm đường sửa từ code thông thường | Không | Tùy thiết kế |
| `@Version` | Optimistic concurrency | Không cấm update, kiểm tra xung đột | Không | Có thể ném optimistic-lock exception |
| Database role chỉ SELECT | DB principal | Chặn DML theo quyền DB | Có, với account bị giới hạn | DB báo lỗi quyền |
| Trigger/constraint | Database | Tùy quy tắc | Có, kể cả SQL ngoài Hibernate | DB có thể từ chối |
| Transaction read-only | Transaction/hạ tầng | Tùy provider | Tùy mức áp dụng database | Không thể giả định phổ quát |

Bảng này nói về **cơ chế**, không xếp hạng một lựa chọn luôn tốt hơn. Thực tế thường cần phối hợp nhiều tầng.

## 20. Ví dụ kiểm chứng hành vi để hiểu đúng

Phần này mô tả **kịch bản mong đợi** để người học có thể tự triển khai kiểm thử tích hợp với Hibernate và một database thật. Đây không phải kết quả test đã chạy cho bài viết.

### 20.1. Entity immutable: thay field nhưng không UPDATE

Chuẩn bị `AuditEvent(id=10, message="original")`, sau đó:

```java
AuditEvent event = em.find(AuditEvent.class, 10L);
event.changeMessageInMemory("modified");
em.flush();
```

Quan sát:

1. `event.getMessage()` trong persistence context có thể là `"modified"`.
2. Hibernate không dự kiến gửi `UPDATE audit_events SET message=...` từ dirty checking entity này.
3. Trong một persistence context **mới** đọc lại từ database (đã ngắt cache/stale state phù hợp), `message` vẫn là `"original"` nếu không có đường ghi khác.

Khi kiểm tra, nên tạo session mới hoặc `refresh` phù hợp để không vô tình đọc lại chính instance đã biến đổi trong first-level cache.

### 20.2. Collection immutable: thay membership dẫn đến lỗi

Giả sử một snapshot đã được persist, đang có `{"READ"}`:

```java
PolicySnapshot snapshot = em.find(PolicySnapshot.class, 10L);

// Giả định có một method nội bộ được dùng chỉ để minh họa:
snapshot.addPermissionForExperiment("ADMIN");
em.flush();
```

Nếu method thật sự thêm phần tử vào persistent collection `@Immutable`, Hibernate dự kiến phát hiện mutation và ném `HibernateException`.

**Đừng kiểm tra chỉ bằng `snapshot.getPermissions().add(...)` trong class mẫu**, bởi getter trả `Collections.unmodifiableSet`: lúc đó Java ném `UnsupportedOperationException` **trước khi Hibernate có cơ hội xử lý**.

### 20.3. Collection phần tử là entity mutable

Một `Catalog` có collection `@Immutable Set<CatalogItem>` nhưng `CatalogItem` không có `@Immutable`. Trong một transaction:

```java
CatalogItem item = em.find(CatalogItem.class, 100L);
item.rename("New title");
```

Nếu `CatalogItem` là entity mutable, thao tác có thể cập nhật hàng của chính nó. `@Immutable` trên collection không chặn mọi chỉnh sửa state của từng item.

### 20.4. Native SQL

```java
em.createNativeQuery(
    "update audit_events set message = 'forced' where id = 10"
).executeUpdate();
```

Với database account có quyền ghi, SQL có thể thay hàng dù entity class được đánh dấu immutable. Chỉ cơ chế DB/authorization phù hợp mới kiểm soát được đường này.

### 20.5. Bulk HQL trên các phiên bản

Chạy một bulk update nhắm vào entity immutable trên Hibernate 6.x và 7.x có thể cho kết quả khác: mặc định 6.x thường cảnh báo, còn Hibernate 7.0+ mặc định báo exception theo migration guide. Nếu dùng nhiều service khác version, đừng suy luận hành vi giống nhau chỉ dựa vào tên annotation.

## 21. Những hiểu lầm phổ biến

### “Thêm `@Immutable` sẽ khiến setter tự throw”

Không đúng với entity. Java vẫn có thể thay đổi field; Hibernate thường chỉ **không đồng bộ state của entity lên database**.

### “`@Immutable` trên collection chỉ im lặng bỏ qua add/remove”

Sai. Hibernate document rõ rằng **modifying an immutable collection** sẽ dẫn đến `HibernateException`.

### “Entity `@Immutable` không bao giờ INSERT hoặc DELETE được”

Không đúng theo nghĩa chung. Annotation cấm/loại bỏ đường UPDATE state thông thường; các thao tác lifecycle khác có semantics riêng và có thể thực hiện nếu database cho phép.

### “Đánh dấu parent entity immutable làm mọi child và association bất biến”

Không thể suy luận như vậy. Collection membership, entity con và owning side của quan hệ là những phần quản lý khác nhau. Cần chỉ rõ scope và kiểm tra đường ghi.

### “Read-only transaction và `@Immutable` là một”

Không. Transaction hint/read-only session có scope theo giao dịch hoặc instance; `@Immutable` là mapping static ở Hibernate.

### “Dữ liệu trong SQL view đã bất biến vì entity có `@Immutable`”

Không. Chỉnh sửa qua ứng dụng khác hoặc SQL path khác vẫn phụ thuộc quyền và cơ chế view/database.

### “`@Immutable` là giải pháp bảo mật cho audit log”

Không. Đó là metadata ORM; cần quyền DB, API, auditing và lưu trữ phù hợp nếu phải chống thay đổi ngoài Hibernate.

### “Hibernate 6 và 7 luôn cho phép bulk UPDATE immutable entity theo cùng cách”

Không. Hibernate 7.0 thay đổi mặc định của bulk update/delete queries đối với immutable entities từ cho phép kèm warning sang exception, có setting cho phép trở lại khi thực sự cần.

## 22. Khi nào nên dùng `@Immutable`?

| Tình huống | Gợi ý | Điều cần bổ sung |
| --- | --- | --- |
| Bảng danh mục quốc gia/mã chuẩn hầu như chỉ đọc | `@Entity @Immutable` có thể phù hợp | Quy trình cập nhật danh mục ngoài ORM, cache invalidation |
| SQL view/bảng tổng hợp chỉ đọc | `@Entity @Immutable` và mapping view/subselect phù hợp | ID duy nhất, quyền DB, refresh policy |
| Bản phát hành đã snapshot các tag/quyền | `@Immutable` trên collection value | API không cho sửa, DB constraints nếu cần |
| Set quan hệ chỉ cố định sau khi tạo | `@Immutable` trên collection `@OneToMany`/`@ManyToMany` | Xem owning side, entity phần tử, cascade |
| Một cột `createdAt` không nên update | `@Column(updatable=false)` hoặc property `@Immutable` | Domain API và database nếu cần |
| Entity có trạng thái DRAFT/PUBLISHED và chỉ PUBLISHED mới bị khóa | Không tự áp `@Immutable` toàn class một cách máy móc | Domain state machine, @Version, DB rule hoặc tách snapshot |
| Audit log yêu cầu append-only | `@Immutable` có thể hỗ trợ ORM | Quyền DB, transaction, retention, audit |
| Danh sách đơn hàng cần cập nhật thường xuyên | Không dùng collection immutable | Mapping mutable và validation |
| Chỉ muốn tối ưu một report query | Read-only query/session có thể phù hợp | Đo memory và throughput, transaction scope |

Một câu hỏi nên đặt trước khi dùng:

> “Tôi muốn Hibernate **bỏ qua thay đổi state**, **ném lỗi khi thay membership**, hay muốn database **từ chối mọi SQL ghi**?”

Ba mục tiêu khác nhau, không thể giải quyết tất cả bằng một annotation.

## 23. Bài tập tình huống

**Bài 1.** Một `AuditEvent @Immutable` được load, sau đó `setMessage("changed")` và `flush()`. Có chắc Hibernate ném exception không?

**Trả lời:** Không. Với entity `@Immutable`, thay đổi thuộc tính trong bộ nhớ thường bị **bỏ qua khi dirty checking**, không ném lỗi chỉ vì set field. Object Java có thể vẫn mang giá trị mới, database vẫn giữ giá trị cũ.

**Bài 2.** Một `PolicySnapshot` có `@ElementCollection @Immutable Set<String> labels` đã lưu vào DB. Code thêm `"urgent"` rồi flush. Kết quả nào cần dự kiến?

**Trả lời:** Hibernate có thể ném `HibernateException` vì membership của immutable collection bị sửa. Nếu getter Java trả unmodifiable view, exception có thể xảy ra **sớm hơn** dưới dạng `UnsupportedOperationException` trước Hibernate.

**Bài 3.** `Catalog.items` là `@OneToMany @Immutable`, nhưng `CatalogItem` vẫn mutable. `item.rename()` có bị chặn không?

**Trả lời:** Không mặc nhiên. Annotation trên collection hạn chế thay **thành viên**; state của entity item phải được quản lý qua annotation/quy tắc riêng.

**Bài 4.** Hệ thống dùng Hibernate 7.2, gọi bulk HQL `update AuditEvent ...` trên immutable entity và bị exception; bản Hibernate 6.x trước đó chỉ ghi warning. Có mâu thuẫn không?

**Trả lời:** Không. Hibernate 7.0 đã thay đổi mặc định cho bulk update/delete nhắm immutable entity. Có setting `hibernate.query.immutable_entity_update_query_handling_mode=allow` nếu thực sự cần nới lỏng, nhưng phải kiểm tra quy tắc nghiệp vụ.

**Bài 5.** Database administrator dùng SQL trực tiếp cập nhật bảng `audit_events` đã map `@Immutable`. Annotation có chặn được không?

**Trả lời:** Không. SQL chạy theo quyền của database account; `@Immutable` không phải trigger hay database permission.

**Bài 6.** Muốn cấm chỉnh sửa sau khi invoice chuyển từ DRAFT sang ISSUED. Nên đặt `@Immutable` lên class `Invoice` luôn không?

**Trả lời:** Không nếu bản nháp vẫn cần cập nhật. Nên thiết kế điều kiện theo state, optimistic locking, transaction và constraint phù hợp, hoặc tách immutable snapshot đã phát hành.

**Bài 7.** Một immutable entity được `persist()` lần đầu. Có thể INSERT không?

**Trả lời:** Có thể. Immutable ở đây liên quan đến update state của entity đã managed; nó không đồng nghĩa cấm tạo mới. Nếu muốn ngăn INSERT trong một luồng, cần quyền và API tương ứng.

**Bài 8.** Ứng dụng dùng `Collections.unmodifiableList()` trên getter. Vậy có cần `@Immutable` cho collection không?

**Trả lời:** Hai cơ chế bảo vệ ở hai tầng. Getter unmodifiable chặn thao tác qua view Java; code nội bộ hoặc ORM vẫn có thể sửa collection. Nếu mapping cần tuyên bố collection persistent không được đổi membership sau khi lưu, `@Immutable` bổ sung ý nghĩa ở Hibernate.

## 24. Tài liệu chính thức

Khi áp dụng trong hệ thống thật, chọn **tài liệu đúng phiên bản Hibernate** mà ứng dụng đang chạy:

- [Hibernate ORM User Guide 7.2 — Mutability / `@Immutable`](https://docs.hibernate.org/orm/7.2/userguide/html_single/#mapping-mutability-immutable): phân biệt immutable entity, basic attribute và plural attribute; các tối ưu dirty checking.
- [Hibernate ORM 7.0 Javadoc — `org.hibernate.annotations.Immutable`](https://docs.hibernate.org/orm/7.0/javadocs/org/hibernate/annotations/Immutable.html): phạm vi annotation, entity changes bị bỏ qua, exception khi sửa collection và inheritance.
- [Hibernate ORM 7.0 Migration Guide](https://docs.hibernate.org/orm/7.0/migration-guide/): mục *Update queries affecting immutable entities*, thay đổi mặc định của bulk mutation trong Hibernate 7.
- [Hibernate ORM User Guide — Persistence Context](https://docs.hibernate.org/orm/7.2/userguide/html_single/#pc): managed/detached, dirty checking, flush và entity state transitions.
- [Hibernate ORM User Guide — `@Subselect`](https://docs.hibernate.org/orm/7.2/userguide/html_single/#mapping-entity-subselect): mapping entity từ truy vấn SQL và những lưu ý với table synchronization.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): hành vi nền của entity, lifecycle, collection mapping, transaction và JPQL.

`@Immutable` là **extension của Hibernate**; nếu có nhu cầu chuyển provider, cần đánh giá lại vì đây không phải một annotation portability standard của Jakarta Persistence.

## Kết luận

**`@Immutable` không có một hành vi duy nhất trên mọi target.** Với entity, Hibernate thường bỏ qua thay đổi state khi đồng bộ và tiết kiệm một phần chi phí dirty checking; với persistent collection, thay đổi danh sách thành viên có thể gây `HibernateException`; với thuộc tính basic, thay đổi riêng field bị bỏ qua. Annotation giúp **diễn đạt ý định mapping** và tránh một số lệnh UPDATE ngoài mong muốn nhưng không tự làm object Java immutable hoặc cấm mọi lệnh ghi ở database.

Để bảo đảm bất biến đúng nghĩa, cần xác định **dữ liệu nào bất biến, từ thời điểm nào, dưới những đường ghi nào**. Sau đó kết hợp mapping Hibernate với API domain, transaction, quyền database, constraint/trigger, concurrency và cache policy khi cần. Đặc biệt phải kiểm tra **phiên bản Hibernate** khi xử lý bulk HQL/JPQL mutation và **phạm vi quan hệ** khi dùng `@Immutable` trên collection.
