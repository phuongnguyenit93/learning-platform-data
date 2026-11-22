# queryForStream() và trách nhiệm đóng Stream còn giữ tài nguyên

Khi dùng Spring `JdbcTemplate`, lời gọi `queryForStream()` rất tiện để đọc dữ liệu bằng Java Stream API mà không phải tạo sẵn một `List` lớn. Nhưng **Stream trả về còn gắn với tài nguyên JDBC đang mở**: thường là `ResultSet`, `Statement`/`PreparedStatement` và `Connection` được mượn từ `DataSource`. Người nhận Stream phải **đóng chính Stream đó sau khi dùng**, kể cả khi đã chạy hết `forEach()`, `count()` hoặc `toList()`.

Quy tắc quan trọng nhất:

```java
try (Stream<OrderRow> rows = jdbc.queryForStream(
        "SELECT id, amount FROM orders ORDER BY id",
        (rs, rowNum) -> new OrderRow(
            rs.getLong("id"),
            rs.getBigDecimal("amount")
        ))) {
    return rows.limit(100).toList();
} // Stream.close() được gọi ở đây, kể cả khi có exception
```

Đoạn trên là **thân phương thức minh họa** trong một repository đã có `JdbcTemplate jdbc` và record `OrderRow` tương ứng; chưa phải một chương trình Java độc lập. Điểm chính là `try-with-resources` bao quanh **toàn bộ thời gian xử lý Stream**, không chỉ lúc khởi tạo.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao một `Stream<T>` từ `JdbcTemplate.queryForStream()` khác với `list.stream()` thông thường.
2. Hiểu khi nào câu SQL được thực thi, khi nào từng hàng được ánh xạ và tài nguyên JDBC được giải phóng.
3. Dùng đúng `try-with-resources` cho tất cả kiểu kết thúc Stream, kể cả `limit()`, `findFirst()`, exception và dừng sớm.
4. Phân biệt `queryForStream()` với `query(..., RowMapper)`, `RowCallbackHandler` và `ResultSetExtractor`.
5. Giữ Stream trong ranh giới transaction phù hợp; tránh trả nó từ `@Transactional` sang controller hoặc chạy qua thread khác.
6. Nhận biết nguy cơ connection pool cạn và giới hạn của `fetchSize`, cursor, việc tích lũy bộ nhớ.
7. Viết và chạy ví dụ Spring Boot + H2 an toàn, có output xác định.

**Ngữ cảnh:** Spring Framework 6.x, Java 17+, JDBC đồng bộ. Spring JDBC hỗ trợ `queryForStream` từ Spring Framework 5.3. Hành vi cursor, buffering và giới hạn kết nối vật lý còn phụ thuộc JDBC driver/DBMS.

## 2. Stream Java thông thường và JDBC-backed Stream

Không phải mọi Java Stream đều cần đóng.

```java
List<String> names = List.of("An", "Bình", "Chi");
long count = names.stream().filter(name -> name.length() > 2).count();
```

Stream ở trên đọc dữ liệu đã nằm trong bộ nhớ. Việc không gọi `close()` thường không giữ tài nguyên hệ điều hành. Trong khi đó:

```java
Stream<String> names = jdbc.queryForStream(
    "SELECT name FROM customer ORDER BY name",
    (rs, rowNum) -> rs.getString("name")
);
```

Stream thứ hai lấy dữ liệu từ `ResultSet` sống. Ngay cả khi chưa đọc phần tử nào, lời gọi `queryForStream()` đã cần tạo statement và gọi cơ chế thực thi query của JDBC. Stream trả về giữ đường truy cập kết quả để ánh xạ từng dòng khi được tiêu thụ.

| Tính chất | `List.stream()` | `JdbcTemplate.queryForStream()` |
| --- | --- | --- |
| Nguồn | Collection đã tạo trong RAM | JDBC `ResultSet` và các tài nguyên liên quan |
| Cần connection DB còn mở? | Không | Có trong lúc Stream còn cần đọc |
| Trách nhiệm đóng sau khi dùng? | Thường không có resource đặc biệt | **Có, phải đóng Stream** |
| `toList()` có tự đóng nguồn? | Không cần đóng collection | **Không tự gọi `close()`** |
| Có thể giữ sau khi transaction kết thúc? | Có nếu dữ liệu đã được tạo đầy đủ | Không an toàn nếu còn phụ thuộc JDBC resource |
| Dùng `parallel()`? | Tùy tính toán và nguồn | Tránh: `ResultSet`/connection JDBC không phải pipeline độc lập cho nhiều thread |
| Có bảo đảm bộ nhớ nhỏ? | Dữ liệu đã có trong RAM | Không; driver có thể đệm hết và terminal op có thể thu gom thành `List` |

Một điểm dễ bỏ sót: Java Stream API có phương thức `close()` vì interface `BaseStream` kế thừa `AutoCloseable`, nhưng **terminal operation không có trách nhiệm tự đóng Stream**. `findFirst()` hay `limit(10).toList()` kết thúc pipeline mà tài nguyên JDBC vẫn có thể đang mở.

## 3. Cơ chế bên dưới queryForStream()

Các overload hữu ích của `JdbcTemplate`:

```java
// SQL tĩnh: sử dụng JDBC Statement.
<T> Stream<T> queryForStream(String sql, RowMapper<T> rowMapper);

// Có tham số bind: sử dụng JDBC PreparedStatement.
<T> Stream<T> queryForStream(
    String sql, RowMapper<T> rowMapper, Object... args);

// Kiểm soát tham số PreparedStatement tường minh.
<T> Stream<T> queryForStream(
    String sql, PreparedStatementSetter pss, RowMapper<T> rowMapper);
```

Các chữ ký trên **minh họa dạng API** (không khai báo thành phương thức độc lập để biên dịch trong project), có thể tra cứu trong `JdbcOperations`/`JdbcTemplate` Javadoc. Khi ứng dụng chạy với JDBC driver phù hợp, `RowMapper<T>` chuyển một hàng `ResultSet` thành một giá trị Java.

### 3.1. Vòng đời tài nguyên

```text
Application/Repository              JdbcTemplate              JDBC Driver/DB
         |                                |                          |
         | queryForStream(SQL, mapper)     |                          |
         +------------------------------->| get Connection           |
         |                                +------------------------->|
         |                                | create Statement         |
         |                                | executeQuery(SQL)        |
         |                                +------------------------->|
         |<------- Stream<T> -------------| ResultSet đang mở        |
         |                                |                          |
         | stream.filter/map/forEach      |                          |
         |      đọc hàng theo nhu cầu ----+---- ResultSet.next() --->|
         |                                |                          |
         | stream.close()                 |                          |
         +--------------------------------+--- close ResultSet ------|
         |                                |--- close Statement ------|
         |                                |--- release Connection --->|
         |                                |                          |
```

Trong triển khai `JdbcTemplate`, Stream được tạo từ một bộ duyệt `ResultSet` và đăng ký tác vụ dọn dẹp qua `onClose(...)`. Khi đóng Stream, Spring đóng `ResultSet`, dọn tham số cần xử lý nếu có, đóng statement và gọi `DataSourceUtils.releaseConnection(...)`.

Điều này dẫn đến ba điểm cần nhớ:

- **Thực thi SQL bắt đầu trước khi trả Stream.** Không hiểu “lazy” là DB chưa nhận truy vấn cho đến khi `count()`; việc ánh xạ các hàng mới thường diễn ra dần khi tiêu thụ Stream.
- **Không đảm bảo driver chỉ tải một hàng mỗi lần.** Driver có thể tải trước/đệm toàn bộ kết quả; muốn stream dữ liệu lớn hiệu quả phải xem `fetchSize`, cursor, transaction và khả năng DBMS.
- **Đóng Stream không luôn đóng connection vật lý tức thì.** Ngoài transaction, `DataSourceUtils.releaseConnection` thường trả logical connection cho pool (hoặc đóng physical connection nếu nguồn không pooling). Trong transaction Spring đang hoạt động, connection có thể tiếp tục được transaction manager giữ đến khi commit/rollback.

Đừng dùng `Stream.onClose()` để tự đóng một `ResultSet` hoặc `Connection` mà bạn không trực tiếp sở hữu; Spring đã đăng ký dọn dẹp. Nhiệm vụ của mã ứng dụng là **gọi `close()` trên Stream trả về**, thông thường bằng `try-with-resources`.

## 4. Mẫu đúng: try-with-resources là ranh giới sở hữu

Tệp `OrderRepository.java` dưới đây là lớp Java 17+ dùng trong Spring application có Bean `JdbcTemplate` và bảng `orders(id, customer_id, amount)`. Đó là mã có thể biên dịch khi có Spring JDBC; cần DB/bảng để chạy thành công:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Stream;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class OrderRepository {
    private final JdbcTemplate jdbc;

    public OrderRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record OrderRow(long id, BigDecimal amount) {}

    public List<OrderRow> firstHundredFor(long customerId) {
        String sql = """
            SELECT id, amount
              FROM orders
             WHERE customer_id = ?
             ORDER BY id
            """;

        try (Stream<OrderRow> rows = jdbc.queryForStream(
                sql,
                (rs, rowNum) -> new OrderRow(
                    rs.getLong("id"),
                    rs.getBigDecimal("amount")
                ),
                customerId)) {
            return rows.limit(100).toList();
        }
    }
}
```

**Vì sao đúng?**

1. `jdbc` là dependency dùng chung của singleton repository, nhưng biến `rows` chỉ sống bên trong **một lời gọi phương thức**.
2. `?` được bind bằng tham số `customerId`, tránh SQL injection khi ghép dữ liệu vào chuỗi SQL.
3. `limit(100)` dừng sau tối đa 100 phần tử Java; khi dừng sớm, các hàng còn lại có thể chưa đọc.
4. `return` vẫn chạy phần `close()` tự động trước khi phương thức kết thúc, vì `try-with-resources` có `finally` do Java tạo.
5. Kết quả trả về là `List<OrderRow>` đã ánh xạ, không còn phụ thuộc vào `ResultSet` đang mở.
6. `OrderRow` chứa các kiểu dữ liệu Java đã materialize; không chứa `Connection` hay `ResultSet`.

**Giới hạn:** `limit(100)` ở Java không tương đương với SQL `LIMIT 100` hay `FETCH FIRST 100 ROWS ONLY`. DB có thể vẫn xử lý/tạo nhiều hàng để trả; SQL tối ưu hơn nếu đặt giới hạn phù hợp ở phía DB, kèm `ORDER BY` có thứ tự xác định. Ví dụ dùng `limit(100)` để minh họa **short-circuit + close**.

### 4.1. Phải đóng ngay cả khi Stream được đọc hết

```java
try (Stream<OrderRepository.OrderRow> rows = jdbc.queryForStream(
        "SELECT id, amount FROM orders ORDER BY id",
        (rs, rowNum) -> new OrderRepository.OrderRow(
            rs.getLong("id"), rs.getBigDecimal("amount")
        ))) {
    long count = rows.count();
    System.out.println(count);
}
```

Đoạn này minh họa trong một method đã có `JdbcTemplate jdbc` và bảng `orders`. Vì `count()` là terminal operation, Stream không còn dùng để thực hiện pipeline khác; nhưng **chỉ có phần kết thúc `try` mới gọi `close()`**. Điều tương tự đúng với `forEach()`, `toList()`, `reduce()`, `collect()`, `findFirst()`, `anyMatch()` và các terminal operation khác.

### 4.2. Phải đóng khi exception xảy ra

```java
try (Stream<OrderRepository.OrderRow> rows = jdbc.queryForStream(
        "SELECT id, amount FROM orders",
        (rs, rowNum) -> new OrderRepository.OrderRow(
            rs.getLong("id"), rs.getBigDecimal("amount")
        ))) {
    rows.forEach(row -> {
        if (row.amount().signum() < 0) {
            throw new IllegalStateException("Negative amount: " + row.id());
        }
    });
}
```

Nếu callback ném `IllegalStateException`, JVM vẫn gọi `rows.close()` khi rời khối `try`. Lỗi trong mapper hoặc JDBC trong quá trình đọc Stream có thể xuất hiện **lúc terminal operation chạy**, chứ không nhất thiết ngay khi gọi `queryForStream()`. Khối `try-with-resources` bao cả giai đoạn đó để bảo vệ tài nguyên.

### 4.3. Khi không dùng try-with-resources thì phải có finally

Nếu bị ràng buộc API không thể dùng `try` trực tiếp, cần bảo đảm `close()` trong `finally`:

```java
Stream<String> stream = jdbc.queryForStream(
    "SELECT name FROM customer",
    (rs, rowNum) -> rs.getString("name")
);
try {
    stream.forEach(System.out::println);
} finally {
    stream.close();
}
```

Đây là **đoạn nằm trong phương thức đã có jdbc**; về độ an toàn tài nguyên nó tương đương `try-with-resources`, nhưng nhiều mã hơn và dễ quên. Nên ưu tiên cách đầu tiên.

## 5. Các cách viết sai tạo nguy cơ giữ connection

### 5.1. Gọi toList() rồi bỏ quên Stream

```java
// SAI: toList() không tự đóng JDBC-backed Stream.
public List<String> allNames() {
    return jdbc.queryForStream(
        "SELECT name FROM customer",
        (rs, rowNum) -> rs.getString("name")
    ).toList();
}
```

Nếu `DataSource` là pool, logical connection vẫn có thể được đánh dấu active và không được trả về pool đúng thời điểm. Dù danh sách đã có đủ phần tử, **đừng trông chờ GC/finalizer tự dọn tài nguyên**.

Sửa:

```java
public List<String> allNames() {
    try (Stream<String> names = jdbc.queryForStream(
            "SELECT name FROM customer",
            (rs, rowNum) -> rs.getString("name"))) {
        return names.toList();
    }
}
```

Hai đoạn trên là **thân phương thức** dành cho repository có `JdbcTemplate jdbc` và các import Java thích hợp, không phải các file Java độc lập.

### 5.2. findFirst()/anyMatch()/limit() dừng sớm

```java
// SAI: dù đã tìm ra phần tử, Stream vẫn cần close.
String first = jdbc.queryForStream(
    "SELECT name FROM customer ORDER BY id",
    (rs, rowNum) -> rs.getString("name")
).findFirst().orElse("(none)");
```

Sửa:

```java
try (Stream<String> names = jdbc.queryForStream(
        "SELECT name FROM customer ORDER BY id",
        (rs, rowNum) -> rs.getString("name"))) {
    String first = names.findFirst().orElse("(none)");
    // Dùng first trong phạm vi này hoặc trả một giá trị String.
}
```

Tác vụ chỉ muốn một hàng nên ưu tiên SQL có giới hạn/`queryForObject` phù hợp kỳ vọng 0/1 hàng. `queryForObject` không phải một lựa chọn tương đương khi không chắc chỉ có một hàng: nó có ngữ nghĩa số lượng bản ghi khác nhau và có thể ném exception nếu kết quả không đúng kỳ vọng.

### 5.3. Lưu Stream vào field singleton

```java
// SAI: giữ Stream JDBC cho nhiều request hoặc nhiều thread.
private Stream<Customer> cachedRows;
```

Stream là đối tượng **single-use**, có trạng thái duyệt và sở hữu resource. Không tái sử dụng như cache. Nếu cần cache, hãy materialize các DTO/giá trị đã đọc xong trong phạm vi Stream rồi lưu bản sao dữ liệu đã tách khỏi JDBC, với chính sách invalidation và giới hạn bộ nhớ thích hợp.

### 5.4. Trả ResultSet/Stream cho layer khác mà không có hợp đồng đóng

```java
// SAI: ai chịu trách nhiệm close? Transaction còn sống không?
public Stream<Customer> findAllOpen() {
    return jdbc.queryForStream(
        "SELECT id, name FROM customer",
        (rs, rowNum) -> new Customer(
            rs.getLong("id"), rs.getString("name")
        )
    );
}
```

Đây là **anti-pattern mô tả rủi ro**; nó không phải khuyến nghị API repository. Nếu bắt buộc có API trả Stream, hợp đồng phải nói rõ caller sở hữu resource và **bắt buộc close**, đảm bảo transaction còn hiệu lực khi tiêu thụ; tốt hơn là dùng callback hoặc trả DTO/List/response đã hoàn chỉnh để quản lý vòng đời tại repository/service.

### 5.5. Sai khi nghĩ stream đã được “đóng tự nhiên” vì đã hết hàng

`ResultSet.next()` trả `false` khi hết dữ liệu không đồng nghĩa `ResultSet.close()` đã xảy ra. Hết phần tử là **trạng thái duyệt**; đóng là **hành động giải phóng tài nguyên**. Đó là lý do mã sau vẫn cần `try`:

```java
try (Stream<String> s = jdbc.queryForStream(
        "SELECT name FROM customer",
        (rs, rowNum) -> rs.getString("name"))) {
    s.forEach(System.out::println);
}
```

## 6. queryForStream() khác query(..., RowMapper) như thế nào?

Với `query(sql, rowMapper)`, `JdbcTemplate` thực hiện toàn bộ quá trình đọc và ánh xạ trong phạm vi lời gọi; khi phương thức trả về `List<T>`, tài nguyên JDBC thông thường đã được dọn dẹp.

Với `queryForStream()`, `JdbcTemplate` **chuyển quyền sở hữu việc đóng** cho người nhận Stream vì vòng đời đọc dữ liệu tiếp tục sau khi lời gọi khởi tạo trả về.

| API | Kiểu trả về | Thời điểm dọn JDBC resource | Bộ nhớ |
| --- | --- | --- | --- |
| `query(sql, RowMapper<T>)` | `List<T>` | Khi lời gọi hoàn tất hoặc gặp lỗi, do template quản lý. | Có thể giữ toàn bộ kết quả trong List. |
| `queryForStream(sql, RowMapper<T>)` | `Stream<T>` | Khi **caller gọi close()**; template đã đăng ký dọn trong onClose. | Có thể xử lý từng phần tử, nhưng phụ thuộc driver và terminal operation. |
| `query(sql, RowCallbackHandler)` | `void` | Khi callback xử lý xong trong lời gọi, do template quản lý. | Có thể giữ bộ nhớ nhỏ nếu handler không tích lũy. |
| `query(sql, ResultSetExtractor<R>)` | `R` | Sau khi extractor trả về, do template quản lý. | Do cách extractor xử lý; không trả JDBC handle còn sống. |

### 6.1. RowCallbackHandler là lựa chọn đơn giản khi chỉ xử lý từng dòng

Nếu mục tiêu là duyệt và xử lý dữ liệu mà **không cần trả một Stream**, có thể dùng `RowCallbackHandler`:

```java
import java.util.concurrent.atomic.LongAdder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;

public final class CustomerCounter {
    private final JdbcTemplate jdbc;

    public CustomerCounter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long countNames() {
        LongAdder total = new LongAdder();

        jdbc.query(
            "SELECT name FROM customer",
            (RowCallbackHandler) rs -> {
                if (rs.getString("name") != null) {
                    total.increment();
                }
            }
        );
        return total.sum();
    }
}
```

`RowCallbackHandler` nhận từng hàng do `JdbcTemplate` đưa đến, **không tự gọi `rs.next()`**. Code không cần tự đóng Stream vì không có Stream nào được trả ra. Tuy nhiên driver vẫn có thể buffer các hàng; “xử lý theo từng hàng” không tự đảm bảo mức tiêu thụ bộ nhớ thấp ở mọi DBMS.

### 6.2. ResultSetExtractor cho xử lý chủ động với ResultSet

`ResultSetExtractor<R>` cho phép tự duyệt `ResultSet` trong callback rồi trả một kết quả đã tách khỏi JDBC:

```java
Long total = jdbc.query(
    "SELECT amount FROM orders",
    rs -> {
        long count = 0;
        while (rs.next()) {
            if (rs.getBigDecimal("amount") != null) {
                count++;
            }
        }
        return count;
    }
);
```

Đây là snippet trong phương thức có `jdbc` và bảng `orders`. Với extractor, caller được quyền gọi `rs.next()`; với `RowCallbackHandler` thì không. **Đừng trả `rs` ra khỏi callback**, vì `JdbcTemplate` sẽ đóng tài nguyên khi lời gọi kết thúc.

## 7. Transaction Spring: stream phải được tiêu thụ đúng phạm vi

Trong mô hình Spring JDBC imperative với `DataSourceTransactionManager` hoặc `JdbcTransactionManager`, tài nguyên transaction thường được liên kết với thread hiện tại. `JdbcTemplate` và `DataSourceUtils` dùng connection đã liên kết khi thao tác trong transaction đó.

### 7.1. Mẫu đúng: mở, tiêu thụ, đóng Stream bên trong @Transactional

```java
import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class CustomerReportService {
    private final JdbcTemplate jdbc;

    public CustomerReportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public long countActive() {
        try (Stream<Long> ids = jdbc.queryForStream(
                "SELECT id FROM customer WHERE active = ?",
                (rs, rowNum) -> rs.getLong("id"),
                true)) {
            return ids.count();
        }
    }
}
```

Snippet trên yêu cầu import `org.springframework.jdbc.core.JdbcTemplate`, DB có bảng/cột tương ứng và transaction management được cấu hình. Phương thức được gọi **qua Spring proxy** để `@Transactional` có hiệu lực trong chế độ proxy. Kết nối do transaction quản lý được giữ đúng phạm vi; Stream đóng trước khi transaction hoàn tất.

Với PostgreSQL JDBC, để thực sự lấy dữ liệu theo cursor khi `fetchSize` dương, một điều kiện phổ biến là connection phải ở chế độ không auto-commit trong transaction phù hợp. `@Transactional(readOnly = true)` có thể giúp thiết lập phạm vi giao dịch, nhưng còn phải xác minh driver, loại `ResultSet` và chế độ thực thi. Bản thân `queryForStream()` **không đảm bảo PostgreSQL sẽ chỉ buffer một lô hàng**.

### 7.2. Mẫu rủi ro: @Transactional trả về Stream chưa đọc

```java
// RỦI RO: transaction của phương thức có thể kết thúc trước khi caller duyệt.
@Transactional(readOnly = true)
public Stream<Customer> openCustomers() {
    return jdbc.queryForStream(
        "SELECT id, name FROM customer",
        (rs, rowNum) -> new Customer(
            rs.getLong("id"), rs.getString("name")
        )
    );
}
```

Trong trường hợp này, Spring transaction proxy thường kết thúc transaction ngay sau khi phương thức trả về **đối tượng Stream**; người gọi mới bắt đầu đọc các phần tử về sau. Nếu DB/driver cần connection/cursor còn nằm trong transaction cũ, lúc đó có thể xảy ra lỗi, kết quả không mong muốn hoặc tài nguyên tồn tại quá lâu. Caller cũng rất dễ quên `close()`.

**Thiết kế tốt hơn:** service thực hiện cả truy vấn và xử lý trong cùng phương thức giao dịch rồi trả `List<DTO>`, `long`, giá trị tổng hợp, hoặc thực hiện callback để xử lý theo hàng trước khi thoát transaction. Nếu muốn API lazy/streaming thực sự ra bên ngoài, phải thiết kế một hợp đồng resource và transaction riêng, không dựa vào việc `@Transactional` của phương thức trả Stream tự bao trùm thời gian caller sử dụng.

### 7.3. Đóng Stream trong transaction có trả connection ngay về pool không?

Không nhất thiết. `Stream.close()` gọi `DataSourceUtils.releaseConnection(...)`, nhưng nếu connection **đang gắn với transaction Spring hiện hành**, Spring có thể giữ connection tới commit/rollback. Đây là hành vi đúng để transaction còn dùng được cho các JDBC operation tiếp theo. Nếu ngoài transaction, logical connection thường được trả pool ngay khi đóng Stream.

Đừng đo “đã đóng Stream chưa” chỉ bằng việc chờ số active connection của Hikari lập tức giảm bên trong một transaction còn hoạt động. Hãy xét **cả vòng đời Stream lẫn vòng đời transaction**.

## 8. Không truyền JDBC Stream sang thread khác hoặc làm parallel()

Mã dưới đây là ví dụ **cố tình không an toàn**:

```java
Stream<Customer> rows = jdbc.queryForStream(
    "SELECT id, name FROM customer",
    (rs, rowNum) -> new Customer(rs.getLong("id"), rs.getString("name"))
);
executor.submit(() -> rows.forEach(System.out::println));
```

Snippet minh họa, không phải chương trình độc lập. Nó để Stream/JDBC connection sống vượt phạm vi lời gọi; ThreadLocal transaction context ở thread tạo Stream không tự chuyển sang worker thread. Nếu không có quy tắc sở hữu rõ ràng, có thể quên đóng hoặc đóng trên luồng khác trong khi còn sử dụng.

Tương tự, **không dùng `rows.parallel()` để “tăng tốc query JDBC”**. Một `ResultSet` và một JDBC `Connection` không phải tập truy vấn độc lập cho mỗi worker; các driver có quy tắc concurrency khác nhau và thứ tự/callback có thể không an toàn. Muốn xử lý tính toán song song, có thể **materialize DTO đã tách khỏi JDBC**, đóng Stream, rồi xử lý danh sách hoặc chia truy vấn thành các task DB độc lập có transaction/connection riêng, với mức concurrency phù hợp pool.

Mã an toàn hơn:

```java
List<Customer> customers;
try (Stream<Customer> rows = jdbc.queryForStream(
        "SELECT id, name FROM customer",
        (rs, rowNum) -> new Customer(
            rs.getLong("id"), rs.getString("name")
        ))) {
    customers = rows.toList();
}
// Đã đóng JDBC resources; sau đây chỉ xử lý DTO thuần Java.
customers.parallelStream().forEach(this::processCustomer);
```

Đây cũng là snippet cần tồn tại trong một class có `processCustomer(Customer)`; dùng parallel stream chỉ khi workload CPU và số lượng phần tử hợp lý. Nếu `customers` rất lớn, materialize toàn bộ có thể tốn bộ nhớ; cân nhắc batch/cursor theo kiến trúc phù hợp.

## 9. Ví dụ Spring Boot chạy được: đóng trước khi truy vấn tiếp

Ví dụ Java 17+ dưới đây mô tả toàn bộ một ứng dụng Spring Boot dùng H2 để tạo ba hàng, đọc hai hàng đầu từ `queryForStream()` và tiếp tục query sau khi Stream đã đóng. Cấu hình pool tối đa một connection để làm rõ tầm quan trọng của việc không giữ tài nguyên quá lâu; chương trình **không cố tình rò rỉ connection**.

### 9.1. Gradle

Tệp `build.gradle` trong project Spring Boot đơn giản:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Tệp `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:stream_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=1
spring.datasource.hikari.connection-timeout=2000
```

`connection-timeout=2000` là **2.000 mili-giây** chờ mượn connection trong Hikari, không phải query timeout. Đặt pool size một connection chỉ để dễ nhìn thấy ý nghĩa vòng đời resource trong demo; cấu hình production cần tính theo số instance, concurrency và giới hạn của DB. `DB_CLOSE_DELAY=-1` là lựa chọn H2 dành cho demo in-memory.

### 9.2. Ứng dụng Java đầy đủ

Tệp `src/main/java/example/StreamClosingApplication.java`:

```java
package example;

import java.util.List;
import java.util.stream.Stream;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class StreamClosingApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamClosingApplication.class, args);
    }

    public record Item(int id, String name) {}

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE items (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(50) NOT NULL
                )
                """);

            jdbc.update("INSERT INTO items(id, name) VALUES (?, ?)", 1, "Alpha");
            jdbc.update("INSERT INTO items(id, name) VALUES (?, ?)", 2, "Beta");
            jdbc.update("INSERT INTO items(id, name) VALUES (?, ?)", 3, "Gamma");

            List<String> firstTwo;
            try (Stream<Item> items = jdbc.queryForStream(
                    "SELECT id, name FROM items WHERE id >= ? ORDER BY id",
                    (rs, rowNum) -> new Item(
                        rs.getInt("id"), rs.getString("name")
                    ),
                    1)) {
                firstTwo = items
                    .limit(2)
                    .map(Item::name)
                    .toList();
            } // Stream được đóng dù limit dừng sớm.

            System.out.println("firstTwo=" + firstTwo);

            try (Stream<Item> items = jdbc.queryForStream(
                    "SELECT id, name FROM items",
                    (rs, rowNum) -> new Item(
                        rs.getInt("id"), rs.getString("name")
                    ))) {
                System.out.println("streamCount=" + items.count());
            }

            Integer tableCount = jdbc.queryForObject(
                "SELECT COUNT(*) FROM items", Integer.class
            );
            System.out.println("tableCount=" + tableCount);
        };
    }
}
```

Chạy với Gradle wrapper từ thư mục project:

```bash
./gradlew bootRun
```

Trên Windows PowerShell có thể chạy `.\gradlew.bat bootRun`. Với Java 17+, dependencies đã tải và H2 hoạt động, **các dòng do `System.out` trong chương trình tạo ra** là:

```text
firstTwo=[Alpha, Beta]
streamCount=3
tableCount=3
```

Spring Boot/Hikari còn có thể in log trước và sau ba dòng trên. Các phần tử được `ORDER BY id` trong query thứ nhất, nên kết quả `firstTwo` xác định; `count()` chỉ đếm, không phụ thuộc thứ tự hàng. Pool size một connection vẫn cho phép các query tiếp theo vì các Stream đã được đóng trước khi chạy statement khác.

**Bài demo chứng minh gì?** Đúng cách dùng Java Stream API với `try-with-resources` và có thể tiếp tục dùng `JdbcTemplate` sau khi hoàn tất xử lý. Nó **không** chứng minh rằng driver thực sự lấy từng lô row từ server hay thời gian sử dụng pool tối ưu; để kiểm chứng những vấn đề đó cần metrics/profiling trên driver/DB thực tế.

## 10. Làm thế nào một Stream bị bỏ quên làm cạn connection pool?

Giả sử Hikari pool có tối đa 4 connection và một request thực hiện:

```java
// SAI: không đóng stream.
Stream<String> rows = jdbc.queryForStream(
    "SELECT name FROM items",
    (rs, rowNum) -> rs.getString("name")
);
rows.findFirst(); // terminal operation kết thúc, resource vẫn còn mở
```

Nếu mỗi request lặp lại thói quen trên mà connection không được trả pool đúng lúc, pool có thể dần có 4 connection active, rồi các request khác bị treo chờ hoặc timeout khi mượn connection. Mức độ xảy ra phụ thuộc connection pool/driver và vòng đời thực tế, nhưng đó là nguy cơ đủ nghiêm trọng để luôn buộc close.

```text
Request A --- queryForStream ---> Connection #1 đang giữ
Request B --- queryForStream ---> Connection #2 đang giữ
Request C --- queryForStream ---> Connection #3 đang giữ
Request D --- queryForStream ---> Connection #4 đang giữ
Request E --- getConnection() -> chờ -> connectionTimeout
                            (nếu 4 connection không được trả)
```

Dấu hiệu thường thấy: `HikariPool-... - Connection is not available, request timed out ...`; số active gần maximum, idle thấp, pending/waiting tăng, response time xấu. Đừng chỉ tăng `maximumPoolSize` để “chữa” vì vấn đề resource lifetime vẫn tồn tại.

### 10.1. Cách đo để tìm resource giữ lâu

- **HikariCP:** theo dõi active, idle, pending, total connections và acquisition timeout.
- **Spring Boot Actuator/Micrometer:** dùng metrics `hikaricp.*` khi đã bật và cấu hình đúng.
- **Thread dump / tracing:** xem thread đang giữ transaction, thời gian chạy callback, SQL và chỗ tạo Stream.
- **Leak detection:** Hikari `leakDetectionThreshold` có thể log stack khi connection giữ lâu hơn ngưỡng, nhưng đó là **cảnh báo nghi vấn**, không tự đóng connection hay chứng minh chắc chắn leak.
- **DB monitoring:** quan sát số session, long-running transaction, locks, cursor và query duration.

Không giả định cứ active tăng là leak: một `@Transactional` dài hoặc truy vấn chậm hợp lệ cũng giữ connection. Cần đối chiếu số liệu với ranh giới `close()`/commit/rollback và request path. Trong transaction, Stream đã đóng vẫn có thể chưa làm số active giảm vì transaction manager giữ connection đến cuối giao dịch.

## 11. Bộ nhớ, fetchSize và streaming thực sự

`queryForStream()` có thể giảm nhu cầu tạo `List` ngay lập tức, nhưng **không tự bảo đảm không tốn bộ nhớ**.

- JDBC driver có thể buffer toàn bộ `ResultSet`; cơ chế server-side cursor khác nhau theo DBMS và connection settings.
- `Stream.toList()`, `sorted()` hoặc `collect(toList())` vẫn có thể tích lũy rất nhiều phần tử; `sorted()` thường cần giữ dữ liệu để sắp xếp.
- `limit(n)` trong Java giảm số phần tử được tiêu thụ ở tầng Java, nhưng DB có thể vẫn xử lý nhiều hàng; ưu tiên `ORDER BY ... LIMIT n`/`FETCH FIRST n ROWS ONLY` nếu đúng nghiệp vụ và DB hỗ trợ.
- `fetchSize` chỉ là **hint tới JDBC driver**. Với PostgreSQL JDBC, fetch size dương thường cần transaction/`autoCommit=false` và forward-only result set để dùng cursor fetch; nếu không, driver có thể tải toàn bộ.
- `JdbcTemplate.setMaxRows` hạn chế số hàng trả về qua JDBC ResultSet; nó không thay thế phân trang SQL và không bảo đảm DB chỉ xử lý đúng số hàng đó.
- `JdbcTemplate.setQueryTimeout` giúp đặt timeout statement nhưng không tự đặt deadline cho toàn bộ chuỗi xử lý dữ liệu trong Stream, nhất là callback/network I/O sau câu SQL.

Nếu cần xuất hàng triệu hàng thành tệp hoặc HTTP response, cân nhắc xử lý theo batch ngắn, SQL phân trang/keyset, cursor thật sự được driver hỗ trợ, giới hạn thời gian và cơ chế dừng sớm; không giữ một transaction/connection xuyên suốt một kết nối HTTP có thể bị client bỏ ngang mà không có cleanup đáng tin cậy.

### 11.1. Ví dụ xử lý từng hàng trong phạm vi close

```java
try (Stream<OrderRepository.OrderRow> rows = jdbc.queryForStream(
        "SELECT id, amount FROM orders ORDER BY id",
        (rs, rowNum) -> new OrderRepository.OrderRow(
            rs.getLong("id"), rs.getBigDecimal("amount")
        ))) {
    rows.forEach(row -> {
        // Xử lý nhanh, tránh giữ connection trong tác vụ mạng lâu.
        validateAmount(row);
    });
}
```

Đây là snippet đặt trong class đã có `JdbcTemplate jdbc` và phương thức `validateAmount(...)`. Nếu cần gọi API mạng, gửi dữ liệu qua queue/batch sau khi đã đọc xong và đóng Stream, hoặc thiết kế job có ranh giới giao dịch riêng, thay vì giữ ResultSet và connection khi chờ hệ thống khác.

## 12. Xử lý exception và cancellation

Lỗi có thể xảy ra ở nhiều thời điểm:

1. **Khi gọi `queryForStream()`:** lấy connection, chuẩn bị statement hoặc chạy SQL thất bại. `JdbcTemplate` xử lý lỗi JDBC theo cơ chế của nó; nếu chưa trả Stream thì caller không có Stream để close.
2. **Khi tiêu thụ Stream:** mapper đọc cột sai, driver phát hiện lỗi ở lần `ResultSet.next()` tiếp theo, hoặc code `filter()/map()/forEach()` ném exception. Caller cần `try-with-resources` để close khi thoát sớm.
3. **Khi close:** driver có thể báo lỗi lúc giải phóng resource. `try-with-resources` theo ngữ nghĩa Java giữ exception chính và có thể gắn lỗi close thành suppressed exception. Trong `JdbcTemplate`, thao tác cleanup có xử lý riêng, nên loại exception cụ thể phụ thuộc mã nguồn/driver.

Ví dụ an toàn:

```java
public List<String> loadNames() {
    try (Stream<String> names = jdbc.queryForStream(
            "SELECT name FROM customer",
            (rs, rowNum) -> rs.getString("name"))) {
        return names
            .filter(name -> name != null && !name.isBlank())
            .toList();
    }
}
```

Nếu `filter()` gây exception hoặc code bị ngắt khi đang xử lý, `try` cố gắng đóng Stream. Với việc cancel `CompletableFuture` hoặc request HTTP, **không dựa vào Java Stream tự dọn** nếu luồng xử lý vẫn tồn tại; hệ thống phải chủ động kết thúc scope và chạy cleanup.

**Không tự động retry mọi thao tác sau lỗi JDBC.** Dữ liệu read-only đơn giản có thể được chạy lại theo chính sách phù hợp, nhưng với truy vấn gây side effect, lỗi mạng/timeout không luôn cho biết chắc transaction đã rollback ở phía DB; phải đánh giá idempotency và trạng thái giao dịch.

## 13. Vì sao không trả trực tiếp Stream từ Controller?

Đây là ví dụ thiết kế dễ gặp:

```java
// RỦI RO: Controller trả JDBC-backed Stream cho tầng serialization.
@GetMapping("/customers")
public Stream<CustomerDto> customers() {
    return repository.openCustomers();
}
```

Spring MVC có thể serialize sau khi phương thức controller trả về, trên các hook/thời điểm khác so với transaction mà bạn tưởng còn sống. Khó xác định rõ ai chịu trách nhiệm close Stream khi response hoàn tất, gặp lỗi hoặc client disconnect; còn nguy cơ đưa JDBC resource qua nhiều layer.

Thông thường, controller nên trả **DTO hoặc page đã materialize**:

```java
@GetMapping("/customers")
public List<CustomerDto> customers() {
    return service.listCustomers(100);
}
```

Ở đây `service.listCustomers` chịu trách nhiệm mở, tiêu thụ, đóng Stream trong phạm vi phù hợp trước khi trả dữ liệu. Đây là snippet Controller giả định đã có service/DTO/annotations/import thích hợp. Nếu yêu cầu HTTP streaming lớn, hãy thiết kế pipeline riêng với resource lifecycle/cancellation/backpressure rõ ràng, thay vì trả thẳng `Stream<T>` JDBC.

## 14. Những lỗi phổ biến và cách sửa

| Cách viết hoặc suy nghĩ sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| `jdbc.queryForStream(...).toList()` và bỏ Stream | `toList()` không tự close, có nguy cơ giữ ResultSet/Connection. | `try (Stream<T> s = jdbc.queryForStream(...)) { return s.toList(); }` |
| Gọi `findFirst()` hay `limit(10)` rồi nghĩ đã giải phóng | Short-circuit chỉ dừng duyệt. | Đặt toàn bộ pipeline trong `try-with-resources`. |
| Trả JDBC Stream từ `@Transactional` rồi duyệt ở caller | Transaction kết thúc trước thời điểm duyệt; tài nguyên/cursor không bảo đảm hợp lệ. | Tiêu thụ và close trong cùng transactional method, trả DTO. |
| Trả JDBC Stream trực tiếp qua Spring MVC JSON | Resource lifetime vượt scope controller, cleanup không rõ. | Materialize page/DTO hoặc thiết kế streaming lifecycle minh bạch. |
| Lưu Stream trong singleton/cache | Một Stream single-use bị chia sẻ; giữ JDBC resource. | Cache dữ liệu đã materialize, không cache Stream/ResultSet. |
| Chuyển Stream sang executor/thread khác | Transaction thread-bound không tự theo; JDBC state có thể bị dùng chéo. | Truyền DTO, đóng nguồn trước, mở query riêng trong task nếu cần. |
| Dùng `parallel()` với JDBC Stream | Concurrency trên ResultSet/connection không được bảo đảm. | Duyệt tuần tự; nếu phải song song, tách query/connection hoặc DTO sau khi đóng. |
| Thấy đã đọc hết hàng nên không gọi `close()` | Kết thúc duyệt không phải giải phóng. | Close luôn, kể cả `count()`/`forEach()`. |
| Thấy pool cạn chỉ tăng `maximumPoolSize` | Nguồn leak/lifetime dài vẫn còn. | Đo active/pending, sửa mọi nơi không close và transaction dài. |
| Đặt `fetchSize=100` rồi tin không dùng nhiều RAM | Driver có thể đệm dữ liệu; `toList()` vẫn thu gom. | Kiểm chứng cursor/driver, pipeline, tài nguyên và cấu trúc kết quả. |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `try (Stream<Row> rows = jdbc.queryForStream(...)) { rows.count(); }` có còn cần close sau `count()` không?

**Đáp án:** Có. `count()` là terminal operation nhưng không tự gọi `close()`. Kết thúc khối `try-with-resources` mới bảo đảm gọi close.

**Câu 2.** Tại sao `jdbc.queryForStream(...).findFirst()` có thể làm connection pool cạn dù chỉ đọc một hàng?

**Đáp án:** Stream có thể vẫn giữ ResultSet/Statement/Connection sau khi dừng sớm. Nếu không close, connection mượn từ pool không được trả đúng lúc, nhất là khi nhiều request lặp lại.

**Câu 3.** `queryForStream()` có luôn gửi SQL đến DB khi gọi, hay chỉ đến lúc chạy `toList()`?

**Đáp án:** Trong triển khai `JdbcTemplate`, JDBC statement đã được thực thi trước khi Stream được trả. Phần đọc/ánh xạ từng hàng diễn ra khi tiêu thụ; driver có thể buffer trước.

**Câu 4.** Đóng Stream bên trong `@Transactional` có nhất thiết trả connection vật lý về pool ngay thời điểm đó?

**Đáp án:** Không. Stream.close giải phóng ResultSet/Statement và yêu cầu Spring releaseConnection; connection có thể do transaction manager giữ tới commit/rollback.

**Câu 5.** Có nên trả JDBC-backed Stream từ repository qua controller để Spring MVC serialize trực tiếp?

**Đáp án:** Thường không. Ranh giới transaction/close không rõ; nên trả dữ liệu đã materialize hoặc thiết kế riêng pipeline streaming có cleanup khi hoàn tất/lỗi/cancel.

**Câu 6.** `queryForStream()` và `query(..., RowMapper)` khác nhau về quản lý resource ra sao?

**Đáp án:** `query(..., RowMapper)` trả `List<T>` đã đọc xong và template dọn JDBC trước khi trả. `queryForStream()` trả Stream còn giữ resource, caller phải close.

**Câu 7.** `fetchSize=100` có bảo đảm chỉ giữ 100 bản ghi trong RAM không?

**Đáp án:** Không. Nó là hint; driver có thể buffer, terminal operations có thể tích lũy. Cần kiểm chứng với DB driver thực tế và xem cách consumer xử lý kết quả.

## 16. Checklist code review

- [ ] Mọi lời gọi `JdbcTemplate.queryForStream()` đều có owner rõ ràng chịu trách nhiệm gọi `Stream.close()`.
- [ ] Sử dụng `try-with-resources` bao cả **tạo Stream và tiêu thụ Stream**, kể cả khi pipeline dừng sớm.
- [ ] Không tin terminal operation tự đóng Stream.
- [ ] Repository/service không lưu `Stream`, `Connection`, `Statement`, `ResultSet` sống trong singleton field hoặc cache.
- [ ] Không trả JDBC-backed Stream vượt khỏi transaction, controller, async hoặc thread boundary không có hợp đồng cleanup.
- [ ] Nếu dùng `@Transactional`, Stream đã được tiêu thụ và close trước khi transaction kết thúc.
- [ ] Dùng `PreparedStatement`/bind parameter khi truy vấn có input động.
- [ ] Với dữ liệu lớn, đã phân tích `fetchSize`, cursor, buffering, batch/pagination, vòng đời transaction và độ dài thao tác.
- [ ] Có metrics pool active/pending/timeout và phân biệt leak với transaction hợp lệ đang chạy lâu.
- [ ] Lỗi hoặc cancellation cũng đi qua đường close resource; không dùng `System.gc()` hay chờ finalizer.

## 17. Tài liệu tham khảo

- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `queryForStream` trả Stream cần được đóng; các overload, `RowMapper`.
- [Spring Framework — JdbcTemplate source](https://github.com/spring-projects/spring-framework/blob/main/spring-jdbc/src/main/java/org/springframework/jdbc/core/JdbcTemplate.java): cách đăng ký `onClose` để đóng ResultSet/Statement và gọi `DataSourceUtils.releaseConnection`.
- [Java SE 21 — Stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): resource-bearing Stream, terminal operations và try-with-resources.
- [Spring Framework — DataSourceUtils](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html): release connection có nhận biết transaction.
- [pgJDBC — Query processing](https://jdbc.postgresql.org/documentation/query/): cursor/fetch size và điều kiện driver.

**Điều cần nhớ:** `queryForStream()` trao cho bạn một pipeline đọc JDBC **còn giữ tài nguyên**. Kết thúc pipeline không đồng nghĩa dọn resource. Mở, xử lý, **đóng Stream trong cùng phạm vi rõ ràng**; khi dùng transaction Spring, kết thúc Stream trước khi transaction kết thúc. Chỉ trả các giá trị/DTO đã tách khỏi JDBC ra ngoài scope đó.
