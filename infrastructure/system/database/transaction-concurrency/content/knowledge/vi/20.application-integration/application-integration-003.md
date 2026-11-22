# Connection pool và nguy cơ rò trạng thái autocommit hoặc mức cô lập

Connection pool tái sử dụng các kết nối vật lý đến cơ sở dữ liệu để giảm chi phí mở kết nối và xác thực cho mỗi request. Ứng dụng thường mượn một connection trong thời gian ngắn, thực hiện truy vấn rồi gọi `close()` để trả nó về pool. Trong môi trường pool, `close()` thường đóng handle logic mà ứng dụng đang cầm; kết nối vật lý có thể vẫn tồn tại để request tiếp theo sử dụng.

Việc tái sử dụng này tạo ra một yêu cầu quan trọng: trạng thái của session phải được làm sạch trước khi giao cho người mượn tiếp theo. Nếu request A tắt autocommit, đổi isolation level hoặc thiết lập biến session rồi trả connection mà không khôi phục, request B có thể nhận một session mang cấu hình của A. Hậu quả có thể là transaction bị mở ngoài ý muốn, khóa bị giữ lâu, dữ liệu đọc theo mức cô lập không mong đợi hoặc thậm chí lộ dữ liệu giữa các tenant nếu schema/role cũng bị rò.

Để dùng pool an toàn, hãy quản lý transaction bằng cấu trúc commit/rollback rõ ràng, khôi phục các thuộc tính connection về cấu hình chuẩn, hiểu giới hạn reset của pool và loại bỏ connection khi không thể xác nhận trạng thái sạch.

## 1. Connection logic và kết nối vật lý

Không có pool, một request thường tạo kết nối vật lý, dùng nó rồi đóng hẳn:

```text
Request A                         Database
   |                                  |
   |------ open physical connection ->|
   |<------------- session A ---------|
   |                                  |
   |------ SQL / COMMIT ------------->|
   |------ close physical session --->|
```

Với connection pool, vòng đời khác:

```text
Request A             Pool                 Database
   |                    |                      |
   |-- borrow() ------->|                      |
   |<-- logical handle -|-- reuse session --->|
   |                    |                      |
   |-- SQL / COMMIT -------------------------->|
   |-- close() -------->|                      |
   |                    | giữ physical session |
   |                    |                      |
Request B              |                      |
   |-- borrow() ------->|                      |
   |<-- logical handle -|-- cùng session ----->|
```

Ứng dụng sở hữu handle trong thời gian mượn. Pool sở hữu vòng đời kết nối vật lý và quyết định khi nào tạo mới, kiểm tra, tái sử dụng hoặc hủy nó. Vì thế, `Connection.close()` trong một pool thường có nghĩa “trả connection”, không nhất thiết là “đóng session database ngay lập tức”.

Một connection vật lý thường gắn với một session database. Session có thể giữ nhiều trạng thái ngoài dữ liệu đã commit, chẳng hạn autocommit, isolation level, schema hiện tại, role, biến session, temporary table, timezone, lock hoặc transaction đang mở. Tái sử dụng session mà không reset các trạng thái liên quan có thể làm request sau nhận được môi trường khác với cấu hình mà nó mong đợi.

## 2. Những trạng thái có thể bị rò giữa hai request

Các thuộc tính thường gặp:

| Trạng thái | Rủi ro nếu bị rò |
|---|---|
| `autoCommit` | Request sau có thể vô tình chạy nhiều câu lệnh trong một transaction hoặc mỗi câu lệnh tự commit ngoài dự kiến. |
| Transaction isolation | Request sau đọc dữ liệu với mức cô lập khác cấu hình của ứng dụng, làm thay đổi khả năng quan sát và xung đột. |
| `readOnly` | Request cần ghi có thể bị từ chối hoặc driver/database xử lý theo chế độ chỉ đọc. |
| Catalog/schema/search path | Truy vấn không định danh đầy đủ có thể đọc hoặc ghi nhầm schema. |
| Role, tenant hoặc security context | Request sau có thể chạy với quyền hoặc phạm vi dữ liệu của request trước. |
| Session variables và `SET` options | Câu SQL có thể nhận hành vi khác, ví dụ timezone, locale, isolation hoặc cấu hình riêng của engine. |
| Temporary tables | Dữ liệu tạm từ request trước có thể còn tồn tại trong session và ảnh hưởng request sau. |
| Session-level advisory lock | Khóa có thể còn được giữ sau khi transaction kết thúc nếu không được nhả đúng cách. |
| Network timeout, schema, catalog hoặc client info | Request sau có thể kế thừa timeout hoặc metadata không mong muốn. |

Không phải mọi thuộc tính đều được quản lý bằng cùng một API. JDBC có các setter cho một số trạng thái như autocommit, isolation, read-only, catalog và schema; các lệnh SQL riêng của DBMS có thể thay đổi trạng thái session khác. Pool có thể reset một số thuộc tính JDBC phổ biến nhưng không nhất thiết hiểu mọi câu `SET` tùy biến mà ứng dụng đã chạy.

## 3. Rò `autoCommit` có thể gây ra điều gì?

Trong JDBC, connection mới thường ở chế độ autocommit theo mặc định, nhưng pool có thể được cấu hình baseline khác. Khi `autoCommit = true`, mỗi câu lệnh được commit tự động khi hoàn tất theo ngữ nghĩa JDBC. Khi `autoCommit = false`, ứng dụng phải kết thúc transaction bằng `commit()` hoặc `rollback()`.

Giả sử request A tắt autocommit để thực hiện hai cập nhật:

```java
Connection connection = dataSource.getConnection();
connection.setAutoCommit(false);

try {
    updateAccountA(connection);
    updateAccountB(connection);
    connection.commit();
} finally {
    connection.close();
}
```

Đoạn code có vấn đề nếu một exception xảy ra trước `commit()`: nó không rollback tường minh. Nếu pool không xử lý được trạng thái transaction đó hoặc connection không được reset đúng cách, request tiếp theo có thể nhận connection còn transaction mở, giữ khóa và chứa thay đổi chưa commit.

Một lỗi khác là request A thay đổi autocommit rồi trả connection mà không khôi phục. Request B có thể tưởng mỗi câu lệnh đang tự commit, trong khi thực tế connection vẫn ở `autoCommit = false`. Nếu B không gọi commit, các thay đổi của nó có thể bị rollback khi pool dọn dẹp hoặc bị giữ lại cùng transaction lâu hơn dự kiến.

Điểm cần nhớ: tắt autocommit là thay đổi trạng thái của connection/session. Hãy luôn kết thúc transaction hiện tại và khôi phục cấu hình trước khi trả connection.

## 4. Rò isolation level thay đổi cách request sau đọc dữ liệu

JDBC cho phép đặt isolation level qua `Connection.setTransactionIsolation(...)`. Ví dụ:

```java
connection.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE);
```

Nếu request A đặt `SERIALIZABLE` để bảo vệ một quy trình nhạy cảm nhưng không khôi phục baseline, request B có thể vô tình chạy ở mức này. Điều đó có thể làm tăng chờ khóa, serialization failure và retry. Ngược lại, nếu A hạ isolation level xuống `READ UNCOMMITTED` hoặc một mức yếu hơn rồi để lại, request B có thể không nhận được bảo đảm mà nó dựa vào.

Isolation level thường là trạng thái của connection/session hoặc transaction tùy DBMS và driver. Thời điểm thay đổi có hiệu lực cũng phụ thuộc sản phẩm. Một số hệ thống chỉ áp dụng mức mới cho transaction tiếp theo; gọi setter giữa transaction có thể bị từ chối hoặc có hành vi được định nghĩa riêng. Vì vậy:

- Đặt isolation level trước khi bắt đầu transaction mà nó cần áp dụng.
- Không đổi isolation level giữa một transaction đang chạy trừ khi tài liệu DBMS xác nhận rõ hành vi.
- Khôi phục mức chuẩn trước khi trả connection.
- Kiểm tra mức thực tế trên server khi điều tra lỗi, không chỉ dựa vào giá trị cấu hình trong code.

Một request bị rò `SERIALIZABLE` có thể khiến các request sau chờ hoặc bị hủy do xung đột. Một request bị rò mức thấp hơn có thể khiến ứng dụng quan sát trạng thái không phù hợp với giả định nghiệp vụ. Cả hai đều là lỗi tính đúng đắn và vận hành.

## 5. Pool reset những gì và giới hạn ở đâu?

Các pool JDBC phổ biến thường theo dõi hoặc khôi phục một số thuộc tính connection mà JDBC định nghĩa, ví dụ autocommit, isolation, read-only, catalog, schema hoặc network timeout, tùy sản phẩm và cấu hình. Một số pool còn rollback transaction chưa hoàn tất khi connection được trả về.

Tuy nhiên, không nên giả định mọi pool đều reset mọi trạng thái session. Ví dụ:

- `SET search_path`, `SET ROLE`, biến session hoặc `SET` option riêng của DBMS có thể không được pool nhận biết.
- Temporary table có thể tồn tại đến khi session kết thúc hoặc được xóa theo quy tắc riêng.
- Session-level advisory lock có thể tồn tại sau khi transaction kết thúc.
- Prepared statement, cursor hoặc resource đặc thù có thể có vòng đời riêng.
- Stored procedure có thể thay đổi trạng thái session như một tác dụng phụ.

Một lệnh khởi tạo connection như `connectionInitSql` thường chạy khi tạo physical connection, không nhất thiết chạy lại mỗi lần borrower nhận connection. Nếu ứng dụng thay đổi session state trong mỗi request, cần reset tương ứng khi trả connection hoặc thiết kế thao tác thay đổi có phạm vi tự kết thúc.

Đọc tài liệu của pool để biết rõ:

1. Thuộc tính JDBC nào được theo dõi và khôi phục.
2. Pool có rollback transaction chưa hoàn tất khi trả connection không.
3. Khi reset thất bại, connection được trả về pool hay bị loại bỏ.
4. Có hook reset-on-return hoặc custom connection initializer không.
5. Cấu hình baseline nào được áp dụng cho connection mới và connection đã tái sử dụng.

Không dùng reset tự động của pool làm lý do bỏ qua cleanup trong code ứng dụng. Ứng dụng vẫn phải đóng transaction đúng cách và không để connection ở trạng thái chưa xác định.

## 6. Mẫu quản lý transaction an toàn trong JDBC

Với transaction do ứng dụng tự quản lý, cấu trúc cơ bản là:

```java
try (Connection connection = dataSource.getConnection()) {
    try {
        connection.setAutoCommit(false);

        updateAccountA(connection);
        updateAccountB(connection);

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
```

Ví dụ này minh họa nguyên tắc rollback khi lỗi và luôn đóng logical handle. Trong code production, nếu rollback thất bại hoặc trạng thái protocol không còn tin cậy, ứng dụng cần yêu cầu pool loại bỏ physical connection theo API cụ thể của pool. Chỉ gọi `close()` không phải lúc nào cũng đủ để chứng minh connection lỗi đã bị loại bỏ.

Một helper transaction hoàn chỉnh cần quản lý cả cấu hình ban đầu và cleanup. Ví dụ khái niệm:

```text
connection = pool.borrow()
baseline = expectedPoolConfiguration
reusable = true

try:
    verifyOrNormalizeConnectionToBaseline(connection, baseline)

    set required isolation before transaction
    set autoCommit = false

    try:
        execute all database work
        commit
    catch error:
        try rollback
        catch rollbackError:
            reusable = false
            attach rollbackError to error
        raise error

finally:
    if reusable:
        reset JDBC and DBMS session state to baseline
        if reset fails:
            reusable = false

    if reusable:
        close logical handle and return to pool
    else:
        evict/discard physical connection using pool-specific API
```

Điểm quan trọng là không khôi phục autocommit bằng cách đơn giản gọi `setAutoCommit(true)` khi transaction còn mở. Theo JDBC, đổi autocommit từ `false` sang `true` khi đang ở giữa transaction có thể commit transaction hiện tại. Hãy rollback trước nếu cần hủy, xác nhận transaction đã kết thúc, rồi mới khôi phục autocommit. Nếu rollback không thành công, không tiếp tục reset như thể connection sạch.

## 7. Khôi phục isolation level và các thuộc tính JDBC

Nếu ứng dụng tạm thời thay đổi thuộc tính, cần biết baseline chuẩn để khôi phục. Một cách đơn giản là lưu giá trị trước khi thay đổi:

```java
int previousIsolation = connection.getTransactionIsolation();
boolean previousReadOnly = connection.isReadOnly();
boolean previousAutoCommit = connection.getAutoCommit();
boolean transactionFinished = false;
boolean reusable = true;
boolean commitAttempted = false;

try {
    // Các thay đổi thuộc tính cần thực hiện ngoài transaction.
    connection.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ);
    connection.setReadOnly(false);
    connection.setAutoCommit(false);

    runWork(connection);
    commitAttempted = true;
    connection.commit();
    transactionFinished = true;
} catch (SQLException | RuntimeException error) {
    if (commitAttempted && isCommitOutcomeUnknown(error)) {
        reusable = false;
        // Không thể suy ra commit đã thất bại; cần đối soát bằng operation ID.
    } else {
        try {
            connection.rollback();
            transactionFinished = true;
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
            reusable = false;
        }
    }
    throw error;
} finally {
    // Chỉ reset khi transaction đã kết thúc được xác nhận.
    if (reusable && transactionFinished) {
        try {
            connection.setAutoCommit(previousAutoCommit);
            connection.setReadOnly(previousReadOnly);
            connection.setTransactionIsolation(previousIsolation);
        } catch (SQLException resetError) {
            reusable = false;
            // Ghi nhận lỗi cleanup và loại connection khỏi pool.
        }
    }

    if (reusable) {
        connection.close(); // Trả logical handle về pool.
    } else {
        // Gọi API evict/invalidate của pool; không tái sử dụng session này.
        evictFromPool(connection);
    }
}
```

Đây là ví dụ minh họa; `evictFromPool` và `isCommitOutcomeUnknown` là placeholder cần triển khai theo API của pool, driver và DBMS. Nếu kết nối mất trong lúc commit, không được giả định rollback sau đó sẽ chứng minh commit thất bại: kết quả có thể chưa xác định và cần đối soát bằng operation ID/idempotency key trên connection mới. Nếu rollback thất bại, transaction cũng chưa được xác nhận kết thúc và connection không được reset như thể nó sạch. Ngoài ra, lưu giá trị trước chỉ an toàn nếu pool bảo đảm connection được giao ra ở baseline đáng tin cậy. Nếu trạng thái có thể đã bị rò từ borrower trước, việc lưu rồi khôi phục sẽ chỉ bảo tồn trạng thái sai. Một thiết kế tốt cần pool reset về baseline cấu hình và/hoặc kiểm tra baseline khi mượn.

Thứ tự cleanup cũng quan trọng:

1. Kết thúc transaction bằng commit hoặc rollback.
2. Chỉ sau khi transaction đã kết thúc mới khôi phục autocommit, isolation và read-only theo quy tắc của driver/DBMS.
3. Khôi phục catalog/schema hoặc trạng thái session tùy biến.
4. Nếu bất kỳ bước cleanup nào thất bại, loại connection khỏi pool.

Không để lỗi trong `finally` che mất exception ban đầu. Hãy lưu lỗi cleanup dưới dạng suppressed exception hoặc ghi log có liên kết với operation ID.

## 8. Trạng thái session tùy biến và an toàn tenant

Một số ứng dụng dùng cùng database/schema cho nhiều tenant và thiết lập tenant context trong session:

```sql
SET app.current_tenant = 'tenant_42';
```

Hoặc thay đổi schema/role/search path trước khi truy vấn. Nếu trạng thái đó còn tồn tại khi connection trả về pool, request của tenant khác có thể vô tình chạy trong context cũ.

Đây là rủi ro bảo mật và phân tách dữ liệu. Không nên dựa vào việc “request nào cũng sẽ set lại tenant” nếu có nhánh code quên thiết lập hoặc query chạy trước bước thiết lập. Cần:

- Đặt tenant context ở một điểm bắt buộc trước mọi truy vấn dữ liệu.
- Reset context trong cùng lifecycle của connection, kể cả khi exception hoặc cancellation xảy ra.
- Ưu tiên cơ chế có phạm vi transaction như `SET LOCAL` trong PostgreSQL khi phù hợp, vì trạng thái được giới hạn trong transaction và tự hết hiệu lực khi transaction kết thúc.
- Không coi `SET LOCAL` hay cơ chế tương tự là portable; kiểm tra DBMS cụ thể.
- Dùng row-level security hoặc quyền database phù hợp làm lớp bảo vệ bổ sung nếu mô hình yêu cầu.
- Kiểm thử việc tái sử dụng cùng physical connection giữa hai tenant khác nhau.

Nếu session context được dùng để quyết định quyền truy cập, reset thất bại phải khiến connection bị loại bỏ. Không được trả nó về pool trong trạng thái không rõ tenant hoặc role.

## 9. `SET SESSION`, `SET LOCAL` và phạm vi tồn tại

Các DBMS có nhiều cách đặt cấu hình ở phạm vi khác nhau. Ví dụ trong PostgreSQL:

- `SET` thay đổi tham số cho session và có thể tồn tại qua nhiều transaction trên cùng connection.
- `SET LOCAL` giới hạn thay đổi đến transaction hiện tại; thay đổi tự hết hiệu lực khi transaction kết thúc.
- `SET` thực hiện bên trong transaction có thể được hoàn tác cùng transaction nếu transaction rollback, theo quy tắc của PostgreSQL.

Trong MySQL, `SET SESSION` thay đổi biến cho session hiện tại; `SET GLOBAL` ảnh hưởng mặc định hoặc trạng thái toàn server tùy biến và quyền. Không dùng `SET GLOBAL` như cách thiết lập cho một request.

SQL Server có nhiều `SET` option gắn với session, và Oracle có các lệnh `ALTER SESSION`. Các lệnh này không có cùng cú pháp hoặc phạm vi với PostgreSQL. Hãy phân biệt rõ cấu hình cấp server, cấp session và cấp transaction trước khi dùng trong code có connection pooling.

Nếu chỉ cần một thiết lập tạm thời cho một transaction, ưu tiên API JDBC hoặc cú pháp transaction-scoped mà DBMS hỗ trợ. Tránh thay đổi session kéo dài nếu không có reset đáng tin cậy.

## 10. Connection pool phải làm gì khi borrower trả connection?

Một lifecycle tốt thường gồm các bước:

1. Borrower kết thúc transaction hiện tại bằng commit hoặc rollback.
2. Borrower đóng statement, result set và các resource liên quan.
3. Borrower khôi phục những thuộc tính session mà mình đã thay đổi.
4. Pool kiểm tra transaction chưa hoàn tất và thực hiện cleanup theo chính sách.
5. Pool reset các thuộc tính JDBC mà nó theo dõi.
6. Pool kiểm tra connection còn hợp lệ và không có lỗi protocol.
7. Pool trả connection vật lý về danh sách idle hoặc loại bỏ nó nếu cleanup/validation thất bại.

Pool có thể thực hiện một số bước tự động, nhưng chi tiết khác nhau theo thư viện. Đừng giả định thứ tự hoặc danh sách thuộc tính reset nếu chưa đọc tài liệu và cấu hình thực tế.

Một số pool có leak detection để cảnh báo connection được mượn quá lâu. Leak detection giúp phát hiện quên đóng handle, nhưng không nhất thiết phát hiện trạng thái session bị thay đổi rồi trả về đúng thời hạn. State leak cần kiểm thử riêng.

## 11. Validation không đồng nghĩa reset

Pool có thể kiểm tra connection còn sống bằng `Connection.isValid(timeout)` hoặc một validation query. Việc này xác nhận khả năng giao tiếp với database ở mức nhất định, không chứng minh connection sạch.

Ví dụ, `SELECT 1` có thể thành công dù connection vẫn ở `autoCommit = false`, isolation level đã bị đổi hoặc session đang giữ một biến tenant cũ. Vì vậy cần phân biệt:

- **Validation:** connection có còn hoạt động và dùng được không?
- **Reset:** connection có trở về trạng thái chuẩn mong đợi không?
- **Transaction cleanup:** transaction trước đã commit/rollback và không còn giữ tài nguyên không?

Ba việc này bổ sung cho nhau. Một connection có thể sống nhưng bẩn; cũng có thể đã reset nhưng không còn kết nối được.

## 12. Khi nào phải loại bỏ connection khỏi pool?

Nếu connection không thể được đưa về trạng thái đã biết, không nên tái sử dụng nó. Những trường hợp thường cần evict/discard:

- `rollback()` thất bại hoặc mất kết nối trong lúc rollback.
- Mất kết nối trong lúc commit khiến kết quả chưa xác định và session không còn dùng được.
- Lệnh reset session state thất bại.
- Driver báo connection hoặc protocol ở trạng thái lỗi.
- Không xác định được transaction cũ đã kết thúc hay chưa.
- Cancel/timeout làm session không còn đáp ứng hoặc không thể xác nhận câu lệnh đã dừng.

Trong JDBC thuần, `Connection.close()` không cung cấp một API portable để yêu cầu mọi pool loại bỏ physical connection. Một số pool có API riêng để evict hoặc invalidate connection. JDBC cũng có `Connection.abort(Executor)`, nhưng cách tích hợp với proxy của pool và chính sách discard phụ thuộc thư viện. Hãy dùng cơ chế được pool hỗ trợ; không tự ý unwrap physical connection nếu thư viện không cho phép.

Nếu cleanup chỉ thất bại ở một thuộc tính tùy biến, connection vẫn có thể hoạt động về mặt mạng nhưng không an toàn về trạng thái. Hãy coi reset failure là lỗi connection và loại nó khỏi pool.

## 13. Không thay đổi connection do framework quản lý transaction

Trong ứng dụng dùng Spring transaction manager, JTA hoặc một framework quản lý transaction khác, connection có thể được bind vào transaction context. Code nghiệp vụ không nên tự ý gọi `commit()`, `rollback()` hoặc thay đổi autocommit/isolation trên connection do framework quản lý.

Thay vào đó, hãy khai báo ranh giới transaction qua cơ chế của framework, ví dụ annotation hoặc transaction template, và để transaction manager quản lý connection. Nếu cần isolation level riêng, cấu hình ở transaction boundary theo API framework hỗ trợ.

Việc tự thay đổi trạng thái connection bên trong transaction được framework quản lý có thể làm lệch nhận thức giữa framework và database, dẫn đến commit sớm, rollback sai hoặc connection không được đồng bộ đúng cách. Chỉ truy cập connection trực tiếp khi framework cho phép và tuân thủ đúng lifecycle của nó.

## 14. Kiểm thử rò trạng thái bằng cách tái sử dụng cùng connection

Kiểm thử cần ép pool tái sử dụng cùng một physical connection để phát hiện state leak. Có thể cấu hình pool test với `maximumPoolSize = 1` và tuần tự hóa hai borrower.

### Kịch bản autocommit

1. Borrower A lấy connection và xác nhận baseline `autoCommit`.
2. A gọi `setAutoCommit(false)`, thực hiện cập nhật rồi rollback.
3. A trả connection.
4. Borrower B lấy connection tiếp theo.
5. B xác nhận `getAutoCommit()` bằng baseline được cấu hình.
6. B thực hiện một cập nhật thử và xác nhận transaction có hành vi commit mong đợi.

### Kịch bản isolation

1. A đổi isolation sang `SERIALIZABLE` và kết thúc transaction.
2. A trả connection.
3. B lấy lại cùng physical connection.
4. B xác nhận isolation trở về baseline, ví dụ `READ_COMMITTED` nếu đó là cấu hình ứng dụng.

### Kịch bản session state

1. A đặt schema, role, tenant context hoặc biến session riêng.
2. A trả connection trong cả trường hợp thành công và exception.
3. B lấy connection và xác nhận không còn trạng thái của A.
4. Lặp lại khi A bị timeout, cancel hoặc rollback thất bại để xác nhận connection được discard nếu không thể reset.

Không chỉ kiểm tra giá trị getter JDBC. Với trạng thái DBMS-specific, hãy chạy truy vấn xác nhận trên server hoặc kiểm tra context thực tế mà truy vấn sử dụng. Cần xác nhận pool thực sự đưa lại cùng physical connection trong bài test, nếu không test có thể vô tình dùng một session mới và bỏ sót lỗi.

## 15. Theo dõi pool và trạng thái connection

Các chỉ số vận hành giúp phân biệt pool cạn connection với state leak:

| Chỉ số | Điều cần quan sát |
|---|---|
| Active connections | Số connection đang được borrower giữ. |
| Idle connections | Số connection sẵn sàng được mượn. |
| Pending borrowers | Số request đang chờ connection. |
| Acquisition time | Thời gian lấy connection từ pool. |
| Usage duration | Thời gian một borrower giữ connection. |
| Validation failures | Số connection không vượt qua kiểm tra sống. |
| Reset/eviction failures | Số lần reset thất bại hoặc connection bị loại. |
| Transaction age | Tuổi transaction đang mở nếu DBMS cung cấp. |
| Lock waits | Thời gian chờ khóa có liên quan đến session của ứng dụng. |

Connection bị giữ quá lâu có thể là connection leak ở tầng ứng dụng. Connection được trả nhưng còn transaction hoặc session state cũ là state leak. Hai vấn đề có thể cùng xuất hiện nhưng cần điều tra khác nhau.

Khi điều tra, liên kết log ứng dụng với connection/session ID, request ID và transaction boundary. Không ghi thông tin nhạy cảm như token xác thực hoặc payload tenant vào log chỉ để chẩn đoán trạng thái session.

## 16. Quy trình thiết kế an toàn cho ứng dụng dùng pool

1. Xác định baseline connection: autocommit, isolation, read-only, schema/catalog, role và các session setting bắt buộc.
2. Quyết định lớp nào sở hữu transaction: code JDBC, framework transaction manager hay container.
3. Đặt isolation và các thuộc tính cần thiết trước khi bắt đầu transaction.
4. Giữ transaction ngắn; không thực hiện I/O bên ngoài trong lúc giữ khóa.
5. Commit khi thành công; rollback khi lỗi hoặc cancellation nếu transaction chưa commit.
6. Đóng statement/result set và khôi phục trạng thái tùy biến.
7. Đảm bảo pool reset về baseline và loại connection khi rollback/reset/validation thất bại.
8. Kiểm thử hai borrower liên tiếp trên cùng physical connection, bao gồm exception, timeout và cancel.
9. Theo dõi transaction age, lock wait, pool acquisition, reset failure và connection eviction.
10. Đọc tài liệu đúng pool, JDBC driver và DBMS; không dựa vào giả định reset chung cho mọi sản phẩm.

## 17. Checklist trước khi đưa connection pool vào production

- [ ] Mỗi borrower đóng logical connection trong mọi nhánh code, kể cả exception.
- [ ] Transaction được commit hoặc rollback tường minh trước khi trả connection.
- [ ] `autoCommit` được khôi phục về baseline chuẩn sau transaction.
- [ ] Isolation level được đặt trước transaction và reset về baseline.
- [ ] Read-only, schema, catalog, role và session variables được quản lý rõ ràng.
- [ ] Các lệnh `SET SESSION` được reset; thiết lập transaction-scoped được ưu tiên khi phù hợp.
- [ ] Không gọi `setAutoCommit(true)` để thay cho rollback khi transaction còn mở.
- [ ] Rollback/reset thất bại dẫn đến loại connection khỏi pool.
- [ ] Hiểu rõ `close()` trả connection về pool hay đóng physical session.
- [ ] Validation được phân biệt với reset và transaction cleanup.
- [ ] Framework transaction manager sở hữu connection thì code không tự commit/rollback.
- [ ] Đã kiểm thử trạng thái giữa hai borrower trên cùng physical connection.
- [ ] Đã kiểm tra cancellation, timeout, mất kết nối và kết quả commit chưa xác định.
- [ ] Có metrics cho active/idle/pending, acquisition time, transaction age, lock wait và eviction.

Connection pool giúp tái sử dụng session, nhưng cũng khiến trạng thái session sống lâu hơn một request. Vì vậy, autocommit, isolation level và các thiết lập session phải được xem như tài nguyên có lifecycle: đặt trước khi dùng, kết thúc transaction, reset về baseline và loại connection nếu không thể xác nhận trạng thái sạch. Chỉ khi đó request tiếp theo mới nhận được một connection có hành vi đúng như cấu hình mà ứng dụng mong đợi.
