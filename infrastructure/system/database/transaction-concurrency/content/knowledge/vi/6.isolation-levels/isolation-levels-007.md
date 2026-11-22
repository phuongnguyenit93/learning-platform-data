# Mức mặc định không thay thế việc đọc tài liệu của hệ quản trị đang dùng

Khi một ứng dụng mở transaction mà không khai báo isolation level, rất dễ nghĩ rằng database sẽ luôn dùng một mức mặc định quen thuộc như `READ COMMITTED` hoặc `REPEATABLE READ`. Cách nghĩ đó chưa đủ an toàn. **Isolation mặc định phụ thuộc hệ quản trị, phiên bản, cấu hình database/session, driver và cách framework quản lý transaction.** Ngay cả khi hai DBMS cùng báo `REPEATABLE READ`, cách chúng tạo snapshot, xử lý khóa, phantom và xung đột ghi vẫn có thể khác nhau.

Vì vậy, khi thiết kế hoặc điều tra một lỗi đồng thời, không thể chỉ dựa vào tên mức cô lập trong code, một giá trị cấu hình cũ hay kiến thức về DBMS khác. Cần xác định database thực tế, đọc tài liệu đúng phiên bản, kiểm tra cấu hình có hiệu lực trên connection đang chạy và xác minh hành vi phù hợp với bất biến nghiệp vụ.

## 1. Isolation level mặc định là gì?

Isolation level quy định cách một transaction quan sát và tương tác với thay đổi do các transaction khác tạo ra. Nó là một phần của hợp đồng đồng thời giữa ứng dụng và hệ quản trị cơ sở dữ liệu.

**Isolation level mặc định** là mức cô lập được hệ quản trị áp dụng khi một transaction không yêu cầu mức khác trong phạm vi cấu hình có hiệu lực. Mức được áp dụng có thể chịu ảnh hưởng của:

- Mặc định tích hợp trong DBMS hoặc phiên bản đang chạy.
- Thiết lập ở cấp database, server, session hoặc connection.
- Lệnh cấu hình do ứng dụng gửi khi mở hoặc bắt đầu transaction.
- Connection pool tái sử dụng session và trạng thái transaction còn sót lại.
- Framework/transaction manager chỉ định isolation cụ thể hoặc dùng giá trị `DEFAULT` để kế thừa từ resource.
- Driver và cách tích hợp truyền thuộc tính transaction xuống server.

Không có một quy tắc rằng tất cả database đều phải chọn `READ COMMITTED`, hay tất cả ứng dụng Java đều có cùng isolation chỉ vì chúng dùng JDBC hoặc Spring.

### Cần phân biệt ba khái niệm

| Khái niệm | Ý nghĩa | Ví dụ câu hỏi cần trả lời |
| --- | --- | --- |
| **DBMS default** | Mức mặc định do engine/configuration quy định khi không có override | Database này mặc định dùng mức nào? |
| **Session/connection setting** | Mức hiện hành của kết nối đang thực thi | Connection trong pool hiện đang dùng mức nào? |
| **Transaction isolation thực tế** | Mức áp dụng cho transaction cụ thể, sau khi xét lệnh và framework | Transaction đang chạy thực tế có snapshot semantics nào? |

Ba giá trị có thể giống nhau, nhưng không nên mặc định là vậy. Ví dụ một database có default `READ COMMITTED`, session được cấu hình `REPEATABLE READ`, còn một transaction cụ thể có thể đặt `SERIALIZABLE`. Khi kết thúc transaction, hành vi khôi phục session setting cũng phụ thuộc cách DBMS và driver quản lý.

## 2. Vì sao một mức mặc định không đủ làm căn cứ thiết kế?

Isolation level có tên chuẩn hóa, nhưng cách triển khai giữa các DBMS có thể khác. Tên mức là điểm bắt đầu để đọc tài liệu, không phải bằng chứng đầy đủ về các lịch giao dịch được phép.

Ví dụ cùng tên `REPEATABLE READ` có thể được triển khai bằng khóa, snapshot isolation hoặc cơ chế kết hợp. Các câu hỏi sau cần được trả lời theo tài liệu của engine:

- Hai lần `SELECT` cùng một hàng trong một transaction có cùng thấy một phiên bản không?
- Một transaction có thể nhìn thấy hàng mới được insert thỏa predicate sau lần đọc đầu tiên không?
- Một truy vấn đọc có giữ khóa đến commit hay dùng snapshot không khóa?
- Hai transaction ghi những hàng khác nhau nhưng cùng vi phạm bất biến tổng hợp có thể cùng commit không?
- Khi một transaction cập nhật hàng mà transaction khác đã sửa, engine chờ, đọc lại điều kiện, báo lỗi hay abort transaction?
- Isolation có áp dụng cho locking reads, nonlocking reads, DDL, sequence hoặc truy vấn qua replica theo cùng cách không?

Chỉ biết default level sẽ không trả lời hết các câu hỏi trên.

### Tên isolation không đồng nghĩa một thuật toán duy nhất

Ví dụ, PostgreSQL triển khai `REPEATABLE READ` dựa trên snapshot isolation. Các truy vấn thông thường trong cùng transaction dùng một snapshot nhất quán, nhưng write skew vẫn có thể xảy ra nếu hai giao dịch cập nhật các hàng khác nhau dựa trên cùng một điều kiện tổng hợp. `SERIALIZABLE` của PostgreSQL bổ sung cơ chế phát hiện phụ thuộc để bảo đảm kết quả tương đương tuần tự và có thể hủy transaction cần retry.

MySQL/InnoDB có locking reads, consistent nonlocking reads, undo versions và quy tắc next-key/gap locking riêng. `REPEATABLE READ` của InnoDB thường là mặc định trong nhiều bản cài đặt, nhưng hành vi của plain `SELECT` khác locking read (`SELECT ... FOR UPDATE` hoặc `FOR SHARE`).

SQL Server có các lựa chọn dựa trên locking hoặc row versioning; `READ COMMITTED` có thể sử dụng locking hay row-versioned reads tùy cấu hình `READ_COMMITTED_SNAPSHOT`. `SNAPSHOT` isolation còn cần được bật ở database trước khi transaction có thể sử dụng.

Oracle Database sử dụng mô hình consistent read và mặc định transaction isolation thường là `READ COMMITTED`; `SERIALIZABLE` và read-only transaction có semantics riêng. Không nên đem thuật ngữ hoặc lệnh của PostgreSQL áp nguyên xi sang Oracle.

Những khác biệt này cho thấy cùng một nhãn không bảo đảm cùng một hành vi thực tế. Hãy đọc phần transaction isolation, concurrency control, locking, row versioning và recovery trong tài liệu đúng DBMS/version.

## 3. Ví dụ default khác nhau giữa các hệ quản trị

Bảng này là định hướng tổng quan cho các hệ quản trị quan hệ phổ biến. Mặc định có thể được thay đổi bởi cấu hình, phiên bản, dịch vụ managed hoặc cách ứng dụng bắt đầu transaction; luôn xác nhận trên môi trường đang chạy.

| Hệ quản trị | Mức mặc định thường gặp | Điểm cần kiểm tra trong tài liệu |
| --- | --- | --- |
| **PostgreSQL** | `READ COMMITTED` | Mỗi câu lệnh thường lấy snapshot mới; `REPEATABLE READ` dùng snapshot transaction; `READ UNCOMMITTED` được xử lý như `READ COMMITTED`. |
| **MySQL / InnoDB** | `REPEATABLE READ` trong cấu hình InnoDB phổ biến | Phân biệt consistent read với locking read; kiểm tra `transaction_isolation`, engine của bảng và gap/next-key locking. |
| **SQL Server** | `READ COMMITTED` | Kiểm tra `READ_COMMITTED_SNAPSHOT`, `ALLOW_SNAPSHOT_ISOLATION` và session isolation. |
| **Oracle Database** | `READ COMMITTED` | Hiểu statement-level consistent read, transaction-level `SERIALIZABLE` và read-only transaction. |
| **SQLite** | Không nên ánh xạ đơn giản vào cùng ma trận isolation của server DBMS | Đọc chế độ journal/WAL, transaction mode và hành vi locking/snapshot của phiên bản SQLite. |

Không dùng bảng tổng quan này làm cấu hình triển khai. Hãy coi nó là danh sách câu hỏi ban đầu để mở tài liệu chính thức và xác nhận giá trị đang có hiệu lực.

## 4. Mặc định có thể bị override ở nhiều cấp

Isolation mặc định không nhất thiết là một hằng số duy nhất bất biến. Một hệ thống có thể thay đổi nó ở các cấp khác nhau.

### Cấp server/database

DBA hoặc cấu hình triển khai có thể đặt hành vi mặc định cho các kết nối mới hoặc một database cụ thể. Một số cài đặt chỉ bật/tắt khả năng sử dụng isolation nhất định chứ không thay đổi default level. Ví dụ SQL Server yêu cầu bật `ALLOW_SNAPSHOT_ISOLATION` trước khi session chọn `SNAPSHOT`; đây không đồng nghĩa server tự chuyển toàn bộ transaction sang snapshot.

### Cấp session/connection

Một connection có thể thay đổi mức cô lập bằng câu lệnh của DBMS hoặc API JDBC. Thiết lập có thể tồn tại đến cuối session nếu không được reset. Trong connection pool, một connection vật lý được tái sử dụng bởi nhiều request; nếu trạng thái session bị rò rỉ từ request trước, request sau có thể chạy với isolation ngoài dự kiến.

### Cấp transaction

Một transaction có thể chỉ định mức riêng nếu DBMS cho phép. Trong PostgreSQL, `SET TRANSACTION ISOLATION LEVEL ...` cần được thiết lập trước truy vấn/statement có tác động đến transaction. Các DBMS khác có quy tắc thời điểm và cú pháp riêng.

### Cấp framework

Spring `@Transactional` có thuộc tính `isolation`. Giá trị `Isolation.DEFAULT` yêu cầu dùng isolation mặc định của datastore/connection. Nếu khai báo cụ thể, transaction manager sẽ cố thiết lập mức đó theo khả năng của resource. Framework không thể tạo ra một semantics mà DBMS không hỗ trợ.

Ví dụ:

~~~java
@Transactional
public OrderSummary loadSummary(long orderId) {
    // Không khai báo isolation: framework dùng DEFAULT.
    // Cần xác minh default của connection/DBMS thực tế.
    return repository.loadSummary(orderId);
}

@Transactional(isolation = Isolation.REPEATABLE_READ, readOnly = true)
public AuditReport loadConsistentReport(long reportId) {
    // Yêu cầu transaction manager đặt mức REPEATABLE_READ.
    // Hành vi thực tế vẫn phụ thuộc DBMS và transaction context.
    return reportRepository.load(reportId);
}
~~~

Annotation trên không tự chứng minh transaction đã được tạo mới. Nếu phương thức tham gia một transaction bên ngoài theo propagation, thuộc tính của transaction đang tồn tại và cách transaction manager xử lý override mới quyết định kết quả. Với Spring proxy thông dụng, self-invocation cũng có thể khiến lời gọi không đi qua proxy nên annotation không được áp dụng như mong đợi.

## 5. Xác định DBMS và phiên bản trước khi đọc tài liệu

Trước khi đọc phần isolation, cần biết chính xác hệ thống đang kết nối tới đâu. Một cấu hình local có thể khác staging, production hoặc database managed. Driver cũng có thể kết nối tới proxy, cluster endpoint hay replica chứ không phải instance mà developer nghĩ đang dùng.

Thông tin cần xác minh:

1. Tên engine và edition/service (PostgreSQL, MySQL, SQL Server, Oracle, SQLite hoặc dịch vụ tương thích).
2. Phiên bản server chính xác, không chỉ phiên bản driver.
3. Storage engine của các bảng liên quan, ví dụ InnoDB trong MySQL.
4. Database-level settings ảnh hưởng isolation hoặc row versioning.
5. Connection/session settings tại thời điểm request chạy.
6. Transaction manager, propagation và isolation cấu hình trong ứng dụng.
7. Connection pool có reset trạng thái sau khi trả connection hay không.
8. Routing: truy vấn có được chuyển tới primary, replica hoặc một endpoint proxy không.

Đừng suy ra DBMS từ dependency trong build file. Một ứng dụng có thư viện JDBC cho PostgreSQL vẫn có thể dùng driver khác theo profile hoặc kết nối tới một dịch vụ tương thích. Nguồn xác thực đáng tin cậy là metadata của connection đang hoạt động và cấu hình môi trường được triển khai.

## 6. Cách kiểm tra mức hiện hành theo từng DBMS

Các câu lệnh dưới đây là ví dụ chẩn đoán, không phải script cấu hình dùng chung. Quyền truy cập metadata có thể khác nhau; một số giá trị báo session hiện hành, một số báo default cho kết nối mới. Cần đối chiếu với tài liệu phiên bản đang chạy.

### PostgreSQL

Xem mức isolation hiện hành của session và giá trị mặc định cấu hình:

~~~sql
SHOW transaction_isolation;
SHOW default_transaction_isolation;

SELECT current_setting('transaction_isolation') AS current_level,
       current_setting('default_transaction_isolation') AS configured_default;
~~~

`SHOW transaction_isolation` cho biết thiết lập áp dụng cho transaction/session context hiện tại theo trạng thái server. `default_transaction_isolation` là cấu hình mặc định cho transaction mới khi không có override. Khi kiểm tra trong một transaction đã bắt đầu, hãy chắc chắn truy vấn chẩn đoán không bị nhầm với một session/connection khác.

### MySQL / InnoDB

Trên các phiên bản MySQL hiện đại, có thể kiểm tra biến isolation:

~~~sql
SELECT @@transaction_isolation AS session_isolation,
       @@global.transaction_isolation AS global_isolation;
~~~

Biến tương thích ở một số phiên bản cũ có tên `tx_isolation`. Hãy dùng đúng tên biến theo phiên bản. Giá trị global thường ảnh hưởng session mới; session hiện tại có thể đã được override. Cũng cần xác minh bảng thực sự dùng InnoDB, vì isolation và concurrency behavior phụ thuộc storage engine.

### SQL Server

SQL Server có thể xem isolation hiện hành của session bằng:

~~~sql
DBCC USEROPTIONS;
~~~

Để kiểm tra các tùy chọn row-versioning ở cấp database, người có quyền thích hợp có thể truy vấn metadata:

~~~sql
SELECT name,
       is_read_committed_snapshot_on,
       snapshot_isolation_state_desc
FROM sys.databases
WHERE name = DB_NAME();
~~~

`DBCC USEROPTIONS` cho biết tùy chọn hiện hành trong session. Các cột trong `sys.databases` cho biết database có bật read-committed snapshot hay cho phép snapshot isolation hay không; chúng không tự chứng minh transaction cụ thể đã dùng `SNAPSHOT`.

### Oracle Database

Oracle yêu cầu phân biệt mức transaction isolation và các thuộc tính đọc nhất quán. Transaction có thể dùng `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE` hoặc `SET TRANSACTION READ ONLY` theo cú pháp Oracle. Việc xác minh cấu hình cần tham khảo tài liệu đúng phiên bản và metadata view mà tài khoản được cấp quyền truy cập. Không lấy tên lệnh `SHOW` của PostgreSQL/MySQL làm cú pháp Oracle.

Với Oracle, một transaction `READ ONLY` có semantics snapshot transaction riêng; nó không phải cách viết đồng nghĩa với mọi cơ chế read-only của các DBMS khác.

### SQLite

SQLite không cung cấp isolation level theo cùng ma trận cấu hình với server DBMS. Tài liệu của SQLite mô tả isolation, transaction và locking dựa trên journal mode, WAL mode, transaction mode cùng kết nối. Có thể dùng các lệnh như `PRAGMA journal_mode;` để xác định journal mode, nhưng không nên diễn dịch kết quả thành nhãn `READ COMMITTED`/`REPEATABLE READ` một cách máy móc.

## 7. Xác minh isolation trong JDBC và Spring

Trong Java, có thể đọc isolation do JDBC connection báo:

~~~java
try (Connection connection = dataSource.getConnection()) {
    int level = connection.getTransactionIsolation();
    System.out.println("JDBC isolation = " + level);
}
~~~

Các hằng JDBC gồm `TRANSACTION_READ_UNCOMMITTED`, `TRANSACTION_READ_COMMITTED`, `TRANSACTION_REPEATABLE_READ`, `TRANSACTION_SERIALIZABLE` và `TRANSACTION_NONE`. Giá trị từ JDBC là thông tin hữu ích về connection nhưng không đủ để chứng minh mọi semantics của engine, nhất là khi framework thay đổi transaction setting sau khi connection được lấy.

Với Spring, cần xác minh:

- Transaction manager đang được inject là manager nào (JDBC, JPA, JTA hay manager tùy chỉnh).
- `@Transactional` có được proxy/interceptor áp dụng trên lời gọi thật không.
- Phương thức tham gia transaction hiện có hay tạo transaction mới.
- Isolation của annotation là `DEFAULT` hay mức cụ thể.
- Driver/manager có truyền isolation tới connection/server thành công không.
- Connection pool có reset isolation và trạng thái session khi trả connection không.

Không nên thêm logging thông tin nhạy cảm hoặc in toàn bộ URL chứa credential để kiểm tra. Chỉ ghi tên database, phiên bản, isolation và định danh kết nối an toàn theo chính sách observability của hệ thống.

## 8. Tên mức giống nhau nhưng kết quả có thể khác

Xét một transaction T1 đọc số lượng đơn `OPEN` hai lần. Ở giữa, T2 thêm một đơn `OPEN` rồi commit.

~~~text
T1: SELECT COUNT(*) WHERE status = 'OPEN'  -> 5
T2: INSERT order(status = 'OPEN')
T2: COMMIT
T1: SELECT COUNT(*) WHERE status = 'OPEN'  -> ?
~~~

Trong môi trường mà mỗi statement lấy snapshot mới, T1 có thể thấy 6. Trong môi trường transaction snapshot cố định, T1 có thể tiếp tục thấy 5. Cùng một câu hỏi nghiệp vụ, cùng một tên isolation trong tài liệu không bảo đảm hành vi giống nhau nếu cơ chế và semantics khác nhau.

### Một ví dụ khác: write skew

Giả sử mỗi ca trực cần ít nhất một bác sĩ. T1 và T2 cùng đọc hai bác sĩ A, B đều đang trực. T1 cập nhật A nghỉ; T2 cập nhật B nghỉ. Hai transaction ghi hai hàng khác nhau và cùng commit có thể khiến không còn ai trực.

Snapshot isolation như cách PostgreSQL triển khai `REPEATABLE READ` vẫn có thể cho phép write skew. Serializable isolation có thể phát hiện phụ thuộc và hủy một transaction. Một DBMS khác có thể dùng predicate/range locking hoặc cơ chế khác để ngăn lịch đó.

Điểm cần xác minh không phải chỉ là “server báo REPEATABLE READ”, mà là **engine có bảo vệ bất biến cụ thể của ứng dụng hay không**.

## 9. Tài liệu chính thức cần đọc phần nào?

Khi đã biết engine và phiên bản, hãy mở tài liệu chính thức đúng version và đọc các nội dung có liên quan trực tiếp:

1. **Transaction isolation levels:** định nghĩa mức cô lập và bất thường được ngăn/cho phép.
2. **Concurrency control / locking:** khóa hàng, khóa bảng, gap/next-key/predicate lock, lock wait và deadlock.
3. **MVCC / consistent reads / row versioning:** snapshot được tạo lúc nào và cách reader thấy phiên bản.
4. **Transaction statements:** cú pháp `BEGIN`, `START TRANSACTION`, `SET TRANSACTION`, `COMMIT`, `ROLLBACK` và giới hạn thời điểm đổi isolation.
5. **Session/database configuration:** default isolation, override cấp session, database hoặc server.
6. **Replication and read replicas:** tính mới của dữ liệu, read-your-writes và hành vi khi failover.
7. **Driver/framework integration:** transaction manager, auto-commit, connection pool và isolation propagation.
8. **Version-specific notes:** thay đổi mặc định, thay đổi thuật toán, bug fix hoặc khác biệt giữa edition.

Ưu tiên tài liệu reference của nhà phát triển DBMS. Bài blog, câu trả lời diễn đàn hoặc ví dụ cũ chỉ nên là gợi ý; đối chiếu lại với documentation chính thức và phiên bản của hệ thống.

### Đọc đúng phiên bản có ý nghĩa gì?

Giả sử production đang dùng MySQL 8.x, trong khi tài liệu nội bộ được viết cho MySQL 5.7. Tên biến cấu hình, cú pháp, default, công cụ quan sát hoặc chi tiết hành vi có thể thay đổi. Hãy truy cập tài liệu phiên bản khớp với server, ghi rõ phiên bản đã xác nhận và kiểm tra ghi chú nâng cấp nếu ứng dụng vừa được chuyển engine hoặc nâng cấp.

Không nên dựa vào một dòng cấu hình trong file mẫu nếu deployment có environment variable, parameter group, managed database setting hoặc lệnh khởi động ghi đè.

## 10. Cách kiểm thử semantics thay vì chỉ đọc tên cấu hình

Đọc tài liệu và kiểm tra setting là bước bắt buộc, nhưng một workload tối thiểu giúp xác nhận hệ thống triển khai đúng như kỳ vọng. Hãy tạo hai session riêng biệt tới cùng môi trường thử nghiệm và điều khiển thời điểm thao tác bằng barrier hoặc lệnh thủ công.

### Kiểm tra snapshot giữa nhiều câu SELECT

Session A:

~~~sql
BEGIN;
-- Nếu cần, đặt mức isolation đang kiểm tra trước câu truy vấn đầu.
SELECT balance FROM accounts WHERE id = 1;
-- Tạm dừng để Session B cập nhật và commit.
SELECT balance FROM accounts WHERE id = 1;
COMMIT;
~~~

Session B:

~~~sql
BEGIN;
UPDATE accounts SET balance = balance + 10 WHERE id = 1;
COMMIT;
~~~

Nếu A nhìn thấy giá trị mới ở lần đọc thứ hai, đó là dấu hiệu snapshot theo statement hoặc semantics tương ứng. Nếu A tiếp tục nhìn giá trị cũ, có thể transaction đang dùng snapshot ổn định. Không kết luận chỉ từ một lần chạy; phải đối chiếu isolation thực tế và DBMS.

### Kiểm tra predicate/phantom

Session A chạy truy vấn `status = 'OPEN'`, Session B insert một hàng mới thỏa điều kiện và commit, rồi A chạy lại truy vấn. Ghi nhận số hàng và giá trị. Phân biệt thay đổi thành viên tập kết quả với việc một hàng cũ đổi giá trị.

### Kiểm tra xung đột ghi

Session A cập nhật một hàng nhưng chưa commit; Session B cố cập nhật cùng hàng. Quan sát B chờ, bị timeout hay nhận lỗi. Sau đó lần lượt thử A commit và rollback để xem B tiếp tục trên trạng thái nào.

### Kiểm tra write skew

Tạo hai session cùng đọc bất biến nhiều hàng như “ít nhất một người trực”, rồi để mỗi session cập nhật một hàng riêng. Thử ở mức isolation mà ứng dụng định dùng. Xác định có transaction bị abort, hay cả hai có thể commit khiến bất biến sai. Chỉ thực hiện trong database test có thể khôi phục.

### Kiểm thử cần có điều kiện kiểm soát

- Mỗi session phải dùng connection riêng; nếu vô tình dùng chung connection, kết quả không đại diện cho đồng thời.
- Đặt transaction isolation rõ ràng khi thử một mức cụ thể; ghi lại giá trị session/transaction đang dùng.
- Dùng barrier hoặc điều phối thời điểm để lịch thực thi có thể lặp lại.
- Xác định trạng thái ban đầu và kết quả mong đợi trước khi chạy.
- Ghi nhận commit/rollback, thời gian chờ, lỗi SQLSTATE/error code và kết quả cuối.
- Chạy lại nhiều lần nếu lịch phụ thuộc scheduler, nhưng không thay thế việc đọc semantics chính thức.
- Dọn dữ liệu thử nghiệm và không thực hiện trên production nếu bài kiểm tra có thể thay đổi dữ liệu nghiệp vụ.

## 11. Cấu hình mặc định và connection pool có thể gây lỗi tinh vi

Connection pool tái sử dụng connection vật lý để tiết kiệm chi phí tạo kết nối. Session settings có thể tồn tại sau khi một request hoàn thành, tùy driver/pool và cách transaction manager reset resource.

Ví dụ một request thay đổi isolation cấp session nhưng không khôi phục như mong đợi. Connection được trả vào pool. Request tiếp theo nhận đúng connection vật lý đó và chạy với isolation khác kỳ vọng.

~~~text
Request A lấy connection C1
Request A: thay đổi session isolation -> REPEATABLE READ
Request A: hoàn thành và trả connection
Request B nhận lại connection C1
Request B: nghĩ rằng đang dùng DB default READ COMMITTED
Thực tế: session setting vẫn có thể là REPEATABLE READ nếu không reset
~~~

Đây là lý do phải tìm hiểu hợp đồng reset của pool và cách transaction manager đặt lại connection state. Không tự gửi lệnh `SET SESSION` tùy tiện trong code request nếu không có cơ chế hoàn nguyên đáng tin cậy.

Với JDBC, `Connection.setTransactionIsolation(...)` là API để thay đổi mức cô lập của connection khi driver/database hỗ trợ. Connection pool thường có cơ chế theo dõi và khôi phục state được quản lý, nhưng không nên suy đoán nó sẽ dọn mọi lệnh SQL session-specific mà ứng dụng tự gửi. Đọc tài liệu pool/driver và kiểm tra hành vi thực tế.

## 12. Khi framework nói DEFAULT, điều đó có nghĩa gì?

Trong Spring, `Isolation.DEFAULT` không chỉ định một mức cụ thể mới. Nó để transaction manager sử dụng mặc định của resource hoặc transaction context. Nếu muốn bảo đảm một yêu cầu snapshot cụ thể, hãy cấu hình rõ mức cô lập mà DBMS hỗ trợ và xác nhận nó được áp dụng trên transaction thật.

Ví dụ:

~~~java
@Transactional(isolation = Isolation.DEFAULT)
public Report load() {
    // Dùng mặc định mà transaction manager/resource đang cung cấp.
    return repository.readReport();
}

@Transactional(isolation = Isolation.REPEATABLE_READ, readOnly = true)
public Report loadSnapshot() {
    // Yêu cầu mức cụ thể; vẫn cần kiểm tra DBMS semantics.
    return repository.readReport();
}
~~~

Chỉ định mức trong annotation cũng có giới hạn:

- Không phải mọi manager/resource đều hỗ trợ mọi isolation level.
- Một transaction đang tồn tại có thể đã quyết định isolation trước khi phương thức hiện tại tham gia.
- `REQUIRED` thường tham gia transaction hiện có; không thể mặc nhiên thay isolation giữa transaction.
- `REQUIRES_NEW` có thể tạo transaction độc lập nhưng chi phí connection và semantics cần được cân nhắc.
- Nếu method call không đi qua transaction proxy, annotation có thể không được áp dụng.
- Đặt isolation cao hơn có thể làm tăng blocking, abort/retry hoặc ảnh hưởng throughput.

Vì thế, default của framework, default của JDBC và default của DBMS là những thứ cần được nối với nhau bằng cấu hình và quan sát, không nên coi là một giá trị duy nhất.

## 13. Quy trình quyết định mức cô lập cho nghiệp vụ

Đừng bắt đầu bằng cách hỏi “DB đang default là gì?” rồi chọn dùng luôn. Hãy bắt đầu từ điều kiện nghiệp vụ:

**Bước 1 — Mô tả bất biến.** Ví dụ số dư không âm, một ghế chỉ có một người giữ, tổng tài khoản sau chuyển tiền không đổi, hoặc mỗi ca trực phải còn người.

**Bước 2 — Liệt kê lịch có thể xảy ra.** Xác định thao tác đọc/ghi của hai transaction có thể xen kẽ ra sao; tìm dirty read, lost update, read skew, phantom hoặc write skew.

**Bước 3 — Chọn cơ chế cần thiết.** Có thể dùng unique/check constraint, conditional update, row lock, version check, snapshot hoặc serializable. Isolation là một phần của giải pháp, không phải tất cả.

**Bước 4 — Xác định semantics DBMS.** Đọc tài liệu đúng engine/version về mức cô lập, locking, MVCC và hành vi xung đột.

**Bước 5 — Quyết định cấu hình.** Chọn dùng default có tài liệu và kiểm soát hay chỉ định mức cụ thể tại transaction. Ghi rõ lý do và phạm vi.

**Bước 6 — Kiểm tra connection thực tế.** Xác minh server version, session setting, transaction manager, connection pool và routing.

**Bước 7 — Viết thử nghiệm đồng thời.** Dùng hai connection để tái hiện lịch quan trọng và kiểm tra trạng thái cuối.

**Bước 8 — Xử lý lỗi có chủ đích.** Chuẩn bị cho lock wait, deadlock, timeout, optimistic conflict và serialization failure; retry toàn bộ transaction khi semantics yêu cầu.

**Bước 9 — Quan sát production.** Theo dõi lock wait, deadlock, transaction duration, retry rate, timeout và lỗi consistency. Không log dữ liệu nhạy cảm chỉ để chẩn đoán.

## 14. Checklist khi chuyển môi trường hoặc nâng cấp DBMS

Khi chuyển từ local sang staging/production, chuyển provider hoặc nâng phiên bản server, hãy xác minh lại:

- Database engine và server version thực tế.
- Storage engine của các bảng liên quan.
- Isolation default ở server/database và session.
- Cài đặt row-versioning hoặc snapshot cần bật riêng.
- Lệnh khởi tạo connection/session do ứng dụng hoặc pool gửi.
- Isolation trong framework có phải `DEFAULT` hay được chỉ định.
- Transaction propagation có làm method tham gia transaction bên ngoài.
- Các query có được route sang replica không; replica lag và read-your-writes ra sao.
- Các lịch đồng thời quan trọng có còn được bảo vệ.
- Retry/deadlock/serialization failure có được xử lý đúng.
- Tài liệu chính thức và migration notes đúng phiên bản đã được xem.

Đừng xem việc ứng dụng khởi động thành công là bằng chứng isolation semantics giống môi trường cũ. Một cấu hình mới vẫn có thể chạy bình thường nhưng làm thay đổi cách các transaction tương tác.

## 15. Những hiểu nhầm thường gặp

- **“SQL chuẩn quy định mọi DBMS có cùng default.”** SQL định nghĩa các mức và yêu cầu theo chuẩn; cấu hình mặc định và cách triển khai cụ thể vẫn khác nhau.
- **“Dự án trước dùng READ COMMITTED nên dự án này cũng vậy.”** Mặc định có thể khác theo engine, version, storage engine và deployment.
- **“Cùng REPEATABLE READ thì cùng ngăn phantom/write skew.”** Không thể suy ra như vậy; cần đọc semantics cụ thể.
- **“`Isolation.DEFAULT` nghĩa là READ COMMITTED.”** Nó có nghĩa framework dùng mặc định của resource/transaction manager, không phải một nhãn cố định.
- **“Một query kiểm tra session là đủ chứng minh transaction cụ thể.”** Cần xem transaction manager có override, transaction đã tồn tại hay connection được route khác hay không.
- **“Connection pool luôn reset mọi trạng thái session.”** Phải kiểm tra hợp đồng pool/driver và những thay đổi do ứng dụng tự gửi.
- **“Đặt SERIALIZABLE là không cần xử lý lỗi.”** Serializable có thể abort transaction; ứng dụng phải retry đúng phạm vi và giữ idempotency.
- **“Isolation mạnh nhất luôn tốt nhất.”** Isolation mạnh hơn có thể tăng xung đột và chi phí; chọn theo bất biến và workload.

## 16. Ví dụ ghi nhận quyết định kỹ thuật

Một nhóm phát triển có thể ghi lại quyết định isolation theo mẫu ngắn dưới đây trong tài liệu thiết kế của hệ thống:

| Hạng mục | Giá trị cần ghi nhận |
| --- | --- |
| Engine/version | Tên DBMS và phiên bản từ connection thật |
| Default | Giá trị server/database/session được xác minh |
| Framework | Transaction manager, propagation, `Isolation.DEFAULT` hay mức cụ thể |
| Workload | Báo cáo nhiều truy vấn, cập nhật một hàng, hay bất biến nhiều hàng |
| Semantics cần | Snapshot theo câu lệnh, snapshot theo transaction, hay serializable |
| Cơ chế phụ trợ | Constraints, conditional update, row locks, versioning |
| Lỗi có thể phát sinh | Deadlock, timeout, serialization failure, stale replica read |
| Retry strategy | Số lần, backoff, phạm vi retry, idempotency |
| Bằng chứng | Link tài liệu đúng phiên bản, câu lệnh kiểm tra và kết quả thử nghiệm hai session |

Ví dụ quyết định: “Báo cáo đối soát cần các truy vấn trong cùng một snapshot. Ứng dụng dùng PostgreSQL phiên bản đã xác minh, mở một transaction read-only ở REPEATABLE READ, giữ transaction trong thời gian truy vấn ngắn và đọc từ primary. Bài kiểm tra hai session xác nhận lần đọc thứ hai tiếp tục thấy snapshot ban đầu.”

Đây là một quyết định cụ thể hơn nhiều so với câu “database mặc định là REPEATABLE READ”. Nó gắn isolation với engine, nhu cầu và bằng chứng.

## Kết luận

Mức cô lập mặc định chỉ là điểm khởi đầu. Hành vi thực tế phụ thuộc DBMS, phiên bản, cấu hình server/database/session, connection pool, driver, framework và transaction context. Cùng một tên isolation không nhất thiết mang lại cùng snapshot, khóa hoặc cách xử lý xung đột giữa các engine.

Khi thiết kế concurrency, hãy mô tả bất biến và lịch giao dịch cần bảo vệ trước; sau đó đọc tài liệu chính thức đúng hệ quản trị đang chạy, kiểm tra isolation trên connection/transaction thật và xác minh bằng thử nghiệm có điều phối. **Không được thay thế việc hiểu semantics của DBMS bằng giả định về giá trị mặc định.**
