# Replica identity và yêu cầu đối với UPDATE hoặc DELETE

Trong PostgreSQL logical replication, một thay đổi INSERT có thể được gửi bằng cách truyền row mới. Với UPDATE hoặc DELETE, subscriber còn phải biết **row cũ nào trên subscriber tương ứng với row vừa thay đổi trên publisher**. PostgreSQL cần một định danh ổn định để tìm row đó. Cơ chế này được gọi là **replica identity**.

Replica identity quyết định thông tin về row cũ được ghi vào WAL và gửi qua logical replication. Thông thường PostgreSQL dùng primary key. Nếu bảng không có primary key, bạn có thể chọn một unique index đủ điều kiện hoặc dùng REPLICA IDENTITY FULL để gửi toàn bộ row cũ. Nếu không có identity phù hợp, UPDATE và DELETE trên bảng được publish có thể thất bại khi logical decoding/replication cần xác định row.

Bài học này giải thích bốn chế độ DEFAULT, USING INDEX, FULL và NOTHING; yêu cầu đối với primary key/unique index; cách publisher gửi old row identity; cách subscriber áp dụng UPDATE/DELETE; các giới hạn với publication column lists, partitioned tables và schema changes; cùng cách phát hiện và xử lý lỗi replica identity.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao logical replication cần nhận diện row cũ cho UPDATE và DELETE.
2. Phân biệt replica identity với primary key và unique constraint.
3. Giải thích REPLICA IDENTITY DEFAULT, USING INDEX, FULL và NOTHING.
4. Chọn primary key hoặc unique index phù hợp làm replica identity.
5. Cấu hình replica identity bằng ALTER TABLE.
6. Hiểu dữ liệu old key/old tuple được ghi vào WAL và truyền cho subscriber.
7. Phân biệt yêu cầu của publisher với cấu trúc cần có ở subscriber.
8. Nhận diện các lỗi khi publication phát UPDATE/DELETE.
9. Hiểu tác động của FULL tới WAL volume, CPU và row lookup.
10. Thiết kế migration để thêm/chuyển replica identity mà giảm downtime.
11. Xử lý column lists, row filters, partitions, TOAST và schema drift.
12. Kiểm tra logical replication bằng SQL, logs và test cases.

> **Phiên bản:** Bài học tập trung PostgreSQL logical replication tích hợp. Một số behavior/options phụ thuộc major version. Nếu dùng extension hoặc CDC connector, hãy kiểm tra thêm cách decoder/connector diễn giải replica identity.

## 2. Vì sao UPDATE và DELETE cần nhận diện row cũ?

Giả sử publisher có bảng:

```sql
CREATE TABLE public.customer (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL
);
```

Một transaction chạy:

```sql
UPDATE public.customer
SET display_name = 'An Nguyen'
WHERE customer_id = 42;

DELETE FROM public.customer
WHERE customer_id = 42;
```

Subscriber cần biết row nào phải được cập nhật hoặc xóa. customer_id=42 là định danh ổn định, vì vậy PostgreSQL có thể gửi old key thay vì toàn bộ row cũ.

### INSERT khác UPDATE/DELETE

- INSERT: subscriber nhận row mới và thêm row.
- UPDATE: subscriber phải tìm row cũ, sau đó áp dụng giá trị mới.
- DELETE: subscriber phải tìm row cũ và xóa nó.
- TRUNCATE: xử lý theo table-level operation; không cần row identity cho từng row.

Replica identity chủ yếu quan trọng với UPDATE và DELETE. Bảng chỉ publish INSERT không cần old-row identity để gửi insert records.

## 3. Luồng replica identity trong logical replication

```text
Publisher table
      |
      | UPDATE / DELETE
      v
Replica identity determines old-row key
      |
      v
WAL logical decoding
      |
      v
Logical replication stream
      |
      v
Subscriber apply worker
      |
      +--> locate old row
      |
      +--> UPDATE new values / DELETE matched row
```

Publisher quyết định old-row identity nào được ghi và gửi. Subscriber dùng thông tin identity nhận được để tìm row tương ứng trong table đích. Subscriber phải có schema tương thích và dữ liệu phù hợp để apply thành công.

### Replica identity không phải cơ chế đồng bộ schema

Logical replication không tự động sao chép DDL nói chung. Việc tạo primary key/index, thay đổi kiểu dữ liệu, thêm cột hoặc đổi replica identity cần được triển khai phù hợp ở subscriber và publisher. Một publication/subscription đang hoạt động không tự bảo đảm schema hai bên luôn giống nhau.

## 4. Replica identity là gì?

Replica identity là cấu hình ở cấp table cho biết PostgreSQL cần lưu thông tin nào về row cũ trong WAL để logical decoding có thể phát UPDATE/DELETE.

Các chế độ:

| Mode | Ý nghĩa |
|---|---|
| DEFAULT | Dùng primary key nếu bảng có primary key |
| USING INDEX | Dùng một unique index đủ điều kiện do người dùng chọn |
| FULL | Ghi toàn bộ old row |
| NOTHING | Không ghi old-row identity |

Kiểm tra cấu hình:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relreplident AS replica_identity_code
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname;
```

relreplident là mã nội bộ: d là default, i là index, f là full và n là nothing. Trong vận hành thường ngày, dùng \d+ table_name trong psql hoặc kiểm tra catalog để xem chi tiết.

## 5. DEFAULT: dùng primary key

DEFAULT là chế độ mặc định của PostgreSQL. Nếu bảng có primary key, primary key được dùng làm replica identity.

```sql
CREATE TABLE public.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
);

ALTER TABLE public.orders
REPLICA IDENTITY DEFAULT;
```

Với UPDATE hoặc DELETE, PostgreSQL chỉ cần gửi các giá trị primary key cũ làm định danh, cùng dữ liệu mới cần thiết cho update.

### Vì sao DEFAULT thường là lựa chọn tốt?

- Primary key có tính duy nhất.
- Các cột primary key không thể NULL.
- Có unique index hỗ trợ lookup.
- Old-row identity nhỏ hơn gửi toàn bộ row.
- Ý nghĩa khóa thường đã được ứng dụng xác định.

### Bảng không có primary key

Nếu table không có primary key, DEFAULT không tự chọn một cột bất kỳ làm identity. PostgreSQL không thể giả định email, name hay một giá trị khác là duy nhất. Khi publication phát UPDATE/DELETE, cần cấu hình một identity phù hợp.

## 6. Kiểm tra primary key hiện có

Liệt kê primary key constraints:

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    con.conname AS primary_key_name,
    pg_catalog.pg_get_constraintdef(con.oid) AS definition
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS t
  ON t.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = t.relnamespace
WHERE con.contype = 'p'
ORDER BY n.nspname, t.relname;
```

Một bảng có primary key thường đã có unique index tương ứng. Nếu DEFAULT đang bật, không cần chỉ định thêm USING INDEX cho primary key đó.

### Composite primary key

Primary key có thể gồm nhiều cột:

```sql
CREATE TABLE public.order_items (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
```

Identity là tổ hợp (order_id, line_no). Cả hai giá trị cũ cần được truyền để xác định đúng row.

## 7. PRIMARY KEY và replica identity khác nhau thế nào?

Primary key là constraint của relational model: nó bảo đảm uniqueness và NOT NULL, đồng thời thường là khóa tham chiếu của foreign keys. Replica identity là table setting điều khiển old-row information cho logical decoding.

| Khái niệm | Vai trò |
|---|---|
| Primary key | Ràng buộc dữ liệu, định danh row trong schema |
| Unique constraint/index | Bảo đảm uniqueness theo các cột/index expression |
| Replica identity | Chọn old-row identity được ghi cho logical replication |

Một primary key có thể tự động làm replica identity ở mode DEFAULT. Nhưng replica identity cũng có thể dùng một unique index khác hoặc toàn bộ row bằng FULL.

### Không nên tạo primary key chỉ để “làm replication chạy” mà không xét dữ liệu

Trước khi thêm primary key, phải xác định cột/cặp cột thực sự duy nhất, không NULL và có ý nghĩa ổn định. Nếu dữ liệu hiện tại có duplicates hoặc NULL, việc thêm constraint sẽ thất bại hoặc đòi hỏi làm sạch dữ liệu trước.

## 8. USING INDEX: dùng unique index

Nếu bảng không có primary key nhưng có một unique index phù hợp, có thể chọn index đó làm replica identity.

Ví dụ:

```sql
CREATE TABLE public.account_profile (
    account_id BIGINT NOT NULL,
    external_ref TEXT NOT NULL,
    full_name TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX account_profile_external_ref_uq
ON public.account_profile (external_ref);

ALTER TABLE public.account_profile
REPLICA IDENTITY USING INDEX account_profile_external_ref_uq;
```

Khi external_ref là duy nhất và không NULL, PostgreSQL có thể dùng nó để tìm old row.

### Điều kiện của index

Index được chọn làm replica identity phải:

- Là unique index.
- Không phải partial index.
- Không phải deferrable.
- Chỉ chứa các cột được đánh dấu NOT NULL.
- Là index hợp lệ và có thể dùng làm định danh row.

Hãy kiểm tra tài liệu PostgreSQL đúng major version và catalog/index definition trước khi thay đổi. Một unique index cho phép NULL ở một hoặc nhiều cột không đáp ứng yêu cầu identity này.

### Vì sao phải NOT NULL?

Một unique index trong PostgreSQL có thể cho phép nhiều rows chứa NULL theo semantics mặc định. Điều đó không bảo đảm định danh duy nhất như replica identity cần. Các cột identity phải có giá trị không NULL để xác định old row đáng tin cậy.

## 9. Tìm unique indexes đủ điều kiện

Liệt kê indexes trên một bảng:

```sql
SELECT
    index_class.relname AS index_name,
    idx.indisunique,
    idx.indisvalid,
    idx.indisready,
    idx.indimmediate,
    idx.indpred IS NOT NULL AS is_partial,
    pg_catalog.pg_get_indexdef(idx.indexrelid) AS index_definition
FROM pg_catalog.pg_index AS idx
JOIN pg_catalog.pg_class AS index_class
  ON index_class.oid = idx.indexrelid
WHERE idx.indrelid = 'public.account_profile'::regclass
ORDER BY index_class.relname;
```

Query này giúp nhìn thấy unique/valid/partial/immediate properties. Cần kiểm tra thêm tất cả index key columns đều NOT NULL; đừng suy luận chỉ từ indisunique=true.

Kiểm tra nullability của các cột trong index:

```sql
SELECT
    a.attname AS column_name,
    a.attnotnull AS is_not_null
FROM pg_catalog.pg_index AS i
CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
JOIN pg_catalog.pg_attribute AS a
  ON a.attrelid = i.indrelid
 AND a.attnum = k.attnum
WHERE i.indexrelid = 'public.account_profile_external_ref_uq'::regclass
  AND k.ord <= i.indnkeyatts
ORDER BY k.ord;
```

Index expressions hoặc included columns cần được xem xét theo đúng semantics/version; replica identity index phải xác định row bằng các key columns phù hợp. Ưu tiên index đơn giản trên các cột NOT NULL.

## 10. Cấu hình USING INDEX

Lệnh:

```sql
ALTER TABLE public.account_profile
REPLICA IDENTITY USING INDEX account_profile_external_ref_uq;
```

Kiểm tra bằng psql:

```text
\d+ public.account_profile
```

Hoặc catalog pg_class.relreplident và index liên quan.

### Index được tham chiếu bởi replica identity

Không thể tùy tiện drop index đang được dùng làm replica identity. Trước khi drop/rebuild, chuyển replica identity sang một index khác hoặc DEFAULT/FULL phù hợp. Việc thay identity cần được phối hợp với publication, subscriber và workload.

## 11. FULL: gửi toàn bộ old row

Khi không có primary key hoặc unique index thích hợp, có thể dùng:

```sql
ALTER TABLE public.legacy_customer
REPLICA IDENTITY FULL;
```

Với FULL, PostgreSQL ghi thông tin toàn bộ old row để logical decoding có thể gửi row cũ. Subscriber có thể dùng các giá trị này để tìm row cần update/delete.

### Khi nào FULL hữu ích?

- Bảng legacy không có khóa duy nhất.
- Không thể thêm primary key/unique index ngay.
- Cần CDC consumer nhận old row values để xây dựng change event.
- Dùng tạm trong migration trước khi có stable key.

### Chi phí

- WAL có thể lớn hơn vì old tuple chứa nhiều cột.
- Logical decoding phải xử lý nhiều dữ liệu hơn.
- Subscriber có thể phải tìm row bằng nhiều cột thay vì index key nhỏ.
- Row lớn/TOASTed data có thể làm payload và I/O tăng.
- Các kiểu dữ liệu không có equality semantics phù hợp có thể gây giới hạn khi tìm row trên subscriber.

FULL là giải pháp tương thích nhưng thường không phải lựa chọn hiệu năng tốt nhất cho bảng lớn/write-heavy.

## 12. NOTHING: không ghi old-row identity

Có thể cấu hình:

```sql
ALTER TABLE public.event_ingest
REPLICA IDENTITY NOTHING;
```

NOTHING không lưu old-row identity cho table. Nó phù hợp với bảng chỉ publish INSERT hoặc khi không cần logical decoding UPDATE/DELETE cho bảng đó.

### Nếu publication phát UPDATE/DELETE?

Khi logical replication cần phát UPDATE hoặc DELETE từ bảng không có replica identity, thao tác có thể thất bại với lỗi yêu cầu replica identity. NOTHING không có nghĩa PostgreSQL tự tìm một row bằng mọi cột.

### Ví dụ INSERT-only publication

Một event log append-only có thể chỉ publish inserts:

```sql
CREATE PUBLICATION event_pub
FOR TABLE public.event_ingest
WITH (publish = 'insert');

ALTER TABLE public.event_ingest
REPLICA IDENTITY NOTHING;
```

Nếu sau này publication được đổi để publish update/delete, phải cấu hình identity phù hợp trước khi workload phát sinh những thao tác đó.

## 13. So sánh bốn chế độ

| Chế độ | Old-row data | Điều kiện | Hiệu năng thường thấy |
|---|---|---|---|
| DEFAULT | Primary key columns | Có PK | Tốt, thường được khuyến nghị |
| USING INDEX | Unique index key columns | Unique, non-partial, non-deferrable, key columns NOT NULL | Tốt nếu index phù hợp |
| FULL | Toàn bộ old row | Không cần PK/unique identity | Có thể tốn WAL/CPU/lookup |
| NOTHING | Không có old-row identity | Chỉ phù hợp khi không cần UPDATE/DELETE replication | Không đáp ứng update/delete |

### Quy tắc lựa chọn

1. Có primary key phù hợp: dùng DEFAULT.
2. Không có primary key nhưng có unique key ổn định: dùng USING INDEX.
3. Không thể tạo key nhưng cần update/delete replication: cân nhắc FULL và đo chi phí.
4. Chỉ publish insert hoặc không cần update/delete: NOTHING có thể phù hợp.

## 14. UPDATE được truyền như thế nào?

Giả sử:

```sql
UPDATE public.account_profile
SET full_name = 'New Name'
WHERE external_ref = 'EXT-42';
```

Với replica identity là unique index external_ref, publisher cần gửi old identity external_ref='EXT-42' và các giá trị mới của row theo publication/schema mapping.

Subscriber:

1. Nhận update message.
2. Dùng old identity để tìm row hiện tại.
3. Áp dụng các cột mới.
4. Ghi kết quả vào subscriber transaction.

### UPDATE identity column

Nếu chính cột identity thay đổi, publisher vẫn cần old identity để tìm row trước khi thay đổi và gửi giá trị mới. Ví dụ đổi external_ref từ EXT-42 sang EXT-43: subscriber phải tìm bằng old value EXT-42, sau đó cập nhật sang EXT-43.

Đây là lý do old key cần được giữ lại trong change record.

## 15. DELETE được truyền như thế nào?

Ví dụ:

```sql
DELETE FROM public.account_profile
WHERE external_ref = 'EXT-42';
```

Publisher gửi định danh row cũ. Subscriber tìm row tương ứng và xóa.

Nếu subscriber không có row matching, apply có thể báo lỗi vì không tìm thấy tuple cần xóa. Nguyên nhân có thể là:

- Subscriber thiếu row từ trước.
- Một thao tác ghi trực tiếp vào subscriber làm lệch dữ liệu.
- Schema/identity mapping không tương thích.
- Subscription bắt đầu từ một trạng thái không đồng bộ.
- Data migration hoặc manual cleanup chỉ chạy ở một phía.

### Không tự ý sửa subscriber

Trong mô hình một chiều, subscriber thường được coi là read-only đối với dữ liệu được replicate. Manual UPDATE/DELETE ở subscriber có thể tạo divergence và khiến apply worker lỗi ở transaction sau.

## 16. Replica identity ở publisher và subscriber

Replica identity được cấu hình trên publisher quyết định old-row identity được ghi vào WAL và gửi trong logical replication stream. Subscriber nhận thông tin identity đó để locate row.

Ở subscriber, replica identity setting không thay thế identity mà publisher gửi. Tuy nhiên subscriber vẫn cần schema tương thích và dữ liệu nhất quán. Index phù hợp ở subscriber giúp lookup nhanh; nếu không có index phù hợp, việc tìm row có thể tốn kém hoặc gặp giới hạn tùy loại identity/kiểu dữ liệu.

Nếu subscriber đồng thời publish dữ liệu tiếp sang một subscriber khác, replica identity của subscriber lại có ý nghĩa đối với luồng outgoing của chính nó.

### Tạo khóa ở cả hai phía

Trong nhiều triển khai, nên tạo cùng primary key/unique index ở cả publisher và subscriber. DDL không tự động được logical replication đồng bộ, vì vậy triển khai schema migration ở cả hai phía theo thứ tự an toàn.

## 17. Điều gì xảy ra khi không có replica identity?

Một bảng không có primary key và ở mode DEFAULT không có old-row identity phù hợp. Nếu publication yêu cầu UPDATE/DELETE, logical replication không thể tạo change record đủ thông tin để apply chính xác.

Ví dụ:

```sql
CREATE TABLE public.inventory_snapshot (
    warehouse_code TEXT NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL
);

CREATE PUBLICATION inventory_pub
FOR TABLE public.inventory_snapshot;

UPDATE public.inventory_snapshot
SET quantity = 10
WHERE warehouse_code = 'WH1'
  AND sku = 'SKU-1';
```

Nếu bảng vẫn dùng DEFAULT mà không có primary key, update có thể báo lỗi replica identity khi logical decoding xử lý.

### Xác định trước khi publish

Trước khi đưa table vào publication có update/delete:

- Xác nhận primary key hoặc unique index phù hợp.
- Kiểm tra relreplident.
- Kiểm tra column list có chứa identity columns.
- Chạy test update/delete trên môi trường thử.
- Theo dõi publisher logs và subscriber apply status.

## 18. Publication và danh sách thao tác được publish

Publication có thể chọn các thao tác:

```sql
CREATE PUBLICATION app_pub
FOR TABLE public.orders
WITH (publish = 'insert, update, delete, truncate');
```

Giá trị mặc định trong các phiên bản hiện đại thường publish insert, update, delete, truncate. Hãy kiểm tra cấu hình cụ thể:

```sql
SELECT
    pubname,
    pubinsert,
    pubupdate,
    pubdelete,
    pubtruncate
FROM pg_catalog.pg_publication;
```

### Chỉ publish INSERT

Nếu bảng append-only, có thể giới hạn publication:

```sql
CREATE PUBLICATION audit_insert_pub
FOR TABLE public.audit_events
WITH (publish = 'insert');
```

Không publish UPDATE/DELETE nghĩa là các thao tác đó không được truyền cho subscription qua publication này. Nó không ngăn ứng dụng thực hiện update/delete trên publisher.

## 19. Publication column lists và replica identity

Publication có thể giới hạn các cột được gửi. Tuy nhiên, nếu publication có column list, danh sách phải bao gồm tất cả cột thuộc replica identity để subscriber có thể xác định row cũ.

Ví dụ:

```sql
CREATE PUBLICATION account_pub
FOR TABLE public.account_profile (
    external_ref,
    full_name,
    updated_at
);
```

Nếu external_ref là replica identity index, column list phải giữ external_ref. Nếu thiếu identity column, cấu hình publication có thể bị từ chối hoặc không đáp ứng điều kiện cho update/delete tùy phiên bản.

### FULL và column list

Với REPLICA IDENTITY FULL, old identity là toàn bộ row. Column list cần được thiết kế sao cho đủ identity columns; vì identity là toàn bộ row nên giới hạn column list có thể không tương thích với mục tiêu đó. Kiểm tra quy tắc version cụ thể trước khi triển khai.

## 20. Row filters và old row

Publication có thể dùng row filter để chỉ publish rows thỏa biểu thức:

```sql
CREATE PUBLICATION active_customer_pub
FOR TABLE public.customer
WHERE (status = 'active');
```

Đối với UPDATE/DELETE, row filter có semantics liên quan row cũ; một thay đổi làm row chuyển từ match sang non-match hoặc ngược lại cần được hiểu đúng theo version. Không coi row filter là một cơ chế đồng bộ đầy đủ hai chiều.

### Tương tác với replica identity

Replica identity xác định row cần update/delete; row filter xác định thay đổi có thuộc publication hay không. Hai cơ chế có vai trò khác nhau. Identity columns vẫn phải được truyền theo yêu cầu của publication column list.

## 21. Unique index và NULL semantics

Một unique index có thể cho phép nhiều NULL values theo default NULL-distinct behavior. Vì vậy, chỉ UNIQUE không đủ chứng minh index có thể làm replica identity.

Ví dụ không phù hợp:

```sql
CREATE TABLE public.device (
    serial_no TEXT,
    model TEXT NOT NULL
);

CREATE UNIQUE INDEX device_serial_uq
ON public.device (serial_no);
```

serial_no nullable, nên index không đáp ứng điều kiện replica identity index. Hãy xác định dữ liệu và constraint trước:

```sql
ALTER TABLE public.device
ALTER COLUMN serial_no SET NOT NULL;

ALTER TABLE public.device
REPLICA IDENTITY USING INDEX device_serial_uq;
```

Chỉ chạy SET NOT NULL nếu dữ liệu hiện tại không có NULL và business rule cho phép. Nếu không, làm sạch/backfill dữ liệu và triển khai constraint theo migration plan.

## 22. Partial unique index không dùng được

Ví dụ:

```sql
CREATE UNIQUE INDEX active_user_email_uq
ON public.users (email)
WHERE is_active;
```

Index này chỉ bảo đảm uniqueness với rows thỏa predicate. Rows ngoài predicate có thể trùng email, nên không thể định danh mọi row trong table. Partial index không đủ điều kiện làm replica identity.

Nếu email cần định danh toàn bộ rows, phải tạo một unique index phù hợp trên toàn bộ tập dữ liệu hoặc chọn một key khác.

## 23. Deferrable unique constraints

Một unique constraint có thể được khai báo DEFERRABLE, cho phép kiểm tra uniqueness trễ tới cuối transaction. Replica identity index cần uniqueness có hiệu lực ngay để dùng làm row identifier; index deferrable không đáp ứng điều kiện.

Ví dụ constraint deferrable:

```sql
CREATE TABLE public.external_account (
    external_id TEXT NOT NULL,
    owner_id BIGINT NOT NULL,
    CONSTRAINT external_account_uq
        UNIQUE (external_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

Nếu cần identity, thiết kế một unique index/constraint không deferrable đáp ứng yêu cầu. Không đổi constraint semantics chỉ vì replication mà không xem xét transaction behavior của ứng dụng.

## 24. Composite unique index

Một unique index nhiều cột có thể làm replica identity nếu toàn bộ key columns thỏa điều kiện:

```sql
CREATE UNIQUE INDEX shipment_key_uq
ON public.shipment (tenant_id, shipment_no);

ALTER TABLE public.shipment
REPLICA IDENTITY USING INDEX shipment_key_uq;
```

Nếu hai cột đều NOT NULL, tổ hợp của chúng định danh một row. Subscriber cần có cùng cột identity và dữ liệu/schema tương thích để apply.

### Composite key trade-off

- Nhiều cột hơn làm identity payload lớn hơn.
- Key columns cần ổn định và có semantics rõ.
- Index lớn hơn có thể ảnh hưởng write performance.
- Nếu một key column thay đổi, old composite key vẫn cần để tìm row trước update.

## 25. Tác động của FULL tới WAL volume

Giả sử một table có 40 cột, bao gồm JSON/text lớn. Với identity index chỉ gồm một BIGINT, old-row identity có thể nhỏ. Với FULL, logical decoding cần thông tin toàn bộ old row.

### Tác động có thể thấy

- WAL bytes tăng trên update/delete-heavy workload.
- Logical decoding throughput giảm.
- Network payload lớn hơn.
- Subscriber apply tốn CPU và lookup work hơn.
- Replication lag tăng khi consumer không theo kịp.

Không có một hệ số tăng cố định. Chi phí phụ thuộc row width, số cột thay đổi, TOAST usage, workload, compression và decoder implementation.

### Đo trước/sau

Theo dõi:

- pg_stat_wal.wal_bytes delta.
- WAL records/FPI nếu workload liên quan.
- Logical slot retained WAL distance.
- Publisher CPU/WAL write throughput.
- Subscriber apply lag.
- Network bytes.

So sánh cùng workload và cùng sample window.

## 26. FULL và row lookup trên subscriber

Với identity index, subscriber có thể dùng key columns để tìm row. Với FULL, subscriber phải dựa trên old-row values của nhiều cột để nhận diện row. Nếu không có index phù hợp, lookup có thể cần scan nhiều rows.

### Bảng lớn

Một table có hàng trăm triệu rows và update/delete rate cao sẽ chịu chi phí đáng kể nếu mỗi change phải dò bằng nhiều cột. FULL nên được xem như giải pháp khi không thể có key tốt, không phải default tối ưu.

### Equality semantics

Việc so sánh old-row values phụ thuộc data types và equality operators. Một số kiểu dữ liệu hoặc extension types có thể không hỗ trợ cách so sánh cần thiết. Kiểm thử update/delete với đúng schema thực tế trước khi dựa vào FULL.

## 27. Replica identity và TOAST

TOAST lưu trữ giá trị lớn bên ngoài heap tuple chính khi cần. Các cột text, jsonb, bytea hoặc arrays lớn có thể được TOAST.

Với identity là primary key/unique index, PostgreSQL chỉ cần old key columns để xác định row. Với FULL, old-row data rộng hơn và có thể làm WAL/decoder work tăng đáng kể.

### Cách thiết kế

- Ưu tiên identity key nhỏ, ổn định.
- Tránh chọn JSON/text payload lớn làm key.
- Đặt primary key/unique key ở các cột có semantics rõ.
- Đo WAL/replication throughput trên rows có TOAST data.

Đừng giả định mọi old TOAST value luôn được truyền theo cùng cách trong mọi output plugin; kiểm tra decoder/protocol version và test event payload thực tế.

## 28. UPDATE primary key

PostgreSQL cho phép update primary key nếu constraints vẫn hợp lệ:

```sql
UPDATE public.orders
SET order_id = 90042
WHERE order_id = 42;
```

Logical replication cần old identity order_id=42 để tìm row subscriber, sau đó apply new key 90042.

### Tác động ứng dụng

Primary key thường nên ổn định. Thay đổi PK có thể ảnh hưởng foreign keys, cache keys, application references và downstream consumers. Logical replication xử lý được old/new identity nhưng không loại bỏ các tác động nghiệp vụ.

### Subscriber conflict

Nếu subscriber đã có row với new key 90042, update có thể vi phạm unique constraint và apply worker dừng. Đây là data divergence/constraint conflict cần điều tra.

## 29. DELETE và subscriber không có matching row

Nếu publisher xóa row có identity customer_id=42 nhưng subscriber không có row đó, apply worker có thể báo không tìm thấy tuple để xóa.

Nguyên nhân:

- Subscription khởi tạo từ snapshot không nhất quán.
- Table đã bị sửa trực tiếp ở subscriber.
- Một transaction/DDL migration bị bỏ sót.
- Publication row filter/column list thay đổi.
- Subscription đã bị disable hoặc lỗi trong một giai đoạn.

### Khắc phục

1. Dừng và ghi nhận apply error.
2. Xác định table/key và transaction gây lỗi.
3. So sánh row publisher/subscriber.
4. Xác định nguồn divergence.
5. Sửa dữ liệu subscriber theo quy trình được phê duyệt hoặc resynchronize table.
6. Resume subscription và xác nhận worker tiến triển.

Không tắt constraint hoặc bỏ qua mọi apply errors để replication chạy tiếp; có thể che giấu divergence lớn hơn.

## 30. UPDATE và subscriber không có matching row

Nếu old identity không tìm thấy row trên subscriber, logical apply không biết row nào phải update. Đây thường là dấu hiệu dữ liệu hai phía đã lệch hoặc initial copy thiếu rows.

### Kiểm tra có mục tiêu

Với identity là customer_id:

```sql
SELECT *
FROM public.customer
WHERE customer_id = 42;
```

Chạy ở cả publisher và subscriber, so sánh row state và transaction history nếu có. Đối với bảng lớn, dùng query theo key cụ thể, không full table scan tùy tiện.

## 31. Unique conflict trên subscriber

Một update có thể tìm đúng old row nhưng giá trị mới vi phạm unique constraint trên subscriber:

```sql
UPDATE public.account_profile
SET external_ref = 'EXT-99'
WHERE external_ref = 'EXT-42';
```

Nếu subscriber đã có EXT-99 cho row khác, apply transaction thất bại. Replica identity xác định row cũ; nó không giải quyết conflict giữa dữ liệu mới với constraints hiện có.

### Cách xử lý

- Kiểm tra ai ghi trực tiếp subscriber.
- Kiểm tra schema/constraint drift.
- Kiểm tra publisher có duplicates do constraint khác nhau hay không.
- Reconcile dữ liệu theo business rules.
- Resume subscription sau khi nguyên nhân được xử lý.

## 32. Replica identity và publication column lists

Nếu publication định nghĩa column list, identity columns cần được bao gồm. Một migration giảm columns gửi đi có thể vô tình loại key cần cho update/delete.

### Quy trình thay column list

1. Xác định replica identity hiện tại.
2. Liệt kê identity columns.
3. Thiết kế column list mới có đầy đủ identity.
4. Cập nhật schema subscriber trước khi cần data.
5. Alter publication theo version-supported syntax.
6. Test insert/update/delete.
7. Theo dõi apply errors và consumer output.

## 33. Replica identity và row filters

Row filter không thay replica identity. Filter quyết định rows nào thuộc publication; identity giúp tìm old row khi thay đổi được gửi.

Khi update làm một row đổi trạng thái filter, hành vi có thể khác với suy nghĩ “new row match thì luôn gửi”. PostgreSQL logical replication có semantics row-filter riêng cho old/new rows và publication version. Thiết kế filter cần test cả ba tình huống:

1. Row không match chuyển sang match.
2. Row match chuyển sang không match.
3. Row vẫn match trước và sau update.

Với CDC consumers, ghi rõ semantics để downstream không hiểu nhầm event thành một bản sao đầy đủ của mọi row.

## 34. Partitioned tables

Logical replication có thể publish partitioned tables; rows thực tế được lưu ở partitions. Cần kiểm tra replica identity trên partitioned root và các partitions theo version, cũng như cấu hình publication dùng partition root hay publish partitions riêng.

### Những điều phải xác minh

- Replica identity/index được áp dụng cho đúng table/partition.
- Unique index trên partitioned table có giới hạn về partition key.
- Mỗi partition có schema/identity phù hợp.
- Subscriber có cấu trúc partition tương thích nếu muốn giữ partitioning.
- Partition attach/detach và DDL được đồng bộ bằng quy trình riêng.

Không giả định mọi thao tác ALTER TABLE trên root đều tạo đúng identity/index behavior ở mọi partition/version; kiểm tra catalog của từng partition và chạy test update/delete.

## 35. Inheritance và table boundaries

Table inheritance truyền thống và declarative partitioning có behavior khác nhau trong publications. Một publication có thể publish parent/partition theo options cụ thể. Replica identity vẫn phải đáp ứng cho các physical tables phát sinh changes.

Khi dùng inheritance/partitioning, kiểm tra pg_publication_tables, pg_class, pg_index và các leaf tables để xác định đúng đối tượng thực sự được publish.

## 36. Schema migration để thêm primary key

Nếu table chưa có identity, phương án dài hạn thường là thêm stable primary key:

```sql
ALTER TABLE public.legacy_customer
ADD COLUMN customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY;

ALTER TABLE public.legacy_customer
ADD CONSTRAINT legacy_customer_pkey
PRIMARY KEY (customer_id);

ALTER TABLE public.legacy_customer
REPLICA IDENTITY DEFAULT;
```

Đây là ví dụ đơn giản. Trên bảng lớn, thêm cột/PK có thể cần rewrite, build index và lock đáng kể tùy version/data/default. Cần migration plan phù hợp production.

### Khi table đã có data

Kiểm tra:

- Backfill strategy và sequence/identity values.
- Lock duration.
- Disk headroom cho index build.
- Replication lag trong lúc migration.
- DDL được chạy trên subscriber.
- Ứng dụng có phụ thuộc insert behavior mới không.

Không chạy một lệnh ALTER TABLE lớn trên production chỉ dựa vào ví dụ bài học.

## 37. Tạo unique index concurrently

Với table lớn, CREATE UNIQUE INDEX CONCURRENTLY có thể giảm blocking writes so với index build thường, nhưng có phase/overhead và có thể thất bại nếu duplicates xuất hiện.

Ví dụ:

```sql
CREATE UNIQUE INDEX CONCURRENTLY customer_external_id_uq
ON public.customer (external_id);
```

Sau khi index hợp lệ và các cột đáp ứng NOT NULL:

```sql
ALTER TABLE public.customer
REPLICA IDENTITY USING INDEX customer_external_id_uq;
```

CREATE INDEX CONCURRENTLY không chạy bên trong transaction block. Cần xác minh indisvalid=true và kiểm tra duplicates/nulls trước khi chuyển identity.

## 38. Thay replica identity an toàn

Giả sử đang dùng FULL và muốn chuyển sang unique index:

1. Xác định candidate key.
2. Làm sạch duplicates/NULLs.
3. Tạo unique index hợp lệ.
4. Xác nhận index đáp ứng điều kiện.
5. Triển khai index/schema tương ứng ở subscriber.
6. Chuyển publisher bằng ALTER TABLE ... REPLICA IDENTITY USING INDEX.
7. Test update/delete.
8. Theo dõi WAL bytes và apply lag.
9. Giữ phương án rollback nếu schema migration gặp lỗi.

### Vì sao không drop FULL trước?

Chuyển trực tiếp sang NOTHING hoặc xóa index trước khi identity mới sẵn sàng có thể làm các update/delete tiếp theo không thể replicate. Chuẩn bị identity mới trước rồi chuyển cấu hình.

## 39. Thay đổi primary key hoặc unique index

Nếu đổi key:

- Đảm bảo key mới tồn tại và unique ở publisher.
- Tạo schema/index ở subscriber.
- Chuyển replica identity đúng thứ tự.
- Cân nhắc các changes đang pending trong replication stream.
- Test update key value và delete.
- Chỉ drop index cũ khi không còn được identity/constraint/foreign key sử dụng.

Đối với CDC downstream, thay đổi identity có thể thay đổi key columns trong event schema; cần thông báo/versioning consumer contract.

## 40. Logical replication và wal_level

Publisher cần wal_level=logical để hỗ trợ logical decoding/replication. Replica identity là một phần thông tin old-row được ghi/đưa ra cho logical decoding.

Kiểm tra:

```sql
SHOW wal_level;
```

Thay đổi wal_level cần restart. Nếu publisher đang dùng physical replication đồng thời logical replication, logical vẫn hỗ trợ physical standby, nhưng WAL chứa thêm thông tin cần thiết cho logical decoding.

## 41. Replica identity và logical decoding plugins

Logical decoding plugin có thể trình bày old-row identity trong output format khác nhau. Một CDC connector có thể cần old key để tạo event before/after, route record hoặc xử lý deletes.

### Trước khi chọn FULL

- Kiểm tra connector yêu cầu primary key/replica identity gì.
- Xác nhận output plugin có phát old tuple theo mode đó.
- Kiểm tra behavior với TOAST columns.
- Đo WAL/network/decoder throughput.
- Xác định downstream schema có key ổn định không.

Một connector có thể hỗ trợ FULL nhưng điều đó không có nghĩa nó là lựa chọn tối ưu cho mọi table.

## 42. Replica identity và logical slots

Logical replication slots giữ WAL cần thiết cho consumer. Nếu consumer chậm, WAL retention tăng. Dùng FULL có thể làm WAL volume lớn hơn trong update/delete-heavy workloads, từ đó tăng pressure lên slot retention.

Theo dõi:

```sql
SELECT
    slot_name,
    plugin,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS retained_wal_distance
FROM pg_catalog.pg_replication_slots
WHERE slot_type = 'logical';
```

Khoảng cách LSN là ước lượng WAL address space, không phải dung lượng disk chính xác của riêng slot. Kết hợp với pg_wal directory size và consumer metrics.

## 43. Performance checklist

Khi đánh giá replica identity:

- Identity columns ít và nhỏ.
- Identity columns NOT NULL.
- Unique key ổn định theo business semantics.
- Subscriber có index phù hợp để lookup.
- Không dùng FULL cho bảng lớn/write-heavy nếu có thể tạo key.
- Không dùng partial/nullable/deferrable unique index.
- Column list chứa đầy đủ identity columns.
- CDC connector hiểu key schema.
- WAL rate/slot lag được đo trước và sau.

## 44. Monitoring replica identity issues

Theo dõi:

- Publisher logs có lỗi replica identity.
- Subscription worker errors và apply lag.
- Logical slot restart_lsn/confirmed_flush_lsn.
- WAL bytes/s trước và sau thay đổi identity.
- Update/delete rates theo table.
- Subscriber table row counts/key consistency.
- Duplicate/unique constraint violations.

### Xem trạng thái subscription

```sql
SELECT
    subname,
    pid,
    relid::regclass AS table_name,
    received_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time
FROM pg_catalog.pg_stat_subscription;
```

Schema view có thể khác giữa major versions. Kiểm tra error logs của apply worker để biết transaction/table/key cụ thể khi replication dừng.

## 45. Troubleshooting: cannot update table because it does not have a replica identity

Lỗi thường xuất hiện khi publication phát update/delete nhưng table không có identity phù hợp.

Quy trình:

1. Xác định table và publication.
2. Kiểm tra psql \d+ table hoặc relreplident.
3. Kiểm tra primary key/unique indexes.
4. Chọn DEFAULT, USING INDEX hoặc FULL.
5. Xác nhận publication column list.
6. Thử một update/delete có kiểm soát.
7. Kiểm tra subscriber apply worker.

Ví dụ khắc phục tạm:

```sql
ALTER TABLE public.legacy_customer
REPLICA IDENTITY FULL;
```

Đây có thể làm WAL lớn hơn. Dùng như biện pháp tạm khi cần và lập kế hoạch tạo identity key ổn định nếu workload phù hợp.

## 46. Troubleshooting: cannot use index as replica identity

Kiểm tra:

- Index có unique không?
- Có phải partial index không?
- Có deferrable không?
- Mọi key columns có NOT NULL không?
- Index đã valid/ready chưa?
- Index có thuộc đúng table không?
- Index có expression/include semantics không phù hợp?

Không chỉ nhìn tên index hoặc UNIQUE trong DDL. Dùng pg_index, pg_attribute và pg_get_indexdef để xác minh.

## 47. Troubleshooting: subscriber row not found

Nếu apply báo không tìm thấy row cho update/delete:

1. Đọc table/key trong error log.
2. Query row tương ứng trên publisher và subscriber.
3. Kiểm tra subscriber có bị ghi trực tiếp không.
4. Kiểm tra initial copy/table synchronization.
5. Kiểm tra row filter/publication changes.
6. Reconcile dữ liệu hoặc resynchronize table.
7. Resume subscription và xác nhận LSN tiến triển.

Không bỏ qua transaction lỗi nếu chưa biết dữ liệu nào bị lệch.

## 48. Troubleshooting: duplicate key trên subscriber

Nếu update/insert gây duplicate key:

- Xác định unique constraint nào bị vi phạm.
- Tìm row conflicting trên subscriber.
- Kiểm tra direct writes hoặc multi-writer design.
- So sánh schema/constraints hai phía.
- Reconcile theo business rule.
- Chỉ resume apply khi trạng thái dữ liệu nhất quán.

Replica identity giúp tìm old row; nó không ngăn subscriber có dữ liệu mới xung đột.

## 49. Troubleshooting: WAL tăng sau khi bật FULL

Nếu WAL bytes tăng rõ:

1. So sánh workload update/delete trước/sau.
2. Xác nhận bảng nào đã chuyển sang FULL.
3. Đo row width và TOAST usage.
4. Kiểm tra logical slot lag và retained WAL.
5. Kiểm tra decoder/network throughput.
6. Tạo unique key/index nếu business data cho phép.
7. Chuyển sang USING INDEX hoặc DEFAULT.
8. Đo lại cùng workload.

Không đổi lại NOTHING nếu publication vẫn cần update/delete.

## 50. Troubleshooting: publication column list thiếu identity

Nếu thay đổi publication bị từ chối hoặc update/delete không đáp ứng:

- Xác định identity columns trên publisher.
- Đọc column list trong pg_publication_tables.
- Thêm đủ identity columns vào publication.
- Đảm bảo subscriber có cột tương ứng.
- Test update/delete và kiểm tra apply.

## 51. Bảng chỉ INSERT và event sourcing

Một số bảng event/audit được thiết kế append-only. Nếu ứng dụng không update/delete và publication chỉ cần insert, có thể:

```sql
CREATE PUBLICATION event_only_pub
FOR TABLE public.event_log
WITH (publish = 'insert');

ALTER TABLE public.event_log
REPLICA IDENTITY NOTHING;
```

Đây là thiết kế hợp lệ khi semantics thực sự append-only. Nếu ứng dụng có cleanup job chạy DELETE, publication sẽ không gửi delete qua publication insert-only; cần quyết định retention/cleanup đồng bộ ở downstream.

## 52. Replica identity trong multi-table publication

Một publication có nhiều tables:

```sql
CREATE PUBLICATION app_pub
FOR TABLE public.customer, public.orders, public.order_items;
```

Mỗi table có replica identity riêng. Một table có PK không có nghĩa mọi table trong publication đều được bảo vệ. Kiểm tra tất cả tables được publish:

```sql
SELECT
    pt.schemaname,
    pt.tablename,
    c.relreplident
FROM pg_catalog.pg_publication_tables AS pt
JOIN pg_catalog.pg_namespace AS n
  ON n.nspname = pt.schemaname
JOIN pg_catalog.pg_class AS c
  ON c.relnamespace = n.oid
 AND c.relname = pt.tablename
WHERE pt.pubname = 'app_pub'
ORDER BY pt.schemaname, pt.tablename;
```

Nếu cùng tên table tồn tại trong nhiều schema, query trên vẫn join theo namespace/table name và tránh nhầm object.

## 53. Test replica identity trong lab

Tạo publisher table không có PK:

```sql
CREATE TABLE public.identity_demo (
    external_id TEXT NOT NULL,
    description TEXT NOT NULL,
    quantity INTEGER NOT NULL
);

INSERT INTO public.identity_demo
VALUES ('A-1', 'first', 10);
```

Tạo unique index và đặt identity:

```sql
CREATE UNIQUE INDEX identity_demo_external_id_uq
ON public.identity_demo (external_id);

ALTER TABLE public.identity_demo
REPLICA IDENTITY USING INDEX identity_demo_external_id_uq;
```

Tạo publication/subscription theo lab environment, sau đó thử:

```sql
UPDATE public.identity_demo
SET quantity = 20
WHERE external_id = 'A-1';

DELETE FROM public.identity_demo
WHERE external_id = 'A-1';
```

Kiểm tra subscriber nhận đúng update/delete. Sau đó thử trên một table REPLICA IDENTITY NOTHING trong publication có update/delete để quan sát lỗi và log.

## 54. Lab: FULL so với unique index

Tạo hai bảng có row width lớn, một bảng dùng USING INDEX, bảng còn lại dùng FULL. Chạy workload update/delete tương đương.

Ghi lại:

- pg_stat_wal.wal_bytes trước/sau.
- Logical slot retained distance.
- Publisher CPU.
- Subscriber apply throughput.
- Network bytes.
- Transaction latency.

### Kết quả cần phân tích

Không chỉ so WAL bytes tổng. Chuẩn hóa theo số rows update/delete và giữ cùng row payload/workload. Xác định FULL làm tăng chi phí ở publisher, network hay subscriber lookup.

## 55. Replica identity và initial table copy

Initial table synchronization copy rows hiện có từ publisher sang subscriber. Replica identity đặc biệt cần cho các thay đổi tiếp theo; initial copy không thay thế việc cấu hình identity cho tương lai.

Khi tạo subscription:

1. Xác nhận table schema/columns tương thích.
2. Xác nhận replica identity trước khi workload update/delete.
3. Kiểm tra initial copy hoàn tất.
4. Xác nhận table synchronization state.
5. Chạy update/delete test sau initial copy.

Nếu publisher phát changes trong lúc table sync, PostgreSQL phối hợp snapshot/catch-up theo replication protocol. Không tự copy file CSV vào subscriber rồi giả định replication state đã đồng bộ.

## 56. DDL và replica identity không tự replicate

Logical replication tích hợp không tự động replicate mọi DDL. Nếu thêm primary key/index ở publisher, cần triển khai tương ứng trên subscriber theo migration plan.

### Thứ tự migration phổ biến

1. Thêm cột/constraint/index trên subscriber theo cách an toàn.
2. Backfill dữ liệu nếu cần.
3. Xác nhận uniqueness/nullability ở cả hai phía.
4. Tạo unique index hợp lệ trên publisher.
5. Chuyển replica identity.
6. Test update/delete.
7. Xóa cấu trúc cũ sau khi xác nhận không còn phụ thuộc.

Nếu schema changes được chạy trong rolling deployment, kiểm soát thời điểm application bắt đầu ghi giá trị mới để tránh mismatch.

## 57. Replica identity và bidirectional/multi-writer

Logical replication một chiều thường giả định publisher là nguồn ghi chính cho các tables được replicate. Nếu cho phép writes ở cả hai phía, có thể xuất hiện:

- Cùng một key được insert ở cả hai phía.
- Một phía update trong khi phía kia delete.
- Key value khác nhau cho cùng logical entity.
- Apply conflicts và transaction failures.

Replica identity không phải conflict resolution system. Multi-writer cần kiến trúc riêng: key allocation, conflict detection/resolution, ownership/partitioning of writes và loop prevention.

## 58. Bảo vệ replica identity trong schema design

Khi thiết kế table mới sẽ được publish:

- Chọn primary key ổn định.
- Dùng NOT NULL và uniqueness.
- Tránh dùng mutable business attributes làm identity nếu có surrogate key tốt.
- Không dùng nullable unique key làm replica identity.
- Giữ identity columns trong publication column lists.
- Tạo cùng key/index ở subscriber.
- Test delete/update/primary key changes.

Surrogate key như BIGINT identity hoặc UUID thường giúp định danh row ổn định. Nhưng chọn kiểu key còn phụ thuộc write distribution, index size, application semantics và ID generation policy.

## 59. Checklist trước khi bật UPDATE/DELETE publication

### Publisher

- wal_level=logical.
- Table có primary key hoặc replica identity index/FULL phù hợp.
- Publication bật đúng operation.
- Column list chứa identity columns.
- Row filter được test với old/new row transitions.
- Replication slot và WAL retention có monitoring.

### Subscriber

- Schema và data đã được đồng bộ.
- Cột identity tồn tại với type tương thích.
- Có index phù hợp để lookup khi cần.
- Không có direct writes ngoài policy.
- Constraints không tạo conflict ngoài dự kiến.
- Apply worker hoạt động.

### Vận hành

- Update/delete test thành công.
- Apply lag và logs được giám sát.
- Migration/rollback plan rõ ràng.
- Reseed/resync procedure đã được ghi lại.

## 60. Runbook: bật UPDATE/DELETE cho table mới

1. Xác định publication và subscription liên quan.
2. Kiểm tra table có primary key không.
3. Nếu không có PK, xác định candidate unique key.
4. Làm sạch duplicates/NULLs.
5. Tạo unique index đủ điều kiện.
6. Tạo index/schema tương ứng trên subscriber.
7. Cấu hình REPLICA IDENTITY DEFAULT hoặc USING INDEX.
8. Đảm bảo publication column list có identity columns.
9. Xác nhận subscriber initial copy/sync hoàn tất.
10. Thực hiện update/delete test.
11. Theo dõi publisher logs, subscription worker và slot lag.
12. Mở workload production theo rollout plan.

## 61. Runbook: table không có identity nhưng cần replicate updates

1. Xác định mức độ khẩn cấp và update/delete volume.
2. Kiểm tra có thể thêm stable primary key không.
3. Nếu chưa thể, tìm unique index đủ điều kiện.
4. Nếu không có candidate, cân nhắc FULL.
5. Đo row width/WAL/CPU/network/apply impact.
6. Kiểm tra equality support cho data types.
7. Test subscriber row lookup và deletes.
8. Triển khai tạm thời có monitoring/rollback.
9. Lập kế hoạch migration sang key ổn định.
10. Không dùng NOTHING khi update/delete phải được publish.

## 62. Runbook: apply worker lỗi vì row không tồn tại

1. Ghi lại subscription/table/key và failing transaction.
2. Xác định row trên publisher.
3. Xác định row trên subscriber.
4. Kiểm tra direct subscriber writes và row filters.
5. Kiểm tra initial copy/sync state.
6. Reconcile table/key theo business owner.
7. Xác nhận constraints/indexes.
8. Resume subscription.
9. Theo dõi LSN/apply lag.
10. Tìm nguyên nhân gốc để ngăn divergence lặp lại.

## 63. Runbook: WAL tăng sau khi chuyển FULL

1. Xác định table/replica identity change time.
2. So sánh WAL bytes trước/sau theo workload tương đương.
3. Đo update/delete rate và row width.
4. Kiểm tra TOAST payloads.
5. Kiểm tra logical slot lag/retained WAL.
6. Đánh giá network và subscriber apply throughput.
7. Xây dựng unique key/index nếu có thể.
8. Chuyển sang USING INDEX/DEFAULT.
9. Đo lại và kiểm tra CDC event compatibility.
10. Giữ FULL nếu chưa có identity thay thế an toàn.

## 64. Bài tập thực hành

### Bài 1 — Mục đích replica identity

Vì sao logical replication cần old-row identity cho UPDATE và DELETE nhưng không cần nó để xác định row cũ của INSERT?

### Bài 2 — Bốn chế độ

So sánh DEFAULT, USING INDEX, FULL và NOTHING về dữ liệu old row được gửi, điều kiện sử dụng và chi phí.

### Bài 3 — DEFAULT

Một bảng có primary key customer_id. Giải thích PostgreSQL chọn replica identity nào khi table ở mode DEFAULT.

### Bài 4 — Không có primary key

Một bảng có cột email nhưng không có uniqueness constraint. Vì sao PostgreSQL không thể tự dùng email làm replica identity?

### Bài 5 — Composite key

Một bảng order_items có primary key (order_id, line_no). Những giá trị nào được dùng để tìm old row khi DELETE?

### Bài 6 — USING INDEX

Tạo unique index trên external_ref TEXT NOT NULL và cấu hình nó làm replica identity. Viết SQL và giải thích điều kiện.

### Bài 7 — Nullable unique index

Một unique index cho phép NULL. Vì sao nó không đủ điều kiện làm replica identity? Nêu migration để làm cột NOT NULL an toàn.

### Bài 8 — Partial index

Một partial unique index chỉ áp dụng cho active users. Vì sao index đó không định danh được mọi row trong table?

### Bài 9 — Deferrable constraint

Giải thích vì sao deferrable unique constraint không phù hợp làm replica identity.

### Bài 10 — FULL

Một legacy table không có key và cần publish DELETE. Cấu hình REPLICA IDENTITY FULL và nêu các rủi ro hiệu năng.

### Bài 11 — NOTHING

Một event table chỉ publish INSERT. Khi nào REPLICA IDENTITY NOTHING phù hợp? Điều gì xảy ra nếu publication sau đó bật DELETE?

### Bài 12 — UPDATE identity column

Publisher đổi external_ref từ EXT-42 sang EXT-43. Giải thích vì sao subscriber phải nhận old identity EXT-42 trước khi áp dụng key mới.

### Bài 13 — DELETE missing row

Subscriber không có row mà publisher vừa DELETE. Nêu các nguyên nhân divergence và quy trình điều tra.

### Bài 14 — Subscriber index

Replica identity do publisher gửi có vai trò gì? Vì sao subscriber vẫn nên có index phù hợp để lookup?

### Bài 15 — Publication operations

Tạo publication chỉ publish INSERT. Nêu khác biệt với publication mặc định có UPDATE/DELETE.

### Bài 16 — Column list

Một publication column list bỏ qua primary key. Vì sao điều này không đáp ứng yêu cầu UPDATE/DELETE? Sửa column list thế nào?

### Bài 17 — Row filter

Một row đổi status từ inactive sang active trong publication có filter status='active'. Hãy xác định các trường hợp old/new row cần test.

### Bài 18 — FULL và row width

Một bảng có 40 cột, JSONB lớn và primary key BIGINT. So sánh old-row payload khi dùng DEFAULT và FULL.

### Bài 19 — TOAST

Giải thích vì sao FULL có thể làm WAL/decoder payload lớn hơn với text/jsonb/bytea lớn.

### Bài 20 — Unique index inspection

Viết query từ pg_index/pg_class để kiểm tra unique, partial, valid và index definition.

### Bài 21 — Column nullability

Dùng pg_attribute và pg_index để xác định các key columns của candidate index có NOT NULL không.

### Bài 22 — Primary key inspection

Truy vấn pg_constraint để liệt kê primary keys và definitions của tất cả tables trong schema public.

### Bài 23 — Index drop

Một index đang được dùng làm replica identity. Vì sao DROP INDEX có thể bị từ chối? Trình tự chuyển identity trước khi drop là gì?

### Bài 24 — FULL performance test

Thiết kế benchmark so sánh WAL bytes, CPU, network, subscriber apply lag giữa FULL và USING INDEX.

### Bài 25 — Logical slots

Vì sao FULL có thể làm logical slot giữ nhiều WAL hơn khi consumer chậm? Viết query xem restart_lsn và confirmed_flush_lsn.

### Bài 26 — Partitioned table

Một publication publish partitioned parent. Những điểm nào cần kiểm tra ở root/leaf partitions về replica identity và unique index?

### Bài 27 — DDL migration

Thêm primary key vào bảng lớn đang được publish. Thiết kế migration có backfill, index build, subscriber schema và rollout.

### Bài 28 — CREATE INDEX CONCURRENTLY

Vì sao index concurrently hữu ích trên bảng lớn? Nêu các trạng thái cần kiểm tra trước khi dùng làm replica identity.

### Bài 29 — Primary key update

Một update đổi primary key và subscriber đã có row với key mới. Giải thích conflict và cách điều tra.

### Bài 30 — Publication nhiều bảng

Một publication có 20 tables. Viết query liệt kê replica identity mode của từng table và nêu cách phát hiện table thiếu identity.

### Bài 31 — CDC connector

Một CDC connector cần before/after event. Hãy xác định cách replica identity ảnh hưởng payload và những test cần làm với TOAST.

### Bài 32 — wal_level

Giải thích vì sao logical replication cần wal_level=logical và setting này có cần restart không.

### Bài 33 — Subscriber direct writes

Một ứng dụng ghi trực tiếp vào subscriber và làm mất row. Khi publisher gửi DELETE, điều gì có thể xảy ra? Đề xuất write ownership policy.

### Bài 34 — Unique conflict

Old row được tìm thấy trên subscriber nhưng giá trị mới vi phạm unique constraint. Vì sao đây không phải lỗi replica identity? Cần xử lý thế nào?

### Bài 35 — Initial table copy

Vì sao initial copy thành công không chứng minh update/delete sau này có thể replicate? Những kiểm tra nào cần làm sau sync?

### Bài 36 — FULL tạm thời

Thiết kế kế hoạch dùng FULL tạm cho một table legacy, sau đó chuyển sang unique index. Làm thế nào để tránh khoảng thời gian không có identity?

### Bài 37 — Multi-writer

Hai publisher cùng ghi một logical entity. Vì sao replica identity không giải quyết conflict? Thiết kế các lớp cần có cho multi-writer.

### Bài 38 — Apply worker errors

Một subscription dừng do row not found. Viết runbook xác định table/key, reconcile data và resume an toàn.

### Bài 39 — WAL spike

Sau khi chuyển 10 bảng sang FULL, WAL tăng 3 lần. Hãy thiết kế metrics và kế hoạch chuyển về key index khi có thể.

### Bài 40 — Thiết kế logical replication

Một hệ thống có:

- Bảng customer 100 triệu rows, có customer_id BIGINT PK.
- Bảng legacy_event 500 triệu rows, không có PK, row width lớn.
- Bảng account có unique email nhưng email hiện nullable.
- Một publication giới hạn columns để gửi dữ liệu sang analytics.
- CDC connector cần before/after images.
- Subscriber chỉ đọc, nhưng một batch job hiện vẫn ghi trực tiếp vào subscriber.

Hãy thiết kế:

1. Replica identity mode cho từng table.
2. Cách xử lý legacy_event và đánh giá FULL cost.
3. Migration email nullable thành unique identity an toàn.
4. Publication column lists chứa đầy đủ identity columns.
5. Subscriber schema/indexes và write ownership.
6. CDC event format và TOAST test.
7. Monitoring WAL bytes, slot lag và apply errors.
8. Test UPDATE/DELETE và key changes.
9. Rollout/rollback sequence.
10. Runbook khi subscriber không tìm thấy old row hoặc gặp unique conflict.

## Kết luận

**Replica identity cho PostgreSQL biết phải gửi thông tin nào của row cũ khi logical replication xử lý UPDATE hoặc DELETE.** DEFAULT dùng primary key và thường là lựa chọn tốt nhất. USING INDEX cho phép dùng unique index hợp lệ khi không có primary key. FULL gửi toàn bộ old row nhưng có thể làm tăng WAL, network, decoder và subscriber lookup costs. NOTHING chỉ phù hợp khi không cần replicate UPDATE/DELETE cho table.

Một identity tốt cần ổn định, duy nhất, không NULL và có index phù hợp. Unique index dùng làm replica identity không được partial hoặc deferrable và key columns phải NOT NULL. Publication column lists phải giữ các identity columns; row filters và partitioning cần được kiểm tra theo semantics của PostgreSQL version đang dùng.

Publisher quyết định old-row identity được phát ra; subscriber phải có schema và dữ liệu tương thích để tìm row rồi apply change. Subscriber bị ghi trực tiếp, initial copy không đầy đủ hoặc migration lệch có thể dẫn tới row-not-found/unique-conflict errors. Replica identity không tự đồng bộ DDL và không phải cơ chế giải quyết multi-writer conflicts.

Cuối cùng, hãy kiểm tra mọi table có publish UPDATE/DELETE, thử các thay đổi identity/key trên staging và theo dõi WAL bytes, logical slot lag cùng apply worker errors. **Chọn một khóa row ổn định ngay từ schema design thường giúp logical replication đơn giản, hiệu quả và dễ vận hành hơn.**
