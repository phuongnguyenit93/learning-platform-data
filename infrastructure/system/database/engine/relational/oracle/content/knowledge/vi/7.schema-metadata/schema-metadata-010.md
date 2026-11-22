# Ghi chú bảng/cột và quy ước đặt tên phục vụ tài liệu hóa Oracle

Một database có thể chạy đúng về mặt kỹ thuật nhưng vẫn khó bảo trì nếu người khác không biết bảng `CUSTOMER` lưu loại khách hàng nào, cột `STATUS` có những giá trị hợp lệ gì, hoặc cột `AMOUNT` tính theo đơn vị tiền tệ nào. Sau vài tháng, tên đối tượng và kiểu dữ liệu không còn đủ để giải thích ý nghĩa nghiệp vụ. Vì vậy, tài liệu hóa schema cần được xây dựng **cùng lúc với DDL**, được lưu trong metadata của Oracle ở những chỗ phù hợp và được quản lý theo phiên bản như mã nguồn.

Trong Oracle Database, hai công cụ nền tảng cho việc này là:

- **`COMMENT ON TABLE` / `COMMENT ON COLUMN`:** lưu chú thích về bảng và cột trong data dictionary của database.
- **Quy ước đặt tên:** đặt tên bảng, cột, khóa, constraint và index theo những quy tắc nhất quán, để một người chưa biết dự án vẫn có thể suy luận đúng về cấu trúc.

Bài học trình bày cách kết hợp hai công cụ đó, truy xuất metadata để lập data dictionary, và giữ tài liệu đồng bộ khi schema thay đổi. Các ví dụ dùng Oracle SQL trong một schema ứng dụng của PDB thực hành.

## 1. Tài liệu hóa database khác gì viết chú thích trong source code?

Trong một dự án Java/Oracle, thông tin về một bảng có thể nằm ở nhiều nơi:

| Nơi lưu | Ví dụ | Ai thường đọc? | Giới hạn |
|---|---|---|---|
| **Tên đối tượng** | `LAB_ORDER.TOTAL_AMOUNT` | SQL developer, DBA, ứng dụng, công cụ ERD | Ngắn gọn, không diễn đạt đầy đủ quy tắc nghiệp vụ |
| **Oracle metadata** | `COMMENT ON COLUMN LAB_ORDER.TOTAL_AMOUNT IS '...'` | Người tra data dictionary, công cụ database, tài liệu sinh tự động | Là mô tả bằng văn bản, không tự ép buộc logic |
| **DDL và constraint** | `NOT NULL`, `PRIMARY KEY`, `CHECK`, `FOREIGN KEY` | Oracle optimizer, developer, DBA | Thể hiện luật có thể thực thi, chưa giải thích toàn bộ mục đích |
| **Migration được version hóa** | `V002__document_lab_order.sql` | Developer, CI/CD, người vận hành | Cần được triển khai đúng thứ tự vào database |
| **Tài liệu nghiệp vụ ngoài database** | Data dictionary, ERD, glossary, ADR | Developer, analyst, product, kiểm toán | Có thể lỗi thời nếu không đồng bộ với schema thật |

Một thiết kế tốt thường có **ba lớp bổ trợ**:

1. **Tên rõ nghĩa** để người đọc hiểu ngay đối tượng thuộc lĩnh vực nào.
2. **Constraint và kiểu dữ liệu** để Oracle kiểm soát những điều kiện có thể thực thi.
3. **Comment và tài liệu nghiệp vụ** để giải thích nguồn gốc, đơn vị, ý nghĩa và vòng đời dữ liệu.

Ví dụ cột `ORDER_STATUS` có kiểu `VARCHAR2(20)` và một `CHECK` giới hạn các mã `NEW`, `PAID`, `CANCELLED`. Constraint bảo đảm không ghi mã ngoài danh sách; comment giải thích **khi nào** đơn hàng chuyển sang `PAID`, mã `CANCELLED` có nghĩa gì, và liệu hệ thống có cho phép phục hồi đơn hàng đã hủy không.

> **Nguyên tắc quan trọng:** Comment là lời mô tả cho người và công cụ đọc metadata. Nếu một quy tắc phải được database bảo vệ, hãy biểu diễn nó bằng constraint, khóa, quyền hoặc cơ chế thực thi phù hợp; đừng chỉ viết nó trong comment.

## 2. Vị trí của comment trong schema và data dictionary

Oracle tổ chức các đối tượng trong **schema**, tức tập hợp đối tượng thuộc về một database user. Trong kiến trúc multitenant, schema thường nằm trong một **PDB**. Một bảng có thể nhận diện đầy đủ bằng tên `SCHEMA.TABLE_NAME`, và cột bằng `SCHEMA.TABLE_NAME.COLUMN_NAME`.

~~~text
Oracle CDB
└── PDB: SALES_PDB
    ├── Schema: SALES_APP
    │   ├── Table: LAB_CUSTOMER
    │   │   ├── CUSTOMER_ID          ── column comment
    │   │   └── CUSTOMER_CODE        ── column comment
    │   └── Table: LAB_ORDER         ── table comment
    │       ├── ORDER_ID             ── column comment
    │       ├── CUSTOMER_ID          ── column comment
    │       ├── ORDER_STATUS         ── column comment
    │       ├── TOTAL_AMOUNT         ── column comment
    │       └── CURRENCY_CODE        ── column comment
    └── Schema: REPORT_APP
        └── View: V_ORDER_SUMMARY    ── mô tả báo cáo
~~~

Khi chạy một câu `COMMENT ON` thành công, Oracle lưu phần chú thích trong **data dictionary**. Các view thường dùng để đọc:

- `USER_TAB_COMMENTS`: chú thích bảng/view thuộc schema của user hiện tại.
- `USER_COL_COMMENTS`: chú thích cột thuộc đối tượng của user hiện tại.
- `ALL_TAB_COMMENTS` và `ALL_COL_COMMENTS`: thông tin về đối tượng mà user được phép nhìn thấy, có cột `OWNER`.
- `DBA_TAB_COMMENTS` và `DBA_COL_COMMENTS`: phục vụ góc nhìn quản trị rộng hơn, cần quyền catalog tương ứng.

Các view `USER_*` rất thuận tiện cho developer vì không phải thêm điều kiện `OWNER` khi đang đăng nhập bằng chính chủ sở hữu schema.

**Lưu ý về PDB:** Kết quả metadata phụ thuộc container mà session đang kết nối và quyền hiện có. Thấy cùng tên bảng trong hai PDB không có nghĩa chúng là cùng một đối tượng. Khi tạo hoặc xuất data dictionary, hãy xác nhận đúng PDB/service trước.

## 3. Cú pháp COMMENT ON TABLE và COMMENT ON COLUMN

### 3.1. Ghi chú bảng

Cú pháp cơ bản:

~~~sql
COMMENT ON TABLE lab_order IS
  'Lưu đơn hàng của khách hàng; mỗi dòng biểu diễn một đơn hàng.';
~~~

Comment nên trả lời: bảng này dùng để làm gì, một dòng đại diện cho điều gì, dữ liệu được tạo ra khi nào, ai sử dụng và có phạm vi nghiệp vụ nào đáng lưu ý. Ví dụ trên mô tả **grain** của bảng: **một dòng = một đơn hàng**. Điều đó có giá trị hơn câu “Bảng đơn hàng”, vì tên bảng đã nói gần đủ ý đó.

### 3.2. Ghi chú cột

~~~sql
COMMENT ON COLUMN lab_order.total_amount IS
  'Tổng giá trị đơn hàng, theo đơn vị tiền tệ ở CURRENCY_CODE; không âm.';
~~~

Comment của cột nên nói **ý nghĩa**, **đơn vị**, **miền giá trị**, **quy tắc null**, **nguồn dữ liệu** hoặc quan hệ với cột khác khi cần. Không cần chép lại máy móc kiểu `NUMBER(15,2)` hay `NOT NULL` vì data dictionary đã có thông tin đó.

### 3.3. Có thể ghi chú đối tượng ở schema khác không?

Tên đầy đủ có thể viết:

~~~sql
COMMENT ON TABLE sales_app.lab_order IS
  'Lưu một bản ghi cho mỗi đơn hàng của hệ thống bán hàng.';

COMMENT ON COLUMN sales_app.lab_order.order_status IS
  'Trạng thái nghiệp vụ: NEW, PAID hoặc CANCELLED.';
~~~

Để ghi chú bảng/cột, user phải sở hữu đối tượng hoặc có quyền hệ thống phù hợp, chẳng hạn quyền chú thích bảng khác theo chính sách của Oracle. Trong thực hành phát triển, an toàn và dễ kiểm soát nhất là **chạy migration bằng tài khoản sở hữu schema** hoặc một tài khoản triển khai có quyền được cấp rõ ràng.

### 3.4. Chuỗi comment chứa dấu nháy đơn

Trong Oracle SQL, một dấu nháy đơn bên trong chuỗi được viết thành **hai dấu nháy đơn**:

~~~sql
COMMENT ON COLUMN lab_customer.display_name IS
  'Tên hiển thị do khách hàng khai báo; không dùng như mã định danh.';

COMMENT ON COLUMN lab_order.order_status IS
  'Giá trị NEW là ''mới tạo'', PAID là ''đã thanh toán''.';
~~~

Với văn bản dài chứa nhiều dấu nháy, Oracle hỗ trợ cú pháp alternative quoting như `q'[ ... ]'`:

~~~sql
COMMENT ON COLUMN lab_order.order_status IS
  q'[NEW = 'mới tạo'; PAID = 'đã thanh toán';
CANCELLED = 'đã hủy'. Không suy trạng thái từ tên hiển thị.]';
~~~

Comment nên viết rõ ràng và đủ ngắn để công cụ đọc metadata hiển thị thuận tiện; mô tả rất dài, luồng nghiệp vụ nhiều nhánh hoặc sơ đồ thường nên nằm trong tài liệu chuyên biệt và được dẫn chiếu bằng tên tài liệu hoặc định danh ổn định.

### 3.5. Sửa hoặc bỏ chú thích

Chạy lại `COMMENT ON` cho cùng bảng/cột sẽ **thay thế** comment cũ:

~~~sql
COMMENT ON COLUMN lab_order.total_amount IS
  'Số tiền phải thu của đơn hàng, theo mã ISO 4217 ở CURRENCY_CODE.';
~~~

Khi không còn muốn giữ chú thích, trong Oracle có thể đặt nội dung thành chuỗi rỗng:

~~~sql
COMMENT ON COLUMN lab_order.total_amount IS '';
~~~

Oracle xử lý chuỗi ký tự rỗng như `NULL` trong ngữ cảnh chuỗi hiện hành; hãy đọc lại `USER_COL_COMMENTS` để xác nhận kết quả. Trong dự án thật, việc xóa comment có thể làm mất ngữ cảnh nghiệp vụ: chỉ xóa khi có chủ đích và đã thay tài liệu ở nơi phù hợp.

**COMMENT là lệnh DDL.** Trong Oracle, DDL thường dẫn đến implicit commit theo quy tắc của database; đừng cho rằng `ROLLBACK` sau khi chạy `COMMENT ON` sẽ khôi phục mô tả cũ. Nên đặt thay đổi comment trong migration có phiên bản và xem nó như thay đổi schema chính thức.

## 4. Tạo ví dụ schema có tên và comment rõ ràng

Các ví dụ tiếp theo dùng hai bảng trong schema ứng dụng:

- `LAB_CUSTOMER`: một dòng đại diện cho một khách hàng nghiệp vụ.
- `LAB_ORDER`: một dòng đại diện cho một đơn hàng; tham chiếu khách hàng qua foreign key.

Giả sử bạn đã kết nối vào **PDB thực hành** và user có quyền tạo bảng. Các bảng chỉ nên tạo **một lần** trong schema trống hoặc trong một migration có kiểm soát.

~~~sql
CREATE TABLE lab_customer (
    customer_id    NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_code  VARCHAR2(32 CHAR) NOT NULL,
    display_name   VARCHAR2(200 CHAR) NOT NULL,
    created_at     TIMESTAMP WITH TIME ZONE
                     DEFAULT SYSTIMESTAMP NOT NULL,

    CONSTRAINT pk_lab_customer
      PRIMARY KEY (customer_id),

    CONSTRAINT uq_lab_customer_code
      UNIQUE (customer_code)
);

CREATE TABLE lab_order (
    order_id       NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_id    NUMBER NOT NULL,
    order_status   VARCHAR2(20 CHAR) DEFAULT 'NEW' NOT NULL,
    total_amount   NUMBER(15,2) NOT NULL,
    currency_code  VARCHAR2(3 CHAR) DEFAULT 'VND' NOT NULL,
    ordered_at     TIMESTAMP WITH TIME ZONE
                     DEFAULT SYSTIMESTAMP NOT NULL,

    CONSTRAINT pk_lab_order
      PRIMARY KEY (order_id),

    CONSTRAINT fk_lab_order_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_customer (customer_id),

    CONSTRAINT ck_lab_order_status
      CHECK (order_status IN ('NEW', 'PAID', 'CANCELLED')),

    CONSTRAINT ck_lab_order_amount
      CHECK (total_amount >= 0)
);
~~~

Ví dụ dùng **identity column** (Oracle 12c trở lên) để database cấp phát khóa thay cho ứng dụng. Constraint `PK`, `FK`, `UQ` và `CK` áp dụng quy tắc có thể kiểm tra bằng máy. Cột tiền sử dụng `NUMBER(15,2)` để biểu diễn số thập phân chính xác trong giới hạn khai báo, còn `CURRENCY_CODE` nói rõ đơn vị. `TIMESTAMP WITH TIME ZONE` cho phép lưu thông tin thời gian gắn với múi giờ/offset; ứng dụng cần có quy ước chuyển đổi khi trình bày.

### 4.1. Ghi chú hai bảng

~~~sql
COMMENT ON TABLE lab_customer IS
  'Danh mục khách hàng phục vụ đơn hàng; mỗi dòng là một khách hàng nghiệp vụ.';

COMMENT ON TABLE lab_order IS
  'Đơn hàng của khách hàng; mỗi dòng là một đơn hàng, không phải một dòng sản phẩm.';
~~~

Hai comment trên cung cấp phạm vi và **grain** của bảng. Nếu sau này có bảng `LAB_ORDER_ITEM`, bảng đó sẽ có grain “một sản phẩm trong một đơn hàng” hoặc “một dòng chi tiết đơn hàng” theo thiết kế thực tế, khác `LAB_ORDER`.

### 4.2. Ghi chú từng cột của khách hàng

~~~sql
COMMENT ON COLUMN lab_customer.customer_id IS
  'Khóa kỹ thuật nội bộ của khách hàng; do Oracle identity cấp phát.';

COMMENT ON COLUMN lab_customer.customer_code IS
  'Mã nghiệp vụ duy nhất của khách hàng; dùng để đối chiếu khi tích hợp.';

COMMENT ON COLUMN lab_customer.display_name IS
  'Tên hiển thị của khách hàng; có thể đổi và không được dùng làm khóa.';

COMMENT ON COLUMN lab_customer.created_at IS
  'Thời điểm tạo bản ghi khách hàng; do database gán theo SYSTIMESTAMP.';
~~~

`CUSTOMER_ID` và `CUSTOMER_CODE` cần hai comment riêng vì chúng có **vai trò khác nhau**. `CUSTOMER_ID` là khóa kỹ thuật ổn định nội bộ; `CUSTOMER_CODE` là mã nghiệp vụ có thể trao đổi giữa các hệ thống. Hai mã có thể trùng về định dạng hoặc cùng kiểu số/chuỗi trong một dự án khác, nhưng không nên được hiểu là đồng nhất.

### 4.3. Ghi chú từng cột đơn hàng

~~~sql
COMMENT ON COLUMN lab_order.order_id IS
  'Khóa kỹ thuật của đơn hàng; do Oracle identity cấp phát.';

COMMENT ON COLUMN lab_order.customer_id IS
  'Khách hàng sở hữu đơn hàng; tham chiếu LAB_CUSTOMER.CUSTOMER_ID.';

COMMENT ON COLUMN lab_order.order_status IS
  'Trạng thái: NEW = mới tạo; PAID = đã thanh toán; CANCELLED = đã hủy.';

COMMENT ON COLUMN lab_order.total_amount IS
  'Tổng số tiền đơn hàng, không âm; đơn vị nằm ở CURRENCY_CODE.';

COMMENT ON COLUMN lab_order.currency_code IS
  'Mã tiền tệ 3 ký tự theo ISO 4217, ví dụ VND hoặc USD.';

COMMENT ON COLUMN lab_order.ordered_at IS
  'Thời điểm phát sinh đơn hàng; lưu TIMESTAMP WITH TIME ZONE.';
~~~

Điều mà các comment **không** thay thế được:

- `ORDER_STATUS` có comment liệt kê mã hợp lệ, nhưng chính `CHECK` mới ngăn giá trị ngoài danh sách.
- `CUSTOMER_ID` có comment mô tả quan hệ, nhưng **foreign key** mới bảo vệ tính toàn vẹn tham chiếu khi constraint được bật/được kiểm tra theo cấu hình.
- `TOTAL_AMOUNT` có comment nói “không âm”, nhưng **check constraint** mới áp đặt điều kiện đó.
- `CURRENCY_CODE` có comment nhắc ISO 4217, song DDL chỉ giới hạn tối đa ba ký tự; nếu cần chặn các mã không thuộc danh sách ISO thực tế, phải triển khai thêm bảng tham chiếu/constraint hoặc xác thực nghiệp vụ.

## 5. Đọc ghi chú từ USER_TAB_COMMENTS và USER_COL_COMMENTS

Sau khi chạy `COMMENT ON`, không cần mở lại từng file migration để xem mô tả. Oracle cho phép truy vấn metadata trực tiếp.

### 5.1. Xem chú thích các bảng

~~~sql
SELECT
    table_name,
    table_type,
    comments
FROM user_tab_comments
WHERE table_name IN ('LAB_CUSTOMER', 'LAB_ORDER')
ORDER BY table_name;
~~~

`TABLE_NAME` trong dictionary lưu tên đối tượng; `TABLE_TYPE` giúp phân biệt loại đối tượng được view thể hiện; `COMMENTS` là nội dung người quản trị/developer đã ghi. Nếu bảng có thật nhưng chưa được chú thích, `COMMENTS` thường là `NULL`.

Để xem chú thích cho tất cả bảng và view mà schema sở hữu:

~~~sql
SELECT table_name, table_type, comments
FROM user_tab_comments
ORDER BY table_name;
~~~

### 5.2. Xem chú thích các cột theo thứ tự định nghĩa

~~~sql
SELECT
    c.table_name,
    c.column_id,
    c.column_name,
    c.data_type,
    c.nullable,
    cc.comments AS column_comment
FROM user_tab_columns c
LEFT JOIN user_col_comments cc
  ON cc.table_name = c.table_name
 AND cc.column_name = c.column_name
WHERE c.table_name IN ('LAB_CUSTOMER', 'LAB_ORDER')
ORDER BY c.table_name, c.column_id;
~~~

`USER_TAB_COLUMNS` cung cấp metadata cấu trúc; `USER_COL_COMMENTS` cung cấp mô tả. Ghép hai nguồn giúp tạo bảng tài liệu tự động: tên cột, vị trí, kiểu, nullable và ý nghĩa. Một cột chưa có comment vẫn xuất hiện nhờ `LEFT JOIN`.

Trong Oracle, tên object không đặt trong dấu nháy khi tạo thường được dictionary lưu ở dạng **chữ hoa**. Vì vậy điều kiện `WHERE TABLE_NAME = 'LAB_ORDER'` dùng tên viết hoa dù câu `CREATE TABLE lab_order` trước đó dùng chữ thường.

### 5.3. Xuất data dictionary của một bảng

~~~sql
SELECT
    c.column_id                      AS ordinal_position,
    c.column_name,
    CASE
      WHEN c.data_type IN ('VARCHAR2', 'CHAR') THEN
        c.data_type || '(' || c.char_length || ' CHAR)'
      WHEN c.data_type = 'NUMBER'
           AND c.data_precision IS NOT NULL THEN
        'NUMBER(' || c.data_precision || ',' ||
        NVL(c.data_scale, 0) || ')'
      ELSE c.data_type
    END                              AS display_type,
    c.nullable,
    cc.comments                      AS business_meaning
FROM user_tab_columns c
LEFT JOIN user_col_comments cc
  ON cc.table_name = c.table_name
 AND cc.column_name = c.column_name
WHERE c.table_name = 'LAB_ORDER'
ORDER BY c.column_id;
~~~

`DISPLAY_TYPE` trong ví dụ là **chuỗi hiển thị đơn giản hóa**, không phải bộ sinh DDL hoàn chỉnh: Oracle còn nhiều kiểu dữ liệu, cách khai báo byte/char semantics và thuộc tính đặc biệt. Nếu cần DDL chính xác, dùng metadata chuyên dụng như `DBMS_METADATA.GET_DDL` hoặc công cụ quản trị phù hợp.

Với `LAB_ORDER`, một bản data dictionary có thể trình bày:

| Column | Type | Nullable | Ý nghĩa |
|---|---|---|---|
| `ORDER_ID` | `NUMBER` (identity) | No | Khóa kỹ thuật của đơn hàng |
| `CUSTOMER_ID` | `NUMBER` | No | Tham chiếu khách hàng |
| `ORDER_STATUS` | `VARCHAR2(20 CHAR)` | No | NEW / PAID / CANCELLED |
| `TOTAL_AMOUNT` | `NUMBER(15,2)` | No | Số tiền theo `CURRENCY_CODE` |
| `CURRENCY_CODE` | `VARCHAR2(3 CHAR)` | No | Mã ISO 4217 |
| `ORDERED_AT` | `TIMESTAMP WITH TIME ZONE` | No | Thời điểm phát sinh đơn hàng |

Không nên dùng bảng mô tả này thay thế hoàn toàn constraint, index và quan hệ vì đó là những đặc điểm cấu trúc quan trọng cần truy xuất từ các view khác.

## 6. Tra cứu comment của schema khác và trong CDB/PDB

### 6.1. Khi user không phải chủ sở hữu

Nếu tài khoản có quyền nhìn thấy đối tượng thuộc `SALES_APP`, có thể đọc:

~~~sql
SELECT owner, table_name, comments
FROM all_tab_comments
WHERE owner = 'SALES_APP'
  AND table_name = 'LAB_ORDER';

SELECT owner, table_name, column_name, comments
FROM all_col_comments
WHERE owner = 'SALES_APP'
  AND table_name = 'LAB_ORDER'
ORDER BY column_name;
~~~

Các view `ALL_*` phản ánh **những đối tượng mà user có thể truy cập/nhìn thấy**, không có nghĩa mọi bảng của mọi schema đều sẽ xuất hiện. Việc đọc metadata từ `DBA_*` có thể cần quyền catalog do DBA cấp.

### 6.2. Khi database có nhiều PDB

Trước khi xuất data dictionary, xác nhận container:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Ví dụ phiên đang ở `SALES_PDB` và `CURRENT_SCHEMA = SALES_APP`, nhưng `SESSION_USER = REPORT_APP`. Điều đó **không biến REPORT_APP thành chủ sở hữu**. Các view `USER_*` dựa trên user/schema theo định nghĩa dictionary; khi cần chọn rõ owner, sử dụng `ALL_*` với `OWNER`.

Trong CDB, tài khoản quản trị có thể dùng các view `CDB_*` phù hợp để xem metadata nhiều container và phân biệt `CON_ID`, với điều kiện quyền truy cập và cấu hình container-data cho phép. Nhưng với bài tập hoặc ứng dụng, cách đơn giản và ít nhầm nhất là **kết nối đến đúng service/PDB, sau đó truy vấn metadata tại PDB đó**.

## 7. Quy ước đặt tên: để tên đã mang thông tin

Trước khi thêm comment, hãy đặt tên sao cho người đọc SQL đoán đúng ý nghĩa. Một convention nhất quán giúp tìm kiếm, review migration, sinh tài liệu và trao đổi giữa developer với DBA thuận tiện hơn.

### 7.1. Quy tắc nền tảng cho identifier Oracle

- **Không dùng dấu nháy kép cho identifier thông thường**. Oracle lưu tên không quoted ở dạng chữ hoa và cho phép tham chiếu không phân biệt hoa/thường.
- **Chọn một convention duy nhất**, chẳng hạn các từ tiếng Anh không dấu, ngăn cách bằng dấu gạch dưới (`SNAKE_CASE`). Lệnh tạo có thể viết `lab_order`; trong dictionary hiển thị `LAB_ORDER`.
- **Tránh từ khóa hoặc tên gây nhầm lẫn**, chẳng hạn `ORDER`, `DATE`, `USER`, vì có thể trùng từ khóa hoặc tên dùng rộng rãi.
- **Không đặt tên theo kiểu dữ liệu** nếu kiểu có thể thay đổi, như `STR_CUSTOMER_NAME` hoặc `NUM_AMOUNT`; tên nên phản ánh ngữ nghĩa.
- **Dùng viết tắt có chuẩn**. `ID`, `URL` có thể quen thuộc; `DT`, `CD`, `FLG` chỉ nên dùng khi glossary quy định nhất quán.
- **Quan tâm giới hạn độ dài tên**. Oracle từ các phiên bản hiện đại (12.2 trở lên, tùy cấu hình tương thích và loại identifier) thường hỗ trợ đến **128 byte** cho nhiều tên đối tượng; hệ thống cũ và một số loại tên có thể chịu giới hạn **30 byte** hoặc giới hạn riêng. Giữ tên ngắn, rõ và kiểm tra version/compatibility của dự án.

Ví dụ:

~~~sql
-- Tên không quoted được Oracle chuẩn hóa:
CREATE TABLE lab_note (
    note_id NUMBER PRIMARY KEY
);

-- Tham chiếu đều có thể trỏ cùng một bảng:
SELECT note_id FROM lab_note;
SELECT NOTE_ID FROM LAB_NOTE;
~~~

Ngược lại, quoted identifier giữ nguyên phân biệt hoa/thường:

~~~sql
CREATE TABLE "LabNote" (
    "NoteId" NUMBER PRIMARY KEY
);

-- Với bảng quoted, câu này là dạng tham chiếu đúng:
SELECT "NoteId" FROM "LabNote";
~~~

Việc dùng tên quoted thường xuyên gây bất tiện vì mọi công cụ, câu SQL và migration phải giữ đúng chữ hoa/thường. Hãy hạn chế trừ khi có yêu cầu tích hợp đặc biệt và đã thống nhất convention rõ ràng.

### 7.2. Chọn số ít hay số nhiều cho tên bảng

Một nhóm có thể chọn `CUSTOMER` / `ORDER_ITEM` (số ít) hoặc `CUSTOMERS` / `ORDER_ITEMS` (số nhiều). Không có quy tắc Oracle bắt buộc phải chọn một phương án. Điều quan trọng là **nhất quán trong cùng schema**.

Ví dụ một dự án chọn **danh từ số ít**:

| Đối tượng | Tên gợi ý | Vì sao |
|---|---|---|
| Bảng khách hàng | `CUSTOMER` | Một dòng đại diện cho một khách hàng |
| Bảng đơn hàng | `SALES_ORDER` | Tránh `ORDER` dễ xung đột từ khóa; mô tả lĩnh vực |
| Dòng chi tiết đơn hàng | `SALES_ORDER_ITEM` | Một dòng đại diện cho chi tiết của một đơn hàng |
| Bảng mã tiền tệ | `CURRENCY` | Mỗi dòng là một đơn vị tiền tệ |
| Bảng ghi nhận sự kiện | `ORDER_EVENT` | Một dòng là một sự kiện; không nhầm với trạng thái hiện tại |

Không cần đặt prefix vào mọi tên bảng nếu schema đã phân biệt rõ domain. Ngược lại, trong schema tích hợp nhiều domain, một prefix như `SALES_` hoặc `HR_` có thể giúp nhóm đối tượng dễ hơn. Hãy nêu rõ điều này trong convention của dự án.

### 7.3. Quy ước đặt tên cột

| Vai trò | Gợi ý tên | Cách hiểu |
|---|---|---|
| Primary key kỹ thuật | `CUSTOMER_ID`, `ORDER_ID` | Khóa ổn định của đối tượng |
| Foreign key | `CUSTOMER_ID` trong bảng đơn hàng | Tên thể hiện đối tượng được tham chiếu |
| Business key | `CUSTOMER_CODE`, `ORDER_NUMBER` | Mã/tên định danh nghiệp vụ, có thể khác khóa kỹ thuật |
| Số lượng | `QUANTITY`, `ITEM_COUNT` | Nên comment rõ đơn vị đo khi cần |
| Giá trị tiền | `UNIT_PRICE`, `TOTAL_AMOUNT` | Nên kèm đơn vị tiền hoặc `CURRENCY_CODE` |
| Trạng thái | `ORDER_STATUS`, `PAYMENT_STATUS` | Cần ghi rõ các giá trị/máy trạng thái |
| Thời gian tạo | `CREATED_AT`, `ORDERED_AT` | Cần nói rõ timezone, thời điểm và nguồn |
| Ngày hiệu lực | `EFFECTIVE_FROM`, `EFFECTIVE_TO` | Cần định nghĩa khoảng bao gồm/không bao gồm |
| Cờ logic | `IS_ACTIVE` hoặc `ACTIVE_FLAG` | Chỉ chọn một convention và nêu rõ giá trị biểu diễn |

Tên `CREATED_AT` hay `PAID_AT` cho biết đó là mốc thời gian; `CREATED_DATE` gợi ý chỉ phần ngày. Trong Oracle, kiểu `DATE` thực tế chứa cả ngày và giờ đến giây; vì vậy **tên cột và comment phải nói rõ ngữ nghĩa**, đừng chỉ suy từ chữ `DATE` trong kiểu dữ liệu.

Tên cột không nên mơ hồ:

| Tên mơ hồ | Tên rõ nghĩa hơn | Lợi ích |
|---|---|---|
| `ID` | `ORDER_ID` | Dễ nhận biết trong SQL join và xuất báo cáo |
| `CODE` | `CURRENCY_CODE` | Biết mã thuộc thực thể nào |
| `DATE` | `ORDERED_AT` | Mốc thời gian được mô tả cụ thể |
| `VALUE` | `TOTAL_AMOUNT` | Biết ý nghĩa của giá trị số |
| `STATUS` | `PAYMENT_STATUS` | Tránh nhầm nhiều loại trạng thái |
| `TYPE` | `CUSTOMER_TYPE` | Xác định loại của đối tượng nào |

Tùy quy ước nhóm, khóa chính của bảng có thể đặt đơn giản là `ID` để tránh lặp trong ORM, nhưng khi đó phải bảo đảm tất cả developer hiểu convention và SQL join luôn dùng alias rõ ràng. Bài thực hành này dùng `<ENTITY>_ID` để dễ đọc với SQL trực tiếp.

### 7.4. Đặt tên constraint, index và sequence

Oracle tự sinh tên constraint dạng `SYS_C...` nếu không chỉ định. Những tên đó khó nhận diện trong lỗi hoặc khi review DDL. Một quy ước phổ biến:

| Loại | Prefix gợi ý | Ví dụ |
|---|---|---|
| Primary key | `PK_` | `PK_LAB_ORDER` |
| Foreign key | `FK_` | `FK_LAB_ORDER_CUSTOMER` |
| Unique constraint | `UQ_` | `UQ_LAB_CUSTOMER_CODE` |
| Check constraint | `CK_` | `CK_LAB_ORDER_STATUS` |
| Index thông thường | `IX_` | `IX_LAB_ORDER_ORDERED_AT` |
| Sequence nếu dùng riêng | `SEQ_` | `SEQ_LAB_ORDER` |
| View | `V_` | `V_ORDER_SUMMARY` |

Đây là convention do nhóm lựa chọn, **không phải quy tắc Oracle bắt buộc**. Cần tính giới hạn độ dài tên và tránh những tên trùng nhau trong cùng namespace Oracle. Một chỉ mục được Oracle tự tạo để hỗ trợ unique/primary key có thể mang tên liên quan constraint; đừng giả định tất cả index đều cần một tên độc lập.

Ví dụ index hỗ trợ truy vấn:

~~~sql
CREATE INDEX ix_lab_order_customer_status
ON lab_order (customer_id, order_status);
~~~

Tên index nêu thực thể và các cột chính, nhưng **không thể thay thế mô tả vì sao index tồn tại**. Với những quyết định tối ưu quan trọng, nên lưu lý do trong migration, tài liệu tuning hoặc design record.

## 8. Comment tốt nên ghi những gì?

Một comment hữu ích trả lời câu hỏi **người đọc thực sự cần**, thay vì nhắc lại tên cột.

| Đặc điểm | Comment thiếu thông tin | Comment hữu ích hơn |
|---|---|---|
| Đơn vị | “Số tiền đơn hàng” | “Tổng tiền theo mã tiền tệ ở CURRENCY_CODE; NUMBER(15,2)” |
| Trạng thái | “Trạng thái đơn hàng” | “NEW = mới tạo; PAID = đã thanh toán; CANCELLED = đã hủy” |
| Thời gian | “Ngày tạo” | “Thời điểm Oracle tạo bản ghi, theo SYSTIMESTAMP” |
| Quan hệ | “Mã khách hàng” | “Khóa ngoại tới LAB_CUSTOMER.CUSTOMER_ID” |
| Dữ liệu tính toán | “Giá trị cuối” | “Tổng trước/hoặc sau chiết khấu, đã/hoặc chưa gồm thuế” |
| Giá trị null | “Ngày kết thúc” | “NULL khi hồ sơ còn hiệu lực; nếu có thì là mốc kết thúc không bao gồm” |
| Phạm vi | “Bảng thanh toán” | “Một dòng là một lần ghi nhận giao dịch thanh toán, có thể nhiều dòng cho một đơn hàng” |

Các dạng thông tin đáng chú ý:

1. **Business definition:** một dòng hoặc một giá trị thật sự đại diện cho gì?
2. **Grain và cardinality:** một khách hàng có thể có bao nhiêu đơn hàng; một dòng dữ liệu biểu thị một giao dịch hay một snapshot?
3. **Domain/enum:** tập trạng thái, cách diễn giải mã, giá trị mặc định.
4. **Unit/currency/timezone:** đơn vị đo, cách làm tròn tiền, thời điểm theo vùng giờ.
5. **Null semantics:** `NULL` có nghĩa “chưa biết”, “chưa áp dụng”, hay “chưa có sự kiện”?
6. **Source of truth:** hệ thống nào sinh dữ liệu, quy trình nào cập nhật, trường nào chỉ là bản sao.
7. **Privacy và retention:** dữ liệu có thuộc loại nhạy cảm, có chính sách lưu trữ/xóa nào; dùng mô tả phân loại chung, tránh ghi giá trị dữ liệu thật hoặc bí mật vào comment.

Ví dụ trong hệ thống đơn hàng, nếu `TOTAL_AMOUNT` đã gồm thuế, comment phải nói rõ điều đó. Không nên tự suy “total amount” mặc định là trước thuế hay sau thuế. Các giả định khác nhau có thể tạo sai lệch trong báo cáo dù SQL không hề báo lỗi.

### Comment không nên chứa những gì?

- Password, API key, token, dữ liệu khách hàng thật hoặc thông tin bí mật vận hành.
- Tài liệu dài hàng trang khó đọc trong công cụ catalog.
- Những lời hứa không được hệ thống bảo đảm, chẳng hạn “luôn unique” nếu không có constraint và quy trình kiểm soát tương ứng.
- Nội dung chỉ đúng trong một môi trường thử nghiệm mà không nêu phạm vi.
- Câu ghi chú chung chung như “Cột ID”, “Bảng data” hoặc “Dùng cho hệ thống”.

## 9. Tên constraint và comment phối hợp ra sao?

Tài liệu hóa mối quan hệ giữa hai bảng cần cả **metadata cấu trúc** lẫn **ý nghĩa**. Ví dụ `FK_LAB_ORDER_CUSTOMER` chứng minh cột `LAB_ORDER.CUSTOMER_ID` tham chiếu bảng khách hàng; comment có thể giải thích đây là khách hàng **đặt hàng**, không phải khách hàng **được xuất hóa đơn** nếu hai vai trò khác nhau.

Đọc constraint của một bảng:

~~~sql
SELECT
    c.constraint_name,
    c.constraint_type,
    c.table_name,
    cc.column_name,
    cc.position,
    c.status,
    c.validated
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.table_name = 'LAB_ORDER'
ORDER BY c.constraint_name, cc.position;
~~~

Một số `CONSTRAINT_TYPE` thường gặp:

| Mã | Nghĩa |
|---|---|
| `P` | Primary key |
| `R` | Foreign key (referential integrity) |
| `U` | Unique |
| `C` | Check constraint, bao gồm một số ràng buộc NOT NULL được biểu diễn trong catalog |

`STATUS` và `VALIDATED` giúp hiểu constraint có bật và đã được kiểm tra với dữ liệu hiện có hay chưa. Một constraint tồn tại trong metadata nhưng bị disable hoặc ở trạng thái không validated không có cùng ý nghĩa bảo đảm dữ liệu như constraint đang enable/validated.

Thông tin quan hệ tham chiếu của foreign key còn có ở `R_OWNER` và `R_CONSTRAINT_NAME` trong `USER_CONSTRAINTS`; muốn lập ERD đầy đủ, cần liên kết đến constraint cha và đúng vị trí cột đối với khóa nhiều cột. Không nên chỉ dựa trên việc hai cột đều tên `CUSTOMER_ID` mà tự kết luận có foreign key được database thực thi.

## 10. Sinh bản data dictionary từ metadata

Một tài liệu data dictionary thường có hai cấp:

**Cấp bảng:** schema, PDB, tên bảng, grain, mô tả nghiệp vụ, nguồn dữ liệu, owner nghiệp vụ, chính sách lưu trữ, quan hệ chính.

**Cấp cột:** tên cột, kiểu dữ liệu, nullable, default, PK/FK, mô tả, miền giá trị, đơn vị, nguồn dữ liệu và ví dụ định dạng **giả lập** nếu cần.

Oracle cung cấp nhiều thông tin kỹ thuật trực tiếp qua data dictionary, nhưng các thông tin nghiệp vụ như owner, chính sách retention hoặc glossary thường phải quản lý trong repository/catalog riêng. Có thể kết hợp cả hai thay vì cố nhét mọi thứ vào một comment.

Ví dụ truy vấn tìm bảng/cột chưa có comment, phục vụ công việc bổ sung tài liệu:

~~~sql
-- Bảng chưa có mô tả
SELECT table_name
FROM user_tab_comments
WHERE table_type = 'TABLE'
  AND comments IS NULL
ORDER BY table_name;

-- Cột chưa có mô tả trong hai bảng ví dụ
SELECT c.table_name, c.column_name
FROM user_tab_columns c
LEFT JOIN user_col_comments cc
  ON cc.table_name = c.table_name
 AND cc.column_name = c.column_name
WHERE c.table_name IN ('LAB_CUSTOMER', 'LAB_ORDER')
  AND cc.comments IS NULL
ORDER BY c.table_name, c.column_id;
~~~

Kết quả chỉ cho biết **thiếu comment**, không đánh giá comment đã viết có đúng nghiệp vụ hay không. Một schema có đủ 100% comment vẫn có thể có mô tả sai hoặc lỗi thời. Chất lượng tài liệu phải được đánh giá bởi người hiểu dữ liệu và quy trình vận hành.

### Ví dụ xuất metadata kèm mô tả bằng SQL*Plus

~~~sql
SET PAGESIZE 1000
SET LINESIZE 200
SET LONG 2000

SELECT c.table_name,
       c.column_id,
       c.column_name,
       c.data_type,
       c.nullable,
       cc.comments
FROM user_tab_columns c
LEFT JOIN user_col_comments cc
  ON cc.table_name = c.table_name
 AND cc.column_name = c.column_name
WHERE c.table_name = 'LAB_ORDER'
ORDER BY c.column_id;
~~~

Trong SQLcl, SQL Developer hoặc công cụ catalog, có thể dùng truy vấn tương tự để xuất CSV, tạo Markdown/HTML hoặc đổ vào một hệ thống tài liệu. Những lệnh `SET` bên trên là lệnh của SQL*Plus/SQLcl, không phải SQL chuẩn để gửi qua `PreparedStatement`.

**Nguyên tắc sinh tài liệu:** chọn một nguồn sự thật cho metadata kỹ thuật (database được triển khai từ migration), và ghi rõ **PDB, schema, phiên bản release, thời điểm trích xuất** trên bản tài liệu. Không lấy metadata staging rồi tuyên bố đó là cấu trúc production nếu hai môi trường đang khác version.

## 11. Quản lý comment và naming convention trong migration

Một quy trình schema change tốt cập nhật DDL và chú thích **trong cùng thay đổi được review**.

Ví dụ cấu trúc repository:

~~~text
database/
├── migrations/
│   ├── V001__create_customer_and_order.sql
│   ├── V002__add_table_and_column_comments.sql
│   └── V003__add_order_payment_reference.sql
├── conventions/
│   └── naming-and-documentation.md
└── docs/
    ├── data-dictionary.md
    ├── erd.md
    └── business-glossary.md
~~~

Đây là tên file minh họa cho quy ước migration kiểu Flyway; công cụ cụ thể có thể dùng quy tắc tên khác. Khi một migration thay đổi ý nghĩa `TOTAL_AMOUNT` từ chưa gồm thuế sang đã gồm thuế, nhóm cần:

1. Xác định thay đổi nghiệp vụ và ảnh hưởng tới ứng dụng/báo cáo.
2. Cập nhật DDL, constraint hoặc dữ liệu nếu thực sự cần.
3. Cập nhật `COMMENT ON COLUMN` để mô tả **ngữ nghĩa mới**.
4. Cập nhật data dictionary/glossary/ERD liên quan.
5. Review tác động tới JDBC mapping, SQL, API và dữ liệu đã tồn tại.
6. Triển khai migration theo trình tự và lưu dấu phiên bản đã áp dụng.

Chỉ đổi comment **không tự biến đổi dữ liệu cũ**. Nếu business rule thay đổi, phải có kế hoạch migration dữ liệu phù hợp. Ngược lại, nếu chỉ sửa lỗi chính tả trong chú thích, không nhất thiết phải tái tạo bảng.

### Ví dụ migration thay mô tả cột

~~~sql
-- V003__clarify_total_amount.sql
COMMENT ON COLUMN lab_order.total_amount IS
  'Tổng tiền khách phải trả, gồm thuế và sau chiết khấu; tiền tệ ở CURRENCY_CODE.';
~~~

Comment ở đây chỉ đúng khi **code tính tiền, dữ liệu và nghiệp vụ thực sự đã được triển khai theo định nghĩa đó**. Nếu hệ thống vẫn lưu tiền trước thuế, cập nhật comment như vậy sẽ làm sai data dictionary; comment không kiểm soát được công thức tính.

### Naming convention không nên thay đổi tùy hứng

Đổi tên bảng hoặc cột sau khi ứng dụng đã dùng trong SQL/JPA/PLSQL có thể làm hỏng truy vấn, view, procedure và migration. Vì vậy:

- Ưu tiên chọn convention trước khi tạo những bảng đầu tiên.
- Chỉ rename khi lợi ích rõ và đã kiểm tra các đối tượng phụ thuộc.
- Với schema cũ, có thể giữ tên hiện tại và dùng comment/glossary để giải thích thay vì đổi tên hàng loạt.
- Khi buộc phải rename, lập kế hoạch tương thích/triển khai tuần tự, không chỉ sửa file DDL gốc.

## 12. Phân biệt metadata Oracle và tài liệu nghiệp vụ mở rộng

Không phải thông tin nào cũng có chỗ lưu chính thức trong `COMMENT ON`.

| Loại thông tin | Nơi lưu đề xuất | Ví dụ |
|---|---|---|
| Mô tả bảng/cột ngắn gọn | `COMMENT ON TABLE/COLUMN` | “Một dòng biểu diễn một đơn hàng” |
| Kiểu dữ liệu, nullability | Data dictionary | `NUMBER(15,2) NOT NULL` |
| PK/FK/UQ/CK | Constraint metadata | `FK_LAB_ORDER_CUSTOMER` |
| Giá trị enum và ý nghĩa | Comment + glossary/bảng mã | `NEW`, `PAID`, `CANCELLED` |
| Luồng nguồn dữ liệu | Data catalog / lineage docs | Dữ liệu phát sinh từ dịch vụ bán hàng |
| SLA cập nhật | Tài liệu nghiệp vụ/vận hành | Được đồng bộ mỗi 15 phút |
| Data owner | Catalog/quy trình quản trị | Nhóm chịu trách nhiệm định nghĩa dữ liệu |
| Phân loại nhạy cảm | Catalog/chính sách bảo mật | Dữ liệu cá nhân, dữ liệu công khai |
| Lịch sử thay đổi | Git + migration history | Vì sao thêm `PAYMENT_REFERENCE` |

Với ứng dụng Java, entity JPA như `@Table(name = "LAB_ORDER")` và `@Column(name = "ORDER_STATUS")` mô tả ánh xạ phía ứng dụng, không thay thế comment ở database. Một consumer khác dùng SQL trực tiếp vẫn cần metadata rõ ràng ngay trong Oracle.

## 13. Những lỗi thường gặp khi tài liệu hóa bảng/cột

| Hiện tượng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| Truy vấn `USER_TAB_COMMENTS` không thấy bảng | Đang đăng nhập user khác hoặc PDB khác | Kiểm tra `SESSION_USER`, `CON_NAME`; dùng `ALL_TAB_COMMENTS` khi cần |
| Bảng có tên trong catalog nhưng `COMMENTS` là `NULL` | Chưa ghi comment hoặc đã bỏ comment | Thêm `COMMENT ON TABLE` qua migration |
| Comment ghi “unique” nhưng vẫn có dữ liệu trùng | Chỉ ghi chú mà không có unique constraint/quy tắc hiệu lực | Tạo constraint phù hợp sau khi xử lý dữ liệu |
| Cột `AMOUNT` có giá trị nhưng không biết đơn vị | Tên mơ hồ, thiếu currency/unit | Bổ sung `CURRENCY_CODE`/unit và mô tả rõ |
| SQL lỗi vì identifier phân biệt hoa/thường | Bảng/cột tạo bằng dấu nháy kép có chữ thường/hỗn hợp | Dùng đúng quoted identifier hoặc thống nhất lại convention |
| Đổi tên cột nhưng ứng dụng hỏng | SQL/JPA/view/procedure phụ thuộc tên cũ | Lập migration và cập nhật tất cả consumer |
| Chạy `ROLLBACK` nhưng comment không trở lại | `COMMENT ON` là DDL, có implicit commit | Quản lý bằng migration chỉnh sửa tiếp theo |
| Export data dictionary không đủ bảng của schema khác | Tài khoản không có quyền nhìn thấy catalog | Dùng đúng view và quyền theo nguyên tắc tối thiểu |
| Mọi bảng đều có comment nhưng nội dung đã cũ | Migration nghiệp vụ không cập nhật tài liệu | Review comment và glossary cùng schema change |
| Công cụ tự sinh DDL sai từ một truy vấn đơn giản | Chưa tính đủ type, length semantics, default, identity, constraint | Dùng `DBMS_METADATA`/DDL tooling phù hợp |

## 14. Bài tập thực hành

### Bài 1 — Đọc một schema chưa có tài liệu

Giả sử bạn được giao các cột:

~~~text
ORDER_ID        NUMBER
CUSTOMER_ID     NUMBER
STATUS          VARCHAR2(20)
AMOUNT          NUMBER(15,2)
DATE_CREATED    DATE
~~~

Hãy đề xuất tên rõ nghĩa hơn cho `STATUS`, `AMOUNT` và `DATE_CREATED`. Viết một câu comment cho từng cột làm rõ **loại trạng thái**, **tiền tệ**, **múi giờ/thời điểm**. Nếu chưa biết thông tin nghiệp vụ, hãy đặt câu hỏi cho người phụ trách trước khi đưa ra định nghĩa chính thức.

**Gợi ý:** `ORDER_STATUS`, `TOTAL_AMOUNT`, `CREATED_AT` là những ứng viên; tên phù hợp cuối cùng phụ thuộc ý nghĩa thật của dữ liệu.

### Bài 2 — Ghi chú và truy vấn lại metadata

Trong schema lab, chạy:

~~~sql
COMMENT ON TABLE lab_order IS
  'Một dòng biểu diễn một đơn hàng của khách hàng.';

COMMENT ON COLUMN lab_order.order_status IS
  'NEW = mới tạo; PAID = đã thanh toán; CANCELLED = đã hủy.';

SELECT table_name, comments
FROM user_tab_comments
WHERE table_name = 'LAB_ORDER';

SELECT column_name, comments
FROM user_col_comments
WHERE table_name = 'LAB_ORDER'
  AND column_name = 'ORDER_STATUS';
~~~

**Kết quả mong đợi:** text chú thích vừa ghi xuất hiện trong cột `COMMENTS` của đúng đối tượng.

### Bài 3 — Kiểm tra tính nhất quán của tên khóa

Trong `LAB_ORDER` có `CUSTOMER_ID`. Hãy dùng `USER_CONSTRAINTS` và `USER_CONS_COLUMNS` xác định có foreign key tham chiếu customer hay không. Giải thích vì sao chỉ có tên cột `CUSTOMER_ID` là chưa đủ để khẳng định database đang bảo vệ quan hệ này.

**Đáp án định hướng:** tên gợi ý ngữ nghĩa; foreign key có trạng thái thực thi mới là ràng buộc ở mức database. Comment mô tả vai trò nhưng không thay thế constraint.

### Bài 4 — Bảng tiền tệ

Giả sử `TOTAL_AMOUNT = 1000` và `CURRENCY_CODE = 'VND'`. Ứng dụng bên ngoài lại hiểu 1000 là USD. Lỗi này có thể xảy ra dù kiểu `NUMBER` và constraint đều hợp lệ không?

**Đáp án:** Có. Đây là sai ngữ nghĩa/đơn vị của dữ liệu ở ranh giới hệ thống. Data dictionary và contract API cần quy định rõ đơn vị, mã tiền tệ và cách quy đổi.

### Bài 5 — Cập nhật schema có comment

Ứng dụng bổ sung cột `PAID_AT TIMESTAMP WITH TIME ZONE`. Hãy đề xuất DDL, một comment giải thích ý nghĩa `NULL` và cách đưa thay đổi vào migration có phiên bản.

Ví dụ:

~~~sql
ALTER TABLE lab_order
  ADD paid_at TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN lab_order.paid_at IS
  'Thời điểm thanh toán thành công; NULL nếu chưa ghi nhận thanh toán.';
~~~

Nếu business thực tế cho phép hủy thanh toán hoặc có nhiều lần thanh toán, phải xem lại mô hình: một cột `PAID_AT` có thể không đủ biểu diễn lịch sử và cần bảng sự kiện thanh toán riêng. Comment làm rõ giới hạn của mô hình nhưng không tự giải quyết giới hạn đó.

### Bài 6 — Review một comment chưa tốt

Comment cũ:

~~~sql
COMMENT ON COLUMN lab_order.order_status IS
  'Trang thai';
~~~

Hãy viết lại để nói rõ các giá trị và sự khác nhau giữa “mới tạo”, “đã thanh toán” và “đã hủy”. Sau đó kiểm tra xem `CHECK` constraint hiện tại có khớp danh sách mã hay không. Nếu enum trong code Java còn có `REFUNDED` mà database chưa cho phép, hãy ghi nhận sự không đồng bộ để thiết kế thay đổi trước khi sửa comment.

## 15. Bản đồ ghi nhớ khi thêm một bảng mới

~~~text
Yêu cầu nghiệp vụ
       |
       v
Định nghĩa dữ liệu
  - Một dòng là gì? Ai sở hữu dữ liệu?
  - Khóa và quan hệ là gì?
  - Đơn vị, trạng thái, thời gian, NULL nghĩa gì?
       |
       v
Đặt tên nhất quán
  TABLE / COLUMN / PK / FK / UQ / CK / INDEX
       |
       v
Viết DDL
  DATA TYPE + NULLABILITY + CONSTRAINT + DEFAULT
       |
       v
Viết COMMENT ON TABLE / COMMENT ON COLUMN
  Giải thích ngữ nghĩa mà tên và DDL chưa diễn đạt
       |
       v
Đưa vào migration và review cùng ứng dụng
       |
       v
Triển khai đúng PDB/schema
       |
       v
Đọc USER_TAB_COMMENTS / USER_COL_COMMENTS
và kết hợp catalog để xuất data dictionary
       |
       v
Duy trì mô tả khi nghiệp vụ và schema đổi
~~~

Một schema dễ hiểu bắt đầu từ **tên đối tượng rõ ràng**, tiếp theo là **kiểu dữ liệu và constraint đúng**, rồi đến **comment có ý nghĩa nghiệp vụ**. Oracle cho phép lưu comment ngay trong metadata của bảng/cột, đồng thời cung cấp các view `USER_*`, `ALL_*` và `DBA_*` để khai thác chúng. Hãy đặt comment trong migration được version hóa, đối chiếu với glossary khi nghiệp vụ thay đổi, và dùng cùng một quy ước đặt tên từ bảng, cột đến khóa và index: tài liệu khi đó có thể được sinh ra từ database mà vẫn giữ đúng ý nghĩa cho người sử dụng.
