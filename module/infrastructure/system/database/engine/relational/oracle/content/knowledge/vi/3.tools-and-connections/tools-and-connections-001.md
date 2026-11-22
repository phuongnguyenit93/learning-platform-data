# Thực hiện câu lệnh và script bằng SQL*Plus, SQLcl và SQL Developer

Khi làm việc với **Oracle Database**, lập trình viên và quản trị viên không chỉ viết câu lệnh SQL. Họ còn phải biết **đưa câu lệnh đến đúng database/schema, thực thi một hoặc nhiều câu lệnh theo đúng thứ tự, quan sát kết quả, quản lý transaction và lưu lại log** để có thể chạy lại trong môi trường khác.

Oracle có ba công cụ quen thuộc phục vụ các nhu cầu này:

- **SQL*Plus**: giao diện dòng lệnh truyền thống của Oracle, phổ biến trong script quản trị, triển khai và môi trường máy chủ.
- **SQLcl (SQL Developer Command Line)**: công cụ dòng lệnh hiện đại hơn, tương thích với phần lớn lệnh script SQL*Plus thông dụng và có thêm tiện ích hiển thị/xuất dữ liệu.
- **Oracle SQL Developer**: ứng dụng giao diện đồ họa để tạo kết nối, soạn SQL, xem kết quả dạng bảng và chạy script từ SQL Worksheet.

Ba công cụ gửi SQL/PLSQL cho Oracle Database xử lý, nhưng **cách gửi lệnh, cách hiển thị và bộ lệnh phía client không hoàn toàn giống nhau**. Bài học hướng dẫn trực tiếp các thao tác đó bằng ví dụ có thể tự thực hành trên một schema được phép tạo bảng.

## 1. Phân biệt SQL, PL/SQL và lệnh của công cụ

Trước khi mở bất kỳ công cụ nào, hãy phân biệt ba lớp thao tác:

| Lớp | Ví dụ | Nơi thực thi |
|---|---|---|
| **SQL** | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE` | Oracle Database nhận, phân tích cú pháp, tối ưu và thực thi |
| **PL/SQL** | Khối `DECLARE ... BEGIN ... END;`, procedure, function | Bộ máy PL/SQL của Oracle Database |
| **Lệnh client/script** | `SET`, `SPOOL`, `PROMPT`, `DESCRIBE`, `@`, `CONNECT`, `VARIABLE` | SQL*Plus, SQLcl hoặc script runner của SQL Developer xử lý trước/tách biệt với SQL gửi lên database |

Ví dụ:

```sql
-- SQL: database thực thi, trả về một hàng.
SELECT 'Hello Oracle' AS message FROM dual;

-- Lệnh phía công cụ: in thông báo lên terminal/Script Output.
PROMPT Bat dau thuc thi script
```

`PROMPT` không phải câu lệnh SQL chuẩn gửi cho SQL engine. Nếu gửi chuỗi `PROMPT ...` qua JDBC bằng `Statement.execute(...)`, ứng dụng sẽ không được hỗ trợ như khi chạy lệnh đó trong SQL*Plus/SQLcl. Ngược lại, `SELECT` chạy trong các công cụ này vẫn do cùng Oracle Database thực thi, nên kết quả dữ liệu phụ thuộc SQL, quyền truy cập và trạng thái database.

Sơ đồ luồng xử lý:

```text
Người dùng / file .sql
        |
        v
SQL*Plus / SQLcl / SQL Developer
        |  xử lý CONNECT, SET, PROMPT, SPOOL, @...
        |  gửi SQL hoặc PL/SQL
        v
Oracle Database (session, schema, transaction)
        |
        |  rows / lỗi ORA- / thông tin thực thi
        v
Terminal / Results Grid / Script Output / log file
```

**Điểm cốt lõi:** file có đuôi `.sql` có thể chứa cả SQL, PL/SQL và lệnh script của công cụ. Không phải mọi đoạn trong file đều chạy trực tiếp qua JDBC hay mọi SQL client khác.

## 2. Chuẩn bị môi trường và thông tin kết nối

Để thực hành, bạn cần:

1. Một Oracle Database đang hoạt động và có thể truy cập từ máy chạy công cụ.
2. Tài khoản Oracle với username/password; nếu chạy ví dụ tạo bảng, tài khoản cần quyền tạo bảng và quota trên tablespace thích hợp.
3. Ít nhất một trong ba công cụ đã được cài đặt/cấu hình tương thích với database.
4. Thông tin **host**, **port** và **service name** (hoặc một **TNS alias** được cấu hình sẵn).

Ví dụ giả định dùng cho phần còn lại:

| Thuộc tính | Giá trị minh họa | Giải thích |
|---|---|---|
| Host | `localhost` | Oracle chạy trên máy cục bộ; thay bằng hostname/IP thực tế khi cần |
| Port | `1521` | Cổng listener thông dụng, nhưng hệ thống có thể dùng cổng khác |
| Service name | `freepdb1` | Ví dụ tên dịch vụ PDB; không phải mọi hệ Oracle đều dùng tên này |
| Username | `lab_user` | Tài khoản thực hành do môi trường cấp |
| Password | Nhập khi công cụ yêu cầu | Không đặt mật khẩu vào script hoặc dòng lệnh được lưu trong lịch sử shell |

Với kiểu kết nối **Easy Connect**, chuỗi thường có dạng:

```text
//hostname:port/service_name
```

Ví dụ `//localhost:1521/freepdb1`. Tên *service* được listener và cấu hình database công bố, không thể tự suy từ tên máy. Trong môi trường multitenant, cần kết nối đúng **PDB** dành cho ứng dụng, không tùy tiện dùng container gốc hoặc tài khoản quản trị.

Một câu lệnh xác minh sau kết nối:

```sql
SELECT USER AS connected_user,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
```

Giá trị `USER` chỉ ra schema/session user hiện tại; các giá trị môi trường giúp tránh chạy script trên nhầm cơ sở dữ liệu hoặc PDB. `CURRENT_SCHEMA` có thể được đổi riêng bằng `ALTER SESSION SET CURRENT_SCHEMA = ...`, vì vậy user đã đăng nhập và schema đang dùng để phân giải tên đối tượng không nhất thiết luôn là một.

## 3. SQL*Plus: thao tác trực tiếp trong terminal

**SQL*Plus** là lựa chọn gọn nhẹ khi cần làm việc bằng terminal, truy cập máy chủ qua SSH, chạy script tự động hoặc bảo trì một hệ thống sử dụng các file `.sql` truyền thống.

### 3.1 Mở chương trình và kết nối

Tại terminal có thể gọi được executable `sqlplus`:

```text
sqlplus /nolog
```

Tham số `/nolog` mở SQL*Plus **mà chưa đăng nhập database**. Tại dấu nhắc `SQL>`:

```sql
CONNECT lab_user@//localhost:1521/freepdb1
```

Công cụ yêu cầu nhập mật khẩu khi cần. Nếu đăng nhập thành công, thử:

```sql
SHOW USER
SELECT 1 + 2 AS result FROM dual;
```

Khi hoàn tất:

```text
EXIT
```

SQL*Plus còn hỗ trợ alias từ `tnsnames.ora` hoặc cấu hình Oracle Net thích hợp, ví dụ `CONNECT lab_user@MYDB`; tên `MYDB` phải thực sự tồn tại trong cấu hình của máy client. Để tránh lộ thông tin xác thực, không đưa mật khẩu trực tiếp vào `CONNECT user/password@...` trong tài liệu, terminal history, CI logs hay file version control.

### 3.2 Điều chỉnh cách hiển thị kết quả

Một số lệnh thường dùng:

```sql
SET LINESIZE 160
SET PAGESIZE 100
SET FEEDBACK ON
SET TIMING ON
SET SERVEROUTPUT ON

SELECT SYSDATE AS current_date FROM dual;
```

| Lệnh | Công dụng |
|---|---|
| `SET LINESIZE n` | Điều chỉnh chiều rộng một dòng kết quả dạng văn bản |
| `SET PAGESIZE n` | Điều chỉnh số dòng trên trang và cách xuất header/định dạng trang |
| `SET FEEDBACK ON` | Hiển thị thông báo như số dòng được chọn hoặc số dòng chịu tác động |
| `SET TIMING ON` | Hiển thị thời gian thực thi được công cụ đo |
| `SET SERVEROUTPUT ON` | Hiển thị dữ liệu do `DBMS_OUTPUT.PUT_LINE` ghi trong PL/SQL |
| `DESCRIBE object_name` hoặc `DESC object_name` | Xem cấu trúc cột/tham số của đối tượng được hỗ trợ |
| `SHOW USER` | Xem Oracle user đang kết nối |
| `SPOOL file_name` / `SPOOL OFF` | Bắt đầu/kết thúc ghi kết quả ra file trên máy client |

Các thiết lập `SET` là **thiết lập của client/session làm việc với công cụ** (và có thể kích hoạt hành vi thu thập hiển thị), không nên nhầm với SQL `ALTER SESSION` gửi trực tiếp lên database.

## 4. SQLcl: dòng lệnh tương thích SQL*Plus với nhiều tiện ích hơn

**SQLcl** là công cụ dòng lệnh trong bộ công cụ Oracle SQL Developer. Tùy bản cài đặt, executable thường có tên `sql` (trên Windows là `sql.exe`).

Mở SQLcl mà chưa kết nối:

```text
sql /nolog
```

Sau đó đăng nhập giống kiểu làm việc với SQL*Plus:

```sql
CONNECT lab_user@//localhost:1521/freepdb1
SHOW USER
SELECT 'SQLcl connected' AS message FROM dual;
```

Các lệnh `@`, `@@`, `START`, `SPOOL`, `SET SERVEROUTPUT ON`, `VARIABLE` và nhiều lệnh script SQL*Plus quen thuộc cũng có mặt trong SQLcl. Tuy nhiên SQLcl và SQL*Plus là hai client khác nhau; một số lệnh nâng cao hoặc chế độ định dạng chỉ xuất hiện trong SQLcl, và mức hỗ trợ có thể thay đổi theo phiên bản.

Một tiện ích dễ thấy là xuất kết quả dưới dạng CSV:

```sql
SET SQLFORMAT CSV
SELECT 101 AS order_id, 'PAID' AS status FROM dual;
SET SQLFORMAT DEFAULT
```

`SET SQLFORMAT CSV` là tính năng của SQLcl. Không nên chép dòng này sang SQL*Plus rồi kỳ vọng nó hoạt động giống nhau. Với dữ liệu thực tế, hãy chú ý escaping, ký tự phân cách, encoding và NLS khi xuất file để đưa vào hệ thống khác.

SQLcl phù hợp khi muốn giữ cách viết script tương tự SQL*Plus nhưng cần môi trường terminal hiện đại, các tiện ích định dạng kết quả và quy trình CLI. Không cần chuyển tất cả script hiện có chỉ vì đổi client; hãy xác định lệnh nào là SQL chuẩn, lệnh nào thuộc tập lệnh script của công cụ.

## 5. Oracle SQL Developer: thực thi qua SQL Worksheet

**SQL Developer** cung cấp giao diện đồ họa để kết nối, viết câu lệnh có hỗ trợ gợi ý cú pháp, xem cấu trúc bảng và làm việc với kết quả dạng lưới.

### 5.1 Tạo kết nối

Trong cửa sổ **Connections**, tạo kết nối mới và nhập các trường minh họa:

| Trường trong giao diện | Giá trị ví dụ |
|---|---|
| Connection Name | `Local Lab` (tên để người dùng nhận biết) |
| Username | `lab_user` |
| Password | Nhập theo tài khoản thực tế |
| Connection Type | `Basic` hoặc kiểu phù hợp với môi trường |
| Hostname | `localhost` |
| Port | `1521` |
| Service name | `freepdb1` |

Bấm **Test** để kiểm tra kết nối rồi **Connect**. Chỉ chọn lưu mật khẩu khi môi trường và quy định bảo mật của bạn cho phép. Nếu dịch vụ doanh nghiệp sử dụng wallet/TNS/SSL, thực hiện theo cấu hình kết nối do hệ thống cung cấp thay vì ép dùng Basic connection.

Mở **SQL Worksheet** của kết nối vừa tạo, nhập:

```sql
SELECT USER AS connected_user FROM dual;
```

### 5.2 Hai cách chạy dễ nhầm: Run Statement và Run Script

Trong SQL Worksheet, hai thao tác phổ biến là:

| Chức năng | Phím tắt mặc định thông dụng | Mục đích | Cửa sổ kết quả thường gặp |
|---|---|---|---|
| **Run Statement** | `F9` | Chạy câu lệnh tại con trỏ hoặc phần được chọn | **Query Result / Results** dạng bảng khi là `SELECT` |
| **Run Script** | `F5` | Chạy tuần tự nội dung worksheet/script theo chế độ script | **Script Output** dạng văn bản, gồm thông báo/lệnh hỗ trợ |

Phím tắt có thể được chỉnh trong phần Preferences/Key Bindings. Tên thao tác và biểu tượng trên thanh công cụ là cách nhận biết chắc chắn hơn nếu hệ thống đã đổi shortcut.

Ví dụ nhập hai câu:

```sql
SELECT 'first' AS stage FROM dual;
SELECT 'second' AS stage FROM dual;
```

- Đặt con trỏ vào câu đầu và chọn **Run Statement**: thường chạy câu đang được chọn/xác định tại con trỏ; kết quả hiện dạng lưới thuận tiện lọc, sắp xếp, xem nhiều cột.
- Chọn **Run Script**: nội dung chạy theo cách đọc script, hai tập kết quả và thông báo xuất vào **Script Output**.

**Khi học hoặc chạy file chứa `PROMPT`, `SET`, `@`, PL/SQL và nhiều câu SQL nối tiếp, hãy ưu tiên `Run Script` (F5)**. `Run Statement` tối ưu cho việc thử nhanh một câu SQL/PLSQL và quan sát kết quả; nó không thay thế đầy đủ trình thông dịch lệnh script.

### 5.3 Xem `DBMS_OUTPUT` trong SQL Developer

Khối PL/SQL có thể ghi thông điệp bằng:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Xin chao tu Oracle');
END;
/
```

Với **Run Script (F5)**, thêm `SET SERVEROUTPUT ON` trước khối để yêu cầu script runner hiển thị `DBMS_OUTPUT`:

```sql
SET SERVEROUTPUT ON
BEGIN
    DBMS_OUTPUT.PUT_LINE('Da thuc thi PL/SQL');
END;
/
```

Nếu dùng **Run Statement (F9)**, có thể mở panel **DBMS Output**, bật thu thập output cho đúng connection, rồi thực hiện PL/SQL. Chỉ gọi `DBMS_OUTPUT.PUT_LINE` không có nghĩa chữ tự động xuất ra bảng **Query Result**. Trong Oracle, output được lưu trong bộ đệm và được client lấy/hiển thị khi được cấu hình thích hợp; nó không phải cơ chế log streaming theo thời gian thực.

## 6. Dấu chấm phẩy `;`, dấu gạch chéo `/` và vùng đệm câu lệnh

Đây là một trong những điểm dễ gây lỗi khi chạy SQL từ file.

### 6.1 SQL thường kết thúc bằng `;`

```sql
SELECT 10 * 3 AS total FROM dual;
```

Trong SQL*Plus và SQLcl, dấu `;` ở cuối câu SQL thường báo cho client kết thúc và gửi câu SQL để thực thi. Bản thân dấu phân cách này không phải thành phần của cú pháp SQL được chuyển nguyên vẹn như một phép toán trong cơ sở dữ liệu.

### 6.2 Khối PL/SQL: `;` bên trong và `/` ở dòng riêng

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from PL/SQL');
END;
/
```

`END;` kết thúc khối PL/SQL về mặt cú pháp, còn dấu `/` **đứng một mình ở dòng mới** yêu cầu công cụ thực thi phần PL/SQL đã gom trong bộ đệm. Điều này đặc biệt quan trọng với script tạo procedure, function, package, trigger hoặc khối PL/SQL vô danh. Không thêm dấu `;` sau `/`.

Ví dụ tạo procedure:

```sql
CREATE OR REPLACE PROCEDURE lab_say_hello AS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from stored procedure');
END;
/

SET SERVEROUTPUT ON
BEGIN
    lab_say_hello;
END;
/
```

Tạo procedure bằng DDL có thể thành công về việc tạo đối tượng nhưng vẫn báo lỗi biên dịch; sử dụng `SHOW ERRORS` trong client hỗ trợ hoặc xem trạng thái/lỗi ở SQL Developer để chẩn đoán.

### 6.3 Tránh chạy câu SQL hai lần

Trong SQL*Plus và SQLcl, dấu `/` ở dòng riêng còn có thể **thực thi lại nội dung SQL đang ở bộ đệm**. Vì thế đoạn sau dễ chạy `SELECT` hai lần:

```sql
SELECT 'once or twice?' AS message FROM dual;
/
```

Với SQL đơn, thường chỉ cần `;`. Với một khối PL/SQL trong script, dùng `END;` và `/` như ví dụ trên. Đừng đặt `/` sau mọi câu SQL theo thói quen, nhất là sau `INSERT`, `UPDATE` hoặc `DELETE`: lặp DML có thể thay đổi dữ liệu nhiều lần hoặc gây lỗi khóa duy nhất.

## 7. Thực hành SQL, DML và transaction

Các ví dụ dưới đây sử dụng một bảng riêng cho bài thực hành. Chạy bằng `Run Script` trong SQL Developer hoặc nhập các lệnh tương ứng vào SQL*Plus/SQLcl.

### 7.1 Tạo bảng thực hành

```sql
CREATE TABLE lab_execution_log (
    log_id     NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_name VARCHAR2(100) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

Đây là câu lệnh DDL. Nó thay đổi cấu trúc schema và **Oracle thực hiện implicit commit liên quan đến DDL**. Vì vậy không nên coi `ROLLBACK` là cách hủy một lệnh `CREATE TABLE` đã thành công. Bảng này chỉ tạo **một lần**; chạy lại sẽ gặp lỗi trùng tên đối tượng nếu bảng vẫn tồn tại.

Nếu không có quyền `CREATE TABLE` hoặc quota phù hợp, cần dùng bảng thực hành đã được cấp quyền thay vì dùng tài khoản `SYS` để vượt lỗi quyền.

### 7.2 Chèn, đọc và xác nhận dữ liệu

```sql
INSERT INTO lab_execution_log (event_name)
VALUES ('first run');

SELECT log_id,
       event_name,
       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at_text
FROM lab_execution_log
ORDER BY log_id;

COMMIT;
```

`INSERT` thay đổi dữ liệu trong transaction hiện tại. `COMMIT` xác nhận những thay đổi chưa được xác nhận của transaction đó. Ví dụ này minh họa kiểu chạy tương tác; trong chương trình thật, ranh giới `COMMIT` phải phù hợp một thao tác nghiệp vụ hoàn chỉnh.

### 7.3 Thử `ROLLBACK` an toàn

```sql
INSERT INTO lab_execution_log (event_name)
VALUES ('temporary row');

SELECT event_name FROM lab_execution_log
WHERE event_name = 'temporary row';

ROLLBACK;

SELECT event_name FROM lab_execution_log
WHERE event_name = 'temporary row';
```

Nếu không có dữ liệu trùng từ trước, truy vấn trước `ROLLBACK` nhìn thấy dòng đang được chính session chèn; truy vấn sau không còn thấy dòng vừa được hoàn tác. Lưu ý `ROLLBACK` hoàn tác **toàn bộ các thay đổi chưa commit của session trong transaction hiện tại**, không chỉ câu `INSERT` ngay phía trên. Không chạy ví dụ rollback trong một phiên đang chứa công việc thực chưa được lưu.

### 7.4 Autocommit: không nên giả định

Trong cách làm việc thông thường của SQL*Plus/SQLcl, có thể đặt rõ:

```sql
SET AUTOCOMMIT OFF
```

SQL Developer có tùy chọn autocommit theo connection/Preferences và các nút **Commit**, **Rollback**. Hãy xác nhận thiết lập hiện tại thay vì suy đoán chỉ vì một lệnh `INSERT` đã báo thành công. Dữ liệu có thể xuất hiện ngay trong session đang thao tác nhưng chưa được session khác nhìn thấy khi chưa `COMMIT`, tùy mức cô lập và trạng thái transaction. Một số hành động thoát ứng dụng hoặc lệnh thoát client có thể có hành vi commit/rollback riêng, vì vậy script cần đặt ranh giới xác nhận rõ ràng.

## 8. Chạy toàn bộ file `.sql` trong SQL*Plus và SQLcl

Thay vì gõ thủ công, lưu nội dung SQL vào file văn bản UTF-8, ví dụ `report.sql`:

```sql
-- report.sql
SET PAGESIZE 100
SET LINESIZE 160
PROMPT === REPORT: LAB EXECUTION LOG ===

SELECT log_id, event_name
FROM lab_execution_log
ORDER BY log_id DESC
FETCH FIRST 10 ROWS ONLY;

PROMPT === END REPORT ===
```

Trong SQL*Plus hoặc SQLcl đã kết nối:

```sql
@report.sql
```

Hoặc:

```sql
START report.sql
```

Các lệnh trên yêu cầu client mở file, đọc lệnh và chạy tuần tự. Nếu file không nằm trong thư mục đang làm việc hoặc vị trí mà client có thể tìm thấy, cần cung cấp đường dẫn phù hợp:

```sql
@C:\lab\sql\report.sql
```

Đường dẫn là đường dẫn **trên máy chạy client**, không phải thư mục trên máy chủ Oracle Database (trừ khi hai máy thật sự trùng nhau). Khi làm việc qua SSH, script nằm trên máy nơi tiến trình SQL*Plus/SQLcl đang chạy. Khi chạy SQL Developer cài trên laptop, đường dẫn `@...` được công cụ phía laptop xử lý.

Các ký tự khoảng trắng, dấu nháy và đường dẫn tương đối có thể yêu cầu cách đặt dấu nháy khác nhau theo client/phiên bản. Khi tự động hóa, dùng đường dẫn đã kiểm tra và thống nhất cách đặt thư mục làm việc.

### 8.1 `@` so với `@@` khi gọi script con

Ví dụ cấu trúc file:

```text
C:\lab\sql\
  main.sql
  01_setup.sql
  02_insert.sql
  03_report.sql
```

Trong `main.sql`:

```sql
PROMPT Chay bo script thuc hanh
@@01_setup.sql
@@02_insert.sql
@@03_report.sql
PROMPT Hoan thanh
```

Trong SQL*Plus/SQLcl, `@@` dùng khi script đang chạy muốn gọi một script khác **theo vị trí của script đang gọi**, đặc biệt hữu ích với các file con nằm cùng thư mục. `@` hoặc `START` dùng để gọi script theo đường dẫn/tìm kiếm file của client. Chọn `@@` cho các file phụ thuộc lẫn nhau giúp gói script dễ di chuyển giữa thư mục hơn, dù bạn vẫn cần xác minh đường dẫn khi đổi nền tảng hoặc client.

SQL Developer hỗ trợ thực thi nhiều lệnh script tương thích qua **Run Script (F5)**; khi dùng `@`/`@@`, kiểm tra phiên bản và đường dẫn trên máy cài SQL Developer nếu kết quả khác terminal. **Run Statement (F9)** không phải nơi thích hợp để gọi hàng loạt lệnh `@` như một script runner.

## 9. Dùng biến trong script: `&`, `ACCEPT` và bind variable

Biến giúp tái sử dụng một file với nhiều tham số mà không cần sửa SQL thủ công. Tuy nhiên **substitution variable** và **bind variable** khác nhau về cơ chế và tính an toàn.

### 9.1 Substitution variable: thay văn bản trước khi gửi SQL

Ví dụ `report_from_id.sql`:

```sql
SET VERIFY OFF
PROMPT Bao cao tu log_id = &1

SELECT log_id, event_name
FROM lab_execution_log
WHERE log_id >= &1
ORDER BY log_id;
```

Trong SQL*Plus/SQLcl, gọi:

```sql
@report_from_id.sql 10
```

Đối số `10` được dùng cho vị trí `&1`. Nếu sử dụng `&variable_name` mà chưa có giá trị, client có thể hỏi người dùng nhập. `SET VERIFY OFF` chỉ ảnh hưởng việc in ra văn bản trước/sau thay thế, không chuyển substitution thành bind.

Có thể khai báo giá trị đơn giản:

```sql
DEFINE min_log_id = 10

SELECT log_id, event_name
FROM lab_execution_log
WHERE log_id >= &min_log_id;

UNDEFINE min_log_id
```

**Điều cần nhớ:** `&min_log_id` là thay **chuỗi văn bản ngay trên client** rồi mới gửi SQL. Nếu lấy giá trị chưa kiểm soát từ người dùng và nối trực tiếp vào SQL, script có thể phát sinh lỗi cú pháp hoặc rủi ro SQL injection. Ngoài ra, chuỗi có dấu nháy đơn, ký tự `&` hoặc định dạng ngày có thể gây lỗi thay thế. Dùng substitution cho các tham số script tin cậy và kiểm soát định dạng; với dữ liệu người dùng trong ứng dụng, ưu tiên bind variable.

### 9.2 `ACCEPT`: hỏi tham số có kiểu dữ liệu

SQL*Plus và SQLcl hỗ trợ kiểu làm việc tương tác:

```sql
ACCEPT p_min_id NUMBER PROMPT 'Nhap log_id toi thieu: '

SELECT log_id, event_name
FROM lab_execution_log
WHERE log_id >= &p_min_id;

UNDEFINE p_min_id
```

Khai báo `NUMBER` giúp ràng buộc định dạng nhập cơ bản trong script tương tác. Tuy nhiên `ACCEPT` vẫn đưa giá trị vào qua cơ chế substitution chứ **không phải bind**; không dùng nó thay thế các API tham số hóa của Java/JDBC khi xử lý dữ liệu không tin cậy.

### 9.3 Bind variable: truyền giá trị qua `:name`

Ví dụ dành cho môi trường SQL*Plus/SQLcl và script runner SQL Developer có hỗ trợ cú pháp `VARIABLE`:

```sql
VARIABLE p_event VARCHAR2(100)

BEGIN
    :p_event := 'script executed';
END;
/

INSERT INTO lab_execution_log (event_name)
VALUES (:p_event);

PRINT p_event
ROLLBACK;
```

`VARIABLE` tạo biến phía client, còn `:p_event` là tham chiếu bind trong SQL/PLSQL. Bind giúp database tiếp nhận giá trị tách khỏi cấu trúc câu SQL, hỗ trợ tái sử dụng câu lệnh và tránh việc dựng SQL bằng cách nối dữ liệu trực tiếp. `PRINT` là lệnh của client để hiển thị biến, không phải SQL.

Khi viết chương trình Java kết nối Oracle, nguyên tắc này tương ứng với `PreparedStatement` và tham số `?`, dù cú pháp khai báo biến của JDBC khác cú pháp `VARIABLE` trong SQL*Plus/SQLcl.

**Chú ý:** cơ chế hỏi bind/substitution có thể khác giữa **Run Statement** và **Run Script** của SQL Developer. Một script sử dụng `VARIABLE`, `PRINT`, `@` và `PROMPT` nên được thử trong chế độ **F5** khi muốn hành vi tương thích script dòng lệnh.

## 10. Ghi kết quả ra file bằng `SPOOL`

Khi cần log thao tác hoặc lưu báo cáo:

```sql
SET ECHO ON
SET FEEDBACK ON
SET TIMING ON
SET LINESIZE 160
SET PAGESIZE 100
SPOOL C:\lab\sql\run-output.log

PROMPT === START ===
SELECT USER AS connected_user FROM dual;
SELECT COUNT(*) AS total_rows FROM lab_execution_log;
PROMPT === FINISH ===

SPOOL OFF
```

`SPOOL` ghi phần output do công cụ tạo ra vào file trên máy client. `SET ECHO ON` hữu ích khi chạy file script vì giúp ghi lại câu lệnh được đọc từ script; `SET TIMING ON` thêm thông tin thời gian do client thu thập. Nếu chỉ muốn dữ liệu xuất ra file dạng chuẩn để máy khác xử lý, SQLcl có thể dùng định dạng CSV hoặc một công cụ xuất dữ liệu phù hợp thay vì coi log văn bản là CSV sạch.

Sự khác nhau giữa các loại output:

| Kênh | Mục đích | Điểm lưu ý |
|---|---|---|
| Terminal output | Theo dõi tương tác trong SQL*Plus/SQLcl | Có thể gồm header, feedback, thời gian và thông báo |
| SQL Developer **Query Result** | Quan sát một tập kết quả dạng bảng | Thuận tiện để xem/sắp xếp/xuất dữ liệu qua GUI |
| SQL Developer **Script Output** | Xem thứ tự nhiều câu và thông báo kiểu script | Phù hợp các lệnh `PROMPT`, `SET`, PL/SQL trong F5 |
| `DBMS_OUTPUT` | Thông điệp từ PL/SQL | Cần client bật thu thập; không phải log tập trung |
| `SPOOL` | Ghi output client xuống file | Đường dẫn/permission nằm ở máy chạy công cụ |

Một số thông tin như password, token hoặc dữ liệu khách hàng có thể vô tình xuất hiện trong log nếu script in lệnh/giá trị. Chỉ lưu và chia sẻ log theo quyền thích hợp; không bật echo toàn bộ trong quy trình chứa thông tin nhạy cảm nếu không cần thiết.

## 11. Tổ chức một bộ script có thể chạy lặp lại

Để thấy đầy đủ quy trình, giả sử ta tạo ba file bên cạnh nhau trong `C:\lab\sql\` và chỉ chạy trong **schema thực hành**.

**File `01_setup.sql` — tạo bảng, chạy một lần:**

```sql
PROMPT Creating lab table...

CREATE TABLE lab_script_run (
    run_id     NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    note       VARCHAR2(100) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

**File `02_execute.sql` — ghi một dòng và xem kết quả:**

```sql
PROMPT Inserting a row...

VARIABLE v_note VARCHAR2(100)
BEGIN
    :v_note := 'executed by script';
    DBMS_OUTPUT.PUT_LINE('Preparing insert');
END;
/

INSERT INTO lab_script_run(note) VALUES (:v_note);
COMMIT;

SELECT run_id,
       note,
       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS run_at
FROM lab_script_run
ORDER BY run_id DESC
FETCH FIRST 5 ROWS ONLY;
```

**File `main.sql` — điều phối:**

```sql
SET SERVEROUTPUT ON
SET FEEDBACK ON
SET TIMING ON
SET ECHO ON

PROMPT ===== START LAB =====
@@01_setup.sql
@@02_execute.sql
PROMPT ===== END LAB =====
```

Để chạy trên CLI, chuyển vào thư mục chứa script và kết nối đúng service bằng SQL*Plus hoặc SQLcl, sau đó:

```sql
@main.sql
```

Trong SQL Developer, mở `main.sql` trong SQL Worksheet phù hợp và chọn **Run Script (F5)**; kiểm tra khả năng phân giải các `@@` đối với client/phiên bản đang dùng.

Ở lần chạy đầu tiên, `01_setup.sql` tạo bảng và `02_execute.sql` ghi một dòng. **Lần chạy tiếp theo sẽ lỗi tạo bảng do bảng đã tồn tại**. Điều đó cho thấy hai tính chất khác nhau:

- Script *thiết lập schema* thường phải quản lý phiên bản, trạng thái đã áp dụng và chiến lược migration, thay vì mù quáng chạy lại `CREATE`.
- Script *thao tác dữ liệu* cần quyết định có được phép chạy lặp và thêm dòng mới hay không. Với nghiệp vụ yêu cầu idempotency, cần khóa nghiệp vụ và điều kiện xử lý thích hợp.

Không tự xóa bảng hoặc dùng `DROP TABLE ... PURGE` chỉ để script “chạy lại cho được” khi có dữ liệu cần giữ. Trong môi trường thực tế, nên dùng migration có kiểm soát và hệ thống quản lý phiên bản schema thay vì chèn logic phá hủy dữ liệu vào script dùng chung.

## 12. Xử lý lỗi và mã thoát khi chạy script tự động

Chạy thủ công có thể đọc lỗi trên màn hình; còn CI/CD, batch job hoặc tác vụ vận hành cần **trả mã thoát** để bước tiếp theo biết thành công hay thất bại.

SQL*Plus hỗ trợ các chỉ thị kiểu:

```sql
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK
```

`WHENEVER SQLERROR` yêu cầu SQL*Plus thoát khi gặp lỗi **SQL/PLSQL** (ví dụ thiếu bảng, lỗi ràng buộc, procedure lỗi); `WHENEVER OSERROR` xử lý một số lỗi hệ điều hành/client được hỗ trợ. SQLcl cũng hỗ trợ kiểu điều khiển script này trong phạm vi tương thích. Cú pháp cụ thể và mã thoát trả về môi trường gọi nên được kiểm chứng theo phiên bản đang sử dụng.

Ví dụ `batch_job.sql`, dùng cho **chạy không tương tác** với đối tượng đã tồn tại:

```sql
SET ECHO ON
SET FEEDBACK ON
WHENEVER OSERROR EXIT FAILURE ROLLBACK
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

INSERT INTO lab_execution_log (event_name)
VALUES ('batch job');

COMMIT;
EXIT SUCCESS
```

Nếu câu `INSERT` lỗi, script thoát và rollback các thay đổi chưa commit. Nếu thành công, script commit rồi trả về trạng thái thành công. Tác vụ gọi SQL*Plus/SQLcl cần kiểm tra exit code **và** log của quá trình chạy.

Lưu ý quan trọng: `WHENEVER SQLERROR` **không bảo đảm bắt mọi lỗi cú pháp của lệnh client** như một lệnh `SET` không tồn tại hoặc một số lỗi `SP2-...`; đây không phải trình bắt lỗi chung cho toàn bộ ngôn ngữ script. Cũng không nên đặt `EXIT SUCCESS` giữa một phiên tương tác đang chứa các thao tác chưa lưu. Một lệnh DDL chạy thành công trước lỗi SQL tiếp theo có thể đã implicit commit, nên rollback lúc thoát không thể khôi phục schema về trước DDL.

Với SQL Developer GUI, lỗi thường hiển thị trong Results/Script Output và không cung cấp cùng mô hình exit code cho một shell job. Khi cần tự động hóa có giám sát mã thoát, ưu tiên dùng một công cụ CLI phù hợp.

## 13. Lỗi thường gặp khi dùng ba công cụ

| Triệu chứng/lỗi | Nguyên nhân thường gặp | Cách kiểm tra/xử lý |
|---|---|---|
| `ORA-01017: invalid username/password` | Sai thông tin đăng nhập hoặc cách xác thực | Kiểm tra username, mật khẩu, service và cấu hình xác thực; không in mật khẩu ra log |
| `ORA-12154` | Không phân giải được connect identifier/TNS alias | Kiểm tra chuỗi Easy Connect, `tnsnames.ora`, biến môi trường/cấu hình Oracle Net |
| `ORA-12514` | Listener không biết service đã yêu cầu | Xác nhận host/port/service name và trạng thái dịch vụ với quản trị viên |
| `ORA-00942` | Bảng/view không tồn tại trong schema phân giải tên hoặc thiếu quyền truy cập | Kiểm tra `USER`, schema, tên đối tượng và quyền được cấp |
| `ORA-01031` | Không đủ quyền thực hiện thao tác | Dùng tài khoản/quyền đúng nhiệm vụ; không tự nâng thành `SYSDBA` |
| `ORA-00001` | Vi phạm unique constraint/index | Kiểm tra khóa duy nhất và nguyên nhân chèn trùng; không bỏ ràng buộc để che lỗi |
| `ORA-06550` kèm `PLS-...` | PL/SQL biên dịch/thực thi lỗi | Đọc dòng/vị trí lỗi, kiểm tra cú pháp, kiểu dữ liệu và tên biến |
| `SP2-0310: unable to open file` (SQL*Plus) | Script không ở đường dẫn mà client có thể đọc | Kiểm tra thư mục làm việc, đường dẫn, quyền file; phân biệt `@` và `@@` |
| Script chạy nhưng không thấy `DBMS_OUTPUT` | Chưa bật thu thập/hiển thị thông điệp | `SET SERVEROUTPUT ON` khi chạy script; bật DBMS Output panel đúng connection khi chạy statement bằng GUI |
| PL/SQL không chạy hoặc chỉ báo chưa đủ lệnh | Thiếu dấu `/` ở dòng riêng | Kết thúc `END;` và thêm `/` ở dòng kế tiếp trong script |
| Một `INSERT` dường như chạy hai lần | Có `;` rồi thêm `/` không đúng chỗ | Xem lại lệnh trong buffer, xóa `/` thừa sau câu SQL đơn |
| SQL Developer chỉ chạy một câu trong nhiều câu | Đang dùng **Run Statement** thay vì **Run Script** | Dùng F5 cho một chuỗi lệnh `.sql` |
| Dữ liệu nhìn thấy trong một phiên nhưng phiên khác chưa thấy | DML chưa commit hoặc khác ngữ cảnh transaction | Kiểm tra autocommit, `COMMIT`, mức cô lập, kết nối/schema đang dùng |
| Kết quả ngày/giờ khác kỳ vọng | Chuyển đổi ngầm phụ thuộc NLS | Dùng biểu thức chuyển đổi rõ ràng như `TO_DATE(..., 'YYYY-MM-DD')`, `TO_CHAR(..., 'YYYY-MM-DD HH24:MI:SS')` |

Chữ số mã lỗi và nội dung có thể thay đổi đôi chút giữa các phiên bản. Nên lưu **toàn bộ thông báo**, bao gồm dòng SQL gây lỗi và trạng thái connection, vì chỉ nhìn một mã lỗi chưa đủ biết chính xác nguyên nhân.

## 14. Quy ước nên áp dụng khi viết script Oracle

1. **Ghi rõ môi trường mục tiêu.** Trước khi chạy script cập nhật dữ liệu, xác minh user, service/PDB và schema. Tránh trường hợp bảng cùng tên tồn tại trong nhiều môi trường.
2. **Dùng account ít quyền nhất đủ làm việc.** Không chạy script thực hành bằng `SYS`/`SYSTEM` và không cấp quyền rộng chỉ để vượt một lỗi truy cập.
3. **Tách script đọc, DML và DDL có tác động lớn.** Đánh dấu rõ đoạn nào thay đổi dữ liệu và cần `COMMIT`; quản lý schema bằng migration nếu triển khai nhiều môi trường.
4. **Đặt transaction boundary có chủ đích.** `COMMIT`/`ROLLBACK` phải thuộc quyết định nghiệp vụ; nhớ DDL có implicit commit và client có hành vi thoát riêng.
5. **Dùng bind variable cho giá trị dữ liệu.** Không dựng SQL ứng dụng bằng cách nối chuỗi người dùng hoặc chèn substitution text không kiểm soát.
6. **Đặt dấu kết thúc đúng.** `;` cho SQL thông thường; khối PL/SQL trong script kết thúc bằng `END;` rồi `/` ở dòng riêng; không lạm dụng `/` sau DML.
7. **Định dạng ngày, số và kết quả rõ ràng.** Đặc biệt khi chuyển dữ liệu qua môi trường khác nhau về NLS/locale; không phụ thuộc việc Oracle ngầm hiểu chuỗi ngày.
8. **Lưu script dưới version control và có thứ tự chạy.** Đặt tên như `001_create_tables.sql`, `002_seed_data.sql`, `003_report.sql`, và mô tả trạng thái cần có trước khi chạy.
9. **Quan sát lỗi theo ngữ cảnh.** Trong batch job cần exit code, log và xử lý từng nhóm lỗi; tránh coi một màn hình hiển thị nhiều dòng là bằng chứng tất cả thao tác thành công.
10. **Bảo vệ thông tin nhạy cảm.** Không đưa password vào file `.sql`, lịch sử shell hoặc output; cấu hình quyền file log và kiểm tra nội dung `SPOOL` trước khi chia sẻ.

## 15. Bài tập thực hành

### Bài tập 1: cùng một truy vấn ở ba công cụ

Hãy kết nối đúng schema rồi chạy:

```sql
SELECT USER AS current_user,
       SYSTIMESTAMP AS database_timestamp
FROM dual;
```

Quan sát: SQL*Plus hiển thị kết quả dạng terminal; SQLcl có khả năng đổi định dạng; SQL Developer **Run Statement** hiển thị dạng grid, còn **Run Script** in dạng script output. Đối chiếu kết quả logic với cách hiển thị, đồng thời xác nhận không kết nối nhầm môi trường.

### Bài tập 2: chạy SQL và PL/SQL trong một script

Tạo file `hello_oracle.sql`:

```sql
SET SERVEROUTPUT ON
PROMPT Start example

SELECT 2 * 5 AS arithmetic_result FROM dual;

BEGIN
    DBMS_OUTPUT.PUT_LINE('PL/SQL block completed');
END;
/

PROMPT End example
```

Chạy `@hello_oracle.sql` bằng SQL*Plus/SQLcl, rồi chạy nội dung này bằng F5 trong SQL Developer. Xác định dòng nào do database trả về và dòng nào do client tự tạo.

### Bài tập 3: kiểm chứng transaction

Trong schema thực hành đã tạo bảng `lab_execution_log`, thực hiện:

```sql
INSERT INTO lab_execution_log(event_name)
VALUES ('rollback exercise');

SELECT COUNT(*) AS row_count
FROM lab_execution_log
WHERE event_name = 'rollback exercise';

ROLLBACK;

SELECT COUNT(*) AS row_count
FROM lab_execution_log
WHERE event_name = 'rollback exercise';
```

So sánh hai lần đếm; nếu đã có dòng cùng tên từ trước thì số sau `ROLLBACK` không nhất thiết bằng 0. Thử lại với một giá trị có thể phân biệt riêng, quan sát session hiện tại và session khác khi chưa commit, và ghi lại kết luận về transaction visibility.

### Bài tập 4: tham số và log

Tạo file `find_log.sql`:

```sql
SET FEEDBACK ON
PROMPT Looking up logs since id &1

SELECT log_id, event_name
FROM lab_execution_log
WHERE log_id >= &1
ORDER BY log_id;
```

Chạy `@find_log.sql 1` rồi `@find_log.sql 100` bằng SQL*Plus/SQLcl. Sau đó dùng `SPOOL` để ghi kết quả vào file trong thư mục do bạn quản lý. Giải thích vì sao `&1` là substitution variable và khi nào cần đổi sang bind variable.

## 16. Chọn công cụ theo công việc

| Nhu cầu | Công cụ phù hợp | Lý do chính |
|---|---|---|
| Gõ lệnh Oracle trên terminal, qua SSH, môi trường tối giản | **SQL*Plus** | Nhẹ, quen thuộc, phù hợp nhiều script vận hành có sẵn |
| Chạy script từ terminal, cần tiện ích định dạng/xuất kết quả | **SQLcl** | Hỗ trợ nhiều lệnh SQL*Plus và mở rộng tiện ích CLI |
| Khám phá schema, thử truy vấn và xem tập kết quả tương tác | **SQL Developer – Run Statement** | Results grid và công cụ trực quan |
| Chạy chuỗi SQL/PLSQL, `PROMPT`, `SET` và script trong GUI | **SQL Developer – Run Script** | Xử lý nội dung theo luồng script và hiển thị Script Output |
| Tự động hóa deploy/batch cần exit code và log | **SQL*Plus hoặc SQLcl** | Dễ tích hợp trong quá trình dòng lệnh và xử lý lỗi có điều kiện |

Hai nguyên tắc quan trọng nhất khi thực hành là: **biết câu lệnh nào được chạy ở Oracle Database, câu lệnh nào do client xử lý; và biết lúc nào đang chạy một câu lệnh, lúc nào đang chạy cả script.** Khi đã nắm rõ `F9`/`F5`, `;`/`/`, `@`/`@@`, bind/substitution, `COMMIT`/`ROLLBACK` và `SPOOL`, bạn có thể chuyển từ thử SQL thủ công sang viết quy trình thao tác Oracle có thể lặp lại, quan sát và kiểm soát được.
