# Flashback Transaction Query và điều kiện truy cập thông tin giao dịch trong Oracle Database

Khi phát hiện một thay đổi dữ liệu sai đã được COMMIT, DBA và đội phát triển thường cần trả lời các câu hỏi: transaction nào đã thay đổi dòng dữ liệu, thay đổi xảy ra lúc nào, user database nào thực hiện, transaction đã tác động lên những bảng nào và có thể tạo câu SQL nào để đảo ngược từng thao tác?

Oracle cung cấp **Flashback Transaction Query** để tra cứu metadata của transaction và SQL biểu diễn thao tác ngược. Tính năng này đọc từ data dictionary view FLASHBACK_TRANSACTION_QUERY. View cung cấp transaction ID (XID), thời điểm bắt đầu/commit, user đăng nhập, operation, table, ROWID và UNDO_SQL.

Trong thực tế, Flashback Transaction Query thường được dùng cùng **Flashback Version Query**. Version Query tìm các phiên bản hàng trong một khoảng SCN hoặc timestamp và cung cấp pseudocolumn VERSIONS_XID. Từ XID đó, DBA truy vấn FLASHBACK_TRANSACTION_QUERY để xem toàn bộ các thay đổi được ghi nhận trong transaction.

Để dùng được tính năng, database cần có **minimal supplemental logging** và COMPATIBLE ở mức phù hợp. Người dùng truy vấn cần system privilege SELECT ANY TRANSACTION, đây là quyền mạnh vì cho phép xem thông tin transaction trên toàn database. Nếu muốn thực thi các câu UNDO_SQL, người dùng còn cần quyền DML phù hợp trên các bảng cụ thể.

Tài liệu này tập trung vào Flashback Transaction Query và điều kiện truy cập thông tin giao dịch. Cần phân biệt nó với Flashback Transaction Backout: Query dùng để điều tra và xem SQL đảo ngược; Backout là một tính năng recovery riêng có thể thực hiện các compensating transactions và có thêm điều kiện cấu hình.

## 1. Flashback Transaction Query trong nhóm Flashback

Oracle Flashback Technology gồm nhiều tính năng có mục tiêu khác nhau. Chúng có thể được kết hợp trong một quy trình điều tra nhưng không thay thế lẫn nhau.

| Tính năng | Mục đích | Cách sử dụng |
|---|---|---|
| Flashback Query | Xem dữ liệu tại một SCN/timestamp trong quá khứ | SELECT ... AS OF SCN/TIMESTAMP |
| Flashback Version Query | Xem các phiên bản hàng trong một khoảng thời gian | VERSIONS BETWEEN SCN/TIMESTAMP |
| Flashback Transaction Query | Xem metadata và SQL đảo ngược của một transaction | Truy vấn FLASHBACK_TRANSACTION_QUERY |
| Flashback Transaction Backout | Back out transaction và transaction phụ thuộc khi database online | DBMS_FLASHBACK.TRANSACTION_BACKOUT |
| Flashback Table | Đưa một hoặc nhiều bảng về trạng thái trước đó | FLASHBACK TABLE ... TO SCN/TIMESTAMP |
| Flashback Database | Đưa toàn database về một SCN/thời điểm trước | Flashback Database với flashback logs |

### 1.1 Vai trò của Flashback Transaction Query

Giả sử người dùng báo rằng một đơn hàng đã bị xóa nhầm. DBA có thể:

1. Dùng Flashback Query hoặc Version Query để xác định trạng thái hàng trước và sau thay đổi.
2. Lấy VERSIONS_XID của transaction đã thực hiện thao tác sai.
3. Truy vấn FLASHBACK_TRANSACTION_QUERY theo XID.
4. Xem user, thời điểm, operation, table và UNDO_SQL.
5. Đánh giá ảnh hưởng đến các bảng khác trong cùng transaction.
6. Chọn phương án phục hồi phù hợp và kiểm thử trước khi thực hiện.

Flashback Transaction Query là công cụ điều tra. Việc nhìn thấy UNDO_SQL không có nghĩa Oracle đã tự động đảo transaction.

### 1.2 Phân biệt Query và Backout

Tên hai tính năng gần nhau nhưng mục đích khác nhau:

- **Flashback Transaction Query:** đọc thông tin transaction và hiển thị SQL có ý nghĩa đảo ngược từng DML.
- **Flashback Transaction Backout:** dùng DBMS_FLASHBACK.TRANSACTION_BACKOUT để tạo và thực thi các compensating transactions, có thể xử lý dependency giữa các transaction.

Backout cần điều kiện archive và supplemental logging bổ sung. Không lấy danh sách điều kiện của Backout rồi áp dụng nhầm cho thao tác Query.

## 2. View FLASHBACK_TRANSACTION_QUERY

FLASHBACK_TRANSACTION_QUERY là static data dictionary view cung cấp thông tin về các transaction có thể được truy vấn bằng Flashback Transaction Query.

### 2.1 Các cột chính

| Cột | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| XID | RAW(8) | Transaction identifier |
| START_SCN | NUMBER | SCN khi transaction bắt đầu |
| START_TIMESTAMP | DATE | Thời điểm transaction bắt đầu |
| COMMIT_SCN | NUMBER | SCN khi transaction commit; NULL với transaction đang active |
| COMMIT_TIMESTAMP | DATE | Thời điểm commit; NULL với transaction đang active |
| LOGON_USER | VARCHAR2(128) | Database user đăng nhập thực hiện transaction |
| UNDO_CHANGE# | NUMBER | Số thứ tự/định danh undo change trong transaction |
| OPERATION | VARCHAR2(32) | DML operation gốc |
| TABLE_NAME | VARCHAR2(256) | Bảng chịu tác động |
| TABLE_OWNER | VARCHAR2(386) | Schema sở hữu bảng |
| ROW_ID | VARCHAR2(19) | ROWID của hàng bị tác động |
| UNDO_SQL | VARCHAR2(4000) | SQL thể hiện thao tác logic ngược với DML gốc |

### 2.2 Giá trị OPERATION

Các giá trị được mô tả trong Database Reference:

| OPERATION | Ý nghĩa |
|---|---|
| D | DELETE |
| I | INSERT |
| U | UPDATE |
| B | Dấu mốc BEGIN của transaction |
| UNKNOWN | Operation không xác định theo nhóm hiển thị |

Một transaction thường có nhiều dòng trong view vì mỗi undo change có thể tạo một dòng metadata. Có thể có dòng B biểu diễn điểm bắt đầu transaction, không phải một DML trên bảng.

### 2.3 XID là khóa tra cứu quan trọng

XID có kiểu RAW(8). Khi biết XID dưới dạng chuỗi hexadecimal, chuyển thành RAW bằng HEXTORAW:

~~~sql
SELECT xid,
       operation,
       table_owner,
       table_name,
       row_id,
       undo_sql
FROM flashback_transaction_query
WHERE xid = HEXTORAW('000200030000002D');
~~~

Chuỗi XID trong ví dụ chỉ là dữ liệu minh họa. Trong thực tế nên lấy XID từ VERSIONS_XID hoặc nguồn điều tra đã xác minh, không đoán XID.

### 2.4 Không truy vấn toàn view nếu không cần thiết

Oracle lưu ý rằng nếu truy vấn FLASHBACK_TRANSACTION_QUERY mà không chỉ định XID trong WHERE clause, câu lệnh có thể quét nhiều dòng transaction không liên quan và làm giảm hiệu năng.

Ưu tiên lọc theo XID:

~~~sql
WHERE xid = :p_xid
~~~

Nếu cần điều tra theo thời gian, hãy dùng Version Query để tìm các XID liên quan trước, sau đó truy vấn transaction metadata theo từng XID. Không dùng một truy vấn không giới hạn làm công cụ polling thường xuyên.

## 3. Điều kiện cấu hình database

Oracle Database 19c mô tả hai điều kiện cấu hình trực tiếp cho Flashback Transaction Query:

1. Database phải chạy với COMPATIBLE từ 10.0 trở lên.
2. Phải bật ít nhất minimal supplemental logging.

Đây là điều kiện của Flashback Transaction Query. Các yêu cầu như ARCHIVELOG, primary key supplemental logging và foreign key supplemental logging thuộc cấu hình Flashback Transaction Backout hoặc các mục tiêu LogMiner/recovery cụ thể khác.

### 3.1 Kiểm tra COMPATIBLE

~~~sql
SHOW PARAMETER compatible;
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'compatible';
~~~

Tài liệu Oracle yêu cầu compatibility 10.0.0 trở lên để cấu hình Flashback Transaction Query. Trên các database release hiện đại, giá trị mặc định thường đã đáp ứng yêu cầu, nhưng vẫn cần kiểm tra nếu hệ thống giữ COMPATIBLE thấp sau upgrade.

### 3.2 Bật minimal supplemental logging

Lệnh do DBA thực hiện:

~~~sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;
~~~

Minimal supplemental logging bổ sung thông tin cần thiết vào redo để hỗ trợ các thao tác khai thác thay đổi. Nó có thể tạo thêm redo overhead, nên phải được đánh giá trong chính sách vận hành và logging của database.

Không bật supplemental logging sau khi sự cố đã xảy ra rồi kỳ vọng dữ liệu redo cũ được bổ sung ngược trở lại. Logging chỉ ghi thông tin bổ sung cho các thay đổi phát sinh sau khi được bật.

### 3.3 Kiểm tra supplemental logging

~~~sql
SELECT supplemental_log_data_min,
       supplemental_log_data_pk,
       supplemental_log_data_ui,
       supplemental_log_data_fk
FROM v$database;
~~~

SUPPLEMENTAL_LOG_DATA_MIN phản ánh trạng thái minimal supplemental logging. Các cột PK/UI/FK thể hiện các nhóm supplemental logging cụ thể. Tên/cột có thể khác theo phiên bản; kiểm tra Database Reference của release đang chạy.

### 3.4 Bật logging ở phạm vi database hay table?

Điều kiện cấu hình trong tài liệu Flashback Transaction Query yêu cầu minimal supplemental logging ở database. Các dạng supplemental logging bổ sung theo primary key, unique index hoặc foreign key có thể cần cho mục tiêu LogMiner/transaction dependency khác.

Không tự bật tất cả nhóm logging chỉ vì đang dùng Flashback Transaction Query. Xác định mục tiêu:

- Chỉ truy vấn metadata/UNDO_SQL: bắt đầu từ minimal supplemental logging theo yêu cầu tài liệu.
- Backout transaction có dependency: cần primary key logging và có thể foreign key logging.
- CDC/LogMiner hoặc replication: tuân theo yêu cầu cụ thể của công nghệ đó.

## 4. Điều kiện truy cập và quyền cần cấp

### 4.1 SELECT ANY TRANSACTION

Oracle yêu cầu system privilege:

~~~sql
GRANT SELECT ANY TRANSACTION TO flash_txn_auditor;
~~~

Quyền này cho phép truy vấn nội dung của FLASHBACK_TRANSACTION_QUERY. Đây là quyền mạnh vì người được cấp có thể xem thông tin transaction của toàn database, bao gồm dữ liệu lịch sử. Chỉ cấp cho DBA hoặc tài khoản điều tra được ủy quyền, không cấp rộng cho user ứng dụng thông thường.

Có thể cấp qua role chuyên biệt:

~~~sql
CREATE ROLE flash_txn_query_role;

GRANT SELECT ANY TRANSACTION TO flash_txn_query_role;

GRANT flash_txn_query_role TO flash_txn_auditor;
~~~

Role cần được enable trong session theo cách ứng dụng/DBA sử dụng. Với PL/SQL definer-rights, quyền qua role không thay thế direct grants trong mọi ngữ cảnh; kiểm tra privilege model của unit nếu truy vấn view bên trong stored code.

### 4.2 Quyền để thực thi UNDO_SQL

Để đọc UNDO_SQL, người dùng cần SELECT ANY TRANSACTION. Nếu muốn thực thi SQL được tạo ra, Oracle yêu cầu quyền SELECT, UPDATE, DELETE và INSERT trên các bảng cụ thể liên quan.

Ví dụ cho một bảng:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON app.orders
TO flash_txn_operator;
~~~

Chỉ cấp quyền trên những bảng thật sự cần phục hồi. Không cấp INSERT ANY TABLE, UPDATE ANY TABLE hoặc DELETE ANY TABLE chỉ để tiện chạy undo SQL.

### 4.3 Quyền truy cập không đồng nghĩa quyền phục hồi

Có thể chia vai trò:

| Vai trò | Quyền phù hợp |
|---|---|
| Auditor điều tra | SELECT ANY TRANSACTION, quyền đọc dữ liệu cần thiết |
| DBA phân tích | Quyền dictionary/monitoring theo chính sách DBA |
| Operator thực hiện phục hồi | Quyền DML trên bảng được phê duyệt; quyền bổ sung nếu dùng Backout |
| Ứng dụng nghiệp vụ | Không nên có SELECT ANY TRANSACTION chỉ để phục vụ chức năng thông thường |

Tài khoản có thể xem UNDO_SQL nhưng không được thực thi nó. Đây là cách tách biệt quyền điều tra khỏi quyền sửa dữ liệu.

### 4.4 Unified Auditing từ 19c RU 19.32

Từ Oracle Database 19c Release Update 19.32, unified auditing ghi nhận việc sử dụng system privilege SELECT ANY TRANSACTION khi truy cập FLASHBACK_TRANSACTION_QUERY. Tính năng này giúp quản trị viên có khả năng audit tốt hơn đối với việc truy cập dữ liệu transaction lịch sử bằng quyền mạnh.

Nếu hệ thống ở RU thấp hơn, không mặc định rằng hành vi audit này đã có. Kiểm tra release update và chính sách unified auditing đang áp dụng.

## 5. Tìm XID bằng Flashback Version Query

Trong nhiều tình huống, DBA biết bảng và hàng bị thay đổi nhưng chưa biết transaction ID. Flashback Version Query có thể tìm các phiên bản của hàng và trả về VERSIONS_XID, VERSIONS_OPERATION, VERSIONS_STARTSCN và VERSIONS_ENDSCN.

### 5.1 Cú pháp VERSIONS BETWEEN

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_xid,
       versions_operation,
       employee_id,
       salary
FROM employees
VERSIONS BETWEEN SCN MINVALUE AND MAXVALUE
WHERE employee_id = :p_employee_id;
~~~

VERSIONS BETWEEN SCN MINVALUE AND MAXVALUE yêu cầu các phiên bản hàng còn có thể truy cập trong phạm vi undo hiện có. Trong ứng dụng thực tế, nên giới hạn bằng SCN hoặc timestamp cụ thể để tránh đọc khoảng thời gian quá rộng.

### 5.2 Tìm thay đổi trong một khoảng thời gian

~~~sql
SELECT versions_starttime,
       versions_endtime,
       versions_xid,
       versions_operation,
       order_id,
       status,
       total_amount
FROM orders
VERSIONS BETWEEN TIMESTAMP
    TO_TIMESTAMP('2026-11-14 08:00:00', 'YYYY-MM-DD HH24:MI:SS')
AND TO_TIMESTAMP('2026-11-14 10:00:00', 'YYYY-MM-DD HH24:MI:SS')
WHERE order_id = :p_order_id
ORDER BY versions_starttime;
~~~

Các mốc thời gian trong ví dụ là minh họa. Dùng timestamp phù hợp với timezone và thời gian của database. Nếu cần ranh giới chính xác theo database change, dùng SCN.

### 5.3 Ý nghĩa VERSIONS_OPERATION

| Giá trị | Ý nghĩa |
|---|---|
| I | Row version được tạo bởi INSERT |
| U | Row version được tạo bởi UPDATE |
| D | Row version liên quan DELETE |

Pseudocolumn VERSIONS_OPERATION mô tả operation tạo ra row version được trả về. Với DELETE, version hiển thị là dữ liệu của hàng trước khi bị xóa. Một số cập nhật index key có thể được biểu diễn như DELETE cộng INSERT trong Version Query.

### 5.4 VERSIONS_XID và transaction metadata

VERSIONS_XID là RAW transaction identifier. Có thể nối trực tiếp với FLASHBACK_TRANSACTION_QUERY:

~~~sql
SELECT DISTINCT
       ftq.xid,
       ftq.start_scn,
       ftq.commit_scn,
       ftq.logon_user,
       ftq.operation,
       ftq.table_owner,
       ftq.table_name,
       ftq.undo_sql
FROM flashback_transaction_query ftq
WHERE ftq.xid IN (
    SELECT versions_xid
    FROM orders VERSIONS BETWEEN SCN MINVALUE AND MAXVALUE
    WHERE order_id = :p_order_id
      AND versions_xid IS NOT NULL
);
~~~

Đây là quy trình Oracle thường dùng: Version Query tìm XID của các row version cần điều tra; Transaction Query cung cấp metadata của transaction đó.

### 5.5 Một transaction có thể thay đổi nhiều bảng

Version Query trên một hàng chỉ cho biết transaction đã tạo row version của hàng đó. Khi đã tìm được XID, truy vấn FLASHBACK_TRANSACTION_QUERY theo XID có thể cho thấy các DML khác của cùng transaction trên các bảng khác.

Ví dụ một transaction có thể:

- Cập nhật ORDERS.
- Cập nhật INVENTORY.
- Ghi ORDER_AUDIT.
- Xóa một dòng staging.
- Commit tất cả thay đổi trong một transaction.

Điều tra theo XID giúp xác định phạm vi transaction đầy đủ hơn so với chỉ xem một row.

## 6. Truy vấn FLASHBACK_TRANSACTION_QUERY theo XID

### 6.1 Truy vấn chi tiết một transaction

~~~sql
SELECT xid,
       start_scn,
       start_timestamp,
       commit_scn,
       commit_timestamp,
       logon_user,
       undo_change#,
       operation,
       table_owner,
       table_name,
       row_id,
       undo_sql
FROM flashback_transaction_query
WHERE xid = HEXTORAW(:p_xid_hex)
ORDER BY undo_change#;
~~~

P_XID_HEX là chuỗi hexadecimal đã được xác định từ nguồn tin cậy. Nếu ứng dụng đã có XID dạng RAW, bind trực tiếp:

~~~sql
WHERE xid = :p_xid
~~~

Không chuyển XID thành VARCHAR2 để so sánh nếu có thể bind RAW đúng kiểu.

### 6.2 Xem tóm tắt transaction

~~~sql
SELECT xid,
       MIN(start_scn) AS start_scn,
       MAX(commit_scn) AS commit_scn,
       MIN(start_timestamp) AS start_timestamp,
       MAX(commit_timestamp) AS commit_timestamp,
       MAX(logon_user) AS logon_user,
       COUNT(CASE WHEN operation IN ('I', 'U', 'D') THEN 1 END)
           AS dml_change_count,
       COUNT(DISTINCT table_owner || '.' || table_name)
           AS affected_table_count
FROM flashback_transaction_query
WHERE xid = HEXTORAW(:p_xid_hex)
GROUP BY xid;
~~~

Đây là bản tóm tắt để định hướng điều tra. Dòng BEGIN không được tính vào dml_change_count. Nếu transaction chạm vào nhiều schema, tên owner/table phải được giữ riêng để tránh nhầm object.

### 6.3 Lọc theo schema và bảng

~~~sql
SELECT xid,
       start_timestamp,
       commit_timestamp,
       operation,
       table_owner,
       table_name,
       row_id,
       undo_sql
FROM flashback_transaction_query
WHERE xid = HEXTORAW(:p_xid_hex)
  AND table_owner = UPPER(:p_owner)
  AND table_name = UPPER(:p_table)
ORDER BY undo_change#;
~~~

Điều kiện owner/table có ích khi đã biết phạm vi cần xem, nhưng XID vẫn là bộ lọc quan trọng nhất để giới hạn transaction.

### 6.4 Transaction đang active

COMMIT_SCN và COMMIT_TIMESTAMP có thể NULL đối với transaction chưa commit. Flashback Transaction Query thường được dùng để điều tra transaction đã hoàn tất, nhưng metadata cũng mô tả các transaction active nếu có thể truy cập. Không xem NULL commit timestamp là một giá trị lỗi nếu transaction vẫn đang mở.

### 6.5 LOGON_USER không phải lúc nào cũng là người dùng cuối

LOGON_USER là database user đăng nhập thực hiện transaction. Nếu ứng dụng dùng một schema chung hoặc connection pool, LOGON_USER có thể chỉ là APP_USER chứ không phải người dùng cuối trên website.

Để truy vết actor nghiệp vụ, ứng dụng cần thiết kế thêm audit trail, unified auditing, CLIENT_IDENTIFIER, MODULE/ACTION hoặc các thuộc tính request phù hợp. Flashback Transaction Query không tự biết user đăng nhập ở tầng ứng dụng nếu database chỉ thấy một shared account.

## 7. UNDO_RETENTION và giới hạn lịch sử

Flashback Version Query cần các row versions còn có thể dựng lại từ undo. Vì vậy, nếu quy trình điều tra bắt đầu từ một hàng và cần tìm VERSIONS_XID, thời gian lưu undo ảnh hưởng trực tiếp đến khả năng tìm transaction ID.

### 7.1 Automatic Undo Management

Flashback features dùng Automatic Undo Management (AUM) và undo tablespace để giữ dữ liệu lịch sử. DBA cần bảo đảm undo tablespace đủ dung lượng cho tốc độ thay đổi dữ liệu và thời gian lịch sử cần truy vấn.

Kiểm tra cấu hình:

~~~sql
SHOW PARAMETER undo;
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'undo_management',
    'undo_tablespace',
    'undo_retention'
);
~~~

### 7.2 UNDO_RETENTION là mục tiêu, không phải cam kết tuyệt đối

Đặt UNDO_RETENTION chỉ định khoảng thời gian Oracle cố gắng giữ undo. Trong undo tablespace fixed-size, Oracle tự điều chỉnh retention theo không gian có sẵn. Với undo tablespace autoextend, Oracle có thể giữ undo lâu hơn để đáp ứng retention threshold và các query dài.

Tuy nhiên, nếu hệ thống thiếu chỗ, Oracle có thể ghi đè undo chưa hết hạn để phục vụ workload mới, trừ khi tablespace được cấu hình RETENTION GUARANTEE. Vì vậy, không thể chỉ nhìn giá trị UNDO_RETENTION rồi khẳng định chắc chắn mọi version trong khoảng đó đều còn truy vấn được.

### 7.3 Xem tuned undo retention

~~~sql
SELECT begin_time,
       end_time,
       tuned_undoretention,
       undoblks,
       txncount,
       maxquerylen,
       ssolderrcnt,
       nospaceerrcnt
FROM v$undostat
ORDER BY begin_time DESC
FETCH FIRST 24 ROWS ONLY;
~~~

TUNED_UNDORETENTION giúp DBA ước lượng thời gian undo thực tế được giữ trong các khoảng thống kê. UNDO_RETENTION và TUNED_UNDORETENTION là hai khái niệm khác nhau.

### 7.4 RETENTION GUARANTEE

Undo tablespace có thể được cấu hình RETENTION GUARANTEE để Oracle không ghi đè unexpired undo. Cấu hình này giúp bảo vệ thời gian flashback đã cam kết, nhưng có đánh đổi: nếu undo tablespace hết chỗ, các DML mới có thể thất bại vì không thể ghi undo.

Ví dụ cấu hình tablespace:

~~~sql
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;
~~~

Chỉ DBA mới nên thay đổi thiết lập này sau khi đánh giá dung lượng, workload và rủi ro ảnh hưởng DML. Không bật guarantee trên production chỉ để giải quyết một truy vấn flashback mà chưa tính capacity.

### 7.5 UNDO_RETENTION ảnh hưởng phần nào trong quy trình?

Phân biệt hai bước:

- **Tìm XID bằng Flashback Version Query:** phụ thuộc vào việc row versions cần thiết còn được dựng lại từ undo hay không.
- **Tra metadata theo XID trong FLASHBACK_TRANSACTION_QUERY:** cần supplemental logging và transaction metadata còn khả dụng; truy vấn theo XID đã biết không phải cùng một thao tác với đọc lại row version.

Nếu lịch sử undo đã hết, Version Query có thể không tìm được phiên bản cần thiết hoặc gặp lỗi snapshot too old. Khi đó, cần xem XID từ audit/log/nguồn khác nếu có; tăng UNDO_RETENTION hiện tại không tái tạo lại undo đã bị ghi đè.

## 8. Đọc và sử dụng UNDO_SQL

UNDO_SQL là SQL code thể hiện thao tác logic ngược với DML trong transaction. Ví dụ:

| DML gốc | UNDO_SQL có thể biểu diễn |
|---|---|
| INSERT một row | DELETE row đó |
| DELETE một row | INSERT lại dữ liệu cũ |
| UPDATE một row | UPDATE trả các cột về giá trị trước |

Đây là SQL gợi ý cho thao tác đảo ngược, không phải một bản backup đầy đủ của transaction.

### 8.1 UNDO_SQL không luôn là nghịch đảo vật lý chính xác

Oracle cảnh báo rằng UNDO_SQL có thể không phải thao tác đối nghịch chính xác trong mọi trường hợp. Ví dụ, khi UNDO_SQL tạo lại một row đã bị DELETE, row mới có thể không có cùng ROWID như row ban đầu.

Các yếu tố cần xem xét:

- Trigger có thể chạy lại khi thực thi SQL đảo ngược.
- Constraint hoặc foreign key có thể không còn ở trạng thái giống lúc transaction gốc chạy.
- Dữ liệu liên quan có thể đã bị transaction khác thay đổi.
- Sequence, identity, external side effects và logic ứng dụng không tự quay ngược.
- Một transaction có thể đã thay đổi nhiều bảng và tạo dependency giữa các thay đổi.
- UNDO_SQL có thể dùng ROWID; ROWID cũ có thể không còn phù hợp sau các thao tác tiếp theo.

### 8.2 Không thực thi UNDO_SQL hàng loạt mà không review

Quy trình an toàn:

1. Xác định chính xác XID và phạm vi transaction.
2. Đọc tất cả rows của transaction, bao gồm bảng liên quan.
3. Đối chiếu với trạng thái dữ liệu hiện tại và các transaction sau đó.
4. Kiểm tra constraints, triggers, cascade rules và side effects.
5. Sao lưu hoặc tạo điểm phục hồi phù hợp trước thao tác.
6. Thử trên clone/test database nếu có thể.
7. Chọn phương pháp phục hồi: DML thủ công, Flashback Table, Flashback Transaction Backout hoặc phương án recovery khác.
8. Thực hiện trong transaction được kiểm soát, kiểm tra số dòng ảnh hưởng và commit theo quy trình change management.

Không copy toàn bộ UNDO_SQL từ view sang SQL worksheet rồi chạy ngay trên production.

### 8.3 Quyền để chạy undo SQL

Nếu transaction tác động APP.ORDERS, APP.INVENTORY và APP.ORDER_AUDIT, operator cần quyền phù hợp trên từng bảng. Ví dụ:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON app.orders
TO flash_txn_operator;

GRANT SELECT, INSERT, UPDATE, DELETE
ON app.inventory
TO flash_txn_operator;

GRANT SELECT, INSERT, UPDATE, DELETE
ON app.order_audit
TO flash_txn_operator;
~~~

Chỉ cấp quyền trên các object được phê duyệt. Nếu dùng Flashback Transaction Backout, cần thêm quyền EXECUTE trên package và các điều kiện riêng của tính năng đó.

## 9. Quy trình điều tra transaction sai

Một quy trình điển hình kết hợp Flashback Version Query và Flashback Transaction Query:

~~~text
Phát hiện dữ liệu sai
        |
        v
Xác định bảng, khóa hàng và khoảng thời gian
        |
        v
Flashback Version Query
VERSIONS BETWEEN SCN/TIMESTAMP
        |
        v
Lấy VERSIONS_XID
        |
        v
FLASHBACK_TRANSACTION_QUERY
WHERE XID = ...
        |
        v
Đọc LOGON_USER, operation, table, ROWID, UNDO_SQL
        |
        v
Đánh giá toàn bộ transaction và các transaction sau đó
        |
        v
Chọn phương án phục hồi phù hợp
        |
        v
Test, review, backup và thực hiện có kiểm soát
~~~

### 9.1 Bước 1: xác định hàng và khoảng thời gian

Thu thập primary key, bảng, schema, thời điểm phát hiện và thời điểm dữ liệu còn đúng. Nếu chỉ biết thời gian gần đúng, dùng một khoảng Version Query đủ hẹp để giảm số row versions.

### 9.2 Bước 2: lấy các XID liên quan

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_xid,
       versions_operation,
       order_id,
       status,
       total_amount
FROM app.orders
VERSIONS BETWEEN TIMESTAMP
    TO_TIMESTAMP('2026-11-14 08:00:00', 'YYYY-MM-DD HH24:MI:SS')
AND TO_TIMESTAMP('2026-11-14 10:00:00', 'YYYY-MM-DD HH24:MI:SS')
WHERE order_id = :p_order_id
ORDER BY versions_startscn;
~~~

Ghi lại XID của version sai. Một hàng có thể có nhiều version và nhiều XID nếu được thay đổi nhiều lần.

### 9.3 Bước 3: xem toàn bộ transaction

~~~sql
SELECT xid,
       start_timestamp,
       commit_timestamp,
       logon_user,
       operation,
       table_owner,
       table_name,
       row_id,
       undo_sql
FROM flashback_transaction_query
WHERE xid = :p_xid
ORDER BY undo_change#;
~~~

Đây là bước để biết transaction có thay đổi các bảng khác hay không. Đừng chỉ phục hồi bảng đầu tiên được phát hiện nếu transaction gốc đã cập nhật nhiều object.

### 9.4 Bước 4: đối chiếu trạng thái hiện tại

UNDO_SQL mô tả thao tác ngược với thay đổi của transaction được chọn. Trước khi dùng, phải kiểm tra dữ liệu hiện tại có bị các transaction sau đó thay đổi hay không. Nếu một row đã được sửa hợp lệ sau transaction sai, áp dụng undo cũ có thể xóa mất thay đổi hợp lệ mới.

### 9.5 Bước 5: chọn công cụ phục hồi

| Tình huống | Hướng xử lý có thể cân nhắc |
|---|---|
| Một vài row bị sửa/xóa, chưa có thay đổi phụ thuộc | Dùng Flashback Query để lấy giá trị cũ và DML có kiểm soát |
| Nhiều row trong một bảng, muốn đưa cả bảng về thời điểm trước | Đánh giá Flashback Table |
| Một transaction sai và các transaction phụ thuộc cần được xử lý | Đánh giá Flashback Transaction Backout |
| Dữ liệu hỏng trên phạm vi lớn hoặc cần quay cả database | Đánh giá point-in-time recovery/Flashback Database |
| Chỉ cần xác định actor và phạm vi thay đổi | Flashback Transaction Query và audit logs |

Không chọn phương án chỉ dựa vào việc UNDO_SQL có sẵn. Phải xét dependency, thời gian, dữ liệu phát sinh sau đó và recovery objective.

## 10. Flashback Transaction Backout: tính năng khác với Query

Flashback Transaction Backout là cơ chế recovery trong package DBMS_FLASHBACK. Nó có thể back out một transaction và các transaction phụ thuộc trong khi database vẫn online bằng cách tạo và thực thi compensating transactions.

Flashback Transaction Query chỉ hiển thị metadata và UNDO_SQL. Nó không gọi Backout và không tự thực thi SQL.

### 10.1 Điều kiện cấu hình riêng cho Backout

Theo tài liệu Oracle Database 19c, để dùng Flashback Transaction Backout, DBA cần:

1. Bật ARCHIVELOG mode.
2. Archive ít nhất một log.
3. Bật minimal supplemental logging.
4. Bật primary key supplemental logging.
5. Nếu cần theo dõi foreign key dependencies, bật foreign key supplemental logging.

Các lệnh minh họa:

~~~sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA (PRIMARY KEY) COLUMNS;
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA (FOREIGN KEY) COLUMNS;
~~~

Foreign key supplemental logging có thể tạo overhead, đặc biệt database có nhiều foreign key constraints. Chỉ bật khi nhu cầu dependency analysis của Backout yêu cầu.

Việc chuyển NOARCHIVELOG sang ARCHIVELOG cần database ở trạng thái MOUNT theo quy trình quản trị:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
ALTER SYSTEM ARCHIVE LOG CURRENT;
~~~

Đây là thao tác quản trị có ảnh hưởng vận hành, không phải bước bắt buộc để chỉ đọc FLASHBACK_TRANSACTION_QUERY theo cấu hình 19c.

### 10.2 Quyền thực thi Backout

Để sử dụng các chức năng trong DBMS_FLASHBACK, Oracle yêu cầu quyền EXECUTE trên package:

~~~sql
GRANT EXECUTE ON SYS.DBMS_FLASHBACK TO flash_txn_operator;
~~~

Ngoài ra, operator cần các quyền liên quan để đọc metadata và thực hiện thao tác trên object theo quy trình được phê duyệt. Không cấp quyền Backout rộng hơn nhu cầu.

### 10.3 Dependency giữa transactions

Nếu transaction B phụ thuộc vào dữ liệu do transaction A tạo ra, back out A có thể cần back out B hoặc xử lý conflict. DBMS_FLASHBACK.TRANSACTION_BACKOUT hỗ trợ các lựa chọn dependency như CASCADE, NONCONFLICT_ONLY và NOCASCADE_FORCE tùy tình huống.

Không chọn NOCASCADE_FORCE chỉ để ép backout thành công. Nếu transaction sau đã dựa vào dữ liệu của transaction trước, force có thể tạo ra trạng thái nghiệp vụ không nhất quán.

### 10.4 Các giới hạn của Backout

Các giới hạn dưới đây thuộc Flashback Transaction Backout, không nên áp dụng nhầm thành kết luận rằng mọi truy vấn FLASHBACK_TRANSACTION_QUERY đều không thể xem transaction:

- Transaction có DDL làm thay đổi cấu trúc logic của bảng không thể được back out theo cơ chế này.
- Các transaction sử dụng LOB types như BFILE, BLOB, CLOB và NCLOB bị giới hạn theo tài liệu.
- Các feature mà LogMiner không hỗ trợ không thể được xử lý đầy đủ.
- PDML và một số XA/RAC transaction branches có thể không được hỗ trợ.
- AQ transaction có thể không back out được vì tác động bên ngoài database không thể quan sát đầy đủ.

Trước khi dùng Backout, đối chiếu giới hạn của đúng release, COMPATIBLE và loại transaction trong workload.

## 11. Bài lab: tìm XID và xem UNDO_SQL

Lab sau minh họa cách tạo dữ liệu, thực hiện một transaction có nhiều DML, tìm XID bằng Version Query rồi truy vấn metadata.

### 11.1 Điều kiện trước khi chạy

- Chạy trong schema lab, không chạy trên bảng production.
- Database đã bật minimal supplemental logging.
- COMPATIBLE đáp ứng điều kiện của Flashback Transaction Query.
- Tài khoản điều tra có SELECT ANY TRANSACTION.
- Tài khoản có quyền đọc bảng lab và sử dụng Version Query theo quyền phù hợp.

### 11.2 Tạo bảng

~~~sql
CREATE TABLE flash_txn_lab (
    id          NUMBER PRIMARY KEY,
    description VARCHAR2(100),
    amount      NUMBER
);
~~~

Sau CREATE TABLE, Oracle khuyến nghị chờ ít nhất 15 giây trước khi commit transaction cần được Flashback Version Query phản ánh. Hãy đợi khoảng thời gian này trong lab.

### 11.3 Tạo dữ liệu ban đầu

~~~sql
INSERT INTO flash_txn_lab VALUES (1, 'Order A', 100);
INSERT INTO flash_txn_lab VALUES (2, 'Order B', 200);
INSERT INTO flash_txn_lab VALUES (3, 'Order C', 300);
COMMIT;
~~~

### 11.4 Thực hiện transaction có nhiều thay đổi

~~~sql
UPDATE flash_txn_lab
SET amount = 150,
    description = 'Order A updated'
WHERE id = 1;

DELETE FROM flash_txn_lab
WHERE id = 2;

INSERT INTO flash_txn_lab
    (id, description, amount)
VALUES
    (4, 'Order D', 400);

COMMIT;
~~~

Ba DML trên cùng một session và cùng transaction trước COMMIT. Mục tiêu là xem một XID có thể chứa nhiều thay đổi.

### 11.5 Tìm XID qua Version Query

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_xid,
       versions_operation,
       id,
       description,
       amount
FROM flash_txn_lab
VERSIONS BETWEEN SCN MINVALUE AND MAXVALUE
WHERE id IN (1, 2, 4)
ORDER BY versions_startscn;
~~~

Ghi lại XID ứng với transaction vừa chạy. Một số hàng có thể có nhiều row versions; hãy đối chiếu SCN và operation để chọn đúng XID.

### 11.6 Truy vấn transaction metadata

~~~sql
SELECT xid,
       start_scn,
       commit_scn,
       start_timestamp,
       commit_timestamp,
       logon_user,
       undo_change#,
       operation,
       table_owner,
       table_name,
       row_id,
       undo_sql
FROM flashback_transaction_query
WHERE xid = HEXTORAW(:p_xid_hex)
ORDER BY undo_change#;
~~~

Kết quả có thể hiển thị UPDATE, DELETE, INSERT và một dòng BEGIN. UNDO_SQL sẽ chứa các câu lệnh logic ngược với các DML đã thực hiện.

### 11.7 Đối chiếu với trạng thái hiện tại

~~~sql
SELECT *
FROM flash_txn_lab
ORDER BY id;
~~~

So sánh trạng thái hiện tại với các version lịch sử. Không thực thi UNDO_SQL trong lab nếu chưa đọc kỹ thứ tự và ảnh hưởng; mục tiêu của bài lab là quan sát metadata và hiểu mối quan hệ XID.

### 11.8 Dọn dữ liệu lab

~~~sql
DROP TABLE flash_txn_lab PURGE;
~~~

Chỉ chạy DROP TABLE nếu đây là bảng lab vừa tạo và không chứa dữ liệu cần giữ.

## 12. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| ORA-01031 insufficient privileges | Thiếu SELECT ANY TRANSACTION hoặc quyền flashback trên object khi chạy Version Query | Cấp đúng privilege tối thiểu theo tính năng đang dùng |
| FLASHBACK_TRANSACTION_QUERY không trả transaction mong đợi | Chưa bật supplemental logging khi transaction phát sinh, XID sai hoặc metadata không còn khả dụng | Kiểm tra supplemental logging, XID và thời điểm transaction |
| Version Query không tìm được row version cũ | Undo đã bị ghi đè hoặc khoảng thời gian ngoài retention thực tế | Kiểm tra V$UNDOSTAT, undo tablespace và retention |
| ORA-01555 snapshot too old | Undo cần cho consistent read/flashback đã bị ghi đè | Tăng capacity/retention phù hợp và giới hạn thời gian query |
| Truy vấn view quá chậm | Không lọc theo XID | Lấy XID từ Version Query rồi lọc trực tiếp |
| UNDO_SQL không đúng như kỳ vọng | UNDO_SQL là logical opposite, không luôn phục hồi ROWID hoặc side effects | Review constraints, triggers, dữ liệu hiện tại và transaction phụ thuộc |
| Không thể chạy UNDO_SQL | Thiếu quyền DML trên bảng hoặc SQL không còn phù hợp với trạng thái hiện tại | Cấp quyền object tối thiểu sau phê duyệt; đánh giá lại SQL |
| LOGON_USER không phải end user | Ứng dụng dùng shared schema/connection pool | Dùng audit trail, CLIENT_IDENTIFIER và MODULE/ACTION |
| Không thấy transaction trước khi bật supplemental logging | Supplemental logging không bổ sung ngược vào redo cũ | Không thể sửa dữ liệu lịch sử bằng cách bật logging sau sự cố |
| Nhầm Query với Backout | Hai tính năng có yêu cầu cấu hình và tác động khác nhau | Dùng Query để điều tra; Backout để thực hiện compensating transactions |
| Backout báo conflict/dependency | Transaction sau phụ thuộc transaction cần back out | Phân tích dependency; chọn phương án CASCADE/NONCONFLICT_ONLY theo quy trình |

## 13. Bảo mật và vận hành

### 13.1 Bảo vệ SELECT ANY TRANSACTION

SELECT ANY TRANSACTION là system privilege mạnh. Nên:

- Cấp cho role chuyên biệt, chỉ thành viên DBA/auditor được phê duyệt.
- Không cấp cho PUBLIC hoặc schema ứng dụng thông thường.
- Review định kỳ người dùng và role đang giữ privilege.
- Audit việc sử dụng privilege theo release và unified auditing policy.
- Không đưa kết quả UNDO_SQL hoặc dữ liệu lịch sử nhạy cảm vào log không được bảo vệ.

### 13.2 Tách điều tra và thực thi

Một quy trình kiểm soát tốt tách hai tài khoản hoặc hai vai trò:

- Tài khoản điều tra chỉ đọc transaction metadata và dữ liệu cần thiết.
- Tài khoản vận hành recovery chỉ có quyền DML trên các object được phê duyệt, dùng khi đã có change approval.

Việc tách vai trò giúp tránh tình huống người có quyền xem toàn bộ lịch sử cũng đồng thời có quyền sửa toàn bộ dữ liệu.

### 13.3 Supplemental logging và redo overhead

Supplemental logging làm tăng lượng redo vì Oracle ghi thêm thông tin cần thiết. Minimal logging là điều kiện cấu hình cho Flashback Transaction Query; các nhóm primary key/foreign key có thể tạo thêm overhead đáng kể tùy workload.

Đo redo generation và archive throughput trước/sau khi thay đổi logging. Cần phối hợp với chính sách Data Guard, LogMiner, CDC và recovery hiện có.

### 13.4 CDB/PDB

Trong multitenant, hãy kết nối đúng container chứa bảng cần điều tra và kiểm tra privilege được cấp trong phạm vi phù hợp. Với quyền common/local và dữ liệu transaction ở PDB, tuân theo chính sách cấp quyền của CDB; không giả định grant trong root tự động tương đương grant local trong mọi ngữ cảnh.

Kiểm tra container hiện tại:

~~~sql
SHOW CON_NAME;
~~~

Hoặc:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Khi điều tra nhiều PDB, ghi rõ PDB/service và schema để tránh nhầm lẫn giữa các object trùng tên.

### 13.5 RAC

Trong RAC, transaction có thể phát sinh từ các instance khác nhau. DBA nên giữ thông tin database/service/instance trong hồ sơ sự cố và đối chiếu transaction XID với các nguồn audit/monitoring khác. Không suy ra instance thực hiện chỉ từ LOGON_USER.

Các transaction XA hoặc PDML/RAC branches có thể chịu giới hạn riêng khi dùng Flashback Transaction Backout; điều này không đồng nghĩa mọi truy vấn metadata bằng Flashback Transaction Query đều bị loại trừ.

## 14. Checklist trước khi truy vấn hoặc phục hồi transaction

### Điều kiện truy cập

1. Database đang chạy với COMPATIBLE từ 10.0 trở lên chưa?
2. Minimal supplemental logging đã được bật trước khi transaction cần điều tra phát sinh chưa?
3. Tài khoản có SELECT ANY TRANSACTION chưa?
4. Nếu dùng Version Query, tài khoản có quyền FLASHBACK và READ/SELECT trên object hoặc quyền hệ thống phù hợp chưa?
5. Đã kết nối đúng PDB/service chưa?
6. Nếu cần thực thi UNDO_SQL, đã cấp SELECT/INSERT/UPDATE/DELETE trên đúng bảng chưa?

### Điều kiện dữ liệu lịch sử

1. Đã xác định bảng, khóa hàng và khoảng SCN/timestamp chưa?
2. Undo cần cho Version Query còn trong retention thực tế không?
3. Đã kiểm tra V$UNDOSTAT.TUNED_UNDORETENTION chưa?
4. Có nguy cơ snapshot too old hoặc undo tablespace thiếu chỗ không?
5. Đã lọc FLASHBACK_TRANSACTION_QUERY theo XID chưa?
6. Đã kiểm tra mọi bảng và DML thuộc transaction chưa?
7. LOGON_USER có đại diện cho user cuối hay chỉ là schema ứng dụng?

### Trước khi thực thi SQL đảo ngược

1. Đã review từng UNDO_SQL chưa?
2. Đã xem các transaction phát sinh sau transaction sai chưa?
3. Đã đánh giá trigger, constraint, foreign key và side effects chưa?
4. Đã kiểm tra ROWID và trạng thái hiện tại của hàng chưa?
5. Đã có backup/restore point hoặc phương án rollback phù hợp chưa?
6. Đã thử trên môi trường test/clone chưa?
7. Đã có phê duyệt thay đổi và xác định operator chưa?
8. Nếu dùng Backout, đã đáp ứng ARCHIVELOG và supplemental logging tương ứng chưa?

## 15. Tổng kết

Flashback Transaction Query giúp truy tìm metadata của transaction và SQL có ý nghĩa đảo ngược các DML đã thực hiện:

- View trung tâm là FLASHBACK_TRANSACTION_QUERY.
- XID là transaction identifier dạng RAW(8), thường được tìm bằng VERSIONS_XID của Flashback Version Query.
- Các metadata chính gồm START_SCN, COMMIT_SCN, LOGON_USER, OPERATION, TABLE_OWNER, TABLE_NAME, ROW_ID và UNDO_SQL.
- Database cần COMPATIBLE từ 10.0 trở lên và minimal supplemental logging.
- Người truy vấn cần SELECT ANY TRANSACTION; đây là quyền mạnh và phải cấp hạn chế.
- Để thực thi UNDO_SQL, cần SELECT/INSERT/UPDATE/DELETE trên các bảng cụ thể.
- Flashback Version Query phụ thuộc vào undo còn khả dụng; UNDO_RETENTION không bảo đảm tuyệt đối nếu undo tablespace thiếu chỗ.
- UNDO_SQL chỉ là logical opposite, không phải bản phục hồi hoàn hảo và không nên chạy hàng loạt mà không review.
- Flashback Transaction Backout là tính năng khác; nó cần ARCHIVELOG, primary key supplemental logging và có thể cần foreign key supplemental logging để xử lý dependencies.

Quy trình tốt là tìm XID bằng Version Query, truy vấn transaction metadata theo XID, xác định đầy đủ phạm vi thay đổi, rồi chọn công cụ phục hồi phù hợp sau khi đánh giá dependency và quyền. Flashback Transaction Query cung cấp bằng chứng để ra quyết định; việc sửa dữ liệu vẫn phải được kiểm soát như một thao tác recovery.

## 16. Tài liệu Oracle tham khảo

- Oracle Database 19c Development Guide, “Using Oracle Flashback Transaction Query”: https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/flashback.html
- Oracle Database 19c Database Reference, “FLASHBACK_TRANSACTION_QUERY”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/FLASHBACK_TRANSACTION_QUERY.html
- Oracle Database 19c SQL Language Reference, “SELECT” and Flashback Version Query: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html
- Oracle Database 19c SQL Language Reference, “GRANT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GRANT.html
- Oracle Database 19c PL/SQL Packages and Types Reference, “DBMS_FLASHBACK”: https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_FLASHBACK.html
- Oracle Database 19c Database Reference, “V$UNDOSTAT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-UNDOSTAT.html
- Oracle Database 19c Error Messages, “ORA-54500 to ORA-56978”: https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/ORA-54500.html
