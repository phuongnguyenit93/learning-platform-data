# PRIMARY KEY, UNIQUE và quan hệ với chỉ mục trong Oracle Database

Khi xây dựng một bảng quan hệ trong **Oracle Database**, việc xác định bản ghi nào là duy nhất là nền tảng của tính toàn vẹn dữ liệu. Hai ràng buộc thường được dùng nhất là **`PRIMARY KEY`** (khóa chính) và **`UNIQUE`** (khóa duy nhất). Oracle thường sử dụng **index** để thực thi chúng, nhưng ba khái niệm này không đồng nghĩa: *constraint* biểu đạt quy tắc dữ liệu phải tuân thủ, còn *index* là cấu trúc truy cập dữ liệu, có thể phục vụ thực thi constraint và tối ưu truy vấn.

Hãy hình dung một hệ thống bán hàng:

- Mỗi khách hàng phải có một `CUSTOMER_ID` xác định, không được trùng và không được để trống.
- `USERNAME` của mỗi khách hàng có thể cần duy nhất vì dùng để đăng nhập.
- `EMAIL` có thể chưa được cung cấp, nhưng nếu đã cung cấp thì không được trùng với email của khách hàng khác theo quy tắc ứng dụng.
- Mỗi đơn hàng phải có mã đơn duy nhất và tham chiếu tới khách hàng hợp lệ.

`PRIMARY KEY`, `UNIQUE`, index và foreign key phối hợp giải quyết các yêu cầu này. Bài học trình bày cách khai báo, hành vi với `NULL`, khóa ghép, index được Oracle tạo hoặc tái sử dụng, các trường hợp đặc biệt như **deferrable constraint**, cách đọc metadata và những lỗi thường gặp khi vận hành.

## 1. Phân biệt khóa chính, khóa duy nhất và chỉ mục

| Thành phần | Bản chất | Bảo đảm hoặc mục đích | Có tự cấm `NULL`? | Có thể có bao nhiêu trên bảng? |
|---|---|---|---|---|
| **`PRIMARY KEY` constraint** | Quy tắc toàn vẹn | Mỗi hàng có một khóa định danh duy nhất và đầy đủ | **Có**, mọi cột tham gia khóa chính phải `NOT NULL` | Tối đa **một** khóa chính; khóa đó có thể gồm nhiều cột |
| **`UNIQUE` constraint** | Quy tắc toàn vẹn | Ngăn các tổ hợp giá trị khóa bị trùng theo quy tắc của Oracle | **Không**, trừ khi cột còn có `NOT NULL` | Có thể có **nhiều** ràng buộc unique |
| **Unique index** | Cấu trúc truy cập và kiểm tra duy nhất ở mức index key | Không cho phép các khóa index bị trùng theo ngữ nghĩa unique index | Không tự buộc cột nguồn `NOT NULL` | Có thể có nhiều index, tùy giới hạn và thiết kế |
| **Nonunique index** | Cấu trúc truy cập | Hỗ trợ tìm kiếm/join/sắp xếp, hoặc được Oracle dùng để thực thi một constraint phù hợp | Không | Có thể có nhiều index |

Điểm mấu chốt:

1. **Khóa chính là một constraint**, không phải tên khác của unique index.
2. **Unique constraint là một constraint**, có thể có index hỗ trợ; index đó không nhất thiết luôn mang thuộc tính `UNIQUE`.
3. **Unique index có thể tự ngăn một số giá trị trùng** ngay cả khi không có constraint tương ứng, nhưng không thay thế hoàn toàn ngữ nghĩa, metadata và khả năng tham chiếu của `PRIMARY KEY`/`UNIQUE` constraint.
4. **Foreign key tham chiếu tới khóa chính hoặc khóa duy nhất được khai báo bằng constraint** ở bảng cha; chỉ tạo unique index trên các cột ở bảng cha không tự biến chúng thành một khóa được foreign key tham chiếu.

```text
                        TABLE CUSTOMERS
                     +--------------------+
                     | CUSTOMER_ID        |---- PRIMARY KEY constraint
                     | USERNAME           |---- UNIQUE constraint
                     | EMAIL              |---- UNIQUE constraint
                     +--------------------+
                             |
                      Oracle chọn/tạo
                      index hỗ trợ
                             v
                  INDEX (B-tree thường gặp)
                  - tra cứu index key
                  - hỗ trợ kiểm tra trùng
                  - có thể được optimizer dùng

               Constraint != vật thể index
```

## 2. PRIMARY KEY: định danh mỗi hàng bằng một khóa hợp lệ

Ràng buộc **`PRIMARY KEY`** yêu cầu giá trị khóa là **duy nhất** và **không `NULL`**. Một bảng chỉ có một primary key constraint, nhưng khóa có thể là **khóa đơn** (một cột) hoặc **khóa ghép** (nhiều cột).

### 2.1. Khai báo khóa chính một cột

```sql
-- Chạy trong schema thực hành Oracle DEV/TEST có quyền CREATE TABLE.
CREATE TABLE lab_customers (
    customer_id NUMBER NOT NULL,
    username    VARCHAR2(50 CHAR) NOT NULL,
    email       VARCHAR2(200 CHAR),
    full_name   VARCHAR2(100 CHAR),
    CONSTRAINT pk_lab_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_lab_customers_username UNIQUE (username),
    CONSTRAINT uq_lab_customers_email UNIQUE (email)
);
```

Ở đây:

- `PK_LAB_CUSTOMERS` bắt buộc `CUSTOMER_ID` có giá trị và không trùng.
- `UQ_LAB_CUSTOMERS_USERNAME` cấm trùng username; cột `USERNAME` đồng thời được khai báo `NOT NULL` vì nghiệp vụ không cho tài khoản thiếu username.
- `UQ_LAB_CUSTOMERS_EMAIL` cấm các giá trị email được cung cấp trùng nhau nhưng vẫn cho phép chưa khai báo email qua `NULL`.

Viết `CUSTOMER_ID NUMBER NOT NULL` cạnh `PRIMARY KEY` là cách diễn đạt rõ ý cho người đọc; bản thân ràng buộc primary key đã yêu cầu không null. Khi thử `INSERT` thiếu `CUSTOMER_ID`, Oracle từ chối thay vì tự sinh giá trị, trừ khi bạn thiết kế thêm **identity column, sequence/default hoặc cơ chế sinh khóa**.

### 2.2. Khai báo khóa chính tại mức cột và mức bảng

Với một cột, có thể dùng cú pháp inline:

```sql
CREATE TABLE lab_products (
    product_id   NUMBER CONSTRAINT pk_lab_products PRIMARY KEY,
    product_name VARCHAR2(100 CHAR) NOT NULL
);
```

Với khóa ghép, dùng constraint ở mức bảng:

```sql
CREATE TABLE lab_order_items (
    order_id   NUMBER NOT NULL,
    line_no    NUMBER NOT NULL,
    product_id NUMBER NOT NULL,
    quantity   NUMBER DEFAULT 1 NOT NULL,
    CONSTRAINT pk_lab_order_items PRIMARY KEY (order_id, line_no),
    CONSTRAINT ck_lab_order_items_quantity CHECK (quantity > 0)
);
```

Khóa của `LAB_ORDER_ITEMS` là cặp `(ORDER_ID, LINE_NO)`. Giá trị `ORDER_ID = 100` có thể xuất hiện ở nhiều dòng, và `LINE_NO = 1` cũng có thể xuất hiện ở nhiều đơn hàng; chỉ **cặp giá trị** phải duy nhất. Tất cả thành phần của khóa ghép phải không `NULL`.

| `ORDER_ID` | `LINE_NO` | Có thể tồn tại cùng nhau? | Giải thích |
|---:|---:|---|---|
| 100 | 1 | Có | Dòng đầu của đơn 100 |
| 100 | 2 | Có | Cặp khóa khác dòng trước |
| 101 | 1 | Có | Cặp khóa khác vì `ORDER_ID` khác |
| 100 | 1 | **Không**, nếu đã có cặp đầu | Vi phạm cùng cặp primary key |
| 100 | `NULL` | **Không** | Cột tham gia primary key không được `NULL` |

### 2.3. Một bảng có bao nhiêu primary key?

Một bảng **chỉ có một** ràng buộc `PRIMARY KEY`, dù có thể có nhiều **candidate key** hoặc nhiều `UNIQUE` constraint. Nếu hệ thống muốn định danh đơn hàng bằng `ORDER_ID` và đồng thời cần mã nghiệp vụ `ORDER_CODE` duy nhất, cách thiết kế thường là:

```sql
CREATE TABLE lab_orders (
    order_id      NUMBER NOT NULL,
    order_code    VARCHAR2(40 CHAR) NOT NULL,
    customer_id   NUMBER NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_lab_orders PRIMARY KEY (order_id),
    CONSTRAINT uq_lab_orders_code UNIQUE (order_code),
    CONSTRAINT fk_lab_orders_customer FOREIGN KEY (customer_id)
        REFERENCES lab_customers (customer_id)
);
```

`ORDER_ID` là khóa chính kỹ thuật; `ORDER_CODE` được bảo vệ bằng unique constraint như khóa nghiệp vụ. Không thể khai báo thêm `PRIMARY KEY (ORDER_CODE)` thứ hai trên cùng bảng; hãy dùng `UNIQUE (ORDER_CODE)`.

### 2.4. Khóa chính và nguồn sinh giá trị

`PRIMARY KEY` **không đồng nghĩa tự tăng**. Oracle cho phép tạo ID bằng ứng dụng, sequence, identity column hoặc những chiến lược đã thiết kế. Ví dụ Oracle có hỗ trợ identity column:

```sql
CREATE TABLE lab_identity_example (
    id NUMBER GENERATED ALWAYS AS IDENTITY,
    description VARCHAR2(100 CHAR),
    CONSTRAINT pk_lab_identity_example PRIMARY KEY (id)
);
```

Identity column giúp Oracle tạo giá trị ID; primary key constraint mới là cơ chế cấm trùng và không null. Với cơ chế sinh khóa bằng sequence, **không mặc định ID liên tiếp không có khoảng trống**: sequence có thể nhảy số do rollback, cache hoặc hoạt động đồng thời; ứng dụng không nên dùng ID để suy luận số lượng bản ghi.

## 3. UNIQUE: bảo vệ khóa ứng viên và quy tắc duy nhất nghiệp vụ

**`UNIQUE` constraint** đảm bảo các giá trị khóa, hoặc tổ hợp giá trị của các cột được khai báo, không trùng theo ngữ nghĩa Oracle. Nó thích hợp cho mã nhân viên, username, mã sản phẩm, mã hóa đơn trong phạm vi tenant, mã đơn từ đối tác hoặc địa chỉ email khi nghiệp vụ cần độc nhất.

### 3.1. UNIQUE một cột và nhiều cột

Ví dụ unique đơn:

```sql
ALTER TABLE lab_customers
ADD CONSTRAINT uq_lab_customers_phone UNIQUE (phone_number);
```

Câu lệnh minh họa trên **chỉ chạy khi cột `PHONE_NUMBER` đã tồn tại** trong bảng. Nếu chưa có cột, hãy thêm cột bằng migration hợp lệ trước. Khi làm việc với schema thật, phải đối chiếu dữ liệu hiện hữu và duplicate trước khi áp constraint. Khai báo tại lúc tạo bảng thường đơn giản và dễ kiểm soát hơn.

Ví dụ unique ghép với bảng riêng:

```sql
CREATE TABLE lab_external_orders (
    id             NUMBER NOT NULL,
    partner_code   VARCHAR2(30 CHAR) NOT NULL,
    external_code  VARCHAR2(60 CHAR) NOT NULL,
    CONSTRAINT pk_lab_external_orders PRIMARY KEY (id),
    CONSTRAINT uq_lab_external_orders_partner
        UNIQUE (partner_code, external_code)
);
```

Mã `external_code = 'A100'` có thể được đối tác `PARTNER_X` và `PARTNER_Y` dùng đồng thời, nhưng **một đối tác không được có hai đơn cùng mã**. Đây là một ví dụ điển hình về unique ghép: ràng buộc dựa trên **tổ hợp**, không phải từng cột phải duy nhất riêng lẻ.

### 3.2. UNIQUE với `NULL` trong Oracle: điểm khác PRIMARY KEY

Đối với **unique constraint một cột** trong Oracle, có thể có **nhiều hàng `NULL`**. Ví dụ: nhiều khách hàng chưa cung cấp email có `EMAIL = NULL`; constraint `UNIQUE (EMAIL)` không cấm tình huống đó. Ngược lại, nếu hai hàng cùng chứa một email cụ thể, Oracle từ chối hàng trùng.

```sql
INSERT INTO lab_customers (customer_id, username, email)
VALUES (1, 'an', NULL);

INSERT INTO lab_customers (customer_id, username, email)
VALUES (2, 'binh', NULL);

INSERT INTO lab_customers (customer_id, username, email)
VALUES (3, 'chi', 'chi@example.test');

COMMIT;
```

Ba bản ghi này hợp lệ với constraint đã tạo. Nhưng lệnh sau **phải thất bại** vì email đã tồn tại:

```sql
-- Ví dụ cố tình vi phạm; KHÔNG đưa vào migration bình thường.
INSERT INTO lab_customers (customer_id, username, email)
VALUES (4, 'dung', 'chi@example.test');

-- Kết quả thường là ORA-00001 (unique constraint violated).
```

Trong SQL Oracle, `NULL` có nghĩa giá trị không xác định; toán tử `=` không coi `NULL = NULL` là `TRUE`. Muốn kiểm tra null, dùng `IS NULL`. Với cột ký tự `VARCHAR2`, Oracle hiện hành còn xử lý chuỗi rỗng `''` như `NULL`; điều đó có thể ảnh hưởng dữ liệu email, username tùy cách khai báo `NOT NULL` và application binding. Không thiết kế kiểm soát uniqueness dựa trên giả định `''` là một giá trị ký tự độc lập với null trong Oracle.

### 3.3. UNIQUE ghép và các giá trị `NULL`: không suy luận như một cột

Với **composite unique key** trong Oracle, nếu **tất cả các cột trong khóa đều `NULL`**, nhiều hàng như vậy có thể được phép. Tuy nhiên, nếu **một số thành phần có giá trị và các thành phần còn lại `NULL`**, các tổ hợp có cùng giá trị ở phần không null có thể bị xem là trùng; Oracle xử lý uniqueness của khóa ghép khác với cách suy luận đơn giản rằng “cứ có một NULL là hàng nào cũng được lặp”.

```sql
CREATE TABLE lab_pair_unique (
    id NUMBER PRIMARY KEY,
    region_code VARCHAR2(10 CHAR),
    partner_ref VARCHAR2(30 CHAR),
    CONSTRAINT uq_lab_pair UNIQUE (region_code, partner_ref)
);
```

| Giá trị `(REGION_CODE, PARTNER_REF)` | Khi đã có một hàng giống hệt, có thể thêm hàng thứ hai? | Giải thích |
|---|---|---|
| `('VN', 'X001')` | Không | Cùng tổ hợp giá trị khác null |
| `('VN', NULL)` | **Không** theo ngữ nghĩa Oracle cho khóa ghép có thành phần không null trùng | Phần khóa đã xác định tương đương nhau |
| `(NULL, 'X001')` | **Không** theo ngữ nghĩa Oracle cho khóa ghép có thành phần không null trùng | Phần khóa đã xác định tương đương nhau |
| `(NULL, NULL)` | Có thể | Toàn bộ các thành phần khóa đều null |
| `('VN', 'X001')` và `('US', 'X001')` | Có | Tổ hợp khác nhau |

Nếu nghiệp vụ thật sự chỉ cho phép một hàng duy nhất khi cả hai thuộc tính cùng thiếu, hoặc có quy tắc riêng về giá trị trống, cần thiết kế thêm constraint, kiểm soát nghiệp vụ hoặc một khóa thay thế phù hợp; **không coi `UNIQUE` nullable tự xử lý mọi trường hợp “chưa biết” theo cùng cách**.

### 3.4. `UNIQUE` không tự thay thế `NOT NULL`

Ví dụ: nếu username là bắt buộc, dùng:

```sql
username VARCHAR2(50 CHAR) NOT NULL,
CONSTRAINT uq_lab_customers_username UNIQUE (username)
```

Nếu chỉ có `UNIQUE (USERNAME)` mà không có `NOT NULL`, những tài khoản không có username vẫn có thể tồn tại. Với khóa nghiệp vụ bắt buộc, kết hợp `UNIQUE` + `NOT NULL` giúp diễn đạt đúng ý nghĩa, hoặc cân nhắc khóa chính nếu nó thực sự được chọn làm định danh chính của bảng.

## 4. Index là gì và tại sao Oracle dùng index để thực thi khóa?

**Index** là một cấu trúc lưu trữ có thể hỗ trợ tìm kiếm giá trị khóa và truy xuất ROWID/record hiệu quả. Với B-tree index thông dụng, Oracle tổ chức key theo thứ tự tìm kiếm. Index vừa có thể phục vụ **truy vấn** (tránh full table scan khi có lợi) vừa có thể phục vụ **kiểm tra uniqueness** ở thời điểm thực hiện thay đổi dữ liệu.

```text
                Dữ liệu CUSTOMER

   CUSTOMER_ID | USERNAME | EMAIL
   ------------+----------+---------------------
       10      | lan      | lan@example.test
       11      | minh     | minh@example.test
       12      | nhu      | NULL

   PK index trên CUSTOMER_ID:
       [10] --> row của Lan
       [11] --> row của Minh
       [12] --> row của Nhu

   Unique index trên USERNAME:
       ['lan']  --> row của Lan
       ['minh'] --> row của Minh
       ['nhu']  --> row của Nhu
```

Khi chèn hai hàng cùng `USERNAME` vào bảng có `UNIQUE` constraint đang được thực thi, Oracle phải phát hiện xung đột và từ chối thay đổi không hợp lệ. Index giúp Oracle làm việc này hiệu quả hơn việc phải quét toàn bộ bảng cho mỗi hàng mới.

### 4.1. Oracle thường tự tạo index hỗ trợ PK/UNIQUE

Khi tạo một primary key hoặc unique constraint được thực thi, Oracle cần cơ chế kiểm tra uniqueness. Nếu **chưa có index phù hợp**, Oracle thường **tạo một index** để hỗ trợ constraint, trong các trường hợp thông thường là **unique B-tree index**. Nếu đã có index phù hợp, Oracle có thể **tái sử dụng** index đó thay vì tự tạo thêm một index trùng chức năng.

Điều này dẫn đến một số thực tế:

- Không cần viết `CREATE UNIQUE INDEX` rồi thêm `PRIMARY KEY` như một quy trình bắt buộc cho mỗi bảng.
- Không nên tạo một index trùng hoàn toàn các cột khóa khi Oracle đã tạo index để thực thi constraint, trừ khi có nhu cầu cụ thể được đo đạc và phê duyệt.
- **Tên constraint và tên index có thể khác nhau.** Không dựa vào quy ước đặt tên để kết luận chúng là một đối tượng.
- Index dùng cho constraint có lifecycle liên quan tới thao tác enable/disable/drop constraint, nhưng cách Oracle giữ hoặc xóa index còn tùy index có được tạo tự động hay tái sử dụng, các tùy chọn lệnh và loại constraint.

### 4.2. Constraint là quy tắc; index là phương tiện

| Tình huống | Constraint | Index | Điều cần nhớ |
|---|---|---|---|
| Khai báo `PRIMARY KEY(id)` | Bảo đảm `id` duy nhất và không null | Oracle tạo hoặc dùng index hỗ trợ | Một primary key có thể được thực thi qua index khác tên |
| Khai báo `UNIQUE(code)` | Bảo đảm code không trùng theo quy tắc nullable | Oracle tạo hoặc dùng index hỗ trợ | Không thay thế ràng buộc not null |
| Chỉ `CREATE UNIQUE INDEX(code)` | Không có PK/UK constraint được khai báo từ lệnh này | Unique index cấm các index key trùng theo quy tắc Oracle | Metadata quan hệ và foreign key cần constraint riêng |
| Chỉ `CREATE INDEX(code)` | Không có quy tắc unique | Nonunique index chỉ hỗ trợ truy cập | Dữ liệu trùng vẫn được phép, nếu không có constraint khác |
| `UNIQUE` deferrable | Quy tắc có thể kiểm tra muộn tới cuối transaction | Có thể dùng nonunique index để hỗ trợ | `INDEX.UNIQUENESS` không luôn phản ánh `CONSTRAINT_TYPE` |

**Không được suy luận ngược:** thấy `USER_INDEXES.UNIQUENESS = 'UNIQUE'` không tự chứng minh bảng có một `UNIQUE` constraint; phải kiểm tra `USER_CONSTRAINTS` và index liên kết. Tương tự, `USER_INDEXES.UNIQUENESS = 'NONUNIQUE'` không có nghĩa index không thể hỗ trợ một primary key hoặc unique constraint.

### 4.3. Dùng index đã có để hỗ trợ constraint

Ví dụ trong schema lab, tạo index **không unique** trước rồi chỉ định nó khi thêm khóa chính:

```sql
CREATE TABLE lab_index_reuse (
    id NUMBER NOT NULL,
    note VARCHAR2(50 CHAR)
);

CREATE INDEX ix_lab_index_reuse_id
    ON lab_index_reuse (id);

ALTER TABLE lab_index_reuse
ADD CONSTRAINT pk_lab_index_reuse PRIMARY KEY (id)
USING INDEX ix_lab_index_reuse_id;
```

Constraint yêu cầu dữ liệu `ID` duy nhất và không null; Oracle có thể thực thi bằng một **nonunique index** phù hợp đã được chỉ định. Index này không biến thành một constraint riêng; loại index và tính chất constraint được quản lý độc lập. Ví dụ giúp hiểu rằng việc nhìn `USER_INDEXES.UNIQUENESS = NONUNIQUE` chưa đủ để kết luận cột `ID` được phép trùng.

Trong dự án thật, quyết định tái sử dụng index phải tính tới thứ tự cột, cấu trúc, partition, khả năng truy cập, phân quyền và tác động đối với optimizer. Không nên chỉ định bừa một index có tên gần giống constraint.

### 4.4. `USING INDEX` dùng để làm gì?

Khi tạo PK/UNIQUE constraint, Oracle cung cấp **`USING INDEX`** để chỉ định hoặc cấu hình index hỗ trợ trong những trường hợp phù hợp. Có thể dùng để tái sử dụng index có sẵn hoặc xác định thuộc tính lưu trữ hợp lệ cho index được tạo. Các giới hạn phụ thuộc loại constraint/index và phiên bản Oracle.

Ví dụ một bảng mới khi muốn dùng index được tạo sẵn:

```sql
CREATE TABLE lab_code_reuse (
    id NUMBER NOT NULL,
    business_code VARCHAR2(30 CHAR) NOT NULL
);

CREATE INDEX ix_lab_code_reuse_code
    ON lab_code_reuse (business_code);

ALTER TABLE lab_code_reuse
ADD CONSTRAINT uq_lab_code_reuse UNIQUE (business_code)
USING INDEX ix_lab_code_reuse_code;
```

Oracle thực thi ràng buộc dù index được khai báo ban đầu là nonunique. Nếu dữ liệu đã có duplicate, thao tác tạo/enable constraint có thể bị từ chối. Cần khảo sát và xử lý trùng dữ liệu trước khi đưa constraint vào sử dụng.

## 5. Deferrable constraint: vì sao UNIQUE/PK có thể dùng nonunique index?

Theo mặc định, ràng buộc unique hoặc primary key thường được kiểm tra theo quy tắc **không trì hoãn**. Oracle còn cho phép khai báo một số constraint là **`DEFERRABLE`**, nghĩa là có thể chọn kiểm tra tại thời điểm kết thúc câu lệnh hoặc trì hoãn kiểm tra đến lúc `COMMIT` của transaction.

Tính năng này hữu ích cho một số quy trình cập nhật liên quan nhiều hàng, ví dụ **hoán đổi hai mã vị trí duy nhất** trong cùng một transaction mà trạng thái trung gian có thể xung đột.

### 5.1. Khai báo UNIQUE deferrable

```sql
CREATE TABLE lab_seat_assignment (
    employee_id NUMBER NOT NULL,
    seat_code   VARCHAR2(20 CHAR) NOT NULL,
    CONSTRAINT pk_lab_seat_assignment PRIMARY KEY (employee_id),
    CONSTRAINT uq_lab_seat_code UNIQUE (seat_code)
        DEFERRABLE INITIALLY IMMEDIATE
);
```

Trong ví dụ này, `UQ_LAB_SEAT_CODE` **được phép chuyển sang chế độ kiểm tra deferred** trong một transaction, nhưng mặc định là immediate. Oracle không thể sử dụng một **unique index có cơ chế cấm trùng ngay lập tức** để đáp ứng mọi trạng thái tạm thời cần được cho phép bởi constraint deferred; vì vậy một deferrable unique constraint thường được thực thi qua **nonunique index**.

Điều này giải thích trường hợp rất quan trọng: **`UNIQUE` constraint đang enabled/validated nhưng index hỗ trợ lại hiển thị `NONUNIQUE` trong dictionary**. Không được xóa index hoặc sửa constraint chỉ vì thấy thuộc tính này.

### 5.2. Trì hoãn kiểm tra trong transaction

```sql
INSERT INTO lab_seat_assignment (employee_id, seat_code)
VALUES (1, 'A01');

INSERT INTO lab_seat_assignment (employee_id, seat_code)
VALUES (2, 'B02');

COMMIT;

-- Bắt đầu transaction thao tác đổi chỗ ở chế độ deferred.
SET CONSTRAINTS uq_lab_seat_code DEFERRED;

UPDATE lab_seat_assignment
SET seat_code = CASE employee_id
    WHEN 1 THEN 'B02'
    WHEN 2 THEN 'A01'
    ELSE seat_code
END
WHERE employee_id IN (1, 2);

COMMIT;
```

Sau `COMMIT` thành công, hai vị trí đã được hoán đổi và uniqueness vẫn được đảm bảo. Trong quá trình thay đổi, các hàng có thể tạm thời vi phạm ràng buộc deferrable theo cơ chế kiểm tra được cho phép; **kết quả cuối transaction vẫn phải hợp lệ**. Nếu dữ liệu vẫn trùng tại thời điểm kiểm tra cuối, `COMMIT` không thể hoàn tất theo cách thông thường; ứng dụng phải xử lý lỗi, điều tra và rollback/sửa giao dịch theo chính sách.

Chỉ constraint được **khai báo `DEFERRABLE` từ đầu** mới có thể chuyển cách kiểm tra như vậy. Một constraint tạo bằng mặc định `NOT DEFERRABLE` không tự trở thành deferrable khi gọi `SET CONSTRAINTS`; muốn đổi đặc tính này thường cần thiết kế lại bằng cách drop/recreate constraint có kiểm soát.

### 5.3. Không phải cứ deferrable là nên dùng

- Cho phép trì hoãn uniqueness có thể giúp hoàn thành tác vụ batch/hoán đổi vị trí, nhưng làm tăng độ phức tạp khi xử lý lỗi tại `COMMIT`.
- Nonunique index hỗ trợ deferred constraint có đặc điểm khác unique index thông thường; cần đo workload thực tế.
- `DEFERRABLE INITIALLY DEFERRED` có thể khiến lỗi dữ liệu chỉ xuất hiện khi giao dịch kết thúc, gây khó chẩn đoán nếu ứng dụng giả định từng statement đều hợp lệ.
- Thời gian sống của transaction dài có thể tăng contention và tài nguyên; không dùng deferred constraint như cách che giấu dữ liệu trùng thường xuyên.

Khi không có lý do nghiệp vụ rõ ràng, **khóa không trì hoãn** vẫn là lựa chọn đơn giản cho phần lớn bảng ứng dụng.

## 6. PRIMARY KEY/UNIQUE và FOREIGN KEY quan hệ với nhau thế nào?

**Foreign key (FK)** biểu thị quan hệ tham chiếu giữa bảng con và một khóa được công bố ở bảng cha. Trong Oracle, khóa đích phải được bảo vệ bằng **primary key hoặc unique constraint** thích hợp, không đơn thuần là một unique index không có constraint.

```sql
CREATE TABLE lab_order_headers (
    order_id      NUMBER NOT NULL,
    order_code    VARCHAR2(40 CHAR) NOT NULL,
    CONSTRAINT pk_lab_order_headers PRIMARY KEY (order_id),
    CONSTRAINT uq_lab_order_headers_code UNIQUE (order_code)
);

CREATE TABLE lab_order_payments (
    payment_id NUMBER NOT NULL,
    order_code VARCHAR2(40 CHAR) NOT NULL,
    amount     NUMBER(12, 2) NOT NULL,
    CONSTRAINT pk_lab_order_payments PRIMARY KEY (payment_id),
    CONSTRAINT fk_lab_payment_order_code FOREIGN KEY (order_code)
        REFERENCES lab_order_headers (order_code)
);
```

Ví dụ này cho thấy FK **không bắt buộc tham chiếu primary key**. `LAB_ORDER_PAYMENTS.ORDER_CODE` có thể tham chiếu tới `LAB_ORDER_HEADERS.ORDER_CODE` vì bảng cha có **unique constraint** trên cột đó.

### 6.1. Foreign key bảo đảm gì?

- Khi `ORDER_CODE` ở bảng con có giá trị, Oracle cần kiểm tra xem giá trị đó được phép tham chiếu tới hàng ở bảng cha hay không.
- Nếu khóa được tham chiếu không tồn tại, thao tác insert/update ở bảng con có thể gặp **`ORA-02291`**.
- Nếu xóa hoặc cập nhật khóa cha khi còn hàng con tham chiếu và không có quy tắc xử lý phù hợp, có thể gặp **`ORA-02292`**.
- FK có thể cho phép `NULL` ở cột con nếu cột con không có `NOT NULL`; điều đó thể hiện quan hệ tùy chọn và cần được thiết kế rõ.

### 6.2. Oracle có tự tạo index trên cột foreign key không?

**Không.** Oracle thường tạo hoặc tái sử dụng index để thực thi **PK/UNIQUE** của bảng cha, nhưng **không mặc nhiên tạo index riêng cho các cột foreign key ở bảng con** chỉ vì bạn khai báo FK.

Với các hệ thống có nhiều truy vấn join hoặc thường cập nhật/xóa hàng cha, việc index cột FK có thể hỗ trợ truy vấn và giảm một số rủi ro contention liên quan kiểm tra quan hệ. Ví dụ:

```sql
CREATE INDEX ix_lab_payments_order_code
ON lab_order_payments (order_code);
```

Tuy nhiên **không phải FK nào cũng cần index**: index tăng chi phí ghi và lưu trữ; nếu bảng con rất nhỏ, workload ít join hoặc thiết kế đã có index phù hợp, index mới có thể dư thừa. Cần xem execution plan, tần suất truy vấn, thao tác trên cha và đặc điểm dữ liệu trước khi tạo.

### 6.3. Unique index riêng có đủ để làm khóa cha không?

Giả sử một bảng cha có:

```sql
CREATE UNIQUE INDEX ux_some_business_code
ON some_parent_table (business_code);
```

Câu lệnh này minh họa **index duy nhất** trên một bảng giả định. Để tạo foreign key tham chiếu `BUSINESS_CODE`, phải có **PK/UNIQUE constraint hợp lệ** ở bảng cha; unique index riêng lẻ không thay thế khai báo khóa cho quan hệ tham chiếu. Với một bảng thật, có thể thêm unique constraint trên cột khi đáp ứng điều kiện, cho phép Oracle tái sử dụng index phù hợp.

## 7. Thực thi bằng index không đồng nghĩa optimizer luôn dùng index

Index dùng để bảo vệ khóa dữ liệu và index dùng cho **execution plan** là hai góc nhìn khác nhau. Khi Oracle nhận một truy vấn, optimizer quyết định dùng full table scan, index unique scan, index range scan, index fast full scan hay đường truy cập khác dựa trên chi phí, thống kê và đặc điểm SQL.

### 7.1. Truy vấn bằng khóa chính

```sql
SELECT customer_id, username, email
FROM lab_customers
WHERE customer_id = :customer_id;
```

Với predicate bằng trên primary key một cột, index của khóa thường là phương tiện hiệu quả để tìm một hàng. Nhưng **không nên tuyên bố mọi lần Oracle buộc phải dùng index**: bảng nhỏ, statistics, optimizer settings và các yếu tố khác có thể khiến full scan rẻ hơn.

### 7.2. Truy vấn theo khóa ghép

```sql
SELECT product_id, quantity
FROM lab_order_items
WHERE order_id = :order_id
  AND line_no = :line_no;
```

Khóa ghép `(ORDER_ID, LINE_NO)` rất phù hợp với truy vấn có cả hai điều kiện bằng. Nếu truy vấn thường xuyên chỉ lọc `LINE_NO`, index có thứ tự `(ORDER_ID, LINE_NO)` không có vai trò giống index bắt đầu bằng `LINE_NO`. Thiết kế index phục vụ truy vấn cần xem thứ tự cột, tính chọn lọc và pattern truy cập, **không chỉ nhìn tên constraint**.

### 7.3. Index B-tree và giá trị NULL

Với **B-tree index Oracle thông thường**, một index key mà **mọi cột khóa đều `NULL`** thường không được lưu thành entry như key thông thường. Điều này giúp giải thích vì sao unique constraint một cột cho phép nhiều giá trị `NULL` và cách xử lý composite key có thành phần null. Tuy nhiên không nên suy luận từ đó rằng **mọi truy vấn `IS NULL` đều không thể dùng bất kỳ index nào**: index ghép còn cột không null, function-based index, bitmap index và thiết kế khác có thể tạo điều kiện truy cập riêng.

**Index uniqueness là thuộc tính của index key**, không có nghĩa Oracle sẽ coi hai hàng có cùng mọi thuộc tính nghiệp vụ là trùng nếu index chỉ chứa một phần thuộc tính đó. Quy tắc dữ liệu cần được khai báo chính xác qua PK/UNIQUE constraint và các constraint bổ sung.

## 8. Tra metadata: constraint nào đang dùng index nào?

Để kiểm tra schema Oracle, đừng chỉ liệt kê `USER_INDEXES`. Hãy xem cả **`USER_CONSTRAINTS`**, **`USER_CONS_COLUMNS`**, **`USER_INDEXES`** và **`USER_IND_COLUMNS`**.

### 8.1. Liệt kê PRIMARY KEY và UNIQUE constraint

```sql
SELECT constraint_name,
       table_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred,
       index_name
FROM user_constraints
WHERE constraint_type IN ('P', 'U')
ORDER BY table_name, constraint_type, constraint_name;
```

| Cột | Ý nghĩa cần đọc |
|---|---|
| `CONSTRAINT_TYPE = 'P'` | Primary key constraint |
| `CONSTRAINT_TYPE = 'U'` | Unique constraint |
| `STATUS` | Constraint đang enabled hay disabled |
| `VALIDATED` | Oracle đã xác minh toàn bộ dữ liệu hiện có đáp ứng constraint hay chưa theo trạng thái ràng buộc |
| `DEFERRABLE` | Constraint có được phép trì hoãn kiểm tra không |
| `DEFERRED` | Chế độ kiểm tra ban đầu được khai báo |
| `INDEX_NAME` | Index có liên quan tới việc thực thi PK/UNIQUE, khi thông tin có áp dụng |

Lưu ý trạng thái constraint có thể là **`ENABLED NOVALIDATE`** khi Oracle kiểm soát thay đổi mới nhưng chưa xác minh tất cả dữ liệu cũ theo chính sách tương ứng. Không coi cứ `ENABLED` là đã chắc chắn lịch sử dữ liệu không có vi phạm; cần xem cả `VALIDATED` và ngữ cảnh migration.

### 8.2. Liệt kê cột thuộc từng constraint

```sql
SELECT c.table_name,
       c.constraint_name,
       c.constraint_type,
       cc.column_name,
       cc.position
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
WHERE c.constraint_type IN ('P', 'U')
ORDER BY c.table_name, c.constraint_name, cc.position;
```

`POSITION` cho biết thứ tự cột trong constraint. Với khóa ghép, thứ tự này giúp hiểu định nghĩa và tiện đối chiếu với thứ tự index, nhưng không nên suy luận rằng index được Oracle chọn nhất thiết có cùng tên hoặc trình tự khai báo trong mọi tình huống tái sử dụng.

### 8.3. Đọc index hỗ trợ và loại index

```sql
SELECT c.table_name,
       c.constraint_name,
       c.constraint_type,
       c.deferrable,
       c.index_name,
       i.uniqueness,
       i.index_type,
       i.status
FROM user_constraints c
LEFT JOIN user_indexes i
  ON i.index_name = c.index_name
WHERE c.constraint_type IN ('P', 'U')
ORDER BY c.table_name, c.constraint_name;
```

Nếu thấy `CONSTRAINT_TYPE = 'U'` và `UNIQUENESS = 'NONUNIQUE'`, đây có thể là một cấu hình đúng, nhất là với deferrable constraint hoặc index không unique được tái sử dụng để bảo vệ constraint. Không sửa chỉ vì hai từ khác nhau.

### 8.4. Xem thứ tự cột trong index thực tế

```sql
SELECT index_name,
       table_name,
       column_name,
       column_position,
       descend
FROM user_ind_columns
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDER_ITEMS')
ORDER BY index_name, column_position;
```

Với index trên biểu thức, cần xem thông tin expression tương ứng ở `USER_IND_EXPRESSIONS`; chỉ nhìn cột sinh bởi expression có thể gây hiểu nhầm. Đối với object thuộc schema khác, dùng các view `ALL_*`/`DBA_*` tương ứng khi được cấp quyền, kèm điều kiện `OWNER`/`INDEX_OWNER` phù hợp. Ở kiến trúc CDB/PDB, xác nhận **đúng PDB** trước khi so sánh metadata cùng tên object.

### 8.5. Sơ đồ metadata phục vụ điều tra

```text
USER_CONSTRAINTS
  - TABLE_NAME
  - CONSTRAINT_NAME
  - CONSTRAINT_TYPE = P / U
  - INDEX_NAME (nếu áp dụng)
            |
            +---- USER_CONS_COLUMNS
            |        các cột thuộc khóa
            |
            +---- USER_INDEXES
                     - UNIQUENESS
                     - INDEX_TYPE
                     - STATUS
                       |
                       +---- USER_IND_COLUMNS
                                các cột của index
```

Quan hệ giữa constraint và index cần được **quan sát bằng metadata**, không xác định bằng cách so chuỗi tên hoặc giả định một index phải tồn tại cho mỗi cột riêng lẻ.

## 9. Những thay đổi schema liên quan PK/UNIQUE trong migration

Trên một bảng đã có dữ liệu, việc thêm primary key hoặc unique constraint có thể thất bại nếu dữ liệu hiện tại vi phạm điều kiện. Điều đó cần được phát hiện **trước khi** áp migration trên production.

### 9.1. Tìm dữ liệu trùng trước khi thêm UNIQUE

Giả sử bảng `CUSTOMERS_LEGACY` có cột `EXTERNAL_CODE` mà hệ thống muốn đặt unique:

```sql
SELECT external_code, COUNT(*) AS duplicate_count
FROM customers_legacy
WHERE external_code IS NOT NULL
GROUP BY external_code
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
```

Truy vấn trên dành cho **unique một cột nullable**, dùng để xem những giá trị đã xuất hiện trên một hàng. Với unique ghép, phải **nhóm theo toàn bộ cột tham gia khóa** và diễn giải các tổ hợp `NULL` theo ngữ nghĩa Oracle thay vì tự bỏ qua mọi hàng có null.

Đối với primary key, kiểm tra cả **trùng khóa** và **`NULL`**:

```sql
SELECT COUNT(*) AS rows_with_missing_id
FROM customers_legacy
WHERE customer_id IS NULL;

SELECT customer_id, COUNT(*) AS duplicate_count
FROM customers_legacy
WHERE customer_id IS NOT NULL
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

Đây là những truy vấn minh họa để khảo sát dữ liệu legacy, chỉ chạy khi bảng tồn tại và bạn có quyền truy cập. Với bảng lớn, nhóm DBA/developer cần tính chi phí quét, thống kê và cửa sổ chạy thích hợp.

### 9.2. Tạo constraint trên bảng hiện hữu

```sql
-- Chỉ sau khi xác nhận CUSTOMERS_LEGACY đã có cột và dữ liệu hợp lệ.
ALTER TABLE customers_legacy
ADD CONSTRAINT pk_customers_legacy PRIMARY KEY (customer_id);

ALTER TABLE customers_legacy
ADD CONSTRAINT uq_customers_legacy_code UNIQUE (external_code);
```

Nếu dữ liệu duplicate hoặc thiếu ID, Oracle có thể từ chối tạo/validate constraint. Không dùng `DISABLE` hay `NOVALIDATE` vô thời hạn chỉ để thông qua một bản triển khai mà không hiểu dữ liệu hiện hữu. **Việc thay đổi schema trên Oracle là DDL, thường có implicit commit**; không thể coi toàn bộ migration được `ROLLBACK` như một transaction DML thuần túy.

### 9.3. ENABLE, DISABLE và VALIDATE không phải công tắc hiệu năng vô hại

Khi một constraint bị **disabled**, Oracle có thể không còn thực thi quy tắc tại thời điểm DML theo cách bạn kỳ vọng. Tùy loại index và trạng thái, việc disable/drop constraint có thể dẫn tới thay đổi hoặc mất index hỗ trợ; khi enable trở lại, Oracle có thể cần quét dữ liệu, xác nhận hợp lệ hoặc tái tạo cấu trúc hỗ trợ.

Trong những hệ thống nhập dữ liệu hàng loạt, các trạng thái như `ENABLE VALIDATE`, `ENABLE NOVALIDATE`, `DISABLE` và `DEFERRABLE` có tác dụng rất khác nhau. DBA/đội migration phải xác định:

- Dữ liệu cũ đã được kiểm tra chưa và ai chịu trách nhiệm xử lý violation?
- DML mới có được bảo vệ bởi constraint ở trạng thái dự kiến không?
- Index supporting được giữ, dùng lại hay cần tạo lại?
- Foreign key phụ thuộc vào khóa cha có ảnh hưởng khi disable/drop PK/UNIQUE không?
- Thời gian kiểm tra constraint có phù hợp dung lượng bảng và lịch triển khai không?

Không tự vô hiệu hóa primary key/unique trên production để “load nhanh” khi chưa đánh giá dữ liệu sau import và rủi ro toàn vẹn tham chiếu.

### 9.4. Xóa constraint và xóa index là hai thao tác khác nhau

`DROP CONSTRAINT` thay đổi quy tắc toàn vẹn. `DROP INDEX` thay đổi cấu trúc truy cập và có thể ảnh hưởng tới constraint đang phụ thuộc vào index. Oracle có những quy định khi index được dùng để thực thi PK/UNIQUE; một index có thể không được drop trực tiếp trong khi constraint liên quan đang dùng nó.

Vì vậy, không nên chạy `DROP INDEX` chỉ dựa trên việc “đã có một index khác trông giống nó”. Trước khi thay đổi, xem `USER_CONSTRAINTS.INDEX_NAME`, thứ tự cột, tính deferrable, trạng thái index, plan truy vấn và dependency. Nếu thực sự cần thay index hỗ trợ constraint, thực hiện qua migration đã được DBA thẩm định và thử nghiệm.

## 10. UNIQUE theo nghiệp vụ: chữ hoa/chữ thường, khoảng trắng và chuẩn hóa

Một unique constraint trên `USERNAME` không tự trả lời mọi câu hỏi như:

- `Lan` và `lan` có được coi là một username không?
- `abc@example.test` và `ABC@example.test` có được coi là cùng email theo hợp đồng ứng dụng không?
- Dấu cách đầu/cuối, ký tự Unicode, accent hoặc dạng chuẩn hóa Unicode có được xử lý trước khi so sánh không?
- Tính duy nhất là toàn hệ thống hay chỉ trong một tenant?

Trong cấu hình so sánh nhị phân thông dụng, hai chuỗi khác chữ hoa/thường có thể được coi là khác. Tuy nhiên Oracle còn hỗ trợ collation và các thiết lập so sánh khác theo phiên bản/cấu hình, vì vậy **không khẳng định mọi Oracle luôn so sánh mọi chuỗi theo binary**. Quy tắc uniqueness cần đồng nhất từ API, truy vấn, constraint/index và xử lý dữ liệu.

### 10.1. Unique index trên biểu thức để kiểm soát chữ hoa/thường

Nếu ứng dụng muốn username không phân biệt chữ hoa/thường và đã thẩm định quy tắc `LOWER`, có thể dùng **function-based unique index**:

```sql
-- Ví dụ minh họa trên một bảng được phép dùng trong DEV/TEST.
CREATE TABLE lab_usernames (
    id NUMBER PRIMARY KEY,
    username VARCHAR2(80 CHAR) NOT NULL
);

CREATE UNIQUE INDEX ux_lab_usernames_lower
ON lab_usernames (LOWER(username));
```

Index này kiểm tra uniqueness của **giá trị biểu thức `LOWER(USERNAME)`**. Nó có thể làm `Lan` và `lan` xung đột. Tuy nhiên **đây là unique index trên biểu thức**, không phải một `UNIQUE (USERNAME)` constraint độc lập, và không thể tùy tiện dùng biểu thức `LOWER(USERNAME)` như khóa đích của foreign key thông thường.

`LOWER` cũng không thay thế mọi yêu cầu chuẩn hóa Unicode hoặc chính sách email/username phức tạp. Đối với hệ thống nhiều ngôn ngữ, cần kiểm tra collation, quy tắc normalization, khoảng trắng và phiên bản Oracle. Một lựa chọn khác là lưu **khóa đã chuẩn hóa** vào cột/virtual column phù hợp, sau đó thiết kế constraint rõ nghĩa trên cột được phép theo chính sách dữ liệu.

### 10.2. UNIQUE theo tenant

Nếu mã đối tượng chỉ cần duy nhất **trong từng tenant**, đừng đặt `UNIQUE (BUSINESS_CODE)` toàn bảng khi nghiệp vụ cho phép nhiều tenant dùng cùng mã. Có thể khai báo:

```sql
CREATE TABLE lab_tenant_products (
    tenant_id NUMBER NOT NULL,
    product_code VARCHAR2(40 CHAR) NOT NULL,
    product_name VARCHAR2(100 CHAR) NOT NULL,
    CONSTRAINT pk_lab_tenant_products PRIMARY KEY (tenant_id, product_code)
);
```

Ở đây khóa chính ghép đã bảo vệ tính duy nhất theo tenant và yêu cầu cả hai thành phần không null. Nếu bảng có thêm `PRODUCT_ID` làm primary key, cặp `(TENANT_ID, PRODUCT_CODE)` nên được bảo vệ bằng **unique constraint** riêng, thay vì một primary key thứ hai.

## 11. Partitioning và uniqueness: phạm vi index có thể bị ràng buộc

Với bảng partitioned, index hỗ trợ PK/UNIQUE có thể là **local** hoặc **global** tùy thiết kế và các quy tắc Oracle. Một **local unique index** trên bảng partitioned thường đòi hỏi **tập cột khóa index có chứa các cột partition key** của bảng để có thể thực thi uniqueness đúng trên toàn bộ các partition. Nếu khóa unique không bao gồm partition key, thiết kế có thể cần **global unique index** hoặc xem lại partition strategy.

Ví dụ nghiệp vụ:

```text
Bảng ORDERS được partition theo ORDER_DATE

Nhu cầu A: UNIQUE (ORDER_DATE, ORDER_CODE)
  -> Bao gồm partition key; có thể cân nhắc local unique index

Nhu cầu B: UNIQUE (ORDER_CODE) trên toàn bộ lịch sử
  -> Không bao gồm ORDER_DATE; thường phải xem global uniqueness/index
     hoặc đổi chiến lược partition/khóa
```

Không nên tự tạo local unique index chỉ vì “partition độc lập giúp nhanh hơn”; **đảm bảo không trùng trên toàn bộ bảng** là yêu cầu logic, không chỉ trong từng partition. Các điều kiện cụ thể phụ thuộc kiểu partitioning và phiên bản Oracle, nên phải đối chiếu thiết kế/DDL thật trước khi triển khai.

## 12. Concurrency: vì sao SELECT trước INSERT không thay thế UNIQUE?

Một lỗi thường thấy trong ứng dụng là kiểm tra mã đã tồn tại hay chưa bằng `SELECT`, rồi mới insert:

```text
Session A: SELECT COUNT(*) WHERE username = 'lan' -> 0
Session B: SELECT COUNT(*) WHERE username = 'lan' -> 0
Session A: INSERT username='lan' -> thành công
Session B: INSERT username='lan' -> ?
```

Nếu không có unique constraint/index thích hợp, cả hai session có thể cùng insert dữ liệu trùng trong các tình huống race condition. Với **unique constraint được thực thi**, Oracle sẽ áp quy tắc toàn vẹn khi DML/transaction diễn ra; session thứ hai có thể phải chờ giao dịch cạnh tranh và cuối cùng nhận `ORA-00001` khi xung đột không thể được chấp nhận.

Điều đó dẫn đến hai nguyên tắc:

1. **Database constraint là tuyến bảo vệ tính đúng đắn cuối cùng** cho dữ liệu cần unique, kể cả khi ứng dụng đã pre-check để trả thông báo thân thiện.
2. **Ứng dụng vẫn phải xử lý lỗi xung đột** một cách rõ ràng: trả `409 Conflict` hoặc thông điệp nghiệp vụ phù hợp, quyết định retry khi an toàn và không tiết lộ thông tin nhạy cảm.

Không coi một kết quả `SELECT NOT EXISTS` là bằng chứng được phép insert nếu có nhiều người dùng đồng thời. Với deferrable constraint, thời điểm báo lỗi có thể dịch tới `COMMIT`, vì vậy logic xử lý giao dịch phải được thiết kế tương ứng.

## 13. Các mã lỗi Oracle thường gặp

| Mã lỗi | Bối cảnh điển hình | Bước điều tra |
|---|---|---|
| `ORA-00001` | Vi phạm unique constraint hoặc unique index | Xác định constraint/index, các cột tham gia, dữ liệu xung đột, luồng ghi đồng thời |
| `ORA-01400` | Cố insert `NULL` vào cột `NOT NULL` | Kiểm tra dữ liệu đầu vào, giá trị mặc định/identity, primary key và các cột bắt buộc |
| `ORA-02260` | Cố tạo thêm primary key cho bảng đã có một primary key | Xem `USER_CONSTRAINTS` và thiết kế lại candidate key bằng UNIQUE |
| `ORA-02291` | Foreign key tham chiếu khóa cha chưa tồn tại | Kiểm tra khóa được tham chiếu, thứ tự insert và transaction |
| `ORA-02292` | Xóa/cập nhật khóa cha khi còn hàng con phụ thuộc | Kiểm tra FK, dữ liệu con và quy tắc xóa nghiệp vụ |
| `ORA-02299` | Không thể validate constraint vì có khóa trùng | Khảo sát dữ liệu cũ, xử lý duplicate trước khi enable/validate |
| `ORA-01452` | Không tạo được unique index vì các khóa đã trùng | Kiểm tra dữ liệu trùng hoặc index expression tương ứng |
| `ORA-02449` | Cố drop một khóa chính/unique còn được FK tham chiếu | Kiểm tra dependency và kế hoạch thay đổi quan hệ |

Thông điệp `ORA-00001` thường chỉ ra tên constraint hoặc index liên quan; trên những phiên bản mới, thông báo có thể cung cấp thêm tên cột. **Không chỉ dựa vào câu chữ của lỗi**, hãy đối chiếu Oracle metadata vì tên trong thông báo có thể là index hoặc constraint, và index name không bắt buộc trùng constraint name.

### 13.1. Khi gặp `ORA-00001` ở API tạo tài khoản

Quy trình chẩn đoán an toàn:

1. Ghi nhận phiên bản ứng dụng, môi trường/PDB, thời điểm và mã ORA; không log password hoặc dữ liệu cá nhân chưa che.
2. Xác định constraint/index được nêu và bảng/cột mà nó bảo vệ.
3. Kiểm tra luồng ghi: giá trị nào được chuẩn hóa, request có thể bị gửi lặp, có giao dịch đồng thời hoặc race condition không.
4. Phân biệt xung đột **username** với xung đột **primary key** do cơ chế sinh ID; hai lỗi đều có thể là `ORA-00001` nhưng hướng xử lý khác nhau.
5. Trả lỗi nghiệp vụ có kiểm soát; chỉ retry khi thao tác idempotent hoặc có cơ chế đảm bảo không tạo dữ liệu sai.

Không tự xóa constraint để “cho insert chạy được”, vì điều đó phá quy tắc dữ liệu cho toàn hệ thống.

## 14. Thực hành Oracle: tạo constraint, gây xung đột và quan sát index

Bài tập dành cho **Oracle DEV/TEST** và một schema lab được cấp quyền `CREATE TABLE`/`CREATE INDEX` cùng quota cần thiết. Không chạy DDL trong môi trường production hoặc schema chứa dữ liệu thật. Các tên `LAB_*` là ví dụ, cần bảo đảm chưa tồn tại trong schema được phép.

### Bước 1 – Xác minh đích kết nối

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
```

Đối chiếu PDB/service và tài khoản với môi trường lab được cấp. Nếu kết quả không đúng, **dừng trước khi chạy DDL**.

### Bước 2 – Tạo bảng có PRIMARY KEY và UNIQUE

```sql
CREATE TABLE lab_pk_uk_demo (
    id NUMBER NOT NULL,
    username VARCHAR2(40 CHAR) NOT NULL,
    email VARCHAR2(100 CHAR),
    tenant_id NUMBER NOT NULL,
    external_code VARCHAR2(30 CHAR) NOT NULL,
    CONSTRAINT pk_lab_pk_uk_demo PRIMARY KEY (id),
    CONSTRAINT uq_lab_pk_uk_username UNIQUE (username),
    CONSTRAINT uq_lab_pk_uk_email UNIQUE (email),
    CONSTRAINT uq_lab_pk_uk_ext UNIQUE (tenant_id, external_code)
);
```

### Bước 3 – Insert dữ liệu hợp lệ

```sql
INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (1, 'lan', 'lan@example.test', 10, 'A01');

INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (2, 'minh', NULL, 10, 'A02');

INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (3, 'nhu', NULL, 20, 'A01');

COMMIT;
```

Ba hàng hợp lệ: `ID` khác nhau, `USERNAME` khác nhau, hai `EMAIL` là `NULL` được phép, còn cặp `(TENANT_ID, EXTERNAL_CODE)` không trùng. `EXTERNAL_CODE = 'A01'` xuất hiện ở tenant 10 và 20 nhưng tổ hợp ghép vẫn khác nhau.

### Bước 4 – Quan sát metadata PK/UNIQUE

```sql
SELECT constraint_name, constraint_type,
       status, validated, deferrable, index_name
FROM user_constraints
WHERE table_name = 'LAB_PK_UK_DEMO'
  AND constraint_type IN ('P', 'U')
ORDER BY constraint_type, constraint_name;

SELECT index_name, uniqueness, index_type, status
FROM user_indexes
WHERE table_name = 'LAB_PK_UK_DEMO'
ORDER BY index_name;

SELECT index_name, column_name, column_position
FROM user_ind_columns
WHERE table_name = 'LAB_PK_UK_DEMO'
ORDER BY index_name, column_position;
```

Hãy ghi nhận: bảng có **một** primary key và **ba** unique constraints; các index hỗ trợ có tên, loại và thứ tự cột như thế nào. Không tự kết luận dựa trên số lượng index nếu trong schema lab có thêm index được tạo bằng tay hoặc nếu Oracle đã tái sử dụng index phù hợp.

### Bước 5 – Thử từng tình huống vi phạm riêng lẻ

Các lệnh sau được **cố tình thiết kế để thất bại**. Hãy chạy **từng câu riêng**, ghi mã lỗi, không đưa cả khối vào migration tự động:

```sql
-- A: Trùng primary key ID = 1.
INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (1, 'new_user', 'new@example.test', 30, 'B01');

-- B: ID mới nhưng trùng username 'lan'.
INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (4, 'lan', 'other@example.test', 30, 'B02');

-- C: Trùng cặp UNIQUE (tenant_id, external_code) = (10, 'A01').
INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (5, 'another', 'another@example.test', 10, 'A01');

-- D: Primary key ID bị NULL.
INSERT INTO lab_pk_uk_demo
    (id, username, email, tenant_id, external_code)
VALUES (NULL, 'null_id', NULL, 50, 'C01');
```

Câu A/B/C thường báo `ORA-00001` nhưng **constraint bị vi phạm khác nhau**; câu D thường liên quan `ORA-01400` do cột `ID` không được null. Kết quả giúp hiểu vai trò của constraint name trong việc gỡ lỗi.

### Bước 6 – Quan sát UNIQUE nullable

```sql
SELECT id, username, email
FROM lab_pk_uk_demo
WHERE email IS NULL
ORDER BY id;
```

Hai hàng `MINH` và `NHU` có thể cùng `EMAIL = NULL`. Điều này không làm constraint unique trên `EMAIL` thất bại. Muốn bắt buộc email, dùng `NOT NULL` khi nghiệp vụ cho phép; không cố dùng `UNIQUE` một mình để cấm null.

### Bước 7 – Xem quan hệ với index và dọn dữ liệu lab

Quan sát `USER_CONSTRAINTS.INDEX_NAME` và đối chiếu `USER_INDEXES.UNIQUENESS`. Nếu có thể, tạo bảng riêng với `DEFERRABLE UNIQUE` như phần 5 để thấy index **`NONUNIQUE`** vẫn hỗ trợ uniqueness của constraint.

Sau khi hoàn thành và xác nhận chỉ có dữ liệu lab do mình sở hữu, có thể dọn theo quy trình:

```sql
DROP TABLE lab_pk_uk_demo PURGE;
```

Lệnh `DROP TABLE ... PURGE` xóa object và không đưa vào recycle bin; là DDL có tác động phá hủy dữ liệu. **Không áp dụng cho bảng production hoặc dữ liệu thực tế**, kể cả khi tên gần giống `LAB_*`.

## 15. Các bài toán thiết kế thường gặp

### 15.1. Dùng natural key hay surrogate key làm PRIMARY KEY?

| Chọn khóa | Ưu điểm | Rủi ro/cân nhắc |
|---|---|---|
| **Surrogate key** (`CUSTOMER_ID` số, identity/sequence hoặc UUID) | Ổn định hơn trước thay đổi username/email; gọn nếu dùng số; dễ tham chiếu nhất quán | Vẫn phải thêm `UNIQUE` cho khóa nghiệp vụ như username hoặc mã đối tác để không chấp nhận dữ liệu trùng |
| **Natural key** (mã nghiệp vụ có ý nghĩa) | Có thể tận dụng mã đã tồn tại; dễ nhìn ở SQL và báo cáo | Mã có thể đổi quy tắc, độ dài hoặc nguồn cấp; ảnh hưởng nhiều foreign key nếu thay đổi |
| **Composite key** (`TENANT_ID`, `PRODUCT_CODE`) | Diễn đạt uniqueness theo ngữ cảnh tự nhiên | Có thể làm FK/index lớn hơn, phức tạp query và thay đổi khi thuộc tính khóa bị đổi |

Không có đáp án luôn đúng. Điều quan trọng là khóa chính **ổn định, duy nhất và không null**; những khóa nghiệp vụ khác cũng cần được bảo vệ bằng unique constraint phù hợp nếu chúng phải duy nhất.

### 15.2. Có cần unique constraint nếu đã kiểm tra ở backend?

**Có, nếu tính duy nhất là bất biến dữ liệu bắt buộc.** Backend pre-check chỉ giúp UX; nó không đủ chống hai transaction đồng thời, script import, batch job hoặc một dịch vụ khác ghi thẳng vào database. Constraint ở database là nơi bảo vệ quy tắc cho mọi nguồn ghi.

### 15.3. Có nên đặt UNIQUE cho mỗi cột thường được lọc?

**Không.** `UNIQUE` là quy tắc toàn vẹn chứ không phải “tùy chọn index nhanh”. Ví dụ `STATUS = 'ACTIVE'` xuất hiện ở rất nhiều khách hàng; cột `STATUS` không phải unique. Nếu truy vấn lọc status, hãy đánh giá nhu cầu **nonunique index** và selectivity, không đặt unique chỉ để có index.

### 15.4. Có nên index từng cột của primary key ghép?

Không tự động. Index hỗ trợ `(TENANT_ID, PRODUCT_CODE)` có thứ tự và đặc điểm riêng; nếu truy vấn thường chỉ lọc `PRODUCT_CODE`, cần xem plan và workload để quyết định index khác. Mỗi index bổ sung đều có chi phí ghi, redo, storage và maintenance.

### 15.5. Khi nào unique index độc lập là lựa chọn phù hợp?

Unique **function-based index** có thể phù hợp để bắt unique theo biểu thức chuẩn hóa, ví dụ `LOWER(USERNAME)`. Một số quy tắc duy nhất có điều kiện có thể được mô hình hóa bằng unique function-based index với các biểu thức trả `NULL` ngoài tập bản ghi cần bảo vệ. Tuy nhiên đây là **cấu trúc index có quy tắc duy nhất của index key**, không phải một UNIQUE constraint trực tiếp trên cột có khả năng tham chiếu FK như bình thường; ứng dụng và migration phải hiểu rõ hệ quả metadata và dependency.

## 16. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “PRIMARY KEY là unique index.” | Primary key là constraint `UNIQUE + NOT NULL` theo nghĩa logic; Oracle dùng index để hỗ trợ thực thi, nhưng hai đối tượng khác nhau. |
| “Một bảng có thể có nhiều PRIMARY KEY.” | Mỗi bảng có tối đa một PK, có thể gồm nhiều cột; nhiều candidate key khác dùng UNIQUE. |
| “UNIQUE tự cấm NULL.” | Unique một cột cho phép nhiều NULL; PK cấm null. UNIQUE ghép với NULL có ngữ nghĩa Oracle riêng. |
| “Hàng có một NULL thì unique ghép luôn cho phép trùng.” | Với composite unique key Oracle, các khóa có phần không null giống nhau vẫn có thể bị coi là trùng. |
| “Chỉ UNIQUE index là đủ để foreign key tham chiếu.” | Foreign key cần PK/UNIQUE constraint hợp lệ của bảng cha. |
| “Bảng có PK nên chắc không cần xem index.” | Cần hiểu index hỗ trợ, thứ tự cột, deferrable và nhu cầu truy vấn riêng. |
| “UNIQUE constraint lúc nào cũng dùng UNIQUE index.” | Constraint deferrable hoặc index được tái sử dụng có thể dùng NONUNIQUE index. |
| “Tạo UNIQUE constraint xong phải tạo thêm UNIQUE index giống hệt.” | Oracle thường tự tạo/tái sử dụng index phù hợp; tạo bản sao có thể dư thừa. |
| “Foreign key Oracle tự tạo index cho cột con.” | Oracle không mặc nhiên tạo index cho FK ở bảng con. |
| “`SELECT NOT EXISTS` trước `INSERT` loại trừ hoàn toàn duplicate.” | Race condition vẫn có thể xảy ra; database constraint mới bảo đảm dưới cạnh tranh. |
| “Index phục vụ PK chắc chắn luôn được optimizer dùng.” | Optimizer chọn plan theo chi phí, stats và query shape. |
| “Xóa index chẳng ảnh hưởng constraint.” | Index có thể được PK/UNIQUE sử dụng; cần tra metadata và dependency. |
| “Đổi constraint bằng DDL có thể luôn rollback như DML.” | Nhiều Oracle DDL implicit commit; phải có migration và kế hoạch xử lý lỗi. |
| “`ORA-00001` luôn do ID bị trùng.” | Có thể do mọi UNIQUE constraint hoặc unique index, kể cả business key/function-based index. |

## 17. Câu hỏi tự luyện

**Câu 1.** Bảng `CUSTOMERS` có `CUSTOMER_ID` primary key và `USERNAME` unique. Có thể thêm hai hàng có cùng `CUSTOMER_ID` nhưng username khác không?

**Đáp án:** Không. Primary key cấm trùng `CUSTOMER_ID` bất kể giá trị username.

**Câu 2.** Bảng `USERS` có `EMAIL VARCHAR2(200)` và `UNIQUE(EMAIL)` nhưng không `NOT NULL`. Hai user cùng `EMAIL = NULL` có được không?

**Đáp án:** Có, với unique constraint một cột trong Oracle. Nếu email bắt buộc, cần thêm `NOT NULL`.

**Câu 3.** Một khóa chính gồm `(ORDER_ID, LINE_NO)`. Giá trị `LINE_NO = 1` có được lặp ở đơn hàng khác không?

**Đáp án:** Có, miễn cặp `(ORDER_ID, LINE_NO)` là duy nhất và mọi thành phần không null.

**Câu 4.** Dictionary cho thấy constraint `UQ_CODE` có `CONSTRAINT_TYPE = U`, nhưng index hỗ trợ có `UNIQUENESS = NONUNIQUE`. Có chắc cấu hình bị sai?

**Đáp án:** Không. Constraint có thể là `DEFERRABLE` hoặc dùng index không unique phù hợp để thực thi. Cần xem `USER_CONSTRAINTS.DEFERRABLE`, trạng thái và index liên kết.

**Câu 5.** Nếu dùng một unique index đơn lẻ trên `PARENT(CODE)` mà không khai báo constraint tương ứng, có thể coi nó là khóa được FK tham chiếu không?

**Đáp án:** Không. FK cần một primary key hoặc unique constraint được khai báo hợp lệ ở bảng cha.

**Câu 6.** Cột `ORDERS.CUSTOMER_ID` có FK đến `CUSTOMERS.CUSTOMER_ID`. Oracle có tạo index trên `ORDERS.CUSTOMER_ID` không?

**Đáp án:** Không mặc định. Cần cân nhắc index riêng cho FK theo workload truy vấn và thao tác DML.

**Câu 7.** Hai request cùng kiểm tra `USERNAME = 'lan'` chưa có, rồi cùng insert. Tại sao backend pre-check chưa đủ?

**Đáp án:** Vì hai session có thể đồng thời quan sát trạng thái chưa có và cùng ghi. Unique constraint ở database bảo vệ tính đúng đắn, còn ứng dụng xử lý lỗi xung đột phát sinh.

**Câu 8.** Một bảng partition theo `ORDER_DATE`, nhưng nghiệp vụ yêu cầu `ORDER_CODE` duy nhất trên mọi ngày. Có thể tùy ý dùng local unique index chỉ trên `ORDER_CODE`?

**Đáp án:** Thường không. Local unique index phải đáp ứng điều kiện về partition key; có thể phải sử dụng global unique index hoặc thiết kế khác. Cần thẩm định theo partition strategy thực tế.

**Câu 9.** `UNIQUE(USERNAME)` có thể tự động coi `'Lan'` và `'lan'` trùng hay không?

**Đáp án:** Phụ thuộc collation/quy tắc so sánh của hệ thống. Nếu nghiệp vụ yêu cầu không phân biệt chữ hoa/thường, cần thiết kế và kiểm thử cơ chế chuẩn hóa/unique phù hợp; không dựa vào giả định mặc định bất biến giữa mọi cấu hình Oracle.

**Câu 10.** Có nên tạo hai index cùng bộ cột và thứ tự khi một index đã được PK constraint sử dụng?

**Đáp án:** Thông thường không, trừ khi có lý do kỹ thuật đo được và được thẩm định. Index dư thừa tăng chi phí ghi, storage và bảo trì.

## Kết luận

Trong Oracle, **`PRIMARY KEY`** chọn một khóa định danh cho mỗi bảng và buộc khóa **duy nhất, không `NULL`**; **`UNIQUE`** bảo vệ những khóa ứng viên hoặc quy tắc duy nhất nghiệp vụ, có thể là một cột hoặc nhiều cột và có cách xử lý `NULL` riêng. **Index** là cấu trúc hỗ trợ truy cập và thực thi uniqueness, nhưng **không phải bản thân constraint**. Oracle thường tạo hoặc tái sử dụng index phù hợp; đặc biệt, một primary key hoặc unique constraint **`DEFERRABLE`** có thể được thực thi qua **nonunique index**.

Khi thiết kế schema, hãy khai báo ràng buộc đúng nghĩa, chọn khóa ổn định, kết hợp `NOT NULL` khi cần, phân biệt khóa ghép với index đa cột, hiểu quan hệ với foreign key và chống race condition bằng constraint ở database. Khi vận hành/migration, đọc `USER_CONSTRAINTS`, `USER_CONS_COLUMNS`, `USER_INDEXES` và `USER_IND_COLUMNS` để xác minh đúng đối tượng, tránh tạo index trùng hoặc xóa index đang phục vụ khóa. Một thiết kế tốt vừa **giữ dữ liệu đúng dưới cạnh tranh**, vừa duy trì hiệu năng truy vấn và khả năng thay đổi schema an toàn.
