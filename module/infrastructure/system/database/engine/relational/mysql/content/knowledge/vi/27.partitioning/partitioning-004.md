# Yêu cầu khóa phân vùng trong các khóa UNIQUE/PRIMARY

Khi một bảng MySQL được phân vùng, partitioning expression quyết định mỗi hàng được đặt vào partition nào. InnoDB phải bảo đảm các ràng buộc duy nhất hoạt động đúng trên toàn bảng, kể cả khi các hàng nằm ở những partition khác nhau. Vì vậy, MySQL áp dụng một quy tắc quan trọng: **mọi cột được dùng trong partitioning expression phải xuất hiện trong mọi khóa UNIQUE của bảng, bao gồm PRIMARY KEY**.

Quy tắc này ảnh hưởng trực tiếp đến thiết kế khóa chính, khóa nghiệp vụ và cách bảo đảm uniqueness khi phân vùng theo ngày, tenant hoặc một thuộc tính khác. Nếu partition theo created_at nhưng muốn order_id duy nhất toàn cục, PRIMARY KEY(order_id) không đáp ứng yêu cầu của MySQL. Nếu đổi thành PRIMARY KEY(created_at, order_id), MySQL chấp nhận thiết kế nhưng ràng buộc mới chỉ bảo đảm cặp created_at và order_id duy nhất; order_id riêng lẻ vẫn có thể trùng ở hai ngày khác nhau.

Trong module **DATABASE_MYSQL**, partitioning thường được dùng để quản lý bảng lớn, giới hạn phạm vi truy vấn bằng partition pruning và hỗ trợ vòng đời dữ liệu. Bài học này giải thích quy tắc khóa UNIQUE/PRIMARY, lý do tồn tại, ví dụ DDL đúng/sai, tác động đến semantics của khóa nghiệp vụ và các cách giữ uniqueness toàn cục khi partition key khác business key.

## 1. Quy tắc cốt lõi của MySQL

Với bảng được partition, mọi cột xuất hiện trong partitioning expression phải là một phần của **mọi unique key** mà bảng khai báo.

Unique key ở đây bao gồm:

- PRIMARY KEY.
- Mọi UNIQUE INDEX hoặc UNIQUE KEY khác.

Ví dụ bảng phân vùng theo created_at:

```sql
CREATE TABLE events (
    event_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    PRIMARY KEY (created_at, event_id),
    UNIQUE KEY uq_created_type (created_at, event_type)
)
ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Partitioning expression dùng created_at. Cả PRIMARY KEY và UNIQUE KEY đều chứa created_at, vì vậy đáp ứng quy tắc.

Một khóa UNIQUE có thể chứa thêm các cột khác; điều bắt buộc là không được thiếu bất kỳ cột nào tham gia partitioning expression.

### 1.1. Partitioning expression dùng nhiều cột

Nếu partitioning expression tham chiếu nhiều cột, tất cả các cột đó phải có mặt trong từng unique key.

Ví dụ partition theo HASH của tenant_id và region_id:

```sql
CREATE TABLE tenant_events (
    tenant_id BIGINT UNSIGNED NOT NULL,
    region_id INT UNSIGNED NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    PRIMARY KEY (tenant_id, region_id, event_id),
    UNIQUE KEY uq_tenant_region_ref (
        tenant_id,
        region_id,
        external_ref
    )
)
ENGINE = InnoDB
PARTITION BY HASH (tenant_id + region_id)
PARTITIONS 16;
```

Expression dùng cả tenant_id và region_id. Hai cột này đều xuất hiện trong PRIMARY KEY và UNIQUE KEY.

Nếu một unique key chỉ chứa tenant_id mà thiếu region_id, key đó không hợp lệ với partitioning expression trên.

### 1.2. Hàm trong partitioning expression không làm mất yêu cầu

Nếu partitioning expression dùng một hàm trên cột, cột được tham chiếu vẫn phải nằm trong mỗi unique key.

Ví dụ:

```sql
CREATE TABLE audit_events (
    event_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    event_code VARCHAR(40) NOT NULL,
    PRIMARY KEY (created_at, event_id),
    UNIQUE KEY uq_created_event_code (created_at, event_code)
)
ENGINE = InnoDB
PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION pmax VALUES LESS THAN MAXVALUE
);
```

Dù expression là YEAR(created_at), cột created_at vẫn phải xuất hiện trong mọi unique key.

Không nhầm giữa partitioning expression và một giá trị tính toán độc lập: MySQL xét các cột được dùng trong expression để áp dụng quy tắc khóa.

## 2. Vì sao MySQL yêu cầu partition key nằm trong unique key?

Một unique index phải phát hiện được hai hàng có cùng khóa, dù chúng được lưu ở đâu. Trong bảng partitioned, các index được tổ chức theo từng partition; MySQL không cung cấp một global unique index duy nhất bao phủ mọi partition.

Partitioning expression xác định partition chứa mỗi hàng. Nếu toàn bộ cột partition key cũng nằm trong unique key, hai hàng có cùng giá trị unique key chắc chắn có cùng giá trị partition key và do đó được định tuyến tới cùng partition. Storage engine có thể kiểm tra uniqueness trong phạm vi partition đó.

Nếu unique key không chứa partition key, hai hàng có thể có cùng giá trị unique key nhưng khác partition key. Chúng có thể được đặt vào hai partition khác nhau; nếu không có global unique index, MySQL không thể dùng index cục bộ của một partition để phát hiện xung đột ở partition khác.

Ví dụ partition theo ngày:

- Hàng A: order_id = 9001, created_at = 2026-01-10.
- Hàng B: order_id = 9001, created_at = 2026-02-10.

Hai hàng có cùng order_id nhưng khác created_at, nên được đưa vào các partition thời gian khác nhau. Nếu chỉ có UNIQUE(order_id), việc kiểm tra uniqueness phải tìm được cả hai partition. Quy tắc của MySQL ngăn khai báo unique key như vậy trên bảng partitioned.

Đây là giới hạn thiết kế có chủ đích, không phải lỗi cú pháp ngẫu nhiên.

## 3. Ví dụ sai: partition theo ngày nhưng PRIMARY KEY chỉ có ID

Giả sử yêu cầu ban đầu:

- Phân vùng đơn hàng theo created_at để dễ quản lý dữ liệu theo tháng/năm.
- order_id là khóa chính và phải duy nhất.
- external_ref là mã giao dịch duy nhất.

DDL sau không hợp lệ:

```sql
CREATE TABLE orders_bad (
    order_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_external_ref (external_ref)
)
ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Cả PRIMARY KEY(order_id) và UNIQUE(external_ref) đều thiếu created_at. MySQL từ chối định nghĩa này.

Thông báo lỗi thường thuộc nhóm:

- A PRIMARY KEY must include all columns in the table's partitioning function.
- A UNIQUE INDEX must include all columns in the table's partitioning function.

Thông báo cụ thể có thể khác tùy phiên bản và khóa được kiểm tra đầu tiên. Ý nghĩa vẫn là unique key phải chứa partition column.

### 3.1. Thêm partition key vào PRIMARY KEY

Có thể đổi thành:

```sql
CREATE TABLE orders_by_date (
    order_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (created_at, order_id),
    UNIQUE KEY uq_created_external_ref (created_at, external_ref),
    KEY idx_customer_created (customer_id, created_at)
)
ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

DDL này hợp lệ theo quy tắc partition key trong unique key:

- PRIMARY KEY(created_at, order_id) chứa created_at.
- UNIQUE(created_at, external_ref) chứa created_at.
- Index thường idx_customer_created không phải unique key, nên không bị ràng buộc phải chứa partition key.

Nhưng semantics đã thay đổi. Khóa chính bảo đảm cặp (created_at, order_id) duy nhất, không bảo đảm order_id riêng lẻ duy nhất. UNIQUE(created_at, external_ref) cũng chỉ bảo đảm external_ref duy nhất trong cùng created_at, không bảo đảm external_ref duy nhất trên toàn bộ bảng.

**Không được kết luận rằng thêm partition key vào unique key vẫn giữ nguyên uniqueness nghiệp vụ ban đầu.** Đây là lỗi thiết kế thường gặp nhất khi chuyển bảng hiện có sang partitioning.

## 4. Ví dụ đúng: uniqueness theo tenant khi partition theo tenant

Không phải lúc nào thêm partition key cũng làm yếu semantics. Nếu yêu cầu nghiệp vụ vốn là duy nhất trong phạm vi tenant, partition theo tenant có thể khớp tự nhiên với khóa nghiệp vụ.

Ví dụ mỗi tenant có external_ref riêng, nhưng hai tenant khác nhau được phép dùng cùng external_ref:

```sql
CREATE TABLE tenant_orders (
    tenant_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    created_at DATETIME NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (tenant_id, order_id),
    UNIQUE KEY uq_tenant_external_ref (tenant_id, external_ref),
    KEY idx_tenant_created (tenant_id, created_at)
)
ENGINE = InnoDB
PARTITION BY HASH (tenant_id)
PARTITIONS 16;
```

Ở đây:

- Partitioning expression chỉ dùng tenant_id.
- PRIMARY KEY có tenant_id.
- UNIQUE KEY có tenant_id.
- Mọi hàng của cùng tenant_id được định tuyến tới cùng partition.
- UNIQUE(tenant_id, external_ref) bảo đảm external_ref không trùng trong phạm vi tenant, kể cả khi tenant có nhiều đơn hàng.

Truy vấn:

```sql
SELECT order_id, amount
FROM tenant_orders
WHERE tenant_id = 42
  AND external_ref = 'EXT-2026-0001';
```

Điều kiện tenant_id cho phép partition pruning; unique index tiếp tục hỗ trợ lookup trong partition tương ứng.

Nếu yêu cầu là external_ref duy nhất toàn hệ thống, thiết kế này chưa đủ: cùng external_ref có thể xuất hiện ở tenant khác. Khi đó cần chọn partition key phù hợp hơn hoặc bổ sung một cơ chế uniqueness toàn cục ở cấu trúc khác.

## 5. UNIQUE prefix và partition key

Quy tắc partition key cũng áp dụng cho unique index dùng prefix của cột chuỗi.

Ví dụ partition theo tenant_id:

```sql
CREATE TABLE tenant_documents (
    tenant_id BIGINT UNSIGNED NOT NULL,
    document_id BIGINT UNSIGNED NOT NULL,
    path VARCHAR(2000) NOT NULL,
    PRIMARY KEY (tenant_id, document_id),
    UNIQUE KEY uq_tenant_path_prefix (tenant_id, path(120))
)
ENGINE = InnoDB
PARTITION BY HASH (tenant_id)
PARTITIONS 8;
```

Key tenant_id có mặt trong UNIQUE key nên đáp ứng quy tắc partitioning. Tuy nhiên, UNIQUE prefix chỉ bảo đảm phần 120 ký tự đầu của path không trùng trong phạm vi tenant; nó không bảo đảm toàn bộ path duy nhất theo semantics của chuỗi đầy đủ.

Hai yêu cầu độc lập cần được kiểm tra:

1. Unique key có chứa đầy đủ partition column hay không?
2. Unique key có biểu diễn đúng uniqueness nghiệp vụ hay không?

Một DDL có thể hợp lệ về partitioning nhưng vẫn sai về nghiệp vụ nếu prefix quá ngắn hoặc nếu composite key làm thay đổi phạm vi uniqueness.

## 6. Cột partition có thể nằm ở bất kỳ vị trí nào trong unique key?

Quy tắc yêu cầu cột partition xuất hiện trong unique key; nó không yêu cầu các cột đó luôn phải đứng đầu key.

Ví dụ với partition theo created_at:

```sql
CREATE TABLE events_position_demo (
    event_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    source_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (event_id, created_at),
    UNIQUE KEY uq_source_date (source_id, created_at)
)
ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Cả hai unique key đều có created_at, dù created_at không đứng đầu PRIMARY KEY.

Tuy nhiên, vị trí cột ảnh hưởng đến khả năng sử dụng leftmost prefix của B-tree. Nếu truy vấn thường lọc theo created_at rồi event_id, thứ tự (created_at, event_id) có thể phù hợp hơn (event_id, created_at). Nếu truy vấn thường tìm theo event_id, thứ tự ngược lại có thể hữu ích hơn.

Vì vậy, phân biệt:

- **Tính hợp lệ của partitioned table:** partition columns phải có trong mọi unique key.
- **Hiệu quả truy vấn:** thứ tự key part cần phù hợp với workload và leftmost prefix.
- **Semantics uniqueness:** tập hợp cột trong unique key xác định phạm vi giá trị phải duy nhất.

Không đổi thứ tự key chỉ để thỏa quy tắc nếu chưa xem xét truy vấn chính.

## 7. Unique key trên bảng partitioned không phải global unique index

MySQL không cung cấp global unique index cho các bảng partitioned theo cách có thể kiểm tra một khóa không chứa partition key xuyên qua mọi partition.

Giả sử bảng partition theo tháng:

```sql
CREATE TABLE payment_events (
    event_id BIGINT UNSIGNED NOT NULL,
    paid_at DATE NOT NULL,
    provider_txn_id VARCHAR(100) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (paid_at, event_id),
    UNIQUE KEY uq_paid_provider_txn (paid_at, provider_txn_id)
)
ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (paid_at) (
    PARTITION p202601 VALUES LESS THAN ('2026-02-01'),
    PARTITION p202602 VALUES LESS THAN ('2026-03-01'),
    PARTITION p202603 VALUES LESS THAN ('2026-04-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

UNIQUE(paid_at, provider_txn_id) cho phép cùng provider_txn_id xuất hiện ở hai ngày khác nhau. Điều này đúng nếu nghiệp vụ định nghĩa giao dịch duy nhất theo ngày; sai nếu provider_txn_id phải duy nhất trên toàn hệ thống.

Một câu truy vấn chỉ có provider_txn_id:

```sql
SELECT *
FROM payment_events
WHERE provider_txn_id = 'PSP-998877';
```

không có điều kiện paid_at nên có thể phải kiểm tra nhiều partition. Không có global unique index trên provider_txn_id để ngăn duplicate xuyên partition.

Partition pruning và uniqueness là hai vấn đề khác nhau. Pruning giảm số partition cần đọc khi điều kiện chứa partition key; nó không tạo ra global unique constraint cho các cột khác.

## 8. Cách giữ uniqueness toàn cục khi partition theo ngày

Nếu cần partition dữ liệu lớn theo ngày nhưng một ID hoặc mã nghiệp vụ phải duy nhất toàn cục, có một số thiết kế phổ biến.

### 8.1. Bảng registry không phân vùng

Tạo một bảng nhỏ hơn, không partition, giữ khóa nghiệp vụ duy nhất. Bảng partitioned lưu dữ liệu chi tiết theo thời gian.

Ví dụ bảng registry:

```sql
CREATE TABLE payment_id_registry (
    provider_txn_id VARCHAR(100) NOT NULL,
    paid_at DATE NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (provider_txn_id),
    UNIQUE KEY uq_registry_event_id (event_id)
) ENGINE = InnoDB;
```

Bảng sự kiện phân vùng theo ngày:

```sql
CREATE TABLE payment_events_partitioned (
    event_id BIGINT UNSIGNED NOT NULL,
    paid_at DATE NOT NULL,
    provider_txn_id VARCHAR(100) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (paid_at, event_id),
    UNIQUE KEY uq_event_date_provider (paid_at, provider_txn_id)
)
ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (paid_at) (
    PARTITION p202601 VALUES LESS THAN ('2026-02-01'),
    PARTITION p202602 VALUES LESS THAN ('2026-03-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Khi nhận một giao dịch mới, ứng dụng ghi registry và bảng chi tiết trong cùng transaction InnoDB:

```sql
START TRANSACTION;

INSERT INTO payment_id_registry (
    provider_txn_id,
    paid_at,
    event_id
)
VALUES (
    'PSP-998877',
    '2026-01-18',
    700001
);

INSERT INTO payment_events_partitioned (
    event_id,
    paid_at,
    provider_txn_id,
    amount
)
VALUES (
    700001,
    '2026-01-18',
    'PSP-998877',
    125000.00
);

COMMIT;
```

Nếu provider_txn_id đã tồn tại, INSERT vào registry thất bại do PRIMARY KEY; transaction cần rollback và xử lý duplicate theo nghiệp vụ. Nếu insert bảng partitioned thất bại, rollback cũng hoàn tác registry.

Ưu điểm:

- Registry bảo đảm provider_txn_id duy nhất toàn cục.
- Bảng chi tiết vẫn partition theo ngày.
- Có thể tìm ngày và event_id từ registry trước, rồi truy vấn đúng partition.
- Transaction InnoDB giúp hai thao tác ghi thành công hoặc rollback cùng nhau.

Giới hạn:

- Registry tăng theo số lượng khóa nghiệp vụ cần lưu.
- Ứng dụng phải duy trì cả hai bảng trong cùng transaction và xử lý retry.
- MySQL InnoDB user-partitioned table không hỗ trợ foreign key; không thể dựa vào FK để ràng buộc registry với bảng partitioned.
- Cần định nghĩa retention của registry. Nếu xóa registry quá sớm, một provider_txn_id cũ có thể được nhập lại.

Không được bỏ qua lỗi duplicate ở registry rồi vẫn chèn bảng chi tiết. Cần xác định rõ đây là lần gửi lại idempotent hay xung đột dữ liệu.

### 8.2. Chọn partition key trùng với phạm vi uniqueness

Nếu khóa nghiệp vụ duy nhất theo tenant, partition theo tenant_id có thể là lựa chọn tự nhiên:

```sql
CREATE TABLE tenant_payment_events (
    tenant_id BIGINT UNSIGNED NOT NULL,
    provider_txn_id VARCHAR(100) NOT NULL,
    paid_at DATETIME NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (tenant_id, provider_txn_id)
)
ENGINE = InnoDB
PARTITION BY HASH (tenant_id)
PARTITIONS 16;
```

Trong ví dụ, khóa nghiệp vụ là cặp (tenant_id, provider_txn_id), và partition key tenant_id nằm trong unique key. MySQL có thể bảo đảm uniqueness của cặp này.

Nếu cần truy vấn hoặc xóa dữ liệu theo thời gian, partition theo tenant có thể không phù hợp. Chọn partition key phải cân bằng cả truy vấn, retention, phân bố dữ liệu và uniqueness.

### 8.3. Dùng ID toàn cục do ứng dụng sinh

Ứng dụng có thể sinh UUID/ULID hoặc ID phân tán để giảm khả năng trùng giữa các node. Đây là một chiến lược tạo ID, không tự thay thế một UNIQUE constraint trong MySQL.

Nếu partition theo ngày và chỉ khai báo PRIMARY KEY(paid_at, event_id), database vẫn không bảo đảm event_id riêng lẻ không trùng giữa hai ngày. Nếu yêu cầu là bảo đảm tuyệt đối ở tầng database, cần registry hoặc một thiết kế partition key tương thích với unique key.

### 8.4. Chấp nhận uniqueness trong phạm vi partition

Đôi khi nghiệp vụ chỉ cần mã duy nhất trong một ngày/tháng. Khi đó, đưa partition key vào unique key chính là semantics mong muốn.

Ví dụ UNIQUE(paid_at, provider_txn_id) bảo đảm cùng provider_txn_id không trùng trong cùng paid_at. Nếu paid_at là DATE, hai giao dịch có cùng provider_txn_id ở hai ngày khác nhau vẫn được phép.

Cần viết rõ phạm vi uniqueness trong tài liệu nghiệp vụ và API, tránh gọi đây là "provider_txn_id duy nhất toàn cục".

## 9. Kiểm tra bảng trước khi partition

Trước khi thêm partitioning vào bảng hiện có, hãy lập danh sách:

1. Partitioning expression dùng những cột nào?
2. PRIMARY KEY hiện tại có đủ tất cả partition columns không?
3. Mỗi UNIQUE KEY hiện tại có đủ tất cả partition columns không?
4. Composite key sau khi thêm partition column có còn đúng semantics nghiệp vụ không?
5. Các truy vấn lookup theo business key có cần tìm xuyên partition không?
6. Có yêu cầu global uniqueness nào cần registry hoặc cấu trúc bổ trợ không?
7. Các bảng có FOREIGN KEY tham chiếu đến hoặc tham chiếu từ bảng này không?
8. Partition key có phù hợp với retention, pruning và phân bố dữ liệu không?

Xem DDL hiện tại:

```sql
SHOW CREATE TABLE orders;
```

Liệt kê index:

```sql
SHOW INDEX FROM orders;
```

Xem metadata partition:

```sql
SELECT
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY PARTITION_ORDINAL_POSITION;
```

Xem các cột trong từng index:

```sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Trong kết quả STATISTICS, NON_UNIQUE = 0 xác định PRIMARY/UNIQUE index. Đối chiếu từng index đó với tất cả cột được tham chiếu trong PARTITION_EXPRESSION. Không chỉ kiểm tra PRIMARY KEY; một UNIQUE KEY phụ bị thiếu partition column cũng làm DDL không hợp lệ.

Với partitioning expression có hàm hoặc biểu thức phức tạp, cần xác định đầy đủ các cột đầu vào của expression. Metadata PARTITION_EXPRESSION hiển thị expression nhưng không tự sinh kết luận rằng mọi unique key đã hợp lệ.

## 10. Quy trình thiết kế khóa khi tạo bảng partitioned

Một quy trình thực tế:

### Bước 1: Chốt partition key theo workload

Chọn cột dựa trên truy vấn, retention, kích thước dữ liệu và cách phân bố hàng. Ví dụ created_at cho retention theo thời gian hoặc tenant_id cho workload tách theo tenant.

Không chọn partition key chỉ để giải quyết một lỗi DDL về unique key.

### Bước 2: Liệt kê khóa nghiệp vụ

Viết rõ các yêu cầu:

- order_id duy nhất toàn hệ thống?
- external_ref duy nhất theo tenant?
- provider_txn_id duy nhất toàn cục hay chỉ trong một ngày?
- Một user có thể dùng cùng username ở tenant khác không?

Không suy ra phạm vi uniqueness từ tên cột.

### Bước 3: Kiểm tra từng unique key

Đối với mỗi PRIMARY/UNIQUE key, kiểm tra mọi partition column đã xuất hiện chưa. Nếu thiếu, DDL không đáp ứng quy tắc partitioning.

### Bước 4: Đánh giá semantics sau khi thêm partition key

Ví dụ:

- UNIQUE(email) đổi thành UNIQUE(created_at, email) sẽ cho phép cùng email xuất hiện ở hai ngày khác nhau.
- PRIMARY KEY(order_id) đổi thành PRIMARY KEY(created_at, order_id) sẽ cho phép cùng order_id ở hai ngày khác nhau.
- UNIQUE(tenant_id, external_ref) khi partition theo HASH(tenant_id) vẫn giữ đúng uniqueness theo tenant.

Nếu semantics thay đổi, không triển khai cho đến khi có thiết kế bổ sung.

### Bước 5: Chọn cách bảo đảm global uniqueness

Có thể chọn:

- Partition key trùng với phạm vi uniqueness.
- Bảng registry không partition có PRIMARY/UNIQUE key toàn cục.
- Một bảng định danh trung tâm hoặc dịch vụ cấp ID, nếu yêu cầu kiến trúc cho phép.
- Thiết kế lại partitioning để mọi giá trị cần unique được định tuyến vào cùng partition.

Phải xác định rõ lớp nào chịu trách nhiệm bảo đảm uniqueness và cách xử lý retry/concurrency.

### Bước 6: Kiểm thử DDL và cạnh tranh

Tạo bảng trên môi trường thử nghiệm, kiểm tra:

- DDL được chấp nhận.
- Duplicate trong cùng partition bị từ chối.
- Duplicate ở partition khác có hành vi đúng theo semantics thiết kế.
- Concurrent insert không thể vượt qua unique constraint.
- Partition pruning hoạt động với các truy vấn chính.
- Quy trình purge/retention không xóa registry sớm.

### Bước 7: Lập kế hoạch migration

Với bảng hiện có, cần kiểm tra dữ liệu duplicate trước khi đổi khóa. Có thể cần tạo bảng mới, backfill theo batch, đồng bộ thay đổi phát sinh và chuyển ứng dụng theo giai đoạn. Không giả định ALTER TABLE thêm partition là thao tác nhẹ hoặc không ảnh hưởng truy cập; đánh giá thời gian rebuild, metadata lock, dung lượng tạm và replication lag.

## 11. Ví dụ migration: bảng đơn hàng partition theo ngày

Giả sử bảng cũ:

```sql
CREATE TABLE orders_legacy (
    order_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_external_ref (external_ref)
) ENGINE = InnoDB;
```

Nghiệp vụ yêu cầu:

- order_id duy nhất toàn hệ thống.
- external_ref duy nhất toàn hệ thống.
- Dữ liệu chi tiết partition theo created_at.

Chỉ đổi khóa thành:

```sql
PRIMARY KEY (created_at, order_id),
UNIQUE KEY (created_at, external_ref)
```

là chưa đủ, vì semantics uniqueness toàn cục đã biến thành uniqueness theo ngày.

Một phương án là giữ registry:

```sql
CREATE TABLE order_identity_registry (
    order_id BIGINT UNSIGNED NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    created_at DATE NOT NULL,
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_registry_external_ref (external_ref)
) ENGINE = InnoDB;
```

Bảng chi tiết:

```sql
CREATE TABLE orders_partitioned (
    order_id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    external_ref VARCHAR(80) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (created_at, order_id),
    UNIQUE KEY uq_partition_date_ref (created_at, external_ref),
    KEY idx_customer_created (customer_id, created_at)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Khi tạo đơn mới, cùng một transaction:

1. Insert order_id và external_ref vào registry để database kiểm tra uniqueness toàn cục.
2. Insert dữ liệu chi tiết vào partitioned table.
3. Commit khi cả hai thao tác thành công; rollback cả hai nếu một thao tác thất bại.

Bảng registry không có foreign key đến partitioned table vì InnoDB user-defined partitioned tables không hỗ trợ foreign key. Ứng dụng phải bảo đảm hai bản ghi được ghi cùng transaction và có quy trình đối soát định kỳ.

Khi đọc theo order_id, tìm created_at trong registry trước rồi dùng cả created_at và order_id để truy vấn bảng partitioned, giúp pruning đúng partition.

## 12. Foreign key và các giới hạn liên quan

Trong MySQL, InnoDB user-defined partitioned tables không hỗ trợ foreign key theo các phiên bản MySQL 8.0 hiện hành. Điều này có nghĩa bảng partitioned không thể có foreign key theo cách thông thường và cũng không thể được bảng khác tham chiếu bằng foreign key.

Vì vậy, nếu mô hình hiện tại dựa nhiều vào FOREIGN KEY, việc partitioning cần được đánh giá ở cấp thiết kế dữ liệu. Registry table có thể bảo đảm uniqueness bằng PRIMARY/UNIQUE key riêng, nhưng quan hệ giữa registry và partitioned detail phải được quản lý bằng transaction, ứng dụng và quy trình kiểm tra nhất quán.

Không tắt foreign_key_checks rồi cho rằng constraint sẽ được bảo đảm tự động trên partitioned table. Biến đó không biến một thiết kế không được hỗ trợ thành mô hình có foreign key đầy đủ.

Ngoài ra, partitioning có các giới hạn về loại cột, biểu thức, index và storage engine. Kiểm tra tài liệu đúng phiên bản MySQL trước khi chọn partition method hoặc thay đổi schema production.

## 13. Các lỗi và hiểu nhầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ thêm partition key vào PRIMARY KEY mà quên UNIQUE phụ | DDL vẫn bị từ chối | Kiểm tra mọi unique index |
| Nghĩ PRIMARY KEY(order_id) vẫn global unique sau khi đổi thành (created_at, order_id) | order_id có thể trùng giữa các ngày | Dùng registry hoặc đổi partition strategy |
| Nghĩ UNIQUE(created_at, email) tương đương UNIQUE(email) | Email chỉ duy nhất trong cùng ngày | Xác định đúng phạm vi uniqueness |
| Chọn partition key theo retention mà không xét business key | Mất khả năng enforce global uniqueness | Thiết kế registry/identity table |
| Nghĩ MySQL có global unique index xuyên partition | DDL không hỗ trợ hoặc semantics không đúng | Đưa partition columns vào unique key |
| Quên cột nằm bên trong partitioning expression | DDL không hợp lệ | Liệt kê mọi cột đầu vào của expression |
| Chỉ xem PRIMARY KEY khi kiểm tra DDL | Unique index phụ vẫn thiếu partition column | Duyệt toàn bộ NON_UNIQUE = 0 |
| Dùng UUID để tuyên bố database bảo đảm duy nhất tuyệt đối | Không có UNIQUE constraint toàn cục | Phân biệt xác suất ID collision và ràng buộc database |
| Dùng UNIQUE prefix mà nghĩ toàn bộ chuỗi duy nhất | Có thể từ chối giá trị khác nhau cùng prefix | Xem semantics của prefix key |
| Bỏ registry quá sớm khi purge partition cũ | ID đã dùng có thể được tái sử dụng | Thiết kế retention và idempotency |
| Bỏ qua giới hạn FOREIGN KEY của InnoDB partitioning | Mô hình quan hệ không được bảo vệ như mong muốn | Đánh giá lại schema và integrity strategy |

## 14. Checklist trước khi đưa partitioned table vào production

**Thiết kế partition:**

- Partitioning expression đã được chọn theo truy vấn, retention và phân bố dữ liệu.
- Đã liệt kê mọi cột tham gia expression, kể cả cột nằm trong hàm.
- Mỗi PRIMARY KEY chứa đầy đủ partition columns.
- Mỗi UNIQUE KEY phụ chứa đầy đủ partition columns.
- Đã xác định rõ phạm vi uniqueness là toàn cục, theo tenant, theo ngày hay theo partition.

**Tính toàn vẹn dữ liệu:**

- Không vô tình làm yếu UNIQUE(email), UNIQUE(order_id) hoặc khóa nghiệp vụ khác.
- Có registry/identity table nếu cần global uniqueness.
- Ghi registry và partitioned detail trong cùng transaction.
- Có cơ chế đối soát khi không thể dùng FOREIGN KEY.
- Có chính sách giữ registry đồng bộ với retention của partition.

**Truy vấn và vận hành:**

- Truy vấn chính có điều kiện trên partition key khi cần pruning.
- Index thường được thiết kế theo workload sau khi xét partitioning.
- Đã thử insert duplicate trong cùng và khác partition.
- Đã thử concurrent insert và retry.
- Đã đánh giá DDL migration, metadata lock, rebuild time và replication lag.
- Đã xác nhận cú pháp và giới hạn trên đúng phiên bản MySQL production.

## 15. Ghi nhớ

- Mọi cột dùng trong partitioning expression phải có mặt trong mọi unique key của bảng, bao gồm PRIMARY KEY.
- Nếu expression dùng nhiều cột hoặc hàm trên cột, tất cả cột đầu vào đều phải được đưa vào từng unique key.
- Quy tắc này giúp MySQL kiểm tra uniqueness trong partition chứa hàng; MySQL không cung cấp global unique index xuyên mọi partition.
- Thêm partition key vào unique key có thể làm thay đổi semantics: UNIQUE(order_id) thành UNIQUE(created_at, order_id) không còn bảo đảm order_id duy nhất toàn cục.
- Partition theo tenant_id phù hợp nếu khóa nghiệp vụ là cặp (tenant_id, business_key) và mọi hàng cùng tenant được đưa vào cùng partition.
- Prefix UNIQUE vẫn có giới hạn uniqueness theo phần prefix, độc lập với quy tắc partition key.
- Partition key có thể không đứng đầu unique key để thỏa quy tắc, nhưng thứ tự cột vẫn ảnh hưởng leftmost prefix và hiệu năng truy vấn.
- Nếu cần global uniqueness khi partition theo ngày, cân nhắc registry/identity table không partition và ghi cùng transaction với bảng chi tiết.
- UUID/ULID do ứng dụng sinh không tự tạo ra global UNIQUE constraint trong database.
- InnoDB user-defined partitioned tables không hỗ trợ foreign key trong MySQL 8.0; cần có chiến lược toàn vẹn dữ liệu phù hợp.
- Kiểm tra SHOW CREATE TABLE, SHOW INDEX và INFORMATION_SCHEMA.STATISTICS trước khi migration.
- Kiểm thử duplicate, concurrent insert, partition pruning, retention và replication trước khi triển khai.

Partitioning phải phù hợp với cả đường truy cập dữ liệu lẫn quy tắc uniqueness của nghiệp vụ. Trước khi chọn partition key, hãy liệt kê các khóa cần duy nhất và xác định phạm vi duy nhất của từng khóa; nếu hai yêu cầu không tương thích, thiết kế registry hoặc thay đổi chiến lược phân vùng trước khi migration.

## Tài liệu tham khảo

- MySQL 8.0 Reference Manual — Partitioning Keys, Primary Keys, and Unique Keys: https://dev.mysql.com/doc/refman/8.0/en/partitioning-limitations-partitioning-keys-unique-keys.html
- MySQL 8.0 Reference Manual — Partitioning Limitations Relating to Storage Engines: https://dev.mysql.com/doc/refman/8.0/en/partitioning-limitations-storage-engines.html
- MySQL 8.0 Reference Manual — Partition Pruning: https://dev.mysql.com/doc/refman/8.0/en/partitioning-pruning.html
- MySQL 8.0 Reference Manual — Partition Management: https://dev.mysql.com/doc/refman/8.0/en/partitioning-management.html

