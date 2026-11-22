# Phân biệt giá trị SQL NULL và giá trị mặc định của kiểu nguyên thủy khi đọc ResultSet

Trong chương **Đọc ResultSet**, một lỗi rất phổ biến là đọc cột số có giá trị SQL `NULL` bằng `ResultSet.getInt(...)` rồi tưởng dữ liệu thực sự bằng `0`. Tương tự, `getBoolean(...)` trả về `false` khi cột `NULL`, khiến chương trình nhầm “chưa xác định” với “sai”. Nếu sử dụng những giá trị này để tính tiền, đánh giá điều kiện hoặc cập nhật bản ghi, ứng dụng có thể đưa ra kết luận sai mà không có ngoại lệ nào được ném ra.

**JDBC (Java Database Connectivity)** là API Java cho truy cập cơ sở dữ liệu quan hệ. JDBC cung cấp hai cơ chế quan trọng để bảo toàn ý nghĩa của `NULL` khi đọc `ResultSet`: gọi **`wasNull()` ngay sau một getter kiểu nguyên thủy**, hoặc sử dụng **getter trả về kiểu đối tượng** phù hợp. Bài viết giải thích quy tắc, ví dụ Java, cách ánh xạ dữ liệu và các tình huống dễ nhầm lẫn.

## 1. SQL NULL là gì?

Trong SQL, `NULL` biểu thị một giá trị **chưa có, không biết hoặc không áp dụng** theo mô hình dữ liệu. Nó không đồng nghĩa với:

- Số `0`.
- Giá trị boolean `FALSE`.
- Chuỗi rỗng `''`.
- Ngày giờ mặc định.
- Dòng dữ liệu không tồn tại.

Xét bảng minh họa:

```sql
CREATE TABLE customer_profiles (
    profile_id   BIGINT PRIMARY KEY,
    login_count  INTEGER NULL,
    subscribed   BOOLEAN NULL,
    display_name VARCHAR(100) NULL
);

INSERT INTO customer_profiles
    (profile_id, login_count, subscribed, display_name)
VALUES
    (1, NULL, NULL, NULL),
    (2, 0, FALSE, ''),
    (3, 8, TRUE, 'Lan');
```

Đây là cú pháp minh họa cho DBMS hỗ trợ kiểu `BOOLEAN` và `INSERT` nhiều hàng. Một số DBMS dùng kiểu biểu diễn boolean hoặc cú pháp chèn khác; cần chỉnh cho hệ quản trị đang sử dụng.

Ba dòng có ý nghĩa khác nhau:

| `profile_id` | `login_count` | `subscribed` | `display_name` | Ý nghĩa |
|---|---:|---|---|---|
| `1` | `NULL` | `NULL` | `NULL` | Chưa có dữ liệu đếm lượt đăng nhập/trạng thái đăng ký/tên hiển thị |
| `2` | `0` | `FALSE` | `''` | Biết chắc lượt đăng nhập bằng 0, không đăng ký, tên đang rỗng |
| `3` | `8` | `TRUE` | `'Lan'` | Có thông tin cụ thể |

Tính năng của DBMS có thể làm chuỗi rỗng và `NULL` tương đương nhau trong một số kiểu hoặc ngữ cảnh, chẳng hạn chuỗi ký tự rỗng trong Oracle Database. Vì vậy, ví dụ phân biệt `''` với `NULL` ở cột chuỗi cần được xác minh trên hệ quản trị mục tiêu.

Trong SQL, để kiểm tra `NULL`, dùng `IS NULL` hoặc `IS NOT NULL`:

```sql
SELECT profile_id
FROM customer_profiles
WHERE login_count IS NULL;

SELECT profile_id
FROM customer_profiles
WHERE login_count = 0;
```

Hai truy vấn trên chọn những nhóm dữ liệu khác nhau. Biểu thức `login_count = NULL` không hoạt động như so sánh bằng thông thường, vì SQL có logic ba giá trị `TRUE`, `FALSE` và `UNKNOWN`.

## 2. Tại sao getter kiểu nguyên thủy gây nhầm lẫn?

Trong Java, các kiểu nguyên thủy như `int`, `long`, `double` và `boolean` **không thể giữ giá trị `null`**. Vì thế, JDBC quy định các getter tương ứng trên `ResultSet` trả về một giá trị đại diện khi cột SQL là `NULL`:

| Getter `ResultSet` | Kiểu Java trả về | Khi giá trị SQL là `NULL` | Giá trị hợp lệ dễ bị nhầm |
|---|---|---|---|
| `getByte(...)` | `byte` | `0` | Byte bằng 0 |
| `getShort(...)` | `short` | `0` | Số nguyên ngắn bằng 0 |
| `getInt(...)` | `int` | `0` | Số nguyên bằng 0 |
| `getLong(...)` | `long` | `0L` | Số nguyên dài bằng 0 |
| `getFloat(...)` | `float` | `0.0f` | Số thực bằng 0 |
| `getDouble(...)` | `double` | `0.0d` | Số thực bằng 0 |
| `getBoolean(...)` | `boolean` | `false` | Boolean thực sự là FALSE |

Đây là **giá trị trả về của getter JDBC** khi đọc `NULL`, không phải lời khẳng định dữ liệu trong database đã được thay bằng `0` hay `false`.

Ví dụ:

```java
int count = resultSet.getInt("login_count");
boolean subscribed = resultSet.getBoolean("subscribed");
```

Nếu cả hai cột là `NULL`, hai biến ở trên lần lượt nhận `0` và `false`. Nhưng nếu dữ liệu thật là `0` và `FALSE`, chương trình cũng nhận hai giá trị hệt như vậy. **Chỉ nhìn vào kết quả kiểu nguyên thủy là không thể phân biệt hai trường hợp.**

### 2.1. `wasNull()` cung cấp thông tin còn thiếu

`ResultSet.wasNull()` trả về `true` nếu **giá trị cột vừa được đọc gần nhất** là SQL `NULL`, và trả về `false` nếu không.

```java
int rawCount = resultSet.getInt("login_count");
boolean countWasNull = resultSet.wasNull();

if (countWasNull) {
    System.out.println("Số lượt đăng nhập chưa xác định (SQL NULL)");
} else {
    System.out.println("Số lượt đăng nhập: " + rawCount);
}
```

Với cột `NULL`, `rawCount` bằng `0` nhưng `countWasNull` là `true`. Với cột có giá trị `0` thật, `rawCount` vẫn bằng `0` nhưng `countWasNull` là `false`.

**Thứ tự gọi rất quan trọng:** `wasNull()` mô tả *getter vừa thực hiện*, không nhận tên cột và không kiểm tra tùy ý một cột trước đó.

## 3. Gọi wasNull() ngay sau đúng getter

### 3.1. Cách dùng đúng

```java
int loginCount = resultSet.getInt("login_count");
boolean loginCountIsNull = resultSet.wasNull();

boolean subscribed = resultSet.getBoolean("subscribed");
boolean subscribedIsNull = resultSet.wasNull();
```

Khi đọc xong `login_count`, ứng dụng lưu ngay kết quả `wasNull()` trước khi đọc `subscribed`. Tương tự, kiểm tra boolean ngay sau `getBoolean(...)`.

Một cách ngắn hơn là chuyển giá trị nguyên thủy sang kiểu wrapper Java:

```java
int countValue = resultSet.getInt("login_count");
Integer loginCount = resultSet.wasNull() ? null : countValue;

boolean subscribedValue = resultSet.getBoolean("subscribed");
Boolean subscribed = resultSet.wasNull() ? null : subscribedValue;
```

Kết quả bảo toàn được cả ba trường hợp:

| Cột SQL | Giá trị Java |
|---|---|
| `login_count IS NULL` | `Integer loginCount = null` |
| `login_count = 0` | `Integer loginCount = 0` |
| `login_count = 8` | `Integer loginCount = 8` |
| `subscribed IS NULL` | `Boolean subscribed = null` |
| `subscribed = FALSE` | `Boolean subscribed = false` |
| `subscribed = TRUE` | `Boolean subscribed = true` |

### 3.2. Cách dùng sai: gọi getter khác trước wasNull()

```java
// SAI: wasNull() lúc này nói về subscribed, không nói về login_count.
int loginCount = resultSet.getInt("login_count");
boolean subscribed = resultSet.getBoolean("subscribed");

if (resultSet.wasNull()) {
    // Không đủ cơ sở kết luận login_count là NULL.
}
```

Ví dụ bản ghi có `login_count = NULL` và `subscribed = FALSE`: `getInt(...)` trả `0`, `getBoolean(...)` trả `false`, nhưng `wasNull()` sau cùng sẽ phản ánh **cột `subscribed`** nên trả `false`. Chương trình sẽ bỏ sót SQL `NULL` ở `login_count`.

### 3.3. Một số quy tắc thực hành

- Gọi `wasNull()` sau getter cần kiểm tra, trước bất kỳ getter cột nào khác.
- Không gọi `wasNull()` trước khi đọc một cột rồi suy diễn kết quả.
- Dùng `getInt(1)`, `getInt("login_count")` đều được; vị trí cột của `ResultSet` bắt đầu từ **1** và tên truyền vào là *column label*, thường trùng tên cột hoặc alias `AS`.
- Mỗi lần `ResultSet.next()` di chuyển đến một dòng mới, phải đọc lại cột và tính lại trạng thái `NULL` cho dòng đó; không tái dùng cờ của dòng trước.
- Không dùng chung `ResultSet` cho nhiều luồng rồi mong `wasNull()` vẫn phản ánh riêng getter của từng luồng; `ResultSet` và cursor cần được sở hữu, sử dụng trong phạm vi rõ ràng.

## 4. Getter trả về đối tượng có thể biểu diễn null

Không phải getter JDBC nào cũng trả về kiểu nguyên thủy. Các getter trả về **kiểu tham chiếu** có thể trực tiếp trả về Java `null` khi cột SQL là `NULL`.

| Getter | Kiểu trả về thông thường | Khi SQL là `NULL` |
|---|---|---|
| `getString(...)` | `String` | `null` |
| `getBigDecimal(...)` | `BigDecimal` | `null` |
| `getDate(...)` | `java.sql.Date` | `null` |
| `getTime(...)` | `java.sql.Time` | `null` |
| `getTimestamp(...)` | `java.sql.Timestamp` | `null` |
| `getBytes(...)` | `byte[]` | `null` |
| `getObject(...)` | `Object` | `null` |

Ví dụ:

```java
String name = resultSet.getString("display_name");

if (name == null) {
    System.out.println("SQL NULL");
} else if (name.isEmpty()) {
    System.out.println("Chuỗi rỗng");
} else {
    System.out.println("Tên hiển thị: " + name);
}
```

Vì `String` có thể chứa `null`, không cần `wasNull()` trong ví dụ này để phân biệt `NULL` với `""`. Tương tự, `BigDecimal` giúp giữ đồng thời trạng thái chưa có giá trị và độ chính xác thập phân cho số tiền.

### 4.1. Dùng getObject(...) cho giá trị nullable

Getter `getObject(int)` hoặc `getObject(String)` trả về `null` nếu cột SQL là `NULL`:

```java
Object rawCount = resultSet.getObject("login_count");

if (rawCount == null) {
    System.out.println("Cột login_count là SQL NULL");
} else {
    System.out.println("Cột có giá trị: " + rawCount);
}
```

**Lưu ý về kiểu Java:** `getObject(...)` không bảo đảm kiểu đối tượng cụ thể giống nhau giữa mọi driver và mọi DBMS. Một cột số có thể được ánh xạ thành các kiểu Java khác nhau tùy SQL type và driver. Vì vậy, không nên ép kiểu mù quáng:

```java
// Có thể lỗi ClassCastException nếu driver trả về kiểu Number khác.
Integer count = (Integer) resultSet.getObject("login_count");
```

Nếu cần một kiểu Java cụ thể, JDBC cung cấp biến thể:

```java
Integer loginCount = resultSet.getObject("login_count", Integer.class);
Boolean subscribed = resultSet.getObject("subscribed", Boolean.class);
```

Với driver hỗ trợ chuyển đổi tương ứng, cột SQL `NULL` sẽ cho kết quả Java `null`. Tuy nhiên, **khả năng hỗ trợ `getObject(column, Class<T>)` và các chuyển đổi sang `Integer`/`Boolean` phụ thuộc vào driver, DBMS và kiểu cột**. Phương thức có thể ném `SQLException`, bao gồm `SQLFeatureNotSupportedException`, khi chuyển đổi không được hỗ trợ.

Để viết mã tương thích rộng, cách **`getInt(...)` rồi `wasNull()`** vẫn là lựa chọn đáng tin cậy khi cần diễn giải cột số nguyên có thể `NULL`.

### 4.2. Không dùng kiểu nguyên thủy cho thuộc tính thực sự nullable

Một DTO chỉ có `int` không phân biệt được `NULL` và `0`:

```java
// Thiết kế làm mất ý nghĩa "chưa xác định".
record IncompleteProfile(long id, int loginCount, boolean subscribed) {}

// Thiết kế giữ lại được SQL NULL.
record Profile(long id, Integer loginCount,
               Boolean subscribed, String displayName) {}
```

Ví dụ `record` cần Java 16+; trong phiên bản Java cũ hơn có thể dùng class với các trường wrapper tương ứng. Một trường không cho phép `NULL` trong schema và được ràng buộc `NOT NULL` có thể dùng primitive; chỉ nên dùng wrapper khi trạng thái thiếu giá trị có ý nghĩa trong nghiệp vụ.

## 5. Ví dụ đầy đủ: đọc từng dòng và ánh xạ sang DTO

Giả sử bảng `customer_profiles` đã được tạo theo ví dụ ở mục 1 và ứng dụng có một `DataSource` cấu hình JDBC. Đoạn mã dưới đây đọc toàn bộ ba cột nullable và bảo toàn các trạng thái dữ liệu.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class ProfileReader {

    // Java 16+; thay bằng class nếu dự án chạy Java cũ hơn.
    public record Profile(
            long id,
            Integer loginCount,
            Boolean subscribed,
            String displayName) {}

    public static List<Profile> loadProfiles(DataSource dataSource)
            throws SQLException {
        String sql = """
                SELECT profile_id, login_count, subscribed, display_name
                FROM customer_profiles
                ORDER BY profile_id
                """;

        List<Profile> profiles = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql);
             ResultSet result = statement.executeQuery()) {

            while (result.next()) {
                // profile_id là PRIMARY KEY NOT NULL.
                long id = result.getLong("profile_id");

                // Getter primitive: lưu ngay wasNull() sau mỗi lần đọc.
                int rawCount = result.getInt("login_count");
                Integer loginCount = result.wasNull() ? null : rawCount;

                boolean rawSubscribed = result.getBoolean("subscribed");
                Boolean subscribed =
                        result.wasNull() ? null : rawSubscribed;

                // Getter object: null biểu thị SQL NULL.
                String displayName = result.getString("display_name");

                profiles.add(new Profile(
                        id, loginCount, subscribed, displayName));
            }
        }

        return profiles;
    }
}
```

Đoạn mã dùng Java 16+ cho `record` và Java 15+ cho text block. Nếu dùng Java thấp hơn, viết DTO dưới dạng class và truyền câu SQL dưới dạng chuỗi thông thường. Trong ứng dụng thực tế, `DataSource` phải trỏ đến cơ sở dữ liệu có bảng và dữ liệu minh họa.

Với ba dòng mẫu, kết quả ánh xạ mong đợi:

| `id` | `loginCount` (Java) | `subscribed` (Java) | `displayName` (Java) |
|---|---|---|---|
| `1` | `null` | `null` | `null` |
| `2` | `0` | `false` | `""` (nếu DBMS phân biệt chuỗi rỗng với `NULL`) |
| `3` | `8` | `true` | `"Lan"` |

Khi dùng DTO này ở tầng dịch vụ, có thể xử lý rõ ràng:

```java
ProfileReader.Profile profile = profiles.get(0);

if (profile.loginCount() == null) {
    // Chưa có dữ liệu thống kê: không khẳng định khách hàng đăng nhập 0 lần.
}

if (profile.subscribed() == null) {
    // Chưa xác định trạng thái đăng ký.
} else if (profile.subscribed()) {
    // Đăng ký TRUE.
} else {
    // Đã biết là FALSE.
}
```

**Không dùng `profile.subscribed() == false`** nếu trường là `Boolean` có thể `null`: phép so sánh với literal `false` có thể tự động unbox và gây `NullPointerException`. Dùng `Boolean.TRUE.equals(profile.subscribed())` khi chỉ cần kiểm tra trạng thái `TRUE`, hoặc phân nhánh tường minh như trên khi cần phân biệt cả ba trường hợp.

## 6. SQL NULL khác với DEFAULT trong schema

Có hai tầng “giá trị mặc định” cần phân biệt:

1. **SQL DEFAULT**: quy tắc của cột khi câu `INSERT` không cung cấp giá trị cho cột, hoặc dùng từ khóa `DEFAULT` theo cú pháp DBMS.
2. **Giá trị getter JDBC trả về khi gặp SQL NULL**: `0` / `false` cho getter nguyên thủy. Giá trị này **không làm thay đổi dữ liệu đang lưu**.

Ví dụ:

```sql
CREATE TABLE counters (
    counter_id BIGINT PRIMARY KEY,
    total_count INTEGER DEFAULT 5
);

-- Không truyền total_count: mặc định của schema thường được áp dụng.
INSERT INTO counters (counter_id) VALUES (1);

-- Truyền NULL tường minh: cột nullable nên dữ liệu được lưu là NULL.
INSERT INTO counters (counter_id, total_count) VALUES (2, NULL);

-- Truyền số 0 thật.
INSERT INTO counters (counter_id, total_count) VALUES (3, 0);
```

Kết quả khái niệm của `SELECT counter_id, total_count FROM counters`:

| ID | `total_count` trên DB | `getInt(...)` | `wasNull()` |
|---|---|---:|---|
| `1` | `5` | `5` | `false` |
| `2` | `NULL` | `0` | `true` |
| `3` | `0` | `0` | `false` |

Nếu khai báo thêm `NOT NULL`, việc chèn `NULL` thường bị từ chối theo quy tắc DBMS và cấu hình SQL mode. Không nên giả định DBMS tự động thay `NULL` bằng default.

Trong Java, một biến `int` nếu chưa được gán trực tiếp có những quy tắc khởi tạo khác nhau tùy nó là **trường** hay **biến cục bộ**: trường nguyên thủy nhận giá trị mặc định của Java (chẳng hạn `0`), còn biến cục bộ phải được gán trước khi dùng. Những quy tắc này không phải là quy tắc `DEFAULT` của SQL và không quyết định giá trị của cột `ResultSet`.

## 7. COALESCE và việc cố ý thay SQL NULL bằng giá trị khác

Đôi khi nghiệp vụ thực sự muốn xem `NULL` như `0`. Có thể thực hiện lựa chọn đó ở SQL bằng `COALESCE`:

```sql
SELECT
    profile_id,
    COALESCE(login_count, 0) AS login_count_for_display
FROM customer_profiles;
```

Khi đó, ngay từ **kết quả truy vấn**, cột `login_count_for_display` không còn phân biệt `NULL` và `0` trong dữ liệu nguồn. `ResultSet.getInt("login_count_for_display")` sẽ đọc giá trị `0` do SQL tạo ra và `wasNull()` sẽ là `false` cho cột này.

Đây là lựa chọn hợp lệ khi chỉ cần hiển thị một tổng số có mặc định rõ ràng, nhưng không phù hợp nếu ứng dụng cần phân biệt “chưa thống kê” với “đã thống kê và bằng 0”.

Cũng có thể lựa chọn mặc định ở tầng Java:

```java
int raw = resultSet.getInt("login_count");
Integer nullableCount = resultSet.wasNull() ? null : raw;

// Chỉ ở điểm nghiệp vụ đã quyết định coi NULL như 0:
int countForDisplay = nullableCount == null ? 0 : nullableCount;
```

Giữ giá trị nullable cho tới khi quyết định nghiệp vụ cần thay thế giúp tránh đánh mất thông tin quá sớm.

## 8. Những tình huống nâng cao dễ mất ý nghĩa của NULL

### 8.1. LEFT JOIN: dòng không khớp và cột NULL

Với `LEFT JOIN`, các cột từ phía bảng phải sẽ là `NULL` khi không có dòng khớp. Ví dụ:

```sql
SELECT c.customer_id,
       p.profile_id AS joined_profile_id,
       p.login_count
FROM customers AS c
LEFT JOIN customer_profiles AS p
    ON p.profile_id = c.customer_id;
```

Kết quả `getInt("login_count") == 0` **không cho biết** khách hàng không có profile, có profile với `login_count = NULL` hay có profile với `login_count = 0`.

Muốn phân biệt:

```java
long joinedProfileId = resultSet.getLong("joined_profile_id");
boolean profileMissing = resultSet.wasNull();

int countValue = resultSet.getInt("login_count");
Integer loginCount = resultSet.wasNull() ? null : countValue;

if (profileMissing) {
    // Không có bản ghi profile khớp ở phía phải JOIN.
} else if (loginCount == null) {
    // Có bản ghi profile nhưng cột login_count là NULL.
} else {
    // Có profile và số lượt đăng nhập đã xác định, có thể bằng 0.
}
```

Ví dụ giả định `customer_profiles.profile_id` là khóa chính không `NULL`. Chỉ đọc cột nullable sau `LEFT JOIN` sẽ không đủ để quyết định có dòng bên phải hay không.

### 8.2. Hàm tổng hợp có thể trả SQL NULL

Trong SQL, `COUNT(*)` trả về số dòng, kể cả `0` với nhóm toàn kết quả rỗng theo cách truy vấn phù hợp. Ngược lại, `SUM` và `AVG` có thể trả về `NULL` nếu không có giá trị số hợp lệ để tổng hợp:

```sql
SELECT SUM(login_count) AS total_logins
FROM customer_profiles
WHERE profile_id > 100000;
```

Khi không có dòng thỏa điều kiện, `SUM(login_count)` thường trả về một dòng với giá trị `NULL`. Đọc `getLong("total_logins")` mà không kiểm tra `wasNull()` sẽ biến “không có dữ liệu để tính tổng” thành số `0`.

```java
long total = resultSet.getLong("total_logins");
Long nullableTotal = resultSet.wasNull() ? null : total;
```

Với tổng của các số thập phân hoặc số có thể vượt `long`, nên đọc thành `BigDecimal` hoặc kiểu phù hợp thay vì ép kiểu mặc định.

### 8.3. Chọn getter tương thích SQL type

`getInt(...)` không phải luôn phù hợp cho cột số, vì SQL `BIGINT` có thể vượt phạm vi `int`, `DECIMAL` có thể có phần lẻ và các driver có quy tắc chuyển đổi khác nhau. Chọn getter khớp dữ liệu:

- `INTEGER` → `getInt(...)` + `wasNull()` hoặc `getObject(..., Integer.class)` nếu driver hỗ trợ.
- `BIGINT` → `getLong(...)` + `wasNull()` hoặc kiểu wrapper tương ứng.
- `DECIMAL` cho tiền → `getBigDecimal(...)`, nhận `null` trực tiếp khi SQL `NULL`.
- `BOOLEAN` → `getBoolean(...)` + `wasNull()`, với điều kiện DBMS/driver ánh xạ boolean như mong đợi.
- Chuỗi → `getString(...)`; ngày giờ → getter đối tượng phù hợp với kiểu thời gian.

Nếu SQL type hoặc phép chuyển đổi không phù hợp, driver có thể ném `SQLException`. `wasNull()` xử lý việc phân biệt `NULL`; nó **không sửa lỗi mất độ chính xác hoặc lỗi chuyển đổi kiểu**.

## 9. Kiểm thử ba trạng thái thay vì hai

Nếu một thuộc tính có thể `NULL`, bộ kiểm thử cần bao gồm ít nhất:

1. **SQL NULL** — kiểm tra getter nguyên thủy trả mặc định, `wasNull() == true` và DTO wrapper là `null`.
2. **Giá trị mặc định thật** (`0` hoặc `FALSE`) — kiểm tra getter trả giá trị giống trường hợp đầu nhưng `wasNull() == false` và DTO giữ giá trị.
3. **Giá trị khác mặc định** (ví dụ `8` hoặc `TRUE`) — kiểm tra ánh xạ trả giá trị chính xác.

Ngoài ra, cần kiểm tra trình tự hai getter nullable trong một dòng:

| `login_count` | `subscribed` | Kỳ vọng sau `getInt` | Kỳ vọng sau `getBoolean` |
|---|---|---|---|
| `NULL` | `FALSE` | `0`, `wasNull = true` | `false`, `wasNull = false` |
| `0` | `NULL` | `0`, `wasNull = false` | `false`, `wasNull = true` |
| `8` | `TRUE` | `8`, `wasNull = false` | `true`, `wasNull = false` |

Đây là bộ trường hợp đặc biệt hữu ích để phát hiện lỗi gọi `wasNull()` **sau getter của cột khác**. Kiểm thử tích hợp nên chạy trên driver và DBMS mục tiêu, đặc biệt với cột boolean được DBMS mô phỏng bằng số hoặc chuỗi.

## 10. Những lỗi thường gặp và cách sửa

| Cách viết hoặc nhận định sai | Vấn đề | Cách sửa |
|---|---|---|
| `getInt("score") == 0` nghĩa là score bằng 0 | Có thể SQL `NULL` | Gọi `wasNull()` ngay sau `getInt(...)` |
| `!getBoolean("active")` nghĩa là giá trị `FALSE` | Có thể SQL `NULL` | Dùng `wasNull()` và kiểu `Boolean` nếu cần ba trạng thái |
| Gọi `wasNull()` sau khi đã đọc cột khác | Kiểm tra sai cột | Lưu cờ `wasNull()` ngay sau getter cần kiểm tra |
| Ép trực tiếp `(Integer) getObject(...)` | Driver có thể trả kiểu `Number` khác | Dùng getter phù hợp hoặc chuyển đổi đã được driver hỗ trợ |
| DTO có `int` cho cột nullable | Đánh mất thông tin thiếu giá trị | Dùng `Integer` hoặc mô hình miền dữ liệu rõ ràng |
| Dùng `COALESCE(nullable_col, 0)` mọi nơi | Làm mất phân biệt `NULL` và `0` | Chỉ dùng khi nghiệp vụ chủ động chọn mặc định |
| Cho rằng `DEFAULT 5` nghĩa là mọi `NULL` đều thành 5 | `DEFAULT` và `NULL` có ngữ nghĩa khác nhau | Xem lại `INSERT`, constraint và quy tắc DBMS |
| Gọi `rs.next()` thấy `false` rồi hiểu một cột là `NULL` | Không có dòng để đọc | Phân biệt “không tìm thấy bản ghi” với “cột của dòng là NULL” |
| Đọc `BIGINT` bằng `getInt(...)` | Nguy cơ vượt phạm vi kiểu | Chọn `getLong(...)` hoặc kiểu dữ liệu tương ứng |
| Dùng wrapper `Boolean` trực tiếp trong `if (value)` | Unboxing `null` có thể gây NPE | Kiểm tra `null` hoặc `Boolean.TRUE.equals(value)` trước |

## 11. Bài tập tự kiểm tra

**Câu 1.** Cột `login_count` có SQL `NULL`. `rs.getInt("login_count")` trả về gì, và gọi gì để biết đó thực sự là `NULL`?

**Đáp án:** `getInt(...)` trả `0`. Gọi `rs.wasNull()` **ngay sau** `getInt(...)`; kết quả `true` cho biết cột là SQL `NULL`.

**Câu 2.** Cột `subscribed` là `FALSE` thật. Kết quả `getBoolean(...)` và `wasNull()` là gì?

**Đáp án:** Lần lượt là `false` và `false`; nếu cột SQL `NULL` thì `getBoolean(...)` cũng là `false` nhưng `wasNull()` là `true`.

**Câu 3.** Sau `getInt("login_count")`, chương trình gọi `getString("display_name")` rồi `wasNull()`. Cờ này đang kiểm tra cột nào?

**Đáp án:** `display_name`, vì đây là giá trị được đọc gần nhất.

**Câu 4.** Có thể dùng `Integer count = rs.getObject("login_count", Integer.class)` để nhận Java `null` không?

**Đáp án:** Có khi driver hỗ trợ kiểu chuyển đổi đó; cần kiểm chứng trên driver/DBMS thực tế. Cách thay thế phổ biến là `getInt(...)` rồi `wasNull()`.

**Câu 5.** `DEFAULT 5` của cột số có phải là giá trị `getInt(...)` dùng khi cột SQL `NULL` không?

**Đáp án:** Không. `DEFAULT` ảnh hưởng cách gán giá trị khi ghi dữ liệu theo cú pháp SQL, còn `getInt(...)` trả `0` khi đọc SQL `NULL`.

**Câu 6.** Vì sao `LEFT JOIN` có thể cần kiểm tra thêm khóa chính của bảng bên phải?

**Đáp án:** Vì một cột dữ liệu bên phải là `NULL` có thể do **không có dòng khớp** hoặc do **có dòng nhưng chính cột đó bằng `NULL`**. Khóa chính không nullable giúp phân biệt hai tình huống.

**Câu 7.** `COUNT(*)` và `SUM(amount)` đều có nên đọc như thể chắc chắn không `NULL` không?

**Đáp án:** Không. `COUNT(*)` trả số đếm không `NULL` theo ngữ nghĩa SQL thông thường; `SUM(amount)` có thể trả SQL `NULL` khi không có dữ liệu số để tổng hợp.

## 12. Ghi nhớ

Trong JDBC, **`0` và `false` có thể là giá trị thật hoặc chỉ là kết quả mà getter nguyên thủy trả về khi SQL bằng `NULL`**. Muốn phân biệt, hãy gọi **`ResultSet.wasNull()` ngay sau getter nguyên thủy**, hoặc dùng getter trả về đối tượng và mô hình Java nullable thích hợp. Chỉ thay `NULL` bằng một mặc định khi nghiệp vụ thực sự yêu cầu; việc giữ đúng ý nghĩa dữ liệu giúp truy vấn, thống kê và xử lý nghiệp vụ đáng tin cậy hơn.
