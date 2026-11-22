# Xử lý nhiều tập kết quả và số dòng cập nhật trong thủ tục lưu trữ JPA

Khi gọi một **stored procedure** từ Jakarta Persistence (JPA), nhiều ví dụ đơn giản chỉ làm một trong hai việc: lấy một danh sách entity hoặc thực hiện một thao tác cập nhật. Nhưng trong ứng dụng thực tế, **một lần gọi thủ tục có thể sinh nhiều loại kết quả nối tiếp nhau**:

- Một hoặc nhiều **tập kết quả** (*result sets*) từ các câu `SELECT`.
- Một hoặc nhiều **số dòng bị tác động** (*update counts*) từ các câu `UPDATE`, `INSERT` hoặc `DELETE`.
- Các **tham số đầu ra** (*OUT/INOUT parameters*) do thủ tục gán.
- Có thể cả **giá trị trả về** theo cơ chế riêng của DBMS và driver.

Ví dụ, thủ tục xử lý một lô đơn hàng có thể cập nhật trạng thái đơn, trả danh sách đơn sau cập nhật, đánh dấu lô đã được kiểm tra và trả danh sách nhật ký. Nếu chỉ gọi `getResultList()` một lần hoặc chỉ đọc một số dòng cập nhật, ứng dụng có thể bỏ sót dữ liệu hoặc hiểu sai kết quả thực thi.

Trong JPA, công cụ quan trọng là **`StoredProcedureQuery`** với các phương thức:

```java
boolean isResultSet = procedure.execute();

List<?> rows = procedure.getResultList();

int updateCount = procedure.getUpdateCount();

boolean nextIsResultSet = procedure.hasMoreResults();
```

Cách dùng đúng không phải gọi cả bốn phương thức liên tiếp một cách tùy ý. Chúng phối hợp thành một **quy trình duyệt các kết quả hiện tại và chuyển sang kết quả tiếp theo**.

> **Quy tắc quan trọng nhất:** `hasMoreResults() == false` **không nhất thiết có nghĩa đã hết kết quả**. Nó cũng có thể có nghĩa kết quả kế tiếp là **update count**, không phải result set. Muốn biết thật sự hết chưa, cần kết hợp với `getUpdateCount() == -1` tại đúng thời điểm.

Bài học này trình bày mô hình kết quả, cú pháp và vòng đời `StoredProcedureQuery`, ví dụ thủ tục SQL Server trả nhiều result sets xen kẽ update counts, cách lấy OUT parameters, ánh xạ kết quả, quản lý transaction, lưu ý khác biệt giữa DBMS/provider và các tình huống thường gặp.

## 1. Một lần gọi procedure có thể trả những gì?

Giả sử ứng dụng gọi một stored procedure:

```text
CALL process_order_batch(batchId = 77, targetStatus = 'APPROVED')
```

Bên trong thủ tục có thể thực hiện:

```text
1. UPDATE orders ...
       -> update count: 2

2. SELECT order_id, customer_name, status FROM orders ...
       -> result set #1: 3 hàng

3. UPDATE batch_jobs ...
       -> update count: 1

4. SELECT audit_id, event_type, event_at FROM order_audit ...
       -> result set #2: 2 hàng

5. Gán OUT parameter affectedOrders = 2
```

Từ góc nhìn ứng dụng, kết quả không chỉ là một danh sách:

```text
Một lần thực thi thủ tục
    |
    +-- Phần 1: UPDATE_COUNT (2)
    |
    +-- Phần 2: RESULT_SET (orders)
    |
    +-- Phần 3: UPDATE_COUNT (1)
    |
    +-- Phần 4: RESULT_SET (audit)
    |
    +-- OUT parameter: affectedOrders = 2
```

Tuy vậy, **những phần nào thực sự được JDBC driver/JPA provider phơi bày** còn phụ thuộc DBMS, cách viết procedure, driver, cấu hình xử lý row count và hỗ trợ của provider. Danh sách trên là thứ tự logic của ví dụ, không phải cam kết mọi môi trường đều báo chính xác cùng số phần.

### 1.1. Result set là gì?

Một **result set** là tập hàng do một câu truy vấn trả về, chẳng hạn:

```sql
SELECT order_id, customer_name, status
FROM orders
WHERE batch_id = 77;
```

Kết quả minh họa:

| order_id | customer_name | status |
| ---: | --- | --- |
| 501 | An | APPROVED |
| 502 | Bình | APPROVED |
| 503 | Chi | APPROVED |

Trong `StoredProcedureQuery`, khi kết quả hiện tại là result set, ta lấy các hàng bằng:

```java
List<?> rows = procedure.getResultList();
```

Tùy mapping, mỗi phần tử có thể là entity, DTO, `Object[]` hoặc scalar value.

**Result set rỗng** vẫn là một result set hợp lệ. Danh sách Java có thể rỗng, nhưng không có nghĩa thủ tục hết kết quả hoặc không thực thi thành công.

### 1.2. Update count là gì?

**Update count** biểu diễn số dòng bị tác động theo kết quả mà DBMS/driver báo cho một câu lệnh DML hoặc một phần thực thi có update count.

Ví dụ:

```sql
UPDATE orders
SET status = 'APPROVED'
WHERE batch_id = 77 AND status <> 'APPROVED';
```

Nếu hai hàng đang ở trạng thái khác và được cập nhật, driver có thể báo:

```text
update count = 2
```

JPA cung cấp:

```java
int affected = procedure.getUpdateCount();
```

Nhưng phải phân biệt các giá trị:

| Giá trị | Ý nghĩa khi đang đọc update count |
| ---: | --- |
| `5` | Có update count với giá trị 5. |
| `1` | Có update count với giá trị 1. |
| `0` | **Có update count với giá trị 0**, vẫn là một kết quả hợp lệ. |
| `-1` | Không có update count hiện tại để đọc; trong quy trình duyệt đúng, có thể là dấu hiệu kết thúc. |

**Không dùng `affected <= 0` để quyết định đã hết kết quả.** Giá trị 0 có thể chỉ là một câu UPDATE không ảnh hưởng dòng nào.

### 1.3. OUT parameter không phải result set

Thủ tục có thể khai báo tham số đầu ra:

```text
affectedOrders OUT INTEGER
```

Sau khi thực thi và xử lý các kết quả cần thiết, ứng dụng lấy nó bằng:

```java
Object value =
    procedure.getOutputParameterValue("AffectedOrders");
```

Giá trị OUT có thể cung cấp một **kết quả nghiệp vụ có tên rõ ràng**. Nó không tự động là result set hay một update count trong chuỗi kết quả JDBC.

Trong một thủ tục có nhiều `SELECT` và DML, việc dùng OUT parameter cho **số đơn thay đổi theo quy tắc nghiệp vụ** thường rõ hơn việc giả định update count đầu tiên luôn là đúng con số cần trả cho client.

## 2. API cốt lõi của StoredProcedureQuery

`StoredProcedureQuery` là giao diện của Jakarta Persistence để mô tả, đăng ký tham số, thực thi và xử lý kết quả thủ tục lưu trữ.

Những phương thức liên quan trực tiếp:

| Phương thức | Vai trò |
| --- | --- |
| `EntityManager.createStoredProcedureQuery(name)` | Tạo query để gọi procedure theo tên. |
| `registerStoredProcedureParameter(...)` | Đăng ký kiểu và mode của tham số. |
| `setParameter(...)` | Bind giá trị của tham số IN/INOUT. |
| `execute()` | Thực thi và cho biết kết quả đầu tiên có phải result set hay không. |
| `getResultList()` | Lấy các hàng của result set hiện tại khi phù hợp. |
| `getSingleResult()` | Lấy một kết quả theo hợp đồng đơn trị, không phải cách duyệt mọi result sets. |
| `getUpdateCount()` | Đọc số dòng cập nhật hiện tại hoặc `-1` nếu không có. |
| `hasMoreResults()` | Tiến tới kết quả tiếp theo và báo nó có phải result set không. |
| `getOutputParameterValue(...)` | Lấy giá trị tham số OUT/INOUT sau khi thực thi. |

Ví dụ đăng ký tham số:

```java
StoredProcedureQuery procedure =
    em.createStoredProcedureQuery("dbo.usp_process_order_batch");

procedure.registerStoredProcedureParameter(
    "BatchId",
    Long.class,
    ParameterMode.IN
);

procedure.registerStoredProcedureParameter(
    "TargetStatus",
    String.class,
    ParameterMode.IN
);

procedure.registerStoredProcedureParameter(
    "AffectedOrders",
    Integer.class,
    ParameterMode.OUT
);
```

Giá trị đầu vào:

```java
procedure.setParameter("BatchId", 77L);
procedure.setParameter("TargetStatus", "APPROVED");
```

Sau đó:

```java
boolean isResultSet = procedure.execute();
```

Giá trị Boolean ở đây là **loại của kết quả đầu tiên**. Nó không có nghĩa thủ tục thành công hoặc thất bại:

- `true`: kết quả đầu tiên là result set.
- `false`: kết quả đầu tiên là update count **hoặc không có kết quả kiểu đó**.

**Không dùng `if (!procedure.execute()) throw ...` để kết luận thủ tục thất bại.** Một thủ tục chỉ cập nhật dữ liệu có thể thực thi thành công nhưng `execute()` trả `false`.

## 3. Hiểu trạng thái kết quả hiện tại

Hãy hình dung `StoredProcedureQuery` như một bộ điều hướng qua chuỗi các phần kết quả.

```text
                 execute()
                     |
                     v
          +----------------------+
          | Current result       |
          +----------------------+
                |          |
          result set    update count / none
                |          |
       getResultList()   getUpdateCount()
                |          |
                +-----+----+
                      |
                hasMoreResults()
                      |
                      v
             Next current result
                      |
                     ...
```

Điều quan trọng là **`execute()` và `hasMoreResults()` báo loại kết quả**, còn `getResultList()`/`getUpdateCount()` đọc **nội dung của kết quả hiện tại**.

### 3.1. execute() trả true

Ví dụ thủ tục bắt đầu bằng:

```sql
SELECT order_id, status
FROM orders
WHERE batch_id = @BatchId;
```

Nếu result set đó được phơi bày là kết quả đầu tiên:

```java
boolean resultSet = procedure.execute();

if (resultSet) {
    List<?> rows = procedure.getResultList();
    // Xử lý tập kết quả đầu tiên.
}
```

Sau khi đọc xong, ứng dụng có thể chuyển sang phần tiếp theo bằng `hasMoreResults()`.

### 3.2. execute() trả false

Giả sử procedure bắt đầu bằng UPDATE:

```sql
UPDATE orders
SET status = @TargetStatus
WHERE batch_id = @BatchId;
```

Kết quả đầu tiên có thể là update count:

```java
boolean resultSet = procedure.execute();

if (!resultSet) {
    int count = procedure.getUpdateCount();

    if (count >= 0) {
        System.out.println("Update count: " + count);
    }
}
```

Nhưng nếu `getUpdateCount() == -1`, có thể không có phần kết quả hiện tại. Cần hiểu con số này theo trạng thái duyệt, không phải coi mọi `execute() == false` là đã xong.

### 3.3. hasMoreResults() trả false

`hasMoreResults()` **di chuyển sang kết quả kế tiếp**. Kết quả Boolean mô tả phần mới:

- `true`: kết quả kế tiếp là result set.
- `false`: kết quả kế tiếp là update count **hoặc không còn kết quả**.

Đây là bẫy:

```java
// Không nên: có thể bỏ sót update counts.
while (procedure.hasMoreResults()) {
    List<?> rows = procedure.getResultList();
}
```

Nếu phần kế tiếp là update count, `hasMoreResults()` trả false và vòng lặp dừng, mặc dù phía sau có thể còn result sets khác.

Muốn duyệt đúng, phải đọc cả hai loại phần, rồi mới đánh giá khi nào thực sự hết.

## 4. Vòng lặp chuẩn để duyệt result sets và update counts

Đây là mẫu xử lý cốt lõi:

```java
boolean isResultSet = procedure.execute();

while (true) {
    if (isResultSet) {
        // Current result là result set.
        List<?> rows = procedure.getResultList();
        processRows(rows);
    } else {
        // Current result là update count hoặc đã hết.
        int count = procedure.getUpdateCount();

        if (count == -1) {
            break; // Không còn phần kết quả để đọc.
        }

        processUpdateCount(count);
    }

    // Chuyển tới phần kế tiếp.
    isResultSet = procedure.hasMoreResults();
}
```

`processRows` và `processUpdateCount` ở đây là các hàm nghiệp vụ minh họa; chúng cần được triển khai nếu đưa đoạn code vào một class thật.

**Thứ tự quan trọng:**

1. Gọi `execute()` **một lần** để bắt đầu.
2. Dựa vào Boolean để chọn cách đọc **phần hiện tại**.
3. Nếu là result set, gọi `getResultList()`.
4. Nếu không phải result set, gọi `getUpdateCount()`.
5. Chỉ dừng khi không có result set và update count là `-1`.
6. Sau khi xử lý phần hiện tại, gọi `hasMoreResults()` để tiến tới phần tiếp theo.

### 4.1. Tại sao count = 0 vẫn phải tiếp tục?

Giả sử:

```text
Current result #1: update count = 0
Next result #2: result set chứa 10 hàng
```

Nếu code viết:

```java
if (count <= 0) {
    break;
}
```

nó sẽ bỏ mất result set thứ hai.

Cách đúng là:

```java
if (count == -1) {
    break;
}
```

**0 là một update count hợp lệ**, không phải sentinel kết thúc.

### 4.2. Vì sao không gọi hasMoreResults() trước khi đọc phần đầu?

Nếu gọi:

```java
procedure.execute();
procedure.hasMoreResults();
```

rồi mới xử lý, lời gọi thứ hai **đã tiến sang phần tiếp theo**. Phần đầu có thể bị bỏ qua. Đây là một lỗi thường gặp khi người viết hiểu `hasMoreResults()` như “chỉ nhìn xem có kết quả khác không” thay vì một phép **tiến trạng thái kết quả**.

### 4.3. Vì sao không gọi getResultList() ở mọi vòng?

Vì phần hiện tại có thể là update count. `getResultList()` là API dành cho phần result set, không phải phép “lấy mọi dữ liệu” cho mọi loại phần. Gọi nó khi phần hiện tại không phải result set có thể dẫn đến `IllegalStateException` hoặc lỗi theo provider.

### 4.4. Không gọi execute() lại để lấy phần thứ hai

`execute()` là thao tác **thực thi stored procedure**. Gọi lại có thể chạy lại các cập nhật và side effects của procedure.

Để đọc phần tiếp theo của **cùng một lần thực thi**, dùng `hasMoreResults()`, không dùng `execute()` lần thứ hai.

## 5. Ví dụ thực tế với SQL Server trả nhiều kết quả

Để thấy rõ update count xen kẽ result sets, ta dùng **Microsoft SQL Server** làm DBMS minh họa. Không phải mọi DBMS hỗ trợ cùng cách trả nhiều tập kết quả; cú pháp tạo procedure ở phần này là **T-SQL**, không phải SQL chuẩn/JPA.

Bài toán: một lô (`batch`) gồm nhiều đơn hàng. Khi xử lý lô, thủ tục cần:

1. Đổi trạng thái các đơn chưa đạt trạng thái đích.
2. Trả danh sách các đơn trong lô.
3. Đánh dấu thời điểm kiểm tra lô.
4. Trả danh sách audit event.
5. Gán tham số OUT cho số đơn đã thay đổi.

### 5.1. Schema tối giản

```sql
CREATE TABLE dbo.batch_jobs (
    batch_id BIGINT NOT NULL PRIMARY KEY,
    last_checked_at DATETIME2(3) NULL
);

CREATE TABLE dbo.orders (
    order_id BIGINT NOT NULL PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    customer_name NVARCHAR(120) NOT NULL,
    status NVARCHAR(20) NOT NULL,
    CONSTRAINT fk_orders_batch
        FOREIGN KEY (batch_id)
        REFERENCES dbo.batch_jobs(batch_id)
);

CREATE TABLE dbo.order_audit (
    audit_id BIGINT NOT NULL PRIMARY KEY,
    batch_id BIGINT NOT NULL,
    event_type NVARCHAR(60) NOT NULL,
    event_at DATETIME2(3) NOT NULL,
    CONSTRAINT fk_audit_batch
        FOREIGN KEY (batch_id)
        REFERENCES dbo.batch_jobs(batch_id)
);
```

Dữ liệu thử:

```sql
INSERT INTO dbo.batch_jobs(batch_id, last_checked_at)
VALUES (77, NULL);

INSERT INTO dbo.orders(
    order_id, batch_id, customer_name, status
)
VALUES
    (501, 77, N'An', N'PENDING'),
    (502, 77, N'Bình', N'PENDING'),
    (503, 77, N'Chi', N'APPROVED');

INSERT INTO dbo.order_audit(
    audit_id, batch_id, event_type, event_at
)
VALUES
    (801, 77, N'BATCH_CREATED', SYSUTCDATETIME()),
    (802, 77, N'BATCH_VALIDATED', SYSUTCDATETIME());
```

### 5.2. Stored procedure T-SQL

```sql
CREATE OR ALTER PROCEDURE dbo.usp_process_order_batch
    @BatchId BIGINT,
    @TargetStatus NVARCHAR(20),
    @AffectedOrders INT OUTPUT
AS
BEGIN
    -- Minh họa update counts từ DML.
    -- Bỏ NOCOUNT ON để driver có cơ hội nhận các counts.
    SET NOCOUNT OFF;

    UPDATE dbo.orders
    SET status = @TargetStatus
    WHERE batch_id = @BatchId
      AND status <> @TargetStatus;

    -- Lưu ngay; @@ROWCOUNT có thể bị ghi đè
    -- bởi các câu lệnh tiếp theo.
    SET @AffectedOrders = @@ROWCOUNT;

    -- Result set #1: tất cả đơn trong lô sau cập nhật.
    SELECT
        order_id,
        customer_name,
        status
    FROM dbo.orders
    WHERE batch_id = @BatchId
    ORDER BY order_id;

    UPDATE dbo.batch_jobs
    SET last_checked_at = SYSUTCDATETIME()
    WHERE batch_id = @BatchId;

    -- Result set #2: nhật ký đã có của lô.
    SELECT
        audit_id,
        event_type,
        event_at
    FROM dbo.order_audit
    WHERE batch_id = @BatchId
    ORDER BY audit_id;
END;
```

Đây là một ví dụ có chủ đích về **nhiều loại kết quả**. Trong ứng dụng thật, việc chọn `SET NOCOUNT ON` hay `OFF` là quyết định API thủ tục: `NOCOUNT ON` thường được dùng để giảm thông điệp row-count không cần thiết, trong khi bài này tắt nó để có thể quan sát update counts. Mỗi driver/provider có thể xử lý các phần từ procedure hơi khác nhau.

**Giá trị `@AffectedOrders` được gán từ `@@ROWCOUNT` ngay sau UPDATE.** Đây là con số nghiệp vụ rõ ràng về số đơn đã đổi trạng thái. Không nên thay bằng “update count thứ mấy của JDBC” vì thủ tục có thể được sửa và phát sinh thêm DML.

### 5.3. Kết quả ý tưởng khi chạy

Lời gọi:

```text
BatchId = 77
TargetStatus = APPROVED
```

Hai đơn #501 và #502 được đổi từ `PENDING` thành `APPROVED`; #503 đã đúng trạng thái.

Kết quả logic có thể gồm:

| Phần | Loại | Nội dung |
| --- | --- | --- |
| 1 | UPDATE_COUNT | 2 đơn được cập nhật |
| 2 | RESULT_SET | 3 đơn trong lô |
| 3 | UPDATE_COUNT | 1 hàng `batch_jobs` được cập nhật |
| 4 | RESULT_SET | 2 dòng audit |
| OUT | AffectedOrders | 2 |

Thứ tự này phản ánh ý định procedure. Trên SQL Server, thông điệp row count từ các statement và việc driver phơi bày chúng có thể ảnh hưởng chi tiết thứ tự/số lượng phần nhìn thấy. Vì vậy code JPA nên **duyệt theo loại**, không giả định “phần 1 chắc chắn là số 2, phần 2 chắc chắn là đơn hàng” khi chưa kiểm chứng môi trường và hợp đồng output.

## 6. Gọi procedure từ JPA và đăng ký tham số

Mẫu gọi bằng `EntityManager`:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

StoredProcedureQuery procedure =
    em.createStoredProcedureQuery(
        "dbo.usp_process_order_batch"
    );

procedure.registerStoredProcedureParameter(
    "BatchId",
    Long.class,
    ParameterMode.IN
);

procedure.registerStoredProcedureParameter(
    "TargetStatus",
    String.class,
    ParameterMode.IN
);

procedure.registerStoredProcedureParameter(
    "AffectedOrders",
    Integer.class,
    ParameterMode.OUT
);

procedure.setParameter("BatchId", 77L);
procedure.setParameter("TargetStatus", "APPROVED");
```

### 6.1. Các mode tham số

| `ParameterMode` | Mô tả |
| --- | --- |
| `IN` | Ứng dụng truyền giá trị vào procedure. |
| `OUT` | Procedure gán giá trị để ứng dụng lấy về. |
| `INOUT` | Có giá trị đầu vào và giá trị đầu ra. |
| `REF_CURSOR` | Dùng với database/provider hỗ trợ cursor output theo cơ chế tương ứng. |

`@AffectedOrders` của T-SQL dùng `OUTPUT` nên ở JPA đăng ký `ParameterMode.OUT`.

### 6.2. Named và positional parameters

JPA cho phép những cách đăng ký phù hợp qua **tên** hoặc **vị trí**, ví dụ:

```java
procedure.registerStoredProcedureParameter(
    1, Long.class, ParameterMode.IN
);
procedure.registerStoredProcedureParameter(
    2, String.class, ParameterMode.IN
);
procedure.registerStoredProcedureParameter(
    3, Integer.class, ParameterMode.OUT
);

procedure.setParameter(1, 77L);
procedure.setParameter(2, "APPROVED");
```

Khi dùng positional parameters, phải bám đúng thứ tự signature thủ tục; không được tự đổi vị trí vì tên Java khác. Cần tránh trộn hai cách đăng ký/binding trong cùng một call nếu không có lý do và chưa kiểm tra provider.

Việc **bind named stored procedure parameters** có thể phụ thuộc driver, dialect và phiên bản JPA provider. Một môi trường nhất định có thể yêu cầu positional registration, dù chương trình minh họa dùng tên cho dễ đọc. Đây là lý do phải tích hợp-test với database/provider đích.

## 7. Ví dụ Java đầy đủ: đọc mọi phần kết quả

Ta định nghĩa một kiểu dữ liệu để giữ các phần được đọc, nhưng không cố diễn giải mọi result set thành cùng một entity.

Đoạn code dưới đây dùng Java 17+ (vì `record`) và Jakarta Persistence:

```java
package com.example.batch;

import java.util.ArrayList;
import java.util.List;
import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

public final class BatchProcedureReader {

    public record Segment(
        int ordinal,
        String kind,
        List<?> rows,
        Integer updateCount
    ) {}

    public record BatchRunResult(
        int affectedOrders,
        List<Segment> segments
    ) {}

    public BatchRunResult run(
            EntityManager em,
            long batchId,
            String targetStatus) {

        StoredProcedureQuery procedure =
            em.createStoredProcedureQuery(
                "dbo.usp_process_order_batch"
            );

        procedure.registerStoredProcedureParameter(
            "BatchId", Long.class, ParameterMode.IN
        );

        procedure.registerStoredProcedureParameter(
            "TargetStatus", String.class, ParameterMode.IN
        );

        procedure.registerStoredProcedureParameter(
            "AffectedOrders", Integer.class, ParameterMode.OUT
        );

        procedure.setParameter("BatchId", batchId);
        procedure.setParameter("TargetStatus", targetStatus);

        List<Segment> segments = new ArrayList<>();
        int ordinal = 0;

        // Chạy procedure đúng một lần.
        boolean isResultSet = procedure.execute();

        while (true) {
            if (isResultSet) {
                // Result set hiện tại.
                List<?> rows = procedure.getResultList();

                segments.add(new Segment(
                    ordinal++,
                    "RESULT_SET",
                    new ArrayList<>(rows),
                    null
                ));
            } else {
                // Update count hiện tại hoặc không còn kết quả.
                int count = procedure.getUpdateCount();

                if (count == -1) {
                    break;
                }

                segments.add(new Segment(
                    ordinal++,
                    "UPDATE_COUNT",
                    List.of(),
                    count
                ));
            }

            // Di chuyển tới phần tiếp theo.
            isResultSet = procedure.hasMoreResults();
        }

        // Đọc OUT sau khi đã xử lý các result sets/counts.
        Object output =
            procedure.getOutputParameterValue("AffectedOrders");

        int affectedOrders = ((Number) output).intValue();

        return new BatchRunResult(
            affectedOrders,
            List.copyOf(segments)
        );
    }
}
```

### 7.1. Cách sử dụng

Giả sử `em` đã được tạo và một transaction đang được quản lý phù hợp:

```java
BatchProcedureReader reader =
    new BatchProcedureReader();

BatchProcedureReader.BatchRunResult result =
    reader.run(em, 77L, "APPROVED");

System.out.println(
    "Business affected orders: " + result.affectedOrders()
);

for (BatchProcedureReader.Segment segment
        : result.segments()) {

    if ("RESULT_SET".equals(segment.kind())) {
        System.out.println(
            "Result set #" + segment.ordinal()
                + ": " + segment.rows().size() + " rows"
        );
    } else {
        System.out.println(
            "Update count #" + segment.ordinal()
                + ": " + segment.updateCount()
        );
    }
}
```

Ở đây chúng ta **ghi nhận mọi phần theo thứ tự mà provider cung cấp**. Hai result sets có thể có cấu trúc hàng khác nhau, vì thế `List<?>` thay vì ép tất cả thành `List<Order>`.

### 7.2. Vì sao đọc OUT sau vòng lặp?

Với thủ tục trả nhiều result sets và update counts, nguyên tắc portable của JPA là **xử lý các kết quả kiểu JDBC trước khi lấy OUT parameters**.

Thay vì:

```java
procedure.execute();

Object count =
    procedure.getOutputParameterValue("AffectedOrders");

// Sau đó mới cố đọc các result sets...
```

nên:

```java
boolean isResultSet = procedure.execute();

// Duyệt tất cả result sets và update counts...

Object count =
    procedure.getOutputParameterValue("AffectedOrders");
```

Một số JDBC drivers yêu cầu hoàn tất/tiến qua phần kết quả trước khi OUT parameters có thể được truy cập một cách đáng tin cậy. Dù provider đôi khi che bớt yêu cầu này, **xử lý result sets/counts trước OUT là cách tổ chức an toàn hơn**.

### 7.3. Vì sao dùng ((Number) output).intValue()?

Một tham số SQL kiểu `INT` thường được provider trả về dưới dạng `Integer`. Việc ép qua `Number` trong ví dụ giúp tránh giả định quá cứng về wrapper numeric trong một số môi trường.

Tuy nhiên, kiểu JPA đã đăng ký là `Integer.class` và procedure đặt OUT ở mọi đường đi; ví dụ giả định `output` không null. Trong ứng dụng thật, nếu OUT có thể null thì cần kiểm tra trước khi chuyển.

### 7.4. Vì sao vẫn lưu các update counts khi đã có OUT?

Các update counts có thể hữu ích để:

- Chẩn đoán hành vi procedure.
- Xác định phần nào của procedure được driver báo đã tác động dữ liệu.
- Kiểm tra hợp đồng thủ tục trong integration tests.
- Phát hiện thay đổi không mong đợi về thứ tự phần kết quả.

Nhưng `affectedOrders` là **kết quả nghiệp vụ có tên**, còn danh sách update counts là **chi tiết thực thi**. Không nên tự cộng mọi update count thành “số đơn được xử lý”; câu UPDATE trên `batch_jobs` cũng tạo update count dù không cập nhật một đơn nào.

## 8. Phân tích vòng lặp theo từng bước

Giả sử provider phơi bày chính xác chuỗi:

```text
C0: UPDATE_COUNT(2)
C1: RESULT_SET(3 orders)
C2: UPDATE_COUNT(1)
C3: RESULT_SET(2 audits)
C4: END
```

Luồng vòng lặp:

| Bước | Giá trị `isResultSet` | API đọc | Dữ liệu | Sau đó |
| --- | --- | --- | --- | --- |
| 1 | `false` từ `execute()` | `getUpdateCount()` | 2 | `hasMoreResults()` sang C1 |
| 2 | `true` | `getResultList()` | 3 đơn | `hasMoreResults()` sang C2 |
| 3 | `false` | `getUpdateCount()` | 1 | `hasMoreResults()` sang C3 |
| 4 | `true` | `getResultList()` | 2 audit | `hasMoreResults()` sang C4 |
| 5 | `false` | `getUpdateCount()` | -1 | Dừng |

Giá trị `false` xuất hiện ở bước 1, 3 và 5, nhưng chỉ **bước 5** kết thúc.

### 8.1. Trường hợp đầu tiên đã là result set

Nếu procedure bắt đầu bằng SELECT:

```text
RESULT_SET -> UPDATE_COUNT -> RESULT_SET -> END
```

`execute()` có thể trả `true`. Vòng lặp sẽ đọc result set đầu tiên, rồi đi tới update count, rồi result set tiếp theo như bình thường.

Không cần viết một vòng lặp hoàn toàn khác chỉ vì result đầu là SELECT.

### 8.2. Trường hợp không có result set

Một procedure chỉ thực hiện DML có thể trả:

```text
UPDATE_COUNT(4) -> END
```

Vòng lặp ghi nhận count 4 và kết thúc khi `getUpdateCount() == -1`.

Nếu `SET NOCOUNT ON` hoặc driver không phơi bày row counts, có thể chỉ quan sát:

```text
END
```

Điều này **không tự chứng minh procedure chưa cập nhật dữ liệu**. Muốn biết con số nghiệp vụ, dùng OUT parameter hoặc một kết quả có hợp đồng rõ ràng.

### 8.3. Trường hợp có update count = 0

Ví dụ chạy lại procedure với cùng trạng thái `APPROVED`:

```text
UPDATE_COUNT(0) -> RESULT_SET -> UPDATE_COUNT(1)
               -> RESULT_SET -> END
```

Không có đơn nào phải đổi trạng thái, nhưng thủ tục vẫn thực hiện SELECT và cập nhật `batch_jobs`. Vòng lặp đúng vẫn đọc tất cả các phần.

**Đây là tình huống kiểm tra quan trọng** để phát hiện code vô tình dùng `count == 0` làm điều kiện dừng.

## 9. Đọc các hàng của nhiều result sets

Trong ví dụ procedure, tập kết quả đầu tiên có cột:

```text
order_id | customer_name | status
```

tập kết quả thứ hai có cột:

```text
audit_id | event_type | event_at
```

Nếu tạo stored procedure query **không cấu hình entity/SQL result mapping**, kết quả nhiều cột thường được trả dưới dạng `Object[]` cho từng hàng; kiểu scalar cụ thể phụ thuộc provider/driver.

Ví dụ xử lý:

```java
List<?> rows = procedure.getResultList();

for (Object row : rows) {
    if (row instanceof Object[] columns) {
        System.out.println(
            java.util.Arrays.toString(columns)
        );
    } else {
        // Có thể là scalar hoặc kiểu đã được mapping.
        System.out.println(row);
    }
}
```

### 9.1. Không ép mọi result set thành một entity

Nếu query được tạo:

```java
em.createStoredProcedureQuery(
    "dbo.usp_process_order_batch",
    OrderEntity.class
);
```

nhưng procedure trả **cả danh sách đơn và danh sách audit với cấu trúc cột khác nhau**, không nên mặc định mọi hàng của mọi result set đều ánh xạ được thành `OrderEntity`.

Với nhiều result sets không cùng cấu trúc, có thể:

1. Dùng kết quả thô `List<?>` rồi map rõ từng tập sau khi đã xác định đúng hợp đồng.
2. Khai báo nhiều `@SqlResultSetMapping` tương ứng nếu provider và JPA version hỗ trợ đúng.
3. Tách procedure thành các lệnh gọi riêng khi hợp đồng dữ liệu quá phức tạp.
4. Dùng JDBC `CallableStatement` trực tiếp nếu cần kiểm soát chính xác nhiều result sets/driver-specific features.

**Không chọn mapping chỉ dựa vào việc query đầu tiên có những cột khớp entity**. Phải xem toàn bộ chuỗi phần kết quả.

### 9.2. Thứ tự result sets cần được mô tả như một hợp đồng

Giả sử application định nghĩa:

```text
Result set #1 = đơn hàng
Result set #2 = audit events
```

Tầng procedure phải giữ thứ tự đó ổn định, và code Java phải hiểu rằng **update counts có thể xen giữa**. Khi lưu các result sets, có thể đánh số **chỉ riêng các tập kết quả** thay vì dùng ordinal của mọi phần.

Ví dụ:

```java
int resultSetIndex = 0;
boolean isResultSet = procedure.execute();

while (true) {
    if (isResultSet) {
        List<?> rows = procedure.getResultList();

        if (resultSetIndex == 0) {
            // Map danh sách đơn hàng.
        } else if (resultSetIndex == 1) {
            // Map danh sách audit.
        }

        resultSetIndex++;
    } else {
        int count = procedure.getUpdateCount();
        if (count == -1) {
            break;
        }
        // Ghi nhận hoặc bỏ qua update count theo hợp đồng.
    }

    isResultSet = procedure.hasMoreResults();
}
```

Nếu sau này procedure thêm một SELECT debug ở đầu, cách ánh xạ dựa trên vị trí sẽ bị lệch. Vì vậy **không trả các SELECT debug tùy ý** từ procedure production có hợp đồng nhiều result sets.

## 10. Chuyển từng result set thành DTO

Không phải ứng dụng nào cũng cần trả `Object[]` ra tầng service. Để code rõ hơn, có thể map sang những DTO chuyên biệt.

Ví dụ:

```java
package com.example.batch;

public record OrderRow(
    long orderId,
    String customerName,
    String status
) {}

public record AuditRow(
    long auditId,
    String eventType,
    Object eventAt
) {}
```

Ở DTO thứ hai, ví dụ dùng `Object eventAt` để giữ tính trung lập khi JPA provider/driver có thể trả kiểu thời gian khác nhau (chẳng hạn `java.sql.Timestamp`). Trong code thực tế, nên chuẩn hóa thành kiểu thời gian cụ thể sau khi đã xác nhận mapping.

### 10.1. Hàm chuyển một hàng đơn

```java
static OrderRow toOrderRow(Object raw) {
    if (!(raw instanceof Object[] values)
            || values.length != 3) {
        throw new IllegalStateException(
            "Unexpected order result shape"
        );
    }

    long id = ((Number) values[0]).longValue();
    String name = (String) values[1];
    String status = (String) values[2];

    return new OrderRow(id, name, status);
}
```

### 10.2. Hàm chuyển một hàng audit

```java
static AuditRow toAuditRow(Object raw) {
    if (!(raw instanceof Object[] values)
            || values.length != 3) {
        throw new IllegalStateException(
            "Unexpected audit result shape"
        );
    }

    long id = ((Number) values[0]).longValue();
    String event = (String) values[1];
    Object at = values[2];

    return new AuditRow(id, event, at);
}
```

Cách map này minh họa **kiểm tra số cột và chuyển kiểu có chủ đích**. Nó giả định provider trả `Object[]` theo thứ tự cột SELECT. Để có tính portable cao hơn, đặc biệt khi nhiều provider, cần xem xét `@SqlResultSetMapping` và contract của driver.

### 10.3. Đừng đoán result set theo số hàng

Một lỗi nguy hiểm:

```java
if (rows.size() == 3) {
    // Nghĩ đây chắc chắn là danh sách đơn.
}
```

Số hàng có thể thay đổi theo dữ liệu. Result set đơn có thể chứa 0, 3 hoặc 300 hàng; result set audit cũng vậy. Phải xác định loại tập theo **thứ tự/hợp đồng mapping**, không theo row count.

### 10.4. Không giả định mọi trường numeric đều là Integer

Cột SQL `BIGINT` thường cần ánh xạ sang `Long`, nhưng khi nhận kết quả native chưa có type mapping, một số provider/driver có thể dùng những lớp số khác nhau. Chuyển qua `Number.longValue()` cho ví dụ đơn giản giúp tránh hardcast sai wrapper.

Với tiền hoặc số có độ chính xác cao, phải bảo toàn `BigDecimal`/precision theo mapping, không ép vô điều kiện sang `double`.

## 11. @SqlResultSetMapping với nhiều tập kết quả

JPA hỗ trợ khai báo **`@SqlResultSetMapping`** để map hàng SQL trả về thành entity, scalar hoặc DTO bằng constructor.

Ví dụ muốn map result set đơn hàng:

```java
@SqlResultSetMapping(
    name = "OrderRowMapping",
    classes = @ConstructorResult(
        targetClass = com.example.batch.OrderRowDto.class,
        columns = {
            @ColumnResult(name = "order_id", type = Long.class),
            @ColumnResult(name = "customer_name", type = String.class),
            @ColumnResult(name = "status", type = String.class)
        }
    )
)
```

Và audit:

```java
@SqlResultSetMapping(
    name = "AuditRowMapping",
    classes = @ConstructorResult(
        targetClass = com.example.batch.AuditRowDto.class,
        columns = {
            @ColumnResult(name = "audit_id", type = Long.class),
            @ColumnResult(name = "event_type", type = String.class),
            @ColumnResult(name = "event_at")
        }
    )
)
```

Các annotation trên phải được khai báo tại vị trí JPA cho phép (chẳng hạn trên entity được quản lý), không phải đặt như statement Java độc lập. `OrderRowDto` và `AuditRowDto` cần constructor khớp thứ tự/kiểu tham số.

Ví dụ class DTO:

```java
package com.example.batch;

public class OrderRowDto {
    private final Long orderId;
    private final String customerName;
    private final String status;

    public OrderRowDto(
            Long orderId,
            String customerName,
            String status) {
        this.orderId = orderId;
        this.customerName = customerName;
        this.status = status;
    }

    public Long getOrderId() { return orderId; }
    public String getCustomerName() { return customerName; }
    public String getStatus() { return status; }
}
```

Khi có nhiều result set mappings đã đăng ký, JPA có overload cho phép truyền các tên mapping:

```java
StoredProcedureQuery procedure =
    em.createStoredProcedureQuery(
        "dbo.usp_process_order_batch",
        "OrderRowMapping",
        "AuditRowMapping"
    );
```

Danh sách mappings tương ứng **thứ tự các result sets**, không có nghĩa một update count cũng được coi là một result set cần mapping.

### 11.1. Cần kiểm chứng với provider và driver

Hỗ trợ nhiều result sets và mapping kết quả stored procedure có những khác biệt thực tế giữa DBMS/provider, nhất là khi procedure còn trả update counts và OUT parameters. Việc đăng ký nhiều resultSetMappings có ở API JPA không đồng nghĩa mọi dialect/provider đều triển khai đúng như nhau trong mọi driver configuration.

Khi dùng Hibernate ORM, EclipseLink hoặc provider khác, phải làm **integration test với database thật** cho thủ tục nhiều result sets. Kiểm tra cả:

- Thứ tự hai tập kết quả.
- Cấu trúc và bí danh cột.
- Kiểu numeric/timestamp thực tế.
- Các update counts xen giữa.
- OUT parameter.
- Trạng thái transaction sau khi đọc hết.

### 11.2. Không nên ép entity mapping vào dữ liệu báo cáo

Nếu một result set chỉ trả một số cột của entity, việc map trực tiếp thành managed entity có thể không phù hợp. Entity JPA thường yêu cầu identity, field mapping và lifecycle riêng.

Với báo cáo hoặc tổng hợp nhiều bảng, DTO/projection là lựa chọn dễ kiểm soát hơn. Đừng tạo một entity giả chỉ để giải quyết một tập kết quả không có identity.

## 12. @NamedStoredProcedureQuery

Thay vì tạo/query/register tham số ở mỗi lần gọi, JPA còn cho phép định nghĩa thủ tục bằng annotation.

Ví dụ trên một entity đã được quản lý:

```java
@NamedStoredProcedureQuery(
    name = "BatchJob.processOrders",
    procedureName = "dbo.usp_process_order_batch",
    parameters = {
        @StoredProcedureParameter(
            name = "BatchId",
            mode = ParameterMode.IN,
            type = Long.class
        ),
        @StoredProcedureParameter(
            name = "TargetStatus",
            mode = ParameterMode.IN,
            type = String.class
        ),
        @StoredProcedureParameter(
            name = "AffectedOrders",
            mode = ParameterMode.OUT,
            type = Integer.class
        )
    }
)
```

Đây là fragment annotation; để chạy cần đặt trên một managed class thích hợp, import `jakarta.persistence.*` và bảo đảm entity/persistence unit chứa named procedure definition.

Sử dụng:

```java
StoredProcedureQuery procedure =
    em.createNamedStoredProcedureQuery(
        "BatchJob.processOrders"
    );

procedure.setParameter("BatchId", 77L);
procedure.setParameter("TargetStatus", "APPROVED");
```

Sau đó vẫn dùng vòng lặp `execute()`, `getResultList()`, `getUpdateCount()` và `hasMoreResults()`.

### 12.1. NamedStoredProcedureQuery không tự giải quyết mọi kết quả

Annotation giúp **tập trung metadata tên procedure, tham số và mapping**, nhưng không biến chuỗi nhiều result sets/update counts thành một `List<?>` duy nhất. Nếu procedure trả nhiều phần, code vẫn phải xử lý từng phần theo đúng hợp đồng.

Một số cấu hình named procedure có thể khai báo `resultClasses` hoặc `resultSetMappings`. Với các result sets có cấu trúc khác nhau, chọn đúng mapping và kiểm tra sự tương thích với provider.

## 13. OUT, INOUT và REF_CURSOR

Thủ tục có thể kết hợp tham số với result sets.

### 13.1. OUT

Ví dụ:

```java
procedure.registerStoredProcedureParameter(
    "AffectedOrders",
    Integer.class,
    ParameterMode.OUT
);
```

Sau khi thực thi và xử lý kết quả phù hợp:

```java
Integer affectedOrders =
    (Integer) procedure.getOutputParameterValue(
        "AffectedOrders"
    );
```

Với thủ tục SQL Server đã trình bày, OUT được gán bằng số đơn thực sự được UPDATE.

### 13.2. INOUT

Với một thủ tục có tham số vừa nhận vừa xuất giá trị:

```java
procedure.registerStoredProcedureParameter(
    "CurrentSequence",
    Long.class,
    ParameterMode.INOUT
);

procedure.setParameter("CurrentSequence", 100L);
```

Sau khi chạy:

```java
Long updatedSequence =
    (Long) procedure.getOutputParameterValue(
        "CurrentSequence"
    );
```

`INOUT` có hai vai trò: nhận một giá trị ban đầu và trả giá trị sau khi procedure xử lý. Không được bỏ bước bind đầu vào nếu procedure yêu cầu nó.

### 13.3. REF_CURSOR là trường hợp khác

Một số DBMS (thường được nhắc tới với Oracle, PostgreSQL và cách gọi khác nhau) sử dụng **cursor output**. JPA có `ParameterMode.REF_CURSOR`:

```java
procedure.registerStoredProcedureParameter(
    "result_cursor",
    void.class,
    ParameterMode.REF_CURSOR
);
```

Cú pháp ví dụ chỉ minh họa mode. **Không coi `void.class` hoặc tên cursor trên là portable cho mọi DBMS/provider.** Các hệ thống Oracle/PostgreSQL/driver có yêu cầu riêng về kiểu, tên/vị trí parameter, cách transaction giữ cursor và cách đọc kết quả.

Đặc biệt, thủ tục SQL Server minh họa trước đó dùng **các SELECT thông thường tạo result sets**, không phải một OUT `REF_CURSOR`. Không trộn hai mô hình vì cùng có từ “result”.

### 13.4. Portable result processing order

Khi stored procedure trả kết quả dạng JDBC và OUT parameters, thứ tự nên theo nguyên tắc:

```text
1. Đăng ký parameter.
2. Bind IN và INOUT.
3. execute().
4. Đọc result sets và update counts.
5. Đọc OUT/INOUT parameter values.
6. Kết thúc transaction / đóng context.
```

Thứ tự này giảm nguy cơ gặp khác biệt driver liên quan tới output values và tài nguyên của result sets.

## 14. SET NOCOUNT trên SQL Server thay đổi điều gì?

Trong SQL Server, `SET NOCOUNT` điều khiển việc gửi thông điệp về số dòng bị tác động cho nhiều statement T-SQL.

### 14.1. SET NOCOUNT OFF

```sql
SET NOCOUNT OFF;
```

Driver có thể nhận các thông điệp row count. Điều này giúp minh họa cách update counts xuất hiện cùng result sets.

Nhưng có những điểm cần nhớ:

- Số update count mà JPA provider phơi bày không nhất thiết đúng bằng số câu UPDATE bạn nhìn thấy trong source.
- Procedure có thêm triggers/nested procedures/SQL statements có thể tạo các counts khác.
- Một số client/provider bỏ qua hoặc hợp nhất những thông điệp nhất định.
- Không nên dựa vào vị trí một update count nếu cần số liệu nghiệp vụ ổn định.

### 14.2. SET NOCOUNT ON

```sql
SET NOCOUNT ON;
```

Thường được sử dụng trong stored procedures production khi ứng dụng không cần các row count messages của từng statement. Kết quả có thể gọn hơn, nhưng:

**Bật NOCOUNT ON không có nghĩa UPDATE không xảy ra.** Nó ảnh hưởng thông điệp row count được gửi, không phải chính thao tác cập nhật dữ liệu.

Nếu ứng dụng cần “số đơn đã xử lý”, một OUT parameter được gán đúng thời điểm bằng `@@ROWCOUNT` hoặc một result set có trường `affected_orders` thường rõ ràng hơn.

### 14.3. @@ROWCOUNT khác getUpdateCount()

Trong T-SQL:

```sql
UPDATE dbo.orders
SET status = @TargetStatus
WHERE batch_id = @BatchId
  AND status <> @TargetStatus;

SET @AffectedOrders = @@ROWCOUNT;
```

`@@ROWCOUNT` là giá trị trong **ngữ cảnh thực thi T-SQL của thủ tục**, biểu thị số dòng chịu ảnh hưởng của statement liên quan.

`getUpdateCount()` là kết quả mà **JPA provider/driver phơi bày cho Java** ở một phần cụ thể trong chuỗi kết quả.

Hai con số có thể trùng ở trường hợp đơn giản nhưng không nên coi là một API tương đương. OUT parameter do thủ tục tự gán có hợp đồng nghiệp vụ mạnh và rõ hơn khi có nhiều DML statements.

## 15. Có nên cộng tất cả update counts?

Giả sử procedure:

```text
UPDATE orders            -> 2
UPDATE batch_jobs        -> 1
UPDATE notification_log  -> 4
```

Tổng là 7, nhưng **7 không phải số đơn**. Nó chỉ là tổng số hàng tác động của các phần mà driver báo.

Vì vậy, các ý nghĩa khác nhau:

| Số liệu | Ý nghĩa có thể |
| --- | --- |
| Update count của UPDATE orders | Số hàng đơn được statement đó tác động. |
| Update count của UPDATE batch_jobs | Số hàng batch được thay đổi. |
| Update count của INSERT audit | Số hàng audit được tạo. |
| OUT `AffectedOrders` | Số đơn đổi trạng thái theo contract procedure. |
| Số hàng của result set orders | Số đơn được SELECT trả về, không nhất thiết số đơn đã cập nhật. |

Nếu một đơn đã ở trạng thái đích, nó có thể xuất hiện trong result set orders nhưng **không được UPDATE lần này**.

### 15.1. Đừng dùng rows.size() thay cho update count

```java
List<?> orders = procedure.getResultList();

int affected = orders.size(); // Không chắc là số đơn thay đổi!
```

Trong ví dụ, `orders.size() == 3` nhưng `AffectedOrders == 2`.

`rows.size()` chỉ là số hàng **trả về bởi SELECT hiện tại**. Nó không tự cho biết bao nhiêu hàng đã được sửa.

### 15.2. Update count = 0 chưa chắc nghiệp vụ thất bại

Nếu procedure được thiết kế idempotent (chỉ cập nhật khi status khác target), chạy lần thứ hai có thể đổi **0 đơn** vì tất cả đã APPROVED. Điều này có thể là kết quả hợp lệ.

Tuy nhiên, một batch ID không tồn tại cũng có thể cho update count 0. Nếu cần phân biệt “không có batch” và “batch hợp lệ nhưng không có gì thay đổi”, procedure phải có logic xác minh/OUT status riêng.

## 16. Duyệt nhiều result sets mà không dùng quá nhiều bộ nhớ

`getResultList()` là phương thức trả danh sách kết quả. Nếu procedure trả hàng triệu rows, lưu tất cả `List<?>` của nhiều result sets trong một object có thể tốn nhiều RAM.

Ví dụ lớp `BatchProcedureReader` trước đó ghi mọi `Segment` vào một list để **minh họa cơ chế duyệt**; đó không phải thiết kế tối ưu cho export dữ liệu lớn.

Khi dữ liệu lớn, cân nhắc:

- Chỉ chọn cột cần thiết trong procedure.
- Chia yêu cầu thành các thủ tục/truy vấn có phân trang nếu domain cho phép.
- Tránh trả toàn bộ lịch sử audit trong cùng call vốn chỉ cần trạng thái batch.
- Dùng JDBC streaming/cursor với driver phù hợp nếu JPA không đáp ứng yêu cầu.
- Thiết kế DTO/projection nhẹ thay vì khởi tạo hàng nghìn managed entities.
- Theo dõi kích thước result sets và thời gian giữ connection/transaction.

Không nên giả định rằng đặt `setMaxResults(100)` trên `StoredProcedureQuery` sẽ giới hạn được mọi result set bên trong thủ tục theo cách portable. Với nhiều result sets, cơ chế giới hạn và khả năng thực thi khác nhau giữa provider/driver; nên giới hạn từ chính procedure hoặc dùng phương án API khác đã được kiểm chứng.

## 17. Thời điểm đọc kết quả và vòng đời transaction

Stored procedure có thể thực hiện DML. Vì vậy, nó cần được gọi trong một **transaction hợp lệ** nếu ứng dụng muốn các thay đổi được cam kết/rollback như một đơn vị.

Với Java SE `RESOURCE_LOCAL`:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        BatchProcedureReader reader =
            new BatchProcedureReader();

        BatchProcedureReader.BatchRunResult result =
            reader.run(em, 77L, "APPROVED");

        // Có thể kiểm tra result và business invariants.

        tx.commit();

        System.out.println(
            "Affected orders: " + result.affectedOrders()
        );
    } catch (RuntimeException ex) {
        try {
            if (tx.isActive()) {
                tx.rollback();
            }
        } catch (RuntimeException rollbackEx) {
            ex.addSuppressed(rollbackEx);
        }
        throw ex;
    }
} finally {
    em.close();
}
```

**Thứ tự: thực thi → xử lý kết quả → commit → phản hồi thành công.**

Không thông báo “đã cập nhật đơn thành công” chỉ vì `execute()` đã trả một Boolean. Lỗi constraint hoặc optimistic/concurrency-related issue vẫn có thể xảy ra trong transaction; provider hoặc database có thể rollback.

### 17.1. Flush trước procedure khi có thay đổi pending

Giả sử trong cùng EntityManager, ứng dụng đã thay đổi một managed entity nhưng chưa flush, sau đó procedure cần đọc trạng thái mới.

```java
OrderEntity order = em.find(OrderEntity.class, orderId);
order.setStatus("READY");

// Procedure có thể đọc trực tiếp từ bảng orders.
// Nếu cần dữ liệu vừa sửa, phải xét flush.
em.flush();

callProcedure(em);
```

`em.flush()` đồng bộ thay đổi đang chờ xuống database **trong transaction**, nhưng **không commit**.

Nếu procedure đọc bảng bằng SQL và business rule cần thấy state mới, việc flush có chủ đích có thể cần thiết. Không nên mặc định mọi lời gọi stored procedure đều tự flush đúng những changes đang pending trên mọi provider/flush mode.

### 17.2. Procedure sửa database có thể khiến managed entities lỗi thời

Ngược lại:

```java
OrderEntity order = em.find(OrderEntity.class, orderId);

callProcedureThatUpdatesOrder(em, orderId);

// order Java có thể vẫn giữ status cũ.
```

JPA persistence context không tự biết mọi thay đổi mà procedure thực thi trực tiếp tại database. Nếu tiếp tục dùng managed entity đã tải, có thể cần:

```java
em.refresh(order);
```

hoặc:

```java
em.clear();
OrderEntity fresh = em.find(OrderEntity.class, orderId);
```

**Cẩn trọng:** `refresh()` có thể ghi đè thay đổi chưa flush của entity; `clear()` detach tất cả managed entities, có thể khiến thay đổi chưa flush không còn được đồng bộ. Cần thiết kế luồng dữ liệu rõ ràng, không dùng các lệnh này như biện pháp xử lý mặc định thiếu suy nghĩ.

### 17.3. OUT parameter không đồng nghĩa đã commit

Ngay cả khi:

```java
int affected = ((Number)
    procedure.getOutputParameterValue("AffectedOrders")
).intValue();
```

trả `2`, các update đó vẫn có thể đang nằm trong transaction **chưa commit**. Nếu transaction rollback sau đó, hai hàng không được cam kết thay đổi như procedure đã tạm thực hiện.

Do đó khi trả kết quả API, phân biệt:

- “Procedure báo đã tác động 2 hàng trong transaction”.
- “Transaction đã commit thành công”.

Hai câu này không phải lúc nào cũng đồng nghĩa.

## 18. Với Spring @Transactional và JTA

Trong một ứng dụng Spring, transaction thường do framework quản lý:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BatchApplicationService {

    @PersistenceContext
    private EntityManager em;

    private final BatchProcedureReader reader =
        new BatchProcedureReader();

    @Transactional
    public BatchProcedureReader.BatchRunResult process(
            long batchId, String targetStatus) {
        return reader.run(em, batchId, targetStatus);
    }
}
```

Ở đây:

- `@Transactional` khai báo ranh giới transaction.
- Không tự gọi `em.getTransaction().begin()` trên EntityManager do Spring/container quản lý.
- Procedure và các thao tác JPA khác có thể tham gia transaction tương ứng, tùy cấu hình transaction manager.
- Commit xảy ra sau khi method trả về qua transaction interceptor; exception ở giai đoạn commit vẫn có thể tới caller.

### 18.1. Không nuốt ngoại lệ để báo thành công

Không nên:

```java
@Transactional
public boolean process(long id) {
    try {
        // Stored procedure updates data...
        return true;
    } catch (RuntimeException ex) {
        return false; // Có thể che lỗi và ảnh hưởng rollback policy.
    }
}
```

Nếu lỗi persistence làm transaction không còn hợp lệ, việc bắt rồi trả bình thường có thể dẫn tới commit lỗi hoặc thông điệp không rõ. Hãy để transaction manager rollback theo chính sách hoặc đánh dấu rollback-only chủ động nếu phải xử lý exception trong transaction.

### 18.2. Resource-local khác JTA

`EntityTransaction` chỉ dành cho EntityManager thuộc persistence unit `RESOURCE_LOCAL`. JTA EntityManager có giao dịch do container/transaction manager điều phối; không dùng `em.getTransaction()` để tự begin/commit.

Dù transaction thuộc kiểu nào, **quy tắc duyệt result sets và update counts của StoredProcedureQuery vẫn là phần logic riêng** cần xử lý đúng.

## 19. Vòng đời tài nguyên khi đọc nhiều kết quả

Một procedure có nhiều result sets có thể giữ JDBC resources, statement và connection lâu hơn một SELECT nhỏ.

Một số thực hành tốt:

1. Mở EntityManager trong phạm vi đơn vị công việc rõ ràng.
2. Bắt đầu transaction trước các thao tác DML của procedure.
3. Duyệt các result sets/update counts theo đúng thứ tự.
4. Lấy OUT parameters sau khi xử lý các phần cần thiết.
5. Đóng/giải phóng tài nguyên qua vòng đời EntityManager/transaction hoặc cơ chế được framework quản lý.
6. Không trả một `StoredProcedureQuery` chưa xử lý ra khỏi service rồi đóng EntityManager.
7. Tránh giữ transaction mở trong lúc truyền một response HTTP lớn cho client.

### 19.1. Không share StoredProcedureQuery giữa thread

`StoredProcedureQuery` gắn với EntityManager và chứa state: registered parameters, bindings, trạng thái thực thi và con trỏ các phần kết quả.

Không dùng một instance làm singleton để nhiều request cùng gọi `execute()`/`hasMoreResults()`. Điều này có thể làm dữ liệu các request xen nhau và không phải cách dùng JPA an toàn.

### 19.2. Không dùng hasMoreResults để nhìn trước

Một procedure có bốn phần kết quả. Nếu trong một thread A code gọi `hasMoreResults()` để “kiểm tra”, rồi thread B gọi tiếp, cả hai đều làm thay đổi con trỏ kết quả. Ngay cả trong một thread, gọi nhiều lần mà không đọc phần hiện tại có thể làm bỏ kết quả.

Cách tổ chức rõ nhất là **một vòng lặp tuần tự, một nơi sở hữu StoredProcedureQuery**, không để nhiều tầng service cùng điều khiển con trỏ.

## 20. Đếm hàng do SELECT khác đếm hàng do UPDATE

Một procedure vừa cập nhật vừa SELECT có ít nhất ba dạng con số:

### 20.1. Số dòng bị statement UPDATE tác động

```java
int updateCount = procedure.getUpdateCount();
```

Đây là số mà driver/provider báo cho **phần update count hiện tại**.

### 20.2. Số hàng trong result set được SELECT trả

```java
List<?> rows = procedure.getResultList();
int selectedRows = rows.size();
```

Đây là số hàng trong **một result set cụ thể**, không đại diện mọi phần kết quả của procedure.

### 20.3. Số liệu nghiệp vụ procedure tính ra

```java
int affectedOrders = ((Number)
    procedure.getOutputParameterValue("AffectedOrders")
).intValue();
```

Đây là một **OUT parameter** do SQL logic quyết định.

Ví dụ đối chiếu:

| Đại lượng | Giá trị |
| --- | ---: |
| UPDATE đổi trạng thái orders | 2 |
| SELECT trả tất cả orders trong batch | 3 |
| UPDATE đánh dấu batch_jobs | 1 |
| SELECT audit rows | 2 |
| OUT AffectedOrders | 2 |

Nếu API muốn “số đơn đã được duyệt” thì có thể là 3; “số đơn đổi trạng thái” là 2; “số phần tử audit” là 2. Những khái niệm này cần đặt tên và định nghĩa rõ.

**Không trả một field tên `affectedRows` mơ hồ nếu người gọi không biết nó thuộc statement nào.**

## 21. Vì sao executeUpdate() không phải API chính cho nhiều result sets?

`Query.executeUpdate()` được dùng cho những truy vấn UPDATE/DELETE và một số tình huống stored procedure được thiết kế để chỉ cần một con số cập nhật.

Nhưng với procedure có:

```text
UPDATE -> SELECT -> UPDATE -> SELECT
```

`executeUpdate()` không phải cơ chế lý tưởng để duyệt mọi phần kết quả. Nó không thay thế chuỗi:

```java
execute()
getResultList()
getUpdateCount()
hasMoreResults()
```

Do đó:

- Nếu procedure chỉ thực hiện một thao tác DML và ứng dụng chỉ cần số dòng, API cập nhật chuyên biệt có thể phù hợp tùy provider.
- Nếu procedure có nhiều result sets hoặc nhiều update counts, dùng **`execute()` và vòng lặp duyệt**.
- Nếu chỉ cần tổng số bản ghi thay đổi theo nghiệp vụ, cân nhắc OUT parameter và thủ tục có hợp đồng rõ, thay vì suy luận từ một count bất kỳ.

### 21.1. getSingleResult() không phải cách lấy result set thứ hai

`getSingleResult()` có nghĩa lấy một kết quả theo hợp đồng đơn trị, không phải “lấy kết quả số 1” hay “lấy tập kết quả tiếp theo”.

Với procedure trả nhiều sets, không dùng:

```java
Object first = procedure.getSingleResult();
Object second = procedure.getSingleResult();
```

và kỳ vọng hai lời gọi tự động chuyển qua hai result sets. Phải quản lý trạng thái bằng `hasMoreResults()`.

## 22. Có nên dùng JDBC CallableStatement trực tiếp?

JPA thuận tiện khi dự án đã dùng EntityManager, mapping và transaction. Tuy nhiên, **stored procedure nhiều result sets phức tạp** là khu vực có thể chịu nhiều khác biệt DBMS/driver/provider.

JDBC có API mức thấp hơn:

```java
CallableStatement stmt =
    connection.prepareCall("{call dbo.usp_process_order_batch(?, ?, ?)}");
```

Với JDBC, có thể duyệt:

```java
boolean isResultSet = stmt.execute();

while (true) {
    if (isResultSet) {
        try (ResultSet rs = stmt.getResultSet()) {
            // Đọc các hàng của result set hiện tại.
        }
    } else {
        int count = stmt.getUpdateCount();
        if (count == -1) {
            break;
        }
        // Xử lý update count hiện tại.
    }

    isResultSet = stmt.getMoreResults();
}
```

Mẫu logic tương tự JPA, nhưng JDBC cho quyền trực tiếp với `ResultSet`, statement/cursor và khả năng driver-specific.

### 22.1. Khi nào nên cân nhắc JDBC?

- Cần streaming rất nhiều hàng theo cách driver hỗ trợ.
- Cần kiểm soát chính xác nhiều result sets với những schema khác nhau.
- Provider JPA không hỗ trợ một loại cursor/OUT parameter riêng của DBMS.
- Có yêu cầu JDBC-specific về fetch size, multiple active result sets, metadata.
- Cần xử lý update counts hoặc warning chi tiết mà tầng JPA không phơi bày đầy đủ.

Nếu ứng dụng đang dùng Spring/JPA và chuyển riêng một thao tác sang JDBC, **phải phối hợp transaction/connection đúng cách**, không tự mở connection khác rồi giả định nó tham gia cùng transaction của EntityManager.

### 22.2. Không trộn result set JDBC và JPA tùy tiện

Khi dùng JDBC thô, code phải đóng `ResultSet`, `CallableStatement` và quản lý kết nối theo đúng framework. Nếu JPA và JDBC cùng dùng một database, việc dùng hai connection khác transaction có thể khiến procedure nhìn thấy trạng thái khác hoặc không có nguyên tử chung.

Cần lựa chọn công cụ dựa trên yêu cầu thực tế, không mặc định JPA luôn bao phủ mọi tính năng thủ tục đặc thù của một DBMS.

## 23. Lỗi thứ tự đọc kết quả và cách khắc phục

### Sai lầm 1 — Chỉ gọi getResultList() một lần

```java
procedure.execute();
List<?> rows = procedure.getResultList();
```

Nếu phần đầu là update count, cách này có thể không hợp lệ. Nếu procedure có nhiều result sets, code cũng bỏ sót các phần sau.

**Cách đúng:** dựa vào `execute()` và duyệt với `hasMoreResults()`.

### Sai lầm 2 — Chỉ lặp khi hasMoreResults() trả true

```java
while (procedure.hasMoreResults()) {
    procedure.getResultList();
}
```

Cách này bỏ phần đầu và có thể dừng ở update count.

**Cách đúng:** xử lý phần đầu từ `execute()`, sau đó chuyển kết quả; khi Boolean false kiểm tra `getUpdateCount()`.

### Sai lầm 3 — Coi false là lỗi hoặc kết thúc

`execute() == false` hoặc `hasMoreResults() == false` có thể đơn giản là **update count hiện tại**.

**Cách đúng:** kiểm tra `getUpdateCount()`.

### Sai lầm 4 — Coi update count = 0 là kết thúc

`0` là một kết quả DML hợp lệ.

**Cách đúng:** chỉ xem `-1` là dấu hiệu không có update count hiện tại trong vòng lặp đang ở nhánh false.

### Sai lầm 5 — Gọi execute() nhiều lần để lấy nhiều result sets

Làm thế có thể chạy lại procedure và lặp tác dụng cập nhật.

**Cách đúng:** `execute()` một lần, `hasMoreResults()` để tiến trong cùng lượt chạy.

### Sai lầm 6 — Dùng getSingleResult() thay cho hasMoreResults()

`getSingleResult()` không phải lệnh next result set.

**Cách đúng:** dùng `getResultList()` trên từng phần result set và `hasMoreResults()` để tiến.

### Sai lầm 7 — Lấy OUT trước khi xử lý result sets

Có thể không portable giữa drivers, đặc biệt với nhiều result sets và update counts.

**Cách đúng:** duyệt các phần trước, rồi lấy OUT parameter.

### Sai lầm 8 — Cộng mọi update count thành số đơn đã xử lý

Procedure có thể cập nhật nhiều bảng. Tổng affected rows không mang một nghĩa nghiệp vụ chung.

**Cách đúng:** lấy OUT parameter chuyên biệt hoặc kết quả được thiết kế có tên.

### Sai lầm 9 — Dùng rows.size() thay cho số dòng cập nhật

Result set có thể chứa những hàng không được thay đổi lần này.

**Cách đúng:** phân biệt selected row count với affected row count.

### Sai lầm 10 — Ánh xạ mọi result set về một entity class

Các sets có thể có cột và kiểu khác nhau.

**Cách đúng:** định nghĩa mapping/DTO riêng theo hợp đồng từng set.

### Sai lầm 11 — Dựa vào số dòng để đoán loại result set

Cả orders và audit có thể cùng có 2 hàng.

**Cách đúng:** xác định thứ tự hoặc mapping kết quả một cách có kiểm soát.

### Sai lầm 12 — Giả định SQL Server NOCOUNT ON làm DML không chạy

NOCOUNT điều khiển thông điệp row count, không phải bản thân UPDATE/DELETE.

**Cách đúng:** đọc OUT contract hoặc kiểm tra dữ liệu đã commit.

### Sai lầm 13 — Nghĩ StoredProcedureQuery tự cập nhật persistence context

Procedure thay đổi database nhưng managed entities đã tải có thể stale.

**Cách đúng:** flush khi cần trước call; refresh/clear/reload có chủ đích sau call.

### Sai lầm 14 — Trả thành công trước commit

OUT parameter có giá trị không chứng minh transaction đã commit.

**Cách đúng:** commit thành công rồi mới xác nhận kết quả nghiệp vụ.

### Sai lầm 15 — Share StoredProcedureQuery giữa nhiều thread

Con trỏ results và parameter bindings là trạng thái mutable.

**Cách đúng:** một query/context phù hợp cho một đơn vị công việc.

### Sai lầm 16 — Không kiểm thử với database/provider thật

Hỗ trợ nhiều result sets phụ thuộc driver/dialect và cách SQL gửi row count.

**Cách đúng:** integration tests trên đúng DBMS, driver và JPA provider dùng trong production.

## 24. Kiểm thử các trường hợp bắt buộc

Đối với một stored procedure có nhiều phần kết quả, nên xây bộ integration tests tối thiểu:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Có ít nhất một hàng đổi trạng thái | OUT affectedOrders và dữ liệu sau UPDATE đúng. |
| Không có hàng nào phải đổi | Update count 0 (nếu được phơi bày) không làm bỏ các result sets sau. |
| Batch không tồn tại | Phân biệt kết quả rỗng với lỗi nghiệp vụ theo contract. |
| Result set orders rỗng | Vẫn đọc được các phần tiếp theo. |
| Result set audit rỗng | Không nhầm result set rỗng với kết thúc chuỗi. |
| Có update count trước SELECT | `execute() == false` vẫn xử lý đúng. |
| Có update count giữa hai SELECT | `hasMoreResults() == false` không làm dừng quá sớm. |
| OUT parameter | Đọc được sau khi duyệt các phần. |
| Procedure phát lỗi DB | Transaction rollback, không trả thành công. |
| Procedure đổi dữ liệu managed đã tải | Context có thể stale; luồng reload xử lý đúng. |
| Thay NOCOUNT ON/OFF | Ứng dụng không phụ thuộc cứng vào số lượng counts. |
| Driver/provider nâng phiên bản | Hợp đồng nhiều result sets vẫn được hỗ trợ. |

### 24.1. Vì sao dùng database thật?

Mock `StoredProcedureQuery` có thể chứng minh vòng lặp Java chọn đúng nhánh, nhưng **không kiểm chứng**:

- Driver trả bao nhiêu update counts.
- Thứ tự phần từ stored procedure.
- OUT parameter có sẵn ở thời điểm nào.
- Kiểu Java của cột `BIGINT`, `DATETIME2`.
- Cách provider áp dụng `@SqlResultSetMapping`.
- Giao dịch rollback khi SQL Server ném lỗi giữa procedure.

Các điểm ấy phải được kiểm tra bằng **integration test** trên môi trường thật hoặc container database phù hợp. Bài này không yêu cầu chạy test; đây là cách thiết kế kiểm thử khi triển khai hệ thống thực tế.

### 24.2. Đừng kiểm tra update counts bằng giả định mong manh

Nếu contract của ứng dụng là “AffectedOrders = 2”, test nên ưu tiên:

1. OUT parameter `AffectedOrders` có giá trị 2.
2. Trạng thái orders sau commit đúng.
3. Hai result sets mang nội dung dự kiến.

Nếu cần test số update counts cụ thể, hãy ghi rõ đó là **hợp đồng của thủ tục và driver đã chọn**, không phải một bảo đảm portable chung của JPA.

## 25. Kết quả rỗng, null và lỗi

Đừng gom mọi trường hợp thành một loại.

### 25.1. Result set rỗng

```java
List<?> rows = procedure.getResultList();

if (rows.isEmpty()) {
    // Tập kết quả hợp lệ nhưng không chứa hàng.
}
```

Đọc xong vẫn có thể `hasMoreResults()` để lấy những phần tiếp.

### 25.2. Update count = 0

```java
int count = procedure.getUpdateCount();

if (count == 0) {
    // Statement không báo ảnh hưởng hàng nào.
}
```

Vẫn có thể còn result sets sau đó.

### 25.3. Không có update count hiện tại

```java
int count = procedure.getUpdateCount();

if (count == -1) {
    // Ở nhánh xử lý non-result-set của vòng lặp,
    // đây là dấu hiệu không còn phần để đọc.
}
```

Không đọc `getUpdateCount()` tùy tiện ngay khi `execute() == true` rồi suy ra đã hết; lúc đó phần hiện tại là result set và API trả `-1` không mô tả phần tiếp theo.

### 25.4. OUT parameter null

Thủ tục có thể gán OUT thành NULL, hoặc không gán giá trị theo logic. Nếu contract cho phép null, kiểm tra:

```java
Object value =
    procedure.getOutputParameterValue("SomeOptionalOut");

if (value == null) {
    // Xử lý theo business contract.
}
```

Không ép `((Number) value).intValue()` trước khi biết value khác null.

### 25.5. Procedure ném lỗi

Một lỗi trong SQL/procedure có thể được báo thành `PersistenceException` hoặc một ngoại lệ liên quan do provider chuyển đổi. Khi procedure có DML, phải xử lý transaction rollback và không coi dữ liệu một số result sets đã đọc là đã commit.

## 26. Bảo mật và kiểm soát tác động

Gọi stored procedure **không tự động an toàn hơn** viết JPQL. Một procedure có thể cập nhật hoặc xóa dữ liệu hàng loạt.

Các nguyên tắc:

1. **Validate đầu vào:** ID batch hợp lệ, trạng thái nằm trong tập cho phép, giới hạn số lượng lô.
2. **Phân quyền thực thi:** không cho mọi caller gọi một procedure có quyền update trên toàn database.
3. **Giới hạn tenant:** nếu có multi-tenancy, procedure phải kiểm tra/được truyền tenant ID từ nguồn tin cậy.
4. **Không nối chuỗi thành SQL động không kiểm soát bên trong procedure:** parameter của JPA chỉ bảo vệ cách Java truyền giá trị; SQL động tự ghép trong procedure vẫn có thể nguy hiểm.
5. **Kiểm soát transaction:** procedure có side effects phải có quy trình rollback hoặc idempotency phù hợp.
6. **Giảm dữ liệu trả về:** không trả toàn bộ thông tin nhạy cảm trong một result set chỉ vì thủ tục có thể SELECT nhiều bảng.
7. **Log có chọn lọc:** ghi ID giao dịch, loại kết quả, thời gian và counts phù hợp; tránh log thông tin cá nhân trong từng row.

### 26.1. Caller không nên tự chọn tên procedure từ input

Không làm:

```java
String procedureName = request.getParameter("procedure");

em.createStoredProcedureQuery(procedureName);
```

nếu không có whitelist rõ và phân quyền. `procedureName` là **cấu trúc thao tác có quyền DB**, không phải một parameter value an toàn chỉ vì `StoredProcedureQuery` có thể bind IN params.

### 26.2. OUT value không thay authorization

Một procedure có thể trả `AffectedOrders = 2` dù caller không được phép tác động hai đơn ấy nếu thủ tục và tầng ứng dụng không kiểm tra quyền. **Truy vấn có kết quả hợp lệ về kỹ thuật không chứng minh kết quả hợp lệ về bảo mật hoặc nghiệp vụ.**

## 27. Tối ưu thiết kế procedure nhiều kết quả

Một procedure trả nhiều result sets có thể giảm số lần round-trip giữa ứng dụng và database, nhưng cũng làm **hợp đồng giao tiếp phức tạp hơn**.

Khi thiết kế, nên cân nhắc:

- Mỗi result set có một **schema cột ổn định** và được đặt tên rõ.
- Tránh các `SELECT` debug vô ý làm thay đổi thứ tự.
- OUT parameters có mục đích nghiệp vụ rõ ràng.
- Không phụ thuộc vào update count từ DML phụ trợ nếu business logic cần con số cụ thể.
- Có chính sách `SET NOCOUNT` thống nhất trên SQL Server.
- Procedure được version/quản lý migration cùng ứng dụng.
- Có integration tests kiểm tra nhiều result sets và counts.
- Tránh trả quá nhiều hàng trong một call.
- Có error code/exception contract rõ nếu một bước thất bại.

### 27.1. Khi nào nên tách procedure?

Nếu một procedure hiện làm tất cả:

```text
Cập nhật đơn
-> Lấy đơn
-> Lấy audit
-> Lấy thống kê
-> Lấy lịch sử khách
-> Lấy sản phẩm liên quan
```

nó có thể trở nên khó kiểm soát:

- Hợp đồng nhiều result sets dễ vỡ khi sửa SQL.
- Provider mapping phức tạp.
- Một phần kết quả có thể rất lớn.
- Khó phân quyền riêng các tập dữ liệu.
- Khó phân trang độc lập từng result set.

Tùy use case, có thể tách thành **một command procedure** trả OUT/summary và các **query chuyên biệt** cho báo cáo. Tuy nhiên, nếu nhiều tập kết quả cần snapshot nhất quán trong đúng một lượt xử lý, giữ chúng trong cùng procedure/transaction có thể là lựa chọn hợp lý.

Không có quy tắc “càng nhiều SELECT trong procedure càng nhanh”. Cần đo workload, round-trips và chi phí kết quả.

## 28. Ví dụ xử lý theo kiểu API service

Một service có thể chuyển kết quả procedure thành DTO rõ ràng thay vì trả `StoredProcedureQuery` ra tầng HTTP.

Ví dụ một kết quả nghiệp vụ:

```java
public record ProcessBatchResponse(
    long batchId,
    int affectedOrders,
    int resultSetCount,
    int updateCountParts
) {}
```

Ứng dụng có thể chuyển:

```java
BatchProcedureReader.BatchRunResult raw =
    reader.run(em, batchId, "APPROVED");

int resultSetParts = 0;
int updateCountParts = 0;

for (BatchProcedureReader.Segment segment
        : raw.segments()) {

    if ("RESULT_SET".equals(segment.kind())) {
        resultSetParts++;
    } else if ("UPDATE_COUNT".equals(segment.kind())) {
        updateCountParts++;
    }
}

ProcessBatchResponse response =
    new ProcessBatchResponse(
        batchId,
        raw.affectedOrders(),
        resultSetParts,
        updateCountParts
    );
```

Đây là DTO thống kê kết quả đọc. Trong ứng dụng thật, response cần trả **dữ liệu nghiệp vụ mà client yêu cầu**, không nhất thiết cần lộ số phần update count phụ trợ của JDBC.

### 28.1. Không trả 200/204 trước khi transaction hoàn tất

Nếu transaction do Spring quản lý, kết quả method còn đi qua transaction interceptor trước khi trả về HTTP layer. Nếu commit thất bại, exception phải được phản ánh đúng.

Với Java SE tự quản lý, chỉ trả response success sau khi `tx.commit()` hoàn tất thành công.

### 28.2. API không cần biết driver phơi bày bao nhiêu counts

Một REST client thường muốn:

```json
{
  "batchId": 77,
  "affectedOrders": 2
}
```

chứ không cần:

```json
{
  "firstJdbcCount": 2,
  "secondJdbcCount": 1,
  "thirdJdbcCount": 0
}
```

Vì thế việc duyệt counts có thể nằm trong tầng persistence/adapter; tầng application trả contract nghiệp vụ ổn định.

## 29. Các tình huống thực hành

### Bài 1 — UPDATE trước SELECT

Stored procedure trả:

```text
UPDATE_COUNT(5)
RESULT_SET(10 rows)
END
```

**Câu hỏi:** `execute()` thường trả gì khi phần đầu được phơi bày đúng là UPDATE_COUNT?

**Giải thích:** `false`. Code phải gọi `getUpdateCount()` trước, xử lý 5, rồi `hasMoreResults()` để chuyển sang result set.

### Bài 2 — false không phải kết thúc

Procedure trả:

```text
RESULT_SET
UPDATE_COUNT(2)
RESULT_SET
END
```

**Câu hỏi:** Vì sao vòng lặp chỉ chạy khi `hasMoreResults() == true` bị lỗi?

**Giải thích:** Khi bước tiếp theo là update count, `hasMoreResults()` trả false nhưng vẫn còn phần kết quả. Phải kiểm tra `getUpdateCount()` rồi tiếp tục.

### Bài 3 — Update count 0

Procedure chạy hai lần với cùng trạng thái mục tiêu. Lần thứ hai UPDATE orders không đổi hàng nào.

**Câu hỏi:** Có nên kết thúc vòng lặp khi count bằng 0?

**Giải thích:** Không. `0` là update count hợp lệ; cần tiếp tục để đọc những result sets sau.

### Bài 4 — getResultList() sai thời điểm

```java
boolean first = procedure.execute(); // false vì update count
List<?> rows = procedure.getResultList();
```

**Giải thích:** Không gọi `getResultList()` nếu current result không phải result set. Đọc `getUpdateCount()` khi Boolean false, trừ trường hợp giá trị -1 báo hết.

### Bài 5 — OUT parameter với nhiều SELECT

Thủ tục có hai SELECT và OUT `AffectedOrders`.

**Câu hỏi:** Thứ tự xử lý portable nên là gì?

**Giải thích:** `execute()`, duyệt result sets/counts, rồi `getOutputParameterValue(...)`.

### Bài 6 — Hai counts không cùng nghĩa

Có UPDATE orders (2 hàng) và UPDATE batch_jobs (1 hàng).

**Câu hỏi:** Tổng 3 có phải ba đơn được cập nhật?

**Giải thích:** Không. Có hai đơn và một batch record. Nên dùng OUT có ý nghĩa rõ như `AffectedOrders = 2`.

### Bài 7 — Result set đầu tiên rỗng

Procedure trả:

```text
RESULT_SET(0 rows)
RESULT_SET(4 rows)
END
```

**Câu hỏi:** Khi `getResultList().isEmpty()`, đã hết chưa?

**Giải thích:** Chưa chắc. Một result set rỗng vẫn là phần kết quả hợp lệ. Phải `hasMoreResults()` để đọc phần tiếp theo.

### Bài 8 — Mapping sai kiểu

Procedure trả một tập orders và một tập audit khác cột, nhưng query khai báo mọi result set là `OrderEntity.class`.

**Giải thích:** Mapping có thể thất bại hoặc dữ liệu sai. Chọn nhiều `@SqlResultSetMapping` tương ứng hoặc map từng set sang DTO rõ ràng.

### Bài 9 — NOCOUNT ON

Thủ tục dùng `SET NOCOUNT ON` và không có update counts nhìn thấy từ driver.

**Câu hỏi:** Có thể kết luận procedure không cập nhật hàng nào không?

**Giải thích:** Không. NOCOUNT ảnh hưởng thông điệp row count; phải dựa vào OUT contract/dữ liệu và transaction.

### Bài 10 — Không muốn đọc audit

Một API chỉ muốn biết số đơn đã đổi trạng thái, nhưng procedure trả 100.000 hàng audit.

**Giải thích:** Nên thay đổi hợp đồng procedure hoặc tách API/query theo nhu cầu. Đừng dùng một stored procedure trả dữ liệu khổng lồ chỉ để lấy một OUT parameter nếu kiến trúc có thể tránh.

### Bài 11 — Procedure gọi lại

```java
procedure.execute();
procedure.execute();
```

**Câu hỏi:** Có phải hai lần gọi lấy hai result sets?

**Giải thích:** Không. Đây có thể là hai lần thực thi thủ tục, dẫn đến tác dụng cập nhật lặp lại. Dùng `hasMoreResults()`.

### Bài 12 — Update trực tiếp khiến entity stale

Entity Order#501 đã được `em.find` tải trước procedure. Procedure đổi status rồi trả result set.

**Giải thích:** Managed Order#501 có thể giữ status cũ trong persistence context. Nếu cần state mới, dùng refresh/clear/reload có chủ đích, tránh làm mất thay đổi chưa flush.

### Bài 13 — Rollback sau khi đọc OUT

Procedure báo `AffectedOrders = 2` nhưng transaction sau đó lỗi và rollback.

**Câu hỏi:** Có được báo cho client rằng hai đơn đã thay đổi thành công không?

**Giải thích:** Không. OUT mô tả tác động trong quá trình thực thi; transaction rollback nghĩa thay đổi chưa được commit.

### Bài 14 — OUT có giá trị null

Procedure cho phép `AffectedOrders` null nếu batch ID không có.

**Giải thích:** Kiểm tra null trước khi cast `Number.intValue()`; phân loại “batch không tồn tại” theo business contract.

### Bài 15 — Kiểm thử portability

Cùng một procedure được nâng phiên bản JDBC driver. Ứng dụng trước đây thấy 2 update counts, bây giờ thấy 3.

**Giải thích:** Hãy kiểm tra SQL/NOCOUNT/driver/provider. Nếu hợp đồng chỉ cần `AffectedOrders` và hai result sets, không nên để tầng nghiệp vụ phụ thuộc vào số count phụ trợ.

## 30. Câu hỏi tự kiểm tra

**1. StoredProcedureQuery có thể trả hơn một result set không?**

Có, tùy procedure, DBMS, driver và JPA provider.

**2. StoredProcedureQuery có thể trả update counts xen giữa các result sets không?**

Có thể; đây là lý do cần duyệt cả hai loại.

**3. `execute() == true` nghĩa là gì?**

Kết quả đầu tiên là một result set, không phải tuyên bố transaction đã commit.

**4. `execute() == false` có nghĩa procedure thất bại không?**

Không. Kết quả đầu tiên có thể là update count hoặc không có kết quả loại đó.

**5. `hasMoreResults()` có chỉ kiểm tra mà không thay đổi vị trí không?**

Không. Nó tiến sang phần kết quả tiếp theo.

**6. `hasMoreResults() == false` có nghĩa chắc chắn đã hết không?**

Không. Phần kế tiếp có thể là update count.

**7. Khi nào nên gọi `getResultList()`?**

Khi current result là result set.

**8. `getUpdateCount() == 0` có nghĩa gì?**

Một update count hợp lệ với giá trị 0; không phải tín hiệu kết thúc.

**9. `getUpdateCount() == -1` dùng thế nào trong vòng lặp?**

Khi đang ở nhánh không phải result set, nó biểu thị không có update count hiện tại và được dùng làm điểm dừng.

**10. Vì sao không gọi `execute()` nhiều lần để lấy result set tiếp?**

Vì đó là thao tác thực thi procedure, có thể chạy lại DML.

**11. Khi nào nên đọc OUT parameter nếu có nhiều JDBC results?**

Sau khi đã xử lý các result sets và update counts.

**12. `getResultList().size()` có phải số dòng UPDATE không?**

Không. Nó là số hàng SELECT trả về trong result set hiện tại.

**13. Có nên cộng mọi update count để trả affectedOrders không?**

Không, nếu procedure cập nhật nhiều bảng hoặc nhiều loại dữ liệu khác nhau.

**14. `SET NOCOUNT ON` trên SQL Server có ngăn UPDATE không?**

Không. Nó ảnh hưởng thông điệp số dòng, không dừng DML.

**15. Hỗ trợ multiple result sets có giống nhau ở mọi DBMS không?**

Không. SQL dialect, driver và provider quyết định nhiều chi tiết thực tế.

**16. Có thể dùng một entity result class cho hai result sets khác cột không?**

Không nên. Cần mapping phù hợp từng tập hoặc xử lý raw/DTO.

**17. `@SqlResultSetMapping` dùng để làm gì?**

Mô tả cách ánh xạ kết quả SQL sang entity, scalar hoặc DTO.

**18. `@NamedStoredProcedureQuery` có tự tiêu thụ mọi result set không?**

Không. Nó khai báo metadata thủ tục; cách duyệt vẫn phải đúng.

**19. Bulk update từ procedure có tự cập nhật managed entity đã tải trong persistence context không?**

Không được giả định; context có thể stale.

**20. Chỉ cần OUT parameter có số 2 đã đủ xác nhận xóa/cập nhật bền vững không?**

Không. Transaction vẫn phải commit thành công.

**21. Khi nào nên xem xét JDBC CallableStatement?**

Khi cần xử lý nhiều result sets/driver-specific features phức tạp mà tầng JPA không đáp ứng ổn định.

**22. Vì sao phải có integration test với database thật?**

Vì số counts, thứ tự phần kết quả, kiểu cột và hành vi OUT/cursor phụ thuộc DBMS/driver/provider.

**23. Có nên trả StoredProcedureQuery còn mở ra khỏi service đã đóng EntityManager không?**

Không. Query và các kết quả phụ thuộc vòng đời persistence context/connection.

**24. Một result set rỗng có chứng minh thủ tục hết kết quả không?**

Không. Có thể còn update count hoặc result set khác.

## 31. Ghi nhớ cốt lõi

Khi gọi stored procedure từ JPA, **một lần `execute()` có thể tạo ra cả một chuỗi các result sets và update counts**. Vì thế, ứng dụng cần xử lý **theo trạng thái hiện tại**, không theo giả định rằng mọi procedure chỉ trả một `List<?>` hoặc một affected row count.

Quy trình nền tảng:

```java
boolean isResultSet = procedure.execute();

while (true) {
    if (isResultSet) {
        List<?> rows = procedure.getResultList();
        // Xử lý rows.
    } else {
        int count = procedure.getUpdateCount();

        if (count == -1) {
            break;
        }

        // Xử lý update count, kể cả count = 0.
    }

    isResultSet = procedure.hasMoreResults();
}

// Sau khi xử lý result sets/counts:
Object out = procedure.getOutputParameterValue("AffectedOrders");
```

Hãy ghi nhớ bốn phân biệt quyết định:

1. **`execute()` và `hasMoreResults()` báo loại kết quả**, không trực tiếp báo thành công/thất bại nghiệp vụ.
2. **`false` không đồng nghĩa hết kết quả**; cần `getUpdateCount()`, và `0` khác `-1`.
3. **Số hàng SELECT, update count và OUT parameter là ba khái niệm khác nhau**; chọn đúng số liệu để trả cho nghiệp vụ.
4. **Procedure cập nhật database không tự làm mới persistence context và không tự cam kết transaction**; phải xử lý flush, reload, exception và commit phù hợp.

Cuối cùng, **khả năng trả nhiều result sets không hoàn toàn portable giữa các DBMS, JDBC drivers và JPA providers**. Muốn dùng trong production, cần định nghĩa rõ schema/thứ tự từng tập kết quả, chính sách row counts, OUT parameters, mapping và transaction; sau đó kiểm chứng bằng integration tests trên database thực tế. Làm đúng những điều đó sẽ giúp ứng dụng đọc đầy đủ kết quả thủ tục, tránh bỏ sót dữ liệu hoặc báo sai số dòng cập nhật.
