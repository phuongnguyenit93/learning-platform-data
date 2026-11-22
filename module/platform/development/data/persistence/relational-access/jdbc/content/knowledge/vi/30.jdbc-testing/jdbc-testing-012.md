# Đánh giá khác biệt giữa cơ sở dữ liệu nhúng và hệ quản trị mục tiêu khi kiểm thử JDBC

Trong chương **Kiểm thử JDBC**, một ứng dụng Java có thể chạy mọi test thành công trên cơ sở dữ liệu nhúng (*embedded database*) nhưng vẫn lỗi khi triển khai với hệ quản trị cơ sở dữ liệu thực tế (*target DBMS*). Lý do là test chỉ chứng minh **mã đã chạy đúng trên môi trường được kiểm tra**, không tự chứng minh mọi quy tắc SQL, kiểu dữ liệu, transaction, locking hay hành vi JDBC driver ở môi trường khác đều giống nhau.

Ví dụ, test dùng H2 trong bộ nhớ có thể cho phép một câu SQL, kiểu dữ liệu hoặc cơ chế khóa mà PostgreSQL, MySQL hay SQL Server xử lý khác. Một câu `INSERT` thành công chưa bảo đảm lấy generated keys giống nhau; một transaction rollback được trong DB nhúng chưa bảo đảm migration DDL cũng rollback được ở DB mục tiêu.

Trong module **JDBC**, nơi ứng dụng truy cập cơ sở dữ liệu quan hệ qua driver và `DataSource`, thao tác SQL tham số hóa bằng `PreparedStatement`, đọc dữ liệu qua `ResultSet`, quản lý kết nối, CRUD, transaction, batching và xử lý lỗi, cần đặt **hợp đồng kiểm thử** rõ ràng: kiểm tra nhanh phần nào bằng DB nhúng và phần nào bắt buộc chạy trên đúng DBMS mục tiêu.

Sau bài học, bạn có thể:

- Phân biệt **DB nhúng để thử nhanh** với **DBMS và driver mục tiêu cần chứng minh tính tương thích**.
- Nhận diện các khác biệt về cú pháp SQL, kiểu dữ liệu, constraint, generated keys, batch, transaction, isolation, concurrency và metadata.
- Thiết kế test theo nhiều tầng, tránh “test xanh” nhưng triển khai lỗi.
- Viết test JDBC với dữ liệu, transaction và hậu điều kiện rõ ràng, sau đó chạy lại trên DB mục tiêu.
- Dùng container hoặc môi trường DB mục tiêu tạm thời để chạy integration test, không phụ thuộc vào một bản DB dùng chung khó kiểm soát.
- Định nghĩa tiêu chí chấp nhận trước khi quyết định dùng DB nhúng cho một phần bộ test.

## 1. Thế nào là cơ sở dữ liệu nhúng và DBMS mục tiêu?

**Cơ sở dữ liệu nhúng** thường chạy trong cùng tiến trình hoặc gắn trực tiếp với ứng dụng kiểm thử, không cần một server DBMS riêng do test quản lý. Ví dụ quen thuộc trong hệ sinh thái Java:

- **H2**: phổ biến cho test JVM nhờ chế độ in-memory và khả năng tạo schema nhanh.
- **HSQLDB**: có chế độ in-process/in-memory, cũng thường được dùng cho test.
- **Apache Derby**: có engine nhúng với JDBC driver tương ứng.
- **SQLite**: engine nhúng, được dùng qua JDBC driver phù hợp (không phải driver SQL mặc định của JDK).

**DBMS mục tiêu** là hệ thống mà ứng dụng thực sự phải vận hành trên đó, ví dụ PostgreSQL, MySQL/InnoDB, MariaDB, SQL Server, Oracle hoặc thậm chí chính SQLite.

Điều quan trọng là **“nhúng” và “mục tiêu” không phải hai nhóm sản phẩm luôn loại trừ nhau**. Nếu ứng dụng chạy SQLite ở production, test SQLite có thể dùng **cùng engine**; vẫn phải so khớp phiên bản, pragma, cách mở kết nối, dữ liệu, filesystem và cấu hình thực tế.

Trong các ví dụ dưới đây:

- H2 in-memory là môi trường **kiểm thử nhanh**.
- PostgreSQL là ví dụ **DBMS mục tiêu**.
- Kết luận về MySQL/SQL Server/Oracle chỉ được xem là hướng dẫn phạm vi cần kiểm thử, **không suy đoán mọi bản phát hành đều có hành vi giống nhau**.

### Mô hình tư duy

~~~mermaid
flowchart TD
    A["Ứng dụng Java / JDBC API"] --> B["Repository + SQL + Transaction"]
    B --> C["Test nhanh trên H2 / DB nhúng"]
    B --> D["Integration test trên PostgreSQL / DB mục tiêu"]
    C --> E["Phản hồi nhanh về logic và đường CRUD cơ bản"]
    D --> F["Bằng chứng về dialect, driver, constraint, khóa và transaction thật"]
    E --> G["CI: nhiều tầng kiểm thử"]
    F --> G
~~~

Một test chạy xanh trên H2 là **bằng chứng có giá trị nhưng phạm vi hẹp**. Nó không thay thế kết quả của test chạy trên DBMS mục tiêu.

## 2. Vì sao cùng một JDBC API vẫn cho kết quả khác?

JDBC chuẩn hóa **cách Java giao tiếp với database**, không chuẩn hóa hoàn toàn mọi hành vi của SQL và server. `Connection`, `PreparedStatement`, `ResultSet` là interface chung, nhưng:

1. **JDBC driver khác nhau**: cách bind tham số, ánh xạ `java.sql.Types`, fetch, generated keys và batch có thể khác.
2. **SQL dialect khác nhau**: cú pháp phân trang, upsert, DDL, biểu thức ngày giờ, JSON và kiểu đặc thù không hoàn toàn portable.
3. **DBMS khác nhau**: MVCC, isolation, khóa, deadlock detection và transaction log được triển khai khác.
4. **Cấu hình khác nhau**: timezone, charset, collation, strict mode, storage engine, extension, quyền truy cập và connection pool làm thay đổi hành vi.
5. **Khối lượng dữ liệu khác nhau**: một truy vấn đúng trên 20 hàng có thể chậm hoặc timeout trên 20 triệu hàng.

| Lớp | Câu hỏi cần đặt | Ví dụ lỗi lọt test |
| --- | --- | --- |
| JDBC API | Driver có hỗ trợ đúng overload/tính năng không? | `RETURN_GENERATED_KEYS` khác hoặc không hỗ trợ |
| SQL dialect | DB đích có hiểu cú pháp không? | `MERGE`/`UPSERT`, `LIMIT`, `RETURNING` |
| Schema | Migration tạo constraint/index đúng không? | H2 bỏ qua kiểu/extension đặc thù |
| Giá trị | Kiểu số, thời gian, Unicode có được giữ đúng không? | Decimal scale hoặc timezone lệch |
| Transaction | Lỗi SQL ảnh hưởng transaction tới mức nào? | PostgreSQL đánh dấu transaction aborted, DB test vẫn chạy tiếp |
| Đồng thời | Hai connection có chặn/xung đột như sản xuất không? | Deadlock/serialization failure không tái hiện |
| Hiệu năng | Query plan và dữ liệu có đại diện không? | Index được dùng khác, N+1 queries không lộ rõ |
| Quyền | Runtime DB role có được cấp quyền đúng không? | Test dùng superuser, production role thiếu quyền |

**Quy tắc:** Muốn chứng minh một đặc tính, phải chạy test trong môi trường có khả năng tái hiện **cơ chế tạo ra đặc tính đó**.

## 3. So sánh nhanh: H2 nhúng và PostgreSQL mục tiêu

Bảng sau minh họa một số **rủi ro tương thích cần kiểm thử**, không phải kết luận tuyệt đối cho mọi phiên bản:

| Chủ đề | H2 in-memory | PostgreSQL mục tiêu | Hệ quả cho test |
| --- | --- | --- | --- |
| Khởi tạo | Rất nhanh; có thể tạo DB bằng URL JDBC | Cần server hoặc container | H2 phù hợp vòng lặp nhanh |
| Kiểu `UUID`, `JSON`, array | Có mức hỗ trợ và cách biểu diễn riêng theo phiên bản | Có các kiểu/toán tử/cơ chế index đặc thù | Test truy vấn kiểu đặc thù trên PG |
| `LIMIT`/`OFFSET` | Có thể hỗ trợ cú pháp phổ biến | Hỗ trợ cú pháp riêng của PostgreSQL | Cú pháp chạy được chưa bảo đảm semantics tương đương |
| `INSERT ... RETURNING` | Tùy chế độ/phiên bản/khả năng tương thích | Là tính năng quan trọng của PostgreSQL | Test SQL thực tế trên PG |
| `ON CONFLICT` | Mức mô phỏng phụ thuộc phiên bản/mode | Semantics, constraint và predicate theo PostgreSQL | Không lấy test H2 thay cho PG |
| Identifier và collation | Quy tắc mặc định/config riêng | Quy tắc identifier/locale/collation của PG | Test tên cột và tìm kiếm chữ hoa/dấu |
| Transaction sau lỗi SQL | Có thể tiếp tục xử lý khác PG | Nhiều lỗi khiến transaction ở trạng thái aborted | Test rollback và khôi phục trên PG |
| Isolation/locking | Engine/chiến lược khóa riêng | MVCC và khóa của PostgreSQL | Test race/deadlock trên PG |
| Execution plan | Bộ tối ưu, statistics riêng | Bộ tối ưu PostgreSQL | Benchmark/EXPLAIN trên PG |
| JDBC driver | Driver H2 | pgJDBC | Kiểm thử API driver ở DB mục tiêu |

### H2 `MODE=PostgreSQL` có thay thế PostgreSQL không?

Không. Chế độ tương thích giúp **một phần cú pháp và cách diễn giải SQL** gần PostgreSQL hơn, nhưng không biến engine H2 thành PostgreSQL.

Ví dụ URL có thể trông như:

~~~text
jdbc:h2:mem:testdb;MODE=PostgreSQL;DB_CLOSE_DELAY=-1
~~~

Không được suy ra từ `MODE=PostgreSQL` rằng test có cùng:

- Cơ chế MVCC/SSI và luật phát hiện serialization failure.
- Hành vi locking, deadlock và lock timeout.
- Kiểu extension, toán tử JSONB, full-text search, function hoặc index chuyên biệt.
- SQLState/vendor error code của pgJDBC.
- Hành vi protocol, fetch size, server cursor, streaming LOB.
- Execution plan và hiệu năng của PostgreSQL.

**Dùng compatibility mode như công cụ giúp test nhanh**, không dùng nó làm bằng chứng thay thế test PostgreSQL thật.

## 4. Những khác biệt SQL và schema dễ bị bỏ sót

### 4.1. Tạo khóa tự sinh

Các hệ quản trị có cú pháp tạo khóa tự sinh khác nhau, chẳng hạn:

~~~sql
-- Ví dụ PostgreSQL:
CREATE TABLE events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL
);
~~~

Trong H2 có những cú pháp identity tương tự; ở MySQL thường gặp `AUTO_INCREMENT`; SQLite có ngữ nghĩa `INTEGER PRIMARY KEY` riêng. **Cú pháp trông giống không chứng minh mọi thuộc tính giống nhau**, ví dụ cách cấp lại sequence, xử lý ID tự gán và giá trị sau rollback.

Ngay cả khi bảng tạo thành công, cách lấy khóa bằng JDBC vẫn phải test:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

static long insertAndReadGeneratedKey(
        Connection conn, String payload
) throws SQLException {
    String sql = "INSERT INTO events (payload) VALUES (?)";

    try (PreparedStatement ps = conn.prepareStatement(
            sql, Statement.RETURN_GENERATED_KEYS)) {
        ps.setString(1, payload);

        if (ps.executeUpdate() != 1) {
            throw new SQLException("Không thêm đúng một sự kiện");
        }

        try (ResultSet keys = ps.getGeneratedKeys()) {
            if (!keys.next()) {
                throw new SQLException("Không nhận được generated key");
            }
            long id = keys.getLong(1);
            if (keys.wasNull() || id <= 0) {
                throw new SQLException("Generated key không hợp lệ");
            }
            return id;
        }
    }
}
~~~

**Cần kiểm chứng trên DB mục tiêu:** driver có trả khóa không, thứ tự khóa khi batch, kiểu Java của khóa, câu `INSERT` nào hỗ trợ generated keys và cách transaction ảnh hưởng tới sequence. Không giả định ID tăng liên tục vì rollback có thể để lại khoảng trống sequence.

### 4.2. Upsert và câu SQL đặc thù

Ví dụ PostgreSQL:

~~~sql
INSERT INTO customer_settings (customer_id, key_name, value_text)
VALUES (?, ?, ?)
ON CONFLICT (customer_id, key_name)
DO UPDATE SET value_text = EXCLUDED.value_text;
~~~

Một hệ khác có thể dùng `ON DUPLICATE KEY UPDATE` hoặc `MERGE` với ngữ nghĩa và rủi ro đồng thời khác nhau. Nếu ứng dụng triển khai SQL đặc thù, hãy **chạy đúng SQL đó trên DBMS mục tiêu**. Đừng sửa thành một câu khác trong test H2 rồi coi chúng đã kiểm tra cùng hành vi.

### 4.3. Migration DDL và transaction

Chạy migration trên DB nhúng có thể bỏ lộ khác biệt:

- Một số DBMS có DDL **implicit commit** hoặc hành vi đặc thù, trong khi PostgreSQL cho phép nhiều thao tác DDL tham gia transaction.
- Tên kiểu, index, constraint, default expression, generated column và extension có thể không giống.
- Cú pháp SQL được bộ migration/tool sửa theo dialect có thể khác test tự viết.
- Quyền tạo bảng/index/schema có thể khác tài khoản ứng dụng.
- Thứ tự migration và migration dữ liệu cũ quan trọng hơn một schema sạch tạo từ đầu.

**Thực hành:** Integration test trên DB mục tiêu nên chạy **chính các migration mà ứng dụng triển khai**, không tạo một bảng tối giản bằng tay rồi tuyên bố migration đã được kiểm thử.

## 5. Kiểu dữ liệu và chuyển đổi JDBC cần kiểm tra theo DBMS đích

Cùng một câu `PreparedStatement.setObject(...)` có thể nhận cách ánh xạ khác nhau từ driver. Các trường hợp có nguy cơ cao:

| Kiểu dữ liệu | Điều cần xác nhận |
| --- | --- |
| `BOOLEAN`/`BIT` | DBMS lưu boolean thật hay ánh xạ qua số, cách đọc `getBoolean()` |
| `DECIMAL(p,s)` | Precision, scale, làm tròn, overflow và `BigDecimal` |
| `DATE`, `TIME` | Chuyển sang `LocalDate`/`LocalTime`, giới hạn giá trị |
| `TIMESTAMP` | Precision phần giây và timezone/không timezone |
| `TIMESTAMP WITH TIME ZONE` | Ánh xạ `OffsetDateTime`, lưu giữ instant/offset |
| `VARCHAR`/`NVARCHAR` | Collation, Unicode, giới hạn ký tự/byte và normalization |
| `BLOB`/`CLOB`/`BYTEA` | Buffering, streaming và transaction giữ locator |
| `UUID`/`JSON`/array | Kiểu đặc thù, toán tử SQL và cách `getObject()` trả giá trị |
| `NULL` | Sự khác biệt giữa SQL NULL và giá trị Java mặc định |

### Ví dụ số tiền: không so sánh `BigDecimal` thiếu ngữ nghĩa

~~~java
import java.math.BigDecimal;
import java.sql.PreparedStatement;

BigDecimal amount = new BigDecimal("1234.50");
ps.setBigDecimal(1, amount);
~~~

Trên cột `DECIMAL(12, 2)`, hãy kiểm tra **giá trị số và scale theo chính sách** sau khi đọc lại. Nếu test dùng:

~~~java
assertEquals(new BigDecimal("1234.50"), actual);
~~~

`BigDecimal.equals()` còn kiểm tra scale; `1234.5` và `1234.50` không `equals` dù so sánh số bằng nhau. Nếu hợp đồng nghiệp vụ yêu cầu **đúng scale**, assert cụ thể; nếu chỉ yêu cầu giá trị số, có thể so bằng `compareTo()`. Đừng mặc định một kiểu so sánh cho mọi trường hợp.

### Timezone và độ chính xác thời gian

~~~java
import java.sql.PreparedStatement;
import java.time.OffsetDateTime;

OffsetDateTime happenedAt =
    OffsetDateTime.parse("2026-11-17T08:30:12.123456+07:00");

ps.setObject(1, happenedAt);
~~~

Kiểm chứng ở DB mục tiêu:

1. Cột thuộc kiểu `TIMESTAMP` hay kiểu có timezone?
2. Driver có hỗ trợ `setObject(OffsetDateTime)` và `getObject(..., OffsetDateTime.class)` không?
3. Sau round-trip, **instant** có được giữ đúng không? Offset hiển thị có thể thay đổi khi hệ quản trị chuẩn hóa.
4. Phần giây có bị làm tròn/cắt tới độ chính xác mà cột hỗ trợ không?
5. Timezone của session, JVM và server có ảnh hưởng tới biểu diễn không?

H2 test chạy cùng JVM có thể khiến sai khác timezone không lộ ra; DB server mục tiêu có cấu hình riêng, nên phải có test ngày giờ tại các ranh giới, kể cả thời điểm đổi DST nếu miền nghiệp vụ liên quan.

### Unicode và collation

Một test chỉ dùng `"Hello"` không thể kiểm tra:

- Tiếng Việt có dấu, Unicode nhiều byte.
- Emoji/code point ngoài BMP.
- Chuỗi dạng dựng sẵn và dấu kết hợp.
- So sánh không phân biệt dấu/chữ hoa, sắp xếp và tìm kiếm.
- Độ dài `VARCHAR` theo byte hay ký tự.

Hãy xây fixture có giá trị như `"Đặng"`, `"e\u0301"`, `"😀"` và các chuỗi sát giới hạn cột, rồi so round-trip theo chính sách đã xác định. Không giả định collation của H2 khớp PostgreSQL, MySQL hoặc SQL Server.

## 6. Constraint và NULL: DB nhúng có thể che lỗi dữ liệu

Kiểm thử JDBC không nên chỉ kiểm tra câu lệnh `INSERT` trả `1`. Cần xác nhận DBMS **thực thi đúng ràng buộc dữ liệu**:

- `PRIMARY KEY` và `UNIQUE`.
- `FOREIGN KEY` (bao gồm thứ tự chèn/xóa và hành vi `ON DELETE`).
- `NOT NULL` và `CHECK`.
- Giá trị mặc định, kiểu cột, chiều dài/precision.
- Ràng buộc uniqueness với nhiều giá trị `NULL`, collation hoặc biểu thức.
- Trigger và generated columns nếu nghiệp vụ sử dụng.
- Tương tác constraint với transaction khi một câu SQL thất bại.

### Điểm riêng thường bị quên ở SQLite

Một số cấu hình SQLite yêu cầu bật kiểm tra foreign key **trên từng connection**, ví dụ:

~~~sql
PRAGMA foreign_keys = ON;
~~~

Đừng suy ra “DDL có `FOREIGN KEY`” đồng nghĩa mọi connection trong mọi phiên bản/cấu hình SQLite chắc chắn đang thực thi nó. Khi SQLite là DB test hoặc DB mục tiêu, kiểm tra `PRAGMA foreign_keys` và cấu hình driver/connection pool thực tế.

### `UNIQUE` và `NULL`

Nhiều DBMS cho phép nhiều hàng có `NULL` trong cột chịu `UNIQUE`, nhưng có khác biệt theo DBMS, thiết kế index và các tùy chọn. Nếu nghiệp vụ yêu cầu “chỉ một hàng thiếu giá trị” hoặc uniqueness không phân biệt hoa/thường, cần định nghĩa ràng buộc đúng trên DB mục tiêu và viết test ở đó.

**Bài học:** Test cần chứng minh **bất biến dữ liệu** và trạng thái sau lỗi, không chỉ chứng minh SQL cú pháp đúng.

## 7. Transaction và isolation: phần dễ khác nhất

Một transaction có thể có hành vi khác đáng kể sau cùng một lỗi SQL:

| Tình huống | Rủi ro nếu chỉ test embedded |
| --- | --- |
| Duplicate key giữa transaction | DB test cho tiếp tục, PostgreSQL có thể đánh dấu transaction aborted |
| Deadlock | Lịch khóa/phát hiện nạn nhân khác |
| Lock wait timeout | Có DB rollback câu lệnh, có DB hủy transaction tùy cấu hình |
| Serialization failure | Xuất hiện trên DBMS mục tiêu khi nhiều giao dịch xung đột |
| `Savepoint` | Mức hỗ trợ và các loại lỗi được phép phục hồi khác |
| DDL trong transaction | Một số DBMS có implicit commit |
| Network loss đúng lúc `commit()` | Kết quả commit có thể không xác định; embedded không mô phỏng lỗi mạng |
| `autoCommit`/connection pool | Pool có thể tái sử dụng connection với trạng thái khác |

### Lỗi SQL và trạng thái transaction PostgreSQL

Ví dụ PostgreSQL:

~~~sql
BEGIN;

INSERT INTO customers(id, email)
VALUES (1, 'first@example.test');

-- Lệnh trùng PK gây lỗi:
INSERT INTO customers(id, email)
VALUES (1, 'second@example.test');

-- Giao dịch bị đánh dấu lỗi:
SELECT COUNT(*) FROM customers;
-- Có thể nhận SQLSTATE 25P02 cho tới khi rollback.

ROLLBACK;
~~~

Trên PostgreSQL, sau một lỗi SQL trong transaction, transaction thường chuyển sang trạng thái aborted và các câu lệnh tiếp theo bị từ chối cho tới khi rollback hoặc rollback tới savepoint hợp lệ.

Một DB nhúng có thể xử lý lỗi ở mức statement khác. Nếu test chỉ xác nhận `SQLException` xuất hiện nhưng **không kiểm tra transaction còn dùng được hay phải rollback**, sản phẩm có thể lỗi ở bước kế tiếp.

### Isolation level không phải một lời hứa đồng nhất

JDBC định nghĩa các mức:

~~~java
Connection.TRANSACTION_READ_COMMITTED
Connection.TRANSACTION_REPEATABLE_READ
Connection.TRANSACTION_SERIALIZABLE
~~~

Nhưng cách DBMS triển khai snapshot, row locks, predicate/range locks và serialization khác nhau. Chạy cùng `setTransactionIsolation(...)` trên H2 và PostgreSQL **không có nghĩa hai lịch transaction đồng thời sẽ có cùng kết quả**.

Những test bắt buộc chạy trên DB mục tiêu thường bao gồm:

1. Hai connection cập nhật cùng hàng.
2. Khóa hàng theo thứ tự ngược tạo deadlock.
3. Write skew hoặc invariant đa hàng ở isolation đã chọn.
4. Retry sau SQLState tương ứng, trên **transaction mới**.
5. Đảm bảo rollback toàn bộ thao tác cần tính nguyên tử.
6. Truy vấn trên pooled connection sau exception/timeout/cancel.

Không viết test đồng thời chỉ dựa vào `Thread.sleep()` và tin rằng đã tái hiện race. Dùng barrier/latch, quan sát trạng thái DB khi cần và deadline để tránh test treo vô hạn.

## 8. Generated keys, batch và metadata: phải xác minh driver thật

### Generated keys

`Statement.RETURN_GENERATED_KEYS` có thể có giới hạn tùy driver và câu SQL. Kiểm tra:

- `getGeneratedKeys()` trả bao nhiêu hàng sau `INSERT`.
- Kiểu/cột giá trị được trả về.
- Có hoạt động khi `executeBatch()` không.
- Thứ tự khóa có tương ứng thứ tự input không; không mặc định nếu tài liệu driver không cam kết.
- Sequence/identity có thể tạo khoảng trống sau rollback.

### Batch update counts

~~~java
int[] counts = preparedStatement.executeBatch();
~~~

Driver có thể trả:

- Số hàng cập nhật cho từng lệnh.
- `Statement.SUCCESS_NO_INFO` khi thành công nhưng không biết số hàng.
- `Statement.EXECUTE_FAILED` trong một số trường hợp tiếp tục sau lỗi.

Khi lỗi, `BatchUpdateException.getUpdateCounts()` có thể chứa kết quả của phần trước lỗi hoặc nhiều phần tử hơn nếu driver tiếp tục thực thi. **Không lấy hành vi của H2 làm mặc định cho pgJDBC/MySQL driver.** Nếu nghiệp vụ yêu cầu nguyên tử cả batch, chạy trong transaction, kiểm tra counts và rollback khi không đạt hậu điều kiện.

### `DatabaseMetaData` và `ResultSetMetaData`

Hai driver có thể báo khác về:

- `supportsBatchUpdates()`, `supportsSavepoints()`.
- `supportsResultSetType(TYPE_SCROLL_SENSITIVE)` và tính updatable.
- `getMaxColumnsInTable()`, `getMaxStatementLength()`; nhiều API trả `0` khi không giới hạn hoặc không rõ.
- `getColumns()`: `DATA_TYPE`, `TYPE_NAME`, `COLUMN_SIZE`, `DECIMAL_DIGITS` và nullability.
- `ResultSetMetaData.getColumnTypeName()` cho kiểu DBMS đặc thù.

Khi ứng dụng sử dụng metadata để sinh schema, serialize dữ liệu hoặc chọn tính năng, test phải chạy trên driver mục tiêu. Một kết quả metadata từ H2 không phải ảnh chụp năng lực của PostgreSQL.

## 9. Hiệu năng, network và môi trường kết nối

DB nhúng thường chạy trong cùng tiến trình, khác đáng kể một server DB có kết nối mạng:

| Yếu tố | DB nhúng | Server DB mục tiêu |
| --- | --- | --- |
| Network round-trip | Thường rất thấp/không qua TCP | Có latency, TLS và lỗi mạng |
| Connection pool | Có thể không cần trong test nhỏ | Quan trọng với concurrency và giới hạn session |
| Query planner | Optimizer riêng, dữ liệu nhỏ | Statistics/index/plan thực tế khác |
| Batch throughput | Không nhất thiết phản ánh tải thật | Driver rewrite, protocol và mạng ảnh hưởng |
| Fetch/streaming | Bộ nhớ dùng trong cùng process | Có server cursor, packet, socket, buffer |
| Timeout/cancel | Khó mô phỏng một số lỗi mạng | `setQueryTimeout`, cancel và network timeout cần thử |
| Deadlock/load | Khó tạo cùng tải/khóa | Cần test gần workload thật |
| Privileges | Test thường dùng admin | Production thường dùng role tối thiểu |

**Microbenchmark trên H2 không phải kết luận hiệu năng cho PostgreSQL.** Một câu query chậm ở môi trường đích có thể do index, join order, thống kê, kích thước bảng, query plan, lock wait, network hoặc cấu hình server, chứ không liên quan độ nhanh/chậm của H2.

Nên có các bài test riêng về:

- Latency khi số hàng lớn.
- N+1 query và round-trip.
- Phân trang keyset/offset, thứ tự ổn định.
- Batch size, memory và các giới hạn payload.
- Fetch size, streaming BLOB/CLOB.
- Query timeout, `Statement.cancel()` và mất kết nối.
- Connection pool exhaustion, leak và đóng tài nguyên.

Những bài test này nên dùng dữ liệu đại diện, có đo đạc và giới hạn chạy; không biến bộ unit test nhanh thành benchmark kéo dài bất ổn.

## 10. Chọn đúng tầng kiểm thử

Một chiến lược thực dụng thường có **nhiều tầng**, mỗi tầng tối ưu cho một loại rủi ro:

~~~mermaid
flowchart TD
    U["Unit tests: không cần DB<br/>logic, mapping, validation"] --> E["Embedded JDBC tests<br/>CRUD cơ bản, vòng phản hồi nhanh"]
    E --> T["Target DB integration tests<br/>SQL dialect, driver, migration, transaction"]
    T --> S["Staging / performance / resilience<br/>load, network, pool, failover"]
~~~

| Tầng | Tốc độ | Phạm vi chứng minh | Ví dụ |
| --- | --- | --- | --- |
| Unit, không DB | Nhanh nhất | Logic tính toán, mapping, lựa chọn câu query, validation | Hàm tạo filter, map DTO |
| DB nhúng | Nhanh, dễ cô lập | JDBC resource management và SQL **được DB nhúng hỗ trợ** | CRUD đơn giản, null mapping |
| DBMS mục tiêu trên container/instance tạm | Chậm hơn, gần thực tế hơn | Dialect, driver, schema, constraint, isolation | Migration, generated keys, rollback |
| Staging giống production | Tốn tài nguyên, cần vận hành | Network, pool, config, dữ liệu/tải và quyền gần thực tế | Concurrency, performance, recovery |

**Không phải mọi test đều chạy trên cả bốn tầng.** Nhưng một chức năng phụ thuộc hành vi PostgreSQL thì ít nhất phải có **test PostgreSQL thật** cho hành vi đó.

### Ma trận mức ưu tiên

| Đặc tính | Test nhúng | Test DB mục tiêu | Ghi chú |
| --- | --- | --- | --- |
| Mapping Java thuần/validation | Có thể không cần DB | Không bắt buộc cho mọi trường hợp | Unit test nhanh |
| SQL đơn giản portable | Hữu ích | Nên có smoke/contract test | Đảm bảo cú pháp và schema thật |
| Migration, DDL, extension | Chỉ kiểm một phần | **Bắt buộc** | Không mô phỏng bằng schema khác |
| Unique/FK/CHECK quan trọng | Hữu ích | **Bắt buộc** | Bất biến dữ liệu |
| Generated keys/UUID/JSON/array | Có thể dùng làm smoke | **Bắt buộc** | Driver và type mapping |
| Batch/LOB/stream | Test thao tác cơ bản | **Bắt buộc** cho tính năng thật | Buffering và hỗ trợ driver |
| Transaction/deadlock/isolation | Không đủ | **Bắt buộc** | Engine locking khác nhau |
| RLS/role/quyền | Thường không tương đương | **Bắt buộc** | Test bằng runtime role |
| Query plan/performance | Không đại diện | **Bắt buộc** trên môi trường thích hợp | Dữ liệu/index/config |
| Network failure/cancel | Rất hạn chế | **Bắt buộc** cho yêu cầu resilience | Cần test có kiểm soát |

“Bắt buộc” ở đây có nghĩa **bắt buộc để chứng minh tính năng đó trên DBMS mục tiêu**, không có nghĩa phải tái chạy mọi test trong mọi commit.

## 11. Chuẩn bị phép thử hợp đồng JDBC dùng chung

**Contract test** là cùng một tập điều kiện và hậu điều kiện được chạy trên nhiều môi trường. Một số test xác nhận hợp đồng chung như rollback và unique constraint; một số test là **DBMS-specific**.

Ta chuẩn bị bảng minh họa được migration hoặc fixture test tạo ra:

~~~sql
CREATE TABLE jdbc_contract_records (
    id BIGINT PRIMARY KEY,
    external_key VARCHAR(80) NOT NULL UNIQUE,
    amount DECIMAL(18, 2) NOT NULL,
    status VARCHAR(20) NOT NULL
);
~~~

Bảng này cố ý dùng **giao điểm SQL phổ biến** giữa H2 và PostgreSQL để minh họa contract test. Trong ứng dụng thật, hãy chạy migration production trên DB mục tiêu và đừng sửa schema đích để làm vừa lòng H2.

### Hợp đồng test muốn chứng minh

Giả sử database test **đã có bảng và chưa có các ID fixture**.

1. Dùng một transaction thủ công.
2. Chèn một hàng `id = 900001`, `external_key = "contract-rollback"`.
3. Chèn một hàng khác có `id = 900002` nhưng **cùng external key**.
4. Câu thứ hai phải bị DBMS từ chối vì `UNIQUE`.
5. Gọi `rollback()` toàn transaction.
6. Dùng một connection mới kiểm tra **cả hai ID đều không tồn tại**.

Test này không mặc định loại `SQLException` hay SQLState giống nhau ở H2 và PostgreSQL. Hợp đồng kiểm tra **bất biến rollback + unique**.

### Mã JUnit Jupiter (JUnit 5) dùng `DataSource`

~~~java
import static org.junit.jupiter.api.Assertions.*;

import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class JdbcContractAssertions {
    private JdbcContractAssertions() {}

    /**
     * Yêu cầu bảng jdbc_contract_records đã được tạo
     * và hai ID fixture chưa có sẵn.
     */
    public static void verifyUniqueConstraintAndRollback(
            DataSource dataSource
    ) throws SQLException {

        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(false);
            try {
                insert(conn, 900001L, "contract-rollback");
                assertThrows(SQLException.class, () ->
                    insert(conn, 900002L, "contract-rollback"));
            } finally {
                // Kể cả khi assertion thất bại, test phải dọn transaction.
                conn.rollback();
            }
        }

        // Kết nối khác chứng minh chưa có dữ liệu được commit.
        try (Connection verify = dataSource.getConnection();
             PreparedStatement ps = verify.prepareStatement(
                 "SELECT COUNT(*) FROM jdbc_contract_records "
                 + "WHERE id IN (?, ?)")) {

            ps.setLong(1, 900001L);
            ps.setLong(2, 900002L);

            try (ResultSet rs = ps.executeQuery()) {
                assertTrue(rs.next());
                assertEquals(0L, rs.getLong(1),
                    "Cả hai hàng phải được rollback");
            }
        }
    }

    private static void insert(
            Connection conn, long id, String key
    ) throws SQLException {
        String sql = """
            INSERT INTO jdbc_contract_records
                (id, external_key, amount, status)
            VALUES (?, ?, ?, ?)
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setString(2, key);
            ps.setBigDecimal(3, new BigDecimal("123.45"));
            ps.setString(4, "DRAFT");

            assertEquals(1, ps.executeUpdate());
        }
    }
}
~~~

**Giới hạn của ví dụ:**

- Bảng test phải được tạo từ trước, với dữ liệu fixture cô lập. Không chạy nhiều test đồng thời trên cùng bảng/ID nếu không có namespace hoặc cleanup riêng.
- DDL tạo bảng diễn ra **trước transaction đang test**; không đặt thao tác tạo/xóa bảng vào chính phép thử rollback để tránh kết luận sai do implicit commit của một số DBMS.
- Test này dùng chung **ý định và hậu điều kiện**, nhưng không chứng minh SQLState, lock wait, generated keys hay mọi ràng buộc của DBMS tương đương.
- `assertThrows(SQLException.class, ...)` chấp nhận driver ném lớp con như `SQLIntegrityConstraintViolationException`. Nếu muốn phân loại mã lỗi, thêm assertion **riêng theo DBMS**.
- `conn.rollback()` trong `finally` giúp kết thúc giao dịch khi assertion lỗi; trong hệ thống thật cần bảo vệ lỗi rollback bằng `addSuppressed()` để không che lỗi gốc.
- Đây là test kỹ thuật trong môi trường test; không dùng cùng ID fixture trên dữ liệu thật.

## 12. Chạy contract test trên H2 để lấy phản hồi nhanh

Ví dụ với H2 JDBC driver và JUnit 5 đã được cấu hình trong **test dependencies**:

~~~java
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.Statement;
import java.util.UUID;

class H2JdbcContractTest {
    @Test
    void uniqueRollbackContract() throws Exception {
        JdbcDataSource dataSource = new JdbcDataSource();

        // Tên DB độc lập cho mỗi test.
        String name = "contract_"
            + UUID.randomUUID().toString().replace("-", "");

        dataSource.setURL(
            "jdbc:h2:mem:" + name + ";DB_CLOSE_DELAY=-1"
        );
        dataSource.setUser("sa");
        dataSource.setPassword("");

        createPortableFixture(dataSource);

        JdbcContractAssertions
            .verifyUniqueConstraintAndRollback(dataSource);
    }

    static void createPortableFixture(DataSource dataSource)
            throws Exception {
        try (Connection conn = dataSource.getConnection();
             Statement st = conn.createStatement()) {
            st.execute("""
                CREATE TABLE jdbc_contract_records (
                    id BIGINT PRIMARY KEY,
                    external_key VARCHAR(80) NOT NULL UNIQUE,
                    amount DECIMAL(18, 2) NOT NULL,
                    status VARCHAR(20) NOT NULL
                )
                """);
        }
    }
}
~~~

**`DB_CLOSE_DELAY=-1`** giữ H2 in-memory database tồn tại sau khi đóng connection cuối trong vòng đời tiến trình, phục vụ nhiều connection kiểm thử. Khi mỗi test dùng tên DB duy nhất, dữ liệu không va chạm với test khác. Với ứng dụng thật cần quản lý lifecycle và dọn tài nguyên phù hợp.

Kết quả test này chỉ chứng minh hợp đồng **trên H2**. Muốn chứng minh trên PostgreSQL, ta chạy lại cùng contract bằng driver PostgreSQL.

## 13. Chạy cùng contract trên PostgreSQL bằng Testcontainers

**Testcontainers** là một cách tạo DBMS mục tiêu trong container cho integration test. Nó là **thư viện bên ngoài JDK**, không phải phần của JDBC chuẩn; cần cấu hình dependency JUnit 5, Testcontainers và JDBC driver tương ứng, cùng môi trường container runtime (ví dụ Docker/engine tương thích) có thể chạy được.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.postgresql.ds.PGSimpleDataSource;

class PostgreSqlJdbcContractIT {
    @Test
    void uniqueRollbackContract() throws Exception {
        try (PostgreSQLContainer<?> pg =
                 new PostgreSQLContainer<>("postgres:16-alpine")) {
            pg.start();

            PGSimpleDataSource dataSource =
                new PGSimpleDataSource();
            dataSource.setServerNames(
                new String[] {pg.getHost()});
            dataSource.setPortNumbers(
                new int[] {pg.getMappedPort(5432)});
            dataSource.setDatabaseName(pg.getDatabaseName());
            dataSource.setUser(pg.getUsername());
            dataSource.setPassword(pg.getPassword());

            // Ở ví dụ nhỏ này dùng chung DDL fixture.
            // Dự án thật phải chạy migration sản phẩm.
            H2JdbcContractTest.createPortableFixture(
                dataSource);

            JdbcContractAssertions
                .verifyUniqueConstraintAndRollback(dataSource);
        }
    }
}
~~~

Ví dụ minh họa việc dùng **cùng DataSource contract** với một driver/engine khác. Trong dự án thật, đừng đặt helper fixture dùng chung trong một lớp có tên `H2JdbcContractTest`; nên chuyển helper sang module test utilities riêng. Để ngắn gọn, đoạn ví dụ tạm gọi lại method public static đã nêu ở phần 12.

### Những điều phải cấu hình đúng

- Chọn image PostgreSQL **cùng major version** với môi trường mục tiêu khi hành vi cần chính xác; `postgres:16-alpine` chỉ là ví dụ, không khẳng định sản xuất đang chạy 16.
- Dùng JDBC driver version đã được kiểm thử với ứng dụng.
- Chạy **migration thật**, schema, extension, collation và timezone quan trọng.
- Cấu hình runtime DB role ít quyền nếu test liên quan phân quyền/RLS.
- Không dùng database production để chạy test có `CREATE TABLE`, `DELETE` hoặc rollback.
- Giới hạn thời gian khởi động container, số lượng container chạy đồng thời và tài nguyên CI.
- Các bộ test phụ thuộc network, TLS, proxy hay failover vẫn có thể cần môi trường staging riêng; container local không tái hiện tất cả đặc tính hạ tầng.

**Lưu ý biên dịch:** Mã Testcontainers đòi phiên bản API và dependency tương thích. Mục tiêu bài học là mô hình test; hãy điều chỉnh tên module, cách khởi tạo container và phiên bản thư viện theo project của bạn.

### Không bắt buộc phải dùng Testcontainers

Nếu CI đã cung cấp PostgreSQL riêng cho test, có thể tạo `DataSource` trỏ đến database tạm cô lập đó. Điều bắt buộc là **engine/driver/hành vi đủ sát mục tiêu**, chứ không phải một công cụ khởi tạo container cụ thể.

## 14. Những bài integration test cần bổ sung trên DBMS mục tiêu

Contract chung mới kiểm tra được một phần. Với PostgreSQL làm DB đích, nên bổ sung những phép thử cụ thể sau:

### 14.1. Transaction bị đánh dấu lỗi sau SQL vi phạm constraint

~~~java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);
    try {
        // Cố ý tạo lỗi UNIQUE trên bảng fixture riêng.
        // Quan sát SQLState đầu tiên và lỗi khi thử chạy SELECT tiếp.
    } finally {
        conn.rollback();
    }
}
~~~

Khi PostgreSQL ném SQLState trong lớp `23` (ví dụ `23505` cho unique violation), giao dịch thường không còn tiếp tục bình thường và một câu SQL sau đó có thể nhận `25P02` cho tới rollback. Đây là đặc tính cần test trên DB mục tiêu, không ép H2 mô phỏng chính xác.

### 14.2. Deadlock và retry transaction

Tạo hai connection, cho chúng khóa hai hàng theo thứ tự ngược, dùng barrier để điều phối và đặt timeout an toàn. Xác nhận DBMS báo deadlock, một transaction bị chọn làm nạn nhân, và ứng dụng **retry toàn transaction** chứ không chỉ SQL cuối cùng.

Chú ý: không được viết test deadlock không có deadline. Nếu một luồng lỗi sớm, phải cleanup và nhả khóa cho luồng còn lại.

### 14.3. Transaction isolation và write skew

Với một invariant như “mỗi ca trực phải còn ít nhất một bác sĩ”, viết test hai transaction `SERIALIZABLE` cùng đọc trước khi sửa hai hàng khác nhau. Trên PostgreSQL, có thể có serialization failure `40001`; kiểm tra ứng dụng retry cả đơn vị nghiệp vụ. Trên H2, đừng giả định cùng lịch sẽ sinh đúng lỗi đó.

### 14.4. Generated keys và batch

Kiểm tra số hàng và thứ tự generated keys từ driver thực, `SUCCESS_NO_INFO`, `BatchUpdateException`, trạng thái transaction sau lỗi và logic rollback.

### 14.5. Character encoding, timezone và binary streaming

Dùng fixture Unicode, dữ liệu sát chiều dài cột, timestamp có timezone, `BigDecimal` sát precision/scale và payload BLOB đủ lớn để driver cần xử lý streaming.

### 14.6. Connection pool và thời gian chờ

Kiểm tra trả kết nối sau lỗi, trạng thái `autoCommit`/isolation/read-only có được reset đúng, query timeout và cancellation có thể làm connection lỗi không, resource leak có xuất hiện không.

Các phép thử này **không nên vô điều kiện chạy trong bộ unit test vài giây**; đưa vào integration suite hoặc CI job có điều kiện môi trường và ngân sách tài nguyên rõ ràng.

## 15. Không để test fixture khác môi trường sản xuất

Một trong những nguyên nhân “xanh ở test, đỏ ở production” là **test schema và cấu hình đã bị đơn giản hóa quá mức**.

Checklist nên thực hiện trước khi tin integration test:

| Thành phần | Cần giống hoặc được kiểm soát thế nào? |
| --- | --- |
| DBMS engine | Đúng PostgreSQL/MySQL/... như mục tiêu |
| Server version | Cùng major và chú ý minor khi cần |
| JDBC driver | Đúng phiên bản hoặc dải phiên bản hỗ trợ |
| Migration | Cùng file migration, cùng thứ tự |
| Extensions/functions | Đã cài và cấu hình giống mục tiêu |
| Character set/collation | Đúng ngôn ngữ, quy tắc sắp xếp/so sánh |
| Timezone/session settings | Được đặt có chủ đích, không phụ thuộc máy developer |
| Isolation/autocommit | Giống cấu hình thực tế của pool/service |
| Database role | Runtime role ít quyền thay vì chỉ superuser |
| Indexes/statistics | Có index thực, dữ liệu đại diện cho query plan |
| Storage engine | Quan trọng với hệ hỗ trợ nhiều engine (ví dụ MySQL) |
| Connection pool | Quy mô, retry, timeout và reset state phù hợp |
| Đồng thời | Có đủ hai hoặc nhiều connection để tạo tranh chấp |
| Network | Khi test timeout, TLS/failover phải có môi trường riêng |
| Dữ liệu | Có NULL, trùng, Unicode, giá trị biên và dữ liệu lớn |

Không nhất thiết mọi cấu hình phải giống hệt từng byte trong mọi test; nhưng phải biết **khác ở đâu** và liệu sự khác biệt có ảnh hưởng đến kết luận hay không.

### Migration sạch khác migration nâng cấp

Test chỉ `CREATE TABLE` trên database rỗng có thể bỏ sót lỗi chuyển đổi dữ liệu khi nâng cấp schema thật:

~~~text
Schema V1 + dữ liệu cũ
    → Migration V2
    → Backfill / đổi constraint
    → Schema V3
~~~

Nên có test từ dữ liệu và phiên bản schema cũ cần được hỗ trợ, chạy migration như quy trình triển khai và xác minh dữ liệu/constraint sau nâng cấp.

## 16. Thiết kế test ổn định, độc lập và dễ chạy trong CI

### 16.1. Mỗi test sở hữu dữ liệu của mình

Tránh dùng chung một bảng và ID fixture giữa các test chạy song song. Lựa chọn:

- Một database/schema/container riêng theo test suite.
- Dữ liệu có `run_id` hoặc khóa fixture độc nhất và cleanup có kiểm soát.
- Transaction rollback sau test nếu test **không cần quan sát từ connection khác** và DBMS cho phép.
- Tạo lại schema khi cần kiểm thử migration.

Không mặc định bọc mọi test trong transaction của framework rồi rollback cuối test là đủ: nếu code tạo connection khác, tự commit hoặc chạy async, các thay đổi đó có thể nằm ngoài transaction test.

### 16.2. Assert hậu điều kiện, không chỉ exception

Ví dụ một test rollback đúng phải kiểm tra **dữ liệu sau rollback**; một test optimistic locking phải kiểm tra số hàng bị ảnh hưởng và giá trị không bị ghi đè; một test batch lỗi phải kiểm tra toàn bộ phần việc chưa commit đã được hủy.

### 16.3. Không để test phụ thuộc thứ tự chạy

Mỗi test nên chuẩn bị dữ liệu và cleanup độc lập; test không được chỉ xanh khi một test khác tạo bảng hoặc chèn dữ liệu trước.

### 16.4. Không dùng `Thread.sleep()` làm bằng chứng concurrency

Đối với deadlock, lock wait và serialization, dùng `CountDownLatch`, `CyclicBarrier` hoặc cơ chế đồng bộ tương đương, đồng thời đặt **timeout và cleanup**. Có thể cần quan sát session DBMS để xác nhận trạng thái chờ thật.

### 16.5. Không đoán mã lỗi theo một DBMS khác

Ví dụ:

| Hệ quản trị | Mã thường gặp | Không nên suy ra |
| --- | --- | --- |
| PostgreSQL | `23505` cho unique violation | H2 phải trả y hệt trong mọi trường hợp |
| PostgreSQL | `40P01` cho deadlock | Mọi DBMS đều dùng mã này |
| PostgreSQL | `40001` cho serialization failure | Mọi `40001` của mọi driver có nguyên nhân giống nhau |
| MySQL/InnoDB | Vendor code `1213` thường liên quan deadlock | Chỉ nhìn SQLState đủ để phân loại chi tiết |
| MySQL/InnoDB | Vendor code `1205` thường là lock wait timeout | Lock timeout và deadlock là một |
| PostgreSQL | `25P02` khi transaction đang aborted | DB nhúng nhất thiết có cùng trạng thái |

Muốn viết retry logic dựa vào SQLState/vendor code, có test trực tiếp với **driver/DBMS mục tiêu** và xử lý riêng kết quả commit không rõ ràng.

## 17. Cách đưa test vào pipeline

Một pipeline thực dụng có thể có cấu trúc:

~~~mermaid
flowchart TD
    A["Mỗi commit/PR"] --> B["Unit tests"]
    B --> C["Embedded JDBC smoke tests"]
    C --> D["Target DB integration: migration + contract"]
    D --> E{"Đều PASS?"}
    E -- "Không" --> F["Chặn merge/deploy"]
    E -- "Có" --> G["Build artifact"]
    G --> H["Staging: concurrency/load/resilience"]
    H --> I{"Đạt SLO / quyền / dữ liệu?"}
    I -- "Không" --> F
    I -- "Có" --> J["Đủ điều kiện cho bước release tiếp theo"]
~~~

Thời điểm và phạm vi chạy tùy nhóm:

- **PR thường xuyên:** unit + embedded smoke + một bộ integration nhỏ nhưng quan trọng trên DB mục tiêu.
- **Nightly/release:** integration đầy đủ với nhiều mức isolation, batch, migration từ schema cũ, timezone/encoding và concurrency.
- **Pre-production:** performance, failover, network timeout, connection pool, security role và dữ liệu đại diện.

Nếu pipeline không có container runtime hoặc quyền tạo DB, đừng im lặng bỏ hết integration test rồi báo “tất cả pass”. Báo rõ **nhóm test nào bị skip** và giới hạn của kết quả.

## 18. Phân tích một lỗi lọt từ H2 sang PostgreSQL

Một service có quy trình:

1. Bật `autoCommit = false`.
2. Chèn bản ghi A.
3. Chèn bản ghi B có khóa trùng, bắt `SQLException`.
4. Bỏ qua lỗi vì B “không quan trọng”.
5. Chạy `UPDATE` bản ghi A.
6. `commit()`.

Trên một DB nhúng cụ thể, test có thể thấy bước 5 thành công. Trên PostgreSQL, sau lỗi constraint ở bước 3, transaction thường chuyển sang **aborted**; bước 5 có thể nhận `25P02`.

**Lỗi không nằm ở cú pháp JDBC**, mà ở giả định sai về trạng thái transaction.

Các hướng sửa:

- Nếu lỗi B không được phép bỏ qua: **rollback toàn transaction**, báo lỗi nghiệp vụ.
- Nếu B thực sự tùy chọn: lập `Savepoint` **trước** câu B, rollback tới savepoint khi loại lỗi dự kiến xảy ra, rồi tiếp tục nếu DBMS hỗ trợ và trạng thái transaction còn hợp lệ.
- Nếu có thể dùng câu SQL biểu diễn chính sách bỏ qua trùng (ví dụ PostgreSQL `ON CONFLICT DO NOTHING`), triển khai theo dialect phù hợp và kiểm tra số hàng ảnh hưởng.
- Kiểm thử cả đường thành công và đường constraint failure trên **PostgreSQL thật**.

Chỉ đổi URL H2 sang `MODE=PostgreSQL` **không chứng minh** luồng lỗi được xử lý như pgJDBC.

## 19. Các ngộ nhận thường gặp

| Ngộ nhận | Vì sao không đúng | Hướng xử lý |
| --- | --- | --- |
| “JDBC là chuẩn nên SQL trên mọi DB giống nhau” | JDBC chuẩn hóa API, SQL dialect/engine khác nhau | Test trên DBMS mục tiêu |
| “H2 PostgreSQL mode là PostgreSQL” | Chỉ mô phỏng một phần cú pháp/hành vi | Không bỏ integration PG |
| “Chỉ cần test trên DB nhúng vì nhanh hơn” | Bỏ sót driver, transaction và migration | Phân tầng test |
| “Test rollback chạy xanh là đủ cho transaction” | Có thể chưa test trạng thái sau lỗi SQL | Assert dữ liệu và trạng thái |
| “Có `FOREIGN KEY` trong DDL là chắc được kiểm tra” | Cấu hình/engine có thể khác | Xác minh constraint đang bật |
| “`SQLState` phải giống nhau giữa mọi driver” | Vendor và mapping khác | Test phân loại trên driver đích |
| “Batch thành công nghĩa cả batch đã commit” | `executeBatch` và `commit` tách biệt | Quản lý transaction và counts |
| “`getGeneratedKeys` luôn theo thứ tự input của batch” | Tùy driver và SQL | Xác minh/tạo mapping an toàn |
| “Test dữ liệu ASCII đủ cho Unicode” | Byte length, collation và ký tự nhiều byte khác | Fixture Unicode/boundary |
| “Test timezone trên cùng JVM là đủ” | Server/session timezone khác | Test round-trip trên DB mục tiêu |
| “Test dùng root/admin gần giống production” | Bỏ lộ lỗi quyền/RLS | Dùng runtime role |
| “Query H2 nhanh nghĩa PG sẽ nhanh” | Planner, index, network, data size khác | Benchmark/EXPLAIN trên PG |
| “`@Transactional` trong test rollback mọi thay đổi” | Code có thể tự mở connection/commit | Cô lập DB và kiểm tra hậu điều kiện |
| “Không có Docker thì có thể bỏ test target” | Không còn bằng chứng tương thích | Dùng DB test riêng hoặc báo gap rõ |
| “Pass trên DB mục tiêu là giống production tuyệt đối” | Cấu hình, tải, network có thể khác | Staging/performance/resilience riêng |

## 20. Tình huống tự kiểm tra

**Tình huống A.** Repository dùng PostgreSQL `ON CONFLICT DO UPDATE`, nhưng test dùng H2 với câu `MERGE` khác cú pháp. Test xanh có chứng minh câu production đúng không?

**Đáp án:** Không. Hai câu SQL khác nhau và có thể khác semantics đồng thời. Phải kiểm tra đúng câu PostgreSQL với pgJDBC.

**Tình huống B.** H2 `MODE=PostgreSQL` chạy qua migration và mọi CRUD test. Có thể bỏ toàn bộ PostgreSQL integration test không?

**Đáp án:** Không. Mode đó không mô phỏng đầy đủ driver, MVCC, locking, isolation, extensions, optimizer và transaction behavior của PostgreSQL.

**Tình huống C.** Test chèn dữ liệu sai foreign key nhưng vẫn thành công trên SQLite. Có chắc schema không có FK không?

**Đáp án:** Chưa. Cần kiểm tra cấu hình `PRAGMA foreign_keys` của connection và engine/version. Không kết luận chỉ từ DDL.

**Tình huống D.** H2 test tiếp tục `SELECT` sau một câu `INSERT` trùng khóa, PostgreSQL báo `25P02`. Test nên sửa theo DB nào?

**Đáp án:** Sửa transaction handling phù hợp PostgreSQL là DB mục tiêu; rollback toàn phần hoặc savepoint tùy nghiệp vụ. Không ép production chạy theo hành vi H2.

**Tình huống E.** Một test SQL chạy xanh trên H2 nhưng production sai thứ tự kết quả vì collation. Cần bổ sung gì?

**Đáp án:** Test sorting, Unicode và case/diacritics trên DB mục tiêu với collation/session thực tế; câu SQL cần `ORDER BY` rõ ràng và tie-breaker nếu cần.

**Tình huống F.** Ứng dụng dùng `getGeneratedKeys()` sau batch insert. H2 trả đủ keys theo thứ tự, driver mục tiêu có thể không làm vậy. Có nên dựa vào hành vi H2 không?

**Đáp án:** Không. Phải test driver/DBMS mục tiêu và chọn cách ánh xạ ID bền vững khi thứ tự không được cam kết.

**Tình huống G.** Có test rollback sau exception, nhưng chỉ assert exception được ném. Vậy đủ chưa?

**Đáp án:** Chưa. Cần kiểm tra bằng connection khác rằng thay đổi trước lỗi không tồn tại hoặc trạng thái nguồn giữ nguyên như mong đợi.

**Tình huống H.** CI chạy tất cả unit/H2 test nhưng PostgreSQL container không khởi động được. Có thể hiển thị “JDBC integration PASS” không?

**Đáp án:** Không. Cần đánh dấu nhóm PostgreSQL là failed/skipped theo chính sách và nêu rõ tính tương thích với target DBMS chưa được xác minh.

**Tình huống I.** Sản phẩm chạy PostgreSQL 16 có extension và RLS, CI dùng PostgreSQL mới hơn với superuser. Mức độ tin cậy của test thế nào?

**Đáp án:** Có giá trị nhưng chưa sát mục tiêu: version, extension, runtime role và policy có thể khác. Cần test cùng major/version phù hợp, migration/extensions và role giống production.

**Tình huống J.** Một DB nhúng chạy rất nhanh với một triệu hàng, có thể dùng kết quả để đặt fetch size/connection pool cho PostgreSQL không?

**Đáp án:** Không trực tiếp. Server DB có network, planner, cursor/buffering và giới hạn connection riêng. Cần benchmark môi trường đại diện.

**Tình huống K.** Test tạo bảng đúng, nhưng migration từ schema cũ lên schema mới làm mất dữ liệu production. Cần kiểu test nào?

**Đáp án:** Migration-upgrade test với fixture ở schema/version cũ có dữ liệu, chạy chính migration và xác minh dữ liệu/ràng buộc sau nâng cấp trên DBMS mục tiêu.

**Tình huống L.** Một service chỉ dùng `PreparedStatement` với SQL portable. Có phải mọi test đều bắt buộc chạy trên target DB cho mỗi commit?

**Đáp án:** Không nhất thiết mỗi test. Có thể dùng unit và embedded để phản hồi nhanh, nhưng cần một nhóm contract/integration trên DBMS mục tiêu để xác nhận những đặc tính phụ thuộc engine/driver; phạm vi và lịch chạy dựa trên rủi ro.

## Ghi nhớ

- **Cơ sở dữ liệu nhúng giúp phản hồi nhanh, không phải bản sao trung thực của mọi DBMS mục tiêu.** JDBC API chung không xóa khác biệt giữa driver, dialect, schema, transaction và optimizer.
- **Kiểm thử theo tầng:** unit cho logic, embedded cho smoke/CRUD portable, target DB integration cho SQL/driver/migration/constraint/transaction và staging cho tải, network, security.
- **H2 `MODE=PostgreSQL` không thay thế PostgreSQL.** Những tính năng đặc thù và xung đột đồng thời phải kiểm chứng trên DBMS thực.
- **Contract test phải kiểm tra hậu điều kiện**, ví dụ sau một lỗi `UNIQUE` và `rollback()`, connection khác phải không thấy hàng đã chèn.
- **Kiểm thử trên đúng phiên bản driver/DBMS và cùng migration, charset, timezone, role và isolation quan trọng.** Không tự tạo một schema khác rồi coi test đã chứng minh production.
- **Đưa dữ liệu biên và trường hợp xấu vào fixture:** NULL, Unicode, precision/scale, generated keys, batch error, deadlock, serialization failure, mất kết nối và kết quả commit chưa rõ.
- **Chỉ tuyên bố đã kiểm tra những gì thực sự chạy.** Nếu nhóm test trên DBMS mục tiêu bị skip hoặc chưa có môi trường, ghi rõ khoảng trống thay vì đánh dấu tương thích đã được xác minh.
