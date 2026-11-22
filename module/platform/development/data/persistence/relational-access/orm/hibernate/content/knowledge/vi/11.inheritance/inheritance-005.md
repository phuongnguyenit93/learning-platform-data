# Cột phân loại và giá trị phân loại kiểu con

Khi ánh xạ **kế thừa (inheritance)** trong JPA/Hibernate, một lớp Java có thể là lớp cha của nhiều kiểu thực thể cụ thể. Ví dụ, ứng dụng quản lý nội dung có lớp cơ sở `ContentItem` và hai kiểu con `ArticleContent` (bài viết) và `VideoContent` (video). Ở phía Java, ta dùng `extends` và tính đa hình; ở phía cơ sở dữ liệu quan hệ, Hibernate phải biết một hàng tương ứng với **kiểu Java cụ thể nào** khi đọc dữ liệu.

Với chiến lược kế thừa **một bảng cho cả hệ phân cấp** (`InheritanceType.SINGLE_TABLE`), thông tin đó thường nằm trong một **cột phân loại** (*discriminator column*). Mỗi kiểu con gắn với một **giá trị phân loại** (*discriminator value*). Hai annotation chuẩn Jakarta Persistence thể hiện cơ chế này là **`@DiscriminatorColumn`** và **`@DiscriminatorValue`**.

Bài học giải thích cách discriminator hoạt động, cách khai báo ở lớp cha và lớp con, ảnh hưởng tới cấu trúc bảng, truy vấn đa hình, những điểm khác biệt giữa `SINGLE_TABLE`, `JOINED` và `TABLE_PER_CLASS`, cùng các vấn đề bảo trì dữ liệu khi thay đổi hệ phân cấp. Ví dụ sử dụng Jakarta Persistence (`jakarta.persistence.*`) và Hibernate ORM; SQL minh họa theo PostgreSQL.

## 1. Vì sao Hibernate cần phân biệt kiểu con?

Giả sử ta có mô hình:

~~~text
                      ContentItem
                  (id, title, status)
                           |
              +------------+------------+
              |                         |
        ArticleContent             VideoContent
         (wordCount)              (durationSeconds)
~~~

Trong Java:

~~~java
ContentItem item = ...;

if (item instanceof ArticleContent article) {
    System.out.println(article.getWordCount());
} else if (item instanceof VideoContent video) {
    System.out.println(video.getDurationSeconds());
}
~~~

Đoạn mã trên cần đối tượng runtime thực sự thuộc `ArticleContent` hoặc `VideoContent`. Nếu database lưu tất cả vào một bảng, các cột `id`, `title` và `status` không đủ cho Hibernate biết phải tạo lớp nào. Một hàng với `word_count = NULL` cũng chưa chắc là video, vì giá trị có thể thiếu do dữ liệu cũ hoặc quy tắc nghiệp vụ.

Cột phân loại giải quyết bằng cách ghi rõ loại hàng:

| id | content_kind | title | status | word_count | duration_seconds |
| ---: | --- | --- | --- | ---: | ---: |
| 1 | ARTICLE | JPA cơ bản | PUBLISHED | 1250 | `NULL` |
| 2 | VIDEO | Hibernate trong 10 phút | DRAFT | `NULL` | 600 |
| 3 | ARTICLE | Ánh xạ entity | DRAFT | 2100 | `NULL` |

Trong ví dụ:

- Hàng có `content_kind = 'ARTICLE'` được ánh xạ thành `ArticleContent`.
- Hàng có `content_kind = 'VIDEO'` được ánh xạ thành `VideoContent`.
- Những cột chung cho cả hệ phân cấp nằm cùng một bảng `content_items`.
- Những cột dành riêng cho từng subtype cũng nằm ở bảng đó, thường có `NULL` đối với hàng thuộc subtype khác.

**`content_kind` là metadata định danh loại thực thể**, không phải ID của hàng. ID vẫn là `id`. Một bảng có thể có hàng `id=1` là `ArticleContent` và hàng `id=2` là `VideoContent` mà cả hai cùng thuộc hệ phân cấp `ContentItem`.

## 2. `@Inheritance` xác định chiến lược lưu kế thừa

JPA định nghĩa ba chiến lược kế thừa entity chính:

| Chiến lược | Cấu trúc bảng cơ bản | Discriminator đóng vai trò gì? |
| --- | --- | --- |
| `InheritanceType.SINGLE_TABLE` | Một bảng chứa mọi entity trong hệ phân cấp | **Thường là cơ chế chính** để Hibernate nhận biết subtype của từng hàng |
| `InheritanceType.JOINED` | Bảng cha chứa field chung, bảng con chứa field riêng, cùng khóa chính | Có thể khai báo discriminator; **không phải lúc nào cũng bắt buộc** vì subtype có thể được xác định từ các bảng con |
| `InheritanceType.TABLE_PER_CLASS` | Mỗi entity cụ thể có bảng chứa các cột cần thiết | Không có một bảng chung chứa discriminator cho mọi subtype; truy vấn đa hình thường cần kết hợp kết quả các bảng |

Ví dụ chọn chiến lược một bảng:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
public abstract class ContentItem {
    // ...
}
~~~

`@Inheritance` đặt trên **lớp entity gốc của hệ phân cấp**, không đặt trên mỗi lớp con. Nếu không khai báo chiến lược, JPA dùng mặc định `SINGLE_TABLE` cho hệ phân cấp entity, nhưng **khai báo tường minh** thường giúp người đọc hiểu đúng thiết kế.

Cần nhớ: `@DiscriminatorColumn` và `@DiscriminatorValue` không quyết định chiến lược thay cho `@Inheritance`. Chúng bổ sung thông tin phân loại theo chiến lược mà hệ phân cấp đang sử dụng.

## 3. Ví dụ hoàn chỉnh với `SINGLE_TABLE`

Ta xây dựng hệ phân cấp gồm lớp cha trừu tượng `ContentItem` và hai lớp con `ArticleContent`, `VideoContent`.

Các lớp nằm trong package:

~~~text
com.example.content.domain
  ContentItem.java
  ArticleContent.java
  VideoContent.java
~~~

### 3.1. Lớp cha khai báo cột phân loại

**`ContentItem.java`:**

~~~java
package com.example.content.domain;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorColumn;
import jakarta.persistence.DiscriminatorType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "content_items")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "content_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 16
)
public abstract class ContentItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    @Column(name = "status", nullable = false, length = 20)
    private String status;

    protected ContentItem() {
        // Constructor cho JPA/Hibernate.
    }

    protected ContentItem(String title) {
        this.title = Objects.requireNonNull(title);
        this.status = "DRAFT";
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getStatus() {
        return status;
    }

    public void publish() {
        this.status = "PUBLISHED";
    }

    public void rename(String newTitle) {
        this.title = Objects.requireNonNull(newTitle);
    }
}
~~~

Ý nghĩa:

- `@Entity`: lớp cha là entity type trong mô hình JPA, dù được khai báo `abstract`.
- `@Inheritance(SINGLE_TABLE)`: toàn bộ hệ phân cấp dùng bảng `content_items`.
- `@DiscriminatorColumn(name = "content_kind")`: chọn tên cột phân loại trong bảng.
- `discriminatorType = DiscriminatorType.STRING`: lưu giá trị loại thực thể bằng chuỗi.
- `length = 16`: mô tả chiều dài cột discriminator kiểu chuỗi khi provider tạo DDL.
- `id`, `title` và `status`: thuộc tính chung được kế thừa bởi hai lớp con.

Lớp cha `abstract` có nghĩa ứng dụng không tạo `new ContentItem(...)`; nó vẫn có thể xuất hiện trong **truy vấn đa hình** như `SELECT c FROM ContentItem c`. Nếu lớp cha là entity cụ thể (không `abstract`), nó cũng có thể có hàng dữ liệu của riêng mình và có thể cần `@DiscriminatorValue`.

### 3.2. Lớp con khai báo giá trị phân loại

**`ArticleContent.java`:**

~~~java
package com.example.content.domain;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

@Entity
@DiscriminatorValue("ARTICLE")
public class ArticleContent extends ContentItem {
    @Column(name = "word_count")
    private Integer wordCount;

    protected ArticleContent() {
    }

    public ArticleContent(String title, int wordCount) {
        super(title);
        if (wordCount < 0) {
            throw new IllegalArgumentException(
                "Số từ phải không âm"
            );
        }
        this.wordCount = wordCount;
    }

    public Integer getWordCount() {
        return wordCount;
    }

    public void updateWordCount(int value) {
        if (value < 0) {
            throw new IllegalArgumentException(
                "Số từ phải không âm"
            );
        }
        this.wordCount = value;
    }
}
~~~

**`VideoContent.java`:**

~~~java
package com.example.content.domain;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

@Entity
@DiscriminatorValue("VIDEO")
public class VideoContent extends ContentItem {
    @Column(name = "duration_seconds")
    private Integer durationSeconds;

    protected VideoContent() {
    }

    public VideoContent(String title, int durationSeconds) {
        super(title);
        if (durationSeconds < 0) {
            throw new IllegalArgumentException(
                "Thời lượng phải không âm"
            );
        }
        this.durationSeconds = durationSeconds;
    }

    public Integer getDurationSeconds() {
        return durationSeconds;
    }

    public void updateDuration(int seconds) {
        if (seconds < 0) {
            throw new IllegalArgumentException(
                "Thời lượng phải không âm"
            );
        }
        this.durationSeconds = seconds;
    }
}
~~~

Hai annotation `@DiscriminatorValue` chỉ định giá trị được lưu trong cột `content_kind` cho mỗi kiểu con:

~~~text
ArticleContent   →  content_kind = 'ARTICLE'
VideoContent     →  content_kind = 'VIDEO'
~~~

Các lớp con **không khai báo `@Table` riêng** trong chiến lược `SINGLE_TABLE`, vì chúng cùng dùng bảng `content_items` của lớp cha. Nếu muốn mỗi subtype có bảng riêng thì phải đánh giá chiến lược kế thừa khác.

### 3.3. Bảng cơ sở dữ liệu tương ứng

Một schema PostgreSQL minh họa:

~~~sql
CREATE TABLE content_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    content_kind VARCHAR(16) NOT NULL,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,

    word_count INTEGER,
    duration_seconds INTEGER,

    CONSTRAINT ck_content_kind
        CHECK (content_kind IN ('ARTICLE', 'VIDEO')),

    CONSTRAINT ck_word_count
        CHECK (word_count IS NULL OR word_count >= 0),

    CONSTRAINT ck_duration_seconds
        CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
);
~~~

Những điểm đáng chú ý:

1. **Chỉ một bảng** lưu cả hai lớp con.
2. **Một cột discriminator** `content_kind` có giá trị `ARTICLE` hoặc `VIDEO`.
3. **Một khóa chính** `id` dùng chung trên toàn hệ phân cấp, vì tất cả hàng nằm trong cùng bảng.
4. `word_count` chỉ có ý nghĩa cho `ArticleContent`.
5. `duration_seconds` chỉ có ý nghĩa cho `VideoContent`.

Trong ví dụ schema này, hai cột riêng của subtype có thể `NULL` ở cấp bảng, kể cả khi nghiệp vụ muốn chúng bắt buộc trong subtype tương ứng. Phần tiếp theo sẽ hướng dẫn bảo vệ điều kiện đó bằng ràng buộc theo discriminator.

## 4. Hibernate đọc một hàng thành kiểu Java nào?

Khi thực hiện:

~~~java
ContentItem item = em.find(ContentItem.class, 1L);
~~~

Hibernate tra cứu entity trong persistence context hoặc nạp từ database. Nếu row `id = 1` có `content_kind = 'ARTICLE'`, Hibernate phải tạo (hoặc lấy) một managed instance tương ứng với `ArticleContent`, nên:

~~~java
if (item instanceof ArticleContent article) {
    System.out.println(article.getWordCount());
}
~~~

có thể truy cập thuộc tính `wordCount`. Với row có discriminator `VIDEO`, kiểu thực tế tương ứng là `VideoContent`.

**Discriminator là thông tin Hibernate dùng để phân loại kiểu thực thể khi materialize hàng.** Ứng dụng không phải tự đọc chuỗi rồi gọi `new ArticleContent(...)` để dựng entity; provider dùng metadata của hệ phân cấp.

Do Hibernate có thể dùng proxy và các cơ chế lazy loading, không nên thiết kế logic dựa hoàn toàn vào `item.getClass() == ArticleContent.class` trong mọi tình huống. Khi cần xử lý kiểu, có thể dùng truy vấn `TYPE`, cơ chế polymorphism của Java phù hợp, hoặc API Hibernate chuyên biệt nếu thực sự cần hiểu proxy.

### Định danh không bị tách riêng theo subtype

Giả sử có hai hàng:

~~~text
(id=1, content_kind='ARTICLE')
(id=2, content_kind='VIDEO')
~~~

Không phải `ArticleContent` có một dải ID riêng và `VideoContent` có dải ID riêng. Với `SINGLE_TABLE`, mọi entity trong hệ phân cấp được lưu ở một bảng với **một namespace khóa chính**.

Không thể có hai hàng cùng `id=1` nhưng khác `content_kind` trong cùng bảng nếu `id` là primary key.

## 5. `@DiscriminatorColumn` khai báo ở đâu và có những thuộc tính gì?

Cú pháp chuẩn:

~~~java
@DiscriminatorColumn(
    name = "content_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 16
)
~~~

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `name` | Tên cột phân loại trong bảng | `content_kind` |
| `discriminatorType` | Kiểu giá trị discriminator do JPA hỗ trợ | `STRING`, `CHAR`, `INTEGER` |
| `length` | Độ dài cho discriminator dạng chuỗi khi sinh DDL | `16` |
| `columnDefinition` | Định nghĩa SQL cụ thể của cột nếu cần tùy biến | Phụ thuộc database, nên hạn chế khi muốn portable |

Annotation này thường được đặt trên **root entity** của hệ phân cấp dùng `SINGLE_TABLE` hoặc `JOINED`. Đặt một `@DiscriminatorColumn` khác ở mỗi subtype không có ý nghĩa “mỗi lớp con có cột loại riêng” trong cùng một cây kế thừa.

Nếu không chỉ định `@DiscriminatorColumn` trong một hệ phân cấp `SINGLE_TABLE`, provider thường dùng cột phân loại mặc định theo JPA:

~~~text
Tên cột: DTYPE
Kiểu discriminator: STRING
~~~

Tuy nhiên, chiến lược đặt tên vật lý hoặc schema có sẵn có thể khiến tên SQL cuối cùng khác cách viết hiển thị trong annotation. Với hệ thống dùng migration, nên **khai báo cột rõ ràng** nếu tên và kiểu là một phần hợp đồng dữ liệu.

### `@DiscriminatorColumn` không phải `@Column` thông thường

Để ánh xạ giá trị phân loại, khai báo:

~~~java
@DiscriminatorColumn(name = "content_kind")
~~~

Không cần thêm field như:

~~~java
@Column(name = "content_kind")
private String kind; // Không nên lặp mapping của cột discriminator.
~~~

Bởi vì Hibernate đã quản lý cột này như một phần của metadata kế thừa. Một mapping thứ hai ghi vào cùng cột có thể gây xung đột ánh xạ, ví dụ lỗi cột được mapping nhiều lần. Nếu ứng dụng cần *đọc* discriminator như dữ liệu để hiển thị, ưu tiên truy vấn kiểu entity bằng `TYPE` hoặc ánh xạ đọc-only riêng theo khả năng provider, có chủ đích; tránh cho ứng dụng tùy tiện sửa giá trị phân loại bằng setter.

**Discriminator khác một cột enum nghiệp vụ.** Đổi trạng thái từ `DRAFT` sang `PUBLISHED` có thể là thao tác hợp lệ trên entity; đổi `content_kind` từ `ARTICLE` sang `VIDEO` sẽ đổi **kiểu thực thể** mà hàng đó đại diện.

## 6. `@DiscriminatorValue` gắn kiểu con với giá trị lưu trữ

Ví dụ:

~~~java
@Entity
@DiscriminatorValue("ARTICLE")
public class ArticleContent extends ContentItem {
    // ...
}

@Entity
@DiscriminatorValue("VIDEO")
public class VideoContent extends ContentItem {
    // ...
}
~~~

`@DiscriminatorValue` được đặt trên một **entity class trong hệ phân cấp** để quy định giá trị phân loại của chính entity đó. Giá trị phải **phân biệt** giữa các entity types được lưu chung bảng, phù hợp với kiểu và độ dài discriminator column.

Dù annotation khai báo `value` bằng Java `String`, giá trị vật lý của cột có thể là chuỗi, ký tự hoặc số nguyên tùy `DiscriminatorType`. Ví dụ với phân loại dạng số:

~~~java
@DiscriminatorColumn(
    name = "content_kind_code",
    discriminatorType = DiscriminatorType.INTEGER
)
~~~

thì:

~~~java
@DiscriminatorValue("1")
public class ArticleContent extends ContentItem { /* ... */ }

@DiscriminatorValue("2")
public class VideoContent extends ContentItem { /* ... */ }
~~~

Giá trị `"1"` và `"2"` trong annotation được diễn giải là giá trị phân loại kiểu số; cột SQL tương ứng nên có kiểu số nguyên được provider/database hỗ trợ.

### Nếu không ghi `@DiscriminatorValue` thì sao?

Với discriminator dạng `STRING`, giá trị mặc định theo JPA thường là **tên entity** (entity name). Điều này có thể làm những hàng mới lưu giá trị như:

~~~text
ArticleContent
VideoContent
~~~

Nếu refactor tên lớp hoặc đổi `@Entity(name = "...")`, giá trị mặc định có thể thay đổi và dữ liệu cũ trở nên không khớp mapping mới. Với discriminator dạng số, giá trị implicit có thể phụ thuộc provider.

Vì thế, nếu dữ liệu cần tồn tại qua các lần triển khai và các tên class có thể thay đổi, nên **khai báo `@DiscriminatorValue` tường minh, ổn định**, đặc biệt khi schema được migration quản lý.

### Giá trị phân loại phải phù hợp cột

Ví dụ sau không phù hợp nếu schema chỉ cho phép một ký tự:

~~~java
@DiscriminatorColumn(
    name = "kind",
    discriminatorType = DiscriminatorType.CHAR
)

@DiscriminatorValue("ARTICLE") // Không phù hợp dạng CHAR một ký tự.
public class ArticleContent extends ContentItem { /* ... */ }
~~~

Với `CHAR`, hãy chọn mã ngắn có một ký tự, chẳng hạn `"A"` và `"V"`. Với `STRING`, kiểm tra độ dài `@DiscriminatorColumn(length = ...)` và `VARCHAR` thực tế đủ chứa tất cả giá trị. Đừng dùng một tên dài hơn độ dài cột rồi chờ database tự xử lý an toàn.

## 7. Một bảng, nhiều subtype và ràng buộc `NOT NULL`

`SINGLE_TABLE` tiện cho truy vấn đa hình, nhưng các cột dành riêng cho subtype thường **không thể khai báo `NOT NULL` vô điều kiện** trên toàn bảng.

Xét:

~~~text
ARTICLE cần word_count
VIDEO cần duration_seconds
~~~

Nếu schema yêu cầu cả hai cột `NOT NULL`:

~~~sql
word_count INTEGER NOT NULL,
duration_seconds INTEGER NOT NULL
~~~

thì hàng `ARTICLE` thiếu `duration_seconds` sẽ không hợp lệ, và hàng `VIDEO` thiếu `word_count` cũng không hợp lệ. Đây là một xung đột giữa ràng buộc theo **toàn bảng** và quy tắc bắt buộc theo **kiểu con**.

Giải pháp là để cột subtype có thể `NULL` ở cấp SQL, rồi kiểm tra tùy discriminator:

~~~sql
ALTER TABLE content_items
ADD CONSTRAINT ck_content_subtype_fields
CHECK (
       (content_kind = 'ARTICLE'
        AND word_count IS NOT NULL
        AND duration_seconds IS NULL)
    OR (content_kind = 'VIDEO'
        AND duration_seconds IS NOT NULL
        AND word_count IS NULL)
);
~~~

Ràng buộc trên giả định:

- Mỗi hàng chỉ thuộc một trong hai subtype.
- `ARTICLE` luôn có `word_count` và không dùng `duration_seconds`.
- `VIDEO` luôn có `duration_seconds` và không dùng `word_count`.

Nếu nghiệp vụ cho phép hàng thiếu số từ/thời lượng khi mới tạo, ràng buộc phải nới lỏng cho đúng yêu cầu. Không nên sao chép `CHECK` này vào ứng dụng thật mà chưa xem vòng đời dữ liệu.

### `@Column(nullable = false)` trên field subtype

Trong chiến lược `SINGLE_TABLE`, chú ý khi viết:

~~~java
@Entity
@DiscriminatorValue("ARTICLE")
public class ArticleContent extends ContentItem {
    @Column(nullable = false)
    private Integer wordCount;
}
~~~

Nếu công cụ tạo DDL sinh ràng buộc `NOT NULL` trực tiếp cho cột `word_count` ở bảng chung, các hàng `VIDEO` có thể không lưu được. Hành vi DDL cụ thể phụ thuộc provider, phiên bản và cách schema được quản lý; cần xem schema **thực tế** chứ không chỉ nhìn annotation.

Nguyên tắc: dùng validation/domain logic để bảo vệ trường bắt buộc của subtype, kết hợp **CHECK có điều kiện tại database** nếu cần bảo đảm qua mọi đường ghi, và tránh ràng buộc chung làm subtype khác không hợp lệ.

## 8. Ghi entity: Hibernate chọn giá trị discriminator

Giả sử ứng dụng đã cấu hình `EntityManagerFactory emf` với ba entity class được đăng ký và schema tương ứng.

Ví dụ dùng JPA resource-local transaction:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    ArticleContent article =
        new ArticleContent("JPA cơ bản", 1250);

    VideoContent video =
        new VideoContent("Hibernate trong 10 phút", 600);

    em.persist(article);
    em.persist(video);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Hibernate dùng metadata để chèn các hàng với giá trị phân loại phù hợp. SQL minh họa, lược bỏ chi tiết generator/binding:

~~~sql
INSERT INTO content_items (
    content_kind, title, status, word_count, duration_seconds
)
VALUES (
    'ARTICLE', 'JPA cơ bản', 'DRAFT', 1250, NULL
);

INSERT INTO content_items (
    content_kind, title, status, word_count, duration_seconds
)
VALUES (
    'VIDEO', 'Hibernate trong 10 phút', 'DRAFT', NULL, 600
);
~~~

Giá trị `ARTICLE` và `VIDEO` xuất phát từ **kiểu Java được persist** cùng metadata `@DiscriminatorValue`. Trong cách ánh xạ thông thường, ứng dụng **không tự gọi** `article.setContentKind("ARTICLE")` và cũng không cần setter cho discriminator.

Thời điểm chạy `INSERT` thực tế có thể thay đổi theo `GenerationType.IDENTITY`, `SEQUENCE`, flush mode và transaction. `persist` đưa object vào trạng thái managed; `commit` thành công mới xác nhận dữ liệu transaction.

### Sửa thuộc tính mà không đổi subtype

Trong một transaction:

~~~java
ContentItem content = em.find(ContentItem.class, 1L);
content.publish();
~~~

Hibernate có thể cập nhật `status` của row `id = 1` mà giữ nguyên `content_kind = 'ARTICLE'`. Không có chuyện chuyển hàng đó sang `VideoContent` chỉ vì `status` thay đổi.

## 9. Truy vấn đa hình và truy vấn từng subtype

Một ưu điểm lớn của inheritance mapping là có thể truy vấn lớp cha và nhận về các kiểu con.

### 9.1. Truy vấn lớp cha

~~~java
List<ContentItem> allContent = em.createQuery(
    "select c from ContentItem c",
    ContentItem.class
).getResultList();
~~~

Với `SINGLE_TABLE`, Hibernate có thể truy vấn bảng `content_items` để lấy mọi loại nội dung. Các phần tử trong danh sách là những instance có kiểu tương ứng `ArticleContent` hoặc `VideoContent`.

Đây là **truy vấn đa hình (polymorphic query)**: `ContentItem` là kiểu kết quả chung, nhưng mỗi hàng chứa thông tin subtype được xác định bằng discriminator.

### 9.2. Truy vấn riêng một lớp con

~~~java
List<ArticleContent> articles = em.createQuery(
    "select a from ArticleContent a",
    ArticleContent.class
).getResultList();
~~~

Hibernate có thể sử dụng điều kiện trên discriminator:

~~~sql
SELECT *
FROM content_items
WHERE content_kind = 'ARTICLE';
~~~

Câu SQL là ví dụ khái niệm. Hibernate có thể chọn danh sách cột, điều kiện và alias khác, nhưng vẫn cần loại trừ những hàng không thuộc subtype được yêu cầu.

### 9.3. Toán tử `TYPE` trong JPQL

JPQL cho phép kiểm tra kiểu thực thể:

~~~java
List<ContentItem> articles = em.createQuery(
    "select c from ContentItem c " +
    "where type(c) = ArticleContent",
    ContentItem.class
).getResultList();
~~~

`TYPE(c)` là **entity type expression**. Nó kiểm tra loại entity theo metadata JPA, không phải so sánh trực tiếp chuỗi `"ARTICLE"` trong mã JPQL.

Cách này có lợi vì query thể hiện tên kiểu Java/JPA, còn mapping phụ trách chuyển sang biểu diễn discriminator trong database. Khi đổi mã discriminator, truy vấn dùng `TYPE` vẫn diễn đạt điều kiện theo entity type thay vì hardcode một chuỗi SQL.

### 9.4. `TREAT` để truy cập thuộc tính của lớp con

Khi chỉ có biến kiểu lớp cha `ContentItem` nhưng cần lọc theo thuộc tính của `ArticleContent`, có thể sử dụng cú pháp `TREAT` trong JPQL:

~~~java
List<ContentItem> longArticles = em.createQuery(
    "select c from ContentItem c " +
    "where treat(c as ArticleContent).wordCount >= :minimum",
    ContentItem.class
)
.setParameter("minimum", 2000)
.getResultList();
~~~

`TREAT(c AS ArticleContent)` cho phép truy cập thuộc tính đặc thù `wordCount` theo kiểu con. Đây là tính năng truy vấn đa hình của JPA, không yêu cầu biến `wordCount` thành field của lớp cha.

Nếu chỉ cần bài viết, truy vấn trực tiếp `ArticleContent` thường ngắn hơn:

~~~java
List<ArticleContent> longArticles = em.createQuery(
    "select a from ArticleContent a " +
    "where a.wordCount >= :minimum",
    ArticleContent.class
)
.setParameter("minimum", 2000)
.getResultList();
~~~

Thời điểm nào Hibernate dùng điều kiện discriminator, join hoặc các biểu thức SQL phụ thuộc chiến lược kế thừa và phiên bản provider.

## 10. Tại sao không dùng một trường `type` nghiệp vụ thay cho kế thừa?

Không phải ứng dụng nào có loại sản phẩm, loại thông báo hoặc trạng thái đều cần kế thừa entity.

Ví dụ:

~~~java
@Entity
public class Task {
    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    private TaskType type;
}
~~~

Nếu mọi `Task` có cùng tập thuộc tính và hành vi, `type` chỉ là **giá trị nghiệp vụ**, không nhất thiết tương ứng với một lớp Java con. Trong trường hợp đó, dùng enum có thể đơn giản, rõ ràng và linh hoạt hơn mô hình kế thừa.

So sánh:

| Discriminator của entity inheritance | Enum/cột nghiệp vụ |
| --- | --- |
| Xác định **lớp entity runtime** mà Hibernate tạo | Chứa **giá trị thuộc tính** của cùng một lớp entity |
| Do metadata inheritance điều khiển | Do thuộc tính được ứng dụng đọc/ghi |
| Thường không được cập nhật độc lập như field bình thường | Có thể thay đổi theo quy tắc nghiệp vụ |
| Dùng với `@Inheritance`/`@DiscriminatorValue` | Có thể dùng `@Enumerated` hoặc converter |
| Khi đổi giá trị có thể đổi loại entity và mapping | Khi đổi giá trị thường vẫn là cùng entity class |

**Chọn entity inheritance** khi subtype thực sự có khác biệt rõ về cấu trúc, hành vi, quan hệ hoặc quy tắc cần quản lý theo kiểu Java. **Chọn thuộc tính trạng thái/loại** nếu chỉ cần một cờ nghiệp vụ có thể thay đổi mà không nên biến bản ghi thành lớp Java khác.

## 11. `JOINED`: có thể có discriminator nhưng không giống `SINGLE_TABLE`

Với chiến lược `JOINED`, mỗi subtype có bảng riêng cho thuộc tính đặc thù, còn bảng cha giữ các thuộc tính chung.

Ví dụ khái niệm:

~~~java
@Entity
@Table(name = "content_items")
@Inheritance(strategy = InheritanceType.JOINED)
@DiscriminatorColumn(
    name = "content_kind",
    discriminatorType = DiscriminatorType.STRING
)
public abstract class ContentItem {
    @Id
    private Long id;
    // title, status...
}

@Entity
@Table(name = "article_contents")
@DiscriminatorValue("ARTICLE")
public class ArticleContent extends ContentItem {
    private Integer wordCount;
}

@Entity
@Table(name = "video_contents")
@DiscriminatorValue("VIDEO")
public class VideoContent extends ContentItem {
    private Integer durationSeconds;
}
~~~

Đây là các đoạn **minh họa ánh xạ**: nếu đưa vào mã nguồn cần bổ sung constructor, import và định nghĩa trường hoàn chỉnh phù hợp như ví dụ `SINGLE_TABLE`.

Lược đồ có thể là:

~~~sql
CREATE TABLE content_items (
    id BIGINT PRIMARY KEY,
    content_kind VARCHAR(16) NOT NULL,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE article_contents (
    id BIGINT PRIMARY KEY REFERENCES content_items(id),
    word_count INTEGER NOT NULL
);

CREATE TABLE video_contents (
    id BIGINT PRIMARY KEY REFERENCES content_items(id),
    duration_seconds INTEGER NOT NULL
);
~~~

Ở đây:

- Bảng cha chứa `id` và các field chung.
- Bảng con `article_contents` chứa thêm `word_count`, cùng `id` làm PK và FK tới bảng cha.
- Bảng con `video_contents` chứa thêm `duration_seconds`, cũng dùng `id` làm PK/FK.
- Nếu có cột `content_kind` ở bảng cha, nó có thể giúp xác định subtype.
- Không phải mọi cấu hình `JOINED` đều cần một cột discriminator vật lý; provider cũng có thể suy ra subtype bằng thông tin bảng con/joins.

**Một điểm khác biệt:** ở `JOINED`, cột bắt buộc `word_count` có thể khai báo `NOT NULL` trong bảng `article_contents` mà không ảnh hưởng tới hàng video, vì video không có hàng tương ứng trong bảng article. Điều này làm ràng buộc cấu trúc subtype tự nhiên hơn so với `SINGLE_TABLE`.

Nếu quyết định dùng discriminator trong `JOINED`, schema và dữ liệu phải bảo đảm nó nhất quán với các hàng bảng con. Một row gắn `content_kind='ARTICLE'` nhưng chỉ có dữ liệu ở bảng `video_contents` là dữ liệu sai mô hình. Hibernate có thể phát hiện lỗi hoặc không dựng được object đúng khi đọc.

## 12. `TABLE_PER_CLASS` không có một discriminator vật lý dùng chung

Với `TABLE_PER_CLASS`, mỗi entity cụ thể được lưu vào bảng riêng mang cả các field được kế thừa:

~~~text
article_contents
  id
  title
  status
  word_count

video_contents
  id
  title
  status
  duration_seconds
~~~

Mô hình:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class ContentItem {
    @Id
    private Long id;
    // ...
}
~~~

Bảng của mỗi subtype đã cho biết hàng thuộc kiểu nào. Truy vấn `ContentItem` đa hình có thể phải kết hợp dữ liệu từ nhiều bảng, chẳng hạn bằng `UNION ALL` hoặc cách tương đương.

Một truy vấn SQL minh họa ý tưởng:

~~~sql
SELECT id, title, status, 'ARTICLE' AS result_kind
FROM article_contents
UNION ALL
SELECT id, title, status, 'VIDEO' AS result_kind
FROM video_contents;
~~~

Cột `result_kind` trong ví dụ là **giá trị do truy vấn tổng hợp**, không phải một cột discriminator vật lý chung được lưu ở mọi hàng. Hibernate có thể tạo một cột/biểu thức phân loại nội bộ khi thực hiện truy vấn đa hình, nhưng đó không đồng nghĩa ta phải khai báo `@DiscriminatorColumn` như trong `SINGLE_TABLE`.

**Đừng nhầm dữ liệu phân loại trong kết quả truy vấn với cột phân loại được lưu trong bảng**. Hai cơ chế giải quyết cùng nhu cầu xác định kiểu kết quả nhưng có cấu trúc lưu trữ khác nhau.

## 13. `@MappedSuperclass` không tạo một hệ phân cấp entity đa hình

Một lớp Java cha có thể dùng:

~~~java
@MappedSuperclass
public abstract class Auditable {
    @Column(name = "created_by")
    private String createdBy;
}
~~~

Các entity con kế thừa field `createdBy`, nhưng `Auditable` **không phải một entity type độc lập** để JPA truy vấn đa hình qua `FROM Auditable`. Vì vậy cũng không có ý nghĩa khai báo discriminator cho `Auditable` như root entity của một cây `SINGLE_TABLE`.

So sánh:

| Lớp cha | Entity type? | Có truy vấn JPQL từ kiểu cha? | Có discriminator hệ phân cấp? |
| --- | --- | --- | --- |
| `@Entity abstract ContentItem` với `@Inheritance` | Có | Có, trả về subtype | Có thể cần/khai báo tùy strategy |
| `@MappedSuperclass abstract Auditable` | Không | Không, vì không phải entity | Không tạo hierarchy discriminator riêng |
| Lớp Java thường làm superclass | Không tự động | Không | Không |

Một hệ thống có thể có cả hai tầng, ví dụ `Auditable` là mapped superclass của `ContentItem`, còn `ArticleContent`/`VideoContent` thuộc entity inheritance. Khi đó discriminator áp dụng **tại root entity `ContentItem`**, không áp dụng tại mapped superclass `Auditable`.

## 14. Đổi kiểu con bằng cách sửa discriminator có hợp lệ không?

Giả sử hàng:

~~~text
id=1, content_kind='ARTICLE',
title='JPA cơ bản', word_count=1250
~~~

Có người muốn chuyển nó thành video bằng SQL:

~~~sql
UPDATE content_items
SET content_kind = 'VIDEO'
WHERE id = 1;
~~~

Thao tác này **không tương đương** việc chuyển object Java `ArticleContent` thành `VideoContent` trong JPA. Java không cho phép một instance đổi runtime class sau khi được tạo; Hibernate cũng quản lý entity identity cùng kiểu đã được xác định khi nạp.

Hơn nữa, hàng mới có `content_kind='VIDEO'` nhưng `duration_seconds=NULL` có thể vi phạm điều kiện nghiệp vụ hoặc `CHECK`. Persistence context đang mở vẫn có thể giữ managed instance kiểu `ArticleContent`. Cache cũng có thể giữ trạng thái phân loại cũ.

**Đừng dùng setter hoặc SQL cập nhật discriminator như thao tác nghiệp vụ thông thường để “đổi subclass”.** Nếu loại nội dung cần đổi thường xuyên, nên xem lại mô hình:

- Nếu đó là trạng thái có thể thay đổi, có thể dùng enum/thuộc tính nghiệp vụ trên một entity.
- Nếu thật sự phải chuyển sang kiểu entity khác, cần quy trình migration hoặc thao tác tạo entity mới/xử lý dữ liệu liên quan có kiểm soát.
- Nếu giữ cùng ID khi chuyển cấu trúc, cần thiết kế thay đổi schema và dữ liệu một cách riêng biệt, đảm bảo toàn bộ thuộc tính, khóa ngoại, cache và context nhất quán.

## 15. Thêm một subtype mới đòi hỏi thay đổi những gì?

Giả sử muốn bổ sung `PodcastContent` với `episodeCount` và discriminator `PODCAST`.

~~~java
@Entity
@DiscriminatorValue("PODCAST")
public class PodcastContent extends ContentItem {
    @Column(name = "episode_count")
    private Integer episodeCount;

    protected PodcastContent() {
    }

    public PodcastContent(String title, int episodeCount) {
        super(title);
        this.episodeCount = episodeCount;
    }
}
~~~

Với `SINGLE_TABLE`, các việc cần xem xét khi phát triển tính năng:

1. Đăng ký lớp entity con trong persistence unit hoặc bảo đảm cơ chế quét entity nhận diện được nó.
2. Thêm cột `episode_count` vào `content_items` bằng migration nếu schema chưa có.
3. Mở rộng `CHECK(content_kind IN (...))` để chấp nhận `PODCAST`.
4. Nếu có ràng buộc theo subtype, bổ sung điều kiện cho loại mới.
5. Bảo đảm độ dài cột `content_kind` đủ chứa `PODCAST`.
6. Cập nhật các service, API, serialization, truy vấn/report và giao diện cần nhận biết loại mới.
7. Lưu ý tương thích khi hệ thống chạy **nhiều phiên bản ứng dụng** trong lúc triển khai.

Mỗi subtype mới là một **thay đổi hợp đồng dữ liệu** khi bảng đã có discriminator và được nhiều phiên bản ứng dụng đọc.

### Trình tự triển khai an toàn khi có nhiều instance chạy song song

Nếu ứng dụng phiên bản cũ chưa biết `PODCAST`, mà dữ liệu mới có hàng `content_kind='PODCAST'`, phiên bản cũ có thể báo lỗi khi cố materialize hàng đó trong truy vấn đa hình. Vì vậy không nên chỉ deploy một instance mới rồi cho nó ghi discriminator mới trong khi các instance cũ vẫn phải đọc toàn bộ bảng.

Một quy trình triển khai thường cần:

~~~text
1. Migration mở rộng schema và constraint
          ↓
2. Đảm bảo các phiên bản reader liên quan hiểu subtype mới
          ↓
3. Bật đường ghi tạo subtype mới
          ↓
4. Giám sát lỗi đọc/ghi và dọn nhánh tương thích cũ khi thích hợp
~~~

Đây là nguyên tắc tương thích dữ liệu nói chung; cách rollout cụ thể phụ thuộc hệ thống. Đối với ứng dụng nhỏ không có nhiều phiên bản chạy đồng thời, quy trình có thể đơn giản hơn.

## 16. Đổi tên lớp hoặc đổi `@DiscriminatorValue` có rủi ro gì?

Giả sử dữ liệu cũ có:

~~~text
content_kind = 'ARTICLE'
~~~

Sau đó lập trình viên đổi annotation thành:

~~~java
@DiscriminatorValue("BLOG_POST")
public class ArticleContent extends ContentItem {
}
~~~

Nếu **không migration dữ liệu cũ**, Hibernate có thể không tìm thấy entity mapping tương ứng khi gặp `'ARTICLE'`. Trong một hệ phân cấp, giá trị discriminator phải khớp metadata đang chạy.

Một migration dữ liệu minh họa:

~~~sql
UPDATE content_items
SET content_kind = 'BLOG_POST'
WHERE content_kind = 'ARTICLE';
~~~

Tuy nhiên, trước khi chạy phải chỉnh lại ràng buộc `CHECK` và cân nhắc mọi phiên bản ứng dụng đang đọc bảng. Một thay đổi như vậy cần được quản lý như migration, có chiến lược sao lưu/rollback và thứ tự triển khai rõ ràng; SQL trên chỉ để diễn đạt mục tiêu.

### Tại sao nên dùng giá trị tường minh ổn định?

So sánh:

~~~java
// Dùng mặc định theo entity name:
@Entity
public class ArticleContent extends ContentItem { }

// Chọn mã lưu ổn định:
@Entity
@DiscriminatorValue("ARTICLE")
public class ArticleContent extends ContentItem { }
~~~

Ở cách đầu, việc refactor tên entity có thể làm thay đổi giá trị discriminator mặc định và ảnh hưởng hàng cũ. Ở cách sau, có thể đổi tên Java class mà **giữ mã `ARTICLE`** nếu ý nghĩa dữ liệu không thay đổi.

Điều này đặc biệt quan trọng khi dữ liệu được sao lưu lâu dài, phục vụ báo cáo SQL, hoặc có hệ thống khác đọc trực tiếp bảng.

## 17. Dữ liệu không hợp lệ trong cột phân loại

Giả sử người quản trị chèn:

~~~sql
INSERT INTO content_items (
    content_kind, title, status
)
VALUES (
    'UNKNOWN', 'Bản ghi lạ', 'DRAFT'
);
~~~

Nếu schema có:

~~~sql
CHECK (content_kind IN ('ARTICLE', 'VIDEO'))
~~~

database sẽ từ chối giá trị không hợp lệ. Nếu schema không có constraint, hàng có thể được lưu nhưng Hibernate **không có mapping subtype tương ứng** khi truy vấn hệ phân cấp.

Một số kết quả có thể gặp tùy provider/phiên bản: lỗi không nhận diện discriminator value, lỗi materialization hoặc kết quả không đúng mong đợi. **Không nên giả định Hibernate sẽ tự động bỏ qua hàng lạ hoặc coi nó là lớp cha**.

Có thể kiểm tra dữ liệu bất thường trước khi thay đổi mã:

~~~sql
SELECT content_kind, COUNT(*) AS row_count
FROM content_items
GROUP BY content_kind
ORDER BY content_kind;
~~~

Với mô hình hiện tại, các giá trị hợp lệ chỉ gồm `ARTICLE` và `VIDEO`. Nếu xuất hiện giá trị khác, cần làm rõ chúng thuộc phiên bản schema nào, có phải dữ liệu legacy không và lớp tương ứng còn tồn tại không trước khi sửa.

### Dữ liệu sai subtype còn có thể nằm ở cột phụ

Ngay cả khi `content_kind='ARTICLE'` hợp lệ, hàng có `duration_seconds=600` và `word_count=NULL` cũng có thể không phù hợp quy tắc nghiệp vụ. Discriminator xác định **lớp Java**, không tự bảo đảm tất cả giá trị cột subtype đúng.

Vì vậy cần kết hợp metadata ORM, validation ở phía Java và các constraint ở database khi nghiệp vụ đòi hỏi.

## 18. Discriminator có liên quan gì tới `@Id` và `@Version`?

Ba loại thông tin này giải quyết ba vấn đề riêng:

| Thành phần | Vai trò |
| --- | --- |
| `@Id` | Xác định **hàng/entity identity**; không được đổi sau khi entity đã persistent |
| `@DiscriminatorColumn` / `@DiscriminatorValue` | Xác định **entity subtype** của hàng trong hierarchy |
| `@Version` | Giúp phát hiện **xung đột cập nhật đồng thời** bằng optimistic locking |

Ví dụ entity cha có:

~~~java
@Id
private Long id;

@Version
private Long version;
~~~

và hệ phân cấp có `content_kind`. Một hàng có thể mang:

~~~text
id=1, version=3, content_kind='ARTICLE'
~~~

- `id=1` cho biết đó là entity nào.
- `content_kind='ARTICLE'` cho biết Hibernate dùng mapping của lớp `ArticleContent`.
- `version=3` cho biết phiên bản dùng để kiểm tra cập nhật đồng thời.

**Discriminator không thay ID, và version không thay discriminator.** Một entity có thể tăng version nhiều lần trong khi giữ nguyên ID và subtype.

## 19. Chỉ mục và hiệu năng truy vấn theo subtype

Với `SINGLE_TABLE`, truy vấn từ lớp con thường lọc theo discriminator. Nếu bảng có hàng triệu bản ghi và ứng dụng thường chỉ truy vấn bài viết, có thể cân nhắc một index trên `content_kind` hoặc index kết hợp các cột lọc thường dùng.

Ví dụ:

~~~sql
CREATE INDEX ix_content_items_kind_status
ON content_items(content_kind, status);
~~~

Index này có thể hữu ích cho truy vấn kiểu:

~~~sql
SELECT id, title
FROM content_items
WHERE content_kind = 'ARTICLE'
  AND status = 'PUBLISHED';
~~~

Nhưng **không phải mọi cột discriminator đều nên được đánh index**. Nếu cột chỉ có hai giá trị với phân bố tương đối đều và query thường lấy phần lớn bảng, index đơn cột có thể không mang lại lợi ích đáng kể. Cần xem kế hoạch truy vấn, lượng dữ liệu và tần suất ghi trước khi quyết định.

So sánh ở mức tổng quát:

| Chiến lược | Truy vấn riêng subtype | Truy vấn đa hình | Đặc điểm schema |
| --- | --- | --- | --- |
| `SINGLE_TABLE` | Thường lọc một bảng theo discriminator | Thường đơn giản, một bảng | Nhiều cột riêng subtype có thể `NULL` |
| `JOINED` | Có thể cần join bảng cha và bảng con | Có thể cần nhiều join | Bảng subtype tách riêng, ràng buộc field rõ hơn |
| `TABLE_PER_CLASS` | Đọc bảng riêng của subtype | Thường kết hợp kết quả từ nhiều bảng | Lặp field cha trong các bảng cụ thể |

Đây là đặc điểm kiến trúc, không phải cam kết mọi truy vấn Hibernate đều có một mẫu SQL cố định. Hiệu năng phụ thuộc truy vấn thực tế, cơ sở dữ liệu, số bảng/subtype, chỉ mục và kích thước dữ liệu.

## 20. Những lỗi cấu hình discriminator thường gặp

| Triệu chứng | Nguyên nhân có thể có | Hướng xử lý |
| --- | --- | --- |
| Hibernate đọc hàng nhưng không xác định được subtype | Giá trị cột phân loại không khớp entity mapping | Kiểm tra `@DiscriminatorValue`, dữ liệu legacy và các lớp đã đăng ký |
| Hai subtype cùng dùng `@DiscriminatorValue("ARTICLE")` | Giá trị phân loại bị trùng trong cùng hierarchy | Dùng mã riêng biệt cho từng entity type |
| Cột discriminator quá ngắn | Giá trị dài hơn `VARCHAR`/`length` | Chọn độ dài đủ và cập nhật migration |
| Dữ liệu cũ lỗi sau khi đổi tên entity | Đã dùng discriminator mặc định theo tên entity | Giữ mã tường minh ổn định hoặc migration đồng bộ |
| Bảng không có `content_kind` như mapping | Mapping và schema thực tế không khớp | Kiểm tra `@DiscriminatorColumn`, naming strategy, migration |
| Lưu `VIDEO` nhưng DB báo `word_count NOT NULL` | Ràng buộc cột subtype áp dụng cho cả bảng `SINGLE_TABLE` | Dùng ràng buộc có điều kiện theo discriminator |
| Có field `@Column(name="content_kind")` cùng cột discriminator | Ánh xạ trùng cột hoặc cố ghi cột do ORM quản lý | Bỏ field ghi trùng; dùng cơ chế đọc-only nếu thực sự cần |
| Dùng `@DiscriminatorColumn` trên `@MappedSuperclass` | Nhầm mapped superclass với root entity inheritance | Đặt metadata trên root `@Entity` |
| Nghĩ `@Table` trên mỗi subtype luôn được dùng với `SINGLE_TABLE` | Hiểu sai chiến lược lưu | Dùng một bảng chung hoặc đổi strategy có migration |
| Chỉ đổi cột discriminator để “biến” Article thành Video | Entity runtime type không thể thay bằng sửa field | Thiết kế migration/chuyển đổi dữ liệu riêng hoặc mô hình khác |
| Phiên bản cũ lỗi khi subtype mới được ghi | Reader cũ không có mapping cho giá trị mới | Triển khai tương thích trước khi bật đường ghi mới |
| Truy vấn `ContentItem` thiếu subtype | Class con chưa đăng ký hoặc mapping hierarchy sai | Kiểm tra persistence unit, entity scan và metadata |

### Tương tác với `@Entity(name = ...)`

Tên entity trong JPQL và mã discriminator là hai khái niệm khác nhau:

~~~java
@Entity(name = "BlogArticle")
@DiscriminatorValue("ARTICLE")
public class ArticleContent extends ContentItem {
}
~~~

Trong ví dụ:

- `ArticleContent`: tên class Java.
- `BlogArticle`: tên entity dùng trong JPQL, ví dụ `FROM BlogArticle`.
- `ARTICLE`: giá trị lưu trong cột discriminator.
- `content_items`: bảng SQL chung.

Đừng nhầm tên bảng, tên entity và discriminator khi đọc lỗi hoặc viết truy vấn.

## 21. Minh họa đầy đủ vòng đời một hàng trong hệ phân cấp

Xem chuỗi:

~~~mermaid
flowchart TD
    A["new ArticleContent(title, wordCount)"] --> B["em.persist(article)"]
    B --> C["Hibernate nhận mapping ArticleContent"]
    C --> D["Dùng discriminator value ARTICLE"]
    D --> E["INSERT vào content_items"]
    E --> F["Transaction commit"]
    F --> G["Hàng DB: id=1, content_kind=ARTICLE"]
    G --> H["em.find(ContentItem.class, 1L)"]
    H --> I["Đọc discriminator và dựng ArticleContent"]
    I --> J["JPQL TYPE(c) = ArticleContent"]
    I --> K["Gọi phương thức thuộc ArticleContent"]
~~~

Đọc sơ đồ theo hai hướng:

**Chiều ghi:** từ kiểu Java thực thể con sang giá trị `ARTICLE` và hàng SQL.

**Chiều đọc:** từ hàng SQL có `content_kind='ARTICLE'` sang instance của lớp `ArticleContent`.

Đây là cơ chế để tính đa hình hoạt động nhất quán giữa mã Java và cơ sở dữ liệu. Nếu metadata và giá trị trong bảng không thống nhất, chiều đọc có thể thất bại.

## 22. Thực hành: bổ sung một kiểu con và dự đoán kết quả

Giả sử dự án đang có `ArticleContent` và `VideoContent` như ví dụ. Yêu cầu thêm nội dung âm thanh với thời lượng `durationSeconds`.

### Bài tập A — Khai báo subtype mới

Hãy viết entity `AudioContent` với discriminator `AUDIO`.

Một cách triển khai:

~~~java
@Entity
@DiscriminatorValue("AUDIO")
public class AudioContent extends ContentItem {
    @Column(name = "audio_duration_seconds")
    private Integer durationSeconds;

    protected AudioContent() {
    }

    public AudioContent(String title, int durationSeconds) {
        super(title);
        if (durationSeconds < 0) {
            throw new IllegalArgumentException("Thời lượng không hợp lệ");
        }
        this.durationSeconds = durationSeconds;
    }

    public Integer getDurationSeconds() {
        return durationSeconds;
    }
}
~~~

Ở chiến lược `SINGLE_TABLE`, entity này **không cần bảng audio riêng**. Cần mở rộng bảng `content_items` bằng cột `audio_duration_seconds` và cập nhật các constraint cho `content_kind='AUDIO'`.

### Bài tập B — Giải thích truy vấn

Giả sử bảng có:

| id | content_kind | title |
| ---: | --- | --- |
| 1 | ARTICLE | A |
| 2 | VIDEO | B |
| 3 | AUDIO | C |

Truy vấn:

~~~java
List<ContentItem> items = em.createQuery(
    "select c from ContentItem c order by c.id",
    ContentItem.class
).getResultList();
~~~

**Đáp án:** nếu cả ba subtype đã được đăng ký và dữ liệu hợp lệ, danh sách có ba phần tử mang kiểu runtime tương ứng `ArticleContent`, `VideoContent`, `AudioContent`. Truy vấn được khai báo bằng kiểu lớp cha nhưng kết quả vẫn giữ tính đa hình.

### Bài tập C — Mã discriminator không khớp

Entity:

~~~java
@Entity
@DiscriminatorValue("AUDIO")
public class AudioContent extends ContentItem {
    // ...
}
~~~

Nhưng có hàng SQL `content_kind='PODCAST'`. Hibernate có tự mặc định coi hàng là `AudioContent` không?

**Đáp án:** Không. Giá trị discriminator phải có mapping phù hợp; nếu không được nhận diện, việc nạp có thể báo lỗi. Cần sửa dữ liệu, annotation hoặc có migration rõ ràng.

### Bài tập D — So sánh hai cơ chế

Có yêu cầu “bản nháp có thể chuyển thành đã xuất bản”. Có nên tạo hai subtype `DraftArticle` và `PublishedArticle` chỉ để đổi discriminator mỗi khi xuất bản không?

**Đáp án gợi ý:** Thường không. `status` là thuộc tính có thể thay đổi của cùng article, nên một field trạng thái sẽ phù hợp hơn. Đổi trạng thái nghiệp vụ không cần đổi runtime entity class.

### Bài tập E — Bảo vệ field bắt buộc

`ArticleContent` phải có `wordCount`, `VideoContent` phải có `durationSeconds`. Có nên khai báo cả hai cột `NOT NULL` ở bảng chung không?

**Đáp án:** Không, vì hàng của subtype này không có giá trị field của subtype kia. Dùng validation theo class và các ràng buộc `CHECK` phụ thuộc `content_kind` nếu muốn bảo vệ dữ liệu ở database.

### Bài tập F — Hiểu cú pháp JPA

Xét:

~~~java
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "content_kind")
public abstract class ContentItem { /* ... */ }

@DiscriminatorValue("ARTICLE")
public class ArticleContent extends ContentItem { /* ... */ }
~~~

Cần bổ sung gì để đây là một hệ phân cấp entity JPA?

**Đáp án:** Lớp cha và lớp con cần được khai báo/đăng ký là **entity** (ví dụ thêm `@Entity` trên mỗi lớp), có định danh ánh xạ hợp lệ ở lớp cha hoặc kế thừa phù hợp, constructor không tham số và các yêu cầu entity còn lại. Hai annotation discriminator **không tự biến lớp Java thường thành entity**.

## 23. Ghi nhớ các nguyên tắc thiết kế

1. **Cột phân loại nói một hàng thuộc subtype nào.** Trong `SINGLE_TABLE`, nó giúp Hibernate dựng đúng class khi đọc và ghi đúng mã khi persist.
2. **`@DiscriminatorColumn` nằm ở root entity**, xác định cột và kiểu lưu. **`@DiscriminatorValue` nằm trên entity type**, xác định mã cụ thể của từng subtype.
3. **ID, discriminator và version khác nhiệm vụ.** ID xác định hàng; discriminator xác định loại entity; version kiểm soát cập nhật đồng thời.
4. **Giá trị discriminator nên tường minh và ổn định.** Đổi mã hoặc thêm subtype cần xem là thay đổi hợp đồng dữ liệu, có migration và kế hoạch tương thích.
5. **`SINGLE_TABLE`, `JOINED` và `TABLE_PER_CLASS` có cấu trúc lưu khác nhau.** `SINGLE_TABLE` dùng một bảng và thường cần discriminator; `JOINED` có thể dùng discriminator; `TABLE_PER_CLASS` không có một cột discriminator vật lý chung.
6. **Field subtype trong `SINGLE_TABLE` cần ràng buộc có điều kiện nếu bắt buộc theo loại.** `NOT NULL` vô điều kiện trên mọi cột riêng subtype thường không phù hợp.
7. **Không dùng sửa discriminator để đổi loại entity đang managed.** Nếu loại thực thể phải thay đổi thường xuyên, hãy xem đó có thật sự là subtype hay chỉ là trạng thái nghiệp vụ.

Khi nhìn một hệ phân cấp entity, hãy luôn đọc cùng lúc **`@Inheritance`, `@DiscriminatorColumn`, `@DiscriminatorValue`, cấu trúc bảng và truy vấn đa hình**. Năm yếu tố này cho biết Hibernate ánh xạ cây lớp Java lên dữ liệu SQL như thế nào, tránh nhầm lẫn giữa kiểu con, cột trạng thái và định danh bản ghi.
