# Rà soát thiết kế giao dịch trước khi đưa vào vận hành

Trước khi đưa một luồng ghi dữ liệu vào production, cần rà soát cách transaction bảo vệ quy tắc nghiệp vụ khi nhiều request chạy đồng thời, khi một câu SQL thất bại, khi kết nối bị ngắt và khi hệ thống phải retry. Một thiết kế có thể chạy đúng trong kiểm thử tuần tự nhưng vẫn gây lost update, write skew, deadlock, dữ liệu trùng hoặc transaction mở lâu khi tải thật tăng lên.

Rà soát transaction không chỉ là xem code có `BEGIN`, `COMMIT` và `ROLLBACK` hay không. Cần hiểu invariant nào phải luôn đúng, những hàng và bảng nào cùng tạo thành một đơn vị nguyên tử, isolation level có bảo vệ được các lần đọc hay không, khóa được lấy theo thứ tự nào, và ứng dụng xử lý thế nào khi không biết commit đã thành công hay chưa.

Bài học này trình bày một cách rà soát có hệ thống, từ yêu cầu nghiệp vụ đến SQL, code ứng dụng, vận hành và triển khai. Mục tiêu là có thể giải thích được transaction sẽ làm gì trong cả đường chạy bình thường lẫn các tình huống cạnh tranh và lỗi.

## 1. Bắt đầu từ invariant nghiệp vụ

Invariant là điều kiện dữ liệu phải luôn đúng sau mọi transaction được commit. Nếu chưa nêu rõ invariant, rất khó chọn isolation level hoặc khóa phù hợp.

Ví dụ với đơn hàng và tồn kho:

- Số lượng tồn kho không được âm.
- Một đơn hàng chỉ có một reservation đang hiệu lực cho cùng một lần đặt.
- Tổng số lượng đã reserve không vượt quá số lượng được phép bán.
- Đơn hàng chỉ chuyển sang `CONFIRMED` khi reservation được ghi nhận thành công.
- Một yêu cầu nghiệp vụ được gửi lại không tạo thêm một đơn hàng hoặc một lần trừ tồn kho.

Với chuyển tiền:

- Số dư không được thấp hơn mức cho phép.
- Một lần chuyển tiền phải trừ tài khoản nguồn và cộng tài khoản đích cùng nhau.
- Tổng tiền giữa hai tài khoản được bảo toàn, trừ phí được định nghĩa rõ.
- Cùng một operation ID không được tạo hai lần chuyển tiền.

Hãy diễn đạt invariant bằng điều kiện có thể kiểm tra. Ví dụ:

\[
available\_quantity \geq 0
\]

hoặc:

\[
debit(operation) + credit(operation) = 0
\]

Invariant có thể nằm trên một hàng, nhiều hàng, nhiều bảng hoặc cả hệ thống. Một `CHECK` constraint có thể bảo vệ điều kiện trên một hàng; unique constraint bảo vệ tính duy nhất; foreign key bảo vệ tham chiếu; nhưng quy tắc tổng hợp nhiều hàng có thể cần transaction protocol, hàng điều phối, exclusion constraint hoặc Serializable tùy mô hình và DBMS.

Trong buổi review, hãy yêu cầu người thiết kế trả lời: “Sau khi transaction commit, điều gì bắt buộc phải đúng?” Nếu câu trả lời chỉ là “các câu SQL chạy không lỗi”, thiết kế chưa mô tả đủ yêu cầu.

## 2. Xác định đơn vị nguyên tử và ranh giới transaction

Một transaction nên bao gồm các thay đổi cần cùng thành công hoặc cùng thất bại để giữ invariant. Không nên gộp mọi công việc của một request vào một transaction dài chỉ vì chúng thuộc cùng một API.

Ví dụ tạo đơn hàng có thể gồm:

1. Kiểm tra sản phẩm và giá.
2. Giữ chỗ tồn kho.
3. Tạo đơn hàng và các dòng đơn.
4. Ghi reservation.
5. Ghi sự kiện cần phát sau commit.

Nếu việc giữ chỗ, tạo đơn và ghi reservation phải cùng tồn tại hoặc cùng bị hủy, chúng cần nằm trong cùng transaction database. Gọi dịch vụ vận chuyển hoặc gửi email thường không cần nằm trong transaction đó; nên phát yêu cầu qua outbox sau khi commit.

Sơ đồ một ranh giới hợp lý:

```text
Request
  |
  +-- Đọc dữ liệu tham khảo / tính toán không giữ khóa
  |
  +-- BEGIN
  |     kiểm tra lại điều kiện có thể thay đổi
  |     cập nhật tồn kho có điều kiện
  |     tạo order và order lines
  |     tạo reservation
  |     ghi outbox event
  +-- COMMIT
  |
  +-- Worker gửi event / gọi dịch vụ bên ngoài
```

Khi review, hãy đánh dấu rõ:

- Điểm bắt đầu transaction.
- Những câu lệnh chạy bên trong.
- Điểm commit hoặc rollback.
- Các thao tác nào xảy ra trước hoặc sau transaction.
- Nếu một bước thất bại, những thay đổi nào phải bị hủy.

Đặc biệt, đừng để transaction mở trong lúc chờ người dùng, HTTP service, message broker, file I/O hoặc một thao tác có độ trễ không kiểm soát. Thời gian chờ bên ngoài thường kéo dài thời gian giữ khóa và làm tăng contention.

## 3. Kiểm tra mọi đường thực thi đều kết thúc transaction

Với mỗi nhánh code, cần xác định transaction sẽ commit hay rollback. Các nhánh cần xem gồm:

- Thành công bình thường.
- Validation thất bại sau khi transaction đã bắt đầu.
- SQL constraint violation.
- Deadlock hoặc serialization failure.
- Query timeout hoặc người dùng hủy request.
- Runtime exception trong lúc xử lý.
- Mất kết nối trước commit, trong commit hoặc sau commit.
- Lỗi rollback hoặc lỗi reset connection.

Trong Java/JDBC, việc gọi `Connection.close()` trên pooled connection thường trả logical connection về pool; nó không phải bằng chứng transaction đã rollback hoặc physical session đã bị đóng. Transaction manager/pool cần bảo đảm rollback và reset trạng thái trước khi tái sử dụng. Nếu trạng thái connection không thể xác nhận, connection cần bị loại khỏi pool.

Một cấu trúc JDBC khái niệm:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        performDatabaseWork(connection);
        connection.commit();
    } catch (Exception error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
            // Connection có thể không còn an toàn để tái sử dụng.
        }
        throw error;
    }
}
```

Đây là khung minh họa. Code production cần phân loại lỗi, xử lý commit outcome chưa xác định và dùng API của transaction manager/pool để đánh dấu connection hỏng khi cần. Không nuốt exception rồi tiếp tục như thể transaction đã thành công.

Nếu dùng Spring hoặc một framework transaction khác, review propagation, rollback rules, checked/unchecked exception, nested transaction và cách framework lấy/trả connection. Annotation `@Transactional` không tự bảo vệ mọi trường hợp nếu exception bị bắt rồi không được ném tiếp, hoặc method được gọi theo cách không đi qua transaction proxy.

## 4. Chọn isolation level dựa trên anomaly cần ngăn

Không chọn isolation level chỉ vì một mức “cao hơn nghe có vẻ an toàn hơn”. Hãy xác định anomaly mà nghiệp vụ không chấp nhận và hiểu semantics của DBMS.

| Mức/chiến lược | Cần cân nhắc |
|---|---|
| Read Uncommitted | Có thể cho phép dirty read ở một số DBMS; nhiều engine MVCC không triển khai đúng nghĩa đọc dữ liệu chưa commit. |
| Read Committed | Mỗi câu lệnh có thể nhìn thấy snapshot khác nhau; cần chú ý non-repeatable read và quyết định dựa trên nhiều lần đọc. |
| Repeatable Read / Snapshot Isolation | Có snapshot ổn định hơn, nhưng một số DBMS vẫn có thể cho phép write skew hoặc anomaly phụ thuộc predicate. |
| Serializable | Bảo đảm kết quả tương đương một thứ tự tuần tự theo semantics DBMS, nhưng có thể chờ khóa hoặc hủy transaction để retry. |

Ví dụ write skew: hai bác sĩ A và B đều đang trực, invariant yêu cầu ít nhất một người trực. Hai transaction cùng đếm thấy có hai người rồi mỗi transaction tắt một người khác nhau. Vì cập nhật hai hàng khác nhau, Snapshot Isolation có thể cho cả hai commit. Serializable có thể phát hiện phụ thuộc nguy hiểm và từ chối một transaction; một hàng điều phối được khóa tường minh cũng có thể tuần tự hóa quyết định.

Rà soát phải hỏi:

- Có nhiều lần đọc mà kết quả đọc trước được dùng để quyết định ghi sau không?
- Predicate có thể bị transaction khác làm thay đổi bằng cách thêm hàng mới không?
- Có invariant tổng hợp qua nhiều hàng không?
- Có thể chuyển quy tắc thành một câu lệnh cập nhật có điều kiện không?
- Có cần `SELECT ... FOR UPDATE`, hàng điều phối hoặc Serializable không?
- Nếu Serializable trả serialization failure, code có retry toàn transaction không?

Isolation level cùng tên giữa PostgreSQL, MySQL InnoDB, SQL Server và Oracle không nhất thiết có cùng cơ chế triển khai. Cần kiểm tra đúng DBMS, phiên bản và cấu hình đang chạy.

## 5. Rà soát cách đọc rồi ghi

Một mẫu dễ sai là đọc giá trị, tính trong ứng dụng rồi ghi lại mà không bảo vệ giá trị đã đọc:

```sql
SELECT balance
FROM account
WHERE account_id = :id;

-- Ứng dụng tính new_balance = balance - :amount

UPDATE account
SET balance = :new_balance
WHERE account_id = :id;
```

Hai transaction có thể cùng đọc một số dư cũ rồi ghi đè kết quả của nhau. Tùy mục tiêu, có thể dùng cập nhật nguyên tử:

```sql
UPDATE account
SET balance = balance - :amount
WHERE account_id = :id
  AND balance >= :amount;
```

Sau đó kiểm tra số hàng bị ảnh hưởng. Nếu cần đọc nhiều trường và thực hiện nhiều quyết định, có thể khóa hàng bằng `FOR UPDATE` hoặc cơ chế tương đương. Nếu quyết định phụ thuộc vào predicate nhiều hàng, khóa một hàng cụ thể có thể chưa đủ.

Khi review, tìm các mẫu:

- `SELECT` rồi `UPDATE` dựa trên giá trị đọc.
- `COUNT(*)` rồi `INSERT` để giới hạn số lượng.
- Kiểm tra tồn tại rồi insert.
- Đọc trạng thái rồi chuyển trạng thái.
- Đọc version rồi ghi mà không có điều kiện version.
- Cập nhật nhiều hàng theo một thứ tự khác nhau giữa các luồng.

Với mỗi mẫu, hỏi transaction đồng thời có thể thay đổi dữ liệu giữa lần đọc và lần ghi hay không, và cơ chế nào ngăn điều đó.

## 6. Kiểm tra khóa tường minh và thứ tự lấy khóa

Khóa tường minh cần có lý do và phạm vi cụ thể. Dùng `FOR UPDATE` cho mọi truy vấn có thể giảm throughput và làm tăng thời gian chờ. Dùng khóa yếu hơn nếu vẫn bảo vệ được invariant, hoặc dùng cập nhật nguyên tử khi phù hợp.

Hai transaction lấy cùng tập khóa theo thứ tự ngược nhau có thể deadlock:

```text
T1: khóa A -> yêu cầu B
T2: khóa B -> yêu cầu A
```

Một quy tắc toàn cục có thể yêu cầu luôn khóa theo ID tăng dần:

```text
ids = sort(unique([accountA, accountB]))
BEGIN
  khóa ids[0]
  khóa ids[1]
  kiểm tra và ghi
COMMIT
```

Quy tắc này phải áp dụng trên mọi đường code có thể chạm cùng tài nguyên, gồm worker nền, trigger, stored procedure, FK và cascade. Thứ tự câu SQL trong code không phải lúc nào cũng cho biết toàn bộ thứ tự khóa vật lý; hãy đối chiếu deadlock graph và hành vi engine.

Khi review, liệt kê:

- Hàng hoặc tài nguyên logic được khóa.
- Thứ tự các bảng được truy cập.
- Các vòng lặp cập nhật nhiều ID.
- Advisory/application lock nếu có.
- Trigger và cascade có thể truy cập tài nguyên bổ sung.
- Các đường code khác dùng thứ tự ngược lại.

## 7. Tính cả khóa ngầm từ index, constraint và trigger

Một câu SQL ngắn có thể tạo nhiều thao tác database hơn những gì code thể hiện. Index phải được duy trì; unique constraint phải phối hợp insert trùng; foreign key phải xác nhận hàng cha; cascade có thể cập nhật nhiều hàng con; trigger có thể ghi audit hoặc cập nhật bảng khác.

Ví dụ cập nhật hàng con:

```sql
UPDATE employee
SET department_id = :new_department_id
WHERE employee_id = :employee_id;
```

Ngoài hàng `employee`, engine có thể kiểm tra hàng `department`, cập nhật index trên FK và chạy trigger. Một transaction khác xóa department hoặc ghi audit có thể chạm tài nguyên liên quan theo thứ tự khác.

Trước khi phát hành, cần biết:

- Index nào được duy trì bởi mỗi câu insert/update/delete.
- Unique key nào có thể bị tranh chấp.
- FK nào được kiểm tra và hành động `ON DELETE`/`ON UPDATE` là gì.
- Index phía con có hỗ trợ tìm hàng tham chiếu hiệu quả không.
- Trigger, procedure và ORM flush sinh ra SQL phụ nào.
- DDL/migration có thể gây metadata/schema lock không.

Không tắt constraint hoặc trigger chỉ để giảm lock wait nếu chưa có cơ chế tương đương bảo vệ invariant. Nếu trigger phức tạp, hãy xem xét xử lý set-based hoặc transactional outbox nhưng phải giữ semantics nghiệp vụ.

## 8. Kiểm tra deadlock và chiến lược retry

Deadlock là kết quả có thể xảy ra trong hệ thống đồng thời, kể cả khi đã thiết kế thứ tự khóa tốt. Cần có chính sách retry rõ ràng:

1. Nhận diện lỗi deadlock hoặc serialization failure bằng SQLSTATE/vendor code của DBMS/driver.
2. Kết thúc transaction lỗi bằng rollback nếu nó còn mở; xác nhận connection sạch.
3. Chờ backoff có giới hạn và jitter.
4. Bắt đầu transaction mới.
5. Đọc lại dữ liệu và chạy lại toàn bộ logic, không chỉ câu SQL cuối.
6. Giới hạn số lần thử và trả lỗi tạm thời khi vượt ngưỡng.

Ví dụ các mã thường gặp:

| DBMS | Deadlock | Serialization/update conflict |
|---|---|---|
| PostgreSQL | `40P01` | `40001` |
| MySQL InnoDB | Error `1213` | Có thể dùng `40001` cho deadlock; cần phân loại theo vendor code và nguyên nhân thực tế. |
| SQL Server | Error `1205` | Error `3960` cho snapshot update conflict. |
| Oracle | `ORA-00060` | `ORA-08177` |

Đừng retry mọi `SQLException`. Unique/FK/check violation thường là lỗi dữ liệu hoặc xung đột nghiệp vụ; timeout có thể cần trả trạng thái bận; lỗi mạng trong lúc commit có thể có kết quả chưa xác định. Adapter database nên phân loại lỗi theo vendor code, SQLSTATE và trạng thái transaction.

## 9. Xử lý commit outcome chưa xác định

Một tình huống đặc biệt nguy hiểm là client gửi `COMMIT`, database đã commit nhưng phản hồi bị mất do network timeout. Từ phía client, không thể kết luận transaction thất bại chỉ vì không nhận được response.

```text
Application                    Database
    |                              |
    |----------- COMMIT ---------->|
    |                              | Commit thành công
    |<------ response lost --------X
    |
    +-- Client thấy timeout
```

Nếu ứng dụng gửi lại một thao tác không idempotent, dữ liệu có thể bị nhân đôi. Thiết kế nên có operation ID hoặc idempotency key ổn định, được ghi cùng thay đổi nghiệp vụ trong một transaction.

Ví dụ:

```sql
CREATE TABLE processed_operation (
    operation_id VARCHAR(100) PRIMARY KEY,
    result_reference VARCHAR(200),
    completed_at TIMESTAMP NOT NULL
);
```

Khi nhận lại cùng operation ID, ứng dụng kiểm tra bản ghi đã xử lý và trả kết quả đã lưu. Nếu chưa có, có thể chạy lại với cùng key và unique constraint vẫn ngăn hai lần xử lý logic tạo hiệu ứng trùng.

Không dùng `SELECT 1` trên connection mới để kết luận transaction trước đã rollback. Cần đối soát dữ liệu bền vững theo operation ID hoặc cơ chế nghiệp vụ tương đương.

## 10. Tác dụng phụ ngoài database: outbox hoặc saga

Gửi email, gọi API thanh toán hoặc phát message trực tiếp bên trong transaction tạo hai cửa sổ lỗi:

- Tác dụng phụ bên ngoài đã xảy ra nhưng transaction database rollback.
- Database commit thành công nhưng process chết trước khi gửi tác dụng phụ.

Transactional outbox ghi sự kiện trong cùng transaction với dữ liệu nghiệp vụ:

```sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :order_id;

INSERT INTO outbox (event_id, event_type, aggregate_id, payload, status)
VALUES (:event_id, 'ORDER_CONFIRMED', :order_id, :payload, 'PENDING');

COMMIT;
```

Worker đọc outbox và gửi sau commit. Worker/consumer phải idempotent vì message có thể được gửi lại. Nếu quy trình trải qua nhiều service và không thể dùng một transaction chung, cân nhắc saga với các bước bù trừ (compensation) được định nghĩa rõ.

Trong review, xác định tác dụng phụ nào có thể lặp, mất hoặc xảy ra trước commit; yêu cầu operation ID, deduplication hoặc outbox tương ứng.

## 11. Đánh giá transaction duration, timeout và connection pool

Transaction dài làm tăng thời gian giữ khóa, giữ snapshot và chi phí rollback. Review cần đo hoặc ước lượng:

- Thời gian transaction bình thường và p95/p99.
- Số câu lệnh và số hàng bị tác động.
- Thời gian chờ khóa.
- Thời gian chờ lấy connection từ pool.
- Thời gian commit/flush log.
- Thời gian xử lý ngoài database khi connection đang được giữ.

Các timeout cần có vai trò riêng:

| Timeout | Bảo vệ điều gì? |
|---|---|
| Pool acquisition timeout | Thời gian request chờ connection. |
| Query/command timeout | Thời gian câu SQL được phép chạy ở client/driver. |
| Lock wait timeout | Thời gian chờ khóa theo cấu hình DBMS. |
| Transaction/request deadline | Thời gian tối đa cho toàn bộ đơn vị công việc. |
| Cleanup budget | Thời gian dành cho cancel, rollback và trả/discard connection. |

Không để HTTP timeout ngắn hơn query timeout đến mức client đã đóng request nhưng SQL vẫn tiếp tục chạy mà không có cancellation path. Cũng cần dành thời gian cho rollback và cleanup. Timeout của pool hoặc session có thể được giữ trên connection tái sử dụng; phải reset đúng cách.

Kiểm tra connection pool có đủ capacity cho concurrency dự kiến nhưng không mở quá nhiều connection gây áp lực lên database. Connection bị giữ trong lúc chờ dịch vụ ngoài có thể làm pool cạn dù database CPU thấp.

## 12. Rà soát transaction trong Java và ORM

Với JDBC, xem rõ `autoCommit`, connection ownership, commit/rollback, savepoint và việc trả connection về pool. Với ORM, cần xem SQL thực tế được sinh ra và thời điểm flush.

Các câu hỏi quan trọng:

- Transaction bắt đầu ở tầng service hay repository?
- Có lời gọi method qua proxy/transaction boundary đúng cách không?
- Propagation `REQUIRED`, `REQUIRES_NEW` hoặc nested/savepoint có đúng ý nghĩa không?
- Exception nào làm framework rollback? Có exception bị catch rồi bỏ qua không?
- ORM có flush sớm trước query hoặc cuối transaction không?
- Cascade của ORM có xóa/cập nhật thêm entity nào không?
- Optimistic locking dùng version column có kiểm tra số hàng cập nhật không?
- Lazy loading có vô tình chạy query khi transaction còn mở không?
- Có N+1 query làm transaction kéo dài không?

Một method service có annotation transaction không chứng minh toàn bộ logic nằm trong transaction. Cần kiểm tra call path, proxy, propagation và connection thực sự được dùng.

## 13. Rà soát index, query plan và phạm vi khóa

Index phù hợp có thể rút ngắn thời gian tìm hàng và giảm thời gian giữ khóa. Ngược lại, thêm nhiều index làm insert/update/delete tốn hơn vì phải duy trì thêm cấu trúc.

Với mỗi câu lệnh ghi quan trọng, xem:

- Predicate có dùng index phù hợp không?
- Rows estimated và actual có chênh lệch lớn không?
- Có scan nhiều hàng hơn số hàng cần cập nhật không?
- Có range/gap/key-range lock theo isolation level không?
- FK phía con có index hỗ trợ delete/update cha không?
- Trigger hoặc cascade có làm tăng số hàng thực tế không?
- Index mới cải thiện đọc nhưng làm tăng chi phí ghi đến mức nào?

Đừng suy ra lock footprint chỉ từ số hàng trong `WHERE`. MySQL InnoDB, SQL Server, PostgreSQL và Oracle có cơ chế khóa khác nhau; execution plan, index và isolation level có thể làm phạm vi tài nguyên bị chạm thay đổi.

## 14. Xác định hành vi khi có lỗi và cancellation

Review cần có bảng lỗi và hành động tương ứng, không chỉ một `catch (Exception)` chung.

| Tình huống | Kết quả cần xác định | Hành động gợi ý |
|---|---|---|
| Deadlock | Transaction/câu lệnh nào bị rollback theo DBMS? | Rollback/cleanup và retry toàn transaction nếu an toàn. |
| Serialization failure | Transaction bị từ chối commit? | Rollback và retry từ đầu với snapshot mới. |
| Lock timeout/NOWAIT | Statement hay transaction bị lỗi? | Kiểm tra trạng thái, rollback theo đơn vị nghiệp vụ hoặc trả busy. |
| Constraint violation | Dữ liệu nào vi phạm? | Trả lỗi nghiệp vụ hoặc xử lý duplicate có chủ đích. |
| Query cancellation | SQL đã dừng chưa, transaction còn mở không? | Cancel, rollback và xác nhận connection sạch. |
| Connection loss trong commit | Commit đã xảy ra chưa? | Đối soát bằng operation ID trước khi retry. |
| Rollback failure | Connection còn tin cậy không? | Discard physical connection và theo dõi cleanup phía DBMS. |

Hành vi sau lỗi khác nhau theo DBMS. Ví dụ PostgreSQL thường đánh dấu transaction aborted sau lỗi SQL trong transaction block; InnoDB có thể rollback toàn transaction khi deadlock nhưng chỉ rollback statement khi lock timeout theo cấu hình mặc định; SQL Server có thể cần `XACT_STATE()`; Oracle thường rollback câu lệnh gây lỗi và để transaction tiếp tục. Không dùng một giả định chung cho tất cả engine.

## 15. Kiểm tra observability trước khi phát hành

Khi transaction gặp vấn đề trong production, đội vận hành phải xác định được request, session, transaction, câu SQL và blocker có liên quan. Một thiết kế tốt cần cung cấp đủ tín hiệu mà không làm lộ dữ liệu nhạy cảm.

Các metric nên có:

- Logical transaction count theo operation và outcome.
- Transaction attempt count và retry count theo error category.
- Transaction duration histogram: p50, p95, p99.
- Commit latency và rollback latency.
- Pool acquisition latency, active/idle connection và pool saturation.
- Lock wait duration, deadlock count và serialization failure count.
- Số transaction đang mở và transaction age cao nhất.
- Số session `idle in transaction` hoặc sleeping với open transaction.
- Outbox backlog, tuổi event cũ nhất và số lần gửi lại.
- CPU, storage/log I/O, replication lag và backlog worker.

Log nên có operation ID, trace/request ID, transaction attempt, loại lỗi và DB session ID nếu có. Tránh ghi password, token, payload nhạy cảm hoặc SQL literal không cần thiết.

Metric phải phân biệt logical request với attempt. Một request có ba attempt rồi thành công là một logical success và hai retry; nếu chỉ đếm exception, dashboard có thể hiểu sai tỷ lệ lỗi cuối cùng.

## 16. Kiểm thử concurrency và failure trước production

Kiểm thử tuần tự không đủ cho thiết kế transaction. Cần kiểm tra các lịch xen kẽ có thể xảy ra bằng nhiều connection độc lập và điều khiển checkpoint.

Các kịch bản nên xem xét:

### 16.1. Lost update

Hai transaction đọc cùng giá trị rồi cập nhật. Xác nhận kết quả cuối không làm mất một thay đổi hợp lệ.

### 16.2. Write skew hoặc invariant nhiều hàng

Hai transaction đọc cùng predicate rồi cập nhật hai hàng khác nhau. Xác nhận constraint, khóa điều phối hoặc Serializable ngăn trạng thái bất hợp lệ.

### 16.3. Unique/FK race

Hai transaction tạo cùng unique key hoặc insert hàng con đồng thời với xóa hàng cha. Xác nhận database giữ constraint và ứng dụng xử lý lỗi đúng.

### 16.4. Deadlock và lock timeout

Tạo thứ tự khóa đảo ngược có kiểm soát. Xác nhận mã lỗi, transaction cleanup, retry và dữ liệu cuối.

### 16.5. Worker crash và lease expiry

Worker chết sau claim hoặc sau tác dụng phụ nhưng trước khi đánh dấu hoàn tất. Xác nhận công việc được nhận lại và idempotency ngăn tác dụng phụ trùng.

### 16.6. Cancellation và mất kết nối

Hủy câu lệnh, mất kết nối trước commit và mất phản hồi trong lúc commit. Xác nhận trạng thái transaction, connection pool và quy trình đối soát operation ID.

### 16.7. Tải cao và transaction dài

Chạy workload đại diện ở nhiều mức concurrency. Theo dõi p95/p99, lock wait, deadlock, pool wait, transaction age và backlog.

Với test đồng thời, dùng `CountDownLatch`, `CyclicBarrier` hoặc cơ chế tương đương để đặt các transaction tại checkpoint xác định. Không dựa vào `Thread.sleep()` làm bằng chứng một câu SQL đã lấy khóa hoặc đã đọc xong.

## 17. Kiểm tra migration và tương thích schema

Transaction code có thể đúng trên schema hiện tại nhưng gặp vấn đề khi migration triển khai đồng thời với traffic. Review cần xác định:

- Migration có yêu cầu khóa bảng hoặc metadata lock mạnh không?
- Thêm index có hỗ trợ online/concurrent trên DBMS và phiên bản đang dùng không?
- Thêm FK/unique constraint có quét dữ liệu cũ hoặc chặn ghi lâu không?
- Ứng dụng phiên bản cũ và mới có thể chạy đồng thời trong thời gian rollout không?
- Thay đổi cột/enum/default có tương thích với code đang chạy không?
- Có thể triển khai theo expand–migrate–contract không?
- Có kế hoạch rollback hoặc forward-fix nếu migration thất bại giữa chừng không?

Ví dụ thêm cột mới có thể triển khai theo nhiều bước: thêm cột tương thích, deploy code ghi cả hai dạng hoặc đọc fallback, backfill theo batch, xác nhận dữ liệu rồi mới chuyển đọc hoàn toàn và loại bỏ cột cũ. Cách cụ thể phụ thuộc DBMS và quy mô bảng.

Không chạy DDL dài mà không đánh giá metadata/schema lock và ảnh hưởng đến transaction đang mở. Một migration bị chặn bởi transaction cũ có thể tạo hàng đợi request mới phía sau nó.

## 18. Đánh giá tải và capacity

Một thiết kế đúng về logic vẫn có thể không vận hành được nếu transaction giữ khóa quá lâu hoặc retry quá nhiều. Benchmark cần dùng workload gần production, dữ liệu và phân phối hot key đại diện.

Đo ít nhất:

| Chỉ số | Mục đích |
|---|---|
| Successful TPS | Năng lực hoàn tất transaction logic. |
| p50/p95/p99 latency | Độ trễ điển hình và đuôi chậm. |
| Logical success/final failure rate | Tỷ lệ yêu cầu nghiệp vụ hoàn tất. |
| Retry/deadlock/serialization rate | Chi phí contention và lỗi cạnh tranh. |
| Lock wait | Mức tranh chấp tài nguyên. |
| Pool wait | Nghẽn connection ở tầng ứng dụng. |
| Transaction age | Transaction giữ snapshot/khóa lâu. |
| CPU, I/O, log flush | Mức bão hòa tài nguyên database. |
| Backlog/in-flight | Hệ thống có theo kịp tốc độ đến hay không. |

Không chọn phương án chỉ vì TPS đỉnh cao hơn. Một phương án có TPS cao nhưng p99, retry hoặc failure rate vượt SLO không phải phương án sẵn sàng production. Xác định sustainable capacity ở mức tải duy trì được trong thời gian đại diện mà vẫn đáp ứng SLO.

## 19. Một ví dụ review tổng hợp: tạo đơn và reserve inventory

Giả sử API `POST /orders` nhận `operation_id`, danh sách sản phẩm và số lượng. Thiết kế cần giữ invariant không bán vượt tồn và không tạo đơn trùng khi client retry.

### 19.1. Các câu hỏi về nghiệp vụ

- Một operation ID đại diện cho một lần đặt đơn hay một lần gửi HTTP?
- Cùng operation ID nhưng payload khác nhau phải được xử lý thế nào?
- Có cho phép một đơn chứa cùng product ID nhiều lần không? Nếu có, có gộp số lượng trước khi reserve không?
- Đơn hàng được tạo khi tất cả sản phẩm reserve thành công hay có thể một phần?
- Khi payment thất bại, reservation được giải phóng theo transaction hay saga?

### 19.2. Một transaction database khả thi

Pseudocode SQL:

```sql
BEGIN;

-- 1. Claim operation ID; unique constraint ngăn tạo trùng.
INSERT INTO processed_operation (operation_id, status)
VALUES (:operation_id, 'PROCESSING');

-- 2. Reserve từng sản phẩm theo thứ tự product_id ổn định.
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :product_id
  AND available_quantity >= :quantity;

-- Ứng dụng phải kiểm tra đúng một hàng được cập nhật cho mỗi sản phẩm.

-- 3. Tạo order và order lines.
INSERT INTO orders (...);
INSERT INTO order_line (...);

-- 4. Ghi reservation và outbox event.
INSERT INTO reservation (...);
INSERT INTO outbox (...);

-- 5. Lưu kết quả operation để lần gửi lại có thể truy vấn.
UPDATE processed_operation
SET status = 'COMPLETED', result_reference = :order_id
WHERE operation_id = :operation_id;

COMMIT;
```

Đây là cấu trúc minh họa; cần xử lý duplicate operation ID trước khi chạy lại, gộp sản phẩm trùng, rollback toàn bộ nếu một sản phẩm không đủ tồn, và dùng cú pháp phù hợp DBMS. Với nhiều sản phẩm, cập nhật theo thứ tự khóa ổn định giúp giảm deadlock.

### 19.3. Những điểm reviewer phải xác nhận

- Unique constraint trên `operation_id` thực sự được bật.
- Cập nhật inventory có điều kiện `available_quantity >= quantity`.
- Số hàng bị cập nhật được kiểm tra, không chỉ giả định thành công.
- Nếu một sản phẩm thất bại, mọi thay đổi trước đó rollback.
- Order, order lines, reservation và operation result commit cùng nhau.
- Outbox event được ghi cùng transaction; worker gửi sau commit.
- Consumer có idempotency key để chịu được message lặp.
- Các sản phẩm được reserve theo thứ tự nhất quán.
- Mất response khi commit được đối soát qua operation ID.
- Retry deadlock/serialization chạy lại toàn transaction và có giới hạn.
- Có metric để quan sát reservation conflict, retry, latency và backlog.

### 19.4. Failure matrix

| Thời điểm lỗi | Kết quả mong muốn |
|---|---|
| Trước khi bắt đầu transaction | Không có thay đổi database. |
| Sau khi reserve sản phẩm thứ nhất, sản phẩm thứ hai hết hàng | Rollback reservation thứ nhất và toàn bộ thay đổi của đơn. |
| Sau khi ghi order nhưng trước outbox, SQL lỗi | Rollback order và reservation cùng nhau. |
| Deadlock khi cập nhật inventory | Rollback attempt, retry toàn transaction có giới hạn. |
| Commit thành công nhưng response bị mất | Lần gửi lại cùng operation ID trả kết quả đã commit, không tạo đơn thứ hai. |
| Worker gửi outbox thành công rồi chết trước khi đánh dấu sent | Message có thể được gửi lại; consumer phải idempotent. |
| Payment service thất bại sau khi order commit | Chạy saga/compensation theo trạng thái nghiệp vụ, không giả vờ transaction database cũ có thể rollback xuyên service. |

## 20. Câu hỏi review theo từng lớp

### Lớp nghiệp vụ

- Invariant được viết rõ và có thể kiểm tra không?
- Một yêu cầu logic có ID ổn định để chống trùng không?
- Trạng thái một phần có được cho phép không?
- Các bước liên service cần saga hoặc compensation không?

### Lớp transaction

- Ranh giới nguyên tử có đúng không?
- Có nhánh nào thoát mà không commit/rollback không?
- Có transaction mở trong lúc chờ bên ngoài không?
- Isolation level có bảo vệ anomaly cần ngăn không?
- Có retry toàn transaction cho lỗi cạnh tranh phù hợp không?

### Lớp SQL/schema

- Có read-then-write race không?
- Index và constraint nào được chạm?
- FK, cascade, trigger hoặc ORM có sinh thao tác phụ không?
- Thứ tự khóa có nhất quán giữa mọi đường code không?
- Query plan có quét quá nhiều hàng hoặc giữ khóa lâu không?

### Lớp Java/framework

- Connection có được quản lý đúng vòng đời không?
- Framework rollback đúng loại exception không?
- Propagation và proxy boundary có đúng không?
- ORM flush/cascade có tạo SQL bất ngờ không?
- Connection lỗi có bị trả về pool không?

### Lớp vận hành

- Có timeout và cleanup budget ở từng tầng không?
- Có metric transaction age, lock wait, retry và pool wait không?
- Có thể truy từ trace ID đến DB session và operation ID không?
- Có benchmark tải đại diện và SLO rõ ràng không?
- Có runbook xử lý deadlock, transaction treo và commit outcome unknown không?

## 21. Tài liệu cần có trước khi phát hành

Một thiết kế transaction quan trọng nên có tài liệu ngắn nhưng đủ để đội phát triển và vận hành hiểu:

1. Invariant nghiệp vụ và cách kiểm chứng.
2. Sơ đồ transaction boundaries và thứ tự SQL chính.
3. Isolation level, khóa tường minh và lý do chọn.
4. Danh sách index, constraint, trigger, cascade và thao tác phụ.
5. Error mapping, retry policy, idempotency và xử lý commit outcome unknown.
6. Timeout, connection pool và giới hạn transaction duration.
7. Metric, log, trace và dashboard cần có.
8. Kịch bản concurrency/failure đã chạy và kết quả correctness.
9. Benchmark, tải mục tiêu, SLO và sustainable capacity.
10. Migration/rollout/rollback plan và runbook vận hành.

Tài liệu không cần mô tả mọi dòng code. Nó cần giúp reviewer trả lời được vì sao thiết kế giữ đúng dữ liệu, cách nó thất bại và cách đội vận hành nhận biết, xử lý khi sự cố xảy ra.

## 22. Checklist quyết định trước production

- [ ] Invariant nghiệp vụ được định nghĩa rõ và có truy vấn/test xác minh.
- [ ] Đơn vị nguyên tử và ranh giới transaction được mô tả.
- [ ] Mọi nhánh thành công/lỗi đều kết thúc transaction rõ ràng.
- [ ] Isolation level được chọn theo anomaly cần ngăn và DBMS thực tế.
- [ ] Các mẫu read-then-write, check-then-insert và predicate race đã được xử lý.
- [ ] Khóa tường minh dùng đúng phạm vi và thứ tự khóa nhất quán.
- [ ] Index, unique/FK/check/exclusion constraint, trigger, cascade và ORM side effect đã được tính đến.
- [ ] Deadlock, serialization failure, timeout và cancellation được phân loại riêng.
- [ ] Retry chạy lại toàn transaction, có giới hạn, backoff và jitter.
- [ ] Tác dụng phụ ngoài database có idempotency, outbox hoặc saga phù hợp.
- [ ] Commit outcome chưa xác định được đối soát bằng operation ID.
- [ ] Transaction không giữ connection/khóa khi chờ dịch vụ bên ngoài.
- [ ] Pool, query, lock, request và cleanup timeout được phối hợp.
- [ ] Connection không sạch hoặc rollback thất bại được loại khỏi pool.
- [ ] Có metric/log/trace để tìm transaction, blocker, retry và transaction age.
- [ ] Đã kiểm thử concurrency, deadlock, crash, cancellation và mất kết nối.
- [ ] Đã benchmark workload đại diện và xác định SLO/capacity.
- [ ] Migration tương thích với traffic và có kế hoạch rollback/forward-fix.
- [ ] Runbook nêu cách điều tra và phục hồi các lỗi transaction phổ biến.

## 23. Kết luận thực hành

Một thiết kế transaction sẵn sàng production phải giải thích được cả ba điều: dữ liệu nào phải luôn đúng, cơ chế concurrency nào bảo vệ điều đó, và ứng dụng sẽ phản ứng ra sao khi database từ chối hoặc không xác nhận một thao tác. Hãy bắt đầu từ invariant, xác định ranh giới nguyên tử, chọn isolation và khóa phù hợp, tính cả index/constraint/trigger, rồi thiết kế retry, idempotency và xử lý tác dụng phụ.

Cuối cùng, xác minh thiết kế bằng các lịch đồng thời và failure scenario có kiểm soát, đo dưới workload đại diện, đồng thời trang bị metric và runbook cho vận hành. Khi reviewer có thể lần theo một request từ operation ID đến transaction, SQL, khóa, commit và kết quả cuối cùng, thiết kế sẽ dễ đánh giá và an toàn hơn khi đi vào production.
