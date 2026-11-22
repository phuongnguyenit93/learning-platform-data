# Duyệt SQLException, SQLState, mã nhà cung cấp và chuỗi nguyên nhân trong JDBC

Khi thao tác JDBC thất bại, `java.sql.SQLException` không chỉ chứa một message. Nó có thể mang **SQLState**, **mã lỗi của nhà cung cấp**, một chuỗi `SQLException` kế tiếp, một chuỗi **underlying causes**, và cả những lỗi phát sinh khi đóng tài nguyên. Nếu chỉ log `e.getMessage()`, ứng dụng có thể bỏ qua nguyên nhân thực tế hoặc bỏ sót lỗi thứ hai trong một batch.

Đây là kiến thức **vẫn áp dụng trên Java 17+ và JDK 26 hiện hành**. `SQLException` là checked exception tiêu chuẩn trong `java.sql`, đồng thời triển khai `Iterable<Throwable>`. Bởi vậy có hai cách duyệt rất hữu ích: vòng `getNextException()` khi cần **các lỗi JDBC**, và `for (Throwable item : exception)` khi muốn đi qua **các SQLExceptions cùng underlying causes**. Những lỗi bị suppressed khi dùng try-with-resources lại phải xử lý riêng.

Bài học thuộc nhóm **Ngoại lệ JDBC**, giải thích:

- Cách đọc `getSQLState()`, `getErrorCode()`, `getClass()`, `getMessage()` và metadata theo driver/DBMS.
- Phân biệt `getNextException()`, `getCause()`, `getSuppressed()` và `SQLException.iterator()`.
- Duyệt ngoại lệ có giới hạn, tránh log lặp/không kết thúc; giữ cause khi chuyển thành lỗi nghiệp vụ.
- Ý nghĩa các class SQLState như `08`, `23`, `28`, `40`, `42`, `01`; không dùng chúng như bảo đảm retry.
- Xử lý `SQLWarning`, `BatchUpdateException` và các subclasses transient/non-transient/recoverable.
- Ví dụ Java 17+ chạy độc lập, đã kiểm chứng bằng `javac --release 17` và JDK 24.
- Cách chẩn đoán một lỗi thật trên DBMS mà không lộ secrets hoặc bịa vendor error codes.

## 1. Vì sao SQLException có nhiều nhánh lỗi?

Một SQLException có thể đại diện cho lỗi ở nhiều tầng: database server, JDBC driver, transaction, connection pool, network và application. JDBC cung cấp **đường liên kết riêng** cho nhiều SQLException, đồng thời vẫn kế thừa những tính năng của `Throwable` trong Java.

```text
SQLException root
  | SQLState=HY000, vendorCode=9001
  |
  +-- getCause() ---------------------> IOException
  |                                     "socket read stopped"
  |
  +-- getNextException() ------------> SQLIntegrityConstraintViolationException
  |                                      SQLState=23505, vendorCode=9002
  |                                      |
  |                                      +-- getCause()
  |                                      |     |
  |                                      |     v
  |                                      |   IllegalStateException
  |                                      |
  |                                      +-- getNextException()
  |                                            |
  |                                            v
  |                                     SQLTransientConnectionException
  |                                      SQLState=08006, vendorCode=9003
  |
  +-- getSuppressed() ----------------> IOException
                                        "statement close failed"
```

Đây là **đồ thị giả lập** được xây bằng constructors Java trong bài, không phải những mã vendor thực tế. Các số `9001`, `9002`, `9003` chỉ giúp bạn nhìn thấy mỗi exception có một mã riêng; chúng **không biểu thị mã lỗi thống nhất của mọi DBMS**.

| Quan hệ | Method | Ý nghĩa | Phương pháp duyệt |
| --- | --- | --- | --- |
| Lỗi JDBC tiếp theo | `getNextException()` | Nối những SQLExceptions thuộc cùng chain. | Vòng `for` trên `SQLException`. |
| Nguyên nhân Java | `getCause()` | Vì sao Throwable được sinh ra, có thể là `IOException`/`RuntimeException`. | Vòng trên `Throwable` hoặc JDBC iterator. |
| Lỗi phụ khi cleanup | `getSuppressed()` | Những Throwable bị giữ lại khi xảy ra primary failure. | Duyệt `Throwable[]` riêng. |
| Kết hợp SQLExceptions và causes | `SQLException.iterator()` | Trả `Iterator<Throwable>` đi qua các SQLExceptions và nguyên nhân phía dưới của chúng. | `for (Throwable t : e)`. |

**Quan trọng:** ba loại liên kết **không có nghĩa giống nhau**. `getNextException()` không đồng nghĩa root cause; `getCause()` không duyệt qua sibling JDBC errors; còn `getSuppressed()` không tự nằm trong kết quả của JDBC iterator.

## 2. Các API cần thuộc

| API | Giá trị trả | Ghi chú |
| --- | --- | --- |
| `getMessage()` | `String` | Mô tả lỗi; có thể `null` hoặc chứa dữ liệu nhạy cảm. |
| `getSQLState()` | `String` | SQLState; có thể `null` nếu driver/framework không cung cấp. |
| `getErrorCode()` | `int` | Mã riêng của vendor; có thể `0` khi không cung cấp. |
| `getNextException()` | `SQLException` | Exception kế tiếp hoặc `null`. |
| `setNextException(SQLException)` | `void` | **Nối thêm vào cuối** chain JDBC. |
| `iterator()` | `Iterator<Throwable>` | SQLExceptions và các causes trong chuỗi. |
| `getCause()` | `Throwable` | Kế thừa từ `Throwable`. |
| `getSuppressed()` | `Throwable[]` | Lỗi bị suppressed, thường từ cleanup. |
| `getClass()` | `Class<?>` | Subclass Java của lỗi. |
| `printStackTrace()` | `void` | Có thể hữu ích trong test, nhưng cần hạn chế dữ liệu ở production. |

Những constructor có reason, SQLState, vendor code, cause giúp tạo ngoại lệ với metadata đầy đủ. Nếu chỉ tạo `new SQLException("some error")` thì SQLState mặc định có thể `null` và vendor code thường bằng `0`. Điều đó **không có nghĩa thao tác SQL thành công**.

### 2.1. SQLException là checked exception

Một method JDBC thường `throws SQLException`. Ứng dụng xử lý bằng:

```java
// Mảnh code giả định có DataSource dataSource đã cấu hình.
try (Connection connection = dataSource.getConnection()) {
    // Làm việc với JDBC.
} catch (SQLException ex) {
    // Đọc các thuộc tính và quyết định xử lý.
    throw new IllegalStateException("Database operation failed", ex);
}
```

Giữ `ex` làm **cause** khi wrap giúp hệ thống giữ toàn bộ SQLException graph (cả next exceptions thuộc root). Đừng chỉ làm `throw new RuntimeException(ex.getMessage())` vì như vậy mất cause, stack trace, SQLState và vendor code.

## 3. SQLState: mã lỗi chuẩn hóa dạng String

SQLState thường có **5 ký tự**: hai ký tự đầu là **class** (nhóm lỗi), ba ký tự sau là **subclass** (chi tiết). JDBC dùng mã theo quy ước X/Open hoặc SQL standard, tùy driver. Không parse SQLState thành số nguyên: một số code bắt đầu bằng `0` và một số chứa chữ.

```java
// Mảnh code trong method có SQLException ex.
String state = ex.getSQLState();
String group = state != null && state.length() == 5
        ? state.substring(0, 2) : "unknown";
```

Với `"23505"`, class = `"23"`, subclass = `"505"`. Với `"08006"`, class = `"08"`, subclass = `"006"`. Với `"HY000"`, class = `"HY"`. Tất cả phải được giữ dưới dạng `String`.

### 3.1. Những class thường gặp

| SQLState class | Ý nghĩa khái quát | Điểm cần nhớ |
| --- | --- | --- |
| `00` | Successful completion | Không thay `null` bằng `00000` khi driver không cung cấp state. |
| `01` | Warning | Thường xem thêm `SQLWarning`. |
| `02` | No data | `ResultSet.next()==false` không có nghĩa sẽ ném SQLException. |
| `08` | Connection exception | Không suy ra retry an toàn nếu outcome của transaction chưa rõ. |
| `22` | Data exception | Lỗi conversion/giá trị/type; cần xem mã chi tiết. |
| `23` | Integrity constraint violation | Duplicate key, foreign key, check constraint… |
| `28` | Invalid authorization specification | Xem access/credentials, không log password. |
| `40` | Transaction rollback | Deadlock/serialization/rollback; cân nhắc retry **toàn transaction**. |
| `42` | Syntax error or access rule violation | Có thể là schema, quyền hoặc cú pháp, không chỉ typo SQL. |
| `HY` | X/Open/ODBC-style diagnostics, như `HY000` | Không mặc định mọi vendor dùng cùng semantics. |

**Đừng hardcode một bảng “SQLState → số lần retry” cho mọi DBMS.** Cùng SQLState class có thể được các driver thể hiện bằng subclass khác nhau; vendor-specific codes, Java subclass và transaction context quan trọng không kém.

### 3.2. Khi SQLState null hoặc khác độ dài 5

Không viết:

```java
// Sai nếu state == null:
String family = ex.getSQLState().substring(0, 2);
```

Dùng một helper an toàn:

```java
static String stateClass(SQLException error) {
    String state = error.getSQLState();
    return state != null && state.length() == 5
            ? state.substring(0, 2) : "unknown";
}
```

SQLState khác 5 ký tự có thể do code tạo ngoại lệ bằng constructor không chuẩn hoặc driver cung cấp dữ liệu bất thường. Log nó như thông tin cần điều tra, không tự sửa cắt/gộp chuỗi làm biến mất dấu hiệu bất thường.

## 4. Vendor error code: riêng từng DBMS/driver

`SQLException.getErrorCode()` trả một số nguyên `int`, do vendor quy định. Nó **không phải một mã JDBC toàn cục**.

```java
// Mảnh code trong catch(SQLException ex):
System.out.println("state=" + ex.getSQLState());
System.out.println("vendorCode=" + ex.getErrorCode());
```

Những điều cần tránh:

- `getErrorCode() == 0` không có nghĩa database đã thành công: nhiều constructors dùng mặc định `0`.
- Số code giống nhau từ PostgreSQL/MySQL/SQL Server/Oracle Database không được giả định có cùng nghĩa.
- Không kết luận một vendor code thuộc class SQLState nào khi chưa kiểm tra driver documentation.
- Đừng xây business rules bằng cách tìm substring trong English message của SQLException.
- Khi nâng JDBC driver hoặc database, cần regression tests cho cách mã hóa lỗi.

Một event chẩn đoán nên giữ **DBMS name/version, JDBC driver name/version, SQLState, vendor code, Java exception class và tên operation**. Nếu dùng log, đừng ghi nguyên JDBC URL có password hoặc SQL bind parameters mang PII.

### 4.1. Hai lỗi trong cùng chain có thể khác SQLState/vendor code

Một lỗi root thường chỉ báo `"batch failed"`/`"connection failed"`, trong khi `getNextException()` chứa thêm lỗi constraint, SQL conversion hoặc timeout cụ thể. Do đó cần duyệt **từng node**, không chỉ root.

## 5. Duyệt SQLException.getNextException()

`SQLException.getNextException()` trả SQLException được liên kết bằng `setNextException()`. Mã duyệt:

```java
// Mảnh code đặt trong catch(SQLException ex).
for (SQLException current = ex;
     current != null;
     current = current.getNextException()) {

    System.out.println("type=" + current.getClass().getName());
    System.out.println("SQLState=" + current.getSQLState());
    System.out.println("vendorCode=" + current.getErrorCode());
}
```

Mỗi node có thể mang SQLState và vendor code riêng. Đừng thay vòng này bằng `for(Throwable cause=ex.getCause();...)` nếu mục đích là tìm các JDBC next exceptions.

### 5.1. setNextException thêm vào cuối chain

```java
SQLException root = new SQLException("root", "HY000", 10);
SQLException a = new SQLException("first", "23505", 20);
SQLException b = new SQLException("second", "08006", 30);
root.setNextException(a);
root.setNextException(b);

// root -> a -> b
// root.getNextException() == a
// a.getNextException() == b
```

`setNextException` **không ghi đè nút a** khi thêm b. Trong ứng dụng thông thường, bạn **đọc** chain do driver tạo; `setNextException` chủ yếu dành cho driver/framework hoặc unit tests.

### 5.2. Duyệt phòng thủ cho logger

Một trình logging thu thập lỗi từ nhiều vendor nên có **giới hạn số node và identity tracking** để tránh log quá lớn hoặc bị kẹt với một graph bị tạo sai. Đây là policy ứng dụng, **không phải giới hạn của JDBC**.

```java
// Mảnh helper trong class, cần imports java.util.Set,
// java.util.Collections và java.util.IdentityHashMap.
static void logNextChainSafely(SQLException root) {
    Set<SQLException> visited =
            Collections.newSetFromMap(new IdentityHashMap<>());
    int count = 0;
    for (SQLException current = root;
         current != null && count < 64;
         current = current.getNextException()) {
        if (!visited.add(current)) {
            System.out.println("duplicate/cyclic SQL exception node");
            return;
        }
        count++;
        System.out.println(current.getClass().getSimpleName()
                + " state=" + current.getSQLState()
                + " code=" + current.getErrorCode());
    }
}
```

`IdentityHashMap` so sánh object identity. Giới hạn `64` là lựa chọn minh họa. Trong production, nên ghi rõ khi chain bị cắt bớt, tránh giả vờ đã in toàn bộ diagnostics.

## 6. Duyệt bằng SQLException.iterator()

`SQLException implements Iterable<Throwable>`. Vì vậy, đoạn mã sau hợp lệ trong Java 17+:

```java
for (Throwable item : ex) {
    if (item instanceof SQLException sql) {
        System.out.println("state=" + sql.getSQLState());
        System.out.println("code=" + sql.getErrorCode());
    } else {
        System.out.println("causeType=" + item.getClass().getName());
    }
}
```

**Kiểu phần tử là `Throwable`, không phải `SQLException`.** Vòng `for (SQLException item : ex)` sẽ không biên dịch vì generic type của iterator không tương thích.

Theo Javadoc Java SE 26, iterator duyệt **mỗi SQLException trong chuỗi cùng các nguyên nhân phía dưới (nếu có)**. Ví dụ một root có cause là IOException, next SQLException có cause là IllegalStateException và next cuối không cause sẽ tạo dãy:

```text
SQLException root
IOException cause of root
SQLException next #1
IllegalStateException cause of next #1
SQLException next #2
```

**Suppressed exceptions không nằm tự động trong dãy này.** Nếu cần lỗi đóng tài nguyên, đọc `getSuppressed()` riêng.

### 6.1. Khi nào chọn iterator, khi nào chọn getNextException?

- Chỉ cần SQLState/vendor code của các lỗi JDBC: dùng vòng `getNextException()` rõ ràng, type tĩnh là `SQLException`.
- Cần tìm thêm `IOException`, `IllegalStateException` hoặc nguyên nhân do driver chèn vào: dùng `for(Throwable t : ex)`.
- Cần kiểm tra lỗi cleanup: duyệt `getSuppressed()` của root và các Throwable quan trọng.
- Nếu dùng đồng thời iterator **và** vòng next/cause để log, chú ý cùng một exception sẽ xuất hiện nhiều lần. Đừng đếm trùng thành nhiều sự cố độc lập.

### 6.2. Cause không nhất thiết là một SQLException

`getCause()` có kiểu `Throwable`. Nó có thể là `IOException`, `RuntimeException` hoặc bất kỳ subclass `Throwable` hợp lệ. Vì thế, không ép cast:

```java
// Sai nếu cause không phải SQLException:
SQLException cause = (SQLException) ex.getCause();
```

Hãy đọc type và dùng `instanceof` khi cần xử lý SQL-specific fields.

## 7. Suppressed exceptions với try-with-resources

`Throwable.getSuppressed()` trả những lỗi phụ đã được gắn bằng `addSuppressed()`. Trong try-with-resources, một lỗi từ khối `try` có thể là primary; lỗi từ `close()` của `ResultSet`, `Statement` hoặc `Connection` có thể bị suppressed.

```java
// Mảnh code tích hợp, cần DataSource thật:
try (Connection connection = dataSource.getConnection();
     Statement statement = connection.createStatement()) {
    statement.executeUpdate("UPDATE sample SET value = 1");
} catch (SQLException primary) {
    for (Throwable suppressed : primary.getSuppressed()) {
        // Ghi type/cause theo chính sách bảo mật; không log secret.
    }
    throw primary;
}
```

Lỗi suppressed **không tự thay thế primary**, cũng không phải `getNextException()`. Nếu chỉ log SQLState root và bỏ suppressed, bạn có thể không phát hiện một `close()` bị lỗi.

**Không lấy `getSuppressed()` từ root rồi kết luận toàn bộ graph không có suppressed khác**: nguyên nhân hoặc next SQLException cũng có thể mang suppressed riêng. Khi cần audit đầy đủ, một trình duyệt graph có identity set và depth limit phải kiểm tra từng Throwable node.

## 8. Ví dụ Java 17+ hoàn chỉnh: next chain, iterator, cause, suppressed

Chương trình sau **không cần database**. Nó chủ động tạo một root SQLException, gắn hai SQLExceptions phía sau, thêm causes/suppressed, rồi in các thuộc tính để quan sát thứ tự duyệt. Nó còn tạo `SQLWarning` và `BatchUpdateException` để kiểm tra những API liên quan.

Các SQLState `HY000`, `23505`, `08006` và vendor codes `9001/9002/9003` trong demo **do code tự đặt**; không khẳng định mọi DBMS trả những mã này trong hoàn cảnh mô tả.

### 8.1. File `SQLExceptionChainDemo.java`

```java
import java.io.IOException;
import java.sql.BatchUpdateException;
import java.sql.SQLException;
import java.sql.SQLIntegrityConstraintViolationException;
import java.sql.SQLTransientConnectionException;
import java.sql.SQLWarning;
import java.sql.Statement;
import java.util.Arrays;

public final class SQLExceptionChainDemo {
    private static String sqlStateClass(SQLException error) {
        String state = error.getSQLState();
        return state != null && state.length() == 5
                ? state.substring(0, 2) : "unknown";
    }

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=PASS");
    }

    public static void main(String[] args) {
        SQLException root = new SQLException(
                "write failed", "HY000", 9001,
                new IOException("socket read stopped"));
        SQLException duplicate = new SQLIntegrityConstraintViolationException(
                "duplicate key", "23505", 9002,
                new IllegalStateException("unique-key collision"));
        SQLException temporary = new SQLTransientConnectionException(
                "connection unavailable", "08006", 9003);

        root.setNextException(duplicate);
        root.setNextException(temporary);
        root.addSuppressed(new IOException("statement close failed"));

        int nextCount = 0;
        for (SQLException current = root; current != null;
             current = current.getNextException()) {
            System.out.println("next[" + nextCount + "]="
                    + current.getClass().getSimpleName()
                    + "|SQLState=" + current.getSQLState()
                    + "|class=" + sqlStateClass(current)
                    + "|vendorCode=" + current.getErrorCode());
            nextCount++;
        }

        int iteratorCount = 0;
        for (Throwable item : root) {
            String kind = item instanceof SQLException sql
                    ? "SQLException:" + sql.getSQLState()
                    : item.getClass().getSimpleName();
            System.out.println("iter[" + iteratorCount + "]=" + kind);
            iteratorCount++;
        }

        check("nextCount", nextCount == 3);
        check("iteratorCount", iteratorCount == 5);
        check("rootCause", root.getCause() instanceof IOException);
        check("suppressedCount", root.getSuppressed().length == 1);
        check("lastNext", duplicate.getNextException() == temporary);

        SQLWarning warning = new SQLWarning("nonfatal notice", "01000", 7001);
        warning.setNextWarning(new SQLWarning("second notice", "01004", 7002));
        check("warningChain", "01004".equals(
                warning.getNextWarning().getSQLState()));

        BatchUpdateException batch = new BatchUpdateException(
                "batch incomplete", "23000", 9010,
                new long[] {1, Statement.EXECUTE_FAILED, Statement.SUCCESS_NO_INFO},
                new IOException("batch operation aborted"));
        System.out.println("batchCounts="
                + Arrays.toString(batch.getLargeUpdateCounts()));
        check("batchCountsLength", batch.getLargeUpdateCounts().length == 3);
    }
}
```

### 8.2. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 SQLExceptionChainDemo.java
java SQLExceptionChainDemo
```

Đã thực hiện đúng hai lệnh với JDK 24 (compile target Java 17), không cần vendor JDBC driver hoặc DBMS.

### 8.3. Stdout chính xác đã kiểm chứng

```text
next[0]=SQLException|SQLState=HY000|class=HY|vendorCode=9001
next[1]=SQLIntegrityConstraintViolationException|SQLState=23505|class=23|vendorCode=9002
next[2]=SQLTransientConnectionException|SQLState=08006|class=08|vendorCode=9003
iter[0]=SQLException:HY000
iter[1]=IOException
iter[2]=SQLException:23505
iter[3]=IllegalStateException
iter[4]=SQLException:08006
nextCount=PASS
iteratorCount=PASS
rootCause=PASS
suppressedCount=PASS
lastNext=PASS
warningChain=PASS
batchCounts=[1, -3, -2]
batchCountsLength=PASS
```

**Tổng 16 dòng stdout; các assertions đều PASS.**

### 8.4. Phân tích kết quả

- `next[0..2]` cho thấy root → duplicate exception → temporary connection exception; `setNextException` nối vào cuối.
- `iter[0..4]` cho thấy iterator duyệt xen kẽ mỗi SQLException với cause của nó, đúng thứ tự đã kiểm chứng: root, IOException, duplicate, IllegalStateException, temporary.
- `nextCount=PASS` chứng minh có đúng ba SQLExceptions trong next chain, **không đếm causes**.
- `iteratorCount=PASS` chứng minh iterator duyệt năm Throwable objects, gồm **hai causes**.
- `rootCause=PASS` và `suppressedCount=PASS` phân biệt cause với suppressed.
- `lastNext=PASS` xác nhận `duplicate.getNextException()==temporary`.
- `warningChain=PASS` kiểm chứng `SQLWarning.getNextWarning()`.
- `batchCounts=[1, -3, -2]` là kết quả constants JDBC, không phải số bản ghi âm. Các marker -3/-2 được giải thích riêng ở mục 10.

Không sử dụng stdout này làm kết quả một database thật: tất cả SQLException objects được tạo trong chương trình.

## 9. SQLWarning: cảnh báo thường không được ném

`SQLWarning extends SQLException`, nhưng JDBC thường **gắn warnings vào Connection/Statement/ResultSet** để ứng dụng có thể đọc mà không làm thao tác chính thất bại.

Có các method:

- `Connection.getWarnings()` và `clearWarnings()`.
- `Statement.getWarnings()` và `clearWarnings()`.
- `ResultSet.getWarnings()` và `clearWarnings()`.
- `SQLWarning.getNextWarning()` và `setNextWarning()`.

Ví dụ dùng với `Statement` còn mở:

```java
SQLWarning warning = statement.getWarnings();
for (SQLWarning current = warning;
     current != null;
     current = current.getNextWarning()) {
    System.out.println(current.getSQLState());
    System.out.println(current.getErrorCode());
}
statement.clearWarnings();
```

Đây là **mảnh code tích hợp**, không phải chương trình độc lập; `statement` phải là một JDBC Statement thật đang mở. Đọc warning trước khi clear. Việc có `SQLWarning` không đồng nghĩa throw một `SQLException`, nhưng trong import/data-processing systems warning có thể báo conversion, truncation hoặc hoạt động không như dự kiến.

`DataTruncation` extends `SQLWarning`, nhưng hành vi báo warning/exception cho dữ liệu bị cắt khác nhau theo driver/DBMS. Đừng chỉ dựa vào caught exceptions để khẳng định không có dữ liệu bị truncation.

## 10. BatchUpdateException và update counts

`BatchUpdateException extends SQLException`, được dùng khi JDBC batch gặp lỗi. Ngoài `getSQLState()` và `getErrorCode()`, nó có:

- `getUpdateCounts()` trả `int[]`.
- `getLargeUpdateCounts()` trả `long[]`, nên dùng với `executeLargeBatch()` hoặc khi số rows có thể vượt `Integer.MAX_VALUE`.

Hai JDBC constants:

| Constant | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `Statement.SUCCESS_NO_INFO` | `-2` | Command thành công nhưng driver không cung cấp row count. |
| `Statement.EXECUTE_FAILED` | `-3` | Command failed (thường trong batch driver tiếp tục xử lý sau lỗi). |

Trong demo, `batchCounts=[1, -3, -2]` nghĩa là một command ảnh hưởng 1 row, một command failed, một command thành công nhưng row count không biết. Nó **không** có nghĩa “1 trừ 3 trừ 2 = -4 rows”.

```java
// Mảnh code trong catch(BatchUpdateException ex):
long[] counts = ex.getLargeUpdateCounts();
for (int i = 0; i < counts.length; i++) {
    long c = counts[i];
    if (c == Statement.EXECUTE_FAILED) {
        System.out.println("batch[" + i + "]: FAILED");
    } else if (c == Statement.SUCCESS_NO_INFO) {
        System.out.println("batch[" + i + "]: SUCCESS_NO_INFO");
    } else {
        System.out.println("batch[" + i + "]: rows=" + c);
    }
}
```

JDBC driver có thể **dừng** hoặc **tiếp tục** sau command lỗi; nếu dừng, counts array có thể chỉ chứa commands đã xử lý trước lỗi. Nếu tiếp tục, có thể có marker `EXECUTE_FAILED`. Không suy ra cả batch tự rollback chỉ vì `BatchUpdateException` được ném; transaction/autoCommit policy vẫn quyết định commit/rollback.

**`getNextException` là chuỗi các lỗi**, còn `getLargeUpdateCounts` là dữ liệu về **các commands**. Không dùng số lượng chained exceptions thay cho số failed rows.

## 11. Subclass SQLException và quyết định retry

JDBC có các subclasses hiện hành:

| Loại | Ý nghĩa | Cách xử lý cần cân nhắc |
| --- | --- | --- |
| `SQLTransientException` | Lỗi có thể thành công khi retry mà không cần thay đổi app-level state. | Chỉ retry khi operation an toàn/idempotent, có backoff và retry budget. |
| `SQLTransientConnectionException` | Vấn đề transient liên quan connection, thường SQLState class 08. | Kiểm tra connection và transaction outcome; đừng retry write mù. |
| `SQLNonTransientException` | Retry giống hệt không tự thành công nếu nguyên nhân chưa sửa. | Sửa SQL/schema/permission/data/config. |
| `SQLIntegrityConstraintViolationException` | Vi phạm constraint, thường class 23 hoặc vendor-specific. | Xử lý duplicate/foreign key/check nghiệp vụ. |
| `SQLSyntaxErrorException` | Syntax hoặc access rule, thường class 42 hoặc vendor-specific. | Sửa SQL/schema/quyền. |
| `SQLInvalidAuthorizationSpecException` | Authentication/authorization, thường class 28. | Kiểm tra credentials/quyền một cách bảo mật. |
| `SQLRecoverableException` | Cần recovery steps để có khả năng chạy lại. | Ít nhất đóng connection hỏng và lấy connection mới; có thể retry toàn transaction. |
| `SQLTimeoutException` | Thao tác JDBC/statement timeout. | Outcome có thể không rõ; không lập tức lặp lại write. |
| `SQLTransactionRollbackException` | Lỗi transaction rollback (thường class 40). | Có thể retry cả transaction với policy phù hợp. |
| `SQLDataException` | Lỗi dữ liệu/type/conversion. | Kiểm tra input và SQL schema. |
| `SQLFeatureNotSupportedException` | Driver không hỗ trợ một JDBC feature. | Dùng feature được support; retry giống hệt không giúp. |

**Không tự quyết định retry dựa trên SQLState hai ký tự đơn lẻ.** Có thể một driver ném generic `SQLException` thay cho một subclass cụ thể, hoặc dùng vendor-specific SQLState. Khi kết nối đứt sau câu lệnh ghi, ứng dụng có thể không biết DB đã commit hay chưa (*ambiguous commit outcome*). Retry không có idempotency key có thể ghi trùng.

`SQLRecoverableException` theo Javadoc yêu cầu recovery steps; tối thiểu đóng connection hiện tại và mở connection khác. Retry toàn transaction có thể thích hợp, nhưng không phải cách mặc định cho mọi hệ thống.

### 11.1. Không retry vô hạn

```java
// Minh họa SAI — pseudocode, không nên đưa vào code thật:
while (true) {
    try {
        writeToDatabase();
        break;
    } catch (SQLException ex) {
        // Không kiểm tra loại lỗi, idempotence hoặc transaction outcome.
    }
}
```

Một retry policy thực tế cần xác định lỗi có thể hồi phục, số lần và thời gian chờ tối đa, backoff/jitter, idempotency, trạng thái transaction, circuit breaker và recovery khi connection hỏng.

## 12. Một mẫu catch an toàn trong ứng dụng thực

```java
// Mảnh code có DataSource dataSource, long accountId,
// bảng account(id,status) trong database thật:
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
             "UPDATE account SET status = ? WHERE id = ?")) {
    ps.setString(1, "ACTIVE");
    ps.setLong(2, accountId);
    ps.executeUpdate();
} catch (SQLException ex) {
    // Log SQLState, vendor code, JDBC next/cause graph có redaction.
    reportJdbcFailure(ex);
    throw new IllegalStateException("Cannot update account", ex);
}
```

`reportJdbcFailure` là helper giả định của ứng dụng, không phải method JDBC. Đoạn này **không chạy độc lập** nếu chưa có DataSource/schema/helper. Giữ exception làm cause khi wrap; không làm:

```java
// Sai vì làm mất exception graph:
throw new IllegalStateException(ex.getMessage());
```

### 12.1. Gợi ý structured logging

Một event có thể chứa:

```text
event=jdbc.operation.failed
operation=update-account
exceptionType=java.sql.SQLIntegrityConstraintViolationException
sqlState=23505
sqlStateClass=23
vendorErrorCode=[vendor-specific]
database=[database-product/version]
driver=[jdbc-driver/version]
correlationId=[safe-request-id]
```

Các giá trị trong dấu ngoặc vuông phải được hệ thống thật cung cấp; đây là **mẫu log**, không phải một stdout đã chạy. Không ghi password, token, raw SQL bind parameters, access tokens hoặc connection URL có credentials.

Nếu cần log `getMessage()` hoặc stack trace, dùng sink có quyền truy cập phù hợp, redaction và rate limiting. Lỗi vendor có thể đưa SQL literals hoặc thông tin nhạy cảm vào message.

### 12.2. Khi cần thu thập toàn bộ exception graph

Một logger chuyên sâu có thể:

1. Duyệt next exceptions với identity set + giới hạn số node.
2. Với mỗi SQLException, lưu class, SQLState, vendor code.
3. Duyệt cause chain hoặc dùng JDBC iterator theo thứ tự chuẩn.
4. Duyệt `getSuppressed()` cho root và các Throwable quan trọng.
5. Không đếm cùng một Throwable object hai lần.
6. Cắt ngắn và đánh dấu graph nếu vượt giới hạn.
7. Không làm thay đổi chain bằng `setNextException`/`initCause`.
8. Bảo vệ text fields, không render nguyên exception graph ra public API.

Trong nhiều trường hợp, dùng logging framework để log original `SQLException` object sau khi gắn structured attributes là đủ; không cần viết một custom Throwable graph serializer phức tạp.

## 13. Chẩn đoán lỗi JDBC theo checklist

Khi nhận SQLException thực tế, lần lượt:

1. **Thao tác nào thất bại?** `connect`, `prepareStatement`, `executeQuery`, `executeUpdate`, `executeBatch`, `commit`, `rollback` hay `close`?
2. **Subclass gì?** `SQLException` generic, `SQLTransientException`, `BatchUpdateException`, hoặc vendor subclass?
3. **SQLState có hợp lệ?** Có `null` không? Hai ký tự đầu thuộc nhóm nào?
4. **Vendor code là gì?** Có `0` không? Mapping tương ứng với DB vendor/version nào?
5. **Có next exceptions?** Duyệt `getNextException()` cho từng SQLException và mã của nó.
6. **Có cause chain?** `getCause()` có IOException/driver exception hay lỗi sâu khác không?
7. **Có suppressed?** Lỗi `close`/resource cleanup có làm điều tra khó hơn không?
8. **Có warning?** Nếu job có dữ liệu bị cắt/chuyển đổi, đọc `getWarnings`.
9. **Có batch counts?** Với BatchUpdateException, kiểm tra `getLargeUpdateCounts` và policy driver.
10. **Transaction có chắc rollback/commit?** Nếu outcome ambiguous, không retry thao tác ghi bừa bãi.
11. **Có cần thay connection?** Nếu SQLRecoverableException hoặc connection không lành mạnh.
12. **Có thể log mà không lộ dữ liệu?** Dùng redaction, correlation ID và logs bảo mật.

### 13.1. Lỗi network và kết quả commit chưa chắc chắn

Nếu client gửi COMMIT rồi đứt kết nối trước khi nhận phản hồi, exception có thể báo lỗi connection nhưng **không chứng minh server chưa commit**. Một SQLState class `08` không làm biến mất rủi ro ghi trùng. Đối với thanh toán/đặt hàng/giao dịch quan trọng, thiết kế idempotency keys, unique constraints, transaction reconciliation hoặc outbox pattern là cần thiết.

SQLState/vendor code hỗ trợ chẩn đoán kỹ thuật, không thay thế business transaction semantics.

### 13.2. Thông tin nên đưa vào báo cáo incident

- Thời điểm, correlation ID, operation name.
- DBMS/version, driver/version, JDK version, connection pool context.
- Java exception subclass và SQLState/vendor code từng node quan trọng.
- Cause/suppressed types.
- Transaction boundary và retry attempts (đã kiểm soát).
- Lỗi ở prepare/execute/commit/close, hay ở tầng mạng.
- Giải pháp/mitigation được xác minh chứ không chỉ suy đoán theo message.

Không tự đưa vào báo cáo secret, token, PII, toàn bộ SQL data hoặc raw credentials.

## 14. Test với DBMS thật — không gán mã giả lập thành vendor code

Ví dụ mục 8 tạo exceptions **bằng Java constructors**, nên xác minh cấu trúc API, **chưa xác minh SQLState thực tế của database**. Nếu cần regression tests với DBMS cụ thể:

| Case | Môi trường test | Điều cần ghi |
| --- | --- | --- |
| Unique constraint violation | Bảng sandbox có UNIQUE index | Subclass, SQLState, vendor code, next/causes. |
| Foreign key violation | Bảng sandbox có FK | Tương tự; không mặc định code giống unique. |
| SQL syntax/access | SQL cố ý sai trong sandbox | Class `42` hay code vendor observed. |
| Authorization failure | Test user có quyền hạn hạn chế | SQLState/vendor, không log password. |
| Network interruption | Fault injection có kiểm soát | Cause chain, connection health, outcome ambiguity. |
| Batch partial failure | Batch chứa một command lỗi | BatchUpdateException counts, có tiếp tục sau fail không. |
| Transaction rollback | Deadlock/serialization được dựng an toàn | SQLState 40/subclass, rollback và retry policy. |
| Warning/truncation | Schema/cấu hình tạo warning | SQLWarning/getNextWarning, raw data correctness. |
| Resource close error | Test double hoặc mock driver | getSuppressed không mất primary. |

Không chạy deadlock/network fault trên production database. Với mỗi kết quả, lưu DBMS + version + driver + version + schema + operation + observed SQLState/vendor. Nếu driver không báo class như mong đợi, ghi kết quả thực thay vì sửa ví dụ để ép trùng một vendor khác.

## 15. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Chỉ log `getMessage()` | Thiếu SQLState, vendor code, chain, cause, suppressed. | Log có cấu trúc và context. |
| `getNextException()==getCause()` | Hai quan hệ khác nhau. | Duyệt riêng hoặc dùng iterator cho SQL+cause. |
| Chỉ xem root SQLState | Node sau có mã cụ thể hơn. | Duyệt đủ next chain. |
| Chỉ xem cause mà quên next | Nhiều SQLExceptions không nằm trong cause chain. | Dùng `getNextException`. |
| Iterator tự có suppressed | Không phải vậy. | Duyệt `getSuppressed()` riêng. |
| `for(SQLException e : root)` | Iterator trả `Throwable`. | Dùng `for(Throwable t : root)`. |
| SQLState luôn có 5 ký tự và non-null | Có thể `null` hoặc không chuẩn. | Validate trước substring. |
| Parse SQLState thành int | Mất leading zero, `HY000` không parse được. | Dùng String. |
| Vendor code `0` là success | Có thể chỉ không có mã được cung cấp. | Kiểm tra driver info. |
| Cùng vendor code cho mọi database | Namespace phụ thuộc vendor. | Kết hợp DBMS/driver/version. |
| Retry mọi lỗi class 08/40 | Có thể outcome không rõ hoặc operation không idempotent. | Policy retry và transaction logic. |
| Bỏ cause khi wrap | Mất stack trace và SQL context. | Wrap bằng constructor có cause. |
| SQLWarning tự throw khi warning | Warnings thường được lưu trong JDBC object. | Đọc `getWarnings()`. |
| `-2` hoặc `-3` là row counts âm | Đây là marker của batch. | Dùng `Statement` constants. |
| Batch failure tự rollback | Không được JDBC bảo đảm. | Quản lý transactions riêng. |
| Không đọc suppressed | Bỏ thông tin lỗi cleanup. | `getSuppressed()`. |
| In raw JDBC URL hoặc SQL bind values | Rò secrets/PII. | Redact và phân quyền. |
| Log không giới hạn khi chain quá dài | Tăng tải và khó tìm lỗi chính. | Giới hạn depth/count. |
| Hardcode English exception message | Message khác nhau theo driver/version/locale. | Dùng subclass/state/vendor/context. |

## 16. Checklist cho ứng dụng Java JDBC

- [ ] Có đọc và log `getClass()`/`getSQLState()`/`getErrorCode()` của root?
- [ ] Có phân biệt SQLState null, vendor code bằng 0?
- [ ] Có duyệt `getNextException()` để không bỏ linked errors?
- [ ] Có đọc `getCause()` hoặc dùng JDBC iterator với đúng `Throwable` type?
- [ ] Có duyệt `getSuppressed()` khi muốn thấy close errors?
- [ ] Nếu cần phân loại state, có kiểm tra length 5 trước substring?
- [ ] Mã vendor được diễn giải trong namespace của DBMS/driver cụ thể?
- [ ] Có tránh parse English message thành business logic?
- [ ] Đã xem `SQLTransient`/`SQLNonTransient`/`SQLRecoverable` subclass?
- [ ] Retry có budget, backoff và bảo vệ idempotency?
- [ ] Outcome của transaction đã rõ trước khi retry write?
- [ ] Với `BatchUpdateException`, có kiểm tra `getLargeUpdateCounts`?
- [ ] Với `SQLWarning`, có đọc `getWarnings()` đúng thời điểm?
- [ ] Có giữ original cause khi wrap exception?
- [ ] Logs có giới hạn số nodes, sampling/redaction và quyền truy cập?
- [ ] Test Java-only tự tạo exception chain được chạy với target JDK?
- [ ] Integration tests trên DBMS/driver thật được báo cáo riêng?
- [ ] Không lưu passwords, token, data nhạy cảm trong error reports?

## 17. Bài tập thực hành

**A — Next chain:** thêm SQLException thứ tư có state `"22001"`, rồi dự đoán `nextCount` và `iteratorCount`. Khi không có cause mới, chúng tăng bao nhiêu?

**B — Cause chain:** thêm IOException làm cause của IllegalStateException ở `duplicate`. Vòng `getNextException` có đếm thêm không? Vòng iterator thay đổi thế nào?

**C — Suppressed:** thêm một suppressed exception vào root. Vì sao `root.getSuppressed().length` tăng mà iterator count không tăng?

**D — Null SQLState:** tạo `new SQLException("unknown database problem")`. Kiểm tra `getSQLState()==null` và `getErrorCode()==0`; sửa formatter để không NPE.

**E — SQLState class:** thử `"08006"` và `"HY000"`. Vì sao không nên `Integer.parseInt` và tại sao phải dùng `substring(0,2)`?

**F — SQLWarning:** thêm warning thứ ba bằng `setNextWarning` rồi duyệt `getNextWarning()`. Có cần throw exception để thấy warnings không?

**G — Batch counts:** thay `getLargeUpdateCounts` thành một long[] có `SUCCESS_NO_INFO`/`EXECUTE_FAILED`, viết formatter không diễn giải chúng thành row counts.

**H — Logging:** thêm identity set và limit 32 để thu thập exceptions + causes + suppressed mà không đếm trùng. Kiểm tra không log raw messages chứa bí mật.

**I — DB integration:** trong DBMS sandbox, cố ý vi phạm UNIQUE index và ghi observed subclass, SQLState, vendor code. Có giống mã giả lập của demo không?

**J — Retry:** mô tả một COMMIT bị mất phản hồi do connection drop; làm thế nào tránh xử lý đơn hàng hai lần?

## 18. Câu hỏi tự kiểm tra

**1.** `SQLException.getNextException` có giống `Throwable.getCause` không? — **Không.** Next nối các lỗi JDBC; cause chỉ nguyên nhân bên dưới của một Throwable.

**2.** `SQLException.iterator` trả kiểu gì? — **`Iterator<Throwable>`**. Có thể duyệt SQLExceptions và causes bằng enhanced-for, không chỉ SQLException.

**3.** Vì sao cần `getSuppressed()` riêng? — Vì iterator của SQLException không tự liệt kê suppressed exceptions, thường liên quan cleanup lỗi.

**4.** SQLState `08006` thuộc class nào? — Class `08`, nhóm connection exception theo quy ước thông thường. Không có nghĩa retry an toàn cho mọi write.

**5.** SQLState `HY000` có parse thành số nguyên được không? — Không; SQLState là String và có thể chứa chữ.

**6.** Vendor error code `0` chứng minh operation thành công? — Không; nó có thể là default nếu không có mã được cung cấp.

**7.** `SQLWarning` luôn được throw? — Không; thường lấy từ `Connection/Statement/ResultSet.getWarnings`.

**8.** `BatchUpdateException.getLargeUpdateCounts` chứa -2/-3 nghĩa gì? — Marker `SUCCESS_NO_INFO` và `EXECUTE_FAILED`, không phải số row âm.

**9.** Đã bắt `SQLTransientConnectionException` có thể retry mọi transaction ngay? — Không, phải kiểm tra outcome, idempotence, connection state và retry policy.

**10.** Tại sao `throw new IllegalStateException(ex.getMessage())` không tốt? — Làm mất cause và exception graph; dùng constructor có `ex`.

**11.** Nếu một JDBC driver báo lỗi bằng nhiều SQLException, làm sao đọc tất cả? — Duyệt `getNextException()` hoặc `SQLException.iterator()`; xét causes và suppressed riêng nếu cần.

**12.** Demo đã chứng minh một DBMS cụ thể dùng mã `9002` cho duplicate key? — Không. Mã 9002 do chương trình tự tạo; cần chạy integration tests với vendor thật.

## 19. Tài liệu chính thức còn áp dụng

- [SQLException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): `getSQLState`, `getErrorCode`, `getNextException`, `iterator`, constructors.
- [SQLException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html): tương thích mã `--release 17`.
- [SQLWarning — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLWarning.html): warning chain và `getNextWarning`.
- [BatchUpdateException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/BatchUpdateException.html): counts và failure behavior.
- [Statement — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Statement.html): `SUCCESS_NO_INFO`, `EXECUTE_FAILED`, `executeLargeBatch`.
- [SQLTransientException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransientException.html): transient behavior.
- [SQLNonTransientException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLNonTransientException.html): nontransient behavior.
- [SQLRecoverableException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLRecoverableException.html): recovery và connection mới.
- [Throwable — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html): causes, suppressed exceptions và stack traces.
- [java.sql package — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/package-summary.html): hệ subclasses JDBC hiện hành.

**Ghi nhớ:** `SQLException` có **SQLState**, **vendor-specific error code** và **getNextException** khác với **getCause**. `SQLException.iterator()` duyệt SQLExceptions cùng causes, còn `getSuppressed()` cần xem riêng. Khi xử lý lỗi thật, kết hợp exception subclass, DBMS/driver version, operation phase, transaction outcome và security-safe logging; đừng retry vô hạn hoặc suy luận từ English message.
