# Database link và truy vấn đối tượng từ database khác trong Oracle

## 1. Database link dùng để làm gì?

Một hệ thống có thể chia dữ liệu trên nhiều Oracle Database vì lý do tổ chức, bảo mật, mở rộng, phân vùng theo khu vực hoặc do lịch sử triển khai. Ứng dụng đôi khi cần đọc dữ liệu ở database khác mà không phải sao chép toàn bộ dữ liệu về database hiện tại.

**Database link (DB link)** là một object trong Oracle cho phép session ở database local kết nối tới database remote và tham chiếu object từ xa trong SQL. Sau khi tạo link, câu truy vấn có thể đọc bảng remote bằng cú pháp `schema.table@database_link`.

Ví dụ:

```sql
SELECT customer_id, customer_name
FROM sales.customers@sales_link
WHERE status = 'ACTIVE';
```

Câu lệnh được gửi từ database local, nhưng bảng `SALES.CUSTOMERS` nằm ở database remote được xác định bởi `SALES_LINK`.

Database link thường được dùng để:
- Truy vấn dữ liệu tham chiếu nằm ở database khác.
- Kết hợp dữ liệu local và remote trong một câu SQL.
- Chuyển dữ liệu giữa hai database bằng `INSERT ... SELECT`.
- Gọi một số package/procedure ở database remote.
- Hỗ trợ báo cáo hoặc tích hợp giữa các hệ thống Oracle.

DB link giúp truy cập dữ liệu từ xa bằng SQL, nhưng tạo thêm phụ thuộc vào mạng, listener, service, credential và trạng thái database remote. Một câu SQL local có thể thất bại nếu remote database không truy cập được. Vì vậy, cần thiết kế quyền, hiệu năng, transaction và vận hành cẩn thận.

Bài học thuộc module **Database Engine Relational Oracle**, chương **Tích hợp phân tán**, tập trung vào **Database link và truy vấn đối tượng từ database khác**.

## 2. Mô hình kết nối local và remote

Khi session local dùng DB link, database local đóng vai trò khởi tạo kết nối đến database remote. Kết nối không được tạo từ máy tính chạy SQL Developer hoặc ứng dụng client trực tiếp đến remote database theo cách thông thường; chính database server local thực hiện kết nối ra ngoài.

```text
Ứng dụng / SQL Developer
          |
          | SQL có @sales_link
          v
Oracle Database LOCAL
          |
          | Oracle Net connection
          | credential theo DB link
          v
Oracle Database REMOTE
          |
          v
REMOTE_SCHEMA.REMOTE_TABLE
```

Các thành phần:
- **Local database:** nơi session đang kết nối và thực thi câu SQL ban đầu.
- **Database link:** object chứa thông tin định tuyến và kiểu xác thực tới remote database.
- **Oracle Net service name/connect descriptor:** xác định host, listener, port và service ở phía remote.
- **Remote database:** database đích.
- **Remote user:** danh tính được dùng để truy cập object từ xa.
- **Remote object:** table, view hoặc object khác được tham chiếu qua link.

### 2.1. Link được mở khi nào?

Thông thường, khi session local lần đầu sử dụng DB link, Oracle mở kết nối/session tới remote database. Kết nối remote có thể được giữ trong thời gian session local còn tồn tại để tái sử dụng.

Một session local có thể dùng nhiều DB link. Mỗi link có thể tạo kết nối tới một remote database khác nhau. Nếu nhiều session local cùng truy cập một link, remote database có thể nhận nhiều session tương ứng.

### 2.2. DB link không phải bản sao dữ liệu

DB link không tự đồng bộ hay sao chép dữ liệu. Khi truy vấn qua link, Oracle truy cập database remote theo thời điểm thực thi. Nếu remote database ngừng hoạt động hoặc mạng bị gián đoạn, truy vấn phụ thuộc link có thể thất bại.

Nếu cần dữ liệu local để truy vấn nhanh và giảm phụ thuộc runtime vào remote database, hãy đánh giá materialized view, ETL, replication hoặc cơ chế CDC thay vì dùng DB link cho mọi request.

## 3. Các loại database link

Oracle hỗ trợ một số phạm vi và kiểu xác thực của database link. Hai cách phân loại thường gặp là phạm vi sở hữu và danh tính remote được sử dụng.

### 3.1. Private database link

Private database link thuộc schema tạo link. Chỉ owner của link mới có thể sử dụng link đó theo quyền thông thường.

Ví dụ, user `APP_OWNER` tạo `SALES_LINK`; các schema khác không tự động dùng được link riêng này.

Ưu điểm:
- Phạm vi sử dụng hẹp.
- Mỗi ứng dụng/schema có thể có credential và quyền riêng.
- Dễ xác định owner chịu trách nhiệm.

Đây thường là lựa chọn phù hợp hơn cho tích hợp của một ứng dụng hoặc một schema.

### 3.2. Public database link

Public database link được tạo ở phạm vi toàn database và có thể được các user có quyền truy cập phù hợp sử dụng.

Ví dụ:

```sql
CREATE PUBLIC DATABASE LINK reporting_link
CONNECT TO report_reader IDENTIFIED BY "password_placeholder"
USING 'REPORTING_SERVICE';
```

Public link tiện cho nhiều schema dùng chung một endpoint, nhưng mở rộng phạm vi sử dụng và có thể khiến nhiều ứng dụng dùng chung một remote identity. Chỉ tạo khi có nhu cầu rõ ràng, owner vận hành và chính sách quyền phù hợp.

### 3.3. Fixed-user database link

Fixed-user link luôn kết nối tới remote database bằng một username được khai báo trong link.

Ví dụ:

```sql
CREATE DATABASE LINK sales_link
CONNECT TO sales_reader IDENTIFIED BY "password_placeholder"
USING 'SALES_SERVICE';
```

Dù local session đăng nhập bằng user nào được phép dùng private link, kết nối remote vẫn sử dụng danh tính `SALES_READER`.

Đây là mô hình thường gặp cho ứng dụng cần truy cập một tập object remote ổn định. Remote account nên chỉ có quyền cần thiết, ví dụ `SELECT` trên một số view thay vì quyền rộng trên schema.

### 3.4. Connected-user hoặc current-user database link

Connected-user link sử dụng danh tính người dùng hiện tại để xác thực ở remote database theo cơ chế Oracle hỗ trợ. Current-user link có thể khai báo rõ:

```sql
CREATE DATABASE LINK hr_link
CONNECT TO CURRENT_USER
USING 'HR_SERVICE';
```

Cách này phù hợp với kiến trúc có danh tính người dùng được quản lý thống nhất, chẳng hạn enterprise/global user và external authentication theo cấu hình Oracle. Nó không có nghĩa bất kỳ local username nào cũng tự động tồn tại và đăng nhập được ở remote database.

Cần kiểm tra cấu hình xác thực, directory/enterprise user, quyền và phiên bản Oracle trước khi chọn mô hình này.

### 3.5. Chọn loại link

| Nhu cầu | Lựa chọn thường cân nhắc |
|---|---|
| Chỉ một schema ứng dụng cần remote access | Private link |
| Nhiều schema thật sự cần dùng chung link | Public link, sau khi đánh giá rủi ro |
| Một remote service account chỉ đọc dữ liệu | Private fixed-user link |
| Cần giữ danh tính người dùng xuyên database | Current-user/enterprise authentication phù hợp |
| Cần cách ly quyền giữa các ứng dụng | Các private link và remote account riêng |

Không chọn public link chỉ vì dễ cấu hình. Phạm vi truy cập càng rộng thì việc kiểm soát, audit và rotation càng khó.

## 4. Điều kiện và quyền để tạo database link

User tạo private DB link cần system privilege `CREATE DATABASE LINK`. Tạo public link cần `CREATE PUBLIC DATABASE LINK`.

DBA có thể cấp quyền theo chính sách:

```sql
GRANT CREATE DATABASE LINK TO app_owner;
```

Để tạo public link:

```sql
GRANT CREATE PUBLIC DATABASE LINK TO integration_admin;
```

Không cấp quyền tạo public link cho mọi developer hoặc service account. Đây là quyền có thể tạo đường kết nối tới database khác và cần được quản lý như một quyền tích hợp hệ thống.

Ngoài quyền ở local database, cần chuẩn bị:
- Remote database đang hoạt động và có thể truy cập từ local database server.
- Listener đang lắng nghe đúng endpoint.
- Service name chính xác.
- Oracle Net naming/connect descriptor hợp lệ.
- Remote account tồn tại và chưa bị khóa/hết hạn.
- Remote account có quyền trên object cần truy vấn.
- Firewall/network policy cho phép kết nối từ host local tới remote listener.
- Cấu hình TLS/network encryption theo yêu cầu bảo mật.

## 5. Cấu hình Oracle Net cho database link

DB link sử dụng một connect string hoặc service name trong mệnh đề `USING`.

Ví dụ `USING 'SALES_SERVICE'` tham chiếu tới Oracle Net service name có thể phân giải trên máy chủ database local.

Một entry minh họa trong `tnsnames.ora`:

```text
SALES_SERVICE =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = sales-db.example.internal)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = salespdb.example.internal)
    )
  )
```

Các giá trị trên chỉ là ví dụ. Cần dùng hostname, port và service name thật của môi trường.

### 5.1. TNS alias được phân giải ở đâu?

Vì kết nối DB link được khởi tạo từ database server local, alias `SALES_SERVICE` cần được phân giải trong môi trường Oracle Net mà database server local sử dụng. Một alias tồn tại trên máy developer nhưng không tồn tại hoặc không đúng trên máy database server sẽ không đủ để DB link hoạt động.

Kiểm tra:
- `TNS_ADMIN` hoặc vị trí cấu hình Oracle Net của database service.
- `tnsnames.ora` trên host local database.
- DNS/firewall từ local database host tới remote host.
- Listener và service registration ở remote.
- Cấu hình wallet/TLS nếu sử dụng.

### 5.2. Service name và PDB

Trong môi trường multitenant, service name có thể xác định PDB đích. Một DB link trỏ nhầm service có thể kết nối thành công nhưng truy cập sai container hoặc schema.

Hãy xác nhận service đích bằng một truy vấn nhận diện:

```sql
SELECT name, db_unique_name, open_mode
FROM v$database;
```

Truy vấn này chạy ở database remote qua link nếu user có quyền đọc view. Không có khoảng trắng giữa `@` và link name:

```sql
SELECT name, db_unique_name, open_mode
FROM v$database@sales_link;
```

Remote user có thể không có quyền đọc `V$DATABASE`; trong trường hợp đó dùng `GLOBAL_NAME` hoặc một view kiểm tra được cấp quyền.

### 5.3. Kiểm tra kết nối trước khi tạo link

DBA có thể dùng công cụ Oracle Net phù hợp trên host local để xác nhận alias và listener. Sau khi tạo link, truy vấn `DUAL` từ remote là phép thử đơn giản nhất.

Không kiểm tra chỉ từ máy client rồi kết luận database server local cũng kết nối được. Hai máy có thể có DNS, firewall hoặc Oracle Net configuration khác nhau.

## 6. Tạo private database link

Ví dụ tạo fixed-user private link trong schema `APP_OWNER`:

```sql
CREATE DATABASE LINK sales_link
CONNECT TO sales_reader
IDENTIFIED BY "password_placeholder"
USING 'SALES_SERVICE';
```

Trong ví dụ:
- `sales_link`: tên DB link local.
- `sales_reader`: remote username.
- `password_placeholder`: placeholder minh họa, không phải credential thật.
- `SALES_SERVICE`: Oracle Net service name của remote database.

Password trong DDL có thể xuất hiện trong script, SQL history, deployment output hoặc công cụ audit/log tùy cách thực thi. Khi triển khai thật, truyền credential qua kênh quản trị được bảo vệ, hạn chế lịch sử/output và không commit DDL chứa password vào repository.

Oracle lưu thông tin xác thực của fixed-user database link theo cơ chế bảo vệ của database; không thiết kế quy trình dựa trên việc truy vấn lại password plaintext từ dictionary.

### 6.1. Tạo link với current user

```sql
CREATE DATABASE LINK hr_link
CONNECT TO CURRENT_USER
USING 'HR_SERVICE';
```

Mô hình này chỉ hoạt động khi remote authentication và danh tính current user được cấu hình đúng. Không dùng nó như cách bỏ qua việc cấp account/privilege ở remote.

### 6.2. Tạo public link

```sql
CREATE PUBLIC DATABASE LINK shared_reporting_link
CONNECT TO report_reader
IDENTIFIED BY "password_placeholder"
USING 'REPORTING_SERVICE';
```

Public link được nhìn thấy ở phạm vi rộng hơn. Cần kiểm soát user nào có thể tham chiếu link và remote account có quyền gì.

### 6.3. Xác nhận link vừa tạo

```sql
SELECT db_link,
       username,
       host,
       created
FROM user_db_links
ORDER BY db_link;
```

View `USER_DB_LINKS` liệt kê link thuộc user hiện tại. Có thể dùng `ALL_DB_LINKS` hoặc `DBA_DB_LINKS` nếu có quyền để xem phạm vi tương ứng.

Các view metadata không hiển thị password plaintext. Hãy bảo vệ cả username, host và thông tin endpoint nếu chúng được phân loại là dữ liệu nhạy cảm trong tổ chức.

## 7. Kiểm tra database link

### 7.1. Truy vấn DUAL ở remote

```sql
SELECT 1
FROM dual@sales_link;
```

Nếu trả về một hàng, local session đã có thể mở link và thực hiện truy vấn remote cơ bản.

### 7.2. Kiểm tra global database name

```sql
SELECT *
FROM global_name@sales_link;
```

Kết quả giúp nhận diện global database name ở phía remote. Điều này hữu ích khi kiểm tra `GLOBAL_NAMES` hoặc lỗi link name không khớp.

### 7.3. Kiểm tra user remote

Có thể kiểm tra danh tính remote bằng:

```sql
SELECT USER
FROM dual@sales_link;
```

Với fixed-user link, kết quả thường là remote username được khai báo trong link. Đây là cách xác nhận link đang dùng đúng danh tính dự kiến.

### 7.4. Kiểm tra object remote

```sql
SELECT owner,
       table_name
FROM all_tables@sales_link
WHERE owner = 'SALES'
ORDER BY table_name;
```

View `ALL_TABLES` chỉ hiển thị object mà remote user có thể thấy theo quyền của họ. Nếu object không xuất hiện, kiểm tra owner, quyền và tên schema ở remote.

### 7.5. Kiểm tra service/container

Nếu remote database là CDB/PDB, xác nhận DB link tới đúng service và container. Một link kết nối thành công không có nghĩa nó đang trỏ tới đúng PDB nghiệp vụ.

## 8. Truy vấn đối tượng remote

Cú pháp chung:

```sql
object_name@database_link
```

Với schema-qualified object:

```sql
schema_name.object_name@database_link
```

Ví dụ:

```sql
SELECT order_id,
       customer_id,
       order_date,
       amount
FROM sales.orders@sales_link
WHERE order_date >= DATE '2026-01-01';
```

`SALES.ORDERS` nằm ở remote database. Predicate được gửi trong truy vấn phân tán và Oracle quyết định cách thực thi dựa trên optimizer, thống kê và khả năng xử lý từ xa.

### 8.1. Truy vấn view remote

```sql
SELECT customer_id,
       customer_name,
       customer_status
FROM sales.active_customers@sales_link;
```

Nếu remote user được cấp quyền trên view, có thể truy vấn view giống table. Dùng view để đóng gói logic và giới hạn cột có thể đơn giản hóa quyền truy cập.

### 8.2. Truy vấn metadata remote

```sql
SELECT owner,
       table_name,
       num_rows,
       last_analyzed
FROM all_tables@sales_link
WHERE owner = 'SALES';
```

Metadata trong data dictionary có thể không phản ánh toàn bộ object nếu remote user không có quyền. Khi cần quản trị, DBA remote nên cung cấp view hoặc báo cáo riêng có giới hạn.

### 8.3. Dùng alias cho remote object

```sql
SELECT o.order_id,
       o.amount
FROM sales.orders@sales_link o
WHERE o.status = 'OPEN';
```

Alias giúp câu SQL dễ đọc và hữu ích khi viết join hoặc hint optimizer. Trong query nhiều database, đặt alias rõ ràng để phân biệt object local và remote.

### 8.4. Remote synonym

Có thể tạo synonym local trỏ tới object remote:

```sql
CREATE SYNONYM remote_orders
FOR sales.orders@sales_link;
```

Sau đó truy vấn:

```sql
SELECT order_id, amount
FROM remote_orders
WHERE status = 'OPEN';
```

Synonym chỉ là tên thay thế. Nó không copy dữ liệu, không cấp quyền remote và không loại bỏ phụ thuộc vào DB link. Khi link hoặc remote object đổi, synonym có thể trở thành invalid hoặc không truy cập được.

## 9. Kết hợp dữ liệu local và remote

Một câu SQL có thể join object local với object remote:

```sql
SELECT c.customer_id,
       c.customer_name,
       o.order_id,
       o.amount
FROM app.customers c
JOIN sales.orders@sales_link o
  ON o.customer_id = c.customer_id
WHERE c.region_id = 10
  AND o.status = 'OPEN';
```

Oracle cần quyết định nơi thực hiện các phần của truy vấn và lượng dữ liệu cần truyền qua mạng.

### 9.1. Giảm dữ liệu truyền qua mạng

Các nguyên tắc thường giúp:
- Chỉ chọn cột thực sự cần.
- Lọc dữ liệu sớm bằng predicate có thể đẩy xuống remote.
- Aggregate ở remote nếu kết quả aggregate nhỏ hơn đáng kể.
- Tránh lấy toàn bộ bảng remote rồi join từng hàng ở local.
- Dùng view remote có logic ổn định và được tối ưu.
- Tránh gọi remote query lặp đi lặp lại trong vòng lặp PL/SQL.

Ví dụ, nếu chỉ cần tổng doanh số theo khách hàng, có thể để remote database tổng hợp trước:

```sql
SELECT r.customer_id,
       r.total_amount,
       c.customer_name
FROM app.customers c
JOIN (
    SELECT customer_id,
           SUM(amount) AS total_amount
    FROM sales.orders@sales_link
    WHERE order_date >= DATE '2026-01-01'
    GROUP BY customer_id
) r
  ON r.customer_id = c.customer_id;
```

Cấu trúc này thể hiện ý định chỉ chuyển kết quả tổng hợp từ remote. Tuy nhiên, việc optimizer thực sự đẩy operation xuống remote cần được xác nhận bằng execution plan.

### 9.2. Collocated inline view

Trong distributed query, nhóm operation có thể được thực hiện cùng tại một remote site để giảm lượng dữ liệu truyền. Oracle có thể biến đổi câu SQL để thực hiện một phần truy vấn tại remote database khi phù hợp.

Khi cần kiểm soát, DBA có thể nghiên cứu `DRIVING_SITE` hint và các kỹ thuật collocated inline view. Hint có thể làm thay đổi nơi điều khiển truy vấn; nó không phải giải pháp mặc định. Phải đo trên workload thật và xem SQL được gửi tới remote.

### 9.3. Tránh row-by-row remote call

Mẫu kém hiệu quả:

```text
FOR mỗi customer local:
    SELECT dữ liệu tương ứng FROM remote_table@link
```

Mỗi vòng lặp có thể tạo thêm network round trip. Với hàng nghìn customer, độ trễ mạng có thể chi phối toàn bộ thời gian.

Ưu tiên một câu distributed query, bulk operation hoặc staging batch để giảm số lần trao đổi.

### 9.4. Chú ý selectivity và statistics

Optimizer cần ước lượng số hàng local/remote. Statistics cũ, phân bố dữ liệu lệch hoặc predicate không sargable có thể dẫn đến plan truyền quá nhiều dữ liệu.

Đọc execution plan và so sánh số hàng thực tế nếu có runtime statistics. Không kết luận một join chậm chỉ vì có DB link; có thể vấn đề nằm ở remote index, cardinality estimate hoặc network latency.

## 10. Execution plan của distributed query

Dùng `EXPLAIN PLAN` để xem cấu trúc dự kiến:

```sql
EXPLAIN PLAN FOR
SELECT c.customer_id,
       o.order_id,
       o.amount
FROM app.customers c
JOIN sales.orders@sales_link o
  ON o.customer_id = c.customer_id
WHERE c.region_id = 10
  AND o.status = 'OPEN';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Plan có thể chứa operation `REMOTE` và phần thông tin SQL được gửi tới remote site. Tên operation và cách hiển thị phụ thuộc phiên bản.

Nếu câu SQL đã thực thi và runtime statistics được thu thập, xem cursor:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Cần quyền phù hợp để đọc cursor plan và runtime statistics.

### 10.1. Các câu hỏi khi đọc plan

- Có operation `REMOTE` ở đâu?
- Predicate nào được đẩy xuống remote?
- Có bao nhiêu hàng/bytes được truyền về local?
- Join được thực hiện tại local hay remote?
- Có full scan remote ngoài dự kiến không?
- Có sort hoặc aggregate lớn sau khi dữ liệu truyền về không?
- Có nhiều lần truy cập remote lặp lại không?
- Remote SQL có dùng index phù hợp không?

### 10.2. Kiểm tra ở cả hai database

Một distributed query có hai phía:
- Local plan cho biết cách database local điều phối.
- Remote SQL/plan cho biết công việc ở database remote.

Khi cần, DBA remote có thể tìm SQL tương ứng trong shared pool hoặc AWR/Statspack theo quyền và license. Kết hợp timestamp, SQL text, module/action và session information để tương quan hai phía.

## 11. DML qua database link

DB link không chỉ dùng để SELECT. Oracle hỗ trợ một số dạng DML trên remote object.

### 11.1. INSERT vào remote table

```sql
INSERT INTO sales.archive_orders@sales_link (
    order_id,
    customer_id,
    amount
)
SELECT order_id,
       customer_id,
       amount
FROM app.local_orders
WHERE archive_flag = 'Y';
```

Câu lệnh đọc dữ liệu local và ghi vào remote. Đây là thao tác cần kiểm soát transaction, quyền remote và số lượng dữ liệu.

### 11.2. INSERT từ remote vào local

```sql
INSERT INTO app.customer_stage (
    customer_id,
    customer_name
)
SELECT customer_id,
       customer_name
FROM sales.customers@sales_link
WHERE status = 'ACTIVE';
```

Cách này hữu ích cho staging hoặc ETL. Với khối lượng lớn, cần benchmark fetch/transfer, redo, undo, index maintenance và batch size.

### 11.3. UPDATE remote object

```sql
UPDATE sales.orders@sales_link
SET status = 'ARCHIVED'
WHERE order_date < DATE '2025-01-01';
```

Remote account cần quyền UPDATE phù hợp. Trước khi chạy, xác nhận predicate chọn đúng phạm vi và cân nhắc tác động tới workload remote.

### 11.4. DELETE remote object

```sql
DELETE FROM sales.staging_orders@sales_link
WHERE load_batch_id = :batch_id;
```

DML từ local session có thể tạo distributed transaction. Hãy xác định transaction đang sửa những database nào và có thể cần two-phase commit hay không.

### 11.5. MERGE và các giới hạn DML

Một số dạng `MERGE`, `RETURNING`, LOB, object type, trigger hoặc constraint có thể có giới hạn khi object nằm ở remote database. Khả năng hỗ trợ phụ thuộc cú pháp, phiên bản và cấu trúc statement.

Không giả định mọi câu DML chạy được trên table local đều chạy được qua DB link. Thử trên staging, đọc SQL Language Reference đúng release và xem lỗi thực tế trước khi triển khai.

## 12. Distributed transaction và two-phase commit

Khi một transaction thay đổi dữ liệu ở nhiều database, Oracle cần bảo đảm các participant đi đến kết quả commit nhất quán. Oracle sử dụng cơ chế **two-phase commit (2PC)** cho distributed transaction theo cấu hình và semantics hỗ trợ.

Ví dụ local transaction:
1. Cập nhật bảng local `APP.ORDERS`.
2. Cập nhật bảng remote `SALES.INVENTORY@SALES_LINK`.
3. Commit.

```sql
UPDATE app.orders
SET status = 'ALLOCATED'
WHERE order_id = :order_id;

UPDATE sales.inventory@sales_link
SET reserved_qty = reserved_qty + :qty
WHERE product_id = :product_id;

COMMIT;
```

Hai thao tác thuộc cùng transaction phân tán. Nếu một participant không thể hoàn tất, Oracle cần phối hợp để bảo đảm quyết định commit/rollback được xử lý theo protocol.

### 12.1. Hai pha

**Prepare phase:**
- Global coordinator yêu cầu các participant chuẩn bị commit.
- Mỗi participant bảo đảm có thể hoàn tất commit và ghi trạng thái cần thiết.
- Participant trả lời prepared/commit-ready hoặc báo lỗi.

**Commit phase:**
- Khi các participant đã sẵn sàng, coordinator thông báo commit.
- Nếu không thể commit theo quyết định giao dịch, coordinator điều phối rollback theo protocol.
- Các participant hoàn tất và giải phóng tài nguyên khi nhận quyết định.

Sơ đồ khái quát:

```text
Local transaction coordinator
          |
          | PREPARE
          +--------------------+
          |                    |
          v                    v
   Local database        Remote database
          |                    |
          +------ READY -------+
          |
          | COMMIT decision
          +--------------------+
          |                    |
          v                    v
   Commit local          Commit remote
```

Sơ đồ giản lược để minh họa. Transaction phân tán có thể có nhiều participant và coordinator/commit point theo cấu trúc thực tế.

### 12.2. Vì sao 2PC quan trọng?

2PC giúp tránh tình huống một database commit còn database khác rollback đối với cùng distributed transaction. Tuy nhiên, nó có chi phí:
- Thêm network round trips.
- Có thể giữ lock lâu hơn.
- Phụ thuộc tính sẵn sàng của các participant.
- Có thể tạo trạng thái in-doubt khi coordinator/participant mất liên lạc.
- Tăng độ phức tạp vận hành.

Không đưa DB link vào transaction nghiệp vụ nếu không thực sự cần cập nhật đồng thời nhiều database.

### 12.3. Read-only query và distributed commit

Một câu SELECT remote đơn thuần không đồng nghĩa với transaction đang cập nhật nhiều database. Two-phase commit chủ yếu liên quan transaction phân tán có thay đổi dữ liệu ở nhiều participant. Tuy vậy, distributed query vẫn phụ thuộc network/remote availability và có thể tiêu thụ tài nguyên ở cả hai phía.

## 13. In-doubt transaction và recovery

Nếu sự cố xảy ra trong quá trình 2PC, một participant có thể chưa nhận được quyết định cuối cùng. Transaction có thể xuất hiện trong trạng thái in-doubt.

Oracle có background recovery process như RECO để hỗ trợ tự động giải quyết distributed transaction khi kết nối và thông tin coordinator trở lại.

### 13.1. Kiểm tra giao dịch pending

DBA có thể xem:

```sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       fail_time,
       retry_time
FROM dba_2pc_pending
ORDER BY fail_time;
```

Thông tin participant:

```sql
SELECT local_tran_id,
       in_out,
       database,
       dbuser_owner,
       interface
FROM dba_2pc_neighbors
ORDER BY local_tran_id;
```

Các view yêu cầu quyền DBA và cột có thể khác theo phiên bản. Không tự xóa hoặc force transaction chỉ vì thấy một dòng pending.

### 13.2. RECO

RECO là process recovery cho distributed transaction. Khi lỗi mạng hoặc database được khôi phục, RECO có thể trao đổi với các participant để hoàn tất transaction theo quyết định đã ghi.

DBA cần kiểm tra:
- Remote database đã hoạt động chưa.
- Listener/service và network đã ổn định chưa.
- Transaction đang ở trạng thái nào.
- Coordinator và participant có cùng quyết định không.
- Alert log và trace có thông tin gì.

### 13.3. Không force commit/rollback tùy tiện

Các lệnh force resolution như `COMMIT FORCE` hoặc `ROLLBACK FORCE` chỉ dành cho DBA xử lý tình huống đặc biệt sau khi xác định quyết định toàn cục và tham khảo quy trình Oracle.

Force một participant theo phỏng đoán có thể tạo mixed outcome, tức các database không còn cùng kết quả nghiệp vụ. Cần lưu bằng chứng, xác định global transaction ID và phối hợp với DBA các participant trước khi xử lý thủ công.

## 14. Transaction boundary và lỗi khi remote database mất kết nối

Khi DML qua DB link gặp lỗi, không nên tiếp tục transaction như thể mọi thao tác trước đó đều đã hoàn tất.

Các nguyên tắc:
- Bắt exception và rollback transaction theo trạng thái/semantics được Oracle yêu cầu.
- Không tự commit một phần chỉ để bỏ qua remote error.
- Kiểm tra transaction pending nếu có lỗi 2PC.
- Không retry DML mù khi chưa xác định outcome.
- Dùng business key hoặc idempotency key nếu thao tác có thể được gửi lại.
- Ghi lại global transaction context và error code phù hợp, không log credential.

Một lỗi kết nối sau khi gửi COMMIT có thể làm client không biết kết quả cuối cùng. Đây là vấn đề tương tự transaction outcome ambiguity ở ứng dụng phân tán; cần có quy trình xác định trạng thái, không giả định mất phản hồi đồng nghĩa rollback.

## 15. Quản lý vòng đời database link

### 15.1. Xem link của schema hiện tại

```sql
SELECT db_link,
       username,
       host,
       created
FROM user_db_links
ORDER BY db_link;
```

### 15.2. Xem link mà user có thể truy cập

```sql
SELECT owner,
       db_link,
       username,
       host
FROM all_db_links
ORDER BY owner, db_link;
```

### 15.3. DBA xem toàn bộ link

```sql
SELECT owner,
       db_link,
       username,
       host,
       created
FROM dba_db_links
ORDER BY owner, db_link;
```

Các view metadata có thể không hiển thị toàn bộ thông tin theo quyền. Không tìm cách lấy password plaintext từ data dictionary.

### 15.4. Đóng kết nối DB link trong session

Có thể đóng kết nối remote của session hiện tại:

```sql
ALTER SESSION CLOSE DATABASE LINK sales_link;
```

Chỉ thực hiện khi không có transaction đang phụ thuộc link và theo đúng điều kiện Oracle. Khi link được dùng lại, Oracle có thể mở kết nối mới.

### 15.5. Xóa private link

```sql
DROP DATABASE LINK sales_link;
```

Lệnh này xóa private link thuộc schema hiện tại.

### 15.6. Xóa public link

```sql
DROP PUBLIC DATABASE LINK shared_reporting_link;
```

Đây là thay đổi ảnh hưởng tới mọi consumer dùng public link đó. Trước khi drop, inventory các schema, job và ứng dụng phụ thuộc.

### 15.7. Rotation credential

Fixed-user DB link gắn với remote credential. Khi remote password thay đổi, cần cập nhật link theo quy trình được hỗ trợ, thường là tạo lại link với credential mới sau khi đánh giá dependency.

Kế hoạch rotation cần:
1. Xác định mọi consumer của link.
2. Tạo/chuẩn bị remote credential mới hoặc cửa sổ chuyển tiếp phù hợp.
3. Cập nhật DB link bằng quy trình triển khai bảo mật.
4. Kiểm tra truy vấn remote bằng session mới.
5. Làm mới session cũ nếu chúng còn giữ remote connection.
6. Thu hồi credential cũ khi không còn consumer.

Không ghi password thật vào script, ticket hoặc log. Không thay credential remote trước khi biết các link và job nào đang sử dụng nó.

## 16. Bảo mật database link

DB link tạo một đường truy cập từ database local sang remote. Nếu credential có quyền quá rộng hoặc link bị lạm dụng, tác động có thể lan qua nhiều hệ thống.

### 16.1. Least privilege ở remote

Remote account chỉ nên được cấp:
- `SELECT` trên các view/bảng cần đọc nếu chỉ truy vấn.
- DML trên object cụ thể nếu thực sự cần ghi.
- Không cấp DBA hoặc `ANY` privilege cho tích hợp thông thường.
- Không dùng schema owner hoặc tài khoản quản trị làm remote identity.

Ưu tiên tạo remote view chỉ chứa cột cần thiết, sau đó cấp quyền trên view cho remote account.

### 16.2. Private link theo ứng dụng

Mỗi ứng dụng nên có private link và remote identity phù hợp. Tránh dùng một public link với tài khoản remote có quyền đọc toàn bộ schema cho mọi workload.

### 16.3. Bảo vệ credential

Credential trong DDL có thể lộ qua:
- Source control.
- SQL history.
- Script triển khai.
- Terminal transcript.
- CI/CD output.
- Audit hoặc log tùy cấu hình.

Dùng quy trình quản trị secret, hạn chế quyền tạo link và kiểm soát nơi lưu script. Oracle bảo vệ credential link trong metadata theo cơ chế riêng, nhưng điều đó không bảo vệ bản DDL chứa password mà đội triển khai đã lưu ở nơi khác.

### 16.4. Bảo vệ network

Kết nối local-to-remote cần được giới hạn:
- Firewall chỉ cho host/service cần thiết.
- Oracle Net encryption/integrity hoặc TLS theo chính sách.
- Kiểm tra certificate và wallet khi dùng TLS.
- Hạn chế listener exposure.
- Theo dõi kết nối và lỗi xác thực.
- Không cho database server kết nối tùy ý ra mọi endpoint.

### 16.5. Audit và truy vết

Nên ghi nhận:
- Schema sở hữu link.
- Remote username.
- Endpoint/service.
- Consumer nghiệp vụ.
- Owner và mục đích.
- Quyền remote được cấp.
- Ngày tạo/rotation gần nhất.
- Các thay đổi DDL và người thực hiện.

Không ghi password. Kết hợp audit database, network monitoring và application module/action để điều tra truy cập bất thường.

## 17. Tên database link và GLOBAL_NAMES

Tham số `GLOBAL_NAMES` điều khiển việc tên DB link có phải khớp global database name của database remote hay không.

Kiểm tra:

```sql
SHOW PARAMETER global_names;
```

Hoặc:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'global_names';
```

Nếu `GLOBAL_NAMES=TRUE`, tên link phải tuân thủ quy tắc global name của remote database. Nếu tên không khớp, có thể gặp lỗi `ORA-02085`.

Kiểm tra global name remote:

```sql
SELECT *
FROM global_name@sales_link;
```

Không đổi global name hoặc `GLOBAL_NAMES` chỉ để làm một link hoạt động mà chưa đánh giá tác động đến các link khác. Đặt tên theo quy ước rõ ràng và xác nhận database identity trước khi tạo link.

## 18. Hạn chế và kiểu dữ liệu khi truy cập remote

Distributed SQL có một số giới hạn khác SQL chỉ chạy trong một database. Các hạn chế phụ thuộc phiên bản, loại object và statement.

Cần đặc biệt kiểm tra:
- `LONG` và một số thao tác trên LOB.
- User-defined object types và collection.
- Remote temporary table.
- Một số phép join, subquery hoặc DML đặc biệt.
- Trigger, constraint và referential integrity giữa database.
- Một số câu lệnh `RETURNING` hoặc thao tác không hỗ trợ qua link.
- Remote procedure call và datatype mapping.
- Hành vi của materialized view hoặc object có dependency remote.

Không giả định foreign key local có thể trực tiếp bảo đảm integrity với bảng remote giống như hai bảng trong cùng database. Nếu cần ràng buộc nghiệp vụ xuyên database, phải thiết kế ở tầng tích hợp hoặc dùng transaction/distributed architecture phù hợp.

Với dữ liệu lớn hoặc kiểu dữ liệu đặc biệt, thử trên đúng Oracle release, driver và cấu trúc object trước khi triển khai.

## 19. Hiệu năng và độ sẵn sàng

### 19.1. Network latency

Mỗi lần trao đổi dữ liệu giữa local và remote đều chịu network latency. Query có nhiều round trip có thể chậm dù cả hai database đều có CPU và I/O dư.

Giảm round trip bằng cách:
- Gộp truy vấn.
- Dùng bulk fetch/bulk DML.
- Tránh gọi remote trong loop.
- Đưa filter/aggregate tới nơi có dữ liệu.
- Giới hạn số request đồng thời.

### 19.2. Remote database là dependency runtime

Nếu câu SQL của ứng dụng phụ thuộc DB link, remote outage có thể làm request local thất bại. Cần đặt timeout, giới hạn concurrency và phân loại lỗi remote.

Đối với nghiệp vụ không cần dữ liệu mới tuyệt đối ở từng request, có thể dùng cache, materialized view hoặc staging để giảm phụ thuộc đồng bộ.

### 19.3. Connection/session fan-out

Một lượng lớn local session cùng sử dụng DB link có thể tạo nhiều remote session. Điều này ảnh hưởng:
- Process/session limit ở remote.
- PGA/CPU remote.
- Network connection count.
- Connection setup overhead.
- Khả năng phục hồi sau outage.

Đặt giới hạn pool và concurrency ở local application/database, đồng thời theo dõi số remote session.

### 19.4. Chỉ truy vấn cột cần thiết

Tránh:

```sql
SELECT *
FROM sales.orders@sales_link;
```

nếu chỉ cần vài cột. Truyền dữ liệu không cần thiết làm tăng network, memory và thời gian xử lý.

### 19.5. Chọn nơi thực hiện join

Nếu phần lớn dữ liệu nằm ở remote, có thể đẩy join/filter/aggregate xuống remote để chỉ trả kết quả nhỏ. Nếu dữ liệu remote rất ít, truyền về local để join với tập local có thể hợp lý hơn.

Không có một site luôn tốt nhất. Xem plan, cardinality, network throughput và chi phí remote/local trước khi dùng hint điều khiển.

## 20. Troubleshooting các lỗi DB link thường gặp

| Mã lỗi | Nguyên nhân thường gặp | Hướng điều tra |
|---|---|---|
| `ORA-12154` | Không phân giải được connect identifier | Kiểm tra Oracle Net alias và cấu hình trên local database server |
| `ORA-12541` | Không có listener tại endpoint | Kiểm tra host/port, listener và firewall |
| `ORA-12514` | Listener không nhận diện service yêu cầu | Kiểm tra `SERVICE_NAME`, service registration và PDB |
| `ORA-01017` | Username/password không hợp lệ | Kiểm tra remote account, credential và trạng thái rotation |
| `ORA-28000` | Remote account bị khóa | Xử lý account/profile ở remote theo policy |
| `ORA-02019` | Không tìm thấy connection description | Kiểm tra `USING`, TNS alias và Oracle Net config |
| `ORA-02085` | Tên link không khớp global database name khi yêu cầu | Kiểm tra `GLOBAL_NAMES` và `GLOBAL_NAME` remote |
| `ORA-02049` | Timeout chờ distributed transaction lock | Kiểm tra transaction giữ lock, thời gian chờ và concurrency |
| `ORA-02068` | Có lỗi nghiêm trọng theo sau từ remote database | Đọc lỗi tiếp theo và alert/trace ở cả hai phía |
| `ORA-02055` | Distributed update thất bại, transaction cần rollback | Rollback theo yêu cầu, kiểm tra transaction state và participant |
| `ORA-03113` | Kênh kết nối bị đóng bất thường | Kiểm tra network, alert log và remote session |

Một mã lỗi có thể là triệu chứng của nhiều nguyên nhân. Luôn đọc toàn bộ error stack, bao gồm lỗi remote theo sau, và đối chiếu timestamp ở cả local lẫn remote.

### 20.1. Quy trình điều tra

1. Thử `SELECT 1 FROM dual@link`.
2. Xác nhận link metadata và remote username.
3. Xác nhận service name và global database name.
4. Kiểm tra network từ host local database.
5. Kiểm tra listener và service ở remote.
6. Kiểm tra remote account status và quyền object.
7. Xem local/remote alert log và listener log.
8. Kiểm tra transaction pending nếu lỗi xảy ra trong distributed DML/COMMIT.
9. Kiểm tra SQL plan và lượng dữ liệu truyền nếu vấn đề là performance.
10. Ghi nhận kết quả và thay đổi cấu hình để tránh tái diễn.

## 21. Lựa chọn DB link hay phương án tích hợp khác?

DB link phù hợp khi cần SQL truy cập trực tiếp dữ liệu remote với khối lượng và tần suất có thể kiểm soát. Nó không phải lựa chọn tối ưu cho mọi kiểu tích hợp.

| Nhu cầu | Phương án cần cân nhắc |
|---|---|
| Truy vấn tham chiếu trực tiếp giữa hai Oracle DB | Database link |
| Báo cáo lặp lại, chấp nhận dữ liệu trễ một khoảng | Materialized view |
| Chuyển dữ liệu theo lịch, khối lượng lớn | ETL/staging/Data Pump |
| Đồng bộ thay đổi liên tục | CDC/replication như Oracle GoldenGate theo kiến trúc |
| Giao tiếp nghiệp vụ qua API | Service/API layer |
| Tích hợp bất đồng bộ và chống phụ thuộc runtime | Message broker/event/outbox |
| HA/DR cho một database | Data Guard hoặc kiến trúc HA phù hợp |

### 21.1. Materialized view

Materialized view có thể lưu kết quả query remote ở local và refresh theo lịch hoặc cơ chế hỗ trợ. Điều này giảm truy cập remote trong từng request nhưng tạo độ trễ dữ liệu và cần quản lý refresh.

### 21.2. ETL và staging

Nếu cần chuyển hàng triệu bản ghi theo batch, ETL/staging có thể dễ kiểm soát retry, restart, audit và chất lượng dữ liệu hơn một query runtime kéo dài qua link.

### 21.3. API hoặc messaging

Nếu database remote thuộc một bounded context khác, API hoặc event integration có thể giữ quyền sở hữu dữ liệu rõ hơn và tránh để ứng dụng phụ thuộc trực tiếp vào schema bên kia.

DB link vẫn có thể là công cụ phù hợp cho một số tích hợp nội bộ, nhưng cần quản lý schema coupling và quyền truy cập.

## 22. Bài thực hành tổng hợp

Bài lab giả định có hai Oracle Database:
- Local database chứa schema `APP`.
- Remote database chứa schema `SALES`.
- Remote service được cấu hình trong Oracle Net của local database server dưới tên `SALES_SERVICE`.
- Remote account `SALES_READER` chỉ có quyền đọc một số object.

Không dùng password thật trong tài liệu hoặc source control. Thực hiện trên môi trường lab có quyền phù hợp.

### Bước 1. Chuẩn bị remote account và quyền

Trên remote database, DBA tạo account theo policy và cấp quyền tối thiểu. Ví dụ:

```sql
GRANT CREATE SESSION TO sales_reader;
GRANT SELECT ON sales.customers TO sales_reader;
GRANT SELECT ON sales.orders TO sales_reader;
```

Nếu remote account cần đọc view, cấp quyền trên view tương ứng thay vì cấp rộng trên schema.

### Bước 2. Kiểm tra Oracle Net từ local server

Xác nhận `SALES_SERVICE` phân giải đúng từ host database local và listener remote có service tương ứng.

### Bước 3. Tạo private link ở local

Trong schema ứng dụng:

```sql
CREATE DATABASE LINK sales_link
CONNECT TO sales_reader
IDENTIFIED BY "password_placeholder"
USING 'SALES_SERVICE';
```

Thay placeholder bằng credential được cấp qua quy trình bảo mật phù hợp trong môi trường lab.

### Bước 4. Kiểm tra link

```sql
SELECT 1
FROM dual@sales_link;

SELECT USER
FROM dual@sales_link;

SELECT *
FROM global_name@sales_link;
```

Xác nhận remote identity và database đích.

### Bước 5. Truy vấn remote table

```sql
SELECT customer_id,
       customer_name
FROM sales.customers@sales_link
WHERE status = 'ACTIVE';
```

### Bước 6. Truy vấn remote view hoặc synonym

```sql
CREATE SYNONYM active_customers_remote
FOR sales.active_customers@sales_link;
```

```sql
SELECT customer_id, customer_name
FROM active_customers_remote;
```

### Bước 7. Join local và remote

```sql
SELECT c.customer_id,
       c.customer_name,
       o.order_id
FROM app.customer_map c
JOIN sales.orders@sales_link o
  ON o.customer_id = c.remote_customer_id
WHERE c.region_id = 10;
```

### Bước 8. Xem execution plan

```sql
EXPLAIN PLAN FOR
SELECT c.customer_id,
       o.order_id
FROM app.customer_map c
JOIN sales.orders@sales_link o
  ON o.customer_id = c.remote_customer_id
WHERE c.region_id = 10;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Tìm operation `REMOTE`, predicate được đẩy xuống và ước lượng số hàng truyền qua mạng.

### Bước 9. Thử DML chỉ trong lab

Nếu remote account được cấp quyền ghi và lab cho phép, thử insert/update một bản ghi thử nghiệm. Xác định transaction có thay đổi local và remote hay không, sau đó commit hoặc rollback theo kịch bản.

Không thử distributed DML trên dữ liệu thật chỉ để kiểm tra kết nối.

### Bước 10. Kiểm tra metadata và dọn lab

```sql
SELECT db_link, username, host, created
FROM user_db_links;
```

Sau khi không còn session/transaction phụ thuộc:

```sql
DROP DATABASE LINK sales_link;
```

Dọn synonym hoặc object lab do bạn tạo theo dependency. Không xóa link dùng chung hoặc object nghiệp vụ.

## 23. Checklist trước khi đưa DB link vào production

### Kết nối và cấu hình
- TNS/service name được kiểm tra từ host local database.
- Remote listener/service đúng.
- Link trỏ đúng database/PDB.
- `GLOBAL_NAMES` được hiểu rõ.
- Có timeout/network policy phù hợp.
- Có kiểm thử sau failover/restart.

### Bảo mật
- Private link được ưu tiên khi đủ dùng.
- Public link có owner và lý do rõ.
- Remote account có least privilege.
- Không dùng DBA/schema owner cho ứng dụng.
- Credential không nằm trong source/log.
- Network encryption và firewall được cấu hình.
- Có audit và rotation plan.

### SQL và hiệu năng
- Chỉ truy vấn cột cần thiết.
- Predicate có thể push xuống remote.
- Không có remote call row-by-row ngoài dự kiến.
- Execution plan đã được xem ở local và remote khi cần.
- Số session remote được kiểm soát.
- Có timeout và giới hạn concurrency.
- Đã benchmark dữ liệu/latency đại diện.

### Transaction và vận hành
- Xác định transaction có cập nhật nhiều database không.
- Hiểu 2PC và xử lý in-doubt.
- Có quy trình rollback khi remote error.
- Không force resolve transaction khi chưa có quyết định toàn cục.
- Có runbook troubleshooting.
- Có phương án thay thế khi remote database outage.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Database link là gì?

**Trả lời:** Object cho phép session local kết nối tới database remote và tham chiếu object từ xa trong SQL bằng cú pháp `object@link`.

**Câu 2.** Private link khác public link thế nào?

**Trả lời:** Private link thuộc một schema; public link có phạm vi sử dụng rộng hơn trong database.

**Câu 3.** Fixed-user link hoạt động ra sao?

**Trả lời:** Nó luôn kết nối remote bằng username được khai báo trong link, bất kể local session nào sử dụng link đó.

**Câu 4.** Current-user link có tự động hoạt động với mọi user không?

**Trả lời:** Không. Cần cấu hình xác thực/danh tính phù hợp ở cả hai database, thường liên quan enterprise/global user hoặc external authentication.

**Câu 5.** TNS alias của DB link được phân giải ở đâu?

**Trả lời:** Trong Oracle Net environment mà database server local sử dụng vì chính local database server khởi tạo kết nối remote.

**Câu 6.** Làm sao kiểm tra link cơ bản?

**Trả lời:** Chạy `SELECT 1 FROM dual@link` và kiểm tra remote identity/global name nếu có quyền.

**Câu 7.** Synonym remote có copy dữ liệu không?

**Trả lời:** Không. Synonym chỉ là tên thay thế cho object remote và vẫn phụ thuộc DB link.

**Câu 8.** Vì sao distributed query có thể chậm?

**Trả lời:** Do network latency, lượng dữ liệu truyền, số round trip, remote execution plan hoặc tài nguyên remote.

**Câu 9.** `DRIVING_SITE` hint dùng để làm gì?

**Trả lời:** Gợi ý optimizer chọn site điều khiển distributed query; cần đo và kiểm tra plan trước khi áp dụng.

**Câu 10.** Khi nào cần two-phase commit?

**Trả lời:** Khi transaction phân tán cần cập nhật nhiều database participant và Oracle phải phối hợp quyết định commit/rollback.

**Câu 11.** RECO làm gì?

**Trả lời:** Hỗ trợ giải quyết distributed transaction còn pending khi participant/coordinator có thể liên lạc lại.

**Câu 12.** Vì sao không tự force commit một giao dịch in-doubt?

**Trả lời:** Có thể khiến các participant có kết quả khác nhau; cần xác định quyết định toàn cục và phối hợp DBA.

**Câu 13.** `GLOBAL_NAMES` ảnh hưởng DB link thế nào?

**Trả lời:** Khi bật, tên link phải tuân thủ quy tắc khớp global database name của remote database.

**Câu 14.** Vì sao remote account cần least privilege?

**Trả lời:** Nếu link hoặc credential bị lạm dụng, quyền tối thiểu giới hạn phạm vi dữ liệu và thao tác có thể bị ảnh hưởng.

**Câu 15.** DB link có thay thế replication không?

**Trả lời:** Không. DB link truy cập dữ liệu remote tại thời điểm query; nó không tự duy trì bản sao đồng bộ.

**Câu 16.** Khi nào nên cân nhắc materialized view thay DB link runtime?

**Trả lời:** Khi truy vấn lặp lại nhiều, chấp nhận độ trễ refresh và muốn giảm phụ thuộc vào remote database trong từng request.

**Câu 17.** Tại sao tránh remote query trong vòng lặp?

**Trả lời:** Mỗi lần gọi có thể tạo network round trip, làm latency tăng theo số vòng lặp.

**Câu 18.** Cần kiểm tra gì khi remote password đổi?

**Trả lời:** Link, remote account, consumer, session đã mở, truy vấn thử và thời điểm thu hồi credential cũ.

## 25. Kết luận

Database link cho phép Oracle Database local truy cập table, view và một số object ở database remote bằng cú pháp `object@link`. Private/public link quyết định phạm vi sử dụng; fixed-user/current-user link quyết định danh tính remote. Kết nối được khởi tạo từ database server local qua Oracle Net, vì vậy service name, listener, network, remote account và quyền object phải được cấu hình đúng ở cả hai phía.

DB link giúp viết distributed query và DML thuận tiện, nhưng hiệu năng phụ thuộc network round trip, lượng dữ liệu truyền, nơi thực hiện join và tài nguyên remote. Hãy lọc và aggregate sớm, chọn cột cần thiết, tránh gọi remote theo từng hàng và kiểm tra execution plan ở cả local lẫn remote. Với transaction thay đổi nhiều database, hiểu two-phase commit, in-doubt transaction và vai trò của RECO; không force commit/rollback khi chưa xác định quyết định toàn cục.

Về bảo mật, ưu tiên private link, remote account least privilege, kiểm soát quyền tạo public link, bảo vệ credential trong DDL và giới hạn kết nối mạng. DB link không phải replication, backup hay message queue. Khi cần giảm phụ thuộc runtime, cân nhắc materialized view, ETL/CDC, API hoặc messaging. Chỉ đưa link vào production sau khi đã kiểm tra service đích, quyền, rotation, hiệu năng, transaction recovery và runbook khi remote database mất kết nối.

