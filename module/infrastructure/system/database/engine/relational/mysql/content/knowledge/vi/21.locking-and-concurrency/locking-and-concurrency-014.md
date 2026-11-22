# GET_LOCK, RELEASE_LOCK và vòng đời khóa tư vấn theo kết nối

MySQL cung cấp các hàm khóa tư vấn (advisory lock) để nhiều session phối hợp truy cập một tài nguyên logic. Hai hàm chính là GET_LOCK() để xin khóa theo tên và RELEASE_LOCK() để giải phóng khóa. Khác với row lock của InnoDB, named lock gắn với session kết nối, không gắn với một hàng hay một transaction.

Điểm quan trọng nhất khi sử dụng nhóm hàm này là vòng đời kết nối. Khóa được giữ sau COMMIT và ROLLBACK; nó chỉ được giải phóng khi session gọi RELEASE_LOCK() tương ứng hoặc session kết thúc. Nếu ứng dụng dùng connection pool mà trả kết nối về pool khi vẫn giữ khóa, session vật lý có thể tiếp tục giữ khóa và chặn các yêu cầu khác.

Trong module **DATABASE_MYSQL**, named lock hữu ích khi cần bảo vệ một công việc logic như chạy một tác vụ định kỳ, tạo hóa đơn cho cùng một đơn hàng hoặc chỉ cho phép một tiến trình rebuild một tài nguyên tại một thời điểm. Bài học này trình bày cách hoạt động, giá trị trả về, phạm vi khóa, quản lý nhiều khóa, tích hợp Java/JDBC, giám sát và các giới hạn cần hiểu trước khi triển khai.

## 1. Khóa tư vấn là gì?

Khóa tư vấn là cơ chế phối hợp tự nguyện giữa các thành phần ứng dụng. Một session xin khóa theo tên; session khác xin cùng tên sẽ phải chờ hoặc nhận kết quả timeout cho đến khi khóa được giải phóng.

Ví dụ hai worker cùng muốn xử lý tài nguyên invoice:9001:

- Worker A gọi GET_LOCK('billing:invoice:9001', 10) và nhận khóa.
- Worker B gọi GET_LOCK() với cùng tên và phải chờ.
- Khi A hoàn tất, A gọi RELEASE_LOCK().
- B có thể nhận khóa nếu thời gian chờ chưa hết.

Khóa tư vấn không tự ngăn UPDATE hoặc DELETE. Nó chỉ phối hợp những client có cùng quy ước gọi GET_LOCK() trước khi thực hiện công việc được bảo vệ. Một ứng dụng khác có quyền ghi bảng nhưng không tuân thủ quy ước này vẫn có thể thay đổi dữ liệu.

Do đó, advisory lock bổ sung cho transaction, row lock và constraint; nó không thay thế PRIMARY KEY, UNIQUE, FOREIGN KEY hoặc cơ chế bảo vệ dữ liệu của InnoDB.

## 2. Phạm vi và đặc tính của named lock

Named lock được quản lý ở cấp một MySQL server instance:

- Tên khóa được chia sẻ giữa các session trên cùng một mysqld.
- Tên khóa không thuộc riêng một schema hoặc một bảng.
- Hai ứng dụng ở hai database khác nhau nhưng dùng cùng tên vẫn tranh chấp cùng khóa.
- Khóa có tính độc quyền: tại một thời điểm chỉ một session có thể nắm giữ named lock đó.
- Khóa được giải phóng bằng RELEASE_LOCK() hoặc khi session kết thúc.
- COMMIT và ROLLBACK không giải phóng named lock.
- GET_LOCK() không tạo ra một hàng dữ liệu hoặc một constraint trong schema.

Tên khóa tối đa 64 ký tự và cần là tên không rỗng. So sánh tên khóa không phân biệt hoa/thường; nên chuẩn hóa tên về chữ thường để tránh hai module vô tình dùng các cách viết khác nhau cho cùng tài nguyên.

Ví dụ tên có namespace ứng dụng:

```sql
SELECT GET_LOCK('billing:invoice:9001', 10);
```

Nên đặt tiền tố cho ứng dụng hoặc module, sau đó là loại tài nguyên và định danh ổn định. Tránh dùng tên chung chung như lock, job hoặc process, vì chúng dễ xung đột với thành phần khác trên cùng server.

Tên khóa có thể xuất hiện trong Performance Schema. Không đưa password, token, email hoặc dữ liệu nhạy cảm vào tên khóa.

## 3. GET_LOCK(): xin khóa theo tên

Cú pháp:

```sql
GET_LOCK(lock_name, timeout)
```

Trong đó:

- lock_name là tên khóa cần xin.
- timeout là thời gian chờ tính bằng giây.
- timeout bằng 0 nghĩa là không chờ; nếu khóa đang bận thì trả kết quả timeout ngay.
- timeout dương cho phép chờ tối đa số giây chỉ định.
- timeout âm có nghĩa là chờ vô hạn; tránh dùng trong request cần thời gian phản hồi có giới hạn.

Ví dụ:

```sql
SELECT GET_LOCK('billing:invoice:9001', 10) AS lock_result;
```

Giá trị trả về:

| Kết quả | Ý nghĩa | Hành động của ứng dụng |
|---:|---|---|
| 1 | Đã lấy được khóa | Có thể chạy phần công việc được bảo vệ |
| 0 | Hết thời gian chờ mà chưa lấy được khóa | Không chạy công việc; trả trạng thái bận hoặc thử lại theo chính sách |
| NULL | Có lỗi khi xin khóa | Xử lý như lỗi; không giả định đã có khóa |

Không được tiếp tục phần công việc chỉ vì câu SELECT chạy mà không ném lỗi. Ứng dụng phải kiểm tra chính xác kết quả bằng 1.

Ví dụ không chờ:

```sql
SELECT GET_LOCK('scheduler:daily-reconcile', 0) AS acquired;
```

Cách này phù hợp khi tác vụ có thể bỏ qua lượt chạy nếu worker khác đang xử lý. Nếu kết quả là 0, worker ghi nhận trạng thái skipped/busy rồi kết thúc hoặc lên lịch lại theo chính sách.

## 4. RELEASE_LOCK(): giải phóng khóa

Cú pháp:

```sql
RELEASE_LOCK(lock_name)
```

Giá trị trả về:

| Kết quả | Ý nghĩa |
|---:|---|
| 1 | Session hiện tại đã giải phóng một lần giữ khóa thành công |
| 0 | Session hiện tại không sở hữu khóa đó; khóa có thể đang do session khác giữ |
| NULL | Tên khóa không tồn tại |

Ví dụ:

```sql
SELECT RELEASE_LOCK('billing:invoice:9001') AS release_result;
```

Chỉ session sở hữu khóa mới có thể giải phóng khóa. Một session quản trị khác không thể dùng RELEASE_LOCK() để giải phóng khóa của session đang chạy. Nếu cần kết thúc session giữ khóa, người có quyền phù hợp có thể xác định connection rồi xử lý session theo quy trình vận hành; việc kill connection có tác động đến mọi công việc khác của session đó.

### 4.1. Ghép GET_LOCK và RELEASE_LOCK đúng cách

Mẫu SQL cơ bản:

Ví dụ dùng bảng tồn kho đơn giản:

```sql
CREATE TABLE inventory (
    sku VARCHAR(32) NOT NULL,
    reserved_quantity INT NOT NULL DEFAULT 0,
    PRIMARY KEY (sku)
) ENGINE = InnoDB;
```

```sql
-- Bước 1: chỉ tiếp tục nếu kết quả là 1
SELECT GET_LOCK('inventory:sku:ABC-123', 10) AS acquired;

-- Bước 2: thực hiện công việc trong transaction
START TRANSACTION;

UPDATE inventory
SET reserved_quantity = reserved_quantity + 1
WHERE sku = 'ABC-123';

COMMIT;

-- Bước 3: giải phóng khóa tư vấn
SELECT RELEASE_LOCK('inventory:sku:ABC-123') AS released;
```

Các câu lệnh trên là một quy trình có điều kiện: nếu GET_LOCK() trả 0 hoặc NULL thì không chạy transaction. Nếu UPDATE hoặc COMMIT thất bại, ứng dụng phải rollback khi cần rồi vẫn thực hiện RELEASE_LOCK() trong nhánh dọn dẹp.

Nên giải phóng khóa sau khi transaction đã COMMIT hoặc ROLLBACK. Như vậy, session khác chỉ nhận khóa sau khi thay đổi dữ liệu của công việc trước đã kết thúc.

### 4.2. Lấy lại cùng một tên khóa trong một session

Từ MySQL 5.7.5, một session có thể giữ nhiều named lock cùng lúc và có thể xin cùng một tên nhiều lần. Mỗi lần GET_LOCK() thành công cần một lần RELEASE_LOCK() tương ứng.

Ví dụ:

```sql
SELECT GET_LOCK('app:resource:42', 0); -- 1
SELECT GET_LOCK('app:resource:42', 0); -- 1, cùng session xin lại

SELECT RELEASE_LOCK('app:resource:42'); -- 1 lần giữ được giải phóng
SELECT RELEASE_LOCK('app:resource:42'); -- lần giữ còn lại được giải phóng
```

Sau lần RELEASE_LOCK() đầu tiên, session khác vẫn chưa thể lấy khóa vì session hiện tại còn một lần giữ khóa. Chỉ sau khi mọi lần giữ cùng tên được giải phóng thì session khác mới có thể nhận khóa.

Đây là nguyên nhân phổ biến gây khóa bị giữ lâu: một nhánh code gọi GET_LOCK() lặp lại nhưng chỉ gọi RELEASE_LOCK() một lần. Ứng dụng nên theo dõi số lần acquire thành công và bảo đảm số lần release tương ứng.

Trước MySQL 5.7.5, một session không có khả năng giữ nhiều named lock đồng thời như các phiên bản mới. Nếu phải hỗ trợ server cũ, hãy kiểm tra hành vi của phiên bản cụ thể và thiết kế chỉ dùng một khóa tại một thời điểm.

## 5. Vòng đời khóa: session, transaction và connection pool

Named lock có vòng đời theo session:

| Sự kiện | Named lock có được giải phóng không? |
|---|---|
| COMMIT | Không |
| ROLLBACK | Không |
| Kết thúc một câu SELECT/UPDATE | Không |
| Gọi RELEASE_LOCK() thành công | Có, giải phóng một lần giữ khóa |
| Gọi RELEASE_ALL_LOCKS() | Có, giải phóng các named lock của session |
| Session kết thúc bình thường | Có |
| Session bị đóng hoặc bị kill connection | Có khi server kết thúc session |
| Server restart | Các khóa trong instance cũ không còn tồn tại |

### 5.1. COMMIT không giải phóng GET_LOCK

Thử trên Session A:

```sql
SELECT GET_LOCK('demo:commit-lifecycle', 0);

START TRANSACTION;
SELECT 1;

COMMIT;

-- Khóa vẫn đang được Session A giữ
SELECT IS_USED_LOCK('demo:commit-lifecycle');

SELECT RELEASE_LOCK('demo:commit-lifecycle');
```

COMMIT kết thúc transaction nhưng không giải phóng khóa tư vấn. Điều này khác với row lock của InnoDB, vốn được giải phóng khi transaction kết thúc.

### 5.2. ROLLBACK cũng không giải phóng GET_LOCK

```sql
SELECT GET_LOCK('demo:rollback-lifecycle', 0);

START TRANSACTION;

UPDATE inventory
SET reserved_quantity = reserved_quantity + 1
WHERE sku = 'ABC-123';

ROLLBACK;

-- Khóa tư vấn vẫn còn
SELECT IS_USED_LOCK('demo:rollback-lifecycle');

SELECT RELEASE_LOCK('demo:rollback-lifecycle');
```

Rollback hoàn tác thay đổi dữ liệu trong transaction InnoDB. Nó không thay đổi trạng thái named lock của session.

### 5.3. Nguy cơ khi dùng connection pool

Connection pool thường trả một logical connection về pool khi ứng dụng gọi close(). Logical close không nhất thiết đóng TCP connection hoặc session MySQL vật lý.

Nếu ứng dụng:

1. Lấy connection từ pool.
2. Xin GET_LOCK().
3. Hoàn tất công việc nhưng quên RELEASE_LOCK().
4. Gọi close() để trả connection về pool.

thì session vật lý có thể vẫn giữ named lock. Một request sau có thể nhận lại chính session đó, hoặc session khác bị chặn bởi khóa còn sót.

Quy tắc vận hành:

- Acquire và release trên cùng một physical MySQL session.
- Đặt RELEASE_LOCK() trong finally hoặc cơ chế cleanup tương đương.
- Chỉ trả connection về pool sau khi đã release mọi khóa mà luồng code sở hữu.
- Nếu không thể xác nhận release thành công vì connection lỗi, hãy loại bỏ/evict physical connection khỏi pool theo API của pool; không tái sử dụng session có trạng thái khóa không rõ.
- Không dùng RELEASE_ALL_LOCKS() một cách tùy tiện trên connection được chia sẻ giữa nhiều thành phần.

Nếu network bị đứt nhưng server chưa phát hiện session đã mất, khóa có thể tiếp tục tồn tại cho đến khi server nhận ra và kết thúc session. GET_LOCK không có lease tự hết hạn theo thời gian; timeout chỉ giới hạn thời gian chờ lấy khóa, không giới hạn thời gian giữ khóa sau khi đã lấy.

## 6. Kiểm tra trạng thái khóa

MySQL cung cấp các hàm hỗ trợ:

### 6.1. IS_FREE_LOCK()

```sql
SELECT IS_FREE_LOCK('billing:invoice:9001') AS is_free;
```

- 1: hiện không có session giữ khóa.
- 0: khóa đang được sử dụng.
- NULL: có lỗi khi kiểm tra.

### 6.2. IS_USED_LOCK()

```sql
SELECT IS_USED_LOCK('billing:invoice:9001') AS owner_connection_id;
```

Nếu khóa đang được giữ, hàm trả connection ID của session sở hữu. Nếu không có session giữ khóa, hàm trả NULL.

Có thể đối chiếu với:

```sql
SELECT CONNECTION_ID() AS current_connection_id;
```

### 6.3. Không dùng IS_FREE_LOCK() để thay GET_LOCK()

Mẫu sau có race condition:

```sql
-- Không dùng hai bước này làm cơ chế acquire
SELECT IS_FREE_LOCK('billing:invoice:9001');

-- Một session khác có thể lấy khóa giữa hai câu lệnh
SELECT GET_LOCK('billing:invoice:9001', 10);
```

Kết quả IS_FREE_LOCK() chỉ phản ánh trạng thái tại thời điểm kiểm tra. Một session khác có thể lấy khóa ngay sau đó. Hãy gọi GET_LOCK() trực tiếp và dựa vào giá trị trả về để quyết định có được thực hiện công việc hay không.

## 7. RELEASE_ALL_LOCKS() và quản lý nhiều khóa

RELEASE_ALL_LOCKS() giải phóng các named lock mà session hiện tại đang giữ và trả về số lần giữ khóa được giải phóng:

```sql
SELECT RELEASE_ALL_LOCKS() AS released_count;
```

Hàm này có thể hữu ích trong một session kiểm thử chuyên biệt hoặc quy trình cleanup có quyền sở hữu toàn bộ named lock của session.

Không nên gọi RELEASE_ALL_LOCKS() trong một connection pool hoặc một connection được nhiều thành phần dùng chung. Session có thể đang giữ khóa của một module khác; giải phóng tất cả sẽ phá vỡ cơ chế phối hợp của module đó.

Trong ứng dụng, ưu tiên lưu danh sách các tên khóa mà chính luồng công việc đã acquire và gọi RELEASE_LOCK() tương ứng từng tên. Chỉ dùng RELEASE_ALL_LOCKS() khi có bảo đảm session dành riêng và không có chủ sở hữu khóa khác trong cùng session.

## 8. Deadlock khi giữ nhiều named lock

Từ MySQL 5.7.5, một session có thể giữ nhiều named lock. Điều đó tạo khả năng deadlock nếu nhiều session lấy các khóa theo thứ tự khác nhau.

Ví dụ:

- Session A lấy khóa resource:A, sau đó chờ resource:B.
- Session B lấy khóa resource:B, sau đó chờ resource:A.
- A và B tạo thành vòng chờ.

MySQL có thể phát hiện deadlock trong quá trình xin named lock và hủy một yêu cầu lấy khóa với lỗi ER_USER_LOCK_DEADLOCK. Điều này không tự động rollback transaction InnoDB của session. Ứng dụng phải xử lý lỗi, giải phóng các khóa đã lấy trong phạm vi sở hữu của mình và quyết định rollback/retry transaction phù hợp.

Cách giảm deadlock:

1. Xác định thứ tự toàn cục cho các tên khóa, ví dụ sắp xếp theo chuỗi hoặc theo ID tăng dần.
2. Mọi luồng đều acquire theo cùng thứ tự.
3. Giữ số lượng khóa đồng thời ở mức nhỏ.
4. Không chờ thao tác mạng hoặc tương tác người dùng trong khi giữ khóa.
5. Dùng timeout hữu hạn và có chính sách retry/backoff.
6. Release trong finally ngay khi công việc kết thúc.

Nếu nhiều session cùng chờ một named lock, thứ tự được cấp khóa không được bảo đảm theo thứ tự chúng gọi GET_LOCK(). Không xây dựng logic nghiệp vụ dựa trên giả định FIFO.

### 8.1. Tránh acquire khóa theo từng hàng trong một câu SQL

Không nên gọi GET_LOCK() như một biểu thức được đánh giá cho nhiều hàng, chẳng hạn:

```sql
-- Không khuyến nghị: một statement có thể xin nhiều named lock
SELECT GET_LOCK(resource_name, 5)
FROM job_queue;
```

Optimizer không bảo đảm thứ tự đánh giá biểu thức theo thứ tự hàng mà ứng dụng mong đợi. Nếu statement lỗi giữa chừng, những named lock đã được lấy trước thời điểm lỗi vẫn có thể còn được session giữ. Việc rollback statement hoặc transaction không tự giải phóng chúng.

Hãy xin từng khóa trong luồng điều khiển ứng dụng, theo thứ tự xác định, ghi nhận mỗi lần acquire thành công và release đầy đủ trong cleanup. Nếu nghiệp vụ cần xử lý nhiều tài nguyên, cân nhắc gom thành một khóa cấp batch thay vì lấy hàng loạt named lock không kiểm soát.

## 9. Named lock khác row lock và table lock như thế nào?

| Đặc điểm | GET_LOCK() | InnoDB row lock | LOCK TABLES |
|---|---|---|---|
| Đối tượng | Tên tài nguyên logic do ứng dụng đặt | Index record và gap liên quan | Bảng |
| Phạm vi | Một mysqld instance | Transaction trên dữ liệu InnoDB | Session và bảng được khóa |
| Có cần transaction? | Không | Có, trong ngữ cảnh transaction/locking read | Có quy tắc riêng với autocommit và transaction |
| COMMIT/ROLLBACK giải phóng? | Không | Có | Không nên suy luận như row lock; theo quy tắc LOCK TABLES |
| Client không tuân thủ quy ước có bị chặn? | Không | Có, nếu thao tác xung đột trên dữ liệu | Các truy cập xung đột bị giới hạn theo table lock |
| Dùng để bảo vệ constraint? | Không | Không thay constraint | Không thay constraint |
| Hữu ích khi | Bảo vệ công việc logic không gắn với một hàng | Bảo vệ hàng dữ liệu trong transaction | Cần khóa phạm vi bảng theo nghiệp vụ/quản trị |

Ví dụ row lock:

```sql
START TRANSACTION;

SELECT *
FROM inventory
WHERE sku = 'ABC-123'
FOR UPDATE;

UPDATE inventory
SET reserved_quantity = reserved_quantity + 1
WHERE sku = 'ABC-123';

COMMIT;
```

Row lock bảo vệ dữ liệu hàng theo cơ chế InnoDB và được giải phóng khi transaction kết thúc. GET_LOCK() bảo vệ một tên logic do các client tự thỏa thuận; nó có thể tồn tại ngay cả khi chưa có hàng tương ứng trong bảng.

Nếu mục tiêu là bảo đảm không có hai hàng cùng email, hãy dùng UNIQUE constraint. Không dùng named lock làm lớp bảo vệ duy nhất cho dữ liệu vì client khác có thể không gọi cùng tên khóa.

## 10. Named lock không phải distributed lock

GET_LOCK() chỉ điều phối session trên cùng một MySQL server instance. Nếu ứng dụng có nhiều MySQL primary độc lập, mỗi server có thể cấp cùng một named lock cho một session của chính server đó.

Ví dụ:

- Worker A lấy billing:daily-close trên MySQL primary A.
- Worker B lấy billing:daily-close trên MySQL primary B.
- Hai server không chia sẻ lock manager; cả hai có thể cùng cấp khóa.

Vì vậy, GET_LOCK() không phải distributed lock cho cụm nhiều server, không phải cơ chế leader election và không cung cấp lease/fencing token. Trong môi trường failover, khóa trên server cũ không tự chuyển sang primary mới.

Nếu cần phối hợp nhiều node, chọn cơ chế phân tán phù hợp có lease, fencing token hoặc transaction/consensus semantics theo yêu cầu hệ thống. Nếu công việc chỉ chạy trên một mysqld và mọi worker đều kết nối đúng instance đó, GET_LOCK() có thể là lựa chọn đơn giản.

Nhóm hàm named-lock gồm GET_LOCK(), RELEASE_LOCK(), IS_FREE_LOCK(), IS_USED_LOCK() và RELEASE_ALL_LOCKS() không an toàn với statement-based replication. MySQL phát warning nếu gọi các hàm này khi binlog_format được đặt là STATEMENT. Không dùng việc phát lại statement có các hàm đó để đồng bộ trạng thái khóa giữa source và replica; lock chỉ tồn tại ở instance nơi hàm được thực thi.

## 11. Giám sát named lock bằng Performance Schema

Trong MySQL 5.7+ và MySQL 8.0, named lock được triển khai dựa trên metadata locking subsystem. Khóa xuất hiện trong performance_schema.metadata_locks với OBJECT_TYPE là USER LEVEL LOCK.

Truy vấn các named lock đang được giữ hoặc đang chờ:

```sql
SELECT
    ml.OBJECT_TYPE,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    ml.OWNER_THREAD_ID,
    th.PROCESSLIST_ID AS connection_id,
    th.PROCESSLIST_USER AS user_name,
    th.PROCESSLIST_HOST AS client_host
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS th
    ON th.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_TYPE = 'USER LEVEL LOCK';
```

Các cột đáng chú ý:

| Cột | Ý nghĩa |
|---|---|
| OBJECT_TYPE | USER LEVEL LOCK xác định named lock từ GET_LOCK() |
| OBJECT_NAME | Tên khóa |
| LOCK_TYPE | Chế độ metadata lock, thường là EXCLUSIVE |
| LOCK_DURATION | Named lock thường có thời lượng EXPLICIT |
| LOCK_STATUS | GRANTED hoặc PENDING cho trạng thái được cấp/đang chờ |
| OWNER_THREAD_ID | Thread nội bộ sở hữu yêu cầu lock |
| PROCESSLIST_ID | Connection ID tương ứng trong session |

LOCK_DURATION = EXPLICIT thể hiện khóa tồn tại cho đến khi được giải phóng tường minh hoặc session kết thúc, phù hợp với vòng đời của GET_LOCK().

Nếu một session gọi GET_LOCK() nhiều lần với cùng tên, Performance Schema chỉ hiển thị một dòng cho tên đó; các lần acquire tiếp theo tăng bộ đếm nội bộ. Do đó, số dòng metadata_locks không nhất thiết bằng số lần GET_LOCK() đã gọi.

Có thể kiểm tra chủ sở hữu bằng hàm:

```sql
SELECT
    IS_USED_LOCK('billing:invoice:9001') AS owner_connection_id;
```

Khi điều tra một khóa bị giữ lâu, đối chiếu connection_id với processlist và log ứng dụng để xác định request nào đã acquire nhưng chưa release.

## 12. Thực nghiệm hai session

Chạy các bước sau trong database lab với hai cửa sổ kết nối riêng.

### 12.1. Session A lấy khóa

```sql
SELECT CONNECTION_ID() AS session_a_id;

SELECT GET_LOCK('lab:invoice:1001', 0) AS acquired;
```

Kết quả mong đợi là 1. Session A hiện đang giữ khóa.

### 12.2. Session B thử lấy cùng khóa

```sql
SELECT CONNECTION_ID() AS session_b_id;

SELECT GET_LOCK('lab:invoice:1001', 3) AS acquired;
```

Session B chờ tối đa ba giây rồi nhận kết quả 0 nếu Session A vẫn giữ khóa. Session B không được chạy phần công việc được bảo vệ.

### 12.3. Session A commit nhưng chưa release

Ở Session A:

```sql
START TRANSACTION;
SELECT 1;
COMMIT;

SELECT IS_USED_LOCK('lab:invoice:1001') AS owner_after_commit;
```

Hàm IS_USED_LOCK() vẫn trả connection ID của Session A. COMMIT không giải phóng named lock.

### 12.4. Session A release và Session B thử lại

Ở Session A:

```sql
SELECT RELEASE_LOCK('lab:invoice:1001') AS released;
```

Sau đó ở Session B:

```sql
SELECT GET_LOCK('lab:invoice:1001', 3) AS acquired;
```

Nếu Session B nhận 1, nó đã lấy được khóa. Kết thúc thí nghiệm bằng:

```sql
SELECT RELEASE_LOCK('lab:invoice:1001');
```

### 12.5. Quan sát Performance Schema

Trong một session thứ ba hoặc sau khi mở khóa, chạy truy vấn ở phần trước để quan sát dòng USER LEVEL LOCK. Có thể thử giữ khóa ở Session A rồi kiểm tra LOCK_STATUS, OBJECT_NAME và PROCESSLIST_ID.

Không chạy thí nghiệm với tên khóa đang được hệ thống thật sử dụng. Dùng tiền tố lab để tránh xung đột với ứng dụng.

## 13. Tích hợp Java/JDBC an toàn

JDBC phải gọi GET_LOCK() và RELEASE_LOCK() trên cùng một connection vật lý. Dùng PreparedStatement để truyền tên khóa:

```java
String lockName = "billing:invoice:" + invoiceId;
int timeoutSeconds = 10;

try (Connection connection = dataSource.getConnection()) {
    if (!acquireNamedLock(connection, lockName, timeoutSeconds)) {
        throw new IllegalStateException(
            "Resource is busy: " + lockName
        );
    }

    try {
        // Helper này tự quản lý transaction và trạng thái connection.
        updateInvoiceInTransaction(connection, invoiceId);
    } finally {
        // Phải release trước khi trả connection về pool.
        releaseNamedLock(connection, lockName);
    }
}
```

Trong đó acquireNamedLock() thực thi SELECT GET_LOCK(?, ?) và chỉ trả true khi giá trị là 1; releaseNamedLock() thực thi SELECT RELEASE_LOCK(?) và xác nhận kết quả là 1. updateInvoiceInTransaction() chịu trách nhiệm commit/rollback và khôi phục trạng thái autocommit trước khi trả về. Cả ba thao tác phải dùng cùng connection vật lý.

Hai helper khóa có thể triển khai như sau:

```java
static boolean acquireNamedLock(
        Connection connection, String lockName, int timeoutSeconds
) throws SQLException {
    try (PreparedStatement ps =
             connection.prepareStatement("SELECT GET_LOCK(?, ?)")) {
        ps.setString(1, lockName);
        ps.setInt(2, timeoutSeconds);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("GET_LOCK returned no row");
            }
            int result = rs.getInt(1);
            if (rs.wasNull()) {
                throw new SQLException("GET_LOCK returned NULL");
            }
            return result == 1;
        }
    }
}

static void releaseNamedLock(
        Connection connection, String lockName
) throws SQLException {
    try (PreparedStatement ps =
             connection.prepareStatement("SELECT RELEASE_LOCK(?)")) {
        ps.setString(1, lockName);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("RELEASE_LOCK returned no row");
            }
            int result = rs.getInt(1);
            if (rs.wasNull() || result != 1) {
                throw new SQLException("Named lock was not released");
            }
        }
    }
}
```

Trong ứng dụng production, cần xử lý thêm lỗi khi rollback, lỗi khi release và quy tắc evict connection khỏi pool nếu trạng thái session không còn xác định. Nếu release thất bại do mất kết nối, không trả một physical connection có trạng thái không rõ về pool để tái sử dụng.

Các nguyên tắc khi tích hợp:

- Không acquire trên connection A rồi release trên connection B.
- Không đóng/return connection trước khi release.
- Không để connection pool tự chọn một session khác cho câu RELEASE_LOCK().
- Dùng timeout hữu hạn phù hợp với SLA của request.
- Không bỏ qua kết quả 0 hoặc NULL.
- Ghi log tên tài nguyên ở dạng không chứa dữ liệu nhạy cảm, thời gian chờ, connection ID và kết quả acquire/release.
- Nếu cần giữ nhiều named lock, quản lý danh sách và số lần acquire để release đúng số lần.

## 14. Các tình huống không nên dùng GET_LOCK()

| Tình huống | Lựa chọn phù hợp hơn |
|---|---|
| Bảo đảm email không trùng | UNIQUE constraint |
| Cập nhật tồn kho của một hàng trong transaction | SELECT ... FOR UPDATE hoặc atomic UPDATE |
| Điều phối worker trên nhiều MySQL primary | Distributed lock/coordination service phù hợp |
| Cần lock tự hết hạn sau một khoảng thời gian | Cơ chế lease có fencing token |
| Cần ngăn mọi client ghi một bảng | Constraint, quyền truy cập hoặc cơ chế khóa dữ liệu phù hợp |
| Chỉ cần kiểm tra một hàng có tồn tại | EXISTS hoặc SELECT phù hợp |
| Chỉ cần khóa một hàng trong transaction | InnoDB row lock |

GET_LOCK phù hợp khi nhiều luồng ứng dụng cần tự nguyện phối hợp quanh một tài nguyên logic, đặc biệt khi tài nguyên đó không có một hàng đại diện rõ ràng. Không dùng nó để thay thế tính toàn vẹn dữ liệu do database cung cấp.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ COMMIT sẽ tự release GET_LOCK | Khóa tiếp tục chặn session khác | Gọi RELEASE_LOCK() tường minh |
| Chỉ release trong nhánh thành công | Exception làm khóa bị giữ lâu | Đặt cleanup trong finally |
| Acquire và release bằng hai connection khác nhau | Session sở hữu khóa vẫn giữ nó | Dùng cùng physical connection |
| Trả connection về pool khi chưa release | Session vật lý có thể tiếp tục giữ khóa | Release trước logical close; evict nếu trạng thái không rõ |
| Không kiểm tra giá trị GET_LOCK | Chạy công việc dù chưa có khóa | Chỉ tiếp tục khi kết quả bằng 1 |
| Dùng IS_FREE_LOCK rồi mới GET_LOCK | Race condition giữa hai câu lệnh | Gọi GET_LOCK trực tiếp |
| Quên acquire lặp lại cùng tên | Còn một lần giữ khóa chưa release | Theo dõi số lần acquire/release |
| Dùng tên khóa chung chung | Các module vô tình chặn nhau | Namespace theo ứng dụng và tài nguyên |
| Chờ vô hạn | Request/worker có thể treo không giới hạn | Dùng timeout hữu hạn và backoff |
| Dùng GET_LOCK như distributed lock | Các mysqld độc lập không chia sẻ lock | Dùng hệ thống điều phối phân tán |
| Gọi RELEASE_ALL_LOCKS trên connection dùng chung | Giải phóng khóa của module khác | Release từng tên khóa thuộc quyền sở hữu |
| Acquire nhiều khóa theo thứ tự khác nhau | Có thể deadlock | Sắp xếp tên khóa theo thứ tự toàn cục |

## 16. Quy trình triển khai và vận hành

Trước khi triển khai:

1. Xác định tài nguyên logic cần bảo vệ và quy ước tên khóa duy nhất.
2. Bảo đảm tên không rỗng, không quá 64 ký tự và có namespace ứng dụng.
3. Chọn timeout phù hợp; không dùng chờ vô hạn cho request thông thường.
4. Quy định rõ hành vi khi kết quả GET_LOCK là 0 hoặc NULL.
5. Thiết kế luồng acquire trước transaction, commit/rollback xong mới release.
6. Nếu dùng nhiều khóa, quy định thứ tự acquire nhất quán.
7. Xác nhận mọi đường thoát đều release trong finally.
8. Kiểm thử với connection pool, timeout, exception và mất kết nối.

Khi vận hành:

1. Theo dõi named lock qua performance_schema.metadata_locks.
2. Đối chiếu OWNER_THREAD_ID với PROCESSLIST_ID và log ứng dụng.
3. Phát hiện session giữ USER LEVEL LOCK lâu bất thường.
4. Kiểm tra connection pool có trả connection khi lock còn tồn tại không.
5. Theo dõi GET_LOCK timeout và ER_USER_LOCK_DEADLOCK.
6. Kiểm tra binlog_format nếu binary logging dùng STATEMENT.
7. Xác nhận cơ chế failover không dựa vào named lock như một khóa phân tán.
8. Chỉ kill connection sau khi đánh giá các transaction và công việc khác đang chạy trên session đó.

## 17. Ghi nhớ

- GET_LOCK(name, timeout) xin một khóa tư vấn độc quyền theo tên trên một MySQL server instance.
- GET_LOCK trả 1 khi lấy được khóa, 0 khi timeout và NULL khi có lỗi.
- RELEASE_LOCK trả 1 khi giải phóng thành công, 0 nếu session hiện tại không sở hữu khóa và NULL nếu tên khóa không tồn tại.
- Tên khóa tối đa 64 ký tự; tên được chia sẻ giữa các schema trên cùng server và so sánh không phân biệt hoa/thường.
- Named lock gắn với session, không gắn với transaction; COMMIT và ROLLBACK không giải phóng khóa.
- Khóa được giải phóng tường minh hoặc khi session kết thúc; GET_LOCK không cung cấp lease tự hết hạn.
- Từ MySQL 5.7.5, một session có thể giữ nhiều named lock; acquire lặp cùng tên cần số lần release tương ứng.
- Dùng IS_FREE_LOCK và IS_USED_LOCK để quan sát; không dùng IS_FREE_LOCK thay cho thao tác acquire nguyên tử.
- Named lock xuất hiện trong Performance Schema metadata_locks với OBJECT_TYPE = USER LEVEL LOCK và thường có LOCK_DURATION = EXPLICIT.
- GET_LOCK chỉ điều phối các client cùng tuân thủ quy ước; nó không thay row lock, unique constraint hoặc distributed lock.
- Với connection pool, acquire và release trên cùng physical connection, release trước khi trả connection về pool.
- Dùng timeout hữu hạn, thứ tự acquire ổn định và cleanup trong finally để giảm khóa bị rò rỉ và deadlock.

GET_LOCK và RELEASE_LOCK là công cụ đơn giản để điều phối công việc theo tài nguyên logic trong một MySQL instance. Khi hiểu đúng vòng đời session và kết hợp với transaction, constraint cùng quản lý connection pool, ứng dụng có thể tránh xử lý trùng một tác vụ mà không để khóa tư vấn tồn tại ngoài ý muốn.

## Tài liệu tham khảo

- MySQL 8.0 Reference Manual — Locking Functions: https://dev.mysql.com/doc/refman/8.0/en/locking-functions.html
- MySQL 8.0 Reference Manual — The metadata_locks Table: https://dev.mysql.com/doc/refman/8.0/en/performance-schema-metadata-locks-table.html
- MySQL 8.0 Reference Manual — Metadata Locking: https://dev.mysql.com/doc/refman/8.0/en/metadata-locking.html

