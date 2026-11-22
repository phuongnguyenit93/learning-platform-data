# Ngoại lệ JDBC: SQLIntegrityConstraintViolationException và lỗi dữ liệu

## Mục tiêu bài học

Khi ứng dụng Java ghi dữ liệu bằng JDBC, **một câu lệnh SQL hợp lệ về cú pháp** vẫn có thể bị database từ chối vì nội dung không thỏa các ràng buộc của bảng: trùng khóa duy nhất, tham chiếu đến bản ghi cha không tồn tại, để trống trường bắt buộc hoặc vi phạm `CHECK`. JDBC diễn đạt một số lỗi này bằng `java.sql.SQLIntegrityConstraintViolationException`, thuộc nhóm `SQLException` **không phải lỗi tạm thời có thể tự hết khi retry y nguyên**.

Tuy nhiên, **vi phạm ràng buộc dữ liệu** không đồng nghĩa mọi **lỗi dữ liệu**. Những trường hợp như số vượt phạm vi, chuyển đổi kiểu không hợp lệ, phép chia cho 0 hoặc ngày tháng không hợp lệ có thể thuộc `SQLDataException`. Việc phân biệt giúp ứng dụng chọn đúng cách phản hồi: sửa input/kiểm tra xung đột, rollback transaction, hay xử lý một lỗi vận hành khác.

Sau bài này, bạn có thể:

1. Hiểu `SQLIntegrityConstraintViolationException`, quan hệ kế thừa từ `SQLNonTransientException` và ý nghĩa **SQLState class `23`** theo Javadoc Java SE 26.
2. Phân biệt các constraints `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `NOT NULL` và `CHECK`; hiểu vì sao cùng một input có thể bị từ chối ở database dù đã qua validation của API.
3. So sánh `SQLIntegrityConstraintViolationException` (**class `23`**) với `SQLDataException` (**class `22`**), `SQLTransactionRollbackException` (**class `40`**) và `SQLSyntaxErrorException` (**class `42`**).
4. Dùng `SQLException.getSQLState()`, `getErrorCode()`, `getNextException()`, `getCause()` để phân loại lỗi an toàn, kể cả SQLState `null` và khi driver không trả đúng subclass mong đợi.
5. Hiểu **vendor-specific SQLState/error codes**: các mã như `23505`, `23503`, `23502` và `23514` là ví dụ cụ thể theo PostgreSQL, **không** được coi là mã toàn cục của mọi JDBC driver.
6. Thiết kế cách rollback/commit, không retry y nguyên sau constraint violation; phân biệt lỗi có thể retry **toàn bộ transaction** trong điều kiện được xác định.
7. Bảo vệ dữ liệu cá nhân khi ghi log SQLException và trả thông báo nghiệp vụ cho người dùng; không parse chuỗi thông báo lỗi DB bằng từ khóa.
8. Xử lý đúng `BatchUpdateException`, `getLargeUpdateCounts()`, các phần tử `Statement.EXECUTE_FAILED` và chuỗi ngoại lệ `getNextException()`.
9. Chạy một ví dụ **Java 17+ độc lập**, kiểm thử 29 điều kiện bằng một JDBC test double có `Connection`, `PreparedStatement`, transaction mock, constraints và các SQLException có SQLState.
10. Đề xuất ma trận integration tests cần chạy với **driver và cơ sở dữ liệu thực**, không nhầm những gì test double chứng minh với hành vi của DBMS.

**Special Note:** Bài chỉ dùng kiến thức còn hiệu lực trong Java SE/JDBC hiện hành (tham khảo Java SE 26), không dựa trên API đã bị loại bỏ hay các cách bắt lỗi chỉ mang tính lịch sử. Mọi đoạn code không độc lập hoặc không dùng database thật đều được chú thích rõ.

## 1. Điều gì xảy ra khi database bác bỏ một thao tác dữ liệu?

Giả sử một ứng dụng lưu đơn hàng vào bảng:

```sql
-- DDL có tính minh họa, cần điều chỉnh theo DBMS.
CREATE TABLE customers (
    id BIGINT PRIMARY KEY
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    units INTEGER NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id),
    CONSTRAINT chk_orders_units CHECK (units > 0)
);
```

DDL trên minh họa những ràng buộc phổ biến. Cú pháp constraint/identity/kiểu dữ liệu hoặc cách DB phát hiện lỗi có thể khác giữa các DBMS.

Khi chạy:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO orders(id, email, customer_id, units) VALUES (?, ?, ?, ?)")) {
    ps.setLong(1, orderId);
    ps.setString(2, email);
    ps.setLong(3, customerId);
    ps.setInt(4, units);
    ps.executeUpdate();
}
```

đây là **snippet tích hợp** cần `connection` thật và các biến dữ liệu hợp lệ, JDBC driver và database. Nếu email đã tồn tại, customer không tồn tại hoặc units không thỏa `CHECK`, DB có thể từ chối lệnh và JDBC driver ném `SQLException`. Một driver tuân theo mapping JDBC có thể dùng `SQLIntegrityConstraintViolationException`.

**Điểm cốt lõi:** cú pháp SQL có thể hoàn toàn đúng; vấn đề nằm ở **tính toàn vẹn của dữ liệu trong database**, không phải parser SQL.

### 1.1. Ràng buộc do database kiểm tra

- **`PRIMARY KEY`:** định danh bản ghi không được trùng (và không được NULL theo quy tắc khóa chính).
- **`UNIQUE`:** tập cột được khai báo duy nhất; chi tiết `NULL` và unique semantics tùy DBMS/schema.
- **`FOREIGN KEY`:** khóa tham chiếu phải đáp ứng tính toàn vẹn quan hệ.
- **`NOT NULL`:** một cột bắt buộc có giá trị không NULL.
- **`CHECK`:** giá trị/hàng phải thỏa biểu thức kiểm tra; quy tắc khi biểu thức trả UNKNOWN/NULL tùy semantics SQL.
- **Các ràng buộc đặc thù DBMS:** chẳng hạn exclusion constraint hoặc ràng buộc do database hỗ trợ khác.

Không nên tin rằng chỉ kiểm tra `email != null` trong Java là đủ: database là điểm kiểm soát **cuối cùng** đối với những ràng buộc đã khai báo. Các request đồng thời có thể vượt qua bước kiểm tra trước ở tầng ứng dụng, nhưng một trong các transaction vẫn sẽ bị unique constraint từ chối.

### 1.2. Không coi mọi thất bại khi INSERT là constraint violation

Một lệnh INSERT có thể thất bại vì:

- SQL sai cú pháp hoặc tên cột không tồn tại (`SQLSyntaxErrorException` hoặc mã vendor tương ứng).
- Kết nối bị hỏng (`SQLTransientConnectionException`, `SQLNonTransientConnectionException` hoặc các lỗi khác).
- Dữ liệu không thể chuyển đổi sang SQL type (`SQLDataException`).
- Deadlock/serialization failure (`SQLTransactionRollbackException` hoặc mã tương ứng).
- Hết thời gian chờ, không đủ quyền hoặc resource exhaustion.
- Batch bị lỗi tại một phần tử (`BatchUpdateException`).

Không thể bắt tất cả `SQLException` rồi trả “email đã tồn tại”. Điều đó làm mất thông tin lỗi thật, che sự cố database và dễ đưa người dùng vào đường xử lý sai.

## 2. Phân cấp ngoại lệ JDBC hiện đại

Javadoc Java SE 26 khai báo:

```text
java.lang.Exception
└── java.sql.SQLException
    ├── java.sql.SQLNonTransientException
    │   ├── SQLIntegrityConstraintViolationException  <-- lỗi constraint
    │   ├── SQLDataException                          <-- lỗi dữ liệu/chuyển đổi
    │   ├── SQLSyntaxErrorException                   <-- cú pháp/quy tắc truy cập
    │   └── ... các subclass không tạm thời khác
    ├── java.sql.SQLTransientException
    │   ├── SQLTransactionRollbackException          <-- transaction rollback
    │   └── ... các subclass tạm thời khác
    ├── java.sql.BatchUpdateException                 <-- lỗi batch
    ├── java.sql.SQLRecoverableException
    └── java.sql.SQLWarning (cảnh báo)
```

Sơ đồ chỉ giữ các nhánh liên quan; dấu `...` không đại diện cho code phải import hoặc class có tên như vậy.

### 2.1. `SQLIntegrityConstraintViolationException`

`SQLIntegrityConstraintViolationException extends SQLNonTransientException`. Javadoc nói subclass này được ném khi SQLState class là `23` **hoặc theo điều kiện do vendor quy định**, báo một integrity constraint như foreign key, primary key hoặc unique key bị vi phạm.

Ý nghĩa “non-transient”: **retry cùng thao tác với cùng điều kiện, không sửa nguyên nhân, được kỳ vọng sẽ lại thất bại**. Đây là chỉ dẫn phân loại, không có nghĩa tình trạng business không thể giải quyết: có thể người dùng đổi email, chọn customer hợp lệ hoặc một transaction khác thay đổi dữ liệu, nhưng hành động sửa phải có chủ đích.

### 2.2. `SQLDataException`

`SQLDataException extends SQLNonTransientException`, gắn với SQLState class `22` hoặc điều kiện vendor. Ví dụ: numeric value out of range, format ngày tháng không hợp lệ, chuyển đổi kiểu sai, division by zero, một số lỗi xử lý XML/JSON tùy DB.

Lỗi dữ liệu không nhất thiết là constraint violation. Một số constraints dùng `CHECK`, nhưng numeric overflow có thể xảy ra **trước khi** hệ thống đánh giá constraint, nên thường nằm ở class `22`.

### 2.3. `SQLTransactionRollbackException`

`SQLTransactionRollbackException extends SQLTransientException`. Javadoc liên hệ với SQLState class `40` hoặc vendor conditions, như deadlock/serialization failure. **Đây không phải lý do tự động retry từng statement**, đặc biệt nếu cả transaction đã bị rollback. Với policy cho phép, phải cân nhắc **retry toàn transaction**, giới hạn lần thử, backoff và tính idempotent.

### 2.4. `SQLSyntaxErrorException`

`SQLSyntaxErrorException extends SQLNonTransientException`; SQLState class `42` hoặc vendor conditions. Dùng khi SQL sai cú pháp hoặc vi phạm quy tắc truy cập. Sửa câu SQL/schema/permissions, **không** yêu cầu người dùng sửa một field dữ liệu như khi unique violation.

### 2.5. `SQLException` chung vẫn rất quan trọng

Driver có thể ném `SQLException` trực tiếp hoặc một subclass vendor-specific thay vì một subclass JDBC chuyên biệt trong mọi trường hợp. Vì thế xử lý robust cần đọc cả:

```java
ex.getSQLState();
ex.getErrorCode();
ex.getNextException();
ex.getCause();
```

Không mặc định `instanceof SQLIntegrityConstraintViolationException` bao phủ **100%** constraints trên mọi driver. Cũng không mặc định SQLState luôn có 5 ký tự; `getSQLState()` có thể trả `null`.

## 3. SQLState: phân loại theo hai ký tự đầu

`SQLException.getSQLState()` cung cấp một mã do driver báo, dựa theo SQL standard conventions hoặc X/Open. Khi có mã 5 ký tự theo SQL standard, **hai ký tự đầu** biểu thị error class.

| SQLState class | Nhóm lỗi | JDBC class thường liên quan | Chính sách tổng quát |
| --- | --- | --- | --- |
| **`23`** | Integrity constraint violation | `SQLIntegrityConstraintViolationException` | Xác định ràng buộc, sửa input/trạng thái domain; rollback |
| **`22`** | Data exception | `SQLDataException` | Sửa kiểu/giá trị/format hoặc quy tắc xử lý |
| **`40`** | Transaction rollback | `SQLTransactionRollbackException` | Cân nhắc retry **toàn transaction** khi phù hợp |
| **`42`** | Syntax error/access rule violation | `SQLSyntaxErrorException` | Sửa SQL/schema/permissions |
| **`08`** | Connection exception | Các subclass connection exception tùy trường hợp | Chẩn đoán kết nối, timeout và trạng thái giao dịch |
| **`0A`** | Feature not supported | `SQLFeatureNotSupportedException` | Driver/DB không hỗ trợ feature |

Bảng dùng để **định hướng phân loại**, không thay contract vendor. Không chỉ dựa vào hai ký tự đầu rồi tự đoán chi tiết constraint. Ví dụ `23` chỉ nói “integrity”, còn muốn biết “trùng email” hay “FK không tồn tại” cần condition code/constraint identifier đáng tin cậy từ vendor.

### 3.1. SQLState có thể null

`getSQLState()` có thể trả `null`; ví dụ constructor `new SQLException("unknown")` khởi tạo SQLState null. Vì vậy code sau không an toàn:

```java
// Sai nếu ex.getSQLState() trả null:
if (ex.getSQLState().startsWith("23")) {
    // ...
}
```

Dùng:

```java
String sqlState = ex.getSQLState();
if (sqlState != null && sqlState.startsWith("23")) {
    // Nhóm integrity, cần xét driver/schema để xử lý chi tiết.
}
```

Đây là snippet tích hợp. Nếu driver không cung cấp SQLState, vẫn phải log và xử lý theo exception type/vendo­r contract, không tự biến thành “validation thành công”.

### 3.2. SQLState không phải error code của vendor

`getSQLState()` trả String code như `23505`. `getErrorCode()` trả **int vendor-specific**; mặc định có thể là 0 nếu không được cung cấp. Một DB có thể dùng một số errorCode cụ thể cho duplicate key; **không** dùng con số của database A để diễn giải driver B.

Ví dụ demo chạy độc lập sau tự đặt vendor code `1005` cho duplicate key: **1005 chỉ là mã tự chế của mock**, tuyệt đối không phải mã PostgreSQL/Oracle/Microsoft SQL Server.

### 3.3. Không parse `getMessage()` để nhận loại lỗi

Nội dung `getMessage()` có thể bao gồm tên constraint, tên bảng, giá trị khóa, ngôn ngữ thông báo hoặc message format do driver thay đổi. Không dùng:

```java
// Anti-pattern: phụ thuộc thông điệp con người, dễ thay đổi.
if (ex.getMessage().contains("duplicate key")) { /* ... */ }
```

Thay vào đó dùng **exception class, SQLState, vendor error code hoặc structured DB metadata** theo tài liệu driver. Nếu thông tin không đủ, xử lý như lỗi DB chung có trace và logging an toàn.

## 4. Các vi phạm toàn vẹn thường gặp

### 4.1. Unique hoặc primary key trùng

Ví dụ:

```sql
-- Một cột chỉ được lưu một giá trị email trong bảng.
ALTER TABLE accounts ADD CONSTRAINT uq_accounts_email UNIQUE (email);
```

DDL là ví dụ, có thể cần điều chỉnh theo schema/DBMS. Nếu hai requests lưu cùng email, một thao tác có thể bị database từ chối.

**Hành vi nên làm:**

- Nếu email thực sự phải duy nhất, coi DB unique constraint là **nguồn bảo đảm cuối cùng**.
- Tầng app có thể kiểm tra trước để hỗ trợ UX, nhưng không xem đó là atomic uniqueness guarantee.
- Khi DB bác bỏ, trả một lỗi domain rõ ràng nếu **chắc chắn** constraint bị vi phạm chính là unique email.
- Nếu cùng request được gửi lại do mạng, áp dụng idempotency/business upsert theo thiết kế, không mặc định duplicate là lỗi server.
- Khi retry, không lặp y nguyên INSERT không có kế hoạch: nếu email vẫn tồn tại, nó sẽ thất bại tiếp.

### 4.2. Foreign key không hợp lệ

```sql
INSERT INTO orders(id, customer_id) VALUES (10, 999999);
```

Nếu customer 999999 không tồn tại và schema có FK, database có thể từ chối. Lỗi ở đây có thể do client truyền ID sai, dữ liệu đã bị xóa đồng thời hoặc workflow chưa tạo parent trước child.

**Không làm:** tắt FK constraints trong DB để INSERT “chạy được”. Đó là phá tính toàn vẹn của dữ liệu.

**Nên làm:** kiểm tra quyền truy cập và tồn tại parent nếu phù hợp, bảo đảm transaction ordering, nhưng vẫn xử lý race ở DB. Không leak sự tồn tại của ID nhạy cảm cho client khi domain yêu cầu kiểm soát quyền.

### 4.3. NOT NULL

Nếu cột bắt buộc và request bỏ qua giá trị, database có thể từ chối `NULL`. Phân biệt:

- **Java `null`** khi bind `setNull` hoặc `setObject`.
- **String rỗng `""`** có thể vẫn là một giá trị không NULL ở một số DB.
- **Không khai báo column** trong INSERT có thể kích hoạt DEFAULT, hoặc gây lỗi nếu không có DEFAULT, tùy schema.
- Validation app phải nhất quán với migration/schema thật.

Không gộp mọi trường hợp missing/blank thành cùng một lỗi SQL tự suy đoán.

### 4.4. CHECK constraint

```sql
CONSTRAINT chk_units_positive CHECK (units > 0)
```

Một row có `units <= 0` có thể bị từ chối. CHECK là ràng buộc do DB kiểm tra. Trong SQL three-valued logic, biểu thức CHECK với `UNKNOWN` có semantics riêng; nếu cột cũng không được phép NULL, dùng thêm `NOT NULL`.

**Không dùng CHECK như một thay thế cho mọi validation UI**: DB giữ integrity, còn ứng dụng nên cung cấp thông báo, context và mã lỗi domain có thể hiểu.

### 4.5. Deferred constraints và thời điểm phát sinh lỗi

Trong một số database (ví dụ PostgreSQL), một số constraints có thể được khai báo **DEFERRABLE**, khiến việc kiểm tra được hoãn đến `COMMIT`. Do đó:

- Một `executeUpdate()` có thể thành công nhưng `connection.commit()` vẫn ném integrity-related `SQLException`.
- Đừng nói “không có SQLException ở execute nghĩa là data đã hợp lệ hoàn toàn”.
- Code cần bao cả bước `commit` trong cùng error-handling boundary.
- Không mặc định mọi constraint đều có thể defer: khả năng hỗ trợ và loại constraint phụ thuộc DBMS.

Nếu `commit` lỗi do **mất kết nối hoặc trạng thái không chắc chắn**, kết quả có thể không xác định; ứng dụng không nên retry một INSERT vô điều kiện. Phân biệt commit bị DB bác bỏ do deferred constraint với commit có kết quả không rõ bởi network failure.

## 5. Integrity constraint violation khác data exception như thế nào?

Hai nhóm thường bị nhầm vì cả hai đều xuất phát từ một “giá trị đầu vào không phù hợp”.

| Tình huống | SQLState class thường gặp | Ý nghĩa |
| --- | --- | --- |
| Duplicate email vi phạm UNIQUE | `23` | Tính toàn vẹn của tập rows bị vi phạm |
| Foreign key trỏ tới parent không tồn tại | `23` | Ràng buộc quan hệ bị vi phạm |
| NOT NULL bị vi phạm | `23` | Ràng buộc trường bắt buộc bị vi phạm |
| CHECK units > 0 bị vi phạm | `23` | Ràng buộc boolean không thỏa |
| Integer vượt miền dữ liệu SQL | `22` | Numeric value out of range |
| Chuỗi không convert được sang numeric SQL type | `22` | Invalid character value for cast |
| Ngày tháng sai format hoặc out of range | `22` | Data conversion/date-time error |
| Chuỗi bị cắt vì vượt cột | `22` hoặc warning/exception tùy API/driver | Có thể liên quan `DataTruncation`, `SQLDataException` hoặc mapping khác |
| Deadlock/serialization failure | `40` | Transaction rollback, không phải data correction đơn thuần |
| SQL sai cú pháp | `42` | SQL syntax/access rule, không phải constraint từ dữ liệu |

**Quan trọng:** `SQLIntegrityConstraintViolationException` và `SQLDataException` đều kế thừa `SQLNonTransientException`; chúng không phải hai cấp “lỗi nhẹ/lỗi nặng”. Chúng chỉ mô tả **hai nhóm nguyên nhân** khác nhau.

### 5.1. Lỗi độ dài có thể có kiểu riêng: DataTruncation

`java.sql.DataTruncation extends SQLWarning` — đây là API vẫn tồn tại ở Java SE 26. Javadoc phân biệt:

- Khi **đọc**, `DataTruncation` có thể được báo như warning, SQLState `01004`.
- Khi **ghi**, `DataTruncation` có thể được ném như exception, SQLState `22001`.
- `getDataSize()` và `getTransferSize()` nêu kích thước gốc/đã chuyển nếu có.
- `DataTruncation` **không kế thừa `SQLDataException`** mặc dù write SQLState của nó thuộc family `22`.

Vì vậy không viết “mọi truncation error chắc chắn là `SQLDataException`”. Hãy kiểm tra JDBC API/driver, SQLState và vị trí phát sinh để phân loại đúng. Tương tự, `SQLWarning` có thể cần được đọc bằng `Statement.getWarnings()` hoặc APIs tương ứng, không chỉ qua một `catch SQLException`.

### 5.2. Business validation và database integrity bổ sung nhau

**Application validation** giúp user nhận feedback sớm:

- Email hợp lệ về cấu trúc và độ dài.
- Các tham số numeric nằm trong khoảng nghiệp vụ.
- Có quyền chọn customer mà request đang tham chiếu.
- Dữ liệu văn bản sử dụng charset/encoding đúng.
- Những field bắt buộc đã được cung cấp.

**Database constraints** chặn trạng thái không hợp lệ khi nhiều clients/processes ghi đồng thời, kể cả khi application check có race.

Không dùng database SQLException như API validation duy nhất, vì message có thể chứa thông tin hệ thống nội bộ. Cũng không chỉ validate ở client rồi bỏ constraints, vì mọi ghi ngoài app sẽ bỏ qua check đó.

## 6. Cách phân loại SQLException theo type và SQLState

Một hàm phân loại **mang tính trợ giúp**, không thay hợp đồng của driver:

```java
enum Category { INTEGRITY, DATA, TRANSACTION_ROLLBACK, OTHER }

static Category classify(SQLException e) {
    String state = e.getSQLState();
    String family = state != null && state.length() >= 2
            ? state.substring(0, 2) : "";

    if (e instanceof SQLIntegrityConstraintViolationException
            || family.equals("23")) return Category.INTEGRITY;
    if (e instanceof SQLDataException
            || family.equals("22")) return Category.DATA;
    if (e instanceof SQLTransactionRollbackException
            || family.equals("40")) return Category.TRANSACTION_ROLLBACK;
    return Category.OTHER;
}
```

Đây là **phần code được triển khai trong chương trình chạy đầy đủ ở mục 10**; cần imports các `java.sql` exceptions liên quan.

### 6.1. Tại sao kiểm tra cả instanceof lẫn SQLState?

- Một driver có thể ném subclass chuyên biệt mà `getSQLState()` bằng null.
- Một driver có thể ném `SQLException` chung nhưng `getSQLState()` bắt đầu với `23`.
- Các trường hợp family khác như `22`, `40` được xử lý tương tự.
- SQLState không có/null được gán nhóm OTHER chứ không gây `NullPointerException`.

### 6.2. Đây không phải bộ phân loại toàn năng

Một số drivers dùng vendor-specific behavior, exception wrapping, nested exception chain hoặc SQLState convention khác. Nếu một exception subclass và SQLState **mâu thuẫn**, helper trên ưu tiên nhánh thứ nhất khớp; đây chỉ là lựa chọn cho demo. Trong hệ thống thật, phải quy định rõ precedence theo driver và chỉ map lỗi domain khi có đủ bằng chứng.

Một `BatchUpdateException` có thể là **top-level error** nhưng nguyên nhân constraint nằm ở `getNextException()`, không nhất thiết ở top-level `getSQLState()`. Helper trên không tự đệ quy; xem mục 11.

### 6.3. Không dùng SQLState để xác định field khi không biết schema

Ngay cả khi `getSQLState()` là `23505` trên PostgreSQL, có thể có nhiều UNIQUE constraints. Muốn biết field vi phạm, dùng **constraint name hoặc structured detail** do driver cung cấp và một **mapping allowlisted** của ứng dụng. Không đoán mọi `23505` đều là duplicate email.

## 7. Transaction sau khi bị integrity violation

### 7.1. Không tiếp tục transaction như thể không có lỗi

Sau một SQL statement bị DB từ chối, transaction có thể ở trạng thái cần rollback. Ví dụ PostgreSQL đặt transaction vào trạng thái failed sau một error trong explicit transaction, trừ khi dùng savepoint phù hợp. DBMS khác có thể có semantics khác; thiết kế JDBC portable nên:

1. Bắt lỗi ở boundary transaction.
2. **Rollback** hoặc giao rollback cho transaction manager/framework.
3. Giải phóng statements/result sets.
4. Chỉ thực hiện thao tác tiếp theo trong transaction/connection hợp lệ.
5. Không retry cùng command trong failed transaction mà chưa xử lý trạng thái.

### 7.2. Dùng try-with-resources

```java
try (Connection c = dataSource.getConnection()) {
    c.setAutoCommit(false);
    try {
        try (PreparedStatement ps = c.prepareStatement(
                "INSERT INTO orders(email, customer_id, units) VALUES (?, ?, ?)")) {
            ps.setString(1, email);
            ps.setLong(2, customerId);
            ps.setInt(3, units);
            ps.executeUpdate();
        }
        c.commit();
    } catch (SQLException | RuntimeException failure) {
        try {
            c.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Đây là **snippet tích hợp**, cần `dataSource` thật, dữ liệu và schema SQL phù hợp. Nó sử dụng modern Java/JDBC, nhưng không chạy độc lập nếu không cấu hình database.

**Caveat:** Nếu đã mượn transaction từ Spring/Jakarta EE/application server, tầng repository **không được tự gọi commit/rollback** nếu transaction manager sở hữu nó. Khi đó để exception propagate/mark rollback theo contract framework.

### 7.3. Rollback failure phải được giữ

Nếu `ps.executeUpdate()` ném `SQLIntegrityConstraintViolationException` và `rollback()` cũng ném SQLException, không nên làm mất lỗi gốc. `failure.addSuppressed(rollbackFailure)` giúp giữ thông tin phụ. Try-with-resources cũng giữ suppressed exceptions từ `close` khi body đã có primary exception.

### 7.4. Commit failure có thể cần điều tra

Nếu `commit()` ném SQLException, **không mặc định rollback sẽ luôn đưa hệ thống về trạng thái cũ**; một số lỗi commit/network khiến kết quả chưa rõ. Log correlation ID, xem transaction manager/driver semantics, sử dụng idempotency keys/unique constraints khi thiết kế retry.

### 7.5. Vì sao không tự động retry unique violation?

Vì điều kiện dữ liệu đang không thỏa UNIQUE. Lặp y nguyên INSERT sẽ vẫn thất bại trừ khi có thay đổi dữ liệu/logic. `SQLIntegrityConstraintViolationException` là non-transient theo contract, nên ưu tiên **business response**, không retry vô hạn.

Ngược lại, serialization failure `40001` hoặc deadlock `40P01` trên PostgreSQL có thể cho phép retry **toàn transaction** nếu đảm bảo idempotency và giới hạn attempts. Chúng thuộc chính sách retry khác, không phải một “constraint error retry”.

## 8. Xung đột đồng thời và thiết kế idempotency

### 8.1. Vì sao SELECT trước INSERT không đủ?

```text
Request A                         Request B
   |                                 |
   | SELECT email: chưa tồn tại      |
   |                                 | SELECT email: chưa tồn tại
   | INSERT email=x                  |
   |                                 | INSERT email=x
   | COMMIT -> thành công            | COMMIT/INSERT -> UNIQUE violation
```

Đây là race condition tự nhiên nếu chỉ check bằng `SELECT` rồi tin vào kết quả. Database UNIQUE constraint là điểm quyết định cuối cùng.

Tùy nghiệp vụ:

- Nếu trùng email nghĩa là bản ghi đã tồn tại, trả lỗi domain thích hợp.
- Nếu request là retry tạo cùng tài nguyên theo idempotency key, kiểm tra **same request / same business intent** và trả kết quả trước đó theo contract.
- Nếu app cần update-or-insert, dùng upsert/merge theo khả năng DBMS và bảo đảm transaction semantics; **không giả định một câu SQL UPSERT chạy giống nhau trên mọi database**.
- Nếu cùng email cho nhiều tenants là hợp lệ, thiết kế unique constraint **theo tenant + email** và mapping tương ứng, không chặn bằng global validation không đúng.

### 8.2. Không dùng lỗi để “giấu” xung đột

Lỗi integrity từ DB là thông tin hệ thống có thể chứa tên bảng/constraint/giá trị. App không cần trả nguyên `getMessage()` cho client. Dùng mã lỗi nghiệp vụ ổn định như `EMAIL_ALREADY_USED` nếu xác định rõ constraint; các mã này là **do ứng dụng tự định nghĩa**, không phải SQLState.

### 8.3. Giữ database constraints trong migrations

Nếu application yêu cầu tính duy nhất, schema phải có constraint tương ứng. Một migration bỏ UNIQUE nhưng giữ validation trong Java sẽ tạo lỗ hổng khi background jobs hoặc các instances ghi đồng thời.

## 9. Một số mã SQLState theo PostgreSQL (ví dụ vendor)

Bảng sau được kiểm tra theo **PostgreSQL 18 Appendix A: Error Codes**. Nó giúp học cách đọc **mã năm ký tự**, **không phải bảng áp dụng mọi JDBC driver**.

| SQLState | Condition PostgreSQL | Class | Tình huống |
| --- | --- | --- | --- |
| `23505` | `unique_violation` | `23` | Trùng khóa unique/primary |
| `23503` | `foreign_key_violation` | `23` | FK không hợp lệ |
| `23502` | `not_null_violation` | `23` | Cột NOT NULL |
| `23514` | `check_violation` | `23` | CHECK constraint |
| `23000` | `integrity_constraint_violation` | `23` | Integrity violation tổng quát |
| `22003` | `numeric_value_out_of_range` | `22` | Số vượt phạm vi |
| `22018` | `invalid_character_value_for_cast` | `22` | Chuyển đổi kiểu text/cast |
| `22007` | `invalid_datetime_format` | `22` | Date/time format sai |
| `22001` | `string_data_right_truncation` | `22` | Text vượt kích thước |
| `40001` | `serialization_failure` | `40` | Transaction serialization failure |
| `40P01` | `deadlock_detected` | `40` | Deadlock, mã PostgreSQL-specific |
| `42601` | `syntax_error` | `42` | Cú pháp SQL sai |

**Lưu ý:** PostgreSQL/JDBC driver có thể cung cấp metadata cụ thể hơn như **constraint name** theo API vendor. Nếu cần mapping field chính xác, ưu tiên structured metadata hơn việc parse localized `getMessage()`. Nếu DB khác PostgreSQL, tra bảng SQLState và error codes của **vendor đó**, không bê nguyên các con số trong bảng.

## 10. Chương trình Java 17+ độc lập: mô phỏng lỗi constraint và data

Để kiểm tra *cú pháp JDBC exception handling* mà không cần cài DB/driver, ví dụ sau dùng `java.lang.reflect.Proxy` tạo `Connection` và `PreparedStatement` **giả**. Mock lưu email trong `Set`, dùng `pending` để mô phỏng transaction; khi phát hiện dữ liệu không hợp lệ, mock **tự ném** các JDBC exceptions đã có trong JDK.

Nó minh họa:

- Một INSERT hợp lệ và `commit`.
- Vi phạm `UNIQUE`, `FOREIGN KEY`, `NOT NULL`, `CHECK` -> `SQLIntegrityConstraintViolationException` kèm các mã class `23`.
- Một quantity vượt phạm vi -> `SQLDataException` với class `22`.
- Rollback khi statement thất bại và làm tiếp trong một transaction mới.
- Phân loại theo subclass hoặc SQLState class; không NPE khi SQLState null.
- `SQLNonTransientException` vs `SQLTransientException`.
- `SQLException.getNextException` và `BatchUpdateException.getLargeUpdateCounts()`.
- Connection/PreparedStatement được close đúng scope.

**Đây là một test double, không thực thi SQL thật.** Các condition codes như `23505` mô phỏng giá trị phổ biến ở PostgreSQL; `getErrorCode()==1005` là **vendor code giả của mock**. Không suy ra driver thực tế trả đúng subclass, error code hoặc thời điểm rollback giống mock.

### 10.1. File `JdbcIntegrityDemo.java`

```java
import java.lang.reflect.Proxy;
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.SQLDataException;
import java.sql.SQLIntegrityConstraintViolationException;
import java.sql.SQLNonTransientException;
import java.sql.SQLTransactionRollbackException;
import java.sql.SQLTransientException;
import java.sql.SQLSyntaxErrorException;
import java.sql.Statement;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public final class JdbcIntegrityDemo {
    record Input(String email, long customerId, int units) {}

    enum Category { INTEGRITY, DATA, TRANSACTION_ROLLBACK, OTHER }

    static Category classify(SQLException e) {
        String state = e.getSQLState();
        String family = state != null && state.length() >= 2
                ? state.substring(0, 2) : "";
        if (e instanceof SQLIntegrityConstraintViolationException
                || family.equals("23")) return Category.INTEGRITY;
        if (e instanceof SQLDataException
                || family.equals("22")) return Category.DATA;
        if (e instanceof SQLTransactionRollbackException
                || family.equals("40")) return Category.TRANSACTION_ROLLBACK;
        return Category.OTHER;
    }

    static final class FakeSession {
        final Set<String> committedEmails = new HashSet<>();
        final Map<String, Input> pending = new LinkedHashMap<>();
        boolean autoCommit = true;
        boolean closed;
        int rollbackCalls;
        int commitCalls;
        int statementsClosed;

        Connection openConnection() {
            return (Connection) Proxy.newProxyInstance(
                JdbcIntegrityDemo.class.getClassLoader(),
                new Class<?>[] {Connection.class},
                (proxy, method, args) -> {
                    String n = method.getName();
                    if (n.equals("close")) { closed = true; return null; }
                    if (n.equals("isClosed")) return closed;
                    if (closed) throw new SQLException("Mock connection closed", "08003");
                    return switch (n) {
                        case "setAutoCommit" -> {
                            boolean requested = (Boolean) args[0];
                            if (requested) throw new SQLException(
                                    "Mock only enables manual transactions", "HY000");
                            autoCommit = false;
                            yield null;
                        }
                        case "getAutoCommit" -> autoCommit;
                        case "prepareStatement" -> newStatement();
                        case "commit" -> {
                            if (autoCommit) throw new SQLException("No manual transaction");
                            committedEmails.addAll(pending.keySet());
                            pending.clear();
                            commitCalls++;
                            yield null;
                        }
                        case "rollback" -> {
                            if (autoCommit) throw new SQLException("No manual transaction");
                            pending.clear();
                            rollbackCalls++;
                            yield null;
                        }
                        default -> throw new java.sql.SQLFeatureNotSupportedException(
                                "Test double: " + n);
                    };
                });
        }

        PreparedStatement newStatement() {
            final Object[] params = new Object[3];
            final boolean[] statementClosed = {false};
            return (PreparedStatement) Proxy.newProxyInstance(
                JdbcIntegrityDemo.class.getClassLoader(),
                new Class<?>[] {PreparedStatement.class},
                (proxy, method, args) -> {
                    String n = method.getName();
                    if (n.equals("close")) {
                        if (!statementClosed[0]) statementsClosed++;
                        statementClosed[0] = true;
                        return null;
                    }
                    if (n.equals("isClosed")) return statementClosed[0];
                    if (closed || statementClosed[0])
                        throw new SQLException("Mock statement closed");
                    return switch (n) {
                        case "setString", "setLong", "setInt" -> {
                            int index = (Integer) args[0];
                            if (index < 1 || index > 3)
                                throw new SQLException("Bad parameter index");
                            params[index - 1] = args[1];
                            yield null;
                        }
                        case "executeUpdate" -> {
                            if (!(params[1] instanceof Long)
                                    || !(params[2] instanceof Integer))
                                throw new SQLException("Missing numeric arguments");
                            Input input = new Input((String) params[0],
                                    (Long) params[1], (Integer) params[2]);
                            validate(input);
                            if (autoCommit) committedEmails.add(input.email());
                            else pending.put(input.email(), input);
                            yield 1;
                        }
                        default -> throw new java.sql.SQLFeatureNotSupportedException(
                                "Test double statement: " + n);
                    };
                });
        }

        void validate(Input input) throws SQLException {
            if (input.email() == null || input.email().isBlank()) {
                throw new SQLIntegrityConstraintViolationException(
                        "email is required", "23502", 1002);
            }
            if (committedEmails.contains(input.email())
                    || pending.containsKey(input.email())) {
                throw new SQLIntegrityConstraintViolationException(
                        "duplicate email", "23505", 1005);
            }
            if (input.customerId() != 10L) {
                throw new SQLIntegrityConstraintViolationException(
                        "parent row does not exist", "23503", 1003);
            }
            if (input.units() <= 0) {
                throw new SQLIntegrityConstraintViolationException(
                        "units must be positive", "23514", 1014);
            }
            if (input.units() > 999) {
                throw new SQLDataException(
                        "numeric value outside mock range", "22003", 2003);
            }
        }
    }

    static void insertAndCommit(Connection c, Input input) throws SQLException {
        try (PreparedStatement ps = c.prepareStatement(
                "INSERT INTO orders(email, customer_id, units) VALUES(?, ?, ?)")) {
            ps.setString(1, input.email());
            ps.setLong(2, input.customerId());
            ps.setInt(3, input.units());
            ps.executeUpdate();
            c.commit();
        } catch (SQLException | RuntimeException failed) {
            try { c.rollback(); }
            catch (SQLException rollbackFailure) {
                failed.addSuppressed(rollbackFailure);
            }
            throw failed;
        }
    }

    @FunctionalInterface
    interface SqlAction { void execute() throws SQLException; }

    static SQLException expectFailure(SqlAction action) {
        try { action.execute(); }
        catch (SQLException expected) { return expected; }
        throw new AssertionError("Expected SQLException");
    }

    static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) throws SQLException {
        FakeSession fake = new FakeSession();
        Connection connection = fake.openConnection();
        try (connection) {
            connection.setAutoCommit(false);
            check("manualTransaction", !connection.getAutoCommit());

            insertAndCommit(connection, new Input("a@example.test", 10, 3));
            check("initialInsertCommitted",
                    fake.committedEmails.contains("a@example.test"));

            SQLException duplicate = expectFailure(() ->
                    insertAndCommit(connection,
                            new Input("a@example.test", 10, 3)));
            check("uniqueSubclass",
                    duplicate instanceof SQLIntegrityConstraintViolationException);
            check("uniqueSQLState", "23505".equals(duplicate.getSQLState()));
            check("uniqueCategory", classify(duplicate) == Category.INTEGRITY);
            check("uniqueIsNonTransient", duplicate instanceof SQLNonTransientException);
            check("syntheticVendorCode", duplicate.getErrorCode() == 1005);

            SQLException foreign = expectFailure(() ->
                    insertAndCommit(connection, new Input("b@example.test", 999, 3)));
            check("foreignKeyViolation", "23503".equals(foreign.getSQLState()));
            SQLException missing = expectFailure(() ->
                    insertAndCommit(connection, new Input(null, 10, 3)));
            check("notNullViolation", "23502".equals(missing.getSQLState()));
            SQLException checkFail = expectFailure(() ->
                    insertAndCommit(connection, new Input("b@example.test", 10, 0)));
            check("checkConstraintViolation", "23514".equals(checkFail.getSQLState()));

            SQLException invalidNumber = expectFailure(() ->
                    insertAndCommit(connection, new Input("b@example.test", 10, 1000)));
            check("dataExceptionSubclass", invalidNumber instanceof SQLDataException);
            check("dataExceptionState", "22003".equals(invalidNumber.getSQLState()));
            check("dataVsIntegrity", classify(invalidNumber) == Category.DATA);
            check("rollbackCalledOnFailures", fake.rollbackCalls == 5);
            check("committedDataPreservedAfterRollback",
                    fake.committedEmails.size() == 1
                            && fake.committedEmails.contains("a@example.test"));

            insertAndCommit(connection, new Input("b@example.test", 10, 5));
            check("successAfterRollback", fake.committedEmails.size() == 2);
            check("preparedStatementsClosed", fake.statementsClosed == 7);
            check("twoCommits", fake.commitCalls == 2);

            check("genericState23Classifies",
                    classify(new SQLException("driver generic", "23000"))
                            == Category.INTEGRITY);
            check("genericState22Classifies",
                    classify(new SQLException("driver generic", "22018"))
                            == Category.DATA);
            check("nullSQLStateSafe",
                    classify(new SQLException("unknown", (String) null))
                            == Category.OTHER);
            check("syntaxNotIntegrity",
                    classify(new SQLSyntaxErrorException("bad SQL", "42000"))
                            == Category.OTHER);

            SQLException rolledBack = new SQLTransactionRollbackException(
                    "simulated serialization failure", "40001");
            check("transactionRollbackCategory",
                    classify(rolledBack) == Category.TRANSACTION_ROLLBACK);
            check("transactionRollbackIsTransient",
                    rolledBack instanceof SQLTransientException);

            SQLException root = new SQLException("outer", "HY000");
            root.setNextException(new SQLIntegrityConstraintViolationException(
                    "inner unique violation", "23505", 17));
            check("nextExceptionContainsIntegrity",
                    root.getNextException() instanceof SQLIntegrityConstraintViolationException);

            BatchUpdateException batch = new BatchUpdateException(
                    "simulated batch failure", "23000", 7,
                    new long[] {1L, Statement.EXECUTE_FAILED}, null);
            batch.setNextException(new SQLIntegrityConstraintViolationException(
                    "batch duplicate", "23505", 17));
            check("batchLargeCountsAvailable",
                    batch.getLargeUpdateCounts().length == 2);
            check("batchExecuteFailedMarker",
                    batch.getLargeUpdateCounts()[1] == Statement.EXECUTE_FAILED);
            check("batchChainedException",
                    batch.getNextException() instanceof SQLIntegrityConstraintViolationException);
        }
        check("connectionClosed", connection.isClosed());
    }
}
```

### 10.2. Biên dịch và chạy

Tạo một thư mục chứa `JdbcIntegrityDemo.java`, mở terminal trong thư mục đó rồi chạy:

```bash
javac --release 17 JdbcIntegrityDemo.java
java JdbcIntegrityDemo
```

Chỉ cần JDK 17+ (các ví dụ đã kiểm thử với OpenJDK 24). Code dùng `java.sql` và `java.base` của Java SE, không cần Maven, JDBC driver, DB server hay network. `record`, switch expression và pattern phù hợp với `--release 17`.

### 10.3. Stdout đã được kiểm chứng trên OpenJDK 24

```text
manualTransaction=true
initialInsertCommitted=true
uniqueSubclass=true
uniqueSQLState=true
uniqueCategory=true
uniqueIsNonTransient=true
syntheticVendorCode=true
foreignKeyViolation=true
notNullViolation=true
checkConstraintViolation=true
dataExceptionSubclass=true
dataExceptionState=true
dataVsIntegrity=true
rollbackCalledOnFailures=true
committedDataPreservedAfterRollback=true
successAfterRollback=true
preparedStatementsClosed=true
twoCommits=true
genericState23Classifies=true
genericState22Classifies=true
nullSQLStateSafe=true
syntaxNotIntegrity=true
transactionRollbackCategory=true
transactionRollbackIsTransient=true
nextExceptionContainsIntegrity=true
batchLargeCountsAvailable=true
batchExecuteFailedMarker=true
batchChainedException=true
connectionClosed=true
```

**29/29 assertions PASS**. Mỗi dòng được in qua `check` chỉ khi điều kiện thực sự đúng; nếu sai, `AssertionError` dừng chương trình. Mã đã được biên dịch bằng `javac --release 17` rồi chạy trên OpenJDK 24; fixture tạm không để lại file trong project.

### 10.4. Đọc các nhóm kết quả

| Nhóm | Assertions | Ý nghĩa |
| --- | --- | --- |
| Thành công | `initialInsertCommitted`, `twoCommits` | Dữ liệu được ghi vào Set mô phỏng khi commit |
| UNIQUE | `uniqueSubclass`, `uniqueSQLState`, `uniqueCategory`, `uniqueIsNonTransient`, `syntheticVendorCode` | Exception đúng subclass class `23`, code giả, non-transient |
| FOREIGN KEY | `foreignKeyViolation` | Mock dùng `23503` cho parent không có |
| NOT NULL | `notNullViolation` | Mock dùng `23502` cho email null |
| CHECK | `checkConstraintViolation` | Mock dùng `23514` cho units không dương |
| Data error | `dataExceptionSubclass`, `dataExceptionState`, `dataVsIntegrity` | `SQLDataException` và `22003` tách khỏi integrity |
| Transaction | `rollbackCalledOnFailures`, `committedDataPreservedAfterRollback`, `successAfterRollback` | Mock rollback sau thất bại; thành công trước vẫn có |
| Cleanup | `preparedStatementsClosed`, `connectionClosed` | Các proxies đóng theo scope |
| Classification | `genericState23Classifies`, `genericState22Classifies`, `nullSQLStateSafe`, `syntaxNotIntegrity` | Fallback SQLState/unknown an toàn |
| Transaction retry class | `transactionRollbackCategory`, `transactionRollbackIsTransient` | Class `40` có policy khác |
| Exception chains | `nextExceptionContainsIntegrity`, `batchChainedException` | Đọc chained SQLException |
| Batch counts | `batchLargeCountsAvailable`, `batchExecuteFailedMarker` | `EXECUTE_FAILED` và long counts |

**Giới hạn quan trọng:** mock không mô phỏng isolation, lock waits, deadlocks, deferrable constraints, trigger behavior, DB storage hoặc SQL parser. Nó tự ném subclasses đã chọn — một DB thật có thể dùng subclass/SQLState/errorCode khác. Vì vậy không dùng các kết quả trên làm bằng chứng rằng PostgreSQL/MySQL/SQL Server/Oracle JDBC driver cụ thể đã được kiểm thử. Bài tập tích hợp ở mục 16 giải quyết phần đó.

## 11. `BatchUpdateException` và lỗi integrity trong batch

Khi gọi `Statement.executeBatch()` hoặc `PreparedStatement.executeBatch()`, lỗi một phần tử thường xuất hiện dưới dạng `BatchUpdateException`. Top-level không nhất thiết là `SQLIntegrityConstraintViolationException`; nguyên nhân có thể nằm trong `getNextException()`/`getCause()`.

```java
try {
    int[] counts = ps.executeBatch();
} catch (BatchUpdateException batch) {
    int[] counts = batch.getUpdateCounts();
    for (SQLException detail = batch.getNextException();
         detail != null;
         detail = detail.getNextException()) {
        // Phân tích detail.getSQLState(), getErrorCode()
        // và type của detail; không log dữ liệu cá nhân.
    }
    throw batch;
}
```

Đây là snippet tích hợp cần `PreparedStatement ps` đã có batch entries. Nó **không phải** chương trình độc lập. Trong chính sách thực tế, cũng cần xem top-level `batch` (không chỉ next exceptions) và phân loại toàn bộ chain theo contract của driver.

### 11.1. Update counts có thể không phải “tất cả hoặc không gì”

Theo Javadoc Java SE 26, driver khi một batch command thất bại có thể:

- Dừng ngay: update counts mô tả các commands đã hoàn thành trước lỗi.
- Tiếp tục xử lý các commands còn lại: update counts có thể có phần tử cho tất cả commands, với `Statement.EXECUTE_FAILED` cho phần tử thất bại và `SUCCESS_NO_INFO` cho thành công không biết row count.

**Không suy ra** chỉ từ độ dài array rằng toàn transaction đã COMMIT hoặc ROLLBACK. Đó là trách nhiệm của transaction policy.

### 11.2. `executeLargeBatch` và `getLargeUpdateCounts`

Khi số lượng rows cập nhật có thể vượt `Integer.MAX_VALUE`, dùng `executeLargeBatch` và `BatchUpdateException.getLargeUpdateCounts()` (trả `long[]`) thay vì int counts. Demo đã tạo một batch exception với `long[]` mô phỏng.

**Các số trong demo là synthetic:** `new long[]{1L, Statement.EXECUTE_FAILED}` và vendor code 7 không phản ánh driver thật.

### 11.3. Không tự retry hàng thất bại mà không xét transaction

Với batch có UNIQUE/FK violation, cần biết:

- Driver dừng ở đâu hoặc có tiếp tục sau lỗi không.
- Database transaction có bị đánh dấu failed không.
- Những rows nào đã persist khi auto-commit; những rows nào chỉ đang pending.
- Việc retry có idempotent hay sẽ sinh dữ liệu trùng.
- Quy tắc rollback/compensation theo nghiệp vụ.

Khi cần tính atomicity của batch, mở transaction rõ ràng và rollback khi thất bại, hoặc dùng cơ chế framework transaction manager.

## 12. Chuỗi SQLException và metadata lỗi

`SQLException` hỗ trợ:

```java
String message = ex.getMessage();
String sqlState = ex.getSQLState();
int vendorCode = ex.getErrorCode();
SQLException next = ex.getNextException();
Throwable cause = ex.getCause();
Throwable[] suppressed = ex.getSuppressed();
```

Đây là các biến/truy cập trong method; `ex` cần là SQLException thực tế.

### 12.1. `getNextException` không giống `getCause`

- `getNextException()` là **JDBC SQLException chain**, thường có các SQL exceptions bổ sung từ driver/batch.
- `getCause()` là **Java exception cause** theo Throwable chain.
- `getSuppressed()` giữ các lỗi phát sinh khi cleanup/rollback không nên che nguyên nhân gốc.
- `SQLException implements Iterable<Throwable>`, có thể duyệt chained SQLExceptions và causes theo contract.

Nếu chỉ log một `ex.getMessage()`, bạn có thể bỏ mất thông tin cốt lõi ở `getNextException()`. Ngược lại, **không xuất nguyên chain ra client** nếu nó có thể chứa SQL text hoặc dữ liệu nhạy cảm.

### 12.2. Khai thác chain có kiểm soát

```java
static boolean containsConstraint(SQLException ex) {
    for (SQLException current = ex; current != null;
         current = current.getNextException()) {
        String state = current.getSQLState();
        if (current instanceof SQLIntegrityConstraintViolationException
                || (state != null && state.startsWith("23"))) {
            return true;
        }
    }
    return false;
}
```

Đây là **helper Java 17+ biên dịch được nếu nằm trong một class có import `java.sql.*`**, không phải full program. Nó duyệt JDBC nextException chain, không tự tìm vào `cause` hoặc `suppressed`. Trong hệ thống thực, cần thêm giới hạn độ sâu/chống vòng lặp không mong muốn với dữ liệu exception bất thường, và chọn thông tin nào là căn cứ domain đáng tin cậy. Không nên map toàn batch thành cùng một lỗi field nếu có nhiều rows/constraints khác nhau.

### 12.3. Ghi log an toàn

Những thông tin thường hữu ích cho internal logs:

- Error category: integrity/data/transaction/other.
- SQLState và vendor error code, nếu có.
- Tên constraint **nếu truy cập qua API đáng tin và được phép log**.
- Service name, operation name, correlation/request ID.
- Driver version/database product version (trong môi trường chẩn đoán thích hợp).
- Transaction outcome (rollback confirmed, unknown commit status).

Hạn chế:

- Email đầy đủ, số thẻ, token, password, nội dung SQL parameters nhạy cảm.
- Raw `SQLException.getMessage()` trong client response.
- Ghi log cùng lỗi ở nhiều tầng liên tiếp gây nhiễu.
- Trả tên bảng/constraint nội bộ cho người dùng cuối khi không cần.

## 13. Thiết kế response nghiệp vụ khi vi phạm ràng buộc

Một lỗi SQL kỹ thuật cần được chuyển sang **thông điệp domain có kiểm soát**.

| Nguyên nhân đã xác minh | Phản hồi nghiệp vụ gợi ý | Lưu ý |
| --- | --- | --- |
| Unique email đã được dùng | “Địa chỉ email đã được sử dụng” | Chỉ nói nếu domain cho phép tiết lộ sự tồn tại |
| Foreign key không hợp lệ | “Không tìm thấy đối tượng liên quan hoặc không thể tham chiếu” | Cân nhắc kiểm tra authorization |
| NOT NULL field thiếu | “Thiếu thông tin bắt buộc” | Nêu field nếu chắc chắn mapping |
| CHECK units > 0 | “Số lượng phải lớn hơn 0” | Kết hợp validation ở API |
| Numeric out of range | “Giá trị nằm ngoài phạm vi cho phép” | Đây thường là SQLDataException, không unique |
| Deadlock/serialization | Trạng thái retry/temporary error theo policy | Không thông báo người dùng “trùng khóa” |
| Unrecognized SQLException | Lỗi hệ thống tổng quát có correlation ID | Không lộ stack trace/SQL |

Trong REST API, **HTTP 409 Conflict** có thể phù hợp với một số unique conflicts; **400/422** có thể phù hợp với một số invalid-input semantics. Đây là **quyết định API/domain**, không phải quy tắc JDBC tự chuyển `SQLState=23` thành HTTP 409. Đừng dùng một mapping máy móc cho mọi integrity violation.

### 13.1. Không tiết lộ người dùng tồn tại trong hệ thống nhạy cảm

Trong đăng ký/đăng nhập, việc thông báo “email này đã đăng ký” có thể tạo user enumeration. Có hệ thống cần phản hồi chung hoặc gửi notification qua kênh thích hợp. DB exception chứa thông tin đầy đủ phục vụ nội bộ, nhưng **response công khai** phải tuân thủ security/privacy policy.

### 13.2. Constraint name nên rõ và ổn định

Thay vì để database tạo tên ngẫu nhiên, schema migration có thể khai báo tên có ý nghĩa như `uq_accounts_tenant_email`. Khi driver cung cấp **structured constraint name**, app có thể dùng allowlist:

```text
uq_accounts_tenant_email -> EMAIL_ALREADY_USED
fk_orders_customer       -> INVALID_CUSTOMER
chk_orders_units         -> INVALID_UNITS
```

Đây là **mapping application tự định nghĩa**, không phải SQLState. Driver khác có thể không expose constraint name theo API chuẩn JDBC; không parse bằng regex từ localized exception message như đường chính.

## 14. Phân biệt retry policy và kết quả transaction

### 14.1. Non-transient không phải “không bao giờ sửa được”

`SQLNonTransientException` nghĩa là retry thao tác **không thay đổi điều kiện** không được kỳ vọng thành công. Nếu người dùng chỉnh input hoặc admin sửa dữ liệu/schema, thao tác có thể chạy được. Không biến ngoại lệ thành cấm retry vĩnh viễn.

### 14.2. Transient không có nghĩa auto-retry vô hạn

`SQLTransactionRollbackException` thuộc `SQLTransientException`, nhưng retry phải xét:

- Có thể an toàn khi **lặp toàn transaction**?
- External side effects (email, payment, API call) có bị nhân đôi không?
- Retry count/backoff/timeouts có giới hạn?
- Có idempotency key hoặc outbox pattern phù hợp không?
- Kết quả transaction trước chắc chắn đã rollback hay đang unknown?

Nếu không rõ trạng thái commit, không tự động làm lại giao dịch có tác động lớn.

### 14.3. Savepoint không thay thế rollback policy chung

JDBC có `Connection.setSavepoint`/`rollback(Savepoint)` khi driver hỗ trợ. Một số workflow có thể phục hồi sau một lỗi statement bằng savepoint, nhưng hỗ trợ transaction/DDL/savepoint và constraints deferred khác nhau theo DBMS. Không hướng dẫn chung “sau integrity error cứ tiếp tục transaction” nếu chưa có savepoint và quy tắc vendor rõ.

## 15. Những lỗi tư duy phổ biến

1. **Catch `SQLException` rồi luôn trả duplicate email.** Sai: SQLException có nhiều nguyên nhân. Dùng subclass, SQLState, vendor contract và constraint mapping.
2. **Catch `SQLIntegrityConstraintViolationException` là đủ cho mọi driver.** Sai: driver có thể trả SQLException chung hoặc vendor subclass. Có chiến lược fallback được kiểm chứng.
3. **Cứ bắt lỗi class23 thì retry ba lần.** Sai: non-transient nghĩa là nguyên nhân chưa được sửa sẽ còn thất bại.
4. **Xem `23505` là mã toàn cục của JDBC.** Sai: mã chi tiết được minh họa theo PostgreSQL, cần tra driver/DBMS khác.
5. **Parse chữ “duplicate” từ getMessage.** Sai: localized message/constraint name có thể đổi hoặc lộ data.
6. **SELECT trước INSERT rồi bỏ UNIQUE.** Sai: requests đồng thời có race; cần constraint tại database.
7. **Bỏ qua rollback sau error.** Có DB giữ transaction ở trạng thái failed, làm các câu sau tiếp tục lỗi.
8. **Không bắt SQLException từ commit.** Deferred constraint có thể bị kiểm tra tại commit, network errors có thể làm outcome không rõ.
9. **Gộp SQLDataException và integrity violation.** Sai: lỗi numeric overflow/convert không giống lỗi FK/UNIQUE.
10. **Nghĩ DataTruncation là subclass SQLDataException.** Sai: `DataTruncation extends SQLWarning`; read/write có SQLState riêng.
11. **Nhìn getErrorCode bằng int rồi suy ra toàn bộ nguyên nhân.** Sai: int này vendor-specific, có thể 0.
12. **Chỉ xem BatchUpdateException message.** Có thể bỏ qua update counts và next exceptions.
13. **Cho rằng batch lỗi đồng nghĩa không row nào đã chạy.** Driver có thể tiếp tục hoặc dừng; transaction quyết định persist.
14. **Gọi một lỗi integrity là “client sai” tuyệt đối.** Có thể do concurrency, migration/schema mismatch, workflow ordering.
15. **Map tất cả class23 thành HTTP 409.** Domain quyết định lỗi nào là conflict, validation, không có quyền tiết lộ, hoặc lỗi hệ thống.
16. **Ghi log đầy đủ SQL parameters và PII.** Vi phạm privacy; log lỗi có kiểm soát.
17. **Quên close statement/connection khi exception.** Dùng try-with-resources để cleanup đúng.
18. **Phụ thuộc thông điệp do driver tạo để test.** Test theo type/state/result/transaction và integration DB.

## 16. Kiểm thử tích hợp với cơ sở dữ liệu thật

Mock ở mục 10 chỉ chứng minh **đường đi Java exceptions và transaction giả**. Khi triển khai, cần thử với driver/DBMS/version thực tế. Các ca kiểm thử tối thiểu:

| Test | Điều cần xác nhận |
| --- | --- |
| Insert hợp lệ | Dữ liệu persisted sau commit |
| Duplicate primary key | Exception class, SQLState, vendor code và rollback |
| Duplicate UNIQUE trên cột đơn | Mapping đúng constraint đó |
| Duplicate UNIQUE tổ hợp | Không map nhầm sang một cột đơn |
| FK không tồn tại | Đúng nhóm integrity, không leak thông tin |
| NOT NULL | Schema và API validation phù hợp |
| CHECK bị vi phạm | Driver trả gì; xử lý domain đúng |
| Numeric out of range | Không bị phân loại nhầm là class 23 |
| Conversion/date error | SQLDataException hoặc vendor mapping tương ứng |
| Deferred constraint | Có thể lỗi tại commit, không chỉ execute |
| Two concurrent INSERTs cùng key | DB đảm bảo unique; app xử lý transaction race |
| Rollback sau integrity error | Connection không để lại failed transaction vào pool |
| Batch 3 items, item thứ hai lỗi | Update counts, nextException chain và atomicity |
| Auto-commit true/false | Hiểu phần nào đã persist sau fail |
| JDBC driver nâng version | SQLState/subclass/error code vẫn được mapping đúng |
| SQLState null | Không crash; báo lỗi unknown có correlation ID |
| Privacy/logging | Không lộ raw SQL/PII cho client |
| Retry policy | Không retry class 23 y nguyên; class40 có policy an toàn |

### 16.1. Hai luồng concurrent cùng một unique key

Tạo hai connections khác nhau, cùng INSERT một giá trị unique trong hai transactions. Quan sát DB outcome với commit/rollback. **Không giả định** phía nào thắng hoặc statement/commit nào ném; mục tiêu là dữ liệu cuối cùng vẫn tuân thủ constraint và lỗi được ứng dụng xử lý an toàn.

### 16.2. Schema migration

Test sau migration thêm/bỏ constraint, đổi tên constraint hoặc thay column type. Một mapping SQLState/domain có thể cần cập nhật theo schema; quản lý migration và error mapping như một phần contract vận hành.

### 16.3. Những thứ không nên assert cứng

- Toàn bộ `SQLException.getMessage()` byte-for-byte.
- Tên implementation class của JDBC driver.
- Mã vendor của DBMS khác cùng một SQLState.
- Thứ tự hai concurrent requests thắng/thua.
- Thời điểm lỗi deferred constraint nếu DBMS hỗ trợ cấu hình defer khác nhau.

Thay vào đó assert domain behavior, SQLState/subclass theo **driver đang test**, transaction rollback và dữ liệu cuối cùng.

## 17. Bài tập thực hành

### Bài tập 1 — Thay đổi input để sửa unique violation

Trong `JdbcIntegrityDemo`, sau lần duplicate `a@example.test`, thử thêm `c@example.test` với customerId=10, units=1. Dự đoán số phần tử trong `FakeSession.committedEmails` sau `commit` và vì sao đây là **sửa dữ liệu**, không phải retry y nguyên lệnh thất bại.

### Bài tập 2 — Đổi thứ tự kiểm tra

Trong `FakeSession.validate`, đảo vị trí check units và duplicate. Nếu một input có cả duplicate email và units=0, mock sẽ phát hiện điều kiện đầu tiên theo thứ tự code. Với DB thật, **không được dựa** vào thứ tự constraint evaluation cố định như mock. Một request có thể vi phạm nhiều constraints, nhưng driver có thể chỉ báo một lỗi tại một thời điểm.

### Bài tập 3 — SQLState null

Tạo `new SQLIntegrityConstraintViolationException("vendor integrity")` không truyền SQLState. `classify` vẫn trả INTEGRITY nhờ type. Đổi thành `new SQLException("unknown")` và quan sát OTHER. Giải thích vì sao fallback phải có cả type lẫn SQLState.

### Bài tập 4 — Batching

Thay batch synthetic `new long[]{1L, EXECUTE_FAILED}` bằng một mảng ba phần tử; phân biệt `SUCCESS_NO_INFO` và `EXECUTE_FAILED`. Đọc Java SE 26 `BatchUpdateException` để giải thích driver có thể dừng/tiếp tục sau lỗi, và tại sao cần transaction nếu muốn atomic writes.

### Bài tập 5 — Non-transient vs transient

Tạo `SQLTransactionRollbackException("serialization", "40001")` và `SQLIntegrityConstraintViolationException("duplicate", "23505")`. So sánh class hierarchy, khi nào có thể retry **toàn transaction**, khi nào chỉ cần trả lỗi domain hoặc thay dữ liệu.

### Bài tập 6 — PostgreSQL integration

Nếu có PostgreSQL test DB, tạo UNIQUE/NOT NULL/FK/CHECK constraints, thử vi phạm thật bằng JDBC driver tương ứng; ghi lại `getSQLState`, `getErrorCode`, class name, next exceptions và tình trạng transaction sau khi fail. Không in email/PII thật; dùng dữ liệu giả.

### Bài tập 7 — Chuỗi exception

Tạo `SQLException outer` có `setNextException` với một SQLException `23505`. Viết một helper duyệt chain, trả category tương ứng mà không lẫn các lỗi unrelated. Xử lý SQLState null và không dùng substring trên null.

## 18. Câu hỏi tự kiểm tra

**1. `SQLIntegrityConstraintViolationException` kế thừa lớp nào?**

`SQLNonTransientException`, gián tiếp từ `SQLException`. Nó gắn với SQLState class `23` hoặc vendor conditions.

**2. UNIQUE constraint bị vi phạm khác gì SQL sai cú pháp?**

UNIQUE vi phạm tính toàn vẹn dữ liệu (class `23`), còn SQL syntax error thuộc nhóm `42`/`SQLSyntaxErrorException` hoặc vendor equivalent.

**3. Tại sao không retry cùng INSERT sau SQLIntegrityConstraintViolationException?**

Vì dữ liệu/constraint chưa thay đổi. Đây là lỗi non-transient; retry cùng điều kiện thường tiếp tục thất bại và có thể gây spam DB.

**4. SQLState `23505` có phải mã mọi JDBC driver cùng dùng không?**

Không. Nó là ví dụ condition code PostgreSQL. Các DB/driver khác có thể dùng `23000`, vendor code và mapping khác.

**5. `SQLDataException` gắn với SQLState class nào?**

`22`, gồm lỗi chuyển đổi, numeric out of range, division by zero và một số dữ liệu không hợp lệ.

**6. Nếu SQLState là null, code phải làm gì?**

Không gọi `startsWith` trực tiếp. Dùng type nếu đáng tin, xử lý như OTHER khi không đủ thông tin, log metadata an toàn và điều tra driver.

**7. `getErrorCode()` khác `getSQLState()` thế nào?**

`getSQLState` là chuỗi theo convention; `getErrorCode` là int vendor-specific (có thể 0). Không thay thế hai giá trị cho nhau.

**8. Có thể bắt lỗi duplicate tại `commit` không?**

Có, nếu constraint được DBMS cho phép deferred hoặc database phát hiện lỗi tại commit. Code phải bao cả `execute` và `commit` trong boundary xử lý transaction.

**9. “Đã SELECT kiểm tra không có email” có bảo đảm INSERT sẽ không trùng không?**

Không. Hai requests đồng thời có thể cùng thấy trống. UNIQUE constraint trong database mới là bảo vệ cuối cùng.

**10. `SQLTransactionRollbackException` có giống `SQLIntegrityConstraintViolationException` không?**

Không. SQLTransactionRollbackException là transient, class `40`; integrity violation là non-transient, class `23`. Retry policy khác nhau.

**11. DataTruncation có phải SQLDataException không?**

Không. `DataTruncation extends SQLWarning`; với read/write có các trạng thái warning/exception và SQLState `01004`/`22001` theo Javadoc.

**12. Sau SQLException khi trong transaction, có thể tiếp tục chạy statement như bình thường không?**

Không nên giả định; nhiều DB (đặc biệt PostgreSQL explicit transaction) yêu cầu rollback. Tầng JDBC/transaction manager cần khôi phục trạng thái hợp lệ.

**13. Một batch có 5 lệnh và lệnh thứ 3 lỗi, các lệnh 4–5 có luôn không chạy?**

Không bảo đảm. Driver có thể dừng hoặc tiếp tục. Đọc update counts/next exceptions và xử lý transaction.

**14. Khi JDBC trả SQLIntegrityConstraintViolationException, có thể luôn trả HTTP 409 không?**

Không. API/domain/security policy xác định response phù hợp. Chỉ map sang domain error cụ thể khi đã xác minh constraint.

**15. Vì sao không đưa ex.getMessage() thẳng tới người dùng?**

Có thể lộ cấu trúc DB, tên cột/constraint, SQL text, dữ liệu nhạy cảm, và message thay đổi theo driver/ngôn ngữ.

**16. Nếu driver chỉ ném SQLException chung có SQLState bắt đầu 23, có thể coi là integrity không?**

Có thể phân loại là nhóm class23 theo convention, nhưng vẫn cần vendor/schema để biết **constraint nào** và mapping nghiệp vụ nào đúng.

**17. Khi rollback cũng lỗi, làm sao giữ nguyên SQLException chính?**

Dùng `failure.addSuppressed(rollbackFailure)` và ném lại primary failure. Đừng thay primary bằng lỗi rollback nếu không có lý do rõ.

**18. Mock Java trong bài có chứng minh PostgreSQL driver ném đúng subclass không?**

Không. Mock tự phát ra exceptions theo design. Muốn biết hành vi driver thực, cần integration test với DBMS và driver version mục tiêu.

## Nguồn chính thức còn hiệu lực

- [Oracle Java SE 26 — `SQLIntegrityConstraintViolationException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLIntegrityConstraintViolationException.html): subclass của SQLNonTransientException, class `23` hoặc vendor conditions, constructors/error code.
- [Oracle Java SE 26 — `SQLDataException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLDataException.html): class `22` và dữ liệu chuyển đổi không hợp lệ.
- [Oracle Java SE 26 — `SQLNonTransientException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLNonTransientException.html): retry không kỳ vọng thành công khi nguyên nhân chưa được sửa.
- [Oracle Java SE 26 — `SQLTransactionRollbackException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransactionRollbackException.html): class `40`, rollback do deadlock/serialization.
- [Oracle Java SE 26 — `SQLException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): `getSQLState`, `getErrorCode`, `getNextException`, Iterable và cause.
- [Oracle Java SE 26 — `BatchUpdateException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/BatchUpdateException.html): update counts, `getLargeUpdateCounts`, driver tiếp tục/dừng.
- [Oracle Java SE 26 — `DataTruncation`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DataTruncation.html): cảnh báo đọc/exception ghi, SQLState 01004/22001.
- [Oracle Java SE 26 — `Connection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): auto-commit, commit, rollback, scope.
- [Oracle Java SE 26 — `PreparedStatement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): parameterized statements và `executeUpdate`.
- [PostgreSQL 18 — Appendix A: Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLState class22/23/40, specific `23505`/`23503`/`23502`/`23514`/`22003`, ý nghĩa hai ký tự đầu.
- [PostgreSQL 18 — Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html): nguyên tắc giao dịch và rollback.

**Ghi nhớ:** `SQLIntegrityConstraintViolationException` liên quan **tính toàn vẹn** (SQLState family `23`), còn `SQLDataException` liên quan **lỗi dữ liệu/chuyển đổi** (family `22`); cả hai đều non-transient. Đừng suy từ chữ “dữ liệu sai” rằng mọi lỗi đều là UNIQUE, cũng đừng suy từ `23505` rằng mọi JDBC driver đều cùng một mã. Hãy kiểm tra **exception class + SQLState + vendor contract + schema**, bảo toàn thông tin lỗi an toàn, **rollback đúng transaction**, không retry y nguyên constraint violation và không xem một chương trình mock là bằng chứng driver thực tế.
