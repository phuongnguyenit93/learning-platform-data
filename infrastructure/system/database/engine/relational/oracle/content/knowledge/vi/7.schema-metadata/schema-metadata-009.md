# Trích xuất DDL bằng `DBMS_METADATA` trong Oracle Database

## 1. Mục đích: lấy lại định nghĩa đối tượng từ data dictionary

Khi một bảng, view, index, sequence hoặc PL/SQL package đã tồn tại trong Oracle Database, người quản trị có thể cần lấy lại câu lệnh tạo đối tượng để review, lưu vào Git, so sánh hai môi trường, chuẩn bị migration hoặc phân tích cấu trúc schema. Oracle cung cấp package **`DBMS_METADATA`** để đọc metadata từ data dictionary và chuyển thành **DDL (Data Definition Language)**, chẳng hạn `CREATE TABLE`, `CREATE VIEW`, `CREATE INDEX` hay `CREATE OR REPLACE PACKAGE`.

Ví dụ, database đang có bảng `APP.ORDERS` nhưng nhóm phát triển không còn file SQL tạo bảng. Truy vấn:

```sql
SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP')
FROM   DUAL;
```

có thể trả về DDL tương đương định nghĩa hiện tại của bảng, với các cột, kiểu dữ liệu, constraint và thuộc tính khác tùy cấu hình transform. Đây là **metadata tại thời điểm truy vấn**, không phải bản chụp mọi thao tác DDL đã từng diễn ra.

**Ba giới hạn phải hiểu ngay:**

1. **DDL không phải dữ liệu bảng**: `CREATE TABLE` không chứa hàng triệu row hiện có. Muốn xuất cả dữ liệu cần cơ chế khác như Data Pump, backup hoặc pipeline dữ liệu.
2. **DDL một object không phải toàn bộ schema**: chỉ `GET_DDL('TABLE', ...)` chưa chắc có tất cả index độc lập, trigger, comment, object grant, package, job và dependency cần để tái dựng ứng dụng.
3. **Đọc DDL không đồng nghĩa thực thi DDL**: `GET_DDL` chỉ trả text; chạy script trích xuất trên môi trường đích là hành động riêng có thể thay đổi database và cần review.

> Nội dung tập trung vào Oracle Database 19c và cơ chế `DBMS_METADATA` được duy trì ở các release mới. Tên schema/đối tượng trong ví dụ là giả định. Trước khi dùng trên hệ thống thật, chọn đúng PDB, quyền truy cập và tài liệu Oracle tương ứng với release đang chạy.

## 2. Mô hình hoạt động của `DBMS_METADATA`

Package có thể trả metadata dưới dạng XML, SXML hoặc DDL. Khi người dùng chọn DDL, Oracle đọc metadata được phép truy cập, áp dụng các **transform** để sinh ra câu lệnh SQL tương ứng.

```text
                      Oracle data dictionary
                        (schema metadata)
                                │
                                ▼
                    DBMS_METADATA retrieval
                    ┌──────────────────────┐
                    │ Object type          │
                    │ Owner / object name  │
                    │ Privilege filtering  │
                    └──────────┬───────────┘
                               │
                               ▼
                     XML metadata model
                               │
                     ┌─────────┴──────────┐
                     │ Transform 'DDL'    │
                     │ PRETTY / STORAGE   │
                     │ TABLESPACE / ...   │
                     └─────────┬──────────┘
                               │
                               ▼
                        CLOB chứa DDL
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
       SQL*Plus / SQLcl                    PL/SQL / ứng dụng
       hiển thị / SPOOL                     nhận đủ CLOB
              │                                 │
              └────────────────┬────────────────┘
                               ▼
                    Review → lưu nguồn → kiểm tra
                    dependency → quyết định deploy
```

Trong mô hình này, **`GET_DDL` là lối vào ngắn** cho một đối tượng đã biết tên. Khi cần duyệt nhiều đối tượng, API mở ngữ cảnh `OPEN`, lọc bằng `SET_FILTER`, thêm transform bằng `ADD_TRANSFORM`, lần lượt `FETCH_CLOB` rồi `CLOSE`.

### 2.1. Ba loại metadata cần phân biệt

| Nhóm | Ví dụ | Hàm thường dùng |
| --- | --- | --- |
| **Named object** | Bảng `APP.ORDERS`, view `APP.V_ORDERS`, package `APP.ORDER_API` | `GET_DDL` |
| **Dependent object** | Index, object grant hoặc comment phụ thuộc vào bảng gốc | `GET_DEPENDENT_DDL` |
| **Granted object** | System privilege, role grant được cấp cho một user/role | `GET_GRANTED_DDL` |

Oracle còn có loại **heterogeneous collection** như `SCHEMA_EXPORT`, `TABLE_EXPORT`, `DATABASE_EXPORT`. Đây là tập nhiều kiểu đối tượng, sử dụng giao diện `OPEN`/`FETCH_*` hoặc công cụ Data Pump; không truyền `SCHEMA_EXPORT` cho `GET_DDL` với kỳ vọng lấy một schema hoàn chỉnh trong một lần gọi.

## 3. Chuẩn bị kết nối, quyền và phạm vi schema

### 3.1. Đang ở PDB nào?

Trong kiến trúc multitenant, cùng tên `APP.ORDERS` có thể tồn tại trong nhiều PDB. `DBMS_METADATA` hoạt động theo **ngữ cảnh container của session** và quyền khả dụng. Trước khi xuất, xác nhận database/service/container:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME')     AS con_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM   dual;
```

Ví dụ một kết quả:

```text
CON_NAME    SERVICE_NAME             CURRENT_SCHEMA  SESSION_USER
----------  -----------------------  --------------  ------------
SALES_PDB   sales_app.example.com    APP             APP
```

Nếu client kết nối nhầm `CDB$ROOT`, DDL truy xuất ở root không tự động đại diện cho object cùng tên trong `SALES_PDB`. Không sửa schema hoặc dùng `ALTER SESSION SET CONTAINER` tùy tiện để ép lấy metadata xuyên tenant; dùng service đúng PDB và tài khoản có quyền thích hợp.

### 3.2. Quyền đọc metadata

Theo mô hình bảo mật của `DBMS_METADATA` trong Oracle 19c:

- **User thông thường** được lấy metadata đối tượng của chính mình. Họ cũng có thể lấy một số thông tin như public synonym hoặc grant liên quan đến mình theo quy tắc của package.
- **User được Oracle coi là privileged**, điển hình kết nối với `SYS` hoặc có role `SELECT_CATALOG_ROLE`, có thể truy xuất metadata thuộc các schema khác theo phạm vi quyền tương ứng.
- Chỉ được `SELECT` trên bảng của schema khác **không có nghĩa** được đọc toàn bộ `CREATE TABLE` thông qua `GET_DDL` của chủ sở hữu đó.
- Khi yêu cầu đối tượng không được phép xem, API có thể trả **không có đối tượng phù hợp**, trông giống object không tồn tại; lỗi kiểu `ORA-31603` cần được xét cùng vấn đề quyền và container.

**Ranh giới PL/SQL quan trọng:** Trong procedure/function/package **definer's rights** (`AUTHID DEFINER`, mặc định), các role thường không có hiệu lực. Một account chạy `GET_DDL` tương tác được nhờ `SELECT_CATALOG_ROLE` vẫn có thể thất bại khi chuyển cùng logic vào stored procedure định nghĩa mặc định. Nếu cần dùng quyền của người gọi, thiết kế **invoker's rights (`AUTHID CURRENT_USER`)** với các quyền phù hợp; không khắc phục bằng cách mặc định cấp `DBA` hoặc chạy mọi extraction bằng `SYS`.

### 3.3. Xác minh object trước khi lấy DDL

```sql
-- Trong schema đang kết nối: object của chủ sở hữu hiện tại.
SELECT object_name, object_type, status
FROM   user_objects
WHERE  object_name = 'ORDERS'
ORDER BY object_type;

-- Nếu được quyền xem schema khác trong đúng PDB:
SELECT owner, object_name, object_type, status
FROM   all_objects
WHERE  owner = 'APP'
AND    object_name = 'ORDERS'
ORDER BY object_type;
```

`ALL_OBJECTS` hiển thị metadata theo quyền view/đối tượng; **có row trong `ALL_OBJECTS` không bảo đảm có quyền lấy DDL bằng `DBMS_METADATA`**. Tên đối tượng và owner thông thường được Oracle lưu chữ hoa nếu tạo **không dùng quoted identifier**. Đối tượng được tạo như `"OrderItems"` giữ đúng chữ hoa/chữ thường; đối số `name`/`schema` phải khớp tên thực.

## 4. `GET_DDL`: câu truy vấn đầu tiên cần biết

### 4.1. Chữ ký hàm

```text
DBMS_METADATA.GET_DDL(
    object_type IN VARCHAR2,
    name        IN VARCHAR2,
    schema      IN VARCHAR2 DEFAULT NULL,
    version     IN VARCHAR2 DEFAULT 'COMPATIBLE',
    model       IN VARCHAR2 DEFAULT 'ORACLE',
    transform   IN VARCHAR2 DEFAULT 'DDL'
) RETURN CLOB;
```

| Tham số | Ý nghĩa | Giá trị ví dụ |
| --- | --- | --- |
| `object_type` | Loại object trong metadata API, **không luôn trùng nguyên văn `OBJECT_TYPE` của `USER_OBJECTS`** | `TABLE`, `VIEW`, `INDEX`, `PACKAGE_SPEC`, `PACKAGE_BODY` |
| `name` | Tên object theo đúng dạng lưu trong dictionary | `ORDERS`, `OrderItems` |
| `schema` | Chủ sở hữu, mặc định current user theo API | `APP` |
| `version` | Cách thể hiện phiên bản metadata, mặc định theo database compatibility | `COMPATIBLE`, `LATEST` |
| `model` | Metadata model; Oracle hỗ trợ `ORACLE` | `ORACLE` |
| `transform` | Chuyển XML metadata sang DDL | `DDL` |

Giá trị trả về là **CLOB**; công cụ client phải hiển thị hoặc ghi đầy đủ CLOB. Không dùng `DBMS_LOB.SUBSTR(..., 4000, 1)` làm phương pháp export cuối cùng vì nó chỉ lấy **một đoạn**.

### 4.2. Trích xuất các object phổ biến

```sql
-- Một bảng với owner rõ ràng.
SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP') AS ddl
FROM   dual;

-- Index tạo độc lập.
SELECT DBMS_METADATA.GET_DDL('INDEX', 'IDX_ORDERS_CREATED_AT', 'APP') AS ddl
FROM   dual;

-- View.
SELECT DBMS_METADATA.GET_DDL('VIEW', 'V_ORDER_TOTAL', 'APP') AS ddl
FROM   dual;

-- Sequence.
SELECT DBMS_METADATA.GET_DDL('SEQUENCE', 'SEQ_ORDER_ID', 'APP') AS ddl
FROM   dual;

-- Trigger.
SELECT DBMS_METADATA.GET_DDL('TRIGGER', 'TRG_ORDER_AUDIT', 'APP') AS ddl
FROM   dual;

-- Stored procedure hoặc function.
SELECT DBMS_METADATA.GET_DDL('PROCEDURE', 'RECALCULATE_ORDER', 'APP') AS ddl
FROM   dual;

SELECT DBMS_METADATA.GET_DDL('FUNCTION', 'CALC_TAX', 'APP') AS ddl
FROM   dual;

-- Tách package specification và package body.
SELECT DBMS_METADATA.GET_DDL('PACKAGE_SPEC', 'ORDER_API', 'APP') AS ddl
FROM   dual;

SELECT DBMS_METADATA.GET_DDL('PACKAGE_BODY', 'ORDER_API', 'APP') AS ddl
FROM   dual;
```

Tất cả tên ở trên đều là ví dụ: chỉ chạy những câu query có object thực sự tồn tại và bạn được phép truy cập. `PACKAGE` là một object type do API hỗ trợ; theo tài liệu Oracle 19c, nó có thể lấy cả specification và body theo cấu hình mặc định. Khi lưu source và build tự động, dùng `PACKAGE_SPEC`/`PACKAGE_BODY` để kiểm soát tách file và thứ tự thường rõ ràng hơn.

### 4.3. Quoted identifier và chữ hoa/chữ thường

Giả sử bảng được tạo như sau trong schema có quyền:

```sql
CREATE TABLE "OrderItems" (
    "ItemId" NUMBER PRIMARY KEY,
    "Qty"    NUMBER NOT NULL
);
```

Tên đã được Oracle lưu là **`OrderItems`**, không phải `ORDERITEMS`. Khi gọi `GET_DDL`, truyền chuỗi tên chính xác:

```sql
SELECT DBMS_METADATA.GET_DDL('TABLE', 'OrderItems')
FROM   dual;
```

`name` là giá trị chuỗi lọc tên object, không phải văn bản câu `SELECT` đã chứa dấu nháy kép của SQL identifier. Do đó, thường không đặt cặp dấu `"` bên trong đối số `name` trừ khi dấu nháy kép thực sự là ký tự trong tên cần tìm. Với object tên chuẩn không quoted, dùng chữ hoa.

### 4.4. `GET_DDL('USER', ...)` và đối tượng hệ thống

`DBMS_METADATA` cũng hỗ trợ những object type cấp database như `USER`, `ROLE`, `TABLESPACE`, tùy quyền. Tuy nhiên, DDL của user có thể chứa **thuộc tính xác thực, account settings hoặc thông tin quản trị nhạy cảm**; DDL tablespace có thể chứa đường dẫn datafile và đặc điểm storage của một môi trường. Không đưa các file này vào repository công khai hoặc chạy lại nguyên văn trên database khác mà không đánh giá, làm sạch thông tin và kiểm tra quyền.

## 5. Hiển thị CLOB đúng cách trong SQL*Plus và SQLcl

Một lỗi thường gặp là `GET_DDL` đã tạo đủ nội dung nhưng client **chỉ hiện vài nghìn ký tự**, khiến người học tưởng metadata bị thiếu.

### 5.1. Thiết lập hiển thị

```sql
-- SQL*Plus / SQLcl, trước khi gọi GET_DDL.
SET LONG 2000000
SET LONGCHUNKSIZE 32767
SET PAGESIZE 0
SET LINESIZE 32767
SET HEADING OFF
SET FEEDBACK OFF
SET TRIMSPOOL ON

SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP')
FROM   dual;
```

Giải thích:

- `SET LONG` giới hạn độ dài giá trị kiểu LONG/CLOB mà SQL*Plus hiển thị; tăng đủ lớn cho object phức tạp.
- `SET LONGCHUNKSIZE` điều chỉnh kích cỡ từng phần client lấy dữ liệu; không làm thay đổi nội dung metadata.
- `PAGESIZE 0`, `HEADING OFF`, `FEEDBACK OFF` tránh header, ngắt trang và câu thông báo lẫn vào script SQL.
- `LINESIZE` và `TRIMSPOOL` hỗ trợ xuất text có bố cục ổn định; không tự chứng minh tất cả ký tự CLOB đã được xuất.

Đây là **các lệnh client**, không phải SQL thuộc database. Công cụ khác như SQL Developer, DBeaver, JDBC hay IDE có cài đặt hiển thị/download CLOB riêng. Nếu kết quả trong grid bị rút ngắn, hãy dùng chức năng lưu CLOB đầy đủ hoặc dùng API đọc stream.

### 5.2. Ghi ra file bằng `SPOOL`

Ví dụ script chạy trong SQL*Plus/SQLcl, với đối tượng `APP.ORDERS` thực sự tồn tại:

```sql
SET ECHO OFF
SET VERIFY OFF
SET HEADING OFF
SET FEEDBACK OFF
SET PAGESIZE 0
SET LONG 2000000
SET LONGCHUNKSIZE 32767
SET LINESIZE 32767
SET TRIMSPOOL ON

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);

SPOOL orders_table.sql
SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP') FROM dual;
SPOOL OFF

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
```

`SPOOL` ghi kết quả text vào file ở **máy đang chạy SQL*Plus/SQLcl**, không tự ghi vào thư mục datafile của server. Đường dẫn và quyền tạo file phụ thuộc môi trường client. Sau khi xuất, đọc file thật để xác nhận không có prompt/header, nội dung không bị cắt, script có dấu kết thúc phù hợp và encoding đúng trước khi commit vào Git.

**Cẩn thận với độ dài:** Nếu một object chứa package body nhiều megabyte, đặt `SET LONG` đủ cao hoặc dùng một cơ chế export CLOB có streaming. `SET LINESIZE` không giải quyết vấn đề cắt dữ liệu do `SET LONG` quá nhỏ.

## 6. Điều khiển DDL bằng `SESSION_TRANSFORM`

DDL Oracle phát sinh có thể rất dài do `PCTFREE`, `INITRANS`, `STORAGE`, `TABLESPACE`, `LOGGING` và nhiều thuộc tính vật lý. Khi lưu schema để review hoặc chuyển giữa môi trường có tên tablespace khác nhau, cần quyết định **giữ nguyên physical details** hay **ẩn bớt chi tiết**.

Oracle cung cấp `DBMS_METADATA.SET_TRANSFORM_PARAM` với handle **`DBMS_METADATA.SESSION_TRANSFORM`** để thay đổi cách `GET_DDL`, `GET_DEPENDENT_DDL`, `GET_GRANTED_DDL` trong **session hiện tại** xuất DDL.

### 6.1. Bỏ các thuộc tính vật lý khi muốn script gọn

```sql
BEGIN
  DBMS_METADATA.SET_TRANSFORM_PARAM(
    DBMS_METADATA.SESSION_TRANSFORM, 'SEGMENT_ATTRIBUTES', FALSE);

  DBMS_METADATA.SET_TRANSFORM_PARAM(
    DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);

  DBMS_METADATA.SET_TRANSFORM_PARAM(
    DBMS_METADATA.SESSION_TRANSFORM, 'PRETTY', TRUE);
END;
/

SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP')
FROM   dual;

-- Trả session về trạng thái mặc định sau khi dùng.
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
```

`SEGMENT_ATTRIBUTES=FALSE` loại bỏ các thuộc tính vật lý thuộc nhóm segment, bao gồm những phần như storage/tablespace/logging theo mô tả của transform. Nếu **muốn chỉ bỏ `STORAGE` mà vẫn giữ `TABLESPACE`**, dùng `STORAGE=FALSE` và để `SEGMENT_ATTRIBUTES` ở trạng thái phù hợp. Khi `SEGMENT_ATTRIBUTES=FALSE`, `STORAGE` và `TABLESPACE` được Oracle bỏ qua vì chúng đã thuộc nhóm bị tắt.

### 6.2. Những transform quan trọng

| Tham số | Phạm vi | Khi đặt `TRUE`/`FALSE` | Lưu ý |
| --- | --- | --- | --- |
| `PRETTY` | Nhiều object type | Có/không format thụt dòng | Mặc định `TRUE` |
| `SQLTERMINATOR` | Nhiều object type | Có/không thêm `;` hoặc `/` | Mặc định `FALSE`; hữu ích cho file SQL |
| `SEGMENT_ATTRIBUTES` | Table, index và một số object khác | Có/không gồm physical, storage, tablespace, logging | Cắt giảm chi tiết có thể đổi semantics storage |
| `STORAGE` | Table/index và nhóm hỗ trợ | Có/không xuất storage clause | Bị bỏ qua nếu `SEGMENT_ATTRIBUTES=FALSE` |
| `TABLESPACE` | Table/index và nhóm hỗ trợ | Có/không xuất tablespace clause | Bị bỏ qua nếu `SEGMENT_ATTRIBUTES=FALSE` |
| `CONSTRAINTS` | Table | Có/không xuất non-referential constraints | Tắt có thể làm mất `PRIMARY KEY`, `UNIQUE`, `CHECK` trong DDL bảng |
| `REF_CONSTRAINTS` | Table | Có/không xuất foreign key | Đừng tắt nếu mục đích tái tạo toàn bộ ràng buộc |
| `CONSTRAINTS_AS_ALTER` | Table | Xuất constraint bằng `ALTER TABLE` khi được hỗ trợ | Cần `CONSTRAINTS=TRUE` |
| `PARTITIONING` | Table, index | Có/không xuất partitioning clauses | Tắt sẽ thay đổi cấu trúc logic/vật lý và có thể phá mục tiêu migration |
| `SPECIFICATION`, `BODY` | Package/type | Điều khiển phần spec/body được xuất | Có thể dùng object type riêng cho spec/body |
| `DEFAULT` | Tất cả transform có hỗ trợ | Với `TRUE`, khôi phục mặc định transform | Nên reset sau phiên xuất |

Ví dụ chỉ ẩn `STORAGE` mà vẫn có tên tablespace:

```sql
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'STORAGE', FALSE);

SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP')
FROM   dual;

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
```

### 6.3. Session transform tồn tại đến khi reset

`SESSION_TRANSFORM` thuộc **session database**. Nếu một script đặt `CONSTRAINTS=FALSE` rồi không reset, các lệnh `GET_DDL` tiếp theo trong cùng session có thể vẫn không xuất constraint. Với connection pool, việc tái sử dụng cùng physical session còn làm lỗi này khó nhận diện hơn.

Vì vậy, một workflow trích xuất có tính lặp lại nên **set các transform rõ ràng trước khi đọc**, **reset về `DEFAULT` sau khi hoàn tất** và tránh dùng những transform thay đổi ngữ nghĩa khi mục đích là sao lưu DDL đầy đủ.

## 7. `GET_DDL` của một bảng còn thiếu những gì?

Một schema chứa quan hệ giữa nhiều object. `CREATE TABLE` của `APP.ORDERS` có thể có các cột, dữ liệu kiểu và những constraint được bật trong transform; nhưng để tái tạo đầy đủ ứng dụng, còn cần xem:

```text
APP.ORDERS
  ├── CREATE TABLE + column definitions
  ├── constraints (PK, UNIQUE, CHECK, FK)
  ├── indexes (đặc biệt các index tạo riêng)
  ├── triggers
  ├── column/table comments
  ├── object grants / synonyms
  ├── sequences, procedures, packages và views tham chiếu tới bảng
  └── metadata liên quan như policies, jobs, materialized views, types...
```

**Không gom tất cả thành một lệnh `GET_DDL('TABLE')`.** Một số constraint có thể đã được in cùng DDL bảng theo mặc định; object phụ thuộc còn lại thường phải xuất riêng qua `GET_DDL`, `GET_DEPENDENT_DDL`, `GET_GRANTED_DDL` hoặc một workflow xuất toàn schema có nhận biết dependency.

### 7.1. `GET_DEPENDENT_DDL`: metadata phụ thuộc đối tượng gốc

Chữ ký rút gọn:

```text
DBMS_METADATA.GET_DEPENDENT_DDL(
    object_type, base_object_name, base_object_schema,
    version, model, transform, object_count
) RETURN CLOB;
```

Ví dụ lấy DDL object grants được cấp **trên bảng** `APP.ORDERS`:

```sql
SELECT DBMS_METADATA.GET_DEPENDENT_DDL(
           'OBJECT_GRANT', 'ORDERS', 'APP') AS ddl
FROM   dual;
```

Ví dụ lấy các index có metadata phụ thuộc bảng:

```sql
SELECT DBMS_METADATA.GET_DEPENDENT_DDL(
           'INDEX', 'ORDERS', 'APP') AS ddl
FROM   dual;
```

Những câu này có thể trả **nhiều câu DDL trong một CLOB**. Nếu không có object thuộc loại cần tìm hoặc tài khoản không được xem, sẽ có trường hợp báo lỗi object-not-found. Hãy đối chiếu dictionary như `ALL_INDEXES`, `ALL_TAB_PRIVS`, `ALL_TRIGGERS` theo quyền trước khi kết luận.

**Chú ý duplicate:** Khi `GET_DDL('TABLE')` đã gồm định nghĩa một primary key/unique constraint và có index Oracle tạo cho constraint đó, không nên phát lại mọi câu `CREATE INDEX` không phân biệt nguồn gốc, vì có thể trùng hoặc xung đột. Phải quyết định cách tái tạo constraint/index nhất quán.

### 7.2. `GET_GRANTED_DDL`: quyền cấp cho user/role

`GET_GRANTED_DDL` nhận **grantee** là người/role nhận quyền, không phải tên table đang được cấp:

```sql
-- System privileges cấp cho user APP.
SELECT DBMS_METADATA.GET_GRANTED_DDL('SYSTEM_GRANT', 'APP')
FROM   dual;

-- Các role được cấp cho APP.
SELECT DBMS_METADATA.GET_GRANTED_DDL('ROLE_GRANT', 'APP')
FROM   dual;

-- Object privileges mà APP là grantee.
SELECT DBMS_METADATA.GET_GRANTED_DDL('OBJECT_GRANT', 'APP')
FROM   dual;
```

Phân biệt hai cách hỏi:

| Câu hỏi | API phù hợp |
| --- | --- |
| Ai có quyền trên **bảng `APP.ORDERS`**? | `GET_DEPENDENT_DDL('OBJECT_GRANT','ORDERS','APP')` |
| Những object grants nào đã được cấp **cho user `REPORT_USER`**? | `GET_GRANTED_DDL('OBJECT_GRANT','REPORT_USER')` |
| Những system privileges nào cấp cho `REPORT_USER`? | `GET_GRANTED_DDL('SYSTEM_GRANT','REPORT_USER')` |
| `REPORT_USER` được cấp những roles nào? | `GET_GRANTED_DDL('ROLE_GRANT','REPORT_USER')` |

Khi export user hoặc phục dựng quyền, cần xét **default role**, profile, quota, system grants, object grants, quyền common/local trong CDB/PDB và các chính sách bảo mật khác. Một `CREATE USER` riêng không đại diện cho tất cả quyền đã cấp.

## 8. Trích xuất nhiều bảng trong schema bằng SQL

Nếu mục tiêu chỉ là lấy nhanh DDL của tất cả bảng ứng dụng trong schema hiện tại, có thể query dictionary và gọi `GET_DDL` cho từng bảng.

```sql
-- Trong schema APP, không cần quyền metadata của schema khác.
SET LONG 2000000
SET PAGESIZE 0

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);

SELECT DBMS_METADATA.GET_DDL('TABLE', t.table_name)
FROM   user_all_tables t
WHERE  t.nested = 'NO'
AND    (t.iot_type IS NULL OR t.iot_type = 'IOT')
ORDER  BY t.table_name;

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
```

Oracle dùng điều kiện **`NESTED='NO'`** và **`IOT_TYPE IS NULL OR IOT_TYPE='IOT'`** trong ví dụ chính thức nhằm tránh gọi `GET_DDL` cho một số đối tượng nội bộ/phần phụ của bảng. Nếu schema có bảng external, temporary, partition, nested collections, XMLType hoặc các object đặc biệt khác, bạn cần xác định đúng danh mục sẽ export thay vì giả định bộ lọc trên bao quát mọi trường hợp.

Ví dụ lấy DDL các view thuộc user:

```sql
SELECT DBMS_METADATA.GET_DDL('VIEW', view_name)
FROM   user_views
ORDER  BY view_name;
```

Không gộp vô điều kiện `GET_DDL` của nhiều loại object theo `USER_OBJECTS.OBJECT_TYPE`: tên loại object mà `DBMS_METADATA` nhận có những trường hợp khác dictionary (`PACKAGE BODY` so với `PACKAGE_BODY`), và một số row dictionary là object nội bộ không thích hợp để tạo lại riêng.

### 8.1. Tự động export DDL cần nghĩ đến dependency

Giả sử view `V_ORDER_REPORT` phụ thuộc bảng `ORDERS`, trigger gọi package `ORDER_API`, package dùng type `ORDER_ROW_TYPE`. Nếu xuất file theo thứ tự alphabet rồi chạy lần lượt, nhiều statement có thể lỗi hoặc tạo object **INVALID** tạm thời.

Thứ tự triển khai điển hình cần đánh giá:

1. Users/roles, tablespaces, schema-level prerequisites khi được phép quản lý.
2. Types, sequences, tables và các đối tượng nền tảng.
3. Indexes/constraints và các dependent objects theo thiết kế.
4. Views, packages/procedures/functions/triggers/materialized views theo dependency.
5. Grants, synonyms, jobs/policies và các đối tượng vận hành khác.
6. Recompile và xác nhận `USER_OBJECTS.STATUS`, constraint, indexes, privileges, invalid objects.

Đây là **định hướng**, không phải thứ tự chuẩn cho mọi schema: type, view, FK và PL/SQL có thể có dependency vòng. Với schema lớn, cân nhắc **Data Pump** hoặc giao diện `OPEN('SCHEMA_EXPORT')` thay vì tự viết script chỉ dựa vào alphabet.

## 9. API nhiều object: `OPEN` → `SET_FILTER` → `ADD_TRANSFORM` → `FETCH_CLOB` → `CLOSE`

Khi cần chương trình hóa việc lấy DDL, `DBMS_METADATA` hỗ trợ handle-based API. Một `OPEN` tạo **retrieval context**, có thể lọc theo schema/name, thêm transform rồi lấy từng CLOB.

```text
h = OPEN('TABLE')
  │
  ├── SET_FILTER(h, 'SCHEMA', 'APP')
  ├── SET_FILTER(h, 'NAME', 'ORDERS') [tùy chọn]
  ├── t = ADD_TRANSFORM(h, 'DDL')
  └── SET_TRANSFORM_PARAM(t, 'SEGMENT_ATTRIBUTES', FALSE)
         │
         ▼
       FETCH_CLOB(h) ── CLOB object #1
         │
         ▼
       FETCH_CLOB(h) ── CLOB object #2 ...
         │
         ▼
       FETCH_CLOB(h) ── NULL = hết object
         │
         ▼
          CLOSE(h)
```

### 9.1. Ví dụ PL/SQL chạy được: duyệt metadata và đếm kích cỡ CLOB

Đoạn sau **chỉ đọc metadata và in số ký tự** của từng DDL, nhằm chứng minh API duyệt hết object. Nó chưa xuất file; làm vậy tránh vô tình làm hỏng DDL khi cắt CLOB qua `DBMS_OUTPUT`:

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
  l_handle       NUMBER;
  l_transform    NUMBER;
  l_ddl          CLOB;
  l_count        PLS_INTEGER := 0;
BEGIN
  l_handle := DBMS_METADATA.OPEN('TABLE');
  DBMS_METADATA.SET_FILTER(l_handle, 'SCHEMA', 'APP');

  l_transform := DBMS_METADATA.ADD_TRANSFORM(l_handle, 'DDL');
  DBMS_METADATA.SET_TRANSFORM_PARAM(
    l_transform, 'SQLTERMINATOR', TRUE);
  DBMS_METADATA.SET_TRANSFORM_PARAM(
    l_transform, 'SEGMENT_ATTRIBUTES', FALSE);

  LOOP
    l_ddl := DBMS_METADATA.FETCH_CLOB(l_handle);
    EXIT WHEN l_ddl IS NULL;

    l_count := l_count + 1;
    DBMS_OUTPUT.PUT_LINE(
      'Object #' || l_count || ': ' || DBMS_LOB.GETLENGTH(l_ddl) || ' characters');

    -- Trong ứng dụng thực, lưu toàn bộ l_ddl theo cơ chế CLOB stream.
    -- Không chỉ lưu DBMS_LOB.SUBSTR(l_ddl, 4000, 1).
  END LOOP;

  DBMS_METADATA.CLOSE(l_handle);
  l_handle := NULL;
  DBMS_OUTPUT.PUT_LINE('Total objects: ' || l_count);
EXCEPTION
  WHEN OTHERS THEN
    IF l_handle IS NOT NULL THEN
      DBMS_METADATA.CLOSE(l_handle);
    END IF;
    RAISE;
END;
/
```

Thay `APP` bằng schema mà tài khoản có quyền xem trước khi chạy. `OPEN('TABLE')` chọn loại object là bảng; `SET_FILTER` áp điều kiện; `ADD_TRANSFORM` chuyển metadata XML sang DDL; `FETCH_CLOB` nhận từng object; `CLOSE` giải phóng ngữ cảnh.

**Hai loại handle khác nhau:** `l_handle` từ `OPEN` dùng cho `SET_FILTER`, `FETCH_CLOB`, `CLOSE`. `l_transform` từ `ADD_TRANSFORM` dùng cho `SET_TRANSFORM_PARAM`; truyền nhầm `l_handle` như transform handle có thể gây lỗi. `SESSION_TRANSFORM` dùng cho các lời gọi `GET_*`, còn transform vừa được thêm cho `OPEN` được điều khiển trực tiếp qua `l_transform` (trừ trường hợp bật kế thừa tham số theo quy tắc `INHERIT`).

### 9.2. Khi nào dùng `SCHEMA_EXPORT`?

Đối với một schema đầy đủ, `OPEN('SCHEMA_EXPORT')` tạo ngữ cảnh **nhiều loại đối tượng**, có thể phát DDL theo thứ tự nhóm object mà Oracle thiết kế cho xuất schema. Oracle Database Utilities có ví dụ `FETCH_CLOB` rồi lưu toàn bộ CLOB vào một bảng staging để khảo sát.

```sql
-- Các lệnh mấu chốt bên trong chương trình PL/SQL;
-- chỉ minh họa retrieval pipeline, không phải một script độc lập.
l_handle := DBMS_METADATA.OPEN('SCHEMA_EXPORT');
DBMS_METADATA.SET_FILTER(l_handle, 'SCHEMA', 'APP');
l_transform := DBMS_METADATA.ADD_TRANSFORM(l_handle, 'DDL');

-- Lặp DBMS_METADATA.FETCH_CLOB(l_handle) đến NULL rồi CLOSE.
```

Với collection phức tạp, tìm đường object phù hợp qua `SCHEMA_EXPORT_OBJECTS`, `TABLE_EXPORT_OBJECTS`, `DATABASE_EXPORT_OBJECTS` và tham số filter như `INCLUDE_PATH_EXPR`/`EXCLUDE_PATH_EXPR`. Không đánh đồng kết quả `SCHEMA_EXPORT` với `GET_DDL('TABLE')`: object, grant, statistics và metadata phụ thuộc có thể trải trên nhiều DDL. Việc dựng lại schema vẫn phải xử lý quyền, thứ tự và các đối tượng không thể chuyển nguyên giữa hai môi trường.

## 10. Tùy biến tên schema/tablespace bằng `MODIFY` và `REMAP`

Một nhu cầu phổ biến là sao chép định nghĩa bảng từ `APP` sang `APP_TEST`, hoặc từ tablespace `DATA_PROD` sang `DATA_TEST`. Trong API nhiều object, Oracle cho phép nối **transform `MODIFY`** rồi **transform `DDL`**, áp `SET_REMAP_PARAM` cho handle `MODIFY`.

Ví dụ đọc DDL một bảng và remap owner, không thực thi DDL:

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
  l_handle    NUMBER;
  l_modify    NUMBER;
  l_ddl_tr    NUMBER;
  l_ddl       CLOB;
BEGIN
  l_handle := DBMS_METADATA.OPEN('TABLE');
  DBMS_METADATA.SET_FILTER(l_handle, 'SCHEMA', 'APP');
  DBMS_METADATA.SET_FILTER(l_handle, 'NAME', 'ORDERS');

  l_modify := DBMS_METADATA.ADD_TRANSFORM(l_handle, 'MODIFY');
  DBMS_METADATA.SET_REMAP_PARAM(
    l_modify, 'REMAP_SCHEMA', 'APP', 'APP_TEST');

  l_ddl_tr := DBMS_METADATA.ADD_TRANSFORM(l_handle, 'DDL');
  DBMS_METADATA.SET_TRANSFORM_PARAM(
    l_ddl_tr, 'SQLTERMINATOR', TRUE);

  l_ddl := DBMS_METADATA.FETCH_CLOB(l_handle);
  DBMS_OUTPUT.PUT_LINE('DDL chars: ' || NVL(DBMS_LOB.GETLENGTH(l_ddl), 0));

  DBMS_METADATA.CLOSE(l_handle);
  l_handle := NULL;
EXCEPTION
  WHEN OTHERS THEN
    IF l_handle IS NOT NULL THEN
      DBMS_METADATA.CLOSE(l_handle);
    END IF;
    RAISE;
END;
/
```

Đoạn minh họa chỉ in độ dài, để không làm mất phần còn lại của CLOB. Trong ứng dụng thực, xuất giá trị `l_ddl` đầy đủ rồi review file trước khi chạy. Có transform **`REMAP_TABLESPACE`** nếu đối tượng/loại metadata hỗ trợ. Chi tiết tham số và kiểu object hỗ trợ xem trong `DBMS_METADATA` Reference.

**Hạn chế quan trọng:** Oracle nêu rõ việc remap **không bảo đảm viết lại mọi chuỗi tham chiếu schema** nhúng trong thân PL/SQL, view, trigger, type hoặc mã động. Ví dụ, source package có `EXECUTE IMMEDIATE 'SELECT ... FROM APP.ORDERS'` có thể cần sửa thủ công. Ngoài ra, remap object owner không tự bảo đảm target schema có user, quota, tablespace, quyền hoặc dependency cần thiết.

## 11. DDL là một snapshot của metadata, không phải full backup

### 11.1. Những gì `DBMS_METADATA` có thể và không thể đáp ứng

| Yêu cầu | `DBMS_METADATA` đáp ứng thế nào? | Nếu cần hơn |
| --- | --- | --- |
| Lấy lại `CREATE TABLE` | Rất phù hợp qua `GET_DDL('TABLE')` | Xem riêng object phụ thuộc và data |
| Lấy định nghĩa view, sequence, package | Phù hợp qua `GET_DDL` cho object type đúng | Xem dependency và version compatibility |
| Lấy index/grants/comments phụ thuộc một bảng | Qua `GET_DEPENDENT_DDL` hoặc API collection | Kiểm tra trùng constraint/index và quyền |
| Lấy grants cấp cho một user | Qua `GET_GRANTED_DDL` | Kiểm kê profile, quota, common/local grants |
| Xuất cả schema nhiều object | `OPEN('SCHEMA_EXPORT')`, filter, transform, fetch | Với quy mô lớn dùng Data Pump metadata export |
| Xuất rows dữ liệu hiện có | **Không** qua `GET_DDL` | Data Pump, backup, ETL hoặc phương án phù hợp |
| Backup có thể point-in-time recovery | **Không** | RMAN, archived redo, chiến lược backup/DR |
| Khôi phục lịch sử mọi lần `ALTER TABLE` | **Không** | DDL audit/version control nếu đã lưu trước đó |
| Tạo script migration an toàn mọi môi trường | Chỉ tạo điểm xuất phát | Review diff, dependency, quyền, test deploy/rollback |

### 11.2. DDL hiện tại không tương đương lịch sử các lần sửa

Giả sử bảng được tạo với hai cột, sau đó `ALTER TABLE` thêm ba cột, đổi kiểu một cột và thêm constraint. `GET_DDL('TABLE',...)` mô tả **trạng thái cấu trúc hiện tại**; nó không tạo lại chuỗi sự kiện đầy đủ theo thời gian.

Vì vậy một hệ thống quản lý schema theo Git vẫn cần migration files có thứ tự và version (Liquibase, Flyway hoặc cơ chế nội bộ tương đương). `DBMS_METADATA` giúp **kiểm tra drift** hoặc tái dựng baseline, không thay thế lịch sử migration đã được kiểm soát.

### 11.3. `METADATA_ONLY` của Data Pump khác việc chỉ lấy một CLOB

Khi cần xuất nhiều loại object, quyền và dependency theo định dạng có thể import, Oracle Data Pump hỗ trợ chế độ **`CONTENT=METADATA_ONLY`**. Tùy phương án, `impdp SQLFILE=...` có thể dùng để xem DDL từ dump mà không chạy các câu tạo object. Đây là workflow công cụ Data Pump với dump/SQLFILE, có quyền và tác động file riêng; không phải đối số của `DBMS_METADATA.GET_DDL`.

Các công cụ này có mục tiêu gần nhau nhưng khác output và cách quản lý: `GET_DDL` rất tiện cho review object đơn lẻ; Data Pump phù hợp khi xuất/import schema lớn theo quy trình quản trị.

## 12. Quyền, bảo mật và những điểm dễ làm lộ thông tin

Metadata không chỉ gồm tên cột: trong một số object có thể chứa **business logic**, tên host/service, đường dẫn, thông tin cấu hình auth, network endpoints hoặc dữ liệu nhạy cảm trong source PL/SQL/comment. Cần kiểm soát việc export tương tự các artefact cấu hình khác.

1. **Dùng quyền tối thiểu**: ưu tiên trích xuất từ schema đang sở hữu; chỉ dùng quyền xem schema khác khi đã được cấp phục vụ công việc.
2. **Chọn đúng PDB**: không xuất nhầm object từ root hoặc PDB khác và trộn script hai tenant.
3. **Giữ bí mật**: xem lại DDL của user, database link, credential-related objects, directory/path, scheduler job và package body trước khi đưa vào Git, ticket hoặc gửi cho bên ngoài.
4. **Xác định mục tiêu script**: DDL cho review có thể ẩn storage, còn DDL phục hồi chính xác cần giữ các thuộc tính quan trọng. Không dùng một bộ transform cho mọi mục đích.
5. **Không tự chạy lại DDL**: các câu `CREATE`, `ALTER`, `DROP`, `GRANT` làm thay đổi database. Việc lấy metadata là read-only; việc apply script là một change request khác.
6. **Giám sát tính nhất quán**: khi nhiều người đang chạy DDL đồng thời, hàng trăm lời gọi `GET_DDL` ở các thời điểm khác nhau có thể tạo snapshot schema không hoàn toàn đồng nhất. Với đợt chuyển môi trường cần kế hoạch freeze/change window hoặc công cụ hỗ trợ nhất quán phù hợp.

### 12.1. Definer's rights và role bị vô hiệu hóa

Đây là tình huống thường gây hiểu nhầm khi tự động hóa:

```text
DBA_USER chạy trực tiếp:
  SELECT DBMS_METADATA.GET_DDL('TABLE','ORDERS','APP') FROM DUAL;
  → Thành công do có SELECT_CATALOG_ROLE.

DBA_USER chuyển logic vào procedure AUTHID DEFINER:
  → Quyền đến từ role thường không còn hiệu lực trong procedure.
  → GET_DDL schema APP có thể trả object-not-found.

Hướng xem xét:
  Invoker's rights AUTHID CURRENT_USER khi mô hình bảo mật cho phép,
  hoặc quyền trực tiếp đúng phạm vi; không cấp role DBA bừa bãi.
```

Phải review mô hình xác thực/ủy quyền của package được xây dựng. `AUTHID CURRENT_USER` không có nghĩa tự động cho phép truy cập metadata của bất kỳ user nào.

## 13. Lỗi và tình huống chẩn đoán phổ biến

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `ORA-31603: object ... not found in schema ...` | Sai name/owner/type, sai PDB hoặc không đủ quyền metadata | `SYS_CONTEXT`, `USER_OBJECTS`/`ALL_OBJECTS`, kiểm tra case-sensitive identifier và security model |
| `ORA-31600`/`INVALID_ARGVAL` | Tham số object type, filter hoặc transform không hợp lệ | Đối chiếu object types/filter names trong tài liệu `DBMS_METADATA` của release |
| `ORA-31608` hoặc object-not-found ở dependent/granted DDL | Không có object/grant loại đó, hoặc không được phép thấy | Kiểm tra `ALL_TAB_PRIVS`, `ALL_INDEXES`, `ROLE_ROLE_PRIVS` hoặc dictionary tương ứng |
| DDL bị cắt ở khoảng 4.000 ký tự | Client giới hạn LONG/CLOB, gọi `DBMS_LOB.SUBSTR` | `SET LONG`, tải full CLOB qua client, so chiều dài thật với `DBMS_LOB.GETLENGTH` |
| Chỉ thấy bảng mà không thấy index/trigger | Chỉ gọi `GET_DDL('TABLE')` | Trích các dependent objects hoặc dùng schema export có thiết kế |
| DDL có quá nhiều `STORAGE`, `TABLESPACE` | Transform mặc định xuất physical attributes | Chỉnh `STORAGE` hoặc `SEGMENT_ATTRIBUTES` theo mục đích rồi reset |
| DDL thiếu constraint | Session từng đặt `CONSTRAINTS=FALSE` hoặc script chỉ xuất một phần | Reset transform; xem `CONSTRAINTS`, `REF_CONSTRAINTS`; đối chiếu dictionary |
| Schema đã được remap nhưng package vẫn tham chiếu owner cũ | Chuỗi trong source PL/SQL/dynamic SQL không được biến đổi toàn diện | Review source, dependencies, hard-coded qualifiers |
| User có quyền trực tiếp truy vấn nhưng `GET_DDL` schema khác vẫn lỗi | Khác biệt giữa object SELECT privilege và metadata privilege | `DBMS_METADATA` security model, `SELECT_CATALOG_ROLE`, current container |
| Chạy trực tiếp được, chạy trong procedure không được | Definer's rights vô hiệu hóa roles | `AUTHID CURRENT_USER`, quyền trực tiếp và privilege check |
| Script xuất thành công nhưng deploy lỗi | Thiếu user/tablespace/grant/dependency, sai phiên bản hoặc trùng object | Đọc errors thực tế, so target capabilities, thứ tự và transform |

### 13.1. Kiểm tra xem DDL có thực sự dài hơn client hiển thị không

```sql
-- Đếm chiều dài CLOB thực do hàm trả về, không cắt CLOB.
SELECT DBMS_LOB.GETLENGTH(
         DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', 'APP')) AS ddl_chars
FROM   dual;
```

Nếu `DDL_CHARS = 25000` nhưng file chỉ có vài nghìn ký tự, nhiều khả năng **client/export pipeline** làm ngắn kết quả, không phải `DBMS_METADATA` bỏ bớt metadata. Với package body có source lớn, cần chọn cơ chế lưu nguyên vẹn CLOB thay vì `DBMS_OUTPUT.PUT_LINE` một lần (vốn có giới hạn độ dài dòng).

### 13.2. Cẩn thận khi dùng `DBMS_OUTPUT`

`DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(l_ddl, 32767, 1))` trông tiện nhưng không đáng tin như một exporter CLOB đầy đủ:

- Một lệnh `SUBSTR` chỉ lấy đoạn đầu; object dài hơn bị **mất phần sau**.
- `PUT_LINE` có giới hạn **bytes/dòng**, nhạy với ký tự đa byte và phiên bản công cụ.
- Tự chèn newline giữa các đoạn CLOB có thể làm thay đổi string literal, quoted identifier hoặc cấu trúc PL/SQL trong script.

Nếu cần export programmatically, dùng API client đọc **CLOB theo stream nguyên vẹn**, hoặc cơ chế ghi file giữ đúng chuỗi ký tự với encoding được kiểm soát. Chỉ dùng `DBMS_OUTPUT` để debug/đếm chiều dài, không phải định dạng chuẩn để tái tạo SQL không mất mát.

## 14. Thực hành có kiểm soát trên schema lab

> Các bước tạo bảng làm thay đổi database và chỉ dành cho **schema lab có quyền**. Không tạo/truncate/drop object production. Nếu môi trường chỉ cho phép đọc, bỏ qua bước tạo và dùng object đã được DBA chỉ định.

### 14.1. Tạo schema object đơn giản

```sql
-- Kết nối tới đúng PDB/schema lab.
CREATE TABLE metadata_lab_orders (
    order_id      NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_code VARCHAR2(30 CHAR) NOT NULL,
    amount        NUMBER(12, 2) DEFAULT 0 NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT pk_metadata_lab_orders PRIMARY KEY (order_id)
);

CREATE INDEX idx_md_orders_customer
  ON metadata_lab_orders(customer_code);

COMMENT ON TABLE metadata_lab_orders IS 'Bảng lab về DBMS_METADATA';
```

DDL `CREATE` có tác dụng thay đổi schema và có implicit commit. Chỉ chạy khi được phép; không sử dụng các tên này nếu trong schema đã tồn tại object trùng.

### 14.2. Xuất DDL bảng và index

```sql
SET LONG 2000000
SET PAGESIZE 0

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);

SELECT DBMS_METADATA.GET_DDL('TABLE', 'METADATA_LAB_ORDERS')
FROM   dual;

SELECT DBMS_METADATA.GET_DDL('INDEX', 'IDX_MD_ORDERS_CUSTOMER')
FROM   dual;

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
```

Quan sát rằng DDL của bảng thường chứa constraint PK, còn secondary index được yêu cầu riêng. Không kết luận DDL của bảng luôn xuất ra mọi independent index có trong schema.

### 14.3. Lấy comment bằng dependent metadata

```sql
SELECT DBMS_METADATA.GET_DEPENDENT_DDL(
           'COMMENT', 'METADATA_LAB_ORDERS')
FROM   dual;
```

Nếu hàm không trả kết quả, kiểm tra object/table comment còn tồn tại, quyền, tên owner mặc định và đúng PDB. `GET_DEPENDENT_DDL` chỉ lấy nhóm dependent object đúng loại, không phải lệnh truy vấn mọi metadata của bảng.

### 14.4. So sánh hai cách xuất DDL

```sql
-- Phiên A: giữ nguyên các physical attributes theo mặc định.
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
SELECT DBMS_METADATA.GET_DDL('TABLE','METADATA_LAB_ORDERS') FROM dual;

-- Phiên B: chỉ thay cách hiển thị, không ALTER TABLE trong database.
EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SEGMENT_ATTRIBUTES', FALSE);
SELECT DBMS_METADATA.GET_DDL('TABLE','METADATA_LAB_ORDERS') FROM dual;

EXEC DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'DEFAULT');
```

**Câu hỏi:** Hai kết quả DDL có thể khác nhau dù bảng thật không đổi không? **Có.** Transform chỉ quyết định cách xuất metadata thành SQL; nó không chạy `ALTER TABLE` trên object gốc.

### 14.5. Dọn lab (tùy chọn, chỉ khi chắc chắn đúng object)

```sql
-- Chạy trên schema lab sau khi đã lưu kết quả cần dùng.
DROP TABLE metadata_lab_orders PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và các đối tượng phụ thuộc có liên quan, không có đường rollback DML thông thường. Trong bài thực hành, ưu tiên giữ lại lab hoặc để chủ sở hữu schema quyết định việc dọn. Không chạy lệnh xóa này nếu object không phải do lab vừa tạo.

## 15. Thiết kế workflow export có thể xem xét và sử dụng lại

Khi dùng `DBMS_METADATA` trong công việc thật, mỗi lần export nên có một **manifest rõ ràng**:

| Trường | Ví dụ |
| --- | --- |
| Nguồn database | `SALES_PDB`, service và DB version/compatible |
| Schema | `APP` |
| Phạm vi | `TABLE`, `INDEX`, `VIEW`, `PACKAGE_SPEC/BODY`, grants, comments... |
| Owner của quá trình | Account được phép đọc metadata |
| Transform profile | `PRETTY=TRUE`, `SQLTERMINATOR=TRUE`, `STORAGE=FALSE` hoặc chế độ full fidelity |
| Thời điểm capture | UTC timestamp và change window |
| Tập object | Danh sách object + loại + owner + object status |
| Số file / checksum | `orders.sql`, `order_api.pks`, `order_api.pkb`... |
| Phạm vi PDB | Current container/DBID hoặc thông tin định danh phù hợp |
| Review | Có đầy đủ phụ thuộc, không lộ bí mật, không lỗi cắt CLOB |
| Mục đích dùng | Audit, schema diff, review hay deploy có kiểm soát |

Một workflow có thể phân tách:

```text
1. Xác minh kết nối và quyền
2. Đóng băng phạm vi và thời điểm capture
3. Lấy danh mục object từ dictionary
4. Chọn GET_DDL / GET_DEPENDENT_DDL / GET_GRANTED_DDL
   hoặc OPEN('SCHEMA_EXPORT')
5. Cấu hình transform phù hợp
6. Xuất đầy đủ CLOB và lưu UTF-8
7. Kiểm tra file/manifest; phân loại sensitive metadata
8. Review dependency, chuẩn hóa những thay đổi có chủ ý
9. So sánh với Git hoặc schema đích
10. Khi được phê duyệt, deploy bằng pipeline riêng
```

Hai mục tiêu thường đối lập cần được viết rõ trong manifest:

- **Full-fidelity capture**: ưu tiên giữ thông tin định nghĩa, physical clauses và các dependent objects; phục vụ audit/reconstruction cụ thể.
- **Portable DDL for review/migration**: có thể bỏ `STORAGE` hoặc remap tablespace/owner để dễ chuyển môi trường; cần chấp nhận khác biệt có chủ đích và review trước apply.

Không nên so sánh file text của hai chế độ rồi kết luận schema drift nếu transform profile khác nhau. Ngược lại, DDL text giống nhau về phần cột cũng không chứng minh **data, grants, indexes, policies và runtime settings** đều giống.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `DBMS_METADATA.GET_DDL('TABLE','ORDERS','APP')` trả về kiểu dữ liệu nào? Có bao gồm tất cả rows trong bảng không?

**Câu 2.** DBA cần lấy danh sách `GRANT SELECT ON APP.ORDERS ...`. Nên dùng `GET_DEPENDENT_DDL` hay `GET_GRANTED_DDL`?

**Câu 3.** Muốn biết toàn bộ role cấp cho user `REPORT_USER`, chọn hàm và object type nào?

**Câu 4.** Một package body dài 35.000 ký tự bị export còn 4.000 ký tự. Có thể do cấu hình nào?

**Câu 5.** `SEGMENT_ATTRIBUTES=FALSE` có tác động gì đến định nghĩa bảng trong database đang chạy?

**Câu 6.** Vì sao `GET_DDL` của một bảng không đủ để cam kết phục hồi đầy đủ ứng dụng?

**Câu 7.** Một common user đã được role `SELECT_CATALOG_ROLE`, query trực tiếp lấy DDL schema khác thành công nhưng gọi trong definer's rights procedure thất bại. Giải thích vì sao.

**Câu 8.** Trong CDB có `APP.ORDERS` ở hai PDB. Chỉ biết tên schema và object đã đủ để export đúng chưa?

**Câu 9.** Khi đã tạo transform handle bằng `ADD_TRANSFORM`, gọi `SET_TRANSFORM_PARAM` với handle của `OPEN` có hợp lệ không?

**Câu 10.** `REMAP_SCHEMA` có tự sửa mọi hard-coded schema name trong dynamic SQL của PL/SQL không?

<details>
<summary>Gợi ý đáp án</summary>

1. Trả **CLOB chứa DDL**, không phải rows. Dữ liệu cần một quy trình export/backup khác.
2. `GET_DEPENDENT_DDL('OBJECT_GRANT','ORDERS','APP')` vì câu hỏi về grants **trên bảng**.
3. `GET_GRANTED_DDL('ROLE_GRANT','REPORT_USER')`.
4. `SET LONG` quá nhỏ, công cụ chỉ preview CLOB, hoặc script dùng `DBMS_LOB.SUBSTR` một lần.
5. Chỉ ảnh hưởng **text DDL được xuất**, không thay đổi bảng gốc. Tuy nhiên script tái tạo từ text đó sẽ thiếu physical attributes tương ứng.
6. Còn index độc lập, trigger, comment, grants, views, package, sequence, data, dependency và nhiều đối tượng khác.
7. Role thường vô hiệu trong definer's rights PL/SQL; phải thiết kế quyền đúng với invoker's rights hoặc quyền trực tiếp.
8. Chưa: phải xác định **current PDB/service, container và quyền**.
9. Không. Dùng handle transform từ `ADD_TRANSFORM`, không dùng retrieval handle từ `OPEN`.
10. Không bảo đảm. Cần review source, view definitions và dependency sau remap.

</details>

## 17. Tài liệu Oracle chính thức

1. [Oracle Database 19c — `DBMS_METADATA` Package Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_METADATA.html): chữ ký chính xác của `GET_DDL`, `GET_DEPENDENT_DDL`, `GET_GRANTED_DDL`, `OPEN`, `SET_FILTER`, `SET_TRANSFORM_PARAM`, `FETCH_CLOB`, model bảo mật, object types, transform parameters.
2. [Oracle Database 19c Utilities — Using the Metadata APIs](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/using-oracle-dbms_metadata-api.html): workflow `OPEN`/`FETCH_CLOB`, lọc object, `MODIFY`/`REMAP_SCHEMA`, trích xuất collection.
3. [Oracle Database 19c Administrator's Guide — Managing Schema Objects](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-schema-objects.html): ví dụ chính thức lấy DDL từ `USER_ALL_TABLES`, tránh nested tables/overflow segments và reset session transforms.
4. [Oracle Database 19c Utilities — Oracle Data Pump Export](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-export-utility.html): metadata-only export, scope schema, các mode và điều kiện cần để export tổng thể.
5. [Oracle Database 19c Utilities — Oracle Data Pump Import](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-import-utility.html): `SQLFILE`, review DDL từ Data Pump dump mà chưa chạy câu tạo object.
6. [Oracle Database 19c Reference — Data Dictionary](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/about-static-data-dictionary-views.html): các `USER_*`, `ALL_*`, `DBA_*`, `CDB_*` views làm nguồn kiểm kê đối tượng và grants.
7. [Oracle Database 19c Multitenant Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/): current container, PDB service, quyền và metadata scope khi trích xuất trong CDB.
8. [Oracle AI Database 26ai — `DBMS_METADATA` Package Reference](https://docs.oracle.com/en/database/oracle/oracle-database/26/arpls/DBMS_METADATA.html): tham khảo thay đổi object types/transform parameters trên release mới; luôn đối chiếu môi trường đang chạy.

**Nguyên tắc thực hành:** Xác định đúng **container → owner → object type/name → quyền → transform → CLOB đầy đủ → dependencies**. `DBMS_METADATA` là công cụ đọc **định nghĩa hiện tại** rất hữu ích, nhưng script sinh ra phải được phân biệt rõ với dữ liệu, lịch sử migration, backup và quyết định triển khai lên hệ thống khác.
