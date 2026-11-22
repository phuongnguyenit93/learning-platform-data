# SAVEPOINT và hủy bỏ một phần công việc

## 1. SAVEPOINT giải quyết vấn đề gì trong vòng đời giao dịch?

Một giao dịch cơ sở dữ liệu (database transaction) thường chứa nhiều thao tác phải được xem xét như một đơn vị. Khi có lỗi, cách đơn giản nhất là hủy toàn bộ bằng `ROLLBACK`. Nhưng không phải mọi bước trong một quy trình đều quan trọng như nhau: có bước bắt buộc phải thành công, trong khi một bước phụ có thể bỏ qua mà kết quả cuối vẫn đúng với yêu cầu nghiệp vụ.

**SAVEPOINT** là một điểm đánh dấu bên trong transaction. Sau khi tạo điểm đánh dấu, ứng dụng có thể thử thực hiện thêm các thao tác. Nếu nhóm thao tác đó gặp lỗi hoặc không đạt điều kiện mong muốn, câu lệnh **`ROLLBACK TO SAVEPOINT`** hoàn tác những thay đổi trong database được thực hiện sau điểm đánh dấu, đồng thời giữ lại các thay đổi trước đó để transaction tiếp tục.

Ví dụ, một quy trình nhập dữ liệu có ba phần:

1. Tạo hồ sơ nhập liệu, **bắt buộc**.
2. Thêm nhãn phân loại bổ sung, **có thể bỏ qua nếu nhãn trùng**.
3. Ghi các dòng dữ liệu cốt lõi, **bắt buộc**.

Nếu phần thêm nhãn thất bại, ứng dụng có thể quay về SAVEPOINT đặt trước phần 2, bỏ nhãn và tiếp tục phần 3. Sau đó, transaction ngoài vẫn phải **`COMMIT`** thì hồ sơ và các dòng cốt lõi mới được xác nhận.

~~~text
BEGIN
  |
  +-- [A] Tạo hồ sơ bắt buộc
  |
  +-- SAVEPOINT optional_tags
  |      |
  |      +-- [B1] Thêm nhãn đầu tiên
  |      |
  |      +-- [B2] Thêm nhãn thứ hai -> gặp lỗi
  |      |
  |      +-- ROLLBACK TO optional_tags
  |             (B1 và B2 đều bị hoàn tác)
  |
  +-- [C] Ghi dòng dữ liệu bắt buộc
  |
  +-- COMMIT
        (A và C được xác nhận; B không có trong kết quả)
~~~

SAVEPOINT tạo khả năng **rollback một phần trong cùng transaction**, không biến phần việc phía trước thành một transaction đã commit riêng.

### 1.1. Các ranh giới cần phân biệt

| Thao tác | Phạm vi tác động | Có làm dữ liệu bền vững không? |
|---|---|---|
| `BEGIN` / bắt đầu transaction | Tạo phạm vi giao dịch ngoài | Không |
| `SAVEPOINT tên` | Đánh dấu vị trí trong transaction hiện tại | Không |
| `ROLLBACK TO SAVEPOINT tên` | Hoàn tác thay đổi sau điểm đánh dấu đó | Không |
| `RELEASE SAVEPOINT tên` | Bỏ điểm đánh dấu, giữ nguyên thay đổi đã thực hiện | Không |
| `COMMIT` | Xác nhận toàn bộ thay đổi còn lại trong transaction | Có, theo bảo đảm durability của DB |
| `ROLLBACK` | Hủy toàn bộ thay đổi chưa commit của transaction | Không; kết thúc transaction |

Điểm phân biệt quan trọng nhất: **`RELEASE SAVEPOINT` không phải `COMMIT`**. Nếu đã release một SAVEPOINT rồi transaction ngoài bị rollback, mọi thay đổi của transaction ngoài vẫn bị hủy.

### 1.2. Liên hệ với ACID

- **Atomicity:** SAVEPOINT cho phép lựa chọn bỏ một phần thao tác *khi transaction còn đang chạy*. Đối với thế giới bên ngoài, transaction chưa commit vẫn được nhìn nhận theo cơ chế visibility/isolation của database; không có một phần kết quả đã commit độc lập.
- **Consistency:** bỏ một bước tùy chọn chỉ hợp lệ nếu bất biến nghiệp vụ vẫn đúng. Nếu bước bị lỗi vốn là bắt buộc, phải rollback toàn bộ.
- **Isolation:** transaction vẫn dùng isolation level của transaction ngoài; SAVEPOINT không tự tăng isolation, ngăn lost update hay giải quyết write skew.
- **Durability:** chỉ `COMMIT` thành công mới xác nhận bền vững phần thay đổi còn lại. SAVEPOINT và RELEASE không bảo đảm durability.

## 2. Vòng đời của một SAVEPOINT

Trong những hệ quản trị hỗ trợ cú pháp phổ biến, một vòng đời cơ bản gồm:

~~~sql
BEGIN;

-- Bước bắt buộc A
UPDATE accounts
SET note = 'Đã xác minh'
WHERE id = 10;

SAVEPOINT before_optional_step;

-- Bước thử nghiệm B
INSERT INTO account_tags (account_id, tag)
VALUES (10, 'preferred');

-- Nếu B hợp lệ: có thể RELEASE SAVEPOINT.
-- Nếu B thất bại: ROLLBACK TO SAVEPOINT.

-- Các bước tiếp theo C
UPDATE accounts
SET updated_at = CURRENT_TIMESTAMP
WHERE id = 10;

COMMIT;
~~~

Đoạn trên là khung điều khiển dòng thực thi: chương trình chọn một trong hai nhánh thành công hoặc thất bại; không chạy cả `RELEASE` lẫn `ROLLBACK TO` theo cách tùy tiện.

### 2.1. Tạo điểm đánh dấu: SAVEPOINT

~~~sql
SAVEPOINT before_optional_step;
~~~

Database ghi nhận trạng thái cần thiết để sau này có thể quay về vị trí đó trong transaction. Tên `before_optional_step` là một tên định danh, không phải bảng hoặc đối tượng dữ liệu được lưu vĩnh viễn.

SAVEPOINT tồn tại trong **transaction và session/connection sở hữu nó**. Connection khác không thể rollback đến SAVEPOINT của connection này. Sau `COMMIT` hoặc `ROLLBACK` toàn bộ, các SAVEPOINT của transaction không còn hiệu lực.

Nên chọn tên rõ nghĩa theo vai trò của nhánh, chẳng hạn `before_optional_metadata`, `before_item_17` hoặc `before_reprice_attempt`. Nếu tên là nội dung do người dùng nhập, không nối trực tiếp nó vào SQL: tên SAVEPOINT là identifier, không phải chỗ phù hợp để bind tham số giá trị; hãy dùng tên cố định hoặc đặt tên an toàn theo quy tắc của driver/database.

### 2.2. Quay lại: ROLLBACK TO SAVEPOINT

~~~sql
ROLLBACK TO SAVEPOINT before_optional_step;
~~~

Câu lệnh hoàn tác các thay đổi được thực hiện sau điểm đánh dấu trong phạm vi transaction và đưa việc thực thi trở lại vị trí đó. Những bước **trước SAVEPOINT** vẫn là thay đổi chưa commit của transaction ngoài.

Ví dụ:

~~~text
BEGIN
UPDATE A             -> A đã thay đổi trong transaction
SAVEPOINT s1
UPDATE B             -> B đã thay đổi trong transaction
ROLLBACK TO s1       -> B trở về trạng thái trước UPDATE B
UPDATE C             -> C đã thay đổi trong transaction
COMMIT               -> A và C được commit
~~~

Trong PostgreSQL, sau `ROLLBACK TO s1`, chính SAVEPOINT `s1` vẫn tồn tại, nên có thể tiếp tục thử nhánh khác hoặc `RELEASE SAVEPOINT s1`. SAVEPOINT được tạo *sau* `s1` bị loại bỏ khi rollback về `s1`.

Không nên nhầm `ROLLBACK TO SAVEPOINT` với `ROLLBACK` đứng một mình: `ROLLBACK` hủy cả A, B và C (nếu chúng chưa commit) và kết thúc transaction.

### 2.3. Bỏ điểm đánh dấu: RELEASE SAVEPOINT

~~~sql
RELEASE SAVEPOINT before_optional_step;
~~~

Khi một nhánh đã hoàn thành và không còn cần khả năng quay lại điểm đó, ứng dụng có thể release SAVEPOINT.

- Các thay đổi sau SAVEPOINT vẫn **nằm trong transaction chưa commit**.
- RELEASE chỉ bỏ điểm đánh dấu; không công bố một phần kết quả như một commit độc lập.
- Nếu transaction ngoài sau đó `ROLLBACK`, các thay đổi được giữ sau RELEASE cũng bị hủy.
- Cú pháp và mức hỗ trợ `RELEASE` khác nhau tùy database; chẳng hạn SQL Server không có câu lệnh `RELEASE SAVEPOINT` tương đương.

Thông thường, sau khi `ROLLBACK TO` trong PostgreSQL, ứng dụng có thể `RELEASE SAVEPOINT` để dọn điểm đánh dấu, rồi tiếp tục transaction ngoài.

## 3. Ví dụ hoàn chỉnh: bỏ qua một nhánh không bắt buộc

Xét hệ thống tiếp nhận đơn nhập liệu. Hồ sơ và dòng nhập là phần cốt lõi. Nhãn gợi ý chỉ nhằm giúp tìm kiếm, nên nếu thao tác thêm nhãn có lỗi về trùng dữ liệu đã biết, transaction có thể giữ phần cốt lõi và bỏ toàn bộ nhóm nhãn.

Các bảng minh họa dùng cú pháp **PostgreSQL**:

~~~sql
CREATE TABLE import_jobs (
    id BIGINT PRIMARY KEY,
    source_name TEXT NOT NULL
);

CREATE TABLE import_lines (
    job_id BIGINT NOT NULL REFERENCES import_jobs(id),
    line_no INTEGER NOT NULL,
    raw_value TEXT NOT NULL,
    PRIMARY KEY (job_id, line_no)
);

CREATE TABLE import_tags (
    job_id BIGINT NOT NULL REFERENCES import_jobs(id),
    tag TEXT NOT NULL,
    PRIMARY KEY (job_id, tag)
);
~~~

Giả sử dữ liệu ban đầu chưa có `job_id = 4301`. Một lần chạy theo các bước sau:

~~~sql
BEGIN;

-- Bước A: bắt buộc.
INSERT INTO import_jobs (id, source_name)
VALUES (4301, 'orders-2026-11.csv');

-- Đánh dấu trước toàn bộ nhóm tùy chọn.
SAVEPOINT before_optional_tags;

-- Bước B1: thành công tạm thời.
INSERT INTO import_tags (job_id, tag)
VALUES (4301, 'reviewed');

-- Bước B2: cố ý thử nhãn trùng, PostgreSQL báo 23505.
INSERT INTO import_tags (job_id, tag)
VALUES (4301, 'reviewed');

-- Khi B2 báo lỗi, client phải xử lý lỗi và thực hiện:
ROLLBACK TO SAVEPOINT before_optional_tags;
RELEASE SAVEPOINT before_optional_tags;

-- Bước C: vẫn tiếp tục được vì đã phục hồi transaction.
INSERT INTO import_lines (job_id, line_no, raw_value)
VALUES (4301, 1, 'item-A');

COMMIT;
~~~

**Lưu ý khi chạy ví dụ:** câu `INSERT` thứ hai cố tình gây lỗi unique. Nếu client được cấu hình dừng thực thi ở lỗi đầu tiên (ví dụ chế độ stop-on-error của script), các câu sau sẽ không tự chạy. Trong ứng dụng thật, nhánh `ROLLBACK TO` phải được gọi trong trình xử lý ngoại lệ, sau khi kiểm tra đây là lỗi nhãn trùng có thể bỏ qua.

Kết quả mong đợi sau commit:

| Bảng | Dữ liệu thuộc job 4301 | Vì sao? |
|---|---|---|
| `import_jobs` | Có hồ sơ 4301 | Chèn trước SAVEPOINT |
| `import_tags` | Không có nhãn mới | Nhóm B1/B2 đã rollback về điểm đánh dấu |
| `import_lines` | Có dòng `item-A` | Chèn sau khi phục hồi rồi commit |

Nếu gặp lỗi ở bước C mà không xử lý được, ứng dụng phải rollback toàn bộ; lúc ấy hồ sơ 4301 cũng sẽ biến mất. SAVEPOINT không mặc định “bảo vệ” A trước rollback toàn bộ.

### 3.1. Tại sao không chỉ bỏ qua lỗi rồi chạy tiếp?

Một số engine có cơ chế đánh dấu transaction là **failed/aborted** khi câu lệnh gặp lỗi. Trong **PostgreSQL**, sau lỗi SQL trong transaction thông thường, các câu lệnh tiếp theo thường nhận lỗi SQLSTATE `25P02` (*current transaction is aborted*) cho tới khi ứng dụng rollback. Nếu đã đặt SAVEPOINT trước câu lệnh lỗi, `ROLLBACK TO SAVEPOINT` cho phép phục hồi phần transaction có thể tiếp tục.

Ở những engine khác, một lỗi constraint có thể chỉ tự rollback câu lệnh lỗi, nhưng đó không đủ để bỏ **toàn bộ nhóm nhiều câu lệnh** đã chạy trước lỗi. SAVEPOINT tạo ranh giới rõ ràng cho nhóm B1/B2.

### 3.2. Thế nào là một bước “có thể bỏ qua”?

Cần quyết định theo nghiệp vụ, không theo việc “database có cho rollback một phần hay không”.

Phù hợp: nhãn gợi ý, dữ liệu enrichment không bắt buộc, một bản ghi nhập không hợp lệ trong chế độ *best effort* có báo cáo đầy đủ.

Không phù hợp: trừ tồn kho đã chấp nhận đơn, cập nhật sổ cái bắt buộc, bản ghi audit bắt buộc theo chính sách, cập nhật phải đi cùng một chuyển tiền, hoặc bước mà thiếu nó làm dữ liệu cuối vi phạm ràng buộc nghiệp vụ.

Nếu thất bại ở phần tùy chọn làm thay đổi giá tiền, trạng thái hoàn tất hay tính hợp lệ của phần cốt lõi, cần tính lại quyết định hoặc rollback toàn bộ thay vì đơn giản bỏ nhánh.

## 4. Nhiều SAVEPOINT và thứ tự lồng nhau

Một transaction có thể có nhiều SAVEPOINT.

~~~sql
BEGIN;

INSERT INTO demo_events(id, event_name) VALUES (1, 'base');

SAVEPOINT s1;
INSERT INTO demo_events(id, event_name) VALUES (2, 'branch A');

SAVEPOINT s2;
INSERT INTO demo_events(id, event_name) VALUES (3, 'branch B');

ROLLBACK TO SAVEPOINT s2;
-- Hủy insert id=3; id=1 và id=2 vẫn trong transaction.

RELEASE SAVEPOINT s2;

ROLLBACK TO SAVEPOINT s1;
-- Hủy thêm insert id=2; id=1 vẫn trong transaction.

RELEASE SAVEPOINT s1;
COMMIT;
-- Chỉ id=1 được commit trong ví dụ này.
~~~

Phân tích trạng thái:

| Mốc | Các thay đổi còn lại trong transaction |
|---|---|
| Sau A và B | `id=1, id=2, id=3` |
| Sau `ROLLBACK TO s2` | `id=1, id=2` |
| Sau `ROLLBACK TO s1` | `id=1` |
| Sau `COMMIT` | `id=1` trở thành dữ liệu đã commit |

Nếu rollback thẳng về `s1` trong lúc `s2` còn tồn tại, các SAVEPOINT được tạo sau `s1` sẽ không còn dùng được. Trong PostgreSQL, có thể đặt lại cùng một tên SAVEPOINT và tên mới tạm thời che tên cũ; tuy vậy, dùng **tên khác nhau** giúp tránh nhập nhằng. Quy tắc tên trùng và release có thể khác giữa hệ quản trị.

### 4.1. SAVEPOINT khác transaction lồng nhau thực sự

Hãy hình dung:

~~~text
OUTER TRANSACTION
  |
  +-- bắt đầu
  +-- thay đổi A
  +-- SAVEPOINT S
  |      +-- thay đổi B
  |      +-- RELEASE S
  +-- thay đổi C
  +-- ROLLBACK toàn bộ
         => A, B, C đều bị hủy
~~~

Dù B được đặt trong một nhánh “nested”, nó không có **commit độc lập**. SAVEPOINT trong cùng transaction khác với mở một transaction vật lý riêng trên một connection khác.

Điều này rất quan trọng khi chọn cơ chế trong Spring Framework: `PROPAGATION_NESTED` (khi transaction manager hỗ trợ) thường sử dụng savepoint trong cùng transaction vật lý, còn `PROPAGATION_REQUIRES_NEW` dùng một transaction vật lý riêng với khả năng commit/rollback độc lập.

## 5. So sánh hành vi của các hệ quản trị phổ biến

### 5.1. PostgreSQL

Cú pháp chính:

~~~sql
BEGIN;
SAVEPOINT s1;
-- thao tác
ROLLBACK TO SAVEPOINT s1;
RELEASE SAVEPOINT s1;
COMMIT;
~~~

Đặc điểm cần nhớ:

- Có thể dùng SAVEPOINT để phục hồi sau lỗi SQL thông thường bên trong transaction.
- `ROLLBACK TO s1` giữ lại `s1`, đồng thời loại các savepoint được tạo sau nó.
- `RELEASE s1` bỏ savepoint nhưng không commit.
- Một số lỗi nghiêm trọng như đứt kết nối hoặc lỗi đã làm transaction không thể phục hồi theo cách thông thường cần xử lý ở phạm vi lớn hơn.
- Việc rollback một phần không hoàn tác mọi loại side effect ngoài dữ liệu giao dịch. Ví dụ, giá trị đã lấy từ sequence bằng `nextval()` không bị trả lại khi rollback về savepoint.

### 5.2. MySQL với InnoDB

~~~sql
START TRANSACTION;
SAVEPOINT s1;
-- thao tác với bảng InnoDB
ROLLBACK TO SAVEPOINT s1;
RELEASE SAVEPOINT s1;
COMMIT;
~~~

Các điểm cần lưu ý:

- SAVEPOINT có hiệu lực khi đang thực hiện transaction; dùng storage engine có hỗ trợ giao dịch, chẳng hạn InnoDB.
- Những lệnh DDL như `CREATE TABLE`, `ALTER TABLE` có thể gây **implicit commit** trong MySQL. Đừng đặt DDL như một bước có thể rollback một phần nếu chưa kiểm tra chính xác tác dụng của lệnh đó.
- Với deadlock InnoDB, cơ sở dữ liệu có thể **rollback toàn bộ transaction**. Khi đó SAVEPOINT không còn là điểm phục hồi; ứng dụng cần chạy lại transaction từ đầu nếu lỗi có thể retry.
- Với lock wait timeout, phạm vi rollback mặc định và cấu hình như `innodb_rollback_on_timeout` ảnh hưởng việc còn có thể tiếp tục transaction hay không.
- Các bảng không hỗ trợ transaction không được bảo vệ bằng cách bọc chúng trong SAVEPOINT.

Vì vậy, không thể suy luận rằng “mọi lỗi khi xử lý một hàng trong InnoDB đều khôi phục được bằng `ROLLBACK TO`”.

### 5.3. SQLite

SQLite hỗ trợ `SAVEPOINT`, `ROLLBACK TO` và `RELEASE`:

~~~sql
BEGIN;
SAVEPOINT s1;
INSERT INTO example(id) VALUES (1);
ROLLBACK TO s1;
RELEASE s1;
COMMIT;
~~~

Một điểm khác đáng chú ý: nếu chưa có `BEGIN`, SAVEPOINT ngoài cùng có thể đóng vai trò như ranh giới giao dịch; `RELEASE` savepoint ngoài cùng khi đó có thể kết thúc transaction. Vì thế, nhận định “RELEASE không commit” áp dụng rõ nhất cho **SAVEPOINT bên trong một transaction ngoài đã mở**, là bối cảnh bài học này.

SQLite cũng có những quy tắc riêng về mức khóa và chế độ journal (WAL/rollback journal), nên việc thêm SAVEPOINT không làm mọi thao tác ghi trở nên song song.

### 5.4. SQL Server

SQL Server sử dụng tên lệnh khác:

~~~sql
BEGIN TRANSACTION;

SAVE TRANSACTION before_optional;

-- thao tác

ROLLBACK TRANSACTION before_optional;
-- Tiếp tục transaction ngoài nếu trạng thái giao dịch còn cho phép.

COMMIT TRANSACTION;
~~~

Không có `RELEASE SAVEPOINT` tương ứng. Sau một lỗi, có thể kiểm tra `XACT_STATE()`:

- `1`: transaction đang hoạt động và có thể commit; có thể rollback về savepoint theo điều kiện của engine.
- `-1`: transaction ở trạng thái *uncommittable*; không thể rollback về savepoint để tiếp tục ghi, mà cần rollback toàn bộ.
- `0`: không có transaction hoạt động.

Chẳng hạn một transaction ở trạng thái không thể commit, hoặc một số trường hợp distributed transaction, không thể dùng savepoint để tiếp tục như ở ví dụ PostgreSQL.

### 5.5. Tóm tắt khác biệt

| Hệ quản trị | Tạo SAVEPOINT | Rollback một phần | Giải phóng SAVEPOINT | Lưu ý chính |
|---|---|---|---|---|
| PostgreSQL | `SAVEPOINT s` | `ROLLBACK TO s` | `RELEASE s` | Có thể phục hồi transaction bị lỗi SQL thông thường bằng rollback về savepoint |
| MySQL/InnoDB | `SAVEPOINT s` | `ROLLBACK TO s` | `RELEASE s` | DDL implicit commit, deadlock có thể rollback cả transaction |
| SQLite | `SAVEPOINT s` | `ROLLBACK TO s` | `RELEASE s` | SAVEPOINT ngoài cùng có thể là ranh giới transaction |
| SQL Server | `SAVE TRANSACTION s` | `ROLLBACK TRANSACTION s` | Không có `RELEASE` tương đương | Phải kiểm tra trạng thái transaction sau lỗi |

Cú pháp và hành vi ở bảng này giúp định hướng; khi triển khai cần dựa vào phiên bản database, driver, isolation level và transaction manager cụ thể.

## 6. Dùng SAVEPOINT trong Java với JDBC

JDBC cung cấp API để làm việc với SAVEPOINT mà không cần tự tạo câu lệnh SQL cho các thao tác quản lý điểm đánh dấu:

- `Connection.setSavepoint()` hoặc `setSavepoint("name")`: tạo SAVEPOINT.
- `Connection.rollback(savepoint)`: rollback đến SAVEPOINT.
- `Connection.releaseSavepoint(savepoint)`: giải phóng SAVEPOINT, nếu driver/database hỗ trợ.
- `Connection.commit()`: commit transaction ngoài.
- `Connection.rollback()`: rollback toàn bộ.

### 6.1. Ví dụ xử lý danh sách có thể bỏ qua nhãn trùng

Giả sử bảng `import_tags` đã được tạo ở mục 3. Trong ví dụ dưới, việc bỏ qua **lỗi unique của nhãn** là yêu cầu nghiệp vụ được xác định trước; các lỗi SQL khác phải làm toàn bộ transaction thất bại.

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Savepoint;
import java.util.List;

public final class SavepointExample {

    public static void importJob(
            String jdbcUrl,
            String username,
            String password,
            long jobId,
            List<String> tags
    ) throws SQLException {
        try (Connection connection =
                     DriverManager.getConnection(jdbcUrl, username, password)) {

            connection.setAutoCommit(false);

            try {
                try (PreparedStatement header = connection.prepareStatement(
                        "INSERT INTO import_jobs(id, source_name) VALUES (?, ?)")) {
                    header.setLong(1, jobId);
                    header.setString(2, "orders-import.csv");
                    header.executeUpdate();
                }

                for (String tag : tags) {
                    Savepoint beforeTag = connection.setSavepoint();

                    try (PreparedStatement insert = connection.prepareStatement(
                            "INSERT INTO import_tags(job_id, tag) VALUES (?, ?)")) {
                        insert.setLong(1, jobId);
                        insert.setString(2, tag);
                        insert.executeUpdate();

                        connection.releaseSavepoint(beforeTag);
                    } catch (SQLException error) {
                        // PostgreSQL: 23505 = unique_violation.
                        // Phục hồi phần transaction đã bắt đầu trước tag.
                        connection.rollback(beforeTag);
                        connection.releaseSavepoint(beforeTag);

                        if (!"23505".equals(error.getSQLState())) {
                            throw error;
                        }
                        // Nhãn trùng là bước tùy chọn, được phép bỏ qua.
                    }
                }

                try (PreparedStatement line = connection.prepareStatement(
                        "INSERT INTO import_lines(job_id, line_no, raw_value) " +
                        "VALUES (?, ?, ?)")) {
                    line.setLong(1, jobId);
                    line.setInt(2, 1);
                    line.setString(3, "item-A");
                    line.executeUpdate();
                }

                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
~~~

Trong ví dụ này:

1. `setAutoCommit(false)` bảo đảm các câu lệnh không tự commit sau từng bước.
2. Hồ sơ được tạo trước các SAVEPOINT.
3. Mỗi tag được xử lý trong một vùng có thể rollback riêng.
4. Chỉ SQLSTATE `23505` mới được chấp nhận để bỏ qua tag; những lỗi khác được ném lại, rồi rollback toàn bộ.
5. Dòng dữ liệu bắt buộc được chèn, sau cùng mới `commit()`.

**Giới hạn cần hiểu:** đoạn mã hướng tới PostgreSQL và driver JDBC có hỗ trợ release savepoint. Không nên áp dụng logic phân loại lỗi `23505` cho engine khác mà không điều chỉnh SQLSTATE/mã lỗi và khả năng phục hồi transaction tương ứng. Đối với hệ thống thực, còn cần ghi nhận những tag đã bị bỏ qua và lý do vào kết quả xử lý/metric.

### 6.2. Vì sao phải quản lý autocommit?

Khi `autoCommit = true`, JDBC thường commit mỗi statement thành công như một transaction riêng. SAVEPOINT cần nằm trong ranh giới transaction có thể tiếp tục; trên nhiều driver, gọi `setSavepoint()` khi autocommit đang bật sẽ báo lỗi.

~~~java
connection.setAutoCommit(false);  // Bắt đầu quản lý transaction bằng ứng dụng.
Savepoint marker = connection.setSavepoint();
// ...
connection.rollback(marker);       // Rollback một phần.
connection.commit();               // Kết thúc transaction ngoài.
~~~

Nếu lấy connection từ pool, phải tuân thủ quy ước quản lý connection của framework và pool. Khi Spring đang quản lý transaction, không nên tự ý bật/tắt `autoCommit` hoặc commit trực tiếp trên connection do Spring cấp.

### 6.3. Xử lý lỗi rollback đến SAVEPOINT

`rollback(savepoint)` có thể thất bại nếu connection đã mất, SAVEPOINT không còn hiệu lực, hoặc toàn bộ transaction đã bị database rollback. Vì vậy không thể mặc định lỗi phát sinh trong mọi trường hợp đều phục hồi được.

Mẫu quản lý hợp lý:

~~~text
try:
    bắt đầu transaction
    làm công việc bắt buộc

    savepoint = tạo SAVEPOINT
    try:
        làm việc tùy chọn
        release savepoint (nếu hỗ trợ)
    catch lỗi:
        nếu transaction còn có thể phục hồi:
            rollback đến savepoint
            phân loại lỗi: cho phép bỏ qua hay phải fail?
        nếu không còn phục hồi được:
            rollback toàn bộ / đóng connection / retry toàn bộ

    làm các bước còn lại
    commit
catch lỗi chưa xử lý:
    rollback toàn bộ nếu còn có thể
    báo lỗi và giữ nguyên nguyên nhân
~~~

Lưu ý: nếu nhánh tùy chọn thực hiện **nhiều statement**, nên đặt một SAVEPOINT trước toàn bộ nhánh; đặt điểm đánh dấu quá muộn có thể để lọt một phần thay đổi không mong muốn.

## 7. SAVEPOINT trong Spring: NESTED và REQUIRES_NEW

Spring có nhiều cách điều phối transaction. Sự khác nhau giữa các propagation mode quyết định liệu có dùng SAVEPOINT, hay tạo transaction vật lý riêng.

### 7.1. PROPAGATION_NESTED

Với cấu hình phù hợp, `Propagation.NESTED` đặt một SAVEPOINT trong transaction ngoài. Nếu nhánh nested rollback, transaction ngoài vẫn có thể tiếp tục; nếu nhánh nested thành công, dữ liệu của nhánh vẫn phụ thuộc vào commit của transaction ngoài.

~~~text
@Transactional (outer)
  |
  +-- lưu bản ghi bắt buộc
  |
  +-- NESTED (savepoint trên cùng transaction)
  |      +-- lưu dữ liệu tùy chọn
  |      +-- thất bại => rollback về savepoint
  |
  +-- xử lý thêm bước bắt buộc
  |
  +-- COMMIT ngoài
~~~

Với JDBC, `DataSourceTransactionManager` là một lựa chọn có hỗ trợ nested transactions thông qua JDBC Savepoint khi driver cung cấp khả năng đó. `JpaTransactionManager` cần thận trọng: các savepoint ở tầng JDBC không tự khôi phục trạng thái của JPA `EntityManager`/persistence context. Không nên cho rằng mọi thao tác JPA sẽ có ngữ nghĩa nested rollback an toàn chỉ vì đã cấu hình `NESTED`.

### 7.2. Ví dụ điều phối bằng TransactionTemplate

Để biểu đạt rõ transaction ngoài và transaction nested:

~~~java
import org.springframework.dao.DuplicateKeyException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public class ImportService {
    private final TransactionTemplate outer;
    private final TransactionTemplate nested;
    private final ImportRepository repository;

    public ImportService(
            PlatformTransactionManager transactionManager,
            ImportRepository repository
    ) {
        this.repository = repository;
        this.outer = new TransactionTemplate(transactionManager);
        this.nested = new TransactionTemplate(transactionManager);
        this.nested.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_NESTED);
    }

    public void process(long jobId) {
        outer.execute(status -> {
            repository.saveRequiredHeader(jobId);

            try {
                nested.execute(inner -> {
                    repository.saveOptionalTags(jobId);
                    return null;
                });
            } catch (DuplicateKeyException e) {
                // Nhánh nested đã rollback về savepoint của nó.
                // Có thể bỏ qua nhãn trùng theo quy tắc nghiệp vụ.
            }

            repository.saveRequiredLines(jobId);
            return null;  // Outer TransactionTemplate sẽ commit nếu thành công.
        });
    }
}
~~~

Ví dụ này giả định `ImportRepository` dùng cùng nguồn JDBC và transaction manager hỗ trợ `PROPAGATION_NESTED`. Các phương thức repository và quy tắc xử lý lỗi phải được xây dựng nhất quán; bắt riêng `DuplicateKeyException` chỉ đúng khi mọi lỗi trùng ở nhánh đó đều được phép bỏ qua.

`TransactionTemplate` quản lý ranh giới commit/rollback; ta không cần tự gọi `Connection.commit()`. Nếu `saveRequiredLines` thất bại, outer transaction rollback và phần header đã tạo cũng bị hủy.

### 7.3. Khác với PROPAGATION_REQUIRES_NEW

| Tiêu chí | `NESTED` (khi dùng SAVEPOINT) | `REQUIRES_NEW` |
|---|---|---|
| Transaction vật lý | Dùng chung transaction ngoài | Tạo transaction vật lý riêng |
| Connection | Thường cùng JDBC connection | Thường cần connection riêng khi outer bị suspend |
| Nhánh thành công | Chưa commit độc lập | Có thể commit độc lập |
| Outer rollback sau nhánh | Hoàn tác cả thay đổi của nhánh | Không hoàn tác transaction mới đã commit |
| Khi nhánh lỗi | Có thể rollback về savepoint và tiếp tục outer | Rollback transaction mới; outer có thể tiếp tục theo chính sách xử lý lỗi |
| Điều kiện kỹ thuật | Driver/transaction manager hỗ trợ savepoint | Đủ tài nguyên để mở transaction độc lập |

Ví dụ, nếu muốn log audit “đã bắt đầu yêu cầu” tồn tại **ngay cả khi outer rollback**, SAVEPOINT không đáp ứng mục đích đó; nhưng dùng transaction độc lập cũng phải cân nhắc tính nhất quán và nhu cầu nghiệp vụ.

Ngược lại, nếu một nhánh tùy chọn phải **được commit cùng** phần chính khi cuối cùng thành công, `NESTED`/SAVEPOINT phù hợp hơn một transaction commit riêng.

### 7.4. Lưu ý khi dùng @Transactional

Khi dùng khai báo `@Transactional(propagation = Propagation.NESTED)`:

- Lời gọi phải đi qua cơ chế proxy/interceptor transaction của Spring. Gọi method nội bộ qua `this.nestedMethod()` thường **không đi qua proxy**, nên propagation có thể không được áp dụng.
- Transaction manager phải hỗ trợ savepoint và cấu hình đúng.
- Nếu nhánh nested ném exception nhưng outer bắt lại, cần chắc chắn nhánh nested đã được rollback về SAVEPOINT trước khi outer tiếp tục.
- Nếu method con dùng `REQUIRED` trong cùng transaction và đánh dấu rollback-only, chỉ bắt exception ở outer **không nhất thiết xóa được trạng thái rollback-only**; đến commit có thể xuất hiện `UnexpectedRollbackException`.
- Khi kết hợp JDBC và JPA, phải hiểu trạng thái đối tượng đang giữ trong persistence context; rollback database không tự hoàn nguyên các trường Java đã thay đổi.

Vì thế, không nên xem `try/catch` bên trong một method `@Transactional` là tương đương với SAVEPOINT.

## 8. Những gì SAVEPOINT không thể hoàn tác hoàn toàn

Một phần thay đổi nằm ngoài sự kiểm soát của transaction database, cho dù thao tác xảy ra sau SAVEPOINT.

### 8.1. Side effect bên ngoài cơ sở dữ liệu

Những hành động sau không được rollback bởi database:

- Gửi email, SMS, push notification hoặc gọi HTTP API.
- Ghi file, gửi thông điệp tới hệ thống queue bên ngoài nếu không có cơ chế transaction phối hợp.
- Thu tiền qua cổng thanh toán, gửi sự kiện tới dịch vụ khác.
- Thay đổi trạng thái trong bộ nhớ tiến trình, cập nhật cache ngoài DB không được hoàn tác.

Ví dụ:

~~~text
SAVEPOINT before_optional
INSERT dòng dữ liệu
GỬI EMAIL "Đã nhập thành công"  <-- email đã rời hệ thống
ROLLBACK TO before_optional    <-- chỉ dữ liệu DB được hoàn tác
~~~

Email không biến mất. Để bảo đảm chỉ phát sự kiện sau khi commit, có thể dùng **transactional outbox**: ghi bản ghi sự kiện vào cùng transaction, và một tiến trình khác chỉ phát sau khi sự kiện đã commit, với idempotency ở consumer.

### 8.2. Sequence, identity và các tài nguyên không giao dịch

Ở PostgreSQL, giá trị tạo bằng `nextval()` không được thu hồi khi rollback một phần hoặc rollback toàn bộ. Vì vậy ID được cấp có thể có khoảng trống:

~~~sql
BEGIN;
SAVEPOINT s1;

SELECT nextval('order_id_seq'); -- Ví dụ trả 101.

ROLLBACK TO SAVEPOINT s1;
COMMIT;

-- Lượt cấp ID sau có thể là 102 thay vì 101.
~~~

Với các engine khác, auto-increment cũng thường không bảo đảm dãy số liên tục. Không lấy việc ID bị nhảy số làm dấu hiệu mất dữ liệu hoặc kết luận SAVEPOINT lỗi.

### 8.3. Snapshot và giao dịch đang giữ tài nguyên

`ROLLBACK TO SAVEPOINT` không biến transaction hiện tại thành một transaction mới. Isolation level, thời điểm snapshot trong các chế độ tương ứng và các thay đổi/khóa trước SAVEPOINT vẫn có thể tiếp tục ảnh hưởng đến những lệnh sau.

Các khóa được lấy sau SAVEPOINT có thể được giải phóng khi rollback đến nó tùy engine/loại khóa. Tuy nhiên, không nên mặc định **mọi** loại khóa/tài nguyên, đặc biệt session-level locks hoặc tài nguyên ngoài database, đều tự động trả lại. Ví dụ PostgreSQL có quy tắc riêng với row/table locks, advisory locks và các loại thao tác.

### 8.4. Ràng buộc kiểm tra ở COMMIT

Một số constraint có thể là **deferrable** và được kiểm tra khi transaction commit. Nhánh tùy chọn có vẻ thành công tại thời điểm `RELEASE SAVEPOINT` nhưng toàn bộ transaction sau đó vẫn thất bại tại `COMMIT` do vi phạm constraint được trì hoãn.

Do đó, `RELEASE` không phải chứng nhận mọi invariant đã hợp lệ vĩnh viễn. Ứng dụng vẫn phải coi `COMMIT` là bước có thể thất bại.

## 9. Khi nào nên và không nên dùng SAVEPOINT?

### 9.1. Những trường hợp phù hợp

**Nhập dữ liệu theo kiểu best effort trong một transaction**

Một batch phải tạo hồ sơ cha và xử lý nhiều dòng con, nhưng một số dòng có thể bị bỏ qua theo quy tắc xác định. Đặt SAVEPOINT trước từng dòng hoặc từng nhóm dòng. Nếu một dòng lỗi dữ liệu được phép bỏ qua, rollback về SAVEPOINT rồi tiếp tục; nếu lỗi ảnh hưởng tính toàn vẹn toàn batch, rollback hết.

Lưu ý về thuật ngữ: “best effort” ở đây là **cho phép một số mục không được ghi**, chứ không tự commit từng mục. Nếu cuối cùng outer transaction rollback, toàn bộ những mục đã chấp nhận trong batch vẫn bị hủy.

**Thử một phương án cập nhật và có phương án thay thế**

Ví dụ, hệ thống muốn thêm dữ liệu enrichment tùy chọn. Khi nhánh thử lỗi theo trường hợp đã biết, có thể rollback và thử nhánh dự phòng trong cùng transaction.

**Kiểm thử thao tác phụ bên trong một yêu cầu**

Khi nội dung chính đã được xác định hợp lệ, một thay đổi phụ có thể thất bại mà không làm thay đổi kết quả chính. SAVEPOINT giúp ghi rõ ranh giới rollback và tránh kéo theo các thao tác trước đó.

### 9.2. Những trường hợp không phù hợp

- Cần giữ một phần dữ liệu **đã commit độc lập** trước khi giao dịch chính kết thúc: SAVEPOINT không làm được.
- Cần rollback một tác vụ đã được gửi tới dịch vụ khác: transaction database không điều khiển được.
- Muốn chữa lỗi isolation hoặc race condition: SAVEPOINT không thay cho khóa, điều kiện cập nhật nguyên tử hoặc isolation phù hợp.
- Muốn bảo vệ transaction khỏi mọi loại lỗi: deadlock, mất connection, lỗi hệ thống và trạng thái transaction không thể commit vẫn có thể bắt buộc rollback toàn bộ.
- Dự định ghi hàng triệu SAVEPOINT mà chưa đánh giá chi phí: mô hình khác có thể hiệu quả hơn.

## 10. Chi phí hiệu năng và vận hành

SAVEPOINT có ích nhưng không miễn phí. Mỗi điểm đánh dấu và lần rollback có thể tiêu thụ thông tin quản lý transaction, undo/MVCC metadata, write-ahead logging theo engine, và thêm round trip giữa ứng dụng với database nếu sử dụng nhiều câu lệnh.

### 10.1. Tại sao SAVEPOINT không làm commit nhanh hơn?

Các thay đổi còn hiệu lực trong transaction vẫn chưa commit và vẫn có thể giữ khóa hoặc ảnh hưởng công việc bảo trì phiên bản cho tới khi transaction ngoài kết thúc. Nếu import 100.000 bản ghi trong một transaction với 100.000 SAVEPOINT, cả batch vẫn là một transaction lớn.

Hệ quả có thể là:

- Thời gian transaction dài làm tăng thời gian giữ khóa hoặc version history.
- Các transaction khác chờ lâu hơn ở dữ liệu tranh chấp.
- Log và bộ nhớ quản lý transaction tăng.
- Khi cuối cùng rollback toàn bộ, mọi bản ghi đã xử lý thành công trong batch vẫn bị hủy.
- Số lượng statement `SAVEPOINT / ROLLBACK TO / RELEASE` lớn có thể làm throughput giảm.

### 10.2. Chọn mức phân nhóm phù hợp

| Cách tổ chức | Ưu điểm | Đổi lại |
|---|---|---|
| Một SAVEPOINT trước từng dòng | Xác định chính xác dòng cần bỏ | Nhiều điểm đánh dấu/round trip |
| Một SAVEPOINT trước một nhóm dòng | Ít điểm đánh dấu hơn | Một lỗi có thể làm mất cả nhóm |
| Một transaction cho mỗi batch nhỏ | Giới hạn thời gian giữ tài nguyên | Các batch commit độc lập, không còn atomic toàn bộ |
| Dùng `ON CONFLICT`/`UPSERT` khi thích hợp | Giảm round trip, tránh exception dự kiến | Chỉ thay thế được một số trường hợp trùng dữ liệu rõ nghĩa |
| Kiểm tra trước rồi chèn | Có thể giảm lỗi thường gặp | Kiểm tra trước vẫn có race condition, cần constraint lúc ghi |

Trong PostgreSQL, nếu yêu cầu chỉ là **bỏ qua khóa duy nhất đã tồn tại** cho một câu `INSERT`, cú pháp sau có thể đơn giản hơn một SAVEPOINT cho mỗi lỗi unique:

~~~sql
INSERT INTO import_tags (job_id, tag)
VALUES (4301, 'reviewed')
ON CONFLICT (job_id, tag) DO NOTHING;
~~~

Điều này chỉ giải quyết xung đột được định nghĩa trong câu lệnh, không tương đương với rollback một chuỗi nhiều thay đổi, và không được dùng để nuốt mọi lỗi dữ liệu hoặc lỗi nghiệp vụ.

### 10.3. Các chỉ số nên quan sát

- Số SAVEPOINT được tạo và số lần rollback một phần trên mỗi request/batch.
- Tỉ lệ mục bị bỏ qua theo **lý do nghiệp vụ**.
- Thời gian transaction từ BEGIN đến COMMIT/ROLLBACK.
- Throughput bản ghi thực sự commit, tách khỏi số mục đã thử.
- Thời gian chờ khóa, deadlock, serialization failure và retry.
- Số transaction cuối cùng rollback toàn bộ dù đã xử lý nhiều dòng thành công tạm thời.

Nếu tỉ lệ rollback một phần quá cao, nên xem lại bước validate dữ liệu, phương án xử lý xung đột hoặc ranh giới batch. Không nên che giấu lỗi dữ liệu bằng cách bắt mọi exception rồi tiếp tục.

## 11. Các lỗi triển khai thường gặp

### 11.1. Nhầm RELEASE với COMMIT

~~~sql
BEGIN;
INSERT INTO demo_events(id, event_name) VALUES (100, 'A');
SAVEPOINT s;
INSERT INTO demo_events(id, event_name) VALUES (101, 'B');
RELEASE SAVEPOINT s;
ROLLBACK;
~~~

**Không có A hoặc B được commit.** RELEASE chỉ xóa điểm đánh dấu, không xác nhận B.

### 11.2. Tạo SAVEPOINT sau câu lệnh có thể lỗi

~~~text
INSERT nhãn thứ nhất
INSERT nhãn thứ hai -> lỗi
SAVEPOINT s           <-- đã quá muộn
~~~

Phải đặt SAVEPOINT **trước** nhóm thao tác muốn có khả năng hoàn tác.

### 11.3. Nuốt lỗi chưa xác định

~~~text
try:
    thực hiện nhiều thao tác
catch mọi exception:
    rollback to savepoint
    tiếp tục như thành công
~~~

Đây là sai lầm nguy hiểm. Lỗi mất kết nối, deadlock, phân quyền, dữ liệu thiếu hoặc invariant không được bảo toàn có thể cần rollback toàn bộ. Phải phân loại lỗi theo engine và yêu cầu nghiệp vụ; ngay cả khi rollback một phần thành công, không phải mọi lỗi đều được phép bỏ qua.

### 11.4. Dùng connection khác để rollback về SAVEPOINT

SAVEPOINT chỉ có ý nghĩa trong transaction hiện tại của connection tạo ra nó. Nếu DAO lấy connection khác ngoài transaction context, `ROLLBACK TO` không quay lại được các thay đổi ở connection ban đầu.

### 11.5. Trộn SAVEPOINT với DDL/loại bảng không hỗ trợ giao dịch

Ví dụ trong MySQL, DDL có thể gây commit ngầm. Nhiều hệ quản trị có quy tắc khác nhau cho DDL, các bảng không giao dịch và thao tác đặc biệt. Phải kiểm tra hành vi engine trước khi đưa các thao tác này vào một nhánh cần rollback một phần.

### 11.6. Cho rằng SAVEPOINT chữa được transaction rollback-only

Trong Spring, nếu transaction manager đã đánh dấu transaction ngoài là rollback-only, RELEASE hoặc tạo thêm SAVEPOINT không làm trạng thái đó trở lại commit được. Phải xử lý chính xác propagation và nguồn lỗi, thay vì cố commit một transaction bị đánh dấu thất bại.

### 11.7. Bỏ qua tình huống COMMIT thất bại hoặc phản hồi thất lạc

Sau xử lý thành công các nhánh, `COMMIT` vẫn có thể thất bại vì constraint trì hoãn, serialization failure, mất kết nối hoặc lỗi lưu trữ. Nếu ứng dụng timeout ngay ở lúc commit, trạng thái thực có thể chưa rõ đối với client. Dùng **idempotency key** và cơ chế truy vấn trạng thái khi nghiệp vụ cần chống xử lý trùng; SAVEPOINT không giải quyết bài toán này.

## 12. Minh họa các đường đi trong vòng đời transaction

~~~mermaid
flowchart TD
    Start["BEGIN transaction"] --> Required["Thực hiện bước bắt buộc A"]
    Required --> Marker["SAVEPOINT S"]
    Marker --> Optional["Thử bước tùy chọn B"]
    Optional --> Decision{"B hợp lệ?"}
    Decision -->|Có| Release["RELEASE SAVEPOINT S"]
    Decision -->|Không, lỗi có thể bỏ qua| RollbackPart["ROLLBACK TO SAVEPOINT S"]
    Decision -->|Không thể phục hồi| RollbackAll["ROLLBACK toàn bộ"]
    RollbackPart --> ReleaseAfter["RELEASE S, nếu DB hỗ trợ"]
    Release --> Continue["Thực hiện bước bắt buộc C"]
    ReleaseAfter --> Continue
    Continue --> Valid{"Các bước bắt buộc và COMMIT thành công?"}
    Valid -->|Có| Commit["COMMIT thành công"]
    Valid -->|Không| RollbackAll
    Commit --> Done["Kết quả A + B + C hoặc A + C"]
    RollbackAll --> End["Không giữ các thay đổi chưa commit"]
~~~

Sơ đồ là cách hiểu logic: trên thực tế, nếu `COMMIT` trả lỗi mất kết nối hoặc trạng thái chưa rõ, ứng dụng không thể mặc định rollback đã thành công; cần cơ chế xác minh kết quả phù hợp.

## 13. Bài tập thực hành

### Bài 1 — Hiểu trạng thái sau rollback một phần

Giả sử bảng trống và mọi câu lệnh đều thành công:

~~~sql
BEGIN;
INSERT INTO notes(id, text_value) VALUES (1, 'one');
SAVEPOINT s1;
INSERT INTO notes(id, text_value) VALUES (2, 'two');
SAVEPOINT s2;
INSERT INTO notes(id, text_value) VALUES (3, 'three');
ROLLBACK TO SAVEPOINT s2;
RELEASE SAVEPOINT s2;
INSERT INTO notes(id, text_value) VALUES (4, 'four');
ROLLBACK TO SAVEPOINT s1;
RELEASE SAVEPOINT s1;
COMMIT;
~~~

**Câu hỏi:** những ID nào tồn tại sau COMMIT?

**Lời giải:** chỉ có `id = 1`. `id=3` bị hoàn tác khi rollback về `s2`. `id=2` và `id=4` bị hoàn tác khi rollback tiếp về `s1`.

### Bài 2 — RELEASE không bảo vệ dữ liệu khỏi rollback

~~~sql
BEGIN;
INSERT INTO notes(id, text_value) VALUES (5, 'five');
SAVEPOINT s1;
INSERT INTO notes(id, text_value) VALUES (6, 'six');
RELEASE SAVEPOINT s1;
ROLLBACK;
~~~

**Câu hỏi:** `id=6` có được giữ vì đã RELEASE hay không?

**Lời giải:** không. Cả `id=5` và `id=6` đều không được commit.

### Bài 3 — Thiết kế import có dòng tùy chọn

Yêu cầu: tạo một batch gồm header và 10 dòng. Dòng nào có mã nhãn trùng thì được phép bỏ qua, nhưng lỗi mất kết nối hoặc không tạo được header thì phải hủy tất cả. Hãy xác định:

1. Điểm đặt SAVEPOINT cho từng dòng.
2. Những lỗi nào cho phép tiếp tục sau `ROLLBACK TO`.
3. Khi nào phải `ROLLBACK` toàn bộ.
4. Kết quả nào cần trả về để người dùng biết dòng nào đã bị bỏ qua.

**Gợi ý:** tạo header trước, đặt một savepoint trước mỗi dòng tùy chọn, chỉ bỏ qua duplicate phù hợp chính sách, và commit cuối sau khi xử lý toàn bộ các bước bắt buộc. Phân loại lỗi theo database; không bắt mọi `SQLException` như một trường hợp trùng nhãn.

### Bài 4 — Chọn giữa NESTED và REQUIRES_NEW

Một dịch vụ cần lưu đơn hàng và nhãn tùy chọn. Nếu lưu nhãn lỗi, vẫn phải cho phép lưu đơn; nhưng nếu cuối cùng đơn hàng thất bại, **không được có nhãn nào tồn tại**.

**Đáp án gợi ý:** một transaction ngoài với SAVEPOINT/`NESTED` cho nhãn phù hợp với ràng buộc commit cùng đơn. `REQUIRES_NEW` có nguy cơ commit nhãn độc lập rồi còn lại khi đơn bị rollback.

## 14. Checklist áp dụng cho một use case thực tế

Trước khi đưa SAVEPOINT vào quy trình, hãy trả lời:

1. **Đâu là phần bắt buộc, đâu là phần tùy chọn?** Có cơ sở nghiệp vụ rõ ràng để bỏ nhánh hay không?
2. **SAVEPOINT được tạo trước đúng nhóm thao tác cần rollback chưa?**
3. **Transaction ngoài nằm trên cùng connection và được quản lý nhất quán chưa?**
4. **Lỗi nào có thể rollback một phần, lỗi nào phải rollback toàn bộ?** Có xét trạng thái transaction bị abort/uncommittable chưa?
5. **Sau rollback một phần, những ràng buộc nghiệp vụ còn đúng không?**
6. **Mọi side effect ngoài DB đã được xử lý riêng chưa?**
7. **Hành vi SAVEPOINT có được driver, transaction manager và engine thực sự hỗ trợ không?**
8. **Ranh giới commit cuối cùng có rõ ràng và có xử lý được lỗi ở COMMIT không?**
9. **Số lượng SAVEPOINT và độ dài transaction có phù hợp tải dự kiến không?**
10. **Đã kiểm thử đường thành công, lỗi tùy chọn, lỗi bắt buộc và rollback toàn bộ chưa?**

SAVEPOINT là công cụ để **quay lại một trạng thái trung gian trong transaction đang mở**. Giá trị lớn nhất của nó là giúp ứng dụng xử lý thất bại cục bộ có chủ đích mà không phải bỏ mọi công việc đã làm. Tuy nhiên, mọi thay đổi còn lại vẫn thuộc transaction ngoài và chỉ có hiệu lực bền vững khi transaction đó commit. Hiểu đúng ranh giới này giúp thiết kế quy trình vừa linh hoạt trước lỗi dữ liệu tùy chọn, vừa giữ được tính nguyên tử và tính nhất quán của nghiệp vụ.
