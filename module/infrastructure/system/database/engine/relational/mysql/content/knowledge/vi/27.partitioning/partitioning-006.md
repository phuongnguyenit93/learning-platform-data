# Giới hạn khóa ngoại, storage engine và kiểu dữ liệu theo phiên bản

Partitioning có thể giúp chia một bảng lớn thành các phần dữ liệu nhỏ hơn để quản lý vòng đời, loại bỏ dữ liệu cũ và hỗ trợ partition pruning. Tuy nhiên, không phải bảng nào cũng có thể partition mà vẫn giữ nguyên khóa ngoại, primary key, unique key và storage engine hiện tại.

Một thiết kế đang chạy tốt trên MySQL 5.7 có thể không còn hợp lệ khi nâng cấp lên MySQL 8.0 vì cơ chế partitioning và danh sách storage engine được hỗ trợ đã thay đổi. Kiểu dữ liệu của partition key, biểu thức partition và các ràng buộc duy nhất cũng có giới hạn riêng. Nếu không kiểm tra trước, thao tác ALTER TABLE có thể thất bại hoặc buộc phải thay đổi mô hình dữ liệu.

Bài này tập trung vào các giới hạn cần kiểm tra trước khi tạo bảng partitioned hoặc chuyển bảng hiện hữu sang partitioning: foreign key, quan hệ primary/unique key, storage engine, kiểu dữ liệu, biểu thức partition và khác biệt theo phiên bản MySQL.

## 1. Partitioning không xóa bỏ các ràng buộc của bảng

Partitioning chia các hàng của một bảng thành những partition theo một quy tắc. Về mặt SQL, ứng dụng vẫn truy vấn một tên bảng logic; MySQL xác định partition cần truy cập dựa trên partitioning expression.

Ví dụ bảng sự kiện chia theo tháng:

```sql
CREATE TABLE events (
    id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    payload JSON NULL,
    PRIMARY KEY (id, created_at)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Partitioning không biến các partition thành những bảng độc lập về mặt ràng buộc. Các quy tắc về khóa chính, unique key, foreign key và storage engine vẫn phải thỏa điều kiện của MySQL.

Trước khi partition, cần trả lời:

- Bảng có đang tham gia quan hệ foreign key ở vai trò child hoặc parent không?
- Mọi primary key và unique key có chứa đầy đủ partition key không?
- Storage engine hiện tại có hỗ trợ partitioning trên phiên bản đích không?
- Kiểu dữ liệu có hợp lệ với partitioning method đã chọn không?
- Biểu thức partition có dùng hàm hoặc toán tử được MySQL cho phép không?
- Việc đổi khóa hoặc engine có làm thay đổi semantics của ứng dụng không?

## 2. Khác biệt storage engine giữa MySQL 5.7, 8.0 và 9.7

Storage engine quyết định cách dữ liệu được lưu và nhiều khả năng của bảng. Partitioning cũng phụ thuộc engine.

| Phiên bản | Hỗ trợ partitioning | Điểm cần lưu ý |
|---|---|---|
| MySQL 5.7 | Có generic partitioning handler với phạm vi engine rộng hơn; vẫn có engine không hỗ trợ | MERGE, FEDERATED và CSV không hỗ trợ; InnoDB có giới hạn foreign key; NDB chỉ hỗ trợ KEY/LINEAR KEY trong cấu hình production |
| MySQL 8.0 | Partitioning được cung cấp bởi native handler của InnoDB và NDB | MyISAM, MERGE, CSV, FEDERATED và engine không có native handler không tạo được partitioned table |
| MySQL 9.7 | Chỉ InnoDB và NDB hỗ trợ native partitioning | Các giới hạn chính về foreign key, unique key và kiểu dữ liệu vẫn cần kiểm tra; NDB có quy tắc riêng |

### 2.1. MySQL 5.7

MySQL 5.7 sử dụng generic partitioning handler và hỗ trợ partitioning trên nhiều storage engine hơn MySQL 8.0. Tuy nhiên, hỗ trợ không đồng nghĩa mọi engine đều dùng được:

- MERGE không tương thích với user-defined partitioning.
- FEDERATED không hỗ trợ partitioning.
- CSV không hỗ trợ partitioning.
- InnoDB có thể partition nhưng không hỗ trợ foreign key trên bảng partitioned.
- NDB chỉ hỗ trợ KEY hoặc LINEAR KEY trong cấu hình được hỗ trợ cho production.

Khi nâng cấp từ 5.7, không nên suy luận rằng một bảng partitioned dùng engine cũ sẽ tiếp tục hoạt động như trước trên 8.0.

### 2.2. MySQL 8.0

Từ MySQL 8.0, partitioning do storage engine cung cấp native handler. Chỉ InnoDB và NDB hỗ trợ partitioning.

Ví dụ khai báo ENGINE=MyISAM cho bảng partitioned có thể thất bại với lỗi engine không triển khai partitioning. MySQL không tự động chuyển bảng sang InnoDB chỉ vì câu lệnh có PARTITION BY.

Với InnoDB, không cần bật một plugin partitioning riêng. Tuy nhiên, các giới hạn foreign key và unique key vẫn áp dụng.

### 2.3. MySQL 9.7

MySQL 9.7 tiếp tục giới hạn partitioning cho InnoDB và NDB. NDB chỉ hỗ trợ KEY hoặc LINEAR KEY cho user-defined partitioning; không áp dụng các kiểu RANGE, LIST hoặc HASH như với InnoDB. Với NDB table có khai báo partition key tường minh, bảng phải có explicit primary key và mọi cột trong partitioning expression phải thuộc primary key. Trường hợp PARTITION BY KEY() không liệt kê cột có quy tắc riêng.

Không nên dùng bảng so sánh này thay cho kiểm tra trên đúng phiên bản minor mà hệ thống triển khai. Khi nâng cấp, chạy thử CREATE TABLE/ALTER TABLE trên bản MySQL đích với schema thật và lưu kết quả DDL.

### 2.4. Tất cả partition trong một bảng dùng cùng storage engine

Các partition của cùng một bảng phải dùng chung storage engine. Không thể tạo partition tháng 1 bằng InnoDB, partition tháng 2 bằng MyISAM và partition tháng 3 bằng ARCHIVE trong cùng một bảng.

MySQL 8.0/9.7 có thể chấp nhận cú pháp ENGINE trong từng PARTITION clause ở một số ngữ cảnh, nhưng tùy chọn engine cấp partition không làm các partition dùng engine khác nhau; engine của bảng là engine áp dụng cho toàn bộ partition.

## 3. Giới hạn foreign key với partitioned InnoDB tables

Đây là giới hạn quan trọng nhất khi chuyển một bảng OLTP có quan hệ cha/con sang partitioning.

Trong MySQL 5.7, 8.0 và 9.7, partitioned InnoDB tables không hỗ trợ foreign key. Giới hạn áp dụng theo cả hai chiều:

1. Bảng InnoDB được partition không thể chứa foreign key tham chiếu đến bảng khác.
2. Bảng InnoDB khác cũng không thể khai báo foreign key tham chiếu đến bảng InnoDB đã partition.

Nói cách khác, một bảng partitioned InnoDB không thể đóng vai trò child table hoặc parent table trong quan hệ foreign key.

### 3.1. Ví dụ bảng child đang có foreign key

Giả sử bảng orders tham chiếu customers:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id, created_at),
    KEY idx_orders_customer (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
) ENGINE=InnoDB;
```

Nếu cố partition orders trong khi giữ foreign key, DDL không hợp lệ:

```sql
ALTER TABLE orders
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p_old VALUES LESS THAN ('2026-01-01'),
    PARTITION p_new VALUES LESS THAN (MAXVALUE)
);
```

MySQL từ chối thao tác vì InnoDB không hỗ trợ foreign key trên bảng user-partitioned. Việc thêm partition key vào primary key không giải quyết giới hạn foreign key này.

### 3.2. Ví dụ bảng parent bị tham chiếu

Giả sử bảng customers được partition theo một cột ngày:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL,
    created_at DATE NOT NULL,
    name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id, created_at)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p_old VALUES LESS THAN ('2026-01-01'),
    PARTITION p_new VALUES LESS THAN (MAXVALUE)
);
```

Một bảng khác không thể tạo foreign key tham chiếu đến customers partitioned InnoDB:

```sql
CREATE TABLE customer_notes (
    id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_created_at DATE NOT NULL,
    note TEXT,
    PRIMARY KEY (id),
    KEY idx_customer_notes_customer (customer_id, customer_created_at),
    CONSTRAINT fk_notes_customer
        FOREIGN KEY (customer_id, customer_created_at)
        REFERENCES customers(id, created_at)
) ENGINE=InnoDB;
```

Ví dụ dùng đúng cặp cột trong primary key của parent để minh họa riêng giới hạn partitioning. Dù khóa tham chiếu đã hợp lệ, MySQL vẫn không cho bảng InnoDB khác tham chiếu đến một partitioned InnoDB table.

### 3.3. NDB là ngoại lệ có phạm vi riêng

NDB Cluster cho phép bảng partitioned bằng KEY hoặc LINEAR KEY có foreign key hoặc được bảng khác tham chiếu bằng foreign key. Đây là khả năng của storage engine NDB trong kiến trúc NDB Cluster, không phải ngoại lệ cho InnoDB.

Không nên chuyển sang NDB chỉ để né giới hạn foreign key của InnoDB. NDB có mô hình triển khai, kiểu dữ liệu, index, transaction, vận hành và yêu cầu cluster riêng. Cần đánh giá toàn bộ workload và kiến trúc trước khi chọn engine.

### 3.4. Kiểu dữ liệu của cột foreign key

Ngay cả khi hai bảng không partitioned, cột foreign key và cột được tham chiếu vẫn phải tương thích:

- Bảng parent và child phải dùng cùng storage engine; chúng không được là temporary table.
- Foreign key được thực thi bởi InnoDB và NDB; với engine khác, cú pháp FOREIGN KEY có thể được parser chấp nhận nhưng constraint không được engine thực thi. Không suy ra rằng có khai báo trong DDL là đã có referential integrity.
- Với kiểu số nguyên, kích thước và signed/unsigned phải khớp; với DECIMAL, precision và scale phải tương ứng.
- Với chuỗi nonbinary, character set và collation phải giống nhau. Độ dài chuỗi không bắt buộc phải bằng nhau.
- Cả khóa được tham chiếu và khóa ngoại đều cần index phù hợp. Ở bảng child, các cột foreign key phải là phần đầu của một index theo đúng thứ tự.
- Index prefix trên cột foreign key không được hỗ trợ. Vì TEXT/BLOB cần prefix length khi lập index, chúng không thể làm cột foreign key.
- Foreign key không thể tham chiếu virtual generated column.

Trong MySQL 9.7, việc tham chiếu một key không unique của InnoDB đã bị deprecated và phụ thuộc cấu hình restrict_fk_on_non_standard_key. Nên chuyển về PRIMARY KEY hoặc UNIQUE KEY chuẩn trước khi nâng cấp.

Từ MySQL 9.6, SQL layer xử lý foreign key của InnoDB theo mặc định; biến innodb_native_foreign_keys điều khiển việc chuyển xử lý này về InnoDB. Thay đổi tầng thực thi không làm mất giới hạn partitioning: partitioned InnoDB tables vẫn không hỗ trợ foreign key.

### 3.5. Nếu nghiệp vụ bắt buộc foreign key thì chọn hướng nào?

- Giữ bảng quan hệ cốt lõi không partitioned nếu cần InnoDB foreign key.
- Chỉ partition bảng lịch sử/telemetry/archive không tham gia foreign key, sau khi xác định rõ cơ chế kiểm tra tham chiếu.
- Nếu chuyển dữ liệu sang partitioned table, thiết kế quy trình ứng dụng kiểm tra parent, xử lý orphan và reconciliation; không giả định foreign key vẫn được engine bảo vệ.
- Nếu cần cả partitioning lẫn foreign key ở cấp engine, đánh giá NDB Cluster như một lựa chọn kiến trúc riêng.

Không xóa foreign key chỉ để câu ALTER TABLE chạy được. Trước khi bỏ constraint, phải xác định nơi sẽ thực thi kiểm tra tồn tại, xử lý delete/update parent và phát hiện dữ liệu mồ côi.

## 4. Quy tắc partition key phải có trong mọi unique key

MySQL yêu cầu tất cả cột được dùng trong partitioning expression phải xuất hiện trong mọi unique key của bảng. Quy tắc này bao gồm PRIMARY KEY vì primary key cũng là một unique key.

Ví dụ partition theo created_at:

```sql
CREATE TABLE events (
    id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    payload JSON,
    PRIMARY KEY (id)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Định nghĩa trên không hợp lệ vì partition key created_at không có trong primary key (id).

Cách sửa về mặt cấu trúc khóa:

```sql
CREATE TABLE events (
    id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    payload JSON,
    PRIMARY KEY (id, created_at)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Định nghĩa mới hợp lệ theo quy tắc partition key và unique key. Tuy nhiên, primary key (id, created_at) chỉ bảo đảm cặp giá trị duy nhất; nó không bảo đảm id riêng lẻ duy nhất trên toàn bảng.

### 4.1. Quy tắc áp dụng cho mọi unique index

Giả sử bảng có:

```sql
PRIMARY KEY (id, created_at),
UNIQUE KEY uk_external_ref (external_ref)
```

Nếu partition theo created_at, unique key external_ref vẫn không hợp lệ vì thiếu created_at. Phải thay đổi unique key thành dạng bao gồm partition key, ví dụ:

```sql
UNIQUE KEY uk_external_ref_created (external_ref, created_at)
```

Nhưng khóa mới chỉ bảo đảm external_ref và created_at cùng duy nhất. Nó cho phép cùng một external_ref xuất hiện ở hai ngày khác nhau. Nếu nghiệp vụ yêu cầu external_ref duy nhất toàn cục, đây là thay đổi semantics, không chỉ là thay đổi cú pháp.

### 4.2. Hệ quả đối với ID duy nhất toàn cục

Partition theo thời gian thường muốn dùng created_at làm partition key để dễ loại bỏ partition cũ. Nhưng nếu ứng dụng đang dựa vào PRIMARY KEY(id) hoặc UNIQUE(external_id), thêm created_at vào partition key buộc mọi unique key phải chứa created_at.

Các lựa chọn cần đánh giá:

- Giữ bảng không partitioned nếu uniqueness toàn cục là yêu cầu bắt buộc và phải được MySQL enforce trực tiếp.
- Dùng composite key có chứa partition key và chấp nhận semantics uniqueness theo tổ hợp.
- Dùng một bảng registry không partitioned để quản lý ID/khóa nghiệp vụ toàn cục, với transaction và quy trình đồng bộ được thiết kế rõ.
- Dùng ID phân tán/UUID để giảm xác suất trùng ở tầng sinh ID, nhưng hiểu rằng điều này không thay thế unique constraint toàn cục trong partitioned table.

Không xóa unique key rồi coi ứng dụng tự sinh ID là đủ nếu chưa có chiến lược phát hiện và xử lý trùng lặp.

Về mặt kỹ thuật, nếu bảng không có bất kỳ unique key nào, quy tắc bắt buộc partition columns xuất hiện trong mọi unique key không còn áp dụng. Tuy nhiên, bỏ toàn bộ primary/unique key làm mất lớp bảo vệ tính duy nhất của dữ liệu và thường không phải cách sửa an toàn.

### 4.3. Biểu thức partition có nhiều cột

Nếu partitioning expression dùng nhiều cột, tất cả cột đó phải có trong mọi unique key.

Ví dụ partition theo tenant_id và ngày:

```sql
PARTITION BY HASH (tenant_id + YEAR(created_at))
PARTITIONS 16
```

Các unique key phải bao gồm cả tenant_id và created_at vì cả hai cột tham gia biểu thức. Quy tắc xét cột được tham chiếu trong expression, không chỉ tên hàm hoặc giá trị kết quả.

## 5. Kiểu dữ liệu hợp lệ cho partition key

Kiểu dữ liệu được phép phụ thuộc partitioning method. Không thể lấy một cột bất kỳ rồi dùng trực tiếp trong mọi dạng PARTITION BY.

### 5.1. RANGE, LIST và HASH dùng biểu thức số nguyên

Với các phương thức RANGE, LIST và HASH dựa trên expression, partitioning expression phải trả về giá trị số nguyên hoặc NULL.

Ví dụ dùng YEAR(created_at):

```sql
CREATE TABLE sales (
    id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (id, created_at)
)
ENGINE=InnoDB
PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p_before_2025 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

YEAR(created_at) trả về số nguyên nên có thể dùng làm partitioning expression. Khi dùng dạng expression, phải kiểm tra hàm được phép và khả năng partition pruning trên đúng phiên bản.

Không thể đơn giản dùng:

```sql
PARTITION BY RANGE (created_at)
```

với DATETIME theo dạng RANGE expression số nguyên. Nếu muốn so sánh trực tiếp theo giá trị ngày/giờ, cân nhắc RANGE COLUMNS.

### 5.2. RANGE COLUMNS và LIST COLUMNS

RANGE COLUMNS và LIST COLUMNS dùng danh sách cột thay vì expression số nguyên. Chúng hỗ trợ:

- Các kiểu số nguyên.
- DATE và DATETIME.
- Các kiểu chuỗi/binary như CHAR, VARCHAR, BINARY và VARBINARY.

DECIMAL, FLOAT và các kiểu numeric không phải số nguyên không được hỗ trợ làm partitioning columns trong các dạng này. TEXT và BLOB cũng không được hỗ trợ.

Ví dụ partition theo DATE:

```sql
CREATE TABLE daily_metrics (
    metric_id BIGINT UNSIGNED NOT NULL,
    metric_date DATE NOT NULL,
    metric_value DECIMAL(18,4) NOT NULL,
    PRIMARY KEY (metric_id, metric_date)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (metric_date) (
    PARTITION p2026_q1 VALUES LESS THAN ('2026-04-01'),
    PARTITION p2026_q2 VALUES LESS THAN ('2026-07-01'),
    PARTITION p2026_q3 VALUES LESS THAN ('2026-10-01'),
    PARTITION p2026_q4 VALUES LESS THAN ('2027-01-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Ví dụ LIST COLUMNS theo vùng:

```sql
CREATE TABLE regional_targets (
    target_id BIGINT UNSIGNED NOT NULL,
    region_code CHAR(2) NOT NULL,
    target_amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (target_id, region_code)
)
ENGINE=InnoDB
PARTITION BY LIST COLUMNS (region_code) (
    PARTITION p_asia VALUES IN ('VN', 'TH', 'SG'),
    PARTITION p_europe VALUES IN ('DE', 'FR', 'NL'),
    PARTITION p_americas VALUES IN ('US', 'CA', 'BR')
);
```

Ví dụ LIST COLUMNS minh họa khả năng dùng kiểu chuỗi. Mọi giá trị hợp lệ cần được ánh xạ vào một partition theo danh sách đã khai báo; nếu miền giá trị thay đổi, phải cập nhật partition definition.

### 5.3. KEY và LINEAR KEY

KEY/LINEAR KEY dùng hàm hash nội bộ của MySQL. Có thể sử dụng các kiểu dữ liệu hợp lệ khác nhau, ngoại trừ TEXT và BLOB.

Ví dụ:

```sql
CREATE TABLE tenant_events (
    id BIGINT UNSIGNED NOT NULL,
    tenant_code VARCHAR(40) NOT NULL,
    event_time DATETIME NOT NULL,
    PRIMARY KEY (id, tenant_code)
)
ENGINE=InnoDB
PARTITION BY KEY (tenant_code)
PARTITIONS 16;
```

Không dùng prefix index part làm partition key cho KEY. Tránh khai báo partition key dựa trên phần đầu chuỗi như tenant_code(8); dùng cột đầy đủ hoặc một cột chuẩn hóa riêng có kiểu dữ liệu phù hợp.

### 5.4. ENUM, SET, TEXT và BLOB

| Kiểu dữ liệu | RANGE/LIST/HASH expression | RANGE/LIST COLUMNS | KEY/LINEAR KEY |
|---|---|---|---|
| INT/BIGINT | Dùng trực tiếp được nếu expression hợp lệ | Hỗ trợ | Hỗ trợ |
| DATE/DATETIME | Dùng qua hàm được phép trả integer, ví dụ YEAR/TO_DAYS | Hỗ trợ trực tiếp | Hỗ trợ |
| CHAR/VARCHAR/BINARY/VARBINARY | Cần expression số nguyên phù hợp | Hỗ trợ | Hỗ trợ |
| ENUM | Không được dùng trong partitioning expression | Không nằm trong danh sách kiểu được hỗ trợ cho COLUMNS | Có thể dùng với KEY theo quy tắc KEY |
| SET | Không nên dùng trực tiếp trong expression | Không nằm trong danh sách kiểu được hỗ trợ cho COLUMNS | Có thể dùng với KEY theo quy tắc KEY |
| TEXT/BLOB | Không hỗ trợ | Không hỗ trợ | Không hỗ trợ |

Với ENUM/SET, không suy luận chỉ từ việc chúng có thể được biểu diễn nội bộ như số hoặc chuỗi. Quy tắc cho expression và KEY khác nhau. Hãy kiểm tra đúng kiểu partitioning và phiên bản đích.

### 5.5. Spatial và FULLTEXT

Các giới hạn áp dụng cho partitioned tables:

- Cột spatial như POINT, LINESTRING hoặc GEOMETRY không được dùng trong partitioned table.
- Partitioned tables không hỗ trợ FULLTEXT index hoặc FULLTEXT search.
- Temporary tables không thể được partition.

Nếu bảng cần tìm kiếm toàn văn hoặc dữ liệu GIS, hãy đánh giá việc tách dữ liệu sang bảng không partitioned hoặc một hệ thống tìm kiếm/chuyên biệt phù hợp.

## 6. Giới hạn của partitioning expression và hàm

Partitioning expression phải xác định được partition ổn định cho cùng một giá trị dữ liệu. MySQL không cho phép mọi biểu thức SQL tùy ý.

Các cấu trúc không được dùng trong partitioning expression:

- Stored procedure hoặc stored function.
- Loadable function, plugin hoặc UDF.
- Biến đã khai báo hoặc user variable.
- Subquery.
- Hàm không nằm trong danh sách MySQL cho phép.

Một số hàm built-in thường được cho phép gồm:

- YEAR(), MONTH(), DAY(), DAYOFMONTH(), DAYOFYEAR().
- TO_DAYS(), TO_SECONDS().
- UNIX_TIMESTAMP() khi dùng với cột TIMESTAMP.
- DATEDIFF(), HOUR(), MINUTE(), SECOND().
- ABS(), CEILING(), FLOOR(), MOD().

Danh sách đầy đủ phụ thuộc phiên bản. Không tự suy luận rằng một hàm built-in bất kỳ đều dùng được trong partition expression.

### 6.1. Toán tử và kiểu kết quả

Với expression partitioning dạng RANGE/LIST/HASH:

- Các phép +, - và * được cho phép khi kết quả là số nguyên hoặc NULL.
- DIV được hỗ trợ.
- Phép chia / không được cho phép trong partitioning expression.
- Các bit operator như |, &, ^, <<, >> và ~ không được cho phép.

Ví dụ biểu thức không phù hợp:

```sql
PARTITION BY RANGE (amount / 100)
```

Ngay cả khi biểu thức có vẻ trả về số, toán tử / không nằm trong tập toán tử được phép. Hãy dùng expression được hỗ trợ và kiểm tra kiểu kết quả.

### 6.2. SQL mode phải ổn định

MySQL không lưu lại SQL mode đã dùng khi tạo user-partitioned table theo cách bảo đảm biểu thức partition luôn được diễn giải giống nhau. Thay đổi SQL mode có thể làm kết quả của biểu thức thay đổi, khiến truy vấn hoặc INSERT không thể định tuyến partition như trước.

Điều này còn ảnh hưởng replication. Nếu source và replica dùng SQL mode khác nhau, partition expression có thể được đánh giá khác nhau; dữ liệu có thể được đưa vào partition khác hoặc statement thành công ở source nhưng thất bại ở replica.

Khuyến nghị:

- Ghi nhận @@GLOBAL.sql_mode và @@SESSION.sql_mode khi thiết kế bảng.
- Giữ SQL mode nhất quán giữa source và replica.
- Không đổi SQL mode tùy tiện sau khi tạo partitioned table.
- Khi nâng cấp hoặc thay cấu hình, kiểm thử INSERT/UPDATE với giá trị biên và biểu thức partition.

## 7. Khác biệt đáng chú ý theo phiên bản

| Giới hạn | MySQL 5.7 | MySQL 8.0 | MySQL 9.7 |
|---|---|---|---|
| Storage engine partitioning | Generic handler, phạm vi rộng hơn nhưng có engine không hỗ trợ | Native handler: InnoDB và NDB | Native handler: InnoDB và NDB |
| InnoDB foreign key với partitioning | Không hỗ trợ | Không hỗ trợ | Không hỗ trợ |
| NDB partitioning | KEY/LINEAR KEY | KEY/LINEAR KEY | KEY/LINEAR KEY |
| Unique key phải chứa partition columns | Có | Có | Có |
| TEXT/BLOB làm partition key | Không hỗ trợ | Không hỗ trợ | Không hỗ trợ |
| FULLTEXT trên partitioned table | Không hỗ trợ | Không hỗ trợ | Không hỗ trợ |
| Spatial columns trong partitioned table | Không hỗ trợ | Không hỗ trợ | Không hỗ trợ |
| Partition count tối đa không dùng NDB | 8192 gồm subpartitions | 8192 gồm subpartitions | 8192 gồm subpartitions |

### 7.1. Thay đổi với KEY partitioning và prefix index

Trong MySQL 8.0.21, việc dùng prefix key part trong KEY partitioning bị cảnh báo/deprecated; prefix column bị bỏ qua khi tính partition key. Nếu tất cả key parts đều dùng prefix, câu lệnh có thể thất bại.

Tài liệu MySQL 9.7 nêu rõ prefix columns không được hỗ trợ trong partitioning key và câu lệnh có thể bị từ chối. Khi nâng cấp từ 8.0, kiểm tra các bảng dùng PARTITION BY KEY() hoặc KEY(column) có index prefix.

### 7.2. ADD COLUMN ALGORITHM=INSTANT và EXCHANGE PARTITION

Trong MySQL 8.0, sau khi thực hiện ALTER TABLE ... ADD COLUMN ... ALGORITHM=INSTANT trên một partitioned table, bảng đó không còn có thể dùng EXCHANGE PARTITION theo giới hạn được tài liệu hóa. Nếu hệ thống dùng partition exchange để nạp hoặc archive dữ liệu, phải kiểm tra kế hoạch DDL trước khi áp dụng thay đổi cột instant.

### 7.3. Số partition không phải càng nhiều càng tốt

Với bảng không dùng NDB, giới hạn tối đa là 8192 partition, bao gồm subpartition. Đây là giới hạn kỹ thuật, không phải khuyến nghị thiết kế.

Hàng trăm hoặc hàng nghìn partition làm tăng metadata, file handle, chi phí mở bảng, thao tác DDL và bộ nhớ cho một số tác vụ như LOAD DATA. Chỉ tạo số partition cần thiết cho pruning và maintenance; tránh tạo partition quá nhỏ hoặc quá nhiều mà không có lợi ích đo được.

## 8. Thiết kế ví dụ: partition theo ngày nhưng vẫn cần khóa duy nhất

Giả sử hệ thống lưu audit events theo ngày, cần primary key và muốn partition để xóa dữ liệu hết hạn.

Thiết kế chưa hợp lệ:

```sql
CREATE TABLE audit_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    created_at DATETIME NOT NULL,
    actor_id BIGINT UNSIGNED NOT NULL,
    action_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (id)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Primary key chỉ có id, không chứa created_at. MySQL từ chối vì partition column phải có mặt trong mọi unique key.

Một thiết kế có thể hợp lệ về quy tắc unique key:

```sql
CREATE TABLE audit_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    created_at DATETIME NOT NULL,
    actor_id BIGINT UNSIGNED NOT NULL,
    action_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (id, created_at),
    KEY idx_audit_actor_time (actor_id, created_at)
)
ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Thiết kế này đáp ứng quy tắc unique key, nhưng primary key không còn bảo đảm id duy nhất độc lập trên toàn bảng. Nếu API hoặc hệ thống khác dựa vào id đơn lẻ làm khóa duy nhất toàn cục, cần giải quyết trước khi triển khai.

Ngoài ra, bảng partitioned InnoDB không thể có foreign key đến actor table và cũng không thể được bảng khác tham chiếu bằng foreign key. Nếu audit event phải có referential integrity do engine enforce, cần cân nhắc giữ bảng không partitioned hoặc thay đổi mô hình dữ liệu.

## 9. Kiểm tra schema trước khi chuyển sang partitioning

### 9.1. Xác nhận phiên bản và engine

```sql
SELECT VERSION();

SHOW TABLE STATUS LIKE 'orders';
SHOW CREATE TABLE orders;
```

Ghi lại phiên bản server, engine, khóa, constraint và định nghĩa hiện tại. Không dựa vào tên bảng hoặc migration cũ để đoán engine thực tế.

### 9.2. Liệt kê foreign key trong schema

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION;
```

Truy vấn giúp tìm các quan hệ mà bảng đang làm child. Để tìm bảng khác tham chiếu đến bảng dự định partition, lọc REFERENCED_TABLE_NAME theo tên bảng mục tiêu.

### 9.3. Kiểm tra partition metadata hiện có

```sql
SELECT
    TABLE_NAME,
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND PARTITION_NAME IS NOT NULL
ORDER BY TABLE_NAME, PARTITION_ORDINAL_POSITION;
```

### 9.4. Kiểm tra unique key

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    GROUP_CONCAT(
        COLUMN_NAME
        ORDER BY SEQ_IN_INDEX
        SEPARATOR ', '
    ) AS index_columns
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND NON_UNIQUE = 0
GROUP BY TABLE_NAME, INDEX_NAME
ORDER BY TABLE_NAME, INDEX_NAME;
```

Đối chiếu từng unique index với tất cả cột trong partitioning expression. Một unique index thiếu dù chỉ một partition column cũng làm định nghĩa partition không hợp lệ.

### 9.5. Kiểm tra cột và biểu thức partition

Xác nhận:

- Kiểu dữ liệu của partition column có được method hỗ trợ không?
- Expression có trả về integer/NULL nếu dùng RANGE/LIST/HASH expression không?
- Hàm sử dụng có nằm trong danh sách cho phép không?
- Có dùng TEXT/BLOB, spatial type hoặc prefix key part không?
- Cột có xuất hiện trong mọi unique key không?
- SQL mode trên source và replica có đồng nhất không?

## 10. Lộ trình migration khi schema hiện tại không tương thích

Nếu bảng đang có foreign key hoặc unique key không phù hợp, không thể chỉ thêm PARTITION BY vào cuối câu CREATE/ALTER. Cần một lộ trình thay đổi có kiểm soát.

1. **Chụp schema và dependency:** lưu SHOW CREATE TABLE, danh sách foreign key, unique key, index, trigger và luồng ứng dụng liên quan.
2. **Xác định yêu cầu integrity:** làm rõ khóa nào phải duy nhất toàn cục và quan hệ nào phải được MySQL enforce.
3. **Chọn engine đích:** xác nhận phiên bản MySQL và engine hỗ trợ partitioning.
4. **Thiết kế partition key:** chọn cột có kiểu dữ liệu hợp lệ, ổn định và phù hợp truy vấn/retention.
5. **Thiết kế lại unique key:** bảo đảm mọi unique key chứa toàn bộ partition columns; đánh giá thay đổi semantics.
6. **Xử lý foreign key:** nếu dùng partitioned InnoDB, thiết kế lại mô hình hoặc giữ bảng quan hệ không partitioned; không bỏ constraint trước khi có cơ chế thay thế.
7. **Kiểm tra dữ liệu:** tìm duplicate, orphan, NULL và giá trị ngoài miền partition.
8. **Thử DDL trên đúng version:** kiểm tra CREATE/ALTER, index, partition pruning và các thao tác maintenance.
9. **Chạy migration thử:** đo thời gian, lock, dung lượng, replication và thời gian rollback/recovery.
10. **Cutover và đối soát:** so sánh số hàng, checksum, khóa nghiệp vụ và các quan hệ tham chiếu trước/sau.

Nếu yêu cầu unique toàn cục hoặc foreign key là không thể thay đổi, giữ bảng không partitioned có thể là quyết định đúng. Có thể dùng archive table riêng, retention theo batch, index phù hợp hoặc sharding theo một kiến trúc khác.

## 11. Lỗi thường gặp và cách diễn giải

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Engine không triển khai partitioning | Dùng MyISAM hoặc engine khác không hỗ trợ trên MySQL 8.0/9.7 | Chọn InnoDB/NDB nếu phù hợp và kiểm tra lại schema |
| Foreign key không được hỗ trợ | Partitioned InnoDB table đang có hoặc được tham chiếu bởi FK | Thiết kế lại quan hệ hoặc giữ bảng không partitioned |
| PRIMARY KEY must include all columns in partitioning function | Primary/unique key thiếu partition column | Thiết kế lại mọi unique key, đánh giá uniqueness toàn cục |
| Partition function returns wrong type | Expression không trả integer/NULL như yêu cầu | Dùng hàm/biểu thức được hỗ trợ hoặc COLUMNS partitioning |
| Function not allowed in partition expression | Dùng stored function, UDF hoặc hàm ngoài danh sách | Chuyển sang built-in function được phép |
| Không tạo được partition trên TEXT/BLOB | Kiểu dữ liệu không được hỗ trợ | Dùng cột chuẩn hóa phù hợp hoặc thiết kế lại partition key |
| FULLTEXT index không tạo được | Partitioned table không hỗ trợ FULLTEXT | Tách tìm kiếm toàn văn sang bảng/index riêng |
| Spatial column không tương thích | Partitioned table không hỗ trợ spatial data types | Tách dữ liệu GIS sang bảng không partitioned |
| Kết quả partition khác giữa source/replica | SQL mode khác nhau hoặc expression phụ thuộc mode | Đồng bộ SQL mode và kiểm tra biểu thức |
| EXCHANGE PARTITION thất bại sau ADD COLUMN INSTANT | Giới hạn của thao tác DDL trên partitioned table | Kiểm tra thứ tự migration và khả năng exchange trước khi ADD COLUMN |

## 12. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| InnoDB hỗ trợ foreign key nên bảng InnoDB partitioned cũng hỗ trợ | InnoDB foreign key và user-defined partitioning không tương thích |
| Chỉ primary key phải chứa partition key | Mọi unique key, kể cả primary key, đều phải chứa tất cả partition columns |
| Thêm partition column vào unique key không đổi nghiệp vụ | Unique theo tổ hợp không tương đương unique toàn cục của cột cũ |
| Mọi storage engine đều partition được | MySQL 8.0/9.7 chỉ có InnoDB và NDB native partitioning |
| NDB và InnoDB dùng cùng partition type | NDB chỉ hỗ trợ KEY/LINEAR KEY cho user-defined partitioning |
| Có thể dùng trực tiếp DATETIME trong mọi RANGE expression | RANGE expression yêu cầu kết quả integer; dùng RANGE COLUMNS cho DATE/DATETIME |
| TEXT/BLOB dùng được nếu có index prefix | TEXT/BLOB không được hỗ trợ làm partition key |
| Hàm built-in nào cũng dùng được | Chỉ một danh sách hàm cụ thể được cho phép |
| Partition càng nhiều càng nhanh | Nhiều partition tăng metadata và chi phí quản lý; 8192 là giới hạn kỹ thuật, không phải mục tiêu |
| Bỏ foreign key là xong | Cần có cơ chế thay thế để bảo vệ referential integrity và đối soát orphan |

## 13. Checklist trước khi tạo hoặc nâng cấp partitioned table

- Đã xác nhận đúng MySQL version và storage engine chưa?
- Engine có native partitioning handler trên phiên bản đích không?
- Bảng có foreign key ở vai trò child hoặc parent không?
- Nếu dùng InnoDB, đã xác nhận không còn FK liên quan đến bảng partitioned chưa?
- Nếu dùng NDB, partition method có phải KEY/LINEAR KEY và thỏa yêu cầu PK không?
- Tất cả partition columns có trong mọi primary/unique key không?
- Thay đổi composite key có làm mất uniqueness toàn cục mà ứng dụng đang dựa vào không?
- Kiểu dữ liệu có hợp lệ với RANGE/LIST/HASH/COLUMNS/KEY không?
- Có TEXT/BLOB, spatial type, FULLTEXT hoặc temporary table không tương thích không?
- Partition expression có dùng hàm được phép và trả đúng kiểu không?
- SQL mode giữa source và replica có giống nhau không?
- Số partition có hợp lý với dung lượng và maintenance workload không?
- Có kế hoạch migration, validation, cutover và rollback không?
- Đã thử DDL trên đúng phiên bản MySQL mục tiêu chưa?

## 14. Tài liệu tham khảo chính thức

- [MySQL 5.7 — Restrictions and Limitations on Partitioning](https://dev.mysql.com/doc/mysql-partitioning-excerpt/5.7/en/partitioning-limitations.html)
- [MySQL 5.7 — Partitioning Limitations Relating to Storage Engines](https://dev.mysql.com/doc/mysql-partitioning-excerpt/5.7/en/partitioning-limitations-storage-engines.html)
- [MySQL 8.0 — Restrictions and Limitations on Partitioning](https://dev.mysql.com/doc/refman/8.0/en/partitioning-limitations.html)
- [MySQL 8.0 — Partitioning Keys, Primary Keys, and Unique Keys](https://dev.mysql.com/doc/refman/8.0/en/partitioning-limitations-partitioning-keys-unique-keys.html)
- [MySQL 8.0 — Partitioning Limitations Relating to Storage Engines](https://dev.mysql.com/doc/refman/8.0/en/partitioning-limitations-storage-engines.html)
- [MySQL 9.7 — Partitioning Overview](https://dev.mysql.com/doc/refman/9.7/en/partitioning-overview.html)
- [MySQL 9.7 — Restrictions and Limitations on Partitioning](https://dev.mysql.com/doc/refman/9.7/en/partitioning-limitations.html)
- [MySQL 9.7 — Foreign Key Constraints](https://dev.mysql.com/doc/refman/9.7/en/create-table-foreign-keys.html)
- [MySQL 8.0 — COLUMNS Partitioning and permitted data types](https://dev.mysql.com/doc/refman/8.0/en/partitioning-columns.html)
- [MySQL 8.0 — KEY Partitioning](https://dev.mysql.com/doc/refman/8.0/en/partitioning-key.html)
- [MySQL 9.7 — COLUMNS Partitioning and permitted data types](https://dev.mysql.com/doc/refman/9.7/en/partitioning-columns.html)
- [MySQL 9.7 — KEY Partitioning](https://dev.mysql.com/doc/refman/9.7/en/partitioning-key.html)
- [MySQL 9.7 — Partitioning Limitations Relating to Functions](https://dev.mysql.com/doc/refman/9.7/en/partitioning-limitations-functions.html)

## Kết luận

Trước khi partition một bảng MySQL, phải kiểm tra đồng thời foreign key, primary/unique key, storage engine, kiểu dữ liệu và biểu thức partition. InnoDB partitioned tables không hỗ trợ foreign key ở cả phía child lẫn parent; mọi unique key phải chứa tất cả cột trong partitioning expression; MySQL 8.0/9.7 chỉ hỗ trợ partitioning native trên InnoDB và NDB. RANGE/LIST/HASH expression cần kết quả integer, trong khi RANGE COLUMNS/LIST COLUMNS hỗ trợ trực tiếp các kiểu integer, DATE/DATETIME và string phù hợp; TEXT/BLOB và spatial columns có giới hạn riêng. Khác biệt phiên bản, SQL mode và thay đổi semantics của unique key có thể ảnh hưởng trực tiếp đến migration. Hãy xác nhận các điều kiện này trên đúng phiên bản đích trước khi chạy DDL, và giữ nguyên ràng buộc nghiệp vụ bằng một thiết kế thay thế rõ ràng nếu partitioning khiến MySQL không còn enforce được chúng.
