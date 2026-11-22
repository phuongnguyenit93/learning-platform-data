# Upsert, kiểm tra trùng và tranh chấp trên khóa duy nhất

Ứng dụng thường cần tạo một bản ghi nếu chưa tồn tại, hoặc cập nhật bản ghi hiện có nếu khóa nghiệp vụ đã được dùng. Mẫu thao tác này được gọi là upsert (update hoặc insert). Ví dụ: đồng bộ sản phẩm từ hệ thống ngoài, ghi trạng thái mới nhất của thiết bị, lưu hồ sơ theo mã khách hàng hoặc tiếp nhận lại một sự kiện có thể được gửi nhiều lần.

Một cách triển khai dễ nghĩ đến là kiểm tra trước bằng SELECT, sau đó INSERT nếu chưa có hoặc UPDATE nếu đã có. Cách làm này có thể sai khi nhiều transaction chạy đồng thời: hai phiên cùng kiểm tra và đều không thấy hàng, rồi cùng INSERT. Nếu không có ràng buộc duy nhất, dữ liệu trùng có thể xuất hiện; nếu có unique constraint, một phiên sẽ gặp lỗi duplicate hoặc phải chờ phiên còn lại. Kiểm tra trước không thay thế được bảo vệ duy nhất ở database.

Trong phạm vi DATABASE_PERFORMANCE, bài học này tập trung vào cách thiết kế upsert an toàn, vai trò của unique constraint/index, hành vi khi tranh chấp cùng khóa, khác biệt cú pháp giữa PostgreSQL, MySQL, SQL Server và Oracle, cùng cách đo chi phí của đường ghi. Mục tiêu là bảo đảm tính đúng đắn khi có concurrency, đồng thời tránh cập nhật và ghi log không cần thiết.

## 1. Upsert là gì và khi nào cần dùng?

Upsert kết hợp hai hành động:

- Nếu chưa có hàng mang khóa nghiệp vụ cần thiết, tạo hàng mới.
- Nếu hàng đã tồn tại, cập nhật các thuộc tính được phép thay đổi.

Ví dụ, hệ thống nhận dữ liệu trạng thái thiết bị theo cặp tenant_id và device_id. Mỗi thiết bị chỉ có một bản ghi trạng thái hiện tại trong một tenant:

```sql
CREATE TABLE device_state (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    state VARCHAR(30) NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, device_id)
);
```

Khóa chính ghép bảo đảm mỗi thiết bị chỉ có một hàng trạng thái trong phạm vi tenant. Upsert có thể tạo hàng đầu tiên hoặc cập nhật trạng thái khi sự kiện mới đến.

Các tình huống thường gặp:

- Đồng bộ dữ liệu từ nguồn ngoài theo external_id.
- Ghi cấu hình theo cặp người dùng và loại cấu hình.
- Cập nhật giá trị tổng hợp hiện tại theo khóa nhóm.
- Tiếp nhận webhook hoặc message có idempotency key.
- Duy trì cache bền vững hoặc bảng trạng thái mới nhất.

Upsert phù hợp khi quy tắc nghiệp vụ thật sự là “một hàng hiện tại cho mỗi khóa”. Nếu mỗi lần nhận dữ liệu phải tạo lịch sử, ledger hoặc event mới, hãy INSERT bản ghi sự kiện riêng thay vì ghi đè dữ liệu cũ.

## 2. Unique constraint là hàng rào bảo vệ cuối cùng

Unique constraint bảo đảm không tồn tại hai hàng có cùng giá trị khóa theo quy tắc so sánh của DBMS. Hệ quản trị thường thực thi constraint bằng unique index hoặc cấu trúc chỉ mục tương đương.

Ví dụ:

```sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_tenant_external
UNIQUE (tenant_id, external_id);
```

Constraint này bảo đảm external_id duy nhất trong từng tenant. Nếu nghiệp vụ yêu cầu external_id duy nhất trên toàn hệ thống, khóa phải được thiết kế khác:

```sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_external
UNIQUE (external_id);
```

Phạm vi uniqueness phải phản ánh đúng quy tắc nghiệp vụ. Đưa tenant_id vào khóa giúp các tenant có thể dùng cùng external_id; bỏ tenant_id sẽ tạo một namespace chung.

### Constraint và index có vai trò khác nhau

- **Unique constraint** diễn đạt quy tắc dữ liệu phải duy nhất.
- **Unique index** là cấu trúc giúp database kiểm tra và truy cập khóa duy nhất hiệu quả.
- **Non-unique index** hỗ trợ truy vấn nhưng không ngăn dữ liệu trùng.

Không nên chỉ tạo index thông thường rồi giả định dữ liệu đã được bảo vệ. Hãy dùng PRIMARY KEY, UNIQUE constraint hoặc unique index đúng với mô hình DBMS.

### Chuẩn hóa khóa nghiệp vụ

Giá trị nhìn giống nhau với người dùng chưa chắc được DB coi là trùng. Cần xác định:

- Phân biệt chữ hoa/thường hay không.
- Có bỏ khoảng trắng đầu/cuối không.
- Có chuẩn hóa Unicode hoặc dấu hay không.
- Có phân biệt dấu gạch, ký tự phân cách và định dạng không.
- Khóa có phân biệt tenant, quốc gia, loại đối tượng hoặc nguồn dữ liệu không.

Ví dụ, nếu mã ngoài không phân biệt hoa/thường, hai giá trị AbC-12 và abc-12 phải được chuẩn hóa hoặc so sánh theo collation phù hợp. Có thể lưu thêm cột normalized_key và đặt unique constraint trên cột đó. Việc chuẩn hóa phải thống nhất giữa insert, update, tìm kiếm và xử lý dữ liệu cũ.

### NULL trong unique key

Quy tắc NULL của unique constraint khác nhau giữa các hệ quản trị và có thể phụ thuộc phiên bản. PostgreSQL mặc định coi các giá trị NULL là khác nhau trong unique constraint, với tùy chọn NULLS NOT DISTINCT ở các phiên bản hỗ trợ. MySQL thường cho phép nhiều NULL trong unique index. SQL Server và Oracle có quy tắc riêng đối với NULL và khóa ghép.

Nếu khóa nghiệp vụ bắt buộc phải có giá trị, nên khai báo NOT NULL cho từng cột khóa. Không dựa vào hành vi NULL mặc định để biểu diễn uniqueness nếu chưa xác nhận semantics của DBMS.

## 3. Vì sao SELECT kiểm tra trước rồi INSERT có race condition?

Mẫu thường gặp:

```sql
SELECT customer_id
FROM customers
WHERE tenant_id = :tenant_id
  AND external_id = :external_id;

-- Nếu không thấy hàng thì INSERT
INSERT INTO customers (tenant_id, external_id, name)
VALUES (:tenant_id, :external_id, :name);
```

Giả sử hai session A và B cùng xử lý khóa (7, 'C-100'):

1. A SELECT và không thấy hàng.
2. B SELECT và cũng không thấy hàng.
3. A INSERT hàng mới.
4. B INSERT cùng khóa.
5. Nếu có unique constraint, B có thể chờ A commit rồi nhận duplicate-key error; nếu A rollback, B có thể tiếp tục thành công.
6. Nếu không có unique constraint, cả hai hàng có thể được lưu và dữ liệu bị trùng.

Đây là race condition giữa thao tác kiểm tra và thao tác ghi. Hai câu lệnh riêng không tạo thành một hành động nguyên tử chỉ vì chúng nằm gần nhau trong code ứng dụng.

### Vì sao SELECT FOR UPDATE không giải quyết mọi trường hợp?

SELECT FOR UPDATE khóa hàng đã tồn tại trong nhiều DBMS. Nếu hàng chưa tồn tại, không có hàng cụ thể để khóa. Một số hệ quản trị và isolation level có thể khóa phạm vi khóa hoặc khoảng index, nhưng hành vi phụ thuộc engine, index và predicate.

Không nên giả định SELECT FOR UPDATE trên một khóa chưa tồn tại sẽ ngăn transaction khác insert cùng khóa. Unique constraint vẫn cần thiết; nếu dùng locking read hoặc serializable, cần hiểu rõ phạm vi khóa và khả năng retry.

### Kiểm tra trước chỉ hữu ích cho trải nghiệm ứng dụng

Ứng dụng có thể SELECT trước để hiển thị thông báo “mã đã tồn tại” hoặc kiểm tra quy tắc nghiệp vụ bổ sung. Nhưng kết quả kiểm tra có thể lỗi thời ngay sau khi trả về. Khi ghi, database vẫn phải thực thi unique constraint và xử lý xung đột.

Với dữ liệu quan trọng, hãy coi database là nơi quyết định cuối cùng về uniqueness. Ứng dụng chuyển lỗi duplicate thành phản hồi nghiệp vụ phù hợp thay vì dựa vào một lần SELECT trước.

## 4. PostgreSQL: INSERT ... ON CONFLICT

PostgreSQL cung cấp cú pháp upsert trực tiếp bằng ON CONFLICT. Database dùng unique constraint hoặc unique index làm arbiter để phát hiện xung đột và thực hiện nhánh DO NOTHING hoặc DO UPDATE.

### DO UPDATE

Ví dụ:

```sql
INSERT INTO device_state (
    tenant_id,
    device_id,
    state,
    observed_at
)
VALUES (
    :tenant_id,
    :device_id,
    :state,
    :observed_at
)
ON CONFLICT (tenant_id, device_id)
DO UPDATE SET
    state = EXCLUDED.state,
    observed_at = EXCLUDED.observed_at;
```

EXCLUDED đại diện cho hàng đề xuất insert nhưng gặp xung đột. Khi có hàng cùng khóa, PostgreSQL cập nhật hàng hiện có bằng các giá trị từ EXCLUDED.

Có thể chỉ định constraint theo tên:

```sql
INSERT INTO customers (tenant_id, external_id, name)
VALUES (:tenant_id, :external_id, :name)
ON CONFLICT ON CONSTRAINT uq_customers_tenant_external
DO UPDATE SET name = EXCLUDED.name;
```

Target của ON CONFLICT phải khớp unique constraint/index phù hợp. Với partial unique index, có thể cần chỉ rõ predicate tương ứng. Một số loại constraint hoặc index có giới hạn riêng; ví dụ DO UPDATE không dùng được với deferrable constraint làm arbiter.

### DO NOTHING

Nếu hàng đã tồn tại và không cần cập nhật:

```sql
INSERT INTO processed_messages (message_id, processed_at)
VALUES (:message_id, CURRENT_TIMESTAMP)
ON CONFLICT (message_id) DO NOTHING
RETURNING message_id;
```

Nếu insert thành công, RETURNING trả khóa vừa tạo. Nếu gặp conflict và DO NOTHING, không có hàng nào được trả về. Ứng dụng có thể hiểu đó là thông điệp đã được ghi nhận trước đó, sau khi xác định đúng constraint gây conflict.

Trong PostgreSQL Read Committed, một INSERT ... ON CONFLICT DO NOTHING có thể bỏ qua insert vì một hàng xung đột vừa được transaction khác tạo nhưng hàng đó chưa hiển thị trong snapshot của chính câu lệnh. Nếu cần đọc hàng hiện có, thực hiện SELECT ở câu lệnh tiếp theo để nhận snapshot mới. Với Repeatable Read hoặc Serializable, có thể cần retry toàn bộ transaction khi gặp serialization failure.

### Tránh UPDATE không cần thiết

Một upsert có thể gặp hàng hiện có nhưng dữ liệu mới giống hệt dữ liệu cũ. Nếu vẫn UPDATE, DB có thể tạo row version mới, ghi WAL, cập nhật index phụ thuộc cột, kích hoạt trigger và làm tăng replication traffic.

PostgreSQL cho phép điều kiện WHERE trong DO UPDATE:

```sql
INSERT INTO device_state (
    tenant_id, device_id, state, observed_at
)
VALUES (
    :tenant_id, :device_id, :state, :observed_at
)
ON CONFLICT (tenant_id, device_id)
DO UPDATE SET
    state = EXCLUDED.state,
    observed_at = EXCLUDED.observed_at
WHERE
    (device_state.state, device_state.observed_at)
    IS DISTINCT FROM
    (EXCLUDED.state, EXCLUDED.observed_at)
RETURNING tenant_id, device_id, state, observed_at;
```

Nếu các giá trị không đổi, nhánh UPDATE không thực hiện cập nhật hàng và RETURNING không trả hàng đó. Tuy nhiên, việc kiểm tra conflict và khóa cần thiết vẫn có chi phí; điều kiện WHERE không làm mất hoàn toàn contention trên cùng khóa.

## 5. MySQL: INSERT ... ON DUPLICATE KEY UPDATE

MySQL hỗ trợ upsert qua ON DUPLICATE KEY UPDATE. Khi INSERT vi phạm một PRIMARY KEY hoặc UNIQUE index, MySQL thực hiện nhánh UPDATE.

Ví dụ với cú pháp row alias trên MySQL 8.0.19 trở lên:

```sql
INSERT INTO device_state (
    tenant_id,
    device_id,
    state,
    observed_at
)
VALUES (
    ?, ?, ?, ?
) AS incoming
ON DUPLICATE KEY UPDATE
    state = incoming.state,
    observed_at = incoming.observed_at;
```

Alias incoming đại diện cho hàng mới được đề xuất. Cú pháp VALUES(column) cũ vẫn xuất hiện trong nhiều ví dụ, nhưng đã bị đánh dấu deprecated từ MySQL 8.0.20; với phiên bản mới nên dùng row alias theo cú pháp được hỗ trợ.

### Conflict có thể đến từ bất kỳ unique key nào

Khác với PostgreSQL, cú pháp MySQL này không chỉ định rõ một conflict target duy nhất theo danh sách cột. Bất kỳ PRIMARY KEY hoặc UNIQUE index nào bị vi phạm đều có thể kích hoạt nhánh UPDATE.

Điều này cần chú ý khi bảng có nhiều unique key. Ví dụ, hàng mới có external_id trùng một bản ghi nhưng email lại trùng một bản ghi khác. Nhánh UPDATE có thể tác động đến hàng xung đột theo unique key được phát hiện, tạo kết quả không đúng ý định nếu mô hình khóa không rõ ràng.

Trước khi dùng, hãy kiểm tra tất cả unique index của bảng và bảo đảm mọi conflict có thể xảy ra đều có semantics cập nhật an toàn.

### Số hàng bị ảnh hưởng

MySQL thường báo affected rows khác nhau cho insert mới, update và nhánh update không thay đổi giá trị; client flag CLIENT_FOUND_ROWS có thể ảnh hưởng cách báo cáo. Không nên dùng affected rows như một tín hiệu portable để phân biệt chính xác mọi trạng thái nghiệp vụ. Nếu cần biết insert hay update, hãy dùng một cơ chế trả kết quả hoặc cột trạng thái được thiết kế rõ ràng.

Nhánh ON DUPLICATE KEY UPDATE vẫn có thể tạo khóa và ghi log ngay cả khi giá trị đích không đổi. Hãy dùng biểu thức có điều kiện khi cần tránh cập nhật không cần thiết, nhưng kiểm tra cú pháp và hành vi của phiên bản MySQL cụ thể.

## 6. SQL Server: UPDATE/INSERT an toàn và MERGE

SQL Server không có cú pháp ON CONFLICT giống PostgreSQL. Có thể triển khai upsert bằng UPDATE trước, sau đó INSERT nếu không tìm thấy hàng, trong một transaction có khóa phù hợp.

Ví dụ:

```sql
SET XACT_ABORT ON;
BEGIN TRANSACTION;

UPDATE dbo.DeviceState WITH (UPDLOCK, HOLDLOCK)
SET
    State = @state,
    ObservedAt = @observed_at
WHERE TenantId = @tenant_id
  AND DeviceId = @device_id;

IF @@ROWCOUNT = 0
BEGIN
    INSERT INTO dbo.DeviceState (
        TenantId, DeviceId, State, ObservedAt
    )
    VALUES (
        @tenant_id, @device_id, @state, @observed_at
    );
END;

COMMIT TRANSACTION;
```

UPDLOCK yêu cầu khóa cập nhật trong lúc kiểm tra/cập nhật; HOLDLOCK áp dụng semantics Serializable cho tham chiếu bảng trong câu lệnh. Khi có unique index trên (TenantId, DeviceId), khóa phạm vi phù hợp có thể ngăn hai transaction cùng kết luận khóa chưa tồn tại rồi insert đồng thời.

Đây là mẫu minh họa cần được kiểm tra theo isolation level, index và phiên bản SQL Server. Không bỏ unique constraint ngay cả khi đã dùng lock hint: constraint là hàng rào cuối cùng bảo vệ dữ liệu trước mọi đường ghi khác.

Nếu có trigger, logic audit hoặc nhiều câu lệnh có thể thay đổi @@ROWCOUNT, hãy lưu ngay số hàng bị ảnh hưởng sau UPDATE trước khi chạy câu lệnh khác. Cần xử lý lỗi bằng TRY/CATCH và bảo đảm rollback khi transaction thất bại. SET XACT_ABORT ON giúp nhiều lỗi runtime làm transaction bị hủy theo quy tắc SQL Server; ứng dụng vẫn phải kiểm tra trạng thái transaction và lỗi trả về.

### MERGE

SQL Server có MERGE để kết hợp INSERT, UPDATE và DELETE dựa trên điều kiện khớp:

```sql
MERGE dbo.DeviceState WITH (HOLDLOCK) AS target
USING (
    SELECT
        @tenant_id AS TenantId,
        @device_id AS DeviceId,
        @state AS State,
        @observed_at AS ObservedAt
) AS source
ON target.TenantId = source.TenantId
AND target.DeviceId = source.DeviceId
WHEN MATCHED THEN
    UPDATE SET
        State = source.State,
        ObservedAt = source.ObservedAt
WHEN NOT MATCHED THEN
    INSERT (TenantId, DeviceId, State, ObservedAt)
    VALUES (source.TenantId, source.DeviceId, source.State, source.ObservedAt);
```

HOLDLOCK thể hiện yêu cầu khóa theo phạm vi Serializable trong ngữ cảnh bảng đích, giúp xử lý một số race condition khi hàng chưa tồn tại. Dù vậy, MERGE có lịch sử các khác biệt hành vi và vấn đề theo phiên bản, trigger, concurrency và cấu trúc câu lệnh. Hãy xem tài liệu và known issues của phiên bản đang dùng, kiểm thử concurrency thực tế, và cân nhắc mẫu UPDATE/INSERT tường minh nếu dễ kiểm soát hơn.

MERGE không tự làm cho mọi thao tác trở nên an toàn nếu điều kiện ON không khớp đúng khóa duy nhất hoặc nguồn chứa nhiều hàng trùng khóa đích. Unique constraint vẫn cần thiết.

## 7. Oracle: MERGE

Oracle cung cấp MERGE để cập nhật hàng khớp và insert hàng chưa khớp. Ví dụ:

```sql
MERGE INTO device_state target
USING (
    SELECT
        :tenant_id AS tenant_id,
        :device_id AS device_id,
        :state AS state,
        :observed_at AS observed_at
    FROM dual
) source
ON (
    target.tenant_id = source.tenant_id
    AND target.device_id = source.device_id
)
WHEN MATCHED THEN
    UPDATE SET
        target.state = source.state,
        target.observed_at = source.observed_at
WHEN NOT MATCHED THEN
    INSERT (
        tenant_id, device_id, state, observed_at
    )
    VALUES (
        source.tenant_id, source.device_id,
        source.state, source.observed_at
    );
```

Điều kiện ON phải xác định đúng hàng đích. Oracle không cho phép cập nhật cột được tham chiếu trong điều kiện ON của MERGE theo các quy tắc tương ứng; khóa định danh thường nên ổn định.

Khi hai session cùng MERGE một khóa chưa tồn tại, cả hai có thể cùng đánh giá nhánh NOT MATCHED trước khi một bên insert. Unique constraint bảo vệ dữ liệu; một session có thể gặp ORA-00001. Ứng dụng cần phân biệt trường hợp cạnh tranh hợp lệ với lỗi unique khác, sau đó đọc lại hoặc retry theo chính sách. Không giả định MERGE luôn xử lý mọi race như một UPSERT nguyên tử tương đương với PostgreSQL ON CONFLICT.

Với nguồn nhiều hàng, bảo đảm mỗi khóa đích chỉ xuất hiện một lần trong source. Nếu nhiều hàng nguồn cùng khớp một hàng đích, MERGE có thể báo lỗi do cố cập nhật cùng hàng nhiều lần hoặc tạo kết quả không xác định theo quy tắc của phiên bản.

## 8. So sánh các cơ chế upsert

| Hệ quản trị | Cú pháp thường dùng | Lưu ý concurrency |
|---|---|---|
| PostgreSQL | INSERT ... ON CONFLICT DO NOTHING/DO UPDATE | Chỉ định conflict target; xử lý conflict bằng unique arbiter; DO UPDATE có thể kèm WHERE |
| MySQL | INSERT ... ON DUPLICATE KEY UPDATE | Bất kỳ PRIMARY/UNIQUE key phù hợp nào có thể kích hoạt update; chú ý bảng có nhiều unique key |
| SQL Server | UPDATE rồi INSERT trong transaction với UPDLOCK/HOLDLOCK; hoặc MERGE | Cần unique index và khóa phạm vi phù hợp; kiểm tra semantics theo phiên bản |
| Oracle | MERGE | Unique constraint vẫn là bảo vệ cuối; cạnh tranh insert có thể phát sinh ORA-00001 và cần xử lý |

Không nên chuyển nguyên câu lệnh giữa các DBMS. Cùng một từ “upsert” có thể khác về conflict target, affected rows, trigger, trả về hàng, xử lý NULL và hành vi khi nhiều unique key bị vi phạm.

## 9. Tranh chấp trên khóa duy nhất

Khi nhiều transaction ghi cùng một unique key, database phải tuần tự hóa việc quyết định hàng nào được tạo hoặc cập nhật. Unique index không chỉ là công cụ tìm kiếm; nó còn là điểm đồng bộ để ngăn hai phiên tạo hai hàng cùng khóa.

Ví dụ, nhiều worker cùng cập nhật trạng thái của một device_id. Nếu tất cả ghi vào cùng một khóa, các thao tác có thể phải chờ nhau dù bảng có hàng triệu khóa khác nhau. Đây là hot key contention.

### Điều gì xảy ra khi insert trùng khóa chưa commit?

Một session có thể đang tạo khóa nhưng chưa commit. Session khác cố insert cùng khóa phải chờ kết quả transaction đầu:

- Nếu transaction đầu commit, session sau phát hiện conflict và đi theo nhánh upsert hoặc nhận lỗi duplicate.
- Nếu transaction đầu rollback, session sau có thể tiếp tục insert vì khóa xung đột không còn tồn tại.
- Nếu transaction đầu kéo dài, các session cùng khóa có thể xếp hàng.

Thời gian chờ phụ thuộc transaction đầu, cơ chế unique index và isolation level. Vì vậy, transaction ghi khóa duy nhất nên ngắn và tránh gọi dịch vụ ngoài trong lúc giữ trạng thái ghi.

### Cùng khóa và khác khóa là hai tình huống khác nhau

- **Cùng logical key:** nhiều transaction cùng ghi một khóa nghiệp vụ; có thể chờ nhau do unique conflict hoặc row lock.
- **Khác logical key nhưng cùng vùng index:** nhiều insert có thể cạnh tranh trên page latch, buffer hoặc cấu trúc nội bộ của index tùy engine.
- **Khóa tăng tuần tự:** nhiều insert vào vùng cuối B-tree có thể tạo hotspot ở trang cuối trong một số workload.

Nếu wait là row/key lock trên cùng giá trị, cần xử lý hot key hoặc giảm số lần ghi cùng khóa. Nếu wait là latch/page contention trên index, cần xem cấu trúc index, tốc độ insert, partitioning và đặc tính engine. Hai vấn đề không có cùng cách giải quyết.

## 10. Hot key, idempotency và giảm số lần ghi

Một khóa nóng có thể xuất hiện khi nhiều request cùng cập nhật:

- Một tài khoản tổng hợp hoặc số dư dùng chung.
- Một hàng trạng thái thiết bị được cập nhật liên tục.
- Một bộ đếm toàn cục.
- Một khóa idempotency nhận lại nhiều lần.
- Một bản ghi cấu hình dùng chung cho nhiều worker.

Trước khi thay đổi schema, hãy xác định có thực sự cần ghi mọi sự kiện vào cùng một hàng hay không.

### Coalesce các cập nhật

Nếu nghiệp vụ chỉ cần trạng thái mới nhất, có thể gộp nhiều thay đổi trước khi ghi. Ví dụ, worker giữ giá trị mới nhất theo device_id trong một khoảng ngắn rồi thực hiện một upsert thay vì ghi mọi thông điệp đến.

Chỉ coalesce khi có thể bỏ qua trạng thái trung gian. Nếu cần audit hoặc lịch sử từng sự kiện, phải ghi event riêng và xây dựng projection trạng thái hiện tại.

### Idempotency key

Đối với thao tác có thể được gửi lại do timeout hoặc retry, tạo một khóa idempotency duy nhất theo phạm vi nghiệp vụ:

```sql
CREATE TABLE processed_requests (
    tenant_id BIGINT NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    response_code INTEGER,
    response_body TEXT,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key)
);
```

Trong transaction xử lý request:

1. Thử ghi idempotency key.
2. Nếu insert thành công, thực hiện thay đổi nghiệp vụ và lưu kết quả.
3. Commit thay đổi nghiệp vụ cùng bản ghi idempotency.
4. Nếu key đã tồn tại, đọc kết quả đã lưu và trả lại.
5. Nếu cùng key nhưng request_hash khác, từ chối vì một key đang bị tái sử dụng cho payload khác.

Nếu thao tác nghiệp vụ và idempotency record nằm trong hai transaction riêng, lỗi giữa hai bước có thể làm request được thực hiện hai lần hoặc kết quả không thể truy hồi. Cần giữ chúng trong cùng transaction DB khi có thể.

Với tác vụ nhiều dịch vụ, transaction DB không thể bao trùm nguyên tử tất cả hệ thống ngoài. Hãy dùng outbox, saga hoặc workflow có trạng thái và idempotency ở từng bước.

### Sharding hoặc partition theo khóa

Nếu một khóa nóng là điểm nghẽn thật sự, có thể chia dữ liệu theo tenant, loại tài nguyên hoặc shard key để giảm tập trung. Nhưng không thể chia một khóa duy nhất thành nhiều bản ghi độc lập nếu nghiệp vụ yêu cầu một giá trị duy nhất toàn cục. Khi phải tổng hợp từ nhiều shard, cần xác định consistency, thứ tự cập nhật và cách xử lý xung đột.

## 11. Tránh cập nhật không cần thiết trong nhánh conflict

Upsert có thể làm phát sinh UPDATE ngay cả khi payload không đổi. Điều này gây:

- Ghi transaction log/WAL hoặc undo.
- Tạo row version mới hoặc thay đổi timestamp cập nhật.
- Cập nhật secondary index nếu cột được index thay đổi.
- Kích hoạt trigger, CDC, audit hoặc replication.
- Tăng lock duration và contention trên hàng nóng.
- Tăng vacuum/purge hoặc version-store workload.

Hãy so sánh giá trị cũ và mới trước khi UPDATE nếu nghiệp vụ cho phép. PostgreSQL có IS DISTINCT FROM; SQL Server có thể dùng so sánh NULL-safe theo kiểu dữ liệu; MySQL và Oracle có toán tử/cú pháp tương ứng. Với nhiều cột, cần so sánh đúng semantics NULL, collation và kiểu dữ liệu.

Không nên bỏ qua UPDATE chỉ dựa trên hash nếu chưa xác định xác suất collision và cách tạo hash. Với dữ liệu quan trọng, so sánh các cột hoặc dùng digest đủ tin cậy kết hợp kiểm tra khi cần.

Nếu cập nhật chỉ một số cột, đừng ghi đè mọi cột bằng payload có thể cũ. Chẳng hạn, một sự kiện trạng thái đến muộn không nên ghi đè trạng thái mới hơn. Có thể thêm điều kiện thời gian hoặc version:

```sql
-- Minh họa PostgreSQL
INSERT INTO device_state (
    tenant_id, device_id, state, observed_at
)
VALUES (
    :tenant_id, :device_id, :state, :observed_at
)
ON CONFLICT (tenant_id, device_id)
DO UPDATE SET
    state = EXCLUDED.state,
    observed_at = EXCLUDED.observed_at
WHERE EXCLUDED.observed_at > device_state.observed_at;
```

Điều kiện này chỉ chấp nhận sự kiện mới hơn theo timestamp. Nếu timestamp không đáng tin cậy hoặc hai sự kiện có cùng thời điểm, cần dùng sequence/version do nguồn có thẩm quyền cấp hoặc một quy tắc thứ tự khác. Không lấy thời gian máy ứng dụng làm thứ tự tuyệt đối nếu đồng hồ có thể lệch.

## 12. Xử lý lỗi duplicate và retry đúng loại

Không phải mọi lỗi ghi đều nên retry. Cần phân loại:

| Tình huống | Hành động thường phù hợp |
|---|---|
| Unique conflict là kết quả nghiệp vụ đã tồn tại | Chạy nhánh upsert/DO NOTHING hoặc đọc hàng hiện có |
| Duplicate key không mong đợi | Kiểm tra constraint nào bị vi phạm và logic khóa |
| Deadlock | Rollback toàn transaction và retry có giới hạn |
| Serialization failure | Retry toàn transaction theo semantics isolation |
| Lock timeout | Xem blocker và tải; retry có backoff nếu lỗi tạm thời |
| Connection lost trong lúc commit | Kết quả commit có thể chưa rõ; dùng idempotency key để truy vấn trạng thái |
| Validation/foreign key error | Sửa dữ liệu hoặc quy tắc; không retry vô hạn |

Mã lỗi thường gặp:

- PostgreSQL: SQLSTATE 23505 cho unique violation; 40001 cho serialization failure; 40P01 cho deadlock detected.
- MySQL: error 1062 cho duplicate entry; deadlock và lock wait timeout có mã riêng theo engine/driver.
- SQL Server: 2601 hoặc 2627 cho vi phạm unique index/constraint; deadlock victim thường là error 1205.
- Oracle: ORA-00001 cho unique constraint violation; deadlock và serialization error có mã riêng.

Hãy xác định đúng constraint/index gây lỗi. Một bảng có thể có unique key cho external_id, email và username; bắt mọi duplicate như cùng một kết quả “đã tồn tại” có thể che giấu lỗi nghiệp vụ.

### Retry phải có giới hạn

Một chính sách retry nên có:

- Số lần thử tối đa.
- Exponential backoff và jitter.
- Timeout tổng của thao tác.
- Phân loại lỗi được phép retry.
- Idempotency key hoặc cơ chế chống áp dụng hai lần.
- Log về attempt, constraint, transaction và correlation ID.

Nếu retry ngay lập tức khi một khóa nóng đang bị tranh chấp, nhiều worker có thể đồng loạt thử lại và làm hàng đợi tăng. Backoff phân tán giúp giảm đồng bộ hóa các lần thử.

### Timeout khi COMMIT

Nếu client mất kết nối ngay lúc gửi COMMIT, ứng dụng có thể không biết transaction đã commit hay chưa. Không nên đơn giản gửi lại thao tác ghi nếu thao tác không idempotent. Dùng idempotency key để truy vấn kết quả đã lưu hoặc để lần retry tiếp theo nhận ra request đã được xử lý.

## 13. Thiết kế unique index cho hiệu năng upsert

Unique index vừa bảo vệ dữ liệu vừa là đường truy cập để tìm hàng conflict. Cần thiết kế index theo khóa nghiệp vụ:

- Đúng cột và đúng phạm vi uniqueness.
- Các cột khóa có kiểu dữ liệu phù hợp, độ dài hợp lý.
- Collation và chuẩn hóa phù hợp với semantics.
- Tránh biểu thức hoặc chuyển kiểu khác nhau giữa lúc ghi và truy vấn.
- Không tạo nhiều unique index trùng lặp nếu không có mục tiêu.
- Cân nhắc partial/filtered unique index khi uniqueness chỉ áp dụng cho tập con.

Ví dụ, mỗi tenant chỉ có một tài khoản đang hoạt động theo external_ref:

```sql
-- PostgreSQL
CREATE UNIQUE INDEX uq_active_account_external
ON accounts (tenant_id, external_ref)
WHERE status = 'ACTIVE';
```

Upsert phải nhắm đúng unique index và predicate. Hàng có status khác ACTIVE không thuộc phạm vi uniqueness này. Nếu nghiệp vụ yêu cầu một tài khoản cho mọi trạng thái, partial index không phù hợp.

### Thứ tự cột và truy vấn phụ

Đối với unique constraint ghép, uniqueness áp dụng trên toàn bộ tổ hợp. Thứ tự cột thường không thay đổi tập tổ hợp được coi là trùng, nhưng ảnh hưởng khả năng dùng index cho truy vấn chỉ lọc theo tiền tố.

Ví dụ (tenant_id, external_id) hỗ trợ tìm theo tenant_id và cả cặp khóa. Nếu workload thường tìm external_id trên toàn hệ thống, index này không nhất thiết tối ưu cho truy vấn đó. Không thêm index chỉ vì có thể; hãy dựa trên workload.

### Chi phí cập nhật unique index

Khi cập nhật cột nằm trong unique key, DB phải kiểm tra khóa mới và có thể di chuyển mục index. Thay đổi khóa có thể xung đột với hàng khác hoặc tạo deadlock nếu nhiều transaction đổi khóa theo thứ tự khác nhau.

Nếu khóa ngoài là định danh ổn định, nên tránh cập nhật nó thường xuyên. Nếu cần đổi, hãy định nghĩa quy trình đổi khóa, xử lý collision và tham chiếu từ bảng khác.

## 14. Đo hiệu năng upsert và unique-key contention

Benchmark upsert phải mô phỏng cả phân bố khóa và mức độ trùng, không chỉ tổng số hàng. Hai workload cùng 10.000 lần ghi/giây có thể có hành vi rất khác:

- Mỗi request ghi một khóa riêng: contention theo hàng có thể thấp.
- Mọi request ghi cùng một khóa: các transaction phải tuần tự hóa trên điểm nóng.
- Phần lớn request là duplicate/no-op: CPU và lock có thể tiêu tốn cho kiểm tra conflict.
- Khóa phân bố lệch: một số khóa nóng chiếm phần lớn request.

### Các chỉ số nên thu thập

| Chỉ số | Mục đích |
|---|---|
| Insert/s và update/s | Phân biệt nhánh tạo mới và nhánh cập nhật |
| Conflict rate | Tỷ lệ khóa đã tồn tại |
| No-op rate | Tỷ lệ payload không làm thay đổi dữ liệu |
| p50/p95/p99 latency | Đo độ trễ từng thao tác |
| Lock wait và deadlock | Nhận diện tranh chấp cùng khóa |
| Unique violation count | Phân biệt conflict được xử lý với lỗi duplicate |
| WAL/log bytes | Đo chi phí ghi và phục hồi |
| Index size và write amplification | Đánh giá chi phí index |
| CPU và I/O | Tìm nút thắt thực thi |
| Retry count và timeout | Phát hiện cạnh tranh hoặc lỗi tạm thời |

### Thiết kế bài đo

1. Tạo dữ liệu có quy mô và phân bố giống production.
2. Chuẩn bị các nhóm khóa: duy nhất, trùng lặp thấp, trùng lặp cao và hot key.
3. Chạy mức concurrency tăng dần.
4. Đo riêng insert mới, update có thay đổi và update no-op.
5. Đo cùng lúc workload đọc/ghi khác trên bảng.
6. So sánh latency, throughput, lock wait, log và CPU.
7. Kiểm tra tính đúng đắn: mỗi khóa chỉ có một hàng và giá trị cuối theo quy tắc thứ tự mong muốn.

Đừng chỉ đo throughput tổng. Một cách upsert có thể đạt số thao tác/giây cao hơn nhưng làm p99 tăng mạnh trên hot key hoặc tăng write amplification cho toàn bảng.

## 15. Ví dụ tổng hợp: tiếp nhận webhook lặp

Một hệ thống nhận webhook từ đối tác. Đối tác có thể gửi lại cùng event_id khi không nhận được phản hồi. Yêu cầu:

- Mỗi event của đối tác chỉ được xử lý một lần.
- Request lặp phải nhận lại kết quả đã xử lý.
- Cùng event_id nhưng payload khác phải được phát hiện.
- Ghi event và thay đổi trạng thái đơn hàng phải nhất quán trong DB.

### Thiết kế dữ liệu

```sql
CREATE TABLE webhook_events (
    partner_id BIGINT NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    response_body TEXT,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (partner_id, event_id)
);
```

Khóa chính ghép tạo namespace event_id theo partner. payload_hash giúp phát hiện cùng khóa nhưng payload khác.

### Luồng xử lý

1. Bắt đầu transaction.
2. Thử INSERT event với trạng thái RECEIVED.
3. Nếu insert thành công, kiểm tra và cập nhật đơn hàng, ghi kết quả xử lý, đổi event sang COMPLETED.
4. Commit cả event và thay đổi đơn hàng.
5. Nếu conflict, đọc event hiện có. Nếu payload_hash giống, trả lại kết quả đã lưu hoặc trạng thái đang xử lý theo giao thức. Nếu hash khác, trả lỗi xung đột dữ liệu.

Với PostgreSQL có thể dùng INSERT ... ON CONFLICT DO NOTHING RETURNING để biết request nào giành quyền xử lý đầu tiên. Nếu không có hàng trả về, đọc bản ghi hiện tại ở câu lệnh tiếp theo. Nếu cần xử lý trạng thái PENDING qua nhiều transaction hoặc worker, cần thêm lease/owner/timeout và quy tắc phục hồi khi worker chết.

Không nên chỉ ghi idempotency key rồi gọi dịch vụ ngoài trong cùng transaction DB. Nếu dịch vụ ngoài thành công nhưng transaction DB rollback, lần retry có thể gọi dịch vụ lần nữa. Dùng transactional outbox và consumer idempotent khi cần phối hợp DB với hệ thống bên ngoài.

## 16. Những sai lầm thường gặp

- **SELECT rồi INSERT mà không có unique constraint:** tạo race condition và dữ liệu trùng.
- **Dùng SELECT FOR UPDATE trên khóa chưa tồn tại rồi tin rằng đã khóa:** không có hàng để khóa; phạm vi khóa phụ thuộc DBMS và isolation.
- **Bắt mọi duplicate key rồi bỏ qua:** có thể che giấu vi phạm ở unique key khác.
- **Tạo unique index sai phạm vi:** khóa tenant hoặc namespace bị bỏ sót, hoặc uniqueness bị áp dụng quá rộng.
- **Không chuẩn hóa khóa:** các dạng viết khác nhau có thể tạo bản ghi trùng theo nghiệp vụ.
- **Dùng MySQL ON DUPLICATE KEY UPDATE khi bảng có nhiều unique key mà chưa đánh giá:** conflict có thể đến từ khóa khác với khóa ứng dụng dự kiến.
- **Cho rằng MERGE luôn tránh race:** cần hiểu concurrency semantics và vẫn giữ unique constraint.
- **UPDATE mọi cột ở mọi lần conflict:** tạo log, row version, trigger và index maintenance không cần thiết.
- **Ghi đè dữ liệu mới bằng sự kiện cũ:** thiếu version hoặc quy tắc thứ tự cập nhật.
- **Retry duplicate như lỗi tạm thời:** duplicate có thể là kết quả nghiệp vụ, không phải lỗi cần thử lại.
- **Retry transaction không idempotent:** có thể ghi trùng side effect hoặc tăng bộ đếm nhiều lần.
- **Tăng worker trên hot key:** có thể làm số phiên chờ tăng mà throughput không cải thiện.
- **Chỉ đo insert mới:** bỏ qua chi phí nhánh update, no-op và unique conflict.

## 17. Checklist thiết kế upsert

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Khóa nghiệp vụ và phạm vi uniqueness là gì? | Có khóa chính/unique constraint đúng |
| Các cột khóa có NOT NULL khi cần không? | Semantics NULL đã được xác định |
| Hoa/thường, dấu và chuẩn hóa có rõ ràng không? | Index và ứng dụng dùng cùng quy tắc |
| Có đang SELECT trước rồi INSERT không? | Database vẫn bảo vệ bằng unique constraint |
| DBMS hỗ trợ cú pháp upsert nào? | Đã kiểm tra đúng phiên bản và semantics |
| Bảng có nhiều unique key không? | Mọi conflict path đã được đánh giá |
| Nhánh UPDATE có ghi giá trị không đổi không? | Có điều kiện loại bỏ no-op nếu phù hợp |
| Sự kiện cũ có thể ghi đè sự kiện mới không? | Có version/timestamp đáng tin cậy |
| Có hot key không? | Đã đo phân bố khóa và lock wait |
| Retry có phân biệt lỗi duplicate và lỗi tạm thời không? | Có phân loại mã lỗi và giới hạn retry |
| Request có thể được gửi lặp không? | Có idempotency key và lưu kết quả |
| Upsert có ảnh hưởng workload khác không? | Đã đo p95/p99, log, CPU, I/O và write amplification |

## 18. Nguyên tắc ra quyết định

Upsert là một thao tác đồng thời, không chỉ là một nhánh if trong ứng dụng. SELECT kiểm tra trước không ngăn được transaction khác ghi cùng khóa. Unique constraint/index phải bảo vệ quy tắc dữ liệu, còn cú pháp upsert của từng DBMS quyết định cách xử lý conflict và nhánh update.

Hãy xác định khóa nghiệp vụ, phạm vi uniqueness, NULL và quy tắc chuẩn hóa trước khi chọn câu lệnh. Dùng cơ chế upsert phù hợp với PostgreSQL, MySQL, SQL Server hoặc Oracle; giữ transaction ngắn; tránh UPDATE no-op; xử lý duplicate, deadlock và serialization failure theo đúng loại lỗi; và dùng idempotency key cho request có thể được gửi lại.

Khi nhiều transaction cùng ghi một khóa nóng, database phải đồng bộ hóa chúng. Muốn cải thiện hiệu năng, cần đo conflict rate, lock wait, p95/p99, log và phân bố khóa; sau đó giảm số lần ghi không cần thiết hoặc thay đổi cách gom và phân phối công việc khi semantics cho phép. Kết quả cuối phải vừa bảo đảm mỗi khóa chỉ có dữ liệu hợp lệ, vừa duy trì throughput và độ trễ phù hợp cho toàn workload.
