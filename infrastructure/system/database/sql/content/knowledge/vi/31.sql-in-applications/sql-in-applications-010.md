# Nhận diện truy vấn N+1 và lựa chọn truy vấn theo tập hợp

Một endpoint có thể trả về đúng dữ liệu, dùng prepared statement an toàn và vẫn chậm nghiêm trọng vì ứng dụng phát ra quá nhiều câu SQL nhỏ. Một ví dụ phổ biến: ứng dụng lấy danh sách 100 tác giả bằng một query, sau đó lặp qua từng tác giả và chạy thêm một query để lấy sách của tác giả đó. Kết quả là **1 + 100 = 101 truy vấn** chỉ để tạo một response.

Mẫu này gọi là **N+1 query problem**. Nó thường xuất hiện khi ứng dụng tải một tập cha, rồi truy cập một quan hệ con theo từng phần tử — đặc biệt khi ORM dùng lazy loading. Vấn đề không chỉ là số lần gọi database; mỗi query còn tạo round trip, parse/bind/execute, kiểm tra quyền, lấy connection hoặc dùng cursor, và làm tăng độ trễ tổng.

Cách giải quyết thường là đưa công việc về **truy vấn theo tập hợp (set-based query)**: truyền danh sách khóa một lần, JOIN, aggregate, subquery, window function hoặc kỹ thuật batch/select-in phù hợp. Tuy nhiên, không phải lúc nào một JOIN khổng lồ cũng là câu trả lời. JOIN nhiều collection có thể nhân bản hàng theo tích Descartes, trả payload lớn và làm ORM hydrate quá nhiều object. Lựa chọn đúng phải cân bằng **số query, số hàng trung gian, row width, tính nhất quán, khả năng phân trang và chi phí xử lý phía ứng dụng**.

> **Nguyên tắc:** phát hiện N+1 bằng query trace và số lần thực thi, xác định dữ liệu thực sự cần, sau đó chọn một trong các chiến lược JOIN, IN/ANY, aggregate, subquery, LATERAL/window hoặc batch fetch. Đo cả số query lẫn số hàng/byte và execution plan; đừng tối ưu chỉ bằng cách ép mọi thứ thành một câu SQL.

Bài học thuộc **Database SQL → SQL trong ứng dụng**. Phần thực hành dùng PostgreSQL với các bảng tác giả, sách và đánh giá; minh họa SQL thuần, JDBC, ORM và DataLoader. Nội dung đi qua cách nhận diện N+1, cách viết lại theo tập hợp, các tình huống JOIN gây nhân bản, phân trang cha/con, top-N theo nhóm, consistency giữa nhiều câu query, index, EXPLAIN, kiểm thử query count và 30 bài tập.

## 1. N+1 query problem là gì?

Giả sử API cần trả danh sách tác giả và tên các cuốn sách của mỗi người.

Cách triển khai ngây thơ:

1. Query danh sách tác giả.
2. Với mỗi tác giả, query sách của tác giả ấy.
3. Ghép dữ liệu thành response.

Nếu có N tác giả, tổng số query là:

\[
Q(N) = 1 + N
\]

Ví dụ:

| Số tác giả N | Query lấy tác giả | Query lấy sách từng tác giả | Tổng |
| ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 2 |
| 10 | 1 | 10 | 11 |
| 50 | 1 | 50 | 51 |
| 100 | 1 | 100 | 101 |
| 500 | 1 | 500 | 501 |

Với một tác giả, mẫu này có thể chưa gây chú ý. Khi endpoint trả 100 hoặc 500 tác giả, số round trips tăng tuyến tính theo số hàng cha.

### 1.1. Ví dụ SQL theo từng hàng

Query đầu tiên:

```sql
SELECT author_id, display_name
FROM authors
WHERE tenant_id = $1
ORDER BY author_id
LIMIT $2;
```

Sau đó ứng dụng lặp:

```sql
SELECT book_id, title
FROM books
WHERE tenant_id = $1
  AND author_id = $2
ORDER BY book_id;
```

Câu thứ hai được thực thi lại cho từng `author_id`. Nếu danh sách đầu có 100 tác giả, database nhận một query cha và 100 query con.

### 1.2. Vì sao nhiều query nhỏ có thể chậm?

Mỗi lần gọi database có thể bao gồm:

- Chi phí gửi request qua network.
- Driver/protocol xử lý query và parameters.
- Parse/plan/execute hoặc lấy plan đã cache.
- Xác thực transaction/session state.
- Database tìm hàng và trả kết quả.
- Driver decode kết quả.
- Ứng dụng mapping dữ liệu và ghép object.

Nếu round trip trung bình 4 ms và 101 query tuần tự, chỉ riêng thời gian round trip có thể lên tới hàng trăm mili giây, chưa tính execution và mapping. Nếu mỗi query con mất 2 ms, 100 query con cũng tạo ra một phần độ trễ đáng kể.

Các con số này chỉ minh họa. Trong môi trường thật, network, pool wait, DB load, cache, row count và query plan quyết định chi phí.

### 1.3. N+1 không chỉ có nghĩa “query trong vòng for”

Một số mẫu khác:

- Lấy 100 order, rồi lấy customer riêng cho từng order.
- Lấy 50 user, rồi lấy role/permission của từng user.
- Lấy 100 bài viết, rồi query count comment từng bài.
- Lấy 20 category, rồi query sản phẩm từng category.
- Resolver GraphQL tải một object, sau đó mỗi field resolver lại truy vấn một quan hệ.
- ORM lazy-load một relation khi serializer đọc property.
- Một query lấy trang cha, một query riêng cho từng parent để lấy child count hoặc trạng thái.

Dấu hiệu quan trọng là **cùng một dạng SQL được thực thi nhiều lần với tham số khác nhau trong cùng một request/job**.

### 1.4. N+1 khác với một query chậm

Một câu query phức tạp có thể chậm vì thiếu index, sort lớn, lock hoặc đọc nhiều hàng. N+1 là vấn đề **số lần gọi query tăng theo số phần tử**. Hai vấn đề có thể xuất hiện đồng thời: 100 query con vừa lặp lại, vừa thiếu index.

### 1.5. N+1 khác SQL injection

N+1 là vấn đề hiệu năng và cách truy xuất dữ liệu. SQL injection là vấn đề ranh giới code/data. Một câu SQL được parameterize an toàn vẫn có thể bị gọi 501 lần. Một query set-based cũng vẫn phải dùng binding/validation và kiểm quyền đúng.

## 2. Tạo bộ dữ liệu PostgreSQL để thực hành

Chạy trong một session PostgreSQL lab. Các bảng `TEMP` tồn tại trong session tạo chúng. Nếu thực thi từ JDBC/ORM ở connection khác, hãy tạo dữ liệu trong chính connection đó hoặc dùng schema lab riêng.

```sql
CREATE TEMP TABLE demo_authors (
    tenant_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    country_code TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, author_id)
);

CREATE TEMP TABLE demo_books (
    tenant_id INTEGER NOT NULL,
    book_id BIGINT NOT NULL,
    author_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('PUBLISHED', 'DRAFT', 'ARCHIVED')
    ),
    published_at TIMESTAMPTZ,
    price NUMERIC(10,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, book_id),
    FOREIGN KEY (tenant_id, author_id)
        REFERENCES demo_authors (tenant_id, author_id)
);

CREATE TEMP TABLE demo_reviews (
    tenant_id INTEGER NOT NULL,
    review_id BIGINT NOT NULL,
    book_id BIGINT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, review_id),
    FOREIGN KEY (tenant_id, book_id)
        REFERENCES demo_books (tenant_id, book_id)
);

INSERT INTO demo_authors
    (tenant_id, author_id, display_name, country_code, created_at)
VALUES
    (10, 1, 'An', 'VN', '2026-10-01 08:00:00+07'),
    (10, 2, 'Bình', 'VN', '2026-10-02 08:00:00+07'),
    (10, 3, 'Chi', 'SG', '2026-10-03 08:00:00+07'),
    (10, 4, 'Dũng', 'VN', '2026-10-04 08:00:00+07'),
    (10, 5, 'Hà', 'US', '2026-10-05 08:00:00+07'),
    (20, 1, 'An tenant 20', 'US', '2026-10-01 08:00:00+07');

INSERT INTO demo_books
    (tenant_id, book_id, author_id, title, status, published_at, price)
VALUES
    (10, 101, 1, 'SQL nhập môn', 'PUBLISHED', '2026-01-01 08:00:00+07', 20.00),
    (10, 102, 1, 'SQL thực hành', 'PUBLISHED', '2026-02-01 08:00:00+07', 30.00),
    (10, 103, 1, 'SQL bản nháp', 'DRAFT', NULL, 0.00),
    (10, 104, 2, 'Java cơ bản', 'PUBLISHED', '2026-03-01 08:00:00+07', 25.00),
    (10, 105, 2, 'Java nâng cao', 'PUBLISHED', '2026-04-01 08:00:00+07', 40.00),
    (10, 106, 3, 'Thiết kế dữ liệu', 'PUBLISHED', '2026-05-01 08:00:00+07', 35.00),
    (10, 107, 4, 'Bản thảo riêng', 'DRAFT', NULL, 0.00),
    (10, 108, 4, 'Sách lưu trữ', 'ARCHIVED', '2025-01-01 08:00:00+07', 10.00),
    (20, 201, 1, 'Sách tenant 20', 'PUBLISHED', '2026-06-01 08:00:00+07', 99.00);

INSERT INTO demo_reviews
    (tenant_id, review_id, book_id, rating, review_text, created_at)
VALUES
    (10, 1001, 101, 5, 'Rất tốt', '2026-06-01 08:00:00+07'),
    (10, 1002, 101, 4, 'Dễ hiểu', '2026-06-02 08:00:00+07'),
    (10, 1003, 102, 5, 'Có ví dụ', '2026-06-03 08:00:00+07'),
    (10, 1004, 104, 3, 'Ổn', '2026-06-04 08:00:00+07'),
    (10, 1005, 105, 5, 'Tốt', '2026-06-05 08:00:00+07'),
    (10, 1006, 106, 4, 'Hữu ích', '2026-06-06 08:00:00+07'),
    (20, 2001, 201, 5, 'Tenant riêng', '2026-06-07 08:00:00+07');
```

Tác giả 5 chưa có sách. Tác giả 4 chỉ có sách draft/archive, không có sách published. Tenant 20 có author_id trùng 1 với tenant 10, giúp thấy vì sao khóa và điều kiện tenant phải được dùng nhất quán.

Kiểm tra:

```sql
SELECT tenant_id, COUNT(*) AS author_count
FROM demo_authors
GROUP BY tenant_id
ORDER BY tenant_id;

SELECT tenant_id, author_id, COUNT(*) AS book_count
FROM demo_books
GROUP BY tenant_id, author_id
ORDER BY tenant_id, author_id;
```

## 3. Tái hiện N+1 trong ứng dụng

### 3.1. Mẫu SQL thuần

Query cha:

```sql
SELECT author_id, display_name
FROM demo_authors
WHERE tenant_id = 10
ORDER BY author_id;
```

Kết quả có 5 tác giả. Sau đó ứng dụng gọi query con 5 lần:

```sql
SELECT book_id, title, status
FROM demo_books
WHERE tenant_id = 10
  AND author_id = 1
ORDER BY book_id;

SELECT book_id, title, status
FROM demo_books
WHERE tenant_id = 10
  AND author_id = 2
ORDER BY book_id;

SELECT book_id, title, status
FROM demo_books
WHERE tenant_id = 10
  AND author_id = 3
ORDER BY book_id;

SELECT book_id, title, status
FROM demo_books
WHERE tenant_id = 10
  AND author_id = 4
ORDER BY book_id;

SELECT book_id, title, status
FROM demo_books
WHERE tenant_id = 10
  AND author_id = 5
ORDER BY book_id;
```

Với N=5, tổng là 6 query. Nếu danh sách tăng lên 100 tác giả, code vẫn giữ một query cha và tạo 100 query con.

### 3.2. Ví dụ JDBC

```java
String authorSql = """
    SELECT author_id, display_name
    FROM demo_authors
    WHERE tenant_id = ?
    ORDER BY author_id
    """;

String bookSql = """
    SELECT book_id, title, status
    FROM demo_books
    WHERE tenant_id = ?
      AND author_id = ?
    ORDER BY book_id
    """;

List<AuthorDto> authors = new ArrayList<>();

try (PreparedStatement authorPs = conn.prepareStatement(authorSql);
     PreparedStatement bookPs = conn.prepareStatement(bookSql)) {

    authorPs.setInt(1, tenantId);

    try (ResultSet authorRs = authorPs.executeQuery()) {
        while (authorRs.next()) {
            int authorId = authorRs.getInt("author_id");
            String name = authorRs.getString("display_name");

            List<BookDto> books = new ArrayList<>();
            bookPs.setInt(1, tenantId);
            bookPs.setInt(2, authorId);

            try (ResultSet bookRs = bookPs.executeQuery()) {
                while (bookRs.next()) {
                    books.add(new BookDto(
                        bookRs.getLong("book_id"),
                        bookRs.getString("title"),
                        bookRs.getString("status")
                    ));
                }
            }

            authors.add(new AuthorDto(authorId, name, books));
        }
    }
}
```

PreparedStatement được tái sử dụng, nhưng `executeQuery()` cho sách vẫn chạy một lần trên mỗi tác giả. **Tái sử dụng statement không xóa N+1**. Số lần database execute vẫn là 1+N.

### 3.3. N+1 ẩn trong ORM lazy loading

Ví dụ JPA entity:

```java
@Entity
class Author {
    @Id
    private Long id;

    private String displayName;

    @OneToMany(mappedBy = "author", fetch = FetchType.LAZY)
    private List<Book> books;
}
```

Service:

```java
List<Author> authors = authorRepository.findByTenantId(tenantId);

for (Author author : authors) {
    // Truy cập collection lazy có thể phát một SELECT riêng.
    int bookCount = author.getBooks().size();
    render(author, bookCount);
}
```

Query lấy danh sách author chỉ chạy một lần. Khi gọi `getBooks()` cho từng author, ORM có thể phát N query. Serializer cũng có thể kích hoạt lazy load nếu nó duyệt relation sau khi service trả entity.

**Không phải mọi `LAZY` đều là lỗi**. Lazy loading giúp tránh tải quan hệ không cần thiết. N+1 xuất hiện khi ứng dụng truy cập quan hệ lazy theo từng parent trong một vòng lặp hoặc trong serialization.

### 3.4. EAGER cũng không đảm bảo hết N+1

Đặt relation `EAGER` không phải lúc nào cũng buộc ORM dùng một JOIN duy nhất. ORM có thể chạy query cha rồi truy vấn phụ để nạp quan hệ. Kết quả tùy ORM, query shape và loại quan hệ. Phải xem SQL thật được phát ra, không suy luận chỉ từ annotation.

## 4. Nhận diện N+1 bằng bằng chứng

### 4.1. Query count theo request

Đếm số câu SQL của một request là tín hiệu đầu tiên. Một request lấy 20 author mà phát:
- 1 query author.
- 20 query book.
- 20 query review count.

Tổng có thể là 41 query. Cần xác định fingerprint của query lặp lại và các tham số khác nhau.

### 4.2. SQL log và query fingerprint

Một dấu hiệu điển hình trong log:

```text
SELECT ... FROM demo_authors WHERE tenant_id = $1
SELECT ... FROM demo_books WHERE tenant_id = $1 AND author_id = $2
SELECT ... FROM demo_books WHERE tenant_id = $1 AND author_id = $2
SELECT ... FROM demo_books WHERE tenant_id = $1 AND author_id = $2
...
```

Nếu cùng một cấu trúc query xuất hiện nhiều lần trong một trace với giá trị `$2` khác nhau, có thể là N+1. Query fingerprint giúp nhóm các câu SQL tương tự dù giá trị bind khác nhau.

Không log toàn bộ PII hoặc payload chỉ để phát hiện N+1. Có thể ghi:
- Request/trace ID.
- Query fingerprint hoặc normalized SQL.
- Số lần execute.
- Thời gian từng query và tổng DB time.
- Rows returned.
- Pool wait.
- ORM entity/collection fetch statistics nếu có.

### 4.3. Query count phải gắn với một request hoặc operation

Đếm tổng query của cả server trong một phút không đủ để xác định request nào gây N+1. Cần trace/span hoặc context theo request/job để biết query nào thuộc operation nào.

### 4.4. Một query lặp lại chưa chắc là N+1

Một job có thể cố ý xử lý từng item độc lập do cần gọi API ngoài hoặc logic tuần tự. Cũng có thể một query được gọi nhiều lần từ các request khác nhau. Dấu hiệu N+1 rõ hơn khi:
- Có một query lấy tập parent.
- Sau đó có một query shape lặp lại theo từng parent.
- Số lần query con tăng tương ứng với số parent.
- Dữ liệu con có thể được lấy theo tập hợp hoặc batch.
- Nhiều lần gọi có cùng mục đích và có thể hợp nhất.

### 4.5. N+1 theo chiều sâu

Ví dụ:
- 1 query authors.
- N query books.
- M query reviews cho từng book.

Nếu tổng số book là M, tổng query có thể là `1 + N + M`. Đây là N+1 lồng nhau, đôi khi được gọi là N+1 nhiều tầng.

## 5. Viết lại bằng LEFT JOIN

Nếu response cần authors cùng danh sách books, có thể lấy bằng một JOIN:

```sql
SELECT
    a.author_id,
    a.display_name,
    b.book_id,
    b.title,
    b.status
FROM demo_authors AS a
LEFT JOIN demo_books AS b
    ON b.tenant_id = a.tenant_id
   AND b.author_id = a.author_id
WHERE a.tenant_id = $1
ORDER BY a.author_id, b.book_id;
```

`LEFT JOIN` giữ cả tác giả không có sách. Với tenant 10:
- Author 1 có ba sách.
- Author 2 có hai sách.
- Author 3 có một sách.
- Author 4 có hai sách.
- Author 5 có một hàng kết quả với các cột `b.*` là SQL NULL.

Nếu dùng `INNER JOIN`, author 5 không xuất hiện; đó là thay đổi semantics nếu API cần trả cả tác giả không có sách.

### 5.1. Ghép hàng JOIN thành object cha/con

Một JOIN trả kết quả dạng phẳng. Parent lặp lại trên từng child. Ứng dụng cần gom nhóm theo khóa cha:

```text
Map<AuthorId, AuthorDto>

for each row:
    author = map.getOrCreate(author_id, display_name)

    if book_id is not NULL:
        author.books.add(book_id, title, status)
```

Không tạo AuthorDto mới cho mỗi hàng JOIN, nếu không tác giả có ba sách sẽ xuất hiện ba lần.

### 5.2. Kiểm khóa NULL để phân biệt parent không có child

Với LEFT JOIN, nếu `book_id` là khóa NOT NULL của bảng con:
- `book_id IS NULL`: không có hàng book khớp.
- `book_id IS NOT NULL`: có một book.

Không dùng `title IS NULL` nếu title có thể NULL hoặc không phải khóa đảm bảo tồn tại.

### 5.3. Điều kiện lọc child đặt ở ON hay WHERE?

Muốn lấy tất cả tác giả và chỉ các sách đã publish:

```sql
SELECT
    a.author_id,
    a.display_name,
    b.book_id,
    b.title
FROM demo_authors AS a
LEFT JOIN demo_books AS b
    ON b.tenant_id = a.tenant_id
   AND b.author_id = a.author_id
   AND b.status = 'PUBLISHED'
WHERE a.tenant_id = $1
ORDER BY a.author_id, b.book_id;
```

Điều kiện `b.status` ở `ON` giữ các tác giả không có sách published.

Nếu viết:

```sql
WHERE a.tenant_id = $1
  AND b.status = 'PUBLISHED'
```

thì những hàng `b.*` là NULL bị loại; LEFT JOIN có hiệu quả gần như INNER JOIN cho predicate ấy. Đặt predicate đúng vị trí theo contract.

### 5.4. Tenant phải nằm trong điều kiện JOIN

Vì `author_id` chỉ unique trong tenant, điều kiện:

```sql
ON b.author_id = a.author_id
```

là chưa đủ nếu có dữ liệu nhiều tenant. Dùng cả tenant và author key:

```sql
ON b.tenant_id = a.tenant_id
AND b.author_id = a.author_id
```

Cần kiểm quyền tenant ở query cha và mọi query batch/child khác.

## 6. Lấy child theo tập hợp bằng IN

Một cách khác là hai query cố định, không phải N query:

Query 1 lấy parent:

```sql
SELECT author_id, display_name
FROM demo_authors
WHERE tenant_id = $1
ORDER BY author_id;
```

Ứng dụng thu danh sách `author_id`, rồi query 2 lấy tất cả sách của các author ấy:

```sql
SELECT author_id, book_id, title, status
FROM demo_books
WHERE tenant_id = $1
  AND author_id = ANY($2::integer[])
ORDER BY author_id, book_id;
```

Với PostgreSQL, `ANY(integer[])` nhận một array bind. Ứng dụng gom sách theo `author_id` trong memory rồi gắn vào parent.

### 6.1. Ví dụ kết quả theo nhóm

Query cha:

| author_id | display_name |
| ---: | --- |
| 1 | An |
| 2 | Bình |
| 3 | Chi |
| 4 | Dũng |
| 5 | Hà |

Query con theo tập hợp:

| author_id | book_id | title |
| ---: | ---: | --- |
| 1 | 101 | SQL nhập môn |
| 1 | 102 | SQL thực hành |
| 1 | 103 | SQL bản nháp |
| 2 | 104 | Java cơ bản |
| 2 | 105 | Java nâng cao |
| 3 | 106 | Thiết kế dữ liệu |
| 4 | 107 | Bản thảo riêng |
| 4 | 108 | Sách lưu trữ |

Author 5 không có dòng child, nhưng vẫn giữ trong danh sách cha nếu ứng dụng khởi tạo map/list từ query đầu.

### 6.2. Vì sao IN/ANY thường phù hợp?

- Query con chỉ chạy một lần cho cả tập parent.
- Kết quả child không lặp lại thông tin parent trên từng hàng.
- Dễ thêm projection chỉ lấy cột cần.
- Dễ nhóm trong ứng dụng.
- Có thể phân trang parent độc lập trước khi lấy child.

### 6.3. Danh sách rỗng

Nếu parent query trả không hàng, không cần query child. Ứng dụng trả danh sách rỗng ngay. Với PostgreSQL, `ANY(ARRAY[]::integer[])` không khớp hàng, nhưng nên xử lý nhánh rỗng rõ ở application để tránh phụ thuộc cú pháp array của từng DBMS.

### 6.4. Danh sách rất lớn

Một `IN` có hàng chục nghìn hoặc hàng trăm nghìn khóa có thể làm query text/parameters lớn, planner tốn công và driver gặp giới hạn. Với tập lớn:
- Chia thành batch có giới hạn.
- Dùng array/table-valued parameter tùy DBMS.
- Dùng temporary/staging table.
- Dùng `JOIN` tới bảng khóa đã nạp.
- Hoặc thiết kế query trực tiếp trên tập cha thay vì gửi ID vòng lại.

Batching giảm số query so với N+1 nhưng có thể vẫn cần nhiều batch. Đó là tradeoff có chủ đích.

## 7. JOIN hay IN/select-in: chọn theo hình dạng kết quả

| Tình huống | JOIN | IN/select-in |
| --- | --- | --- |
| Một parent có một child (many-to-one/one-to-one) | Thường rất phù hợp | Có thể phù hợp nhưng thường thêm query |
| Parent có collection nhỏ | Có thể tốt, một round trip | Tốt, hai query và dễ nhóm |
| Parent có collection lớn | Có thể trả nhiều hàng lặp parent | Có thể kiểm soát child rows rõ hơn |
| Nhiều collection cùng lúc | Dễ Cartesian explosion | Thường tránh nhân chéo |
| Cần phân trang parent | Cần cẩn thận không limit joined rows | Dễ lấy page cha rồi batch child |
| Cần snapshot một statement | Một JOIN là một statement | Nhiều statement, cần xét isolation |
| Cần DTO tổng hợp | JOIN/aggregate có thể hiệu quả | Có thể ghép trong app |

Không có một quy tắc “JOIN luôn tốt hơn hai query”. Mục tiêu là giảm round trips **mà không tạo ra quá nhiều hàng trung gian hoặc payload trùng lặp**.

## 8. N+1 khi lấy count hoặc aggregate cho từng parent

Ví dụ endpoint muốn hiển thị mỗi author có bao nhiêu sách published.

N+1:

```sql
SELECT author_id, display_name
FROM demo_authors
WHERE tenant_id = $1;
```

Rồi mỗi author:

```sql
SELECT COUNT(*)
FROM demo_books
WHERE tenant_id = $1
  AND author_id = $2
  AND status = 'PUBLISHED';
```

Thay bằng một aggregate:

```sql
SELECT
    a.author_id,
    a.display_name,
    COUNT(b.book_id) AS published_book_count
FROM demo_authors AS a
LEFT JOIN demo_books AS b
    ON b.tenant_id = a.tenant_id
   AND b.author_id = a.author_id
   AND b.status = 'PUBLISHED'
WHERE a.tenant_id = $1
GROUP BY a.tenant_id, a.author_id, a.display_name
ORDER BY a.author_id;
```

### 8.1. COUNT(*) và COUNT(child_key) khác nhau trong LEFT JOIN

Với author không có book published:
- LEFT JOIN vẫn tạo một hàng parent với cột child NULL.
- `COUNT(*)` đếm hàng nối này thành 1.
- `COUNT(b.book_id)` bỏ giá trị NULL, cho 0.

Vì thế, khi đếm child trên LEFT JOIN, thường dùng `COUNT(child.primary_key)` hoặc cột child chắc chắn NOT NULL.

### 8.2. Aggregate độc lập trước khi JOIN

Nếu cần count/sum trên nhiều quan hệ, có thể aggregate child trước:

```sql
SELECT
    a.author_id,
    a.display_name,
    COALESCE(x.published_book_count, 0) AS published_book_count,
    COALESCE(x.total_published_price, 0) AS total_published_price
FROM demo_authors AS a
LEFT JOIN (
    SELECT
        tenant_id,
        author_id,
        COUNT(*) AS published_book_count,
        SUM(price) AS total_published_price
    FROM demo_books
    WHERE status = 'PUBLISHED'
    GROUP BY tenant_id, author_id
) AS x
    ON x.tenant_id = a.tenant_id
   AND x.author_id = a.author_id
WHERE a.tenant_id = $1
ORDER BY a.author_id;
```

Đây là cách tránh việc JOIN nhiều bảng detail rồi vô tình nhân bản số lượng trước khi aggregate.

## 9. Correlated subquery và LATERAL

Không phải mọi truy vấn liên quan parent/child đều cần kéo child rows về ứng dụng.

### 9.1. Scalar correlated subquery

```sql
SELECT
    a.author_id,
    a.display_name,
    (
        SELECT COUNT(*)
        FROM demo_books AS b
        WHERE b.tenant_id = a.tenant_id
          AND b.author_id = a.author_id
          AND b.status = 'PUBLISHED'
    ) AS published_book_count
FROM demo_authors AS a
WHERE a.tenant_id = $1
ORDER BY a.author_id;
```

Đây là một SQL statement. Optimizer có thể biến đổi/triển khai subquery theo nhiều cách; không suy luận rằng nó chắc chắn thực thi một truy vấn con độc lập cho mỗi hàng như N+1 ở application. Hãy xem execution plan.

### 9.2. LATERAL cho top-N child mỗi parent

Giả sử API cần ba sách mới nhất của mỗi tác giả:

```sql
SELECT
    a.author_id,
    a.display_name,
    b.book_id,
    b.title,
    b.published_at
FROM demo_authors AS a
LEFT JOIN LATERAL (
    SELECT book_id, title, published_at
    FROM demo_books AS b
    WHERE b.tenant_id = a.tenant_id
      AND b.author_id = a.author_id
      AND b.status = 'PUBLISHED'
    ORDER BY b.published_at DESC, b.book_id DESC
    LIMIT 3
) AS b ON TRUE
WHERE a.tenant_id = $1
ORDER BY a.author_id, b.published_at DESC, b.book_id DESC;
```

`LATERAL` cho phép subquery tham chiếu hàng hiện tại của `a`. Đây vẫn là **một statement SQL**, nhưng plan bên trong có thể dùng nested loop/index scan hoặc cách khác. Tính hiệu quả phụ thuộc số parent, index và giới hạn top-N.

### 9.3. LATERAL không phải phép màu

Nếu parent có hàng triệu hàng hoặc mỗi lateral subquery phải scan/sort rất nhiều child, query vẫn đắt. Cần index như `(tenant_id, author_id, status, published_at DESC, book_id DESC)` phù hợp với filter/order và xem EXPLAIN.

## 10. Window function cho top-N mỗi nhóm

Một cách khác là đánh số child theo từng author rồi lọc:

```sql
WITH ranked_books AS (
    SELECT
        b.tenant_id,
        b.author_id,
        b.book_id,
        b.title,
        b.published_at,
        ROW_NUMBER() OVER (
            PARTITION BY b.tenant_id, b.author_id
            ORDER BY b.published_at DESC, b.book_id DESC
        ) AS rn
    FROM demo_books AS b
    WHERE b.tenant_id = $1
      AND b.status = 'PUBLISHED'
)
SELECT
    a.author_id,
    a.display_name,
    rb.book_id,
    rb.title,
    rb.published_at
FROM demo_authors AS a
LEFT JOIN ranked_books AS rb
    ON rb.tenant_id = a.tenant_id
   AND rb.author_id = a.author_id
   AND rb.rn <= 3
WHERE a.tenant_id = $1
ORDER BY a.author_id, rb.rn;
```

`ROW_NUMBER()` reset theo từng partition author. Dùng `rn <= 3` trong điều kiện JOIN để giữ tác giả không có sách; nếu đặt điều kiện ở WHERE, parent có thể bị loại.

### 10.1. ROW_NUMBER, RANK và DENSE_RANK

- `ROW_NUMBER`: luôn đánh số riêng từng hàng, kể cả giá trị sort bằng nhau.
- `RANK`: hàng đồng hạng có cùng rank và có khoảng nhảy tiếp theo.
- `DENSE_RANK`: hàng đồng hạng có cùng rank, rank kế tiếp không bị nhảy.

Nếu contract là **tối đa đúng 3 hàng mỗi author**, `ROW_NUMBER() <= 3` phù hợp. Nếu contract là “lấy tất cả hàng thuộc top 3 mức giá trị và cho phép nhiều hơn 3 hàng khi hòa”, cân nhắc `RANK`/`DENSE_RANK`.

### 10.2. Top-N per group có thể dùng LATERAL hoặc window

| Cách | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| LATERAL + LIMIT | Dễ diễn đạt top-N cho mỗi parent, có thể tận dụng index theo parent | Có thể lặp index scan theo từng parent trong plan |
| Window + ROW_NUMBER | Một luồng xử lý set-based, tiện nhiều phép xếp hạng | Có thể phải xử lý/sort toàn bộ tập child phù hợp |
| IN/select-in rồi lọc ở app | Dễ code nếu dữ liệu nhỏ | Tải quá nhiều child, app phải sort/filter |
| N query cho từng parent | Dễ viết | Round trips tăng theo N |

Chọn theo cardinality và plan thực tế.

## 11. JSON aggregation để trả cấu trúc lồng nhau

PostgreSQL có thể tạo JSON cho từng author và danh sách sách:

```sql
SELECT
    a.author_id,
    a.display_name,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'bookId', b.book_id,
                'title', b.title,
                'status', b.status
            )
            ORDER BY b.book_id
        ) FILTER (WHERE b.book_id IS NOT NULL),
        '[]'::jsonb
    ) AS books
FROM demo_authors AS a
LEFT JOIN demo_books AS b
    ON b.tenant_id = a.tenant_id
   AND b.author_id = a.author_id
WHERE a.tenant_id = $1
GROUP BY a.tenant_id, a.author_id, a.display_name
ORDER BY a.author_id;
```

Kết quả mỗi author là một hàng, field `books` chứa JSON array. Tác giả không có sách nhận `[]`.

### 11.1. FILTER tránh object toàn NULL

Nếu không lọc hàng LEFT JOIN không có child, `jsonb_agg(jsonb_build_object(...))` có thể tạo một object với các field null. `FILTER (WHERE b.book_id IS NOT NULL)` bỏ hàng placeholder của LEFT JOIN.

### 11.2. JSON aggregation giảm số hàng SQL nhưng có thể tăng row width

Một hàng có JSON array rất lớn vẫn có thể chiếm nhiều RAM và network. Nếu một author có hàng triệu sách, gom tất cả vào một JSONB value có thể tốn tài nguyên đáng kể. Số hàng trả về nhỏ **không đồng nghĩa payload nhỏ**.

Dùng JSON aggregation khi collection có kích thước kiểm soát hoặc API thực sự cần JSON document lồng nhau. Với export lớn, streaming rows hoặc batch thường phù hợp hơn.

## 12. JOIN nhiều collection và Cartesian explosion

Đây là lý do quan trọng để không biến mọi N+1 thành một JOIN duy nhất.

Giả sử mỗi author có:
- 10 books.
- 8 awards.

Nếu JOIN đồng thời hai collection:

```sql
SELECT
    a.author_id,
    b.book_id,
    aw.award_id
FROM demo_authors AS a
LEFT JOIN demo_books AS b
    ON b.tenant_id = a.tenant_id
   AND b.author_id = a.author_id
LEFT JOIN demo_author_awards AS aw
    ON aw.tenant_id = a.tenant_id
   AND aw.author_id = a.author_id
WHERE a.tenant_id = $1;
```

Một author có 10 books và 8 awards có thể tạo **10 × 8 = 80 hàng**. Book lặp lại 8 lần, award lặp lại 10 lần. Với nhiều collection, số hàng trung gian có thể phình theo tích cardinality.

### 12.1. Tác động của Cartesian multiplication

- Dữ liệu parent/child lặp nhiều lần.
- Network payload tăng.
- ORM phải de-duplicate object.
- Aggregate có thể bị sai nếu count/sum sau JOIN trực tiếp.
- Sort/hash và memory database tăng.
- Response mapping phức tạp.

### 12.2. Giải pháp: aggregate riêng từng collection

```sql
WITH book_summary AS (
    SELECT
        tenant_id,
        author_id,
        COUNT(*) AS book_count
    FROM demo_books
    GROUP BY tenant_id, author_id
),
award_summary AS (
    SELECT
        tenant_id,
        author_id,
        COUNT(*) AS award_count
    FROM demo_author_awards
    GROUP BY tenant_id, author_id
)
SELECT
    a.author_id,
    a.display_name,
    COALESCE(bs.book_count, 0) AS book_count,
    COALESCE(aw.award_count, 0) AS award_count
FROM demo_authors AS a
LEFT JOIN book_summary AS bs
    ON bs.tenant_id = a.tenant_id
   AND bs.author_id = a.author_id
LEFT JOIN award_summary AS aw
    ON aw.tenant_id = a.tenant_id
   AND aw.author_id = a.author_id
WHERE a.tenant_id = $1
ORDER BY a.author_id;
```

Mỗi collection được aggregate trước khi JOIN, tránh nhân chéo hàng detail.

### 12.3. Giải pháp: select-in cho từng collection

Một query lấy authors, một query lấy books theo author IDs, một query lấy awards theo author IDs. Tổng cộng 3 query cố định theo batch, không phải 1+N+N. Ứng dụng nhóm từng tập riêng.

Đây thường là lựa chọn rõ ràng khi response cần nhiều collection độc lập.

### 12.4. ORM có thể gọi hiện tượng này là multiple bag fetch

Một số ORM có giới hạn khi fetch join nhiều collection cùng lúc, hoặc tạo Cartesian explosion. Thay vì cố ép ORM JOIN tất cả, dùng projection, batch fetch hoặc split/select-in query tùy framework.

## 13. Batch fetching: giảm N+1 thành 1 + số batch

Nếu có 1.000 parent và batch size 100:
- Query cha: 1.
- Query child: 10 batch.
- Tổng: 11 thay vì 1.001.

Batch fetch không nhất thiết chỉ có một query, nhưng giới hạn số query theo số batch thay vì số parent.

### 13.1. PostgreSQL với ANY array

```sql
SELECT author_id, book_id, title
FROM demo_books
WHERE tenant_id = $1
  AND author_id = ANY($2::integer[])
ORDER BY author_id, book_id;
```

Ứng dụng chia author IDs thành các nhóm tối đa 500 hoặc 1.000 tùy workload. Mỗi nhóm chạy một query. Kích thước batch phải đo theo giới hạn parameter, row count và payload.

### 13.2. Batch fetch của ORM

Hibernate có các cơ chế như `@BatchSize` hoặc `hibernate.default_batch_fetch_size` để gom lazy loads theo nhóm tùy mapping/query. Khi ứng dụng truy cập relation của một entity, ORM có thể tải một nhóm khóa thay vì một query cho mỗi entity.

Ví dụ ý tưởng:

```java
@OneToMany(mappedBy = "author", fetch = FetchType.LAZY)
@BatchSize(size = 50)
private List<Book> books;
```

Cú pháp/hiệu lực phụ thuộc phiên bản Hibernate và mapping. Batch fetch giảm N+1 nhưng không nhất thiết biến thành một query duy nhất. Phải quan sát SQL thật và số batch.

### 13.3. Subselect fetching

Một số ORM hỗ trợ lấy collection của nhiều parent trong một truy vấn con dựa trên tập parent đã được tải trước. Điều này có thể giảm số query, nhưng phụ thuộc query ban đầu, session state và framework. Cần đo với đúng use case.

### 13.4. Batch size quá lớn cũng có chi phí

Một batch lớn có thể:
- Tạo `IN` list/array rất lớn.
- Trả quá nhiều child.
- Tăng heap và thời gian mapping.
- Làm query plan kém.
- Tạo một request DB quá nặng.

Batch size phải phù hợp với phân bố child per parent, không chỉ số parent.

## 14. Lựa chọn fetch strategy trong ORM

### 14.1. JPA/Hibernate: JOIN FETCH

Nếu một endpoint luôn cần author và books, có thể viết query:

```java
@Query("""
    select distinct a
    from Author a
    left join fetch a.books
    where a.tenantId = :tenantId
    order by a.id
    """)
List<Author> findAuthorsWithBooks(@Param("tenantId") int tenantId);
```

`JOIN FETCH` yêu cầu ORM tải quan hệ trong query. `distinct` có thể giúp loại parent trùng trong kết quả entity ở một số cách xử lý, nhưng SQL vẫn có thể trả nhiều hàng do collection. Hiệu quả và cú pháp phụ thuộc JPA provider/version.

**Không fetch join collection lớn với pagination một cách thiếu kiểm soát.** ORM có thể phải lấy nhiều hàng và phân trang trong memory, cảnh báo hoặc tạo kết quả không như mong muốn tùy provider. Nên phân trang parent trước, rồi batch collection.

### 14.2. EntityGraph

JPA EntityGraph có thể khai báo quan hệ cần tải cho một use case mà không đặt tất cả quan hệ thành EAGER toàn cục. Nhưng provider có thể thực thi bằng JOIN hoặc query bổ sung. EntityGraph là mô tả fetch plan, không bảo đảm số SQL cụ thể.

### 14.3. DTO projection

Nếu endpoint chỉ cần `author_id`, `display_name`, `book_count`, hãy query projection DTO thay vì hydrate entity graph:

```java
public record AuthorSummary(
    Integer authorId,
    String displayName,
    Long publishedBookCount
) {}
```

SQL aggregate ở mục 8 có thể map thẳng vào DTO. Cách này tránh tải collection nếu API chỉ cần count.

### 14.4. Hibernate statistics và SQL logging

Có thể bật statistics trong môi trường phù hợp để xem:
- Query executions.
- Entity fetch/load.
- Collection fetch/load.
- Second-level cache hits/misses.
- Session metrics.

SQL logging giúp thấy pattern lặp lại, nhưng log giá trị nhạy cảm phải được kiểm soát. Đừng bật verbose parameter logging ở production mà không cân nhắc PII/secret.

### 14.5. Django: select_related và prefetch_related

Django ORM:
- `select_related()` thường dùng JOIN cho quan hệ ForeignKey/OneToOne.
- `prefetch_related()` thường chạy query riêng cho tập liên quan rồi ghép ở Python, phù hợp nhiều quan hệ collection.

Ví dụ:

```python
authors = (
    Author.objects
    .filter(tenant_id=tenant_id)
    .prefetch_related("books")
)
```

Đây thường là một query authors và một query books cho tập authors, thay vì một query sách mỗi author. `select_related("profile")` phù hợp cho quan hệ đơn. Hãy kiểm SQL và số query theo version/query cụ thể.

### 14.6. SQLAlchemy: joinedload và selectinload

SQLAlchemy có:
- `joinedload()` để eager-load bằng JOIN.
- `selectinload()` để tải relation bằng một hoặc nhiều query `IN` theo nhóm khóa.

Ví dụ:

```python
stmt = (
    select(Author)
    .where(Author.tenant_id == tenant_id)
    .options(selectinload(Author.books))
)
authors = session.scalars(stmt).all()
```

`selectinload` thường là chiến lược hữu ích cho collection vì tránh nhân parent rows trong kết quả chính. Với nhiều parent hoặc giới hạn bind parameters, ORM có thể chia batch. Kiểm query thật.

### 14.7. Entity Framework Core: Include và split query

EF Core có `Include` để tải navigation properties. Với nhiều collection, một query JOIN có thể gây Cartesian explosion; `AsSplitQuery()` cho phép chia thành nhiều query theo cơ chế framework. Split query giảm nhân chéo nhưng có nhiều round trips và có thể thấy dữ liệu khác nhau giữa các statement nếu không dùng isolation phù hợp.

### 14.8. Không đặt EAGER mặc định cho mọi relation

Một quan hệ chỉ cần ở một số màn hình nên được tải theo use case. EAGER toàn cục có thể khiến những endpoint không cần dữ liệu ấy vẫn đọc nhiều hàng. Hãy chọn fetch plan theo nhu cầu thực tế.

## 15. GraphQL DataLoader và batch resolver

N+1 thường xuất hiện trong GraphQL khi resolver cho mỗi parent gọi repository riêng:

```text
Query.authors
  -> trả N author
  -> Author.books resolver chạy N lần
  -> mỗi lần query books WHERE author_id = ?
```

Một giải pháp là **DataLoader**: gom các khóa được yêu cầu trong một tick/batch rồi query một lần bằng IN/ANY, sau đó trả kết quả theo thứ tự key ban đầu.

Mô hình:

```text
Resolver author 1 -> loader.load(1)
Resolver author 2 -> loader.load(2)
Resolver author 3 -> loader.load(3)
                 |
                 v
          DataLoader collects [1,2,3]
                 |
                 v
     SELECT ... WHERE author_id = ANY(...)
                 |
                 v
       Map results by author_id
                 |
                 v
        Resolve each Promise by key
```

### 15.1. DataLoader phải giữ đúng thứ tự kết quả

Batch function nhận danh sách keys và cần trả một phần tử tương ứng **cho từng key theo cùng thứ tự**, kể cả key không có child. SQL `IN` không đảm bảo thứ tự bằng thứ tự input. Phải group/map rồi dựng array theo keys.

### 15.2. DataLoader cache có scope

Cache của DataLoader thường nên giới hạn theo request để không trộn dữ liệu/quyền giữa user/tenant hoặc giữ dữ liệu stale lâu. Nếu dùng global cache, phải thiết kế key, tenant, authorization và invalidation rõ ràng.

### 15.3. Batch limit

Nếu GraphQL query yêu cầu hàng chục nghìn parent, DataLoader cần giới hạn kích thước batch hoặc page. Batch query một lần cho 100.000 keys không tự nhiên là tối ưu.

## 16. Phân trang cha trước, rồi tải con theo tập hợp

Một lỗi phổ biến là JOIN parent/child rồi áp `LIMIT 20` lên kết quả phẳng:

```sql
SELECT a.author_id, a.display_name, b.book_id, b.title
FROM demo_authors AS a
LEFT JOIN demo_books AS b
    ON b.tenant_id = a.tenant_id
   AND b.author_id = a.author_id
WHERE a.tenant_id = $1
ORDER BY a.author_id, b.book_id
LIMIT 20;
```

LIMIT ở đây giới hạn **20 hàng JOIN**, không phải 20 authors. Nếu author đầu có nhiều books, trang có thể chỉ chứa một vài author.

### 16.1. Lấy page parent trước

```sql
WITH author_page AS (
    SELECT tenant_id, author_id, display_name
    FROM demo_authors
    WHERE tenant_id = $1
    ORDER BY author_id
    LIMIT $2 OFFSET $3
)
SELECT
    p.author_id,
    p.display_name,
    b.book_id,
    b.title
FROM author_page AS p
LEFT JOIN demo_books AS b
    ON b.tenant_id = p.tenant_id
   AND b.author_id = p.author_id
ORDER BY p.author_id, b.book_id;
```

Ở đây LIMIT áp dụng trước trên tập authors. Kết quả JOIN vẫn có thể nhiều hơn page size vì mỗi author có nhiều books, nhưng **số parent trong trang** được giữ đúng.

### 16.2. Hai query select-in sau khi lấy page

Cách khác:
1. Query trang author.
2. Nếu page rỗng, trả luôn.
3. Query books cho tất cả author IDs trong page bằng ANY/IN.
4. Group books theo author_id.

Cách này thường dễ kiểm soát DTO và tránh duplicate parent rows. Cần cân nhắc snapshot consistency giữa hai query.

### 16.3. Keyset pagination cha/con

Nếu page authors dùng keyset:
- Lấy author IDs tiếp theo theo `(created_at, author_id)` hoặc khóa sắp xếp ổn định.
- Query books theo tập IDs của page.
- Trả cursor dựa trên parent cuối trang, không dựa trên child cuối cùng.

Cursor của trang phải đại diện cho **đơn vị được phân trang**. Nếu trang theo author mà cursor lấy từ book, semantics sẽ sai.

## 17. Tính nhất quán giữa query cha và query con

JOIN trong một statement nhìn dữ liệu theo snapshot của statement theo isolation semantics của DBMS. Select-in thường là nhiều statement:

1. Query authors.
2. Query books theo author IDs.

Nếu dữ liệu thay đổi giữa hai query, response có thể kết hợp parent ở trạng thái cũ với child ở trạng thái mới.

### 17.1. Read Committed và nhiều statement

Trong PostgreSQL mặc định READ COMMITTED, mỗi statement có thể có snapshot mới. Một book được thêm sau query authors nhưng trước query books có thể xuất hiện trong response. Một book bị xóa giữa hai query có thể không xuất hiện.

Đây có thể chấp nhận được cho một màn hình danh sách “gần realtime”, nhưng không phù hợp nếu contract đòi một snapshot duy nhất.

### 17.2. Repeatable Read hoặc snapshot transaction

Nếu cần nhất quán giữa các query batch, có thể dùng transaction isolation phù hợp. PostgreSQL REPEATABLE READ giữ snapshot nhất quán cho các statement trong transaction, nhưng transaction dài giữ connection/snapshot lâu và có chi phí vận hành.

Không giữ transaction mở qua nhiều thao tác người dùng hoặc HTTP requests dài nếu không có thiết kế rõ.

### 17.3. Cách khác: một statement hoặc materialized result

Có thể dùng JOIN/CTE/aggregate trong một statement để có snapshot của statement. Với export/báo cáo lớn, tạo snapshot/materialized job dataset có thể phù hợp hơn.

### 17.4. Không cần snapshot nghiêm ngặt cho mọi endpoint

Một trang danh sách bình thường có thể chấp nhận dữ liệu mới giữa các request. Quan trọng là contract nói rõ:
- Có thể thấy dữ liệu mới khi chuyển trang không?
- Có thể lặp hoặc bỏ sót khi sort key thay đổi không?
- Export có phải là snapshot tại một thời điểm không?
- Đồng bộ incremental dựa trên watermark nào?

## 18. Index cho query set-based

Các query theo tập hợp vẫn cần index phù hợp.

Với lab:
```sql
CREATE INDEX idx_demo_books_tenant_author
ON demo_books (tenant_id, author_id);

CREATE INDEX idx_demo_books_tenant_author_status
ON demo_books (tenant_id, author_id, status);

CREATE INDEX idx_demo_books_top_published
ON demo_books (
    tenant_id,
    author_id,
    published_at DESC,
    book_id DESC
)
WHERE status = 'PUBLISHED';

CREATE INDEX idx_demo_reviews_tenant_book
ON demo_reviews (tenant_id, book_id);
```

### 18.1. Index foreign key/filter

Nếu query thường là:

```sql
WHERE tenant_id = ?
  AND author_id = ?
```

index bắt đầu bằng `(tenant_id, author_id)` thường phù hợp. Với status filter, cân nhắc index thêm status theo workload.

### 18.2. Index top-N

Query top-N mỗi author sắp xếp theo `published_at DESC, book_id DESC`. Index partial có điều kiện `status='PUBLISHED'` có thể giúp giảm số hàng cần xét, nếu workload và planner phù hợp.

### 18.3. Đừng tạo index cho mọi query fingerprint

Index:
- Tốn disk.
- Tăng chi phí INSERT/UPDATE/DELETE.
- Tốn cache.
- Có thể làm planner có nhiều lựa chọn nhưng không giúp query.
- Có chi phí bảo trì và vacuum.

Đo query phổ biến, selectivity, write rate và index usage trước khi thêm.

## 19. EXPLAIN để hiểu lựa chọn set-based

So sánh JOIN:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    a.author_id,
    a.display_name,
    b.book_id,
    b.title
FROM demo_authors AS a
LEFT JOIN demo_books AS b
    ON b.tenant_id = a.tenant_id
   AND b.author_id = a.author_id
WHERE a.tenant_id = 10
ORDER BY a.author_id, b.book_id;
```

Và select-in child query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT author_id, book_id, title
FROM demo_books
WHERE tenant_id = 10
  AND author_id = ANY(ARRAY[1,2,3,4,5]::integer[])
ORDER BY author_id, book_id;
```

### 19.1. Các chỉ số cần xem

- Actual rows tại từng node.
- Estimated rows so với actual rows.
- Loops (đặc biệt nested loop).
- Shared/local/temp buffers.
- Sort method và disk spill.
- Planning time/execution time.
- Rows removed by filter.
- Index scan/bitmap/seq scan.
- Số query và tổng thời gian của cả request.

### 19.2. Một statement không có nghĩa một lần truy cập vật lý

Một JOIN có thể dùng Nested Loop với inner index scan lặp nhiều lần. Đó là plan bên trong database, không phải N+1 round trips từ application. Nested loop có thể rất hiệu quả nếu outer set nhỏ và inner index tốt. Đừng nhầm số loops trong EXPLAIN với số câu SQL ứng dụng gửi.

### 19.3. Nhiều query nhỏ có thể có tổng chi phí lớn dù từng query nhanh

Nếu query child mỗi cái 1 ms nhưng có 300 lần execute, tổng thời gian database và network vẫn đáng kể. Đo cả tổng query count/time trong request, không chỉ slow query threshold của từng statement.

### 19.4. Một query lớn có thể có plan tệ

Set-based rewrite có thể tạo hash join lớn, sort spill hoặc Cartesian multiplication. So sánh:
- Kết quả có đúng không?
- Tổng rows/bytes có giảm không?
- Query count giảm bao nhiêu?
- DB CPU/buffers tăng hay giảm?
- App heap/CPU thay đổi ra sao?
- Tail latency và concurrency thế nào?

## 20. Kiểm thử tự động để ngăn N+1 quay lại

Một bài test chỉ kiểm response có đúng JSON không sẽ không phát hiện 101 query thay vì 2 query.

### 20.1. Kiểm query count

Trong integration test, có thể dùng:
- Hibernate Statistics.
- Datasource proxy/interceptor.
- JDBC instrumentation.
- SQLAlchemy event listeners.
- Django `assertNumQueries`.
- EF Core command logging/interceptors.
- Query tracing hoặc test database metrics.

Ví dụ Django:

```python
with self.assertNumQueries(2):
    response = self.client.get("/authors")
```

Con số 2 chỉ đúng với một implementation cụ thể: query authors và prefetch books. Nếu middleware/auth/query setup có query khác, điều chỉnh test để đo đúng operation hoặc dùng fingerprint/counter riêng.

### 20.2. Test theo số parent khác nhau

Một test hữu ích chạy với 1 author rồi 20 authors:
- Nếu query count tăng từ 2 lên 21, có dấu hiệu N+1.
- Nếu query count vẫn 2 (hoặc tăng theo batch đã định), chiến lược fetch có khả năng đúng.

Đừng hardcode một query count quá mong manh nếu implementation hợp lệ có thể dùng 2 hoặc 3 query. Test nên bảo vệ contract quan trọng: **query count không tăng tuyến tính theo số parent**.

### 20.3. Test trường hợp parent không có child

Bảo đảm LEFT JOIN/select-in vẫn trả parent có collection rỗng. Test author 5 không có sách, và author 4 không có sách published.

### 20.4. Test duplicate và nhiều collection

Tạo author có:
- 3 books.
- 4 awards.
- 2 tags.

Xác nhận:
- Không nhân đôi book/award/tag.
- Count không bị nhân lên.
- DTO có mỗi child đúng một lần.
- Response size có giới hạn.

### 20.5. Test tenant isolation

Dữ liệu có author_id=1 trong tenant 10 và tenant 20. Query child phải ràng buộc cả `tenant_id` và `author_id`; test không để book tenant 20 lọt vào author tenant 10.

### 20.6. Test query count không đồng nghĩa performance test

Hai query có thể trả hàng triệu dòng và chậm hơn 100 query nhỏ trên dữ liệu rất nhỏ. Query count là tín hiệu cần thiết nhưng không đủ. Cần benchmark cardinality, row width, bytes và execution plan.

## 21. Một quy trình chẩn đoán N+1

### Bước 1 — Chọn request chậm có dấu hiệu lặp

Dùng tracing/APM hoặc log để tìm endpoint có:
- Nhiều SQL spans.
- Cùng fingerprint lặp lại.
- Nhiều lần gọi repository cho cùng relation.
- DB time chiếm tỷ lệ lớn.

### Bước 2 — Gắn query với code path

Tìm:
- Vòng lặp gọi repository/DAO.
- Serializer truy cập lazy property.
- Resolver GraphQL.
- Mapping DTO đọc relation.
- Template/render code gọi getter.
- Callback/event handler phát query.

### Bước 3 — Xác định shape dữ liệu

Hỏi:
- Cần parent nào?
- Child nào?
- Chỉ cần count hay toàn bộ child?
- Có cần nhiều collection?
- Có cần top-N mỗi parent?
- Có page parent?
- Có yêu cầu snapshot không?

### Bước 4 — Chọn chiến lược

- JOIN cho relation đơn hoặc collection nhỏ phù hợp.
- Select-in/IN/ANY cho collection theo tập parent.
- Aggregate nếu chỉ cần count/sum.
- LATERAL/window cho top-N per parent.
- Batch fetch nếu ORM/driver hỗ trợ và tập lớn.
- Job/stream nếu cần đọc khối lượng lớn.

### Bước 5 — Viết lại và kiểm semantics

So sánh:
- Parent không có child.
- Child bị filter theo trạng thái.
- Tenant/authorization.
- NULL.
- Duplicate.
- Ordering.
- Pagination.
- Snapshot/concurrency.

### Bước 6 — Đo lại toàn request

Đo query count, tổng DB time, rows/bytes, app mapping, heap/GC, p95/p99 và pool usage. Một câu query duy nhất không phải mục tiêu tự thân.

## 22. Lựa chọn nhanh theo tình huống

| Nhu cầu | Lựa chọn thường phù hợp | Cần cảnh giác |
| --- | --- | --- |
| Parent + một child | JOIN | Null/LEFT vs INNER |
| Parent + collection nhỏ | JOIN hoặc select-in | Duplicate parent rows |
| Parent + nhiều collection | Select-in hoặc aggregate riêng | Cartesian explosion |
| Chỉ cần child count | GROUP BY/aggregate/subquery | COUNT(*) với LEFT JOIN |
| Top 3 child mỗi parent | LATERAL hoặc ROW_NUMBER | Index/sort cardinality |
| Page cha và collection | Page parent trước, select-in child | Không LIMIT trên joined rows |
| GraphQL nested resolver | DataLoader/batch resolver | Batch order/cache scope |
| ORM lazy collection | EntityGraph/join fetch/batch/select-in | EAGER không đảm bảo 1 query |
| Export lớn | Cursor/stream/batch | Connection/transaction lifetime |
| Tập ID lớn | Array/table-valued/staging/chunk | Parameter limits, huge IN |
| Báo cáo tổng hợp | Aggregate/materialized summary | Query vẫn có thể scan lớn |

## 23. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ nhìn số query tổng toàn server | Không biết request nào gây N+1 | Trace theo request/job |
| Reuse PreparedStatement và nghĩ đã hết N+1 | Vẫn execute N lần | Batch/set-based |
| Bật EAGER toàn bộ relation | Query thừa ở nhiều endpoint | Fetch plan theo use case |
| Dùng JOIN cho mọi collection | Cartesian explosion | Select-in/aggregate riêng |
| INNER JOIN khi cần parent không child | Mất parent | LEFT JOIN |
| Đặt child predicate ở WHERE sau LEFT JOIN | Vô tình loại parent | Đặt ở ON khi phù hợp |
| COUNT(*) trên LEFT JOIN | Đếm placeholder row | COUNT(child PK) |
| JOIN hai collection rồi COUNT | Count bị nhân | Aggregate trước hoặc query riêng |
| Dùng DISTINCT để che duplicate | Có thể tốn sort/hash và che lỗi join | Sửa cardinality/mapping |
| LIMIT sau JOIN collection | Trang có ít parent hơn yêu cầu | Page parent trước |
| Chỉ JOIN theo author_id | Có thể trộn tenant | Join cả tenant key |
| Lấy toàn bộ child cho top-3 | Tải thừa | LATERAL/window |
| Batch quá lớn | IN/query/payload khổng lồ | Đo và chunk |
| Batch quá nhỏ | Vẫn nhiều round trips | Tối ưu batch size |
| DataLoader global cache | Trộn tenant/stale data | Cache scope request |
| Chỉ test response correctness | N+1 quay lại | Query count test |
| Chỉ test query count | Một query lớn vẫn quá đắt | Rows/bytes/plan/load test |
| Giữ transaction dài để snapshot mọi trang | Giữ connection/snapshot lâu | Snapshot/job design |
| Không kiểm consistency giữa select-in queries | Response có thể trộn thời điểm | Isolation/contract |
| Dùng correlated subquery rồi mặc định N+1 | Hiểu sai optimizer | EXPLAIN |
| Thấy Nested Loop loops=N trong plan và gọi là N+1 | Nhầm nội bộ DB với round trips | Phân biệt SQL executions và plan loops |
| ORM fetch join pagination collection | Có thể paginate sai/ở memory | Page parent rồi batch child |
| Dùng serializer trong khi session đóng | Lazy loading lỗi hoặc query ngoài dự kiến | DTO projection/fetch plan |
| Không lọc tenant ở query child | Lộ dữ liệu khác tenant | Scope mọi query |
| Dùng query count như mục tiêu duy nhất | Có thể tạo query khổng lồ | Tối ưu tổng chi phí |

## 24. Bài tập thực hành

Các bài dùng `demo_authors`, `demo_books`, `demo_reviews` trong cùng PostgreSQL session tạo bảng. Nếu chạy ORM/JDBC, tạo lại dataset trên connection/schema phù hợp.

### Bài 1 — Tính N+1

Một endpoint tải 80 authors, rồi mỗi author tải books riêng. Tính tổng query. Nếu mỗi author còn tải review count riêng, tổng query thay đổi thế nào?

### Bài 2 — Nhận diện trong log

Cho một trace có một SELECT authors và 50 SELECT books có cùng fingerprint nhưng author_id khác. Giải thích vì sao đây là dấu hiệu N+1.

### Bài 3 — PreparedStatement reuse

Một JDBC PreparedStatement được tạo một lần rồi execute 100 lần trong vòng lặp. Vì sao vẫn là N+1 dù không tạo 100 object statement?

### Bài 4 — LEFT JOIN

Viết query lấy tất cả authors tenant 10 và books của họ. Chứng minh author 5 vẫn xuất hiện với book_id NULL.

### Bài 5 — INNER vs LEFT

Thay LEFT JOIN bằng INNER JOIN. Những author nào biến mất? Khi nào đây là hành vi đúng?

### Bài 6 — Child filter trong ON

Lấy tất cả authors và chỉ sách PUBLISHED. Viết predicate ở ON. Sau đó chuyển predicate sang WHERE và giải thích khác biệt.

### Bài 7 — Map JOIN rows thành DTO

Viết pseudo-code dùng Map theo author_id để gom nhiều rows thành một AuthorDto với list books. Tránh tạo duplicate parent.

### Bài 8 — Select-in

Lấy authors trước, rồi dùng `author_id = ANY($2::integer[])` để lấy books. Group child theo author_id. Tổng số query là bao nhiêu?

### Bài 9 — Danh sách rỗng

Nếu query authors không trả hàng, xử lý select-in thế nào? Vì sao nên tránh dựng `IN ()`?

### Bài 10 — Nhiều ID

Giả sử có 50.000 author IDs. So sánh một array, chunked IN, temporary table và JOIN tới staging table. Những giới hạn nào cần đo?

### Bài 11 — Count theo parent

Viết một query trả author và số sách PUBLISHED. Vì sao dùng COUNT(b.book_id) thay vì COUNT(*)?

### Bài 12 — Aggregate trước JOIN

Một author có books và awards. Viết CTE aggregate riêng từng collection trước khi JOIN. Vì sao tránh nhân chéo?

### Bài 13 — Correlated subquery

Viết scalar subquery đếm sách mỗi author. Vì sao đây là một SQL statement, dù subquery tham chiếu hàng ngoài? Cần xem plan nào?

### Bài 14 — LATERAL top-N

Lấy ba sách published mới nhất của mỗi author bằng LEFT JOIN LATERAL. Giữ author không có sách published.

### Bài 15 — Window top-N

Viết ROW_NUMBER partition theo tenant_id, author_id, lấy rn <= 3. So sánh với LATERAL.

### Bài 16 — Rank ties

Nếu hai sách có cùng published_at, ROW_NUMBER cần tie-breaker nào để thứ tự xác định? Khi nào RANK phù hợp hơn?

### Bài 17 — JSON aggregate

Tạo JSON array books theo author. Dùng FILTER để loại hàng child NULL từ LEFT JOIN. Tác giả không có sách nhận giá trị gì?

### Bài 18 — JSON payload lớn

Một author có 100.000 books. Vì sao một hàng SQL chứa JSON array rất lớn vẫn có thể gây vấn đề memory/network?

### Bài 19 — Cartesian explosion

Một author có 10 books và 8 awards. JOIN cả hai collection tạo bao nhiêu hàng? Nếu có thêm 5 tags thì số hàng lý thuyết có thể là bao nhiêu?

### Bài 20 — Pagination parent

Viết CTE lấy page 2 authors rồi LEFT JOIN books. Vì sao LIMIT phải nằm trong CTE cha?

### Bài 21 — ORM lazy loading

Tìm một relation LAZY trong entity mẫu. Viết service loop truy cập relation và giải thích query phát sinh. Đề xuất fetch plan cho endpoint.

### Bài 22 — JPA fetch join

Viết query `LEFT JOIN FETCH` cho authors/books. Vì sao fetch join collection và pagination có thể gây vấn đề?

### Bài 23 — Batch fetch

Cấu hình batch size phù hợp trong ORM bạn dùng. Đo query count với 1, 20 và 100 parents. Vì sao số query có thể tăng theo số batch chứ không theo số parent?

### Bài 24 — DataLoader

Viết batch function nhận list author IDs, query books theo tập hợp và trả list kết quả đúng thứ tự keys. Xử lý author không có sách.

### Bài 25 — Snapshot consistency

Mô phỏng thêm book giữa query authors và query books ở READ COMMITTED. So sánh với transaction REPEATABLE READ. Chi phí của transaction dài là gì?

### Bài 26 — EXPLAIN

Chạy EXPLAIN ANALYZE cho JOIN và select-in. So sánh actual rows, loops, buffers và execution time. Vì sao nested loop loops=N không đồng nghĩa application gửi N queries?

### Bài 27 — Query count test

Viết integration test kiểm endpoint trả 20 authors không phát 21 queries. Bảo đảm test không quá cứng với một implementation hợp lệ dùng 2–3 query.

### Bài 28 — Tenant isolation

Dữ liệu có author_id=1 ở tenant 10 và 20. Viết JOIN và select-in query không để book tenant 20 xuất hiện trong response tenant 10.

### Bài 29 — Data skew

Tạo một author có hàng nghìn books, các author còn lại chỉ có một book. So sánh JOIN, select-in và JSON aggregation. Metric nào giúp chọn strategy?

### Bài 30 — Thiết kế endpoint hoàn chỉnh

Thiết kế API `/authors` trả:
1. Trang authors theo tenant đã xác thực.
2. Display name và số sách published.
3. Tối đa 3 sách mới nhất mỗi author.
4. Pagination ổn định.
5. Không phát N+1.
6. Không Cartesian explosion khi có thêm awards.
7. Query count test và load test.
8. Index phù hợp.
9. Snapshot semantics được mô tả.
10. Projection giới hạn cột/bytes.
11. DTO mapping không duplicate parent.
12. EXPLAIN và metrics theo request.

## 25. Checklist triển khai

### Nhận diện
- [ ] Có trace/query count theo request hoặc job?
- [ ] Có query fingerprint lặp lại theo từng parent?
- [ ] Có lazy loading trong vòng lặp hoặc serializer?
- [ ] Có resolver/repository gọi query theo từng khóa?
- [ ] Đã đo tổng DB time, rows và bytes?

### Chọn chiến lược
- [ ] Chỉ cần relation đơn hay collection?
- [ ] JOIN có tạo duplicate parent rows?
- [ ] Nhiều collection có nhân chéo?
- [ ] Chỉ cần count/sum hay cần toàn bộ child?
- [ ] Top-N per parent có thể dùng LATERAL/window?
- [ ] Select-in/batch có phù hợp cardinality?
- [ ] Parent pagination được áp dụng trước khi tải collection?

### Tính đúng
- [ ] LEFT vs INNER JOIN đúng contract?
- [ ] Child predicates ở ON/WHERE đúng?
- [ ] Tenant key có trong JOIN và child query?
- [ ] COUNT dùng cột child NOT NULL?
- [ ] Ordering có tie-breaker?
- [ ] Duplicate/empty collection được xử lý?
- [ ] Snapshot consistency giữa nhiều statement được hiểu?

### Vận hành
- [ ] Query count test có kiểm soát N+1?
- [ ] EXPLAIN trên dữ liệu đại diện?
- [ ] Index filter/order phù hợp?
- [ ] Batch size và ID list có giới hạn?
- [ ] ORM persistence context không phình?
- [ ] Logging không lộ PII?
- [ ] p95/p99, rows/bytes, pool wait và memory được đo?

## 26. Sơ đồ lựa chọn chiến lược

```text
            CẦN TẢI PARENT + DỮ LIỆU LIÊN QUAN
                             |
                             v
                   Chỉ cần scalar/count?
                      /             \
                    Có               Không
                    |                  |
                    v                  v
             Aggregate/subquery    Cần collection?
                                  /             \
                                Có               Không
                                |                  |
                                v                  v
                      Có nhiều collection?     JOIN relation đơn
                          /          \
                        Có            Không
                        |               |
                        v               v
                 Select-in/aggregate   JOIN hay select-in?
                 riêng từng collection theo cardinality/plan
                        |               |
                        +-------+-------+
                                |
                                v
                  Có phân trang parent?
                                |
                                v
                   Page parent trước child
                                |
                                v
                  Cần top-N mỗi parent?
                         /          \
                       Có            Không
                       |               |
                       v               v
                 LATERAL/window    JOIN/select-in
                                |
                                v
             Query count + rows/bytes + EXPLAIN + tests
```

## 27. Tổng kết

N+1 xuất hiện khi một query lấy tập cha, rồi ứng dụng phát thêm query cho từng parent để lấy quan hệ hoặc thông tin phụ. Nó thường bị che khuất bởi lazy loading, ORM mapping, serializer hoặc resolver GraphQL. Dấu hiệu rõ nhất là một query fingerprint lặp lại trong cùng request và số lần execute tăng theo số parent. Tái sử dụng PreparedStatement không giải quyết N+1 nếu statement vẫn được execute N lần.

Truy vấn theo tập hợp có nhiều hình thức. **JOIN** phù hợp khi relation và cardinality được kiểm soát; **IN/ANY/select-in** giúp lấy collection theo một tập parent mà không nhân bản parent rows; **aggregate** phù hợp khi chỉ cần count/sum; **correlated subquery** có thể diễn đạt scalar logic trong một statement; **LATERAL/window function** giải quyết top-N per group; **batch fetch/DataLoader** gom các yêu cầu quan hệ thành query theo nhóm. ORM cung cấp fetch join, entity graph, select-in, prefetch và split query, nhưng cần kiểm SQL thực tế.

Không nên theo đuổi mục tiêu “một query bằng mọi giá”. JOIN nhiều collection có thể tạo Cartesian explosion; LIMIT sau JOIN có thể phân trang sai parent; aggregate sau join nhân bản có thể cho count sai; nhiều query select-in có thể nhìn các snapshot khác nhau; một batch khổng lồ vẫn có thể làm database và ứng dụng quá tải. Hãy xét **cardinality, row width, số query, số hàng trung gian, bytes, index, transaction và consistency** cùng lúc.

Khi phát hiện một endpoint chậm, hãy gắn SQL với request, nhận diện query lặp, xác định chính xác dữ liệu cần và chọn fetch strategy theo use case. Sau khi viết lại, kiểm tra parent không có child, duplicate, tenant isolation, pagination, snapshot và query count; đo EXPLAIN cùng metrics toàn request. Một thiết kế tốt giảm round trips mà vẫn giữ tập kết quả gọn, đúng và có thể dự đoán khi số lượng dữ liệu tăng.
