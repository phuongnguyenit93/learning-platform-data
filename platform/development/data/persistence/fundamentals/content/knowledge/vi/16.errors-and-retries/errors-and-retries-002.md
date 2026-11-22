# Phân biệt lỗi tạm thời với lỗi không thể giải quyết bằng thử lại

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Phân biệt **lỗi tạm thời** (*transient error*), **lỗi không thể khắc phục bằng việc thử lại cùng yêu cầu** (*non-transient error*) và **kết quả thao tác chưa xác định** (*unknown outcome*).
2. Đọc ngữ cảnh lỗi và mã `SQLSTATE` của PostgreSQL qua `SQLException` trong Java để quyết định dừng, retry hoặc đối soát.
3. Giải thích vì sao `40001` và `40P01` thường cần **thử lại toàn transaction**, trong khi lỗi dữ liệu, schema và quyền thường cần sửa nguyên nhân.
4. Thiết kế retry có giới hạn lần thử, giới hạn thời gian, exponential backoff, jitter và khả năng hủy.
5. Dùng idempotency key và ràng buộc UNIQUE để xử lý an toàn khi client không biết giao dịch đã commit hay chưa.
6. Kết hợp phân loại lỗi với thiết kế transaction, connection pool, API và hệ thống giám sát.

Bài thuộc chương **Lỗi và thử lại** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module tập trung vào lưu trữ bền vững trong ứng dụng Java: mô hình dữ liệu, lược đồ, truy vấn, chỉ mục, transaction, mức cô lập, kiểm soát đồng thời, xử lý lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và tối ưu hiệu năng. Retry chỉ đúng khi vừa cải thiện khả năng phục hồi vừa giữ được **bất biến dữ liệu** mà nghiệp vụ yêu cầu.

## 1. Vì sao không phải lỗi nào cũng nên retry?

Xét API tạo đơn hàng. Sau khi gửi SQL, Java nhận một `SQLException`. Có ít nhất ba khả năng:

- Hai transaction gặp **deadlock**; PostgreSQL đã hủy một transaction để phá vòng chờ. Giao dịch có thể thành công ở lần thử sau nếu được chạy lại an toàn.
- Câu SQL vi phạm `CHECK (quantity > 0)` vì `quantity = -3`. Chạy lại 100 lần với cùng dữ liệu không sửa được lỗi.
- Database đã commit đơn hàng nhưng kết nối mất đúng lúc gửi phản hồi. Java thấy exception, song **không biết đơn đã được lưu hay chưa**. Tạo đơn lần nữa bằng khóa mới có thể gây ghi trùng.

Điều quan trọng là phân biệt **tính tạm thời của nguyên nhân lỗi** với **tính an toàn khi lặp của thao tác**.

| Nhóm | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Lỗi tạm thời | Deadlock, transaction conflict, failover, cạn tài nguyên trong một khoảng ngắn | Retry có điều kiện, backoff, giới hạn số lần và thời gian |
| Lỗi không tự hết khi thử lại | SQL sai, thiếu quyền, dữ liệu vi phạm ràng buộc, định dạng không hợp lệ | Sửa code, schema, quyền, dữ liệu hoặc quy tắc nghiệp vụ |
| Trạng thái chưa xác định | Client mất phản hồi sau `COMMIT` hoặc sau thao tác ghi tự commit | Đối soát bằng định danh nghiệp vụ/idempotency key rồi mới quyết định tiếp |

Một lỗi có nguyên nhân tạm thời **không đồng nghĩa** được phép retry mọi thao tác. Ví dụ mất mạng khi gọi cổng thanh toán là một lỗi mạng tạm thời, nhưng yêu cầu thanh toán có thể đã thành công; lặp yêu cầu mà không có cơ chế chống trùng sẽ nguy hiểm.

## 2. Ranh giới transaction quyết định cách xử lý

Giả sử một nghiệp vụ thực hiện:

~~~text
A. Lấy Connection từ DataSource
B. Bắt đầu transaction
C. Trừ tồn kho có điều kiện
D. Tạo đơn hàng
E. COMMIT
F. Trả kết quả cho HTTP client
~~~

Vị trí xảy ra lỗi ảnh hưởng trực tiếp đến ý nghĩa của retry:

| Lỗi ở bước | Điều có thể khẳng định | Quyết định tiếp theo |
| --- | --- | --- |
| A, chưa mượn được connection | Nhánh thao tác này chưa dùng connection để gửi SQL | Có thể chờ rồi thử mượn lại, nếu còn ngân sách |
| B–D, DB báo lỗi SQL và transaction chưa commit | Những thay đổi trong transaction có thể rollback | Rollback; phân loại nguyên nhân rồi chỉ retry khi an toàn |
| B–D, mất socket khi đang ghi | Client không nắm chắc mọi bước server đã thực hiện; autocommit làm tình hình khác đi | Xác định transaction boundary; đối soát khi có khả năng đã commit |
| E, mất phản hồi `COMMIT` | DB có thể đã commit và chỉ mất gói tin phản hồi | Không suy ra rollback; tra cứu qua request key |
| F, phản hồi API bị mất sau commit | DB đã có kết quả nhưng client có thể gọi lại | Cùng request key phải quy về cùng một yêu cầu nghiệp vụ |

Ở PostgreSQL, sau lỗi SQL trong transaction, session thường vào trạng thái **transaction aborted**. Những lệnh SQL tiếp theo có thể trả `25P02` cho đến khi `ROLLBACK` hoặc phục hồi bằng savepoint phù hợp. Retry statement ngay trong transaction đã hỏng sẽ không giải quyết được vấn đề.

Với transaction gồm nhiều lần đọc và ghi, dữ liệu mới có thể đã thay đổi trong lúc retry. Đặc biệt ở `SERIALIZABLE`, retry **phải tính lại các quyết định nghiệp vụ từ đầu** trên transaction mới, thay vì chỉ thực thi lại câu SQL cuối.

## 3. Phân loại theo SQLSTATE của PostgreSQL

`SQLSTATE` thường là mã gồm năm ký tự. Trong JDBC, đọc bằng `SQLException.getSQLState()`. Hai ký tự đầu biểu thị nhóm lỗi; một số mã có ý nghĩa riêng theo PostgreSQL.

Các hướng xử lý trong bảng là **gợi ý có điều kiện cho PostgreSQL**, không phải danh sách tự động retry áp dụng cho mọi thao tác hay DBMS:

| SQLSTATE / nhóm | Nguyên nhân thường gặp | Có nên thử lại? |
| --- | --- | --- |
| `40001` — serialization_failure | Transaction bị từ chối để giữ tính tuần tự | Thường retry **toàn transaction**, nếu an toàn |
| `40P01` — deadlock_detected | Vòng chờ khóa; DB hủy một transaction | Retry toàn transaction có giới hạn; xem lại thứ tự khóa |
| `55P03` — lock_not_available | Không lấy được khóa theo NOWAIT hoặc điều kiện timeout | Có thể retry với backoff, hoặc cần giảm tranh chấp |
| `08xxx` — connection exception | Không kết nối được, socket bị ngắt | Có thể mở kết nối mới; phải xét **kết quả ghi chưa rõ** |
| `57P01` — admin_shutdown | DB đang ngừng hoạt động | Có thể kết nối lại sau phục hồi; không suy ra thao tác ghi chưa xảy ra |
| `57P03` — cannot_connect_now | DB tạm thời chưa nhận kết nối | Retry sau khi DB sẵn sàng, có giới hạn |
| `53300` — too_many_connections | Hết slot kết nối | Giảm tải, kiểm tra pool; retry dồn dập có hại |
| `53200` — out_of_memory | Database thiếu bộ nhớ | Điều tra năng lực/hành vi truy vấn; retry ngay có thể tệ hơn |
| `57014` — query_canceled | SQL bị hủy do timeout, lệnh cancel hoặc nguyên nhân khác | Cần tìm nguyên nhân; không mặc nhiên retry |
| `25P02` — in_failed_sql_transaction | Transaction hiện tại đã lỗi | Rollback; giải quyết lỗi trước đó |
| `23505` — unique_violation | Khóa trùng, có thể là xung đột idempotency | Kiểm tra dữ liệu/kết quả hiện có; không retry mù |
| `23503` — foreign_key_violation | Không có bản ghi tham chiếu hợp lệ | Sửa dữ liệu, thứ tự thao tác hoặc logic |
| `23502` — not_null_violation | Bỏ thiếu trường bắt buộc | Sửa đầu vào/schema |
| `23514` — check_violation | Vi phạm CHECK constraint | Sửa quy tắc/đầu vào |
| `22xxx` — data exception | Kiểu, độ dài, số học hoặc dữ liệu không hợp lệ | Sửa dữ liệu hoặc biểu thức |
| `42xxx` — syntax/access rule | Sai SQL, thiếu cột/bảng, một số lỗi quyền | Sửa query, schema hoặc quyền |
| `28xxx` — invalid authorization | Lỗi xác thực | Sửa thông tin xác thực/cấu hình |
| `0A000` — feature_not_supported | Tính năng không được DB hỗ trợ | Điều chỉnh thiết kế hoặc phiên bản |

Một số lỗi thuộc class có ý nghĩa rộng. Ví dụ `23505` có thể là “email đã đăng ký” hoặc “request key của yêu cầu đã được xử lý”: cùng mã lỗi nhưng **phản hồi nghiệp vụ hoàn toàn khác nhau**. Lỗi `08xxx` có thể xảy ra trước khi gửi SQL hoặc sau khi DB đã xử lý xong một thao tác ghi; chỉ mã lỗi không cho biết commit đã xảy ra hay chưa.

### 3.1. Retry toàn transaction khi gặp serialization failure hoặc deadlock

Xét nghiệp vụ chuyển tiền:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT balance FROM accounts WHERE id = 101;

UPDATE accounts
SET balance = balance - 100
WHERE id = 101 AND balance >= 100;

UPDATE accounts
SET balance = balance + 100
WHERE id = 202;

COMMIT;
~~~

Nếu PostgreSQL trả `40001), transaction phải được thực hiện lại từ bước **đọc và kiểm tra số dư** trong một transaction mới. Số dư, thứ tự giao dịch và điều kiện nghiệp vụ có thể đã thay đổi. Chạy lại duy nhất câu UPDATE cuối có thể tạo giao dịch sai logic hoặc không khớp với kết quả bước trước.

Với `40P01`, PostgreSQL phát hiện deadlock và chọn một transaction làm nạn nhân. Sau khi rollback, có thể thử lại; đồng thời cần giảm nguyên nhân gốc bằng cách thống nhất thứ tự khóa và rút ngắn thời gian giữ transaction. Nếu mỗi lần đều khóa A rồi B và giao dịch đối ứng khóa B rồi A, tăng số lần thử không phải sửa chữa căn bản.

### 3.2. Vi phạm ràng buộc không phải một tín hiệu retry

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY
);

CREATE TABLE orders (
    id          BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Nếu cố tạo đơn tham chiếu `customer_id = 9001` chưa tồn tại, PostgreSQL báo vi phạm khóa ngoại. Lặp INSERT ngay với cùng trạng thái thường không giúp gì. Nếu quantity là số âm, vấn đề là dữ liệu hoặc logic nghiệp vụ.

Một trường hợp tham chiếu sẽ được tạo **bởi một tác vụ khác trong tương lai** không có nghĩa mọi lỗi foreign key đều nên retry. Nếu cần đợi dữ liệu phụ thuộc, hãy thiết kế điều phối rõ ràng bằng queue, dependency hoặc thứ tự transaction, thay vì lặp vô hạn một câu SQL lỗi.

### 3.3. Các lỗi thiết kế và cấu hình

~~~sql
-- Ví dụ có lỗi chính tả cột.
SELECT totla_amount FROM orders;
~~~

Nếu cột đúng là `total_amount`, retry trên cùng schema không sửa được lỗi. Tương tự, mật khẩu sai, thiếu `GRANT`, tên bảng không tồn tại hoặc migration không tương thích thường cần sửa cấu hình, code hoặc thứ tự triển khai.

Nếu lỗi chỉ xuất hiện trong một giai đoạn migration, hãy coi đó là vấn đề **tương thích schema** cần xử lý có chủ đích; không che bằng retry vô hạn.

## 4. Timeout và lỗi kết nối: cùng chữ “lỗi” nhưng khác kết quả

| Nơi timeout | Trạng thái có thể có | Cần cân nhắc |
| --- | --- | --- |
| Chờ mượn connection từ pool | Chưa có connection để gửi SQL ở nhánh hiện tại | Chờ có giới hạn hoặc trả lỗi quá tải |
| Kết nối TCP/TLS, login | Chưa thiết lập session thành công | Kiểm tra mạng, chứng chỉ, thông tin xác thực, DB readiness |
| Chờ khóa | Transaction có thể đang tranh chấp hoặc đã bị hủy statement | Rollback khi cần, giảm lock contention |
| Statement/query timeout | SQL có thể bị hủy hoặc connection gặp lỗi | Xác định loại lệnh và trạng thái transaction |
| Socket read timeout sau khi gửi SQL | Server có thể đã xử lý nhưng phản hồi không tới client | Đặc biệt thận trọng nếu có ghi/autocommit |
| Mất phản hồi của `COMMIT` | Commit có thể đã thành công | Bắt buộc coi kết quả là chưa xác định cho đến khi đối soát |
| HTTP client timeout | Server có thể còn làm việc hoặc đã commit | Không coi timeout HTTP là rollback DB |

Một request bị client hủy không nhất thiết làm DB dừng transaction ngay lập tức; điều này phụ thuộc driver, framework và propagation của cancellation. Với câu lệnh ghi tự commit, việc mất socket sau khi gửi statement cũng có thể dẫn đến kết quả không chắc chắn. Cần hiểu cả **giai đoạn lỗi** lẫn **ngữ nghĩa của thao tác**.

### 4.1. Mất phản hồi COMMIT

~~~text
Java client                          Database
     |                                  |
     |------- INSERT đơn hàng --------->|
     |                                  | statement thành công
     |------- COMMIT ------------------>|
     |                                  | commit hoàn tất
     |                  mất phản hồi  X |
     |<--------------- không nhận ----- |
     |                                  |
     | SQLException/timeout             |
~~~

Client **không thể kết luận transaction đã rollback**. Gọi `rollback()` trên một connection hỏng, nếu gọi được, cũng không đảo ngược một commit đã xảy ra.

Nếu nghiệp vụ tạo đơn dùng định danh mới mỗi lần retry, một yêu cầu duy nhất có thể tạo hai đơn. Điều này giải thích vì sao **lỗi mạng có thể phục hồi nhanh nhưng không được phép retry ghi một cách vô điều kiện**.

### 4.2. Quá tải và retry storm

Giả sử 1.000 request cùng gặp lỗi `53300` rồi mỗi request thử lại ngay năm lần. Hệ thống có thể nhận thêm hàng nghìn lượt xin kết nối trong thời gian ngắn, đúng lúc DB không còn tài nguyên. Retry làm thời gian phục hồi lâu hơn.

Cách giảm rủi ro:

- Giới hạn số lượt thử và **ngân sách thời gian tổng**.
- Dùng **exponential backoff có jitter**.
- Giới hạn đồng thời, có thể dùng circuit breaker hoặc load shedding.
- Đo pool active/idle/pending, lock wait và độ trễ I/O.
- Phân biệt lỗi tạm thời do khả năng phục hồi tự nhiên với lỗi đòi hỏi can thiệp cấu hình, khối lượng công việc hoặc hạ tầng.

**Không tăng pool size như phản xạ đầu tiên**: nhiều connection hơn có thể làm một DB đang nghẽn CPU, I/O hoặc lock phải xử lý thêm tranh chấp.

## 5. Idempotency: điều kiện để lặp thao tác ghi an toàn

Một thao tác **idempotent ở cấp nghiệp vụ** có thể được gọi lại với cùng định danh mà không tạo thêm tác dụng phụ.

~~~sql
-- Tăng số dư 100. Chạy hai lần sẽ tăng 200.
UPDATE accounts
SET balance = balance + 100
WHERE id = 101;

-- Gán trạng thái cuối xác định.
UPDATE orders
SET status = 'CANCELLED'
WHERE id = 501;
~~~

Câu UPDATE thứ hai có thể idempotent xét riêng giá trị `status`, nhưng trigger ghi audit, sự kiện, email hoặc tích hợp ngoài DB có thể bị kích hoạt nhiều lần. Vì vậy, xét **toàn bộ hành động nghiệp vụ**, không chỉ câu SQL.

### 5.1. Một bảng chống xử lý trùng request

Ví dụ API đặt hàng nhận `requestKey` do client gửi và giữ nguyên cho mọi lần retry của cùng một yêu cầu:

~~~sql
CREATE TABLE order_requests (
    tenant_id      BIGINT NOT NULL,
    request_key    TEXT NOT NULL,
    payload_hash   TEXT NOT NULL,
    status         TEXT NOT NULL
                   CHECK (status IN ('IN_PROGRESS', 'COMPLETED')),
    order_id       BIGINT,
    PRIMARY KEY (tenant_id, request_key)
);
~~~

Ứng dụng cần thiết kế giao thức:

1. Xác thực tenant, yêu cầu một `request_key` không rỗng và tính `payload_hash` từ nội dung nghiệp vụ đã chuẩn hóa.
2. Bắt đầu transaction. Cố tạo bản ghi yêu cầu với khóa duy nhất.
3. Nếu cùng key đã tồn tại, **không lặp lại tác động tạo đơn**; kiểm tra payload có khớp không và đọc kết quả hiện có.
4. Nếu mới, thực hiện kiểm tra/giữ tồn kho, tạo đơn, ghi kết quả request và outbox trong cùng transaction.
5. Commit, rồi trả xác nhận khi nhận được kết quả commit.
6. Nếu mất phản hồi, tra cứu bằng **cùng key**, đối soát và tiếp tục giao thức chống trùng.

PostgreSQL hỗ trợ cấu trúc:

~~~sql
INSERT INTO order_requests
    (tenant_id, request_key, payload_hash, status)
VALUES
    (42, 'checkout-001', 'digest-of-request', 'IN_PROGRESS')
ON CONFLICT (tenant_id, request_key) DO NOTHING
RETURNING request_key;
~~~

Khi `RETURNING` có hàng, lệnh đã tạo một yêu cầu mới **trong transaction hiện tại**; chưa chứng minh transaction sẽ commit. Khi không có hàng, khóa đã tồn tại: cần kiểm tra trạng thái và payload. PostgreSQL có thể chờ transaction đang cạnh tranh cùng khóa giải quyết xung đột.

Một ràng buộc UNIQUE là **điều kiện cần cho chống trùng**, nhưng chưa phải toàn bộ idempotency protocol. Cần còn quy định ownership của request, trạng thái xử lý dở, TTL, quyền lấy kết quả và cách đảm bảo side effect ở các dịch vụ ngoài không bị lặp.

### 5.2. Đối soát khi kết quả commit chưa xác định

Khi mất phản hồi `COMMIT`, quy trình an toàn là:

1. Mở **kết nối mới** tới nguồn dữ liệu có độ nhất quán phù hợp, thường là primary thay vì replica có thể trễ.
2. Tra cứu theo `tenant_id + request_key` và kiểm tra payload.
3. Nếu `COMPLETED` cùng payload, trả lại kết quả đã ghi; không tạo yêu cầu mới.
4. Nếu key đã tồn tại nhưng payload khác, báo conflict.
5. Nếu chưa có bản ghi, **không khẳng định chắc transaction cũ đã thất bại**: nó có thể còn đang xử lý hoặc chưa thấy được. Chỉ thử lại bằng **cùng key** với unique constraint và quy tắc điều phối xung đột.
6. Nếu hết thời gian mà chưa xác định trạng thái, phản hồi trạng thái đang xử lý/chưa xác định và cung cấp đường tra cứu tiếp theo.

Nếu transaction còn gọi API thanh toán, gửi email hoặc phát event ra ngoài DB, cần thiết kế thêm idempotency ở dịch vụ đó, outbox hoặc cơ chế đối soát. Rollback DB không tự thu hồi cuộc gọi ngoài đã xảy ra.

## 6. Retry cần chính sách hữu hạn

Một chính sách đủ tốt phải trả lời:

| Yếu tố | Cần xác định |
| --- | --- |
| Phân loại | Lỗi nào retryable trong **ngữ cảnh operation này**? |
| Phạm vi | Retry statement đọc, mở connection hay toàn transaction ghi? |
| Số lượt | Tổng `maxAttempts`, tính cả lần đầu |
| Thời gian | Deadline tổng của request/job, không chỉ timeout mỗi lượt |
| Khoảng chờ | Exponential backoff và jitter |
| Dừng | Cancellation, thread interrupt, circuit breaker, overload |
| An toàn khi lặp | Idempotency key, constraint, kiểm tra side effect |
| Giám sát | Attempts, nguyên nhân lỗi, tỷ lệ retry thành công, p95/p99 |

Với **full jitter**, một công thức minh họa là:

`cap(attempt) = min(maxDelay, baseDelay × 2^(attempt−1))`

`sleep = random(0, cap(attempt))`

Ví dụ với baseDelay 50 ms, maxDelay 1 giây, khoảng chờ ngẫu nhiên tối đa ở các lần retry lần lượt là 50, 100, 200, 400, 800, rồi 1000 ms. Đừng áp dụng các số này máy móc cho mọi ứng dụng: một API có deadline 300 ms không thể chờ hàng giây chỉ để tăng xác suất thành công.

**Tính ngân sách theo thời gian đã dùng:** nếu đã hết deadline, không thực hiện lượt tiếp theo dù chưa đạt `maxAttempts`. Khi request bị hủy, cần dừng backoff và giải phóng connection/statement; không làm việc tiếp không mục đích.

### 6.1. Chọn một tầng chịu trách nhiệm retry

Nếu gateway, service, repository và driver đều retry cùng một lỗi ba lượt, số lần thực thi hiệu dụng có thể tăng theo cấp số nhân. Cần chỉ định rõ nơi retry:

- Truy vấn SELECT thuần có thể retry ở repository/service với ngân sách chung.
- Transaction ghi có nhiều bước nên retry ở **tầng sở hữu toàn bộ đơn vị nghiệp vụ**.
- Job bất đồng bộ có thể retry qua queue với lịch chờ và dead-letter.
- Những lỗi ngoài DB cần phối hợp với hợp đồng idempotency riêng của hệ thống nhận.

Không đặt retry mù bên dưới một service không biết thao tác có side effect hay không.

## 7. Ví dụ Java/JDBC: retry một SELECT an toàn

Đoạn Java 17 sau dùng `DataSource`, mở connection ở mỗi lượt thử, đọc `SQLState`, retry tối đa ba lần, có jitter và tôn trọng tín hiệu interrupt. Ví dụ **chỉ dành cho một SELECT thuần**, không tự động áp dụng cho ghi.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.OptionalInt;
import java.util.concurrent.ThreadLocalRandom;
import javax.sql.DataSource;

public final class SafeReadRetry {
    private final DataSource dataSource;

    public SafeReadRetry(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public OptionalInt readStock(long productId)
            throws SQLException, InterruptedException {

        final int maxAttempts = 3;
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try (Connection connection = dataSource.getConnection();
                 PreparedStatement statement = connection.prepareStatement(
                         "SELECT stock FROM products WHERE id = ?")) {

                statement.setLong(1, productId);
                statement.setQueryTimeout(2);

                try (ResultSet rs = statement.executeQuery()) {
                    if (!rs.next()) {
                        return OptionalInt.empty();
                    }
                    return OptionalInt.of(rs.getInt("stock"));
                }
            } catch (SQLException error) {
                if (attempt == maxAttempts || !isRetryableRead(error)) {
                    throw error;
                }

                long capMillis = Math.min(500L, 50L << (attempt - 1));
                long delayMillis =
                        ThreadLocalRandom.current().nextLong(capMillis + 1);
                Thread.sleep(delayMillis);
            }
        }
        throw new IllegalStateException("Unreachable retry path");
    }

    private static boolean isRetryableRead(SQLException error) {
        String state = error.getSQLState();
        if (state == null) {
            return false;
        }

        return state.startsWith("08")
                || "40001".equals(state)
                || "40P01".equals(state)
                || "55P03".equals(state)
                || "57P01".equals(state)
                || "57P03".equals(state);
    }
}
~~~

Trong triển khai thật, còn phải tích hợp deadline tổng, logging có kiểm soát, metrics và cancellation của framework. `setQueryTimeout(2)` giới hạn thời gian statement theo khả năng của driver/DBMS; không thay cho socket timeout hoặc pool acquisition timeout. Ví dụ cố ý **không retry `57014` tự động** vì query có thể bị người dùng hủy hoặc đã quá chậm. `Thread.sleep()` thích hợp minh họa code blocking; trong event loop hoặc pipeline bất đồng bộ, cần cơ chế lập lịch không chặn luồng.

Một truy vấn có tên SELECT **chưa chắc chỉ đọc** nếu gọi hàm có side effect. Chỉ dùng chính sách này khi chắc chắn phép thử lại không gây tác động nghiệp vụ.

### 7.1. SQLException và class con chỉ là tín hiệu

JDBC có các kiểu như `SQLTransientException`, `SQLNonTransientException`, `SQLRecoverableException` và `SQLTransactionRollbackException`. Những tên này gợi ý hướng xử lý, nhưng driver không nhất thiết ánh xạ mọi lỗi DBMS thành class như mong muốn.

Khi phân loại, xét:

- `SQLException.getSQLState()` và `getErrorCode()`.
- `getNextException()`, nguyên nhân và các exception liên quan.
- Operation đang chạy là SELECT, ghi trong transaction, hay `COMMIT`.
- Lệnh đã gửi đến server chưa; có autocommit hay không.
- Thông tin pool, network và deadline của request.

Tránh dựa vào việc tìm một chuỗi tiếng Anh trong `getMessage()`: message có thể đổi theo driver, engine, phiên bản hoặc ngôn ngữ. Không log secret, mật khẩu hoặc tham số nhạy cảm chỉ để chẩn đoán lỗi.

## 8. Retry **toàn transaction** khi ghi

Giả sử nghiệp vụ trừ tồn kho và tạo đơn. Bất biến quan trọng: một request key chỉ được thực hiện một lần; đơn hàng và tồn kho phải commit hoặc rollback cùng nhau.

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0)
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    request_key TEXT NOT NULL,
    product_id BIGINT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    UNIQUE (tenant_id, request_key)
);
~~~

Một câu trừ tồn kho có điều kiện:

~~~sql
UPDATE products
SET stock = stock - ?
WHERE id = ?
  AND stock >= ?;
~~~

Hệ thống phải kiểm tra số hàng được UPDATE; nếu bằng 0 thì sản phẩm không có hoặc không đủ tồn kho. Đặt bước tạo đơn và các thay đổi liên quan trong **cùng transaction**. Phải phối hợp với khóa yêu cầu duy nhất để một yêu cầu được retry không trừ tồn kho lần thứ hai.

Mẫu điều phối khái niệm:

~~~text
lặp trong số lượt thử hữu hạn:
    mở Connection / transaction mới
    try:
        giữ quyền xử lý request_key
        nếu key đã xử lý: kiểm tra payload, trả kết quả cũ
        nếu key mới:
            kiểm tra và cập nhật tồn kho bằng SQL nguyên tử
            tạo đơn và outbox event trong cùng transaction
        COMMIT
        trả kết quả
    nếu 40001 hoặc 40P01 trước khi biết commit thành công:
        rollback nếu có thể
        chờ với backoff/jitter
        thực hiện lại toàn bộ kiểm tra trong transaction mới
    nếu mất phản hồi COMMIT:
        đối soát bằng request_key trên kết nối mới
        tiếp tục giao thức idempotent; không tạo key mới
    nếu lỗi không retryable:
        rollback nếu có thể và báo nguyên nhân
~~~

Trong PostgreSQL, một transaction đang aborted không thể phục hồi bằng việc chạy tiếp `UPDATE` trên connection đó như chưa có lỗi. Cần rollback và tạo transaction mới. Nếu lỗi xảy ra **sau khi DB có thể đã commit**, retry giống như lỗi serialization thuần túy là không an toàn.

### 8.1. Ranh giới của tác dụng phụ ngoài DB

Ví dụ trong transaction:

~~~text
UPDATE tồn kho trong database
GỌI cổng thanh toán ngoài database
INSERT đơn hàng trong database
COMMIT
~~~

Nếu lệnh INSERT lỗi rồi database rollback, cổng thanh toán **không tự rollback**. Retry toàn transaction có thể khiến cổng thanh toán bị gọi thêm lần nữa. Cần thiết kế quy trình thanh toán có idempotency, trạng thái xử lý, đối soát và cơ chế bù trừ; hoặc dùng outbox để công bố event sau khi transaction DB đã commit.

Một outbox worker có thể phát thông điệp theo mô hình **at-least-once** nên consumer cũng cần loại bỏ trùng theo event ID hay yêu cầu nghiệp vụ. Idempotency được thiết kế **xuyên suốt đường đi**, không dừng ở SQL `UNIQUE`.

## 9. Phân biệt phản hồi lỗi nghiệp vụ và lỗi hạ tầng

| Nguyên nhân | Ví dụ | Hướng xử lý phía API |
| --- | --- | --- |
| Dữ liệu request sai | Quantity âm, trường bắt buộc thiếu | Trả lỗi 4xx phù hợp, giải thích dữ liệu cần sửa |
| Xung đột nghiệp vụ | Ghế đã đặt, version đã thay đổi | Báo conflict, thường có thể dùng HTTP 409 |
| Lỗi quyền người dùng | Không có quyền với tenant | Trả 401/403 theo hợp đồng xác thực/phân quyền |
| Role DB thiếu quyền | Tài khoản ứng dụng chưa được GRANT | Báo lỗi hệ thống và sửa cấu hình triển khai |
| Query/schema lỗi | Sai tên cột, migration chưa tương thích | Sửa code/schema; không retry cùng yêu cầu vô hạn |
| Deadlock/serialization | `40P01`, `40001` | Retry toàn transaction an toàn; nếu hết ngân sách báo lỗi |
| Quá tải/failover | DB chưa sẵn sàng, không có connection | Giảm tải, backoff; có thể dùng 503/Retry-After phù hợp |
| Mất phản hồi commit | Không biết đơn đã được lưu hay chưa | Trả trạng thái có thể tra cứu bằng idempotency key |

HTTP status là **hợp đồng API**, không được suy ra máy móc chỉ từ SQLSTATE. Ví dụ `23505` có thể là “email trùng” hoặc “request idempotency đã có”: một bên là xung đột, bên kia có thể trả lại kết quả cũ nếu payload khớp. `Retry-After` chỉ đề xuất thời gian gọi lại; nó **không thay thế idempotency key**.

## 10. Kiểm thử và giám sát

### 10.1. Các trường hợp cần kiểm chứng

| Tình huống thử nghiệm | Cần xác minh |
| --- | --- |
| Hai transaction gây deadlock | Một transaction bị hủy, retry có giới hạn và không vi phạm bất biến |
| Xung đột SERIALIZABLE | Có `40001`, đọc lại dữ liệu và retry toàn transaction |
| Trùng request key | Không tạo hai đơn, không trừ tồn kho hai lần; cùng payload trả cùng kết quả |
| Trùng key nhưng khác payload | Trả conflict, không âm thầm dùng lại kết quả cũ |
| CHECK/FK/SQL syntax lỗi | Dừng retry, báo nguyên nhân phù hợp |
| Pool cạn kết nối | Không tạo retry storm; không làm treo request vô hạn |
| Mất kết nối trước khi gửi SQL | Có thể phục hồi kết nối, không sinh side effect |
| Mất phản hồi `COMMIT` | Đối soát rồi tiếp tục cùng key; không tạo tác động trùng |
| Timeout khi đọc/ghi | Xác định giai đoạn, trạng thái transaction và cancellation |
| Hết số lượt hoặc deadline | Thoát vòng retry, trả lỗi quan sát được và đóng tài nguyên |

Dùng hai kết nối độc lập và database thật để thử deadlock/serialization. Với commit không xác định, cần fault injection tại **đúng ranh giới phản hồi COMMIT** trong môi trường test; chỉ gọi `ROLLBACK` hoặc dừng database bình thường không mô phỏng đầy đủ tình huống mất phản hồi. Không làm thử nghiệm phá dữ liệu trên production.

### 10.2. Những số liệu cần theo dõi

- Lỗi theo **operation, SQLSTATE, giai đoạn** (acquire, execute, commit) và bản triển khai.
- Số attempts/request, tỷ lệ retry thành công/thất bại, retry đã tiêu thụ bao nhiêu thời gian.
- p50/p95/p99 độ trễ end-to-end, thời gian backoff và số request quá deadline.
- Connection pool active/idle/pending, query latency, lock wait, deadlock và tài nguyên DB.
- Số trường hợp unknown commit, thời gian đối soát, request bị lặp nhưng đã chặn trùng.
- Tần suất xung đột idempotency key và số lỗi do payload không khớp.

Không dùng retry để che đi nguyên nhân gốc; sự tăng đột biến `40P01` có thể chỉ ra thứ tự lấy khóa không nhất quán, còn `53300` có thể cho thấy tổng số connection của các instance đã vượt khả năng DB.

## 11. Bài tập thực hành

**Bài 1 — phân loại SQLSTATE.** Một dịch vụ Java nhận các mã `40001`, `23514`, `40P01`, `08006` (ngay sau khi gửi COMMIT), `42601` và `53300`. Với từng mã, hãy chỉ ra: có cần rollback không, có retry được không, retry ở phạm vi nào, có cần đối soát trạng thái không, và có nên chờ backoff hay không.

*Gợi ý:* `40001` và `40P01` thường retry toàn transaction; `23514` và `42601` cần sửa dữ liệu/SQL; `53300` cần giảm tải và chờ có giới hạn; `08006` sau COMMIT phải coi kết quả là chưa xác định.

**Bài 2 — lỗi logic ẩn dưới retry.** Một API đặt hàng đọc `stock`, tính trừ trong Java rồi ghi `UPDATE SET stock = ?`; khi lỗi, nó tự chạy lại năm lần. Hai request đồng thời có thể gây vấn đề gì? Hãy đề xuất `UPDATE ... WHERE stock >= ?`, ràng buộc UNIQUE theo request key và transaction cho đơn/tồn kho.

**Bài 3 — phản hồi HTTP bị mất.** Một thanh toán có `request_key = pay-8821` được database lưu nhưng client timeout. Client gửi lại cùng key. Hãy thiết kế bảng trạng thái, cách kiểm tra payload, nơi lưu kết quả và cơ chế phối hợp với cổng thanh toán/outbox để không thu tiền hai lần.

**Bài 4 — ngân sách retry.** Request có deadline 700 ms. Lần đầu SQL mất 250 ms rồi báo lỗi, lần hai chờ connection 300 ms rồi thất bại. Chỉ còn 150 ms. Nếu một lượt thường cần 200 ms, có nên thử nữa không? Giải thích vì sao `maxAttempts` không phải giới hạn duy nhất.

**Bài 5 — lập chính sách cho service của bạn.** Tạo bảng gồm tên operation, mức side effect, nhóm SQLSTATE được xét retry, phạm vi transaction, idempotency key, deadline và cách đối soát. So sánh một `SELECT` chỉ đọc, một nghiệp vụ chuyển tiền và một yêu cầu gọi API ngoài.

## 12. Các ngộ nhận cần tránh

**“Mọi SQLException đều nên thử lại.”** Lỗi dữ liệu, schema, quyền và constraint có thể lặp vô hạn nếu không sửa nguyên nhân.

**“SQLTransientException nghĩa là an toàn để lặp mọi câu ghi.”** Tính tạm thời của lỗi không quyết định tính idempotent của nghiệp vụ.

**“Deadlock chỉ cần retry statement cuối.”** Transaction bị hủy/aborted; phải tính lại toàn bộ thao tác phụ thuộc trong một transaction mới.

**“Timeout đồng nghĩa thao tác chưa xảy ra.”** Đặc biệt khi socket mất sau `COMMIT`, client có thể không biết DB đã commit hay chưa.

**“Gặp `23505` thì tăng attempts.”** Vi phạm UNIQUE thường cần xử lý xung đột hoặc trả lại kết quả idempotent đã có.

**“Cố thử mãi sẽ giúp hệ thống tự hồi phục.”** Retry storm có thể ngăn DB hồi phục trong lúc quá tải.

**“Backoff cố định là đủ.”** Không có jitter và deadline, nhiều client vẫn có thể dồn retry cùng nhịp.

**“Có UNIQUE key tức là thanh toán đã hoàn toàn idempotent.”** Phải bảo vệ cả side effect ngoài DB, phản hồi và event delivery.

**“Gọi rollback trong catch chứng minh commit chưa xảy ra.”** Sau khi mất phản hồi `COMMIT`, rollback có thể không có tác dụng hoặc không tới DB.

## Ghi nhớ

**Lỗi tạm thời** có khả năng hết khi điều kiện vận hành thay đổi; **lỗi không thể giải quyết bằng thử lại** đòi hỏi sửa dữ liệu, logic, schema hoặc quyền. Với PostgreSQL, `40001` và `40P01` thường là ứng viên retry toàn transaction; nhiều lỗi `23xxx`, `22xxx` và `42xxx` thường cần xử lý nguyên nhân. Quyết định cuối cùng phụ thuộc **operation và transaction boundary**, không chỉ vào mã SQLSTATE.

Trong Java, một chính sách retry đáng tin phải giới hạn số lượt và thời gian, dùng backoff/jitter, tạo transaction mới khi thích hợp, tôn trọng cancellation và giữ mọi tài nguyên được đóng đúng. Nếu phản hồi `COMMIT` bị mất, hãy coi kết quả **chưa xác định** và dùng idempotency/đối soát để tránh nhân đôi dữ liệu nghiệp vụ.
