# Phạm vi tham số và metadata ở CDB so với PDB trong Oracle Database

## 1. Vì sao cùng một câu SQL có thể cho kết quả khác nhau ở root và PDB?

Giả sử một hệ thống Oracle Database có **CDB** tên `CDB01` và hai **PDB** tên `SALES_PDB`, `HR_PDB`. DBA kết nối vào `CDB$ROOT`, xem tham số `STATISTICS_LEVEL` và danh sách bảng bằng `DBA_TABLES`. Ứng dụng kết nối vào `SALES_PDB`, chạy những truy vấn trông giống hệt nhưng thấy giá trị tham số hoặc danh sách bảng khác. Một tài khoản giám sát ở root truy vấn `CDB_TABLES` còn có thể thấy thông tin của cả hai PDB, trong khi tài khoản ứng dụng chỉ thấy phạm vi một PDB.

Đây là hành vi thiết kế của **Oracle Multitenant**, không nhất thiết là dữ liệu bị mất hay tham số bị sai. Trong CDB, một số cấu hình áp dụng ở cấp database/instance; một số được **kế thừa từ root nhưng có thể ghi đè ở PDB**; và các đối tượng metadata được hiển thị theo **current container, quyền truy cập và loại view**.

Bài học tập trung vào hai câu hỏi:

1. **Phạm vi tham số:** Khi đọc hoặc thay đổi một initialization parameter, giá trị đó thuộc root, riêng PDB, instance, session hay được kế thừa? Nó có tồn tại qua lần đóng/mở PDB không?
2. **Phạm vi metadata:** Khi đọc `USER_*`, `ALL_*`, `DBA_*`, `CDB_*` và `V$`/`GV$`, câu truy vấn đang thấy dữ liệu của container nào? Vì sao thêm `CDB_` không bảo đảm thấy mọi PDB?

> Ví dụ dùng cú pháp Oracle Database 19c, có thể áp dụng khái niệm cho các release mới hơn khi đối chiếu tài liệu tương ứng. Tên container, service và giá trị cấu hình đều minh họa. Các lệnh `ALTER SYSTEM`, `ALTER SESSION SET CONTAINER` trong phần thực hành có tác động khác nhau; chỉ chạy phần thay đổi ở môi trường lab và với quyền được cấp.

## 2. Nhìn đúng cấu trúc CDB trước khi nói đến phạm vi

```text
                      Oracle Database CDB01
                 (instance, SGA, background process)
                                │
        ┌───────────────────────┼────────────────────────┐
        │                       │                        │
        ▼                       ▼                        ▼
   CDB$ROOT                 PDB$SEED                  User PDBs
   CON_ID = 1              CON_ID = 2             ┌───────────────┐
        │                       │                 │ SALES_PDB     │
        │                       │                 │ CON_ID = 3    │
        │                       │                 │ Tables/users  │
        │                       │                 ├───────────────┤
        │                       │                 │ HR_PDB        │
        │                       │                 │ CON_ID = 4    │
        │                       │                 │ Tables/users  │
        │                       │                 └───────────────┘
        │                       │                        │
        ├── Metadata và         └─ Template PDB           │
        │   tài nguyên chung                              │
        │                                                  │
        └───── Các PDB kế thừa tham số cho phép ────────────┘
                (một số PDB có override riêng)
```

| Thành phần | Vai trò | Phạm vi thường gặp |
| --- | --- | --- |
| **CDB** | Database nhiều container; hạ tầng vật lý/instance và nhiều tài nguyên dùng chung | Toàn CDB, có thể gồm các PDB ứng dụng |
| **`CDB$ROOT`** | Root container chứa metadata, common users và cấu hình quản trị CDB | Nơi thực hiện thao tác ảnh hưởng toàn CDB và truy vấn metadata xuyên PDB khi đủ quyền |
| **`PDB$SEED`** | PDB mẫu do Oracle dùng khi tạo PDB mới | Không phải PDB ứng dụng để tạo bảng nghiệp vụ |
| **User PDB** | Container riêng chứa schema, dữ liệu và một phần cấu hình | Một PDB độc lập về namespace, nhiều quyền và các đối tượng schema |
| **Application root / application PDB** | Tầng ứng dụng trong application container (nếu sử dụng) | Có cơ chế kế thừa và metadata/data links tương tự nhưng thêm tầng application root |

Trong kiến trúc multitenant, **không phải mỗi PDB đều có một instance và redo log riêng**. Một CDB có một hoặc nhiều instance tùy topology; các PDB chia sẻ nhiều thành phần hạ tầng. Tuy vậy, mỗi PDB có không gian schema và dữ liệu logic riêng, với các datafiles riêng cho tablespace của nó.

### 2.1. Ba khái niệm về phạm vi không đồng nhất

| Phạm vi | Ví dụ | Cần phân biệt |
| --- | --- | --- |
| **Instance scope** | Tham số bộ nhớ/tiến trình của instance, một số `GV$` | Có thể khác giữa các instance của RAC, nhưng không đồng nghĩa mỗi PDB có instance riêng |
| **Container scope** | Object schema của `SALES_PDB`, tham số PDB cho phép override | Cùng tên đối tượng/parameter có thể tồn tại ở nhiều container với metadata/giá trị khác nhau |
| **Session scope** | `ALTER SESSION`, schema hiện hành và các session-modifiable parameters | Hai session trong cùng PDB có thể thấy/được áp dụng session settings khác nhau |

Hãy hỏi rõ đang nói về **instance, container hay session** trước khi thay đổi cấu hình hoặc giải thích output.

## 3. Xác định current container ngay khi đăng nhập

Mỗi phiên làm việc Oracle có một **current container**. Khi ứng dụng đăng nhập bằng service của PDB, current container thường là PDB được service đó trỏ tới. Khi DBA đăng nhập vào root, câu SQL thông thường chạy trong ngữ cảnh root.

Các câu lệnh **chỉ đọc** để tự xác định ngữ cảnh:

```sql
-- SQL*Plus / SQLcl
SHOW CON_NAME;
SHOW CON_ID;

-- SQL chuẩn của Oracle, dùng được trong công cụ thực thi query:
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'CON_ID')   AS con_id,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM   dual;
```

Ví dụ:

```text
CON_NAME   CON_ID  SERVICE_NAME
---------  ------  ------------------------
SALES_PDB  3       sales_app.example.com
```

Nếu tài khoản/common user có quyền phù hợp, DBA có thể chuyển current container:

```sql
-- Lệnh thay đổi ngữ cảnh session: chỉ dành cho tài khoản có quyền SET CONTAINER.
ALTER SESSION SET CONTAINER = SALES_PDB;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name FROM dual;

-- Khi cần trở về root và có quyền:
ALTER SESSION SET CONTAINER = CDB$ROOT;
```

Việc chuyển container không tự động cấp quyền xem dữ liệu hay thao tác quản trị trong PDB đích. `SET CONTAINER`, `CREATE SESSION` và các quyền đối với đối tượng vẫn phải được cấp theo ngữ cảnh phù hợp. Với ứng dụng, nên kết nối trực tiếp **service của PDB** thay vì bắt đầu ở root rồi chuyển container.

### 3.1. Quan sát danh sách các container từ root

```sql
-- Thực hiện từ CDB$ROOT với quyền đọc view phù hợp.
SELECT con_id, name, open_mode, restricted
FROM   v$containers
ORDER BY con_id;

-- Riêng PDB, ở root có thể xem PDB$SEED và các user PDB:
SELECT con_id, name, open_mode, restricted
FROM   v$pdbs
ORDER BY con_id;
```

`V$CONTAINERS` cung cấp metadata về các container, kể cả root. `V$PDBS` liệt kê PDB liên quan đến **instance hiện tại**; khi truy vấn bên trong một PDB, `V$PDBS` chỉ hiển thị thông tin PDB hiện tại thay vì toàn bộ các PDB. Trong RAC, kiểm tra thêm instance hoặc dùng `GV$` tương ứng khi cần góc nhìn nhiều instance.

Không đồng nhất `OPEN_MODE='READ WRITE'` với quyền user có thể đọc mọi object. Visibility vẫn bị điều chỉnh bởi quyền, container hiện tại và object-specific policy.

## 4. Tham số khởi tạo: mặc định ở root, một số cho phép override ở PDB

### 4.1. Nguyên tắc kế thừa

Oracle dùng mô hình **parameter inheritance**:

- **Root có giá trị tham số** phù hợp với toàn CDB hoặc hoạt động instance.
- **PDB mặc định kế thừa** giá trị tương ứng từ root khi chưa có thiết lập riêng.
- **Chỉ một tập con tham số được phép đổi tại PDB**. Những tham số khác phải kế thừa root và không thể tùy ý có giá trị riêng ở từng PDB.
- Khi PDB được phép override và DBA đặt một giá trị cho nó, **PDB dùng giá trị riêng** thay vì tiếp tục kế thừa root, cho đến khi cấu hình inheritance được khôi phục/đặt lại theo cú pháp phù hợp.

Hình dung:

```text
                         Root: PARAM_X = A
                                │
                   ┌────────────┴─────────────┐
                   ▼                          ▼
       SALES_PDB: inherit=true         HR_PDB: inherit=false
       effective PARAM_X = A           explicit PARAM_X = B
                   │                          │
                   └────────────┬─────────────┘
                                ▼
                   Root đổi PARAM_X = C

       SALES_PDB thấy C nếu nhận thay đổi theo phạm vi/thời điểm áp dụng
       HR_PDB tiếp tục dùng B khi override còn hiệu lực
```

**Điểm quyết định:** Không phải cứ DBA chỉnh tham số từ root là mọi PDB mất override. Tác động phụ thuộc `CONTAINER=CURRENT` hay `CONTAINER=ALL`, khả năng PDB override, giá trị `SCOPE` và trạng thái khởi động/đang mở.

### 4.2. Không suy đoán từ tên tham số; tra `ISPDB_MODIFIABLE`

Oracle Database Reference định nghĩa `V$SYSTEM_PARAMETER.ISPDB_MODIFIABLE`:

- **`TRUE`**: tham số có thể được cấu hình riêng cho PDB.
- **`FALSE`**: không thể sửa tham số đó từ trong PDB, nên PDB phải dùng cấu hình của cấp quản trị cao hơn.

```sql
-- Chỉ đọc: xác định các tham số có thể thiết lập riêng trong PDB.
SELECT name,
       display_value,
       ispdb_modifiable,
       issys_modifiable,
       isses_modifiable
FROM   v$system_parameter
WHERE  name IN (
           'statistics_level',
           'optimizer_mode',
           'open_cursors',
           'db_name',
           'processes',
           'sga_target'
       )
ORDER BY name;
```

Các tên tham số ở đây chỉ là **đầu vào kiểm tra**; kết quả cột `ISPDB_MODIFIABLE` trên **release và môi trường thật** mới là căn cứ để quyết định thay đổi tại PDB. Một tham số có thể thuộc nhóm giới hạn hạ tầng và không cho PDB tự đặt, trong khi tham số hành vi truy vấn có thể được thay đổi ở PDB.

Muốn lấy danh sách đầy đủ từ database đang chạy:

```sql
SELECT name,
       display_value,
       issys_modifiable,
       isses_modifiable
FROM   v$system_parameter
WHERE  ispdb_modifiable = 'TRUE'
ORDER BY name;
```

**Phân biệt ba cột:**

| Cột | Câu hỏi trả lời | Giá trị thường gặp |
| --- | --- | --- |
| `ISPDB_MODIFIABLE` | Có thể đặt riêng trong PDB không? | `TRUE`, `FALSE` |
| `ISSYS_MODIFIABLE` | Có thể thay đổi bằng `ALTER SYSTEM` khi đang chạy không và có hiệu lực lúc nào? | `IMMEDIATE`, `DEFERRED`, `FALSE` |
| `ISSES_MODIFIABLE` | Session có thể thay đổi bằng `ALTER SESSION` không? | `TRUE`, `FALSE` |

Một tham số `ISSES_MODIFIABLE='TRUE'` không có nghĩa được dùng `ALTER SYSTEM` tại PDB. Một tham số `ISSYS_MODIFIABLE='IMMEDIATE'` cũng **không tự có nghĩa `ISPDB_MODIFIABLE='TRUE'`**. Mỗi cột kiểm soát một chiều phạm vi khác nhau.

### 4.3. Ví dụ nhóm tham số theo mục đích

| Nhóm | Ví dụ | Phạm vi cần cân nhắc |
| --- | --- | --- |
| Cấu trúc database/instance | `DB_NAME`, `CONTROL_FILES`, `PROCESSES` | Hạ tầng CDB/instance; PDB không sở hữu control file hoặc process pool độc lập |
| Bộ nhớ và quản lý tài nguyên | `SGA_TARGET`, `PGA_AGGREGATE_TARGET`, một số giới hạn bộ nhớ PDB theo release | Phân biệt bộ nhớ chung của instance và giới hạn tài nguyên có hỗ trợ trên PDB |
| Optimizer/session behavior | `OPTIMIZER_MODE`, `STATISTICS_LEVEL`, các tham số hành vi optimizer khác | Có thể có mức cấu hình PDB hoặc session tùy tham số/release |
| Quản lý kết nối/session | `OPEN_CURSORS`, `SESSIONS` và các giới hạn liên quan | Cần đọc metadata để biết tham số nào cho PDB override và giới hạn cục bộ |
| Storage/đặc tính PDB | Default tablespace, giới hạn storage, open mode, service | Nhiều thuộc tính là metadata/thuộc tính PDB hoặc thao tác `ALTER PLUGGABLE DATABASE`, không phải initialization parameter |

Không “tự động chia” SGA thành một SGA riêng cho mỗi PDB. PDB có khả năng kiểm soát/giới hạn tài nguyên ở một số release và offering, nhưng vẫn sống trong hạ tầng instance dùng chung. Chỉ kết luận một tham số có thể đặt riêng khi Oracle báo `ISPDB_MODIFIABLE='TRUE'` và manual có điều kiện tương ứng.

## 5. `CONTAINER=CURRENT` và `CONTAINER=ALL` khi thay tham số

`ALTER SYSTEM SET` trong CDB cho phép chỉ rõ `CONTAINER` để quyết định tính áp dụng của một lần đặt tham số. **Current container phải được xác định trước.**

| Vị trí chạy | `CONTAINER` | Phạm vi có ý nghĩa | Ảnh hưởng đến inheritance |
| --- | --- | --- | --- |
| `CDB$ROOT` | `CURRENT` hoặc bỏ qua | Giá trị root; các PDB đang kế thừa có thể nhận giá trị root mới theo quy tắc hiệu lực | **Không** chủ động xóa override đang có của PDB |
| `CDB$ROOT` | `ALL` | Root và toàn bộ PDB trong CDB | **Đặt lại inheritance thành true** cho tham số ở các PDB, có thể thay thế override trước đó |
| Một PDB | `CURRENT` hoặc bỏ qua | Chỉ PDB hiện tại, khi tham số hỗ trợ `ISPDB_MODIFIABLE=TRUE` | PDB có thể tạo/điều chỉnh override riêng |
| Một PDB | `ALL` | Không dùng cho toàn CDB từ trong PDB thường | Không được mở rộng phạm vi sang các PDB khác bằng cách này |

**Cú pháp minh họa, không thực hiện ở production nếu chưa duyệt thay đổi:**

```sql
-- Chạy ở CDB$ROOT: chỉ cập nhật root và các PDB còn kế thừa.
ALTER SYSTEM SET STATISTICS_LEVEL = TYPICAL
  SCOPE = BOTH CONTAINER = CURRENT;

-- Chạy ở SALES_PDB: đặt riêng cho PDB hiện tại (nếu được hỗ trợ).
ALTER SYSTEM SET STATISTICS_LEVEL = ALL
  SCOPE = BOTH CONTAINER = CURRENT;

-- Chạy ở CDB$ROOT: có phạm vi toàn CDB,
-- đồng thời làm PDB quay lại kế thừa tham số đó.
ALTER SYSTEM SET STATISTICS_LEVEL = TYPICAL
  SCOPE = BOTH CONTAINER = ALL;
```

**Chú ý ba nghĩa khác nhau của từ `ALL`:**

1. `STATISTICS_LEVEL = ALL`: đây là **giá trị của tham số**.
2. `CONTAINER = ALL`: đây là **phạm vi thay đổi**.
3. `SCOPE = BOTH`: đây là **thời điểm và nơi lưu thay đổi**, không phải phạm vi container.

`CONTAINER=ALL` có thể làm mất cấu hình riêng của nhiều PDB. Với một CDB chạy nhiều ứng dụng, đây là thay đổi lớn cần kiểm kê các override hiện hành trước và có phương án khôi phục.

### 5.1. Minh họa từng bước cho hai PDB

Giả sử tham số X là một tham số `ISPDB_MODIFIABLE=TRUE`:

| Thời điểm | Root | `SALES_PDB` | `HR_PDB` |
| --- | --- | --- | --- |
| Ban đầu | `A` | `A` (inherit) | `A` (inherit) |
| Đặt `HR_PDB` riêng thành `B` | `A` | `A` (inherit) | `B` (override) |
| Root đặt `C`, `CONTAINER=CURRENT` | `C` | `C` (inherit) | `B` (override) |
| Root đặt `D`, `CONTAINER=ALL` | `D` | `D` (inherit) | `D` (inherit, override bị thay thế) |

Bảng mô tả **giá trị hiệu lực sau khi thay đổi đã được áp dụng theo `SCOPE`/khả năng động**. Nếu `SCOPE=SPFILE` thì giá trị lưu mới chưa nhất thiết được thấy ngay trong session đang chạy.

### 5.2. Không nhầm `CONTAINER=ALL` trong những loại lệnh khác

`CONTAINER` còn xuất hiện trong `CREATE USER`, `CREATE ROLE`, `GRANT`, `REVOKE`... nhưng ngữ nghĩa chi tiết và điều kiện quyền **không giống hệt `ALTER SYSTEM`**. Ví dụ, `GRANT CREATE SESSION ... CONTAINER=ALL` cho common user là một **common grant**, không phải thao tác đổi tham số. Luôn đọc mô tả của lệnh đang dùng.

## 6. `SCOPE=MEMORY`, `SPFILE`, `BOTH` và khả năng tồn tại qua mở lại PDB

Không chỉ cần biết **đổi cho container nào**; cần biết thay đổi có **hiệu lực ngay** và **được lưu bền vững** hay không.

| `SCOPE` | Với dynamic parameter trong PDB | Khi đóng/mở lại PDB hoặc khởi động lại CDB |
| --- | --- | --- |
| `MEMORY` | Thay đổi giá trị đang chạy ở PDB, trong phạm vi thích hợp | Không duy trì như cấu hình PDB bền vững; giá trị có thể trở lại theo root/giá trị khởi động |
| `SPFILE` | Ghi thiết lập PDB bền vững, không nhất thiết thay giá trị runtime ngay | Hiệu lực sau lần mở lại PDB/khởi động lại CDB |
| `BOTH` | Thay đổi runtime ở PDB và ghi thiết lập bền vững | Duy trì qua đóng/mở PDB hoặc khởi động lại CDB |

**Điều kiện:** Ngữ nghĩa thực tế còn chịu giới hạn tham số là dynamic hay static, Oracle Home có dùng SPFILE hay PFILE và các điều kiện cụ thể của release. Với **static parameter**, `SCOPE=SPFILE` là lựa chọn phù hợp để tác động ở lần startup tiếp theo; không ép `MEMORY/BOTH` nếu tham số không cho phép thay runtime.

### 6.1. PDB không có một PFILE độc lập như một instance riêng

Oracle lưu cấu hình initialization parameter của PDB khi dùng `SCOPE=SPFILE`/`BOTH` theo cơ chế persistent PDB parameter settings. **Text PFILE không thể chứa các giá trị initialization parameter riêng của PDB**. Nếu PDB được unplug, các tham số đã đặt riêng bền vững được đưa vào **XML metadata** của PDB để có thể phục hồi khi plug vào CDB khác theo tài liệu Oracle.

Điều đó không có nghĩa mọi giá trị parameter của PDB đều được lưu ở một file `initSALES_PDB.ora` trên filesystem. Một PDB không sở hữu tiến trình startup instance độc lập như một non-CDB trước đây.

### 6.2. Cách đưa PDB trở lại trạng thái kế thừa

Khi một tham số từng bị override ở PDB và muốn bỏ cấu hình riêng, DBA có thể sử dụng `ALTER SYSTEM RESET` trong PDB. Theo tài liệu 19c, tác dụng phụ thuộc `SCOPE`:

| `ALTER SYSTEM RESET` tại PDB | Tác động cần hiểu |
| --- | --- |
| `SCOPE=SPFILE` | Bỏ thiết lập bền vững của PDB; PDB kế thừa root khi mở lại |
| `SCOPE=MEMORY` | Khôi phục giá trị trong bộ nhớ theo quy tắc startup/inheritance; nếu còn persistent override, mở lại PDB có thể tái áp dụng giá trị đó |
| `SCOPE=BOTH` | Bỏ override bền vững và đưa PDB về kế thừa root, theo quy tắc Oracle |

```sql
-- CHỈ MINH HỌA thay đổi cấu hình ở lab sau khi chốt ngữ cảnh PDB.
-- DBA cần kiểm tra tham số hỗ trợ và có thể phát sinh tác động ứng dụng.
ALTER SYSTEM RESET STATISTICS_LEVEL
  SCOPE = BOTH CONTAINER = CURRENT;
```

Đừng thay reset bằng `ALTER SYSTEM SET parameter = <giá trị hiện tại của root>` nếu mục tiêu là **khôi phục inheritance**. Gán một giá trị giống root trong PDB vẫn có thể tạo **override riêng**, và lần root thay đổi tiếp theo PDB vẫn giữ giá trị cũ. Kiểm tra cả ngữ nghĩa `RESET` của đúng version trước khi dùng.

## 7. Ba view tham số phải phân biệt

| View | Câu hỏi chính | Đặc điểm |
| --- | --- | --- |
| **`V$PARAMETER`** | Giá trị tham số đang có hiệu lực đối với **session hiện tại** là gì? | Phản ánh `ALTER SESSION` nếu session đã thay đổi tham số đó |
| **`V$SYSTEM_PARAMETER`** | Giá trị tham số cấp hệ thống/instance theo current container là gì? | Dùng để kiểm tra `ISPDB_MODIFIABLE` và cấu hình dùng làm mặc định cho session mới |
| **`V$SPPARAMETER`** | Những tham số nào đã được ghi vào **server parameter file/persistent settings**? | Có `ISSPECIFIED`; không nhất thiết phản ánh đúng giá trị runtime ngay thời điểm query |

### 7.1. So sánh session value và system value

```sql
-- Chỉ đọc, từ đúng container cần điều tra.
SELECT name,
       display_value,
       isses_modifiable,
       ispdb_modifiable
FROM   v$parameter
WHERE  name IN ('optimizer_mode', 'statistics_level')
ORDER BY name;

SELECT name,
       display_value,
       issys_modifiable,
       ispdb_modifiable
FROM   v$system_parameter
WHERE  name IN ('optimizer_mode', 'statistics_level')
ORDER BY name;
```

Nếu session đã `ALTER SESSION SET OPTIMIZER_MODE=FIRST_ROWS`, `V$PARAMETER` có thể khác `V$SYSTEM_PARAMETER` **dù current container giống nhau**. Vì vậy so sánh parameter giữa hai ứng dụng trước hết phải chốt container, sau đó kiểm tra session override.

### 7.2. Persistent settings và `ISSPECIFIED`

```sql
-- Chỉ đọc; view này mô tả nội dung server parameter file.
SELECT con_id, sid, name, display_value, isspecified
FROM   v$spparameter
WHERE  name IN ('optimizer_mode', 'statistics_level')
ORDER BY con_id, sid, name;
```

`V$SPPARAMETER` cho biết thiết lập đã được khai báo bền vững, nhưng **không dùng một query duy nhất của nó để suy ra ngay giá trị có hiệu lực của mọi PDB**. Một PDB có thể đang kế thừa root; một thay đổi `SCOPE=SPFILE` chưa có hiệu lực runtime; PDB có thể không xuất hiện trong phạm vi data object mà user được phép xem. Hãy truy vấn `V$SYSTEM_PARAMETER` trong chính PDB cần đối chiếu và xác minh nguồn persistent config theo tài liệu.

### 7.3. `ISDEFAULT` và `ISMODIFIED` không phải nhãn xác thực inheritance

`ISDEFAULT` và `ISMODIFIED` có ngữ nghĩa riêng về giá trị mặc định, tham số đã khai báo/thay đổi ở runtime. **Không thể dựa riêng vào `ISDEFAULT='TRUE'` để kết luận PDB hiện đang kế thừa root**, cũng không dùng `ISMODIFIED` làm chứng cứ đủ rằng PDB có override bền vững. Đối chiếu với nơi thực hiện `ALTER SYSTEM`, `SCOPE`, các setting được lưu và giá trị thực trong PDB.

### 7.4. RAC: một `CON_ID` có thể xuất hiện trên nhiều instance

Trong RAC, tham số còn có chiều **instance**: một số phải đồng nhất, số khác có thể khác theo instance nếu `ISINSTANCE_MODIFIABLE` cho phép. Khi cần tìm bất thường trên toàn RAC, tham khảo `GV$SYSTEM_PARAMETER` và lọc theo `INST_ID` **lẫn** `CON_ID`, trong phạm vi quyền cho phép.

```sql
-- Chỉ đọc; kết quả phụ thuộc ngữ cảnh container và quyền visibility.
SELECT inst_id, con_id, name, display_value
FROM   gv$system_parameter
WHERE  name = 'statistics_level'
ORDER BY inst_id, con_id;
```

Trong `GV$`, `INST_ID` chỉ instance, còn `CON_ID` chỉ container. **`INST_ID=2` không phải `CON_ID=2`**; `CON_ID=2` có ý nghĩa `PDB$SEED` trong CDB.

## 8. Metadata và data dictionary: cùng định nghĩa view, dữ liệu theo container

### 8.1. Metadata nào đặt ở root, metadata nào thuộc PDB?

Oracle lưu **định nghĩa metadata của các data dictionary tables/views Oracle-supplied** chủ yếu trong root, dùng cơ chế liên kết nội bộ để PDB nhìn thấy dictionary thích hợp. Nhưng **các bản ghi mô tả đối tượng nghiệp vụ** của một PDB nằm trong phạm vi PDB đó.

Ví dụ:

```text
CDB$ROOT
  ├── metadata Oracle-supplied cho dictionary views
  ├── định nghĩa/common object dùng toàn CDB
  └── DBA_TABLES tại root: đối tượng thuộc root

SALES_PDB
  ├── APP.ORDERS
  ├── APP.ORDER_ITEMS
  └── DBA_TABLES tại SALES_PDB: metadata của các bảng thấy trong PDB

HR_PDB
  ├── HR.EMPLOYEES
  ├── HR.DEPARTMENTS
  └── DBA_TABLES tại HR_PDB: metadata thuộc HR_PDB
```

Do đó, `SELECT ... FROM DBA_TABLES` khi **current container = root** không tự động hợp nhất metadata của `SALES_PDB` và `HR_PDB`. Bảng ứng dụng tạo trong `SALES_PDB` có thể xuất hiện trong `DBA_TABLES` của `SALES_PDB` nhưng không có row tương ứng trong `DBA_TABLES` của `CDB$ROOT`.

### 8.2. Metadata link, data link, extended data link

Oracle Multitenant phân biệt một số cơ chế liên kết dictionary/common objects:

- **Metadata link**: đối tượng trong PDB tham chiếu metadata được duy trì ở root/application root, trong khi dữ liệu có thể thuộc PDB. Với application common object, nhiều application PDB có thể chia sẻ một định nghĩa nhưng có dữ liệu riêng.
- **Data link**: PDB tham chiếu metadata **và dữ liệu** chung đặt ở root/application root, theo quy tắc của đối tượng.
- **Extended data link**: kết hợp dữ liệu từ application root và application PDB trong application container, khi loại đối tượng hỗ trợ.

Không nhầm các cơ chế này với **database link (`DBLINK`)** dùng truy vấn database ở nơi khác. Metadata/data links của multitenant là cơ chế liên kết nội bộ nhằm chia sẻ định nghĩa và/hoặc nội dung giữa container.

Với các object thích hợp, cột `SHARING` trong những view như `DBA_OBJECTS`/`CDB_OBJECTS` hỗ trợ phân biệt object thông thường với các loại liên kết chia sẻ:

```sql
SELECT owner, object_name, object_type, sharing
FROM   dba_objects
WHERE  owner = 'APP'
ORDER BY object_name;
```

Đây là truy vấn **metadata ở current container**; muốn kiểm kê xuyên PDB cần xem `CDB_OBJECTS` từ root với quyền và visibility phù hợp.

## 9. `USER_*`, `ALL_*`, `DBA_*`, `CDB_*`: bốn lớp dictionary views

| Nhóm view | Phạm vi hiển thị theo ngữ nghĩa | Ví dụ |
| --- | --- | --- |
| **`USER_*`** | Đối tượng/metadata liên quan đến schema của user hiện tại, trong current container | `USER_TABLES`, `USER_OBJECTS` |
| **`ALL_*`** | Đối tượng user có quyền truy cập/được phép thấy, trong current container | `ALL_TABLES`, `ALL_OBJECTS` |
| **`DBA_*`** | Metadata quản trị trong current container, nếu tài khoản có quyền đọc dictionary | `DBA_TABLES`, `DBA_USERS`, `DBA_OBJECTS` |
| **`CDB_*`** | Container data objects có cột `CON_ID`; từ root có thể trả metadata của nhiều container theo quyền và `CONTAINER_DATA` | `CDB_TABLES`, `CDB_USERS`, `CDB_OBJECTS` |

**Điều cần nhớ:** `DBA_` nghĩa là độ rộng metadata theo **quyền trong current container**, không đồng nghĩa “toàn bộ CDB”. `CDB_` là cơ chế xem **đa container**, nhưng chỉ khi truy vấn ở root, có quyền dictionary và container visibility phù hợp.

### 9.1. Cùng tên bảng, khác PDB

Giả sử mỗi PDB đều có bảng `APP.CONFIG`:

```text
SALES_PDB.APP.CONFIG    ← metadata, rows riêng của SALES
HR_PDB.APP.CONFIG       ← metadata, rows riêng của HR
```

Từ `SALES_PDB`:

```sql
-- Chỉ đọc metadata cục bộ của current PDB.
SELECT owner, table_name, tablespace_name
FROM   dba_tables
WHERE  owner = 'APP' AND table_name = 'CONFIG';
```

Từ `CDB$ROOT` với quyền và container visibility phù hợp:

```sql
SELECT con_id, owner, table_name, tablespace_name
FROM   cdb_tables
WHERE  owner = 'APP' AND table_name = 'CONFIG'
ORDER BY con_id;
```

Đầu ra minh họa:

```text
CON_ID OWNER TABLE_NAME TABLESPACE_NAME
------ ----- ---------- ---------------
3      APP   CONFIG     APP_DATA
4      APP   CONFIG     HR_DATA
```

Hai row này **không phải một table được nhân đôi sai**: chúng là hai đối tượng trong hai container, cùng owner/table name nhưng khác namespace và storage.

### 9.2. `CDB_*` query khi đang ở PDB

Oracle 19c mô tả: khi current container **không phải root**, các `CDB_*` views chỉ thể hiện đối tượng visible qua `DBA_*` tương ứng trong **PDB hiện tại**. Vì vậy, chọn tên view `CDB_TABLES` ở `SALES_PDB` **không cấp quyền nhìn sang `HR_PDB`**. Muốn thống kê nhiều PDB, dùng account quản trị phù hợp từ root hoặc cơ chế được cấp quyền rõ ràng.

### 9.3. Không dùng metadata view để đọc dữ liệu nghiệp vụ

`CDB_TABLES` liệt kê **metadata về bảng**; nó không tự hợp nhất dữ liệu rows của `APP.ORDERS` từ nhiều PDB. Khi cần truy vấn dữ liệu ứng dụng xuyên container có cơ chế riêng như **`CONTAINERS()`** với các điều kiện object/schema/grant nghiêm ngặt, thường dùng bởi common user và các object được chuẩn bị để xuất hiện ở các PDB liên quan. Không coi `SELECT * FROM CDB_TABLES` là tương đương `SELECT * FROM APP.ORDERS` ở toàn CDB.

## 10. Cột `CON_ID`: khóa nhận diện container trong kết quả tổng hợp

Trong nhiều view `CDB_*` và container data objects như `V$`/`GV$`, cột **`CON_ID`** cho biết row thuộc phạm vi nào.

| `CON_ID` | Ý nghĩa thường gặp trong CDB |
| --- | --- |
| **0** | Thông tin **toàn CDB** hoặc trường hợp non-CDB; không phải tên một PDB tên `0` |
| **1** | `CDB$ROOT` |
| **2** | `PDB$SEED` |
| **3 trở lên** | User PDB, application root, application PDB hoặc container khác được gán ID |

**Đừng loại bỏ `CON_ID=0` như một lỗi dữ liệu.** Ở các performance views, nó thường chỉ row tổng hợp cho toàn CDB/instance. Cũng không nên giả định `CON_ID=3` luôn là `SALES_PDB`: container ID thay đổi theo CDB, quá trình plug/unplug và thời điểm khảo sát.

### 10.1. Ghép tên container từ ID

```sql
-- Chạy trong CDB$ROOT với quyền xem metadata tương ứng.
SELECT con_id, name, open_mode
FROM   v$containers
ORDER BY con_id;

-- Ví dụ ghép tên với metadata bảng (cần quyền + container visibility).
SELECT c.name AS container_name,
       t.con_id,
       t.owner,
       t.table_name
FROM   cdb_tables t
JOIN   v$containers c ON c.con_id = t.con_id
WHERE  t.owner = 'APP'
ORDER BY t.con_id, t.table_name;
```

Join qua `CON_ID` chỉ đúng khi **cùng CDB tại cùng thời điểm**. Không dùng `CON_ID` làm định danh toàn cục bền vững giữa các CDB. Nếu cần theo dõi PDB qua unplug/plug, cần cân nhắc `GUID`, `DBID`, thông tin incarnation và lịch sử PDB phù hợp với mục tiêu.

### 10.2. `INST_ID` khác `CON_ID`

`GV$` thường thêm `INST_ID` để cho biết instance trong RAC; `CON_ID` là container. Một query tổng hợp có thể cần cả hai:

```sql
-- Ví dụ đọc thông tin nhiều instance/container nếu view cung cấp và user được phép.
SELECT inst_id, con_id, name, open_mode
FROM   gv$containers
ORDER BY inst_id, con_id;
```

Nếu một PDB đang mở trên hai instance RAC, nó có thể xuất hiện hai row với **cùng `CON_ID` nhưng khác `INST_ID`**. Đếm row không qua distinct đúng khóa có thể dẫn đến kết luận sai về số PDB.

## 11. Vì sao truy vấn `CDB_*` ở root không trả đủ tất cả PDB?

Đây là tình huống rất hay gặp trong kiểm kê, giám sát và phân quyền DBA.

### 11.1. `CONTAINER_DATA` quyết định phạm vi row được phép thấy

Các `CDB_*` views là **container data objects**. Với common user truy vấn ở root, phạm vi row từ các container được kiểm soát bởi thuộc tính **`CONTAINER_DATA`** ở cấp user và có thể theo từng object. Oracle Database Reference nêu rằng theo mặc định một user kết nối root có thể chỉ thấy dữ liệu root. Vì vậy:

```sql
-- Từ CDB$ROOT, bằng common user có quyền đọc CDB_USERS:
SELECT con_id, username, common
FROM   cdb_users
WHERE  username LIKE 'APP%'
ORDER BY con_id, username;
```

Nếu không có row cho một PDB, **chưa đủ để kết luận PDB đó không có user `APP...`**. Cần kiểm tra: account đang chạy có quyền dictionary không, `CONTAINER_DATA` bao gồm PDB đó không, PDB có mở không, và query có bị filter không.

DBA được ủy quyền có thể quan sát thuộc tính này thông qua `CDB_CONTAINER_DATA`/`DBA_CONTAINER_DATA` theo hướng dẫn Oracle Security Guide. **Không nới rộng `CONTAINER_DATA` lên toàn bộ PDB chỉ để dashboard có thêm row** nếu không được phê duyệt quyền truy cập dữ liệu xuyên tenant.

### 11.2. PDB đóng hoặc `RESTRICTED` ảnh hưởng kết quả

Theo Oracle Database Reference 19c, `CDB_*` views được tổng hợp từ các **PDB đang mở** và có giới hạn đối với PDB mở ở chế độ `RESTRICTED`; trạng thái PDB và instance RAC có thể ảnh hưởng tập kết quả. Một PDB `MOUNTED` vẫn có metadata trong các view quản lý PDB, nhưng `CDB_TABLES` có thể **không trả danh sách bảng của PDB đó** tại thời điểm đang đóng.

```sql
-- Xem trạng thái container để biết phạm vi có thể thu thập metadata.
SELECT con_id, name, open_mode, restricted
FROM   v$pdbs
ORDER BY con_id;
```

Đừng tự mở PDB production chỉ để làm cho câu query metadata có đủ row. Nếu cần kiểm kê, phải thống nhất phạm vi, thời điểm và quyền với DBA chịu trách nhiệm.

### 11.3. Quyền dictionary và quyền tenant là hai điều kiện riêng

Một common user có quyền `SELECT` trên một container data object nhưng không được phép xem tất cả container theo `CONTAINER_DATA`. Ngược lại, `CONTAINER_DATA` cho phép phạm vi container cũng **không tự cấp quyền `SELECT` lên mọi view/table**. Hai tầng kiểm soát cần đáp ứng độc lập:

```text
      Quyền đọc object/view?
                 │
         ┌───────┴────────┐
         │                │
        NO               YES
         │                │
       Lỗi/              ▼
      bị chặn     CONTAINER_DATA cho phép PDB nào?
                          │
                 ┌────────┴─────────┐
                 ▼                  ▼
            Được phép          Không được phép
                 │                  │
            Có thể thấy       Không có row từ PDB
            row hợp lệ        đó trong kết quả
```

Vì vậy không chẩn đoán “view lỗi” chỉ từ việc root nhận ít row hơn dự kiến.

## 12. Cảnh giác với các `V$`/`GV$` có semantics đặc biệt

Không phải mọi performance view đều hiển thị một row mỗi PDB. Một số view cung cấp **số liệu cấp instance**, dùng `CON_ID=0` khi truy vấn từ root; những view khác là container data objects có thể cung cấp row chi tiết PDB.

Ví dụ Oracle 19c Multitenant Administrator's Guide chỉ rõ sự khác biệt:

| Số liệu | View cấp hệ thống | View tương ứng theo container |
| --- | --- | --- |
| System statistics | `[G]V$SYSSTAT` | `[G]V$CON_SYSSTAT` |
| Time model | `[G]V$SYS_TIME_MODEL` | `[G]V$CON_SYS_TIME_MODEL` |
| System event | `[G]V$SYSTEM_EVENT` | `[G]V$CON_SYSTEM_EVENT` |
| Wait class | `[G]V$SYSTEM_WAIT_CLASS` | `[G]V$CON_SYSTEM_WAIT_CLASS` |

Ví dụ:

```sql
-- Quan sát thống kê theo container ở root, nếu đủ quyền.
SELECT con_id, name, value
FROM   v$con_sysstat
WHERE  name = 'execute count'
ORDER BY con_id;
```

Nếu truy vấn `V$SYSSTAT` ở root mà nhận row `CON_ID=0`, đó là ý nghĩa tổng hợp do view thiết kế, không phải SQL đã “làm rơi” tất cả `CON_ID` của PDB. Tương tự, một số `GV$` view còn cần `INST_ID` để tổng hợp đúng trong RAC.

**Không áp dụng công thức phổ quát “cứ thêm `CON_ID` là số liệu chia theo PDB”.** Trước khi xây hệ thống monitoring, đọc định nghĩa của chính view đang dùng và xác định metric là instance-wide hay PDB-specific.

## 13. Common user, local user và phạm vi quyền cũng là metadata

Tham số là một loại metadata quản trị; **user, role, privilege, profile, object và grant** cũng có phạm vi container. Cần tách:

- **Common user**: danh tính được định nghĩa để tồn tại xuyên các container thuộc phạm vi root; thường tên user tự tạo ở CDB root có tiền tố mặc định `C##`, tùy cấu hình.
- **Local user**: chỉ thuộc một PDB; có thể có cùng username ở hai PDB khác nhau nhưng là hai user độc lập.
- **Common privilege/grant**: quyền được cấp với phạm vi `CONTAINER=ALL` theo điều kiện của Oracle, khả dụng trong các PDB thuộc phạm vi tương ứng.
- **Local privilege/grant**: quyền được cấp với `CONTAINER=CURRENT`, chỉ có hiệu lực tại container cấp quyền.

### 13.1. Kiểm tra user thuộc container nào

```sql
-- Từ một PDB: chỉ thấy metadata user trong current PDB.
SELECT username, common, oracle_maintained
FROM   dba_users
ORDER BY username;

-- Từ CDB$ROOT: có thể thấy nhiều PDB khi được phép.
SELECT con_id, username, common, oracle_maintained
FROM   cdb_users
ORDER BY con_id, username;
```

`COMMON='YES'` nói user là common user; **không tự nói** user đó đã được cấp mọi quyền trên mọi bảng ở mọi PDB. Một common user có thể có quyền common ở một số chức năng và **local grants** riêng trong một PDB.

### 13.2. Ví dụ hiệu lực của common grant và local grant

```text
CDB$ROOT: C##REPORT có common role/quyền ở phạm vi được cấp

SALES_PDB: C##REPORT còn có local SELECT trên APP.DAILY_SALES
HR_PDB:    Không có local SELECT trên HR.SALARY

Kết quả:
  C##REPORT có thể dùng quyền common khi kết nối phù hợp,
  nhưng không thể từ quyền local tại SALES_PDB mà đọc HR.SALARY.
```

`CONTAINER=ALL` trong `GRANT` là quyết định phân quyền xuyên nhiều tenant, có rủi ro bảo mật. Không dùng nó để khắc phục truy vấn metadata thiếu row khi chưa làm rõ yêu cầu và ranh giới quyền.

## 14. Phân biệt metadata cấu trúc với metadata vận hành PDB

| Câu hỏi quản trị | View điển hình | Ghi chú |
| --- | --- | --- |
| CDB hiện tại có phải multitenant không? | `V$DATABASE.CDB` | Giá trị `YES/NO` |
| Tên/ID/open mode các container? | `V$CONTAINERS`, `V$PDBS` | Phân biệt root/seed/PDB, xem `RESTRICTED` |
| Danh mục PDB và trạng thái lifecycle? | `DBA_PDBS`, `CDB_PDBS` ở root | Metadata về PDB, không phải toàn bộ bảng bên trong PDB |
| Bảng nào có trong PDB hiện tại? | `DBA_TABLES` hoặc `USER_TABLES`/`ALL_TABLES` | Chịu ảnh hưởng quyền đối tượng và current container |
| Tên bảng xuất hiện ở những PDB nào? | `CDB_TABLES` ở root | Chỉ đầy đủ khi PDB mở và quyền/`CONTAINER_DATA` cho phép |
| User là local hay common? | `DBA_USERS.COMMON`, `CDB_USERS.COMMON` | Local/common khác scope của grant |
| Service thuộc PDB nào? | `V$SERVICES`, `CDB_SERVICES` (nếu được hỗ trợ) | Service là đường vào PDB; không phải schema/table |
| Parameter có thể override tại PDB không? | `V$SYSTEM_PARAMETER.ISPDB_MODIFIABLE` | Kết hợp `ISSYS_MODIFIABLE`, `SCOPE`, `CONTAINER` |
| Tham số nào lưu persistent? | `V$SPPARAMETER`, metadata cấu hình tương ứng | Đối chiếu với runtime values trong PDB |

### 14.1. Ví dụ: `DBA_PDBS` khác `DBA_TABLES`

```sql
-- Từ root, có quyền thích hợp: metadata về sự tồn tại PDB.
SELECT pdb_id, pdb_name, status
FROM   dba_pdbs
ORDER BY pdb_id;

-- Từ root: DBA_TABLES là metadata bảng trong root.
SELECT owner, table_name
FROM   dba_tables
WHERE  owner = 'APP'
ORDER BY table_name;

-- Từ root: CDB_TABLES có thể trả metadata bảng trong những PDB nhìn thấy.
SELECT con_id, owner, table_name
FROM   cdb_tables
WHERE  owner = 'APP'
ORDER BY con_id, table_name;
```

Một PDB có thể xuất hiện trong `DBA_PDBS` ngay cả khi đang `MOUNTED`; điều đó không đảm bảo `CDB_TABLES` trả đầy đủ chi tiết schema của PDB đó.

## 15. Quy trình đọc metadata trước khi thay đổi parameter

Đây là quy trình nên áp dụng trong design review/change request.

**Bước 1 — Chốt CDB/release/instance/container.** Ghi service đăng nhập, kết quả `SYS_CONTEXT`, tên PDB và trạng thái open mode. Trong RAC, ghi rõ instance/session.

**Bước 2 — Chọn tham số.** Lấy tên và purpose chính xác; tra `V$SYSTEM_PARAMETER.ISPDB_MODIFIABLE`, `ISSYS_MODIFIABLE`, `ISSES_MODIFIABLE`, điều kiện của release.

**Bước 3 — Đọc root và PDB riêng.** Quan sát `V$SYSTEM_PARAMETER` tại root, sau đó tại từng PDB cần ảnh hưởng; kiểm tra session override bằng `V$PARAMETER`, persistent settings bằng `V$SPPARAMETER` khi phù hợp.

**Bước 4 — Xác định kế thừa/override.** Không dựa vào duy nhất `ISDEFAULT`; dùng lịch sử cấu hình/DDL thay đổi và quan sát runtime/persistent values để biết PDB nào đang có thiết lập riêng.

**Bước 5 — Đánh giá blast radius.** Với `CONTAINER=CURRENT` ở root, xét các PDB đang kế thừa. Với `CONTAINER=ALL`, nhận diện các override có thể bị xóa. Với `SCOPE=SPFILE`, lên kế hoạch mở lại PDB/CDB theo chu kỳ bảo trì phù hợp.

**Bước 6 — Phê duyệt, thực hiện, xác nhận.** Chỉ DBA có quyền thực hiện `ALTER SYSTEM`. Sau thay đổi, quan sát đúng view trong đúng container, kể cả sau reopen nếu cần xác thực persistence.

**Bước 7 — Ghi lại trạng thái.** Lưu tên parameter, giá trị trước/sau ở root và PDB, `SCOPE`, `CONTAINER`, owner phê duyệt và thời điểm cần xem xét lại.

### 15.1. Mẫu phiếu thay đổi tham số

| Trường | Ví dụ |
| --- | --- |
| CDB / version | `CDB01`, Oracle 19c RU phù hợp |
| Instance | `cdb01_1`, với RAC ghi đủ các instance |
| PDB mục tiêu | `SALES_PDB` |
| Tham số | `STATISTICS_LEVEL` |
| `ISPDB_MODIFIABLE` | Giá trị **đọc trực tiếp** tại môi trường |
| Current root value | `TYPICAL` |
| Current PDB value | `TYPICAL` hoặc override hiện có |
| Target value | `ALL` |
| `SCOPE`/`CONTAINER` | `BOTH` / `CURRENT` tại `SALES_PDB` |
| Ảnh hưởng người dùng | Thay đổi thống kê/overhead liên quan workload PDB |
| Xác nhận sau thay đổi | Query `V$SYSTEM_PARAMETER` tại `SALES_PDB` và PDB khác nếu liên quan |
| Rollback | Phương án `RESET`/khôi phục theo tài liệu, đã thẩm định |

## 16. Bài thực hành chỉ đọc: so sánh root với một PDB

> Lab này không yêu cầu tạo/dừng PDB, đổi tham số hoặc đọc dữ liệu người dùng. Nếu tài khoản chỉ có quyền trong PDB, thực hiện phần PDB; phần root cần DBA có quyền phù hợp.

### Bước A — Xác định CDB và container hiện tại

```sql
SELECT cdb, name, dbid
FROM   v$database;

SELECT SYS_CONTEXT('USERENV','CON_NAME') AS current_container,
       SYS_CONTEXT('USERENV','CON_ID')   AS current_con_id
FROM   dual;
```

`V$DATABASE.CDB` cho biết database có phải CDB hay không; tên/DBID liên quan đến database, không đại diện cho schema của PDB ứng dụng.

### Bước B — Tại `CDB$ROOT`, ghi metadata các PDB

```sql
SELECT con_id, name, open_mode, restricted
FROM   v$pdbs
ORDER BY con_id;

SELECT name, display_value, ispdb_modifiable,
       issys_modifiable, isses_modifiable
FROM   v$system_parameter
WHERE  name IN ('statistics_level','optimizer_mode','open_cursors')
ORDER BY name;
```

Ghi giá trị root, đừng suy rằng đó cũng là effective value của mọi PDB.

### Bước C — Kết nối trực tiếp vào `SALES_PDB`

Kết nối bằng một **PDB service** được DBA cung cấp (ví dụ `sales_app.example.com`), rồi chạy:

```sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS current_container
FROM   dual;

SELECT name, display_value, ispdb_modifiable,
       issys_modifiable, isses_modifiable
FROM   v$system_parameter
WHERE  name IN ('statistics_level','optimizer_mode','open_cursors')
ORDER BY name;
```

Nếu tài khoản đủ quyền:

```sql
SELECT owner, table_name
FROM   dba_tables
WHERE  owner = 'APP'
ORDER BY table_name;
```

Nếu thiếu quyền `DBA_TABLES`, có thể thay bằng `ALL_TABLES` hoặc `USER_TABLES` để quan sát những đối tượng mà tài khoản đang được phép biết. Kết quả của ba view này khác nhau về **quyền**, kể cả ở cùng một PDB.

### Bước D — Quay lại root và kiểm kê metadata đa container

```sql
SELECT con_id, owner, table_name
FROM   cdb_tables
WHERE  owner = 'APP'
ORDER BY con_id, table_name;
```

Đối chiếu với `V$PDBS` và phạm vi `CONTAINER_DATA`. Nếu `SALES_PDB` không xuất hiện, không kết luận bảng đã mất trước khi kiểm tra quyền, trạng thái mở và container thực tế.

### Bước E — Giải thích kết quả

Ghi lại ít nhất bốn nhận xét:

1. Current container của mỗi câu query là gì?
2. `V$SYSTEM_PARAMETER` hiển thị tham số nào có thể cấu hình ở PDB?
3. `DBA_TABLES` ở root và PDB khác nhau vì nguyên nhân nào?
4. `CDB_TABLES` có `CON_ID` nào và liệu tập kết quả đã được cấp quyền xem tất cả PDB chưa?

## 17. Tình huống xử lý sự cố

### Tình huống 1 — DBA đổi tham số ở root nhưng một PDB vẫn giữ giá trị cũ

**Quan sát:** `STATISTICS_LEVEL` ở root đã thành `TYPICAL`, nhưng `HR_PDB` tiếp tục hiển thị `ALL`.

**Giải thích có thể:** `HR_PDB` từng có override riêng. Nếu root đổi với `CONTAINER=CURRENT`, các PDB còn kế thừa nhận giá trị root theo quy tắc áp dụng, còn PDB có override giữ giá trị riêng. Cũng cần kiểm tra việc setting mới chỉ ở `SPFILE` và chưa được áp dụng runtime, hoặc có session override.

**Hướng xử lý:** xác minh `ISPDB_MODIFIABLE`, đọc runtime và persistent config trong root/PDB, kiểm tra change record. Chỉ `RESET` override khi thật sự muốn PDB quay lại kế thừa.

### Tình huống 2 — Root query `DBA_TABLES` không thấy bảng app dù ứng dụng chạy bình thường

**Quan sát:** `SALES_PDB.APP.ORDERS` tồn tại và ứng dụng truy vấn được, nhưng DBA xem `DBA_TABLES` tại `CDB$ROOT` không thấy `APP.ORDERS`.

**Giải thích:** `DBA_TABLES` tại root mô tả metadata root; bảng ứng dụng được tạo ở PDB. Dùng `DBA_TABLES` **trong SALES_PDB** hoặc `CDB_TABLES` **từ root** khi đủ quyền.

### Tình huống 3 — Common user query `CDB_USERS` chỉ thấy `CON_ID=1`

**Quan sát:** View truy vấn được, không lỗi ORA, nhưng không có row user PDB.

**Giải thích:** `CONTAINER_DATA` mặc định/được cấu hình có thể chỉ cho thấy root. Tài khoản còn phải có quyền dictionary phù hợp và các PDB cần ở trạng thái hỗ trợ xem metadata. Không suy rằng user PDB không tồn tại.

### Tình huống 4 — Một PDB có row trong `DBA_PDBS` nhưng không có bảng trong `CDB_TABLES`

**Quan sát:** `HR_PDB` đang `MOUNTED` trong `V$PDBS`, `DBA_PDBS` vẫn liệt kê PDB đó.

**Giải thích:** View quản lý PDB cung cấp metadata lifecycle từ root; `CDB_TABLES` cần truy vấn metadata của PDB đang mở và phụ thuộc visibility. PDB đóng không có nghĩa tables của nó đã bị xóa.

### Tình huống 5 — Monitoring đếm gấp đôi PDB trong RAC

**Quan sát:** Query từ `GV$CONTAINERS` trả hai row `SALES_PDB`.

**Giải thích:** Có thể cùng PDB đang mở trên hai instance, khác `INST_ID`. Dùng `(INST_ID, CON_ID)` để xem trạng thái theo instance; dùng distinct container identity khi đếm PDB logic trong một CDB.

### Tình huống 6 — PDB có `SCOPE=MEMORY` rồi reopen mất cấu hình

**Quan sát:** DBA đổi tham số thành `ALL` trong `SALES_PDB`, ban đầu thấy có hiệu lực; sau maintenance PDB quay về giá trị root.

**Giải thích:** `SCOPE=MEMORY` chỉ áp dụng runtime; không bền vững qua reopen theo quy tắc Oracle. Nếu cần persistent override, lên kế hoạch `SCOPE=BOTH` hoặc `SPFILE` tùy tính động và quy trình thay đổi.

### Tình huống 7 — Sau unplug/plug, cấu hình PDB vẫn khác root mới

**Quan sát:** `HR_PDB` được chuyển sang CDB khác; một vài tham số vẫn theo override cũ dù root mới khác.

**Giải thích:** Oracle có thể mang theo các giá trị tham số PDB đã đặt bền vững (`SPFILE`/`BOTH`) trong XML metadata của PDB khi unplug/plug. Cần review cấu hình PDB đích, giới hạn/compatibility và quy trình plug-in sau migration; đừng mặc định mọi tham số đều kế thừa root mới.

## 18. Những nhầm lẫn thường gặp

1. **“PDB là một instance nhỏ.”** Sai: PDB là container logic dùng chung nhiều tài nguyên instance của CDB.
2. **“`ALTER SYSTEM` trong root luôn thay tất cả PDB.”** Chưa đúng: phải xét tham số có override, `CONTAINER`, `SCOPE` và thời điểm áp dụng.
3. **“`CONTAINER=ALL` không làm mất cấu hình riêng.”** Sai với `ALTER SYSTEM SET`: nó có thể đặt lại inheritance ở các PDB.
4. **“`ISPDB_MODIFIABLE=TRUE` nghĩa là tham số đổi được ngay không cần restart.”** Sai: còn `ISSYS_MODIFIABLE` và `SCOPE`.
5. **“`V$PARAMETER` và `V$SYSTEM_PARAMETER` luôn giống nhau.”** Sai nếu session đã override hoặc có khác biệt phạm vi.
6. **“`SCOPE=MEMORY` vẫn còn sau reopen PDB.”** Thông thường không; muốn persistent phải dùng cách lưu được hỗ trợ.
7. **“`ISDEFAULT='TRUE'` chắc chắn nghĩa là PDB đang inherit root.”** Không đủ căn cứ.
8. **“`DBA_TABLES` trong root liệt kê table của mọi PDB.”** Sai: root là một current container riêng.
9. **“Đổi `DBA_TABLES` thành `CDB_TABLES` là thấy hết tenant.”** Sai nếu quyền dictionary, `CONTAINER_DATA` hoặc trạng thái PDB không cho phép.
10. **“`CON_ID=0` là một PDB bị lỗi.”** Sai: thường biểu diễn phạm vi toàn CDB/instance.
11. **“`CON_ID=3` có nghĩa SALES ở mọi CDB.”** Sai: ID là local theo CDB và thời điểm.
12. **“Common user có thể truy cập mọi bảng mọi PDB.”** Sai: còn container-level privileges và quyền object.
13. **“Mọi `V$` đều có breakdown theo PDB.”** Sai: một số view là instance-level; dùng view `V$CON_*` tương ứng khi có.
14. **“PDB đã đóng thì metadata của nó biến mất.”** Sai: cần phân biệt metadata tồn tại của PDB và khả năng truy vấn schema metadata khi PDB đang mở.
15. **“Một query `CDB_*` không trả đủ nghĩa là dữ liệu đã mất.”** Không kết luận như vậy trước khi kiểm tra quyền, open mode, restricted mode và query filters.

## 19. Câu hỏi ôn tập

**Câu 1.** Một parameter có `ISSYS_MODIFIABLE=IMMEDIATE`, `ISPDB_MODIFIABLE=FALSE`. Có thể dùng `ALTER SYSTEM SET` trong `SALES_PDB` để đặt riêng giá trị không? Vì sao?

**Câu 2.** Root đặt `PARAM_X=C` với `CONTAINER=CURRENT`; `HR_PDB` từng override `PARAM_X=B`. Giá trị `HR_PDB` sau khi thay đổi đã có hiệu lực là gì?

**Câu 3.** Khi root chạy `ALTER SYSTEM SET ... CONTAINER=ALL`, điều gì có thể xảy ra với inheritance của tham số trong các PDB?

**Câu 4.** `CDB_USERS` query ở root của common user chỉ hiển thị `CON_ID=1`, trong khi `V$PDBS` có `SALES_PDB` và `HR_PDB` đang mở. Nêu hai điều cần kiểm tra trước khi kết luận không có local users.

**Câu 5.** Tại sao `SELECT ... FROM DBA_TABLES` ở `CDB$ROOT` và `SALES_PDB` có thể trả kết quả khác nhau dù cùng user quản trị?

**Câu 6.** `V$SYSSTAT` ở root có `CON_ID=0`. Muốn xem breakdown theo PDB, nên điều tra view nào?

**Câu 7.** DBA chạy `ALTER SYSTEM SET ... SCOPE=SPFILE` ở PDB. Ngay lập tức `V$SYSTEM_PARAMETER` phải hiển thị giá trị mới không?

**Câu 8.** Sau khi `ALTER SESSION` tại một session, vì sao `V$PARAMETER` có thể khác `V$SYSTEM_PARAMETER` trong cùng container?

<details>
<summary>Gợi ý đáp án</summary>

1. **Không.** `ISPDB_MODIFIABLE=FALSE` không cho phép PDB override; khả năng đổi runtime không quyết định scope PDB.
2. **B**, nếu override vẫn còn, vì thay đổi root `CONTAINER=CURRENT` không đặt lại inheritance của PDB.
3. Thao tác có thể **đặt inheritance của tham số về true** trong toàn CDB, thay override từng PDB; cần review blast radius.
4. Kiểm tra **`CONTAINER_DATA`** và quyền dictionary/view, đồng thời trạng thái mở/restricted của PDB và điều kiện lọc câu SQL.
5. Vì `DBA_TABLES` mô tả metadata trong **current container**, còn các PDB có schema và đối tượng riêng.
6. Xem **`V$CON_SYSSTAT`** hoặc `GV$CON_SYSSTAT` theo instance và `CON_ID`.
7. **Không bắt buộc.** `SPFILE` là persistent setting cho lần mở lại PDB/khởi động lại phù hợp; runtime có thể chưa đổi.
8. `V$PARAMETER` phản ánh giá trị session sau `ALTER SESSION`, còn `V$SYSTEM_PARAMETER` là giá trị hệ thống phục vụ session hiện hành/mới.

</details>

## 20. Tài liệu Oracle chính thức để đối chiếu

Các khái niệm/cú pháp phải được đối chiếu với release thực tế, nhất là khi triển khai Oracle Database 19c, 21c hoặc Oracle AI Database 26ai:

1. [Oracle Database 19c Multitenant Administrator's Guide — Administering PDBs](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/administering-pdbs-with-sql-plus.html): `ISPDB_MODIFIABLE`, tham số PDB, `SCOPE`, `ALTER SYSTEM`, metadata khi unplug/plug.
2. [Oracle Database 19c Multitenant Administrator's Guide — Administering a CDB](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/administering-a-cdb-with-sql-plus.html): inheritance tại root, `CONTAINER=CURRENT`/`ALL`, phạm vi câu lệnh và common/local security.
3. [Oracle Database 19c SQL Language Reference — ALTER SYSTEM](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-SYSTEM.html): ngữ nghĩa chính thức của `SCOPE`, `CONTAINER` và điều kiện quyền.
4. [Oracle Database 19c Administrator's Guide — Creating and Configuring an Oracle Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/creating-and-configuring-an-oracle-database.html): SPFILE, PFILE, parameter persistence và `ALTER SYSTEM RESET`.
5. [Oracle Database 19c Multitenant Administrator's Guide — Monitoring CDBs and PDBs](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/viewing-information-about-cdbs-and-pdbs-with-sql-plus.html): `V$CONTAINERS`, `V$PDBS`, `CDB_*`, `DBA_*`, container data objects và `CON_ID`.
6. [Oracle Database 19c Database Reference — CDB_* Views](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/cdb_-views.html): giới hạn metadata, quyền và `CONTAINER_DATA`, hành vi với PDB mở/đóng.
7. [Oracle Database 19c Database Reference — V$PARAMETER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-PARAMETER.html), [V$SYSTEM_PARAMETER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYSTEM_PARAMETER.html), [V$SPPARAMETER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SPPARAMETER.html): session/system/persistent parameter metadata.
8. [Oracle Database 19c Multitenant Administrator's Guide — Overview of the Multitenant Architecture](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/overview-of-the-multitenant-architecture.html): data dictionary architecture, metadata/data links và common/local objects.
9. [Oracle Database 19c Security Guide — Managing Commonly and Locally Granted Privileges](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-commonly-and-locally-granted-privileges.html): common/local grants, `CONTAINER_DATA` và ranh giới tenant.
10. [Oracle AI Database 26ai — Data Dictionary and Dynamic Performance Views](https://docs.oracle.com/en/database/oracle/oracle-database/26/cncpt/data-dictionary-and-dynamic-performance-views.html): tài liệu kiến trúc ở release mới để so sánh thay đổi.

**Cách nhớ nhất quán:** Muốn hiểu một kết quả Oracle Multitenant, xác định **current container → loại view/parameter → phạm vi instance/session/root/PDB → quyền và `CONTAINER_DATA` → trạng thái PDB → `SCOPE`/`CONTAINER` nếu có thay đổi cấu hình**. Cùng một tên tham số hay view không bảo đảm cùng giá trị hoặc cùng tập row giữa `CDB$ROOT` và các PDB.
