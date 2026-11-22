# Common user, local user, common role và local role trong Oracle CDB/PDB

Trong kiến trúc **Oracle Multitenant**, một **container database (CDB)** có thể chứa nhiều **pluggable database (PDB)**. Mỗi PDB có dữ liệu và đối tượng nghiệp vụ riêng, nhưng các PDB trong cùng CDB chia sẻ một số thành phần hạ tầng và quản trị. Vì thế, khi tạo tài khoản hoặc cấp quyền, câu hỏi không chỉ là **“user được làm gì?”** mà còn là **“user hoặc role này tồn tại ở container nào, và quyền có hiệu lực ở container nào?”**

Oracle phân biệt bốn khái niệm quan trọng:

- **Common user**: danh tính được tạo ở cấp container chung, hiện diện trong nhiều container thuộc phạm vi chung đó.
- **Local user**: danh tính chỉ được tạo và quản lý trong **một PDB**.
- **Common role**: role có tên và định nghĩa chung trong nhiều container, dùng làm cơ sở phân quyền xuyên phạm vi CDB hoặc application container tương ứng.
- **Local role**: role chỉ tồn tại trong một PDB, phù hợp phân quyền theo nghiệp vụ của PDB đó.

Một user là **danh tính có thể đăng nhập** nếu đáp ứng cơ chế xác thực và có quyền mở session. Một role là **tập quyền có thể cấp cho user hoặc role khác**; bản thân role không phải tài khoản ứng dụng để đăng nhập. Và điều quan trọng nhất: **common user không mặc nhiên có quyền đọc dữ liệu của mọi PDB; common role cũng không tự mang mọi quyền trên mọi PDB.** Phạm vi *tồn tại của danh tính/role* và phạm vi *hiệu lực của từng grant* phải được xem riêng.

## 1. Bối cảnh: CDB root và các PDB

Một CDB Oracle thông thường gồm **`CDB$ROOT`** (root), **`PDB$SEED`** (PDB mẫu hệ thống) và một hoặc nhiều PDB ứng dụng. Ví dụ:

```text
                         CDB: SALES_CDB
                               |
           +-------------------+--------------------+
           |                   |                    |
       CDB$ROOT             PDB$SEED           Các PDB ứng dụng
     Quản trị CDB         PDB mẫu hệ thống          |
                                                  +-- SALES_DEV
                                                  |    Schema, bảng, user, role riêng
                                                  |
                                                  +-- SALES_TEST
                                                  |    Schema, bảng, user, role riêng
                                                  |
                                                  +-- SALES_PROD
                                                       Schema, bảng, user, role riêng
```

Sơ đồ chỉ mô tả container logic. Trong triển khai thật, **không nên dùng chung CDB cho DEV/TEST/PROD chỉ vì kỹ thuật cho phép**: các PDB cùng CDB còn chia sẻ nhiều rủi ro ở cấp instance, lưu trữ, bảo trì và quản trị. Trong bài học, các tên `SALES_DEV`, `SALES_TEST`, `SALES_PROD` dùng để minh họa **ranh giới quyền**; môi trường thật cần quyết định mức cách ly theo yêu cầu an toàn, khả dụng và quản trị.

Một CDB còn có thể có **application root/application PDB** trong kiến trúc *application container*. Các thực thể *application common user/role* được tạo trong **application root** và có phạm vi liên quan đến application container đó. Bài này trước hết giải thích **CDB common user/role tạo tại `CDB$ROOT`** và **local user/role tại PDB thông thường**, rồi chỉ ra khác biệt của trường hợp application container ở phần sau.

### 1.1. Câu hỏi đầu tiên: session đang ở container nào?

Trong SQL*Plus hoặc SQLcl, có thể dùng lệnh của công cụ:

```text
SHOW CON_NAME
```

Với SQL chuẩn của Oracle, câu truy vấn chỉ đọc sau hữu ích cả khi chạy qua JDBC:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

`CON_NAME` giúp phân biệt root và PDB; `SERVICE_NAME` cho biết dịch vụ session đang dùng; `SESSION_USER` chỉ danh tính đăng nhập. `CURRENT_SCHEMA` có thể khác `SESSION_USER` nếu một session đổi schema mặc định để phân giải tên đối tượng; **đổi `CURRENT_SCHEMA` không cấp thêm quyền**.

Người vận hành hoặc developer cần xác minh **đúng service/PDB** trước khi tạo user, cấp role hoặc chạy migration. Cùng tên user ở hai PDB không bảo đảm đó là cùng danh tính.

## 2. Phân biệt *user* và *role* trước khi xét common/local

| Khía cạnh | User | Role |
|---|---|---|
| Bản chất | Danh tính database, có thể có cơ chế xác thực và schema sở hữu đối tượng | Tập hợp quyền được định nghĩa để cấp cho principal khác |
| Đăng nhập | Có thể tạo session nếu account hợp lệ, xác thực được và được cấp `CREATE SESSION` khi cần | Role không phải login account |
| Sở hữu đối tượng | Schema tương ứng có thể sở hữu table, view, package, sequence, v.v. theo quyền | Role không sở hữu schema/table như user |
| Cấp quyền | Có thể nhận quyền system, object và role | Có thể nhận quyền và được grant cho user/role khác theo quy định Oracle |
| Quản trị | `CREATE USER`, `ALTER USER`, `DROP USER` | `CREATE ROLE`, `ALTER ROLE` khi phù hợp, `DROP ROLE` |
| Common/local | Quyết định user tồn tại ở container nào | Quyết định role tồn tại ở container nào |

Ví dụ, một ứng dụng thường đăng nhập bằng user `APP_RUNTIME`; quyền đọc báo cáo có thể được đóng gói trong role `APP_REPORT_READER`. Tài khoản có thể nhận role này, nhưng không phải cứ nhận role là được đăng nhập: quyền `CREATE SESSION` và cơ chế xác thực phải đáp ứng điều kiện. Cũng cần nhớ rằng các **đơn vị PL/SQL definer-rights thông thường không sử dụng quyền thông qua role để kiểm tra quyền trực tiếp trên đối tượng**; nếu một package cần truy cập bảng của schema khác, phải xem cơ chế quyền thích hợp và các grant trực tiếp cần thiết.

## 3. Common user: danh tính chung của CDB

**CDB common user** được tạo tại **`CDB$ROOT`** và có cùng tên trong các container thuộc CDB. Thông thường, đó là danh tính dành cho quản trị, giám sát hoặc nghiệp vụ quản trị cần hoạt động tại nhiều PDB theo phạm vi được phép.

Tên common user tự tạo thường bắt đầu bằng **`C##`**, là tiền tố mặc định của tham số Oracle `COMMON_USER_PREFIX`; các user hệ thống do Oracle quản lý như `SYS` và `SYSTEM` có quy tắc riêng. Không nên chỉnh tham số tiền tố chỉ để né quy ước tên. Các quy tắc đặt tên cụ thể còn phụ thuộc cấu hình và phiên bản Oracle.

Ví dụ minh họa của người có quyền quản trị **sau khi xác nhận đang ở `CDB$ROOT`**:

```sql
-- Thực hiện bởi DBA có quyền trong CDB root.
-- Thay <SECRET_DO_DBA_CAP> bằng credential bảo mật thật qua quy trình được duyệt.
CREATE USER C##LAB_AUDITOR
IDENTIFIED BY "<SECRET_DO_DBA_CAP>"
CONTAINER = ALL;
```

`CONTAINER = ALL` trong câu lệnh **tạo common user** xác định phạm vi tạo ở CDB root và các PDB liên quan. Đây là ví dụ cú pháp phục vụ học tập; **không chạy nguyên văn placeholder mật khẩu**, không lưu mật khẩu thật trong tệp SQL đã commit hoặc lịch sử terminal dùng chung.

### 3.1. Common user hiện diện ở đâu?

```text
CDB$ROOT:    C##LAB_AUDITOR   (common user)
                  |
                  +---- PDB_A: C##LAB_AUDITOR
                  |
                  +---- PDB_B: C##LAB_AUDITOR
                  |
                  +---- PDB_C: C##LAB_AUDITOR
```

Danh tính này được quản lý chung từ root. Việc tạo common user không có nghĩa nó sở hữu chung một bộ bảng ở tất cả PDB: nếu được phép tạo đối tượng, schema mang tên đó trong mỗi PDB có phạm vi đối tượng riêng. Tương tự, user dùng cùng danh tính không tự **chuyển session** sang PDB khác hoặc tự đọc được bảng của PDB khác.

Để truy cập một PDB, account vẫn cần có điều kiện xác thực, quyền mở session và đường kết nối phù hợp. Những đặc quyền khác có thể được **grant commonly** từ root hoặc **grant locally** trong từng PDB. Vì vậy common user có thể có nhiều quyền ở PDB A nhưng rất ít quyền ở PDB B.

### 3.2. Khi nào common user phù hợp?

- Danh tính quản trị/giám sát có phạm vi công việc nhiều PDB và được kiểm soát bởi đội DBA.
- Công cụ quản lý cần một identity nhất quán tại nhiều container, với quyền từng PDB được thiết kế rõ ràng.
- Quy trình quản trị CDB có thực sự cần phân quyền chung từ root.

Không nên dùng common user chỉ vì “đỡ phải tạo user trong từng PDB” khi ứng dụng phục vụ một PDB duy nhất. Một common identity làm **phạm vi tác động của lỗi cấp quyền, credential bị lộ hoặc cấu hình sai** dễ rộng hơn. Tài khoản runtime của ứng dụng một PDB thường phù hợp với local user.

### 3.3. Common user có quyền quản trị mặc định không?

**Không.** Tiền tố `C##` hoặc trạng thái common không tự làm một account trở thành DBA/SYSDBA. Chỉ cấp đặc quyền cần thiết theo công việc. Ví dụ sau là một **local grant** cho common user, được thực hiện trong PDB mục tiêu bởi người có quyền:

```sql
-- Đang kết nối trực tiếp tới PDB_A bằng service của PDB_A.
GRANT CREATE SESSION TO C##LAB_AUDITOR CONTAINER = CURRENT;
```

Grant này chỉ áp dụng cho container hiện tại. Nếu PDB B chưa cấp quyền tương ứng, không được mặc nhiên coi common user có thể đăng nhập PDB B. Đừng cấp `CREATE SESSION` hoặc quyền truy cập dữ liệu ở mọi PDB bằng `CONTAINER = ALL` chỉ để sửa lỗi một ứng dụng tại một PDB.

## 4. Local user: danh tính riêng của một PDB

**Local user** được tạo **trong một PDB** và chỉ tồn tại trong PDB đó. Đây là kiểu user phù hợp với tài khoản ứng dụng, schema owner, tài khoản migration hoặc người dùng nghiệp vụ gắn với một PDB cụ thể.

Ví dụ trong PDB `SALES_DEV`:

```sql
-- Trước khi chạy: bảo đảm CON_NAME = SALES_DEV.
-- Dành cho người được giao quyền tạo user trong PDB DEV.
CREATE USER SALES_APP
IDENTIFIED BY "<SECRET_DO_DBA_CAP>"
CONTAINER = CURRENT;

GRANT CREATE SESSION TO SALES_APP CONTAINER = CURRENT;
```

`CONTAINER = CURRENT` biểu thị thao tác trong container hiện tại. Với local user được tạo ở PDB, tài khoản `SALES_APP` không tự xuất hiện tại PDB khác. Nếu `SALES_TEST` cũng có user `SALES_APP`, đó là **local user khác**, có thể có mật khẩu, trạng thái, profile, schema object và quyền độc lập.

```text
PDB SALES_DEV:   SALES_APP  (local user A)
PDB SALES_TEST:  SALES_APP  (local user B)
PDB SALES_PROD:  SALES_APP  (local user C)

Tên giống nhau != cùng account hoặc cùng quyền.
```

### 4.1. Local user không điều khiển root

Một local user không được tạo tại root để tự “nhân bản” qua PDB. Tài khoản chỉ có identity trong PDB của mình. Quyền `CREATE SESSION`, `CREATE TABLE`, `SELECT` trên bảng nghiệp vụ, quota của tablespace và role membership cũng được xét trong phạm vi PDB tương ứng.

Trong Oracle, các thao tác từ một phiên PDB không tự động ghi vào schema cùng tên ở một PDB khác. Nếu ứng dụng DEV cố kết nối PDB production bằng credential DEV, cần xét riêng xem ở PDB production có user tương ứng và quyền gì; nên bổ sung cách ly endpoint, network và secret để giảm rủi ro cấu hình nhầm.

### 4.2. Những lý do nên dùng local user cho ứng dụng

- **Ranh giới dữ liệu rõ:** danh tính chỉ có nghĩa trong một PDB, phù hợp một workload hoặc một môi trường.
- **Quyền tối thiểu:** dễ giới hạn quyền DML hoặc `EXECUTE` đến đúng đối tượng ứng dụng cần.
- **Vòng đời riêng:** có thể khóa, thay mật khẩu hoặc thu hồi local user khi ứng dụng được nghỉ mà không thay đổi common identity của CDB.
- **Quản lý môi trường:** DEV/TEST/PROD có credential, quota, role và chính sách truy cập riêng.

Không có nghĩa local user là một biên cô lập hạ tầng hoàn chỉnh: nhiều PDB chung CDB vẫn chia sẻ tài nguyên ở cấp cao hơn. Bài toán vận hành/khả dụng cần xét thêm kiến trúc triển khai.

## 5. Common role: role hiện diện trong nhiều container

**CDB common role** được tạo từ `CDB$ROOT`, có cùng tên trong các container thuộc CDB và thường mang tiền tố `C##` theo quy tắc tên common role. Nó hữu ích khi tổ chức muốn có **một vai trò quản trị hoặc giám sát chung** để cấp cho nhiều principal, trong khi vẫn kiểm soát đặc quyền áp dụng tại từng container.

Ví dụ tạo common role ở root:

```sql
-- Thực hiện trong CDB$ROOT bằng account được cấp quyền.
CREATE ROLE C##LAB_OBSERVER CONTAINER = ALL;
```

Tạo role thành công mới chỉ tạo **tên và đối tượng role** trong phạm vi common. Nó không tự chứa `SELECT ANY TABLE`, `DBA`, `CREATE USER` hoặc quyền nào khác. Cần thiết kế quyền và membership một cách tường minh.

### 5.1. Common role được grant như thế nào?

Có hai khái niệm cần tách:

1. **Common grant:** được thực hiện từ root với `CONTAINER = ALL` theo điều kiện của Oracle, thường là cấp quyền/role cho common principal và có hiệu lực trên phạm vi các container liên quan.
2. **Local grant:** được thực hiện trong container hiện tại với `CONTAINER = CURRENT`, chỉ có hiệu lực trong container đó, kể cả khi principal nhận grant là **common user hoặc common role**.

Ví dụ, sau khi tạo `C##LAB_OBSERVER` và `C##LAB_AUDITOR` trong root:

```sql
-- Thực hiện trong CDB$ROOT: membership chung cho common user.
GRANT C##LAB_OBSERVER TO C##LAB_AUDITOR CONTAINER = ALL;
```

Role membership này có phạm vi chung. Nhưng nếu role mới được tạo chưa được cấp quyền truy vấn nào thì việc user có role vẫn **không tự cho phép đọc bảng**. Một PDB riêng có thể cấp quyền đọc đối tượng phù hợp vào role này **tại PDB đó**, ví dụ:

```sql
-- Thực hiện trong PDB_A với quyền trên đối tượng APP_OWNER.AUDIT_EVENTS.
GRANT SELECT ON APP_OWNER.AUDIT_EVENTS
TO C##LAB_OBSERVER;
```

Ví dụ trên là **object privilege grant tại PDB_A**; nó không biến bảng `AUDIT_EVENTS` của PDB_A thành bảng chung cho mọi PDB. Dấu hiệu quan trọng là **vị trí session và phạm vi grant**, không chỉ cái tên bắt đầu `C##`.

> **Cảnh báo phạm vi:** một lệnh `GRANT ... CONTAINER = ALL` trong root có thể mở rộng quyền sang nhiều PDB hiện có và PDB được tạo sau này theo quy tắc common grant. Chỉ áp dụng khi quyền thực sự phải có hiệu lực xuyên phạm vi đó và đã được phê duyệt. Không dùng common grant để sửa một lỗi quyền cục bộ.

### 5.2. Common role có thể cấp cho local user không?

**Có, bằng local grant trong PDB phù hợp.** Ví dụ trong `PDB_A`:

```sql
-- Trong PDB_A, APP_REPORTER là local user đã được tạo trước.
GRANT C##LAB_OBSERVER TO APP_REPORTER CONTAINER = CURRENT;
```

Đây là grant role **chỉ dành cho local user `APP_REPORTER` của PDB_A**. `APP_REPORTER` ở PDB_B, nếu có, không mặc nhiên nhận role này. Common role có thể được dùng lại ở nhiều PDB, nhưng **việc ai nhận role và role có quyền gì trong từng PDB vẫn phải được xem xét**.

### 5.3. Khi nào dùng common role?

- Muốn chuẩn hóa tên và cấu trúc role giám sát hoặc vận hành được quản lý từ root.
- Có yêu cầu quản trị chung thực sự ở nhiều PDB, với grant được kiểm soát theo phạm vi.
- Muốn sử dụng cùng common role cho các local user khác nhau ở từng PDB, nhưng vẫn phân quyền cục bộ.

Với nghiệp vụ chỉ thuộc một PDB, một **local role** thường dễ quản trị và ít mở rộng ranh giới ngoài ý muốn hơn.

## 6. Local role: nhóm quyền riêng trong PDB

**Local role** được tạo **bên trong một PDB** và chỉ tồn tại trong PDB đó. Local role phù hợp để mô hình hóa những quyền cụ thể của ứng dụng, chẳng hạn `ORDER_READER`, `ORDER_WRITER`, `REPORT_VIEWER` hoặc nhóm quyền dành cho batch job.

Ví dụ tạo user và role ở `SALES_TEST`:

```sql
-- Xác nhận đang kết nối SALES_TEST trước khi chạy.
CREATE ROLE SALES_REPORT_READER CONTAINER = CURRENT;

CREATE USER REPORT_APP
IDENTIFIED BY "<SECRET_DO_DBA_CAP>"
CONTAINER = CURRENT;

GRANT CREATE SESSION TO REPORT_APP CONTAINER = CURRENT;

GRANT SALES_REPORT_READER TO REPORT_APP CONTAINER = CURRENT;
```

Sau đó, chủ sở hữu schema hoặc người có quyền grant object privilege có thể cấp quyền đọc bảng cần thiết cho role:

```sql
-- APP_OWNER.ORDERS phải tồn tại trong SALES_TEST.
GRANT SELECT ON APP_OWNER.ORDERS TO SALES_REPORT_READER;
```

Khi account `REPORT_APP` đăng nhập vào `SALES_TEST` và role được bật, nó có thể sử dụng những quyền được cấp thông qua role theo luật kích hoạt role của Oracle. Điều này **không tạo** user/role hay quyền tương ứng trong `SALES_DEV` hoặc `SALES_PROD`.

Local role **không thể được grant commonly từ CDB root cho tất cả PDB** vì nó không tồn tại như một common role ở cấp CDB. Nếu hai PDB đều cần role nghiệp vụ tên `SALES_REPORT_READER`, DBA/nhóm ứng dụng tạo và quản lý hai local role độc lập thông qua migration hoặc IaC phù hợp.

### 6.1. Dùng role thay vì cấp quyền hàng loạt cho từng user

Không dùng kiểu cấp quyền vượt nhu cầu như:

```sql
-- Ví dụ KHÔNG KHUYẾN NGHỊ cho runtime account:
-- GRANT DBA TO REPORT_APP;
-- GRANT SELECT ANY TABLE TO REPORT_APP;
```

Thay vào đó, đóng gói các object privilege được yêu cầu trong local role, ví dụ `GRANT SELECT ON APP_OWNER.ORDERS TO SALES_REPORT_READER`. Khi thêm bảng báo cáo được phê duyệt, cấp tiếp quyền vào role rồi kiểm chứng danh sách principal nhận role. Không nên dùng `SELECT ANY TABLE` để “khỏi phải grant từng bảng”, vì nó mở phạm vi rộng hơn yêu cầu nghiệp vụ.

### 6.2. Role không thay thế mọi direct grant

Nếu một **definer-rights PL/SQL package** thực thi SQL tham chiếu bảng của schema khác, chỉ cấp quyền qua role cho chủ package thường **không đủ** để compile hoặc chạy logic đó. Cần xem owner của package, authid (definer/invoker), các quyền trực tiếp trên object và cách Oracle tính quyền ở ngữ cảnh thực thi. Quyền trực tiếp có thể cần thiết cho schema sở hữu package. Đây là vấn đề phân quyền SQL/PLSQL, không phải lỗi common/local.

## 7. Bảng so sánh bốn loại thực thể

| Đặc điểm | Common user | Local user | Common role | Local role |
|---|---|---|---|---|
| Loại đối tượng | Danh tính/schema | Danh tính/schema | Nhóm quyền | Nhóm quyền |
| Nơi tạo (CDB thông thường) | `CDB$ROOT` | PDB | `CDB$ROOT` | PDB |
| Cú pháp phạm vi điển hình | `CREATE USER C##... CONTAINER=ALL` | `CREATE USER ... CONTAINER=CURRENT` | `CREATE ROLE C##... CONTAINER=ALL` | `CREATE ROLE ... CONTAINER=CURRENT` |
| Phạm vi tồn tại | Các container của CDB | Một PDB | Các container của CDB | Một PDB |
| Quy ước tên thường gặp | Bắt đầu `C##` | Không dùng tiền tố common dành riêng | Bắt đầu `C##` | Không dùng tiền tố common dành riêng |
| Có thể đăng nhập? | Khi được xác thực và có quyền cần thiết | Khi được xác thực và có quyền cần thiết | Không | Không |
| Quyền có tự phát sinh? | Không | Không | Không | Không |
| Có thể nhận local grant? | Có, tại PDB mục tiêu | Có, tại PDB của nó | Có, tại PDB mục tiêu | Có, tại PDB của nó |
| Có thể nhận common grant? | Có khi đáp ứng điều kiện common grant từ root | Không, local principal không tồn tại trên tất cả PDB | Có khi đáp ứng điều kiện common grant từ root | Không |
| Dùng điển hình | Công việc quản trị nhiều PDB | Ứng dụng/đơn vị nghiệp vụ một PDB | Vai trò quản trị/giám sát chuẩn hóa nhiều PDB | Quyền truy cập nghiệp vụ trong một PDB |

**Hai trục cần đọc riêng:** `USER`/`ROLE` chỉ **principal hay nhóm quyền**; `COMMON`/`LOCAL` chỉ **phạm vi tồn tại**. Các grant lại có một trục riêng về **phạm vi hiệu lực**: common grant hoặc local grant.

## 8. `CONTAINER = ALL` và `CONTAINER = CURRENT`: không được nhầm

Trong câu lệnh tạo principal hoặc cấp quyền, Oracle hỗ trợ mệnh đề `CONTAINER` để xác định phạm vi, nhưng **các trường hợp hợp lệ phụ thuộc lệnh, loại principal và container hiện tại**. Không thể tùy ý viết `CONTAINER=ALL` ở bất cứ PDB nào.

### 8.1. Tạo danh tính/role

```text
Ở CDB$ROOT:
    CREATE USER C##OPS_... CONTAINER = ALL    -> common user
    CREATE ROLE C##OPS_... CONTAINER = ALL    -> common role

Ở PDB_A:
    CREATE USER APP_... CONTAINER = CURRENT   -> local user
    CREATE ROLE APP_... CONTAINER = CURRENT   -> local role
```

Việc tạo common user/role thuộc quyền quản trị root. Không thể tạo common user CDB từ bên trong một PDB bằng cách thêm `CONTAINER=ALL`. Và không nên coi root là chỗ để tạo local account ứng dụng của PDB.

### 8.2. Phạm vi `GRANT`

Ví dụ cùng một common user nhận quyền `CREATE SESSION` theo hai cách:

```sql
-- Trong CDB$ROOT, nếu được phê duyệt cấp quyền chung:
GRANT CREATE SESSION TO C##LAB_AUDITOR CONTAINER = ALL;

-- Trong PDB_A, nếu chỉ cần cấp quyền tại PDB_A:
GRANT CREATE SESSION TO C##LAB_AUDITOR CONTAINER = CURRENT;
```

Hai lệnh thể hiện **hai chính sách quyền khác nhau**, không phải hai cách viết tương đương. Common grant từ root áp dụng trên phạm vi common; local grant chỉ thuộc container hiện tại. Một quyền common cũng có thể xuất hiện trong `DBA_SYS_PRIVS` ở PDB và được đánh dấu `COMMON = YES`, trong khi quyền được cấp chỉ tại PDB thường có `COMMON = NO`.

Đối với **role membership** cũng tương tự: common role được grant commonly cho common user ở root có hiệu lực chung; grant role chỉ trong PDB có hiệu lực ở PDB đó. **Local user không thể nhận một common grant toàn CDB** khi nó chỉ tồn tại trong PDB riêng.

### 8.3. Phân biệt common grant và common principal

```text
COMMON PRINCIPAL        SCOPE OF GRANT
------------------      ---------------------------
C##LAB_AUDITOR          CREATE SESSION [PDB_A: LOCAL]
  tồn tại ở mọi PDB     SELECT ...      [PDB_A: LOCAL]
                        CREATE SESSION [PDB_B: CHƯA CẤP]
                        CREATE SESSION [ROOT: CHƯA CẤP]

Role C##LAB_OBSERVER    Có thể nhận privilege cục bộ
  tồn tại ở mọi PDB     riêng tại PDB_A, PDB_B, ...
```

Đây là mô hình nguyên lý. Không phải vì một principal được định nghĩa common mà những quyền được cấp locally sẽ tự lan sang PDB khác. Chiều ngược lại cũng đúng: một user tên `APP_RUNTIME` chỉ tồn tại tại PDB_A không thể trở thành common user chỉ bằng một `GRANT ... CONTAINER=ALL`.

## 9. Quan sát common/local bằng data dictionary

Các view `DBA_*` giúp DBA quan sát metadata **trong container đang kết nối**. Những truy vấn sau dành cho người có quyền đọc data dictionary phù hợp; ứng dụng runtime không nên được cấp quyền quản trị chỉ để xem báo cáo này.

### 9.1. Xác định user thường hay chung

```sql
SELECT username, common, oracle_maintained, account_status
FROM dba_users
WHERE username IN ('C##LAB_AUDITOR', 'SALES_APP', 'REPORT_APP')
ORDER BY username;
```

`COMMON = YES` cho biết user thuộc loại common, còn `COMMON = NO` cho biết local user. `ORACLE_MAINTAINED` giúp nhận diện user được Oracle quản lý. **Đừng quyết định xóa hoặc thay quyền user dựa riêng vào tiền tố tên**: metadata và phạm vi sở hữu mới là bằng chứng quan trọng.

Khi chạy tại **PDB_A**, có thể thấy common user và local user của PDB_A; điều đó không khẳng định local user của PDB_B cũng hiện diện ở PDB_A.

### 9.2. Kiểm tra common/local role

```sql
SELECT role, common, oracle_maintained
FROM dba_roles
WHERE role IN ('C##LAB_OBSERVER', 'SALES_REPORT_READER')
ORDER BY role;
```

Các giá trị `COMMON = YES/NO` phân biệt nguồn gốc vai trò. Một common role chỉ mới được tạo nhưng chưa có quyền cũng xuất hiện như một role hợp lệ: **sự hiện diện của role không chứng minh nó cho phép truy cập bảng nào**.

### 9.3. Kiểm tra quyền system được grant locally hay commonly

```sql
SELECT grantee, privilege, admin_option, common
FROM dba_sys_privs
WHERE grantee IN ('C##LAB_AUDITOR', 'SALES_APP', 'REPORT_APP')
ORDER BY grantee, privilege;
```

`COMMON` trong kết quả cho biết tính common/local của **grant**, không phải trạng thái common/local của user. Cần đối chiếu thêm container hiện tại. Tương tự với role membership:

```sql
SELECT grantee, granted_role, admin_option, default_role, common
FROM dba_role_privs
WHERE grantee IN ('C##LAB_AUDITOR', 'SALES_APP', 'REPORT_APP')
ORDER BY grantee, granted_role;
```

Một common user có thể xuất hiện với **grant `COMMON=NO`** ở PDB_A; đây là trường hợp bình thường khi tổ chức muốn chỉ cấp quyền tại PDB đó.

### 9.4. Quan sát theo nhiều container từ root

Khi kết nối `CDB$ROOT` bằng tài khoản đủ quyền, DBA có thể sử dụng các view `CDB_*` để nhìn dữ liệu metadata của nhiều container. Ví dụ:

```sql
-- Chạy tại CDB$ROOT bởi DBA có quyền phù hợp.
SELECT con_id, username, common, oracle_maintained
FROM cdb_users
WHERE username IN ('C##LAB_AUDITOR', 'SALES_APP')
ORDER BY con_id, username;
```

`CON_ID` giúp định vị container sở hữu dòng metadata; có thể đối chiếu với danh sách container theo công cụ quản trị phù hợp. Các `CDB_*` view có yêu cầu quyền và ngữ cảnh container; thông tin nhìn thấy còn tùy quyền của session, trạng thái PDB và phiên bản Oracle. Không coi kết quả thiếu một PDB là bằng chứng rằng PDB đó không tồn tại nếu chưa xác minh quyền/khả năng truy cập metadata.

## 10. Quyền của common user trong từng PDB: ví dụ đầy đủ

Giả sử CDB có hai PDB nghiệp vụ: `PDB_SALES` và `PDB_SUPPORT`. Đội vận hành muốn tài khoản `C##AUDIT_OPERATOR` dùng chung danh tính để kiểm tra log nghiệp vụ, nhưng chỉ được **đọc** bảng audit đã duyệt ở từng PDB, không được đọc tùy ý mọi bảng.

```text
                                  CDB$ROOT
                         C##AUDIT_OPERATOR (common user)
                         C##AUDIT_READ     (common role)
                                   |
              common grant: role -> user (CONTAINER=ALL)
                                   |
                     +-------------+-------------+
                     |                           |
                 PDB_SALES                   PDB_SUPPORT
             CREATE SESSION (local)       CREATE SESSION (local)
             SELECT AUDIT_LOG (local)     SELECT EVENT_LOG (local)
                     |                           |
               user dùng role              user dùng role
               trong PDB_SALES             trong PDB_SUPPORT
```

### Bước 1 – DBA định nghĩa principal chung tại root

```sql
-- Chạy trong CDB$ROOT bởi account có quyền quản trị được giao.
CREATE USER C##AUDIT_OPERATOR
IDENTIFIED BY "<SECRET_DO_DBA_CAP>"
CONTAINER = ALL;

CREATE ROLE C##AUDIT_READ CONTAINER = ALL;

GRANT C##AUDIT_READ TO C##AUDIT_OPERATOR CONTAINER = ALL;
```

Đến đây common role chưa có quyền đọc bảng nghiệp vụ nào, và bài lab **chưa cấp `CREATE SESSION` thường trực trên mọi PDB**. Người quản trị phân quyền tại các PDB có nhu cầu.

### Bước 2 – Cấp quyền cụ thể tại PDB_SALES

```sql
-- Session quản trị đang ở PDB_SALES.
GRANT CREATE SESSION TO C##AUDIT_OPERATOR CONTAINER = CURRENT;

-- Bảng ví dụ phải có thật và người cấp có quyền grant trên bảng.
GRANT SELECT ON SALES_OWNER.AUDIT_LOG TO C##AUDIT_READ;
```

### Bước 3 – Cấp quyền khác tại PDB_SUPPORT

```sql
-- Session quản trị đang ở PDB_SUPPORT.
GRANT CREATE SESSION TO C##AUDIT_OPERATOR CONTAINER = CURRENT;

GRANT SELECT ON SUPPORT_OWNER.EVENT_LOG TO C##AUDIT_READ;
```

Khi đăng nhập đúng service của `PDB_SALES`, account chỉ được dùng quyền sẵn có trong `PDB_SALES`; khi đăng nhập `PDB_SUPPORT`, quyền đối tượng được xác định theo grant tại `PDB_SUPPORT`. **Common role là một tên chung nhưng quyền object có thể khác theo PDB**. Không nên diễn giải kết quả ở một PDB như kết quả toàn CDB.

### Bước 4 – Chặn phạm vi không được phép

Nếu có `PDB_FINANCE` không thuộc phạm vi giám sát, tổ chức **không grant `CREATE SESSION` hay quyền đọc dữ liệu tại PDB đó**. Đồng thời hạn chế network route/service và phân phối secret để tránh giả định một account common có thể tự do truy cập mọi nơi. Các chính sách truy cập đặc quyền khác nếu có phải được xem xét riêng.

### Bước 5 – Xác minh các grant

Đối với từng PDB, DBA kiểm tra `DBA_USERS`, `DBA_ROLES`, `DBA_SYS_PRIVS`, `DBA_ROLE_PRIVS` và object grants phù hợp. Người thử nghiệm đăng nhập bằng đúng common user qua service được cấp và chạy truy vấn đọc được phê duyệt; không kiểm thử bằng `SYS`, vì kết quả quyền cao sẽ che đi lỗi phân quyền của tài khoản thực tế.

## 11. Ví dụ ngược lại: local role cho ứng dụng chỉ trong một PDB

Một dịch vụ Spring Boot `order-api` chỉ làm việc với schema `ORDER_OWNER` của `PDB_ORDERS`. Đội dự án tạo user và role cục bộ:

```text
PDB_ORDERS
  |
  +-- ORDER_OWNER        : schema chứa bảng
  +-- ORDER_API          : local runtime user
  +-- ORDER_API_READ     : local role
  +-- ORDER_API_WRITE    : local role

PDB_BILLING
  |
  +-- Không mặc nhiên có ORDER_API hay những role trên
```

Ví dụ các lệnh cục bộ, thực hiện bởi người có quyền tại `PDB_ORDERS`:

```sql
CREATE ROLE ORDER_API_READ CONTAINER = CURRENT;
CREATE ROLE ORDER_API_WRITE CONTAINER = CURRENT;

CREATE USER ORDER_API
IDENTIFIED BY "<SECRET_DO_DBA_CAP>"
CONTAINER = CURRENT;

GRANT CREATE SESSION TO ORDER_API CONTAINER = CURRENT;

-- Chủ object hoặc người có quyền thực hiện grant.
GRANT SELECT ON ORDER_OWNER.ORDERS TO ORDER_API_READ;
GRANT INSERT, UPDATE ON ORDER_OWNER.ORDERS TO ORDER_API_WRITE;

GRANT ORDER_API_READ, ORDER_API_WRITE TO ORDER_API;
```

Phân quyền này bám sát một PDB và những thao tác ứng dụng cần. Tùy kiến trúc, account runtime có thể nhận quyền trực tiếp hoặc role, đặc biệt khi ứng dụng gọi PL/SQL definer-rights cần kiểm tra direct grant. Không nên chuyển tất cả user/role này thành common chỉ vì công ty có nhiều PDB: những thực thể cục bộ sẽ giảm phạm vi ảnh hưởng và dễ quản trị vòng đời hơn.

## 12. Những điều cần hiểu về chuyển container

Trong môi trường multitenant, nhiều thao tác quản trị phụ thuộc vào **container hiện tại**. DBA có thể chuyển container bằng câu lệnh phù hợp khi account có quyền cần thiết:

```sql
-- Ví dụ dành cho account quản trị đã được cấp quyền SET CONTAINER cần thiết.
ALTER SESSION SET CONTAINER = PDB_ORDERS;
```

Không phải user nào cũng được phép thực thi lệnh này. Và **chuyển container không thay thế việc được cấp quyền tại PDB đích**; danh tính, trạng thái, session privileges và chính sách vẫn được Oracle kiểm tra.

Đối với ứng dụng, cách thường gặp là tạo connection tới **service của PDB mục tiêu**:

```text
jdbc:oracle:thin:@//db-host.internal:1521/order_pdb_service
```

`order_pdb_service` là tên minh họa. Một connection pool ứng dụng phải kết nối nhất quán tới PDB đã được cấu hình và cấp quyền; không nên sử dụng quyền chuyển container từ ứng dụng thông thường để truy cập nhiều PDB. Một common user không đồng nghĩa ứng dụng có thể truy vấn cross-PDB bằng một câu SQL đơn giản như thể tất cả bảng thuộc cùng schema.

Khi vận hành nhiều PDB, lưu **PDB/service** trong audit log, incident record và metadata triển khai. Chỉ ghi `username = APP_USER` là thiếu thông tin nếu mỗi PDB có một local user cùng tên.

## 13. Vòng đời PDB và hệ quả đối với common/local

Tính chất common/local còn thể hiện khi tạo, clone, unplug/plug hoặc xóa PDB:

| Hoạt động | Common user/role | Local user/role |
|---|---|---|
| Tạo thêm PDB trong CDB | Principal chung thuộc phạm vi CDB được nhận diện theo cơ chế common | PDB mới không tự có mọi local principal được tạo thủ công ở PDB khác |
| Cấp quyền trong PDB A | Có thể nhận local grant ở PDB A, không tự đồng nghĩa có quyền tại PDB B | Chỉ ảnh hưởng principal local ở PDB A |
| Clone PDB | Common principal vẫn chịu quy tắc metadata và tương thích CDB đích | Local users/roles thuộc dữ liệu/metadata được clone theo quy trình clone PDB |
| Unplug/plug PDB vào CDB khác | Phải xét sự tương thích common principal của CDB nguồn/đích và các vấn đề đồng bộ/vi phạm được Oracle báo | Local principal gắn với PDB được di chuyển, nhưng quyền và phụ thuộc vẫn cần kiểm tra |
| Thu hồi quyền một PDB | Grant local có thể được thu hồi tại PDB đó | Grant cục bộ được quản lý tại đúng PDB |

Lifecycle thực tế phụ thuộc phiên bản Oracle, loại PDB và phương án chuyển đổi; không tự khẳng định thao tác clone/plug sẽ giữ **mọi** quyền và credential hoạt động nguyên vẹn. Với PDB chuyển giữa CDB, DBA phải kiểm tra plug-in violations, trạng thái common principal, quyền và bảo mật trước khi mở dịch vụ.

Việc xóa một **common user hoặc common role** ở root là thao tác có phạm vi rộng và có thể ảnh hưởng nhiều PDB. Không áp dụng các lệnh `DROP USER C##...` hoặc `DROP ROLE C##...` theo thói quen dọn dữ liệu test khi chưa xác nhận toàn bộ dependency và phạm vi ảnh hưởng.

## 14. Application common user/role là trường hợp mở rộng

Một **application container** có **application root** và các application PDB. Oracle hỗ trợ **application common users và application common roles**, được quản lý theo phạm vi application container tương ứng. Đây không phải CDB common principal ở `CDB$ROOT` cũng không phải local principal của một PDB duy nhất.

```text
CDB$ROOT
  |
  +-- APP_ROOT (application root)
  |     |
  |     +-- APP_PDB_1
  |     +-- APP_PDB_2
  |     +-- Application common principal thuộc phạm vi APP_ROOT
  |
  +-- OTHER_PDB (ngoài application container)
```

Application common principal phục vụ chia sẻ quản trị/đối tượng ứng dụng giữa những application PDB liên quan. **Nó không mặc nhiên tồn tại hoặc có quyền ở mọi PDB ngoài application container**. Cú pháp, chế độ chia sẻ metadata và quy trình đồng bộ ứng dụng có những quy tắc riêng; khi sử dụng cần đọc tài liệu chính xác theo phiên bản Oracle và loại container. Không lấy công thức `CREATE USER C##... CONTAINER=ALL` dành cho CDB root rồi áp dụng máy móc ở application root.

## 15. Bài thực hành: phân biệt danh tính và phạm vi grant

Bài lab cần **một Oracle CDB với ít nhất hai PDB thử nghiệm** và một DBA hoặc người được ủy quyền để tạo principal. Các thao tác tạo common user/role ở root có phạm vi rộng; chỉ thực hiện trong lab được cấp quyền, **không dùng production** hoặc tài khoản hệ thống sẵn có như `SYS` để làm application identity.

### Bước 1 – Quan sát container trước khi thao tác

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
```

Ghi lại đây là `CDB$ROOT`, `PDB_A` hay `PDB_B`, và session có quyền gì. Không chạy câu lệnh tạo common principal khi đang ở PDB thông thường.

### Bước 2 – DBA tạo common user và common role trong root

```sql
-- CDB$ROOT, chỉ thực hiện nếu phạm vi lab được phê duyệt.
CREATE USER C##LAB_REVIEWER
IDENTIFIED BY "<SECRET_LAB>"
CONTAINER = ALL;

CREATE ROLE C##LAB_READ_ONLY CONTAINER = ALL;

GRANT C##LAB_READ_ONLY TO C##LAB_REVIEWER CONTAINER = ALL;
```

Ở thời điểm này **không mặc định** tài khoản mới đã có `CREATE SESSION` hay role có quyền `SELECT` đối tượng nào. Việc tạo common user/role và việc cấp quyền là hai việc khác nhau.

### Bước 3 – Trong PDB_A, tạo local user và local role

```sql
-- PDB_A, cần quyền CREATE USER / CREATE ROLE trong PDB này.
CREATE USER LAB_REPORT_A
IDENTIFIED BY "<SECRET_LAB_A>"
CONTAINER = CURRENT;

CREATE ROLE LAB_REPORT_VIEW CONTAINER = CURRENT;

GRANT CREATE SESSION TO LAB_REPORT_A CONTAINER = CURRENT;
GRANT LAB_REPORT_VIEW TO LAB_REPORT_A CONTAINER = CURRENT;
```

### Bước 4 – Tại PDB_A, cấp quyền sử dụng common role cục bộ

```sql
-- Chỉ cho common user được mở session tại PDB_A.
GRANT CREATE SESSION TO C##LAB_REVIEWER CONTAINER = CURRENT;

-- Có thể cấp common role cho local user chỉ tại PDB_A.
GRANT C##LAB_READ_ONLY TO LAB_REPORT_A CONTAINER = CURRENT;
```

Các role này chưa nhất thiết chứa object privilege. Nếu muốn kiểm tra quyền thực thi SQL, có thể tạo một bảng dữ liệu giả **trong schema lab được cấp phép**, sau đó chủ object grant `SELECT` vào role phù hợp. Không dùng bảng thật, role `DBA` hoặc `SELECT ANY TABLE` để minh họa.

### Bước 5 – Quan sát metadata ở PDB_A

```sql
-- DBA hoặc người có quyền xem metadata thích hợp.
SELECT username, common
FROM dba_users
WHERE username IN ('C##LAB_REVIEWER', 'LAB_REPORT_A');

SELECT role, common
FROM dba_roles
WHERE role IN ('C##LAB_READ_ONLY', 'LAB_REPORT_VIEW');

SELECT grantee, privilege, common
FROM dba_sys_privs
WHERE grantee IN ('C##LAB_REVIEWER', 'LAB_REPORT_A');

SELECT grantee, granted_role, common
FROM dba_role_privs
WHERE grantee IN ('C##LAB_REVIEWER', 'LAB_REPORT_A');
```

Hãy chỉ ra sự khác nhau giữa `DBA_USERS.COMMON` và `DBA_SYS_PRIVS.COMMON`: một giá trị mô tả **loại user**, giá trị kia mô tả **phạm vi grant**. Khi xem ở PDB B, common user/role vẫn có thể hiện diện nhưng local `LAB_REPORT_A`/`LAB_REPORT_VIEW` của PDB A không tự có ở PDB B.

### Bước 6 – Quan sát ở PDB_B

Trong PDB_B, DBA xác nhận common principal tồn tại, rồi kiểm tra xem quyền `CREATE SESSION` đã được cấp locally ở PDB B hay chưa. Do bài lab không cấp common `CREATE SESSION` tại root, **không nên mặc định common user đăng nhập PDB B thành công**. Tương tự, role `LAB_REPORT_VIEW` tạo tại PDB A không phải role của PDB B.

Nếu cần thực hành thêm ở PDB B, hãy tạo **local principal riêng** và chọn grant ở PDB B theo đúng yêu cầu. Không copy secret hoặc tự động grant quyền chung để bài lab “dễ chạy”.

### Bước 7 – Ghi chép kết quả

| Câu hỏi | Điều cần ghi nhận |
|---|---|
| `C##LAB_REVIEWER` là user loại gì? | Common user vì được tạo ở root, thể hiện `COMMON=YES` |
| `LAB_REPORT_A` tồn tại ở đâu? | Chỉ trong PDB A nơi user được tạo |
| `C##LAB_READ_ONLY` là role loại gì? | Common role; có thể nhận local grant hoặc common grant |
| `LAB_REPORT_VIEW` có xuất hiện ở PDB B không? | Không tự xuất hiện vì là local role của PDB A |
| Grant `CREATE SESSION` ở PDB A có tự cấp quyền ở PDB B không? | Không; đó là local grant `CONTAINER=CURRENT` |
| Một common user có quyền đọc tất cả bảng của PDB không? | Không; phải xem các object/system privilege, role membership và phạm vi grant |

Khi dọn lab, **chỉ người có quyền quản trị** được xóa object sau khi xác minh không còn phụ thuộc và không dùng chung với bài khác; đặc biệt các principal common có phạm vi CDB rộng hơn một PDB. Lưu báo cáo bằng metadata và kết quả truy vấn, không lưu credential thật.

## 16. Các tình huống dễ mắc lỗi khi phát triển và vận hành

### Tình huống A – Ứng dụng báo `ORA-01017` dù DEV kết nối được

User `APP_API` là **local user** ở `PDB_DEV` và `PDB_TEST`. Hai PDB có account cùng tên nhưng password riêng. Khi cấu hình TEST vô tình trỏ đến credential DEV, Oracle có thể từ chối xác thực bằng `ORA-01017`.

**Cách xử lý:** xác minh `SERVICE_NAME`, `CON_NAME`, nguồn secret và identity của user ở đúng PDB; không tạo common user để “đồng bộ password” hoặc cấp quyền admin. Tách secret mỗi môi trường và kiểm soát kết nối từ workload.

### Tình huống B – Common user tồn tại nhưng `ORA-01045`

DBA tạo `C##MONITOR` ở CDB root, sau đó công cụ cố đăng nhập PDB mới và gặp `ORA-01045` do thiếu `CREATE SESSION` trong ngữ cảnh đó. Tên common chỉ cho biết identity tồn tại, **không cho biết quyền mở session đã được grant**.

**Cách xử lý:** kiểm tra grant ở PDB đích và yêu cầu cấp quyền hẹp nhất phù hợp. Nếu một quyền cần hiện diện ở nhiều PDB, DBA phải đánh giá riêng yêu cầu common grant; không mở quyền toàn CDB chỉ để xử lý một PDB.

### Tình huống C – Common role có tên đúng nhưng user vẫn không đọc được bảng

`C##READ_AUDIT` tồn tại ở mọi PDB, được grant cho một local user tại PDB B. Tuy nhiên quyền `SELECT ON OWNER.AUDIT_LOG` chỉ được cấp vào role đó ở PDB A.

**Cách xử lý:** kiểm tra `DBA_ROLE_PRIVS`, object grants và **container đang thực thi query**. Grant object privilege tại đúng PDB B nếu được phê duyệt; không cấp `SELECT ANY TABLE` trên toàn CDB.

### Tình huống D – `ORA-00942` khi package chạy, nhưng query trực tiếp lại được

Một user nhận `SELECT` qua role và chạy SQL trực tiếp thành công. Sau đó một definer-rights PL/SQL package của schema đó tham chiếu bảng của schema khác lại báo lỗi object hoặc quyền.

**Cách xử lý:** xem sự khác nhau giữa quyền qua role và quyền trực tiếp khi biên dịch/thực thi PL/SQL definer-rights; DBA hoặc owner cấp direct object privilege phù hợp. Đổi role thành common không giải quyết được quy tắc thực thi này.

### Tình huống E – Sau plug PDB vào CDB mới, các quyền common hoạt động khác trước

PDB được chuyển sang CDB khác có thể gặp sự khác biệt về common users/roles hoặc các grant chung. DBA cần xác nhận sự tương thích metadata và các thông báo kiểm tra sau plug, rồi thử quyền và kết nối bằng principal đúng.

**Cách xử lý:** đánh giá quy trình di chuyển, không giả định common role mang toàn bộ grant của CDB cũ sang CDB mới. Kiểm thử bằng account ứng dụng/giám sát có quyền tối thiểu; kiểm tra cả chính sách secret và đích service.

## 17. Nguyên tắc bảo mật khi phân quyền CDB/PDB

Phạm vi common có thể thuận tiện cho quản trị nhưng cũng làm tăng tác động của một grant hoặc credential bị lộ. Một thiết kế an toàn thường tuân theo các nguyên tắc sau:

1. **Ưu tiên local user cho tài khoản runtime** của ứng dụng chỉ sử dụng một PDB; dùng common user khi có yêu cầu xuyên container rõ ràng.
2. **Ưu tiên local role cho quyền nghiệp vụ** thuộc một PDB; common role chủ yếu cho chính sách quản trị/giám sát cần tái sử dụng.
3. **Cấp quyền tối thiểu**, phân biệt quyền system (`CREATE SESSION`, `CREATE TABLE`), object (`SELECT`, `UPDATE`, `EXECUTE`) và role membership.
4. **Không nhầm common principal với common grant**; yêu cầu phải chỉ rõ `CONTAINER=ALL` hoặc `CURRENT` theo nghiệp vụ và chính sách phê duyệt.
5. **Tách tài khoản chạy ứng dụng và tài khoản migration/DBA**; runtime user không cần quyền `CREATE USER`, `ALTER SYSTEM`, `DBA` hoặc `SYSDBA`.
6. **Tách mật khẩu, secret, network và service theo môi trường**; chỉ đặt hai PDB khác tên là chưa bảo đảm cô lập.
7. **Kiểm toán thao tác có phạm vi rộng** từ CDB root, đặc biệt `GRANT ... CONTAINER=ALL`, thay common user/role và thao tác lifecycle PDB.
8. **Kiểm tra quyền bằng danh tính thực** của ứng dụng hoặc công cụ; một truy vấn chạy được dưới `SYS` không chứng minh runtime account có quyền.
9. **Thẩm định tác động khi thêm PDB mới**, thay công cụ vận hành hoặc chuyển PDB giữa các CDB: common grant và local grant có vòng đời khác nhau.

| Sai lầm phổ biến | Hậu quả | Cách hiểu đúng |
|---|---|---|
| “Tên có `C##` nên chắc chắn là DBA.” | Cấp quyền vượt yêu cầu hoặc chẩn đoán sai | `C##` thường phản ánh common naming; đặc quyền do grant quyết định |
| “Common user tự đăng nhập và đọc được mọi PDB.” | Bỏ qua `CREATE SESSION`, role và object grants | Common identity tồn tại nhiều nơi nhưng quyền có thể chỉ cục bộ |
| “Common role chứa sẵn mọi quyền trong mọi PDB.” | Cho phép thiếu hoặc vượt quyền | Role chỉ có các grant được cấp; quyền object có thể khác nhau theo PDB |
| “Cùng user `APP_API` ở hai PDB là cùng tài khoản.” | Nhầm password/secret và ownership | Hai local user cùng tên vẫn độc lập |
| “Local role ở PDB A có thể `GRANT ... CONTAINER=ALL` cho PDB B.” | Lỗi cú pháp/phạm vi, tư duy sai về local role | Local role chỉ tồn tại và có hiệu lực trong PDB của nó |
| “`DBA_USERS.COMMON=YES` đồng nghĩa grant cũng `COMMON=YES`.” | Hiểu sai quyền hiệu lực | Phải đọc cột `COMMON` của **từng grant** |
| “Có quyền qua role thì definer-rights package luôn chạy.” | Lỗi compile/runtime PL/SQL | Có trường hợp cần direct grant cho owner |
| “Chuyển PDB bằng tên service là đủ cách ly.” | Cấu hình nhầm/secret chung có thể gây truy cập chéo | Kết hợp endpoint, secret, network, privilege và audit |

## 18. Bài tập tình huống

### Câu 1 – Chọn loại user

Hệ thống có 12 PDB cho 12 khách hàng. Mỗi ứng dụng chỉ truy cập PDB của khách hàng tương ứng. Nên bắt đầu từ common hay local user cho tài khoản runtime?

**Gợi ý:** local user phù hợp hơn vì phạm vi truy cập một PDB; dùng identity và secret riêng theo tenant nếu chính sách yêu cầu. Common user có thể dành cho công việc quản trị nhiều PDB với quyền được kiểm soát rõ.

### Câu 2 – Chọn loại role

Đội giám sát có một vai trò đọc metadata cần hiện diện tại nhiều PDB, nhưng mỗi PDB chỉ cho phép đọc tập view phù hợp. Chọn common hay local role?

**Gợi ý:** common role có thể chuẩn hóa identity của role, kết hợp **local object grants** ở từng PDB. Nếu không cần quản lý từ root, cũng có thể tổ chức bằng các local role riêng; phải nêu rõ ai duyệt phạm vi và quyền.

### Câu 3 – Đọc thông tin dictionary

Tại PDB A, `DBA_USERS` trả về `C##ADMIN_A / COMMON=YES`, nhưng `DBA_SYS_PRIVS` ghi quyền `CREATE SESSION / COMMON=NO`. Điều này có mâu thuẫn không?

**Đáp án:** không. User là common principal, còn grant `CREATE SESSION` được cấp **locally tại PDB A**.

### Câu 4 – Tên giống nhau ở hai PDB

`REPORT_USER` tồn tại trong PDB A và B, mỗi nơi có một mật khẩu và role khác nhau. Đây có phải một common user?

**Đáp án:** không. Hai local user được tạo độc lập trong hai PDB, chỉ tình cờ cùng tên.

### Câu 5 – Sai lầm về role

Đội phát triển tạo `C##REPORT_READER` tại root và lập tức tin rằng user trong tất cả PDB có thể chạy `SELECT` trên bảng `ORDERS`. Điều còn thiếu là gì?

**Đáp án:** phải xem role đã được grant cho user nào, **phạm vi membership**, quyền đối tượng được cấp vào role ở PDB nào và role có được bật khi SQL thực thi hay không. Việc tạo common role không tự tạo bất kỳ grant nào.

## Kết luận

Trong Oracle Multitenant, **common/local xác định phạm vi tồn tại của user hoặc role**, còn **`CONTAINER=ALL`/`CONTAINER=CURRENT` xác định phạm vi của thao tác và grant phù hợp**. **Common user** và **common role** được quản lý tại root cho phạm vi nhiều container; **local user** và **local role** chỉ thuộc PDB của mình. Một principal common vẫn có thể chỉ nhận quyền cục bộ tại một PDB, và hai principal local cùng tên ở hai PDB vẫn độc lập.

Khi triển khai ứng dụng hay quản trị Oracle, hãy luôn kiểm tra **container hiện tại, loại principal, phạm vi từng grant và quyền thực sự cần**. Sự phân biệt này giúp tránh lỗi `CREATE SESSION`, lỗi quyền truy cập dữ liệu, nhầm lẫn sau chuyển PDB và đặc biệt là việc vô tình cấp quyền rộng từ CDB root.
