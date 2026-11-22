# Lọc hàng, chọn cột và kiểm tra hỗ trợ theo phiên bản trong PostgreSQL

Logical replication của PostgreSQL cho phép một publication chỉ phát hành một phần dữ liệu của bảng. Hai khả năng quan trọng là **row filters** để giới hạn những hàng được gửi và **column lists** để giới hạn những cột được gửi. Chúng hữu ích khi subscriber chỉ cần dữ liệu của một tenant, một khu vực, một nhóm nghiệp vụ hoặc một tập thuộc tính phục vụ báo cáo.

Hai tính năng này được bổ sung từ **PostgreSQL 15**. Publisher dùng cú pháp `WHERE (...)` trong `CREATE PUBLICATION` để lọc hàng và danh sách cột sau tên bảng để chọn cột. Subscriber nhận các thay đổi đã được publication lọc, sau đó apply vào các bảng đích có cấu trúc tương thích.

Việc chọn đúng phiên bản ở cả hai đầu rất quan trọng. Một publisher PostgreSQL 15 trở lên có thể phát hành row-filtered/column-filtered changes tới subscriber cũ trong một số topology, nhưng subscriber trước PostgreSQL 15 không áp dụng các giới hạn đó khi initial table synchronization: nó có thể copy toàn bộ hàng và toàn bộ cột. PostgreSQL 18 bổ sung hỗ trợ replicate generated columns, với một số giới hạn initial sync khi subscriber cũ hơn 18.

```text
                 PUBLISHER (PostgreSQL 15+)
              +-----------------------------+
              |       orders                |
              | tenant_id | id | amount |   |
              | status    | internal_note   |
              +--------------+--------------+
                             |
                  Row filter: tenant_id = 42
                             |
                  Column list: tenant_id,
                  id, amount, status
                             |
                             v
                  Logical publication
                             |
                             v
                  SUBSCRIBER
              +-----------------------------+
              |       orders                |
              | tenant_id | id | amount |   |
              | status                    |
              +-----------------------------+
```

Bài thuộc chương **Sao chép logic** của module *Database Engine Relational PostgreSQL*. Mục tiêu là nắm cú pháp, semantics, giới hạn replica identity, tương tác với partitioning và nhiều publications, cùng cách kiểm tra tính năng theo phiên bản trước khi triển khai.

Sau bài học, bạn có thể:

1. Phân biệt row filter và column list.
2. Tạo publication lọc theo tenant hoặc điều kiện nghiệp vụ.
3. Chọn cột cần gửi mà vẫn giữ replica identity hợp lệ.
4. Giải thích UPDATE có thể biến thành INSERT hoặc DELETE khi row đi vào/ra filter.
5. Nhận diện các biểu thức row filter được hỗ trợ và các biểu thức bị từ chối.
6. Hiểu vì sao TRUNCATE không tuân theo row filter/column list.
7. Xử lý nhiều publications, partitioned tables và initial data synchronization.
8. Đánh giá schema tương thích ở subscriber.
9. Kiểm tra hỗ trợ PostgreSQL 14, 15, 16, 17 và 18.
10. Phát hiện rủi ro bảo mật, thay đổi schema và sai lệch dữ liệu do cấu hình lọc.

> **Phạm vi thực hành:** Ví dụ dùng hai database lab độc lập, một publisher và một subscriber. Publication được tạo ở publisher; subscription và bảng đích được tạo ở subscriber. Không chạy lệnh DROP/TRUNCATE trên dữ liệu thật để thử nghiệm. Row filters và column lists giúp giới hạn dữ liệu truyền, nhưng không phải cơ chế phân quyền bảo mật cho subscriber.

---

## 1. Row filter và column list là gì?

### 1.1. Row filter

Row filter là điều kiện `WHERE` gắn với một bảng trong publication. Publisher chỉ phát hành những hàng thỏa điều kiện đó.

Ví dụ:

```sql
CREATE PUBLICATION tenant_42_pub
FOR TABLE sales.orders
WHERE (tenant_id = 42);
```

Publication này chỉ phát hành các thay đổi của hàng có `tenant_id = 42`, theo quy tắc xử lý INSERT/UPDATE/DELETE của row filter.

Row filter được đánh giá ở phía publisher trước khi thay đổi được gửi cho subscriber. Nó không tạo một view vật lý và cũng không thay đổi dữ liệu nguồn.

### 1.2. Column list

Column list chỉ định các cột của bảng được phát hành:

```sql
CREATE PUBLICATION tenant_42_pub
FOR TABLE sales.orders (tenant_id, order_id, status, amount)
WHERE (tenant_id = 42);
```

Trong ví dụ, publication phát hành bốn cột được nêu. Các cột khác, chẳng hạn `internal_note`, không được gửi trong row changes của publication này.

Column list không đổi schema của bảng nguồn. Nó chỉ định nội dung row data được phát hành.

### 1.3. Dùng đồng thời

Row filter và column list có thể được khai báo cùng một table specification:

```sql
CREATE PUBLICATION tenant_42_orders
FOR TABLE sales.orders
    (tenant_id, order_id, status, amount, created_at)
    WHERE (tenant_id = 42)
WITH (publish = 'insert, update, delete');
```

Publication này:

- Chỉ phát hành hàng thuộc tenant 42.
- Chỉ gửi các cột được liệt kê.
- Phát hành INSERT, UPDATE và DELETE.
- Không phát hành TRUNCATE.

Ở đây loại bỏ `truncate` khỏi danh sách publish là có chủ ý. Row filter và column list không lọc TRUNCATE; nếu TRUNCATE được publish, subscriber có thể nhận lệnh truncate toàn bảng đích dù nó chỉ chứa một tập hàng.

### 1.4. Phân biệt với các tính năng khác

| Tính năng | Mục đích | Tác động |
|---|---|---|
| Row filter | Chọn hàng | Giới hạn rows được phát hành |
| Column list | Chọn cột | Giới hạn columns trong row changes |
| `publish` option | Chọn loại thao tác | Bật/tắt INSERT, UPDATE, DELETE, TRUNCATE |
| `REPLICA IDENTITY` | Xác định row cũ | Giúp subscriber tìm row cần UPDATE/DELETE |
| RLS | Phân quyền/giới hạn hàng trong query | Cơ chế row security của database |
| Subscription | Kết nối subscriber với publications | Tạo logical replication workers/slot |

Không nhầm row filter với RLS hoặc quyền SELECT. Chúng có liên quan đến security context nhưng là các cơ chế khác nhau.

---

## 2. Phiên bản hỗ trợ

### 2.1. Row filters và column lists được giới thiệu ở PostgreSQL 15

PostgreSQL 15 bổ sung khả năng chọn lọc nội dung publication bằng:

- Row filter với `WHERE (...)`.
- Column list sau tên bảng.

Vì vậy publisher PostgreSQL 14 trở xuống không hiểu cú pháp này trong `CREATE PUBLICATION`. Muốn dùng hai tính năng, publisher cần PostgreSQL 15 trở lên.

### 2.2. Ma trận phiên bản

| Publisher version | Row filters | Column lists | Ghi chú |
|---|---|---|---|
| PostgreSQL 14 trở xuống | Không hỗ trợ | Không hỗ trợ | Publication không có cú pháp lọc hàng/chọn cột |
| PostgreSQL 15 | Có | Có | Phiên bản đầu tiên có hai tính năng |
| PostgreSQL 16 | Có | Có | Tiếp tục hỗ trợ |
| PostgreSQL 17 | Có | Có | Tiếp tục hỗ trợ |
| PostgreSQL 18 | Có | Có | Có thêm hỗ trợ generated-column replication |

### 2.3. Publisher và subscriber có thể khác phiên bản

Logical replication được thiết kế để hỗ trợ một số kịch bản khác major version, thường dùng trong nâng cấp hoặc migration. Nhưng hỗ trợ cú pháp publication là tính năng phía publisher, còn initial data synchronization có behavior phụ thuộc phiên bản subscriber.

Để row filter và column list hoạt động nhất quán từ initial copy trở đi, nên dùng publisher và subscriber đều từ PostgreSQL 15 trở lên. Nếu subscriber cũ hơn, phải xử lý các giới hạn ở phần tiếp theo trước khi triển khai.

### 2.4. Subscriber trước PostgreSQL 15: initial copy có thể bỏ qua filter

Nếu publisher là PostgreSQL 15+ nhưng subscriber ở phiên bản trước 15:

- Initial table synchronization không áp dụng row filters; toàn bộ hàng hiện có có thể được copy.
- Initial table synchronization không áp dụng column lists; toàn bộ cột có thể được copy.
- Sau initial sync, publisher vẫn phát hành changes theo row filter/column list đã cấu hình.

Điều này có thể tạo ra trạng thái nguy hiểm: subscriber ban đầu chứa nhiều hàng/cột hơn mong muốn, nhưng về sau chỉ nhận các thay đổi đã lọc. Những hàng dư được copy ban đầu không tự động biến mất chỉ vì row filter không phát hành chúng.

Nếu subscriber cũ không thể nâng cấp, cần có quy trình initial load riêng đã kiểm soát, schema đích tương thích với cách copy của phiên bản cũ và bước đối soát/cleanup rõ ràng. Không giả định filter đã bảo vệ initial snapshot.

### 2.5. PostgreSQL 18 và generated columns

PostgreSQL 18 bổ sung khả năng replicate stored generated columns:

- Có thể đưa generated column vào column list.
- Nếu không chỉ định column list, publication option `publish_generated_columns = stored` cho phép phát hành stored generated columns.
- Nếu subscriber trước PostgreSQL 18, initial table synchronization không copy generated columns, kể cả khi publisher đã bật option.

Đây là một thay đổi riêng về generated columns; không có nghĩa row filters/column lists chỉ mới được hỗ trợ từ PostgreSQL 18.

### 2.6. Kiểm tra version ở cả hai đầu

Trên publisher:

```sql
SELECT
    version() AS full_version,
    current_setting('server_version') AS server_version,
    current_setting('server_version_num')::integer AS version_num,
    current_setting('server_version_num')::integer >= 150000
        AS supports_row_filters_and_column_lists;
```

Chạy cùng truy vấn trên subscriber. Ví dụ `150000` là mốc PostgreSQL 15.0; `180000` là mốc PostgreSQL 18.0.

Không kiểm tra duy nhất client version của psql. Publication syntax được phân tích bởi server publisher; initial synchronization behavior phụ thuộc server subscriber.

### 2.7. Kiểm tra tool và server riêng

```bash
psql --version
pg_dump --version
```

Các lệnh này cho biết phiên bản client tool. Để biết phiên bản server thực sự, kết nối tới từng node và chạy `SHOW server_version;`.

### 2.8. Kiểm tra release notes

Trước khi dùng generated columns hoặc tính năng mới hơn, đọc release notes của major version cụ thể. Một syntax có trong tài liệu current có thể không tồn tại trên server cũ.

---

## 3. Thiết kế bảng mẫu cho row filter và column list

### 3.1. Bảng nguồn

Ví dụ bảng orders:

```sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    tenant_id       BIGINT NOT NULL,
    order_id        BIGINT NOT NULL,
    status          TEXT NOT NULL,
    amount          NUMERIC(14, 2) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    internal_note   TEXT,
    payment_token   TEXT,
    PRIMARY KEY (tenant_id, order_id)
);
```

Khóa chính gồm `(tenant_id, order_id)`. Cấu trúc này thuận tiện cho filter theo tenant vì `tenant_id` là một phần của replica identity.

### 3.2. Dữ liệu mẫu

```sql
INSERT INTO sales.orders
    (tenant_id, order_id, status, amount, internal_note, payment_token)
VALUES
    (42, 1001, 'paid',    120000, 'priority customer', 'tok-a'),
    (42, 1002, 'pending',  80000, 'call before ship',  'tok-b'),
    (43, 2001, 'paid',    450000, 'internal review',   'tok-c'),
    (44, 3001, 'draft',    25000, 'not confirmed',     'tok-d');
```

### 3.3. Mục tiêu subscriber

Giả sử subscriber chỉ cần:

- Orders thuộc tenant 42.
- Các cột `tenant_id`, `order_id`, `status`, `amount`, `created_at`.
- Không cần `internal_note` hoặc `payment_token`.

Row filter quyết định tập hàng; column list quyết định tập cột.

### 3.4. Tạo publication

Trên publisher PostgreSQL 15 trở lên:

```sql
CREATE PUBLICATION tenant_42_orders
FOR TABLE sales.orders
    (tenant_id, order_id, status, amount, created_at)
    WHERE (tenant_id = 42)
WITH (publish = 'insert, update, delete');
```

Bỏ `TRUNCATE` khỏi danh sách publish để không gửi lệnh truncate toàn bộ bảng đích.

### 3.5. Tạo bảng subscriber

Trên subscriber:

```sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    tenant_id   BIGINT NOT NULL,
    order_id    BIGINT NOT NULL,
    status      TEXT NOT NULL,
    amount      NUMERIC(14, 2) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
```

Subscriber không cần có hai cột `internal_note` và `payment_token`, vì chúng không nằm trong column list. Các cột được phát hành phải tồn tại trên subscriber và có kiểu dữ liệu tương thích.

### 3.6. Tạo subscription

Trên subscriber, role thực thi cần quyền phù hợp để tạo subscription và bảng đích đã được chuẩn bị:

```sql
CREATE SUBSCRIPTION tenant_42_sub
CONNECTION 'host=publisher.example.net port=5432 dbname=appdb user=replicator password=replace-me sslmode=verify-full'
PUBLICATION tenant_42_orders
WITH (copy_data = true);
```

Connection string chỉ minh họa cú pháp. Production nên dùng passfile/secret manager thay vì ghi password trực tiếp trong SQL script hoặc log.

### 3.7. Kết quả mong đợi

Trên publisher, bốn rows tồn tại. Trên subscriber, chỉ hai rows của tenant 42 được initial sync; chỉ năm cột được sao chép.

```sql
SELECT tenant_id, order_id, status, amount, created_at
FROM sales.orders
ORDER BY tenant_id, order_id;
```

Subscriber không nhận `internal_note` hoặc `payment_token`.

---

## 4. Quy tắc đánh giá row filter

### 4.1. Điều kiện TRUE mới được phát hành

Row filter được đánh giá ở publisher:

- TRUE: hàng đủ điều kiện được phát hành.
- FALSE: hàng không được phát hành.
- NULL: hàng không được phát hành.

Đây là semantics SQL thông thường của điều kiện WHERE: chỉ giá trị TRUE được giữ lại.

### 4.2. Điều kiện phải đặt trong ngoặc

Cú pháp:

```sql
CREATE PUBLICATION p_orders
FOR TABLE sales.orders
WHERE (tenant_id = 42 AND status <> 'draft');
```

Biểu thức sau WHERE phải được đặt trong ngoặc. Mỗi table specification có thể có điều kiện riêng.

### 4.3. Biểu thức được phép

Row filter chỉ cho phép các biểu thức đơn giản. Không hỗ trợ:

- User-defined functions.
- User-defined operators.
- User-defined types.
- User-defined collations.
- System column references.
- Built-in functions không immutable.

Ví dụ điều kiện đơn giản:

```sql
WHERE (tenant_id = 42)
WHERE (status IN ('paid', 'shipped'))
WHERE (amount >= 100000 AND tenant_id = 42)
```

Các ví dụ trên minh họa cú pháp biểu thức. Nếu publication phát hành UPDATE/DELETE, mọi cột được dùng trong filter phải thuộc replica identity; không phải mọi ví dụ đều hợp lệ cho mọi table definition.

Không dùng function phụ thuộc thời gian như `now()` trong filter vì kết quả thay đổi theo thời điểm và không phải immutable expression. Nếu cần cutoff theo ngày, tính mốc cố định và lưu thành literal/configuration phù hợp.

### 4.4. Row filter không phải truy vấn tùy ý

Không thể gọi function nghiệp vụ, join bảng khác hoặc truy vấn bảng tham chiếu trong row filter. Biểu thức chỉ đánh giá trên cột của row đang được phát hành.

Nếu cần lọc theo dữ liệu ở bảng khác, cân nhắc:

- Denormalize thuộc tính cần lọc vào bảng nguồn.
- Dùng bảng staging/materialized process riêng.
- Tạo một pipeline logical replication/application ETL khác.
- Thực hiện lọc ở subscriber sau khi dữ liệu được nạp, nếu chấp nhận dữ liệu nguồn đã truyền tới subscriber.

### 4.5. Vai trò dùng để đánh giá

Row filter được đánh giá với role dùng cho replication connection của subscription. Quyền và row-level security trên publisher có thể ảnh hưởng việc đọc dữ liệu.

Không giả định filter luôn chạy bằng superuser. Thiết kế role, table ownership và RLS policy rõ ràng; kiểm tra behavior bằng đúng replication role trong môi trường lab.

---

## 5. Replica identity giới hạn row filter và column list

### 5.1. Vì sao UPDATE/DELETE cần replica identity?

Subscriber phải biết row nào cần UPDATE hoặc DELETE. Publisher gửi thông tin nhận diện row cũ theo replica identity.

Thông thường, PostgreSQL dùng primary key làm replica identity. Nếu không có primary key, có thể chọn một unique index phù hợp hoặc dùng `REPLICA IDENTITY FULL`.

### 5.2. Row filter cho UPDATE/DELETE

Nếu publication phát hành UPDATE hoặc DELETE, các cột được tham chiếu trong row filter phải thuộc replica identity.

Ví dụ bảng `sales.orders` có primary key:

```sql
PRIMARY KEY (tenant_id, order_id)
```

Filter sau hợp lệ:

```sql
WHERE (tenant_id = 42)
```

Filter sau không phù hợp cho publication có UPDATE/DELETE nếu `status` không nằm trong replica identity:

```sql
WHERE (status = 'paid')
```

Vì publisher cần đánh giá filter cho old/new row trong UPDATE và định vị row cũ khi apply thay đổi.

### 5.3. Column list cho UPDATE/DELETE

Nếu publication phát hành UPDATE hoặc DELETE, column list phải bao gồm tất cả cột replica identity.

Ví dụ với primary key `(tenant_id, order_id)`:

```sql
CREATE PUBLICATION tenant_42_orders
FOR TABLE sales.orders
    (tenant_id, order_id, status, amount)
    WHERE (tenant_id = 42);
```

Danh sách cột giữ cả `tenant_id` và `order_id`, nên subscriber có đủ thông tin nhận diện row.

### 5.4. Nếu chỉ phát hành INSERT

Khi publication chỉ phát hành INSERT, các ràng buộc replica identity cho row filter/column list được nới:

- Row filter có thể tham chiếu bất kỳ cột nào của row.
- Column list có thể bỏ các cột replica identity.

Ví dụ:

```sql
CREATE PUBLICATION paid_order_inserts
FOR TABLE sales.orders (status, amount, created_at)
WHERE (status = 'paid')
WITH (publish = 'insert');
```

Đây là publication insert-only. Nếu sau này thêm UPDATE hoặc DELETE, phải đánh giá lại filter và column list trước khi đổi publish option.

### 5.5. REPLICA IDENTITY FULL

Nếu bảng không có khóa phù hợp, có thể dùng:

```sql
ALTER TABLE sales.orders REPLICA IDENTITY FULL;
```

Khi đó toàn bộ row được dùng để nhận diện old row cho UPDATE/DELETE. Đây là fallback có chi phí lớn hơn, vì logical decoding phải xử lý nhiều dữ liệu hơn và subscriber cần so khớp row theo nội dung.

Ưu tiên primary key hoặc unique index phù hợp thay vì dùng FULL cho mọi bảng.

### 5.6. Dùng unique index làm replica identity

Có thể chọn unique index đáp ứng điều kiện PostgreSQL:

```sql
CREATE UNIQUE INDEX orders_replica_key
ON sales.orders (tenant_id, order_id);

ALTER TABLE sales.orders
REPLICA IDENTITY USING INDEX orders_replica_key;
```

Unique index dùng làm replica identity phải đáp ứng các điều kiện về uniqueness, không partial/expression và các cột phải NOT NULL theo yêu cầu PostgreSQL. Kiểm tra documentation version đang chạy.

### 5.7. Lỗi thường gặp

Nếu filter dùng cột không thuộc replica identity hoặc column list bỏ mất identity columns trong publication có UPDATE/DELETE, CREATE/ALTER PUBLICATION có thể bị từ chối hoặc thao tác publish không hợp lệ.

Đừng sửa lỗi bằng cách bỏ primary key khỏi subscriber. Hãy thiết kế lại replica identity ở publisher và giữ cấu trúc khóa tương thích ở subscriber.

---

## 6. UPDATE có thể trở thành INSERT hoặc DELETE

### 6.1. Row filter đánh giá cả old row và new row

Khi UPDATE được xử lý, PostgreSQL đánh giá row filter trên cả phiên bản trước và sau khi cập nhật.

| Old row | New row | Thay đổi được phát hành |
|---|---|---|
| Không khớp | Không khớp | Không phát hành |
| Không khớp | Khớp | INSERT |
| Khớp | Không khớp | DELETE |
| Khớp | Khớp | UPDATE |

Mục tiêu là subscriber phản ánh đúng tập rows mà row filter xác định ở publisher.

### 6.2. Row đi vào tập được chọn

Giả sử publication dùng:

```sql
WHERE (tenant_id = 42)
```

Một row trước đó thuộc tenant 43 được cập nhật thành tenant 42. Old row không khớp, new row khớp. Subscriber nhận một INSERT để tạo row mới trong tập dữ liệu được publish.

### 6.3. Row rời khỏi tập được chọn

Một row trước đó thuộc tenant 42 được chuyển sang tenant 43. Old row khớp, new row không khớp. Subscriber nhận DELETE để xóa row đã được gửi trước đó.

### 6.4. Cả hai phiên bản đều khớp

Nếu tenant_id vẫn là 42, thay đổi status hoặc amount được phát hành dưới dạng UPDATE (nếu publication bật UPDATE).

### 6.5. Cả hai phiên bản đều không khớp

Nếu tenant_id vẫn là 43, UPDATE không được phát hành tới subscriber tenant 42.

### 6.6. Hệ quả vận hành

Row filter không đơn thuần là “chỉ kiểm tra row mới”. PostgreSQL duy trì ranh giới tập dữ liệu ở subscriber bằng cách biến đổi UPDATE thành INSERT/DELETE khi điều kiện membership thay đổi.

Điều này chỉ hoạt động đúng khi replica identity đủ để định vị old row và các cột cần thiết được publish.

### 6.7. Thay đổi điều kiện filter

Nếu thay filter từ `tenant_id = 42` sang `tenant_id IN (42, 43)`, các rows tenant 43 đang tồn tại không tự động được thêm chỉ vì publication definition đã đổi. Cần xem xét refresh/initial synchronization hoặc quy trình backfill để subscriber nhận đủ dữ liệu mới nằm trong phạm vi.

Tương tự, khi thu hẹp filter, những rows đã có ở subscriber nhưng không còn thuộc phạm vi có thể vẫn tồn tại nếu thay đổi filter không tạo DML delete tương ứng. Hãy lập kế hoạch reconcile dữ liệu sau khi sửa publication.

---

## 7. Column list: quy tắc và schema đích

### 7.1. Chỉ nhận tên cột đơn giản

Column list chỉ chứa các column references đơn giản:

```sql
CREATE PUBLICATION p_orders
FOR TABLE sales.orders (tenant_id, order_id, status, amount);
```

Column list không được kết hợp với publication specification `FOR TABLES IN SCHEMA`; `FOR ALL TABLES` và `FOR TABLES IN SCHEMA` cũng không cho khai báo filter/list riêng cho từng table. Khi cần chọn hàng/cột, khai báo từng table bằng `FOR TABLE`.

Không dùng biểu thức, phép tính, alias hoặc rename trong column list. Ví dụ các dạng `lower(email)`, `amount * 1.1` hoặc `email AS contact` không phải cú pháp column list.

Nếu cần transform/rename, dùng schema/view/ETL ở một tầng khác. Publication column list chỉ chọn cột gốc.

### 7.2. Thứ tự cột không được bảo toàn

Thứ tự tên trong column list không được dùng như một phép sắp xếp vị trí cột. Logical replication ánh xạ theo tên cột. Subscriber cần có các cột được publish với tên tương ứng và kiểu dữ liệu tương thích.

### 7.3. Subscriber có thể có thêm cột

Bảng subscriber phải có ít nhất tất cả các cột được publish. Nó có thể có thêm cột riêng, nhưng các cột thêm đó phải có cách tạo giá trị hợp lệ khi replication apply INSERT.

Ví dụ, cột bổ sung `subscriber_tag TEXT` có thể dùng default hoặc cho phép NULL. Nếu là NOT NULL không có default, INSERT từ apply worker có thể thất bại vì publisher không gửi cột đó.

### 7.4. Subscriber có thể thiếu cột bị loại

Nếu column list bỏ `internal_note` và `payment_token`, bảng đích có thể không khai báo hai cột này. Điều này hữu ích khi subscriber có schema gọn hơn, nhưng schema mapping phải được kiểm tra trước khi bật subscription.

### 7.5. Explicit list khác với không khai báo list

Nếu không có column list, PostgreSQL phát hành tất cả các cột thông thường của bảng, bao gồm các cột được thêm vào sau này.

Nếu khai báo column list tường minh liệt kê mọi cột hiện có, cột mới được thêm về sau sẽ không tự động được phát hành. Đây là khác biệt quan trọng khi schema thay đổi.

### 7.6. Ví dụ schema evolution

Ban đầu:

```sql
CREATE PUBLICATION p_orders
FOR TABLE sales.orders (tenant_id, order_id, status, amount);
```

Sau đó publisher thêm:

```sql
ALTER TABLE sales.orders
ADD COLUMN fulfillment_region TEXT;
```

Cột mới không tự động xuất hiện trong column list hiện tại. Nếu subscriber cần nó:

1. Tạo cột tương thích trên subscriber.
2. Kiểm tra replica identity và publication requirements.
3. Cập nhật column list bằng ALTER PUBLICATION.
4. Lập kế hoạch backfill cho dữ liệu cũ nếu cần.
5. Kiểm tra replication tiếp tục bình thường.

### 7.7. Column list không phải projection có bảo mật

Column list có thể giảm payload và tránh đồng bộ các thuộc tính không cần thiết. Tuy nhiên, không coi nó là biện pháp bảo mật để bảo đảm subscriber không thể lấy dữ liệu của cột bị bỏ. Publication không cung cấp quyền truy cập độc lập theo từng subscriber ở mức cột.

Nếu dữ liệu nhạy cảm cần được bảo vệ, kiểm soát quyền ở publisher, tạo nguồn dữ liệu đã được tách riêng hoặc dùng cơ chế security phù hợp. Không dựa vào column list làm ranh giới bí mật.

---

## 8. TRUNCATE không được row filter hoặc column list giới hạn

### 8.1. Row filter không áp dụng cho TRUNCATE

Row filter chỉ đánh giá row changes. TRUNCATE là thao tác trên toàn relation, không phải một tập row events để filter từng hàng.

Vì vậy, nếu publication phát hành TRUNCATE, lệnh này được gửi tới subscriber mà không áp dụng row filter.

### 8.2. Column list cũng không áp dụng cho TRUNCATE

Column list giới hạn dữ liệu row payload. TRUNCATE không mang row payload nên column list không thay đổi behavior của nó.

### 8.3. Rủi ro với subscriber chỉ chứa một phần hàng

Giả sử subscriber chỉ nhận tenant 42. Bảng đích chỉ có các rows của tenant 42. Nếu ứng dụng chạy TRUNCATE bảng trên publisher và publication phát hành TRUNCATE, subscriber có thể truncate toàn bộ bảng đích, kể cả khi publisher chỉ muốn xóa rows của một tenant.

### 8.4. Cấu hình publication an toàn hơn

Với publication partial data, thường bỏ TRUNCATE:

```sql
CREATE PUBLICATION tenant_42_orders
FOR TABLE sales.orders
    (tenant_id, order_id, status, amount)
    WHERE (tenant_id = 42)
WITH (publish = 'insert, update, delete');
```

### 8.5. Nếu nghiệp vụ cần xóa nhiều hàng

Thay vì TRUNCATE, dùng DELETE có điều kiện để logical replication có thể áp dụng row filter cho từng row:

```sql
DELETE FROM sales.orders
WHERE tenant_id = 42
  AND status = 'cancelled';
```

DELETE chỉ phát hành những row changes thỏa filter. Đánh giá tác động hiệu năng và số lượng WAL records khi xóa khối lượng lớn.

### 8.6. Kiểm tra publish options

```sql
SELECT
    pubname,
    pubinsert,
    pubupdate,
    pubdelete,
    pubtruncate
FROM pg_publication
ORDER BY pubname;
```

Nếu publication có partial rows, xác nhận `pubtruncate` là false trừ khi đã thiết kế rõ semantics truncate toàn bảng ở subscriber.

---

## 9. Nhiều publications cùng phát hành một bảng

### 9.1. Row filters được kết hợp bằng OR

Một subscription có thể theo dõi nhiều publications cùng chứa một bảng. Nếu các publications định nghĩa row filters khác nhau cho cùng operation, PostgreSQL kết hợp chúng bằng OR.

Ví dụ:

```sql
CREATE PUBLICATION tenant_42_pub
FOR TABLE sales.orders WHERE (tenant_id = 42);

CREATE PUBLICATION tenant_43_pub
FOR TABLE sales.orders WHERE (tenant_id = 43);
```

Nếu subscription đăng ký cả hai publications, các rows thuộc tenant 42 hoặc tenant 43 được phát hành.

### 9.2. Publication không filter làm filter khác trở nên vô hiệu

Nếu một publication không có row filter cho operation đó, hoặc bảng được đưa vào publication kiểu `FOR ALL TABLES`/`FOR TABLES IN SCHEMA`, điều kiện lọc từ publication khác trở nên dư thừa vì có một nguồn phát hành không giới hạn.

Ví dụ:

```sql
CREATE PUBLICATION all_orders
FOR TABLE sales.orders;

CREATE PUBLICATION tenant_42_only
FOR TABLE sales.orders WHERE (tenant_id = 42);
```

Một subscription nhận cả hai publications sẽ nhận tất cả rows theo publication `all_orders`; filter tenant 42 không còn giới hạn dữ liệu tổng thể.

### 9.3. Column lists không được kết hợp tùy ý

Hiện tại không hỗ trợ một subscription có nhiều publications mà cùng một table được publish với các column lists khác nhau.

```sql
CREATE PUBLICATION p_a
FOR TABLE sales.orders (tenant_id, order_id, status);

CREATE PUBLICATION p_b
FOR TABLE sales.orders (tenant_id, order_id, amount);
```

Không tạo một subscription để mong PostgreSQL tự union hai danh sách thành bốn cột. CREATE SUBSCRIPTION sẽ từ chối một số cấu hình xung đột; nếu publication được ALTER sau khi subscription đã tồn tại, có thể phát sinh lỗi apply.

### 9.4. Thay đổi column list sau khi subscription được tạo

Nếu thay column list ở publication đang được subscriber dùng, kiểm tra mọi publication khác trong cùng subscription có phát hành cùng bảng. Các column lists phải khớp theo yêu cầu hỗ trợ.

Nếu đã rơi vào trạng thái mismatch, cần chỉnh column lists cho đồng nhất và có thể phải recreate subscription hoặc drop/add publication qua ALTER SUBSCRIPTION theo hướng dẫn version.

### 9.5. Thiết kế một publication theo subscriber

Khi nhiều subscriber cần các tập cột khác nhau, có thể tạo publication riêng cho mỗi nhóm subscriber, nhưng không ghép các publication có column lists xung đột cho cùng một bảng trong một subscription.

Hãy lập bảng mapping:

| Subscriber | Publication | Row filter | Column list |
|---|---|---|---|
| Tenant 42 | tenant_42_pub | tenant_id = 42 | Các cột nghiệp vụ cần |
| Tenant 43 | tenant_43_pub | tenant_id = 43 | Cùng tập cột tương thích |
| Analytics | analytics_pub | Không filter hoặc filter riêng | Tập cột phân tích |

Kiểm tra các subscription có overlap publication trước khi tạo mới.

---

## 10. Partitioned tables và publish_via_partition_root

### 10.1. Publication có thể chứa partitioned table

Khi thêm partitioned table vào publication, các partitions hiện tại và tương lai được xem là thuộc publication theo quy tắc PostgreSQL. Row filter và column list có thể được chọn từ root hoặc từ từng partition.

### 10.2. publish_via_partition_root = false

Đây là mặc định. Row filter và column list của từng leaf partition được dùng khi phát hành thay đổi từ partition đó.

Điều này có thể hữu ích khi mỗi partition có policy hoặc schema phù hợp riêng, nhưng cần bảo đảm cấu hình ở mọi partition thống nhất với ý định replication.

### 10.3. publish_via_partition_root = true

Khi bật:

```sql
CREATE PUBLICATION regional_orders
FOR TABLE sales.orders
    (tenant_id, order_id, status, amount)
    WHERE (tenant_id = 42)
WITH (
    publish = 'insert, update, delete',
    publish_via_partition_root = true
);
```

Row filter và column list được lấy từ root partitioned table. Thay đổi xảy ra trực tiếp ở leaf partition cũng được publish theo identity/schema của root.

### 10.4. Kiểm tra cấu hình partition

```sql
SELECT
    p.pubname,
    p.pubviaroot,
    pt.schemaname,
    pt.tablename,
    pt.attnames,
    pt.rowfilter
FROM pg_publication AS p
JOIN pg_publication_tables AS pt
  ON pt.pubname = p.pubname
WHERE p.pubname = 'regional_orders'
ORDER BY pt.schemaname, pt.tablename;
```

View có thể hiển thị các leaf partitions được mở rộng từ partitioned root. Kiểm tra schema view trên đúng major version.

### 10.5. TRUNCATE trực tiếp partition

Khi `publish_via_partition_root = true`, TRUNCATE thực hiện trực tiếp trên partition có các quy tắc riêng; PostgreSQL không publish một số thao tác TRUNCATE trực tiếp trên partition theo behavior được tài liệu hóa. Dù vậy, row filter/column list vẫn không phải cơ chế lọc TRUNCATE. Thiết kế publication partial data nên tắt truncate nếu không có nhu cầu rõ ràng.

### 10.6. Partition mới

Khi tạo/attach partition mới:

- Kiểm tra partition có thuộc publication qua root/schema scope hay không.
- Nếu `publish_via_partition_root = false`, kiểm tra filter và column list trên partition.
- Nếu true, kiểm tra cấu hình trên root.
- Xác nhận subscriber có table đích/partition tương thích.
- Test insert/update/delete đi qua root và thao tác trực tiếp trên leaf.

### 10.7. Khác cấu trúc partition giữa publisher và subscriber

Logical replication có thể publish thay đổi theo root để subscriber dùng partition structure khác hoặc bảng không partitioned, nhưng cần schema/identity mapping tương thích. Đừng giả định hai partition trees tự động được đồng bộ DDL; DDL không được replicate.

---

## 11. Initial data synchronization và copy_data

### 11.1. Initial copy

Khi tạo subscription với `copy_data = true`, PostgreSQL copy dữ liệu hiện có của các bảng được subscribe. Với publisher/subscriber hỗ trợ row filters/column lists, initial sync áp dụng:

- Row filter để chọn rows.
- Column list để chọn columns.

Sau khi initial copy hoàn tất, apply workers tiếp tục nhận các thay đổi mới từ publisher.

### 11.2. copy_data = false

```sql
CREATE SUBSCRIPTION tenant_42_sub
CONNECTION 'host=publisher.example.net dbname=appdb user=replicator sslmode=verify-full'
PUBLICATION tenant_42_orders
WITH (copy_data = false);
```

Khi dùng `copy_data = false`, subscription không tự copy rows đã tồn tại. Nó chỉ tiếp tục apply changes sau khi subscription bắt đầu. Cần một initial load riêng được đồng bộ với replication position để không bỏ sót hoặc nhân đôi dữ liệu.

### 11.3. publish option không điều khiển initial copy

Publication option `publish` chọn loại DML được phát hành trong replication stream. Initial data synchronization không tuân theo option này khi copy rows hiện có.

Ví dụ publication chỉ publish UPDATE/DELETE vẫn có thể copy dữ liệu hiện tại trong initial sync nếu subscription dùng `copy_data = true`.

### 11.4. Row filter trong initial sync

Nếu publisher có row filter và subscriber từ PostgreSQL 15 trở lên, initial copy chỉ lấy rows thỏa điều kiện. Nếu subscription nhận nhiều publications cho cùng table, các row filters kết hợp theo OR cho cùng operation.

### 11.5. Subscriber cũ hơn 15

Nếu subscriber trước PostgreSQL 15:

- Initial copy bỏ qua row filters và copy toàn bộ rows.
- Initial copy bỏ qua column lists và copy toàn bộ columns.

Sau initial copy, changes được phát hành theo filter/list của publisher. Kết quả ban đầu có thể vượt phạm vi mong muốn; cần nâng cấp subscriber hoặc có phương án initial data riêng.

### 11.6. Tránh dữ liệu cũ dư thừa

Nếu subscriber đã có dữ liệu trước khi tạo subscription, `copy_data = true` có thể gặp duplicate key hoặc conflict. Nếu `copy_data = false`, phải chắc chắn dữ liệu ban đầu khớp với publication filter/column list và điểm bắt đầu replication.

Không xóa hàng loạt trên subscriber để “sửa” sau initial sync mà không biết transaction đang apply và trạng thái slot/worker.

### 11.7. Kiểm tra trạng thái table synchronization

```sql
SELECT
    srrelid::regclass AS relation,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY srrelid::regclass::text;
```

Trạng thái table sync giúp nhận biết bảng đang copy, catch-up hoặc đã ready. Mã trạng thái và ý nghĩa chi tiết phụ thuộc PostgreSQL version; tra cứu catalog documentation trước khi viết automation.

---

## 12. Kiểm tra hỗ trợ theo phiên bản một cách có hệ thống

### 12.1. Kiểm tra publisher

Chạy trên publisher:

```sql
SHOW server_version;

SELECT current_setting('server_version_num')::integer AS version_num;
```

Nếu publisher thấp hơn 150000, không dùng cú pháp row filter/column list.

### 12.2. Kiểm tra subscriber

Kết nối riêng tới subscriber và chạy cùng truy vấn. Không dùng version của publisher để suy ra initial sync behavior ở subscriber.

Ghi lại cả hai:

| Node | Server version | Vai trò | Feature cần xác nhận |
|---|---|---|---|
| Publisher | 15+ | Tạo publication và lọc changes | Row filter, column list |
| Subscriber | 15+ | Initial copy theo filter/list | Initial sync chọn đúng rows/columns |
| Subscriber | 14 trở xuống | Subscriber legacy | Initial copy có thể copy tất cả rows/columns |
| Publisher | 18+ | Generated column source | `publish_generated_columns` và column list generated |
| Subscriber | Trước 18 | Legacy generated-column target | Initial copy không copy generated columns |

### 12.3. Kiểm tra catalog publication

Trên publisher PostgreSQL 15+:

```sql
SELECT
    pubname,
    schemaname,
    tablename,
    attnames,
    rowfilter
FROM pg_publication_tables
WHERE schemaname = 'sales'
ORDER BY pubname, tablename;
```

View này hiển thị các bảng trong publications cùng danh sách cột và row filter nếu có. Với partitioned table, view có thể mở rộng thông tin tới các partitions theo semantics của publication.

### 12.4. Kiểm tra publication-level options

```sql
SELECT
    pubname,
    puballtables,
    pubinsert,
    pubupdate,
    pubdelete,
    pubtruncate,
    pubviaroot
FROM pg_publication
ORDER BY pubname;
```

Một số cột có thể khác theo major version. Dùng lệnh psql `\dRp+` để xem publication ở dạng dễ đọc:

```text
\dRp+
\dRp+ tenant_42_orders
```

### 12.5. Kiểm tra publication table membership

```sql
SELECT *
FROM pg_publication_tables
WHERE pubname = 'tenant_42_orders';
```

Xác nhận:

- Bảng đúng schema/name.
- Column list chứa replica identity columns.
- Row filter đúng biểu thức.
- Không có publication khác vô tình phát hành cùng table không filter.

### 12.6. Kiểm tra subscription

Trên subscriber:

```sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription
ORDER BY subname;
```

Để xem trạng thái worker:

```sql
SELECT
    subname,
    pid,
    relid::regclass AS relation,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription;
```

View và các cột có thể thay đổi theo version. Đọc catalog documentation trước khi đóng gói thành monitoring query dùng chung nhiều major versions.

### 12.7. Kiểm tra feature bằng test publication

Trong lab, tạo bảng nhỏ rồi thử cú pháp:

```sql
CREATE TABLE public.feature_probe (
    id BIGINT PRIMARY KEY,
    region TEXT NOT NULL,
    payload TEXT,
    private_value TEXT
);

CREATE PUBLICATION feature_probe_pub
FOR TABLE public.feature_probe (id, region, payload)
WHERE (region = 'APAC');
```

Nếu server không hỗ trợ syntax, CREATE PUBLICATION sẽ báo lỗi parse/feature. Sau thử nghiệm, drop publication/table trong lab.

### 12.8. Generated columns từ PostgreSQL 18

Trên PostgreSQL 18:

```sql
CREATE TABLE public.invoice (
    invoice_id BIGINT PRIMARY KEY,
    net_amount NUMERIC(12, 2) NOT NULL,
    tax_amount NUMERIC(12, 2) NOT NULL,
    gross_amount NUMERIC(12, 2)
        GENERATED ALWAYS AS (net_amount + tax_amount) STORED
);

CREATE PUBLICATION invoice_pub
FOR TABLE public.invoice
    (invoice_id, net_amount, tax_amount, gross_amount);
```

Column list có thể nêu generated column trực tiếp. Nếu không dùng explicit list, publication option `publish_generated_columns = stored` điều khiển việc phát hành stored generated columns. Subscriber trước PostgreSQL 18 không copy generated columns trong initial sync; kiểm tra schema và version trước khi dùng.

---

## 13. Security và row-level security

### 13.1. Row filter không phải security boundary

Row filter có thể được dùng để giảm dữ liệu gửi tới subscriber, nhưng không nên là lớp bảo vệ duy nhất cho dữ liệu nhạy cảm.

PostgreSQL hiện không có privilege độc lập trên từng publication để một subscriber chỉ được cấp quyền vào một publication cụ thể. Một replication connection có thể truy cập publications theo quyền và cấu hình hệ thống; các publication khác có thể phát hành cùng dữ liệu.

### 13.2. Column list không phải column-level access control

Column list giúp giảm payload và schema footprint, nhưng không bảo đảm subscriber độc hại không thể lấy dữ liệu cột bị bỏ. Dùng publisher-side privileges, database separation, data masking hoặc pipeline chuyên biệt nếu cần confidentiality.

### 13.3. Role replication

Role kết nối replication phải có thuộc tính REPLICATION hoặc là superuser, cùng quyền LOGIN và quyền SELECT cần thiết cho initial table copy.

Không dùng superuser làm replication user mặc định. Cấp quyền tối thiểu và giới hạn kết nối bằng pg_hba.conf/network policy.

### 13.4. RLS trên publisher

Nếu replication role không có SUPERUSER hoặc BYPASSRLS, row security policies trên publisher có thể được thực thi. Điều này có thể ảnh hưởng rows mà replication connection nhìn thấy.

Nếu không tin cậy tất cả table owners, có thể dùng connection option `options=-crow_security=off` để replication dừng thay vì thực thi một row security policy do owner thêm vào. Kiểm tra documentation security đúng version và thử bằng role thực tế.

### 13.5. Row filter expression và RLS

Row filter là điều kiện publication; RLS là policy kiểm soát row access. Hai lớp có thể cùng ảnh hưởng dữ liệu được đọc/replicate. Đừng giả định một filter thay thế policy hoặc policy thay thế publication scope.

### 13.6. Subscriber privileges

Apply worker trên subscriber chạy với security context theo subscription owner và table owner/role switching rules của version. Bảo đảm owner có thể apply DML trên bảng đích và không tạo trigger/rule ngoài ý muốn.

### 13.7. Bảo vệ credentials và network

- Dùng SCRAM hoặc certificate authentication.
- Dùng TLS và kiểm tra server certificate.
- Bảo vệ password file/secret manager.
- Chỉ mở network cho subscriber cần thiết.
- Theo dõi các replication connections.
- Không log connection string có password.

---

## 14. Monitoring row filters và column lists

### 14.1. Xem publication definition

```sql
SELECT
    pubname,
    schemaname,
    tablename,
    attnames,
    rowfilter
FROM pg_publication_tables
ORDER BY pubname, schemaname, tablename;
```

Đây là cách kiểm tra cấu hình thực tế sau khi publication được tạo/alter. Không chỉ dựa vào migration script đã chạy trong quá khứ.

### 14.2. Xem trạng thái subscription

```sql
SELECT
    subname,
    pid,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription;
```

Nếu subscription không có worker, kiểm tra `subenabled`, connection, slot, logs và trạng thái apply.

### 14.3. Xem table synchronization

```sql
SELECT
    srrelid::regclass AS relation,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY srrelid::regclass::text;
```

Initial sync có thể mất nhiều thời gian với bảng lớn. Row filter giảm số rows phải copy nếu subscriber hỗ trợ; column list giảm số cột trong initial copy nếu phiên bản hỗ trợ.

### 14.4. Kiểm tra dữ liệu thực tế

Trên publisher:

```sql
SELECT COUNT(*)
FROM sales.orders
WHERE tenant_id = 42;
```

Trên subscriber:

```sql
SELECT COUNT(*)
FROM sales.orders;
```

Hai số đếm có thể khác tạm thời khi replication đang lag. Để so sánh chính xác, dừng ghi trong lab hoặc tạo một reconciliation point có thể xác định, rồi đối chiếu theo primary key và nội dung cột được publish.

### 14.5. Kiểm tra cột hiện diện

Trên subscriber:

```sql
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'sales'
  AND table_name = 'orders'
ORDER BY ordinal_position;
```

Đối chiếu với column list và schema contract. Không giả định các cột bị bỏ khỏi publication sẽ tự động bị drop khỏi subscriber.

### 14.6. Kiểm tra replication errors

Đọc PostgreSQL logs trên cả publisher và subscriber. Các lỗi thường liên quan:

- Replica identity thiếu hoặc không hợp lệ.
- Column list không bao gồm identity columns.
- Subscriber thiếu cột được publish.
- Data type mapping không tương thích.
- Apply worker không có quyền ghi.
- Publication column lists xung đột.
- Initial synchronization không tương thích với subscriber cũ.

### 14.7. Metrics vận hành

Theo dõi:

- Subscription worker state.
- Replication lag và latest end LSN/time.
- Initial table sync progress/state.
- Publisher WAL retention/slot health.
- Apply errors và retry count.
- Row counts/reconciliation drift.
- Disk/network/CPU khi initial copy.

Row filter có thể giảm rows nhưng không tự động giảm mọi chi phí logical decoding hoặc mọi metadata work. Column list giảm payload, nhưng hiệu năng cần đo bằng workload thực tế.

---

## 15. Thay đổi publication an toàn

### 15.1. Thêm bảng với row filter và column list

```sql
ALTER PUBLICATION tenant_42_orders
ADD TABLE sales.refunds
    (tenant_id, refund_id, order_id, amount)
    WHERE (tenant_id = 42);
```

Thao tác này thay đổi publication definition ở publisher. Nếu subscription chưa theo dõi bảng mới, cần refresh publication ở subscriber theo quy trình phù hợp để tạo table synchronization worker.

### 15.2. Thay table specification

```sql
ALTER PUBLICATION tenant_42_orders
SET TABLE sales.orders
    (tenant_id, order_id, status, amount, created_at)
    WHERE (tenant_id = 42);
```

SET TABLE thay thế danh sách table members của publication. Nếu publication có nhiều bảng, liệt kê lại toàn bộ các bảng cần giữ; nếu không, các bảng bị bỏ khỏi danh sách sẽ không còn thuộc publication.

### 15.3. Drop một bảng

```sql
ALTER PUBLICATION tenant_42_orders
DROP TABLE sales.refunds;
```

Drop table khỏi publication dừng phát hành changes của bảng đó sau khi transaction thay đổi publication commit. Nó không tự drop bảng trên subscriber và không xóa dữ liệu đã được replicate.

### 15.4. Thay đổi filter

Khi cần mở rộng phạm vi:

```sql
ALTER PUBLICATION tenant_42_orders
SET TABLE sales.orders
    (tenant_id, order_id, status, amount, created_at)
    WHERE (tenant_id IN (42, 43));
```

Thay đổi filter chỉ điều khiển changes tiếp theo. Các rows tenant 43 đã tồn tại trên publisher không tự động được backfill chỉ vì filter mới đã bao gồm chúng.

### 15.5. Thay đổi column list

Khi thêm cột mới:

1. Thêm cột tương thích trên subscriber trước.
2. Xác định giá trị cho các rows đã tồn tại ở subscriber.
3. Cập nhật column list ở publisher.
4. Xác minh publication và subscription tiếp tục hoạt động.
5. Đối soát dữ liệu sau thay đổi.

Không kỳ vọng một ALTER PUBLICATION tự backfill giá trị cột mới cho mọi row cũ.

### 15.6. Thay đổi schema theo expand/contract

Một trình tự an toàn thường là:

1. **Expand:** thêm cột nullable/default-compatible ở subscriber.
2. **Expand:** thêm cột ở publisher.
3. Cập nhật column list để phát hành cột mới.
4. Backfill dữ liệu cũ theo quy trình có kiểm soát.
5. Xác minh subscriber đã đồng bộ.
6. Chuyển ứng dụng sang sử dụng cột mới.
7. **Contract:** loại bỏ cột cũ sau khi mọi consumer đã chuyển.

Logical replication không tự replicate DDL. Schema migration cần được điều phối ở cả hai đầu.

### 15.7. Thay đổi filter cần reconcile

Khi mở rộng filter, cần backfill các rows mới nằm trong phạm vi. Khi thu hẹp filter, cần xóa hoặc archive các rows không còn thuộc phạm vi ở subscriber. Dùng business key và một cutover point có thể kiểm chứng để tránh bỏ sót updates trong lúc backfill.

### 15.8. Nhiều publication cùng subscription

Trước khi ALTER column list:

- Liệt kê publications mà subscription đang theo dõi.
- Xác định các publication khác có cùng table không.
- Bảo đảm column lists không xung đột.
- Bảo đảm row filters được kết hợp theo OR như mong đợi.
- Lập kế hoạch thay đổi và đối soát sau khi apply worker tiếp tục.

---

## 16. Troubleshooting

### 16.1. Server không nhận cú pháp WHERE trong CREATE PUBLICATION

Nguyên nhân thường gặp là publisher PostgreSQL 14 trở xuống. Kiểm tra `SHOW server_version` trên publisher. Row filters được giới thiệu từ PostgreSQL 15.

### 16.2. Column list syntax không được hỗ trợ

Tương tự row filter, column lists được giới thiệu từ PostgreSQL 15. Nâng publisher hoặc thiết kế pipeline khác; đổi client version không làm server cũ hiểu cú pháp mới.

### 16.3. Row filter dùng cột không thuộc replica identity

Nếu publication có UPDATE/DELETE, filter chỉ được tham chiếu các cột thuộc replica identity. Xem:

```sql
SELECT
    c.relname,
    c.relreplident
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'sales'
  AND c.relname = 'orders';
```

`relreplident` cho biết chế độ replica identity. Kiểm tra index thực tế và quyết định thêm key phù hợp hay dùng FULL nếu không có lựa chọn khác.

### 16.4. Column list thiếu identity columns

Nếu publication phát hành UPDATE/DELETE, đảm bảo column list có toàn bộ replica identity columns. Ví dụ bảng có primary key `(tenant_id, order_id)` thì cả hai phải nằm trong list.

### 16.5. Subscriber báo thiếu cột

So sánh `pg_publication_tables.attnames` ở publisher với `information_schema.columns` ở subscriber. Tạo các cột được publish trước khi bật/refresh subscription; kiểm tra tên và kiểu dữ liệu.

### 16.6. Subscriber báo NOT NULL violation

Có thể bảng đích có thêm cột NOT NULL mà publisher không gửi. Thêm default, cho phép NULL, hoặc thay schema mapping để apply INSERT có giá trị hợp lệ.

### 16.7. Initial sync chứa rows ngoài filter

Kiểm tra subscriber version. Nếu subscriber trước PostgreSQL 15, initial sync bỏ qua row filters và copy toàn bộ table data. Lập kế hoạch cleanup/reinitialize hoặc nâng cấp subscriber.

### 16.8. Initial sync có cột bị loại

Nếu subscriber trước PostgreSQL 15, initial sync bỏ qua column lists và copy toàn bộ columns. Nếu schema đích chỉ có subset cột, initial sync có thể lỗi vì thiếu columns.

### 16.9. UPDATE làm subscriber xuất hiện INSERT/DELETE

Đây có thể là behavior đúng. Nếu old row không khớp nhưng new row khớp, UPDATE được chuyển thành INSERT. Nếu old row khớp nhưng new row không khớp, UPDATE được chuyển thành DELETE.

Kiểm tra old/new values và row filter trước khi coi đây là lỗi.

### 16.10. TRUNCATE làm subscriber mất toàn bộ dữ liệu

Row filter không áp dụng cho TRUNCATE. Kiểm tra `pubtruncate`; với publication partial rows, thường loại TRUNCATE khỏi `publish` option.

### 16.11. Row filter không giới hạn dữ liệu như mong đợi

Kiểm tra:

- Subscription có theo dõi publication không filter khác không.
- Bảng có nằm trong `FOR ALL TABLES` hoặc `FOR TABLES IN SCHEMA` publication không.
- Multiple row filters có được OR thành tập rộng hơn không.
- RLS role có ảnh hưởng visibility không.
- Partition đang dùng filter từ root hay leaf.

### 16.12. Subscription lỗi sau khi đổi column list

Kiểm tra xem cùng table có được phát hành bởi nhiều publications với column lists khác nhau hay không. Làm cho các danh sách tương thích và thực hiện quy trình ALTER SUBSCRIPTION/recreate theo hướng dẫn PostgreSQL version.

### 16.13. Generated column không được initial sync

Nếu publisher là PostgreSQL 18 nhưng subscriber trước 18, initial table synchronization không copy generated columns. Nâng subscriber hoặc tạo quy trình initial load tương thích.

### 16.14. Filter expression bị từ chối

Loại bỏ:

- User-defined function/operator/type/collation.
- Non-immutable built-in function.
- System column.
- Cột không thuộc replica identity nếu có UPDATE/DELETE.

Giữ expression đơn giản trên các cột được phép.

### 16.15. Replication lag tăng

Row filters/column lists không bảo đảm replication nhanh hơn trong mọi trường hợp. Kiểm tra logical decoding, WAL generation, network, apply worker, index/constraint overhead trên subscriber và initial sync workers.

---

## 17. Thực hành trong lab

### 17.1. Kiểm tra publisher version

```sql
SHOW server_version;
SELECT current_setting('server_version_num')::integer;
```

Chỉ tiếp tục ví dụ row filter/column list nếu publisher là PostgreSQL 15 trở lên.

### 17.2. Tạo bảng và publication

```sql
CREATE SCHEMA IF NOT EXISTS lab;

CREATE TABLE lab.customer_events (
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    internal_payload JSONB,
    PRIMARY KEY (tenant_id, event_id)
);

CREATE PUBLICATION lab_tenant_42_pub
FOR TABLE lab.customer_events
    (tenant_id, event_id, event_type, event_time)
    WHERE (tenant_id = 42)
WITH (publish = 'insert, update, delete');
```

### 17.3. Xem publication definition

```sql
SELECT
    pubname,
    schemaname,
    tablename,
    attnames,
    rowfilter
FROM pg_publication_tables
WHERE pubname = 'lab_tenant_42_pub';
```

Xác nhận filter tenant 42 và column list chỉ gồm bốn cột đã chọn.

### 17.4. Tạo subscriber table

Trên subscriber:

```sql
CREATE SCHEMA IF NOT EXISTS lab;

CREATE TABLE lab.customer_events (
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
);
```

Bảng đích không cần cột JSONB `internal_payload`.

### 17.5. Tạo subscription

Trên subscriber:

```sql
CREATE SUBSCRIPTION lab_tenant_42_sub
CONNECTION 'host=publisher.example.net dbname=appdb user=replicator sslmode=verify-full'
PUBLICATION lab_tenant_42_pub
WITH (copy_data = true);
```

Đợi initial synchronization hoàn tất rồi kiểm tra `pg_subscription_rel` và `pg_stat_subscription`.

### 17.6. Insert row thuộc tenant được chọn

Trên publisher:

```sql
INSERT INTO lab.customer_events
    (tenant_id, event_id, event_type, event_time, internal_payload)
VALUES
    (42, 1, 'order_created', clock_timestamp(), '{"source":"api"}');
```

Row này được phát hành. Subscriber nhận bốn cột đã chọn.

### 17.7. Insert row ngoài filter

```sql
INSERT INTO lab.customer_events
    (tenant_id, event_id, event_type, event_time, internal_payload)
VALUES
    (43, 2, 'order_created', clock_timestamp(), '{"source":"api"}');
```

Row tenant 43 không được phát hành tới subscriber tenant 42.

### 17.8. UPDATE row đi vào filter

```sql
UPDATE lab.customer_events
SET tenant_id = 42
WHERE tenant_id = 43
  AND event_id = 2;
```

Old row không khớp, new row khớp. Subscriber nhận INSERT cho row này.

### 17.9. UPDATE row rời filter

```sql
UPDATE lab.customer_events
SET tenant_id = 43
WHERE tenant_id = 42
  AND event_id = 1;
```

Old row khớp, new row không khớp. Subscriber nhận DELETE cho row đó.

### 17.10. Xác nhận dữ liệu đích

Trên subscriber:

```sql
SELECT *
FROM lab.customer_events
ORDER BY tenant_id, event_id;
```

Không có cột `internal_payload`; rows trong subscriber phản ánh điều kiện filter hiện hành sau khi các thay đổi đã apply.

### 17.11. Kiểm tra TRUNCATE không được publish

```sql
SELECT pubname, pubtruncate
FROM pg_publication
WHERE pubname = 'lab_tenant_42_pub';
```

Giá trị phải là false theo cấu hình publication ví dụ. Không thử TRUNCATE trên production để kiểm chứng.

### 17.12. Dọn lab

Chỉ trên môi trường lab:

```sql
-- Trên subscriber: dừng và xóa subscription trước
DROP SUBSCRIPTION IF EXISTS lab_tenant_42_sub;

-- Trên publisher:
DROP PUBLICATION IF EXISTS lab_tenant_42_pub;
DROP TABLE IF EXISTS lab.customer_events;
```

Nếu subscription đang dùng replication slot trên publisher, kiểm tra slot đã được giải phóng hoặc xử lý theo quy trình trước khi drop publication.

---

## 18. Những hiểu lầm thường gặp

**1. “Row filters được hỗ trợ từ PostgreSQL 14.”** Sai. Row filters được giới thiệu ở PostgreSQL 15.

**2. “Column lists là tính năng PostgreSQL 18.”** Sai. Column lists có từ PostgreSQL 15; PostgreSQL 18 bổ sung generated-column replication.

**3. “Chỉ cần publisher 15+, subscriber version không quan trọng.”** Sai. Subscriber trước 15 bỏ qua row filters và column lists trong initial data synchronization.

**4. “Row filter chỉ kiểm tra new row khi UPDATE.”** Sai. PostgreSQL đánh giá cả old và new row, rồi có thể chuyển UPDATE thành INSERT hoặc DELETE.

**5. “Filter tenant_id = 42 sẽ tự xóa mọi rows tenant khác khỏi subscriber.”** Không. Filter áp dụng changes được phát hành; thay đổi filter không tự reconcile toàn bộ dữ liệu đã có.

**6. “Row filter có thể dùng function tùy chỉnh.”** Không. Expression bị giới hạn; user-defined functions/operators/types/collations và non-immutable built-ins không được phép.

**7. “Row filter có thể tham chiếu bất kỳ cột nào.”** Chỉ khi publication chỉ publish INSERT. Nếu có UPDATE/DELETE, filter columns phải thuộc replica identity.

**8. “Column list có thể bỏ primary key trong mọi trường hợp.”** Không. Với UPDATE/DELETE, phải giữ tất cả replica identity columns.

**9. “Column list cho phép rename hoặc tính toán cột.”** Không. Nó chỉ nhận simple column references.

**10. “Column list bảo đảm dữ liệu cột bị bỏ không thể truy cập.”** Không. Đây không phải security boundary.

**11. “Row filter áp dụng cho TRUNCATE.”** Không. TRUNCATE không được filter theo rows.

**12. “Column list áp dụng cho TRUNCATE.”** Không. TRUNCATE không mang row columns.

**13. “Có thể kết hợp nhiều row filters bằng AND.”** Không. Các filters của cùng table/operation trong nhiều publications được kết hợp bằng OR.

**14. “Một publication không filter không ảnh hưởng publication filter khác.”** Sai. Publication không filter có thể làm filter kia trở nên dư thừa.

**15. “Có thể union column lists từ nhiều publications.”** Không. Một subscription không hỗ trợ cùng table với các column lists khác nhau.

**16. “Thứ tự cột trong column list là thứ tự gửi.”** Không. Thứ tự tên cột không được bảo toàn như một phép sắp xếp vị trí.

**17. “Không có column list tương đương liệt kê toàn bộ cột hiện tại.”** Không. Không khai báo list sẽ bao gồm cột thêm trong tương lai; explicit list thì không.

**18. “Subscriber phải có schema giống hệt publisher.”** Không nhất thiết, nhưng phải có tất cả cột được publish và kiểu dữ liệu tương thích; cột bổ sung phải có giá trị hợp lệ khi INSERT.

**19. “DDL được replicate cùng row changes.”** Không. Logical replication không tự phát hành DDL.

**20. “Thay đổi row filter tự backfill dữ liệu cũ.”** Không. Cần initial sync/backfill/reconciliation riêng.

**21. “FOR TABLES IN SCHEMA hỗ trợ column list.”** Không. Column lists không được hỗ trợ khi publication cũng dùng FOR TABLES IN SCHEMA.

**22. “Partitioned table luôn dùng filter của root.”** Không. Phụ thuộc `publish_via_partition_root`.

**23. “Subscriber trước 18 luôn nhận generated columns khi publisher bật option.”** Không. Initial sync từ publisher 18 tới subscriber trước 18 không copy generated columns.

**24. “publish = 'update, delete' nghĩa initial sync không copy rows.”** Không. Initial data synchronization không tuân theo publish operation list.

**25. “Row filter thay thế RLS.”** Không. RLS và publication filter là hai cơ chế khác nhau, có thể cùng ảnh hưởng dữ liệu.

**26. “Filter đúng thì mọi subscriber chỉ có thể xem dữ liệu được lọc.”** Không. Security phải được thực thi ở publisher và network/role boundary.

**27. “pg_publication_tables chỉ là metadata không cần kiểm tra.”** Sai. Đây là nơi hữu ích để xác nhận cấu hình publication thực tế.

**28. “Column list luôn làm replication nhanh hơn.”** Không bảo đảm. Hiệu năng phụ thuộc decoding, WAL rate, network, apply và workload.

**29. “copy_data = false tự đồng bộ dữ liệu cũ.”** Không. Nó bỏ qua initial copy; cần initial load riêng được phối hợp.

**30. “TRUNCATE an toàn với subscriber partial data vì row filter giới hạn tenant.”** Sai. Tắt truncate publishing hoặc thiết kế semantics riêng.

---

## 19. Bài tập thực hành và đáp án

### Bài 1 — Phiên bản

**Câu hỏi:** Phiên bản PostgreSQL nào đầu tiên hỗ trợ row filters và column lists?

**Đáp án:** PostgreSQL 15.

### Bài 2 — Publisher cũ

**Câu hỏi:** Publisher PostgreSQL 14 có thể tạo publication với WHERE row filter không?

**Đáp án:** Không. Cú pháp được giới thiệu ở PostgreSQL 15.

### Bài 3 — Subscriber cũ

**Câu hỏi:** Publisher 15, subscriber 14: initial sync có áp dụng row filter không?

**Đáp án:** Không. Subscriber trước 15 copy toàn bộ rows trong initial synchronization.

### Bài 4 — Column list

**Yêu cầu:** Chỉ phát hành id và status.

```sql
CREATE PUBLICATION p_orders
FOR TABLE sales.orders (id, status);
```

### Bài 5 — Row filter

**Yêu cầu:** Chỉ phát hành tenant 42.

```sql
CREATE PUBLICATION p_tenant_42
FOR TABLE sales.orders
WHERE (tenant_id = 42);
```

### Bài 6 — Kết hợp

**Yêu cầu:** Chỉ phát hành tenant 42 và bốn cột.

```sql
CREATE PUBLICATION p_tenant_42
FOR TABLE sales.orders (tenant_id, order_id, status, amount)
WHERE (tenant_id = 42);
```

### Bài 7 — NULL

**Câu hỏi:** Row filter trả NULL thì row có được publish không?

**Đáp án:** Không. Chỉ TRUE được giữ lại.

### Bài 8 — Immutable expression

**Câu hỏi:** Có thể dùng now() trong row filter không?

**Đáp án:** Không. Đây là hàm không immutable.

### Bài 9 — User-defined function

**Câu hỏi:** Có thể gọi hàm tùy chỉnh trong row filter không?

**Đáp án:** Không. Row filter chỉ cho phép biểu thức đơn giản theo quy tắc PostgreSQL.

### Bài 10 — Replica identity

**Câu hỏi:** Với UPDATE/DELETE, các cột row filter phải thuộc đâu?

**Đáp án:** Replica identity.

### Bài 11 — Column list identity

**Câu hỏi:** Column list của publication có UPDATE/DELETE phải chứa gì?

**Đáp án:** Tất cả replica identity columns.

### Bài 12 — Insert only

**Câu hỏi:** Nếu publication chỉ publish INSERT, filter có thể dùng cột không thuộc replica identity không?

**Đáp án:** Có.

### Bài 13 — Update vào filter

**Câu hỏi:** Old row không khớp, new row khớp: subscriber nhận gì?

**Đáp án:** INSERT.

### Bài 14 — Update ra khỏi filter

**Câu hỏi:** Old row khớp, new row không khớp: subscriber nhận gì?

**Đáp án:** DELETE.

### Bài 15 — Cả hai khớp

**Câu hỏi:** Old và new đều khớp: subscriber nhận gì?

**Đáp án:** UPDATE.

### Bài 16 — TRUNCATE

**Câu hỏi:** Row filter có giới hạn TRUNCATE theo tenant không?

**Đáp án:** Không. TRUNCATE không bị row filter giới hạn.

### Bài 17 — Publish option

**Yêu cầu:** Không phát hành TRUNCATE.

```sql
CREATE PUBLICATION p_partial
FOR TABLE sales.orders WHERE (tenant_id = 42)
WITH (publish = 'insert, update, delete');
```

### Bài 18 — Nhiều filters

**Câu hỏi:** Hai publications cùng table với filters tenant 42 và 43 kết hợp ra sao?

**Đáp án:** OR; subscription nhận tenant 42 hoặc 43 nếu cả hai publications được theo dõi.

### Bài 19 — Publication không filter

**Câu hỏi:** Một publication không filter có thể làm filter khác vô hiệu không?

**Đáp án:** Có. Nó có thể phát hành tất cả rows cho operation đó.

### Bài 20 — Column list conflict

**Câu hỏi:** Một subscription có thể theo dõi cùng table từ hai publications với column lists khác nhau không?

**Đáp án:** Không được hỗ trợ.

### Bài 21 — Column order

**Câu hỏi:** Column list có bảo toàn thứ tự cột không?

**Đáp án:** Không. Logical replication ánh xạ theo tên cột.

### Bài 22 — Subscriber schema

**Câu hỏi:** Subscriber có thể có thêm cột riêng không?

**Đáp án:** Có, nhưng phải có giá trị hợp lệ khi apply INSERT, ví dụ nullable hoặc có default.

### Bài 23 — Future column

**Câu hỏi:** Không khai báo column list có tự phát hành cột thêm về sau không?

**Đáp án:** Có. Explicit column list thì cột mới không tự động được thêm vào.

### Bài 24 — Partition root

**Câu hỏi:** Tham số nào quyết định row filter/column list lấy từ root hay leaf partition?

**Đáp án:** `publish_via_partition_root`.

### Bài 25 — Initial sync

**Câu hỏi:** Initial sync có tuân theo publish operation list không?

**Đáp án:** Không. Publish option chọn DML changes, không điều khiển copy existing data.

### Bài 26 — copy_data

**Câu hỏi:** copy_data=false có làm initial copy không?

**Đáp án:** Không. Cần initial load riêng.

### Bài 27 — PostgreSQL 18

**Câu hỏi:** Phiên bản nào bổ sung generated-column replication?

**Đáp án:** PostgreSQL 18.

### Bài 28 — Catalog

**Yêu cầu:** Xem row filter và column list.

```sql
SELECT pubname, schemaname, tablename, attnames, rowfilter
FROM pg_publication_tables;
```

### Bài 29 — Version check

**Yêu cầu:** Kiểm tra publisher có version 15+.

```sql
SELECT current_setting('server_version_num')::integer >= 150000;
```

### Bài 30 — Security

**Câu hỏi:** Column list có thể thay thế publisher-side security controls không?

**Đáp án:** Không. Column list không phải ranh giới bảo mật.

---

## 20. Checklist triển khai

### Phiên bản

1. Xác nhận publisher version là PostgreSQL 15+.
2. Xác nhận subscriber version và initial-sync behavior.
3. Nếu dùng generated columns, kiểm tra publisher/subscriber có hỗ trợ PostgreSQL 18.
4. Đọc release notes cho các version cụ thể.

### Publication

5. Xác định row scope theo tenant/region/business rule.
6. Chọn expression đơn giản, immutable.
7. Nếu có UPDATE/DELETE, chỉ dùng filter columns thuộc replica identity.
8. Chọn column list cần thiết.
9. Giữ tất cả replica identity columns trong list khi có UPDATE/DELETE.
10. Kiểm tra table không nằm trong publication khác không filter.
11. Kiểm tra multiple filters được OR đúng ý định.
12. Tránh column-list mismatch cho cùng table trong một subscription.
13. Tắt TRUNCATE publishing cho partial-data subscribers nếu không có semantics đặc biệt.

### Subscriber

14. Tạo bảng đích có tất cả published columns.
15. Kiểm tra data types, nullability, defaults và replica identity.
16. Quyết định copy_data true/false.
17. Nếu subscriber trước 15, xử lý initial sync copy all rows/columns.
18. Nếu subscriber trước 18, xử lý generated columns initial sync.
19. Chuẩn bị quyền apply DML và replication connection.

### Vận hành

20. Kiểm tra pg_publication_tables.
21. Kiểm tra pg_subscription và pg_stat_subscription.
22. Theo dõi table synchronization state.
23. Đối soát rows/cột theo một cutover point.
24. Kiểm tra filter changes có cần backfill/cleanup.
25. Điều phối schema migration ở publisher và subscriber.
26. Kiểm tra RLS/role context.
27. Không dùng filter/list làm security boundary.
28. Theo dõi WAL, replication lag và apply errors.
29. Test INSERT/UPDATE/DELETE đi vào/ra filter.
30. Test restore/recovery và runbook trước production rollout.

---

## 21. Tổng kết

Row filters và column lists giúp logical replication phát hành một tập con dữ liệu của bảng. Row filter quyết định **hàng nào** được gửi; column list quyết định **cột nào** được gửi. Hai tính năng được giới thiệu trong PostgreSQL 15 và có các giới hạn quan trọng về replica identity, initial synchronization, partitioning, nhiều publications và version compatibility.

Các điểm cần nhớ:

- Publisher phải là PostgreSQL 15 trở lên để khai báo row filters và column lists.
- Subscriber trước PostgreSQL 15 bỏ qua row filters/column lists trong initial data synchronization; nó có thể copy tất cả rows và columns.
- PostgreSQL 18 bổ sung generated-column replication; subscriber trước 18 có giới hạn khi initial copy generated columns.
- Nếu publication có UPDATE/DELETE, filter columns phải thuộc replica identity và column list phải chứa toàn bộ identity columns.
- UPDATE được đánh giá trên cả old/new row; thay đổi membership có thể được phát hành dưới dạng INSERT hoặc DELETE.
- Row filter chỉ nhận biểu thức đơn giản, không cho user-defined functions/operators/types/collations, system columns hoặc non-immutable built-ins.
- Column list chỉ nhận tên cột đơn giản; không hỗ trợ transform, alias hoặc rename.
- Row filters và column lists không giới hạn TRUNCATE. Với subscriber partial data, thường tắt truncate publishing.
- Row filters từ nhiều publications cùng table/operation kết hợp bằng OR; column lists khác nhau cho cùng table trong một subscription không được hỗ trợ.
- Partition root/leaf quyết định filter và column list được chọn qua `publish_via_partition_root`.
- Initial data synchronization áp dụng row filters/column lists theo phiên bản subscriber; publish operation list không điều khiển initial copy.
- Thay filter hoặc column list không tự backfill/reconcile dữ liệu đã có. Cần schema migration, initial load hoặc backfill có kiểm soát.
- Row filter và column list không phải ranh giới bảo mật; bảo vệ dữ liệu ở publisher và network/role layer.

**Câu hỏi tự kiểm tra:** Một publisher PostgreSQL 18 phát hành bảng orders cho tenant 42 với row filter và column list, nhưng subscriber đang chạy PostgreSQL 14. Vì sao subscriber có thể nhận nhiều hàng và cột hơn mong đợi trong initial sync? Vì initial synchronization trên subscriber trước PostgreSQL 15 không áp dụng hai tính năng này. Để triển khai đúng, kiểm tra version ở cả hai đầu, replica identity, schema đích, publish options và mọi publication khác cùng phát hành bảng.

### Tài liệu PostgreSQL chính thức

- [PostgreSQL 15 Release Notes — row filters and column lists](https://www.postgresql.org/docs/15/release-15.html).
- [CREATE PUBLICATION — PostgreSQL 15](https://www.postgresql.org/docs/15/sql-createpublication.html).
- [Row Filters — PostgreSQL 15](https://www.postgresql.org/docs/15/logical-replication-row-filter.html).
- [Column Lists — PostgreSQL 15](https://www.postgresql.org/docs/15/logical-replication-col-lists.html).
- [CREATE PUBLICATION — Current](https://www.postgresql.org/docs/current/sql-createpublication.html).
- [Row Filters — Current](https://www.postgresql.org/docs/current/logical-replication-row-filter.html).
- [Column Lists — Current](https://www.postgresql.org/docs/current/logical-replication-col-lists.html).
- [Publication and Replica Identity — Current](https://www.postgresql.org/docs/current/logical-replication-publication.html).
- [Logical Replication Security — Current](https://www.postgresql.org/docs/current/logical-replication-security.html).
- [Logical Replication Architecture and Initial Snapshot — Current](https://www.postgresql.org/docs/current/logical-replication-architecture.html).
- [PostgreSQL 18 Release Notes — generated columns in logical replication](https://www.postgresql.org/docs/current/release-18.html).
- [CREATE SUBSCRIPTION — Current](https://www.postgresql.org/docs/current/sql-createsubscription.html).
- [Monitoring Statistics — Current](https://www.postgresql.org/docs/current/monitoring-stats.html).
