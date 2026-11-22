# ORA-00942, ORA-01031 và lỗi phân giải đối tượng hoặc thiếu quyền

Khi một câu SQL hoặc chương trình PL/SQL không truy cập được bảng, view, sequence, package hay đối tượng khác, Oracle thường trả về một trong hai lỗi:

- **ORA-00942: table or view does not exist** — Oracle không phân giải được tên bảng/view trong ngữ cảnh thực thi, hoặc đối tượng không khả dụng với người dùng hiện tại. Một synonym có thể tồn tại nhưng trỏ tới đối tượng không tồn tại hoặc không truy cập được.
- **ORA-01031: insufficient privileges** — Oracle đã nhận diện thao tác hoặc đối tượng nhưng người dùng thực hiện không có quyền cần thiết cho thao tác đó.

Hai lỗi có thể xuất hiện ở các giai đoạn khác nhau và đôi khi cùng bắt nguồn từ một cấu hình sai: kết nối nhầm schema/PDB, synonym trỏ sai owner, grant thiếu, quyền chỉ được cấp qua role trong khi PL/SQL definer-rights cần quyền trực tiếp, hoặc ứng dụng chạy bằng user khác với user DBA đang kiểm tra.

Không nên xử lý bằng cách cấp DBA, SELECT ANY TABLE hoặc các quyền ANY rộng cho ứng dụng. Cách điều tra đúng là xác định **session thực tế**, **tên object được Oracle phân giải**, **owner của object**, **loại thao tác** và **đường cấp quyền**. Sau đó cấp đúng quyền tối thiểu trên đúng object hoặc sửa tên/schema/synonym/service.

## 1. Hiểu hai lỗi và thời điểm phát sinh

### 1.1 ORA-00942

ORA-00942 thường có thông báo:

~~~text
ORA-00942: table or view does not exist
~~~

Các nguyên nhân thường gặp:

- Bảng hoặc view chưa được tạo.
- Object nằm trong schema khác nhưng SQL dùng tên không qualification.
- Ứng dụng kết nối bằng database user khác.
- Current schema khác với giả định.
- Synonym không tồn tại, trỏ tới object đã bị drop/rename hoặc trỏ sai owner.
- Tài khoản không có quyền truy cập object được tham chiếu.
- Tên object được tạo bằng quoted identifier và chữ hoa/thường không khớp.
- Kết nối tới nhầm database, service hoặc PDB.
- Database link hoặc remote object có vấn đề.
- View, procedure hoặc SQL động tham chiếu object không tồn tại trong môi trường hiện tại.

ORA-00942 không phải bằng chứng tuyệt đối rằng object đã bị xóa. Oracle có thể không cho người dùng biết sự tồn tại của một object mà họ không có quyền truy cập. Vì vậy, hãy kiểm tra bằng đúng user ứng dụng và đối chiếu metadata với DBA khi cần.

### 1.2 ORA-01031

Thông báo thường gặp:

~~~text
ORA-01031: insufficient privileges
~~~

Lỗi xuất hiện khi người dùng không có system privilege hoặc object privilege cần thiết cho thao tác. Ví dụ:

- SELECT, INSERT, UPDATE hoặc DELETE trên object của schema khác.
- EXECUTE trên procedure, function hoặc package.
- CREATE TABLE, CREATE VIEW, CREATE PROCEDURE hoặc CREATE SEQUENCE trong schema của chính mình.
- CREATE ANY TABLE hoặc ALTER ANY TABLE khi thao tác lên schema khác.
- Quyền cần thiết để tạo view dựa trên object của owner khác.
- Quyền cấp lại cho user khác khi thiếu GRANT OPTION hoặc ADMIN OPTION.
- Quyền cần thiết trong PL/SQL stored unit không được cấp trực tiếp cho definer.

Một số lỗi về quota, tablespace, object state hoặc cú pháp có mã lỗi khác. Ví dụ ORA-01950 thường liên quan quota trên tablespace; không nên xem mọi lỗi CREATE TABLE là ORA-01031.

### 1.3 So sánh nhanh

| Tiêu chí | ORA-00942 | ORA-01031 |
|---|---|---|
| Ý nghĩa thường gặp | Không phân giải được bảng/view hoặc không thể truy cập tên đó | Thiếu quyền cho thao tác |
| Vấn đề chính | Tên, owner, synonym, service/PDB hoặc khả năng truy cập object | System privilege, object privilege hoặc grant path |
| Kiểm tra đầu tiên | User, current schema, owner, synonym, object tồn tại ở đâu | Lệnh đang chạy và quyền cụ thể cần cho lệnh |
| Cách sửa thường gặp | Sửa schema qualification, synonym, connection hoặc cấp quyền object | Cấp đúng object/system privilege tối thiểu |
| Rủi ro khi sửa sai | Tạo synonym sai hoặc trỏ nhầm dữ liệu | Cấp quyền quá rộng, mở rộng phạm vi truy cập |

Không nên chỉ dựa vào tên lỗi để thay đổi quyền. Hãy xác định câu SQL chính xác và ngữ cảnh thực thi.

## 2. Xác định session đang gây lỗi

Điều tra bằng DBA account nhưng không kiểm tra danh tính của session ứng dụng là một nguyên nhân khiến sự cố bị chẩn đoán sai. DBA có thể nhìn thấy object và đọc được dữ liệu trong khi ứng dụng không thể.

Bắt đầu bằng truy vấn từ chính connection đang lỗi:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_USER') AS current_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    SYS_CONTEXT('USERENV', 'CURRENT_EDITION_NAME') AS current_edition,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name
FROM dual;
~~~

Các giá trị này trả lời những câu hỏi khác nhau:

- SESSION_USER là database user đã xác thực cho session.
- CURRENT_USER là user hiện hành trong ngữ cảnh thực thi; giá trị có thể thay đổi khi vào definer-rights PL/SQL.
- CURRENT_SCHEMA là schema Oracle dùng để phân giải tên object không có owner qualification.
- CURRENT_EDITION_NAME cho biết edition hiện hành nếu database sử dụng edition-based redefinition.
- CON_NAME và SERVICE_NAME giúp xác định container/PDB và service đã kết nối.
- DB_NAME giúp đối chiếu database đích.

### 2.1 SESSION_USER không phải CURRENT_SCHEMA

Ví dụ session đăng nhập bằng APP_RUNTIME nhưng đổi schema phân giải:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = SALES;
~~~

Sau lệnh này:

- SESSION_USER vẫn là APP_RUNTIME.
- CURRENT_SCHEMA trở thành SALES.
- Tên bảng không qualification có thể được tìm trong schema SALES.
- Quyền thực tế vẫn được đánh giá theo user và privilege context; đổi CURRENT_SCHEMA không cấp thêm quyền.

CURRENT_SCHEMA là cơ chế điều khiển name resolution, không phải cách đăng nhập thành user khác và không thay thế GRANT.

### 2.2 Kiểm tra từ DBA session

DBA có thể tìm session ứng dụng:

~~~sql
SELECT
    sid,
    serial#,
    username,
    schema#,
    service_name,
    machine,
    program,
    module,
    action,
    status,
    sql_id
FROM v$session
WHERE username = 'APP_RUNTIME'
ORDER BY logon_time;
~~~

Thay APP_RUNTIME bằng user thực tế. Trong Oracle RAC, dùng GV$SESSION và đưa INST_ID vào điều kiện/join để phân biệt session có SID trùng trên các instance.

Nếu connection pool có nhiều user hoặc proxy authentication, hãy kiểm tra cả client identifier, service, module/action và thông tin proxy phù hợp. Đừng giả định mọi request đều chạy bằng một schema chỉ vì cấu hình datasource có tên như vậy.

### 2.3 So sánh connection ứng dụng với SQL client

Hãy chạy cùng câu SELECT session context qua:

1. Connection của ứng dụng đang lỗi.
2. SQL Developer hoặc SQL*Plus đăng nhập bằng đúng username ứng dụng.
3. DBA connection để xem metadata khi cần.

Nếu kết quả khác nhau, ghi lại user, service, PDB, current schema, edition và session settings. Một kết nối SQL Developer đăng nhập bằng tài khoản cá nhân không đại diện cho quyền của ứng dụng.

## 3. Oracle phân giải tên object như thế nào?

Một tên như ORDERS có thể tồn tại ở nhiều schema. Khi SQL dùng tên không qualification, Oracle phải xác định object nào được tham chiếu.

### 3.1 Tên không qualification và tên có owner

Ví dụ:

~~~sql
SELECT *
FROM orders;
~~~

Tên ORDERS không ghi owner. Oracle phân giải trong ngữ cảnh schema hiện hành và các synonym phù hợp.

Nếu object nằm trong schema SALES, có thể ghi rõ:

~~~sql
SELECT *
FROM sales.orders;
~~~

Schema qualification giúp câu SQL ít phụ thuộc CURRENT_SCHEMA và giảm nhầm lẫn khi nhiều schema có object trùng tên. Tuy nhiên, ghi SALES.ORDERS không tự cấp quyền cho user; user vẫn phải có privilege phù hợp trên object.

### 3.2 Object cục bộ và synonym

Synonym là một tên thay thế cho object. Có hai loại phổ biến:

- Private synonym: thuộc một schema và có phạm vi sử dụng theo quyền/khả năng nhìn thấy của schema đó.
- Public synonym: được tạo trong namespace công khai và có thể được nhiều schema tham chiếu.

Ví dụ:

~~~sql
CREATE SYNONYM app_runtime.orders
FOR sales.orders;
~~~

Hoặc public synonym:

~~~sql
CREATE PUBLIC SYNONYM orders
FOR sales.orders;
~~~

Public synonym thường chỉ nên tạo khi có lý do quản trị rõ ràng vì nó ảnh hưởng name resolution của nhiều schema.

**Synonym không cấp quyền.** Nếu APP_RUNTIME có synonym APP_RUNTIME.ORDERS trỏ tới SALES.ORDERS nhưng không có SELECT trên SALES.ORDERS, câu SELECT vẫn thất bại.

### 3.3 Object cùng tên có thể che synonym

Nếu schema có object thật và synonym cùng tên, object cục bộ có thể được phân giải trước synonym. Ví dụ APP_RUNTIME có bảng ORDERS cũ trong khi private synonym ORDERS trỏ tới SALES.ORDERS; câu SQL không qualification có thể tham chiếu bảng cục bộ.

Khi nghi ngờ synonym bị che, hãy dùng tên có owner và kiểm tra ALL_OBJECTS/ALL_SYNONYMS. Không xóa object cục bộ chỉ vì muốn synonym được dùng; trước tiên xác định dependency và ý định thiết kế.

### 3.4 Synonym có thể trỏ sai hoặc đã lỗi thời

Synonym có thể tồn tại dù target bị drop hoặc đổi tên. Việc tạo synonym thường không xác minh đầy đủ rằng target sẽ còn tồn tại và truy cập được trong mọi lần thực thi.

Kiểm tra:

~~~sql
SELECT
    owner,
    synonym_name,
    table_owner,
    table_name,
    db_link
FROM all_synonyms
WHERE synonym_name = 'ORDERS'
ORDER BY owner;
~~~

Nếu có quyền DBA, có thể kiểm tra DBA_SYNONYMS. Với synonym của chính user, xem USER_SYNONYMS.

Nếu DB_LINK có giá trị, synonym trỏ tới remote object. Điều tra database link và remote identity riêng, không chỉ tìm bảng local.

### 3.5 Database link

Ví dụ:

~~~sql
SELECT *
FROM sales.orders@reporting_link;
~~~

Tên object gồm schema, object và database link. Cần kiểm tra:

- Database link có tồn tại và thuộc phạm vi user không.
- Link dùng fixed user, connected user hay current user theo cấu hình.
- Remote database/service có hoạt động không.
- Remote user có quyền trên object hay không.
- Tên schema/object ở remote có đúng không.

Xem metadata link mà user được phép nhìn thấy:

~~~sql
SELECT owner, db_link, username, host
FROM all_db_links;
~~~

Thông tin password không được hiển thị trong view. Có thể kiểm tra remote identity bằng:

~~~sql
SELECT user
FROM dual@reporting_link;
~~~

Nếu truy vấn remote lỗi, mã lỗi có thể là ORA-02019, ORA-12154, ORA-01017 hoặc lỗi mạng khác thay vì ORA-00942. Hãy đọc toàn bộ error stack để xác định lỗi phát sinh ở local hay remote database.

## 4. Tên object có phân biệt chữ hoa/thường không?

Oracle chuyển identifier không đặt trong dấu nháy kép về chữ hoa khi lưu và phân giải.

Ví dụ:

~~~sql
CREATE TABLE customer_order (
    id NUMBER
);
~~~

Tên được lưu như CUSTOMER_ORDER. Các cách tham chiếu không đặt trong dấu nháy như customer_order, Customer_Order hoặc CUSTOMER_ORDER được chuẩn hóa về cùng identifier.

Nếu tạo bằng quoted identifier:

~~~sql
CREATE TABLE "CustomerOrder" (
    "OrderId" NUMBER
);
~~~

thì phải tham chiếu đúng chữ hoa/thường và dấu nháy:

~~~sql
SELECT "OrderId"
FROM "CustomerOrder";
~~~

Các câu sau không tham chiếu cùng tên:

~~~sql
SELECT orderid FROM CustomerOrder;
SELECT "ORDERID" FROM "CUSTOMERORDER";
~~~

Quoted identifiers dễ gây lỗi khi ORM hoặc code generator tự viết tên không có dấu nháy. Với schema mới, thường nên dùng identifier không quoted, theo quy ước nhất quán. Nếu phải tích hợp object quoted đã có, kiểm tra metadata chính xác trước khi viết SQL.

### 4.1 Xem tên thật trong data dictionary

~~~sql
SELECT owner, object_name, object_type
FROM all_objects
WHERE UPPER(object_name) = UPPER(:name)
ORDER BY owner, object_type, object_name;
~~~

Query trên hữu ích để tìm gần đúng nhưng có thể trả nhiều object khác nhau về chữ hoa/thường. Khi object được tạo bằng quoted identifier, hãy so sánh OBJECT_NAME chính xác:

~~~sql
SELECT owner, object_name, object_type
FROM all_objects
WHERE object_name = :exact_name;
~~~

Bind exact_name bằng chuỗi đúng như metadata trả về.

## 5. Xác nhận object có tồn tại và có thể nhìn thấy

Data dictionary có nhiều view với phạm vi khác nhau.

| View | Phạm vi |
|---|---|
| USER_OBJECTS | Object thuộc schema hiện tại |
| ALL_OBJECTS | Object mà user hiện tại có thể truy cập/nhìn thấy |
| DBA_OBJECTS | Object toàn database, cần quyền DBA/catalog |
| USER_TABLES | Bảng thuộc schema hiện tại |
| ALL_TABLES | Bảng mà user có thể truy cập |
| DBA_TABLES | Bảng toàn database |
| USER_VIEWS / ALL_VIEWS / DBA_VIEWS | Metadata view theo phạm vi |
| USER_SYNONYMS / ALL_SYNONYMS / DBA_SYNONYMS | Synonym theo phạm vi |
| ALL_TAB_PRIVS | Object grants mà user có thể nhìn thấy |
| USER_TAB_PRIVS_RECD | Object grants nhận được bởi user |
| USER_SYS_PRIVS | System privileges được cấp trực tiếp cho user |
| SESSION_PRIVS | System privileges hiện có trong session |
| SESSION_ROLES | Roles đang được enable trong session |

### 5.1 Tìm object theo owner và tên

~~~sql
SELECT
    owner,
    object_name,
    object_type,
    status,
    editionable
FROM all_objects
WHERE owner = 'SALES'
  AND object_name = 'ORDERS'
ORDER BY object_type;
~~~

Nếu release không có cột hoặc thuộc tính editionable theo cách truy vấn trên, bỏ cột đó và dùng metadata phù hợp với phiên bản. Với tên không quoted, owner và object thường được lưu uppercase.

ALL_OBJECTS không phải catalog toàn database. Không có dòng trong ALL_OBJECTS không chứng minh object không tồn tại; có thể user không có quyền để nhìn thấy nó. DBA có thể kiểm tra DBA_OBJECTS hoặc CDB_OBJECTS trong đúng container nếu cần.

### 5.2 Kiểm tra bảng và view riêng

~~~sql
SELECT owner, table_name
FROM all_tables
WHERE owner = 'SALES'
  AND table_name = 'ORDERS';

SELECT owner, view_name
FROM all_views
WHERE owner = 'SALES'
  AND view_name = 'ORDER_SUMMARY';
~~~

Một câu query có thể tham chiếu synonym hoặc view chứ không phải bảng trực tiếp. Kiểm tra đúng loại object và dependency.

### 5.3 Kiểm tra dependency của view/package

~~~sql
SELECT
    owner,
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM all_dependencies
WHERE owner = 'APP_OWNER'
  AND name = 'ORDER_API'
ORDER BY referenced_owner, referenced_name;
~~~

ALL_DEPENDENCIES giúp tìm object được tham chiếu bởi stored object. Nếu view hoặc package phụ thuộc vào object đã drop/rename, lỗi có thể xuất hiện khi compile hoặc execute. Cần kiểm tra thêm ALL_ERRORS/USER_ERRORS để xem lỗi compile cụ thể.

### 5.4 Xem DDL thực tế

Nếu có quyền phù hợp, DBA hoặc owner có thể lấy DDL:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
    'TABLE',
    'ORDERS',
    'SALES'
)
FROM dual;
~~~

Đối với view, synonym, package hoặc sequence, thay object type tương ứng. DDL giúp xác nhận tên, constraint, cột và cấu trúc thật. Không dùng metadata extraction để lộ DDL hoặc thông tin nhạy cảm cho user không có thẩm quyền.

## 6. Kiểm tra synonym và target

Nếu SQL dùng tên ORDERS nhưng bảng thực nằm trong SALES, có thể ứng dụng phụ thuộc private hoặc public synonym.

Kiểm tra tất cả synonym user nhìn thấy:

~~~sql
SELECT
    owner,
    synonym_name,
    table_owner,
    table_name,
    db_link
FROM all_synonyms
WHERE synonym_name = 'ORDERS'
ORDER BY owner;
~~~

Đọc kết quả:

- OWNER là schema chứa synonym, hoặc PUBLIC với public synonym.
- TABLE_OWNER là owner target.
- TABLE_NAME là object đích.
- DB_LINK khác NULL cho biết target nằm qua database link.

Sau đó kiểm tra target:

~~~sql
SELECT owner, object_name, object_type, status
FROM all_objects
WHERE owner = 'SALES'
  AND object_name = 'ORDERS';
~~~

Và kiểm tra quyền trên target:

~~~sql
SELECT
    grantee,
    owner,
    table_name,
    privilege,
    grantable
FROM all_tab_privs
WHERE owner = 'SALES'
  AND table_name = 'ORDERS'
ORDER BY grantee, privilege;
~~~

Nếu APP_RUNTIME không xuất hiện trong kết quả, quyền có thể được cấp qua role. Hãy kiểm tra role và trạng thái enable. Với PL/SQL definer-rights, quyền qua role không thay thế direct grant như phần sau giải thích.

### 6.1 Tạo private synonym sau khi xác nhận target

Ví dụ DBA hoặc owner tạo synonym cho user:

~~~sql
CREATE SYNONYM app_runtime.orders
FOR sales.orders;
~~~

Nếu user tự tạo synonym trong schema của mình, họ cần CREATE SYNONYM. Tạo public synonym cần CREATE PUBLIC SYNONYM, thường chỉ cấp cho quản trị viên.

Sau khi tạo synonym, user vẫn cần object privilege trên SALES.ORDERS:

~~~sql
GRANT SELECT ON sales.orders TO app_runtime;
~~~

Không tạo synonym chỉ để che giấu owner nếu chưa giải quyết quyền truy cập.

## 7. Phân biệt object privilege và system privilege

Oracle có hai nhóm quyền chính liên quan đến lỗi này.

### 7.1 Object privilege

Object privilege cho phép thực hiện thao tác trên một object cụ thể.

| Privilege | Ví dụ thao tác |
|---|---|
| SELECT | Đọc bảng/view hoặc một số object có quyền SELECT |
| INSERT | Thêm dòng |
| UPDATE | Cập nhật cột/dòng |
| DELETE | Xóa dòng |
| REFERENCES | Tạo foreign key tham chiếu key của object |
| ALTER | Thay đổi cấu trúc object khi được hỗ trợ |
| INDEX | Tạo index trên object theo quyền được cấp |
| EXECUTE | Gọi procedure, function, package hoặc type có thể thực thi |

Một số object có quyền đặc thù khác. Hãy tra Oracle SQL Language Reference cho đúng object type và release.

Ví dụ cấp quyền SELECT trên bảng:

~~~sql
GRANT SELECT ON sales.orders TO app_runtime;
~~~

Chỉ cấp DML cần thiết:

~~~sql
GRANT SELECT, INSERT, UPDATE ON sales.orders TO app_runtime;
~~~

Không cấp DELETE nếu service không cần xóa dữ liệu.

### 7.2 System privilege

System privilege cho phép thực hiện một nhóm thao tác ở phạm vi schema/database.

| Privilege | Ví dụ |
|---|---|
| CREATE SESSION | Đăng nhập database |
| CREATE TABLE | Tạo bảng trong schema của chính user |
| CREATE VIEW | Tạo view trong schema của chính user |
| CREATE SEQUENCE | Tạo sequence trong schema của chính user |
| CREATE PROCEDURE | Tạo procedure/function/package trong schema của chính user |
| CREATE SYNONYM | Tạo private synonym trong schema của chính user |
| CREATE ANY TABLE | Tạo bảng trong schema khác |
| ALTER ANY TABLE | Alter bảng thuộc schema khác |
| DROP ANY TABLE | Drop bảng thuộc schema khác |
| CREATE ANY VIEW | Tạo view trong schema khác |
| EXECUTE ANY PROCEDURE | Execute procedure thuộc schema khác |

Các quyền ANY có phạm vi rộng và có thể tác động đến object của nhiều schema. Không cấp chúng cho runtime account chỉ để làm một query hoạt động.

### 7.3 Quyền tạo object và quota tablespace

Để tạo bảng trong schema của mình, user thường cần CREATE TABLE và quota phù hợp trên tablespace (hoặc UNLIMITED TABLESPACE theo chính sách).

Ví dụ:

~~~sql
GRANT CREATE SESSION, CREATE TABLE TO app_developer;
ALTER USER app_developer QUOTA 100M ON app_data;
~~~

Quota được cấp trên tablespace cụ thể. Nếu thiếu quota, lỗi thường là ORA-01950 chứ không nhất thiết ORA-01031.

Không cấp UNLIMITED TABLESPACE mặc định cho mọi user. Dùng quota theo dung lượng và môi trường.

## 8. Cấp quyền đúng object

Giả sử SALES sở hữu ORDERS và ứng dụng APP_RUNTIME cần đọc đơn hàng.

### 8.1 Cấp SELECT trực tiếp

Owner hoặc DBA thực hiện:

~~~sql
GRANT SELECT ON sales.orders TO app_runtime;
~~~

Ứng dụng truy vấn:

~~~sql
SELECT order_id, status
FROM sales.orders
WHERE order_id = :order_id;
~~~

Nếu muốn dùng synonym:

~~~sql
CREATE SYNONYM app_runtime.orders
FOR sales.orders;
~~~

Sau đó:

~~~sql
SELECT order_id, status
FROM orders
WHERE order_id = :order_id;
~~~

Synonym chỉ giúp rút gọn tên; grant SELECT vẫn cần.

### 8.2 Cấp nhiều object privilege

Ví dụ service cần đọc và cập nhật trạng thái:

~~~sql
GRANT SELECT, UPDATE ON sales.orders TO app_runtime;
~~~

Có thể giới hạn cột cho một số object privilege như UPDATE:

~~~sql
GRANT UPDATE (status, updated_at)
ON sales.orders
TO app_runtime;
~~~

Column-level privilege giúp giảm phạm vi thay đổi khi service chỉ cần cập nhật một số cột. Hãy xác nhận câu UPDATE thực tế không ghi các cột khác.

### 8.3 Quyền EXECUTE trên package

Nếu ứng dụng gọi package:

~~~sql
GRANT EXECUTE ON sales.order_api TO app_runtime;
~~~

Java gọi procedure qua JDBC:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement statement =
         connection.prepareCall("{ call sales.order_api.get_order(?, ?) }")) {

    statement.setLong(1, orderId);
    statement.registerOutParameter(2, java.sql.Types.VARCHAR);
    statement.execute();

    String status = statement.getString(2);
}
~~~

Quyền EXECUTE trên package cho phép gọi public members được công bố theo package spec. Nó không tự cấp quyền SELECT trực tiếp cho APP_RUNTIME trên mọi bảng mà package truy cập. Package definer-rights có thể dùng quyền của owner trong phạm vi thực thi; phần quyền bên trong cần được thiết kế riêng.

### 8.4 Quyền trên view

Nếu APP_RUNTIME chỉ cần đọc một tập dữ liệu đã được giới hạn, có thể cấp SELECT trên view:

~~~sql
GRANT SELECT ON sales.order_summary_v TO app_runtime;
~~~

Owner của view cần có quyền thích hợp trên các object nền để tạo/duy trì view. Consumer thường chỉ cần quyền trên view, theo quy tắc quyền của view và object nền. Không cấp quyền rộng trên tất cả bảng nền nếu ứng dụng chỉ cần view.

## 9. Direct grant và role grant

Đây là nguyên nhân thường gặp khi một câu SQL chạy trong SQL Developer nhưng stored procedure lại lỗi ORA-00942 hoặc ORA-01031.

### 9.1 Role là gì?

Role là tập hợp privilege được cấp cho user hoặc role khác. Role giúp quản trị quyền theo nhóm.

Ví dụ:

~~~sql
CREATE ROLE order_reader_role;

GRANT SELECT ON sales.orders TO order_reader_role;

GRANT order_reader_role TO app_runtime;
~~~

Khi role được enable trong session, APP_RUNTIME có thể sử dụng quyền SELECT qua role trong SQL tương tác thông thường.

Kiểm tra role:

~~~sql
SELECT role
FROM session_roles
ORDER BY role;
~~~

Role được cấp cho user chưa chắc đang enable trong session; có thể bị giới hạn bởi default role, SET ROLE, secure application role hoặc cơ chế xác thực.

### 9.2 Definer-rights PL/SQL

Stored procedure/function/package mặc định thường chạy với quyền của owner (definer rights), trừ khi khai báo AUTHID CURRENT_USER.

Trong definer-rights unit:

- Quyền của definer là cơ sở để kiểm tra quyền thực thi.
- Các role thông thường của definer bị vô hiệu hóa trong lúc unit chạy.
- Quyền cần cho static SQL trong stored unit phải được cấp trực tiếp cho owner theo quy tắc compile-time privilege checking.
- Chỉ cấp role cho owner có thể khiến SQL tương tác chạy được nhưng stored unit không compile hoặc không execute được.

Ví dụ APP_OWNER tạo package đọc SALES.ORDERS. Cấp role cho APP_OWNER có thể chưa đủ. Cần grant trực tiếp:

~~~sql
GRANT SELECT ON sales.orders TO app_owner;
~~~

Sau đó compile package bằng APP_OWNER.

Không cấp quyền cho APP_RUNTIME nếu package definer-rights do APP_OWNER sở hữu và runtime chỉ cần EXECUTE package. Quyền phải được cấp cho đúng principal thực hiện thao tác trong từng privilege context.

### 9.3 Ví dụ lỗi do quyền qua role

Giả sử:

~~~sql
CREATE ROLE sales_read_role;
GRANT SELECT ON sales.orders TO sales_read_role;
GRANT sales_read_role TO app_owner;
~~~

APP_OWNER có thể chạy trực tiếp:

~~~sql
SELECT * FROM sales.orders;
~~~

nếu role đang enable. Nhưng khi compile procedure definer-rights có static SQL:

~~~sql
CREATE OR REPLACE PROCEDURE app_owner.read_orders
AS
    l_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM sales.orders;
END;
/
~~~

Oracle có thể báo lỗi do owner không có direct grant trên SALES.ORDERS. Cấp trực tiếp:

~~~sql
GRANT SELECT ON sales.orders TO app_owner;
~~~

Rồi compile lại:

~~~sql
ALTER PROCEDURE app_owner.read_orders COMPILE;
~~~

Kiểm tra lỗi:

~~~sql
SELECT line, position, text
FROM all_errors
WHERE owner = 'APP_OWNER'
  AND name = 'READ_ORDERS'
  AND type = 'PROCEDURE'
ORDER BY sequence;
~~~

### 9.4 AUTHID CURRENT_USER và invoker-rights

Unit khai báo:

~~~sql
CREATE OR REPLACE PROCEDURE app_owner.read_orders
AUTHID CURRENT_USER
AS
    l_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM sales.orders;
END;
/
~~~

AUTHID CURRENT_USER làm unit chạy theo quyền của invoker ở runtime. Các role đang enable của invoker có thể tham gia kiểm tra quyền theo quy tắc invoker-rights. Điều này hữu ích khi muốn cùng một unit hoạt động với quyền của từng caller, nhưng làm authorization phụ thuộc user gọi.

Cần phân biệt quyền cần để compile unit với quyền cần khi runtime. Static SQL được phân tích khi compile; owner cần có quyền phù hợp để tham chiếu object. Khi chạy invoker-rights, quyền runtime được đánh giá theo invoker. Hãy kiểm tra cả compile owner lẫn caller, thay vì chỉ thay AUTHID để né lỗi.

### 9.5 Dynamic SQL

Dynamic SQL tạo câu lệnh tại runtime:

~~~sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM sales.orders'
INTO l_count;
~~~

Dynamic SQL không làm biến mất yêu cầu privilege. Trong definer-rights unit, role của definer vẫn bị vô hiệu hóa; quyền được đánh giá theo definer privilege context. Trong invoker-rights unit, quyền runtime gắn với invoker theo quy tắc tương ứng.

Dynamic SQL còn có rủi ro SQL injection nếu ghép input vào identifier hoặc literal. Dùng bind variable cho giá trị; identifier cần được whitelist và kiểm tra theo quy tắc riêng vì bind variable không thể thay thế tên bảng/cột.

## 10. Quyền cần thiết khi tạo view và stored object

Tạo object khác với truy vấn object đã tồn tại. Một user có thể SELECT bảng nhưng chưa có quyền CREATE VIEW; hoặc có CREATE VIEW nhưng không có direct SELECT trên bảng nền.

### 10.1 Tạo view trong schema của mình

Ví dụ APP_REPORT cần tạo view dựa trên SALES.ORDERS:

~~~sql
GRANT CREATE VIEW TO app_report;
GRANT SELECT ON sales.orders TO app_report;
~~~

Sau đó APP_REPORT:

~~~sql
CREATE OR REPLACE VIEW order_summary_v AS
SELECT order_id, status
FROM sales.orders;
~~~

Với object nền thuộc schema khác, quyền cần thiết để tạo view phải được cấp trực tiếp cho owner của view theo yêu cầu Oracle. Quyền thông qua role không đủ cho các kiểm tra quyền cần thiết khi định nghĩa view.

Nếu view cần truy cập object nền trong nhiều schema, phải cấp trực tiếp từng quyền cần thiết cho owner view. Hãy cấp đúng SELECT hoặc quyền cần thiết trên đúng object, không cấp SELECT ANY TABLE.

### 10.2 Tạo view trong schema khác

CREATE ANY VIEW cho phép tạo view ở schema khác và là system privilege rộng. Chỉ DBA hoặc tài khoản triển khai có kiểm soát mới nên sở hữu quyền này khi thực sự cần.

Không cấp CREATE ANY VIEW cho runtime account. Tốt hơn là triển khai bằng owner schema tương ứng hoặc dùng quy trình release có quyền tạm thời được kiểm soát.

### 10.3 Tạo procedure/package

Để tạo procedure trong schema của mình, user cần CREATE PROCEDURE. Để tạo trong schema khác, cần CREATE ANY PROCEDURE, quyền rộng hơn.

Ví dụ:

~~~sql
GRANT CREATE PROCEDURE TO app_owner;
~~~

Nếu procedure tham chiếu object thuộc schema khác, cần quyền trực tiếp thích hợp trên các object đó khi compile và runtime theo AUTHID.

### 10.4 Tạo sequence và synonym

Tạo sequence trong schema của mình:

~~~sql
GRANT CREATE SEQUENCE TO app_owner;
~~~

Tạo private synonym:

~~~sql
GRANT CREATE SYNONYM TO app_runtime;
~~~

Tạo public synonym yêu cầu quyền quản trị CREATE PUBLIC SYNONYM. Không cấp quyền này cho ứng dụng thông thường.

## 11. Kiểm tra quyền hiện có

### 11.1 Object grants

~~~sql
SELECT
    grantee,
    owner,
    table_name,
    privilege,
    grantable
FROM all_tab_privs
WHERE owner = 'SALES'
  AND table_name = 'ORDERS'
ORDER BY grantee, privilege;
~~~

Có thể xem quyền user nhận được:

~~~sql
SELECT
    owner,
    table_name,
    privilege,
    grantor,
    grantable
FROM user_tab_privs_recd
ORDER BY owner, table_name, privilege;
~~~

ALL_TAB_PRIVS và các view liên quan có phạm vi hiển thị phụ thuộc quyền hiện tại. DBA có thể dùng DBA_TAB_PRIVS để xem rộng hơn.

### 11.2 Quyền qua role

~~~sql
SELECT granted_role, default_role
FROM user_role_privs
ORDER BY granted_role;

SELECT role
FROM session_roles
ORDER BY role;

SELECT role, owner, table_name, privilege
FROM role_tab_privs
WHERE owner = 'SALES'
  AND table_name = 'ORDERS'
ORDER BY role, privilege;
~~~

USER_ROLE_PRIVS cho biết role được cấp và default role theo metadata; SESSION_ROLES cho biết role hiện đang enable. ROLE_TAB_PRIVS giúp xem object privilege được cấp cho role.

Nếu user nhận role qua role khác, cần lần theo role hierarchy. DBA có thể kiểm tra DBA_ROLE_PRIVS/ROLE_ROLE_PRIVS và DBA_TAB_PRIVS.

### 11.3 System privilege

~~~sql
SELECT privilege
FROM session_privs
ORDER BY privilege;
~~~

SESSION_PRIVS cho biết system privileges đang có hiệu lực trong session. USER_SYS_PRIVS cho biết system privilege được cấp trực tiếp cho user:

~~~sql
SELECT privilege, admin_option
FROM user_sys_privs
ORDER BY privilege;
~~~

Quyền qua role có thể xem bằng ROLE_SYS_PRIVS và SESSION_ROLES. Hãy phân biệt quyền được cấp, quyền default và quyền đang enable.

### 11.4 Tìm user được cấp quyền trên object

DBA có thể truy vấn:

~~~sql
SELECT
    grantee,
    privilege,
    grantable
FROM dba_tab_privs
WHERE owner = 'SALES'
  AND table_name = 'ORDERS'
ORDER BY grantee, privilege;
~~~

DBA_TAB_PRIVS yêu cầu quyền catalog phù hợp. Không cấp quyền catalog toàn database cho ứng dụng chỉ để tự điều tra.

## 12. Các tình huống thường gây ORA-00942

### 12.1 Kết nối bằng nhầm user

SQL chạy bằng SALES nhưng ứng dụng kết nối bằng APP_RUNTIME. SALES nhìn thấy SALES.ORDERS vì là owner; APP_RUNTIME không có quyền và không có synonym phù hợp.

Cách xử lý:

- Đọc SESSION_USER từ connection ứng dụng.
- Xác định object owner.
- Cấp đúng object privilege hoặc gọi API/package được công bố.
- Dùng owner qualification nếu phù hợp.

### 12.2 Object nằm ở schema khác

Ứng dụng chạy:

~~~sql
SELECT * FROM orders;
~~~

Trong khi object là SALES.ORDERS và CURRENT_SCHEMA là APP_RUNTIME.

Có thể sửa SQL:

~~~sql
SELECT * FROM sales.orders;
~~~

hoặc tạo private synonym cho APP_RUNTIME. Cả hai cách vẫn cần object privilege.

### 12.3 Synonym target bị drop hoặc đổi tên

Kiểm tra ALL_SYNONYMS, sau đó kiểm tra target trong ALL_OBJECTS/DBA_OBJECTS. Nếu target đã đổi tên, cập nhật synonym theo migration đã được duyệt và kiểm tra các consumer khác.

### 12.4 Nhầm PDB hoặc service

Cùng một database có thể có nhiều PDB. SALES.ORDERS tồn tại ở PDB_DEV nhưng không tồn tại ở PDB_TEST. Ứng dụng có thể đang dùng JDBC URL hoặc service name sai.

Kiểm tra:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

Đối chiếu với JDBC URL, service registration, datasource environment variable và secret/config của deployment. Không sửa quyền ở PDB khác với nơi ứng dụng đang kết nối.

### 12.5 Object chưa được deploy

Nếu migration chưa chạy hoặc chạy lỗi, object có thể chưa tồn tại. Kiểm tra release version, migration history và schema owner. Không tự tạo object thủ công trên production nếu schema migration là nguồn sự thật; sửa migration/deployment theo quy trình của hệ thống.

### 12.6 View hoặc synonym có tên quoted

Nếu object được tạo với tên quoted, truy vấn bằng identifier không quoted sẽ tìm tên uppercase khác. Đọc ALL_OBJECTS/ALL_SYNONYMS để biết exact name và sửa mapping SQL/ORM.

### 12.7 View phụ thuộc object không khả dụng

View có thể tồn tại nhưng truy vấn view gặp lỗi do dependency, invalid status hoặc privilege trên base object. Kiểm tra:

~~~sql
SELECT owner, object_name, status
FROM all_objects
WHERE owner = 'SALES'
  AND object_name = 'ORDER_SUMMARY_V';
~~~

Sau đó xem ALL_ERRORS và ALL_DEPENDENCIES. Một số lỗi view invalid có thể trả ORA-04063 hoặc lỗi khác; hãy dùng error stack đầy đủ.

## 13. Các tình huống thường gây ORA-01031

### 13.1 Thiếu quyền DML

APP_RUNTIME đọc được bảng nhưng không INSERT:

~~~sql
INSERT INTO sales.orders (order_id, status)
VALUES (:id, 'NEW');
~~~

Nếu chỉ được cấp SELECT, INSERT có thể trả lỗi quyền. Cấp quyền cần thiết:

~~~sql
GRANT INSERT ON sales.orders TO app_runtime;
~~~

Nếu service cần UPDATE nhưng không DELETE, cấp đúng INSERT/UPDATE/SELECT.

### 13.2 Thiếu quyền CREATE trong schema riêng

APP_OWNER chạy CREATE TABLE nhưng không có CREATE TABLE:

~~~sql
CREATE TABLE staging_orders (
    order_id NUMBER PRIMARY KEY
);
~~~

DBA có thể cấp:

~~~sql
GRANT CREATE TABLE TO app_owner;
ALTER USER app_owner QUOTA 100M ON app_data;
~~~

Kiểm tra tablespace mặc định, quota và policy. Nếu lỗi là ORA-01950, xử lý quota thay vì cấp CREATE ANY TABLE.

### 13.3 Dùng quyền ANY để giải quyết sai vấn đề

Nếu APP_RUNTIME cần SELECT SALES.ORDERS, không cấp:

~~~sql
GRANT SELECT ANY TABLE TO app_runtime;
~~~

Quyền này cho phép đọc rất nhiều bảng ngoài phạm vi nghiệp vụ. Thay vào đó:

~~~sql
GRANT SELECT ON sales.orders TO app_runtime;
~~~

Tương tự, không cấp INSERT ANY TABLE, UPDATE ANY TABLE, DELETE ANY TABLE, ALTER ANY TABLE hoặc DROP ANY TABLE chỉ để sửa một lỗi trên một object.

### 13.4 Thiếu quyền EXECUTE

Nếu ứng dụng gọi package SALES.ORDER_API nhưng thiếu EXECUTE:

~~~sql
GRANT EXECUTE ON sales.order_api TO app_runtime;
~~~

Sau đó kiểm tra đúng package spec, synonym và tên procedure. Nếu package gọi object khác, quyền bên trong phụ thuộc AUTHID và quyền của owner/invoker; EXECUTE trên package không phải grant tổng quát trên toàn bộ schema.

### 13.5 Thiếu quyền GRANT OPTION

Một user có SELECT trên SALES.ORDERS chưa chắc được quyền cấp SELECT cho user khác.

Để cấp lại object privilege, grantor cần quyền thích hợp, thường là object owner hoặc được cấp privilege WITH GRANT OPTION.

Ví dụ owner cấp:

~~~sql
GRANT SELECT ON sales.orders
TO app_runtime
WITH GRANT OPTION;
~~~

Chỉ dùng WITH GRANT OPTION nếu APP_RUNTIME thực sự cần phân phối tiếp quyền đó. Không cấp rộng theo thói quen.

Đối với system privilege và role, ADMIN OPTION là cơ chế liên quan; nó khác GRANT OPTION của object privilege.

## 14. Quyền trực tiếp, role và các loại code path

Không phải mọi thao tác đều đánh giá privilege theo cùng một cách. Hãy xác định code chạy trực tiếp, trong stored procedure definer-rights, invoker-rights, trigger, view hay job.

### 14.1 SQL chạy trực tiếp từ JDBC

SQL tương tác trong session có thể sử dụng system/object privileges được cấp trực tiếp và các role đang enable. Nếu role không enable, quyền chỉ có qua role có thể không có hiệu lực.

Kiểm tra SESSION_ROLES và SESSION_PRIVS từ đúng connection.

### 14.2 Stored procedure definer-rights

Đây là mặc định phổ biến của named PL/SQL unit. Quyền của owner là cơ sở thực thi; role thường bị disable bên trong. Static SQL trong unit cần privilege phù hợp được cấp trực tiếp cho owner.

Nếu procedure đọc SALES.ORDERS, grant SELECT trực tiếp cho procedure owner. Caller thường chỉ cần EXECUTE trên procedure nếu API được thiết kế như vậy.

### 14.3 Invoker-rights

AUTHID CURRENT_USER khiến quyền runtime dựa trên invoker. Đây là lựa chọn có chủ đích khi unit phải tôn trọng quyền của người gọi.

Kiểm tra:

- Owner có thể compile unit và phân giải object không.
- Invoker có quyền runtime không.
- Role cần thiết có đang enable không.
- Dynamic SQL có tham chiếu object theo input không.
- Unit có mở rộng quyền ngoài ý định không.

### 14.4 Trigger

Trigger chạy theo security model của trigger và database. Không giả định role của session gọi có thể cung cấp quyền cho mọi SQL trong trigger. Nếu trigger tham chiếu object ngoài schema owner, cần kiểm tra quyền trực tiếp của trigger owner và dependency.

Một trigger lỗi privilege có thể làm DML trên bảng nguồn thất bại, dù user có INSERT/UPDATE trên bảng nguồn. Xem ALL_ERRORS, ALL_DEPENDENCIES và trigger source.

### 14.5 Job và scheduler

Job có thể chạy dưới credential/schema khác với session tương tác. Kiểm tra owner của job, credential, job_action, enabled state và privilege context. Không dùng kết quả từ SQL Developer để suy ra job có cùng quyền.

## 15. View, package và quyền trên object nền

Một mô hình thường dùng là owner schema giữ bảng, còn application user truy cập qua view hoặc package.

Ví dụ:

~~~text
SALES schema
  ORDERS
  CUSTOMERS
  ORDER_SUMMARY_V
  ORDER_API package

APP_RUNTIME
  SELECT trên ORDER_SUMMARY_V
  EXECUTE trên ORDER_API
~~~

Owner view/package giữ quyền truy cập dữ liệu nền. Runtime chỉ được cấp interface cần thiết.

### 15.1 Quyền của owner view

Khi tạo view trên object thuộc schema khác, owner view cần quyền phù hợp trên object nền được cấp trực tiếp. Role grant không đủ cho việc xác minh privilege của view definition.

Ví dụ:

~~~sql
GRANT SELECT ON sales.orders TO app_report;

-- Chạy bằng APP_REPORT:
CREATE OR REPLACE VIEW order_summary_v AS
SELECT order_id, status
FROM sales.orders;
~~~

Sau đó:

~~~sql
GRANT SELECT ON app_report.order_summary_v TO app_runtime;
~~~

APP_RUNTIME có thể đọc view mà không cần được cấp SELECT trực tiếp trên SALES.ORDERS nếu view được tạo và cấu hình đúng. Nếu view dùng invoker rights hoặc các tính năng security đặc thù, cần xem xét quy tắc tương ứng.

### 15.2 Quyền của definer-rights package

Owner package có direct grants trên các bảng mà package cần. Caller chỉ cần EXECUTE trên package. Đây là cách giảm bề mặt quyền của runtime user.

Tuy nhiên, package phải kiểm tra input, giới hạn dữ liệu và tránh dynamic SQL nguy hiểm. Definer-rights package là một boundary bảo mật; code có lỗi có thể thực hiện thao tác bằng quyền cao hơn caller.

### 15.3 WITH GRANT OPTION và view

Quyền cấp lại privilege trên view hoặc object có quy tắc riêng. Không cấp WITH GRANT OPTION chỉ để khắc phục ORA-01031 của một ứng dụng. Nếu một schema cần cấp quyền cho schema khác, xác định rõ owner và grant chain; để DBA/owner cấp trực tiếp thường đơn giản hơn.

## 16. Kiểm tra object invalid và lỗi compile PL/SQL

Một object có thể tồn tại nhưng trạng thái INVALID. Khi đó lỗi thường khác ORA-00942, nhưng dependency không hợp lệ có thể dẫn tới lỗi khi compile hoặc execute.

Kiểm tra trạng thái:

~~~sql
SELECT owner, object_name, object_type, status
FROM all_objects
WHERE owner = 'APP_OWNER'
  AND status <> 'VALID'
ORDER BY object_type, object_name;
~~~

Xem compile errors:

~~~sql
SELECT
    owner,
    name,
    type,
    line,
    position,
    text
FROM all_errors
WHERE owner = 'APP_OWNER'
ORDER BY name, type, sequence;
~~~

Nếu đang ở schema của chính mình, có thể dùng USER_ERRORS.

Compile lại object sau khi dependency hoặc grant đã được sửa:

~~~sql
ALTER PACKAGE app_owner.order_api COMPILE;
ALTER PACKAGE app_owner.order_api COMPILE BODY;
~~~

Hoặc compile procedure/view tương ứng. Sau đó kiểm tra ALL_OBJECTS và ALL_ERRORS.

Không dùng compile hàng loạt trên production khi chưa hiểu dependency và tác động. Thay đổi object có thể làm invalid object phụ thuộc và tạo tải compile.

## 17. Dynamic SQL và tên object từ input

Dynamic SQL có thể tạo ORA-00942 nếu tên object được nối từ input không đúng schema hoặc identifier.

Ví dụ nguy hiểm:

~~~sql
l_sql := 'SELECT COUNT(*) FROM ' || p_table_name;
EXECUTE IMMEDIATE l_sql INTO l_count;
~~~

p_table_name có thể rỗng, sai tên, chứa schema không mong muốn hoặc bị lợi dụng để SQL injection.

### 17.1 Whitelist identifier

Không thể bind tên bảng như bind một giá trị. Nếu phải chọn bảng động, dùng whitelist:

~~~sql
CASE p_source
    WHEN 'ORDERS' THEN
        l_table_name := 'SALES.ORDERS';
    WHEN 'CUSTOMERS' THEN
        l_table_name := 'SALES.CUSTOMERS';
    ELSE
        RAISE_APPLICATION_ERROR(-20001, 'Unsupported source');
END CASE;

l_sql := 'SELECT COUNT(*) FROM ' || l_table_name;
EXECUTE IMMEDIATE l_sql INTO l_count;
~~~

Whitelist phải là mapping nội bộ đã kiểm soát, không lấy raw identifier từ request.

### 17.2 Bind giá trị

~~~sql
l_sql := 'SELECT COUNT(*) FROM sales.orders WHERE status = :1';
EXECUTE IMMEDIATE l_sql INTO l_count USING p_status;
~~~

Bind variable bảo vệ giá trị dữ liệu và cho phép reuse SQL. Nó không thay thế việc kiểm soát tên object.

### 17.3 DBMS_ASSERT

Oracle cung cấp DBMS_ASSERT để kiểm tra một số dạng identifier và SQL name. Đây là công cụ hỗ trợ validation, không thay thế whitelist và authorization. Một tên hợp lệ về cú pháp vẫn có thể là object mà caller không được phép truy cập.

## 18. Lỗi khi gọi object qua synonym, view và package

Khi câu lệnh không dùng trực tiếp tên bảng, hãy lần theo từng lớp.

Ví dụ:

~~~text
APP_RUNTIME query
    |
    v
APP_RUNTIME.ORDERS synonym
    |
    v
SALES.ORDER_SUMMARY_V view
    |
    v
SALES.ORDERS table
    |
    v
SALES.CUSTOMERS table
~~~

Điều tra theo thứ tự:

1. APP_RUNTIME có synonym ORDERS không?
2. Synonym trỏ tới owner/object nào?
3. View target có tồn tại và VALID không?
4. View dependency có còn tồn tại không?
5. Owner view có direct privileges trên object nền không?
6. APP_RUNTIME có SELECT trên view không?
7. Nếu view gọi function/package, owner và quyền EXECUTE có phù hợp không?
8. Nếu có database link, remote identity và remote grants có đúng không?

Một lỗi ở lớp cuối có thể được nhìn thấy từ câu SQL ở lớp đầu. Không cấp quyền trực tiếp cho APP_RUNTIME trên mọi object nền trước khi xác định security design.

## 19. Container database, PDB và edition

Trong môi trường multitenant, cùng một tên schema/object có thể tồn tại ở nhiều PDB. User local trong PDB này không mặc nhiên có quyền trong PDB khác.

### 19.1 Xác định container

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

Đối chiếu service trong JDBC URL với PDB mong muốn. Không cấp grant ở CDB root khi ứng dụng thực sự kết nối vào PDB hoặc ngược lại mà chưa hiểu common/local user.

### 19.2 Common và local users

Common user có phạm vi container theo cách cấp quyền và container clause; local user thuộc PDB cụ thể. Các quyền có thể được cấp locally hoặc commonly tùy object, user và yêu cầu.

Không dùng CONTAINER=ALL như một cách sửa lỗi nhanh. Đó là thay đổi phạm vi quyền nhiều container và cần quản trị viên đánh giá.

### 19.3 Edition-based redefinition

Nếu database dùng edition-based redefinition, object có thể có editioned version. Cùng tên có thể resolve tới edition hiện hành của session.

Kiểm tra CURRENT_EDITION_NAME và editionable object metadata. Một ứng dụng kết nối vào edition khác có thể thấy package/view version khác với SQL Developer. Đây là vấn đề deployment/name resolution, không nhất thiết là thiếu grant.

## 20. Quy trình chẩn đoán ORA-00942

Thực hiện theo trình tự để không thay đổi quyền trước khi biết nguyên nhân.

### Bước 1: Thu thập câu SQL và toàn bộ error stack

Ghi lại SQL chính xác, schema qualification, bind type, thời điểm, application service, database user và connection pool. Không chỉ lưu dòng đầu ORA-00942 nếu stack còn có lỗi remote hoặc PL/SQL.

### Bước 2: Xác định session context

Chạy SESSION_USER, CURRENT_USER, CURRENT_SCHEMA, CON_NAME, SERVICE_NAME và CURRENT_EDITION_NAME từ connection đang lỗi.

### Bước 3: Kiểm tra tên object

Xác định SQL đang tham chiếu tên không qualification, schema.object, synonym hay remote object. Kiểm tra quoted identifier và chữ hoa/thường.

### Bước 4: Tìm object và synonym

Dùng USER_OBJECTS, ALL_OBJECTS, ALL_SYNONYMS và các view tương ứng. Nếu không nhìn thấy object, nhờ DBA/owner xác nhận bằng DBA_OBJECTS trong đúng PDB.

### Bước 5: Kiểm tra target và dependency

Nếu là synonym, kiểm tra target. Nếu là view/package, kiểm tra status, dependencies và compile errors. Nếu có database link, kiểm tra remote database và remote user.

### Bước 6: Kiểm tra quyền

Xem ALL_TAB_PRIVS, SESSION_ROLES và SESSION_PRIVS. Với PL/SQL definer-rights, kiểm tra direct grant cho owner chứ không chỉ role của caller.

### Bước 7: Sửa đúng lớp

- Sai schema/name: sửa SQL hoặc mapping.
- Sai synonym: sửa synonym sau khi xác định target.
- Nhầm PDB/service: sửa connection configuration.
- Thiếu object privilege: owner/DBA cấp đúng object grant.
- Thiếu direct grant cho stored unit: cấp cho definer và compile lại.
- Object chưa deploy: chạy migration đúng môi trường.

### Bước 8: Chạy lại bằng cùng user

Xác nhận từ connection ứng dụng, không chỉ từ DBA account.

## 21. Quy trình chẩn đoán ORA-01031

### Bước 1: Xác định thao tác thất bại

Lỗi xảy ra ở SELECT, DML, CREATE, ALTER, DROP, GRANT, EXECUTE hay trong PL/SQL? Privilege cần thiết khác nhau theo thao tác và object.

### Bước 2: Xác định principal

Xác định SESSION_USER, CURRENT_USER, owner của stored unit và invoker nếu có. Nếu chạy job, xác định job owner/credential.

### Bước 3: Xác định quyền cần có

Ví dụ:

- SELECT object của schema khác: SELECT object privilege.
- Gọi package: EXECUTE trên package.
- Tạo table schema riêng: CREATE TABLE và quota.
- Tạo view: CREATE VIEW và direct grants trên base objects.
- Tạo object trong schema khác: quyền ANY tương ứng, thường cần tài khoản triển khai có kiểm soát.

### Bước 4: Kiểm tra grant path

Xem quyền trực tiếp, quyền qua role, role đang enable và grant option. Với definer-rights PL/SQL, kiểm tra quyền trực tiếp cho owner.

### Bước 5: Cấp quyền tối thiểu

Owner/DBA cấp đúng privilege trên đúng object hoặc system privilege cần cho deployment. Tránh DBA, ANY hoặc UNLIMITED quyền nếu không có yêu cầu rõ.

### Bước 6: Compile và kiểm thử

Compile lại stored unit nếu cần. Chạy câu lệnh bằng đúng user/service. Kiểm thử cả quyền được phép và quyền bị từ chối để bảo đảm security boundary đúng.

## 22. Ví dụ end-to-end: ứng dụng đọc bảng SALES.ORDERS

Giả sử:

- SALES sở hữu bảng ORDERS.
- APP_RUNTIME là user kết nối từ ứng dụng.
- Ứng dụng chỉ cần đọc order_id, status và created_at.
- Không cần DML trực tiếp.

### 22.1 Kiểm tra kết nối

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

Xác nhận SESSION_USER là APP_RUNTIME và service/PDB là môi trường mong muốn.

### 22.2 Kiểm tra object

DBA hoặc owner:

~~~sql
SELECT owner, object_name, object_type, status
FROM dba_objects
WHERE owner = 'SALES'
  AND object_name = 'ORDERS';
~~~

Nếu object tồn tại, kiểm tra đúng object type và trạng thái.

### 22.3 Cấp quyền tối thiểu

Owner SALES:

~~~sql
GRANT SELECT ON sales.orders TO app_runtime;
~~~

### 22.4 Query có qualification

~~~sql
SELECT order_id, status, created_at
FROM sales.orders
WHERE order_id = :order_id;
~~~

### 22.5 Kiểm thử bằng ứng dụng

Dùng chính datasource của APP_RUNTIME. Ghi nhận session context, chạy query và xác nhận kết quả. Nếu cần synonym, tạo private synonym sau khi grant và kiểm thử name resolution.

Không cấp SELECT ANY TABLE vì một query không truy cập được SALES.ORDERS.

## 23. Ví dụ end-to-end: package definer-rights

Giả sử SALES sở hữu ORDERS, APP_OWNER sở hữu package API và APP_RUNTIME chỉ được gọi package.

### 23.1 Cấp quyền cho package owner

~~~sql
GRANT SELECT ON sales.orders TO app_owner;
~~~

Quyền được cấp trực tiếp cho APP_OWNER.

### 23.2 Tạo package

~~~sql
CREATE OR REPLACE PACKAGE app_owner.order_api AS
    PROCEDURE get_order_count(p_count OUT NUMBER);
END order_api;
/

CREATE OR REPLACE PACKAGE BODY app_owner.order_api AS
    PROCEDURE get_order_count(p_count OUT NUMBER) IS
    BEGIN
        SELECT COUNT(*)
          INTO p_count
          FROM sales.orders;
    END get_order_count;
END order_api;
/
~~~

### 23.3 Cấp EXECUTE cho runtime

~~~sql
GRANT EXECUTE ON app_owner.order_api TO app_runtime;
~~~

APP_RUNTIME chỉ cần gọi package:

~~~sql
BEGIN
    app_owner.order_api.get_order_count(:count_value);
END;
/
~~~

Nếu package invalid, kiểm tra ALL_ERRORS của APP_OWNER. Nếu caller không gọi được, kiểm tra EXECUTE và name resolution. Nếu package owner thiếu quyền trên SALES.ORDERS, cấp direct grant cho APP_OWNER và compile lại.

## 24. Bảo mật và nguyên tắc least privilege

Privilege là một phần của thiết kế bảo mật. Một grant quá rộng có thể biến lỗi truy cập một bảng thành quyền đọc/sửa dữ liệu ngoài phạm vi ứng dụng.

Các nguyên tắc:

- Tách owner schema và runtime schema khi phù hợp.
- Runtime account chỉ có quyền cần cho chức năng đang chạy.
- Ưu tiên object grants trên bảng/view/package cụ thể.
- Hạn chế quyền ANY cho tài khoản triển khai được kiểm soát.
- Không cấp DBA cho ứng dụng.
- Không cấp CREATE PUBLIC SYNONYM cho runtime.
- Không cấp GRANT OPTION hoặc ADMIN OPTION nếu không cần phân phối quyền.
- Dùng package/view làm interface khi muốn kiểm soát dữ liệu.
- Kiểm tra quyền cả trong SQL trực tiếp và PL/SQL privilege context.
- Audit grant/revoke và thay đổi synonym.
- Không ghi password database link hoặc secret vào log.
- Không hiển thị chi tiết object nội bộ cho client cuối nếu không cần.

### 24.1 Tách tài khoản deployment và runtime

Một mô hình phổ biến:

| User | Trách nhiệm | Quyền điển hình |
|---|---|---|
| SALES_OWNER | Sở hữu bảng nghiệp vụ | Quyền tạo/sửa object trong schema SALES |
| APP_OWNER | Sở hữu view/package interface | Direct grants cần thiết trên object nền; CREATE VIEW/PROCEDURE |
| APP_RUNTIME | Kết nối từ ứng dụng | SELECT view và EXECUTE package hoặc object grants rất hẹp |
| MIGRATION_USER | Chạy schema migration | Quyền DDL có kiểm soát, chỉ dùng trong release |

Không dùng APP_RUNTIME làm owner của mọi object nếu ứng dụng chỉ cần DML/execute. Việc tách owner và runtime giảm tác động khi credential ứng dụng bị lộ.

### 24.2 Audit quyền

DBA có thể truy vấn quyền cấp trực tiếp và qua role, ghi lại ai cấp, khi nào và vì sao. Quy trình release nên có danh sách grant mong muốn và kiểm tra drift giữa DEV/TEST/PROD.

Không xóa quyền chỉ vì thấy một grant không quen thuộc. Kiểm tra dependency, audit trail, job và package trước khi revoke.

## 25. Những cách sửa sai thường gặp

| Cách làm | Rủi ro | Cách làm phù hợp |
|---|---|---|
| Cấp DBA cho APP_RUNTIME | Quyền gần như toàn database | Cấp object privilege tối thiểu |
| Cấp SELECT ANY TABLE để đọc một bảng | Mở rộng đọc sang nhiều schema | GRANT SELECT ON owner.table |
| Tạo public synonym cho mọi object | Tác động name resolution toàn database | Private synonym hoặc schema qualification |
| Tạo synonym rồi nghĩ đã có quyền | Synonym không cấp privilege | Grant trên target object |
| Dùng ALTER SESSION CURRENT_SCHEMA để né grant | Không tạo thêm quyền | Cấp object privilege đúng |
| Kiểm tra bằng DBA account rồi kết luận app đã có quyền | DBA có quyền khác user ứng dụng | Test bằng đúng datasource/user |
| Chỉ cấp quyền qua role cho definer-rights package | Role bị disable trong unit | Direct grant cho package owner |
| Cấp CREATE ANY TABLE cho runtime | Có thể tạo object trong schema khác | Deployment user có kiểm soát |
| Dùng SELECT trước INSERT để tránh duplicate | Race condition | UNIQUE constraint |
| Sửa synonym ở nhầm PDB | App vẫn lỗi hoặc trỏ sai dữ liệu | Kiểm tra service/container trước |
| Recompile mọi object trên production | Có thể tạo invalidation và tải compile | Compile object liên quan có kiểm soát |
| Đổi tên object quoted tùy tiện | Phá vỡ consumer phụ thuộc | Xác minh dependency và migration |

## 26. Checklist điều tra

### Danh tính và môi trường

- [ ] Đã thu thập toàn bộ error stack và SQL chính xác.
- [ ] Đã xác định SESSION_USER.
- [ ] Đã xác định CURRENT_USER và CURRENT_SCHEMA.
- [ ] Đã xác định service, database và PDB/container.
- [ ] Đã kiểm tra edition nếu môi trường dùng edition-based redefinition.
- [ ] Đã tái hiện bằng đúng user và connection của ứng dụng.

### Phân giải object

- [ ] Đã xác định tên object đầy đủ và object type.
- [ ] Đã kiểm tra owner/schema.
- [ ] Đã kiểm tra chữ hoa/thường và quoted identifier.
- [ ] Đã kiểm tra private/public synonym.
- [ ] Đã kiểm tra synonym target còn tồn tại.
- [ ] Đã kiểm tra database link nếu có.
- [ ] Đã kiểm tra view/package dependency và status.
- [ ] Đã xác nhận object được deploy ở đúng PDB.

### Quyền

- [ ] Đã xác định thao tác cần privilege nào.
- [ ] Đã kiểm tra object grants.
- [ ] Đã kiểm tra system privileges.
- [ ] Đã kiểm tra role được cấp và role đang enable.
- [ ] Đã phân biệt direct grant với role grant.
- [ ] Đã xác định definer-rights hay invoker-rights.
- [ ] Đã kiểm tra direct grant cho owner của stored unit/view khi cần.
- [ ] Đã kiểm tra GRANT OPTION/ADMIN OPTION nếu có thao tác cấp quyền.
- [ ] Đã kiểm tra quota riêng nếu lỗi liên quan tạo segment/table.

### Khắc phục và xác nhận

- [ ] Chỉ sửa đúng SQL, schema, synonym, service hoặc grant gây lỗi.
- [ ] Không cấp DBA/ANY privilege rộng cho runtime.
- [ ] Đã compile lại object bị invalid nếu cần.
- [ ] Đã chạy lại bằng đúng user ứng dụng.
- [ ] Đã kiểm tra quyền được phép và quyền phải bị từ chối.
- [ ] Đã ghi lại grant/synonym/migration change để có thể tái lập.

## 27. Kết luận

ORA-00942 thường liên quan đến việc Oracle không phân giải được tên bảng/view trong ngữ cảnh hiện tại hoặc user không thể truy cập object đó. ORA-01031 cho biết thao tác thiếu privilege. Cả hai cần được điều tra từ đúng session, schema, service/PDB và privilege context.

Hãy lần theo tên object từ SQL tới schema, synonym, view hoặc database link; xác nhận object tồn tại trong đúng container; sau đó kiểm tra object privilege, system privilege và role. Đặc biệt, quyền qua role trong SQL tương tác không thay thế direct grant cần cho static SQL của definer-rights PL/SQL hoặc view definition.

Cách sửa bền vững là dùng schema qualification khi phù hợp, quản lý synonym có chủ đích, cấp object privilege tối thiểu, tách owner khỏi runtime user và kiểm thử bằng đúng connection ứng dụng. Không dùng DBA hoặc quyền ANY rộng để che một lỗi phân giải tên hay một grant còn thiếu.
