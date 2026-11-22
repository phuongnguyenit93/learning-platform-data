# Đọc kết quả qua getResultStream và quản lý tài nguyên liên quan

Khi học JPQL, chúng ta thường bắt đầu bằng `getResultList()`: thực thi truy vấn và nhận `List<T>` chứa các kết quả. Tuy nhiên, từ JPA 2.2 (và trong Jakarta Persistence), API truy vấn còn có `getResultStream()` để cung cấp kết quả dưới dạng Java `Stream<T>`.

Ví dụ:

```java
try (Stream<Book> books = entityManager.createQuery(
        "SELECT b FROM Book b WHERE b.published = true",
        Book.class
    ).getResultStream()) {

    books.forEach(book -> System.out.println(book.getTitle()));
}
```

Cú pháp trông đơn giản, nhưng có ba vấn đề cần hiểu kỹ:

1. **Stream là cách xử lý kết quả ở Java, không tự động đồng nghĩa dữ liệu được đọc từng hàng từ database.** Triển khai JPA có thể materialize danh sách trước rồi trả `List.stream()`; một số provider có thể cung cấp cơ chế streaming/cursor riêng.
2. **Stream có thể giữ tài nguyên sống trong lúc duyệt**, chẳng hạn JDBC `ResultSet`, `Statement` và `Connection` thông qua provider. Chỉ kết thúc phép duyệt không phải lúc nào cũng đủ để giải phóng mọi tài nguyên trong mọi tình huống.
3. **Stream phụ thuộc vòng đời của query, persistence context và transaction.** Nếu trả stream ra ngoài phạm vi `EntityManager`/transaction rồi mới duyệt, ứng dụng có thể gặp lỗi, mất dữ liệu chưa đọc, giữ connection quá lâu hoặc gây rò rỉ tài nguyên.

Bài **“Đọc kết quả qua getResultStream và quản lý tài nguyên liên quan”** thuộc chương **JPQL cơ bản** trong chủ đề **Data Persistence Relational Access ORM JPA**. Chúng ta sẽ phân tích ngữ nghĩa API, so sánh với `getResultList()`, viết code có `try-with-resources`, kiểm soát transaction/connection, phân trang, projection, memory, exception, kiểm thử và những quyết định thiết kế cho truy vấn lớn.

Các ví dụ sử dụng `jakarta.persistence` với Java 17+. Dự án JPA 2.2 cũ dùng `javax.persistence`; `getResultStream()` được bổ sung từ JPA 2.2, nên không áp dụng nguyên dạng cho những phiên bản JPA trước đó.

## 1. Vì sao JPQL cần thêm cách đọc kết quả bằng Stream?

Xét câu JPQL:

```java
TypedQuery<Book> query = em.createQuery(
    "SELECT b FROM Book b " +
    "WHERE b.published = true " +
    "ORDER BY b.id",
    Book.class
);
```

Cách thường gặp:

```java
List<Book> books = query.getResultList();

for (Book book : books) {
    process(book);
}
```

`getResultList()` trả một `List`, phù hợp khi cần:

- Dùng nhiều lần kết quả trong bộ nhớ.
- Lấy số phần tử bằng `size()`.
- Truy cập phần tử theo index.
- Trả danh sách DTO cho API.
- Xử lý số lượng bản ghi nhỏ hoặc đã được phân trang.

Nhưng nếu ứng dụng chỉ muốn duyệt kết quả theo luồng xử lý:

```java
try (Stream<Book> books = query.getResultStream()) {
    books.filter(Book::isPublished)
         .map(Book::getTitle)
         .forEach(System.out::println);
}
```

thì `Stream` giúp mô tả một **pipeline** gồm các phép biến đổi và terminal operation.

Ví dụ `filter`, `map`, `flatMap`, `findFirst`, `anyMatch`, `forEach`, `collect` là API **Java Stream**, không phải JPQL. Cần phân biệt hai tầng:

```text
JPQL                                  Java Stream
SELECT b FROM Book b ...             .map(Book::getTitle)
            │                        .filter(...)
            ▼                        .forEach(...)
Database / JPA provider ───────────► kết quả Java
```

**`getResultStream()` không làm JPQL thay đổi thành SQL cursor theo một hợp đồng portable.** Nó chỉ đưa kết quả của JPA query vào API Java Stream, với cách hiện thực cụ thể tùy provider.

## 2. Ví dụ entity Book

Ta dùng một entity có ID, tiêu đề, danh mục và trạng thái xuất bản.

```java
package com.example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, length = 60)
    private String category;

    @Column(nullable = false)
    private boolean published;

    protected Book() {}

    public Book(String title, String category, boolean published) {
        this.title = title;
        this.category = category;
        this.published = published;
    }

    public Long getId() { return id; }

    public String getTitle() { return title; }

    public String getCategory() { return category; }

    public boolean isPublished() { return published; }
}
```

DDL minh họa:

```sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    category VARCHAR(60) NOT NULL,
    published BOOLEAN NOT NULL
);
```

Cú pháp DDL thực tế có thể khác theo PostgreSQL, MySQL, SQL Server hoặc database khác; bảng ở đây chỉ để hiểu JPQL. Các ví dụ `getResultStream()` sử dụng entity đã được ánh xạ và một `EntityManager` đang hoạt động.

## 3. `getResultList()` và `getResultStream()` khác nhau ở đâu?

### Đọc bằng List

```java
List<Book> books = em.createQuery(
    "SELECT b FROM Book b WHERE b.published = true",
    Book.class
).getResultList();

for (Book book : books) {
    System.out.println(book.getTitle());
}
```

Về phía application, `List` là collection đã có khi method trả về; ứng dụng có thể duyệt nhiều lần. Với query trả về entity, các Book có thể là managed instances thuộc persistence context.

### Đọc bằng Stream

```java
try (Stream<Book> books = em.createQuery(
        "SELECT b FROM Book b WHERE b.published = true",
        Book.class
    ).getResultStream()) {

    books.map(Book::getTitle)
         .forEach(System.out::println);
}
```

Về phía application, `Stream` biểu diễn một dòng xử lý **chỉ tiêu thụ một lần**. Ta có thể ghép `map`, `filter` và các terminal operations của Java Stream.

### So sánh

| Tiêu chí | `getResultList()` | `getResultStream()` |
| --- | --- | --- |
| Kiểu kết quả | `List<T>` | `Stream<T>` |
| Có thể dùng lại cùng kết quả? | Thường có thể duyệt List nhiều lần | Stream chỉ được tiêu thụ một lần |
| Cách xử lý | Vòng lặp, Collection API | Stream pipeline và terminal operation |
| Có bảo đảm dữ liệu đọc từng hàng từ DB? | Không | **Cũng không** |
| Có thể dùng với `map`/`filter`? | Có, qua `list.stream()` | Có ngay trên kết quả |
| Có thể giữ tài nguyên JDBC khi trả về? | Provider thường hoàn tất query trước khi trả List | **Có thể**, tùy provider và cách hiện thực stream |
| Có cần `try-with-resources` cho bản thân kết quả? | List không phải AutoCloseable | **Nên dùng**, vì Stream là AutoCloseable |
| Có giới hạn số hàng ở SQL nếu gọi `stream.limit(n)`? | Không áp dụng trực tiếp | Không có bảo đảm pushdown sang SQL |
| Phù hợp số bản ghi nhỏ/đã phân trang | Có | Có, nhưng chưa chắc đem lại lợi ích |
| Phù hợp duyệt tập lớn | Cần phân trang/batching | Có thể hữu ích, nhưng phải xét provider/cursor/memory |

Một cách nhìn đúng: `getResultStream()` là **API xử lý kết quả**, không phải lời hứa hiệu năng.

## 4. Điểm quan trọng nhất: Stream không chắc là JDBC streaming

Trong JPA 2.2, `getResultStream()` có triển khai mặc định tương đương ý tưởng:

```java
default Stream<T> getResultStream() {
    return getResultList().stream();
}
```

Đây là **mô tả ngữ nghĩa mặc định**, không phải source code đầy đủ phải có ở mọi provider. Nhà cung cấp JPA có thể override để hỗ trợ phương thức riêng, chẳng hạn đọc từ JDBC cursor hoặc cơ chế cuộn kết quả.

Hệ quả có hai nhánh:

### Nhánh A: Provider materialize List trước

```text
Database
    │
    ▼
SELECT lấy kết quả
    │
    ▼
Provider tạo List<Book> đầy đủ
    │
    ▼
List.stream()
    │
    ▼
Java pipeline
```

Nếu query trả về 500.000 Book, provider có thể đã tạo danh sách lớn trước khi code gọi `.limit(10)`.

```java
try (Stream<Book> books = query.getResultStream()) {
    books.limit(10).forEach(this::process);
}
```

Trong trường hợp này, `limit(10)` chỉ giới hạn **10 phần tử được xử lý ở Java**, không thay đổi việc provider đã tải bao nhiêu hàng từ DB.

### Nhánh B: Provider hỗ trợ đọc tăng dần

```text
Database cursor / JDBC ResultSet
             │
             ▼
Provider đọc hàng theo nhu cầu
             │
             ▼
Stream<Book>
             │
             ▼
Java pipeline
```

Cách này có thể giảm việc materialize toàn bộ result list trong Java, nhưng lại giữ tài nguyên SQL sống cho đến khi duyệt và đóng stream.

Tuy nhiên, còn phụ thuộc:

- JDBC driver có hỗ trợ cursor/fetch size thích hợp không.
- Transaction có đang sống không.
- Provider chuyển `ResultSet` thành entities như thế nào.
- Persistence context có giữ tất cả managed entities đã đọc không.
- Query có join fetch collection hoặc mapping gây materialize nhiều dữ liệu không.
- Cache, pagination, driver buffering và transaction isolation.

**Không đồng nhất “Stream Java lười tính toán” với “database chỉ trả đúng số hàng đã tiêu thụ”.** Đây là hai tầng khác nhau và không có bảo đảm tối ưu hóa xuyên tầng.

## 5. Đọc kết quả đúng bằng `try-with-resources`

Vì `Stream<T>` mở rộng `BaseStream<T, ?>` và `BaseStream` là `AutoCloseable`, ta có thể dùng `try-with-resources`.

```java
try (Stream<Book> stream = em.createQuery(
        "SELECT b FROM Book b " +
        "WHERE b.published = true " +
        "ORDER BY b.id",
        Book.class
    ).getResultStream()) {

    stream.forEach(book -> {
        System.out.println(book.getId() + ": " + book.getTitle());
    });
}
```

Khi đi ra khỏi `try`, Java gọi `stream.close()`, kể cả khi terminal operation phát sinh exception. Nếu provider gắn thao tác dọn `ResultSet`/statement/cursor vào việc đóng stream, cơ chế đó có cơ hội giải phóng tài nguyên ngay.

### Vì sao không chỉ dùng `forEach()`?

```java
Stream<Book> books = query.getResultStream();

books.forEach(this::process);
```

Đoạn trên chạy được trong nhiều trường hợp, nhưng **không bảo đảm ứng dụng đã đóng stream**. Java Stream không được yêu cầu tự động gọi `close()` sau terminal operation.

Nếu provider đang giữ JDBC cursor, việc không đóng có thể kéo dài thời gian giữ:

- `ResultSet`.
- `PreparedStatement`.
- JDBC connection hoặc connection lease.
- Server-side cursor và transaction resources.

Một số provider/driver có thể tự dọn vào lúc duyệt đến cuối, nhưng không nên viết code dựa trên một giả định không portable, đặc biệt khi có exception hoặc short-circuit operation.

### `close()` có thay thế `EntityManager.close()` không?

Không. Chúng quản lý những phạm vi tài nguyên khác nhau:

```text
EntityManager / persistence context / transaction
              │
              └── Query
                    │
                    └── Stream kết quả
                          │
                          └── Có thể giữ JDBC cursor

Đóng Stream: dọn tài nguyên gắn với kết quả stream.
Đóng EntityManager: kết thúc application-managed EntityManager/context.
Commit/Rollback: kết thúc transaction.
```

Cần bảo đảm **cả ba ranh giới** phù hợp: stream, persistence context và transaction.

## 6. Mẫu đầy đủ với application-managed EntityManager

Trong môi trường resource-local, một mẫu truy vấn đọc an toàn:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

public final class BookReader {

    private final EntityManagerFactory emf;

    public BookReader(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public List<String> readPublishedTitles() {
        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            List<String> titles;

            try (Stream<String> stream = em.createQuery(
                    "SELECT b.title FROM Book b " +
                    "WHERE b.published = true " +
                    "ORDER BY b.id",
                    String.class
                ).getResultStream()) {

                titles = stream.toList();
            }

            em.getTransaction().commit();
            return titles;
        } catch (RuntimeException ex) {
            if (em.getTransaction().isActive()) {
                try {
                    em.getTransaction().rollback();
                } catch (RuntimeException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
```

Luồng:

1. Tạo `EntityManager`.
2. Bắt đầu transaction phù hợp với provider/driver.
3. Tạo JPQL typed query.
4. Nhận stream trong `try-with-resources`.
5. **Tiêu thụ stream trước khi transaction/context kết thúc**.
6. Đóng stream, kể cả có exception.
7. Commit nếu toàn bộ thao tác thành công; rollback khi thất bại.
8. Đóng `EntityManager` trong `finally`.
9. Trả về dữ liệu đã materialize an toàn cho caller.

Ví dụ này chủ động dùng transaction ngay cả khi thao tác chỉ đọc, vì cursor-streaming trên một số provider/driver có yêu cầu transaction đang hoạt động. JPA có thể cho phép nhiều truy vấn đọc ngoài transaction, nhưng **không nên giả định mọi cơ chế stream/cursor đều hoạt động tốt sau khi context hoặc connection đã kết thúc**.

### Một lưu ý về bộ nhớ

Ở ví dụ này, `stream.toList()` lại materialize **toàn bộ danh sách String**. Cách đó an toàn khi kết quả được giới hạn hoặc nhỏ, nhưng không phải giải pháp xử lý tập dữ liệu khổng lồ bằng bộ nhớ hằng.

Nếu mục tiêu là xử lý từng bản ghi mà không giữ hết, hãy làm việc bên trong `try` và ghi kết quả tới sink có kiểm soát, hoặc dùng phân trang/batch.

## 7. Không trả Stream từ method đã đóng EntityManager

Anti-pattern thường gặp:

```java
public Stream<Book> findBooks() {
    EntityManager em = emf.createEntityManager();

    try {
        return em.createQuery(
            "SELECT b FROM Book b",
            Book.class
        ).getResultStream();
    } finally {
        em.close();
    }
}
```

Method đã đóng `EntityManager` trước khi caller tiêu thụ stream. Nếu provider đang đọc tăng dần hoặc cần lazy-load association, traversal có thể gặp lỗi vì tài nguyên đã đóng.

Một anti-pattern khác trong Spring:

```java
@Transactional(readOnly = true)
public Stream<Book> findBooks() {
    return repository.findAllAsStream();
}
```

Nếu transaction chỉ gắn với method này, nó có thể kết thúc ngay khi method trả về, trong khi caller chưa tiêu thụ stream. `@Transactional` trên method **trả stream** không tự bảo đảm transaction sống trong suốt quá trình caller duyệt kết quả.

### Hai giải pháp tốt

**Giải pháp A: consume và đóng trong cùng method/transaction**

```java
@Transactional(readOnly = true)
public List<BookSummary> findSummaries() {
    try (Stream<Book> books = repository.streamPublishedBooks()) {
        return books.map(
            b -> new BookSummary(b.getId(), b.getTitle())
        ).toList();
    }
}
```

Method trả danh sách DTO đã có sẵn, không trả một stream đang phụ thuộc transaction. Tuy nhiên, với kết quả rất lớn, vẫn cần pagination để tránh materialize danh sách khổng lồ.

**Giải pháp B: xử lý bên trong callback nhận stream**

Một API ở tầng service có thể nhận hàm tiêu thụ:

```java
public void withPublishedBooks(Consumer<Stream<Book>> consumer) {
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        try (Stream<Book> books = em.createQuery(
                "SELECT b FROM Book b WHERE b.published = true",
                Book.class
            ).getResultStream()) {

            consumer.accept(books);
        }

        em.getTransaction().commit();
    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
```

Hợp đồng callback phải yêu cầu **tiêu thụ stream ngay bên trong callback**, không giữ hoặc trả stream ra để sử dụng sau. Với codebase lớn, có thể thiết kế API callback trên từng row hoặc DTO để tránh lộ đối tượng stream ở ranh giới tầng ứng dụng.

## 8. `try-with-resources` với short-circuit operation

Một Java stream không nhất thiết đi hết mọi phần tử. Các thao tác có thể dừng sớm:

- `findFirst()`.
- `findAny()`.
- `anyMatch(...)`.
- `allMatch(...)`.
- `noneMatch(...)`.
- `limit(n)` đi kèm terminal operation.

Ví dụ:

```java
Optional<Book> first;

try (Stream<Book> books = em.createQuery(
        "SELECT b FROM Book b WHERE b.category = :category " +
        "ORDER BY b.id",
        Book.class
    ).setParameter("category", "JAVA")
     .getResultStream()) {

    first = books.findFirst();
}
```

`findFirst()` có thể chỉ tiêu thụ một phần kết quả. Đối với provider dùng JDBC cursor, những phần chưa đọc có thể vẫn đang ở phía driver/server. `try-with-resources` cho phép đóng stream ngay khi không cần nữa.

### Vì sao `findFirst()` chưa đủ để tối ưu SQL?

```java
query.getResultStream().findFirst();
```

Không có bảo đảm provider đẩy `findFirst()` xuống SQL thành `LIMIT 1`. Với triển khai `getResultList().stream()`, tất cả hàng có thể đã được tải.

Nếu chỉ muốn một hàng, hãy giới hạn ở cấp JPA query:

```java
Optional<Book> first;

TypedQuery<Book> query = em.createQuery(
    "SELECT b FROM Book b " +
    "WHERE b.category = :category " +
    "ORDER BY b.id",
    Book.class
);
query.setParameter("category", "JAVA");
query.setMaxResults(1);

try (Stream<Book> books = query.getResultStream()) {
    first = books.findFirst();
}
```

`setMaxResults(1)` biểu diễn giới hạn query với JPA; provider sẽ tạo chiến lược SQL/pagination phù hợp thay vì phụ thuộc vào phép `Stream.limit(1)` ở Java.

## 9. `Stream.limit(n)` không thay thế `setMaxResults(n)`

Cặp code sau có ý nghĩa khác nhau:

**Giới hạn ở pipeline Java:**

```java
try (Stream<Book> books = em.createQuery(
        "SELECT b FROM Book b ORDER BY b.id",
        Book.class
    ).getResultStream()) {

    books.limit(20).forEach(this::processBook);
}
```

**Giới hạn ở query JPA:**

```java
TypedQuery<Book> query = em.createQuery(
    "SELECT b FROM Book b ORDER BY b.id",
    Book.class
);
query.setMaxResults(20);

try (Stream<Book> books = query.getResultStream()) {
    books.forEach(this::processBook);
}
```

Ở ví dụ thứ hai, `setMaxResults(20)` được provider xem là giới hạn kết quả query. Ở ví dụ thứ nhất, `limit(20)` là phép xử lý Java; có thể dừng duyệt sớm nếu provider cung cấp streaming, nhưng không bảo đảm giảm số hàng được DB/driver materialize.

### Tương tự với filter và sort

```java
stream.filter(book -> book.getCategory().equals("JAVA"));
stream.sorted(Comparator.comparing(Book::getTitle));
```

Hai phép toán trên diễn ra ở Java, sau khi JPA đã cung cấp các phần tử. Chúng không biến thành JPQL `WHERE` hoặc `ORDER BY` nhờ phép màu.

Ưu tiên:

```java
"SELECT b FROM Book b " +
"WHERE b.category = :category " +
"ORDER BY b.title"
```

để DB lọc/sắp xếp bằng index và query execution plan thích hợp.

**Tối ưu đầu tiên của truy vấn lớn là giảm dữ liệu tại query/database, không phải chuyển mọi thao tác sang Java Stream.**

## 10. Phân trang bằng JPQL thay vì đọc vô hạn

Một cách kiểm soát bộ nhớ với tập dữ liệu lớn là **pagination**:

```java
int pageSize = 100;
int offset = 0;

while (true) {
    TypedQuery<Book> query = em.createQuery(
        "SELECT b FROM Book b " +
        "WHERE b.published = true " +
        "ORDER BY b.id",
        Book.class
    );

    List<Book> page = query
        .setFirstResult(offset)
        .setMaxResults(pageSize)
        .getResultList();

    if (page.isEmpty()) {
        break;
    }

    for (Book book : page) {
        processBook(book);
    }

    offset += page.size();
}
```

Đây là ví dụ ý tưởng. Nếu `processBook` cập nhật dữ liệu, phải quản lý flush/clear và transaction boundaries cẩn thận; đồng thời số bản ghi có thể thay đổi giữa các trang.

### Offset pagination và dữ liệu đang thay đổi

Khi có nhiều transaction ghi dữ liệu, `OFFSET` có thể gặp bỏ sót/đọc trùng nếu hàng được thêm/xóa hoặc điều kiện sắp xếp thay đổi giữa các lần query.

Với một tác vụ quét liên tục theo khóa tăng dần, **keyset pagination** thường phù hợp hơn:

```java
Long lastId = 0L;
int batchSize = 100;

while (true) {
    List<Book> batch = em.createQuery(
        "SELECT b FROM Book b " +
        "WHERE b.published = true " +
        "AND b.id > :lastId " +
        "ORDER BY b.id",
        Book.class
    ).setParameter("lastId", lastId)
     .setMaxResults(batchSize)
     .getResultList();

    if (batch.isEmpty()) {
        break;
    }

    for (Book book : batch) {
        processBook(book);
    }

    lastId = batch.get(batch.size() - 1).getId();
}
```

Keyset pagination cũng có giả định: khóa sắp xếp phải ổn định, filter nên được thiết kế rõ và dữ liệu thay đổi đồng thời vẫn cần xử lý theo yêu cầu consistency. Không tự xem đây là snapshot cố định của toàn DB.

### Khi nào cần `getResultStream()` nữa?

Nếu query đã có `setMaxResults(100)`, dùng `getResultList()` rồi duyệt có thể dễ hiểu hơn và đủ tốt. `getResultStream()` không bắt buộc trong mọi tình huống; API phù hợp là API làm rõ nhất **vòng đời và chi phí** của thao tác.

## 11. Projection và DTO: giảm entity được quản lý

Khi query:

```java
SELECT b FROM Book b
```

JPA thường trả các `Book` managed, khiến persistence context theo dõi identity và state của chúng. Nếu duyệt rất nhiều entity, bộ nhớ vẫn có thể tăng dù provider đọc ResultSet theo luồng.

Nếu ứng dụng chỉ cần ID và title, nên cân nhắc projection.

### Projection thành giá trị scalar

```java
try (Stream<String> titles = em.createQuery(
        "SELECT b.title FROM Book b " +
        "WHERE b.published = true " +
        "ORDER BY b.id",
        String.class
    ).getResultStream()) {

    titles.forEach(this::writeTitle);
}
```

Đoạn này không tạo managed `Book` cho từng hàng vì query chỉ trả một thuộc tính scalar. Provider vẫn có thể materialize kết quả theo cách riêng, nhưng áp lực quản lý entity thường thấp hơn.

### Projection bằng JPQL constructor expression

Định nghĩa DTO:

```java
package com.example.dto;

public final class BookSummary {

    private final Long id;
    private final String title;

    public BookSummary(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
}
```

JPQL:

```java
TypedQuery<BookSummary> query = em.createQuery(
    "SELECT NEW com.example.dto.BookSummary(b.id, b.title) " +
    "FROM Book b " +
    "WHERE b.published = true " +
    "ORDER BY b.id",
    BookSummary.class
);

try (Stream<BookSummary> summaries = query.getResultStream()) {
    summaries.forEach(summary ->
        System.out.println(
            summary.getId() + ": " + summary.getTitle()
        )
    );
}
```

`NEW com.example.dto.BookSummary(...)` là **constructor expression của JPQL**, giúp tránh load toàn bộ Book entity và các state không cần thiết.

Một DTO mới tạo bằng constructor projection **không tự là managed entity**, ngay cả khi nó mang các giá trị cột của một entity. Cần phân biệt DTO và object entity khi dùng về sau.

### Vì sao không cứ stream entity rồi map DTO?

```java
try (Stream<Book> books = entityQuery.getResultStream()) {
    books.map(b -> new BookSummary(b.getId(), b.getTitle()))
         .forEach(this::processSummary);
}
```

Cách này cũng có thể dùng, nhưng provider có thể đã phải tạo và quản lý từng `Book` trước khi code map. JPQL constructor projection thường biểu đạt chính xác nhu cầu dữ liệu hơn.

## 12. Persistence context có thể tăng bộ nhớ dù JDBC đang stream

Đây là vấn đề rất dễ bỏ qua:

```text
JDBC ResultSet đọc tăng dần
           │
           ▼
JPA provider tạo managed Book
           │
           ▼
Persistence context giữ entity identity / state
           │
           ▼
Nhiều Book đã được xử lý vẫn có thể còn managed
           │
           ▼
Bộ nhớ tiếp tục tăng
```

`getResultStream()` có thể làm giảm lượng row buffered bởi provider/driver trong một số cấu hình, nhưng **không tự xóa entity đã đọc khỏi persistence context**.

Ví dụ:

```java
try (Stream<Book> books = query.getResultStream()) {
    books.forEach(book -> processBook(book));
}
```

Nếu hàng trăm nghìn Book trở thành managed, context có thể giữ nhiều object/snapshot. Kể cả khi `processBook()` không giữ reference, provider vẫn có thể duy trì dữ liệu để bảo đảm identity/dirty checking.

### Có nên `em.clear()` mỗi 100 hàng ngay khi đang stream?

Không nên mặc định làm vậy.

```java
AtomicInteger counter = new AtomicInteger();

try (Stream<Book> books = query.getResultStream()) {
    books.forEach(book -> {
        processBook(book);

        if (counter.incrementAndGet() % 100 == 0) {
            em.clear(); // Không portable như một quy tắc chung!
        }
    });
}
```

`clear()` detach tất cả managed entities; việc gọi trong lúc provider đang dùng result stream/cursor có thể tương tác phức tạp với lazy associations, managed graph, cache, flush, query execution và provider-specific behavior. Một số tổ hợp có thể chạy, một số có thể gây lỗi hoặc thay đổi ngữ nghĩa.

Nếu cần xử lý batch lớn, những chiến lược thường rõ ràng hơn là:

- Query scalar/DTO thay vì entity managed.
- Phân trang để mỗi batch có ranh giới context/transaction cụ thể.
- Flush/clear **giữa các batch** đã hoàn thành, không tùy tiện giữa một cursor đang hoạt động.
- Dùng API read-only, stateless hoặc scrollable result của provider khi có yêu cầu rõ và đã kiểm thử.
- Đặt giới hạn kích thước công việc/transaction.

Không có một cấu hình `getResultStream()` duy nhất bảo đảm bộ nhớ hằng trên mọi provider.

## 13. Vòng đời transaction ảnh hưởng đến JDBC cursor

Khi provider trả một stream gắn với JDBC cursor, nó có thể cần giữ connection và transaction trong suốt quá trình tiêu thụ.

Ví dụ thứ tự hợp lý:

```text
begin transaction
    │
    ▼
create query
    │
    ▼
getResultStream
    │
    ▼
consume stream đầy đủ hoặc dừng sớm
    │
    ▼
close stream
    │
    ▼
commit/rollback transaction
    │
    ▼
close EntityManager
```

Thứ tự sai:

```text
begin transaction
getResultStream
commit
close EntityManager
return stream
caller tiêu thụ stream  ← có thể lỗi / resource đã đóng
```

### Truy vấn SELECT có bắt buộc transaction không?

Chuẩn JPA cho phép nhiều query đọc ngoài transaction trong các trường hợp phù hợp. Nhưng hỗ trợ **streaming thực sự từ JDBC cursor** có thể cần transaction active tùy database/driver/provider. Ví dụ một số cơ chế cursor/fetch size của PostgreSQL yêu cầu connection không ở chế độ autocommit; MySQL có các điều kiện streaming riêng.

Vì vậy, cho nghiệp vụ duyệt nhiều hàng bằng `getResultStream()`:

- Đừng suy rằng “query đọc” luôn hoạt động tối ưu không cần transaction.
- Giữ transaction/context sống trong lúc tiêu thụ.
- Không kéo transaction quá dài chỉ vì muốn stream qua mạng cho client.
- Kiểm thử trên **đúng database và driver** của production.

Một transaction đọc chạy lâu có thể giữ snapshot/lock hoặc tài nguyên DB theo isolation và cấu hình, kể cả không có UPDATE.

## 14. Connection pool và nguy cơ rò rỉ tài nguyên

Một ứng dụng web thường dùng connection pool. Giả sử pool có 10 connection, mỗi request lấy stream dữ liệu nhưng không đóng:

```text
Request 1 ─► Stream A ─► JDBC Connection 1 đang bị giữ
Request 2 ─► Stream B ─► JDBC Connection 2 đang bị giữ
...
Request 10 ─► Stream J ─► JDBC Connection 10 đang bị giữ

Request 11 ─► chờ connection, có thể timeout
```

Nếu implementation giữ connection tới khi stream đóng, việc không close stream hoặc giữ stream quá lâu có thể làm cạn pool.

Biểu hiện thường gặp:

- Request mới đợi connection.
- Connection acquisition timeout.
- Số active connections tăng và không giảm.
- Database có nhiều server-side cursors/transactions tồn tại lâu.
- Hệ thống chậm dù CPU không cao.
- Lỗi xuất hiện sau nhiều request, khó tái hiện trong test đơn lẻ.

**Dùng try-with-resources là một biện pháp quản lý tài nguyên phòng ngừa, không phải bằng chứng rằng provider chắc chắn đang dùng cursor.**

### Đừng chỉ dựa vào Garbage Collector

Một stream bị bỏ quên có thể được GC trong tương lai, nhưng Java GC không bảo đảm tài nguyên JDBC được đóng kịp thời theo yêu cầu nghiệp vụ. Tài nguyên database là hữu hạn; cần ranh giới đóng chủ động.

Tương tự, không dựa vào connection pool sẽ tự “thu hồi” các connection đã được giữ bởi thao tác kéo dài để sửa lỗi quản lý tài nguyên của ứng dụng.

## 15. Ném exception khi đang duyệt stream

Stream có thể phát lỗi ở nhiều giai đoạn:

1. Khi tạo query.
2. Khi gọi `getResultStream()`.
3. Khi terminal operation bắt đầu.
4. Khi provider đọc một hàng tiếp theo.
5. Khi map entity/convert value.
6. Khi lazy-load association trong consumer.
7. Khi code trong `map`/`forEach` ném exception.
8. Khi đóng stream/cursor.

Ví dụ:

```java
try (Stream<Book> books = query.getResultStream()) {
    books.forEach(book -> {
        if (book.getTitle() == null) {
            throw new IllegalStateException("Invalid book title");
        }
        processBook(book);
    });
}
```

Nếu `processBook` ném exception, `try-with-resources` vẫn gọi `close()` khi thoát phạm vi.

### Exception có thể không ném tại dòng getResultStream

Nếu provider thực sự trì hoãn đọc dữ liệu, lỗi SQL hoặc mapping có thể chỉ xuất hiện khi consumer gọi `forEach`, `findFirst` hoặc `toList`. Vì thế một `try-catch` chỉ bọc `getResultStream()` mà không bao bọc traversal là chưa đủ.

Ví dụ sai:

```java
Stream<Book> books;

try {
    books = query.getResultStream();
} catch (PersistenceException ex) {
    handle(ex);
    return;
}

// Lỗi có thể xảy ra bên dưới:
books.forEach(this::processBook);
```

Hãy đặt toàn bộ **khởi tạo, tiêu thụ và đóng stream** trong ranh giới error handling/transaction phù hợp.

### Khi transaction đã lỗi

Nếu một `PersistenceException` hoặc lỗi DB khiến transaction rollback-only hoặc không thể tiếp tục, đừng cố đọc tiếp cùng stream hoặc dùng tiếp context như thể khỏe mạnh. Dừng duyệt, đóng stream, rollback theo transaction manager và kết thúc đơn vị công việc thất bại.

## 16. Mẫu truy vấn read-only với Spring

Trong Spring, một service có thể quản lý transaction:

```java
@Service
public class BookReportService {

    private final BookRepository bookRepository;

    public BookReportService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional(readOnly = true)
    public void exportTitles(Consumer<BookSummary> consumer) {
        try (Stream<BookSummary> rows =
                bookRepository.streamPublishedSummaries()) {

            rows.forEach(consumer);
        }
    }
}
```

Repository có thể khai báo:

```java
public interface BookRepository
        extends JpaRepository<Book, Long> {

    @Query(
        "SELECT NEW com.example.dto.BookSummary(b.id, b.title) " +
        "FROM Book b WHERE b.published = true ORDER BY b.id"
    )
    Stream<BookSummary> streamPublishedSummaries();
}
```

Đây là ví dụ **Spring Data JPA**, không phải API thuần Jakarta Persistence. Một số phần code (như `@Service`, `@Transactional`, `@Query` và repository interface) cần các thư viện Spring tương ứng.

Điểm thiết kế:

- Method service là ranh giới transaction.
- Repository trả stream, nhưng **service tiêu thụ trong transaction**.
- Service đóng stream trước khi transaction kết thúc.
- Không trả stream thẳng ra controller.
- `readOnly = true` là hint/semantics của framework và transaction manager, **không phải bảo đảm portable JPA rằng stream luôn giữ cursor hay entity không thể bị sửa**.

### Vì sao controller không nên nhận Stream<Book>?

Ví dụ nguy hiểm:

```java
@GetMapping("/books")
public Stream<Book> books() {
    return service.findBooksAsStream();
}
```

Framework HTTP có thể serialize response sau khi service method đã trả về, tức transaction/query resource đã kết thúc. Ngoài ra, trả trực tiếp entity còn có thể gây lazy loading, vòng tham chiếu và lộ dữ liệu nội bộ.

Nên trả DTO đã phân trang hoặc dùng cơ chế xuất dữ liệu chuyên dụng có phạm vi transaction và lifecycle được quản lý rõ ràng.

## 17. Không dùng Java parallel stream tùy tiện với JPA entity

JPA `EntityManager` và persistence context thông thường không thread-safe để ứng dụng truy cập đồng thời. Vì vậy:

```java
try (Stream<Book> books = query.getResultStream()) {
    books.parallel().forEach(book -> {
        processWithEntityManager(book); // Nguy cơ thread-safety!
    });
}
```

không phải pattern an toàn tổng quát.

Ngay cả khi Java Stream có thể parallelize một collection, JPA provider có thể đang:

- Đọc tuần tự từ JDBC cursor.
- Tạo managed entities trong cùng persistence context.
- Lazy-load associations trong consumer.
- Giữ connection và transaction trên một thread/context.
- Dựa vào cấu trúc internal state không hỗ trợ parallel traversal.

Parallel stream không làm SQL chạy song song một cách đúng đắn chỉ vì có `parallel()`.

Nếu muốn xử lý parallel:

1. Lấy tập ID hoặc DTO độc lập từ DB theo các partition.
2. Giao từng partition cho một worker có **EntityManager/transaction riêng** nếu cần truy cập persistence.
3. Không chia sẻ một `EntityManager` giữa threads.
4. Xác định locking/idempotency cho các update đồng thời.
5. Giới hạn concurrency theo connection pool và tài nguyên DB.

Nếu chỉ làm phép tính thuần Java trên DTO đã materialize, parallel processing có thể phù hợp hơn, nhưng vẫn phải cân nhắc chi phí và thứ tự.

## 18. Stream chỉ có thể tiêu thụ một lần

Ví dụ sai:

```java
Stream<Book> books = query.getResultStream();

long count = books.count();
books.forEach(System.out::println); // IllegalStateException.
```

Sau khi terminal operation `count()` đã tiêu thụ stream, không thể chạy `forEach()` tiếp trên chính stream đó. Java Stream không phải collection có thể reset.

Nếu cần nhiều phép thống kê hoặc duyệt nhiều lần:

- Dùng một query aggregate riêng trong DB.
- Hoặc materialize danh sách có giới hạn rồi dùng lại.
- Hoặc thực thi một query mới.
- Hoặc tính tất cả chỉ số trong một lần duyệt stream.

### Một lần duyệt để tính tổng

```java
LongSummaryStatistics stats;

try (Stream<Long> ids = em.createQuery(
        "SELECT b.id FROM Book b WHERE b.published = true",
        Long.class
    ).getResultStream()) {

    stats = ids.mapToLong(Long::longValue)
               .summaryStatistics();
}
```

Ví dụ dùng `LongSummaryStatistics` để tính count/min/max/sum trên ID, chỉ nhằm minh họa một terminal operation tổng hợp. Với aggregate trên database, JPQL `COUNT`, `MIN`, `MAX`, `SUM` thường tiết kiệm việc truyền mọi hàng hơn.

**Đừng stream toàn bộ hàng chỉ để đếm số bản ghi.** Hãy dùng query aggregate khi nhiệm vụ phù hợp:

```java
Long count = em.createQuery(
    "SELECT COUNT(b) FROM Book b WHERE b.published = true",
    Long.class
).getSingleResult();
```

## 19. `findFirst()` so với `getSingleResult()`

Cả hai đều có thể phục vụ nhu cầu nhận một kết quả, nhưng semantics khác nhau.

### `getSingleResult()`

```java
Book book = em.createQuery(
    "SELECT b FROM Book b WHERE b.id = :id",
    Book.class
).setParameter("id", 42L)
 .getSingleResult();
```

`getSingleResult()` theo quy tắc JPA có thể ném `NoResultException` khi không có kết quả và `NonUniqueResultException` khi có nhiều hơn một kết quả. Ở các phiên bản Jakarta Persistence mới, cũng có API tìm một kết quả hoặc null tùy hỗ trợ, nhưng ví dụ này tập trung vào `getResultStream()`.

### `findFirst()` trên Stream

```java
Optional<Book> first;

TypedQuery<Book> query = em.createQuery(
    "SELECT b FROM Book b " +
    "WHERE b.category = :category ORDER BY b.id",
    Book.class
);
query.setParameter("category", "JAVA");
query.setMaxResults(1);

try (Stream<Book> stream = query.getResultStream()) {
    first = stream.findFirst();
}
```

`findFirst()` trả `Optional.empty()` khi stream rỗng và chỉ chọn phần tử đầu tiên theo encounter order. Nó không tự bảo đảm tính duy nhất của kết quả gốc.

Nếu nghiệp vụ yêu cầu “chỉ được có một Book mang mã này”, hãy dựa vào unique constraint, điều kiện query và cách xử lý nhiều kết quả. Dùng `findFirst()` trên một query trả nhiều hàng có thể che giấu dữ liệu trùng.

### Vai trò của ORDER BY

Không có `ORDER BY`, “đầu tiên” theo quan sát DB có thể không ổn định. Nếu dùng `findFirst()` cho một lựa chọn nghiệp vụ, hãy xác định thứ tự rõ ràng trong JPQL:

```java
"SELECT b FROM Book b ORDER BY b.id ASC"
```

Kết hợp `setMaxResults(1)` nếu chỉ cần một hàng.

## 20. Stream từ query JOIN FETCH có thể gặp vấn đề gì?

Giả sử Book có collection `authors` hoặc `reviews`:

```java
SELECT b FROM Book b
LEFT JOIN FETCH b.reviews
```

Một Book với 30 reviews có thể tạo nhiều hàng SQL cho cùng một root Book. Kết hợp streaming và fetch join collection tạo thêm những vấn đề:

- Kết quả root entity có thể cần xử lý trùng.
- Provider có thể phải materialize/group nhiều hàng để tạo collection.
- Ordering, DISTINCT và pagination có quy tắc riêng.
- Streaming thực sự theo một root mỗi lần có thể không còn đơn giản.
- Một `Stream.limit(10)` ở Java không bảo đảm chỉ đọc 10 Book từ DB nếu mỗi Book được nhân nhiều hàng JOIN.

**Đừng tự cho rằng join fetch collection + getResultStream = xử lý dữ liệu lớn bằng bộ nhớ hằng.**

Nếu cần xử lý nhiều Book và thông tin quan hệ:

- Query ID/page trước.
- Fetch các association cần thiết theo một batch.
- Dùng DTO projection hoặc query chuyên biệt.
- Tránh collection fetch join cùng pagination một cách vô tư.
- Kiểm thử số SQL, memory và thứ tự thực tế.

### N+1 vẫn có thể xảy ra trong consumer

```java
try (Stream<Book> books = bookQuery.getResultStream()) {
    books.forEach(book -> {
        System.out.println(book.getPublisher().getName());
    });
}
```

Nếu `publisher` là lazy association chưa load, mỗi lần đọc có thể tạo truy vấn phụ. Stream không tự chữa N+1.

Cần chọn fetch plan phù hợp: JOIN FETCH quan hệ to-one, entity graph, batch fetching hoặc DTO projection; nhưng không biến mọi association thành EAGER vì có thể tải thừa dữ liệu.

## 21. Query flush và tương tác với pending changes

`getResultStream()` là một cách thực thi query và vẫn chịu quy tắc flush của JPA.

Ví dụ:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
book.rename("Tên mới");

try (Stream<Book> stream = em.createQuery(
        "SELECT b FROM Book b WHERE b.title = :title",
        Book.class
    ).setParameter("title", "Tên mới")
     .getResultStream()) {

    stream.forEach(this::processBook);
}

em.getTransaction().commit();
```

Với `FlushModeType.AUTO` và context đang tham gia transaction, provider phải bảo đảm những thay đổi pending có thể ảnh hưởng kết quả query được phản ánh theo ngữ nghĩa JPA. Một cách thực hiện thường gặp là flush trước khi query đọc dữ liệu.

Vì vậy, lỗi `UNIQUE`/`NOT NULL`/foreign key hoặc optimistic locking có thể xuất hiện **khi gọi getResultStream hoặc khi tiêu thụ stream**, dù code chưa tới commit.

### `COMMIT` có bảo đảm không flush trước stream không?

Không nên coi `FlushModeType.COMMIT` là lệnh cấm tuyệt đối mọi SQL ghi trước commit. Với COMMIT, ảnh hưởng của pending changes lên query trước commit không được bảo đảm như AUTO. Provider vẫn có thể thực hiện SQL sớm do ID generation, flush tường minh hoặc hành vi khác.

Ví dụ:

```java
query.setFlushMode(FlushModeType.COMMIT);
```

chỉ thay flush mode cho query theo API, không tự bảo đảm stream là read-only hay database chưa nhận bất kỳ UPDATE nào.

### Stream và transaction đang bị rollback-only

Nếu lỗi trong consumer hoặc provider khiến transaction không thể commit, dừng tiêu thụ, đóng stream, rollback và kết thúc context. Không dùng lại stream hoặc entity graph cũ để “thử tiếp” trên cùng transaction đã lỗi.

## 22. Fetch size: gợi ý cho driver, không phải giới hạn kết quả

Một số provider/JDBC driver hỗ trợ **fetch size** — số hàng muốn driver lấy theo mỗi đợt. Nó khác hoàn toàn với `setMaxResults()`.

- **`setMaxResults(n)`:** giới hạn số kết quả query.
- **Fetch size:** gợi ý cách driver/provider vận chuyển các hàng của result set.
- **Java Stream.limit(n):** giới hạn số phần tử được xử lý bởi pipeline, không bảo đảm giới hạn SQL.
- **Batch size DML:** số statement ghi được gom, không đồng nghĩa fetch size.

Ví dụ khái niệm:

```text
Query có 50.000 kết quả
             │
             ├── setMaxResults(100) → chỉ yêu cầu tối đa 100 kết quả
             │
             └── fetchSize(100)     → có thể lấy 100 hàng mỗi lượt
                                      nhưng vẫn có thể đọc 50.000
```

Jakarta Persistence không cung cấp một `Query.setFetchSize(int)` portable chuẩn cho mọi provider. Hibernate và một số ORM có hint/API mở rộng; JDBC có `Statement.setFetchSize(int)`. Nếu sử dụng một hint provider-specific, phải:

- Kiểm tra đúng provider và version.
- Hiểu driver có tôn trọng hint không.
- Hiểu điều kiện transaction/autocommit/cursor của database.
- Không sao chép hint sang provider khác rồi kỳ vọng tương đương.
- Xác nhận memory và connection behavior bằng integration test.

Không nên đưa ra một magic number như “fetch size 100 bảo đảm streaming”: kết quả phụ thuộc pipeline hoàn chỉnh từ JPA đến JDBC và DB.

## 23. Khi nào nên dùng JDBC thay vì JPQL Stream?

Nếu yêu cầu là quét hàng triệu bản ghi với tiêu chí rất chặt về bộ nhớ và tốc độ, JPA entity streaming có thể không phải công cụ phù hợp nhất.

Các lựa chọn tùy bài toán:

| Nhu cầu | Cách thường phù hợp |
| --- | --- |
| Hiển thị 20–100 Book | JPQL + `setMaxResults` + `getResultList` |
| Đọc vài nghìn DTO, xử lý một lượt | JPQL constructor projection + Stream/List |
| Xuất CSV có giới hạn và transaction rõ | JPQL Stream, try-with-resources hoặc paging |
| Quét rất nhiều hàng chỉ lấy một số cột | DTO/scalar projection, JDBC cursor hoặc batch |
| Cần chính xác memory/connection ở mức thấp | JDBC có quản lý `ResultSet`/`Statement`/`Connection` tường minh |
| Cần cập nhật hàng loạt | Batch update có transaction rõ, bulk JPQL DML hoặc JDBC batching |
| Xử lý phân tán/parallel | Chia ID/keyset ranges, mỗi worker có context/transaction riêng |
| Cần snapshot nhất quán qua quá trình dài | Transaction isolation/snapshot strategy riêng, không chỉ Stream |

JDBC có thể cho phép kiểm soát fetch size, cursor và row mapping trực tiếp, nhưng đổi lại ứng dụng phải tự quản lý connection, SQL, transaction và mapping. Không có công cụ nào luôn tốt nhất; chọn theo yêu cầu dữ liệu/consistency cụ thể.

## 24. Ví dụ xuất CSV an toàn hơn việc trả Stream ra controller

Giả sử cần xuất danh sách sách đã xuất bản sang một file CSV. Mục tiêu:

- Query chỉ lấy ID và title.
- Tiêu thụ stream trong transaction.
- Đóng stream trước khi đóng EntityManager.
- Không trả một stream JPA còn sống ra ngoài service.
- Đảm bảo writer được quản lý riêng.

Mẫu:

```java
public void exportPublishedBooks(
        EntityManagerFactory emf, Writer output) throws IOException {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        try (Stream<BookSummary> rows = em.createQuery(
                "SELECT NEW com.example.dto.BookSummary(b.id, b.title) " +
                "FROM Book b WHERE b.published = true ORDER BY b.id",
                BookSummary.class
            ).getResultStream()) {

            Iterator<BookSummary> iterator = rows.iterator();

            while (iterator.hasNext()) {
                BookSummary row = iterator.next();

                output.write(Long.toString(row.getId()));
                output.write(",");
                output.write(escapeCsv(row.getTitle()));
                output.write("\n");
            }
        }

        em.getTransaction().commit();
    } catch (IOException | RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            try {
                em.getTransaction().rollback();
            } catch (RuntimeException rollbackEx) {
                ex.addSuppressed(rollbackEx);
            }
        }
        throw ex;
    } finally {
        em.close();
    }
}
```

Đoạn ví dụ giả định có method `escapeCsv(String)` để trích xuất/quote các ký tự như dấu phẩy, dấu nháy kép và xuống dòng theo CSV specification. Method đó là logic đầu ra, không phải API của JPA.

### Vì sao dùng Iterator trong Stream?

`Stream.iterator()` là một terminal operation đặc biệt cung cấp cách duyệt kết quả, giúp viết code có checked exception `IOException` trong vòng lặp. Nếu dùng:

```java
rows.forEach(row -> output.write(...));
```

thì `Writer.write` ném `IOException` đã checked, nên lambda Consumer không thể ném trực tiếp nếu không có wrapper hoặc xử lý trong lambda.

Dù duyệt bằng iterator, stream vẫn cần đóng bằng try-with-resources.

### Hạn chế của xuất CSV trực tiếp trong một DB transaction

Nếu ghi CSV đến một HTTP response hoặc network sink rất chậm, transaction và JDBC cursor có thể bị giữ lâu. Nếu client ngắt kết nối, `IOException` làm luồng thoát, stream đóng và transaction rollback, nhưng dữ liệu đã gửi một phần cho client không thể “thu hồi”.

Với export lớn hoặc cần độ tin cậy cao, nên cân nhắc:

- Phân trang và ghi vào file tạm/đối tượng lưu trữ có kiểm soát.
- Tạo export job tách khỏi HTTP request.
- Dùng snapshot/version boundary phù hợp.
- Cho client tải artifact hoàn chỉnh sau khi job thành công.
- Có cơ chế resume/retry/idempotency nếu yêu cầu.

**Đừng kéo dài một JDBC cursor chỉ để chờ tốc độ tải xuống của client.**

## 25. Quản lý Writer, HTTP response và transaction

Trong ví dụ `exportPublishedBooks(...)`, `Writer output` được **caller cung cấp**, nên method không tự đóng writer nếu hợp đồng API định nghĩa caller sở hữu nó. Ngược lại, stream JPA được tạo bên trong method nên method phải đóng nó.

Đây là nguyên tắc **ownership tài nguyên**:

| Tài nguyên | Ai thường tạo? | Ai nên đóng? |
| --- | --- | --- |
| `EntityManager` application-managed | Service/repository method | Chính method, trong `finally` |
| `Stream<T>` từ `getResultStream()` | Method thực thi query | Chính phạm vi tiêu thụ, `try-with-resources` |
| JDBC `ResultSet` trong provider | JPA provider | Provider, qua lifecycle/close stream |
| JDBC Connection do pool cấp | ORM/transaction manager | ORM/manager trả lại pool theo lifecycle |
| `Writer` do caller truyền vào | Caller | Caller, trừ khi hợp đồng chuyển ownership |
| HTTP response stream | HTTP framework | Theo framework contract |
| Spring container-managed `EntityManager` | Framework | Không tự `close()` thủ công trong application code |

Nhầm ownership dễ dẫn tới hai lỗi đối lập: **không đóng tài nguyên mình sở hữu** hoặc **đóng tài nguyên do bên khác đang quản lý**.

Với container-managed JPA, không được gọi `em.close()` tùy tiện như resource-local. Nhưng stream do chính method mở vẫn nên được đóng trong phạm vi tiêu thụ.

## 26. Kiểm thử rằng stream được đóng

Lỗi rò rỉ stream có thể không biểu hiện ngay ở một test nhỏ. Một chiến lược kiểm thử gồm:

1. Chạy truy vấn trả stream trong transaction.
2. Đọc một phần rồi thoát sớm.
3. Bảo đảm `try-with-resources` được dùng.
4. Lặp lại nhiều lần với số connection pool nhỏ.
5. Xác minh các request/query tiếp theo vẫn lấy được connection.
6. Quan sát số active/idle connections và cursor nếu provider/database cung cấp.
7. Chạy kịch bản consumer ném exception giữa chừng.

### Test close bằng Java Stream hook

Để hiểu Java semantics của `close()`, có thể tạo stream thuần Java:

```java
@Test
void tryWithResourcesCallsCloseOnShortCircuit() {
    AtomicBoolean closed = new AtomicBoolean(false);

    try (Stream<Integer> values = Stream.of(1, 2, 3)
            .onClose(() -> closed.set(true))) {

        assertEquals(1, values.findFirst().orElseThrow());
    }

    assertTrue(closed.get());
}
```

Đây là test **Java Stream behavior**, không chứng minh JPA provider đóng JDBC connection đúng cách. Nó chỉ minh họa vì sao try-with-resources là lựa chọn tốt khi dừng sớm.

### Integration test với provider thật

Một test tích hợp có thể tạo nhiều Book, sau đó:

```java
for (int attempt = 0; attempt < 100; attempt++) {
    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        try (Stream<Book> books = em.createQuery(
                "SELECT b FROM Book b ORDER BY b.id",
                Book.class
            ).getResultStream()) {

            books.findFirst(); // Dừng sớm.
        }

        em.getTransaction().commit();
    } finally {
        em.close();
    }
}
```

Đoạn trên cần một schema/data fixture phù hợp và error handling/rollback nếu test muốn kiểm tra cả exception path. Test không nên chỉ assert “không ném exception”: nên quan sát pool metrics hoặc thử acquire connection tiếp theo dưới cấu hình giới hạn, bởi một số provider có thể materialize list nên không giữ cursor lâu.

### Test lỗi giữa quá trình duyệt

```java
@Test
void exceptionWhileConsumingStillClosesStream() {
    AtomicBoolean closed = new AtomicBoolean(false);

    assertThrows(IllegalStateException.class, () -> {
        try (Stream<Integer> values = Stream.of(1, 2, 3)
                .onClose(() -> closed.set(true))) {

            values.forEach(value -> {
                if (value == 2) {
                    throw new IllegalStateException("stop");
                }
            });
        }
    });

    assertTrue(closed.get());
}
```

Tương tự, đây là test thuần Java để chứng minh mechanics của `AutoCloseable`. Muốn khẳng định việc giải phóng JDBC resources, cần integration test với provider và driver của hệ thống.

## 27. Đừng lầm `try-with-resources` là giải pháp mọi vấn đề hiệu năng

Ví dụ:

```java
try (Stream<Book> books = em.createQuery(
        "SELECT b FROM Book b",
        Book.class
    ).getResultStream()) {

    List<Book> all = books.toList();
}
```

Stream được đóng đúng. Nhưng memory vẫn có thể tăng rất mạnh vì:

- Provider có thể materialize List trước.
- `toList()` tạo một collection chứa mọi phần tử.
- Persistence context có thể giữ mọi managed Book.
- Các lazy associations được truy cập có thể gây N+1.
- Kết quả SQL có thể cực lớn.

Cần tách ba mục tiêu:

1. **An toàn tài nguyên:** đóng stream/transaction/context.
2. **Kiểm soát bộ nhớ:** projection, batching, pagination, không giữ mọi object.
3. **Tối ưu SQL:** lọc/sắp xếp tại DB, index, fetch plan, tránh N+1.

`try-with-resources` giải quyết mục tiêu thứ nhất. Nó không tự giải quyết hai mục tiêu còn lại.

## 28. Những lỗi thường gặp

### Lỗi 1: Không đóng stream

```java
query.getResultStream().forEach(this::processBook);
```

Thiếu ranh giới đóng tường minh. Nên dùng try-with-resources khi stream có thể gắn với JDBC resources.

### Lỗi 2: Đóng EntityManager trước khi tiêu thụ stream

```java
Stream<Book> stream = query.getResultStream();
em.close();
stream.forEach(this::processBook);
```

Provider có thể cần context/connection đang sống. Tiêu thụ trước khi đóng.

### Lỗi 3: Trả stream ra tầng controller

Transaction có thể kết thúc trước lúc JSON serializer duyệt. Trả DTO đã xử lý hoặc triển khai streaming endpoint với lifecycle chuyên biệt.

### Lỗi 4: Tin rằng Stream luôn tiết kiệm bộ nhớ hơn List

Triển khai mặc định có thể là `getResultList().stream()`. Cần kiểm tra provider cụ thể và chọn projection/paging.

### Lỗi 5: Dùng `stream.limit(10)` thay `setMaxResults(10)`

`limit` xử lý Java, không bảo đảm SQL giới hạn 10 hàng. Dùng query-level limit khi chỉ cần ít kết quả.

### Lỗi 6: Dùng `stream.filter(...)` để thay WHERE

Java filter có thể xử lý sau khi DB trả dữ liệu. Ưu tiên JPQL `WHERE` khi filter có thể diễn đạt được bằng query.

### Lỗi 7: Dùng `parallel()` với managed entities

Persistence context/EntityManager không thread-safe để chia sẻ tùy tiện. Đừng parallelize cursor/query không có thiết kế riêng.

### Lỗi 8: Quên transaction khi provider cần server-side cursor

Một số driver cần transaction/autocommit phù hợp. Không suy rằng mọi SELECT stream có thể duyệt ngoài transaction.

### Lỗi 9: Không đóng stream khi `findFirst()` trả về

Short-circuit operation có thể dừng trước khi đọc hết; còn JDBC resources có thể cần giải phóng.

### Lỗi 10: Dùng một stream hai lần

Java Stream chỉ tiêu thụ một lần. Nếu cần duyệt nhiều lần, tạo query mới hoặc materialize collection có giới hạn.

### Lỗi 11: Stream toàn entity rồi giữ chúng trong persistence context khổng lồ

JDBC streaming không tự detach entity. Dùng DTO/scalar hoặc batch/context boundaries.

### Lỗi 12: Gọi `em.clear()` tùy tiện giữa một result stream đang hoạt động

Có thể tác động đến managed state, lazy association và provider cursor. Không coi đó là pattern portable; ưu tiên phân trang và ranh giới batch rõ ràng.

### Lỗi 13: Nuốt exception khi đang duyệt stream rồi tiếp tục cùng transaction

Transaction có thể rollback-only. Dừng, đóng tài nguyên và xử lý transaction thất bại.

### Lỗi 14: Chỉ kiểm thử kết quả, không kiểm tra pool/cursor

Một test trả đúng 10 Book không chứng minh JDBC resource đã được đóng. Cần quan sát resource lifecycle dưới load/early termination.

### Lỗi 15: Kéo dài transaction do consumer chậm

Nếu gửi dữ liệu qua mạng chậm ngay trong stream callback, DB connection có thể bị giữ lâu. Cân nhắc job/export file/paging.

### Lỗi 16: Cho rằng `close()` của Stream commit transaction

`stream.close()` chỉ đóng stream theo contract Java/provider. Commit/rollback và EntityManager lifecycle phải được xử lý riêng.

## 29. Ma trận lựa chọn API cho JPQL

| Nhu cầu | Gợi ý |
| --- | --- |
| Lấy danh sách nhỏ | `getResultList()` |
| Lấy một entity theo ID | `find()` |
| Lấy một kết quả duy nhất, kỳ vọng đúng một | `getSingleResult()` và xử lý ngoại lệ |
| Có thể không có kết quả, chỉ muốn phần tử đầu | `setMaxResults(1)` rồi `getResultStream().findFirst()`, đóng stream |
| Duyệt một lượt số lượng vừa phải | `getResultStream()` với try-with-resources |
| Xử lý hàng trăm nghìn dòng | DTO projection, paging/batch hoặc cursor provider-specific có kiểm chứng |
| Chỉ cần COUNT/SUM/AVG | JPQL aggregate thay vì stream mọi entity |
| Xuất CSV lớn | Query projection + resource lifecycle rõ; cân nhắc batch/export job |
| Xử lý đa luồng | Chia partition, mỗi worker có context/transaction riêng |
| Cần kiểm soát JDBC cursor chi tiết | Cân nhắc API provider/JDBC có lifecycle tường minh |
| Cần trả HTTP JSON | DTO phân trang, không trả live JPA stream ra controller |

Quy tắc thực dụng: **API tối ưu nhất là API thể hiện rõ số dữ liệu cần đọc và thời điểm hoàn tất công việc**, không phải API có tên nghe giống “streaming”.

## 30. Bài tập thực hành

### Bài 1: Đọc hiểu getResultStream

```java
try (Stream<Book> books = em.createQuery(
        "SELECT b FROM Book b",
        Book.class
    ).getResultStream()) {

    books.forEach(this::processBook);
}
```

**Câu hỏi:** Try-with-resources đang bảo vệ tài nguyên nào?

**Đáp án:** Nó gọi `Stream.close()` khi thoát phạm vi. Nếu provider gắn cursor/ResultSet/statement cleanup vào stream, các tài nguyên đó được dọn đúng thời điểm. Transaction và EntityManager vẫn phải có lifecycle riêng.

### Bài 2: Limit ở Java

```java
query.getResultStream().limit(10).forEach(this::processBook);
```

**Câu hỏi:** Có chắc DB chỉ đọc 10 hàng không?

**Đáp án:** Không. Provider có thể materialize toàn bộ List trước. Cần `setMaxResults(10)` ở query nếu muốn giới hạn kết quả JPA.

### Bài 3: Trả stream qua service

```java
public Stream<Book> list() {
    try (EntityManager em = emf.createEntityManager()) {
        return em.createQuery(
            "SELECT b FROM Book b",
            Book.class
        ).getResultStream();
    }
}
```

**Câu hỏi:** Rủi ro?

**Đáp án:** Method trả stream sau khi EntityManager đã đóng. Khi caller tiêu thụ, query/cursor/lazy associations có thể không còn hợp lệ. Tiêu thụ trong phạm vi resource và trả DTO/list đã materialize hoặc dùng callback có lifecycle rõ.

### Bài 4: Filter ở Java

```java
try (Stream<Book> books = query.getResultStream()) {
    books.filter(b -> b.getCategory().equals("JAVA"))
         .forEach(this::processBook);
}
```

**Câu hỏi:** Nếu chỉ muốn Book category JAVA, nên đổi gì?

**Đáp án:** Đưa filter vào JPQL `WHERE b.category = :category` để DB lọc trước khi dữ liệu được chuyển sang Java.

### Bài 5: Short-circuit

```java
Optional<Book> first = stream.findFirst();
```

**Câu hỏi:** Có cần đóng stream không?

**Đáp án:** Có. `findFirst()` có thể không tiêu thụ hết cursor; dùng try-with-resources và query-level limit nếu chỉ cần một hàng.

### Bài 6: Query Stream và JPA persistence context

Một query stream đọc 500.000 `Book` managed và gọi `forEach`.

**Câu hỏi:** Có bảo đảm heap không tăng không?

**Đáp án:** Không. Persistence context có thể giữ các entity/snapshot. Cân nhắc scalar/DTO projection, phân trang, batch/context boundaries hoặc API provider-specific được kiểm chứng.

### Bài 7: Parallel stream

```java
books.parallel().forEach(b -> b.getPublisher().getName());
```

**Câu hỏi:** Vì sao nguy hiểm?

**Đáp án:** Có thể lazy-load qua cùng EntityManager/persistence context từ nhiều threads, trong khi JPA EntityManager không được xem là thread-safe. Nếu cần parallel, tách work units/context và transaction.

### Bài 8: Connection pool cạn

Một service mở stream, gọi `findFirst()` rồi bỏ reference mà không close. Sau nhiều request, connection pool hết connection.

**Câu hỏi:** Sửa ở đâu?

**Đáp án:** Đóng stream bằng try-with-resources, bảo đảm transaction/EntityManager kết thúc, kiểm tra pool metrics và driver/provider behavior. Không chỉ tăng kích thước pool để che lỗi.

### Bài 9: CSV export

Method nhận `Writer` do caller tạo và lấy Stream từ JPA.

**Câu hỏi:** Method nên đóng gì?

**Đáp án:** Đóng Stream và EntityManager do method sở hữu, kết thúc transaction; không tự đóng Writer của caller trừ khi contract chuyển ownership. Xử lý IOException để không giữ transaction/cursor.

### Bài 10: Bulk statistics

Ứng dụng muốn đếm số Book published, nhưng đang stream tất cả `Book` rồi gọi `count()`.

**Câu hỏi:** Cách nào phù hợp hơn?

**Đáp án:** Dùng JPQL `SELECT COUNT(b) FROM Book b WHERE b.published = true` để DB tính aggregate, giảm số hàng truyền và object được tạo.

### Bài 11: Bắt lỗi ở đâu?

Một provider đọc cursor tăng dần; SQL/mapping lỗi ở hàng thứ 500.

**Câu hỏi:** `getResultStream()` đã trả thành công thì có nghĩa không thể lỗi nữa không?

**Đáp án:** Không. Lỗi có thể xảy ra khi terminal operation đang duyệt. Bao bọc cả traversal, đóng stream và rollback/đóng context khi lỗi khiến transaction thất bại.

### Bài 12: N+1 khi stream entity

Consumer gọi `book.getPublisher().getName()` cho mỗi Book và tạo nhiều SELECT.

**Câu hỏi:** Stream có giải quyết N+1 không?

**Đáp án:** Không. Cần thiết kế fetch plan, JPQL JOIN FETCH cho to-one hoặc DTO projection phù hợp và đo SQL thực tế.

## 31. Checklist khi dùng getResultStream trong dự án

Trước khi đưa một query stream vào production, hãy tự hỏi:

1. **Có thật sự cần Stream không?** Một List đã phân trang có thể rõ ràng hơn?
2. **JPA version hỗ trợ `getResultStream()` chưa?** JPA 2.2/Jakarta Persistence?
3. **Provider thực hiện stream bằng List hay JDBC cursor?** Có chứng cứ từ tài liệu/integration test không?
4. **Ai sở hữu stream?** Có `try-with-resources` hoặc close rõ ràng không?
5. **Transaction có sống trong toàn bộ quá trình tiêu thụ không?**
6. **EntityManager có bị đóng trước khi duyệt không?**
7. **Stream có bị trả ra controller/caller ngoài transaction không?**
8. **Có early termination bằng `findFirst`/`limit`/`anyMatch` không?** Vẫn close chứ?
9. **Query có giới hạn dữ liệu ở SQL/JPA không?** Dùng `WHERE`, `ORDER BY` và `setMaxResults` khi cần.
10. **Query trả entity managed hay DTO/scalar?** Context có thể tăng bộ nhớ không?
11. **Có join fetch collection hoặc lazy N+1 không?**
12. **Có cần fetch size/cursor hints provider-specific không?** Đã kiểm chứng với driver/DB thực chưa?
13. **Có `parallel()` hoặc nhiều thread dùng chung context không?** Nếu có, cần thiết kế lại.
14. **Consumer có thể chậm hoặc bị block do network/file IO không?** Transaction giữ connection bao lâu?
15. **Exception có thể xảy ra giữa traversal không?** Có rollback và cleanup đầy đủ không?
16. **Có theo dõi pool active/idle, cursor và timeouts không?**
17. **Có test short-circuit, consumer error và query lớn không?**
18. **Có cần snapshot consistency giữa những batch không?** Nếu có, transaction isolation và paging strategy là gì?
19. **Có dùng stream một lần duy nhất không?** Nếu phải duyệt lại, có strategy khác không?
20. **Người gọi có nhận được DTO an toàn thay vì live JPA entity/cursor không?**

Một checklist như vậy giúp tránh ngộ nhận rằng chỉ cần thay `getResultList()` bằng `getResultStream()` là ứng dụng sẽ tự động tiết kiệm bộ nhớ và không rò rỉ connection.

## Kết luận

**`getResultStream()` giúp đọc kết quả JPQL qua Java Stream, nhưng không bảo đảm provider luôn đọc dữ liệu tăng dần từ JDBC.** Triển khai mặc định của API có thể dựa trên `getResultList().stream()`; các provider khác có thể dùng cursor hoặc cơ chế streaming riêng. Vì thế, hiệu năng và mức sử dụng bộ nhớ phải được đánh giá trên provider, JDBC driver và database thực tế.

Điều cần làm nhất quán là **tiêu thụ và đóng Stream trong cùng phạm vi transaction/persistence context còn sống**. Dùng `try-with-resources`, không trả stream còn mở ra ngoài service, không đóng EntityManager trước khi tiêu thụ và xử lý cả lỗi phát sinh trong lúc duyệt. Đóng Stream không thay thế commit/rollback hoặc đóng EntityManager; mỗi tài nguyên có ownership và lifecycle riêng.

Nếu mục tiêu là giảm tải, hãy bắt đầu từ **JPQL WHERE/ORDER BY, setMaxResults, projection DTO/scalar và pagination**. Đừng dùng Java `limit`, `filter` hoặc `parallel()` như một thay thế tự động cho tối ưu SQL hoặc quản lý context. Với tập cực lớn, cân nhắc batch hoặc JDBC/provider-specific cursor và kiểm thử riêng khả năng giữ connection, bộ nhớ và tính nhất quán.

Câu hỏi quan trọng nhất khi sử dụng API này là: **“Kết quả được tải lúc nào, stream giữ tài nguyên gì, ai đóng nó, và query/transaction có còn sống cho đến khi dữ liệu được tiêu thụ xong không?”**. Trả lời đúng bốn câu hỏi đó sẽ giúp sử dụng `getResultStream()` rõ ràng, an toàn và hiệu quả.
