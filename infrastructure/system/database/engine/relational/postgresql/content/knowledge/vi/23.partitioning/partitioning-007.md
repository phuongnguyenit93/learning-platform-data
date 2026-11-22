# Khóa ngoại, ràng buộc và mức hỗ trợ theo phiên bản trong PostgreSQL Partitioning

Phân vùng (*table partitioning*) giúp một bảng logic rất lớn được lưu trên nhiều bảng vật lý nhỏ hơn. PostgreSQL có thể định tuyến dữ liệu đến phân vùng phù hợp, loại các phân vùng không liên quan khi truy vấn (*partition pruning*) và cho phép quản lý dữ liệu theo tháng, tenant hoặc dải giá trị.

Nhưng phân vùng đặt ra một câu hỏi quan trọng hơn tốc độ: **những ràng buộc dữ liệu có còn bảo vệ toàn bộ bảng logic hay chỉ bảo vệ từng phân vùng?**

Ví dụ một hệ thống hóa đơn phân vùng theo tháng:

```text
                   invoice (partitioned parent)
                          PARTITION BY RANGE (issued_on)
                               │
              ┌────────────────┼─────────────────┐
              ▼                ▼                 ▼
       invoice_2026_10   invoice_2026_11   invoice_default
          tháng 10         tháng 11          dữ liệu khác

invoice_id = 42 có thể xuất hiện ở nhiều tháng.
```

Nếu khóa chính chỉ là `invoice_id`, PostgreSQL có thể kiểm tra duy nhất toàn cục hay không? Một bảng `invoice_line` có thể tạo `FOREIGN KEY` đến bảng cha `invoice` không? `CHECK` và `NOT NULL` được truyền xuống các phân vùng ra sao? Những khả năng này thay đổi thế nào từ PostgreSQL 10, 11, 12 đến 17, 18?

**Trọng tâm bài học:**

- Phân biệt **khóa phân vùng** (*partition key*) với **khóa chính** (*primary key*) và **khóa ngoại** (*foreign key*).
- Hiểu vì sao `PRIMARY KEY`/`UNIQUE` của bảng phân vùng phải bao gồm các cột khóa phân vùng và vì sao đó **không phải global unique index**.
- Thiết kế FK từ bảng phân vùng đến bảng thường, từ bảng thường đến bảng phân vùng, và giữa hai bảng phân vùng.
- Hiểu cách `CHECK`, `NOT NULL`, partition bounds, default partitions và constraint validation tương tác.
- Nắm các mốc hỗ trợ lịch sử: **PostgreSQL 10 → 11 → 12 → 17 → 18**.
- Thực hành DDL, DML, truy vấn catalog, các tình huống lỗi chủ đích và kế hoạch migration.

Bài này thuộc chương **Phân vùng** của module *Database Engine Relational PostgreSQL*. Các ví dụ chính hướng tới **PostgreSQL 18**, đồng thời chỉ rõ các bước không chạy được trên phiên bản cũ. Tại thời điểm biên soạn tháng 11/2026, PostgreSQL **19 mới ở giai đoạn release candidate**, nên không lấy tính năng của bản thử nghiệm làm bảo đảm cho production.

> Ràng buộc chính xác ở **bảng cha phân vùng** phụ thuộc phiên bản PostgreSQL, cấu trúc partition key, index access method và loại constraint. Đừng suy luận từ việc một constraint tạo thành công trên **một leaf partition** rằng nó tự bảo vệ mọi leaf khác.

---

## 1. Phân vùng khai báo: một bảng logic, nhiều bảng vật lý

Trong **declarative partitioning**, tạo bảng cha với `PARTITION BY`:

```sql
CREATE TABLE invoice (
    invoice_id BIGINT NOT NULL,
    issued_on DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL
) PARTITION BY RANGE (issued_on);
```

Tạo các phân vùng:

```sql
CREATE TABLE invoice_2026_10
PARTITION OF invoice
FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE invoice_2026_11
PARTITION OF invoice
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
```

Truy vấn:

```sql
SELECT *
FROM invoice
WHERE issued_on >= DATE '2026-11-01'
  AND issued_on < DATE '2026-12-01';
```

Bảng cha là đối tượng logic, không lưu heap tuples của chính nó. Hàng thật nằm trong các leaf partitions. PostgreSQL định tuyến một `INSERT INTO invoice` đến phân vùng thích hợp và thường có thể prune các phân vùng không liên quan khi query có điều kiện trên khóa phân vùng.

### 1.1. Range bounds có quy tắc nửa mở

Với:

```sql
FOR VALUES FROM ('2026-10-01') TO ('2026-11-01')
```

biên dưới **bao gồm**, biên trên **không bao gồm**:

```text
2026-10-01 ≤ issued_on < 2026-11-01
```

Vì vậy ngày `2026-11-01` thuộc phân vùng tháng 11, không phải tháng 10.

### 1.2. PARTITION BY không đồng nghĩa PRIMARY KEY

```sql
PARTITION BY RANGE (issued_on)
```

chỉ định cột dùng để **chọn phân vùng**, không tự tạo `PRIMARY KEY (issued_on)`, không tự tạo unique constraint trên cột đó và không tự bảo đảm một giá trị ngày chỉ xuất hiện một lần.

### 1.3. Các kiểu phân vùng

| Kiểu | Ví dụ | Quy tắc |
|---|---|---|
| `RANGE` | `PARTITION BY RANGE (issued_on)` | Mỗi phân vùng giữ một dải giá trị |
| `LIST` | `PARTITION BY LIST (tenant_id)` | Mỗi phân vùng giữ những giá trị được liệt kê |
| `HASH` | `PARTITION BY HASH (tenant_id)` | Chọn phân vùng theo hash, modulus/remainder |

**`PARTITION BY HASH` không phải `CREATE INDEX ... USING hash`.** Một bên là cách phân phối hàng giữa các partitions, bên kia là phương pháp lập index.

## 2. Những ràng buộc dữ liệu phải phân biệt

| Loại | Mục đích | Câu hỏi khi partitioning |
|---|---|---|
| `NOT NULL` | Cấm SQL NULL ở cột | Có truyền xuống mọi partition không? |
| `CHECK` | Kiểm tra điều kiện trên một hàng | Có kế thừa? Có đồng nghĩa partition bound? |
| `PRIMARY KEY` | Định danh hàng, không NULL và duy nhất | Có phải chứa partition key? |
| `UNIQUE` | Cấm khóa trùng theo quy tắc NULL | Chỉ một partition hay toàn bảng logic? |
| `FOREIGN KEY` | Bảo vệ tham chiếu giữa bảng | Bảng nào được làm referenced/referencing? |
| `EXCLUDE` | Cấm những cặp hàng có các quan hệ xung đột | Có hỗ trợ trên parent, từ version nào? |
| Partition bound | Quy định một hàng được ở partition nào | Khi thiếu partition hoặc move row thì sao? |

Để thiết kế đúng, trước tiên xác định **ràng buộc nghiệp vụ áp dụng trong phạm vi nào**: toàn bộ hệ thống, một tenant, một tháng, hay một tập theo trạng thái.

### 2.1. Phạm vi là cốt lõi

Giả sử mã hóa đơn `invoice_id=42` xuất hiện tháng 10 và tháng 11:

- Nếu nghiệp vụ cho phép lặp ID giữa các tháng, khóa `(issued_on, invoice_id)` có thể phù hợp.
- Nếu ID phải duy nhất **toàn hệ thống bất kể tháng**, partitioning theo `issued_on` tạo ra thách thức vì parent-level unique trên `invoice_id` đơn lẻ không được hỗ trợ theo cơ chế local indexes hiện hành.

Không giải quyết xung đột nghiệp vụ bằng việc lặng lẽ thêm cột tháng vào PK nếu API và các bảng khác vẫn coi `invoice_id` là định danh duy nhất toàn cục.

## 3. Vì sao UNIQUE/PRIMARY KEY parent phải chứa partition key?

PostgreSQL tạo **partitioned index** ở bảng cha về mặt metadata, và những index vật lý tương ứng trên các phân vùng.

```text
                 UNIQUE trên parent (metadata)
                                │
                   ┌────────────┴───────────┐
                   ▼                        ▼
         unique index partition 10  unique index partition 11
             chỉ thấy hàng tháng 10     chỉ thấy hàng tháng 11
```

Một unique index trên phân vùng tháng 10 không thể tự nhìn được những giá trị đã nằm trong phân vùng tháng 11.

Do đó, một constraint UNIQUE/PK trên parent chỉ bảo đảm được tính duy nhất toàn bảng khi **cấu trúc partitioning bảo đảm các hàng có cùng unique key sẽ rơi vào cùng leaf partition**.

Với declarative partitioning, PostgreSQL yêu cầu:

1. **Tất cả các cột trong partition key đều phải xuất hiện trong UNIQUE/PRIMARY KEY của bảng cha.**
2. **Partition key không được chứa biểu thức hoặc lời gọi hàm** khi định nghĩa loại constraint parent-level đó.
3. Nếu có **nhiều tầng partitioning**, constraint có thể cần bao gồm các cột khóa của từng tầng phân vùng trong phân cấp, theo quy tắc server.

Ví dụ hợp lệ:

```sql
CREATE TABLE invoice (
    invoice_id BIGINT NOT NULL,
    issued_on DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    CONSTRAINT pk_invoice PRIMARY KEY (issued_on, invoice_id)
) PARTITION BY RANGE (issued_on);
```

Ví dụ không hợp lệ:

```sql
-- CỐ TÌNH GÂY LỖI: partition key issued_on
-- không có trong PRIMARY KEY.
CREATE TABLE invoice_bad (
    invoice_id BIGINT PRIMARY KEY,
    issued_on DATE NOT NULL
) PARTITION BY RANGE (issued_on);
```

Lỗi không phải do thiếu một index được tạo thủ công; định nghĩa PK **không đáp ứng điều kiện của partitioned table**.

## 4. PRIMARY KEY gồm partition key bảo đảm điều gì?

Với:

```sql
PRIMARY KEY (issued_on, invoice_id)
```

hai hàng này **không được cùng tồn tại**:

```text
(issued_on=2026-11-05, invoice_id=42)
(issued_on=2026-11-05, invoice_id=42)
```

Nhưng hai hàng này **được phép**, vì khóa ghép khác nhau:

```text
(issued_on=2026-10-05, invoice_id=42)
(issued_on=2026-11-05, invoice_id=42)
```

Ràng buộc chỉ nói tổ hợp `(issued_on, invoice_id)` là duy nhất. Nó **không bảo đảm `invoice_id` một mình là duy nhất toàn bảng**.

### 4.1. Khóa ghép phải xuất hiện trong mô hình dữ liệu

Nếu một line item tham chiếu hóa đơn, `invoice_line` thường cần lưu cả `issued_on` và `invoice_id` để có thể khai báo FK tới PK trên.

Việc đổi PK từ `invoice_id` sang `(issued_on, invoice_id)` là **thay đổi hợp đồng dữ liệu** của:

- Các bảng con.
- ORM entity ID/composite key mapping.
- URL API hoặc public identifier.
- Các lệnh `ON CONFLICT`.
- Cache keys và message payload.
- Chiến lược dedup/idempotency.
- JOIN và index design.

Không coi việc thêm partition key vào PK là một sửa DDL nhỏ vô hại.

### 4.2. Một ID dùng sequence có tự duy nhất toàn cục không?

`GENERATED ... AS IDENTITY` hoặc sequence có thể cấp số tăng cho nhiều phân vùng, nhưng **generator không tương đương UNIQUE constraint toàn cục**:

- Có thể chèn giá trị tường minh trong những cấu hình cho phép.
- Có thể nhập dữ liệu hoặc restore từ nguồn khác.
- Sequence có thể được điều chỉnh hoặc có nhiều nguồn sinh ID.
- Phân quyền/migration có thể làm giả định “không trùng” mất hiệu lực.

Nếu yêu cầu uniqueness tuyệt đối, hãy thiết kế ràng buộc thực sự trong phạm vi hỗ trợ, không chỉ tin vào thuật toán sinh ID.

## 5. UNIQUE trên leaf khác UNIQUE trên parent

Giả sử chưa có parent UNIQUE và ta tạo:

```sql
CREATE UNIQUE INDEX ux_invoice_2026_10_id
ON invoice_2026_10 (invoice_id);
```

Index này chỉ bảo vệ dữ liệu tháng 10. Một `invoice_id` giống hệt có thể nằm ở tháng 11.

### 5.1. Index vật lý ở từng partition

```text
invoice_2026_10: invoice_id=42   (được phép)
invoice_2026_11: invoice_id=42   (được phép)

Hai unique leaf indexes riêng biệt không thấy nhau.
```

Muốn hợp đồng toàn bảng logic:

```sql
ALTER TABLE invoice
ADD CONSTRAINT uq_invoice_date_id
UNIQUE (issued_on, invoice_id);
```

Nhưng nếu PK đã dùng chính hai cột này, thêm UNIQUE trùng mục đích thường không cần thiết và làm tăng chi phí index.

### 5.2. Không có global unique index thông thường trên partitioned table

Tính đến PostgreSQL 18, đừng giả định đã có index duy nhất lưu **tất cả `invoice_id` ở mọi partition** như một B-tree thống nhất. Parent partitioned index là cấu trúc metadata với indexes ở leaves; restriction về partition key vẫn áp dụng.

## 6. Expression partition key làm thay đổi khả năng tạo PK/UNIQUE

PostgreSQL cho phép một số expression partition keys tùy tính chất biểu thức và operator class.

Ví dụ biểu diễn ý tưởng:

```sql
CREATE TABLE sample_by_mod (
    record_id BIGINT NOT NULL,
    payload TEXT
) PARTITION BY LIST ((record_id % 4));
```

Nhưng:

```sql
-- CỐ TÌNH KHÔNG HỢP LỆ:
ALTER TABLE sample_by_mod
ADD CONSTRAINT pk_sample_by_mod PRIMARY KEY (record_id);
```

Không thể suy luận rằng chỉ vì `record_id` quyết định `record_id % 4` thì UNIQUE/PK parent được chấp nhận. Với partition key **chứa biểu thức**, PostgreSQL giới hạn việc khai báo parent-level unique/primary key.

### 6.1. Thay thế có thể cần thay đổi schema

Nếu business key toàn cục phải UNIQUE, cân nhắc:

- Partition theo chính cột business key (nếu phù hợp với truy vấn/retention).
- Dùng bảng registry **không phân vùng** với unique key toàn cục.
- Giữ một bảng lookup định danh và một bảng fact phân vùng.
- Tách định danh logic với storage key có contract minh bạch.
- Dùng một khóa tổng hợp nếu thực sự đó là tính duy nhất nghiệp vụ.

Mỗi phương án có trade-off về index size, retention, FK cost và complexity.

## 7. Thiết kế global ID bằng registry table

Một mẫu khi cần bảo đảm `external_id` không trùng bất kể tháng:

```sql
CREATE TABLE invoice_identity (
    external_id TEXT PRIMARY KEY,
    issued_on DATE NOT NULL,
    invoice_id BIGINT NOT NULL
);
```

Bảng registry có unique B-tree trên `external_id`. Giao dịch tạo hóa đơn phải phối hợp:

1. Đặt một entry trong registry.
2. Tạo hóa đơn ở partition phù hợp.
3. Cập nhật/đảm bảo mapping và rollback toàn bộ nếu lỗi.
4. Thiết kế chính sách xóa/retention để không tạo dangling mappings.

Đây là **mô hình thiết kế**, không phải đoạn SQL hoàn chỉnh đủ xử lý tất cả cạnh tranh ghi.

### 7.1. Trade-off

- Registry có thể trở thành bảng rất lớn dù bảng invoice được partition theo thời gian.
- Giữ mapping sau khi xóa partition cần retention policy rõ.
- Nếu dùng FK từ registry đến invoice, FK đó phải tham chiếu khóa hợp lệ như `(issued_on, invoice_id)` trên phiên bản hỗ trợ.
- Nếu dùng triggers hoặc application writes, phải xử lý atomicity và retries.

**Một registry có unique index thực** đáng tin hơn “SELECT để kiểm tra có tồn tại không rồi INSERT” dưới concurrency.

## 8. FOREIGN KEY có hai vai trò: referencing và referenced

Cần phân biệt hướng của FK:

```text
    child table (referencing)
      FOREIGN KEY (...)
              │
              ▼
    parent table (referenced)
      PRIMARY KEY / UNIQUE (...)
```

**Referencing table** giữ cột FK. **Referenced table** có khóa được tham chiếu, được bảo vệ bằng unique/primary key hoặc non-partial unique index đủ điều kiện.

Với partitioning, có bốn tình huống:

| Bảng giữ FK | Bảng được tham chiếu | Ý nghĩa |
|---|---|---|
| Thường | Thường | FK truyền thống |
| Phân vùng | Thường | Nhiều leaf rows tham chiếu parent thường |
| Thường | Phân vùng | Bảng thường tham chiếu khóa của logical partitioned table |
| Phân vùng | Phân vùng | Cả child và referenced đều chia partition |

Khả năng hỗ trợ không xuất hiện đồng thời trong PostgreSQL 10/11/12.

## 9. Lịch sử hỗ trợ theo major version

Bảng này nói về **declarative partitioning** của PostgreSQL core, không áp dụng máy móc cho inheritance partitioning hoặc extensions bên thứ ba.

| Version | Mốc quan trọng |
|---|---|
| **PostgreSQL 10** (2017) | Declarative RANGE/LIST partitioning ban đầu; chưa có parent-level PK/UNIQUE spanning partition tree và chưa hỗ trợ FK ở cả hai hướng với partitioned table |
| **PostgreSQL 11** (2018) | Hỗ trợ PK/UNIQUE parent khi gồm toàn bộ partition key; hỗ trợ **FK từ partitioned table đến bảng thường**; thêm HASH partitioning, default partition và row movement qua UPDATE |
| **PostgreSQL 12** (2019) | Hỗ trợ **FK tham chiếu partitioned table**; từ đó bao phủ các tình huống bảng thường hoặc bảng phân vùng tham chiếu một parent phân vùng theo các điều kiện hợp lệ |
| **PostgreSQL 13–16** | Cơ chế FK/PK/UNIQUE ở trên tiếp tục được cải thiện; các giới hạn parent unique vẫn còn; parent-level EXCLUDE chưa được hỗ trợ qua 16 |
| **PostgreSQL 17** (2024) | Thêm hỗ trợ **EXCLUDE constraint trên partitioned parent** với điều kiện chứa đầy đủ partition key và so sánh equality trên các key ấy |
| **PostgreSQL 18** (2025) | Thêm **NOT VALID FK trên partitioned tables**, thêm `NOT ENFORCED` cho CHECK/FK và các cải tiến về NOT NULL/temporal constraints; cần phân biệt các trạng thái validation/enforcement |
| **PostgreSQL 19** (tại 14/11/2026) | Đang ở **RC2**; không coi tài liệu RC là baseline production ổn định trước GA |

Các thay đổi bản minor và sửa lỗi vẫn đáng chú ý; luôn kiểm tra chính xác `server_version` và release notes của phiên bản được triển khai.

### 9.1. Kiểm tra version ngay trên database

```sql
SELECT version();

SHOW server_version;
SHOW server_version_num;
```

Ví dụ điều kiện dùng trong migration script:

```sql
SELECT current_setting('server_version_num')::integer >= 120000
    AS supports_fks_referencing_partitioned_parent;
```

Đây là **kiểm tra major feature gate**, không thay thế kiểm thử câu DDL thật, minor fixes hoặc các khác biệt của môi trường.

### 9.2. Không đối chiếu tính năng bằng công cụ psql một mình

`psql --version` phản ánh client trên máy chạy lệnh, không nhất thiết là PostgreSQL server version của database đích. Để quyết định DDL, dùng `SHOW server_version_num` trên kết nối thực.

## 10. Lab chính: một schema quản lý hóa đơn theo tháng

Các ví dụ tiếp theo dùng **PostgreSQL 12+** cho đầy đủ FK hai chiều và tốt nhất trên PostgreSQL 18. Mở database lab mới hoặc xác nhận schema này chưa có dữ liệu cần giữ.

```sql
CREATE SCHEMA IF NOT EXISTS demo_part_fk;

CREATE TABLE demo_part_fk.customer (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO demo_part_fk.customer (customer_id, customer_name)
VALUES
    (1, 'Khách A'),
    (2, 'Khách B'),
    (3, 'Khách C');
```

Bảng `customer` không phân vùng, có PK duy nhất toàn bảng.

### 10.1. Tạo bảng hóa đơn phân vùng

```sql
CREATE TABLE demo_part_fk.invoice (
    issued_on DATE NOT NULL,
    invoice_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW',

    CONSTRAINT pk_demo_invoice
        PRIMARY KEY (issued_on, invoice_id),

    CONSTRAINT fk_demo_invoice_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_part_fk.customer(customer_id),

    CONSTRAINT ck_demo_invoice_amount
        CHECK (amount >= 0),

    CONSTRAINT ck_demo_invoice_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
)
PARTITION BY RANGE (issued_on);
```

Những điểm cần chú ý:

- `issued_on` là partition key và có trong PK.
- `invoice_id` đơn lẻ **không có unique guarantee toàn cục**.
- FK `invoice.customer_id → customer.customer_id` là **FK từ bảng phân vùng đến bảng thường**, hỗ trợ từ PostgreSQL 11.
- `CHECK` và `NOT NULL` ở parent áp dụng cho các partitions.
- Cột `status` có DEFAULT, nhưng DEFAULT không phải ràng buộc cho phép giá trị: `CHECK` mới bảo vệ tập giá trị.

### 10.2. Tạo các leaf partitions

```sql
CREATE TABLE demo_part_fk.invoice_2026_10
PARTITION OF demo_part_fk.invoice
FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE demo_part_fk.invoice_2026_11
PARTITION OF demo_part_fk.invoice
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE demo_part_fk.invoice_default
PARTITION OF demo_part_fk.invoice DEFAULT;
```

Các constraint của parent sẽ được phản ánh xuống partitions theo loại constraint và quy tắc triển khai. Phần lớn indexes vật lý được tạo trên từng leaf, còn parent partitioned index không chứa heap TIDs của mọi leaf trong một cấu trúc global.

### 10.3. Chèn dữ liệu hợp lệ

```sql
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount, status)
VALUES
    (DATE '2026-10-10', 1001, 1, 450.00, 'NEW'),
    (DATE '2026-11-10', 1001, 2, 990.00, 'PAID'),
    (DATE '2026-11-12', 1002, 1, 120.00, 'NEW');
```

Lưu ý `invoice_id=1001` được dùng ở **hai tháng**, vẫn hợp lệ vì PK gồm cả `issued_on`.

### 10.4. Xem partition chứa hàng

```sql
SELECT
    tableoid::regclass AS physical_partition,
    issued_on,
    invoice_id,
    customer_id,
    amount,
    status
FROM demo_part_fk.invoice
ORDER BY issued_on, invoice_id;
```

`tableoid` giúp quan sát quan hệ vật lý chứa hàng. Không dùng `tableoid` làm khóa định danh nghiệp vụ hoặc giả định tên partition không bao giờ đổi.

## 11. Lỗi UNIQUE/PK khi trùng khóa ghép

Trên dữ liệu lab ở trên:

```sql
-- CỐ TÌNH GÂY LỖI: tổ hợp PK đã tồn tại.
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES
    (DATE '2026-11-10', 1001, 3, 600.00);
```

SQLSTATE thường là `23505` — `unique_violation`. Tổ hợp khóa `(2026-11-10,1001)` đã tồn tại.

Nhưng:

```sql
-- HỢP LỆ theo PK ghép, vì ngày khác:
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES
    (DATE '2026-11-15', 1001, 3, 600.00);
```

`invoice_id` lặp trong cùng tháng nhưng **khác ngày** vẫn được phép. Nếu nghiệp vụ muốn “invoice_id duy nhất trong cả tháng”, PK `(issued_on,invoice_id)` chưa biểu đạt đúng luật đó.

### 11.1. Chọn partition key theo phạm vi unique thực sự

Nếu luật là “mỗi tenant và tháng chỉ có một mã hóa đơn”, có thể cần cột `invoice_month` ổn định làm partition key và constraint `UNIQUE (tenant_id, invoice_month, invoice_number)`. Nếu muốn một mã duy nhất toàn đời hệ thống, ngày/tháng không được mặc định thêm vào business identity chỉ để tạo PK.

**Storage partitioning và business uniqueness phải được thiết kế cùng nhau.**

## 12. FK từ parent phân vùng đến bảng thường

FK trong `demo_part_fk.invoice`:

```sql
CONSTRAINT fk_demo_invoice_customer
FOREIGN KEY (customer_id)
REFERENCES demo_part_fk.customer(customer_id)
```

bảo đảm mỗi invoice có `customer_id` hợp lệ trong bảng customer.

Thử:

```sql
-- CỐ TÌNH GÂY LỖI: customer_id=999 không tồn tại.
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES
    (DATE '2026-11-16', 2001, 999, 50.00);
```

Lỗi thường là `23503` — `foreign_key_violation`.

### 12.1. FK được kiểm tra qua các leaf như thế nào?

Việc khai báo constraint ở **partitioned parent** là hợp đồng logic cho những row trong cây phân vùng. PostgreSQL quản lý các constraint/trigger cần thiết tương ứng với các leaf partitions để chặn giá trị tham chiếu không hợp lệ.

Không cần viết trigger ứng dụng riêng cho từng tháng chỉ vì `invoice` được phân vùng. Tuy nhiên, migration và danh mục catalog có thể hiển thị các constraint child/clones chứ không chỉ đúng một row như bảng thường.

### 12.2. FK không tự tạo index ở phía referencing

`customer.customer_id` là PK nên có index phục vụ lookup referenced key.

Nhưng cột `invoice.customer_id` ở phía referencing **không tự được tạo một index chỉ vì có FK**. Nếu cần tìm hóa đơn theo customer hoặc kiểm tra DELETE/UPDATE customer, cân nhắc:

```sql
CREATE INDEX idx_demo_invoice_customer
ON demo_part_fk.invoice (customer_id);
```

Trên bảng cha phân vùng, đây là parent partitioned index và các child indexes tương ứng. Đánh giá chi phí index trên mọi partition, không chỉ trên một bảng.

## 13. FK từ bảng thường tham chiếu parent phân vùng

Từ **PostgreSQL 12**, có thể cho một bảng thường tham chiếu PK/UNIQUE hợp lệ của parent partitioned table.

Ví dụ:

```sql
CREATE TABLE demo_part_fk.invoice_receipt (
    receipt_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_issued_on DATE NOT NULL,
    invoice_id BIGINT NOT NULL,
    received_amount NUMERIC(14, 2) NOT NULL CHECK (received_amount >= 0),

    CONSTRAINT fk_receipt_invoice
        FOREIGN KEY (invoice_issued_on, invoice_id)
        REFERENCES demo_part_fk.invoice(issued_on, invoice_id)
);
```

Chèn:

```sql
INSERT INTO demo_part_fk.invoice_receipt
    (invoice_issued_on, invoice_id, received_amount)
VALUES
    (DATE '2026-10-10', 1001, 150.00),
    (DATE '2026-11-10', 1001, 200.00);
```

Hai receipts này tham chiếu **hai hóa đơn khác nhau** vì ngày phát hành khác nhau.

### 13.1. Vì sao FK phải có cả ngày?

```sql
-- CỐ TÌNH KHÔNG HỢP LỆ: chưa có UNIQUE/PK
-- chỉ trên invoice_id ở bảng cha.
CREATE TABLE demo_part_fk.receipt_wrong (
    receipt_id BIGINT PRIMARY KEY,
    invoice_id BIGINT NOT NULL
        REFERENCES demo_part_fk.invoice(invoice_id)
);
```

PostgreSQL không thể sử dụng khóa không unique `invoice_id` làm referenced key của FK. Vấn đề không nằm ở cú pháp thiếu tên partition; đó là do parent không có unique guarantee cho một mình `invoice_id`.

### 13.2. FK referenced partition không phải search toàn cây một cách ngẫu nhiên

Nếu referenced key chứa `issued_on`, PostgreSQL có thể khai thác các quy tắc partitioning/indexing khi kiểm tra tham chiếu. Nhưng chi phí thực tế còn phụ thuộc runtime triggers, phiên bản, số phân vùng, index, caching và workload. Đọc `EXPLAIN`/thống kê và theo dõi FK checks trên môi trường đại diện nếu có bottleneck.

## 14. FK giữa hai bảng phân vùng

Ta có thể phân vùng bảng dòng hóa đơn theo cùng ngày phát hành:

```sql
CREATE TABLE demo_part_fk.invoice_line (
    issued_on DATE NOT NULL,
    invoice_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku TEXT NOT NULL,
    qty INTEGER NOT NULL CHECK (qty > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),

    CONSTRAINT pk_demo_invoice_line
        PRIMARY KEY (issued_on, invoice_id, line_no),

    CONSTRAINT fk_demo_line_invoice
        FOREIGN KEY (issued_on, invoice_id)
        REFERENCES demo_part_fk.invoice(issued_on, invoice_id)
        ON DELETE CASCADE
)
PARTITION BY RANGE (issued_on);
```

Tạo partitions:

```sql
CREATE TABLE demo_part_fk.invoice_line_2026_10
PARTITION OF demo_part_fk.invoice_line
FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE demo_part_fk.invoice_line_2026_11
PARTITION OF demo_part_fk.invoice_line
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE demo_part_fk.invoice_line_default
PARTITION OF demo_part_fk.invoice_line DEFAULT;
```

Chèn hợp lệ:

```sql
INSERT INTO demo_part_fk.invoice_line
    (issued_on, invoice_id, line_no, sku, qty, unit_price)
VALUES
    (DATE '2026-10-10', 1001, 1, 'PEN', 2, 20.00),
    (DATE '2026-10-10', 1001, 2, 'BOOK', 1, 35.00),
    (DATE '2026-11-10', 1001, 1, 'BAG', 1, 100.00);
```

Bây giờ cả referencing và referenced tables đều phân vùng. Trường hợp này thực hành đầy đủ trên PostgreSQL **12+**.

### 14.1. Sai ngày có thể làm FK thất bại dù invoice_id tồn tại

```sql
-- CỐ TÌNH GÂY LỖI:
INSERT INTO demo_part_fk.invoice_line
    (issued_on, invoice_id, line_no, sku, qty, unit_price)
VALUES
    (DATE '2026-11-11', 1001, 1, 'MISMATCH', 1, 1.00);
```

Invoice `1001` có thể có ở ngày khác, nhưng **tổ hợp `(2026-11-11,1001)` không tồn tại**. FK không tìm “đơn nào có cùng ID ở gần ngày đó”; nó tìm chính xác referenced key.

### 14.2. Co-partitioning không tự loại bỏ mọi FK cost

Hai bảng có cùng range key có thể thuận lợi cho pruning/maintenance, nhưng FK vẫn phải bảo vệ toàn vẹn dưới concurrent INSERT/UPDATE/DELETE. Không có bảo đảm “cùng tháng thì FK miễn phí”.

### 14.3. Chú ý ON DELETE CASCADE

Nếu xóa invoice hợp lệ:

```sql
-- Chỉ thực hành sau khi sao lưu dữ liệu lab:
DELETE FROM demo_part_fk.invoice
WHERE issued_on = DATE '2026-10-10'
  AND invoice_id = 1001;
```

FK `ON DELETE CASCADE` có thể xóa các lines tương ứng. Nếu còn `invoice_receipt` tham chiếu cùng invoice và FK mặc định `NO ACTION`, lệnh DELETE có thể **bị chặn**, thay vì cascade một phần rồi để database không nhất quán.

Thực hành trong transaction với `ROLLBACK` nếu cần giữ dữ liệu:

```sql
BEGIN;
DELETE FROM demo_part_fk.invoice
WHERE issued_on = DATE '2026-10-10'
  AND invoice_id = 1001;
ROLLBACK;
```

Nếu câu DELETE gây lỗi, transaction đang aborted; `ROLLBACK` vẫn là cách kết thúc đúng.

## 15. Composite FK và quy tắc NULL

Một foreign key ghép:

```sql
FOREIGN KEY (issued_on, invoice_id)
REFERENCES demo_part_fk.invoice(issued_on, invoice_id)
```

mặc định có hành vi `MATCH SIMPLE`: nếu **bất kỳ** cột referencing nào là NULL, row có thể không cần tìm referenced tuple.

Do đó, nếu luật nghiệp vụ không cho phép “tham chiếu một nửa”, đặt `NOT NULL` trên từng cột referencing, như ở bảng `invoice_line` và `invoice_receipt`.

### 15.1. MATCH FULL

`MATCH FULL` yêu cầu hoặc tất cả các cột referencing NULL, hoặc tất cả tham gia matching; không chấp nhận trộn NULL/non-NULL. Nhưng nếu luật đòi hỏi **luôn có tham chiếu**, vẫn cần `NOT NULL`.

```sql
-- Mẫu cú pháp:
FOREIGN KEY (issued_on, invoice_id)
REFERENCES demo_part_fk.invoice(issued_on, invoice_id)
MATCH FULL
```

Đây là đoạn định nghĩa constraint, không phải SQL statement độc lập để chạy.

## 16. FK action: NO ACTION, RESTRICT, CASCADE, SET NULL, SET DEFAULT

Các hành động FK vẫn mang ý nghĩa dữ liệu thông thường khi một hoặc cả hai bảng được partition:

| Hành động | Ý nghĩa |
|---|---|
| `NO ACTION` | Kiểm tra ràng buộc và từ chối khi vi phạm tại thời điểm áp dụng |
| `RESTRICT` | Ngăn thay đổi key được tham chiếu khi có row phụ thuộc theo semantics RESTRICT |
| `CASCADE` | Lan truyền DELETE/UPDATE key sang referencing rows |
| `SET NULL` | Đặt referencing columns thành NULL theo cú pháp/quy tắc |
| `SET DEFAULT` | Đặt giá trị mặc định, vẫn phải thỏa FK/constraints |

### 16.1. Cẩn thận khi FK có partition key

Nếu `issued_on` nằm trong FK và `invoice_line.issued_on NOT NULL`, một `ON DELETE SET NULL` muốn đặt cột đó thành NULL sẽ vi phạm `NOT NULL`. Vì vậy lựa chọn FK action phải tương thích toàn bộ constraints và partition routing.

### 16.2. ON UPDATE CASCADE có thể làm row movement

Khi referenced key gồm ngày phát hành và UPDATE đổi ngày khiến invoice chuyển partition, hành động cascade có thể cần cập nhật cả referencing rows, thậm chí làm chúng chuyển partition. Đây là thao tác tốn nhiều chi phí và có rủi ro lock/serialization.

Thực hành tốt: **ưu tiên partition key và identity key bất biến** nếu nghiệp vụ cho phép. Đừng xem đổi ngày phát hành là UPDATE vô hại.

## 17. CHECK và NOT NULL ở parent được kế thừa

Trong `demo_part_fk.invoice`:

```sql
amount NUMERIC(14, 2) NOT NULL,
CONSTRAINT ck_demo_invoice_amount CHECK (amount >= 0)
```

Quy tắc này áp dụng cả hàng được định tuyến sang `invoice_2026_10`, `invoice_2026_11` và `invoice_default`.

### 17.1. Thử CHECK

```sql
-- CỐ TÌNH GÂY LỖI (SQLSTATE 23514):
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES
    (DATE '2026-11-20', 2500, 1, -1.00);
```

### 17.2. Thử NOT NULL

```sql
-- CỐ TÌNH GÂY LỖI (SQLSTATE 23502):
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES
    (DATE '2026-11-20', 2501, 1, NULL);
```

### 17.3. CHECK chấp nhận UNKNOWN khi cột nullable

Nếu cột `amount` cho phép NULL, `CHECK (amount >= 0)` **không tự chặn NULL** vì biểu thức trả UNKNOWN. Muốn cấm NULL, khai báo `NOT NULL`.

### 17.4. Không bỏ constraint được thừa kế tùy tiện ở leaf

Không được drop một parent `NOT NULL`/`CHECK` inherited tại leaf như thể nó là constraint riêng. Với declarative partitioning, parent-level CHECK/NOT NULL áp dụng cho toàn cây theo các quy tắc kế thừa của phiên bản.

## 18. CHECK ở một partition riêng

Đôi khi một partition cần chính sách chặt hơn:

```sql
ALTER TABLE demo_part_fk.invoice_2026_11
ADD CONSTRAINT ck_november_positive_amount
CHECK (amount > 0);
```

Lúc này:

- Parent chỉ yêu cầu `amount >= 0`.
- Partition tháng 11 yêu cầu thêm `amount > 0`.
- Dữ liệu tháng 10 không bị tự động áp constraint mới ở tháng 11.

Đây là constraint **cục bộ**, không phải parent-level rule cho toàn bảng. Nếu API chèn invoice `amount=0` vào tháng 11, có thể bị từ chối trong khi tháng 10 cho phép.

### 18.1. Không tạo sự khác biệt vô tình

Các constraint local hợp lệ có thể hữu ích khi đang migration, nhưng làm behavior thay đổi theo tháng. Nên tài liệu hóa lý do, cách rollout và bao giờ đưa luật chung lên parent.

## 19. Partition bounds khác CHECK tùy chỉnh

Một partition:

```sql
CREATE TABLE demo_part_fk.invoice_2026_12
PARTITION OF demo_part_fk.invoice
FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
```

được engine biết **range constraint** và dùng nó cho routing/pruning. Không cần tự tạo:

```sql
CHECK (issued_on >= DATE '2026-12-01'
       AND issued_on < DATE '2027-01-01')
```

để partition có biên giới hợp lệ.

Tuy nhiên, khi **ATTACH một bảng đã có dữ liệu**, một CHECK phù hợp và đã được xác thực có thể giúp PostgreSQL chứng minh dữ liệu nằm trong bound mà không phải scan toàn bộ bảng.

### 19.1. Pruning không phải FK validation

- **Partition pruning:** planner/executor giảm số partitions phải đọc theo predicate.
- **Constraint exclusion:** kỹ thuật dùng CHECK để loại bỏ relations theo các điều kiện có thể chứng minh.
- **FK validation:** bảo đảm dữ liệu referencing có referenced key hợp lệ.
- **Unique enforcement:** bảo vệ không trùng key theo phạm vi constraint.

Bốn cơ chế liên quan tới truy vấn và constraints nhưng **không thay thế nhau**.

## 20. DEFAULT partition: tránh lỗi routing nhưng không miễn constraints

Ta đã có:

```sql
CREATE TABLE demo_part_fk.invoice_default
PARTITION OF demo_part_fk.invoice DEFAULT;
```

Nếu chèn ngày không thuộc hai tháng đã khai báo:

```sql
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES
    (DATE '2027-02-01', 3001, 1, 5.00);
```

row đi vào default partition, **vẫn phải thỏa PK/FK/CHECK/NOT NULL**.

### 20.1. Nếu không có DEFAULT?

Khi không phân vùng nào match, `INSERT INTO partitioned_parent` sẽ báo lỗi routing. PostgreSQL không tự tạo partition tháng mới trừ khi có orchestration/extension riêng.

### 20.2. DEFAULT không phải “thùng rác không kiểm tra”

Dữ liệu trong default partition vẫn thuộc logical parent, ảnh hưởng uniqueness, FK và kết quả SELECT trên parent. Giữ default partition có thể hữu ích cho ingestion nhưng cần monitor số rows và chính sách tách/di chuyển đúng bounds.

### 20.3. Thêm partition mới khi DEFAULT đang có hàng

Nếu thêm partition tháng 2/2027 mà `invoice_default` đang chứa hàng tháng 2, PostgreSQL phải bảo đảm dữ liệu không còn mâu thuẫn với partition bounds mới; operation có thể yêu cầu scan/lock hoặc di chuyển dữ liệu trước theo kế hoạch.

Không coi `CREATE TABLE ... PARTITION OF` hoặc `ATTACH PARTITION` là operation O(1) vô điều kiện khi có default partition.

## 21. ATTACH PARTITION: kiểm tra dữ liệu cũ và ràng buộc

Một cách quản lý partition là tạo bảng thường, nạp dữ liệu, chuẩn bị constraints rồi attach vào parent.

Ví dụ **chỉ dùng trên lab tách biệt** để không trùng phân vùng tháng 10/11 hiện có:

```sql
CREATE TABLE demo_part_fk.invoice_stage_2027_01
    (LIKE demo_part_fk.invoice INCLUDING DEFAULTS INCLUDING CONSTRAINTS);

ALTER TABLE demo_part_fk.invoice_stage_2027_01
ADD CONSTRAINT ck_invoice_stage_jan_bound
CHECK (
    issued_on >= DATE '2027-01-01'
    AND issued_on < DATE '2027-02-01'
);
```

Cú pháp `LIKE` trên partitioned table tạo bảng có các cột/thuộc tính được chỉ định, không tự sao chép toàn bộ tree và mọi constraint/index/FK như một phép clone magic. Cần kiểm tra schema của staging.

### 21.1. Tải dữ liệu staging hợp lệ

```sql
INSERT INTO demo_part_fk.invoice_stage_2027_01
    (issued_on, invoice_id, customer_id, amount, status)
VALUES
    (DATE '2027-01-05', 8001, 1, 100.00, 'NEW');
```

Bảng stage độc lập có thể chưa có FK/PK tương ứng nếu không được khai báo; tính đúng dữ liệu staging phải được kiểm tra trước lúc attach, không chỉ dựa vào việc INSERT đã thành công.

### 21.2. Attach vào parent

```sql
ALTER TABLE demo_part_fk.invoice
ATTACH PARTITION demo_part_fk.invoice_stage_2027_01
FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');
```

PostgreSQL cần xác minh schema, bound constraints, indexes/constraints liên quan và có thể quét dữ liệu nếu không đủ bằng chứng constraint. Với parent có DEFAULT, cũng phải xét dữ liệu trong default partition.

**Quan trọng:** `ATTACH PARTITION` không phải một cách bỏ qua PK/FK/CHECK. Nó là thao tác DDL có thể có lock và kiểm tra dữ liệu tùy tình huống.

### 21.3. Prevalidated CHECK có thể giảm scan

Một CHECK hợp lệ biểu đạt đúng bounds có thể giúp server tránh quét bảng stage để xác minh hàng thuộc partition mới. Nhưng không tự bảo đảm mọi scan/lock trên các bảng liên quan đều biến mất, nhất là khi có default partition và ràng buộc khác.

### 21.4. Không dùng CHECK NOT VALID như bằng chứng đã sạch

Một CHECK đang `NOT VALID` không chứng minh các rows cũ đều thỏa, nên không thể thay một constraint validated trong mọi bước attach optimization.

## 22. DETACH PARTITION và nguy cơ FK/retention

Ví dụ logic:

```sql
ALTER TABLE demo_part_fk.invoice
DETACH PARTITION demo_part_fk.invoice_2026_10;
```

Sau detach, bảng tháng 10 trở thành quan hệ độc lập, không còn thuộc logical parent. Điều này có thể thay đổi:

- Những rows mà query trên parent nhìn thấy.
- Dữ liệu được bảo vệ bởi FK/unique constraints thuộc partition hierarchy.
- Referential-action paths khi bảng khác đang tham chiếu.
- Retention và audit consistency.
- Các objects/constraints/indexes phụ thuộc trên partition.

**Không giả định DETACH luôn được phép hoặc không ảnh hưởng FK.** PostgreSQL có thể từ chối operation nếu dependencies/referential constraints không cho phép, và độ hỗ trợ/cách xử lý phụ thuộc phiên bản và cấu trúc.

### 22.1. Retention phải bảo vệ tham chiếu

Nếu `invoice_receipt` tham chiếu hóa đơn tháng 10, xóa/drop/detach tháng đó không chỉ là thao tác dọn file cũ. Cần quyết định xử lý receipts, lines, legal retention, trạng thái orphan và transaction đồng thời.

Có những thiết kế nên partition **cả facts và dependent tables theo cùng retention key**; có những hệ thống cần giữ registry hoặc archive keys lâu hơn invoice payload.

### 22.2. DETACH CONCURRENTLY là chủ đề riêng

Một số phiên bản hỗ trợ `DETACH PARTITION CONCURRENTLY` với hạn chế transaction, default partition và constraint/dependency riêng. Không đưa nó vào migration mà chưa xác nhận tương thích với bảng, FK, default partition và thời gian thao tác.

## 23. ON CONFLICT trên bảng phân vùng

PostgreSQL có `INSERT ... ON CONFLICT` để xử lý unique/PK conflicts trong phạm vi các constraints/indexes hợp lệ.

Với parent có PK `(issued_on, invoice_id)`:

```sql
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount, status)
VALUES
    (DATE '2026-11-10', 1001, 2, 990.00, 'PAID')
ON CONFLICT (issued_on, invoice_id)
DO NOTHING;
```

Đây là conflict target đúng theo unique key của parent. Nó **không** xử lý “invoice_id trùng nhưng ngày khác”, vì hai rows đó không xung đột unique key.

### 23.1. Không có parent UNIQUE(invoice_id)

```sql
-- CỐ TÌNH GÂY LỖI: không có unique arbiter
-- chỉ trên invoice_id của parent.
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES (DATE '2026-11-13', 1001, 1, 100.00)
ON CONFLICT (invoice_id)
DO UPDATE SET amount = EXCLUDED.amount;
```

PostgreSQL không thể tự suy ra business uniqueness trên mỗi invoice ID bất kể ngày. Cần thay conflict target hoặc thiết kế schema.

### 23.2. Không đổi partition key qua DO UPDATE mà không xét hạn chế

`ON CONFLICT DO UPDATE` trên partitioned parent có những hạn chế khi action đòi hỏi **di chuyển hàng bị conflict sang partition khác**. Không xem nó hoàn toàn tương đương `UPDATE` thông thường có row movement.

Nếu nghiệp vụ cần sửa ngày phát hành, hãy kiểm tra phiên bản, loại lệnh, triggers và các FK dependent rows, đồng thời ưu tiên mô hình partition key bất biến.

## 24. FK và khóa ràng buộc khi DELETE/UPDATE referenced row

Khi xóa hoặc sửa referenced key của một bảng, PostgreSQL phải bảo đảm không còn referencing rows vi phạm, theo `ON DELETE`/`ON UPDATE` action.

Với:

```sql
DELETE FROM demo_part_fk.customer
WHERE customer_id = 1;
```

bảng `invoice` đang có FK đến `customer`. Nếu còn hóa đơn tham chiếu và action mặc định `NO ACTION`, DELETE bị từ chối.

### 24.1. Index referencing columns thường rất quan trọng

PostgreSQL tự tạo index cho PK/UNIQUE referenced key. Nhưng ở phía referencing, bạn cần đánh giá index:

```sql
CREATE INDEX idx_demo_invoice_customer
ON demo_part_fk.invoice (customer_id);
```

Nếu index này đã được tạo trong phần thực hành trước, không chạy lại cùng tên. Trong production, quyết định dựa trên chi phí kiểm tra FK, lượng DELETE/UPDATE ở parent và truy vấn thường gặp.

### 24.2. Một FK trên parent có thể tác động nhiều partitions

DELETE/UPDATE referenced row có thể cần kiểm tra references nằm ở nhiều leaf partitions, đặc biệt khi referencing partition key không có trong điều kiện cần tìm. Số phân vùng quá lớn có thể làm catalog/trigger/planning overhead tăng.

Không chọn partitioning chỉ theo kích thước bảng mà bỏ qua tần suất bảo trì FK và số partitions.

## 25. DEFERRABLE FK khác DEFERRABLE transaction

`DEFERRABLE` trên foreign key có thể hoãn thời điểm kiểm tra theo quy tắc constraint:

```sql
CREATE TABLE demo_part_fk.review_link (
    review_id BIGINT PRIMARY KEY,
    issued_on DATE NOT NULL,
    invoice_id BIGINT NOT NULL,
    CONSTRAINT fk_review_invoice
        FOREIGN KEY (issued_on, invoice_id)
        REFERENCES demo_part_fk.invoice(issued_on, invoice_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
```

Trong một transaction:

```sql
BEGIN;

SET CONSTRAINTS fk_review_invoice DEFERRED;

-- Thực hiện các thay đổi cần bảo đảm constraint đúng khi commit.
-- Ví dụ chỉ dùng khi đã hiểu data order và rollback.

ROLLBACK;
```

`SET CONSTRAINTS` có thể ảnh hưởng các FK deferrable phù hợp. Nó **không** biến một FK sai thành hợp lệ sau commit.

### 25.1. NO ACTION khác RESTRICT về tính trì hoãn

`NO ACTION` có thể được kiểm tra muộn khi constraint được khai báo `DEFERRABLE` và điều kiện cho phép. `RESTRICT` thực thi giới hạn của nó theo semantics chặt hơn, không thể xem là hoãn cùng cách như NO ACTION.

### 25.2. Không nhầm với serializable read-only DEFERRABLE

`BEGIN ISOLATION LEVEL SERIALIZABLE READ ONLY DEFERRABLE` là **transaction characteristic cho safe snapshot**. Nó hoàn toàn khác `FOREIGN KEY ... DEFERRABLE` về thời điểm kiểm tra FK.

## 26. NOT VALID và VALIDATE CONSTRAINT: migration quan trọng

Khi thêm FK vào bảng đã có hàng triệu records, việc kiểm tra toàn bộ dữ liệu cũ ngay tại lệnh `ADD CONSTRAINT` có thể gây thời gian chờ và khóa không mong muốn.

PostgreSQL có cơ chế:

```sql
ALTER TABLE some_table
ADD CONSTRAINT fk_something
FOREIGN KEY (...)
REFERENCES other_table (...)
NOT VALID;
```

Sau đó:

```sql
ALTER TABLE some_table
VALIDATE CONSTRAINT fk_something;
```

Với `NOT VALID`, PostgreSQL **không xác minh mọi hàng cũ ngay khi ADD** nhưng vẫn **áp dụng constraint đối với các INSERT/UPDATE mới thích hợp**. `VALIDATE` kiểm tra dữ liệu cũ và đổi trạng thái validation nếu đạt.

### 26.1. Mốc phiên bản đặc biệt

Với **foreign key trên partitioned tables**, hỗ trợ `NOT VALID` ở parent là tính năng được bổ sung trong **PostgreSQL 18**. Trên PostgreSQL 12–17, không được giả định có thể dùng y hệt quy trình này cho một partitioned parent, dù FK thông thường đã được hỗ trợ.

### 26.2. Ví dụ PG18+

```sql
-- Chỉ chạy PostgreSQL 18+ trên schema lab phù hợp.
ALTER TABLE demo_part_fk.invoice_line
ADD CONSTRAINT fk_line_sku_catalog
FOREIGN KEY (sku)
REFERENCES demo_part_fk.sku_catalog(sku)
NOT VALID;
```

Ví dụ này giả định bảng `sku_catalog` **đã được tạo**. Nếu cần thực hành đầy đủ:

```sql
CREATE TABLE demo_part_fk.sku_catalog (
    sku TEXT PRIMARY KEY
);

INSERT INTO demo_part_fk.sku_catalog (sku)
VALUES ('PEN'), ('BOOK'), ('BAG');
```

Tạo catalog **trước** câu `ALTER TABLE ... ADD CONSTRAINT`. Nếu `invoice_line` đã có SKU khác trong dữ liệu lab, chúng cần được xử lý trước khi validation thành công.

Sau đó:

```sql
ALTER TABLE demo_part_fk.invoice_line
VALIDATE CONSTRAINT fk_line_sku_catalog;
```

### 26.3. NOT VALID không được dùng cho UNIQUE như với FK

Không có một giải pháp tổng quát kiểu:

```sql
-- CỐ TÌNH KHÔNG HỢP LỆ:
ALTER TABLE demo_part_fk.invoice
ADD CONSTRAINT uq_invoice_id UNIQUE (invoice_id) NOT VALID;
```

Có hai vấn đề: `UNIQUE(invoice_id)` thiếu partition key, và `NOT VALID` không phải cách trì hoãn kiểm tra uniqueness tương đương FK/CHECK.

## 27. NOT ENFORCED (PostgreSQL 18) khác NOT VALID

Đây là khác biệt quan trọng:

| Thuộc tính | Ý nghĩa chính |
|---|---|
| `NOT VALID` | Constraint được áp dụng cho dữ liệu mới/thay đổi; **chưa xác minh đầy đủ dữ liệu cũ** |
| `VALIDATE CONSTRAINT` | Kiểm tra dữ liệu cũ và xác lập trạng thái validated khi đạt |
| `NOT ENFORCED` (PG18+) | Khai báo constraint nhưng **không yêu cầu PostgreSQL thực thi kiểm tra vi phạm** cho loại hỗ trợ |
| `ENFORCED` | Constraint được thực thi theo ngữ nghĩa ràng buộc tương ứng |

PostgreSQL 18 hỗ trợ `NOT ENFORCED` cho **CHECK và FOREIGN KEY**. Nó không có nghĩa “kiểm tra sau” giống `NOT VALID`.

### 27.1. Mẫu cú pháp

```sql
-- PostgreSQL 18+; mẫu trình bày ý nghĩa, không chạy tùy tiện:
CREATE TABLE demo_part_fk.external_import (
    row_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_import_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_part_fk.customer(customer_id)
        NOT ENFORCED
);
```

Constraint đang NOT ENFORCED **không bảo vệ dữ liệu như FK được thực thi**. Không dùng nó để tuyên bố hệ thống có referential integrity nghiêm ngặt.

### 27.2. Vì sao có NOT ENFORCED?

Một số workflow cần mô tả metadata/compatibility hoặc chuyển tiếp schema qua nhiều bước, nhưng không muốn bật enforcement ngay. Việc sử dụng phải có kế hoạch validation và migration rõ.

Nếu nghiệp vụ cần chống orphan rows, dùng constraint thực thi; đừng để `NOT ENFORCED` tồn tại chỉ vì lệnh DDL “thành công”.

## 28. SQLSTATE và lỗi cần phân biệt

| SQLSTATE | Tên | Tình huống |
|---|---|---|
| `23505` | `unique_violation` | Trùng PK/UNIQUE hợp lệ |
| `23503` | `foreign_key_violation` | Referenced key không tồn tại hoặc DELETE/UPDATE vi phạm FK |
| `23514` | `check_violation` | Không thỏa CHECK; một số lỗi partition check liên quan |
| `23502` | `not_null_violation` | Cột NOT NULL nhận NULL |
| `42P16` | `invalid_table_definition` | Một số định nghĩa table/partition/PK không hợp lệ |
| `0A000` | `feature_not_supported` | Chức năng không hỗ trợ với tổ hợp DDL/phiên bản |
| `23001` | `restrict_violation` | PostgreSQL 18 đổi một số vi phạm FK `RESTRICT` sang SQLSTATE này |

Không viết application error handler dựa duy nhất trên chuỗi error tiếng Anh có thể thay đổi. PostgreSQL JDBC cung cấp `SQLException#getSQLState()` để phân loại.

### 28.1. Một statement lỗi làm transaction bị abort

```sql
BEGIN;

-- Lệnh gây lỗi chủ đích:
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES (DATE '2026-11-10', 1001, 1, 1.00);

-- Transaction sẽ ở trạng thái failed cho tới khi ROLLBACK
-- hoặc rollback về savepoint phù hợp.

ROLLBACK;
```

Nếu thử nhiều tình huống lỗi, dùng transaction riêng hoặc savepoint đúng cách, tránh nhầm lỗi `25P02` thứ cấp với nguyên nhân ban đầu.

## 29. EXCLUDE constraint trên partitioned parent: PostgreSQL 17+

**EXCLUDE** cấm những cặp hàng có tất cả các quan hệ so sánh chỉ định cùng đúng theo cách gây xung đột.

Ứng dụng đặt phòng có thể cần:

> Trong cùng một tenant và cùng room, không cho hai booking intervals giao nhau.

Từ PostgreSQL **17**, có thể khai báo EXCLUDE ở partitioned parent **nếu**:

1. Bao gồm **toàn bộ partition key columns**.
2. So sánh các partition key columns bằng **equality (`=`)**, không dùng toán tử overlap `&&` cho chính partition key.
3. Các phần còn lại dùng operator/index method phù hợp.

### 29.1. Ví dụ phân vùng theo tenant

```sql
-- Chỉ chạy trên PostgreSQL 17+ và database lab.
-- btree_gist hỗ trợ equality GiST cho kiểu scalar phổ biến.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE demo_part_fk.room_booking (
    tenant_id INTEGER NOT NULL,
    booking_id BIGINT NOT NULL,
    room_id INTEGER NOT NULL,
    during TSTZRANGE NOT NULL,

    CONSTRAINT pk_room_booking
        PRIMARY KEY (tenant_id, booking_id),

    CONSTRAINT ex_room_booking_no_overlap
        EXCLUDE USING gist (
            tenant_id WITH =,
            room_id WITH =,
            during WITH &&
        )
)
PARTITION BY LIST (tenant_id);

CREATE TABLE demo_part_fk.room_booking_t1
PARTITION OF demo_part_fk.room_booking FOR VALUES IN (1);

CREATE TABLE demo_part_fk.room_booking_t2
PARTITION OF demo_part_fk.room_booking FOR VALUES IN (2);
```

Ở đây partition key `tenant_id` xuất hiện trong EXCLUDE với operator `=`. Hai bookings cùng tenant và room có intervals overlap sẽ bị chặn; những tenant khác nhau vào các partitions khác nhau, và operator equality trên tenant phản ánh ranh giới đó.

### 29.2. Trường hợp không đúng: partition theo thời gian bắt đầu nhưng cấm overlap xuyên tháng

Giả sử phân vùng bằng `booking_start` theo tháng, còn luật muốn cấm **mọi khoảng thời gian overlap bất kể ngày bắt đầu**. Một EXCLUDE chỉ kiểm tra leaf partitions có thể bỏ sót các khoảng chồng chéo ở hai tháng.

Thêm partition key vào EXCLUDE với equality có thể làm luật mới chỉ cấm hàng có **cùng booking_start**, không còn là “cấm mọi overlap”. Vì vậy không tự kết luận parent EXCLUDE giải quyết được mọi bài toán thời gian cắt qua partition boundaries.

### 29.3. Tính năng version-specific

Trước PostgreSQL 17, parent-level EXCLUDE spanning partitioned table không được hỗ trợ theo cơ chế này; có thể khai EXCLUDE trên từng leaf, nhưng chỉ bảo vệ phạm vi leaf. Từ 17+, các điều kiện về partition key vẫn là bắt buộc.

## 30. Temporal constraints ở PostgreSQL 18: đừng nhầm với PK thường

PostgreSQL 18 thêm các cú pháp liên quan **temporal primary/unique keys** và **temporal foreign keys**, ví dụ `WITHOUT OVERLAPS` và `PERIOD`.

Điểm cần ghi nhớ trong bài partitioning:

- Các tính năng temporal constraints có **quy tắc riêng** về range/multirange và toán tử overlap.
- Chúng **không xóa bỏ mọi giới hạn về partition key** của parent-level constraints.
- Không thay PK/FK thông thường bằng temporal constraint mà không chứng minh đúng business semantics.
- Khi triển khai trên PG18, đọc tài liệu của đúng minor version, loại partition key và cách constraint được tạo trên tree.

### 30.1. Ý nghĩa không đổi

Một PK thời gian biểu đạt “các khoảng hiệu lực của cùng identity không overlap”, khác với PK scalar `(issued_on, invoice_id)` chỉ cấm trùng chính xác hai giá trị.

Nếu nghiệp vụ chỉ cần một hóa đơn có ID và ngày phát hành, dùng composite scalar PK bình thường; đừng thêm temporal syntax chỉ vì server mới hỗ trợ.

## 31. Deferrable UNIQUE và ON CONFLICT

PostgreSQL hỗ trợ khái niệm deferrable constraints, nhưng **ON CONFLICT DO UPDATE** yêu cầu arbiter index/constraint thích hợp và không xử lý mọi dạng deferred uniqueness như một index unique immediate.

Với partitioned table:

- Constraint phải đáp ứng partition-key restriction.
- Arbiter phải phù hợp với conflict target.
- Tránh suy diễn từ một unique leaf index sang unique arbiter của parent.
- Các thay đổi partition key trong DO UPDATE còn có hạn chế row movement.

Nếu workflow yêu cầu idempotent upsert, thường chọn một **unique key đơn giản, được kiểm tra ngay** với partition key đúng, hoặc một registry table unpartitioned để bảo vệ business ID toàn cục.

## 32. Multi-level partitioning: mọi tầng đều liên quan

Ví dụ logic:

```text
invoice
PARTITION BY RANGE (issued_on)
    │
    └── invoice_2026_11
        PARTITION BY HASH (tenant_id)
            │
            ├── remainder 0
            └── remainder 1
```

Nếu định nghĩa một parent-level PK, nó phải đáp ứng quy tắc **tất cả partition key columns trong toàn partition hierarchy liên quan**, không chỉ khóa ở root.

Một thiết kế có thể cần:

```sql
PRIMARY KEY (issued_on, tenant_id, invoice_id)
```

nếu hai tầng thực sự phân vùng theo `issued_on` và `tenant_id`. Thiếu `tenant_id` có thể không đủ để đảm bảo uniqueness ở các hash leaves của cùng tháng.

### 32.1. Cẩn thận với expression subpartition key

Nếu một tầng sử dụng biểu thức partition key, nó có thể khiến việc khai báo parent-level PK/UNIQUE bị giới hạn. Đừng vẽ tree nhiều tầng rồi thêm PK sau cùng mà không kiểm tra DDL feasibility ngay từ đầu.

## 33. Bảng constraint metadata ở parent và leaf

PostgreSQL lưu thông tin quan hệ, partition và constraint trong catalog.

### 33.1. Xem cây partition

```sql
SELECT *
FROM pg_partition_tree('demo_part_fk.invoice'::regclass);
```

Hàm `pg_partition_tree` được hỗ trợ trên PostgreSQL hiện đại (từ 12); không chạy trên PG10/11.

Kết quả cung cấp các quan hệ trong tree, quan hệ cha gần nhất, mức phân cấp và thông tin leaf.

### 33.2. Xem ranh giới từng partition

```sql
SELECT
    c.oid::regclass AS relation_name,
    c.relkind,
    pg_get_expr(c.relpartbound, c.oid) AS partition_bound
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'demo_part_fk'
  AND c.relispartition
ORDER BY c.relname;
```

`relkind='p'` thường biểu thị partitioned table; `relkind='r'` là ordinary table. Nếu một partition là subpartitioned parent, nó cũng có thể có relkind `p`.

### 33.3. Xem constraints và convalidated

```sql
SELECT
    con.conrelid::regclass AS on_table,
    con.conname,
    con.contype,
    con.convalidated,
    con.condeferrable,
    con.condeferred,
    CASE
        WHEN con.confrelid <> 0
        THEN con.confrelid::regclass::text
        ELSE NULL
    END AS referenced_table,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
JOIN pg_namespace AS ns ON ns.oid = con.connamespace
WHERE ns.nspname = 'demo_part_fk'
ORDER BY on_table, conname;
```

`contype` phân loại:

| Giá trị | Constraint |
|---|---|
| `p` | PRIMARY KEY |
| `u` | UNIQUE |
| `f` | FOREIGN KEY |
| `c` | CHECK |
| `x` | EXCLUDE |
| `n` | NOT NULL trong PostgreSQL 18+ theo catalog mới |

Trên các phiên bản cũ, NOT NULL không được biểu diễn như vậy ở `pg_constraint`. Không sử dụng cột phiên bản mới trong query chạy trên server cũ nếu chưa kiểm tra.

### 33.4. Các constraint clones có liên kết ra sao?

Trong PostgreSQL hiện đại, catalog như `pg_constraint.conparentid` có thể cho thấy constraint child được kế thừa/clone từ parent constraint. Đừng đánh giá “có N dòng FK trong catalog nghĩa là ứng dụng định nghĩa N foreign keys khác nhau” mà không hiểu partition hierarchy.

```sql
SELECT
    con.oid,
    con.conrelid::regclass AS on_table,
    con.conname,
    con.conparentid,
    con.convalidated
FROM pg_constraint AS con
WHERE con.connamespace = 'demo_part_fk'::regnamespace
ORDER BY con.conrelid::regclass::text, con.conname;
```

Kiểm tra version catalog và quyền đọc hệ thống; tránh xây migration chỉ dựa vào tên tự động sinh nếu schema có thể thay đổi qua upgrade.

## 34. PostgreSQL 18: đọc trạng thái conenforced

PostgreSQL 18 bổ sung catalog `pg_constraint.conenforced` để phản ánh enforcement status của constraint phù hợp.

```sql
-- Chỉ PostgreSQL 18+:
SELECT
    conrelid::regclass AS on_table,
    conname,
    contype,
    convalidated,
    conenforced,
    pg_get_constraintdef(oid)
FROM pg_constraint
WHERE connamespace = 'demo_part_fk'::regnamespace
ORDER BY on_table, conname;
```

Đây là lý do một công cụ migration/inspection cần phân biệt **đã validate** với **có đang enforce**. Không truy vấn `conenforced` trên PG17 rồi kết luận catalog bị hỏng.

## 35. Foreign key index: nơi chi phí thường bị đánh giá thấp

Một parent FK với hàng trăm partitions có thể tạo nhiều đối tượng constraint/trigger theo cơ chế triển khai. Các thao tác:

- Thêm ràng buộc FK cho cây hiện có.
- Thêm leaf partition mới.
- Xóa referenced row có nhiều children.
- Thay đổi key được tham chiếu.
- DETACH/DROP partitions cũ.
- Restore schema/dump.

đều cần được benchmark và lập kế hoạch theo số partitions và số hàng tham chiếu.

### 35.1. Chọn index cho FK nhiều cột

Với:

```sql
FOREIGN KEY (issued_on, invoice_id)
REFERENCES invoice(issued_on, invoice_id)
```

một index referencing thường phù hợp:

```sql
CREATE INDEX idx_line_invoice_fk
ON demo_part_fk.invoice_line (issued_on, invoice_id);
```

Nhưng vì `invoice_line` đã có PK `(issued_on, invoice_id, line_no)`, **PK B-tree có prefix hai cột này** và có thể đáp ứng nhiều kiểu lookup FK; không nhất thiết cần thêm index trùng prefix. Kiểm tra query patterns trước khi giữ index.

### 35.2. FK không nhất thiết phải trùng partition strategy

Một referenced parent có thể partition theo thời gian còn referencing table theo tenant, miễn FK đúng và phiên bản hỗ trợ. Nhưng chi phí tra cứu/scan có thể cao hơn nếu không prune được theo tham số FK.

Chọn đồng nhất partition keys khi có lợi về lifecycle/query, **không coi đó là điều kiện pháp lý bắt buộc của mọi FK**.

## 36. Update partition key và tính nguyên tử

Từ PostgreSQL 11, PostgreSQL hỗ trợ `UPDATE` khiến một row chuyển từ partition cũ sang partition mới khi điều kiện phù hợp.

Ví dụ lab:

```sql
BEGIN;

UPDATE demo_part_fk.invoice
SET issued_on = DATE '2026-11-25'
WHERE issued_on = DATE '2026-11-12'
  AND invoice_id = 1002;

ROLLBACK;
```

Vì `issued_on` nằm trong PK, sửa nó là **sửa identity key đối với FK**. Nếu có referencing rows, action như `NO ACTION` có thể chặn UPDATE hoặc `ON UPDATE CASCADE` cần xử lý phụ thuộc.

### 36.1. Row movement không thay FK semantics

PostgreSQL không được chuyển row rồi tự bỏ qua ràng buộc chỉ vì đích là partition khác. Đích phải thuộc bound hợp lệ, thỏa các constraints và tiếp tục bảo đảm references.

### 36.2. Concurrency

Row movement có những trường hợp cạnh tranh với DELETE/UPDATE ở session khác và có thể gây serialization-related errors. Ứng dụng cần transaction boundary, retry policy và idempotency đúng, không chỉ ghi một câu UPDATE rồi giả định không bao giờ xảy ra conflict.

## 37. Thêm một constraint trên parent: tác động tới mọi leaf

Nếu muốn thêm luật trạng thái:

```sql
ALTER TABLE demo_part_fk.invoice
ADD CONSTRAINT ck_invoice_status_strict
CHECK (status IN ('NEW', 'PAID', 'CANCELLED'));
```

Parent đã có CHECK tương tự trong lab, nên câu trên là ví dụ **constraint trùng mục đích**, không cần thực thi thật. Quan trọng là DDL ở parent có thể:

- Phải kiểm tra dữ liệu cũ trên nhiều partitions.
- Cần locks trong thời gian thay đổi schema.
- Truyền constraint xuống leaves.
- Ảnh hưởng writers concurrent.
- Phải phối hợp với partition thêm mới sau này.

### 37.1. CHECK NOT VALID có thể hỗ trợ migration

```sql
ALTER TABLE demo_part_fk.invoice
ADD CONSTRAINT ck_invoice_amount_ceiling
CHECK (amount <= 100000000)
NOT VALID;
```

Các INSERT/UPDATE mới phải thỏa CHECK enforced, nhưng existing rows chưa được scan toàn bộ ở bước ADD. Khi đã làm sạch dữ liệu:

```sql
ALTER TABLE demo_part_fk.invoice
VALIDATE CONSTRAINT ck_invoice_amount_ceiling;
```

Hỗ trợ và chi tiết khóa/propagation của từng thao tác phụ thuộc phiên bản; kiểm thử trên staging với số partitions tương đương trước production.

## 38. Chuyển từ bảng thường sang bảng phân vùng

Một bảng thường có thể đang có:

```sql
PRIMARY KEY (invoice_id)
```

và nhiều FK khác tham chiếu `invoice_id`. Nếu phân vùng theo ngày:

```sql
PARTITION BY RANGE (issued_on)
```

thì không thể tạo cùng PK `(invoice_id)` trên parent theo quy tắc hiện hành.

### 38.1. Vấn đề cần giải quyết trước migration

1. **ID có phải duy nhất toàn cục không?**
2. **Khóa phân vùng là ngày phát hành hay ngày tạo record?**
3. **Các bảng con có biết ngày tương ứng không?**
4. **Tất cả FK có thể chuyển sang composite key không?**
5. **API/ORM có thể xử lý composite identity không?**
6. **Có cần giữ lookup bằng invoice_id đơn lẻ không?**
7. **Có bảng registry hoặc lookup nào được dùng làm authority không?**
8. **Retention có xóa referenced rows trước referencing rows không?**
9. **Version đích có hỗ trợ FK đầy đủ và NOT VALID migration không?**
10. **Có thể chạy dual-write/backfill/validation an toàn không?**

### 38.2. Quy trình migration định hướng

```text
Khảo sát schema + FK graph
           │
           ▼
Chọn khóa partition & business identity
           │
           ▼
Thiết kế PK/UNIQUE hợp lệ trên parent
           │
           ▼
Tạo parent + partitions + constraints
           │
           ▼
Backfill dữ liệu và kiểm tra uniqueness
           │
           ▼
Tạo/chuyển FK theo version hỗ trợ
           │
           ▼
Validation dữ liệu và test concurrency
           │
           ▼
Cutover ứng dụng có kiểm soát
           │
           ▼
Giám sát FK errors, latency, DDL/locks
```

Không có một câu `ALTER TABLE original PARTITION BY ...` biến bảng thường thành partitioned parent tương đương tự động trong PostgreSQL hiện hành. Migration cần tạo cấu trúc mới hoặc kiến trúc thay thế, và phải giữ toàn vẹn dữ liệu trong giai đoạn cutover.

## 39. Những sai lầm khi dùng trigger thay constraint

Khi gặp giới hạn parent-level UNIQUE(invoice_id), có người đề xuất trigger:

```text
BEFORE INSERT:
  SELECT 1 FROM invoice WHERE invoice_id = NEW.invoice_id;
  Nếu không có: cho INSERT.
```

Đây **không đủ** để bảo đảm uniqueness khi có hai transaction đồng thời:

1. Transaction A kiểm tra và thấy chưa có ID.
2. Transaction B kiểm tra và cũng thấy chưa có ID.
3. Cả hai chèn vào các partitions khác nhau.
4. Không có unique constraint toàn cục nào bắt một trong hai phải thất bại.

### 39.1. Nếu thật sự cần global invariant

Phải dùng thiết kế có đồng bộ/concurrency control đáng tin như registry table unique, khóa cụ thể với transaction protocol được chứng minh đúng, hoặc một schema partition strategy khác.

**Trigger không tự biến một phép SELECT kiểm tra tồn tại thành serializable uniqueness enforcement.**

## 40. Phân vùng bằng tenant_id: một phương án tự nhiên cho unique theo tenant

Nếu business key là “`order_code` duy nhất trong một tenant”, phân vùng theo tenant có thể hài hòa với PK/UNIQUE:

```sql
CREATE TABLE demo_part_fk.tenant_order (
    tenant_id INTEGER NOT NULL,
    order_code TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    CONSTRAINT pk_tenant_order PRIMARY KEY (tenant_id, order_code)
)
PARTITION BY HASH (tenant_id);
```

Tạo hash partitions:

```sql
CREATE TABLE demo_part_fk.tenant_order_p0
PARTITION OF demo_part_fk.tenant_order
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE demo_part_fk.tenant_order_p1
PARTITION OF demo_part_fk.tenant_order
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE demo_part_fk.tenant_order_p2
PARTITION OF demo_part_fk.tenant_order
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE demo_part_fk.tenant_order_p3
PARTITION OF demo_part_fk.tenant_order
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

Đây là ví dụ **PostgreSQL 11+**, vì hash partitioning và parent PK hỗ trợ từ 11.

### 40.1. Hai tenant được dùng cùng mã order

```sql
INSERT INTO demo_part_fk.tenant_order (tenant_id, order_code, amount)
VALUES
    (1, 'A001', 100),
    (2, 'A001', 200);
```

Hợp lệ vì khóa ghép khác nhau.

### 40.2. Trong cùng tenant, mã order không thể trùng

```sql
-- CỐ TÌNH GÂY LỖI:
INSERT INTO demo_part_fk.tenant_order (tenant_id, order_code, amount)
VALUES (1, 'A001', 300);
```

Parent PK bảo vệ uniqueness của cặp `(tenant_id,order_code)` toàn tree, nhờ các hàng cùng tenant luôn được định tuyến đến cùng hash partition.

## 41. FOREIGN KEY đến bảng phân vùng HASH

Từ PG12+, có thể:

```sql
CREATE TABLE demo_part_fk.tenant_order_note (
    note_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    order_code TEXT NOT NULL,
    note_text TEXT NOT NULL,

    CONSTRAINT fk_note_tenant_order
        FOREIGN KEY (tenant_id, order_code)
        REFERENCES demo_part_fk.tenant_order(tenant_id, order_code)
);
```

Chèn hợp lệ:

```sql
INSERT INTO demo_part_fk.tenant_order_note
    (tenant_id, order_code, note_text)
VALUES
    (1, 'A001', 'Giao hàng nhanh');
```

Sai tenant:

```sql
-- CỐ TÌNH GÂY LỖI (không có order 3/A001):
INSERT INTO demo_part_fk.tenant_order_note
    (tenant_id, order_code, note_text)
VALUES
    (3, 'A001', 'Sai khóa tenant');
```

Điều quan trọng là FK **mang tenant_id**, tránh tham chiếu nhầm một order của tenant khác chỉ vì order_code giống nhau.

## 42. LIST partitioning và phạm vi khóa

Với LIST:

```sql
CREATE TABLE demo_part_fk.tenant_setting (
    tenant_id INTEGER NOT NULL,
    setting_name TEXT NOT NULL,
    setting_value TEXT NOT NULL,
    CONSTRAINT uq_setting_per_tenant
        UNIQUE (tenant_id, setting_name)
)
PARTITION BY LIST (tenant_id);

CREATE TABLE demo_part_fk.tenant_setting_t1
PARTITION OF demo_part_fk.tenant_setting FOR VALUES IN (1);

CREATE TABLE demo_part_fk.tenant_setting_t2
PARTITION OF demo_part_fk.tenant_setting FOR VALUES IN (2);

CREATE TABLE demo_part_fk.tenant_setting_default
PARTITION OF demo_part_fk.tenant_setting DEFAULT;
```

`UNIQUE (tenant_id, setting_name)` có thể được parent thực thi nhờ tenant_id là partition key. `UNIQUE (setting_name)` riêng không được chấp nhận trên parent vì thiếu tenant_id.

### 42.1. DEFAULT partition có thể chứa nhiều tenant

Unique index trong default partition vẫn bảo vệ tổ hợp `(tenant_id, setting_name)`, không chỉ tên setting. Khi chuyển tenant ra partition chuyên biệt, hệ thống cần bảo đảm dữ liệu/bounds không trùng và constraints tiếp tục hợp lệ.

## 43. Partition bounds, NULL và routing

Một số quy tắc tùy partition strategy:

- `RANGE` thường không nhận NULL partition key theo bounds dạng FROM/TO, có thể cần DEFAULT nếu muốn route NULL.
- `LIST` có thể chỉ định giá trị NULL theo quy tắc list partitioning.
- `HASH` định tuyến theo hash key, với quy tắc xử lý NULL của server.
- `NOT NULL` trên partition key là yêu cầu nghiệp vụ nên áp nếu NULL không hợp lệ.

Ví dụ parent `invoice.issued_on NOT NULL` bảo đảm không có hóa đơn thiếu ngày, bất kể default partition có nhận được một số giá trị khác không.

### 43.1. Default partition không làm null tự hợp lệ

Nếu `issued_on NOT NULL`, `INSERT ... issued_on=NULL` sẽ bị từ chối theo constraint, không tự chuyển thành “unknown month” trong default.

## 44. FOREIGN TABLE làm partition: kiểm tra constraint ở đâu?

PostgreSQL cho phép những cấu trúc với **foreign tables** làm partitions trong một số hoàn cảnh. Nhưng foreign table chứa dữ liệu do FDW/remote system quản lý, và các khai báo CHECK/NOT NULL ở foreign table **có thể không được PostgreSQL core thực thi trên dữ liệu ở remote**.

Đây là điểm rất quan trọng:

> **Đừng tin dữ liệu remote chỉ vì local foreign table khai một CHECK trông hợp lệ.**

Nếu remote source cho phép dữ liệu vi phạm partition bound hoặc constraint, những giả định mà planner dùng để tối ưu có thể trở thành sai, dẫn đến hành vi không mong muốn.

### 44.1. FK/unique trên foreign partitions có giới hạn riêng

Không giả định mọi parent FK/unique/index/constraint mechanism với ordinary local partitions cũng áp dụng không thay đổi cho foreign table partitions. Tài liệu `CREATE FOREIGN TABLE` và FDW cụ thể phải là nguồn quyết định; migration cần kiểm tra ràng buộc ở remote.

## 45. RLS, quyền và constraints

Row-Level Security (RLS) giới hạn những hàng user được xem/chỉnh, nhưng không thay PK/UNIQUE/FK.

Ví dụ một FK phải bảo vệ dữ liệu ngay cả khi referencing user không được xem referenced row theo RLS; PostgreSQL có cơ chế thực thi integrity riêng để tránh làm sai toàn vẹn dữ liệu.

### 45.1. Không dùng FK thay authorization

Một row có `tenant_id=2` và FK hợp lệ đến một order của tenant 2 không có nghĩa user tenant 1 được phép truy cập row đó. Authorization vẫn cần application scoping, GRANT/RLS và chính sách role.

### 45.2. Unique errors có thể tiết lộ sự tồn tại

Một INSERT báo duplicate key có thể cho client suy ra một business ID đã tồn tại, dù SELECT bị RLS chặn. Không đưa nguyên thông báo DB error chứa dữ liệu nhạy cảm ra API công khai; xử lý lỗi và rate limit phù hợp.

## 46. Partition pruning và FK không phải hai nút bật tắt độc lập về thiết kế

Khi FK tham chiếu PK có chứa partition key, câu SQL theo composite key thường có điều kiện phù hợp để prune:

```sql
SELECT *
FROM demo_part_fk.invoice
WHERE issued_on = DATE '2026-11-10'
  AND invoice_id = 1001;
```

Nhưng API chỉ biết `invoice_id` có thể phải dò nhiều phân vùng:

```sql
SELECT *
FROM demo_part_fk.invoice
WHERE invoice_id = 1001;
```

Và query này cũng có thể trả **nhiều hóa đơn** nếu invoice_id lặp giữa ngày/tháng.

**Thiết kế partition key, business identity, FK và mẫu truy vấn cần nhất quán**, không phải bốn quyết định tách biệt.

### 46.1. Pruning không có nghĩa FK được bỏ qua

Ngay khi query chỉ đọc một partition, FK vẫn áp dụng các nguyên tắc toàn vẹn dữ liệu khi INSERT/UPDATE/DELETE. Optimization không phải cơ chế “skip integrity checks”.

## 47. Index trên parent là virtual; indexes trên leaves là physical

Ví dụ:

```sql
CREATE INDEX idx_invoice_status
ON demo_part_fk.invoice (status);
```

PostgreSQL có thể tạo partitioned index ở parent và các indexes thực trên những leaf partitions phù hợp. Khi thêm partition mới, hệ thống xử lý index tương ứng theo quy tắc.

### 47.1. CONCURRENTLY và parent partitioned index

Trên nhiều phiên bản PostgreSQL, `CREATE INDEX CONCURRENTLY` không được hỗ trợ trực tiếp trên **partitioned parent** theo cùng cách bảng thường. Một chiến lược migration là:

1. Tạo parent index dạng `ON ONLY` (invalid/incomplete).
2. Tạo index ở từng leaf bằng `CREATE INDEX CONCURRENTLY` nếu hỗ trợ.
3. `ALTER INDEX ... ATTACH PARTITION` để gắn child indexes.
4. Khi đủ children, parent index được đánh dấu valid.

Với **UNIQUE/PRIMARY KEY** cần cẩn trọng hơn nữa về constraints và tính hợp lệ. Không copy nguyên kế hoạch một index thường sang PK mà không kiểm tra phiên bản và dependencies.

### 47.2. Tạo index không thay unique business scope

Một `CREATE INDEX (invoice_id)` trên partitioned parent chỉ hỗ trợ lookup, **không** biến `invoice_id` thành unique toàn cục.

## 48. Thời gian khóa khi ALTER TABLE ở cây phân vùng

Các operation có thể cần lock theo độ mạnh khác nhau:

- `ADD CONSTRAINT`.
- `VALIDATE CONSTRAINT`.
- `ATTACH PARTITION`.
- `DETACH PARTITION`.
- `CREATE INDEX`/`ATTACH INDEX PARTITION`.
- `DROP CONSTRAINT`.
- `UPDATE` khiến row movement.

Không có quy tắc “vì bảng cha không chứa dữ liệu nên DDL trên parent O(1) và không lock leaves”. Một DDL phải điều phối metadata và leaf objects; validation có thể scan dữ liệu.

### 48.1. Giám sát

```sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    left(query, 180) AS sql_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

Nếu DDL bị chờ, xem loại lock và blocking transactions theo quy trình DBA. Không kill transaction khác tùy tiện chỉ vì migration chậm.

## 49. SQLSTATE thay đổi giữa versions: lưu ý ứng dụng

PostgreSQL 18 có thay đổi cách báo SQLSTATE cho một số **RESTRICT FK violations**, từ `23503` sang `23001`.

Nếu Java code:

```java
if ("23503".equals(e.getSQLState())) {
    // Foreign key violation
}
```

được nâng lên PG18, logic có thể bỏ sót trường hợp RESTRICT violation nếu chỉ hard-code một giá trị.

Giải pháp là dựa trên **loại constraint action và SQLSTATE đã được version-verify**, đồng thời có test integration cho các trường hợp:

- Insert child không có parent.
- Delete referenced parent khi child còn tồn tại với `NO ACTION`.
- Delete referenced parent khi child còn tồn tại với `RESTRICT`.
- Cascade/SET NULL/SET DEFAULT.
- Constraint deferred/validated.

Không bắt mọi lỗi class `23` rồi xử lý như nhau; uniqueness, FK, CHECK, NOT NULL có ý nghĩa nghiệp vụ khác.

## 50. JDBC: bind đầy đủ composite FK

Trong Java:

```java
String sql = """
    INSERT INTO demo_part_fk.invoice_line
      (issued_on, invoice_id, line_no, sku, qty, unit_price)
    VALUES (?, ?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, java.time.LocalDate.of(2026, 11, 10));
    ps.setLong(2, 1001L);
    ps.setInt(3, 1);
    ps.setString(4, "SKU-01");
    ps.setInt(5, 2);
    ps.setBigDecimal(6, new java.math.BigDecimal("10.00"));

    ps.executeUpdate();
}
```

Nếu `issued_on` trong referencing row sai, FK sẽ từ chối dù `invoice_id` tồn tại ngày khác.

### 50.1. Tránh ghép ngày làm text tự do

Dùng bind `DATE` đúng kiểu JDBC/PostgreSQL, không để application tùy tiện trộn local timezone và timestamp khi thiết kế partition key.

Nếu partitioning dựa trên `TIMESTAMPTZ` theo UTC, phải thống nhất khoảng ngày/tháng và timezone. Không tạo tháng theo local date ở ứng dụng nhưng bounds theo UTC mà không chứng minh chúng tương ứng.

### 50.2. Composite key trong ORM

Nếu ORM mapping dùng `@Id` chỉ trên `invoice_id` trong khi PK thực là `(issued_on,invoice_id)`, cache identity có thể nhập nhằng và update/delete nhầm hàng.

Thiết kế entity composite ID đầy đủ và repository methods có tham số partition key. Không hy sinh correctness chỉ vì ORM mặc định thích scalar ID.

## 51. Các migration tests nên có

Một suite test tích hợp cho schema phân vùng nên thử:

1. Insert ở từng partition có bound đúng.
2. Insert ngoài bounds khi không có DEFAULT.
3. Insert ngoài bounds khi có DEFAULT.
4. Duplicate PK **trong cùng** partition.
5. Same invoice_id **khác** partition key.
6. Insert FK hợp lệ từ partitioned referencing parent.
7. Insert FK sai với referenced ordinary table.
8. Insert FK hợp lệ đến partitioned referenced parent.
9. FK sai một thành phần composite key.
10. DELETE referenced row với child còn tồn tại.
11. `ON DELETE CASCADE` khi được khai báo.
12. `ON UPDATE` làm thay đổi partition key.
13. CHECK/NOT NULL inherited và local CHECK.
14. Attach partition có dữ liệu cũ hợp lệ.
15. Attach partition có dữ liệu sai bound.
16. Default partition có dữ liệu giao với partition mới.
17. FK validation `NOT VALID` trên PG18+.
18. `NOT ENFORCED` chỉ khi version/contract cho phép.
19. Concurrent INSERT cùng business key ở hai partitions.
20. Restore/migration lên major version mục tiêu.

Không cần chạy tất cả trên production; nên thực hiện trên staging/test database với schema và dữ liệu đại diện.

## 52. Bài tập 1: PK có hợp lệ không?

Bảng:

```sql
CREATE TABLE event_store (
    event_id BIGINT,
    event_day DATE NOT NULL,
    PRIMARY KEY (event_id)
) PARTITION BY RANGE (event_day);
```

**Câu hỏi:** có tạo thành công trên PostgreSQL 18 không?

**Đáp án:** không. `event_day` là partition key nhưng không có trong PK. Một định nghĩa hợp lệ về mặt restriction là `PRIMARY KEY (event_day,event_id)`, với lưu ý nó không bảo đảm `event_id` global unique.

## 53. Bài tập 2: uniqueness chỉ trên mỗi partition

Có hai partitions tháng 10 và tháng 11, mỗi leaf đều có:

```sql
CREATE UNIQUE INDEX ... ON leaf (external_id);
```

**Câu hỏi:** external_id='A001' có được xuất hiện cả hai tháng không?

**Đáp án:** có thể, vì hai indexes bảo vệ hai tập rows riêng. Muốn global uniqueness cần thiết kế khác hoặc parent UNIQUE hợp lệ có partition key phù hợp với business scope.

## 54. Bài tập 3: ngày là thành phần identity

Một parent có:

```sql
PRIMARY KEY (issued_on, invoice_id)
```

Hai hàng cùng `invoice_id=42` vào ngày `2026-10-01` và `2026-10-02`.

**Đáp án:** hợp lệ theo PK. Nếu nghiệp vụ muốn một ID duy nhất trong tháng, cần thiết kế lại khóa/partition key và uniqueness contract, không suy ra PK hiện tại đủ.

## 55. Bài tập 4: phân biệt hai hướng FK

A. Partitioned invoice có FK đến ordinary customer.

B. Ordinary receipt có FK đến partitioned invoice.

**Câu hỏi:** hỗ trợ từ major version nào?

**Đáp án:** A từ PostgreSQL 11; B từ PostgreSQL 12. PostgreSQL 10 declarative partitioning chưa có các dạng FK này.

## 56. Bài tập 5: FK phải trỏ unique key

```sql
FOREIGN KEY (invoice_id)
REFERENCES demo_part_fk.invoice(invoice_id)
```

**Hỏi:** vì sao không được?

**Đáp án:** parent không có unique/PK chỉ trên invoice_id; constraint hợp lệ của parent là `(issued_on,invoice_id)`. Trỏ chỉ invoice_id có thể nhập nhằng giữa nhiều ngày/partition.

## 57. Bài tập 6: lỗi composite key mismatch

Invoice có `(issued_on=2026-11-10,invoice_id=1001)`. Line chèn `(issued_on=2026-11-11,invoice_id=1001)`.

**Đáp án:** FK thất bại dù invoice_id giống nhau. FK so cả hai thành phần và không tự chuyển ngày về mốc khác.

## 58. Bài tập 7: chỉ CHECK thì chưa đủ

```sql
amount NUMERIC,
CHECK (amount >= 0)
```

**Hỏi:** NULL có bị cấm không?

**Đáp án:** không. `CHECK` không từ chối biểu thức UNKNOWN do NULL. Dùng `NOT NULL` nếu bắt buộc phải có amount.

## 59. Bài tập 8: NOT NULL inherited

Parent có `issued_on DATE NOT NULL`. Một leaf cố bỏ NOT NULL của cột này.

**Đáp án:** không được làm leaf yếu hơn parent constraint inherited như vậy trong declarative partitioning. Constraint của parent áp dụng trên toàn tree.

## 60. Bài tập 9: default partition

Một row có `issued_on='2027-03-01'`, không match tháng 10/11; parent có DEFAULT.

**Đáp án:** row đi vào default partition nếu thỏa các constraints còn lại. DEFAULT không bỏ qua FK/PK/CHECK.

## 61. Bài tập 10: attach với dữ liệu sai bound

Stage table chuẩn bị cho tháng 01/2027 chứa một row ngày `2027-02-10`.

**Hỏi:** attach vào partition `FROM 2027-01-01 TO 2027-02-01` có hợp lệ không?

**Đáp án:** không nếu dữ liệu vi phạm bound. PostgreSQL cần xác minh hoặc dựa vào một CHECK đã được xác thực đúng, không cho phép một row sai bound vào leaf bình thường.

## 62. Bài tập 11: ON DELETE CASCADE và FK khác

Invoice có lines dùng `ON DELETE CASCADE` nhưng receipts dùng `NO ACTION`.

**Hỏi:** DELETE invoice được bảo đảm thành công và chỉ xóa lines?

**Đáp án:** không. FK receipt có thể ngăn DELETE nếu còn referencing rows. Giao dịch phải thỏa **tất cả constraints**, không chỉ một FK có CASCADE.

## 63. Bài tập 12: NOT VALID khác NOT ENFORCED

**Câu hỏi:** khi thêm FK `NOT VALID`, các INSERT mới có được vi phạm không? Khi `NOT ENFORCED` thì sao?

**Đáp án:** enforced `NOT VALID` vẫn kiểm tra các thay đổi dữ liệu mới thích hợp; trạng thái chưa validate chỉ nói chưa quét/xác minh toàn bộ rows cũ. `NOT ENFORCED` (PG18+) không thực thi kiểm tra integrity như FK enforced.

## 64. Bài tập 13: mốc PostgreSQL 18

**Câu hỏi:** vì sao một migration script dùng `ALTER TABLE partitioned_parent ADD FOREIGN KEY ... NOT VALID` có thể chạy trên PostgreSQL 18 nhưng không chạy giống vậy trên 16?

**Đáp án:** PG18 bổ sung hỗ trợ NOT VALID foreign keys trên partitioned tables. FK trên partitioned parent đã có từ trước, nhưng **không phải mọi option của FK được hỗ trợ cùng một thời điểm**.

## 65. Bài tập 14: EXCLUDE parent theo version

**Câu hỏi:** parent-level `EXCLUDE USING gist` có được hỗ trợ từ PG17 không, và có thể dùng `partition_key WITH &&` không?

**Đáp án:** PG17 cho phép parent EXCLUDE theo các điều kiện; mọi partition key columns phải xuất hiện với operator **equality**. Dùng overlap `&&` trên chính partition key không thỏa restriction đó.

## 66. Bài tập 15: cùng tenant, không trùng phòng

Bảng booking partition by LIST(tenant_id), constraint:

```sql
EXCLUDE USING gist (
    tenant_id WITH =,
    room_id WITH =,
    during WITH &&
)
```

**Hỏi:** ràng buộc muốn cấm điều gì?

**Đáp án:** hai bookings cùng tenant và room không được có khoảng `during` overlap. Điều kiện tenant equality phù hợp partition structure. Cần GiST operator classes tương ứng và PostgreSQL 17+ cho parent-level EXCLUDE.

## 67. Bài tập 16: global ID từ sequence

Một developer nói: “Mọi invoice_id do một sequence cấp, không thể trùng; không cần unique constraint.”

**Đáp án:** sequence là cơ chế sinh giá trị, không phải bảo đảm toàn vẹn dữ liệu chống mọi đường ghi, import, restore và thao tác tường minh. Nếu cần global uniqueness, thiết kế một constraint đáng tin ở đúng phạm vi (ví dụ registry PK) hoặc chọn khóa phân vùng phù hợp.

## 68. Bài tập 17: index referencing FK

`invoice_line` có PK `(issued_on,invoice_id,line_no)`. Có cần thêm `INDEX(issued_on,invoice_id)` chỉ để hỗ trợ FK lookup không?

**Đáp án:** không nhất thiết; PK B-tree đã có prefix hai cột đó. Đo workload và query plans, tránh index trùng chức năng không cần thiết.

## 69. Bài tập 18: expression partition key

Một parent phân vùng theo `(id % 4)`. Developer muốn `PRIMARY KEY(id)` ở parent.

**Đáp án:** declarative partitioning hạn chế parent PK/UNIQUE khi partition key chứa expression. Dù expression là hàm của id, PostgreSQL không coi nó tương đương cột partition key đáp ứng restriction của constraint.

## 70. Bài tập 19: subpartition

Parent partition theo ngày, mỗi month subpartition theo tenant. Unique constraint trên root chỉ gồm `(issued_on,invoice_id)`.

**Hỏi:** cần xem thêm điều gì?

**Đáp án:** nhiều tầng partitioning yêu cầu tính đến partition key của descendant partitioned tables, ví dụ thêm tenant_id; PK chỉ bao root partition key có thể không đủ cho toàn tree.

## 71. Bài tập 20: detached partition và receipts

Hệ thống dự định detach tháng 10 khi còn receipt tham chiếu invoice tháng 10 qua parent FK.

**Đáp án định hướng:** không coi detach là xóa dữ liệu vô hại. Cần phân tích dependencies, FK enforcement, retention và hành vi version cụ thể, thử trên staging và có kế hoạch lưu/chuyển dữ liệu phụ thuộc.

## 72. Bài tập 21: legacy inheritance partitioning

Hệ thống cũ dùng `CREATE TABLE child (...) INHERITS(parent)` và các trigger để route INSERT.

**Hỏi:** có thể áp y hệt bảng mốc FK/PK của declarative partitioning không?

**Đáp án:** không. Legacy inheritance có semantics khác về indexes, uniqueness, FK và automatic routing. Trước migration phải phân biệt hai mô hình.

## 73. Bài tập 22: partition pruning và CHECK

**Câu hỏi:** thêm `CHECK (issued_on BETWEEN ...)` có tự tạo partition theo tháng và thay thế `PARTITION BY` không?

**Đáp án:** không. CHECK là ràng buộc dữ liệu; partition key/bounds là cấu trúc routing và pruning riêng. Constraint exclusion dựa vào CHECK là cơ chế tối ưu khác, không tạo leaf partitions.

## 74. Bài tập 23: migration cho version cũ

Hệ thống chạy PG11, có một bảng thường muốn thêm FK tới partitioned parent.

**Đáp án:** PG11 chưa hỗ trợ FK **referencing** partitioned table. Có thể đổi target server lên PG12+ theo kế hoạch upgrade hoặc thiết kế lại referenced key/registry; không lách FK bằng trigger đơn giản rồi gọi là toàn vẹn tương đương.

## 75. Bài tập 24: catalog trạng thái enforcement

Server PostgreSQL 17 chạy:

```sql
SELECT conenforced FROM pg_constraint;
```

**Đáp án:** câu này không chạy vì `conenforced` được thêm trong PostgreSQL 18. Dùng version check trước khi dựa vào catalog fields.

## 76. Bài tập 25: SQLSTATE RESTRICT sau upgrade

Ứng dụng chỉ catch `23503`. Sau upgrade PG18, `ON DELETE RESTRICT` có thể báo `23001`.

**Đáp án:** cập nhật logic phân loại lỗi theo SQLSTATE version-specific và integration tests; không nuốt hết SQLSTATE class `23` vì có nhiều constraint violations khác nhau.

## 77. Ma trận quyết định thiết kế khóa

| Nhu cầu nghiệp vụ | Partitioning phù hợp để xem xét | Khóa/ràng buộc cần đánh giá |
|---|---|---|
| ID duy nhất theo tenant | `HASH/LIST(tenant_id)` | `PRIMARY KEY(tenant_id,id)` |
| ID duy nhất theo ngày | `RANGE(event_date)` | `PRIMARY KEY(event_date,id)` |
| ID duy nhất theo tháng | `RANGE(event_month)` với cột tháng rõ | `UNIQUE(event_month,id)` |
| ID duy nhất toàn cục, partition theo ngày | `RANGE(event_date)` | Registry unique hoặc thiết kế partition key/identity khác |
| Child rows thuộc một invoice ngày cụ thể | Cùng partition day/month hoặc không | Composite FK `(issued_on,invoice_id)` |
| FK từ partitioned table đến ordinary parent | Version PG11+ | FK bình thường, child indexes theo workload |
| FK đến partitioned parent | Version PG12+ | Referenced PK/UNIQUE phải hợp lệ |
| EXCLUDE overlap trong từng tenant | `LIST/HASH(tenant_id)` | PG17+ parent EXCLUDE có partition key equality |
| Data import lớn, thêm FK rồi validate | Có thể partitioned parent | PG18+ FK `NOT VALID` trên partitioned table |
| Không muốn ràng buộc thực thi | Tùy nghiệp vụ | `NOT ENFORCED` PG18+ không bảo vệ integrity |

Đây là **hướng thiết kế**, không phải công thức tự động. Yêu cầu về cardinality, query pruning, số partitions, retention và locks cũng quyết định cấu trúc cuối cùng.

## 78. Checklist trước khi triển khai constraints trên partitioned tables

1. Đã xác nhận đây là **declarative partitioning**, không phải legacy inheritance?
2. `SHOW server_version_num` trên **server thật** là bao nhiêu?
3. Khóa phân vùng gồm những **cột hay expression** nào?
4. Có các tầng subpartition không?
5. PK/UNIQUE của parent đã bao gồm **mọi partition key columns liên quan** chưa?
6. Constraint có thực sự bảo vệ uniqueness đúng **phạm vi nghiệp vụ** không?
7. Có đang giả định một leaf UNIQUE bảo vệ các leaf khác không?
8. Có một business ID cần global uniqueness dù partition theo thời gian không?
9. Có cần registry table để bảo vệ global ID không?
10. Các FK referencing có đủ composite key để trỏ PK/UNIQUE hợp lệ không?
11. Có thể tạo FK đến partitioned parent trên major version mục tiêu không?
12. Có NULL columns khiến composite FK bị bỏ kiểm tra theo MATCH SIMPLE không?
13. Đã lựa chọn ON DELETE/ON UPDATE actions phù hợp partition key chưa?
14. Có cascade gây xóa/sửa nhiều partitions không?
15. Có index phù hợp ở phía referencing không?
16. Có index PK/UNIQUE trùng prefix, khiến index mới dư không?
17. Parent CHECK/NOT NULL có truyền xuống leaves đúng ý định không?
18. Có leaf-local CHECK làm behavior khác nhau giữa partitions không?
19. Partition bounds có bao phủ dữ liệu thật không?
20. Có DEFAULT partition và hàng rơi vào DEFAULT nhiều không?
21. ATTACH có cần scan dữ liệu cũ không?
22. Có prevalidated CHECK bounds để giảm scan phù hợp không?
23. DETACH/DROP có ảnh hưởng đến FK references và retention không?
24. Có external/foreign partitions mà DB core không enforce CHECK ở remote không?
25. Có dùng `NOT VALID` trên partitioned FK trước PG18 không?
26. Có nhầm `NOT ENFORCED` là một constraint đang bảo vệ dữ liệu không?
27. EXCLUDE parent có được hỗ trợ (PG17+) và chứa partition keys equality không?
28. Có temporal constraint trên PG18 cần kiểm chứng syntax/semantics riêng không?
29. Có kế hoạch xử lý on-conflict/upsert khi unique key gồm partition key không?
30. ORM/API có model hóa composite key đúng không?
31. Row movement khi UPDATE partition key có được kiểm thử không?
32. Có số lượng partitions quá lớn gây overhead constraint/DDL không?
33. Migration có quy trình lock/timeouts/rollback không?
34. Có integration tests cho FK errors, UNIQUE, CHECK, NOT NULL không?
35. Có kiểm tra SQLSTATE khác biệt giữa major versions không?
36. Có metadata query `pg_constraint`/`pg_partition_tree` để xác minh deploy không?
37. Có benchmark một số thao tác DELETE referenced parent với rất nhiều child rows không?
38. Có kế hoạch quản lý tạo partition mới trước kỳ dữ liệu tiếp theo không?
39. Có policy cho default partition và orphaned references khi retention không?
40. Đã đọc release notes đúng minor version của server đích chưa?

## 79. Nguồn tài liệu phiên bản

Để đối chiếu schema và tính năng **theo version**, tham khảo tài liệu PostgreSQL chính thức:

- [PostgreSQL 10 — Partitioning](https://www.postgresql.org/docs/10/ddl-partitioning.html)
- [PostgreSQL 11 — Partitioning](https://www.postgresql.org/docs/11/ddl-partitioning.html)
- [PostgreSQL 12 — Partitioning](https://www.postgresql.org/docs/12/ddl-partitioning.html)
- [PostgreSQL 16 — Partitioning](https://www.postgresql.org/docs/16/ddl-partitioning.html)
- [PostgreSQL 17 — Partitioning](https://www.postgresql.org/docs/17/ddl-partitioning.html)
- [PostgreSQL 18 — Partitioning](https://www.postgresql.org/docs/18/ddl-partitioning.html)
- [PostgreSQL 18 — CREATE TABLE](https://www.postgresql.org/docs/18/sql-createtable.html)
- [PostgreSQL 18 — ALTER TABLE](https://www.postgresql.org/docs/18/sql-altertable.html)
- [PostgreSQL 18 — Release notes](https://www.postgresql.org/docs/18/release-18.html)
- [PostgreSQL 17 — Release notes](https://www.postgresql.org/docs/17/release-17.html)

**Đọc tài liệu khớp với server đang chạy.** Một ví dụ hợp lệ trên PG18 không tự chạy được trên PG11, và tính năng ở PG19 RC chưa nên coi là contract production trước GA.

## 80. Tổng kết

**Phân vùng không tự hủy bỏ các ràng buộc dữ liệu, nhưng nó thay đổi phạm vi mà PostgreSQL có thể chứng minh tính duy nhất và bảo vệ tham chiếu.**

Những nguyên tắc cần nhớ:

1. **PK/UNIQUE của partitioned parent phải bao gồm tất cả partition key columns và không dùng expression partition key theo restriction hiện hành.** Đây là cách PostgreSQL dựa vào routing để bảo vệ uniqueness bằng các index local.
2. **PK `(issued_on,invoice_id)` chỉ bảo vệ tổ hợp, không bảo vệ `invoice_id` toàn cục.** Nếu ID phải duy nhất không phụ thuộc ngày, cần thiết kế khác.
3. **FK theo version:** PG10 chưa hỗ trợ trong declarative tree; PG11 hỗ trợ FK **từ** partitioned table đến ordinary table; PG12 hỗ trợ FK **đến** partitioned table, giúp các tình huống FK hai chiều với parent phân vùng.
4. **CHECK/NOT NULL ở parent được inherited.** Bounds quyết định routing; CHECK chỉ là ràng buộc bổ sung và không thay partition key.
5. **PG17 thêm parent EXCLUDE theo điều kiện partition key equality; PG18 thêm NOT VALID FK trên partitioned tables và NOT ENFORCED CHECK/FK.** NOT VALID và NOT ENFORCED hoàn toàn khác ý nghĩa.
6. **Quản trị partitions phải đi cùng constraints.** ATTACH, DETACH, DEFAULT partitions, index ở leaves, row movement và retention cần kiểm tra dữ liệu/locks/dependencies.
7. **Thiết kế FK và business identity ngay trước khi partition.** Composite keys ảnh hưởng ứng dụng, ORM, API, JOIN và `ON CONFLICT`, không chỉ database DDL.

Một câu hỏi quyết định kiến trúc là: **“Giá trị nào phải duy nhất trong toàn bộ dữ liệu, và những hàng có cùng giá trị đó có luôn được đưa về cùng một partition không?”** Tiếp đó hãy hỏi: **“Các bảng tham chiếu có đủ thông tin partition key để tạo một FK thực sự được PostgreSQL bảo vệ trên phiên bản mục tiêu không?”** Hai câu trả lời này giúp tránh một hệ thống trông đúng trên mỗi phân vùng riêng lẻ nhưng không bảo đảm toàn vẹn dữ liệu của bảng logic.
