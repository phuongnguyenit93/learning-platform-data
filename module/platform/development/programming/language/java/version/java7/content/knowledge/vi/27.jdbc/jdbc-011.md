# JDBC: Kiểm thử lỗi truy vấn, lỗi giao dịch và lỗi đóng trong Java

## 1. Vì sao chỉ kiểm thử đường thành công là chưa đủ?

Một repository Java có thể chạy tốt khi database khỏe, truy vấn trả dữ liệu đúng và mọi lệnh `close()` hoàn tất. Nhưng hệ thống thật thường gặp lỗi ở **nhiều thời điểm khác nhau**:

- Pool không cấp được `Connection`.
- Driver không chuẩn bị được câu lệnh qua `prepareStatement()`.
- Gọi `executeQuery()` hoặc `executeUpdate()` ném `SQLException`.
- Kết quả đã tạo nhưng `ResultSet.next()` hay `getString()` lỗi trong lúc đọc.
- Một thao tác cập nhật thành công một phần rồi câu lệnh tiếp theo thất bại.
- `commit()` thất bại, nên kết quả giao dịch có thể **không rõ** đối với ứng dụng.
- Ứng dụng cố `rollback()` nhưng thao tác rollback tiếp tục thất bại.
- `ResultSet.close()`, `PreparedStatement.close()` hoặc `Connection.close()` ném lỗi ngay khi xử lý chính đã hoàn thành hoặc đã thất bại.

Nếu chỉ viết test kiểu “mock `executeQuery()` trả một `ResultSet`, assert dữ liệu đúng”, bạn chưa kiểm chứng đường dọn tài nguyên, thứ tự thao tác transaction, cách giữ ngoại lệ gốc hay điều gì xảy ra nếu lỗi xuất hiện sau khi database đã nhận một lệnh.

Bài này tập trung vào chủ đề **“Kiểm thử lỗi truy vấn, lỗi giao dịch và lỗi đóng”** thuộc mục **JDBC**. Trọng tâm là **thiết kế failure injection, assertion theo từng nhánh và phân biệt unit test với integration test**. Các API sử dụng là API vẫn áp dụng trong Java hiện đại: JDBC `Connection`, `PreparedStatement`, `ResultSet`, `SQLException`, `DataSource`, `try-with-resources` (Java 7+) và `Throwable.getSuppressed()`. Chương trình minh họa **đã biên dịch và chạy bằng Java 17**.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Vẽ toàn bộ các **điểm phát sinh lỗi** trong một lời gọi JDBC.
2. Lập **ma trận fault injection** thay vì chỉ một test chung chung ném `SQLException`.
3. Xác minh exception chính (**primary**) và những exception phụ từ `close` hay `rollback` (**suppressed**).
4. Phân biệt lỗi đọc query với lỗi transaction và lỗi cleanup.
5. Kiểm tra `commit` chỉ được gọi khi các bước trước đó hoàn thành; `rollback` được thử khi transaction thất bại theo policy.
6. Hiểu vì sao **commit exception không đồng nghĩa chắc chắn chưa commit**, nên không tự động retry mọi giao dịch.
7. Giữ đúng ownership/lifetime của `Connection`, `Statement`, `ResultSet` khi cả khởi tạo lẫn đóng đều có thể lỗi.
8. Viết test double JDBC thuần Java để kiểm tra control flow và thử nghiệm thêm với **database/driver thực**.
9. Đặt các assertion bền vững: close order, primary error, suppressed error, state DB, idempotency và trạng thái pool.
10. Tránh phụ thuộc behavior driver chưa được cam kết hoặc API cũ không còn phù hợp.

## 2. Mô hình lỗi và ranh giới trách nhiệm

Hãy xem một truy vấn đọc:

```text
DataSource / pool
      |
      | getConnection()              <-- có thể lỗi
      v
Connection
      |
      | prepareStatement(sql)        <-- có thể lỗi
      v
PreparedStatement
      |
      | setParameter(...)            <-- có thể lỗi
      | executeQuery()               <-- có thể lỗi
      v
ResultSet
      |
      | next(), getXXX(...)          <-- có thể lỗi giữa chừng
      v
DTO / dữ liệu ứng dụng

Dọn dẹp (thứ tự ngược):
ResultSet.close() --> PreparedStatement.close() --> Connection.close()
       ^                      ^                       ^
       |                      |                       |
       lỗi close có thể xảy ra ở bất kỳ bước nào
```

Với giao dịch ghi, thêm:

```text
Connection.setAutoCommit(false)
       |
       v
executeUpdate()/executeBatch()/các câu lệnh SQL
       |
       +--> thành công --> commit()
       |
       +--> lỗi --------> rollback() best effort
       |
       v
Close statements và logical connection
```

**Ba lớp cần kiểm chứng riêng:**

- **Hợp đồng ngôn ngữ Java:** try-with-resources đóng resource theo thứ tự ngược, giữ primary exception, gắn close failure vào `getSuppressed()`.
- **Hợp đồng JDBC:** các phương thức có thể ném `SQLException`; connection có transaction state, commit/rollback, close, SQLState/vendor error codes.
- **Hợp đồng nghiệp vụ:** khi nào retry, khi nào hủy, có cần idempotency, nếu commit outcome không rõ thì xử lý ra sao, ai chịu trách nhiệm dọn tài nguyên.

Test double có thể chứng minh lớp thứ nhất và một phần cách code gọi lớp thứ hai. **Chỉ database/driver thực mới kiểm chứng được hiệu ứng SQL/transaction thực**.

## 3. Ma trận lỗi cần bao phủ

Một ma trận test hiệu quả đặt tên điểm lỗi và outcome kỳ vọng ngay từ đầu:

| Điểm chèn lỗi | Tác động trực tiếp | Điều cần assert | Không nên suy |
| --- | --- | --- | --- |
| `getConnection` | Chưa có Connection được cấp | Error propagate; không cố close object chưa nhận | “Pool đã bị leak” nếu chưa nhận connection |
| `prepareStatement` | Có connection, chưa có statement hợp lệ | Connection được đóng; lỗi prepare primary | Statement chưa tạo vẫn có `close` |
| `setXxx` | Bind parameter thất bại | Statement/connection đóng; không execute query | SQL đã chạy |
| `executeQuery` | Không nhận được result set | Statement/connection đóng; lỗi query primary | ResultSet tồn tại để close |
| `ResultSet.next/getXxx` | Lỗi khi duyệt/map kết quả | Đóng RS → Statement → Connection; lỗi đọc primary | Đã đọc một số row nghĩa query thành công toàn phần |
| `executeUpdate` | Lỗi trong transaction | Thử rollback; không commit trong nhánh thất bại | Statement lỗi nghĩa DB chắc chắn không đổi |
| `commit` | Xác nhận giao dịch lỗi | Ghi outcome không rõ, policy retry thận trọng; thử rollback khi hợp lệ | Chắc chắn DB đã rollback/chưa commit |
| `rollback` | Không hoàn tác được theo kỳ vọng | Giữ lỗi gốc, bổ sung rollback failure | Transaction chắc chắn đã được phục hồi |
| `ResultSet.close` | Lỗi cleanup sau hoặc cùng body | Primary nếu không có lỗi trước; suppressed nếu body đã lỗi | Query phải được chạy lại |
| `Statement.close` | Lỗi cleanup | Những resource còn lại vẫn được thử đóng | Statement close luôn đồng nghĩa Connection close |
| `Connection.close` | Lỗi trả/giải phóng resource | Exception được quan sát; báo telemetry/kiểm tra pool | Physical connection chắc chắn bị đóng hay trả lại thành công |

**Một lỗi có thể kích hoạt các lỗi khác.** Ví dụ `executeQuery` ném `SQLException`, rồi cả `PreparedStatement.close` và `Connection.close` cũng ném. Test phải xác nhận điều gì là **primary** và điều gì được giữ lại như **suppressed**.

### 3.1. Không gom mọi trường hợp vào assert “throws SQLException”

Bài test như sau chưa đủ:

```java
assertThrows(SQLException.class, repository::load);
```

Đây là cú pháp minh họa của một framework unit test có `assertThrows`, không thuộc JDK tiêu chuẩn. Nếu không kiểm tra message/type/phase/event sequence, test có thể PASS do **một lỗi hoàn toàn khác** (chẳng hạn lỗi close connection) và che mất lỗi executeQuery mà bạn định kiểm chứng.

Một assertion tốt hơn sẽ nêu:

- Lỗi được inject ở **executeQuery** hay **ResultSet.next**?
- **Primary exception** là object/message/SQLState dự kiến?
- `ResultSet` đã được tạo hay chưa?
- Những resource nào đã tạo thành công đã được đóng hoặc **được thử đóng**?
- `getSuppressed()` chứa những lỗi cleanup nào theo **thứ tự**?
- Trường hợp transaction có `commit/rollback` được gọi đúng không?
- Trạng thái nghiệp vụ/DB cuối cùng đã được xác minh ở đâu?

## 4. SQLException và cấu trúc lỗi

`SQLException` chứa thông tin chẩn đoán quan trọng:

- `getMessage()`: mô tả lỗi, có thể phụ thuộc driver.
- `getSQLState()`: mã SQLState nếu driver cung cấp.
- `getErrorCode()`: mã lỗi vendor nếu có.
- `getCause()`: nguyên nhân Java thường.
- `getNextException()`: chuỗi exception bổ sung theo JDBC.
- `getSuppressed()`: lỗi phụ do try-with-resources hoặc code tự gắn.

**`getNextException()` và `getSuppressed()` là hai cơ chế khác nhau.**

### 4.1. Primary và suppressed của try-with-resources

Ví dụ:

```java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    throw new SQLException("read failure");
}
```

Đây là mã minh họa trong phương thức có `throws SQLException`, với các biến đã khai báo; phần thân cố tình ném lỗi. Nếu cả ba lời gọi `close` còn ném lỗi, thứ tự gần với:

```text
Primary: SQLException("read failure")
Suppressed:
  SQLException("close ResultSet")
  SQLException("close PreparedStatement")
  SQLException("close Connection")
```

Đây là **minh họa với từng close đều ném đúng lỗi giả lập**, không phải message mà JDBC driver nào cũng tạo. Java khởi tạo resource **trái sang phải**, đóng **phải sang trái** và **tiếp tục thử đóng** các resource còn lại dù một bước close ném lỗi.

### 4.2. Nếu body thành công nhưng close thất bại

Nếu SQL và mapping thành công nhưng `ResultSet.close()` ném lỗi, thì **close exception trở thành primary**. Nếu close statement và connection tiếp tục lỗi, chúng thường trở thành suppressed của lỗi close đầu tiên.

Do đó một test đúng phải tách:

1. **Body failure**: primary đến từ SQL/mapping; close failures suppressed.
2. **Close-only failure**: primary đến từ resource close đầu tiên thất bại; các close lỗi sau suppressed.
3. **Không có lỗi**: không có exception; mọi resource đóng thành công.
4. **Resource initializer failure**: primary đến từ lời gọi tạo resource; những resource **đã tạo thành công trước đó** vẫn được đóng.

### 4.3. Lỗi rollback do code thêm vào

Try-with-resources tự gắn lỗi của `close`, nhưng **không tự gắn lỗi `rollback` vào lỗi SQL đang xử lý**, vì rollback là phương thức do ứng dụng gọi, không phải resource close tự động.

Mẫu thường dùng:

```java
catch (SQLException | RuntimeException original) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        original.addSuppressed(rollbackFailure);
    }
    throw original;
}
```

Đây là đoạn minh họa trong scope có `connection` và transaction đang active, phải được đặt ở nơi caller thực sự sở hữu giao dịch. Nó giữ nguyên original exception để chẩn đoán lý do đầu tiên, đồng thời không che mất thông tin rollback cũng lỗi.

**Đừng tự gắn cùng một Throwable làm suppressed của chính nó**, vì Java sẽ từ chối self-suppression; mỗi lỗi khác nhau cần object riêng và policy rõ.

### 4.4. Bắt lỗi gì?

Trong repository thông thường, `SQLException` là trọng tâm. Nhưng mapping logic có thể ném `RuntimeException`; nếu transaction đã bắt đầu và code tự sở hữu nó, thường cũng cần rollback đối với failure runtime.

Không nên nuốt mọi `Throwable` rồi tiếp tục như bình thường. `Error` thường biểu thị vấn đề nghiêm trọng của JVM; policy handling phải được quyết định ở tầng ứng dụng. Try-with-resources vẫn cố dọn tài nguyên trong quá trình stack unwinding, nhưng **không tự gọi rollback** chỉ vì có `Error`.

## 5. Thiết kế mã dễ kiểm thử: tách nguồn Connection

Thay vì khởi tạo kết nối sâu trong method bằng hard-coded URL, nên inject `DataSource` hoặc một abstraction nhẹ.

Ví dụ:

```java
@FunctionalInterface
interface ConnectionSource {
    Connection open() throws SQLException;
}
```

Đây là interface minh họa cần import `java.sql.Connection` và `java.sql.SQLException`.

Trong ứng dụng có database thật:

```java
ConnectionSource source = dataSource::getConnection;
```

Với unit test:

```java
ConnectionSource source = fakeSession::open;
```

Hai đoạn là minh họa với `dataSource` và `fakeSession` đã định nghĩa. Điểm quan trọng là code repository **không cần biết** connection tới thật hay một test double: nó luôn gọi cùng API, còn test double có thể **chủ động ném lỗi ở đúng điểm** mà test muốn kiểm tra.

### 5.1. Ưu tiên DataSource thực trong production

`javax.sql.DataSource` vẫn là abstraction JDBC hiện hành và thường tương tác với connection pool. Interface `ConnectionSource` chỉ là lớp mỏng phục vụ demo/test. Trong dự án thật, constructor repository nhận `DataSource` là cách rất phổ biến.

Không cần thêm một hierarchy phức tạp chỉ để mock một lời gọi `getConnection`; mục tiêu là **tạo ranh giới dễ thay thế** mà không phụ thuộc credential hay network trong unit test.

### 5.2. Ownership phải được ghi rõ

Nếu repository tự gọi `dataSource.getConnection()`, repository thường **sở hữu** logical connection và phải đóng qua try-with-resources. Nếu framework/transaction manager đưa vào một connection **đã nằm trong một giao dịch của caller**, repository **không được tự ý close** connection đó nếu hợp đồng không trao ownership.

Test phải phản ánh ownership thật. Một assertion “close Connection một lần” có thể **sai** với code chạy trong một transaction scope do framework quản lý, dù nó đúng với ví dụ repository tự mượn connection.

## 6. Kiểm thử lỗi truy vấn đọc

Một method query có scope đúng:

```java
static String findName(ConnectionSource source) throws SQLException {
    try (Connection c = source.open();
         PreparedStatement ps =
                 c.prepareStatement("SELECT name FROM users WHERE id = ?")) {
        ps.setLong(1, 7L);
        try (ResultSet rs = ps.executeQuery()) {
            return rs.next() ? rs.getString("name") : "NONE";
        }
    }
}
```

Đây là method Java đầy đủ nhưng cần interface `ConnectionSource`/imports trong cùng file. Code này được dùng nguyên trong chương trình kiểm thử cuối bài.

### 6.1. Trường hợp thành công

Test double trả:

- `prepareStatement(...)` → PreparedStatement.
- `setLong(1,7)` → không lỗi.
- `executeQuery()` → ResultSet.
- `next()` → true ở row đầu.
- `getString("name")` → "Ada".

Kỳ vọng kết quả `"Ada"` và thứ tự đóng:

```text
close:ResultSet
close:PreparedStatement
close:Connection
```

**Không cần** tạo một database thật chỉ để xác minh Java gọi close theo thứ tự nào. Nhưng test double không chứng minh SQL trong DB thực sẽ trả "Ada" — đó là mục tiêu của integration test.

### 6.2. Lỗi ngay tại executeQuery

Nếu `ps.executeQuery()` ném `SQLException("query failure")`:

- **Không có ResultSet được tạo thành công**, nên không kỳ vọng `ResultSet.close()`.
- `PreparedStatement` đã tạo thành công nên được thử đóng.
- `Connection` đã tạo thành công nên được thử đóng.
- `query failure` là primary.
- Nếu close statement/connection cũng lỗi, chúng thành suppressed.

**Test đúng phải kiểm tra chính xác rằng không có close ResultSet trước khi ResultSet được khởi tạo.**

### 6.3. Lỗi khi đọc ResultSet

`executeQuery()` đã trả `ResultSet` nhưng `rs.next()` ném `SQLException("read failure")`:

- `ResultSet` là resource đã tạo thành công, cần thử đóng.
- Statement và Connection cũng cần được thử đóng.
- `read failure` là primary nếu close errors xuất hiện sau đó.
- Khi một số row đã đọc rồi mới lỗi, **không tự trả một kết quả business “thành công một phần”** trừ khi hợp đồng cho phép và có thông báo trạng thái phù hợp.

Với báo cáo/aggregation, chỉ công bố kết quả sau khi toàn bộ dữ liệu cần thiết đã đọc và xử lý thành công; nếu không, một lỗi giữa chừng có thể bị xem nhầm là “không có dữ liệu”.

### 6.4. Không nhầm “0 row” với lỗi

`rs.next()==false` là **một kết quả hợp lệ**, không phải exception. Test nên có case riêng cho empty result set, nhất là với repository trả `Optional.empty()` hoặc empty list.

Đừng tự throw SQLException chỉ vì query không trả row nếu domain cho phép không tìm thấy; lỗi business “not found” và lỗi database connection là hai tầng khác nhau.

### 6.5. Lỗi đọc column và mapping

Các phương thức `rs.getString`, `getLong`, `getObject` có thể ném `SQLException` khi dữ liệu/column/driver có vấn đề. Mapping cũng có thể ném runtime exception khi chuyển kiểu.

Test ít nhất:

- `next()` thành công, `getXxx()` thất bại.
- Column SQL `NULL` được xử lý theo hợp đồng (primitive getter và `wasNull()` khi cần).
- Mapping exception không làm rò resource.
- Nếu repository map ResultSet thành DTO, **không trả lazy stream** đang phụ thuộc một cursor đã đóng.

## 7. Kiểm thử giao dịch: commit, rollback và lỗi commit

### 7.1. Transaction boundary nên tường minh

Với `autoCommit=false`, ứng dụng phải quyết định:

- Khi nào transaction **bắt đầu**.
- Những câu lệnh nào thuộc transaction.
- Điều kiện nghiệp vụ để **commit**.
- Những exception nào khiến **rollback**.
- Cách giữ lại rollback failure để không che mất lỗi gốc.
- Ai đóng Connection và khi nào.
- Nếu commit thất bại mà kết quả DB không rõ thì hệ thống sẽ **đối soát hoặc xử lý idempotency** thế nào.

Mẫu dùng trong demo:

```java
static void updateStatus(ConnectionSource source) throws SQLException {
    try (Connection c = source.open()) {
        c.setAutoCommit(false);
        try {
            try (PreparedStatement ps = c.prepareStatement(
                    "UPDATE users SET active = ? WHERE id = ?")) {
                ps.setBoolean(1, true);
                ps.setLong(2, 7L);
                if (ps.executeUpdate() != 1) {
                    throw new SQLException("unexpected row count");
                }
            }
            c.commit();
        } catch (SQLException | RuntimeException failure) {
            try {
                c.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        }
    }
}
```

Đây là method Java đầy đủ với interface `ConnectionSource` và imports. Nó dùng một connection được method sở hữu; không áp dụng nguyên xi khi framework quản lý transaction hộ. Ví dụ cố ý đơn giản để test thứ tự, **không phải** mã production xử lý mọi failure mode, retry, commit ambiguity hoặc distributed transaction.

### 7.2. Thành công: update rồi commit rồi close

Nếu `executeUpdate()==1` và statement close thành công:

```text
open
autoCommit=false
prepare
update
close:PreparedStatement
commit
close:Connection
```

Thứ tự là quan trọng: statement đã được đóng sau khi thực thi, rồi method gọi `commit`, cuối cùng connection đóng.

Test assert:

- Có `setAutoCommit(false)`.
- Có `executeUpdate`.
- Có `commit`.
- **Không gọi rollback** ở nhánh thành công.
- Connection đóng đúng một lần theo ownership của method.
- Không dùng biến “query returned 1” làm bằng chứng database thực đã commit: unit test chỉ xác minh **lời gọi**.

### 7.3. Lỗi executeUpdate: rollback được thử

Nếu `executeUpdate()` ném `SQLException("update failure")`, code:

1. Thoát try-with-resources của PreparedStatement, thử đóng statement.
2. Đi vào catch của transaction.
3. Thử `rollback()`.
4. Ném lại **chính lỗi update**.
5. Thoát try-with-resources ngoài, thử đóng connection.

Test phải xác minh **không commit** khi update thất bại. Nếu rollback thành công thì cũng chỉ biết lời gọi rollback của test double hoàn tất, không biết database thật đã rollback những thay đổi nào; integration test cần kiểm tra persisted state.

### 7.4. Nếu Statement.close thất bại trước commit

Một chi tiết dễ bị bỏ sót: statement close xảy ra ở cuối khối `try (PreparedStatement ps...)`, **trước `c.commit()`**. Nếu close statement ném `SQLException`, execution rời khối theo exception và đi vào catch của transaction: **commit có thể không được gọi**, rollback được thử.

Đây là lựa chọn của **cấu trúc mã**: nếu ứng dụng muốn tách trạng thái “SQL đã thực thi thành công” khỏi “cleanup statement thành công”, cần policy rõ và test từng trường hợp. Không mặc định close statement failure lúc nào cũng nên được bỏ qua để commit; cũng không mặc định nó có nghĩa SQL đã thất bại.

### 7.5. Commit ném exception không chứng minh rollback thực sự xảy ra

Đây là vấn đề quan trọng nhất khi kiểm thử giao dịch với database thật.

Nếu `c.commit()` ném `SQLException` do mất kết nối/timeout:

- **Ứng dụng có thể không biết** database đã nhận/commit lệnh trước khi kết nối đứt hay chưa.
- Việc thử `rollback()` sau lỗi commit là một hành động phục hồi best effort, **không khẳng định rollback chắc chắn có hiệu lực** nếu transaction đã được commit hoặc connection không còn dùng được.
- Không tự động retry một lệnh ghi **không idempotent** vì điều đó có thể thực hiện tác dụng phụ hai lần.
- Cần transaction ID/business request ID, idempotency key, unique constraints, operation status lookup hoặc reconciliation tùy hệ thống.

Một unit test dùng mock luôn ném `SQLException("commit failure")` chỉ chứng minh code xử lý exception, **không xác lập commit outcome trên server**.

### 7.6. Nếu rollback cũng ném lỗi

Giả sử primary là `commit failure`, rollback ném `rollback failure` và Connection.close ném `close Connection`:

```text
Primary: commit failure
Suppressed #1: rollback failure   (do code gọi addSuppressed)
Suppressed #2: close Connection   (do try-with-resources)
```

Trong ví dụ đã kiểm thử, thứ tự này được assert chính xác. Nó phản ánh đường control flow và thời điểm lỗi, không nên diễn giải `rollback failure` là một cause thay thế lỗi commit.

### 7.7. Nếu update, statement.close, rollback và connection.close đều lỗi

Kịch bản kép:

```text
executeUpdate() -> "update failure"      PRIMARY
PreparedStatement.close() -> "close PreparedStatement"
rollback() -> "rollback failure"
Connection.close() -> "close Connection"
```

Kết quả trên **cấu trúc try/catch của ví dụ**:

```text
Primary: update failure
Suppressed (đúng thứ tự):
  close PreparedStatement
  rollback failure
  close Connection
```

Điều này xảy ra vì close statement được Java tự gắn suppressed ngay khi rời try-with-resources bên trong; rollback failure được code tự `addSuppressed` trong catch; cuối cùng close connection được TWR ngoài gắn vào khi exception tiếp tục propagate.

**Không bắt buộc mọi repository có cùng thứ tự nếu bố trí nested try/catch khác nhau**. Điều đúng cần assert là expected control flow của **mã đang kiểm thử**, không một công thức cứng cho tất cả chương trình JDBC.

### 7.8. Lỗi setAutoCommit(false) cần một case riêng

Trong method ví dụ, `c.setAutoCommit(false)` nằm **trước** khối try/catch quản lý transaction. Nếu nó ném `SQLException`, connection đã được TWR outer quản lý nên **vẫn được thử đóng**, nhưng mã **không gọi rollback** trong catch phía dưới vì chưa vào khối đó.

Không nói “mọi lỗi JDBC chắc chắn gọi rollback”; chỉ những lỗi thuộc **phạm vi catch đã thiết kế** mới làm vậy. Production có thể cần xác định trạng thái transaction khi thay đổi auto-commit thất bại và quyết định cách xử lý theo driver/provider.

### 7.9. Nếu rollback lỗi, có nên thử commit?

**Không.** Rollback failure không phải tín hiệu “thử commit để kết thúc transaction”. Khi trạng thái transaction không còn chắc chắn, ứng dụng phải xử lý lỗi, không tự xác nhận một tập thay đổi chưa hoàn chỉnh. Phương án cụ thể phụ thuộc loại DB, connection health và transaction manager.

## 8. Khi lỗi đóng Connection: hành vi nào cần kiểm thử?

`Connection.close()` được gọi bởi TWR khi scope connection kết thúc. Theo JDBC, nếu transaction còn active mà `close()` được gọi, kết quả **implementation-defined**: ứng dụng nên **commit hoặc rollback tường minh trước close**.

Vì thế có hai nhóm test:

**Unit test** — verify code cố close connection theo ownership, các lỗi close không che primary, pool-return behavior được gọi đúng qua abstraction.

**Integration test** — verify trạng thái database và pool khi connection đóng giữa transaction; behavior driver cụ thể không được suy từ một dynamic proxy.

### 8.1. Pooled Connection là logical wrapper

Trong dịch vụ có connection pool, `close()` thường **trả logical connection về pool**, không đóng physical socket ngay. Test nên theo dõi:

- Slot được trả sau success/exception.
- Không giữ connection borrowed sau method return.
- Transaction state được reset/rollback theo provider policy đã cấu hình.
- Pool không bị cạn sau nhiều failures.
- Lỗi close được báo để pool loại bỏ connection hỏng nếu provider có cơ chế đó.

**Không assert mọi close tạo đúng một sự kiện TCP disconnect**, trừ khi bạn cố tình kiểm thử một provider và mode cụ thể.

### 8.2. Không double-close chỉ để sửa lỗi

Với try-with-resources, Java đã thử close. Nếu `close` ném exception, **không nên gọi lại close ngay một cách mù quáng**: bạn có thể làm sai semantics của một pooled wrapper hoặc che mất lỗi. Hãy để owner/provider quản lý resource bị hỏng, ghi telemetry và test đúng contract.

### 8.3. Close không đồng nghĩa commit

Nếu SQL update thành công nhưng ứng dụng chưa commit, TWR không tự quyết định business transaction. Dựa vào close để rollback/commit là không portable. Test phải quan sát explicit `commit`/`rollback` và kiểm tra state DB thật khi cần.

## 9. Các tầng kiểm thử nên phối hợp

### 9.1. Unit test: fault injection bằng test doubles

Mục tiêu là control flow:

- Mock `ConnectionSource.open` có thể ném đúng lúc.
- `prepareStatement` có thể ném.
- `executeQuery` có thể ném trước khi ResultSet được tạo.
- `ResultSet.next` hoặc `getXxx` có thể ném sau khi ResultSet đã tạo.
- `executeUpdate` có thể ném hoặc trả row count bất thường.
- `commit` và `rollback` có thể ném riêng hoặc cùng lúc.
- `close` của từng resource có thể ném và lưu thứ tự gọi.

**Điểm mạnh:** chạy nhanh, deterministic, không cần network, tạo được các lỗi hiếm gặp mà DB thật khó ép đúng thời điểm.

**Giới hạn:** không chứng minh SQL syntax, isolation, khóa, triggers, network failure, durability hoặc chính sách rollback/commit thực của DB.

### 9.2. Integration test: database thật và rollback state

Một integration test tốt có thể:

1. Mở transaction trong **database cô lập cho test**.
2. Insert hoặc update dữ liệu test có unique ID.
3. Gây lỗi SQL có chủ đích ở một statement sau khi statement trước đó đã thành công.
4. Yêu cầu repository rollback.
5. Mở **connection khác** và assert dữ liệu **không được commit**.
6. Đo connection pool checkout/checkin trước và sau test.
7. Dọn dữ liệu test và tránh chia sẻ trạng thái giữa test cases.

Đừng dùng test DB production. Dùng test schema riêng hoặc containerized DB phù hợp. Nếu dùng H2/SQLite nhưng production là PostgreSQL/MySQL/Oracle, hiểu rằng transaction isolation, kiểu dữ liệu, DDL auto-commit, SQL dialect và lỗi mạng có thể khác; cần test bổ sung với DB/driver thật khi yêu cầu quan trọng.

### 9.3. Test transaction commit failure bằng fault injection có kiểm soát

Đây là một bài integration khó: cần có network proxy/fault injection hoặc server-side fault phù hợp để mô phỏng mất kết nối đúng lúc commit.

Có thể không xác định được phía server đã commit hay chưa. Điều cần kiểm chứng là ứng dụng **không tự báo chắc chắn thất bại chưa ghi**, không retry bừa, và có cơ chế **reconciliation/idempotency**.

Không làm ngắt mạng trên môi trường sản xuất để kiểm thử.

### 9.4. Contract test qua driver, DataSource và pool

Nếu dùng connection pool hoặc transaction manager:

- Kiểm tra wrapper Connection có bị trả lại pool sau exception không.
- Kiểm tra stale connections được loại khỏi pool theo cấu hình khi lỗi fatal.
- Kiểm tra auto-commit, read-only, isolation và schema có được reset theo contract provider khi trả connection.
- Nếu code sở hữu transaction, kiểm tra commit/rollback.
- Nếu **framework sở hữu transaction**, dùng transaction testing facilities của framework thay vì tự close connection do framework cấp.

Mục tiêu không phải assert mọi driver giống nhau ở chi tiết nội bộ, mà là **ứng dụng giữ đúng các invariant do sản phẩm cần**.

### 9.5. Load test và so sánh metrics

Một hệ thống có thể PASS unit test nhưng leak connection ở callback/lazy streaming hoặc một branch hiếm. Đo:

- Active/idle/pending pool connections.
- Checkout duration, connect timeout và connection acquisition errors.
- SQL errors theo operation, SQLState và vendor code.
- Commit success/failure, rollback attempts/failure.
- Resource close exceptions.
- Request success/error/timeout/retry rate.
- Chênh lệch số connection acquired/released sau một test run đã quiescent.

Không xem một lần pool active count dao động là bằng chứng leak, bởi worker khác có thể đang sử dụng connection. Cần test environment và ranh giới đo ổn định.

## 10. Chương trình Java 17+ đã biên dịch và chạy thành công

File **`JdbcFailureTestingDemo.java`** dưới đây là **chương trình độc lập**, không cần database, JDBC driver ngoài hoặc thư viện test bên thứ ba.

Nó dùng `java.lang.reflect.Proxy` để triển khai **những method JDBC mà chính chương trình gọi**. Một `Session` giữ tập `Fault` để chủ động ném `SQLException` ở các điểm:

`OPEN`, `PREPARE`, `EXECUTE_QUERY`, `READ_ROW`, `EXECUTE_UPDATE`, `COMMIT`, `ROLLBACK`, `CLOSE_RESULT`, `CLOSE_STATEMENT`, `CLOSE_CONNECTION`.

Bộ test kiểm tra **mười tình huống**:

1. Query thành công, close order đúng.
2. `executeQuery` thất bại, sau đó statement/connection close đều lỗi.
3. `ResultSet.next` thất bại, cả ba close đều lỗi.
4. Body thành công nhưng ba lần close đều lỗi.
5. `prepareStatement` thất bại sau khi connection đã được tạo.
6. Transaction update thành công, commit xảy ra trước close connection.
7. `executeUpdate` lỗi → rollback, không commit.
8. `commit` lỗi + `rollback` lỗi + `Connection.close` lỗi.
9. `executeUpdate` lỗi + statement close lỗi + rollback lỗi + connection close lỗi.
10. `ConnectionSource.open` lỗi → không có resource nào để đóng.

**Không tuyên bố đã kết nối thật tới database.** Test double chỉ kiểm tra logic phía Java, lời gọi interface và ngữ nghĩa try-with-resources. Phần cần SQL thật phải dùng integration test ở môi trường phù hợp.

### 10.1. Toàn bộ file JdbcFailureTestingDemo.java

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.EnumSet;
import java.util.List;
import java.util.stream.Collectors;

public final class JdbcFailureTestingDemo {
    enum Fault {
        OPEN, PREPARE, EXECUTE_QUERY, READ_ROW, EXECUTE_UPDATE,
        COMMIT, ROLLBACK, CLOSE_RESULT, CLOSE_STATEMENT, CLOSE_CONNECTION
    }

    @FunctionalInterface
    interface ConnectionSource {
        Connection open() throws SQLException;
    }

    private static void check(boolean ok, String description) {
        if (!ok) throw new AssertionError(description);
    }

    static String findName(ConnectionSource source) throws SQLException {
        try (Connection c = source.open();
             PreparedStatement ps =
                     c.prepareStatement("SELECT name FROM users WHERE id = ?")) {
            ps.setLong(1, 7L);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? rs.getString("name") : "NONE";
            }
        }
    }

    static void updateStatus(ConnectionSource source) throws SQLException {
        try (Connection c = source.open()) {
            c.setAutoCommit(false);
            try {
                try (PreparedStatement ps = c.prepareStatement(
                        "UPDATE users SET active = ? WHERE id = ?")) {
                    ps.setBoolean(1, true);
                    ps.setLong(2, 7L);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException("unexpected row count");
                    }
                }
                c.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    static final class Session implements InvocationHandler {
        final EnumSet<Fault> faults;
        final List<String> events = new ArrayList<>();
        final Connection connection = proxy(Connection.class);
        final PreparedStatement statement = proxy(PreparedStatement.class);
        final ResultSet result = proxy(ResultSet.class);
        boolean first = true;

        Session(Fault... failures) {
            faults = failures.length == 0
                    ? EnumSet.noneOf(Fault.class)
                    : EnumSet.copyOf(Arrays.asList(failures));
        }

        private <T> T proxy(Class<T> api) {
            return api.cast(Proxy.newProxyInstance(
                    api.getClassLoader(), new Class<?>[] {api}, this));
        }

        Connection open() throws SQLException {
            events.add("open");
            fail(Fault.OPEN, "open failure");
            return connection;
        }

        private void fail(Fault point, String message) throws SQLException {
            if (faults.contains(point)) throw new SQLException(message);
        }

        @Override
        public Object invoke(Object receiver, Method method, Object[] args)
                throws SQLException {
            String name = method.getName();
            switch (name) {
                case "prepareStatement":
                    events.add("prepare");
                    fail(Fault.PREPARE, "prepare failure");
                    return statement;
                case "setLong":
                case "setBoolean":
                    return null;
                case "executeQuery":
                    events.add("query");
                    fail(Fault.EXECUTE_QUERY, "query failure");
                    return result;
                case "next":
                    events.add("next");
                    fail(Fault.READ_ROW, "read failure");
                    boolean available = first;
                    first = false;
                    return available;
                case "getString":
                    return "Ada";
                case "executeUpdate":
                    events.add("update");
                    fail(Fault.EXECUTE_UPDATE, "update failure");
                    return 1;
                case "setAutoCommit":
                    events.add("autoCommit=false");
                    return null;
                case "commit":
                    events.add("commit");
                    fail(Fault.COMMIT, "commit failure");
                    return null;
                case "rollback":
                    events.add("rollback");
                    fail(Fault.ROLLBACK, "rollback failure");
                    return null;
                case "close":
                    if (receiver == result) {
                        events.add("close:ResultSet");
                        fail(Fault.CLOSE_RESULT, "close ResultSet");
                    } else if (receiver == statement) {
                        events.add("close:PreparedStatement");
                        fail(Fault.CLOSE_STATEMENT, "close PreparedStatement");
                    } else {
                        events.add("close:Connection");
                        fail(Fault.CLOSE_CONNECTION, "close Connection");
                    }
                    return null;
                case "toString":
                    return "JDBC proxy test double";
                default:
                    throw new UnsupportedOperationException(
                            "Test double unsupported: " + name);
            }
        }

        List<String> closeEvents() {
            return events.stream().filter(s -> s.startsWith("close:"))
                    .collect(Collectors.toList());
        }

        boolean saw(String event) {
            return events.contains(event);
        }
    }

    static SQLException expectSql(String expectedMessage, SqlAction action)
            throws Exception {
        try {
            action.run();
            throw new AssertionError(
                    "Expected SQLException: " + expectedMessage);
        } catch (SQLException exception) {
            check(expectedMessage.equals(exception.getMessage()),
                    "Unexpected primary error: " + exception.getMessage());
            return exception;
        }
    }

    @FunctionalInterface
    interface SqlAction {
        void run() throws SQLException;
    }

    static void suppressed(SQLException primary, String... expected) {
        String[] actual = Arrays.stream(primary.getSuppressed())
                .map(Throwable::getMessage).toArray(String[]::new);
        check(Arrays.equals(actual, expected),
                "Suppressed mismatch: " + Arrays.toString(actual));
    }

    public static void main(String[] args) throws Exception {
        Session normal = new Session();
        check("Ada".equals(findName(normal::open)), "happy query");
        check(normal.closeEvents().equals(List.of(
                "close:ResultSet", "close:PreparedStatement",
                "close:Connection")), "reverse close order");
        System.out.println("query success and close order = PASS");

        Session queryFailure = new Session(
                Fault.EXECUTE_QUERY, Fault.CLOSE_STATEMENT,
                Fault.CLOSE_CONNECTION);
        SQLException queryError = expectSql("query failure",
                () -> findName(queryFailure::open));
        suppressed(queryError,
                "close PreparedStatement", "close Connection");
        check(queryFailure.closeEvents().equals(List.of(
                "close:PreparedStatement", "close:Connection")),
                "query failed before result opened");
        System.out.println(
                "query error primary; two close errors suppressed = PASS");

        Session readFailure = new Session(Fault.READ_ROW, Fault.CLOSE_RESULT,
                Fault.CLOSE_STATEMENT, Fault.CLOSE_CONNECTION);
        SQLException readError = expectSql("read failure",
                () -> findName(readFailure::open));
        suppressed(readError, "close ResultSet",
                "close PreparedStatement", "close Connection");
        System.out.println(
                "result read error; three closes attempted = PASS");

        Session closeOnly = new Session(Fault.CLOSE_RESULT,
                Fault.CLOSE_STATEMENT, Fault.CLOSE_CONNECTION);
        SQLException closeError = expectSql("close ResultSet",
                () -> findName(closeOnly::open));
        suppressed(closeError,
                "close PreparedStatement", "close Connection");
        System.out.println("close-only primary and suppressed = PASS");

        Session prepareFailure = new Session(
                Fault.PREPARE, Fault.CLOSE_CONNECTION);
        SQLException prepareError = expectSql("prepare failure",
                () -> findName(prepareFailure::open));
        suppressed(prepareError, "close Connection");
        check(prepareFailure.closeEvents().equals(
                List.of("close:Connection")),
                "partially initialized close");
        System.out.println(
                "partial initialization cleans connection = PASS");

        Session transactionSuccess = new Session();
        updateStatus(transactionSuccess::open);
        check(transactionSuccess.saw("autoCommit=false")
                && transactionSuccess.saw("update")
                && transactionSuccess.saw("commit")
                && !transactionSuccess.saw("rollback"),
                "successful transaction behavior");
        check(transactionSuccess.closeEvents().equals(List.of(
                "close:PreparedStatement", "close:Connection")),
                "transaction close order");
        System.out.println(
                "transaction success commits before close = PASS");

        Session updateFailure = new Session(Fault.EXECUTE_UPDATE);
        SQLException updateError = expectSql("update failure",
                () -> updateStatus(updateFailure::open));
        suppressed(updateError);
        check(updateFailure.saw("rollback")
                && !updateFailure.saw("commit"),
                "update failure rollback");
        System.out.println("update failure rolls back = PASS");

        Session commitFailure = new Session(Fault.COMMIT, Fault.ROLLBACK,
                Fault.CLOSE_CONNECTION);
        SQLException commitError = expectSql("commit failure",
                () -> updateStatus(commitFailure::open));
        suppressed(commitError, "rollback failure", "close Connection");
        check(commitFailure.saw("commit")
                && commitFailure.saw("rollback"),
                "commit failure rollback attempt");
        System.out.println(
                "commit/rollback/close failures preserved = PASS");

        Session combinedFailure = new Session(Fault.EXECUTE_UPDATE,
                Fault.CLOSE_STATEMENT, Fault.ROLLBACK,
                Fault.CLOSE_CONNECTION);
        SQLException combinedError = expectSql("update failure",
                () -> updateStatus(combinedFailure::open));
        suppressed(combinedError, "close PreparedStatement",
                "rollback failure", "close Connection");
        check(!combinedFailure.saw("commit")
                && combinedFailure.saw("rollback"),
                "combined failure transaction flow");
        System.out.println(
                "update/close/rollback failure ordering = PASS");

        Session openFailure = new Session(Fault.OPEN);
        SQLException opened = expectSql("open failure",
                () -> findName(openFailure::open));
        suppressed(opened);
        check(openFailure.closeEvents().isEmpty(),
                "failed resource acquisition cannot be closed");
        System.out.println(
                "open failure creates no close attempt = PASS");

        System.out.println("checks = PASS");
    }
}
```

### 10.2. Lệnh Java 17 và stdout đúng

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 JdbcFailureTestingDemo.java
java JdbcFailureTestingDemo
```

Kết quả **đã biên dịch và chạy trên JDK 17**, không có warning; stdout chính xác:

```text
query success and close order = PASS
query error primary; two close errors suppressed = PASS
result read error; three closes attempted = PASS
close-only primary and suppressed = PASS
partial initialization cleans connection = PASS
transaction success commits before close = PASS
update failure rolls back = PASS
commit/rollback/close failures preserved = PASS
update/close/rollback failure ordering = PASS
open failure creates no close attempt = PASS
checks = PASS
```

Chương trình không in các chuỗi ngẫu nhiên, timestamp hoặc phụ thuộc thứ tự scheduler; output có thể đối chiếu chính xác.

### 10.3. Vì sao dùng Proxy?

`Connection`, `PreparedStatement` và `ResultSet` là các interface JDBC lớn, nhiều methods. Một dynamic proxy có thể mô phỏng **chỉ những phương thức test cần**, lưu event log và chủ động ném `SQLException` ở điểm đã định.

Ưu điểm:

- Không cần driver/database ngoài để test control flow.
- Có thể tạo nhiều close exceptions cùng lúc.
- Ghi thứ tự đóng resource.
- Có thể kiểm tra phương thức nào **không được gọi**, ví dụ không commit sau update failure.
- Không cần can thiệp vào mã source Java/JDBC hay server.

**Giới hạn:** một proxy đơn giản không phải JDBC driver hoàn chỉnh. Nó không biết SQL thực, kết nối thật, transaction state server, network timeouts hay pool implementation. Nó ném `UnsupportedOperationException` nếu chương trình gọi một method chưa mô phỏng; điều đó hữu ích để báo test double chưa đủ thay vì trả giá trị giả im lặng.

### 10.4. Vì sao test case không nên gộp lại?

Nếu cùng một Session giả lập cả lỗi executeQuery và lỗi đọc ResultSet, **lỗi executeQuery xảy ra trước**, ResultSet chưa tồn tại nên bạn **không bao giờ kiểm thử được lỗi đọc**. Mỗi case đặt fault đúng điểm là cách tăng coverage có ý nghĩa.

Tương tự, nếu test “close-only” nhưng body đã ném lỗi, bạn không thể chứng minh lỗi close đầu tiên được chọn làm primary; body exception sẽ là primary. Vì vậy cần **một case riêng** cho body thành công nhưng close thất bại.

### 10.5. Vì sao phải kiểm tra các event **không xảy ra**?

Một test transaction phải assert cả:

- Trong success: `commit` đã gọi, `rollback` không gọi.
- Trong update failure: `rollback` đã gọi, **commit không gọi**.
- Trong open failure: **không cố close một resource chưa được cấp**.

Chỉ assert “rollback được gọi” không phát hiện được một implementation lỗi gọi **commit trước** rồi mới rollback. Assertions âm tính giúp tìm bug về thứ tự/nhánh.

### 10.6. Vì sao không yêu cầu test mock chứng minh DB rollback thật?

Dynamic proxy chỉ tạo event "rollback"; nó không có database state để hoàn tác. Để xác minh durability, isolation, trigger, lock và persisted rows, phải chạy integration test với DB thật. Phân biệt điều này trong test report là yêu cầu chất lượng, không phải hạn chế nhỏ có thể bỏ qua.

## 11. Đọc và báo cáo exception một cách an toàn

Một lỗi JDBC trong production có thể có:

```java
catch (SQLException error) {
    logSqlStateAndVendorCode(error);

    for (Throwable suppressed : error.getSuppressed()) {
        logCleanupFailure(suppressed);
    }
    throw error;
}
```

Đây là **đoạn minh họa không độc lập**, với logging methods do dự án định nghĩa.

Nên ghi:

- Operation name hoặc SQL fingerprint (không log nguyên parameter chứa dữ liệu nhạy cảm).
- Request/transaction correlation ID.
- SQLState, vendor error code và throwable class.
- Primary exception, suppressed exceptions.
- Bước lỗi: ACQUIRE, PREPARE, EXECUTE, READ, COMMIT, ROLLBACK, CLOSE.
- Pool metrics/connection lifecycle phù hợp.

**Không log username/password, access tokens hay toàn bộ query parameters có PII** chỉ để debug JDBC.

### 11.1. Không tự retry theo mọi SQLException

`SQLException` là họ exception rộng. Một số lỗi liên quan tới data validation/constraint, một số tới tranh chấp/timeout/connection; không có quy tắc “mọi SQLException retry ba lần”.

Lựa chọn retry cần:

1. Phân loại lỗi theo SQLState/vendor-specific contract và driver.
2. Xác định operation là **read-only** hay có side effect.
3. Xác định trạng thái transaction và commit đã/đang/không chắc đã xảy ra.
4. Có idempotency key nếu retry write.
5. Có deadline tổng, backoff, giới hạn số lần thử và cơ chế circuit-breaker nếu cần.
6. Xác minh không tạo duplicate logical operation.

### 11.2. Commit ambiguity phải được thể hiện ra API nghiệp vụ

Một service không nên trả “chắc chắn chưa ghi” chỉ vì `commit` ném exception. Trong phân tán, connection có thể đứt **sau khi server đã commit nhưng trước khi client nhận phản hồi**.

Nếu nghiệp vụ quan trọng, ghi operation ID trong transaction và cung cấp cách kiểm tra trạng thái theo ID. Nếu kết quả không rõ, báo **UNKNOWN/REQUIRES_RECONCILIATION**, không giả vờ failed-and-safe-to-retry.

### 11.3. Rollback failure không đồng nghĩa transaction tự commit

Rollback thất bại nói lên **thao tác rollback không hoàn tất/không xác nhận được**, không chứng minh database đã commit hoặc đã rollback. Cần theo dõi trạng thái thực từ server/transaction manager, tùy loại lỗi và khả năng kết nối.

## 12. Kiểm thử với connection pool, framework và async

### 12.1. Ai sở hữu transaction?

Nếu repository tự gọi `DataSource.getConnection()` và `setAutoCommit(false)`, nó có thể là owner transaction như ví dụ.

Nếu framework (Spring/Jakarta Transactions) cấp connection đã tham gia transaction:

- Framework có thể kiểm soát commit/rollback và connection lifecycle.
- Test cần assert tương tác với **framework transaction boundary**, không ép repository tự gọi `commit/close`.
- Không sử dụng TWR tự đóng connection do framework sở hữu nếu contract framework không cho phép.

**Không có một quy tắc “luôn gọi rollback ở repository” đúng cho mọi kiến trúc.** Rule là mỗi transaction có **một owner rõ ràng**.

### 12.2. Một lỗi close của pooled connection cần test riêng

Với pool, lỗi `Connection.close` có thể xảy ra khi wrapper trả connection về pool hoặc pool phát hiện connection hỏng. Test integration nên đo pool health và request latency, chứ không khẳng định physical connection chắc chắn đã đóng tại đúng thời điểm close wrapper.

### 12.3. Không đưa ResultSet sống qua thread async tùy tiện

Một method trả `CompletableFuture` rồi đóng `Connection/Statement/ResultSet` trong thread gốc có thể tạo lỗi đọc cursor khi async task bắt đầu. Nếu kết quả cần xử lý async, map sang DTO/immutable payload **trong scope JDBC** hoặc chuyển ownership resource theo một abstraction có lifecycle rõ, và kiểm thử cancellation/close.

### 12.4. Timeout không luôn dừng SQL trên server

Một request timeout hoặc `Future.get(timeout)` hết hạn có thể chỉ làm thread đợi hết hạn, **không chứng minh statement trên server đã bị hủy**. Nếu yêu cầu timeout SQL, dùng API được driver hỗ trợ như `Statement.setQueryTimeout()` hoặc cơ chế cancellation theo contract/provider, và có integration test để quan sát.

Không tự coi exception “timeout” của HTTP layer là bằng chứng database chưa áp dụng thay đổi.

## 13. Anti-pattern: những test tưởng đúng nhưng không bắt được bug

### 13.1. Chỉ assert kiểu exception

```java
assertThrows(SQLException.class, () -> repo.findName());
```

Có thể PASS do close error thay vì executeQuery error. Nên xác minh **đúng fault point, primary message/state và cleanup sequence**.

### 13.2. Dùng mock “trả null” khi executeQuery lỗi

Nếu muốn test `SQLException`, hãy **ném SQLException**. Mock trả `null` có thể gây `NullPointerException` ở code dùng ResultSet, không kiểm tra được đường lỗi JDBC thực tế và tạo false confidence.

### 13.3. Mock được cả ResultSet dù query chưa trả về

Nếu `executeQuery` đã ném, không có ResultSet được khởi tạo. Test assert `rs.close` trong tình huống đó là sai về resource lifecycle.

### 13.4. Để lỗi close che lỗi query

Một `finally { statement.close(); }` viết cẩu thả có thể thay thế primary exception nếu `close()` ném. Try-with-resources giúp giữ lỗi body và attached close errors. Nếu code phải close thủ công, hãy áp dụng policy suppressed riêng.

### 13.5. Không thử rollback khi update thất bại

Nếu transaction do method sở hữu, catch chỉ log rồi return mà không rollback có thể khiến state transaction treo cho tới close; do `Connection.close` với active transaction là implementation-defined, đừng dựa vào close như rollback tự động.

### 13.6. Đặt commit trong finally

`finally { connection.commit(); }` có thể commit những thay đổi một phần khi code đã gặp exception. Commit phải thuộc **nhánh thành công**, rollback thuộc **nhánh thất bại** theo transaction policy.

### 13.7. Retry ngay sau commit exception

Nếu DB đã commit nhưng phản hồi bị mất, retry giao dịch không idempotent có thể nhân đôi side effect. Dùng operation ID, unique constraint, status reconciliation và retry policy.

### 13.8. Đếm số close của physical socket trong unit test

Unit test mock có thể chứng minh code **gọi close**. Không chứng minh pool/provider đóng socket vật lý hay nhả server cursor đúng cách. Những điều đó cần integration test/provider telemetry.

### 13.9. Quên kiểm thử partial initialization

`getConnection` thành công, `prepareStatement` lỗi: Connection vẫn phải được đóng. Đây là nhánh thường bị bỏ sót khi developer chỉ thử body exception sau khi mọi resource đã khởi tạo thành công.

### 13.10. Quên suppressed trên rollback

Nếu rollback cũng lỗi, thay thế exception gốc bằng rollback error có thể khiến log đánh mất **nguyên nhân business/SQL ban đầu**. Giữ primary và `addSuppressed` hợp lý; trong unit test assert thứ tự/loại lỗi.

### 13.11. Test chỉ xác minh method calls, không state DB

Mock `commit` được gọi không chứng minh DB đã commit. Integration test phải đọc persisted rows qua connection khác sau commit/rollback để xác minh hiệu quả thật.

### 13.12. Không test exception giữa chừng khi đọc ResultSet

Nếu ResultSet đã trả một số rows rồi `next()` lỗi, code có thể vô tình trả partial list như success. Test phải quyết định partial-result contract và kiểm tra resource cleanup.

## 14. Ma trận test thực hành nên đặt tên cụ thể

| Test name gợi ý | Failure injection | Assertion trọng tâm |
| --- | --- | --- |
| `querySuccessClosesInReverseOrder` | Không lỗi | Kết quả và RS → PS → C |
| `connectionAcquireFailureDoesNotCloseUncreatedResource` | OPEN | Exception propagate, 0 closes |
| `prepareFailureClosesConnection` | PREPARE | Chỉ C được close, primary prepare |
| `executeFailurePreservesCloseErrors` | EXECUTE_QUERY + PS/C close | Primary execute; 2 suppressed |
| `readFailureClosesAllResources` | READ_ROW + 3 close | Primary read; 3 suppressed |
| `closeOnlyFailureBecomesPrimary` | 3 close, body OK | RS close primary; PS/C suppressed |
| `successfulUpdateCommitsBeforeClose` | Không lỗi | Commit 1, rollback 0, C close |
| `updateFailureRollsBack` | EXECUTE_UPDATE | Commit 0, rollback 1 |
| `statementCloseFailureTriggersRollback` | CLOSE_STATEMENT | Theo cấu trúc method, không commit và có rollback |
| `commitFailureAttemptsRollback` | COMMIT | Rollback được thử theo policy |
| `commitRollbackCloseFailuresAllVisible` | COMMIT+ROLLBACK+C close | Primary commit; 2 suppressed |
| `updateCloseRollbackFailuresKeepPrimary` | UPDATE+PS close+ROLLBACK+C close | Primary update; 3 suppressed |
| `emptyResultIsNotSqlFailure` | ResultSet.next false | Empty outcome, closes |
| `runtimeMappingFailureStillCloses` | Mapping RuntimeException | Cả RS/PS/C được đóng |
| `poolReturnsSlotAfterError` | Driver/pool integration | Active checkout trở về baseline |
| `dbRollbackActuallyUndoesWrites` | Real DB SQL fail | Persisted state không chứa partial write |

Bộ demo hoàn chỉnh thực hiện **10 test chính**; những test bổ sung trong ma trận là gợi ý để mở rộng phù hợp code dự án, **không được báo là đã chạy khi chưa thực hiện**.

## 15. Bài tập có đáp án

### Bài 1 — Lỗi không có Connection

`DataSource.getConnection()` ném `SQLException`. Có nên assert `Connection.close()` được gọi không?

**Đáp án:** Không. Nếu chưa nhận được Connection hợp lệ, resource đó chưa được tạo cho caller và không có object để đóng. Test nên assert exception propagate đúng.

### Bài 2 — Partial initialization

Connection được cấp thành công, nhưng `prepareStatement()` lỗi. Resource nào vẫn phải được đóng?

**Đáp án:** Connection; PreparedStatement chưa được khởi tạo thành công nên không có PS để đóng.

### Bài 3 — Query execute lỗi

`executeQuery()` ném lỗi trước khi trả ResultSet. Test có nên thấy `ResultSet.close()`?

**Đáp án:** Không. Chỉ những resource đã khởi tạo thành công mới được TWR tự đóng.

### Bài 4 — Lỗi đọc row

`ResultSet.next()` ném `SQLException` sau khi ResultSet đã tạo. Thứ tự close kỳ vọng?

**Đáp án:** ResultSet → PreparedStatement/Statement → Connection.

### Bài 5 — Close-only error

Body query không lỗi, nhưng ResultSet.close ném lỗi, PS/C close đều lỗi. Exception chính là gì?

**Đáp án:** Lỗi close ResultSet đầu tiên theo thứ tự đóng; các lỗi close sau bị suppressed.

### Bài 6 — Query + close errors

`executeQuery` ném primary, Statement.close cũng lỗi. Có nên thay primary bằng close error không?

**Đáp án:** Không. TWR giữ lỗi query là primary, gắn close error vào `getSuppressed()`.

### Bài 7 — Suppressed vs cause

`getSuppressed` có phải luôn giống `SQLException.getNextException` hoặc `getCause` không?

**Đáp án:** Không. Đây là các cấu trúc exception khác nhau, phục vụ mục tiêu khác nhau.

### Bài 8 — Update failure

Transaction đang autoCommit=false, `executeUpdate` ném SQLException. Nhánh transaction nên thử gì?

**Đáp án:** Rollback (nếu method sở hữu transaction và Connection cho phép), không commit; giữ lỗi gốc.

### Bài 9 — Rollback cũng lỗi

Rollback ném SQLException sau update failure. Làm sao không mất lỗi update?

**Đáp án:** `original.addSuppressed(rollbackFailure)` rồi ném lại original, đồng thời để TWR xử lý close.

### Bài 10 — Commit lỗi

`commit()` ném SQLException do socket mất kết nối. Có chắc database chưa commit không?

**Đáp án:** Không. Outcome có thể không rõ; cần idempotency/reconciliation, không retry side effect một cách mù quáng.

### Bài 11 — Close Connection trong active transaction

Có được giả định `Connection.close()` chắc chắn rollback khi autoCommit=false không?

**Đáp án:** Không. JDBC mô tả outcome implementation-defined khi close có active transaction; commit/rollback tường minh trước close.

### Bài 12 — PreparedStatement.close lỗi

Trong mẫu transaction, statement close lỗi ngay trước `c.commit()`. Vì sao commit có thể không được gọi?

**Đáp án:** Close xảy ra ở cuối try-with-resources trong khối transaction; exception chuyển control flow sang catch để rollback.

### Bài 13 — Exception order

Trong demo: update lỗi → statement close lỗi → rollback lỗi → connection close lỗi. Primary và ba suppressed lần lượt là gì?

**Đáp án:** Primary update failure; suppressed close PreparedStatement, rollback failure, close Connection.

### Bài 14 — Mock vs database

Proxy JDBC ghi event "commit". Đã xác minh có dữ liệu được commit trên server chưa?

**Đáp án:** Chưa. Nó chỉ xác minh lời gọi. Phải dùng database thật và đọc persisted state để kiểm tra.

### Bài 15 — SQLState

Có nên assert message SQLException của mọi driver luôn là `"syntax error near ..."` giống nhau?

**Đáp án:** Không. Messages và vendor codes phụ thuộc provider/version. Dùng contract/codes phù hợp môi trường, không hardcode message cross-driver khi integration test.

### Bài 16 — Runtime mapping

`ResultSet.getString` thành công nhưng mapper ném IllegalArgumentException. Resource có được TWR đóng không?

**Đáp án:** Có. TWR cleanup khi rời scope do runtime exception; nếu transaction trong phạm vi catch, rollback policy cũng cần xét.

### Bài 17 — ResultSet rỗng

`rs.next()` trả false. Có được xem là SQL execution error không?

**Đáp án:** Không mặc định. Empty result là một kết quả hợp lệ, cần test riêng theo domain contract.

### Bài 18 — Pool

Sau 100 request thất bại, pool active count tăng mãi. Điều gì cần điều tra?

**Đáp án:** Connection not returned, lazy stream/callback giữ resource, close failures, concurrency và pool configuration. Quan sát ở quiescent state; không kết luận từ một snapshot động.

### Bài 19 — Transaction owner

Framework quản lý transaction/Connection. Repository có nên tự `commit/rollback/close` Connection do framework đưa vào không?

**Đáp án:** Không tự ý. Tuân hợp đồng ownership và transaction manager; test phù hợp tầng framework.

### Bài 20 — Retry

Lệnh ghi không idempotent lỗi khi commit. Có nên retry ngay ba lần để chắc chắn thành công?

**Đáp án:** Không. Nếu server đã commit nhưng client mất phản hồi, retry có thể gây duplicate. Cần operation identity/idempotency và status check.

### Bài 21 — Timeout HTTP

HTTP request timeout trong lúc DB query đang chạy. Có chứng minh query phía server đã ngừng không?

**Đáp án:** Không. Cần timeout/cancellation JDBC được provider hỗ trợ và integration test quan sát server state.

### Bài 22 — Connection.close error

TWR gọi `Connection.close()` nhưng ném SQLException. Unit test có chứng minh physical socket đã đóng không?

**Đáp án:** Không. Với pooled wrapper, close thường là trả logical connection; lifecycle vật lý tùy pool/provider.

### Bài 23 — Chọn injection point

Muốn kiểm tra ResultSet.close lỗi khi body đã trả dữ liệu, nên inject lỗi ở `executeQuery` hay `ResultSet.close`?

**Đáp án:** Chỉ ở ResultSet.close cho close-only case; nếu inject executeQuery trước, ResultSet sẽ không tạo nên không kiểm tra được close của nó.

### Bài 24 — Tại sao assert not-called?

Test update failure đã thấy rollback được gọi. Vì sao vẫn nên assert commit không gọi?

**Đáp án:** Vì một implementation lỗi có thể gọi cả commit và rollback; assertion âm tính bắt bug thứ tự/nhánh đó.

### Bài 25 — Log an toàn

Khi JDBC lỗi, có nên log mọi query parameter, credentials và connection URL chứa mật khẩu không?

**Đáp án:** Không. Ghi operation ID, SQL fingerprint, SQLState/vendor code và primary/suppressed errors; tránh lộ secrets/PII.

### Bài 26 — Database dialect

Test chạy với một DB in-memory khác vendor đã PASS. Có đủ chứng minh behavior của production DB không?

**Đáp án:** Không. SQL dialect, transaction behavior và driver/pool có thể khác. Cần contract/integration tests trên provider sản xuất đối với yêu cầu quan trọng.

## 16. Checklist QA cho một repository JDBC

- [ ] Biết rõ điểm nào có thể ném lỗi: acquire, prepare, bind, execute, read, commit, rollback, close.
- [ ] Tách lỗi query, transaction và close thành test cases độc lập.
- [ ] Không chỉ assert `SQLException.class` mà còn test đúng fault point.
- [ ] Resource tạo thành công được thử đóng khi scope kết thúc.
- [ ] Resource chưa tạo thành công **không** bị test yêu cầu đóng giả.
- [ ] Thứ tự đóng JDBC resource phù hợp: ResultSet → Statement → Connection.
- [ ] Lỗi body là primary, lỗi close sau đó suppressed.
- [ ] Close-only failure có thể trở thành primary.
- [ ] Nhiều close failures không ngăn cleanup những resources còn lại.
- [ ] Phân biệt `getSuppressed()`, `getNextException()` và `getCause()`.
- [ ] Nếu repository sở hữu transaction, có commit ở đường thành công.
- [ ] Khi update lỗi, không commit; rollback được thử theo policy.
- [ ] Rollback failure được ghi lại mà không che lỗi gốc.
- [ ] Commit exception được xem xét như **outcome có thể không rõ**.
- [ ] Không retry lệnh ghi có side effect nếu chưa có idempotency/reconciliation.
- [ ] Không dùng Connection.close thay cho explicit commit/rollback.
- [ ] Không đóng Connection do framework/transaction manager sở hữu ngoài hợp đồng.
- [ ] Tách unit double và integration test database thật.
- [ ] Verify persisted DB state qua connection độc lập trong integration test.
- [ ] Verify pool checkout/checkin ở nhánh success/error và quan sát quiescent baseline.
- [ ] Không trả ResultSet/lazy stream khi resource đã bị đóng.
- [ ] Query timeout/cancel được kiểm tra riêng theo provider, không dựa vào HTTP timeout.
- [ ] Không log secrets, access tokens, hoặc PII trong SQL parameters.
- [ ] Test empty result không bị xem nhầm SQLException.
- [ ] Test mapping RuntimeException vẫn dọn tài nguyên.
- [ ] Test cả lỗi initialization và lỗi close.
- [ ] Đảm bảo test double fail-fast với method JDBC chưa mô phỏng.
- [ ] Tránh assertions phụ thuộc SQL exception message của mọi vendor.
- [ ] Tất cả ví dụ dùng JDBC/TWR còn hiệu lực trong Java hiện đại.
- [ ] Mã Java mẫu đã compile/run được dưới JDK 17.

## 17. Tài liệu Java/JDBC chính thức

- [Java SE 17 — Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): `commit()`, `rollback()`, `setAutoCommit()`, `close()` và lưu ý active transaction khi close.
- [Java SE 17 — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): binding tham số, `executeQuery` và `executeUpdate`.
- [Java SE 17 — ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): `next()`, getter, `close()` và vòng đời cursor.
- [Java SE 17 — Statement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html): `close()` và sự phụ thuộc của ResultSet.
- [Java SE 17 — SQLException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor code, `getNextException`.
- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `addSuppressed`, `getSuppressed`.
- [JLS Java SE 17 `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): khởi tạo trái sang phải, đóng ngược, exception suppression.
- [Java SE 17 — DataSource](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/javax/sql/DataSource.html): abstraction lấy Connection.
- [Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): dynamic proxy dùng làm test double.

## 18. Tổng kết

Một bộ test JDBC tốt không chỉ chứng minh SQL **chạy được khi mọi thứ thuận lợi**. Nó phải cố tình gây lỗi ở từng bước của pipeline, xác minh resource cleanup, transaction ownership và thứ tự xử lý ngoại lệ.

Khi `executeQuery` lỗi, ResultSet có thể chưa tồn tại, nhưng Statement/Connection đã mở vẫn cần được dọn. Khi `ResultSet.next` lỗi, cả ba resource cần được thử đóng. Khi close cũng lỗi, **lỗi SQL ban đầu không được bị mất**; Java try-with-resources giữ nó làm primary và gắn close failures qua `getSuppressed()`. Nếu **chỉ** close lỗi, close exception đầu tiên trở thành primary.

Trong transaction, success mới commit; failure được xử lý theo rollback policy của owner; rollback failure phải được ghi mà không che original exception. Đặc biệt, **`commit()` ném exception không chứng minh server chưa commit** — cần chống retry trùng, idempotency và trạng thái reconciliation nếu nghiệp vụ có side effect.

Cuối cùng, test double JDBC thuần Java rất hữu ích để kiểm tra logic/exception/close order một cách deterministic; còn **database, driver, transaction và connection pool thật** cần được kiểm chứng bằng integration tests riêng. Đây là cách tiếp cận vừa thực tế vừa phù hợp hoàn toàn với **Java 17+ và các API JDBC hiện hành**.