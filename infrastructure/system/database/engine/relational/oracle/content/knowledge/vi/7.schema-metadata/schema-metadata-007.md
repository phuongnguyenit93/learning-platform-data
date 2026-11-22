# Tra cứu mã PL/SQL, lỗi biên dịch và trạng thái INVALID trong Oracle Database

Khi làm việc với Oracle Database, bạn không chỉ tạo bảng và chạy câu lệnh SQL. Database còn lưu nhiều đối tượng **PL/SQL** như procedure, function, package, trigger và type body. Những đối tượng này có **mã nguồn**, **trạng thái biên dịch**, **thông báo lỗi** và **quan hệ phụ thuộc** với các đối tượng khác. Tất cả đều có thể được tra cứu qua **data dictionary** của Oracle.

Một tình huống quen thuộc: ứng dụng gọi một procedure và gặp lỗi, trong khi file mã nguồn cục bộ trông có vẻ đúng. Có thể procedure trên database vẫn chứa bản cũ, vừa bị lỗi khi biên dịch hoặc đã chuyển sang trạng thái `INVALID` vì bảng/package phụ thuộc thay đổi. Để tìm nguyên nhân, cần trả lời theo thứ tự: *Đang kết nối vào database và schema nào? Mã PL/SQL thực sự được lưu là gì? Object nào INVALID? Compiler báo lỗi ở dòng nào? Object đang phụ thuộc vào đâu?*

Mục tiêu sau bài học:

- Xác định schema, container/PDB và loại PL/SQL object cần kiểm tra.
- Đọc mã nguồn qua `USER_SOURCE`, `ALL_SOURCE` và khi được cấp quyền, `DBA_SOURCE`.
- Tra cứu lỗi biên dịch qua `USER_ERRORS`, `ALL_ERRORS`, `DBA_ERRORS` và lệnh `SHOW ERRORS`.
- Phân biệt trạng thái `VALID`/`INVALID` trong `USER_OBJECTS` hoặc `ALL_OBJECTS` với lỗi phát sinh khi **thực thi**.
- Hiểu sự khác biệt giữa package specification và package body khi biên dịch.
- Điều tra invalidation do dependency, quyền truy cập, thay đổi DDL và thực hiện biên dịch lại có kiểm soát.
- Thực hành tạo một procedure lỗi, đọc lỗi, sửa mã, kiểm tra trạng thái và gọi thành công.

> Các ví dụ dùng các object tự tạo trong **schema thực hành**. Đừng chạy lệnh `CREATE OR REPLACE` hoặc `ALTER ... COMPILE` đối với object production chưa được phép thay đổi; thay đổi package specification, trigger hoặc các object dùng chung có thể ảnh hưởng nhiều phiên và ứng dụng. Nội dung tập trung vào Oracle Database hiện đại; một số cột/quyền của dictionary view thay đổi theo phiên bản và chính sách bảo mật.

## 1. Đặt PL/SQL object vào bức tranh schema và metadata

**Schema** là tập các đối tượng thuộc một database user. Khi bạn tạo một procedure thông thường dưới tài khoản `LAB_USER`, object được lưu trong schema `LAB_USER`, trừ khi câu lệnh có quyền và chỉ định chủ sở hữu khác. Các object PL/SQL có thể được lưu và biên dịch trong database; chúng khác anonymous PL/SQL block mà client gửi để chạy tức thời.

| Loại | Ví dụ | Được lưu như object có tên? | Mã nguồn có thể tra cứu? |
| --- | --- | --- | --- |
| **Procedure** | `LAB_SEND_EMAIL` | Có | Thường qua `USER_SOURCE` với `TYPE='PROCEDURE'` |
| **Function** | `LAB_TOTAL_PRICE` | Có | `TYPE='FUNCTION'` |
| **Package specification** | `LAB_ORDER_PKG` khai báo API | Có | `TYPE='PACKAGE'` |
| **Package body** | `LAB_ORDER_PKG` phần triển khai | Có, là object type riêng | `TYPE='PACKAGE BODY'` |
| **Trigger** | `LAB_AUDIT_TRG` | Có | `TYPE='TRIGGER'` |
| **Object type/type body** | `LAB_ADDRESS_TYPE` | Có | `TYPE='TYPE'` và `TYPE='TYPE BODY'` |
| **Anonymous block** | `DECLARE ... BEGIN ... END;` | Không như stored schema object độc lập | Không xuất hiện như một procedure trong `USER_SOURCE` |

Một stored object có thông tin phân tán trong nhiều dictionary views. Không nên xem một view là nguồn duy nhất cho toàn bộ chẩn đoán.

```text
            Oracle Database / PDB hiện tại
                         │
                        Schema
                         │
              Stored PL/SQL object
                         │
          ┌──────────────┼──────────────┬────────────────┐
          │              │              │                │
          ▼              ▼              ▼                ▼
      *_SOURCE       *_OBJECTS       *_ERRORS       *_DEPENDENCIES
      Mã nguồn       Trạng thái       Lỗi/warning    Quan hệ phụ thuộc
      từng dòng      VALID/INVALID   biên dịch       giữa các object
```

### 1.1. Ba phạm vi USER, ALL và DBA

Nhiều nhóm data dictionary views có ba tiền tố:

| Tiền tố | Ý nghĩa tổng quát | Khi nào dùng |
| --- | --- | --- |
| `USER_*` | Các object thuộc **schema của user đang kết nối** | Bắt đầu khi đang sở hữu procedure/package cần sửa; không cần cột `OWNER` |
| `ALL_*` | Những object mà user hiện tại có thể truy cập/nhìn thấy theo quyền dictionary | Tìm object ở schema khác trong phạm vi được phép; thường có `OWNER` |
| `DBA_*` | Thông tin toàn database trong phạm vi quyền quản trị tương ứng | Phân tích nhiều schema; yêu cầu quyền phù hợp |

Ví dụ, `USER_SOURCE` và `USER_ERRORS` phù hợp với tài khoản đang sở hữu procedure; muốn kiểm tra `HR.PAYROLL_PKG` từ user khác, bạn có thể cần `ALL_SOURCE`/`ALL_ERRORS` nếu quyền cho phép hoặc nhờ DBA. **Không mặc định rằng có quyền EXECUTE một package thì luôn được xem toàn bộ mã nguồn private/body**; mức hiển thị phụ thuộc quyền, phiên bản và chính sách.

Oracle Database Multitenant còn có cấp **CDB/PDB**. Một user cùng tên ở hai PDB có thể sở hữu các object khác nhau. Vì thế trước khi đọc `USER_SOURCE` phải xác định đúng session/connection.

## 2. Xác định đúng phiên đăng nhập trước khi chẩn đoán

Chạy một câu SQL đơn giản:

```sql
SELECT USER AS login_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
```

Ý nghĩa:

- `LOGIN_USER`: database user đã đăng nhập.
- `CURRENT_SCHEMA`: schema được dùng để phân giải tên object không ghi owner; có thể đã bị đổi bằng `ALTER SESSION SET CURRENT_SCHEMA`.
- `CONTAINER_NAME`: CDB root hoặc PDB hiện tại.
- `DATABASE_NAME` và `SERVICE_NAME`: giúp xác nhận đúng database/service đích.

**Lưu ý quan trọng:** `CURRENT_SCHEMA` có thể khác `USER`. Các view `USER_*` mô tả object thuộc schema của **current user**, không tự chuyển sang schema mới chỉ vì bạn đặt `CURRENT_SCHEMA` khác. Nếu cần kiểm tra một object thuộc owner khác, dùng tên schema rõ ràng và view `ALL_*` với điều kiện `OWNER` khi được quyền.

Một checklist thông tin kết nối thực tế:

```text
Database/service:   ORACLE_LAB / FREEPDB1       (ví dụ)
PDB hiện tại:       FREEPDB1
Login user:         LAB_USER
Current schema:     LAB_USER
Object owner:       LAB_USER
Object name:        LAB_COMPILE_DEMO
Object type:        PROCEDURE
```

Đừng dùng các tên trong ví dụ để suy đoán tên của database thật.

## 3. Tra cứu mã nguồn PL/SQL trong USER_SOURCE

`USER_SOURCE` lưu mã nguồn các object PL/SQL thuộc schema hiện tại, thường theo **từng dòng**. Các cột cốt lõi:

| Cột | Ý nghĩa |
| --- | --- |
| `NAME` | Tên stored object |
| `TYPE` | Loại nguồn: `PROCEDURE`, `FUNCTION`, `PACKAGE`, `PACKAGE BODY`, `TRIGGER`, `TYPE`, `TYPE BODY`... |
| `LINE` | Số thứ tự dòng mã nguồn của object |
| `TEXT` | Nội dung dòng mã nguồn được lưu |

Ví dụ đọc một procedure:

```sql
SELECT line, text
FROM user_source
WHERE name = 'LAB_COMPILE_DEMO'
  AND type = 'PROCEDURE'
ORDER BY line;
```

**Phải `ORDER BY LINE`** để tái dựng đúng thứ tự; kết quả của một truy vấn SQL không có `ORDER BY` không được đảm bảo theo thứ tự lưu trữ. Tên object không đặt trong double quotes khi tạo thường được Oracle lưu/tra cứu theo dạng chữ hoa, vì vậy dùng `'LAB_COMPILE_DEMO'`. Object được tạo bằng double quotes với tên phân biệt chữ hoa/thường phải dùng đúng chữ.

### 3.1. Đọc package specification và package body

Package có hai phần mã nguồn có vai trò khác nhau:

- **Specification (`TYPE='PACKAGE'`):** khai báo public procedures, functions, types, constants, cursors và API cho caller.
- **Body (`TYPE='PACKAGE BODY'`):** định nghĩa phần triển khai và có thể chứa các thành phần private.

Đọc tách hai phần:

```sql
SELECT type, line, text
FROM user_source
WHERE name = 'LAB_ORDER_PKG'
  AND type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY CASE type WHEN 'PACKAGE' THEN 1 ELSE 2 END, line;
```

Không lọc chỉ bằng `NAME` rồi ghép các dòng bất kể `TYPE`: dòng 1 của specification và dòng 1 của body là **hai bộ đếm riêng**. Cũng không coi status của package specification đại diện cho tình trạng biên dịch của body.

### 3.2. Đọc source ở schema khác khi có quyền

`ALL_SOURCE` có thêm `OWNER`:

```sql
SELECT owner, name, type, line, text
FROM all_source
WHERE owner = 'APP_OWNER'
  AND name = 'PAYMENT_PKG'
  AND type = 'PACKAGE'
ORDER BY line;
```

Khi có quyền quản trị phù hợp, `DBA_SOURCE` hỗ trợ phân tích toàn database trong phạm vi container liên quan:

```sql
SELECT owner, name, type, line, text
FROM dba_source
WHERE owner = 'APP_OWNER'
  AND name = 'PAYMENT_PKG'
  AND type = 'PACKAGE BODY'
ORDER BY line;
```

Hai ví dụ này là truy vấn minh họa. Không suy ra quyền xem nội dung package body của schema khác nếu database trả lỗi quyền hoặc không có hàng.

### 3.3. Vì sao mã nguồn tra cứu có thể khác file trong Git?

Các nguyên nhân phổ biến:

1. Đang kết nối nhầm PDB hoặc database môi trường khác.
2. Object owner khác schema bạn đang truy vấn.
3. File trong Git đã sửa nhưng **chưa triển khai** lên database, hoặc database đã nhận một bản triển khai khác.
4. Một script `CREATE OR REPLACE` được chạy từ client với cách xử lý dấu `/`/delimiter không như dự tính.
5. Object đã được **wrapped** (obfuscated bằng tính năng PL/SQL wrapping); dictionary có thể chứa biểu diễn wrapped, không hiển thị mã nguồn gốc thông thường.
6. Object là anonymous block, dynamic SQL hoặc mã được sinh trong runtime, nên không tồn tại dưới tên procedure trong `USER_SOURCE`.

`USER_SOURCE` phản ánh mã của stored object mà Oracle có trong schema/PDB hiện tại, còn Git phản ánh bản mã nguồn của repository. Khi đối chiếu, cần kiểm tra version triển khai, owner, tên object và loại source. `USER_SOURCE` không phải công cụ khôi phục đáng tin cậy mã plaintext từ wrapped PL/SQL.

## 4. Kiểm tra trạng thái VALID và INVALID

`USER_OBJECTS` (hoặc `ALL_OBJECTS` với cột `OWNER`) cho biết metadata của schema object: tên, loại, status và thời điểm DDL.

Liệt kê các PL/SQL object cần chú ý:

```sql
SELECT object_name,
       object_type,
       status,
       created,
       last_ddl_time
FROM user_objects
WHERE object_type IN (
    'PROCEDURE', 'FUNCTION',
    'PACKAGE', 'PACKAGE BODY',
    'TRIGGER', 'TYPE', 'TYPE BODY'
)
ORDER BY object_type, object_name;
```

Chỉ lấy các object `INVALID`:

```sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
```

Để xem object cụ thể:

```sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_name = 'LAB_COMPILE_DEMO';
```

### 4.1. VALID thực sự có nghĩa gì?

Với stored PL/SQL, **`VALID`** thường có nghĩa object được Oracle xem là hợp lệ về trạng thái biên dịch/phụ thuộc tại thời điểm tra cứu. Điều đó **không chứng minh** procedure sẽ thực thi thành công với mọi tham số hoặc mọi điều kiện runtime.

Ví dụ một procedure đã `VALID` vẫn có thể gặp:

- `NO_DATA_FOUND` hoặc `TOO_MANY_ROWS` từ `SELECT ... INTO`.
- Lỗi constraint, deadlock, mất kết nối hoặc tablespace đầy khi chạy.
- Lỗi quyền, dữ liệu hoặc object ở runtime trong những kịch bản thích hợp, đặc biệt có dynamic SQL.
- Exception do logic nghiệp vụ hoặc lỗi từ một procedure khác.

**`VALID` là thông tin về trạng thái object**, không phải chứng nhận toàn bộ nghiệp vụ đúng.

### 4.2. INVALID thực sự có nghĩa gì?

**`INVALID`** cho biết Oracle cần biên dịch/kiểm tra lại object trước khi có thể dùng bình thường, hoặc quá trình biên dịch trước đó không thành công. Những nguyên nhân thường gặp:

- Lỗi cú pháp hoặc khai báo trong PL/SQL.
- Tham chiếu đến bảng/cột/package/function không tồn tại, đã đổi tên hoặc không truy cập được.
- Thay đổi DDL ở object phụ thuộc làm object hiện tại bị invalidated.
- Package specification bị đổi dẫn đến việc các object phụ thuộc cần xác minh/biên dịch lại.
- Quyền truy cập cần cho việc biên dịch bị thu hồi hoặc cấp không đúng dạng.

Một object chuyển sang `INVALID` do **dependency invalidation** có thể **chưa có dòng lỗi biên dịch mới trong `USER_ERRORS`**. Oracle có cơ chế thử recompile khi đối tượng được dùng; nếu nguyên nhân biến mất và biên dịch thành công, object có thể trở lại `VALID`. Nếu lỗi vẫn còn, lệnh gọi có thể thất bại.

Đừng hiểu `INVALID` như một mệnh lệnh phải chạy ngay `ALTER ... COMPILE` trong mọi môi trường: trước hết cần xác định nguyên nhân và ảnh hưởng đến ứng dụng.

### 4.3. LAST_DDL_TIME là gì?

`LAST_DDL_TIME` là thời gian thao tác DDL liên quan object, có thể thay đổi do các lần compile, create/alter và một số hoạt động DDL khác. Nó **không phải thời điểm cuối cùng procedure được chạy**, cũng không phải một hash nội dung source. Nếu muốn theo dõi mã nguồn đã thay đổi về mặt nghiệp vụ, cần đối chiếu deployment/version hoặc diff nguồn có kiểm soát.

## 5. Tra cứu lỗi biên dịch trong USER_ERRORS

Khi `CREATE OR REPLACE PROCEDURE`, `FUNCTION`, `PACKAGE BODY` hoặc một đối tượng PL/SQL khác bị lỗi, Oracle có thể tạo/lưu object nhưng không biên dịch thành công. SQL*Plus thường hiển thị thông báo kiểu *Procedure created with compilation errors*. Muốn biết lỗi cụ thể phải đọc diagnostics.

`USER_ERRORS` chứa thông báo **ERROR/WARNING** được Oracle lưu cho các object thuộc schema hiện tại.

| Cột | Vai trò |
| --- | --- |
| `NAME` | Tên object |
| `TYPE` | Loại object, ví dụ `PROCEDURE` hoặc `PACKAGE BODY` |
| `SEQUENCE` | Thứ tự các diagnostic messages |
| `LINE` | Dòng trong source unit được báo lỗi |
| `POSITION` | Vị trí trong dòng được báo lỗi |
| `TEXT` | Nội dung thông báo |
| `ATTRIBUTE` | Loại diagnostic, thường `ERROR` hoặc `WARNING` |

Ví dụ:

```sql
SELECT name,
       type,
       sequence,
       line,
       position,
       attribute,
       text
FROM user_errors
WHERE name = 'LAB_COMPILE_DEMO'
ORDER BY type, sequence;
```

Nếu muốn chỉ xem lỗi:

```sql
SELECT line, position, text
FROM user_errors
WHERE name = 'LAB_COMPILE_DEMO'
  AND type = 'PROCEDURE'
  AND attribute = 'ERROR'
ORDER BY sequence;
```

**Lưu ý:** `WARNING` có thể xuất hiện khi PL/SQL warnings được bật mà object vẫn ở trạng thái `VALID`. Không phải dòng nào trong `USER_ERRORS` cũng có nghĩa object không chạy được. Ngược lại, object `INVALID` do phụ thuộc bị thay đổi có thể chưa có hàng diagnostic cho tới khi Oracle thử compile lại.

### 5.1. Ghép lỗi với dòng source

Trong nhiều trường hợp, bạn muốn biết ngay dòng source chứa lỗi:

```sql
SELECT e.type,
       e.sequence,
       e.line,
       e.position,
       e.attribute,
       e.text AS error_text,
       s.text AS source_line
FROM user_errors e
LEFT JOIN user_source s
       ON s.name = e.name
      AND s.type = e.type
      AND s.line = e.line
WHERE e.name = 'LAB_COMPILE_DEMO'
  AND e.type = 'PROCEDURE'
ORDER BY e.sequence;
```

`USER_ERRORS.LINE` và `USER_SOURCE.LINE` được đối chiếu trong **cùng unit và TYPE**. Số dòng hiển thị trong file `.sql` có thể khác số dòng source unit lưu trong Oracle, vì file client còn chứa lệnh `SET`, comments trước `CREATE`, câu SQL khác và dấu slash kết thúc. Dấu `/` thường là lệnh thực thi script của SQL*Plus/SQLcl, **không phải một dòng PL/SQL source**.

Một lỗi khai báo ban đầu có thể kéo theo nhiều lỗi thứ cấp. Hãy đọc từ `SEQUENCE` đầu tiên, giải quyết lỗi gốc, compile lại rồi xem diagnostics mới.

### 5.2. Tra cứu lỗi ở schema khác

Với quyền thích hợp:

```sql
SELECT owner, name, type, line, position, attribute, text
FROM all_errors
WHERE owner = 'APP_OWNER'
  AND name = 'PAYMENT_PKG'
ORDER BY type, sequence;
```

`DBA_ERRORS` có thể được dùng bởi người quản trị có quyền xem. Hai tên bảng ngoài schema cần xác định **owner chính xác**; không nên dùng câu truy vấn lọc theo `NAME` duy nhất khi có nhiều schema cùng tạo object tên giống nhau.

## 6. SHOW ERRORS trong SQL*Plus, SQLcl và SQL Developer

Trong SQL*Plus/SQLcl, sau khi chạy lệnh `CREATE OR REPLACE`, bạn có thể xem lỗi object mới nhất bằng:

```sql
SHOW ERRORS
```

Hoặc chỉ rõ loại và tên:

```sql
SHOW ERRORS PROCEDURE LAB_COMPILE_DEMO
SHOW ERRORS FUNCTION LAB_TOTAL_PRICE
SHOW ERRORS PACKAGE LAB_ORDER_PKG
SHOW ERRORS PACKAGE BODY LAB_ORDER_PKG
SHOW ERRORS TRIGGER LAB_AUDIT_TRG
```

Trong SQL Developer, **Run Script (F5)** thường hỗ trợ các lệnh script tương tự `SHOW ERRORS`; chế độ **Run Statement (Ctrl+Enter)** có cách xử lý khác. Bạn cũng có thể mở object và xem tab diagnostics/errors tùy phiên bản. Câu `SELECT` từ `USER_ERRORS` là cách SQL chuẩn về mặt client mà bạn có thể dùng nhất quán khi công cụ không hỗ trợ `SHOW ERRORS`.

Một số công cụ có mục **Compile/Recompile** trong giao diện. Hãy xác định đúng object type: đặc biệt, lỗi trong **package body** không có nghĩa phải compile hoặc thay đổi package specification.

## 7. Thực hành đầy đủ: tạo một procedure INVALID rồi sửa

Thực hành trên schema riêng, ví dụ `LAB_USER` trong đúng PDB. Cần quyền `CREATE PROCEDURE` trong schema và quyền thực thi `DBMS_OUTPUT` nếu muốn xem kết quả (môi trường thực hành thường có quyền cần thiết). Nếu object `LAB_COMPILE_DEMO` đã tồn tại và cần giữ nguyên, hãy đổi tên object mới để tránh `CREATE OR REPLACE` ghi đè mã của bài khác.

### Bước 1 — Chủ động tạo lỗi biên dịch

Trong SQL*Plus/SQLcl hoặc SQL Developer ở chế độ Run Script, chạy:

```sql
CREATE OR REPLACE PROCEDURE lab_compile_demo AS
    v_result NUMBER;
BEGIN
    v_result := missing_value + 1;
    DBMS_OUTPUT.PUT_LINE('Result = ' || v_result);
END;
/
```

Biến `missing_value` **chưa được khai báo** trong procedure; vì vậy compiler sẽ báo lỗi kiểu `PLS-00201: identifier ... must be declared` hoặc diagnostics liên quan. Dấu `/` ở dòng riêng yêu cầu client kiểu SQL*Plus gửi toàn bộ lệnh `CREATE OR REPLACE` để thực thi; nó không thuộc mã PL/SQL của procedure.

Lưu ý Oracle có thể trả một thông báo cho biết **procedure được tạo nhưng có lỗi biên dịch**. Điều đó có nghĩa tên object vẫn có thể xuất hiện trong dictionary, không phải có thể gọi thành công.

### Bước 2 — Xác nhận object INVALID

```sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'LAB_COMPILE_DEMO';
```

Kết quả mong đợi ở bước có lỗi:

```text
OBJECT_NAME          OBJECT_TYPE    STATUS
-------------------  -------------  -------
LAB_COMPILE_DEMO     PROCEDURE      INVALID
```

### Bước 3 — Đọc lỗi và mã thật trên database

```sql
SHOW ERRORS PROCEDURE LAB_COMPILE_DEMO
```

Và:

```sql
SELECT sequence, line, position, attribute, text
FROM user_errors
WHERE name = 'LAB_COMPILE_DEMO'
  AND type = 'PROCEDURE'
ORDER BY sequence;

SELECT line, text
FROM user_source
WHERE name = 'LAB_COMPILE_DEMO'
  AND type = 'PROCEDURE'
ORDER BY line;
```

Hãy đối chiếu line/position để tìm dòng có `missing_value`. Nếu thấy nhiều dòng lỗi, xử lý thông báo về identifier chưa khai báo trước. Những số dòng và thứ tự diagnostics cụ thể có thể thay đổi do trình bày source và phiên bản.

### Bước 4 — Sửa mã để compile thành công

Thay procedure bằng bản có khai báo/khởi tạo biến đầy đủ:

```sql
CREATE OR REPLACE PROCEDURE lab_compile_demo AS
    v_value  NUMBER := 41;
    v_result NUMBER;
BEGIN
    v_result := v_value + 1;
    DBMS_OUTPUT.PUT_LINE('Result = ' || v_result);
END;
/
```

Kiểm tra lại:

```sql
SHOW ERRORS PROCEDURE LAB_COMPILE_DEMO

SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'LAB_COMPILE_DEMO';

SELECT line, position, attribute, text
FROM user_errors
WHERE name = 'LAB_COMPILE_DEMO'
ORDER BY sequence;
```

Object thường chuyển sang `VALID` và không còn diagnostics `ERROR` của bản compile lỗi trước. Việc không có hàng trong `USER_ERRORS` sau compile thành công là bình thường khi không bật/không phát sinh warnings.

### Bước 5 — Gọi procedure sau khi compile

Trong SQL*Plus/SQLcl:

```sql
SET SERVEROUTPUT ON

BEGIN
    lab_compile_demo;
END;
/
```

Kết quả minh họa:

```text
Result = 42
```

Trong công cụ hỗ trợ DBMS_OUTPUT, bạn có thể cần bật panel/hiển thị output tương ứng. `SET SERVEROUTPUT ON` là lệnh client hỗ trợ xem `DBMS_OUTPUT`, không phải cú pháp thuộc procedure.

### Bước 6 — Biên dịch lại mà không đổi source

Nếu muốn yêu cầu Oracle biên dịch lại **procedure đã tồn tại**:

```sql
ALTER PROCEDURE lab_compile_demo COMPILE;

SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'LAB_COMPILE_DEMO';

SELECT line, position, text
FROM user_errors
WHERE name = 'LAB_COMPILE_DEMO'
ORDER BY sequence;
```

`ALTER ... COMPILE` không tự sửa mã nguồn: nó yêu cầu Oracle thử compile object đang lưu. Khi nguyên nhân lỗi vẫn còn, object có thể tiếp tục `INVALID`. Với lỗi kiểu `missing_value` chưa khai báo, phải sửa `CREATE OR REPLACE`; chạy `ALTER ... COMPILE` lặp lại không biến tên chưa khai báo thành hợp lệ.

> Khi chạy lại bài thực hành, `CREATE OR REPLACE` sẽ thay thế procedure cùng tên trong schema hiện tại. Chỉ thực hiện trong schema lab và khi bạn xác nhận không dùng object này cho bài khác.

## 8. PACKAGE và PACKAGE BODY: hai trạng thái biên dịch độc lập

Package được chia thành **specification** và **body**. Một package có thể có specification `VALID` nhưng body `INVALID`; trong trường hợp đó API có thể còn hiện diện nhưng việc gọi những routine cần body có thể thất bại.

Ví dụ package đơn giản:

```sql
CREATE OR REPLACE PACKAGE lab_math_pkg AS
    FUNCTION double_value(p_value NUMBER) RETURN NUMBER;
END lab_math_pkg;
/

CREATE OR REPLACE PACKAGE BODY lab_math_pkg AS
    FUNCTION double_value(p_value NUMBER) RETURN NUMBER IS
    BEGIN
        RETURN p_value * 2;
    END double_value;
END lab_math_pkg;
/
```

Tra cứu cả hai object:

```sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_name = 'LAB_MATH_PKG'
ORDER BY object_type;
```

Kết quả có thể gồm hai hàng:

```text
LAB_MATH_PKG   PACKAGE        VALID
LAB_MATH_PKG   PACKAGE BODY   VALID
```

Nếu trong body viết sai tên biến hoặc gọi routine không tồn tại, lỗi sẽ thuộc `TYPE='PACKAGE BODY'`:

```sql
SELECT type, line, position, attribute, text
FROM user_errors
WHERE name = 'LAB_MATH_PKG'
ORDER BY type, sequence;
```

Các lệnh compile liên quan:

```sql
ALTER PACKAGE lab_math_pkg COMPILE PACKAGE;
ALTER PACKAGE lab_math_pkg COMPILE BODY;
```

**Phân biệt tác động:** Compile specification có thể gây invalidation/revalidation ở những thành phần phụ thuộc theo cơ chế Oracle; nếu chỉ body lỗi, tập trung sửa body và dùng `COMPILE BODY` để tránh thay đổi không cần thiết ở public specification. Tạo/sửa public API trong spec có thể ảnh hưởng các caller lớn hơn nhiều so với thay đổi triển khai private trong body.

Khi xem source, luôn chỉ định đúng `TYPE`:

```sql
SELECT line, text
FROM user_source
WHERE name = 'LAB_MATH_PKG'
  AND type = 'PACKAGE BODY'
ORDER BY line;
```

**Một lỗi thường gặp:** chỉ chạy `SHOW ERRORS PACKAGE LAB_MATH_PKG` trong khi mã sai nằm ở `PACKAGE BODY`, rồi kết luận “không có lỗi”. Hãy kiểm tra đúng loại object.

## 9. Lỗi biên dịch khác lỗi runtime như thế nào?

Hai nhóm sự cố có đường điều tra khác nhau.

| Tình huống | Ví dụ | Nơi cần xem |
| --- | --- | --- |
| **Lỗi parse/compile stored PL/SQL** | `PLS-00201`: biến hoặc identifier chưa khai báo | `USER_ERRORS`, `USER_SOURCE`, `SHOW ERRORS` |
| **Lỗi SQL tĩnh trong stored PL/SQL** | `ORA-00904`: cột sai tên; `PL/SQL: SQL Statement ignored` | `USER_ERRORS` và bảng/cột/quyền phụ thuộc |
| **Lỗi phân giải object/quyền trong compile** | `PLS-00201`, `ORA-00942` khi object không truy cập được | `USER_ERRORS`, dependency, quyền trực tiếp |
| **Lỗi khi chạy một object VALID** | `NO_DATA_FOUND`, `TOO_MANY_ROWS`, `ZERO_DIVIDE` | Call stack, điều kiện dữ liệu, exception handler |
| **Lỗi khi gọi object đang invalid** | `ORA-04063`, `ORA-06508`, `ORA-04098` tùy object và đường gọi | `USER_OBJECTS`, `USER_ERRORS`, dependencies, alert/application logs |
| **Lỗi anonymous block** | `ORA-06550` và thông báo `PLS-...` khi chạy `BEGIN ... END;` | Output trả về từ client và chính anonymous block; không kỳ vọng có stored object mới trong `USER_ERRORS` |

### 9.1. Ví dụ VALID vẫn lỗi runtime

```sql
CREATE OR REPLACE PROCEDURE lab_runtime_demo AS
    v_num NUMBER;
BEGIN
    SELECT 1 / 0 INTO v_num
    FROM dual;
END;
/
```

Đây là procedure có cú pháp hợp lệ về nguyên tắc nhưng khi chạy có thể phát sinh lỗi toán học như `ORA-01476: divisor is equal to zero`. Vì vậy trạng thái `VALID` không bảo đảm nghiệp vụ thành công. Không nên dùng `USER_ERRORS` để tìm tất cả các lỗi chỉ xảy ra trong quá trình thực thi.

### 9.2. Ví dụ sai cột trong SQL tĩnh

Giả sử một bảng có cột `ORDER_ID` và `AMOUNT` nhưng procedure chứa:

```sql
SELECT amount_missing
INTO v_amount
FROM lab_orders
WHERE order_id = p_order_id;
```

Nếu bảng `LAB_ORDERS` tồn tại và compiler có quyền truy cập thích hợp, `AMOUNT_MISSING` có thể gây `ORA-00904: invalid identifier` khi compile procedure. Chỉ sửa procedure sẽ không đủ nếu vấn đề gốc là lược đồ bảng đã thay đổi hoặc câu SQL được viết theo một phiên bản schema khác.

## 10. Điều tra INVALID do dependency

Một procedure có thể `VALID` hôm qua nhưng `INVALID` hôm nay dù không ai sửa trực tiếp source của nó. Nguyên nhân thường là **đối tượng phụ thuộc** đã thay đổi.

Ví dụ:

```text
TABLE LAB_ORDERS
       │ cột được procedure tham chiếu
       ▼
PACKAGE BODY LAB_ORDER_PKG
       │ hàm được function khác gọi
       ▼
FUNCTION LAB_REPORT_TOTAL
```

Thay đổi DDL ở bảng hoặc package specification có thể làm một số dependent objects cần kiểm tra/biên dịch lại. Oracle có **fine-grained dependency management** ở các phiên bản hiện đại: không phải mọi thao tác DDL đều vô hiệu hóa tất cả dependent objects. Phải **kiểm tra trạng thái thực tế** sau thay đổi.

### 10.1. Tra cứu quan hệ phụ thuộc

`USER_DEPENDENCIES` có các cột như `NAME`, `TYPE`, `REFERENCED_OWNER`, `REFERENCED_NAME`, `REFERENCED_TYPE`:

```sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM user_dependencies
WHERE name = 'LAB_ORDER_PKG'
ORDER BY type, referenced_owner, referenced_name;
```

Để tìm object đang **phụ thuộc vào** một bảng hoặc package cụ thể trong phạm vi có thể thấy:

```sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM all_dependencies
WHERE referenced_owner = 'LAB_USER'
  AND referenced_name = 'LAB_ORDERS'
ORDER BY owner, name, type;
```

Các view này cung cấp thông tin dependency được Oracle ghi nhận; **dynamic SQL** dựng tên object lúc runtime không nhất thiết tạo dependency tĩnh như SQL tham chiếu trực tiếp. Hệ thống thật cần xét cả mã ứng dụng, synonyms và những lời gọi dynamic.

Nếu cần tra cứu trạng thái các object được dependency view liệt kê, dùng `ALL_OBJECTS` với owner/type phù hợp:

```sql
SELECT owner, object_name, object_type, status
FROM all_objects
WHERE owner = 'LAB_USER'
  AND object_name IN ('LAB_ORDERS', 'LAB_ORDER_PKG');
```

### 10.2. Recompile tự động và recompile thủ công

Oracle có thể **thử biên dịch lại một object INVALID khi object được tham chiếu/gọi**, nếu điều kiện cần đã được phục hồi. Điều đó không có nghĩa mọi lời gọi chắc chắn thành công: nếu cột đã bị xóa hoặc quyền vẫn thiếu, compile vẫn lỗi.

Khi cần chủ động compile:

```sql
ALTER PROCEDURE lab_compile_demo COMPILE;
ALTER FUNCTION lab_total_price COMPILE;
ALTER PACKAGE lab_math_pkg COMPILE BODY;
ALTER TRIGGER lab_audit_trg COMPILE;
```

Các lệnh là **mẫu cú pháp theo từng loại object**; chỉ chạy khi object tương ứng tồn tại và bạn có quyền, không chạy toàn bộ chúng như một script để “sửa hết lỗi”.

Hướng xử lý hợp lý:

1. Xác định object `INVALID` và object phụ thuộc thay đổi.
2. Đọc `USER_ERRORS`, `USER_SOURCE`/`ALL_SOURCE` và kiểm tra metadata schema/privileges.
3. Sửa nguyên nhân gốc: nguồn PL/SQL, tên cột/bảng, package API, quyền truy cập hoặc lỗi triển khai.
4. Compile lại object liên quan theo đúng loại.
5. Đọc lại `STATUS` và `*_ERRORS`; thử gọi trong điều kiện test phù hợp.
6. Kiểm tra các dependent objects và ứng dụng sử dụng API này.

**Không dùng bulk recompilation như giải pháp mặc định.** Các công cụ compile toàn schema hoặc recompile song song có thể tiêu thụ CPU, tác động đến phụ thuộc và cần quyền cao. Trong production, cần cân nhắc thời điểm bảo trì, phạm vi ảnh hưởng và kế hoạch khôi phục.

### 10.3. Quyền qua ROLE và quyền trực tiếp

Một nguyên nhân khó nhận biết là user có thể `SELECT` bảng ở session SQL nhưng stored PL/SQL **definer's-rights** lại không compile được vì quyền chỉ đến từ **role**.

Ví dụ user được cấp một role cho phép đọc `OTHER_SCHEMA.ORDERS`. Truy vấn ad hoc có thể chạy, nhưng khi procedure definer's-rights tham chiếu bảng này trong SQL tĩnh, quyền cần thiết thường phải được **grant trực tiếp cho owner của procedure**. Roles mặc định không được dùng để xác thực các quyền của named definer's-rights PL/SQL theo cách tương tự session SQL.

Với `AUTHID CURRENT_USER` (invoker's-rights), quyền và ngữ cảnh xác thực có những quy tắc bổ sung; không nên tổng quát hóa một câu sang mọi dạng routine và mọi phiên bản.

Khi gặp `PLS-00201` hoặc `ORA-00942` trong một stored procedure, cần kiểm tra:

- Object có tồn tại trong đúng PDB/schema không?
- Tên có chính xác, kể cả trường hợp dùng quoted identifiers không?
- Procedure dùng definer's-rights hay invoker's-rights?
- Owner có quyền trực tiếp cần thiết để compile không?
- Synonym có trỏ đúng object và grants có còn hiệu lực không?

**Không cấp `DBA` hoặc các quyền rộng chỉ để làm hết INVALID.** Cấp quyền đúng object/privilege và xác thực theo chính sách bảo mật của hệ thống.

## 11. Các lỗi thường gặp khi đọc metadata

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `USER_SOURCE` không có dòng | Sai schema/PDB, sai tên hoặc type, object chưa được tạo, không phải stored PL/SQL | Xem `USER`, `CURRENT_SCHEMA`, `CON_NAME`, `USER_OBJECTS` |
| `ALL_SOURCE` không thấy body | Thiếu quyền hiển thị, sai owner/type hoặc object được bảo vệ | Xác minh quyền, owner, chính sách và trạng thái object |
| `USER_ERRORS` rỗng nhưng status `INVALID` | Object invalidated do dependency nhưng chưa biên dịch lại hoặc lỗi ở object khác | Xem dependencies, tình trạng object gốc; compile có kiểm soát |
| `USER_ERRORS` có hàng nhưng status `VALID` | Chỉ có warnings, không phải errors | Xem `ATTRIBUTE`, `TYPE` và trạng thái hiện tại |
| `SHOW ERRORS` báo không có lỗi nhưng package vẫn không chạy | Đang xem `PACKAGE` thay cho `PACKAGE BODY`, hoặc lỗi runtime | Xem `USER_OBJECTS`/`USER_ERRORS` với đúng type |
| Đã sửa file source nhưng lỗi cũ vẫn còn | Chưa deploy đúng database/PDB, script chưa chạy hoặc dùng object khác owner | Đọc `USER_SOURCE` trên database, xác minh phiên kết nối |
| Compile thành công nhưng khi gọi lỗi | Lỗi runtime/data/privilege/dynamic SQL; gọi object phụ thuộc gặp vấn đề | Xem stack trace thực thi và status các dependency |
| Compile lại vẫn INVALID | Nguyên nhân gốc còn tồn tại | Đọc `USER_ERRORS` mới nhất, sửa source/dependency/grants |
| Status thay đổi sau DDL dù không sửa PL/SQL | Oracle invalidated dependency | Xem `USER_DEPENDENCIES` và thay đổi object được tham chiếu |
| Error line không khớp dòng file SQL | File có lệnh client, comments, dấu `/` trước/sau unit | So với `USER_SOURCE.LINE` trong đúng `TYPE` |
| Không tìm được object vừa gọi | Gọi qua synonym, owner khác hoặc cấu trúc edition/PDB khác | Truy ngược synonym/owner/edition và quyền metadata |

### 11.1. Một số mã lỗi đáng nhận biết

| Lỗi | Ý nghĩa thường gặp |
| --- | --- |
| `PLS-00103` | Compiler gặp token/cú pháp không mong đợi |
| `PLS-00201` | Identifier chưa được khai báo hoặc không thể phân giải/truy cập |
| `PLS-00302` | Component thuộc package/object không được khai báo hoặc không khả dụng |
| `PLS-00306` | Sai số lượng hoặc kiểu tham số khi gọi procedure/function |
| `ORA-00904` | SQL identifier/column không hợp lệ |
| `ORA-00942` | Table/view không tồn tại hoặc không truy cập được trong ngữ cảnh cần thiết |
| `ORA-04063` | Stored object (ví dụ package body/view) có lỗi |
| `ORA-06508` | Không tìm hoặc không thể thực thi program unit được gọi |
| `ORA-04098` | Trigger đang invalid và re-validation thất bại |
| `ORA-06550` | Lỗi biên dịch/phân tích PL/SQL được báo tại một vị trí trong block |

Thông báo thực tế có thể kèm nhiều mã lỗi trong một stack. Đọc **cả văn bản, loại object, dòng/vị trí và nguyên nhân phía trước** trước khi kết luận.

## 12. Đọc object status trong môi trường lớn

Khi hệ thống có nhiều schema, câu SQL chỉ đếm số lượng INVALID là điểm khởi đầu, chưa phải chẩn đoán:

```sql
SELECT owner, object_type, COUNT(*) AS invalid_count
FROM all_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY invalid_count DESC, owner, object_type;
```

`ALL_OBJECTS` phản ánh phạm vi quyền hiện tại. DBA muốn tổng hợp trên toàn database/container phù hợp có thể sử dụng `DBA_OBJECTS`, và với CDB cần xác định phạm vi container/`CDB_*` nếu quản trị nhiều PDB. Đừng gộp các PDB chỉ bằng `OWNER` và `OBJECT_NAME` vì cùng tên có thể xuất hiện ở nhiều PDB.

Một bản ghi sự cố nên có:

| Trường | Vì sao cần |
| --- | --- |
| Database/PDB/edition và timestamp | Xác định đúng nơi có lỗi |
| Owner, object name, object type | Phân biệt package spec/body hoặc object trùng tên |
| STATUS trước/sau | Biết việc compile có khôi phục được object không |
| Source version/deployment ID | Đối chiếu với Git và pipeline triển khai |
| Diagnostic line/position/text | Chỉ rõ lỗi compiler |
| Referenced object vừa đổi | Tìm nguyên nhân invalidation |
| Người/chương trình có ảnh hưởng | Đánh giá mức độ ưu tiên và cửa sổ triển khai |

### 12.1. Khi nào không nên tự sửa ngay?

- Object ở production dùng chung bởi nhiều dịch vụ.
- Package specification phải thay đổi chữ ký public API.
- Trigger đang tham gia vào thao tác DML nghiệp vụ hoặc audit.
- INVALID xuất hiện sau migration đang chạy hoặc một thay đổi quyền bảo mật.
- Các object thuộc schema hệ thống/Oracle-maintained đang được DBA xử lý theo cơ chế riêng.

Khi đó, ưu tiên **đọc metadata và báo nguyên nhân có bằng chứng**. Sửa source/recompile ở production nên đi cùng quy trình triển khai, đánh giá phụ thuộc và rollback phù hợp.

## 13. Bài tập vận dụng

### Bài tập 1 — Tìm mã thực tế của một function

Giả sử trong schema hiện tại có function `CALC_DISCOUNT`. Hãy viết câu `SELECT` lấy `NAME`, `TYPE`, `LINE`, `TEXT` từ `USER_SOURCE`, lọc `TYPE='FUNCTION'` và sắp xếp tăng theo `LINE`. Sau đó xác định biến nào trong function được khai báo ở phần đầu và thao tác nào diễn ra trong `BEGIN ... END`.

### Bài tập 2 — Vì sao function VALID nhưng ứng dụng lỗi?

Một function tra cứu giá bằng `SELECT price INTO v_price FROM products WHERE id = p_id`. `USER_OBJECTS` báo `VALID`, nhưng gọi với mã sản phẩm không tồn tại gây `NO_DATA_FOUND`. Giải thích vì sao `USER_ERRORS` không nhất thiết có hàng và nên điều tra ở lớp dữ liệu/exception handling.

### Bài tập 3 — Package spec VALID, body INVALID

Giả sử `USER_OBJECTS` trả:

```text
OBJECT_NAME      OBJECT_TYPE     STATUS
---------------  --------------  -------
PAYMENT_PKG      PACKAGE         VALID
PAYMENT_PKG      PACKAGE BODY    INVALID
```

Hãy viết câu truy vấn `USER_ERRORS` lọc `NAME='PAYMENT_PKG'` và `TYPE='PACKAGE BODY'`; sau đó chọn đúng câu `SHOW ERRORS PACKAGE BODY PAYMENT_PKG`. Giải thích vì sao việc compile specification trước không nhất thiết sửa được lỗi ở body.

### Bài tập 4 — INVALID sau khi bảng thay đổi

Một package body dùng cột `ORDER_TOTAL` của `ORDERS`. Sau migration, cột này đổi tên. Kiểm tra nào cần thực hiện trước khi chạy compile lại? Hãy nêu ít nhất bốn điểm: trạng thái, source, lỗi, dependency và phiên bản schema đang triển khai. Giải thích vì sao `ALTER PACKAGE ... COMPILE BODY` không tự sửa tên cột cũ trong source.

### Bài tập 5 — Phân biệt warning và error

Một object có hàng `USER_ERRORS.ATTRIBUTE='WARNING'` nhưng `USER_OBJECTS.STATUS='VALID'`. Điều này có mâu thuẫn không? Hãy giải thích ý nghĩa của PL/SQL compiler warnings và tại sao phải lọc `ATTRIBUTE` khi thống kê object thực sự bị lỗi.

## 14. Quy trình tra cứu ngắn gọn để áp dụng

```text
1. Xác định database / PDB / USER / CURRENT_SCHEMA
                         │
                         ▼
2. Xác định owner + object name + object type
                         │
                         ▼
3. USER_OBJECTS / ALL_OBJECTS → VALID hay INVALID?
                         │
                         ▼
4. USER_SOURCE / ALL_SOURCE → source đang lưu là gì?
                         │
                         ▼
5. USER_ERRORS / ALL_ERRORS → error hay warning? dòng nào?
                         │
                         ▼
6. *_DEPENDENCIES + grants → object nào đổi hoặc thiếu quyền?
                         │
                         ▼
7. Sửa nguyên nhân / compile đúng object type
                         │
                         ▼
8. Đọc lại STATUS + ERRORS, thử gọi trên môi trường phù hợp
```

Trong Oracle, **`USER_SOURCE` trả lời “database đang lưu mã gì”, `USER_ERRORS` trả lời “compiler đang báo gì”, `USER_OBJECTS` trả lời “object được đánh dấu VALID hay INVALID”, còn `USER_DEPENDENCIES` gợi ý “những object nào có thể tác động đến nó”**. Kết hợp bốn góc nhìn này với thông tin schema/PDB và quyền truy cập sẽ giúp bạn phân biệt lỗi triển khai, lỗi biên dịch, invalidation và lỗi runtime một cách có hệ thống.
