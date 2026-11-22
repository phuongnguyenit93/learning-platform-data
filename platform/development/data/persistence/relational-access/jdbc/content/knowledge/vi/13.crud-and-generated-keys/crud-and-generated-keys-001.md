# Thiết kế thao tác tạo, đọc, cập nhật và xóa bằng JDBC

JDBC (*Java Database Connectivity*) là API chuẩn của Java để truy cập cơ sở dữ liệu quan hệ qua SQL. Với JDBC, một chức năng CRUD không chỉ gồm bốn câu lệnh `INSERT`, `SELECT`, `UPDATE`, `DELETE`: mã ứng dụng còn phải quản lý kết nối, tham số SQL, kết quả trả về, transaction, tài nguyên và trường hợp nhiều người cùng sửa dữ liệu.

Trong chương **CRUD và khóa sinh**, bài này xây dựng một lớp truy cập dữ liệu có thể tái sử dụng; đồng thời giải thích cách lấy khóa chính được cơ sở dữ liệu sinh sau thao tác tạo bản ghi.

Sau bài học, bạn có thể:

- Thiết kế hợp đồng của các phương thức `create`, `findById`, `findPage`, `update` và `delete`.
- Dùng `PreparedStatement` và `ResultSet` để chuyển đổi an toàn giữa Java và bảng quan hệ.
- Lấy khóa tự sinh qua `Statement.RETURN_GENERATED_KEYS` và `getGeneratedKeys()`.
- Hiểu ý nghĩa của số dòng bị ảnh hưởng, transaction và kiểm soát cập nhật đồng thời.
- Nhận biết những lỗi thiết kế CRUD thường gây mất dữ liệu hoặc rò rỉ tài nguyên.

## 1. Bắt đầu từ hợp đồng dữ liệu

Giả sử ứng dụng quản lý sách có bảng `books`:

```sql
CREATE TABLE books (
    id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title   VARCHAR(200) NOT NULL,
    author  VARCHAR(120) NOT NULL,
    price   DECIMAL(12, 2) NOT NULL CHECK (price >= 0),
    version INTEGER NOT NULL DEFAULT 0
);
```

Đây là cú pháp minh họa phù hợp với PostgreSQL hoặc H2 hiện đại. Kiểu sinh khóa (`IDENTITY`, `AUTO_INCREMENT`, `SEQUENCE`), cú pháp phân trang và một số chi tiết SQL khác thay đổi theo hệ quản trị cơ sở dữ liệu; giao diện JDBC vẫn cung cấp cùng các loại đối tượng cơ bản.

| Nghiệp vụ | Câu lệnh SQL | Lời gọi JDBC | Kết quả phù hợp |
|---|---|---|---|
| Tạo sách | `INSERT INTO ... VALUES (...)` | `executeUpdate()` và `getGeneratedKeys()` | ID vừa sinh hoặc lỗi |
| Đọc theo ID | `SELECT ... WHERE id = ?` | `executeQuery()` | `Optional<Book>` |
| Liệt kê | `SELECT ... ORDER BY ...` | `executeQuery()` | Danh sách, có giới hạn |
| Sửa sách | `UPDATE ... WHERE id = ? AND version = ?` | `executeUpdate()` | Có sửa được hay không |
| Xóa sách | `DELETE ... WHERE id = ? AND version = ?` | `executeUpdate()` | Có xóa được hay không |

Các quyết định thiết kế quan trọng:

1. **ID do cơ sở dữ liệu quản lý.** Client không gửi `id` khi tạo sách; chỉ nhận ID sau khi lệnh `INSERT` thành công và driver trả khóa.
2. **Đối tượng đầu vào khác đối tượng đã lưu.** `NewBook` chứa dữ liệu cần tạo; `Book` có thêm `id` và `version`.
3. **Không tìm thấy là một trường hợp hợp lệ của thao tác đọc.** `Optional.empty()` diễn đạt điều đó rõ hơn việc trả `null`.
4. **Sửa/xóa có điều kiện.** `version` dùng cho *optimistic locking* nhằm tránh âm thầm ghi đè thay đổi của phiên khác.
5. **DAO/repository chỉ lo truy cập dữ liệu.** Kiểm tra quy tắc nghiệp vụ, phân quyền và điều phối nhiều thao tác nằm ở lớp service.

## 2. Một repository JDBC đầy đủ

Ví dụ dùng Java 17+ (`record`) và `javax.sql.DataSource`. `DataSource` được cấu hình ở bên ngoài (thường thông qua connection pool hoặc dependency injection); mỗi phương thức tự lấy một `Connection` và đóng bằng `try-with-resources`. Driver JDBC cho hệ cơ sở dữ liệu tương ứng phải có trên classpath.

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class BookRepository {
    public record NewBook(String title, String author, BigDecimal price) {}

    public record Book(
            long id,
            String title,
            String author,
            BigDecimal price,
            int version) {}

    private final DataSource dataSource;

    public BookRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    // CREATE: chỉ chèn các cột do ứng dụng cung cấp.
    public long create(NewBook input) throws SQLException {
        Objects.requireNonNull(input);
        String sql = "INSERT INTO books (title, author, price) VALUES (?, ?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     sql, Statement.RETURN_GENERATED_KEYS)) {

            statement.setString(1, input.title());
            statement.setString(2, input.author());
            statement.setBigDecimal(3, input.price());

            int affected = statement.executeUpdate();
            if (affected != 1) {
                throw new SQLException("INSERT cần ảnh hưởng đúng một dòng: " + affected);
            }

            try (ResultSet keys = statement.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException("Driver không trả khóa tự sinh");
                }
                long id = keys.getLong(1);
                if (keys.wasNull()) {
                    throw new SQLException("Khóa tự sinh trả về NULL");
                }
                return id;
            }
        }
    }

    // READ: lấy một bản ghi; không tìm thấy thì trả Optional.empty().
    public Optional<Book> findById(long id) throws SQLException {
        String sql = """
                SELECT id, title, author, price, version
                FROM books
                WHERE id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, id);
            try (ResultSet result = statement.executeQuery()) {
                return result.next()
                        ? Optional.of(mapBook(result))
                        : Optional.empty();
            }
        }
    }

    // READ: phân trang theo cú pháp LIMIT/OFFSET của PostgreSQL/H2.
    public List<Book> findPage(int limit, int offset) throws SQLException {
        if (limit < 1 || limit > 100 || offset < 0) {
            throw new IllegalArgumentException("limit 1..100; offset >= 0");
        }

        String sql = """
                SELECT id, title, author, price, version
                FROM books
                ORDER BY id
                LIMIT ? OFFSET ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setInt(1, limit);
            statement.setInt(2, offset);

            try (ResultSet result = statement.executeQuery()) {
                List<Book> books = new ArrayList<>();
                while (result.next()) {
                    books.add(mapBook(result));
                }
                return books;
            }
        }
    }

    // UPDATE: không ghi đè nếu phiên khác đã tăng version.
    public boolean update(Book book) throws SQLException {
        Objects.requireNonNull(book);
        String sql = """
                UPDATE books
                SET title = ?, author = ?, price = ?, version = version + 1
                WHERE id = ? AND version = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setString(1, book.title());
            statement.setString(2, book.author());
            statement.setBigDecimal(3, book.price());
            statement.setLong(4, book.id());
            statement.setInt(5, book.version());
            return statement.executeUpdate() == 1;
        }
    }

    // DELETE: giữ điều kiện version khi quyết định xóa.
    public boolean delete(long id, int expectedVersion) throws SQLException {
        String sql = "DELETE FROM books WHERE id = ? AND version = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, id);
            statement.setInt(2, expectedVersion);
            return statement.executeUpdate() == 1;
        }
    }

    private static Book mapBook(ResultSet result) throws SQLException {
        return new Book(
                result.getLong("id"),
                result.getString("title"),
                result.getString("author"),
                result.getBigDecimal("price"),
                result.getInt("version"));
    }
}
```

### Vì sao repository viết theo cách này?

- `PreparedStatement` thay giá trị vào các dấu `?` theo kiểu dữ liệu; không ghép chuỗi đầu vào của người dùng thành SQL. Điều này bảo vệ câu lệnh trước SQL injection trong **phần giá trị tham số**.
- `setBigDecimal()` và `getBigDecimal()` giữ độ chính xác của `DECIMAL`; dùng `double` cho giá tiền dễ phát sinh sai số biểu diễn nhị phân.
- `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` cả khi có `SQLException`. Với connection pool, `Connection.close()` thường trả kết nối về pool.
- `executeQuery()` dành cho câu lệnh trả `ResultSet`; `executeUpdate()` trả số dòng ảnh hưởng đối với `INSERT`, `UPDATE`, `DELETE`.
- SQL đọc ghi rõ tên cột để tránh thay đổi ngầm khi schema được mở rộng, và `ORDER BY id` tạo thứ tự ổn định cho phân trang.
- Lỗi truy cập dữ liệu được chuyển ra bằng `SQLException`; lớp gọi quyết định ghi log, retry khi phù hợp hoặc ánh xạ lỗi thành phản hồi ứng dụng.

**Lưu ý về tính di động:** `LIMIT ? OFFSET ?` minh họa cho PostgreSQL/H2; một số hệ quản trị dùng `OFFSET ... FETCH` hoặc cú pháp khác. Không đưa trực tiếp tên bảng, tên cột hay hướng sắp xếp chưa kiểm tra từ input vào SQL: dấu `?` chỉ thay được **giá trị**, không thay được identifier. Nếu cần sắp xếp động, dùng danh sách cột cho phép cố định trong code.

## 3. Luồng gọi CRUD trong ứng dụng

Giả sử ứng dụng đã cấu hình `DataSource dataSource`. Có thể sử dụng repository như sau:

```java
BookRepository repository = new BookRepository(dataSource);

long id = repository.create(new BookRepository.NewBook(
        "Effective Java", "Joshua Bloch", new BigDecimal("42.50")));

BookRepository.Book current = repository.findById(id).orElseThrow();

BookRepository.Book edited = new BookRepository.Book(
        current.id(),
        "Effective Java (ấn bản cập nhật)",
        current.author(),
        new BigDecimal("45.00"),
        current.version());

boolean updated = repository.update(edited);
if (!updated) {
    // Bản ghi bị xóa hoặc phiên khác đã sửa trước đó.
    throw new IllegalStateException("Dữ liệu đã thay đổi; cần đọc lại");
}

// Lệnh UPDATE ở trên tăng version từ current.version() lên 1.
boolean deleted = repository.delete(id, current.version() + 1);
```

Ở luồng thực tế, lớp service nên xác thực các giá trị đầu vào, kiểm tra quyền trước khi gọi repository và xử lý tình huống `updated == false` hoặc `deleted == false` theo yêu cầu sản phẩm. Ví dụ trên chỉ mô tả đường đi thành công; nếu người khác cập nhật sau bước `update`, lời gọi `delete` với version cũ sẽ thất bại an toàn.

### CREATE và khóa tự sinh

Khi khai báo `Statement.RETURN_GENERATED_KEYS`, chương trình yêu cầu driver trả khóa do lệnh `INSERT` tạo ra. Sau `executeUpdate()`, gọi `getGeneratedKeys()` và đọc cột đầu tiên của `ResultSet`:

```java
try (PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO books (title, author, price) VALUES (?, ?, ?)",
        Statement.RETURN_GENERATED_KEYS)) {
    // ... bind tham số, rồi statement.executeUpdate() ...
    try (ResultSet keys = statement.getGeneratedKeys()) {
        if (keys.next()) {
            long newId = keys.getLong(1);
        }
    }
}
```

Đoạn rút gọn này chỉ làm nổi bật API; phương thức `create` hoàn chỉnh phía trên đã kiểm tra số dòng ảnh hưởng, kết quả rỗng và giá trị `NULL`. Không dùng `SELECT MAX(id)` để đoán ID vừa tạo: một phiên khác có thể chèn bản ghi cùng lúc. Cũng không mặc định mọi driver hỗ trợ cách trả khóa giống nhau; cần kiểm tra hành vi của driver và hệ quản trị đang dùng. Chẳng hạn PostgreSQL có thể dùng `INSERT ... RETURNING id` khi cần kiểm soát rõ cột trả về.

**Điểm cần chú ý:** Trong chế độ auto-commit mặc định, `INSERT` có thể đã được commit trước khi ứng dụng phát hiện `getGeneratedKeys()` không trả kết quả. Vì vậy không tự động lặp lại `INSERT` chỉ vì không đọc được khóa; thao tác tạo có thể đã thành công trong cơ sở dữ liệu. Những API tạo dữ liệu cần retry nên có cơ chế nhận diện yêu cầu trùng, chẳng hạn một mã nghiệp vụ duy nhất.

### READ và cách ánh xạ hàng

`ResultSet` ban đầu đứng **trước** hàng đầu tiên. `result.next()` chuyển con trỏ đến hàng tiếp theo và cho biết có hàng hay không. Với đọc một ID duy nhất, chỉ cần một lần `next()`; với danh sách, dùng vòng `while (result.next())`. Phương thức `mapBook` gom logic chuyển đổi để mọi nhánh đọc nhất quán.

Khi cột SQL cho phép `NULL`, cần phân biệt giá trị `0` với `NULL` ở các getter kiểu nguyên thủy như `getInt()` và `getLong()` bằng `wasNull()`, hoặc dùng `getObject()` với kiểu tương ứng khi được driver hỗ trợ. Ví dụ trên khai báo `id` và `version` là `NOT NULL`, nên các getter nguyên thủy là phù hợp.

### UPDATE và số dòng bị ảnh hưởng

`UPDATE` trả số dòng ảnh hưởng; với `WHERE id = ? AND version = ?` trên khóa chính, kết quả kỳ vọng là `1` hoặc `0`:

| Kết quả | Diễn giải |
|---|---|
| `1` | Bản ghi tồn tại, version khớp và lệnh cập nhật đã được thực thi. |
| `0` | Không có ID đó **hoặc** bản ghi hiện tại có version khác. |
| Lỗi SQL | Có thể do kết nối, ràng buộc, kiểu dữ liệu hoặc lỗi khác từ cơ sở dữ liệu. |

Không thể phân biệt “không tồn tại” với “xung đột phiên bản” chỉ dựa trên kết quả `0`; nếu API cần thông báo riêng, hãy đọc lại trạng thái và chấp nhận rằng dữ liệu có thể tiếp tục thay đổi giữa các lần đọc. Trong thiết kế đơn giản không dùng optimistic locking, `WHERE id = ?` là đủ nhưng có nguy cơ *lost update* khi hai người ghi đè lên cùng một bản ghi.

### DELETE và chính sách dữ liệu

Luôn có điều kiện `WHERE` trong thao tác xóa theo ID. Với bảng có khóa ngoại, lệnh xóa có thể thất bại vì ràng buộc tham chiếu hoặc gây xóa dây chuyền khi schema có `ON DELETE CASCADE`. Nếu nghiệp vụ cần giữ lịch sử, cân nhắc *soft delete* (`deleted_at`, `is_deleted`) và đảm bảo các truy vấn đọc áp dụng bộ lọc nhất quán; lựa chọn này phụ thuộc yêu cầu lưu trữ, kiểm toán và khôi phục dữ liệu.

## 4. Khi nhiều thay đổi phải thành công cùng nhau: transaction

Mỗi phương thức repository ở trên chạy độc lập với một kết nối mới; khi `autoCommit = true`, mỗi lệnh thay đổi được commit riêng. Nếu một thao tác nghiệp vụ gồm **nhiều câu lệnh phụ thuộc nhau** (chẳng hạn thêm đơn hàng và các dòng chi tiết), tất cả phải dùng **cùng một `Connection`** trong cùng transaction.

```java
try (Connection connection = dataSource.getConnection()) {
    boolean oldAutoCommit = connection.getAutoCommit();
    connection.setAutoCommit(false);

    try {
        // Chạy nhiều PreparedStatement trên CHÍNH connection này.
        // Ví dụ: INSERT orders, lấy generated key,
        // sau đó INSERT order_items với order_id vừa nhận.

        connection.commit();
    } catch (SQLException originalError) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            originalError.addSuppressed(rollbackError);
        }
        throw originalError;
    } finally {
        connection.setAutoCommit(oldAutoCommit);
    }
}
```

Đây là **khung transaction**, phần thao tác SQL cần được bổ sung theo nghiệp vụ. Trong lớp service thật, nên mở transaction tại ranh giới nghiệp vụ và truyền `Connection` đó vào các hàm DAO nội bộ; nếu từng DAO tự gọi `dataSource.getConnection()`, các lệnh sẽ chạy trong các transaction khác nhau. Nếu môi trường có transaction manager (ví dụ Spring), tuân theo cơ chế quản lý transaction của framework để tránh điều phối thủ công chồng chéo.

Khi lỗi xảy ra, rollback giúp hoàn tác các lệnh chưa commit. Mức cô lập transaction (`READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`...) quyết định các hiện tượng đọc/ghi đồng thời được cho phép; nó không thay thế hoàn toàn quy tắc quản lý version và ràng buộc duy nhất. Với transaction phức tạp, hãy xác định thứ tự khóa và thời gian giữ transaction để giảm nguy cơ deadlock.

## 5. Những quyết định để CRUD an toàn khi vận hành

| Vấn đề | Cách xử lý |
|---|---|
| SQL injection | Dùng `PreparedStatement` cho mọi giá trị đầu vào; allowlist khi chọn cột hoặc hướng `ORDER BY` động. |
| Rò rỉ connection | Đóng `Connection`, `PreparedStatement`, `ResultSet` với `try-with-resources`. |
| Mất cập nhật | Dùng điều kiện `version` trong `UPDATE`/`DELETE`, hoặc khóa dòng khi nghiệp vụ yêu cầu. |
| Dữ liệu không hợp lệ | Xác thực ở service, giữ `NOT NULL`, `CHECK`, `UNIQUE`, FK ở database. |
| Thao tác nhiều bước bị dở dang | Dùng transaction chung, commit/rollback rõ ràng. |
| Truy vấn quá nhiều dữ liệu | Đặt giới hạn số hàng, phân trang và chỉ chọn cột cần dùng. |
| Phân trang thiếu ổn định | Dùng `ORDER BY` xác định; với dữ liệu lớn, cân nhắc *keyset pagination* theo ID hoặc khóa sắp xếp. |
| Lỗi khó truy vết | Ghi log thao tác, SQLState, mã lỗi và ngữ cảnh an toàn; không log password hoặc dữ liệu nhạy cảm. |
| Retry gây dữ liệu trùng | Retry có điều kiện theo loại lỗi và dùng idempotency key/ràng buộc unique khi phù hợp. |

Hai tình huống thường bị bỏ sót:

1. **Không có điều kiện `WHERE` trong `UPDATE`/`DELETE`:** câu lệnh có thể ảnh hưởng toàn bảng. Code review và test tích hợp phải phát hiện được lỗi này.
2. **Kiểm tra dữ liệu rồi mới ghi mà thiếu ràng buộc:** hai request đồng thời đều có thể vượt qua bước “chưa tồn tại”. Nếu một giá trị bắt buộc duy nhất, hãy tạo `UNIQUE` trong database và xử lý lỗi vi phạm ràng buộc, thay vì chỉ dựa vào truy vấn `SELECT` trước khi `INSERT`.

## 6. Tự kiểm tra bằng các kịch bản tích hợp

Cần kiểm tra repository trên **một cơ sở dữ liệu thử nghiệm cùng loại với môi trường chạy thật**, vì cú pháp SQL, hành vi khóa sinh và mã lỗi có thể phụ thuộc driver:

| Kịch bản | Kết quả mong đợi |
|---|---|
| `create` với dữ liệu hợp lệ | Thêm đúng một sách, ID trả về là khóa thực tế trong bảng. |
| `findById` với ID đã tạo | Trả đúng `title`, `author`, `price`, `version = 0`. |
| `findById` với ID không có | Trả `Optional.empty()`. |
| `findPage(10, 0)` | Không quá 10 sách, thứ tự theo ID tăng dần. |
| `update` với version hiện tại | Trả `true`, dữ liệu mới được lưu, version tăng 1. |
| `update` bằng version cũ | Trả `false`, không ghi đè dữ liệu mới hơn. |
| `delete` với version cũ | Trả `false`, bản ghi vẫn còn. |
| `delete` với version chính xác | Trả `true`; truy vấn theo ID sau đó không tìm thấy. |
| `INSERT` vi phạm `NOT NULL`/`CHECK` | Cơ sở dữ liệu từ chối và Java nhận `SQLException`. |
| Bước thứ hai trong transaction thất bại | Cả các thay đổi chưa commit ở bước thứ nhất đều rollback. |

Một chu trình kiểm chứng tối thiểu: tạo sách → đọc sách → sửa đúng version → thử sửa lại bằng version cũ → xóa đúng version → xác nhận không tìm thấy. Dữ liệu test cần được cô lập để các lần chạy không ảnh hưởng đến nhau.

## 7. Câu hỏi vận dụng

**Tình huống 1.** Hai người cùng đọc sách ở `version = 3`. A cập nhật thành công, B gửi lệnh `UPDATE ... WHERE id = ? AND version = 3`. Kết quả của B là gì? Vì sao nên thông báo xung đột thay vì tự động ghi đè?

*Gợi ý:* Sau lệnh của A, `version` thành `4`; điều kiện của B không còn khớp nên số dòng ảnh hưởng bằng `0`.

**Tình huống 2.** Sau khi thêm một đơn hàng và lấy `order_id`, chương trình lỗi ở bước thêm chi tiết đơn hàng. Bạn sẽ đặt hai lệnh trong transaction nào, và tại sao không được tạo một kết nối mới cho bước thứ hai?

*Gợi ý:* Cùng `Connection`, tắt auto-commit, `commit()` khi tất cả thành công và `rollback()` nếu có lỗi.

**Tình huống 3.** API cho phép người dùng chọn `sortBy=title|price|id`. Có thể viết `ORDER BY ?` rồi dùng `statement.setString(...)` không?

*Gợi ý:* Không; placeholder đại diện cho giá trị SQL, không đại diện cho tên cột. Ánh xạ input sang một tập tên cột được cho phép trong code, sau đó mới ghép phần identifier đã kiểm soát.

**Ghi nhớ:** Thiết kế CRUD bằng JDBC là thiết kế **hợp đồng dữ liệu, SQL an toàn, vòng đời tài nguyên và hành vi khi có lỗi/cạnh tranh**. Khi các phần này rõ ràng, câu lệnh `INSERT`, `SELECT`, `UPDATE`, `DELETE` trở thành phần triển khai có thể kiểm chứng và bảo trì.
