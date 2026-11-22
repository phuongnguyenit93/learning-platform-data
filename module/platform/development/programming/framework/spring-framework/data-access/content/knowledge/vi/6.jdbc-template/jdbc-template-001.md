# JdbcTemplate và JdbcOperations trong kiến trúc truy cập dữ liệu

> **Điểm cốt lõi:** Trong Spring JDBC, `JdbcOperations` là **interface định nghĩa hợp đồng thao tác JDBC**; `JdbcTemplate` là **class hiện thực hợp đồng đó**. Cả hai thuộc `org.springframework.jdbc.core`. Tầng repository có thể phụ thuộc `JdbcOperations` để khai báo những thao tác nó cần, còn Spring cung cấp `JdbcTemplate` để thực hiện chúng bằng `DataSource`, quản lý kết nối/tài nguyên và dịch lỗi SQL. Đây là cách vận dụng nguyên tắc lập trình hướng interface ngay trong tầng truy cập dữ liệu.

Bài viết làm rõ mối quan hệ interface/implementation, vị trí của chúng trong kiến trúc Spring Framework, mã JDBC hoàn chỉnh, xử lý kết quả, transaction, khả năng kiểm thử và những giới hạn cần phân biệt.

## 1. Hai kiểu, một hợp đồng thao tác

Các import cơ bản:

```java
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.JdbcTemplate;
```

Ở mức quan hệ kiểu:

```java
public interface JdbcOperations {
    // Chỉ minh họa ý nghĩa interface; không phải toàn bộ chữ ký API.
}

public class JdbcTemplate implements JdbcOperations {
    // Spring cung cấp implementation thực tế.
}
```

**Đoạn trên là sơ đồ rút gọn, không dùng để tạo hai kiểu trùng tên trong ứng dụng.** Trong dự án thực, luôn import `JdbcOperations` và `JdbcTemplate` từ Spring; không tự định nghĩa lại.

- **`JdbcOperations`:** định nghĩa tập các phương thức JDBC cấp cao, ví dụ `query(...)`, `queryForObject(...)`, `update(...)`, `batchUpdate(...)` và `execute(...)`. Nó chỉ mô tả các thao tác mà bên gọi có thể yêu cầu, không quyết định chi tiết cách tạo và đóng JDBC resource.
- **`JdbcTemplate`:** implementation trung tâm của Spring JDBC. Nó điều phối các bước thực thi: xin connection, chuẩn bị statement, bind tham số, chạy SQL, duyệt `ResultSet`, gọi callback/`RowMapper`, đóng resource và chuyển `SQLException` sang hệ phân cấp `DataAccessException`.
- **`DataSource`:** nguồn cung cấp `java.sql.Connection` cho `JdbcTemplate`. Nó thường được cấu hình làm bean độc lập và có thể sử dụng connection pool.
- **`Connection`:** đối tượng JDBC thực tế mà Spring lấy từ `DataSource` khi cần làm việc với database.

Sơ đồ phụ thuộc:

```text
Tầng service (nghiệp vụ, @Transactional)
                 |
                 v
BookRepository (hợp đồng truy cập Book)
                 ^
                 |
JdbcBookRepository (implementation JDBC)
                 |
                 v
JdbcOperations (interface thao tác JDBC)
                 ^
                 | implements
                 |
JdbcTemplate (implementation Spring)
                 |
                 v
DataSource ---> Connection ---> SQL ---> Database
```

Sơ đồ thể hiện **hai interface ở hai mức khác nhau**:

1. `BookRepository` là **hợp đồng nghiệp vụ về dữ liệu Book**, do ứng dụng tự đặt tên và thiết kế: `findById`, `save`, `findAll`.
2. `JdbcOperations` là **hợp đồng thao tác SQL/JDBC tổng quát**, do Spring cung cấp: `query`, `update`, `execute`.

Không nên gọi `JdbcOperations` là interface repository nghiệp vụ: nó vẫn bộc lộ SQL và JDBC callbacks. Nó giúp tách DAO khỏi **implementation `JdbcTemplate` cụ thể**, nhưng không khiến DAO độc lập hoàn toàn với Spring JDBC.

## 2. Tại sao JdbcTemplate cần có interface JdbcOperations?

Một DAO có thể phụ thuộc class cụ thể:

```java
import org.springframework.jdbc.core.JdbcTemplate;

public final class SimpleBookDao {
    private final JdbcTemplate jdbc;

    public SimpleBookDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }
}
```

Cũng có thể phụ thuộc interface:

```java
import org.springframework.jdbc.core.JdbcOperations;

public final class SimpleBookDao {
    private final JdbcOperations jdbc;

    public SimpleBookDao(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }
}
```

**Hai khối trên là hai lựa chọn thay thế cho cùng một lớp**, không đặt cả hai trong cùng package khi biên dịch. Trong cách thứ hai, code chỉ cần những phương thức được `JdbcOperations` công bố. Spring có thể inject một bean `JdbcTemplate` vì class đó implements interface.

Những lợi ích thực tế khi phụ thuộc `JdbcOperations`:

- **Giảm phụ thuộc vào implementation cụ thể:** DAO khai báo nhu cầu dùng API thực thi JDBC, không cần biết bean nào đang đáp ứng.
- **Dễ mock/stub khi unit test:** có thể tạo mock `JdbcOperations` để kiểm tra điều phối trong DAO mà không cần mock toàn bộ `Connection`, `PreparedStatement` và `ResultSet`.
- **Kiểm soát phạm vi API:** biến kiểu `JdbcOperations` chỉ cho phép gọi những phương thức của hợp đồng; các cấu hình riêng của `JdbcTemplate` như setter cấu hình không xuất hiện ở ranh giới này.
- **Nhất quán với dependency injection:** class có thể nhận interface qua constructor, còn Spring quyết định instance thực tế lúc tạo bean.

Tuy nhiên, **không bắt buộc mọi DAO phải khai báo `JdbcOperations`**. Dùng `JdbcTemplate` trực tiếp là hợp lệ và được Spring hỗ trợ, nhất là khi class cần các phương thức cấu hình/đặc điểm riêng của implementation. Đừng thêm một interface do dự án tự định nghĩa chỉ để sao chép toàn bộ API `JdbcOperations` mà không có ranh giới nghiệp vụ mới.

### Phân biệt polymorphism với việc đổi công nghệ database

Điều sau là hợp lệ về kiểu Java:

```java
JdbcOperations operations = new JdbcTemplate(dataSource);
```

`dataSource` trong ví dụ là một biến `javax.sql.DataSource` đã được cấu hình trước; đoạn code là một câu lệnh trong method/constructor, không phải chương trình độc lập.

Vì `JdbcTemplate implements JdbcOperations`, biến interface có thể trỏ đến instance cụ thể. Nhưng **đổi từ JDBC sang JPA hay R2DBC không chỉ bằng cách thay implementation của `JdbcOperations`**: interface này mang hợp đồng JDBC đồng bộ, còn JPA/R2DBC có mô hình truy cập khác. Muốn tách nghiệp vụ khỏi công nghệ persistence, hãy đặt interface repository theo miền nghiệp vụ ở tầng cao hơn như `BookRepository`.

## 3. JdbcTemplate làm gì thay cho JDBC thuần?

Nếu dùng JDBC thuần để lấy các bản ghi, lập trình viên thường phải:

1. Lấy `Connection` qua `DataSource.getConnection()`.
2. Tạo `PreparedStatement`.
3. Bind từng tham số vào các placeholder `?`.
4. Gọi `executeQuery()`.
5. Lặp `ResultSet` và đọc từng cột theo kiểu.
6. Đóng `ResultSet`, `Statement` và giải phóng `Connection` cả khi có lỗi.
7. Xử lý `SQLException`, phân biệt lỗi database và quyết định đường truyền lỗi lên tầng trên.

`JdbcTemplate` giữ phần lớn cơ chế lặp lại đó và cho code ứng dụng cung cấp SQL, tham số và cách ánh xạ dữ liệu. Ví dụ:

```java
List<String> titles = jdbc.query(
    "SELECT title FROM books WHERE price >= ? ORDER BY id",
    (rs, rowNum) -> rs.getString("title"),
    100
);
```

`jdbc` là một biến `JdbcOperations` hoặc `JdbcTemplate` đã được inject; `titles` nhận danh sách theo thứ tự SQL yêu cầu. Đây là **đoạn code trong method** có bảng `books`, không phải tệp Java độc lập.

Spring dùng `RowMapper<String>` (biểu diễn bằng lambda) để chuyển mỗi hàng sang một `String`. Không cần tự viết vòng lặp `while (resultSet.next())`, đóng statement hoặc trả connection. Khi SQL cần tham số, dùng `?` và bind giá trị để tránh ghép dữ liệu người dùng trực tiếp vào câu SQL.

### Bảng phân công trách nhiệm

| Công việc | `JdbcTemplate`/Spring xử lý | Code ứng dụng xử lý |
| --- | --- | --- |
| Kết nối | Lấy/trả JDBC connection qua nguồn phù hợp với transaction | Chọn/cấu hình `DataSource` |
| SQL | Chuẩn bị và thực thi statement | Viết câu SQL đúng nghiệp vụ |
| Tham số | Bind giá trị qua JDBC | Cung cấp giá trị và kiểu dữ liệu phù hợp |
| Kết quả | Duyệt `ResultSet` và gọi callback | Ánh xạ hàng thành record/DTO |
| Tài nguyên | Đóng `ResultSet`, statement, giải phóng connection | Không giữ tham chiếu JDBC resource ra ngoài callback |
| Lỗi | Dịch nhiều `SQLException` sang `DataAccessException` | Quyết định xử lý lỗi có ý nghĩa nghiệp vụ |
| Transaction | Tích hợp cơ chế connection-bound của Spring | Định nghĩa ranh giới `@Transactional` và transaction manager phù hợp |

**Hạn chế:** `JdbcTemplate` không tự biết SQL nghiệp vụ, không bảo đảm truy vấn luôn hiệu quả, không tự ngăn N+1 query, và không thay thế schema, index hay thiết kế transaction.

## 4. Ví dụ ứng dụng Spring Boot hoàn chỉnh: repository phụ thuộc JdbcOperations

Ví dụ sử dụng **Java 17+**, Spring Boot 3.3+, Spring JDBC và H2 in-memory. Tạo một dự án Spring Boot Gradle thông thường có plugin Spring Boot và dependency management, sau đó thêm các dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Đây là phần `dependencies` thêm vào **dự án đã có build script Spring Boot**, không phải toàn bộ tệp `build.gradle`. Với Maven, dùng dependency tương đương. Spring Boot chỉ có thể tự cấu hình `JdbcTemplate` khi các điều kiện như nguồn dữ liệu hợp lệ và các class cần thiết được đáp ứng.

**`src/main/resources/application.yml`:**

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:jdbc_ops_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
```

Ở đây database H2 được tạo trong memory khi ứng dụng chạy và không cần server DB độc lập.

### 4.1. Kiểu dữ liệu trả về

**`src/main/java/example/Book.java`:**

```java
package example;

public record Book(long id, String title, int price) {}
```

`record` có sẵn từ Java 16, phù hợp với Java 17+. Nó tự cung cấp constructor, accessor `id()`/`title()`/`price()` và `toString()` có thể dự đoán được.

### 4.2. Hợp đồng repository nghiệp vụ

**`src/main/java/example/BookRepository.java`:**

```java
package example;

import java.util.List;
import java.util.Optional;

public interface BookRepository {
    int insert(Book book);
    List<Book> findAll();
    Optional<Book> findById(long id);
}
```

Service sử dụng `BookRepository` thay vì viết SQL trực tiếp. Các phương thức mô tả nhu cầu dữ liệu của module: thêm, tìm tất cả, tìm theo định danh.

### 4.3. Repository JDBC dùng JdbcOperations

**`src/main/java/example/JdbcBookRepository.java`:**

```java
package example;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public final class JdbcBookRepository implements BookRepository {
    private static final RowMapper<Book> BOOK_MAPPER =
        (rs, rowNum) -> new Book(
            rs.getLong("id"),
            rs.getString("title"),
            rs.getInt("price")
        );

    private final JdbcOperations jdbc;

    public JdbcBookRepository(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public int insert(Book book) {
        return jdbc.update(
            "INSERT INTO books (id, title, price) VALUES (?, ?, ?)",
            book.id(), book.title(), book.price()
        );
    }

    @Override
    public List<Book> findAll() {
        return jdbc.query(
            "SELECT id, title, price FROM books ORDER BY id",
            BOOK_MAPPER
        );
    }

    @Override
    public Optional<Book> findById(long id) {
        List<Book> found = jdbc.query(
            "SELECT id, title, price FROM books WHERE id = ?",
            BOOK_MAPPER,
            id
        );
        return found.stream().findFirst();
    }
}
```

Giải thích từng điểm:

- `@Repository` cho phép Spring phát hiện class trong component scan và tạo bean, đồng thời làm rõ vai trò tầng truy cập dữ liệu.
- Constructor yêu cầu **`JdbcOperations`**, trong khi bean thực tế thường là **`JdbcTemplate`** do Spring Boot tạo. Đây là dependency inversion qua interface.
- `BOOK_MAPPER` là `RowMapper<Book>` nhận từng hàng kết quả và biến thành record. Callback không giữ `ResultSet` sau khi phương thức kết thúc.
- `insert` gọi `update` và trả số hàng bị tác động; với lần insert thành công thường là 1.
- `findAll` dùng `ORDER BY id` để thứ tự đầu ra rõ ràng. JDBC/Spring không cam kết thứ tự nếu SQL không yêu cầu.
- `findById` dùng `query`, nên truy vấn không có hàng thì trả danh sách rỗng và `Optional.empty()`. Vì `id` là PRIMARY KEY, tối đa chỉ có một hàng; không cần bắt exception "zero rows" của `queryForObject`.
- Placeholder `?` giúp tách giá trị `id`/`title`/`price` khỏi văn bản SQL. Nếu client tự cung cấp tên cột hay cấu trúc SQL động, phải dùng whitelist; placeholder không thể dùng làm tên bảng/cột.

### 4.4. Chạy ứng dụng và quan sát kết quả

**`src/main/java/example/JdbcOperationsDemoApplication.java`:**

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;

@SpringBootApplication
public class JdbcOperationsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JdbcOperationsDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcOperations jdbc, BookRepository books) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE books (
                    id BIGINT PRIMARY KEY,
                    title VARCHAR(100) NOT NULL,
                    price INT NOT NULL
                )
                """);

            System.out.println("insert1=" +
                books.insert(new Book(1L, "Java", 120)));
            System.out.println("insert2=" +
                books.insert(new Book(2L, "Spring", 200)));

            System.out.println("all=" + books.findAll());
            System.out.println("found=" + books.findById(2L));
            System.out.println("missing=" + books.findById(99L));
        };
    }
}
```

Từ thư mục gốc của dự án, chạy:

```bash
./gradlew bootRun
```

Trên Windows, dùng `gradlew.bat bootRun`. Trong database H2 mới và khi không có script schema hoặc dữ liệu bổ sung, những dòng **do chương trình in** (ngoài log của Spring) là:

```text
insert1=1
insert2=1
all=[Book[id=1, title=Java, price=120], Book[id=2, title=Spring, price=200]]
found=Optional[Book[id=2, title=Spring, price=200]]
missing=Optional.empty
```

Vì sao có kết quả đó?

1. Spring Boot tạo `DataSource` từ H2 và cung cấp `JdbcTemplate`; bean concrete đó có thể được inject qua kiểu `JdbcOperations`.
2. `CommandLineRunner` tạo bảng bằng `execute`, sau đó gọi API repository.
3. Hai `INSERT` hợp lệ nên `update` trả 1 cho mỗi lời gọi.
4. `findAll` trả danh sách đã ánh xạ qua `BOOK_MAPPER` và có thứ tự ID tăng dần.
5. `findById(2L)` tìm được một record; ID 99 không có hàng nên trả `Optional.empty()`.
6. Với JDBC/`JdbcTemplate`, những câu lệnh được thực hiện trực tiếp dưới tầng này, không cần tạo entity JPA hay `EntityManager`.

**Giới hạn của ví dụ:** Các file Java trên là chương trình Spring Boot hoàn chỉnh **khi được đặt vào dự án có cấu hình build/dependency tương ứng**. Chúng không thể biên dịch chỉ bằng `javac` của JDK thuần vì cần các thư viện Spring trên classpath. Nếu chạy nhiều lần vào cùng database file hoặc có cơ chế tạo schema khác, kết quả chèn dữ liệu có thể khác; đây là lý do ví dụ dùng H2 in-memory mới.

## 5. Các nhóm thao tác quan trọng trong JdbcOperations

`JdbcOperations` có nhiều overload; hiểu ý nghĩa phương thức quan trọng hơn học thuộc từng chữ ký.

| API | Dùng khi | Hành vi |
| --- | --- | --- |
| `execute(String sql)` | DDL hoặc SQL không cần dữ liệu trả về từ callback | Thực thi câu SQL; các overload `execute` khác nhận callback |
| `update(String sql, Object... args)` | `INSERT`, `UPDATE`, `DELETE` | Trả `int` là số hàng bị tác động; có thể là 0 |
| `query(String sql, RowMapper<T>, Object... args)` | Truy vấn 0..N hàng | Trả `List<T>`; 0 hàng là danh sách rỗng |
| `queryForObject(String sql, Class<T>, Object... args)` | Một hàng, một cột như `COUNT(*)` | Yêu cầu đúng 1 hàng và 1 cột, ánh xạ kiểu mong muốn |
| `queryForObject(String sql, RowMapper<T>, Object... args)` | Đúng 1 hàng cần map thành object | Yêu cầu đúng 1 hàng, không tự biến 0 hàng thành `Optional.empty()` |
| `batchUpdate(...)` | Nhiều thao tác cập nhật được gom batch | Trả thông tin số hàng tác động theo từng batch item, phụ thuộc hỗ trợ JDBC driver |
| `queryForList(...)` | Danh sách kết quả đơn giản | Có overload trả `List<Map<String,Object>>` hoặc danh sách một cột theo kiểu chỉ định |
| `execute(..., callback)`, `query(..., callback)` | Cần can thiệp cách tạo statement hoặc trích xuất kết quả | Cho phép callback JDBC với vòng đời do template quản lý |

### 5.1. `query(...)` khác `queryForObject(...)`

Nếu tìm bản ghi tùy chọn, `query(...)` thường dễ biểu đạt hơn:

```java
List<Book> books = jdbc.query(
    "SELECT id, title, price FROM books WHERE id = ?",
    BOOK_MAPPER,
    42L
);
Optional<Book> one = books.stream().findFirst();
```

Ở đây `BOOK_MAPPER` là `RowMapper<Book>` trong repository đã khai báo, `jdbc` là `JdbcOperations` được inject, và code nằm trong một method.

Ngược lại:

```java
Book book = jdbc.queryForObject(
    "SELECT id, title, price FROM books WHERE id = ?",
    BOOK_MAPPER,
    42L
);
```

`queryForObject` kỳ vọng đúng một hàng; nếu không có hàng thì ném `EmptyResultDataAccessException`, nếu nhiều hàng thì ném lỗi số lượng kết quả (`IncorrectResultSizeDataAccessException` hoặc subclass phù hợp). Với `id` có ràng buộc duy nhất, trường hợp nhiều hàng không xảy ra nếu dữ liệu hợp lệ, nhưng **trường hợp không tồn tại vẫn phải xử lý theo hợp đồng nghiệp vụ**.

Với số đếm:

```java
Integer count = jdbc.queryForObject(
    "SELECT COUNT(*) FROM books WHERE price >= ?",
    Integer.class,
    100
);
```

`COUNT(*)` luôn trả một hàng trong truy vấn tổng hợp đơn giản này nên phù hợp `queryForObject`; giá trị có thể lớn hơn phạm vi `Integer` trong hệ thống rất lớn, khi đó cân nhắc `Long.class`.

### 5.2. Các kiểu callback xử lý ResultSet

`JdbcOperations` cung cấp nhiều kiểu callback:

- **`RowMapper<T>`:** chuyển mỗi hàng thành một object; `query` gom chúng vào `List<T>`. Là lựa chọn thông dụng khi ánh xạ record/DTO.
- **`ResultSetExtractor<T>`:** xử lý cả `ResultSet` và tự quyết định cấu trúc dữ liệu trả về; hữu ích khi nhiều hàng cần gom thành một cấu trúc lồng nhau.
- **`RowCallbackHandler`:** xử lý lần lượt từng hàng, thường để cập nhật một accumulator hoặc stream dữ liệu sang sink do ứng dụng quản lý, không tự tạo `List<T>` như `RowMapper`.

Ví dụ dùng `ResultSetExtractor<Integer>` chỉ để minh họa callback toàn bộ tập kết quả:

```java
Integer count = jdbc.query(
    "SELECT id FROM books",
    rs -> {
        int seen = 0;
        while (rs.next()) {
            seen++;
        }
        return seen;
    }
);
```

Trong câu truy vấn này, cách đếm ở Java hợp lệ nhưng **trong ứng dụng thật nên dùng `SELECT COUNT(*)`** để DB thực hiện công việc hiệu quả hơn. Callback của `ResultSetExtractor` được nhận `ResultSet` chưa tự di chuyển tới hàng đầu; mã phải tự gọi `next()`. Trái lại, trong `RowMapper`, Spring đã di chuyển con trỏ tới hàng tương ứng trước khi gọi callback.

Không lưu hoặc trả chính `ResultSet`/`Connection` ra ngoài callback: template sẽ đóng tài nguyên khi lời gọi kết thúc.

### 5.3. Batch update

Khi có nhiều dòng cần ghi, có thể dùng `JdbcOperations.batchUpdate(...)` thay vì vòng lặp gọi `update(...)` cho mỗi dòng. Ví dụ trong method có `jdbc`:

```java
int[] counts = jdbc.batchUpdate(
    "UPDATE books SET price = ? WHERE id = ?",
    java.util.List.of(
        new Object[] {150, 1L},
        new Object[] {250, 2L}
    )
);
```

Đây là một overload batch cho danh sách bộ tham số trong Spring JDBC hiện đại; driver có thể trả số hàng tác động hoặc giá trị JDBC như `Statement.SUCCESS_NO_INFO` trong một số trường hợp. **Batch không tự động nghĩa là transaction nguyên tử**: cần transaction rõ ràng nếu muốn các bản cập nhật cùng commit/rollback. Đồng thời, batch không bảo đảm database làm ít SQL hơn về mặt logic; lợi ích thường nằm ở số round-trip và tối ưu driver.

## 6. Vị trí trong kiến trúc nhiều tầng

Một cách phân chia trách nhiệm có giá trị lâu dài:

```text
HTTP Controller / Message Consumer
             |
             v
Service (quy tắc nghiệp vụ, transaction boundary)
             |
             v
Domain Repository interface (BookRepository)
             |
             v
Infrastructure implementation (JdbcBookRepository)
             |
             v
JdbcOperations -> JdbcTemplate -> DataSource -> Database
```

**Controller** không cần biết `JdbcTemplate` hay SQL nếu service/repository đã che giấu thao tác dữ liệu. **Service** xử lý quy tắc nghiệp vụ, gọi repository và quyết định transaction. **Repository JDBC** viết câu SQL, bind tham số, mapping result set và trả object phù hợp. **Spring JDBC** đảm nhận vòng đời resource và chuẩn hóa lỗi truy cập dữ liệu.

### Tại sao service nên phụ thuộc BookRepository?

Nếu service trực tiếp phụ thuộc `JdbcOperations` và chứa SQL, logic nghiệp vụ sẽ bị trộn với persistence, làm khó đổi schema/query, test nghiệp vụ độc lập và tái sử dụng chức năng truy cập dữ liệu.

Điều này không có nghĩa **mọi ứng dụng nhỏ đều cần nhiều lớp/interface riêng**. Ứng dụng nhỏ hoặc script SQL đơn giản có thể inject `JdbcOperations` thẳng vào một service. Nhưng khi nghiệp vụ có nhiều use case hoặc cần cô lập chi tiết lưu trữ, một `BookRepository` thể hiện ý định miền thường dễ bảo trì hơn.

### Khi nào chọn field kiểu JdbcTemplate?

Nếu DAO cần một API chỉ có ở `JdbcTemplate`, hoặc cần cấu hình cụ thể ở lúc khởi tạo, dùng kiểu concrete có thể hợp lý. Nếu DAO chỉ cần `query`/`update`, field kiểu `JdbcOperations` là lựa chọn rõ ràng. **Không thay đổi cấu hình của một `JdbcTemplate` dùng chung giữa lúc nhiều request đang chạy**; đối tượng an toàn để chia sẻ sau khi được cấu hình hoàn tất.

## 7. Giao dịch: JdbcTemplate và JdbcOperations có tự tạo transaction không?

**Không.** `JdbcOperations` là interface thao tác JDBC; `JdbcTemplate` thường sử dụng `DataSourceUtils` để tìm connection thích hợp và tham gia transaction do Spring quản lý khi có. Transaction boundary do Spring transaction manager và cấu hình `@Transactional` quyết định, không phải do tên của biến `jdbc`.

Ví dụ service tích hợp với `BookRepository` ở trên:

**`BookBatchService.java`:**

```java
package example;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookBatchService {
    private final BookRepository books;

    public BookBatchService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public void addPair(Book first, Book second) {
        books.insert(first);
        books.insert(second);
    }
}
```

Class này được dùng trong **Spring context có transaction manager cho đúng `DataSource`**, và phương thức được gọi từ một bean khác qua Spring proxy. Nếu câu insert thứ hai gây `DuplicateKeyException` (một unchecked `DataAccessException`), quy tắc rollback mặc định thường rollback cả insert thứ nhất.

Cần phân biệt:

- Gọi từng `jdbc.update(...)` **ngoài** transaction khai báo sẽ phụ thuộc chế độ `autoCommit` của connection và môi trường; không tự coi hai lời gọi là một đơn vị nguyên tử.
- Trong một transaction JDBC Spring, các thao tác qua `JdbcTemplate`/`JdbcOperations` dùng cùng nguồn dữ liệu có thể chia sẻ connection đang được transaction manager bind.
- Transaction được quản lý bằng `DataSourceTransactionManager` hoặc `JdbcTransactionManager` và phải trỏ đúng bean `DataSource`. Nhiều nguồn dữ liệu không tự tham gia một transaction phân tán chỉ vì có một `@Transactional`.
- Nếu tự lấy raw JDBC connection trong transaction Spring, nên dùng `DataSourceUtils.getConnection(dataSource)` và `releaseConnection(connection, dataSource)` hoặc dùng `JdbcTemplate`; gọi `dataSource.getConnection()` trực tiếp trên pool thông thường **không chắc** tham gia transaction đang được bind.
- `@Transactional` theo Spring AOP proxy thường không được áp dụng cho lời gọi nội bộ `this.someMethod()` trong cùng bean; thread mới do `@Async`/`CompletableFuture` tạo ra cũng không tự nhận transaction thread-bound.

Vì vậy, khi code repository khai báo field `JdbcOperations` thay vì `JdbcTemplate`, **quy tắc transaction không đổi**. Runtime vẫn sử dụng implementation và connection management thực tế.

## 8. Lỗi SQL được chuyển thành DataAccessException

Một giá trị lớn của `JdbcTemplate` là cung cấp hệ lỗi Spring thống nhất hơn `SQLException` vốn khác nhau theo DBMS và driver. Các thao tác trong `JdbcOperations` thường ném unchecked `DataAccessException` (hoặc subclass) khi có lỗi truy cập dữ liệu.

Ví dụ các trường hợp điển hình:

| Trường hợp | Loại Spring có thể gặp | Ý nghĩa |
| --- | --- | --- |
| Vi phạm khóa duy nhất | `DuplicateKeyException` | Insert/update đụng ràng buộc unique hoặc PK |
| Truy vấn sai cú pháp | `BadSqlGrammarException` | SQL không hợp lệ cho dialect/schema |
| `queryForObject` không tìm thấy hàng | `EmptyResultDataAccessException` | Kỳ vọng đúng 1 hàng nhưng nhận 0 |
| `queryForObject` nhận nhiều hàng | `IncorrectResultSizeDataAccessException` | Không đúng số lượng kết quả mong đợi |
| Vấn đề tài nguyên DB | Subclass `DataAccessException` tùy nguyên nhân | Timeout, DB không thể truy cập hoặc lỗi driver |

**Không bảo đảm mọi DBMS đều map từng mã SQL sang cùng subclass chi tiết.** Spring sử dụng bộ dịch lỗi tùy JDBC/DBMS/cấu hình. Code nghiệp vụ nên bắt chính xác loại lỗi mình có thể xử lý; những lỗi không thể khôi phục thường để lan lên tầng chính sách ngoại lệ/giao dịch.

Không dựa vào `catch (SQLException)` quanh một lời gọi `jdbc.query(...)` như khi dùng JDBC thuần: contract `JdbcTemplate` dịch lỗi thành unchecked exceptions. Ngược lại, callback JDBC tùy chỉnh có thể được phép khai báo `SQLException` để template dịch ở biên callback.

### Cách xử lý "không tìm thấy"

`queryForObject` có hợp đồng **đúng một kết quả**. Nếu use case cho phép "không có", một trong các cách phù hợp là:

- `query(...)` trả `List<T>`, sau đó chọn `Optional.empty()` như repository ví dụ.
- Dùng `queryForObject(...)` và bắt riêng `EmptyResultDataAccessException` khi đây là một phần chủ đích của hợp đồng.

Không bắt `DataAccessException` rồi đổi tất cả thành `Optional.empty()`: như vậy lỗi syntax, mất kết nối DB và lỗi cơ sở dữ liệu sẽ bị che giấu thành "không tìm thấy dữ liệu".

## 9. JdbcOperations, NamedParameterJdbcOperations và JdbcClient

Ba API này có mối liên quan nhưng **không phải ba tên thay thế cho một interface**:

| API | Cách khai báo tham số | Quan hệ |
| --- | --- | --- |
| `JdbcOperations` | Placeholder vị trí `?` trong các phương thức JDBC cổ điển | Interface được `JdbcTemplate` implements |
| `JdbcTemplate` | Hỗ trợ API thực thi JDBC truyền thống với `?` và các callback | Class implements `JdbcOperations` |
| `NamedParameterJdbcOperations` | Placeholder có tên như `:id`, `:title` | Interface riêng, được `NamedParameterJdbcTemplate` implements |
| `JdbcClient` (Spring 6.1+) | Fluent API dùng tham số theo vị trí hoặc có tên | Facade sử dụng `JdbcOperations`/`NamedParameterJdbcOperations` ở dưới để thực thi |

**`NamedParameterJdbcOperations` không kế thừa `JdbcOperations`.** Khi cần truyền nhiều giá trị có tên hoặc tên tham số rõ ràng, có thể inject interface `NamedParameterJdbcOperations` và dùng `NamedParameterJdbcTemplate` làm implementation.

Ví dụ trong method có `NamedParameterJdbcOperations namedJdbc`:

```java
Integer count = namedJdbc.queryForObject(
    "SELECT COUNT(*) FROM books WHERE price >= :minPrice",
    java.util.Map.of("minPrice", 100),
    Integer.class
);
```

Đây là đoạn dùng interface riêng của Spring:

```java
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
```

Tham số có tên được Spring chuyển/bind thành JDBC statement phù hợp. Tên tham số là cách diễn đạt ý định rõ ràng hơn khi một query dài có nhiều tham số; nó **không tự đổi SQL sang ngôn ngữ truy vấn khác**.

Từ Spring Framework 6.1, `JdbcClient` cung cấp API fluent hợp nhất cho các truy vấn/cập nhật phổ biến và ủy quyền thực thi cho các lớp operations bên dưới. Nó không làm `JdbcOperations` lỗi thời hoặc mất giá trị; các trường hợp callback nâng cao vẫn có thể sử dụng `JdbcTemplate`/`JdbcOperations`.

## 10. Thread safety, connection pool và tài nguyên

`JdbcTemplate` được thiết kế **thread-safe sau khi đã cấu hình xong**. Một bean có thể được inject vào nhiều repository và phục vụ nhiều request đồng thời; mỗi lần thao tác không sử dụng một `Connection` toàn cục duy nhất. Các connection đến từ `DataSource`/pool và được quản lý theo thao tác hoặc giao dịch.

Các quy tắc thực tế:

1. **Đặt `DataSource` và `JdbcTemplate` làm bean dùng chung** trong cấu hình thông thường, thay vì tạo template mới trong mọi request. Nếu tự `new JdbcTemplate(dataSource)`, nó vẫn có thể hoạt động nhưng bean container giúp kiểm soát cấu hình nhất quán.
2. **Không ghi `Connection`, `Statement` hay `ResultSet` vào field của singleton repository.** Chúng có vòng đời ngắn và có trạng thái riêng.
3. **Không giữ resource sau callback.** Ví dụ `RowMapper` phải đọc dữ liệu rồi tạo DTO/record; trả trực tiếp `ResultSet` ra ngoài làm resource bị đóng trước khi bên gọi dùng.
4. **Không dùng `HashSet`/`HashMap` khi code đòi hỏi thứ tự danh sách mà những cấu trúc đó không cam kết.** Muốn DB trả theo thứ tự cần `ORDER BY` phù hợp trong SQL, kể cả khi dùng `JdbcTemplate`.
5. **Cẩn trọng với query streaming.** Khi dùng overload trả `Stream<T>`, người gọi phải đóng stream theo API; không giả định một stream dài vô hạn tự trả connection ngay sau khi tạo.
6. **Tránh query quá lâu trong transaction.** Connection đang được giữ sẽ làm giảm số handle pool có thể cho request khác mượn; đo thời gian giữ connection, pool active/idle/pending và mức đồng thời trước khi tăng pool size.
7. **Cấu hình SQL statement/transaction timeout đúng mức.** Pool acquisition timeout, JDBC query timeout và transaction timeout là các vấn đề khác nhau.
8. **An toàn tham số:** bind giá trị bằng `?` hoặc named parameters; không nối raw dữ liệu người dùng vào SQL. Những thành phần không thể bind như tên cột để sort phải được kiểm tra whitelist.

Với nhiều bean `JdbcTemplate`/`JdbcOperations` hoặc nhiều `DataSource`, Spring có thể không biết inject bean nào. Cần phân biệt rõ qua `@Qualifier`, `@Primary` hoặc bean configuration và đảm bảo transaction manager tương ứng với nguồn dữ liệu. Đừng chỉ quan sát tên field `jdbc` rồi đoán connection đã đi đúng DB.

## 11. Kiểm thử đúng mức trừu tượng

Có hai loại kiểm thử bổ sung nhau:

**Unit test repository với mock `JdbcOperations`:** kiểm tra repository có gọi đúng operation, bind đúng tham số và chuyển dữ liệu sang kết quả nghiệp vụ theo hợp đồng. Vì có thể mock interface, bài test không phải khởi tạo `DataSource` thật. Tuy nhiên, nếu mock `query(...)` trả sẵn `Book`, test **không chứng minh** SQL chạy được trên DB hoặc `RowMapper` ánh xạ đúng cột.

**Integration test với database thật hoặc H2:** thực thi schema và dữ liệu test, gọi repository qua Spring context/`JdbcTemplate` rồi xác minh:
- `INSERT` và `SELECT` đọc đúng dữ liệu/cột.
- Truy vấn với `ORDER BY` thực sự trả thứ tự theo yêu cầu.
- Trường hợp không tìm thấy trả đúng `Optional.empty()`.
- Constraint như unique key hoặc khóa ngoại báo lỗi đúng ở tầng dữ liệu.
- Service có `@Transactional` rollback nhiều lần update cùng nguồn dữ liệu khi phát sinh unchecked exception.
- Khi có nhiều `DataSource`, repository dùng đúng nguồn và transaction manager.

Spring Boot cung cấp slice test `@JdbcTest` để tập trung kiểm thử thành phần JDBC; có thể kết hợp `@Import(JdbcBookRepository.class)` và embedded test database phù hợp. Trong hệ thống sử dụng cú pháp hoặc behavior riêng của PostgreSQL, chỉ kiểm thử bằng H2 có thể bỏ sót khác biệt; khi đó dùng PostgreSQL test thực tế (ví dụ Testcontainers).

Một test chạy nhiều lần và "không lỗi" cũng chưa chứng minh repository quản lý resource tốt: nếu nghi leak, quan sát pool active connections sau lượng thao tác đủ lớn trong điều kiện kiểm thử.

### Câu hỏi quyết định khi thiết kế lớp

- DAO cần những method chung `query`/`update`? Có thể khai báo field là `JdbcOperations`.
- DAO cần API cấu hình/chi tiết cụ thể của `JdbcTemplate`? Xem xét inject concrete type, nhưng cấu hình một lần khi khởi tạo.
- API nghiệp vụ không nên nhìn thấy SQL? Đặt interface repository như `BookRepository`.
- Query có quá nhiều tham số `?`? Có thể dùng `NamedParameterJdbcOperations` với `:paramName`.
- Muốn cú pháp fluent trên Spring 6.1+? Cân nhắc `JdbcClient`.
- Cần bảo đảm atomicity giữa nhiều thao tác? Định nghĩa `@Transactional`/transaction manager, không kỳ vọng `JdbcOperations` tự nhóm các câu lệnh.

## 12. Những hiểu nhầm cần tránh

| Nhận định sai | Điều đúng |
| --- | --- |
| "`JdbcOperations` là class giống `JdbcTemplate`." | `JdbcOperations` là **interface**; `JdbcTemplate` là **implementation**. |
| "Cứ khai báo field `JdbcOperations` là Spring tự tạo bean." | Vẫn cần bean thực tế như `JdbcTemplate`, được cấu hình thủ công hoặc auto-configuration phù hợp. |
| "DAO dùng interface nên không cần SQL." | `JdbcOperations` vẫn là API JDBC tổng quát; repository implementation phải viết SQL. |
| "`JdbcTemplate` luôn mở connection mới cho mỗi query." | `DataSource` có thể là pool và Spring có thể tái sử dụng connection bound với transaction. |
| "Gọi `queryForObject` với 0 hàng sẽ trả `null`." | Không; theo hợp đồng đúng một hàng, 0 hàng gây `EmptyResultDataAccessException`. |
| "`query(...)` tự bảo đảm danh sách theo ID." | Không; thứ tự DB cần `ORDER BY` thích hợp. |
| "`batchUpdate` tự tạo một transaction nguyên tử." | Không; cần ranh giới transaction tương ứng nếu muốn commit/rollback cả batch. |
| "Dùng JdbcTemplate thì DAO phải tự đóng Connection." | Thông thường template quản lý resource; không tự đóng connection của nó qua callback. |
| "Spring JDBC tự phát hiện mọi SQL chậm và tối ưu." | Không; DBA/ứng dụng vẫn cần index, SQL đúng, đo query plan và timeout. |
| "`JdbcOperations`, `NamedParameterJdbcOperations` và `JdbcClient` là cùng một interface." | Đây là các API khác nhau; chúng có thể phối hợp trong cùng hệ Spring JDBC. |

## 13. Tự kiểm tra kiến thức

**Câu 1.** Vì sao có thể viết `JdbcOperations jdbc` nhưng truyền instance `JdbcTemplate` vào constructor?

**Đáp án:** Vì `JdbcTemplate implements JdbcOperations`. Java cho phép biến kiểu interface nhận implementation phù hợp; code DAO chỉ phụ thuộc phương thức được interface công bố.

**Câu 2.** `BookRepository` và `JdbcOperations` trong ví dụ có trùng trách nhiệm không?

**Đáp án:** Không. `BookRepository` mô tả thao tác nghiệp vụ trên sách; `JdbcOperations` mô tả thao tác SQL tổng quát. `JdbcBookRepository` là cầu nối giữa hai hợp đồng.

**Câu 3.** Khi truy vấn có thể không có hàng, vì sao `query(...)` thường dễ đưa về `Optional` hơn `queryForObject(...)`?

**Đáp án:** `query` trả danh sách rỗng nếu 0 hàng; `queryForObject` yêu cầu đúng một hàng và ném exception nếu thiếu.

**Câu 4.** Trong `@Transactional` service, thay field repository từ `JdbcTemplate` sang `JdbcOperations` có làm mất transaction không?

**Đáp án:** Không, nếu Spring inject cùng implementation/`DataSource` và các thao tác vẫn đi qua integration transaction. Transaction do transaction manager và đường gọi qua Spring proxy quyết định.

**Câu 5.** Mock `JdbcOperations` thành công đã chứng minh câu SQL tương thích PostgreSQL chưa?

**Đáp án:** Chưa. Mock chỉ kiểm tra tương tác Java theo hành vi giả lập; cần integration test chạy SQL và schema trên database phù hợp.

**Câu 6.** Khi nào nên viết `JdbcOperations`, khi nào nên viết `NamedParameterJdbcOperations`?

**Đáp án:** `JdbcOperations` cho SQL dùng placeholder vị trí `?`; `NamedParameterJdbcOperations` cho SQL dùng placeholder có tên `:name`. Chọn theo nhu cầu rõ ràng của repository, không giả định hai interface kế thừa lẫn nhau.

## Tài liệu tham khảo

- [Spring Framework — `JdbcOperations` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html): hợp đồng JDBC, các nhóm method và ý nghĩa dùng interface để tăng testability.
- [Spring Framework — `JdbcTemplate` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): implementation, JDBC callbacks, resource management, exception translation.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): cách thực thi SQL, `JdbcTemplate`, `NamedParameterJdbcTemplate`, `JdbcClient`.
- [Spring Framework — Data Access with JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): bảng phân chia trách nhiệm framework và ứng dụng.
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSource`, `DataSourceUtils` và JDBC transaction.
- [Spring Framework — `NamedParameterJdbcOperations` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcOperations.html): hợp đồng named parameters.

**Ghi nhớ:** `JdbcOperations` cho biết repository **có thể làm gì với JDBC**; `JdbcTemplate` quyết định **thực hiện thao tác đó thế nào bằng JDBC và Spring**. Tầng ứng dụng nên cung cấp SQL, mapping và ranh giới nghiệp vụ rõ ràng; để Spring quản lý connection, statement, result set và cơ chế dịch lỗi đúng ngữ cảnh. Muốn độc lập với công nghệ lưu trữ ở cấp nghiệp vụ, hãy tạo một repository interface theo miền thay vì để service trực tiếp phụ thuộc các API SQL.