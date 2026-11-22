# Quan hệ giữa user, schema và quyền sở hữu đối tượng

## 1. Bài toán: ai đăng nhập, ai sở hữu bảng và ai được sử dụng bảng?

Hãy tưởng tượng hệ thống bán hàng có bảng `ORDERS`. Một tiến trình triển khai tạo bảng, backend Java đọc và ghi đơn hàng, còn nhóm báo cáo chỉ cần xem dữ liệu. Nếu mọi thành phần cùng đăng nhập Oracle Database bằng một tài khoản có toàn quyền, sẽ khó phân tách trách nhiệm và hạn chế thiệt hại khi một thông tin đăng nhập bị lộ hoặc một chương trình thực thi câu SQL sai.

Oracle giải quyết bài toán này bằng những khái niệm liên quan nhưng **không đồng nhất**:

- **Database user (user):** danh tính được Oracle quản lý để xác thực và phân quyền. User có thể được cấp quyền kết nối, tạo đối tượng, đọc hoặc thay đổi đối tượng của user khác.
- **Schema:** không gian tên (*namespace*) và tập hợp các **schema object** gắn với một database user. Trong Oracle, **schema có cùng tên với user** tương ứng.
- **Owner (chủ sở hữu đối tượng):** user/schema mà đối tượng thuộc về. Đối với bảng `SALES.ORDERS`, owner là `SALES`, bất kể phiên nào đang `SELECT`, `INSERT` hay quản lý bảng theo quyền được cấp.
- **Privilege (quyền):** khả năng thực hiện một hành động được Oracle cho phép, chẳng hạn `CREATE TABLE`, `SELECT` một bảng hoặc `EXECUTE` một package.
- **Role (vai trò):** một tập quyền có thể cấp cho user hoặc role khác để đơn giản hóa việc phân quyền.

Ví dụ sơ đồ:

```text
                          ORACLE DATABASE / PDB
                                    |
             +----------------------+----------------------+
             |                      |                      |
           User                  User                   User
        LAB_OWNER              LAB_API               LAB_REPORT
             |                      |                      |
             v                      |                      |
      Schema LAB_OWNER              |                      |
        +--------------+            |                      |
        | LAB_ORDERS   |<-----------+------ GRANT SELECT, INSERT
        | LAB_CUSTOMERS|            |
        | Package ...  |            +-----------------------+
        +--------------+                                    |
             ^                                              |
             +------------------ GRANT SELECT --------------+
```

Trong ví dụ trên, `LAB_OWNER` sở hữu bảng; `LAB_API` và `LAB_REPORT` chỉ **được cấp quyền sử dụng** những phần cần thiết. Việc có quyền truy cập **không tự biến tài khoản được cấp quyền thành owner**.

Mục tiêu của bài học là phân biệt chính xác `user`, `schema`, `owner`, `role` và `privilege`; hiểu Oracle xác định tên đối tượng thế nào; biết xem metadata về người sở hữu và các quyền đã cấp; đồng thời thực hành phân tách tài khoản sở hữu dữ liệu với tài khoản ứng dụng.

## 2. User và schema: quan hệ một-một về tên, khác nhau về vai trò

### 2.1. Database user là gì?

**Database user** là một đối tượng bảo mật của Oracle. User có thể được xác thực bằng mật khẩu hoặc các cơ chế được cấu hình khác; tài khoản có thể bị khóa, hết hạn hoặc có chính sách xác thực riêng. Để mở một phiên đăng nhập thông thường, user phải có cơ chế xác thực hợp lệ **và quyền tạo phiên**, phổ biến là system privilege `CREATE SESSION`.

Một user thường gắn với:

| Thành phần | Tác dụng |
|---|---|
| Danh tính/tên user | Phân biệt tài khoản khi xác thực, cấp quyền và ghi nhận hoạt động |
| Cơ chế xác thực | Quyết định cách user được nhận diện khi kết nối |
| System privileges | Những quyền như `CREATE SESSION`, `CREATE TABLE`, `CREATE VIEW` |
| Object privileges | Quyền trên bảng, view, sequence, procedure... của schema khác |
| Roles | Những nhóm quyền được cấp cho user, trực tiếp hoặc qua role khác |
| Default/temporary tablespace và quota | Thiết lập nơi lưu đối tượng, vùng tạm và giới hạn không gian được phép sử dụng |
| Account status/profile | Chính sách trạng thái đăng nhập, mật khẩu, tài nguyên hoặc giới hạn phiên |

**Có user không có nghĩa user được quyền đăng nhập.** Chẳng hạn một tài khoản chuyên sở hữu schema có thể được khóa để ngăn đăng nhập trực tiếp sau khi đối tượng đã được triển khai; các phiên ứng dụng dùng một tài khoản khác được cấp quyền cụ thể.

### 2.2. Schema là gì?

Trong Oracle, **schema là tập hợp các schema object thuộc về một database user**. Các object đó thường được tham chiếu theo dạng:

```sql
schema_name.object_name
```

Ví dụ:

```sql
SELECT order_id, total_amount
FROM sales.orders;
```

Ở đây:

- `SALES` là **schema/owner** của bảng.
- `ORDERS` là tên đối tượng.
- Người chạy truy vấn **có thể không phải** user `SALES`; họ chỉ cần có quyền thích hợp.

Khi tạo user, Oracle thiết lập schema mang **cùng tên user**. Để bắt đầu có đối tượng trong schema, cần thực hiện DDL hợp lệ và có quyền phù hợp. Không có thao tác quản trị độc lập kiểu “tạo một schema `SALES` rồi gắn cho user `OTHER_USER`” theo mô hình thông thường của Oracle.

Oracle có câu lệnh `CREATE SCHEMA` phục vụ một nhóm thao tác tạo đối tượng và cấp quyền trong điều kiện nhất định; **tên lệnh này không có nghĩa nó tạo schema-user độc lập** như ở một số hệ quản trị khác.

### 2.3. User và schema giống nhau ở điểm nào?

Ví dụ tạo database user `LAB_OWNER` thì schema tương ứng cũng mang tên `LAB_OWNER`. Khi user này tạo bảng `LAB_ORDERS` trong chính schema của mình, tên đầy đủ là:

```text
LAB_OWNER.LAB_ORDERS
```

Trong metadata, owner của bảng sẽ là `LAB_OWNER`. Tuy nhiên, hai từ này trả lời những câu hỏi khác nhau:

| Câu hỏi | Khái niệm phù hợp |
|---|---|
| “Ai đăng nhập và xác thực vào database?” | User/session |
| “Đối tượng thuộc không gian tên nào?” | Schema |
| “Bảng `ORDERS` do ai sở hữu?” | Owner |
| “Tài khoản này được `SELECT` bảng nào?” | Object privileges/roles |
| “Tài khoản này được tạo bảng không?” | System privileges và các điều kiện liên quan |
| “Datafile lưu bảng ở đâu?” | Tablespace, segment, datafile, không phải tên user |

### 2.4. Schema khác database và tablespace

Đây là ba lớp thường bị nhầm:

```text
DATABASE (hoặc PDB trong một môi trường multitenant)
  |
  +-- User/Schema LAB_OWNER
  |     +-- LAB_ORDERS (table)
  |     +-- IDX_LAB_ORDERS (index)
  |     +-- API_ORDER_PKG (package)
  |
  +-- User/Schema LAB_REPORT
  |     +-- REPORT_VIEW (view)
  |
  +-- Tablespace USERS
  |     +-- Các segment thuộc nhiều schema khác nhau
  |
  +-- Tablespace APP_INDEX
        +-- Các index segment theo cấu hình
```

- **Database/PDB** là phạm vi chứa nhiều user/schema và các đối tượng khác.
- **Schema** tổ chức object theo **quyền sở hữu và tên**.
- **Tablespace** tổ chức **không gian lưu trữ logic** cho segment. Nhiều schema có thể đặt các segment vào cùng tablespace; một schema cũng có thể có segment ở nhiều tablespace.

Đặt `DEFAULT TABLESPACE USERS` cho một user **không** biến tablespace `USERS` thành “schema của user đó”. Đổi tablespace của segment cũng **không** đổi owner của bảng.

## 3. Object ownership: một đối tượng thuộc về ai?

### 3.1. Schema object là những gì?

Một schema có thể chứa nhiều loại đối tượng, chẳng hạn:

| Loại | Ví dụ | Vai trò |
|---|---|---|
| **Table** | `LAB_OWNER.LAB_ORDERS` | Lưu dữ liệu hàng/cột |
| **View** | `LAB_OWNER.V_ACTIVE_ORDERS` | Lưu định nghĩa truy vấn để truy cập dữ liệu |
| **Index** | `LAB_OWNER.IDX_ORDERS_CUSTOMER` | Hỗ trợ đường truy cập và một số ràng buộc |
| **Sequence** | `LAB_OWNER.ORDER_SEQ` | Cấp giá trị theo sequence |
| **Procedure/function** | `LAB_OWNER.CREATE_ORDER` | Mã PL/SQL được lưu trong schema |
| **Package** | `LAB_OWNER.ORDER_API` | Nhóm các khai báo và thao tác PL/SQL |
| **Trigger** | `LAB_OWNER.TRG_ORDER_AUDIT` | Mã được kích hoạt bởi sự kiện phù hợp |
| **Synonym riêng (private synonym)** | `LAB_REPORT.ORDERS` | Tên thay thế tham chiếu một đối tượng khác |
| **Materialized view** | `LAB_OWNER.MV_SALES_MONTHLY` | Kết quả truy vấn được lưu theo cơ chế làm mới phù hợp |

**Không phải mọi đối tượng Oracle đều là schema object.** User, role, tablespace, profile và các thiết lập cấp database có mô hình quản trị khác. Một số loại object toàn cục như public synonym cũng không nên hiểu giống private synonym trong schema người dùng.

### 3.2. Quyền sở hữu gắn với tên object, không gắn với người chạy truy vấn

Ví dụ:

```sql
SELECT *
FROM lab_owner.lab_orders;
```

Cho dù câu SQL do `LAB_API` chạy, bảng vẫn thuộc `LAB_OWNER`.

Khi `LAB_API` thực hiện thao tác được cấp quyền:

```sql
INSERT INTO lab_owner.lab_orders (order_id, customer_name, total_amount)
VALUES (1001, 'Lan', 250000);
```

**Owner của bảng không đổi**. Dòng dữ liệu có thể được tạo bởi transaction của `LAB_API`, nhưng owner của **đối tượng bảng** vẫn là `LAB_OWNER`. Nếu ứng dụng cần biết ai tạo từng đơn hàng, phải thiết kế cột audit hoặc cơ chế ghi nhật ký thích hợp; trường “owner” trong metadata không trả lời câu hỏi “người nào tạo hàng này”.

### 3.3. Quyền của owner đối với đối tượng của mình

Chủ sở hữu có quyền quản lý và thao tác trên đối tượng của mình theo các quy tắc Oracle áp dụng; chẳng hạn thường không cần tự `GRANT SELECT` cho chính mình đối với bảng mình sở hữu. Tuy nhiên, **quyền sở hữu không đồng nghĩa mọi system privilege**:

- Sở hữu bảng không tự cấp quyền tạo user mới.
- Sở hữu bảng không tự cấp quyền đọc bảng trong schema bất kỳ.
- Sở hữu một package không tự cấp quyền tạo hoặc sửa đối tượng của user khác.
- Muốn tạo loại object mới vẫn cần system privilege thích hợp và điều kiện đi kèm.

Trong bài toán vận hành, nên phân biệt **quyền tạo đối tượng**, **quyền sở hữu đối tượng** và **quyền dùng đối tượng đã tồn tại**. Ba quyền này không phải một.

## 4. Ai trở thành owner khi tạo đối tượng?

### 4.1. Tạo đối tượng trong schema của chính mình

Giả sử phiên đang đăng nhập bằng `LAB_OWNER`, và được cấp `CREATE TABLE` cùng quota cần thiết:

```sql
CREATE TABLE lab_orders (
    order_id     NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL,
    total_amount NUMBER(12,2) NOT NULL
);
```

Vì không ghi tiền tố schema, bảng thường được tạo trong schema của user theo ngữ cảnh và quy tắc DDL hiện hành. Trong ví dụ này, tên đầy đủ là `LAB_OWNER.LAB_ORDERS`.

### 4.2. Tạo đối tượng trong schema khác là trường hợp có quyền đặc biệt

Một tài khoản quản trị được cấp quyền thích hợp có thể thực hiện các loại DDL nhằm tạo/sửa object trong schema khác, ví dụ lệnh dạng:

```sql
-- Chỉ minh họa cú pháp và phạm vi đặc quyền quản trị.
CREATE TABLE lab_owner.admin_created_table (
    id NUMBER
);
```

Để làm được, phiên phải có **quyền hệ thống phù hợp** như `CREATE ANY TABLE` và đáp ứng những điều kiện liên quan. Khi lệnh hợp lệ, owner của bảng là `LAB_OWNER`, **không nhất thiết là người thực thi DDL**.

Các quyền `ANY` cho phép tác động xuyên schema và có phạm vi rộng. Không cấp các quyền này cho tài khoản ứng dụng thông thường.

### 4.3. Đổi tên bảng có đổi owner không?

Không. Đổi tên object trong cùng schema làm thay đổi tên object, chứ không biến nó thành object của schema khác. Muốn chuyển quyền sở hữu dữ liệu giữa các schema, thường cần quy trình phù hợp như tạo đối tượng ở schema đích, di chuyển/copy dữ liệu, chuyển grant, dependency và metadata liên quan. Không giả định chỉ cần `ALTER SESSION SET CURRENT_SCHEMA` hoặc sửa chuỗi `schema.table` là có thể đổi chủ sở hữu.

### 4.4. `DROP USER ... CASCADE` ảnh hưởng gì đến schema?

Schema gắn với user, nên việc xóa user kèm `CASCADE` có thể xóa **các đối tượng thuộc schema đó** và làm ảnh hưởng các đối tượng ở schema khác đang tham chiếu tới chúng. Đây là thao tác phá hủy, cần quy trình backup/restore, đánh giá dependency và xác nhận phạm vi trước khi DBA thực hiện.

```sql
-- LỆNH NGUY HIỂM, chỉ ghi để nhận diện; KHÔNG CHẠY trên môi trường dữ liệu thật.
-- DROP USER lab_owner CASCADE;
```

## 5. Quyền Oracle: system privilege, object privilege và role

### 5.1. System privilege: quyền thực hiện loại thao tác

**System privilege** cho phép user thực hiện một loại thao tác ở phạm vi mà quyền xác định.

| Quyền | Ý nghĩa |
|---|---|
| `CREATE SESSION` | Được tạo phiên đăng nhập khi thỏa điều kiện xác thực/trạng thái tài khoản |
| `CREATE TABLE` | Được tạo bảng trong schema theo phạm vi quyền và điều kiện lưu trữ |
| `CREATE VIEW` | Được tạo view trong schema theo quy tắc quyền và dependency |
| `CREATE SEQUENCE` | Được tạo sequence trong schema |
| `CREATE PROCEDURE` | Được tạo các đối tượng chương trình PL/SQL thích hợp trong schema |
| `CREATE ANY TABLE` | Quyền tạo bảng trong schema khác theo quy tắc Oracle; phạm vi rộng |
| `SELECT ANY TABLE` | Quyền đọc nhiều bảng/view xuyên schema trong phạm vi quyền; phạm vi rất rộng |

Không nên suy ra rằng người có `CREATE SESSION` mặc nhiên có `SELECT` trên bảng ứng dụng, hoặc người có `CREATE TABLE` mặc nhiên được `CREATE TABLE OTHER_SCHEMA.X` mà không có quyền `ANY` tương ứng.

### 5.2. Object privilege: quyền trên đối tượng cụ thể

**Object privilege** áp dụng cho một đối tượng hoặc loại đối tượng phù hợp:

```sql
GRANT SELECT ON lab_orders TO lab_report;
GRANT SELECT, INSERT ON lab_orders TO lab_api;
```

Hai dòng trên được thực hiện bởi chủ sở hữu `LAB_OWNER` trong ví dụ. Kết quả:

- `LAB_REPORT` được đọc `LAB_OWNER.LAB_ORDERS`.
- `LAB_API` được đọc và chèn dữ liệu vào `LAB_OWNER.LAB_ORDERS`.
- Không vì được `SELECT` mà tự có quyền `UPDATE`, `DELETE`, `ALTER`, `DROP` bảng.
- Không vì được `INSERT` mà owner của bảng đổi thành `LAB_API`.

Một số quyền thường dùng:

| Loại object | Object privilege thông dụng | Ví dụ |
|---|---|---|
| Table/view | `SELECT`, `INSERT`, `UPDATE`, `DELETE` theo điều kiện Oracle | `GRANT SELECT ON lab_orders ...` |
| Sequence | `SELECT` để lấy giá trị sequence khi được phép | `GRANT SELECT ON order_seq ...` |
| Procedure/function/package | `EXECUTE` | `GRANT EXECUTE ON order_api ...` |

Ngoài ví dụ trên, Oracle hỗ trợ những privilege khác tùy loại object và phiên bản. Chỉ cấp quyền thực sự cần, và kiểm tra hành vi cụ thể khi thiết kế chính sách truy cập.

### 5.3. Role giúp quản lý nhiều quyền

Khi nhiều tài khoản báo cáo cần đọc cùng nhóm bảng, có thể dùng role để nhóm quyền:

```sql
-- Thực hiện bởi tài khoản quản trị có quyền tạo role.
CREATE ROLE app_report_role;

-- Thực hiện bởi owner hoặc tài khoản có quyền cấp object privilege.
GRANT SELECT ON lab_owner.lab_orders TO app_report_role;

-- Thực hiện bởi tài khoản có quyền grant role.
GRANT app_report_role TO lab_report;
```

Từ đó `LAB_REPORT` có thể nhận quyền thông qua role khi role đang được bật và ngữ cảnh thực thi cho phép sử dụng quyền từ role.

**Đặc biệt với PL/SQL được lưu trong database:** khi biên dịch các đối tượng **definer's rights**, quyền trên object được tham chiếu thường cần được **cấp trực tiếp cho owner của chương trình**, thay vì chỉ đi qua role. Quy tắc về role còn phụ thuộc chế độ thực thi (`AUTHID DEFINER` hay `AUTHID CURRENT_USER`) và các tính năng Oracle dành cho program unit. Vì thế, một `SELECT` chạy được trong SQL worksheet không đảm bảo procedure chứa đúng câu `SELECT` đó có thể compile nếu quyền chỉ đến từ role.

### 5.4. `GRANT`, `REVOKE`, `WITH GRANT OPTION`, `WITH ADMIN OPTION`

| Cơ chế | Công dụng |
|---|---|
| `GRANT` | Cấp một quyền hoặc role theo quyền hạn của người cấp |
| `REVOKE` | Thu hồi quyền hoặc role được cấp theo quy tắc Oracle |
| `WITH GRANT OPTION` | Cho phép người nhận **object privilege** tiếp tục cấp quyền đó trên object cho user/role phù hợp |
| `WITH ADMIN OPTION` | Dùng với **system privilege hoặc role** để cho phép quản lý cấp quyền/role theo quy tắc Oracle |

Ví dụ:

```sql
-- Trong phiên của LAB_OWNER:
GRANT SELECT ON lab_orders TO lab_report;

-- Khi muốn thu hồi grant trực tiếp:
REVOKE SELECT ON lab_orders FROM lab_report;
```

Sau khi `REVOKE`, nếu `LAB_REPORT` vẫn được phép truy cập thông qua role hoặc một quyền khác còn hiệu lực, việc thu hồi **một grant trực tiếp** có thể chưa đủ để chặn toàn bộ đường truy cập. Cần xem đầy đủ các quyền đang hiệu lực.

**Không cấp `WITH GRANT OPTION` chỉ để một ứng dụng có thể đọc bảng.** Quyền cấp tiếp có thể mở rộng phạm vi truy cập ngoài dự kiến.

## 6. SQL thực hành: tách owner, API và tài khoản đọc báo cáo

Phần này xây dựng ví dụ tự chứa với ba user để quan sát rõ quan hệ owner và quyền. Chỉ sử dụng **database/PDB thực hành** và tài khoản quản trị được phép tạo user. Các bước quản trị có thể yêu cầu hỗ trợ từ DBA. Không chạy các lệnh tạo user/role trên hệ thống sản xuất nếu chưa có quy trình phê duyệt.

### Bước 1. Chuẩn bị các tài khoản bằng user quản trị

Các mật khẩu trong ví dụ là placeholder, phải thay bằng giá trị phù hợp do môi trường quản lý bí mật cung cấp. `USERS` là tên tablespace ví dụ; nếu môi trường không có tablespace đó, phải dùng tablespace được DBA chỉ định.

```sql
-- Chạy trong PDB thực hành với user quản trị có quyền tương ứng.
CREATE USER lab_owner
    IDENTIFIED BY "<replace_with_owner_password>"
    DEFAULT TABLESPACE users;

CREATE USER lab_api
    IDENTIFIED BY "<replace_with_api_password>";

CREATE USER lab_report
    IDENTIFIED BY "<replace_with_report_password>";

GRANT CREATE SESSION, CREATE TABLE TO lab_owner;
GRANT CREATE SESSION TO lab_api, lab_report;

ALTER USER lab_owner QUOTA 20M ON users;
```

Giải thích:

- Mỗi `CREATE USER` tạo danh tính database và schema cùng tên.
- `LAB_OWNER` được phép tạo bảng trong schema của mình.
- `LAB_API` và `LAB_REPORT` được phép mở phiên; chúng **chưa được cấp quyền đọc bảng `LAB_OWNER`**.
- Quota cấp cho `LAB_OWNER` là điều kiện lưu trữ phục vụ tạo bảng trong tablespace ví dụ; quota và quyền DDL là hai cơ chế khác nhau.
- Trong môi trường thực tế, thiết lập account status, profile, xác thực, default/temp tablespace, privilege và quota phải theo chính sách của DBA.

### Bước 2. Tạo bảng bằng tài khoản sở hữu schema

Kết nối SQL*Plus/SQLcl hoặc SQL Developer dưới user `LAB_OWNER`, rồi chạy:

```sql
CREATE TABLE lab_orders (
    order_id      NUMBER NOT NULL,
    customer_name VARCHAR2(100) NOT NULL,
    total_amount  NUMBER(12, 2) NOT NULL,
    CONSTRAINT pk_lab_orders PRIMARY KEY (order_id),
    CONSTRAINT ck_lab_orders_total CHECK (total_amount >= 0)
);

INSERT INTO lab_orders (order_id, customer_name, total_amount)
VALUES (1001, 'Nguyen Lan', 250000);

INSERT INTO lab_orders (order_id, customer_name, total_amount)
VALUES (1002, 'Tran Minh', 420000);

COMMIT;
```

Ở đây bảng có tên đầy đủ `LAB_OWNER.LAB_ORDERS`. Bạn không cần gõ tiền tố `LAB_OWNER.` khi đang làm việc trong schema phù hợp; nhưng khi từ user khác truy cập, việc ghi tên đầy đủ thường giúp tránh nhầm.

### Bước 3. Xem owner từ metadata

Vẫn dưới `LAB_OWNER`:

```sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE object_name = 'LAB_ORDERS';
```

`USER_OBJECTS` là metadata dành cho object trong schema của user hiện tại, nên không có cột `OWNER` như `ALL_OBJECTS`. Muốn xem owner tường minh, có thể chạy:

```sql
SELECT owner,
       object_name,
       object_type,
       status
FROM all_objects
WHERE owner = 'LAB_OWNER'
  AND object_name = 'LAB_ORDERS';
```

Đối tượng vừa tạo có owner `LAB_OWNER`. Những tên unquoted như `lab_orders` được Oracle lưu ở dạng chữ hoa theo quy tắc định danh thông thường, vì vậy điều kiện dictionary dùng `'LAB_ORDERS'`.

### Bước 4. Thử truy cập bằng tài khoản khác trước khi cấp quyền

Đăng nhập bằng `LAB_REPORT`, thử:

```sql
SELECT order_id, total_amount
FROM lab_owner.lab_orders;
```

Nếu user chưa có quyền nào khác cho phép đọc bảng, Oracle từ chối truy cập. Với việc tham chiếu bảng không tồn tại/không được phép nhìn thấy, lỗi thường gặp là `ORA-00942: table or view does not exist`. Lỗi này **không nhất thiết** có nghĩa bảng thật sự chưa được tạo; Oracle còn có thể hạn chế lộ thông tin về object khi không có quyền.

### Bước 5. Chủ sở hữu cấp đúng quyền

Quay lại phiên `LAB_OWNER`:

```sql
GRANT SELECT ON lab_orders TO lab_report;
GRANT SELECT, INSERT ON lab_orders TO lab_api;
```

Các lệnh `GRANT` được Oracle xử lý như câu DCL và có hiệu lực theo quy tắc của cơ sở dữ liệu. Sau đó:

**Dưới `LAB_REPORT`:**

```sql
SELECT order_id, customer_name, total_amount
FROM lab_owner.lab_orders
ORDER BY order_id;
```

**Dưới `LAB_API`:**

```sql
INSERT INTO lab_owner.lab_orders (order_id, customer_name, total_amount)
VALUES (1003, 'Le An', 150000);

COMMIT;

SELECT COUNT(*) AS total_orders
FROM lab_owner.lab_orders;
```

Khi `LAB_API` chèn một hàng, hàng mới vẫn nằm trong bảng `LAB_OWNER.LAB_ORDERS`. Việc `LAB_API` commit giao dịch **không chuyển quyền sở hữu bảng**.

### Bước 6. Kiểm tra danh sách grant

Trong phiên `LAB_OWNER`, xem grant trực tiếp do owner cấp:

```sql
SELECT table_name,
       grantee,
       privilege,
       grantable
FROM user_tab_privs_made
WHERE table_name = 'LAB_ORDERS'
ORDER BY grantee, privilege;
```

Trong phiên `LAB_REPORT`, xem các quyền đối tượng nhận trực tiếp:

```sql
SELECT owner,
       table_name,
       privilege,
       grantor
FROM user_tab_privs_recd
WHERE owner = 'LAB_OWNER'
  AND table_name = 'LAB_ORDERS';
```

Các view `USER_TAB_PRIVS_MADE` và `USER_TAB_PRIVS_RECD` tập trung vào **các grant đã được ghi nhận trong phạm vi view**; để phân tích toàn bộ quyền đang hiệu lực, cần xem thêm role, quyền hệ thống và ngữ cảnh chạy.

### Bước 7. Dọn tài nguyên học tập

Khi kết thúc bài thực hành, DBA có thể hỗ trợ thu hồi quyền, xóa bảng và tài khoản minh họa theo quy trình. Đặc biệt, `DROP TABLE`, `DROP USER ... CASCADE` là thao tác phá hủy dữ liệu và có thể ảnh hưởng các dependency; chỉ thực hiện sau khi xác nhận chính xác môi trường và các đối tượng được phép xóa.

## 7. Tên đối tượng có và không có tiền tố schema

### 7.1. Vì sao `SELECT * FROM orders` có thể chọn nhầm bảng?

Giả sử trong một PDB có hai schema:

```text
SALES.ORDERS
REPORT.ORDERS
```

Câu SQL:

```sql
SELECT * FROM orders;
```

chỉ nêu **tên ngắn** `ORDERS`. Oracle phải phân giải tên dựa trên ngữ cảnh schema hiện hành, đối tượng và các quy tắc phân giải tên (gồm cả synonym nếu áp dụng). Vì vậy một câu SQL chưa đủ để kết luận bảng nào được đọc.

Ghi tên đầy đủ giúp rõ ý định:

```sql
SELECT * FROM sales.orders;
```

Việc ghi `SALES.ORDERS` **không tự cấp quyền**. Nếu user hiện tại không được phép truy cập, câu SQL vẫn lỗi.

### 7.2. `CURRENT_SCHEMA` khác `SESSION_USER`

Trong một phiên SQL, bạn có thể xem:

```sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

- **`SESSION_USER`**: danh tính user của phiên đăng nhập.
- **`CURRENT_SCHEMA`**: schema mặc định dùng trong quá trình phân giải một số tên đối tượng không có tiền tố.

Oracle cho phép đặt schema mặc định của phiên:

```sql
ALTER SESSION SET CURRENT_SCHEMA = LAB_OWNER;

SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

Nếu câu lệnh chạy dưới `LAB_REPORT`, sau `ALTER SESSION`:

```text
SESSION_USER   = LAB_REPORT
CURRENT_SCHEMA = LAB_OWNER
```

Bạn có thể viết:

```sql
SELECT order_id FROM lab_orders;
```

thay cho:

```sql
SELECT order_id FROM lab_owner.lab_orders;
```

nhưng chỉ nếu `LAB_REPORT` **đã có quyền `SELECT`**. `ALTER SESSION SET CURRENT_SCHEMA` **không đăng nhập lại**, **không đổi user** và **không cấp thêm object privilege**.

Nếu cần khôi phục ngữ cảnh schema ban đầu trong phiên ví dụ:

```sql
ALTER SESSION SET CURRENT_SCHEMA = LAB_REPORT;
```

### 7.3. Synonym có đổi owner không?

Synonym là **bí danh** cho tên đối tượng. Ví dụ, nếu `LAB_REPORT` được cấp `CREATE SYNONYM` và quyền `SELECT` trên bảng gốc:

```sql
-- Trong phiên LAB_REPORT:
CREATE SYNONYM my_orders FOR lab_owner.lab_orders;

SELECT order_id FROM my_orders;
```

Trong ví dụ:

- `LAB_REPORT.MY_ORDERS` là **private synonym** thuộc schema `LAB_REPORT`.
- `LAB_OWNER.LAB_ORDERS` vẫn là bảng do `LAB_OWNER` sở hữu.
- Tạo synonym **không cấp thêm quyền đọc bảng gốc**.

Đây là lý do metadata có thể cho thấy user sở hữu một `SYNONYM` mà **không sở hữu bảng** được synonym tham chiếu.

Các **public synonym** có phạm vi tên rộng hơn, cần quản trị cẩn thận để tránh xung đột tên và hiểu nhầm nguồn đối tượng.

### 7.4. Tên phân biệt chữ hoa/chữ thường khi dùng dấu nháy kép

Oracle thông thường chuyển các định danh **không đặt trong nháy kép** thành chữ hoa trong metadata:

```sql
CREATE TABLE demo_case (id NUMBER);
-- Tên dictionary thông thường: DEMO_CASE
```

Nếu cố ý tạo định danh có nháy kép:

```sql
CREATE TABLE "DemoCase" ("Id" NUMBER);
```

thì tên được giữ theo đúng cách viết và câu SQL tham chiếu cần dùng dấu nháy kép/chữ hoa-chữ thường phù hợp, ví dụ `"DemoCase"."Id"`.

Đối với hệ thống ứng dụng, quy ước định danh không dùng nháy kép cho tên bảng/cột thường giúp việc viết SQL, migration và đọc metadata đơn giản hơn.

## 8. Xem user, owner và quyền bằng data dictionary

Oracle có nhiều nhóm dictionary views. Cần phân biệt **phạm vi dữ liệu có thể thấy** và **quyền cần có để đọc view**.

### 8.1. `USER_`, `ALL_`, `DBA_`: ba góc nhìn

| Nhóm view | Phạm vi khái quát | Ví dụ |
|---|---|---|
| `USER_...` | Đối tượng/thông tin thuộc schema của user đang kết nối | `USER_TABLES`, `USER_OBJECTS`, `USER_INDEXES` |
| `ALL_...` | Đối tượng/thông tin có thể truy cập hoặc nhìn thấy theo quyền và quy tắc view | `ALL_TABLES`, `ALL_OBJECTS`, `ALL_TAB_COLUMNS` |
| `DBA_...` | Góc nhìn quản trị rộng hơn trong database/container | `DBA_USERS`, `DBA_OBJECTS`, `DBA_TAB_PRIVS` |

Thông thường user ứng dụng có thể dùng `USER_` và một số `ALL_` view phù hợp. Các `DBA_` view yêu cầu quyền xem dictionary thích hợp; không tự cấp các quyền quản trị chỉ để chạy một câu truy vấn học tập.

**Lưu ý:** `ALL_OBJECTS` cho biết các object khả kiến trong phạm vi của view, nhưng **không nên coi mọi dòng là bằng chứng user có thể làm mọi thao tác trên đối tượng đó**. Muốn biết thao tác cụ thể, vẫn cần xét quyền tương ứng.

### 8.2. Xem các object thuộc schema đang kết nối

```sql
SELECT object_name,
       object_type,
       status,
       created
FROM user_objects
ORDER BY object_type, object_name;
```

Nếu kết nối bằng `LAB_OWNER`, kết quả là những object thuộc schema đó. `USER_OBJECTS` không cần cột owner vì phạm vi đã được giới hạn theo user.

Xem bảng và index của schema:

```sql
SELECT table_name, tablespace_name
FROM user_tables
ORDER BY table_name;

SELECT index_name, table_name, tablespace_name
FROM user_indexes
ORDER BY table_name, index_name;
```

Đừng nhầm `TABLESPACE_NAME` với owner. Đây là nơi cấp phát segment tương ứng, không phải danh tính sở hữu đối tượng.

### 8.3. Xem tên owner của các object khả kiến

```sql
SELECT owner,
       object_name,
       object_type,
       status
FROM all_objects
WHERE object_name = 'LAB_ORDERS'
ORDER BY owner, object_type;
```

Cột `OWNER` xác định schema sở hữu object. Nếu user hiện tại không có quyền thấy object, `ALL_OBJECTS` có thể không trả về dòng tương ứng, dù object thực sự tồn tại trong database.

Để lọc các bảng ở schema cụ thể:

```sql
SELECT owner, table_name, tablespace_name
FROM all_tables
WHERE owner = 'LAB_OWNER'
ORDER BY table_name;
```

### 8.4. Góc nhìn quản trị: danh sách user và object ownership

Với user DBA có quyền phù hợp:

```sql
SELECT username,
       account_status,
       default_tablespace,
       temporary_tablespace
FROM dba_users
WHERE username IN ('LAB_OWNER', 'LAB_API', 'LAB_REPORT')
ORDER BY username;
```

Xem owner theo metadata:

```sql
SELECT owner, object_type, COUNT(*) AS object_count
FROM dba_objects
WHERE owner IN ('LAB_OWNER', 'LAB_API', 'LAB_REPORT')
GROUP BY owner, object_type
ORDER BY owner, object_type;
```

Đây là thống kê **object dictionary**, không trực tiếp cho biết dung lượng segment hay số hàng dữ liệu; các loại đối tượng không nhất thiết đều có segment lưu trữ riêng.

### 8.5. Xem quyền trên đối tượng

Trong phiên chủ sở hữu `LAB_OWNER`:

```sql
SELECT table_name, grantee, privilege, grantable
FROM user_tab_privs_made
WHERE table_name = 'LAB_ORDERS';
```

Với DBA:

```sql
SELECT owner, table_name, grantee, privilege, grantable
FROM dba_tab_privs
WHERE owner = 'LAB_OWNER'
  AND table_name = 'LAB_ORDERS'
ORDER BY grantee, privilege;
```

Xem system privileges được grant trực tiếp trong phạm vi quản trị:

```sql
SELECT grantee, privilege, admin_option
FROM dba_sys_privs
WHERE grantee IN ('LAB_OWNER', 'LAB_API', 'LAB_REPORT')
ORDER BY grantee, privilege;
```

Xem role được grant:

```sql
SELECT grantee, granted_role, admin_option, default_role
FROM dba_role_privs
WHERE grantee IN ('LAB_OWNER', 'LAB_API', 'LAB_REPORT')
ORDER BY grantee, granted_role;
```

Để nhìn quyền/role đang **hiệu lực trong phiên hiện tại**:

```sql
SELECT privilege FROM session_privs ORDER BY privilege;

SELECT role FROM session_roles ORDER BY role;
```

Một số quyền có thể được cấp trực tiếp, thông qua role hoặc theo các chính sách/chế độ đặc biệt. Vì vậy nên xem metadata cùng với session context và thử thao tác trong môi trường thực hành khi cần kiểm chứng hành vi.

## 9. Chủ sở hữu object và quyền thực thi PL/SQL

Sự phân biệt user/schema/owner còn đặc biệt quan trọng khi làm việc với **stored procedure, function, package hoặc view**.

### 9.1. Procedure thuộc schema nào?

Giả sử:

```text
LAB_OWNER.ORDER_API (package)
LAB_OWNER.LAB_ORDERS (table)
LAB_API            (user ứng dụng)
```

Một package do `LAB_OWNER` tạo thuộc schema `LAB_OWNER`. Tài khoản `LAB_API` muốn gọi package thường cần được cấp `EXECUTE`:

```sql
-- Do owner cấp trong phiên LAB_OWNER:
GRANT EXECUTE ON order_api TO lab_api;
```

**Quyền `EXECUTE` không chuyển ownership package.** Người gọi và owner là hai thực thể khác nhau.

### 9.2. Definer's rights và invoker's rights

Oracle hỗ trợ hai mô hình quyền thực thi PL/SQL được lưu:

| Mô hình | Khai báo thường gặp | Ý nghĩa chính |
|---|---|---|
| **Definer's rights** | `AUTHID DEFINER` (thường là mặc định cho stored PL/SQL) | Mã chạy theo ngữ cảnh quyền của chủ sở hữu chương trình, với các quy tắc hạn chế role và name resolution |
| **Invoker's rights** | `AUTHID CURRENT_USER` | Mã chạy theo ngữ cảnh quyền của người gọi ở những bước phù hợp, tuân theo quy tắc invoker-rights của Oracle |

Ví dụ định nghĩa:

```sql
CREATE OR REPLACE PROCEDURE lab_owner.show_order_count
AUTHID DEFINER
AS
    v_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM lab_owner.lab_orders;

    DBMS_OUTPUT.PUT_LINE('So don hang: ' || v_count);
END;
/
```

Đây là ví dụ minh họa và cần quyền `CREATE PROCEDURE`, object `LAB_OWNER.LAB_ORDERS` tồn tại cùng các điều kiện phù hợp. Người gọi muốn chạy procedure có thể cần:

```sql
GRANT EXECUTE ON lab_owner.show_order_count TO lab_api;
```

Khi dùng **definer's rights**, một tài khoản chỉ có quyền `EXECUTE` trên chương trình có thể dùng các thao tác được đóng gói bên trong theo quyền thực thi của owner mà không cần được cấp trực tiếp mọi quyền trên bảng bên dưới. Điều này hữu ích để chỉ công bố một API có kiểm soát. Tuy nhiên, owner phải thiết kế procedure an toàn, kiểm tra đầu vào và không mở ra thao tác dữ liệu vượt mục đích nghiệp vụ.

Khi dùng **invoker's rights**, việc kiểm tra quyền và ngữ cảnh thực thi khác đi; không nên chỉ đổi `AUTHID` mà giả định chương trình vẫn hoạt động giống cũ. Với các phiên bản Oracle có chính sách `INHERIT PRIVILEGES`, còn phải xét quyền kế thừa liên quan nếu áp dụng.

### 9.3. Vì sao grant qua role có thể đủ để `SELECT` nhưng không đủ để compile procedure?

Giả sử `LAB_DEV` được role `APP_READ_ROLE`, role này có quyền đọc `LAB_OWNER.LAB_ORDERS`. Người phát triển chạy:

```sql
SELECT COUNT(*) FROM lab_owner.lab_orders;
```

và câu truy vấn thành công trong SQL worksheet. Tuy nhiên, khi tạo stored procedure theo mô hình **definer's rights** có tham chiếu đến bảng đó, Oracle thường đòi quyền trên bảng được **grant trực tiếp cho owner của procedure** để compile và hoạt động ổn định theo quy tắc quyền của stored object.

Một grant trực tiếp có thể cần như:

```sql
-- Trong phiên owner của bảng:
GRANT SELECT ON lab_orders TO lab_dev;
```

Đó là tình huống kinh điển của lỗi “chạy SQL trực tiếp được nhưng procedure compile lỗi”. Cần kiểm tra quyền được grant cho **user sở hữu chương trình**, không chỉ các role đang bật ở phiên phát triển.

## 10. Thiết kế tài khoản cho ứng dụng Java/Spring

Đối với ứng dụng kết nối Oracle qua JDBC, tài khoản dùng trong connection pool thường **không cần sở hữu toàn bộ bảng**.

### 10.1. Phân tách owner và runtime user

Mô hình tham khảo:

```text
                    CI/CD / DBA / Migration
                              |
                         LAB_OWNER
                              |
                   Tạo/sửa bảng, index,
                   view, package theo quy trình
                              |
                 Schema LAB_OWNER
                       /           \
              GRANT giới hạn      GRANT SELECT
                    /                  \
              LAB_API               LAB_REPORT
                |                       |
           Backend Java             Tác vụ báo cáo
```

Trong mô hình này:

- **Schema owner** được sử dụng bởi quy trình thay đổi cấu trúc dữ liệu có kiểm soát.
- **Runtime account** như `LAB_API` chỉ có quyền cần thiết cho hoạt động ứng dụng, chẳng hạn `SELECT`, `INSERT`, `UPDATE` trên các bảng được chỉ định hoặc `EXECUTE` các package API.
- **Reporting account** như `LAB_REPORT` chỉ nhận quyền đọc ở phạm vi phù hợp.
- Mật khẩu/credential được quản lý tập trung, không commit vào repository hoặc ghi thẳng trong file cấu hình có thể phát tán.

Mô hình này giới hạn phạm vi của lỗi ứng dụng. Ví dụ, một lỗi SQL chạy dưới `LAB_API` không nên được cấp sẵn quyền `DROP USER` hoặc `CREATE ANY TABLE`.

### 10.2. Ứng dụng nên tham chiếu bảng bằng tên nào?

Nếu backend kết nối bằng `LAB_API` nhưng bảng thuộc `LAB_OWNER`, SQL thường nên dùng:

```sql
SELECT order_id, total_amount
FROM lab_owner.lab_orders
WHERE order_id = :order_id;
```

Trong JDBC chuẩn, ví dụ tương đương thường dùng placeholder `?`:

```java
String sql = """
    SELECT order_id, total_amount
    FROM lab_owner.lab_orders
    WHERE order_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, orderId);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Chuyển hàng kết quả thành đối tượng ứng dụng.
        }
    }
}
```

Ví dụ Java trên sử dụng text block (Java 15+), và giả định đã có `Connection`, `orderId` cùng import JDBC thích hợp. Đây là đoạn minh họa cách gọi bảng **khác schema** và bind giá trị, không phải ứng dụng hoàn chỉnh.

Nếu chọn dùng `ALTER SESSION SET CURRENT_SCHEMA = LAB_OWNER`, cần xem tương tác với connection pool: kết nối có thể được tái sử dụng giữa request. Trạng thái session bị thay đổi phải được đặt/khôi phục có kiểm soát, tránh để query khác vô tình dùng schema mặc định sai.

### 10.3. Migration tool có cần đăng nhập bằng owner không?

Khi một công cụ như Flyway/Liquibase tạo bảng, view hoặc package, bạn cần xác định **tài khoản nào chạy DDL**, **schema đích** và **quyền thực tế**. Có thể dùng owner được kiểm soát hoặc tài khoản triển khai có quyền DDL thích hợp theo chính sách. Không cấp tài khoản runtime các quyền `ANY` rộng chỉ để migration hoạt động.

Tên schema nên nhất quán trong script; cấp quyền cho runtime user và role cần được quản lý như một phần của thay đổi cấu trúc. Nếu triển khai object ở schema mới, các grant và dependency cũ không tự chuyển sang schema đó.

## 11. Multitenant: user/schema nằm trong CDB hay PDB?

Oracle Database triển khai theo kiến trúc **CDB/PDB** có thêm phạm vi cần phân biệt:

- **CDB (container database):** chứa root và các pluggable database (PDB), cùng những thành phần cấu trúc phù hợp.
- **PDB:** môi trường cơ sở dữ liệu logic có thể chứa user/schema, bảng và nhiều đối tượng ứng dụng.
- **Local user:** user được tạo trong phạm vi PDB theo mô hình được Oracle hỗ trợ.
- **Common user:** user có phạm vi nhận diện/cấp quyền theo cơ chế common user trong CDB; tên và cách tạo tuân theo quy tắc của phiên bản/cấu hình, thường liên quan tiền tố `C##` trong môi trường chuẩn.

Ví dụ hai PDB có thể cùng có user/schema tên `APP_OWNER` mà dữ liệu là **hai tập độc lập**:

```text
CDB
  |
  +-- PDB_SALES
  |     +-- APP_OWNER.ORDERS
  |
  +-- PDB_TEST
        +-- APP_OWNER.ORDERS
```

Không vì cùng tên `APP_OWNER` mà suy ra hai bảng trên là một object hoặc user ở PDB này tự đọc bảng ở PDB khác. Khi xem owner trong `ALL_OBJECTS` hoặc `DBA_OBJECTS`, phải biết **mình đang kết nối vào container/PDB nào**. Quyền và các view `CDB_...` ở cấp quản trị còn có yêu cầu và phạm vi riêng.

Đối với môi trường thực hành, hãy kết nối đến service của đúng PDB trước khi tạo user hoặc chạy DDL. Các ví dụ SQL trong bài được thiết kế cho PDB/schema thực hành thông thường, không nhằm hướng dẫn tạo common user ở CDB root.

## 12. Tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Điều cần kiểm tra |
|---|---|---|
| `ORA-00942: table or view does not exist` khi `SELECT` từ schema khác | Sai schema/tên bảng, object không tồn tại trong PDB đang kết nối hoặc user không có quyền truy cập | `CURRENT_SCHEMA`, tên đầy đủ, quyền `SELECT`, synonym, PDB |
| `ORA-01031: insufficient privileges` khi DDL hoặc thao tác | Thiếu system/object privilege thích hợp | Quyền trực tiếp, role, phạm vi `ANY`, owner và ngữ cảnh thực thi |
| `ORA-01950: no privileges on tablespace ...` khi tạo/ghi đối tượng | User thiếu quota hoặc điều kiện sử dụng tablespace | Quota, default tablespace, phạm vi tạo segment |
| `CREATE TABLE` thành công ở user A nhưng user B không thấy | B chưa có quyền hoặc đang tra sai schema/PDB | `ALL_OBJECTS`, `GRANT`, kết nối của B |
| `SELECT` chạy được trong worksheet nhưng procedure không compile | Quyền chỉ được cấp qua role, không trực tiếp cho owner chương trình | `USER_ERRORS`, `USER_TAB_PRIVS_RECD`, cấp quyền trực tiếp |
| `ALTER SESSION SET CURRENT_SCHEMA` xong vẫn không đọc được bảng | Đổi schema mặc định **không cấp quyền** | `SESSION_USER`, `CURRENT_SCHEMA`, object grant |
| `SELECT * FROM ORDERS` trả dữ liệu của bảng khác mong đợi | Name resolution gặp object/synonym trong schema hiện hành | Tên đầy đủ `OWNER.OBJECT`, synonym, session state |
| Tạo synonym rồi vẫn lỗi `SELECT` | Synonym chỉ là bí danh, không cấp object privilege | Quyền trên đối tượng được synonym trỏ tới |
| Cùng một tên schema trong hai môi trường cho kết quả khác | Đang kết nối các PDB/database khác nhau | Service name, `SYS_CONTEXT`, metadata PDB |
| `REVOKE` quyền trực tiếp nhưng user vẫn đọc được | User có quyền qua role hoặc system privilege khác | Danh sách grant, role, quyền đang hiệu lực |

### Quy trình kiểm tra nhanh khi không truy cập được bảng

1. **Xác định danh tính phiên và schema hiện hành**:

   ```sql
   SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
          SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
   FROM dual;
   ```

2. **Ghi rõ tên object theo owner**, ví dụ `LAB_OWNER.LAB_ORDERS`, rồi kiểm tra tên và PDB bằng tài khoản có quyền xem metadata.
3. **Xem quyền trực tiếp và role** có hiệu lực đối với thao tác cần thực hiện.
4. **Phân biệt SQL thường với stored PL/SQL**: cách tính quyền qua role có thể khác.
5. **Chỉ yêu cầu cấp quyền cần thiết**, ví dụ `SELECT` trên đúng bảng hoặc `EXECUTE` đúng package, thay vì cấp quyền `ANY` để “sửa nhanh”.

## 13. Những nhận định đúng và sai cần nhớ

| Nhận định | Kết luận | Giải thích |
|---|---|---|
| “Oracle có schema cùng tên với database user.” | Đúng | Schema gắn với user tương ứng trong phạm vi database/PDB |
| “User có `CREATE SESSION` nên đọc được mọi bảng.” | Sai | Quyền tạo phiên khác quyền trên đối tượng |
| “User có quyền `SELECT` bảng thì trở thành owner của bảng.” | Sai | Owner không đổi khi cấp quyền |
| “Schema chính là tablespace.” | Sai | Schema tổ chức object theo chủ sở hữu; tablespace tổ chức lưu trữ |
| “Một schema có thể chứa nhiều bảng, view, index, procedure.” | Đúng | Đây là các schema object |
| “Một tablespace chỉ chứa object từ một schema.” | Sai | Nhiều schema có thể cùng sử dụng một tablespace |
| “Tạo synonym đồng nghĩa cấp quyền đọc bảng gốc.” | Sai | Synonym là bí danh; cần quyền trên object đích |
| “`CURRENT_SCHEMA` đổi thì `SESSION_USER` đổi theo.” | Sai | Đây là hai thông tin riêng |
| “Tài khoản `LAB_API` chèn hàng vào `LAB_OWNER.LAB_ORDERS` thì owner đổi thành `LAB_API`.” | Sai | Owner của table vẫn là `LAB_OWNER` |
| “Một procedure có thể cần quyền grant trực tiếp dù SQL worksheet dùng role vẫn chạy.” | Đúng trong nhiều trường hợp definer's rights | Phụ thuộc cơ chế kiểm tra quyền khi biên dịch/thực thi chương trình |
| “User đã được cấp quyền `DROP` mọi schema bằng cách thêm tiền tố schema.” | Sai | Cú pháp tên đầy đủ không thay thế privilege |
| “Owner của object có thể xem bằng `ALL_OBJECTS.OWNER` khi object khả kiến.” | Đúng | Metadata trả owner theo phạm vi view/quyền truy cập |
| “Cùng tên `APP_OWNER` ở hai PDB thì chắc chắn là một bảng duy nhất.” | Sai | Mỗi PDB có phạm vi dữ liệu/user/schema theo kiến trúc multitenant |

## 14. Bài tập tự kiểm tra

### Câu 1

Trong database có bảng `HR.EMPLOYEES`. User `REPORT` được cấp `SELECT ON HR.EMPLOYEES`. Ai là owner?

**Đáp án:** `HR`. `REPORT` có quyền đọc, không sở hữu bảng.

### Câu 2

`REPORT` thực hiện:

```sql
ALTER SESSION SET CURRENT_SCHEMA = HR;
SELECT * FROM employees;
```

Lệnh đầu có làm user `REPORT` thành `HR` không?

**Đáp án:** Không. Danh tính phiên vẫn là `REPORT`, chỉ schema mặc định dùng để phân giải tên ngắn đổi thành `HR`. `SELECT` chỉ chạy khi user có quyền trên bảng.

### Câu 3

Một user có `CREATE TABLE` nhưng không được phép cấp phát không gian ở tablespace mặc định. Việc có `CREATE TABLE` đã đủ để tạo bảng có segment trong tablespace đó chưa?

**Đáp án:** Chưa chắc. Cần đáp ứng các điều kiện lưu trữ/quota và trạng thái tablespace liên quan.

### Câu 4

User `REPORT` tạo private synonym `ORDERS` trỏ đến `SALES.ORDERS`. Hai object nào tồn tại và ai sở hữu chúng?

**Đáp án:** `REPORT.ORDERS` là synonym do `REPORT` sở hữu; `SALES.ORDERS` vẫn là bảng do `SALES` sở hữu. Synonym không chuyển quyền sở hữu hoặc tự cấp quyền đọc.

### Câu 5

Một package `APP.PKG_ORDER` do `APP` sở hữu, user `API` có quyền `EXECUTE` trên package. `API` có tự được tạo/sửa code package không?

**Đáp án:** Không. `EXECUTE` chỉ cho phép gọi chương trình trong phạm vi quyền; quyền sửa/tạo object và quyền sở hữu là các khái niệm khác.

### Câu 6

Bạn kiểm tra `USER_OBJECTS` của `LAB_API` và không thấy `LAB_OWNER.LAB_ORDERS`, nhưng query `SELECT * FROM LAB_OWNER.LAB_ORDERS` vẫn chạy. Có mâu thuẫn không?

**Đáp án:** Không. `USER_OBJECTS` chỉ liệt kê object thuộc **schema `LAB_API`**; bảng thuộc `LAB_OWNER`. Quyền truy cập có thể được kiểm tra qua `ALL_OBJECTS`, `ALL_TABLES` và metadata grant phù hợp.

### Câu 7

Một developer được cấp quyền `SELECT` trên bảng của owner khác thông qua role, chạy SQL trực tiếp thành công nhưng procedure definer's rights báo thiếu quyền khi compile. Cần xem gì trước?

**Đáp án:** Kiểm tra **grant trực tiếp cho schema sở hữu procedure**, vì quyền từ role có thể không được dùng trong quá trình compile/execute theo mô hình quyền của stored PL/SQL.

### Câu 8

Ứng dụng cần đọc và chèn đơn hàng vào `LAB_OWNER.LAB_ORDERS`. Quyền nào phù hợp hơn cho `LAB_API`: `SELECT, INSERT ON LAB_OWNER.LAB_ORDERS` hay `SELECT ANY TABLE`?

**Đáp án:** Quyền object cụ thể `SELECT, INSERT` trên bảng cần dùng giúp thực hiện nguyên tắc quyền tối thiểu và giới hạn tác động khi ứng dụng gặp lỗi.

## 15. Kết luận

Trong Oracle Database, **user** là danh tính bảo mật để đăng nhập và nhận quyền; **schema** là không gian tên và tập các object gắn với user đó; **owner** xác định schema nào sở hữu từng object. Ba khái niệm có quan hệ chặt chẽ nhưng phải phân biệt với **privilege**, **role**, **tablespace** và **session**.

Khi nhìn thấy `SALES.ORDERS`, hãy đọc `SALES` là **schema/owner**, còn việc một tài khoản khác có thể `SELECT`, `INSERT`, `UPDATE` hay `EXECUTE` phụ thuộc các quyền đã cấp. `GRANT` mở quyền sử dụng chứ không đổi chủ sở hữu; `CURRENT_SCHEMA` giúp phân giải tên ngắn chứ không đổi user hoặc tạo quyền mới; synonym tạo bí danh chứ không biến object đích thành object của người tạo synonym.

Hiểu đúng mô hình này giúp bạn viết SQL rõ ràng, tra metadata chính xác qua `USER_`/`ALL_`/`DBA_` views, thiết kế quyền tối thiểu cho backend Java và tách việc **sở hữu, triển khai và sử dụng dữ liệu** thành các trách nhiệm dễ quản lý.
