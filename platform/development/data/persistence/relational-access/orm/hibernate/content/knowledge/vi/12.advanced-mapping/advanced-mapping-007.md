# Quan hệ đa hình bằng @Any và giới hạn bảo toàn tham chiếu trong Hibernate ORM

Trong mô hình quan hệ thông thường, một thuộc tính entity như `Comment.article` được ánh xạ bằng `@ManyToOne`: cột `article_id` trong bảng `comments` tham chiếu đến khóa chính của **một bảng đích xác định** là `articles`.

Nhưng một số nghiệp vụ muốn cùng một bản ghi có thể trỏ đến **những loại entity khác nhau**. Ví dụ một bình luận có thể gắn vào bài viết (`Article`), video (`Video`) hoặc một loại nội dung khác. Các entity đích có thể thuộc những bảng hoàn toàn riêng biệt và **không cùng một hệ phân cấp entity JPA**.

Hibernate ORM cung cấp ánh xạ đặc thù `@Any` cho tình huống này. Thay vì lưu một khóa ngoại tới một bảng duy nhất, bản ghi nguồn lưu **hai thông tin**:

- **Discriminator**: mã cho biết đối tượng được tham chiếu thuộc loại entity nào.
- **Identifier**: giá trị khóa chính của hàng trong bảng thuộc loại đó.

Ví dụ:

| comment_id | body | target_type | target_id |
|---:|---|---|---:|
| 1 | Bài viết rất hữu ích | `ARTICLE` | 12 |
| 2 | Video dễ hiểu | `VIDEO` | 12 |
| 3 | Cần bổ sung ví dụ | `ARTICLE` | 18 |

Giá trị `target_id = 12` có thể xuất hiện cả ở bài viết và video; **chỉ cặp `(target_type, target_id)` mới xác định đối tượng đích**.

Cách này linh hoạt, nhưng có một đánh đổi kiến trúc quan trọng: **một cột `target_id` không thể dùng khóa ngoại SQL thông thường để trỏ luân phiên đến nhiều bảng khác nhau theo giá trị `target_type`**. Hibernate có thể diễn giải tham chiếu ở tầng ORM, nhưng database không tự bảo đảm tính tồn tại của mọi đối tượng đích như với foreign key đơn trị truyền thống.

Bài học trình bày cơ chế `@Any`, một ví dụ hoàn chỉnh, giới hạn toàn vẹn tham chiếu, các tác động đến truy vấn và vòng đời dữ liệu, đồng thời so sánh những phương án mô hình hóa thay thế.

## 1. Từ `@ManyToOne` tới quan hệ đa hình

### 1.1. Quan hệ đơn trị thông thường

Với mô hình một bình luận thuộc về một bài viết:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "article_id", nullable = false)
private Article article;
```

Database có thể bảo vệ liên kết:

```sql
CREATE TABLE comments (
    id BIGINT PRIMARY KEY,
    article_id BIGINT NOT NULL,
    body VARCHAR(500) NOT NULL,

    CONSTRAINT fk_comment_article
        FOREIGN KEY (article_id)
        REFERENCES articles(id)
);
```

Nếu ứng dụng ghi `article_id = 999` nhưng không có bài viết 999, foreign key có thể từ chối thao tác. Nếu muốn xóa bài viết đang được tham chiếu, database cũng có thể ngăn hoặc thực hiện chính sách `ON DELETE` đã cấu hình.

Trong trường hợp này, quan hệ có **một bảng đích rõ ràng**, nên ràng buộc FK được xác định tường minh.

### 1.2. Yêu cầu đa hình

Giả sử bình luận có thể thuộc một trong ba loại nội dung:

```text
                      +------------------+
                      |      Comment     |
                      |------------------|
                      | id               |
                      | body             |
                      | target           |
                      +--------+---------+
                               |
                    target_type + target_id
                               |
                +--------------+--------------+
                |                             |
         ARTICLE, 12                    VIDEO, 12
                |                             |
                v                             v
       +----------------+             +----------------+
       |    articles    |             |     videos     |
       | id = 12        |             | id = 12        |
       +----------------+             +----------------+
```

Nếu dùng một thuộc tính `Comment.target`, kiểu Java của target có thể là một interface như `CommentTarget`; từng entity cụ thể tự định nghĩa bảng, trường dữ liệu và nghiệp vụ riêng.

Dùng `@ManyToOne` thông thường không diễn đạt được “FK sẽ trỏ đến bảng articles hoặc videos tùy giá trị cột khác”. Đó chính là trường hợp `@Any` giải quyết ở **tầng ánh xạ Hibernate**.

### 1.3. “Đa hình” ở đây khác đa hình kế thừa JPA

Có hai kiểu đa hình cần phân biệt:

1. **Đa hình trong hệ phân cấp entity (`@Inheritance`):** `Article` và `Video` có thể kế thừa một entity cha `Content` được JPA mapping theo `SINGLE_TABLE`, `JOINED` hoặc `TABLE_PER_CLASS`.
2. **`@Any`:** các entity đích có thể **không có entity cha chung**, không cùng bảng và chỉ được liên kết bởi discriminator cộng khóa chính.

`@Any` không tự tạo một hệ kế thừa JPA và không khiến các bảng đích dùng chung identity space. Nó là một **liên kết đa hình kiểu “một trong nhiều loại”**, không phải một subtype mapping của đối tượng nguồn.

## 2. Cấu trúc dữ liệu của ánh xạ `@Any`

Một liên kết `@Any` đơn trị thường được lưu bằng hai cột trong bảng của entity sở hữu quan hệ:

```text
comments
+----+------------------+-------------+-----------+
| id | body             | target_type | target_id |
+----+------------------+-------------+-----------+
|  1 | Bình luận A      | ARTICLE     |        12 |
|  2 | Bình luận B      | VIDEO       |        34 |
+----+------------------+-------------+-----------+
                         |             |
                         |             +-- Identifier của target
                         |
                         +-- Mã để chọn entity mapping đích
```

Hibernate cần trả lời:

- Nếu `target_type = 'ARTICLE'` thì Java entity class nào tương ứng?
- Nếu `target_type = 'VIDEO'` thì Java entity class nào tương ứng?
- Khóa `target_id` dùng kiểu Java/JDBC nào để tìm hàng đích?
- Khi ứng dụng gán một entity cụ thể vào `Comment.target`, Hibernate phải ghi discriminator và identifier nào?

Các thông tin đó được mô tả bằng annotation ánh xạ `@Any` và các annotation đi kèm.

Điểm khác với FK truyền thống: **Hibernate biết cách tìm bảng qua metadata; cơ sở dữ liệu chỉ nhìn thấy các giá trị cột thông thường**, trừ khi dự án bổ sung cơ chế kiểm soát riêng.

## 3. Ví dụ Hibernate 6: một bình luận cho bài viết hoặc video

Các annotation ở phần này minh họa **phong cách ánh xạ Hibernate ORM 6.x**. `@Any` là tính năng riêng Hibernate, không phải annotation của Jakarta Persistence. API và cú pháp ánh xạ `@Any` ở các dòng Hibernate cũ có khác biệt; khi nâng cấp phải dùng tài liệu đúng phiên bản.

### 3.1. Interface biểu thị đối tượng có thể bình luận

```java
package com.example.content;

public interface CommentTarget {
    Long getId();
}
```

Interface này là **hợp đồng Java của ứng dụng**, không phải một entity JPA và không có bảng vật lý riêng.

### 3.2. Entity `Article`

```java
package com.example.content;

import jakarta.persistence.*;

@Entity
@Table(name = "articles")
public class Article implements CommentTarget {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    protected Article() {
    }

    public Article(String title) {
        this.title = title;
    }

    @Override
    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

### 3.3. Entity `Video`

```java
package com.example.content;

import jakarta.persistence.*;

@Entity
@Table(name = "videos")
public class Video implements CommentTarget {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 250)
    private String playbackUrl;

    protected Video() {
    }

    public Video(String playbackUrl) {
        this.playbackUrl = playbackUrl;
    }

    @Override
    public Long getId() {
        return id;
    }

    public String getPlaybackUrl() {
        return playbackUrl;
    }
}
```

Hai entity cùng thực hiện `CommentTarget` nhưng **không kế thừa một `@Entity` chung** và được lưu ở hai bảng độc lập.

### 3.4. Entity `Comment` dùng `@Any`

```java
package com.example.content;

import jakarta.persistence.*;
import org.hibernate.annotations.Any;
import org.hibernate.annotations.AnyDiscriminator;
import org.hibernate.annotations.AnyDiscriminatorValue;
import org.hibernate.annotations.AnyKeyJavaClass;

@Entity
@Table(name = "comments")
public class Comment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 500)
    private String body;

    @Any(fetch = FetchType.LAZY)
    @AnyDiscriminator(DiscriminatorType.STRING)
    @AnyDiscriminatorValue(
        discriminator = "ARTICLE",
        entity = Article.class
    )
    @AnyDiscriminatorValue(
        discriminator = "VIDEO",
        entity = Video.class
    )
    @AnyKeyJavaClass(Long.class)
    @Column(name = "target_type", nullable = false, length = 16)
    @JoinColumn(name = "target_id", nullable = false)
    private CommentTarget target;

    protected Comment() {
    }

    public Comment(String body, CommentTarget target) {
        this.body = body;
        this.target = target;
    }

    public Long getId() {
        return id;
    }

    public String getBody() {
        return body;
    }

    public CommentTarget getTarget() {
        return target;
    }

    public void setTarget(CommentTarget target) {
        this.target = target;
    }
}
```

Các import `jakarta.persistence.*` cung cấp `DiscriminatorType`, `FetchType`, `Column` và `JoinColumn`. Những annotation riêng `Any`/`AnyDiscriminator`/`AnyDiscriminatorValue`/`AnyKeyJavaClass` đến từ Hibernate.

### 3.5. Diễn giải từng annotation

| Annotation | Vai trò |
|---|---|
| `@Any` | Thông báo đây là quan hệ đa hình đặc thù Hibernate |
| `@Any(fetch = LAZY)` | Yêu cầu trì hoãn tải entity đích khi cơ chế/runtime hỗ trợ |
| `@AnyDiscriminator(DiscriminatorType.STRING)` | Mô tả loại discriminator được lưu, ở đây là chuỗi |
| `@AnyDiscriminatorValue(discriminator = "ARTICLE", entity = Article.class)` | Ánh xạ mã `ARTICLE` sang entity `Article` |
| `@AnyDiscriminatorValue(discriminator = "VIDEO", entity = Video.class)` | Ánh xạ mã `VIDEO` sang entity `Video` |
| `@AnyKeyJavaClass(Long.class)` | Khai báo kiểu Java của khóa định danh đích |
| `@Column(name = "target_type")` | Cột vật lý chứa discriminator |
| `@JoinColumn(name = "target_id")` | Cột vật lý chứa identifier của đối tượng đích |

Với một `Comment` trỏ tới `Article(id = 12)`, Hibernate cần ghi `target_type = 'ARTICLE'` và `target_id = 12`. Nếu trỏ tới `Video(id = 12)`, cột target ID vẫn là 12 nhưng mã discriminator đổi thành `VIDEO`.

**Giới hạn quan trọng:** các loại target trong một `@Any` cần có kiểu định danh tương thích với ánh xạ key đã khai báo. Ví dụ `Article.id` là `Long` còn `Video.id` là `UUID` thì không thể mặc định dùng chung `@AnyKeyJavaClass(Long.class)` rồi mong Hibernate tự xử lý không mất thông tin. Muốn liên kết nhiều loại khóa khác nhau cần thiết kế lại contract lưu ID hoặc chọn mô hình khác.

### 3.6. DDL tương ứng

Ví dụ PostgreSQL, độc lập với lựa chọn generator cụ thể:

```sql
CREATE TABLE articles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);

CREATE TABLE videos (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    playback_url VARCHAR(250) NOT NULL
);

CREATE TABLE comments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    body VARCHAR(500) NOT NULL,
    target_type VARCHAR(16) NOT NULL,
    target_id BIGINT NOT NULL,

    CONSTRAINT ck_comments_target_type
        CHECK (target_type IN ('ARTICLE', 'VIDEO'))
);

CREATE INDEX idx_comments_target
    ON comments(target_type, target_id);
```

Hai điểm dễ bỏ sót:

1. Bảng `comments` có **index `(target_type, target_id)`** phục vụ truy vấn tất cả bình luận của một target.
2. Bảng `comments` **không có khóa ngoại SQL từ `target_id` tới cả hai bảng `articles` và `videos`**, bởi foreign key SQL bình thường phải tham chiếu một bảng đích xác định.

Ràng buộc `CHECK` chỉ bảo đảm discriminator thuộc tập giá trị được phép. Nó không chứng minh `Article(12)` hoặc `Video(12)` thực sự tồn tại.

## 4. Khi Hibernate đọc và ghi một quan hệ `@Any`

### 4.1. Ghi dữ liệu

Ví dụ ứng dụng đã tải một bài viết hiện hữu:

```java
Article article = em.find(Article.class, articleId);

if (article == null) {
    throw new IllegalArgumentException("Article not found");
}

Comment comment = new Comment(
    "Bài viết có ví dụ dễ hiểu",
    article
);

em.persist(comment);
```

Khi flush, Hibernate dựa trên loại entity đích (`Article`), mã discriminator đã khai báo và identifier của article để ghi hai cột `target_type`, `target_id`.

Ví dụ SQL minh họa:

```sql
INSERT INTO comments (body, target_type, target_id)
VALUES ('Bài viết có ví dụ dễ hiểu', 'ARTICLE', 12);
```

Hibernate không biến `target_id` thành một FK động trên database. Sự liên kết chỉ được hiểu đúng khi Hibernate đọc cả cặp giá trị.

Cũng cần lưu ý: đây là ví dụ trong một **transaction do caller hoặc framework quản lý**, không phải câu lệnh `persist` độc lập luôn commit thành công.

### 4.2. Đọc dữ liệu

Khi tải `Comment(id = 1)`, Hibernate đọc `target_type` và `target_id`. Ví dụ:

```text
comments:
  id = 1
  target_type = 'ARTICLE'
  target_id = 12

Hibernate:
  'ARTICLE' -> Article.class
  12        -> khóa chính của Article
       |
       v
  Comment.target -> Article(id = 12)
```

Nếu association được trì hoãn và các điều kiện lazy loading phù hợp, Hibernate có thể chưa cần lấy toàn bộ cột của Article ngay lập tức. Khi ứng dụng yêu cầu `comment.getTarget()` hoặc một thuộc tính của target, Hibernate có thể phải thực hiện truy vấn bổ sung.

Ví dụ:

```java
Comment comment = em.find(Comment.class, commentId);

CommentTarget target = comment.getTarget();

if (target instanceof Article article) {
    System.out.println(article.getTitle());
} else if (target instanceof Video video) {
    System.out.println(video.getPlaybackUrl());
}
```

Code minh họa nhánh xử lý theo kiểu target thực tế. Trong hệ thống lớn, nên chuyển hướng xử lý này về một service/domain interface phù hợp thay vì để mọi controller rải rác `instanceof`.

### 4.3. Đổi target

Nếu ứng dụng cho phép chuyển một bình luận từ bài viết sang video:

```java
Comment comment = em.find(Comment.class, commentId);
Video video = em.find(Video.class, videoId);

if (video == null) {
    throw new IllegalArgumentException("Video not found");
}

comment.setTarget(video);
```

Trong transaction hợp lệ, khi flush Hibernate có thể cập nhật cả discriminator và ID:

```sql
UPDATE comments
SET target_type = 'VIDEO',
    target_id = :videoId
WHERE id = :commentId;
```

Hai cột **phải thay đổi nhất quán**. Việc chỉ cập nhật `target_id` bằng SQL thủ công trong khi giữ nguyên `target_type` có thể khiến liên kết chuyển sang một đối tượng khác, hoặc trỏ tới đối tượng không tồn tại.

### 4.4. Target chưa được lưu

Nếu gán vào `Comment.target` một `Article` mới vẫn chưa có ID, Hibernate cần biết cách xác định định danh và thứ tự persist các entity. Không nên mặc định `@Any` sẽ cascade persist đến mọi loại target mới.

Ví dụ:

```java
Article article = new Article("Bài viết mới");
Comment comment = new Comment("Bình luận", article);

// Chủ động persist các entity theo vòng đời nghiệp vụ.
em.persist(article);
em.persist(comment);
```

Cách này làm rõ ý định tạo Article trước khi Comment cần tham chiếu tới ID của Article. Nếu dùng generator cần `INSERT` để lấy ID (`IDENTITY`), thời điểm SQL thực thi phụ thuộc Hibernate và transaction.

Thông thường, đối tượng đích như `Article` hay `Video` có vòng đời độc lập với bình luận, nên **không nên mặc định cascade REMOVE từ Comment sang target**.

## 5. Bảo toàn tham chiếu là gì và tại sao `@Any` làm nó yếu hơn?

Trong database quan hệ, **referential integrity** (toàn vẹn tham chiếu) nghĩa là một khóa tham chiếu không được chỉ tới hàng không tồn tại, theo chính sách ràng buộc đã khai báo.

Với `@ManyToOne` tới một bảng:

```sql
FOREIGN KEY (article_id)
REFERENCES articles(id)
```

database có thể kiểm tra lúc insert/update và kiểm soát việc xóa hàng đích.

Với `@Any`:

```text
comments.target_type = ARTICLE -> articles(id)
comments.target_type = VIDEO   -> videos(id)

Nhưng chỉ có một cột comments.target_id.
```

Một foreign key SQL thông thường không có cú pháp dạng:

```sql
-- CÚ PHÁP GIẢ, KHÔNG PHẢI SQL HỢP LỆ:
FOREIGN KEY (target_id)
REFERENCES CASE target_type
    WHEN 'ARTICLE' THEN articles(id)
    WHEN 'VIDEO' THEN videos(id)
END;
```

Vì FK phải tham chiếu **một quan hệ đích xác định**, schema không thể khai báo **một FK duy nhất đa bảng** dựa trên giá trị discriminator theo cách đơn giản đó.

Hệ quả: dữ liệu này vẫn có thể được DB chấp nhận:

```sql
INSERT INTO comments (body, target_type, target_id)
VALUES ('Bình luận mồ côi', 'ARTICLE', 999999);
```

Ngay cả khi bảng `articles` không có ID `999999`, `CHECK(target_type IN (...))` vẫn thỏa mãn, kiểu dữ liệu vẫn hợp lệ và không có FK tới articles để từ chối.

**Hibernate hiểu cách tìm đối tượng, nhưng không tự tạo được ràng buộc foreign key vật lý bảo vệ tất cả đích.**

### 5.1. Những gì database vẫn bảo đảm được

Dù không có FK đa bảng thông thường, schema vẫn có thể bảo vệ một số tính chất:

- `NOT NULL`: cặp discriminator và ID bắt buộc có giá trị.
- `CHECK (target_type IN (...))`: discriminator thuộc danh sách đã được hỗ trợ.
- Kiểu SQL của `target_id`: ví dụ `BIGINT`, không phải một chuỗi tùy ý.
- Index `(target_type, target_id)`: truy vấn nhanh hơn, nhưng index **không kiểm tra tồn tại target**.
- `UNIQUE` nếu nghiệp vụ cần giới hạn số liên kết trên một target, nhưng phải xét phạm vi uniqueness và semantics null.

Đây đều là ràng buộc hữu ích. Tuy nhiên, **không ràng buộc nào trong số đó tự xác nhận target ID đang tồn tại trong đúng bảng**.

### 5.2. Trùng ID giữa các bảng là bình thường

Giả sử:

```text
Article(id=12) là bài viết "Hibernate 6"
Video(id=12)   là video "Giới thiệu ORM"
```

Khi đó:

```text
('ARTICLE', 12) != ('VIDEO', 12)
```

Nếu truy vấn hoặc cache chỉ dùng `target_id` mà không dùng discriminator, hai đối tượng có thể bị trộn lẫn. Ví dụ sai:

```java
Map<Long, List<Comment>> commentsByTargetId;
```

Map này không đủ để phân biệt Article(12) với Video(12). Một khóa logic đầy đủ cần bao gồm **loại và ID**, cùng tenant hoặc phạm vi khác nếu đó là một phần của identity ứng dụng:

```java
public record TargetKey(String type, Long id) {
}
```

Nếu multi-tenant, có thể dùng một khóa gồm `tenantId`, `type` và `id` theo thiết kế nghiệp vụ.

## 6. Mối nguy lớn nhất: tham chiếu mồ côi khi xóa target

Một entity có thể tồn tại hợp lệ lúc Comment được tạo nhưng bị xóa về sau.

Giả sử:

```text
articles:
  id = 12, title = "Hibernate ORM"

comments:
  id = 1, target_type = ARTICLE, target_id = 12
```

Sau đó có lệnh:

```sql
DELETE FROM articles WHERE id = 12;
```

Nếu không có cơ chế bảo vệ bổ sung, database vẫn để lại:

```text
comments:
  id = 1, target_type = ARTICLE, target_id = 12

articles:
  [không còn hàng 12]
```

Comment giờ chứa **dangling reference**. Hibernate có thể phát hiện lỗi khi cần resolve target, ví dụ exception do entity đích không tìm thấy; loại exception và thời điểm xảy ra phụ thuộc đường load, lazy proxy và phiên bản Hibernate.

### 6.1. Không nên dựa vào lazy proxy để chứng minh tồn tại

Đối với liên kết lazy, Hibernate đôi khi chỉ cần discriminator và ID để cung cấp reference. Việc reference khác `null` **không chứng minh** hàng đích còn tồn tại. Truy cập một thuộc tính thật của target mới có thể yêu cầu truy vấn và làm lộ lỗi.

Vì vậy, không dùng:

```java
if (comment.getTarget() != null) {
    // Không đủ căn cứ kết luận target thật sự tồn tại.
}
```

để bảo vệ thao tác nghiệp vụ nhạy cảm. Khi cần xác nhận, phải kiểm tra tồn tại theo loại entity đúng và tính đến transaction/concurrency.

### 6.2. Chính sách khi xóa target

Một ứng dụng dùng `@Any` nên định nghĩa rõ chuyện gì xảy ra với các liên kết khi target bị xóa:

| Chính sách | Ý nghĩa | Điều cần triển khai |
|---|---|---|
| **RESTRICT** | Không cho xóa target nếu còn comment | Kiểm tra tham chiếu, bảo vệ concurrency, có thể cần trigger/ràng buộc bổ sung |
| **CASCADE ở tầng nghiệp vụ** | Xóa comment cùng target | Service hoặc job phải xóa các comment liên quan đúng loại và ID |
| **SOFT DELETE** | Target vẫn còn hàng nhưng đánh dấu đã xóa | Mọi truy vấn và quyền truy cập phải tôn trọng trạng thái soft delete |
| **RETAIN AS HISTORY** | Giữ comment nhưng target có thể biến mất | Thiết kế rõ dữ liệu snapshot và UX khi nội dung gốc không còn |
| **SET NULL / UNLINK** | Comment không còn target | Chỉ dùng nếu mapping cho phép liên kết nullable, hai cột phải nhất quán |

Không có lựa chọn nào luôn đúng. Với bình luận công khai, cascade delete có thể hợp lý; với bản ghi kiểm toán, giữ snapshot độc lập có thể cần thiết hơn. **Quan trọng là chính sách phải được thực hiện trong mọi đường xóa**, bao gồm admin script, batch job và service khác.

### 6.3. Xóa theo cặp type + ID

Nếu chọn xóa comment trước khi xóa Article, SQL phải lọc cả hai cột:

```sql
DELETE FROM comments
WHERE target_type = 'ARTICLE'
  AND target_id = :articleId;
```

Thiếu `target_type` có thể xóa nhầm các comment của `Video` có cùng ID.

Sau đó mới xóa Article:

```sql
DELETE FROM articles
WHERE id = :articleId;
```

Hai bước nên được phối hợp trong transaction thích hợp. Nhưng **chỉ dùng transaction không tự loại bỏ mọi race condition** khi các writer khác được phép chèn Comment song song. Phần concurrency được trình bày tiếp theo.

## 7. Giới hạn của kiểm tra ở tầng ứng dụng và vấn đề concurrent writes

Một service có thể kiểm tra `Article` tồn tại trước khi tạo Comment:

```java
Article article = em.find(Article.class, articleId);
if (article == null) {
    throw new IllegalArgumentException("Article not found");
}

em.persist(new Comment("Nội dung mới", article));
```

Đây là validation tốt về mặt nghiệp vụ, nhưng **không tương đương ràng buộc FK tại database**.

Xét hai transaction:

```text
Transaction T1: tạo Comment          Transaction T2: xóa Article
-------------------------------      --------------------------------
SELECT article 12 -> tồn tại
                                     DELETE article 12
                                     COMMIT
INSERT comment(target=ARTICLE,12)
COMMIT
-------------------------------      --------------------------------
Kết quả: comment trỏ đến article đã bị xóa.
```

Tùy isolation level, lịch khóa, thứ tự thao tác và cơ chế persistence, một hệ thống có thể gặp trường hợp tương tự. Chỉ vì việc kiểm tra và insert nằm trong cùng một transaction không bảo đảm **mọi transaction khác** bị ngăn xóa target.

### 7.1. Những biện pháp giảm hoặc loại rủi ro

- Định nghĩa **một lớp service sở hữu vòng đời** tạo/xóa target và liên kết.
- Sử dụng **locking** và một quy tắc khóa nhất quán ở mọi đường tạo/xóa, nếu database và yêu cầu cho phép.
- Cân nhắc **database trigger** cho các loại target đã biết, nhưng phải thiết kế đủ cả thao tác insert/update liên kết lẫn delete target, và phân tích isolation/concurrency để tránh race.
- Sử dụng một **bảng gốc/registry** có FK thực nếu toàn vẹn tham chiếu bắt buộc ở mức DB.
- Với hệ thống phân tán, dùng event/outbox và cơ chế reconcile nếu chấp nhận nhất quán cuối cùng, đồng thời hiểu rằng đây **không phải referential integrity đồng bộ**.
- Có job kiểm tra orphan định kỳ để phát hiện vi phạm tồn tại từ dữ liệu legacy hoặc đường ghi ngoài ứng dụng.

**Lưu ý:** “thêm trigger kiểm tra target có tồn tại” chưa chắc đủ. Nếu trigger chỉ đọc sự tồn tại mà không phối hợp khóa với transaction xóa, vẫn có thể xảy ra race. Muốn mức bảo đảm tương đương FK phải thiết kế quy tắc bảo vệ tất cả writer và delete path trên DB thực tế.

## 8. Tìm và xử lý orphan references

Khi không có FK cứng, dự án nên chủ động theo dõi các liên kết không còn target.

Ví dụ SQL PostgreSQL để tìm comment có discriminator hợp lệ nhưng target không tồn tại:

```sql
SELECT c.id, c.target_type, c.target_id
FROM comments c
LEFT JOIN articles a
       ON c.target_type = 'ARTICLE'
      AND c.target_id = a.id
LEFT JOIN videos v
       ON c.target_type = 'VIDEO'
      AND c.target_id = v.id
WHERE
    (c.target_type = 'ARTICLE' AND a.id IS NULL)
    OR
    (c.target_type = 'VIDEO' AND v.id IS NULL);
```

Truy vấn này giả định tập discriminator được giới hạn ở `ARTICLE` và `VIDEO`. Nếu database cho phép discriminator không được biết tới, cần kiểm tra thêm loại không hợp lệ:

```sql
SELECT id, target_type, target_id
FROM comments
WHERE target_type NOT IN ('ARTICLE', 'VIDEO');
```

Với `target_type` nullable, điều kiện `NOT IN` không tự bắt `NULL`; khi thiết kế cột bắt buộc, hãy đặt `NOT NULL`.

### 8.1. Xử lý orphan theo nghiệp vụ

Không nên tự động xóa mọi orphan nếu comment có giá trị pháp lý, kiểm toán hoặc lịch sử. Một số hướng:

- Xóa orphan theo policy retention rõ ràng.
- Đánh dấu record lỗi và tách khỏi view thông thường.
- Lưu snapshot nội dung đích tại thời điểm tạo nếu nghiệp vụ cần xem lịch sử.
- Khôi phục target nếu xóa nhầm và còn khả năng phục hồi.
- Ghi lại nguyên nhân (migration, batch delete, bug, thay đổi discriminator).

Job kiểm tra chỉ phát hiện dữ liệu đang lỗi ở thời điểm chạy; nó không thay thế một cơ chế bảo vệ đồng thời lúc ghi.

## 9. `@Any` và vấn đề truy vấn HQL/JPQL

Một quan hệ `@ManyToOne` bình thường có mapping tới **một entity type cụ thể**. Hibernate có thể biết bảng cần join và các điều kiện FK ngay khi xây dựng truy vấn:

```java
select c
from CommentToArticle c
join c.article a
where a.title like :pattern
```

Với `@Any`, bảng đích chỉ được biết theo giá trị `target_type` của **từng hàng kết quả**. Do đó, **không nên kỳ vọng có thể dùng mọi cú pháp path join và fetch join như với association JPA thông thường**.

Ví dụ giả định không di động/không nên dựa vào như một JPQL join bình thường:

```sql
-- Ý tưởng sai về mặt cấu trúc SQL:
JOIN c.target t
-- "t" có lúc là bảng articles, có lúc là bảng videos;
-- một JOIN SQL thông thường phải biết bảng tại lúc biên dịch.
```

Các khả năng HQL đối với `@Any` phụ thuộc phiên bản Hibernate; Hibernate có những hạn chế với đường dẫn polymorphic association không có entity target type thống nhất. **Không thiết kế query phức tạp dựa trên giả định rằng `JOIN FETCH c.target` luôn được hỗ trợ**.

### 9.1. Truy vấn bằng hai cột vật lý

Muốn lấy comment của Article(12), cách đơn giản là truy vấn theo discriminator và ID. Ví dụ native SQL:

```sql
SELECT c.id, c.body, c.target_type, c.target_id
FROM comments c
WHERE c.target_type = 'ARTICLE'
  AND c.target_id = :articleId
ORDER BY c.id;
```

Khi cần hiển thị danh sách bình luận kèm thông tin entity đích thuộc một loại đã biết, có thể join bảng đích **cụ thể**:

```sql
SELECT c.id, c.body, a.title
FROM comments c
JOIN articles a
  ON c.target_type = 'ARTICLE'
 AND c.target_id = a.id
WHERE c.target_type = 'ARTICLE'
ORDER BY c.id;
```

SQL trên chỉ dành cho bình luận của Article; nó không cố biến `@Any` thành một join đa bảng chung.

### 9.2. Khi cần nhiều loại target trong một báo cáo

Có thể:

1. Truy vấn comment và cặp type/ID trước.
2. Phân nhóm theo discriminator.
3. Truy vấn từng entity type theo **tập ID**.
4. Ghép kết quả thành DTO theo `TargetKey(type, id)`.

Hoặc dùng `UNION ALL` ở SQL chuyên biệt cho báo cáo:

```sql
SELECT c.id AS comment_id,
       c.body,
       'ARTICLE' AS target_type,
       a.id AS target_id,
       a.title AS target_label
FROM comments c
JOIN articles a
  ON c.target_type = 'ARTICLE'
 AND c.target_id = a.id

UNION ALL

SELECT c.id AS comment_id,
       c.body,
       'VIDEO' AS target_type,
       v.id AS target_id,
       v.playback_url AS target_label
FROM comments c
JOIN videos v
  ON c.target_type = 'VIDEO'
 AND c.target_id = v.id;
```

Đây là SQL minh họa cho hai loại target cụ thể, cần điều chỉnh truy vấn thật theo schema và dữ liệu hiển thị. **Mỗi lần thêm một loại target**, query/report liên quan cũng cần được xem xét; `@Any` không tự xóa bỏ chi phí ấy.

### 9.3. Không dùng discriminator do client gửi trực tiếp để xây SQL

Nếu API nhận `targetType` từ request, nên parse vào một tập giá trị hữu hạn, xác nhận quyền truy cập và ánh xạ qua cấu hình server. Không ghép tên bảng từ chuỗi do người dùng gửi vào SQL/HQL một cách tùy ý.

Thay vì:

```java
String sql = "SELECT * FROM " + requestType + " WHERE id = ?";
```

hãy sử dụng tập enum/registry được ứng dụng định nghĩa, các truy vấn đã biết và tham số được bind đúng. Điều này vừa bảo vệ an toàn truy vấn, vừa tránh cho client điều khiển trực tiếp tên class entity hoặc bảng SQL.

## 10. Lazy loading và khả năng phát sinh N+1

Với mapping:

```java
@Any(fetch = FetchType.LAZY)
private CommentTarget target;
```

Hibernate có discriminator và target ID nên trong một số cấu hình có thể trì hoãn tải entity đích. Tuy vậy, mức độ lazy thực tế phụ thuộc version, cơ chế proxy/enhancement, fetch plan và việc target đã có trong persistence context/cache hay chưa.

Ví dụ truy vấn 100 comment:

```java
List<Comment> comments = em.createQuery(
    "select c from Comment c order by c.id",
    Comment.class
).getResultList();

for (Comment comment : comments) {
    System.out.println(comment.getTarget());
}
```

Nếu `toString()` của target đi vào các thuộc tính chưa tải, Hibernate có thể phải truy vấn riêng để resolve nhiều target, tạo dạng **N+1**:

```text
1 SELECT lấy 100 comments
+
n SELECT(s) lấy target tương ứng
-----------------------------
Có thể nhiều round-trip xuống database
```

Không nên giả định Hibernate có thể dùng **một fetch join đa bảng duy nhất** để lấy đầy đủ mọi loại target. Các query tối ưu có thể cần nhóm theo target type, đọc dữ liệu theo batch hoặc chuyển sang SQL báo cáo chuyên biệt.

### 10.1. Lựa chọn khi use case chỉ cần metadata

Nếu màn hình chỉ cần bình luận và biểu tượng loại target, DTO có `target_type`/`target_id` thường đủ. Không có lý do bắt buộc tải toàn bộ Article/Video khi danh sách chưa cần chúng.

Nếu cần mỗi comment kèm tiêu đề target, cân nhắc:

- Tải theo loại target và dùng `IN (...)` để giảm số truy vấn.
- Lấy thông tin hiển thị dạng snapshot đã lưu trên comment nếu chấp nhận yêu cầu đồng bộ hóa.
- Dùng native SQL báo cáo `UNION ALL` khi số loại ít và schema ổn định.
- Phân trang ở nguồn comment trước khi truy xuất target cho trang kết quả.

### 10.2. Không dùng EAGER để che mọi lỗi

Đặt `fetch = EAGER` không giải quyết giới hạn FK và có thể khiến Hibernate tải nhiều target không cần thiết. Eager cũng không bảo đảm tất cả dữ liệu sẽ được lấy bằng một SQL duy nhất.

Tối ưu là chọn **fetch plan theo nhu cầu của từng màn hình**, không phải buộc ORM tải mọi quan hệ đa hình mọi lúc.

### 10.3. Session và proxy

Nếu trả `Comment` ra khỏi Session rồi truy cập một target lazy chưa initialized, có thể gặp `LazyInitializationException` hoặc lỗi resolve entity nếu target đã bị xóa.

Đối với API, nên tạo DTO trong phạm vi transaction và không để serializer tự đi qua `getTarget()` một cách không kiểm soát.

## 11. `@Any` không tự cung cấp quan hệ hai chiều

Khi Comment có:

```java
@Any
private CommentTarget target;
```

không thể tự suy ra rằng entity `Article` có một collection chuẩn:

```java
@OneToMany(mappedBy = "target")
private List<Comment> comments;
```

theo cùng cách với `@ManyToOne` thông thường. Nguyên nhân là `target` không phải một FK duy nhất tới bảng `articles`, mà là liên kết được diễn giải qua **discriminator + ID** và có thể trỏ nhiều bảng khác.

Nếu nghiệp vụ cần `article.getComments()`, hãy cân nhắc:

- Một repository method rõ ràng: `findCommentsForArticle(articleId)`.
- Một mapping phụ bổ sung có điều kiện/discriminator riêng Hibernate nếu được thiết kế và kiểm chứng chặt chẽ.
- Một mô hình DB khác với FK thật hoặc quan hệ kế thừa.
- DTO/query chuyên biệt cho use case thay vì tự động thêm navigation hai chiều.

Việc cố tạo association hai chiều đầy đủ từ mọi concrete target có thể làm ánh xạ phức tạp, khó kiểm soát SQL và vòng đời hơn giá trị nó mang lại.

## 12. `@Any` khác `@ManyToAny`

Trong Hibernate có một khái niệm liên quan: **`@ManyToAny`**, dùng cho một collection có thể chứa các entity thuộc nhiều loại khác nhau.

Ví dụ khái niệm:

```text
ArticleBundle
    |
    +--> items:
           - Article(12)
           - Video(34)
           - Article(18)
```

Với collection như vậy, Hibernate có thể cần một **join table** lưu owner ID, discriminator và target ID, cùng các annotation mapping tương ứng của `@ManyToAny`.

Phân biệt:

| Tiêu chí | `@Any` | `@ManyToAny` |
|---|---|---|
| Số đích trên một field | Một đối tượng đa hình | Một collection nhiều đối tượng đa hình |
| Dữ liệu tham chiếu | Thường hai cột trong bảng entity nguồn | Thường join table cho các phần tử |
| Có thể trỏ nhiều entity type | Có | Có |
| Vấn đề FK đa bảng | Vẫn tồn tại | Vẫn tồn tại trên các liên kết đích |
| Ứng dụng điển hình | Comment trỏ tới Article hoặc Video | Một nhóm nội dung gồm nhiều loại entity |

Việc chuyển từ `@Any` sang `@ManyToAny` **không giải quyết tự động toàn vẹn tham chiếu**; nó chỉ thay đổi cardinality và cách lưu tập liên kết.

## 13. Thêm loại entity mới hoặc đổi discriminator

Giả sử ban đầu chỉ hỗ trợ `ARTICLE` và `VIDEO`; sau đó muốn thêm `PODCAST`.

Các phần cần thay đổi có thể bao gồm:

1. Tạo entity `Podcast` và bảng `podcasts`.
2. Bổ sung `@AnyDiscriminatorValue(discriminator = "PODCAST", entity = Podcast.class)`.
3. Cập nhật `CHECK(target_type IN (...))` trong migration nếu có.
4. Bổ sung logic tạo/xóa, validate quyền truy cập, lookup và chính sách vòng đời.
5. Cập nhật các truy vấn báo cáo, thống kê và orphan scan.
6. Đảm bảo khóa chính của Podcast dùng kiểu tương thích với `@AnyKeyJavaClass`.
7. Đảm bảo không có deployment cũ không hiểu discriminator mới nhưng vẫn đọc dữ liệu được ghi bởi deployment mới.

### 13.1. Discriminator là hợp đồng lưu trữ lâu dài

Không nên tự ý thay `ARTICLE` thành `POST` trong annotation mà không cập nhật dữ liệu cũ. Nếu hàng đang lưu:

```text
target_type = ARTICLE
target_id   = 12
```

nhưng mapping mới chỉ nhận `POST`, Hibernate có thể không còn ánh xạ được discriminator cũ. Cần migration dữ liệu hoặc giai đoạn tương thích có kiểm soát.

**Tên mã discriminator nên ổn định** và không nên phụ thuộc vào tên class Java hay tên package có thể thay đổi khi refactor. Dùng giá trị do thiết kế schema quản lý thường bền vững hơn việc dựa vào tên class tự động.

### 13.2. Rolling deployment

Trong giai đoạn chạy song song hai phiên bản ứng dụng, một phiên bản mới có thể ghi target type mà phiên bản cũ chưa biết. Vì thế, triển khai cần cân nhắc thứ tự:

- Phát hành code có khả năng đọc các giá trị mới trước khi bắt đầu ghi chúng.
- Cập nhật database constraint và dữ liệu đúng thời điểm.
- Kiểm tra các worker, consumer, batch job dùng cùng bảng.
- Có kế hoạch rollback tương thích dữ liệu, không chỉ rollback mã Java.

Đối với `@Any`, discriminator là một phần của **giao thức lưu trữ giữa các phiên bản ứng dụng**.

## 14. Bảo mật và biên giới tenant

Liên kết `(type, id)` là dữ liệu kỹ thuật, không tự chứa thông tin về quyền truy cập. Nếu một request cho phép client chọn `targetType = 'ARTICLE'` và `targetId = 12`, ứng dụng còn phải kiểm tra:

- Người dùng có quyền đọc hoặc bình luận nội dung đích không?
- Đối tượng đó có đang công khai, bị khóa hoặc đã xóa mềm không?
- Target thuộc cùng tenant, tổ chức hoặc workspace với Comment không?
- Có được phép gắn comment vào mọi loại target mà discriminator hỗ trợ không?
- Các loại target có cùng quy tắc retention và bảo mật không?

Ví dụ hệ thống đa tenant có `Article(12)` ở tenant A và `Article(12)` ở tenant B. Nếu ID được cấp trong phạm vi tenant hoặc query không hạn chế tenant, cặp `('ARTICLE', 12)` có thể **không đủ** để nhận diện target trong toàn hệ thống.

Có thể cần mô hình key:

```text
(tenant_id, target_type, target_id)
```

và quy tắc truy vấn/authorization nhất quán. Tuy nhiên, chỉ thêm cột `tenant_id` vào `comments` **vẫn không tạo ra FK đa bảng**. Bảo vệ cross-tenant integrity cần được thực thi ở lớp phù hợp hoặc thiết kế lại schema để có common FK thực.

### Tránh ánh xạ class tùy ý từ input

Không dùng tên Java class do client gửi để gọi reflection và quyết định entity type. Discriminator nên là tập cho phép trên server, ví dụ một enum hoặc registry ánh xạ từ giá trị API được kiểm soát sang các loại đích được hỗ trợ.

Điều này tránh nhầm lẫn giữa “mã lựa chọn nội dung” và “quyền gọi tùy ý một class/SQL table” của ứng dụng.

## 15. Chính sách cascade và vòng đời target

Không nên nhầm mối quan hệ “bình luận nhắc tới nội dung” với “bình luận sở hữu nội dung”.

Một `Comment` được xóa thường **không nên** tự xóa `Article` hay `Video` mà nó tham chiếu. Ngược lại, khi target bị xóa, ứng dụng cần có chính sách với Comment liên quan.

Đối với quan hệ `@Any`, khả năng dùng cascade và các hành vi lifecycle phụ thuộc annotation, mapping và Hibernate version. Nhưng ngay cả khi có API cho cascade, **cấu hình ORM không thể bù hoàn toàn cho thiếu ràng buộc referential integrity ở database** khi dữ liệu bị thay đổi bởi một tiến trình khác hoặc bằng SQL trực tiếp.

Một thiết kế nghiệp vụ thường rõ hơn nếu:

- Service tạo Comment nhận một target **đã tồn tại và được phép bình luận**.
- Service xóa target có trách nhiệm xóa/giữ/ẩn các Comment liên quan.
- Các đường batch/admin migration tuân theo cùng policy.
- Có một cách phát hiện và xử lý orphan sau sự cố hoặc dữ liệu cũ.

### Soft delete

Nếu Article chỉ đổi cột `deleted_at` chứ không bị xóa vật lý, cặp type/ID vẫn trỏ tới một hàng tồn tại. Nhưng ở tầng nghiệp vụ, target có thể không còn hợp lệ để hiển thị hoặc bình luận.

Điều đó cho thấy **referential integrity** và **business validity** là hai mức kiểm tra khác nhau. Ngay cả FK thật cũng không tự đảm bảo target chưa bị khóa, chưa bị ẩn hoặc người dùng có quyền sử dụng.

## 16. Những mô hình thay thế `@Any`

`@Any` linh hoạt nhưng thường là lựa chọn có đánh đổi. Trước khi áp dụng, nên so sánh với các mô hình quan hệ có khả năng tạo FK thật.

### 16.1. Một entity cha chung với `@Inheritance`

Nếu `Article` và `Video` thuộc một loại domain chung có thể mô hình hóa thành `Content`, ta có thể dùng **JPA inheritance**.

Ví dụ:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "contents")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Content {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    protected Content() {
    }

    public Long getId() {
        return id;
    }
}
```

Các subtype:

```java
@Entity
@Table(name = "articles")
public class Article extends Content {
    private String title;
}

@Entity
@Table(name = "videos")
public class Video extends Content {
    private String playbackUrl;
}
```

Comment:

```java
@Entity
@Table(name = "comments")
public class Comment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "content_id", nullable = false)
    private Content target;
}
```

Với chiến lược `JOINED`, các target thuộc hệ kế thừa chia sẻ một hàng gốc ở bảng `contents`, và `comments.content_id` có thể là **foreign key thật tới `contents(id)`**.

Ưu điểm:

- Quan hệ trở thành `@ManyToOne` chuẩn.
- Database có thể bảo vệ FK từ Comment đến hàng gốc Content.
- HQL/JPQL polymorphism thường tự nhiên hơn.
- Các loại content có identity chung và có thể dùng nhiều cơ chế ORM chuẩn.

Đánh đổi:

- Cần thiết kế một hệ entity inheritance chung.
- `JOINED` có thể tạo nhiều join khi lấy subtype.
- Các loại target quá khác nhau có thể không phù hợp gắn chung một hierarchy.

Chú ý: `TABLE_PER_CLASS` vẫn phân tán hàng subtype vào nhiều bảng và không đem lại cùng lợi ích “một bảng gốc vật lý” cho FK theo cách `JOINED` hoặc `SINGLE_TABLE` có thể làm. Phải chọn chiến lược inheritance có chủ đích.

### 16.2. Nhiều foreign key nullable

Nếu tập target nhỏ và ổn định, có thể đưa từng FK thật vào Comment:

```sql
CREATE TABLE comments (
    id BIGINT PRIMARY KEY,
    body VARCHAR(500) NOT NULL,

    article_id BIGINT NULL REFERENCES articles(id),
    video_id BIGINT NULL REFERENCES videos(id),

    CONSTRAINT ck_comment_exactly_one_target CHECK (
        (CASE WHEN article_id IS NOT NULL THEN 1 ELSE 0 END)
      + (CASE WHEN video_id IS NOT NULL THEN 1 ELSE 0 END)
      = 1
    )
);
```

Entity có thể dùng hai association chuẩn:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "article_id")
private Article article;

@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "video_id")
private Video video;
```

Ưu điểm: DB kiểm tra được sự tồn tại của từng target bằng FK và kiểm tra “đúng một target” bằng constraint. Nhược điểm: schema và code phải thêm cột/association cho mỗi loại mới; các cột không dùng sẽ là `NULL`.

Đây thường là lựa chọn tốt nếu chỉ có hai hoặc ba target type và **bảo toàn tham chiếu ở DB là bắt buộc**.

### 16.3. Bảng gốc/registry chung

Một hướng khác là tạo bảng `targets` hoặc `content_registry` chứa **một ID toàn cục và type** của mọi target:

```text
content_registry
+----+----------+
| id | kind     |
+----+----------+
| 12 | ARTICLE  |
| 13 | VIDEO    |
+----+----------+
   ^
   |
comments.target_registry_id -> FK content_registry(id)
```

Khi đó, Comment có thể trỏ tới **một bảng chung**, tạo được FK thực từ comments.

Nhưng cần chú ý: FK từ Comment tới registry chỉ bảo đảm **hàng registry tồn tại**. Nó không tự chứng minh hàng concrete `Article` hoặc `Video` cũng tồn tại nếu registry và bảng concrete không được ràng buộc/đồng bộ thích hợp. Muốn toàn vẹn đầy đủ, cần thiết kế quan hệ và vòng đời các hàng concrete cho đúng, ví dụ dùng `JOINED` inheritance hoặc các constraint/transaction phù hợp.

### 16.4. Bảng liên kết riêng cho từng loại

Ví dụ tạo `article_comments` và `video_comments`, mỗi bảng có FK tới đúng loại target và Comment:

```text
article_comments(comment_id FK, article_id FK)
video_comments(comment_id FK, video_id FK)
```

Ưu điểm là mỗi đường liên kết có FK rõ ràng. Nhược điểm là thêm bảng, truy vấn hợp nhất phức tạp và phải thiết kế quy tắc một Comment chỉ thuộc một target trên nhiều bảng liên kết.

### 16.5. Chỉ lưu `targetType` và `targetId` như field thường

Thay vì `@Any`, có thể định nghĩa:

```java
@Column(name = "target_type", nullable = false)
private String targetType;

@Column(name = "target_id", nullable = false)
private Long targetId;
```

Repository/service tự truy vấn theo type và ID. Cách này có cùng **giới hạn DB referential integrity** như `@Any`, nhưng rõ ràng hơn về việc ứng dụng tự kiểm soát resolution, caching và transaction.

Nó phù hợp khi target ở **một service khác**, không thể quản lý chung bằng Hibernate Session, hoặc khi ứng dụng chỉ cần lưu liên kết logic chứ hiếm khi điều hướng qua đối tượng.

**Không nên chọn `@Any` chỉ vì muốn có kiểu property là `Object`**; nếu association không cần ORM tự resolve, lưu type/ID có chủ đích có thể là thiết kế đơn giản hơn.

### 16.6. Bảng so sánh

| Mô hình | FK thật tới target? | Truy vấn đa hình | Chi phí khi thêm loại target |
|---|---|---|---|
| `@Any` | Không có một FK SQL đa bảng thông thường | Bị hạn chế; thường cần chia theo type | Thêm discriminator mapping, policy và query |
| `@Inheritance(JOINED)` với entity gốc | Có thể FK tới bảng gốc | Thuận lợi hơn qua association chuẩn | Thêm subtype và schema |
| `@Inheritance(SINGLE_TABLE)` | Có thể FK tới bảng chung | Thuận lợi qua entity gốc | Cột subtype trong bảng lớn, có thể nhiều null |
| Nhiều FK nullable | Có, từng FK theo bảng | Truy vấn theo từng association rõ ràng | Thêm cột, constraint và code |
| Bảng registry chung | Có tới registry | Cần thiết kế resolution | Thêm loại và đồng bộ registry/concrete |
| Bảng liên kết riêng | Có trên từng bảng liên kết | Cần union/tổng hợp | Thêm bảng và truy vấn |
| Lưu type/ID như thuộc tính thường | Không | Tự triển khai | Dễ thêm type nhưng nhiều trách nhiệm ở service |

Không mô hình nào thắng tuyệt đối; điều quan trọng là chọn theo **khả năng thay đổi của tập target, yêu cầu referential integrity, kiểu truy vấn và quyền sở hữu vòng đời dữ liệu**.

## 17. Lựa chọn theo tình huống thực tế

### Tình huống A: comment có thể gắn vào nhiều entity domain độc lập

Nếu chỉ có vài loại target nhưng chúng không chia sẻ một entity hierarchy hợp lý, `@Any` có thể giúp giữ một thuộc tính association ở tầng Java và tránh nhiều cột nullable.

Nên chấp nhận nó **chỉ khi** có chính sách rõ để validate, xóa, kiểm tra orphan và cập nhật discriminator. Nếu dữ liệu bình luận có giá trị quan trọng hoặc liên quan tiền bạc/pháp lý, hãy cân nhắc mạnh một thiết kế có FK thật.

### Tình huống B: Article và Video đều là Content

Nếu cả hai thực sự có chung lifecycle, quyền, trạng thái và nhiều truy vấn polymorphic, `Content` entity gốc với `JOINED` hoặc `SINGLE_TABLE` thường tự nhiên hơn. `Comment.target` khi ấy trở thành `@ManyToOne Content`, query và FK dễ quản lý hơn.

### Tình huống C: một service lưu reference tới dữ liệu thuộc service khác

`@Any` không biến reference cross-service thành một foreign key. Nếu target được lưu ở database/service khác, Hibernate trong service nguồn thường không quản lý được entity đích như association thông thường.

Ở trường hợp này, lưu `targetType` + `targetId` hoặc một resource identifier rõ ràng, cùng giao thức kiểm tra qua API/event, thường phản ánh kiến trúc tốt hơn.

### Tình huống D: dữ liệu cần audit dài hạn

Nếu bản ghi audit phải tồn tại kể cả khi target bị xóa, tham chiếu `@Any` đơn thuần không đủ: bản ghi audit có thể cần **snapshot thông tin target** tại thời điểm sự kiện, như loại, ID, tiêu đề, chủ thể thao tác, thời gian và ngữ cảnh. Đây là yêu cầu thiết kế audit riêng, không nên kỳ vọng một proxy tới entity hiện tại sẽ bảo tồn lịch sử.

## 18. Kiểm tra toàn vẹn bằng service: ví dụ có giới hạn rõ

Một service chỉ cho phép bình luận Article hoặc Video có thể được viết theo kiểu có whitelist:

```java
public enum TargetType {
    ARTICLE,
    VIDEO
}
```

```java
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CommentService {

    private final EntityManager em;

    public CommentService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public void add(
            TargetType type,
            Long targetId,
            String text) {

        if (targetId == null || text == null || text.isBlank()) {
            throw new IllegalArgumentException("Invalid comment input");
        }

        CommentTarget target = switch (type) {
            case ARTICLE -> em.find(Article.class, targetId);
            case VIDEO -> em.find(Video.class, targetId);
        };

        if (target == null) {
            throw new IllegalArgumentException("Target not found");
        }

        // Ở production cần kiểm tra quyền và trạng thái target.
        em.persist(new Comment(text, target));
    }
}
```

Ví dụ giả định Spring thực sự xử lý `@Transactional` và `EntityManager` được cấu hình với Hibernate provider. Không cần lấy tên class từ request để quyết định bảng. Hibernate tự viết discriminator đã khai báo dựa vào entity target.

**Giới hạn của service này:** nó kiểm tra target tại thời điểm truy vấn, nhưng nếu một transaction khác xóa target đồng thời thì có thể vẫn tạo orphan trừ khi có cơ chế đồng bộ thêm. Đó là lý do không nên mô tả validation tầng ứng dụng là “thay thế hoàn toàn FK”.

### Nếu cần bảo đảm mạnh hơn

Các lựa chọn kỹ thuật có thể gồm:

- Đưa mọi thao tác tạo Comment và xóa target qua các service cùng áp dụng locking protocol.
- Bảo vệ trên DB với trigger/constraint thiết kế riêng và kiểm tra isolation.
- Sử dụng một bảng gốc có FK thật thay cho `@Any`.
- Cấm xóa vật lý target trong nghiệp vụ và quản lý trạng thái soft delete nhất quán.

Không có một snippet `@Transactional` duy nhất có thể bảo đảm tính toàn vẹn khi các writer khác vẫn được phép xóa hàng đích mà không phối hợp.

## 19. Những lỗi vận hành thường gặp

### 19.1. Thêm mapping `@Any` rồi chờ Hibernate sinh FK

**Kỳ vọng sai:** Hibernate sẽ tạo FK từ `comments.target_id` tới Articles hoặc Videos dựa trên `target_type`.

**Thực tế:** một FK đa bảng dạng đó không nằm trong mô hình FK SQL thông thường. Phải chọn schema khác nếu cần ràng buộc cứng.

### 19.2. Chỉ lọc theo target ID

**Kỳ vọng sai:** `target_id = 12` đủ xác định đối tượng.

**Thực tế:** Article(12) và Video(12) là hai target khác nhau. Mọi lookup, delete, thống kê và cache key phải dùng cả discriminator.

### 19.3. Chỉ kiểm tra target khi tạo comment

**Kỳ vọng sai:** nếu target tồn tại tại thời điểm tạo thì dữ liệu sẽ mãi toàn vẹn.

**Thực tế:** target có thể bị xóa về sau hoặc đồng thời. Cần lifecycle policy và kiểm soát race condition.

### 19.4. Đổi discriminator mà không migration

**Kỳ vọng sai:** đổi tên class hoặc mã `@AnyDiscriminatorValue` sẽ tự cập nhật dữ liệu cũ.

**Thực tế:** các hàng vẫn giữ discriminator cũ. Mapping mới có thể không resolve được hoặc phân giải sai target.

### 19.5. Trộn nhiều kiểu identifier không tương thích

**Kỳ vọng sai:** một cột `target_id BIGINT` sẽ vừa lưu `Long` của Article vừa lưu `UUID` của Video mà không cần thiết kế thêm.

**Thực tế:** `@Any` cần key type/JDBC mapping tương thích. Nên chuẩn hóa key hoặc dùng mô hình khác.

### 19.6. Mong đợi fetch join và cascade giống `@ManyToOne`

**Kỳ vọng sai:** mọi khả năng truy vấn/lifecycle của quan hệ JPA chuẩn đều áp dụng nguyên vẹn cho `@Any`.

**Thực tế:** `@Any` là ánh xạ đặc thù Hibernate có các hạn chế về query path, target type và quan hệ ngược; cần kiểm tra Javadoc/User Guide của đúng version.

### 19.7. Tự động serialize target

**Kỳ vọng sai:** trả entity Comment cho JSON serializer luôn an toàn.

**Thực tế:** serializer có thể làm phát sinh N+1, load dữ liệu nhạy cảm hoặc lỗi nếu target không còn tồn tại. DTO và fetch strategy rõ ràng thường an toàn hơn.

### 19.8. Dùng soft delete như một khóa ngoại

**Kỳ vọng sai:** vì hiếm khi xóa vật lý nên referential integrity được bảo đảm.

**Thực tế:** soft delete là chính sách ứng dụng. Script admin, migration, purge job hoặc lỗi dữ liệu vẫn có thể tạo orphan; thêm nữa target “còn hàng” vẫn có thể bị vô hiệu về mặt nghiệp vụ.

## 20. Thiết kế thay đổi dữ liệu và migration

Khi chuyển từ quan hệ truyền thống `comments.article_id` sang `@Any`, không nên chỉ đổi entity field. Cần một migration phối hợp.

Ví dụ schema cũ:

```text
comments(id, body, article_id)
```

Schema mới:

```text
comments(id, body, target_type, target_id)
```

Các bước logic:

1. Thêm cột `target_type` và `target_id` tạm thời theo chiến lược cho phép triển khai dữ liệu an toàn.
2. Với các hàng cũ, ghi `target_type = 'ARTICLE'` và `target_id = article_id`.
3. Đối chiếu mọi `article_id` có target tồn tại; sửa dữ liệu lỗi trước khi bỏ FK cũ.
4. Cập nhật code để đọc/ghi mô hình mới, xét tương thích khi rolling deployment.
5. Chỉ đặt `NOT NULL`/`CHECK` và bỏ cột `article_id`/FK cũ sau khi quá trình chuyển đổi đạt điều kiện.
6. Xây chính sách xóa target và job orphan scan vì từ đây không còn FK cũ bảo vệ toàn bộ liên kết.
7. Cập nhật các query/report/index dùng `article_id`.
8. Xác định kế hoạch rollback trước khi bắt đầu ghi loại `VIDEO`, vì schema cũ không biểu diễn được giá trị đó bằng `article_id`.

Một migration kiểu này không chỉ là đổi tên cột; đó là **thay đổi mức bảo đảm toàn vẹn dữ liệu** của hệ thống.

## 21. Điều gì cần xác nhận trước khi đưa vào production?

Đối với dự án quyết định dùng `@Any`, cần xác định ít nhất:

### Mapping và phiên bản

- Hibernate version đang dùng có hỗ trợ đúng cú pháp `@Any`/`@AnyDiscriminator`/`@AnyKeyJavaClass` đã khai báo.
- Mỗi discriminator trỏ đến đúng entity class.
- Mọi target ID có kiểu Java/JDBC tương thích.
- Schema vật lý có cột discriminator/ID, constraint và index phù hợp.

### Toàn vẹn và vòng đời

- Comment được tạo chỉ khi target hợp lệ và người dùng có quyền.
- Khi Article/Video bị xóa, một chính sách rõ được thực hiện.
- Không có đường xóa/ghi từ job hoặc SQL trực tiếp bỏ qua policy mà không được theo dõi.
- Có cách phát hiện orphan và hướng xử lý theo loại dữ liệu.
- Đã phân tích transaction/concurrency nếu yêu cầu toàn vẹn mạnh.

### Truy vấn và hiệu năng

- Có index `(target_type, target_id)` cho lookup theo target.
- Query list không vô tình resolve hàng nghìn target khác loại riêng lẻ.
- DTO tránh serialization tùy ý của polymorphic target.
- Các truy vấn báo cáo đa loại được triển khai rõ, không giả định fetch join đa hình luôn hoạt động.

### Thay đổi và bảo mật

- Discriminator ổn định, có migration khi đổi tên/thêm loại.
- Rolling deployment không khiến code cũ đọc phải loại mới chưa được hỗ trợ.
- Quy tắc multi-tenant/organization được áp dụng cho cả Comment và target.
- Client không được trực tiếp biến giá trị type thành SQL table hoặc Java class tùy ý.

## 22. Bài tập suy luận kiến trúc

### Bài tập 1: Có đủ bảo toàn tham chiếu chưa?

Schema:

```sql
CREATE TABLE comments (
    id BIGINT PRIMARY KEY,
    target_type VARCHAR(16) NOT NULL
        CHECK (target_type IN ('ARTICLE', 'VIDEO')),
    target_id BIGINT NOT NULL
);
```

Câu hỏi: nếu `target_type = 'VIDEO'` và `target_id = 500` nhưng không có Video(500), database có chặn insert không?

**Phân tích:** không, chỉ có `CHECK` và `NOT NULL`. Chúng không xác minh hàng Video(500) tồn tại. Muốn FK cứng, cần mô hình liên kết khác hoặc cơ chế DB chuyên biệt hơn.

### Bài tập 2: Xóa nhầm comment

Hai bảng đều có hàng `id = 5`. Một job chạy:

```sql
DELETE FROM comments WHERE target_id = 5;
```

Kết quả là gì?

**Phân tích:** mọi comment trỏ tới bất kỳ loại target có ID 5 đều có thể bị xóa. Job thiếu discriminator. Câu điều kiện phải bao gồm `target_type` và, nếu có, tenant/scope.

### Bài tập 3: Chọn mô hình theo yêu cầu

Hệ thống chỉ có Article và Video; dữ liệu quan trọng, database bắt buộc chặn mọi liên kết mồ côi bằng FK thật, và ít khả năng thêm loại target mới.

**Hướng phù hợp:** cân nhắc **nhiều FK nullable với constraint đúng một target**, hoặc xây entity gốc chung nếu Article/Video thực sự thuộc cùng hierarchy. `@Any` không phải lựa chọn tự nhiên nhất khi FK cứng là yêu cầu bắt buộc.

### Bài tập 4: Có cùng tên Java interface là đủ không?

`Article implements CommentTarget` và `Video implements CommentTarget`, nhưng một bảng dùng ID `BIGINT` còn bảng kia dùng `UUID`.

**Phân tích:** interface chỉ giải quyết type chung ở Java. `@Any` vẫn cần lưu target key vào một ánh xạ cột nhất quán; cần xem lại kiểu ID, mapping hoặc mô hình DB.

## 23. Ghi nhớ

- **`@Any` là tính năng riêng của Hibernate ORM**, dùng cho một association có thể trỏ đến nhiều entity type không nhất thiết chung hệ kế thừa JPA.
- Cấu trúc thường dùng **discriminator + identifier**: ví dụ `('ARTICLE', 12)` hoặc `('VIDEO', 12)`.
- Với Hibernate 6, ánh xạ có thể dùng `@Any`, `@AnyDiscriminator`, `@AnyDiscriminatorValue`, `@AnyKeyJavaClass`, `@Column` và `@JoinColumn`.
- **Tất cả target ID phải tương thích với key mapping đã chọn**; interface Java chung không giải quyết khác biệt `Long`/`UUID` ở DB.
- Một cột `target_id` không thể có **FK SQL thông thường trỏ tới nhiều bảng theo discriminator**. `CHECK` discriminator chỉ kiểm tra tập type hợp lệ, không kiểm tra target tồn tại.
- Khi target bị xóa, Comment có thể trở thành **dangling reference**. Cần chính sách xóa, validation, kiểm soát đồng thời và phát hiện orphan.
- Mọi truy vấn, thống kê, cache key và thao tác xóa phải xác định target bằng **cả loại và ID**.
- `@Any` có hạn chế về khả năng query join, inverse mapping và hành vi fetch so với association JPA thông thường; nên chọn DTO và query theo type khi cần hiệu năng dự đoán được.
- `@ManyToAny` là biến thể cho collection đa hình nhưng cũng không tự tạo FK đa bảng.
- Nếu cần **referential integrity mạnh tại database**, hãy cân nhắc `@Inheritance` với bảng gốc chung, nhiều FK nullable hoặc các bảng liên kết có FK thật.
- Đổi discriminator hoặc thêm loại target là **thay đổi hợp đồng dữ liệu**, cần migration và kế hoạch tương thích phiên bản.

**Kết luận:** `@Any` giải quyết một nhu cầu mô hình hóa rất cụ thể: **tham chiếu đa hình tới nhiều entity type độc lập**. Nó mang lại sự linh hoạt ở tầng Hibernate bằng cách diễn giải cặp `(discriminator, identifier)`, nhưng **đánh đổi khả năng bảo vệ tham chiếu bằng foreign key quan hệ thông thường**. Quyết định sử dụng `@Any` chỉ hợp lý khi nhóm hiểu và chấp nhận đánh đổi này, đồng thời có thiết kế rõ cho tính đúng đắn dữ liệu, vòng đời target, truy vấn và vận hành lâu dài.
