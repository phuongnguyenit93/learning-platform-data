# Phân biệt truyền NULL và bỏ qua cột để dùng mặc định của bảng trong JDBC

## 1. Ba ý nghĩa dễ bị nhầm: NULL, DEFAULT và không cung cấp cột

Trong chương **Kiểu dữ liệu và NULL**, một câu hỏi quan trọng khi ghi dữ liệu là: nếu ứng dụng Java không có giá trị cho một trường, cơ sở dữ liệu sẽ lưu `NULL` hay tự điền giá trị mặc định?

**JDBC (Java Database Connectivity)** là API giúp Java truy cập cơ sở dữ liệu quan hệ. Với JDBC, `PreparedStatement` cho phép gán các giá trị SQL, kể cả `NULL`, nhưng **giá trị `NULL` và yêu cầu cơ sở dữ liệu dùng `DEFAULT` là hai ý nghĩa khác nhau**.

Giả sử bảng `support_ticket` có cột `status VARCHAR(20) NOT NULL DEFAULT 'OPEN'`. Khi tạo ticket:

- Nếu **bỏ cột `status` khỏi danh sách cột của `INSERT`**, cơ sở dữ liệu dùng mặc định `'OPEN'`.
- Nếu **truyền SQL `NULL` cho `status`**, hệ quản trị thường báo lỗi ràng buộc `NOT NULL`; nó **không tự thay `NULL` bằng `'OPEN'`** theo ngữ nghĩa SQL thông thường.
- Nếu **truyền chuỗi `'CLOSED'`**, cơ sở dữ liệu lưu `'CLOSED'` nếu các ràng buộc khác cho phép.

| Ý định của ứng dụng | Câu SQL | Kết quả điển hình |
| --- | --- | --- |
| “Không chỉ định trạng thái, dùng giá trị mặc định” | `INSERT ... (id, title) VALUES (?, ?)` | `status = 'OPEN'` |
| “Trạng thái được khai báo rõ là không có giá trị” | `INSERT ... (id, title, status) VALUES (?, ?, ?)`, marker 3 là SQL `NULL` | **Lỗi `NOT NULL`** |
| “Đặt trạng thái cụ thể” | `INSERT ... (id, title, status) VALUES (?, ?, ?)` với `'CLOSED'` | `status = 'CLOSED'` |

Sự khác biệt này nằm ở **ngữ nghĩa câu SQL**, không phải một cờ tự động của JDBC driver. Bạn cần chọn **cột nào xuất hiện trong câu lệnh** trước khi gán tham số.

## 2. Bảng ví dụ: hai cột có DEFAULT với ràng buộc khác nhau

Xét bảng hỗ trợ yêu cầu khách hàng:

~~~sql
CREATE TABLE support_ticket (
    id         BIGINT PRIMARY KEY,
    title      VARCHAR(200) NOT NULL,
    status     VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    note       VARCHAR(500) DEFAULT 'Chưa có ghi chú',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Đây là cú pháp SQL thông dụng; ví dụ giả định DBMS hỗ trợ `DEFAULT` cho chuỗi và `CURRENT_TIMESTAMP`. Các quy tắc về kiểu dữ liệu, biểu thức mặc định và cột sinh tự động có thể khác giữa các hệ quản trị.

- `id`: khóa chính, ứng dụng cung cấp trong các ví dụ; không có mặc định.
- `title`: bắt buộc, không có mặc định; bỏ cột hoặc gán `NULL` đều không hợp lệ trong cách khai báo này.
- `status`: có mặc định `'OPEN'` nhưng **không cho phép `NULL`**.
- `note`: có mặc định `'Chưa có ghi chú'` và **cho phép `NULL`** vì không có ràng buộc `NOT NULL`.
- `created_at`: mặc định dùng thời gian do cơ sở dữ liệu xác định khi áp dụng biểu thức `CURRENT_TIMESTAMP`.

Với bảng này, hai câu SQL bên dưới **có kết quả khác nhau**, dù phía Java đều nói “không có nội dung ghi chú”:

~~~sql
-- Trường hợp A: bỏ hẳn cột note.
INSERT INTO support_ticket (id, title)
VALUES (101, 'Không đăng nhập được');

-- Trường hợp B: chỉ định tường minh SQL NULL.
INSERT INTO support_ticket (id, title, note)
VALUES (102, 'Không nhận được email', NULL);
~~~

Khi đọc lại:

~~~sql
SELECT id, status, note
FROM support_ticket
WHERE id IN (101, 102)
ORDER BY id;
~~~

| `id` | `status` | `note` |
| --- | --- | --- |
| 101 | `OPEN` | `Chưa có ghi chú` |
| 102 | `OPEN` | SQL `NULL` |

**Lý do:** ở hàng 101, cơ sở dữ liệu áp dụng mặc định cho cột `note` vì cột này không xuất hiện trong `INSERT`. Ở hàng 102, câu lệnh chỉ định rõ `note = NULL`, nên giá trị mặc định không được sử dụng theo ngữ nghĩa SQL thông thường.

## 3. Trong JDBC, `setNull()` nghĩa là truyền NULL thật

Phương thức `PreparedStatement.setNull(parameterIndex, sqlType)` gửi **giá trị SQL `NULL`** tới marker tham số được chỉ định. Ví dụ:

~~~java
String sql = """
        INSERT INTO support_ticket (id, title, note)
        VALUES (?, ?, ?)
        """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 102L);
    ps.setString(2, "Không nhận được email");
    ps.setNull(3, java.sql.Types.VARCHAR);
    ps.executeUpdate();
}
~~~

Vị trí tham số JDBC bắt đầu từ **1**. Ở đây, `setNull(3, Types.VARCHAR)` chỉ định marker thứ ba nhận SQL `NULL` với kiểu tương ứng `VARCHAR`. Nếu `note` cho phép `NULL`, bản ghi được lưu với `note = NULL`, dù cột có `DEFAULT`.

Phân biệt các trường hợp sau:

| Mã Java/JDBC | Ý nghĩa |
| --- | --- |
| `ps.setNull(3, Types.VARCHAR)` | Gán SQL `NULL` cho marker 3. |
| `ps.setString(3, null)` | Nhiều driver xử lý như SQL `NULL`, nhưng `setNull` hoặc `setObject` có kiểu rõ ràng là lựa chọn minh bạch hơn. |
| `ps.setObject(3, null, Types.VARCHAR)` | Yêu cầu gán `NULL` với kiểu SQL được chỉ định; mức hỗ trợ chuyển đổi phụ thuộc driver. |
| `ps.setString(3, "NULL")` | Gán **chuỗi ký tự** `NULL`; không phải SQL `NULL`. |
| Không gọi setter thứ 3 trong câu có ba marker | Tham số 3 chưa được gán; thường gây `SQLException` khi thực thi, **không phải** yêu cầu dùng `DEFAULT`. |

Với kiểu đặc biệt hoặc cột không suy ra được kiểu từ marker, một số driver yêu cầu `setNull(index, sqlType, typeName)` hay ép kiểu rõ ràng trong SQL. Cách chuyển giá trị Java `null` sang SQL `NULL` cần tuân theo hợp đồng JDBC và driver.

**Không gán `null` bằng cách bỏ qua setter.** Bỏ qua một **cột của câu `INSERT`** và bỏ qua lời gọi `setXxx` cho một **marker đã tồn tại** là hai thao tác hoàn toàn khác nhau.

## 4. Muốn dùng DEFAULT: loại cột khỏi INSERT hoặc dùng từ khóa SQL DEFAULT

### 4.1. Bỏ cột khỏi danh sách cột

Đây là cách trực quan nhất để yêu cầu giá trị mặc định:

~~~sql
INSERT INTO support_ticket (id, title)
VALUES (?, ?);
~~~

Vì `status`, `note` và `created_at` không được liệt kê, cơ sở dữ liệu sẽ áp dụng giá trị mặc định đã khai báo cho từng cột. Nếu một cột không có `DEFAULT`, kết quả tùy thuộc khả năng nhận `NULL`, tính chất cột sinh tự động và ràng buộc của DBMS.

JDBC tương ứng:

~~~java
String sql = "INSERT INTO support_ticket (id, title) VALUES (?, ?)";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 101L);
    ps.setString(2, "Không đăng nhập được");
    ps.executeUpdate();
}
~~~

**Ở đây chỉ có hai marker, nên chỉ cần gán tham số 1 và 2.** Ứng dụng không truyền tham số thứ ba “đại diện cho DEFAULT”.

### 4.2. Dùng từ khóa `DEFAULT` nếu DBMS hỗ trợ

Nhiều DBMS, trong đó có PostgreSQL, hỗ trợ chỉ định `DEFAULT` ngay trong biểu thức `VALUES`:

~~~sql
-- Minh họa cú pháp được PostgreSQL hỗ trợ.
INSERT INTO support_ticket (id, title, note)
VALUES (?, ?, DEFAULT);
~~~

Trong câu này, `DEFAULT` là **cú pháp SQL**, không phải giá trị được truyền qua `PreparedStatement`. Hai marker duy nhất thuộc `id` và `title`.

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO support_ticket (id, title, note) VALUES (?, ?, DEFAULT)")) {
    ps.setLong(1, 103L);
    ps.setString(2, "Yêu cầu hỗ trợ mới");
    ps.executeUpdate();
}
~~~

Không thể thay phần `DEFAULT` của câu SQL bằng một marker để rồi gán chuỗi `"DEFAULT"`:

~~~sql
-- Không mang ý nghĩa "dùng mặc định":
INSERT INTO support_ticket (id, title, note) VALUES (?, ?, ?)
~~~

~~~java
ps.setString(3, "DEFAULT"); // Lưu chuỗi "DEFAULT" vào note, nếu hợp lệ.
~~~

Một marker `?` biểu diễn **giá trị SQL**, không thể biến thành từ khóa `DEFAULT`, tên cột hay một đoạn cú pháp SQL tùy ý.

### 4.3. Bỏ mọi cột khi bảng cho phép

Một số DBMS cho phép `INSERT INTO support_ticket DEFAULT VALUES` để yêu cầu giá trị mặc định cho mọi cột. **Bảng ví dụ ở trên không phù hợp** vì `id` và `title` là bắt buộc mà không có mặc định. Cú pháp chèn hàng dùng toàn bộ mặc định còn khác giữa các DBMS, nên chỉ áp dụng khi schema và hệ quản trị thực sự hỗ trợ.

## 5. Ví dụ Java đầy đủ: ba ý định tạo ghi chú

Ba phương thức dưới đây cùng chèn vào bảng `support_ticket`, nhưng diễn đạt ba ý định dữ liệu:

1. **Bỏ qua ghi chú** để database tự dùng `DEFAULT`.
2. **Ghi chú là SQL `NULL` thật**.
3. **Ghi chú có một giá trị cụ thể**.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public final class TicketDao {
    private final DataSource dataSource;

    public TicketDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insertUsingDefaults(long id, String title)
            throws SQLException {
        String sql = """
                INSERT INTO support_ticket (id, title)
                VALUES (?, ?)
                """;

        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setString(2, title);
            ps.executeUpdate();
        }
    }

    public void insertWithExplicitNullNote(long id, String title)
            throws SQLException {
        String sql = """
                INSERT INTO support_ticket (id, title, note)
                VALUES (?, ?, ?)
                """;

        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setString(2, title);
            ps.setNull(3, Types.VARCHAR); // NULL, không phải DEFAULT.
            ps.executeUpdate();
        }
    }

    public void insertWithNote(long id, String title, String note)
            throws SQLException {
        if (note == null) {
            throw new IllegalArgumentException(
                    "Dùng insertWithExplicitNullNote khi muốn ghi NULL");
        }

        String sql = """
                INSERT INTO support_ticket (id, title, note)
                VALUES (?, ?, ?)
                """;

        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setString(2, title);
            ps.setString(3, note);
            ps.executeUpdate();
        }
    }
}
~~~

Ví dụ sử dụng Java 17 trở lên cho text block `"""` và giả định `DataSource` đã được cấu hình. Các ID dưới đây chưa được sử dụng trong bảng:

~~~java
TicketDao dao = new TicketDao(dataSource);
dao.insertUsingDefaults(101L, "Không đăng nhập được");
dao.insertWithExplicitNullNote(102L, "Không nhận được email");
dao.insertWithNote(103L, "Chưa đồng bộ dữ liệu", "Kiểm tra lúc 14 giờ");
~~~

Kết quả dự kiến ở cột `note` lần lượt là **`'Chưa có ghi chú'`**, **SQL `NULL`** và **`'Kiểm tra lúc 14 giờ'`**. Cả ba câu lệnh đều bỏ cột `status`, nên cột này lấy mặc định `'OPEN'`.

`try-with-resources` đảm bảo `PreparedStatement` và `Connection` được đóng khi phương thức kết thúc. Trong một nghiệp vụ gồm nhiều câu SQL cần cùng commit hoặc rollback, tầng service nên quản lý một `Connection` chung và truyền vào DAO, thay vì để từng phương thức DAO tự mở giao dịch riêng.

## 6. Khi nhận dữ liệu từ API: cần phân biệt ba trạng thái

Một trường tùy chọn trong yêu cầu tạo bản ghi có thể mang **ba ý nghĩa nghiệp vụ**:

| Trạng thái đầu vào | Ý nghĩa | SQL thích hợp |
| --- | --- | --- |
| Không gửi trường `note` | “Để DB dùng giá trị mặc định” | `INSERT` **bỏ cột `note`** |
| Gửi `note: null` | “Lưu SQL NULL” | `INSERT` có `note = ?`, `setNull` |
| Gửi `note: "Gọi lại"` | “Lưu đúng chuỗi được cung cấp” | `INSERT` có `note = ?`, `setString` |

Ví dụ về ba payload JSON, chỉ nhằm minh họa ý nghĩa:

~~~json
{"id":201,"title":"Không vào được ứng dụng"}
{"id":202,"title":"Không vào được ứng dụng","note":null}
{"id":203,"title":"Không vào được ứng dụng","note":"Gọi lại"}
~~~

Một kiểu Java chỉ chứa `String note` không phân biệt được “trường `note` bị thiếu” với “trường có mặt nhưng giá trị `null`” nếu tầng nhận request đã làm mất thông tin này. Tương tự, `Optional<String>` thông thường biểu diễn có/không có một giá trị khác `null`, không tự mang đủ ba trạng thái trên.

Khi hợp đồng API cần đủ ba trạng thái, hãy giữ thêm thông tin *trường có xuất hiện hay không* (ví dụ `boolean noteProvided` và `String note`) hoặc dùng một kiểu kết quả riêng:

~~~java
// Mô hình Java 17+ để giữ rõ ba ý định của request.
sealed interface NoteInput
        permits UseDefaultNote, ExplicitNullNote, NoteValue {}

record UseDefaultNote() implements NoteInput {}
record ExplicitNullNote() implements NoteInput {}
record NoteValue(String value) implements NoteInput {}
~~~

Tầng nhận JSON có trách nhiệm ánh xạ *thiếu trường → UseDefaultNote*, *có trường null → ExplicitNullNote*, *có chuỗi → NoteValue*. Sau đó service có thể chọn một trong ba phương thức DAO ở mục 5, hoặc một phương thức lưu dữ liệu được thiết kế để nhận kiểu ba trạng thái này.

Một cách triển khai thực dụng là chuẩn bị **những câu SQL cố định theo từng trường hợp**, ví dụ hai mẫu `INSERT` (có/không có `note`); khi có `note`, bind `NULL` hoặc chuỗi theo giá trị thực tế. Nếu có nhiều cột tùy chọn, có thể tạo câu SQL động từ **danh sách tên cột được lập trình viên cho phép**, tuyệt đối không chèn tên cột tùy ý do người dùng gửi.

## 7. Với UPDATE, bỏ cột không có nghĩa là áp dụng DEFAULT

**Ngữ nghĩa của `INSERT` và `UPDATE` khác nhau.** Trong `INSERT`, bỏ một cột thường khiến DBMS áp dụng giá trị mặc định cho cột đó. Trong `UPDATE`, **không đề cập đến cột** có nghĩa là **giữ nguyên giá trị cũ của cột**.

Giả sử ticket 101 đang có `note = 'Đã gọi khách hàng'`:

~~~sql
-- Chỉ thay đổi trạng thái. Note giữ nguyên giá trị cũ.
UPDATE support_ticket
SET status = 'CLOSED'
WHERE id = 101;
~~~

Nếu muốn xóa ghi chú thành SQL `NULL`:

~~~sql
UPDATE support_ticket
SET note = NULL
WHERE id = 101;
~~~

Nếu muốn đặt lại ghi chú theo mặc định khai báo của bảng, một số DBMS (như PostgreSQL) cho phép:

~~~sql
-- Cú pháp cần kiểm tra trên DBMS cụ thể.
UPDATE support_ticket
SET note = DEFAULT
WHERE id = 101;
~~~

`UPDATE ... SET note = DEFAULT` không tương đương với việc **không có** `note` trong danh sách cột cập nhật. Nó yêu cầu áp dụng biểu thức mặc định hiện tại của bảng, nếu DBMS hỗ trợ.

### PATCH khác PUT như thế nào trong API?

Không có quy tắc bắt buộc từ JDBC về hành vi của endpoint HTTP. Tuy nhiên, với một API cập nhật một phần, lựa chọn thường hợp lý là:

- **Trường vắng mặt:** giữ giá trị hiện tại; không đưa cột vào `SET`.
- **Trường hiện diện với `null`:** cập nhật thành SQL `NULL` nếu schema cho phép.
- **Yêu cầu đặt lại mặc định:** dùng một hành động rõ ràng trong API và SQL `DEFAULT` nếu DBMS hỗ trợ.

Đừng tự động dùng mặc định bảng chỉ vì một trường bị bỏ qua trong `UPDATE`. Điều đó sẽ làm mất dữ liệu trước đó.

## 8. DEFAULT tương tác thế nào với NOT NULL và kiểu dữ liệu?

### 8.1. Có DEFAULT vẫn có thể từ chối NULL

Với `status VARCHAR(20) NOT NULL DEFAULT 'OPEN'`:

~~~sql
-- Hợp lệ: bỏ status để nhận 'OPEN'.
INSERT INTO support_ticket (id, title)
VALUES (301, 'Yêu cầu mới');

-- Không hợp lệ theo ngữ nghĩa thông thường: NULL vi phạm NOT NULL.
INSERT INTO support_ticket (id, title, status)
VALUES (302, 'Yêu cầu khác', NULL);
~~~

**`DEFAULT` không tự động làm cột trở thành nullable.** `NOT NULL` kiểm soát giá trị được phép; `DEFAULT` chỉ nêu giá trị được dùng khi SQL yêu cầu mặc định.

### 8.2. Bỏ một cột không có DEFAULT sẽ ra sao?

Các trường hợp điển hình:

| Khai báo cột | `INSERT` bỏ cột | `INSERT` gán SQL NULL |
| --- | --- | --- |
| `note VARCHAR(500) DEFAULT 'Chưa có ghi chú'` | Dùng chuỗi mặc định | Lưu `NULL` |
| `note VARCHAR(500)` | Thường dùng `NULL` khi không có default và cột nullable | Lưu `NULL` |
| `status VARCHAR(20) NOT NULL DEFAULT 'OPEN'` | Dùng `'OPEN'` | Lỗi `NOT NULL` |
| `title VARCHAR(200) NOT NULL` | Lỗi thiếu giá trị hợp lệ | Lỗi `NOT NULL` |
| Cột identity/generated | DBMS có thể tự sinh theo quy tắc riêng | Tùy loại cột và DBMS |

Một số hệ quản trị có chế độ SQL, trigger, cột tự sinh hoặc cơ chế **DEFAULT ON NULL** riêng. Các phần mở rộng này có thể làm khác hành vi thông thường; cần xem đúng hợp đồng DBMS khi sử dụng. Trong SQL chuẩn và thiết kế JDBC portable, hãy xem **`NULL` được truyền tường minh** và **mặc định do bỏ cột** là hai thao tác khác nhau.

### 8.3. Thay đổi DEFAULT tác động đến hàng nào?

Giả sử sau này quản trị viên đổi mặc định của `note` từ `'Chưa có ghi chú'` sang `'Chưa cập nhật'`. Những lần `INSERT` **tiếp theo** bỏ cột sẽ dùng mặc định mới. Việc thay đổi mặc định thường **không tự cập nhật những bản ghi đã có**; các bản ghi cũ giữ giá trị từng được lưu. Hãy xem xét migration dữ liệu riêng nếu nghiệp vụ yêu cầu cập nhật bản ghi cũ.

## 9. Cẩn trọng khi đọc kết quả và kiểm thử

Khi đọc `support_ticket.note` bằng JDBC:

~~~java
String sql = "SELECT status, note, created_at "
           + "FROM support_ticket WHERE id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 102L);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String status = rs.getString("status");
            String note = rs.getString("note"); // SQL NULL -> Java null.
            java.sql.Timestamp created =
                    rs.getTimestamp("created_at");

            System.out.println("status=" + status);
            System.out.println("note=" + note);
            System.out.println("created=" + created);
        }
    }
}
~~~

Hãy kiểm tra giá trị thực sau khi DB thực thi `INSERT`. `PreparedStatement` **không tự trả về giá trị mặc định** cho những cột không xuất hiện trong câu lệnh. Muốn nhận giá trị do DB sinh, có thể `SELECT` lại, hoặc dùng `RETURNING`/cơ chế generated keys phù hợp với driver và DBMS.

Đặc biệt, **đừng giả định** Java `null` và SQL `NULL` trong một câu truy vấn so sánh bằng nhau theo toán tử `=`:

~~~sql
-- Không tìm đúng các hàng có note NULL:
SELECT id FROM support_ticket WHERE note = NULL;

-- Đúng:
SELECT id FROM support_ticket WHERE note IS NULL;
~~~

Nếu dùng `WHERE note = ?` và gán tham số SQL `NULL`, biểu thức so sánh bằng cũng không tương đương `IS NULL` theo logic ba giá trị của SQL. Với nhu cầu lọc `NULL`, hãy chọn câu SQL có `IS NULL` rõ ràng.

## 10. Những lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Cột có DEFAULT nhưng vẫn nhận NULL | `INSERT` đã liệt kê cột và bind `NULL` | Bỏ cột khỏi `INSERT` hoặc dùng `DEFAULT` theo cú pháp DBMS. |
| Cột `NOT NULL DEFAULT ...` bị lỗi khi ghi | Gửi SQL `NULL` tường minh | Dùng giá trị cụ thể hoặc yêu cầu dùng mặc định bằng SQL. |
| Lỗi thiếu tham số lúc `executeUpdate()` | Có marker `?` nhưng không gọi setter vì Java `null` | Dùng `setNull` hoặc xây câu SQL thực sự không chứa cột. |
| Chuỗi `"DEFAULT"` xuất hiện trong dữ liệu | Bind chữ `"DEFAULT"` vào `?` | Dùng từ khóa SQL `DEFAULT` khi DB hỗ trợ. |
| Bỏ `note` trong UPDATE nhưng lại muốn giá trị mặc định | Bỏ cột trong UPDATE chỉ giữ nguyên giá trị cũ | Chỉ định `SET note = DEFAULT` nếu DBMS hỗ trợ. |
| API không phân biệt thiếu trường và null | DTO chỉ có `String note` | Giữ thông tin field presence hoặc dùng kiểu ba trạng thái. |
| Thời điểm `created_at` lệch kỳ vọng | DB sử dụng đồng hồ/session time zone của DBMS | Xác minh quy tắc `CURRENT_TIMESTAMP` và múi giờ. |
| Câu SQL động dễ bị injection | Ghép tên cột do người dùng cung cấp | Dùng danh sách cột cho phép; bind giá trị bằng `PreparedStatement`. |
| `getString("note") == null` bị hiểu là default | SQL `NULL` và chuỗi default khác nhau | Kiểm tra giá trị lưu thực tế, làm rõ quy tắc null/default. |

Nếu thư viện ORM hoặc framework hỗ trợ *dynamic insert* (chỉ đưa cột có giá trị vào `INSERT`), hãy kiểm tra chính xác cơ chế bỏ cột của nó. Một số ORM mặc định **vẫn sinh tham số NULL** cho thuộc tính thiếu giá trị, hoặc có cơ chế riêng để kích hoạt default của database. Không suy ra hành vi ORM chỉ từ tên trường trong DTO.

## 11. Bài thực hành

### Bài 1 — Dự đoán giá trị

Cho bảng `support_ticket` đã khai báo ở mục 2. Sau ba câu lệnh:

~~~sql
INSERT INTO support_ticket (id, title)
VALUES (401, 'A');

INSERT INTO support_ticket (id, title, note)
VALUES (402, 'B', NULL);

INSERT INTO support_ticket (id, title, note)
VALUES (403, 'C', 'Đã xác minh');
~~~

Hãy xác định `status`, `note` ở từng hàng. Đáp án lần lượt: cả ba có `status = 'OPEN'`; `note` là `'Chưa có ghi chú'`, SQL `NULL`, `'Đã xác minh'`.

### Bài 2 — Tìm lỗi trong Java

~~~java
String sql = "INSERT INTO support_ticket(id, title, note) VALUES (?, ?, ?)";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 404L);
    ps.setString(2, "D");
    // Cố ý bỏ marker 3 với suy nghĩ database sẽ dùng DEFAULT.
    ps.executeUpdate();
}
~~~

**Giải thích:** statement vẫn có ba marker nhưng marker 3 chưa được gán. Cần **bỏ cột `note` khỏi SQL** nếu muốn `DEFAULT`, hoặc gọi `ps.setNull(3, Types.VARCHAR)` nếu muốn lưu SQL `NULL`.

### Bài 3 — UPDATE có ba ý định

Ticket 101 đang có `note = 'Ghi chú cũ'`. Hãy viết SQL cho ba yêu cầu: giữ nguyên ghi chú, xóa ghi chú, và đặt lại ghi chú mặc định. Đáp án:

~~~sql
UPDATE support_ticket SET status = 'CLOSED' WHERE id = 101;
UPDATE support_ticket SET note = NULL WHERE id = 101;
-- Câu cuối cần DBMS hỗ trợ cú pháp SET ... = DEFAULT:
UPDATE support_ticket SET note = DEFAULT WHERE id = 101;
~~~

### Bài 4 — API ba trạng thái

Với request tạo ticket, hãy phân biệt:

1. Không có trường `note`: sử dụng `insertUsingDefaults()`.
2. Có trường `note` nhưng giá trị `null`: sử dụng `insertWithExplicitNullNote()`.
3. Có trường `note` là một chuỗi: sử dụng `insertWithNote()`.

Thử đọc lại cả ba hàng bằng `ResultSet.getString("note")` để xác nhận sự khác biệt.

## 12. Checklist trước khi ghi dữ liệu

- Xác định ý định nghiệp vụ: **dùng DEFAULT**, **lưu NULL**, **lưu giá trị cụ thể** hay **giữ nguyên giá trị cũ**.
- Với `INSERT`, dùng danh sách cột chính xác; **bỏ cột** nếu muốn DBMS áp dụng mặc định.
- Nếu cần lưu SQL `NULL`, dùng `setNull(index, Types.XXX)` hoặc cách bind `NULL` có kiểu phù hợp.
- Không để marker `?` chưa gán; không bind chuỗi `"DEFAULT"` và mong nó trở thành từ khóa SQL.
- Xác minh `DEFAULT`, `NOT NULL`, kiểu cột, trigger và quy tắc đặc biệt của DBMS.
- Với `UPDATE`, **bỏ cột là giữ nguyên**; đặt lại mặc định cần biểu thức riêng nếu DBMS hỗ trợ.
- Nếu API cho phép phân biệt thiếu trường, `null` và giá trị, hãy bảo toàn đủ ba trạng thái trong DTO.
- Đọc lại dữ liệu hoặc dùng cơ chế DBMS thích hợp để xác minh giá trị được DB sinh, đặc biệt timestamp và cột generated.

**Ghi nhớ:** `PreparedStatement.setNull()` **truyền SQL NULL tường minh**; muốn dùng `DEFAULT` khi `INSERT`, hãy **bỏ cột khỏi câu lệnh** hoặc chỉ định từ khóa SQL `DEFAULT` khi DBMS hỗ trợ. Với `UPDATE`, bỏ cột **giữ nguyên giá trị hiện tại**. Tách bạch các ý định này giúp API Java, câu SQL và ràng buộc dữ liệu trong JDBC thể hiện đúng nghiệp vụ.
