# Ngữ nghĩa `save`, `findById`, `existsById` và `deleteById` trong Spring Data Redis

## 1. Bốn thao tác cốt lõi của Redis Repository

Spring Data Redis cung cấp các Repository giúp thao tác với đối tượng Java như những thực thể có **định danh (ID)**. Đối với một thực thể được đánh dấu `@RedisHash`, Repository có thể lưu đối tượng vào Redis dưới dạng Hash, lấy đối tượng theo ID, kiểm tra sự tồn tại và xóa đối tượng.

Bốn phương thức thường gặp nhất là:

~~~java
<S extends T> S save(S entity);
Optional<T> findById(ID id);
boolean existsById(ID id);
void deleteById(ID id);
~~~

Các chữ ký này xuất phát từ hợp đồng `CrudRepository<T, ID>` của Spring Data. Chúng biểu diễn bốn ý định khác nhau:

| Phương thức | Ý định | Kết quả | Điểm cần nhớ |
|---|---|---|---|
| `save(entity)` | Lưu trạng thái hiện tại của đối tượng theo ID | Trả về thực thể đã lưu | Có thể **tạo mới hoặc ghi đè** bản ghi cùng ID; không mặc định là cập nhật một vài field |
| `findById(id)` | Đọc và chuyển Redis Hash thành đối tượng Java | `Optional<T>` | Không tìm thấy thì `Optional.empty()`, không trả về `null` |
| `existsById(id)` | Kiểm tra ID có bản ghi hay không | `boolean` | Chỉ là kiểm tra tại thời điểm gọi; không khóa bản ghi |
| `deleteById(id)` | Xóa bản ghi có ID đã cho | `void` | Không có bản ghi thì thông thường bỏ qua; không trả về số bản ghi đã xóa |

Mục tiêu của bài học là hiểu **ngữ nghĩa** của từng thao tác, đặc biệt khi dữ liệu thay đổi, key hết hạn, nhiều tiến trình cập nhật đồng thời hoặc Redis Hash có thêm những field không được khai báo trong lớp Java.

## 2. Mô hình dữ liệu: ID, keyspace và Redis Hash

Giả sử có lớp Java `Article` với ID `a-101`. Khi sử dụng:

~~~java
@RedisHash("articles")
public class Article {
    @Id
    private String id;
    private String title;
}
~~~

Repository thường lưu thực thể vào một Redis key:

~~~text
Redis key: articles:a-101
Redis type: hash

id     -> a-101
title  -> Spring Data Redis
_class -> com.example.redis.model.Article
~~~

Trong đó:

- `articles` là **keyspace**, được khai báo trong `@RedisHash("articles")`.
- `a-101` là **ID** của thực thể.
- `articles:a-101` là **Redis key** của bản ghi.
- `id`, `title` và `_class` là những **field của Redis Hash**.

Dạng tổng quát:

~~~text
@RedisHash("<keyspace>") + @Id <id>
                 |
                 v
       Redis key "<keyspace>:<id>"
                 |
                 v
         Hash các field của entity
~~~

Tên key và cách mã hóa thực tế có thể phụ thuộc cấu hình mapping, serializer và ID. Ví dụ bài học sử dụng cấu hình Repository thông thường với ID kiểu `String`.

**Phân biệt:** `findById("a-101")` nhận **ID** `a-101`, không nhận cả chuỗi `articles:a-101`. Repository tự tạo Redis key theo keyspace của loại thực thể.

## 3. Ví dụ Spring Boot tối thiểu

### 3.1. Dependency và kết nối Redis

Trong dự án Spring Boot sử dụng Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

Hoặc với Gradle:

~~~gradle
implementation 'org.springframework.boot:spring-boot-starter-data-redis'
~~~

Để Spring Boot quản lý phiên bản tương thích, sử dụng BOM/parent hoặc plugin Spring Boot phù hợp với dự án.

Ví dụ cấu hình `application.yml`:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
~~~

Chạy Redis ở máy phát triển bằng Docker, nếu chưa có dịch vụ Redis:

~~~bash
docker run --rm --name redis-repository-demo -p 6379:6379 redis:7-alpine
~~~

### 3.2. Khai báo thực thể

Tệp `src/main/java/com/example/redis/model/Article.java`:

~~~java
package com.example.redis.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("articles")
public class Article {

    @Id
    private String id;

    private String title;

    @Indexed
    private String category;

    private int viewCount;

    public Article() {
    }

    public Article(String id, String title, String category, int viewCount) {
        this.id = id;
        this.title = title;
        this.category = category;
        this.viewCount = viewCount;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public int getViewCount() {
        return viewCount;
    }

    public void setViewCount(int viewCount) {
        this.viewCount = viewCount;
    }
}
~~~

`@Id` nằm trong gói `org.springframework.data.annotation`. `@Indexed` được thêm để minh họa việc Repository quản lý cả **secondary index** bên ngoài Redis Hash chính; không bắt buộc khi chỉ thao tác theo ID.

### 3.3. Khai báo Repository

Tệp `src/main/java/com/example/redis/repository/ArticleRepository.java`:

~~~java
package com.example.redis.repository;

import com.example.redis.model.Article;
import org.springframework.data.repository.CrudRepository;

public interface ArticleRepository extends CrudRepository<Article, String> {
}
~~~

Trong `CrudRepository<Article, String>`:

- `Article` là loại đối tượng lưu trữ.
- `String` là kiểu dữ liệu của trường `@Id`.
- Bốn method đang học được kế thừa, không cần viết phần thân SQL hay lệnh Redis.

Đặt lớp khởi động `@SpringBootApplication` ở package cha `com.example.redis` để Spring Boot có thể phát hiện entity và Repository theo cấu hình phổ biến. Khi Repository nằm ngoài vùng quét, cần cấu hình quét Repository tương ứng, chẳng hạn `@EnableRedisRepositories`.

## 4. `save(entity)`: lưu đối tượng theo ID

### 4.1. Tạo mới khi ID chưa có bản ghi

Giả sử Redis chưa có key `articles:a-101`:

~~~java
Article article = new Article(
    "a-101",
    "Học Redis Repository",
    "spring",
    10
);

Article saved = articleRepository.save(article);
System.out.println(saved.getId()); // a-101
~~~

Trạng thái logic:

~~~text
Trước save:
    articles:a-101          (không tồn tại)

Sau save:
    articles:a-101          (Redis Hash)
        id        = a-101
        title     = Học Redis Repository
        category  = spring
        viewCount = 10
        _class    = ...
~~~

Repository lấy ID, xác định keyspace, chuyển thuộc tính Java thành các field phù hợp và lưu dữ liệu. Nếu bật `@Indexed`, thao tác lưu cũng có thể cập nhật những key phụ phục vụ tra cứu theo `category`.

### 4.2. Cùng ID: ghi lại trạng thái, không tạo bản ghi thứ hai

~~~java
Article updated = new Article(
    "a-101",
    "Redis Repository nâng cao",
    "backend",
    25
);

articleRepository.save(updated);
~~~

Hai lần `save` dùng cùng ID `a-101` tương ứng **một Redis key** `articles:a-101`. Lần sau ghi trạng thái mới của thực thể đó; nó không tạo thêm `articles:a-102` hay thêm “một dòng” như một thao tác append.

| Field | Trước lần lưu thứ hai | Sau lần lưu thứ hai |
|---|---|---|
| `id` | `a-101` | `a-101` |
| `title` | Học Redis Repository | Redis Repository nâng cao |
| `category` | spring | backend |
| `viewCount` | 10 | 25 |

Điểm quan trọng: `save` là thao tác lưu **trạng thái thực thể**. Đối với cơ chế Object-to-Hash Mapping thông thường của Redis Repository, cập nhật có thể **xóa nội dung Hash cũ và ghi lại các field từ đối tượng mới**. Vì vậy, đừng hiểu `save` như một lệnh `HSET` chỉ sửa field khác biệt.

Ví dụ:

~~~text
Hash trước:
    id          = a-101
    title       = Học Redis
    viewCount   = 10
    debugFlag   = manually-added

Đối tượng Java được save:
    id          = a-101
    title       = Redis nâng cao
    viewCount   = 20
    (không có thuộc tính debugFlag)

Hash sau khi Repository save:
    id          = a-101
    title       = Redis nâng cao
    viewCount   = 20
    (debugFlag có thể bị xóa)
~~~

Nếu một ứng dụng khác quản lý `debugFlag`, nên lưu nó ở một key riêng hoặc đưa nó vào mô hình quản lý dữ liệu một cách rõ ràng. Trộn thao tác ghi field thủ công với `repository.save` trên cùng key dễ làm mất dữ liệu.

### 4.3. Khi ID chưa được gán

Với thực thể có `@Id String id`, Spring Data Redis có thể sinh một ID khi lưu đối tượng mà ID còn `null`:

~~~java
Article newArticle = new Article(
    null,
    "Bài viết chưa có ID",
    "java",
    0
);

Article saved = articleRepository.save(newArticle);
String generatedId = saved.getId();
~~~

ID mới trở thành phần định danh của Redis key. **Hãy sử dụng đối tượng mà `save` trả về** cho các thao tác tiếp theo: theo hợp đồng Spring Data, đối tượng trả về có thể được thay đổi trong quá trình lưu, nên không giả định mọi trường hợp đều phải là cùng một Java instance ban đầu.

Nếu muốn cập nhật bản ghi đã có, cần giữ và sử dụng **đúng ID**. Việc tạo lại một object mới với ID `null` rồi `save` thường dẫn tới một thực thể khác, không phải cập nhật bản ghi cũ.

### 4.4. Thay ID không đồng nghĩa đổi tên key

Giả sử đã lưu `a-101`, sau đó đặt ID của object thành `a-999` rồi gọi `save`:

~~~java
Article article = articleRepository.findById("a-101").orElseThrow();
article.setId("a-999");

articleRepository.save(article);
~~~

Lúc này ID mới trỏ tới key mới `articles:a-999`. Không nên giả định bản ghi cũ `articles:a-101` tự được xóa. Để chuyển định danh thực sự, cần thiết kế nghiệp vụ tạo key mới, xử lý các tham chiếu và xóa key cũ có chủ đích.

**Quy tắc thiết kế:** ID của thực thể nên ổn định trong vòng đời bản ghi.

### 4.5. `save` không phải cam kết chỉ thêm mới

`save` không có điều kiện kiểu “chỉ tạo khi ID chưa tồn tại” (`INSERT IF ABSENT`). Nếu hai lời gọi dùng cùng ID, lời gọi đến sau có thể ghi đè giá trị trước đó.

Nếu hệ thống cần **chặn trùng ID** hoặc bảo đảm chỉ tạo mới khi key chưa tồn tại, cần một cơ chế điều kiện/atomic phù hợp với Redis và cách Repository quản lý index, thay vì chỉ dùng `existsById` rồi `save`.

## 5. `findById(id)`: đọc Hash và dựng lại đối tượng

### 5.1. Khi có bản ghi

~~~java
Optional<Article> maybeArticle =
    articleRepository.findById("a-101");

maybeArticle.ifPresent(article ->
    System.out.println(article.getTitle())
);
~~~

Về mặt logic, Repository thực hiện:

~~~text
findById("a-101")
      |
      v
Chọn key "articles:a-101"
      |
      v
Đọc các field Redis Hash
      |
      v
Chuyển đổi Hash -> Article
      |
      v
Optional chứa Article
~~~

Nếu dữ liệu đã được lưu đúng cấu trúc, `getId()` trả về `a-101`, còn `getTitle()` nhận giá trị từ Hash.

`findById` dựa trên **ID/key của thực thể**. Không cần đánh dấu `@Indexed` trên `title` hay `category` để tìm bằng ID; chỉ mục phụ phục vụ những kiểu truy vấn khác.

### 5.2. Khi không có bản ghi

~~~java
Optional<Article> missing =
    articleRepository.findById("not-found");

System.out.println(missing.isEmpty()); // true
~~~

Kết quả là `Optional.empty()`. Vì thế, đoạn mã sau không phù hợp khi bản ghi có thể thiếu:

~~~java
Article article = articleRepository.findById("not-found").get();
// NoSuchElementException vì Optional đang rỗng.
~~~

Nên xử lý theo yêu cầu nghiệp vụ:

~~~java
Article article = articleRepository.findById("a-101")
    .orElseThrow(() ->
        new IllegalArgumentException("Article không tồn tại: a-101")
    );
~~~

Trong lớp API REST, trường hợp không có bản ghi thường được chuyển thành HTTP 404 qua exception handler phù hợp. Repository tự nó không quyết định mã HTTP.

### 5.3. Hash có thể tồn tại nhưng ánh xạ Java vẫn lỗi

`Optional.empty()` áp dụng cho trường hợp **không tìm thấy thực thể theo ID**. Nếu key có tồn tại nhưng nội dung bị sửa sai định dạng, metadata kiểu không phù hợp hoặc converter không thể dựng object, việc đọc có thể phát sinh lỗi chuyển đổi. Không nên hiểu rằng mọi lỗi Redis đều biến thành `Optional.empty()`.

Các nguyên nhân thường gặp:

- Key không chứa Hash như Repository mong đợi.
- Field chứa kiểu dữ liệu không thể chuyển sang thuộc tính Java.
- Thay đổi tên class, `@TypeAlias` hoặc cấu trúc lớp mà không xử lý dữ liệu cũ.
- Dùng một serializer/mapper khác để ghi trực tiếp vào key do Repository quản lý.

### 5.4. `findById` thường đọc nội dung cả thực thể

Vì mục tiêu là tái dựng một `Article` đầy đủ, thao tác này thường cần đọc các field của Hash. Nếu chỉ muốn biết key có tồn tại hay không, `existsById` diễn đạt ý định trực tiếp hơn; nếu cần nội dung của entity, chỉ cần `findById` mà không phải gọi thêm `existsById`.

## 6. `existsById(id)`: kiểm tra sự tồn tại tại một thời điểm

### 6.1. Kết quả `true` hoặc `false`

~~~java
boolean beforeSave = articleRepository.existsById("a-101");

articleRepository.save(
    new Article("a-101", "Bắt đầu với Redis", "spring", 1)
);

boolean afterSave = articleRepository.existsById("a-101");
~~~

Nếu không có tác nhân khác sửa dữ liệu và key không hết hạn giữa các lời gọi, `beforeSave` là `false` và `afterSave` là `true`.

Về mặt ý nghĩa, `existsById` hỏi Redis liệu bản ghi tại key của ID còn hiện diện hay không. Với Repository Redis thông thường, nó có thể dựa trên thao tác kiểm tra key tương đương `EXISTS`. Nó **không có nghĩa** là đọc và kiểm chứng toàn bộ nội dung `Article`.

### 6.2. `true` chưa bảo đảm đọc được đối tượng

Một key có thể hiện diện nhưng nội dung bên trong không đúng định dạng mà converter của Repository yêu cầu. Vì thế:

~~~java
if (articleRepository.existsById("a-101")) {
    // Chưa thể khẳng định dữ liệu luôn ánh xạ thành Article hợp lệ.
}
~~~

Muốn lấy thông tin, hãy đọc bằng `findById` và xử lý lỗi dữ liệu nếu cần.

### 6.3. Kiểm tra rồi thực hiện không phải thao tác nguyên tử

Đoạn sau dễ xuất hiện tình huống tranh chấp:

~~~java
if (!articleRepository.existsById("a-101")) {
    articleRepository.save(
        new Article("a-101", "Mới", "spring", 0)
    );
}
~~~

Hai tiến trình có thể chạy xen kẽ:

~~~text
Thời điểm   Tiến trình A               Tiến trình B
---------   -----------------------    -----------------------
t1          existsById -> false
t2                                     existsById -> false
t3          save(article A)
t4                                     save(article B)
t5          Bản ghi cuối phụ thuộc thứ tự ghi
~~~

Dù cả A và B đều nhìn thấy `false`, điều kiện “chỉ lưu nếu chưa tồn tại” **không được bảo đảm** bởi chuỗi hai method độc lập.

Tương tự, `existsById` trả về `true` không bảo đảm `findById` ngay sau đó luôn tìm được dữ liệu: key có thể bị xóa hoặc hết hạn trong khoảng giữa.

### 6.4. Chọn `existsById` hay `findById`?

**Chỉ cần trả lời có/không:**

~~~java
boolean exists = articleRepository.existsById(id);
~~~

**Cần đọc thuộc tính để xử lý:**

~~~java
Optional<Article> found = articleRepository.findById(id);

if (found.isPresent()) {
    Article article = found.get();
    // Sử dụng dữ liệu đã đọc.
}
~~~

Tránh:

~~~java
if (articleRepository.existsById(id)) {
    Article article = articleRepository.findById(id).orElseThrow();
    // Hai lần truy cập; vẫn có khả năng dữ liệu thay đổi giữa hai lần.
}
~~~

## 7. `deleteById(id)`: xóa bản ghi theo ID

### 7.1. Xóa một thực thể đã lưu

~~~java
articleRepository.save(
    new Article("a-101", "Sẽ bị xóa", "spring", 0)
);

articleRepository.deleteById("a-101");

boolean exists = articleRepository.existsById("a-101");
System.out.println(exists); // false nếu không có ghi mới xen vào
~~~

Về mặt logic, sau `deleteById`, key thực thể `articles:a-101` không còn. Redis Repository cũng xử lý thông tin quản lý liên quan, chẳng hạn index được duy trì bởi chính Repository theo cơ chế của phiên bản và cấu hình đang dùng.

Không nên đồng nhất `deleteById` với việc ứng dụng tự gọi duy nhất lệnh Redis `DEL`, bởi Repository có thể cần nhiều thao tác để bảo trì secondary index và dữ liệu quản lý thực thể.

### 7.2. Xóa ID không tồn tại

Theo hợp đồng của `CrudRepository`, nếu không có entity tương ứng, `deleteById` được bỏ qua:

~~~java
articleRepository.deleteById("not-found");
// Không cần một bản ghi có sẵn để lệnh xóa được chấp nhận.
~~~

Điều này khiến thao tác xóa **có tính lặp lại theo kết quả cuối**: gọi thêm lần nữa vẫn hướng đến trạng thái không còn bản ghi. Tuy nhiên, mỗi lời gọi vẫn có thể phát sinh thao tác với Redis và lỗi hạ tầng; “bỏ qua khi không tồn tại” không có nghĩa mọi lỗi đều bị nuốt.

### 7.3. Method trả về `void`, không báo có xóa thật hay không

~~~java
articleRepository.deleteById("a-101");
~~~

Không thể biết từ giá trị trả về liệu trước đó key có tồn tại hay không. Nếu nghiệp vụ cần phân biệt “đã tồn tại” và “chưa từng có”, phải xây dựng cơ chế phản hồi riêng. Đọc trước khi xóa là một lựa chọn đơn giản nhưng **không nguyên tử**, nên có thể không phù hợp khi cần kết quả chính xác tuyệt đối trong môi trường đồng thời.

### 7.4. Xóa theo ID không có nghĩa xóa cả đồ thị đối tượng

Nếu `Article` có tham chiếu (`@Reference`) tới một thực thể độc lập, `deleteById` không nên được hiểu như một lệnh cascade delete theo quy tắc JPA. Cần xác định rõ bản ghi nào được quản lý và xóa riêng những thực thể phụ khi nghiệp vụ yêu cầu.

## 8. Vòng đời đầy đủ: lưu, đọc, kiểm tra, xóa

Đặt đoạn sau trong lớp ứng dụng Spring Boot:

~~~java
package com.example.redis;

import com.example.redis.model.Article;
import com.example.redis.repository.ArticleRepository;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RedisRepositoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedisRepositoryApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(ArticleRepository repository) {
        return args -> {
            String id = "a-101";

            // 1. Dọn bản ghi của lần chạy trước nếu có.
            repository.deleteById(id);

            System.out.println(repository.existsById(id)); // false

            // 2. Lưu bản ghi mới.
            Article first = new Article(
                id, "Redis Repository cơ bản", "spring", 5
            );
            Article saved = repository.save(first);

            System.out.println(saved.getId());              // a-101
            System.out.println(repository.existsById(id)); // true

            // 3. Đọc lại.
            Article loaded = repository.findById(id)
                .orElseThrow();
            System.out.println(loaded.getTitle());

            // 4. Cập nhật bằng cách lưu trạng thái mới.
            loaded.setTitle("Redis Repository nâng cao");
            loaded.setViewCount(6);
            repository.save(loaded);

            Article afterUpdate = repository.findById(id)
                .orElseThrow();
            System.out.println(afterUpdate.getTitle());
            System.out.println(afterUpdate.getViewCount());

            // 5. Xóa và thử đọc lại.
            repository.deleteById(id);
            System.out.println(repository.existsById(id)); // false
            System.out.println(repository.findById(id).isEmpty()); // true

            // 6. Xóa lặp lại khi không tồn tại.
            repository.deleteById(id);
        };
    }
}
~~~

Dạng trạng thái kỳ vọng của key chính khi không có tiến trình khác can thiệp:

~~~text
Chưa có bản ghi
    |
    | save(Article{id="a-101", title="Redis Repository cơ bản"})
    v
articles:a-101 tồn tại
    |
    | findById("a-101")      -> Optional<Article>
    | existsById("a-101")    -> true
    |
    | save(Article{id="a-101", title="Redis Repository nâng cao"})
    v
articles:a-101 vẫn tồn tại, chứa trạng thái mới
    |
    | deleteById("a-101")
    v
articles:a-101 không tồn tại
    |
    | findById("a-101")      -> Optional.empty()
    | existsById("a-101")    -> false
    | deleteById("a-101")    -> bỏ qua ID không tồn tại
~~~

Lưu ý các comment kết quả trong ví dụ giả định Redis sẵn sàng, cấu hình đúng và không có thao tác ghi/xóa đồng thời từ phía khác.

## 9. Quan sát Redis trực tiếp để hiểu hành vi

Nếu muốn tạm dừng ví dụ sau bước lưu mà trước bước xóa, có thể dùng `redis-cli` quan sát key chính.

Sau `save`:

~~~redis
TYPE articles:a-101
HGETALL articles:a-101
HGET articles:a-101 title
EXISTS articles:a-101
~~~

Kết quả logic:

~~~text
TYPE       -> hash
HGETALL    -> gồm id, title, category, viewCount, _class...
HGET title -> giá trị của title
EXISTS     -> 1
~~~

Sau `deleteById`:

~~~redis
EXISTS articles:a-101
TYPE articles:a-101
HGETALL articles:a-101
~~~

Kết quả thông thường:

~~~text
EXISTS  -> 0
TYPE    -> none
HGETALL -> không có field
~~~

Bảng đối chiếu:

| Ý định | Repository | Redis CLI minh họa |
|---|---|---|
| Lưu object | `save(article)` | Có thể gồm các lệnh ghi Hash và thao tác metadata/index |
| Đọc object | `findById(id)` | Đọc Hash + chuyển đổi dữ liệu sang Java |
| Kiểm tra key | `existsById(id)` | `EXISTS articles:a-101` |
| Xóa object | `deleteById(id)` | Xóa key chính và xử lý thông tin quản lý liên quan |

**Các lệnh Redis CLI chỉ dùng để minh họa cơ chế.** Không nên dùng `HSET` hoặc `DEL` thủ công thay cho Repository trên cùng key nếu đang phụ thuộc vào secondary index, TTL, keyspace metadata hoặc bộ chuyển đổi dữ liệu của Spring Data Redis.

## 10. TTL: tồn tại bây giờ, biến mất sau đó

Một thực thể Redis có thể hết hạn tự động. Ví dụ một loại dữ liệu riêng:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "temporary-articles", timeToLive = 60)
public class TemporaryArticle {

    @Id
    private String id;

    private String title;

    // Constructor và accessor tương ứng.
}
~~~

`timeToLive = 60` đặt TTL 60 giây cho bản ghi được lưu theo cấu hình này. Vòng đời có thể là:

~~~text
t = 0s:
    save(entity)
    existsById(id) = true
    findById(id)   = Optional chứa entity

t > 60s (sau khi Redis xử lý hết hạn):
    existsById(id) = false
    findById(id)   = Optional.empty()
~~~

Khi cần, có thể xác nhận TTL bằng Redis CLI:

~~~redis
TTL temporary-articles:some-id
~~~

Một số điều cần biết:

- `existsById` không bảo đảm key còn tồn tại trong lần thao tác kế tiếp; TTL có thể hết hạn ngay sau lần kiểm tra.
- `findById` không phân biệt nguyên nhân key vắng mặt là do chưa từng tạo, đã xóa bằng Repository hay đã hết hạn.
- `save` trên entity có TTL thường áp dụng lại thời gian sống theo cấu hình hoặc thuộc tính TTL hiện tại của entity. Cần chú ý điều này khi dùng `save` như thao tác cập nhật.
- Xử lý sự kiện hết hạn và dọn các index phụ có cơ chế riêng, phụ thuộc cấu hình Redis keyspace notifications và Spring Data Redis. Không mặc nhiên xem index phụ là nguồn xác thực sự tồn tại của entity.

Ngoài TTL cố định trên `@RedisHash`, Spring Data Redis còn hỗ trợ thuộc tính `@TimeToLive` để quản lý TTL theo từng thực thể. Khi có yêu cầu lưu trữ ngắn hạn, hãy lựa chọn một chính sách nhất quán.

## 11. Secondary index có ảnh hưởng gì đến bốn thao tác?

Trong ví dụ, `Article.category` có `@Indexed`:

~~~java
@Indexed
private String category;
~~~

Đánh dấu này yêu cầu Repository duy trì cấu trúc chỉ mục để tìm theo category, ví dụ qua method truy vấn phát sinh từ tên:

~~~java
public interface ArticleRepository
        extends CrudRepository<Article, String> {

    Iterable<Article> findByCategory(String category);
}
~~~

Khi gọi:

~~~java
repository.save(new Article("a-101", "A", "spring", 1));
repository.save(new Article("a-101", "A", "backend", 1));
repository.deleteById("a-101");
~~~

Repository cần quản lý mối liên hệ giữa ID và các giá trị chỉ mục khi lưu lại hoặc xóa thực thể. Vì thế, tác động của `save` và `deleteById` có thể vượt ra ngoài Hash chính `articles:a-101`.

Ngược lại:

- `findById` tìm theo key của ID, không cần truy vấn chỉ mục category.
- `existsById` kiểm tra sự tồn tại theo ID, không có nghĩa kiểm tra xem mọi secondary index đã đồng bộ.
- Nếu tự `HSET` đổi category trong Hash, bạn có thể làm chỉ mục bị sai so với dữ liệu thực tế.
- `@Indexed` không phải ràng buộc unique. Hai `Article` khác ID có thể có cùng category.

Trong một ứng dụng thực, chỉ nên lập chỉ mục những thuộc tính thật sự được truy vấn và nên đưa các thay đổi thực thể qua cơ chế có thể bảo trì chỉ mục đúng cách.

## 12. Cập nhật một field: vì sao `save` đôi khi không phù hợp?

Giả sử chỉ muốn tăng `viewCount` từ 10 lên 11. Cách dễ nghĩ tới:

~~~java
Article article = repository.findById("a-101").orElseThrow();
article.setViewCount(article.getViewCount() + 1);
repository.save(article);
~~~

Cách này dễ hiểu và phù hợp trong tình huống không có cập nhật cạnh tranh nghiêm ngặt. Nhưng hai tiến trình có thể cùng đọc giá trị 10, cùng tính 11 rồi cùng `save`; kết quả sau cùng là 11 thay vì 12. Đây là một dạng **lost update**.

~~~text
A đọc viewCount = 10
B đọc viewCount = 10
A đặt 11 và save
B đặt 11 và save
Kết quả: 11 (mất một lượt tăng)
~~~

Đối với bộ đếm có tính đồng thời cao, nên xem xét cách cập nhật nguyên tử bằng Redis phù hợp với định dạng Hash, chẳng hạn `HINCRBY`, thay vì chuỗi đọc → tăng → `save`. Ví dụ minh họa với một key do ứng dụng quản lý:

~~~redis
HINCRBY article-counters:a-101 views 1
~~~

Dùng key riêng `article-counters:a-101` tránh can thiệp vào Hash thực thể do Repository sở hữu. Nếu bộ đếm bắt buộc nằm trong cùng entity, cần thiết kế rõ cơ chế đồng bộ giữa bộ đếm nguyên tử và mọi thao tác `save`.

Spring Data Redis còn có `PartialUpdate` để sửa có chọn lọc một số thuộc tính trên key do Repository quản lý:

~~~java
import org.springframework.data.redis.core.PartialUpdate;
import org.springframework.data.redis.core.RedisKeyValueTemplate;

public void rename(RedisKeyValueTemplate template) {
    PartialUpdate<Article> update =
        new PartialUpdate<Article>("a-101", Article.class)
            .set("title", "Tiêu đề mới");

    template.update(update);
}
~~~

`PartialUpdate` giúp tránh lưu lại toàn bộ đối tượng cho trường hợp phù hợp, nhưng **không tự biến** các chuỗi đọc–tính toán–ghi thành thao tác nguyên tử, và hành vi đối với custom converters, collection hoặc index cần được xem xét khi áp dụng.

## 13. Khi nào cần giao dịch, khóa hoặc kiểm tra phiên bản?

Bốn method kế thừa từ `CrudRepository` diễn đạt các thao tác CRUD, nhưng một chuỗi nhiều lời gọi không mặc nhiên là một transaction nguyên tử.

Ví dụ điều kiện nghiệp vụ:

> Chỉ cho phép xóa bài viết nếu trạng thái hiện tại là `DRAFT`.

Đoạn mã:

~~~java
Article article = repository.findById(id).orElseThrow();

if ("DRAFT".equals(article.getStatus())) {
    repository.deleteById(id);
}
~~~

chỉ minh họa ý tưởng khi entity có thuộc tính `status`; `Article` trong ví dụ đầu chưa khai báo thuộc tính này. Vấn đề là một tiến trình khác có thể đổi trạng thái thành `PUBLISHED` giữa bước kiểm tra và bước xóa.

Muốn bảo đảm ràng buộc trong môi trường cạnh tranh, cần lựa chọn cách đồng bộ phù hợp với miền dữ liệu và thao tác Redis: cập nhật có điều kiện, cơ chế kiểm soát phiên bản mà phiên bản thư viện hỗ trợ, `WATCH`/`MULTI`, Lua script hoặc một thiết kế ghi dữ liệu khác. Phải đánh giá cả việc cập nhật secondary index và TTL nếu đi ngoài Repository.

Một Redis command riêng lẻ có thể được thực thi nguyên tử, nhưng **nhiều method Repository gọi nối tiếp** không tự thành một thao tác nguyên tử với người dùng khác.

## 14. Lỗi đầu vào và lỗi hạ tầng

### 14.1. Truyền `null`

Các hợp đồng Spring Data Repository yêu cầu tham số không được `null` ở các vị trí như:

~~~java
repository.save(null);
repository.findById(null);
repository.existsById(null);
repository.deleteById(null);
~~~

Những lời gọi này vi phạm hợp đồng phương thức và thường gây `IllegalArgumentException`. Không dùng `null` để biểu thị “không tìm thấy”. Với `findById`, hãy dùng `Optional.empty()`.

### 14.2. Redis không kết nối được

Lỗi mạng, Redis ngừng hoạt động, timeout hoặc lỗi xác thực là **lỗi vận hành**, không phải “entity không tồn tại”. Không nên chuyển tất cả exception của `findById` thành `Optional.empty()` hay của `existsById` thành `false`, vì điều đó sẽ che giấu sự cố thật.

### 14.3. Keyspace hoặc ID khác mong đợi

~~~java
repository.findById("articles:a-101"); // Sai ý định nếu ID thực là "a-101".
repository.findById("a-101");          // Đúng ID.
~~~

Nếu Redis CLI thấy `articles:a-101` nhưng Repository không tìm được, cần kiểm tra loại entity, keyspace, ID, cấu hình serializer và Redis database đang kết nối.

### 14.4. Dùng `save` như partial update

Nếu một object chỉ được gán `id` và `title`, các thuộc tính Java khác có thể nhận giá trị mặc định (`null`, `0`...) khi lưu lại. Lưu object ấy không đồng nghĩa giữ nguyên mọi field cũ. Khi cần đổi một số field, đọc đầy đủ trước khi cập nhật hoặc dùng cơ chế cập nhật có chọn lọc phù hợp.

### 14.5. Dùng `existsById` làm bảo đảm tính duy nhất

Kiểm tra `false` rồi `save` không ngăn tiến trình khác tạo cùng ID. Muốn ràng buộc duy nhất phải có cơ chế nguyên tử có điều kiện, thay vì chỉ dựa vào cặp method này.

### 14.6. Tự xóa key Redis thay vì `deleteById`

Nếu Repository quản lý index phụ, dùng trực tiếp `DEL articles:a-101` có thể khiến index không được xử lý như khi xóa qua Repository. Trừ khi đã thiết kế riêng cơ chế dọn metadata, hãy để Repository thực hiện xóa các entity do nó quản lý.

## 15. Tình huống nghiệp vụ và cách chọn phương thức

| Tình huống | Cách tiếp cận phù hợp | Lý do |
|---|---|---|
| Tạo một bài viết có ID mới | `save(newArticle)` | Ghi trạng thái thực thể vào Redis |
| Cập nhật đầy đủ thông tin bài viết đã biết ID | `save(article)` | Lưu trạng thái mới của cùng key |
| Hiển thị chi tiết bài viết | `findById(id)` | Cần các thuộc tính, xử lý `Optional.empty()` |
| Chỉ hiển thị thông báo “có/không có bài viết” | `existsById(id)` | Không cần tạo lại toàn bộ entity |
| Xóa bài viết theo ID | `deleteById(id)` | Xóa bằng cơ chế Repository |
| Chỉ thêm bài viết nếu key chưa tồn tại, kể cả có truy cập đồng thời | Cơ chế ghi nguyên tử có điều kiện | `existsById` + `save` có race condition |
| Tăng lượt xem với lưu lượng truy cập cao | Bộ đếm Redis nguyên tử thiết kế riêng | Chuỗi `findById` → tăng → `save` có thể mất lượt |
| Sửa riêng một thuộc tính | `PartialUpdate` hoặc chiến lược cập nhật field phù hợp | Hạn chế nguy cơ ghi lại cả Hash |
| Phải biết chắc “đã xóa được bản ghi tồn tại trước đó” | Thiết kế thao tác xóa có phản hồi nguyên tử riêng | `deleteById` trả về `void` |

## 16. Bài thực hành theo trạng thái

### Bài 1: Quan sát tạo và cập nhật

Viết chương trình:

~~~java
Article first = new Article("lab-1", "Tiêu đề A", "redis", 1);
repository.save(first);

Article second = new Article("lab-1", "Tiêu đề B", "redis", 2);
repository.save(second);

Article result = repository.findById("lab-1").orElseThrow();
System.out.println(result.getTitle());
~~~

Dự đoán giá trị in ra, số lượng Redis key chính và điều gì xảy ra với field chỉ có trong bản ghi Hash cũ.

### Bài 2: Xử lý `Optional` đúng cách

~~~java
String title = repository.findById("unknown")
    .map(Article::getTitle)
    .orElse("(không có bài viết)");

System.out.println(title);
~~~

Giải thích vì sao không cần gọi `existsById("unknown")` trước đoạn này.

### Bài 3: Kiểm tra trước và sau xóa

~~~java
String id = "lab-2";

repository.save(new Article(id, "Để xóa", "java", 0));
System.out.println(repository.existsById(id));

repository.deleteById(id);
System.out.println(repository.existsById(id));

repository.deleteById(id);
System.out.println(repository.findById(id).isPresent());
~~~

Dự đoán kết quả trong điều kiện không có truy cập đồng thời hoặc TTL can thiệp. Vì sao lần `deleteById` thứ hai không phải một lỗi “bản ghi không tồn tại”?

### Bài 4: Đọc → sửa → lưu đồng thời

Có hai luồng cùng lấy `Article{viewCount=100}` rồi tăng thêm 1 và `save`. Hãy mô tả các thứ tự chạy có thể khiến kết quả là 101 thay vì 102. Đề xuất một cách thiết kế bộ đếm Redis tránh mất lượt tăng.

### Bài 5: TTL

Tạo một entity với `@RedisHash(timeToLive = 10)`. Lưu bằng `save`, kiểm tra `existsById` và `findById` trước/sau khi Redis hết hạn key. Giải thích vì sao việc đọc về `Optional.empty()` không cho biết entity đã bị xóa chủ động hay tự hết hạn.

## 17. Ghi nhớ

- `save` lưu **trạng thái thực thể theo ID**; khi ID đã có, bản ghi cùng key được cập nhật và có thể mất các field ngoài mô hình mapping. Luôn xem đối tượng trả về là kết quả của thao tác lưu.
- `findById` trả về **`Optional<T>`**, nên xử lý rõ trường hợp không tìm thấy. Việc đọc dữ liệu Hash sai định dạng vẫn có thể gây lỗi.
- `existsById` trả về **`boolean`** tại thời điểm kiểm tra; không khóa dữ liệu và không bảo đảm điều kiện cho `save`/`deleteById` ở bước tiếp theo.
- `deleteById` xóa theo ID, trả về **`void`**; ID không tồn tại được bỏ qua theo hợp đồng Repository.
- Với `@RedisHash`, ID được kết hợp với keyspace để xác định Redis key. Repository còn có thể quản lý secondary index và TTL, nên không thể xem mọi method là đúng một lệnh Redis độc lập.
- Những nghiệp vụ cần so sánh rồi ghi, tăng bộ đếm chính xác hay chống ghi đè đồng thời cần cơ chế đồng bộ thích hợp ngoài việc gọi bốn phương thức CRUD nối tiếp.

### Tài liệu đọc thêm

- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Redis Repositories: Usage](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/usage.html)
- [Spring Data Redis — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html)
- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Commons — Core Concepts / Repository interfaces](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html)
