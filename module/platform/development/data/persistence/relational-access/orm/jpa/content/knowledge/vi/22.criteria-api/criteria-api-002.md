# Vai trò của CriteriaBuilder, CriteriaQuery và Root

Trong JPA (Jakarta Persistence), **Criteria API** cho phép xây dựng truy vấn bằng các đối tượng Java thay vì ghép chuỗi JPQL. Đây là lựa chọn đặc biệt hữu ích khi truy vấn phải thay đổi theo tham số tìm kiếm, điều kiện lọc tùy chọn, quyền truy cập dữ liệu hoặc các phần của một màn hình tìm kiếm nâng cao.

Ba thành phần xuất hiện thường xuyên nhất là:

- **`CriteriaBuilder`:** bộ công cụ tạo truy vấn, điều kiện, biểu thức, phép so sánh, phép kết hợp logic, phép tổng hợp và nhiều thành phần khác.
- **`CriteriaQuery<T>`:** đối tượng mô tả **truy vấn SELECT** và kiểu kết quả `T`, gồm phần chọn, điều kiện lọc, sắp xếp, nhóm, having và distinct.
- **`Root<X>`:** đại diện cho **thực thể gốc trong mệnh đề FROM**, đóng vai trò điểm xuất phát để truy cập thuộc tính và điều hướng quan hệ của entity `X`.

Ví dụ tối thiểu:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

cq.select(book)
  .where(cb.isTrue(book.get("published")));

List<Book> result = em.createQuery(cq).getResultList();
```

Trong đoạn code này:

1. `cb` tạo cấu trúc Criteria.
2. `cq` mô tả truy vấn trả về `Book`.
3. `book` biểu diễn entity `Book` trong phần FROM.
4. `cb.isTrue(...)` xây dựng một điều kiện.
5. `cq.select(...).where(...)` gắn thành phần SELECT/WHERE vào truy vấn.
6. `em.createQuery(cq)` chuyển cây Criteria thành đối tượng JPA `TypedQuery<Book>` có thể thực thi.
7. `getResultList()` thực hiện truy vấn và trả kết quả.

Bài học **“Vai trò của CriteriaBuilder, CriteriaQuery và Root”** thuộc chương **Criteria API** trong chủ đề **Data Persistence Relational Access ORM JPA**. Nội dung đi từ mô hình tư duy và kiểu Java, qua ví dụ truy vấn thực tế, đến phân biệt `Root` với `Path`/`Join`, cách tạo điều kiện động, projection, aggregation, query parameters, phân trang, CriteriaUpdate/Delete và những lỗi thường gặp.

Các ví dụ sử dụng package `jakarta.persistence` của Jakarta Persistence. Các dự án JPA cũ sử dụng package `javax.persistence` có khái niệm tương ứng; cần thống nhất API version trong dự án.

## 1. Đối chiếu Criteria API với JPQL

Giả sử muốn tìm các sách đã xuất bản, có giá không thấp hơn một giá trị nhất định, rồi sắp xếp theo giá.

Bằng JPQL:

```java
List<Book> books = em.createQuery(
    "SELECT b FROM Book b " +
    "WHERE b.published = true AND b.price >= :minPrice " +
    "ORDER BY b.price ASC",
    Book.class
).setParameter("minPrice", new BigDecimal("100000"))
 .getResultList();
```

Bằng Criteria API:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

Predicate published = cb.isTrue(book.get("published"));

Predicate priceAtLeast = cb.greaterThanOrEqualTo(
    book.<BigDecimal>get("price"),
    new BigDecimal("100000")
);

cq.select(book)
  .where(cb.and(published, priceAtLeast))
  .orderBy(cb.asc(book.get("price")));

List<Book> books = em.createQuery(cq).getResultList();
```

Hai cách mô tả cùng **ý định truy vấn**. Criteria API không tự bảo đảm SQL nhanh hơn hoặc ít câu lệnh hơn JPQL. Cả hai cuối cùng được JPA provider biên dịch thành truy vấn phù hợp với database, mapping và dialect.

Criteria thường dài hơn với truy vấn tĩnh rất đơn giản, nhưng có ưu thế khi:

- Người dùng có thể bật/tắt nhiều tiêu chí lọc.
- Điều kiện được tái sử dụng theo các hàm hỗ trợ.
- Muốn xây query theo cấu trúc thay vì nối chuỗi.
- Muốn tận dụng **static metamodel** để kiểm tra tên và kiểu thuộc tính ngay lúc biên dịch.
- Một query thay đổi theo quyền hoặc ngữ cảnh ứng dụng.

**Criteria API là một cách biểu diễn truy vấn có cấu trúc, không phải một ORM khác tách khỏi JPA.**

## 2. Mô hình cây truy vấn

Có thể hình dung Criteria query như một cây cú pháp biểu diễn truy vấn:

```text
                    EntityManager
                          │
             getCriteriaBuilder()
                          │
                          ▼
                   CriteriaBuilder
                          │
                 createQuery(Book.class)
                          │
                          ▼
                 CriteriaQuery<Book>
                    │     │      │
        from(Book)  │     │      └─ orderBy(...)
              │     │     └─ where(...)
              ▼     │
         Root<Book> │
              │     └─ select(book)
              │
         book.get("price")
              │
        Path<BigDecimal>
              │
     cb.greaterThanOrEqualTo(...)
              │
           Predicate
              │
              └── gắn vào CriteriaQuery.where(...)
                          │
                em.createQuery(cq)
                          │
                          ▼
                  TypedQuery<Book>
                          │
             setParameter / getResultList
                          │
                          ▼
                      Database
```

Đây là sơ đồ khái niệm để hiểu luồng tạo query, không quy định provider phải cài đặt nội bộ bằng một loại AST cụ thể.

Điều cần nhớ:

- `CriteriaBuilder` **tạo** các thành phần.
- `CriteriaQuery` **chứa cấu trúc SELECT query**.
- `Root` **định vị entity trong FROM**.
- `Predicate`/`Expression`/`Path`/`Join` **diễn đạt biểu thức và điều kiện**.
- `TypedQuery` **là đối tượng thực thi truy vấn** do `EntityManager` tạo từ Criteria query.

## 3. Entity mẫu để học Criteria API

Ta sử dụng `Book` và `Author`, trong đó nhiều sách có thể thuộc cùng một tác giả.

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDate;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean published;

    @Column(nullable = false)
    private LocalDate createdDate;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private Author author;

    protected Book() {}

    public Book(
            String title,
            BigDecimal price,
            boolean published,
            LocalDate createdDate,
            Author author) {
        this.title = title;
        this.price = price;
        this.published = published;
        this.createdDate = createdDate;
        this.author = author;
    }

    public Long getId() { return id; }

    public String getTitle() { return title; }

    public BigDecimal getPrice() { return price; }

    public boolean isPublished() { return published; }

    public LocalDate getCreatedDate() { return createdDate; }

    public Author getAuthor() { return author; }
}
```

Entity `Author`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "authors")
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Author() {}

    public Author(String name) {
        this.name = name;
    }

    public Long getId() { return id; }

    public String getName() { return name; }
}
```

Schema quan hệ minh họa:

```sql
CREATE TABLE authors (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    price DECIMAL(14, 2) NOT NULL,
    published BOOLEAN NOT NULL,
    created_date DATE NOT NULL,
    author_id BIGINT NOT NULL,
    CONSTRAINT fk_books_author
        FOREIGN KEY (author_id) REFERENCES authors(id)
);
```

DDL là ví dụ mang tính khái niệm. Cú pháp sinh ID và kiểu BOOLEAN/DATE có thể khác nhau theo database và dialect.

Những field này đủ để minh họa lọc theo boolean, khoảng giá, ngày, title, join tác giả, sắp xếp, projection và aggregation.

## 4. `CriteriaBuilder`: bộ công cụ tạo query và biểu thức

JPA cung cấp `CriteriaBuilder` qua `EntityManager`:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
```

Một số phương thức tiêu biểu:

| Nhóm chức năng | Ví dụ |
| --- | --- |
| Tạo SELECT query | `cb.createQuery(Book.class)` |
| Tạo query dạng Tuple | `cb.createTupleQuery()` |
| Tạo Criteria UPDATE | `cb.createCriteriaUpdate(Book.class)` |
| Tạo Criteria DELETE | `cb.createCriteriaDelete(Book.class)` |
| So sánh bằng/khác | `cb.equal(...)`, `cb.notEqual(...)` |
| So sánh thứ tự | `cb.greaterThan(...)`, `cb.lessThan(...)` |
| Kết hợp logic | `cb.and(...)`, `cb.or(...)`, `cb.not(...)` |
| Kiểm tra null | `cb.isNull(...)`, `cb.isNotNull(...)` |
| So khớp chuỗi | `cb.like(...)`, `cb.lower(...)` |
| Kiểm tra khoảng | `cb.between(...)` |
| Điều kiện đúng/sai | `cb.conjunction()`, `cb.disjunction()` |
| Tổng hợp | `cb.count(...)`, `cb.sum(...)`, `cb.avg(...)` |
| Tạo thứ tự | `cb.asc(...)`, `cb.desc(...)` |
| Constructor projection | `cb.construct(Dto.class, ...)` |
| Tham số | `cb.parameter(String.class, "pattern")` |

Một phương thức `cb.equal(...)` không tự đi đến database:

```java
Predicate titleMatches = cb.equal(
    book.get("title"),
    "JPA căn bản"
);
```

Nó tạo một thành phần biểu diễn điều kiện. Điều kiện đó cần được gắn vào Criteria query, rồi query được thực thi qua `EntityManager`.

### CriteriaBuilder không phải đối tượng thực thi

Đoạn sau không chạy SQL:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

Predicate p = cb.equal(book.get("title"), "JPA căn bản");
cq.where(p);
```

Chỉ khi tạo và thực thi query:

```java
List<Book> books = em.createQuery(cq).getResultList();
```

provider mới cần xử lý truy vấn để trả kết quả. Thời điểm flush và SQL cụ thể vẫn phụ thuộc context, query, provider và transaction.

## 5. `CriteriaQuery<T>`: bản mô tả SELECT và kiểu kết quả

Một Criteria query SELECT được tạo bằng:

```java
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
```

Tham số generic `Book` biểu diễn **kiểu kết quả mà ứng dụng mong muốn**.

Các thao tác thường dùng:

```java
cq.select(...)
  .where(...)
  .orderBy(...)
  .distinct(true);
```

Ngoài ra `CriteriaQuery` hỗ trợ `groupBy(...)` và `having(...)`, tùy loại query.

Ví dụ:

```java
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

cq.select(book)
  .where(cb.isTrue(book.get("published")))
  .orderBy(cb.desc(book.get("createdDate")));
```

Ở đây:

- `select(book)` yêu cầu trả về entity `Book`.
- `where(...)` xác định điều kiện lọc.
- `orderBy(...)` xác định thứ tự kết quả.
- Kiểu của `cq` là `CriteriaQuery<Book>` nên khi đưa vào `EntityManager`, ứng dụng nhận `TypedQuery<Book>`.

### CriteriaQuery là cấu trúc đang được xây dựng

Các phương thức như `where` và `orderBy` thay đổi cấu trúc truy vấn hiện tại; không nên tưởng rằng cứ gọi `where` một lần là vĩnh viễn bổ sung một điều kiện vào danh sách tự động.

Ví dụ dễ sai:

```java
cq.where(cb.isTrue(book.get("published")));

cq.where(cb.greaterThan(
    book.<BigDecimal>get("price"),
    BigDecimal.ZERO
));
```

Lệnh `where(...)` thứ hai **thay thế restriction trước đó** trên query, chứ không tự nối thêm bằng AND. Nếu muốn cả hai, cần kết hợp thành một Predicate:

```java
Predicate published = cb.isTrue(book.get("published"));

Predicate pricePositive = cb.greaterThan(
    book.<BigDecimal>get("price"),
    BigDecimal.ZERO
);

cq.where(cb.and(published, pricePositive));
```

Hoặc xây danh sách điều kiện rồi gọi `where` một lần.

Đây là lý do quan trọng khi xây bộ lọc động.

## 6. `Root<X>`: điểm xuất phát của FROM

`Root<Book>` được tạo bởi:

```java
Root<Book> book = cq.from(Book.class);
```

Nó tương đương về ý tưởng với biến định danh `b` trong JPQL:

```sql
SELECT b FROM Book b
```

Trong Criteria:

```java
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);
cq.select(book);
```

Root giữ vai trò **đường dẫn bắt đầu** để truy cập những thuộc tính của Book:

```java
Path<Long> id = book.get("id");
Path<String> title = book.get("title");
Path<BigDecimal> price = book.get("price");
```

Nhờ `Root`, provider biết `title` và `price` thuộc entity nào trong query.

### Root không phải entity Book thực

`book` ở đây là **biểu diễn truy vấn**. Nó không phải `Book` đã được tải từ database.

Sai:

```java
// Root<Book> không có nghĩa là Book:
Book actualBook = book; // Không biên dịch.
```

Đúng:

```java
List<Book> actualBooks = em.createQuery(cq).getResultList();
```

Root dùng để **mô tả cách tìm entity**, còn danh sách kết quả chứa các Book entity thật theo semantics của JPA.

### Root có thể truy cập association

```java
Path<Author> authorPath = book.get("author");
Path<String> authorName = book.get("author").get("name");
```

Tuy nhiên, khi cần kiểm soát join type, dùng `join(...)` tường minh thường dễ hiểu và an toàn hơn:

```java
Join<Book, Author> author = book.join("author", JoinType.INNER);
```

Chúng ta sẽ xem phân biệt `Root` với `Join` ở phần sau.

## 7. Hướng dẫn đọc một truy vấn Criteria từ đầu đến cuối

Một truy vấn có lọc title và sắp xếp:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> root = cq.from(Book.class);

Predicate titleMatches = cb.like(
    cb.lower(root.get("title")),
    "%jpa%"
);

cq.select(root)
  .where(titleMatches)
  .orderBy(cb.asc(root.get("title")));

TypedQuery<Book> query = em.createQuery(cq);

List<Book> results = query.getResultList();
```

Đối chiếu JPQL:

```sql
SELECT b
FROM Book b
WHERE LOWER(b.title) LIKE '%jpa%'
ORDER BY b.title ASC
```

Bảng đọc từng dòng:

| Code | Ý nghĩa |
| --- | --- |
| `em.getCriteriaBuilder()` | Lấy công cụ tạo Criteria |
| `cb.createQuery(Book.class)` | Tạo SELECT query trả `Book` |
| `cq.from(Book.class)` | Đặt Book làm nguồn dữ liệu gốc |
| `root.get("title")` | Tham chiếu thuộc tính title của Book |
| `cb.lower(...)` | Biểu thức chuyển thành chữ thường |
| `cb.like(..., "%jpa%")` | Predicate so khớp mẫu |
| `cq.select(root)` | Kết quả là Book entity |
| `cq.where(titleMatches)` | Gắn điều kiện WHERE |
| `cq.orderBy(cb.asc(...))` | Sắp xếp theo title |
| `em.createQuery(cq)` | Tạo query executable |
| `getResultList()` | Thực thi và nhận kết quả |

**Ba đối tượng trung tâm không thay thế nhau:** `CriteriaBuilder` tạo điều kiện, `CriteriaQuery` lắp cấu trúc, `Root` xác định các thuộc tính thuộc nguồn nào.

## 8. `Path`, `Expression` và `Predicate` liên hệ với Root ra sao?

Trong Criteria API, các kiểu liên quan tạo nên một mô hình biểu thức có phân cấp.

### `Path<T>`

`Path<T>` mô tả đường truy cập một thuộc tính hoặc phần của entity model.

```java
Path<String> title = root.get("title");
Path<BigDecimal> price = root.get("price");
```

Các đường này không chứa giá trị title/price của một Book cụ thể, mà biểu diễn **cột/thuộc tính cần tham chiếu khi query**.

### `Expression<T>`

`Expression<T>` là biểu diễn một giá trị/biểu thức có kiểu `T` trong query. Nhiều `Path<T>` cũng dùng được tại nơi yêu cầu `Expression<T>`.

```java
Expression<String> lowerTitle =
    cb.lower(root.get("title"));
```

`cb.lower(...)` tạo một expression mới, không đổi tên Java field và không tự cập nhật dữ liệu.

### `Predicate`

`Predicate` là biểu thức điều kiện logic.

```java
Predicate condition = cb.like(
    cb.lower(root.get("title")),
    "%jpa%"
);
```

Một Predicate có thể kết hợp với các Predicate khác:

```java
Predicate available = cb.isTrue(root.get("published"));

Predicate expensive = cb.greaterThan(
    root.<BigDecimal>get("price"),
    new BigDecimal("200000")
);

Predicate finalCondition = cb.and(available, expensive);
```

Tư duy:

```text
Root<Book>
    │
    └── get("price") → Path<BigDecimal>
                              │
             cb.greaterThan(path, amount)
                              │
                              ▼
                           Predicate
                              │
                   cq.where(predicate)
```

### `Selection<T>`

`Selection<T>` mô tả thành phần được chọn trong SELECT. Root hoặc expression có thể được dùng làm selection; khi projection nhiều cột, có thể dùng `Tuple` hoặc constructor projection.

Điều này lý giải vì sao:

```java
cq.select(root);
```

và:

```java
cq.select(root.get("title"));
```

trả về các kiểu kết quả khác nhau khi CriteriaQuery được khai báo phù hợp.

## 9. Lọc theo nhiều điều kiện với CriteriaBuilder

Ví dụ tìm Book:

- Đã xuất bản.
- Giá trong khoảng 100.000–500.000.
- Tiêu đề chứa “java”.
- Tạo sau ngày xác định.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

Predicate published = cb.isTrue(
    book.get("published")
);

Predicate priceRange = cb.between(
    book.<BigDecimal>get("price"),
    new BigDecimal("100000"),
    new BigDecimal("500000")
);

Predicate titleContains = cb.like(
    cb.lower(book.get("title")),
    "%java%"
);

Predicate afterDate = cb.greaterThanOrEqualTo(
    book.<LocalDate>get("createdDate"),
    LocalDate.of(2025, 1, 1)
);

Predicate all = cb.and(
    published,
    priceRange,
    titleContains,
    afterDate
);

cq.select(book)
  .where(all)
  .orderBy(cb.asc(book.get("id")));

List<Book> books = em.createQuery(cq).getResultList();
```

Các Predicate không thực thi SQL riêng lẻ. Chúng là những nút điều kiện được CriteriaQuery sử dụng khi query chạy.

### AND so với OR

```java
Predicate inexpensive = cb.lessThan(
    book.<BigDecimal>get("price"),
    new BigDecimal("100000")
);

Predicate premium = cb.greaterThan(
    book.<BigDecimal>get("price"),
    new BigDecimal("500000")
);

Predicate specialPrice = cb.or(inexpensive, premium);
```

Tương đương ý tưởng:

```sql
WHERE price < 100000 OR price > 500000
```

Có thể lồng AND/OR:

```java
Predicate rule = cb.and(
    cb.isTrue(book.get("published")),
    cb.or(inexpensive, premium)
);
```

Tương đương:

```sql
WHERE published = TRUE
  AND (price < 100000 OR price > 500000)
```

Luôn làm rõ dấu ngoặc logic; một điều kiện AND/OR sai có thể trả dữ liệu ngoài phạm vi người dùng được xem.

## 10. Xây query động: trường hợp quan trọng nhất của Criteria API

Giả sử API tìm kiếm nhận các tiêu chí tùy chọn:

```java
public record BookSearch(
    String titleKeyword,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Boolean published,
    Long authorId
) {}
```

Nếu dùng JPQL ghép chuỗi, code dễ trở nên phức tạp khi nhiều tham số vắng mặt. Với Criteria, có thể tạo danh sách Predicate và chỉ bổ sung khi tiêu chí tồn tại.

```java
public List<Book> searchBooks(
        EntityManager em, BookSearch input) {

    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Book> cq = cb.createQuery(Book.class);
    Root<Book> book = cq.from(Book.class);

    List<Predicate> conditions = new ArrayList<>();

    if (input.titleKeyword() != null &&
        !input.titleKeyword().isBlank()) {

        String pattern =
            "%" + input.titleKeyword().trim().toLowerCase(Locale.ROOT) + "%";

        conditions.add(cb.like(
            cb.lower(book.get("title")),
            pattern
        ));
    }

    if (input.minPrice() != null) {
        conditions.add(cb.greaterThanOrEqualTo(
            book.<BigDecimal>get("price"),
            input.minPrice()
        ));
    }

    if (input.maxPrice() != null) {
        conditions.add(cb.lessThanOrEqualTo(
            book.<BigDecimal>get("price"),
            input.maxPrice()
        ));
    }

    if (input.published() != null) {
        conditions.add(cb.equal(
            book.get("published"),
            input.published()
        ));
    }

    if (input.authorId() != null) {
        conditions.add(cb.equal(
            book.get("author").get("id"),
            input.authorId()
        ));
    }

    cq.select(book)
      .where(conditions.toArray(new Predicate[0]))
      .orderBy(cb.asc(book.get("id")));

    return em.createQuery(cq).getResultList();
}
```

Code trên sử dụng:

- `CriteriaBuilder` để tạo từng phép so sánh.
- `Root<Book>` để định vị thuộc tính.
- `CriteriaQuery<Book>` để lắp tất cả Predicate và chọn kết quả.
- `EntityManager` để thực thi.

Chỉ cần bổ sung một điều kiện mới vào danh sách khi người dùng cung cấp tiêu chí tương ứng.

### Xử lý danh sách điều kiện rỗng

Khi danh sách `conditions` rỗng:

```java
cq.where(new Predicate[0]);
```

Theo API Criteria, truyền mảng restriction rỗng nghĩa là xóa các restriction đã có, tức không có điều kiện WHERE từ danh sách đó. Đây có thể là kết quả đúng khi cho phép tìm tất cả, nhưng trong API có dữ liệu nhạy cảm, **không được vô tình bỏ điều kiện phân quyền**.

Ví dụ với bộ lọc tenant, điều kiện tenant phải luôn được bổ sung bất kể người dùng có chọn bộ lọc khác hay không.

### Chú ý LIKE wildcard

Đoạn:

```java
String pattern = "%" + keyword + "%";
```

không phải một thao tác “tìm chuỗi literal” hoàn toàn: ký tự `%` và `_` của SQL LIKE có ý nghĩa wildcard. Nếu người dùng nhập những ký tự này, kết quả có thể rộng hơn mong đợi.

Khi yêu cầu tìm literal substring, hãy escape wildcard đúng quy tắc rồi dùng overload `CriteriaBuilder.like(...)` với ký tự escape, phù hợp database/provider. Tương tự, cần giới hạn độ dài từ khóa và phân trang, không mặc định mọi pattern sẽ dùng index hiệu quả.

## 11. Lấy CriteriaBuilder từ đâu và dùng trong phạm vi nào?

`CriteriaBuilder` có thể lấy từ `EntityManager`:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
```

Hoặc `EntityManagerFactory`:

```java
CriteriaBuilder cb = emf.getCriteriaBuilder();
```

Đây là công cụ xây cấu trúc query, **không phải connection tới database**.

Nó khác với:

- `EntityManager`: quản lý persistence context và thao tác persistence.
- `CriteriaQuery`: mô tả một SELECT query cụ thể.
- `TypedQuery`: đối tượng query mà ứng dụng thực thi cùng tham số, pagination, flush mode.
- `Root`: biểu diễn nguồn entity trong một CriteriaQuery cụ thể.

### Không tạo Root từ EntityManager

Không có quy tắc:

```java
// Sai ý tưởng:
Root<Book> book = em.from(Book.class);
```

Root được tạo từ query:

```java
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);
```

Lý do: Root cần gắn với **cây truy vấn cụ thể**, để những expression/predicate tham chiếu đúng FROM.

### Không dùng cùng một Root cho query khác

Ví dụ sai về phạm vi:

```java
CriteriaQuery<Book> first = cb.createQuery(Book.class);
Root<Book> rootFirst = first.from(Book.class);

CriteriaQuery<Book> second = cb.createQuery(Book.class);

// Không lấy rootFirst của first làm Root cho second.
second.select(rootFirst);
```

Một Root/Path/Join gắn với cấu trúc query nơi nó được tạo. Với query thứ hai, cần gọi:

```java
Root<Book> rootSecond = second.from(Book.class);
second.select(rootSecond);
```

Điều này càng quan trọng khi xây helper tạo Predicate. Helper nên **nhận Root của query hiện tại** hoặc được gọi lại với root mới, thay vì lưu một Predicate/Root cũ vào static field để tái dùng xuyên query.

## 12. Kiểu kết quả của CriteriaQuery quyết định kiểu TypedQuery

Chọn entity:

```java
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

cq.select(book);

TypedQuery<Book> query = em.createQuery(cq);
List<Book> books = query.getResultList();
```

Chọn thuộc tính title:

```java
CriteriaQuery<String> cq = cb.createQuery(String.class);
Root<Book> book = cq.from(Book.class);

cq.select(book.get("title"));

TypedQuery<String> query = em.createQuery(cq);
List<String> titles = query.getResultList();
```

Chọn ID:

```java
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Book> book = cq.from(Book.class);

cq.select(book.get("id"));

List<Long> ids = em.createQuery(cq).getResultList();
```

Điểm quan trọng:

- `CriteriaQuery<Book>` không có nghĩa query bắt buộc chỉ có điều kiện theo Book; nó có nghĩa **kiểu phần tử kết quả** là Book.
- `Root<Book>` có nghĩa **entity gốc** của query là Book.
- Hai generic có thể giống nhau hoặc khác nhau.

Ví dụ:

```java
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Book> book = cq.from(Book.class);

cq.select(cb.count(book));
```

Ở đây Root là Book, kết quả là Long.

## 13. Root và Join: điều hướng quan hệ nhiều bảng

Có Book liên kết Author:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Author author;
```

Muốn tìm sách của tác giả có tên chứa `"Nguyễn"`:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

Join<Book, Author> author = book.join(
    "author",
    JoinType.INNER
);

Predicate authorMatches = cb.like(
    cb.lower(author.get("name")),
    "%nguyễn%"
);

cq.select(book)
  .where(authorMatches)
  .orderBy(cb.asc(book.get("title")));

List<Book> result = em.createQuery(cq).getResultList();
```

JPQL tương ứng:

```sql
SELECT b
FROM Book b JOIN b.author a
WHERE LOWER(a.name) LIKE '%nguyễn%'
ORDER BY b.title ASC
```

Phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| `Root<Book> book` | Biểu diễn nguồn entity Book trong FROM |
| `Join<Book, Author> author` | Biểu diễn liên kết từ Book sang Author |
| `author.get("name")` | Biểu diễn thuộc tính name của Author |
| `cb.like(...)` | Tạo Predicate lọc theo Author name |
| `cq.select(book)` | Trả Book, không phải Author |

**Join không thay thế Root của Book.** Nó mở rộng đường điều hướng qua association được khai báo trong mapping.

### JoinType.INNER và LEFT

```java
book.join("author", JoinType.INNER);
book.join("author", JoinType.LEFT);
```

- `INNER` thường chỉ giữ các Book có association Author khớp theo điều kiện join.
- `LEFT` có thể giữ Book ngay cả khi association không có bản ghi tương ứng, tùy WHERE và mapping.

Với field `author` khai báo `optional = false`, tất cả Book hợp lệ phải có Author, nhưng khái niệm LEFT vẫn hữu ích khi học quan hệ tùy chọn.

### Filter ở WHERE có thể làm LEFT JOIN giống INNER JOIN

Ví dụ:

```java
Join<Book, Author> author =
    book.join("author", JoinType.LEFT);

cq.where(cb.equal(author.get("name"), "An"));
```

Khi Author null, Predicate trên Author name thường không khớp, nên các Book không có Author có thể bị loại. Nếu muốn giữ Book thiếu Author, cần thiết kế điều kiện cẩn thận, chẳng hạn kết hợp `isNull` tùy nghiệp vụ.

Không thể chỉ nhìn `JoinType.LEFT` mà kết luận query luôn giữ mọi row bên trái sau WHERE.

## 14. Một Root hay nhiều Root?

Truy vấn thường có một Root:

```java
Root<Book> book = cq.from(Book.class);
```

Criteria API cũng cho phép nhiều Root:

```java
Root<Book> book = cq.from(Book.class);
Root<Author> author = cq.from(Author.class);
```

Nhưng nhiều Root độc lập về bản chất mô tả nhiều nguồn trong FROM, thường tương đương **Cartesian product / cross join** trước khi có điều kiện liên kết.

Ví dụ nguy hiểm:

```java
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);
Root<Author> author = cq.from(Author.class);

cq.select(book);
```

Nếu có 100 Book và 50 Author, truy vấn về lý thuyết có thể tạo tới 5.000 cặp trước khi lọc, dẫn tới kết quả Book lặp và chi phí lớn.

Nếu entity đã có association, ưu tiên:

```java
Join<Book, Author> author = book.join("author");
```

thay vì thêm Root thứ hai không cần thiết.

Nếu thực sự muốn nhiều Root cho điều kiện độc lập, phải định nghĩa predicate liên kết phù hợp và hiểu hiệu ứng của cross join. Đừng sử dụng `cq.from(...)` lần thứ hai chỉ vì muốn lọc theo thuộc tính của entity liên quan.

## 15. Static metamodel: truy cập thuộc tính kiểu an toàn hơn

Các ví dụ trước sử dụng tên thuộc tính dạng chuỗi:

```java
root.get("title")
root.get("price")
```

Điều này tiện nhưng dễ sai khi refactor:

```java
root.get("titel") // Lỗi chính tả có thể chỉ được phát hiện runtime.
```

JPA hỗ trợ **static metamodel**, thường được sinh bằng annotation processor trong quá trình build.

Với entity `Book`, bộ sinh metamodel có thể tạo class `Book_` tương tự:

```java
@StaticMetamodel(Book.class)
public abstract class Book_ {

    public static volatile SingularAttribute<Book, Long> id;

    public static volatile SingularAttribute<Book, String> title;

    public static volatile SingularAttribute<Book, BigDecimal> price;

    public static volatile SingularAttribute<Book, Boolean> published;

    public static volatile SingularAttribute<Book, LocalDate> createdDate;

    public static volatile SingularAttribute<Book, Author> author;
}
```

Đây là minh họa cấu trúc; **không nhất thiết tự viết class `Book_`**. Trong dự án thực tế, nó thường được sinh từ entity model.

Có metamodel:

```java
Root<Book> book = cq.from(Book.class);

Path<String> title = book.get(Book_.title);
Path<BigDecimal> price = book.get(Book_.price);
```

Lợi ích:

- Đổi tên field `title` có thể được phát hiện qua lỗi biên dịch khi code tham chiếu `Book_.title` không còn phù hợp.
- Kiểu `BigDecimal` của `price` được thể hiện rõ.
- IDE có thể autocomplete các thuộc tính.

### Cần phân biệt type-safe với mọi lỗi query đều được bắt ở compile time

Static metamodel giúp bắt nhiều lỗi tên/kiểu thuộc tính, nhưng không bảo đảm query hợp lệ trong mọi trường hợp:

- Mapping có thể sai so với schema DB.
- Một join có thể tạo kết quả lặp.
- Điều kiện AND/OR có thể sai logic.
- Provider có thể phát sinh SQL không tối ưu.
- Transaction/flush/fetch policy có thể khác dự đoán.

**Type-safe API giảm một nhóm lỗi nhưng không thay thế integration test.**

## 16. So sánh kiểu dữ liệu và vấn đề `get("...")`

Khi dùng:

```java
root.get("price")
```

compiler có thể thiếu đủ thông tin để suy ra kiểu mong muốn trong một số overload. Do đó ví dụ thường dùng:

```java
root.<BigDecimal>get("price")
```

Khi đó:

```java
Predicate minPrice = cb.greaterThanOrEqualTo(
    root.<BigDecimal>get("price"),
    new BigDecimal("100000")
);
```

Kiểu generic `BigDecimal` giúp chọn overload phù hợp của `greaterThanOrEqualTo`, vốn yêu cầu các biểu thức so sánh tương thích.

Nếu có static metamodel:

```java
Predicate minPrice = cb.greaterThanOrEqualTo(
    root.get(Book_.price),
    new BigDecimal("100000")
);
```

thường rõ hơn và ít cần ghi type witness tường minh.

### Không nhầm `Path.as(...)` với SQL CAST portable

Criteria API có phương thức `as(Class<X>)` để biểu diễn một expression dưới dạng kiểu yêu cầu, nhưng cách chuyển kiểu SQL cụ thể và việc một database có hỗ trợ chuyển đổi hay không phụ thuộc JPA version/provider. Không nên dùng `root.get("price").as(String.class)` như một mẹo thay đổi semantic dữ liệu không được kiểm thử.

Tốt hơn hết là model field đúng kiểu Java ngay từ đầu và dùng biểu thức so sánh tương thích.

## 17. Giá trị literal và ParameterExpression

Có hai cách xây predicate:

### Giá trị đặt trực tiếp khi xây Criteria

```java
Predicate p = cb.equal(root.get("published"), true);
```

JPA provider quyết định xử lý literal hoặc bound parameter ở SQL như thế nào.

### Tham số được khai báo và bind khi thực thi

```java
ParameterExpression<BigDecimal> minPrice =
    cb.parameter(BigDecimal.class, "minPrice");

Predicate filter = cb.greaterThanOrEqualTo(
    root.<BigDecimal>get("price"),
    minPrice
);

cq.select(root).where(filter);

TypedQuery<Book> query = em.createQuery(cq);

query.setParameter("minPrice", new BigDecimal("120000"));

List<Book> books = query.getResultList();
```

Có thể tạo nhiều TypedQuery thực thi với những parameter values khác nhau từ cấu trúc criteria phù hợp. Tuy nhiên, không dùng một `TypedQuery` mutable chung giữa nhiều threads.

### Bind tham số đúng kiểu

Nếu `minPrice` là `BigDecimal`, hãy bind BigDecimal tương ứng:

```java
query.setParameter("minPrice", new BigDecimal("120000"));
```

Không nên gửi chuỗi `"120000"` rồi hy vọng provider tự convert trong mọi tình huống.

### Vì sao cần quan tâm SQL injection?

Criteria API cấu trúc hóa tên thuộc tính và giá trị, giảm việc ghép chuỗi JPQL trực tiếp. Giá trị nghiệp vụ nên được đưa qua **parameter binding** khi phù hợp.

Tuy vậy, nếu xây sort/property names từ user input bằng chuỗi:

```java
root.get(userProvidedFieldName)
```

thì dù không phải SQL string injection trực tiếp theo nghĩa truyền thống, ứng dụng vẫn có nguy cơ cho phép truy cập hoặc sắp xếp theo thuộc tính ngoài whitelist, tạo query lỗi hoặc query quá nặng.

Hãy whitelist những thuộc tính được phép tìm kiếm/sắp xếp thay vì dùng trực tiếp một chuỗi bất kỳ từ HTTP request.

## 18. Điều kiện null, boolean và IN

### Kiểm tra null

```java
Predicate missingAuthor = cb.isNull(root.get("author"));
```

`isNull` diễn đạt kiểm tra null trong query:

```sql
WHERE author_id IS NULL
```

Không nên thay bằng:

```java
cb.equal(root.get("author"), null)
```

vì ngữ nghĩa `= NULL` trong SQL không tương đương `IS NULL` và cách provider xử lý null ở API có thể không phù hợp ý định. Dùng `isNull`/`isNotNull` để rõ ràng.

Trong entity ví dụ, author là bắt buộc, nên điều kiện missingAuthor thường không có kết quả nếu dữ liệu tuân thủ constraint. Điều kiện null hữu ích hơn cho các association hoặc field tùy chọn.

### Boolean

```java
Predicate published = cb.isTrue(root.get("published"));
Predicate unpublished = cb.isFalse(root.get("published"));
```

Hoặc:

```java
Predicate published = cb.equal(root.get("published"), true);
```

Hai cách biểu diễn lọc boolean cơ bản, tùy mong muốn về nullability/semantics. Với field primitive `boolean` không null, tình huống đơn giản hơn.

### IN với tập giá trị

Giả sử category là thuộc tính chuỗi trong một entity khác, hoặc muốn tìm Book có ID thuộc một tập:

```java
List<Long> ids = List.of(10L, 20L, 30L);

Predicate selected = root.get("id").in(ids);

cq.where(selected);
```

Với danh sách rỗng, không nên mặc định mọi provider/DB đều xử lý SQL `IN ()` như nhau. Hãy quyết định nghiệp vụ:

- Nếu danh sách rỗng nghĩa là không giới hạn, **không thêm predicate**.
- Nếu danh sách rỗng nghĩa là không có kết quả, thêm `cb.disjunction()` (điều kiện false).

Ví dụ:

```java
Predicate idFilter = ids.isEmpty()
    ? cb.disjunction()
    : root.get("id").in(ids);
```

Cách xử lý này rõ ràng hơn là để provider nhận một danh sách rỗng rồi hy vọng kết quả portable.

## 19. `conjunction()` và `disjunction()` khi xây điều kiện động

`CriteriaBuilder` có:

```java
Predicate alwaysTrue = cb.conjunction();
Predicate alwaysFalse = cb.disjunction();
```

Trong ngữ nghĩa kết hợp:

- `conjunction()` ban đầu tương đương điều kiện **true**, thích hợp làm điểm bắt đầu của chuỗi AND.
- `disjunction()` ban đầu tương đương điều kiện **false**, thích hợp làm điểm bắt đầu của chuỗi OR.

Ví dụ xây AND:

```java
Predicate where = cb.conjunction();

where = cb.and(
    where,
    cb.isTrue(root.get("published"))
);

if (minPrice != null) {
    where = cb.and(
        where,
        cb.greaterThanOrEqualTo(
            root.<BigDecimal>get("price"),
            minPrice
        )
    );
}

cq.where(where);
```

Ví dụ xây OR:

```java
Predicate any = cb.disjunction();

if (wantFree) {
    any = cb.or(
        any,
        cb.equal(root.get("price"), BigDecimal.ZERO)
    );
}

if (wantPremium) {
    any = cb.or(
        any,
        cb.greaterThan(
            root.<BigDecimal>get("price"),
            premiumThreshold
        )
    );
}
```

Nếu không có tiêu chí nào được bật, `disjunction()` vẫn false và query sẽ không trả kết quả. Đó có thể là đúng hoặc sai tùy nghiệp vụ; cần quyết định rõ.

Không trộn lẫn “không có điều kiện” với “điều kiện luôn false”.

## 20. Projection: chọn entity, một field, Tuple hay DTO

`CriteriaQuery<T>` cho phép mô tả nhiều kiểu kết quả.

### 20.1. Chọn entity

```java
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

cq.select(book);
```

Kết quả là Book entity, thường managed nếu được tải theo ngữ nghĩa JPA.

### 20.2. Chọn một field

```java
CriteriaQuery<String> cq = cb.createQuery(String.class);
Root<Book> book = cq.from(Book.class);

cq.select(book.get("title"));
```

Kết quả là String, không phải Book entity.

### 20.3. Chọn Tuple

```java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<Book> book = cq.from(Book.class);

cq.multiselect(
    book.get("id").alias("bookId"),
    book.get("title").alias("bookTitle")
);

List<Tuple> rows = em.createQuery(cq).getResultList();

for (Tuple row : rows) {
    Long id = row.get("bookId", Long.class);
    String title = row.get("bookTitle", String.class);
    System.out.println(id + ": " + title);
}
```

`Tuple` phù hợp cho query chọn các cột khác kiểu mà không muốn tạo DTO riêng. Nhưng thao tác đọc bằng alias dễ bị sai tên và cần quản lý kiểu.

### 20.4. Constructor projection bằng CriteriaBuilder

Định nghĩa DTO:

```java
public record BookSummary(Long id, String title) {}
```

Tạo query:

```java
CriteriaQuery<BookSummary> cq =
    cb.createQuery(BookSummary.class);

Root<Book> book = cq.from(Book.class);

cq.select(cb.construct(
    BookSummary.class,
    book.get("id"),
    book.get("title")
));

List<BookSummary> summaries =
    em.createQuery(cq).getResultList();
```

`cb.construct(...)` tạo **constructor projection**, tương đương ý tưởng với JPQL `SELECT NEW ...`. Constructor target phải phù hợp về số lượng và kiểu tham số; không phải mọi sai khác đều được phát hiện ở compile time khi dùng attribute names dạng chuỗi.

### Vì sao projection quan trọng?

Nếu màn hình chỉ cần ID và title, không nhất thiết load cả Book entity cùng toàn bộ state và association. DTO/scalar projection có thể giảm overhead của persistence context và dữ liệu truyền giữa DB và ứng dụng.

Lựa chọn kiểu `CriteriaQuery<T>` giúp mô tả chính xác kết quả muốn nhận.

## 21. DISTINCT khi join gây lặp Book

Giả sử Book có nhiều Tag qua association, và query join tới Tag:

```java
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

Join<Book, Tag> tag = book.join("tags");

cq.select(book)
  .where(cb.equal(tag.get("name"), "JAVA"));
```

Nếu một Book khớp nhiều hàng join hoặc query join thêm collection khác, danh sách kết quả có thể chứa lặp các tham chiếu tới cùng Book entity, tùy ngữ nghĩa query và provider.

Muốn loại trùng ở mức SELECT:

```java
cq.select(book).distinct(true);
```

Tương tự JPQL:

```sql
SELECT DISTINCT b FROM Book b JOIN b.tags t
```

Lưu ý:

- `distinct(true)` biểu đạt ý nghĩa loại trùng kết quả.
- SQL cụ thể hoặc cách provider de-duplicate có thể khác nhau.
- JOIN FETCH collection và pagination có các hạn chế riêng; không nên lấy `distinct(true)` làm giải pháp tuyệt đối cho mọi trường hợp.

Ví dụ `Tag` chỉ mô tả một association giả định bổ sung vào Book, không bắt buộc tồn tại trong entity mẫu đầu bài. Nếu dùng ví dụ này trong dự án, cần khai báo `Book.tags` và entity `Tag` phù hợp.

## 22. Sắp xếp và phân trang trong CriteriaQuery

Tạo thứ tự:

```java
cq.orderBy(
    cb.asc(book.get("price")),
    cb.desc(book.get("id"))
);
```

Ý nghĩa:

1. Sắp theo giá tăng dần.
2. Với giá bằng nhau, sắp ID giảm dần.

Phân trang không được cấu hình trực tiếp bằng `CriteriaQuery`, mà trên `TypedQuery`:

```java
TypedQuery<Book> query = em.createQuery(cq);

List<Book> page = query
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

Đây là một ví dụ phân chia vai trò rõ:

- `CriteriaQuery` mô tả **truy vấn** và ORDER BY.
- `TypedQuery` cấu hình **thực thi** như page offset, max results và parameter binding.

### Vì sao phải có ORDER BY ổn định?

Nếu chỉ phân trang mà không có thứ tự, database có thể trả các hàng theo một thứ tự không ổn định. Trong trường hợp dữ liệu thay đổi đồng thời, offset pagination còn có thể bỏ sót hoặc lặp record.

Nên có tiebreaker duy nhất, ví dụ ID:

```java
cq.orderBy(
    cb.asc(book.get("createdDate")),
    cb.asc(book.get("id"))
);
```

Với pagination trên join fetch collection, cần cân nhắc tách query lấy IDs và query fetch associations; không suy rằng `setMaxResults` luôn giới hạn chính xác số row join ở SQL theo trực giác.

## 23. Dynamic ORDER BY cần whitelist

Khi frontend gửi tham số:

```text
sort=price&direction=desc
```

Không nên dùng trực tiếp mọi tên field từ request:

```java
root.get(requestSortField)
```

dù Criteria API không ghép thẳng SQL string. Tên field không hợp lệ gây lỗi runtime; field không nên cho phép sắp xếp có thể tạo query đắt hoặc lộ thông tin về schema.

Một hướng an toàn:

```java
Expression<?> sortPath = switch (sortField) {
    case "title" -> book.get("title");
    case "price" -> book.get("price");
    case "createdDate" -> book.get("createdDate");
    default -> book.get("id");
};

Order order = descending
    ? cb.desc(sortPath)
    : cb.asc(sortPath);

cq.orderBy(order, cb.asc(book.get("id")));
```

Với Java 17 switch expression như trên, `sortField` phải khác null hoặc được chuẩn hóa trước. Phân quyền và validation cần xảy ra trước khi xây query.

Nếu có static metamodel, có thể sử dụng các thuộc tính `Book_.title`/`Book_.price` thay cho string literal.

## 24. Group By và Having

`CriteriaQuery` hỗ trợ aggregation. Ví dụ đếm số sách theo tác giả:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<Book> book = cq.from(Book.class);

Join<Book, Author> author =
    book.join("author", JoinType.INNER);

Expression<Long> bookCount = cb.count(book);

cq.multiselect(
    author.get("id").alias("authorId"),
    bookCount.alias("bookCount")
);

cq.groupBy(author.get("id"));

List<Tuple> result = em.createQuery(cq).getResultList();
```

JPQL tương ứng:

```sql
SELECT a.id, COUNT(b)
FROM Book b JOIN b.author a
GROUP BY a.id
```

Lọc các tác giả có ít nhất 5 sách:

```java
cq.having(
    cb.ge(bookCount, 5L)
);
```

Trong Criteria API:

- `cb.count(book)` tạo aggregate expression trả Long.
- `cq.groupBy(...)` tạo GROUP BY.
- `cq.having(...)` tạo điều kiện trên nhóm.
- `cq.multiselect(...)` mô tả kiểu output.

Không phải mọi field được chọn đều hợp lệ nếu query có GROUP BY. Các quy tắc group-by của JPQL/SQL vẫn áp dụng; không thể chọn tùy ý các cột không nằm trong nhóm hoặc aggregate.

### Count và kiểu kết quả

`cb.count(...)` trả `Expression<Long>`. Vì thế:

```java
CriteriaQuery<Long> countQuery =
    cb.createQuery(Long.class);

Root<Book> book = countQuery.from(Book.class);

countQuery.select(cb.count(book));

Long total = em.createQuery(countQuery).getSingleResult();
```

Đây là ví dụ rất rõ rằng `Root<Book>` không bắt buộc kéo theo `CriteriaQuery<Book>`.

## 25. Query đếm riêng cho pagination

Trong một API phân trang, thường cần:

1. Query nội dung trang: `CriteriaQuery<Book>`.
2. Query tổng số phần tử: `CriteriaQuery<Long>`.

Hai query có thể dùng cùng bộ lọc đầu vào nhưng **phải tạo Root/Predicate phù hợp với từng query**.

Ví dụ hàm hỗ trợ:

```java
private static List<Predicate> buildFilters(
        CriteriaBuilder cb,
        Root<Book> root,
        BookSearch input) {

    List<Predicate> predicates = new ArrayList<>();

    if (input.published() != null) {
        predicates.add(cb.equal(
            root.get("published"),
            input.published()
        ));
    }

    if (input.minPrice() != null) {
        predicates.add(cb.greaterThanOrEqualTo(
            root.<BigDecimal>get("price"),
            input.minPrice()
        ));
    }

    if (input.authorId() != null) {
        predicates.add(cb.equal(
            root.get("author").get("id"),
            input.authorId()
        ));
    }

    return predicates;
}
```

Query nội dung:

```java
CriteriaQuery<Book> dataQuery =
    cb.createQuery(Book.class);

Root<Book> dataRoot = dataQuery.from(Book.class);

dataQuery.select(dataRoot)
    .where(buildFilters(
        cb, dataRoot, input
    ).toArray(new Predicate[0]))
    .orderBy(cb.asc(dataRoot.get("id")));

List<Book> page = em.createQuery(dataQuery)
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
```

Query tổng:

```java
CriteriaQuery<Long> countQuery =
    cb.createQuery(Long.class);

Root<Book> countRoot = countQuery.from(Book.class);

countQuery.select(cb.count(countRoot))
    .where(buildFilters(
        cb, countRoot, input
    ).toArray(new Predicate[0]));

Long total = em.createQuery(countQuery)
    .getSingleResult();
```

Điểm quan trọng nhất: **không tái sử dụng `dataRoot` hay các Predicate gắn với `dataQuery` cho `countQuery`**. Mỗi query có cây biểu thức riêng. Reuse function mô tả logic, không reuse những node đã được tạo cho một query khác.

Khi query dữ liệu có join collection, count query có thể cần `countDistinct(countRoot)` hoặc một chiến lược tránh nhân bản record. Không mặc định copy tất cả join/fetch của data query sang count query.

## 26. Subquery và vai trò của Root trong truy vấn lồng

Criteria API hỗ trợ subquery, ví dụ tìm các Book có ít nhất một Review đạt điểm từ 4 trở lên.

Giả sử có entity `Review`:

```java
@Entity
public class Review {

    @Id
    private Long id;

    @ManyToOne
    private Book book;

    private int rating;

    protected Review() {}
}
```

Tạo subquery:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

Subquery<Long> sq = cq.subquery(Long.class);
Root<Review> review = sq.from(Review.class);

sq.select(cb.literal(1L))
  .where(
      cb.equal(review.get("book"), book),
      cb.greaterThanOrEqualTo(
          review.<Integer>get("rating"),
          4
      )
  );

cq.select(book)
  .where(cb.exists(sq));

List<Book> books = em.createQuery(cq).getResultList();
```

Ý tưởng JPQL:

```sql
SELECT b
FROM Book b
WHERE EXISTS (
    SELECT 1
    FROM Review r
    WHERE r.book = b
      AND r.rating >= 4
)
```

Những điểm cần nhớ:

- Query ngoài có Root `Book`.
- Subquery có Root `Review` của riêng nó.
- Điều kiện `r.book = b` liên kết subquery với entity ngoài.
- `cb.exists(sq)` tạo Predicate cho query ngoài.
- `CriteriaBuilder` tạo biểu thức cho cả hai.
- `CriteriaQuery` ngoài giữ cấu trúc SELECT cuối cùng, còn `Subquery` giữ cấu trúc SELECT lồng.

Một Root không tự tồn tại toàn cục. Nó luôn gắn với vị trí trong một query/subquery.

## 27. CriteriaQuery và CriteriaUpdate/CriteriaDelete khác nhau

`CriteriaBuilder` còn tạo:

```java
CriteriaUpdate<Book> update =
    cb.createCriteriaUpdate(Book.class);

CriteriaDelete<Book> delete =
    cb.createCriteriaDelete(Book.class);
```

Đây **không phải `CriteriaQuery<T>`** vì chúng mô tả bulk UPDATE/DELETE thay vì SELECT.

### Bulk update

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<Book> update =
    cb.createCriteriaUpdate(Book.class);

Root<Book> book = update.from(Book.class);

update.set("published", false)
      .where(cb.lessThan(
          book.<LocalDate>get("createdDate"),
          LocalDate.of(2020, 1, 1)
      ));

em.getTransaction().begin();

int affected = em.createQuery(update).executeUpdate();

em.getTransaction().commit();
```

### Bulk delete

```java
CriteriaDelete<Book> delete =
    cb.createCriteriaDelete(Book.class);

Root<Book> book = delete.from(Book.class);

delete.where(cb.isFalse(book.get("published")));

em.getTransaction().begin();

int affected = em.createQuery(delete).executeUpdate();

em.getTransaction().commit();
```

**Cảnh báo quan trọng:** Criteria bulk UPDATE/DELETE có ngữ nghĩa của bulk JPQL DML. Chúng không giống sửa từng managed entity rồi dirty checking:

- Có thể bỏ qua việc đồng bộ state của các managed entity đang nằm trong persistence context.
- Không tự thực thi mọi entity lifecycle callback/cascade như các thao tác per-entity.
- Versioning và optimistic locking không được áp dụng tự động giống cập nhật managed entity thông thường.
- Có thể khiến context giữ state stale sau bulk operation.
- Cần transaction phù hợp và phải xét ràng buộc foreign key.

Không dùng CriteriaDelete cho một use case xóa aggregate có cascade/orphanRemoval rồi kỳ vọng nó hoạt động giống `em.remove(rootEntity)`.

Bài này tập trung vào ba thành phần `CriteriaBuilder`, `CriteriaQuery`, `Root` cho SELECT; ví dụ bulk chỉ để xác định ranh giới vai trò. Ở cả SELECT và bulk DML, Root vẫn đại diện nguồn entity, nhưng object mô tả thao tác khác nhau.

## 28. Criteria API không làm thay đổi lifecycle entity

Khi query trả về entity:

```java
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);
cq.select(book);

Book result = em.createQuery(cq)
    .setMaxResults(1)
    .getResultStream()
    .findFirst()
    .orElse(null);
```

Nếu `result` không null, nó có thể là managed entity trong persistence context hiện tại. Việc dùng Criteria thay JPQL không thay đổi các quy tắc:

- Entity identity và first-level cache.
- Dirty checking.
- Lazy/eager fetch semantics theo mapping và query.
- Flush mode.
- Transaction isolation và locking.
- Cascade và orphanRemoval.
- Managed/detached lifecycle.

Nếu dùng `getResultStream()`, nên đóng stream bằng `try-with-resources` vì provider có thể giữ JDBC resources trong lúc duyệt:

```java
Book result;

try (Stream<Book> rows = em.createQuery(cq)
        .setMaxResults(1)
        .getResultStream()) {

    result = rows.findFirst().orElse(null);
}
```

Criteria chỉ là cách mô tả truy vấn. Nó không tự làm provider an toàn hơn về tài nguyên hoặc thread hơn so với JPQL.

## 29. Join fetch: lấy entity liên quan trước khi truy cập

Nếu một service cần Book và Author trong cùng phép đọc:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

book.fetch("author", JoinType.INNER);

cq.select(book);

List<Book> result = em.createQuery(cq).getResultList();
```

`root.fetch(...)` mô tả **fetch join**, không giống `root.join(...)` thông thường:

- `join(...)` thường dùng để biểu diễn association trong điều kiện và projection.
- `fetch(...)` khai báo fetch semantics để nạp association cùng query theo chiến lược phù hợp.

`Fetch<Book, Author>` không nên được cast sang `Join<Book, Author>` theo một quy tắc portable để vừa fetch vừa lọc bằng attribute; một số provider cho phép các extension/cast, nhưng không nên phụ thuộc nếu dự án yêu cầu JPA chuẩn.

Khi cần filter theo Author đồng thời load Author, có thể tạo join riêng cho Predicate và fetch riêng, sau đó kiểm tra SQL provider tạo ra. Nếu query bị join lặp hoặc không tối ưu, cân nhắc entity graph hoặc điều chỉnh query design.

### Fetch collection và pagination

Fetch join collection có thể làm nhân số hàng SQL và khiến phân trang phức tạp. Đừng gọi `setMaxResults(20)` trên một query fetch collection rồi mặc định database chỉ xử lý đúng 20 root entities theo cách hiệu quả nhất.

Một lựa chọn thường rõ ràng hơn: lấy page IDs trước, rồi fetch các Book/association cần thiết cho ID đó bằng query thứ hai.

## 30. CriteriaBuilder không phải SQL string builder

Một sai lầm tư duy là xem Criteria API chỉ như cách ghép chuỗi SQL thủ công:

```java
String where = "b.title = '" + userInput + "'";
```

Criteria API không yêu cầu tạo chuỗi WHERE theo cách đó. Thay vào đó:

```java
ParameterExpression<String> title =
    cb.parameter(String.class, "title");

cq.where(cb.equal(root.get("title"), title));

TypedQuery<Book> query = em.createQuery(cq);
query.setParameter("title", userInput);
```

Các thành phần được provider ánh xạ qua metadata entity model. Điều này giảm lỗi cú pháp trong quá trình ghép điều kiện, giúp code dễ tái sử dụng và dễ xác định cấu trúc hơn.

Tuy nhiên, đừng nhầm Criteria API là một lớp bảo vệ tự động khỏi mọi lỗi bảo mật:

- Điều kiện phân quyền có thể bị quên.
- Attribute path có thể bị lấy từ input chưa whitelist.
- `LIKE` pattern có thể bị người dùng điều khiển để mở rộng search.
- Page size có thể bị đặt rất lớn.
- Query động có thể tạo Cartesian product và quá nhiều JOIN.
- Provider có thể tạo SQL phức tạp, cần chỉ số DB phù hợp.

Query đúng về cú pháp chưa chắc đúng về phân quyền hoặc hiệu năng.

## 31. CriteriaBuilder, CriteriaQuery và Root trong ứng dụng phân tầng

Một cấu trúc phổ biến:

```text
Controller / API
      │
      ▼
BookSearchRequest
      │
      ▼
Service xác thực và phân quyền
      │
      ▼
Repository / Query component
      │
      ├── CriteriaBuilder
      ├── CriteriaQuery<Book>
      ├── Root<Book>
      ├── Predicates / Joins
      └── em.createQuery(...)
      │
      ▼
Book DTOs / paged result
```

Việc tạo query thường nằm ở repository/query component để:

- Không đặt trực tiếp logic persistence vào controller.
- Gom các quy tắc chuyển filter DTO thành Predicate.
- Tái sử dụng whitelisted sort/projection.
- Dễ unit test logic chuyển input và integration test query thực tế.
- Quản lý transaction và EntityManager đúng ranh giới.

### Một helper Predicate tái sử dụng

```java
public final class BookPredicates {

    private BookPredicates() {}

    public static Predicate published(
            CriteriaBuilder cb,
            Root<Book> book) {

        return cb.isTrue(book.get("published"));
    }

    public static Predicate minPrice(
            CriteriaBuilder cb,
            Root<Book> book,
            BigDecimal value) {

        return cb.greaterThanOrEqualTo(
            book.<BigDecimal>get("price"),
            value
        );
    }
}
```

Dùng:

```java
cq.where(cb.and(
    BookPredicates.published(cb, root),
    BookPredicates.minPrice(
        cb, root, new BigDecimal("120000")
    )
));
```

Nên **truyền CriteriaBuilder và Root hiện tại** cho helper. Không lưu static `Root<Book>` hay `Predicate` đã gắn query để dùng lại trên nhiều EntityManager/query khác.

## 32. Cẩn trọng khi tái sử dụng và sửa CriteriaQuery

`CriteriaQuery` là mô tả mutable trong lúc xây dựng. Ví dụ:

```java
cq.where(cb.isTrue(root.get("published")));

TypedQuery<Book> first = em.createQuery(cq);

// Sau đó sửa lại cq:
cq.where(cb.isFalse(root.get("published")));

TypedQuery<Book> second = em.createQuery(cq);
```

Không nên viết code phụ thuộc vào việc `first` sẽ tự đổi theo `cq` hoặc `first` hoàn toàn không bị ảnh hưởng trong mọi implementation. Hãy xây **CriteriaQuery riêng** cho những use case độc lập và coi mỗi query definition là hoàn chỉnh trước khi tạo executable query.

Tương tự, không chia sẻ một mutable CriteriaQuery/Root/TypedQuery giữa nhiều threads. Nếu phải sinh query theo request, tạo cấu trúc mới cho từng lời gọi trong context phù hợp.

Một số nhà cung cấp có cơ chế caching query plan, nhưng đó không có nghĩa ứng dụng nên dùng một instance CriteriaQuery mutable như singleton.

## 33. Criteria API và khả năng kết hợp với Specification

Trong Spring Data JPA, `Specification<T>` dựa trên các khái niệm tương tự:

```java
@FunctionalInterface
public interface Specification<T> {

    Predicate toPredicate(
        Root<T> root,
        CriteriaQuery<?> query,
        CriteriaBuilder criteriaBuilder
    );
}
```

Chữ ký trên diễn giải ý tưởng của Specification trong Spring Data JPA. Đây là abstraction framework, **không phải interface `Specification` thuộc Jakarta Persistence chuẩn**.

Ví dụ sử dụng trong Spring:

```java
Specification<Book> published = (root, query, cb) ->
    cb.isTrue(root.get("published"));

Specification<Book> minPrice = (root, query, cb) ->
    cb.greaterThanOrEqualTo(
        root.<BigDecimal>get("price"),
        new BigDecimal("100000")
    );

Specification<Book> combined =
    published.and(minPrice);
```

Lúc này dễ nhìn thấy lý do callback nhận đủ ba tham số:

- `root`: xác định thuộc tính của entity.
- `query`: cho phép điều chỉnh cấu trúc truy vấn khi phù hợp.
- `cb`: tạo Predicate và biểu thức.

Mặc dù Specification rất tiện, không nên sửa `query.orderBy(...)` hoặc `query.fetch(...)` tùy ý trong mọi Specification nhỏ nếu các thành phần đó được tái sử dụng cho count query/pagination; một số thao tác không phù hợp khi repository tạo count query.

Hiểu ba thành phần Criteria từ JPA gốc sẽ giúp sử dụng Specification đúng hơn.

## 34. Query vẫn chịu transaction và flush mode của JPA

Một query xây bằng Criteria:

```java
Book book = em.find(Book.class, 42L);
book.rename("Tên mới");

CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> root = cq.from(Book.class);

cq.select(root).where(
    cb.equal(root.get("title"), "Tên mới")
);

List<Book> result = em.createQuery(cq).getResultList();
```

Ở `FlushModeType.AUTO` trong persistence context đã tham gia transaction, provider phải bảo đảm những thay đổi pending có thể ảnh hưởng kết quả query được phản ánh trong việc xử lý query. Một cách thực hiện thường gặp là flush trước SELECT.

Với `FlushModeType.COMMIT`, ảnh hưởng của pending changes lên query trước commit không có cùng bảo đảm như AUTO.

Criteria API không làm thay đổi bản chất đó. `CriteriaBuilder` không quyết định transaction isolation; `Root` không làm entity detached trở lại managed; `CriteriaQuery` không tự đồng bộ state Java xuống DB.

Nếu một query gây lỗi unique constraint trước khi trả kết quả, nguyên nhân có thể là SQL ghi được flush trước query, không phải bản thân SELECT sai.

## 35. Kiểm thử truy vấn Criteria

Các method Criteria là API tạo cấu trúc, nhưng logic query vẫn cần integration test với JPA provider và database phù hợp.

Ví dụ JUnit với resource-local EntityManager:

```java
@Test
void findsPublishedBooksAboveMinimumPrice() {
    EntityManager em = emf.createEntityManager();

    try {
        CriteriaBuilder cb = em.getCriteriaBuilder();

        CriteriaQuery<Book> cq = cb.createQuery(Book.class);
        Root<Book> book = cq.from(Book.class);

        cq.select(book)
          .where(cb.and(
              cb.isTrue(book.get("published")),
              cb.greaterThanOrEqualTo(
                  book.<BigDecimal>get("price"),
                  new BigDecimal("150000")
              )
          ))
          .orderBy(cb.asc(book.get("id")));

        List<Book> books =
            em.createQuery(cq).getResultList();

        assertTrue(
            books.stream().allMatch(
                b -> b.isPublished()
                    && b.getPrice().compareTo(
                        new BigDecimal("150000")
                    ) >= 0
            )
        );
    } finally {
        em.close();
    }
}
```

Test trên minh họa assertion về điều kiện của dữ liệu trả về. Để tránh “test xanh khi query trả rỗng”, một integration test hoàn chỉnh cần seed fixture đã biết có ít nhất một kết quả và một số bản ghi không khớp, rồi assert chính xác ID dự kiến.

Các trường hợp nên kiểm tra:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Một điều kiện | Predicate được áp dụng đúng |
| Nhiều điều kiện AND | Không bị mất điều kiện khi gọi `where` |
| OR lồng AND | Đúng dấu ngoặc logic |
| Filter rỗng | Không vô tình trả dữ liệu ngoài quyền |
| LIKE chứa `%` hoặc `_` | Escape/validation theo yêu cầu |
| Min/max price | Biên đúng bằng giá trị giới hạn |
| Join Author | Không lẫn Book của tác giả khác |
| Nhiều Root | Không vô tình gây Cartesian product |
| Projection DTO | Constructor và kiểu kết quả khớp |
| Count/page | Tổng số đúng, không nhân bản do join |
| Sort | Thứ tự ổn định và field nằm trong whitelist |
| NULL | Dùng `isNull`/`isNotNull` đúng ngữ nghĩa |
| IN rỗng | Không có kết quả hay không áp dụng lọc theo chính sách |
| Bulk Update/Delete | Kiểm tra dữ liệu DB và state stale sau thao tác |
| Transaction/flush | Query đúng trong context/transaction phù hợp |

**Một query được tạo thành công bằng Criteria chưa có nghĩa điều kiện nghiệp vụ đã đúng.**

## 36. Những nhầm lẫn thường gặp

### Nhầm lẫn 1: CriteriaBuilder là Query

Sai. `CriteriaBuilder` là công cụ tạo các biểu thức và query definition; `CriteriaQuery` mới là cấu trúc SELECT query.

### Nhầm lẫn 2: Root là entity được tải

Sai. `Root<Book>` là biểu diễn Book trong FROM, không phải một Java Book đã được query trả về.

### Nhầm lẫn 3: `get("title")` trả giá trị title của một Book

Sai. Nó trả Path/Expression đại diện cho thuộc tính trong query, không phải String của một row cụ thể.

### Nhầm lẫn 4: Tạo CriteriaQuery là chạy SQL

Sai. Cần `em.createQuery(cq)` rồi thực thi qua `getResultList()`, `getSingleResult()` hoặc API terminal tương ứng.

### Nhầm lẫn 5: Gọi `where(...)` nhiều lần tự tạo AND

Sai. Mỗi lần thiết lập where restriction có thể thay thế restriction trước đó. Kết hợp Predicate bằng `cb.and` hoặc một mảng/list rồi gọi `where` đúng cách.

### Nhầm lẫn 6: `CriteriaQuery<Book>` yêu cầu `Root<Book>` duy nhất

Không. Kiểu kết quả và nguồn dữ liệu là hai khái niệm khác. `CriteriaQuery<Long>` có thể có `Root<Book>` để tính count.

### Nhầm lẫn 7: Cứ thêm Root để truy vấn bảng liên quan

Nhiều Root thường tạo nhiều nguồn độc lập/cross join. Nếu có association, dùng `root.join(...)` phù hợp.

### Nhầm lẫn 8: String-based path là compile-time safe

Không. `root.get("titel")` có thể chỉ gây lỗi runtime. Static metamodel giúp bắt lỗi thuộc tính tốt hơn.

### Nhầm lẫn 9: Dùng `equal(path, null)` thay `isNull`

Không nên. Dùng `cb.isNull(path)` để thể hiện SQL null semantics rõ ràng.

### Nhầm lẫn 10: `cb.construct(...)` luôn tạo managed entity

Không. Constructor projection thường tạo DTO. Ngay cả khi constructor target có cấu trúc giống entity, không được coi kết quả DTO là managed entity.

### Nhầm lẫn 11: Criteria API chống mọi lỗi bảo mật

Không. Phải vẫn kiểm tra phân quyền, whitelist sort/filter, giới hạn page size và escape LIKE wildcard khi phù hợp.

### Nhầm lẫn 12: Criteria luôn nhanh hơn JPQL

Không. Provider dịch cả hai sang SQL theo mapping. Hiệu năng phụ thuộc SQL thực tế, index, join, projection và lượng dữ liệu.

### Nhầm lẫn 13: CriteriaQuery có thể tái dùng Root của query khác

Không. Root/Path/Join là các node thuộc cây truy vấn cụ thể. Dùng helper nhận Root hiện tại thay vì giữ Root global.

### Nhầm lẫn 14: Criteria JOIN FETCH luôn phù hợp phân trang

Không. Fetch collection có thể nhân bản rows và làm pagination phức tạp. Cần query design phù hợp.

### Nhầm lẫn 15: CriteriaDelete tương đương `em.remove(entity)`

Không. Bulk delete có những semantics khác về cascade, callbacks và persistence context.

### Nhầm lẫn 16: Criteria API không bị flush trước truy vấn

Sai. Nó vẫn chịu flush mode và transaction semantics như JPQL.

## 37. Bài tập thực hành

### Bài tập 1: Nhận diện ba vai trò

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> book = cq.from(Book.class);

cq.where(cb.isTrue(book.get("published")));
```

**Câu hỏi:** Dòng nào tạo builder, dòng nào định nghĩa SELECT query và dòng nào tạo nguồn FROM?

**Đáp án:** `getCriteriaBuilder` tạo builder; `createQuery(Book.class)` tạo CriteriaQuery trả Book; `cq.from(Book.class)` tạo Root đại diện Book trong FROM.

### Bài tập 2: Chuyển JPQL sang Criteria

JPQL:

```sql
SELECT b FROM Book b
WHERE b.price < :maxPrice
ORDER BY b.title
```

Một cách viết:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Book> cq = cb.createQuery(Book.class);
Root<Book> b = cq.from(Book.class);

ParameterExpression<BigDecimal> max =
    cb.parameter(BigDecimal.class, "maxPrice");

cq.select(b)
  .where(cb.lessThan(b.<BigDecimal>get("price"), max))
  .orderBy(cb.asc(b.get("title")));

List<Book> result = em.createQuery(cq)
    .setParameter("maxPrice", new BigDecimal("200000"))
    .getResultList();
```

### Bài tập 3: Vì sao điều kiện đầu biến mất?

```java
cq.where(cb.isTrue(root.get("published")));
cq.where(cb.equal(root.get("author").get("id"), 10L));
```

**Câu hỏi:** Vì sao query chỉ lọc author?

**Đáp án:** Lệnh `where` thứ hai thay thế restriction đầu. Cần dùng `cb.and(...)` hoặc danh sách Predicate rồi gắn một lần.

### Bài tập 4: Root khác kiểu kết quả

```java
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Book> book = cq.from(Book.class);
cq.select(cb.count(book));
```

**Câu hỏi:** Có phải sai generic không?

**Đáp án:** Không. Root là Book, nhưng phần SELECT trả Long từ count aggregate.

### Bài tập 5: Filter động

Yêu cầu người dùng có thể chọn `minPrice` và `published`. Nếu cả hai null thì dùng chính sách cho phép tìm tất cả.

**Gợi ý:** Tạo `List<Predicate>`, thêm điều kiện cho từng field khác null, sau đó gọi `where(predicates.toArray(new Predicate[0]))`. Nhớ bổ sung điều kiện phân quyền bắt buộc nếu domain đa tenant.

### Bài tập 6: Join theo tác giả

**Yêu cầu:** Tìm Book của Author có tên “An”.

```java
Join<Book, Author> author =
    root.join("author", JoinType.INNER);

cq.where(cb.equal(author.get("name"), "An"));
```

**Đáp án:** Join đại diện association từ Book tới Author; Root Book vẫn là nguồn kết quả khi `cq.select(root)`.

### Bài tập 7: Xử lý IN rỗng

```java
List<Long> ids = List.of();
Predicate p = root.get("id").in(ids);
```

**Câu hỏi:** Nếu danh sách rỗng nghĩa là không có bản ghi nào được phép, nên làm gì?

**Đáp án:** Dùng `cb.disjunction()` hoặc trả kết quả rỗng sớm theo thiết kế. Không phụ thuộc SQL `IN ()` của provider/database.

### Bài tập 8: Projection DTO

**Yêu cầu:** Chỉ đọc ID và title của Book.

**Gợi ý đáp án:** Dùng `CriteriaQuery<BookSummary>` và `cb.construct(BookSummary.class, root.get("id"), root.get("title"))`. Không cần load toàn Book khi chỉ cần hai field.

### Bài tập 9: Count query

**Câu hỏi:** Vì sao không dùng lại Predicate đã tạo từ `dataRoot` cho `countRoot`?

**Đáp án:** Predicate/Path tham chiếu cây query gốc. Count query cần Root riêng; tạo lại Predicate bằng helper nhận root của count query.

### Bài tập 10: Tìm Book có Review tốt

**Yêu cầu:** Tìm Book có ít nhất một Review rating >= 4.

**Gợi ý:** Dùng `Subquery<Long>` với `Root<Review>`, liên kết `review.book = outerBook` và predicate rating, rồi gắn `cb.exists(subquery)` vào query ngoài.

### Bài tập 11: Criteria UPDATE

**Câu hỏi:** Sau `CriteriaUpdate<Book>`, tại sao Book managed đã tải có thể còn state cũ?

**Đáp án:** Bulk DML tác động DB trực tiếp và không tự đồng bộ toàn bộ managed state trong persistence context. Cần transaction/context strategy phù hợp.

### Bài tập 12: Dynamic sort

Người dùng gửi `sortField = "price"`.

**Câu hỏi:** Có nên gọi `root.get(sortField)` với bất kỳ string từ HTTP request không?

**Đáp án:** Không. Whitelist trường được phép, giới hạn page size và kiểm soát truy vấn. Criteria không tự thay business authorization.

## 38. Checklist khi xây Criteria query

Trước khi xem một Criteria query hoàn chỉnh, hãy tự hỏi:

1. **`CriteriaBuilder` đã được lấy từ JPA API phù hợp chưa?**
2. **Kiểu `CriteriaQuery<T>` có khớp với Selection/DTO dự kiến không?**
3. **Root có được tạo từ chính CriteriaQuery hiện tại không?**
4. **Các Path có truy cập đúng thuộc tính entity không?**
5. **Có cần static metamodel để tăng type safety không?**
6. **Điều kiện AND/OR đã được nhóm đúng chưa?**
7. **Có bị gọi `where` nhiều lần làm mất điều kiện cũ không?**
8. **Các tham số có được bind đúng kiểu không?**
9. **Null dùng `isNull`/`isNotNull` khi phù hợp chưa?**
10. **Danh sách IN rỗng được xử lý theo nghiệp vụ chưa?**
11. **LIKE wildcard và Unicode/locale được xử lý theo yêu cầu chưa?**
12. **Có bắt buộc điều kiện tenant/authorization không?**
13. **Dynamic field và sort có whitelist không?**
14. **Join có sử dụng association mapping thay vì thêm Root không cần thiết không?**
15. **LEFT JOIN có bị WHERE làm mất các row không khớp không?**
16. **Distinct có cần thiết vì join collection không?**
17. **Projection có tránh tải entity không cần thiết không?**
18. **ORDER BY có ổn định cho pagination không?**
19. **Count query có dùng Root/Predicate riêng không?**
20. **Có dùng fetch join collection cùng pagination gây vấn đề không?**
21. **Có vô tình dùng CriteriaUpdate/Delete thay cho lifecycle per-entity không?**
22. **Query có thể gây flush pending changes trong transaction không?**
23. **CriteriaQuery/TypedQuery có được tạo và dùng trong phạm vi thread/request phù hợp không?**
24. **Đã có integration test với dữ liệu đúng và sai điều kiện chưa?**
25. **SQL thực tế, index và số round trip có được kiểm tra khi query quan trọng về hiệu năng không?**

Bộ câu hỏi này bao quát những rủi ro thường gặp khi sử dụng bộ ba CriteriaBuilder–CriteriaQuery–Root trong repository thực tế.

## Kết luận

**`CriteriaBuilder`, `CriteriaQuery` và `Root` giữ ba vai trò khác nhau nhưng bổ sung cho nhau trong JPA Criteria API.**

- **`CriteriaBuilder`** là công cụ xây query definition và các thành phần như `Predicate`, `Expression`, phép so sánh, aggregate, order và constructor projection.
- **`CriteriaQuery<T>`** biểu diễn cấu trúc **SELECT query** và kiểu kết quả `T`, kết nối SELECT với FROM, WHERE, ORDER BY, GROUP BY, HAVING và DISTINCT.
- **`Root<X>`** đại diện entity nguồn `X` trong **FROM**, là điểm bắt đầu cho các đường dẫn thuộc tính `Path` và quan hệ `Join`.

Quy trình điển hình là **lấy CriteriaBuilder → tạo CriteriaQuery → khai báo Root → tạo điều kiện/selection → lắp vào query → tạo TypedQuery bằng EntityManager → bind tham số và thực thi**. Ba đối tượng đầu chỉ giúp mô tả truy vấn; không tự làm database chạy SQL ngay khi chúng được tạo.

Khi query có nhiều bộ lọc tùy chọn, Criteria API đặc biệt hữu ích vì cho phép lắp Predicate có cấu trúc thay vì nối chuỗi JPQL. Tuy nhiên, cần hiểu đúng phạm vi của Root trong từng query, cách `where` thay thế restriction cũ, khác biệt giữa `Root<Book>` và `CriteriaQuery<Long>`, cũng như giới hạn của static metamodel, projection, join và bulk DML.

Hãy luôn tự hỏi: **“Builder đang tạo biểu thức gì? Query sẽ trả kiểu kết quả nào? Root này đại diện entity nào trong FROM, và những điều kiện có thật sự gắn vào đúng cây truy vấn hay không?”**. Nếu trả lời được bốn câu hỏi đó, bạn đã nắm nền tảng quan trọng nhất để xây dựng Criteria query rõ ràng, an toàn và dễ mở rộng.
