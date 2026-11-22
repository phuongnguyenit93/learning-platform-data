# Cập nhật theo khóa để tránh sửa nhầm nhiều hàng trong Spring JDBC

> **Mục tiêu:** Viết và rà soát lệnh `UPDATE` chỉ tác động **đúng bản ghi được xác định bằng khóa**; kết hợp `WHERE`, tham số hóa bằng `JdbcTemplate`, khóa chính/khóa ghép, kiểm tra số hàng ảnh hưởng và optimistic locking. Hiểu vì sao `UPDATE` không có điều kiện hoặc dùng điều kiện không duy nhất có thể làm thay đổi dữ liệu hàng loạt, cũng như cách bảo vệ ứng dụng khi có nhiều người cập nhật đồng thời.

**Ngữ cảnh:** Spring Framework → Data Access → **Cập nhật và khóa sinh**. Bài này tập trung vào cập nhật bản ghi *đã tồn tại* bằng khóa; việc lấy khóa sinh sau `INSERT` được nhắc để phân biệt nhưng không thay thế nội dung chính. Ví dụ thực hành dùng Java 17+, Spring Boot 3.5.16, Spring JDBC và H2.

## 1. Vì sao UPDATE không có khóa là thao tác nguy hiểm?

Câu lệnh SQL `UPDATE` áp dụng cho **mọi hàng thỏa điều kiện `WHERE`**. Nếu bỏ `WHERE`, phạm vi thông thường là toàn bảng. Nếu điều kiện không duy nhất, có thể có 2, 20 hoặc hàng triệu bản ghi trùng điều kiện.

Giả sử bảng `documents` có ba hàng:

| tenant_id | id | title | version |
| --- | ---: | --- | ---: |
| tenant-a | 101 | Draft | 0 |
| tenant-a | 102 | Second | 0 |
| tenant-b | 101 | Other | 0 |

**Lệnh nguy hiểm:**

```sql
-- SAI: không có WHERE; toàn bộ documents có thể bị đổi title.
UPDATE documents SET title = 'Reviewed';

-- SAI: tenant_id là điều kiện lọc rộng, chưa nhận diện một document.
UPDATE documents SET title = 'Reviewed'
WHERE tenant_id = 'tenant-a';

-- SAI trong ví dụ này: id trùng giữa hai tenant.
UPDATE documents SET title = 'Reviewed'
WHERE id = 101;
```

**Lệnh đúng với khóa ghép đã ràng buộc ở database:**

```sql
UPDATE documents
SET title = ?
WHERE tenant_id = ? AND id = ?;
```

Ở schema ví dụ, `PRIMARY KEY (tenant_id, id)` bảo đảm tối đa một hàng trùng **cả hai** thành phần. Với lệnh đầy đủ, database xác định đúng document trong đúng tenant.

Điều quan trọng không chỉ là “thêm một `WHERE`”; mà là **`WHERE` có tính duy nhất được database bảo đảm và đủ phạm vi bảo mật**.

## 2. Khóa nào đủ để xác định duy nhất một hàng?

Các dạng khóa thường gặp:

| Loại khóa | Ví dụ điều kiện | Có bảo đảm tối đa một hàng? | Lưu ý |
| --- | --- | --- | --- |
| Khóa chính một cột | `WHERE id = ?` | Có, khi `id` là `PRIMARY KEY` của bảng | Không bỏ qua kiểm soát quyền truy cập |
| Khóa chính ghép | `WHERE tenant_id = ? AND id = ?` | Có, khi chính cặp đó là `PRIMARY KEY` | Bắt buộc đủ mọi thành phần |
| Unique key / unique index | `WHERE external_code = ?` | Có nếu DB thực sự enforce uniqueness phù hợp | Chú ý NULL/collation/partial unique |
| Khóa tự nhiên không có constraint | `WHERE email = ?` | **Không có bảo đảm** | Có thể trùng, đổi email, normalize khác nhau |
| Trạng thái/nhóm | `WHERE status = 'PENDING'` | Không | Đây là filter cho bulk operation |
| Chỉ tenant | `WHERE tenant_id = ?` | Không | Thường có nhiều bản ghi cùng tenant |

**Hãy kiểm tra DDL/migration**, không chỉ tên trường Java. Cột tên `id` không tự chứng minh nó là primary key; một UUID hoặc business code không tự có uniqueness nếu chưa khai báo constraint phù hợp.

Các hướng thiết kế phổ biến:

- Bảng một tenant hoặc key globally unique: `id BIGINT PRIMARY KEY`; `WHERE id = ?` là điểm bắt đầu tốt.
- Bảng multi-tenant: `PRIMARY KEY (tenant_id, id)` hoặc `UNIQUE (tenant_id, business_key)`; `WHERE` dùng đủ khóa, với tenant lấy từ security context được xác thực.
- Business key thay đổi theo thời gian: ưu tiên technical stable key cho `UPDATE`, giữ business key có unique constraint riêng nếu cần.
- Khóa composite gồm nhiều cột: không bỏ sót một cột chỉ vì dữ liệu test hiện tại “chưa có hàng trùng”.

**Không thay điều kiện chính xác bằng `LIMIT 1` một cách tùy tiện.** Một số database không hỗ trợ cú pháp `UPDATE ... LIMIT`; ngay cả nơi hỗ trợ, việc chọn ngẫu nhiên một hàng trong nhiều hàng trùng chỉ che lỗi mô hình dữ liệu.

## 3. Quy tắc vàng: UPDATE có khóa + bind tham số + kiểm tra row count

Một mẫu Spring JDBC dùng `JdbcTemplate`:

```java
// Snippet trong DAO đã inject JdbcTemplate jdbc.
public void rename(long id, String title) {
    int changed = jdbc.update(
        "UPDATE documents SET title = ? WHERE id = ?",
        title, id);

    if (changed != 1) {
        throw new IllegalStateException(
            "Expected one updated row, got " + changed);
    }
}
```

Đây là **snippet minh họa** dành cho bảng có `id` duy nhất trong schema. Đoạn này **chưa đủ để bảo đảm rollback nếu code không nằm trong transaction**; mục 7 sẽ phân tích.

Ý nghĩa ba hành động:

1. `WHERE id = ?` tạo phạm vi theo khóa được DB bảo đảm.
2. `jdbc.update(sql, title, id)` bind riêng dữ liệu, tránh nối input và lỗi SQL injection. Thứ tự argument phải theo thứ tự dấu `?`: **title trước, id sau**.
3. Giá trị `changed` của `JdbcTemplate.update` là số hàng được JDBC driver báo tác động. Một UPDATE theo primary key đúng nghĩa phải có **tối đa một hàng khớp**; cần xử lý khác nhau khi count là 0, 1 hoặc bất thường.

**Một điểm rất quan trọng:** việc **kiểm tra count sau UPDATE không thay thế `WHERE` duy nhất và transaction**. Nếu `WHERE` quá rộng, statement có thể đã cập nhật nhiều hàng **trước khi** Java nhìn thấy `changed > 1`. Nếu hoạt động ở auto-commit, thay đổi có thể đã commit, không thể hoàn tác chỉ bằng cách ném exception sau đó.

## 4. Đọc đúng số hàng bị ảnh hưởng

`JdbcTemplate.update(...)` và `PreparedStatement.executeUpdate()` trả về `int` số hàng ảnh hưởng theo quy tắc JDBC/driver. Trong ca cập nhật theo khóa:

| Số hàng (`int changed`) | Cách hiểu ban đầu | Phản ứng thường phù hợp |
| ---: | --- | --- |
| `0` | Không có hàng thỏa predicate; có thể không tồn tại, sai tenant, hoặc version cũ | Trả 404/409 hoặc lỗi domain theo contract; không báo thành công giả |
| `1` | Có một hàng được driver báo tác động | Có thể coi thành công với schema/predicate và semantics DB đúng |
| `> 1` | Predicate hoặc dữ liệu không thỏa invariant “một hàng” | Báo lỗi nghiêm trọng, rollback transaction, điều tra điều kiện khóa/DDL |
| SQL ném exception | Constraint, type, deadlock, connection, permission… | Để Spring chuyển thành `DataAccessException`, quyết định retry/rollback theo loại lỗi |

**Ngoại lệ về driver:** số đếm “affected/matched/changed rows” có thể khác giữa hệ cơ sở dữ liệu, chế độ driver, đặc biệt khi set lại **cùng giá trị cũ**, trigger hoặc view. Nếu cần phân biệt “hàng có tồn tại” với “giá trị thực sự thay đổi”, đừng áp một quy tắc chung cho mọi DB; hãy xem JDBC driver và dialect đang chạy, viết integration test.

Với optimistic locking (`WHERE version = ?`), `0` đặc biệt quan trọng: nó có thể báo **ghi đè cạnh tranh đã bị ngăn**, nhưng bản thân count không phân biệt “hàng đã bị xóa” với “version không còn đúng”. Việc ánh xạ thành HTTP 404/409 phải theo mô hình nghiệp vụ.

### Cách phân loại kết quả trong service

```java
int count = repository.renameIfVersion(tenantId, id,
                                       expectedVersion, newTitle);

if (count == 1) {
    return; // Thành công.
}
if (count == 0) {
    throw new IllegalStateException(
        "Document missing or version changed");
}
throw new IllegalStateException(
    "Invariant violation: updated " + count + " rows");
```

Đây là snippet minh họa, không phải file chạy độc lập. Với contract yêu cầu 0 không phải lỗi, có thể trả enum `UPDATED / NO_MATCH` thay vì ném exception, miễn caller hiểu rõ ý nghĩa.

## 5. Cách viết WHERE an toàn cho bảng đơn và nhiều tenant

### Bảng khóa chính đơn

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
```

```java
// Snippet: jdbc là JdbcTemplate đã inject; id và name hợp lệ.
int rows = jdbc.update(
    "UPDATE products SET name = ? WHERE id = ?",
    name, id);
```

Do `id` là primary key, một query không thể khớp hai sản phẩm khác nhau theo `id`. Thêm điều kiện phụ như `AND status = 'ACTIVE'` là hợp lý nếu chỉ cho phép sửa item active, nhưng khi count bằng 0 cần nhận thức có thể do trạng thái bị từ chối, không chỉ “không có id”.

### Bảng khóa chính ghép

```sql
CREATE TABLE documents (
    tenant_id VARCHAR(32) NOT NULL,
    id BIGINT NOT NULL,
    title VARCHAR(120) NOT NULL,
    version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, id)
);
```

```java
int rows = jdbc.update(
    "UPDATE documents SET title = ? " +
    "WHERE tenant_id = ? AND id = ?",
    title, tenantId, id);
```

DB đảm bảo cặp tenant/id duy nhất. **Tuy nhiên, `tenantId` phải lấy từ ngữ cảnh quyền truy cập được tin cậy**, không đơn giản nhận bất kỳ tenant ID nào do client tự khai. Có thể kết hợp DB row-level security nếu hệ thống/DB hỗ trợ, nhưng không thay thế kiểm tra authentication/authorization.

### Khóa có giá trị NULL

Khóa chính không NULL. Nếu dùng cột nullable làm điều kiện, SQL `WHERE nullable_col = NULL` không bao giờ là so sánh đúng theo SQL three-valued logic; cần `IS NULL` hoặc phép so sánh null-safe theo dialect. Thiết kế khóa duy nhất thông thường tránh dùng nullable key một cách mơ hồ.

### Khi dùng soft delete

Đặt thêm trạng thái:

```sql
UPDATE documents
SET title = ?
WHERE tenant_id = ? AND id = ? AND deleted_at IS NULL;
```

Nếu `changed=0`, có thể document không tồn tại, đã soft-delete hoặc tenant không đúng. Tránh tự động chạy lại không có `deleted_at IS NULL` chỉ để đạt count 1, vì như vậy có thể sửa record đã bị xóa về mặt nghiệp vụ.

## 6. Optimistic locking: khóa đúng bản ghi vẫn có thể ghi đè dữ liệu mới

Khóa chính giải quyết **“sửa nhầm nhiều bản ghi”**, nhưng chưa giải quyết **“hai request cùng sửa một bản ghi”**.

Ví dụ:

```text
T0: document (tenant-a, 101) = title "Draft", version 0

T1: người A đọc version 0
T2: người B cũng đọc version 0

T3: A lưu "Final"
T4: B lưu "Old edit" dựa trên dữ liệu cũ

Nếu cả hai UPDATE chỉ WHERE id=101,
B có thể ghi đè thay đổi của A (lost update).
```

**Cách phòng tránh cho read-modify-write:** lưu cột `version` và yêu cầu phiên bản khớp với bản mà client đã đọc.

```sql
UPDATE documents
SET title = ?,
    version = version + 1
WHERE tenant_id = ?
  AND id = ?
  AND version = ?;
```

Ý nghĩa:

- **`tenant_id, id`**: định vị duy nhất document.
- **`version = ?`**: yêu cầu trạng thái chưa bị ai cập nhật kể từ lúc caller đọc.
- **`version = version + 1`**: đổi version trong cùng một statement nguyên tử khi update thành công.
- `rowsAffected == 1`: cập nhật được thực hiện trên phiên bản mong đợi.
- `rowsAffected == 0`: một trong các predicate không còn đúng; không ghi đè dữ liệu mới bằng phiên bản cũ.

Mẫu Java:

```java
int count = jdbc.update(
    """
    UPDATE documents
    SET title = ?, version = version + 1
    WHERE tenant_id = ? AND id = ? AND version = ?
    """,
    newTitle, tenantId, id, expectedVersion);

if (count == 0) {
    throw new IllegalStateException(
        "Version conflict or document not found");
}
if (count != 1) {
    throw new IllegalStateException(
        "Expected one row, got " + count);
}
```

SQL update với kiểm tra version **được DB đánh giá trong cùng statement**, an toàn hơn kiểu:

```text
SELECT ... WHERE id = ?;
if (version == expected) {
    UPDATE ... WHERE id = ?;  <-- Dễ xảy ra race giữa SELECT và UPDATE
}
```

**Lưu ý:** optimistic locking không làm biến mất mọi conflict. Ứng dụng phải giải quyết xung đột: báo cho người dùng tải lại và so sánh, merge có kiểm soát hoặc retry khi thao tác idempotent/thuần. Không retry vô hạn hay ghi đè âm thầm. Bản demo ở mục 11 mô phỏng hai request tuần tự dùng cùng version cũ để chứng minh `0` ở lần thứ hai; đó chưa phải stress test thực sự nhiều thread.

### Version kiểu số hay timestamp?

`INTEGER/BIGINT version` tăng dần thường dễ hiểu và kiểm thử. Timestamp có thể gặp collision khi hai thao tác nằm trong độ chính xác thời gian của DB, khác timezone hoặc driver làm tròn; đừng thay thế một cách vô thức bằng timestamp tự sinh. Chọn chiến lược theo schema và yêu cầu concurrency. Trong JPA, `@Version` có hỗ trợ riêng; ở **JdbcTemplate thuần** bạn phải tự viết điều kiện version/increment.

## 7. Transaction: row count check có đủ để rollback không?

Một `UPDATE` đơn lẻ là statement nguyên tử theo DB, nhưng **một thao tác nghiệp vụ** có thể có nhiều statement: cập nhật document, thêm audit, trừ quota, tạo notification outbox.

Với Spring, đặt `@Transactional` ở **service public được gọi qua Spring proxy**, để các thao tác JDBC cùng datasource/manager tham gia transaction.

```java
// Snippet khái niệm: các repository và auditWriter đã cấu hình.
@Transactional
public void approveDocument(String tenantId, long id) {
    int changed = repository.approve(tenantId, id);
    if (changed != 1) {
        throw new IllegalStateException(
            "Exactly one document expected");
    }
    auditWriter.recordApproved(tenantId, id);
}
```

Mục tiêu: khi UPDATE hoặc INSERT audit lỗi theo quy tắc rollback, cả hai được rollback. **Đừng để UPDATE commit trước rồi mới kiểm tra count** trong một DAO không transactional, nhất là khi không chắc predicate duy nhất. Nếu chỉ cần một SQL statement trên bảng có PK, phạm vi khóa chính vẫn phải đúng; không dùng `@Transactional` để “sửa” SQL thiếu `WHERE`.

**Quy tắc mặc định của Spring** (nếu không cấu hình rollback khác): unchecked `RuntimeException`/`Error` kích hoạt rollback; checked exception không tự động kích hoạt rollback. Nếu dùng checked business exception, cân nhắc `@Transactional(rollbackFor = MyCheckedException.class)` hoặc policy thích hợp.

**Proxy/self-invocation:** `this.approveDocument(...)` trong cùng object có thể không đi qua AOP transaction proxy. Controller/runner/service khác gọi public method trên Spring bean proxy mới đúng với proxy-mode mặc định. Đừng đặt annotation lên method rồi mặc định tin mọi đường gọi đều có transaction.

### Một lỗi đặc biệt nguy hiểm

```java
// SAI về bảo đảm rollback trong autocommit:
int changed = jdbc.update(
    "UPDATE documents SET title = ? WHERE tenant_id = ?",
    title, tenantId); // Có thể đã commit việc đổi nhiều hàng!

if (changed > 1) {
    throw new IllegalStateException("Too many rows");
}
```

Sau khi ném exception, **không có bảo đảm những thay đổi đã autocommit bị hoàn tác**. Ngăn sự cố trước tiên bằng `WHERE` theo khóa duy nhất được DB ràng buộc; transaction bảo vệ tính nguyên tử khi có nhiều bước và phục vụ rollback nếu invariant vi phạm.

## 8. Kiểm tra điều kiện nghiệp vụ ngay trong WHERE

Không phải mọi biến động đều chỉ cần `id`/`version`. Bạn có thể đặt điều kiện thêm vào SQL để bảo vệ invariant atomically.

### Chỉ chuyển từ DRAFT sang APPROVED

```sql
UPDATE documents
SET status = 'APPROVED',
    version = version + 1
WHERE tenant_id = ?
  AND id = ?
  AND status = 'DRAFT'
  AND version = ?;
```

Nếu `0`: có thể document không tồn tại, đã approved, đã bị xóa hoặc version cũ. Đây là **conditional state transition**, tốt hơn việc SELECT status rồi UPDATE không có kiểm tra trạng thái khi có race.

### Không trừ số dư xuống âm

```sql
UPDATE wallets
SET balance = balance - ?,
    version = version + 1
WHERE wallet_id = ?
  AND balance >= ?;
```

Tham số amount được bind **hai lần**: một cho phép trừ, một cho ngưỡng. `wallet_id` là khóa chính/unique. Với wallet thực, phải kiểm soát amount `> 0`, currency/scale, idempotency, transaction đa tài khoản, audit và khóa cạnh tranh. Ví dụ SQL này chỉ cho thấy **predicate kiểm tra số dư và thay đổi nằm trong cùng statement**.

### Đừng dùng điều kiện không duy nhất để thay khóa

```sql
-- Thiếu khóa: mọi đơn hàng PENDING đều có thể bị APPROVED.
UPDATE orders SET status = 'APPROVED'
WHERE status = 'PENDING';

-- Đúng nếu order_id là PRIMARY KEY và state transition được phép:
UPDATE orders SET status = 'APPROVED'
WHERE order_id = ? AND status = 'PENDING';
```

Thêm điều kiện nghiệp vụ **sau** điều kiện khóa, không **thay** điều kiện khóa. Điều này giúp code review dễ phát hiện mất khóa khi sửa SQL.

## 9. Pessimistic locking và isolation: khi nào cần SELECT FOR UPDATE?

Optimistic locking thường phù hợp khi conflict không quá thường xuyên. Với workflow phải đọc nhiều cột, đưa ra quyết định phức tạp rồi cập nhật, có thể dùng **khóa hàng bi quan** theo tính năng DB.

```sql
-- Cú pháp thường gặp, hỗ trợ/cách khóa khác nhau giữa DB.
SELECT id, balance
FROM wallets
WHERE wallet_id = ?
FOR UPDATE;
```

**Điều kiện sử dụng đúng:**

- Thực hiện SELECT và UPDATE **trong cùng transaction**, không dùng auto-commit rồi mong khóa vẫn giữ đến statement sau.
- `WHERE` vẫn theo khóa và phạm vi bảo mật.
- Kiểm tra database/driver/isolation có hỗ trợ cú pháp và lock semantics mong muốn.
- Giữ transaction ngắn, tránh gọi network/API chậm khi đang giữ row lock.
- Có thể phát sinh deadlock/lock wait timeout; cần chiến lược retry có giới hạn nếu nghiệp vụ cho phép.

Không dùng `FOR UPDATE` nếu chỉ cần cập nhật một trường với một statement `UPDATE ... WHERE id = ? AND version = ?`. Thêm lock không cần thiết có thể gây nghẽn và giảm throughput.

### Isolation không thay cho predicate đúng

Chọn `READ_COMMITTED`, `REPEATABLE_READ` hay `SERIALIZABLE` quyết định loại hiện tượng concurrency được giảm/tránh tùy DB; **không mức isolation nào cứu được một câu `UPDATE` thiếu khóa**. Mọi row phù hợp `WHERE` vẫn là đối tượng có thể bị cập nhật.

## 10. Generated key liên quan thế nào đến UPDATE theo khóa?

Chủ đề “Cập nhật và khóa sinh” dễ gây nhầm giữa hai thời điểm:

1. **INSERT:** database sinh khóa mới (`IDENTITY`, sequence, UUID DB-side…). Code có thể lấy bằng JDBC `getGeneratedKeys` hoặc Spring `KeyHolder`.
2. **UPDATE:** dùng **khóa xác định** được lưu/đọc từ dữ liệu nghiệp vụ để cập nhật đúng hàng. `UPDATE` bình thường không “tạo khóa mới” hay tự chọn record mới nhất.

Trong Spring JDBC, mã INSERT thường có mẫu:

```java
// Snippet minh họa, cần JdbcTemplate jdbc và schema phù hợp.
KeyHolder holder = new GeneratedKeyHolder();
int inserted = jdbc.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO products(name) VALUES (?)",
        new String[] {"id"});
    ps.setString(1, "Keyboard");
    return ps;
}, holder);

Number generatedId = holder.getKey();
```

Cần import `org.springframework.jdbc.support.KeyHolder`, `GeneratedKeyHolder` và `java.sql.PreparedStatement`. Đây không phải ví dụ chạy độc lập và chỉ đúng khi cột id được DB sinh, driver hỗ trợ generated keys. `getKey()` cũng có thể không phù hợp nếu nhiều keys/cột, hãy kiểm tra kết quả. Với bảng composite PK, cơ chế sinh khóa có thể khác.

**Sau INSERT, lưu khóa đúng bản ghi**, không đoán bằng `SELECT MAX(id)` hay “lấy hàng cuối cùng”. Cả hai cách đoán đều có thể sai khi nhiều request cùng chèn. Khi UPDATE, bind id đã lấy được vào `WHERE` và kiểm tra count.

```sql
UPDATE products
SET name = ?
WHERE id = ?;
```

Khi chỉ cập nhật các cột thông thường, không thay `id` (khóa tham chiếu) nếu không có thiết kế migration/foreign-key rõ ràng.

## 11. Chương trình hoàn chỉnh: khóa ghép, cập nhật nghiêm ngặt và optimistic locking

Ví dụ **Java 17+**, Maven, **Spring Boot 3.5.16**, Spring JDBC và H2 in-memory. Nó thể hiện:

- Một document chỉ được xác định bằng cặp `(tenant_id,id)`.
- Một method transactional yêu cầu **đúng một hàng** được cập nhật.
- Một id không tồn tại trả lỗi domain trong service, không báo thành công giả.
- Hai lần ghi bằng cùng `expectedVersion=0`: lần đầu thành công, lần hai không ghi đè.
- Document ở tenant khác có cùng id không bị thay đổi.

**Đây là project Maven nhiều file.** Không biên dịch riêng từng source bằng `javac` nếu thiếu classpath Spring/H2.

### 11.1. Cấu trúc project

```text
keyed-update-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/keyupdate/
        │   ├── KeyUpdateApplication.java
        │   └── DocumentService.java
        └── resources/
            ├── application.properties
            ├── schema.sql
            └── data.sql
```

### 11.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>keyed-update-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot starter JDBC cung cấp `JdbcTemplate` và hạ tầng transaction phù hợp với datasource được auto-configure. H2 là database nhúng dùng cho demo, không có dữ liệu production.

### 11.3. src/main/resources/schema.sql

```sql
CREATE TABLE documents (
    tenant_id VARCHAR(32) NOT NULL,
    id BIGINT NOT NULL,
    title VARCHAR(120) NOT NULL,
    version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, id)
);
```

**Tại sao PK gồm hai cột?** Ví dụ cố ý tạo hai tenant dùng cùng `id=101` để chứng minh `WHERE id=?` là **không đủ** với thiết kế này. DB bảo đảm cặp tenant/id là duy nhất.

### 11.4. src/main/resources/data.sql

```sql
INSERT INTO documents (tenant_id, id, title, version)
VALUES
    ('tenant-a', 101, 'Draft', 0),
    ('tenant-a', 102, 'Second', 0),
    ('tenant-b', 101, 'Other', 0);
```

### 11.5. src/main/resources/application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
spring.datasource.url=jdbc:h2:mem:keyedupdate;DB_CLOSE_DELAY=-1
spring.sql.init.mode=always
```

### 11.6. src/main/java/com/example/keyupdate/DocumentService.java

```java
package com.example.keyupdate;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {

    private final JdbcTemplate jdbc;

    public DocumentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Không thay đổi hơn một document: tenant_id + id là composite PK.
    // RuntimeException trên 0 hàng khiến transaction rollback.
    @Transactional
    public int renameStrict(String tenantId, long id, String newTitle) {
        int changed = jdbc.update(
            "UPDATE documents SET title = ? " +
            "WHERE tenant_id = ? AND id = ?",
            newTitle, tenantId, id);

        if (changed != 1) {
            throw new IllegalStateException(
                "Expected exactly one updated document; got " + changed);
        }
        return changed;
    }

    // Optimistic locking: version phải khớp trong cùng câu UPDATE.
    @Transactional
    public int renameIfVersion(
            String tenantId, long id, int expectedVersion,
            String newTitle) {

        int changed = jdbc.update(
            """
            UPDATE documents
            SET title = ?, version = version + 1
            WHERE tenant_id = ? AND id = ? AND version = ?
            """,
            newTitle, tenantId, id, expectedVersion);

        // 0: missing row, wrong tenant, or stale version.
        // Caller quyết định có báo conflict hay tra cứu thêm.
        if (changed > 1) {
            throw new IllegalStateException(
                "Invariant violation: " + changed + " rows");
        }
        return changed;
    }
}
```

**Lưu ý thực tế:** public service được Spring quản lý nên `@Transactional` áp dụng khi caller truy cập qua bean proxy. `IllegalStateException` là unchecked, phù hợp default rollback của Spring. Khóa ghép được ràng buộc bởi `PRIMARY KEY`, nên `changed > 1` không thể xảy ra khi SQL/schema đúng; phép kiểm tra vẫn nêu rõ invariant ở ranh giới DAO/service.

### 11.7. src/main/java/com/example/keyupdate/KeyUpdateApplication.java

```java
package com.example.keyupdate;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class KeyUpdateApplication {

    public static void main(String[] args) {
        SpringApplication.run(KeyUpdateApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DocumentService service, JdbcTemplate jdbc) {
        return args -> {
            int updated = service.renameStrict(
                    "tenant-a", 101L, "Reviewed");
            System.out.println("strict-updated=" + updated);

            try {
                service.renameStrict("tenant-a", 999L, "Ignored");
            } catch (IllegalStateException ex) {
                System.out.println("missing=NOT_FOUND");
            }

            int fresh = service.renameIfVersion(
                    "tenant-a", 101L, 0, "Final");
            System.out.println("optimistic-updated=" + fresh);

            int stale = service.renameIfVersion(
                    "tenant-a", 101L, 0, "Unexpected");
            System.out.println("optimistic-stale=" + stale);

            String document = jdbc.queryForObject(
                "SELECT title || '|' || version FROM documents " +
                "WHERE tenant_id = ? AND id = ?",
                String.class, "tenant-a", 101L);
            System.out.println("document=" + document);

            String otherTenant = jdbc.queryForObject(
                "SELECT title FROM documents " +
                "WHERE tenant_id = ? AND id = ?",
                String.class, "tenant-b", 101L);
            System.out.println("other-tenant=" + otherTenant);
        };
    }
}
```

**Chạy** tại thư mục `keyed-update-demo` sau khi cài JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

**Các dòng do ứng dụng chủ động in** (không tính output Maven/Spring):

```text
strict-updated=1
missing=NOT_FOUND
optimistic-updated=1
optimistic-stale=0
document=Final|1
other-tenant=Other
```

### 11.8. Phân tích từng kết quả

1. `strict-updated=1`: `WHERE tenant_id='tenant-a' AND id=101` xác định một hàng. Title từ `Draft` thành `Reviewed`.
2. `missing=NOT_FOUND`: id 999 không có, update count = 0; service ném unchecked exception và Spring transaction rollback. Không có document mới được tạo.
3. `optimistic-updated=1`: document phiên bản 0 được sửa thành `Final` và version lên 1 **trong cùng UPDATE**.
4. `optimistic-stale=0`: lời gọi kế tiếp vẫn đòi version 0, nhưng DB đang có version 1, vì vậy **không ghi đè** title thành `Unexpected`.
5. `document=Final|1`: đọc sau cùng chứng minh title và version chính xác.
6. `other-tenant=Other`: tenant-b dùng cùng id 101 nhưng title vẫn nguyên, chứng minh khóa ghép đã giới hạn phạm vi.

Demo sử dụng H2 và thực thi tuần tự; nó chứng minh logic predicate/version nhưng **không chứng minh khả năng chịu tải, race conditions thực tế hoặc isolation của mọi database**. Khi làm dự án thật cần viết integration tests với DB production hoặc Testcontainers, kiểm tra multi-tenancy security và concurrent requests.

**Không chạy câu UPDATE thiếu khóa trên dữ liệu production để “thử xem nó ảnh hưởng bao nhiêu hàng”.** Để minh họa sai phạm vi có thể dùng môi trường test, transaction có kiểm soát và rollback, hoặc dùng `SELECT COUNT(*)` cùng predicate để đánh giá trước (dù SELECT trước không thay thế ràng buộc duy nhất/atomic update khi có cạnh tranh).

## 12. Named parameters giúp tránh đảo thứ tự khóa và giá trị

Với nhiều tham số cùng kiểu `String` hoặc `long`, kiểu positional `?` dễ bị gọi sai thứ tự. `NamedParameterJdbcTemplate` giúp thể hiện trực tiếp vai trò:

```java
// Snippet: NamedParameterJdbcTemplate named đã được inject.
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("tenant", tenantId)
    .addValue("documentId", id)
    .addValue("title", newTitle)
    .addValue("version", expectedVersion);

int changed = named.update(
    """
    UPDATE documents
    SET title = :title, version = version + 1
    WHERE tenant_id = :tenant
      AND id = :documentId
      AND version = :version
    """,
    params);
```

Cần imports `org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate` và `MapSqlParameterSource`. Named parameter vẫn là prepared statement parameterization, **không** cho phép thay một tên bảng/tên cột động bằng `:tableName`. Mỗi named value phải đến từ nguồn đã validate/authorize, nhất là tenant.

**Không chọn giữa `?` và `:name` bằng cách đoán query “ngắn hơn”:** cả hai đều hợp lệ. Chọn phong cách nhất quán, kiểm tra thứ tự/type, test SQL thực tế và giữ transaction semantics.

## 13. SqlUpdate object, JDBC thuần và batchUpdate

### 13.1. SqlUpdate của Spring JDBC

Trong codebase cũ có thể gặp `org.springframework.jdbc.object.SqlUpdate`:

```java
// Snippet cần DataSource ds và imports.
SqlUpdate op = new SqlUpdate(ds,
        "UPDATE documents SET title = ? " +
        "WHERE tenant_id = ? AND id = ?");
op.declareParameter(new SqlParameter("title", Types.VARCHAR));
op.declareParameter(new SqlParameter("tenant", Types.VARCHAR));
op.declareParameter(new SqlParameter("id", Types.BIGINT));
op.setRequiredRowsAffected(1);
op.compile();

int rows = op.update("Final", "tenant-a", 101L);
```

`setRequiredRowsAffected(1)` yêu cầu chính xác một hàng; `setMaxRowsAffected(1)` chỉ kiểm tra không vượt quá số hàng tối đa được cấu hình. Đây là **kiểm tra count sau khi thực thi**, không tự biến một điều kiện `WHERE` không duy nhất thành duy nhất. Nếu quan tâm rollback khi có bất thường, vẫn cần transaction thích hợp. `compile()` chuẩn bị object Spring, **không** chạy UPDATE.

### 13.2. PreparedStatement thuần

```java
// Snippet trong method có java.sql.Connection con.
String sql =
    "UPDATE documents SET title = ? " +
    "WHERE tenant_id = ? AND id = ?";

try (PreparedStatement ps = con.prepareStatement(sql)) {
    ps.setString(1, newTitle);
    ps.setString(2, tenantId);
    ps.setLong(3, id);
    int changed = ps.executeUpdate();
}
```

`PreparedStatement` index bắt đầu từ **1**. Với JDBC thuần, nơi sở hữu `Connection` phải quyết định transaction và cleanup. `JdbcTemplate` giảm boilerplate này. Cả hai cần SQL predicate đúng.

### 13.3. Batch update theo nhiều khóa

```java
// Snippet cho DAO có JdbcTemplate jdbc và danh sách DocumentChange.
int[] counts = jdbc.batchUpdate(
    "UPDATE documents SET title = ? " +
    "WHERE tenant_id = ? AND id = ?",
    changes,
    changes.size(),
    (ps, change) -> {
        ps.setString(1, change.title());
        ps.setString(2, change.tenantId());
        ps.setLong(3, change.id());
    });
```

Ở đây `changes` là danh sách các record kiểu `DocumentChange` do ứng dụng định nghĩa; đây là snippet minh họa, không là project độc lập. Overload `batchUpdate(String, Collection<T>, int, ParameterizedPreparedStatementSetter<T>)` trong Spring JDBC có kiểu trả **`int[][]`** theo từng batch, không phải `int[]`. Nếu dùng overload khác `batchUpdate(String, BatchPreparedStatementSetter)`, kiểu trả là **`int[]`**. Khi refactor/test, chọn overload và khai báo kiểu nhận kết quả đúng, đừng copy nhầm signature.

**Đọc batch results cẩn thận:** JDBC có sentinel `Statement.SUCCESS_NO_INFO` (`-2`) hoặc `EXECUTE_FAILED` (`-3`) tùy driver. Không giả định mọi entry có count chính xác là 1. Nếu thao tác batch phải atomic, dùng transaction và xử lý exception/partial failure phù hợp.

### 13.4. Cập nhật không khóa trong job dữ liệu có chủ đích

Một tác vụ migration/bulk update có thể cố ý cập nhật nhiều hàng:

```sql
UPDATE documents
SET archived = TRUE
WHERE retention_due < CURRENT_DATE
  AND archived = FALSE;
```

Đây **không** phải update theo khóa đơn hàng, mà là bulk business operation. Nó cần quyền cao, kiểm tra predicate, kế hoạch migration, bảo toàn dữ liệu, observability và rollback/backup. Không áp quy tắc “mọi UPDATE phải đúng một hàng” cho bulk job; thay vào đó, phân biệt rõ loại thao tác và kiểm soát phạm vi phù hợp.

## 14. Test để phát hiện cập nhật quá rộng và lost update

### Test chức năng theo khóa

Bắt đầu bằng nhiều hàng có điểm tương đồng:

- Hai hàng cùng `tenant_id` nhưng khác `id`.
- Hai tenant dùng cùng một `id`.
- Hai hàng có cùng title/status, khác khóa.
- Một id không tồn tại.
- Một hàng đã soft-delete hoặc trạng thái không hợp lệ.
- Hai yêu cầu dùng cùng `version` cũ.

Sau mỗi thao tác, **query lại toàn bộ các hàng có nguy cơ liên quan** trong fixture, không chỉ kiểm tra row count. Với bảng có tenant, chứng minh một update cho tenant-a không làm đổi tenant-b.

Ví dụ assertion khái niệm:

```java
int count = service.renameIfVersion("tenant-a", 101L, 0, "New");
assertEquals(1, count);

int stale = service.renameIfVersion("tenant-a", 101L, 0, "Old");
assertEquals(0, stale);

// Kiểm tra title/version sau cùng và record tenant-b
// vẫn nguyên bằng JdbcTemplate hoặc repository.
```

Snippet `assertEquals` cần JUnit và dữ liệu test riêng; không thuộc ví dụ chạy `CommandLineRunner`. Nếu dùng `@JdbcTest`, `@SpringBootTest`, `@Transactional` test, hãy hiểu rollback test framework, datasource và fixture initialization trước khi kết luận sản phẩm an toàn.

### Test transaction rollback khi count bất thường

Trong môi trường test, tạo một service có `@Transactional` gọi một operation không khớp invariant, ném exception, rồi truy vấn xác nhận dữ liệu không đổi. Quan trọng hơn: **đánh giá độc lập predicate/constraint**, vì rollback là lưới an toàn, không phải biện pháp ngăn mass update ở thời điểm statement đang thực thi.

### Test cạnh tranh thực sự

Dùng hai transaction/threads với latch hoặc công cụ kiểm thử concurrency, cho cả hai đọc cùng version rồi cùng update. Kỳ vọng một transaction cập nhật thành công, transaction còn lại **không thể ghi đè im lặng**; tùy DB còn có conflict/lock timeout/deadlock. Nếu có retry, retry phải reload state và áp dụng chính sách merge, không tự dùng lại stale data.

## 15. Những lỗi hay gặp và cách sửa

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Thiếu `WHERE` | Sửa toàn bảng | Viết và review predicate theo khóa |
| Chỉ `WHERE tenant_id=?` trong bảng nhiều document | Sửa nhiều hàng của tenant | Thêm đầy đủ `tenant_id AND id` |
| Chỉ `WHERE id=?` trong composite PK | Sửa cùng id ở nhiều tenant | Bind tất cả thành phần khóa |
| Tin tên cột `id` đồng nghĩa primary key | Không có uniqueness guarantee | Kiểm tra migration/DDL |
| Dùng email/name/status không unique | Có thể nhiều hàng khớp | Dùng stable unique key và DB constraint |
| Dùng `UPDATE ... LIMIT 1` để che sai phạm vi | Chọn hàng không chủ đích, phụ thuộc dialect | Đúng `WHERE` và constraint |
| Chỉ kiểm tra `rows>1` sau autocommit | Nhiều hàng đã bị commit | Predicate duy nhất + transaction |
| Bỏ qua `rows=0` | Trả “thành công” khi không có hàng | Domain error, 404/409 hoặc NO_MATCH |
| Tưởng `0` luôn đồng nghĩa không tồn tại | Nhầm stale version/tenant/status | Phân biệt bằng contract và lookup có quyền |
| Đổi thứ tự `title,tenant,id` trong bind | Sửa sai hoặc JDBC type error | So từng dấu `?` và param |
| Ghép input vào SQL trực tiếp | SQL injection | Prepared statement/named params |
| Lấy tenant id chưa được xác thực | Sửa chéo tenant | Tenant từ security context, DB policy |
| Chỉ khóa PK, không bảo vệ version | Lost update | `WHERE version=?` + increment |
| SELECT version rồi UPDATE chỉ theo id | Time-of-check/time-of-use race | Kiểm tra version trong cùng UPDATE |
| Không tăng `version` sau update | Stale check vô hiệu | `version=version+1` atomic |
| Tự retry version cũ vô hạn | Nhiều conflict, có thể ghi đè logic | Reload/merge có giới hạn |
| Cho rằng `@Transactional` có hiệu lực với self-call | Không đi qua proxy | Gọi qua Spring bean proxy |
| Coi `SqlUpdate.setRequiredRowsAffected` là SQL LIMIT | Không ngăn nhiều hàng được sửa trước kiểm tra | DB uniqueness + transaction |
| Lấy `SELECT MAX(id)` để update hàng vừa insert | Race/concurrency sai hàng | `KeyHolder`/`getGeneratedKeys` |
| Coi `JdbcTemplate.batchUpdate` có một count duy nhất | Mất thông tin từng batch | Chọn overload và xử lý `int[]`/`int[][]` đúng |
| Giữ transaction mở khi gọi API bên ngoài | Lock lâu, timeout | Thu gọn transaction, outbox khi cần |

## 16. Quy trình code review cho UPDATE theo khóa

Khi duyệt một PR chứa `UPDATE`, lần lượt hỏi:

1. **Có `WHERE` không?** Nếu không, đây có phải bulk migration được cho phép và kiểm soát riêng?
2. **`WHERE` dùng khóa nào?** Primary key, composite PK hay unique key? Có DB constraint thực sự?
3. **Có tenant/authorization scope không?** Giá trị tenant từ nguồn đáng tin hay request tùy ý?
4. **Có bind an toàn không?** `?` hoặc named parameters, đúng thứ tự và type?
5. **Count 0/1/>1 xử lý thế nào?** Có báo mất hàng, conflict, hoặc invariant violation đúng contract?
6. **Có khả năng lost update không?** Nếu read-modify-write, dùng version/check state/lock thích hợp?
7. **Transaction boundary ở đâu?** Một statement hay nhiều statement, có rollback khi count không như mong muốn?
8. **Nếu có generated key:** khóa lấy từ INSERT đúng transaction hay đang đoán bằng `MAX(id)`?
9. **Nếu có batch:** overload nào, return counts là kiểu gì, có sentinel JDBC không?
10. **Có test đủ hàng tương tự nhau không?** Ít nhất hai hàng cùng tenant và hai tenant cùng id (nếu multi-tenant).
11. **Có quan sát được lỗi không?** Log/metric số hàng, transaction failure, deadlock/conflict nhưng không log dữ liệu nhạy cảm.

Một câu hỏi quan trọng để kết luận: **“Có bằng chứng ở schema và test rằng một lần gọi sửa đúng record đã chọn, không chạm record bên cạnh không?”** Nếu chưa, đừng chỉ tin vào việc SQL nhìn có vẻ đủ điều kiện.

## 17. Tự kiểm tra kiến thức

**1.** Bảng có `PRIMARY KEY(id)`. `UPDATE products SET name=? WHERE id=?` có thể khớp hai hàng cùng id không?  
**Đáp:** không nếu DB thực sự enforce primary key; trong điều kiện bình thường tối đa một hàng khớp. Vẫn cần kiểm tra `0` và quyền truy cập.

**2.** Bảng có `PRIMARY KEY(tenant_id,id)`, cùng id 101 ở tenant A/B. `WHERE id=101` có an toàn không?  
**Đáp:** không; nó có thể sửa cả hai. Dùng `tenant_id=? AND id=?` với tenant đã xác thực.

**3.** `UPDATE` trả 2, Java throw exception sau đó. Dữ liệu chắc chắn rollback?  
**Đáp:** không, nếu statement đã auto-commit; transaction mới có thể rollback theo quy tắc phù hợp. Quan trọng nhất vẫn là predicate/constraint duy nhất.

**4.** `UPDATE ... WHERE id=? AND version=?` trả 0. Có chắc record đã bị xóa?  
**Đáp:** không; còn có thể wrong tenant, status bị lọc, version stale hoặc semantics DB cụ thể. Phải phân loại theo contract.

**5.** Hai request cùng đọc version 0; lần thứ nhất tăng version lên 1, lần hai vẫn dùng 0. Kết quả mong đợi?  
**Đáp:** lần thứ hai không ghi đè, `rows=0` nếu predicate version được DB đánh giá atomically.

**6.** `setRequiredRowsAffected(1)` trên Spring `SqlUpdate` có tự làm SQL thành `UPDATE ... LIMIT 1`?  
**Đáp:** không; nó kiểm tra count sau thực thi, không sửa phạm vi SQL.

**7.** Vì sao không dùng `SELECT MAX(id)` để tìm row vừa tạo rồi cập nhật?  
**Đáp:** các connection khác có thể insert đồng thời, trả về id không thuộc operation của bạn. Dùng generated keys của chính INSERT.

**8.** Khi nào một `UPDATE` nhiều hàng là hợp lệ?  
**Đáp:** bulk operation được thiết kế có chủ đích, predicate và quyền/rollback/observability riêng; khác với cập nhật một entity theo khóa.

## Tài liệu tham khảo chính thức

- Spring Framework — `JdbcTemplate` và update SQL: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — `@Transactional` settings và proxy: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — rollback mặc định: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework API — `JdbcTemplate`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework API — `SqlUpdate` và `setRequiredRowsAffected`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/SqlUpdate.html
- Spring Framework — JDBC batch operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Boot 3.5 — SQL databases/H2: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Java SE 17 — `PreparedStatement.executeUpdate()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html
- Java SE 17 — JDBC batch counts: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html

**Kết luận:** Để cập nhật **một** bản ghi an toàn, hãy dùng **`UPDATE ... WHERE` chứa khóa duy nhất được database ràng buộc**, bind tham số thay vì nối chuỗi, **xử lý chính xác số hàng ảnh hưởng**, thêm **version** khi có cạnh tranh, và đặt **transaction boundary** đúng nghiệp vụ. Kiểm tra count là bước phát hiện lỗi — **không phải** giấy phép được viết một predicate quá rộng.