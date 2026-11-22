# Lấy kết quả LWT qua wasApplied và các cột liên quan

> **Chương:** Truy vấn từ Java  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — học Apache Cassandra và mô hình wide-column phân tán, partition key, thiết kế bảng theo truy vấn, tính nhất quán đọc/ghi, CQL, replication, compaction, repair, xử lý lỗi và kết nối từ ứng dụng Java.

Trong Cassandra, `INSERT` thông thường có thể cập nhật một hàng đã tồn tại. Khi ứng dụng cần **chỉ tạo nếu chưa có** hoặc **chỉ cập nhật khi giá trị cũ còn đúng**, CQL cung cấp các thao tác có điều kiện như `IF NOT EXISTS`, `IF EXISTS` và `IF version = ?`. Chúng được gọi là **Lightweight Transactions (LWT)** hoặc **compare-and-set (CAS)** và sử dụng cơ chế đồng thuận Paxos.

Khác với ghi thông thường, LWT trả một hàng kết quả chứa cột boolean đặc biệt `[applied]`. Java Driver 4.x cung cấp `ResultSet.wasApplied()` (hoặc `AsyncResultSet.wasApplied()`) để đọc kết quả điều kiện. Nếu CAS không được áp dụng, response **có thể chứa các cột hiện tại của hàng** để giúp giải thích xung đột.

Ba outcome phải tách biệt:

1. **APPLIED:** LWT trả `wasApplied() == true` — điều kiện được chấp nhận và ghi được áp dụng theo mức nhất quán được yêu cầu.
2. **NOT_APPLIED:** LWT trả `wasApplied() == false` — yêu cầu đã nhận phản hồi nhưng điều kiện không thỏa. Đây là kết quả nghiệp vụ, **không phải exception**.
3. **UNKNOWN/ERROR:** Request timeout, lỗi mạng, unavailable hoặc lỗi khác — chưa có kết quả xác định; **không được suy rằng CAS không được áp dụng**.

**Phạm vi:** bài dùng Apache Cassandra Java Driver **4.x** (đối chiếu API **4.19**) và Cassandra 4.x–5.x; Driver 3.x có lớp/API khác. Các output dạng bảng là ví dụ minh họa, **không phải kết quả benchmark đã đo**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt mutation thường và các dạng LWT `INSERT IF NOT EXISTS`, `UPDATE IF ...`, `UPDATE/DELETE IF EXISTS`.
2. Dùng `ResultSet.wasApplied()` đúng ngữ nghĩa và hiểu tại sao nó **trả true cả với non-LWT**.
3. Đọc các cột được trả khi điều kiện không thỏa, sử dụng `ColumnDefinitions.contains()`, `Row.isNull()` và getter theo tên.
4. Dùng `PreparedStatement`/`BoundStatement`, đặt **regular consistency** và **serial consistency** riêng.
5. Viết code đồng bộ/bất đồng bộ, ánh xạ APPLIED, NOT_APPLIED, UNKNOWN thành kết quả nghiệp vụ đúng.
6. Hiểu giới hạn CAS theo partition; không đánh đồng LWT với giao dịch SQL nhiều partition.
7. Tạo lab có writer cạnh tranh, đo conflict rate, timeout, p95/p99 và xác minh invariants.

## 2. LWT giải quyết bài toán nào?

### 2.1. Upsert khác tạo mới có điều kiện

Ví dụ một bảng trạng thái account:

~~~sql
CREATE TABLE lwt_lab.account_state (
    account_id uuid PRIMARY KEY,
    status text,
    version int,
    owner text,
    updated_at timestamp
);
~~~

Lệnh:

~~~sql
INSERT INTO lwt_lab.account_state
    (account_id, status, version, owner)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'NEW', 1, 'worker-A'
);
~~~

là **upsert**: Cassandra không kiểm tra rằng hàng chưa tồn tại. Không có cột `[applied]` trả về như một LWT. Muốn chỉ tạo lần đầu:

~~~sql
INSERT INTO lwt_lab.account_state
    (account_id, status, version, owner)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'NEW', 1, 'worker-A'
) IF NOT EXISTS;
~~~

Nếu một writer khác đã tạo hàng, lệnh trả `[applied] = false` thay vì ghi đè.

### 2.2. UPDATE với version để chống lost update

~~~sql
UPDATE lwt_lab.account_state
SET status = 'ACTIVE',
    version = 2,
    updated_at = '2026-11-21T09:00:00Z'
WHERE account_id = 11111111-1111-4111-8111-111111111111
IF version = 1;
~~~

Lệnh có nghĩa “chỉ ghi nếu `version` còn là 1”. Nếu writer khác đã nâng version lên 2, kết quả `false` thường trả thêm **giá trị hiện tại của cột version**.

~~~mermaid
sequenceDiagram
    participant A as Writer A / Java
    participant B as Writer B / Java
    participant C as Cassandra replicas
    A->>C: UPDATE SET version=2 IF version=1
    B->>C: UPDATE SET version=2 IF version=1
    Note over C: CAS/Paxos phân xử các đề xuất
    C-->>A: [applied] true (ví dụ)
    C-->>B: [applied] false, version=2 (ví dụ)
~~~

Sơ đồ **không khẳng định A luôn thắng**. Nếu hai writers cùng dùng expectedVersion 1, CAS ngăn cả hai cùng áp dụng thay đổi trên cùng trạng thái 1 khi các request hoàn thành hợp lệ. Thực tế còn có contention và timeout phải xử lý riêng.

### 2.3. Những trường hợp dùng LWT

| Tình huống | Phù hợp không? | Giải thích |
|---|---|---|
| Chỉ tạo resource với khóa định danh duy nhất | Có thể | `IF NOT EXISTS` bảo vệ khóa đó |
| Optimistic locking của trạng thái/version | Có thể | `IF version = ?` để kiểm tra tiền điều kiện |
| Xóa chỉ khi owner còn là giá trị cũ | Có thể | `DELETE ... IF owner = ?` |
| Bulk import hàng triệu sự kiện idempotent | Thường không cần | LWT gây thêm Paxos round trips |
| Đảm bảo username không trùng khi username không là khóa | Chưa đủ | Phải thiết kế bảng khóa theo username |
| Transaction chuyển giá trị giữa hai partition bất kỳ | Không đủ | Không có ACID transaction tùy ý nhiều partition |

LWT bảo vệ một **bất biến được thiết kế theo partition**, không tự thay thế data model hay chiến lược tránh hot partition.

## 3. Kết quả [applied] và những cột được trả

### 3.1. Phản hồi có một hàng và cờ boolean

Với thao tác điều kiện đã nhận response:

~~~text
LWT thành công:
 [applied]
-----------
 True

LWT không thỏa:
 [applied] | ... các cột hiện tại có liên quan ...
-----------
 False     | ...
~~~

Không mong chờ một LWT `true` luôn trả tất cả giá trị vừa ghi. Thông thường, chỉ có cờ `[applied]`. Nếu cần đọc lại hàng đã ghi để đối chiếu, hãy làm query riêng hoặc tận dụng giá trị đã biết trong service.

### 3.2. Ma trận theo hình thức CQL

| LWT | Khi true | Khi false | Diễn giải |
|---|---|---|---|
| `INSERT ... IF NOT EXISTS` | Thường chỉ `[applied]` | Cờ và **giá trị hàng đang tồn tại** | Khóa này đã có row |
| `UPDATE ... IF version = ?` | Thường chỉ cờ | Cờ và giá trị hiện tại của **cột điều kiện** như `version` | Compare-and-set thất bại |
| `UPDATE ... IF status = ? AND version = ?` | Thường chỉ cờ | Các cột được so sánh, ví dụ `status`, `version` | Có thay đổi cạnh tranh |
| `UPDATE ... IF EXISTS` | Thường chỉ cờ | Thường **chỉ cờ** | Hàng không tồn tại |
| `DELETE ... IF EXISTS` | Thường chỉ cờ | Thường **chỉ cờ** | Không có hàng để xóa |
| `DELETE ... IF owner = ?` | Thường chỉ cờ | Cờ và giá trị hiện tại của `owner` | Điều kiện owner không thỏa |

**Quan trọng:** tập cột phụ thuộc CQL, phiên bản và schema. Không hard-code mọi LWT `false` đều trả full row. Cụ thể, `UPDATE ... IF EXISTS` false thường **không có cột `version`** để lấy.

### 3.3. Ví dụ INSERT IF NOT EXISTS bị trùng

Giả sử hàng đã có `status='NEW'`, `version=1`:

~~~text
 [applied] | account_id                            | status | version | owner
-----------+---------------------------------------+--------+---------+---------
 False     | 11111111-1111-4111-8111-111111111111  | NEW    | 1       | worker-A
~~~

Thứ tự/nhóm cột có thể khác; nếu schema có `updated_at` chưa được ghi, giá trị có thể null. Code Java phải **đọc theo tên**, không chọn `getInt(1)` vì cột vị trí thứ hai có thể là UUID.

### 3.4. Ví dụ UPDATE có điều kiện không thỏa

Nếu `version` đã là 2 nhưng yêu cầu `IF version=1`:

~~~text
 [applied] | version
-----------+---------
 False     | 2
~~~

Giá trị 2 được quan sát ở thời điểm CAS kiểm tra điều kiện; nó **không hứa sẽ còn là 2 mãi**. Writer khác có thể nâng version thành 3 ngay sau khi response được trả.

### 3.5. Có nên đọc [applied] bằng Row.getBoolean?

Có thể làm:

~~~java
ResultSet rs = session.execute(conditionalStatement);
boolean applied = rs.wasApplied(); // NÊN dùng
Row first = rs.one();              // vẫn đọc được vì wasApplied không tiêu thụ
if (first != null) {
    boolean flag = first.getBoolean("[applied]");
}
~~~

`ResultSet.wasApplied()` **không tiêu thụ row**; nó tương đương xem cờ tại hàng tiếp theo. Phương thức chuyên dụng là lựa chọn dễ đọc hơn. Tránh đặt tên cột nghiệp vụ literal `"[applied]"` vì có nguy cơ va chạm tên trong response của một số phiên bản CQL.

## 4. Cạm bẫy: wasApplied() true với non-LWT

Theo tài liệu Java Driver 4.19:

- Nếu request là LWT, `wasApplied()` phản ánh boolean `[applied]` từ server.
- Nếu request **không** là conditional write, phương thức **luôn trả true theo quy ước API**.
- Với DDL có `IF NOT EXISTS` như `CREATE TABLE IF NOT EXISTS`, Cassandra **không** trả cột `[applied]` của LWT và `wasApplied()` cũng trả true. Nó **không chứng minh** bảng mới được tạo.

~~~java
ResultSet normal = session.execute(
    "UPDATE lwt_lab.account_state SET status='NEW' " +
    "WHERE account_id=11111111-1111-4111-8111-111111111111");

// "true" ở đây KHÔNG chứng minh thao tác CAS thành công.
boolean misleading = normal.wasApplied(); // true với non-LWT
~~~

**Chỉ dùng wasApplied để ra quyết định nghiệp vụ trong code mà bạn biết chắc đã chạy INSERT/UPDATE/DELETE với IF của LWT.** Đừng áp dụng để xác định CREATE KEYSPACE/CREATE TABLE IF NOT EXISTS có tạo đối tượng mới hay không.

## 5. Lab CQL có thể chạy lặp theo từng trạng thái

### 5.1. Topology, keyspace và bảng

Thực hành trên **cluster Cassandra lab**, tên DC thật là `dc1`, có ba node và RF=3. Nếu cluster chỉ có một node, phải điều chỉnh RF/CL theo topology thay vì diễn giải mọi unavailable là lỗi LWT.

~~~bash
nodetool status
nodetool describecluster
nodetool version
~~~

Trong `cqlsh`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lwt_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lwt_lab.account_state (
    account_id uuid PRIMARY KEY,
    status text,
    version int,
    owner text,
    updated_at timestamp
);
~~~

`IF NOT EXISTS` **không chỉnh lại schema cũ** nếu keyspace/table đã tồn tại. Dùng `DESCRIBE KEYSPACE lwt_lab`, `DESCRIBE TABLE lwt_lab.account_state` để kiểm tra. Nếu muốn lặp lab từ đầu, dùng một UUID khác hoặc keyspace mới, không xóa nhầm production data.

### 5.2. INSERT IF NOT EXISTS hai lần

~~~sql
INSERT INTO lwt_lab.account_state
    (account_id, status, version, owner, updated_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'NEW', 1, 'worker-A', '2026-11-21T09:00:00Z'
) IF NOT EXISTS;
~~~

Khi chưa có hàng:

~~~text
 [applied]
-----------
 True
~~~

Chạy lại **đúng lệnh trên**:

~~~text
 [applied] | account_id | status | version | owner | updated_at
-----------+------------+--------+---------+-------+-----------
 False     | ...        | NEW    | 1       | ...   | ...
~~~

Lần hai là **CAS conflict hợp lệ**. Không log nguyên hàng hiện hữu nếu schema thật chứa dữ liệu nhạy cảm.

### 5.3. UPDATE theo version lần đầu và lặp lại

~~~sql
UPDATE lwt_lab.account_state
SET status='ACTIVE',
    version=2,
    updated_at='2026-11-21T09:05:00Z'
WHERE account_id=11111111-1111-4111-8111-111111111111
IF version=1;
~~~

Khi version còn 1, `[applied]=true`. Chạy lần hai sau khi version thành 2, `[applied]=false` và thường thêm `version=2`. Lưu ý cột `updated_at` thuộc `SET` không nhất thiết xuất hiện trong response thất bại vì nó không phải điều kiện.

### 5.4. IF EXISTS trên hàng có và không có

~~~sql
UPDATE lwt_lab.account_state
SET owner='worker-B'
WHERE account_id=11111111-1111-4111-8111-111111111111
IF EXISTS;

UPDATE lwt_lab.account_state
SET owner='worker-B'
WHERE account_id=33333333-3333-4333-8333-333333333333
IF EXISTS;
~~~

Lệnh đầu dự kiến true, lệnh sau false. Với khóa thiếu, **thường chỉ trả `[applied]`**, không có `owner` hay `version`.

### 5.5. DELETE có điều kiện

~~~sql
DELETE FROM lwt_lab.account_state
WHERE account_id=11111111-1111-4111-8111-111111111111
IF version=2;

DELETE FROM lwt_lab.account_state
WHERE account_id=11111111-1111-4111-8111-111111111111
IF EXISTS;
~~~

Không có writer khác, lệnh đầu `true`, lần xóa thứ hai `false`. **DELETE được áp dụng không đồng nghĩa dữ liệu đã bị xóa byte vật lý ngay**: tombstone, compaction và repair là cơ chế riêng.

### 5.6. Bảng kết quả mong đợi cần ghi lại

| Test | Trạng thái trước | Kết quả dự kiến | Cột liên quan |
|---|---|---|---|
| Insert mới | Chưa có hàng | True | Chỉ cờ |
| Insert trùng | Đã tồn tại | False | Các giá trị hàng hiện tại |
| Update version đúng | Version 1 | True | Chỉ cờ |
| Update version sai | Version 2 nhưng IF 1 | False | Version 2 |
| Update IF EXISTS trên khóa thiếu | Không tồn tại | False | Thường chỉ cờ |
| Delete IF version đúng | Version 2 | True | Chỉ cờ |
| Delete IF EXISTS lần hai | Đã xóa | False | Thường chỉ cờ |

Đây là **kỳ vọng có điều kiện của lab**, không phải số liệu đã được chạy trên Cassandra trong bài.

## 6. Java đồng bộ: wasApplied rồi đọc cột trả về

### 6.1. Chuẩn bị session, prepared statement và consistency

Giả định có `CqlSession session` dùng lại trong ứng dụng, đã cấu hình contact points, local DC, TLS, auth. Các ví dụ Java 4.x dùng:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;
~~~

Với LWT, hai consistency levels được đặt độc lập:

~~~java
// Fragment minh họa: ps đã được prepare với đúng số bind markers.
BoundStatement statement = ps.bind(/* các giá trị đúng thứ tự */)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);
~~~

`LOCAL_QUORUM` cho regular write phase; `LOCAL_SERIAL` cho serial/Paxos phase. Chỉ dùng khi RF/DC phù hợp. Việc đổi CL không tạo LWT nếu CQL thiếu `IF`.

### 6.2. INSERT IF NOT EXISTS: true → CREATED, false → CONFLICT

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

void createIfAbsent(CqlSession session, UUID accountId) {
    PreparedStatement ps = session.prepare(
        "INSERT INTO lwt_lab.account_state " +
        "(account_id, status, version, owner) " +
        "VALUES (?, ?, ?, ?) IF NOT EXISTS");

    BoundStatement bs = ps.bind(accountId, "NEW", 1, "worker-A")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

    ResultSet rs = session.execute(bs);
    if (rs.wasApplied()) {
        System.out.println("CREATED");
        return;
    }

    // Không thỏa vì row đã tồn tại; đọc các cột nếu thực sự có.
    Row current = rs.one();
    String currentStatus = null;
    Integer currentVersion = null;

    if (current != null) {
        if (current.getColumnDefinitions().contains("status")
                && !current.isNull("status")) {
            currentStatus = current.getString("status");
        }
        if (current.getColumnDefinitions().contains("version")
                && !current.isNull("version")) {
            currentVersion = current.getInt("version");
        }
    }

    // Thực tế: trả DTO conflict; không log payload/secret nhạy cảm.
    System.out.println("ALREADY_EXISTS; status=" + currentStatus
            + ", version=" + currentVersion);
}
~~~

Ưu điểm: `wasApplied()` không tiêu thụ hàng, nên sau đó `rs.one()` vẫn có thể đọc dữ liệu. `ColumnDefinitions.contains("version")` kiểm tra tồn tại cột; `isNull` tránh coi null là giá trị 0; `getInt`/`getString` đọc **theo tên**.

### 6.3. UPDATE IF version: lấy giá trị thực khi xung đột

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

void updateStatusIfVersion(CqlSession session, UUID accountId,
                           String nextStatus, int expectedVersion) {
    PreparedStatement ps = session.prepare(
        "UPDATE lwt_lab.account_state " +
        "SET status = ?, version = ? " +
        "WHERE account_id = ? IF version = ?");

    int nextVersion = Math.addExact(expectedVersion, 1);
    BoundStatement bs = ps.bind(
            nextStatus, nextVersion, accountId, expectedVersion)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

    ResultSet rs = session.execute(bs);
    if (rs.wasApplied()) {
        System.out.println("CAS_APPLIED; nextVersion=" + nextVersion);
        return;
    }

    Row current = rs.one();
    Integer actualVersion = null;
    if (current != null
            && current.getColumnDefinitions().contains("version")
            && !current.isNull("version")) {
        actualVersion = current.getInt("version");
    }
    System.out.println("CAS_CONFLICT; observedVersion=" + actualVersion);
}
~~~

Thứ tự bind là **status mới, version mới, accountId, expectedVersion**. `actualVersion` chỉ là giá trị tại thời điểm CAS thất bại, có thể đổi tiếp. `null` nghĩa là không có giá trị số tin cậy trong response; không chuyển thành 0.

### 6.4. IF EXISTS false: không truy cập cột version vô điều kiện

~~~java
PreparedStatement ps = session.prepare(
    "UPDATE lwt_lab.account_state SET owner = ? " +
    "WHERE account_id = ? IF EXISTS");

ResultSet rs = session.execute(ps.bind("worker-B", accountId));
if (!rs.wasApplied()) {
    // Thường chỉ có [applied], KHÔNG bảo đảm version tồn tại.
    System.out.println("NOT_FOUND");
}
~~~

Ví dụ rút gọn dùng consistency defaults của execution profile; trong code production nên bảo đảm regular/serial CL được cấu hình tường minh theo policy.

## 7. Cột phản hồi thay đổi: tránh lỗi null và missing field

### 7.1. Phân biệt missing column với NULL

Một hàm dùng chung có thể thấy:

~~~text
INSERT ... IF NOT EXISTS, false       -> có thể có status/version/owner
UPDATE ... IF version = ?, false     -> thường có version
UPDATE ... IF EXISTS, false         -> thường chỉ có [applied]
~~~

Nếu luôn gọi `rs.one().getInt("version")`, nhánh IF EXISTS false có thể ném exception vì cột đó **không thuộc result schema**. Nếu có cột nhưng giá trị null, vẫn không nên gán thành version 0.

### 7.2. Hàm tiện ích Java trả Optional

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.Optional;

Optional<Integer> optionalInt(Row row, String column) {
    if (row == null
            || !row.getColumnDefinitions().contains(column)
            || row.isNull(column)) {
        return Optional.empty();
    }
    return Optional.of(row.getInt(column));
}
~~~

`Optional.empty()` chỉ có nghĩa **response không có một giá trị số để dùng**, không phải actualVersion = 0 hoặc không có hàng ở Cassandra.

### 7.3. Cột [applied] là response metadata, không phải schema data

`[applied]` là cột **tổng hợp trong kết quả của thao tác điều kiện**. Nó không phải một cột persistent trong bảng `account_state`. Không thiết kế `SELECT "[applied]" FROM ...` với kỳ vọng lấy trạng thái giao dịch đã xảy ra.

### 7.4. False + version trả về không thể thay thế CAS kế tiếp

Nếu một writer khác đã nâng version từ 2 lên 3 sau response, việc UPDATE **không có IF** dựa trên version 2 sẽ ghi đè trạng thái mới. Khi retry:

1. Xác định ngữ nghĩa nghiệp vụ có cho phép thử lại không.
2. Recompute đề xuất từ trạng thái mới hoặc chọn cách trả conflict.
3. Thực hiện **một CAS khác**, không bỏ điều kiện.
4. Giới hạn retry count, áp backoff và theo dõi contention.

## 8. Java bất đồng bộ: AsyncResultSet.wasApplied()

### 8.1. Không chặn luồng xử lý yêu cầu

Java Driver 4.x cung cấp `CqlSession.executeAsync(statement)` trả `CompletionStage<AsyncResultSet>`. Khi có phản hồi, `AsyncResultSet.wasApplied()` đọc cùng cờ LWT; có thể xem row từ trang hiện tại:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

CompletionStage<String> createIfAbsentAsync(
        CqlSession session, UUID accountId) {
    PreparedStatement ps = session.prepare(
        "INSERT INTO lwt_lab.account_state " +
        "(account_id, status, version, owner) " +
        "VALUES (?, ?, ?, ?) IF NOT EXISTS");

    BoundStatement bs = ps.bind(accountId, "NEW", 1, "worker-A")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

    return session.executeAsync(bs).thenApply(rs -> {
        if (rs.wasApplied()) {
            return "CREATED";
        }
        Row current = rs.one();
        if (current != null
                && current.getColumnDefinitions().contains("version")
                && !current.isNull("version")) {
            return "CONFLICT_VERSION_" + current.getInt("version");
        }
        return "CONFLICT";
    });
}
~~~

Một LWT đơn thường có **một hàng phản hồi** nên không cần `fetchNextPage()` để lấy hàng triệu page. `wasApplied()` **không tiêu thụ** hàng; `one()` cho row hiện tại. Trong callback `thenApply`, không chạy blocking query, không gọi `Thread.sleep`, không xử lý CPU quá nặng trên thread completion của driver.

### 8.2. Completion exceptional không phải CAS false

~~~text
CompletionStage hoàn thành bình thường:
    rs.wasApplied() == true  -> APPLIED
    rs.wasApplied() == false -> NOT_APPLIED / CAS_CONFLICT

CompletionStage hoàn thành exceptional:
    timeout / unavailable / connection / invalid query / ...
    -> phân loại ERROR hoặc UNKNOWN, không tự coi là false
~~~

**Phản ví dụ sai:**

~~~java
// KHÔNG làm như vậy:
// return session.executeAsync(bs)
//     .exceptionally(error -> fakeNotAppliedResult);
~~~

Đoạn code trên đang biến **lỗi request** thành **false vì điều kiện**. Nếu server commit nhưng client mất phản hồi, xử lý sai này có thể dẫn tới tạo lại resource, gửi sự kiện sai hoặc xóa nhầm dữ liệu. Hãy giữ exception trong nhánh riêng, gắn correlation/request ID và thực hiện reconciliation theo nghiệp vụ.

### 8.3. Mapper và Spring Data trả gì?

Java Driver Mapper 4.x hỗ trợ DAO trả `boolean`/`Boolean` từ một method `@Update(ifExists = true)`; driver ánh xạ nó tới `ResultSet.wasApplied()`. Nếu cần đọc các cột điều kiện khi false, có thể chọn return type `ResultSet`/`AsyncResultSet` qua API Mapper phù hợp, thay vì chỉ trả boolean.

~~~java
// Ý tưởng từ API Apache Java Driver Mapper @Update:
// @Update(ifExists = true)
// boolean updateIfExists(MyEntity row);
//
// @Update(customIfClause = "status = :expectedStatus")
// ResultSet updateIfStatusMatches(MyEntity row, String expectedStatus);
~~~

Đây là **phác thảo annotation**, không phải interface có thể biên dịch nguyên trạng: cần entity/DAO annotations và mapping cụ thể. Với Spring Data Cassandra, framework/repository method có thể đã biến đổi result. Nếu ứng dụng cần `[applied]` và current values, thiết kế return DTO/outcome rõ hoặc dùng Java Driver trực tiếp cho CAS quan trọng.

## 9. Regular consistency và serial consistency

### 9.1. Hai pha nhất quán

LWT sử dụng Paxos cho **pha điều kiện/serial**; regular consistency điều khiển mức ACK của ghi dữ liệu theo cơ chế Cassandra. Driver 4.x có hai thuộc tính riêng:

~~~java
BoundStatement bs = ps.bind(/* đúng các bind markers */)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
~~~

| Thuộc tính | Tác dụng | Không được hiểu nhầm |
|---|---|---|
| `LOCAL_SERIAL` | Quorum/pha serial **cục bộ trong DC** liên quan | Không đồng nghĩa `SERIAL` trên multi-DC |
| `SERIAL` | Pha serial/Paxos với phạm vi replica rộng hơn theo topology | Không cung cấp transaction tùy ý nhiều partition |
| `LOCAL_QUORUM` | Điều kiện phản hồi cho regular write tại DC local | Không tạo CAS khi câu lệnh không có `IF` |
| `QUORUM` | Quorum theo RF/replica placement phù hợp | Không phải cách khác để viết `SERIAL` |

Với cluster đa DC và invariant phải được giữ **toàn cụm** (hai region có thể cùng sửa một key), cần phân tích kỹ lựa chọn `SERIAL` hoặc `LOCAL_SERIAL`, cách ứng dụng route vào DC và failure modes. Không chọn LOCAL_SERIAL chỉ vì RTT thấp hơn mà bỏ qua yêu cầu duy nhất toàn hệ thống.

### 9.2. LWT hoạt động ở đơn vị nào?

LWT/Paxos của Cassandra được tổ chức quanh **partition**. Nó phù hợp để bảo vệ một key/partition mà ứng dụng đã thiết kế. Nó **không tự tạo**:

- Referential integrity giữa hai bảng khác partition.
- Unique constraint tùy ý trên một cột không phải partition key.
- ACID transfer cross-partition như transaction SQL.
- Atomic publish sang Kafka/email/payment provider.

Ví dụ, muốn giới hạn mỗi username chỉ đăng ký một lần, tạo **bảng registry khóa theo username**:

~~~sql
CREATE TABLE lwt_lab.username_registry (
    username text PRIMARY KEY,
    account_id uuid
);

INSERT INTO lwt_lab.username_registry (username, account_id)
VALUES ('alice', 11111111-1111-4111-8111-111111111111)
IF NOT EXISTS;
~~~

CAS ngăn tranh cùng `username='alice'` trong bảng này. Nhưng tạo hàng `account_state` ở **partition khác** là một bước riêng, cần workflow/idempotency/reconciliation hoặc outbox/saga nếu có sự cố giữa chừng.

### 9.3. Vì sao chỉ QUORUM vẫn có lost update?

Hai writer đọc `version=1` rồi gửi hai UPDATE **không có IF** ở `QUORUM` có thể cùng nhận ACK, và giá trị cuối cùng phụ thuộc giải quyết timestamp. CL cao **không** kiểm tra version cũ. Muốn CAS phải giữ câu `IF version = ?` và serial consistency phù hợp.

## 10. Xử lý APPLIED, NOT_APPLIED và UNKNOWN trong service

### 10.1. Ánh xạ có ý nghĩa nghiệp vụ

| Outcome | Điều kiện | API có thể phản hồi |
|---|---|---|
| **APPLIED** | LWT trả `true` | 201 Created/200 OK/204 tùy thao tác |
| **NOT_APPLIED** | LWT trả `false` | 409 Conflict, 412 Precondition Failed, hoặc 404 với IF EXISTS |
| **UNKNOWN/ERROR** | Request timeout/lỗi không có cờ LWT xác định | 503/504/retry/reconcile có kiểm soát |

Các status HTTP là **gợi ý**, không phải chuẩn bắt buộc. Điều quan trọng là **CAS false là phản hồi hợp lệ**, còn timeout là một loại lỗi cần xác minh thêm.

### 10.2. Nếu wasApplied false: nên làm gì?

1. Kiểm tra câu lệnh thực sự là `INSERT IF NOT EXISTS`, `UPDATE IF ...` hay `IF EXISTS`.
2. Đọc **những cột thực sự xuất hiện** trong result. Không giả định full row.
3. Có thể trả `currentVersion`, `currentStatus` nếu hợp đồng API cho phép, nhưng tránh lộ owner/secrets của user khác.
4. Nếu cần retry vì version đổi, tính lại proposal và dùng CAS mới; có giới hạn attempt, backoff.
5. Nếu việc “đã ở trạng thái mong muốn” được định nghĩa là thành công idempotent, phải đối chiếu business identity/request ID phù hợp trước khi trả success.

### 10.3. Timeout có thể xảy ra sau khi mutation được áp dụng

~~~text
Java -> Cassandra: UPDATE SET version=8 IF version=7
Paxos/replicas đã xử lý request ở một mức nào đó
Network bị ngắt trước khi response về client
Java nhận timeout, không biết outcome chắc chắn

Retry y nguyên:
   Có thể nhận false, version=8
   dù chính request đầu đã nâng version từ 7 lên 8.
~~~

Vì vậy, **không được coi timeout là rollback hoặc CAS false**. Nếu operation quan trọng:

- Gắn idempotency key, operation ID hoặc marker nghiệp vụ được lưu trong phạm vi nhất quán phù hợp.
- Sau unknown outcome, đọc lại trạng thái ở CL thích hợp rồi **reconcile**, không tự động bắn lại side effect.
- Không bật `setIdempotence(true)` trên tất cả CAS một cách máy móc. Một câu CAS có thể idempotent về trạng thái mong muốn nhưng **kết quả wasApplied của hai lần chạy khác nhau**, cùng với các side effects của API.
- Dùng retry budget, deadline, backoff, telemetry, phân biệt quá tải với xung đột nghiệp vụ.

### 10.4. CAS true không biến side effect ngoài Cassandra thành atomic

Ví dụ:

~~~text
CAS true
  -> service gọi hệ thống gửi email hoặc thanh toán
  -> service crash trước khi ghi trạng thái hoàn tất
  -> replay request: CAS có thể false
~~~

Không thể chỉ nhìn `wasApplied=false` ở lượt replay mà kết luận email/payment trước đó chưa được thực hiện. Cần **outbox phù hợp, idempotent consumer, operation IDs, saga hoặc bù trừ** tùy nghiệp vụ. Cassandra không tạo một transaction chung với hệ thống bên ngoài.

## 11. Hiệu năng LWT, hot key và observability

### 11.1. Paxos có chi phí

So với mutation không điều kiện, CAS cần các bước kiểm tra/đồng thuận bổ sung, bị ảnh hưởng bởi quorum availability, network RTT và contention ở cùng partition. Không dùng `IF NOT EXISTS` cho mọi bulk import chỉ vì “an toàn hơn”.

| Mẫu tải | Nguy cơ | Hướng xử lý |
|---|---|---|
| Vài CAS mỗi phút, ít tranh chấp | Chi phí thường có thể chấp nhận | Chuẩn bị statement và đo SLO thực |
| Nhiều writer tranh một partition | Contention, CAS false và p99 tăng | Queue per key, giới hạn writers, đổi workflow |
| Writers ở nhiều DC | RTT serial cao, race theo topology | Thiết kế locality và chọn serial CL có chủ đích |
| CAS trả full existing row rộng | Network, privacy và memory overhead | Dùng registry nhỏ, version/status tối thiểu |
| Vòng retry vô hạn | Thêm áp lực Paxos trên node nghẽn | Retry budget, backoff, idempotency/reconcile |

Một hot partition vẫn hot dù LWT “đúng”. Dùng token-aware routing giúp tránh coordinator hop, nhưng không tự tăng số replica cho một key.

### 11.2. Quan sát trên cluster và ứng dụng

Trong cluster lab:

~~~bash
nodetool status
nodetool tablestats lwt_lab.account_state
nodetool tpstats
nodetool compactionstats
~~~

Kết hợp các metric Cassandra liên quan CAS/Paxos contention, prepare/propose latency, read/write latency, errors và request latency. **Tên JMX/exporter thay đổi theo bản Cassandra**; cần xác nhận metric thực thay vì suy mọi tên luôn hiện diện.

Ứng dụng Java cần ghi:

- Số `APPLIED`, `NOT_APPLIED`, `UNKNOWN/TIMEOUT` tách theo query type.
- CAS latency p50/p95/p99 và total request time, không trộn với SELECT không điều kiện.
- Retry count, contention, coordinator/replica errors, TLS/network failures.
- Số hot keys/rate limit theo label đã **ẩn danh**, không log account ID hoặc current row nhạy cảm.
- CPU/network/disk/compaction/repair và số replica Up/Down ở DC dùng cho CL.

CAS false do version mismatch bình thường **không mặc nhiên là lỗi hạ tầng**; nhưng tỷ lệ conflict tăng bất ngờ có thể là dấu hiệu nhiều writer tranh nhau, bug versioning hoặc hotspot.

## 12. Ma trận kiểm thử và lab hai writer

### 12.1. Kiểm thử chức năng

| Case | Trạng thái ban đầu | Outcome mong đợi | Phần phải xác minh |
|---|---|---|---|
| Insert lần đầu | Khóa trống | True | Không giả định có full row |
| Insert trùng | Đã có row | False | Đọc được cột tồn tại nếu có |
| Update version đúng | Version 1 | True | Không kỳ vọng version mới trong result |
| Update version cũ | Version 2, IF 1 | False | Version 2 ở cột điều kiện |
| UPDATE IF EXISTS trên khóa thiếu | Không có row | False | Thường không có version |
| DELETE IF owner mismatch | Owner khác | False | Có thể có owner |
| Mutation không IF | Non-LWT | `wasApplied() == true` theo API | Không có cột [applied] LWT |
| DDL IF NOT EXISTS lặp | Bảng đã tồn tại | `wasApplied() == true` theo API | Không chứng minh tạo mới |
| Timeout sau possible commit | Mất response | Exception/unknown | Không suy thành false |

### 12.2. Thử hai writer cạnh tranh

Trên cluster lab RF/CL hợp lệ:

1. Khởi tạo hàng với `version=1`.
2. Hai thread/service gửi cùng `UPDATE ... IF version=1`, mỗi thread muốn đặt `status` khác nhau.
3. Dùng barrier hoặc điều phối cho hai request gần đồng thời; ghi `wasApplied`, exception, latency.
4. Nếu hai phản hồi đều hợp lệ, kỳ vọng không có hai CAS cùng áp dụng trên trạng thái version 1.
5. Đọc lại version/trạng thái cuối ở CL phù hợp. Nếu một request timeout, đánh dấu outcome **unknown** và xác minh lại.
6. Lặp lại nhiều lần trên **khóa mới hoặc reset có kiểm soát**, không dùng một lần để khẳng định p99.

### 12.3. Benchmark có đối chứng

| Biến | Các mức gợi ý | Lý do |
|---|---|---|
| Writers/key | 1, 2, 8, 32 tùy capacity lab | Tách hot-key contention |
| Số partitions | Một hot key; hàng nghìn keys độc lập | So skew và khả năng scale |
| CL | Giữ nhất quán regular/serial CL trong mỗi nhóm | Tránh so hai loại quorum khác nhau |
| Data model | Row nhỏ; thử row rộng riêng | LWT false có thể trả thêm row |
| Kết quả | True/False/Unknown, p95/p99, errors | Tính đúng và hiệu năng phải cùng đạt |
| Nhiễu | GC, streaming, repair, compaction | Không kết luận chỉ từ một mẫu |

Không chèn số liệu tưởng tượng; điền từ lab:

| Writers/key | APPLIED/s | NOT_APPLIED/s | UNKNOWN/s | p95 (ms) | p99 (ms) | CPU/network |
|---|---:|---:|---:|---:|---:|---|
| 1 | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ |
| 2 | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ |
| 8 | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ |
| 32 | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ | _điền_ |

## 13. Những ngộ nhận phổ biến

| Ngộ nhận | Vì sao sai | Cách làm đúng |
|---|---|---|
| “wasApplied true luôn nghĩa mới INSERT thành công” | Non-LWT/DDL IF NOT EXISTS cũng trả true theo API | Chỉ dùng trên result của conditional DML |
| “wasApplied false là exception cần retry ngay” | Đây là CAS conflict bình thường | Trả conflict hoặc retry có điều kiện |
| “Timeout = false” | Mutation có thể đã commit nhưng mất ACK | UNKNOWN và reconcile |
| “Mọi LWT false trả đầy đủ hàng” | IF version chỉ trả cột điều kiện; IF EXISTS thường chỉ cờ | Dùng ColumnDefinitions.contains |
| “Cột [applied] là cột của bảng” | Cột tổng hợp response | Không ánh xạ vào schema persistent |
| “getInt(version) dùng mọi lúc” | Cột có thể thiếu hoặc null | Kiểm tra tồn tại và null trước |
| “Version trả ở CAS false luôn là mới nhất” | Writer khác có thể thay ngay sau response | Dùng CAS mới, không update vô điều kiện |
| “QUORUM tự chống lost update” | Write CL không so phiên bản | Sử dụng IF version = ? khi cần |
| “LOCAL_SERIAL = SERIAL trên mọi DC” | Phạm vi serial khác nhau | Thiết kế theo invariant xuyên DC |
| “LWT là ACID giao dịch trên mọi partition” | Phạm vi chủ yếu theo partition | Registry, outbox/saga/reconcile |
| “PreparedStatement tự tạo atomic workflow nhiều bảng” | Prepared chỉ hỗ trợ bind/parse/routing | Thiết kế transaction boundary riêng |
| “Cứ dùng LWT cho mọi lệnh ghi sẽ tốt hơn” | Paxos có chi phí và contention | Chỉ áp dụng khi cần bất biến |

## 14. Câu hỏi vận dụng

**Bài 1 — Non-LWT:** Gọi `UPDATE` không `IF` rồi `wasApplied()` trả true. Có thể nói “CAS thành công” không?

**Đáp án:** không. True là hành vi mặc định của API đối với non-LWT, không có kiểm tra điều kiện.

**Bài 2 — Version conflict:** `UPDATE ... IF version=3` thất bại, response có `version=4`. Nên làm gì?

**Đáp án:** báo optimistic concurrency conflict, có thể cung cấp currentVersion=4 nếu phù hợp. Không ghi đè vô điều kiện. Retry cần tính lại trên trạng thái mới.

**Bài 3 — IF EXISTS:** Câu lệnh `UPDATE ... IF EXISTS` trả false; code `rs.one().getInt("version")` gây lỗi. Vì sao?

**Đáp án:** không có hàng nên kết quả thường chỉ có `[applied]`, thiếu cột `version`.

**Bài 4 — Request lặp:** `INSERT ... IF NOT EXISTS` trả true lần đầu và false lần hai. Đây là lỗi mạng?

**Đáp án:** không, đó là kết quả điều kiện không thỏa. Nếu request lặp sau timeout cần xét request ID và business state để xác nhận thao tác trước đã hoàn tất chưa.

**Bài 5 — Timeout:** Client gửi CAS nâng version 7→8, response mất; retry nhận false/version 8. Có chắc request đầu thất bại?

**Đáp án:** không. Request đầu có thể đã commit; phải reconcile.

**Bài 6 — Unique username:** `accounts_by_id(id PRIMARY KEY, username)` có `INSERT ... IF NOT EXISTS`. Hai id khác nhau có thể cùng username không?

**Đáp án:** có. Điều kiện kiểm tra theo id, không tự có unique index trên username. Dùng bảng registry khóa theo username và workflow có bù trừ.

**Bài 7 — Async exception:** `exceptionally(error -> "CONFLICT")` có phù hợp khi Cassandra mất quorum?

**Đáp án:** không. Mất quorum/timeout không phải CAS false; phân loại exception thành error/unknown.

**Bài 8 — Serial CL:** Developer dùng `setConsistencyLevel(LOCAL_QUORUM)` nhưng không đặt `IF version=?`. Có tự chống lost update không?

**Đáp án:** không. Regular CL không thực hiện compare-and-set; cần câu lệnh điều kiện và serial CL phù hợp.

### Checklist hoàn thành

- [ ] Hiểu INSERT/UPDATE không IF là mutation thường và không có kết quả [applied] LWT.
- [ ] Gọi `ResultSet.wasApplied()`/`AsyncResultSet.wasApplied()` đúng trên LWT.
- [ ] Biết non-LWT và conditional DDL trả wasApplied=true theo quy ước API.
- [ ] Phân biệt APPLIED, NOT_APPLIED, UNKNOWN/ERROR.
- [ ] Biết INSERT IF NOT EXISTS false có thể trả hàng hiện có.
- [ ] Biết UPDATE IF column false có thể trả cột so sánh; IF EXISTS false thường chỉ cờ.
- [ ] Dùng `ColumnDefinitions.contains()` và `Row.isNull()` trước khi đọc primitive.
- [ ] Bind prepared statements đúng thứ tự, dùng CqlSession dài hạn.
- [ ] Đặt regular/serial consistency phù hợp RF/DC và invariant.
- [ ] Không coi LWT là giao dịch ACID tùy ý cross-partition.
- [ ] Có retry budget, backoff, idempotency/reconciliation cho unknown outcome.
- [ ] Đo conflict rate, timeout, p95/p99 và tài nguyên trên cluster thực.

## 15. Tài liệu tham khảo

1. Apache Cassandra — [CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT IF NOT EXISTS`, `UPDATE IF`, `DELETE IF` và chi phí Paxos.
2. Apache Cassandra Java Driver 4.19 — [ResultSet API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/ResultSet.html): `wasApplied()`, non-LWT behavior và việc không tiêu thụ hàng.
3. Apache Cassandra Java Driver 4.19 — [AsyncResultSet API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/AsyncResultSet.html): phản hồi CAS bất đồng bộ.
4. Apache Cassandra Java Driver 4.19 — [ColumnDefinitions API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/ColumnDefinitions.html): `contains()` và kiểm tra metadata cột.
5. Apache Cassandra Java Driver 4.19 — [Statement API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/Statement.html): `setConsistencyLevel`, `setSerialConsistencyLevel` và các execution attributes.
6. Apache Cassandra Java Driver 4.19 — [Mapper @Update API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/mapper/annotations/Update.html): boolean return qua `wasApplied` hoặc raw result để đọc cột điều kiện.
7. Apache Cassandra source docs — [Paxos/LWT design](https://github.com/apache/cassandra/blob/trunk/src/java/org/apache/cassandra/service/paxos/Paxos.md): đồng thuận và cạnh tranh giữa coordinators.
8. DataStax CQL Reference — [INSERT IF NOT EXISTS response](https://docs.datastax.com/en/cql-oss/3.x/cql/cql_reference/cqlInsert.html): false có thể trả giá trị của hàng hiện có.

