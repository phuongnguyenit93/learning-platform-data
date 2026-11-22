# Giới hạn phạm vi, quyền và giấy phép của các phương án tích hợp

Oracle Database có nhiều cách kết nối và trao đổi dữ liệu với hệ thống khác: database link và distributed SQL, materialized view, external table, Data Pump, Database Gateway, Oracle GoldenGate, Advanced Queuing và REST API. Mỗi phương án có phạm vi dữ liệu, mô hình quyền, đặc điểm vận hành và điều kiện cấp phép khác nhau.

Một lựa chọn tích hợp đúng cần trả lời ba câu hỏi:

1. **Phạm vi:** Hệ thống nào được kết nối, schema/table/row nào được đọc hoặc ghi, dữ liệu di chuyển một lần hay đồng bộ liên tục?
2. **Quyền:** Danh tính nào thực hiện kết nối, quyền được cấp ở database nào, có thể cấp tiếp hay truy cập ngoài phạm vi không?
3. **Giấy phép:** Database edition, option, product, deployment và metric nào được hợp đồng cho phép?

Không nên chọn công nghệ chỉ vì nó đã được cài hoặc lệnh kỹ thuật chạy được. Khả năng kỹ thuật và quyền sử dụng thương mại là hai việc riêng. Đặc biệt với GoldenGate, Gateway, XStream, Active Data Guard và các tính năng bảo mật, phải xác nhận đúng phiên bản, edition, sản phẩm, hợp đồng và cách triển khai trước khi đưa vào production.

## 1. Bản đồ các phương án tích hợp

| Phương án | Mô hình | Phạm vi thường dùng | Điểm cần kiểm soát |
|---|---|---|---|
| Database link | Truy vấn/ghi từ một database sang database khác | Object cụ thể ở database từ xa | Remote account, link owner, public/private, distributed transaction |
| Materialized view | Lưu bản sao kết quả truy vấn và refresh | Bảng hoặc tập dữ liệu cần đọc cục bộ | Refresh mode, freshness, quyền nguồn/đích, dung lượng |
| External table | Đọc dữ liệu file như table | File hoặc định dạng được access driver hỗ trợ | DIRECTORY, quyền filesystem, format và nguồn file |
| Data Pump | Export/import logic | Full, schema, table hoặc tablespace | Quyền Data Pump, dump file, consistency, encryption |
| Database Gateway / Heterogeneous Services | Truy cập hệ thống không phải Oracle | Object ở SQL Server, ODBC hoặc hệ thống được hỗ trợ | Gateway/agent, type mapping, pushdown, distributed transaction, license |
| Oracle GoldenGate | Capture và replicate thay đổi | Bảng/schema/database hoặc luồng đã lọc | Product license, capture/apply, conflict, lag, supplemental logging |
| AQ / Transactional Event Queues | Trao đổi message bất đồng bộ | Queue, consumer, event | Quyền enqueue/dequeue, retention, delivery semantics |
| REST qua ORDS hoặc API layer | Tích hợp qua HTTP | Endpoint, resource, operation | Authentication, OAuth/role, network, rate limit và license database |

Không có phương án nào phù hợp cho mọi trường hợp. Ví dụ, database link thuận tiện cho truy vấn từ xa nhưng tạo phụ thuộc thời gian chạy vào network và database nguồn. GoldenGate phù hợp với replication liên tục nhưng cần kiến trúc capture/apply và kiểm soát license. Data Pump phù hợp cho di chuyển theo đợt, không phải đồng bộ từng thay đổi theo thời gian thực.

## 2. Xác định phạm vi trước khi chọn công nghệ

Trước khi thiết kế, hãy mô tả phạm vi tích hợp theo các chiều sau:

### Phạm vi hệ thống

- Database nguồn và database đích.
- CDB/PDB và service name liên quan.
- Hệ thống ngoài Oracle như SQL Server, PostgreSQL, file server hoặc API.
- Môi trường development, test, staging, production và DR.
- Vùng mạng được phép kết nối.

### Phạm vi dữ liệu

- Schema nào được chia sẻ?
- Bảng/view nào cần truy cập?
- Có cần giới hạn theo cột hoặc theo tenant không?
- Có thể lọc theo hàng, thời gian hoặc trạng thái nghiệp vụ không?
- Có dữ liệu nhạy cảm cần mask hoặc loại bỏ không?
- Có cần dữ liệu lịch sử hay chỉ dữ liệu hiện tại?

### Phạm vi thao tác

- Chỉ đọc hay có cả ghi?
- Một chiều hay hai chiều?
- Truy vấn theo yêu cầu hay đồng bộ liên tục?
- Có yêu cầu transaction xuyên database không?
- Có yêu cầu gần thời gian thực hay chấp nhận batch?
- Khi mất kết nối, dữ liệu được retry, xếp hàng hay bỏ qua?

### Phạm vi thời gian và phục hồi

- Tần suất chạy và thời gian cửa sổ.
- RPO và độ trễ dữ liệu tối đa.
- RTO khi một hệ thống mất kết nối.
- Cách phát hiện dữ liệu thiếu hoặc trùng.
- Cách reconcile sau khi khôi phục.

Một thiết kế rõ phạm vi giúp cấp quyền hẹp, ước tính tải và xác định license cần kiểm tra.

## 3. Database link: kết nối trực tiếp giữa hai database

Database link (DB link) cho phép một session trong database local truy cập object ở database remote bằng cú pháp như:

~~~sql
SELECT order_id,
       status
  FROM orders@orders_link;
~~~

DB link thường phù hợp khi:

- Ứng dụng cần truy vấn dữ liệu remote theo yêu cầu.
- Số lượng object và lưu lượng ở mức có thể kiểm soát.
- Có thể chấp nhận phụ thuộc network và availability của database remote.
- Cần thao tác distributed SQL hoặc transaction qua nhiều database.

DB link không sao chép dữ liệu sang local. Truy vấn vẫn phụ thuộc remote database và network tại thời điểm thực thi.

### Tạo private database link

Ví dụ:

~~~sql
CREATE DATABASE LINK orders_link
  CONNECT TO integration_reader
  IDENTIFIED BY "Managed-Secret"
  USING 'ORDERS_SERVICE';
~~~

Tên service ORDERS_SERVICE phải được cấu hình trong Oracle Net naming hoặc connect descriptor phù hợp với database local. Password trong ví dụ chỉ là placeholder; không ghi secret thật vào source code hoặc file SQL được commit.

User tạo private DB link cần quyền CREATE DATABASE LINK. DB link riêng thuộc phạm vi user sở hữu nó.

### Tạo public database link

~~~sql
CREATE PUBLIC DATABASE LINK shared_orders_link
  CONNECT TO integration_reader
  IDENTIFIED BY "Managed-Secret"
  USING 'ORDERS_SERVICE';
~~~

Tạo public link cần quyền CREATE PUBLIC DATABASE LINK. Public link có thể được mọi database user sử dụng theo cấu hình link và quyền remote tương ứng. Vì vậy, public link có thể mở rộng phạm vi truy cập vượt quá nhu cầu của một ứng dụng.

Ưu tiên private DB link cho service hoặc schema cụ thể. Chỉ dùng public link khi có lý do kiến trúc rõ ràng, owner chịu trách nhiệm, quyền remote hẹp và audit phù hợp.

### Loại xác thực của DB link

Các kiểu kết nối thường gặp:

- **Fixed user:** DB link lưu thông tin user remote cố định; mọi truy cập qua link dùng danh tính remote đó.
- **Connected user:** danh tính local được dùng để xác thực tương ứng ở remote theo cấu hình và mô hình xác thực hỗ trợ.
- **Current user:** sử dụng global user/current user trong các tình huống được hỗ trợ, thường gắn với enterprise user/security model.

Không nên dùng fixed user có quyền DBA hoặc quyền đọc toàn bộ schema. Tạo remote account chỉ có quyền cần cho tích hợp, ví dụ SELECT trên một số view hoặc EXECUTE trên package API.

### Quyền nằm ở cả hai phía

Để truy vấn qua DB link thành công:

1. Local user cần quyền sử dụng DB link theo cách link được tạo và sở hữu.
2. Link phải phân giải đúng service và kết nối được đến remote database.
3. Remote credential phải xác thực được.
4. Remote user phải có privilege trên object được truy cập.
5. Network và firewall phải cho phép kết nối.

Local grant không thay thế remote grant. Ví dụ, cấp SELECT cho local user trên một view không tự cấp quyền đọc bảng remote. Remote account phải có quyền tương ứng trên object remote hoặc package được công bố.

### Private link và public link

| Tiêu chí | Private DB link | Public DB link |
|---|---|---|
| Phạm vi nhìn thấy | User sở hữu link | Các user trong database có thể tham chiếu |
| Quyền tạo | CREATE DATABASE LINK | CREATE PUBLIC DATABASE LINK |
| Credential | Có thể gắn với user remote cố định | Có thể gắn credential cố định dùng chung |
| Rủi ro | Phụ thuộc quyền remote account và link owner | Dễ mở rộng phạm vi truy cập cho nhiều user |
| Khuyến nghị | Ưu tiên cho ứng dụng/schema cụ thể | Chỉ dùng khi có lý do và kiểm soát rõ |

### Kiểm tra database link

~~~sql
SELECT owner,
       db_link,
       username,
       host
  FROM dba_db_links
 ORDER BY owner, db_link;
~~~

User thường có thể xem USER_DB_LINKS hoặc ALL_DB_LINKS trong phạm vi quyền được phép. Không truy vấn hoặc xuất thông tin credential nhạy cảm vào báo cáo.

Kiểm tra remote:

~~~sql
SELECT 1
  FROM dual@orders_link;
~~~

Sau đó xác nhận đúng database/service:

~~~sql
SELECT name,
       db_unique_name
  FROM v$database@orders_link;
~~~

Truy vấn trên cần quyền đọc dynamic performance view ở remote; nếu không có, dùng một view kiểm tra tối thiểu được công bố cho tích hợp.

## 4. Distributed SQL và distributed transaction

DB link hỗ trợ distributed query, ví dụ join local và remote table:

~~~sql
SELECT o.order_id,
       c.customer_name
  FROM local_orders o
  JOIN customers@crm_link c
    ON c.customer_id = o.customer_id;
~~~

Oracle có thể đẩy một phần xử lý về remote database hoặc truyền dữ liệu về local để thực hiện phần còn lại. Kế hoạch thực thi phụ thuộc thống kê, predicate, kiểu dữ liệu, khả năng remote và optimizer.

Không giả định join luôn được thực hiện tại nơi có ít dữ liệu nhất. Kiểm tra execution plan và số hàng truyền qua network khi truy vấn chậm.

### Transaction xuyên database

Một transaction có thể cập nhật object local và remote thông qua DB link:

~~~sql
UPDATE local_orders
   SET status = 'CONFIRMED'
 WHERE order_id = 1001;

UPDATE orders@orders_link
   SET status = 'CONFIRMED'
 WHERE order_id = 1001;

COMMIT;
~~~

Trong trường hợp cần bảo đảm tính nhất quán giữa nhiều database, Oracle sử dụng distributed transaction coordination, thường liên quan two-phase commit (2PC). Một transaction có thể có trạng thái in-doubt nếu một participant hoặc network gặp lỗi ở thời điểm commit.

DBA cần biết cách theo dõi và xử lý distributed transaction, bao gồm các view như DBA_2PC_PENDING và quy trình recovery tương ứng. Không tự xóa hoặc force commit/rollback giao dịch in-doubt khi chưa xác định quyết định commit toàn cục.

### Giới hạn vận hành của distributed transaction

- Network latency kéo dài thời gian giữ lock.
- Remote database không sẵn sàng có thể làm transaction không hoàn tất.
- Lỗi 2PC có thể tạo in-doubt transaction cần xử lý.
- Một số thao tác hoặc kiểu object không phù hợp với distributed transaction.
- Transaction lớn xuyên nhiều hệ thống làm tăng coupling.

Nếu không cần transaction đồng bộ xuyên database, cân nhắc outbox pattern, queue hoặc replication bất đồng bộ để giảm coupling.

## 5. Materialized view: bản sao dữ liệu có refresh

Materialized view lưu kết quả truy vấn vào database thay vì thực thi truy vấn remote mỗi lần người dùng đọc. Nó phù hợp với báo cáo, tra cứu hoặc dữ liệu tham chiếu cần đọc nhanh và chấp nhận độ trễ refresh.

Ví dụ tạo materialized view dựa trên remote table:

~~~sql
CREATE MATERIALIZED VIEW local_customer_snapshot
  BUILD IMMEDIATE
  REFRESH COMPLETE ON DEMAND
AS
SELECT customer_id,
       customer_name,
       customer_status
  FROM customers@crm_link;
~~~

Ví dụ này tạo bản sao logic của một tập cột từ remote. User tạo MV cần quyền tạo materialized view và các quyền đọc nguồn tương ứng; remote user qua DB link cần quyền đọc bảng hoặc view remote.

### Complete refresh và fast refresh

| Cơ chế | Hành vi | Đặc điểm |
|---|---|---|
| COMPLETE | Chạy lại query để xây lại toàn bộ nội dung | Dễ hiểu, có thể tốn I/O và thời gian |
| FAST | Áp dụng thay đổi tăng dần khi đủ điều kiện | Cần log/metadata và query đáp ứng yêu cầu |
| FORCE | Cố gắng FAST, nếu không được thì COMPLETE theo quy tắc | Kết quả và chi phí phụ thuộc khả năng fast refresh |

Fast refresh có điều kiện về query, materialized view log, key và khả năng hỗ trợ của nguồn/đích. Không phải query bất kỳ nào cũng fast refresh được. Với remote master, cần đọc tài liệu Oracle đúng release và thử refresh trong môi trường tương đương.

### Quyền và phạm vi

- Local owner cần quyền tạo và refresh MV.
- Remote account chỉ cần quyền đọc object nguồn.
- Không cấp remote SELECT ANY TABLE chỉ để refresh một MV.
- Nếu người dùng chỉ cần đọc MV, cấp SELECT trên MV thay vì DB link hoặc bảng nguồn.
- Đặt lịch refresh phù hợp với freshness SLA và tải nguồn.

Materialized view có thể giảm truy vấn trực tiếp lên remote database, nhưng tạo bản sao dữ liệu. Phải xác định ai được đọc bản sao, dữ liệu có nhạy cảm không và khi nào dữ liệu được xóa hoặc refresh.

## 6. External tables: đọc file qua SQL

External table cho phép Oracle truy vấn dữ liệu nằm trong file ngoài database như một table. Dữ liệu không nhất thiết được lưu trong segment của bảng Oracle; access driver đọc file theo cấu hình.

Ví dụ đơn giản với ORACLE_LOADER:

~~~sql
CREATE TABLE ext_orders (
  order_id      NUMBER,
  customer_id   NUMBER,
  order_date    DATE,
  order_status  VARCHAR2(30)
)
ORGANIZATION EXTERNAL (
  TYPE ORACLE_LOADER
  DEFAULT DIRECTORY dp_dir
  ACCESS PARAMETERS (
    RECORDS DELIMITED BY NEWLINE
    FIELDS TERMINATED BY ','
    OPTIONALLY ENCLOSED BY '"'
    MISSING FIELD VALUES ARE NULL
  )
  LOCATION ('orders.csv')
)
REJECT LIMIT UNLIMITED;
~~~

External table phù hợp cho:

- Nạp file CSV hoặc text.
- Đọc file trao đổi theo batch.
- Kết hợp SQL để lọc/biến đổi dữ liệu.
- Stage dữ liệu trước khi insert vào bảng nội bộ.

### Quyền external table

User tạo external table cần quyền tạo table phù hợp và quyền READ trên DIRECTORY object. Oracle software owner cần quyền đọc file ở filesystem. Nếu external table ghi file qua access driver hỗ trợ, cần quyền WRITE và quyền filesystem tương ứng.

Không cấp quyền DIRECTORY cho PUBLIC. Một DIRECTORY object có thể trỏ đến vị trí chứa nhiều file; quyền quá rộng có thể cho phép đọc file ngoài phạm vi nghiệp vụ.

### External table không phải DB link

External table đọc file, không thực hiện truy vấn trực tiếp đến database khác. Nếu file được tạo bởi hệ thống khác, cần quy trình đưa file vào thư mục, kiểm tra checksum, format, encoding, quyền và thời điểm hoàn tất.

Không cho ứng dụng đọc file đang được producer ghi dở. Dùng cơ chế staging/rename nguyên tử hoặc manifest để chỉ import file đã hoàn thành.

## 7. Data Pump: di chuyển logic theo phạm vi

Data Pump dùng expdp/impdp để export/import metadata và dữ liệu:

| Mode | Phạm vi |
|---|---|
| FULL=YES | Phạm vi full database theo quyền và hỗ trợ |
| SCHEMAS | Một hoặc nhiều schema |
| TABLES | Một hoặc nhiều bảng |
| TABLESPACES | Các object/dữ liệu theo tablespace |
| TRANSPORT_TABLESPACES | Metadata cho workflow chuyển datafile transportable |

Data Pump phù hợp cho migration, refresh môi trường test, chuyển schema hoặc trao đổi dữ liệu theo đợt. Nó không phải cơ chế đồng bộ liên tục.

### Quyền Data Pump

User cần quyền phù hợp với mode, object và DIRECTORY:

- CREATE SESSION.
- READ/WRITE trên DIRECTORY object.
- Quyền đọc object nguồn.
- Quyền tạo object ở database đích.
- Các role Data Pump full export/import khi thao tác vượt phạm vi schema của chính user.

Không cấp DBA mặc định. Cần phân biệt role DATAPUMP_EXP_FULL_DATABASE và DATAPUMP_IMP_FULL_DATABASE với quyền DBA tổng quát.

### Network link import

Data Pump có thể dùng NETWORK_LINK để đọc trực tiếp từ database nguồn qua database link:

~~~text
impdp app_user@TARGET NETWORK_LINK=SOURCE_LINK SCHEMAS=APP_OWNER LOGFILE=network_import.log
~~~

Đích cần có database link trỏ đến nguồn và quyền đọc cần thiết. Cần kiểm tra version compatibility, network throughput, remote load và transaction/consistency requirements. NETWORK_LINK không biến Data Pump thành replication liên tục.

## 8. Database Gateway và Heterogeneous Services

Database link thông thường kết nối đến Oracle Database. Khi cần truy cập một hệ quản trị không phải Oracle, có thể cần Oracle Database Gateway hoặc một giải pháp heterogeneous connectivity phù hợp.

Heterogeneous Services cung cấp lớp tích hợp để Oracle truy cập hệ thống không đồng nhất. Gateway chuyển đổi request, metadata và dữ liệu giữa Oracle SQL và giao thức/SQL của hệ thống đích.

Ví dụ kiến trúc khái quát:

~~~text
Oracle application
       |
       v
Oracle Database
       |
       | database link
       v
Heterogeneous Services
       |
       v
Database Gateway / agent
       |
       v
Non-Oracle database
~~~

Gateway cụ thể phụ thuộc hệ thống đích và phiên bản. Có thể có gateway dành cho một database vendor hoặc generic connectivity dựa trên ODBC.

### Phạm vi và giới hạn

- Không phải mọi kiểu dữ liệu Oracle đều ánh xạ một-một sang hệ thống đích.
- SQL function, join, analytic function và datatype có thể không được push down.
- Một số DDL hoặc transaction semantics không được hỗ trợ giống Oracle-to-Oracle.
- Hiệu năng phụ thuộc network, driver, gateway host và khả năng remote optimizer.
- Transaction phân tán với non-Oracle participant có thể có giới hạn riêng.
- Cần kiểm tra character set, timezone, numeric precision và NULL semantics.

Không giả định truy vấn chạy được trên Oracle cũng sẽ chạy giống hệt qua gateway. Kiểm thử câu SQL thực tế, execution behavior, transaction và lỗi ở cả hai phía.

### Quyền gateway

Remote account cần quyền tối thiểu trên hệ thống đích. Local database user cần quyền sử dụng database link và object/view được công bố. Gateway process/agent cần credential, OS account và network access theo cấu hình.

Tách tài khoản gateway service khỏi tài khoản quản trị database. Không lưu credential remote trong file cấu hình có thể đọc công khai. Hạn chế quyền trên gateway host, log và thư mục cấu hình.

### Giấy phép gateway

Không suy luận rằng gateway được phép dùng chỉ vì binary, driver hoặc cấu hình có mặt trong Oracle Home. Điều kiện license có thể phụ thuộc tên sản phẩm gateway, hệ thống đích, phiên bản, edition, cách triển khai và hợp đồng. Kiểm tra tài liệu licensing hiện hành và order document cho đúng gateway cụ thể trước production.

Generic connectivity, gateway dành riêng cho vendor và các sản phẩm tích hợp của bên thứ ba có thể có điều kiện thương mại khác nhau. Không áp dụng một kết luận license chung cho mọi gateway.

## 9. Oracle GoldenGate: capture và replicate thay đổi

Oracle GoldenGate là nền tảng capture, route và apply thay đổi dữ liệu giữa database hoặc hệ thống được hỗ trợ. Nó phù hợp với:

- Replication gần thời gian thực.
- Đồng bộ dữ liệu sang hệ thống báo cáo.
- Di chuyển database với downtime thấp.
- Tích hợp dữ liệu giữa nhiều hệ thống.
- Kiến trúc active/passive hoặc một số topology multi-directional được thiết kế riêng.

Luồng đơn giản:

~~~text
Source database
      |
      | redo / transaction log
      v
GoldenGate Extract
      |
      v
Trail files
      |
      | network transfer
      v
GoldenGate Replicat
      |
      v
Target database
~~~

GoldenGate có thể dùng Extract/Replicat và các thành phần khác tùy kiến trúc, deployment model và version. Không nên coi sơ đồ đơn giản này là kiến trúc triển khai hoàn chỉnh.

### Phạm vi replication

GoldenGate có thể lọc theo:

- Database/schema/table.
- Column mapping.
- Row predicate.
- Operation type.
- Routing rule.

Phạm vi lọc phải được kiểm thử. Nếu lọc bảng cha mà quên bảng con, dữ liệu đích có thể thiếu quan hệ. Nếu lọc theo tenant, phải bảo đảm mọi transaction và bảng phụ thuộc đều áp dụng cùng chính sách.

### Quyền và bảo mật

Capture account cần quyền đọc metadata/log và truy cập các view/package cần thiết theo phiên bản, capture mode và cấu hình. Apply account cần quyền ghi object đích. Không cấp DBA cho cả Extract và Replicat nếu tài liệu không yêu cầu.

Các điểm cần quản lý:

- Credential store và secret rotation.
- TLS/encryption cho luồng truyền.
- Quyền đọc trail file.
- Network access giữa source, target và GoldenGate deployment.
- Audit thay đổi cấu hình.
- Tách account vận hành GoldenGate khỏi DBA account.

### Consistency và conflict

GoldenGate replication bất đồng bộ có thể tạo lag. Hai chiều replication cần thiết kế conflict detection/resolution, key, sequence và transaction ordering. Không bật bidirectional replication chỉ bằng cách cấu hình hai luồng ngược chiều.

Cần xác định:

- Source of truth cho từng bảng/column.
- Conflict rule.
- Duplicate transaction handling.
- DDL replication policy.
- Unsupported datatype/object.
- Initial load và instantiation SCN.
- Lag alert và recovery/reposition procedure.

### License GoldenGate

Oracle GoldenGate là sản phẩm có điều kiện cấp phép riêng; không coi nó tự động nằm trong quyền sử dụng Oracle Database chỉ vì database có redo log hoặc GoldenGate agent có thể kết nối. Metric, deployment, topology, cloud/on-premises, source/target và quyền sử dụng có thể thay đổi theo hợp đồng và product version.

Trước khi bật GoldenGate trong production, đối chiếu Oracle GoldenGate Licensing Information/User Manual, Oracle price list và hợp đồng đã ký. Cần xác nhận cả môi trường DR, test, development, passive target và các deployment phụ có được bao phủ hay không.

## 10. XStream và giao diện capture/apply

Oracle XStream cung cấp API để ứng dụng bên ngoài nhận thay đổi từ Oracle hoặc gửi thay đổi vào Oracle theo mô hình capture/outbound và apply/inbound.

XStream có thể hữu ích khi middleware hoặc ứng dụng cần tích hợp trực tiếp với transaction change stream. Tuy nhiên, nó đòi hỏi hiểu sâu về LCR, transaction boundary, ordering, checkpoint, restart và backpressure.

Không nên chọn XStream như một tiện ích miễn phí thay thế GoldenGate. XStream có điều kiện license liên quan Oracle GoldenGate theo tài liệu Oracle; phải xác nhận entitlement hiện hành trước khi dùng.

Quyền cần xem xét:

- User capture/apply chuyên biệt.
- Quyền execute package/API XStream theo tài liệu.
- Quyền truy cập log và dictionary cần thiết.
- Credential store và network.
- Quyền vận hành checkpoint/restart.

Không cấp quyền SYSDBA hoặc DBA cho ứng dụng chỉ để khởi tạo stream. Dùng script cấp quyền chính thức theo đúng release và role tối thiểu.

## 11. Advanced Queuing và Transactional Event Queues

Oracle Advanced Queuing (AQ) và Transactional Event Queues (TxEventQ, tùy phiên bản) hỗ trợ trao đổi message bất đồng bộ trong database.

Một producer enqueue message vào queue; consumer dequeue và xử lý sau. Điều này giảm phụ thuộc đồng bộ giữa hai ứng dụng.

~~~text
Producer
   |
   | enqueue
   v
Oracle Queue
   |
   | dequeue
   v
Consumer
~~~

Mô hình queue phù hợp khi:

- Producer không cần chờ consumer hoàn tất.
- Có thể retry khi consumer tạm ngừng.
- Cần buffering khi tải tăng đột biến.
- Muốn tách vòng đời hai service.

### Phạm vi và quyền

Quyền cần cấp theo queue và API được dùng. User producer cần quyền enqueue; consumer cần quyền dequeue; quản trị queue cần quyền phù hợp để tạo, thay đổi và giám sát queue.

Không cấp quyền quản trị queue cho mọi service. Phân tách queue theo domain hoặc service để giới hạn ai được gửi/nhận message.

### Delivery semantics

Thiết kế phải xác định:

- At-most-once, at-least-once hoặc xử lý idempotent.
- Retry và backoff.
- Dead-letter/exception queue.
- Message expiration và retention.
- Ordering và grouping.
- Poison message.
- Transaction boundary giữa enqueue/dequeue và cập nhật business table.

Không giả định message chỉ được xử lý đúng một lần nếu consumer có thể crash sau khi thực hiện nghiệp vụ nhưng trước khi acknowledge/dequeue hoàn tất. Thiết kế idempotency key và xử lý duplicate.

### License

AQ/TxEventQ là tính năng database có điều kiện sử dụng phụ thuộc release, edition và cấu hình. Kiểm tra licensing guide và tài liệu tính năng của đúng phiên bản, đặc biệt khi kết hợp với GoldenGate, sharding, RAC hoặc các option khác. Không suy ra license từ tên package hoặc việc queue được tạo thành công.

## 12. REST API và ORDS

REST API tạo một ranh giới tích hợp ở tầng HTTP thay vì cho hệ thống ngoài kết nối trực tiếp vào database. Oracle REST Data Services (ORDS) có thể ánh xạ REST endpoint đến SQL, PL/SQL hoặc module được định nghĩa.

Luồng khái quát:

~~~text
External application
       |
       | HTTPS / OAuth
       v
ORDS / API layer
       |
       | database session
       v
Oracle schema / PL/SQL API
~~~

REST phù hợp khi cần tích hợp qua API contract, kiểm soát request/response, authentication, rate limit và versioning.

### Quyền endpoint

Không expose trực tiếp toàn bộ schema. Nên:

- Tạo module/resource theo nghiệp vụ.
- Dùng schema/API owner riêng nếu phù hợp.
- Cấp quyền execute trên package hoặc quyền SELECT trên view đã giới hạn.
- Ánh xạ role/OAuth scope đến operation.
- Kiểm tra tenant và authorization trên mỗi request.
- Giới hạn payload, request rate và timeout.
- Bảo vệ endpoint bằng HTTPS và chính sách token.

Một endpoint GET không tự động là read-only nếu PL/SQL phía sau có side effect. Phải review behavior của handler và package.

### License và ranh giới sản phẩm

ORDS là lớp dịch vụ/API; database phía sau vẫn cần license theo edition, metric và deployment. Quyền sử dụng ORDS, Oracle Database và các option được gọi bởi code phải được kiểm tra riêng theo điều khoản hiện hành. Nếu API dùng tính năng database được cấp phép riêng, việc gọi qua REST không làm mất yêu cầu license đó.

## 13. Ma trận quyền tối thiểu theo phương án

| Phương án | Local identity | Remote/target identity | Quyền nên giới hạn |
|---|---|---|---|
| Private DB link | Schema/service owner có CREATE DATABASE LINK | Account chuyên biệt trên remote | SELECT view hoặc EXECUTE API cụ thể |
| Public DB link | DBA có CREATE PUBLIC DATABASE LINK | Fixed remote account | Tránh nếu không cần; không dùng account quyền rộng |
| Materialized view | Owner có quyền tạo/refresh MV | DB link account đọc nguồn | Chỉ đọc object nguồn cần refresh |
| External table | User có quyền tạo external table và READ DIRECTORY | OS account của Oracle server | Chỉ đọc thư mục/file staging |
| Data Pump | User chạy job và DIRECTORY privilege | Database nguồn/đích theo job | Role Data Pump đúng mode, không mặc định DBA |
| Gateway | Local integration schema | Remote gateway account | Chỉ object và operation cần thiết |
| GoldenGate | Capture/apply accounts | Source/target credentials | Role theo capture/apply mode và version |
| AQ/TxEventQ | Producer/consumer identity | Queue owner/admin | Enqueue/dequeue trên queue cụ thể |
| REST/ORDS | API schema/handler | OAuth client/end-user | Scope endpoint, package/view và tenant |

Quyền thực tế phụ thuộc release và cấu hình. Dùng script cấp quyền chính thức của Oracle cho GoldenGate, XStream, Gateway hoặc component tương ứng; không tự thay thế bằng DBA.

## 14. Database link và quyền qua PL/SQL

Khi một stored procedure dùng DB link, cần hiểu rõ quyền thực thi của PL/SQL unit:

- Definer-rights unit chạy theo quyền của owner theo quy tắc Oracle.
- Invoker-rights unit chạy theo ngữ cảnh của invoker theo quy tắc AUTHID CURRENT_USER.
- Role có thể bị vô hiệu hóa trong named definer-rights unit.
- Remote account qua DB link vẫn phải có quyền trên remote object.

Ví dụ package API:

~~~sql
CREATE OR REPLACE PACKAGE app_api AS
  PROCEDURE read_customer(p_customer_id IN NUMBER);
END app_api;
/

CREATE OR REPLACE PACKAGE BODY app_api AS
  PROCEDURE read_customer(p_customer_id IN NUMBER) IS
    l_name VARCHAR2(200);
  BEGIN
    SELECT customer_name
      INTO l_name
      FROM customers@crm_link
     WHERE customer_id = p_customer_id;
  END;
END app_api;
/
~~~

Đây là ví dụ minh họa. Cần xác minh DB link được tạo trong schema phù hợp, owner có quyền sử dụng link, remote credential hoạt động và remote user có SELECT trên object. Không cấp SELECT ANY TABLE ở remote để sửa lỗi thiếu quyền trên một bảng.

## 15. Tách quyền theo môi trường và danh tính

Không dùng một credential cho mọi môi trường:

| Môi trường | Danh tính ví dụ | Nguyên tắc |
|---|---|---|
| Development | APP_DEV_INTEGRATION | Chỉ truy cập dữ liệu dev |
| Test | APP_TEST_INTEGRATION | Dữ liệu test và endpoint test |
| Staging | APP_STAGE_INTEGRATION | Gần production nhưng secret riêng |
| Production | APP_PROD_INTEGRATION | Quyền hẹp, secret quản lý tập trung, audit |
| DR | APP_DR_INTEGRATION | Chỉ dùng theo topology và kế hoạch DR |

Một DB link ở production không nên trỏ nhầm đến database test hoặc ngược lại. Kiểm tra service name, DB_UNIQUE_NAME, PDB và remote account khi triển khai.

Credential cần:

- Được lưu trong secret manager hoặc wallet phù hợp.
- Có owner và vòng đời.
- Được rotate có kiểm soát.
- Có quy trình revoke khi lộ.
- Không xuất hiện trong Git, log hoặc command history.

## 16. Row-level, column-level và tenant scope

Schema/table privilege thường chỉ giới hạn object, không tự giới hạn hàng theo tenant. Nếu một remote account có SELECT trên bảng CUSTOMER, nó có thể đọc mọi hàng của bảng theo quyền đó.

Để thu hẹp phạm vi:

- Công bố view đã lọc cột/hàng.
- Dùng package API kiểm tra business context.
- Dùng Virtual Private Database (VPD) hoặc Row-Level Security khi phù hợp.
- Dùng Application Context được thiết lập từ nguồn tin cậy.
- Tách schema hoặc database theo tenant nếu kiến trúc yêu cầu.
- Truyền tenant identifier bằng bind variable và kiểm tra ở database.

Không tin tenant_id do client tự gửi nếu không được xác thực. Nếu tất cả request dùng chung một DB account, database cần một cơ chế context an toàn để phân biệt request/tenant.

### View làm lớp công bố dữ liệu

Ví dụ view chỉ công bố cột cần thiết:

~~~sql
CREATE OR REPLACE VIEW app_owner.customer_public_v AS
SELECT customer_id,
       customer_name,
       customer_status
  FROM app_owner.customers
 WHERE customer_status = 'ACTIVE';

GRANT SELECT ON app_owner.customer_public_v TO integration_reader;
~~~

View giúp giới hạn cột và hàng theo predicate cố định. Với tenant-specific access, cần predicate được gắn với context đã xác thực và kiểm tra kỹ quyền bypass.

### Package API

Thay vì cấp INSERT/UPDATE trên bảng, có thể cấp EXECUTE trên package chỉ cung cấp thao tác hợp lệ:

~~~sql
GRANT EXECUTE ON app_owner.customer_api TO integration_writer;
~~~

Package phải validate input, tenant, trạng thái nghiệp vụ và transaction boundary. EXECUTE trên package vẫn có thể cho phép thao tác rất rộng nếu code bên trong không được thiết kế an toàn.

## 17. Network scope và điểm kết nối

Tích hợp không chỉ là quyền database. Hãy giới hạn network:

- Chỉ mở host/port cần thiết giữa hai hệ thống.
- Dùng service name đúng PDB.
- Không expose listener database trực tiếp ra Internet.
- Dùng TLS/TCPS khi phù hợp.
- Dùng VPN, private network hoặc service mesh theo kiến trúc.
- Giới hạn outbound connection từ database/gateway.
- Kiểm soát DNS, certificate và endpoint rotation.
- Theo dõi connection source và bất thường.

Với REST, giới hạn endpoint và API gateway. Với GoldenGate, chỉ mở các port giữa deployment components cần thiết. Với Gateway, giới hạn kết nối từ gateway host đến remote database.

## 18. Licensing: phân biệt database, option và product

Oracle licensing có thể gồm nhiều lớp:

1. **Database edition:** ví dụ Standard Edition 2 hoặc Enterprise Edition theo hợp đồng và release.
2. **Database option:** tính năng bổ sung có thể cần license riêng.
3. **Management pack:** một số công cụ giám sát/chẩn đoán có điều kiện cấp phép riêng.
4. **Sản phẩm tích hợp riêng:** ví dụ Oracle GoldenGate hoặc một gateway cụ thể.
5. **Metric và deployment:** Processor, Named User Plus hoặc metric khác; on-premises, cloud, virtualized, DR và môi trường phụ.

Một feature có thể được cài đặt sẵn hoặc xuất hiện trong giao diện nhưng điều đó không tự chứng minh tổ chức có entitlement. Ngược lại, việc một feature được gọi trong code không phải lúc nào cũng đủ để kết luận license; cần đối chiếu cách sử dụng, edition, release và hợp đồng.

### Nguyên tắc kiểm tra license

- Xác định chính xác product/option và version.
- Đọc Licensing Information/User Manual của release.
- Đối chiếu Oracle price list và order document/hợp đồng.
- Xác nhận metric và số lượng license.
- Kiểm tra môi trường production, test, development, standby và DR.
- Xác nhận quy tắc virtualization, cloud và disaster recovery.
- Lưu bằng chứng phê duyệt trước khi production.
- Hỏi license specialist/Oracle khi điều khoản không rõ.

Không dùng một bài blog, một câu trả lời diễn đàn hoặc kết quả kỹ thuật cài đặt làm căn cứ pháp lý cuối cùng.

## 19. Bảng định hướng licensing theo phương án

Bảng sau là định hướng kỹ thuật để biết phần nào cần xác minh. Nó không thay thế hợp đồng, price list hoặc tư vấn license chính thức.

| Phương án | Điểm license cần xác minh |
|---|---|
| DB link Oracle-to-Oracle | DB link là khả năng database; từng database deployment vẫn phải được cấp phép theo edition/metric của nó |
| Distributed SQL / 2PC | Xác nhận database edition/version và mọi option liên quan đến kiến trúc; không suy luận từ việc transaction chạy thành công |
| Materialized view | Xác nhận quyền dùng tính năng trong edition/release và các option phụ thuộc như Partitioning nếu thiết kế sử dụng |
| External table cơ bản | Xác nhận access driver và feature cụ thể; driver chuyên biệt hoặc tích hợp ngoài có thể có điều kiện riêng |
| Data Pump | Tiện ích export/import logic; database nguồn/đích và các option được dùng vẫn phải có entitlement tương ứng |
| Database Gateway | Xác nhận đúng gateway product, target platform, version và hợp đồng; không áp dụng một kết luận chung cho mọi gateway |
| GoldenGate | Sản phẩm riêng có license; xác nhận metric, source/target, deployment, topology và môi trường phụ |
| XStream | Kiểm tra điều kiện license gắn với GoldenGate theo tài liệu Oracle hiện hành |
| AQ / TxEventQ | Xác nhận release, edition và tính năng queue được sử dụng; xem xét option khác nếu kiến trúc phụ thuộc |
| REST / ORDS | Xác nhận quyền sử dụng ORDS và database/option phía sau; API không miễn trừ license database |
| Active Data Guard | Nếu dùng tính năng thuộc Active Data Guard option, xác nhận entitlement riêng; không đồng nhất với mọi chức năng Data Guard cơ bản |

### Các điểm đặc biệt cần chú ý

**GoldenGate:** thường là sản phẩm được cấp phép riêng. Phải xác định số deployment, source/target, topology và metric theo hợp đồng.

**XStream:** không nên xem là đường thay thế GoldenGate không cần license. Đối chiếu licensing guide của Oracle cho XStream và release đang dùng.

**Gateway:** sản phẩm gateway cho từng hệ thống đích có thể có điều kiện riêng. Kiểm tra đúng SKU/product thay vì chỉ tìm từ khóa Heterogeneous Services.

**Active Data Guard:** một số khả năng như real-time query trên physical standby thuộc option Active Data Guard. Phải phân biệt Data Guard cơ bản với tính năng được cấp phép bổ sung.

**Advanced Security:** các chức năng như Transparent Data Encryption hoặc network encryption có điều kiện license thay đổi theo release và chương trình cấp phép. Nếu tích hợp yêu cầu mã hóa, xác minh feature và entitlement cụ thể.

**Partitioning:** nếu dùng partitioned tables trong materialized view, staging hoặc replication target, xác nhận option Partitioning có được cấp phép và được triển khai đúng metric hay không.

## 20. Kiểm soát license trong vòng đời tích hợp

License review nên diễn ra trước khi thiết kế được chốt và trước khi bật feature trên production:

1. Lập danh sách công nghệ dự kiến.
2. Ghi rõ feature, option, product và version.
3. Ghi rõ source/target, số database, node, deployment và môi trường.
4. Xác định metric áp dụng theo hợp đồng.
5. Kiểm tra feature sử dụng có thuộc edition/option nào.
6. Xác nhận test, DR, standby, cloud và virtualization.
7. Lưu bằng chứng entitlement và người phê duyệt.
8. Kiểm tra lại khi topology hoặc version thay đổi.

Không đợi đến lúc audit mới xác định GoldenGate deployment hoặc option đang dùng. Tích hợp mới có thể làm thay đổi footprint license ngay cả khi dữ liệu và ứng dụng không thay đổi.

### Feature usage views không phải hợp đồng

Oracle có các view phục vụ theo dõi feature usage, chẳng hạn DBA_FEATURE_USAGE_STATISTICS trong các release hỗ trợ. Chúng có thể giúp nhận diện một số feature được database ghi nhận đã sử dụng:

~~~sql
SELECT name,
       detected_usages,
       currently_used,
       first_usage_date,
       last_usage_date
  FROM dba_feature_usage_statistics
 ORDER BY name;
~~~

View này là nguồn thông tin kỹ thuật để điều tra, không phải kết luận pháp lý duy nhất về entitlement hoặc nghĩa vụ thanh toán. Nó có thể có giới hạn về detection, thời điểm cập nhật và cách ánh xạ feature sang license. Luôn đối chiếu hợp đồng, licensing guide và người phụ trách license.

## 21. Chọn phương án theo nhu cầu thực tế

| Nhu cầu | Lựa chọn thường xem xét | Câu hỏi cần trả lời |
|---|---|---|
| Truy vấn remote theo yêu cầu | DB link | Có chấp nhận network dependency và remote availability không? |
| Báo cáo đọc nhanh, chấp nhận dữ liệu trễ | Materialized view | Refresh bao lâu một lần, complete hay fast? |
| Nạp file batch | External table | Ai tạo file, format, encoding và atomic handoff thế nào? |
| Di chuyển schema hoặc bảng theo đợt | Data Pump | Có downtime, snapshot consistency và remap nào? |
| Truy cập non-Oracle database | Gateway | Driver, datatype, pushdown, transaction và license nào? |
| Replication liên tục, downtime thấp | GoldenGate | Có license, capture/apply design, lag và conflict strategy không? |
| Tách producer/consumer | AQ/TxEventQ | Retry, duplicate, ordering và retention được xử lý ra sao? |
| API cho nhiều hệ thống ngoài | REST/ORDS | Authentication, authorization, rate limit và API contract thế nào? |

Không chọn GoldenGate chỉ vì cần một truy vấn remote; cũng không chọn DB link cho một luồng replication cần hoạt động khi nguồn tạm thời mất kết nối. Mỗi công nghệ giải quyết một kiểu coupling khác nhau.

## 22. Ví dụ thiết kế tích hợp an toàn

Giả sử ứng dụng đơn hàng cần:

- Đọc danh mục khách hàng từ CRM.
- Gửi sự kiện đơn hàng sang hệ thống thanh toán.
- Đồng bộ dữ liệu báo cáo sang kho dữ liệu.
- Nhận file danh mục mỗi đêm.

Có thể phân chia:

| Nhu cầu | Thiết kế | Phạm vi quyền |
|---|---|---|
| Đọc CRM | Private DB link hoặc API | Remote account chỉ SELECT view khách hàng |
| Gửi sự kiện | AQ/TxEventQ hoặc API message broker | Producer chỉ enqueue queue đơn hàng |
| Báo cáo | Materialized view hoặc GoldenGate tùy freshness/volume | Reader chỉ đọc view; GoldenGate capture/apply account theo script chính thức |
| File danh mục | External table | READ trên staging DIRECTORY và quyền filesystem tối thiểu |

Trước production:

- Xác nhận mọi database deployment được cấp phép.
- Kiểm tra gateway/GoldenGate/option nếu có.
- Tách credential dev/test/prod.
- Giới hạn network.
- Kiểm tra row/tenant scope.
- Kiểm tra retry, consistency và audit.
- Lập runbook khi remote system unavailable.

## 23. Kiểm tra sau khi triển khai

Sau khi tích hợp được bật, cần kiểm tra:

### Phạm vi

- Chỉ đúng schema/object được truy cập.
- Không có public DB link hoặc PUBLIC grant ngoài dự kiến.
- Filter row/column/tenant hoạt động đúng.
- Service và PDB trỏ đúng môi trường.

### Quyền

- Remote user chỉ có quyền cần thiết.
- Local user không có DBA hoặc ANY privilege không cần thiết.
- DIRECTORY chỉ cấp cho user/job phù hợp.
- GoldenGate capture/apply dùng account riêng.
- Queue producer/consumer chỉ thao tác queue của mình.
- REST scope ánh xạ đúng endpoint.

### Vận hành

- Có alert khi DB link/gateway mất kết nối.
- Có refresh status và lag monitoring cho MV/GoldenGate.
- Có dead-letter/retry cho queue.
- Có kiểm soát file staging và external table.
- Có log và audit theo yêu cầu.
- Có runbook recovery và reconcile.

### License

- Product/option/version đã được ghi nhận.
- Metric và deployment đã được xác nhận.
- DR/test/cloud/virtualization đã được xem xét.
- Có bằng chứng phê duyệt và owner.

## 24. Các lỗi thiết kế thường gặp

**Dùng public database link cho mọi ứng dụng:** mọi user có thể tham chiếu link và remote fixed account có thể trở thành cửa truy cập rộng. Ưu tiên private link và remote view/API.

**Cấp SELECT ANY TABLE ở remote:** một integration chỉ cần đọc vài bảng nhưng có thể đọc nhiều schema. Tạo remote account và view chuyên biệt.

**Dùng DB link cho replication liên tục:** truy vấn đồng bộ phụ thuộc remote availability và tạo coupling. Đánh giá queue hoặc replication platform.

**Cho rằng materialized view luôn fast refresh:** fast refresh có điều kiện. Kiểm tra query, log và release trước khi thiết kế SLA.

**Cho rằng external table đọc file ở máy client:** Oracle server đọc file theo DIRECTORY object. Đảm bảo đúng host và OS permission.

**Nhầm TABLESPACES với transportable tablespaces:** logical export khác với chuyển datafile.

**Dùng Gateway nhưng bỏ qua type mapping:** datatype, SQL function và transaction behavior có thể khác giữa hệ thống.

**Dùng GoldenGate mà không xác định conflict owner:** bidirectional replication có thể tạo xung đột và dữ liệu không nhất quán.

**Dùng XStream để né license GoldenGate:** cần xác nhận điều kiện license của XStream theo tài liệu Oracle.

**Cấp DBA cho capture/apply account:** quyền quá rộng làm tăng rủi ro nếu credential bị lộ.

**Tin rằng feature chạy được nghĩa là đã có license:** kỹ thuật và entitlement là hai việc khác nhau.

**Dùng feature usage view làm kết luận license:** view chỉ là một nguồn bằng chứng kỹ thuật.

## 25. Checklist thiết kế tích hợp

- [ ] Xác định source, target, CDB/PDB và service.
- [ ] Xác định schema, table, column, row và tenant scope.
- [ ] Chọn mô hình synchronous, asynchronous, batch hay replication.
- [ ] Xác định consistency, ordering, retry và duplicate handling.
- [ ] Chọn công nghệ và ghi rõ lý do.
- [ ] Xác định local identity, remote identity và owner.
- [ ] Cấp object privilege/role hẹp nhất.
- [ ] Kiểm soát private/public DB link và database link credentials.
- [ ] Giới hạn DIRECTORY và filesystem access.
- [ ] Kiểm tra gateway type mapping và pushdown.
- [ ] Kiểm tra GoldenGate/XStream capture/apply permissions.
- [ ] Kiểm tra REST authentication và API authorization.
- [ ] Xác nhận edition, option, product, metric và deployment license.
- [ ] Kiểm tra test, DR, cloud và virtualization.
- [ ] Lập monitoring, audit, incident và recovery runbook.
- [ ] Lưu bằng chứng kỹ thuật và license approval.

## 26. Kết luận

Các phương án tích hợp Oracle khác nhau về phạm vi, quyền và cách vận hành. DB link phục vụ truy cập remote; materialized view lưu bản sao có refresh; external table đọc file; Data Pump di chuyển logic; Gateway truy cập hệ thống không đồng nhất; GoldenGate capture/apply thay đổi liên tục; AQ/TxEventQ tách producer và consumer; REST tạo API boundary.

Thiết kế an toàn bắt đầu từ việc xác định rõ schema, object, row, tenant, thao tác và độ trễ cần thiết. Tách danh tính local/remote, ưu tiên private link, remote view hoặc package API, giới hạn quyền DIRECTORY, queue và endpoint, đồng thời bảo vệ credential và network. Distributed transaction, replication hai chiều, gateway và refresh đều có giới hạn consistency và recovery riêng.

Về license, không suy luận từ việc feature được cài đặt hoặc lệnh chạy thành công. Hãy xác định database edition, option, product, version, metric, source/target, production/test/DR và cách triển khai. GoldenGate, XStream, Gateway, Active Data Guard và một số tính năng bảo mật cần được kiểm tra riêng theo tài liệu licensing hiện hành và hợp đồng. Feature usage views chỉ hỗ trợ điều tra; quyết định entitlement phải dựa trên tài liệu và phê duyệt chính thức.
