# Quy định quyền sở hữu tài nguyên trong callback của JdbcTemplate

## 1. Vì sao phải quy định rõ ai sở hữu tài nguyên?

Trong JDBC thuần, người viết code thường tự nhận trách nhiệm cho vòng đời của `Connection`, `Statement`, `PreparedStatement`, `ResultSet`: tạo/mượn, sử dụng, rồi đóng trong `finally` hoặc `try-with-resources`. Khi chuyển sang Spring Framework `JdbcTemplate`, một phần việc đó được **chuyển sang template**. Nếu callback vẫn đóng tài nguyên mà Spring đang quản lý, bạn có thể làm hỏng thao tác đang chạy hoặc ranh giới transaction. Ngược lại, nếu callback tự tạo tài nguyên mới nhưng cho rằng Spring sẽ đóng tất cả thay mình, ứng dụng có thể rò rỉ cursor/statement.

Một quy tắc ngắn gọn nhưng phải hiểu theo từng API:

> **Ai tạo ra tài nguyên và ai được hợp đồng API giao quyền quản lý vòng đời thì người đó chịu trách nhiệm đóng hoặc giải phóng.** `JdbcTemplate` thường sở hữu những tài nguyên nó tạo/cấp trực tiếp. Callback sở hữu những tài nguyên bổ sung do chính callback tạo, trừ khi đã bàn giao chúng cho template theo hợp đồng. Một kết quả dạng `Stream` đặc biệt sẽ chuyển trách nhiệm đóng stream sang người gọi.

Sau bài học, bạn có thể:

1. Phân biệt tài nguyên **được template giao tạm cho callback**, tài nguyên **callback tự mở**, và tài nguyên **thoát khỏi phạm vi lời gọi**.
2. Dùng đúng `RowMapper`, `RowCallbackHandler`, `ResultSetExtractor`, `PreparedStatementCreator`, `PreparedStatementSetter`, `PreparedStatementCallback`, `StatementCallback` và `ConnectionCallback`.
3. Biết khi nào **không được tự đóng** `Connection`, `Statement`, `ResultSet`, và khi nào **phải chủ động đóng** bằng `try-with-resources`.
4. Hiểu việc Spring giải phóng một connection trong transaction không nhất thiết có nghĩa là đóng connection vật lý ngay lập tức.
5. Dùng `queryForStream` an toàn, không trả `ResultSet` hoặc stream lấy trực tiếp từ JDBC callback ra ngoài khi statement đã đóng.
6. Chạy một ví dụ Java 17 với Spring JDBC và H2 để kiểm tra các hợp đồng nêu trên, kể cả một transaction rollback.

**Ranh giới bài học:** chủ đề chính là *ownership và vòng đời tài nguyên trong callback của JdbcTemplate*. Cấu hình `DataSource`, transaction propagation và các chiến lược ORM chỉ được nhắc tới khi ảnh hưởng đến ownership.

## 2. Ba cấp tài nguyên trong luồng JDBC

```text
DataSource (Spring bean / connection pool)
     │
     ├─ mượn Connection
     │      │
     │      ├─ tạo Statement / PreparedStatement / CallableStatement
     │      │      │
     │      │      └─ chạy SQL, nhận ResultSet
     │      │
     │      └─ khi xong: giải phóng connection cho đúng owner
     │
     └─ tiếp tục phục vụ các lời gọi khác
```

- **`DataSource`** thường là bean dùng chung. Đóng một `Connection` đã mượn khác với đóng chính `DataSource` hoặc toàn bộ pool.
- **`Connection`** biểu diễn một phiên làm việc JDBC và trạng thái transaction. Nó có thể là handle/proxy của pool. Spring có thể giữ connection đến khi transaction kết thúc.
- **`Statement` và các lớp con** giữ tài nguyên JDBC liên quan việc thực thi SQL; có thể có cursor/result set đi kèm.
- **`ResultSet`** thường phụ thuộc vào statement và connection đang mở. Nó không phải collection Java độc lập có thể sử dụng sau khi các tài nguyên nền đã đóng.
- **`Stream<T>` do `JdbcTemplate.queryForStream` trả về** là dạng truy cập lười (lazy): stream có thể giữ các tài nguyên JDBC đang mở và vì vậy người gọi phải đóng stream sau khi dùng.

**Không đánh đồng:** “Đóng JDBC handle” và “đóng physical connection” là hai chuyện. Với connection pool, `Connection.close()` thường trả handle về pool; với transaction của Spring, template có thể chỉ release handle và để transaction manager quyết định thời điểm trả/đóng connection. Điều này không làm cho việc gọi `close()` trên object được callback mượn trở nên đúng.

## 3. JdbcTemplate đảm nhiệm điều gì?

Một lời gọi phổ biến:

```java
List<String> names = jdbcTemplate.query(
        "SELECT name FROM users ORDER BY id",
        (rs, rowNum) -> rs.getString("name"));
```

Ở phương thức `query` tiêu chuẩn này, trách nhiệm được phân chia như sau:

1. Người dùng cung cấp SQL và cách ánh xạ một dòng.
2. `JdbcTemplate` lấy connection qua hạ tầng nhận biết Spring transaction.
3. `JdbcTemplate` tạo statement, thực thi query và nhận result set.
4. `JdbcTemplate` duyệt result set, gọi `RowMapper` với mỗi dòng hiện tại.
5. Callback chỉ **đọc dữ liệu cần thiết** và xây dựng giá trị Java (ở đây là `String`).
6. Sau lời gọi, template đóng `ResultSet`/`Statement` theo cấu trúc nội bộ, rồi release `Connection` theo ngữ cảnh transaction.
7. Nếu JDBC ném `SQLException`, template thực hiện exception translation sang hệ `DataAccessException` phù hợp. Một runtime exception do callback ném được lan truyền; với transaction đang hoạt động, việc rollback theo quy tắc của transaction manager/interceptor.

Bạn **không** viết `rs.close()` hay `rs.next()` trong `RowMapper` để “hỗ trợ” việc dọn dẹp. Template đã chịu trách nhiệm về con trỏ và vòng đời resource ở overload này.

### Định nghĩa owner

| Khái niệm | Nghĩa | Hành động đúng |
| --- | --- | --- |
| **Owner** | Thành phần có trách nhiệm release/close tài nguyên ở ranh giới API | Thực hiện cleanup trong `finally` hoặc `try-with-resources` |
| **Borrower** | Thành phần được mượn tài nguyên có sẵn trong callback | Sử dụng trong phạm vi callback, không tự đóng khi owner là template |
| **Handoff** | Callback tạo resource và trả cho template theo contract | Không tự đóng ngay trước khi template dùng; template chịu cleanup sau khi nhận |
| **Escaped resource** | Tài nguyên tiếp tục tồn tại sau khi API trả về | Người nhận phải quản lý lifecycle nếu hợp đồng trả về như vậy; điển hình `queryForStream` |

Không áp dụng câu “mọi callback đều không cần đóng gì” một cách máy móc. Callback có thể tự tạo statement/result set mới, mở file, stream hoặc socket riêng. Những tài nguyên phụ đó không tự động thuộc trách nhiệm của `JdbcTemplate`.

## 4. Bảng ownership theo loại callback

Đọc bảng như một contract thực hành; từ “Spring” nghĩa là `JdbcTemplate` hoặc hạ tầng Spring quản lý theo cách gọi cụ thể.

| API/callback | Resource nhận vào | Ai sở hữu resource nhận vào? | Callback cần làm gì? |
| --- | --- | --- | --- |
| `RowMapper<T>` | `ResultSet` đang đứng tại một dòng | Spring | Đọc cột và trả object; không `next()`/`close()` |
| `RowCallbackHandler` | `ResultSet` tại một dòng | Spring | Xử lý đúng dòng hiện tại; không `next()`/`close()` |
| `ResultSetExtractor<T>` qua `query(...)` | `ResultSet` đã thực thi query | Spring | Tự duyệt `next()`, trích xuất dữ liệu; không đóng result set được cấp |
| `PreparedStatementSetter` | `PreparedStatement` đã được tạo | Spring | Bind tham số, có thể chỉnh fetch/query option theo contract; không đóng statement |
| `PreparedStatementCreator` | `Connection` do template cấp; callback trả `PreparedStatement` | Spring sở hữu connection, nhận ownership statement đã trả | Tạo statement hợp lệ và bàn giao; không đóng connection/statement trước khi trả |
| `PreparedStatementCallback<T>` qua `execute` | `PreparedStatement` đang hoạt động | Spring sở hữu statement và connection | Chạy SQL; **đóng các ResultSet tự mở** |
| `StatementCallback<T>` qua `execute` | `Statement` đang hoạt động | Spring sở hữu statement và connection | Chạy SQL; **đóng các ResultSet tự mở** |
| `CallableStatementCallback<T>` qua `execute` | `CallableStatement` đang hoạt động | Spring sở hữu callable statement và connection | Thao tác procedure; đóng ResultSet tự mở, theo contract |
| `ConnectionCallback<T>` qua `execute` | `Connection` do template cấp | Spring | Không đóng connection; **đóng statement/result set tự tạo** |
| `queryForStream(...)` | `Stream<T>` được trả ra khỏi lời gọi | Người gọi sở hữu stream | Dùng `try-with-resources` và đóng stream kể cả khi không duyệt hết |

**Phân biệt hai trường hợp `ResultSet`:**

- Khi dùng `jdbc.query(sql, ResultSetExtractor)`, **template** tạo và quản lý `ResultSet`, callback chỉ mượn.
- Khi dùng `jdbc.execute(sql, PreparedStatementCallback)`, chính callback thường gọi `ps.executeQuery()` rồi nhận `ResultSet`. Javadoc Spring yêu cầu **callback đóng các ResultSet tự mở** ngay cả khi Spring sẽ đóng statement được giao cho callback. Không thể dựa vào giả định “đóng statement thì result set chắc chắn đã được giải phóng thật” trong mọi môi trường, vì statement có thể được pooling.

## 5. RowMapper: chỉ chuyển dòng thành object

`RowMapper<T>` có dạng:

```java
// Snippet trong DAO đã inject JdbcTemplate.
List<UserView> users = jdbcTemplate.query(
        "SELECT id, name FROM users ORDER BY id",
        (rs, rowNum) -> new UserView(
                rs.getLong("id"),
                rs.getString("name")));
```

`UserView` ở đây là record hoặc class ứng dụng định nghĩa. Mỗi lần callback được gọi, `ResultSet` đã nằm tại dòng cần xử lý; `rowNum` là chỉ số dòng (bắt đầu từ 0) trong kết quả ánh xạ, không phải cột `id` của database.

**Không làm:**

```java
// SAI: đây chỉ là code minh họa lỗi, không nên chạy.
(rs, rowNum) -> {
    rs.next();             // Bỏ qua dòng, làm hỏng vòng lặp do template điều khiển.
    String name = rs.getString("name");
    rs.close();            // Đóng cursor của Spring ngay trong mapper.
    return name;
}
```

**Làm đúng:** đọc cột của **dòng hiện tại**, chuyển sang giá trị Java độc lập, rồi trả về. Nếu cần xử lý BLOB/CLOB hoặc binary stream, hãy vật chất hóa nội dung an toàn trong lifetime của result set (và xem giới hạn bộ nhớ) thay vì trả một stream phụ thuộc vào cursor đã bị đóng.

`RowMapper` không nên chứa thao tác JDBC phức tạp hoặc mở thêm statement trên connection đang duyệt: một số driver không cho nhiều result set hoạt động trên cùng connection hoặc có hành vi ngầm đóng cursor. Nếu cần truy vấn bổ sung, cân nhắc JOIN/batch query hay đổi thiết kế data access.

## 6. RowCallbackHandler: callback được gọi từng dòng, không sở hữu cursor

`RowCallbackHandler.processRow(ResultSet rs)` chạy một lần cho từng dòng sau khi `JdbcTemplate` đã gọi `rs.next()` và đặt cursor vào dòng hiện tại. Handler thường được dùng để tích lũy dữ liệu/side effect có kiểm soát.

```java
// Snippet trong method đã có jdbcTemplate.
List<String> names = new ArrayList<>();
jdbcTemplate.query(
        "SELECT name FROM users ORDER BY id",
        (RowCallbackHandler) rs -> names.add(rs.getString("name")));
System.out.println(names);
```

**Sai:** trong callback vừa lặp `while (rs.next())` vừa để `JdbcTemplate` lặp. Điều này sẽ gây nhảy/thiếu dòng. Cũng không đóng `rs` trong handler.

**Lưu ý về trạng thái:** một handler có state có thể phù hợp **cho một lời gọi `query`**. Không dùng cùng một instance handler có mutable field cho nhiều thread/request nếu không bảo đảm an toàn đồng thời. Nếu chỉ muốn tạo một object mỗi dòng và nhận danh sách, `RowMapper` thường đơn giản hơn.

## 7. ResultSetExtractor: tự duyệt nhưng không sở hữu result set do query cấp

`ResultSetExtractor<T>` phù hợp khi bạn cần kết quả tổng hợp hoặc ánh xạ nhiều dòng thành một object.

```java
// Snippet; template tạo/đóng ResultSet.
Integer total = jdbcTemplate.query(
        "SELECT id FROM users ORDER BY id",
        (ResultSetExtractor<Integer>) rs -> {
            int count = 0;
            while (rs.next()) {
                count++;
            }
            return count;
        });
```

Ở overload này:

- Callback **phải tự gọi `rs.next()`** khi muốn duyệt dữ liệu.
- Callback **không gọi `rs.close()`**, vì template là owner.
- Kết quả trả về là một giá trị Java không cần connection nữa, ví dụ `Integer`, DTO, `List`, `Map`.
- Nếu gặp `SQLException` trong callback, bạn có thể để nó thoát ra để template chuyển đổi sang `DataAccessException`. Đừng nuốt lỗi rồi trả kết quả không đầy đủ.

**Ví dụ sai:**

```java
// SAI: trả JDBC ResultSet cho caller sau khi JdbcTemplate.query kết thúc.
ResultSet escaped = jdbcTemplate.query(
        "SELECT * FROM users",
        (ResultSetExtractor<ResultSet>) rs -> rs);
```

Sau khi `query` kết thúc, Spring có thể đã đóng `ResultSet` và statement; object trả ra không còn là dữ liệu độc lập. Hãy chuyển dữ liệu thành object/collection **trong callback**. Đây cũng là lý do không nên trả `InputStream` gắn với LOB/cursor nếu chưa xử lý ownership của stream và backend.

## 8. PreparedStatementSetter và PreparedStatementCreator: hai hợp đồng khác nhau

### 8.1. PreparedStatementSetter nhận statement đã có

```java
// Snippet minh họa; setter không đóng ps.
jdbcTemplate.update(
        "UPDATE users SET name = ? WHERE id = ?",
        ps -> {
            ps.setString(1, "Lan");
            ps.setLong(2, 5L);
        });
```

Spring đã tạo statement và sẽ đóng sau thao tác. Callback chỉ set tham số/thuộc tính được cho phép. Việc gọi `ps.executeUpdate()` ngay trong setter là sai trách nhiệm; template sẽ tự thực thi tiếp theo, có thể dẫn đến ghi hai lần. Cũng không gọi `ps.close()`.

### 8.2. PreparedStatementCreator tạo rồi bàn giao statement

```java
// Snippet: callback tạo PreparedStatement và trả cho JdbcTemplate.
// Ví dụ phù hợp khi cần chỉ định các đặc điểm statement.
PreparedStatementCreator creator = connection -> {
    PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO users (name) VALUES (?)");
    ps.setString(1, "Mai");
    return ps;
};
int changed = jdbcTemplate.update(creator);
```

Ownership sau handoff:

1. Spring cấp `Connection`; creator không đóng connection.
2. Creator tạo `PreparedStatement` và **trả nó** cho template. Không đóng statement trước `return`.
3. Sau khi template thực thi, template dọn statement và release connection.
4. Nếu callback mở các tài nguyên **phụ ngoài statement được bàn giao** (file, stream, statement tạm), callback vẫn phải quản lý chúng.
5. Nếu có exception xảy ra **trước lúc bàn giao** và resource đã được tạo nhưng chưa trả cho template, callback cần dọn tài nguyên mà nó còn sở hữu. Có thể thiết kế creator chỉ làm thao tác chuẩn bị ngắn, hạn chế resource phụ.

Thay vì tạo creator chỉ để bind vài tham số, phương thức `update(sql, args...)` hoặc `PreparedStatementSetter` thường rõ ràng hơn.

## 9. StatementCallback và PreparedStatementCallback: phải đóng ResultSet tự mở

### 9.1. PreparedStatementCallback

```java
// ĐÚNG: Spring sở hữu ps; callback sở hữu ResultSet do ps.executeQuery trả về.
Integer count = jdbcTemplate.execute(
        "SELECT COUNT(*) FROM users WHERE id >= ?",
        (PreparedStatementCallback<Integer>) ps -> {
            ps.setLong(1, 2L);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return 0;
                }
                return rs.getInt(1);
            }
        });
```

Tại sao có `try (ResultSet rs = ...)` nhưng không có `try (PreparedStatement ps = ...)`?

- `ps` do template tạo và chuyển vào callback: **template là owner**.
- `rs` do chính callback gọi `executeQuery()` để mở: **callback phải chủ động đóng**.
- Nếu SQL hoặc việc đọc dữ liệu ném `SQLException`, `try-with-resources` vẫn đóng `rs`; Spring tiếp tục xử lý cleanup của statement/connection và chuyển đổi SQLException.
- Không trả `rs` hoặc `Stream` phụ thuộc vào `rs` ra khỏi callback.

### 9.2. StatementCallback

```java
// Snippet; giả định bảng users tồn tại.
Integer count = jdbcTemplate.execute(
        (StatementCallback<Integer>) statement -> {
            try (ResultSet rs = statement.executeQuery(
                    "SELECT COUNT(*) FROM users")) {
                rs.next();
                return rs.getInt(1);
            }
        });
```

Với callback dạng này, Spring đóng `Statement` sau callback, nhưng các `ResultSet` tự mở cần được đóng trong callback để tránh rò tài nguyên, nhất là khi statement được pooling. Đừng lấy câu “JDBC close statement sẽ đóng result set” làm lý do bỏ cleanup; chi tiết pooling có thể làm tài nguyên tồn tại lâu hơn mong đợi.

### 9.3. CallableStatementCallback

Đối với stored procedure, `CallableStatementCallback<T>` nhận `CallableStatement` từ template. Callback có thể thực thi procedure và đọc `ResultSet`/output parameters. Những result set do callback lấy ra cần được giải phóng theo hợp đồng JDBC; không đóng callable statement mà Spring đã cấp. Với driver có nhiều result set liên tiếp, cần xử lý `getMoreResults`/`getUpdateCount` và vòng đời từng result set cẩn thận.

Đây là use case nâng cao; không nên thêm stored procedure chỉ để minh họa ownership nếu bài toán phù hợp `query`/`update` đơn giản.

## 10. ConnectionCallback: template sở hữu connection, callback sở hữu thứ tự tạo thêm

`JdbcTemplate.execute(ConnectionCallback<T>)` chuyển một JDBC `Connection` vào callback. Callback được quyền gọi các thao tác JDBC thông thường, nhưng **không sở hữu việc đóng connection ấy**.

```java
// ĐÚNG: không đưa connection vào try-with-resources.
// Statement và ResultSet tự tạo thì đóng.
Long count = jdbcTemplate.execute((ConnectionCallback<Long>) connection -> {
    try (PreparedStatement ps = connection.prepareStatement(
                 "SELECT COUNT(*) FROM users");
         ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getLong(1);
    }
});
```

So sánh với JDBC thuần:

```java
// JDBC THUẦN: code tự gọi dataSource.getConnection(), nên phải
// trả/đóng chính connection đó theo hợp đồng của DataSource.
try (Connection ownConnection = dataSource.getConnection();
     PreparedStatement ps = ownConnection.prepareStatement(
             "SELECT COUNT(*) FROM users");
     ResultSet rs = ps.executeQuery()) {
    rs.next();
    System.out.println(rs.getLong(1));
}
```

Trường hợp JDBC thuần trên giả định không có Spring-managed transaction cần tham gia. Nếu code chạy trong Spring transaction nhưng lấy connection độc lập trực tiếp, nó có thể nằm ngoài transaction. Dùng `JdbcTemplate` hoặc `DataSourceUtils` khi cần phối hợp giao dịch.

### Những thao tác cần tránh trên connection được mượn

- Không gọi `connection.close()` hoặc giữ reference để dùng sau callback.
- Không tự `commit()`, `rollback()` hoặc thay đổi `autoCommit` làm phá transaction do Spring quản lý.
- Không tự thay đổi isolation/readOnly/connection state mà không hiểu tác động đến pool/transaction; nếu thay đổi thuộc tính JDBC hợp lệ cho tác vụ, cần đảm bảo restoration.
- Không bàn giao `Connection` cho thread khác hoặc lưu thành mutable field dùng chung.
- Không cố trả `PreparedStatement` hoặc `ResultSet` còn mở cho nơi gọi sau khi callback đã kết thúc.

Một số phiên bản Spring cung cấp close-suppressing proxy cho connection trong `ConnectionCallback`, nhưng đó là chi tiết phòng vệ. Hợp đồng của caller vẫn là **không đóng và không tự quản transaction trên connection do template cấp**.

## 11. Trường hợp khác biệt: queryForStream chuyển trách nhiệm cho caller

Phần lớn API `JdbcTemplate.query` trả kết quả đã được trích xuất khi method hoàn tất. Riêng `queryForStream(...)` trả một `Stream<T>` **lazy và closeable**, có thể đang giữ `ResultSet`, `Statement` và `Connection` để tiếp tục duyệt.

```java
// ĐÚNG: stream được đóng cả khi pipeline bị lỗi hoặc short-circuit.
try (Stream<String> stream = jdbcTemplate.queryForStream(
        "SELECT name FROM users ORDER BY id",
        (rs, rowNum) -> rs.getString("name"))) {
    stream.limit(10).forEach(System.out::println);
}
```

`try-with-resources` rất quan trọng kể cả khi:

- Bạn đã gọi terminal operation như `count()`, `findFirst()` hoặc `forEach()`.
- Pipeline chỉ đọc một phần kết quả rồi dừng.
- Có exception trong bước map/filter/consume.
- Bạn không đi qua mọi phần tử.

**Đừng giả định terminal operation tự gọi `Stream.close()`**; Java Stream thông thường không tự đóng chỉ vì đã xử lý hết pipeline. Không tạo stream rồi quên đóng:

```java
// SAI: thiếu đóng closeable stream.
Stream<String> stream = jdbcTemplate.queryForStream(
        "SELECT name FROM users",
        (rs, rowNum) -> rs.getString("name"));
String first = stream.findFirst().orElse("unknown");
// Khi không đóng stream, tài nguyên JDBC có thể bị giữ lại.
```

**Không trả stream JDBC ra ngoài service mà không có giao ước ownership.** Nếu public API trả `Stream<T>`, caller cần biết phải đóng nó đúng lúc; lazy stream phụ thuộc vào connection và transaction có thể hết hạn. Thường an toàn hơn là trích xuất danh sách có giới hạn hoặc xử lý trọn vẹn trong tầng data access bằng `try-with-resources`.

`queryForRowSet` thường trả abstraction `SqlRowSet` dùng dữ liệu đã được tách khỏi `ResultSet` (tùy RowSet implementation và khả năng driver). Đừng nhầm `SqlRowSet` với JDBC `ResultSet` còn sống; đọc contract của implementation trước khi giả định có thể streaming/giữ tài nguyên dài hạn.

## 12. Ví dụ hoàn chỉnh Java 17: quan sát các loại callback

Ví dụ này dùng **Spring Framework 6.2.14**, **H2 2.3.232**, JDK **17+** và Gradle. Chương trình chỉ dùng Spring Framework thuần, không cần Spring Boot hay database bên ngoài. `DriverManagerDataSource` tiện cho demo, không phải connection pool cho production.

### 12.1. Cấu trúc dự án

```text
jdbc-callback-ownership/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ResourceOwnershipDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'jdbc-callback-ownership'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-jdbc:6.2.14'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.ResourceOwnershipDemo'
}
```

`src/main/java/demo/ResourceOwnershipDemo.java`:

```java
package demo;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementCallback;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class ResourceOwnershipDemo {

    record Job(long id, String name, boolean completed) {}

    @Configuration
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:ownership;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(DataSource dataSource) {
            return new TransactionTemplate(
                    new DataSourceTransactionManager(dataSource));
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate tx = context.getBean(TransactionTemplate.class);

            jdbc.execute("""
                    CREATE TABLE jobs (
                        id BIGINT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        completed BOOLEAN NOT NULL
                    )
                    """);
            jdbc.update("INSERT INTO jobs VALUES (?, ?, ?)",
                    1L, "Thiết kế", false);
            jdbc.update("INSERT INTO jobs VALUES (?, ?, ?)",
                    2L, "Viết mã", true);
            jdbc.update("INSERT INTO jobs VALUES (?, ?, ?)",
                    3L, "Kiểm thử", false);

            // 1) RowMapper chỉ đọc dòng hiện tại, không next/close.
            List<Job> jobs = jdbc.query(
                    "SELECT id, name, completed FROM jobs ORDER BY id",
                    (rs, rowNum) -> new Job(
                            rs.getLong("id"),
                            rs.getString("name"),
                            rs.getBoolean("completed")));
            System.out.println("mapped=" + jobs.size());

            // 2) RowCallbackHandler cũng chỉ xử lý dòng hiện tại.
            List<String> names = new ArrayList<>();
            jdbc.query("SELECT name FROM jobs ORDER BY id",
                    (RowCallbackHandler) rs -> names.add(rs.getString("name")));
            System.out.println("names=" + String.join(", ", names));

            // 3) ResultSetExtractor tự next, Spring đóng ResultSet.
            Integer extracted = jdbc.query(
                    "SELECT id FROM jobs ORDER BY id",
                    (ResultSetExtractor<Integer>) rs -> {
                        int count = 0;
                        while (rs.next()) {
                            count++;
                        }
                        return count;
                    });
            System.out.println("extractor=" + extracted);

            // 4) Template đóng PreparedStatement; callback đóng ResultSet
            //    do chính ps.executeQuery() mở ra.
            Integer statementCount = jdbc.execute(
                    "SELECT COUNT(*) FROM jobs WHERE id >= ?",
                    (PreparedStatementCallback<Integer>) ps -> {
                        ps.setLong(1, 2L);
                        try (ResultSet rs = ps.executeQuery()) {
                            rs.next();
                            return rs.getInt(1);
                        }
                    });
            System.out.println("statementCount=" + statementCount);

            // 5) ConnectionCallback mượn connection; callback tự đóng
            //    PreparedStatement/ResultSet mà nó tạo.
            Integer connectionCount = jdbc.execute(
                    (ConnectionCallback<Integer>) connection -> {
                        try (PreparedStatement ps = connection.prepareStatement(
                                     "SELECT COUNT(*) FROM jobs WHERE completed = TRUE");
                             ResultSet rs = ps.executeQuery()) {
                            rs.next();
                            return rs.getInt(1);
                        }
                    });
            System.out.println("connectionCount=" + connectionCount);

            // 6) Caller nhận Stream phải đóng, dù đã count xong.
            long streamCount;
            try (Stream<String> stream = jdbc.queryForStream(
                    "SELECT name FROM jobs ORDER BY id",
                    (rs, rowNum) -> rs.getString("name"))) {
                streamCount = stream.count();
            }
            System.out.println("streamCount=" + streamCount);

            // 7) Trong transaction, JdbcTemplate chỉ release connection;
            //    manager quyết định commit/rollback.
            try {
                tx.executeWithoutResult(status -> {
                    jdbc.execute((ConnectionCallback<Void>) connection -> {
                        try (PreparedStatement own = connection.prepareStatement(
                                "UPDATE jobs SET completed = TRUE WHERE id = 1")) {
                            own.executeUpdate();
                        }
                        return null;
                    });
                    throw new IllegalStateException("rollback example");
                });
            } catch (IllegalStateException expected) {
                // Chỉ bắt exception cố ý tạo ra trong bài demo.
            }

            Boolean completed = jdbc.queryForObject(
                    "SELECT completed FROM jobs WHERE id = ?",
                    Boolean.class, 1L);
            System.out.println("afterRollback=" + completed);
        }
    }
}
```

Tại thư mục có `build.gradle`, chạy:

```bash
gradle run
```

Nếu project có Gradle Wrapper, có thể dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows). Phần output do `System.out` tạo ra là:

```text
mapped=3
names=Thiết kế, Viết mã, Kiểm thử
extractor=3
statementCount=2
connectionCount=1
streamCount=3
afterRollback=false
```

Console có thể thêm log Gradle/Spring. **Vì sao các giá trị đó đúng?**

- Ba `INSERT` tạo ba job nên `mapped=3`. Kết quả order theo `id` tương ứng ba tên.
- `ResultSetExtractor` đếm ba dòng nên `extractor=3`.
- `PreparedStatementCallback` bind `id >= 2`, do đó đếm hai job.
- `ConnectionCallback` đếm job có `completed = TRUE`: chỉ job id 2, nên bằng 1.
- Stream duyệt ba dòng rồi được đóng, do đó `streamCount=3`.
- Trong transaction cuối, callback tạo và tự đóng statement, nhưng **không đóng connection** do template cấp. Sau khi callback trả về, `IllegalStateException` khiến transaction rollback; job id 1 vẫn `completed=false`.

**Điều có thể quan sát qua code:** nguồn đóng tài nguyên không dựa vào kiểu `AutoCloseable` đơn thuần mà dựa vào ownership: có `try-with-resources` cho ResultSet tự mở, statement tự tạo và stream được trả ra ngoài; không có `try-with-resources` bao connection/statement/template-managed result set được callback mượn.

### 12.2. Các biến thể để thử

1. **Phát hiện sai cursor:** đặt `rs.next()` trong `RowCallbackHandler`, quan sát số dòng xử lý bị thiếu hoặc lỗi. Sau đó khôi phục code đúng.
2. **Phát hiện thiếu cleanup:** bỏ `try-with-resources` cho `ResultSet` tự mở trong `PreparedStatementCallback`; dùng instrumented DataSource/pool leak metrics để quan sát tài nguyên theo thời gian, không chỉ dựa vào bài test ba dòng.
3. **Phát hiện resource escape:** trả `ResultSet` từ `ResultSetExtractor` rồi sử dụng ở caller; hiểu vì sao cursor đã hết lifetime.
4. **Stream đóng sớm:** thay `stream.count()` bằng `stream.findFirst()`; dù chỉ đọc một phần, vẫn phải đóng stream.
5. **Không đóng connection transaction:** thay callback tạo `PreparedStatement` bằng lệnh `JdbcTemplate.update(...)` bên trong cùng `TransactionTemplate`; kết quả rollback phải giữ nguyên.

## 13. Ownership khi có @Transactional hoặc TransactionTemplate

Giả sử một Spring service được intercept bởi `@Transactional` và truy cập database qua `JdbcTemplate`:

```text
Service method bắt đầu Spring transaction T1
    │
    ├─ JdbcTemplate.query(...)
    │    ├─ lấy connection T1 đang được bind
    │    ├─ tạo/đóng statement, result set
    │    └─ release handle, T1 vẫn giữ connection
    │
    ├─ JdbcTemplate.update(...)
    │    └─ dùng connection T1
    │
    └─ service thành công hoặc ném exception
           └─ transaction manager commit/rollback và giải phóng connection
```

`JdbcTemplate` giải phóng connection bằng hạ tầng `DataSourceUtils` có nhận biết transaction. Vì vậy, **đừng tự gọi `connection.commit()`/`rollback()` hay `connection.close()` trong callback** để “giải phóng sớm”; transaction manager đang là owner của transaction. Một số handle có thể là proxy và suppress close, nhưng không phải lý do để phá contract.

Nếu không có Spring transaction đang hoạt động, template vẫn lấy và trả connection đúng cách theo `DataSource`/pool, và từng statement có thể theo auto-commit của driver. **`JdbcTemplate` không tự mở một nghiệp vụ transaction nhiều bước chỉ vì bạn gọi liên tiếp nhiều method `update`**.

Khi callback ném runtime exception:

- `JdbcTemplate` dọn tài nguyên mà nó sở hữu trong đường xử lý lỗi.
- Nếu exception là `SQLException`, template thường chuyển đổi sang `DataAccessException`.
- Nếu có transaction phù hợp, Spring áp dụng rollback theo transaction rule của `TransactionTemplate` hoặc interceptor `@Transactional`; mặc định annotation thường rollback với unchecked exception.
- Nếu callback **bắt rồi nuốt** lỗi và trả về như thành công, transaction infrastructure có thể không biết cần rollback. Hãy thiết kế exception handling theo use case, hoặc đánh dấu rollback-only khi có chủ đích.

### Không giữ tài nguyên qua callback

`Connection`, `PreparedStatement` và `ResultSet` không nên được gán vào singleton field, cache hay đưa vào công việc async rồi sử dụng sau khi callback trả về. Khi đó:

- Statement/result set có thể đã bị đóng;
- Connection có thể đã trả về pool và được một request khác sử dụng;
- Transaction gắn theo luồng hiện tại có thể đã kết thúc;
- Code vô tình tạo race condition và lỗi chỉ xuất hiện dưới tải.

Hãy chuyển các cột cần thiết sang immutable DTO/record hoặc collection ngay trong callback. Nếu tập kết quả lớn, áp dụng paging, cursor/stream với lifetime chặt chẽ và try-with-resources, hoặc thiết kế xử lý lô phù hợp.

## 14. Những ngoại lệ và tình huống nâng cao

### 14.1. ResultSet do code tự mở bên trong StatementCallback

Theo Javadoc của các callback dạng `StatementCallback`/`PreparedStatementCallback`, Spring sẽ đóng statement **nhưng không bảo đảm việc đóng statement làm tất cả ResultSet đã mở được release hoàn toàn trong mọi pool/driver**. Vì vậy, ResultSet do callback mở phải được đóng trong `finally`/`try-with-resources`. Quy tắc này **khác** với `RowMapper`/`ResultSetExtractor` được truyền cho `JdbcTemplate.query`.

### 14.2. Statement tạo thêm ngoài statement của template

Nếu trong `ConnectionCallback` bạn gọi `connection.createStatement()` hoặc `prepareStatement()`, đó là statement do callback tạo: callback phải đóng nó. Nếu trong một `StatementCallback` bạn nhận statement A từ template nhưng sau đó dùng connection để tạo statement B, statement B cũng do bạn tạo và cần được đóng. Không trông chờ template quét mọi resource mà callback có thể tạo.

### 14.3. Stream, InputStream, Reader và LOB

Đừng nhầm Java Stream pipeline của `queryForStream` với `InputStream` để đọc BLOB hoặc `Reader` để đọc CLOB. Dữ liệu LOB lớn có thể được driver cung cấp qua stream phụ thuộc result set/connection. Khi dùng các API này:

- Đọc và đóng stream theo contract của API/driver trong lúc result set còn mở.
- Nếu cần dùng sau callback, cân nhắc lưu dữ liệu ra nơi có ownership và giới hạn rõ ràng hoặc chuyển thành `byte[]`/`String` khi kích thước cho phép.
- Không trả stream gắn cursor ra khỏi `RowMapper` và giả định nó sống độc lập.
- Kiểm tra cơ chế streaming, transaction và memory của driver mục tiêu, vì hành vi H2 trong memory không bảo đảm giống PostgreSQL/MySQL/Oracle.

### 14.4. BatchPreparedStatementSetter

Với `JdbcTemplate.batchUpdate` và `BatchPreparedStatementSetter`, Spring giữ statement; setter chỉ bind giá trị cho từng chỉ số và cung cấp kích thước batch. Không đóng statement hoặc tự gọi `executeBatch()` trong `setValues`; template sẽ điều khiển thực thi batch. Tài nguyên phụ do setter tạo vẫn cần được dọn theo vòng đời của chúng.

### 14.5. Không dùng connection chung giữa thread

Callback nhận connection được tạo/bind cho lời gọi JDBC hiện tại. Đừng lưu rồi sử dụng nó từ `CompletableFuture`, `@Async` hoặc thread khác: đa số JDBC connection không được thiết kế cho chia sẻ tùy tiện, và Spring JDBC transaction đồng bộ thường gắn với thread. Mở transaction/ràng buộc data access theo execution context đúng.

## 15. Các lỗi thường gặp và cách tự chẩn đoán

| Triệu chứng | Nguyên nhân về ownership | Cách kiểm tra/sửa |
| --- | --- | --- |
| `ResultSet closed` hoặc bị thiếu dòng | Callback gọi `rs.close()`/`next()` sai contract | Kiểm tra callback loại gì; bỏ close/next trong mapper/handler |
| `Statement closed` | Callback đóng statement do template cấp | Chỉ đóng statement do callback tự tạo |
| Connection không dùng được ở thao tác tiếp theo | Callback đóng/giữ sai connection hoặc thay đổi state | Không quản lý lifecycle connection do template cấp |
| Pool cạn sau nhiều lần `queryForStream` | Caller không `close()` stream | Dùng `try-with-resources` quanh stream |
| Leak cursor khi dùng `execute(PreparedStatementCallback)` | Callback không đóng ResultSet tự mở | Đóng result set trong callback |
| Kết quả mapping sai/lặp | `RowMapper` hoặc handler tự di chuyển cursor | Chỉ đọc dòng hiện tại, dùng extractor nếu phải tự duyệt |
| Dữ liệu chỉ được ghi một phần | Không có transaction bao trùm hoặc lỗi bị nuốt | Kiểm tra ranh giới transaction, rollback integration test |
| `SQLException` biến mất, caller tưởng thành công | Callback tự bắt rồi bỏ qua lỗi | Để Spring dịch lỗi hoặc xử lý/đánh dấu rollback rõ ràng |
| Lỗi bất thường khi xử lý async | Giữ ResultSet/Connection sau callback hoặc qua thread | Materialize dữ liệu; mở tài nguyên theo task |
| Heap tăng cao khi đọc bảng lớn | Callback tích lũy toàn bộ dữ liệu không giới hạn | Paging, streaming có đóng stream, xử lý lô |
| Leak xảy ra dù đã đóng statement | ResultSet tự mở bị bỏ sót, driver/pool có pooling | Kiểm tra nơi thực sự tạo result set và dùng explicit close |

**Quy trình chẩn đoán:** xác định API được gọi (`query` hay `execute` hay `queryForStream`) → ghi rõ callback loại gì → vẽ ai tạo từng resource → xem `try-with-resources` nằm đúng layer chưa → test cả đường thành công, exception và early exit → quan sát pool/driver resource metrics nếu có.

## 16. Checklist review code theo ownership

Khi review một callback JDBC, hãy tự hỏi lần lượt:

1. Tôi đang dùng overload `JdbcTemplate` nào? Nó truyền cho callback `ResultSet`, `Statement`, `PreparedStatement` hay `Connection`?
2. Template đã mở resource này, hay callback tự gọi `executeQuery()`/`prepareStatement()` để tạo nó?
3. Nếu callback tự tạo resource, tôi đã đặt `try-with-resources` quanh nó chưa?
4. Nếu template cấp resource, có dòng `close()`/`commit()`/`rollback()` hoặc thay đổi state trái contract không?
5. Ai điều khiển `rs.next()`: `JdbcTemplate` (RowMapper/RowCallbackHandler) hay callback (ResultSetExtractor)?
6. Callback có trả JDBC cursor, statement, connection, LOB stream hoặc object còn phụ thuộc resource đã đóng ra ngoài không?
7. Nếu trả `Stream<T>` của `queryForStream`, caller có biết trách nhiệm đóng và có thử đường short-circuit/exception không?
8. Callback có giữ mutable state dùng chung giữa nhiều thread hay chạy async với handle mượn không?
9. Khi gặp `SQLException`, có để template dịch lỗi không; khi gặp runtime exception, transaction có rollback theo ý định không?
10. Tôi đã chạy integration test trên driver/database gần production cho đường có cursor, stream, pool hoặc transaction quan trọng chưa?

**Mức đạt:** bạn không chỉ viết được câu `jdbcTemplate.query(...)` mà còn giải thích chính xác tại sao một `ResultSet` trong `ResultSetExtractor` thì không đóng, trong `PreparedStatementCallback` lại phải đóng, và tại sao `queryForStream` cần caller gọi `close()`.

## 17. Nguồn tham khảo

- Spring Framework 6.2, **Data Access with JDBC** (bảng trách nhiệm giữa Spring và ứng dụng): https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc.html
- Spring Framework 6.2, **Using the JDBC Core Classes**: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html
- Spring Framework Javadoc, **JdbcTemplate**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework Javadoc, **PreparedStatementCallback**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/PreparedStatementCallback.html
- Spring Framework Javadoc, **StatementCallback**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/StatementCallback.html
- Spring Framework Javadoc, **RowCallbackHandler**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/RowCallbackHandler.html
- Spring Framework Javadoc, **DataSourceUtils**: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html

Hãy đọc contract của đúng overload và phiên bản đang dùng. Ownership của tài nguyên chỉ rõ ràng khi biết **ai tạo, ai mượn, ai đóng và khi nào phạm vi callback kết thúc**.