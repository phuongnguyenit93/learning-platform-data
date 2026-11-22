# SQLXML: free(), ranh giới giao dịch và tránh dùng sau khi giải phóng

## Mục tiêu học tập

Đối tượng `java.sql.SQLXML` không phải một `String` lưu XML có thể giữ mãi trong bộ nhớ ứng dụng. JDBC có thể triển khai SQLXML như **một locator/handle gắn với connection và transaction**, giữ tài nguyên tại driver hoặc cơ sở dữ liệu. Một lỗi thường gặp là lấy SQLXML từ `ResultSet`, đóng connection hoặc gọi `free()`, rồi tiếp tục đọc hay bind nó trong một bước khác.

Bài này tập trung vào **quyền sở hữu, thời điểm kết thúc sử dụng, ranh giới giao dịch và việc phòng ngừa use-after-free**. Sau khi học, bạn sẽ:

- Giải thích hợp đồng của `SQLXML.free()`: giải phóng tài nguyên, không thể dùng tiếp, gọi lại là **no-op**, và lỗi `SQLException` có thể phát sinh khi giải phóng.
- Biết điều gì vẫn được phép **sau free** và điều gì phải bị từ chối; không coi `free` giống `commit` hay `Connection.close`.
- Phân biệt **giới hạn do application chủ động kết thúc** (`free`) với **vòng đời theo transaction/connection** do driver quản lý.
- Hiểu Javadoc Java SE 26 bảo đảm SQLXML **hợp lệ trong giao dịch được tạo ra**, nhưng không hứa mọi driver hủy chính xác ngay khi `commit/rollback` hay cho phép dùng sau ranh giới đó.
- Sắp xếp đúng `createSQLXML → write → close writer/stream → setSQLXML → execute → free → commit/rollback` trong một luồng nghiệp vụ an toàn; nêu rõ những chi tiết driver-dependent.
- Đọc SQLXML từ `ResultSet.getSQLXML` trong phạm vi ResultSet, statement, connection, transaction; phân biệt SQL `NULL` với object đã free.
- Tránh giải phóng **quá sớm** trước khi driver tiêu thụ dữ liệu tại `PreparedStatement.executeUpdate`, và tránh giữ SQLXML qua request/connection-pool checkout.
- Dùng `try/finally` cho Java 17–25, hoặc một `AutoCloseable` adapter để có **suppressed exceptions** với try-with-resources.
- Biết thay đổi mới của **Java 26/JDBC 4.5**: `SQLXML extends AutoCloseable`; default `close()` gọi `free()`, trong khi `javac --release 17` vẫn cần `free` hoặc adapter.
- Chạy một chương trình **Java 17+ không cần database** với 24 kiểm thử assertions về free, transaction boundaries, premature release, stream lifecycle, closed connection và adapter.

**Phạm vi hiện hành:** `SQLXML` thuộc `java.sql` và vẫn được hỗ trợ trong Java SE 26. Chỉ dùng kiến thức còn áp dụng ngày nay; không dựa vào behavior lỗi thời, không giả định mọi driver đều giống nhau. Phần mô phỏng giao dịch được đánh dấu rõ là **test double**, không phải kết quả của một DBMS thật.

## 1. Ba khái niệm phải tách biệt: release, transaction, connection

Một workflow dùng SQLXML chịu ba loại vòng đời **khác nhau**:

| Vòng đời | Đối tượng quản lý | Sự kiện chính | Ý nghĩa |
| --- | --- | --- | --- |
| **SQLXML resource** | `SQLXML` | `free()` (hoặc `close()` ở JDK 26+) | Giải phóng tài nguyên của **chính object SQLXML**, làm object không đọc/ghi được nữa |
| **Database transaction** | `Connection` và DBMS | `commit()` / `rollback()`, autocommit | Chốt hoặc hoàn tác thay đổi SQL và kết thúc transaction theo semantics database |
| **Logical JDBC connection** | `Connection`, thường do pool cấp | `close()` | Đóng handle mà application sở hữu; với pool có thể là **trả connection về pool**, không phải đóng vật lý |

**Không đồng nhất:** `xml.free()` **không** commit, không rollback, không xóa giá trị XML đã lưu thành công trong bảng, không đóng `PreparedStatement` và không trả `Connection` về pool.

**Không đồng nhất:** `connection.commit()` **không tự bảo đảm** mọi SQLXML bị free đúng lúc, hoặc sau commit luôn đọc/ghi được với locator cũ. JDBC SQLXML lifetime gắn với transaction; ứng dụng nên giới hạn sử dụng trong phạm vi đó và free tài nguyên theo code.

**Không đồng nhất:** `connection.close()` cũng không phải cái cớ để bỏ `SQLXML.free()` trong code Java 17+. Đóng các resource đúng quyền sở hữu giúp tránh leak, kể cả khi driver có cơ chế dọn bổ sung.

### Ví dụ kiến trúc

```text
Request / Repository
    |
    +-- Connection logical handle -------------------+
    |                                                |
    |   Transaction T1                               |
    |      |                                         |
    |      +-- SQLXML object X (driver locator)       |
    |      |      |                                  |
    |      |      +-- initialize / bind / execute     |
    |      |      +-- X.free()  <-- kết thúc dùng X    |
    |      |                                         |
    |      +-- commit / rollback  <-- kết thúc T1     |
    |                                                |
    +-- Connection.close() <-- kết thúc dùng handle -+
```

Khi thiết kế API repository, hãy đặt **phạm vi SQLXML hẹp**. Đừng truyền trực tiếp `SQLXML` lên controller hoặc trả handle của nó cho một job chạy sau khi transaction đã kết thúc.

## 2. `SQLXML.free()`: hợp đồng chính xác

Chữ ký Java SE hiện hành:

```java
void free() throws SQLException;
```

Tài liệu chính thức Java SE 26 nêu:

1. `free()` đóng và giải phóng tài nguyên do object SQLXML giữ.
2. Sau khi giải phóng, SQLXML **không thể đọc hoặc ghi**.
3. Mọi lời gọi khác ngoài `free()` — và `close()` ở JDK 26+ — sẽ dẫn đến `SQLException` nếu object đã được free/closed.
4. Nếu gọi `free()` nhiều lần, các lần tiếp theo **không có thêm tác dụng (no-op)**.
5. `free()` khai báo `throws SQLException` nếu việc release lỗi; `SQLFeatureNotSupportedException` cũng được liệt kê trong Javadoc cho driver không hỗ trợ method.

Nghĩa là:

```java
SQLXML xml = connection.createSQLXML();
try {
    xml.setString("<message>Xin chào</message>");
    // Bind và execute khi XML còn hợp lệ.
} finally {
    xml.free();
}
```

Đây là **snippet tích hợp trong một method**, cần `connection` còn mở. Không nên gọi `xml.getString()` sau `finally` để kiểm tra nội dung; object đã free. Cũng không được giả định có thể gọi `setString` lần nữa để “tái sử dụng bộ nhớ”.

### 2.1. free() có idempotent không?

**Có**. Theo contract, `xml.free(); xml.free();` không khiến một giá trị đã freed trở nên hợp lệ trở lại và lần sau là no-op. Tuy nhiên, **không nên cố tình gọi lặp ở nhiều tầng code** chỉ vì hợp đồng cho phép: đó là dấu hiệu ownership không rõ.

Ví dụ thiết kế:

```java
void releaseXml(SQLXML xml) throws SQLException {
    if (xml != null) {
        xml.free();
    }
}
```

Snippet này chỉ phù hợp khi caller **thực sự sở hữu object** và chịu trách nhiệm giải phóng. Không cho cả tầng service, repository và framework cùng free một object mà không xác định owner.

### 2.2. free() không có “giá trị trả về”

`free` trả `void`. Đừng viết logic suy ra từ return value rằng dữ liệu đã commit hay rằng server đã xóa XML khỏi cột. Method nói về tài nguyên **JDBC object**, không phải về thao tác DML.

### 2.3. free() có thể lỗi

Ví dụ:

```java
try {
    xml.free();
} catch (SQLException releaseFailure) {
    // Ghi nhận lỗi giải phóng và bảo toàn nguyên nhân gốc khi thích hợp.
}
```

Đây là snippet, không có main. **Không nên catch và bỏ qua** mọi SQLException một cách vô thức. Nếu SQL operation đã thất bại trước đó, cần tránh lỗi cleanup che mất lỗi chính; mục 7 giải thích cách dùng adapter và suppressed exceptions.

## 3. Điều gì xảy ra sau khi free?

Theo Java SE 26, các lời gọi sau đều **không còn hợp lệ** trên một `SQLXML` đã free:

| Thao tác | Kết quả mong đợi theo contract sau free |
| --- | --- |
| `getString()` | `SQLException` |
| `getCharacterStream()` | `SQLException` |
| `getBinaryStream()` | `SQLException` |
| `getSource(DOMSource.class)` | `SQLException` |
| `setString(newXml)` | `SQLException` |
| `setCharacterStream()` | `SQLException` |
| `setBinaryStream()` | `SQLException` |
| `setResult(DOMResult.class)` | `SQLException` |
| `free()` lần hai | No-op |
| `close()` trên **JDK 26+** | No-op nếu đã đóng, theo `close` contract |

**Đừng dùng `free` như `clear()` của một collection**. Nó **vô hiệu hóa** chính object, không chỉ xóa text rồi cho phép ghi một lần mới. Muốn tạo nội dung XML khác, dùng `Connection.createSQLXML()` để có đối tượng mới.

### Sai và đúng

**Sai:**

```java
SQLXML xml = connection.createSQLXML();
xml.setString("<first/>");
xml.free();
xml.setString("<second/>"); // SQLException: use-after-free
```

**Đúng:**

```java
SQLXML first = connection.createSQLXML();
try {
    first.setString("<first/>");
    // Bind / execute first.
} finally {
    first.free();
}

SQLXML second = connection.createSQLXML();
try {
    second.setString("<second/>");
    // Bind / execute second.
} finally {
    second.free();
}
```

Cả hai là **snippets tích hợp**, cần Connection và statement thật. Chúng cho thấy **object ownership**, không tự chạy một câu SQL.

### Không kiểm tra “đã free chưa” bằng cách gọi getter

`SQLXML` không có method chuẩn `isFreed()` hay `isClosed()` trên Java 17. Đừng làm:

```java
try {
    xml.getString(); // Dùng để đoán object còn sống?
} catch (SQLException ignored) {
    // Coi object đã free?
}
```

Cách này sai vì `getString()` là **read API chỉ nên gọi một lần**, có thể tiêu thụ trạng thái readable; `SQLException` còn có nhiều nguyên nhân như SQL error, XML malformed, hoặc state không readable **ngay cả khi chưa free**.

Tầng ứng dụng nên dùng **scope/ownership** để tránh use-after-free, không dùng phương thức đọc làm health-check.

## 4. Đọc một lần, ghi một lần không phải điều kiện tương đương free

`SQLXML` có hai nhóm trạng thái riêng:

- **readable / not readable**
- **writable / not writable**

Các methods **đọc** gồm `getString`, `getCharacterStream`, `getBinaryStream`, `getSource`. Các methods **ghi** gồm `setString`, `setCharacterStream`, `setBinaryStream`, `setResult`.

Theo Javadoc:

- Gọi **một read method** sẽ chuyển sang **not readable**. Implementation có thể đồng thời chuyển sang not writable.
- Gọi **một write method** sẽ chuyển sang **not writable**. Implementation có thể đồng thời chuyển sang not readable.
- Gọi **free/close** sẽ chuyển cả hai sang trạng thái **không thể dùng**.

Bảng giúp phân biệt:

| Tình trạng | Đã free? | Có thể đọc/ghi? |
| --- | --- | --- |
| Object mới từ `createSQLXML()` | Chưa | Chưa có XML content; cho phép **một** phương thức khởi tạo |
| Đã `setString`/`setCharacterStream` | Chưa | Không ghi lại; **đọc lại cùng object có thể bị driver từ chối** |
| Object từ `ResultSet.getSQLXML` chưa được đọc | Chưa | Có thể đọc qua **một** read API |
| Đã gọi một read API | Chưa | Không đọc lại; driver có thể hạn chế ghi |
| Đã gọi `free()` | **Rồi** | Không đọc, không ghi, không bind/execute với object đó |
| Connection/transaction đã kết thúc | Không xác định | **Không dựa** vào object cũ, dù chưa free; quy tắc sau ranh giới phụ thuộc driver |

**Hai loại lỗi khác nhau:** `SQLException` sau lần đọc thứ hai không nhất thiết chứng minh `free` đã xảy ra; nó có thể chỉ là trạng thái **not readable**. Đừng phân loại mọi lỗi SQLXML là “giải phóng quá sớm”.

### Không đọc lại object vừa dùng để ghi

```java
SQLXML xml = connection.createSQLXML();
xml.setString("<ok/>");
// Không bảo đảm: String copied = xml.getString();
```

Implementation được phép đánh dấu object **not readable** khi bắt đầu ghi. Nếu ứng dụng cần xác nhận XML trước khi gửi, kiểm tra chính `String` đầu vào bằng XML parser an toàn hoặc kiểm thử đối tượng nguồn, không đòi SQLXML tự cho read-back.

## 5. Ranh giới transaction: điều Javadoc bảo đảm và không bảo đảm

Javadoc Java SE 26 mô tả SQLXML thường được driver triển khai như **logical pointer** đến dữ liệu XML, và object **hợp lệ trong giao dịch mà nó được tạo**. Đây là cơ sở để lựa chọn scope sử dụng.

### 5.1. Mức bảo đảm tối thiểu

Một `SQLXML` được tạo/tải từ transaction T1 **được kỳ vọng sử dụng trong transaction đó**, trừ khi ứng dụng đã gọi `free/close`. Điều này không đồng nghĩa “DB lưu một object XML Java mãi mãi”. Có thể có dữ liệu/locator phía server, hoặc representation tối ưu của driver.

**Hợp đồng không hứa object vẫn usable qua transaction T2**. Vì vậy ứng dụng portable không nên giữ SQLXML cũ sau `commit`/`rollback` để đọc hoặc cập nhật ở transaction kế tiếp.

### 5.2. Không khẳng định tất cả driver đều invalid ngay sau commit

Có driver materialize XML thành dữ liệu client-side, có driver giữ locator gắn transaction. **Không có quy tắc chung rằng `commit()` luôn tự gọi `free()`, hoặc mọi `getString()` sau `commit` luôn phải ném `SQLException`**. Muốn biết behavior cụ thể, cần tài liệu và integration tests của driver/DBMS.

Đây là sự khác biệt quan trọng:

- **Sau `free()`**: API contract xác định object đã invalid.
- **Sau transaction boundary nhưng chưa free**: object không còn được portable code dựa vào; kết quả có thể **khác giữa implementations**.
- **Sau `Connection.close()`**: không được dùng locator gắn với Connection đã kết thúc; một số objects materialized có thể hành xử khác, nhưng code portable không dựa vào đó.

### 5.3. Ranh giới commit/rollback không thay thế release

Khi ứng dụng kết thúc transaction, JDBC/DB có thể cleanup những locators hoặc resources. Nhưng **không xem đó là thay thế** `SQLXML.free()`, vì tài nguyên có thể tồn tại đến khi object được GC hoặc driver thực hiện dọn, đặc biệt trong transaction dài.

Đặt `free()` trong scope mà application sở hữu để chủ động trả tài nguyên và giảm nguy cơ tích lũy.

### 5.4. Auto-commit làm scope ngắn hơn

JDBC `Connection` thường bắt đầu ở chế độ **auto-commit=true**; một statement hoàn tất có thể tự commit theo contract. Đừng cố giữ `SQLXML` sau các câu statement rồi trông đợi một transaction dài vô hạn.

Nếu nghiệp vụ cần ghi SQLXML và các thao tác DML khác thành một đơn vị, dùng `setAutoCommit(false)`, `commit`/`rollback` rõ ràng. **Không bật manual transaction chỉ để làm cho SQLXML “sống mãi”**; vẫn cần giới hạn scope, timeout và cleanup.

### 5.5. Rollback

`rollback` hoàn tác thay đổi giao dịch theo DB semantics. Nó **không gọi ngược lại `SQLXML.free()` theo hợp đồng Java**. Sau rollback, không tái sử dụng object SQLXML cũ để tạo lại lệnh ghi. Nếu thử lại nghiệp vụ, nên **lấy một Connection/transaction hợp lệ và tạo SQLXML mới**, sau đó bind statement mới khi cần.

## 6. Thứ tự ghi an toàn: đừng free trước execute

Một luồng ghi XML theo JDBC:

```text
Connection còn mở, transaction đang hoạt động
    |
    v
SQLXML xml = connection.createSQLXML()
    |
    v
xml.setString(...) / setCharacterStream() / setResult(...)
    |
    v
Đóng Writer / OutputStream / hoàn tất Result
    |
    v
PreparedStatement ps = connection.prepareStatement(sql)
    |
    v
ps.setSQLXML(1, xml)
    |
    v
ps.executeUpdate() / ps.execute()        <-- driver tiêu thụ XML
    |
    v
Không còn cần xml: xml.free()            <-- giải phóng SQLXML
    |
    v
connection.commit() hoặc rollback theo kết quả
    |
    v
Connection.close()                       <-- trả logical connection
```

Đây là trình tự **khuyến nghị khi object không cần sau execute**. Trong các workflow phức tạp có ResultSet streaming hoặc driver-specific locators, vị trí giải phóng phải căn cứ thời điểm đã hoàn tất việc tiêu thụ.

### 6.1. Vì sao không free ngay sau setSQLXML?

`PreparedStatement.setSQLXML` **gán tham số**, nhưng driver có thể thực sự đọc data khi `executeUpdate/execute`. Vì vậy:

```java
SQLXML xml = connection.createSQLXML();
xml.setString("<order/>");
ps.setSQLXML(1, xml);
xml.free();       // QUÁ SỚM nếu statement chưa tiêu thụ XML
ps.executeUpdate();
```

Đây là **anti-pattern**, không nên copy. Nó có thể dẫn đến SQLException hoặc lỗi data do object đã invalid trước execute.

Đúng hơn:

```java
SQLXML xml = connection.createSQLXML();
try {
    xml.setString("<order/>");
    ps.setSQLXML(1, xml);
    ps.executeUpdate();
} finally {
    xml.free();   // Chỉ sau execute hoặc sau khi thao tác thất bại
}
```

Đây là snippet trong method, cần `connection`/`ps`; phải đặt cả transaction và statement trong scope riêng phù hợp.

### 6.2. Đóng Writer/OutputStream trước bind/execute

Nếu chọn `setCharacterStream` hoặc `setBinaryStream`:

```java
SQLXML xml = connection.createSQLXML();
try {
    try (Writer writer = xml.setCharacterStream()) {
        writer.write("<note>Tiếng Việt</note>");
    } // Writer đóng trước bind.

    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO documents(payload) VALUES (?)")) {
        ps.setSQLXML(1, xml);
        ps.executeUpdate();
    }
} finally {
    xml.free();
}
```

Javadoc của `PreparedStatement.setSQLXML` nêu `SQLException` khi `Result`/`Writer`/`OutputStream` liên quan chưa đóng. Javadoc `SQLXML` cũng yêu cầu mọi streams phải được đóng trước `execute`.

**Đừng dựa vào `flush()` như tương đương `close()`**: nhiều providers chỉ hoàn thiện XML data khi đóng writer/result, không phải khi có một phần bytes/characters trong buffer.

### 6.3. Batch statements và thời điểm consume

Khi dùng `addBatch()`/`executeBatch()`, **không nên free SQLXML sau mỗi `addBatch` nếu batch chưa được execute**. Driver có thể cần object/stream ở thời điểm thực thi batch. Hãy căn cứ contract driver cho batch parameter handling và giải phóng sau khi batch đã thực sự tiêu thụ dữ liệu. Với nhiều records, thường tạo **SQLXML riêng mỗi record**; không tái khởi tạo một SQLXML qua nhiều batch entries.

## 7. Java 17–25: quản lý bằng `free()`, finally và suppressed exceptions

### 7.1. Cách tối giản, tương thích Java 17

```java
SQLXML xml = connection.createSQLXML();
try {
    xml.setString(document);
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setSQLXML(1, xml);
        ps.executeUpdate();
    }
} finally {
    xml.free();
}
```

Snippet trên yêu cầu `connection`, `document` và `sql` phù hợp. `Connection`/`PreparedStatement` là `AutoCloseable`, nhưng trên **Java 17–25** `SQLXML` **chưa** extends `AutoCloseable`; do đó `try (SQLXML xml = ...)` **không compile** khi target `--release 17`.

### 7.2. Lỗi cleanup có thể che lỗi chính

`SQLXML.free()` có thể ném `SQLException`. Nếu `executeUpdate` đã ném một exception và `free` trong `finally` cũng ném, exception của `free` có thể thay thế nguyên nhân chính trong luồng exception thông thường. Điều này làm khó phân tích lỗi dữ liệu/transaction.

Vì vậy với code production quan trọng, cần chính sách giữ **primary failure** và **release failure**. Một giải pháp Java 17 là dùng một **AutoCloseable adapter** có `close` chỉ gọi `free`, rồi giao cơ chế suppressed exceptions cho try-with-resources. Adapter này không làm thay đổi interface `SQLXML` trong JDK 17.

### 7.3. Adapter Java 17+ cho SQLXML

```java
import java.sql.SQLException;
import java.sql.SQLXML;

public final class SqlXmlLease implements AutoCloseable {
    private final SQLXML value;
    private boolean closed;

    public SqlXmlLease(SQLXML value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    public SQLXML get() {
        if (closed) throw new IllegalStateException("SQLXML lease closed");
        return value;
    }

    @Override
    public void close() throws SQLException {
        if (!closed) {
            closed = true;
            value.free();
        }
    }
}
```

Đây là **lớp độc lập**, có thể biên dịch bằng `javac --release 17 SqlXmlLease.java`. Nó là helper của ứng dụng, **không phải API JDK**. Việc đặt `closed=true` trước `free` tránh cố giải phóng lần hai từ cùng lease nếu lần đầu ném SQLException, nhưng trạng thái resource thật khi free lỗi vẫn phụ thuộc driver.

Ví dụ:

```java
try (SqlXmlLease lease =
         new SqlXmlLease(connection.createSQLXML());
     PreparedStatement ps = connection.prepareStatement(sql)) {
    SQLXML xml = lease.get();
    xml.setString(document);
    ps.setSQLXML(1, xml);
    ps.executeUpdate();
}
```

**Thứ tự đóng quan trọng:** trong resource list, `lease` được khai báo **trước** `ps`, nên try-with-resources đóng **`ps` trước, rồi mới `lease` (gọi free)**. Như vậy statement đã dùng xong trước khi XML được giải phóng.

Nếu body ném SQLException và `lease.close()` cũng lỗi, try-with-resources giữ body exception là primary và thêm cleanup exception vào `getSuppressed()`. Dùng adapter giúp tránh code `finally` lồng nhau khó bảo trì.

### 7.4. Adapter không thay thế transaction

Adapter chỉ dọn SQLXML. Bạn vẫn phải quyết định `commit/rollback`, đóng Connection và xử lý failure đúng tầng ứng dụng. Đừng nghĩ có try-with-resources là tự động commit khi body thành công.

## 8. Java 26+: SQLXML là AutoCloseable

**Thay đổi hiện hành** trong Java SE 26/JDBC 4.5: `SQLXML` **extends `AutoCloseable`** và có:

```java
default void close() throws SQLException;
```

Implementation mặc định của `close()` **gọi `free()`**. Đối tượng đã đóng thì `close` lần sau là no-op. Điều này được mô tả trong [SQLXML Java SE 26 Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLXML.html).

| Target Java | Có thể khai báo SQLXML trực tiếp trong try-with-resources? | Cách cleanup |
| --- | --- | --- |
| **17–25** | Không | `free()` trong finally hoặc `AutoCloseable` adapter |
| **26+** | Có | `try (SQLXML xml = ...)` tự gọi `close()` → `free()`; `free()` vẫn hợp lệ |

### Snippet JDK 26+ (không chạy trên Java 17)

```java
// Chỉ compile khi target Java 26 trở lên.
try (SQLXML xml = connection.createSQLXML();
     PreparedStatement ps = connection.prepareStatement(sql)) {
    xml.setString(document);
    ps.setSQLXML(1, xml);
    ps.executeUpdate();
} // ps.close() trước; xml.close() -> free() sau.
```

**Đừng copy snippet này vào project biên dịch `--release 17`**. Khi target Java 17, `SQLXML` chưa implement `AutoCloseable` nên compiler từ chối resource declaration, dù máy bạn cài một JDK mới hơn. Sử dụng bản có `free` hoặc adapter.

### Tại sao close không tự lưu dữ liệu?

`close` và `free` chỉ giải phóng tài nguyên **SQLXML**, không thay `executeUpdate` hay `Connection.commit`. Nếu bạn thoát try-with-resources **trước execute**, dữ liệu có thể không được lưu; thời điểm dùng và đóng SQLXML vẫn phải đặt đúng thứ tự.

### Không lạm dụng close() lặp lại

Javadoc mới định nghĩa repeated close là no-op; về mặt code ownership, vẫn nên **chỉ một tầng** quyết định scope. Khi cùng một SQLXML được nhiều components giữ reference, họ không nên tranh nhau đóng object.

## 9. Một ví dụ giao dịch thực tế (cần JDBC driver và database)

Ví dụ method sau tổ chức **transaction + release + statement lifetime**. Đây là **mã tích hợp**, không chạy độc lập vì `DataSource` và bảng `xml_documents` phải có thật:

```java
static int insertDocument(DataSource dataSource, String xmlText)
        throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            int rows;
            try (SqlXmlLease lease =
                     new SqlXmlLease(connection.createSQLXML());
                 PreparedStatement ps = connection.prepareStatement(
                         "INSERT INTO xml_documents(payload) VALUES (?)")) {
                SQLXML xml = lease.get();
                xml.setString(xmlText);
                ps.setSQLXML(1, xml);
                rows = ps.executeUpdate();
            } // ps đóng; SQLXML free trước khi commit.
            connection.commit();
            return rows;
        } catch (SQLException | RuntimeException failure) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        }
    }
}
```

Cần imports `javax.sql.DataSource`, `java.sql.Connection`, `PreparedStatement`, `SQLXML`, `SQLException` và helper `SqlXmlLease` từ mục 7. `xml_documents(payload)` là bảng/column ví dụ, SQL type phải hỗ trợ XML trong DBMS được chọn.

### 9.1. Ưu điểm của cấu trúc này

- `Connection` chỉ sống trong một request/giao dịch.
- Chuyển sang manual transaction bằng `setAutoCommit(false)`.
- SQLXML chỉ tồn tại trong scope mà code sở hữu.
- `setSQLXML` chỉ bind khi XML chưa free.
- `executeUpdate` diễn ra trước khi statement và XML bị dọn.
- `PreparedStatement` đóng trước SQLXML theo thứ tự resource list.
- SQLXML được `free` trước `commit`, khi transaction vẫn đang hoạt động và không còn cần giá trị tại statement.
- Exception từ rollback được thêm vào `failure.getSuppressed()` để giữ nguyên nhân gốc.
- `Connection` được đóng đúng scope, kể cả khi thất bại.

### 9.2. Phạm vi hỗ trợ và caveat

- Bản thân `SqlXmlLease` hỗ trợ Java 17+; JDK26 có thể dùng SQLXML trực tiếp trong try-with-resources.
- Cột SQL XML có cú pháp khác nhau giữa DBMS, và `createSQLXML/setSQLXML` có thể ném `SQLFeatureNotSupportedException` với driver không hỗ trợ.
- Transaction nesting hoặc transaction do framework quản lý (ví dụ container-managed, Spring) **không nhất thiết cho phép repository tự commit/rollback**. Nếu framework sở hữu transaction, chỉ viết SQLXML trong transaction đó và giao commit/rollback cho framework.
- Đoạn ví dụ không có retry, isolation-level policy hoặc XML validation; bổ sung theo yêu cầu sản phẩm.
- Nếu SQL driver cần giữ một locator lâu hơn thời điểm `executeUpdate`, kiểm thử integration và điều chỉnh release boundary theo contract; không tự free trước khi statement tiêu thụ xong.

### 9.3. Khi SQLXML lấy từ ResultSet

`ResultSet.getSQLXML` cung cấp XML **đã tồn tại trong DB**, khác object mới từ `createSQLXML`. Hãy xử lý nó trước khi `ResultSet`/`Connection` bị đóng.

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT payload FROM xml_documents WHERE id = ?")) {
    ps.setLong(1, id);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            SQLXML value = rs.getSQLXML(1);
            if (value != null) {
                try {
                    String xmlText = value.getString(); // Đọc một lần.
                    // Xử lý xmlText ở đây.
                } finally {
                    value.free();
                }
            }
        }
    }
}
```

Đây là snippet tích hợp, cần `id`, Connection, JDBC driver, bảng và `throws SQLException`. Nếu SQL column là NULL thì `getSQLXML` có thể trả Java `null`; **không gọi `free()` trên null**.

### 9.4. Đừng trả object SQLXML ra khỏi repository

**Anti-pattern:**

```java
SQLXML getDocument(DataSource source, long id) throws SQLException {
    try (Connection conn = source.getConnection()) {
        // Trả SQLXML lấy từ ResultSet rồi đóng Connection ở đây.
        // Caller có thể gặp locator hết hiệu lực.
        throw new UnsupportedOperationException("Anti-pattern minh họa");
    }
}
```

Đoạn này là **phác thảo anti-pattern có chủ đích**, không phải method dùng trong ứng dụng. Đúng hướng là: **materialize** text/data có giới hạn ngay trong scope, hoặc trả một API streaming sở hữu cả Connection/ResultSet với lifecycle rất rõ ràng. Không phát tán một SQLXML locator trần ra ngoài transaction.

## 10. Ví dụ chạy được Java 17+: free, transaction và use-after-free

Để học cách **đặt điều kiện kiểm thử** mà không cần cài database, ví dụ dưới đây dùng `java.lang.reflect.Proxy` giả lập một `Connection` và `PreparedStatement`, đồng thời triển khai một `MemoryXml` theo interface `SQLXML`.

Fixture **cố tình mô phỏng** database driver có **transaction-bound locators**: sau `commit` hoặc `rollback`, SQLXML được tạo ở transaction trước sẽ bị từ chối. Đây là **chính sách của mock**, không phải luật bắt buộc với mọi driver. Phần **free() và use-after-free** bám theo Javadoc; phần mock còn kiểm tra premature release và writer chưa đóng.

### 10.1. Phạm vi mock

- Có `Connection.createSQLXML()`, `setAutoCommit(false)`, `commit`, `rollback`, `close`, `prepareStatement`.
- `PreparedStatement.setSQLXML(1, xml)` và `executeUpdate()` mô phỏng việc driver tiêu thụ XML.
- `MemoryXml` hỗ trợ `setString/getString`, `setCharacterStream/getCharacterStream`, `setBinaryStream/getBinaryStream`, `free`, cùng trạng thái readable/writable.
- `getSource/setResult` của test double cố tình ném `SQLFeatureNotSupportedException` khi object còn hoạt động; fixture **không phải JDBC driver hoàn chỉnh**. Với driver thật hỗ trợ SQLXML, Javadoc yêu cầu các API được implement đầy đủ.
- `XmlLease` là adapter Java 17 dùng try-with-resources để gọi `free`.
- Các methods JDBC ngoài phạm vi mock ném `SQLFeatureNotSupportedException` và **không thực sự gửi dữ liệu lên DB**.

### 10.2. Cấu trúc

```text
sqlxml-free-demo/
└── SqlXmlFreeDemo.java
```

Không cần external JAR, credentials hay database. Mã được biên dịch bằng `javac --release 17` và thực thi trên OpenJDK 24.

### 10.3. Toàn bộ file `SqlXmlFreeDemo.java`

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLXML;
import javax.xml.transform.Source;
import javax.xml.transform.Result;

public final class SqlXmlFreeDemo {
    private static final class Session {
        boolean closed;
        boolean autoCommit = true;
        long generation;
        String stored;

        Connection open() {
            return (Connection) Proxy.newProxyInstance(
                SqlXmlFreeDemo.class.getClassLoader(),
                new Class<?>[]{Connection.class}, (proxy, method, args) -> {
                    String name = method.getName();
                    if (name.equals("close")) { closed = true; return null; }
                    if (name.equals("isClosed")) return closed;
                    if (closed) throw new SQLException("Connection closed");
                    return switch (name) {
                        case "setAutoCommit" -> { autoCommit = (Boolean) args[0]; yield null; }
                        case "getAutoCommit" -> autoCommit;
                        case "commit", "rollback" -> {
                            if (autoCommit) throw new SQLException("Not in manual transaction");
                            generation++;
                            yield null;
                        }
                        case "createSQLXML" -> new MemoryXml(this);
                        case "prepareStatement" -> prepare();
                        default -> throw new SQLFeatureNotSupportedException("Mock: " + name);
                    };
                });
        }

        PreparedStatement prepare() {
            final boolean[] closedStatement = {false};
            final MemoryXml[] param = {null};
            return (PreparedStatement) Proxy.newProxyInstance(
                SqlXmlFreeDemo.class.getClassLoader(),
                new Class<?>[]{PreparedStatement.class}, (proxy, method, args) -> {
                    String name = method.getName();
                    if (name.equals("close")) { closedStatement[0] = true; return null; }
                    if (name.equals("isClosed")) return closedStatement[0];
                    if (closed || closedStatement[0]) throw new SQLException("Statement closed");
                    switch (name) {
                        case "setSQLXML":
                            if ((Integer) args[0] != 1 || !(args[1] instanceof MemoryXml xml)) {
                                throw new SQLException("Only mock SQLXML index 1 supported");
                            }
                            xml.ensureActive();
                            if (xml.writerOpen) throw new SQLException("Writer must close before bind");
                            param[0] = xml;
                            return null;
                        case "executeUpdate":
                            if (param[0] == null) throw new SQLException("No XML param");
                            stored = param[0].textForExecute();
                            return 1;
                        default:
                            throw new SQLFeatureNotSupportedException("Mock statement: " + name);
                    }
                });
        }
    }

    private static final class MemoryXml implements SQLXML {
        final Session session;
        final long bornGeneration;
        String text;
        boolean freed;
        boolean writable = true;
        boolean readable;
        boolean writerOpen;
        int releaseCount;

        MemoryXml(Session session) {
            this.session = session;
            this.bornGeneration = session.generation;
        }

        static MemoryXml fromQuery(Session session, String text) {
            MemoryXml xml = new MemoryXml(session);
            xml.writable = false;
            xml.readable = true;
            xml.text = text;
            return xml;
        }

        void ensureActive() throws SQLException {
            if (freed) throw new SQLException("SQLXML already freed");
            if (session.closed) throw new SQLException("Connection closed");
            if (bornGeneration != session.generation) {
                throw new SQLException("Mock locator expired at transaction boundary");
            }
        }

        void startWrite() throws SQLException {
            ensureActive();
            if (!writable) throw new SQLException("Not writable");
            writable = false;
            readable = false;
        }

        String readOnce() throws SQLException {
            ensureActive();
            if (!readable || writerOpen) throw new SQLException("Not readable");
            readable = false;
            return text;
        }

        String textForExecute() throws SQLException {
            ensureActive();
            if (writable || writerOpen || text == null) {
                throw new SQLException("XML data incomplete");
            }
            return text;
        }

        @Override public void free() {
            if (freed) return;
            freed = true;
            text = null;
            writerOpen = false;
            releaseCount++;
        }
        @Override public void setString(String value) throws SQLException {
            startWrite();
            text = value;
        }
        @Override public String getString() throws SQLException {
            return readOnce();
        }
        @Override public Writer setCharacterStream() throws SQLException {
            startWrite();
            writerOpen = true;
            return new StringWriter() {
                private boolean closed;
                @Override public void close() {
                    if (closed) return;
                    text = toString();
                    writerOpen = false;
                    closed = true;
                }
            };
        }
        @Override public Reader getCharacterStream() throws SQLException {
            return new StringReader(readOnce());
        }
        @Override public OutputStream setBinaryStream() throws SQLException {
            startWrite();
            writerOpen = true;
            return new ByteArrayOutputStream() {
                private boolean closed;
                @Override public void close() {
                    if (closed) return;
                    text = new String(toByteArray(), StandardCharsets.UTF_8);
                    writerOpen = false;
                    closed = true;
                }
            };
        }
        @Override public InputStream getBinaryStream() throws SQLException {
            return new ByteArrayInputStream(
                    readOnce().getBytes(StandardCharsets.UTF_8));
        }
        @Override public <T extends Source> T getSource(Class<T> type)
                throws SQLException {
            ensureActive();
            throw new SQLFeatureNotSupportedException("Mock omits getSource");
        }
        @Override public <T extends Result> T setResult(Class<T> type)
                throws SQLException {
            ensureActive();
            throw new SQLFeatureNotSupportedException("Mock omits setResult");
        }
    }

    private static final class XmlLease implements AutoCloseable {
        final SQLXML value;
        boolean closed;
        XmlLease(SQLXML value) { this.value = value; }
        @Override public void close() throws SQLException {
            if (!closed) {
                closed = true;
                value.free();
            }
        }
    }

    @FunctionalInterface
    interface SqlAction { void run() throws SQLException; }

    static boolean rejected(SqlAction action) {
        try { action.run(); return false; }
        catch (SQLException expected) { return true; }
    }
    static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws Exception {
        Session session = new Session();
        Connection connection = session.open();
        MemoryXml afterClose;
        try (connection) {
            connection.setAutoCommit(false);
            check("manualTransaction", !connection.getAutoCommit());
            try (PreparedStatement ps =
                         connection.prepareStatement("INSERT INTO demo(xml) VALUES (?)")) {
                MemoryXml first = (MemoryXml) connection.createSQLXML();
                ps.setSQLXML(1, first);
                check("emptyNotExecutable", rejected(ps::executeUpdate));
                first.setString("<item>Xin chào</item>");
                check("secondWriteRejected",
                        rejected(() -> first.setString("<other/>")));
                check("executeBeforeFree", ps.executeUpdate() == 1
                        && session.stored.equals("<item>Xin chào</item>"));
                first.free();
                first.free();
                check("freeIdempotent", first.releaseCount == 1);
                check("readAfterFreeRejected", rejected(first::getString));
                check("writeAfterFreeRejected",
                        rejected(() -> first.setString("<again/>")));
                check("sourceAfterFreeRejected",
                        rejected(() -> first.getSource(null)));
                check("streamAfterFreeRejected",
                        rejected(first::getCharacterStream));
                check("bindAfterFreeRejected",
                        rejected(() -> ps.setSQLXML(1, first)));

                MemoryXml writerXml = (MemoryXml) connection.createSQLXML();
                Writer writer = writerXml.setCharacterStream();
                writer.write("<stream>Đã đóng</stream>");
                check("bindWhileWriterOpenRejected",
                        rejected(() -> ps.setSQLXML(1, writerXml)));
                writer.close();
                ps.setSQLXML(1, writerXml);
                check("closedWriterExecutes", ps.executeUpdate() == 1
                        && session.stored.equals("<stream>Đã đóng</stream>"));
                writerXml.free();

                MemoryXml tooEarly = (MemoryXml) connection.createSQLXML();
                tooEarly.setString("<x/>");
                ps.setSQLXML(1, tooEarly);
                tooEarly.free();
                check("freeBeforeExecuteRejected", rejected(ps::executeUpdate));

                MemoryXml readOnly = MemoryXml.fromQuery(session, "<db>ok</db>");
                check("firstReadWorks", readOnly.getString().equals("<db>ok</db>"));
                check("secondReadRejected", rejected(readOnly::getString));
                readOnly.free();
            }

            MemoryXml atCommit = (MemoryXml) connection.createSQLXML();
            atCommit.setString("<commit/>");
            connection.commit();
            check("commitExpiryInMock",
                    rejected(() -> atCommit.textForExecute()));
            atCommit.free();
            check("freeAfterCommit", atCommit.releaseCount == 1);

            MemoryXml atRollback = (MemoryXml) connection.createSQLXML();
            atRollback.setString("<rollback/>");
            connection.rollback();
            check("rollbackExpiryInMock",
                    rejected(() -> atRollback.textForExecute()));
            atRollback.free();

            MemoryXml fresh = (MemoryXml) connection.createSQLXML();
            fresh.setString("<new-transaction/>");
            check("freshTransactionCanCreate",
                    fresh.textForExecute().equals("<new-transaction/>"));
            fresh.free();

            MemoryXml leased = (MemoryXml) connection.createSQLXML();
            try (XmlLease lease = new XmlLease(leased)) {
                lease.value.setString("<managed/>");
            }
            check("java17LeaseCallsFree", leased.releaseCount == 1);
            check("leaseObjectNowInvalid", rejected(leased::getString));

            afterClose = (MemoryXml) connection.createSQLXML();
            afterClose.setString("<closed/>");
        }
        check("connectionClosed", connection.isClosed());
        check("connectionCloseInvalidatesMock",
                rejected(afterClose::getString));
        afterClose.free();
        check("createAfterCloseRejected",
                rejected(connection::createSQLXML));
    }
}
```

### 10.4. Lệnh biên dịch và chạy

Trong thư mục `sqlxml-free-demo` chứa file `SqlXmlFreeDemo.java`:

```bash
javac --release 17 SqlXmlFreeDemo.java
java SqlXmlFreeDemo
```

Lệnh như trên hoạt động trong PowerShell, cmd, Bash hoặc terminal khác nếu JDK 17+ có trong `PATH`. Code sử dụng các modules chuẩn `java.base`, `java.sql` và `java.xml`, không cần cài JDBC driver. Java 17 hỗ trợ switch expression và pattern matching cho `instanceof` được dùng trong code.

### 10.5. Stdout chính xác đã chạy trên OpenJDK 24

```text
manualTransaction=true
emptyNotExecutable=true
secondWriteRejected=true
executeBeforeFree=true
freeIdempotent=true
readAfterFreeRejected=true
writeAfterFreeRejected=true
sourceAfterFreeRejected=true
streamAfterFreeRejected=true
bindAfterFreeRejected=true
bindWhileWriterOpenRejected=true
closedWriterExecutes=true
freeBeforeExecuteRejected=true
firstReadWorks=true
secondReadRejected=true
commitExpiryInMock=true
freeAfterCommit=true
rollbackExpiryInMock=true
freshTransactionCanCreate=true
java17LeaseCallsFree=true
leaseObjectNowInvalid=true
connectionClosed=true
connectionCloseInvalidatesMock=true
createAfterCloseRejected=true
```

**24/24 assertions PASS**. Method `check` ném `AssertionError` nếu điều kiện sai; các dòng `=true` **không** được in vô điều kiện. Bộ mã đã biên dịch với `javac --release 17` và chạy trên Windows OpenJDK 24. Các file test tạm đã được dọn sạch.

### 10.6. Đọc từng nhóm kiểm thử

| Nhóm | Các assertions | Điều chứng minh |
| --- | --- | --- |
| Manual transaction | `manualTransaction` | Connection mock đổi sang manual transaction |
| Chưa khởi tạo | `emptyNotExecutable` | Không execute một XML chưa có nội dung |
| Ghi một lần | `secondWriteRejected` | Không tái khởi tạo XML bằng write API |
| Execute rồi free | `executeBeforeFree` | Object còn hợp lệ lúc mock statement tiêu thụ; dữ liệu mock được ghi nhận |
| Free idempotent | `freeIdempotent` | Gọi free hai lần chỉ release một lần |
| Không dùng sau free | `readAfterFreeRejected`, `writeAfterFreeRejected`, `sourceAfterFreeRejected`, `streamAfterFreeRejected` | Mọi read/write methods sau free bị từ chối |
| Không bind object invalid | `bindAfterFreeRejected`, `freeBeforeExecuteRejected` | Bị từ chối khi bind sau free hoặc execute sau premature free |
| Hoàn tất Writer | `bindWhileWriterOpenRejected`, `closedWriterExecutes` | Đóng Writer trước khi driver tiêu thụ XML |
| Read-once | `firstReadWorks`, `secondReadRejected` | Object đọc từ query chỉ cho một read API |
| Transaction-bound mock locator | `commitExpiryInMock`, `rollbackExpiryInMock` | **Mock-specific** invalidation; không khẳng định mọi driver như vậy |
| Dọn dẹp sau boundary | `freeAfterCommit` | Mock cho phép release sau commit; không biến thành lời hứa của mọi driver |
| Giao dịch mới | `freshTransactionCanCreate` | Tạo object mới trong scope mới |
| Adapter Java 17 | `java17LeaseCallsFree`, `leaseObjectNowInvalid` | `XmlLease.close()` gọi free và object không được tái sử dụng |
| Đóng Connection | `connectionClosed`, `connectionCloseInvalidatesMock`, `createAfterCloseRejected` | Connection mock từ chối thao tác sau khi đóng |

**Quan trọng:** `commitExpiryInMock=true` **không** có nghĩa Java spec yêu cầu mọi SQLXML ném SQLException sau commit. Fixture cố ý chọn strict transaction-bound policy để học cách **không dựa vào locator vượt scope**. Tương tự, `MemoryXml.fromQuery` là data giả lập cho read-once, **không phải `ResultSet` thật**. Không dùng mock thay integration test với database.

## 11. Connection pool, request scope và async processing

### 11.1. Pool trả logical handle

Khi dùng HikariCP, application server hoặc pool khác, `dataSource.getConnection()` thường cấp một **logical Connection**. Gọi `close` trên handle trả về pool theo hợp đồng pool, không nhất thiết đóng physical socket.

Một `SQLXML` tạo từ handle đó có thể đại diện cho XML do driver/session phía dưới quản lý. Nếu bạn lưu SQLXML ở singleton hoặc trả ra ngoài service, request khác có thể **mượn lại physical connection** trong khi code cũ vẫn giữ một locator.

Điều này gây ra:

- Use-after-free khi component khác đã gọi `free`.
- Dùng locator sau khi transaction/request kết thúc.
- Lỗi driver state hoặc `SQLException` không ổn định giữa môi trường.
- Memory/resource leak do không free đúng lúc.
- Khó xác định ai sở hữu `SQLXML` hoặc ai cần close.

### 11.2. Không trả SQLXML trực tiếp từ API async

Không đưa `SQLXML` vào queue, `CompletableFuture`, callback hoặc Reactor publisher để xử lý sau khi connection scope kết thúc, trừ khi bạn thiết kế API streaming **giữ toàn bộ resource ownership** một cách an toàn. Thay vào đó:

- Với XML nhỏ, đọc một lần trong transaction rồi trả `String`/DTO hoặc node tree đã materialize.
- Với XML lớn, stream trong phạm vi giữ Connection/ResultSet và có backpressure, timeout, cancellation và cleanup.
- Nếu muốn xử lý offline, lưu XML/document vào storage có lifetime độc lập với JDBC locator, rồi chỉ chuyển tham chiếu hợp lệ.

**Không giả định** một XML object có thể dùng đồng thời bởi nhiều threads. `SQLXML` không hứa thread-safety phổ quát; chủ thể sở hữu nên dùng trong một workflow tuần tự hoặc theo contract driver.

## 12. SQLXML.free so với đóng Writer/Stream/ResultSet/Statement

Các thao tác resource thường bị nhầm:

| Resource | Dọn thế nào? | Vai trò |
| --- | --- | --- |
| `Writer` từ `SQLXML.setCharacterStream()` | `writer.close()` (try-with-resources) | Hoàn tất **dữ liệu XML đang được ghi** |
| `OutputStream` từ `setBinaryStream()` | `out.close()` | Hoàn tất bytes/XML encoding trước bind/execute |
| `Reader` từ `getCharacterStream()` | `reader.close()` | Kết thúc đọc và trả resources cho stream |
| `InputStream` từ `getBinaryStream()` | `in.close()` | Kết thúc đọc binary stream |
| `SQLXML` | `free()` (hoặc `close()` trên JDK26+) | Giải phóng **SQLXML object/locator** |
| `PreparedStatement` | `ps.close()` | Giải phóng JDBC statement |
| `ResultSet` | `rs.close()` | Giải phóng JDBC cursor/result |
| `Connection` | `connection.close()` | Kết thúc logical JDBC connection handle |
| Transaction | `commit` / `rollback` | Chốt/hoàn tác thay đổi SQL |

**Đóng Writer không đồng nghĩa free SQLXML**, và **free SQLXML không đồng nghĩa Writer được đóng trước execute**. Mỗi thứ có điểm kết thúc sử dụng riêng.

### Câu hỏi thường gặp: chỉ dùng setString, có stream nào cần close?

Không. `setString` không trả một Writer/OutputStream cho caller; khi dùng `setString`, bạn chỉ cần đảm bảo SQLXML không free quá sớm và release object sau khi hoàn tất. Dù vậy XML có thể bị DB/driver từ chối do định dạng hoặc schema không hợp lệ ở lúc set/execute.

## 13. SQLException, SQLFeatureNotSupportedException và cleanup policy

### 13.1. `SQLException` sau free là lỗi hợp đồng

Một `getString` hoặc `setString` sau free có thể ném `SQLException` vì object không còn hợp lệ. Hãy xem lại **thứ tự resource lifecycle**, không retry cùng một instance với cùng một method.

Nếu muốn retry operation, hãy tạo **SQLXML mới** ở transaction hợp lệ, rồi lặp workflow. Đừng dùng object đã free.

### 13.2. `SQLException` tại commit không tương đương free lỗi

`Connection.commit()` có thể thất bại do network/DB; `free()` có thể thất bại do resource release. Chúng là hai loại lỗi khác nhau, yêu cầu logging/rollback policy khác nhau. Đặc biệt, nếu commit thất bại, trạng thái DB có thể không rõ; đừng tự retry INSERT vô điều kiện và tạo dữ liệu trùng.

### 13.3. `SQLFeatureNotSupportedException`

Javadoc cho phép method không được driver hỗ trợ ném `SQLFeatureNotSupportedException`. Không có nghĩa `SQLXML` bị loại khỏi Java. Nó có thể là **giới hạn của driver/DB/schema**, cần kiểm tra capability và chọn giải pháp được nghiệp vụ cho phép (chẳng hạn lưu XML text vào CLOB nếu DB không có XML type).

### 13.4. Không xóa dấu vết lỗi nguyên nhân chính

Nếu lỗi ở `executeUpdate` nhưng release cũng lỗi, bạn nên ghi nhận **primary exception** và **suppressed exception**. Try-with-resources dùng adapter làm việc này tự động cho `XmlLease.close`. Với transaction code, khi rollback lỗi trong `catch`, thêm rollback error vào suppressed và vẫn ném nguyên nhân chính.

## 14. Tính đúng đắn XML và bảo mật: phạm vi liên quan

`SQLXML.free()` **không** chứng minh XML đầu vào đã đúng cấu trúc, không parse XML, và không loại nguy cơ XXE/DTD. Nếu dữ liệu XML đến từ nguồn không đáng tin:

- Giới hạn độ dài, nesting và payload size trước khi xử lý.
- Dùng `PreparedStatement.setSQLXML` để bind, không nối XML trực tiếp vào SQL literals.
- Khi parse XML, cấu hình JAXP/StAX/SAX/DOM để giới hạn external DTD, external entities và resource access phù hợp trust model.
- Escape text/attributes bằng XML serializer, không tự nối `String` chưa escape vào markup.
- Khi biến đổi XML sang dữ liệu nội bộ, thực hiện trong scope mà resource còn hợp lệ.
- Tránh log nguyên văn XML nhạy cảm chỉ để debug use-after-free hoặc transaction error.

Dữ liệu XML malformed có thể chỉ bị từ chối khi driver thực thi SQL, không nhất thiết ngay lúc `setString`. Vì vậy cleanup và rollback paths cần xử lý **cả lỗi muộn**.

## 15. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `SQLException` ngay sau `xml.free()` khi đọc | Use-after-free rõ ràng | Không đọc lại; materialize trước free nếu cần |
| `SQLException` khi gọi `setString` lần hai | SQLXML đã not writable, không nhất thiết đã free | Tạo SQLXML mới |
| `SQLException` khi gọi `getString` lần hai | SQLXML đã not readable | Đọc một lần; giữ `String`/DTO của ứng dụng |
| Lỗi tại `ps.setSQLXML` khi Writer mở | Stream/Result chưa đóng | Đóng Writer/OutputStream, hoàn tất Result trước bind |
| Lỗi tại `executeUpdate` sau khi free XML | Object bị giải phóng quá sớm | Đặt free sau execute |
| Lỗi chỉ xuất hiện sau commit | Locator có thể hết transaction scope | Không tái sử dụng object; tạo mới trong transaction mới |
| Lỗi chỉ xuất hiện sau rollback | Locator cũ không portable qua rollback | Xây lại XML ở transaction mới |
| Lỗi sau `Connection.close()` | Logical JDBC handle đã hết scope | Không đưa SQLXML ra khỏi repository scope |
| Memory/resource tăng trong transaction dài | SQLXML/streams chưa free/close | Giới hạn scope, try-with-resources, finally |
| `free` bản thân ném SQLException | Driver error khi release | Giữ primary exception và ghi release failure |
| Java 17 không compile `try(SQLXML x=...)` | SQLXML chưa AutoCloseable | Dùng free hoặc adapter; JDK26 mới trực tiếp hỗ trợ |
| XML stored nhưng byte-for-byte khác input | DB/driver có thể canonicalize/serialize XML | Đánh giá theo XML semantics, không mặc định bytes phải giống |
| Driver không hỗ trợ `createSQLXML` | Feature/schema limitation | Kiểm tra driver/DB; dùng phương án lưu hợp lệ khác |
| API trả SQLXML là null | SQL column là NULL | Kiểm tra null trước getter/free |

## 16. Ma trận kiểm thử tích hợp nên có với database thật

| Test | Điều kỳ vọng cần xác minh |
| --- | --- |
| Tạo SQLXML, ghi, bind, execute, free | Data thực sự lưu/đọc đúng trong cùng transaction |
| Free hai lần | Lần sau không có thêm tác dụng; không dùng lại object |
| Getter/setter sau free | SQLException đúng contract |
| Stream ghi chưa đóng | setSQLXML hoặc execute từ chối theo Javadoc |
| Free trước execute | Không dựa vào object freed; thiết kế tránh lỗi này |
| SQLXML từ ResultSet | Đọc một lần, free trong scope ResultSet/Connection |
| ResultSet SQL NULL | getSQLXML trả null theo driver/JDBC contract |
| Commit xong dùng locator cũ | **Chỉ quan sát driver behavior**; app không dựa vào nó |
| Rollback xong dùng locator cũ | **Chỉ quan sát driver behavior**; app không dựa vào nó |
| Connection pool release/reborrow | Không có use-after-close, leak, cross-request locator |
| Lỗi SQL trong execute rồi free | Primary error được giữ, release error được ghi/suppressed |
| Lỗi commit/rollback | Không retry mù quáng, transaction state được điều tra |
| Xử lý XML Unicode | Dữ liệu ký tự có dấu, emoji, XML entities đúng |
| XML không hợp lệ | Lỗi được báo và transaction rollback, resources được free |
| XML lớn | Memory/latency/streaming được đo; không giữ toàn bộ XML nếu không cần |
| Driver upgrade | Contract SQLXML, transaction và resource close vẫn đúng |

Bộ test ở mục 10 chỉ kiểm tra **mô hình mock**, không thay thế ma trận trên. Integration tests cần driver version và loại cột SQL XML thật mà sản phẩm sử dụng.

## 17. Checklist triển khai

1. **Owner:** Xác định tầng nào sở hữu `SQLXML` và chịu trách nhiệm `free`.
2. **Scope:** Chỉ giữ `SQLXML` trong vòng đời transaction/connection cần thiết.
3. **Read/write once:** Không coi SQLXML là đối tượng có thể đọc/ghi lặp.
4. **Không free trước khi dùng:** Chỉ giải phóng khi statement/stream/transformer đã hoàn tất.
5. **Stream completion:** Đóng tất cả Writer/OutputStream/Result liên quan trước bind/execute.
6. **PreparedStatement:** Dùng `setSQLXML` với placeholder, không nối raw XML vào SQL.
7. **Transaction:** Có policy commit/rollback rõ ràng; `free` không thay transaction.
8. **Driver caveat:** Không giả định commit/rollback luôn gọi free hoặc luôn giữ locator hoạt động.
9. **ResultSet SQL NULL:** Kiểm tra `xml != null` trước getter/free.
10. **Java version:** Java 17–25 dùng free/adapter; JDK26+ có SQLXML AutoCloseable.
11. **Primary failure:** Bảo toàn exceptions khi cleanup/rollback lỗi.
12. **Pool:** Không truyền SQLXML qua các request/checkout khác.
13. **Async:** Không chuyển XML locator sang background task sau khi JDBC scope kết thúc.
14. **Large XML:** Dùng streams khi cần và xử lý trong resource scope.
15. **Security:** Không nhầm cleanup với XML validation/XXE defense.
16. **No re-use:** Nếu muốn XML thứ hai, tạo một SQLXML mới.
17. **Instrumentation:** Theo dõi connection/statement/SQLXML resource leaks trong tests.
18. **Compatibility:** Test driver và DBMS thực tế, không chỉ mock.
19. **No internal classes:** Không dùng reflection để lấy raw locator rồi bỏ qua lifecycle.
20. **No unnecessary release loops:** Một owner, một scope, một lần release chủ động.

## 18. Câu hỏi tự kiểm tra

**1. `SQLXML.free()` có xoá giá trị XML khỏi bảng SQL không?**

Không. Nó release resource mà object JDBC giữ. Giá trị đã được lưu thành công trong DB được quản lý theo DML/transaction của DBMS.

**2. Có thể gọi `free()` hai lần không?**

Có. Lần sau no-op theo contract. Nhưng ownership nên rõ ràng, không cố tình free ở nhiều tầng.

**3. Sau free, `getString()` có được phép trả chuỗi cũ đã cache không?**

Không. Theo `SQLXML` contract, các methods khác `free/close` sau khi object đã đóng phải ném `SQLException`.

**4. Có thể gọi `getString()` hai lần nếu chưa free không?**

Không nên giả định; read APIs có ngữ nghĩa đọc tối đa một lần và chuyển trạng thái sang **not readable**.

**5. Sau `setString`, SQLXML luôn có thể `getString` trước execute?**

Không. Driver được phép đánh dấu object not readable khi ghi.

**6. `commit` có nghĩa Java tự gọi `SQLXML.free` không?**

Không được suy ra như vậy. Transaction boundary và SQLXML release là hai trách nhiệm khác nhau.

**7. SQLXML có luôn ném SQLException ngay sau commit không?**

Không có bảo đảm mọi driver giống nhau. Code portable **không sử dụng SQLXML vượt transaction scope**; mock có thể mô phỏng strict expiration để dạy giới hạn.

**8. Tại sao không giải phóng ngay sau `PreparedStatement.setSQLXML`?**

Vì driver có thể cần object khi `executeUpdate`/`execute` diễn ra, nên free sớm gây use-after-free.

**9. Trong Java 17, `try(SQLXML xml=...)` có compile không?**

Không. `SQLXML` chỉ mới extends AutoCloseable trong JDK 26. Dùng `free` hoặc `AutoCloseable` adapter cho Java 17.

**10. Trong Java 26, `SQLXML.close()` làm gì?**

Default implementation gọi `free()`. Nó giúp try-with-resources; không tự thực thi SQL hay commit.

**11. Gọi `close` trên Writer có giống gọi SQLXML.free không?**

Không. Writer.close hoàn tất dữ liệu ghi. SQLXML.free release toàn bộ đối tượng sau khi không cần sử dụng nữa.

**12. Một repository nên trả `SQLXML` ra cho controller xử lý sau khi Connection đã đóng không?**

Không nên. Đọc/materialize hoặc stream trong scope đang sở hữu resource, đừng đưa locator sang request khác.

**13. Khi statement lỗi, free cũng lỗi thì nên ưu tiên exception nào?**

Giữ nguyên nhân chính của SQL operation và ghi cleanup failure bằng suppressed exception khi có thể. Try-with-resources với adapter giúp xử lý tự động.

**14. `ResultSet.getSQLXML` trên cột SQL NULL trả gì?**

Có thể trả Java `null`; cần null-check trước `getString`/`free`.

**15. `free()` và `rollback()` khác nhau thế nào?**

`free` giải phóng tài nguyên SQLXML; `rollback` hoàn tác thay đổi transaction theo database contract.

**16. Tại sao bài kiểm thử mock mô phỏng hết hiệu lực sau commit nhưng không gọi đó là quy tắc chung?**

Vì Javadoc chỉ bảo đảm lifetime trong transaction; cách driver biểu diễn locator hoặc dữ liệu materialized có thể khác nhau. Test mock chọn trường hợp strict để dạy code không dựa vào tài nguyên vượt scope.

**17. Nếu cần đọc XML nhiều lần, nên làm gì?**

Đọc SQLXML **một lần** rồi materialize một `String`/DOM hoặc dữ liệu riêng của ứng dụng nếu bộ nhớ cho phép; hoặc thiết kế streaming/queries có lifecycle rõ ràng.

**18. Nếu SQLXML.create không hỗ trợ trên một driver, free sẽ sửa được không?**

Không. `SQLFeatureNotSupportedException` từ `createSQLXML` phản ánh capability của driver; cần chọn cách lưu XML theo DB/schema thay vì retry resource release.

## Nguồn chính thức còn hiệu lực

- [Oracle Java SE 26 — `SQLXML`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLXML.html): `free` idempotent, vòng đời trong transaction, read/write-once, use-after-free `SQLException` và `close()` từ JDK 26.
- [Oracle Java SE 26 — `Connection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `createSQLXML`, `commit`, `rollback`, `close` và transaction semantics.
- [Oracle Java SE 26 — `PreparedStatement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): `setSQLXML` và điều kiện đóng Result/Writer/OutputStream.
- [Oracle Java SE 26 — `ResultSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): `getSQLXML`, SQL NULL và result resource.
- [Oracle Java SE 26 — `SQLException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): lỗi JDBC và suppressed exceptions.
- [Oracle Java SE 26 — `SQLFeatureNotSupportedException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): optional driver capability.
- [Oracle Java SE 26 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html): try-with-resources và suppressed exceptions.
- [Oracle Java SE 26 — `java.sql package`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/package-summary.html): JDBC 4.5 bổ sung AutoCloseable cho `SQLXML` và một số SQL types khác.
- [Oracle Java SE 17 — `SQLXML`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLXML.html): `free` là cleanup hợp lệ nhưng Java 17 `SQLXML` chưa AutoCloseable.
- [Oracle JDBC Tutorial — SQLXML Objects](https://docs.oracle.com/javase/tutorial/jdbc/basics/sqlxml.html): transaction lifetime và release; dùng để đối chiếu contract, không dựa vào ví dụ driver cũ làm mã tích hợp hiện đại.
- [Microsoft Learn — SQLXML and JDBC Driver for SQL Server](https://learn.microsoft.com/en-us/sql/connect/jdbc/sqlxml-interface): ví dụ một vendor ghi rõ trạng thái và giải phóng SQLXML; không suy rộng đặc điểm vendor thành Java spec.

**Ghi nhớ:** **`free()` vô hiệu hóa SQLXML**; đừng đọc/ghi/bind lại. SQLXML có phạm vi sử dụng **gắn với transaction và Connection**, nhưng cách driver ứng xử **sau commit/rollback** khác với lỗi chắc chắn **sau free**. Hoàn tất stream, bind và execute trước khi release; giữ một owner rõ ràng; không chuyển locator qua request hoặc pool checkout. Trên **Java 17–25** dùng `free` hoặc adapter, trên **Java 26+** có thêm `AutoCloseable.close()` (mặc định gọi `free`). Việc release **không thay transaction commit/rollback**.
