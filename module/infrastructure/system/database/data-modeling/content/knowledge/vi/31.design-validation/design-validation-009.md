# Kiểm thử chuyển đổi lược đồ, đối soát và khả năng khôi phục

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, chất lượng một thiết kế không chỉ nằm ở ERD đẹp, chuẩn hóa đúng hay câu lệnh `CREATE TABLE` chạy thành công. Khi hệ thống đang hoạt động, một thay đổi lược đồ có thể làm **mất sự tương thích giữa các phiên bản ứng dụng, biến đổi sai dữ liệu lịch sử, nhân bản sự kiện hoặc phá đường khôi phục**. Vì vậy, kiểm chứng thiết kế phải đi xuyên qua cả **schema, dữ liệu, ứng dụng, tích hợp và vận hành**.

Bài học thuộc chương **Kiểm chứng thiết kế** tập trung vào ba năng lực:

1. **Kiểm thử chuyển đổi lược đồ (*schema migration testing*):** cấu trúc mới có triển khai được khi ứng dụng cũ/mới cùng chạy, các ràng buộc còn đúng và tác động lên giao dịch có nằm trong giới hạn?
2. **Đối soát (*reconciliation*):** từng thực thể, giá trị, số đo và tập dữ liệu trong mô hình mới có giữ đúng ý nghĩa từ nguồn không?
3. **Khả năng khôi phục (*recoverability*):** khi deployment, backfill hoặc hệ lưu trữ gặp sự cố, có thể tiếp tục, chuyển ngược đường đọc/ghi, dựng lại dữ liệu hay phục hồi tới một mốc đã được kiểm chứng không?

Sau bài này, bạn có thể xây một **kế hoạch kiểm chứng có điều kiện đạt/không đạt**, viết SQL kiểm tra khóa và sai khác dữ liệu, thiết kế backfill idempotent, thử tình huống lỗi có chủ đích trong môi trường an toàn, xác định RPO/RTO và ra quyết định **go / no-go** dựa trên bằng chứng.

## 1. “Migration chạy thành công” không đồng nghĩa “thiết kế đã được kiểm chứng”

Giả sử hệ Orders chuyển từ `amount_cents INTEGER` sang `amount_minor BIGINT`. Migration có thể trả mã thoát 0 sau:

~~~sql
ALTER TABLE orders ADD COLUMN amount_minor BIGINT;
~~~

Nhưng các câu hỏi quan trọng vẫn còn:

- Các đơn **đã tồn tại** có được chuyển đầy đủ sang cột mới chưa?
- Các **writer cũ** còn ghi `amount_cents` có cập nhật `amount_minor` không?
- Mọi **reader mới** có tránh đọc giá trị chưa backfill hoặc đã cũ không?
- Các ứng dụng Java, ETL, CDC, API/event và dashboard có hiểu **kiểu dữ liệu và đơn vị tiền mới**?
- Nếu backfill chết sau 30% dữ liệu, chạy lại có **nhân bản hoặc ghi đè cập nhật mới hơn** không?
- Nếu DB hoặc node đang giữ lock bị lỗi, giao dịch nguồn có còn nhất quán không?
- Nếu xóa cột cũ rồi phát hiện lỗi, liệu chỉ deploy lại binary cũ có còn hoạt động?
- Đã **diễn tập khôi phục** từ backup/transaction log và đo thời gian thực tế chưa?

Do đó, một lần đổi lược đồ chỉ được xem là hoàn tất khi **cả cấu trúc và dữ liệu đã được xác minh**, các consumer đã được chuyển và phương án phục hồi được đánh giá tương xứng với rủi ro.

> **Kiểm chứng migration là kiểm chứng những bất biến nghiệp vụ trong khi mô hình cũ và mới có thể cùng tồn tại, không chỉ xác nhận SQL không báo lỗi.**

## 2. Xác định đối tượng kiểm chứng trước khi viết test

Một bài kiểm thử tốt phải trả lời chính xác **đang bảo vệ điều gì**.

| Khía cạnh | Bất biến cần bảo vệ | Ví dụ bằng chứng |
|---|---|---|
| **Grain và khóa** | Một dòng đại diện đúng một đơn vị nghiệp vụ | `UNIQUE(tenant_id,order_id)` và query tìm duplicate |
| **Giá trị** | Ánh xạ cũ → mới giữ đúng ý nghĩa | `amount_minor = amount_cents::BIGINT` trong cùng đơn vị |
| **Quan hệ** | Không có tham chiếu sai tenant hoặc FK mồ côi | Anti-join và FK validation |
| **Tính đầy đủ** | Không mất bản ghi do lọc, paging hoặc đến muộn | Đếm khóa và đối chiếu tập khóa |
| **Ứng dụng** | Mọi phiên bản còn chạy đều hiểu schema hiện hành | Compatibility matrix + integration tests |
| **Tính nhất quán** | Writer cạnh tranh không để hai biểu diễn lệch nhau | Concurrency test, row-level mismatch |
| **Độ trễ và tải** | DDL/backfill không vượt giới hạn vận hành | Lock wait, WAL, replication lag, latency |
| **Khôi phục** | Có thể phục hồi theo RPO/RTO mục tiêu | Restore drill và bằng chứng đo |
| **Tích hợp** | Event/API/CDC không đổi nghĩa ngoài ý muốn | Contract tests, dedupe/replay |
| **Bảo mật** | Migration không nới quyền hoặc làm lộ bản sao dữ liệu | Kiểm thử tenant, masking, retention |

**Một bất biến có thể cần nhiều phép thử.** `COUNT(*)` bằng nhau không chứng minh dữ liệu đúng từng dòng; tổng tiền khớp không chứng minh hai hóa đơn không bị hoán đổi; `PRIMARY KEY` kỹ thuật không chứng minh sự kiện nguồn chỉ được nạp một lần.

### 2.1. Bắt đầu từ grain, không từ câu lệnh ALTER

Ví dụ nguồn:

~~~text
orders:
    Một dòng = một đơn hàng hiện hành
    Khóa nghiệp vụ = (tenant_id, order_id)
    Số tiền = amount_cents trong đơn vị cent của USD
    Chủ sở hữu nghiệp vụ = Orders domain
~~~

Nếu mô hình đích đổi thành **một dòng hàng của đơn** hoặc **một sự kiện thanh toán**, việc đối soát `COUNT(*)` giữa hai bảng **không còn là phép thử phù hợp**. Trước tiên phải mô tả quan hệ giữa hai grain, sau đó mới chọn phép tổng hợp và kiểm tra.

### 2.2. Không lấy dữ liệu mẫu làm bằng chứng đầy đủ

Một bộ 10 đơn toàn số tiền dương, cùng tenant và không có cập nhật cạnh tranh chỉ kiểm tra đường đi thuận lợi. Cần thêm:

- Đơn chưa có dữ liệu mới, dữ liệu null, dữ liệu trễ.
- Nhiều tenant dùng trùng số đơn hiển thị.
- Giá trị 0, sát giới hạn `INTEGER`, vượt giới hạn `INTEGER` sau khi contract.
- Sự kiện nạp lại, nhiều worker chạy đồng thời, giao dịch bị rollback.
- Tình huống lock, timeout, mất kết nối, job dừng giữa lô.
- Dữ liệu lịch sử thuộc nhiều partition, các kỳ đã chốt và các consumer ít chạy.

**Dữ liệu test phải có phản ví dụ**, không chỉ có những bản ghi giúp migration trông đúng.

## 3. Một kế hoạch test gắn với expand–migrate–contract

Chiến lược **mở rộng → chuyển đổi dần → thu hẹp** chia rủi ro thành các điểm kiểm soát.

~~~mermaid
flowchart TD
    B["Baseline: nguồn và consumer"] --> E["EXPAND: thêm cấu trúc"]
    E --> C1{"Schema + app cũ tương thích?"}
    C1 -->|Không| S["Stop / xử lý / giữ hệ cũ"]
    C1 -->|Có| M["MIGRATE: sync, backfill, shadow read"]
    M --> C2{"Không mất dữ liệu, mismatch = 0?"}
    C2 -->|Không| F["Tạm dừng và sửa rồi chạy lại"]
    F --> M
    C2 -->|Có| R["Canary / cutover reader và writer"]
    R --> C3{"Consumer và SLO đều đạt?"}
    C3 -->|Không| M
    C3 -->|Có| D["CONTRACT: bỏ cấu trúc cũ"]
    D --> V["Validate + recovery drill + theo dõi"]
~~~

| Pha | Đối tượng kiểm thử | Điều kiện chuyển pha |
|---|---|---|
| **Baseline** | Dữ liệu nguồn, khóa, chất lượng, consumer, SLA | Có số đo và hiểu ý nghĩa cần giữ |
| **Expand** | Additive DDL, lock, quyền, app cũ còn chạy | Cấu trúc mới không phá writer/reader cũ |
| **Sync** | New writes, old writes, rollback giao dịch, concurrency | Không phát sinh dữ liệu cũ–mới lệch |
| **Backfill** | Batch/retry/idempotency, tiến độ và nguồn | Không có dòng thiếu/sai ngoài ngoại lệ được duyệt |
| **Read cutover** | Shadow read, canary, compatibility, latency | Chênh lệch bằng 0, SLO đạt |
| **Write cutover** | Toàn bộ writer chuyển, type/range mới | Không còn writer cần cấu trúc cũ |
| **Contract** | Không còn consumer cũ, ràng buộc mới, backup/recovery | Được duyệt xóa; biết điểm không quay lại |
| **Post-deploy** | Reconciliation liên tục, replay, restore drill | Không có lệch âm thầm sau cutover |

**Không gom tất cả test vào cuối kỳ migration.** Nếu không kiểm chứng sync trước backfill, dữ liệu có thể bắt đầu lệch khi các writer cũ tiếp tục cập nhật. Nếu không thử phục hồi trước contract, đến lúc xóa cột cũ mới biết backup không dùng được.

## 4. Ma trận tương thích ứng dụng và schema

Giả định:

- **S0:** chỉ có `amount_cents`.
- **S1:** có `amount_cents` và `amount_minor`, giữ cơ chế đồng bộ.
- **S2:** chỉ còn `amount_minor`.

Ứng dụng:

- **A0:** code cũ chỉ biết `amount_cents`.
- **A1:** code chuyển tiếp biết cả hai cột.
- **A2:** code mới chỉ biết `amount_minor`.

| App / Schema | S0 | S1 | S2 |
|---|---|---|---|
| **A0** | Hợp lệ | Hợp lệ **nếu bridge bảo toàn hợp đồng cũ** | **Không hợp lệ** |
| **A1** | Chỉ khi không tham chiếu cột chưa tồn tại | Hợp lệ nếu sync/backfill đúng | Tùy A1 còn dùng cột cũ hay không |
| **A2** | Không hợp lệ | Có thể đọc mới khi dữ liệu đủ; ghi phụ thuộc chiến lược | Hợp lệ |

**Bẫy:** `COALESCE(amount_minor,amount_cents)` vẫn **lỗi cú pháp trên S0** vì cột mới chưa tồn tại. Do đó **thêm schema trước khi deploy code tham chiếu schema mới**, trừ khi ứng dụng có cơ chế phát hiện capability/đường SQL riêng được kiểm thử.

### Những consumer dễ bị bỏ quên

- API server đang rolling deploy.
- Java background worker, cron/batch, ứng dụng quản trị.
- Mobile/desktop client sống lâu, nếu nó phụ thuộc vào hợp đồng public.
- Stored procedure, view, trigger, reporting query, BI semantic layer.
- CDC connector, schema registry, message producer/consumer và data lake.
- Các job chạy cuối tuần/cuối tháng/cuối quý.
- Quy trình backup, restore, data export và kiểm tra phục hồi.

Tài liệu migration phải ghi **owner, cách xác định đã chuyển và bằng chứng** của từng nhóm; “ứng dụng chính đã deploy” chưa đủ cho phép xóa cấu trúc cũ.

## 5. Ví dụ xuyên suốt: cột tiền cũ và cột tiền mới

Ta dùng **PostgreSQL** để xây một bài kiểm thử cụ thể. Các lệnh SQL là ví dụ đào tạo, phải thử trên môi trường riêng và điều chỉnh theo phiên bản DBMS, dữ liệu/lock thực tế; **không chạy tùy tiện trên production**.

### 5.1. Ngữ nghĩa và giới hạn phạm vi

~~~text
Bảng nguồn: orders
Grain: mỗi (tenant_id,order_id) có một dòng hiện hành
Cột cũ: amount_cents INTEGER NOT NULL
Cột mới: amount_minor BIGINT
Tiền tệ trong ví dụ: USD; cả hai vẫn đo đơn vị cent
Mapping: amount_minor = amount_cents::BIGINT
Giá trị hợp lệ: >= 0 theo nghiệp vụ ví dụ
~~~

**Đây là thay đổi tên và miền biểu diễn, không phải thay đơn vị**. Trên một hệ đa tiền tệ, *minor unit* có thể không phải cent cho mọi loại tiền; không dùng phép cast ví dụ để tự giải quyết quy đổi tiền tệ.

Bảng giả định:

~~~sql
CREATE TABLE orders (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    currency_code CHAR(3) NOT NULL CHECK (currency_code = 'USD'),
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
~~~

**Key** dùng trong đối soát là `(tenant_id,order_id)`, không dùng `order_id` riêng nếu ID chỉ duy nhất trong tenant. `updated_at` dùng theo dõi thay đổi trạng thái nguồn, **không nhất thiết** là thời gian sự kiện kinh doanh.

### 5.2. Expand schema

~~~sql
ALTER TABLE orders
    ADD COLUMN amount_minor BIGINT;
~~~

Ở giai đoạn đầu cột mới **nullable** để app cũ còn hoạt động và dữ liệu lịch sử chưa backfill có thể tồn tại hợp lệ. Nên kiểm tra lock và tốc độ thực tế. Thêm cột nullable không default thường nhẹ trên PostgreSQL hiện đại, nhưng **không có nghĩa không lấy lock**.

### 5.3. Bridge đồng bộ writer cũ với cột mới

Trong S1, app cũ vẫn ghi `amount_cents`. Một mẫu bridge đơn giản trong **cùng DB transaction**:

~~~sql
CREATE OR REPLACE FUNCTION sync_order_amount_from_legacy()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.amount_minor := NEW.amount_cents::BIGINT;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_orders_amount_legacy
BEFORE INSERT OR UPDATE OF amount_cents ON orders
FOR EACH ROW
EXECUTE FUNCTION sync_order_amount_from_legacy();
~~~

Đây là bridge **từ cột cũ sang cột mới**, không phải hai nguồn chân lý. Khi A0 tiếp tục `INSERT` hoặc sửa `amount_cents`, trigger điền `amount_minor` trong **cùng transaction**.

Trong S1, **writer mới vẫn phải ghi tương thích với cột cũ**: ví dụ ghi `amount_cents` (và nếu muốn, ghi `amount_minor` cùng giá trị) cho đến khi mọi reader/writer cũ đã rời hệ. Writer chỉ sửa `amount_minor` khi cột cũ vẫn bắt buộc có giá trị và còn được đọc **không phải đường ghi hợp lệ**.

Đặt thêm guard để chặn trạng thái hai cột khác nhau đối với **dòng được ghi sau khi tạo guard**:

~~~sql
ALTER TABLE orders
    ADD CONSTRAINT orders_amount_mapping_consistent
    CHECK (
        amount_minor IS NULL
        OR amount_minor = amount_cents::BIGINT
    ) NOT VALID;
~~~

`NOT VALID` trên PostgreSQL cho phép chưa quét xác nhận các dòng lịch sử tại lúc thêm constraint nhưng **các thao tác ghi/update sau đó vẫn phải tuân theo CHECK**. Trigger giúp đường ghi legacy đạt điều kiện. Guard **không thay thế kiểm thử nhiều writer, trigger bị vô hiệu, bulk load hoặc replication đặc biệt**.

### 5.4. Backfill theo lô có thể chạy lại

~~~sql
WITH batch AS (
    SELECT tenant_id, order_id
    FROM orders
    WHERE amount_minor IS NULL
    ORDER BY tenant_id, order_id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE orders AS o
SET amount_minor = o.amount_cents::BIGINT
FROM batch AS b
WHERE o.tenant_id = b.tenant_id
  AND o.order_id = b.order_id
  AND o.amount_minor IS NULL
RETURNING o.tenant_id, o.order_id, o.amount_minor;
~~~

Giải thích:

- Mỗi lần chạy chọn tối đa **500 dòng chưa chuyển** và khóa dòng được chọn.
- `SKIP LOCKED` giúp nhiều worker tránh chờ cùng một dòng đã khóa, nhưng **không bảo đảm công bằng hoặc sẽ xử lý hết nếu các dòng luôn bị khóa**.
- Cập nhật cột mới từ **cột cũ của bản ghi được khóa**, không dùng snapshot tiền đã đọc từ trước khi lock.
- Nếu transaction chết trước commit, dòng trở lại trạng thái cũ; chạy lại chọn những dòng còn NULL. Nếu đã commit, điều kiện `IS NULL` giúp tránh ghi lại.
- Một trigger chỉ bật trên `UPDATE OF amount_cents` không chạy khi câu này chỉ SET `amount_minor`; guard vẫn được kiểm tra.
- Cần điều tiết tốc độ, timeout, lag, WAL và kích thước lô theo hệ thật; **500 là con số minh họa**.

**Không cập nhật cả triệu dòng trong một transaction chỉ vì SQL trông ngắn.** Transaction lớn có thể kéo dài lock, tạo áp lực MVCC/WAL, replication lag và làm khó dừng/khôi phục.

## 6. Kiểm thử migration từ cấu trúc tới dữ liệu

### 6.1. Thử tính tương thích của bản triển khai

Trong môi trường test có cùng các bước migration:

1. Chạy **A0 với S0**, lưu baseline các truy vấn và thao tác ghi.
2. Thực hiện **expand S0 → S1**, chạy lại tất cả test của A0.
3. Kiểm tra schema bằng metadata DB: cột mới tồn tại, kiểu đúng, cột cũ chưa bị bỏ, quyền không tự mở rộng.
4. Cho writer cũ ghi mới/cập nhật, xác nhận bridge điền cột mới.
5. Cho app chuyển tiếp đọc cả cột cũ/mới và so kết quả; không vội chuyển toàn bộ lưu lượng.
6. Thử restart, rolling deploy, connection pool và transaction đang mở tại thời điểm DDL.
7. Chỉ sau khi mọi consumer không còn phụ thuộc cột cũ, thử **S2 với A2** trong môi trường khôi phục độc lập.

Đừng mặc định `SELECT *` hoặc cơ chế ORM phản chiếu tự động (*reflection*) không bị tác động khi thêm cột: code deserialize theo thứ tự/số cột có thể nhạy cảm ngay cả với thay đổi “chỉ thêm trường”.

### 6.2. Unit test cho hàm ánh xạ

Với mapping `amount_minor = amount_cents::BIGINT`, các ca tối thiểu:

| Giá trị vào | Giá trị ra kỳ vọng | Mục đích |
|---:|---:|---|
| 0 | 0 | Giá trị biên nhỏ nhất hợp lệ |
| 1 | 1 | Bảo toàn đơn vị cent |
| 1250 | 1250 | Không nhân/chia 100 |
| 2147483647 | 2147483647 | Giới hạn lớn nhất của signed `INTEGER` |
| -1 | Bị từ chối | `CHECK (amount_cents >= 0)` theo nghiệp vụ ví dụ |
| NULL ở cột cũ | Bị từ chối | `amount_cents NOT NULL` |
| 2147483648 vào cột cũ | Bị từ chối | Ngoài phạm vi `INTEGER` trước contract |

Nếu yêu cầu thực tế cho phép hoàn tiền hoặc số âm, không áp đặt bảng này: phải đổi quy tắc nghiệp vụ và test, **không sửa lén dữ liệu để vượt test**.

### 6.3. Kiểm thử trigger trong transaction có rollback

Trên DB test có dữ liệu thử và trong transaction riêng:

~~~sql
BEGIN;

INSERT INTO orders (
    tenant_id, order_id, amount_cents, currency_code, updated_at
)
VALUES (
    'T01', 'test-order-1', 1250, 'USD', CURRENT_TIMESTAMP
);

SELECT amount_cents, amount_minor
FROM orders
WHERE tenant_id = 'T01' AND order_id = 'test-order-1';

UPDATE orders
SET amount_cents = 1450,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = 'T01' AND order_id = 'test-order-1';

SELECT amount_cents, amount_minor
FROM orders
WHERE tenant_id = 'T01' AND order_id = 'test-order-1';

ROLLBACK;
~~~

Kỳ vọng:

- Sau INSERT: cũ = 1250, mới = 1250.
- Sau UPDATE: cũ = 1450, mới = 1450.
- Sau ROLLBACK: bản ghi test **không tồn tại**, nếu trước đó chưa có.

**Không dùng ca test với ID có thể trùng dữ liệu thật trên production.** Trong môi trường test phải biết trạng thái đầu, kiểm tra số dòng affected, và dùng database/schema cô lập để tránh can thiệp dữ liệu người dùng.

### 6.4. Test consistency guard

Nếu một writer cố cập nhật **chỉ** `amount_minor` thành giá trị khác `amount_cents`, trigger ở trên không được kích hoạt bởi update riêng cột mới; **CHECK** phải từ chối transaction không nhất quán.

~~~sql
-- Ví dụ cố ý gây lỗi, chỉ chạy trên test DB:
UPDATE orders
SET amount_minor = amount_cents::BIGINT + 1
WHERE tenant_id = 'T01' AND order_id = 'test-order-2';
~~~

Lệnh chỉ thử được khi `test-order-2` tồn tại; nếu không có dòng, `UPDATE 0` **không phải** bằng chứng guard hoạt động. Test tự động phải xác minh **đã nhắm đúng một dòng**, và một update cố tình sai dẫn tới **constraint violation**.

### 6.5. Test backfill tiếp tục sau lỗi

Tạo bộ dữ liệu có:

- 3 dòng cũ chưa chuyển, `amount_minor IS NULL`.
- 2 dòng đã chuyển đúng.
- Ít nhất một dòng đang bị transaction khác giữ lock.

Chạy batch theo kịch bản:

1. Worker A xử lý một lô rồi commit.
2. Worker B dừng/rollback giữa một lô.
3. Chạy lại cùng câu batch đến khi không còn dòng NULL.
4. Xác minh mọi dòng vẫn có một khóa nghiệp vụ duy nhất, không bị mất cập nhật.
5. Kiểm tra dòng đang khóa được chọn khi lock được giải phóng.

**Điều kiện `WHERE amount_minor IS NULL` chỉ giúp tránh ghi lại những dòng đã chuyển; nó không tự phát hiện cột mới đã có giá trị nhưng sai.** Cần test đối soát riêng.

## 7. Đối soát cấp khóa, cấp dòng, tổng hợp và lịch sử

Đối soát có nhiều tầng. Một kế hoạch tốt không dùng một câu `SELECT COUNT(*)` làm bằng chứng duy nhất.

### 7.1. Đếm dữ liệu chưa chuyển

~~~sql
SELECT COUNT(*) AS missing_new_values
FROM orders
WHERE amount_minor IS NULL;
~~~

Kỳ vọng **0** trước khi mọi reader phụ thuộc cột mới. Nhưng một dòng có `amount_minor = 500` trong khi `amount_cents = 600` vẫn không bị phát hiện.

### 7.2. Đối soát từng dòng với `IS DISTINCT FROM`

~~~sql
SELECT
    tenant_id, order_id,
    amount_cents, amount_minor
FROM orders
WHERE amount_minor IS DISTINCT FROM amount_cents::BIGINT
ORDER BY tenant_id, order_id
LIMIT 100;
~~~

`IS DISTINCT FROM` ở PostgreSQL so sánh cả trường hợp NULL theo cách xác định; khác với `<>`, vốn cho kết quả UNKNOWN khi một bên NULL.

Nếu truy vấn không trả dòng, hai cột **bằng nhau theo mapping đã định** trong snapshot quan sát. Tuy nhiên, vì chúng nằm trong **cùng một hàng** và có thể cùng được ghi sai, kết quả đó **chưa chứng minh** nguồn nghiệp vụ ban đầu đúng. Phải đối chiếu thêm với nguồn độc lập hoặc tập dữ liệu đã được ký nhận.

### 7.3. Đối soát tổng theo phạm vi

~~~sql
SELECT
    tenant_id,
    currency_code,
    COUNT(*) AS orders_count,
    SUM(amount_cents::BIGINT) AS legacy_total,
    SUM(amount_minor) AS new_total
FROM orders
GROUP BY tenant_id, currency_code
ORDER BY tenant_id, currency_code;
~~~

Tổng cần đối soát **trong cùng đơn vị tiền và cùng grain**, không được cộng USD với VND nếu không có quy tắc chuyển đổi. Trong ví dụ chỉ có USD, vẫn giữ `currency_code` để thể hiện ràng buộc ngữ nghĩa.

**Tổng khớp không chứng minh mọi hàng đúng.** Ví dụ:

~~~text
Nguồn:     O1 = 100, O2 = 200  => tổng 300
Kết quả:   O1 = 150, O2 = 150  => tổng 300
~~~

Tổng 300 vẫn khớp nhưng **hai dòng đều sai**. Vì vậy cần both **row-level diff** và aggregate reconciliation.

### 7.4. Đối soát với snapshot nguồn độc lập

Nếu có `source_orders_snapshot` là **bản chụp nguồn được phê duyệt** ở cùng thời điểm chốt, chứa `tenant_id`, `order_id`, `amount_cents`, có thể dùng:

~~~sql
WITH source AS (
    SELECT tenant_id, order_id,
           amount_cents::BIGINT AS expected_minor
    FROM source_orders_snapshot
),
target AS (
    SELECT tenant_id, order_id,
           amount_minor AS actual_minor
    FROM orders
)
SELECT
    s.tenant_id AS source_tenant,
    s.order_id AS source_order,
    t.tenant_id AS target_tenant,
    t.order_id AS target_order,
    s.expected_minor,
    t.actual_minor
FROM source AS s
FULL OUTER JOIN target AS t
  ON t.tenant_id = s.tenant_id
 AND t.order_id = s.order_id
WHERE s.order_id IS NULL
   OR t.order_id IS NULL
   OR s.expected_minor IS DISTINCT FROM t.actual_minor;
~~~

`source_orders_snapshot` là **bảng minh họa bổ sung**, không thuộc DDL `orders` phía trên. Hai tập dữ liệu **phải được chốt cùng một thời điểm logic** (snapshot hoặc CDC watermark tương ứng); nếu bên nguồn tiếp tục thay đổi trong lúc bên đích được quét, sẽ có những khác biệt **do thời điểm đo**, không nhất thiết do migration sai.

Truy vấn trên chỉ đáng tin nếu **cả hai phía đã được kiểm tra duy nhất theo `(tenant_id,order_id)`**. Nếu source có duplicate, FULL JOIN có thể làm nhân kết quả. Cần kiểm tra uniqueness riêng.

### 7.5. Đối soát tập khóa, không chỉ số lượng

~~~sql
-- Có ở nguồn nhưng thiếu ở đích:
SELECT tenant_id, order_id
FROM source_orders_snapshot
EXCEPT
SELECT tenant_id, order_id
FROM orders;

-- Có ở đích nhưng không có trong snapshot nguồn:
SELECT tenant_id, order_id
FROM orders
EXCEPT
SELECT tenant_id, order_id
FROM source_orders_snapshot;
~~~

Hai phép `EXCEPT` ở đây kiểm tra **tập khóa**; `EXCEPT` thông thường loại các bản ghi trùng, nên vẫn phải kiểm tra **duplicate** riêng. Nếu nguồn và đích khác phạm vi (chỉ active orders ở nguồn, tất cả lịch sử ở đích), cần lọc đúng hợp đồng trước khi dùng.

### 7.6. Đối soát dữ liệu lịch sử và thời điểm hiệu lực

Khi migration liên quan SCD Type 2, snapshot hoặc event time, không thể chỉ so số dòng và tiền:

| Mô hình | Bất biến cần kiểm tra |
|---|---|
| **SCD Type 2** | Không có hai khoảng hiệu lực chồng lấn cho cùng business key; as-of join trả đúng một phiên bản |
| **Periodic snapshot** | Đầy đủ kho × sản phẩm × ngày chốt; không cộng số tồn qua ngày để gọi là tồn cuối kỳ |
| **Fact giao dịch** | Không duplicate event/business key; amount/timestamp tại sự kiện vẫn đúng |
| **Tỷ lệ phân tích** | Tử số và mẫu số cùng tập quan sát; không cộng các rate |
| **Event stream** | Event ID ổn định khi retry; replay không tạo side effect trùng |
| **Đổi timezone báo cáo** | Cùng mốc UTC có thể thuộc ngày địa phương khác; xác nhận chính sách restatement |

Nếu chuyển một fact cấp đơn thành fact cấp dòng, `COUNT(*)` **không cần bằng nhau**; phải kiểm tra `SUM(line_amount)` với **thành phần giá trị cấp đơn tương ứng**, phân loại phí/thuế/discount và kiểm tra từng `order_id`.

### 7.7. Nhiều lớp kiểm tra, nhiều cấp độ tin cậy

~~~text
Schema tồn tại đúng kiểu
    ↓
Khóa/FK/grain hợp lệ
    ↓
Đủ dòng và đủ tập khóa
    ↓
Mapping cấp dòng đúng
    ↓
Measure/KPI theo ngày, tenant, currency khớp
    ↓
Consumer trả đúng kết quả
    ↓
Đối soát tiếp sau dữ liệu trễ và thay đổi đồng thời
~~~

Mỗi tầng phát hiện một lớp lỗi khác nhau. Không bỏ qua kiểm tra cấp dòng chỉ vì dashboard tổng theo tháng nhìn “có vẻ đúng”.

## 8. Test các đường ghi cạnh tranh và tính nhất quán

### 8.1. Race condition khi backfill và writer cùng sửa

Một tình huống nguy hiểm:

~~~text
T1: Backfill đọc amount_cents = 1000
T2: Ứng dụng sửa amount_cents = 1200
T3: Backfill ghi amount_minor = 1000 từ cache cũ
~~~

Kết quả: cột mới sai. Câu batch ở phần trước đọc giá trị dưới **row lock trong cùng UPDATE**, giảm rủi ro dùng snapshot ứng dụng lỗi thời; trigger giúp mọi sửa `amount_cents` cập nhật cột mới trong transaction tương ứng.

Tuy nhiên, **mức cô lập giao dịch và điều kiện WHERE vẫn cần kiểm thử**. Nếu ứng dụng đọc–sửa–ghi không có optimistic concurrency, hai yêu cầu nghiệp vụ đồng thời có thể ghi đè nhau **ngay cả khi hai cột vẫn bằng nhau**.

### 8.2. Ca kiểm thử đồng thời

| Kịch bản | Thiết lập | Kỳ vọng |
|---|---|---|
| Writer A0 ghi khi chưa backfill | Cột mới NULL | Trigger cập nhật cột mới cùng giá trị |
| Writer A0 sửa dòng đã backfill | Hai cột ban đầu bằng nhau | Hai cột tiếp tục bằng nhau |
| Backfill gặp dòng đang khóa | Transaction khác đang UPDATE | `SKIP LOCKED` bỏ qua tạm, xử lý sau |
| Worker backfill chết giữa transaction | Batch chưa COMMIT | Không có cập nhật nửa chừng trong batch |
| Hai backfill worker chạy đồng thời | Cùng vùng ID | Không double-apply hoặc tạo duplicate |
| Writer chỉ cập nhật cột mới | Cột cũ chưa đổi | Guard từ chối mismatch |
| Hai request nghiệp vụ cùng sửa đơn | Có version hoặc lock | Không mất cập nhật ngoài quy tắc nghiệp vụ |
| Writer cố ghi giá trị vượt INT | App cũ còn hoạt động | Bị từ chối tới khi contract hợp lệ |

### 8.3. Tại sao dual-write qua hai hệ nguy hiểm hơn?

Nếu cấu trúc mới nằm ở **database khác**:

~~~text
Write old_db → success
Write new_db → timeout
~~~

Không thể mặc nhiên rollback được cả hai chỉ bằng transaction local. Cần thiết kế:

- **Transactional outbox** ở DB chủ sở hữu, hoặc CDC từ nguồn commit đáng tin cậy.
- ID sự kiện/phiên bản ổn định để consumer **idempotent**.
- Quy tắc thứ tự cập nhật của cùng thực thể và late event.
- Backfill **snapshot + stream từ offset/watermark có chứng cứ**, không bỏ mất thay đổi giữa hai bước.
- Reconciliation và cơ chế sửa sai có quyền sở hữu rõ ràng.

Trong hệ phân tán, điều kiện “hai DB bằng nhau tức thời” có thể **không phải bất biến hợp lệ** nếu kiến trúc cho phép eventual consistency. Phải tài liệu hóa **độ trễ được phép, mốc so sánh và cách xác định lỗi thực sự**.

## 9. Kiểm thử ứng dụng và hợp đồng khi chuyển schema

### 9.1. Shadow read

Trong S1, ứng dụng vẫn trả kết quả từ cột cũ nhưng **đọc thêm cột mới để so**:

~~~sql
SELECT
    tenant_id, order_id,
    amount_cents::BIGINT AS legacy_value,
    amount_minor AS candidate_value
FROM orders
WHERE tenant_id = :tenant_id AND order_id = :order_id;
~~~

Không chọn `COALESCE(amount_minor, amount_cents)` làm bằng chứng correctness. Nếu `amount_minor` **không NULL nhưng cũ**, nó sẽ ưu tiên sai. Phải so hai giá trị trực tiếp.

Shadow read có thể tăng tải đọc và log: chỉ lấy mẫu có giới hạn, ghi metric mismatch **không chứa dữ liệu nhạy cảm không cần thiết**, và quan sát độ trễ.

### 9.2. Canary

Chuyển dần nhóm người dùng/tenant/instance sang đọc trường mới, rồi so:

- Giá trị hiển thị và tổng KPI.
- Latency p95/p99, tỷ lệ lỗi query, timeout, deadlock.
- Số mismatch, số row chưa backfill.
- Hành vi Java serializer, ORM, cache và API với giá trị biên.

Không có tỷ lệ canary nào phù hợp mọi hệ. Phải chọn cửa sổ có workload đại diện (cả job theo lịch) và có **kill switch** đã thử.

### 9.3. Contract API và event không tự đổi theo tên cột DB

Nếu API đang trả:

~~~json
{ "orderId": "O42", "amountCents": 1250, "currency": "USD" }
~~~

DB đổi thành `amount_minor BIGINT` **không yêu cầu** tự động đổi field `amountCents` của API. Có thể giữ DTO v1 bằng phép chiếu khi ý nghĩa còn tương thích. Khi cần số lớn hơn 32-bit, phải kiểm tra **khả năng biểu diễn của JSON client, Java DTO, event schema và downstream warehouse**; có thể cần version v2 hoặc kiểu string decimal/integer với hợp đồng rõ.

Test tương thích ít nhất:

1. Client cũ đọc được response của API đang chạy.
2. Producer mới không phát event làm consumer cũ parse sai.
3. Event v1 đã lưu vẫn **replay được** sau khi consumer nâng cấp.
4. Không đổi đơn vị tiền/thời gian chỉ vì field name đổi.
5. Schema registry, CDC connector và data contract có kế hoạch chuyển pha riêng.

**Điều kiện schema đồng bộ ở DB không chứng minh hợp đồng mạng tương thích.**

## 10. Chuyển sang cấu trúc mới mà không tạo “khoảng trống” tương thích

Ở ví dụ, cột legacy `amount_cents` ban đầu `NOT NULL`. Vì vậy, khi S1 còn nguyên, ứng dụng chỉ ghi `amount_minor` **không thể INSERT hợp lệ**: cột cũ vẫn bắt buộc có giá trị. Một cutover an toàn cần phân biệt **reader mới**, **writer chuyển tiếp** và **writer chỉ dùng cột mới**.

### 10.1. Đặt điều kiện đạt trước khi đọc mới

~~~sql
-- Kiểm tra dữ liệu chưa chuyển:
SELECT COUNT(*) AS still_null
FROM orders
WHERE amount_minor IS NULL;

-- Kiểm tra sai khác:
SELECT COUNT(*) AS mismatched
FROM orders
WHERE amount_minor IS DISTINCT FROM amount_cents::BIGINT;

-- Xác nhận constraint so khớp lịch sử sau backfill:
ALTER TABLE orders
    VALIDATE CONSTRAINT orders_amount_mapping_consistent;
~~~

Hai số đếm phải về **0**, và việc `VALIDATE` phải đạt trên một trạng thái dữ liệu ổn định theo cơ chế ghi đã thiết kế. Trước khi chuyển reader toàn hệ, kiểm tra shadow read, canary, source reconciliation và tác động tải.

### 10.2. Tăng ràng buộc cột mới

Khi đã backfill và mọi writer tương thích, có thể tăng dần:

~~~sql
ALTER TABLE orders
    ADD CONSTRAINT orders_amount_minor_present
    CHECK (amount_minor IS NOT NULL) NOT VALID;

ALTER TABLE orders
    VALIDATE CONSTRAINT orders_amount_minor_present;

ALTER TABLE orders
    ALTER COLUMN amount_minor SET NOT NULL;
~~~

PostgreSQL có thể dùng một `CHECK` đã được xác nhận để giảm công quét dữ liệu khi `SET NOT NULL` tùy phiên bản/điều kiện; **không khẳng định các thao tác trên không cần lock**. Phải thử trong môi trường gần tải thực.

### 10.3. Pha trung gian S1b: cho writer mới chạy song song

Khi **đã chứng minh không còn bất kỳ reader/writer cũ nào yêu cầu `amount_cents`**, có thể đi qua một pha trung gian:

~~~text
S1:
    Cột cũ NOT NULL, cột mới đã đủ dữ liệu
    Writer chuyển tiếp ghi cột cũ/hoặc cả hai
    Reader mới đã đọc cột mới

S1b:
    Cột mới NOT NULL
    Cột cũ được phép NULL và không còn ràng buộc bằng cột mới
    Writer chuyển tiếp ghi cả hai vẫn chạy được
    Writer mới chỉ ghi cột mới cũng chạy được
    TUYỆT ĐỐI không còn consumer cần cột cũ đúng

S2:
    Bỏ hẳn cột cũ, chỉ giữ cột mới
~~~

Ví dụ DDL cho bước **S1 → S1b**, chỉ khi gate legacy-consumer đã đạt:

~~~sql
BEGIN;

DROP TRIGGER IF EXISTS trg_orders_amount_legacy ON orders;
DROP FUNCTION IF EXISTS sync_order_amount_from_legacy();

ALTER TABLE orders
    DROP CONSTRAINT orders_amount_mapping_consistent;

ALTER TABLE orders
    ALTER COLUMN amount_cents DROP NOT NULL;

COMMIT;
~~~

Ở S1b, ứng dụng mới có thể `INSERT` chỉ với `amount_minor`; ứng dụng chuyển tiếp vẫn có thể ghi **cả hai**. Nhưng `amount_cents` **có thể NULL hoặc trở nên cũ** từ thời điểm này: **không thể rollback về reader A0 chỉ bằng đổi feature flag**. Nếu cần rollback A0 sau S1b, phải có kế hoạch xây lại cột cũ từ cột mới, kiểm tra phạm vi `INTEGER`, khôi phục bridge và đánh giá giao dịch phát sinh — một hoạt động riêng với rủi ro rõ ràng.

Khi toàn bộ writer/reader chỉ còn dùng cột mới và các phụ thuộc cũ đã được loại bỏ, thực hiện contract:

~~~sql
ALTER TABLE orders
    DROP COLUMN amount_cents;
~~~

**Điểm cốt lõi:** *rollout có thể cuốn chiếu* chỉ khi có một **trạng thái trung gian mà cả bản ứng dụng trước và sau cùng chạy được**. Không tự kỳ vọng có thể vừa drop cột cũ vừa rolling deploy bản chỉ dùng cột mới mà không có chiến lược tương thích.

### 10.4. Kiểm thử gate S1b và S2

| Thử nghiệm | Kỳ vọng ở S1b | Kỳ vọng ở S2 |
|---|---|---|
| A1 ghi cả hai cột | Thành công nếu giá trị mới hợp lệ | **Không thành công** nếu SQL còn tham chiếu cột cũ |
| A2 ghi cột mới | Thành công | Thành công |
| A2 đọc cột mới | Thành công | Thành công |
| A0 chỉ ghi cột cũ | **Không được phép tồn tại**; nếu thử có thể vi phạm `NOT NULL` mới | Không tương thích |
| A0 đọc cột cũ | Giá trị có thể cũ/NULL, **không đáng tin** | Không tương thích |
| Bản ghi mới vượt miền INT | Có thể lưu khi chính sách cho phép và consumer đã nâng cấp | Có thể lưu |
| Restore từ bản S0 | Cần migration lại và reconcile dữ liệu phát sinh | Cần kế hoạch phục hồi đã diễn tập |

**Nghiệm thu S1b không dựa trên “có cột cũ là rollback được”.** Phải ghi rõ khi nào cột cũ không còn được duy trì và mất quyền là nguồn đọc tin cậy.

## 11. Khả năng khôi phục gồm những tầng nào?

**Recoverability** là khả năng đưa hệ thống và dữ liệu về trạng thái đáp ứng những bất biến đã thỏa thuận sau lỗi. Nó không chỉ là “có một file backup”.

| Cấp phục hồi | Ví dụ | Điều kiện |
|---|---|---|
| **Retry một batch** | Worker chết trước commit | Batch idempotent, transaction ngắn, checkpoint |
| **Rollback giao dịch** | SQL cập nhật sai nhưng chưa commit | DB rollback được toàn bộ thay đổi thuộc transaction |
| **Rollback đường đọc/feature flag** | Reader mới hiển thị sai | Cột cũ còn đồng bộ đúng, fallback đã thử |
| **Roll-forward ứng dụng/schema** | Cấu trúc cũ đã xóa hoặc dữ liệu mới không tương thích cũ | Có bản sửa mới và lộ trình deploy hợp lệ |
| **Dựng lại projection** | Read model/data mart lỗi | Nguồn lịch sử, watermark, mapping và replay |
| **Khôi phục từ backup** | Mất dữ liệu hoặc DB bị hỏng | Backup có thể đọc, restore được, kiểm tra toàn vẹn |
| **Point-in-time recovery (PITR)** | Cần trở về mốc trước thay đổi phá hoại | Base backup + WAL/log cần thiết và cơ chế phục hồi tương thích |
| **Chuyển vùng/khôi phục dịch vụ** | Node/zone lỗi | Failover, DNS/connection, SLO và dữ liệu nhất quán |

Các lựa chọn **không tương đương**:

- `ROLLBACK` chỉ tác động transaction chưa commit; không hoàn nguyên hàng nghìn commit đã hoàn tất.
- **Rollback binary** không giúp app cũ chạy nếu schema/format đã bị loại bỏ.
- **Replica** không tự thay thế backup: xóa nhầm hoặc ghi sai có thể được nhân bản sang replica.
- **Backup** không tự bảo đảm phục hồi được đến mốc cần thiết, đặc biệt nếu chưa diễn tập và thiếu log.
- **Event replay** không tự tạo lại một trường đã không được lưu trong sự kiện gốc.

### 11.1. RPO và RTO

- **RPO — Recovery Point Objective:** mức **mất dữ liệu tối đa có thể chấp nhận** tính theo thời gian, khi khôi phục đến trạng thái trước sự cố.
- **RTO — Recovery Time Objective:** **thời gian tối đa cho phép để khôi phục dịch vụ** đến trạng thái vận hành chấp nhận được.

Ví dụ mục tiêu minh họa:

~~~text
RPO mục tiêu: không quá 5 phút dữ liệu được chấp nhận mất
RTO mục tiêu: không quá 60 phút gián đoạn dịch vụ
~~~

Nếu sự cố xảy ra lúc 10:00 và bản phục hồi chỉ tới 09:58, khoảng mất dữ liệu **hai phút** có thể nằm trong RPO 5 phút — **chỉ khi mốc/commit đã được xác nhận chính xác**. Nhưng nếu hệ mất 90 phút mới phục vụ được giao dịch, RTO 60 phút **không đạt**.

RPO/RTO phải được **chủ sở hữu nghiệp vụ phê duyệt**; không tự chọn từ thời gian một lệnh `pg_restore` chạy xong. RTO còn bao gồm kiểm tra tính đúng, mở lại ghi, kết nối ứng dụng, cache và các thành phần phụ thuộc.

### 11.2. Backup nào giải quyết trường hợp nào?

| Cơ chế | Phù hợp cho | Giới hạn cần nhớ |
|---|---|---|
| **Logical dump** | Xuất schema/dữ liệu; khôi phục dataset ở mốc dump | Không tự mang đầy đủ WAL để khôi phục tới thời điểm bất kỳ |
| **Physical/base backup** | Khôi phục trạng thái cluster/storage hợp lệ | Cần đúng phiên bản, cấu hình và log nếu muốn PITR |
| **WAL archive / transaction log** | Phục hồi tới mốc trong vùng log được giữ | Phải đủ chuỗi log, tương thích timeline và cấu hình |
| **Managed snapshot** | Phục hồi theo điểm snapshot được hỗ trợ | Tính nhất quán và RPO phụ thuộc dịch vụ/cấu hình |
| **Replica** | Giảm downtime/failover | Ghi/xóa sai có thể lan sang replica; không thay thế backup độc lập |
| **Event log có thể replay** | Dựng lại projection từ event | Phụ thuộc retention, schema lịch sử, ordering, idempotency |

Một hệ có thể kết hợp nhiều cơ chế. **Khả năng khôi phục phải được đo bằng thử nghiệm trên bản sao độc lập**, không suy ra từ việc lịch backup có màu xanh.

## 12. Diễn tập restore và PITR an toàn

### 12.1. Chọn môi trường diễn tập

**Không thực hiện fault injection hoặc PITR trực tiếp lên DB production** chỉ để kiểm thử bài học. Chuẩn bị môi trường khôi phục tách biệt:

- Dùng backup/snapshot được tạo theo quy trình chính thức.
- Cô lập network và secrets; không cho ứng dụng test gửi email/thanh toán thật.
- Ẩn danh hoặc giới hạn truy cập dữ liệu nhạy cảm theo chính sách.
- Có cùng các yêu cầu thiết yếu về phiên bản PostgreSQL, extensions, locale/collation, cấu hình và quyền.
- Không kết nối nhầm tới broker hoặc source production khi replay.

### 12.2. Các bước diễn tập

~~~text
1. Chọn backup và một mốc khôi phục mục tiêu.
2. Xác minh backup và chuỗi WAL/log có sẵn, checksum/tính toàn vẹn.
3. Dựng môi trường DB/cluster khôi phục hoàn toàn tách biệt.
4. Restore base backup; nếu cần PITR, áp dụng WAL/log tới mốc.
5. Khởi động DB ở chế độ kiểm soát, xác nhận server sẵn sàng.
6. Kiểm tra schema/version, extensions, quyền và khóa quan trọng.
7. Đếm khóa, so số dư/giá trị và chạy các invariant nghiệp vụ.
8. Triển khai ứng dụng tương thích với schema đã phục hồi.
9. Kiểm thử đọc/ghi mô phỏng và các consumer phụ thuộc.
10. Đo thời gian toàn bộ, điểm dữ liệu được phục hồi,
    sai khác và hành động khắc phục.
~~~

Một lệnh restore trả thành công nhưng **thiếu extension, role, cấu hình quyền hoặc dữ liệu sau mốc** chưa chứng minh khôi phục đạt. Phải chứng minh dữ liệu tại mốc và **dịch vụ** sau restore có thể hoạt động theo hợp đồng.

### 12.3. PITR và lỗi migration đã commit

Giả sử `DROP COLUMN` đã commit lúc 10:05, đến 10:15 mới phát hiện một job cũ không tương thích. Các lựa chọn:

- **Roll-forward:** sửa job để dùng schema mới. Phù hợp nếu dữ liệu và hệ mới vẫn đúng.
- **Phục hồi vào một môi trường khác** tới mốc trước `DROP COLUMN`, trích/đối soát dữ liệu cần thiết và lên kế hoạch chuyển lại.
- **Khôi phục toàn hệ tới mốc cũ** chỉ khi chấp nhận/giải quyết được giao dịch hợp lệ phát sinh sau mốc, cùng các hệ tích hợp liên quan.

PITR quay database về trạng thái quá khứ có thể khiến **mất những giao dịch hợp lệ sau thời điểm phục hồi** hoặc tạo bất nhất với broker và dịch vụ khác. Vì vậy phải có quy trình reapply/reconcile những thay đổi ấy theo owner.

**Không coi PITR là “nút undo an toàn”** cho mọi migration. Khi đã có giao dịch mới, phục hồi một DB riêng lẻ về quá khứ có thể làm sai toàn hệ nếu không phối hợp.

### 12.4. Vì sao backup thành công vẫn có thể không restore được?

Một số lỗi thường gặp:

- File backup thiếu, bị hỏng hoặc không giải mã được vì **mất khóa mã hóa**.
- Snapshot không nhất quán hoặc thiếu phần WAL cần để recovery.
- Không đủ dung lượng, băng thông hoặc quyền khởi động môi trường mới.
- Phiên bản/extension khác, migration chưa tương thích với bản DB được khôi phục.
- Tài khoản ứng dụng và secret không sẵn sàng/không thể phục hồi.
- Schema phục hồi không khớp binary được deploy hiện hành.
- RTO bị vượt vì phải tải một dataset lớn quá lâu hoặc phải xây lại index.
- Backup có dữ liệu chính nhưng thiếu object storage, file đính kèm hoặc hệ thống tham chiếu cần cho nghiệp vụ.

Vì thế kế hoạch kiểm chứng phải bao phủ **khôi phục cả chuỗi phụ thuộc liên quan**, không chỉ bảng chính.

## 13. Thử lỗi có chủ đích và khả năng tiếp tục

Các bài thử lỗi sau phải thực hiện trong **môi trường được phép và cô lập**, sử dụng fixture hoặc dữ liệu đã bảo vệ.

| Lỗi được tiêm | Điều cần chứng minh | Dấu hiệu không đạt |
|---|---|---|
| Worker backfill chết **trước commit** | Transaction rollback, chạy lại không mất dòng | Một số dòng cập nhật nửa chừng |
| Worker chết **sau commit, trước checkpoint** | Replay lô vẫn idempotent | Giá trị bị cộng thêm hoặc tạo duplicate |
| Hai worker chọn vùng dữ liệu giao nhau | Lock/selector không làm hai bản ghi cùng grain | Duplicate hoặc mất cập nhật |
| App A0 ghi sau khi backfill một dòng | Bridge giữ cột mới đúng | Cột mới stale nhưng không NULL |
| Mất kết nối DB giữa hai bước nghiệp vụ | Transaction nguyên tử hoặc có quy tắc bù | Đơn ở trạng thái nửa chuyển |
| Replica chậm | Reader không chuyển nếu không đạt freshness gate | Kết quả khác nguồn mà không cảnh báo |
| CDC consumer ngừng lâu | Có lag/backlog và resume từ offset | Mất sự kiện hoặc xử lý lại sai |
| Event delivery trùng | Inbox/idempotency không tạo side effect trùng | Đếm đơn/thu tiền lặp |
| Event đến sai thứ tự | Phiên bản cũ không ghi đè mới | Read model quay về trạng thái quá khứ |
| Có bản ghi không map được FK | Quarantine/ngoại lệ có kiểm soát | Gán ID mặc định tùy tiện |
| Thao tác `DROP COLUMN` bị từ chối vì dependency | Không dùng `CASCADE` bừa bãi | View/truy vấn quan trọng bị xóa |
| Restore từ backup + log | Có thể tái dựng schema/dữ liệu tại mốc | Restore thiếu log, vượt RPO/RTO |

### 13.1. Không tự tuyên bố exactly-once

Một luồng dùng transactional outbox thường có thể phát **ít nhất một lần**. Nếu publisher gửi event thành công rồi chết trước khi đánh dấu đã gửi, nó có thể phát lại. Consumer cần:

~~~text
eventId: ổn định cho một sự kiện logic
consumer inbox: đánh dấu sự kiện đã xử lý
business key: chặn hai tác dụng phụ giống nhau khi nghiệp vụ không cho phép
transaction: cập nhật inbox và read model cùng commit nếu có thể
retry: kiểm soát độc lập cho API bên ngoài
~~~

Đối soát số event đã nhận không đủ: phải so **số sự kiện logic** và **tác dụng phụ nghiệp vụ** sau replay.

### 13.2. Thử restart và tiếp tục từ checkpoint

Với backfill/CDC:

1. Chạy đến một checkpoint xác định.
2. Dừng worker đột ngột trong môi trường test.
3. Khởi động lại từ checkpoint hoặc chọn lại dòng chưa chuyển.
4. Kiểm tra không bỏ lọt cập nhật khi resume.
5. Đối soát với snapshot nguồn và watermark phù hợp.

Không dùng mỗi `MAX(order_id)` làm checkpoint nếu nguồn còn cho phép **thêm/sửa dòng ID thấp hơn** mà không có sync/CDC bảo vệ. Một con trỏ chỉ chứng minh worker đã đi qua một khoảng, **không** chứng minh tất cả thay đổi đến sau đã được xử lý.

## 14. Kiểm thử hiệu năng, lock và tác động lên vận hành

Một migration có kết quả dữ liệu đúng nhưng giữ lock quá lâu khiến hệ không nhận đơn trong giờ cao điểm **vẫn là migration không đạt**.

### 14.1. Đo trước và sau trên workload đại diện

| Nhóm đo | Baseline | Khi expand/backfill/cutover | Điều kiện đánh giá |
|---|---|---|---|
| **Độ trễ giao dịch** | p50/p95/p99 của ghi đơn | So với baseline cùng loại tải | Không vượt SLO/phạm vi tăng được phê duyệt |
| **Tỷ lệ lỗi** | Query timeout, deadlock, 5xx | Theo tenant/endpoint/writer | Không có tăng bất thường kéo dài |
| **Lock** | Lock wait, lock timeout | Theo thời điểm DDL và batch | Không chặn giao dịch quan trọng quá ngưỡng |
| **WAL / I/O** | Tốc độ ghi log, disk | Trong backfill | Không vượt công suất/làm thiếu dung lượng |
| **Replication lag** | Độ trễ bản sao | Khi tạo index và ghi batch | Không làm reader mất điều kiện freshness |
| **Bloat / vacuum** | Dung lượng, dead tuples | Sau nhiều UPDATE | Có kế hoạch bảo trì phù hợp |
| **Thời gian mỗi batch** | Mốc trước thử nghiệm | Median/p95 và retry | Job có thể tiến triển trong khung được duyệt |
| **Tiến độ** | Tổng dòng cần chuyển | Dòng còn lại, lỗi theo lô | Không kẹt ở một nhóm dữ liệu |
| **Khả năng đọc/ghi sau cutover** | Mốc từ bản cũ | Số mismatch, throughput | Không suy giảm tính đúng/khả dụng |

Thử trên môi trường có **khối lượng, phân bố khóa, tỷ lệ ghi và chỉ mục tương đồng**, không chỉ chạy một script trong DB rỗng.

### 14.2. DDL có thể cần lock dù cú pháp trông nhỏ

Trong PostgreSQL, `ALTER TABLE` có thể cần những loại lock khác nhau, và thời gian chờ lock có thể dài hơn thời gian thao tác metadata. Cần:

- Đánh giá phiên bản PostgreSQL và câu DDL thực tế.
- Đặt **`lock_timeout`** được duyệt để không chờ mãi rồi làm nghẽn truy vấn khác.
- Theo dõi transaction dài, connection pool và thao tác DDL cạnh tranh.
- Chạy thử DDL trên dữ liệu có cấu trúc và quy mô gần thực.
- Có kế hoạch dừng/thử lại sau timeout; không lặp retry vô hạn với cùng tải.

Ví dụ ý tưởng trong phiên migration:

~~~sql
SET lock_timeout = '3s';

-- Chỉ thực hiện câu DDL sau khi đánh giá lock và thử nghiệm.
-- ALTER TABLE ...;
~~~

`3s` là ngưỡng **minh họa**, không phải khuyến nghị chung. Cũng cần cân nhắc `statement_timeout`, transaction timeout, việc retry theo batch và tác động lên hệ giám sát.

### 14.3. Index và constraint có giai đoạn kiểm chứng riêng

Trong PostgreSQL, một cách giảm tác động khi tạo index lớn là:

~~~sql
-- Cần chạy ngoài transaction block thông thường:
CREATE INDEX CONCURRENTLY idx_orders_tenant_updated
    ON orders (tenant_id, updated_at);
~~~

Nhưng `CONCURRENTLY` vẫn tiêu thụ CPU, I/O, có thể kéo dài và có thể thất bại, để lại index cần kiểm tra trước khi retry. **Không** viết migration framework mặc định bọc câu này trong một transaction rồi coi đó là thành công.

Với `CHECK` hoặc FK có hỗ trợ kiểu `NOT VALID`/validate:

1. Thêm cơ chế chặn dữ liệu mới không hợp lệ.
2. Làm sạch/backfill dữ liệu lịch sử.
3. **VALIDATE** và ghi nhận kết quả.
4. Sau đó mới dùng bất biến ấy làm gate cho reader/writer mới.

Sự tồn tại của một constraint được khai báo nhưng **chưa validate** không đồng nghĩa tất cả dữ liệu lịch sử đã được kiểm chứng.

## 15. Thiết kế một quyết định go / no-go có bằng chứng

Một migration cần có **người phê duyệt và điều kiện khách quan**. Không quyết định “go” vì đã sát giờ phát hành hoặc vì SQL migration vừa chạy hết.

### 15.1. Bảng điều kiện trước contract

| Gate | Minh chứng yêu cầu | Trạng thái mong đợi |
|---|---|---|
| **Nguồn/grain** | Tài liệu business key, đơn vị, phạm vi tenant | Được owner ký nhận |
| **App/schema** | Ma trận A0/A1/A2 × S0/S1/S1b/S2 | Tất cả tổ hợp đang chạy đều tương thích |
| **Đủ dữ liệu** | `missing_new_values` | 0 trước new-only reads |
| **Đúng dữ liệu** | `mismatched`, source/target diff | 0 hoặc ngoại lệ đã giải quyết theo chính sách |
| **Tính duy nhất** | Duplicate-grain test | Không có duplicate chưa giải thích |
| **FK/lịch sử** | Referential checks, as-of join | Không có vi phạm chưa giải quyết |
| **Hiệu năng** | Canary, p95/p99, lock wait, replication lag | Trong giới hạn đã phê duyệt |
| **Người tiêu thụ** | Danh sách worker, API, CDC, BI, job định kỳ | Không còn phụ thuộc cột cũ |
| **Phục hồi** | Backup, restore/PITR drill, bản diễn tập runbook | Đạt RPO/RTO, biết điểm không thể rollback |
| **An toàn dữ liệu** | Kiểm tra quyền, retention, test dataset | Không lộ dữ liệu/cấp thêm quyền ngoài yêu cầu |
| **Vận hành** | Owner, dashboard, alert, rollback/roll-forward | Sẵn sàng theo dõi sau deploy |

**Ngưỡng bằng 0** có ý nghĩa với những bất biến chặt như key trùng hoặc ánh xạ tiền sai trong bài ví dụ. Những chỉ số khác có thể có ngưỡng khác nhau do nghiệp vụ quyết định (ví dụ lag 2 phút được phép), nhưng mọi ngoại lệ phải có **người chịu trách nhiệm, phạm vi và kế hoạch xử lý**.

### 15.2. Báo cáo bằng chứng tối thiểu

Một mẫu ngắn để ghi vào release record:

~~~text
Migration ID: orders-amount-v2
Schema baseline: S0
Target: S2
Business owner: Orders
Technical owner: Database / Platform

Scope:
    orders grain = (tenant_id, order_id)
    amount_minor = amount_cents::BIGINT
    currency = USD; unit = cent

Validation:
    row-level mismatch = 0
    null new values = 0
    key duplicates = 0
    source/target reconciliation = PASS at approved watermark
    A0 on S1 = PASS
    A1 on S1 = PASS
    A2 on S1b = PASS
    A2 on S2 = PASS
    canary SLO = PASS

Recovery:
    latest restore rehearsal = PASS
    observed RPO/RTO = recorded values
    fallback available until phase S1
    after phase S1b = roll-forward / planned repair

Approval:
    business + technical + operations
~~~

Đây là **mẫu bằng chứng**, không phải báo cáo một deployment thật. Khi dùng, phải ghi số đo thực tế, phiên bản artifact, thời điểm test và đường dẫn log/dashboard có quyền truy cập phù hợp.

### 15.3. Những lý do nên dừng ngay

- Có cột mới **khác cột cũ nhưng không NULL**, nguyên nhân chưa rõ.
- Tìm thấy writer cũ vẫn đang ghi sau khi dỡ bridge.
- Đường đọc mới làm thay đổi KPI mà chưa có phê duyệt thay đổi ngữ nghĩa.
- Backfill gây replication lag hoặc lock wait vượt ngưỡng.
- Test restore thất bại, thiếu WAL cần PITR hoặc không có khả năng khởi động bản ứng dụng phù hợp.
- Test duplicate event gây thanh toán/giao hàng trùng.
- Hệ có dữ liệu nhiều tenant nhưng migration bỏ namespace khỏi khóa hoặc kiểm tra quyền.

**No-go là một kết quả kiểm chứng hợp lệ.** Chậm contract thường ít rủi ro hơn xóa sớm cấu trúc mà consumer vẫn sử dụng.

## 16. Các loại chuyển đổi cần bộ test khác nhau

### 16.1. Đổi tên cột thuần túy

Rủi ro chính là **tương thích schema/consumer**. Nếu mapping 1:1, cần thử A0/A1/A2, chính sách rename, view compatibility và các job hiếm chạy. Cần chứng minh dữ liệu giữ nguyên theo khóa và không có cấu trúc cũ bị sử dụng khi drop.

### 16.2. Đổi kiểu hoặc đơn vị tiền

Đổi `INTEGER` → `BIGINT` khác với đổi **cent → dollar**. Trường hợp sau cần công thức chuyển, quy tắc làm tròn và kiểm thử:

~~~text
125 cents -> 1.25 dollars, không phải 125 dollars
~~~

Nếu hệ dùng `NUMERIC`, cần kiểm tra precision/scale, tiền tệ khác nhau và các phép tính tổng hợp; không tự dùng `DOUBLE PRECISION` cho tiền cần độ chính xác thập phân.

### 16.3. Tách một trường thành nhiều trường

Ví dụ:

~~~text
shipping_address_text
    ↓
shipping_street, shipping_ward, shipping_city, shipping_country
~~~

Một parser không thể chắc chắn phân tách đúng mọi địa chỉ cũ. Phép thử cần:

- Tập dữ liệu thực tế đa dạng, có khoảng trắng, tiếng Việt, thiếu thành phần, dữ liệu quốc tế.
- **Tỷ lệ ánh xạ được** và **độ tin cậy** khi mapping.
- Dòng không đủ thông tin vào hàng đợi cần rà soát; không tự tạo country/ward giả.
- Quy tắc giữ địa chỉ tại thời điểm giao dịch, không vô tình đổi theo hồ sơ hiện hành.
- Tính khả nghịch: sau khi bỏ chuỗi gốc, có thể mất ghi chú giao hàng không tái dựng được.

Migration có thể thành công về số dòng nhưng **mất thông tin nghiệp vụ không thể khôi phục**.

### 16.4. Đổi từ quan hệ một-nhiều sang nhiều-nhiều

Nguồn:

~~~text
employees.department_id
~~~

Đích:

~~~text
employee_departments(employee_id, department_id, valid_from)
~~~

Test phải chứng minh:

- Mỗi quan hệ cũ được chuyển thành **đúng một quan hệ mới** theo chính sách.
- Không tạo trùng `(employee_id,department_id,valid_from)`.
- Nếu nhiều phòng ban mới được phép, ứng dụng cũ chỉ đọc một `department_id` **không còn đủ ngữ nghĩa**.
- Cần gate tính năng, hoặc định nghĩa “phòng ban chính” riêng có kiểm chứng.

Đây không chỉ là đổi schema, mà còn đổi **hợp đồng nghiệp vụ**.

### 16.5. Chuyển từ quan hệ sang document hoặc đồ thị

**Document:** một đơn có thể chứa `items[]`. Khi flatten sang fact dòng hàng, đừng chép `order_total` cấp đơn lên mọi item rồi cộng. Test grain trước/sau và số dòng nested.

**Đồ thị:** một quan hệ có thể được truy cập qua nhiều đường đi. Khi chuyển FK sang edge/node, test số **thực thể và quan hệ duy nhất**, không dùng số đường đi làm số giao dịch.

**Time series:** đổi từ bảng sự kiện sang chuỗi theo metric+labelset cần kiểm tra cardinality/churn, giờ đo và dữ liệu bị mất khi tổng hợp. Không coi timestamp nhãn là cách giữ lịch sử sự kiện.

### 16.6. Chuyển fact và dimension phân tích

Nếu fact cũ ở cấp đơn, fact mới ở cấp dòng:

- `COUNT(*)` không cần bằng nhau.
- Chuyển `order_total` phải phân rã chính xác thuế, ship, giảm giá và hoàn trả nếu cần.
- `COUNT(DISTINCT order_id)` có thể cần namespace tenant/source.
- SCD Type 2 phải khớp phiên bản dimension theo **event time**, không phải ngày nạp.
- Một `JOIN` dimension one-to-many có thể nhân bản fact và làm tổng sai.

**Bộ đối soát phải dựa trên grain và KPI**, không dựa trên phép đếm cơ học của hai cấu trúc khác nhau.

## 17. Lỗi thường gặp khi kiểm chứng và phục hồi

| Sai lầm | Vì sao không đủ | Cách đúng hơn |
|---|---|---|
| “DDL trả exit code 0 là đạt” | Chưa kiểm tra data/app/recovery | Gate theo nhiều tầng |
| “Hai bảng cùng COUNT(*) là tương đương” | Có thể hoán đổi/lệch giá trị | So tập khóa, từng dòng và tổng |
| “Tổng tiền khớp là dữ liệu đúng” | Sai số có thể bù trừ | Row-level reconciliation |
| “`COALESCE` luôn cho giá trị đúng” | Cột mới stale nhưng không NULL | Sync và mismatch detection |
| “Backfill một lần là xong” | Writer cũ còn ghi và event đến muộn | Bridge/CDC và kiểm tra liên tục |
| “Có surrogate PK thì không duplicate” | Hai bản ghi cùng business grain vẫn khác ID | Unique-grain test |
| “Có replica là có backup” | Xóa/ghi sai có thể replicate | Backup độc lập, restore drill |
| “Có file dump tức đạt RTO” | Restore và khởi động ứng dụng có thể chậm | Đo end-to-end recovery |
| “PITR luôn undo được migration” | Mất giao dịch mới hoặc lệch với broker | Kế hoạch reconcile/roll-forward |
| “Rollback app cũ được sau khi drop cột” | Binary cũ không hiểu schema mới | Xác định điểm không rollback đơn giản |
| “`NOT VALID` nghĩa constraint không áp dụng” | Ghi mới vẫn có thể bị kiểm tra | Hiểu trạng thái chưa validate lịch sử |
| “`CONCURRENTLY` nghĩa không có chi phí” | Vẫn tốn I/O, CPU và có thể lỗi | Đo tải và trạng thái index |
| “Chạy trên DB nhỏ đủ đại diện” | Không phản ánh lock/index/backfill lớn | Tải/khối lượng gần thực và giám sát |
| “Xóa dữ liệu test khỏi production sau thử là ổn” | Có thể đã kích hoạt email, tiền, event | Môi trường cô lập và side effect giả lập |
| “Schema DB đổi thì API phải đổi ngay” | Consumer có vòng đời khác | API/event contract độc lập |
| “Chỉ cần test đường thành công” | Lỗi thường xảy ra khi retry/concurrency | Failure injection an toàn |
| “Mọi event nhận trễ là lỗi nhập liệu” | Event time và ingestion time khác | Watermark và chính sách chốt kỳ |
| “Ghi log mọi dữ liệu để dễ debug” | Có thể làm lộ PII/tiền | Metric, ID tham chiếu và kiểm soát truy cập |

## 18. Bài luyện tập có lời giải

### Bài 1 — Thay tên cột trong một lần có an toàn?

Hệ thống có hai phiên bản ứng dụng chạy song song. Bản cũ đọc `amount_cents`; bản mới đọc `amount_minor`. Nhóm muốn chạy `ALTER TABLE ... RENAME COLUMN` trực tiếp rồi rolling deploy app mới. Hãy nêu nguy cơ và kế hoạch phù hợp.

**Lời giải:** Bản app cũ sẽ lỗi ngay khi cột bị rename, còn bản mới có thể lỗi nếu khởi động trước schema mới. Nên **expand** thêm cột mới, giữ bridge/đồng bộ và backfill, kiểm tra ma trận app–schema, chuyển đọc/ghi theo pha tương thích rồi **contract** sau khi không còn consumer cũ.

### Bài 2 — Tổng bằng nhau nhưng dữ liệu sai

Nguồn có `O1=100`, `O2=200`; đích có `O1=150`, `O2=150`. Tổng đều 300. Chỉ kiểm tra `SUM` có đạt chưa?

**Lời giải:** **Chưa.** Hai bản ghi đều sai nhưng sai lệch bù trừ. Đối soát **từng khóa nghiệp vụ**, rồi so tập khóa, số dòng và các tổng theo tenant/kỳ/đơn vị.

### Bài 3 — Backfill xong nhưng reader vẫn sai

Một dòng có `amount_cents=1000`, `amount_minor=1000`. App cũ cập nhật `amount_cents=1200` nhưng bridge không hoạt động. Reader dùng `COALESCE(amount_minor,amount_cents)`. Nó đọc gì và sửa thế nào?

**Lời giải:** Đọc **1000**, tức là **sai** vì cột mới không NULL nhưng đã cũ. Phải sửa cơ chế đồng bộ writer, chạy mismatch check và bổ sung kiểm thử writer cũ **sau backfill**; `COALESCE` không xử lý giá trị stale.

### Bài 4 — Retry khi backfill bị kill

Job chạy batch theo `WHERE amount_minor IS NULL`, transaction bị kill khi đang cập nhật lô thứ 20. Có thể chạy lại an toàn không?

**Lời giải:** Nếu mỗi batch là transaction nguyên tử và mapping idempotent, batch chưa commit rollback; chạy lại sẽ chọn những dòng còn NULL. Kiểm tra concurrency, checkpoint và row-level mismatch để bảo đảm **không còn giá trị đã có nhưng sai**.

### Bài 5 — SQL kiểm tra NULL chưa đủ

Sau backfill `SELECT COUNT(*) WHERE amount_minor IS NULL` trả 0, nhưng `amount_minor` có 10 giá trị lệch `amount_cents`. Có thể chuyển read sang cột mới không?

**Lời giải:** **Không.** Gate độ đầy đủ đạt nhưng correctness chưa đạt. So bằng `IS DISTINCT FROM`, xác định writer/trigger nào tạo lệch, sửa theo nguồn đáng tin và chạy đối soát lại.

### Bài 6 — Giới hạn kiểu dữ liệu

`amount_cents` là signed `INTEGER`; `amount_minor` là `BIGINT`. Khi cột cũ và app cũ còn dùng, app mới muốn ghi giá trị **3.000.000.000**. Điều gì xảy ra?

**Lời giải:** Số này vượt giới hạn tối đa signed 32-bit là **2.147.483.647**. Không thể bảo toàn cột legacy và consumer cũ theo mapping 1:1. Phải nâng cấp toàn bộ consumer, có giai đoạn S1b/S2 được thử nghiệm, rồi mới bật phạm vi giá trị lớn.

### Bài 7 — Writer mới chỉ ghi cột mới

Trong S1, `amount_cents` vẫn `NOT NULL`, bridge chỉ copy từ cột cũ. App A2 gửi INSERT chỉ có `amount_minor`. Có chắc thành công không?

**Lời giải:** **Không.** INSERT thiếu `amount_cents` sẽ vi phạm `NOT NULL`. Cần ứng dụng chuyển tiếp ghi cả hai, hoặc pha S1b khi **không còn reader/writer cũ**, bỏ bridge/guard đúng lúc và cho cột cũ nullable trước khi chạy new-only writer.

### Bài 8 — Có thể rollback về A0 sau S1b?

Hệ đã dỡ bridge, cho `amount_cents` nullable và app mới bắt đầu ghi `amount_minor` với giá trị lớn. Một nút feature flag “read old” có khôi phục an toàn không?

**Lời giải:** **Không.** Cột cũ có thể NULL/stale hoặc không chứa được số lớn. Phải dùng roll-forward hoặc quy trình tái tạo có kiểm tra, không coi feature flag là rollback dữ liệu tự động.

### Bài 9 — Replica có thay được backup?

Nhóm có một read replica đồng bộ nhưng chưa từng thử restore từ backup. Sau lỗi chạy `DELETE` nhầm, việc có replica đủ bảo đảm khôi phục không?

**Lời giải:** **Không.** Lệnh xóa hợp lệ có thể được replicate sang replica. Cần backup độc lập, log/PITR nếu yêu cầu, retention, kiểm tra và **diễn tập khôi phục thực tế**.

### Bài 10 — Đánh giá RPO/RTO

Sự cố xảy ra lúc 10:00, khôi phục tới mốc dữ liệu 09:58, dịch vụ hoạt động đầy đủ lúc 11:30. Mục tiêu là **RPO ≤ 5 phút**, **RTO ≤ 60 phút**. Đánh giá?

**Lời giải:** Mất dữ liệu tối đa theo hai mốc đã cho là **2 phút**, có thể đạt RPO nếu các mốc commit đã được xác minh. Thời gian gián đoạn **90 phút**, **không đạt RTO**. Phải đánh giá cả khởi động app, kết nối, kiểm thử và việc mở lại dịch vụ.

### Bài 11 — PITR làm biến mất giao dịch mới?

10:05 drop cột cũ; 10:15 phát hiện lỗi job; từ 10:05 đến 10:15 có nhiều đơn hợp lệ được tạo. Nhóm đề xuất phục hồi toàn DB về 10:04. Điều gì cần xem xét?

**Lời giải:** PITR toàn DB về 10:04 có thể mất các commit từ sau đó, đồng thời lệch với payment, broker và các consumer. Nên ưu tiên **roll-forward** khi chỉ là lỗi consumer; nếu phải restore, có kế hoạch bảo toàn/tái áp dụng giao dịch sau mốc và đối soát liên hệ giữa các hệ.

### Bài 12 — Snapshot + CDC không có watermark

Nhóm copy bảng cũ sang DB mới trong một giờ, sau đó mới bắt đầu đọc CDC từ thời điểm kết thúc copy. Có nguy cơ gì?

**Lời giải:** Các update xảy ra **trong lúc copy** có thể không nằm đúng ảnh chụp được chuyển và cũng không được đọc lại qua CDC. Cần snapshot nhất quán, offset/watermark được ghi và xử lý replay/idempotency; không lấy “copy xong thì bật CDC” làm bảo đảm đầy đủ.

### Bài 13 — So sánh fact khác grain

Fact cũ có 100 đơn; fact mới có 420 dòng hàng. `COUNT(*)` không bằng nhau. Điều này chứng minh migration sai?

**Lời giải:** **Không.** Grain khác nhau. Cần kiểm tra **đủ tập đơn**, duy nhất `(order_id,line_no)`, mapping dòng nguồn, phép tổng hợp giá trị hàng cấp dòng theo đơn và các loại tiền/phí/giảm giá. Không ép hai số dòng phải bằng nhau.

### Bài 14 — SCD Type 2 bị chồng khoảng

Một giao dịch lúc 15/07 JOIN được hai bản ghi dimension khách vì hai khoảng hiệu lực chồng lấn. Migration fact báo cáo doanh số tăng gấp đôi. Phép thử nào cần bổ sung?

**Lời giải:** Kiểm tra **không chồng lấn khoảng `[valid_from,valid_to)`** theo business key và **as-of join phải khớp đúng một phiên bản** cho mỗi fact. Đừng sửa bằng `SUM(DISTINCT amount)` vì các giao dịch thật có thể có cùng giá trị.

### Bài 15 — Contract khi còn job ít chạy

Trong ba tuần không có request production nào đọc `amount_cents`, nhưng một job đối soát cuối quý vẫn dùng cột này. Đã đủ điều kiện drop chưa?

**Lời giải:** **Chưa.** Monitoring runtime ba tuần không quan sát được job cuối quý. Phải kiểm kê và sửa job, thử trên schema mới, xác minh các consumer cũ/restore runbook, rồi mới phê duyệt contract.

### Bài 16 — Mô hình địa chỉ không có phép biến đổi ngược

Nguồn chứa `shipping_address_text`; hệ mới tách `street,ward,city` và xóa trường gốc. Một số địa chỉ có ghi chú “giao tại cổng sau” bị parser bỏ. Điều gì thất bại?

**Lời giải:** **Mất thông tin không khả nghịch.** Không có SQL rollback nào tái tạo được ghi chú đã mất. Cần giữ dữ liệu gốc theo chính sách, kiểm thử mapping đa dạng, hàng đợi review và phê duyệt rủi ro trước khi xóa.

### Bài 17 — Mất ACK trong event streaming

Publisher đã gửi một event thành công rồi chết trước khi đánh dấu nó đã phát. Sau restart, event được gửi lại, consumer tạo hai đơn giao hàng. Nguyên nhân và cách khắc phục?

**Lời giải:** At-least-once có thể tạo duplicate delivery. Consumer phải idempotent theo `eventId` và bất biến nghiệp vụ, ghi inbox cùng transaction read model nếu phù hợp, đồng thời bảo vệ các side effect bên ngoài. Test phải xác nhận **chỉ một công việc giao** sau replay.

## 19. Checklist kiểm chứng chuyển đổi lược đồ và khôi phục

- [ ] Đã định nghĩa **grain, khóa nghiệp vụ, namespace và công thức mapping** cũ–mới.
- [ ] Đã thống nhất đơn vị tiền, thời điểm nghiệp vụ, trạng thái, `NULL` và trường hợp ngoại lệ.
- [ ] Đã lập **ma trận app–schema** có cả consumer hiếm chạy, worker, CDC và BI.
- [ ] Đã đo baseline latency, lỗi, WAL/I/O, replication lag và khối lượng dữ liệu.
- [ ] Expand không phá app cũ; những DDL có lock đã được thử với tải phù hợp.
- [ ] Có bridge/dual-write/CDC giữ cập nhật đồng thời nhất quán, không tạo hai nguồn chân lý.
- [ ] Backfill chia lô, retry an toàn, idempotent và có giới hạn tải.
- [ ] Đã thử worker dừng trước/sau commit, hai worker chạy đồng thời, row lock và restart.
- [ ] Có kiểm tra **NULL, mismatch cấp dòng, tập khóa, duplicate, FK và tổng theo phạm vi**.
- [ ] Đã đối soát với nguồn độc lập ở **cùng snapshot/watermark**, không chỉ so hai cột cùng hàng.
- [ ] Với lịch sử, đã kiểm tra event time, SCD valid-time, late events, replay và restatement.
- [ ] Shadow read/canary đạt correctness và SLO trước khi chuyển tất cả reader.
- [ ] Chỉ chuyển new-only writer sau khi cột mới đủ dữ liệu, ràng buộc hợp lệ và không còn writer cũ.
- [ ] Đã ghi rõ **điểm không thể rollback đơn giản**, đặc biệt khi dỡ sync và bỏ cột.
- [ ] API/event/CDC contract được kiểm thử độc lập với thay đổi schema DB.
- [ ] Đã kiểm tra schema/role/extension/config khi restore trong môi trường cô lập.
- [ ] Có backup/snapshot/log đáng tin cậy và **diễn tập restore/PITR thực tế**.
- [ ] RPO/RTO có mục tiêu được phê duyệt và **số đo thực nghiệm**, không chỉ cam kết trên giấy.
- [ ] Có kế hoạch tái áp dụng hoặc đối soát giao dịch mới nếu phải phục hồi về mốc cũ.
- [ ] Có kiểm soát PII, quyền, retention và đường gửi thông điệp khi dùng dữ liệu phục hồi để thử.
- [ ] Gate **go/no-go** có bằng chứng, owner và cách dừng/roll-forward.
- [ ] Không contract khi còn consumer cũ; theo dõi mismatch và chất lượng dữ liệu **sau deploy**.

## 20. Tổng kết: kiểm chứng trước khi xóa đường lui

Hãy nhớ bốn câu hỏi trước mọi thay đổi có rủi ro:

1. **Có thể triển khai cùng lúc với hệ đang chạy không?** — kiểm thử tương thích app–schema và ràng buộc.
2. **Dữ liệu đã chuyển đầy đủ và đúng nghĩa chưa?** — đối soát **theo khóa, từng dòng, kỳ và đơn vị**, không chỉ đếm dòng hoặc tổng tiền.
3. **Nếu lỗi giữa chừng có thể tiếp tục an toàn không?** — transaction ngắn, idempotency, checkpoint, CDC offset và khả năng retry.
4. **Nếu lỗi lớn có thể phục hồi trong giới hạn chấp nhận không?** — backup, PITR/replay, diễn tập restore, RPO/RTO và kế hoạch xử lý giao dịch sau mốc khôi phục.

**Ghi nhớ:** **Kiểm thử chuyển đổi lược đồ, đối soát và khả năng khôi phục phải được thiết kế như một hệ thống bằng chứng xuyên suốt expand–migrate–contract.** Một migration chỉ đáng tin khi **tính đúng của dữ liệu, tính tương thích của consumer và con đường phục hồi** đã được xác minh trước khi loại bỏ cấu trúc cũ.




