# Chế độ chỉ đọc và những thay đổi thực sự được bỏ theo dõi

## 1. Câu hỏi cốt lõi: “read-only” có thật sự làm entity bất biến?

Trong Hibernate ORM, một entity có thể được nạp vào persistence context nhưng được đánh dấu **chỉ đọc** (*read-only*). Điều đó thường có nghĩa Hibernate **không dirty-check và không phát sinh SQL `UPDATE` từ những thay đổi của các thuộc tính đơn giản hoặc quan hệ đơn trị thuộc entity đó**. Tuy nhiên, không nên hiểu read-only là:

- Object Java trở nên bất biến, không thể gọi setter.
- Entity bị đưa ra khỏi persistence context.
- Mọi thao tác trên collection và association đều bị chặn.
- Entity không thể bị xóa, hoặc không thể thực hiện cascade.
- Transaction/database tự động cấm toàn bộ SQL ghi.

Đây là những hiểu lầm dễ tạo lỗi mất dữ liệu hoặc ghi dữ liệu ngoài ý muốn.

Ví dụ, một hệ thống tin tức tải bài viết để dựng trang:

```text
               Database
         articles(id=10, title="A", version=3)
                      │
                      │ Session.get(...)
                      ▼
              Persistence Context
         Article(id=10) [MANAGED, READ-ONLY]
                      │
           ┌──────────┴───────────┐
           │                      │
       article.rename("B")    article.addKeyword("ORM")
           │                      │
           ▼                      ▼
   Thay đổi scalar field     Thay đổi collection
   không được dirty-check    vẫn có thể được đồng bộ
   thành UPDATE article      vào collection table
           │                      │
           └──────────┬───────────┘
                      ▼
                flush/commit
        Không thể suy ra “không SQL ghi”
```

Tài liệu này giải thích các cơ chế read-only trong Hibernate, chúng tác động lên những thành phần nào của state, cách kết hợp với transaction và cache, cũng như cách thiết kế một luồng chỉ đọc thực sự an toàn.

## 2. Persistence context và dirty checking

Hibernate dùng `Session` (hoặc `EntityManager` qua Jakarta Persistence) để quản lý vòng đời entity. Trong một persistence context, Hibernate thường giữ một managed instance cho một entity type và identifier tương ứng, đồng thời theo dõi trạng thái của nó để đồng bộ với database.

Với entity mutable thông thường:

```text
Tải từ database:
  id=10, title="Tên cũ", category_id=5
        │
        ▼
  Managed Article
  Snapshot hoặc thông tin theo dõi thay đổi
        │
        ├── article.rename("Tên mới")
        └── article.changeCategory(otherCategory)
        │
        ▼
  Flush → xác định thuộc tính/association nào đã đổi
        │
        ▼
  SQL UPDATE articles ... WHERE id=10 ...
```

Với một entity **read-only** trong Hibernate, việc dirty-check các thuộc tính cơ bản và các association đơn trị có thể được bỏ qua; Hibernate không cần giữ đầy đủ state snapshot phục vụ cập nhật những thuộc tính đó. Mục đích là giảm công việc tracking cho các entity mà use case **chỉ định đọc**.

Phải phân biệt hai câu:

1. “Hibernate không theo dõi thay đổi của một phần trạng thái entity này để UPDATE.”
2. “Hibernate hoàn toàn không quản lý entity này nữa.”

Câu đầu mô tả read-only; câu thứ hai mô tả một entity **detached**. Entity read-only vẫn có identity trong persistence context, có thể tham gia lazy loading và được tham chiếu từ các entity khác trong session.

## 3. Những lớp “chỉ đọc” có thể xuất hiện

| Cơ chế | Phạm vi | Tác động chính | Không bảo đảm |
|---|---|---|---|
| `session.setReadOnly(entity, true)` | Một managed entity cụ thể | Bỏ dirty checking của những state được quy định cho read-only entity | Không chặn mọi collection change, cascade hoặc remove |
| `session.setDefaultReadOnly(true)` | Các entity được nạp vào session theo cơ chế áp dụng về sau | Mặc định read-only cho đối tượng được load trong phạm vi đó | Không tự đổi trạng thái entity đã managed từ trước |
| `query.setReadOnly(true)` | Các entity mới được load bởi truy vấn Hibernate đó | Chỉ đọc theo từng query | Không biến DTO thành entity, không ghi đè trạng thái entity đã tồn tại trong PC |
| `@Immutable` trên entity | Mapping entity Hibernate | Entity được coi là bất biến đối với dirty checking thông thường | Không phải ràng buộc database; không cấm native SQL |
| `@Immutable` trên collection | Mapping collection Hibernate | Cấm sửa collection đã được đánh dấu bất biến theo cơ chế Hibernate | Không phải giống `setReadOnly(entity,true)` |
| `@Column(updatable=false)` | Một cột được mapping | Hibernate không đưa cột đó vào SQL UPDATE thông thường | Entity và những cột khác vẫn có thể cập nhật |
| `@Transactional(readOnly=true)` | Transaction do framework quản lý | Hint/chính sách tối ưu cho transaction và ORM | Không phải tường lửa cấm mọi câu SQL ghi |
| `FlushMode.MANUAL` | Quy tắc auto-flush của session | Không tự flush ở nhiều thời điểm thông thường | Entity vẫn managed; gọi `flush()` tường minh vẫn có thể ghi |
| Database read-only user/role | Quyền và ràng buộc ở database | Ngăn thao tác ghi theo quyền thực tế | Không tự biến Java entity thành immutable |

Điều quan trọng là **phạm vi**. Một query read-only, một transaction read-only và một entity `@Immutable` có thể cùng xuất hiện, nhưng chúng bảo vệ những điều khác nhau.

## 4. Mô hình dữ liệu dùng xuyên suốt bài

Giả sử hệ thống quản lý bài viết. Mỗi bài thuộc một thể loại và có tập keyword:

```sql
CREATE TABLE categories (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE articles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category_id BIGINT NOT NULL REFERENCES categories(id),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE article_keywords (
    article_id BIGINT NOT NULL REFERENCES articles(id),
    keyword VARCHAR(80) NOT NULL,
    PRIMARY KEY (article_id, keyword)
);
```

Entity `Category`:

```java
package com.example.blog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "categories")
public class Category {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Category() {}

    public Category(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên thể loại không hợp lệ");
        }
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

Entity `Article`:

```java
package com.example.blog.domain;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

@Entity
@Table(name = "articles")
public class Article {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 255)
    private String title;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "category_id", nullable = false)
    private Category category;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
            name = "article_keywords",
            joinColumns = @JoinColumn(name = "article_id"))
    @Column(name = "keyword", nullable = false, length = 80)
    private Set<String> keywords = new HashSet<>();

    @Version
    private Long version;

    protected Article() {}

    public Article(String title, Category category) {
        if (title == null || title.isBlank() || category == null) {
            throw new IllegalArgumentException("Bài viết không hợp lệ");
        }
        this.title = title;
        this.category = category;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public Category getCategory() { return category; }
    public Long getVersion() { return version; }

    public Set<String> getKeywords() {
        return Collections.unmodifiableSet(keywords);
    }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề không hợp lệ");
        }
        this.title = newTitle;
    }

    public void changeCategory(Category category) {
        if (category == null) {
            throw new IllegalArgumentException("Thiếu thể loại");
        }
        this.category = category;
    }

    public void addKeyword(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            throw new IllegalArgumentException("Keyword không hợp lệ");
        }
        keywords.add(keyword.trim());
    }

    public void removeKeyword(String keyword) {
        keywords.remove(keyword);
    }
}
```

`Article.title` là scalar property. `Article.category` là association **đơn trị** `@ManyToOne`, trong đó `articles.category_id` là cột FK phía Article sở hữu. `Article.keywords` là một **persistent collection** có collection table riêng. Ba loại state này giúp nhìn rõ những thay đổi bị bỏ theo dõi khi Article là read-only và những thay đổi có thể vẫn được Hibernate xử lý.

Các ví dụ giả định database đã có bản ghi Article và Category. Khi ví dụ sử dụng `SessionFactory`, Hibernate được cấu hình và transaction được quản lý đúng vòng đời.

## 5. Read-only theo từng entity: Session.setReadOnly()

Hibernate cung cấp API riêng:

```java
session.setReadOnly(article, true);
```

Trong đó `article` phải là instance đang ở trạng thái phù hợp để session quản lý. Có thể xem tình trạng bằng `session.isReadOnly(article)`:

```java
import org.hibernate.Session;
import org.hibernate.Transaction;

try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        Article article = session.get(Article.class, 10L);
        if (article == null) {
            throw new IllegalArgumentException("Không tìm thấy bài viết");
        }

        session.setReadOnly(article, true);
        System.out.println(session.contains(article));   // true
        System.out.println(session.isReadOnly(article)); // true

        article.rename("Tiêu đề chỉ thay đổi trong memory");

        session.flush();
        tx.commit();
    } catch (RuntimeException | Error error) {
        if (tx.isActive()) {
            try {
                tx.rollback();
            } catch (RuntimeException rollbackError) {
                error.addSuppressed(rollbackError);
            }
        }
        throw error;
    }
}
```

Trong trường hợp đơn giản chỉ đổi `title` **sau khi** đánh dấu read-only, Hibernate không tạo `UPDATE articles SET title = ...` từ dirty checking của Article. Nhưng lời gọi `rename()` vẫn đổi Java field; `article.getTitle()` ngay sau đó có thể trả về tên mới trong memory.

Điều này tạo hai góc nhìn:

```text
Database title  = "A"
Managed Article [read-only]
    article.rename("B")
        │
        ├── Java field title = "B"
        ├── Hibernate không dirty-check title thành UPDATE
        └── Database vẫn có title = "A"
```

**Read-only không hủy khả năng sửa state Java; nó thay đổi cách Hibernate đồng bộ một số state ấy.** Vì vậy hạn chế gọi method thay đổi trạng thái trên entity được đánh dấu read-only, ngay cả khi bạn tin rằng SQL UPDATE sẽ không xảy ra. Dữ liệu trong memory có thể gây hiểu nhầm cho phần còn lại của transaction.

### 5.1. Read-only vẫn là managed

```java
Article article = session.get(Article.class, 10L);
session.setReadOnly(article, true);

Article again = session.get(Article.class, 10L);
System.out.println(article == again); // true trong cùng PC
```

Hibernate vẫn giữ identity map cho Article. Đây không phải `session.evict(article)` hay `entityManager.detach(article)`. Entity read-only vẫn có thể tham gia quan hệ, được truy vấn lại trong cùng persistence context và có lazy association nếu session còn mở.

### 5.2. Phạm vi một instance

```java
Article a = session.get(Article.class, 10L);
Article b = session.get(Article.class, 11L);

session.setReadOnly(a, true);

System.out.println(session.isReadOnly(a)); // true
System.out.println(session.isReadOnly(b)); // thường false
```

Việc đánh dấu `a` không khiến mọi Article khác trong session read-only. Nếu mặc định session đang ở chế độ modifiable, entity `b` vẫn được dirty-check bình thường.

## 6. Chính xác các thay đổi scalar nào bị bỏ theo dõi?

Đối với **read-only entity** theo semantics Hibernate, các thay đổi thông thường của:

- Các thuộc tính đơn giản như `String`, `int`, `boolean`, `BigDecimal`, `LocalDate`.
- Các trường basic thuộc một embeddable hoặc component được ánh xạ như state của entity.
- Các association **đơn trị** (*single-ended associations*) như `@ManyToOne` hoặc `@OneToOne` có thể cập nhật.

thường không được Hibernate dirty-check để phát sinh SQL `UPDATE` trên hàng của chính read-only entity.

Ví dụ:

```java
Article article = session.get(Article.class, articleId);
Category other = session.get(Category.class, otherCategoryId);

session.setReadOnly(article, true);

article.rename("Tên đổi trong memory");
article.changeCategory(other);

session.flush();
// Không có UPDATE articles cho các thay đổi title/category_id
// được thực hiện sau khi Article thành read-only.
```

Hậu quả có thể khá khó nhận ra: code nhìn thấy `article.getCategory() == other` nhưng database vẫn giữ `category_id` cũ. Thao tác `refresh()` hoặc load trong persistence context khác có thể cho giá trị khác với object đang giữ.

### 6.1. Embeddable là state hay entity độc lập?

Một `@Embeddable` như `Money` hoặc `Address` thường được lưu như một phần thuộc tính của owner. Nếu owner read-only, sửa các field được ánh xạ của component cũng không tự biến thành UPDATE của owner thông qua dirty checking thông thường.

Ngược lại, một entity `Address @Entity` được tham chiếu bằng `@ManyToOne` có identity và trạng thái read-only **riêng**. Nếu Article read-only nhưng Address/Category vẫn mutable và managed, sửa field trên entity liên quan có thể tạo UPDATE cho **hàng liên quan**.

```java
session.setReadOnly(article, true);

Category category = article.getCategory();
// category không tự read-only chỉ vì article read-only.
// Nếu Category có method rename() và còn managed/modifiable,
// việc gọi method ấy có thể cập nhật bảng categories.
```

Không đánh đồng read-only của owner với việc “đóng băng toàn bộ object graph”.

### 6.2. Field không được phép thay bằng business rule

Chế độ read-only không có chức năng kiểm tra invariant nghiệp vụ. Nếu có field `approvedAt` hoặc `status` chỉ được sửa qua một quy trình đặc biệt, hãy thiết kế API domain và authorization phù hợp; đừng dựa vào read-only flag của một lần query để bảo đảm điều đó trên mọi đường ghi.

## 7. Collection vẫn có thể được Hibernate đồng bộ

Đây là giới hạn quan trọng nhất của read-only entity.

Hibernate phân biệt trạng thái scalar/to-one của entity và trạng thái **collection được ánh xạ**. Một entity read-only không đồng nghĩa collection của nó cũng bất biến. Thay đổi collection có thể được Hibernate phát hiện và ghi vào database; tùy mapping, việc collection trở thành dirty còn có thể ảnh hưởng tới version của entity owner.

Ví dụ:

```java
Article article = session.get(Article.class, 10L);
session.setReadOnly(article, true);

article.rename("Đổi tiêu đề nhưng không muốn ghi");
article.addKeyword("hibernate");

session.flush();
```

Với mapping `@ElementCollection Set<String> keywords` trong bài:

```text
Scalar state:
  Article.title = "Đổi tiêu đề..." trong Java
  → Không phải UPDATE title do dirty checking read-only.

Collection state:
  Article.keywords thêm "hibernate"
  → Có thể tạo INSERT vào article_keywords.
  → Có thể thay đổi version của Article theo semantics collection/version.
```

Kết quả SQL chính xác còn phụ thuộc snapshot, collection type, state trước đó và cách Hibernate quản lý version. Điều quan trọng không đổi: **không được dùng `setReadOnly(article,true)` làm cam kết rằng mọi thao tác lên Article graph đều không thể phát sinh SQL ghi**.

### 7.1. Collection không được quản lý giống scalar property

Một read-only entity có thể được giảm chi phí snapshot/dirty checking đối với basic fields và single-ended associations, nhưng Hibernate vẫn quản lý persistent collection thông qua collection wrapper, collection entries, row keys và các kế hoạch đồng bộ quan hệ.

Với:

```java
@ElementCollection(fetch = FetchType.LAZY)
private Set<String> keywords = new HashSet<>();
```

Hibernate có thể theo dõi việc thêm/xóa giá trị trong collection table. Với:

```java
@OneToMany(mappedBy = "article", cascade = CascadeType.PERSIST)
private List<Comment> comments = new ArrayList<>();
```

thao tác thêm con mới có thể làm phát sinh `INSERT` cho Comment nếu phía sở hữu FK được thiết lập đúng và cascade/persist phù hợp. Nếu `Comment` là managed và mutable, việc sửa `comment.body` vẫn là thay đổi của Comment, không phải scalar state của Article.

### 7.2. Hai chiều không có nghĩa chỉ sửa phía inverse là đủ

Giả sử:

```java
@OneToMany(mappedBy = "article")
private List<Comment> comments = new ArrayList<>();
```

và phía Comment có:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "article_id")
private Article article;
```

Trong quan hệ hai chiều, `Comment.article` là phía sở hữu FK. Chỉ thêm `comment` vào `article.comments` phía inverse có thể không ghi FK đúng. Helper domain cần đồng bộ cả hai phía, và việc Comment mới được persist phải được quyết định rõ.

Đừng dùng read-only ở Article để suy luận rằng thêm/xóa association chắc chắn sẽ bị bỏ qua; đồng thời đừng dùng collection wrapper như cách né quy tắc owning side của JPA.

## 8. Version của read-only entity có luôn đứng yên không?

Không nhất thiết.

Nếu read-only entity chỉ bị đổi scalar field hoặc một updatable single-ended association, Hibernate không dirty-check những thay đổi ấy để UPDATE, nên bản thân những thay đổi đó không làm tăng version theo cơ chế thông thường.

Tuy nhiên, nếu một **persistent collection** thuộc entity read-only trở nên dirty và mapping yêu cầu version đồng bộ với thay đổi collection, Hibernate có thể tăng version của owner. Điều này không mâu thuẫn với read-only: Hibernate đang xử lý **thay đổi collection**, không phải update scalar state đã được bỏ dirty checking.

| Thao tác trên `Article` read-only | Kết quả điển hình |
|---|---|
| `article.rename("B")` | Không UPDATE title; không tăng version chỉ vì title đổi |
| `article.changeCategory(other)` | Không UPDATE FK theo scalar/to-one dirty checking |
| `article.addKeyword("ORM")` | Collection table có thể INSERT; version của owner có thể thay đổi |
| Sửa field của `Category` managed khác | UPDATE Category có thể xảy ra; Article read-only không bảo vệ Category |
| `session.remove(article)` / `em.remove(article)` | Remove vẫn có thể xóa entity; read-only không cấm |
| Bulk JPQL/native SQL update Article | Không được chặn bởi read-only flag theo session |

Hành vi version của collection còn tùy phía sở hữu, type của collection, `@Version`, mapping và phiên bản Hibernate. Không dựa vào bất kỳ con số version cụ thể nào trong ví dụ mà không kiểm chứng configuration thực tế. Nếu application dùng version của parent để bảo vệ tính nhất quán của child graph, cần thiết kế protocol concurrency rõ ràng.

## 9. Cascade và remove không bị vô hiệu hóa bởi read-only

Một entity read-only vẫn là managed entity. Hibernate vẫn có thể thực hiện các cascade operations theo mapping và lịch trình lifecycle.

Ví dụ quan hệ:

```java
@OneToMany(
        mappedBy = "article",
        cascade = {CascadeType.PERSIST, CascadeType.REMOVE},
        orphanRemoval = true)
private List<Comment> comments = new ArrayList<>();
```

Ngay cả khi Article được đánh dấu read-only theo session, điều đó **không tự tắt** cascade persist/remove hoặc orphan removal khi code thay đổi graph theo một operation hợp lệ. Read-only không phải công cụ để bảo vệ các entity liên quan khỏi việc bị xóa.

Một câu lệnh:

```java
Article article = session.get(Article.class, 10L);
session.setReadOnly(article, true);

session.remove(article);
```

vẫn là yêu cầu xóa Article. Nó không bị Hibernate từ chối chỉ bởi vì Article là read-only cho dirty checking. Việc xóa thành công hay không còn phụ thuộc FK, cascades, database constraints và trạng thái transaction.

### 9.1. Cách bảo đảm “không thể xóa”

Nếu domain quy định bài viết đã phát hành không được xóa, cần bảo vệ bằng domain service, authorization, trạng thái, FK hoặc ràng buộc database tương ứng. Read-only entity không tương đương quyền truy cập database `SELECT`-only và không thay thế access control.

### 9.2. CascadeType.ALL cần hiểu trọn ý nghĩa

Đặt `cascade = CascadeType.ALL` cho association không chỉ ảnh hưởng tới persist hay merge; nó bao gồm remove, refresh, detach. Với association tới entity dùng chung như `Category`, đặt cascade remove bừa bãi có thể cố xóa Category khi xóa Article. Read-only flag không làm tình huống đó an toàn.

## 10. Session.setDefaultReadOnly(true): mặc định cho entity được load

Nếu một use case đọc nhiều entity mà không có kế hoạch cập nhật chúng, Hibernate có thể thiết lập mặc định read-only trên session:

```java
session.setDefaultReadOnly(true);

Article a = session.get(Article.class, 10L);
Article b = session.get(Article.class, 11L);

System.out.println(session.isReadOnly(a)); // true
System.out.println(session.isReadOnly(b)); // true
```

Điều này phù hợp với những batch query chuyên đọc nhiều managed entities. Tuy nhiên, nó có **giới hạn thời điểm**:

- Mặc định read-only chủ yếu áp dụng cho các entity được tải qua những đường load phù hợp **sau** khi thiết lập.
- Nó **không tự chuyển** mọi entity đã có trong persistence context thành read-only.
- Nó không thay đổi semantics của các thao tác tường minh như `persist()`, `remove()` và cascade.
- Nó không làm persistence context biến mất; entity vừa load vẫn có identity, associations và lifecycle managed.

### 10.1. Entity đã managed trước đó giữ trạng thái riêng

```java
Article earlier = session.get(Article.class, 10L);
// Giả sử earlier đang modifiable.

session.setDefaultReadOnly(true);

Article same = session.get(Article.class, 10L);
Article later = session.get(Article.class, 11L);

System.out.println(earlier == same);            // true
System.out.println(session.isReadOnly(earlier)); // vẫn false
System.out.println(session.isReadOnly(later));   // true
```

Khi `get()` trả lại object đã managed, đổi session default không ghi đè trạng thái read-only/modifiable của instance ấy. Nếu cần đổi một managed entity có sẵn, dùng `session.setReadOnly(entity, true)` tường minh.

### 10.2. Phục hồi session default sau khi đọc

Một session có thể được tái sử dụng trong nhiều thao tác thuộc cùng đơn vị công việc. Nếu một helper tùy tiện bật default read-only mà không trả lại, code sau đó có thể tải thêm entity tưởng là modifiable nhưng thực tế read-only.

```java
boolean previous = session.isDefaultReadOnly();
try {
    session.setDefaultReadOnly(true);

    List<Article> articles = session
            .createQuery(
                    "select a from Article a order by a.id",
                    Article.class)
            .setMaxResults(100)
            .getResultList();

    // Chỉ đọc dữ liệu trong phạm vi này.
    articles.forEach(a -> consume(a.getTitle()));
} finally {
    session.setDefaultReadOnly(previous);
}
```

Đoạn code giả định `consume(String)` là hàm của ứng dụng. Việc khôi phục default chỉ tác động đến **những lần nạp tương lai**; các instance đã được tạo read-only trong khối vẫn giữ flag riêng của chúng. Không tự động đổi chúng thành modifiable khi kết thúc `finally`.

Đối với read-only query trong phạm vi hẹp, cách đặt flag trên query thường rõ ý định hơn việc đổi default của cả session.

## 11. Query.setReadOnly(true): chỉ định theo truy vấn

Hibernate cung cấp phương thức `setReadOnly(true)` trên API `org.hibernate.query.Query`:

```java
import org.hibernate.Session;
import org.hibernate.query.Query;

Query<Article> query = session.createQuery(
        "select a from Article a " +
        "where a.title like :prefix " +
        "order by a.id",
        Article.class);

List<Article> rows = query
        .setParameter("prefix", "Hibernate%")
        .setReadOnly(true)
        .setMaxResults(50)
        .getResultList();
```

Các entity **mới được load** qua query có thể được Hibernate đánh dấu read-only theo flag này. Nhưng cần nhớ rằng persistence context vẫn là identity map.

### 11.1. Query read-only không ghi đè entity đã có trong PC

```java
Article earlier = session.get(Article.class, 10L);
// earlier đã managed, modifiable.

List<Article> articles = session.createQuery(
        "select a from Article a where a.id = :id",
        Article.class)
        .setParameter("id", 10L)
        .setReadOnly(true)
        .getResultList();

Article result = articles.get(0);

System.out.println(earlier == result);          // true
System.out.println(session.isReadOnly(result)); // vẫn là false
```

Nếu query trả về một managed instance đã tồn tại, flag read-only của query không tự đổi trạng thái instance đó. Điều này đặc biệt quan trọng khi một transaction thực hiện nhiều truy vấn, vì thứ tự nạp entity có thể quyết định flag áp dụng cho từng instance.

### 11.2. Projection không phải entity read-only

```java
public record ArticleListItem(Long id, String title) {}
```

```java
List<ArticleListItem> items = session.createQuery(
        "select new com.example.blog.read.ArticleListItem(" +
        "  a.id, a.title" +
        ") from Article a order by a.id",
        ArticleListItem.class)
        .setMaxResults(50)
        .getResultList();
```

Ở đây `ArticleListItem` là một record DTO, không phải entity managed. Không cần đánh dấu nó read-only qua Hibernate query. Nó không tham gia dirty checking ngay từ đầu. Tên package trong JPQL constructor expression cần trùng với class DTO thực tế.

Nếu chỉ cần vài cột phục vụ UI/API, projection thường có hợp đồng rõ ràng và chi phí quản lý thấp hơn việc tải nhiều managed entities rồi bật read-only.

### 11.3. Query join fetch và association

Một query nạp Article cùng Category/collection có thể khởi tạo thêm những entity liên quan. Cách áp dụng read-only flag cho các entity được load trong fetch plan phụ thuộc thời điểm chúng xuất hiện trong PC và cơ chế load của Hibernate; entity liên quan **đã managed** trước đó không bị query đổi trạng thái. Không nên coi query read-only là thao tác chuyển cả graph đã tồn tại sang read-only.

Nếu cần chắc chắn một managed instance cụ thể không bị dirty-check, hãy thao tác flag tường minh với instance ấy; nếu yêu cầu bất biến xuyên suốt ứng dụng, xem xét `@Immutable` trên đúng mapping.

## 12. Chuyển từ read-only trở lại modifiable

Hibernate cho phép chuyển trạng thái của **mutable entity** đang managed:

```java
session.setReadOnly(article, true);
// ...
session.setReadOnly(article, false);
```

Nhưng có một hệ quả dễ bị bỏ sót: trong thời gian entity read-only, Hibernate không duy trì snapshot của các basic fields như với một entity modifiable thông thường. Khi chuyển trở lại modifiable, Hibernate có thể **coi trạng thái hiện tại của entity là trạng thái nền** để so sánh những thay đổi tiếp theo. Vì vậy những thay đổi đã thực hiện **trong lúc read-only** không tự được ghi lại chỉ vì bạn bật chế độ ghi.

Ví dụ cần phân biệt:

```java
Article article = session.get(Article.class, articleId);

session.setReadOnly(article, true);
article.rename("B"); // Đổi Java field, bị bỏ dirty checking.

session.setReadOnly(article, false);
// Đừng giả định rename("B") vừa rồi sẽ được ghi.
```

Nếu code tiếp tục sửa một field **sau** khi chuyển lại modifiable, Hibernate có thể theo dõi thay đổi so với snapshot mới. Nhưng object có thể đang chứa state đã lệch database. Một luồng cập nhật an toàn nên **tải lại state nền đáng tin cậy** rồi mới áp dụng command.

### 12.1. Mẫu an toàn khi cần sửa sau giai đoạn đọc

```java
Article article = session.get(Article.class, articleId);
session.setReadOnly(article, true);

// ... xử lý đọc ...

session.setReadOnly(article, false);
session.refresh(article); // Đồng bộ lại state từ DB theo transaction.

article.rename("Tiêu đề cần cập nhật");
// flush/commit theo transaction; optimistic locking nếu có @Version.
```

`refresh()` làm state entity được nạp lại theo provider/transaction isolation, có thể **ghi đè thay đổi trong memory chưa flush**. Không đặt `refresh()` tùy tiện sau khi đã thực hiện những thay đổi hợp lệ khác. Trong code thực tế, còn có thể đơn giản hơn: dùng một transaction đọc thuần riêng, kết thúc nó, rồi bắt đầu transaction ghi và tải entity managed mới.

### 12.2. Không bật modifiable trên @Immutable entity

Nếu entity class được ánh xạ bằng `@Immutable`, mapping đó nói với Hibernate rằng entity vốn không dành cho cập nhật state. Không coi `setReadOnly(entity, false)` là cách “phá khóa” một immutable entity để Hibernate dirty-check bình thường. Nếu nghiệp vụ cần cập nhật dữ liệu, phải xem lại mapping/transaction và đường ghi phù hợp.

## 13. @Immutable: bất biến theo mapping entity

Hibernate cung cấp annotation:

```java
import org.hibernate.annotations.Immutable;
```

Ví dụ một bảng danh mục mã tiền tệ:

```java
package com.example.reference.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Table(name = "currency_codes")
public class CurrencyCode {
    @Id
    @Column(length = 3)
    private String code;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected CurrencyCode() {}

    public String getCode() { return code; }
    public String getDisplayName() { return displayName; }
}
```

`@Immutable` ở mức entity cho Hibernate biết **không cần dirty-check thay đổi state entity** để tạo các UPDATE thông thường. Nó khác với read-only per session:

- Là lựa chọn của mapping, áp dụng thống nhất cho entity type được ánh xạ.
- Phù hợp với dữ liệu tham chiếu do nghiệp vụ này không chỉnh sửa qua ORM bình thường.
- Có thể giảm chi phí dirty checking/snapshot của entity.
- Không trở thành constraint `CHECK`/trigger hoặc quyền `SELECT ONLY` ở database.
- Không bảo đảm bulk HQL, native SQL hoặc ứng dụng khác không sửa bảng.

Một bảng cấu hình được DB admin/migration cập nhật định kỳ vẫn có thể ánh xạ `@Immutable` nếu application chỉ đọc, nhưng cần có kế hoạch refresh/cache invalidation khi dữ liệu đổi ngoài đường ghi Hibernate bình thường.

### 13.1. Hibernate @Immutable không phải Java final

Một class `@Immutable` vẫn có thể có setter, field mutable hoặc danh sách mutable ở Java. Annotation không chặn câu lệnh Java thay đổi object; nó thông báo cho ORM cách đồng bộ một phần state.

Ngược lại, một Java record hoặc DTO `final` với field `final` có thể bất biến ở mức API, nhưng không tự là một entity Hibernate. “Java immutable object” và “Hibernate immutable entity” không phải cùng khái niệm.

### 13.2. @Immutable trên entity không cấm INSERT/DELETE tuyệt đối

Một entity bất biến về cập nhật có thể vẫn được persist hoặc remove qua lifecycle thích hợp, tùy mapping và operation. Nếu bảng bắt buộc append-only hoặc hoàn toàn không cho xóa/sửa, phải triển khai giới hạn trong database và application policy.

Ví dụ không nên dựa vào:

```java
@Entity
@Immutable
class AuditRecord { /* ... */ }
```

để kết luận không ai có thể gọi `em.remove(auditRecord)` hoặc xóa bằng SQL trực tiếp. Audit không được sửa/xóa là yêu cầu hệ thống; cần chính sách retention, quyền DB, ràng buộc hoặc storage thích hợp.

## 14. @Immutable trên collection khác với read-only entity

Đây là một trong những điểm dễ nhầm khi đọc tài liệu Hibernate.

Hibernate cho phép đánh dấu một collection mapping là immutable:

```java
import org.hibernate.annotations.Immutable;

@Immutable
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
        name = "published_article_keywords",
        joinColumns = @JoinColumn(name = "article_id"))
@Column(name = "keyword", nullable = false)
private Set<String> publishedKeywords = new HashSet<>();
```

Khi collection được mapping `@Immutable`, việc thay đổi persistent collection đã được Hibernate quản lý có thể làm Hibernate ném `HibernateException` lúc phát hiện collection bị sửa/flush. Đây không phải việc “im lặng bỏ qua” mọi thao tác như read-only scalar state của entity.

So sánh:

| Trường hợp | `article.rename("B")` | `article.addKeyword("ORM")` |
|---|---|---|
| Article mutable và keywords mutable | UPDATE Article khi cần | Cập nhật collection table khi cần |
| Article read-only theo `setReadOnly(true)` | Thường bỏ UPDATE scalar | Collection vẫn có thể được cập nhật |
| Article `@Immutable` ở mức entity | Bỏ update state entity thông thường | Không tự bảo đảm collection mutable sẽ bị cấm; xem mapping collection |
| `@Immutable` trên chính keywords collection | Article scalar vẫn theo mapping của Article | Thay đổi collection có thể bị từ chối bằng exception |

Vì vậy, khi use case đòi hỏi cả bài viết lẫn keywords không được thay đổi, đừng chỉ bật read-only flag cho Article rồi tin rằng toàn bộ aggregate đã đóng băng. Phải chọn rõ mức độ bảo vệ ở mapping, tầng domain và database.

## 15. @Column(updatable=false) không phải read-only entity

Một thuộc tính không được cập nhật sau lúc tạo có thể có:

```java
@Column(name = "created_at",
        nullable = false,
        updatable = false)
private Instant createdAt;
```

Hibernate sẽ không đưa cột `created_at` vào SQL UPDATE thông thường của entity mapping đó. Nhưng:

- Các field khác vẫn được dirty-check/cập nhật nếu entity mutable.
- Nếu Java code gán `createdAt` mới, field trong memory vẫn đổi.
- SQL trực tiếp, trigger hoặc service khác vẫn có thể cập nhật cột nếu quyền database cho phép.
- Annotation không khiến toàn entity trở thành read-only.

Với một audit field không nên đổi, nên kết hợp constructor/lifecycle callback, không có public setter, quy tắc domain và database constraint/permission thích hợp. Với những cột chỉ được database sinh, có thể cần mapping generated values để Hibernate đọc lại giá trị đúng; `updatable=false` đơn thuần không tự reload.

## 16. FlushMode.MANUAL không đồng nghĩa read-only

Trong Hibernate, flush mode quyết định Hibernate **khi nào tự động đồng bộ những thay đổi pending**, chứ không trực tiếp xác định entity nào modifiable.

Ví dụ:

```java
import org.hibernate.FlushMode;

session.setHibernateFlushMode(FlushMode.MANUAL);

Article article = session.get(Article.class, 10L);
article.rename("B");

// AUTO flush bị hạn chế theo MANUAL,
// nhưng entity vẫn managed và modifiable.
session.flush(); // Flush tường minh vẫn có thể UPDATE Article.
```

Trong trường hợp trên, Hibernate vẫn có thể dirty-check và thực thi SQL UPDATE khi `flush()` được gọi rõ ràng. Vì thế `FlushMode.MANUAL` không phải cách bảo vệ nghiệp vụ rằng database không bao giờ ghi.

Ngược lại, nếu entity đã read-only nhưng session có FlushMode.AUTO, Hibernate vẫn có thể flush những entity modifiable khác hoặc những collection thay đổi. Flush mode và read-only entity flag là **hai trục độc lập**.

| Tình huống | State entity | Flush behavior |
|---|---|---|
| Managed mutable + AUTO | Dirty-check bình thường | Hibernate auto-flush theo điều kiện |
| Managed mutable + MANUAL | Vẫn mutable | Cần flush tường minh cho những thay đổi pending |
| Read-only entity + AUTO | Bỏ dirty-check scalar/to-one của entity đó | Vẫn có thể flush thay đổi khác |
| Read-only entity + MANUAL | Bỏ dirty-check scalar/to-one | Manual flush vẫn có thể ghi collection/entity khác |

Không thay đổi flush mode trên một Session dùng chung trong transaction mà không hiểu luồng hiện tại, vì có thể khiến thay đổi hợp lệ của caller không được đồng bộ đúng thời điểm.

## 17. Spring @Transactional(readOnly = true): một tầng khác

Trong Spring:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ArticleQueryService {
    private final ArticleRepository repository;

    public ArticleQueryService(ArticleRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Article loadForDisplay(Long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Không tìm thấy"));
    }
}
```

Đoạn code giả định `ArticleRepository` là repository tương thích Spring Data JPA. `@Transactional(readOnly=true)` là **chỉ dẫn ở tầng transaction manager** rằng phương thức được thiết kế để đọc. Tùy Spring/transaction manager/Hibernate integration, framework có thể:

- Cấu hình flush mode tối ưu, thường hạn chế auto-flush trên session cho transaction đọc.
- Truyền trạng thái read-only xuống JDBC connection/transaction khi hỗ trợ.
- Đặt session default read-only cho các entity mới được nạp theo những integration/phiên bản phù hợp.
- Tối ưu lượng công việc dirty checking.

Không có một bảo đảm đồng nhất trên mọi môi trường rằng annotation này **cấm** `entityManager.persist()`, `executeUpdate()` hoặc native SQL. Một số database/driver thực thi read-only transaction nghiêm ngặt; môi trường khác chỉ coi đó là hint hoặc có hành vi khác. Cần kiểm tra cấu hình thực tế nếu đang thiết kế chính sách dữ liệu bất biến.

### 17.1. Gọi phương thức ghi từ một transaction đọc

Ví dụ:

```java
@Transactional(readOnly = true)
public void dangerousMixedOperation(Long id) {
    Article article = em.find(Article.class, id);
    article.rename("Đã sửa");
    // Không nên kỳ vọng thay đổi được commit,
    // cũng không coi readOnly=true là hàng rào bảo mật.
}
```

Đây là một hợp đồng phương thức không nhất quán: khai báo chỉ đọc nhưng lại sửa state. Tùy integration, SQL có thể bị bỏ tự động flush hoặc bị database từ chối khi có DML; nhưng một lệnh SQL tường minh vẫn có thể được thực thi ở môi trường cho phép.

Hướng thiết kế rõ hơn là:

```java
@Transactional(readOnly = true)
public ArticleSummary viewArticle(Long id) {
    // Query DTO đọc.
}

@Transactional
public void renameArticle(Long id, String title) {
    Article article = em.find(Article.class, id);
    article.rename(title);
}
```

Trong Spring, lưu ý proxy-based transactions và self-invocation: nếu một method trong cùng bean gọi trực tiếp method `@Transactional` khác của chính nó, annotation trên method được gọi có thể không được proxy áp dụng như mong muốn. Phạm vi transaction cần được tổ chức ở application service boundary.

### 17.2. Read-only transaction không phải authorization

Ngay cả nếu database từ chối UPDATE trong một transaction read-only, nó không bảo đảm client có quyền đọc mọi row. Cần kiểm tra authorization, tenant isolation và filter dữ liệu phù hợp. “Chỉ đọc” nghĩa không dự kiến ghi; nó không có nghĩa “đọc gì cũng được”.

## 18. Database read-only: mức bảo vệ thực sự khác ORM

Nếu yêu cầu là một service **không bao giờ được phép ghi** vào production database, chỉ bật Hibernate read-only không đủ. Cần xem xét quyền database:

```sql
-- Ví dụ khái quát PostgreSQL:
GRANT SELECT ON TABLE articles TO reporting_reader;
GRANT SELECT ON TABLE categories TO reporting_reader;
GRANT SELECT ON TABLE article_keywords TO reporting_reader;
```

Một user chỉ được cấp SELECT và không có quyền ghi từ role khác sẽ bị database từ chối DML không hợp lệ. Để chính sách thực sự có hiệu lực, cần kiểm tra quyền kế thừa, schema privileges, views, stored procedures, owner privileges và đường kết nối thực tế; vài dòng GRANT không tự thu hồi mọi quyền đã cấp trước đó.

Trong PostgreSQL, transaction read-only có thể được cấu hình ở database/session/transaction; driver và transaction manager phải truyền đúng cấu hình. Database khác có semantics khác nhau, đặc biệt khi stored procedures hoặc temporary objects tham gia. Đừng dùng annotation Hibernate làm bằng chứng tuân thủ bảo mật dữ liệu.

### 18.1. Read replica có làm session read-only không?

Một read replica có thể chỉ cho phép đọc theo cấu hình database/cluster. Nhưng điều đó không làm các entity Hibernate tự động trở thành read-only trong memory. Nếu session đang modifiable, Hibernate vẫn có thể thực hiện dirty checking và **cố** phát UPDATE, rồi database mới báo lỗi.

Ngoài ra, replica có thể bị replication lag; giá trị đọc có thể cũ hơn primary. Chính sách read/write routing và yêu cầu nhất quán phải được thiết kế ở tầng application/storage, không chỉ chọn `setReadOnly()`.

## 19. Read-only không làm mất vai trò của persistence context

Ngay cả khi một Article read-only:

```java
Article first = session.get(Article.class, 10L);
session.setReadOnly(first, true);
Article second = session.get(Article.class, 10L);

System.out.println(first == second); // true
```

Hibernate vẫn giữ managed reference trong PC. Điều đó kéo theo những đặc tính sau:

- Identity map vẫn có thể chiếm bộ nhớ.
- Entity graph có thể chứa lazy proxies và persistent collections.
- Các association được tải sau đó vẫn có thể phát thêm SQL SELECT.
- Những entity khác trong PC vẫn được dirty-check nếu modifiable.
- `clear()` hoặc `detach()` vẫn là các thao tác riêng để chấm dứt quản lý state.

Read-only có thể giảm overhead snapshot/dirty checking, nhưng không loại bỏ chi phí materialize entity, JDBC result set, identity map, collection wrappers hay JSON serialization.

### 19.1. Đừng nhầm read-only với detach

| Đặc tính | Managed read-only | Detached |
|---|---|---|
| Có mặt trong PC | Có | Không |
| Hibernate quản lý identity | Có | Không trong PC cũ |
| Scalar change tự tạo UPDATE | Không theo semantics read-only | Không qua PC cũ |
| Lazy loading khi Session mở | Có thể thực hiện | Association chưa khởi tạo có thể lỗi |
| Collection/cascade | Vẫn có thể được ORM xử lý | Không tự flush qua PC cũ |
| Đưa lại vào managed mode | `setReadOnly(false)` khi mapping cho phép | `merge()` hoặc load entity mới |
| Mục đích | Giữ entity trong PC nhưng giảm tracking ghi | Chấm dứt management của object |

Nếu muốn giải phóng state khỏi PC trong import lớn, `setReadOnly(true)` không thay `clear()`. Nếu chỉ muốn một query tạo DTO để trả API, cả hai thao tác có thể không cần thiết.

### 19.2. StatelessSession cũng không phải “read-only Session”

Hibernate có `StatelessSession` cho một số tác vụ dữ liệu khối lượng lớn; nó không dùng persistence context/dirty checking theo cùng cách Session stateful. Các thao tác insert/update/delete thường mang semantics tường minh hơn, và nhiều khả năng ORM như cascade/lifecycle events có khác biệt tùy version.

Đừng chọn `StatelessSession` chỉ vì tên có vẻ phù hợp read-only. Nó thay đổi mô hình thao tác và consistency của application, không chỉ bật một optimization flag cho Session thông thường.

## 20. Read-only trong transaction có nhiều entity khác nhau

Ví dụ application cần đọc một bài viết chỉ để tham khảo, nhưng cập nhật thống kê ở entity khác:

```java
@Transactional
public void recordArticleView(Long articleId) {
    Session session = em.unwrap(Session.class);

    Article article = em.find(Article.class, articleId);
    if (article == null) {
        throw new IllegalArgumentException("Không tìm thấy bài");
    }

    session.setReadOnly(article, true);

    ArticleViewCounter counter = em.find(
            ArticleViewCounter.class, articleId);
    counter.increment();
}
```

Đoạn code giả định một entity `ArticleViewCounter` có key phù hợp và method `increment()`, được dùng để minh họa ranh giới trạng thái. Trong transaction này:

- Article vẫn managed nhưng scalar changes của Article không bị dirty-check.
- Counter vẫn là entity managed và modifiable, nên việc tăng count có thể tạo UPDATE.
- Commit vẫn có thể phát SQL ghi (counter), dù một entity cụ thể read-only.

Nếu mục tiêu của use case là **toàn bộ transaction không ghi**, không nên trộn thao tác đếm lượt xem trong cùng transaction đọc. Có thể ghi metric qua event hoặc command riêng, tùy yêu cầu nhất quán.

### 20.1. Read-only tại mức entity không lan truyền tự động sang entity khác

`Article` read-only không có nghĩa:

```text
Article [read-only]
   ├── Category [tự động read-only?]  → Không bảo đảm
   ├── Comments [tự động read-only?]  → Không bảo đảm
   └── ViewCounter [tự động read-only?] → Không
```

Khi Hibernate load một entity liên quan, read-only của nó phụ thuộc cách mapping/load và default/query flags áp dụng cho thời điểm nạp, chứ không được suy ra chỉ từ flag trên parent. Dùng `@Immutable` trên những reference data thực sự cố định hoặc query DTO khi muốn tránh vô tình sửa object graph.

## 21. Hành vi của collection khi dùng @ElementCollection, @OneToMany và @ManyToMany

Một bảng khái quát giúp phân biệt “không dirty-check scalar” và “không thao tác quan hệ”:

| Mapping của Article | Ví dụ Java | Có thể xảy ra ở flush khi Article read-only |
|---|---|---|
| Basic field `title` | `rename("B")` | Thay đổi title bị bỏ khỏi dirty checking của Article |
| `@ManyToOne Category` | `changeCategory(other)` | Không UPDATE FK Article qua change của single-ended association |
| `@ElementCollection Set<String>` | `addKeyword("JPA")` | Có thể INSERT vào collection table |
| `@OneToMany Comment` | `comments.add(new Comment(...))` | Có thể cascade persist/update relationship khi owning side đúng |
| `@ManyToMany Tag` | `tags.add(tag)` | Có thể INSERT join-table row khi collection owning side thay đổi |
| Managed Comment mutable | `comment.editBody("...")` | Comment có thể UPDATE dù Article read-only |

Trong `@OneToMany(mappedBy=...)`, cần xét owning side: nếu chỉ sửa collection inverse mà không cập nhật FK phía con, database có thể không phản ánh quan hệ. Trong `@ManyToMany`, cần thao tác phía owning side của join table; `CascadeType.REMOVE` tới entity Tag dùng chung thường là lựa chọn không phù hợp.

**Kết luận kỹ thuật của bảng:** read-only entity không phải “vùng cấm UPDATE” cho mọi table mà entity có quan hệ tới.

## 22. Thay đổi được bỏ theo dõi có thể gây sai lệch trong memory

Đây là một failure mode tinh vi khi application nghĩ read-only đồng nghĩa object bất biến.

```text
T0: Database Article #10 có title="A"
T1: Session nạp Article và setReadOnly(true)
T2: Một method nghiệp vụ vô tình gọi rename("B")
T3: Một method khác đọc article.getTitle() → thấy "B"
T4: Transaction commit; database vẫn là "A"
T5: Request khác load Article → nhận "A"
```

Nếu method ở T3 dùng title để tạo email, audit event hoặc cache entry, nó có thể xuất dữ liệu **chưa bao giờ được lưu**. Vì vậy có hai cấp bảo vệ cần cân nhắc:

1. **Không cần update SQL:** read-only flag của Hibernate có thể hữu ích.
2. **Không cho phép code sửa object:** thiết kế class API bất biến/đóng gói, use case chỉ đọc trả DTO/value object, hoặc không cấp reference mutable cho tầng hiển thị.

Một record DTO:

```java
public record ArticlePreview(Long id, String title) {}
```

không có setter cho `title`; các field là `final`. Nó không phải managed entity, nên không bị logic dirty checking của Hibernate chi phối. Nhưng record có thể chứa reference tới object mutable, nên bất biến của record là bất biến nông; các value object trong DTO cũng cần được thiết kế phù hợp.

### 22.1. Dùng read model thay vì entity read-only trong API

```java
@Transactional(readOnly = true)
public ArticlePreview findPreview(Long id) {
    return em.createQuery(
            "select new com.example.blog.read.ArticlePreview(" +
            "  a.id, a.title" +
            ") from Article a where a.id = :id",
            ArticlePreview.class)
            .setParameter("id", id)
            .getResultStream()
            .findFirst()
            .orElseThrow(() ->
                    new IllegalArgumentException("Không tìm thấy bài"));
}
```

Với DTO projection này, tầng UI không giữ Article managed hoặc detached. Nó chỉ nhận đúng dữ liệu được chọn. Nếu endpoint cần đọc danh sách lớn, bổ sung điều kiện lọc, sắp xếp và phân trang để tránh lấy toàn bộ row.

## 23. Read-only và second-level cache

Hibernate có thể có second-level cache ở phạm vi `SessionFactory`. Read-only flag của một entity trong Session không phải lệnh xóa hoặc cấu hình second-level cache region.

- `session.setReadOnly(article,true)` thay đổi cách quản lý state của instance trong PC hiện tại.
- `session.clear()` bỏ managed entries của first-level cache, không tự evict mọi second-level cache entry.
- Entity `@Immutable` có thể phù hợp với cache concurrency strategy read-only **nếu dữ liệu thực sự không thay đổi qua những đường không được invalidation**.
- Một ứng dụng/admin khác cập nhật bảng có thể khiến cache đọc lại giá trị cũ nếu không có chiến lược invalidation/expiry.

Không coi second-level cache “read-only” là database security boundary. Nếu dữ liệu tham chiếu được cập nhật qua migration hoặc job, cần có quy trình evict/invalidate theo Hibernate cache provider và deployment topology.

### 23.1. Đọc từ cache không đồng nghĩa mới nhất

Sau khi một transaction khác sửa database, entity hiện có trong PC vẫn có thể giữ state cũ cho tới khi refresh/clear/nạp session mới tùy isolation. Thêm second-level cache còn có thêm một tầng cần quản lý. Read-only flag không quyết định isolation level hoặc consistency giữa các session.

## 24. Tránh sử dụng read-only flag để “tối ưu” khi cần cập nhật sau đó

Giả sử service thực hiện:

```java
Article article = session.get(Article.class, id);
session.setReadOnly(article, true);

// Đọc các thuộc tính để tính toán...

article.rename("Tên mới từ kết quả tính toán");
tx.commit();
```

Nếu mục tiêu cuối cùng là cập nhật `title`, bật read-only ngay trước khi gọi `rename()` là sai về hợp đồng. Việc tăng tốc dirty checking không đáng để hy sinh tính đúng đắn.

Hướng rõ hơn:

```java
@Transactional
public void renameArticle(Long id, String newTitle) {
    Article article = em.find(Article.class, id);
    if (article == null) {
        throw new IllegalArgumentException("Không tìm thấy");
    }

    article.rename(newTitle);
    // Managed mutable → update khi cần, @Version nếu mapping có.
}
```

Nếu bài toán cần tính toán lâu trên dữ liệu đọc rồi ghi lại sau, có thể:

1. Query một snapshot DTO trong transaction đọc.
2. Xử lý tính toán ngoài transaction nếu được.
3. Mở transaction ghi, tải managed entity và kiểm tra expected version/state.
4. Áp dụng command có kiểm soát; xử lý optimistic lock conflict.

Đây là thiết kế rõ ràng hơn việc bật/tắt read-only nhiều lần trên cùng managed instance vốn có thể đã lệch database.

## 25. Một quy trình batch đọc hiệu quả

Với lô hàng trăm nghìn bài viết, tải tất cả entity vào một session read-only vẫn chiếm bộ nhớ vì identity map và reference từ application.

Một cách đọc theo trang với query read-only:

```java
public void exportArticleTitles(SessionFactory factory,
                                java.util.function.Consumer<String> output) {
    final int pageSize = 500;
    long cursor = 0L;

    try (Session session = factory.openSession()) {
        Transaction tx = session.beginTransaction();
        try {
            while (true) {
                List<Article> batch = session.createQuery(
                        "select a from Article a " +
                        "where a.id > :cursor " +
                        "order by a.id",
                        Article.class)
                        .setParameter("cursor", cursor)
                        .setReadOnly(true)
                        .setMaxResults(pageSize)
                        .getResultList();

                if (batch.isEmpty()) {
                    break;
                }

                for (Article article : batch) {
                    output.accept(article.getTitle());
                    cursor = article.getId();
                }

                session.clear(); // Giải phóng managed state giữa các trang.
            }
            tx.commit();
        } catch (RuntimeException | Error error) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
            }
            throw error;
        }
    }
}
```

Ví dụ giả định `Article.id` là Long dương, có thứ tự tăng tương ứng và đối tượng `output` không thực hiện thao tác ghi ngoài ý muốn. Đây là thiết kế **read-only use case**; nếu output ghi file/network, cần xem xét lỗi/rollback và resource lifecycle. Một transaction kéo dài qua hàng triệu row có thể chiếm tài nguyên database, vì vậy với export thực tế có thể cần transaction theo trang, snapshot isolation phù hợp hoặc streaming cursor.

Lưu ý:

- `setReadOnly(true)` giảm chi phí state tracking nhất định.
- `session.clear()` giải phóng managed entries sau khi dùng; nó **không** rollback SQL và không tự đóng session.
- Cursor `id > :cursor` giới hạn trang; index PK giúp hỗ trợ.
- Nếu chỉ cần title, dùng DTO/scalar projection thay vì entity sẽ tránh quản lý state ngay từ đầu.
- Nếu các row thay đổi đồng thời trong lúc export, keyset pagination không tự tạo snapshot nhất quán cho toàn bộ lần export.

Một lựa chọn gọn hơn để tránh entity:

```java
List<String> titles = session.createQuery(
        "select a.title from Article a " +
        "where a.id > :cursor order by a.id",
        String.class)
        .setParameter("cursor", cursor)
        .setMaxResults(500)
        .getResultList();
```

Nếu cần tiếp tục phân trang, query scalar cũng phải trả ID để cập nhật cursor, ví dụ record `ArticleCursorRow(Long id, String title)`. Chỉ chọn title mà không có ID thì không thể biết vị trí keyset tiếp theo từ kết quả.

## 26. Các sai lầm phổ biến

| Quan niệm hoặc hiện tượng | Vì sao không đúng | Hướng xử lý |
|---|---|---|
| “Read-only entity không thể sửa field Java” | Setter/method vẫn thay state trong memory | Dùng DTO/đóng gói nếu muốn API không cho sửa |
| “Đánh dấu Article read-only là toàn bộ transaction không ghi” | Entity khác, collection hoặc SQL tường minh vẫn có thể ghi | Xác định scope; dùng transaction/DB policy khi cần |
| “Collection của entity read-only cũng không đổi” | Collection vẫn có state tracking riêng | Tránh mutation, dùng `@Immutable` collection khi đúng domain |
| “@Immutable collection sẽ im lặng bỏ thay đổi” | Hibernate có thể ném exception khi sửa persistent immutable collection | Coi đó là hợp đồng không được sửa; kiểm tra lỗi phù hợp |
| “setDefaultReadOnly(true) đổi mọi managed entity hiện có” | Chỉ tác động các đường load tương lai | Dùng `setReadOnly(entity,true)` với instance có sẵn |
| “Query.setReadOnly(true) làm instance đã managed read-only” | Identity map trả lại instance cũ và flag cũ | Kiểm tra trạng thái instance và quản lý scope |
| “Bật read-only → sửa → tắt read-only là ghi lại thay đổi” | Thay đổi lúc read-only không được tracking như pending update | Tải/refresh state, rồi sửa sau khi modifiable |
| “@Immutable ngăn mọi SQL update” | Native/bulk DML hoặc actor ngoài có thể sửa database | Enforce quyền/constraint ở DB |
| “@Column(updatable=false) làm entity bất biến” | Chỉ ảnh hưởng một cột trong UPDATE thông thường | Dùng mapping theo đúng mức bảo vệ |
| “FlushMode.MANUAL là read-only” | Manual flush vẫn có thể ghi state mutable | Phân biệt dirty checking và flush scheduling |
| “@Transactional(readOnly=true) là cơ chế security” | Chủ yếu là hint/optimization tùy integration | Authorization và quyền database tách biệt |
| “Article read-only thì Category cũng read-only” | Entity liên quan có trạng thái quản lý riêng | Xác định graph và từng mapping |
| “Read-only ngăn em.remove(article)” | Remove là lifecycle operation khác dirty checking | Kiểm soát xóa ở domain/DB |
| “Read-only làm PC không giữ object” | Identity map vẫn giữ managed instance | Dùng projection hoặc clear/detach đúng chỗ |
| “Read replica luôn trả trạng thái mới nhất” | Có thể có replication lag | Chọn consistency và read routing đúng |
| “@Version không bao giờ tăng với read-only entity” | Dirty collection có thể kéo theo version update | Hiểu versioning của collection và mapping |

## 27. Phân tích bốn tình huống thực tế

### Tình huống A: màn hình danh sách chỉ xem thông tin

Yêu cầu: hiển thị 50 tiêu đề và tên thể loại, không có command cập nhật.

**Lựa chọn thường phù hợp:** constructor projection vào record:

```java
public record ArticleSummary(
        Long id, String title, String categoryName) {}
```

```java
List<ArticleSummary> items = em.createQuery(
        "select new com.example.blog.read.ArticleSummary(" +
        "  a.id, a.title, c.name" +
        ") from Article a join a.category c " +
        "order by a.id",
        ArticleSummary.class)
        .setMaxResults(50)
        .getResultList();
```

Không cần entity managed chỉ để hiển thị, nên cũng không cần thao tác read-only flag cho mỗi row.

### Tình huống B: báo cáo xử lý nhiều entity và cần quan hệ lazy

Yêu cầu: tính báo cáo từ nhiều entity, cần đọc một số association nhưng không sửa entity.

**Lựa chọn có thể phù hợp:** session/query read-only kết hợp phân trang, query join fetch có kiểm soát hoặc batch fetching. Điều này vẫn giữ lazy loading trong session, nhưng tránh dirty checking scalar state không cần thiết. Không dùng `EAGER` hoặc fetch nhiều collection lớn chỉ vì query read-only.

### Tình huống C: bảng danh mục chỉ do migration cập nhật

Yêu cầu: application truy vấn CountryCode/CurrencyCode, không cho domain cập nhật chúng.

**Lựa chọn có thể phù hợp:** `@Immutable` trên entity cùng với quyền database chỉ đọc khi có yêu cầu bảo vệ thực sự, và cache invalidation nếu migration thay đổi dữ liệu. Annotation này không thay cho chính sách dữ liệu ở database.

### Tình huống D: command vừa đọc metadata vừa ghi entity chính

Yêu cầu: dùng Article để tham khảo, nhưng ghi entity `ArticleViewCounter`.

**Lựa chọn:** đánh dấu Article read-only nếu session có nhiều state đọc, giữ Counter modifiable trong transaction ghi. Không khai báo toàn bộ method là read-only một cách trái mục đích. Nếu chỉ đọc một vài scalar của Article, query projection có thể gọn hơn.

## 28. Cách lựa chọn từ yêu cầu nghiệp vụ

Một quy trình hữu ích:

**Bước 1 — Bạn có cần entity managed hay chỉ cần dữ liệu hiển thị?** Nếu chỉ cần vài cột, dùng DTO/projection. Nếu cần duyệt quan hệ/lifecycle trong PC, cân nhắc entity read-only.

**Bước 2 — Phạm vi chỉ đọc đến đâu?** Một instance cụ thể → `session.setReadOnly()`; một query → `query.setReadOnly()`; nhiều lần load trong cùng session → `setDefaultReadOnly()`; toàn entity type bất biến về update → `@Immutable`.

**Bước 3 — Có collection hoặc cascade nào có thể ghi không?** Kiểm tra `@ElementCollection`, `@OneToMany`, `@ManyToMany`, owning side, `orphanRemoval` và `CascadeType.REMOVE`. Không kết luận read-only chặn tất cả.

**Bước 4 — Transaction có cần tuyệt đối không phát SQL ghi không?** Nếu cần, tách read operation khỏi write, cấu hình transaction/database role/read replica và phép kiểm tra thích hợp. Read-only ORM flag không thay thế security policy.

**Bước 5 — Có khả năng chuyển entity từ đọc sang ghi trong cùng Session không?** Nếu có, hãy thiết kế ranh giới transaction rõ ràng, tránh sửa trong giai đoạn read-only và dùng state nền tin cậy trước khi ghi.

**Bước 6 — Có cache hoặc replica không?** Xác định data freshness, isolation và invalidation thay vì dựa vào read-only flag để đọc dữ liệu mới nhất.

**Bước 7 — Có thực sự có lợi về hiệu năng không?** Đo số entity, snapshot/dirty-check overhead, memory, SQL và latency. Với danh sách lớn, projection và phân trang thường có tác động mạnh hơn chỉ đổi read-only flag.

## 29. Sơ đồ tư duy cuối bài

```text
               Use case chỉ muốn ĐỌC dữ liệu
                            │
               Có cần managed entity không?
                   ┌────────┴────────┐
                  KHÔNG             CÓ
                   │                 │
                   ▼                 ▼
             DTO/projection     Phạm vi read-only?
                                     │
                        ┌────────────┼───────────────┐
                        │            │               │
                    Một entity    Một query     Nhiều lần load
                        │            │               │
                        ▼            ▼               ▼
                setReadOnly()    Query.setReadOnly()  setDefaultReadOnly()
                        │            │               │
                        └────────────┴───────────────┘
                                     │
                                     ▼
                       Entity vẫn MANAGED trong PC
                                     │
                           Đổi loại state nào?
                     ┌───────────────┴──────────────┐
                     │                              │
              Scalar / to-one                   Collection / cascade
                     │                              │
                     ▼                              ▼
              Bỏ dirty-check                  Vẫn có thể phát
              update state đó                  INSERT/DELETE/UPDATE
                     │                              │
                     └───────────────┬──────────────┘
                                     ▼
                        Muốn không ghi ở DB?
                                     │
                                     ▼
                    Transaction policy + quyền DB
                    + domain authorization/constraints

   @Immutable entity: read-only theo mapping
   @Immutable collection: cấm sửa collection theo ORM
   FlushMode.MANUAL: kiểm soát thời điểm flush, không phải khóa ghi
   detach/clear: chấm dứt quản lý, không giống read-only
```

**Kết luận:** chế độ chỉ đọc trong Hibernate là một **cơ chế quản lý thay đổi có phạm vi**, không phải thuộc tính bất biến tuyệt đối của Java object hay database. Với managed read-only entity, Hibernate chủ yếu bỏ theo dõi cập nhật của scalar state và những association đơn trị; persistent collection, cascade, entity liên quan, remove và SQL tường minh vẫn có thể gây thao tác ghi. Hãy chọn đúng phạm vi `setReadOnly()`, `setDefaultReadOnly()`, `Query.setReadOnly()` hoặc `@Immutable`; tách biệt chúng với flush mode, transaction read-only và quyền database. Khi chỉ cần dữ liệu trình bày, projection DTO thường là cách biểu đạt ý định chỉ đọc rõ nhất.
