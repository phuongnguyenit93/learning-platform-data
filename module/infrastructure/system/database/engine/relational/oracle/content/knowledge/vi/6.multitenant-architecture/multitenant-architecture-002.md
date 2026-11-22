# Container hiện tại, CON_ID và chuyển container đúng phạm vi

Trong Oracle Database sử dụng kiến trúc **multitenant**, một kết nối thành công chưa đủ để khẳng định câu SQL đang chạy ở đúng nơi. Cùng một instance có thể phục vụ **CDB root** và nhiều **PDB**; mỗi PDB chứa các schema, đối tượng và dữ liệu ứng dụng theo phạm vi riêng. Trước khi tạo bảng, đọc dữ liệu, cấp quyền hoặc thực hiện thao tác quản trị, phải trả lời được ba câu hỏi:

1. **Session hiện ở container nào?**
2. **CON_ID của container đó có ý nghĩa gì, và nó khác các CON_ID đang thấy trong view ra sao?**
3. **Muốn làm việc với một PDB khác thì kết nối hoặc chuyển container bằng cách nào, với quyền nào?**

Bài này sử dụng SQL*Plus/SQLcl và các câu SQL chỉ đọc để xác định ngữ cảnh; phần chuyển container có ví dụ `ALTER SESSION SET CONTAINER` dành cho **tài khoản quản trị/common user được cấp quyền**. Mọi tên PDB/service trong ví dụ đều là giả định, cần thay bằng giá trị thực tế.

## 1. Vì sao container là một phần của ngữ cảnh thực thi SQL?

Giả sử hệ thống có CDB `SALESDB` với hai PDB:

~~~mermaid
flowchart TD
    C["Oracle CDB: SALESDB"] --> R["CDB$ROOT (CON_ID = 1)"]
    C --> S["PDB$SEED (thường CON_ID = 2)"]
    C --> A["SALES_PDB (ví dụ CON_ID = 3)"]
    C --> B["REPORT_PDB (ví dụ CON_ID = 4)"]
    A --> A1["Schema SALES_APP"]
    A1 --> A2["ORDERS, PRODUCTS..."]
    B --> B1["Schema REPORT_APP"]
    B1 --> B2["Bảng và view báo cáo"]
~~~

**CDB** (*Container Database*) cung cấp hạ tầng và các thành phần dùng chung. **`CDB$ROOT`** là container gốc để quản lý CDB và những thành phần chung. **`PDB$SEED`** là PDB mẫu phục vụ việc tạo PDB khác; nó thường được mở `READ ONLY`. **PDB ứng dụng** là nơi người dùng và bảng nghiệp vụ của ứng dụng thường cư trú.

Trong cùng một CDB, các tên bảng giống nhau có thể xuất hiện trong hai PDB khác nhau mà chứa dữ liệu khác nhau. Ví dụ, chạy:

~~~sql
SELECT COUNT(*) FROM orders;
~~~

không có nghĩa Oracle tự tìm bảng `ORDERS` trong mọi PDB. Oracle phân giải tên đối tượng dựa trên **container, schema và quyền của session hiện tại**. Vì vậy một kết quả `ORA-00942` hoặc số dòng khác dự kiến có thể bắt nguồn từ việc kết nối vào sai PDB, chứ không nhất thiết bảng đã bị xóa.

| Khái niệm | Vai trò | Có phải “container hiện tại” không? |
|---|---|---|
| Database/CDB name | Tên database tổng thể, ví dụ `SALESDB` | Không: tên CDB không cho biết session ở root hay PDB |
| Instance name | Tên instance chạy bộ nhớ/tiến trình, ví dụ `sales1` | Không: một instance có thể phục vụ nhiều container |
| Service name | Tên dịch vụ client dùng để định tuyến kết nối | Service có thể trỏ vào PDB, nhưng cần xác minh container thực tế |
| Container name | `CDB$ROOT` hoặc tên PDB như `SALES_PDB` | **Có**: đây là phạm vi hiện tại của session |
| `CON_ID` | Mã số định danh container trong một CDB | **Có thể đối chiếu** với tên container trong cùng database |
| Schema/current schema | Không gian tên để tìm bảng, view, package... trong container | Không: đổi schema không phải đổi PDB |

Một session thông thường có **một container hiện tại tại một thời điểm**. Thay đổi container bằng cơ chế được phép tác động tới ngữ cảnh phân giải đối tượng; nó không đồng nghĩa với đổi tên database, đổi instance hay chuyển dữ liệu vật lý giữa các PDB.

## 2. Xác định container hiện tại ngay sau khi đăng nhập

Trong SQL*Plus hoặc SQLcl, hai lệnh nhanh:

~~~sql
SHOW CON_NAME
SHOW CON_ID
~~~

Ví dụ kết quả **minh họa**:

~~~text
CON_NAME
------------------------------
SALES_PDB

CON_ID
------------------------------
3
~~~

`SHOW CON_NAME` và `SHOW CON_ID` là **lệnh của client SQL*Plus/SQLcl**, không phải cú pháp SQL chuẩn để gửi qua JDBC. Với SQL Developer, có thể chạy trong chế độ hỗ trợ script hoặc dùng câu `SELECT` dưới đây; nhiều trình SQL GUI chỉ hỗ trợ một phần lệnh `SHOW`.

### 2.1 Truy vấn dùng được trong phần lớn công cụ SQL

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container,
       SYS_CONTEXT('USERENV', 'CON_ID') AS current_con_id
FROM dual;
~~~

`SYS_CONTEXT('USERENV', ...)` trả về thông tin môi trường **của chính session đang chạy câu SQL**. Trong đó:

- `CON_NAME` là tên container hiện tại (ví dụ `CDB$ROOT` hoặc `SALES_PDB`).
- `CON_ID` là định danh container tương ứng, có thể chuyển sang kiểu số khi cần so sánh.

Điểm mạnh của cách này: **không cần giả định đang đứng trong root** và không phải lấy tên PDB từ URL bằng suy đoán. Bạn có thể chạy nó ngay sau khi đăng nhập bằng tài khoản ứng dụng.

Một truy vấn bổ sung giúp xác định toàn bộ ngữ cảnh phiên:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'CON_ID') AS container_id,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

| Giá trị | Trả lời câu hỏi |
|---|---|
| `SESSION_USER` | Database user đã đăng nhập là ai? |
| `CURRENT_SCHEMA` | Nếu viết `SELECT * FROM orders`, Oracle ưu tiên tìm trong schema nào? |
| `CON_NAME` | Session đang ở root hay PDB nào? |
| `CON_ID` | Mã số container là bao nhiêu trong CDB này? |
| `SERVICE_NAME` | Service name hiện được phiên ghi nhận là gì? |

**Không dùng riêng `CURRENT_SCHEMA` hoặc `SERVICE_NAME` để kết luận container.** Một session có thể dùng schema khác với login user; service phục vụ định tuyến kết nối và không phải lúc nào cũng giống nguyên văn tên PDB. `CON_NAME` và `CON_ID` là bằng chứng trực tiếp hơn về container hiện tại.

### 2.2 Ví dụ đọc kết quả

~~~text
LOGIN_USER   CURRENT_SCHEMA   CONTAINER_NAME   CONTAINER_ID   SERVICE_NAME
-----------  ---------------  ---------------  -------------  --------------
SALES_APP    SALES_APP        SALES_PDB        3              sales_service
~~~

Kết luận đúng: session đang đăng nhập bằng `SALES_APP`, phân giải tên không định danh schema dưới `SALES_APP`, và đang ở container `SALES_PDB`. `CONTAINER_ID = 3` có ý nghĩa trong CDB đang được kết nối. Giá trị `sales_service` là service phiên sử dụng, không phải tên vật lý của datafile, instance hay schema.

## 3. Hiểu CON_ID = 0, 1, 2 và các giá trị khác

`CON_ID` xuất hiện trong nhiều dynamic performance view (`V$...`), data dictionary view đa container (`CDB_...`) và các metadata liên quan. Nó giúp phân biệt **hàng dữ liệu thuộc container nào** trong **database đang quan sát**.

| Giá trị `CON_ID` | Diễn giải thường gặp |
|---|---|
| `0` | Dữ liệu áp dụng toàn CDB, không gắn với một container cụ thể, hoặc xuất hiện trong ngữ cảnh non-CDB; cách hiểu chi tiết phụ thuộc view |
| `1` | `CDB$ROOT` trong CDB |
| `2` | Thông thường `PDB$SEED` |
| `3` trở lên | Các PDB hoặc loại container khác có định danh riêng; phải tra cứu tên thực tế |

**`CON_ID = 0` không phải “PDB số 0”.** Với một số view thống kê, nó biểu thị phạm vi toàn CDB. Nếu cộng một hàng tổng `CON_ID = 0` với các hàng `CON_ID` theo PDB, bạn có thể **đếm trùng**. Tương tự, số `3` không phải quy ước cố định cho tên `SALES_PDB` trên mọi môi trường: thứ tự tạo PDB, clone, xóa/tạo lại hay CDB khác có thể cho mã khác.

Giá trị `CON_ID` là **định danh kỹ thuật theo ngữ cảnh database**, không phải mã doanh nghiệp dùng vĩnh viễn trong API hay trong bảng dữ liệu.

### 3.1 Tra CON_ID sang tên container

Khi có quyền truy vấn view hệ thống, từ phiên quản trị tại `CDB$ROOT`:

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$containers
ORDER BY con_id;
~~~

Ví dụ:

~~~text
CON_ID  NAME          OPEN_MODE   RESTRICTED
------  ------------  ----------  ----------
1       CDB$ROOT      READ WRITE  NO
2       PDB$SEED      READ ONLY   NO
3       SALES_PDB     READ WRITE  NO
4       REPORT_PDB    MOUNTED     NO
~~~

Ở đây `CON_ID = 4` là `REPORT_PDB` trong **chính CDB đang quan sát**, hiện `MOUNTED`. Không suy rằng có thể chạy SQL ứng dụng ở PDB này chỉ vì nó có mặt trong danh sách.

Để chỉ xem các PDB:

~~~sql
SELECT con_id, name, open_mode, restricted
FROM v$pdbs
ORDER BY con_id;
~~~

`V$CONTAINERS` và `V$PDBS` thường yêu cầu quyền quan sát hệ thống; các hàng nhìn thấy phụ thuộc phiên và phạm vi container. Nếu truy vấn đang chạy từ PDB hoặc tài khoản có quyền hạn chế, kết quả có thể **không bao gồm toàn bộ CDB**. Muốn lập bản đồ đầy đủ, dùng tài khoản được phép tại root.

### 3.2 Có thể kiểm tra chính CON_ID của phiên bằng SQL

~~~sql
SELECT TO_NUMBER(SYS_CONTEXT('USERENV', 'CON_ID')) AS my_con_id,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS my_con_name
FROM dual;
~~~

Khi có quyền xem `V$CONTAINERS`, có thể đối chiếu:

~~~sql
SELECT c.con_id, c.name, c.open_mode
FROM v$containers c
WHERE c.con_id = TO_NUMBER(SYS_CONTEXT('USERENV', 'CON_ID'));
~~~

Truy vấn thứ hai chỉ lọc **hàng tương ứng với container hiện tại**, không đại diện cho cả danh sách PDB. Đừng dùng số từ screenshot ở database khác để đối chiếu: cùng một `CON_ID` có thể chỉ container khác ở CDB khác.

### 3.3 Nếu môi trường không dùng CDB

Oracle phiên bản/kiến trúc cũ có thể là non-CDB. Khi có đủ quyền:

~~~sql
SELECT name, cdb, open_mode
FROM v$database;
~~~

Nếu `CDB = NO`, bài toán phân biệt root/PDB và `ALTER SESSION SET CONTAINER` **không áp dụng theo cùng mô hình**. Không bắt buộc mọi công cụ trả về danh sách PDB trong môi trường không hỗ trợ multitenant. Nếu cần học CDB/PDB, phải dùng một database có kiến trúc multitenant.

## 4. Đúng container không đồng nghĩa đúng schema

Xét hai session cùng ở `SALES_PDB`:

~~~text
Session A: SESSION_USER = SALES_APP, CURRENT_SCHEMA = SALES_APP
Session B: SESSION_USER = AUDITOR,   CURRENT_SCHEMA = SALES_APP
CON_NAME của cả hai: SALES_PDB
~~~

Nếu người dùng `AUDITOR` được cấp quyền, session B có thể tra cứu đối tượng của `SALES_APP` bằng tên đầy đủ `SALES_APP.ORDERS` hoặc nhờ thay đổi schema mặc định:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = SALES_APP;
~~~

Sau lệnh này, quan sát:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

`CURRENT_SCHEMA` có thể thay đổi, nhưng `SESSION_USER` và `CON_NAME` **không tự đổi**. Lệnh này cũng **không cấp thêm quyền**: nếu `AUDITOR` không có quyền trên `SALES_APP.ORDERS` thì truy vấn vẫn thất bại. Câu `ALTER SESSION SET CURRENT_SCHEMA` và `ALTER SESSION SET CONTAINER` giải quyết hai vấn đề khác nhau.

Để tránh nhầm lẫn trong bài thực hành nhiều PDB, ưu tiên ghi **schema và container** kèm nhau. Viết `SALES_APP.ORDERS` chỉ định schema trong **container hiện tại**; cú pháp đó không tự nhảy sang `SALES_PDB` nếu session đang ở `REPORT_PDB`.

## 5. Cách thông thường để vào đúng PDB: kết nối qua service

Đối với ứng dụng, tài khoản local user và phần lớn công cụ thường dùng, cách làm rõ ràng là **tạo kết nối đến service của PDB mong muốn**.

~~~mermaid
flowchart TD
    U["SQL*Plus / JDBC / ứng dụng"] -->|"//db-host:1521/sales_service"| L["Listener"]
    L --> S["Service của SALES_PDB"]
    S --> P["Session tại SALES_PDB"]
    P --> V["SYS_CONTEXT: CON_NAME = SALES_PDB"]
~~~

Ví dụ SQL*Plus/SQLcl từ terminal:

~~~sh
sqlplus -L sales_app@//db-host.example:1521/sales_service
~~~

SQL*Plus sẽ yêu cầu mật khẩu khi chưa được cung cấp. Thay host/port/service/user bằng thông tin thực tế; không ghi mật khẩu trực tiếp vào dòng lệnh hoặc lịch sử shell.

Sau khi đăng nhập:

~~~sql
SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV','CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV','CON_ID') AS container_id,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name
FROM dual;
~~~

Nếu `CONTAINER_NAME` trả về `SALES_PDB`, phiên đang ở đúng container đã dự kiến. **Hãy xác nhận bằng truy vấn**, vì tên service không buộc phải giống tên PDB và một hệ thống có thể gắn nhiều service cho cùng PDB.

Ứng dụng Java JDBC Thin thường sử dụng cú pháp URL:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//db-host.example:1521/sales_service
spring.datasource.username=sales_app
~~~

Giữ mật khẩu trong hệ thống cấu hình secret thích hợp. Connection pool thường quản lý các kết nối vật lý theo một cấu hình service cụ thể; ứng dụng phục vụ nhiều PDB nên thiết kế phân tách DataSource/kết nối rõ ràng theo PDB, thay vì vô tình làm thay đổi container của một connection đang được tái sử dụng.

**Cần phân biệt:** listener tiếp nhận yêu cầu kết nối và service định tuyến tới database/PDB; `ALTER SESSION SET CONTAINER` là thao tác đổi phạm vi **trong một phiên đã kết nối**, dùng cho tình huống có thẩm quyền đặc biệt. Kết nối đến service PDB là cách dễ xác minh hơn cho tác vụ thường ngày của ứng dụng.

## 6. Chuyển container bằng ALTER SESSION: ai được dùng?

Oracle hỗ trợ lệnh:

~~~sql
ALTER SESSION SET CONTAINER = SALES_PDB;
~~~

Đây là **thao tác có điều kiện**, không phải khả năng mặc định của mọi database user. Trong kiến trúc CDB, việc chuyển container giữa root/PDB thông thường đòi hỏi một **common user** (ví dụ một tài khoản quản trị chung được cho phép) có quyền `SET CONTAINER` phù hợp với đích. Quyền quản trị và kiểu tài khoản cụ thể còn phụ thuộc cấu hình và chính sách bảo mật của database.

**Local user** được tạo riêng trong một PDB để ứng dụng sử dụng không thể mặc nhiên chuyển sang PDB khác bằng `ALTER SESSION SET CONTAINER`. Ngay cả khi lệnh SQL có cú pháp đúng, Oracle vẫn kiểm tra quyền, trạng thái PDB và điều kiện phiên.

### 6.1 Phân biệt local user với common user

| Loại tài khoản | Phạm vi | Cách làm việc với PDB khác |
|---|---|---|
| **Local user** | Thuộc một PDB cụ thể, ví dụ `SALES_APP` | Đăng nhập qua service của PDB nơi user tồn tại; dùng tài khoản/ủy quyền thích hợp ở PDB khác |
| **Common user** | Có định danh chung qua các container thuộc phạm vi của common user, ví dụ tài khoản quản trị CDB | Có thể chuyển container **nếu có quyền `SET CONTAINER` trên đích và các điều kiện khác thỏa mãn** |
| **Application common user** | Phạm vi application container/application PDB, nếu triển khai kiến trúc này | Quyền và đường chuyển container phải xét theo application container, không coi như common user toàn CDB |

Trong các CDB thông thường, tên common user do người quản trị tạo thường có tiền tố `C##` theo cấu hình mặc định; **tiền tố trong tên không tự chứng minh tài khoản đang sở hữu quyền cần thiết**. Đừng dựa vào việc username bắt đầu bằng `C##` để bỏ qua kiểm tra quyền.

### 6.2 Quy trình chuyển container minh họa cho common user đã được cấp quyền

Giả sử phiên quản trị bắt đầu ở `CDB$ROOT`, tài khoản `C##OBSERVER` đã được cấp `SET CONTAINER` phù hợp và PDB `SALES_PDB` đang được mở:

~~~sql
-- 1. Xác nhận phạm vi ban đầu
SHOW CON_NAME
SHOW CON_ID

-- 2. Tìm đúng tên và trạng thái PDB đích
SELECT con_id, name, open_mode, restricted
FROM v$pdbs
WHERE name = 'SALES_PDB';

-- 3. Chuyển sang PDB đã xác nhận
ALTER SESSION SET CONTAINER = SALES_PDB;

-- 4. Xác minh lại ngay sau khi chuyển
SHOW CON_NAME
SHOW CON_ID

SELECT SYS_CONTEXT('USERENV','CON_NAME') AS current_container,
       SYS_CONTEXT('USERENV','CON_ID') AS current_con_id
FROM dual;
~~~

Nếu kết quả trả về `SALES_PDB` và đúng CON_ID từ danh sách, có thể nói **session đã chuyển sang đúng PDB**. Không nên chuyển tiếp sang các câu DDL/DML trước khi xác minh này.

Khi cần quay lại root, và tài khoản có quyền tương ứng:

~~~sql
ALTER SESSION SET CONTAINER = CDB$ROOT;

SELECT SYS_CONTEXT('USERENV','CON_NAME') AS current_container,
       SYS_CONTEXT('USERENV','CON_ID') AS current_con_id
FROM dual;
~~~

Kết quả dự kiến là `CDB$ROOT` và `1`. Với các công cụ không hỗ trợ `SHOW CON_NAME`, các câu `SYS_CONTEXT` vẫn là cách xác nhận. Chỉ thực hiện chuỗi chuyển container này trong phiên riêng đã được ủy quyền, trên môi trường được phép quản trị.

### 6.3 Điều kiện trước khi chuyển

Trước `ALTER SESSION SET CONTAINER`, người vận hành cần xác định:

1. **Môi trường thực sự là CDB.** Với non-CDB, không áp dụng workflow này.
2. **Tài khoản và quyền hợp lệ.** Common user phải có quyền `SET CONTAINER` đúng phạm vi; local user không thể tự nâng cấp thành common user bằng cách chạy câu lệnh.
3. **Container đích đúng tên và có trạng thái phục vụ tác vụ dự định.** Ví dụ, PDB muốn truy cập dữ liệu ghi thường cần `READ WRITE`; `PDB$SEED` thường chỉ đọc và không phải đích cho schema ứng dụng.
4. **Phiên không đang ở giữa một giao dịch cần giữ lại.** Không cố đổi container khi transaction còn hoạt động; cần hoàn tất `COMMIT` hoặc `ROLLBACK` có chủ đích trong phạm vi hiện tại theo quy trình.
5. **Không có trạng thái phiên cần được giữ nguyên một cách mù quáng.** Sau khi chuyển, cần kiểm tra lại container/schema/quyền và những thiết lập session quan trọng trước khi tiếp tục.

Một lệnh `ALTER SESSION SET CONTAINER` **không tự sao chép bảng**, **không di chuyển dữ liệu giữa hai PDB**, **không biến local user thành common user** và **không cấp quyền đọc bảng của PDB đích**. Nó chỉ là cơ chế thay đổi phạm vi container hiện tại đối với phiên đủ điều kiện.

### 6.4 Vì sao không nên dùng ALTER SESSION tùy tiện trong connection pool?

Giả sử ứng dụng lấy một JDBC connection từ pool, chuyển nó sang `REPORT_PDB`, trả lại pool mà không đảm bảo khôi phục đúng trạng thái, rồi request sau sử dụng lại connection và nghĩ mình đang ở `SALES_PDB`. Các câu SQL sau có thể đọc nhầm dữ liệu, báo thiếu bảng, hoặc thực hiện DML ở phạm vi sai.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant P as Connection pool
    participant O as Oracle session
    participant B as Request B
    A->>P: Mượn connection
    P->>O: Session ban đầu ở SALES_PDB
    A->>O: ALTER SESSION SET CONTAINER = REPORT_PDB
    A->>P: Trả connection chưa xác minh trạng thái
    B->>P: Mượn lại connection
    B->>O: SELECT từ schema mặc định
    O-->>B: Có thể truy cập nhầm REPORT_PDB
~~~

Vì vậy, với ứng dụng đa PDB, cách tổ chức connection pool riêng theo service/đích và xác nhận container khi khởi tạo kết nối thường rõ ràng, ít lỗi hơn. Nếu hệ thống có nhu cầu chuyển container động được thiết kế chuyên biệt, phải kiểm soát ranh giới giao dịch và trạng thái phiên; không làm như một thao tác phụ trong một repository method thông thường.

## 7. Phân biệt phạm vi của truy vấn trong root và trong PDB

Một common user kết nối vào `CDB$ROOT` **không đồng nghĩa mỗi câu `SELECT` thông thường tự chạy trong tất cả PDB**. Tùy loại view, Oracle cung cấp những cách quan sát khác nhau:

- **Bảng/schema ứng dụng thông thường:** câu `SELECT` nhìn vào đối tượng trong **container hiện tại** theo quyền/schema; không tự duyệt mọi PDB.
- **`DBA_*` view:** phản ánh data dictionary trong phạm vi phiên/container, tùy quyền.
- **`CDB_*` view:** có thể cung cấp dữ liệu của nhiều container từ root khi tài khoản có quyền và cấu hình container-data phù hợp; cột `CON_ID` giúp phân biệt nguồn.
- **`V$*`/`GV$*` view:** phản ánh trạng thái runtime; ý nghĩa cột `CON_ID` và tập hàng nhìn thấy phụ thuộc từng view, instance, phiên và quyền.

Ví dụ với quyền phù hợp, từ root:

~~~sql
SELECT con_id, username, common
FROM cdb_users
WHERE username IN ('SALES_APP', 'REPORT_APP')
ORDER BY con_id, username;
~~~

Nếu `CDB_USERS` cho hai hàng mang `CON_ID` khác nhau, đó là metadata của user trong các container khác nhau. **Không** lấy kết quả như bằng chứng rằng session root đang đồng thời “ở cả hai PDB” hoặc có quyền truy vấn mọi bảng của hai user. Khả năng nhìn thấy từng hàng còn phụ thuộc quyền của tài khoản/common user và cấu hình hiển thị dữ liệu container.

### 7.1 Khi cần đọc từ đúng schema ở đúng PDB

Giả sử muốn đếm đơn hàng trong `SALES_PDB`. Hai cách rõ ràng:

**Cách thông thường cho ứng dụng:** đăng nhập một session đến service của `SALES_PDB` bằng user được cấp quyền rồi chạy:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS con_name
FROM dual;

SELECT COUNT(*) AS order_count
FROM sales_app.orders;
~~~

**Cách dành cho common user có thẩm quyền:** từ root, xác định PDB và trạng thái, chuyển đúng container, xác nhận `CON_NAME`, rồi chỉ truy vấn bảng khi user hiện tại có quyền trên đối tượng đó. Việc chuyển container và quyền đọc bảng là **hai kiểm tra riêng biệt**.

Nếu dùng tên bảng ngắn `orders`, Oracle còn phụ thuộc `CURRENT_SCHEMA`. Để tái lập tình huống chính xác, ghi lại cả `SESSION_USER`, `CURRENT_SCHEMA` và `CON_NAME`.

### 7.2 CON_ID trên V$SESSION thể hiện điều gì?

Tài khoản được phép quan sát có thể truy vấn:

~~~sql
SELECT sid, serial#, username, con_id, service_name, status
FROM v$session
WHERE type = 'USER'
ORDER BY con_id, sid;
~~~

`V$SESSION.CON_ID` gắn một session với container theo phạm vi view tại thời điểm quan sát; `SERVICE_NAME` cho biết dịch vụ phiên sử dụng. Một truy vấn tại root có quyền rộng có thể nhìn thấy các session ở nhiều container; tài khoản PDB thường chỉ quan sát được phần được phép. **Đừng nhầm `CON_ID` của các hàng session khác với `CON_ID` của chính phiên đang chạy truy vấn**. Để xác nhận phiên của mình, `SYS_CONTEXT('USERENV','CON_ID')` là cách trực tiếp.

## 8. Những tình huống dễ nhầm khi quản lý container

| Quan sát hoặc hành động | Kết luận đúng / hướng xử lý |
|---|---|
| `SHOW CON_NAME` trả về `CDB$ROOT` | Session đang ở root; chưa ở PDB ứng dụng |
| `SHOW PDBS` cho thấy `SALES_PDB READ WRITE` | PDB sẵn sàng về chế độ mở; cần tiếp tục kiểm tra service, user và quyền |
| `SHOW PDBS` cho thấy `PDB$SEED READ ONLY` | Thường là trạng thái đúng của PDB mẫu; không dùng seed cho dữ liệu nghiệp vụ |
| `V$CONTAINERS` có `CON_ID = 0` | Cần kiểm tra ý nghĩa view; không suy đó là PDB tên “0” |
| URL JDBC dùng `sales_service` | Đó là tên service, không phải bằng chứng tuyệt đối về container; xác nhận `CON_NAME` sau đăng nhập |
| `CURRENT_SCHEMA` đổi từ `AUDITOR` sang `SALES_APP` | Chỉ đổi ngữ cảnh phân giải object; `CON_NAME` không tự đổi |
| `ALTER SESSION SET CONTAINER` báo thiếu quyền | Xem loại user và quyền `SET CONTAINER`; không cấp rộng quyền vì lỗi câu lệnh |
| Root thấy metadata user của PDB qua `CDB_USERS` | Có quyền xem một phần metadata; chưa chắc được đọc bảng ứng dụng trong PDB |
| Hai CDB cùng có `CON_ID = 3` | Không bảo đảm đó là cùng một PDB; cần đối chiếu tên và database |
| Kết nối SQL thành công nhưng `ORA-00942` khi gọi bảng | Kiểm tra PDB, schema, tên đối tượng và quyền trước khi kết luận bảng không tồn tại |
| Kết nối tới service báo lỗi trước khi vào session | Kiểm tra listener/service/PDB mở; khi chưa kết nối được thì chưa thể chạy `SHOW CON_NAME` trong session đó |

### 8.1 Thông báo lỗi liên quan container

**`ORA-01031: insufficient privileges`** có thể xảy ra khi thao tác chuyển container không được cấp quyền phù hợp. **`ORA-65011`** liên quan PDB được nêu không tồn tại theo ngữ cảnh quản lý đang dùng; trước tiên truy vấn lại tên PDB và CDB kết nối. **`ORA-01109: database not open`** có thể xuất hiện khi cố truy vấn đối tượng trong database/PDB chưa mở theo yêu cầu. Các mã lỗi này là dấu hiệu để khoanh vùng, không phải một phép chẩn đoán trọn vẹn: cần đối chiếu trạng thái thực tế, quyền và câu SQL đầy đủ.

Nếu phiên đang có transaction hoặc đang dùng một cơ chế session đặc thù, Oracle có thể từ chối việc chuyển; không nên giải quyết bằng cách tự ý `COMMIT` một transaction không rõ nội dung. Hoàn tất giao dịch đúng ý định nghiệp vụ trước, rồi thực hiện chuyển ở một phiên quản trị an toàn.

## 9. Tập lệnh thực hành theo hai vai trò

### 9.1 Người phát triển ứng dụng: xác minh kết nối PDB, không cần quyền quản trị

Trong terminal:

~~~sh
sqlplus -L sales_app@//db-host.example:1521/sales_service
~~~

Trong session SQL:

~~~sql
-- Quan sát tài khoản, schema, container và service
SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV','CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV','CON_ID') AS container_id,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name
FROM dual;

-- Chạy truy vấn chỉ đọc thuộc schema đã được cấp quyền
SELECT COUNT(*) AS order_count
FROM sales_app.orders;
~~~

`sales_app.orders` chỉ là một bảng minh họa; nếu schema thực tế không có bảng này, thay bằng bảng thực hành được cấp quyền. Nếu câu `SYS_CONTEXT` cho container khác kỳ vọng, kiểm tra chuỗi kết nối/service trước khi chạy SQL cập nhật.

Nếu cần làm việc với `REPORT_PDB` bằng một local user khác, **mở kết nối mới đến service của REPORT_PDB** bằng thông tin tài khoản phù hợp. Không cố dùng lệnh chuyển container như một cách lách quyền.

### 9.2 Quản trị viên/common user có quyền: quan sát và đổi phạm vi có kiểm soát

Ở `CDB$ROOT`:

~~~sql
-- Bước 1: Kiểm tra là CDB và tên database
SELECT name, cdb, open_mode
FROM v$database;

-- Bước 2: Kiểm tra container của chính phiên
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS before_name,
       SYS_CONTEXT('USERENV','CON_ID') AS before_id
FROM dual;

-- Bước 3: Xác định đích và chế độ mở
SELECT con_id, name, open_mode, restricted
FROM v$pdbs
WHERE name = 'SALES_PDB';

-- Bước 4: Chuyển chỉ khi account đã được cấp quyền và phiên sẵn sàng
ALTER SESSION SET CONTAINER = SALES_PDB;

-- Bước 5: Xác minh đích ngay lập tức
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS after_name,
       SYS_CONTEXT('USERENV','CON_ID') AS after_id,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Đây là chuỗi **có thao tác đổi phạm vi session** ở bước 4; các bước còn lại chỉ đọc. Không đưa chuỗi quản trị này vào một script production tự động không có kiểm soát quyền, đích và ranh giới transaction. Khi thực hành xong, nếu tiếp tục dùng phiên quản trị cho công việc ở root thì chuyển về root với quyền phù hợp và **xác nhận lại**:

~~~sql
ALTER SESSION SET CONTAINER = CDB$ROOT;

SELECT SYS_CONTEXT('USERENV','CON_NAME') AS final_container
FROM dual;
~~~

## 10. Sơ đồ quyết định: kết nối mới hay chuyển container?

~~~mermaid
flowchart TD
    A["Cần thao tác ở một PDB"] --> B{"Đang có session ở đúng PDB?"}
    B -->|Có| C["Kiểm tra schema và quyền rồi chạy SQL"]
    B -->|Không| D{"Là common user có SET CONTAINER đúng phạm vi?"}
    D -->|Không| E["Đăng nhập qua service của PDB với tài khoản phù hợp"]
    D -->|Có| F{"Cần chuyển trong cùng session quản trị?"}
    F -->|Không| E
    F -->|Có| G["Kiểm tra transaction, tên PDB, OPEN_MODE"]
    G --> H["ALTER SESSION SET CONTAINER = PDB"]
    H --> I["Xác minh CON_NAME, CON_ID, CURRENT_SCHEMA"]
    E --> I
    I --> C
~~~

Với người học và với hầu hết ứng dụng, đường đi phổ biến là **đăng nhập bằng service của PDB đích rồi xác nhận container**. `ALTER SESSION SET CONTAINER` chủ yếu phục vụ công việc được ủy quyền của common user, với các điều kiện nghiêm ngặt về quyền và trạng thái session.

## 11. Bài tập tự kiểm tra

**Bài 1 — Nhận diện container.** Mở một kết nối SQL vào PDB thực hành, chạy `SHOW CON_NAME` (nếu công cụ hỗ trợ) và truy vấn `SYS_CONTEXT`. Ghi `SESSION_USER`, `CURRENT_SCHEMA`, `CON_NAME`, `CON_ID` và `SERVICE_NAME`. Giải thích vì sao `SERVICE_NAME` không nhất thiết giống `CON_NAME`.

**Bài 2 — Vẽ bản đồ CON_ID.** Với tài khoản được phép ở CDB root, chạy `SELECT CON_ID, NAME, OPEN_MODE FROM V$CONTAINERS ORDER BY CON_ID`. Đánh dấu root, seed và từng PDB. Giải thích vì sao không thể mang số CON_ID từ CDB A sang CDB B để suy ra tên PDB.

**Bài 3 — Phạm vi user và schema.** Trong PDB thực hành, xem `SESSION_USER` và `CURRENT_SCHEMA` trước/sau khi thay đổi `CURRENT_SCHEMA` tới schema mà bạn được phép tham chiếu. Xác nhận `CON_NAME` không đổi và giải thích vì sao một schema khác vẫn yêu cầu quyền truy cập đối tượng.

**Bài 4 — Chuyển container có thẩm quyền.** Nếu được quản trị viên cấp common user với `SET CONTAINER` và môi trường thử nghiệm được phép, chuyển từ root sang một PDB đã mở, đọc lại `CON_NAME` và `CON_ID` rồi quay lại root. Nếu không có quyền, **không cần cố thử lệnh chuyển**: mô tả vì sao local user nên dùng kết nối mới theo service.

**Bài 5 — Đọc tình huống.** Người dùng báo “Tôi vào được Oracle nhưng không thấy bảng `ORDERS`”. Hãy trình bày thứ tự kiểm tra: đã kết nối service nào, `CON_NAME` là gì, `CURRENT_SCHEMA` là gì, bảng thuộc schema nào, tài khoản có quyền hay không. Nêu tại sao tạo lại bảng ngay lập tức là phản ứng không phù hợp.

**Bài 6 — Phạm vi view.** Từ root, một truy vấn `CDB_USERS` trả về user ở nhiều CON_ID. Giải thích sự khác nhau giữa “phiên có thể xem metadata từ nhiều container” và “phiên đang thực thi một câu `SELECT` nghiệp vụ trong một container cụ thể”.

## 12. Ghi nhớ để thao tác đúng phạm vi

| Điều cần biết | Câu lệnh hoặc nguyên tắc |
|---|---|
| Session ở đâu? | `SHOW CON_NAME` / `SYS_CONTEXT('USERENV','CON_NAME')` |
| CON_ID hiện tại là gì? | `SHOW CON_ID` / `SYS_CONTEXT('USERENV','CON_ID')` |
| CON_ID ứng với PDB nào? | Từ root, tra `V$CONTAINERS` hoặc `V$PDBS` khi có quyền |
| Database có CDB không? | `SELECT CDB FROM V$DATABASE` |
| PDB có mở để ghi không? | Đối chiếu `OPEN_MODE`; thường cần `READ WRITE` cho DML |
| User và schema khác gì? | `SESSION_USER` là user; `CURRENT_SCHEMA` là nơi phân giải tên đối tượng |
| Ứng dụng vào PDB nào? | Kết nối qua **service của PDB**, sau đó xác nhận `CON_NAME` |
| Ai được dùng `ALTER SESSION SET CONTAINER`? | Common user có quyền `SET CONTAINER` hợp lệ, session/đích đáp ứng điều kiện |
| Đổi container có làm tăng quyền không? | **Không**: quyền đối tượng và quy tắc bảo mật vẫn được kiểm tra |
| Có thể dùng CON_ID làm ID toàn hệ thống không? | **Không**: định danh này cần ngữ cảnh CDB và view |

Quy tắc thực hành quan trọng nhất là **xác định container trước, thao tác sau**. Trong Oracle multitenant, đúng database server nhưng sai PDB vẫn có thể dẫn đến sai dữ liệu, sai quyền hoặc sai vị trí tạo đối tượng. Kiểm tra `CON_NAME`, `CON_ID`, `CURRENT_SCHEMA` và service của phiên giúp đặt mỗi câu SQL vào đúng phạm vi; khi cần chuyển container, hãy dùng đúng tư cách tài khoản, đúng quyền và xác nhận lại ngữ cảnh ngay sau thao tác.
