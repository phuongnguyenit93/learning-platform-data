# Kiểm thử Unicode, dữ liệu lớn và khả năng hỗ trợ của DBMS trong JDBC

Trong JDBC, lưu được một chuỗi Java vào cột SQL **không đồng nghĩa** dữ liệu đã đi qua database một cách chính xác. Khi ứng dụng xử lý **tiếng Việt có dấu, emoji, ký tự ngoài Basic Multilingual Plane (BMP), văn bản dài hoặc LOB**, phải kiểm tra toàn bộ đường đi: **Java `String` → JDBC driver → cấu hình character set/type/collation của DBMS → lưu trữ → JDBC ResultSet/Reader → Java `String`**.

Ba nhóm rủi ro chính là:

1. **Unicode:** sai charset, mất dấu, thay emoji bằng `?`, surrogate pair không hợp lệ, normalize không mong muốn, so sánh/collation khác byte-for-byte equality.
2. **Dữ liệu lớn:** vượt giới hạn cột, bị cắt ngầm hoặc ném `DataTruncation`, driver giữ toàn bộ dữ liệu trong RAM dù API cung cấp stream, stream/LOB bị đóng quá sớm, timeout hoặc áp lực lên transaction/log.
3. **Khả năng hỗ trợ DBMS/driver:** có API Java `setNString`/`setNClob` không có nghĩa mọi driver/server đều hỗ trợ kiểu `NVARCHAR`/`NCLOB`; `DatabaseMetaData` cho biết khả năng **được công bố**, nhưng vẫn cần **integration test thực tế**.

Bài học thuộc ngữ cảnh **JDBC dữ liệu**, áp dụng các API hiện hành trên **Java 17+ và JDK hiện nay**, bao gồm `java.sql.PreparedStatement`, `ResultSet`, `Types`, `Clob`, `NClob`, `DatabaseMetaData`, `ResultSetMetaData`, `SQLFeatureNotSupportedException`, `DataTruncation` và các loại dữ liệu văn bản/nhị phân.

Nội dung có **hai ví dụ Java 17+**:

- `UnicodeFixturesCheck.java`: chương trình **JDK-only chạy độc lập**, đã biên dịch và thực thi với 8 kiểm tra PASS trên JDK 24; minh họa fixture Unicode, NFC/NFD, dữ liệu lớn và `Reader`.
- `JdbcUnicodeRoundTrip.java`: phép thử **tích hợp JDBC thật** có rollback và assertions cho cả văn bản ngắn/dài; **đã được biên dịch** bằng `javac --release 17`, nhưng cần bạn cung cấp database/driver/schema và **chưa được thực thi với DBMS thật** trong phần kiểm chứng này. Không giả định một DBMS bất kỳ đã PASS.

**Lưu ý trọng tâm:** Unicode encoding, normalization, collation và case folding là **bốn vấn đề khác nhau**; API streaming, cột LOB và cơ chế streaming thực tế của driver cũng **không hoàn toàn đồng nhất**. Hãy kiểm tra riêng từng thuộc tính thay vì chỉ xem “INSERT không báo lỗi”.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Thiết kế bộ dữ liệu kiểm thử có tiếng Việt, chữ viết khác, emoji, supplementary code points, combining marks, dạng NFC/NFD, ký tự ranh giới và chuỗi dài.
- Hiểu sự khác biệt giữa **UTF-16 code units**, **Unicode code points**, **grapheme clusters** và **UTF-8 bytes**.
- Dùng đúng `PreparedStatement.setString`, `setNString`, `setCharacterStream`, `setNCharacterStream`, `setClob`/`setNClob` và `setBinaryStream`/`setBlob` khi phù hợp.
- Lấy dữ liệu qua `ResultSet.getString`, `getNString`, `getCharacterStream`, `getNCharacterStream`, `getClob`/`getNClob` hoặc `getBinaryStream` và xử lý vòng đời tài nguyên.
- Biết cách dùng `DatabaseMetaData.getTypeInfo`, `getColumns`, `supportsTransactions`, `supportsBatchUpdates` để thăm dò khả năng hỗ trợ nhưng **không xem metadata là bằng chứng tuyệt đối**.
- Phân biệt lỗi unsupported feature, lỗi encoding/conversion, truncation, DBMS collation và giới hạn cột.
- Viết kiểm thử round-trip so sánh **exact Java String** và **Unicode normalization** riêng biệt.
- Kiểm thử dữ liệu lớn bằng stream, quan sát memory/latency/log size mà không nhầm độ dài char với số byte UTF-8.
- Bảo toàn dữ liệu và rollback sạch trong integration tests, không để lại dữ liệu thử ngoài ý muốn.

## 2. Java Unicode và database encoding là hai tầng riêng

Java `String` là chuỗi các **UTF-16 code units**. Những ký tự trong BMP thường chiếm một `char`, còn Unicode code point nằm ngoài BMP như nhiều emoji thường chiếm **một surrogate pair = hai `char`**. Một số ký tự hiển thị còn được tạo từ **nhiều code points**, ví dụ chữ `e` cộng combining acute mark.

```java
String s = "😀";
System.out.println(s.length());                       // 2 UTF-16 code units
System.out.println(s.codePointCount(0, s.length())); // 1 code point
```

Đây là mảnh code có thể đặt trong method Java; không phải chương trình độc lập. Vì thế:

- `String.length()` **không phải** số ký tự hiển thị và cũng **không phải** số byte UTF-8.
- `codePointCount` đếm Unicode code points, không đếm grapheme clusters mà người dùng cảm nhận.
- `str.getBytes(StandardCharsets.UTF_8).length` là số byte của bản mã UTF-8 tạo ở client, không phải số byte mà DBMS cuối cùng dùng để lưu.
- DBMS có thể có ngữ nghĩa độ dài theo **byte**, **code point**, **UTF-16 code unit** hoặc **character set cụ thể**; tên `VARCHAR(500)` không tự giải quyết mọi sự khác biệt giữa vendors.
- SQL string comparison có thể dùng **collation**, nơi hai chuỗi khác nhau về code point vẫn được xem là bằng nhau.
- Chuyển encoding sai có thể gây lỗi, thay thế ký tự hoặc cắt dữ liệu; đừng giả định nhận HTTP 200 hoặc `executeUpdate()==1` nghĩa là chuỗi vẫn nguyên.

### 2.1. Một ma trận Unicode cần có trong test fixtures

| Nhóm | Fixture gợi ý | Điều cần kiểm tra |
| --- | --- | --- |
| ASCII | `"Hello 123"` | Baseline không dấu và khoảng trắng. |
| Tiếng Việt dựng sẵn | `"Trường Đại học, Cộng hòa"` | Không mất dấu/hỏng bảng mã. |
| Tiếng Việt tổ hợp | `"e\u0301"` (e + dấu acute) | Bảo toàn đúng chuỗi code units khi yêu cầu exact round-trip. |
| NFC vs NFD | `"\u00E9"` đối chiếu `"e\u0301"` | Exact equality khác nhau, normalize NFC có thể bằng nhau. |
| Supplementary emoji | `"😀"` | Không thay bằng `?`; không cắt surrogate pair. |
| Ký tự ngoài BMP không phải emoji | `"𐐷"` | Phát hiện hệ DB chỉ hỗ trợ BMP hoặc xử lý surrogate sai. |
| Ký tự từ nhiều script | `"مرحبا 漢字 한글"` | Hỗ trợ đa hệ chữ viết. |
| Khoảng trắng đặc biệt | `"A\u00A0B"` (NBSP) | Kiểm tra trim/collation/normalization không làm đổi ngoài ý muốn. |
| Line break | `"dòng 1\n dòng 2"` | Không cắt hoặc thay `\n` trong text/LOB. |
| Dấu ngoặc kép/nháy đơn | `"O'Connor \u0022quoted\u0022"` | PreparedStatement bảo toàn dữ liệu mà không nối SQL string. |
| Chuỗi rỗng và SQL NULL | `""` đối chiếu `null` | Phân biệt null và empty theo DBMS (một số DB đặc biệt). |
| Chuỗi dài | Nhiều MB, có emoji ở gần ranh giới chunk | Không truncate, không tách surrogate pair khi streaming. |

Khi chuyển fixture có escape như `"\u0301"` vào Java source, nó tương ứng với ký tự kết hợp thật. Kiểm tra không nên chỉ dùng màn hình/console, vì font, terminal encoding và copy/paste có thể che sự khác nhau giữa các code points.

### 2.2. Exact equality khác canonical equivalence

```java
String composed = "\u00E9";
String decomposed = "e\u0301";

boolean rawEqual = composed.equals(decomposed); // false
boolean nfcEqual = java.text.Normalizer.normalize(
        composed, java.text.Normalizer.Form.NFC).equals(
        java.text.Normalizer.normalize(
                decomposed, java.text.Normalizer.Form.NFC)); // true
```

Nếu yêu cầu **giữ nguyên đầu vào**, dùng `String.equals` khi readback. Nếu nghiệp vụ cho phép xem hai chuỗi canonical-equivalent là tương đương, normalize theo một policy rõ ràng; phải lưu ý normalization có thể **thay representation code points**. Không dùng `NFKC`/`NFKD` mặc định cho mọi dữ liệu: compatibility normalization có thể làm mất các phân biệt có ý nghĩa.

**Collation của DB khác normalization của Java.** Ví dụ một unique index với case-insensitive/accent-insensitive collation có thể coi hai giá trị là trùng dù raw bytes khác. Vì thế **vừa kiểm tra raw round-trip vừa kiểm tra SQL compare/order/unique** theo yêu cầu sản phẩm.

## 3. Các loại cột SQL và mapping qua JDBC

| SQL/JDBC data type | Java API thường dùng | Ghi chú |
| --- | --- | --- |
| `CHAR`, `VARCHAR`, `LONGVARCHAR` | `setString`, `getString`, `setCharacterStream`, `getCharacterStream` | Charset/collation phụ thuộc DBMS và cột. |
| `NCHAR`, `NVARCHAR`, `LONGNVARCHAR` | `setNString`, `getNString`, `setNCharacterStream`, `getNCharacterStream` | Dành cho national character set ở những DBMS/driver hỗ trợ. |
| `CLOB` | `setClob`, `setCharacterStream`, `getClob`, `getCharacterStream` | Lưu lượng ký tự lớn, thường không nên materialize toàn bộ. |
| `NCLOB` | `setNClob`, `setNCharacterStream`, `getNClob`, `getNCharacterStream` | National character large object; có thể không được hỗ trợ ở mọi DB. |
| `BLOB` / `VARBINARY` / `LONGVARBINARY` | `setBlob`, `setBinaryStream`, `getBlob`, `getBinaryStream` | Byte stream; dùng cho ảnh/file hoặc dữ liệu nhị phân, không tự có Unicode interpretation. |
| `SQLXML` | `setSQLXML` / `getSQLXML` | Kiểu XML được hỗ trợ tùy DB/driver, không mặc định thay cho text CLOB. |

Các constants `Types.NCHAR`, `Types.NVARCHAR`, `Types.LONGNVARCHAR` và `Types.NCLOB` là **JDBC type codes**, không có nghĩa tên SQL type trên server luôn viết hệt như vậy. Ví dụ các DBMS khác nhau dùng `TEXT`, `LONGTEXT`, `NVARCHAR2`, `NVARCHAR(MAX)` hoặc những kiểu tương đương.

**Đừng đoán**: `NVARCHAR` chắc chắn “Unicode hơn” `VARCHAR`. Có DBMS dùng Unicode database encoding cho `VARCHAR/TEXT`; có DBMS phân biệt national/non-national charsets. Cần xem **server encoding, collation, column type và JDBC driver implementation** cho từng hệ.

### 3.1. setString và setNString khác nhau

```java
// Mảnh code bên trong method có PreparedStatement ps và String text:
ps.setString(1, text);
ps.setNString(2, text);
```

- `setString` gán một Java `String` vào parameter, driver chuyển đổi phù hợp với SQL target type.
- `setNString` **chỉ rõ national character set semantics** cho dữ liệu parameter theo JDBC 4.0; driver có thể ném `SQLFeatureNotSupportedException` hoặc `SQLException` nếu không hỗ trợ kiểu/national character set/conversion.
- Không dùng `setNString` vào mọi cột `VARCHAR/TEXT` chỉ vì chuỗi có emoji. Sự đúng đắn phụ thuộc cột DB, charset, driver và cách bind.
- Không chuyển mọi `SQLException` từ `setNString` sang `setString` mà không đánh giá nguy cơ chuyển đổi sai dữ liệu.
- `getNString` ở kết quả có contract và khả năng hỗ trợ tương ứng; nếu DB không có national types, dùng `getString` cho cột Unicode phù hợp có thể là lựa chọn đúng.

### 3.2. setCharacterStream và setNCharacterStream

```java
// Mảnh code, Reader source đã có và PreparedStatement ps hợp lệ:
ps.setCharacterStream(1, source, lengthInChars);
ps.setNCharacterStream(2, source, lengthInChars);
```

- `Reader` cung cấp **ký tự**, không cung cấp raw bytes.
- Độ dài `lengthInChars` theo API là **số ký tự trong stream**, thực tế reader Java phục vụ **UTF-16 char units**; nếu truyền `StringReader` từ một `String`, dùng `string.length()`, không dùng `getBytes(UTF_8).length` hoặc `codePointCount(...)` để làm length hint. Điều này đặc biệt quan trọng khi có emoji.
- Những overload **không truyền length** cũng còn được hỗ trợ từ JDBC 4.0, nhưng khả năng streaming và hiệu suất có thể khác giữa drivers.
- Với `setNCharacterStream`, driver biết target là national character stream; không mặc định DBMS nào cũng hỗ trợ.
- Reader phải **còn mở cho tới khi driver hoàn tất việc đọc**. Với nhiều driver, nó được tiêu thụ trong `executeUpdate()`/`execute()`, không nhất thiết ngay lúc gọi setter.
- Driver có thể **buffer toàn bộ stream** trước khi gửi. API streaming không hứa memory luôn O(chunk size).

### 3.3. Binary stream không phải character stream

`setBinaryStream(index, inputStream, bytesLength)` sử dụng **bytes**, thích hợp cho `BLOB` hoặc binary payload. Nếu một ứng dụng chọn lưu UTF-8 text như bytes vào BLOB, encoding phải được xác định rõ lúc ghi/đọc. Không dùng `getCharacterStream` để đọc một file PNG hay ZIP, và không dùng `getBinaryStream` rồi ngầm hiểu bytes là text không cần decoder.

## 4. LOB là gì và nên quản lý thế nào?

`CLOB` = Character Large Object; `NCLOB` = National Character Large Object; `BLOB` = Binary Large Object. JDBC có `Clob`, `NClob`, `Blob`, các method đọc stream và `free()` để giải phóng tài nguyên driver/server khi thích hợp.

**Không phải mọi cột kiểu text lớn đều bắt buộc map qua `Clob` object.** Một số DBMS dùng `TEXT`/`LONGTEXT` và driver hỗ trợ `getCharacterStream` tốt hơn một API CLOB chuyên biệt; điều này phải được thử.

```java
// Mảnh code tích hợp: đọc dữ liệu text dài theo stream.
try (ResultSet rs = statement.executeQuery()) {
    if (rs.next()) {
        try (Reader reader = rs.getCharacterStream("long_text")) {
            if (reader == null) {
                // Giá trị SQL NULL; xử lý theo contract ứng dụng.
            } else {
                char[] buffer = new char[8192];
                int n;
                while ((n = reader.read(buffer)) != -1) {
                    // Xử lý từng phần; không giữ toàn bộ vào một StringBuilder.
                }
            }
        }
    }
}
```

Đây là mảnh code **không độc lập**, cần `statement` và SQL/query hợp lệ. Khi dùng `ResultSet.getCharacterStream`, chú ý:

- Giữ `ResultSet`/`Statement`/`Connection` còn mở cho đến khi đọc xong stream; driver có thể đóng stream khi chuyển cột/hàng hoặc đóng result set.
- Xử lý `null` nếu cột SQL NULL; không nên gọi method trên Reader null.
- Luôn đóng Reader/stream và giải phóng CLOB/BLOB locator khi có.
- Không giữ một `Clob` locator qua transaction/connection lifecycle vượt hợp đồng của driver.
- `Clob.length()` trả `long`; `String.length()` trả `int`. Với dữ liệu khổng lồ, tránh materialize vào một Java `String`, vì giới hạn bộ nhớ/array.
- Đọc/gửi theo chunk và kiểm tra EOF/độ dài/checksum; tránh `rs.getString("long_text")` cho payload quá lớn nếu có thể dùng stream.

### 4.1. setClob/setNClob và cleanup

```java
// Mảnh code cho cột NCLOB mà driver hỗ trợ:
try (Reader source = new StringReader(largeText)) {
    ps.setNClob(1, source, largeText.length());
    ps.executeUpdate();
}
```

Với `NClob` object do driver tạo, dùng `free()` khi không còn cần để giải phóng resources. `NClob` extends `Clob`; không coi nó là Java String bất biến. Các operations có thể bị ràng buộc bởi transaction mà locator được tạo ra. Khi driver không hỗ trợ national character set, `SQLFeatureNotSupportedException` hoặc `SQLException` có thể được báo; kiểm tra khả năng thực tế, không cố “ép cast” một `Clob` thành `NClob`.

## 5. Kiểm thử dữ liệu lớn cần phân biệt năm loại giới hạn

| Giới hạn | Ví dụ tác động | Biện pháp test |
| --- | --- | --- |
| **Độ rộng cột** | `VARCHAR(n)` có thể từ chối/truncate. | Test n−1, n, n+1 theo đơn vị mà DBMS dùng. |
| **Charset/encoding** | Cùng số Unicode codepoints có số UTF-8 bytes khác nhau. | Ghi cả BMP và supplementary, so exact. |
| **Protocol/driver binding** | Driver giới hạn length hoặc buffer payload. | Test `setCharacterStream`/`setNClob`, lặp kích thước tăng dần. |
| **Java memory** | `getString`/`getBytes` copy một object cực lớn. | Stream từng chunk, profile heap/GC. |
| **Server limits/transactions** | WAL/redo/log, LOB quota, timeout, replication cost. | Test môi trường cô lập, theo dõi DB metrics và rollback. |

Không chỉ test kích thước “1 MB” rồi coi mọi loại dữ liệu đều tương đương. Một triệu **UTF-16 chars** không bằng một triệu **UTF-8 bytes**. Dữ liệu ASCII, tiếng Việt và emoji có byte density rất khác nhau.

### 5.1. Các mốc biên nên thử

1. Chuỗi rỗng, chỉ một ký tự, chỉ một emoji, chỉ một dấu kết hợp.
2. Giá trị dài ngay sát `VARCHAR(n)` theo cách DBMS đếm.
3. Giá trị vượt `VARCHAR(n)` một đơn vị: DB báo lỗi, truncate, warning hay driver tự convert?
4. Chuỗi dài gồm toàn ASCII, toàn tiếng Việt, nhiều supplementary emoji.
5. Emoji nằm sát ranh giới khối đọc Reader 4096/8192 code units.
6. Chuỗi chứa newline, apostrophe, NBSP và tổ hợp NFD.
7. Giá trị NULL tách biệt chuỗi rỗng.
8. LOB lớn nhiều MB, khả năng serialize/deserialize và bộ nhớ.
9. Nhiều rows/batches, một transaction lớn, rollback/commit và recovery.
10. Cùng bộ dữ liệu trên các version khác nhau của DBMS/driver/JDK.

Khi kiểm thử một **batch lớn**, đừng giữ hàng trăm nghìn `byte[]`/`String` đồng thời nếu mục tiêu là đánh giá streaming; dùng input data generator hoặc file/Reader và đo memory thực tế.

### 5.2. Truncation không luôn có cùng biểu hiện

`java.sql.DataTruncation` là SQLException/SQLWarning liên quan tới việc dữ liệu bị cắt trong truyền/đọc ghi; nhưng driver/DBMS **không bắt buộc ném cùng class và message trong mọi tình huống**. Có thể là lỗi SQLState/vendor code, warning, hoặc server silently converts theo config.

Khi test:

- So sánh **exact readback** sau INSERT.
- Đọc `Statement.getWarnings()` và `Connection.getWarnings()` khi có.
- Bắt `SQLException` với `SQLState`, `getErrorCode()`, `getNextException()` và cause; không chỉ so English message.
- Bật chế độ DBMS nghiêm ngặt khi có và phù hợp; không chọn cấu hình cho phép truncate âm thầm.
- Kiểm tra *observed* column length/type bằng metadata và schema thực tế, không đoán từ Java `String.length()`.
- Nếu yêu cầu bảo toàn tuyệt đối, **mọi thay đổi không được mong muốn phải làm test thất bại**.

## 6. Ví dụ JDK-only tự chạy: tạo bộ dữ liệu Unicode + Reader lớn

Ví dụ đầu tiên **không sử dụng JDBC driver hay database**. Nó kiểm tra các bất biến phía Java trước khi đưa dữ liệu qua JDBC:

- Supplementary code points khiến `String.length()` lớn hơn `codePointCount`.
- UTF-8 encode/decode phải giữ nguyên chuỗi hợp lệ.
- Dạng NFC/NFD của `é` và `e + combining acute` có thể khác raw nhưng tương đương chuẩn hóa.
- Một chuỗi dài trên 1 triệu UTF-16 chars có thể so sánh qua `Reader`.
- Mã hóa surrogate pair không hợp lệ sẽ bị từ chối nếu dùng `CharsetEncoder` với `CodingErrorAction.REPORT`.

### 6.1. Tạo file `UnicodeFixturesCheck.java`

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Arrays;

public final class UnicodeFixturesCheck {
    private static void check(String name, boolean success) {
        if (!success) throw new AssertionError(name);
        System.out.println(name + "=PASS");
    }

    private static boolean equalReaders(Reader left, Reader right) throws IOException {
        try (Reader a = new BufferedReader(left, 8192);
             Reader b = new BufferedReader(right, 8192)) {
            int ca, cb;
            do {
                ca = a.read();
                cb = b.read();
                if (ca != cb) return false;
            } while (ca != -1);
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        String sample = "Tiếng Việt: Hà Nội, 😀, 𐐷, e\u0301, \u00E9";
        check("supplementaryCodePoint",
                sample.length() > sample.codePointCount(0, sample.length()));
        check("utf8RoundTrip",
                sample.equals(new String(sample.getBytes(StandardCharsets.UTF_8),
                        StandardCharsets.UTF_8)));
        String decomposed = "e\u0301";
        String composed = "\u00E9";
        check("nfcEquivalent",
                !decomposed.equals(composed) &&
                Normalizer.normalize(decomposed, Normalizer.Form.NFC).equals(composed));
        check("nfdEquivalent",
                Normalizer.normalize(composed, Normalizer.Form.NFD).equals(decomposed));

        String large = ("Đường phố Hà Nội | 😀 | e\u0301\n").repeat(55_000);
        check("largeOverMillionUtf16", large.length() > 1_000_000);
        check("largeReaderRoundTrip",
                equalReaders(new StringReader(large), new StringReader(large)));
        byte[] encoded = large.getBytes(StandardCharsets.UTF_8);
        check("largeUtf8RoundTrip",
                Arrays.equals(encoded,
                        new String(encoded, StandardCharsets.UTF_8)
                                .getBytes(StandardCharsets.UTF_8)));

        boolean rejected = false;
        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap("\uD83D"));
        } catch (CharacterCodingException expected) {
            rejected = true;
        }
        check("loneSurrogateRejected", rejected);
        System.out.println("checks=8");
    }
}
```

### 6.2. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 UnicodeFixturesCheck.java
java UnicodeFixturesCheck
```

**Stdout chính xác đã kiểm chứng bằng JDK 24:**

```text
supplementaryCodePoint=PASS
utf8RoundTrip=PASS
nfcEquivalent=PASS
nfdEquivalent=PASS
largeOverMillionUtf16=PASS
largeReaderRoundTrip=PASS
largeUtf8RoundTrip=PASS
loneSurrogateRejected=PASS
checks=8
```

Đây là **8 assertions với 9 dòng stdout**, vì dòng cuối báo tổng. Những bài test này chứng minh **data fixtures và Java APIs**, **không** chứng minh một DBMS đã hỗ trợ chúng.

### 6.3. Giải thích từng nhóm

**Supplementary characters:** `😀` và `𐐷` chiếm hai UTF-16 code units trong `String`; nếu bạn cắt chuỗi bằng `substring`/`char[]` theo ranh giới sai, có thể tách đôi một surrogate pair.

**UTF-8 round-trip:** khi dữ liệu nguồn là chuỗi Unicode hợp lệ và encoder/decoder cùng chuẩn, `new String(bytes, UTF_8)` khôi phục đúng code units. Đây là kiểm thử phía Java, không tự xác nhận charset của cột DB.

**NFC/NFD:** `"\u00E9"` và `"e\u0301"` raw không giống nhau nhưng có thể bằng nhau sau normalization. Không sửa input trước khi lưu nếu yêu cầu bảo toàn chính xác.

**Dữ liệu lớn:** `repeat(55_000)` tạo fixture lớn hơn một triệu char units; `equalReaders` so sánh tuần tự thay vì đọc một lượng lớn từ một `Reader` thành `StringBuilder`. Lưu ý tự tạo biến `large` và chuyển thành UTF-8 `byte[]` trong bài test vẫn chiếm bộ nhớ — đây **không phải chương trình chứng minh full pipeline có constant-memory streaming**.

**Malformed surrogate:** `CharsetEncoder` với `CodingErrorAction.REPORT` từ chối một lone high surrogate. Nếu bạn sử dụng các API mặc định có chính sách replacement, một ký tự lỗi có thể trở thành `?`/U+FFFD thay vì được phát hiện; test cần ghi rõ yêu cầu xử lý input không hợp lệ.

## 7. Kiểm thử tích hợp JDBC thật: cần chuẩn bị gì?

Chương trình thứ hai sử dụng `java.sql.DriverManager` và `PreparedStatement` để **INSERT → SELECT → so exact → rollback**. Nó yêu cầu:

1. Một DBMS đang chạy mà bạn có quyền truy cập trong **môi trường thử nghiệm cô lập**.
2. Một JDBC driver JAR đúng version trên runtime classpath, có service-provider registration phù hợp.
3. Một bảng test được chuẩn bị trước, **không chứa dữ liệu sản xuất** và có 3 cột: `id` (số nguyên BIGINT hoặc tương đương), `short_text` (text ngắn hỗ trợ Unicode/supplementary) và `long_text` (large text có thể đọc ghi theo character stream).
4. DBMS/driver hỗ trợ transactions/rollback cho bảng test và có quyền INSERT/SELECT.
5. Biến môi trường `JDBC_URL` và credentials nếu cần. **Không có connection string universal**; dùng cấu hình do vendor công bố.
6. Test dùng đúng char-set/collation/column type mà sản phẩm muốn xác minh, không giả định DB default luôn Unicode-safe.

### 7.1. Schema minh họa, không universal DDL

```sql
-- Minh họa ngữ nghĩa kiểu dữ liệu, chỉ chạy nếu DBMS hỗ trợ cú pháp:
CREATE TABLE jdbc_unicode_probe (
    id BIGINT PRIMARY KEY,
    short_text NVARCHAR(500),
    long_text CLOB
);
```

**Không phải mọi DBMS hỗ trợ trực tiếp `NVARCHAR(500)` hoặc `CLOB`**, nên phải tạo schema tương đương theo tài liệu vendor. Các ví dụ có thể gặp:

| DBMS | Chiến lược cần kiểm tra |
| --- | --- |
| PostgreSQL | Database encoding `UTF8`, cột `TEXT`/`VARCHAR`; đường JDBC `setString/getString` và stream thực tế. |
| MySQL | **`utf8mb4`** cho các cột ký tự cần emoji/supplementary, với kiểu `VARCHAR/TEXT/LONGTEXT` phù hợp. Không sử dụng `utf8mb3` cho thiết kế mới: MySQL ghi rõ nó chỉ hỗ trợ BMP và đã deprecated. |
| SQL Server | `NVARCHAR`/`NVARCHAR(MAX)` hoặc kiểu/collation UTF-8 phù hợp; phải chú ý supplementary-character-aware collations và đơn vị độ dài. |
| Oracle Database | Chọn đúng `VARCHAR2`, `NVARCHAR2`, `CLOB`, `NCLOB` theo database/national character set và cách driver bind. |
| DBMS khác | Xem type system/charset/collation/driver docs, không sao chép cú pháp từ vendor khác. |

Các ví dụ là **điểm cần xem xét, không phải lời cam kết portability**. Test trên DBMS và driver version cụ thể mới quyết định loại cột nào hoạt động.

### 7.2. Chọn chế độ JDBC binding

Chương trình có biến `JDBC_USE_NATIONAL`:

- `false` (mặc định): `setString/getString` cho `short_text`, tiện cho DBMS dùng Unicode column ở non-national text type.
- `true`: `setNString/getNString` cho `short_text`, chỉ bật khi target column/driver thực sự hỗ trợ national character semantics.

Trong cả hai chế độ, `long_text` dùng `setCharacterStream`/`getCharacterStream`. Để test `NCLOB` thực sự, cần một test case riêng sử dụng `setNClob/getNClob` hoặc `setNCharacterStream/getNCharacterStream` cùng cột tương ứng; đừng gán nhãn bài test CLOB là bài test NCLOB.

## 8. Java integration probe đầy đủ: `JdbcUnicodeRoundTrip.java`

Ví dụ dùng một bảng test duy nhất. Mọi thao tác dữ liệu được thực hiện trong transaction và rollback ở cuối. Nếu DBMS không hỗ trợ transactions, chương trình từ chối chạy test để giảm nguy cơ để lại dữ liệu.

### 8.1. Source code

```java
import java.io.BufferedReader;
import java.io.Reader;
import java.io.StringReader;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.Types;
import java.text.Normalizer;
import java.util.Properties;
import java.util.concurrent.ThreadLocalRandom;

public final class JdbcUnicodeRoundTrip {
    private static String required(String name) {
        String v = System.getenv(name);
        if (v == null || v.isBlank()) {
            throw new IllegalArgumentException("Set environment variable " + name);
        }
        return v;
    }

    private static boolean hasJdbcType(DatabaseMetaData meta, int type)
            throws SQLException {
        try (ResultSet rs = meta.getTypeInfo()) {
            while (rs.next()) {
                if (rs.getInt("DATA_TYPE") == type) return true;
            }
        }
        return false;
    }

    private static long assertSameCharacters(String expected, Reader source)
            throws Exception {
        try (Reader a = new StringReader(expected);
             Reader b = new BufferedReader(source, 8192)) {
            long count = 0;
            while (true) {
                int ca = a.read();
                int cb = b.read();
                if (ca != cb) {
                    throw new AssertionError(
                            "Long-text mismatch at UTF-16 offset " + count);
                }
                if (ca < 0) return count;
                count++;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String url = required("JDBC_URL");
        String table = System.getenv().getOrDefault(
                "JDBC_TEST_TABLE", "jdbc_unicode_probe");
        if (!table.matches("[A-Za-z_][A-Za-z0-9_]*")) {
            throw new IllegalArgumentException(
                    "Unsafe test table identifier");
        }
        Properties props = new Properties();
        String user = System.getenv("JDBC_USER");
        String password = System.getenv("JDBC_PASSWORD");
        if (user != null) props.setProperty("user", user);
        if (password != null) props.setProperty("password", password);
        boolean national = Boolean.parseBoolean(
                System.getenv().getOrDefault("JDBC_USE_NATIONAL", "false"));

        String text = "Tiếng Việt Hà Nội; emoji 😀; 𐐷; e\u0301; \u00E9";
        String large = ("Lưu dữ liệu dài: 😀 | Cộng hòa | e\u0301\n")
                .repeat(55_000);
        long id = ThreadLocalRandom.current()
                .nextLong(1, Long.MAX_VALUE);

        try (Connection connection =
                     DriverManager.getConnection(url, props)) {
            DatabaseMetaData meta = connection.getMetaData();
            System.out.println("db=" + meta.getDatabaseProductName());
            System.out.println("driver=" + meta.getDriverName());
            System.out.println("advertisesNVARCHAR=" +
                    hasJdbcType(meta, Types.NVARCHAR));
            System.out.println("advertisesNCLOB=" +
                    hasJdbcType(meta, Types.NCLOB));

            if (!meta.supportsTransactions()) {
                throw new SQLException(
                        "This rollback-based probe requires transactions");
            }
            boolean previous = connection.getAutoCommit();
            connection.setAutoCommit(false);
            try {
                String insertSql = "INSERT INTO " + table +
                        " (id, short_text, long_text) VALUES (?, ?, ?)";
                try (PreparedStatement statement =
                             connection.prepareStatement(insertSql);
                     Reader content = new StringReader(large)) {
                    statement.setLong(1, id);
                    if (national) {
                        statement.setNString(2, text);
                    } else {
                        statement.setString(2, text);
                    }
                    statement.setCharacterStream(
                            3, content, large.length());
                    if (statement.executeUpdate() != 1) {
                        throw new AssertionError(
                                "Expected exactly one inserted row");
                    }
                }

                String selectSql = "SELECT short_text, long_text FROM " +
                        table + " WHERE id = ?";
                try (PreparedStatement statement =
                             connection.prepareStatement(selectSql)) {
                    statement.setLong(1, id);
                    try (ResultSet rows = statement.executeQuery()) {
                        if (!rows.next()) {
                            throw new AssertionError(
                                    "Inserted row not found");
                        }
                        String got = national
                                ? rows.getNString(1) : rows.getString(1);
                        if (!text.equals(got)) {
                            throw new AssertionError(
                                    "Unicode not preserved exactly");
                        }
                        if (!Normalizer.normalize(
                                    text, Normalizer.Form.NFC).equals(
                                Normalizer.normalize(
                                    got, Normalizer.Form.NFC))) {
                            throw new AssertionError("NFC values differ");
                        }
                        Reader longReader = rows.getCharacterStream(2);
                        if (longReader == null) {
                            throw new AssertionError(
                                    "Unexpected NULL long_text");
                        }
                        long length = assertSameCharacters(large, longReader);
                        if (length != large.length()) {
                            throw new AssertionError("Length differs");
                        }
                        System.out.println("shortExact=PASS");
                        System.out.println("longStreamExact=PASS");
                        System.out.println("largeUtf16Chars=" + length);
                        if (rows.next()) {
                            throw new AssertionError("Duplicate rows");
                        }
                    }
                }
            } finally {
                try {
                    connection.rollback();
                    System.out.println("rollback=REQUESTED");
                } finally {
                    connection.setAutoCommit(previous);
                }
            }
        }
    }
}
```

### 8.2. Giải thích các quyết định của ví dụ

**SQL identifier:** chương trình chỉ cho phép `JDBC_TEST_TABLE` theo dạng `[A-Za-z_][A-Za-z0-9_]*` trước khi ghép tên bảng vào SQL. `PreparedStatement` không thể bind table/column names bằng `?`. Với sản phẩm thật, tên bảng nên nằm trong danh sách cấu hình đã tin cậy, không lấy trực tiếp từ user input. Pattern trên là hạn chế đủ cho demo, **không xử lý đầy đủ mọi schema/quoted identifiers/case folding của mọi DBMS**.

**Dữ liệu thử:** `text` chứa tiếng Việt, emoji ngoài BMP, ký tự `𐐷` và cả dạng `e\u0301`/`\u00E9`. `large` chứa hơn một triệu UTF-16 code units, có newline và supplementary characters.

**Metadata trước khi ghi:** `getTypeInfo()` trả các SQL types mà driver/DBMS quảng cáo, gồm cột `DATA_TYPE` (JDBC `Types` codes). Hai cờ `advertisesNVARCHAR` và `advertisesNCLOB` chỉ nói metadata có liệt kê type đó hay không, **không chứng minh bind/read thật đã thành công**.

**Transaction:** kiểm tra `supportsTransactions()` trước khi thay `autoCommit`, sau đó `rollback()` trong `finally`. Bảng được tạo **trước khi chạy**, không cố CREATE/DROP trong test, tránh DDL tự commit trên một số vendors. Vẫn phải dùng **database test cô lập**, vì behavior rollback, triggers hoặc side effects không phải mọi hệ đều giống nhau.

**PreparedStatement:** giá trị `id` được bind bằng `setLong`, chuỗi ngắn bằng `setString`/`setNString`, chuỗi dài bằng `setCharacterStream(index, Reader, long)`. Dùng `large.length()` vì Reader đọc UTF-16 `char`, không dùng số UTF-8 bytes.

**Reader lifecycle:** `content` được giữ mở tới sau `executeUpdate`; Reader đọc từ ResultSet được so sánh/đóng **khi ResultSet còn mở**.

**Exact readback:** `text.equals(got)` làm test fail nếu DB/driver thay đổi code units, ví dụ normalize không mong muốn hoặc thay emoji. Một phép kiểm tra NFC bổ sung có ích để chẩn đoán, nhưng **không thay thế exact equality**.

**Long-text streaming:** `assertSameCharacters` đọc từng UTF-16 char qua `Reader` và so với expected, trả số chars thực nhận. Tối ưu về memory phía **đọc từ ResultSet**, nhưng fixture `large` vẫn được tạo nguyên trong RAM để có expected. Với dữ liệu rất lớn, có thể thay bằng generator/digest streaming theo contract đã xác minh.

**Cleanup:** phương thức `rollback` được gọi ngay cả khi assert thất bại. Nếu connection/DBMS đứt giữa chừng, chương trình không thể bảo đảm cleanup toàn bộ external effects; chỉ chạy trong môi trường thử an toàn.

### 8.3. Biên dịch

```bash
javac --release 17 -encoding UTF-8 JdbcUnicodeRoundTrip.java
```

Lệnh biên dịch chỉ cần JDK; lúc **chạy** phải có JDBC driver/library vendor trên runtime classpath và DB/test table thật.

### 8.4. Cách chạy với database của bạn

Trên Linux/macOS, sau khi xác nhận URL/driver/database/sandbox:

```bash
# Export các biến bằng giá trị cấu hình thật của môi trường test.
# Không ghi credentials vào source hoặc commit vào repository.
export JDBC_URL
export JDBC_USER
export JDBC_PASSWORD
export JDBC_TEST_TABLE=jdbc_unicode_probe
export JDBC_USE_NATIONAL=false

# Đặt driver.jar là đường dẫn JAR driver bạn đã được cấp/cài đúng.
java -cp "driver.jar:." JdbcUnicodeRoundTrip
```

Các dòng `export JDBC_URL` chỉ xuất những biến **đã được shell/công cụ quản lý secrets cấp sẵn**; nếu chưa có, chương trình sẽ báo thiếu `JDBC_URL` thay vì kết nối. Trong pipeline CI nên inject secrets an toàn. Không đưa password thật vào tài liệu, sample repo hoặc nhật ký dòng lệnh.

Trên Windows PowerShell:

```powershell
# JDBC_URL, JDBC_USER và JDBC_PASSWORD phải được cấu hình trước
# bằng hệ thống secrets/môi trường test tương ứng.
$env:JDBC_TEST_TABLE = "jdbc_unicode_probe"
$env:JDBC_USE_NATIONAL = "false"
java -cp 'driver.jar;.' JdbcUnicodeRoundTrip
```

**Đây là ví dụ chạy có điều kiện**, không có stdout cố định từ DBMS. Các dòng `db=...`/`driver=...`, cờ metadata và `largeUtf16Chars=...` phụ thuộc database/driver/schemas. Nếu assertions vượt qua, bạn sẽ thấy `shortExact=PASS`, `longStreamExact=PASS` và `rollback=REQUESTED`. **Chưa chạy integration program với DBMS thật trong phiên kiểm chứng này**, nên không tuyên bố PASS cho một vendor cụ thể.

## 9. Cần kiểm tra gì trong DatabaseMetaData?

`DatabaseMetaData` giúp quan sát môi trường thực tế:

| API | Thông tin | Hạn chế |
| --- | --- | --- |
| `getDatabaseProductName()` / `getDatabaseProductVersion()` | DBMS và version. | Không phải bảng tra tự động mọi tính năng tương thích. |
| `getDriverName()` / `getDriverVersion()` | JDBC driver/version. | Cùng DB version nhưng driver khác có thể hành xử khác. |
| `getTypeInfo()` | Các SQL type được quảng cáo, JDBC `DATA_TYPE` và tên `TYPE_NAME`. | Có entry `NVARCHAR`/`NCLOB` chưa chắc mọi setter/column combination chạy được. |
| `getColumns(...)` | Schema, column type, type name, column size, nullable và metadata khác. | Case sensitivity/schema/catalog wildcard có thể khác vendor; cần đối chiếu DDL thật. |
| `supportsTransactions()` | DB/driver công bố hỗ trợ transactions. | Không chứng minh bảng hiện dùng có rollback semantics phù hợp. |
| `supportsBatchUpdates()` | Công bố hỗ trợ JDBC batch updates. | Không chứng minh throughput/atomicity/LOB streaming trong batch. |
| `getMaxCharLiteralLength()` | Giới hạn literal ký tự mà DB có thể xử lý. | Không trực tiếp là giới hạn bind parameter LOB; giá trị 0 có thể nghĩa không rõ/không giới hạn. |
| `getMaxRowSize()` | Giới hạn kích thước row được metadata công bố. | Không thay cho limit thực của LOB/out-of-row storage. |
| `getSQLStateType()` | Kiểu SQLState mà driver báo. | Không khiến mọi vendor dùng cùng error codes. |
| `getDefaultTransactionIsolation()` | Isolation mặc định. | Không chứng minh all transactions/LOB features supported. |

Ví dụ mảnh thăm dò cột:

```java
// Đặt trong method có Connection c và thử table tương ứng.
DatabaseMetaData meta = c.getMetaData();
try (ResultSet columns = meta.getColumns(
        null, null, "jdbc_unicode_probe", "%")) {
    while (columns.next()) {
        System.out.println(columns.getString("COLUMN_NAME")
                + " -> " + columns.getString("TYPE_NAME")
                + " / size=" + columns.getInt("COLUMN_SIZE"));
    }
}
```

**Chú ý** `getColumns` có catalog/schema patterns và identifier-case rules của từng DBMS; nếu không trả hàng, có thể cần truyền đúng schema/case, **không lập tức kết luận bảng không tồn tại**.

Tương tự, `ResultSetMetaData.getColumnType/getColumnTypeName` cung cấp thông tin của kết quả SELECT, hữu ích khi mapping `CLOB`/`NCLOB`/`VARCHAR`. Hai nguồn metadata phải được đối chiếu với schema thực và integration test.

### 9.1. Unsupported features phải được kiểm chứng bằng thao tác

Một driver có thể ném:

```java
java.sql.SQLFeatureNotSupportedException
```

khi `setNString`, `setNCharacterStream`, `setNClob` hoặc `getNClob` chưa hỗ trợ. Nhưng có thể gặp `SQLException` khác (conversion/unsupported type/driver-specific). Bắt và báo rõ **method nào, column SQL type nào, DB/driver version nào, SQLState/vendor code nào**.

Không lặng lẽ fallback mọi unsupported national stream sang binary hoặc một kiểu khác: có thể thay đổi semantics/làm hỏng Unicode. Một fallback chỉ hợp lệ nếu **đã xác minh** cột và driver thực sự bảo toàn Unicode theo cách bind mới.

## 10. Bộ kiểm thử khả năng hỗ trợ DBMS nên gồm những lớp nào?

Một test suite đáng tin có thể tách thành:

### 10.1. Unit tests phía Java

- Unicode fixtures và `Normalizer`.
- UTF-8 encode/decode strict; reject invalid surrogate.
- Tạo payload lớn theo generator.
- So sánh Reader theo chunks, không phụ thuộc timing.
- Kiểm tra ranh giới surrogate pairs và string length units.

**Không cần DB**, nhanh và deterministic. Chương trình ở mục 6 là ví dụ.

### 10.2. Driver discovery và environment checks

- Driver JAR có mặt ở runtime; `DriverManager.getConnection` nhận URL vendor.
- Driver version và DB product/version được ghi lại.
- Database charset/column types/collations được xác minh.
- Test credentials chỉ có quyền trên môi trường thử, không production.
- LOB/network timeouts/buffer settings được ghi rõ trong test report.

### 10.3. Integration round-trip tests

- `setString/getString` trên text Unicode-compatible.
- `setNString/getNString` **chỉ khi** DB/driver hỗ trợ national type.
- `setCharacterStream/getCharacterStream` trên large text.
- `setNClob/getNClob` hoặc `setNCharacterStream/getNCharacterStream` trên NCLOB thích hợp.
- `setBinaryStream/getBinaryStream` cho BLOB với bytes định danh rõ.
- NULL so với empty, near-limit và over-limit payload.
- Exact equality và optional Unicode normalization/collation tests.
- Transaction rollback/cleanup.
- Dữ liệu rất lớn với memory/latency instrumentation.

### 10.4. Compatibility matrix

Với mỗi tổ hợp **DBMS version × JDBC driver version × Java runtime × charset/collation × column type**, ghi lại:

| Hạng mục | Kết quả cần ghi |
| --- | --- |
| `setString/getString` | PASS/FAIL, exact comparison, SQLState nếu lỗi. |
| `setNString/getNString` | PASS/UNSUPPORTED/FAIL theo column national type. |
| `setCharacterStream/getCharacterStream` | PASS/FAIL, kích thước và thời gian đọc/ghi. |
| `setNClob/getNClob` | PASS/UNSUPPORTED/FAIL, cleanup LOB locator. |
| Unicode BMP + supplementary | Có bảo toàn code points/UTF-16 char units không? |
| NFC vs NFD | DB giữ raw representation hay normalize? SQL equality/collation ra sao? |
| LOB 1 MB / 10 MB / nhiều GB (nếu phù hợp) | Bộ nhớ, thời gian, errors, driver buffering behavior. |
| Truncation | Error/warning/readback mismatch, SQLState và DB settings. |
| Transactions | Rollback có loại bỏ test row không? |
| Batch updates | Có hỗ trợ, có thật sự phù hợp với LOB stream không? |
| Schema/index | Unique/search/order/collation có đúng nghiệp vụ không? |

**Không đưa “UNSUPPORTED” thành “PASS”**; một API không được driver hỗ trợ là kết quả tương thích cần hiển thị rõ. Và không coi metadata khai báo hỗ trợ là kết quả pass của round-trip.

## 11. Chuẩn hóa Unicode, collation, tìm kiếm và unique keys

Giả sử hai chuỗi:

```text
café      (U+00E9: composed é)
café     (e + U+0301: decomposed)
```

Trên Java, hai chuỗi có thể không `equals` dù hiển thị tương tự. Trong DB, một collation có thể coi chúng bằng nhau hoặc không tùy vendor/collation/version. Một index `UNIQUE`, `ORDER BY`, `LIKE` và `=` không có semantic “chuỗi codepoints byte-for-byte” chung cho mọi hệ.

Do đó có ít nhất **ba yêu cầu khác nhau**:

1. **Storage fidelity:** đọc lại chính xác những gì đã ghi.
2. **Search equivalence:** khi tìm kiếm, người dùng gõ NFC/NFD hoặc dấu khác có được match không?
3. **Uniqueness/security:** những chuỗi có vẻ giống nhau có bị gộp hay tách theo chính sách của sản phẩm không?

Nếu sản phẩm cần chuẩn hóa để tìm kiếm, có thể lưu **raw value** và thêm một **canonical search key** được tạo theo quy tắc được tài liệu hóa. Không âm thầm normalize/casefold toàn bộ dữ liệu lưu nếu có hậu quả về danh tính, pháp lý hoặc chữ ký số.

**Quan trọng:** `Normalizer` **không** tương đương `String.toLowerCase`, Unicode case folding hay DB collation. Và một kết quả SQL `WHERE text = ?` không chứng minh dữ liệu raw được bảo toàn. Luôn test `SELECT` và so exact trên Java để xác minh storage.

### 11.1. Collation và index có thể thay đổi behavior theo upgrade

CLDR/Unicode tables, DBMS collations và driver conversion logic có thể thay đổi giữa versions. Cần regression tests cho tên người, địa chỉ, tiếng Việt có dấu, emoji và case-insensitive queries sau khi nâng DBMS/driver/JDK.

Không viết test hardcode kết quả order của những chuỗi gần nhau rồi coi đúng mọi collation. Hãy ghi rõ DB version và collation (ví dụ case/accent sensitivity) của môi trường kiểm chứng.

## 12. Byte, char, code point và giới hạn độ dài

| Biểu thức | Đếm gì? | Có phù hợp làm JDBC Reader length? |
| --- | --- | --- |
| `s.length()` | Java UTF-16 code units. | **Có**, với `StringReader` trên `s` trong overload cần length. |
| `s.codePointCount(0, s.length())` | Unicode code points. | **Không nhất thiết**, vì supplementary char chiếm 2 UTF-16 units. |
| `s.getBytes(UTF_8).length` | UTF-8 bytes. | **Không** phải character-stream length; dùng cho binary byte payload. |
| `Clob.length()` | Số ký tự theo JDBC CLOB abstraction. | `long`, phụ thuộc driver/DBMS semantics; không áp vào bytes tự động. |
| `ResultSetMetaData.getPrecision` | Precision metadata cho cột. | Không trực tiếp là kích thước UTF-8 payload trên wire. |

Ví dụ:

```java
String emoji = "😀";
int utf16 = emoji.length(); // 2
int points = emoji.codePointCount(0, emoji.length()); // 1
int utf8Bytes = emoji.getBytes(StandardCharsets.UTF_8).length; // 4
```

Các chỉ số đều đúng **trong đơn vị của chúng**. Đặt giới hạn như “100 ký tự” cho UI có thể phải định nghĩa grapheme clusters, không phải `String.length()`. Với DBMS, cần biết cột giới hạn theo bytes/codepoints/UTF-16 units và có space dành cho supplementary characters.

**Đừng để stream length sai:** truyền `utf8Bytes` cho `setCharacterStream` có thể khiến driver chờ thêm characters hoặc ném lỗi, tùy overload/implementation. Ngược lại, truyền `String.length()` cho `setBinaryStream` có thể cắt bytes.

## 13. Tính năng JDBC và dữ liệu lớn: những bẫy hiệu năng

- `getString` có thể tạo toàn bộ giá trị lớn thành Java String, gây heap pressure.
- `setCharacterStream` **cho phép** truyền Reader nhưng driver có thể buffer dữ liệu trước khi gửi; phải đo thực tế.
- Một batch INSERT rất nhiều LOB có thể giữ Readers/buffers lâu; hãy test kích thước batch, transaction và driver memory.
- Autocommit trên từng row có thể tăng chi phí log/round-trip; gom transaction hợp lý, không tạo transaction quá lớn gây disk pressure.
- `ResultSet.setFetchSize`/`Statement.setFetchSize` là **hint**, không đảm bảo server cursor/streaming ở mọi driver.
- `PreparedStatement.setFetchSize` và JDBC fetch settings không tự chuyển `CLOB` thành constant-memory stream.
- Driver có thể đóng input stream khi statement được thực thi hoặc khi statement/result set đóng; giữ stream scope đúng và đọc hết trước khi chuyển row nếu cần.
- Một driver có thể giới hạn payload cho LOB streaming qua network packet/SSL/TLS buffer hoặc kích thước row; cần test cả lỗi lẫn throughput.
- `SQLException` lớn hoặc timeout cần phân loại; tránh retry vô hạn trên một transaction/connection hỏng.

### 13.1. Stress test phải đo cả DB server

Các metrics hữu ích:

- Client heap/GC, resident memory, allocation, time-to-first-byte.
- Database CPU, WAL/redo/transaction log, temporary storage, LOB tablespace.
- Network throughput và reconnects.
- Average/p95/p99 insert/read latency theo kích thước text.
- Truncation/unsupported feature errors theo driver/version.
- Connection pool active/idle/waiting, acquisition timeout và max lifetime.
- Batch throughput, rollback cost, cleanup time.

Test dữ liệu khổng lồ nên chạy trong **sandbox có quota** để không làm đầy production storage hoặc transaction log. Đừng xem `rollback` là miễn phí: DB vẫn có thể tiêu tốn log, CPU, locks và side effects trước khi hoàn tác.

## 14. DBMS-specific Unicode chú ý gì?

### 14.1. MySQL — ưu tiên utf8mb4

Trong MySQL 8.4, tài liệu chính thức xác nhận:

- `utf8mb4` hỗ trợ BMP **và supplementary** Unicode characters, tối đa 4 byte UTF-8/character.
- `utf8mb3` chỉ hỗ trợ BMP và đã **deprecated**; không chọn cho ứng dụng mới.
- Alias `utf8` có liên hệ lịch sử với `utf8mb3`, nên khi yêu cầu emoji/supplementary hãy **cấu hình rõ `utf8mb4`** theo DB/column/connection settings.

Test không chỉ `SHOW CREATE TABLE` mà cả connection character set, column collation, JDBC driver version và round-trip emoji. Không dựa vào chuyện MySQL JDBC `getNString` có tương đương Oracle/SQL Server; mỗi driver có type mapping riêng.

### 14.2. Microsoft SQL Server — NVARCHAR và collation

SQL Server cung cấp `NCHAR`/`NVARCHAR` cho Unicode text. Tài liệu Microsoft phân biệt supplementary-character-aware collations (được ghi nhận với `_SC` và các collations mới) và UTF-8 collations cho `VARCHAR` trên phiên bản phù hợp.

Khi test supplementary emoji, chú ý SQL string length/substrings và collation: cùng một chuỗi có thể được hàm SQL xử lý theo code units hoặc code points tùy collation. Đừng mặc định cách SQL Server `LEN` đếm có ý nghĩa giống `String.length()` hoặc ngược lại.

### 14.3. PostgreSQL và các DBMS Unicode khác

PostgreSQL với database encoding UTF8 có thể sử dụng `TEXT`/`VARCHAR` lưu Unicode; việc dùng `setNString` không phải yêu cầu chung cho mọi text Unicode. Chọn JDBC setter theo **column mapping thực**, không theo suy luận “Unicode => N prefix”.

Với Oracle Database, cần phân biệt database character set và national character set, các kiểu `VARCHAR2`/`NVARCHAR2`/`CLOB`/`NCLOB` và khả năng JDBC driver tương ứng.

**Bài học xuyên DBMS:** một tên API Java có thể tồn tại ở mọi JDK nhưng feature support, SQL type, length semantics, collation và conversion phụ thuộc **server + driver + column schema**. Không có phép thử metadata đơn lẻ thay được round-trip tests.

## 15. An toàn, bảo mật và tính đúng đắn khi kiểm thử JDBC

- Chỉ dùng `PreparedStatement` cho giá trị dữ liệu; không nối input người dùng trực tiếp vào SQL.
- Cột/bảng SQL identifiers không bind bằng `?`; chỉ sử dụng tên đã kiểm soát/whitelist.
- Không đặt database credentials vào source code, sample README, test output hoặc CI logs.
- Tách tài khoản test và production, giới hạn quyền tối thiểu.
- Không ghi text người dùng thật/PII vào dataset thử nghiệm khi không cần.
- Dùng test fixtures synthetic và có kiểm soát.
- Giữ `Connection`/`Statement`/`ResultSet`/`Reader` đúng lifecycle, đóng bằng try-with-resources.
- Khi dùng `Clob`/`Blob`/`NClob` locator, xem contract `free()`/`close()` và phạm vi transaction.
- Bắt `SQLFeatureNotSupportedException` hoặc `SQLException` và ghi DB/driver version, operation, SQLState; không ép fallback gây mất dữ liệu.
- Định nghĩa trước việc expected round-trip là **exact code units** hay normalization-equivalent; không tự đổi tiêu chí sau khi test fail.
- Không chạy stress test LOB hàng GB trên database production hoặc trên đường truyền/cluster chưa có quota.
- Kiểm tra transaction cleanup và bảng test không bị để lại dữ liệu sau khi assertion fail.
- Không lưu raw credentials hoặc full connection URL vào báo cáo public; các URL có thể chứa secret.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng |
| --- | --- | --- |
| Emoji thành `?` | Charset/cột/driver conversion không hỗ trợ supplementary. | Ghi `😀`/`𐐷`, đọc exact, kiểm tra DB charset. |
| Tiếng Việt mất dấu | Sai encoding/collation/transcoding trước hoặc trong JDBC. | Test UTF-8 input, bind parameter, raw readback. |
| Chuỗi giống nhau trên UI nhưng `equals=false` | NFC vs NFD/combining marks. | So code points và `Normalizer`. |
| SQL equality khác Java `equals` | DB collation case/accent normalization. | Test SQL `=`/unique riêng raw readback. |
| `VARCHAR(n)` bất ngờ truncate | Đơn vị length/charset/DB mode khác mong đợi. | Test n−1,n,n+1 và đọc lại exact. |
| `setNString` không hỗ trợ | Driver/server/column không có national character semantics tương ứng. | `getTypeInfo` + test bind/read trên schema thật. |
| Metadata nói có `NCLOB` nhưng test fail | Type advertisement không bảo đảm mọi overload và driver behavior. | Gọi `setNClob/getNClob` với cột thật. |
| Gửi Reader với length sai | Nhầm UTF-8 bytes/code points với UTF-16 Reader chars. | Với StringReader dùng `String.length()`. |
| Large payload làm OOM | Gọi `getString/getBytes` hoặc driver tự buffer. | Stream và profile heap, test driver config. |
| Reader đóng quá sớm | Đóng trước khi `executeUpdate` đọc xong. | Giữ mở trong statement execution scope. |
| ResultSet stream đọc lỗi | Chuyển row/đóng statement trước khi đọc hết. | Đọc trước khi `rs.next()`/close. |
| `Clob` locator không còn hợp lệ | Vượt transaction/connection lifecycle. | Đọc/free trong scope đã quy định. |
| SQLFeatureNotSupportedException | JDBC feature/overload chưa được driver triển khai. | Đọc docs driver, ghi feature support matrix. |
| Unsupported conversion báo SQLException khác | Không phải mọi driver báo cùng exception class. | SQLState/vendor code + observed readback. |
| DB rollback không xóa dữ liệu | Bảng/engine/DDL/triggers không theo transaction assumptions. | Test trên sandbox, xem storage/engine. |
| Test báo PASS nhưng SQL search sai | Chỉ test storage, không test collation/index. | Kiểm tra search/unique/order theo yêu cầu. |
| Mất dữ liệu khi nâng driver/JDK | Thay mapping/encoding/driver buffering/collation. | Regression test tổ hợp versions. |
| Ký tự ngoài BMP bị cắt giữa stream chunks | Parser/streaming code tách surrogate pair. | Test emoji sát buffer boundary. |
| Input chứa lone surrogate bị thay ký tự | Encoder mặc định có replacement policy. | `CharsetEncoder` với `REPORT`. |
| Database stress test gây disk/lock pressure | Payload lớn và transaction/log nhiều. | Dùng test DB có quota và monitoring. |

## 17. Checklist QA trước khi phát hành

1. Đã ghi DBMS/version, JDBC driver/version, JDK version, charset và collation của test environment?
2. Table test có đúng column types/sizes theo schema thật?
3. Có fixture tiếng Việt precomposed và decomposed?
4. Có emoji và supplementary code point khác emoji?
5. Có test Unicode code units, code points và UTF-8 bytes riêng?
6. Có test text empty vs SQL NULL?
7. Có test string giới hạn n−1, n, n+1 theo semantics cột?
8. `setString/getString` exact round-trip PASS trên cột text chính?
9. `setNString/getNString` được test khi DB hỗ trợ national chars, không gán default PASS?
10. `setCharacterStream/getCharacterStream` được test với payload lớn và Reader đúng scope?
11. `NCLOB` được test riêng qua `setNClob/getNClob` khi cần?
12. Binary BLOB được test theo byte stream riêng, không nhầm text encoding?
13. `DatabaseMetaData.getTypeInfo` được lưu lại cùng kết quả thực thi API?
14. Có kiểm tra warnings/truncation/SQLState thay vì chỉ `executeUpdate()==1`?
15. Có kiểm tra raw Java String equality **và** normalization/search/collation theo mục tiêu sản phẩm?
16. Streaming có được profile memory, latency và resource lifecycle?
17. Có test transaction rollback/cleanup và đảm bảo không còn test rows?
18. Pool/connection limits và stress test quota được xác định?
19. Query use case thật có dùng `PreparedStatement` và tránh SQL injection?
20. Test lại khi nâng JDK/driver/DBMS/charset/collation?

## 18. Bài tập thực hành

**A — Unicode units.** Với `"😀"` và `"e\u0301"`, in `length`, `codePointCount` và UTF-8 byte length. Tại sao không thể dùng một giá trị thay cho ba đơn vị?

**B — NFC/NFD.** Tạo các cặp `"\u00E9"`/`"e\u0301"`. Test raw equality, NFC equality và NFD equality. Chọn policy khi lưu tên người và khi xây search key.

**C — Ký tự lỗi.** Đổi mẫu `"\uD83D"` trong `UnicodeFixturesCheck` thành high-surrogate + low-surrogate hợp lệ; xem encoder có tiếp tục báo lỗi không. Giải thích sự khác nhau giữa reject/replace policy.

**D — Large Reader.** Thay số lần `repeat` từ 55.000 lên 150.000 trong test sandbox, đo heap/time. Phân biệt chương trình dùng String fixture với chương trình phát sinh chars thực sự theo stream.

**E — Database round-trip.** Dựng bảng riêng trên DBMS bạn dùng, chọn đúng cột Unicode-safe rồi chạy `JdbcUnicodeRoundTrip`. Ghi lại DB/driver version, metadata và exact assertions. Đừng chạy trên bảng production.

**F — National character APIs.** Nếu driver có national type, dùng `JDBC_USE_NATIONAL=true` và cột tương ứng. Nếu driver không hỗ trợ, ghi UNSUPPORTED thay vì sửa test để che lỗi.

**G — LOB.** Bổ sung phép thử `setNClob/getNClob` hoặc `setBinaryStream/getBinaryStream`, sử dụng table chứa cột type tương ứng. Xác minh exact value/digest và cleanup.

**H — Truncation.** Thử một chuỗi vượt độ rộng cột trong sandbox. Quan sát error, warning hoặc raw mismatch; không giả định DB luôn từ chối như nhau.

**I — Collation.** Thử SQL equality, unique và ORDER BY trên hai chuỗi khác representation, test cả case và accent sensitivity. So với `String.equals` phía Java.

**J — Compatibility.** Tái chạy cùng bộ fixtures với hai phiên bản JDBC driver hoặc hai DBMS được tổ chức hỗ trợ. Lập bảng PASS/UNSUPPORTED/FAIL theo từng API và kiểu cột.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `String.length()` của `"😀"` trả 1 đúng không?

**Đáp án:** Không, Java `String` dùng UTF-16; supplementary code point này chiếm 2 `char`. `codePointCount` trả 1 và UTF-8 có 4 bytes.

**Câu 2.** Nếu SQL INSERT thành công có thể coi Unicode round-trip PASS chưa?

**Đáp án:** Chưa. Phải SELECT lại và so exact, test both BMP/supplementary và kiểm tra truncation/conversion.

**Câu 3.** `setNString` có phải luôn đúng hơn `setString` khi chuỗi chứa tiếng Việt?

**Đáp án:** Không. Việc chọn API phụ thuộc SQL column national-character semantics, driver và DBMS. Một cột TEXT/VARCHAR có charset Unicode phù hợp có thể hoạt động đúng với `setString`.

**Câu 4.** `getTypeInfo` quảng cáo `NCLOB` có bảo đảm `setNClob/getNClob` hoạt động trên mọi cột không?

**Đáp án:** Không. Metadata là thông tin được driver công bố; cần test thật với column type/driver/version và overload cụ thể.

**Câu 5.** Vì sao phải test emoji khi đã test tiếng Việt?

**Đáp án:** Nhiều chữ tiếng Việt thuộc BMP; emoji thường ngoài BMP và cần surrogate pair/4-byte UTF-8. Một hệ chỉ hỗ trợ BMP có thể PASS với tiếng Việt nhưng FAIL emoji.

**Câu 6.** Tại sao `setCharacterStream` dùng `large.length()` chứ không `getBytes(UTF_8).length`?

**Đáp án:** Reader cung cấp chars, không phải bytes. Với `StringReader`, số UTF-16 `char` là `String.length()`; UTF-8 bytes có thể nhiều hơn.

**Câu 7.** `getCharacterStream` có bảo đảm JVM luôn dùng bộ nhớ O(1) với một LOB hàng GB không?

**Đáp án:** Không. API cho phép đọc theo stream; driver, database protocol và phía client có thể buffer. Phải đo thực tế.

**Câu 8.** Vì sao phải phân biệt NFC equivalence với Java raw equality và DB collation?

**Đáp án:** Hai chuỗi có thể biểu diễn Unicode khác nhau nhưng canonical-equivalent, và collation có thể xem nhiều chuỗi khác nhau là bằng; ba tiêu chí không đồng nhất.

**Câu 9.** `SQLFeatureNotSupportedException` là dấu hiệu database đã làm hỏng dữ liệu Unicode đúng không?

**Đáp án:** Không. Nó cho biết một JDBC method/feature không được driver hỗ trợ. Ghi UNSUPPORTED và test phương án khác phù hợp, không tự coi data corruption.

**Câu 10.** Bài test đã xác minh DBMS nào PASS?

**Đáp án:** Chưa có DBMS được chạy trong bài này. Chương trình Java-only đã chạy PASS và chương trình JDBC integration đã biên dịch; kết quả DBMS thật phụ thuộc môi trường bạn cấu hình và chỉ được ghi nhận sau khi thực thi.

## 20. Tài liệu chính thức, hiện hành

- [PreparedStatement — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): `setString`/`setNString`, `setCharacterStream`/`setNCharacterStream`, `setNClob`, `setBinaryStream` và `SQLFeatureNotSupportedException`.
- [ResultSet — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): `getString/getNString`, character streams, CLOB/NCLOB/BLOB, result lifecycle.
- [DatabaseMetaData — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DatabaseMetaData.html): `getTypeInfo`, `getColumns`, support flags và product/driver metadata.
- [Types — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Types.html): `VARCHAR`, `NVARCHAR`, `CLOB`, `NCLOB`, `BLOB` và các type codes.
- [Clob — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Clob.html), [NClob](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/NClob.html), [Blob](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Blob.html): LOB streams, length và cleanup.
- [SQLFeatureNotSupportedException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html), [DataTruncation](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DataTruncation.html): unsupported features và truncation diagnostics.
- [Normalizer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD, Unicode normalization.
- [MySQL 8.4 Unicode support](https://dev.mysql.com/doc/refman/8.4/en/charset-unicode.html): `utf8mb4`, supplementary characters và `utf8mb3` deprecated.
- [SQL Server Unicode and collations](https://learn.microsoft.com/en-us/sql/relational-databases/collations/collation-and-unicode-support): `NVARCHAR`, supplementary characters và collation behavior.

**Ghi nhớ:** Test JDBC Unicode phải **ghi → đọc lại → so chính xác**, không chỉ INSERT thành công. Dữ liệu lớn cần phân biệt **chars, code points, UTF-8 bytes và giới hạn cột**, đọc/ghi stream với lifecycle đúng và đo memory/driver buffering. DBMS feature support cần xem **schema + metadata + thử thao tác thật**, bởi API có mặt trong JDK không bảo đảm driver/server hỗ trợ mọi national/LOB methods. Bộ Java-only chỉ xác minh fixtures; tích hợp JDBC chỉ được coi PASS sau khi chạy trên DBMS/driver/version cụ thể và rollback sạch.
