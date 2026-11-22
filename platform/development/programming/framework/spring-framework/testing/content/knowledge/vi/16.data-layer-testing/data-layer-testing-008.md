# Đọc dữ liệu qua JDBC để tránh chỉ xác nhận bộ đệm ORM

Khi kiểm thử tầng dữ liệu dùng Spring Data JPA hoặc Hibernate, việc gọi lại repository sau khi lưu một entity chưa chắc đã chứng minh dữ liệu đã được ghi và đọc từ cơ sở dữ liệu. JPA quản lý một **persistence context** (ngữ cảnh persistence) và giữ các entity đang được quản lý trong bộ nhớ. Vì vậy, một lần đọc bằng repository có thể trả về chính đối tượng đang nằm trong bộ nhớ mà không cần đọc lại hàng dữ liệu.

Một cách kiểm chứng độc lập hơn là đồng bộ các thay đổi ORM xuống cơ sở dữ liệu bằng `flush()`, sau đó dùng JDBC, chẳng hạn `JdbcTemplate`, chạy câu SQL `SELECT` trực tiếp. JDBC không tra cứu entity trong persistence context của JPA. Kết quả truy vấn vì thế cho biết cơ sở dữ liệu đang trả về giá trị nào trong transaction hiện tại.

## 1. Vì sao đọc lại bằng repository có thể tạo cảm giác kiểm thử đã thành công?

JPA duy trì persistence context trong phạm vi một `EntityManager`. Đây là bộ nhớ cấp một (first-level cache), đồng thời là nơi JPA theo dõi trạng thái của entity. Trong một persistence context, một entity có định danh cụ thể thường được đại diện bởi một đối tượng đang được quản lý. Khi ứng dụng thay đổi đối tượng đó, JPA ghi nhận thay đổi và lên lịch phát sinh câu SQL phù hợp.

Ví dụ, một bài kiểm thử thực hiện:

```java
Book saved = bookRepository.save(new Book("978-0132350884", "Clean Code"));

Book found = bookRepository.findById(saved.getId()).orElseThrow();

assertThat(found.getTitle()).isEqualTo("Clean Code");
```

Assertion trên có thể thành công vì `found` chính là entity đã được quản lý trong persistence context. JPA đã biết đối tượng đó có tiêu đề `Clean Code`; lần đọc tiếp theo có thể không phát sinh một câu `SELECT` mới. Bài kiểm thử khi ấy mới xác nhận trạng thái của đối tượng trong bộ nhớ, chưa trực tiếp xác nhận giá trị đang nằm trong bảng.

Ngay cả khi một truy vấn JPQL hoặc repository method có phát sinh SQL, kết quả entity vẫn được đối chiếu với persistence context. Nếu entity cùng định danh đã được quản lý, JPA thường trả về đối tượng đang quản lý đó thay vì tạo một bản sao độc lập. Vì vậy, kiểm tra thuộc tính của entity sau khi đọc lại bằng ORM không phải lúc nào cũng là bằng chứng độc lập về dữ liệu đã lưu.

Vấn đề này đặc biệt đáng chú ý khi kiểm thử:

- Một thao tác `INSERT`, `UPDATE` hoặc `DELETE` có thực sự được gửi xuống cơ sở dữ liệu hay không.
- Giá trị cột sau khi ghi có đúng như mong đợi hay không.
- Cột được cơ sở dữ liệu tự sinh, giá trị mặc định hoặc trigger có hoạt động đúng hay không.
- Cơ sở dữ liệu có áp dụng ràng buộc duy nhất, khóa ngoại, `NOT NULL` và các quy tắc dữ liệu khác hay không.

## 2. JDBC cung cấp một đường đọc độc lập với persistence context

`JdbcTemplate` thực thi SQL thông qua `DataSource`. Khi gọi `queryForObject`, `query`, hoặc `update`, nó làm việc với kết quả SQL do cơ sở dữ liệu trả về. Nó không yêu cầu JPA tìm entity trong persistence context và không lấy giá trị từ bộ nhớ cấp một của Hibernate.

Luồng kiểm thử có thể tổ chức như sau:

```text
Test
  |
  | 1. Gọi repository để lưu entity
  v
JPA / Hibernate
  |
  | 2. Theo dõi entity trong persistence context
  | 3. EntityManager.flush()
  v
DataSource / JDBC connection
  |
  | 4. Gửi INSERT / UPDATE / DELETE xuống database
  v
Database
  ^
  | 5. JdbcTemplate thực thi SELECT trực tiếp
  |
Test nhận giá trị cột hoặc số lượng hàng
```

Điểm quan trọng là hai đường truy cập có trách nhiệm khác nhau:

| Thành phần | Vai trò trong bài kiểm thử |
| --- | --- |
| Repository / JPA | Thực hiện thao tác ghi theo mô hình entity và quy tắc ORM. |
| `EntityManager.flush()` | Buộc các thay đổi đang chờ trong persistence context được đồng bộ thành SQL. |
| `JdbcTemplate` | Đọc trực tiếp hàng và cột bằng SQL, không đi qua persistence context. |
| Assertion | So sánh kết quả SQL với dữ liệu mong đợi. |

JDBC vẫn sử dụng cấu hình kết nối của Spring. Nếu `JdbcTemplate` và JPA dùng cùng `DataSource` trong một transaction do Spring quản lý, chúng thường tham gia cùng transaction và dùng connection được đồng bộ cho transaction đó. Đây là hành vi mong muốn trong bài kiểm thử thông thường: lệnh ghi từ ORM và lệnh đọc JDBC cùng nhìn thấy trạng thái dữ liệu trong transaction hiện tại.

## 3. Chuẩn bị ví dụ entity và repository

Giả sử ứng dụng lưu thông tin sách trong bảng `books`. Ta khai báo rõ tên bảng và tên cột để câu SQL trong bài kiểm thử khớp với schema.

```java
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

    @Column(name = "isbn", nullable = false, unique = true, length = 20)
    private String isbn;

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    protected Book() {
    }

    public Book(String isbn, String title) {
        this.isbn = isbn;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getIsbn() {
        return isbn;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
```

Repository chỉ cần kế thừa `JpaRepository`:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {
}
```

Ví dụ sử dụng Spring Boot với JPA. `@DataJpaTest` tạo test slice cho tầng JPA, cấu hình các thành phần cần thiết như repository, `EntityManager` và `DataSource`, đồng thời mặc định chạy mỗi test trong một transaction được rollback sau khi test kết thúc.

## 4. Kiểm chứng hàng dữ liệu bằng `JdbcTemplate`

Ta tiêm cả repository, `JdbcTemplate` và `EntityManager` vào bài kiểm thử. Repository thực hiện thao tác ghi; `EntityManager.flush()` đồng bộ thay đổi; sau đó JDBC đọc trực tiếp các cột trong bảng.

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class BookJdbcPersistenceTest {

    @Autowired
    private BookRepository bookRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void shouldWriteBookRowThatJdbcCanRead() {
        Book saved = bookRepository.save(
                new Book("978-0132350884", "Clean Code")
        );

        entityManager.flush();

        Long rowCount = jdbcTemplate.queryForObject(
                "select count(*) from books where isbn = ?",
                Long.class,
                saved.getIsbn()
        );

        String storedTitle = jdbcTemplate.queryForObject(
                "select title from books where isbn = ?",
                String.class,
                saved.getIsbn()
        );

        assertThat(rowCount).isEqualTo(1L);
        assertThat(storedTitle).isEqualTo("Clean Code");
    }
}
```

### Đọc từng bước của bài kiểm thử

**Bước 1 — Ghi qua repository.**

```java
Book saved = bookRepository.save(
        new Book("978-0132350884", "Clean Code")
);
```

Repository yêu cầu JPA lưu entity. Entity có thể đang được quản lý trong persistence context. Tùy chiến lược sinh khóa và thời điểm thực thi, một số câu SQL có thể đã được gửi đi; không nên dựa vào chi tiết đó để bỏ qua bước đồng bộ tường minh.

**Bước 2 — Đồng bộ thay đổi bằng `flush()`.**

```java
entityManager.flush();
```

`flush()` yêu cầu JPA đồng bộ các thay đổi đang chờ với cơ sở dữ liệu. Các câu `INSERT`, `UPDATE` hoặc `DELETE` cần thiết được phát sinh và thực thi. Nếu dữ liệu vi phạm ràng buộc, lỗi thường xuất hiện ở thời điểm flush hoặc khi transaction được commit, thay vì nhất thiết xuất hiện ngay tại lời gọi `save()`.

`flush()` không có nghĩa là commit. Dữ liệu vẫn nằm trong transaction hiện tại và có thể bị rollback.

**Bước 3 — Đọc số lượng hàng bằng JDBC.**

```java
Long rowCount = jdbcTemplate.queryForObject(
        "select count(*) from books where isbn = ?",
        Long.class,
        saved.getIsbn()
);
```

SQL được gửi trực tiếp đến database. Tham số `?` được bind bằng API của JDBC, vì thế không cần ghép giá trị đầu vào vào chuỗi SQL. Truy vấn `COUNT(*)` xác nhận có đúng một hàng mang ISBN đã lưu.

**Bước 4 — Đọc giá trị cột thực tế.**

```java
String storedTitle = jdbcTemplate.queryForObject(
        "select title from books where isbn = ?",
        String.class,
        saved.getIsbn()
);
```

Kết quả là giá trị cột `title` mà database trả về. Assertion này có ý nghĩa khác với `saved.getTitle()`: nó kiểm tra kết quả của một câu `SELECT` thực thi qua JDBC.

**Bước 5 — So sánh với kết quả mong đợi.**

Hai assertion kiểm tra cả sự tồn tại của hàng lẫn nội dung cột. Nếu chỉ kiểm tra số lượng hàng, một hàng được ghi với tiêu đề sai vẫn có thể làm test thành công. Nếu chỉ kiểm tra tiêu đề, cần chắc chắn truy vấn đang nhắm đến đúng khóa và không có dữ liệu trùng lặp gây nhầm lẫn. Kết hợp các điều kiện phù hợp giúp assertion có ý nghĩa rõ ràng.

## 5. Phân biệt `flush()`, `clear()` và `commit()`

Ba thao tác này thường xuất hiện trong kiểm thử JPA nhưng có mục đích khác nhau.

| Thao tác | Tác dụng | Có commit transaction không? |
| --- | --- | --- |
| `entityManager.flush()` | Gửi các thay đổi đang chờ trong persistence context xuống database. | Không. |
| `entityManager.clear()` | Xóa các entity đang được quản lý khỏi persistence context hiện tại. | Không. |
| Commit transaction | Hoàn tất transaction; thay đổi trở thành dữ liệu đã commit theo cơ chế của database. | Có. |

### `flush()` là điều kiện quan trọng trước khi đọc bằng JDBC

ORM có thể trì hoãn việc phát sinh SQL cho đến khi flush tự động hoặc flush tường minh. Nếu chạy câu `SELECT` bằng JDBC trước khi thay đổi được flush, truy vấn có thể chưa nhìn thấy hàng mới hoặc vẫn nhìn thấy giá trị cũ. Vì vậy, bài kiểm thử cần gọi `flush()` trước câu SQL đọc để kiểm soát thứ tự thực thi.

### `clear()` hữu ích khi muốn đọc lại bằng JPA

`clear()` không cần thiết để `JdbcTemplate` bỏ qua persistence context; JDBC vốn đã không sử dụng persistence context. Tuy nhiên, nếu bài kiểm thử muốn kiểm tra thêm rằng một lần đọc JPA tiếp theo không chỉ trả lại entity đang được quản lý, có thể flush rồi clear trước khi gọi repository:

```java
entityManager.flush();
entityManager.clear();

Book reloaded = bookRepository.findById(saved.getId()).orElseThrow();
assertThat(reloaded.getTitle()).isEqualTo("Clean Code");
```

Sau `clear()`, entity cũ không còn được quản lý trong persistence context. Lần đọc JPA cần nạp lại entity. Dù vậy, nếu mục tiêu là có một phép đọc độc lập với ORM, truy vấn `JdbcTemplate` vẫn thể hiện rõ ranh giới kiểm chứng hơn.

### `flush()` không chứng minh dữ liệu đã commit

Trong `@DataJpaTest`, transaction kiểm thử thường được rollback khi phương thức test kết thúc. JDBC có thể đọc được hàng vừa ghi vì truy vấn tham gia cùng transaction và nhìn thấy các thay đổi của transaction đó. Điều này chứng minh SQL đã được thực thi và trạng thái trong transaction là đúng; nó chưa chứng minh một transaction khác có thể nhìn thấy dữ liệu sau commit.

## 6. Khi nào cần kiểm tra khả năng đọc sau commit?

Có hai mức kiểm chứng cần phân biệt:

| Mức kiểm chứng | Cách làm | Kết luận có thể rút ra |
| --- | --- | --- |
| Đọc trong cùng transaction | Ghi qua JPA, gọi `flush()`, đọc bằng `JdbcTemplate` trong test transaction. | SQL đã đồng bộ xuống database và JDBC đọc được trạng thái trong transaction hiện tại. |
| Đọc sau commit | Cho transaction ghi kết thúc thành công, sau đó đọc bằng một transaction khác hoặc ngoài transaction ghi. | Dữ liệu đã commit có thể được nhìn thấy từ transaction đọc tiếp theo. |

Nếu cần kiểm tra mức thứ hai, có thể tổ chức test để phương thức kiểm thử không tự bao toàn bộ thao tác trong một transaction, gọi một service có `@Transactional` để ghi dữ liệu, rồi truy vấn JDBC sau khi lời gọi service trả về. Khi service transaction commit thành công, câu truy vấn tiếp theo chạy ngoài transaction ghi sẽ kiểm tra khả năng nhìn thấy dữ liệu đã commit.

Với test slice `@DataJpaTest`, một lựa chọn khác là chủ động kết thúc test transaction sau khi đánh dấu commit bằng `TestTransaction`:

```java
import org.springframework.test.context.transaction.TestTransaction;

// Sau khi lưu dữ liệu và gọi entityManager.flush():
TestTransaction.flagForCommit();
TestTransaction.end();

// Transaction kiểm thử đã kết thúc; truy vấn JDBC tiếp theo chạy ngoài transaction đó.
Long rowCount = jdbcTemplate.queryForObject(
        "select count(*) from books where isbn = ?",
        Long.class,
        "978-0132350884"
);

assertThat(rowCount).isEqualTo(1L);
```

Đây là ví dụ về ranh giới commit, không phải thao tác mặc định cho mọi bài kiểm thử. Khi chủ động commit trong test, dữ liệu sẽ không còn được rollback tự động bởi transaction test đã kết thúc. Bài kiểm thử cần có chiến lược dọn dữ liệu rõ ràng, chẳng hạn xóa bản ghi theo khóa thử nghiệm hoặc dùng database riêng được tạo lại giữa các test. Nếu không cần xác nhận khả năng nhìn thấy sau commit, nên giữ transaction rollback mặc định của `@DataJpaTest` để test độc lập và dễ lặp lại.

## 7. Dùng JDBC để kiểm tra các giá trị do database tạo ra

Một lợi ích khác của JDBC là kiểm tra được giá trị do database quyết định. Ví dụ, một cột có `DEFAULT CURRENT_TIMESTAMP`, một trigger cập nhật cột kiểm toán, hoặc một biểu thức SQL tạo giá trị chuẩn hóa. Entity trong bộ nhớ có thể chưa phản ánh các thay đổi đó.

Giả sử bảng `books` có cột `created_at` được database gán giá trị mặc định khi insert. Sau khi ghi và flush, bài kiểm thử có thể đọc cột này:

```java
Timestamp createdAt = jdbcTemplate.queryForObject(
        "select created_at from books where isbn = ?",
        Timestamp.class,
        saved.getIsbn()
);

assertThat(createdAt).isNotNull();
```

Tương tự, với trigger thay đổi một cột sau khi insert hoặc update, JDBC có thể đọc giá trị cuối cùng do database lưu. Nếu sau đó cần đồng bộ lại entity trong persistence context, có thể dùng `entityManager.refresh(entity)` hoặc clear rồi đọc lại. Cần nhớ rằng `refresh()` là thao tác của ORM; phép đọc JDBC vẫn là bằng chứng trực tiếp hơn về giá trị cột.

JDBC cũng hữu ích khi kiểm tra các ràng buộc dữ liệu. Ví dụ, nếu `isbn` có ràng buộc `UNIQUE`, có thể thử lưu hai bản ghi trùng ISBN, gọi `flush()` và xác nhận thao tác bị từ chối. Lỗi có thể được chuyển thành `DataIntegrityViolationException` ở tầng Spring tùy vị trí và cách xử lý exception. Việc kiểm tra phải đặt tại thời điểm thực thi SQL phù hợp; chỉ gọi `save()` rồi kết thúc test có thể chưa kích hoạt ràng buộc ngay lập tức.

## 8. Lưu ý về transaction và cấu hình database trong test

### JDBC và JPA cần dùng cùng `DataSource` nếu muốn đọc trong cùng transaction

Trong cấu hình Spring thông thường, `JpaTransactionManager` có thể đồng bộ JDBC connection với `DataSource` của JPA. `JdbcTemplate` sử dụng cơ chế quản lý connection của Spring, nên câu SQL có thể tham gia transaction hiện hành.

Nếu ứng dụng cấu hình nhiều `DataSource`, nhiều transaction manager hoặc một `JdbcTemplate` trỏ sang database khác, truy vấn JDBC có thể không nhìn thấy thay đổi chưa commit của JPA. Khi đó cần kiểm tra lại wiring: `EntityManagerFactory`, transaction manager và `JdbcTemplate` phải trỏ đến đúng nguồn dữ liệu theo mục tiêu test.

### Database dùng trong test có thể khác database production

`@DataJpaTest` thường thay thế cấu hình datasource bằng embedded database nếu project có dependency tương ứng. Điều này thuận tiện cho test nhanh, nhưng kết quả chỉ phản ánh hành vi của database đang dùng trong test. Cú pháp SQL, kiểu dữ liệu, collation, khóa, isolation level, trigger và một số ràng buộc có thể khác giữa H2, PostgreSQL, MySQL hoặc các hệ quản trị khác.

Nếu bài kiểm thử phụ thuộc vào đặc tính riêng của production database, cần chạy test với đúng hệ quản trị đó, thường thông qua Testcontainers hoặc datasource kiểm thử đã được cấu hình. Với Spring Boot, `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` có thể ngăn `@DataJpaTest` tự thay datasource; cấu hình kết nối thật cho test vẫn phải được cung cấp riêng và an toàn.

### Rollback tự động có giới hạn rõ ràng

Transaction rollback sau test giúp dọn dữ liệu và tránh test này ảnh hưởng test khác. JDBC đọc trong transaction đó vẫn có thể thấy dữ liệu vừa ghi. Vì thế, không nên diễn giải kết quả JDBC trong một test transaction là bằng chứng cho việc commit đã thành công hoặc dữ liệu đã được một phiên làm việc độc lập nhìn thấy.

## 9. Những lỗi thiết kế thường gặp

**Đọc bằng repository rồi kết luận database đã được kiểm tra.**

Repository là đường truy cập ORM. Entity có thể được trả lại từ persistence context. Nếu mục tiêu là xác nhận hàng và cột trong database, hãy dùng JDBC sau khi flush.

**Bỏ qua `flush()` trước truy vấn JDBC.**

Thay đổi có thể vẫn đang chờ trong persistence context. Truy vấn SQL chạy trước khi flush có thể đọc trạng thái cũ. Hãy kiểm soát thứ tự bằng `entityManager.flush()`.

**Cho rằng `flush()` đồng nghĩa với commit.**

Flush chỉ đồng bộ SQL trong transaction hiện tại. Constraint có thể được kiểm tra ở flush, nhưng transaction vẫn có thể rollback. Nếu yêu cầu là xác nhận dữ liệu đã commit, hãy kiểm tra sau khi transaction ghi kết thúc.

**Chỉ kiểm tra `saved.getTitle()`.**

Đó là giá trị trên đối tượng Java. Nó không chứng minh database đã lưu cùng giá trị. Hãy truy vấn cột `title` bằng JDBC.

**Chỉ kiểm tra `COUNT(*)` mà không kiểm tra dữ liệu quan trọng.**

Sự tồn tại của hàng không đảm bảo mọi cột đều chính xác. Nên đọc những cột liên quan trực tiếp đến hành vi cần kiểm chứng.

**Dùng SQL không khớp schema thực tế.**

Tên bảng và tên cột trong SQL phải khớp với mapping và schema. Khai báo `@Table` và `@Column` tường minh có thể giúp ví dụ và test dễ đọc hơn. Trong dự án có naming strategy, migration hoặc schema riêng, hãy kiểm tra schema thực tế của test database.

**Dùng embedded database để kết luận về hành vi riêng của production database.**

JDBC loại bỏ persistence context khỏi đường đọc, nhưng không làm cho H2 trở thành PostgreSQL hoặc MySQL. Chọn đúng database kiểm thử khi hành vi phụ thuộc dialect hoặc tính năng riêng.

## 10. Quy trình áp dụng trong bài kiểm thử tầng dữ liệu

Khi cần xác nhận một thao tác ghi qua ORM đã tạo ra trạng thái dữ liệu đúng, có thể áp dụng trình tự sau:

1. Tạo dữ liệu đầu vào với khóa nhận diện rõ ràng để tránh đọc nhầm bản ghi.
2. Gọi repository hoặc service để thực hiện thao tác cần kiểm thử.
3. Gọi `entityManager.flush()` để buộc ORM gửi các thay đổi đang chờ xuống database.
4. Dùng `JdbcTemplate` chạy `SELECT` với tham số bind, nhắm đúng hàng và các cột cần kiểm tra.
5. Assertion trên kết quả JDBC, chẳng hạn số lượng hàng, giá trị cột, giá trị mặc định hoặc kết quả do trigger tạo ra.
6. Xác định rõ test đang kiểm tra trạng thái trong cùng transaction hay dữ liệu đã commit. Chỉ thay đổi chiến lược transaction và cleanup khi yêu cầu thực sự cần mức kiểm chứng sau commit.

Không phải mọi test repository đều cần thêm JDBC. Nếu mục tiêu chỉ là kiểm tra quy tắc tìm kiếm hoặc mapping ở mức ORM, test repository thông thường có thể phù hợp. JDBC đặc biệt có giá trị khi câu hỏi kiểm thử là: **database thực sự đang trả về hàng và giá trị cột nào sau thao tác ghi?**

## Kết luận

Đọc dữ liệu bằng JDBC tạo ra một phép kiểm tra tách khỏi persistence context của JPA. Khi kết hợp `EntityManager.flush()` với `JdbcTemplate`, bài kiểm thử xác nhận được trạng thái mà database trả về trong transaction hiện tại, thay vì chỉ xác nhận entity còn nằm trong bộ nhớ ORM.

Luôn phân biệt flush với commit: test `@DataJpaTest` thông thường đọc JDBC trong cùng transaction và rollback sau đó. Nếu cần xác nhận dữ liệu đã commit và được transaction khác nhìn thấy, phải thiết kế ranh giới transaction tương ứng. Đồng thời, hãy chạy trên đúng loại database khi hành vi cần kiểm chứng phụ thuộc vào hệ quản trị cụ thể.
