# Mở rộng trước, chuyển đổi dần rồi thu hẹp cấu trúc cũ

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, thiết kế dữ liệu không chỉ là tạo một mô hình đúng ở thời điểm ban đầu, mà còn phải làm cho mô hình **tiến hóa an toàn khi yêu cầu nghiệp vụ, lưu lượng và các hệ thống tích hợp thay đổi**. Một thay đổi cột tưởng chừng đơn giản có thể khiến phiên bản ứng dụng cũ ngừng hoạt động, job ETL đọc sai, dịch vụ khác bị mất trường, hoặc dữ liệu mới và cũ không còn nhất quán.

Chủ đề thuộc chương **Tiến hóa mô hình** này giới thiệu chiến lược **mở rộng → chuyển đổi dần → thu hẹp** (*expand–migrate–contract*, còn gọi *expand-and-contract*):

1. **Expand:** thêm cấu trúc mới theo cách chưa phá những người đang sử dụng cấu trúc cũ.
2. **Migrate/Transition:** chuyển dữ liệu và các đường đọc/ghi qua nhiều đợt, có đo lường và đối soát.
3. **Contract:** chỉ loại bỏ cấu trúc cũ khi **không còn phụ thuộc** và đã đủ điều kiện an toàn.

Sau bài học, bạn có thể:

- Lập **ma trận tương thích** giữa phiên bản schema, ứng dụng, API, event và pipeline.
- Xác định khi nào một thay đổi **additive** có thể triển khai an toàn và khi nào phải tách nhiều bước.
- Thiết kế **dual-write**, fallback read, trigger/CDC hoặc workflow phù hợp mà không tạo hai nguồn chân lý.
- Backfill dữ liệu lớn theo lô, idempotent, có watermark, không mất cập nhật đồng thời.
- Tăng dần ràng buộc `NOT NULL`, khóa ngoại và chỉ mục theo chiến lược kiểm chứng.
- Đặt điều kiện chuyển pha, rollback/roll-forward và phép đo chất lượng dữ liệu.
- Phân biệt thay đổi schema nội bộ với thay đổi hợp đồng API/event bên ngoài.

## 1. Vì sao không thể luôn sửa schema trong một lần?

Giả sử dịch vụ Orders đang lưu một số tiền bằng cột `amount_cents INTEGER`. Nhóm kỹ thuật muốn chuyển sang `amount_minor BIGINT` để tên dễ hiểu hơn và có khoảng biểu diễn lớn hơn. Một kế hoạch nguy hiểm là:

~~~sql
ALTER TABLE orders RENAME COLUMN amount_cents TO amount_minor;
ALTER TABLE orders ALTER COLUMN amount_minor TYPE BIGINT;
~~~

Về dữ liệu, phép đổi có vẻ hợp lý. Nhưng trong môi trường đang chạy:

- **Ứng dụng v1** còn truy vấn `SELECT amount_cents FROM orders` sẽ lỗi ngay sau khi đổi tên.
- Một số **worker, cron, ETL và ứng dụng di động** có thể chưa được nâng phiên bản.
- Trong rolling deployment, vài instance vẫn ghi theo schema cũ, còn instance mới đã dùng schema mới.
- Một job snapshot hoặc CDC có thể đọc cấu trúc cũ và mất khả năng giải mã dữ liệu thay đổi.
- Nếu đổi ý nghĩa từ **cent** sang **đơn vị tiền chính**, dữ liệu có thể sai **gấp 100 lần** dù SQL vẫn chạy.

Đổi tên hoặc đổi kiểu trực tiếp đôi khi vẫn chấp nhận được nếu hệ thống nhỏ, có cửa sổ dừng ghi được phê duyệt, toàn bộ consumer được kiểm soát và kế hoạch khôi phục rõ. Nhưng với hệ thống **cần phục vụ liên tục hoặc có nhiều consumer**, phải thiết kế **giai đoạn các phiên bản cùng tồn tại**.

> Nguyên tắc: **Không loại bỏ một cấu trúc khi vẫn còn phiên bản ứng dụng hoặc consumer hợp lệ cần đến nó.**

## 2. Tư duy expand–migrate–contract

~~~mermaid
flowchart LR
    A["Schema cũ + App cũ"] --> B["EXPAND\nCũ và mới cùng tồn tại"]
    B --> C["MIGRATE\nGhi tương thích + backfill + chuyển đọc"]
    C --> D["CONTRACT\nBỏ cấu trúc cũ khi đã an toàn"]
    D --> E["Schema mới + App mới"]
~~~

### Giai đoạn 1 — Expand: thêm mà chưa phá

Mục tiêu: tạo nơi tiếp nhận mô hình mới **trong khi client cũ vẫn có thể hoạt động**.

Ví dụ:

- Thêm cột `amount_minor BIGINT NULL`.
- Tạo bảng mới mà chưa xóa bảng cũ.
- Tạo chỉ mục phục vụ cách truy vấn mới.
- Chuẩn bị mapping và logic ghi nhất quán.
- Chưa ép app cũ phải dùng trường mới; chưa xóa/đổi tên trường cũ.

**Additive về cú pháp không bảo đảm tương thích về hành vi.** Thêm cột có default đắt đỏ, trigger lỗi, constraint chưa phù hợp hoặc tăng độ trễ ghi vẫn có thể gây sự cố. Cần xét DBMS, phiên bản, tải và cách triển khai thật.

### Giai đoạn 2 — Migrate: chuyển dữ liệu và lưu lượng theo từng bước

Mục tiêu: đảm bảo **dữ liệu mới được đồng bộ**, **dữ liệu lịch sử được backfill**, người tiêu thụ được chuyển có kiểm soát.

Các công việc có thể chạy song song nhưng phải có thứ tự phụ thuộc:

- Đảm bảo mọi phiên bản ứng dụng đang ghi có **cơ chế duy trì cấu trúc mới**.
- Backfill các dòng cũ theo lô.
- Kiểm tra đối soát cũ–mới, tài nguyên và lỗi đồng bộ.
- Chuyển một phần người đọc sang cột/bảng mới.
- Mở rộng phạm vi cho đến khi **mọi người đọc và ghi** dùng mô hình mới.

### Giai đoạn 3 — Contract: thu hẹp cấu trúc cũ

Mục tiêu: xóa đường ghi cũ, constraint cũ, chỉ mục không cần, cột/bảng cũ **sau khi xác nhận không còn phụ thuộc**.

Contract **không phải bước dọn dẹp tùy hứng**. Nó là một lần thay đổi có thể làm hỏng app cũ, job ít chạy, dashboard ít dùng hoặc quá trình khôi phục từ backup cũ.

## 3. Bốn bất biến phải giữ trong quá trình chuyển đổi

| Bất biến | Câu hỏi kiểm chứng | Nếu vi phạm |
|---|---|---|
| **Tương thích (compatibility)** | Mỗi phiên bản đang chạy có hiểu schema được triển khai không? | Ứng dụng lỗi truy vấn/ghi |
| **Tính đúng (correctness)** | Giá trị cũ và mới có cùng ý nghĩa và được cập nhật nhất quán không? | Báo cáo/đơn hàng sai |
| **Tiến triển (progress)** | Backfill và cutover có tiếp tục được khi retry, restart, lỗi mạng không? | Kẹt một phần, khó tiếp tục |
| **Khả năng quan sát và phục hồi** | Có biết dòng nào chưa chuyển, có đường quay lại hoặc khắc phục an toàn không? | Lỗi âm thầm, rollback nguy hiểm |

Trong thực tế còn phải xét **bảo mật, retention, khóa ngoại, độ trễ, tải ghi và chi phí lưu trữ**. Một migration chỉ đạt khi script SQL trả exit code 0 nhưng làm chậm sản xuất hoặc tạo dữ liệu sai **chưa phải thành công**.

### Rõ người sở hữu quyết định

Chủ sở hữu nghiệp vụ cần xác nhận **ý nghĩa trường và quy tắc chuyển đổi**. Nhóm phát triển/DBA chịu trách nhiệm triển khai, khóa/ràng buộc, backfill và sức khỏe DB. Các consumer phải xác nhận tương thích hợp đồng. Đừng để job chuyển đổi tự quyết rằng giá trị không parse được sẽ thành 0 hay `NULL`.

## 4. Ma trận tương thích giữa phiên bản schema và ứng dụng

Giả sử có ba trạng thái schema:

- **S0:** chỉ có `amount_cents`.
- **S1:** có `amount_cents` và `amount_minor`, với cơ chế đồng bộ.
- **S2:** chỉ giữ `amount_minor`.

Ứng dụng:

- **A0 (legacy):** chỉ đọc/ghi `amount_cents`.
- **A1 (transition):** biết cả hai cột, có cơ chế đọc an toàn và ghi theo chiến lược chuyển đổi.
- **A2 (new):** chỉ đọc/ghi `amount_minor`.

| Ứng dụng / Schema | S0 — cũ | S1 — hai cột | S2 — mới |
|---|---|---|---|
| **A0** | Hoạt động | **Có thể hoạt động**, nếu giữ đầy đủ ngữ nghĩa cột cũ và đồng bộ | **Không** |
| **A1** | **Tùy thiết kế**; nếu SQL tham chiếu cột mới sẽ lỗi | Hoạt động khi cơ chế sync/backfill đúng | **Tùy thiết kế**; nếu vẫn tham chiếu cột cũ sẽ lỗi |
| **A2** | **Không** | Hoạt động khi cột mới đã có dữ liệu, ngữ nghĩa và cơ chế ghi đúng | Hoạt động |

Thứ tự triển khai tổng quát:

~~~text
S0 + A0
    ↓ Expand schema
S1 + A0
    ↓ Triển khai logic tương thích, backfill
S1 + A1
    ↓ Đổi đường đọc/ghi và quan sát
S1 + A2
    ↓ Xác nhận A0/A1 không còn phụ thuộc
S2 + A2
~~~

**Ma trận phải được tạo cho hệ thật**, không chỉ hai cột ví dụ. Một thay đổi có thể ảnh hưởng API bên ngoài, mobile app tồn tại nhiều tháng, background worker, CDC, BI và luồng restore từ snapshot.

### Đừng mặc định A1 chạy được trên S0

Ứng dụng có câu `SELECT COALESCE(amount_minor, amount_cents)` **vẫn lỗi** trên S0 vì `amount_minor` chưa tồn tại. Khả năng fallback chỉ hữu ích **sau khi schema đã được mở rộng**, trừ khi app có đường truy vấn tách riêng hoặc feature detection được thiết kế rõ.

## 5. Ví dụ xuyên suốt: từ cột INT cũ sang BIGINT mới

Ta dùng PostgreSQL để minh họa **một phép chuyển đổi có thể kiểm chứng**. Không giả định môi trường nào cũng cần đúng tên cột hoặc cú pháp này.

### 5.1. Bối cảnh và ý nghĩa

Bảng nguồn ban đầu:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    created_at TIMESTAMPTZ NOT NULL
);
~~~

Yêu cầu mới:

~~~text
Tên cũ: amount_cents INTEGER
Tên mới: amount_minor BIGINT
Đơn vị trong ví dụ: cent của USD cho cả hai trường
Grain: một dòng = một đơn hàng
Quy tắc chuyển: amount_minor = amount_cents::BIGINT
~~~

**Quan trọng:** đổi `INTEGER` sang `BIGINT` và đổi tên **không tự thay đổi đơn vị**. Trong ví dụ, *minor unit* vẫn là cent vì chỉ xét USD. Nếu mở rộng nhiều tiền tệ có đơn vị nhỏ nhất khác nhau, cần `currency_code`, quy tắc quy đổi/làm tròn và một migration nghiệp vụ **khác**, không suy từ phép cast này.

Tại sao chọn ví dụ này? Nó cho phép minh họa **đổi cấu trúc nhưng giữ ngữ nghĩa**, tránh việc cố tự động tách địa chỉ tự do hoặc tên người thành các trường mà dữ liệu cũ không đủ thông tin.

### 5.2. Expand: thêm cột mới trước

~~~sql
ALTER TABLE orders
    ADD COLUMN amount_minor BIGINT;

ALTER TABLE orders
    ADD CONSTRAINT orders_amount_minor_nonnegative
    CHECK (amount_minor IS NULL OR amount_minor >= 0)
    NOT VALID;
~~~

Sau bước này:

- `amount_cents` vẫn tồn tại để **A0** hoạt động.
- `amount_minor` ban đầu **nullable**, nên chưa bắt dữ liệu lịch sử phải được nạp ngay.
- `CHECK ... NOT VALID` của PostgreSQL có thể áp dụng cho **các dòng ghi mới/thay đổi** mà chưa quét xác minh tất cả dòng lịch sử tại thời điểm thêm; vẫn cần kiểm tra ảnh hưởng khóa trong môi trường thật.
- Không thêm `NOT NULL` ngay khi hàng triệu dòng cũ chưa được backfill.

**Cẩn thận về hiệu năng DDL:** thêm cột nullable không default thường là thao tác metadata tương đối nhẹ trên nhiều phiên bản PostgreSQL hiện đại, nhưng `ALTER TABLE` vẫn có thể cần lock gây chờ. Không coi nó là “không lock” hoặc “luôn tức thời”.

### 5.3. Vấn đề đồng bộ khi app cũ và mới cùng ghi

Giả sử sau khi thêm cột, backfill đơn `order_id=42`:

~~~text
amount_cents = 1000
amount_minor = 1000
~~~

Sau đó A0 cập nhật:

~~~sql
UPDATE orders
SET amount_cents = 1200
WHERE order_id = 42;
~~~

Nếu không có cơ chế đồng bộ, kết quả:

~~~text
amount_cents = 1200   -- mới
amount_minor = 1000   -- cũ, sai
~~~

Đường đọc `COALESCE(amount_minor, amount_cents::BIGINT)` sẽ lấy **1000**, tạo lỗi số tiền **âm thầm**. Backfill một lần **không đủ** nếu còn phiên bản cũ có thể ghi.

**Điều kiện cần:** trước hoặc trong giai đoạn backfill, bảo đảm **mọi đường ghi** vào dữ liệu đang chuyển được đồng bộ bằng một cơ chế có chủ đích. Tùy hệ thống:

1. **Application dual-write**: ứng dụng viết hai cột trong **cùng transaction/statement**, sau khi đã thay thế hết các writer cũ; hoặc
2. **DB trigger tương thích**: DB đồng bộ hai cột kể cả khi A0 chỉ biết cột cũ; hoặc
3. Một workflow chuyển đổi có **đóng băng/điều phối ghi**, CDC và reconciliation được thiết kế đủ mạnh, với cửa sổ nhất quán rõ.

Không được chạy hai thao tác ghi sang **hai database khác nhau** rồi gọi đó là dual-write nguyên tử. Nếu không có transaction phân tán, cần outbox/CDC, retry/idempotency và cơ chế đối soát.

### 5.4. Minh họa bridge bằng trigger PostgreSQL

Trong ví dụ, muốn A0 còn ghi `amount_cents` và A1/A2 có thể ghi `amount_minor` khi **S1** tồn tại, có thể dùng một trigger đồng bộ hai chiều. Đây là **mẫu kỹ thuật để học**, cần thử cạnh tranh giao dịch, tải và các đường bulk load thực tế trước khi dùng sản xuất.

~~~sql
CREATE OR REPLACE FUNCTION sync_orders_amount()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.amount_minor IS NULL THEN
            NEW.amount_minor := NEW.amount_cents::BIGINT;
        ELSIF NEW.amount_cents IS NULL THEN
            IF NEW.amount_minor < 0
               OR NEW.amount_minor > 2147483647 THEN
                RAISE EXCEPTION 'amount_minor outside legacy INTEGER range';
            END IF;
            NEW.amount_cents := NEW.amount_minor::INTEGER;
        ELSIF NEW.amount_minor IS DISTINCT
              FROM NEW.amount_cents::BIGINT THEN
            RAISE EXCEPTION 'inconsistent order amounts';
        END IF;
    ELSE
        IF NEW.amount_cents IS DISTINCT FROM OLD.amount_cents
           AND NEW.amount_minor IS NOT DISTINCT FROM OLD.amount_minor THEN
            -- Writer cũ chỉ cập nhật trường cũ.
            NEW.amount_minor := NEW.amount_cents::BIGINT;
        ELSIF NEW.amount_minor IS DISTINCT FROM OLD.amount_minor
              AND NEW.amount_cents IS NOT DISTINCT FROM OLD.amount_cents THEN
            -- Writer mới chỉ cập nhật trường mới.
            IF NEW.amount_minor < 0
               OR NEW.amount_minor > 2147483647 THEN
                RAISE EXCEPTION 'amount_minor outside legacy INTEGER range';
            END IF;
            NEW.amount_cents := NEW.amount_minor::INTEGER;
        ELSIF NEW.amount_minor IS DISTINCT FROM OLD.amount_minor
              AND NEW.amount_cents IS DISTINCT FROM OLD.amount_cents
              AND NEW.amount_minor IS DISTINCT
                  FROM NEW.amount_cents::BIGINT THEN
            RAISE EXCEPTION 'inconsistent order amounts';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_sync_orders_amount
BEFORE INSERT OR UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION sync_orders_amount();
~~~

Giải thích và giới hạn:

- Trên `INSERT`, nếu chỉ có giá trị cũ, trigger điền giá trị mới; nếu chỉ có giá trị mới trong khoảng legacy, trigger điền cột cũ **trước khi** các ràng buộc `NOT NULL` được kiểm tra.
- Trên `UPDATE`, một phía đổi thì phía kia được đồng bộ; nếu hai phía cùng đổi nhưng không bằng nhau, transaction bị từ chối.
- Trong giai đoạn tương thích, **không cho phép giá trị vượt giới hạn `INTEGER` cũ** dù cột mới là `BIGINT`, vì các writer/reader cũ chưa hiểu giá trị lớn.
- Mẫu giả định **một đơn có một giá trị tiền không âm** và đơn vị không đổi; nếu nghiệp vụ cho phép số âm/điều chỉnh, phải đổi invariant.
- Với update các trường khác trên dòng chưa backfill, cột mới có thể vẫn `NULL`; **đường đọc fallback** và backfill xử lý trạng thái này.
- Việc thay đổi cột bằng công cụ bypass trigger, bulk copy đặc biệt, replication hoặc ghi qua một đường không dùng trigger cần được nhận diện; không tự xem trigger là bảo vệ tuyệt đối toàn hệ.

**Một lựa chọn đơn giản hơn:** nếu có thể triển khai tất cả writer tương thích trước khi chuyển đọc và không còn A0, ứng dụng có thể ghi cả hai cột trong một câu `UPDATE`/transaction, không cần trigger. Cần chọn **một quy tắc nguồn chân lý rõ ràng** để tránh hai cơ chế cùng ghi chồng nhau.

## 6. Backfill dữ liệu lịch sử theo lô và có thể chạy lại

Sau khi đường ghi mới đã an toàn, cần chuyển những bản ghi lịch sử còn `amount_minor IS NULL`.

### 6.1. Không cập nhật hàng triệu dòng trong một transaction khổng lồ

Một câu:

~~~sql
UPDATE orders
SET amount_minor = amount_cents::BIGINT
WHERE amount_minor IS NULL;
~~~

về mặt tính toán là hợp lý nhưng với bảng lớn có thể:

- Tạo nhiều WAL/redo log, phiên bản MVCC và I/O.
- Tăng replication lag, lock contention hoặc ảnh hưởng latency.
- Làm transaction dài, khó quan sát tiến độ và khó retry.
- Gây bloat và áp lực vacuum/compaction.

Cần lựa chọn batch size và tốc độ theo workload thật.

### 6.2. Ví dụ batch PostgreSQL có khóa dòng

~~~sql
WITH batch AS (
    SELECT order_id
    FROM orders
    WHERE amount_minor IS NULL
    ORDER BY order_id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE orders AS o
SET amount_minor = o.amount_cents::BIGINT
FROM batch AS b
WHERE o.order_id = b.order_id
  AND o.amount_minor IS NULL
RETURNING o.order_id, o.amount_minor;
~~~

Chạy mỗi lô trong **transaction ngắn** với bộ điều khiển tốc độ, giám sát và điểm dừng. Lệnh tìm những dòng chưa chuyển nên có độ chọn lọc/index phù hợp khi bảng lớn; đừng mặc định liên tục quét toàn bộ bảng là rẻ.

**Vì sao batch idempotent?** Sau một lô thành công, các dòng ấy không còn `NULL` nên chạy lại **không tự ghi đè**. Nếu tiến trình chết trước commit, lô rollback và được chọn lại. Với trigger đồng bộ khi cập nhật, giá trị mới được tính từ **giá trị cũ trong cùng phiên bản dòng đã khóa**, giảm rủi ro ghi giá trị lỗi thời.

**Vì sao `SKIP LOCKED`?** Nhiều worker có thể chia nhau những dòng chưa bị khóa thay vì cùng chờ một dòng. Đây **không** phải bảo đảm công bằng hay rằng mọi dòng đều sẽ được chọn ngay; worker cần chạy tiếp, xử lý lỗi và theo dõi backlog.

### 6.3. Kiểm tra tiến độ và sai khác

~~~sql
-- Số dòng chưa backfill:
SELECT COUNT(*) AS missing_new_amount
FROM orders
WHERE amount_minor IS NULL;

-- Sai khác (bao gồm NULL):
SELECT order_id, amount_cents, amount_minor
FROM orders
WHERE amount_minor IS DISTINCT FROM amount_cents::BIGINT
ORDER BY order_id
LIMIT 100;

-- Tổng đối soát trên phạm vi đã chốt:
SELECT
    COUNT(*) AS row_count,
    SUM(amount_cents::BIGINT) AS old_sum,
    SUM(amount_minor) AS new_sum
FROM orders;
~~~

`IS DISTINCT FROM` ở PostgreSQL so sánh cả trường hợp `NULL`; không bị lỗ hổng như `amount_minor <> amount_cents`, vốn cho kết quả UNKNOWN khi cột mới NULL. **Tổng bằng nhau chưa chứng minh từng dòng đúng**: hai sai lệch có thể bù trừ. Cần kiểm tra đồng thời tổng, số dòng, khóa và sai khác cấp dòng.

Trong hệ lớn, full scan đối soát có thể tốn tài nguyên. Có thể đo theo **partition/khoảng ID/tenant**, xây checksum hoặc thống kê theo batch và làm vòng kiểm tra đầy đủ ngoài giờ cao điểm; phải ghi rõ giới hạn của mỗi phép thử.

## 7. Chuyển đường đọc và đường ghi theo từng pha

Sau expand và khi có cơ chế đồng bộ, không nên chuyển tất cả consumer trong một lượt nếu khó kiểm soát rủi ro. Một kế hoạch triển khai:

| Pha | Đường ghi | Đường đọc | Điều kiện trước khi sang pha sau |
|---|---|---|---|
| **P0 — cũ** | Chỉ trường cũ | Chỉ trường cũ | Kiểm kê consumer và định nghĩa chuyển đổi |
| **P1 — expand** | Cũ vẫn hoạt động; đồng bộ tạo trường mới | Cũ | Schema mới đã có, không phá A0 |
| **P2 — backfill** | Đồng bộ cũ/mới ở transaction nguồn | Cũ; shadow-read trường mới | Backlog và mismatch giảm về ngưỡng đã duyệt |
| **P3 — canary** | Tiếp tục đồng bộ | Một nhóm nhỏ đọc mới có fallback | Đối soát, lỗi và latency đạt SLO |
| **P4 — cutover** | Ghi trường mới, giữ đồng bộ ngược nếu A0 còn chạy | Mọi consumer được phép đọc mới | Không còn đường đọc cũ; writer cũ đã ngừng |
| **P5 — contract** | Chỉ trường mới | Chỉ trường mới | Đã qua thời gian quan sát, có phương án phục hồi |

Phân biệt **đường đọc** và **đường ghi**: chuyển đọc không bảo đảm mọi writer đã đổi; chuyển writer không bảo đảm các job đọc cũ đã hết.

### 7.1. Fallback read có điều kiện

Trong S1, một truy vấn chuyển tiếp:

~~~sql
SELECT
    order_id,
    COALESCE(amount_minor, amount_cents::BIGINT) AS amount_for_read
FROM orders
WHERE order_id = :order_id;
~~~

Truy vấn **chỉ an toàn** khi đã loại rủi ro **cột mới có giá trị cũ nhưng không NULL**. Nếu trigger đồng bộ bị tắt hoặc một writer bypass cơ chế đồng bộ, `COALESCE` có thể **ưu tiên giá trị sai**. Vì vậy phải đo mismatch liên tục, không chỉ đo số NULL.

### 7.2. Shadow read và canary

Trong thời gian đầu, ứng dụng có thể đọc cả hai và **so sánh** nhưng vẫn trả giá trị cũ cho người dùng. Sau đó chuyển một phần traffic sang giá trị mới:

~~~text
Phase shadow:
    user sees old_amount
    application compares old_amount vs new_amount
    metrics record mismatches (không log PII/thông tin nhạy cảm)

Phase canary:
    1% requests read new_amount
    compare business results, latency, errors

Phase rollout:
    10% → 50% → 100% nếu các ngưỡng đã định nghĩa đạt
~~~

Đây là **chiến lược minh họa**, không có nghĩa mỗi hệ phải dùng đúng các tỷ lệ ấy. Canary theo **tenant, nhóm ứng dụng hoặc instance** cần tránh tình huống một nhóm vừa ghi theo cách cũ vừa đọc theo cách mới thiếu cơ chế đồng bộ.

### 7.3. Khi nào mới cho phép giá trị lớn hơn giới hạn cũ?

Ví dụ mới dùng `BIGINT` để lưu số lớn hơn `INTEGER`. Trong S1 khi A0 còn hoạt động, trigger ví dụ **từ chối** giá trị lớn hơn 2.147.483.647 để bảo đảm có thể đồng bộ sang cột cũ.

Chỉ cho phép mở rộng phạm vi giá trị sau khi:

1. Tất cả đường đọc/ghi đã hiểu `BIGINT` và không giả định số 32-bit.
2. API, protobuf/JSON schema, job ETL, ORM/Java DTO và báo cáo đã chấp nhận kiểu mới.
3. Cơ chế đồng bộ ngược sang `INTEGER` đã được dỡ bỏ theo kế hoạch.
4. Đã kiểm thử các giá trị sát giới hạn và vượt giới hạn cũ.

**Đổi kiểu ở DB không bảo đảm toàn hệ chấp nhận kiểu mới.** Ví dụ Java `int` không đủ chứa một số `BIGINT` lớn; serializer, consumer và data warehouse cũng có thể giới hạn riêng.

## 8. Tăng ràng buộc mới sau khi dữ liệu đã sạch

Một lỗi phổ biến là thêm `NOT NULL` trước khi backfill hoàn tất. Đúng hơn, sau khi **không còn giá trị NULL và mọi writer đều cung cấp trường mới**, tăng dần độ chặt.

Ví dụ PostgreSQL:

~~~sql
-- Chỉ thực hiện khi đã kiểm tra backfill và mọi writer.
ALTER TABLE orders
    VALIDATE CONSTRAINT orders_amount_minor_nonnegative;

ALTER TABLE orders
    ADD CONSTRAINT orders_amount_minor_present
    CHECK (amount_minor IS NOT NULL) NOT VALID;

ALTER TABLE orders
    VALIDATE CONSTRAINT orders_amount_minor_present;

ALTER TABLE orders
    ALTER COLUMN amount_minor SET NOT NULL;
~~~

Đặc điểm cần hiểu:

- Ràng buộc `CHECK ... NOT VALID` có thể được áp dụng cho ghi mới trước khi đã quét toàn bảng, còn `VALIDATE CONSTRAINT` xác minh dữ liệu lịch sử theo cơ chế và lock của PostgreSQL.
- Nếu còn bản ghi NULL, bước `VALIDATE` tương ứng sẽ thất bại; **không được sửa bằng cách thay NULL thành 0 khi chưa có quy tắc nghiệp vụ**.
- Trên một số phiên bản PostgreSQL, một `CHECK` đã được xác nhận có thể giúp `SET NOT NULL` **tránh một lần quét lại**; vẫn phải kiểm tra phiên bản và lock.
- Sau khi `amount_minor` có `NOT NULL`, thêm/đổi đường ghi phải bảo đảm trigger hoặc ứng dụng cấp giá trị hợp lệ.

### Tăng ràng buộc khóa ngoại cũng phải có pha chuyển

Ví dụ chuyển `orders.customer_ref` dạng TEXT sang `customer_id BIGINT` tham chiếu `customers`:

1. Tạo `customer_id` nullable, chưa gỡ `customer_ref`.
2. Xây **mapping đáng tin cậy** giữa ref cũ và khách hàng đích; không ép ref không khớp về một ID bất kỳ.
3. Đồng bộ ghi mới trong giai đoạn chuyển.
4. Backfill theo lô; đưa trường hợp **không ánh xạ được/đa nghĩa** vào hàng đợi xử lý.
5. Tạo index phù hợp và thêm FK theo cách giảm tác động; PostgreSQL có thể hỗ trợ `ADD CONSTRAINT ... NOT VALID` rồi `VALIDATE CONSTRAINT` cho FK.
6. Chuyển truy vấn/consumer; chỉ sau khi các bất biến đạt mới gỡ ref cũ.

Với hệ nhiều tenant, FK không được vô tình cho `customer_id` thuộc tenant khác. Thiết kế khóa có thể cần **`(tenant_id,customer_id)`** hoặc chiến lược định danh toàn cục đã được chứng minh.

## 9. Contract: loại cấu trúc cũ chỉ sau khi chứng minh không còn ai dùng

Một danh sách “đã deploy app mới” **chưa đủ** cho phép xóa `amount_cents`.

Trước khi contract phải kiểm tra:

- Mọi **instance ứng dụng**, background worker, batch/cron, tác vụ vận hành đều không còn đọc/ghi trường cũ.
- Không còn **mobile/desktop client** phụ thuộc trực tiếp vào biểu diễn cũ hoặc giao diện trả cột cũ.
- ETL/CDC, BI, báo cáo hiếm chạy, view, stored procedure, trigger và tool hỗ trợ đã được nâng cấp.
- Không còn job thỉnh thoảng mới thực hiện (theo tuần/tháng/quý) có thể chạm cột cũ.
- `amount_minor` đầy đủ, đúng ngữ nghĩa; sai khác cũ–mới bằng **0 hoặc được giải trình theo chính sách**.
- Quy trình restore/backfill khi trở lại bản snapshot cũ đã được kiểm thử.
- Đã có phương án dừng, thời điểm triển khai và trách nhiệm xử lý nếu phát sinh lỗi.

### 9.1. Dỡ bridge và xóa cột cũ

Khi **chỉ còn ứng dụng mới**, không còn cần đồng bộ về `amount_cents`:

~~~sql
BEGIN;

DROP TRIGGER IF EXISTS trg_sync_orders_amount ON orders;
DROP FUNCTION IF EXISTS sync_orders_amount();

ALTER TABLE orders
    DROP COLUMN amount_cents;

COMMIT;
~~~

Đây là **thao tác phá vỡ tương thích với A0**. Không chạy nếu vẫn còn writer/reader cũ. Trong hệ thật cần kiểm tra phụ thuộc của function/trigger, view, constraint, quyền và các transaction đang giữ lock. PostgreSQL có thể cần lock mạnh cho `DROP COLUMN`; thời gian chờ lock và khả năng rollback của migration phải được cân nhắc.

**Xóa cột không phải lúc nào giải phóng dung lượng file ngay lập tức.** Trên một số engine, việc loại bỏ metadata của cột không đồng nghĩa tái cấu trúc toàn bộ dữ liệu vật lý tức thì; tối ưu dung lượng là một kế hoạch riêng.

### 9.2. Không nhầm rollback với khôi phục dữ liệu cũ

Trước contract, rollback thường có thể là **đổi đường đọc về trường cũ** và dừng rollout, miễn đồng bộ vẫn chính xác.

Sau `DROP COLUMN amount_cents`, chạy lại binary A0 có thể **không hoạt động**. Nếu dữ liệu mới đã vượt giới hạn INT, không có phép chuyển ngược 1-1 vào cột cũ. Vì vậy:

- Trước contract, phải xác định **điểm không còn rollback đơn giản**.
- Sau điểm đó, chiến lược có thể là **roll-forward** (sửa ứng dụng mới), hoặc migration khôi phục có phê duyệt từ backup/snapshot và dữ liệu phát sinh sau đó.
- Không hứa có thể hoàn nguyên nhanh chỉ bằng `ALTER TABLE ADD COLUMN amount_cents INTEGER`: thêm lại cột không tái tạo đầy đủ dữ liệu/hợp đồng đã mất.

## 10. Thứ tự deploy trong hệ rolling và nhiều phiên bản

Ở hệ có autoscaling/rolling deploy, trong vài phút hay vài giờ có thể đồng thời tồn tại **A0, A1 và A2**. Một cách tổ chức phát hành:

~~~mermaid
flowchart TD
    A["S0 + A0"] --> B["DB expand thành S1"]
    B --> C["Cơ chế sync tương thích writer cũ"]
    C --> D["Backfill và đối soát"]
    D --> E["A1 shadow-read / canary"]
    E --> F{"Các gate đã đạt?"}
    F -->|Chưa| G["Dừng rollout, sửa và retry"]
    G --> D
    F -->|Rồi| H["A2 đọc/ghi mới"]
    H --> I["Quan sát mọi consumer và rollback window"]
    I --> J{"Không còn phụ thuộc cũ?"}
    J -->|Chưa| I
    J -->|Có| K["S2 contract cột cũ"]
~~~

**Đừng phụ thuộc vào thứ tự khởi động pod theo cảm tính.** Nên có migration riêng với trạng thái rõ, feature flag hoặc capability flag nếu hữu ích, phép kiểm tra compatibility khi khởi động, và cơ chế ngăn deployment không tương thích.

### Một kế hoạch phát hành tối thiểu

| Phát hành | Schema | Ứng dụng | Kết quả mong đợi |
|---|---|---|---|
| R0 | S0 | A0 | Baseline được đo |
| R1 | S1 | A0 | Cột mới tồn tại; app cũ vẫn chạy |
| R2 | S1 | A0/A1 | Sync và backfill; không có mismatch tăng |
| R3 | S1 | A1/A2 | Đọc mới, đã kiểm thử rollback về cũ |
| R4 | S1 | A2 | Không còn phụ thuộc cũ |
| R5 | S2 | A2 | Dọn cấu trúc cũ có phê duyệt |

Khoảng cách giữa R4 và R5 có thể là **nhiều ngày hoặc lâu hơn** để chờ job định kỳ, consumer ngoài tổ chức và cửa sổ khôi phục đã được xác nhận. Không có “sau 24 giờ luôn được drop cột” áp dụng cho mọi hệ.

## 11. Đổi tên, tách và gộp trường: không phải lúc nào cũng có phép ánh xạ

### 11.1. Đổi tên thuần túy

Nếu `old_name` và `new_name` biểu diễn **cùng một khái niệm**, có thể dùng expand–migrate–contract giống ví dụ. Điều khó không nằm ở SQL rename mà ở các consumer dùng tên cũ.

**Tuy nhiên:** nếu DB có view tương thích hoặc API serializer ổn định độc lập với tên cột, phạm vi thay đổi có thể nhỏ hơn. Đừng tạo bridge không cần thiết nếu đã có cách bảo vệ hợp đồng.

### 11.2. Tách địa chỉ từ một chuỗi tự do

Nguồn:

~~~text
shipping_address_text = "Số 12, đường X, phường Y, TP Z"
~~~

Mô hình mới:

~~~text
shipping_street
shipping_ward
shipping_city
shipping_country
~~~

**Không được giả định** có thể parse chính xác mọi địa chỉ lịch sử. Có địa chỉ thiếu thành phần, viết tắt, đổi địa giới, chứa ghi chú giao hàng hoặc có nhiều định dạng.

Kế hoạch đúng:

1. Expand bằng trường/bảng mới với trạng thái **`unverified` / `needs_review`** khi cần.
2. Xác nhận **mục đích**: địa chỉ tại lúc đặt hay địa chỉ khách hiện hành? Đơn lịch sử không nên tự đổi theo hồ sơ khách.
3. Backfill bằng parser có độ tin cậy được đo, lưu trạng thái mapping và hàng đợi rà soát.
4. Không tự gán `country` mặc định hoặc xóa chuỗi gốc nếu thiếu thông tin.
5. Chỉ tăng `NOT NULL`/FK và bỏ cột cũ khi dữ liệu bắt buộc đã được xác minh hoặc có chính sách ngoại lệ.

Đây là thay đổi **ngữ nghĩa và cấu trúc**, không chỉ đổi tên cột.

### 11.3. Gộp hai trường thành một

Nếu hai hệ lưu `first_name` và `last_name`, gộp thành `display_name` có thể phục vụ hiển thị; nhưng không phải lúc nào **có thể tách lại chính xác** tên. Rollback từ biểu diễn gộp về hai trường cũ có thể mất thông tin. Cần xác định **mất tính nghịch đảo** trước khi contract.

### 11.4. Thay quan hệ một-nhiều thành nhiều-nhiều

Giả sử `employees.department_id` chỉ cho một phòng ban, nghiệp vụ mới cho nhiều phòng ban:

~~~text
employees(employee_id, department_id)  -- cũ

employee_departments(
    employee_id, department_id, effective_from, role
) -- mới
~~~

Trong giai đoạn expand, có thể tạo bảng liên kết mới và chuyển dữ liệu quan hệ cũ sang bảng này. Nhưng **cơ chế ghi ngược về một `department_id` cũ không thể diễn đạt nhiều phòng ban**. Do đó cần một **giai đoạn giới hạn tính năng**: không cho người dùng tạo nhiều quan hệ đồng thời cho đến khi toàn bộ writer/reader cũ đã ngừng, hoặc công bố chính sách rõ về “phòng ban chính” với thông tin phân biệt không thể suy lại từ cột cũ.

**Một thay đổi từ 1:N sang M:N thường là thay đổi hợp đồng nghiệp vụ**, không chỉ migration vật lý.

## 12. Tiến hóa bảng và dữ liệu phân tích theo cùng nguyên tắc

Expand–migrate–contract không chỉ áp dụng cho một cột OLTP.

### 12.1. Từ một bảng lớn sang hai bảng

Giả sử `customers` chứa dữ liệu hồ sơ chung và các tùy chọn thông báo ít liên quan. Khi muốn tách `customer_notification_preferences`:

- **Expand:** tạo bảng mới và khóa/FK phù hợp, giữ trường cũ.
- **Migrate:** sao chép dữ liệu lịch sử, đồng bộ thay đổi, xử lý trường hợp khách chưa có preference.
- **Read cutover:** truy vấn/ứng dụng mới đọc bảng mới, xử lý `0/1` row theo quy tắc.
- **Contract:** xóa trường cũ sau khi consumer đã đổi.

Lưu ý: cùng một customer có thể nhiều kênh/mục đích thông báo; grain bảng mới cần được xác định, không biến một cột boolean thành danh sách mà thiếu khóa `(customer_id,channel,purpose)` khi nghiệp vụ yêu cầu.

### 12.2. Từ fact cũ sang fact mới có grain khác

Data warehouse có `fact_orders` ở cấp đơn, nay cần `fact_order_lines` ở cấp dòng để phân tích sản phẩm:

- **Không** thể backfill dòng hàng chỉ bằng chia đều `order_total` nếu không có dữ liệu dòng nguồn.
- Cần nguồn `order_items`, giá tại thời điểm giao dịch, giảm giá, thuế/ship và mapping lịch sử.
- Hai fact có thể **cùng tồn tại**, phục vụ KPI ở các grain khác nhau; không nhất thiết “contract fact cấp đơn” nếu vẫn có nhu cầu.
- Đối soát \(\sum\text{lineAmount}\) với số tiền cấp đơn phải xét **những thành phần được tính trong mỗi KPI**.

**Thay đổi grain không đồng nghĩa rename bảng.** Cần khai báo lại khóa, phép đo và câu hỏi được phép trả lời.

### 12.3. SCD Type 2 và lịch sử dimension

Khi từ dimension chỉ có trạng thái hiện tại (Type 1) sang SCD Type 2:

1. Expand thêm `valid_from`, `valid_to`, surrogate key/version.
2. Xây lịch sử **từ nguồn sự kiện đáng tin cậy** nếu có; nếu không, đừng bịa lịch sử quá khứ không tồn tại.
3. Chuyển fact sang khóa phiên bản đúng thời điểm nghiệp vụ.
4. Kiểm tra không có hai khoảng hiệu lực chồng lấn cho cùng business key.
5. Chuyển báo cáo từ “theo thuộc tính hiện tại” sang “tại thời điểm sự kiện” **chỉ khi KPI thực sự đổi định nghĩa**.

Không phải lúc nào cũng nên bỏ dimension Type 1; nó có thể vẫn được dùng để trả lời câu hỏi “theo phân loại hiện tại”.

## 13. API và sự kiện: schema DB không phải hợp đồng duy nhất

Một sai lầm là hoàn thành migration DB, sau đó đổi ngay JSON response/event payload theo tên cột mới.

~~~text
DB nội bộ thay đổi
     |
     +--> API DTO / GraphQL schema
     +--> Integration event schema
     +--> CDC / ETL contract
     +--> BI semantic layer
     +--> Cache / search document
~~~

Các thành phần này có thể có **chu kỳ phát hành và người sở hữu khác nhau**. Nếu API public vẫn cần `amountCents`, ứng dụng có thể tiếp tục ánh xạ từ `amount_minor` trong DB sang trường API cũ cho đến khi consumer đổi. Không buộc API rename chỉ vì DB rename.

### 13.1. Expand contract cho API

Ví dụ:

~~~json
{
  "orderId": "ord_42",
  "amountCents": 1200,
  "amountMinor": "1200",
  "currency": "USD"
}
~~~

Đây chỉ là **một phương án chuyển tiếp**: API cũ còn field `amountCents`; API mới có field `amountMinor` dạng string tránh phụ thuộc giới hạn số nguyên của các consumer JSON. Không nên triển khai nếu chính sách bảo mật/độ phức tạp không chấp nhận. Hợp đồng phải nói rõ **đơn vị, giới hạn giá trị và quy tắc chọn field**, tránh consumer cộng hai field như hai khoản khác nhau.

Trong nhiều trường hợp, tốt hơn là **giữ API v1 nguyên trạng** và phát v2 rõ ràng, thay vì thêm field cùng nghĩa vào một response không có quy tắc.

### 13.2. Expand contract cho integration event

Nếu event `OrderConfirmed v1` chứa trường tiền kiểu `INTEGER`, đổi sang `BIGINT` hoặc đổi đơn vị có thể phá consumer. Các cách:

- Phát **event schema v2** với field/kiểu mới, có tài liệu mapping.
- Giữ v1 trong thời gian chuyển đổi nếu cần; xác định cách tránh consumer **xử lý cả v1 và v2 như hai sự kiện nghiệp vụ khác nhau**.
- Thiết kế consumer/upcaster đọc được **event lịch sử v1** khi replay.
- Phân biệt `schemaVersion` của event với `aggregateVersion` của đơn.

**Không giả định thêm optional field luôn an toàn.** Consumer strict, protobuf schema registry, generated models hoặc exhaustive enum handling có thể có quy tắc khác nhau. Phải kiểm tra **consumer-driven contract test** và chiều tương thích thực tế.

### 13.3. CDC và read model

CDC đọc thay đổi bảng `orders` có thể thấy cột mới xuất hiện hoặc cột cũ biến mất. Nếu consumer phụ thuộc vào row-level schema, đây là thay đổi **hợp đồng tích hợp** ngay cả khi API không đổi.

Giải pháp có thể là:

- Lớp mapping ổn định từ nguồn CDC sang event công bố.
- Outbox mang payload theo version rõ.
- Nâng cấp schema registry/connector theo đúng thứ tự.
- Backfill read model mới theo snapshot có mốc, sau đó áp dụng CDC từ một **offset/watermark** đáng tin cậy để không mất cập nhật giữa snapshot và stream.

Không thể chỉ “copy bảng một lần rồi bật CDC” mà không quản lý **ranh giới thời gian và offset**; thay đổi trong lúc copy có thể bị bỏ sót hoặc áp dụng hai lần.

## 14. Backfill dữ liệu lớn trong hệ đang hoạt động

### 14.1. Giới hạn tải và transaction

Một backfill an toàn thường có:

- Batch size được thử nghiệm theo I/O, CPU, WAL/redo, lock và replication lag.
- Chạy có **rate limit** và cửa sổ giảm tải khi cần.
- `lock_timeout` / `statement_timeout` phù hợp trong PostgreSQL; không đặt ngưỡng tùy tiện làm hủy job trong khi chưa xử lý retry.
- Checkpoint tiến độ hoặc bộ chọn idempotent để resume.
- Theo dõi dead tuples/bloat, vacuum/compaction và tác động đến backup.
- Khả năng tạm dừng khi **latency hoặc lag vượt ngưỡng**.

Đừng tính “500 hàng mỗi lô chắc chắn an toàn”. Một dòng có payload lớn, trigger nhiều bảng hoặc index phức tạp có thể tốn tài nguyên hơn hàng trăm dòng nhỏ.

### 14.2. Cursor hay điều kiện chưa chuyển?

Hai phương pháp phổ biến:

| Chiến lược | Lợi ích | Rủi ro |
|---|---|---|
| Quét theo `order_id > last_id` | Tiến triển đơn giản, có checkpoint | Dòng ID thấp được tạo/đổi sau khi cursor đi qua có thể bị bỏ sót nếu thiếu sync |
| Chọn `WHERE new_column IS NULL` | Tự tìm những dòng chưa chuyển; retry tự nhiên | Có thể scan tốn kém, cần index phù hợp; không phát hiện giá trị **đã có nhưng sai** |
| Snapshot + CDC | Có thể giảm ảnh hưởng khi chuyển giữa kho | Cần giữ offset, xử lý trùng/sai thứ tự và consistency |

Với `WHERE amount_minor IS NULL`, có thể cân nhắc chỉ mục tạm cho khối lượng lớn:

~~~sql
-- PostgreSQL: phải chạy ngoài transaction block.
CREATE INDEX CONCURRENTLY idx_orders_amount_missing
    ON orders (order_id)
    WHERE amount_minor IS NULL;
~~~

Sau khi backfill hoàn tất, chỉ mục này thường không còn cần. Dọn nó bằng một lần thay đổi riêng:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS idx_orders_amount_missing;
~~~

**Không dùng `CREATE INDEX CONCURRENTLY` hoặc `DROP INDEX CONCURRENTLY` bên trong một transaction block thông thường** trên PostgreSQL. Chỉ mục tạo concurrent có thể thất bại/để lại trạng thái cần xử lý; phải kiểm tra tình trạng thực trước khi retry. Có thể không cần chỉ mục tạm nếu bảng nhỏ hoặc truy vấn theo phân vùng hiệu quả hơn.

### 14.3. Dữ liệu đến muộn và cập nhật cạnh tranh

Đối với hệ có event hoặc outbox:

- Một bản ghi được sửa **sau khi đã backfill** phải cập nhật cấu trúc mới.
- Một sự kiện cũ đến muộn phải được xử lý theo **version/sequence/ngữ nghĩa thời điểm**, không ghi đè dữ liệu mới vô điều kiện.
- Nếu cùng một dòng có hai update cạnh tranh, dùng khóa, optimistic version hoặc transaction phù hợp.
- Job replay cần **idempotent**: chạy lại không tăng số đơn hoặc nhân tiền.

Lệnh `UPDATE ... WHERE amount_minor IS NULL` chỉ giải quyết **dòng chưa có giá trị mới**; nó **không** sửa trường hợp cột mới đã bị ghi sai. Vì vậy cần hai vòng riêng: **chuyển dữ liệu chưa có** và **đối soát sửa sai lệch có chứng cứ**.

## 15. Migration liên quan constraint, chỉ mục và lock

Một số kiểu thay đổi cần kế hoạch kỹ thuật đặc thù:

| Thao tác | Rủi ro | Cách giảm rủi ro |
|---|---|---|
| Thêm cột nullable | Lock DDL, app `SELECT *` có thể thay shape | Deploy expand trước, đo lock và client |
| Thêm cột có default/giá trị sinh | Có thể rewrite/lock tùy engine/version/expression | Kiểm tra phiên bản DB và kế hoạch vật lý |
| Tạo index trên bảng lớn | I/O, lock, replication lag | Dùng cơ chế online/concurrent phù hợp |
| Thêm `NOT NULL` | Quét dữ liệu, lỗi với row NULL | Backfill và validate trước |
| Thêm FK | Kiểm tra tất cả quan hệ, lock và dữ liệu mồ côi | Index và `NOT VALID`/validate nếu DB hỗ trợ |
| Đổi loại khóa chính | FK, index, replication, application IDs | Song song khóa cũ/mới, mapping và nhiều pha |
| Đổi partition key | Có thể di chuyển nhiều dữ liệu | Bảng/partition mới và backfill/CDC có kiểm soát |
| Drop column/table | App cũ hỏng, rollback khó | Chỉ contract sau khi kiểm kê và đạt gate |

**DDL “online” không đồng nghĩa “không có lock, không có I/O và không có downtime trong mọi tình huống”.** Cần đo trên DBMS/phiên bản thực, mô hình transaction, index và tải gần sản xuất.

### Thiết kế thứ tự constraint

Khi thêm khóa ngoại hoặc uniqueness:

1. Làm sạch dữ liệu và xác nhận rule nghiệp vụ.
2. Chuẩn bị index phù hợp nếu cần.
3. Bắt đầu cưỡng chế đối với ghi mới.
4. Xác minh dữ liệu lịch sử.
5. Mở rộng phạm vi chuyển đổi và cuối cùng loại logic cũ.

Nếu người dùng có thể gửi dữ liệu không hợp lệ trong quá trình backfill, cần cơ chế chặn **trước khi** job kiểm tra xong; nếu không, migration có thể luôn chạy sau một mục tiêu di động.

## 16. Gate chuyển pha: đo gì để được phép tiếp tục?

Một kế hoạch migration nên quy định **điều kiện đạt/không đạt**, không chỉ có ngày dự kiến drop cột.

| Gate | Bằng chứng / chỉ số | Nếu chưa đạt |
|---|---|---|
| **Expand tương thích** | A0 đọc/ghi thành công trên S1; schema deploy sạch | Dừng rollout app mới |
| **Writer sync** | Không có writer bypass, sai lệch mới không tăng | Sửa bridge/app writer |
| **Backfill** | Số dòng NULL giảm; checkpoint tiến triển | Điều chỉnh batch/index, xử lý lỗi |
| **Correctness** | Mismatch cấp dòng = 0 hoặc ngoại lệ đã được giải trình | Không chuyển read |
| **Canary** | Kết quả business, latency, error rate đạt SLO | Quay đọc về cũ, điều tra |
| **New-only** | Toàn bộ consumer đang dùng model mới, không còn truy cập cũ | Chưa contract |
| **Recovery** | Restore/replay/backfill đã diễn tập, rollback/roll-forward rõ | Hoãn contract |

### Một bộ metric vận hành minh họa

~~~text
migration_rows_total
migration_rows_remaining
migration_rows_processed_per_minute
migration_mismatch_rows
migration_backfill_errors_total
migration_batch_duration_seconds
migration_db_lock_wait_seconds
migration_replication_lag_seconds
migration_old_column_reads
migration_old_column_writes
migration_new_read_errors
migration_cutover_rollback_count
~~~

Không phải mọi hệ có thể đếm chính xác từng lần đọc một cột ở tầng DB. Có thể cần **instrument ứng dụng, phân tích truy vấn, metadata dependency hoặc log có chọn lọc**. Một chỉ số `old_column_reads=0` trong vài phút không đủ chứng minh job chạy theo tháng đã được chuyển.

### Đối soát phạm vi có ý nghĩa

Ngoài sai khác theo dòng:

- Đối soát `COUNT(*)` theo tenant/ngày/partition.
- Đối soát tổng tiền cùng đơn vị tiền và cùng định nghĩa KPI.
- Kiểm tra khóa, FK, uniqueness và trường hợp `NULL`.
- Thử các giá trị biên: 0, cực lớn, dữ liệu cũ, giá trị bị sửa sau backfill.
- Kiểm tra những consumer ít sử dụng: xuất báo cáo cuối tháng, restore, công cụ admin, email job.

Nên có **bằng chứng đã thử** chứ không chỉ checkbox “done”.

## 17. Rollback, roll-forward và điểm không thể quay lại dễ dàng

### Trước contract

Nếu cột cũ luôn được đồng bộ đúng, khi canary sai có thể:

- Đặt feature flag cho đường đọc quay về `amount_cents`.
- Dừng rollout A2, giữ schema S1 và fix logic mapping.
- Tiếp tục xử lý sai khác/backfill trong khi người dùng đọc cấu trúc cũ.

**Không tự rollback schema expand** khi app mới đã tham chiếu cột mới; có thể làm lỗi nặng hơn.

### Sau contract

Đã xóa `amount_cents`:

- Binary A0 không còn tương thích với S2.
- Các giá trị mới có thể vượt phạm vi `INTEGER`, không thể ghi lại chính xác vào cột cũ.
- Restore toàn DB có thể làm mất **giao dịch sau snapshot** nếu không có quy trình phục hồi/replay.

Vì vậy phương án thường là **roll-forward**: sửa A2/S2. Nếu thật sự cần khôi phục dữ liệu cũ, phải có kế hoạch **reversible migration với dữ liệu nguồn còn đủ**, thời gian dừng, snapshot và cách reconcile các giao dịch mới. Điều kiện này phải được chuẩn bị **trước khi contract**, không thể bù bằng lời hứa sau khi lỗi.

### Migration dữ liệu không khả nghịch

Ví dụ thay `free_text_address` bằng địa chỉ cấu trúc rồi xóa bản gốc, nhưng parser đã làm mất thông tin “gần cổng sau, gọi trước khi giao”. Không có SQL rename nào tái tạo lại nội dung đó. Đây là **mất thông tin**, khác hẳn đổi kiểu `INTEGER` sang `BIGINT`.

Một quyết định contract phải đánh giá:

\[
\text{Có thể khôi phục biểu diễn cũ từ biểu diễn mới không?}
\]

Nếu không, cần **giữ bản gốc phù hợp chính sách**, phê duyệt mất dữ liệu, hoặc thay đổi kế hoạch.

## 18. So sánh trong các mô hình dữ liệu khác nhau

| Mô hình | Expand | Migrate | Contract | Điểm đặc biệt |
|---|---|---|---|---|
| **Quan hệ** | Thêm cột/bảng/FK/index | Dual-write, backfill, đổi JOIN | Drop cột/bảng cũ | DDL lock, constraints, MVCC, transaction |
| **Document** | Thêm trường mới/schema version | Dual-read/mapping, backfill document | Bỏ trường cũ sau khi reader đổi | Document cũ/mới có thể cùng tồn tại lâu |
| **Đồ thị** | Thêm loại node/edge/property | Chuyển quan hệ cũ sang kiểu mới | Xóa edge/property cũ | Mất/nhân đường đi, semantics quan hệ thay đổi |
| **Phân tích** | Tạo fact/dimension mới, version metric | Backfill theo grain/time, chuyển dashboard | Retire mart/view cũ | Lịch sử, SCD, distinct, fanout và chốt kỳ |
| **Event streaming** | Công bố schema/event v2 song song | Consumer/upcaster, replay, offset cutover | Dừng v1 theo chính sách | Event v1 tồn tại trong log/backup rất lâu |

### Với document

Nếu bản cũ:

~~~json
{ "orderId": "O1", "amountCents": 1200 }
~~~

và bản mới:

~~~json
{ "orderId": "O1", "amountMinor": "1200", "schemaVersion": 2 }
~~~

thì reader trong giai đoạn chuyển phải hiểu **cả hai phiên bản**, hoặc một job backfill được bảo đảm xong trước khi reader chỉ đọc v2. Không giả định mọi document được update đồng thời. Một document cũ có thể được ghi lại từ cache/backup sau khi đã chuyển nếu thiếu version check.

### Với đồ thị

Từ cạnh `(User)-[:MEMBER_OF]->(Team)` sang mô hình quan hệ có thời gian `Membership`, phải xác định:

- Một cạnh cũ tương ứng bao nhiêu bản ghi membership?
- Có thể suy ra `effective_from`/role từ dữ liệu cũ không?
- Trong thời gian hai biểu diễn cùng tồn tại, truy vấn có bị **đếm đôi quan hệ** không?
- Trước khi xóa cạnh cũ, các truy vấn đường đi và quyền truy cập đã đổi chưa?

Expand mà không thay traversal query có thể làm kết quả đồ thị sai, dù các node/edge đều hợp lệ.

### Với analytics

Một dashboard có metric `totalRevenue` tính theo fact cũ không được tự đổi sang fact mới có **định nghĩa doanh thu khác** mà vẫn giữ nhãn KPI. Cần chạy hai metric song song, đối soát theo ngày/tenant và công bố thời điểm chuyển đổi. Nếu grain thay đổi, `SUM`, `COUNT(DISTINCT)` và join dimension phải được thiết kế lại.

## 19. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao nguy hiểm? | Hướng xử lý |
|---|---|---|
| “Đổi tên cột nhanh nên luôn an toàn” | App cũ, ETL hoặc view còn dùng tên cũ | Expand trước, kiểm kê consumer |
| “Cột mới NULL được thì không cần đồng bộ” | Backfill xong A0 có thể ghi giá trị mới chỉ vào cột cũ | Bridge/dual-write trước chuyển đọc |
| “Chỉ cần COALESCE là tránh lỗi” | Cột mới có giá trị **cũ nhưng không NULL** | Đối soát mismatch và đồng bộ đúng |
| “Dual-write sang hai DB là transaction nguyên tử” | Một phía thành công, một phía thất bại | Outbox/CDC, idempotency, reconciliation |
| “Đổi INTEGER thành BIGINT là xong” | DTO/JSON/client có thể vẫn giới hạn INT | Ma trận tương thích toàn hệ |
| “Backfill một lần là đủ” | Có cập nhật cạnh tranh và event đến muộn | Sync, replay và kiểm tra sau backfill |
| “Tổng tiền khớp chứng minh từng dòng khớp” | Sai số có thể triệt tiêu | Kiểm tra cấp dòng và theo partition |
| “Thêm NOT NULL trước rồi cập nhật sau” | Dòng lịch sử NULL gây lỗi | Chuyển dữ liệu trước, validate rồi cưỡng chế |
| “CREATE INDEX CONCURRENTLY không có tác động” | Vẫn tốn CPU/I/O và có thể lỗi | Đo tiến độ, load, index state |
| “App mới đã deploy thì drop cột cũ” | Cron/BI/mobile/restore còn phụ thuộc | Kiểm kê và gate contract |
| “Tắt tính năng mới là rollback được schema” | Đã drop cột hoặc mất thông tin | Xác định điểm không quay lại |
| “Tách trường free text luôn tự động 100%” | Dữ liệu lịch sử đa nghĩa/thiếu | Mapping, confidence, review |
| “Dữ liệu mới là source of truth ngay sau ADD COLUMN” | Chưa backfill/đồng bộ đủ | Chỉ cutover sau correctness gate |
| “Sửa DB schema xong là API/event cũng phải rename” | Phá hợp đồng người tiêu thụ | Mapping và version độc lập |
| “Shadow read không cần giữ bí mật dữ liệu” | Log đối chiếu có thể lộ PII | Chỉ log metric/mã tham chiếu tối thiểu |
| “Mọi migration phải dùng trigger” | Trigger có overhead và logic phức tạp | Chọn app dual-write hoặc phương án thích hợp |

## 20. Bài luyện tập có lời giải

### Bài 1 — Xác định các pha

Hệ có `orders.amount_cents`; nhóm muốn chuyển sang `amount_minor`. Hãy đặt việc thêm cột, backfill và xóa cột cũ vào ba pha.

**Lời giải:** **Expand:** thêm `amount_minor` nullable, giữ cột cũ và cơ chế đồng bộ. **Migrate:** backfill, đối soát, triển khai read/write mới dần. **Contract:** gỡ sync và xóa `amount_cents` sau khi đã xác nhận không còn consumer cũ.

### Bài 2 — Vì sao COALESCE vẫn sai?

Trước backfill: `amount_cents=1000, amount_minor=NULL`. Backfill xong hai cột đều 1000. Ứng dụng cũ ghi `amount_cents=1200` và không cập nhật cột mới. `COALESCE(amount_minor,amount_cents)` trả gì?

**Lời giải:** Trả **1000**, là giá trị **sai**, vì `amount_minor` không NULL nhưng đã cũ. Cần đồng bộ mọi writer trước khi đổi đường đọc; fallback NULL không giải quyết stale value.

### Bài 3 — Ma trận tương thích

A0 chỉ đọc `amount_cents`, A2 chỉ đọc `amount_minor`. S0 chỉ có cột cũ, S2 chỉ có cột mới. A0 chạy với S2 được không? A2 chạy với S0 được không?

**Lời giải:** **Không** trong cả hai trường hợp theo giả định. Cần pha S1 có cả hai, deploy đúng thứ tự và chỉ contract khi A0 đã ngừng.

### Bài 4 — Backfill bị gián đoạn

Job cập nhật 500 dòng mỗi transaction, dùng `WHERE amount_minor IS NULL`. Một transaction bị kill trước commit. Làm sao tiếp tục?

**Lời giải:** Transaction chưa commit rollback; chạy lại batch sẽ chọn các dòng vẫn NULL. Cần giám sát backlog, retry và giới hạn tốc độ. Idempotency không thay thế việc kiểm tra giá trị mới **đã có nhưng sai**.

### Bài 5 — Chuyển BIGINT quá sớm

A0 còn dùng `int` 32-bit; A2 muốn ghi `amount_minor=3.000.000.000`. Hệ vẫn đồng bộ sang `amount_cents INTEGER`. Có được phép không?

**Lời giải:** **Không** nếu phải bảo toàn đồng bộ với A0; giá trị vượt tối đa 2.147.483.647 của signed 32-bit integer. Phải ngừng phụ thuộc legacy và nâng cấp DTO/API/ETL trước khi bỏ giới hạn.

### Bài 6 — Xác minh NULL và mismatch

Sau backfill, `COUNT(*) WHERE amount_minor IS NULL` trả 0 nhưng có 10 dòng `amount_minor <> amount_cents`. Đã đạt gate correctness chưa?

**Lời giải:** **Chưa**. Không có NULL chỉ chứng minh cột mới đã được điền; không chứng minh đúng. Dùng đối soát từng dòng như `IS DISTINCT FROM` và điều tra nguyên nhân trước read cutover.

### Bài 7 — Tách địa chỉ

Từ chuỗi địa chỉ tự do, nhóm muốn có `street,ward,city,country` và thêm `NOT NULL` ngay sau chạy parser. 5% địa chỉ không parse đáng tin cậy. Làm gì?

**Lời giải:** Giữ thông tin gốc theo chính sách, đánh dấu chưa xác minh và có quy trình review/bổ sung. Không tự tạo giá trị giả hoặc cưỡng chế `NOT NULL` khi các trường bắt buộc chưa có căn cứ.

### Bài 8 — Từ một phòng ban sang nhiều phòng ban

Nguồn `employees.department_id` chỉ hỗ trợ một giá trị. Mô hình mới cho phép nhiều phòng ban trong bảng liên kết. Có thể bật tính năng tạo nhiều phòng ban khi ứng dụng cũ vẫn chỉ đọc một `department_id` không?

**Lời giải:** Không mặc nhiên. Một cột cũ không biểu diễn đầy đủ quan hệ nhiều-nhiều; cần giới hạn tính năng cho đến khi client cũ được nâng cấp, hoặc định nghĩa “phòng ban chính” có ranh giới rõ và không gây mất ngữ nghĩa.

### Bài 9 — Gộp hai fact

Fact dòng hàng có ba dòng/đơn; fact thanh toán có hai giao dịch/đơn. Nhóm mới JOIN trực tiếp hai fact để đối soát trước contract fact cũ. Điều gì xảy ra?

**Lời giải:** Có thể tạo **6 dòng** và nhân số tiền. Tổng hợp mỗi fact về **grain cấp đơn** rồi JOIN. Migration analytics phải bảo vệ grain và định nghĩa measure, không chỉ tên cột.

### Bài 10 — API contract và DB refactor

DB đã đổi `amount_cents` thành `amount_minor`, nhưng nhiều đối tác còn đọc JSON `amountCents`. Có bắt buộc đổi JSON ngay không?

**Lời giải:** Không. Tầng API có thể tiếp tục ánh xạ sang hợp đồng v1 còn hiệu lực nếu giá trị, đơn vị và giới hạn vẫn tương thích. Nếu cần mở rộng phạm vi hoặc đổi kiểu, phát v2/chiến lược tương thích có kiểm chứng.

### Bài 11 — Phụ thuộc ít chạy

Mọi request production không còn đọc cột cũ trong một tuần. Tuy nhiên báo cáo đối soát cuối quý còn dùng `amount_cents`. Có được contract không?

**Lời giải:** **Không** nếu báo cáo vẫn cần chạy. Metric request runtime không quan sát đủ job hiếm. Phải kiểm kê consumer, nâng cấp báo cáo, kiểm thử và có bằng chứng nó không còn phụ thuộc.

### Bài 12 — Rollback sau khi drop

Đã drop cột `amount_cents`; cột mới chứa một số giá trị vượt phạm vi INTEGER. Người vận hành muốn khởi động binary A0 và thêm lại `amount_cents` để rollback.

**Lời giải:** Không phải rollback an toàn. A0 không hiểu schema mới; dữ liệu vượt giới hạn cũ không khôi phục nguyên vẹn. Cần phương án roll-forward hoặc khôi phục được phê duyệt, có kiểm soát dữ liệu phát sinh sau snapshot.

## 21. Checklist trước khi thực hiện expand–migrate–contract

- [ ] Đã xác nhận **ngữ nghĩa nghiệp vụ** của trường/bảng cũ và mới, đơn vị tiền, thời gian, grain.
- [ ] Đã vẽ **ma trận tương thích** schema/app/API/event/ETL/BI và thứ tự deploy.
- [ ] Đã kiểm kê cả consumer hiếm chạy, mobile, batch, backup/restore và CDC.
- [ ] Expand **không phá** app cũ; không sớm drop/rename hoặc thêm `NOT NULL` không phù hợp.
- [ ] Đã chọn một cơ chế đồng bộ ghi rõ ràng: **app dual-write, DB trigger hoặc outbox/CDC có đối soát**.
- [ ] Đã chứng minh **không có stale non-NULL** khi dùng fallback read.
- [ ] Dữ liệu mới và cũ có khóa, namespace, ràng buộc và lịch sử đúng phạm vi.
- [ ] Backfill theo batch có retry/idempotency, giới hạn tải, checkpoint và xử lý dữ liệu đến muộn.
- [ ] Có phép kiểm tra NULL, mismatch cấp dòng, số dòng, tổng theo phạm vi và giá trị biên.
- [ ] Có kế hoạch tăng dần `CHECK`, `NOT NULL`, FK và index theo khả năng DBMS thực tế.
- [ ] Canary/shadow read có số liệu về correctness, latency, error và bảo vệ dữ liệu log.
- [ ] Đã theo dõi replication lag, WAL/redo, lock wait, CPU/I/O và bloat khi chuyển.
- [ ] API/event contract được quản lý **độc lập với tên cột DB**, có schema version và consumer tests.
- [ ] Đã xác nhận không còn writer/reader cũ trước khi **contract**.
- [ ] Đã xác định **điểm không rollback đơn giản**, phương án roll-forward và diễn tập restore/replay.
- [ ] Đã có gate rõ cho từng pha; không triển khai chỉ vì “đến hạn dọn cột”.
- [ ] Các thay đổi mất thông tin/không thể ánh xạ đều có xử lý ngoại lệ và phê duyệt nghiệp vụ.

**Ghi nhớ:** **Expand trước để cho phép cùng tồn tại, migrate theo lô có kiểm chứng để chuyển dữ liệu và lưu lượng, rồi contract chỉ khi không còn phụ thuộc cũ.** Migration không chỉ là câu `ALTER TABLE`, mà là một tiến trình phối hợp **schema, ứng dụng, dữ liệu, API/event, vận hành và khả năng phục hồi**. Thiết kế tốt giữ đúng ngữ nghĩa và khóa ngay trong giai đoạn hai biểu diễn cùng tồn tại, đồng thời đặt **bằng chứng đối soát và ma trận tương thích** làm điều kiện trước khi loại bỏ cấu trúc cũ.
