# So sánh tham chiếu ứng dụng, DBRef, DocumentReference và $lookup

## 1. Bài toán liên kết document trong MongoDB

Trong chương **Tham chiếu tài liệu** của **Spring Data MongoDB**, ta cần quyết định cách biểu diễn và truy xuất quan hệ giữa hai document nằm ở các collection khác nhau. Ví dụ một cuốn sách thuộc về một tác giả, với document trong collection `authors`:

~~~json
{
  "_id": "author-7",
  "name": "Nguyễn An",
  "country": "VN"
}
~~~

Và document trong collection `books`:

~~~json
{
  "_id": "book-42",
  "title": "MongoDB thực hành",
  "status": "PUBLISHED",
  "authorId": "author-7"
}
~~~

Nếu trang danh sách sách chỉ cần tên tác giả, ứng dụng có nhiều lựa chọn:

1. **Tham chiếu do ứng dụng quản lý** (*manual/application reference*): lưu `authorId`, sau đó chủ động truy vấn collection `authors`.
2. **`@DBRef`**: lưu một cấu trúc DBRef đặc biệt (có `$ref` và `$id`), để Spring Data hỗ trợ phân giải khi đọc đối tượng.
3. **`@DocumentReference`**: mặc định lưu giá trị ID của document đích dưới dạng tham chiếu ngắn gọn và để Spring Data phân giải theo thông tin mapping.
4. **`$lookup`**: thực thi phép kết hợp collection trong **aggregation pipeline** trên MongoDB server khi cần kết quả chứa dữ liệu từ cả hai collection.

Điểm cốt lõi: **ba cách đầu là cách lưu hoặc biểu diễn tham chiếu trong mô hình dữ liệu; `$lookup` là thao tác truy vấn**. Một hệ thống dùng `authorId` hoàn toàn có thể kết hợp dữ liệu bằng `$lookup` mà không cần dùng `@DBRef` hay `@DocumentReference`.

Bài viết tập trung vào Java 17+, Spring Boot 3.x và Spring Data MongoDB 4.x. Các API liên quan tới lazy loading, mapping và cấu hình chi tiết có thể thay đổi giữa các phiên bản; cần xác minh trên dependency thực tế khi đưa vào dự án.

## 2. Bảng so sánh bốn lựa chọn

| Tiêu chí | Tham chiếu ứng dụng | `@DBRef` | `@DocumentReference` | `$lookup` |
|---|---|---|---|---|
| Cách lưu điển hình | `authorId: "author-7"` | `author: { "$ref": "authors", "$id": "author-7" }` | `author: "author-7"` theo mặc định | Không quy định cách lưu |
| Ai thực hiện kết nối dữ liệu? | Code service/repository | Cơ chế reference resolver của Spring Data | Cơ chế reference resolver của Spring Data | MongoDB server qua aggregation |
| Kết quả ở Java | ID và đối tượng được truy vấn riêng, tự ghép | Property được mapping thành entity đích | Property được mapping thành entity đích | Kết quả pipeline theo projection/DTO |
| Kiểm soát thời điểm tải | Tường minh | Có thể eager/lazy | Có thể eager/lazy | Thời điểm chạy aggregation |
| Khả năng batch | Chủ động gom ID và truy vấn `$in` | Phụ thuộc cách resolver xử lý và hình dạng reference | Phụ thuộc cách resolver xử lý và cấu hình mapping | Server xử lý join trong pipeline |
| Tùy biến điều kiện liên kết | Do ứng dụng quy định | Theo DBRef được lưu | Hỗ trợ `lookup` tùy chỉnh trong annotation | Linh hoạt với `localField`/`foreignField` hoặc pipeline |
| Khi ưu tiên | Mặc định an toàn, rõ số truy vấn | Tương thích dữ liệu DBRef hiện hữu | Muốn property dạng object với cách lưu reference đơn giản | Tìm kiếm/báo cáo cần kết hợp dữ liệu tại server |
| Rủi ro chính | Lặp code truy vấn, quên batch | Tải ngầm, N+1, cấu trúc DBRef | Tải ngầm, N+1, phụ thuộc cơ chế phân giải | Pipeline khó, chi phí join/sort/memory |

Không có lựa chọn luôn nhanh hoặc luôn tốt hơn. Số round trip, index, kích thước dữ liệu, tần suất đọc, mô hình nhất quán và khả năng kiểm thử quan trọng hơn tên annotation.

### Quy tắc ra quyết định

~~~mermaid
flowchart TD
    A["Cần liên kết dữ liệu giữa các collection"] --> B{"Chỉ cần giữ ID, tự kiểm soát tải dữ liệu?"}
    B -->|"Có"| C["Tham chiếu ứng dụng + batch theo nhu cầu"]
    B -->|"Không"| D{"Trả danh sách hoặc báo cáo kết hợp nhiều collection?"}
    D -->|"Có"| E["Aggregation $lookup + projection + index"]
    D -->|"Không"| F{"Muốn property Java là object được Spring Data phân giải?"}
    F -->|"Có"| G{"Schema hiện có đã là DBRef?"}
    G -->|"Có"| H["Dùng @DBRef, đánh giá migration khi cần"]
    G -->|"Không"| I["Cân nhắc @DocumentReference"]
    F -->|"Không"| C
    C --> J["Đo query count, latency và kiểm tra dữ liệu thiếu"]
    E --> J
    H --> J
    I --> J
~~~

## 3. Mô hình nguồn dùng chung

Các ví dụ sau định nghĩa tác giả và sách ở package `com.example.library`. Trong ví dụ, ID được lưu dưới dạng **BSON String** để dễ đối chiếu giữa các phương án; ứng dụng thật có thể chọn `ObjectId` hoặc kiểu khác nếu dùng nhất quán.

**Author.java**

~~~java
package com.example.library;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "authors")
public class Author {
    @MongoId(FieldType.STRING)
    private String id;
    private String name;
    private String country;

    public Author() {}

    public Author(String id, String name, String country) {
        this.id = id;
        this.name = name;
        this.country = country;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getCountry() { return country; }
    public void setCountry(String country) { this.country = country; }
}
~~~

**Book.java** — mô hình lưu tham chiếu ứng dụng:

~~~java
package com.example.library;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "books")
public class Book {
    @MongoId(FieldType.STRING)
    private String id;
    private String title;
    private String status;
    private String authorId;

    public Book() {}

    public Book(String id, String title, String status, String authorId) {
        this.id = id;
        this.title = title;
        this.status = status;
        this.authorId = authorId;
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getStatus() { return status; }
    public String getAuthorId() { return authorId; }
}
~~~

Trong các ví dụ, có thể dùng chung collection `authors` cho các kiểu quan hệ và dùng collection riêng `books`, `books_dbref`, `books_docref` để quan sát sự khác biệt của BSON. Việc này chỉ phục vụ học tập, không có nghĩa hệ thống thực tế cần ba collection chứa cùng sách.

## 4. Tham chiếu ứng dụng: lưu khóa và chủ động truy vấn

Với mô hình `Book`, MongoDB chỉ lưu `authorId` như một field thông thường:

~~~json
{
  "_id": "book-42",
  "title": "MongoDB thực hành",
  "status": "PUBLISHED",
  "authorId": "author-7"
}
~~~

Spring Data không tự động tải tác giả khi truy vấn `Book` vì không có annotation tham chiếu. Đây là đặc điểm hữu ích: **một lần đọc sách không bất ngờ kéo theo nhiều lần đọc tác giả**.

Định nghĩa hai repository:

~~~java
package com.example.library;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookRepository extends MongoRepository<Book, String> {
    List<Book> findByStatus(String status);
}
~~~

~~~java
package com.example.library;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface AuthorRepository extends MongoRepository<Author, String> {
}
~~~

### 4.1. Cách đơn giản: tải từng đối tượng được tham chiếu

~~~java
Book book = bookRepository.findById("book-42").orElseThrow();
Author author = authorRepository.findById(book.getAuthorId())
        .orElseThrow();
~~~

Đây là hai thao tác đọc. Cách này phù hợp một màn hình chi tiết chỉ có một sách. Nếu danh sách chứa 100 sách và code thực hiện `findById` cho từng sách, số lần truy vấn có thể tăng tới **1 + N** (*N+1 query problem*), gây độ trễ đáng kể dù mỗi truy vấn đều có index.

### 4.2. Tối ưu danh sách: gom ID rồi batch

Thay vì tải từng tác giả, lấy danh sách sách trước, gom các `authorId` duy nhất, rồi lấy tác giả một lượt:

~~~java
package com.example.library;

public record BookView(String id, String title, String authorName) {
}
~~~

~~~java
package com.example.library;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;

@Service
public class BookViewService {
    private final BookRepository books;
    private final AuthorRepository authors;

    public BookViewService(BookRepository books, AuthorRepository authors) {
        this.books = books;
        this.authors = authors;
    }

    public List<BookView> published() {
        List<Book> results = books.findByStatus("PUBLISHED");

        Set<String> authorIds = results.stream()
                .map(Book::getAuthorId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Map<String, Author> byId = new HashMap<>();
        authors.findAllById(authorIds).forEach(
                author -> byId.put(author.getId(), author));

        return results.stream()
                .map(book -> {
                    Author author = byId.get(book.getAuthorId());
                    return new BookView(
                            book.getId(),
                            book.getTitle(),
                            author == null ? null : author.getName());
                })
                .toList();
    }
}
~~~

Thường có thể đọc tác giả theo điều kiện `_id in (...)` thay vì một truy vấn cho mỗi sách. Với tập ID rất lớn, cần **phân trang và chia batch** có giới hạn, không đưa toàn bộ danh mục vào một `$in` khổng lồ. Đoạn code trên cố ý thể hiện chính sách khi không tìm thấy tác giả: trả `authorName = null`. Trong ứng dụng thật, có thể muốn trả lỗi dữ liệu, dùng snapshot tên tác giả hoặc ẩn sách, tùy yêu cầu nghiệp vụ.

**Ưu điểm:** BSON đơn giản, dễ dùng với driver/aggregation, dễ kiểm soát truy vấn, có thể cache hoặc batch theo trường hợp sử dụng. **Nhược điểm:** service phải tự tổ chức tải liên kết và xử lý reference không tồn tại.

## 5. @DBRef: tham chiếu theo định dạng DBRef

MongoDB có quy ước biểu diễn DBRef bằng document chứa các trường như `$ref` (tên collection), `$id` (ID document đích), đôi khi có `$db` (tên database). Spring Data MongoDB hỗ trợ ánh xạ bằng `@DBRef`.

**BookDbRef.java**:

~~~java
package com.example.library;

import org.springframework.data.mongodb.core.mapping.DBRef;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "books_dbref")
public class BookDbRef {
    @MongoId(FieldType.STRING)
    private String id;
    private String title;
    @DBRef(lazy = true)
    private Author author;

    public BookDbRef() {}

    public BookDbRef(String id, String title, Author author) {
        this.id = id;
        this.title = title;
        this.author = author;
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
    public Author getAuthor() { return author; }
}
~~~

Với tác giả có `_id = "author-7"`, hình dạng BSON lưu tham chiếu có thể là:

~~~json
{
  "_id": "book-dbref-42",
  "title": "MongoDB thực hành",
  "author": {
    "$ref": "authors",
    "$id": "author-7"
  }
}
~~~

`@DBRef` lưu **thông tin tham chiếu**, không nhúng toàn bộ document `Author`. Khi cần materialize property `author`, Spring Data sử dụng thông tin DBRef để tìm document đích.

### 5.1. Eager và lazy

- `@DBRef` **không khai báo `lazy = true`**: khi mapping tài liệu, Spring Data thường phân giải tham chiếu ngay (*eager*).
- `@DBRef(lazy = true)`: framework cố gắng trì hoãn truy vấn document đích cho tới khi proxy được truy cập.

Ví dụ:

~~~java
BookDbRef book = mongoTemplate.findById(
        "book-dbref-42", BookDbRef.class);

// Truy cập author có thể kích hoạt việc phân giải tham chiếu.
String authorName = book.getAuthor().getName();
~~~

Trên một số cấu hình Java/module, việc tạo proxy lazy có thể gặp hạn chế truy cập hoặc bất tương thích kiểu; cần kiểm thử trên JDK và Spring Data version thực tế. Gọi `toString()`, debug object hoặc serialize sang JSON đôi khi cũng khiến proxy bị truy cập và phát sinh thêm query.

**Không hiểu lazy là miễn phí.** Nếu lặp 100 sách rồi truy cập `getAuthor().getName()`, hệ thống vẫn có thể thực hiện nhiều lần truy vấn bổ sung. Một số đường phân giải collection reference có khả năng gom truy vấn trong tình huống phù hợp, nhưng không nên giả định luôn batch được.

### 5.2. DBRef không tự quản lý quan hệ như foreign key

`@DBRef` không làm MongoDB tạo foreign key constraint. Nếu tác giả bị xóa, DBRef vẫn có thể còn trong sách; tùy mapping và cách truy cập, tài liệu đích có thể không phân giải được.

Spring Data MongoDB cũng **không mặc định cascade-save** đối tượng được tham chiếu qua `@DBRef`. Cần lưu `Author` trước hoặc theo quy trình riêng. Tương tự, xóa `BookDbRef` không nên mặc định xóa `Author` đang được nhiều sách dùng chung.

DBRef hữu ích khi dự án **đã lưu theo chuẩn DBRef**, cần tương thích collection cũ hoặc tính chất định dạng này thực sự là yêu cầu tích hợp. Khi không có ràng buộc như vậy, tham chiếu ID đơn giản thường dễ quản lý hơn.

## 6. @DocumentReference: tham chiếu do Spring Data mô tả

`@DocumentReference` cho phép ánh xạ property như một đối tượng liên quan nhưng **không bắt buộc lưu cấu trúc DBRef**. Theo hành vi mặc định, Spring Data MongoDB có thể lưu **ID của document đích** và dùng ID đó để truy vấn khi đọc.

**BookDocRef.java**:

~~~java
package com.example.library;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "books_docref")
public class BookDocRef {
    @MongoId(FieldType.STRING)
    private String id;
    private String title;
    @DocumentReference(lazy = true)
    private Author author;

    public BookDocRef() {}

    public BookDocRef(String id, String title, Author author) {
        this.id = id;
        this.title = title;
        this.author = author;
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
    public Author getAuthor() { return author; }
}
~~~

Hình dạng BSON minh họa với reference mặc định:

~~~json
{
  "_id": "book-docref-42",
  "title": "MongoDB thực hành",
  "author": "author-7"
}
~~~

So với `@DBRef`, cách lưu này ngắn gọn, không buộc lưu `$ref` và `$id` cùng với mỗi reference. Nó vẫn cần **truy vấn bổ sung khi phân giải property**; `@DocumentReference` không tự biến thao tác đọc sách thành một `$lookup` ở server.

### 6.1. Tùy biến lookup và writing

Với `@DocumentReference`, mapping có thể cấu hình biểu thức `lookup` để tìm document đích theo khóa khác `_id`, chẳng hạn một mã tự nhiên **được bảo đảm duy nhất**. Hãy chú ý rằng việc tùy biến `lookup` chỉ nói Spring Data **tìm** bằng điều kiện nào; **giá trị được lưu** còn phụ thuộc quy tắc writing/reference-value của mapping.

Chẳng hạn, khi muốn lưu mã tác giả `externalCode` thay cho ID, cần thiết kế rõ cách xuất reference lúc ghi và cách `lookup` giải mã nó lúc đọc. Không nên đổi annotation trên dữ liệu đang lưu bằng ID rồi kỳ vọng tất cả giá trị cũ tự chuyển thành mã mới.

Các thuộc tính như `lazy` có cùng vấn đề với DBRef: một property trông như object Java nhưng truy cập getter có thể kích hoạt truy vấn I/O. Đừng để việc serialize hàng loạt entity âm thầm kéo theo nhiều lần đọc. Trong REST API, nên dùng DTO/projection rõ ràng hơn là trả thẳng entity có lazy reference.

### 6.2. Một collection nhiều reference

Trong trường hợp một bài viết có nhiều tag:

~~~java
@DocumentReference(lazy = true)
private java.util.List<Tag> tags;
~~~

Đoạn trên chỉ minh họa **property đặt trong một entity**; `Tag` phải là kiểu được mapping phù hợp. Khi dùng reference mặc định, tài liệu nguồn có thể lưu danh sách ID thay vì nhúng mỗi Tag.

Hãy kiểm tra cách Spring Data giải quyết collection reference, xử lý tag không tồn tại và thứ tự kết quả. **Thứ tự trong danh sách Java không nên được giả định luôn giữ nguyên** khi cơ chế phân giải tham chiếu thay đổi hoặc khi chạy truy vấn nhiều đối tượng nếu không có bảo đảm cụ thể. Với thứ tự hiển thị quan trọng, cần mô hình hóa vị trí hoặc quy tắc sắp xếp rõ ràng.

### 6.3. Không có cascade hoặc referential integrity tự động

Như `@DBRef`, `@DocumentReference` không biến MongoDB thành database có foreign key. Khi xóa tác giả, tài liệu sách vẫn có thể mang ID cũ. Tương tự, lưu sách không tự động bảo đảm tác giả được lưu hoặc cập nhật cùng giao dịch.

**Khi nên chọn:** cần domain model cho phép truy cập `book.getAuthor()`, muốn lưu reference dạng đơn giản và chấp nhận được cơ chế phân giải của Spring Data. **Khi nên cân nhắc lại:** cần kiểm soát tuyệt đối số query, latency của API danh sách hoặc muốn ứng dụng truy cập MongoDB từ nhiều ngôn ngữ/framework khác nhau với quy ước truy vấn rõ ràng.

## 7. $lookup: kết hợp collection ngay trên MongoDB server

`$lookup` là một stage trong MongoDB aggregation pipeline, thực hiện kết hợp tài liệu từ collection đích. Với `books.authorId` và `authors._id`, thao tác dạng equality lookup thường tương đương với một phép **left outer join**: mỗi sách nhận thêm mảng các tác giả phù hợp, kể cả mảng rỗng khi không tìm thấy.

~~~javascript
db.books.aggregate([
  { $match: { status: "PUBLISHED" } },
  {
    $lookup: {
      from: "authors",
      localField: "authorId",
      foreignField: "_id",
      as: "authorDocs"
    }
  },
  {
    $unwind: {
      path: "$authorDocs",
      preserveNullAndEmptyArrays: true
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      authorName: "$authorDocs.name"
    }
  }
]);
~~~

Phân tích từng stage:

1. `$match` lọc chỉ các sách đang xuất bản. Đưa bộ lọc sớm thường làm giảm số document phải join.
2. `$lookup` tìm tài liệu có `authors._id = books.authorId` rồi gắn vào mảng `authorDocs`.
3. `$unwind` chuyển mảng thành phần tử đơn. `preserveNullAndEmptyArrays: true` giúp giữ sách không tìm thấy tác giả; bỏ tùy chọn này có thể khiến sách bị loại khỏi kết quả.
4. `$project` chỉ trả những field phục vụ màn hình, tránh gửi nguyên document tác giả nếu không cần.

Trong ví dụ, `authors._id` là khóa duy nhất nên mỗi sách có tối đa một tác giả. Nếu join trên một field không unique, `$lookup` có thể cho nhiều kết quả và `$unwind` làm tăng số dòng đầu ra. Cần kiểm tra cardinality trước khi chọn cách projection.

### 7.1. Thực hiện bằng MongoTemplate và Aggregation

Tạo DTO:

~~~java
package com.example.library;

public record BookWithAuthor(
        String title,
        String authorName) {
}
~~~

Service tạo aggregation:

~~~java
package com.example.library;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.stereotype.Service;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

@Service
public class BookAggregationService {
    private final MongoTemplate mongo;

    public BookAggregationService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<BookWithAuthor> publishedWithAuthors() {
        Aggregation pipeline = newAggregation(
                match(org.springframework.data.mongodb.core.query.Criteria
                        .where("status").is("PUBLISHED")),
                lookup("authors", "authorId", "_id", "authorDocs"),
                unwind("authorDocs", true),
                project("title")
                        .and("authorDocs.name").as("authorName"));

        return mongo.aggregate(
                pipeline, "books", BookWithAuthor.class)
                .getMappedResults();
    }
}
~~~

Đây là pipeline tường minh trong `MongoTemplate`. Tên field trong `lookup(...)` của ví dụ khớp trực tiếp với BSON đang lưu. Nếu entity dùng `@Field` đổi tên hoặc pipeline có stage raw BSON, cần kiểm tra cách mapping tên field ở từng stage và test với dữ liệu thực.

`@Aggregation` trên repository cũng có thể khai báo pipeline ổn định; điều đó **không làm `@DBRef` và `@DocumentReference` trở thành `$lookup`**. Chọn aggregation repository hay template tùy cách tổ chức code và độ động của pipeline.

### 7.2. $lookup dạng pipeline và giới hạn

MongoDB hỗ trợ thêm dạng `$lookup` có `let` và `pipeline` để join theo điều kiện phức tạp, lọc hoặc project tài liệu đích ngay trong quá trình join. Khả năng dùng index cho biểu thức liên kết, giới hạn dữ liệu và hành vi của `$lookup` có thể phụ thuộc phiên bản MongoDB, cấu trúc pipeline, kiểu index và topology.

Đừng mặc định tất cả join được tối ưu hiệu quả như join trong RDBMS. Cần đo **số document đầu vào, số document kết hợp, số lần sort, độ trễ, bộ nhớ/đĩa trung gian** và dùng `explain` ở môi trường thích hợp. Khi tập sách trả về lớn, hãy cân nhắc `$match`, `$sort`, `$skip`/`$limit` phù hợp, projection gọn và index.

**Ưu điểm:** một pipeline trên server, dễ tạo DTO báo cáo hoặc filter theo trường từ nhiều collection. **Nhược điểm:** pipeline dài có thể khó đọc/debug, output có thể nhân bản khi join 1-nhiều, và không tự giải quyết dữ liệu tham chiếu bị thiếu hoặc tính nhất quán nghiệp vụ.

## 8. Độ trễ, N+1 và chỉ mục

Chọn API theo số lần truy vấn thực sự và hình dạng kết quả:

| Tình huống | Cách đề xuất | Điều cần đo |
|---|---|---|
Xem chi tiết một sách và tác giả | Lưu `authorId`, truy vấn theo nhu cầu; hoặc reference nếu phù hợp | 1–2 round trip, cache, thời gian truy cập |
Danh sách 50–100 sách có tên tác giả | Batch ID hoặc `$lookup` | Số round trip, payload, p95 latency, index |
Báo cáo tổng hợp theo quốc gia tác giả | `$lookup` + `$group`, hoặc read model | Số stage, docs examined, memory |
Tài liệu lịch sử không được thay đổi tên hiển thị | Lưu snapshot tên lúc phát sinh nghiệp vụ | Độ đúng đắn lịch sử, thay đổi nguồn |
Nhiều màn hình chỉ cần ID tác giả | Tham chiếu ứng dụng, không resolve | Tránh truy vấn dữ liệu không dùng |
Collection DBRef đang hoạt động | Giữ `@DBRef`, tối ưu truy cập hoặc lên kế hoạch chuyển đổi | N+1, compatibility, migration |

Chỉ mục nền tảng:

~~~javascript
// MongoDB tạo unique index cho _id theo mặc định.
db.books.createIndex({ authorId: 1 });
db.books.createIndex({ status: 1, authorId: 1 });
~~~

Index `books.authorId` hữu ích khi tìm tất cả sách của một tác giả; join theo `authors._id` có thể dùng index `_id` bên collection authors. Index kết hợp `status` và `authorId` chỉ là ứng viên; nhu cầu sort và tính chọn lọc quyết định index tối ưu. Không nên tạo cả hai index trên mọi hệ thống mà không đo chi phí ghi.

Khi dùng `@DocumentReference` mặc định có field `author` chứa ID, query ngược từ ID có thể cần index trên `books_docref.author`. Với DBRef, cấu trúc tham chiếu có cách lưu khác; cần xem field thực tế khi xây dựng index hoặc query raw.

**N+1 không chỉ là vấn đề ORM quan hệ.** Lazy reference trong MongoDB cũng có thể dẫn tới rất nhiều round trip. Tính số lệnh thật, ví dụ theo MongoDB profiler, command monitoring hoặc công cụ quan sát được phép dùng, thay vì suy đoán từ code Java trông ngắn gọn.

## 9. Nhất quán dữ liệu và vòng đời tham chiếu

MongoDB không tạo foreign key constraint chỉ vì tồn tại ID, DBRef hoặc DocumentReference. Quan hệ có thể bị **dangling** khi đối tượng đích bị xóa, đổi collection hoặc bị di chuyển.

### 9.1. Lưu theo thứ tự và xác nhận tồn tại

Giả sử muốn tạo sách tham chiếu tới tác giả:

1. Xác nhận tác giả tồn tại và người gọi có quyền dùng tác giả đó.
2. Lưu sách với ID tác giả ổn định.
3. Khi trả kết quả, xác định chính sách nếu tác giả không còn tồn tại: trả null, lỗi nghiệp vụ, giữ snapshot hay ẩn sách.

Việc “kiểm tra tồn tại rồi lưu sách” bằng **hai thao tác riêng** không tạo bảo đảm toàn vẹn tuyệt đối: tác giả có thể bị xóa ở giữa. Nếu một bất biến cần bảo đảm nguyên tử qua nhiều document, phải thiết kế transaction/session phù hợp trên MongoDB topology được hỗ trợ, hoặc dùng mô hình dữ liệu khác làm bất biến dễ bảo vệ hơn.

### 9.2. Không có cascade-save mặc định

Với `@DBRef` và `@DocumentReference`, **không mặc định tự động lưu tác giả** khi gọi `bookRepository.save(book)`. Người phát triển cần xử lý lưu đối tượng đích theo ranh giới aggregate và nghiệp vụ. Không được dựa vào hành vi cascade của JPA để suy ra MongoDB sẽ vận hành tương tự.

### 9.3. Khi nào nên nhúng thay vì tham chiếu?

Nếu địa chỉ, giá lúc mua hoặc thông tin biên nhận phải giữ nguyên theo lịch sử, thường nên nhúng *snapshot* vào document nghiệp vụ, vì đọc dữ liệu nguồn hiện tại có thể làm sai lịch sử. Nếu tác giả cập nhật tên và mọi cuốn sách phải hiển thị tên mới, tham chiếu có thể hợp lý hơn.

Một thực thể có thể vừa giữ reference hiện hành, vừa giữ trường snapshot:

~~~json
{
  "_id": "order-line-1",
  "productId": "p-7",
  "titleAtPurchase": "Bình nước 500 ml",
  "unitPriceVndAtPurchase": 129000
}
~~~

Đừng đồng bộ `titleAtPurchase` theo tên sản phẩm mới; đây là bản ghi giao dịch đã chốt. Chính sách dữ liệu được quyết định bởi ý nghĩa nghiệp vụ, không phải annotation.

## 10. Reactive access và ranh giới tải tham chiếu

Spring Data MongoDB có hạ tầng `ReactiveMongoTemplate` và `ReactiveMongoRepository` phục vụ luồng không chặn (*non-blocking*). Khi chọn biểu diễn liên kết trong một ứng dụng reactive:

- Tham chiếu ID rõ ràng cộng truy vấn reactive chủ động (có thể dùng `Flux`/`Mono` và batching) giúp kiểm soát thời điểm I/O.
- Aggregation `$lookup` có thể được thực thi bằng `ReactiveMongoTemplate` với kết quả dạng publisher.
- Không được giả định proxy lazy của các annotation tham chiếu sẽ tự trở thành I/O reactive; cần kiểm tra khả năng hỗ trợ reference resolver của phiên bản Spring Data MongoDB và kiểu driver cụ thể.
- Tránh gọi API đồng bộ hoặc `block()` trực tiếp trên event-loop WebFlux.

Nếu dữ liệu có nhiều liên kết cần đọc cùng lúc, hãy thiết kế **read model/DTO** và xác minh query count ngay từ đầu. Trả thẳng entity mang nhiều lazy reference từ controller có thể tạo truy vấn bổ sung khó quan sát và rủi ro serialization.

## 11. Kiểm thử bốn phương án trên MongoDB thực

Trong Spring Boot 3.x, `@DataMongoTest` có thể giúp kiểm thử repository/template mapping, nhưng không tự khởi tạo server MongoDB. Sử dụng MongoDB test cô lập (có thể qua Testcontainers) để kiểm tra **BSON thực tế**, cách resolve reference và truy vấn aggregation.

Ví dụ kiểm tra dữ liệu raw cho hai cách lưu reference (giả sử đã lưu entity vào các collection riêng):

~~~java
package com.example.library;

import static com.mongodb.client.model.Filters.eq;
import static org.assertj.core.api.Assertions.assertThat;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class ReferenceMappingTest {
    @Autowired
    MongoTemplate mongo;

    @Test
    void distinguishesDocumentReferenceFromDbRef() {
        Author author = new Author("author-7", "Nguyễn An", "VN");
        mongo.save(author);

        mongo.save(new BookDocRef(
                "book-docref-42", "MongoDB thực hành", author));
        mongo.save(new BookDbRef(
                "book-dbref-42", "MongoDB thực hành", author));

        Document docRef = mongo.getCollection("books_docref")
                .find(eq("_id", "book-docref-42"))
                .first();
        Document dbRef = mongo.getCollection("books_dbref")
                .find(eq("_id", "book-dbref-42"))
                .first();

        assertThat(docRef).isNotNull();
        assertThat(dbRef).isNotNull();
        assertThat(docRef.get("author")).isEqualTo("author-7");
        assertThat(dbRef.get("author")).isNotEqualTo("author-7");

        BookDocRef restored =
                mongo.findById("book-docref-42", BookDocRef.class);
        assertThat(restored).isNotNull();
        assertThat(restored.getAuthor().getName())
                .isEqualTo("Nguyễn An");
    }
}
~~~

Test trên minh họa behavior mong đợi khi reference mặc định lưu ID là BSON String; kết quả BSON phải được kiểm tra trên đúng phiên bản đang dùng. Với `@DBRef`, driver/framework có thể biểu diễn dữ liệu raw dưới dạng đối tượng `com.mongodb.DBRef` hoặc document có các thành phần `$ref`/`$id`; không nên ép mọi dạng về một class Java nếu chưa kiểm tra cách driver chuyển đổi.

Các test quan trọng khác:

1. **Manual reference:** tạo sách có `authorId`, xác minh số truy vấn khi đọc một sách và nhiều sách; kiểm tra batch không tạo N+1.
2. **DBRef/DocumentReference:** thử eager và lazy; kiểm tra thời điểm query thực sự chạy, serialization và proxy trên JDK triển khai.
3. **Dangling reference:** xóa tác giả rồi đọc sách; quyết định cách trả lỗi/null thay vì giả định luôn tìm thấy.
4. **Aggregation:** test `$lookup` với sách có tác giả, không có tác giả và nhiều điều kiện lọc; xác minh `$unwind` có hoặc không giữ kết quả thiếu.
5. **Hiệu năng:** đo p95 latency, số lệnh truy vấn, tổng BSON trả về và `explain("executionStats")` ở quy mô dữ liệu phù hợp.
6. **Migration:** thay từ DBRef sang ID hoặc DocumentReference cần đọc được dữ liệu cũ trong giai đoạn chuyển đổi và xác minh tài liệu đã chuyển.
7. **Concurrency:** tạo/xóa document đích đồng thời với document tham chiếu; test chính sách transaction hoặc eventual consistency của nghiệp vụ.

## 12. Các lỗi thiết kế dễ gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
Nghĩ `@DBRef` tự thực thi join server | Thực tế có thể nhiều lần đọc bổ sung | Đo query count; dùng `$lookup` khi cần server-side join |
Nghĩ `@DocumentReference` là DBRef rút gọn có cùng BSON | Migration sai schema, không phân giải được | Đọc raw BSON và hiểu định dạng reference |
Đọc danh sách rồi gọi getter lazy cho từng phần tử | N+1 round trips | Dùng batch, DTO/read model hoặc aggregation |
Đổi annotation từ `@DBRef` sang `@DocumentReference` mà không đổi dữ liệu | Dữ liệu cũ có dạng `$ref`/`$id`, mapping mới có thể sai | Lập kế hoạch migration/read compatibility |
Giả định tham chiếu là foreign key | Xóa tác giả khiến sách mang reference hỏng | Thiết kế chính sách xóa, kiểm tra và đối soát |
Giả định save sách sẽ cascade-save tác giả | Thiếu document đích khi đọc | Lưu aggregate/đích có chủ đích |
Join 1-nhiều rồi unwind mà không xem cardinality | Nhân bản nhiều dòng kết quả, tăng memory | Kiểm tra cardinality, lọc sớm và projection |
Truyền toàn bộ BSON lớn về chỉ để hiển thị tên | Tăng tải mạng và latency | Project field cần dùng, phân trang hợp lý |
Dùng ID String nhưng một bên lưu BSON ObjectId | Reference không khớp dù nhìn giống nhau | Thống nhất `@Id`/`@MongoId` và kiểu BSON |
Trả entity lazy trực tiếp trong REST | Serialization kích hoạt I/O ngoài dự kiến | Chuyển sang DTO với việc tải liên kết tường minh |
Dùng `$lookup` để giải quyết mọi truy vấn | Pipeline phức tạp, bỏ qua index/chi phí ghi | So với batch ID, projection và embedding theo workload |

## 13. Bài tập vận dụng

**Bài 1 — So sánh BSON.** Tạo một `Author`, rồi lưu ba phiên bản sách: `authorId` thuần, `@DBRef` và `@DocumentReference`. Dùng MongoDB shell hoặc Java driver đọc raw BSON. Giải thích vì sao ba dạng lưu trữ không tương đương và cần migration nếu thay đổi annotation.

**Bài 2 — Tìm N+1.** Tạo 100 sách thuộc 10 tác giả. Đo số lệnh MongoDB khi duyệt và đọc tên tác giả qua lazy reference. Viết lại màn hình danh sách bằng cách gom ID và `findAllById`, sau đó đo lại số round trip.

**Bài 3 — Viết $lookup.** Từ collection `books` chứa `authorId`, viết aggregation trả `title` và `authorName` cho sách đã xuất bản. Xử lý tình huống tác giả bị xóa, so sánh kết quả khi bật và tắt `preserveNullAndEmptyArrays`.

**Bài 4 — Đánh giá index.** Tạo index phù hợp để tìm sách theo tác giả và trạng thái. Dùng `explain("executionStats")` với dữ liệu đủ lớn; ghi lại số keys examined, docs examined, execution time và payload khi dùng batch so với `$lookup`.

**Bài 5 — Quy tắc nhất quán.** Trong hệ thống đơn hàng, phân loại thông tin nào cần snapshot lúc mua và thông tin nào nên tham chiếu tới thực thể đang sống. Đưa ra chính sách khi document đích bị xóa, thay ID hoặc chưa đồng bộ.

## 14. Ghi nhớ

**Tham chiếu ứng dụng** lưu ID minh bạch và cho ứng dụng toàn quyền quyết định khi nào tải dữ liệu. **`@DBRef`** dùng định dạng DBRef, phù hợp đặc biệt với dữ liệu đã lưu theo quy ước này. **`@DocumentReference`** hỗ trợ mapping tham chiếu linh hoạt, mặc định có thể lưu ID đơn giản trong BSON và phân giải thành property object. **`$lookup`** là phép kết hợp trên MongoDB server dành cho aggregation, có thể làm việc với dữ liệu lưu ID thông thường.

Khi sử dụng Spring Data MongoDB, hãy chọn dựa trên **số lần truy vấn, hình dạng BSON, loại dữ liệu cần trả, độ trễ, index, lifecycle và mức nhất quán**. Không phương án nào tự tạo foreign key hoặc cascade-save. Với các truy vấn danh sách, kiểm tra N+1; với aggregation, kiểm tra query plan; với mọi dạng reference, test raw BSON và chính sách xử lý dữ liệu đích bị thiếu.
