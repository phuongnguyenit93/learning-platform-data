# Đánh giá ảnh hưởng của collation tới so sánh và sắp xếp

> **Chương:** Số và văn bản  
> **Ngữ cảnh:** Ứng dụng Java sử dụng JDBC để đọc, ghi và truy vấn văn bản trong cơ sở dữ liệu quan hệ.

Khi tìm một khách hàng tên `Lan`, ứng dụng có nên trả về cả `lan` và `Lán` không? Khi sắp xếp danh sách họ tên tiếng Việt, `Đ` đứng ở đâu? Hai chuỗi nhìn giống nhau có được coi là trùng khi đặt ràng buộc `UNIQUE` không? Những câu hỏi này không thể được giải quyết chỉ bằng `PreparedStatement.setString()` hay kiểu cột `VARCHAR`: kết quả còn phụ thuộc vào **collation** mà hệ quản trị cơ sở dữ liệu áp dụng.

Bài học tập trung vào cách nhận diện, kiểm chứng và đánh giá tác động của collation đến phép so sánh, thứ tự sắp xếp, tính duy nhất và hiệu năng truy vấn JDBC. Ví dụ SQL chính sử dụng **MySQL 8.0+** để có kết quả quan sát được; tên collation và một số hành vi không thể bê nguyên sang PostgreSQL, SQL Server hoặc hệ quản trị khác.

## 1. Collation quyết định điều gì?

**Collation** là tập quy tắc mà cơ sở dữ liệu dùng để so sánh và xác định thứ tự của các chuỗi ký tự. Tùy hệ quản trị, collation có thể xét đến:

- **Ngôn ngữ/vùng (locale):** quy tắc sắp xếp chữ cái của tiếng Việt hoặc một ngôn ngữ cụ thể.
- **Chữ hoa và chữ thường:** `Lan` và `lan` có được xem là tương đương hay không (*case sensitivity*).
- **Dấu phụ:** `Lan` và `Lán` có được xem là tương đương hay không (*accent sensitivity*).
- **Mức độ so sánh:** có phân biệt các biến thể ký tự, ký hiệu hoặc dạng biểu diễn Unicode hay không, tùy bộ quy tắc.
- **Đặc điểm riêng của hệ quản trị:** xử lý khoảng trắng cuối chuỗi, ký tự kết hợp, phiên bản thuật toán Unicode và các quy tắc bổ sung.

Phân biệt ba khái niệm dễ bị nhầm:

| Khái niệm | Chức năng | Ví dụ |
|---|---|---|
| **Character set/encoding** | Biểu diễn và lưu ký tự thành dữ liệu; quyết định tập ký tự có thể lưu | `utf8mb4` trong MySQL |
| **Collation** | Quyết định hai giá trị văn bản được so sánh và sắp xếp ra sao | `utf8mb4_0900_ai_ci` |
| **Kiểu dữ liệu** | Quy định dạng giá trị và những giới hạn của cột | `VARCHAR(100)`, `TEXT` |

Hai cột cùng dùng Unicode và `VARCHAR(100)` vẫn có thể cho kết quả `WHERE`, `ORDER BY` hoặc `UNIQUE` khác nhau nếu collation khác nhau. Ngược lại, việc truyền tham số đúng qua JDBC không tự chọn quy tắc so sánh mới cho cột.

Trong MySQL, hậu tố thường gặp là `ci` (*case-insensitive*), `cs` (*case-sensitive*), `ai` (*accent-insensitive*) và `as` (*accent-sensitive*). Ví dụ `utf8mb4_0900_ai_ci` không phân biệt dấu và chữ hoa/thường theo quy tắc của nó; `utf8mb4_0900_as_cs` phân biệt cả hai. Các ký hiệu này **không phải tên hay quy ước collation chung của mọi DBMS**.

## 2. Một bộ dữ liệu để đo tác động

Để tránh kết luận dựa trên cảm giác về thứ tự chữ cái, hãy chạy cùng một bộ dữ liệu dưới các quy tắc khác nhau. Ví dụ sau dành cho MySQL 8.0+:

```sql
CREATE TABLE contacts (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci NOT NULL,
    INDEX idx_contacts_display_name (display_name)
);

INSERT INTO contacts (id, display_name) VALUES
    (1, 'Lan'),
    (2, 'lan'),
    (3, 'Lán'),
    (4, 'Bình'),
    (5, 'Mai'),
    (6, 'mai');
```

Cột `display_name` sử dụng `utf8mb4_0900_ai_ci` và có chỉ mục để so sánh chi phí truy vấn về sau. Dữ liệu có cả trường hợp khác chữ hoa/thường và trường hợp khác dấu. Hãy giữ các hàng này khi thực hiện những truy vấn tiếp theo.

### 2.1. So sánh bằng (`=`)

```sql
-- Theo collation mặc định của cột: không phân biệt hoa/thường và dấu.
SELECT id, display_name
FROM contacts
WHERE display_name = 'lan'
ORDER BY id;
```

Với collation của bảng mẫu, kết quả gồm các hàng `1: Lan`, `2: lan` và `3: Lán`. Cả ba đều được coi là tương đương với chuỗi tìm kiếm `lan` **trong phép so sánh SQL này**. Điều đó không có nghĩa dữ liệu gốc bị biến đổi: `ResultSet.getString("display_name")` vẫn đọc từng chuỗi như đã lưu.

Thay đổi collation tại **biểu thức truy vấn**, giữ nguyên dữ liệu:

```sql
SELECT id, display_name
FROM contacts
WHERE display_name COLLATE utf8mb4_0900_as_cs = 'lan'
ORDER BY id;
```

Kết quả chỉ còn `2: lan`, bởi phép so sánh giờ phân biệt chữ hoa/thường và dấu. Bài kiểm chứng này cho thấy collation ảnh hưởng trực tiếp đến số bản ghi mà DAO/repository JDBC lấy về dù tham số truy vấn giữ nguyên.

| So sánh với `'lan'` | `utf8mb4_0900_ai_ci` | `utf8mb4_0900_as_cs` |
|---|---|---|
| `'Lan'` | Bằng | Khác |
| `'lan'` | Bằng | Bằng |
| `'Lán'` | Bằng | Khác |

**Không đồng nhất so sánh theo ngôn ngữ với so sánh mã ký tự.** Nếu yêu cầu nghiệp vụ là tìm kiếm thân thiện với người dùng, collation không phân biệt dấu có thể phù hợp. Nếu cần phân biệt chính xác mã định danh hoặc nội dung có ý nghĩa pháp lý, phải chọn cơ chế so khớp chặt chẽ tương ứng với yêu cầu, không mặc định rằng chữ trông tương tự là cùng một giá trị.

### 2.2. Sắp xếp (`ORDER BY`) và các nhóm đồng hạng

```sql
SELECT id, display_name
FROM contacts
ORDER BY display_name, id;
```

`ORDER BY display_name` dùng quy tắc của collation trên cột. Vì `Lan`, `lan` và `Lán` tương đương ở mức so sánh đang dùng, **chỉ sắp xếp theo `display_name` không quy định thứ tự giữa ba hàng này**. Thêm `id` làm khóa phụ để kết quả ổn định trong nhóm đồng hạng, đặc biệt quan trọng khi dùng `LIMIT`/`OFFSET` hoặc phân trang.

Để thấy thứ tự thay đổi khi yêu cầu phân biệt dấu và hoa/thường:

```sql
SELECT id, display_name
FROM contacts
ORDER BY display_name COLLATE utf8mb4_0900_as_cs, id;
```

Thứ tự cụ thể giữa các ký tự phải được kiểm tra trên **collation, phiên bản và dữ liệu thực tế**. Không được mặc định mọi collation Unicode đều xếp chữ cái tiếng Việt theo cùng một thứ tự; một collation đa ngôn ngữ không thay thế được quy tắc sắp xếp tiếng Việt nếu sản phẩm yêu cầu thứ tự từ điển tiếng Việt.

Điểm cần phân biệt: điều kiện `WHERE` quyết định *những hàng nào* khớp, còn `ORDER BY` quyết định *thứ tự những hàng đã chọn*. Một truy vấn có thể dùng hai collation khác nhau cho hai mục đích, nhưng cần chủ ý và kiểm tra tác động tới chỉ mục.

### 2.3. `LIKE`, `DISTINCT`, `GROUP BY` và `UNIQUE`

Collation còn chi phối nhiều thao tác liên quan tới tính tương đương văn bản, với chi tiết khác nhau giữa DBMS và phiên bản:

```sql
-- MySQL 8.0+ với collation của bảng mẫu:
SELECT id, display_name
FROM contacts
WHERE display_name LIKE 'la%'
ORDER BY id;

-- Ba cách viết tương đương chỉ tính là một giá trị DISTINCT.
SELECT COUNT(DISTINCT display_name) AS distinct_names
FROM contacts
WHERE id IN (1, 2, 3);
-- distinct_names = 1

-- Đếm các biến thể được xem là khớp cùng một tên.
SELECT COUNT(*) AS matching_rows
FROM contacts
WHERE display_name = 'lan';
-- matching_rows = 3
```

`GROUP BY display_name` cũng có thể gộp các biến thể theo quy tắc tương đương của collation. Nếu hiển thị một giá trị đại diện cho nhóm, cần quy định cách chọn đại diện, thay vì giả định tên hiển thị nào sẽ được trả về. Với `LIKE`, khả năng phân biệt hoa/thường và dấu phụ phụ thuộc vào DBMS/collation; đừng suy diễn hành vi của MySQL sang PostgreSQL hay SQL Server.

Một cột có ràng buộc duy nhất còn mang ý nghĩa nghiệp vụ:

```sql
CREATE TABLE contact_aliases (
    alias VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci NOT NULL UNIQUE
);

INSERT INTO contact_aliases (alias) VALUES ('Lan');
-- Lệnh tiếp theo vi phạm UNIQUE vì 'lan' tương đương 'Lan'.
INSERT INTO contact_aliases (alias) VALUES ('lan');
```

Hai tên hiển thị khác nhau có thể bị chặn bởi `UNIQUE` nếu collation coi chúng bằng nhau. Ngược lại, chọn collation phân biệt hơn có thể cho phép tạo hai giá trị mà người dùng coi là cùng tên. Khi đổi collation trên cột đã có dữ liệu, phải kiểm tra **xung đột giá trị duy nhất** trước khi sửa schema.

## 3. Kiểm tra collation đang được áp dụng

Không nên suy đoán từ cấu hình hệ điều hành, ngôn ngữ Java hay tên bảng. Collation có thể được khai báo ở mức database, bảng, cột hoặc biểu thức; cơ chế kế thừa và ưu tiên phụ thuộc DBMS.

Với MySQL, kiểm tra cấu hình cột và thông tin của phiên làm việc:

```sql
SHOW FULL COLUMNS FROM contacts;

SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME,
       CHARACTER_SET_NAME, COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'contacts';

SELECT @@collation_connection AS connection_collation,
       @@character_set_connection AS connection_charset;
```

Collation của **cột** là điều cần kiểm tra trước cho ví dụ `WHERE display_name = ?`; collation của **kết nối** cũng cần biết vì nó liên quan tới chuỗi literal và biểu thức được gửi vào SQL. Khi SQL kết hợp hai biểu thức có collation khác nhau, DBMS có quy tắc xác định collation nào thắng hoặc có thể báo xung đột. Không giả định collation của kết nối sẽ ghi đè collation đã khai báo trên cột.

Ở những hệ quản trị khác:

| Hệ quản trị | Hướng kiểm tra/cấu hình | Lưu ý khi chuyển SQL |
|---|---|---|
| MySQL 8.0+ | `SHOW FULL COLUMNS`, `information_schema.COLUMNS`, `COLLATE` | Dùng tên như `utf8mb4_0900_ai_ci`, `utf8mb4_0900_as_cs`. |
| PostgreSQL | Thông tin collation trong catalog và định nghĩa cột; có collation do `libc` hoặc ICU cung cấp | Tên, phiên bản ICU và thuộc tính *deterministic* ảnh hưởng hành vi; không có hậu tố `_ai_ci` kiểu MySQL. |
| SQL Server | `sys.columns`, `sys.types`, `COLLATIONPROPERTY`, `COLLATE` | Nhiều tên collation chứa `CI`/`CS`, `AI`/`AS`, nhưng là tên và quy tắc của SQL Server. |

Không dùng `COLLATE` của một DBMS làm SQL đa nền tảng. Nếu sản phẩm hỗ trợ nhiều cơ sở dữ liệu, cần adapter hoặc SQL dialect cùng bộ kiểm thử tương thích riêng.

## 4. Tác động tới truy vấn JDBC

JDBC cung cấp API chuẩn để kết nối, gửi SQL và đọc kết quả. **Bộ máy SQL của database** thực thi so sánh chuỗi theo collation đã xác định; `PreparedStatement` không tự biến phép `=` thành so khớp nhị phân, cũng không áp dụng `java.text.Collator` lên hàng trong bảng.

Ví dụ truy vấn có tham số và sắp xếp ổn định:

```java
// Giả sử dataSource đã được cấu hình cho MySQL 8.0+ và bảng contacts.
String inputName = "lan";
String sql = """
    SELECT id, display_name
    FROM contacts
    WHERE display_name = ?
    ORDER BY display_name, id
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setString(1, inputName);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            String name = rs.getString("display_name");
            System.out.printf("%d: %s%n", id, name);
        }
    }
}
```

Với bảng mẫu, câu lệnh này trả về ba biến thể của `lan`. `setString(1, inputName)` có hai vai trò quan trọng: truyền giá trị đúng kiểu và tránh nối trực tiếp dữ liệu người dùng vào câu SQL. Tuy nhiên, **tham số bind chỉ biểu diễn giá trị**, không lựa chọn collation hay thay đổi đặc điểm của cột.

Nếu giao diện cho phép chọn chế độ so khớp, hãy ánh xạ một enum đáng tin cậy sang **danh sách cố định** các tên collation; không chèn chuỗi tên collation do người dùng nhập:

```java
enum SearchMode { FRIENDLY, STRICT }

SearchMode mode = SearchMode.STRICT;
String collation = switch (mode) {
    case FRIENDLY -> "utf8mb4_0900_ai_ci";
    case STRICT -> "utf8mb4_0900_as_cs";
};

String sql = "SELECT id, display_name FROM contacts "
    + "WHERE display_name COLLATE " + collation + " = ? "
    + "ORDER BY display_name COLLATE " + collation + ", id";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "lan");
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id") + ": "
                + rs.getString("display_name"));
        }
    }
}
```

Đây là ví dụ **SQL riêng cho MySQL**. Không dùng `?` để thay thế tên collation: placeholder trong `PreparedStatement` dùng cho **giá trị**, không dùng cho tên cột, từ khóa SQL hoặc cú pháp chọn collation. Nếu chỉ có một chính sách so sánh cho ứng dụng, thường đơn giản và ổn định hơn khi định nghĩa đúng collation ngay tại schema.

### Phân trang và sắp xếp trong Java

Giả sử Java đọc 20 hàng từ câu SQL `LIMIT 20`, sau đó gọi `Collator.getInstance(Locale.forLanguageTag("vi-VN"))` để sắp xếp danh sách. Kết quả này **không bảo đảm** là 20 hàng đầu tiên theo thứ tự tiếng Việt mong muốn của toàn bộ bảng: database đã chọn trang trước khi Java sắp xếp. Ngoài ra, `java.text.Collator` và collation của DBMS có thể dùng phiên bản hoặc quy tắc khác nhau.

Với phân trang ở database, hãy dùng `ORDER BY` có collation phù hợp và một khóa phụ duy nhất, ví dụ `ORDER BY display_name, id`. Nếu cần quy tắc thứ tự giống nhau giữa màn hình, báo cáo và tác vụ nền, hãy thống nhất một nguồn quy tắc và kiểm thử bằng cùng tập dữ liệu; tránh để mỗi lớp tự sắp xếp theo một định nghĩa khác nhau.

## 5. Unicode, chuẩn hóa và những trường hợp dễ gây lỗi

Một ký tự hiển thị có thể có nhiều dạng biểu diễn Unicode. Chẳng hạn `á` có thể là ký tự dựng sẵn `U+00E1`, hoặc là `a` (`U+0061`) theo sau bởi dấu sắc kết hợp (`U+0301`). Hai chuỗi trông giống nhau nhưng dãy code point khác nhau:

```java
import java.text.Normalizer;

String composed = "\u00E1";       // á: một code point
String decomposed = "a\u0301";   // a + dấu sắc kết hợp

System.out.println(composed.equals(decomposed)); // false
System.out.println(
    Normalizer.normalize(composed, Normalizer.Form.NFC)
        .equals(Normalizer.normalize(decomposed, Normalizer.Form.NFC))
); // true
```

`String.equals()` của Java không phải phép so sánh SQL theo collation. Một số collation xử lý hai dạng Unicode là tương đương, trong khi những collation hoặc phép so sánh byte khác có thể phân biệt. **Chuẩn hóa NFC** đầu vào có thể giúp giảm các dạng biểu diễn khác nhau trong lưu trữ, nhưng không thay thế quyết định chính sách dấu, chữ hoa/thường và thứ tự sắp xếp.

Khi kiểm thử dữ liệu tiếng Việt, nên có trường hợp `Đ`/`D`, các dấu thanh và dấu nguyên âm (`a`, `ă`, `â`), chữ hoa/thường, khoảng trắng cuối và chuỗi Unicode ở dạng dựng sẵn/kết hợp. Đừng suy đoán `Đ` có tương đương `D` hay không chỉ từ tên collation chứa `_ai`: kết quả phải được đo trên collation thực tế. Đặc biệt, quy tắc khoảng trắng cuối có thể khác nhau giữa bộ collation, kiểu dữ liệu và DBMS.

Không dùng `String.compareTo()` để mô phỏng kết quả `ORDER BY` của database: phương thức này so sánh theo đơn vị mã UTF-16, không phải thứ tự từ điển theo locale. `String.equalsIgnoreCase()` cũng không phải bản sao của collation không phân biệt chữ hoa/thường trong SQL.

## 6. Ảnh hưởng đến chỉ mục và hiệu năng

Một chỉ mục trên cột văn bản lưu khóa phù hợp với quy tắc so sánh/sắp xếp của chỉ mục và hệ quản trị. Khi `WHERE` hoặc `ORDER BY` dùng quy tắc khác với quy tắc của chỉ mục, bộ tối ưu **có thể** không tận dụng được các thao tác tìm kiếm theo phạm vi hoặc thứ tự sẵn có, từ đó cần xử lý thêm. Mức độ ảnh hưởng phụ thuộc dữ liệu, kế hoạch truy vấn, phiên bản DBMS và cách biểu thức được viết.

So sánh hai kế hoạch trong MySQL:

```sql
EXPLAIN
SELECT id, display_name
FROM contacts
WHERE display_name = 'lan'
ORDER BY display_name, id;

EXPLAIN
SELECT id, display_name
FROM contacts
WHERE display_name COLLATE utf8mb4_0900_as_cs = 'lan'
ORDER BY display_name COLLATE utf8mb4_0900_as_cs, id;
```

Trong bảng ví dụ chỉ có sáu hàng, optimizer có thể chọn quét bảng cho cả hai câu truy vấn; điều đó **không đủ** để kết luận chỉ mục không có tác dụng. Với dữ liệu đại diện cho môi trường thật, hãy đối chiếu `type`, `key`, số hàng ước lượng và thông tin sắp xếp trong `EXPLAIN`; khi cần, đo thời gian thực thi, lượng dữ liệu đọc và chi phí sắp xếp.

Những câu hỏi cần đặt ra khi đánh giá:

1. Collation của cột và của biểu thức truy vấn có trùng nhau không?
2. Điều kiện có dùng được chỉ mục trên cột trực tiếp, hay đã bọc cột trong hàm/ép kiểu/chuyển collation làm thay đổi khả năng tối ưu?
3. Truy vấn có `ORDER BY` và phân trang hay không? Có cần khóa phụ duy nhất để giữ thứ tự ổn định không?
4. So khớp không phân biệt dấu/hoa thường có khiến nhiều hàng cùng khớp hơn, làm tăng số hàng phải xử lý không?
5. Các phép so sánh lặp lại trong `JOIN`, `GROUP BY`, `DISTINCT` và kiểm tra `UNIQUE` chịu tác động gì?

Nếu ứng dụng thường xuyên cần hai kiểu tra cứu có ngữ nghĩa khác nhau, có thể cân nhắc khóa tìm kiếm được chuẩn hóa, cột phát sinh, chỉ mục riêng hoặc chức năng index phù hợp của DBMS. Không tự động dùng `LOWER(column) = LOWER(?)` hay ép `COLLATE` cho mọi truy vấn: những thay đổi đó có thể làm lệch ngữ nghĩa dấu tiếng Việt và khả năng dùng index. Cần kiểm thử bằng `EXPLAIN` và dữ liệu thực tế trước khi quyết định.

## 7. Quy trình đánh giá trước khi chọn hoặc đổi collation

Một quyết định collation nên đi từ yêu cầu người dùng đến bằng chứng trên dữ liệu, rồi mới đến thay đổi schema.

| Bước | Thao tác | Kết quả cần xác nhận |
|---|---|---|
| 1. Định nghĩa ngữ nghĩa | Hỏi rõ tên người, từ khóa, mã định danh, khóa duy nhất có cần phân biệt dấu/hoa thường không | Bộ quy tắc nghiệp vụ, không chỉ tên collation |
| 2. Kiểm tra môi trường | Xác định DBMS, phiên bản, collation cột/kết nối và khả năng hỗ trợ locale | SQL thử nghiệm phản ánh đúng môi trường chạy |
| 3. Tạo bộ dữ liệu biên | Dùng biến thể hoa/thường, dấu tiếng Việt, `Đ`/`D`, Unicode NFC/NFD, khoảng trắng | Danh sách các cặp phải bằng/khác theo yêu cầu |
| 4. So sánh kết quả | Chạy `=`, `LIKE`, `ORDER BY`, `DISTINCT`, `GROUP BY`, kiểm tra `UNIQUE` | Không có kết quả ghép hoặc phân tách sai về nghiệp vụ |
| 5. Kiểm tra JDBC | Dùng tham số `?`, đọc lại nguyên văn qua `ResultSet`, thử phân trang | Hành vi dữ liệu ổn định từ SQL đến Java |
| 6. Đo hiệu năng | So sánh kế hoạch `EXPLAIN` và thời gian trên dữ liệu đại diện | Khả năng dùng chỉ mục, chi phí sắp xếp, số hàng đọc phù hợp |
| 7. Lập kế hoạch thay đổi | Rà xung đột unique, truy vấn phụ thuộc thứ tự, chỉ mục và quy trình triển khai | Có phương án kiểm tra dữ liệu, sao lưu và khôi phục phù hợp DBMS |

**Thận trọng với thay đổi schema:** thay collation của cột có thể thay kết quả truy vấn, làm trùng khóa unique, buộc xây dựng lại chỉ mục hoặc khóa bảng trong quá trình migration. Khả năng rollback của DDL không giống nhau giữa các DBMS; ví dụ không nên giả định một thao tác `ALTER TABLE` của MySQL có thể được đảo ngược bằng `Connection.rollback()`. Hãy kiểm tra trên môi trường thử nghiệm và thiết kế migration theo DBMS cụ thể trước khi tác động tới dữ liệu sản xuất.

### Bài thực hành

Trên bảng `contacts` ở mục 2, hãy thực hiện và ghi nhận:

1. Chạy `WHERE display_name = 'lan'`, sau đó thêm `COLLATE utf8mb4_0900_as_cs`. So sánh tập `id` trả về và giải thích vì sao `PreparedStatement` vẫn có thể trả về các kết quả khác nhau khi chỉ đổi SQL.
2. Chạy `ORDER BY display_name` rồi `ORDER BY display_name, id`. Xác định những hàng có cùng khóa sắp xếp theo collation và giải thích tác động khi phân trang.
3. Thử chèn `'Lan'` và `'lan'` vào cột `UNIQUE` của `contact_aliases`. Giải thích xung đột dựa trên collation thay vì dựa trên Java `String.equals()`.
4. Chạy hai lệnh `EXPLAIN` ở mục 6 với dữ liệu mẫu; giải thích vì sao một bảng quá nhỏ chưa phù hợp để khẳng định truy vấn nào nhanh hơn.
5. Bổ sung các giá trị `Da`, `Đa`, `Dà` và hai dạng Unicode của cùng ký tự vào bảng thử nghiệm. Ghi lại kết quả thực trên collation đang dùng trước khi quyết định ứng dụng cần chế độ tìm kiếm nào.

**Tiêu chí hoàn thành:** người học giải thích được vì sao cùng một tham số JDBC có thể khớp nhiều hàng khác nhau dưới các collation khác nhau; biết kiểm tra collation thực tế; viết truy vấn tham số hóa có sắp xếp ổn định; nhận diện rủi ro unique, Unicode và chỉ mục; đồng thời đánh giá thay đổi bằng dữ liệu và kế hoạch truy vấn thay vì dựa vào tên collation.
