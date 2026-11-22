# Phân giải tên theo schema, CURRENT_SCHEMA và synonym

Khi ứng dụng chạy `SELECT * FROM orders`, Oracle phải trả lời một câu hỏi trước khi đọc dữ liệu: **`ORDERS` là đối tượng nào?** Trong một database có nhiều schema, có thể tồn tại `APP_OWNER.ORDERS`, `REPORT_OWNER.ORDERS`, hoặc một synonym mang tên `ORDERS` trỏ tới một bảng ở schema khác. Hai session cùng thực hiện SQL text giống nhau đôi khi truy cập hai đối tượng khác nhau vì **ngữ cảnh phân giải tên** không giống nhau.

Bài này giải thích cách Oracle phân giải tên không kèm schema, cách `CURRENT_SCHEMA` ảnh hưởng phạm vi tìm kiếm, vai trò của **private synonym** và **public synonym**, cách xác minh đối tượng đích qua metadata và lý do **tìm được tên không đồng nghĩa có quyền truy cập**. Các thao tác DDL trong ví dụ chỉ dành cho schema thực hành đã được cấp quyền.

## 1. Ba cách tham chiếu một đối tượng

Giả sử một PDB có schema `APP_OWNER` sở hữu bảng `ORDERS` và user `REPORT_USER` cần đọc bảng này. Ba lối viết có thể dẫn đến cùng bảng:

~~~sql
-- 1. Gọi rõ owner: không cần mặc định schema.
SELECT order_id, amount FROM app_owner.orders;

-- 2. Sau khi session đổi CURRENT_SCHEMA thành APP_OWNER:
SELECT order_id, amount FROM orders;

-- 3. Nếu REPORT_USER có synonym APP_ORDERS trỏ tới APP_OWNER.ORDERS:
SELECT order_id, amount FROM app_orders;
~~~

Điều kiện là mỗi cách phải được thiết lập đúng và user có **quyền SELECT trên bảng đích**. Ba cách có cùng kết quả trong ví dụ đơn giản nhưng mang ý nghĩa khác nhau:

| Cách tham chiếu | Oracle dùng thông tin nào để tìm đối tượng? | Ảnh hưởng đến phạm vi nào? |
|---|---|---|
| `APP_OWNER.ORDERS` | Tên schema và tên đối tượng được viết tường minh | Chỉ tham chiếu cụ thể trong câu SQL đó |
| `ORDERS` | `CURRENT_SCHEMA` và quy tắc tra cứu synonym | Mọi tên không định danh trong câu SQL phù hợp |
| `APP_ORDERS` | Synonym tên `APP_ORDERS`, rồi tên đối tượng mà nó trỏ đến | Alias có thể dùng trong nhiều câu SQL |

Không cách nào tự cấp quyền đọc/ghi bảng. Không cách nào tự đưa session sang PDB khác.

~~~mermaid
flowchart TD
    A["SQL: SELECT ... FROM orders"] --> B["Session hiện ở PDB nào?"]
    B --> C["CURRENT_SCHEMA là gì?"]
    C --> D["Tìm đối tượng hoặc private synonym phù hợp"]
    D --> E["Nếu chưa khớp, xét public synonym"]
    E --> F["Xác định đối tượng đích"]
    F --> G{"Có quyền và đối tượng hợp lệ?"}
    G -->|Có| H["Parse/execute SQL"]
    G -->|Không| I["Thông báo lỗi phù hợp"]
~~~

Sơ đồ thể hiện luồng tư duy khi gặp **tên đối tượng đơn giản** (bảng, view và nhiều đối tượng schema thông dụng). Oracle còn có các quy tắc riêng cho package, type, thành phần PL/SQL, database link, identifier có dấu ngoặc kép và SQL nằm trong stored object. Không nên lấy sơ đồ này làm toàn bộ ngữ pháp phân giải mọi tên trong Oracle.

## 2. Schema, user và container là ba khái niệm cần tách riêng

### 2.1 Schema là gì?

Một **schema** là không gian tên gồm các đối tượng database thuộc một user, chẳng hạn table, view, sequence, package, index và synonym. Trong Oracle, schema gắn với database user; tên user/schema thường là điểm xuất phát của việc xác định đối tượng.

Ví dụ:

~~~text
PDB SALES_PDB
├── APP_OWNER
│   ├── ORDERS       (table)
│   ├── PRODUCTS     (table)
│   └── ORDER_API    (package)
├── REPORT_OWNER
│   └── ORDERS       (table khác)
└── REPORT_USER
    └── APP_ORDERS   (private synonym, nếu được tạo)
~~~

`APP_OWNER.ORDERS` và `REPORT_OWNER.ORDERS` là hai tên đầy đủ khác nhau. Khi gõ `SELECT * FROM ORDERS` mà không chỉ rõ schema, Oracle phải sử dụng **ngữ cảnh session** để chọn tên phù hợp.

### 2.2 Container/PDB xác định giới hạn tìm kiếm

Trong Oracle multitenant, nhiều PDB có thể cùng chứa schema tên `APP_OWNER`, mỗi schema có các bảng riêng. `APP_OWNER.ORDERS` trong `SALES_PDB` không mặc nhiên là đối tượng `APP_OWNER.ORDERS` trong `REPORT_PDB`.

Đầu tiên hãy xác định container đang kết nối:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'CON_ID') AS container_id,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

`ALTER SESSION SET CURRENT_SCHEMA` chỉ thay đổi **schema mặc định trong container hiện tại**; nó **không đổi PDB**. Muốn truy vấn ở PDB khác theo cách thông thường, ứng dụng cần kết nối tới **service của PDB đó** bằng tài khoản phù hợp. Việc chuyển container trong một session là chức năng quản trị riêng, có các điều kiện và quyền `SET CONTAINER`; không dùng `CURRENT_SCHEMA` để thay thế.

### 2.3 Tên service cũng không phải schema

Chuỗi kết nối JDBC ví dụ:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//db-host.example:1521/sales_service
spring.datasource.username=report_user
~~~

`sales_service` định tuyến kết nối, `report_user` là database user đăng nhập, còn `CURRENT_SCHEMA` mặc định thường trùng schema của user đăng nhập khi session được khởi tạo. Có thể dùng `SYS_CONTEXT` để kiểm chứng cả ba; không suy tên schema chỉ từ service hay URL.

## 3. Oracle tìm tên không có tiền tố schema thế nào?

Xét một câu SQL trực tiếp trong session:

~~~sql
SELECT order_id FROM orders;
~~~

Với một tham chiếu đơn giản tới table/view, cách hình dung hữu ích là:

1. **Trong current schema:** Oracle xét đối tượng schema có tên `ORDERS` phù hợp với ngữ cảnh câu SQL.
2. **Private synonym:** khi không tìm thấy đối tượng trực tiếp, Oracle xét private synonym phù hợp trong phạm vi phân giải tên.
3. **Public synonym:** nếu không có đối tượng/private synonym được ưu tiên, Oracle có thể xét public synonym tên `ORDERS`.
4. **Đối tượng đích và quyền:** sau khi xác định mục tiêu, Oracle kiểm tra đối tượng, kiểu sử dụng và quyền cần thiết; nếu không thỏa mãn, câu lệnh thất bại.

Đây là mô hình theo thứ tự ưu tiên cho **tên không định danh thông dụng**. Các namespace và dạng tham chiếu đặc biệt có thể có quy tắc khác, ví dụ `package.procedure` hoặc `schema.object`; khi chẩn đoán phải xét **SQL thật** chứ không áp thứ tự này cho mọi trường hợp.

### 3.1 Ví dụ tên local che public synonym

Giả sử database có public synonym `ORDERS` trỏ tới `APP_OWNER.ORDERS`. Nếu `REPORT_OWNER` đã sở hữu bảng `REPORT_OWNER.ORDERS` và session đặt `CURRENT_SCHEMA = REPORT_OWNER`:

~~~sql
SELECT * FROM orders;
~~~

thì tên đối tượng trực tiếp ở schema đang xét được ưu tiên, nên câu SQL sẽ tham chiếu **`REPORT_OWNER.ORDERS`**, không phải tự động đi qua public synonym.

Điều này giải thích vì sao một câu SQL vốn chạy nhờ public synonym có thể đổi hành vi hoặc gặp lỗi sau khi một object cùng tên được tạo trong schema. **Public synonym không ép mọi session phải sử dụng cùng đối tượng**, vì tên cụ thể hơn có quyền ưu tiên trong phân giải.

### 3.2 Private synonym và object chung namespace

Private synonym nằm trong schema. Bảng, view, sequence và private synonym thuộc một nhóm namespace schema chung trong các trường hợp thông dụng; bạn không thể cứ tạo một private synonym tên `ORDERS` nếu schema đó đã có bảng `ORDERS` cùng tên. Khi cần alias để tránh va chạm, dùng tên rõ nghĩa như `APP_ORDERS` hoặc `ORDER_READ_API`.

Ngược lại, public synonym thuộc phạm vi tên công khai; một local object có thể che public synonym. Vì vậy khi quản lý hệ thống nhiều nhóm, cần tránh đặt public synonym quá chung chung như `DATA`, `ORDERS` hoặc `USER`.

### 3.3 Một tên có dấu chấm chưa chắc luôn là một bảng

Ví dụ:

~~~sql
SELECT * FROM app_owner.orders;
~~~

`APP_OWNER.ORDERS` ở đây là tham chiếu được định danh bằng schema và object; nếu trong `APP_OWNER` có một **private synonym** tên `ORDERS`, tên được định danh có thể tham chiếu synonym đó tùy quy tắc/loại đối tượng. Để chứng minh đích thực sự là bảng nào, hãy tra `ALL_OBJECTS` và `ALL_SYNONYMS` chứ không suy từ hình thức có dấu chấm.

Các biểu thức như `package_name.function_name` hoặc `schema.package_name.procedure_name` có quy tắc phân giải gắn với package, thành phần PL/SQL và namespace khác; dấu chấm không phải luôn có một nghĩa duy nhất.

## 4. SESSION_USER, CURRENT_USER, CURRENT_SCHEMA và USER khác gì?

Một trong những nguyên nhân phổ biến gây nhầm là cho rằng “đã đăng nhập bằng user nào thì mọi tên đối tượng luôn thuộc schema đó”.

Chạy:

~~~sql
SELECT USER AS user_expression,
       SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV', 'CURRENT_USER') AS current_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

| Giá trị | Diễn giải trong session SQL trực tiếp thông thường |
|---|---|
| `USER` / `SESSION_USER` | User của phiên đăng nhập |
| `CURRENT_USER` | Ngữ cảnh user dùng cho kiểm tra quyền/thực thi phù hợp; có thể khác trong stored PL/SQL theo mô hình definer/invoker rights |
| `CURRENT_SCHEMA` | Schema được Oracle dùng mặc định để phân giải nhiều tên đối tượng không định danh |

Ngay sau khi một user đăng nhập bình thường, các giá trị thường cùng tên. Nhưng có thể đổi **`CURRENT_SCHEMA` mà không đổi login user**.

### 4.1 Thay đổi CURRENT_SCHEMA trong một phiên

Đăng nhập bằng `REPORT_USER` có quyền đọc `APP_OWNER.ORDERS` rồi chạy:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS schema_before
FROM dual;

ALTER SESSION SET CURRENT_SCHEMA = APP_OWNER;

SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS schema_after
FROM dual;
~~~

Ví dụ dự kiến:

~~~text
Trước: SESSION_USER=REPORT_USER, CURRENT_SCHEMA=REPORT_USER
Sau:   SESSION_USER=REPORT_USER, CURRENT_SCHEMA=APP_OWNER
~~~

Sau đó, tên không định danh có thể được phân giải tại `APP_OWNER`:

~~~sql
SELECT order_id, amount
FROM orders;
~~~

Lệnh `ALTER SESSION SET CURRENT_SCHEMA` **không đăng nhập lại**, **không đổi user**, **không cấp quyền mới**, **không thay đổi PDB** và **không di chuyển đối tượng từ schema này sang schema khác**.

Nếu `REPORT_USER` chưa có quyền `SELECT` trên `APP_OWNER.ORDERS`, việc tìm đúng tên vẫn không khiến câu `SELECT` thành công.

Khi muốn trả phiên thực hành về schema ban đầu:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = REPORT_USER;

SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

### 4.2 CURRENT_SCHEMA khác với ALTER SESSION SET CONTAINER

~~~sql
-- Đổi schema mặc định, vẫn trong cùng container:
ALTER SESSION SET CURRENT_SCHEMA = APP_OWNER;
~~~

Lệnh trên khác về bản chất với:

~~~sql
-- Chỉ dành cho common user đủ quyền và session/đích phù hợp:
ALTER SESSION SET CONTAINER = SALES_PDB;
~~~

Trong ví dụ thứ hai, Oracle chuyển **container của session** khi điều kiện được đáp ứng. `CURRENT_SCHEMA` không thể được dùng như một đường tắt để “truy cập xuyên PDB”.

### 4.3 CURRENT_SCHEMA không phải quyền tạo hoặc sửa object

Khi đổi `CURRENT_SCHEMA`, các câu SQL hoặc DDL không định danh có thể được diễn giải theo schema mới. Vì vậy phải đặc biệt thận trọng với các lệnh như `CREATE TABLE`, `ALTER TABLE` hoặc các thao tác cấp quyền: **ghi schema rõ ràng khi làm việc với nhiều owner**, kiểm tra `OWNER` sau khi thao tác, và đừng giả định rằng đổi schema sẽ cấp quyền `CREATE ANY TABLE` hay quyền quản trị khác.

`ALTER SESSION SET CURRENT_SCHEMA` thông thường chỉ điều chỉnh ngữ cảnh của session và có thể được dùng mà không cần đặc quyền quản trị đặc biệt. Quyền trên **đối tượng thực tế** vẫn là bước kiểm tra độc lập.

## 5. Ví dụ xuyên suốt với hai tài khoản

Các câu lệnh sau giả định bạn có một **PDB thực hành** và hai user đã được người quản trị chuẩn bị:

- `APP_OWNER` sở hữu bảng nghiệp vụ và có quyền tạo bảng trong schema của mình.
- `REPORT_USER` có quyền tạo private synonym trong schema của mình khi thực hành phần synonym; chưa có quyền đọc `APP_OWNER.ORDERS` cho tới khi được cấp.

**Không chạy các lệnh này trong schema production.** Chúng là thao tác tạo dữ liệu mẫu và cấp quyền phục vụ bài học.

### 5.1 Ở kết nối APP_OWNER: tạo bảng và cấp quyền đọc

~~~sql
-- Chạy khi đang đăng nhập APP_OWNER, trong PDB thực hành.
CREATE TABLE orders (
    order_id NUMBER(10) PRIMARY KEY,
    amount   NUMBER(12,2) NOT NULL
);

INSERT INTO orders (order_id, amount) VALUES (101, 125000);
INSERT INTO orders (order_id, amount) VALUES (102, 84000);
COMMIT;

-- APP_OWNER là chủ bảng, cấp đúng quyền SELECT cần thiết.
GRANT SELECT ON orders TO report_user;
~~~

Sau khi cấp, `REPORT_USER` mới có thể đọc bảng theo quyền được cấp. Nếu muốn thực hiện `INSERT` hoặc `UPDATE` từ `REPORT_USER`, cần quyền tương ứng; **`SELECT` không bao hàm quyền ghi**.

### 5.2 Ở kết nối REPORT_USER: tên đầy đủ luôn rõ ràng

~~~sql
SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS login_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM dual;

SELECT order_id, amount
FROM app_owner.orders
ORDER BY order_id;
~~~

Truy vấn sau dùng tên đầy đủ nên không phụ thuộc vào việc `CURRENT_SCHEMA` có trùng `APP_OWNER` hay không, trong phạm vi PDB đang kết nối và quyền `SELECT` đã cấp.

Giả sử `REPORT_USER` chưa có bảng/view/synonym tên `ORDERS`, câu:

~~~sql
SELECT order_id, amount
FROM orders;
~~~

có thể thất bại với `ORA-00942`. Lỗi này **không có nghĩa** bảng `APP_OWNER.ORDERS` không tồn tại; tên không định danh chưa dẫn tới đúng object hoặc quyền không đáp ứng.

### 5.3 Đổi CURRENT_SCHEMA rồi dùng tên ngắn

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = APP_OWNER;

SELECT order_id, amount
FROM orders
ORDER BY order_id;

SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS login_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Kết quả câu đọc dữ liệu giống cách gọi `APP_OWNER.ORDERS`, nhưng login user vẫn là `REPORT_USER`. Điều này minh họa sự khác nhau giữa **mặc định tìm tên** và **chủ sở hữu đối tượng**.

Trước khi thử synonym riêng trong schema `REPORT_USER`, khôi phục:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = REPORT_USER;
~~~

### 5.4 Tạo private synonym trong REPORT_USER

~~~sql
-- Chạy khi đang đăng nhập REPORT_USER, CURRENT_SCHEMA=REPORT_USER.
-- Cần quyền CREATE SYNONYM phù hợp.
CREATE SYNONYM app_orders FOR app_owner.orders;

SELECT order_id, amount
FROM app_orders
ORDER BY order_id;
~~~

`APP_ORDERS` là một **tên thay thế**. Nó không chứa bản sao của hai hàng `ORDERS` và không phải view sao chép dữ liệu. Khi sử dụng alias này, Oracle phân giải tới `APP_OWNER.ORDERS` theo metadata synonym, rồi áp dụng các kiểm tra quyền thực tế.

Muốn kiểm tra object thật, vẫn có thể gọi:

~~~sql
SELECT order_id, amount
FROM app_owner.orders
ORDER BY order_id;
~~~

Nếu `APP_OWNER` bổ sung hàng mới vào bảng và commit, khi đọc lại bằng synonym, `REPORT_USER` truy cập bảng đích theo các quy tắc nhất quán đọc của Oracle; synonym không có bộ dữ liệu riêng cần “đồng bộ”.

### 5.5 Nếu không có quyền CREATE SYNONYM

Việc tạo alias có thể thất bại do thiếu quyền DDL. Bài học vẫn có thể hoàn thành phần phân giải tên bằng `APP_OWNER.ORDERS` và `ALTER SESSION SET CURRENT_SCHEMA`; phần tạo private synonym cần nhờ quản trị viên cấp quyền phù hợp **trong môi trường thực hành**, hoặc cung cấp một synonym đã tồn tại. Không cần cấp `CREATE PUBLIC SYNONYM` hay quyền quản trị rộng chỉ để chạy ví dụ này.

## 6. Synonym: alias, không phải bảng, view hay GRANT

Oracle hỗ trợ synonym để tạo một tên tham chiếu thay cho đối tượng khác. Synonym có thể trỏ đến table, view, sequence, package, procedure, function, type và những loại đối tượng được hỗ trợ khác; trong một số cấu hình, synonym còn có thể tham chiếu đối tượng qua database link.

~~~mermaid
flowchart LR
    A["REPORT_USER chạy SELECT FROM app_orders"] --> B["Private synonym REPORT_USER.APP_ORDERS"]
    B --> C["Bảng APP_OWNER.ORDERS"]
    D["Quyền SELECT trên APP_OWNER.ORDERS"] --> C
    C --> E["Dữ liệu thật của ORDERS"]
~~~

Điểm quan trọng:

- **Synonym là metadata tên thay thế.** Nó không tạo bản sao dữ liệu, không tạo index riêng cho alias.
- **Synonym không cấp quyền.** User cần quyền thao tác trên đối tượng đích, dù tên synonym được phân giải thành công.
- **Synonym có thể mất hiệu lực sử dụng** nếu object đích bị đổi tên/xóa, quyền bị thu hồi, hoặc chuỗi synonym không còn hợp lệ.
- **Synonym không đổi schema chủ sở hữu.** Dữ liệu vẫn ở `APP_OWNER.ORDERS`; alias `REPORT_USER.APP_ORDERS` nằm trong schema của `REPORT_USER`.
- **Synonym không vượt giới hạn PDB.** Nó được xét trong container và ngữ cảnh truy cập liên quan, không phải đường tắt để lấy bảng của PDB khác.

### 6.1 Private synonym

Tạo trong schema của user thực hành:

~~~sql
CREATE SYNONYM order_reader FOR app_owner.orders;
~~~

Truy vấn:

~~~sql
SELECT * FROM order_reader;
~~~

Người dùng khác không tự thấy private synonym của `REPORT_USER` khi gõ cùng tên ngắn trong schema của họ. Trong những trường hợp được quyền và loại đối tượng hỗ trợ, một private synonym cũng có thể được gọi theo tên đầy đủ `REPORT_USER.ORDER_READER`, nhưng quyền trên đối tượng đích vẫn được kiểm tra.

Tạo private synonym trong **schema khác** cần quyền cao hơn (ví dụ `CREATE ANY SYNONYM`) và cần được quản trị cẩn thận; user thông thường chỉ nên tạo alias trong schema được phép sở hữu.

### 6.2 Public synonym

**Public synonym** nằm trong namespace công khai của database/container theo phạm vi tương ứng. Nó giúp những session không có một object/private synonym ưu tiên hơn có thể phân giải cùng một tên, ví dụ các public synonym do Oracle cung cấp hoặc DBA đã thiết lập.

Cú pháp để **minh họa cho quản trị viên**, không chạy trong bài thực hành user thường:

~~~sql
-- Ví dụ DDL chỉ dành cho quản trị viên được ủy quyền:
CREATE PUBLIC SYNONYM app_orders_global FOR app_owner.orders;
~~~

Lệnh này cần quyền `CREATE PUBLIC SYNONYM` và có thể làm thay đổi namespace dùng chung. Public synonym không làm cho bảng `APP_OWNER.ORDERS` tự động có quyền `SELECT` dành cho mọi user; việc cấp quyền vẫn phải làm **trên đối tượng đích** theo nhu cầu và chính sách.

| Thuộc tính | Private synonym | Public synonym |
|---|---|---|
| Nơi đặt tên alias | Schema cụ thể | Namespace `PUBLIC` theo phạm vi database/container |
| Chủ thể hay tạo | Chủ schema có `CREATE SYNONYM` | DBA/user có `CREATE PUBLIC SYNONYM` |
| Khả năng hiện diện | Phân giải trong ngữ cảnh schema và quyền phù hợp | Có thể được tìm khi không có tên ưu tiên hơn |
| Có sao chép bảng? | Không | Không |
| Có cấp quyền trên bảng đích? | Không | Không |
| Rủi ro đặt tên chung | Chủ yếu trong phạm vi schema | Cao hơn do có thể va chạm với tên của nhiều ứng dụng |

### 6.3 Synonym trỏ đến synonym khác

Một synonym có thể trỏ đến tên khác; chuỗi phụ thuộc quá dài hoặc vòng lặp có thể gây khó theo dõi, và **chuỗi synonym vòng tròn** có thể dẫn đến lỗi `ORA-01775: looping chain of synonyms`. Khi điều tra, phải lần theo `TABLE_OWNER`, `TABLE_NAME` và `DB_LINK` thay vì chỉ xem alias đầu tiên.

Ví dụ về metadata liên kết (chỉ là minh họa):

~~~text
REPORT_USER.ORDERS_API
  -> APP_OWNER.ORDERS

REPORT_USER.ORDERS_OLD
  -> REPORT_USER.ORDERS_API
  -> APP_OWNER.ORDERS
~~~

Trong thiết kế mới, alias đơn giản và tên rõ nghĩa thường dễ quản lý hơn chuỗi synonym nhiều tầng.

### 6.4 Synonym trỏ qua database link

Nếu hệ thống đã được thiết lập database link, synonym có thể tham chiếu đối tượng từ xa, ví dụ về **cú pháp**:

~~~sql
-- Minh họa cú pháp; SALES_REMOTE_LINK phải tồn tại và được ủy quyền.
CREATE SYNONYM remote_orders FOR app_owner.orders@SALES_REMOTE_LINK;
~~~

Khi đó việc truy vấn còn phụ thuộc database link, kết nối, user và quyền ở database từ xa. `DB_LINK` trong metadata synonym cho biết đường tham chiếu từ xa; không nên suy rằng target đang nằm trong cùng PDB/datafile local. Ví dụ này không yêu cầu tạo database link hay mở kết nối đến hệ thống khác.

## 7. Tìm đúng đối tượng bằng metadata

Khi nghi ngờ câu SQL đang đi qua synonym hoặc current schema khác với dự kiến, hãy ghi nhận **ngữ cảnh phiên**, **object trùng tên**, **synonym** và **quyền**. Mỗi nhóm được phản ánh bởi các data dictionary view riêng.

### 7.1 Xác nhận phiên trước

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV', 'CURRENT_USER') AS current_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

Giả sử kết quả:

~~~text
SESSION_USER  CURRENT_USER  CURRENT_SCHEMA  CON_NAME   SERVICE_NAME
------------ ------------- --------------- ---------- --------------
REPORT_USER   REPORT_USER   APP_OWNER       SALES_PDB  sales_service
~~~

Điều cần thấy: user đang đăng nhập vẫn là `REPORT_USER` nhưng SQL không định danh có thể được phân giải trong `APP_OWNER`. Khi chẩn đoán, đừng chỉ đọc cột `SESSION_USER` rồi mặc định mọi đối tượng thuộc schema đó.

### 7.2 Tìm các đối tượng cùng tên

~~~sql
SELECT owner,
       object_name,
       object_type,
       status
FROM all_objects
WHERE object_name = 'ORDERS'
ORDER BY owner, object_type;
~~~

Ví dụ:

~~~text
OWNER         OBJECT_NAME  OBJECT_TYPE  STATUS
------------  -----------  -----------  -------
APP_OWNER     ORDERS       TABLE        VALID
REPORT_OWNER  ORDERS       TABLE        VALID
~~~

`ALL_OBJECTS` cho thấy **các đối tượng mà user có thể quan sát theo quyền/truy cập metadata**. Nó không nhất thiết liệt kê mọi object trong database, nhất là nếu tài khoản chỉ có quyền hạn chế. Với tài khoản quản trị được phép, `DBA_OBJECTS` mở rộng phạm vi theo quyền. Vì các định danh không đặt dấu ngoặc kép thường được Oracle chuẩn hóa thành chữ hoa, ví dụ tìm tên `'ORDERS'` thay vì `'orders'`.

### 7.3 Tìm private/public synonym

~~~sql
SELECT owner,
       synonym_name,
       table_owner,
       table_name,
       db_link
FROM all_synonyms
WHERE synonym_name IN ('ORDERS', 'APP_ORDERS', 'APP_ORDERS_GLOBAL')
ORDER BY owner, synonym_name;
~~~

| Cột | Dùng để xác định điều gì? |
|---|---|
| `OWNER` | Chủ synonym, ví dụ `REPORT_USER` hoặc `PUBLIC` |
| `SYNONYM_NAME` | Alias mà SQL có thể tham chiếu |
| `TABLE_OWNER` | Schema/chủ của đối tượng mà synonym tham chiếu |
| `TABLE_NAME` | Tên đối tượng đích được khai báo trong synonym |
| `DB_LINK` | Tên database link nếu alias đi đến đối tượng từ xa; thường `NULL` nếu local |

`ALL_SYNONYMS` phản ánh các synonym mà user có thể quan sát theo phạm vi view, bao gồm những public synonym phù hợp. `USER_SYNONYMS` tập trung vào synonym do user sở hữu; `DBA_SYNONYMS` chỉ dành cho tài khoản có quyền xem toàn diện tương ứng.

Một synonym được liệt kê **không bảo đảm đối tượng đích còn tồn tại, còn đúng loại hoặc user có quyền sử dụng**. Metadata synonym chỉ cho biết **tên mà alias khai báo tham chiếu đến**.

### 7.4 Xem quyền trên object

~~~sql
SELECT grantor,
       grantee,
       owner,
       table_name,
       privilege
FROM all_tab_privs
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY grantee, privilege;
~~~

`ALL_TAB_PRIVS` liệt kê các quyền object mà user có thể quan sát. Nếu đã được chủ bảng cấp `SELECT` trực tiếp, có thể thấy grant tương ứng theo phạm vi truy vấn. Tuy nhiên quyền có thể đến từ role, `PUBLIC` hoặc cơ chế quản trị khác; **kết quả thiếu một hàng không tự chứng minh không có bất kỳ đường cấp quyền nào**. Với stored PL/SQL, quyền thông qua role còn có các quy tắc riêng.

Không có lệnh `GRANT SELECT ON app_orders ...` để đồng nhất synonym với bảng chứa dữ liệu: **hãy cấp quyền trên đối tượng đích** (`APP_OWNER.ORDERS`) theo phạm vi cần thiết.

### 7.5 USER_OBJECTS không chạy theo CURRENT_SCHEMA

Một nhầm lẫn thường gặp: sau khi đổi `CURRENT_SCHEMA = APP_OWNER`, gọi `USER_OBJECTS` rồi hy vọng view hiển thị toàn bộ object của `APP_OWNER`.

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = APP_OWNER;

SELECT object_name, object_type
FROM user_objects
WHERE object_name = 'ORDERS';
~~~

`USER_OBJECTS` mô tả object thuộc **user** theo ngữ cảnh view, không tự biến thành “object của mọi schema được đặt vào `CURRENT_SCHEMA`” bởi lệnh `ALTER SESSION`. Muốn kiểm tra object `APP_OWNER.ORDERS` mà user được phép quan sát, truy vấn `ALL_OBJECTS` với `OWNER = 'APP_OWNER'`; với quyền quản trị, có thể dùng `DBA_OBJECTS`. Sau ví dụ, khôi phục `CURRENT_SCHEMA` nếu cần.

## 8. Tên không định danh, tên định danh và dấu ngoặc kép

### 8.1 Tên không đặt dấu ngoặc kép thường được chuẩn hóa chữ hoa

Oracle xử lý nhiều identifier không đặt dấu ngoặc kép theo dạng chữ hoa:

~~~sql
SELECT * FROM app_owner.orders;
SELECT * FROM APP_OWNER.ORDERS;
~~~

Hai câu trên cùng sử dụng các identifier không đặt dấu ngoặc kép nên tham chiếu cùng tên chuẩn hóa (khi object tồn tại và quyền đủ). Vì vậy trong `ALL_OBJECTS`, bạn thường thấy `OBJECT_NAME = 'ORDERS'`.

### 8.2 Tên đặt dấu ngoặc kép giữ chính xác chữ hoa/thường

Nếu chủ schema tạo:

~~~sql
-- Chỉ trong schema thử nghiệm
CREATE TABLE "OrderItems" (
    "OrderId" NUMBER PRIMARY KEY
);
~~~

thì truy vấn thông thường phải giữ cách viết:

~~~sql
SELECT "OrderId"
FROM "OrderItems";
~~~

`SELECT OrderId FROM OrderItems` là cách Oracle hiểu các identifier không đặt dấu ngoặc kép thành `ORDERID` và `ORDERITEMS`; nó có thể không tìm thấy object `"OrderItems"` đã tạo. Synonym và tên schema cũng chịu quy tắc quote/case phù hợp. Việc sử dụng identifier có dấu ngoặc kép cần có lý do vì có thể tăng lỗi gõ tên và khác biệt giữa các công cụ/ORM.

### 8.3 Tên đầy đủ là một cách giữ đường đi rõ ràng

Khi đọc log hoặc debug một API, câu:

~~~sql
SELECT order_id FROM app_owner.orders WHERE order_id = :id;
~~~

cho phép người đọc xác định rõ schema mà tác giả dự định dùng, trong PDB đang kết nối. Trường hợp object tại `APP_OWNER.ORDERS` là synonym thay vì table, metadata vẫn phải được kiểm tra để xác định đích cuối cùng. Tên đầy đủ giảm phụ thuộc vào việc session bị đổi `CURRENT_SCHEMA` giữa chừng nhưng không giải quyết sai service/PDB hoặc thiếu quyền.

## 9. Ảnh hưởng trong ứng dụng Java, JDBC và connection pool

Trong ứng dụng Java hoặc Spring, repository có thể gửi câu SQL:

~~~java
String sql = "SELECT order_id, amount FROM orders WHERE order_id = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 101L);
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            // Xử lý bản ghi trả về.
        }
    }
}
~~~

Giả sử ứng dụng có import JDBC và `Connection connection` được tạo đúng cách. Dấu `?` bind giá trị `order_id`, còn tên `orders` trong SQL vẫn phải được Oracle **phân giải thành object cụ thể**.

Nếu ứng dụng dùng connection pool, mỗi physical connection có một session state. Một request gọi:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = REPORT_OWNER;
~~~

rồi trả connection về pool mà không khôi phục ngữ cảnh có thể khiến request kế tiếp thực thi `FROM orders` ở schema khác với dự kiến. Kết quả có thể là sai bảng, thiếu quyền, hoặc trả số liệu không đúng nghiệp vụ.

### 9.1 Những lựa chọn ổn định hơn cho ứng dụng

| Tình huống | Cách tổ chức dễ kiểm soát |
|---|---|
| Ứng dụng luôn truy cập schema duy nhất | Dùng tên `APP_OWNER.ORDERS` rõ ràng, hoặc cấu hình default schema một cách nhất quán ở tất cả connection |
| Ứng dụng cần trừu tượng hóa tên owner | Dùng private synonym có quản lý, theo dõi alias và quyền của object đích |
| Ứng dụng dùng nhiều schema trong cùng PDB | Dùng tên đủ schema với các object quan trọng, quản lý quyền theo nguyên tắc tối thiểu |
| Ứng dụng dùng nhiều PDB | Cấu hình kết nối/service theo PDB; không dùng `CURRENT_SCHEMA` thay cho PDB |
| Pool tái sử dụng session | Khởi tạo/reset session state rõ ràng; không để yêu cầu trước vô tình thay đổi ngữ cảnh yêu cầu sau |
| ORM tự sinh SQL | Kiểm tra cấu hình schema naming và SQL được sinh thực tế; xác minh owner qua metadata khi có lỗi |

Không ghép schema name do người dùng cung cấp trực tiếp vào SQL:

~~~java
// Không an toàn nếu schemaName đến trực tiếp từ input không kiểm soát:
String sql = "SELECT * FROM " + schemaName + ".orders";
~~~

Bind variable `?` chỉ đại diện **giá trị dữ liệu**, không đại diện identifier như schema, table hoặc tên cột. Nếu hệ thống bắt buộc chọn schema động, dùng danh sách cho phép được kiểm soát và xác minh định danh trước khi tạo SQL; không xem `CURRENT_SCHEMA` là giải pháp thay thế kiểm soát quyền.

### 9.2 SQL trong PL/SQL đã biên dịch có ngữ cảnh riêng

Không nên giả định việc đổi `CURRENT_SCHEMA` trong session sẽ chuyển hướng toàn bộ SQL tĩnh bên trong một package/procedure đã biên dịch sang bảng cùng tên ở schema khác. Với **definer's rights** và **invoker's rights**, Oracle có quy tắc riêng về ngữ cảnh thực thi, quyền và phân giải object. SQL tĩnh trong stored object có thể đã được phân giải/gắn dependency khi biên dịch, còn dynamic SQL cần xét ngữ cảnh thực thi cụ thể.

Khi một câu SQL chạy trực tiếp trả kết quả đúng nhưng code trong package không tìm thấy object, hãy kiểm tra **owner của package, kiểu quyền thực thi, dependency và các grant trực tiếp** bên cạnh `CURRENT_SCHEMA`. Đừng chữa lỗi stored PL/SQL chỉ bằng cách đặt `CURRENT_SCHEMA` ở client.

## 10. Chẩn đoán lỗi khi Oracle không tìm thấy hoặc sử dụng được object

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| `ORA-00942: table or view does not exist` | Tên chưa phân giải tới object hợp lệ, sai schema/PDB hoặc thiếu quyền SELECT | Đọc `CON_NAME`, `CURRENT_SCHEMA`, truy vấn `ALL_OBJECTS` và kiểm tra quyền |
| `ORA-01031: insufficient privileges` | User thiếu quyền thực hiện thao tác cụ thể | Kiểm tra quyền object/system theo câu SQL thực tế |
| `ORA-00980: synonym translation is no longer valid` | Synonym không thể phân giải đích hợp lệ, đích thay đổi hoặc không dùng được theo quyền/đường kết nối | Tra `ALL_SYNONYMS` rồi kiểm tra object đích, DB link và quyền |
| `ORA-01775: looping chain of synonyms` | Synonym trỏ vòng lặp qua các alias | Dò chuỗi `OWNER.SYNONYM_NAME → TABLE_OWNER.TABLE_NAME` |
| `ORA-00955: name is already used by an existing object` | Tên alias/object xung đột trong namespace tương ứng | Kiểm tra `ALL_OBJECTS` và `ALL_SYNONYMS` trước khi tạo |
| `PLS-00201: identifier must be declared` | PL/SQL không nhìn thấy tên/không có quyền phù hợp trong ngữ cảnh biên dịch/thực thi | Kiểm tra owner package, grant trực tiếp, loại AUTHID và dependency |
| Cùng `FROM orders` nhưng hai user thấy hai dữ liệu | `CURRENT_SCHEMA` khác, local object hoặc synonym khác, hoặc PDB khác | So sánh `CON_NAME`, `CURRENT_SCHEMA`, `ALL_OBJECTS` và `ALL_SYNONYMS` của hai phiên |
| Đổi `CURRENT_SCHEMA` nhưng vẫn không `SELECT` được | Không có quyền trên table/view đích | Yêu cầu grant tối thiểu trên object đích; không xem đổi schema là cấp quyền |
| Một schema thấy alias, schema khác không thấy | Private synonym chỉ tồn tại trong phạm vi schema/kiểu tra cứu phù hợp | Kiểm tra `OWNER` của synonym và cách câu SQL tham chiếu |
| Public synonym hoạt động ở một schema, sai ở schema khác | Local object/private synonym có độ ưu tiên cao hơn alias public | Kiểm tra tên trùng trong current schema |

**`ORA-00942` không phải bằng chứng duy nhất rằng bảng bị xóa.** Oracle có thể trả thông báo này khi user thiếu quyền trên object mà họ cố truy cập. Trước khi tạo lại bảng hoặc đổi tên, xác minh container, schema, synonym và grant.

### 10.1 Trình tự kiểm tra khi SELECT báo lỗi

~~~mermaid
flowchart TD
    A["SELECT FROM orders lỗi hoặc trả sai dữ liệu"] --> B["Xác nhận CON_NAME / service"]
    B --> C["Xác nhận SESSION_USER và CURRENT_SCHEMA"]
    C --> D{"Đang dùng tên schema.object?"}
    D -->|Có| E["Tra object/synonym tại schema đã ghi"]
    D -->|Không| F["Tra object/private synonym trong current schema"]
    F --> G["Nếu cần, kiểm tra public synonym"]
    E --> H["Xác nhận đối tượng đích và quyền"]
    G --> H
    H --> I{"Object và quyền hợp lệ?"}
    I -->|Có| J["Kiểm tra SQL, schema và dữ liệu thực tế"]
    I -->|Không| K["Điều chỉnh đúng tên, quyền hoặc synonym"]
~~~

Trình tự này ưu tiên quan sát **không làm thay đổi dữ liệu**. Với bảng lớn, có thể thử phân giải/kiểm tra quyền đọc bằng một truy vấn không yêu cầu lấy hàng:

~~~sql
SELECT *
FROM app_owner.orders
WHERE 1 = 0;
~~~

Truy vấn có thể giúp phát hiện lỗi tên/quyền mà không quét hàng để trả kết quả. Nó không chứng minh tất cả phép toán DML hoặc hiệu năng trên bảng đều hoạt động tốt, và vẫn phải chạy trong đúng PDB.

## 11. Bài thực hành: chứng minh từng cơ chế bằng cùng một bảng

Trong PDB thực hành đã có `APP_OWNER.ORDERS` và `REPORT_USER` được cấp `SELECT`, hãy thực hiện các bước sau:

**Bước 1 — Ghi lại trạng thái đầu**

~~~sql
SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV','CON_NAME') AS container_name
FROM dual;
~~~

Ghi cả service của connection. Xác nhận bằng account `REPORT_USER` trước khi tiếp tục.

**Bước 2 — Thử tên có owner**

~~~sql
SELECT order_id, amount
FROM app_owner.orders
ORDER BY order_id;
~~~

Giải thích vì sao câu này không cần `CURRENT_SCHEMA = APP_OWNER`, nhưng cần quyền `SELECT` của user.

**Bước 3 — Đổi current schema và thử tên ngắn**

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = APP_OWNER;

SELECT order_id, amount FROM orders ORDER BY order_id;

SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

So sánh login user trước/sau. Nếu kết quả đọc bảng khác thường, đối chiếu object đích và quyền trước khi sửa dữ liệu.

**Bước 4 — Trả CURRENT_SCHEMA về REPORT_USER**

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = REPORT_USER;
~~~

**Bước 5 — Sử dụng private synonym**

Nếu được cấp quyền tạo synonym:

~~~sql
CREATE SYNONYM app_orders FOR app_owner.orders;

SELECT order_id, amount
FROM app_orders
ORDER BY order_id;
~~~

Nếu synonym `APP_ORDERS` đã tồn tại, không chạy lại lệnh `CREATE`; dùng alias có sẵn hoặc xin một tên thực hành khác. Ghi nhận việc tạo alias không cần sao chép hàng dữ liệu và không phát sinh quyền đọc mới trên target.

**Bước 6 — Đọc metadata**

~~~sql
SELECT owner, object_name, object_type
FROM all_objects
WHERE object_name IN ('ORDERS', 'APP_ORDERS')
ORDER BY owner, object_name;

SELECT owner, synonym_name, table_owner, table_name, db_link
FROM all_synonyms
WHERE synonym_name = 'APP_ORDERS';
~~~

Điền kết quả vào bảng:

| Câu SQL/cách tra | Schema hoặc synonym ban đầu | Đối tượng đích thực tế | Quyền cần có |
|---|---|---|---|
| `APP_OWNER.ORDERS` | `APP_OWNER` | `APP_OWNER.ORDERS` | `SELECT` trên bảng |
| `ORDERS` sau `CURRENT_SCHEMA=APP_OWNER` | `APP_OWNER` | `APP_OWNER.ORDERS` nếu là table được tạo ở trên | `SELECT` trên bảng |
| `APP_ORDERS` khi `CURRENT_SCHEMA=REPORT_USER` | `REPORT_USER.APP_ORDERS` | `APP_OWNER.ORDERS` | `SELECT` trên bảng |

**Bước 7 — Thảo luận thay vì thử quyền rộng**

Một người khác dùng `REPORT_OWNER` cũng có bảng tên `ORDERS`. Dự đoán kết quả khi session của họ gọi `FROM ORDERS`, khi đổi `CURRENT_SCHEMA` thành `APP_OWNER` (nếu vẫn có quyền) và khi viết `APP_OWNER.ORDERS` trực tiếp. Giải thích thêm tình huống có public synonym `ORDERS` và tại sao object local được ưu tiên.

### Câu hỏi tự kiểm tra

1. `SESSION_USER` và `CURRENT_SCHEMA` khác nhau trong trường hợp nào? Lệnh nào có thể làm chúng khác nhau trong session SQL trực tiếp?
2. `ALTER SESSION SET CURRENT_SCHEMA = APP_OWNER` có làm `REPORT_USER` thành chủ bảng `ORDERS` không? Có tự cấp quyền `SELECT` không?
3. Tại sao public synonym không bảo đảm mọi session chạy `FROM ORDERS` sẽ dùng cùng một bảng?
4. Làm sao biết `APP_ORDERS` là table, view hay synonym, và nếu là synonym thì nó đang trỏ đi đâu?
5. `ALL_OBJECTS` và `USER_OBJECTS` khác nhau thế nào khi đã đổi `CURRENT_SCHEMA`?
6. Vì sao tên `APP_OWNER.ORDERS` vẫn có thể chỉ tới hai đối tượng khác nhau nếu kết nối vào hai PDB khác nhau?
7. Tại sao bind variable dùng để truyền `:id` được nhưng không thể thay thế trực tiếp tên schema/table ở vị trí identifier?
8. Nếu ứng dụng dùng connection pool và đổi `CURRENT_SCHEMA` giữa các request, nguy cơ nào xảy ra?

## 12. Ghi nhớ để tránh truy vấn nhầm đối tượng

Một câu SQL trong Oracle được hiểu trong **ngữ cảnh của session**, không chỉ từ chuỗi ký tự hiển thị trong editor. Khi nhìn thấy:

~~~sql
SELECT * FROM orders;
~~~

hãy tự hỏi:

- Phiên đang kết nối **PDB/service** nào?
- `CURRENT_SCHEMA` đang là gì, có khác `SESSION_USER` không?
- Trong schema đang xét có bảng/view hoặc private synonym `ORDERS` không? Có public synonym cùng tên không?
- Synonym trỏ tới đối tượng nào, có đi qua database link không?
- User thực thi có quyền cần thiết trên đối tượng đích không?

Nếu muốn chắc chắn về schema đích, viết rõ `APP_OWNER.ORDERS` và xác nhận container. Nếu cần alias ổn định, dùng synonym có quản lý và kiểm tra metadata; nếu đổi `CURRENT_SCHEMA`, kiểm soát trạng thái session và connection pool. **Schema-qualified name, CURRENT_SCHEMA và synonym là ba cơ chế đặt/tra tên khác nhau; không cơ chế nào thay thế kiểm tra quyền và container.**
