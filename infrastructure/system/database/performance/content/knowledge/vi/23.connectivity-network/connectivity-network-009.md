# Proxy kết nối và các ràng buộc về trạng thái phiên hoặc giao dịch

Ứng dụng thường mở nhiều kết nối đến cơ sở dữ liệu để phục vụ các request đồng thời. Nếu mỗi client giữ một kết nối vật lý riêng trong thời gian dài, số session ở DB có thể tăng lớn, tiêu thụ bộ nhớ và worker, làm tăng chi phí xác thực, quản lý socket và lập lịch. Connection proxy hoặc connection pooler đứng giữa ứng dụng và DB giúp tái sử dụng một tập backend connection có giới hạn, xếp hàng yêu cầu khi cần và đôi khi định tuyến kết nối đến node phù hợp.

Proxy có thể nhận hàng trăm hoặc hàng nghìn kết nối client nhưng chỉ duy trì một số lượng backend connection nhỏ hơn. Để làm được điều đó, nó phải quyết định backend nào phục vụ client nào và trong bao lâu. Quyết định này liên quan trực tiếp đến trạng thái session và transaction. Một session DB có thể giữ biến phiên, role, schema tìm kiếm, temporary table, cursor, prepared statement, advisory lock hoặc trạng thái transaction. Nếu proxy trả backend về pool rồi giao cho client khác, trạng thái còn sót lại có thể làm request tiếp theo chạy sai hoặc làm lộ dữ liệu giữa các client.

Trong phạm vi DATABASE_PERFORMANCE, bài học này giải thích các kiểu pooling, backend affinity, khác biệt giữa trạng thái session và transaction, các tính năng cần giữ cùng một backend, cơ chế reset và pinning, định tuyến/failover, cùng cách đo hiệu quả của proxy. Mục tiêu là tăng khả năng tái sử dụng kết nối mà vẫn bảo toàn semantics của ứng dụng và tính đúng đắn của giao dịch.

## 1. Proxy kết nối hoạt động ở giữa ứng dụng và DB

Một kiến trúc đơn giản có ba thành phần:

```text
Ứng dụng / connection pool
          |
          | frontend connections
          v
  Connection proxy / pooler
          |
          | backend connections
          v
       Database
```

Frontend connection là kết nối từ ứng dụng đến proxy. Backend connection là kết nối vật lý từ proxy đến DB. Hai loại kết nối này có vòng đời và số lượng khác nhau.

Proxy có thể thực hiện một hoặc nhiều chức năng:

- Tái sử dụng backend connection để giảm số session DB phải tạo mới.
- Giới hạn tổng backend connection đến một database hoặc node.
- Xếp hàng client khi pool backend đã bận.
- Chia pool theo database, user, tenant hoặc nhóm máy chủ.
- Kiểm tra sức khỏe node và ngừng gửi kết nối mới đến node lỗi.
- Định tuyến read/write hoặc chuyển request đến primary/replica theo quy tắc.
- Giám sát số client, số backend, thời gian chờ và mức sử dụng pool.

Không phải mọi proxy đều hiểu SQL. TCP load balancer có thể chỉ chuyển tiếp byte giữa hai đầu; DB-aware proxy hiểu giao thức hoặc một phần câu lệnh để quản lý connection, multiplexing và routing. Khả năng giữ trạng thái và xử lý lỗi phụ thuộc loại proxy, DBMS, driver và phiên bản.

### Proxy và connection pool trong ứng dụng

Ứng dụng cũng thường có connection pool ở phía driver. Hai tầng có thể cùng tồn tại:

1. Request mượn một logical connection từ pool ứng dụng.
2. Driver gửi câu lệnh qua frontend connection đến proxy.
3. Proxy cấp backend connection phù hợp cho request hoặc transaction.
4. Khi đơn vị công việc kết thúc, backend có thể được trả về pool proxy.
5. Logical connection ở ứng dụng vẫn có thể được giữ để tái sử dụng.

Pool ứng dụng và pool proxy giải quyết hai phạm vi khác nhau. Pool ứng dụng giới hạn số kết nối từ một tiến trình/service và giảm chi phí tạo connection ở client. Proxy quản lý số kết nối thực sự mở đến DB trên toàn bộ client. Nếu cấu hình hai tầng không phù hợp, ứng dụng có thể xếp hàng trong pool riêng trong khi proxy còn backend rảnh, hoặc proxy có thể tạo hàng đợi lớn dù mỗi ứng dụng có vẻ còn connection.

## 2. Ba kiểu pooling phổ biến

Các connection pooler thường cung cấp một số chế độ gắn backend với frontend:

| Chế độ | Backend được giữ đến khi nào? | Đặc điểm |
|---|---|---|
| Session pooling | Trong toàn bộ vòng đời frontend session | Giữ semantics session gần với kết nối trực tiếp; khả năng multiplexing thấp hơn |
| Transaction pooling | Trong một transaction; trả backend sau COMMIT/ROLLBACK | Cho phép nhiều client dùng luân phiên một backend ở các transaction khác nhau |
| Statement pooling | Trong một câu lệnh; trả backend sau mỗi statement | Multiplexing cao nhưng ràng buộc mạnh; không phù hợp transaction nhiều câu lệnh |

Tên gọi và chi tiết hỗ trợ có thể khác giữa sản phẩm. Không nên suy ra mọi proxy đều có đúng ba chế độ hoặc hành vi giống nhau.

### Session pooling

Trong session pooling, frontend client được gắn với một backend connection trong suốt phiên. Nếu ứng dụng chạy:

```sql
SET search_path TO app_schema;
CREATE TEMP TABLE request_items (...);
PREPARE find_item AS SELECT ...;
```

thì các lệnh tiếp theo trên cùng session có thể tiếp tục sử dụng trạng thái đó. Proxy ít có cơ hội tái sử dụng backend cho client khác khi frontend vẫn mở.

Ưu điểm:

- Tương thích tốt hơn với ứng dụng phụ thuộc trạng thái session.
- Temporary table, cursor, session variable và prepared statement có thể tồn tại theo vòng đời backend session như kết nối trực tiếp.
- Dễ giữ advisory lock hoặc thiết lập session trong nhiều câu lệnh.

Đổi lại, nếu ứng dụng giữ connection idle trong pool lâu, backend tương ứng có thể bị giữ dù không chạy SQL. Số backend cần thiết có thể tiến gần số frontend session đang được gắn.

### Transaction pooling

Trong transaction pooling, proxy cấp backend khi client bắt đầu transaction hoặc phát câu lệnh cần thực thi, rồi giữ backend đó đến khi transaction kết thúc. Sau COMMIT hoặc ROLLBACK, backend được trả về pool và có thể phục vụ client khác.

Ví dụ:

```sql
BEGIN;
SELECT balance FROM accounts WHERE account_id = :id FOR UPDATE;
UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :id;
COMMIT;
```

Các câu lệnh trong transaction phải chạy trên cùng backend để khóa, snapshot và thay đổi chưa commit được giữ đúng. Sau COMMIT, transaction tiếp theo trên cùng frontend connection có thể được cấp một backend khác.

Transaction pooling tăng khả năng multiplexing khi nhiều client giữ frontend connection nhưng chỉ một phần trong số đó đang thực hiện transaction. Nó cũng tạo ràng buộc: trạng thái session không tự động đi theo frontend client khi backend được đổi.

Một câu lệnh autocommit có thể được xem như một transaction riêng. Backend có thể chỉ được giữ trong lúc thực thi câu lệnh đó. Vì vậy, hai câu lệnh autocommit liên tiếp không được mặc định chạy trên cùng backend session.

### Statement pooling

Statement pooling trả backend sau từng statement. Chế độ này phù hợp với các thao tác độc lập, không cần transaction nhiều câu lệnh hoặc trạng thái session giữa các câu. Nó thường không cho phép BEGIN ... COMMIT nhiều statement như một transaction thông thường.

Statement pooling có thể tăng mức multiplexing, nhưng ứng dụng phải thiết kế theo từng statement độc lập và không dựa vào session state. Các tính năng như temporary table, cursor, session variable hoặc prepared statement phụ thuộc backend có thể không dùng được theo cách thông thường.

### Chọn chế độ theo semantics

Không chọn transaction pooling chỉ vì nó cho phép nhiều client hơn. Hãy lập danh sách các tính năng ứng dụng sử dụng:

- Nếu ứng dụng phụ thuộc nhiều trạng thái session kéo dài qua transaction, session pooling thường dễ tương thích hơn.
- Nếu phần lớn request dùng transaction ngắn, không phụ thuộc trạng thái session, transaction pooling thường tận dụng backend tốt hơn.
- Nếu mỗi statement độc lập và không cần transaction nhiều câu lệnh, statement pooling có thể phù hợp.

Một số proxy hỗ trợ pinning hoặc virtualization cho một số tính năng session. Khả năng này phải được xác nhận theo sản phẩm và phiên bản; không giả định mọi trạng thái đều được proxy mô phỏng.

## 3. Trạng thái session và trạng thái transaction

Điểm cốt lõi của pooling là phân biệt trạng thái gắn với backend session và trạng thái chỉ tồn tại trong một transaction.

### Trạng thái session

Trạng thái session thường tồn tại trên backend connection cho đến khi được thay đổi, reset hoặc session kết thúc. Ví dụ:

- Session variables hoặc biến người dùng.
- SET ROLE, search_path, schema mặc định, timezone, collation hoặc các session option.
- Temporary table và dữ liệu trong temporary table.
- Server-side prepared statement.
- Cursor hoặc portal phụ thuộc session.
- LISTEN/subscription hoặc notification state.
- Session-level advisory lock.
- Sequence/session function state như giá trị sinh ID gần nhất theo connection.
- Trạng thái package hoặc context trong một số DBMS.

Nếu proxy chuyển backend sang client khác mà không reset hoặc cô lập trạng thái, client mới có thể kế thừa giá trị của client trước. Nếu proxy giữ backend cho client cũ nhưng client nghĩ backend đã được đổi, câu lệnh có thể thất bại hoặc trả kết quả sai.

### Trạng thái transaction

Trạng thái transaction gắn với một giao dịch đang mở:

- Snapshot hoặc read view.
- Khóa hàng, khóa phạm vi và khóa ghi.
- Thay đổi chưa commit.
- Isolation level và transaction characteristics.
- Savepoint.
- Transaction-local setting.
- Transaction-scoped advisory lock.

Proxy ở transaction pooling phải giữ cùng backend trong suốt transaction. Nếu chuyển backend giữa các câu lệnh trong transaction, DB không còn thấy cùng một tập thay đổi, khóa và snapshot; tính nguyên tử và cô lập sẽ bị phá vỡ.

### Bảng phân biệt

| Tính năng | Phạm vi trạng thái thường gặp | Rủi ro khi dùng transaction pooling |
|---|---|---|
| BEGIN/COMMIT và khóa hàng | Transaction | Backend phải được giữ xuyên suốt transaction |
| SET LOCAL trong PostgreSQL | Transaction | An toàn hơn cho setting chỉ cần trong transaction; tự hết hiệu lực khi kết thúc |
| SET search_path ở cấp session | Session | Có thể mất hoặc rò trạng thái khi đổi backend |
| Temporary table | Session hoặc transaction tùy cách tạo/DBMS | Có thể không tồn tại trên backend của transaction kế tiếp |
| Session variable | Session | Có thể biến mất hoặc bị client khác nhìn thấy nếu không reset |
| Prepared statement phía server | Thường session | Có thể không tồn tại trên backend mới, trừ khi proxy hỗ trợ theo dõi/virtualization |
| Session advisory lock | Session | Có thể giữ backend hoặc khóa tồn tại ngoài transaction |
| Transaction advisory lock | Transaction | Gắn với transaction, phù hợp hơn nếu DBMS hỗ trợ |
| Cursor | Thường gắn session/transaction | Không nên tiếp tục fetch sau khi backend được trả về |
| LISTEN/subscription | Session | Cần giữ kết nối chuyên dụng hoặc cơ chế proxy hỗ trợ |

Phạm vi chính xác có thể khác theo DBMS và câu lệnh. Luôn kiểm tra tài liệu engine và proxy trước khi thay đổi pool mode.

## 4. Backend affinity và transaction pinning

Backend affinity là yêu cầu một client hoặc một đơn vị công việc tiếp tục sử dụng cùng backend connection. Trong session pooling, affinity tồn tại theo session. Trong transaction pooling, affinity thường tồn tại theo transaction. Một số proxy có thể pin client vào backend lâu hơn khi phát hiện trạng thái không thể multiplex an toàn.

### Vì sao cần pinning?

Proxy cần pinning khi ứng dụng dùng tính năng phụ thuộc session mà proxy không thể chuyển trạng thái sang backend khác. Ví dụ:

- Tạo temporary table rồi dùng lại ở transaction tiếp theo.
- Thiết lập session variable rồi đọc trong câu lệnh sau.
- Giữ cursor qua nhiều lần fetch.
- Dùng session-level lock.
- Thay đổi session setting không được proxy theo dõi hoặc reset.
- Dùng protocol-level prepared statement không được proxy quản lý.

Pinning giúp bảo toàn semantics nhưng giảm khả năng tái sử dụng backend. Nếu nhiều client bị pin trong thời gian dài, số backend khả dụng cho client khác giảm và pool wait có thể tăng.

### Pinning có thể không rõ ràng

Một ứng dụng có thể dùng thư viện ORM hoặc driver tự động tạo prepared statement, đặt session option hoặc tạo temporary table. Nhóm phát triển chỉ thấy một câu truy vấn, nhưng proxy có thể phải giữ backend lâu hơn dự kiến.

Khi chẩn đoán, cần xem:

- Tỷ lệ client được pin và lý do pin nếu proxy cung cấp metric.
- Backend connection gắn lâu với một frontend.
- Các lệnh SET, PREPARE, DEALLOCATE, CREATE TEMP, DECLARE CURSOR hoặc advisory lock.
- Cấu hình reset và danh sách tính năng được proxy hỗ trợ.
- Hành vi của driver, ORM và statement cache.

Không nên tắt pinning để tăng multiplexing trước khi biết tính năng nào đang phụ thuộc backend. Việc đó có thể biến một vấn đề hiệu năng thành lỗi dữ liệu hoặc lỗi giao dịch.

## 5. Cấu hình session an toàn trong transaction pooling

Nếu một setting chỉ cần trong một transaction, ưu tiên cách khai báo có phạm vi transaction thay vì thay đổi trạng thái session kéo dài.

### PostgreSQL SET LOCAL

Ví dụ:

```sql
BEGIN;
SET LOCAL search_path = app_schema;
SET LOCAL statement_timeout = '2s';

SELECT *
FROM orders
WHERE order_id = :order_id;
COMMIT;
```

SET LOCAL có hiệu lực trong transaction hiện tại và tự trở về trạng thái trước đó khi transaction kết thúc. Điều này phù hợp hơn với transaction pooling khi setting chỉ cần trong một đơn vị công việc. Cần xác nhận setting cụ thể cho phép dùng SET LOCAL và thứ tự câu lệnh phù hợp.

### SQL Server và MySQL

Một số session option có thể được đặt ở cấp connection hoặc session. Nếu proxy có cơ chế reset khi trả backend, cần biết chính xác option nào được reset. Nếu không, hãy dùng cú pháp transaction-scoped hoặc truyền tham số ngay trong câu lệnh khi DBMS hỗ trợ.

Không giả định rằng rollback tự reset mọi session variable, temporary object hoặc SET option. ROLLBACK kết thúc transaction nhưng session state có thể vẫn còn.

### Tránh phụ thuộc vào giá trị phiên trước

Một backend có thể được tái sử dụng cho client khác. Mọi logic cần thiết phải được thiết lập tường minh trong đúng phạm vi:

- Đặt tenant_id trong predicate hoặc security context được DB/proxy bảo vệ.
- Đặt role hoặc schema theo cơ chế transaction-local nếu hỗ trợ.
- Truyền timezone, locale và các giá trị nghiệp vụ thành tham số rõ ràng.
- Không giả định session variable đã được thiết lập bởi request trước.
- Không dùng giá trị last-insert-id từ một connection khác.

Điều này cũng giúp kiểm thử và tái hiện lỗi dễ hơn vì kết quả không phụ thuộc lịch sử sử dụng backend.

## 6. Temporary table, cursor và prepared statement

Đây là các tính năng dễ tạo khác biệt giữa kết nối trực tiếp và transaction pooling.

### Temporary table

Temporary table thường thuộc về DB session. Nếu transaction đầu tạo temporary table rồi commit, transaction tiếp theo có thể được cấp backend khác và không thấy bảng đó. Nếu backend cũ được tái sử dụng cho client khác, bảng tạm hoặc dữ liệu còn lại có thể gây va chạm hoặc rò dữ liệu nếu không được dọn đúng.

PostgreSQL có thể tạo temporary table với ON COMMIT DROP hoặc ON COMMIT DELETE ROWS:

```sql
BEGIN;
CREATE TEMP TABLE request_ids (
    id BIGINT PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO request_ids (id)
VALUES (101), (102), (103);

SELECT o.*
FROM orders AS o
JOIN request_ids AS r ON r.id = o.order_id;
COMMIT;
```

ON COMMIT DROP làm bảng tạm bị xóa khi transaction commit. Mẫu này có thể phù hợp nếu bảng chỉ được dùng trong một transaction và proxy giữ backend suốt transaction. Cú pháp và hành vi tương đương khác nhau giữa DBMS; cần kiểm tra cụ thể.

Nếu cần chia sẻ tập khóa qua nhiều transaction, cân nhắc CTE, table-valued parameter, bảng staging bền vững có job_id/tenant_id và cleanup rõ ràng, hoặc cơ chế bulk input của driver.

### Cursor và streaming

Cursor thường phụ thuộc session hoặc transaction. Nếu ứng dụng mở cursor, commit rồi tiếp tục fetch trong transaction sau, backend mới có thể không biết cursor đó. Một số DBMS hỗ trợ holdable cursor, nhưng vẫn cần xem proxy có duy trì affinity hay không.

Streaming result cũng có thể giữ backend bận cho đến khi client đọc hết hoặc đóng result set. Nếu ứng dụng xử lý từng hàng lâu trong khi giữ cursor, backend connection bị chiếm và giảm pool capacity.

Hãy:

- Đọc kết quả trong thời gian hợp lý.
- Đóng cursor/result set khi không còn dùng.
- Tránh giữ transaction mở trong lúc client xử lý dữ liệu chậm.
- Dùng pagination/keyset hoặc chia batch nếu tập kết quả lớn.
- Kiểm tra giới hạn cursor của proxy và driver.

### Prepared statement

Prepared statement có thể được quản lý ở hai lớp:

- Client-side statement cache: driver lưu metadata hoặc câu lệnh đã chuẩn bị ở phía ứng dụng.
- Server-side prepared statement: DB tạo statement object gắn với session backend.

Trong transaction pooling, backend có thể đổi giữa hai transaction. Server-side statement đã tạo trên backend A không mặc nhiên tồn tại trên backend B. Một số proxy hiện đại có thể theo dõi và quản lý prepared statement theo khả năng riêng; hỗ trợ phụ thuộc phiên bản, cấu hình và giao thức.

Các lựa chọn:

- Dùng prepared statement được proxy hỗ trợ và cấu hình đúng.
- Dùng chế độ session pooling nếu ứng dụng phụ thuộc server-side state không thể virtualize.
- Tắt server-side statement cache trong driver nếu proxy không hỗ trợ, nhưng đo lại chi phí parse/plan.
- Tránh tự PREPARE rồi giả định statement sống qua nhiều transaction nếu backend có thể đổi.

Không tắt prepared statement cache một cách mặc định. Việc đó có thể làm tăng parse CPU và giảm hiệu năng; hãy xác minh tính tương thích trước.

## 7. Session variable, role và bảo mật tenant

Session variable thường được dùng để truyền tenant, user hoặc cấu hình ứng dụng. Trong mô hình proxy, cần biết biến được lưu ở frontend, proxy hay backend.

Ví dụ không an toàn nếu backend có thể được tái sử dụng:

```sql
SET app.tenant_id = 'tenant-A';
-- transaction kết thúc, backend được trả về pool
```

Nếu trạng thái này không được reset, request tiếp theo có thể kế thừa tenant-A. Nếu proxy đổi backend, câu lệnh sau có thể không còn thấy biến đã đặt. Cả hai trường hợp đều nguy hiểm.

### Truyền tenant an toàn

Ưu tiên:

- Đưa tenant_id thành tham số trong predicate SQL.
- Dùng Row-Level Security hoặc policy DB có context được thiết lập và reset theo cơ chế được kiểm chứng.
- Dùng transaction-local setting nếu DBMS và proxy hỗ trợ.
- Thiết lập context ngay sau khi bắt đầu transaction và xóa/reset trước khi kết thúc nếu cần.
- Kiểm thử hai tenant dùng luân phiên cùng backend để phát hiện rò state.

Ví dụ PostgreSQL với setting transaction-local và RLS cần được triển khai theo policy cụ thể:

```sql
BEGIN;
SET LOCAL app.tenant_id = 'tenant-A';

SELECT *
FROM tenant_documents;
COMMIT;
```

Policy RLS phải đọc context theo cách phù hợp và từ chối mặc định khi context thiếu hoặc không hợp lệ. Không coi một biến session do client tùy ý đặt là danh tính đáng tin cậy nếu người dùng có thể tự thay đổi nó.

### Role và search_path

SET ROLE, SET search_path và schema mặc định có thể ảnh hưởng quyền hoặc cách phân giải tên bảng. Nếu các setting tồn tại qua lần mượn backend, chúng có thể gây truy cập sai schema hoặc quyền ngoài dự kiến.

Hãy đặt role/schema trong phạm vi transaction nếu DBMS hỗ trợ, dùng tên schema rõ ràng trong SQL khi phù hợp, và xác nhận proxy reset đúng trạng thái. Không dựa vào search_path hoặc default schema do request trước thiết lập.

## 8. Advisory lock, LISTEN/NOTIFY và session-level features

Một số tính năng được thiết kế gắn với session lâu dài:

- PostgreSQL session-level advisory lock tồn tại cho đến khi được unlock hoặc session kết thúc.
- Transaction-level advisory lock được giải phóng khi transaction kết thúc.
- LISTEN đăng ký nhận notification trên session.
- Cursor hoặc subscription có thể tồn tại qua nhiều statement.
- Một số DBMS có package state hoặc context gắn với session.

Với transaction pooling, ưu tiên cơ chế transaction-scoped nếu nghiệp vụ chỉ cần khóa trong một transaction. PostgreSQL cung cấp pg_advisory_xact_lock cho khóa tự giải phóng khi transaction kết thúc:

```sql
BEGIN;
SELECT pg_advisory_xact_lock(:lock_key);

UPDATE inventory
SET reserved = reserved + :quantity
WHERE item_id = :item_id;
COMMIT;
```

Nếu cần session-level advisory lock hoặc LISTEN lâu dài, dùng kết nối chuyên dụng/session pooling hoặc một thành phần quản lý riêng có lifecycle rõ ràng. Không để một listener cạnh tranh backend với các request transaction ngắn.

## 9. Reset backend trước khi tái sử dụng

Khi trả backend về pool, proxy có thể chạy lệnh reset để đưa session về trạng thái sạch. Mục tiêu là tránh trạng thái của client trước ảnh hưởng client sau.

Reset có thể cần xử lý:

- Transaction chưa kết thúc.
- SET option và session variables.
- Temporary table và temporary object.
- Prepared statement.
- Cursor/portal.
- Advisory lock.
- Role, schema và authorization context.
- LISTEN/subscription hoặc session package state.
- Các resource khác do DBMS hoặc extension tạo.

### Reset toàn phần và reset chọn lọc

Reset toàn phần có thể an toàn hơn nhưng tốn CPU và thời gian, đồng thời có thể xóa các đối tượng mà ứng dụng muốn tái sử dụng. Reset chọn lọc nhanh hơn nhưng dễ bỏ sót trạng thái ít phổ biến.

Ví dụ PostgreSQL có DISCARD ALL để loại bỏ nhiều trạng thái session, nhưng lệnh này không thể chạy bên trong transaction block và có giới hạn riêng. Một pooler có thể cấu hình reset query phù hợp với chế độ pooling. Hãy kiểm tra tài liệu của phiên bản pooler, vì một số reset query chỉ chạy trong session pooling hoặc chỉ chạy khi được bật.

Không tự chạy DISCARD ALL sau mỗi transaction trong ứng dụng mà không hiểu chi phí và trạng thái cần giữ. Cấu hình reset thuộc về kiến trúc pooler và phải được thử nghiệm cùng driver.

### Rollback không phải reset session

ROLLBACK hủy thay đổi chưa commit và kết thúc transaction hiện tại. Nó không nhất thiết:

- Xóa mọi temporary table.
- Xóa session variable.
- Hủy mọi prepared statement.
- Hủy session advisory lock.
- Đặt lại role hoặc search_path.
- Hủy LISTEN.

Vì vậy, cần tách hai việc: bảo đảm transaction được kết thúc đúng cách và bảo đảm backend session được reset theo hợp đồng của pooler.

### Reset thất bại

Nếu reset command thất bại, proxy nên loại bỏ backend hoặc đánh dấu không thể tái sử dụng theo cơ chế sản phẩm. Nếu vẫn trả backend chưa sạch cho client khác, rủi ro state leak tăng. Theo dõi reset error, backend close/reconnect và tỷ lệ session bị loại khỏi pool.

## 10. Transaction phải được giữ nguyên trên một backend

Trong transaction pooling, proxy phải bảo đảm tất cả statement của một transaction chạy trên cùng backend. Đây là yêu cầu về tính nguyên tử và nhất quán, không phải tối ưu tùy chọn.

Ví dụ:

```sql
BEGIN;
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;
COMMIT;
```

Hai UPDATE và COMMIT phải cùng một backend. Nếu proxy đổi backend sau câu UPDATE đầu tiên, câu thứ hai có thể không nhìn thấy thay đổi chưa commit hoặc không thuộc transaction ban đầu.

### Autocommit và nhiều statement

Khi autocommit bật, mỗi statement thường là transaction riêng theo semantics DBMS. Nếu ứng dụng cần nhiều câu lệnh cùng nguyên tử, phải mở transaction rõ ràng. Không giả định việc gửi nhiều statement trong một lần gọi API luôn tạo một transaction duy nhất; driver và DBMS có thể xử lý khác nhau.

### Savepoint

Savepoint là trạng thái transaction. Các lệnh SAVEPOINT, ROLLBACK TO SAVEPOINT và RELEASE SAVEPOINT phải chạy trên cùng backend trong transaction tương ứng. Không thể chuyển backend giữa các thao tác này.

### Transaction dài làm giảm multiplexing

Backend được giữ từ lúc transaction bắt đầu đến khi commit/rollback, kể cả khi client tạm không gửi SQL. Nếu ứng dụng chờ mạng hoặc xử lý CPU trong transaction, backend vẫn bị chiếm. Transaction pooling không giúp tái sử dụng backend trong lúc transaction đang mở.

Vì vậy, proxy có thể tăng tỷ lệ client/backend nhưng không loại bỏ nhu cầu rút ngắn transaction. Hãy đặt transaction boundary quanh phần đọc/ghi cần tính nguyên tử và không giữ transaction trong lúc chờ người dùng hoặc dịch vụ ngoài.

## 11. Routing giữa primary và replica

Một số proxy có thể định tuyến truy vấn đọc đến replica và ghi đến primary. Routing có thể dựa trên user, database, query rule, transaction read-only hoặc phân tích câu SQL. Khả năng chính xác phụ thuộc proxy.

Các ràng buộc:

- Transaction có ghi thường phải chạy trên primary.
- Các statement trong cùng transaction phải tuân theo một routing policy nhất quán.
- Đọc ngay sau ghi có thể cần read-your-writes; replica có độ trễ áp dụng log nên có thể trả dữ liệu cũ.
- Session state trên primary không tự xuất hiện trên replica.
- Một truy vấn có side effect hoặc gọi function ghi dữ liệu có thể không được nhận diện là read-only chỉ từ từ khóa SELECT.
- Temporary object hoặc prepared state thường không chia sẻ giữa các node.

### Read-your-writes

Ví dụ:

```sql
BEGIN;
UPDATE orders
SET status = 'PAID'
WHERE order_id = :order_id;
COMMIT;

SELECT status
FROM orders
WHERE order_id = :order_id;
```

Nếu SELECT được gửi ngay đến replica chưa áp dụng thay đổi, ứng dụng có thể thấy trạng thái cũ. Giải pháp có thể là đọc primary trong một khoảng thời gian, dùng consistency token/LSN nếu hệ thống hỗ trợ, hoặc đợi replica bắt kịp. Không nên giả định proxy tự bảo đảm read-your-writes nếu chưa bật và kiểm chứng tính năng đó.

### Session affinity khi routing

Một frontend session có thể được gắn với primary hoặc một replica vì trạng thái hoặc chính sách routing. Nếu proxy đổi node giữa các statement, các session variable, temporary table hoặc cursor có thể không tồn tại ở node mới. Hãy tách kết nối chuyên dụng cho listener, long-lived session hoặc workflow cần node affinity.

## 12. Failover và kết nối bị ngắt

Proxy có thể phát hiện node lỗi và ngừng gửi kết nối mới đến node đó. Tuy nhiên, failover không thể tự di chuyển một transaction đang chạy sang node khác với đầy đủ khóa, snapshot và thay đổi chưa commit.

Khi backend bị mất:

- Transaction đang chạy có thể bị rollback hoặc kết quả commit trở nên không rõ với client.
- Frontend connection có thể nhận lỗi, bị đóng hoặc cần reconnect.
- Prepared statement, temporary table và session state trên backend cũ mất.
- Connection pool cần loại bỏ backend lỗi và tạo kết nối mới.
- Ứng dụng có thể cần retry toàn bộ đơn vị công việc.

### Kết quả COMMIT không rõ

Nếu kết nối đứt đúng lúc gửi COMMIT, ứng dụng có thể không biết DB đã commit trước khi mất kết nối hay chưa. Không retry một thao tác không idempotent một cách mù quáng. Dùng idempotency key, transaction identifier hoặc bảng kết quả nghiệp vụ để xác định thao tác đã được áp dụng chưa.

### Retry phải theo ranh giới transaction

Nếu transaction bị lỗi giữa chừng, ứng dụng thường phải bắt đầu một transaction mới và thực hiện lại toàn bộ đơn vị nghiệp vụ. Không tiếp tục từ statement cuối trên backend khác nếu các statement trước thuộc transaction đã mất.

Retry cần:

- Phân loại lỗi có thể retry.
- Giới hạn số lần và dùng backoff có jitter.
- Bảo đảm thao tác idempotent hoặc có khóa chống lặp.
- Không retry validation error hoặc lỗi cấu hình vô hạn.
- Ghi log request ID, transaction, node và thời điểm failover.

## 13. PgBouncer và các ví dụ về hành vi proxy

PgBouncer là một connection pooler phổ biến cho PostgreSQL và cung cấp các chế độ session, transaction và statement pooling.

### Quan sát pool

Các lệnh quản trị PgBouncer thường dùng:

```sql
SHOW POOLS;
SHOW CLIENTS;
SHOW SERVERS;
SHOW STATS;
```

Ý nghĩa khái quát:

- SHOW POOLS: số client, backend, client đang chờ và trạng thái pool theo database/user.
- SHOW CLIENTS: trạng thái frontend connection.
- SHOW SERVERS: trạng thái backend connection.
- SHOW STATS: số transaction/query và thời gian chờ trung bình theo thống kê pool.

Tên cột và trường có thể thay đổi theo phiên bản. Dùng console quản trị PgBouncer và quyền phù hợp; đây không phải các câu SQL chạy trên database nghiệp vụ.

### Reset và prepared statement

PgBouncer có cấu hình reset query và hỗ trợ prepared statement phụ thuộc phiên bản/cấu hình. Trong transaction pooling, không nên giả định mọi session-level state đều được giữ hoặc tự động mô phỏng. Đọc tài liệu phiên bản đang triển khai để biết:

- Lệnh reset nào được chạy khi trả server.
- Reset query có chạy trong chế độ pooling hiện tại không.
- Prepared statement protocol được theo dõi/virtualize ra sao.
- Tính năng nào khiến client cần giữ server connection.
- Cách xử lý cancel, reconnect và server bị mất.

Nếu ứng dụng sử dụng SET, temporary table, LISTEN, cursor hoặc advisory lock, hãy kiểm thử từng tính năng trong đúng pool mode.

## 14. Proxy trong hệ MySQL và các dịch vụ quản lý

ProxySQL, cloud database proxy và các dịch vụ như RDS Proxy có cách quản lý multiplexing, session pinning, routing và reset riêng. Một số sản phẩm có thể nhận diện lệnh làm thay đổi session state và pin frontend vào backend; một số tính năng chỉ được hỗ trợ với một số phiên bản engine/driver.

### ProxySQL

ProxySQL quản lý hostgroup, connection pool và query rule cho MySQL. Có thể quan sát các bảng thống kê trong schema quản trị, chẳng hạn thống kê pool và processlist. Khi đánh giá multiplexing, cần xem:

- Số client connection so với backend connection.
- Số backend đang dùng và backend rảnh.
- Số request chờ.
- Query rule có định tuyến đúng primary/replica không.
- Tính năng session nào làm connection không thể multiplex.
- Lỗi reset và reconnect.

Tên bảng quản trị, cột và khả năng multiplexing thay đổi theo phiên bản. Hãy dùng tài liệu đúng bản đang cài.

### RDS Proxy và proxy được quản lý

Proxy được quản lý có thể tự động quản lý connection pool, health check và failover. Một số session state hoặc câu lệnh có thể khiến connection bị pin, làm giảm multiplexing. Hãy quan sát metric pinning và backend connection utilization nếu dịch vụ cung cấp.

Việc proxy quản lý kết nối không thay đổi semantics của transaction DB. Transaction dài vẫn giữ backend; failover vẫn có thể làm transaction đang chạy thất bại; session state chỉ được hỗ trợ trong phạm vi sản phẩm công bố.

### Oracle DRCP và connection pooling

Oracle Database Resident Connection Pooling (DRCP) cho phép chia sẻ server process/session qua connection broker theo cơ chế của Oracle. Connection class và thuộc tính purity giúp xác định session có thể được tái sử dụng với mức trạng thái nào. Một số client-side pool của Oracle còn hỗ trợ session tagging và callback để kiểm tra hoặc thiết lập lại trạng thái khi mượn session; cần phân biệt tính năng của client pool với cơ chế DRCP phía database.

DRCP có semantics và cấu hình khác proxy TCP/SQL-aware. Cần hiểu session purity, connection class, cách reset trạng thái và hành vi driver trước khi tối ưu số session.

## 15. Đo hiệu năng proxy và connection pool

Để biết proxy có giúp hệ thống hay không, cần đo cả hai phía frontend/backend và độ trễ end-to-end.

### Chỉ số frontend

- Tổng client connection.
- Client active, idle và đang chờ backend.
- Thời gian chờ lấy backend (pool wait/acquire wait).
- Số client bị giới hạn hoặc từ chối.
- Connection churn, reconnect và authentication latency.

### Chỉ số backend

- Tổng backend connection và số backend đang dùng/rảnh.
- Tỷ lệ sử dụng pool theo database/user/hostgroup.
- Backend connection lifetime và số lần tạo mới.
- Backend transaction age.
- Session bị pin và lý do pin nếu có.
- Reset failure, server disconnect và health-check failure.

### Chỉ số DB

- Active session, transaction đang mở và idle in transaction.
- CPU, I/O, memory, worker và lock wait.
- Throughput transaction/query.
- Commit latency, log/WAL và replication lag.
- Số session vượt giới hạn hoặc chờ tài nguyên.

### Chỉ số ứng dụng

- Thời gian acquire connection từ pool ứng dụng.
- Connection hold time.
- Transaction duration.
- Query latency p50/p95/p99.
- Request timeout, retry và lỗi kết nối.
- Số request đang chờ trong worker/thread pool.

Không dùng riêng tỷ lệ frontend/backend để kết luận proxy hiệu quả. Một proxy có tỷ lệ multiplexing cao nhưng pool wait dài hoặc p99 tăng vẫn có thể làm trải nghiệm xấu hơn.

## 16. Dùng định luật Little để ước lượng nhu cầu backend

Định luật Little cho một hệ thống ổn định:

```text
L = λ × W
```

Trong đó L là số công việc trung bình đang ở trong phạm vi đo, λ là throughput và W là thời gian trung bình công việc chiếm tài nguyên.

Giả sử hệ thống thực hiện 80 transaction mỗi giây:

| Thời gian giữ backend trung bình | Backend đang bận trung bình ước tính |
|---:|---:|
| 100 ms | 8 |
| 250 ms | 20 |
| 500 ms | 40 |
| 1.000 ms | 80 |

Nếu proxy chỉ có 50 backend connection khả dụng cho pool đó, mức 1 giây giữ backend vượt năng lực pool trong điều kiện throughput 80 transaction/giây. Hàng đợi sẽ hình thành hoặc request bị timeout. Giảm thời gian giữ backend từ 1 giây xuống 250 ms làm nhu cầu trung bình giảm từ khoảng 80 xuống 20 backend, nếu throughput và phạm vi đo giữ nguyên.

Ước lượng này dùng thời gian backend bị chiếm, không chỉ thời gian SQL CPU. Transaction mở nhưng đang chờ ứng dụng vẫn giữ backend trong transaction pooling. Cần đo phân bố và burst vì trung bình không phản ánh đỉnh tải hoặc p99.

### Phân biệt các khoảng thời gian

- Pool acquire time: thời gian chờ proxy cấp backend.
- Backend hold time: thời gian backend bị gắn với client.
- SQL execution time: thời gian DB thực thi câu lệnh.
- Transaction duration: thời gian từ BEGIN đến COMMIT/ROLLBACK.
- Request duration: toàn bộ thời gian xử lý request ở ứng dụng.

Nếu backend hold time lớn hơn nhiều SQL execution time, có thể transaction chứa khoảng chờ ứng dụng hoặc thời gian đọc kết quả dài. Nếu acquire time cao nhưng backend utilization thấp, kiểm tra phân pool, giới hạn user/database, routing hoặc backend health. Nếu backend utilization cao và hold time dài, rút ngắn transaction và xử lý pinning trước khi chỉ tăng pool size.

## 17. Thiết kế transaction ngắn để tận dụng proxy

Một transaction ngắn giúp backend quay lại pool sớm:

```sql
BEGIN;

SELECT quantity
FROM inventory
WHERE item_id = :item_id
FOR UPDATE;

UPDATE inventory
SET quantity = quantity - :requested
WHERE item_id = :item_id
  AND quantity >= :requested;

COMMIT;
```

Đây là ví dụ rút gọn; ứng dụng phải kiểm tra số hàng cập nhật và xử lý trường hợp không đủ tồn kho trong cùng transaction. Không gọi dịch vụ ngoài, chờ người dùng hoặc xử lý file giữa lúc khóa hàng và commit.

### Đọc ngoài transaction, xác minh trong transaction

Nếu có bước tính toán hoặc gọi dịch vụ bên ngoài, có thể thực hiện trước transaction rồi bắt đầu transaction ngắn để đọc lại phiên bản và xác minh điều kiện:

1. Đọc dữ liệu cần thiết và version.
2. Thực hiện công việc ngoài DB.
3. Bắt đầu transaction.
4. Cập nhật có điều kiện theo version.
5. Nếu không cập nhật được, đọc lại và xử lý conflict.
6. Commit.

Mẫu này cần được kiểm tra theo invariant nghiệp vụ. Không chuyển bước ra ngoài transaction nếu kết quả đó phải được bảo vệ nguyên tử với thay đổi DB.

### Tránh giữ connection khi không cần

- Lấy connection muộn, ngay trước khi cần truy cập DB.
- Trả connection sau khi hoàn thành đơn vị công việc.
- Đóng result set/cursor sớm.
- Không giữ transaction mở trong khi xử lý dữ liệu ở ứng dụng.
- Dùng batch hoặc pagination cho kết quả lớn.
- Đặt timeout hợp lý cho acquire, statement và transaction.

## 18. Cấu hình pool và giới hạn tài nguyên

Pool size cần cân bằng giữa khả năng xử lý đồng thời, tài nguyên DB và hàng đợi. Cấu hình quá nhỏ làm acquire wait tăng; cấu hình quá lớn làm DB chịu quá nhiều session và tăng contention.

Các giới hạn cần xét:

- Max client connections ở proxy.
- Backend pool size theo database/user/hostgroup.
- Tổng backend tối đa trên tất cả pool.
- Giới hạn connection của DB và phần dự phòng cho admin/replication/job.
- Pool size của từng instance ứng dụng.
- Số replica và cách phân phối kết nối.
- Số transaction dài và tỷ lệ session bị pin.

Một proxy có thể tạo pool riêng theo cặp database/user. Vì vậy, tổng backend thực tế có thể là tổng của nhiều pool chứ không phải một giới hạn duy nhất. Cần tính tổng trên toàn proxy và toàn cụm.

### Backpressure và queueing

Khi backend pool đầy, proxy có thể xếp hàng client. Queue có giới hạn giúp bảo vệ DB khỏi số session quá lớn, nhưng nếu hàng đợi quá dài, request sẽ timeout ở tầng ứng dụng. Nên:

- Đặt giới hạn queue và acquire timeout theo SLO.
- Từ chối sớm khi không thể xử lý trong thời hạn.
- Điều tiết request nền để ưu tiên request tương tác.
- Theo dõi queue age và p95/p99 acquire time.
- Không tăng pool size nếu DB đã bão hòa CPU/I/O hoặc khóa nóng.

Backpressure cần lan truyền rõ ràng đến ứng dụng để retry có kiểm soát. Retry ngay lập tức trên hàng đợi đầy có thể làm tải tăng thêm.

## 19. Lỗi phổ biến khi chuyển từ direct connection sang proxy

### Session state biến mất

Ứng dụng đặt SET hoặc tạo temporary table trong một transaction, sau đó dùng lại ở transaction tiếp theo. Backend mới không có state cũ nên câu lệnh thất bại hoặc dùng default khác. Cách xử lý: chuyển state sang transaction-local, đặt lại trong từng transaction hoặc dùng session pooling cho phần cần affinity.

### Session state rò giữa client

Backend được tái sử dụng nhưng reset không đầy đủ. Client sau kế thừa role, schema, timezone, tenant context hoặc biến phiên của client trước. Cách xử lý: reset/cleanup đã kiểm chứng, thiết lập context tường minh và kiểm thử luân phiên nhiều client trên cùng backend.

### Transaction bị chia qua nhiều backend

Proxy hoặc ứng dụng dùng chế độ statement pooling cho workflow nhiều câu lệnh. Các câu lệnh không còn cùng transaction. Cách xử lý: dùng transaction pooling hoặc session pooling phù hợp và xác nhận transaction affinity.

### Prepared statement không tồn tại trên backend mới

Driver cache server-side statement theo session, nhưng proxy cấp backend khác. Cách xử lý: bật cơ chế hỗ trợ prepared statement của proxy, điều chỉnh driver cache hoặc chọn pool mode phù hợp sau khi đo.

### Backend bị pin quá nhiều

Một tính năng session làm proxy không thể trả backend về pool. Số backend bận tăng dù SQL activity thấp. Cách xử lý: tìm lý do pin, rút ngắn session feature hoặc tách workload cần affinity sang pool riêng.

### Transaction mở lâu

Ứng dụng chờ HTTP hoặc xử lý CPU giữa các câu SQL. Backend bị giữ dù không có truy vấn đang chạy. Cách xử lý: rút ngắn transaction, dùng version check/outbox/workflow khi semantics cho phép.

### Read/write routing trả dữ liệu cũ

Truy vấn đọc sau ghi được gửi đến replica chưa bắt kịp. Cách xử lý: dùng primary cho read-your-writes hoặc cơ chế consistency token được hệ thống hỗ trợ.

### Failover làm request bị thực hiện hai lần

Client mất kết nối trong lúc commit và retry thao tác không idempotent. Cách xử lý: dùng idempotency key và xác minh trạng thái trước khi áp dụng lại.

## 20. Quy trình triển khai proxy an toàn

1. **Kiểm kê cách ứng dụng dùng session.** Tìm SET, session variable, temp table, cursor, prepared statement, advisory lock, LISTEN và connection-specific function.
2. **Kiểm kê transaction.** Xác định autocommit, BEGIN/COMMIT, savepoint, isolation level và các đoạn chờ ngoài DB.
3. **Xác định khả năng proxy.** Đọc tài liệu đúng phiên bản về pool mode, pinning, reset, prepared statement, routing và failover.
4. **Phân nhóm workload.** Tách request transaction ngắn khỏi listener, session dài, báo cáo streaming hoặc tác vụ cần affinity.
5. **Chọn pool mode.** Chọn session, transaction hoặc statement theo semantics, không chỉ theo tỷ lệ multiplexing.
6. **Thiết lập reset và timeout.** Bảo đảm rollback, reset, acquire timeout, idle timeout và health check phù hợp.
7. **Kiểm thử state isolation.** Cho nhiều client/tenant dùng luân phiên cùng backend và xác minh không mất hoặc rò trạng thái.
8. **Kiểm thử concurrency.** Chạy tải thực tế với transaction ngắn/dài, hot key, prepared statement và temporary object.
9. **Kiểm thử failover.** Ngắt backend trong truy vấn và tại thời điểm commit; xác minh lỗi, retry và idempotency.
10. **Đo trước/sau.** So sánh frontend/backend connection, pool wait, backend hold time, DB CPU/I/O, transaction latency và p95/p99.
11. **Triển khai theo giai đoạn.** Bắt đầu với một nhóm client hoặc workload, theo dõi pinning và lỗi rồi mở rộng.
12. **Có đường quay lại.** Giữ cấu hình direct/session pool hoặc phương án rollback đã kiểm thử nếu ứng dụng phụ thuộc tính năng chưa được proxy hỗ trợ.

## 21. Ví dụ thiết kế: API nhiều request ngắn và listener dài

Một ứng dụng có hai loại workload:

- API xử lý đơn hàng: mỗi request đọc/ghi trong transaction khoảng vài chục mili giây.
- Listener nhận notification và giữ kết nối liên tục để nhận sự kiện.

Nếu cả hai dùng chung transaction pool, listener có thể chiếm backend lâu hoặc phụ thuộc session feature mà transaction pooling không hỗ trợ. Có thể tách:

| Workload | Kết nối phù hợp | Lý do |
|---|---|---|
| API transaction ngắn | Transaction pooling | Backend được trả sau mỗi COMMIT/ROLLBACK |
| Listener LISTEN lâu dài | Session connection/pool riêng | Subscription gắn với session |
| Job báo cáo streaming | Pool riêng hoặc session affinity có giới hạn | Tránh chiếm backend API quá lâu |
| Tác vụ admin/migration | Kết nối quản trị riêng | Không bị giới hạn bởi pool ứng dụng thông thường |

Pool riêng giúp đặt giới hạn và ưu tiên độc lập. Listener vẫn cần reconnect và đăng ký LISTEN lại sau failover; ứng dụng phải xử lý notification có thể bị mất trong thời gian ngắt kết nối bằng cách đối chiếu trạng thái bền vững.

## 22. Checklist vận hành proxy

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Proxy là TCP pass-through hay DB-aware pooler? | Biết rõ khả năng hiểu protocol và SQL |
| Pool mode hiện tại là gì? | Session, transaction, statement hoặc chế độ riêng |
| Transaction có giữ cùng backend không? | Đã kiểm thử BEGIN/COMMIT và rollback |
| Ứng dụng có dùng session state không? | Có danh sách SET, temp table, cursor, prepared statement, lock và listener |
| State có được reset không? | Có kiểm thử state leak giữa hai client |
| Tính năng nào gây pinning? | Có metric hoặc log lý do pin |
| Backend hold time có gần transaction duration không? | Đã đo khoảng chờ ngoài DB |
| Pool wait có tăng không? | Có acquire latency, queue age và timeout |
| Routing có bảo đảm read-your-writes không? | Có chính sách primary/replica rõ ràng |
| Failover có thể làm kết quả commit không rõ không? | Có idempotency và retry toàn transaction |
| Tổng backend có nằm trong năng lực DB không? | Tính cả mọi pool và phần dự phòng |
| p95/p99 và throughput có cải thiện không? | Có baseline và phép đo cùng workload |

## 23. Những sai lầm thường gặp

- **Cho rằng frontend connection luôn gắn với một backend:** điều này chỉ đúng trong một số pool mode hoặc khi bị pin.
- **Dùng transaction pooling nhưng dựa vào session variable:** trạng thái có thể không tồn tại ở backend của transaction kế tiếp.
- **Cho rằng COMMIT reset toàn bộ session:** transaction kết thúc nhưng session state có thể còn.
- **Dùng temporary table qua nhiều transaction:** backend có thể thay đổi giữa các transaction.
- **Giữ cursor hoặc streaming result quá lâu:** backend bị chiếm dù DB ít CPU.
- **Tắt prepared statement cache mà không đo:** có thể tăng parse/plan CPU mà không giải quyết đúng nguyên nhân.
- **Bỏ pinning để tăng multiplexing:** có thể làm hỏng semantics của ứng dụng.
- **Tăng backend pool khi DB đã bão hòa:** làm tăng session, contention và context switching.
- **Định tuyến mọi SELECT đến replica:** có thể vi phạm read-your-writes hoặc gọi function có side effect.
- **Coi proxy có thể di chuyển transaction khi failover:** transaction đang chạy không thể được chuyển nguyên trạng sang backend khác.
- **Retry ngay sau lỗi kết nối:** có thể thực hiện trùng nếu COMMIT đã thành công.
- **Chỉ theo dõi tổng connection:** bỏ qua backend hold time, pool wait, pinning và transaction age.

## 24. Nguyên tắc ra quyết định

Connection proxy tăng khả năng chia sẻ backend connection bằng cách quyết định thời điểm cấp, giữ và trả backend. Session pooling giữ backend theo frontend session; transaction pooling giữ backend theo transaction; statement pooling chỉ giữ theo câu lệnh và giới hạn mạnh các workflow nhiều câu. Sự lựa chọn phải dựa trên cách ứng dụng dùng session state, transaction, prepared statement, temporary object và các tính năng gắn với kết nối.

Hãy kiểm kê trạng thái session, giữ mọi transaction trên cùng backend đến COMMIT/ROLLBACK, dùng transaction-local setting khi phù hợp, reset backend trước khi tái sử dụng và tách workload cần session affinity. Đo frontend/backend connection, pool wait, backend hold time, pinning, transaction age và p95/p99 để biết proxy có thực sự tăng hiệu quả hay chỉ chuyển hàng đợi sang một tầng khác.

Proxy không thay thế thiết kế transaction ngắn, idempotency hoặc quy tắc consistency. Một cấu hình tốt phải vừa tăng khả năng tái sử dụng kết nối, vừa ngăn rò trạng thái giữa client, bảo toàn transaction và xử lý rõ ràng khi routing hoặc failover thay đổi backend.
