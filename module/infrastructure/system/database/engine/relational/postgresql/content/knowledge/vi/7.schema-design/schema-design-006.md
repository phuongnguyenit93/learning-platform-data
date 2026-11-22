# Thiết kế dữ liệu thời gian, lịch sử và nhật ký thay đổi

Trong ứng dụng thực tế, dữ liệu không chỉ có **giá trị hiện tại**. Giá bán có thể thay đổi theo ngày; địa chỉ giao hàng có thể được cập nhật sau khi đơn đã tạo; một hợp đồng có hiệu lực trong một khoảng thời gian; và khi xảy ra khiếu nại, hệ thống cần biết **trước đây dữ liệu là gì, thay đổi khi nào, do ai và vì sao**. Nếu thiết kế bảng chỉ lưu giá trị mới nhất, những câu hỏi đó có thể không còn trả lời được.

PostgreSQL hỗ trợ nhiều công cụ để mô hình hóa dữ liệu theo thời gian: `date`, `timestamp`, `timestamptz`, `interval`, **range types** như `daterange` và `tstzrange`, ràng buộc `EXCLUDE`, transaction, trigger, `jsonb`, partitioning và cơ chế đọc thay đổi từ WAL. Nhưng không có một kiểu bảng duy nhất giải quyết mọi yêu cầu lịch sử. Trước tiên phải xác định đang lưu **thời gian hiệu lực nghiệp vụ**, **thời gian hệ thống ghi nhận**, **thời điểm sự kiện xảy ra**, hay **nhật ký thao tác**.

Bài học này giúp bạn:

- Chọn kiểu dữ liệu thời gian và xử lý múi giờ nhất quán.
- Thiết kế bảng trạng thái hiện tại, bảng phiên bản lịch sử và truy vấn **as-of**.
- Ngăn các khoảng hiệu lực chồng lấn bằng `tstzrange` và `EXCLUDE USING gist`.
- Phân biệt lịch sử dữ liệu với **audit log**, event log, event sourcing và **outbox**.
- Ghi lịch sử bằng ứng dụng hoặc trigger trong cùng transaction.
- Thiết kế chỉ mục, partition, chính sách lưu giữ và quy trình sửa dữ liệu quá khứ.
- Xử lý đồng thời, ghi sự kiện đến muộn và các rủi ro bảo mật của nhật ký thay đổi.

> Các ví dụ SQL dành cho **PostgreSQL trong database thử nghiệm**. Những ngày giờ, giá tiền và tên đối tượng là minh họa, không phải dữ liệu thực. Các ràng buộc, chính sách lịch sử và xóa dữ liệu phải được quyết định theo nghiệp vụ, pháp lý và yêu cầu vận hành trước khi triển khai production.

## 1. Bốn câu hỏi về thời gian cần phân biệt

Một hàng có thể có nhiều mốc thời gian với ý nghĩa khác nhau:

| Mốc | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| **Thời điểm sự kiện** (*event time*) | Sự kiện thực tế xảy ra khi nào? | Cảm biến ghi nhiệt độ lúc 09:00. |
| **Thời điểm tiếp nhận** (*ingestion/recorded time*) | PostgreSQL hoặc hệ thống nhận/ghi sự kiện lúc nào? | Dữ liệu mạng gửi chậm, đến server lúc 09:06. |
| **Thời gian hiệu lực** (*valid time*) | Giá trị này có hiệu lực trong nghiệp vụ từ lúc nào đến lúc nào? | Giá mới áp dụng từ 00:00 ngày 01/12. |
| **Thời gian hệ thống biết hoặc lưu phiên bản** (*system/transaction time*) | Hệ thống ghi nhận sự thật này ở thời điểm nào? | Ngày 14/11 mới biết một mức giá hiệu lực từ 01/11. |

Chúng có thể giống nhau trong trường hợp đơn giản, nhưng **không nên mặc định chúng luôn trùng nhau**.

Ví dụ:

```text
01/11         10/11           14/11             01/12
  │             │               │                 │
  ├─────────────┴───────────────┼─────────────────┤
  │ Giá 100 có hiệu lực từ 01/11 │                 │
  │                             │ Ghi nhận sửa lại:
  │                             │ giá thực ra là 120
  │                             │ từ 01/11
  │                                               │
  └───────────────────────────────────────────────┘

Thời gian hiệu lực của bản sửa: 01/11
Thời gian hệ thống nhận bản sửa: 14/11
```

Nếu chỉ có một cột `updated_at`, bạn không thể phân biệt **“giá có hiệu lực từ ngày nào”** với **“ngày nào công ty phát hiện và sửa giá”**.

### Xác định câu hỏi nghiệp vụ trước khi chọn bảng

Hãy hỏi:

1. Có cần biết **trạng thái tại một thời điểm quá khứ** không?
2. Có cần **lập lịch thay đổi trong tương lai** không?
3. Có cần biết **ai sửa, lý do và request nào tạo thay đổi** không?
4. Có cho phép **sửa hồi tố** một quyết định đã có hiệu lực không?
5. Có cần phục dựng **hệ thống đã tin điều gì tại thời điểm trước đây**, kể cả khi sau đó có bản đính chính?
6. Lịch sử cần lưu trong bao lâu, và có yêu cầu chống sửa/xóa không?

Câu trả lời sẽ quyết định dùng cột thời gian đơn giản, bảng lịch sử một chiều, mô hình **bitemporal**, hay audit/event log riêng.

## 2. Các kiểu dữ liệu thời gian của PostgreSQL

PostgreSQL có các kiểu chính:

| Kiểu | Ý nghĩa | Khi nên cân nhắc |
|---|---|---|
| `date` | Ngày theo lịch, không có giờ hoặc múi giờ. | Ngày sinh, ngày nghỉ, ngày bắt đầu chính sách theo lịch. |
| `time without time zone` | Giờ trong ngày, không mang múi giờ. | Giờ mở cửa theo lịch địa phương, khi có ngữ cảnh vùng riêng. |
| `timestamp without time zone` | Ngày và giờ dạng **local wall time**, không gắn offset/time zone. | Lịch theo giờ địa phương khi vùng được lưu riêng hoặc dữ liệu không biểu diễn một thời điểm tuyệt đối. |
| `timestamp with time zone` / `timestamptz` | Một thời điểm cụ thể trên trục thời gian; PostgreSQL chuẩn hóa nội bộ và hiển thị theo time zone phiên. | `created_at`, `occurred_at`, `valid_from` khi cần thời điểm chính xác. |
| `interval` | Khoảng thời gian có thành phần tháng, ngày và thời gian. | Thời lượng, thời gian chờ, cộng/trừ lịch. |
| `daterange`, `tsrange`, `tstzrange` | Khoảng giá trị ngày hoặc timestamp. | Thời gian hiệu lực, lịch đặt chỗ, kiểm tra giao nhau. |

Ví dụ:

```sql
CREATE TABLE temporal_type_examples (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    business_date DATE NOT NULL,
    local_appointment TIMESTAMP WITHOUT TIME ZONE,
    event_instant TIMESTAMPTZ NOT NULL,
    duration INTERVAL
);
```

### TIMESTAMPTZ không lưu tên múi giờ gốc

Tên `timestamp with time zone` dễ gây hiểu lầm: PostgreSQL dùng thông tin offset/time zone của input để xác định **thời điểm tuyệt đối**, rồi khi query hiển thị theo `TimeZone` của session. Nó **không lưu riêng chuỗi vùng** như `Asia/Ho_Chi_Minh` đi kèm mỗi giá trị.

Hai literal sau mô tả cùng một thời điểm:

```sql
SELECT
    TIMESTAMPTZ '2026-11-14 09:00:00+07'
      = TIMESTAMPTZ '2026-11-14 02:00:00+00'
      AS same_instant;
-- true
```

Nếu nghiệp vụ cần biết người dùng **đã chọn múi giờ địa lý nào**, ví dụ `Europe/Berlin` để tính lịch theo quy tắc DST tương lai, hãy lưu **IANA time-zone identifier** riêng, thay vì chỉ lưu offset `+01:00`.

## 3. Thiết kế múi giờ: thời điểm tuyệt đối và giờ theo lịch

Một nguyên tắc hữu ích:

- **Sự kiện đã xảy ra tại một thời điểm cụ thể:** ưu tiên `timestamptz`.
- **Quy tắc theo ngày địa phương:** lưu `date` và vùng giờ nghiệp vụ khi cần.
- **Cuộc hẹn theo đồng hồ ở vùng nào đó:** có thể cần cả local date/time và tên time zone, cùng quy tắc xử lý thời điểm không tồn tại hoặc lặp lại vì DST.

Thử quan sát:

```sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-11-14 02:00:00+00' AS local_display;

SET TIME ZONE 'UTC';

SELECT TIMESTAMPTZ '2026-11-14 02:00:00+00' AS utc_display;
```

Giá trị là **cùng một instant**, nhưng cách hiển thị thay đổi. Sau ví dụ, trả cấu hình về giá trị phiên mặc định nếu cần:

```sql
RESET TIME ZONE;
```

### AT TIME ZONE có hai hướng chuyển đổi

```sql
-- Timestamptz -> giờ địa phương không kèm time zone.
SELECT
    TIMESTAMPTZ '2026-11-14 02:00:00+00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh' AS local_clock;
-- 2026-11-14 09:00:00

-- Local timestamp tại vùng được chỉ định -> instant.
SELECT
    TIMESTAMP '2026-11-14 09:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh' AS actual_instant;
```

Trong câu thứ hai, kết quả có kiểu `timestamptz` và có thể **được hiển thị theo time zone của session**, không nhất thiết với hậu tố `+07`.

### Đừng dùng khoảng 24 giờ máy móc cho mọi “ngày địa phương”

Ở những vùng có **Daylight Saving Time (DST)**, một ngày theo lịch đôi khi dài **23 hoặc 25 giờ**. Khi lọc dữ liệu theo ngày của người dùng, hãy dựng **hai ranh giới theo múi giờ địa phương** rồi so sánh với cột `timestamptz`.

Ví dụ lấy sự kiện thuộc ngày **14/11/2026** theo lịch Việt Nam:

```sql
SELECT *
FROM temporal_type_examples
WHERE event_instant >=
      (TIMESTAMP '2026-11-14 00:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh')
  AND event_instant <
      (TIMESTAMP '2026-11-15 00:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh');
```

Cách dùng điều kiện **`>=` đầu ngày và `<` đầu ngày kế** cũng thuận tiện cho chỉ mục B-tree trên `event_instant`. Việc ép kiểu/định dạng trực tiếp cột trong `WHERE` có thể khiến tối ưu chỉ mục khó hơn nếu không có expression index tương ứng.

## 4. current_timestamp, now(), statement_timestamp() và clock_timestamp()

Khi muốn biết “hiện tại” trong PostgreSQL, cần hiểu **hiện tại tại mốc nào**:

| Biểu thức | Ý nghĩa chính |
|---|---|
| `CURRENT_TIMESTAMP` | Thời điểm bắt đầu transaction hiện tại. |
| `now()` | Tương đương thời điểm bắt đầu transaction, không liên tục tăng trong transaction dài. |
| `transaction_timestamp()` | Thời điểm bắt đầu transaction. |
| `statement_timestamp()` | Thời điểm server nhận/làm việc với statement hiện tại theo cơ chế PostgreSQL. |
| `clock_timestamp()` | Đồng hồ thực tại thời điểm gọi; có thể thay đổi ngay trong một statement. |

Ví dụ:

```sql
BEGIN;

SELECT now(), statement_timestamp(), clock_timestamp();

SELECT pg_sleep(1);

SELECT now(), statement_timestamp(), clock_timestamp();

ROLLBACK;
```

Trong transaction ở trên, `now()` giữ giá trị lúc bắt đầu transaction, còn `statement_timestamp()` và `clock_timestamp()` có thể phản ánh thời điểm muộn hơn.

### Chọn hàm nào cho audit log?

Không có lựa chọn duy nhất cho mọi hệ thống:

- Muốn mọi thay đổi cùng transaction mang **một mốc đồng nhất**: `now()` có thể phù hợp.
- Muốn thời điểm **mỗi statement** bắt đầu: `statement_timestamp()`.
- Muốn đồng hồ ngay lúc trigger ghi từng bản ghi: `clock_timestamp()`.
- Muốn thời gian sự kiện thực tế từ thiết bị hoặc đối tác: thường phải lưu **timestamp từ sự kiện**, không thay bằng thời điểm server nhận.

**Timestamp không tự chứng minh thứ tự commit của các transaction.** Hai transaction có thể bắt đầu theo thứ tự A rồi B nhưng commit theo thứ tự B rồi A. Để cần thứ tự ổn định, có thể phải sử dụng version number theo entity, khóa đồng thời, LSN/CDC hoặc các ràng buộc và giao thức riêng.

## 5. Chọn mô hình lưu lịch sử theo câu hỏi cần trả lời

Những mô hình thường gặp:

| Mô hình | Lưu gì? | Điểm mạnh | Giới hạn |
|---|---|---|---|
| **Current-state table** | Chỉ hàng đang có hiệu lực. | Đơn giản, truy vấn nhanh. | Mất giá trị cũ khi `UPDATE`/`DELETE` nếu không có cơ chế khác. |
| **Snapshot định kỳ** | Ảnh chụp toàn bảng hoặc tập dữ liệu theo lịch. | Hữu ích cho báo cáo/mốc khôi phục. | Có thể thiếu thay đổi giữa hai lần chụp. |
| **Versioned/SCD Type 2** | Mỗi phiên bản giá trị và khoảng hiệu lực của nó. | Trả lời “giá trị nào có hiệu lực tại thời điểm T?”. | Cần quản lý khoảng, cập nhật đồng thời và sửa hồi tố. |
| **Bitemporal** | Cả thời gian nghiệp vụ có hiệu lực và thời gian hệ thống biết bản ghi. | Trả lời “lúc trước hệ thống nghĩ gì về một thời điểm?”. | Logic và ràng buộc phức tạp hơn. |
| **Audit log** | Bản ghi thao tác: ai/điều gì/bao giờ/old/new. | Truy vết thay đổi, hỗ trợ điều tra. | Không tự là mô hình trạng thái lịch sử có hiệu lực. |
| **Event log / event sourcing** | Chuỗi sự kiện nghiệp vụ bất biến. | Phù hợp hệ thống cần tái dựng trạng thái từ sự kiện. | Đòi hỏi schema sự kiện, thứ tự, versioning và replay. |
| **CDC / logical decoding** | Stream thay đổi dữ liệu từ log database. | Đồng bộ hệ thống gần thời gian thực. | Không tự có ngữ nghĩa actor/reason của nghiệp vụ. |

Một hệ thống có thể dùng **nhiều mô hình cùng lúc**. Ví dụ bảng giá phiên bản cho truy vấn theo ngày, audit log để truy vết ai đổi giá, và outbox để phát sự kiện `PriceChanged` sang hệ thống khác.

## 6. Thiết kế bảng trạng thái hiện tại: đơn giản nhưng phải chấp nhận giới hạn

Ví dụ:

```sql
CREATE TABLE catalog_products_current (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Truy vấn lấy giá hiện tại:

```sql
SELECT product_id, sku, price
FROM catalog_products_current
WHERE product_id = 42;
```

Ưu điểm: dễ hiểu, một hàng mỗi sản phẩm, chỉ mục đơn giản. Nhưng nếu chạy:

```sql
UPDATE catalog_products_current
SET price = 125000,
    updated_at = clock_timestamp()
WHERE product_id = 42;
```

thì giá cũ đã bị thay thế trong **trạng thái logic hiện hành của bảng**. PostgreSQL dùng MVCC và WAL nhưng điều đó **không tương đương một kho lịch sử truy vấn được tùy ý**. Autovacuum có thể thu hồi các tuple version cũ; WAL có vòng đời lưu giữ riêng.

Nếu yêu cầu là “xem bảng giá của ngày 01/11”, bạn cần một thiết kế lịch sử tường minh, không thể chỉ trông vào `updated_at` và MVCC.

## 7. Mô hình lịch sử theo khoảng hiệu lực: SCD Type 2

**Slowly Changing Dimension Type 2 (SCD Type 2)** là cách lưu **mỗi phiên bản giá trị thành một hàng**, đi kèm khoảng thời gian hiệu lực. Thay vì ghi đè giá cũ, hệ thống **đóng khoảng cũ** rồi **tạo một phiên bản mới**.

Ví dụ:

| product_id | price | valid_from | valid_to |
|---:|---:|---|---|
| 42 | 100.000 | 01/11 00:00 | 10/11 00:00 |
| 42 | 115.000 | 10/11 00:00 | 14/11 09:00 |
| 42 | 125.000 | 14/11 09:00 | Không giới hạn |

Với cách hiểu **đầu bao gồm, cuối không bao gồm** (ký hiệu **`[)`**):

- 09/11 23:59 thuộc phiên bản 100.000.
- Đúng 10/11 00:00 thuộc phiên bản 115.000.
- Đúng 14/11 09:00 thuộc phiên bản 125.000.

Hai phiên bản liền kề có thể dùng **cùng một mốc kết thúc/bắt đầu** mà không chồng lấn.

### Vì sao không dùng BETWEEN cho hai đầu đều bao gồm?

Nếu điều kiện:

```sql
WHERE :instant BETWEEN valid_from AND valid_to
```

thì tại đúng ranh giới giữa hai phiên bản, có nguy cơ cả bản cũ và mới đều khớp nếu `valid_to` được coi là bao gồm. Thêm nữa, `valid_to IS NULL` không được `BETWEEN` xử lý như “vô hạn”.

Với `[)`, dùng:

```sql
WHERE valid_from <= :instant
  AND (valid_to IS NULL OR :instant < valid_to)
```

Trong ví dụ SQL dùng `:instant` để chỉ **tham số từ ứng dụng/tool có hỗ trợ named parameters**; PostgreSQL SQL thuần không tự hiểu cú pháp named parameter kiểu đó.

## 8. Schema lịch sử giá sản phẩm trong PostgreSQL

Tách bảng **định danh sản phẩm** khỏi bảng **các phiên bản giá**:

```sql
CREATE TABLE catalog_products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE product_price_versions (
    version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL
        REFERENCES catalog_products(product_id),
    price NUMERIC(12, 2) NOT NULL
        CHECK (price >= 0),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    changed_by TEXT NOT NULL,
    change_reason TEXT,
    recorded_at TIMESTAMPTZ NOT NULL
        DEFAULT clock_timestamp(),
    CONSTRAINT chk_price_valid_interval
        CHECK (valid_to IS NULL OR valid_to > valid_from)
);
```

Giải thích:

- `version_id` là định danh duy nhất **của một phiên bản**, không phải mã sản phẩm.
- `product_id` gom các phiên bản cùng sản phẩm.
- `valid_from` và `valid_to` quyết định khi phiên bản giá **có hiệu lực**.
- `valid_to IS NULL` quy ước phiên bản có thời điểm kết thúc **chưa xác định**.
- `recorded_at` ghi **thời điểm hệ thống lưu phiên bản**, có thể khác `valid_from`.
- `changed_by` và `change_reason` hỗ trợ truy vết cơ bản, nhưng chưa phải hệ thống audit đầy đủ.

Tạo dữ liệu thử nghiệm:

```sql
INSERT INTO catalog_products(product_id, sku, name)
VALUES (42, 'SKU-042', 'San pham demo');

INSERT INTO product_price_versions
    (product_id, price, valid_from, valid_to,
     changed_by, change_reason)
VALUES
    (42, 100000, TIMESTAMPTZ '2026-11-01 00:00:00+07',
         TIMESTAMPTZ '2026-11-10 00:00:00+07',
         'pricing_admin', 'Gia ban dau'),
    (42, 115000, TIMESTAMPTZ '2026-11-10 00:00:00+07',
         TIMESTAMPTZ '2026-11-14 09:00:00+07',
         'pricing_admin', 'Dieu chinh dot 1'),
    (42, 125000, TIMESTAMPTZ '2026-11-14 09:00:00+07',
         NULL,
         'pricing_admin', 'Dieu chinh dot 2');
```

**Lưu ý:** Tập lệnh này tạo dữ liệu mẫu trên database lab còn trống. Schema ở trên **chưa có ràng buộc ngăn mọi khoảng chồng lấn**; phần sau sẽ bổ sung `EXCLUDE` để bảo vệ bất biến đó ở tầng database.

## 9. Truy vấn giá tại một thời điểm bất kỳ — as-of query

Để tìm giá hiệu lực lúc **12/11/2026 10:00 ở Việt Nam**:

```sql
SELECT version_id, product_id, price,
       valid_from, valid_to
FROM product_price_versions
WHERE product_id = 42
  AND valid_from <=
      TIMESTAMPTZ '2026-11-12 10:00:00+07'
  AND (
      valid_to IS NULL
      OR TIMESTAMPTZ '2026-11-12 10:00:00+07' < valid_to
  );
```

Kết quả kỳ vọng là giá **115.000**. Với dữ liệu không có khoảng chồng lấn, một sản phẩm tại thời điểm T có **tối đa một phiên bản** đang có hiệu lực.

### Truy vấn giá hiện tại

Nếu mô hình chỉ cho phép một phiên bản **mở về tương lai**:

```sql
SELECT product_id, price
FROM product_price_versions
WHERE product_id = 42
  AND valid_to IS NULL;
```

Nhưng cần chú ý **hiệu lực tương lai**: một phiên bản có `valid_from` là ngày mai và `valid_to IS NULL` chưa chắc là giá **đang hiệu lực hôm nay**. Vì vậy, truy vấn hiện tại chắc chắn hơn:

```sql
SELECT product_id, price
FROM product_price_versions
WHERE product_id = 42
  AND valid_from <= now()
  AND (valid_to IS NULL OR now() < valid_to);
```

**“Khoảng không có ngày kết thúc” không luôn đồng nghĩa “đang có hiệu lực tại thời điểm truy vấn”.** Điều này đặc biệt quan trọng khi lập lịch thay đổi trước vài ngày.

### Tính giá cho nhiều sản phẩm theo thời điểm

```sql
SELECT p.product_id, p.sku, v.price
FROM catalog_products AS p
LEFT JOIN product_price_versions AS v
  ON v.product_id = p.product_id
 AND v.valid_from <= TIMESTAMPTZ '2026-11-12 10:00:00+07'
 AND (
       v.valid_to IS NULL
       OR TIMESTAMPTZ '2026-11-12 10:00:00+07' < v.valid_to
     );
```

`LEFT JOIN` cho phép vẫn thấy sản phẩm chưa có phiên bản giá tại mốc đã chọn. Nếu dữ liệu có những khoảng chồng lấn, truy vấn có thể trả **nhiều dòng cho một sản phẩm**, nên cần ràng buộc đúng ngay từ khi ghi.

## 10. Range types: biểu diễn khoảng thời gian rõ hơn

PostgreSQL cung cấp **range types**: `daterange`, `tsrange`, `tstzrange` và những range khác. Với lịch sử có mốc thời gian tuyệt đối, `tstzrange` là lựa chọn thường phù hợp.

Ví dụ:

```sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-01 00:00:00+07',
    TIMESTAMPTZ '2026-11-10 00:00:00+07',
    '[)'
) AS active_period;
```

`[)` nghĩa là **bao gồm đầu, không bao gồm cuối**.

Các toán tử quan trọng:

| Toán tử | Ví dụ | Ý nghĩa |
|---|---|---|
| `@>` | `valid_period @> some_timestamp` | Khoảng **chứa** thời điểm. |
| `&&` | `period_a && period_b` | Hai khoảng có phần **giao nhau**. |
| `<@` | `period_a <@ period_b` | Khoảng đầu nằm trong khoảng sau. |
| `lower()` | `lower(valid_period)` | Lấy đầu khoảng. |
| `upper()` | `upper(valid_period)` | Lấy cuối khoảng; có thể không có giới hạn. |
| `isempty()` | `isempty(valid_period)` | Kiểm tra khoảng rỗng. |

Ví dụ:

```sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-01 00:00:00+07',
        TIMESTAMPTZ '2026-11-10 00:00:00+07',
        '[)'
    ) @> TIMESTAMPTZ '2026-11-05 10:00:00+07'
    AS contains_fifth_day;
-- true
```

### Dùng NULL để biểu diễn đầu hoặc cuối không giới hạn

Khi tạo range:

```sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    NULL,
    '[)'
) AS open_ended;
```

`NULL` ở **tham số upper** trong constructor nghĩa là **upper bound không giới hạn**. Điều này khác việc lưu cột `valid_period` bằng SQL `NULL`: một range `NULL` không mang nghĩa “khoảng mở vô hạn”.

Nếu dùng trực tiếp cột kiểu `tstzrange`, nên đặt `NOT NULL` và kiểm tra `NOT isempty(valid_period)` khi nghiệp vụ không cho khoảng rỗng.

## 11. Chống khoảng hiệu lực chồng lấn bằng EXCLUDE USING gist

Hai bản giá của cùng sản phẩm có khoảng hiệu lực giao nhau là lỗi thiết kế dữ liệu nếu nghiệp vụ quy định **một sản phẩm chỉ có một giá tại mỗi thời điểm**.

Chỉ có `CHECK (valid_to > valid_from)` chưa đủ: ràng buộc này đảm bảo **từng hàng tự hợp lệ**, nhưng không so sánh hai hàng khác nhau.

PostgreSQL hỗ trợ **exclusion constraint** với chỉ mục GiST để đảm bảo **không tồn tại hai hàng cùng sản phẩm có khoảng giao nhau**.

Trước tiên, trong database lab có thể cần extension `btree_gist` để cung cấp lớp toán tử phù hợp cho `BIGINT WITH =` trong GiST:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

Việc cài extension cần quyền thích hợp và có thể bị chính sách hệ thống hạn chế.

Sau khi dữ liệu hiện tại **không có khoảng chồng lấn**, thêm ràng buộc:

```sql
ALTER TABLE product_price_versions
ADD CONSTRAINT ex_price_no_overlap
EXCLUDE USING gist (
    product_id WITH =,
    tstzrange(valid_from, valid_to, '[)') WITH &&
);
```

Ý nghĩa:

- **`product_id WITH =`**: xét các phiên bản của cùng sản phẩm.
- **`tstzrange(...) WITH &&`**: không cho khoảng thời gian giao nhau.
- Hai phiên bản của **hai sản phẩm khác nhau** có thể cùng khoảng thời gian.
- Hai phiên bản **cùng sản phẩm** có thể nằm **kề nhau** tại ranh giới `[)`, nhưng không thể chồng lấn.

Ví dụ lệnh sau phải thất bại nếu đã có giá 115.000 từ 10/11 đến 14/11 09:00:

```sql
INSERT INTO product_price_versions
    (product_id, price, valid_from, valid_to, changed_by)
VALUES
    (42, 119000,
     TIMESTAMPTZ '2026-11-11 00:00:00+07',
     TIMESTAMPTZ '2026-11-13 00:00:00+07',
     'pricing_admin');
```

PostgreSQL sẽ từ chối vì hai khoảng giao nhau cho cùng `product_id`. Lỗi exclusion constraint thường có SQLSTATE **`23P01`** (`exclusion_violation`).

### Exclusion constraint không đảm bảo “không có lỗ hổng”

Giả sử một sản phẩm có giá từ ngày 01/11 đến 10/11 và từ 15/11 trở đi. Hai khoảng **không chồng lấn**, nên ràng buộc `EXCLUDE` chấp nhận; nhưng ngày 10–14/11 **không có giá**.

Nếu nghiệp vụ yêu cầu tính liên tục, cần quy tắc ghi dữ liệu, kiểm tra theo entity hoặc quy trình bảo đảm **không có gap**. `EXCLUDE` chỉ bảo vệ **không overlap**, không tự sinh phiên bản để lấp khoảng trống.

### Partial unique index cho bản mở hiện tại

Trong một số thiết kế, thêm:

```sql
CREATE UNIQUE INDEX ux_price_one_open_version
ON product_price_versions(product_id)
WHERE valid_to IS NULL;
```

Chỉ mục này không cho hai phiên bản cùng sản phẩm có `valid_to IS NULL`. Nếu đã có `EXCLUDE` không overlap với range upper không giới hạn, bất biến “không có hai khoảng mở giao nhau” về cơ bản **đã được bảo vệ**; partial unique index là một lựa chọn bổ sung với chi phí ghi/lưu trữ, có thể hữu ích cho một số đường truy vấn. Đừng tự động thêm nhiều chỉ mục trùng chức năng mà chưa đánh giá workload.

## 12. Cập nhật một phiên bản giá: transaction phải bao trùm cả hai bước

Khi giá thay đổi tại thời điểm T, ta muốn:

1. Kết thúc phiên bản cũ tại **T**.
2. Thêm phiên bản mới bắt đầu tại **T**.
3. Hai bước **thành công hoặc rollback cùng nhau**.

Ví dụ trong **database lab**, với sản phẩm `42` và T là **15/11/2026 09:00 +07**:

```sql
BEGIN;

-- Serialize các thay đổi giá của cùng sản phẩm
-- nếu mọi writer tuân thủ giao thức khóa này.
SELECT product_id
FROM catalog_products
WHERE product_id = 42
FOR UPDATE;

UPDATE product_price_versions
SET valid_to = TIMESTAMPTZ '2026-11-15 09:00:00+07'
WHERE product_id = 42
  AND valid_to IS NULL;

INSERT INTO product_price_versions (
    product_id, price, valid_from, valid_to,
    changed_by, change_reason
)
VALUES (
    42, 129000,
    TIMESTAMPTZ '2026-11-15 09:00:00+07',
    NULL,
    'pricing_admin', 'Cap nhat gia ngay 15/11'
);

COMMIT;
```

**Đây là ví dụ cập nhật với T lớn hơn mọi `valid_from` hiện hữu và một phiên bản mở đang tồn tại**. Nếu có phiên bản tương lai đã lên lịch, quy trình phải xét toàn bộ timeline thay vì chỉ tìm `valid_to IS NULL`.

### Vì sao khóa hàng cha?

Nếu hai worker cùng đổi giá sản phẩm 42, cả hai có thể đọc giá cũ và cố tạo phiên bản mới. Khóa `catalog_products` bằng `FOR UPDATE` giúp **tuần tự hóa theo sản phẩm** khi tất cả đường ghi sử dụng cùng giao thức.

Trong hệ thống có nhiều đường ghi, `EXCLUDE` vẫn là tuyến bảo vệ quan trọng ở database: một worker quên khóa cha có thể vẫn bị constraint từ chối khi tạo overlap, thay vì âm thầm làm dữ liệu sai.

### Dùng cùng một thời điểm T

Không nên gọi `clock_timestamp()` độc lập ở bước `UPDATE` và `INSERT` nếu hai bước phải **ghép khít** tại một mốc. Hai lần gọi có thể khác vài microsecond và tạo gap ngoài ý muốn.

Một cách dễ kiểm soát là **chọn T một lần** ở tầng ứng dụng hoặc SQL rồi dùng T làm tham số cho cả hai statement trong cùng transaction. Nếu cần lập lịch hồi tố hay tương lai, T phải là **mốc hiệu lực nghiệp vụ** được phê duyệt, không nhất thiết là thời điểm server đang ghi.

### Kiểm tra số hàng cập nhật

Ví dụ `UPDATE` không tìm thấy bản mở nào có thể là một trường hợp nghiệp vụ hợp lệ (sản phẩm mới), hoặc dấu hiệu timeline không như kỳ vọng. Ứng dụng nên kiểm tra **row count**, điều kiện định danh và kết quả cuối cùng trước `COMMIT`; không mặc định cứ có `INSERT` thành công là quá trình thay đổi giá đã đúng.

## 13. Bitemporal: hai chiều thời gian để trả lời “khi đó chúng ta đã biết gì?”

Mô hình lịch sử một chiều trả lời “tại thời điểm T, giá có hiệu lực là gì?” Nhưng đôi khi cần thêm câu hỏi khó hơn:

> “Vào ngày 10/11, hệ thống **đang tin** giá của ngày 01/11 là bao nhiêu, trước khi bản sửa ngày 14/11 được nhập?”

Đây là nhu cầu **bitemporal**, kết hợp:

- **Valid time:** khoảng giá trị được cho là đúng trong thế giới nghiệp vụ.
- **System/recorded time:** khoảng thời gian hệ thống lưu một **phiên bản nhận định** về giá trị ấy.

Ví dụ:

```text
01/11: Giá 100 có hiệu lực theo bản ghi ban đầu.
10/11: Hệ thống vẫn tin giá từ 01/11 là 100.
14/11: Phát hiện giá đúng từ 01/11 phải là 120.

As of recorded 10/11, valid 05/11 → 100.
As of recorded 15/11, valid 05/11 → 120.
```

Chỉ cập nhật hàng cũ thành 120 và ghi `updated_at` 14/11 sẽ **không giữ lại đầy đủ** điều mà hệ thống từng tin hôm 10/11.

### Một schema bitemporal giản lược

```sql
CREATE TABLE product_price_assertions (
    assertion_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES catalog_products(product_id),
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),

    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,

    recorded_from TIMESTAMPTZ NOT NULL,
    recorded_to TIMESTAMPTZ,

    correction_reason TEXT,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (recorded_to IS NULL OR recorded_to > recorded_from)
);
```

Mỗi hàng biểu diễn một **assertion**: một mức giá có hiệu lực trong khoảng `valid_from → valid_to`, được hệ thống tin trong khoảng `recorded_from → recorded_to`.

Truy vấn:

```sql
SELECT product_id, price
FROM product_price_assertions
WHERE product_id = 42
  -- Giá có hiệu lực vào ngày 05/11:
  AND valid_from <= TIMESTAMPTZ '2026-11-05 12:00:00+07'
  AND (
       valid_to IS NULL
       OR TIMESTAMPTZ '2026-11-05 12:00:00+07' < valid_to
  )
  -- Hệ thống đã biết nhận định này vào ngày 10/11:
  AND recorded_from <= TIMESTAMPTZ '2026-11-10 12:00:00+07'
  AND (
       recorded_to IS NULL
       OR TIMESTAMPTZ '2026-11-10 12:00:00+07' < recorded_to
  );
```

**Schema trên chỉ giới thiệu cách biểu diễn**. Nó chưa có ràng buộc đa chiều để đảm bảo đúng một nhận định giá tại từng cặp thời điểm. Triển khai bitemporal thật phải thiết kế logic đóng bản assertion cũ, lưu bản sửa mới, quản lý đồng thời và tránh overlap không hợp lệ trên **hai trục thời gian**.

### PostgreSQL không tự kích hoạt system-versioned table chỉ vì có cột thời gian

PostgreSQL thông thường **không tự cung cấp cú pháp SQL Server-style `FOR SYSTEM_TIME AS OF` hoặc tự lưu mọi phiên bản của table** chỉ vì bạn đặt tên cột `valid_from`/`recorded_from`. Muốn bitemporal cần triển khai bằng schema, trigger, ứng dụng hoặc extension thích hợp và kiểm tra ngữ nghĩa của chúng.

Một cột `recorded_at DEFAULT now()` **không đủ** để bảo đảm system-time history. Để biết bản ghi đã bị thay thế khi nào, cần có cơ chế đóng `recorded_to`, giữ assertion cũ và ghi assertion mới một cách nhất quán.

## 14. Lịch sử dữ liệu khác audit log ở điểm nào?

**Bảng lịch sử** mô tả **những phiên bản trạng thái** để trả lời câu hỏi giá trị đúng tại một mốc. **Audit log** mô tả **hành động thay đổi** để trả lời ai/điều gì đã tạo thay đổi và tác động thế nào.

Ví dụ:

| Khía cạnh | Version table | Audit log |
|---|---|---|
| Nội dung chính | Trạng thái và khoảng hiệu lực. | Sự kiện `INSERT`/`UPDATE`/`DELETE`, old/new, actor, reason, request. |
| Câu hỏi | Giá có hiệu lực ngày 10/11 là bao nhiêu? | Ai đổi giá ngày 14/11? |
| Truy vấn điển hình | `valid_period @> T`. | `WHERE entity_id = ... ORDER BY changed_at`. |
| Có phản ánh sửa hồi tố? | Có, nếu thiết kế thời gian hiệu lực phù hợp. | Có thể ghi thao tác sửa nhưng chưa mô hình hóa valid time. |
| Có đủ cho điều tra bảo mật? | Thường không. | Tốt hơn, nhưng audit log trong cùng DB vẫn có giới hạn chống giả mạo. |

Cả hai có thể bổ sung nhau. Nếu nghiệp vụ có giá thay đổi theo ngày nhưng cũng cần kiểm toán, nên lưu **version table để tra cứu trạng thái** và **audit log để truy vết thao tác**.

### Event log không đồng nghĩa audit log

Sự kiện nghiệp vụ như `OrderPaid` hoặc `PriceApproved` thường mô tả **điều đã xảy ra trong domain**. Audit log kỹ thuật có thể ghi “hàng orders id 123 đổi cột status từ PENDING sang PAID”.

Hai bản ghi có mục đích khác nhau. Một event nghiệp vụ có thể tạo ra nhiều thay đổi bảng; một thao tác SQL lại có thể không mang đủ ý nghĩa của một sự kiện nghiệp vụ.

## 15. Thiết kế bảng audit: danh tính, hành động, thời gian và payload

Một bảng audit thông dụng có các trường:

| Trường | Vai trò |
|---|---|
| `audit_id` | Định danh ổn định của bản ghi audit. |
| `entity_type`, `entity_id` | Loại và định danh đối tượng bị thay đổi. |
| `action` | `INSERT`, `UPDATE`, `DELETE` hoặc sự kiện nghiệp vụ được định nghĩa. |
| `changed_at` | Thời điểm ghi nhận thay đổi. |
| `actor` | Principal đã yêu cầu thay đổi, theo cơ chế xác thực được tin cậy. |
| `request_id` / `correlation_id` | Ghép hành động với request hoặc job. |
| `old_values` / `new_values` | Dữ liệu trước/sau hoặc chỉ các trường đã đổi. |
| `reason` | Lý do sửa được cung cấp từ nghiệp vụ khi cần. |
| `source` | Ứng dụng/job/service nào phát sinh thay đổi. |

`jsonb` phù hợp cho payload old/new linh hoạt, nhưng **không nên đưa toàn bộ dữ liệu nhạy cảm vào log theo thói quen**. Với thông tin tài chính, tài khoản, token và dữ liệu cá nhân, phải xác định mức cần thiết, hạn chế truy cập và retention.

### Ví dụ bảng nghiệp vụ và schema audit

```sql
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE public.demo_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit.demo_order_changes (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    action TEXT NOT NULL
        CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
    old_values JSONB,
    new_values JSONB,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    actor TEXT NOT NULL,
    request_id TEXT,
    change_reason TEXT
);
```

`order_id` trong audit table **không được gắn foreign key bắt buộc** tới `demo_orders` trong ví dụ này. Lý do: khi đơn hàng bị xóa, audit record cần **vẫn tồn tại** để cho biết đã có hàng nào bị xóa. Một foreign key thông thường có thể làm thiết kế xóa và lưu audit mâu thuẫn nhau nếu không có chiến lược retention/soft delete phù hợp.

## 16. Ghi audit bằng trigger trong cùng transaction

PostgreSQL hỗ trợ **trigger** để tự động ghi bản ghi audit khi hàng bị `INSERT`, `UPDATE` hoặc `DELETE`. Cách này giúp ghi nhận nhiều đường thay đổi dữ liệu khác nhau, không chỉ từ một service cụ thể.

Ví dụ trigger function cho bảng `public.demo_orders`:

```sql
CREATE OR REPLACE FUNCTION audit.log_demo_order_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, audit, pg_temp
AS $$
DECLARE
    v_actor TEXT;
    v_request TEXT;
BEGIN
    -- App có thể đặt các biến này trong transaction.
    -- Giá trị từ client không được tự coi là danh tính đã xác thực.
    v_actor := NULLIF(current_setting('app.actor', true), '');
    v_request := NULLIF(current_setting('app.request_id', true), '');

    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit.demo_order_changes (
            order_id, action, old_values, new_values,
            actor, request_id
        )
        VALUES (
            NEW.order_id, 'INSERT', NULL, to_jsonb(NEW),
            COALESCE(v_actor, session_user::TEXT), v_request
        );
        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        -- Bỏ qua UPDATE không đổi nội dung hàng.
        IF to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
            INSERT INTO audit.demo_order_changes (
                order_id, action, old_values, new_values,
                actor, request_id
            )
            VALUES (
                NEW.order_id, 'UPDATE', to_jsonb(OLD), to_jsonb(NEW),
                COALESCE(v_actor, session_user::TEXT), v_request
            );
        END IF;
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit.demo_order_changes (
            order_id, action, old_values, new_values,
            actor, request_id
        )
        VALUES (
            OLD.order_id, 'DELETE', to_jsonb(OLD), NULL,
            COALESCE(v_actor, session_user::TEXT), v_request
        );
        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_demo_orders_audit
AFTER INSERT OR UPDATE OR DELETE
ON public.demo_orders
FOR EACH ROW
EXECUTE FUNCTION audit.log_demo_order_change();
```

### Những thuộc tính cần hiểu

- Trigger `AFTER ... FOR EACH ROW` chạy khi thao tác hàng tương ứng xảy ra và thực hiện trong **transaction chứa thay đổi**.
- Khi transaction **rollback**, cả thay đổi hàng và audit record do trigger tạo trong transaction đó **cùng rollback**.
- Với `UPDATE`, `OLD` là hình ảnh hàng trước, `NEW` là hình ảnh sau.
- Với `INSERT` chỉ có `NEW` hữu dụng; với `DELETE` chỉ có `OLD`.
- `TG_OP` cho biết loại thao tác.
- `to_jsonb(OLD)`/`to_jsonb(NEW)` giúp lưu payload dạng JSONB, nhưng có thể sao chép dữ liệu nhạy cảm và tạo log lớn.
- Trigger được tạo ở chế độ mặc định của ví dụ; quyền và khả năng vô hiệu hóa trigger bởi role có đặc quyền vẫn phải được kiểm soát.

### Vì sao dùng SECURITY DEFINER?

Ví dụ dùng `SECURITY DEFINER` để minh họa một thiết kế trong đó trigger có thể ghi bảng audit bằng quyền của **owner function**, ngay cả khi role ứng dụng không có quyền `INSERT` trực tiếp vào audit table. Điều đó **chỉ an toàn khi**:

1. Function và schema audit do role đáng tin cậy sở hữu.
2. `search_path` được khóa vào schema tin cậy; mọi quan hệ quan trọng được schema-qualify.
3. Quyền `EXECUTE` của function, quyền tạo đối tượng trong schema và quyền trên audit table được rà soát.
4. Ứng dụng không thể tùy ý sửa/xóa log qua đường truy cập khác.
5. Mã trigger không dùng dynamic SQL từ input không được kiểm soát.

**Không copy nguyên function SECURITY DEFINER lên production mà chưa kiểm tra ownership/privileges**. Mã chạy với quyền cao có thể biến thành lỗ hổng nếu tin cậy sai schema hoặc input.

### app.actor không tự là danh tính đáng tin

`current_setting('app.actor', true)` đọc một **custom configuration parameter** do ứng dụng có thể đặt, ví dụ:

```sql
BEGIN;

SELECT set_config('app.actor', 'user-123', true);
SELECT set_config('app.request_id', 'req-789', true);

UPDATE public.demo_orders
SET status = 'PAID'
WHERE order_id = 1;

COMMIT;
```

Tham số thứ ba `true` trong `set_config` đặt giá trị **chỉ trong transaction hiện tại**, giúp tránh rò rỉ state qua connection pool. Nhưng client có thể tự gửi giá trị actor khác nếu có quyền kết nối, nên đó là **ngữ cảnh ứng dụng cung cấp**, không phải bằng chứng độc lập về người dùng đã xác thực.

Nếu audit yêu cầu danh tính đáng tin cậy về pháp lý/an ninh, hệ thống cần cơ chế xác thực, ánh xạ principal và bảo vệ đường ghi log phù hợp; có thể bổ sung log ở tầng dịch vụ hoặc hệ thống giám sát riêng.

## 17. Kiểm tra hành vi trigger và rollback

Trên database lab:

```sql
INSERT INTO public.demo_orders(status, total_amount)
VALUES ('PENDING', 300000)
RETURNING order_id;
```

Giả sử `order_id` trả về là **1**. Cập nhật:

```sql
UPDATE public.demo_orders
SET status = 'PAID'
WHERE order_id = 1;

SELECT audit_id, action, old_values, new_values, changed_at
FROM audit.demo_order_changes
WHERE order_id = 1
ORDER BY audit_id;
```

Bạn sẽ thấy record `INSERT` và `UPDATE` tương ứng nếu các lệnh thành công và trigger chưa bị thay đổi.

Kiểm tra rollback:

```sql
BEGIN;

UPDATE public.demo_orders
SET status = 'CANCELLED'
WHERE order_id = 1;

ROLLBACK;

SELECT status
FROM public.demo_orders
WHERE order_id = 1;
```

Giá trị trạng thái vẫn là `PAID`, và bản ghi audit cho thay đổi `CANCELLED` **không tồn tại như một thay đổi đã commit**. Đây là kết quả mong muốn với audit database ghi **các thay đổi đã commit**, nhưng nếu muốn ghi **mọi lần thử bị từ chối**, cần cơ chế audit ở tầng ứng dụng hoặc log độc lập: trigger transaction không giữ lại bằng chứng về thao tác đã rollback.

### Audit ID không phải commit sequence tuyệt đối

`audit_id` do identity sequence cấp thường tăng, nhưng sequence của PostgreSQL **không rollback theo transaction** và có thể có khoảng trống. Thứ tự lấy sequence value cũng không bảo đảm giống thứ tự transaction commit.

Vì vậy, `ORDER BY audit_id` hữu ích để hiển thị trong nhiều hệ thống đơn giản, nhưng **không phải chứng cứ tuyệt đối về thứ tự commit toàn database**. Nếu cần ordering theo entity, hãy có version number tuần tự được bảo vệ bởi khóa/transaction hoặc cơ chế stream có mốc tương ứng.

## 18. Audit bằng trigger có giới hạn nào?

Trigger audit là công cụ mạnh, nhưng không tự trở thành hệ thống **tamper-proof**:

1. **Role đặc quyền cao** có thể thay đổi object, tắt trigger hoặc tác động trực tiếp tới dữ liệu/log theo quyền.
2. **DDL** như `ALTER TABLE`, `DROP TABLE` không được ghi nhận bởi row-level DML trigger ở trên.
3. Thao tác SQL bị lỗi hoặc transaction rollback thường **không để lại audit row đã commit** trong cùng database.
4. Dữ liệu ngoài database (file, message broker, API bên thứ ba) không được trigger này tự ghi nhận.
5. Trigger có thêm **chi phí ghi, WAL, index, I/O** cho mọi thay đổi liên quan.
6. Payload old/new đầy đủ có thể tăng dung lượng và rủi ro bảo mật.
7. Với bulk update hàng triệu dòng, row-level trigger có thể sinh rất nhiều audit records, ảnh hưởng thời gian transaction.

Để đáp ứng yêu cầu kiểm toán nghiêm ngặt, có thể cần **log độc lập/khó sửa**, quản lý quyền tách biệt, bảo vệ và giám sát truy cập, chuỗi hash hoặc lưu trữ bất biến theo quy trình. Những biện pháp này không tự xuất hiện chỉ vì bảng tên `audit_log`.

### Audit ở tầng ứng dụng và tầng database có thể kết hợp

Ứng dụng thường biết **actor và lý do nghiệp vụ** tốt hơn database. Database trigger lại có thể nhìn thấy thao tác DML từ nhiều đường ghi. Kết hợp hai tầng giúp có cả thông tin nghiệp vụ và phát hiện những thay đổi không đi qua service chính.

Điều quan trọng là xác định **nguồn tin cậy**, không ghi hai bộ audit thiếu đồng bộ rồi nhầm chúng là cùng một sự kiện.

## 19. Event sourcing: lịch sử sự kiện là nguồn dữ liệu gốc

Trong **event sourcing**, thay vì xem bảng trạng thái hiện tại là nguồn gốc duy nhất, ứng dụng lưu các sự kiện nghiệp vụ theo trình tự và dựng ra trạng thái từ chúng.

Ví dụ chuỗi sự kiện của đơn hàng:

```text
OrderCreated(orderId=101, total=300000)
      │
      ▼
PaymentConfirmed(orderId=101, paymentId=...)
      │
      ▼
OrderPacked(orderId=101)
      │
      ▼
OrderShipped(orderId=101)
```

Một bảng sự kiện:

```sql
CREATE TABLE order_domain_events (
    event_id UUID PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sequence_no BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (order_id, sequence_no)
);

CREATE INDEX ix_order_events_replay
ON order_domain_events(order_id, sequence_no);
```

Mỗi sự kiện có:

- **`event_id`** để nhận diện khi gửi lại.
- **`sequence_no`** để tạo trật tự theo từng `order_id`.
- **`event_type`** diễn đạt ý nghĩa nghiệp vụ.
- **`payload`** chứa dữ liệu cần để dựng trạng thái.
- **`occurred_at`** là thời điểm sự kiện, có thể khác `recorded_at`.

`UNIQUE(order_id, sequence_no)` ngăn cùng một vị trí trong chuỗi của một order bị ghi hai lần, nhưng **không tự cấp số tuần tự an toàn khi hai worker ghi cùng lúc**. Ứng dụng cần transaction, khóa/optimistic concurrency hoặc giao thức append event có kiểm soát.

### Event sourcing không phải chỉ thêm bảng audit

Audit log có thể ghi “trạng thái đổi từ PENDING sang PAID”. Event sourcing đòi hỏi **sự kiện có đủ ý nghĩa và schema để tái dựng state**. Ví dụ `PaymentConfirmed` có thể cần mã thanh toán, số tiền và thông tin nghiệp vụ; nó không chỉ là bản chụp cột bị thay.

Nếu thay đổi cách biểu diễn sự kiện, cần chiến lược **event schema versioning** và cách replay dữ liệu cũ. Một hệ thống đơn giản chỉ cần tra cứu lịch sử giá có thể không cần trả giá phức tạp của event sourcing.

## 20. Outbox pattern: ghi dữ liệu và sự kiện trong cùng transaction

Một vấn đề phổ biến:

```text
Ứng dụng:
  1. UPDATE orders SET status = 'PAID'
  2. Gửi message OrderPaid tới broker
```

Nếu database commit thành công nhưng gửi message thất bại, các hệ thống downstream có thể không biết đơn đã thanh toán. Nếu gửi message trước commit rồi transaction rollback, downstream có thể nhận sự kiện về một thay đổi chưa từng thành công.

**Transactional outbox** lưu **dữ liệu nghiệp vụ và một hàng sự kiện để phát** trong cùng transaction PostgreSQL:

```sql
CREATE TABLE app_outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    published_at TIMESTAMPTZ
);
```

Ví dụ ý tưởng:

```sql
BEGIN;

UPDATE public.demo_orders
SET status = 'PAID'
WHERE order_id = 1
  AND status = 'PENDING';

-- Chỉ nên tạo event nếu UPDATE thực sự tác động
-- đúng hàng theo quy tắc nghiệp vụ.
INSERT INTO app_outbox_events (
    event_id, aggregate_type, aggregate_id, event_type, payload
)
VALUES (
    '11111111-1111-4111-8111-111111111111'::UUID,
    'Order', 1, 'OrderPaid',
    '{"order_id": 1, "new_status": "PAID"}'::JSONB
);

COMMIT;
```

**Ví dụ này tập trung vào ranh giới transaction**, chưa phải workflow hoàn chỉnh. Trong production, ứng dụng phải kiểm tra `UPDATE` tác động đúng một hàng trước khi ghi event, hoặc dùng `UPDATE ... RETURNING` để ràng buộc hai bước.

Một worker riêng đọc các outbox row chưa phát, gửi tới broker rồi ghi nhận `published_at`. Nếu worker gửi thành công nhưng mất kết nối trước khi đánh dấu đã phát, message có thể gửi lại. Vì vậy downstream cần **idempotency**, không mặc định exactly-once end-to-end.

### Outbox khác audit log

- **Audit log:** ai/điều gì đã đổi dữ liệu, để tra cứu và điều tra.
- **Outbox:** sự kiện nào cần giao cho hệ thống khác sau commit.
- **Event sourcing:** chuỗi sự kiện là nguồn dữ liệu để phục dựng trạng thái.

Ba thứ có thể dùng cùng nhau, nhưng không nên mặc định một bảng outbox ngắn hạn đã đáp ứng yêu cầu audit lưu 7 năm.

## 21. Change Data Capture (CDC) và logical decoding

PostgreSQL có cơ chế **logical decoding** đọc các thay đổi đã ghi vào WAL để tạo dòng thay đổi logic cho một consumer. Logical replication và công cụ CDC có thể sử dụng hướng này.

Điểm mạnh:

- Ghi nhận thay đổi database gần thời gian thực mà không yêu cầu mọi service tự gọi webhook.
- Hữu ích để đồng bộ kho dữ liệu, công cụ tìm kiếm hoặc downstream.
- Có thể tách công việc xuất thay đổi khỏi đường xử lý đồng bộ của ứng dụng.

Nhưng CDC có những giới hạn quan trọng:

- Thay đổi cấp hàng không tự nói **ai trong nghiệp vụ** đã phê duyệt hoặc vì sao.
- Cấu hình `wal_level`, publication/slot, replication identity và quyền cần phù hợp.
- Consumer chậm hoặc ngừng có thể khiến **replication slot giữ WAL**, làm tăng dung lượng đĩa và áp lực vận hành.
- Thứ tự, giao dịch, schema change và khả năng phát lại phụ thuộc giao thức/plugin/consumer.
- Không nên coi CDC là kho lịch sử vĩnh viễn nếu không có hệ thống lưu sự kiện và retention phù hợp.

**CDC không phải bản sao lưu thay thế.** Nếu consumer nhận cả thao tác xóa nhầm, nó có thể chuyển chính thay đổi sai đó xuống downstream.

### Chọn giữa trigger và CDC

| Nhu cầu | Trigger audit | CDC/logical decoding |
|---|---|---|
| Lưu actor/reason từ ứng dụng | Có thể ghi nếu app truyền ngữ cảnh đáng tin cậy. | Cần kết hợp thêm metadata nghiệp vụ. |
| Bảo đảm bản ghi audit đi cùng commit | Có khi audit ghi cùng transaction. | Change stream phát sinh từ commit và được consumer xử lý riêng. |
| Đẩy thay đổi cho nhiều hệ thống | Không nên gọi network trực tiếp từ trigger; nên dùng outbox/worker. | Phù hợp với kiến trúc stream/consumer khi có vận hành tương ứng. |
| Chi phí đường ghi | Thêm DML vào transaction. | Có chi phí WAL, slot, decoding, lưu/đọc stream. |
| Lưu lịch sử có cấu trúc để query as-of | Phải thiết kế bảng/history riêng. | Phải xây materialized history/projection ở consumer. |

## 22. Chỉ mục cho dữ liệu lịch sử và audit

Lịch sử thường lớn hơn bảng hiện tại rất nhiều. Chỉ mục nên theo **câu hỏi truy vấn thực tế**.

### 22.1. Tra phiên bản mới nhất của một entity

```sql
CREATE INDEX ix_price_product_start_desc
ON product_price_versions(product_id, valid_from DESC);
```

Truy vấn:

```sql
SELECT price, valid_from, valid_to
FROM product_price_versions
WHERE product_id = 42
ORDER BY valid_from DESC, version_id DESC
LIMIT 1;
```

Điều kiện theo `product_id` và sắp theo `valid_from` giúp index phù hợp với kiểu tìm phiên bản mới nhất theo thời điểm bắt đầu. Tuy nhiên, **bản bắt đầu gần nhất có thể thuộc tương lai**; nó không nhất thiết là giá đang có hiệu lực nếu ứng dụng lên lịch thay đổi trước.

### 22.2. Tra audit của một entity theo thời gian

```sql
CREATE INDEX ix_audit_order_changed_desc
ON audit.demo_order_changes(
    order_id,
    changed_at DESC,
    audit_id DESC
);
```

```sql
SELECT audit_id, action, changed_at,
       old_values, new_values
FROM audit.demo_order_changes
WHERE order_id = 1
ORDER BY changed_at DESC, audit_id DESC
LIMIT 50;
```

Phân trang lịch sử dài nên cân nhắc **keyset pagination**, dùng cặp `(changed_at, audit_id)` để duyệt ổn định theo một thứ tự định nghĩa rõ, thay vì `OFFSET` rất lớn.

### 22.3. BRIN cho bảng append-only theo thời gian

Trên bảng log rất lớn mà dữ liệu thường được ghi gần đúng thứ tự `changed_at`, **BRIN index** có thể nhỏ và hữu ích cho truy vấn theo khoảng thời gian:

```sql
CREATE INDEX ix_audit_changed_brin
ON audit.demo_order_changes
USING brin(changed_at);
```

BRIN lưu metadata tóm tắt theo các dải trang, nên rất phù hợp khi giá trị thời gian **tương quan với vị trí vật lý của hàng**. Nếu liên tục ghi backfill với timestamp lịch sử rải rác, tương quan thấp có thể khiến index kém hiệu quả hơn.

BRIN không thay thế B-tree cho mọi câu truy vấn `WHERE order_id = ...`. Thực tế thường dùng **B-tree theo entity/time** và cân nhắc BRIN cho quét khoảng thời gian trên bảng rất lớn.

### 22.4. GiST cho range và exclusion

`EXCLUDE USING gist` trong mô hình giá sử dụng chỉ mục GiST để ngăn overlap. Nếu truy vấn thời điểm dùng:

```sql
WHERE tstzrange(valid_from, valid_to, '[)')
      @> TIMESTAMPTZ '2026-11-12 10:00:00+07'
```

thì có thể tận dụng lớp toán tử range/GiST phù hợp khi điều kiện và kế hoạch truy vấn cho phép. Nhưng hiệu năng thật phụ thuộc số lượng sản phẩm, độ chọn lọc, thống kê và cách kết hợp với `product_id`.

Luôn dùng `EXPLAIN (ANALYZE, BUFFERS)` trên **môi trường thử nghiệm** khi cần đo kế hoạch thực tế:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT version_id, price
FROM product_price_versions
WHERE product_id = 42
  AND tstzrange(valid_from, valid_to, '[)')
      @> TIMESTAMPTZ '2026-11-12 10:00:00+07';
```

`EXPLAIN ANALYZE` **thực sự thực thi câu truy vấn**; chỉ dùng an toàn với `SELECT` trong ví dụ này hoặc theo cách kiểm soát transaction khi phân tích lệnh ghi.

### 22.5. GIN cho JSONB

Nếu audit có nhu cầu lọc theo trường trong `new_values`:

```sql
SELECT *
FROM audit.demo_order_changes
WHERE new_values @> '{"status": "PAID"}'::jsonb;
```

Một **GIN index** trên `jsonb` có thể hữu ích với workload phù hợp:

```sql
CREATE INDEX ix_audit_new_values_gin
ON audit.demo_order_changes
USING gin(new_values);
```

Nhưng index GIN trên JSONB lớn tăng chi phí ghi, dung lượng và maintenance. Không tạo mặc định nếu ứng dụng chủ yếu tìm theo `order_id`/`changed_at`.

## 23. Partition theo thời gian và chính sách retention

Bảng audit/event có thể tăng hàng triệu hàng mỗi tháng. **Declarative partitioning** theo `occurred_at` hoặc `changed_at` giúp quản lý từng khoảng thời gian và có thể hỗ trợ pruning khi truy vấn có filter phù hợp.

Ví dụ bảng log đơn giản chia partition theo tháng:

```sql
CREATE TABLE activity_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY,
    occurred_at TIMESTAMPTZ NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (event_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE activity_events_2026_11
PARTITION OF activity_events
FOR VALUES FROM ('2026-11-01 00:00:00+00')
           TO ('2026-12-01 00:00:00+00');

CREATE TABLE activity_events_2026_12
PARTITION OF activity_events
FOR VALUES FROM ('2026-12-01 00:00:00+00')
           TO ('2027-01-01 00:00:00+00');
```

Với partition range, đầu khoảng **bao gồm** và cuối **không bao gồm**; giá trị đúng 01/12 00:00 UTC đi vào partition tháng 12, không vào tháng 11.

### Vì sao primary key gồm cả occurred_at?

Trong PostgreSQL, một **PRIMARY KEY hoặc UNIQUE constraint trên partitioned table** cần bao gồm các cột partition key theo các điều kiện được hỗ trợ, vì chỉ mục uniqueness toàn cục không mặc nhiên tồn tại trên toàn bộ partition tree.

Vì vậy, `PRIMARY KEY(event_id, occurred_at)` không bảo đảm rằng **`event_id` riêng lẻ** là duy nhất toàn bảng nếu cùng ID xuất hiện ở hai tháng khác nhau. Nếu sự kiện cần ID globally unique, cần:

- Nguồn sinh ID đủ tin cậy (ví dụ UUID từ ứng dụng), **và/hoặc**
- Cơ chế đăng ký/deduplication tách biệt có uniqueness phù hợp,
- Thiết kế partition key/khóa nghiệp vụ theo yêu cầu.

Đừng cho rằng một identity sequence trên bảng partition tự tạo ràng buộc duy nhất toàn cục cho `event_id`.

### Truy vấn cho phép partition pruning

```sql
SELECT event_id, event_type, actor
FROM activity_events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
```

Khi planner có đủ thông tin, nó có thể bỏ qua các partition nằm ngoài khoảng cần đọc.

### Retention là yêu cầu nghiệp vụ và pháp lý

Không phải mọi log cần giữ mãi:

- Audit phục vụ tuân thủ có thể cần thời hạn lưu giữ cụ thể và quyền xóa được kiểm soát.
- Event log dùng replay có thể không được xóa trước khi consumer/projection cần đến.
- Outbox đã giao thành công có thể có retention ngắn hơn nhưng vẫn cần cơ chế đối chiếu.
- Dữ liệu cá nhân có thể có yêu cầu xóa/ẩn danh, phải cân đối với nghĩa vụ kiểm toán hợp lệ.

Partitioning giúp quản lý dữ liệu theo tháng, nhưng **không tự định nghĩa chính sách retention**. Việc `DROP`/`DETACH` partition hoặc xóa dữ liệu phải theo runbook có đối chiếu, backup/restore, người phê duyệt và hệ quả phụ thuộc.

## 24. Ghi sự kiện đến muộn và sửa dữ liệu hồi tố

Một hệ thống nhận đơn từ chi nhánh offline có thể thấy:

```text
09:00  Đơn đã được tạo ở thiết bị cửa hàng.
09:05  Thiết bị mất mạng.
10:30  Thiết bị gửi đơn lên máy chủ.
10:31  PostgreSQL commit bản ghi.
```

Nếu chỉ lưu `created_at DEFAULT now()` trên server, báo cáo “đơn lúc 09:00” sẽ biến thành “đơn lúc 10:31”. Vì vậy nên phân biệt:

```sql
CREATE TABLE offline_order_events (
    event_id UUID PRIMARY KEY,
    store_id BIGINT NOT NULL,
    device_event_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    payload JSONB NOT NULL
);
```

**`device_event_at` do thiết bị gửi không phải luôn là sự thật tuyệt đối**: đồng hồ client có thể sai hoặc bị thao túng. Ứng dụng có thể cần kiểm tra độ lệch, chữ ký nguồn, sequence number, thời gian đồng bộ và xác định quy tắc ưu tiên khi dữ liệu đến muộn.

### Một sự kiện đến muộn có thể đổi lịch sử theo valid time

Giả sử giá 100 được nhập vào ngày 01/11; đến ngày 14/11 mới nhận thông báo giá thực tế từ 05/11 phải là 105. Có thể cần **chẻ khoảng lịch sử**:

```text
Trước sửa:
[01/11, vô hạn) → 100

Sau sửa hợp lệ theo nghiệp vụ:
[01/11, 05/11) → 100
[05/11, vô hạn) → 105
```

Không đơn giản thay giá của cả khoảng cũ, vì như vậy báo cáo cho ngày 03/11 cũng bị sửa thành 105. Và nếu phải biết **ngày 10/11 hệ thống đã tin điều gì**, bạn cần bitemporal, không chỉ viết lại các khoảng valid time.

Với thay đổi hồi tố, nên xác định rõ:

1. Có cho phép sửa quá khứ hay chỉ thêm bản điều chỉnh mới?
2. Truy vấn “as-of valid time” có phải dùng phiên bản đính chính mới nhất?
3. Có cần giữ nguyên thông tin lịch sử **trước khi sửa** để giải trình?
4. Bản sửa có ảnh hưởng invoice/settlement đã chốt không?
5. Hành động sửa có cần phê duyệt, reason và bằng chứng audit không?

## 25. Đồng thời, tính nguyên tử và tính nhất quán thời gian

Thiết kế lịch sử có thể bị sai khi hai request cùng thay đổi một entity. Ví dụ hai worker cùng đọc `valid_to IS NULL`, rồi đều cố chèn bản giá mới. Nếu không có cơ chế bảo vệ, có thể phát sinh các khoảng giao nhau hoặc lost update.

Các lớp bảo vệ nên kết hợp:

- **Transaction:** đóng phiên bản cũ và thêm phiên bản mới trong cùng một đơn vị nguyên tử.
- **Khóa theo entity:** ví dụ `SELECT ... FOR UPDATE` trên hàng parent để tuần tự hóa quá trình đổi giá.
- **Ràng buộc cơ sở dữ liệu:** `EXCLUDE` cho non-overlap, `CHECK` cho khoảng hợp lệ, `FOREIGN KEY` cho object tồn tại.
- **Optimistic concurrency khi phù hợp:** version counter hoặc kiểm tra bản ghi mong đợi trước khi ghi.
- **Retry có giới hạn:** xử lý các lỗi đồng thời có thể retry sau rollback, không gửi lại bừa những thao tác bên ngoài.

### Không nhầm đồng hồ với quyền kiểm soát đồng thời

Hai request có thể cùng `clock_timestamp()` rất gần nhau và cố cập nhật. Timestamp **không thay thế transaction lock hoặc constraint**.

Nếu nghiệp vụ dùng `valid_from` do client quyết định, hai request có thể chọn cùng mốc hoặc mốc đảo ngược. Cần quy tắc chấp nhận/backdate rõ ràng, không dựa vào giả định “timestamp luôn tăng”.

### Đơn vị nghiệp vụ có nhiều bảng

Thay đổi hợp đồng có thể cần:

1. Thêm một phiên bản hợp đồng.
2. Ghi audit lý do và người phê duyệt.
3. Ghi outbox event để gửi thông báo.

Nếu các bước phải cùng thành công, đặt chúng trong **cùng PostgreSQL transaction**. Với audit qua trigger, phần ghi log có thể tự tham gia transaction. Với outbox, ứng dụng ghi event row trước commit rồi worker bên ngoài mới thực hiện gửi.

Không gọi API hoặc broker bên ngoài lâu dài khi đang giữ khóa DB nếu có thể tránh: điều này kéo dài transaction, tăng lock wait và làm retry khó hơn.

## 26. Bảo mật, quyền và độ tin cậy của lịch sử

Lịch sử có thể nhạy cảm **hơn dữ liệu hiện tại** vì lưu cả giá trị cũ đã bị thay đổi hoặc thông tin người dùng mong đã được xóa.

Một số nguyên tắc:

1. **Least privilege:** role đọc báo cáo không mặc nhiên cần `SELECT` mọi trường audit; role ứng dụng không mặc nhiên cần `UPDATE`/`DELETE` trên audit log.
2. **Phân quyền ghi:** chỉ đường ghi được kiểm soát có thể thêm audit records; tránh quyền sửa lịch sử không cần thiết.
3. **Bảo vệ actor:** phân biệt principal đã xác thực với chuỗi actor do client tự gửi.
4. **Giới hạn payload:** chỉ lưu trường cần thiết; cân nhắc masking/redaction với secret, token, thông tin cá nhân.
5. **Chống sửa/xóa:** nếu cần bằng chứng độc lập, chuyển log tới hệ thống kiểm toán tách quyền hoặc lưu trữ bất biến phù hợp.
6. **Retention và xóa hợp lệ:** thiết kế chính sách lưu giữ có thể thực thi, không giữ vô hạn chỉ vì dung lượng còn trống.
7. **Khả năng phục hồi:** backup và restore phải bao gồm cả history/audit/metadata quan trọng.
8. **Giám sát thao tác đặc quyền:** kiểm tra những thay đổi trigger, schema, quyền, hoặc quy trình import bỏ qua luồng ghi log.

### Trigger không ghi toàn bộ sự kiện bảo mật

Row-level trigger không tự ghi **đăng nhập thất bại**, **truy vấn SELECT**, **DDL** hoặc hoạt động đã rollback. Nếu cần ghi những loại hành động đó, phải xây kế hoạch observability/auditing ở đúng tầng, ví dụ log server, extension audit phù hợp hoặc hệ thống truy vết ứng dụng.

## 27. Theo dõi sức khỏe của bảng lịch sử và nhật ký

Dữ liệu lịch sử thường tăng liên tục; thiết kế cần tính tới vận hành:

| Cần quan sát | Vì sao |
|---|---|
| Tốc độ tăng hàng và kích thước table/index | Dự báo dung lượng và tác động lên backup/restore. |
| Tỷ lệ UPDATE/DELETE trong history table | Lịch sử append-only lý tưởng khác bảng cập nhật thường xuyên. |
| Autovacuum, dead tuples, bloat | Cập nhật phiên bản hoặc dọn retention có thể tạo dead tuples. |
| Hiệu năng as-of query và audit lookup | Đảm bảo index phù hợp khi lịch sử nhiều năm. |
| Partition coverage và default partition | Tránh lỗi insert vào tháng chưa được tạo partition. |
| Outbox backlog và thời gian chờ phát | Phát hiện consumer/broker lỗi; tránh mất hoặc gửi chậm sự kiện. |
| Replication slot và WAL retention | CDC consumer chậm có thể làm `pg_wal` tăng nhanh. |
| Bất biến không-overlap/gap theo entity | Phát hiện đường ghi bỏ qua giao thức hoặc dữ liệu legacy sai. |
| Quyền và thay đổi đối tượng audit | Kiểm soát rủi ro vô hiệu hóa/tamper. |

Ví dụ quan sát kích thước bảng:

```sql
SELECT
    pg_size_pretty(
        pg_total_relation_size('product_price_versions'::regclass)
    ) AS price_history_total_size,
    pg_size_pretty(
        pg_total_relation_size('audit.demo_order_changes'::regclass)
    ) AS audit_total_size;
```

Với bảng partitioned, cần xác định đúng cấp cha/các partition khi đo dung lượng: một số hàm trên relation cha không đơn giản cộng tất cả leaf partitions theo cách người dùng mong đợi. Công cụ quan sát nên biết cấu trúc partition tree.

## 28. Chọn thiết kế cho ba tình huống cụ thể

### Tình huống A — Giá bán thay đổi theo ngày

Yêu cầu: đặt lịch giá tương lai, hỏi giá tại ngày T, không được có hai giá chồng lấn.

**Thiết kế phù hợp:** `product_price_versions` với `valid_from/valid_to` hoặc cột `tstzrange`, ràng buộc `EXCLUDE`, query as-of và transaction cập nhật có kiểm soát.

Nếu cần biết giá đã bị sửa hồi tố vào ngày nào và bản cũ lúc trước là gì, mở rộng thành **bitemporal** hoặc giữ assertion/audit riêng.

### Tình huống B — Lịch sử trạng thái đơn hàng

Yêu cầu: xem đơn đã qua `PENDING → PAID → SHIPPED` khi nào, ai phê duyệt.

**Thiết kế phù hợp:** bảng trạng thái hiện tại để phục vụ API nhanh, kết hợp **append-only status events** có entity ID, event type, actor, event time, request ID, sequence number; có thể thêm audit trigger nếu cần ghi cả thay đổi ngoài service.

Nếu cần liên kết tới broker, dùng outbox trong cùng transaction với thay đổi trạng thái.

### Tình huống C — Nhật ký cảm biến/telemetry

Yêu cầu: ghi nhiều sự kiện mỗi giây, dữ liệu có thể đến muộn, lọc theo thiết bị và khoảng thời gian, xóa log cũ theo retention.

**Thiết kế phù hợp:** `event_time` và `received_at` riêng, khóa deduplication ổn định, partition theo một mốc đã chọn, B-tree theo `device_id,event_time` nếu truy vấn thiết bị phổ biến, có thể BRIN theo thời gian khi dữ liệu tương quan vật lý.

Không thay thời gian cảm biến bằng `DEFAULT now()` nếu mục tiêu là phân tích thời điểm sự kiện xảy ra; nhưng cũng không tin tuyệt đối timestamp từ thiết bị.

## 29. Các sai lầm thường gặp

**“Chỉ cần updated_at là có lịch sử.”** Không. `updated_at` lưu thời điểm sửa cuối, không lưu giá trị cũ hay thời gian hiệu lực của mọi phiên bản.

**“PostgreSQL MVCC cho phép đọc lại mọi phiên bản đã UPDATE từ nhiều tháng trước.”** Không. MVCC phục vụ đồng thời và snapshot transaction; tuple cũ có thể được vacuum thu hồi.

**“TIMESTAMPTZ giữ nguyên tên múi giờ mà người dùng nhập.”** Không. Nó mô tả instant và hiển thị theo session time zone; muốn giữ IANA zone gốc cần cột riêng.

**“Mỗi ngày luôn dài 24 giờ.”** Không trong tất cả vùng có DST; query ngày địa phương cần ranh giới chính xác theo vùng.

**“now() tăng sau mỗi câu SQL.”** Không trong một transaction; nó gắn với thời điểm bắt đầu transaction.

**“valid_to IS NULL luôn có nghĩa giá đang có hiệu lực hôm nay.”** Không, nếu `valid_from` ở tương lai.

**“CHECK(valid_to > valid_from) ngăn mọi overlap.”** Không. Nó kiểm tra từng hàng, không ràng buộc các hàng cùng entity.

**“EXCLUDE ngăn overlap thì cũng bảo đảm timeline không có khoảng trống.”** Không. Ràng buộc overlap không tự kiểm tra continuity.

**“Chỉ cần lưu bản mới nhất và audit old/new là truy vấn as-of dễ dàng.”** Không nhất thiết. Audit event có thể phải replay và không diễn đạt valid time, nhất là khi có sửa hồi tố.

**“Bitemporal chỉ cần hai cột created_at/updated_at.”** Không. Nó cần phiên bản nhận định theo cả valid time và recorded/system time.

**“Trigger audit là log không thể bị giả mạo.”** Không. Quyền cao, thay đổi trigger và hoạt động ngoài DML có thể vượt khả năng của trigger.

**“Nếu transaction rollback, audit row vẫn còn để chứng minh đã thử thao tác.”** Không khi audit được ghi trong cùng transaction; muốn ghi cả attempt cần cơ chế khác.

**“Audit ID luôn là thứ tự commit.”** Không. Sequence có thể có lỗ hổng và được cấp trước commit.

**“CDC tự cho biết người dùng nghiệp vụ nào đã phê duyệt.”** Không. Cần metadata actor ở tầng phù hợp.

**“Đã gửi outbox là chắc chắn consumer chỉ nhận một lần.”** Không. Outbox thường cần consumer idempotent vì có thể giao lại sau sự cố.

**“Partitioned table có event_id identity thì event_id chắc chắn unique toàn mọi partition.”** Không tự động có ràng buộc uniqueness toàn cục khi partition key không thuộc khóa.

**“Thêm mọi index vào audit log để query nhanh hơn.”** Mỗi index tăng chi phí ghi, WAL, dung lượng và bảo trì; cần tối ưu theo truy vấn thực.

## 30. Bài tập thực hành

### Bài 1 — Chọn kiểu thời gian

Cho các dữ liệu:

1. Ngày sinh khách hàng.
2. Thời điểm thanh toán ngân hàng xác nhận.
3. Giờ mở cửa **09:00 mỗi ngày** của một cửa hàng ở vùng `Europe/Berlin`.
4. Thời lượng giữ chỗ 90 phút.
5. Thời điểm cảm biến đo và thời điểm server nhận gói tin.

Hãy chọn `date`, `time`, `timestamptz`, `interval` hoặc tổ hợp phù hợp. Giải thích khi nào cần lưu tên vùng giờ IANA riêng.

### Bài 2 — Truy vấn as-of

Với lịch sử giá của sản phẩm 42:

```text
[01/11 00:00, 10/11 00:00) -> 100000
[10/11 00:00, 14/11 09:00) -> 115000
[14/11 09:00, vô hạn)   -> 125000
```

Hãy viết SQL tìm giá tại 09/11 23:59, đúng 10/11 00:00 và đúng 14/11 09:00. Giải thích vì sao `[)` tránh chồng lấn ở ranh giới.

### Bài 3 — Ràng buộc overlap

Một bảng đặt phòng có `room_id` và `booked_period tstzrange`. Hãy thiết kế:

- `CHECK (NOT isempty(booked_period))`.
- `EXCLUDE USING gist` không cho hai đặt phòng đã xác nhận của cùng phòng chồng khoảng.
- Điều kiện cho phép hai đặt phòng kề nhau, một kết thúc đúng lúc đặt phòng khác bắt đầu.

*Gợi ý:* extension `btree_gist` cung cấp toán tử `=` phù hợp cho kiểu ID thường dùng, `&&` kiểm tra overlap, và có thể dùng **partial exclusion constraint** khi chỉ đặt phòng `CONFIRMED` cần loại trừ nhau.

### Bài 4 — Transaction cập nhật giá

Viết một transaction cập nhật giá 42 từ 125.000 thành 129.000 tại T cố định. Giải thích vì sao cần đóng phiên bản cũ và chèn phiên bản mới trong cùng transaction, tại sao nên khóa hàng parent và ràng buộc `EXCLUDE` vẫn cần thiết.

### Bài 5 — Phân biệt valid và recorded time

Ngày 14/11, hệ thống phát hiện mức giá đã có hiệu lực từ 01/11 thực ra là 120 thay vì 100. Hãy mô tả cách trả lời:

1. Giá **được cho là có hiệu lực** tại 05/11 theo dữ liệu đã sửa.
2. Giá mà hệ thống **đã tin vào 10/11** cho ngày 05/11.

Giải thích vì sao một bảng SCD2 chỉ có valid time không nhất thiết trả lời đủ cả hai câu hỏi.

### Bài 6 — Audit trigger và rollback

Một trigger `AFTER UPDATE` ghi `OLD`/`NEW` vào bảng audit trong cùng transaction. Ứng dụng cập nhật đơn rồi `ROLLBACK`. Hãy dự đoán trạng thái đơn và audit record sau rollback. Nêu thêm cách tiếp cận nếu hệ thống cần ghi lại **nỗ lực truy cập bị từ chối**.

### Bài 7 — Outbox và mất phản hồi

Ứng dụng commit `OrderPaid` cùng outbox row. Worker gửi message thành công nhưng mất kết nối trước khi đánh dấu `published_at`. Lần chạy sau worker gửi lại.

Giải thích vì sao consumer phải dùng `event_id`/idempotency, và vì sao việc đặt outbox trong cùng transaction khắc phục một loại lỗi nhưng không tự tạo exactly-once trên toàn hệ thống.

### Bài 8 — Lịch sử lớn và chỉ mục

Hệ thống lưu 200 triệu sự kiện, truy vấn thường theo `device_id` và `event_time`; dữ liệu phần lớn được insert theo thứ tự thời gian nhưng có backfill mỗi ngày.

Hãy đề xuất B-tree, BRIN hoặc partitioning phù hợp, nêu điều kiện BRIN mất hiệu quả và giải thích giới hạn uniqueness của partitioned table.

### Bài 9 — Nhật ký có đủ chống giả mạo không?

Một bảng audit chứa actor, time, old/new, nhưng tài khoản ứng dụng có quyền `UPDATE` và `DELETE` trên chính bảng audit, đồng thời administrator có thể tắt trigger. Hãy chỉ ra các rủi ro và đề xuất cải tiến quyền, nguồn log độc lập, bảo mật payload và retention.

### Bài 10 — Quy trình sửa hồi tố

Hợp đồng A có phí 1.000.000 hiệu lực từ 01/10. Ngày 15/11 bộ phận nghiệp vụ yêu cầu phí 900.000 có hiệu lực từ 01/11, nhưng hệ thống đã xuất một số hóa đơn trong khoảng 01–14/11.

Hãy đề xuất quy trình: phê duyệt, versioning valid time, recorded time, xử lý hóa đơn đã chốt, audit reason và phát event điều chỉnh, thay vì âm thầm `UPDATE` bản ghi cũ.

## Kết luận

Thiết kế dữ liệu thời gian trong PostgreSQL bắt đầu từ việc **chọn đúng ý nghĩa của mỗi mốc**: sự kiện xảy ra khi nào, hệ thống nhận khi nào, giá trị có hiệu lực trong khoảng nào, và hệ thống đã tin nhận định đó từ lúc nào. Kiểu **`timestamptz`** giúp lưu thời điểm tuyệt đối; **`date`**, `time` và tên vùng giờ riêng phù hợp hơn với những quy tắc theo lịch địa phương. Dùng **khoảng `[)`**, `tstzrange` và `EXCLUDE USING gist` để mô hình hóa phiên bản lịch sử nhất quán mà không chồng lấn.

**Bảng phiên bản** phục vụ truy vấn trạng thái *as-of*, **bitemporal** phục vụ cả thời gian hiệu lực và lịch sử điều hệ thống từng biết, **audit log** phục vụ truy vết thay đổi, còn **outbox/CDC/event sourcing** giải quyết những bài toán truyền sự kiện hoặc tái dựng trạng thái khác nhau. Những mô hình này có thể kết hợp, nhưng không thay thế nhau một cách tự động.

Một thiết kế tốt không chỉ chạy được truy vấn hôm nay: nó cần **transaction và ràng buộc chống xung đột**, chỉ mục phù hợp với truy vấn lịch sử, partition/retention có kiểm soát, actor và dữ liệu nhạy cảm được bảo vệ, khả năng phục hồi khi có sự cố và quy trình sửa hồi tố minh bạch. Khi các yêu cầu đó được xác định từ đầu, PostgreSQL có thể lưu không chỉ “dữ liệu bây giờ” mà cả **bằng chứng đáng tin về dữ liệu đã thay đổi như thế nào qua thời gian**.
