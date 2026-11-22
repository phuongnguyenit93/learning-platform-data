# Đánh giá xung đột khi hợp nhất entity đã tách

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Khóa lạc quan

Một entity có thể được người dùng tải lên biểu mẫu chỉnh sửa, trở thành **detached** khi persistence context kết thúc, rồi được gửi lại để lưu sau vài phút. Trong khoảng đó, một giao dịch khác có thể đã thay đổi chính bản ghi ấy. Nếu chỉ gọi **EntityManager.merge(...)** mà không hiểu cơ chế phiên bản, ứng dụng có thể ghi đè dữ liệu mới hoặc xử lý lỗi không đúng thời điểm.

**Khóa lạc quan (optimistic locking)** với **@Version** giúp JPA nhận diện một bản cập nhật đang dựa trên phiên bản cũ. Khi hợp nhất detached entity mang stale version, provider phải thực hiện kiểm tra phiên bản phù hợp theo hợp đồng JPA. Xung đột có thể được báo bằng **OptimisticLockException** tại **merge**, **flush** hoặc **commit**; không được giả định lỗi luôn xuất hiện ngay tại dòng merge.

~~~text
T0  Database Article#42: version=7, title="Intro", body="Old"
T1  Người A đọc Article#42 version=7 rồi đóng EntityManager
T2  Người B đọc Article#42 version=7
T3  B đổi title và commit → database version=8
T4  A sửa body trên detached Article version=7
T5  A gọi merge(detached)
T6  JPA kiểm tra version: 7 không còn khớp 8
T7  OptimisticLockException tại merge/flush/commit
T8  Transaction của A rollback; thay đổi của B được giữ
~~~

**Merge không có nghĩa lấy dữ liệu trong object cũ làm nguồn sự thật mới nhất.** Nhưng @Version cũng không phải phép màu: những đường ghi khác như native SQL, bulk JPQL hoặc stored procedure có thể không cập nhật version theo quy tắc ORM nếu không được thiết kế rõ.

Bài này đi từ vòng đời entity, version snapshots, cơ chế merge, thời điểm lỗi, rủi ro ghi đè field, cascade và quan hệ, API chỉnh sửa qua DTO, retry, transaction đến kiểm thử hai giao dịch thực sự.

## 1. Phân biệt detached, managed và merge

### 1.1. Các trạng thái cơ bản

| Trạng thái | Ý nghĩa | Dirty checking? |
|---|---|---|
| New/transient | Java object chưa được persist | Không |
| Managed | Được persistence context quản lý | Có |
| Detached | Đã có persistence identity, không còn managed | Không |
| Removed | Được đánh dấu xóa trong context | Theo JPA remove lifecycle |

Ví dụ:

~~~java
EntityManager em = emf.createEntityManager();
Article article = em.find(Article.class, 42L);
em.close();

// article vẫn là Java object nhưng đã detached.
// Đổi field lúc này không tự tạo UPDATE.
~~~

Entity có thể detached do **em.detach(entity)**, **em.clear()**, **em.close()** hoặc khi context tương ứng kết thúc. Nó vẫn chứa ID, version và các persistent attributes đã được load.

### 1.2. Merge hợp nhất state vào managed target

~~~java
Article detached = ...;
Article managed = em.merge(detached);
~~~

Ý nghĩa:
- **detached** là đối tượng nguồn, vẫn detached sau merge.
- **managed** là đối tượng trả về được quản lý trong persistence context đang dùng.
- JPA hợp nhất state của nguồn vào managed entity cùng identity hoặc một managed copy.
- Nếu đã có managed target cùng identity trong context, JPA có thể dùng chính target đó.
- SQL UPDATE có thể chỉ phát khi flush/commit.
- Trên entity có @Version, provider phải bảo vệ tính nhất quán của phiên bản.

Không viết:

~~~java
em.merge(detached);
detached.rename("Sửa tiếp", Instant.now());
// detached vẫn không được dirty checking.
~~~

Nên viết:

~~~java
Article managed = em.merge(detached);
managed.rename("Sửa tiếp", Instant.now());
~~~

Nếu merge phát hiện xung đột và ném exception, managed result chưa chắc được trả về.

### 1.3. Merge không đồng nghĩa commit

**Merge** là thao tác hợp nhất trạng thái vào persistence context. **Flush** đồng bộ pending changes với database trong transaction. **Commit** xác nhận transaction. Mỗi bước có thể gặp lỗi và không đồng nghĩa với bước còn lại.

~~~text
detached
   |
   v
EntityManager.merge
   |
   +-- validate identity/version/state theo provider
   |
   v
managed target có pending changes
   |
   v
flush → SQL UPDATE ... WHERE id=? AND version=?
   |
   v
commit hoặc rollback
~~~

### 1.4. Optimistic locking là bảo vệ snapshot

Một detached object mang version **V** cho biết client đã biên tập dựa trên snapshot V. Nếu bản ghi DB hiện là V+1, ứng dụng phải coi đó là stale edit thay vì mặc định tự ghi đè.

Optimistic locking là cơ chế **phát hiện**, không phải thuật toán tự hòa giải hai bản chỉnh sửa. Nó không so sánh diff văn bản, không biết ý định người dùng và không tự đề xuất bản cuối.

## 2. Mô hình entity Article có @Version

Ví dụ dùng Jakarta Persistence và bảng articles.

~~~java
package com.example.content;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "articles")
public class Article {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(nullable = false)
    private Long version;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(name = "body", nullable = false, length = 10000)
    private String body;

    @Column(nullable = false)
    private Instant modifiedAt;

    protected Article() {}

    public Article(String title, String body, Instant now) {
        rename(title, now);
        rewriteBody(body, now);
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getTitle() { return title; }
    public String getBody() { return body; }
    public Instant getModifiedAt() { return modifiedAt; }

    public void rename(String nextTitle, Instant now) {
        if (nextTitle == null || nextTitle.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề trống");
        }
        title = nextTitle.trim();
        modifiedAt = Objects.requireNonNull(now);
    }

    public void rewriteBody(String nextBody, Instant now) {
        if (nextBody == null || nextBody.isBlank()) {
            throw new IllegalArgumentException("Nội dung trống");
        }
        body = nextBody;
        modifiedAt = Objects.requireNonNull(now);
    }
}
~~~

**Không có setter công khai cho version.** Ứng dụng không nên đặt version theo ý muốn chỉ để vượt qua kiểm tra concurrency. Cần để JPA/provider quản lý thuộc tính này khi dùng managed entity.

### 2.1. Schema PostgreSQL minh họa

~~~sql
CREATE TABLE articles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    body VARCHAR(10000) NOT NULL,
    modified_at TIMESTAMPTZ NOT NULL
);
~~~

DDL chỉ minh họa. Migration thực tế phải tương thích với provider, đặc biệt cơ chế khởi tạo version khi INSERT. Không giả định version luôn bắt đầu từ 0 trên mọi hệ thống; ví dụ dưới ký hiệu ban đầu **V**.

### 2.2. Tại sao dùng Long?

Numeric version giúp dễ hình dung:
- Một managed update thành công thường tăng version.
- SQL ghi có điều kiện oldVersion.
- Một snapshot cũ dễ được phát hiện.
- Có thể mang version trong DTO hoặc ETag có kiểm soát.

JPA hỗ trợ các version types theo đặc tả; không phải mọi type đều có thể cộng 1 thủ công. Ví dụ bài dùng Long nhất quán.

### 2.3. modifiedAt không thay @Version

| Trường | Mục đích |
|---|---|
| id | Entity identity |
| version | Optimistic lock token |
| title/body | Business state được hợp nhất |
| modifiedAt | Dấu thời gian nghiệp vụ |

Dùng timestamp modifiedAt đơn thuần để phát hiện xung đột có rủi ro về độ phân giải thời gian, clock và đường ghi ngoài ORM. Với optimistic locking JPA, dùng **@Version**.

### 2.4. Entity và DTO khác nhau

- **Detached Article**: có identity, persistent state và snapshot version.
- **ArticleEditRequest**: dữ liệu do client gửi, có thể chỉ chứa vài fields.
- **Managed Article**: được JPA theo dõi trong transaction hiện tại.

Không dựng một Article từ JSON chỉ có ID/title rồi gọi merge nếu những field khác bị thiếu; state NULL hoặc stale có thể bị hợp nhất ngoài ý muốn.

## 3. Diễn tiến hai người cùng chỉnh sửa

### 3.1. Timeline xung đột

~~~text
Database ban đầu:
Article#42 {title="Intro", body="Old", version=7}

A tải rồi detached:
A_article {title="Intro", body="Old", version=7}

B tải, đổi title:
B_article {title="New intro", body="Old", version=7}

B flush/commit:
Database {title="New intro", body="Old", version=8}

A đổi body trên detached:
A_article {title="Intro", body="A content", version=7}

A merge:
Stale snapshot version=7 trong khi DB version=8
→ optimistic conflict
→ rollback A
~~~

A và B có thể sửa hai fields khác nhau nhưng vẫn xung đột. @Version thường bảo vệ **entity-row snapshot** chứ không tự so sánh “hai field có khác nhau không”.

### 3.2. A đọc và rời persistence context

~~~java
EntityManager emA = emf.createEntityManager();
Article detachedA;

try {
    emA.getTransaction().begin();

    detachedA = emA.find(Article.class, articleId);

    emA.getTransaction().commit();
} finally {
    emA.close();
}

Long originalVersion = detachedA.getVersion();
detachedA.rewriteBody("Nội dung A", Instant.now());
~~~

Đây là ví dụ resource-local EntityManager. Trong Spring, EntityManager thường do framework quản lý; không tự begin/commit trên injected transaction-scoped EntityManager.

### 3.3. B sửa và commit bằng context khác

~~~java
EntityManager emB = emf.createEntityManager();

try {
    emB.getTransaction().begin();

    Article articleB =
        emB.find(Article.class, articleId);

    articleB.rename("Tiêu đề B", Instant.now());

    emB.getTransaction().commit();
} finally {
    emB.close();
}
~~~

Nếu cập nhật thành công, JPA quản lý việc kiểm tra/tăng version. Không viết code tự gán version trên entity B.

### 3.4. A hợp nhất bản cũ

~~~java
EntityManager emMerge = emf.createEntityManager();

try {
    emMerge.getTransaction().begin();

    Article managed = emMerge.merge(detachedA);

    // Có thể lỗi ngay tại merge, ở flush, hoặc commit.
    emMerge.flush();

    emMerge.getTransaction().commit();
} catch (RuntimeException ex) {
    if (emMerge.getTransaction().isActive()) {
        emMerge.getTransaction().rollback();
    }
    throw ex;
} finally {
    emMerge.close();
}
~~~

Với detached version cũ, provider phải ngăn bản sửa stale được commit thành công theo cơ chế @Version. Exception có thể được bọc ở tầng transaction/framework; không phụ thuộc duy nhất vào exact class từ một dòng code.

### 3.5. Database sau rollback

Sau optimistic conflict và rollback:
- Thay đổi đã commit của B được giữ.
- Những thay đổi chưa commit của A bị hủy.
- Transaction A không được tiếp tục để “cố lưu” cùng stale instance.
- Cần tải state mới trong transaction/persistence context mới trước khi quyết định retry hoặc hòa giải.

## 4. Thời điểm OptimisticLockException

### 4.1. Tại merge

Provider có thể đọc target hiện tại và so sánh version:

~~~java
Article managed = em.merge(detached);
// Có thể ném OptimisticLockException ở đây.
~~~

### 4.2. Tại flush

Provider có thể trì hoãn SQL tới lúc flush:

~~~java
Article managed = em.merge(detached);
em.flush();  // Có thể phát hiện version mismatch tại đây.
~~~

**Flush không đồng nghĩa commit**. Câu SQL có thể chạy nhưng transaction vẫn có thể rollback.

### 4.3. Tại commit

Nếu không flush thủ công:

~~~java
Article managed = em.merge(detached);
transaction.commit(); // Có thể thất bại ở flush/commit.
~~~

Trong Spring @Transactional, phần commit thường do interceptor thực hiện **sau khi method body kết thúc**. Vì vậy try/catch chỉ bao quanh em.merge trong method có thể không bắt được lỗi xuất hiện ở commit.

### 4.4. Sai lầm: chỉ bắt lỗi tại merge

~~~java
try {
    em.merge(detached);
} catch (OptimisticLockException ex) {
    // Không đủ nếu exception chỉ xuất hiện lúc flush/commit.
}

em.flush();
transaction.commit();
~~~

Cần xử lý lỗi ở ranh giới bao trọn transaction. Dùng Spring exception translation và controller advice/service caller khi phù hợp.

### 4.5. Các dạng exception có thể gặp

| Tầng | Dạng lỗi có thể xuất hiện |
|---|---|
| Jakarta Persistence | OptimisticLockException |
| Commit của transaction | RollbackException có cause liên quan |
| Spring | OptimisticLockingFailureException hoặc ObjectOptimisticLockingFailureException |
| Provider | Stale object/row exception riêng, được bọc |
| Database | Deadlock, serialization error hoặc constraint error khác, không đồng nhất với optimistic conflict |

Không phân loại chỉ dựa vào chuỗi error message. Quan sát cause chain và API exception translation phù hợp.

### 4.6. Rollback khi một entity xung đột

Giả sử transaction sửa Article#1 và Article#2. Article#2 bị optimistic conflict; các thay đổi chưa commit của Article#1 cũng phải được rollback nếu chúng thuộc cùng transaction.

Đừng khẳng định “Article#1 lưu thành công” chỉ vì SQL UPDATE của nó đã chạy trước khi flush ném exception.

### 4.7. Flush thành công vẫn chưa đủ xác nhận

Commit còn có thể thất bại vì một constraint deferred, kết nối, lock/isolation hoặc vấn đề transaction khác. Chỉ báo thành công cho người dùng sau khi transaction boundary đã hoàn tất đúng.

## 5. Nguồn detached và managed result sau merge

### 5.1. Đối tượng đầu vào vẫn detached

~~~java
Article detached = obtainDetachedArticle();
Article managed = em.merge(detached);

System.out.println(em.contains(detached)); // false
System.out.println(em.contains(managed));  // true
~~~

**obtainDetachedArticle** là helper minh họa, phải được định nghĩa trong project/test khi dùng. Một managed result được trả về từ merge có cùng persistence identity nhưng **không nhất thiết cùng Java reference** với detached source.

Nếu cần sửa tiếp, sửa **managed**:

~~~java
Article managed = em.merge(detached);
managed.rename("Tiêu đề sau merge", Instant.now());
~~~

Không sửa detached rồi cho rằng dirty checking đang theo dõi nó.

### 5.2. Phiên bản của detached không tự cập nhật

~~~text
Trước merge thành công:
    detached.version = 7

Sau khi managed update và commit:
    database.version = 8
    managed.version  = 8 (với numeric @Version)
    detached.version có thể vẫn = 7
~~~

Nguồn detached giữ snapshot cũ. Nếu dùng nó cho một lần merge khác, có thể bị coi là stale. Muốn trả một token version mới cho client, dựa trên state đã được lưu/commit theo transaction hợp lệ, không lấy version của detached source.

### 5.3. Target đã managed có thể bị copy dữ liệu cũ

~~~java
Article managed = em.find(Article.class, id);
managed.rename("Sửa mới từ service", now);

Article result = em.merge(detachedWithSameId);
~~~

JPA có thể hợp nhất detached state vào chính managed target trong context. Nếu detached có title cũ, việc merge có thể **ghi đè thay đổi title vừa thực hiện ở RAM** dù database version chưa đổi. Đây là xung đột thứ tự thao tác **trong cùng persistence context**, không nhất thiết được @Version tự giải quyết.

### 5.4. Phân loại xung đột

| Tình huống | Điều xảy ra | Cơ chế bảo vệ |
|---|---|---|
| Detached V, DB V+1 | Snapshot không còn mới | @Version, OptimisticLockException |
| Detached cùng V nhưng target managed đã chỉnh sửa field | Có thể overwrite in-memory | Thiết kế service/domain flow |
| A sửa body, B sửa title từ V | Row-level conflict sau commit đầu tiên | @Version + business resolution |
| Native SQL thay DB không tăng version | Có thể không phát hiện stale snapshot | Policy đồng nhất mọi write paths |
| DTO thiếu fields được dựng thành entity rồi merge | Có thể copy NULL/state cũ | DTO patch + managed update |
| Child graph version cũ | Có thể xung đột ở child | @Version child + cascade/flush |

**Optimistic locking chỉ phát hiện loại xung đột theo version**, không phân giải tự động toàn bộ trường hợp người dùng không hài lòng với kết quả merge.

## 6. SQL version check và giới hạn của @Version

### 6.1. SQL minh họa

Giả sử DB Article#42 version=7 và một managed update cần ghi. SQL logic thường tương tự:

~~~sql
UPDATE articles
SET title = ?,
    body = ?,
    version = 8
WHERE id = 42
  AND version = 7;
~~~

Nếu row version=7 không còn, một update đúng theo optimistic lock không được âm thầm ghi đè version=8. Provider phát hiện và báo lỗi.

Đây là minh họa; provider có thể chỉ update dirty columns, dùng bind parameters, hoặc có chiến lược version khác.

### 6.2. Version không tự tăng mỗi lần gọi merge

Nếu merge không tạo một thay đổi persistent state cần UPDATE, không được khẳng định **mỗi merge nhất định tăng version**. Optimistic locking liên quan entity update và các lock modes cụ thể, không đơn thuần một lời gọi API.

### 6.3. Không tự tăng version từ client

Sai:

~~~java
// Không cung cấp API kiểu này để vượt conflict:
detached.setVersion(detached.getVersion() + 1);
em.merge(detached);
~~~

Version là **dấu hiệu của snapshot được đọc**. Nếu người dùng tự đặt thành giá trị hiện tại chỉ để qua kiểm tra, cơ chế phát hiện stale update bị phá vỡ.

### 6.4. Native SQL ngoài ORM

~~~sql
UPDATE articles
SET body = 'Body từ một job khác'
WHERE id = 42;
~~~

Nếu writer này không tăng version, detached entity version=7 có thể bị coi là hợp lệ dù body DB đã đổi. Cần thống nhất chính sách với mọi đường ghi: ORM, native SQL, stored procedure, bulk update, trigger và ứng dụng khác.

Với numeric version, một pattern CAS SQL là:

~~~sql
UPDATE articles
SET body = :new_body,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
~~~

Caller phải kiểm tra affected row count và transaction, không giả định JPA tự kiểm tra/tăng version của native query.

### 6.5. Bulk JPQL UPDATE cũng là đường ghi riêng

~~~java
em.createQuery(
    "update Article a set a.title = :title where a.id = :id"
)
.setParameter("title", "New title")
.setParameter("id", id)
.executeUpdate();
~~~

Dù chỉ nhắm một ID, đó vẫn là **bulk DML**: không tự áp managed-entity @Version behavior hoặc đồng bộ Java instances. Nếu cần optimistic locking, biểu đạt version predicate/increment rõ ràng hoặc chọn managed update.

### 6.6. modifiedAt không thay thế concurrency token

Timestamp có thể trùng nhau do độ phân giải, không được set ở mọi writer, hoặc phụ thuộc clock. Dùng **@Version** cho locking semantics rõ ràng; modifiedAt phục vụ audit/display.

## 7. Khác biệt giữa row-level và field-level conflict

### 7.1. Hai người sửa hai fields khác nhau

~~~text
Base version=7:
    title="Intro"
    body="Old"

A đổi body="A body" trên detached version=7.
B đổi title="B title" và commit version=8.

A merge version=7 → conflict.
~~~

Vì sao JPA không tự hợp nhất thành title B + body A? Detached object của A có thể chứa **cả title cũ và body mới**:

~~~text
A detached:
    title="Intro"    (cũ)
    body="A body"    (A có sửa)
    version=7
~~~

Copy toàn bộ A sang DB mà bỏ version check sẽ làm **mất title B**. JPA không biết A chỉ muốn sửa body.

### 7.2. Hòa giải ba chiều

Một conflict resolution có thể so sánh:

| Field | Base V=7 | A muốn | DB hiện V=8 |
|---|---|---|---|
| title | Intro | Intro (không đổi) | B title |
| body | Old | A body | Old |

Nếu biết rõ intent của A và DB chưa đổi body, ứng dụng có thể thử:
1. Giữ title từ DB;
2. Áp body của A;
3. Ghi vào managed Article phiên bản hiện tại;
4. Commit; optimistic lock vẫn bảo vệ nếu có writer thứ ba.

Nếu A và B cùng sửa body, cần chính sách rõ: từ chối, yêu cầu người dùng chọn hoặc domain-specific merge. **Không tự coi last-write-wins là an toàn**.

### 7.3. Một detached entity không mô tả được ý định đầy đủ

Giá trị title="Intro" trong detached source có thể là:
- User cố ý đổi title về Intro;
- Hoặc title chưa được chạm tới từ lúc form mở.

Để resolve conflict theo field, cần lưu **base snapshot hoặc danh sách fields thay đổi**. DTO patch thường diễn đạt ý định tốt hơn toàn entity detached.

### 7.4. Provider-specific dirty optimistic locking

Hibernate và một số ORM có extensions optimistic locking dựa trên dirty/all columns trong một số mapping. Không mặc định tính năng này là hợp đồng portable của JPA @Version/merge; cần cấu hình và kiểm thử. Bài tập trung vào optimistic row versioning.

## 8. Optimistic và pessimistic locking khác nhau

### 8.1. Optimistic không khóa database trong suốt thời gian người dùng nhập liệu

Người A có thể giữ form 20 phút mà không giữ DB lock. Người B vẫn có thể commit trong thời gian đó; khi A lưu, version check phát hiện xung đột.

Đó là tính phù hợp của optimistic lock với web applications dài hơi, không phải sự bảo đảm “mọi người không bao giờ sửa trùng”.

### 8.2. Pessimistic locking

~~~java
Article article = em.find(
    Article.class, id,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Database có thể giữ lock đến khi transaction kết thúc theo DB/driver behavior. Không giữ một transaction mở trong lúc người dùng nhập form chỉ để tránh optimistic conflict.

### 8.3. OPTIMISTIC và OPTIMISTIC_FORCE_INCREMENT

~~~java
Article article = em.find(
    Article.class, id,
    LockModeType.OPTIMISTIC
);
~~~

~~~java
em.lock(
    article,
    LockModeType.OPTIMISTIC_FORCE_INCREMENT
);
~~~

**OPTIMISTIC** yêu cầu xác minh version cho managed entity theo JPA. **OPTIMISTIC_FORCE_INCREMENT** yêu cầu tăng version theo contract để có thể bảo vệ những trường hợp cần đánh dấu phiên bản, chẳng hạn coordinated updates. Cả hai không phải cách hợp thức hóa **một detached object đã stale**.

### 8.4. Bảng lựa chọn

| Use case | Công cụ cân nhắc |
|---|---|
| Người dùng sửa form dài | @Version + conflict response |
| Sửa managed entity ngắn trong transaction | @Version bình thường |
| Cần khóa write trong transaction ngắn | PESSIMISTIC_WRITE |
| Kiểm tra version của entity đã đọc | OPTIMISTIC |
| Cần đánh dấu thay đổi version có chủ đích | OPTIMISTIC_FORCE_INCREMENT |
| Atomic update có expectedVersion | Conditional UPDATE/CAS |

## 9. Transaction sau xung đột

### 9.1. Rollback và không tiếp tục dùng transaction lỗi

~~~java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    Article result = em.merge(detached);
    em.flush();

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

OptimisticLockException thường làm transaction bị đánh dấu rollback. Sau xung đột:
- Rollback transaction;
- Không sửa/lưu tiếp trên cùng transaction bị lỗi;
- Không tin state của managed objects trong context vừa rollback;
- Đọc bản mới bằng transaction/context mới nếu cần resolve.

### 9.2. Không retry mù quáng trên cùng detached source

Sai về ý nghĩa:

~~~java
for (int i = 0; i < 3; i++) {
    try {
        em.merge(stale);
    } catch (OptimisticLockException ex) {
        // Thử lại cùng object stale, cùng transaction?
    }
}
~~~

Nếu source version=7, DB version=8, retry y nguyên source không tạo ra thông tin mới. Hơn nữa, transaction có thể đã rollback-only.

Muốn thử lại phải:
1. Rollback và tạo transaction mới;
2. Tải bản hiện hành;
3. Kiểm tra business changes/intent;
4. Áp dụng policy resolve;
5. Commit và xử lý khả năng xung đột tiếp.

### 9.3. Phân loại lỗi ở tầng ứng dụng

Optimistic conflict khác:
- FK/UNIQUE/CHECK constraint violation;
- Validation error;
- Serialization failure/deadlock;
- Resource not found;
- Authorization denied.

Không chuyển tất cả exceptions thành “có người khác sửa”. Với Spring, có thể gặp các exception translation như ObjectOptimisticLockingFailureException; với JPA thuần có thể thấy OptimisticLockException/RollbackException có cause tương ứng.

### 9.4. HTTP response cho conflict

- **409 Conflict** phù hợp cho nhiều API từ chối stale edit do domain/version conflict.
- **412 Precondition Failed** phù hợp khi dùng **If-Match** và precondition version/ETag không thỏa.
- **404 Not Found** hoặc policy tương ứng nếu row đã bị xóa.
- **403 Forbidden** nếu user không được quyền truy cập.

Không coi 0 affected rows của một conditional update luôn là 409: có thể do quyền, status, version hoặc tài nguyên không tồn tại.

### 9.5. Chỉ công bố thành công sau commit

Nếu transaction rollback nhưng service đã gửi email/webhook “bài viết đã cập nhật”, external side effect và database state bất nhất. Khi cần thông báo:
- Ghi event/outbox cùng transaction;
- Publish sau commit với retry/idempotency phù hợp;
- Không coi merge/flush hoặc việc method body return là commit.

## 10. Spring Data JPA: save và saveAndFlush

### 10.1. Save có thể dùng merge

~~~java
Article saved = articleRepository.save(detached);
~~~

Spring Data quyết định persist hoặc merge tùy cách nhận diện entity mới. Với detached entity đã tồn tại, save thường đi qua merge. **saved** là reference nên dùng tiếp trong context, không mặc định **saved == detached**.

### 10.2. saveAndFlush không phải commit

~~~java
Article saved = articleRepository.saveAndFlush(detached);
~~~

Có thể làm SQL version check diễn ra sớm ở flush, nhưng transaction còn có thể rollback hoặc commit thất bại. Không trả HTTP 200 chỉ vì saveAndFlush chưa ném exception ngay tại dòng gọi.

### 10.3. Spring transaction interceptor

~~~java
@Service
public class ArticleService {
    private final ArticleRepository repository;

    public ArticleService(ArticleRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Article editDetached(Article detached) {
        return repository.save(detached);
    }
}
~~~

Ở đây code minh họa mechanics, **không phải API tốt nhất cho JSON client**. Exception tại commit có thể được ném từ Spring transaction interceptor **sau khi thân method đã return**; đặt xử lý lỗi ở boundary phù hợp.

### 10.4. Chỉ dùng EntityManager.merge khi thật sự cần

Nhiều web applications không cần merge detached entity từ request. Với PATCH/PUT:
- Nhận request DTO chứa expectedVersion;
- Load managed entity hiện tại theo ID;
- Kiểm tra expectedVersion;
- Gọi domain methods với changed fields;
- Flush/commit;
- Trả version mới.

Cách này tránh copy vô tình dữ liệu cũ ở các fields client không định thay đổi. Phần tiếp theo xây ví dụ đầy đủ.

## 11. API an toàn hơn: expectedVersion và managed entity

Một HTTP request không nên dựng một entity detached từ JSON thiếu fields rồi gọi merge theo mặc định. Thiết kế rõ **đối tượng nào được sửa**, **client đã đọc version nào** và **những fields nào thực sự thay đổi**.

### 11.1. Trả version trong DTO khi mở biểu mẫu

~~~java
public record ArticleView(
    Long id,
    Long version,
    String title,
    String body
) {
    public static ArticleView from(Article article) {
        return new ArticleView(
            article.getId(),
            article.getVersion(),
            article.getTitle(),
            article.getBody()
        );
    }
}
~~~

GET Article#42 version=7:

~~~json
{
  "id": 42,
  "version": 7,
  "title": "Intro",
  "body": "Old body"
}
~~~

Client giữ version=7 làm token snapshot, không tự tăng version trước khi lưu.

### 11.2. Request chỉ đổi tiêu đề

~~~java
public record RenameArticleRequest(
    Long expectedVersion,
    String newTitle
) {}
~~~

Request này không chứa body vì client **không yêu cầu thay body**. Đó là khác biệt lớn so với dựng Article có body=null rồi merge.

### 11.3. Service managed update với version precondition

~~~java
@Service
public class ArticleEditService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public ArticleView rename(
            long articleId,
            long expectedVersion,
            String newTitle) {

        Article article = em.find(
            Article.class, articleId);

        if (article == null) {
            throw new ArticleNotFoundException(articleId);
        }

        if (!Objects.equals(
                article.getVersion(),
                expectedVersion)) {
            throw new ArticleConflictException(
                articleId,
                expectedVersion,
                article.getVersion()
            );
        }

        article.rename(newTitle, Instant.now());
        em.flush();

        return ArticleView.from(article);
    }
}
~~~

**ArticleNotFoundException** và **ArticleConflictException** là application exceptions cần định nghĩa riêng, không phải JPA API. Những imports cần thiết gồm Spring Service/Transactional, Jakarta PersistenceContext/EntityManager, Objects và Instant.

### 11.4. Vì sao cần explicit expectedVersion?

Nếu service chỉ tải phiên bản hiện tại:

~~~java
Article current = em.find(Article.class, id);
current.rename(request.newTitle(), now);
~~~

thì JPA quản lý version **tại lúc server đọc**, nhưng không biết client đã soạn request từ version cũ vài phút trước.

Client gửi bản sửa từ version=7, DB đã thành version=8; nếu server không so sánh expectedVersion, nó có thể ghi thành công trên managed version=8 và **ghi đè ý định thay đổi của người khác**.

### 11.5. Vì sao Java check chưa đủ?

Giả sử:
1. Server A đọc DB version=8.
2. Client expectedVersion=8 nên check thành công.
3. Server B commit, DB lên version=9.
4. A flush update từ managed version=8.

Lúc này **@Version ở SQL update** vẫn phải phát hiện writer mới. Java precondition bảo vệ stale form *trước khi thao tác*, còn JPA version check bảo vệ race *sau lúc server đã đọc*.

### 11.6. PATCH không đồng nhất null với absent

Một request:

~~~json
{
  "expectedVersion": 7,
  "title": "New title"
}
~~~

khác request:

~~~json
{
  "expectedVersion": 7,
  "title": "New title",
  "body": null
}
~~~

Field vắng mặt có thể nghĩa “giữ nguyên”, field null có thể nghĩa “xóa” hoặc “không hợp lệ”. Hãy dùng DTO theo command, field presence semantics hoặc JSON Patch phù hợp. Không copy mù những null fields vào entity managed.

### 11.7. Authorization

Nếu entity thuộc owner/tenant, service phải xác thực người dùng được sửa Article trước khi tiết lộ currentVersion hoặc thông tin nội dung. @Version không phải bộ lọc quyền truy cập.

## 12. ETag và If-Match ở HTTP

Version có thể được biểu diễn bằng ETag để client gửi conditional requests.

### 12.1. GET trả ETag

~~~http
HTTP/1.1 200 OK
ETag: "article-42-v7"
Content-Type: application/json

{"id":42,"title":"Intro","body":"Old body"}
~~~

### 12.2. PATCH gửi If-Match

~~~http
PATCH /articles/42
If-Match: "article-42-v7"
Content-Type: application/json

{"title":"New title"}
~~~

Server kiểm tra precondition, tải managed Article, thực thi đúng field change và để @Version bảo vệ flush/commit.

### 12.3. Xung đột precondition

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/json

{"code":"ARTICLE_VERSION_CONFLICT"}
~~~

**412** phù hợp với If-Match không thỏa. Nếu API sử dụng field expectedVersion thay vì HTTP precondition, **409 Conflict** thường phù hợp. Tùy policy, **404** dành cho resource không còn tồn tại, **403** cho không đủ quyền.

### 12.4. ETag không thay SQL version check

Nếu server chỉ so sánh ETag rồi dùng native UPDATE không có condition version, writer khác có thể chen vào giữa check và UPDATE. **ETag là hợp đồng HTTP**, còn **@Version/CAS** bảo vệ transaction ở DB.

### 12.5. Không tự hợp nhất mọi sửa đổi khác field

Một ETag cũ có thể bị từ chối dù A và B sửa hai fields khác nhau. Nếu muốn hòa giải field-level, phải định nghĩa policy và base snapshot. ETag không tự làm merge ba chiều.

## 13. Cascade merge và xung đột trên entity graph

Khi Article có quan hệ tới Sections, merge root có thể cascade sang children nếu được cấu hình.

### 13.1. Child ArticleSection có version riêng

~~~java
@Entity
@Table(name = "article_sections")
public class ArticleSection {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "article_id", nullable = false)
    private Article article;

    @Column(nullable = false)
    private String heading;

    @Column(nullable = false, length = 5000)
    private String content;

    protected ArticleSection() {}

    public Long getId() { return id; }
    public Long getVersion() { return version; }

    public void rewrite(String nextContent) {
        if (nextContent == null) {
            throw new IllegalArgumentException("Content null");
        }
        content = nextContent;
    }
}
~~~

Bổ sung trong Article:

~~~java
@OneToMany(
    mappedBy = "article",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    },
    orphanRemoval = true
)
private List<ArticleSection> sections =
    new ArrayList<>();
~~~

Đây là những đoạn mapping minh họa, không phải hai entity classes hoàn chỉnh trong cùng Java file. Cần imports List/ArrayList và helpers quản lý quan hệ hai chiều.

### 13.2. CascadeType.MERGE

~~~java
Article managed = em.merge(detachedArticle);
~~~

Với cascade MERGE, state của các ArticleSection liên kết có thể được hợp nhất theo các quy tắc JPA. Nếu một section detached mang version=4 nhưng DB section đã thành version=5, có thể gặp optimistic conflict **ở child**, không chỉ ở root.

### 13.3. Root version không mặc định bảo vệ mọi child update

Article.version có thể không tăng với mọi thay đổi riêng của ArticleSection, tùy mapping/operation/provider. Không suy ra một @Version trên root sẽ tự phát hiện mọi chỉnh sửa sâu trong toàn object graph.

Thiết kế rõ:
- Section có @Version riêng không?
- Có cho sửa Section độc lập không?
- Việc thêm/xóa Section có tính là thay đổi root aggregate không?
- Có cần buộc tăng Article.version khi sửa children?
- Những editors nhận snapshot cấp Article hay cấp Section?

### 13.4. Không có cascade MERGE

Nếu association không cho cascade MERGE, không kỳ vọng merge root tự động cập nhật toàn bộ detached children. Cần quản lý child state rõ trong service hoặc cấu hình cascade tương ứng nghiệp vụ.

Không thêm CascadeType.ALL tùy tiện chỉ để merge child: ALL còn bao gồm REMOVE và những hành vi lifecycle khác.

### 13.5. Detached children vẫn detached

Merge graph tạo/tìm managed targets. Source child references vẫn có thể detached; sửa chúng sau merge không tự được dirty checking.

## 14. Collections, orphanRemoval và unfetched LAZY attributes

### 14.1. Thay collection không phải PATCH

A đọc Article cùng Sections [S1,S2]. B thêm S3. A gửi detached snapshot cũ [S1,S2] rồi merge. Nếu ứng dụng coi collection source như trạng thái cuối cùng và có orphanRemoval/cascade, có rủi ro ảnh hưởng membership mà A không hề muốn thay đổi.

Phải xác định rõ:
- Collection đã được tải lúc A đọc chưa?
- Client cố ý xóa child hay chỉ không gửi field?
- Có orphanRemoval/cascade MERGE không?
- Root/child version có bảo vệ đúng thay đổi membership không?

### 14.2. Collection rỗng khác field không gửi

Không dựng detached Article từ JSON thiếu sections với:

~~~java
private List<ArticleSection> sections =
    new ArrayList<>();
~~~

rồi mặc định merge như lệnh “xóa hết sections”. Trường không xuất hiện trong request không nhất thiết mang ý nghĩa empty collection.

### 14.3. LAZY attribute chưa được fetch

JPA quy định provider phải bỏ qua những **LAZY fields chưa được tải** khi merge detached entity; chúng không được coi là null hoặc dữ liệu cần ghi.

Nhưng hãy phân biệt:
- LAZY chưa fetch → provider không hợp nhất state không có sẵn;
- LAZY đã fetch từ lâu → source có thể mang stale state;
- JSON DTO null → không phải bằng chứng field JPA chưa fetch;
- Collection đã được code tạo/clear → là state cụ thể.

Không dùng quy tắc này làm cơ sở để merge các partial entities tùy ý từ HTTP request.

### 14.4. Owning side của quan hệ hai chiều

Với mappedBy="article", phía **ArticleSection.article** là owning side của FK. Cần helper đồng bộ:

~~~java
public void addSection(ArticleSection section) {
    sections.add(section);
    section.attachTo(this);
}
~~~

**attachTo** là domain method cần triển khai trong ArticleSection. Nếu collection và owning reference không nhất quán, merge/cascade có thể sinh kết quả FK hoặc SQL khác kỳ vọng.

### 14.5. Xung đột xóa child và sửa child

B xóa Section#10, A giữ detached Section#10 rồi merge. Kết quả có thể là optimistic conflict, missing row hoặc lỗi provider/constraint tùy mapping và thời điểm. Không khẳng định mọi trường hợp đều bị báo bằng cùng một exception chính xác.

### 14.6. Merge graph quá rộng

Một Article có hàng nghìn Sections/Comments. Merge toàn graph có thể:
- Copy nhiều Java objects;
- Kéo theo N+1/selects;
- Tăng chi phí flush;
- Tạo xung đột không liên quan với field đang sửa;
- Kích hoạt cascade ngoài ý muốn.

Đổi title thì thường chỉ cần load managed Article và gọi rename, không cần merge tất cả detached relationships.

## 15. Entity bị xóa giữa lúc đọc và merge

### 15.1. Merge không phải UPSERT tùy ý

Nếu A tải Article#42 rồi detached, B DELETE row ấy và commit, A merge bản cũ. Không thiết kế rằng merge chắc chắn **tạo lại Article#42** như một SQL UPSERT.

Với entity có identity/version, việc merge stale row đã bị xóa cần được coi là concurrency/missing-row scenario; exception cụ thể và thời điểm phát hiện có thể khác provider.

### 15.2. Hợp đồng API

Sau rollback, server có thể kiểm tra lại:
- Article đã bị xóa → 404/410 theo API policy;
- Article vẫn còn nhưng version đổi → 409/412;
- Người dùng không còn quyền → 403 hoặc 404 che thông tin theo security policy.

Nếu cho phép khôi phục nội dung A thành **bài viết mới**, phải dùng create command với ID/version mới, không dựa vào merge để hồi sinh row đã bị xóa.

### 15.3. Soft-delete

Một Article có deletedAt không null vẫn có row. @Version có thể tăng khi soft delete bằng managed update, nhưng business service vẫn phải từ chối sửa bài đã xóa nếu đó là policy. Khớp version không có nghĩa operation được phép.

## 16. Hướng phục hồi xung đột cho người dùng

### 16.1. Giữ lại draft

Khi optimistic conflict:
- Không trả HTTP success;
- Không xóa nội dung A đang nhập;
- Không ép ghi đè bản B;
- Cho A xem version mới và quyết định.

### 16.2. Response ví dụ

~~~json
{
  "code": "ARTICLE_VERSION_CONFLICT",
  "message": "Bài viết đã thay đổi kể từ khi bạn mở biểu mẫu.",
  "expectedVersion": 7,
  "currentVersion": 8,
  "resolution": "RELOAD_AND_REVIEW"
}
~~~

Chỉ lộ currentVersion/nội dung mới nếu user có quyền đọc.

### 16.3. Sơ đồ xử lý

~~~text
Client gửi draft version=7
         |
         v
Server phát hiện database version=8
         |
         v
Rollback, HTTP 409/412
         |
         v
Client giữ draft và tải bản hiện hành
         |
         +-- So sánh local với remote
         +-- User chọn thay đổi cần giữ
         |
         v
Gửi command mới expectedVersion=8
         |
         v
Server kiểm tra version và ghi nếu chưa có writer thứ ba
~~~

### 16.4. Merge ba chiều

Đối với text editor, có thể so sánh:
- **Base:** snapshot ban đầu;
- **Local:** draft của A;
- **Remote:** bản DB mới.

Nếu Local và Remote sửa khác đoạn có thể đề xuất hợp nhất, nhưng nếu cùng sửa một đoạn phải có policy. Sau khi resolve, vẫn dùng expectedVersion của **Remote** và để DB optimistic check bảo vệ writer tiếp theo.

### 16.5. Retry phải đọc lại state

Không retry y nguyên một detached source stale trong transaction đã lỗi. Chỉ retry một biến đổi idempotent khi:

- Rollback, tạo transaction mới;
- Đọc state hiện hành;
- Xác nhận biến đổi vẫn phù hợp nghiệp vụ;
- Áp lại intent;
- Có giới hạn retries và xử lý khi conflict tiếp.

## 17. So sánh merge detached với cập nhật managed entity

Không phải quy trình nào cũng nên đi qua EntityManager.merge. Đánh giá xung đột còn cần đánh giá **đường ghi nào phù hợp**.

| Tiêu chí | Merge detached | Load managed rồi thay đổi |
|---|---|---|
| Nguồn dữ liệu | Detached entity snapshot | DTO command / domain inputs |
| Đối tượng được dirty checking | Managed result của merge | Managed entity vừa load |
| Client expectedVersion | Có sẵn trong detached nếu snapshot hợp lệ | Phải gửi và kiểm tra rõ |
| Khả năng ghi đè fields không đổi | Cao nếu detached snapshot stale và thiếu conflict policy | Thấp hơn nếu chỉ sửa field được yêu cầu |
| Áp domain methods | Chỉ nếu caller chủ động gọi | Tự nhiên khi service gọi method |
| Cascade graph | Có thể lan sang children theo mapping | Service kiểm soát association operations |
| JPA version checking | Có khi versioned và được quản lý đúng | Có khi update entity versioned |
| Trường hợp phù hợp | Đồng bộ một detached graph thật sự cần thiết | REST command, partial update, workflow nghiệp vụ |
| Debugging | Phải hiểu snapshot và cascade | Dễ theo dõi intent từng thao tác |

### 17.1. Khi merge có lý do chính đáng

Merge hợp lý khi:
- Client/logic nội bộ thực sự quản lý một detached entity graph có identity/version;
- Tất cả properties được tải và cập nhật theo contract rõ;
- Cascade được thiết kế cho graph đó;
- Xung đột được xử lý ở transaction boundary;
- API không nhận entity tùy ý thiếu fields như một partial DTO.

Ví dụ các workflow disconnected desktop clients hoặc một số batch ingestion có snapshot rõ ràng.

### 17.2. Khi managed update dễ an toàn hơn

Với request “đổi title Article#42”, service có thể:
1. Kiểm tra quyền và expectedVersion;
2. Load managed Article;
3. Gọi rename;
4. Để @Version check tại flush/commit.

Không phải merge toàn entity chỉ để cập nhật một String.

### 17.3. Khi không cần load entity

Nếu thao tác rất đơn giản và có expectedVersion, có thể dùng **conditional bulk update**:

~~~java
int changed = em.createQuery(
    """
    update Article a
    set a.title = :title,
        a.modifiedAt = :now,
        a.version = a.version + 1
    where a.id = :id
      and a.version = :expectedVersion
    """
)
.setParameter("title", title)
.setParameter("now", now)
.setParameter("id", id)
.setParameter("expectedVersion", expectedVersion)
.executeUpdate();
~~~

Điều kiện version giúp một thao tác **compare-and-set** ở database với numeric @Version. Nếu changed=0, cần xác định có phải ID không tồn tại, không có quyền, hay version đã đổi.

**Lưu ý:** đây là JPQL bulk DML, không tự gọi @PreUpdate, auditing listeners, domain methods hoặc cập nhật managed Article trong persistence context. Không cho rằng nó tương đương merge hoặc managed dirty checking.

### 17.4. Dùng một kiểu thay đổi nhất quán

Một aggregate vừa được cập nhật bằng managed entity, vừa có nhiều repository @Modifying, native SQL và procedure có thể tạo xung đột khó chẩn đoán nếu version policy không thống nhất.

Nên xác định rõ:
- Đường ghi chính;
- Những trường hợp được phép bulk/native;
- Version increment/check ở mỗi đường;
- Cache/context invalidation;
- Audit/event logic;
- Transaction boundary.

## 18. Concurrency dưới nhiều tình huống

### 18.1. Hai editors cùng phiên bản

~~~text
DB V=10
A đọc V=10
B đọc V=10
B commit → V=11
A merge V=10 → conflict
~~~

Đây là trường hợp điển hình của optimistic locking.

### 18.2. A đã giữ detached nhưng không sửa

A đọc V=10 rồi đóng context, B commit V=11. A merge V=10 nhưng không tự sửa field nào. Cách provider xử lý merge/phiên bản stale vẫn phải tuân thủ version consistency; **không dựa vào việc object “không dirty” để bỏ qua kiểm tra**. Nếu ứng dụng không có yêu cầu thay đổi, đừng merge chỉ để xác nhận “đã đọc”.

### 18.3. Hai writers sửa cùng lúc sau khi đọc hiện hành

A và B đều load V=10 trong những transactions khác nhau, rồi cùng sửa. Một transaction commit đầu tiên, transaction còn lại phải được kiểm tra và có thể xung đột khi flush/commit.

Điều này có thể xảy ra **ngay cả khi không có detached entity**, vì optimistic locking cũng bảo vệ managed updates. Detached merge là một workflow phổ biến để tạo stale snapshot, không phải nơi duy nhất có conflict.

### 18.4. Entity bị xóa

A đọc V=10; B xóa row và commit; A merge. Kết quả không phải một cập nhật hợp lệ như thường. Kiểm tra row existence/version, rollback và phân loại missing resource theo API policy.

### 18.5. Bulk UPDATE không tăng version

A giữ V=10, B dùng bulk JPQL đặt title mới mà không tăng version. A sau đó merge vẫn V=10. Nếu provider không có tín hiệu version đã thay đổi, nguy cơ lost update tồn tại. Đây là **lỗ hổng chính sách versioning**, không phải lỗi cấu hình @Version của A.

### 18.6. Native SQL tăng version nhưng JPA managed stale

B dùng native SQL tăng version, A đã managed Article V=10 trong context. Khi A flush thay đổi, version predicate cũ không khớp và optimistic conflict có thể xuất hiện. Nếu A chỉ gọi find cùng ID, identity map có thể vẫn trả object cũ; cần refresh/clear hoặc context mới khi có yêu cầu đọc lại.

### 18.7. Hai requests đến cùng một tenant/account

@Version bảo vệ row, nhưng vẫn cần tenant predicate/authorization. Một client có expectedVersion đúng của Article người khác **không tự có quyền sửa** Article ấy. Đừng tiết lộ dữ liệu qua 409 response trước khi kiểm tra quyền.

### 18.8. Transaction isolation và race

Isolation level có thể ảnh hưởng snapshot visibility và thời điểm DB phát hiện xung đột. @Version là một cơ chế cấp ORM; deadlock/serialization failures ở DB là loại lỗi khác có thể cùng xảy ra. Cần policy retry riêng cho những lỗi transient có thể retry và những optimistic conflicts cần user decision.

## 19. Kiểm thử tích hợp với hai EntityManagers

Không thể chứng minh optimistic locking bằng việc mock EntityManager.merge đơn thuần. Cần DB/provider thật hoặc môi trường tương thích, có **hai persistence contexts độc lập** và những transactions commit theo thứ tự có kiểm soát.

### 19.1. Fixture có version

~~~java
Article newArticle =
    new Article("Intro", "Old body", Instant.now());

EntityManager fixtureEm = emf.createEntityManager();

Long articleId;
try {
    fixtureEm.getTransaction().begin();
    fixtureEm.persist(newArticle);
    fixtureEm.getTransaction().commit();
    articleId = newArticle.getId();
} finally {
    fixtureEm.close();
}
~~~

Ghi nhận originalVersion bằng query sau commit thay vì hard-code 0 hoặc 1.

### 19.2. Test stale detached merge

~~~java
@Test
void staleDetachedMergeMustFail() {
    // A đọc rồi detached.
    EntityManager reader = emf.createEntityManager();
    Article stale;
    try {
        reader.getTransaction().begin();
        stale = reader.find(Article.class, articleId);
        reader.getTransaction().commit();
    } finally {
        reader.close();
    }

    Long oldVersion = stale.getVersion();

    // B cập nhật và commit trước khi A merge.
    EntityManager writerB = emf.createEntityManager();
    try {
        writerB.getTransaction().begin();

        Article current =
            writerB.find(Article.class, articleId);
        current.rename("Title from B", Instant.now());

        writerB.getTransaction().commit();
    } finally {
        writerB.close();
    }

    stale.rewriteBody("Body from A", Instant.now());

    // A cố lưu snapshot cũ trong transaction khác.
    EntityManager writerA = emf.createEntityManager();
    try {
        assertThrows(
            PersistenceException.class,
            () -> {
                writerA.getTransaction().begin();
                writerA.merge(stale);
                writerA.flush();
                writerA.getTransaction().commit();
            }
        );
    } finally {
        if (writerA.getTransaction().isActive()) {
            writerA.getTransaction().rollback();
        }
        writerA.close();
    }

    // Kiểm tra bản đã commit của B còn nguyên.
    EntityManager verify = emf.createEntityManager();
    try {
        Article db = verify.find(Article.class, articleId);

        assertEquals("Title from B", db.getTitle());
        assertEquals("Old body", db.getBody());
        assertTrue(db.getVersion() > oldVersion);
    } finally {
        verify.close();
    }
}
~~~

Ví dụ giả định imports JUnit 5, jakarta.persistence.PersistenceException, EntityManagerFactory, Instant và fixture có articleId. Với raw JPA, lỗi có thể là OptimisticLockException hoặc RollbackException có cause; cả hai là những PersistenceException thường gặp. Nếu framework chuyển exception sang Spring DataAccessException, assertion cần điều chỉnh theo tầng API và kiểm tra cause.

**Đây là tình huống stale snapshot có thứ tự commit xác định**, không cần hai threads chạy đồng thời để kiểm chứng quy tắc version.

### 19.3. Test merge trả managed instance

~~~java
@Test
void mergeReturnsManagedCopyNotSource() {
    Article detached = readAndDetachArticle(articleId);

    EntityManager em = emf.createEntityManager();
    try {
        em.getTransaction().begin();

        Article managed = em.merge(detached);

        assertNotSame(detached, managed);
        assertFalse(em.contains(detached));
        assertTrue(em.contains(managed));

        em.getTransaction().rollback();
    } finally {
        em.close();
    }
}
~~~

**readAndDetachArticle** là helper fixture cần triển khai. Test này kiểm tra reference identity và management, không chứng minh optimistic conflict.

### 19.4. Test expectedVersion của REST command

Quy trình:
1. GET ArticleView version=V.
2. Transaction B update Article và commit V+1.
3. Client gửi RenameArticleRequest(expectedVersion=V).
4. Service load current V+1 và ném ArticleConflictException.
5. Assert không ghi title của request stale.
6. Gửi request mới với V+1 và title hợp lệ; assert commit.

Test cả lỗi precondition của ứng dụng và SQL @Version check khi concurrent writer xuất hiện sau lúc service load.

### 19.5. Test race sau khi server kiểm tra version

Mô phỏng:
- Transaction A load current V, check expectedVersion=V;
- Transaction B load V, update/commit thành V+1;
- A update/flush từ snapshot V;
- Kỳ vọng optimistic conflict dù Java check của A trước đó đã thành công.

Dùng hai EntityManagers/transactions độc lập; có thể điều phối bằng CountDownLatch/Barrier trong test multi-thread hoặc kiểm soát thứ tự thao tác trong integration test. **Không dùng cùng EntityManager đồng thời trên hai threads.**

### 19.6. Test stale child graph

Tạo Article có ArticleSection versioned:
1. A load article+sections rồi detached;
2. B đổi một section và commit;
3. A đổi cùng section trên bản detached;
4. Merge root có CascadeType.MERGE;
5. Assert conflict ở child hoặc transaction bị rollback theo provider;
6. Kiểm tra bản B không bị ghi đè.

Test với mapping và cascade đúng mục đích, không giả định root version luôn tăng do child edit.

### 19.7. Test thất bại mà transaction vẫn rollback toàn bộ

Trong một transaction A:
- Update Article#1;
- Merge stale Article#2;
- Flush có lỗi;
- Rollback.

Sau đó transaction kiểm tra mới phải thấy Article#1 chưa giữ update của A nếu cả hai cùng transaction. Test này xác nhận atomicity, không chỉ exception.

### 19.8. Test bulk SQL không tăng version

Tạo Article V, thực hiện một bulk UPDATE title mà không tăng version, rồi đọc DB. Kiểm tra version còn V theo câu DML này. Thử stale snapshot merge và quan sát nguy cơ. Sau đó thay bulk UPDATE bằng CAS tăng version và xác nhận xung đột được phát hiện.

Đây là test quan trọng để chứng minh **khoảng trống của những writer không tuân thủ @Version**, không phải để khuyên bỏ qua version.

### 19.9. Test không được dựa vào cùng persistence context

Nếu A/B cùng dùng một EntityManager, identity map có thể trả một Java instance. Khi đó test không mô phỏng hai snapshots độc lập. Cần tối thiểu hai contexts/transactions và context mới để verify committed DB state.

### 19.10. Test trên database đúng loại

Một số provider/DB khác nhau về flush timing, JDBC exceptions, transaction isolation và mapping version. Test có thể chạy với H2 để học ý tưởng, nhưng nên xác minh các luồng concurrency quan trọng trên DB/driver giống production.

## 20. Troubleshooting: từ exception tới nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| OptimisticLockException ngay tại merge | Detached source stale | Rollback, reload current version |
| Lỗi chỉ xuất hiện ở flush/commit | SQL version check bị trì hoãn | Handle ở transaction boundary |
| HTTP trả 500 không rõ | Chưa map optimistic exception | 409/412 và conflict payload |
| saveAndFlush thành công nhưng commit lỗi | Flush không phải commit | Không báo success trước commit |
| Sau merge detached vẫn version cũ | Source không tự managed | Dùng managed result/current version |
| Sau merge sửa detached không lưu | Detached không dirty checking | Sửa managed result |
| Merge ghi đè title vừa sửa | Managed target nhận state từ detached | Tránh merge stale state vào cùng context |
| DTO thiếu body làm mất body | Dựng partial entity rồi merge | Load managed + patch fields rõ |
| Version client không được kiểm tra | Server load mới nhất rồi overwrite | ExpectedVersion/If-Match precondition |
| Xung đột dù sửa field khác nhau | Lock cấp row, không theo diff | Giải quyết ba chiều nếu cần |
| @Version không phát hiện native update | Writer không tăng version | Thống nhất tất cả write paths |
| Bulk JPQL sửa nhưng version không đổi | Bulk bypass ORM optimistic behavior | CAS/manual version hoặc managed update |
| Merge child gây conflict | Cascade MERGE qua detached child stale | Version/cascade policy rõ |
| Root version không đổi khi child sửa | Child có lifecycle/version riêng | Xác định aggregate concurrency boundary |
| Collection bị thay ngoài ý định | Snapshot cũ được merge quá rộng | DTO commands và xử lý membership rõ |
| Child bị xóa dù client không yêu cầu | OrphanRemoval + collection merge | Không coi absent như empty |
| Merge row đã bị xóa | Detached identity không còn DB row | Phân loại 404/410/conflict |
| Optimistic exception bị nuốt | Code catch rồi tiếp tục | Rollback, không trả success |
| Retry liên tục vẫn conflict | Dùng nguyên detached source stale | Reload + resolve trong transaction mới |
| Transaction B không thấy data fixture | Setup chưa commit/isolation | Fixture commit rõ |
| Test A/B cùng Java instance | Dùng cùng EntityManager | Hai contexts độc lập |
| Cả A và B commit dù muốn conflict | Version không mapping/driver ngoài ORM | Kiểm tra @Version và SQL |
| User mất draft khi conflict | Frontend xóa input khi HTTP 409 | Giữ local edits và hiển thị diff |
| HTTP trả current version ngoài quyền | Thiếu authorization | Check policy trước khi tiết lộ |
| Flush thất bại nhưng phần khác tưởng đã lưu | Nhầm flush với commit | Kiểm tra transaction rollback |

## 21. Bài tập thực hành

Các bài tập dựa trên entity **Article** có Long ID, Long @Version, title, body, modifiedAt và entity **ArticleSection** khi cần. Mục tiêu là **đánh giá được xung đột** trước khi viết code lưu dữ liệu, không chỉ ghi nhớ tên exception.

### Bài 1. Xác định trạng thái entity

Một Article được tải bằng EntityManager A. Sau đó A.close() và reference Article được giữ trong biến Java. Hãy cho biết:
- Article có còn managed không?
- Sửa title trên reference đó có tạo UPDATE không?
- Khi một EntityManager B mới muốn lưu sửa đổi, dùng API nào và cần chú ý phiên bản ra sao?

### Bài 2. Phân biệt source với return value

Cho:

~~~java
Article detached = ...;
Article result = em.merge(detached);
~~~

Giải thích:
- detached và result có chắc cùng reference không?
- em.contains(detached) và em.contains(result) thường trả gì?
- Nếu cần sửa tiếp sau merge, nên sửa object nào?
- Nếu detached.version=V, DB lên V+1 sau commit, detached.version có chắc cũng lên V+1 không?

### Bài 3. Phát hiện stale snapshot

Database Article#42 version=8. A đang giữ detached Article#42 version=7. A gọi merge. Lỗi có thể xuất hiện tại những thời điểm nào? Sau optimistic conflict, transaction của A phải xử lý thế nào?

### Bài 4. Vì sao flush không phải commit?

Code:

~~~java
Article managed = em.merge(detached);
em.flush();
sendEmail("Article saved");
~~~

Sau flush, transaction commit thất bại do constraint hoặc concurrency. Hãy phân tích sự không nhất quán giữa email và DB. Đề xuất outbox/after-commit policy.

### Bài 5. Hai field khác nhau vẫn xung đột

A sửa body, B sửa title cùng từ version=5. B commit version=6. A merge bản 5 và bị từ chối.

Giải thích tại sao @Version không tự nói rằng hai thay đổi có thể kết hợp an toàn. Hãy trình bày base/local/remote và quy tắc merge ba chiều.

### Bài 6. Thiếu expectedVersion trên REST API

Client mở form khi DB version=5. B lưu và tăng lên version=6. Client gửi PATCH chỉ có title, server load managed Article version=6 rồi rename và commit.

Tại sao @Version có thể **không** phát hiện stale form trong trường hợp này? Hãy thêm expectedVersion hoặc If-Match.

### Bài 7. Version check ở Java vẫn có race

A load current version=6, check client expectedVersion=6 thành công. B commit version=7 trước khi A flush. Hãy chỉ ra cơ chế nào bảo vệ A tại UPDATE và vì sao so sánh version chỉ ở Java không đủ.

### Bài 8. Version của source detached

A merge một Article version=3 thành công, managed version sau commit là 4. A tái sử dụng detached source version=3 trong transaction sau.

Phân tích kết quả có thể xảy ra. Làm sao thiết kế client state để không gửi token cũ?

### Bài 9. DTO partial edit

Request JSON chỉ có title và expectedVersion, không có body. Một developer tạo Article body=null rồi gọi merge. Hãy phân tích rủi ro và viết service load managed entity rồi gọi rename.

### Bài 10. Phân biệt absent, null và empty string

API PATCH cho phép sửa body. Thiết kế semantics cho ba trường hợp:
- Body không xuất hiện;
- Body được gửi null;
- Body được gửi chuỗi rỗng.

Trình bày DTO/JSON Patch/field-mask thích hợp và cách bảo vệ @Version.

### Bài 11. Version không tăng khi writer ngoài ORM

Job B chạy:

~~~sql
UPDATE articles SET body = 'Job body' WHERE id = 42;
~~~

mà không tăng version. A giữ detached Article cùng version. Giải thích lost-update risk và sửa câu SQL theo CAS numeric version.

### Bài 12. Bulk JPQL UPDATE một row

Một câu:

~~~java
update Article a
set a.title = :title
where a.id = :id
~~~

có phải managed entity update chỉ vì WHERE id trỏ tới một row không? Hãy giải thích @Version, callbacks, persistence context staleness và cách thêm version predicate/increment nếu cần.

### Bài 13. Target managed đã được sửa trước merge

Trong một transaction:

~~~java
Article managed = em.find(Article.class, id);
managed.rename("Title X", now);
em.merge(detachedWithSameId);
~~~

Nếu detached có title "Old", có rủi ro gì? Vì sao @Version không nhất thiết tự phân xử hai thay đổi trong cùng context?

### Bài 14. Transaction rollback toàn bộ

A thay Article#1, sau đó merge stale Article#2 trong cùng transaction; Article#2 gây OptimisticLockException. Có được trả kết quả “Article#1 đã lưu thành công” không? Hãy thiết kế integration test mở transaction mới để xác minh DB.

### Bài 15. Spring Data saveAndFlush

Một service gọi:

~~~java
Article saved = repository.saveAndFlush(detached);
~~~

và nhận object. Điều đó có bảo đảm commit đã thành công không? Nếu conflict xuất hiện sau khi thân @Transactional method return, exception được xử lý ở tầng nào?

### Bài 16. JPA exceptions trong Spring

Phân biệt:
- jakarta.persistence.OptimisticLockException;
- jakarta.persistence.RollbackException;
- Spring ObjectOptimisticLockingFailureException;
- SQL deadlock/serialization failure.

Vì sao không nên bắt mọi RuntimeException rồi trả một HTTP 409 cố định?

### Bài 17. ETag và If-Match

Thiết kế GET Article#42 version=12 với ETag, PATCH gửi If-Match version=12. Nếu DB thành version=13, HTTP status nào thích hợp? Nếu không dùng HTTP preconditions mà dùng DTO expectedVersion, HTTP status nào thường phù hợp?

### Bài 18. Người dùng giữ draft khi conflict

A viết bài trong 30 phút, B đã lưu thay đổi khác. A nhấn Save và nhận 409. Hãy thiết kế UI:
- Giữ local draft;
- Tải current DB;
- Hiển thị diff;
- Cho user chọn phần muốn giữ;
- Gửi expectedVersion mới;
- Xử lý tiếp nếu lại có writer thứ ba.

### Bài 19. CascadeType.MERGE trên sections

Article có 5 Sections. A detached root và children version=4. B sửa Section#3 thành version=5. A merge root kèm cascade MERGE.

Xung đột có thể đến từ root hay child? Nếu child có @Version riêng nhưng root không tăng version khi child sửa, cần xem xét gì về aggregate boundary?

### Bài 20. Collection không được gửi

Một client chỉ đổi title và không gửi sections. Backend tạo entity có List sections rỗng rồi merge với orphanRemoval=true. Hãy giải thích rủi ro và đề xuất command DTO chỉ đổi title.

### Bài 21. LAZY chưa fetch khi merge

Một detached Article có quan hệ sections LAZY chưa được tải. Theo JPA, state LAZY unfetched phải được xử lý thế nào lúc merge? So sánh với sections đã được tải từ lâu hoặc collection bị code clear trước merge.

### Bài 22. Entity bị xóa

A tải Article version=10. B xóa Article và commit. A merge detached Article. Có nên tự INSERT lại Article từ source không? Hãy thiết kế API response và quy trình tạo bài mới có ID/version mới nếu cần khôi phục nội dung.

### Bài 23. Pessimistic vs optimistic

Một màn hình cho phép người dùng sửa bài trong 20 phút. Vì sao PESSIMISTIC_WRITE giữ transaction lâu là rủi ro? Optimistic lock phù hợp hơn thế nào? Trường hợp nào thực sự cần pessimistic lock ngắn hạn?

### Bài 24. Viết integration test deterministic

Tạo Article fixture. Dùng:
1. EntityManager A load version V rồi close.
2. EntityManager B update và commit V+1.
3. A sửa detached và merge qua EntityManager C.
4. Assert OptimisticLockException hoặc wrapper phù hợp tại merge/flush/commit.
5. Rollback C.
6. Context D đọc lại DB và assert state của B còn nguyên.

Nêu lý do không dùng cùng EntityManager cho A/B và không hard-code version ban đầu bằng 0.

### Bài 25. Test race sau Java precondition

Dùng hai transactions độc lập. A load V và pass expectedVersion. B commit V+1 trước flush của A. Thiết kế test chứng minh JPA @Version vẫn phát hiện lỗi dù Java version comparison của A đã đúng tại thời điểm đọc.

### Bài 26. Version token trên mobile offline

Một mobile app sửa Article khi không có mạng. Sau hai ngày, app gửi detached snapshot cũ. Hãy so sánh:
- Tự gọi merge và xử lý OptimisticLockException;
- Gửi patch command với expectedVersion và base snapshot;
- Hòa giải tự động các fields không xung đột;
- Yêu cầu user review những fields trùng.

Lưu ý về retry và không gửi last-write-wins mặc định.

### Bài 27. Native SQL và transaction boundaries

Có một writer ngoài ORM dùng stored procedure để đổi Article.body nhưng không tăng version. Hãy thiết kế contract versioning chung để merge detached từ JPA không bỏ lỡ cập nhật.

### Bài 28. Test stale section nhưng current root

A đọc Article root version=8 và Section version=3. B sửa Section thành version=4 mà không tăng root. A muốn sửa Section dựa trên version=3.

Nếu API chỉ so sánh root version=8, điều gì có thể bị bỏ qua? Đề xuất kiểm tra Section.version hoặc quy tắc force-increment root.

### Bài 29. Quyền trước khi báo currentVersion

User không có quyền đọc Article#42 nhưng gửi PATCH với expectedVersion cũ. API không nên trả title/currentVersion mới nếu quyền đã bị thu hồi. Hãy thiết kế order của authorization check, missing resource response và optimistic conflict response.

### Bài 30. Chọn đường cập nhật cho sáu nghiệp vụ

Chọn giữa **merge detached / managed update / conditional bulk UPDATE / pessimistic lock / event-driven command**:

1. Đổi một tiêu đề trong REST API.
2. Đồng bộ offline Article + Sections đã có version riêng.
3. Tăng bộ đếm xem bài viết.
4. Chuyển trạng thái phê duyệt khi còn PENDING.
5. Đổi nội dung một bản ghi trong transaction ngắn có contention cao.
6. Một workflow phê duyệt cần audit, transaction và domain events.

Với mỗi mục, giải thích:
- Version token;
- Có cần callbacks/domain methods không;
- Race khi commit;
- Cần giữ draft/resolve hay có thể retry;
- Persistence context có thể stale không.

## 22. Bảng tra cứu nhanh

| Mục đích | API / chiến lược |
|---|---|
| Khai báo version | @Version private Long version |
| Tải managed entity | em.find(Article.class, id) |
| Đưa managed entity sang detached | em.detach, em.clear hoặc close context |
| Hợp nhất detached | Article managed = em.merge(detached) |
| Kiểm tra managed | em.contains(entity) |
| Đồng bộ SQL sớm | em.flush() (không commit) |
| Hoàn tất transaction | commit hoặc rollback |
| Exception optimistic | OptimisticLockException hoặc wrapper |
| Spring Data lưu entity | repository.save(entity) |
| Spring Data flush sớm | repository.saveAndFlush(entity) |
| So sánh version client | expectedVersion == managed.getVersion() |
| Race sau khi check version | @Version SQL update predicate |
| Trả HTTP conflict | 409 khi version/domain conflict |
| Trả lỗi If-Match | 412 khi precondition không thỏa |
| Bảo vệ REST edit | DTO command + managed update |
| Muốn tự merge nội dung | Base/local/remote + conflict policy |
| Merge child graph | CascadeType.MERGE + child @Version nếu cần |
| Bỏ qua LAZY unfetched lúc merge | Theo semantics JPA |
| Cập nhật conditional native/JPQL | UPDATE WHERE id AND version + increment |
| Đọc lại state sau rollback | Transaction và EntityManager mới |
| Retry sau conflict | Reload + reapply intent + giới hạn |
| Xóa row cạnh tranh | Xử lý missing resource/conflict |
| Tối ưu concurrency test | Hai contexts độc lập + commit có thứ tự |
| Không mất audit khi conflict | Outbox/after commit |

### 22.1. Năm điều không nên nhầm

| Khái niệm A | Không đồng nghĩa với B |
|---|---|
| Merge | Reattach chính source object |
| Flush | Commit |
| @Version | Tự động hòa giải nội dung |
| Client expectedVersion check | Thay thế SQL version check khi có race |
| Source detached snapshot | DTO PATCH chỉ chứa changed fields |

## 23. Checklist đánh giá xung đột trước khi merge

Trước khi cho một detached entity đi qua EntityManager.merge, hãy trả lời:

1. **Entity này có @Version không?** Kiểu và mapping version có đúng?
2. **Detached source có version thật từ lúc đọc không?** Hay được dựng lại sai từ JSON?
3. **Nguồn dữ liệu đã detached bằng cách nào?** Context nào từng quản lý?
4. **Có writer khác đã commit phiên bản mới không?** Nếu có phải resolve?
5. **Biết rằng optimistic conflict có thể xuất hiện ở merge/flush/commit chưa?**
6. **Catch/exception translation có bao trọn transaction boundary không?**
7. **Có rollback transaction khi lỗi không?** Không cố ghi tiếp.
8. **Có hiểu merge trả managed target khác detached source không?**
9. **Có dùng managed result thay vì sửa detached sau merge không?**
10. **Có giữ lại version mới sau commit, không tái dùng source cũ không?**
11. **Có xung đột in-memory với managed target cùng ID không?**
12. **Có phân biệt full detached snapshot với partial DTO không?**
13. **Một field không gửi có bị hiểu thành NULL/empty không?**
14. **Nếu dùng PATCH, đã định nghĩa field-presence semantics chưa?**
15. **Có cần client expectedVersion/If-Match không?** Tránh stale form.
16. **Có dựa vào Java check mà quên SQL version check không?**
17. **Các writer native/bulk/procedure có tăng/check version đúng không?**
18. **Domain validators và authorization có áp trước lưu không?**
19. **Có cascade MERGE sang children không?** Child versions có đúng?
20. **Root version có thật sự bảo vệ những chỉnh sửa child cần bảo vệ không?**
21. **Collections có orphanRemoval không?** Có rủi ro xóa do snapshot cũ?
22. **LAZY attributes đã được tải hay chưa?** Không lẫn unfetched với null.
23. **Mỗi association owning/inverse đã đồng bộ chưa?**
24. **Nếu row bị xóa, có tránh xem merge như UPSERT không?**
25. **Response conflict có giữ bản nháp người dùng không?**
26. **Có tự động merge field-level mà không có base/local/remote không?**
27. **Retry có mở transaction mới và reload state không?**
28. **Có giới hạn retry, idempotency và rollback đúng không?**
29. **Có side effects được phát trước commit không?** Cần outbox/after-commit.
30. **Có integration tests với hai EntityManagers và DB mục tiêu không?**
31. **Có test trường hợp update bị xung đột ở commit, không chỉ merge không?**
32. **Có test external writer không tuân thủ version để phát hiện lỗ hổng không?**
33. **Có phân loại 404/403/409/412 để không lộ dữ liệu ngoài quyền không?**
34. **Có hiểu optimistic lock bảo vệ snapshot, không thay business invariants không?**

### 23.1. Cây quyết định thực tế

~~~text
Người dùng muốn lưu chỉnh sửa Article
              |
              v
Dữ liệu đến từ entity detached thật hay request DTO?
              |
       +------+------+
       |             |
       v             v
 Detached        Request DTO
 snapshot        partial/command
       |             |
       |             +-- Load managed Article
       |             +-- Validate permission
       |             +-- Check expectedVersion
       |             +-- Apply chỉ changed fields
       |             +-- Flush / commit
       |
       +-- Verify source ID/version
       +-- Kiểm soát cascade graph/children
       +-- em.merge(detached)
       +-- Dùng managed result
       +-- Flush / commit
              |
              v
    Có optimistic conflict?
       |
       +-- Không → Chỉ xác nhận thành công sau commit
       |
       +-- Có
             |
             +-- Rollback
             +-- Giữ client draft
             +-- Mở transaction mới để đọc current
             +-- Resolve bằng user/domain policy
             +-- Gửi expectedVersion mới
             +-- Commit lại nếu version vẫn phù hợp
~~~

## 24. Kết luận

**Đánh giá xung đột khi hợp nhất entity đã tách** bắt đầu bằng sự thật rằng **detached entity là snapshot của một thời điểm trước đây**, còn database có thể đã thay đổi sau đó. **@Version** giúp JPA phát hiện stale snapshots và ngăn nhiều kiểu lost update, nhưng không tự biết ý định từng field, không sửa dữ liệu nghiệp vụ và không buộc những writer bên ngoài ORM tuân thủ version.

Ba nguyên tắc quan trọng nhất:

1. **Merge không phải reattach source.** Source vẫn detached, managed result mới là đối tượng được theo dõi. Đừng tiếp tục sửa source rồi mong UPDATE.
2. **Xung đột có thể phát hiện tại merge, flush hoặc commit.** Hãy rollback transaction, phân loại lỗi ở transaction boundary, không trả thành công sớm và không retry cùng source stale.
3. **Thiết kế API với expectedVersion và changed fields rõ ràng.** Với HTTP forms/partial edits, load managed entity hiện tại, kiểm tra phiên bản từ client rồi gọi domain methods thường an toàn hơn merge một object dựng lại từ JSON.

Khi có collections/cascade MERGE, cần xem xét **version của children**, **root aggregate concurrency boundary**, **orphanRemoval** và trạng thái LAZY đã tải/chưa tải. Khi có native SQL, bulk DML, stored procedure hoặc writers khác, phải thống nhất **version checking/increment** ở mọi đường ghi.

~~~text
Detached Article(version=V)
        |
        v
merge(detached) → managed target
        |
        +-- DB current version = V?
        |        |
        |        +-- Có → Flush UPDATE với version guard
        |        |          |
        |        |          +-- Commit thành công → version mới
        |        |          +-- Writer chen vào → conflict
        |        |
        |        +-- Không → conflict
        |
        v
Rollback khi conflict
        |
        v
Reload + resolve + expectedVersion mới
~~~

**Mục tiêu cuối cùng không chỉ là “không để exception xảy ra”, mà là không để thay đổi của người này bị âm thầm ghi đè bởi một bản chỉnh sửa đã lỗi thời.** Xác định rõ snapshot, version, changed fields và transaction boundary là nền tảng để xây dựng workflow cập nhật JPA an toàn trong hệ thống có nhiều người dùng.







