# Ánh xạ giá trị cơ bản bằng ElementCollection

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Tập hợp và Map

Một entity trong ứng dụng Java thường chứa không chỉ các thuộc tính đơn như `String title` hay `Long id` mà còn **tập hợp các giá trị đơn giản**: danh sách từ khóa, tập nhãn, nhiều số điện thoại phụ, danh sách ngôn ngữ hỗ trợ, hoặc một `Map` lưu các cặp khóa–giá trị cấu hình. Các phần tử này có thể chỉ là `String`, `Integer`, `Enum` hoặc những basic type khác, **không phải entity có định danh riêng**.

Trong Jakarta Persistence (JPA), `@ElementCollection` cho phép ánh xạ một collection chứa **basic values** hoặc các đối tượng `@Embeddable`. Bài này tập trung vào nhánh **basic values**, tức là ánh xạ `Set<String>`, `List<String>`, `Set<Enum>`, `Map<String, String>` và các kiểu tương tự.

**Điểm cốt lõi:** `@ElementCollection` lưu các phần tử vào một **collection table** gắn với entity chủ sở hữu. Các phần tử không có `@Id` riêng, không được quản lý bằng `EntityManager.find`/`remove` như entity độc lập. Khi thêm hoặc xóa phần tử, JPA đồng bộ các hàng trong bảng giá trị theo vòng đời của **owner entity**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao một tập nhãn `Set<String>` nên là basic-value collection thay vì vội tạo một `@Entity Tag`.
2. Khai báo `@ElementCollection` cùng `@CollectionTable`, `@JoinColumn` và `@Column`.
3. Hiểu bảng phụ được tạo ra, foreign key về bảng owner và cách các phần tử được lưu.
4. Phân biệt ngữ nghĩa `Set`, `List` và `Map` khi lưu các giá trị cơ bản.
5. Dùng `@OrderColumn` để bảo toàn thứ tự của `List` và `@MapKeyColumn` để lưu khóa của `Map`.
6. Ánh xạ enum bằng `@Enumerated(EnumType.STRING)` trong element collection.
7. Thêm, xóa, thay thế giá trị trong transaction; hiểu cascade theo ownership, dirty checking và thời điểm flush.
8. Truy vấn tập giá trị với `JOIN`, `MEMBER OF`, `KEY` và `VALUE` trong JPQL.
9. Nhận diện chi phí cập nhật collection, truy vấn lazy, N+1, việc xóa/ghi lại hàng và ràng buộc unique/index.
10. Chọn giữa `@ElementCollection`, `@OneToMany`, `@ManyToMany` và `AttributeConverter` theo nhu cầu nghiệp vụ.

## 2. Bắt đầu bằng một yêu cầu nghiệp vụ

Giả sử hệ thống bài viết lưu:

- `Article` có định danh `id` và tiêu đề `title`.
- Mỗi bài viết có **nhiều nhãn** như `"java"`, `"jpa"`, `"database"`.
- Nhãn chỉ là chuỗi giá trị thuộc riêng bài viết: không cần người quản lý nhãn, không có ID riêng, không có ngày tạo hoặc trạng thái riêng.
- Trong một bài viết, không được có hai nhãn trùng nhau sau khi chuẩn hóa.

Tư duy Java:

```java
class Article {
    Long id;
    String title;
    Set<String> tags = new HashSet<>();
}
```

Nếu chỉ thêm `@Entity` lên `Article` mà không khai báo cách lưu `tags`, JPA không thể tự coi một `Set<String>` như một cột `VARCHAR` đơn giản chứa nhiều hàng. Quan hệ dữ liệu phải được mô hình hóa rõ.

Một phương án quan hệ phù hợp:

```text
articles                            article_tags
+----+---------------------+        +------------+-----------+
| id | title               |        | article_id | tag_value |
+----+---------------------+        +------------+-----------+
| 10 | JPA cơ bản          |        | 10         | java      |
| 20 | Persistence Context |        | 10         | jpa       |
+----+---------------------+        | 10         | database  |
                                   | 20         | orm       |
                                   +------------+-----------+

Article#10
    tags = {"java", "jpa", "database"}

Article#20
    tags = {"orm"}
```

Bảng `articles` chứa **entity**. Bảng `article_tags` chứa **các giá trị thuộc entity**. Không cần bảng `tags` với entity ID riêng nếu domain chỉ cần các chuỗi nhãn.

## 3. @ElementCollection thực sự đại diện cho điều gì?

Một mapping cơ bản:

```java
@ElementCollection
private Set<String> tags = new HashSet<>();
```

JPA hiểu `tags` là một collection các phần tử không phải entity, được quản lý theo owner. Các phần tử kiểu `String` là **basic type**. Với nhiều provider, collection được lưu ở bảng phụ có tên và cột theo quy ước mặc định; nhưng tên mặc định có thể gây bất ngờ và phụ thuộc naming strategy.

Để code rõ và có schema ổn định, nên chỉ định tên bảng và tên cột:

```java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "article_tags",
    joinColumns = @JoinColumn(name = "article_id")
)
@Column(name = "tag_value", nullable = false, length = 40)
private Set<String> tags = new HashSet<>();
```

Giải thích từng annotation:

| Annotation | Vai trò |
|---|---|
| `@ElementCollection` | Xác định thuộc tính là collection của basic values hoặc embeddables, không phải collection entity |
| `fetch = FetchType.LAZY` | Yêu cầu tải collection khi cần; `LAZY` cũng là mặc định cho element collection |
| `@CollectionTable(name = "article_tags")` | Chỉ định bảng chứa các phần tử |
| `joinColumns = @JoinColumn(name = "article_id")` | Chỉ định cột ở collection table tham chiếu ID của entity owner |
| `@Column(name = "tag_value")` | Chỉ định cột chứa **giá trị String của mỗi phần tử** |
| `nullable = false` | Diễn đạt rằng giá trị tag không được null ở schema/mapping |
| `length = 40` | Metadata độ dài cho cột chuỗi, không thay thế validation nghiệp vụ |

**Điểm dễ nhầm:** `@JoinColumn(name = "article_id")` ở đây mô tả khóa ngoại **của bảng `article_tags`** về `articles`. Trong khi đó `@Column(name = "tag_value")` mô tả **nội dung phần tử**, không phải khóa ngoại hay thuộc tính của một entity `Tag`.

### 3.1. DDL tương ứng

Với một database hỗ trợ cú pháp dưới đây, schema có thể là:

```sql
CREATE TABLE articles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);

CREATE TABLE article_tags (
    article_id BIGINT NOT NULL,
    tag_value VARCHAR(40) NOT NULL,

    CONSTRAINT fk_article_tags_article
        FOREIGN KEY (article_id) REFERENCES articles(id),

    CONSTRAINT uq_article_tags_value
        UNIQUE (article_id, tag_value)
);
```

Đây là DDL minh họa gần với H2/PostgreSQL; database khác có thể dùng cú pháp identity khác. Khóa ngoại bảo đảm tag phải thuộc một article có thật. Unique constraint trên cặp `(article_id, tag_value)` giúp tránh hai tag giống nhau trong cùng bài viết **ở mức database**.

Từ việc một `Set<String>` khử trùng lặp trong Java **không thể suy ra** database sẽ tự tạo unique constraint trên hai cột. Nếu uniqueness là invariant, hãy khai báo và kiểm tra constraint trong migration. Các provider có thể tạo DDL khác nhau tùy cấu hình; đừng coi tự sinh schema là hợp đồng vận hành của hệ thống thật.

## 4. Ví dụ hoàn chỉnh: Entity Article với tập Set<String>

### 4.1. Định nghĩa entity

```java
package demo.domain;

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

import java.util.Collections;
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

@Entity
@Table(name = "articles")
public class Article {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "article_tags",
        joinColumns = @JoinColumn(
            name = "article_id",
            nullable = false
        )
    )
    @Column(name = "tag_value", nullable = false, length = 40)
    private Set<String> tags = new HashSet<>();

    protected Article() {
        // JPA cần constructor không tham số.
    }

    public Article(String title) {
        this.title = requireTitle(title);
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Set<String> getTags() {
        return Collections.unmodifiableSet(tags);
    }

    public boolean addTag(String input) {
        return tags.add(normalizeTag(input));
    }

    public boolean removeTag(String input) {
        return tags.remove(normalizeTag(input));
    }

    public void rename(String newTitle) {
        this.title = requireTitle(newTitle);
    }

    private static String requireTitle(String value) {
        Objects.requireNonNull(value, "title");
        String normalized = value.trim();

        if (normalized.isEmpty() || normalized.length() > 200) {
            throw new IllegalArgumentException("Invalid title");
        }
        return normalized;
    }

    private static String normalizeTag(String input) {
        Objects.requireNonNull(input, "tag");

        String normalized =
            input.trim().toLowerCase(Locale.ROOT);

        if (normalized.isEmpty() || normalized.length() > 40) {
            throw new IllegalArgumentException("Invalid tag");
        }
        return normalized;
    }
}
```

Ở đây `tags` là tập các **String bất biến**. `addTag` và `removeTag` dùng cùng quy tắc chuẩn hóa, để `"JPA"` và `" jpa "` được coi như một tag `"jpa"`. Bộ quy tắc chuẩn hóa này là **quy ước nghiệp vụ của ví dụ**, không phải yêu cầu của JPA.

Các ý thiết kế:

1. Chỉ entity `Article` có `@Id`. Phần tử `String` trong `tags` không có ID riêng.
2. `tags` được khởi tạo bằng `HashSet` để khi tạo Article mới có thể thêm tag ngay trước khi persist.
3. Getter trả về view không sửa trực tiếp để mọi thay đổi đi qua các phương thức domain có validation.
4. `@ElementCollection` được quản lý bởi JPA khi `Article` là managed; không cần gọi `em.persist(tag)`.
5. Có thể thêm tag cho Article trước khi persist; khi lưu owner, provider đồng bộ các giá trị.
6. Không thể suy ra từ `HashSet` rằng thứ tự tag phải được bảo toàn trong database; `Set` không có thứ tự.
7. Nếu muốn duy trì thứ tự hiển thị cố định, nên sắp xếp ở tầng đọc/DTO theo quy tắc rõ ràng, hoặc chọn một mô hình thứ tự phù hợp.

### 4.2. Tại sao không lưu Set thành chuỗi phân cách dấu phẩy?

Một giải pháp tưởng đơn giản:

```text
articles.tags = "java,jpa,database"
```

Có thể phù hợp với nhu cầu lưu một document nguyên khối trong một số hệ thống, nhưng gây nhiều bất tiện nếu ứng dụng cần tìm kiếm chính xác một tag, index tag, kiểm soát trùng, thêm/xóa một giá trị hoặc áp dụng constraint.

Với collection table, mỗi giá trị nằm ở một hàng riêng, cho phép tìm bằng SQL JOIN, đặt index và kiểm soát FK. Đây là một lựa chọn chuẩn hóa quan hệ dễ làm việc với JPA cho nhu cầu nhiều giá trị thuộc một entity.

Không có nghĩa mọi tập dữ liệu phải thành nhiều hàng: nếu nghiệp vụ **luôn lưu/đọc như một khối** và có yêu cầu riêng về JSON, converter hoặc cột array của database, thiết kế khác có thể phù hợp hơn. Nhưng `@ElementCollection` là điểm khởi đầu rõ ràng khi muốn truy vấn và quản lý từng giá trị theo mô hình quan hệ.

## 5. Persistence unit để chạy ví dụ

Một ứng dụng Java SE có thể khai báo file `src/main/resources/META-INF/persistence.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="
               https://jakarta.ee/xml/ns/persistence
               https://jakarta.ee/xml/ns/persistence/persistence_3_0.xsd"
             version="3.0">

    <persistence-unit name="elementCollectionPU"
                      transaction-type="RESOURCE_LOCAL">

        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>demo.domain.Article</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:element_collection;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>

            <!-- Chỉ dùng cho database tạm trong bài học. -->
            <property name="hibernate.hbm2ddl.auto"
                      value="create-drop"/>
            <property name="hibernate.show_sql" value="true"/>
            <property name="hibernate.format_sql" value="true"/>
        </properties>
    </persistence-unit>
</persistence>
```

Muốn chạy cần các dependency tương thích gồm Jakarta Persistence API, Hibernate ORM provider và H2 JDBC driver. `hibernate.*` là thuộc tính riêng của Hibernate, không phải API JPA chung.

**Cảnh báo:** `hibernate.hbm2ddl.auto=create-drop` có thể tạo rồi xóa schema; chỉ dùng với database thử nghiệm. Với dữ liệu thật, hãy dùng migration được kiểm soát và ràng buộc đúng với database triển khai.

## 6. Persist entity có ElementCollection

Đoạn chương trình sau cho thấy không có entity `Tag` nào cần được persist độc lập:

```java
package demo;

import demo.domain.Article;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

public class CreateArticleDemo {

    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("elementCollectionPU");

        try {
            saveExample(emf);
        } finally {
            emf.close();
        }
    }

    private static void saveExample(EntityManagerFactory emf) {
        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();
            tx.begin();

            try {
                Article article = new Article("Học JPA");
                article.addTag("Java");
                article.addTag(" JPA ");
                article.addTag("database");
                article.addTag("java"); // Trùng sau chuẩn hóa.

                em.persist(article);

                tx.commit();

                System.out.println("Article ID: " + article.getId());
                System.out.println("Tags: " + article.getTags());
            } catch (RuntimeException failure) {
                if (tx.isActive()) {
                    try {
                        tx.rollback();
                    } catch (RuntimeException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;
            }
        } finally {
            em.close();
        }
    }
}
```

Sau commit, mô hình dữ liệu dự kiến:

```text
articles:
  (id=1, title="Học JPA")

article_tags:
  (article_id=1, tag_value="java")
  (article_id=1, tag_value="jpa")
  (article_id=1, tag_value="database")
```

ID cụ thể, thứ tự hàng và câu SQL thực tế có thể khác tùy database, provider và thời điểm đồng bộ. Ví dụ `GenerationType.IDENTITY` có thể làm INSERT hàng `articles` xảy ra sớm để lấy ID chủ sở hữu; các hàng `article_tags` được ghi theo quá trình đồng bộ persistence context.

**Vì sao không có `CascadeType.PERSIST` trên `tags`?** Vì đây là **element collection**, không phải association đến entity con. Các giá trị thuộc vòng đời owner theo semantics của `@ElementCollection`; không có đối tượng `Tag` mang identity để cascade `persist` đến.

## 7. Đọc ElementCollection: lazy và persistence context

`@ElementCollection` có mặc định `fetch = FetchType.LAZY`. Điều đó mô tả mong muốn trì hoãn tải collection cho đến khi cần; với JPA, `LAZY` là một **hint** mà provider có khả năng quyết định cách thực hiện. Cần quan sát SQL của stack cụ thể, không mặc định mọi provider/đường code đều tải đúng một cách.

### 7.1. Tải Article trước, đọc tags sau

```java
EntityManager em = emf.createEntityManager();

try {
    Article article = em.find(Article.class, articleId);

    System.out.println(article.getTitle());

    // Có thể kích hoạt query bổ sung để tải collection.
    System.out.println(article.getTags().size());
} finally {
    em.close();
}
```

Khi collection chưa được khởi tạo, provider có thể truy vấn:

```sql
SELECT article_id, tag_value
FROM article_tags
WHERE article_id = ?;
```

Không phải lúc nào cũng có một SQL riêng: provider có thể tải chung bằng join, fetch plan, cache hoặc tối ưu khác.

### 7.2. Đọc collection sau khi EntityManager đóng

```java
Article detached;

EntityManager em = emf.createEntityManager();
try {
    detached = em.find(Article.class, articleId);
} finally {
    em.close();
}

System.out.println(detached.getTags().size());
```

Nếu `tags` chưa được nạp và provider dùng lazy proxy/collection, việc truy cập sau khi persistence context đóng có thể ném exception như `LazyInitializationException` của Hibernate. Đây là **ngoại lệ provider**, không phải một class exception chuẩn của JPA.

Để tránh vấn đề, hãy chủ động lấy dữ liệu cần thiết **trong phạm vi context đang mở**, ví dụ:

- Load collection trước khi đóng EM, nếu use case thực sự cần.
- Dùng JPQL fetch join hoặc entity graph phù hợp.
- Trả DTO chứa tập giá trị đã được copy vào cấu trúc Java thuần thay vì đưa entity lazy ra ngoài phạm vi transaction.

Không nên chuyển mọi element collection thành `EAGER` chỉ để tránh lỗi truy cập sau transaction: với danh sách nhiều Article, điều đó có thể tạo thêm truy vấn hoặc tải quá nhiều dữ liệu.

## 8. Thêm, xóa và thay thế phần tử trên managed entity

Khi entity `Article` đã được quản lý trong một transaction, thay đổi trên collection được provider theo dõi bằng cơ chế dirty checking/collection tracking.

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    try {
        Article article = em.find(Article.class, articleId);

        if (article == null) {
            throw new IllegalArgumentException("Article not found");
        }

        article.addTag("Hibernate");
        article.removeTag("database");

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
} finally {
    em.close();
}
```

Về mặt ngữ nghĩa, database cần đạt trạng thái:

```sql
-- Một cách thực hiện có thể có:
INSERT INTO article_tags (article_id, tag_value)
VALUES (?, 'hibernate');

DELETE FROM article_tags
WHERE article_id = ? AND tag_value = 'database';
```

**Không nên khẳng định** Hibernate hay mọi JPA provider luôn phát đúng hai SQL này. Tùy collection type, cấu hình và cách provider xác định hàng đã thay đổi, nó có thể xóa/ghi lại một phần hoặc nhiều phần tử của collection. Điều quan trọng là **trạng thái sau transaction**, không phải giả định về câu lệnh cụ thể.

### 8.1. Khi collection chưa có phần tử

```java
Article article = new Article("New");
article.addTag("JPA");
article.addTag("JPA");

System.out.println(article.getTags().size()); // 1
```

`Set<String>` sử dụng `String.equals()` để loại trùng. Vì `String` bất biến, giá trị thêm vào `HashSet` có `hashCode()` ổn định. Không có vấn đề generated ID của entity ở từng tag vì phần tử ở đây **không phải entity**.

### 8.2. Có cần gọi em.persist(article) lại khi sửa tags không?

Không. Với entity đã managed, việc gọi các phương thức chỉnh sửa collection được quản lý sẽ được JPA xem xét khi flush. Không cần `em.persist` lần nữa, và `em.persist` cũng không phải một cách “lưu collection” độc lập.

Nếu Article đã **detached** vì EntityManager trước đó đóng, thay đổi trên collection detached **không tự động đồng bộ**. Có thể tải lại Article trong transaction mới rồi áp dụng thay đổi, hoặc dùng `merge` khi phù hợp và hiểu rõ cách provider merge state collection.

### 8.3. Thận trọng với việc thay thế cả collection field

Đoạn code sau có thể gây khó theo dõi:

```java
article.tags = new HashSet<>(incomingTags);
```

Nó thay tham chiếu collection đã được provider bọc/tracking. Tùy provider và mapping, việc gán cả collection có thể làm phát sinh xóa/ghi lại hàng, hoặc những vấn đề với quản lý collection, đặc biệt nếu mapping có orphan-related behavior hay cấu hình đặc thù.

Trong ứng dụng, thường nên cung cấp một phương thức domain cập nhật **collection hiện tại** theo tập giá trị đã chuẩn hóa:

```java
public void replaceTags(Set<String> inputs) {
    Objects.requireNonNull(inputs);

    Set<String> normalized = new HashSet<>();
    for (String input : inputs) {
        normalized.add(normalizeTag(input));
    }

    tags.clear();
    tags.addAll(normalized);
}
```

Đây là ví dụ phương thức bổ sung trong entity `Article`; không cần gắn setter công khai. Tuy nhiên, `clear/addAll` cũng không bảo đảm provider tạo SQL tối ưu: nếu hệ thống cập nhật rất thường xuyên và collection lớn, cần quan sát số lệnh thực tế và cân nhắc mô hình khác.

### 8.4. Những thay đổi trên collection chỉ có hiệu lực bền vững sau commit

```text
tx.begin()
  |
  +-- load Article (managed)
  +-- article.addTag("jpa")
  +-- article.removeTag("legacy")
  |
  +-- flush có thể đồng bộ SQL
  |
  +-- tx.commit() -> dữ liệu được xác nhận
      hoặc
      tx.rollback() -> không giữ thay đổi chưa commit
```

`flush()` không tương đương commit. Nếu provider đã chèn/xóa hàng `article_tags` trong transaction rồi transaction rollback, kết quả được hoàn tác theo quy tắc cơ sở dữ liệu.

## 9. Set<String>: tập giá trị không trùng

`Set` thích hợp khi **tính duy nhất** là một phần của nghiệp vụ và **thứ tự không quan trọng**.

Ví dụ:

```java
@ElementCollection
@CollectionTable(
    name = "article_tags",
    joinColumns = @JoinColumn(name = "article_id")
)
@Column(name = "tag_value", nullable = false, length = 40)
private Set<String> tags = new HashSet<>();
```

Các đặc điểm:

- Trong Java, `Set` không lưu hai phần tử được xem là bằng nhau.
- `HashSet` không bảo toàn thứ tự duyệt.
- Để độc lập với trạng thái Java và bảo vệ dữ liệu khỏi ghi trực tiếp, thêm constraint `UNIQUE(article_id, tag_value)` vào schema nếu nghiệp vụ cần.
- Một tag `"Java"` và `"java"` là **khác nhau** theo `String.equals()`. Nếu domain muốn không phân biệt chữ hoa/thường, chuẩn hóa đầu vào trước khi thêm; có thể bổ sung chính sách collation/index ở database.

### 9.1. Set không thay thế ràng buộc trong database

Giả sử có hai transaction:

```text
Transaction A                   Transaction B
-------------                   -------------
load Article#10                 load Article#10
addTag("new-tag")               addTag("new-tag")
commit                          commit
```

`Set` trong mỗi persistence context chỉ biết dữ liệu của transaction đó. Nếu database không có unique constraint và không có concurrency policy phù hợp, không thể dựa vào Java Set để loại trùng trong mọi tình huống concurrent write.

Với invariant “mỗi Article có tối đa một hàng cho mỗi tag”, dùng unique constraint `(article_id, tag_value)` và xử lý lỗi conflict trong transaction. Có thể dùng `@Version` trên owner để phát hiện một số cập nhật cạnh tranh, nhưng kết quả cụ thể khi thay đổi collection phụ thuộc mapping/provider và phương thức cập nhật. Constraint ở database vẫn là lớp bảo vệ quan trọng.

### 9.2. Khi một nhãn cần identity riêng

Nếu cần một danh mục tag có ID, mô tả, tên hiển thị, người tạo hoặc tag được chia sẻ với trạng thái riêng, `String` không còn biểu đạt đầy đủ mô hình. Khi đó có thể cần `Tag` là `@Entity` và association `@ManyToMany` hoặc entity bảng nối.

`@ElementCollection` hợp với **giá trị thuộc owner** hơn là những đối tượng cần lifecycle độc lập.

## 10. List<String>: danh sách có thể trùng và có thể cần thứ tự

Nếu thứ tự phần tử có ý nghĩa, ví dụ các bước hướng dẫn hoặc danh sách gợi ý hiển thị theo thứ tự người dùng sắp xếp, `List<String>` có thể phù hợp.

```java
@ElementCollection
@CollectionTable(
    name = "article_keywords",
    joinColumns = @JoinColumn(name = "article_id")
)
@Column(name = "keyword_value", nullable = false, length = 80)
private List<String> keywords = new ArrayList<>();
```

Một `List` cho phép phần tử trùng và có chỉ số khi dùng Java. **Nhưng việc lưu List không tự bảo đảm thứ tự duyệt sẽ giữ nguyên sau khi tải lại từ database** nếu không có mapping lưu thứ tự. SQL table không có khái niệm thứ tự hàng mặc định.

### 10.1. Dùng @OrderColumn để lưu vị trí

```java
@ElementCollection
@CollectionTable(
    name = "article_steps",
    joinColumns = @JoinColumn(name = "article_id")
)
@OrderColumn(name = "step_position")
@Column(name = "step_text", nullable = false, length = 500)
private List<String> steps = new ArrayList<>();
```

Bảng phụ có thể là:

```text
article_steps
+------------+---------------+------------------------+
| article_id | step_position | step_text              |
+------------+---------------+------------------------+
| 10         | 0             | Tạo entity             |
| 10         | 1             | Thêm mapping           |
| 10         | 2             | Chạy transaction       |
+------------+---------------+------------------------+
```

`@OrderColumn` lưu vị trí phần tử vào một cột riêng. Provider quản lý giá trị chỉ số trong quá trình cập nhật collection. Về mặt dữ liệu, thứ tự thuộc về **vị trí trong danh sách**, không phải thứ tự từ điển của `step_text`.

### 10.2. Điều gì xảy ra khi chèn vào đầu danh sách?

Giả sử:

```java
steps.add(0, "Chuẩn bị project");
```

Các vị trí cũ có thể phải được cập nhật:

```text
Trước:
0 -> "Tạo entity"
1 -> "Thêm mapping"
2 -> "Chạy transaction"

Sau:
0 -> "Chuẩn bị project"
1 -> "Tạo entity"
2 -> "Thêm mapping"
3 -> "Chạy transaction"
```

Vì chỉ số của nhiều hàng thay đổi, provider có thể phát nhiều SQL. Đối với danh sách dài và thường chèn/xóa giữa danh sách, việc dùng `@OrderColumn` có thể tạo chi phí đáng kể.

Nếu ứng dụng cần thứ tự bền vững nhưng mỗi phần tử còn có metadata riêng như thời điểm tạo, trạng thái và quyền chỉnh sửa, một entity con có cột vị trí do domain quản lý có thể phù hợp hơn.

### 10.3. @OrderColumn khác @OrderBy

- `@OrderColumn` **lưu vị trí List** trong một cột do provider quản lý. Thứ tự được duy trì theo thay đổi vị trí phần tử.
- `@OrderBy` diễn đạt cách **sắp xếp kết quả truy xuất** theo giá trị/thuộc tính, không nhất thiết lưu vị trí do người dùng tùy ý sắp đặt.

Với basic value collection, cú pháp `@OrderBy` và khả năng ordering tùy các quy tắc của đặc tả/provider; khi cần giữ thứ tự list như trong Java, `@OrderColumn` là giải pháp rõ ràng hơn.

Đừng đặt `@OrderColumn` lên `Set` chỉ vì muốn kết quả duyệt có thứ tự: Set không đại diện tự nhiên cho một chuỗi vị trí có thể trùng. Hãy chọn collection type phù hợp nghiệp vụ trước.

### 10.4. Khi không có @OrderColumn

Nếu domain **không cần bảo toàn thứ tự**, `List<String>` có thể mang ý nghĩa giống một bag (cho phép trùng) ở góc nhìn persistence. Điều đó ảnh hưởng cách provider xác định từng hàng khi xóa một phần tử, vì các giá trị trùng nhau khó được phân biệt nếu bảng không có vị trí hoặc ID hàng độc lập.

Với provider như Hibernate, thay đổi một bag có thể dẫn đến việc xóa/ghi lại nhiều hàng hơn mong đợi. Đây là một lý do phải quan sát SQL, nhất là với collection lớn.

## 11. Map<String, String>: lưu cặp khóa–giá trị cơ bản

Một Article có thể có metadata đơn giản như:

```text
{"language": "vi", "format": "markdown", "difficulty": "beginner"}
```

Nếu metadata chỉ là các chuỗi thuộc Article, không cần entity riêng cho mỗi cặp, có thể dùng `@ElementCollection` trên `Map<String, String>`.

### 11.1. Mapping Map

```java
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapKeyColumn;

import java.util.HashMap;
import java.util.Map;

@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "article_metadata",
    joinColumns = @JoinColumn(name = "article_id")
)
@MapKeyColumn(name = "meta_key", length = 60)
@Column(name = "meta_value", length = 300)
private Map<String, String> metadata = new HashMap<>();
```

Annotation có các vai trò khác nhau:

| Thành phần | Cột trong `article_metadata` |
|---|---|
| `@JoinColumn(name = "article_id")` | Khóa ngoại về owner `Article` |
| `@MapKeyColumn(name = "meta_key")` | **Khóa** của mỗi entry trong `Map` |
| `@Column(name = "meta_value")` | **Giá trị** của mỗi entry |
| `@ElementCollection` | Gắn toàn bộ map với lifecycle của owner |

DDL minh họa:

```sql
CREATE TABLE article_metadata (
    article_id BIGINT NOT NULL,
    meta_key VARCHAR(60) NOT NULL,
    meta_value VARCHAR(300),

    CONSTRAINT fk_article_metadata_article
        FOREIGN KEY (article_id) REFERENCES articles(id),

    CONSTRAINT uq_article_metadata_key
        UNIQUE (article_id, meta_key)
);
```

Ở đây `Map` có **mỗi key một value** trong Java. Muốn bảo vệ tính duy nhất của mỗi key dưới database, nên đặt unique constraint theo `(article_id, meta_key)`. Việc có/không cho phép `meta_value = NULL` phải được xác định theo domain.

### 11.2. Thêm và xóa entry

Trong một class owner, có thể viết:

```java
public void putMetadata(String key, String value) {
    Objects.requireNonNull(key, "key");
    Objects.requireNonNull(value, "value");

    String normalizedKey = key.trim().toLowerCase(Locale.ROOT);
    if (normalizedKey.isEmpty()) {
        throw new IllegalArgumentException("Metadata key is blank");
    }

    metadata.put(normalizedKey, value.trim());
}

public void removeMetadata(String key) {
    Objects.requireNonNull(key, "key");
    metadata.remove(key.trim().toLowerCase(Locale.ROOT));
}
```

Nếu Article đã managed, JPA theo dõi thay đổi của map và đồng bộ collection table khi flush/commit. Không gọi `em.persist` cho từng `Map.Entry`.

### 11.3. MapKeyColumn không phải MapKey của entity association

`@MapKeyColumn` lưu **key cơ bản** của map vào một cột trong collection table. Nó phù hợp với `Map<String, String>` hoặc các basic key type được hỗ trợ.

`@MapKey` thường được thảo luận khi một map association có key lấy từ **thuộc tính của entity/value**, và nó có semantics khác. Với bài toán lưu khóa String riêng trong collection table, `@MapKeyColumn` là annotation trực tiếp, dễ đọc.

### 11.4. Map khác Set và List

| Collection Java | Phần tử | Ngữ nghĩa |
|---|---|---|
| `Set<String>` | Một giá trị String | Không trùng theo equals; không có thứ tự |
| `List<String>` | Một giá trị String mỗi vị trí | Có thứ tự trong Java; cho phép trùng |
| `Map<String, String>` | Cặp `key → value` | Mỗi key là duy nhất; thay value theo key |
| `Set<Enum>` | Một giá trị enum | Không trùng; lưu qua chiến lược enum mapping |

Ví dụ `Map` không phải `List` các String dạng `"key=value"`: dùng map giúp domain truy cập theo key và database thể hiện rõ hai cột.

## 12. @ElementCollection với enum và basic type khác

`@ElementCollection` không chỉ dành cho `String`. Một entity có thể lưu tập các lựa chọn thuộc kiểu enum.

### 12.1. Tập enum

```java
public enum Channel {
    EMAIL,
    SMS,
    PUSH
}
```

Mapping:

```java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "notification_channels",
    joinColumns = @JoinColumn(name = "profile_id")
)
@Enumerated(EnumType.STRING)
@Column(name = "channel_code", nullable = false, length = 20)
private Set<Channel> channels =
    EnumSet.noneOf(Channel.class);
```

Đoạn trên là một field trong entity giả định `NotificationProfile` có `@Id` phù hợp. `EnumSet` là implementation chuyên cho enum trong Java và có thể được dùng khi khởi tạo giá trị trước persistence; provider có thể thay thế collection bằng implementation do nó quản lý.

**Nên cân nhắc `EnumType.STRING`** để lưu giá trị `"EMAIL"`, `"SMS"`, `"PUSH"`, thay vì ordinal `0`, `1`, `2`. Nếu sau này thay thứ tự phần tử trong enum, ordinal lưu trong database có nguy cơ bị diễn giải sai. Tuy nhiên, đổi tên constant cũng có thể làm dữ liệu STRING cũ không map được; cần migration và chính sách tương thích.

`EnumType.STRING` bảo đảm representation bằng tên enum theo quy tắc API, không tự cho phép đổi tên enum mà không migration.

### 12.2. Kiểu ngày và kiểu số

Tùy basic type được JPA provider hỗ trợ, bạn cũng có thể lưu:

```java
@ElementCollection
@CollectionTable(
    name = "profile_lucky_numbers",
    joinColumns = @JoinColumn(name = "profile_id")
)
@Column(name = "lucky_number", nullable = false)
private Set<Integer> luckyNumbers = new HashSet<>();
```

Với `LocalDate`, `BigDecimal` và các basic type chuẩn, mapping cột cần tương thích với JDBC/database. Khi dùng kiểu ngày–giờ, cần phân biệt ngày lịch `LocalDate` với thời điểm có timezone/UTC; đừng mặc định mọi kiểu thời gian đều cùng semantics.

Nếu giá trị cần thêm quy tắc domain riêng (ví dụ mã quốc gia đã chuẩn hóa), có thể dùng value object và converter phù hợp, nhưng khả năng áp dụng converter cho phần tử collection cần được khai báo đúng nơi và kiểm tra theo phiên bản Jakarta Persistence/provider đang dùng. Bài này chủ yếu dùng basic types tiêu chuẩn để tránh trộn lẫn yêu cầu ánh xạ đặc thù.

### 12.3. @Enumerated và @MapKeyEnumerated

Khi **giá trị phần tử** là enum, `@Enumerated(EnumType.STRING)` thường là lựa chọn rõ ràng. Khi **key của Map** là enum, JPA có `@MapKeyEnumerated` dành cho cách lưu key.

Ví dụ:

```java
@ElementCollection
@CollectionTable(
    name = "localized_titles",
    joinColumns = @JoinColumn(name = "article_id")
)
@MapKeyEnumerated(EnumType.STRING)
@MapKeyColumn(name = "language_code")
@Column(name = "localized_title")
private Map<Language, String> localizedTitles =
    new HashMap<>();
```

`Language` là enum được ứng dụng định nghĩa, chẳng hạn `VI`, `EN`. Ví dụ trên cần đặt trong entity `Article`, khai báo enum và migration cho bảng tương ứng. Mục đích là minh họa **key enum** khác **value String**.

## 13. Truy vấn phần tử cơ bản bằng JPQL

Một ưu điểm của collection table là có thể truy vấn **từng giá trị** thông qua cú pháp JPQL collection association.

### 13.1. Tìm tất cả Article có tag xác định

Cách 1 — dùng `JOIN`:

```java
List<Article> articles = em.createQuery(
    "select distinct a from Article a " +
    "join a.tags t " +
    "where t = :tag",
    Article.class)
    .setParameter("tag", "jpa")
    .getResultList();
```

`t` ở đây đại diện **phần tử String** trong collection, không phải entity `Tag`. Provider tạo phép nối với collection table theo mapping.

`distinct` có thể hữu ích khi một query join với nhiều phần tử tạo hàng lặp ở kết quả; với predicate khớp một tag trong một Set unique, số bản ghi cụ thể tùy dữ liệu và cấu trúc query.

Cách 2 — dùng `MEMBER OF`:

```java
List<Article> articles = em.createQuery(
    "select a from Article a " +
    "where :tag member of a.tags",
    Article.class)
    .setParameter("tag", "jpa")
    .getResultList();
```

`MEMBER OF` diễn đạt “giá trị có là một phần tử của collection này không?”. Với basic collection, đây là cách diễn đạt trực tiếp, không cần viết tên bảng phụ ở tầng JPQL.

### 13.2. Đếm phần tử

```java
List<Article> results = em.createQuery(
    "select a from Article a " +
    "where size(a.tags) >= :minimum",
    Article.class)
    .setParameter("minimum", 3)
    .getResultList();
```

`SIZE(a.tags)` trả kích thước collection theo ngữ nghĩa JPQL. Provider chuyển sang SQL phù hợp (thường có subquery hoặc cách tối ưu tương đương).

Nếu điều kiện đếm và lọc rất thường xuyên trên bảng phụ lớn, hãy xem query plan và chỉ số cần thiết.

### 13.3. Query theo key/value trong Map

Với `Article.metadata` là `Map<String, String>`:

```java
List<Article> markdownArticles = em.createQuery(
    "select distinct a from Article a " +
    "join a.metadata m " +
    "where key(m) = :key " +
    "and value(m) = :value",
    Article.class)
    .setParameter("key", "format")
    .setParameter("value", "markdown")
    .getResultList();
```

`KEY(m)` lấy key của map entry, còn `VALUE(m)` lấy value. Các hàm này thuộc ngữ nghĩa JPQL cho map-valued association và không phải hàm SQL trực tiếp trên một cột JSON.

### 13.4. Query trả về giá trị String

Nếu cần chỉ danh sách tag của Article, có thể chọn phần tử:

```java
List<String> tags = em.createQuery(
    "select t from Article a join a.tags t " +
    "where a.id = :articleId",
    String.class)
    .setParameter("articleId", articleId)
    .getResultList();
```

Ở đây kết quả là `List<String>`, không phải `List<Tag>`. Cách query riêng có thể có lợi khi API chỉ cần vài giá trị, không cần load toàn bộ Article.

### 13.5. Tránh dùng native SQL mà quên join condition

Trong SQL thuần:

```sql
SELECT a.id, a.title
FROM articles AS a
JOIN article_tags AS t
  ON t.article_id = a.id
WHERE t.tag_value = 'jpa';
```

Nếu dùng native SQL, application chịu trách nhiệm viết điều kiện join, column names và chính sách tenant (nếu có). Với JPQL, provider suy ra liên kết từ mapping.

## 14. Fetching, N+1 và chiến lược tải dữ liệu

Giả sử API hiển thị 100 bài viết, mỗi bài có 20 tag.

```java
List<Article> articles = em.createQuery(
    "select a from Article a", Article.class)
    .getResultList();

for (Article a : articles) {
    System.out.println(a.getTags().size());
}
```

Với lazy collection, một truy vấn tải 100 Article có thể kèm nhiều truy vấn phụ để tải tags khi vòng lặp lần lượt chạm vào collection. Đó là dạng **N+1**:

```text
1 query: SELECT articles ...
N query: SELECT article_tags WHERE article_id = ?
```

Không phải mọi provider và cấu hình đều đúng chính xác N+1 query: có thể có batch fetching, cache hoặc subselect optimization. Cần xem log SQL thay vì kết luận từ annotation.

### 14.1. Fetch join khi thực sự cần tập tag

```java
List<Article> articles = em.createQuery(
    "select distinct a from Article a " +
    "left join fetch a.tags",
    Article.class)
    .getResultList();
```

`LEFT JOIN FETCH` giúp tải collection trong truy vấn chính theo cơ chế JPA. Tuy nhiên, nếu mỗi Article có nhiều tag, SQL JOIN có thể nhân số hàng:

```text
Article#1 có 10 tag -> có thể tạo 10 hàng ở kết quả SQL.
Article#2 có 20 tag -> có thể tạo 20 hàng ở kết quả SQL.
```

JPA/provider cần tái dựng entity và collection từ các hàng này. `distinct` trong JPQL giúp diễn đạt kết quả entity duy nhất; chi tiết đẩy `DISTINCT` xuống SQL phụ thuộc provider/phiên bản.

**Cần thận trọng khi phân trang cùng collection fetch join.** Giới hạn số hàng SQL không đồng nghĩa giới hạn số Article gốc; một số provider phải xử lý pagination trong bộ nhớ hoặc từ chối một số cấu hình. Với trang dữ liệu lớn, thường nên phân trang ID/entity trước rồi tải collection cho tập kết quả nhỏ qua query thứ hai.

### 14.2. Khi có nhiều collection

Một Article có thể có cả `tags`, `steps` và `metadata`. Fetch join nhiều collection cùng lúc có thể tạo phép nhân Cartesian:

```text
Article có 10 tags và 8 steps
-> join cả hai collection có thể tạo khoảng 80 hàng SQL.
```

Một số provider (đặc biệt Hibernate) còn có giới hạn khi fetch đồng thời nhiều bag, ví dụ lỗi liên quan **multiple bag fetch**.

Do đó, không dùng một câu query fetch toàn bộ mọi collection như quy tắc mặc định. Chọn dữ liệu thực sự cần cho use case, dùng query/projection/batch fetching phù hợp và quan sát số hàng SQL.

### 14.3. Không đổi tất cả sang EAGER

`@ElementCollection(fetch = FetchType.EAGER)` yêu cầu provider tải collection eagerly, nhưng có thể làm chi phí tăng trên những đường code **không cần** giá trị collection. EAGER không bảo đảm một SQL duy nhất; provider có thể dùng các query bổ sung.

Ưu tiên thiết kế **fetch plan theo use case**: ví dụ màn hình danh sách chỉ cần title/count, còn màn hình chi tiết mới cần tags và metadata.

## 15. Vòng đời của basic elements gắn với owner

Đây là khác biệt lớn giữa `@ElementCollection` và association đến entity.

### 15.1. Persist owner

```java
Article article = new Article("JPA");
article.addTag("java");
article.addTag("orm");

em.persist(article);
```

Provider lưu Article và các hàng thuộc `article_tags` theo transaction. Không có `Tag` entity cần `persist` riêng.

### 15.2. Gỡ một phần tử

```java
article.removeTag("orm");
```

Điều này có nghĩa hàng giá trị `"orm"` thuộc Article sẽ không còn trong collection sau khi đồng bộ thành công. **Không có entity `Tag`** bị đánh dấu removed trong persistence context, vì tag chỉ là một basic value.

### 15.3. Xóa owner

```java
Article managed = em.find(Article.class, articleId);

if (managed != null) {
    em.remove(managed);
}
```

Vì các hàng trong collection table thuộc owner, JPA/provider phải xử lý dữ liệu collection tương ứng khi xóa Article, hoặc phối hợp với database FK/cascade tùy cấu hình. Sau transaction thành công, không còn các hàng `article_tags` thuộc Article đã xóa.

**Không cần** `cascade = CascadeType.REMOVE` trên `@ElementCollection`; annotation này không định nghĩa thuộc tính `cascade` giống `@OneToMany`.

### 15.4. Tách giá trị khỏi owner có làm mất giá trị ở nơi khác không?

Nếu hai Article đều có tag `"jpa"`, database có thể lưu hai hàng:

```text
(10, "jpa")
(20, "jpa")
```

Xóa tag của Article#10 **không xóa tag của Article#20**, vì đây là **hai hàng giá trị thuộc hai owner**. Chuỗi Java `"jpa"` không có ID và lifecycle chung.

Ngược lại, nếu hệ thống dùng entity `Tag` chung cho toàn bộ bài viết, sẽ có bảng `tags` và bảng nối; việc gỡ liên kết giữa một Article và Tag không mặc nhiên xóa entity Tag đó.

## 16. Collection value khác entity relationship

Để chọn đúng annotation, cần xác định phần tử có identity/lifecycle riêng không.

| Nhu cầu | Cơ chế JPA nên cân nhắc |
|---|---|
| Article có các tag String riêng, chỉ quan tâm giá trị | `@ElementCollection Set<String>` |
| User có danh sách số nguyên lựa chọn | `@ElementCollection List<Integer>` |
| Article có map metadata String → String | `@ElementCollection Map<String,String>` |
| Order có OrderLine là entity với ID, trạng thái và lifecycle | `@OneToMany` |
| Article chia sẻ các Tag entity có mô tả/trạng thái riêng | `@ManyToMany` hoặc entity liên kết |
| Một value object gồm nhiều field thuộc owner | `@Embedded` hoặc `@ElementCollection` của embeddable |
| Một collection được lưu thành một cột JSON/text | Converter/JDBC type/provider-specific mapping khi phù hợp |

### 16.1. ElementCollection không phải @OneToMany

```java
// Basic elements:
@ElementCollection
private Set<String> tags;

// Entity association:
@OneToMany(mappedBy = "article")
private List<Comment> comments;
```

`String` không có `@Id` hay `EntityManager.find(String.class, ...)`. `Comment` nếu được khai báo `@Entity` sẽ có identity và có thể có lifecycle riêng. Không dùng `@OneToMany` cho `Set<String>` nếu String chỉ là giá trị cơ bản.

### 16.2. ElementCollection không phải AttributeConverter

Một `AttributeConverter<Set<String>, String>` tự viết có thể biến cả collection thành một chuỗi, nhưng JPA lúc ấy nhìn nó như **một basic attribute lưu trong một cột**, không phải một collection table với từng hàng giá trị.

Hệ quả:

- Query theo phần tử không còn dùng tự nhiên `JOIN a.tags` như `@ElementCollection`.
- Schema không có FK và một hàng riêng cho từng tag.
- Mỗi thay đổi nhỏ có thể cần ghi lại toàn bộ chuỗi/JSON.
- Tính tương thích với SQL index, constraint và cách migrate khác đi.

Khi cần tương tác quan hệ với từng phần tử, `@ElementCollection` thường diễn đạt tốt hơn. Khi cần lưu một cấu trúc nguyên khối trong một cột và database có khả năng phù hợp, converter/JSON mapping có thể có lợi.

### 16.3. Khi nào không nên dùng ElementCollection?

Hãy cân nhắc một entity con thay vì basic value nếu mỗi phần tử cần:

- ID để tham chiếu độc lập.
- Người tạo, ngày tạo, trạng thái xử lý hoặc lịch sử thay đổi.
- Optimistic locking riêng.
- API CRUD độc lập.
- Được nhiều owner chia sẻ cùng một bản ghi.
- Lượng dữ liệu lớn, thường cập nhật từng phần tử và cần hiệu năng SQL tinh chỉnh.

Không nên tạo entity chỉ để tránh chú thích `@ElementCollection`, nhưng cũng không nên ép một khái niệm có identity rõ ràng thành `String`.

## 17. Thiết kế schema: constraint, index và nullability

Các basic values không có khóa chính riêng theo mô hình entity; nhưng schema vẫn có thể dùng **primary key hoặc unique constraint ở collection table** để quản lý tính nhất quán.

### 17.1. Unique cho Set

Nếu Set lưu tag không trùng trong phạm vi một owner:

```sql
ALTER TABLE article_tags
ADD CONSTRAINT uq_article_tags_value
UNIQUE (article_id, tag_value);
```

Cặp cột làm unique giúp tránh hai hàng giống nhau. Không nhất thiết phải khai báo primary key là chính cặp này, nhưng có thể là lựa chọn schema phù hợp nếu giá trị hoàn toàn định danh hàng trong tập.

### 17.2. Index cho query ngược từ tag đến Article

Nếu query thường là “tìm mọi Article có tag java”, index:

```sql
CREATE INDEX idx_article_tags_value
ON article_tags (tag_value, article_id);
```

có thể hữu ích, tùy optimizer/workload. Trong khi đó, index `(article_id, tag_value)` phục vụ tốt các truy vấn lấy tags theo article và kiểm tra uniqueness theo owner.

Thứ tự cột trong composite index ảnh hưởng cách query sử dụng index. Hãy xem `EXPLAIN` và dữ liệu thực tế trước khi quyết định chỉ số.

### 17.3. Null elements và null keys

Với `Set<String>` hoặc `List<String>`, Java có thể chấp nhận `null` tùy implementation; nhưng database column có thể `NOT NULL`. Domain nên quyết định có cho phần tử null hay không. Một tag null thường không có ý nghĩa, nên factory/helper nên từ chối nó.

Với `Map<String, String>`, không nên mặc định null key hợp lệ ở database. Nếu `meta_key` là thành phần unique/primary key logic, thường nên để `NOT NULL`. Null value có thể hợp lệ nếu domain muốn phân biệt “key có tồn tại nhưng giá trị chưa xác định” với “key không tồn tại”; nếu không, từ chối null value để tránh mơ hồ.

### 17.4. Index và constraint trong JPA hay trong migration?

Có thể dùng metadata JPA như `@CollectionTable(uniqueConstraints = ...)` trong cấu hình, nhưng database có thể khác nhau về DDL sinh ra. Với hệ thống production, migration là nơi rõ ràng hơn để quản lý PK/FK/UNIQUE/INDEX và các quy tắc triển khai.

Ví dụ nếu muốn metadata unique trong collection table:

```java
@CollectionTable(
    name = "article_tags",
    joinColumns = @JoinColumn(name = "article_id"),
    uniqueConstraints = @UniqueConstraint(
        columnNames = {"article_id", "tag_value"}
    )
)
```

Cần import `jakarta.persistence.UniqueConstraint` và bảo đảm tên cột khớp `@Column(name="tag_value")`. Metadata không thay thế kiểm tra schema thực tế.

## 18. Trường hợp owner dùng khóa chính ghép

Nếu entity owner có `@EmbeddedId` gồm nhiều cột, collection table cũng phải chứa **đủ các cột join** để xác định owner.

Ví dụ một `Customer` có khóa `(tenant_id, customer_code)`, và tập ngôn ngữ yêu thích:

```java
@ElementCollection
@CollectionTable(
    name = "customer_languages",
    joinColumns = {
        @JoinColumn(
            name = "tenant_id",
            referencedColumnName = "tenant_id"
        ),
        @JoinColumn(
            name = "customer_code",
            referencedColumnName = "customer_code"
        )
    }
)
@Column(name = "language_code", nullable = false)
private Set<String> languages = new HashSet<>();
```

Schema:

```sql
CREATE TABLE customer_languages (
    tenant_id VARCHAR(36) NOT NULL,
    customer_code VARCHAR(32) NOT NULL,
    language_code VARCHAR(10) NOT NULL,

    FOREIGN KEY (tenant_id, customer_code)
        REFERENCES customers(tenant_id, customer_code),

    UNIQUE (tenant_id, customer_code, language_code)
);
```

Đây là một collection của **basic String** vẫn được sở hữu bởi một entity có composite PK. `@JoinColumn.name` là cột trong **collection table**, `referencedColumnName` là cột trong bảng owner. Không được bỏ một phần khóa ghép nếu nó cần thiết để xác định một customer duy nhất.

## 19. Vấn đề hiệu năng khi cập nhật collection

Một collection có 5 phần tử và một collection có 50.000 phần tử không nên được quản lý giống nhau.

### 19.1. Vì sao UPDATE nhỏ có thể tạo nhiều SQL?

Khác với entity con có `@Id` riêng, một giá trị String trong collection table có thể không có một surrogate key để provider chỉ rõ hàng cần cập nhật. Tùy mapping, collection type và provider, thay đổi phần tử có thể được biểu diễn thành:

- `INSERT` một hàng mới.
- `DELETE` một hàng theo owner + giá trị.
- `DELETE` nhiều hàng rồi `INSERT` lại các hàng hiện có.
- `UPDATE` hoặc tổ chức lại các vị trí của `List` có `@OrderColumn`.

Ví dụ thay một giá trị trong `List<String>` với các giá trị trùng hoặc không có order column có thể khiến provider khó xác định hàng nào cần sửa một cách riêng biệt.

### 19.2. Có nên dùng Set thay List để tối ưu?

Chọn `Set` nếu **nghiệp vụ cấm trùng**. Chọn `List` nếu **nghiệp vụ cần thứ tự hoặc phần tử trùng**. Không đổi semantics nghiệp vụ chỉ để hy vọng provider sinh SQL ít hơn.

Tuy nhiên, cấu trúc và tính duy nhất của phần tử có thể ảnh hưởng mạnh đến khả năng provider xác định phần tử bị thay đổi. Đối với workload quan trọng, phải đo SQL thực tế với loại collection và provider đã chọn.

### 19.3. Collection lớn không nên tải hết vào RAM để xóa một giá trị

Nếu Article có hàng trăm nghìn tag (một mô hình có thể đã cần xem lại), cách:

```java
Article article = em.find(Article.class, articleId);
article.removeTag("obsolete");
```

có thể buộc tải cả collection tùy provider. Nếu cần cập nhật một hàng riêng lẻ với hiệu năng cao, cân nhắc entity con có ID, repository riêng, hoặc SQL chuyên biệt trong một transaction được kiểm soát. Những giải pháp đó cần xử lý đồng bộ persistence context và invariant, không phải chỉ thay một annotation.

### 19.4. JDBC batching có giúp không?

Nếu provider có thể gom nhiều `INSERT`/`DELETE` collection values, batching có thể giảm round-trip. Nhưng tính hiệu quả phụ thuộc provider, driver, kiểu generator của owner, transaction, SQL ordering và kích thước collection. Đừng suy luận “đã dùng `@ElementCollection` tức là tự động batch mọi phần tử”.

Quan sát số SQL statement, JDBC batch metrics, network latency và DB execution plan nếu performance là yêu cầu.

## 20. Đồng thời và tính nhất quán khi nhiều transaction sửa cùng collection

Giả sử hai request cùng sửa tags của Article#10:

```text
Transaction A: đọc tags = {"java"}
Transaction B: đọc tags = {"java"}

A thêm "jpa"
B thêm "orm"

A commit
B commit
```

Kết quả cuối cùng có thể phụ thuộc provider, cách tracking collection, isolation và concurrency control. Không nên tự động kỳ vọng luôn có cả `"jpa"` và `"orm"` khi hai transaction cùng sửa collection trên cùng owner.

### 20.1. @Version trên owner

Một cách phổ biến để hỗ trợ optimistic locking là đặt version trên Article:

```java
@Version
private Long version;
```

Khi provider theo dõi thay đổi collection và tăng version của owner theo mapping, một transaction khác có thể phát hiện version conflict. Nhưng cơ chế chính xác đối với **thay đổi collection riêng** có thể phụ thuộc provider/cấu hình, vì vậy cần kiểm thử trên stack hiện tại.

Nếu ứng dụng có đường ghi **native SQL** trực tiếp vào bảng phụ, nó có thể không làm tăng version owner một cách tự động. Khi đó phải có chính sách cập nhật version hoặc phối hợp transaction riêng.

### 20.2. Unique constraint cho invariant cứng

Dù có optimistic locking, constraint `UNIQUE(article_id, tag_value)` vẫn cần thiết khi domain cấm tag trùng. Hai transaction có thể cùng cố thêm một tag: database constraint là lớp kiểm tra cuối cùng cho dữ liệu đã commit.

### 20.3. Không xử lý lỗi bằng cách bỏ commit hoặc flush

Nếu flush/commit ném exception do unique/FK/NOT NULL, hãy rollback transaction và xử lý conflict rõ ràng. Không tiếp tục dùng cùng transaction đã bị đánh dấu rollback-only để ghi các giá trị khác. Lỗi database là tín hiệu về quy tắc dữ liệu, không phải vấn đề có thể giải quyết bằng cách bỏ qua `em.flush()`.

## 21. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tạo được bảng collection | Tên `@CollectionTable`/`@JoinColumn` không khớp schema, quyền DB hoặc migration | Kiểm tra DDL thực, mapping và tên cột |
| Collection được lưu nhưng không có phần tử | Owner chưa được persist/commit, chưa sửa managed entity, hoặc transaction rollback | Kiểm tra transaction và trạng thái managed |
| Tag trùng xuất hiện trong DB | Không có unique constraint, SQL trực tiếp bỏ qua Set | Thêm constraint và xử lý dữ liệu cũ |
| `List` tải lại sai thứ tự | Không lưu vị trí, thiếu `@OrderColumn` | Lưu thứ tự theo nhu cầu domain |
| Lỗi nullability khi insert value | Cột `@Column(nullable=false)` nhận null | Validation trước khi add, xem schema |
| `LazyInitializationException` | Truy cập collection lazy sau khi EM đóng | Fetch/DTO trong context còn mở |
| N+1 khi đọc danh sách Article | Truy cập từng lazy collection | Fetch plan, batch/subselect phù hợp |
| Thay một tag lại sinh nhiều DELETE/INSERT | Provider xử lý collection theo snapshot/loại collection | Đo SQL, cân nhắc mô hình có identity riêng |
| `@ManyToMany`/`@OneToMany` bị dùng cho String | Phần tử là basic type, không phải entity | Chuyển sang `@ElementCollection` |
| Tên cột map key/value bị đảo | Dùng `@Column` cho key hoặc nhầm `@MapKeyColumn` | MapKeyColumn → key, Column → value |
| Chạy query theo `tag_value` trong JPQL bị lỗi | JPQL dùng tên field, không dùng tên cột SQL | Dùng `join a.tags t`, `t` hoặc `member of` |
| Đổi tên enum làm load thất bại | Dữ liệu EnumType.STRING còn tên cũ | Migration dữ liệu enum |
| Collection quá lớn và tốn RAM | Load hết collection khi chỉ cần một giá trị | Query/projection/thiết kế lại persistence |
| Xóa owner bị lỗi FK | Schema hoặc provider chưa xử lý hàng phụ theo chính sách | Xem FK, transaction, DDL và mapping |
| Map có entry cùng key nhiều lần do SQL trực tiếp | Thiếu unique constraint ở collection table | `UNIQUE(owner_id, map_key)` |
| Collection detached đổi nhưng không lưu | Không thuộc managed persistence context | Tải lại owner/merge theo chính sách rõ ràng |

### 21.1. Đừng nhầm @Column với @JoinColumn

```java
@CollectionTable(
    name = "article_tags",
    joinColumns = @JoinColumn(name = "article_id")
)
@Column(name = "tag_value")
```

`article_id` định danh **owner**. `tag_value` là **một phần tử String**. Nếu hai cột bị khai báo nhầm, provider có thể tạo schema không đúng hoặc báo lỗi mapping.

### 21.2. Không gắn @Id lên từng String

Một `String` không phải `@Entity`. Không có cách viết ý nghĩa như:

```java
@ElementCollection
@Id // Không đúng trên collection value theo mục đích này.
private Set<String> tags;
```

`@Id` định danh một entity; không tạo identity riêng cho phần tử basic trong element collection. Nếu từng phần tử cần ID, hãy định nghĩa entity con phù hợp.

### 21.3. Thứ tự của HashSet không ổn định

```java
Set<String> tags = new HashSet<>();
tags.add("java");
tags.add("jpa");
tags.add("database");
```

Không bảo đảm lúc nào in collection cũng theo thứ tự vừa thêm, càng không bảo đảm database trả theo thứ tự đó. Nếu UI cần thứ tự chữ cái, sắp xếp khi tạo DTO hoặc dùng query có `ORDER BY` tương ứng.

### 21.4. Đừng giả định default table name là hợp đồng schema

Nếu không khai báo `@CollectionTable(name=...)`, provider tạo tên dựa trên entity/attribute và naming strategy. Khi đổi tên Java field hoặc thay provider/naming convention, schema có thể không còn khớp.

Chỉ định tên bảng/cột rõ ràng giúp migration và quan sát SQL dễ quản lý hơn.

## 22. Bài thực hành: Set, List và Map trong một dự án

Xây một ứng dụng Java SE với H2/Hibernate hoặc database JPA tương thích. Mục tiêu là quan sát dữ liệu trong **bảng phụ** và thay đổi của **managed collection**.

### Phần A — Set<String> tags

1. Tạo entity `Article` và mapping `Set<String> tags` theo phần 4.
2. Tạo Article có các tag `"JPA"`, `"java"`, `" java "`.
3. Persist và commit.
4. Kiểm tra Java Set chỉ còn các tag sau chuẩn hóa.
5. Chạy SQL đọc `article_tags` và xác nhận mỗi tag thuộc đúng Article.
6. Mở EntityManager mới, load Article, thêm `"orm"` và xóa `"jpa"`, commit.
7. Quan sát SQL phát ra khi thay đổi collection.
8. Thử thêm tag trùng trực tiếp bằng SQL để xem unique constraint hoạt động.

### Phần B — List<String> có thứ tự

1. Thêm field `steps` vào Article, mapping bằng `@ElementCollection`, `@CollectionTable` và `@OrderColumn`.
2. Tạo các bước `"A"`, `"B"`, `"C"`.
3. Commit, kiểm tra cột `step_position`.
4. Tải lại Article, xác nhận thứ tự.
5. Chèn `"X"` vào vị trí đầu và commit.
6. Quan sát số SQL ảnh hưởng đến vị trí.
7. Tạo biến thể không có `@OrderColumn` trong môi trường thử nghiệm và ghi nhận rằng không có hợp đồng bảo toàn thứ tự truy xuất.

### Phần C — Map<String, String>

1. Thêm `metadata` như phần 11.
2. Ghi `("language", "vi")` và `("format", "markdown")`.
3. Commit, kiểm tra bảng `article_metadata` có các cột `article_id`, `meta_key`, `meta_value`.
4. Đổi `"format"` thành `"html"`, commit.
5. Xóa `"language"`, commit.
6. Truy vấn Article có `KEY(m)="format"` và `VALUE(m)="html"` bằng JPQL.

### Phần D — LAZY và N+1

1. Tạo khoảng 20 Article, mỗi Article có vài tag.
2. Tải danh sách chỉ bằng `select a from Article a`.
3. Đếm số SQL khi lần lượt gọi `getTags().size()`.
4. So sánh với query `left join fetch a.tags`.
5. Quan sát số hàng SQL khi fetch join một Article có nhiều tag.
6. Nếu muốn phân trang, thử phương án query ID trang trước rồi fetch tags cho tập ID đó.

### Phần E — Xóa owner

1. Tạo Article có tags, steps và metadata.
2. Commit và kiểm tra các bảng phụ.
3. Trong transaction mới, xóa Article.
4. Commit, kiểm tra không còn các hàng collection thuộc Article.
5. So sánh với mô hình có entity `Tag` dùng chung: xóa liên kết không nên xóa entity Tag chung.

### Phần F — Transaction rollback

1. Bắt đầu transaction, load Article và thêm tag mới.
2. `em.flush()` để yêu cầu đồng bộ dữ liệu.
3. `tx.rollback()`.
4. Mở EntityManager mới và xác nhận tag chưa được commit.
5. Giải thích vì sao SQL được thực thi trong transaction không đồng nghĩa dữ liệu đã bền vững.

### Mẫu bảng kết quả

| Thử nghiệm | Collection type | Mapping bảng phụ | SQL có thể xuất hiện | Điều cần kiểm chứng |
|---|---|---|---|---|
| Thêm tag | `Set<String>` | `article_tags` | `INSERT` | Không trùng và owner đúng |
| Xóa tag | `Set<String>` | `article_tags` | `DELETE` hoặc thay đổi nhiều hàng | Tag còn lại đúng |
| Chèn bước đầu | `List<String>` | `article_steps` + vị trí | `INSERT/UPDATE` | Thứ tự sau khi tải lại |
| Đổi value map | `Map<String,String>` | `article_metadata` | `UPDATE` hoặc `DELETE/INSERT` | Một key có value mới |
| Lấy collection lazy | Mọi loại | Bảng phụ | `SELECT` khi truy cập | Không truy cập sau EM đóng nếu chưa load |
| Xóa Article | Mọi loại | Các bảng phụ | `DELETE` | Không còn hàng thuộc owner |
| Rollback | Mọi loại | Các bảng phụ | SQL trong transaction bị rollback | Không có dữ liệu commit mới |

**Lưu ý:** bảng ghi các khả năng SQL, không xác nhận chính xác số statement của một provider/version chưa chạy. Hãy dựa vào log JDBC, Hibernate statistics và truy vấn kiểm chứng trên database thử nghiệm.

## 23. Câu hỏi ôn tập

1. Khi nào nên chọn `@ElementCollection` thay vì `@OneToMany`?
2. Một `Set<String>` dùng `@ElementCollection` có tạo ra entity `Tag` không?
3. `@CollectionTable` và `@Column` khác nhau ở chỗ nào?
4. Cột `article_id` trong collection table có vai trò gì?
5. Vì sao `Set` không tự bảo đảm unique constraint ở database?
6. Nếu hệ thống cần thứ tự cố định của `List` khi tải lại, cần annotation nào?
7. Vì sao chèn phần tử vào đầu `List` có `@OrderColumn` có thể đắt?
8. Trong một `Map<String,String>`, `@MapKeyColumn` ánh xạ phần nào?
9. Muốn tìm Article chứa tag `"jpa"` bằng JPQL, có thể dùng những cách nào?
10. `@ElementCollection` mặc định LAZY hay EAGER? Điều gì xảy ra nếu truy cập collection chưa tải ngoài persistence context?
11. Khi owner bị xóa, các giá trị thuộc element collection phải có vòng đời ra sao?
12. Có cần `CascadeType.PERSIST` để lưu từng String trong collection không?
13. `@Enumerated(EnumType.STRING)` giúp tránh rủi ro nào so với ORDINAL?
14. Tại sao query `JOIN FETCH` nhiều collection có thể nhân số hàng kết quả?
15. Bulk SQL ghi trực tiếp bảng phụ có tự cập nhật collection đang managed không?
16. Khi entity owner dùng composite primary key, `@CollectionTable.joinColumns` phải chứa thông tin gì?
17. Nếu mỗi tag cần người tạo, thời điểm tạo và quyền xóa riêng, có nên vẫn dùng String không?
18. Tại sao nên chuẩn hóa tag trước khi lưu, và tại sao vẫn cần database constraint?
19. Khi thay đổi collection trong transaction rồi rollback, dữ liệu mới có được giữ không?
20. Điều gì quyết định nên lưu nhiều giá trị thành collection table hay một cột JSON?

## 24. Ghi nhớ trọng tâm

```text
@Entity Article
    |
    +-- id: Long
    +-- title: String
    |
    +-- @ElementCollection Set<String> tags
    |       |
    |       +-- article_tags(article_id, tag_value)
    |
    +-- @ElementCollection List<String> steps
    |       |
    |       +-- @OrderColumn
    |       +-- article_steps(article_id, step_position, step_text)
    |
    +-- @ElementCollection Map<String, String> metadata
            |
            +-- @MapKeyColumn -> meta_key
            +-- @Column       -> meta_value
            +-- article_metadata(article_id, meta_key, meta_value)

Article là Entity có identity.
Tags, steps và metadata là tập hợp basic values.
Collection table thuộc vòng đời của Article.
```

| Ý muốn thiết kế | Cách ánh xạ |
|---|---|
| Lưu nhiều String thuộc một entity | `@ElementCollection` + `@CollectionTable` + `@Column` |
| Chống trùng trong Java | `Set<String>` |
| Chống trùng bền vững ở database | `UNIQUE(owner_id, value)` |
| Lưu danh sách có vị trí | `List<String>` + `@OrderColumn` |
| Lưu key/value đơn giản | `Map<K,V>` + `@MapKeyColumn` + `@Column` |
| Lưu tập Enum | `@ElementCollection` + `@Enumerated(EnumType.STRING)` |
| Tìm entity theo phần tử | JPQL `JOIN` hoặc `MEMBER OF` |
| Tải collection theo nhu cầu | `LAZY` + fetch plan phù hợp use case |
| Phần tử có identity/lifecycle riêng | Xem xét `@OneToMany`/`@ManyToMany` thay vì basic element collection |
| Collection rất lớn/cập nhật thường xuyên | Đo SQL, xem lại schema và mô hình trước khi chọn |

**Nguyên tắc cuối cùng:** dùng `@ElementCollection` khi **phần tử chỉ là giá trị thuộc entity sở hữu**, không cần identity độc lập. Hãy mô tả rõ **bảng phụ, khóa ngoại và cột giá trị**; chọn `Set`, `List` hay `Map` theo đúng ngữ nghĩa; quyết định thứ tự, uniqueness và constraint ở database; đồng thời quan sát chi phí SQL và chiến lược fetch khi collection lớn. Cách này giúp mã Java thể hiện đúng tập hợp nghiệp vụ mà vẫn giữ cấu trúc dữ liệu quan hệ minh bạch.

