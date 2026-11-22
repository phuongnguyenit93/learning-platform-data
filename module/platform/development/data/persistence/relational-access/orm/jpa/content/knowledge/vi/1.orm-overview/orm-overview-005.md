# Phân biệt JPA, Hibernate, JDBC và Spring Data JPA

Trong ứng dụng Java, cùng một thao tác như lưu một cuốn sách vào cơ sở dữ liệu quan hệ có thể được viết bằng JDBC, JPA, Hibernate hoặc Spring Data JPA. Bốn tên gọi này thường xuất hiện cùng nhau, nhưng **không nằm ở cùng một tầng trừu tượng**: JDBC là API làm việc với cơ sở dữ liệu bằng câu lệnh SQL; JPA (nay là Jakarta Persistence) là đặc tả chuẩn cho quản lý dữ liệu hướng đối tượng; Hibernate ORM là một triển khai ORM phổ biến, đồng thời là JPA provider; còn Spring Data JPA hỗ trợ xây dựng tầng repository trên JPA trong hệ sinh thái Spring.

Điều quan trọng là hiểu **ai định nghĩa hợp đồng, ai thực thi, ai rút gọn mã ứng dụng**, và lúc nào nhà phát triển phải chủ động viết SQL.

## 1. Trước hết: ORM giải quyết vấn đề gì?

Ứng dụng Java tổ chức dữ liệu dưới dạng đối tượng, trong khi cơ sở dữ liệu quan hệ lưu thông tin vào bảng, hàng, cột và liên kết bằng khóa ngoại. Sự khác nhau giữa hai mô hình này thường được gọi là *object–relational impedance mismatch*.

Giả sử hệ thống quản lý sách có bảng:

~~~sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(255) NOT NULL
);
~~~

Trong Java, sách lại được biểu diễn bởi một lớp:

~~~java
public class Book {
    private Long id;
    private String title;

    // Constructor, getter, setter...
}
~~~

Khi không sử dụng ORM, lập trình viên phải viết mã chuyển từng cột từ `ResultSet` thành thuộc tính Java, và chuyển ngược thuộc tính thành tham số SQL khi ghi dữ liệu. ORM cho phép khai báo ánh xạ `Book ↔ books`, `id ↔ id`, `title ↔ title`, từ đó hỗ trợ truy vấn, ghi nhận thay đổi và quản lý vòng đời đối tượng.

Tuy nhiên, ORM **không xóa bỏ** kiến thức về SQL, khóa chính, khóa ngoại, chỉ mục, transaction hay cách cơ sở dữ liệu thực thi truy vấn. Nó chỉ cung cấp một tầng trừu tượng để xử lý nhiều công việc lặp lại.

## 2. Nhìn từ trên xuống: bốn công nghệ nằm ở đâu?

Một cấu hình Spring Boot thông dụng có luồng gọi như sau:

~~~text
                  Mã nghiệp vụ Java
                         |
               Spring Data JPA          (tùy chọn)
           Repository / JpaRepository
                         |
                Jakarta Persistence
              JPA API / EntityManager  (hợp đồng chuẩn)
                         |
                   Hibernate ORM
              JPA provider / ORM engine
                         |
                        JDBC
             Driver / Connection / SQL
                         |
               Cơ sở dữ liệu quan hệ
~~~

Có thể viết ứng dụng đi thẳng từ mã nghiệp vụ xuống `EntityManager` mà không dùng Spring Data JPA; gọi API `Session` riêng của Hibernate mà không đi qua API JPA; hoặc dùng JDBC trực tiếp, không cần ORM. Trong cấu hình ORM quan hệ phổ biến, Hibernate vẫn dùng JDBC và driver phù hợp ở tầng dưới để trao đổi với cơ sở dữ liệu.

Bảng sau phân biệt các vai trò:

| Công nghệ | Bản chất | API thường gặp | Công việc chính | Có tự triển khai ORM không? |
|---|---|---|---|---|
| **JDBC** | API chuẩn của Java để truy cập dữ liệu quan hệ | `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` | Gửi SQL, lấy kết quả, điều khiển transaction ở mức kết nối | Không |
| **JPA / Jakarta Persistence** | Đặc tả và API chuẩn về persistence/ORM | `@Entity`, `EntityManager`, JPQL, Criteria API | Quy định cách ánh xạ entity, truy vấn và quản lý vòng đời entity | Không; cần provider thực thi |
| **Hibernate ORM** | Framework ORM; một JPA provider | `Session`, `SessionFactory`; đồng thời hỗ trợ `EntityManager` | Ánh xạ và quản lý entity, tạo/thực thi SQL, dirty checking, cache... | Có |
| **Spring Data JPA** | Thư viện thuộc Spring Data, xây dựng trên JPA | `Repository`, `JpaRepository`, `@Query` | Giảm mã repository, sinh truy vấn từ tên phương thức, hỗ trợ paging/sorting | Không; cần JPA provider |

**JPA không đồng nghĩa với Hibernate.** JPA là hợp đồng chuẩn; Hibernate là một triển khai của hợp đồng đó. Những provider khác, chẳng hạn EclipseLink, cũng có thể triển khai JPA. **Spring Data JPA cũng không thay thế Hibernate**: nó thường sử dụng Hibernate ở dưới khi ứng dụng Spring Boot dùng cấu hình mặc định, nhưng có thể làm việc với provider JPA khác.

> Về tên gọi: JPA vốn là viết tắt của *Java Persistence API*. Sau khi chuyển sang Jakarta EE, đặc tả chính thức mang tên **Jakarta Persistence**, nhưng cách gọi “JPA” vẫn rất phổ biến. Dự án hiện đại dùng package `jakarta.persistence.*`; mã và tài liệu cũ có thể dùng `javax.persistence.*`. Hai nhóm package thuộc những thế hệ API khác nhau, không thể tùy ý trộn chúng trong cùng một cấu hình.

## 3. JDBC: chủ động viết SQL và ánh xạ dữ liệu

JDBC là lựa chọn gần với cơ sở dữ liệu nhất trong bốn công nghệ. Ứng dụng chuẩn bị SQL, gắn tham số, thực thi, đọc kết quả và tự chuyển thành đối tượng phù hợp.

Ví dụ đọc một sách theo `id`, giả sử `dataSource` đã được cấu hình và lớp `BookRow` là DTO:

~~~java
public record BookRow(long id, String title) {}

public BookRow findBook(long id) throws SQLException {
    String sql = "SELECT id, title FROM books WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, id);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                return null;
            }
            return new BookRow(
                result.getLong("id"),
                result.getString("title")
            );
        }
    }
}
~~~

Ở đây:

1. `DataSource` cung cấp một `Connection`; ứng dụng thực tế thường sử dụng connection pool.
2. `PreparedStatement` truyền tham số bằng cơ chế binding, giúp tránh nối chuỗi giá trị người dùng trực tiếp vào SQL.
3. `ResultSet` chứa các hàng kết quả; lập trình viên tự quyết định cách chuyển chúng sang đối tượng.
4. `try-with-resources` đóng tài nguyên đúng cách; nếu `Connection` đến từ pool thì việc `close()` thường trả kết nối về pool.

Nếu một thao tác cần nhiều câu SQL phải thành công hoặc thất bại cùng nhau, JDBC có thể điều khiển transaction ở mức kết nối:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        // Thực thi nhiều INSERT / UPDATE bằng cùng connection.
        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

JDBC **không mặc nhiên** tạo quan hệ giữa các đối tượng, không theo dõi thuộc tính nào đã đổi và không sinh các câu `INSERT`/`UPDATE` dựa trên entity. Đổi lại, lập trình viên kiểm soát trực tiếp câu SQL, rất phù hợp với những truy vấn đặc thù hoặc xử lý dữ liệu hàng loạt.

## 4. JPA: đặc tả chuẩn cho entity và persistence context

JPA định nghĩa *cách một ứng dụng Java nói chuyện với tầng persistence theo mô hình entity*. Các thành phần trung tâm bao gồm:

- **Entity**: đối tượng được ánh xạ vào dữ liệu lưu trữ, thường khai báo bằng `@Entity`, `@Id`, `@Column` và các annotation quan hệ.
- **EntityManager**: API chuẩn để `persist`, `find`, `remove`, `merge` và tạo truy vấn.
- **Persistence context**: tập hợp các entity đang được quản lý trong một phạm vi nhất định. Với mỗi định danh entity, context quản lý một thể hiện đối tượng nhất quán.
- **JPQL và Criteria API**: cách mô tả truy vấn dựa trên entity và thuộc tính Java, thay vì phụ thuộc hoàn toàn vào tên bảng/cột.
- **Transaction và flush**: xác định ranh giới thay đổi và thời điểm đồng bộ trạng thái trong context xuống cơ sở dữ liệu.

### 4.1. Ánh xạ một entity

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Column;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 255)
    private String title;

    protected Book() {} // Constructor không tham số cho JPA

    public Book(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

Đoạn entity này minh họa cách khai báo; cần bảng `books` có cơ chế sinh khóa chính tương thích với `GenerationType.IDENTITY` trong cơ sở dữ liệu đang dùng. Schema ban đầu ở mục 1 chỉ để mô tả cấu trúc, chưa thể hiện cú pháp tự sinh khóa riêng của một hệ quản trị.

### 4.2. Làm việc qua EntityManager

Ví dụ dưới đây dùng `EntityManager` theo chế độ *resource-local transaction* để làm rõ vai trò JPA. Trong ứng dụng Spring, transaction thường do `@Transactional` quản lý, không gọi `getTransaction()` trực tiếp như ở đây.

~~~java
EntityManager em = entityManagerFactory.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Book book = em.find(Book.class, 10L);
    if (book == null) {
        throw new IllegalArgumentException("Không tìm thấy sách");
    }

    book.setTitle("Java Persistence");
    // Chưa cần gọi phương thức update(...).

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

Khi `em.find(...)` trả về một entity đang được quản lý (*managed entity*), provider sẽ kiểm tra thay đổi của nó (*dirty checking*) và đồng bộ thành câu SQL phù hợp trong quá trình flush. Việc flush thường xảy ra trước hoặc khi commit, nhưng thời điểm thực hiện SQL còn phụ thuộc chiến lược flush, loại thao tác và provider. **Flush cũng không có nghĩa là commit**: SQL đã được gửi đi vẫn có thể bị rollback nếu transaction chưa commit.

Không phải entity nào cũng ở trạng thái managed. Một đối tượng vừa tạo bằng `new` là *new/transient*; sau `persist`, nó trở thành managed. Entity bị tách khỏi persistence context là *detached*; cần hiểu ngữ nghĩa của `merge` nếu muốn đồng bộ trạng thái từ một đối tượng detached. Một entity đã đánh dấu xóa nằm ở trạng thái *removed* trong context.

### 4.3. JPQL khác SQL như thế nào?

~~~java
List<Book> books = em.createQuery(
        "SELECT b FROM Book b WHERE b.title LIKE :pattern",
        Book.class)
    .setParameter("pattern", "%Java%")
    .getResultList();
~~~

Trong JPQL, `Book` là **tên entity** và `b.title` là **thuộc tính Java**, thay vì tên bảng/cột như trong SQL. Provider dịch truy vấn phù hợp thành SQL. JPA cũng cho phép thực thi native SQL khi cần, nhưng câu truy vấn native phụ thuộc vào schema và có thể phụ thuộc cú pháp của cơ sở dữ liệu.

JPA chuẩn hóa API, song **một API chuẩn không tự vận hành**. Ứng dụng cần Hibernate, EclipseLink hoặc provider tương đương để thực sự ánh xạ entity và làm việc với database.

## 5. Hibernate: bộ máy ORM triển khai JPA

Hibernate ORM là framework thực hiện phần công việc nặng của ORM: đọc metadata ánh xạ, quản lý trạng thái entity, sinh SQL, thực hiện load/persist/update/delete, hỗ trợ lazy loading, cache và nhiều tối ưu hóa.

Khi dùng Hibernate như JPA provider, mã nghiệp vụ có thể chỉ import `jakarta.persistence.*`. Hibernate đứng sau `EntityManager` và cung cấp hành vi thực thi. Khi cần khả năng riêng của Hibernate, ứng dụng còn có thể dùng API native như `Session` và `SessionFactory`:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        Book book = session.get(Book.class, 10L);
        if (book == null) {
            throw new IllegalArgumentException("Không tìm thấy sách");
        }

        book.setTitle("Hibernate ORM");
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

`Session` là API native của Hibernate; `EntityManager` là API chuẩn của JPA. Khi Hibernate làm provider, hai API có những khả năng tương ứng và có thể truy cập API Hibernate từ `EntityManager` bằng cơ chế `unwrap(...)` khi thực sự cần. Tuy nhiên, **viết code phụ thuộc vào Hibernate API làm giảm tính độc lập với provider**.

Hibernate không có nghĩa là “không bao giờ viết SQL”. Ứng dụng vẫn có thể dùng HQL, JPQL, native SQL và các công cụ truy vấn khác. Hibernate cũng không đảm bảo truy vấn nào được sinh ra cũng tối ưu: lập trình viên phải quan sát SQL thực tế, đánh giá số lượt truy vấn, chỉ mục và execution plan khi cần.

## 6. Spring Data JPA: giảm mã repository trong ứng dụng Spring

Khi chỉ dùng JPA, nhiều lớp DAO/repository thường lặp lại các thao tác như tìm theo khóa chính, lưu, xóa, phân trang và dựng truy vấn đơn giản. **Spring Data JPA** cung cấp mô hình khai báo interface repository và tạo phần triển khai cần thiết lúc runtime.

~~~java
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {
    List<Book> findByTitleContainingIgnoreCase(String keyword);
}
~~~

Không cần tự viết lớp triển khai cho `findById`, `findAll`, `save`, `deleteById` hay phương thức truy vấn dẫn xuất `findByTitleContainingIgnoreCase` ở trên. Spring Data JPA phân tích tên phương thức và phối hợp với JPA provider để thực hiện truy vấn.

Ví dụ service sử dụng repository:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    private final BookRepository books;

    public BookService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public void rename(Long id, String newTitle) {
        Book book = books.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy sách"));

        book.setTitle(newTitle);
        // Entity managed sẽ được đồng bộ khi transaction flush/commit.
    }
}
~~~

Điểm khác biệt cần chú ý:

- `@Transactional` ở đây do **Spring Transaction Management** cung cấp; nó quản lý ranh giới transaction cho service. Annotation này không phải tính năng riêng của Spring Data JPA.
- `JpaRepository.save(entity)` không có nghĩa chắc chắn sẽ thực thi `INSERT` ngay lập tức. Spring Data JPA xác định entity mới hay đã tồn tại để sử dụng thao tác JPA phù hợp; SQL có thể được trì hoãn đến flush, với những ngoại lệ tùy chiến lược sinh khóa và provider.
- Khi truy vấn trở nên phức tạp, có thể dùng `@Query`, `Specification`, Criteria API, custom repository implementation hoặc native SQL. Spring Data JPA không cấm viết truy vấn thủ công.

Trong một dự án Spring Boot thường gặp, dependency `spring-boot-starter-data-jpa` tập hợp Spring Data JPA và một JPA provider mặc định (thường là Hibernate), cùng các thành phần tích hợp cần thiết. Ứng dụng vẫn cần cấu hình kết nối và JDBC driver phù hợp với hệ quản trị cơ sở dữ liệu.

**Không nhầm Spring Data JPA với Spring JDBC hoặc Spring Data JDBC:** Spring JDBC (ví dụ `JdbcTemplate`) giúp giảm mã xử lý JDBC; Spring Data JDBC có mô hình repository riêng nhưng không sử dụng JPA persistence context hay Hibernate theo cơ chế Spring Data JPA.

## 7. Cùng một chức năng, bốn cách nhìn

Yêu cầu: “Đổi tên sách có `id = 10`”.

| Cách tiếp cận | Nhà phát triển thường viết gì? | Ai quản lý chuyển đổi object ↔ SQL? |
|---|---|---|
| JDBC | `UPDATE books SET title = ? WHERE id = ?`; gắn tham số, kiểm tra kết quả | Chính mã ứng dụng |
| JPA | `em.find(Book.class, 10L)` rồi `book.setTitle(...)` trong transaction | JPA provider, ví dụ Hibernate |
| Hibernate native | `session.get(Book.class, 10L)` rồi `book.setTitle(...)` trong transaction | Hibernate |
| Spring Data JPA | `repository.findById(10L)` rồi thay đổi entity trong transaction | Spring Data JPA gọi JPA; provider thực thi ORM |

Quan sát quan trọng: dùng Spring Data JPA **không loại bỏ** JPA và Hibernate ở các tầng bên dưới. Dùng JPA với Hibernate cũng thường **không loại bỏ** JDBC ở tầng truy cập cơ sở dữ liệu.

### Transaction và thời điểm gửi SQL

Với JDBC trực tiếp, lập trình viên quyết định SQL và điều khiển transaction qua `Connection` (hoặc để framework quản lý). Với JPA/Hibernate, các thay đổi trên entity đang managed được theo dõi trong persistence context và thường được gửi xuống database khi flush. Spring Data JPA hỗ trợ gọi repository, còn việc quản lý transaction trong ứng dụng Spring thường do Spring Transaction Management đảm nhiệm.

Vì vậy, đừng đánh đồng các thao tác sau:

- **Thay đổi thuộc tính Java**: dữ liệu trong bộ nhớ đã đổi.
- **Flush**: ORM đồng bộ thay đổi thành các lệnh SQL gửi xuống database.
- **Commit**: transaction được xác nhận thành công; trước commit có thể rollback.

Một số thao tác `persist`/`save` có thể khiến SQL được thực hiện sớm hơn, đặc biệt khi cần lấy khóa chính từ database; không nên dựa vào giả định “mọi SQL chỉ chạy đúng lúc commit”.

## 8. Khi nào nên chọn công nghệ nào?

Đây không phải bốn lựa chọn loại trừ lẫn nhau. Bạn chọn **tầng API để viết mã**, rồi cấu hình những thành phần bên dưới cho phù hợp.

| Bối cảnh | Hướng phù hợp | Lý do |
|---|---|---|
| Cần câu SQL đặc thù, sử dụng nhiều tính năng riêng của DBMS, hoặc muốn kiểm soát từng hàng kết quả | JDBC, thường qua Spring JDBC/JdbcTemplate nếu đang dùng Spring | SQL tường minh, dễ kiểm soát đường thực thi |
| Ứng dụng không dùng Spring nhưng cần model entity và ORM chuẩn hóa | JPA với một provider như Hibernate | API chuẩn, có persistence context, quan hệ và dirty checking |
| Cần chức năng chuyên biệt mà JPA chuẩn không cung cấp | Hibernate native API khi cần thiết | Truy cập trực tiếp các khả năng riêng của provider |
| Ứng dụng Spring có CRUD, tìm kiếm và phân trang trên entity quan hệ | Spring Data JPA + JPA provider | Repository ngắn gọn, tích hợp tốt với Spring |
| Truy vấn báo cáo phức tạp hoặc batch khối lượng lớn trong ứng dụng đang dùng JPA | Kết hợp JPA với native SQL/JDBC khi hợp lý | Giữ ORM cho nghiệp vụ chính và chủ động tối ưu các đường truy vấn quan trọng |

Không có quy tắc “ORM luôn chậm hơn JDBC” hoặc “Spring Data JPA luôn nhanh hơn JPA”. Hiệu năng thực tế phụ thuộc số câu SQL, cách fetch dữ liệu, batch, index, kích thước transaction, connection pool và thiết kế truy vấn. Một câu SQL tốt có thể hiệu quả hơn nhiều lần truy cập entity; ngược lại, ORM được cấu hình đúng giúp giảm lỗi thủ công và hỗ trợ xây dựng nghiệp vụ phức tạp.

## 9. Các ngộ nhận dễ gặp khi đi làm

### “Cứ có `@Entity` là dùng JPA, không cần Hibernate nữa?”

Không đúng. `@Entity` là metadata theo đặc tả JPA; cần JPA provider xử lý metadata và thực thi thao tác persistence. Provider thường được dự án Spring Boot sử dụng là Hibernate.

### “Hibernate và JPA là hai công cụ cạnh tranh?”

Không hoàn toàn. Hibernate là một trong các triển khai JPA. Khi viết mã theo JPA API nhưng sử dụng Hibernate làm provider, bạn **đang dùng cả JPA lẫn Hibernate**, chỉ ở hai vai trò khác nhau.

### “Spring Data JPA có thể hoạt động không có JPA provider?”

Không. Spring Data JPA xây dựng tầng repository dựa trên JPA, nên vẫn cần một JPA provider thích hợp và cấu hình persistence.

### “Gọi `save()` thì lập tức có một SQL INSERT?”

Không nhất thiết. `save()` có thể tương ứng với `persist` hoặc `merge` tùy trạng thái entity. SQL có thể chạy khi flush hoặc sớm hơn tùy trường hợp; `saveAndFlush()` yêu cầu flush nhưng cũng không tương đương với commit transaction.

### “Dùng ORM thì không cần quan tâm N+1 query?”

Ngược lại, ORM có thể khiến hiện tượng **N+1** khó nhận ra: truy vấn ban đầu lấy N entity, sau đó việc truy cập một quan hệ lazy tạo thêm N truy vấn. Cần cân nhắc fetch join, entity graph, batch fetching hoặc projection tùy yêu cầu. Lazy loading ngoài một persistence context/session khả dụng có thể gây lỗi ở Hibernate.

### “Có JPA rồi thì để ORM tự tạo schema trên production?”

ORM có thể hỗ trợ tạo/cập nhật schema trong môi trường phát triển, nhưng hệ thống production nên quản lý tiến hóa schema có kiểm soát bằng migration như Flyway hoặc Liquibase và kiểm tra trước khi triển khai. Các annotation ánh xạ không thay thế chiến lược migration.

### “`@Query` luôn là SQL?”

Mặc định, truy vấn khai báo trong Spring Data JPA `@Query` là **JPQL**. Chỉ khi sử dụng chế độ native thích hợp (ví dụ `nativeQuery = true`) thì nội dung mới được hiểu là native SQL. Tên entity và thuộc tính của JPQL khác tên bảng/cột trong SQL.

## 10. Cách ghi nhớ khi đọc code một dự án thực tế

Đọc các dấu hiệu sau để biết dự án đang dùng tầng nào:

| Nhìn thấy trong code | Điều đó thường cho biết |
|---|---|
| `DriverManager`, `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` | Đang tương tác với JDBC |
| `@Entity`, `@OneToMany`, `EntityManager`, `TypedQuery` | Đang dùng mô hình/API JPA |
| `org.hibernate.Session`, `SessionFactory`, Hibernate-specific annotations | Đang dùng khả năng API riêng của Hibernate |
| `JpaRepository<Book, Long>`, `findByTitle...`, `Pageable` | Đang dùng repository của Spring Data JPA |
| `@Transactional` trên service Spring | Spring quản lý transaction; chưa đủ để kết luận dùng JDBC hay JPA |

Thử tự trả lời ba tình huống:

1. **Một service chỉ gọi `bookRepository.findById(id)`, nhưng log vẫn xuất hiện `SELECT ... FROM books`. Ai tạo truy vấn?** Spring Data JPA cung cấp lời gọi repository; JPA provider (thường Hibernate) xử lý truy vấn, và JDBC chuyển lệnh đến database.
2. **Muốn dùng một câu lệnh SQL đặc biệt để cập nhật hàng loạt, liệu bắt buộc bỏ Spring Data JPA?** Không. Có thể dùng native query hoặc một thành phần JDBC riêng, miễn là xử lý transaction và trạng thái entity nhất quán.
3. **Thay provider từ Hibernate sang EclipseLink mà vẫn giữ `JpaRepository` được không?** Về nguyên tắc có, vì Spring Data JPA dựa trên JPA. Tuy nhiên cần cấu hình và kiểm thử lại các điểm phụ thuộc provider, dialect, tính năng mở rộng và hành vi thực tế.

Khi thiết kế tầng persistence cho một ứng dụng Java, hãy bắt đầu từ nhu cầu: cần kiểm soát SQL trực tiếp đến đâu, mô hình entity có phức tạp không, có dùng Spring không, và tác vụ nào cần tối ưu riêng. Từ đó xác định nên viết ở tầng JDBC, JPA, Hibernate API hay Spring Data JPA; các tầng còn lại có thể vẫn hiện diện trong cùng một ứng dụng.
