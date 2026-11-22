# CREATE TABLE AS SELECT và những thuộc tính cần kiểm tra sau khi sao chép trong Oracle

Khi cần tạo bảng phục vụ thử nghiệm, lưu một ảnh chụp dữ liệu trước khi chuyển đổi, hoặc xây dựng bảng tổng hợp từ kết quả truy vấn, Oracle Database hỗ trợ cú pháp **CREATE TABLE AS SELECT (CTAS)**. Ví dụ:

```sql
CREATE TABLE orders_snapshot AS
SELECT order_id, customer_id, total_amount
FROM orders
WHERE order_status = 'PAID';
```

Một câu lệnh vừa **tạo bảng mới** vừa **đưa dữ liệu của kết quả SELECT vào bảng đó**. Đây là cách rất tiện lợi, nhưng đi kèm một ngộ nhận nguy hiểm: *“Bảng mới chắc chắn giống hệt bảng gốc, chỉ khác tên.”* Thực tế, CTAS chủ yếu lấy **danh sách cột/kiểu dữ liệu của kết quả truy vấn và các hàng được chọn**; nhiều thuộc tính schema và hành vi vận hành của bảng nguồn **không tự được sao chép**.

Một bảng CTAS có thể trông giống bảng gốc khi bạn chạy `SELECT *`, trong khi lại thiếu **PRIMARY KEY**, **UNIQUE**, **FOREIGN KEY**, **CHECK**, **DEFAULT**, **IDENTITY**, **index**, **trigger**, **comment**, **grant** hoặc những tùy chọn lưu trữ và bảo mật quan trọng. Một số **NOT NULL** có thể được Oracle kế thừa trong những điều kiện nhất định, nhưng bạn không được giả định mọi ràng buộc đều giống nhau.

Bài học này hướng dẫn CTAS theo đúng ngữ cảnh **bảng và ràng buộc** của Oracle Database: cú pháp, ví dụ có thể tự chạy, những gì thường được giữ hoặc không giữ, cách đọc data dictionary để đối chiếu, quy trình bổ sung thuộc tính còn thiếu và những rủi ro khi sử dụng CTAS cho dữ liệu quan trọng.

Sau bài học, bạn có thể:

- Dùng CTAS để tạo bảng từ toàn bộ, một phần, hoặc **không hàng nào** của kết quả SELECT.
- Phân biệt **sao chép dữ liệu**, **sao chép định nghĩa cột** và **nhân bản toàn bộ cấu trúc/hành vi của bảng**.
- Biết cách kiểm tra lại constraints, indexes, defaults, identity, triggers, comments, privileges, LOB/partitioning và storage.
- Dùng `USER_TABLES`, `USER_TAB_COLUMNS`, `USER_CONSTRAINTS`, `USER_INDEXES` và các dictionary views khác để xác nhận kết quả thực tế.
- Tránh các bẫy liên quan implicit commit, dữ liệu nhất quán tại thời điểm chụp, quyền truy cập và hiệu năng.
- Lập một **checklist kỹ thuật** trước khi dùng bảng CTAS trong pipeline hay ứng dụng thực tế.

> Các ví dụ tạo bảng dưới tiền tố `LAB_CTAS_` để dễ nhận biết. Chỉ thực hiện trong schema thực hành hoặc môi trường được phép; `CREATE TABLE` là DDL và không nên chạy trong một transaction nghiệp vụ đang có thay đổi chưa muốn commit. Hành vi chi tiết của CTAS có thể phụ thuộc phiên bản Oracle, tính năng và dạng truy vấn nguồn. Vì vậy việc **đọc lại metadata của bảng mới** là bước thiết yếu.

## 1. CTAS thực hiện hai việc trong một câu lệnh

CTAS là dạng `CREATE TABLE ... AS SELECT ...`:

```text
        BẢNG NGUỒN / VIEW / CÁC BẢNG JOIN
                        │
                        ▼
                 SELECT query
         • Chọn cột, biểu thức, bí danh
         • WHERE / JOIN / GROUP BY
         • Tính kết quả tại thời điểm chạy
                        │
                        ▼
               CREATE TABLE AS
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
   Định nghĩa cột                Các hàng kết quả
   được suy từ SELECT            được nạp vào bảng mới
         │                             │
         └──────────────┬──────────────┘
                        ▼
               BẢNG ĐÍCH MỚI

  KHÔNG ĐƯỢC NGẦM HIỂU LÀ SAO CHÉP ĐẦY ĐỦ:
  PK / FK / UNIQUE / CHECK / INDEX / TRIGGER /
  DEFAULT / IDENTITY / GRANTS / COMMENTS / ...
```

Điểm khác biệt quan trọng:

| Kỹ thuật | Mục đích | Bảng đích có cần tồn tại trước? |
| --- | --- | --- |
| `CREATE TABLE ... AS SELECT ...` | Tạo **bảng mới** từ kết quả SELECT | **Không**; CTAS tạo ra bảng |
| `INSERT INTO target SELECT ...` | Thêm dữ liệu vào **bảng đã tồn tại** | **Có** |
| `CREATE TABLE ...` khai báo cột và constraints | Tạo schema theo thiết kế rõ ràng | Không |
| `CREATE VIEW ... AS SELECT ...` | Lưu định nghĩa truy vấn logic, không phải bảng lưu toàn bộ kết quả theo CTAS | Không; tạo view |
| Export/import, Data Pump, metadata DDL | Di chuyển/phục hồi object/data theo các tùy chọn tương ứng | Phụ thuộc công cụ và mục tiêu |

CTAS rất hữu ích khi **cần một bảng dữ liệu mới từ một truy vấn**. Nếu mục tiêu là bản sao chính xác của schema và các đối tượng phụ trợ để thay thế bảng production, CTAS **không phải** phương pháp đầy đủ chỉ với một lệnh.

### 1.1. Các quyền cơ bản

Để CTAS thành công, user cần:

- Quyền **CREATE TABLE** trong schema được phép (hoặc quyền quản trị tương ứng nếu tạo trong schema khác).
- Khả năng đọc các bảng/view nguồn theo quyền có hiệu lực đối với câu SELECT.
- Quota/dung lượng thích hợp ở tablespace đích và tài nguyên lưu trữ đủ để nạp dữ liệu.

Việc có quyền `SELECT` trên bảng nguồn không đồng nghĩa tự động có quyền tạo bảng trong schema đó. Ngược lại, một bảng mới do bạn tạo không tự được cấp quyền truy cập cho những user có quyền trên bảng nguồn.

## 2. Cú pháp CTAS cơ bản và ba cách sao chép thường gặp

### 2.1. Sao chép toàn bộ các cột được SELECT và toàn bộ hàng

```sql
CREATE TABLE lab_ctas_orders_all AS
SELECT *
FROM lab_ctas_orders;
```

Oracle tạo bảng `LAB_CTAS_ORDERS_ALL` và nạp các hàng được truy vấn. Dùng `SELECT *` nhanh trong lab, nhưng có rủi ro:

- Danh sách cột thay đổi khi bảng nguồn được thêm/xóa cột.
- Các **invisible/hidden columns** không nhất thiết xuất hiện trong `SELECT *` thông thường.
- CTAS lấy **các cột do SELECT trả về**; không có nghĩa mọi thuộc tính storage, default, computed/virtual hoặc identity đều được nhân bản.

Trong mã triển khai nên **liệt kê cột rõ ràng** để schema đích có thể dự đoán được:

```sql
CREATE TABLE lab_ctas_orders_all AS
SELECT order_id, customer_id, amount, status, created_at, note
FROM lab_ctas_orders;
```

Hai lệnh trên **không được chạy liên tiếp trên cùng tên bảng** vì lệnh thứ hai sẽ gặp lỗi “name is already used by an existing object”. Hãy chọn một cách tạo và một tên bảng đích phù hợp.

### 2.2. Sao chép chỉ những hàng phù hợp WHERE

```sql
CREATE TABLE lab_ctas_orders_paid AS
SELECT order_id, customer_id, amount, status, created_at
FROM lab_ctas_orders
WHERE status = 'PAID';
```

Số hàng của bảng mới bằng số hàng thuộc kết quả truy vấn tại snapshot mà câu SELECT nhìn thấy. Không cần bảng đích có cùng số cột hay toàn bộ hàng của nguồn.

### 2.3. Chỉ lấy cấu trúc cột, không lấy dữ liệu

```sql
CREATE TABLE lab_ctas_orders_empty AS
SELECT order_id, customer_id, amount, status, created_at, note
FROM lab_ctas_orders
WHERE 1 = 0;
```

Điều kiện `1 = 0` luôn sai nên bảng mới **không có hàng**, nhưng vẫn có các cột suy ra từ SELECT. Đây là mẫu hay dùng để dựng khung cột nhanh.

**Không gọi đây là “sao chép toàn bộ schema nhưng rỗng”**: primary key, foreign key, default, index, trigger và nhiều thuộc tính không được tự copy chỉ vì bảng chưa có dữ liệu. Những ràng buộc NOT NULL được kế thừa theo điều kiện nhất định vẫn cần kiểm tra.

### 2.4. Sao chép từ JOIN hoặc phép tính, không chỉ từ một bảng

CTAS nhận bất kỳ SELECT phù hợp với quy tắc của Oracle, kể cả join, biểu thức và tổng hợp:

```sql
CREATE TABLE lab_ctas_customer_revenue AS
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    SUM(o.amount) AS revenue
FROM lab_ctas_customers c
JOIN lab_ctas_orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name;
```

Kết quả bảng `LAB_CTAS_CUSTOMER_REVENUE` là **một bảng báo cáo mới**, không phải bản sao của `LAB_CTAS_CUSTOMERS` hay `LAB_CTAS_ORDERS`. Cột `REVENUE` được suy ra từ `SUM`, còn `ORDER_COUNT` được suy ra từ `COUNT`. Nếu muốn cột có precision/scale rõ ràng cho giao diện hoặc API, nên dùng `CAST` có chủ đích.

## 3. Chuẩn bị bộ dữ liệu minh họa để quan sát khác biệt

Các bước trong phần này chỉ dành cho **schema thực hành**. Nếu object đã tồn tại, hãy đổi tên thay vì ghi đè object đang được sử dụng.

Tạo bảng cha:

```sql
CREATE TABLE lab_ctas_customers (
    customer_id   NUMBER(10)
        CONSTRAINT pk_lab_ctas_customers PRIMARY KEY,
    customer_name VARCHAR2(80) NOT NULL
);

INSERT INTO lab_ctas_customers (customer_id, customer_name)
VALUES (101, 'An');

INSERT INTO lab_ctas_customers (customer_id, customer_name)
VALUES (102, 'Binh');
```

Tạo bảng đơn hàng có nhiều thuộc tính cần đối chiếu:

```sql
CREATE TABLE lab_ctas_orders (
    order_id    NUMBER(10),
    customer_id NUMBER(10) NOT NULL,
    amount      NUMBER(12, 2) DEFAULT 0 NOT NULL,
    status      VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    created_at  DATE DEFAULT SYSDATE NOT NULL,
    note        VARCHAR2(100),
    CONSTRAINT pk_lab_ctas_orders
        PRIMARY KEY (order_id),
    CONSTRAINT fk_lab_ctas_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_ctas_customers (customer_id),
    CONSTRAINT ck_lab_ctas_orders_amount
        CHECK (amount >= 0),
    CONSTRAINT ck_lab_ctas_orders_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE INDEX idx_lab_ctas_orders_customer
    ON lab_ctas_orders (customer_id);
```

Thêm dữ liệu để quan sát:

```sql
INSERT INTO lab_ctas_orders
    (order_id, customer_id, amount, status, note)
VALUES
    (1, 101, 120.50, 'PAID', 'Giao thanh cong');

INSERT INTO lab_ctas_orders
    (order_id, customer_id, amount, status, note)
VALUES
    (2, 101, 85.00, 'NEW', NULL);

INSERT INTO lab_ctas_orders
    (order_id, customer_id, amount, status, note)
VALUES
    (3, 102, 30.00, 'CANCELLED', 'Da huy');

COMMIT;
```

Lưu ý: `CREATED_AT` nhận giá trị default `SYSDATE` vì lệnh INSERT không cung cấp cột này. Constraint primary key tạo một index phù hợp để thực thi tính duy nhất; index `IDX_LAB_CTAS_ORDERS_CUSTOMER` được tạo thêm để phục vụ truy cập theo khách hàng.

Giờ chạy CTAS:

```sql
CREATE TABLE lab_ctas_orders_copy AS
SELECT order_id, customer_id, amount, status, created_at, note
FROM lab_ctas_orders;
```

Các hàng được sao chép, nhưng bây giờ cần **chủ động đối chiếu hành vi** của bảng mới với bảng gốc.

## 4. Thuộc tính nào được sao chép, thuộc tính nào không?

Bảng tổng quan dưới đây thể hiện hành vi CTAS Oracle thông thường. Có những trường hợp ngoại lệ của NOT NULL, kiểu dữ liệu và tùy chọn DDL; đọc lại metadata luôn là bước quyết định.

| Thành phần | Khi dùng CTAS thông thường | Điều phải kiểm tra |
| --- | --- | --- |
| **Số hàng và giá trị cột** | Nạp những hàng của kết quả SELECT | Điều kiện WHERE/JOIN, số hàng, NULL, tổng tiền, dữ liệu thời điểm chụp |
| **Tên cột** | Lấy tên/cột alias của SELECT hoặc danh sách cột đích khai báo | Tên trùng, alias, quoted identifiers, độ dài tên |
| **Kiểu dữ liệu** | Suy ra từ kiểu của biểu thức SELECT | NUMBER precision/scale, CHAR/VARCHAR2 length semantics, DATE/TIMESTAMP, LOB |
| **NULLABLE/NOT NULL** | Một số NOT NULL có thể được kế thừa theo điều kiện Oracle | `USER_TAB_COLUMNS.NULLABLE` và `USER_CONSTRAINTS`; không coi việc kế thừa là luôn đúng |
| **PRIMARY KEY** | **Không tự copy** | Tạo PK phù hợp sau khi dữ liệu được kiểm tra |
| **UNIQUE** | **Không tự copy** | Dữ liệu đích có còn unique không? |
| **FOREIGN KEY** | **Không tự copy** | Bảng cha, orphan rows và quyền REFERENCES |
| **CHECK** | **Không tự copy** | Logic nghiệp vụ có phải áp dụng cho bảng đích? |
| **DEFAULT/DEFAULT ON NULL** | **Không tự giữ như định nghĩa default của nguồn** | Xem `DATA_DEFAULT` và tạo default mới khi cần |
| **IDENTITY/sequence behavior** | Không mặc định sao chép cơ chế sinh khóa | `USER_TAB_IDENTITY_COLS`, sequence/trigger liên quan |
| **Index của bảng nguồn** | **Không tự copy** | `USER_INDEXES`, `USER_IND_COLUMNS`; tạo index theo workload đích |
| **Trigger** | **Không tự copy** | `USER_TRIGGERS` và những side effects cần thiết |
| **Comments** | Không tự giữ như metadata comment | `USER_TAB_COMMENTS`, `USER_COL_COMMENTS` |
| **GRANT/privileges** | Không kế thừa grants trên bảng nguồn | `USER_TAB_PRIVS_MADE` hoặc view quyền tương ứng |
| **Virtual/hidden/invisible columns** | Kết quả phụ thuộc SELECT; không suy ra còn thuộc tính gốc | `USER_TAB_COLS`, expression/visibility |
| **Partitioning, compression, LOB storage, tablespace, logging** | Theo DDL và mặc định của bảng mới, không mặc nhiên giống bảng nguồn | `USER_TABLES`, `USER_TAB_PARTITIONS`, `USER_LOBS`, DDL thật |
| **Row-level security, audit, masking, encryption policy** | Không được giả định chuyển sang bảng mới | Kiểm tra các policy/security controls được áp dụng thực tế |
| **Optimizer statistics** | Không thể coi là bản sao statistics nguồn | Kiểm tra statistics riêng; CTAS có thể được tự thu thập thống kê trong những điều kiện phù hợp |

Kết luận: CTAS **sao chép kết quả của SELECT vào một bảng mới**, chứ không thực hiện “clone tất cả object và tất cả metadata phụ trợ”.

## 5. Ràng buộc: phần dễ bỏ sót nhất

### 5.1. PRIMARY KEY không tự xuất hiện

Bảng `LAB_CTAS_ORDERS` có:

```sql
CONSTRAINT pk_lab_ctas_orders PRIMARY KEY (order_id)
```

Nhưng bảng `LAB_CTAS_ORDERS_COPY` tạo bằng CTAS không tự nhận cùng primary key. Kết quả `ORDER_ID` hiện tại có thể vẫn không trùng, **nhưng dữ liệu hiện tại không trùng không có nghĩa có ràng buộc bảo vệ dữ liệu tương lai**.

Nếu muốn bảng đích có PK:

```sql
ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT pk_lab_ctas_orders_copy
    PRIMARY KEY (order_id);
```

Trước khi thêm, cần xác minh:

```sql
SELECT order_id, COUNT(*) AS duplicate_count
FROM lab_ctas_orders_copy
GROUP BY order_id
HAVING COUNT(*) > 1;

SELECT COUNT(*) AS null_key_count
FROM lab_ctas_orders_copy
WHERE order_id IS NULL;
```

Vì PK yêu cầu không NULL và duy nhất, nếu CTAS từ JOIN làm một order xuất hiện nhiều lần thì `ALTER TABLE ... PRIMARY KEY` có thể thất bại. Không tự thêm PK với giả định mã nguồn có PK là đủ.

### 5.2. UNIQUE, FOREIGN KEY và CHECK cũng không tự giữ

**UNIQUE:** nếu bảng đích cần bảo đảm một cặp giá trị không bị lặp, thêm constraint thích hợp:

```sql
ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT uq_lab_ctas_order_customer
    UNIQUE (order_id, customer_id);
```

Ví dụ này chỉ có ý nghĩa nếu nghiệp vụ muốn uniqueness trên **cặp** (`ORDER_ID`, `CUSTOMER_ID`); với primary key trên `ORDER_ID`, nó có thể trở thành ràng buộc dư thừa. Tránh copy cơ học mọi UNIQUE mà không xét mục đích.

**FOREIGN KEY:** nếu bảng đích được dùng như bảng nghiệp vụ có quan hệ với khách hàng:

```sql
ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT fk_lab_ctas_copy_customer
    FOREIGN KEY (customer_id)
    REFERENCES lab_ctas_customers (customer_id);
```

Trước khi thêm FK, kiểm tra các hàng tham chiếu tới parent không tồn tại:

```sql
SELECT o.customer_id, COUNT(*) AS rows_without_parent
FROM lab_ctas_orders_copy o
LEFT JOIN lab_ctas_customers c
       ON c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL
GROUP BY o.customer_id;
```

Nếu bạn tạo bảng snapshot từ dữ liệu lịch sử nhưng bảng parent về sau đã thay đổi, việc áp FK có thể không phù hợp hoặc bị từ chối do orphan rows. Một snapshot phục vụ phân tích có thể cố ý không có FK; đây là **quyết định thiết kế có chủ đích**, không phải lý do bỏ qua kiểm tra.

**CHECK:**

```sql
ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT ck_lab_ctas_copy_amount
    CHECK (amount >= 0);

ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT ck_lab_ctas_copy_status
    CHECK (status IN ('NEW', 'PAID', 'CANCELLED'));
```

Nếu CTAS tạo dữ liệu qua biểu thức thay đổi ý nghĩa của cột, không nên tự động chép lại CHECK. Ví dụ bảng kết quả tổng hợp có cột `TOTAL_AMOUNT` có thể cần CHECK khác bảng đơn hàng gốc.

### 5.3. NOT NULL là ngoại lệ cần hiểu chính xác

Oracle **có thể kế thừa NOT NULL** từ bảng nguồn trong CTAS theo điều kiện của loại SELECT, ví dụ khi cột đích được chọn trực tiếp từ cột nguồn có ràng buộc NOT NULL và query đáp ứng các điều kiện Oracle quy định. Ngược lại, với biểu thức, JOIN, tổ hợp SELECT phức tạp hoặc một số kiểu dữ liệu/cấu hình, việc kế thừa không được bảo đảm.

Vì vậy **hai kết luận đều sai**:

1. “CTAS chắc chắn bỏ tất cả NOT NULL.”
2. “CTAS luôn giữ tất cả NOT NULL của bảng nguồn.”

Hãy đọc metadata:

```sql
SELECT table_name, column_name, nullable
FROM user_tab_columns
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, column_id;
```

Và constraint:

```sql
SELECT table_name, constraint_name, constraint_type,
       status, validated, search_condition_vc
FROM user_constraints
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, constraint_type, constraint_name;
```

Ở các phiên bản hỗ trợ `SEARCH_CONDITION_VC`, cột này giúp xem CHECK/NOT NULL condition bằng VARCHAR2; giới hạn độ dài và các phiên bản cũ cần lưu ý. Nếu view môi trường không có cột đó, truy vấn chỉ các cột chung `TABLE_NAME`, `CONSTRAINT_NAME`, `CONSTRAINT_TYPE`, `STATUS` và `VALIDATED`.

Một constraint loại `C` trong `USER_CONSTRAINTS` có thể là **NOT NULL** hoặc một **CHECK** khác; phải đối chiếu cột/điều kiện, không chỉ đếm constraint type `C`.

Nếu yêu cầu nghiệp vụ là bắt buộc có `STATUS`, có thể áp dụng:

```sql
ALTER TABLE lab_ctas_orders_copy
    MODIFY (status NOT NULL);
```

Nếu cột đã có NOT NULL được Oracle kế thừa, không cần thêm lặp lại; hãy kiểm tra trước để chọn lệnh phù hợp.

### 5.4. Trạng thái constraint cũng là metadata

Ngoài loại constraint, bảng nguồn có thể có các thuộc tính như:

- `ENABLED` hoặc `DISABLED`.
- `VALIDATED` hoặc `NOT VALIDATED`.
- `DEFERRABLE` và `INITIALLY DEFERRED/IMMEDIATE`.
- Quy tắc `ON DELETE` của foreign key.
- Tên constraint được quy ước theo hệ thống triển khai.

Khi dựng bảng đích như một bảng nghiệp vụ thực sự, việc chỉ thêm một constraint “cùng loại” chưa chắc tái tạo **cùng hành vi**. Hãy so sánh metadata và quyết định rõ những trạng thái nào cần giữ.

## 6. DEFAULT, IDENTITY, generated columns và dữ liệu được chụp

### 6.1. Giá trị hiện có được sao chép, DEFAULT không tự theo

Trong bảng nguồn:

```sql
status     VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
created_at DATE DEFAULT SYSDATE NOT NULL
```

Khi CTAS chọn `STATUS` và `CREATED_AT`, **các giá trị đã tồn tại trong hàng nguồn được sao chép**. Nhưng bảng đích không mặc nhiên có `DEFAULT 'NEW'` hoặc `DEFAULT SYSDATE` cho các lần INSERT sau.

Kiểm tra:

```sql
SELECT table_name, column_name, nullable, data_default
FROM user_tab_columns
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
  AND column_name IN ('STATUS', 'CREATED_AT', 'AMOUNT')
ORDER BY table_name, column_name;
```

`DATA_DEFAULT` thuộc kiểu LONG ở một số dictionary views; đọc và hiển thị giá trị trong SQL client thay vì cố `ORDER BY` trực tiếp cột này.

Nếu bảng đích cần default:

```sql
ALTER TABLE lab_ctas_orders_copy
    MODIFY (status DEFAULT 'NEW');

ALTER TABLE lab_ctas_orders_copy
    MODIFY (created_at DEFAULT SYSDATE);
```

Đặt default **không thay đổi ngược các giá trị đã lưu**. Các dạng `DEFAULT ON NULL` hoặc biểu thức default khác cần được xử lý theo đúng ngữ nghĩa riêng, không coi `DEFAULT` đơn giản là hoàn toàn tương đương.

### 6.2. IDENTITY không đơn giản là giá trị số trong một cột

Giả sử bảng nguồn có:

```sql
id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY
```

CTAS có thể lấy **các giá trị ID hiện có** trong `SELECT id`, nhưng **cơ chế tự sinh giá trị cho các INSERT mới không được coi là đã nhân bản**. Với bảng sử dụng identity, cần kiểm tra dictionary metadata dành cho identity, ví dụ `USER_TAB_IDENTITY_COLS` ở phiên bản có hỗ trợ:

```sql
SELECT table_name, column_name, generation_type
FROM user_tab_identity_cols
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, column_name;
```

Đây là truy vấn tham khảo cho môi trường hỗ trợ identity columns. Với database cũ không có view, đừng mặc định tính năng identity có mặt.

Việc “tạo lại identity” cho bảng đã có các giá trị ID cần **quyết định thiết kế và xử lý bộ sinh khóa** phù hợp để tránh đụng giá trị tồn tại. Không tự tạo sequence mới ở giá trị bắt đầu 1 nếu bảng snapshot đã chứa các khóa 1, 2, 3...

### 6.3. VIRTUAL, INVISIBLE và GENERATED properties

Một số cột được tính từ biểu thức (**virtual column**) hoặc được đánh dấu **invisible**; `SELECT *` thường không thể hiện toàn bộ cột có tính chất đặc biệt. Khi bạn chủ động SELECT một virtual column, kết quả được materialize như giá trị của biểu thức trong bảng mới, **không đồng nghĩa bảng CTAS giữ nguyên công thức virtual column**.

Ví dụ khái niệm:

```sql
CREATE TABLE lab_ctas_price_source (
    net_amount NUMBER(10, 2),
    tax_amount NUMBER(10, 2),
    gross_amount NUMBER(12, 2)
        GENERATED ALWAYS AS (net_amount + tax_amount) VIRTUAL
);

CREATE TABLE lab_ctas_price_copy AS
SELECT net_amount, tax_amount, gross_amount
FROM lab_ctas_price_source;
```

Ở đích, `GROSS_AMOUNT` chứa giá trị được chọn tại thời điểm CTAS; **không giả định phép tính virtual được duy trì** khi `NET_AMOUNT` thay đổi về sau. Kiểm tra `USER_TAB_COLS`, đặc biệt các thuộc tính liên quan virtual/hidden nếu phiên bản hỗ trợ:

```sql
SELECT table_name, column_name, data_type,
       nullable, virtual_column, hidden_column
FROM user_tab_cols
WHERE table_name IN ('LAB_CTAS_PRICE_SOURCE', 'LAB_CTAS_PRICE_COPY')
ORDER BY table_name, column_id;
```

Đối với biểu thức trong `SELECT`, Oracle suy ra kiểu và tên cột dựa vào biểu thức hoặc alias. Muốn schema ổn định, hãy chỉ định tên và kiểu một cách có chủ đích.

## 7. Kiểu dữ liệu và tên cột khi SELECT có biểu thức

CTAS không chỉ nhân bản các cột của một bảng. Nếu SELECT biến đổi dữ liệu, **kiểu cột đích là kiểu của kết quả biểu thức**, không nhất thiết giống cột gốc.

Ví dụ:

```sql
CREATE TABLE lab_ctas_order_summary AS
SELECT
    CAST(customer_id AS NUMBER(10)) AS customer_id,
    CAST(COUNT(*) AS NUMBER(10)) AS order_count,
    CAST(SUM(amount) AS NUMBER(14, 2)) AS total_amount
FROM lab_ctas_orders
WHERE status = 'PAID'
GROUP BY customer_id;
```

Tại đây:

- `ORDER_COUNT` là kết quả tổng hợp, không phải cột của bảng nguồn.
- `TOTAL_AMOUNT` là tổng qua nhiều hàng, cần cân nhắc precision/scale đủ lớn.
- `CAST` giúp mô tả rõ kiểu đích và tránh phụ thuộc cách suy luận kiểu của một biểu thức phức tạp.
- Không tự gắn primary key cho `CUSTOMER_ID` nếu query có khả năng tạo nhiều hàng cho một khách hàng trong thiết kế khác.

### 7.1. Bí danh và tên cột trùng nhau

Trong CTAS với SELECT gồm nhiều biểu thức, mỗi cột đích cần có tên hợp lệ, không trùng tên không phù hợp. Nếu JOIN hai bảng đều có `ID`, câu `SELECT a.id, b.id` có thể gây lỗi tên cột trùng trong CTAS. Dùng alias:

```sql
CREATE TABLE lab_ctas_pairs AS
SELECT a.customer_id AS customer_id,
       o.order_id    AS order_id
FROM lab_ctas_customers a
JOIN lab_ctas_orders o
  ON o.customer_id = a.customer_id;
```

Với biểu thức như `SUM(amount)`, nên dùng `AS total_amount` thay vì chờ Oracle tự tạo tên cột. Nếu dùng alias có double quotes, tên cột có thể phân biệt hoa/thường, gây bất tiện trong truy vấn về sau.

### 7.2. NULL literal và CAST

Nếu muốn cột mới nhận NULL ở mọi hàng, hãy khai báo kiểu rõ:

```sql
CREATE TABLE lab_ctas_with_review_flag AS
SELECT order_id,
       CAST(NULL AS VARCHAR2(30)) AS review_note
FROM lab_ctas_orders;
```

Không nên dùng `NULL AS review_note` trong CTAS rồi mặc định Oracle sẽ tự suy ra đúng kiểu/độ dài bạn muốn; ở một số tình huống có thể phát sinh lỗi định nghĩa cột không hợp lệ hoặc kiểu không như dự kiến.

### 7.3. DATE, TIMESTAMP, NUMBER và VARCHAR2

Khi dùng `TO_CHAR(created_at, ...)`, cột đích sẽ chứa **text**, không còn là DATE/TIMESTAMP. Khi dùng `TRUNC(created_at)`, cột đích vẫn liên quan kiểu ngày nhưng có ý nghĩa chính xác của hàm. Khi dùng phép tính hoặc `NVL`, kiểu kết quả phụ thuộc quy tắc Oracle áp dụng cho các biểu thức.

Không xem bảng CTAS từ một truy vấn báo cáo là schema tương đương với bảng nghiệp vụ. Kiểm tra:

```sql
SELECT table_name,
       column_id,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       char_used,
       nullable
FROM user_tab_columns
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY',
                     'LAB_CTAS_ORDER_SUMMARY')
ORDER BY table_name, column_id;
```

`CHAR_USED` giúp phân biệt byte/character length semantics khi áp dụng cho cột ký tự; `DATA_LENGTH` không phải lúc nào cũng là số ký tự tối đa trong giao diện người dùng.

## 8. Index, trigger, sequence và các đối tượng đi kèm

### 8.1. CTAS không copy index

Bảng nguồn có thể có nhiều index cho primary key, foreign key, tìm kiếm hay function-based index. Bảng CTAS mới **không tự nhận các index đó**.

Kiểm tra:

```sql
SELECT table_name, index_name, uniqueness, index_type, status
FROM user_indexes
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, index_name;
```

Danh sách cột index:

```sql
SELECT index_name, column_position, column_name, descend
FROM user_ind_columns
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY index_name, column_position;
```

Đối với function-based indexes, có thể cần xem thêm `USER_IND_EXPRESSIONS`. Nếu bảng mới chỉ phục vụ một lần đối soát, có thể **không cần** toàn bộ index của bảng nguồn. Nếu bảng mới phục vụ lâu dài cho ứng dụng, hãy tạo index dựa trên **truy vấn thật**, ràng buộc và dữ liệu đích.

Ví dụ thêm một index cho truy vấn thường lọc `CUSTOMER_ID`:

```sql
CREATE INDEX idx_lab_ctas_copy_customer
ON lab_ctas_orders_copy (customer_id);
```

Index tiêu tốn dung lượng và thời gian khi ghi; không tự động thêm nhiều index chỉ vì nguồn có chúng.

### 8.2. Trigger không theo CTAS

Một trigger `BEFORE INSERT` của nguồn có thể sinh mã, ghi audit, kiểm tra quy tắc hoặc cập nhật bảng phụ. CTAS tạo một **bảng khác**; trigger nguồn không tự được gắn vào bảng đó.

Tra cứu:

```sql
SELECT table_name,
       trigger_name,
       trigger_type,
       triggering_event,
       status
FROM user_triggers
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, trigger_name;
```

Khi cần trigger trên bảng đích, hãy kiểm tra cả **mục đích nghiệp vụ**. Trigger ghi audit của bảng production có thể không phù hợp cho snapshot dùng thử. Ngược lại, thiếu trigger sinh khóa trong một bảng được thay thế chính thức có thể gây lỗi cho các lần INSERT mới.

### 8.3. Sequence, synonym và các object ngoài bảng

Nếu ứng dụng dùng `MY_SEQ.NEXTVAL` để lấy ID cho bảng nguồn, CTAS chỉ copy **các ID đang có** khi bạn chọn cột tương ứng. Nó không tự tạo một sequence mới, không chỉnh giá trị bắt đầu của sequence và không tạo synonym trỏ đến bảng đích.

Với một hệ thống cũ, câu DML của ứng dụng có thể dựa vào sequence/trigger/synonym và grants phối hợp. Trước khi chuyển sang bảng mới, phải rà soát toàn bộ đường ghi, không chỉ kết quả `SELECT COUNT(*)`.

## 9. Comments, privileges và bảo mật không tự được nhân bản

### 9.1. Comments

Table/column comments giúp công cụ và người dùng hiểu dữ liệu:

```sql
COMMENT ON TABLE lab_ctas_orders
IS 'Bang don hang thuc hanh CTAS';

COMMENT ON COLUMN lab_ctas_orders.amount
IS 'So tien cua don hang';
```

Sau CTAS, **không giả định comment đã được mang sang bảng copy**. Kiểm tra:

```sql
SELECT table_name, comments
FROM user_tab_comments
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name;

SELECT table_name, column_name, comments
FROM user_col_comments
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, column_name;
```

Khi cần, thêm comment tương ứng hoặc viết comment mới mô tả **nguồn và thời điểm chụp**:

```sql
COMMENT ON TABLE lab_ctas_orders_copy
IS 'Ban sao CTAS phuc vu thuc hanh; khong tu dong dong bo';
```

### 9.2. GRANT trên bảng nguồn không được kế thừa

Giả sử user `APP_READER` được cấp `SELECT` trên `LAB_CTAS_ORDERS`. Điều đó không có nghĩa user này được phép đọc `LAB_CTAS_ORDERS_COPY`.

Tra cứu privileges đã cấp, khi view phù hợp và có quyền:

```sql
SELECT table_name, grantee, privilege, grantable
FROM user_tab_privs_made
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, grantee, privilege;
```

Nếu bảng mới thực sự cần được chia sẻ, chủ sở hữu có thể cấp quyền theo nguyên tắc tối thiểu:

```sql
-- Ví dụ chỉ dùng khi APP_READER tồn tại và được phê duyệt:
-- GRANT SELECT ON lab_ctas_orders_copy TO app_reader;
```

Không copy tự động toàn bộ grants của nguồn. Một bảng snapshot có thể chứa dữ liệu nhạy cảm hoặc thuộc môi trường test; quyền truy cập cần được xét lại.

### 9.3. Row-level security, masking và encryption

Một bảng nguồn có thể chịu các cơ chế như:

- **VPD/row-level security** giới hạn những hàng user được phép nhìn thấy.
- **Data Redaction** hoặc masking/policy trình bày dữ liệu.
- **Auditing** và những quy tắc truy cập đặc thù.
- **Column/tablespace encryption** và các chính sách lưu trữ nhạy cảm.

**Không mặc định CTAS chuyển nguyên các chính sách này sang bảng mới.** Câu `SELECT` nguồn có thể chỉ thấy những hàng được phép nhìn theo ngữ cảnh session, nhưng bảng mới phải được kiểm tra lại các security controls riêng của nó. Những dữ liệu được truy vấn/biểu diễn theo policy cũng cần được hiểu đúng trước khi sao chép.

Vì vậy, không nên CTAS một bảng chứa thông tin nhạy cảm sang schema hoặc tablespace có bảo mật thấp hơn chỉ vì cần “bản backup nhanh”. CTAS không thay thế quy trình backup, data masking và data governance.

## 10. Tablespace, partitioning, compression, LOB và logging

### 10.1. Vị trí lưu trữ không mặc nhiên giữ nguyên

Nếu không chỉ rõ tablespace, bảng CTAS thường được tạo theo **quy tắc default tablespace và DDL của user/table**; không phải cứ nguồn nằm ở `APP_DATA` thì đích cũng nằm `APP_DATA`.

Ví dụ có chủ đích:

```sql
CREATE TABLE lab_ctas_orders_in_data
TABLESPACE app_data
AS
SELECT order_id, customer_id, amount, status
FROM lab_ctas_orders;
```

Ví dụ trên chỉ chạy khi tablespace `APP_DATA` tồn tại, user có quota/quyền và bạn được phép cấp phát tại đó. Với schema lab không có `APP_DATA`, hãy bỏ mệnh đề `TABLESPACE` hoặc thay theo cấu hình thật.

Kiểm tra ở dictionary:

```sql
SELECT table_name,
       tablespace_name,
       partitioned,
       temporary,
       logging,
       compression,
       compress_for
FROM user_tables
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name;
```

Một số cột về compression có thể phụ thuộc phiên bản/tính năng; khi làm việc với partitioned tables, `TABLESPACE_NAME` ở cấp bảng không đủ để kết luận vị trí của tất cả partitions/subpartitions.

### 10.2. Partitioning không xuất hiện chỉ vì nguồn có partition

Nếu nguồn được partition theo ngày hoặc hash, CTAS thông thường không phải lời cam kết bảng đích có cùng partition layout, local indexes hay partition attributes. Muốn bảng mới partitioned, cần **định nghĩa partitioning trong CREATE TABLE** nếu phiên bản/tính năng hỗ trợ và sau đó kiểm tra:

```sql
SELECT table_name, partitioning_type, subpartitioning_type
FROM user_part_tables
WHERE table_name = 'LAB_CTAS_ORDERS_COPY';
```

Nếu là bảng partitioned, kiểm tra thêm `USER_TAB_PARTITIONS`/`USER_TAB_SUBPARTITIONS` và các index liên quan. Không đưa một bảng copy dùng thử vào workload production rồi mới phát hiện toàn bộ dữ liệu nằm trong một segment không partitioned.

### 10.3. LOB storage và column properties

Đối với `CLOB`, `BLOB` hoặc LOBs khác, CTAS có thể tạo các cột LOB từ kết quả SELECT, nhưng cấu hình **SecureFiles/BasicFiles, LOB storage, retention/compression/deduplication, encryption** không được mặc định giống nguồn. Đọc metadata phù hợp:

```sql
SELECT table_name, column_name, segment_name,
       tablespace_name, securefile
FROM user_lobs
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, column_name;
```

Một số cột trong `USER_LOBS` và khả năng cấu hình SecureFiles thay đổi theo version/edition; lệnh chỉ là mẫu quan sát khi bảng có LOB. Với bảng lab không có LOB, không có hàng là bình thường.

### 10.4. LOGGING, NOLOGGING và recovery

CTAS có thể được tối ưu để nạp một lượng dữ liệu lớn và có các tùy chọn liên quan đến `PARALLEL` hoặc `NOLOGGING` tùy môi trường. Đây là **quyết định vận hành**, không chỉ vấn đề tốc độ.

Ví dụ cú pháp chuyên biệt:

```sql
CREATE TABLE lab_ctas_bulk_copy
NOLOGGING
AS
SELECT order_id, customer_id, amount, status
FROM lab_ctas_orders;
```

**Không dùng `NOLOGGING` mặc định cho dữ liệu quan trọng.** Một số thao tác nologging có thể tạo ít redo cho dữ liệu nạp theo cách Oracle hỗ trợ, nhưng vẫn có metadata/redo nhất định; chế độ `FORCE LOGGING` hoặc các quy tắc khác có thể thay đổi hiệu lực. Những thay đổi không được ghi đủ redo có thể tạo **rủi ro media recovery/standby** nếu backup và đồng bộ không được xử lý phù hợp.

Nếu định sử dụng CTAS để nạp dữ liệu lớn:

1. Xác định yêu cầu recovery/RPO và Data Guard.
2. Kiểm tra mức logging được tổ chức cho phép.
3. Dự trù tablespace, TEMP, UNDO, redo và dung lượng hệ thống.
4. Cân nhắc thống kê, index/constraint được tạo sau khi nạp.
5. Lên kế hoạch backup và kiểm chứng recovery khi áp dụng nologging.

CTAS **không phải backup vật lý thay thế RMAN**. Bảng copy trên cùng database/tablespace không bảo vệ bạn trước sự cố mất storage, corruption ở mức database hoặc lỗi vận hành nghiêm trọng.

## 11. DDL, COMMIT và tính nhất quán dữ liệu

### 11.1. CTAS là DDL, có implicit commit

Trong Oracle, `CREATE TABLE` là **DDL**, kể cả khi có `AS SELECT`. Các lệnh DDL thực hiện implicit commit theo ngữ nghĩa Oracle đối với transaction hiện tại; một DDL được thực hiện sau DML chưa commit có thể **commit các thay đổi trước đó** ngay cả khi bạn nghĩ đang làm việc trong transaction ứng dụng.

Ví dụ cần tránh trong ứng dụng:

```sql
UPDATE orders
SET order_status = 'PAID'
WHERE order_id = 1001;

-- Việc tạo bảng dưới đây là DDL, không phải một bước INSERT
-- có thể ROLLBACK cùng transaction nghiệp vụ.
CREATE TABLE orders_checkpoint AS
SELECT * FROM orders;

ROLLBACK;
```

`ROLLBACK` sau CTAS **không phải phương pháp xóa bảng vừa tạo hoặc hoàn tác việc tạo bảng**. Khi cần quản lý bảng staging, hãy có quy trình tạo/drop được phê duyệt, không dựa vào rollback transaction.

### 11.2. CTAS là một ảnh chụp logic tại thời điểm truy vấn

CTAS materialize dữ liệu mà phần `SELECT` nhìn thấy theo cơ chế **read consistency** của Oracle. Nó không thiết lập liên kết đồng bộ tự động với bảng nguồn.

```text
T0:  CTAS bắt đầu đọc ORDERS
      ↓
      Đọc một tập dữ liệu nhất quán theo snapshot thích hợp
      ↓
T1:  Tạo bảng ORDERS_SNAPSHOT với kết quả được chọn
      ↓
T2:  Nguồn tiếp tục có INSERT / UPDATE / DELETE
      ↓
      Bảng snapshot KHÔNG tự cập nhật theo nguồn
```

Nếu bảng nguồn đang được cập nhật đồng thời, dữ liệu snapshot có thể khác trạng thái nguồn ở thời điểm bạn kiểm tra lại sau khi CTAS hoàn tất. Đây là hành vi bình thường của một ảnh chụp; không nhất thiết là lỗi thiếu hàng.

Đối với di chuyển dữ liệu cần tính nhất quán giữa **nhiều bảng**, phải thiết kế điểm chụp/snapshot, thời gian cắt chuyển, hoặc công cụ phù hợp thay vì CTAS các bảng độc lập ở những thời điểm khác nhau rồi giả định chúng là một transaction snapshot duy nhất.

### 11.3. CTAS không bảo đảm thứ tự vật lý hay thứ tự khi SELECT về sau

Dù câu SELECT trong CTAS có sắp xếp ở những trường hợp được phép, **bảng là một tập dữ liệu quan hệ, không có thứ tự hàng mặc định để truy vấn sau đó dựa vào**.

Khi đọc bảng copy, muốn thứ tự xác định, phải dùng:

```sql
SELECT order_id, amount
FROM lab_ctas_orders_copy
ORDER BY order_id;
```

Không viết ứng dụng phân trang dựa vào “CTAS đã nạp đúng thứ tự ngày” mà không có `ORDER BY`. Khi có giá trị bằng nhau trong cột sắp xếp, nên thêm khóa phụ duy nhất.

## 12. Quy trình kiểm tra bảng đích bằng data dictionary

Một báo cáo đối chiếu CTAS tốt không chỉ nhìn `SELECT COUNT(*)`. Nên xem theo từng lớp:

```text
                 BẢNG NGUỒN
                      │
                  CREATE TABLE
                   AS SELECT
                      │
                      ▼
                  BẢNG ĐÍCH
                      │
       ┌──────────────┼────────────────────────┐
       ▼              ▼                        ▼
   Dữ liệu         Định nghĩa cột        Các thuộc tính khác
   COUNT/SUM       USER_TAB_COLUMNS      USER_CONSTRAINTS
   NULL/DUPLICATE  USER_TAB_COLS         USER_INDEXES
   MIN/MAX         USER_TAB_IDENTITY...  USER_TRIGGERS
                                         USER_TAB_COMMENTS
                                         USER_TAB_PRIVS...
                                         USER_TABLES/USER_LOBS
                      │
                      ▼
            Tạo lại thuộc tính cần thiết
                      │
                      ▼
          Kiểm tra lại và bàn giao
```

### 12.1. Bảng đích có tồn tại đúng loại?

```sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'LAB_CTAS_ORDERS',
    'LAB_CTAS_ORDERS_COPY'
)
ORDER BY object_name;
```

Với bảng ở schema khác, dùng `ALL_OBJECTS` và lọc `OWNER` khi có quyền. Trong CDB/PDB, kiểm tra đúng service/container trước để tránh so nhầm bảng trùng tên ở môi trường khác.

### 12.2. So sánh số hàng và tổng nghiệp vụ

Khi CTAS copy toàn bộ bảng đơn hàng:

```sql
SELECT 'SOURCE' AS source_name,
       COUNT(*) AS row_count,
       SUM(amount) AS amount_sum
FROM lab_ctas_orders
UNION ALL
SELECT 'COPY' AS source_name,
       COUNT(*) AS row_count,
       SUM(amount) AS amount_sum
FROM lab_ctas_orders_copy;
```

Ví dụ kết quả khi không có thay đổi sau CTAS:

| SOURCE_NAME | ROW_COUNT | AMOUNT_SUM |
| --- | ---: | ---: |
| SOURCE | 3 | 235.50 |
| COPY | 3 | 235.50 |

**Không kết luận hai bảng hoàn toàn giống nhau chỉ vì COUNT/SUM trùng.** Những hàng khác nhau có thể có cùng tổng tiền. Nếu nguồn vẫn đang ghi, số liệu nguồn mới nhất có thể khác snapshot đích. Cần đối chiếu trên cùng mốc snapshot hoặc dùng biện pháp kiểm tra dữ liệu phù hợp với yêu cầu.

Đối chiếu NULL và tính duy nhất:

```sql
SELECT COUNT(*) AS row_count,
       COUNT(order_id) AS nonnull_order_ids,
       COUNT(DISTINCT order_id) AS distinct_order_ids,
       SUM(CASE WHEN status IS NULL THEN 1 ELSE 0 END) AS null_status_rows
FROM lab_ctas_orders_copy;
```

Những con số này giúp phát hiện vấn đề trước khi thêm constraints.

### 12.3. So sánh cột theo tên, type, precision/scale

```sql
SELECT table_name,
       column_id,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       nullable
FROM user_tab_columns
WHERE table_name IN (
    'LAB_CTAS_ORDERS',
    'LAB_CTAS_ORDERS_COPY'
)
ORDER BY table_name, column_id;
```

Thực tế còn cần kiểm tra `DATA_DEFAULT`, `CHAR_USED`, collation, identity và hidden/virtual properties khi có sử dụng. Những chi tiết này dễ bị bỏ qua nếu chỉ nhìn tên cột và kiểu `VARCHAR2`.

### 12.4. So sánh constraint và cột tham gia

```sql
SELECT c.table_name,
       c.constraint_name,
       c.constraint_type,
       cc.column_name,
       cc.position,
       c.status,
       c.validated
FROM user_constraints c
LEFT JOIN user_cons_columns cc
       ON cc.constraint_name = c.constraint_name
WHERE c.table_name IN (
    'LAB_CTAS_ORDERS',
    'LAB_CTAS_ORDERS_COPY'
)
ORDER BY c.table_name, c.constraint_name, cc.position;
```

Trong `USER_CONSTRAINTS`:

- `P` = primary key.
- `U` = unique.
- `R` = referential/foreign key.
- `C` = check, bao gồm các biểu thức NOT NULL ở những cách hiển thị tương ứng.

Tên ràng buộc hệ thống và thứ tự hiển thị có thể khác nhau. Để xem chính xác điều kiện và referenced table/constraint, cần đọc thêm các cột metadata thích hợp, không chỉ loại constraint.

### 12.5. So sánh index và trigger

```sql
SELECT table_name, index_name, uniqueness
FROM user_indexes
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, index_name;

SELECT table_name, trigger_name, status
FROM user_triggers
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, trigger_name;
```

Nếu bảng nguồn có index do PK tạo ra, bảng đích chỉ có index tương ứng **sau khi bạn tạo constraint/index cho bảng đích**.

### 12.6. So sánh định nghĩa đầy đủ với DBMS_METADATA

Oracle cung cấp `DBMS_METADATA.GET_DDL` để truy xuất DDL tạo object khi tài khoản có quyền cần thiết:

```sql
SELECT DBMS_METADATA.GET_DDL(
           'TABLE',
           'LAB_CTAS_ORDERS',
           USER
       ) AS source_ddl
FROM dual;

SELECT DBMS_METADATA.GET_DDL(
           'TABLE',
           'LAB_CTAS_ORDERS_COPY',
           USER
       ) AS target_ddl
FROM dual;
```

Trong SQL*Plus có thể cần thiết lập hiển thị CLOB đủ dài, ví dụ `SET LONG 20000`, để xem DDL đầy đủ. `DBMS_METADATA` hỗ trợ xuất metadata hữu ích nhưng kết quả tùy transform parameters, quyền, edition và version. Một số thành phần như index, grant, trigger có thể cần trích xuất theo **đúng object type** hoặc script riêng, không mặc nhiên có tất cả trong một lệnh `GET_DDL('TABLE',...)`.

Để kiểm tra nhanh, các dictionary views vẫn là cách trực tiếp và dễ dùng hơn khi chỉ quan tâm một thuộc tính.

## 13. Thêm lại thuộc tính có chủ đích sau CTAS

Một workflow mẫu khi chuẩn bị **bảng đích phục vụ lâu dài**:

1. **Xác định mục tiêu:** snapshot chỉ đọc, staging, báo cáo hay thay thế bảng nghiệp vụ?
2. **Định nghĩa danh sách cột:** chọn cột trực tiếp hay biểu thức? dùng `CAST` và alias khi cần.
3. **Chạy CTAS trong môi trường được phép** và kiểm tra nạp dữ liệu thành công.
4. **Kiểm tra dữ liệu:** số hàng, NULL, duplicate, tổng nghiệp vụ, tính hợp lệ của FK.
5. **Kiểm tra metadata:** kiểu, precision, nullable, default, identity, generated columns.
6. **Tạo constraints cần thiết** và bảo đảm dữ liệu đích đạt điều kiện.
7. **Tạo index theo workload** và kiểm tra chi phí lưu trữ.
8. **Xem xét triggers, sequences, privileges, comments và security policies** theo mục đích thực tế.
9. **Xem xét tablespace, partitioning, LOB, logging, stats và backup/recovery** trước khi vận hành.
10. **Chạy kiểm tra ứng dụng**: insert/update/delete được phép? API đọc/ghi như mong muốn? dữ liệu có còn phân biệt đúng các trạng thái?

Chẳng hạn đối với bảng `LAB_CTAS_ORDERS_COPY` đã được kiểm tra không có duplicate key, ta có thể bổ sung:

```sql
ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT pk_lab_ctas_orders_copy PRIMARY KEY (order_id);

ALTER TABLE lab_ctas_orders_copy
    MODIFY (customer_id NOT NULL);

ALTER TABLE lab_ctas_orders_copy
    MODIFY (amount DEFAULT 0);

ALTER TABLE lab_ctas_orders_copy
    MODIFY (status DEFAULT 'NEW');

ALTER TABLE lab_ctas_orders_copy
    ADD CONSTRAINT ck_lab_ctas_copy_amount CHECK (amount >= 0);

CREATE INDEX idx_lab_ctas_copy_customer
    ON lab_ctas_orders_copy(customer_id);
```

Đây là các **ví dụ cho object của bài lab**, không phải script hoàn chỉnh để clone nguồn. Nếu PK, NOT NULL hoặc index đã được tạo ở các bước trước, không chạy lặp lại. Nếu mục tiêu là snapshot bất biến, nhiều ràng buộc và index có thể không cần thiết, trong khi comment/metadata về thời điểm chụp lại quan trọng.

### 13.1. Thống kê optimizer sau CTAS

Khi CTAS nạp lượng dữ liệu lớn, Oracle có thể thu thập một số optimizer statistics ngay trong quá trình tạo tùy phiên bản và điều kiện. Nhưng **không giả định bảng mới có thống kê tương đương bảng nguồn** hoặc thống kê sẽ luôn đủ tốt cho truy vấn mới.

Có thể quan sát:

```sql
SELECT table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY');
```

Đối với hệ thống lớn, việc thu thập thống kê bằng `DBMS_STATS` phải phù hợp chính sách và khối lượng dữ liệu; không tự chạy một tác vụ gathering toàn schema trong production chỉ vì vừa dùng CTAS.

### 13.2. Thời điểm tạo và ownership

`USER_OBJECTS.CREATED` của bảng đích phản ánh thời điểm tạo object mới, không phải của bảng nguồn. Tên schema/owner của bảng đích là schema theo ngữ cảnh CREATE TABLE, không phải luôn là schema của source trong `FROM source_owner.source_table`.

Với mô hình nhiều schema, nên lưu rõ **owner nguồn, owner đích, PDB, timestamp** và phiên bản dữ liệu. Hai bảng cùng tên ở hai PDB có thể có metadata hoàn toàn khác nhau.

## 14. Những lỗi phổ biến khi dùng CTAS

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `ORA-00955: name is already used by an existing object` | Bảng hoặc object khác đã dùng tên đích | Chọn tên mới hoặc quản lý vòng đời object theo quy trình; không drop vội |
| `ORA-00942: table or view does not exist` | Sai owner/PDB, tên object hoặc không đủ quyền truy cập | Kiểm tra current schema, grants và tên đầy đủ của nguồn |
| `ORA-01031: insufficient privileges` | Thiếu quyền CREATE TABLE/khả năng thực hiện DDL | Xác minh grant phù hợp và quota |
| `ORA-01950: no privileges on tablespace` | Không có quota được cấp trên tablespace đích | Nhờ quản trị viên cấp quota hợp lệ hoặc dùng tablespace khác |
| `ORA-01653: unable to extend table` | Tablespace/storage đích không cấp được extent | Kiểm tra tablespace, datafiles/autoextend, ASM/filesystem |
| `ORA-00918: column ambiguously defined` | Tên cột trong query nguồn không rõ/trùng khi tạo bảng | Dùng alias duy nhất cho từng cột |
| `ORA-01723: zero-length columns are not allowed` | Biểu thức nguồn không suy ra được độ dài/kiểu cột phù hợp | Dùng `CAST` sang kiểu và độ dài cụ thể, nhất là `NULL` literals |
| INSERT mới vào bảng copy không có default | CTAS không mang default tương ứng | Kiểm tra `DATA_DEFAULT` và thêm khi cần |
| Dữ liệu duplicate xuất hiện sau CTAS | Thiếu PK/UNIQUE; query JOIN nhân bản hàng | Kiểm tra dữ liệu, tạo constraint phù hợp |
| Chèn khóa từ ứng dụng không còn tự sinh | Identity/sequence/trigger không được clone | Thiết kế lại cơ chế sinh khóa, tránh trùng ID |
| Truy vấn bảng copy chậm hơn nguồn | Không có index, thống kê khác, layout khác | Xem execution plan, workload, tạo index/stats hợp lý |
| User khác không đọc được bảng copy | Grants nguồn không được kế thừa | Cấp quyền tối thiểu trên bảng mới |
| Dữ liệu nhạy cảm bị lộ trong snapshot | Bảng đích thiếu policy/masking/grant phù hợp | Dừng phổ biến dữ liệu, kiểm tra security controls và quy trình tạo bản sao |
| So sánh COUNT nguồn và đích không khớp | WHERE, JOIN, nguồn tiếp tục thay đổi hoặc lỗi logic query | Dùng cùng snapshot/phạm vi và điều kiện SELECT rõ ràng |
| ROLLBACK không xóa bảng copy | CTAS là DDL, implicit commit | Quản lý object bằng DDL có chủ đích; không dùng rollback để đảo CTAS |

Đừng sửa tất cả các lỗi trên bằng cách lặp lại CTAS với `SELECT *`. Phải xác định **lỗi thuộc SELECT nguồn, quyền/DDL, dữ liệu đã nạp hay metadata bảng đích** trước khi hành động.

## 15. Tình huống nghiệp vụ cần lựa chọn đúng phương pháp

### Tình huống A — Sao lưu nhanh trước migration

Một nhóm muốn chạy:

```sql
CREATE TABLE orders_backup AS
SELECT * FROM orders;
```

**Lợi ích:** có bản chụp dữ liệu truy vấn được trong cùng database. **Giới hạn:** không phải backup phục hồi toàn hệ thống, không copy đủ constraints/index/grants/trigger và phụ thuộc cùng hạ tầng lưu trữ. Trước migration quan trọng cần một kế hoạch backup/recovery (ví dụ RMAN/Data Pump phù hợp), bảo đảm snapshot và kiểm soát môi trường.

### Tình huống B — Tạo bảng báo cáo từ JOIN

CTAS từ nhiều bảng có thể phù hợp để tạo dữ liệu báo cáo cuối kỳ, nhưng không nên thêm mọi foreign key và trigger nguồn nếu báo cáo chỉ đọc. Nên tập trung vào tên cột, kiểu dữ liệu, tính đúng đắn của aggregate, refresh strategy, indexing, quyền SELECT và timestamp của kỳ báo cáo.

### Tình huống C — Tạo bảng staging trước khi import

`WHERE 1 = 0` tạo bảng rỗng nhanh, song thiếu constraints/default có thể dẫn đến dữ liệu bẩn. Một staging table có thể **cố ý lỏng ràng buộc** để lưu cả dòng lỗi, nhưng phải có cơ chế validate trước khi đưa sang bảng nghiệp vụ. Nếu staging phải bảo đảm loại dữ liệu và uniqueness ngay khi nạp, khai báo constraints cần thiết thay vì dựa vào CTAS.

### Tình huống D — Thay thế bảng giao dịch bằng CTAS

Đây là trường hợp rủi ro cao: ứng dụng có thể dùng trigger sinh khóa, identity, grant, index, partition, policy bảo mật và khóa ngoại từ những bảng khác. Một CTAS có đủ hàng dữ liệu vẫn có thể **không tương thích với ứng dụng**. Cần migration script đầy đủ, plan cutover, kiểm tra dependency, backup và rollback strategy ở cấp triển khai. Không thực hiện đổi tên/drop bảng production chỉ dựa trên một bản CTAS.

### Tình huống E — Chia dữ liệu theo năm

```sql
CREATE TABLE lab_ctas_orders_2025 AS
SELECT order_id, customer_id, amount, status, created_at
FROM lab_ctas_orders
WHERE created_at >= DATE '2025-01-01'
  AND created_at < DATE '2026-01-01';
```

Điều kiện nửa mở giúp chọn đúng dữ liệu ngày giờ, không phụ thuộc chuyển kiểu ngầm từ text. Bảng kết quả có thể phù hợp cho phân tích, nhưng cần quyết định rõ nó là **archive, snapshot hay bảng nghiệp vụ đang hoạt động**. Nếu archive phải tuân thủ retention và chính sách bảo mật, CTAS mới chỉ là bước copy dữ liệu.

## 16. Bài thực hành: so sánh bảng nguồn và bảng CTAS

**Điều kiện:** Có quyền `CREATE TABLE` trong schema lab, đủ quota và database đã chứa bảng `LAB_CTAS_CUSTOMERS`/`LAB_CTAS_ORDERS` từ mục 3. Bài này chỉ tạo và quan sát các object của lab; không sửa bảng sản xuất.

### Phần A — Tạo bản copy và xác nhận hàng

Nếu chưa tạo copy:

```sql
CREATE TABLE lab_ctas_orders_copy AS
SELECT order_id, customer_id, amount, status, created_at, note
FROM lab_ctas_orders;
```

Chạy:

```sql
SELECT COUNT(*) AS copied_rows,
       SUM(amount) AS total_amount
FROM lab_ctas_orders_copy;
```

Với dữ liệu mẫu chưa bị thay đổi, số hàng dự kiến là **3**, tổng tiền là **235.50**. Nếu khác, xác minh các bước INSERT, CTAS và trạng thái nguồn, không giả định mẫu SQL đã được chạy từ đầu.

### Phần B — Kiểm tra kiểu dữ liệu và DEFAULT

```sql
SELECT table_name, column_name, data_type,
       data_precision, data_scale, nullable, data_default
FROM user_tab_columns
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
  AND column_name IN ('ORDER_ID', 'AMOUNT', 'STATUS', 'CREATED_AT')
ORDER BY table_name, column_name;
```

Ghi ra một bảng so sánh: `ORDER_ID`, `AMOUNT`, `STATUS` và `CREATED_AT` có kiểu và nullable thế nào? `DEFAULT 0`, `DEFAULT 'NEW'`, `DEFAULT SYSDATE` có còn được khai báo trên bảng copy hay không?

### Phần C — Kiểm tra constraints

```sql
SELECT table_name, constraint_name, constraint_type,
       status, validated
FROM user_constraints
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, constraint_type, constraint_name;
```

Xác định:

1. Bảng nguồn có PK, FK, CHECK nào?
2. Bảng đích có tự nhận PK/FK/CHECK không?
3. Những NOT NULL nào hiện có trên đích? Chúng được Oracle kế thừa theo điều kiện nào của CTAS?
4. Nếu đích cần dùng cho INSERT mới, bạn sẽ thêm constraint nào và **kiểm tra dữ liệu ra sao trước khi thêm**?

### Phần D — Kiểm tra index và trigger

```sql
SELECT table_name, index_name, uniqueness
FROM user_indexes
WHERE table_name IN ('LAB_CTAS_ORDERS', 'LAB_CTAS_ORDERS_COPY')
ORDER BY table_name, index_name;
```

Tìm index do PK và index `IDX_LAB_CTAS_ORDERS_CUSTOMER` ở nguồn. Đích có index nào ngay sau CTAS? Nếu sau đó thêm PK ở bảng đích, danh sách index thay đổi thế nào?

Nếu không tạo trigger ở nguồn trong bài lab, `USER_TRIGGERS` không có hàng là bình thường. Điều đó không làm mất ý nghĩa nguyên tắc trigger không được CTAS tự gắn sang bảng mới.

### Phần E — CTAS có điều kiện và CTAS rỗng

```sql
CREATE TABLE lab_ctas_paid_only AS
SELECT order_id, customer_id, amount
FROM lab_ctas_orders
WHERE status = 'PAID';

CREATE TABLE lab_ctas_empty_shape AS
SELECT order_id, customer_id, amount
FROM lab_ctas_orders
WHERE 1 = 0;
```

So sánh:

```sql
SELECT 'PAID_ONLY' AS copy_type, COUNT(*) AS row_count
FROM lab_ctas_paid_only
UNION ALL
SELECT 'EMPTY_SHAPE', COUNT(*)
FROM lab_ctas_empty_shape;
```

Với dữ liệu mẫu, `PAID_ONLY` có 1 hàng, `EMPTY_SHAPE` có 0 hàng. Cả hai vẫn có định nghĩa cột suy ra từ SELECT; chúng không vì thế trở thành bản sao toàn bộ constraints.

### Phần F — Viết checklist bàn giao

Giả sử `LAB_CTAS_ORDERS_COPY` sẽ thay thế nguồn trong một ứng dụng Java:

- API có dùng IDENTITY/sequence/trigger để sinh khóa không?
- Các truy vấn nào cần index và plan tương tự?
- Cột nào phải có DEFAULT hoặc NOT NULL?
- Có các foreign keys từ bảng khác tham chiếu tới nguồn không?
- Cần bảo đảm GRANT, comments, masking, audit và backup nào?
- Các job/PL/SQL packages, synonyms và views đang tham chiếu tên bảng cũ ra sao?
- Có kế hoạch kiểm thử rollback/cutover trước khi thay đổi production không?

Hãy kết luận liệu **chỉ một câu lệnh CTAS** có đủ đáp ứng bài toán thay thế bảng nghiệp vụ không; nêu rõ lý do.

## 17. Bảng ghi nhớ cuối bài

| Muốn làm gì? | CTAS có phù hợp? | Điều kiện |
| --- | --- | --- |
| Tạo bảng snapshot đọc được ngay | **Có** | Hiểu snapshot không tự cập nhật và không phải backup độc lập |
| Tạo bảng rỗng cùng danh sách cột của SELECT | **Có** với `WHERE 1=0` | Không giả định constraints/default/index tự theo |
| Tạo bảng tổng hợp từ JOIN/GROUP BY | **Có** | Định nghĩa aliases/types rõ, kiểm tra tính đúng đắn của dữ liệu |
| Clone PK/FK/UNIQUE/CHECK/DEFAULT/IDENTITY chính xác | **Không chỉ bằng CTAS** | Cần metadata/DDL bổ sung và xác minh sau tạo |
| Clone index/trigger/grants/security policies | **Không chỉ bằng CTAS** | Cần thiết kế và triển khai riêng |
| Tạo bảng mới có partition/compression/LOB storage đúng | **Có thể** với DDL thích hợp | Phải cấu hình và kiểm tra, không suy từ bảng nguồn |
| Tạo backup có thể khôi phục sau mất database/storage | **Không** | Sử dụng phương án backup/recovery được hỗ trợ |
| Thay bảng production không gián đoạn | **Không đủ** | Cần quy trình migration/cutover, dependency, quyền và kiểm thử |

```text
CREATE TABLE target AS SELECT ... FROM source
                     │
                     ▼
      CỘT + KIỂU SUY TỪ SELECT + CÁC HÀNG ĐƯỢC CHỌN
                     │
                     ▼
     KIỂM TRA BỔ SUNG TRƯỚC KHI SỬ DỤNG
          ├── PK / UNIQUE / FK / CHECK / NOT NULL
          ├── DEFAULT / IDENTITY / VIRTUAL / INVISIBLE
          ├── INDEX / TRIGGER / SEQUENCE / SYNONYM
          ├── COMMENTS / PRIVILEGES / SECURITY
          ├── TABLESPACE / PARTITION / LOB / LOGGING
          ├── STATS / BACKUP / RECOVERY
          └── SỐ HÀNG / GIÁ TRỊ / THỜI ĐIỂM SNAPSHOT
                     │
                     ▼
      BẢNG ĐÍCH ĐƯỢC XÁC NHẬN PHÙ HỢP MỤC ĐÍCH
```

**Thông điệp quan trọng nhất:** CTAS là công cụ rất mạnh để **materialize kết quả SELECT thành bảng mới**, không phải lệnh sao chép mọi thuộc tính của bảng nguồn. Khi hiểu rõ khác biệt giữa *dữ liệu*, *định nghĩa cột* và *các đối tượng/ràng buộc đi kèm*, bạn có thể dùng CTAS nhanh chóng trong môi trường Oracle mà vẫn kiểm soát tính toàn vẹn dữ liệu, bảo mật và khả năng vận hành của bảng đích.
