# OrderBy và sắp xếp động

## 1. Khi nào cần sắp xếp trong Spring Data MongoDB?

Trong Spring Data MongoDB, repository có thể tự tạo truy vấn dựa trên **tên phương thức** (*derived query*). Khi kết quả là danh sách, ứng dụng thường cần một thứ tự cụ thể: sách mới nhất trước, sách theo tên A–Z, bài viết được xem nhiều nhất hoặc các đơn hàng ưu tiên xử lý trước.

Với những trường hợp đó, Spring Data cung cấp hai cách quan trọng:

- **`OrderBy` trong tên phương thức:** ghi rõ khóa và chiều sắp xếp cố định ngay trong interface repository, ví dụ `findByStatusOrderByCreatedAtDescIdDesc(...)`.
- **`Sort` truyền khi gọi phương thức:** quyết định khóa và chiều sắp xếp tại runtime, ví dụ `findByStatus("PUBLISHED", Sort.by("title").ascending())`.

Khi cần chia trang, có thể đưa `Sort` vào `Pageable` để vừa sắp xếp vừa giới hạn số document trả về.

Điểm cốt lõi là **sắp xếp phải được thực hiện ở MongoDB**, không phải tải một collection rất lớn về Java rồi dùng `List.sort(...)`. Trong hệ thống thực tế, thứ tự kết quả cũng liên quan đến **index, tính ổn định của phân trang, cách ánh xạ tên field BSON và an toàn của tham số người dùng**.

| Nhu cầu nghiệp vụ | Lựa chọn thường hợp lý |
| --- | --- |
| Một màn hình luôn hiển thị sách mới nhất | Derived query có `OrderByCreatedAtDescIdDesc` |
| Người dùng chọn sắp theo tên, lượt xem hoặc thời điểm | Derived query nhận tham số `Sort` |
| API trả từng trang sách và cần thứ tự xác định | `Pageable` chứa `Sort` |
| Cần lọc, projection hoặc aggregation phức tạp | `MongoTemplate` hay aggregation với `$sort` |
| Ứng dụng reactive | Repository hoặc `ReactiveMongoTemplate` với nguyên tắc sắp xếp tương tự |

## 2. Dữ liệu và entity dùng xuyên suốt bài học

Giả sử một ứng dụng quản lý sách có collection `books`. Trạng thái có thể là `DRAFT` hoặc `PUBLISHED`, còn thời điểm tạo được lưu ở tên BSON `created_at`.

Ví dụ tài liệu thực hành trong `mongosh`:

```javascript
use book_sort_demo

db.books.insertMany([
  {
    _id: "BK-001",
    title: "Java căn bản",
    status: "PUBLISHED",
    created_at: ISODate("2026-11-01T08:00:00Z"),
    view_count: 80,
    author_name: "An"
  },
  {
    _id: "BK-002",
    title: "MongoDB thực hành",
    status: "PUBLISHED",
    created_at: ISODate("2026-11-04T08:00:00Z"),
    view_count: 140,
    author_name: "Bình"
  },
  {
    _id: "BK-003",
    title: "Spring Data nhập môn",
    status: "PUBLISHED",
    created_at: ISODate("2026-11-10T08:00:00Z"),
    view_count: 120,
    author_name: "An"
  },
  {
    _id: "BK-004",
    title: "Query nâng cao",
    status: "PUBLISHED",
    created_at: ISODate("2026-11-10T08:00:00Z"),
    view_count: 260,
    author_name: "Chi"
  },
  {
    _id: "BK-005",
    title: "Bản thảo dữ liệu",
    status: "DRAFT",
    created_at: ISODate("2026-11-12T08:00:00Z"),
    view_count: 0,
    author_name: "Bình"
  }
])
```

Chỉ chạy `insertMany` khi collection thực hành chưa có các ID này; chạy lại sẽ gây lỗi duplicate key. Trên Spring Boot 3.x, ví dụ ứng dụng có thể dùng `spring.data.mongodb.uri=mongodb://localhost:27017/book_sort_demo`. Môi trường triển khai thật cần cấu hình xác thực, quyền truy cập và kết nối an toàn.

Entity Java được khai báo như sau:

```java
package com.example.library;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "books")
public class Book {

    @MongoId(FieldType.STRING)
    private String id;

    private String title;
    private String status;

    @Field("created_at")
    private Instant createdAt;

    @Field("view_count")
    private long viewCount;

    @Field("author_name")
    private String authorName;

    protected Book() {}

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public long getViewCount() { return viewCount; }
    public String getAuthorName() { return authorName; }
}
```

Lưu ý ba nhóm tên:

| Property Java | Field BSON | Dùng khi viết derived query hoặc `Sort` theo entity |
| --- | --- | --- |
| `id` | `_id` | `id` |
| `createdAt` | `created_at` | `createdAt` |
| `viewCount` | `view_count` | `viewCount` |
| `authorName` | `author_name` | `authorName` |
| `title` | `title` | `title` |

`@MongoId(FieldType.STRING)` giúp ID có dạng `BK-001` được biểu diễn bằng BSON String. Với `@Field`, Spring Data ánh xạ property Java sang tên field BSON; trong `mongosh` vẫn phải viết tên BSON thật.

## 3. `OrderBy` cố định trong tên phương thức

Khai báo repository:

```java
package com.example.library;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookRepository extends MongoRepository<Book, String> {

    List<Book> findByStatusOrderByCreatedAtDescIdDesc(String status);

    List<Book> findByStatusOrderByTitleAscIdAsc(String status);

    List<Book> findTop3ByStatusOrderByViewCountDescIdAsc(String status);
}
```

Spring Data phân tích tên phương thức thành hai phần:

1. **Phần điều kiện** `findByStatus`: lọc các document có property `status` bằng tham số truyền vào.
2. **Phần sắp xếp tĩnh** bắt đầu bằng `OrderBy`: định nghĩa một hoặc nhiều property và hướng `Asc`/`Desc`.

Ví dụ:

```java
List<Book> newest =
    bookRepository.findByStatusOrderByCreatedAtDescIdDesc("PUBLISHED");

List<Book> alphabetical =
    bookRepository.findByStatusOrderByTitleAscIdAsc("PUBLISHED");

List<Book> mostViewed =
    bookRepository.findTop3ByStatusOrderByViewCountDescIdAsc("PUBLISHED");
```

Từ bộ dữ liệu mẫu, ý nghĩa của từng lời gọi:

| Phương thức | Tiêu chí | Thứ tự mong đợi của ID |
| --- | --- | --- |
| `findByStatusOrderByCreatedAtDescIdDesc` | Mới nhất trước; cùng thời điểm thì ID giảm dần | `BK-004`, `BK-003`, `BK-002`, `BK-001` |
| `findByStatusOrderByTitleAscIdAsc` | Theo tiêu đề tăng dần; cùng tiêu đề thì ID tăng dần | Phụ thuộc quy tắc so sánh chuỗi/collation của MongoDB |
| `findTop3ByStatusOrderByViewCountDescIdAsc` | Ba sách PUBLISHED có lượt xem cao nhất | `BK-004`, `BK-002`, `BK-003` |

Trong `mongosh`, truy vấn tương ứng với lựa chọn “mới nhất trước”:

```javascript
db.books.find({ status: "PUBLISHED" })
  .sort({ created_at: -1, _id: -1 })
```

Kết quả có thể sắp theo các khóa tương ứng vì:

- `OrderByCreatedAt` diễn giải theo **property Java** `createdAt`, không phải literal `created_at` trong tên method.
- `Desc` diễn đạt giảm dần; `Asc` diễn đạt tăng dần.
- Nhiều khóa được nối tiếp trong tên phương thức: `CreatedAtDescIdDesc`.
- `findTop3By...` bổ sung giới hạn tối đa ba kết quả sau khi sắp xếp.

### Những sai lầm khi đặt tên phương thức

```java
// Đúng: phần OrderBy dùng tên property Java.
List<Book> findByStatusOrderByCreatedAtDesc(String status);

// Sai ý định: viết tên trường BSON dạng snake_case trong method.
// List<Book> findByStatusOrderByCreated_atDesc(String status);

// Sai ý định: viết tên property không tồn tại trên entity.
// List<Book> findByStatusOrderByPublicationDateDesc(String status);
```

Spring Data cần phân tích đúng đường dẫn property. Nếu không tìm được property, ứng dụng thường báo lỗi khi khởi tạo repository hoặc khi tạo truy vấn. Đừng dựa vào việc một method biên dịch được trong Java để kết luận Spring Data có thể suy diễn đúng truy vấn MongoDB.

**Chọn `OrderBy` tĩnh khi mọi lời gọi của phương thức phải theo cùng một thứ tự.** Nếu giao diện cho người dùng chọn nhiều phương án sắp xếp, việc tạo một phương thức riêng cho từng phương án có thể dẫn đến interface dài và khó bảo trì.

## 4. Sắp xếp động với tham số `Sort`

Khi yêu cầu có tùy chọn “Mới nhất”, “Tên A–Z” hoặc “Xem nhiều nhất”, hãy khai báo phương thức nhận `org.springframework.data.domain.Sort`:

```java
import java.util.List;
import org.springframework.data.domain.Sort;

public interface BookRepository extends MongoRepository<Book, String> {

    List<Book> findByStatus(String status, Sort sort);
}
```

Đây là một **biến thể của `BookRepository` ở mục trước**. Khi áp dụng trong dự án, gộp tất cả phương thức vào cùng một interface, không tạo hai interface trùng tên.

Lời gọi:

```java
import org.springframework.data.domain.Sort;

Sort newestSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Sort titleSort = Sort.by(
    Sort.Order.asc("title"),
    Sort.Order.asc("id")
);

Sort popularSort = Sort.by(
    Sort.Order.desc("viewCount"),
    Sort.Order.asc("id")
);

List<Book> newest =
    bookRepository.findByStatus("PUBLISHED", newestSort);

List<Book> byTitle =
    bookRepository.findByStatus("PUBLISHED", titleSort);

List<Book> popular =
    bookRepository.findByStatus("PUBLISHED", popularSort);
```

**Cùng một phương thức repository** nhưng có thể tạo nhiều thứ tự sắp xếp. Các khóa và hướng nằm trong đối tượng `Sort` khi runtime.

Một vài dạng khai báo `Sort` hữu ích:

```java
Sort descendingByTime = Sort.by("createdAt").descending();

Sort ascendingByTitle = Sort.by("title").ascending();

Sort multiKey = Sort.by(Sort.Order.desc("viewCount"))
    .and(Sort.by(Sort.Order.asc("id")));

Sort unspecified = Sort.unsorted();
```

`Sort.unsorted()` nghĩa là không yêu cầu thứ tự. Nó **không có nghĩa** MongoDB sẽ luôn trả theo thứ tự insert hoặc `_id`. Nếu kết quả được phân trang hay hiển thị có thứ tự ổn định, hãy gửi `Sort` tường minh.

### So sánh `OrderBy` và `Sort`

| Tiêu chí | `OrderBy` trong tên method | `Sort` động |
| --- | --- | --- |
| Định nghĩa thứ tự | Trong tên phương thức Java | Trong đối số khi gọi |
| Linh hoạt giữa các request | Ít, cần phương thức khác | Cao, có thể xây từ yêu cầu hợp lệ |
| Khả năng đọc nhanh ý nghĩa method | Rõ khi ít khóa | Rõ nếu tên biến hoặc builder diễn đạt đúng |
| Nguy cơ dùng tên property sai | Phát hiện qua phân tích method | Cần xác thực và kiểm thử các field sort |
| Khi dùng | Màn hình có thứ tự cố định | API danh sách cho phép đổi thứ tự |

**Không nên trộn `OrderBy` cố định với `Sort` động mà không xác định rõ quy tắc ưu tiên và cách framework ghép điều kiện ở phiên bản đang dùng.** Nếu cần một sort do caller kiểm soát, hãy khai báo query nhận `Sort` mà không có `OrderBy` trong tên để tránh gây hiểu lầm.

## 5. Ghép `Sort` với `Pageable` để giới hạn kết quả

`Sort` một mình **không giới hạn số lượng** document được trả về. Trong một API hiển thị danh sách, cần giới hạn số bản ghi từ phía database. Spring Data hỗ trợ `Pageable`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import java.util.List;

public interface BookRepository extends MongoRepository<Book, String> {

    List<Book> findByStatus(String status, Sort sort);

    Page<Book> findByStatus(String status, Pageable pageable);
}
```

Tạo yêu cầu trang đầu, kích thước hai phần tử, sắp mới nhất trước:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

Pageable firstPage = PageRequest.of(0, 2, sort);

Page<Book> result =
    bookRepository.findByStatus("PUBLISHED", firstPage);

List<Book> content = result.getContent();
long total = result.getTotalElements();
boolean hasNext = result.hasNext();
```

Với dữ liệu demo trong mục 2, danh sách `PUBLISHED` được sắp `createdAt DESC, id DESC` là:

| Vị trí sau sort | ID | Thời điểm |
| --- | --- | --- |
| 1 | `BK-004` | `2026-11-10T08:00:00Z` |
| 2 | `BK-003` | `2026-11-10T08:00:00Z` |
| 3 | `BK-002` | `2026-11-04T08:00:00Z` |
| 4 | `BK-001` | `2026-11-01T08:00:00Z` |

Vì vậy:

- Trang `0`, kích thước `2`: `BK-004` và `BK-003`.
- Trang `1`, kích thước `2`: `BK-002` và `BK-001`.
- `totalElements` là `4` nếu database chỉ chứa bộ dữ liệu mẫu và không có ghi mới.

Tương đương về ý nghĩa trong MongoDB:

```javascript
db.books.find({ status: "PUBLISHED" })
  .sort({ created_at: -1, _id: -1 })
  .skip(0)
  .limit(2)
```

**PageRequest đánh số trang từ 0**, và kích thước trang phải lớn hơn 0. `Page<Book>` có thông tin tổng số phần tử, vì vậy Spring Data có thể cần thêm truy vấn count. Khi giao diện chỉ yêu cầu “có trang sau hay không?” mà không cần tổng số, có thể cân nhắc cơ chế trả `Slice` hoặc truy vấn lấy thêm một phần tử theo khả năng của phiên bản repository đang dùng.

`findAll(Pageable)` cũng có thể được gọi trực tiếp từ `MongoRepository`, nhưng không có điều kiện `status`. Nếu nhu cầu nghiệp vụ chỉ được xem sách đã xuất bản, **dùng `findByStatus(..., pageable)`** thay vì lấy tất cả rồi lọc trong Java.

## 6. Tại sao cần khóa phụ để sắp xếp ổn định?

Hai sách `BK-003` và `BK-004` có cùng `created_at`. Truy vấn chỉ:

```javascript
db.books.find({ status: "PUBLISHED" })
  .sort({ created_at: -1 })
```

**không quy định thứ tự giữa hai document có cùng thời điểm**. Thứ tự chúng xuất hiện có thể bị ảnh hưởng bởi kế hoạch thực thi, index hoặc thay đổi dữ liệu.

Thêm một khóa sắp xếp duy nhất, thường là `_id`:

```javascript
db.books.find({ status: "PUBLISHED" })
  .sort({ created_at: -1, _id: -1 })
```

và diễn đạt tương ứng trong Java:

```java
Sort stableNewest = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
```

Lúc đó, **đối với một tập dữ liệu không đổi**, thứ tự được xác định đầy đủ. `_id` là duy nhất trong một collection nên dùng làm khóa phụ rất thuận tiện.

Lưu ý quan trọng: khóa phụ giúp thứ tự xác định nhưng **không biến nhiều request phân trang thành một snapshot bất biến**. Nếu có sách mới được thêm giữa lần lấy trang 1 và trang 2, phân trang dựa trên `skip` vẫn có thể lặp hoặc bỏ qua document. Với danh sách cuộn vô hạn, có thể chuyển sang cursor/keyset pagination.

Ví dụ trang tiếp theo sau một kết quả cuối có `created_at` và `_id`:

```javascript
const lastCreatedAt = ISODate("2026-11-10T08:00:00Z");
const lastId = "BK-003";

db.books.find({
  status: "PUBLISHED",
  $or: [
    { created_at: { $lt: lastCreatedAt } },
    {
      created_at: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ created_at: -1, _id: -1 })
.limit(2)
```

Cursor cần được lấy từ **document cuối của trang trước**, chứa đủ tất cả khóa sort, và các bộ lọc như `status` phải được giữ nhất quán giữa các trang. Mẫu trên áp dụng khi sort giảm dần theo cả `created_at` và `_id`. Khi cho phép sort động, điều kiện cursor cũng phải thay đổi tương ứng; không thể dùng chung một biểu thức cho mọi hướng sắp.

## 7. Bảo vệ `Sort` động từ yêu cầu người dùng

Một API thực tế có thể nhận các tham số:

```text
GET /books?status=PUBLISHED&sort=newest&page=0&size=20
GET /books?status=PUBLISHED&sort=title&page=0&size=20
GET /books?status=PUBLISHED&sort=popular&page=0&size=20
```

Không nên lấy chuỗi người dùng cung cấp rồi chuyển thẳng thành `Sort.by(userValue)`. Không phải mọi property đều nên được phép sắp xếp: trường lớn, trường nhạy cảm, đường dẫn chưa có index hoặc property sai có thể gây lỗi, truy vấn chậm hoặc lộ thông tin ngoài ý định.

Một cách đơn giản là **cho phép đúng những tùy chọn nghiệp vụ đã định nghĩa**:

```java
package com.example.library;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class BookListingService {

    private final BookRepository books;

    public BookListingService(BookRepository books) {
        this.books = books;
    }

    public Page<Book> list(
            String status,
            String sortKey,
            int page,
            int size) {
        if (status == null || status.isBlank()) {
            throw new IllegalArgumentException("Thiếu trạng thái");
        }
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Trang không hợp lệ");
        }

        String selected = sortKey == null ? "newest" : sortKey;

        Sort sort = switch (selected) {
            case "newest" -> Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            );
            case "title" -> Sort.by(
                Sort.Order.asc("title"),
                Sort.Order.asc("id")
            );
            case "popular" -> Sort.by(
                Sort.Order.desc("viewCount"),
                Sort.Order.asc("id")
            );
            default -> throw new IllegalArgumentException(
                "Kiểu sắp xếp không được hỗ trợ: " + selected
            );
        };

        return books.findByStatus(
            status,
            PageRequest.of(page, size, sort)
        );
    }
}
```

Service trên dùng `switch` expression của Java 17 trở lên. Nó giới hạn kích thước trang ở 100, không cho người dùng chọn tùy ý đường dẫn MongoDB và luôn thêm ID làm khóa phụ.

Việc cho phép `status` từ request cũng cần tuân theo **ràng buộc nghiệp vụ**: nếu chỉ được xem sách xuất bản, service hoặc lớp kiểm tra quyền phải áp đặt trạng thái phù hợp thay vì tin tưởng hoàn toàn vào request. Trong ứng dụng nhiều tenant, cần lọc theo `tenantId` và kiểm tra quyền ở tầng truy vấn. `Sort` là công cụ sắp xếp, **không phải cơ chế phân quyền**.

### Nếu API nhận tên field và hướng sort riêng

Một số API cho phép `sortField=createdAt&direction=desc`. Khi đó cần chuyển tên bên ngoài (ví dụ `created`, `title`, `views`) về một **danh sách property Java được phép** và kiểm tra `direction` chỉ là `asc` hoặc `desc`. Sau đó có thể dựng:

```java
Sort.Direction direction =
    Sort.Direction.fromString("desc");

Sort sort = Sort.by(
    new Sort.Order(direction, "createdAt"),
    Sort.Order.desc("id")
);
```

Đoạn trên là minh họa với giá trị `"desc"` đã được xác thực. Nếu sort theo `createdAt` tăng dần, khóa phụ nên được xác định theo quy tắc sản phẩm; quan trọng là tạo được **thứ tự đầy đủ và nhất quán**.

## 8. Sắp xếp chuỗi, chữ hoa và collation

Sắp xếp theo `title` không đơn giản là “A–Z tiếng Việt” trong mọi môi trường. MongoDB có quy tắc so sánh chuỗi mặc định và hỗ trợ **collation** để chọn quy tắc so sánh theo ngôn ngữ, độ phân biệt chữ hoa/thường, dấu và các tùy chọn khác.

Ví dụ khi ứng dụng cần sắp xếp tiêu đề theo tiếng Việt, một truy vấn trong `mongosh` có thể yêu cầu collation:

```javascript
db.books.find({ status: "PUBLISHED" })
  .collation({ locale: "vi", strength: 2 })
  .sort({ title: 1, _id: 1 })
```

`locale: "vi"` là lựa chọn theo tiếng Việt; `strength` điều chỉnh mức phân biệt khi so sánh. Thứ tự chính xác vẫn cần được xác nhận bằng tập dữ liệu gồm chữ hoa, chữ thường và ký tự có dấu. Không nên coi một lệnh `OrderByTitleAsc` tự động áp dụng quy tắc tiếng Việt; đó là **sort theo cơ chế so sánh đang có**, có thể cần thêm collation ở cấp truy vấn hoặc collection.

Với `MongoTemplate` có thể biểu diễn collation tường minh:

```java
import org.springframework.data.mongodb.core.query.Collation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.domain.Sort;

Query query = Query.query(
    Criteria.where("status").is("PUBLISHED")
);
query.with(Sort.by(
    Sort.Order.asc("title"),
    Sort.Order.asc("id")
));
query.collation(Collation.of("vi"));
query.limit(20);
```

Collation trong query và collation của index cần **tương thích** để index hỗ trợ sắp xếp theo chuỗi như dự kiến. Nếu cần sort tiếng Việt thường xuyên, hãy xem xét index được tạo với collation tương ứng và đo `explain`. Không tự giả định một index sắp theo so sánh mặc định sẽ tối ưu mọi truy vấn dùng collation tùy chọn.

### Trường null, missing và kiểu BSON khác nhau

Nếu một số document không có `title` hoặc `created_at`, MongoDB vẫn phải đặt chúng vào thứ tự theo quy tắc so sánh BSON. Những document thiếu field và document có field `null` cần được xem xét rõ trong yêu cầu nghiệp vụ; `Sort` không tự lấp giá trị thay thế.

Đặc biệt, trộn BSON Date với String ở `created_at` có thể tạo thứ tự không đúng ý định “mới nhất”. Vì vậy, cần kiểm soát schema, chuyển dữ liệu cũ nếu cần và kiểm thử trên document BSON thật.

## 9. Thiết kế index để sắp xếp không trở thành nút thắt

Truy vấn có `sort` luôn **có thể tạo thêm công việc ở MongoDB**. Tùy bộ lọc, số document và index hiện có, MongoDB có thể trả theo thứ tự từ index hoặc cần một bước sort riêng. Với dữ liệu lớn, các bước sort không được hỗ trợ tốt có thể tốn tài nguyên hoặc trở nên chậm.

Giả sử truy vấn quan trọng nhất là:

```javascript
db.books.find({ status: "PUBLISHED" })
  .sort({ created_at: -1, _id: -1 })
  .limit(20)
```

Một index ứng viên:

```javascript
db.books.createIndex(
  { status: 1, created_at: -1, _id: -1 },
  { name: "books_status_created_id_desc" }
)
```

Trong trường hợp này:

- `status` là điều kiện **bằng**, thường nên đứng trước các khóa dùng cho sort.
- `created_at` và `_id` theo cùng chiều với yêu cầu sắp xếp.
- Có thể quét các sách `PUBLISHED` theo thứ tự phù hợp mà không cần sắp xếp một tập kết quả lớn ở ứng dụng.

Nếu workload thường dùng “xem nhiều nhất”, có thể cần một index khác:

```javascript
db.books.createIndex(
  { status: 1, view_count: -1, _id: 1 },
  { name: "books_status_views_id" }
)
```

Đối với sort theo `title`, một index khác có thể phù hợp, đặc biệt khi collation dùng cho chuỗi phải khớp với index. **Không tạo tất cả các index chỉ vì UI có nhiều tùy chọn sort**: mỗi index tốn bộ nhớ và dung lượng lưu trữ, đồng thời tăng chi phí cho thao tác insert/update/delete.

### Quan sát query plan

Trong `mongosh`:

```javascript
db.books.find({ status: "PUBLISHED" })
  .sort({ created_at: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Đọc các chỉ dấu:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| `winningPlan` | MongoDB chọn kế hoạch nào? |
| `IXSCAN` hay `COLLSCAN` | Có dùng index hay phải quét collection? |
| Stage sắp xếp như `SORT` | Có cần bước sort riêng ngoài thứ tự index không? |
| `totalKeysExamined` | Duyệt bao nhiêu khóa index? |
| `totalDocsExamined` | Phải đọc bao nhiêu document? |
| `nReturned` | Trả bao nhiêu kết quả sau bộ lọc/giới hạn? |
| `executionTimeMillis` | Thời gian đo của lần thực thi này là bao nhiêu? |

Không đánh giá index chỉ bằng việc thấy `IXSCAN`. Nếu truy vấn quét một số lượng khóa rất lớn để trả 20 document, hiệu quả có thể vẫn thấp. Mặt khác, `COLLSCAN` trên collection demo năm bản ghi không nói lên hiệu năng khi có hàng triệu bản ghi. Cần đo với dữ liệu và tải đại diện, đồng thời kiểm tra độ trễ từ ứng dụng.

### Tên trường trong index khác tên property Java

Trong repository:

```java
Sort.by(Sort.Order.desc("createdAt"));
```

Trong `mongosh`:

```javascript
db.books.createIndex({ created_at: -1 })
```

Không tạo nhầm index `{ createdAt: -1 }` nếu document thật lưu ở `created_at`. Khi dùng annotation index ở tầng entity, vẫn cần kiểm tra index thực tế trên MongoDB và cơ chế tạo index của phiên bản Spring Data/Spring Boot: chỉ khai báo annotation không bảo đảm hệ thống đã tự tạo index trong mọi cấu hình.

## 10. `MongoTemplate` và sort trong aggregation

Khi bộ lọc không thể diễn đạt rõ bằng tên derived method hoặc có nhiều điều kiện tùy chọn, dùng `MongoTemplate`:

```java
package com.example.library;

import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class BookQueryService {

    private final MongoTemplate template;

    public BookQueryService(MongoTemplate template) {
        this.template = template;
    }

    public List<Book> recentPublished(int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Giới hạn không hợp lệ");
        }

        Query query = Query.query(
            Criteria.where("status").is("PUBLISHED")
        );
        query.with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ));
        query.limit(limit);

        return template.find(query, Book.class);
    }
}
```

Khi `find(query, Book.class)` có metadata mapping của entity, Spring Data sử dụng tên field BSON phù hợp: `createdAt` được ánh xạ thành `created_at` và `id` thành `_id`. Với truy vấn viết bằng driver trực tiếp hoặc câu lệnh trong `mongosh`, phải dùng tên BSON.

Trong aggregation, ta có thể dùng stage `$sort` và `$limit`:

```javascript
db.books.aggregate([
  { $match: { status: "PUBLISHED" } },
  { $sort: { view_count: -1, _id: 1 } },
  { $limit: 3 },
  {
    $project: {
      _id: 1,
      title: 1,
      view_count: 1
    }
  }
])
```

Đây là một pipeline trên MongoDB, không phải tên phương thức suy diễn. Trật tự `$match`, `$sort`, `$limit` được chọn để phù hợp mục tiêu lọc rồi lấy số ít kết quả đã sắp. Bộ tối ưu aggregation có thể điều chỉnh các stage khi an toàn, nhưng không nên mặc định mọi aggregation đều dùng đúng index mong muốn; hãy kiểm tra explain và dữ liệu thực tế.

### Trường lồng nhau và tham chiếu

Nếu `Book` nhúng một object `author` với property `name`, có thể dùng sắp xếp theo đường dẫn nested property như `Sort.by("author.name")` khi metadata mapping hỗ trợ đường dẫn đó. Nhưng **sắp xếp theo trường của document trong collection khác không tự join** chỉ nhờ derived method hay `Sort`. Khi dữ liệu cần sắp nằm ở collection được tham chiếu, phải cân nhắc `$lookup`, truy vấn hai bước hoặc lưu một field phục vụ sort có chính sách đồng bộ rõ ràng.

## 11. Sắp xếp trong Reactive MongoDB

Trong ứng dụng reactive, `ReactiveMongoRepository` và `ReactiveMongoTemplate` vẫn có khả năng nhận sort, nhưng kiểu kết quả thường là `Flux<T>`/`Mono<T>` thay vì `List<T>` hoặc `Optional<T>`.

Ví dụ:

```java
package com.example.library;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveBookRepository
        extends ReactiveMongoRepository<Book, String> {

    Flux<Book> findByStatusOrderByCreatedAtDescIdDesc(String status);

    Flux<Book> findByStatus(String status, Sort sort);

    Flux<Book> findByStatus(String status, Pageable pageable);
}
```

Lấy các sách xuất bản theo trang và sắp ở server:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Flux;

Flux<Book> firstTwenty = reactiveBookRepository.findByStatus(
    "PUBLISHED",
    PageRequest.of(
        0, 20,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        )
    )
);
```

Khi được subscribe, luồng thực hiện truy vấn MongoDB có phân trang và sort. `Flux` không có sẵn thông tin tổng số phần tử như `Page`; nếu cần tổng, ứng dụng phải thiết kế thao tác đếm tương ứng và ghép kết quả theo nhu cầu. Tránh dùng `findAll().collectList()` để tải cả collection chỉ nhằm chọn 20 phần tử ở Java.

**Reactive không miễn phí công việc của database.** Nếu không có index hỗ trợ sort hoặc query trả quá nhiều bản ghi, MongoDB vẫn chịu chi phí thực thi. Mã xử lý reactive cũng không nên gọi `block()` trực tiếp trên thread xử lý request.

## 12. Kiểm thử thứ tự thực tế

Khi muốn xác minh một derived method có `OrderBy` hoạt động đúng, hãy dùng **MongoDB thật trong môi trường kiểm thử tích hợp**, ví dụ MongoDB dành cho test hoặc Testcontainers. Kiểm tra cả hai trường hợp: dữ liệu có khóa sort khác nhau và dữ liệu có khóa sort bằng nhau.

Để dễ tạo fixture, có thể bổ sung constructor sau vào entity `Book` ở mục 2:

```java
public Book(
        String id, String title, String status,
        Instant createdAt, long viewCount, String authorName) {
    this.id = id;
    this.title = title;
    this.status = status;
    this.createdAt = createdAt;
    this.viewCount = viewCount;
    this.authorName = authorName;
}
```

Ví dụ kiểm thử dưới đây sử dụng một **database riêng chỉ dành cho test**. Việc `deleteAll()` là thao tác hủy dữ liệu và tuyệt đối không được chạy trên database dùng chung hoặc production.

```java
package com.example.library;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class BookSortingRepositoryTest {

    @Autowired
    BookRepository books;

    @BeforeEach
    void insertIntoIsolatedTestDatabase() {
        books.deleteAll();
        Instant sameTime = Instant.parse("2026-11-10T08:00:00Z");
        books.insert(List.of(
            new Book("BK-001", "A", "PUBLISHED",
                Instant.parse("2026-11-01T08:00:00Z"), 80, "An"),
            new Book("BK-002", "B", "PUBLISHED",
                Instant.parse("2026-11-04T08:00:00Z"), 140, "Bình"),
            new Book("BK-003", "C", "PUBLISHED",
                sameTime, 120, "An"),
            new Book("BK-004", "D", "PUBLISHED",
                sameTime, 260, "Chi"),
            new Book("BK-005", "E", "DRAFT",
                Instant.parse("2026-11-12T08:00:00Z"), 0, "Bình")
        ));
    }

    @Test
    void staticOrderByUsesCreatedAtThenId() {
        assertThat(books
            .findByStatusOrderByCreatedAtDescIdDesc("PUBLISHED"))
            .extracting(Book::getId)
            .containsExactly("BK-004", "BK-003", "BK-002", "BK-001");
    }

    @Test
    void dynamicSortByViewsCanUseDifferentOrder() {
        Sort sort = Sort.by(
            Sort.Order.desc("viewCount"),
            Sort.Order.asc("id")
        );

        assertThat(books.findByStatus("PUBLISHED", sort))
            .extracting(Book::getId)
            .containsExactly("BK-004", "BK-002", "BK-003", "BK-001");
    }

    @Test
    void pagedSortKeepsStableOrder() {
        Page<Book> page = books.findByStatus(
            "PUBLISHED",
            PageRequest.of(0, 2, Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            ))
        );

        assertThat(page.getContent())
            .extracting(Book::getId)
            .containsExactly("BK-004", "BK-003");

        assertThat(page.getTotalElements()).isEqualTo(4);
        assertThat(page.hasNext()).isTrue();
    }
}
```

Các method `findByStatusOrderByCreatedAtDescIdDesc` và `findByStatus` cần được khai báo chung trong `BookRepository` như các phần trước. `@DataMongoTest` cung cấp cấu hình kiểm thử lớp dữ liệu, nhưng **không tự bảo đảm một MongoDB thử nghiệm an toàn đã sẵn sàng**; dự án cần cấu hình hạ tầng test phù hợp.

Các ca bổ sung nên có:

1. Nhiều sách có cùng `createdAt` để xác minh khóa phụ `id`.
2. Field `created_at` thiếu/null hoặc sai BSON type trong tài liệu lịch sử.
3. Tham số sort bị từ chối khi không thuộc allowlist, kích thước trang vượt giới hạn.
4. Sắp theo tên tiếng Việt với/không có collation mong muốn.
5. So sánh query plan khi có và chưa có index phù hợp trên dữ liệu đại diện.
6. Thêm dữ liệu giữa hai request trang để kiểm tra chính sách phân trang của API.

## 13. Những lỗi hay gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Phương thức `OrderBy` không khởi tạo được | Tên property trong derived method không tồn tại | Dùng tên property Java chính xác, kiểm tra stack trace phân tích query |
| Sort theo `createdAt` nhưng dữ liệu MongoDB có `created_at` | Nhầm tên Java và BSON trong truy vấn thô | Với repository dùng `createdAt`; với `mongosh` dùng `created_at` |
| Kết quả đổi vị trí khi cùng timestamp | Chỉ sắp theo `createdAt`, không có khóa phụ | Thêm `id` hoặc trường duy nhất khác |
| `findByStatus(..., Sort)` trả quá nhiều sách | `Sort` không có giới hạn | Sử dụng `Pageable`, `Top` hoặc giới hạn query |
| Sort do người dùng gửi gây query không mong muốn | Không kiểm soát tên property hoặc chiều sort | Allowlist lựa chọn nghiệp vụ, kiểm tra kích thước trang |
| `findAll(Pageable)` lộ sách DRAFT | Không có điều kiện trạng thái/quyền | Dùng query theo `status` và điều kiện phân quyền |
| Trang sâu rất chậm | Phân trang offset/skip lớn | Cân nhắc cursor/keyset, đo bằng explain |
| Sort theo title không theo thứ tự tiếng Việt | Collation chưa phù hợp hoặc index khác collation | Xác định quy tắc so sánh và tạo index tương thích |
| Sort chậm dù đã có index | Thứ tự khóa index không phù hợp filter/sort | Xem `winningPlan`, `totalKeysExamined`, `SORT` và workload thực tế |
| Pipeline aggregation sort sai field | Viết tên property Java vào BSON thô | Dùng tên field BSON trong `mongosh`/pipeline thô |
| Sort theo tên document tham chiếu không hoạt động | Derived query không tự join collection khác | Dùng `$lookup`, mô hình snapshot hoặc truy vấn liên quan tường minh |

## 14. Bài tập tự kiểm tra

**Bài tập 1.** Viết derived query tìm sách có `status` xác định, sắp theo `createdAt` giảm dần rồi `id` giảm dần.

**Đáp án:**

```java
List<Book> findByStatusOrderByCreatedAtDescIdDesc(String status);
```

**Bài tập 2.** Làm sao dùng một phương thức để lúc thì sắp theo tên, lúc thì sắp theo lượt xem?

**Đáp án:** Khai báo `findByStatus(String status, Sort sort)` rồi truyền `Sort.by("title").ascending()` hoặc `Sort.by("viewCount").descending()`; thêm khóa phụ `id` nếu yêu cầu thứ tự ổn định.

**Bài tập 3.** Có 4 sách `PUBLISHED` và cần lấy 2 sách mới nhất ở trang đầu. Dùng API gì?

**Đáp án:** `findByStatus("PUBLISHED", PageRequest.of(0, 2, Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))))`.

**Bài tập 4.** Nếu hai sách có cùng `created_at`, `sort({ created_at: -1 })` có đảm bảo sách nào đứng trước không?

**Đáp án:** Không. Thêm `_id` làm khóa sort phụ nếu cần kết quả xác định.

**Bài tập 5.** Repository dùng `@Field("view_count")` trên `viewCount`. Trong tên method và `Sort` viết tên nào?

**Đáp án:** Dùng `ViewCount` trong `OrderByViewCountDesc` và `"viewCount"` trong `Sort`. Với `mongosh` hoặc index BSON trực tiếp, dùng `view_count`.

**Bài tập 6.** Vì sao không nên lấy chuỗi `sortField` bất kỳ từ HTTP request rồi chuyển thẳng thành `Sort.by(sortField)`?

**Đáp án:** Có thể dẫn đến lỗi property không hợp lệ, truy vấn tốn tài nguyên hoặc thao tác ngoài phạm vi dự kiến. Hãy dùng allowlist các lựa chọn sắp xếp phục vụ nghiệp vụ.

**Kết luận:** Trong Spring Data MongoDB, **`OrderBy` trong tên phương thức** phù hợp với thứ tự cố định, còn **`Sort` động** cho phép thay đổi khóa và hướng sắp khi runtime. `Pageable` kết hợp sort với giới hạn dữ liệu; khóa phụ như `id` giúp thứ tự rõ ràng khi nhiều document bằng nhau trên khóa chính. Khi triển khai, phải đối chiếu tên property Java với field BSON, kiểm soát input, thiết kế index theo bộ lọc và sort thực tế, và kiểm thử kết quả trên MongoDB.
