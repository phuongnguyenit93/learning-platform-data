# Phân biệt NULL, chuỗi rỗng, giá trị 0 và giá trị mặc định trong JDBC

Khi ứng dụng Java làm việc với cơ sở dữ liệu quan hệ qua **JDBC (Java Database Connectivity)**, cùng một trường dữ liệu có thể ở những trạng thái rất khác nhau: chưa có giá trị (`NULL`), có giá trị văn bản nhưng không chứa ký tự nào (`''`), có giá trị số bằng không (`0`), hoặc được cơ sở dữ liệu tự điền theo một quy tắc `DEFAULT`. Nếu gộp các trạng thái này thành một khái niệm “trống”, ứng dụng có thể tính sai, mất thông tin hoặc cập nhật ngoài ý muốn.

Bài thuộc chương **Kiểu dữ liệu và NULL** này giải thích ngữ nghĩa SQL và cách biểu diễn chúng bằng `PreparedStatement`, `ResultSet` trong JDBC. Mục tiêu là xác định rõ **giá trị nào đang được lưu**, **điều kiện nào thực sự khớp** và **khi nào DBMS áp dụng mặc định**.

## 1. Bốn khái niệm cần phân biệt

| Trường hợp | Ý nghĩa trong nhiều hệ CSDL quan hệ | Giá trị Java thường gặp |
| --- | --- | --- |
| **SQL `NULL`** | Không có giá trị SQL tại vị trí cột; chưa biết/không áp dụng tùy nghiệp vụ | `null` với kiểu tham chiếu |
| **Chuỗi rỗng `''`** | Một giá trị chuỗi có độ dài 0; khác `NULL` trên các hệ như PostgreSQL và MySQL | `""` (đối tượng `String` không phải `null`) |
| **Số `0`** | Một số thực sự bằng không, dùng trong phép so sánh/số học | `0` (`int`), `0L` (`long`), v.v. |
| **Giá trị `DEFAULT`** | Quy tắc ở schema hoặc biểu thức được DBMS sử dụng trong tình huống phù hợp | Không phải một giá trị Java cố định; phụ thuộc định nghĩa cột |

**`DEFAULT` không phải kiểu dữ liệu hay trạng thái thứ tư của một ô sau khi lưu.** Nó là *quy tắc lựa chọn giá trị*. Sau khi thực thi một `INSERT`, giá trị thực tế có thể là chuỗi, số, ngày giờ hoặc `NULL`, tùy định nghĩa `DEFAULT` và khả năng của DBMS.

Ví dụ:

- Tên hiển thị `NULL`: chưa được cung cấp hoặc không xác định.
- Tên hiển thị `''`: người dùng chủ động để chuỗi rỗng, nếu nghiệp vụ cho phép.
- Điểm thưởng `0`: người dùng có **0 điểm**, một dữ kiện có ý nghĩa để cộng/trừ.
- Điểm thưởng `DEFAULT 0`: DBMS tự gán **0** khi thao tác chèn kích hoạt mặc định. Sau khi lưu, không thể chỉ nhìn số 0 mà biết nó do người dùng truyền hay do default.

Không có quy tắc nghiệp vụ phổ quát rằng `NULL` luôn có nghĩa “chưa nhập” còn `''` luôn có nghĩa “đã xóa”. Ý nghĩa thực tế phải do mô hình dữ liệu và hợp đồng API xác định.

## 2. Ví dụ bảng dữ liệu có NULL, chuỗi rỗng, 0 và DEFAULT

Để minh họa chính xác, phần này sử dụng **PostgreSQL**. Các câu `CREATE TABLE` và `INSERT` bên dưới có thể chạy trên một database PostgreSQL mà tài khoản có quyền tạo/ghi bảng:

```sql
CREATE TABLE customer_profile (
    id            BIGINT PRIMARY KEY,
    display_name  VARCHAR(100) DEFAULT 'Anonymous',
    reward_points INTEGER NOT NULL DEFAULT 0,
    contact_note  VARCHAR(255)
);
```

Ở đây:

- `display_name` **cho phép `NULL`**, có `DEFAULT 'Anonymous'`.
- `reward_points` **không cho phép `NULL`**, có `DEFAULT 0`.
- `contact_note` cho phép `NULL` và không khai báo `DEFAULT` riêng.
- `id` là khóa chính, được ứng dụng cung cấp trong ví dụ.

Thử chèn ba bản ghi khác nhau:

```sql
-- A: Bo qua ca ba cot tuy chon.
INSERT INTO customer_profile (id) VALUES (1);

-- B: Truyen ro chuoi rong va so 0.
INSERT INTO customer_profile
    (id, display_name, reward_points, contact_note)
VALUES (2, '', 0, '');

-- C: Truyen NULL tuong minh cho hai cot cho phep NULL.
INSERT INTO customer_profile
    (id, display_name, reward_points, contact_note)
VALUES (3, NULL, 0, NULL);
```

Khi chạy truy vấn:

```sql
SELECT id, display_name, reward_points, contact_note
FROM customer_profile
ORDER BY id;
```

Kết quả về mặt ý nghĩa:

| `id` | `display_name` | `reward_points` | `contact_note` | Giải thích |
| --- | --- | ---: | --- | --- |
| 1 | `'Anonymous'` | 0 | `NULL` | Hai cột có default nhận giá trị mặc định; `contact_note` nhận `NULL` |
| 2 | `''` | 0 | `''` | Chuỗi rỗng và số 0 được truyền trực tiếp |
| 3 | `NULL` | 0 | `NULL` | `NULL` tường minh được giữ ở cột cho phép; không đổi thành `'Anonymous'` |

**Điểm mấu chốt:** ở bản ghi 3, `DEFAULT 'Anonymous'` *không* thay thế `NULL` được truyền tường minh. Trong bản ghi 1, `DEFAULT` được dùng vì cột đó không xuất hiện trong danh sách cột chèn.

## 3. Khi nào giá trị DEFAULT được áp dụng?

Trong SQL và JDBC, việc **không truyền cột**, **truyền SQL `NULL`** và **yêu cầu `DEFAULT`** là ba hành động khác nhau.

| Hành động khi `INSERT` | Ví dụ PostgreSQL | Với `display_name DEFAULT 'Anonymous'` |
| --- | --- | --- |
| Bỏ cột ra khỏi lệnh chèn | `INSERT INTO customer_profile(id) VALUES (4)` | DBMS điền `'Anonymous'` |
| Ghi rõ `DEFAULT` | `INSERT ... (id, display_name) VALUES (5, DEFAULT)` | DBMS điền `'Anonymous'` |
| Ghi rõ `NULL` | `INSERT ... (id, display_name) VALUES (6, NULL)` | Cột lưu `NULL` |
| Ghi chuỗi rỗng | `INSERT ... (id, display_name) VALUES (7, '')` | Cột lưu `''` |
| Ghi một chuỗi | `INSERT ... (id, display_name) VALUES (8, 'Linh')` | Cột lưu `'Linh'` |

Những dòng ví dụ có dấu `...` trong bảng là **ký hiệu rút gọn để so sánh**, không phải câu SQL đầy đủ có thể sao chép chạy trực tiếp. SQL `DEFAULT` có thể được dùng theo những cú pháp khác nhau giữa các hệ quản trị; các ví dụ ở phần này mô tả hành vi PostgreSQL.

Với cột `reward_points INTEGER NOT NULL DEFAULT 0`:

```sql
-- Thanh cong: bo qua cot reward_points -> dung DEFAULT 0.
INSERT INTO customer_profile (id) VALUES (10);

-- Thanh cong: truyen gia tri so 0 tuong minh.
INSERT INTO customer_profile (id, reward_points) VALUES (11, 0);

-- Loi rang buoc NOT NULL: NULL khong duoc thay bang DEFAULT 0.
INSERT INTO customer_profile (id, reward_points) VALUES (12, NULL);
```

Trong nhiều DBMS, cột không có `DEFAULT` riêng sẽ nhận `NULL` khi bị bỏ qua, **nếu cột cho phép `NULL`**. Nếu cột bắt buộc và không có giá trị mặc định, lệnh chèn thường bị từ chối. Các trường hợp generated/identity columns, trigger và chế độ SQL đặc thù có thể thay đổi hành vi; hãy dựa vào schema và tài liệu DBMS cụ thể.

### DEFAULT khi UPDATE

Ở PostgreSQL, có thể đặt lại giá trị bằng mặc định của cột:

```sql
UPDATE customer_profile
SET display_name = DEFAULT
WHERE id = 2;
```

Lệnh này gán `'Anonymous'` cho hàng số 2. Ngược lại:

```sql
UPDATE customer_profile
SET display_name = NULL
WHERE id = 2;
```

Lệnh thứ hai lưu `NULL`, không áp dụng `DEFAULT`. Việc cập nhật một cột không có mặt trong mệnh đề `SET` thông thường **giữ nguyên giá trị cũ của cột**; default không tự kích hoạt lại.

## 4. SQL NULL và logic ba giá trị

Trong SQL, `NULL` **không được so sánh như một giá trị thông thường**. Biểu thức so sánh với `NULL` thường cho kết quả logic **UNKNOWN**, ngoài `TRUE` và `FALSE`. Điều kiện `WHERE` thông thường chỉ giữ những hàng có điều kiện bằng `TRUE`.

| Biểu thức SQL | Kết quả theo logic ba giá trị |
| --- | --- |
| `NULL = NULL` | UNKNOWN |
| `NULL <> NULL` | UNKNOWN |
| `0 = 0` | TRUE |
| `'' = ''` | TRUE trên PostgreSQL (và các DBMS phân biệt chuỗi rỗng) |
| `NULL = 0` | UNKNOWN |
| `NULL = ''` | UNKNOWN |
| `NULL IS NULL` | TRUE |
| `NULL IS NOT NULL` | FALSE |

Vì vậy, hai câu sau **không tương đương**:

```sql
-- Sai muc tieu tim NULL: phep = NULL cho UNKNOWN.
SELECT id FROM customer_profile WHERE display_name = NULL;

-- Dung: dung toan tu IS NULL.
SELECT id FROM customer_profile WHERE display_name IS NULL;
```

Muốn tìm chuỗi rỗng thực sự trên PostgreSQL:

```sql
SELECT id
FROM customer_profile
WHERE display_name = '';
```

Muốn tìm số điểm bằng 0:

```sql
SELECT id
FROM customer_profile
WHERE reward_points = 0;
```

Ba truy vấn kiểm tra **ba điều kiện khác nhau**. Tránh viết một câu `WHERE column = ?` với tham số `NULL` rồi hy vọng nó tương đương `IS NULL`: khi bind SQL `NULL`, phép so sánh `= ?` vẫn thường cho UNKNOWN.

### Phân biệt kết quả qua hàm SQL

`COALESCE(expression, fallback)` trả về đối số đầu tiên khác `NULL`; còn `NULLIF(a, b)` trả `NULL` nếu hai biểu thức bằng nhau (theo quy tắc so sánh của DBMS).

```sql
-- display_name NULL -> 'Anonymous'
-- display_name ''   -> '' (van la chuoi rong)
SELECT id, COALESCE(display_name, 'Anonymous') AS shown_name
FROM customer_profile;

-- Neu nghiep vu xem ca NULL va '' la "khong co ten":
SELECT id,
       COALESCE(NULLIF(display_name, ''), 'Anonymous') AS shown_name
FROM customer_profile;
```

Các hàm trên thay đổi **giá trị của biểu thức kết quả**, không tự cập nhật dữ liệu đã lưu. Cũng cần cân nhắc ảnh hưởng đến việc sử dụng chỉ mục nếu đặt hàm trên cột trong điều kiện lọc của truy vấn lớn.

## 5. Chuỗi rỗng không phải lúc nào cũng giống nhau giữa các DBMS

Ví dụ PostgreSQL phân biệt `NULL` và `''`. MySQL cũng phân biệt chúng trong các kiểu chuỗi phổ biến. Tuy nhiên, **Oracle Database hiện coi chuỗi ký tự có độ dài bằng 0 là `NULL` trong nhiều ngữ cảnh kiểu ký tự như `VARCHAR2`**. Do đó, một lệnh chèn `''` có thể được xử lý như `NULL` trên Oracle.

Không viết quy tắc đa DBMS dựa trên giả định rằng **mọi** hệ quản trị đều lưu được `NULL` và chuỗi rỗng như hai trạng thái riêng biệt.

| DBMS | Cách hiểu thông dụng đối với chuỗi độ dài 0 |
| --- | --- |
| PostgreSQL | `''` khác `NULL` |
| MySQL | `''` khác `NULL` |
| SQL Server | `''` khác `NULL` (các quy tắc kiểu và so sánh có thể cần kiểm tra thêm) |
| Oracle Database | Chuỗi ký tự độ dài 0 thường được xử lý như `NULL` |

Ngoài ra, **chuỗi chỉ chứa dấu cách** (`" "`) cũng không phải `""` trong Java. Cơ sở dữ liệu có thể áp dụng quy tắc so sánh, khoảng trắng cuối hoặc collation đặc thù. Nếu nghiệp vụ không chấp nhận tên chỉ chứa khoảng trắng, phải đưa ra quy tắc chuẩn hóa rõ ràng; không suy ra chỉ từ trạng thái SQL `NULL`.

## 6. Java null, String rỗng và giá trị nguyên thủy

Trong Java, `null` là trạng thái của **kiểu tham chiếu** (ví dụ `String`, `Integer`), còn `int` là kiểu nguyên thủy **không có giá trị `null`**:

```java
String missingName = null; // Khong co doi tuong String.
String emptyName = "";     // Chuoi co 0 ky tu, khac null.

Integer unknownPoints = null; // Co the bieu dien trang thai khong co gia tri.
int zeroPoints = 0;           // Gia tri so 0, khong phai null.
```

Với bộ nhớ của một đối tượng Java mới được tạo, `int` field có giá trị mặc định Java bằng 0 và `String` field mặc định Java bằng `null`. **Đó là mặc định của Java**, hoàn toàn độc lập với `DEFAULT` của bảng SQL. DBMS chỉ dùng quy tắc `DEFAULT` khi nhận một câu SQL phù hợp; một biến Java bằng 0 không tự biến thành chỉ thị `DEFAULT`.

Hãy phân biệt:

| Giá trị phía Java | Điều muốn diễn đạt trong SQL | Phương thức JDBC |
| --- | --- | --- |
| `String name = null` | Ghi SQL `NULL` vào cột chuỗi | `setNull(index, Types.VARCHAR)` |
| `String name = ""` | Ghi chuỗi rỗng | `setString(index, "")` |
| `int count = 0` | Ghi số 0 | `setInt(index, 0)` |
| “Sử dụng mặc định của cột” | Để DBMS áp dụng `DEFAULT` | Bỏ cột trong SQL `INSERT`, hoặc dùng cú pháp `DEFAULT` của DBMS |

`PreparedStatement` **không có một lệnh bind chung kiểu “`setDefault(index)`” trong JDBC tiêu chuẩn**. Nếu muốn áp dụng default, ứng dụng phải xây dựng cấu trúc SQL tương ứng. Không thay thế default bằng `setNull()` hoặc bằng một chuỗi ký tự `"DEFAULT"`.

## 7. Ghi dữ liệu đúng ý nghĩa bằng PreparedStatement

Ví dụ Java sau làm việc với bảng `customer_profile` đã tạo ở phần 2. Cùng một `Connection` có thể dùng cho nhiều thao tác, nhưng cần kiểm soát giao dịch và vòng đời connection ở bên gọi.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;

public final class CustomerProfileRepository {
    private CustomerProfileRepository() {}

    // Su dung DEFAULT cho display_name va reward_points.
    public static void insertUsingDefaults(
            Connection connection, long id) throws SQLException {

        String sql = "INSERT INTO customer_profile (id) VALUES (?)";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.executeUpdate();
        }
    }

    // Luu chinh xac NULL, chuoi rong hoac mot chuoi co noi dung.
    public static void insertExplicitValues(
            Connection connection, long id, String displayName,
            int rewardPoints, String contactNote) throws SQLException {

        String sql = "INSERT INTO customer_profile " +
                "(id, display_name, reward_points, contact_note) " +
                "VALUES (?, ?, ?, ?)";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            if (displayName == null) {
                statement.setNull(2, Types.VARCHAR);
            } else {
                statement.setString(2, displayName);
            }

            statement.setInt(3, rewardPoints);

            if (contactNote == null) {
                statement.setNull(4, Types.VARCHAR);
            } else {
                statement.setString(4, contactNote);
            }

            statement.executeUpdate();
        }
    }

    public static void printById(
            Connection connection, long id) throws SQLException {

        String sql = "SELECT display_name, reward_points, contact_note " +
                "FROM customer_profile WHERE id = ?";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    System.out.println("Khong tim thay profile");
                    return;
                }

                String name = result.getString("display_name");
                int points = result.getInt("reward_points");
                boolean pointsIsNull = result.wasNull();
                String note = result.getString("contact_note");

                System.out.println("name=" + name
                        + ", points=" + points
                        + ", pointsIsNull=" + pointsIsNull
                        + ", note=" + note);
            }
        }
    }
}
```

Sử dụng ví dụ với ID **chưa tồn tại** trong bảng:

```java
CustomerProfileRepository.insertUsingDefaults(connection, 100L);
CustomerProfileRepository.insertExplicitValues(
        connection, 101L, "", 0, "");
CustomerProfileRepository.insertExplicitValues(
        connection, 102L, null, 0, null);
```

Kết quả lưu trữ dự kiến:

- ID 100: `display_name = 'Anonymous'`, `reward_points = 0`, `contact_note = NULL`.
- ID 101: `display_name = ''`, `reward_points = 0`, `contact_note = ''`.
- ID 102: `display_name = NULL`, `reward_points = 0`, `contact_note = NULL`.

**Không thể dùng `PreparedStatement` để phân biệt “chỉ định 0” với “default tự tạo ra 0” sau khi DBMS đã lưu cùng số 0.** Nếu nguồn gốc giá trị quan trọng, mô hình dữ liệu cần lưu thêm thông tin (ví dụ cờ trạng thái hoặc lịch sử thay đổi), chứ không suy luận từ giá trị cuối cùng.

### Gửi chuỗi "NULL" không phải SQL NULL

```java
statement.setString(1, "NULL");             // Chuoi co 4 ky tu.
statement.setString(1, "");                 // Chuoi rong.
statement.setNull(1, Types.VARCHAR);       // SQL NULL.
```

Đây là ba thao tác **minh họa độc lập** trên một placeholder phù hợp; gọi liên tiếp lên cùng vị trí trước khi thực thi thì lệnh gọi cuối ghi đè giá trị đã bind trước đó. Với `setNull`, chọn hằng `Types` theo kiểu cột hoặc tham số mà DBMS mong đợi. Hỗ trợ và quy tắc chuyển đổi một số kiểu đặc biệt có thể khác theo driver.

## 8. Đọc NULL từ ResultSet: đặc biệt lưu ý getter kiểu nguyên thủy

Các getter trả về kiểu tham chiếu có thể trả về Java `null` nếu cột SQL là `NULL`:

```java
String name = result.getString("display_name");
if (name == null) {
    System.out.println("SQL NULL");
} else if (name.isEmpty()) {
    System.out.println("Chuoi rong");
} else {
    System.out.println("Ten: " + name);
}
```

Với `getInt()`, `getLong()`, `getBoolean()`, không có giá trị nguyên thủy `null` để trả về. JDBC quy định các getter này trả về giá trị mặc định nguyên thủy khi đọc SQL `NULL`, ví dụ **0** cho `getInt`, `false` cho `getBoolean`. Cần gọi **`ResultSet.wasNull()` ngay sau getter** nếu cột có thể `NULL`.

```java
int score = result.getInt("optional_score");
boolean scoreWasNull = result.wasNull();

Integer scoreValue = scoreWasNull ? null : score;
```

Đoạn mã giả định query đang đọc có cột `optional_score` có thể `NULL`. Nếu gọi một getter khác trước `wasNull()`, bạn có thể nhận trạng thái SQL `NULL` của **cột vừa đọc sau cùng**, không còn của `optional_score`.

Trong ví dụ `customer_profile`, `reward_points` là `NOT NULL`, nên `pointsIsNull` theo schema phải là `false`. Với cột thực sự nullable, `wasNull()` là cách quan trọng để không nhầm SQL `NULL` với số 0.

Một số driver hỗ trợ đọc thẳng kiểu wrapper:

```java
Integer nullableScore = result.getObject("optional_score", Integer.class);
```

Khi driver hỗ trợ phép chuyển đổi JDBC `getObject(column, Class<T>)`, SQL `NULL` được biểu diễn thành Java `null` cho kiểu tham chiếu này. Hãy kiểm tra hỗ trợ của driver/kiểu cột trên môi trường triển khai.

## 9. Khi nào SQL NULL, chuỗi rỗng hoặc 0 ảnh hưởng kết quả tổng hợp?

Các hàm SQL thường xử lý `NULL` khác với số 0:

```sql
-- Dem so hang bat ke cac cot co NULL hay khong.
SELECT COUNT(*) AS all_profiles FROM customer_profile;

-- Dem so hang co display_name KHAC NULL.
-- Chuoi rong van duoc tinh neu DBMS phan biet '' va NULL.
SELECT COUNT(display_name) AS named_values FROM customer_profile;
```

Trong PostgreSQL, `COUNT(display_name)` đếm cả `''` vì nó là giá trị khác `NULL`. Nếu muốn đếm **tên không rỗng**, cần viết điều kiện nghiệp vụ riêng:

```sql
SELECT COUNT(*) AS nonempty_names
FROM customer_profile
WHERE display_name IS NOT NULL
  AND display_name <> '';
```

Với số liệu có thể `NULL`:

- `SUM(column)` và `AVG(column)` thường **bỏ qua** các giá trị `NULL`.
- Số `0` là một giá trị thực: `SUM` cộng 0, còn `AVG` tính 0 vào số phần tử khác NULL, nên có thể thay đổi trung bình.
- Khi không có giá trị khác `NULL` để cộng, `SUM` có thể trả `NULL`; `COUNT(column)` trả 0.
- `COALESCE(SUM(column), 0)` có thể được dùng khi màn hình yêu cầu hiển thị 0, nhưng cần hiểu đây là **chuyển đổi kết quả**, không thay đổi dữ liệu nguồn.

Ví dụ giá trị điểm là `{NULL, 0, 10}`: `COUNT(*) = 3`, `COUNT(points) = 2`, `SUM(points) = 10`, `AVG(points) = 5`. Nếu tùy tiện đổi `NULL` thành `0` trước khi tính trung bình, kết quả sẽ khác, vì số phần tử được tính tăng lên.

## 10. Bài toán PATCH: phân biệt “không gửi trường” và “gửi NULL”

Trong API cập nhật từng phần, còn một khác biệt quan trọng **ngoài bốn giá trị ở cột**: người dùng có thể **không gửi trường** trong request.

Giả sử hệ thống có thao tác cập nhật `display_name`:

| Dữ liệu request | Ý nghĩa nghiệp vụ có thể chọn | SQL nên thực hiện |
| --- | --- | --- |
| Không có thuộc tính `displayName` | Giữ nguyên tên đang lưu | Không đưa `display_name` vào `SET` |
| `"displayName": null` | Xóa giá trị, lưu SQL `NULL` | `SET display_name = NULL` hoặc bind `setNull()` |
| `"displayName": ""` | Đặt chuỗi rỗng (nếu cho phép) | `SET display_name = ?` và `setString(..., "")` |
| `"displayName": "Linh"` | Đặt tên có nội dung | `SET display_name = ?` và `setString(..., "Linh")` |
| Request có cờ “khôi phục tên mặc định” | Dùng default do DBMS quy định | `SET display_name = DEFAULT` nếu DBMS hỗ trợ |

Nếu giải mã request vào một `String displayName` đơn lẻ, cả trường **vắng mặt** và trường **được gửi `null`** có thể cùng cho giá trị Java `null`, khiến mất ý định của người dùng. Để phân biệt, lớp tiếp nhận request cần theo dõi **sự hiện diện của trường** bằng cấu trúc phù hợp, ví dụ cờ `present` đi cùng giá trị, một kiểu tổng (*sealed type*) hoặc cơ chế của thư viện JSON.

**`Optional<String>` đơn lẻ không tự biểu diễn đủ ba trạng thái** “vắng mặt”, “có mặt và `null`”, “có mặt và chuỗi” nếu các trạng thái đó đã bị gộp trong quá trình giải mã. Cần thiết kế hợp đồng API rõ ràng trước khi viết SQL.

## 11. Những ràng buộc và trường hợp đặc thù nên kiểm tra

| Chủ đề | Nguy cơ khi nhầm lẫn | Cách xử lý |
| --- | --- | --- |
| `NOT NULL` | Truyền `NULL` rồi mong `DEFAULT` tự điền | Bỏ cột hoặc dùng cú pháp `DEFAULT` phù hợp; tuân thủ constraint |
| `UNIQUE` | Giả định nhiều `NULL` luôn có cùng quy tắc như giá trị bình thường | Kiểm tra DBMS, định nghĩa constraint/index và cách xử lý `NULL` |
| Cột `CHAR` và `VARCHAR` | Cách xử lý dấu cách cuối, chuỗi rỗng có thể khác | Xác nhận kiểu cột, collation và quy tắc so sánh |
| Oracle chuỗi rỗng | `''` có thể được coi là `NULL` | Không phụ thuộc khả năng phân biệt nếu DBMS không hỗ trợ |
| `DEFAULT CURRENT_TIMESTAMP` | Nghĩ giá trị được Java tự tính khi biến bằng `null` | Để DBMS áp dụng default trong lệnh SQL thích hợp |
| `ResultSet.getInt()` | Cột nullable đọc ra 0 và bị xem là dữ liệu thật | Gọi `wasNull()` ngay sau getter |
| `COUNT(column)` | Xem kết quả bằng tổng số hàng | Dùng `COUNT(*)` nếu cần đếm mọi hàng |
| `COALESCE()` | Xem giá trị thay thế ở truy vấn là đã được lưu | Phân biệt hiển thị với giá trị trong bảng |
| API cập nhật từng phần | Gộp không gửi trường với gửi `null` | Theo dõi sự hiện diện của trường, xác định chính sách PATCH |

Một lưu ý về **quy tắc mặc định trong DBMS**: mặc định có thể là biểu thức động (`CURRENT_TIMESTAMP`), một số tạo từ sequence, hoặc một giá trị tĩnh. Chỉ đọc schema mới biết chính xác điều gì được gán. Một trigger có thể thay đổi giá trị sau khi chèn, nên kết quả đọc lại cần được hiểu theo toàn bộ quy tắc của database.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Bảng có cột `display_name VARCHAR(100) DEFAULT 'Anonymous'` cho phép NULL. Nếu `INSERT` truyền `display_name = NULL`, cột nhận giá trị gì?

*Gợi ý:* Trên PostgreSQL, cột lưu `NULL`. `DEFAULT` không tự thay thế SQL `NULL` được truyền tường minh.

**Câu 2.** Nếu `ResultSet.getInt("score")` trả về 0, có chắc dữ liệu trong DB là số 0 không?

*Gợi ý:* Không. Với cột nullable, SQL `NULL` cũng cho kết quả `getInt` bằng 0; phải gọi `wasNull()` ngay sau getter.

**Câu 3.** Hai câu `WHERE name = ''` và `WHERE name IS NULL` có cho cùng kết quả trên PostgreSQL không?

*Gợi ý:* Không. Truy vấn thứ nhất kiểm tra chuỗi rỗng, truy vấn thứ hai kiểm tra SQL `NULL`.

**Câu 4.** Nếu bảng có `reward_points INTEGER NOT NULL DEFAULT 0`, nên gọi `setNull(index, Types.INTEGER)` để yêu cầu số 0 mặc định không?

*Gợi ý:* Không. SQL `NULL` vi phạm `NOT NULL`; bỏ cột trong `INSERT` hoặc yêu cầu `DEFAULT` theo cú pháp DBMS.

**Câu 5.** `COUNT(display_name)` có tính bản ghi mà `display_name = ''` không?

*Gợi ý:* Có trên các hệ như PostgreSQL vì chuỗi rỗng không phải `NULL`.

**Câu 6.** Với API PATCH, request không có `displayName` và request có `"displayName": null` có nên mặc định mang cùng ý nghĩa?

*Gợi ý:* Không. Một quy ước phổ biến là trường vắng mặt nghĩa là “không thay đổi”, còn `null` tường minh nghĩa là “xóa giá trị”; cần định nghĩa hợp đồng API.

**Câu 7.** Trên Oracle, có thể mặc định lưu và phân biệt `''` với `NULL` trong cột ký tự như trên PostgreSQL không?

*Gợi ý:* Không nên giả định. Oracle thường xử lý chuỗi ký tự độ dài 0 như `NULL`; phải kiểm tra dữ liệu và kiểu cột cụ thể.

## Ghi nhớ

Trong JDBC, **SQL `NULL` là sự vắng mặt của giá trị**, **`''` là chuỗi có độ dài 0** trên những DBMS phân biệt được, còn **`0` là một giá trị số thật**. **`DEFAULT` là quy tắc ở schema**, thường được kích hoạt khi bỏ cột trong `INSERT` hoặc dùng cú pháp `DEFAULT` phù hợp; nó không tự thay thế giá trị SQL `NULL` truyền tường minh. Khi ghi, dùng `PreparedStatement.setNull()`, `setString()`, `setInt()` theo đúng ý nghĩa. Khi đọc, đặc biệt với getter kiểu nguyên thủy, gọi `ResultSet.wasNull()` để phân biệt `NULL` với 0. Cuối cùng, luôn xác định hợp đồng nghiệp vụ cho trường vắng mặt, rỗng, bằng 0 và phép cập nhật từng phần, đồng thời kiểm tra các khác biệt của DBMS/driver trước khi triển khai.
