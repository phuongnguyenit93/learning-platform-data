# Khi nào cần custom change thay vì change type có sẵn

## 1. Bối cảnh: mở rộng Liquibase đúng lúc

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, mục tiêu là quản lý thay đổi schema và dữ liệu có kiểm chứng bằng changelog, changeset, precondition, checksum, lịch sử triển khai, rollback và quy trình phối hợp nhiều môi trường. Ở chương **Mở rộng**, một câu hỏi thiết kế quan trọng là: **khi nào nên phát triển custom change thay vì sử dụng change type có sẵn?**

Liquibase cung cấp nhiều change type như `createTable`, `addColumn`, `createIndex`, `addForeignKeyConstraint`, `insert`, `update`, `renameColumn` và `sqlFile`. Phần lớn migration schema thông thường nên bắt đầu từ các thành phần này. Một **custom change** là phần mở rộng do nhóm tự lập trình, thường bằng Java, để Liquibase gọi khi xử lý changeset. Nó cần thiết trong một số tình huống có logic chuyên biệt mà change type chuẩn hoặc SQL rõ ràng không diễn đạt tốt.

Quyết định dùng custom change có tác động vượt quá một file changelog: bạn phải bảo trì mã Java, đóng gói dependency cho CLI/Spring Boot/CI/CD, kiểm soát phiên bản bytecode, triển khai rollback, thử nghiệm trên DBMS đích và theo dõi trạng thái khi thay đổi thất bại. Vì thế **custom change là phương án cuối sau khi đánh giá API Liquibase có sẵn và SQL tùy chỉnh** — không phải lựa chọn mặc định chỉ vì người viết quen Java.

Sau bài học, bạn có thể:

- Chọn giữa change type chuẩn, `sql`/`sqlFile` và Java custom change theo tiêu chí kiểm chứng được.
- Phân biệt `CustomTaskChange`, `CustomSqlChange` và cơ chế rollback liên quan.
- Thiết kế một custom change có validation, tham số, xử lý dữ liệu và giới hạn trách nhiệm rõ ràng.
- Đánh giá transaction, idempotency, checksum, portability, SQL preview và rủi ro vận hành.
- Đưa extension vào Spring Boot hoặc migration job và kiểm thử trên CI/CD mà không làm lệch lịch sử.

## 2. Ba cấp giải pháp: declarative → SQL → custom code

Với một yêu cầu migration mới, hãy so sánh ba hướng theo thứ tự ưu tiên:

| Phương án | Ví dụ | Lợi thế | Chi phí/rủi ro |
|---|---|---|---|
| **Change type có sẵn** | `addColumn`, `createIndex` | Khai báo ngắn, dễ review, Liquibase sinh SQL theo DBMS và có metadata rõ | Không biểu diễn được mọi tính năng vendor hoặc nghiệp vụ phức tạp |
| **SQL tùy chỉnh** | `sql`, `sqlFile`, formatted SQL | Minh bạch SQL, dùng được syntax DBMS đặc thù, dễ xem trước | Phụ thuộc dialect, delimiter và transaction; rollback thường phải tự viết |
| **Java custom change** | Triển khai `CustomSqlChange` hoặc `CustomTaskChange` | Có thuật toán, thư viện Java, lựa chọn câu lệnh động theo metadata | Cần classpath, kiểm thử mã, kiểm soát version, khó preview/rollback hơn |

Ví dụ yêu cầu **thêm cột nullable**: chọn `addColumn`.

Yêu cầu **tạo index bằng cú pháp đặc thù** mà change type hỗ trợ chưa đủ: cân nhắc `sql` hoặc `sqlFile`, giới hạn theo `dbms` và viết rollback.

Yêu cầu **giải mã dữ liệu nhị phân legacy bằng thư viện Java nội bộ rồi chuyển sang bảng mới**, không thể biểu diễn ổn định và rõ ràng bằng SQL: có thể cân nhắc `CustomTaskChange` sau khi đánh giá liệu một job backfill riêng ngoài Liquibase có phù hợp hơn không.

### 2.1. Cây quyết định

```text
Có change type Liquibase chuẩn đáp ứng đủ?
  ├─ Có → Ưu tiên change type chuẩn
  └─ Không
      |
      v
Có thể viết SQL/sqlFile ngắn, rõ, test được?
  ├─ Có → SQL tùy chỉnh + dbms + rollback/test
  └─ Không
      |
      v
Có cần thuật toán Java, thư viện đặc biệt,
hoặc tạo SQL động theo metadata một cách đáng kể?
  ├─ Không → Thiết kế lại migration / tách bước
  └─ Có
      |
      v
Có thể đóng gói extension, kiểm thử, quan sát,
kiểm soát retry và phương án phục hồi?
  ├─ Không → Job riêng hoặc thay đổi kiến trúc
  └─ Có → Cân nhắc custom change có kiểm soát
```

Không nên xem cây quyết định là quy tắc tuyệt đối. Ví dụ một change type chuẩn có thể sinh SQL không phù hợp với yêu cầu online migration của DBMS cụ thể; lúc đó SQL tường minh được review tốt hơn.

## 3. Vì sao ưu tiên change type có sẵn?

Liquibase hiểu semantics của change type chuẩn. Khi gặp `createTable` hoặc `addColumn`, nó có thể:

- Phân tích và validate các thuộc tính liên quan.
- Sinh SQL dựa trên database implementation và khả năng hỗ trợ.
- Ghi identity và checksum vào lịch sử.
- Cung cấp một số cơ chế rollback tự động với những change type hỗ trợ.
- Hiển thị thay đổi ở mức ý định, giúp reviewer hiểu dễ hơn SQL dài.
- Hỗ trợ extension/database-specific SQL generators theo cơ chế Liquibase.

Ví dụ YAML tạo cột:

```yaml
databaseChangeLog:
  - changeSet:
      id: "001-add-account-status"
      author: "schema-team"
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: status_code
                  type: VARCHAR(20)
```

Đây là một migration declarative. Nhóm không cần viết Java, quản lý JDBC connection hoặc tự xây SQL cho từng DBMS.

Nếu yêu cầu chỉ là thêm cột, đổi tên bảng, tạo index, thêm constraint hoặc nạp một ít dữ liệu reference, custom change thường làm tăng chi phí mà không đem lại lợi ích tương xứng.

### 3.1. Thử kết hợp change type và precondition trước

Nhiều bài toán tưởng cần Java thực ra giải được bằng các primitive có sẵn:

- `preConditions` kiểm tra điều kiện đầu vào.
- `sqlCheck` kiểm tra giá trị truy vấn.
- `dbms` giới hạn engine.
- Context/label giới hạn môi trường hoặc giai đoạn release.
- Nhiều changeset chia một thao tác lớn thành những bước rõ ràng.
- `sqlFile` chứa SQL vendor-specific được review riêng.
- `runInTransaction` điều chỉnh transaction theo hỗ trợ của DBMS và yêu cầu thực tế.

Dùng những khả năng này thường rõ ràng hơn việc viết một lớp Java có nhiều nhánh xử lý.

## 4. Khi nào SQL tùy chỉnh tốt hơn custom change?

SQL tùy chỉnh là lựa chọn hợp lý khi yêu cầu vẫn **bản chất là một hoặc vài câu SQL**, nhưng change type chuẩn không diễn đạt được:

- Tạo index với tùy chọn đặc thù DBMS.
- Dùng function, expression index hoặc operator riêng.
- Thực hiện data migration bằng một câu `UPDATE ... CASE` rõ ràng.
- Chạy DDL có tùy chọn online/concurrently riêng engine.
- Tạo procedure, trigger hoặc view phức tạp.

Ví dụ PostgreSQL tạo index theo biểu thức:

```yaml
databaseChangeLog:
  - changeSet:
      id: "002-index-email-lower"
      author: "schema-team"
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX idx_account_email_lower
              ON customer_account (lower(email));
      rollback:
        - sql:
            sql: |
              DROP INDEX IF EXISTS idx_account_email_lower;
```

Ví dụ dành cho PostgreSQL và database thử nghiệm được phép sửa. Phải kiểm tra khóa, chi phí tạo index và SQL rollback trên phiên bản DBMS thực tế.

Nếu đã có SQL ngắn và quyết định được từ trước, dùng custom Java chỉ để gọi chính SQL đó thường không đáng: khó preview hơn, thêm dependency và làm reviewer phải đi đọc cả mã nguồn Java.

### 4.1. sqlFile khi SQL dài

```yaml
databaseChangeLog:
  - changeSet:
      id: "003-refresh-reporting-view"
      author: "schema-team"
      dbms: postgresql
      changes:
        - sqlFile:
            path: sql/003-refresh-reporting-view.sql
            relativeToChangelogFile: true
            splitStatements: false
```

`sqlFile` cho phép review một file SQL riêng và vẫn giữ changeset identity trong changelog cha. Hãy kiểm tra delimiters, đường dẫn resource và rollback. File SQL dùng `sqlFile` không đồng nghĩa tự động là formatted SQL changelog.

## 5. Tình huống thực sự đáng cân nhắc custom change

Một custom change có thể hợp lý khi thỏa nhiều điều kiện sau:

1. **Logic không thể biểu diễn đáng tin bằng change type hoặc SQL ngắn.** Ví dụ cần giải mã định dạng cũ, normalize một thuật toán phức tạp, hoặc đọc dữ liệu tài nguyên đặc thù.
2. **Cần thư viện Java chuyên biệt.** Việc port thuật toán sang SQL dễ gây sai logic hoặc không thể bảo trì.
3. **Cần đọc metadata database để quyết định kế hoạch SQL một cách có cấu trúc.** Tuy nhiên trước tiên hãy xem extension SQL generator hoặc change type chuẩn đã hỗ trợ chưa.
4. **Có thể xác định rõ input, output và bất biến.** Một custom change không nên làm “mọi thứ” trong một lần chạy.
5. **Có phương án phục hồi.** Có thể rollback thật, migration bù, backup/PITR hoặc forward-fix được phê duyệt.
6. **Có môi trường test và đóng gói đáng tin.** Cùng class implementation và dependency phải có mặt tại mọi môi trường chạy Liquibase.
7. **Có lý do chọn chạy trong Liquibase thay vì một job nghiệp vụ riêng.** Với backfill khối lượng lớn, việc chuyển sang batch job quan sát được thường an toàn hơn.

Ví dụ đáng cân nhắc: dữ liệu legacy được lưu bằng codec Java riêng, cần chuyển thành cấu trúc chuẩn và phải tái sử dụng thư viện decoder đã có test. Một custom task có thể dùng thư viện đó trên từng bản ghi rồi cập nhật kết quả. Nhưng nếu phải xử lý hàng trăm triệu bản ghi trong nhiều giờ, một batch job checkpoint/resume riêng có thể tốt hơn việc giữ Liquibase lock và thời gian startup lâu.

## 6. Tình huống không nên dùng custom change

Không nên viết custom change chỉ vì:

- Người phát triển muốn viết Java thay vì YAML/XML.
- Một change type chuẩn thiếu một tùy chọn nhỏ nhưng có thể viết vài dòng SQL rõ ràng.
- Muốn giấu SQL khỏi code review.
- Muốn bỏ qua checksum hoặc lịch sử Liquibase.
- Muốn tự mở connection và commit ở bất kỳ thời điểm nào.
- Muốn gọi API bên ngoài, gửi email hoặc thao tác file như tác vụ vận hành thông thường.
- Muốn xử lý dữ liệu lớn không kiểm soát, không checkpoint, không đánh giá timeout.
- Không có khả năng đưa extension JAR đến migration CLI, Spring Boot và pipeline.
- Muốn thay thế một job backfill hoặc ETL mà đáng lẽ cần theo dõi tiến độ riêng.

Custom change là một phần của migration được ghi nhận trong `DATABASECHANGELOG`. Nó không tự nhiên cung cấp hàng đợi, cơ chế resume ở từng bản ghi, giám sát dài hạn hay distributed orchestration.

## 7. Các interface quan trọng của custom change Java

Liquibase có API để lập trình custom change. Hai hướng thường gặp:

| Interface | Vai trò | Đặc điểm vận hành |
|---|---|---|
| `CustomTaskChange` | Thực hiện logic Java khi Liquibase chạy changeset | Có thể truy cập Database/connection, nhưng SQL preview không thể hiện đầy đủ tác động Java |
| `CustomSqlChange` | Tạo các đối tượng SQL statement để Liquibase thực thi | Phù hợp khi cần sinh SQL có cấu trúc theo metadata; SQL preview có cơ hội quan sát kết quả sinh |
| `CustomTaskRollback` | Cung cấp logic rollback cho custom task | Chỉ áp dụng khi có thể định nghĩa hành vi đảo ngược có ý nghĩa |
| `CustomSqlRollback` | Cung cấp SQL statements cho rollback custom SQL | Cần xác minh SQL rollback trên DBMS đích |

Đây là các API nổi bật trong các phiên bản Liquibase 4.x; chữ ký method, cơ chế instantiate, XSD/parameter binding và classpath có thể khác theo phiên bản. Trước khi sao chép mẫu, hãy kiểm tra đúng API và runtime Liquibase đã pin của dự án.

### 7.1. CustomTaskChange

Một triển khai `CustomTaskChange` nhận database và thực hiện logic. Nó hữu ích với phép chuyển đổi cần Java, nhưng phải đặc biệt chú ý:

- Tính nhất quán của transaction.
- Tốc độ xử lý, batch size và timeout.
- SQL injection và quyền truy cập.
- Partial effect khi thất bại.
- Khả năng hiển thị SQL preview.
- Kế hoạch rollback/forward recovery.

### 7.2. CustomSqlChange

`CustomSqlChange` sinh ra các `SqlStatement` thay vì tự thực thi toàn bộ công việc bên trong một task. Đây có thể là phương án phù hợp nếu thuật toán chủ yếu là chọn cấu trúc SQL dựa trên metadata/DBMS.

Không nên giả định mọi statement do custom SQL generator sinh ra đều portable hoặc có rollback tự động. Hãy kiểm tra lệnh preview và thực thi trên từng DBMS hỗ trợ.

## 8. Lifecycle, metadata và validation của custom change

Một custom change thường cần các phần trách nhiệm sau:

- Nhận tham số từ changelog qua property setter hoặc cơ chế của version đang dùng.
- Khởi tạo với `setUp()`.
- Nhận resource accessor qua `setFileOpener(ResourceAccessor)` khi cần đọc resource được đóng gói.
- Kiểm tra tham số và điều kiện cấu hình bằng `validate(Database)`.
- Thực thi tác động bằng `execute(Database)` hoặc tạo SQL bằng `generateStatements(Database)`.
- Trả thông điệp kết quả bằng `getConfirmationMessage()`.

Không dùng validation để thực hiện DDL/DML hoặc gọi side effect. Validation nên kiểm tra điều kiện có thể biết trước: tham số bắt buộc, range của batch size, DBMS được hỗ trợ, format cấu hình. Những điều kiện dữ liệu như duplicate/null nên được kiểm tra thêm bằng precondition và bài test trong môi trường representative.

### 8.1. Ví dụ cấu trúc class với CustomTaskChange

Ví dụ dưới đây minh họa **bộ khung**; phần `LegacyStatusCodec` là thư viện nghiệp vụ do dự án cung cấp, không phải API của Liquibase. Cần bổ sung imports, dependency, unit test và xác nhận đúng chữ ký API theo Liquibase version.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

import liquibase.change.custom.CustomChangeException;
import liquibase.change.custom.CustomTaskChange;
import liquibase.change.custom.SetupException;
import liquibase.database.Database;
import liquibase.database.jvm.JdbcConnection;
import liquibase.exception.ValidationErrors;
import liquibase.resource.ResourceAccessor;

public final class DecodeLegacyStatusChange implements CustomTaskChange {

    private int batchSize = 250;

    // Liquibase có thể bind tham số "batchSize" qua setter.
    public void setBatchSize(String value) {
        this.batchSize = Integer.parseInt(value);
    }

    @Override
    public void setUp() throws SetupException {
        // Không chạy DDL/DML ở bước setup.
    }

    @Override
    public void setFileOpener(ResourceAccessor accessor) {
        // Có thể giữ ResourceAccessor nếu cần đọc resource.
    }

    @Override
    public ValidationErrors validate(Database database) {
        ValidationErrors errors = new ValidationErrors();
        if (batchSize < 1 || batchSize > 1000) {
            errors.addError("batchSize phải nằm trong [1, 1000]");
        }
        return errors;
    }

    @Override
    public void execute(Database database) throws CustomChangeException {
        if (!(database.getConnection() instanceof JdbcConnection)) {
            throw new CustomChangeException("Yêu cầu JDBC connection");
        }

        Connection jdbc = ((JdbcConnection) database.getConnection())
            .getUnderlyingConnection();

        String selectSql =
            "SELECT id, legacy_status_bytes " +
            "FROM customer_account " +
            "WHERE status_code IS NULL ORDER BY id";

        String updateSql =
            "UPDATE customer_account SET status_code = ? " +
            "WHERE id = ? AND status_code IS NULL";

        try (PreparedStatement read = jdbc.prepareStatement(selectSql);
             ResultSet rs = read.executeQuery();
             PreparedStatement update = jdbc.prepareStatement(updateSql)) {

            int pending = 0;
            while (rs.next()) {
                // Decoder là thư viện nghiệp vụ, phải được kiểm thử riêng.
                String value = LegacyStatusCodec.decode(rs.getBytes(2));
                update.setString(1, value);
                update.setLong(2, rs.getLong(1));
                update.addBatch();

                if (++pending >= batchSize) {
                    update.executeBatch();
                    pending = 0;
                }
            }
            if (pending > 0) {
                update.executeBatch();
            }
        } catch (SQLException | RuntimeException ex) {
            throw new CustomChangeException(
                "Không thể chuyển đổi legacy status", ex);
        }
    }

    @Override
    public String getConfirmationMessage() {
        return "Đã xử lý chuyển đổi legacy status";
    }
}
```

**Giới hạn của ví dụ:** đây là skeleton để giải thích interface, không phải production-ready batch backfill. Nó sử dụng query JDBC và `LegacyStatusCodec` giả định; cần kiểm tra cách JDBC driver streaming `ResultSet`, lượng memory, schema, khóa, timeout, transaction và khả năng resume. Không đóng hoặc tự commit connection do Liquibase quản lý. Với dữ liệu lớn, hãy tách thành job có checkpoint thay vì dùng một transaction kéo dài và giữ lock toàn bộ migration.

### 8.2. Bind class trong changelog XML

```xml
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog
        http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-4.30.xsd">

    <changeSet id="050-decode-legacy-status"
               author="schema-team">
        <customChange class="com.example.migration.DecodeLegacyStatusChange">
            <param name="batchSize" value="250"/>
        </customChange>
    </changeSet>
</databaseChangeLog>
```

Điều kiện để chạy:

1. Class đã được biên dịch và nằm trên classpath của **chính process Liquibase**.
2. Mọi thư viện của `LegacyStatusCodec` đều có mặt với version tương thích.
3. Runtime hỗ trợ `customChange` và binding tham số theo cú pháp được sử dụng.
4. Database và role có quyền đọc cột legacy, cập nhật cột đích.
5. Precondition và kiểm thử xác nhận schema đầu vào đã tồn tại.

Không sao chép nguyên ví dụ vào production nếu chưa có decoder thật, test data, plan phục hồi và kiểm soát khối lượng.

## 9. Kiểm tra đầu vào bằng precondition trước custom change

Custom change không nên tự gánh mọi bước bảo vệ. Hãy tận dụng precondition declarative để chặn sớm khi schema chưa đúng, tránh ghi dữ liệu lên cấu trúc sai.

Ví dụ YAML trước một custom change có thể có:

```yaml
databaseChangeLog:
  - changeSet:
      id: "049-check-legacy-columns"
      author: "schema-team"
      preConditions:
        - onFail: HALT
        - columnExists:
            tableName: customer_account
            columnName: legacy_status_bytes
        - columnExists:
            tableName: customer_account
            columnName: status_code
      changes:
        - sql:
            sql: SELECT 1
```

Ví dụ này chỉ minh họa cách đặt precondition; trong thiết kế thực tế, nên gắn precondition vào **cùng changeset cần điều kiện** và không tạo một changeset chỉ chứa `SELECT 1` để làm cổng giả. Với customChange XML ở trên, có thể thêm `<preConditions>...<columnExists .../>...</preConditions>` ngay trước `<customChange>` trong changeset đó.

Các precondition dữ liệu như count NULL, unsupported code hoặc orphan nên có query phù hợp DBMS và được kiểm thử cả nhánh đạt lẫn nhánh HALT. Không dùng `MARK_RAN` để che việc custom change chưa thực sự tạo hiệu ứng mong muốn.

## 10. Lựa chọn giữa CustomTaskChange và CustomSqlChange

Một cách chọn đơn giản:

| Câu hỏi | CustomTaskChange | CustomSqlChange |
|---|---|---|
| Logic là thuật toán Java thao tác dữ liệu? | Thường phù hợp hơn | Có thể không phù hợp |
| Logic là sinh SQL theo metadata DBMS? | Không phải ưu tiên | Thường phù hợp hơn |
| Cần xem SQL trước update? | Khó quan sát đầy đủ | Có thể sinh SQL để review |
| Cần rollback? | Cần thiết kế task rollback hoặc cơ chế phù hợp | Cần thiết kế SQL rollback |
| Phụ thuộc thư viện domain? | Có thể tận dụng | Chỉ khi tạo SQL |
| Migration rất lớn, cần resume theo checkpoint? | Thường nên cân nhắc job ngoài Liquibase | Có thể sinh SQL nhưng vẫn cần kiểm soát vận hành |

### 10.1. Tránh biến CustomSqlChange thành “SQL string builder” không kiểm soát

Nếu logic chỉ là ghép chuỗi SQL từ input changelog, cần cân nhắc SQL injection, quote identifier và khác biệt dialect. Không đưa thẳng tên bảng/cột do người dùng nhập vào raw SQL. Với giá trị dữ liệu, dùng parameter binding khi tự thực thi JDBC; với identifier, dùng danh sách cho phép hoặc API tạo SQL phù hợp.

Nếu chỉ có một câu lệnh cố định, đặt trực tiếp trong `sql` hoặc `sqlFile` sẽ minh bạch và dễ review hơn.

## 11. Transaction: custom change không được tự ý quản lý connection

Liquibase quản lý việc thực thi changeset và thường tổ chức transaction theo changeset khi DBMS và thao tác hỗ trợ, với `runInTransaction` theo cấu hình. Custom code cần tôn trọng vòng đời connection được Liquibase cung cấp.

Các lỗi nguy hiểm:

- Mở connection riêng rồi commit độc lập với transaction Liquibase.
- Gọi `commit()` hoặc `setAutoCommit(true)` trên managed connection tùy tiện.
- Ghi vào database phụ mà không có transaction/distributed coordination phù hợp.
- Gọi HTTP API tạo side effect mà Liquibase rollback không hoàn tác.
- Xử lý nhiều triệu bản ghi trong transaction dài gây lock, log growth và timeout.

**Nguyên tắc:** không tự quản lý commit của connection Liquibase nếu không có lý do rất đặc biệt, đã được thiết kế và kiểm thử. Nếu phải dùng connection ngoài, phải ghi rõ atomicity boundary và cơ chế đối soát.

### 11.1. DDL có thể commit ngầm

Một số DBMS có implicit commit đối với nhiều thao tác DDL. `runInTransaction: true` không biến mọi DDL thành thao tác có thể rollback. Một custom task có thể trộn DDL và DML, làm trạng thái sau failure phức tạp hơn.

Trước release, hãy kiểm thử custom change với DBMS/version production, kể cả lỗi giữa chừng, để biết chính xác thứ gì đã commit, thứ gì bị rollback và record `DATABASECHANGELOG` có được ghi hay chưa.

## 12. Idempotency và khả năng retry

Khi một changeset thất bại, Liquibase có thể chưa ghi nhận nó là đã hoàn tất. Nếu custom code đã tạo side effect một phần và lần sau chạy lại, nó có thể làm trùng dữ liệu hoặc gây lỗi.

Một custom change tốt cần trả lời:

1. Nếu chạy lại cùng input, kết quả có bị nhân đôi không?
2. Có khóa tự nhiên hoặc idempotency key để tránh duplicate không?
3. Nếu dừng sau batch thứ 7, lần chạy sau biết xử lý tiếp từ đâu?
4. Có kiểm tra số lượng/giá trị trước và sau không?
5. Nếu rollback transaction không hỗ trợ, có migration bù hoặc snapshot không?
6. Nếu dữ liệu không hợp lệ, dừng an toàn hay bỏ qua có log và đối soát?

Trong ví dụ Java, câu `UPDATE ... WHERE status_code IS NULL` giúp tránh ghi đè những bản ghi đã chuyển, nhưng **không đảm bảo toàn bộ migration idempotent trong mọi trường hợp**. Bản ghi có thể bị thay đổi đồng thời, decoder có thể không deterministic hoặc bảng nguồn có thể thay đổi giữa các lần chạy.

Với dữ liệu lớn cần checkpoint và resume, một batch job theo tiến trình riêng có thể phù hợp hơn Liquibase changeset. Đừng cố biến custom change thành một ETL engine lâu dài.

## 13. Rollback: tính chất bắt buộc phải được thiết kế

Một custom change không tự động có rollback có ý nghĩa. Liquibase có API `CustomTaskRollback`, `CustomSqlRollback` hoặc cách khai báo rollback tường minh tùy loại change và phiên bản. Nhưng khả năng gọi rollback không đồng nghĩa có thể khôi phục thông tin đã mất.

Ví dụ giải mã legacy bytes thành status code:

- Nếu vẫn giữ cột nguồn và phép chuyển đổi thuần, rollback có thể chỉ cần đưa cột đích về trạng thái trước migration — nhưng phải biết giá trị gốc nào đã tồn tại.
- Nếu custom change xóa dữ liệu nguồn hoặc chuyển đổi mất thông tin, không thể đơn giản đảo ngược bằng cách viết một SQL reverse.
- Nếu application đã ghi dữ liệu mới sau migration, rollback schema có thể làm mất hoặc sai dữ liệu.

### 13.1. Phân loại chiến lược phục hồi

| Loại thay đổi | Phương án thường cân nhắc |
|---|---|
| Schema mở rộng có thể bỏ | Rollback DDL đã kiểm thử |
| Dữ liệu chuyển đổi reversible và có dấu vết | Custom rollback hoặc SQL rollback dựa trên dữ liệu gốc |
| Dữ liệu chuyển đổi mất thông tin | Backup/PITR, migration bù, forward fix |
| Tác động hệ thống ngoài database | Quy trình bù và đối soát độc lập |
| Backfill lớn theo batch | Job resumable, checkpoint và chiến lược dừng/tiếp tục |

Không điền rollback “giả” chỉ để lệnh preview báo pass. Nếu một migration không thể rollback an toàn, hãy mô tả giới hạn, yêu cầu backup và phê duyệt trước khi thực thi.

## 14. SQL preview và khả năng quan sát của custom change

Với change type chuẩn hoặc `sqlFile`, `update-sql` thường thể hiện những statement sẽ được thực thi. Với **CustomTaskChange**, phần lớn logic nằm trong `execute(Database)` của Java nên không thể suy ra đầy đủ SQL chỉ từ changelog. Vì vậy:

- Không coi SQL preview trống hoặc thiếu statement là bằng chứng custom change không làm gì.
- Không tự tin rằng reviewer đã nhìn thấy toàn bộ DML của task chỉ vì pipeline lưu `update-sql`.
- Cần tài liệu về thuật toán, target table, số bản ghi dự kiến, read/write pattern và phương án phục hồi.
- Cần kiểm thử integration xác nhận tác động schema/data trên DBMS đích.
- Cần log/metric có kiểm soát để biết số bản ghi xử lý và điều kiện thất bại.

Với `CustomSqlChange`, preview có thể hữu ích hơn vì extension sinh ra `SqlStatement`; vẫn phải kiểm tra đúng phiên bản engine và filter.

### 14.1. Không ghi dữ liệu nhạy cảm vào log

Custom Java có thể nhìn thấy thông tin database. Log chỉ nên ghi số lượng, ID batch hoặc thống kê phù hợp; tránh ghi payload cá nhân, secret, connection password hoặc bản ghi thô vào console CI/CD.

Nếu cần audit, sử dụng cơ chế logging và retention theo chính sách. Không để stack trace chứa SQL với literal nhạy cảm trong artifact công khai.

## 15. Checksum, identity và version của Java class

Liquibase nhận diện changeset theo bộ ba:

```text
(id, author, logical changelog file path)
```

Checksum của changeset phản ánh nội dung mà Liquibase dùng để tính checksum trong changelog, **không nên giả định nó phản ánh bytecode, dependency hoặc thuật toán Java của custom class**. Đây là rủi ro quan trọng: nếu mã `DecodeLegacyStatusChange` thay đổi giữa hai bản build mà XML changelog vẫn giữ nguyên, lịch sử có thể không phản ánh sự khác biệt của thuật toán.

Hậu quả:

- Môi trường A có thể thực thi version 1 của custom class.
- Môi trường B dùng cùng changeset identity nhưng thực thi version 2.
- Hai môi trường có thể có kết quả dữ liệu khác dù changelog text giống nhau.

Biện pháp:

1. Pin artifact và dependency của extension theo release.
2. Ghi commit/digest của migration job và extension JAR.
3. Không thay đổi hành vi class đã được dùng cho changeset lịch sử.
4. Với logic mới, tạo changeset mới và cân nhắc class version mới.
5. Giữ build reproducible hoặc ít nhất có provenance kiểm chứng.
6. Test upgrade path trên artifact chính xác sẽ phát hành.

Đừng giải quyết khác biệt custom code bằng cách sửa `MD5SUM` hoặc xóa record `DATABASECHANGELOG`. Giữ lịch sử trung thực và thêm migration bù khi cần.

## 16. Đóng gói và classpath cho CLI, Spring Boot và CI/CD

Một custom change Java phải hiện diện trong **process Liquibase thực thi migration**. Đây có thể là:

- Liquibase CLI chạy độc lập.
- Spring Boot application tự chạy Liquibase khi startup.
- Migration job/container chuyên dụng trong CI/CD.
- Plugin/extension runtime được quản lý riêng.

Nếu class hoặc dependency không được nạp, Liquibase có thể báo `ClassNotFoundException`, `NoClassDefFoundError`, lỗi khởi tạo class hoặc lỗi parameter binding. Changelog có cú pháp đúng vẫn không thực thi được.

### 16.1. Đường đi triển khai

```text
Source code custom change
          |
          v
Build + test extension JAR
          |
          v
Pin version/digest artifact
          |
          v
Đóng gói vào Liquibase runtime classpath
          |
          v
validate / migration integration test
          |
          v
Preview + approval
          |
          v
Production migration job hoặc Spring Boot startup
```

### 16.2. Spring Boot

Khi Liquibase được bật trong Spring Boot, app thường tạo `SpringLiquibase` trong quá trình khởi tạo context. Nếu custom class nằm trong ứng dụng JAR cùng dependency tương thích, Liquibase có thể nạp nó từ classpath. Nhưng nếu migration chạy bằng CLI/job riêng, việc class có trong application JAR **không đảm bảo** class có trong CLI/job.

Cần kiểm tra bản đóng gói thực tế, plugin dependency, version Liquibase và cách Spring Boot loader expose class/resource. Với hệ thống nhiều replica, hãy cân nhắc một migration job riêng để tránh mọi replica cùng thực hiện custom task lâu.

### 16.3. Không trộn version Liquibase

Các interface extension và dependency có thể thay đổi giữa version. Extension cần được build/test với version Liquibase đã pin và runtime thực tế. Không dựa vào việc “compile được” để kết luận sẽ hoạt động trên một CLI cũ hơn hoặc Spring Boot đang quản lý version Liquibase khác.

## 17. Testing strategy cho custom change

Không chỉ chạy một unit test cho phương thức Java. Cần ít nhất các tầng sau:

| Tầng kiểm thử | Mục tiêu |
|---|---|
| Unit test | Kiểm tra codec/thuật toán với input hợp lệ, null, lỗi và dữ liệu biên |
| Validation test | Kiểm tra param thiếu/sai, DBMS không hỗ trợ và lỗi setup |
| Integration DBMS | Chạy changeset thật trên đúng engine production |
| Fresh install | Xác nhận changelog từ database trống |
| Upgrade path | Chạy từ schema cũ với dữ liệu legacy |
| Partial failure | Cố ý làm lỗi giữa chừng; xem history, data và transaction |
| Retry/idempotency | Chạy lại theo trạng thái phục hồi; không làm trùng dữ liệu |
| Rollback/forward fix | Thử khả năng phục hồi được công bố |
| Packaging test | Chạy bằng đúng artifact CLI/Boot/job sẽ deploy |
| Performance test | Đo throughput, lock, timeout và memory với dữ liệu đại diện |

### 17.1. Test database phải cùng engine

H2 có thể thích hợp cho vòng feedback nhanh nhưng không chứng minh các giả định DDL, transaction, type, lock và encoding của PostgreSQL/MySQL/Oracle/SQL Server. Custom task dùng JDBC/SQL và thuật toán nhạy với schema phải được kiểm thử trên engine production hoặc môi trường tương đương.

### 17.2. Bài test partial effect

Một test quan trọng:

1. Chuẩn bị vài trăm bản ghi legacy trong database disposable.
2. Cho decoder cố ý lỗi sau một số bản ghi/batch.
3. Kiểm tra transaction đã rollback hay có dữ liệu cập nhật một phần.
4. Kiểm tra `DATABASECHANGELOG` có đánh dấu changeset hay chưa.
5. Xác minh lần retry không nhân đôi hoặc bỏ sót dữ liệu.
6. Kiểm tra log/metric không để lộ payload nhạy cảm.

Không thực hiện fault injection trên database production.

## 18. Review bảo mật, hiệu năng và portability

Một custom change cũng là code có quyền migration. Quyền này thường rộng hơn application runtime, nên cần review như một thành phần triển khai hạ tầng.

**Bảo mật:**

- Dùng `PreparedStatement` cho giá trị dữ liệu; không ghép SQL từ input chưa xác thực.
- Kiểm soát identifier nếu cần tạo SQL động.
- Không gọi shell/process bên ngoài một cách tùy tiện.
- Không đọc secret hoặc file ngoài phạm vi migration cần thiết.
- Pin dependency và kiểm tra vulnerability/license theo chính sách.
- Không ghi payload/secret vào log.

**Hiệu năng:**

- Xem xét batch size, cursor/streaming và memory.
- Đo DB lock, transaction log và thời gian migration.
- Tránh quét toàn bảng lặp đi lặp lại mà không index.
- Xác định timeout và resource limit của CI/CD/job.
- Tránh block Spring Boot startup lâu nếu data migration lớn.

**Portability:**

- Xác định DBMS hỗ trợ bằng `dbms` hoặc validation.
- Không giả định JDBC driver trả kiểu dữ liệu giống nhau ở mọi DBMS.
- Dùng SQL generator hoặc statement phù hợp dialect khi cần.
- Kiểm thử trên từng engine được công bố hỗ trợ.
- Không tự tuyên bố “cross-platform” chỉ vì class Java biên dịch trên nhiều hệ điều hành.

## 19. Vận hành khi custom change thất bại

Quy trình xử lý nên theo thứ tự:

1. **Dừng rollout hoặc giữ readiness không đạt** nếu schema mới là điều kiện bắt buộc.
2. Xác định đúng application/migration artifact, custom class version và dependency.
3. Đọc exception gốc, xác định thay đổi bị lỗi trước hay sau khi viết dữ liệu.
4. Kiểm tra `DATABASECHANGELOG` và bảng `DATABASECHANGELOGLOCK` theo schema metadata thực tế.
5. Đối chiếu dữ liệu và schema thực tế; không suy ra từ log “failed” rằng mọi thao tác đã rollback.
6. Xác định transaction boundary và side effect ngoài database nếu có.
7. Đánh giá retry có an toàn/idempotent không.
8. Nếu không an toàn, thiết kế repair/compensating migration hoặc restore theo kế hoạch.
9. Thử trên bản sao representative rồi mới thực thi quy trình phục hồi.
10. Lưu postmortem: nguyên nhân, artifact, changeset identity, dữ liệu ảnh hưởng và thay đổi phòng ngừa.

Không xóa record history, sửa checksum hoặc dùng `MARK_RAN` để che lỗi. Nếu lock bị bỏ lại, chỉ giải phóng sau khi xác minh không còn migration process hợp lệ.

## 20. Bài thực hành: chọn giải pháp phù hợp

Giả sử nhóm có bốn yêu cầu:

| Yêu cầu | Phương án đề xuất | Lý do |
|---|---|---|
| Thêm cột `status_code` | `addColumn` | Có change type chuẩn |
| Tạo expression index dùng PostgreSQL | `sql`/`sqlFile` | SQL rõ, ngắn và đặc thù DBMS |
| Backfill 1.000 bản ghi bằng bộ giải mã nhị phân Java nội bộ | Cân nhắc `CustomTaskChange` | Thuật toán domain nằm trong thư viện Java; phải có test và recovery |
| Chuyển đổi 200 triệu bản ghi, có nhiều giờ chạy và cần checkpoint/resume | Job dữ liệu riêng, Liquibase quản lý schema và milestone | Không nên giữ migration lock và startup quá lâu |

### Bước 1. Viết decision record

Với yêu cầu backfill binary, ghi rõ vì sao SQL hoặc change type chuẩn không đủ, library Java cần dùng, volume, DBMS, quyền và thời gian cho phép.

### Bước 2. Xây dựng custom class

Triển khai setter tham số, `validate`, `execute`/`generateStatements` và message. Không tự commit connection Liquibase. Có unit test cho decoder.

### Bước 3. Tạo changeset có precondition

Kiểm tra cột nguồn/đích tồn tại, dữ liệu đầu vào hợp lệ và đặt changeset identity ổn định. Xác định rõ rollback hoặc forward recovery.

### Bước 4. Chạy integration test

Dùng database cùng engine production, dữ liệu bình thường và dữ liệu biên. Xác nhận số bản ghi đúng, schema không drift, history được ghi nhận, retry có kiểm soát.

### Bước 5. Thử failure/retry

Cố ý làm decoder lỗi giữa batch trên DB lab. Quan sát commit/rollback thực tế, sửa dữ liệu và kiểm thử chạy lại. Nếu không chứng minh retry an toàn, không đưa custom task vào production.

### Bước 6. Đóng gói và release

Pin version JAR, Liquibase runtime và dependency. Chạy test bằng đúng artifact migration job hoặc Spring Boot. Review những side effect không thể hiển thị qua SQL preview.

**Tiêu chí hoàn thành:** nhóm giải thích được vì sao custom change cần thiết, chứng minh lợi ích so với SQL, có test validation/integration/failure, biết rollback/forward fix và có artifact bất biến cho CI/CD.

## 21. Checklist quyết định trước khi tạo custom change

- [ ] Đã thử change type chuẩn và các thuộc tính hỗ trợ.
- [ ] Đã đánh giá `sql`/`sqlFile` và SQL vendor-specific.
- [ ] Đã xác nhận logic thật sự cần Java hoặc sinh SQL động phức tạp.
- [ ] Đã đánh giá job backfill riêng nếu dữ liệu lớn/cần checkpoint.
- [ ] Input, output, schema, DBMS và volume được mô tả rõ.
- [ ] Custom class có validation tham số và error message hữu ích.
- [ ] Không tự commit/đóng connection do Liquibase quản lý.
- [ ] Có cơ chế idempotency/retry và kiểm tra partial effect.
- [ ] Rollback hoặc forward recovery/backup được duyệt.
- [ ] Đã xác định giới hạn của SQL preview cho custom task.
- [ ] Đã pin JAR, dependencies, Liquibase version và artifact digest.
- [ ] Không sửa class behavior của changeset lịch sử mà không tạo migration mới.
- [ ] Có unit/integration test trên DBMS tương ứng với production.
- [ ] Đã kiểm tra fresh install, upgrade path và failure giữa chừng.
- [ ] CI/CD, CLI hoặc Spring Boot đều nạp được custom class đúng version.
- [ ] Không ghi secret/dữ liệu nhạy cảm vào log.
- [ ] Đã review quyền migration, hiệu năng, thời gian giữ lock và khả năng rollback.
- [ ] Có runbook xử lý khi custom change thất bại.

**Kết luận:** chỉ dùng custom change khi change type chuẩn và SQL rõ ràng không còn đáp ứng yêu cầu, đồng thời lợi ích của logic Java hoặc khả năng sinh SQL động đủ lớn để bù chi phí bảo trì. `CustomTaskChange` phù hợp với tác vụ Java đặc thù; `CustomSqlChange` phù hợp hơn nếu mục tiêu là tạo SQL theo metadata. Trong cả hai trường hợp, cần kiểm soát transaction, retry, rollback, classpath, checksum-vs-bytecode, CI/CD và khả năng quan sát. Một extension được thiết kế tốt phải khiến migration **dễ kiểm chứng và an toàn hơn**, chứ không chỉ chuyển độ phức tạp từ changelog sang Java.

