# Toán tử và hàm trên khoảng giá trị trong PostgreSQL

Một hệ thống đặt phòng cần biết hai lượt đặt có **trùng thời gian** không. Một hệ thống quản lý giá bán cần xác định bảng giá nào **có hiệu lực tại ngày giao dịch**. Một hệ thống kho cần lưu các dải số lô, còn dịch vụ phân quyền cần kiểm tra một thời điểm có nằm trong giai đoạn cấp quyền hay không.

Nếu chỉ lưu hai cột `start_at` và `end_at`, ứng dụng thường phải tự viết nhiều điều kiện so sánh và tự thống nhất quy ước về **cận đóng** (có lấy giá trị tại ranh giới) hay **cận mở** (không lấy giá trị đó). PostgreSQL cung cấp **kiểu khoảng giá trị (*range types*)** cùng các toán tử và hàm chuyên dụng để diễn đạt trực tiếp:

- `@>`: khoảng **chứa** một giá trị hoặc một khoảng khác.
- `<@`: giá trị/khoảng **nằm trong** một khoảng khác.
- `&&`: hai khoảng **giao nhau** (có phần tử chung).
- `-|-`: hai khoảng **liền kề** nhưng không giao nhau.
- `+`, `*`, `-`: **hợp, giao, hiệu** của các khoảng, với những giới hạn cần hiểu.
- `lower()`, `upper()`, `lower_inc()`, `upper_inc()`, `lower_inf()`, `upper_inf()`, `isempty()`: xem **hai cận** và tình trạng rỗng/vô hạn của khoảng.
- **Multirange** (PostgreSQL 14+) để biểu diễn **nhiều khoảng không liền nhau** trong một giá trị, cùng `range_agg()`, `range_intersect_agg()` và `range_merge()` cho các bài toán tổng hợp.

Bài học thuộc chương **Hàm và biểu thức** trong module *Database Engine Relational PostgreSQL*. Nội dung đi từ cú pháp cơ bản tới thiết kế truy vấn lịch đặt phòng, ràng buộc không chồng lấn, chỉ mục GiST, sai lầm ở ranh giới thời gian, hàm xử lý multirange và bài tập thực hành.

> **Điều kiện thực hành:** Các ví dụ SQL dùng PostgreSQL thông dụng. **Multirange** và các thao tác tổng hợp liên quan cần PostgreSQL **14 trở lên**. Lệnh `CREATE EXTENSION btree_gist` để minh họa loại trừ theo ID phòng có thể cần quyền phù hợp. Hãy chạy `SHOW server_version;` trước khi thử.

## 1. Khoảng giá trị là gì và khác INTERVAL như thế nào?

Một **range** mô tả tập các giá trị nằm giữa một **cận dưới** (*lower bound*) và một **cận trên** (*upper bound*).

Ví dụ:

```text
Khoảng [10, 20) :

10 ●──────────────────○ 20
   lấy 10       không lấy 20

Khoảng (10, 20] :

10 ○──────────────────● 20
   không lấy 10      lấy 20
```

Ký hiệu:

| Ký hiệu | Nghĩa |
|---|---|
| `[` ở cận dưới | Bao gồm cận dưới |
| `(` ở cận dưới | Không bao gồm cận dưới |
| `]` ở cận trên | Bao gồm cận trên |
| `)` ở cận trên | Không bao gồm cận trên |
| `[a,b]` | Bao gồm cả a lẫn b |
| `[a,b)` | Bao gồm a, không bao gồm b |
| `(a,b]` | Không bao gồm a, bao gồm b |
| `(a,b)` | Không bao gồm cả hai |

**`[10,20)`** thường được gọi là quy ước **nửa mở** (*half-open interval*). Nếu hai lượt đặt lần lượt kết thúc lúc 10:00 và bắt đầu lúc 10:00, chúng không trùng nhau khi cùng dùng `[)`.

### 1.1. Range khác kiểu INTERVAL

Trong PostgreSQL:

- **`INTERVAL`** mô tả **khoảng thời lượng**, ví dụ `INTERVAL '90 minutes'` hoặc `INTERVAL '2 days'`.
- **`tstzrange`** mô tả **tập các thời điểm** từ lúc bắt đầu đến lúc kết thúc, ví dụ `[09:00,10:30)` vào một ngày cụ thể.

```sql
SELECT
    INTERVAL '90 minutes' AS duration,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        TIMESTAMPTZ '2026-11-14 10:30:00+07',
        '[)'
    ) AS period;
```

Một thời lượng 90 phút tự nó không cho biết **bắt đầu lúc nào**. Một `tstzrange` lưu **hai ranh giới thời điểm** và quy tắc bao gồm chúng. Không dùng `INTERVAL` thay range cho bài toán kiểm tra hai lịch có chồng lấn.

### 1.2. Range là một giá trị có kiểu, không phải chuỗi ký tự tùy ý

Chuỗi `'[1,5)'` có thể được ép thành `int4range`, nhưng sau khi ép nó là **giá trị khoảng của PostgreSQL**, có ngữ nghĩa kiểm tra giao/chứa, chuẩn hóa cận và lưu trữ riêng.

```sql
SELECT
    '[1,5)'::int4range AS range_from_literal,
    int4range(1, 5, '[)') AS range_from_constructor;
```

Hai biểu thức trên tương đương về tập số nguyên. Khi viết ứng dụng, có thể dùng constructor, bind parameter và ép kiểu rõ ràng để tránh tự nối chuỗi SQL tạo range từ đầu vào chưa kiểm soát.

## 2. Các kiểu range có sẵn trong PostgreSQL

| Kiểu range | Kiểu dữ liệu của phần tử | Ví dụ |
|---|---|---|
| `int4range` | `integer` / `int4` | `int4range(1, 10)` |
| `int8range` | `bigint` / `int8` | `int8range(10000000000, 20000000000)` |
| `numrange` | `numeric` | `numrange(1.5, 2.75)` |
| `daterange` | `date` | `daterange(DATE '2026-01-01', DATE '2026-02-01')` |
| `tsrange` | `timestamp without time zone` | `tsrange(TIMESTAMP '2026-11-14 09:00', TIMESTAMP '2026-11-14 10:00')` |
| `tstzrange` | `timestamp with time zone` / `timestamptz` | `tstzrange(TIMESTAMPTZ '2026-11-14 09:00+07', TIMESTAMPTZ '2026-11-14 10:00+07')` |

**Chọn đúng kiểu phần tử** quan trọng hơn tên gọi ngắn:

- Khoảng ID nguyên dùng `int4range` hoặc `int8range` theo miền ID.
- Giá/khối lượng chính xác theo số thập phân dùng `numrange`.
- Ngày hiệu lực (không cần giờ) dùng `daterange`.
- Giờ địa phương mang ý nghĩa “đồng hồ trên tường” không gắn timezone có thể dùng `tsrange` nếu mô hình thực sự yêu cầu.
- Lịch đặt phòng, lịch họp hoặc cửa sổ thời điểm thực trên toàn cầu thường thích hợp với **`tstzrange`**, vì so sánh các thời điểm đã xét offset/múi giờ.

PostgreSQL còn cho phép định nghĩa **custom range types** khi kiểu phần tử có thứ tự và được hỗ trợ bằng các hàm/operator class thích hợp. Bài này dùng những kiểu xây dựng sẵn để tập trung vào toán tử và hàm.

### 2.1. Các kiểu multirange tương ứng

Từ PostgreSQL 14 có:

| Range | Multirange |
|---|---|
| `int4range` | `int4multirange` |
| `int8range` | `int8multirange` |
| `numrange` | `nummultirange` |
| `daterange` | `datemultirange` |
| `tsrange` | `tsmultirange` |
| `tstzrange` | `tstzmultirange` |

Multirange biểu diễn một tập gồm **không, một hoặc nhiều đoạn khoảng** không giao nhau. Các đoạn chồng lấn hoặc liền nhau được chuẩn hóa để có biểu diễn thống nhất. Phần này đặc biệt hữu ích khi hiệu hai khoảng tạo ra **hai đoạn rời**, điều mà một giá trị range đơn không biểu diễn được.

## 3. Khởi tạo range bằng constructor và literal

### 3.1. Constructor với cận dưới, cận trên

```sql
SELECT
    int4range(1, 5) AS default_bounds,
    int4range(1, 5, '[)') AS half_open,
    int4range(1, 5, '[]') AS both_inclusive,
    int4range(1, 5, '()') AS both_exclusive;
```

Các constructor thường có tham số tùy chọn thứ ba chọn `[)`, `[]`, `()` hoặc `(]`. Nếu không đưa tham số, mặc định thường là **`[)`**.

**Lưu ý quan trọng:** Với kiểu **rời rạc** như số nguyên, PostgreSQL có thể **chuẩn hóa cận**; vì vậy kết quả hiển thị không nhất thiết giữ nguyên dấu ngoặc lúc nhập.

### 3.2. Range literal

```sql
SELECT
    '[1,5)'::int4range AS a,
    '(1,5]'::int4range AS b,
    '[2026-01-01,2026-02-01)'::daterange AS c;
```

Trong SQL, literal range là chuỗi có cú pháp đặc biệt được cast sang kiểu range. Với thời gian có offset phức tạp, constructor và ép kiểu `TIMESTAMPTZ` rõ ràng thường giúp ví dụ dễ đọc hơn.

### 3.3. Cận mở/đóng không chỉ là cách trình bày

```sql
SELECT
    numrange(1, 5, '[)') @> 1::numeric AS includes_one,
    numrange(1, 5, '[)') @> 5::numeric AS includes_five,
    numrange(1, 5, '(]') @> 1::numeric AS excludes_one,
    numrange(1, 5, '(]') @> 5::numeric AS includes_five_in_other_range;
```

Kết quả dự kiến: `true`, `false`, `false`, `true`.

Toán tử **`@>`** thể hiện kiểm tra phần tử nằm trong khoảng. Thay đổi dấu ngoặc ở cận có thể làm kết quả khác ngay ở một giá trị biên.

### 3.4. Thứ tự cận

Một range **không rỗng** cần miền giá trị hợp lý: cận dưới không lớn hơn cận trên theo thứ tự của kiểu. Ví dụ constructor đảo cận `int4range(10, 2)` không phải cách biểu diễn khoảng “đi lùi”; PostgreSQL sẽ từ chối cận sai.

Nếu nghiệp vụ có “bắt đầu” và “kết thúc” bị đảo, ứng dụng cần **báo lỗi hoặc đổi chỗ có chủ đích** theo hợp đồng, không mong range tự suy diễn một hướng thời gian ngược.

## 4. Discrete range và continuous range: chuẩn hóa cận

Một điểm tinh tế của PostgreSQL là **cùng một tập phần tử có thể viết bằng nhiều ký hiệu**. Với kiểu **rời rạc** như `integer` và `date`, PostgreSQL có hàm *canonicalization* để đưa khoảng về dạng chuẩn.

### 4.1. Ví dụ int4range

Các khoảng sau mô tả **cùng tập số nguyên**:

```text
[1,5)   = {1,2,3,4}
(0,4]   = {1,2,3,4}
[1,4]   = {1,2,3,4}
```

Thử:

```sql
SELECT
    int4range(1, 5, '[)') AS a,
    int4range(0, 4, '(]') AS b,
    int4range(1, 4, '[]') AS c,
    int4range(1, 5, '[)') = int4range(0, 4, '(]') AS same_set;
```

Kết quả `same_set=true`. Các dạng `int4range` thường được chuẩn hóa thành **`[1,5)`**.

**Vì sao?** Giữa hai số nguyên 4 và 5 **không có số nguyên nào khác**. Chuyển cận trên `4]` thành `5)` vẫn giữ nguyên tập phần tử.

### 4.2. Ví dụ daterange

```sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-01-31', '[]')
        AS january_inclusive,
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)')
        AS january_half_open;
```

Hai giá trị có thể hiển thị cùng dạng `[2026-01-01,2026-02-01)` vì ngày là miền rời rạc từng ngày. Cách viết nửa mở rất thuận tiện cho các khoảng ngày nối tiếp.

### 4.3. numrange và tsrange không có “ngày kế tiếp” hoặc “số kế tiếp” đơn giản

Với `numeric` và thời gian, không có một bước kế tiếp cố định theo cùng ý nghĩa của `integer + 1` hay `date + 1 day`:

```sql
SELECT
    numrange(1, 5, '[)') AS a,
    numrange(1, 5, '(]') AS b,
    numrange(1, 5, '[)') = numrange(1, 5, '(]') AS same_set;
```

Kết quả `same_set=false`. Khoảng thứ nhất chứa 1 nhưng không chứa 5; khoảng thứ hai thì ngược lại. Không mong PostgreSQL tự đổi cận để tạo cùng biểu diễn như `int4range`.

### 4.4. Tại sao canonicalization quan trọng?

- Range có thể thay đổi **dạng in ra** ngay khi được lưu.
- So sánh `=` trên range có ý nghĩa theo biểu diễn/chuẩn hóa của kiểu range, không chỉ so chuỗi literal đầu vào.
- Một constraint/unique index trên range không đồng nghĩa với ràng buộc không chồng lấn: hai khoảng khác nhau vẫn có thể **giao nhau** dù `=` là false.
- Khi trình bày ngày cuối của `daterange` với quy ước `[)`, `upper(range)` là **ngày bắt đầu không còn hiệu lực**, không phải “ngày cuối được bao gồm”.

## 5. Khoảng rỗng và khoảng không có cận

Không phải range nào cũng chứa phần tử. Cũng không phải range nào cũng có đủ hai cận hữu hạn.

### 5.1. empty range

```sql
SELECT
    'empty'::int4range AS empty_literal,
    isempty('empty'::int4range) AS literal_is_empty,
    int4range(5, 5, '[)') AS empty_by_bounds,
    isempty(int4range(5, 5, '[)')) AS computed_is_empty;
```

Kết quả hai phép kiểm tra `isempty` đều là `true`.

Do `[5,5)` bao gồm cận dưới 5 nhưng không bao gồm cận trên 5, tập không chứa phần tử nào. PostgreSQL thường hiển thị kiểu range rỗng dưới dạng **`empty`**.

### 5.2. Cùng cận nhưng hai dấu đóng

```sql
SELECT
    int4range(5, 5, '[]') AS one_integer,
    isempty(int4range(5, 5, '[]')) AS is_empty,
    int4range(5, 5, '[]') @> 5 AS contains_five;
```

Đây là khoảng chứa **một phần tử 5**, không rỗng. Với `int4range`, dạng chuẩn có thể hiển thị thành `[5,6)`.

**Đối chiếu:** `[5,5]` trên miền số nguyên chứa 5; `[5,5)` thì rỗng.

### 5.3. Khoảng không có cận dưới hoặc trên

Một cận không được chỉ định bằng `NULL` trong constructor sẽ là **unbounded**:

```sql
SELECT
    int4range(NULL, 10, '[)') AS less_than_ten,
    int4range(10, NULL, '[)') AS from_ten_onward,
    int4range(NULL, NULL) AS all_integers;
```

Những khoảng này lần lượt biểu diễn các số nguyên **nhỏ hơn 10**, **từ 10 trở đi** và **toàn bộ miền số nguyên**.

Lưu ý các cận không được chỉ định **không phải** giá trị `NULL` đang được chứa trong range. Range xác định một tập **giá trị không NULL thuộc miền phần tử**; một cận bỏ trống chỉ diễn đạt miền kéo dài vô hạn theo hướng đó.

### 5.4. Unbounded khác kiểu phần tử có giá trị infinity

Các kiểu như `date`, `timestamp`, `timestamptz` có thể có giá trị phần tử đặc biệt `infinity`/`-infinity`. Nhưng:

- **Cận không xác định** (unbounded) nghĩa là range không có bound tại phía đó.
- **Bound có giá trị `infinity`** là một **giá trị cận** thuộc hệ thống biểu diễn của kiểu thời gian, với quy tắc bao gồm/loại trừ riêng.

Trong thiết kế dữ liệu, đừng xem `upper_inf(range)` là cách hỏi “cận trên có chuỗi `infinity` hay không”. Nó hỏi cận trên có **unbounded** hay không, không đồng nhất với một bound được đặt bằng giá trị timestamp đặc biệt `infinity`.

Ví dụ trực quan:

```sql
SELECT
    upper_inf(tstzrange(
        TIMESTAMPTZ '2026-01-01 00:00:00+00',
        NULL,
        '[)'
    )) AS is_unbounded_upper,
    upper_inf(tstzrange(
        TIMESTAMPTZ '2026-01-01 00:00:00+00',
        'infinity'::timestamptz,
        '[)'
    )) AS uses_infinity_value_as_bound;
```

Về ý nghĩa, biểu thức thứ nhất là `true`, biểu thức thứ hai là `false`. Nếu cần xử lý các giá trị infinity của kiểu thời gian, phải xét cả bound type, tính inclusive và yêu cầu nghiệp vụ.

## 6. Hàm kiểm tra cận của range

PostgreSQL có nhóm hàm hữu ích để xem ranh giới thực sự của một range.

| Hàm | Câu hỏi trả lời | Ghi chú |
|---|---|---|
| `lower(r)` | Cận dưới có giá trị gì? | Có thể trả NULL nếu unbounded hoặc empty |
| `upper(r)` | Cận trên có giá trị gì? | Có thể trả NULL nếu unbounded hoặc empty |
| `lower_inc(r)` | Cận dưới có được bao gồm? | Với bound không tồn tại, không coi là cận đóng |
| `upper_inc(r)` | Cận trên có được bao gồm? | Với bound không tồn tại, không coi là cận đóng |
| `lower_inf(r)` | Có thiếu cận dưới (unbounded) không? | Không đồng nghĩa literal `-infinity` |
| `upper_inf(r)` | Có thiếu cận trên (unbounded) không? | Không đồng nghĩa literal `infinity` |
| `isempty(r)` | Range có rỗng không? | Kiểm tra tập không có phần tử |

### 6.1. Đọc hai cận từ một daterange

```sql
WITH periods AS (
    SELECT
        daterange(DATE '2026-02-01',
                  DATE '2026-03-01', '[)') AS r
)
SELECT
    r,
    lower(r) AS start_date,
    upper(r) AS end_exclusive,
    lower_inc(r) AS includes_start,
    upper_inc(r) AS includes_end,
    lower_inf(r) AS has_no_start_bound,
    upper_inf(r) AS has_no_end_bound,
    isempty(r) AS is_empty
FROM periods;
```

Kết quả về mặt ý nghĩa:

- `start_date = 2026-02-01`.
- `end_exclusive = 2026-03-01`.
- `includes_start = true`.
- `includes_end = false`.
- Cả `lower_inf` và `upper_inf` đều là `false`.
- `is_empty = false`.

Tên alias `end_exclusive` nhắc người đọc: đây **không** phải ngày 01/03 được bao gồm, mà là ranh giới đầu tiên **ngoài** khoảng.

### 6.2. Cách đọc một range có cận thiếu

```sql
SELECT
    lower_inf(int4range(NULL, 20)) AS no_lower,
    upper_inf(int4range(NULL, 20)) AS no_upper,
    upper(int4range(NULL, 20)) AS upper_bound;
```

Kết quả: `no_lower=true`, `no_upper=false`, `upper_bound=20`.

Khi `lower()` hoặc `upper()` trả NULL, cần xét tiếp `isempty()`/`lower_inf()`/`upper_inf()` để phân biệt **không có cận** với **range rỗng**. Chỉ nhìn giá trị trả ra của `lower`/`upper` là chưa đủ.

### 6.3. Áp dụng vào dữ liệu bảng

```sql
CREATE SCHEMA IF NOT EXISTS range_lab;

CREATE TABLE range_lab.price_rules (
    rule_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_code TEXT NOT NULL,
    valid_days DATERANGE NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT chk_price_rule_not_empty
        CHECK (NOT isempty(valid_days))
);

INSERT INTO range_lab.price_rules
    (product_code, valid_days, unit_price)
VALUES
    ('SKU-A', daterange(DATE '2026-01-01', DATE '2026-02-01', '[)'), 120),
    ('SKU-A', daterange(DATE '2026-02-01', DATE '2026-03-01', '[)'), 135),
    ('SKU-B', daterange(DATE '2026-01-15', DATE '2026-02-15', '[)'),  80);
```

Kiểm tra:

```sql
SELECT
    rule_id,
    product_code,
    valid_days,
    lower(valid_days) AS starts_on,
    upper(valid_days) AS stops_before,
    unit_price
FROM range_lab.price_rules
ORDER BY product_code, lower(valid_days);
```

Mỗi hàng là **một quy tắc giá có hiệu lực trong một khoảng ngày**. Hai kỳ của `SKU-A` tiếp giáp ở ngày 01/02, nhưng không chồng lấn vì dùng `[)`.

## 7. Toán tử @>: range chứa phần tử hoặc range khác

### 7.1. Kiểm tra một ngày có thuộc khoảng hiệu lực không

```sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)')
        @> DATE '2026-01-01' AS includes_first_day,
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)')
        @> DATE '2026-01-31' AS includes_last_day,
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)')
        @> DATE '2026-02-01' AS includes_next_month;
```

Kết quả: **`true`, `true`, `false`**.

Đây là câu hỏi phổ biến: **“Ngày giao dịch có nằm trong thời hạn của bảng giá?”**

```sql
SELECT product_code, unit_price
FROM range_lab.price_rules
WHERE product_code = 'SKU-A'
  AND valid_days @> DATE '2026-01-20';
```

Kết quả là giá 120 cho tháng 1.

### 7.2. Kiểm tra một range có chứa range khác không

```sql
SELECT
    int4range(1, 10) @> int4range(3, 7)
        AS inner_fits,
    int4range(3, 7) @> int4range(1, 10)
        AS reverse_fits;
```

Kết quả: `true` và `false`.

Ở đây `@>` nhận **range ở bên phải**, không chỉ một phần tử đơn.

### 7.3. Toán tử <@ theo chiều ngược lại

```sql
SELECT
    5 <@ int4range(1, 10) AS point_inside,
    int4range(3, 7) <@ int4range(1, 10) AS range_inside,
    int4range(1, 10) <@ int4range(3, 7) AS large_inside_small;
```

Kết quả: `true`, `true`, `false`.

Hai dạng ngữ nghĩa tương ứng:

```text
range @> element   <=> element <@ range
rangeA @> rangeB   <=> rangeB <@ rangeA
```

Chúng dễ dùng để biểu đạt luật nghiệp vụ thay vì lặp các điều kiện `start <= x AND x < end` trong mọi câu truy vấn.

### 7.4. Chọn kiểu phần tử phù hợp

Với `tstzrange`, hãy so với **`TIMESTAMPTZ`**, không phải một chuỗi thời gian không rõ timezone:

```sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00+07',
    TIMESTAMPTZ '2026-11-14 10:00+07',
    '[)'
) @> TIMESTAMPTZ '2026-11-14 09:30+07' AS is_within;
```

Kết quả `true`.

## 8. Toán tử &&: hai khoảng giao nhau

`&&` trả `true` khi hai khoảng **có ít nhất một phần tử chung**.

```sql
SELECT
    int4range(1, 5) && int4range(3, 8)
        AS overlaps,
    int4range(1, 5) && int4range(5, 8)
        AS touching_at_boundary,
    int4range(1, 5) && int4range(8, 10)
        AS separated;
```

Kết quả: `true`, `false`, `false`.

### 8.1. Vì sao hai khoảng [1,5) và [5,8) không giao?

```text
[1,5): 1 ●────────────○ 5
[5,8):                 5 ●──────────○ 8

Điểm 5:
 - Không thuộc khoảng thứ nhất.
 - Có thuộc khoảng thứ hai.

Không có phần tử chung  =>  && trả false.
```

Trong lịch đặt phòng, điều này giúp một khách **trả phòng lúc 10:00** và người tiếp theo **nhận phòng lúc 10:00** mà không bị nhận nhầm là lịch trùng.

### 8.2. Ranh giới có thể thực sự giao khi hai cận đều đóng

Với `numrange`:

```sql
SELECT
    numrange(1, 5, '[]') &&
    numrange(5, 8, '[)') AS both_include_five;
```

Kết quả `true` vì giá trị 5 thuộc cả hai khoảng.

Không kết luận “hai khoảng có đầu cuối bằng nhau thì luôn không overlap”. Phải xét **dấu ngoặc và sự chuẩn hóa của kiểu range**.

### 8.3. Kiểm tra hai khoảng ngày

```sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)')
        &&
    daterange(DATE '2026-01-20', DATE '2026-02-20', '[)')
        AS overlap_january_february;
```

Kết quả `true`: khoảng thứ hai chứa các ngày 20–31/01 cũng thuộc khoảng đầu.

### 8.4. Tìm các bản ghi có lịch giao khoảng yêu cầu

```sql
SELECT rule_id, product_code, valid_days
FROM range_lab.price_rules
WHERE product_code = 'SKU-A'
  AND valid_days &&
      daterange(DATE '2026-01-25', DATE '2026-02-10', '[)')
ORDER BY lower(valid_days);
```

Hai quy tắc giá tháng 1 và tháng 2 của `SKU-A` đều giao với cửa sổ 25/01–10/02. Đây là kiểu truy vấn “tìm mọi khoảng có hiệu lực ít nhất một phần trong kỳ báo cáo”.

## 9. Toán tử -|-: hai khoảng liền kề

`-|-` kiểm tra hai khoảng **kề nhau**, có thể ghép thành một khoảng liên tục **mà không để lỗ hổng**, nhưng không có phần tử chung.

```sql
SELECT
    int4range(1, 5) -|- int4range(5, 8)
        AS adjacent,
    int4range(1, 5) -|- int4range(6, 8)
        AS gap_between,
    int4range(1, 5) -|- int4range(4, 8)
        AS overlaps_instead;
```

Kết quả: `true`, `false`, `false`.

### 9.1. Trùng và liền kề là hai khái niệm khác nhau

| Hai khoảng | `&&` (overlap) | `-|-` (adjacent) |
|---|---|---|
| `[1,5)` và `[3,8)` | true | false |
| `[1,5)` và `[5,8)` | false | true |
| `[1,5)` và `[6,8)` | false | false |

Trong bài toán phòng họp:

- **Overlap** thường phải bị từ chối khi cùng phòng.
- **Adjacent** thường được chấp nhận: lịch mới bắt đầu đúng lúc lịch cũ kết thúc.
- **Separated** cũng được chấp nhận vì có khoảng trống giữa hai lượt.

### 9.2. Khác biệt với `=`

Hai range có thể **bằng nhau**, **giao nhau nhưng không bằng nhau**, **liền nhau**, hoặc **tách rời**. Nếu mục tiêu là cấm lịch trùng, dùng `UNIQUE(period)` chỉ cấm **hai khoảng hoàn toàn bằng nhau**; nó **không cấm** `[09:00,10:00)` cùng `[09:30,10:30)`. Cần toán tử **`&&`** trong truy vấn hoặc exclusion constraint.

## 10. Các toán tử quan hệ vị trí khác

Ngoài chứa/giao/kề, PostgreSQL có các toán tử giúp so sánh vị trí tương đối của hai khoảng.

| Toán tử | Ý nghĩa trực quan |
|---|---|
| `<<` | Khoảng bên trái nằm **hoàn toàn trước** khoảng bên phải |
| `>>` | Khoảng bên trái nằm **hoàn toàn sau** khoảng bên phải |
| `&<` | Khoảng bên trái **không kéo dài sang phải** quá khoảng bên phải |
| `&>` | Khoảng bên trái **không kéo dài sang trái** quá khoảng bên phải |
| `-|-` | Hai khoảng liền kề |
| `&&` | Hai khoảng có giao |
| `@>` | Bên trái chứa bên phải |
| `<@` | Bên trái nằm trong bên phải |

Ví dụ dễ quan sát:

```sql
SELECT
    int4range(1, 4) << int4range(6, 9)
        AS strictly_left,
    int4range(9, 12) >> int4range(6, 9)
        AS strictly_right,
    int4range(1, 5) &< int4range(3, 8)
        AS does_not_extend_right,
    int4range(3, 8) &> int4range(1, 5)
        AS does_not_extend_left;
```

Với dữ liệu và ranh giới này, các kết quả dự kiến là `true`.

**Cảnh báo:** `&<` và `&>` không có nghĩa đơn giản là “khoảng A nằm trước B” hoặc “A chứa trong B”. Chúng diễn đạt quan hệ ranh giới **không kéo dài vượt về một phía**, nên có thể đúng ngay cả khi hai khoảng giao nhau. Khi bài toán chỉ cần overlap hay contains, ưu tiên `&&` hoặc `@>` để code rõ hơn.

### 10.1. Thử quan hệ vị trí của ba khoảng

```sql
WITH demo AS (
    SELECT
        int4range(1, 5) AS a,
        int4range(3, 8) AS b,
        int4range(10, 12) AS c
)
SELECT
    a && b AS a_overlaps_b,
    a << c AS a_before_c,
    c >> b AS c_after_b,
    a -|- b AS a_adjacent_b
FROM demo;
```

Các kết quả tương ứng: `true`, `true`, `true`, `false`.

## 11. Phép hợp +, giao * và hiệu - của hai range

Ba toán tử có vẻ giống phép toán tập hợp nhưng cần hiểu một hạn chế: **một range đơn chỉ biểu diễn một khoảng liên tục**. Nếu phép tính tạo hai đoạn rời, một kết quả thuộc kiểu range đơn không biểu diễn được toàn bộ tập đó.

### 11.1. Hợp hai khoảng giao nhau hoặc liền nhau

```sql
SELECT
    int4range(1, 5) + int4range(3, 8)
        AS union_overlapping,
    int4range(1, 5) + int4range(5, 8)
        AS union_adjacent;
```

Cả hai trường hợp đều cho kết quả tập số nguyên `[1,8)`.

Hợp bằng `+` trên hai **range đơn** phù hợp khi kết quả vẫn là **một khoảng liên tục**. Nếu hai range rời nhau có lỗ hổng, phép cộng range trực tiếp **không thể trả một range biểu diễn chính xác cả hai đoạn**, và PostgreSQL có thể báo lỗi.

```sql
-- Cố tình minh họa phép hợp không biểu diễn được bằng một range:
-- SELECT int4range(1, 3) + int4range(5, 8);
-- ERROR: result of range union would not be contiguous
```

Đừng dùng `+` range đơn để “gộp bất kỳ hai lịch” nếu hai lịch có thể cách nhau nhiều ngày. Trong trường hợp đó, hãy dùng **multirange**.

### 11.2. Giao hai khoảng

```sql
SELECT
    int4range(1, 7) * int4range(5, 10)
        AS common_part,
    int4range(1, 5) * int4range(5, 10)
        AS no_common_part;
```

Kết quả:

- `common_part = [5,7)`.
- `no_common_part = empty`.

Nếu hai khoảng không có phần tử chung, **giao là range rỗng**, không phải NULL. Kiểm tra bằng `isempty(result)`.

### 11.3. Hiệu hai khoảng khi kết quả còn liên tục

```sql
SELECT
    int4range(1, 10) - int4range(1, 4)
        AS remove_prefix,
    int4range(1, 10) - int4range(8, 12)
        AS remove_suffix;
```

Kết quả:

- Bỏ tiền tố `[1,4)` khỏi `[1,10)` còn `[4,10)`.
- Bỏ hậu tố `[8,12)` còn `[1,8)`.

Nhưng khi cắt một đoạn **nằm giữa**:

```text
[1,10) trừ [4,7)

[1,4)       [7,10)
     (lỗ hổng)
```

kết quả gồm hai mảnh rời nên **không thể dùng một `int4range` duy nhất**.

```sql
-- Không dùng như phép tính trả int4range đơn:
-- SELECT int4range(1, 10) - int4range(4, 7);
-- PostgreSQL không thể biểu diễn hai đoạn rời bằng một range.
```

Giải pháp đúng là **multirange** khi hệ thống chạy PostgreSQL 14+.

### 11.4. So sánh phép toán với bài toán nghiệp vụ

| Câu hỏi | Toán tử/hàm phù hợp |
|---|---|
| Hai lịch có chồng nhau không? | `&&` |
| Ngày X có nằm trong thời hạn giá? | `@>` |
| Một khung giờ con nằm trọn trong khung giờ lớn? | `@>` hoặc `<@` |
| Hai đoạn có thể nối liền không? | `-|-` hoặc `&&` để xét |
| Phần thời gian chung? | `*` |
| Ghép hai đoạn giao nhau/liền nhau? | `+` |
| Trừ một đoạn khỏi đoạn khác mà có thể tạo nhiều mảnh? | **multirange subtraction** |
| Gom tất cả các khoảng theo từng đối tượng? | `range_agg()` |

## 12. Multirange: nhiều khoảng rời trong một giá trị

Một range đơn:

```text
[1,10)
```

có một đoạn liên tục.

Một multirange:

```text
{[1,4),[7,10)}
```

biểu diễn hai đoạn rời, có khoảng trống ở giữa.

### 12.1. Tạo multirange

```sql
SELECT
    '{[1,4),[7,10)}'::int4multirange AS from_literal,
    int4multirange(
        int4range(1, 4),
        int4range(7, 10)
    ) AS from_constructor;
```

Hai giá trị là cùng tập số nguyên, được biểu diễn dưới dạng `int4multirange`.

### 12.2. Hiệu tạo hai mảnh

```sql
SELECT
    int4multirange(int4range(1, 10))
    -
    int4multirange(int4range(4, 7))
    AS remaining_segments;
```

Kết quả dự kiến:

```text
{[1,4),[7,10)}
```

Đây là lý do quan trọng để chọn multirange thay vì cố gắng biểu diễn mọi tập thời gian bằng một cặp cận đầu/cuối.

### 12.3. Hợp hai multirange

```sql
SELECT
    int4multirange(int4range(1, 3), int4range(6, 8))
    +
    int4multirange(int4range(3, 6))
    AS merged_set;
```

Kết quả là một đoạn liên tục dưới dạng multirange:

```text
{[1,8)}
```

Vì `[1,3)` liền `[3,6)`, rồi liền `[6,8)`, toàn bộ tập đã nối lại thành một khoảng.

### 12.4. Multirange cũng hỗ trợ chứa và giao

```sql
SELECT
    '{[1,4),[7,10)}'::int4multirange @> 2
        AS contains_two,
    '{[1,4),[7,10)}'::int4multirange @> 5
        AS contains_five,
    '{[1,4),[7,10)}'::int4multirange &&
    '{[3,5),[12,15)}'::int4multirange
        AS overlaps_other_set;
```

Kết quả: `true`, `false`, `true`.

### 12.5. Unnest multirange thành từng đoạn

Muốn đưa mỗi đoạn con ra một hàng:

```sql
SELECT part
FROM unnest('{[1,4),[7,10)}'::int4multirange) AS t(part)
ORDER BY lower(part);
```

Kết quả gồm hai range `[1,4)` và `[7,10)`.

Đây là cách hữu ích khi giao diện muốn **một hàng cho mỗi giai đoạn liên tục**, trong khi dữ liệu tổng hợp được lưu hoặc tính ở dạng multirange.

## 13. range_agg(), range_intersect_agg() và range_merge()

### 13.1. range_agg(): hợp nhiều range thành một multirange

Ví dụ ba khung giờ:

```sql
WITH periods(period) AS (
    VALUES
        (int4range(1, 4)),
        (int4range(3, 6)),
        (int4range(8, 10))
)
SELECT range_agg(period) AS combined
FROM periods;
```

Kết quả:

```text
{[1,6),[8,10)}
```

Hai đoạn đầu giao nhau nên được hợp thành `[1,6)`; đoạn `[8,10)` tách rời nên được giữ nguyên trong multirange.

### 13.2. range_agg() là aggregate, không phải SUM

`range_agg` làm việc với tập hợp các khoảng và tạo **hợp của chúng**, không cộng “độ dài” của mỗi khoảng. Hai lịch 09:00–10:00 và 09:30–10:30 có tổng thời lượng từng lịch là 120 phút, nhưng **hợp thời gian bị chiếm** chỉ có 90 phút.

Để đo tổng thời lượng **không đếm chồng**, hãy hợp các range trước và tính độ dài **từng đoạn** sau đó, với định nghĩa đơn vị và timezone phù hợp.

### 13.3. range_intersect_agg(): phần giao của mọi range trong nhóm

```sql
WITH periods(period) AS (
    VALUES
        (int4range(1, 10)),
        (int4range(3, 8)),
        (int4range(5, 12))
)
SELECT range_intersect_agg(period) AS common_to_all
FROM periods;
```

Kết quả `[5,8)`: mọi khoảng đầu vào đều chứa các số 5, 6, 7.

Nếu các khoảng không có phần tử chung thì phép giao là range rỗng. Khi không có hàng/giá trị hợp lệ nào để tổng hợp, aggregate có thể trả `NULL`; cần phân biệt **không có dữ liệu** với **có dữ liệu nhưng giao rỗng**.

### 13.4. range_merge(): lấy một khoảng bao phủ toàn bộ, kể cả lỗ hổng

Đây là hàm dễ gây hiểu nhầm. Với multirange gồm hai đoạn rời:

```sql
SELECT
    range_merge(
        '{[1,4),[7,10)}'::int4multirange
    ) AS bounding_range;
```

Kết quả `[1,10)`.

**Cảnh báo:** `range_merge` tạo **khoảng bao nhỏ nhất** (*bounding range*), nên nó **lấp cả lỗ hổng** giữa 4 và 7 trong kết quả biểu diễn. Nó **không** bảo toàn tập phần tử gốc như multirange.

Nếu muốn biết một thời điểm có thật sự nằm trong giai đoạn được đặt hay không, **không nên** thay multirange bằng `range_merge` rồi dùng `@>`, vì sẽ coi cả các khoảng trống là đã được đặt.

### 13.5. Tổng hợp các khoảng theo nhóm

```sql
WITH events(room_id, slot) AS (
    VALUES
        (101, int4range(9, 10)),
        (101, int4range(10, 11)),
        (101, int4range(13, 14)),
        (102, int4range(9, 12))
)
SELECT
    room_id,
    range_agg(slot) AS busy_segments
FROM events
GROUP BY room_id
ORDER BY room_id;
```

Kết quả:

| room_id | busy_segments |
|---:|---|
| 101 | `{[9,11),[13,14)}` |
| 102 | `{[9,12)}` |

Hai khung `[9,10)` và `[10,11)` của phòng 101 là **liền nhau**, nên hợp của chúng thành `[9,11)`. Khung `[13,14)` vẫn là đoạn khác.

## 14. Bài toán lịch đặt phòng: dùng tstzrange và &&

Phần này minh họa một ứng dụng có nhiều phòng và khoảng đặt chỗ.

### 14.1. Thiết kế bảng

```sql
CREATE TABLE range_lab.bookings (
    booking_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id INTEGER NOT NULL,
    guest_name TEXT NOT NULL,
    occupied_at TSTZRANGE NOT NULL,
    CONSTRAINT chk_booking_nonempty
        CHECK (NOT isempty(occupied_at)),
    CONSTRAINT chk_booking_bounded
        CHECK (
            NOT lower_inf(occupied_at)
            AND NOT upper_inf(occupied_at)
        ),
    CONSTRAINT chk_booking_half_open
        CHECK (
            lower_inc(occupied_at)
            AND NOT upper_inc(occupied_at)
        )
);
```

Ba `CHECK` xác định quy tắc lab:

- Không cho đặt một **khoảng rỗng**.
- Mỗi lượt phải có **thời điểm bắt đầu và kết thúc** hữu hạn theo cơ chế bound (không unbounded).
- Dùng quy ước **`[)`**: có lúc bắt đầu, không lấy lúc kết thúc.

**Lưu ý:** `NOT lower_inf / NOT upper_inf` kiểm tra cận unbounded, không tự loại các giá trị phần tử đặc biệt `infinity`. Nếu nghiệp vụ cấm hoàn toàn các giá trị thời gian `infinity`/`-infinity`, cần constraint bổ sung và chính sách nhập liệu.

### 14.2. Thêm dữ liệu

```sql
INSERT INTO range_lab.bookings
    (room_id, guest_name, occupied_at)
VALUES
    (
        101, 'Lan',
        tstzrange(
            TIMESTAMPTZ '2026-11-14 09:00+07',
            TIMESTAMPTZ '2026-11-14 10:00+07',
            '[)'
        )
    ),
    (
        101, 'Minh',
        tstzrange(
            TIMESTAMPTZ '2026-11-14 10:00+07',
            TIMESTAMPTZ '2026-11-14 11:00+07',
            '[)'
        )
    ),
    (
        101, 'Ngọc',
        tstzrange(
            TIMESTAMPTZ '2026-11-14 13:00+07',
            TIMESTAMPTZ '2026-11-14 14:00+07',
            '[)'
        )
    ),
    (
        102, 'Phúc',
        tstzrange(
            TIMESTAMPTZ '2026-11-14 09:30+07',
            TIMESTAMPTZ '2026-11-14 10:30+07',
            '[)'
        )
    );
```

Phòng 101 có các lịch 09–10, 10–11, 13–14; phòng 102 có lịch 09:30–10:30. Chúng có thể cùng tồn tại vì phòng khác nhau hoặc các thời đoạn không chồng lấn trong cùng phòng.

### 14.3. Truy vấn tìm lịch xung đột với yêu cầu mới

Yêu cầu đặt phòng 101 từ **09:45 tới 10:15**:

```sql
SELECT
    booking_id,
    room_id,
    guest_name,
    lower(occupied_at) AS starts_at,
    upper(occupied_at) AS ends_before
FROM range_lab.bookings
WHERE room_id = 101
  AND occupied_at &&
      tstzrange(
          TIMESTAMPTZ '2026-11-14 09:45+07',
          TIMESTAMPTZ '2026-11-14 10:15+07',
          '[)'
      )
ORDER BY lower(occupied_at);
```

Truy vấn trả **hai lịch** của phòng 101: Lan (09–10) và Minh (10–11). Cửa sổ đề nghị giao cả hai lịch.

### 14.4. Yêu cầu bắt đầu đúng khi lịch cũ kết thúc

```sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00+07',
        TIMESTAMPTZ '2026-11-14 10:00+07',
        '[)'
    ) &&
    tstzrange(
        TIMESTAMPTZ '2026-11-14 10:00+07',
        TIMESTAMPTZ '2026-11-14 11:00+07',
        '[)'
    ) AS overlaps,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00+07',
        TIMESTAMPTZ '2026-11-14 10:00+07',
        '[)'
    ) -|-
    tstzrange(
        TIMESTAMPTZ '2026-11-14 10:00+07',
        TIMESTAMPTZ '2026-11-14 11:00+07',
        '[)'
    ) AS adjacent;
```

Kết quả `overlaps=false` và `adjacent=true`.

### 14.5. Kiểm tra trước rồi INSERT có đủ chống trùng?

Một luồng ứng dụng có thể làm:

```text
Transaction A: SELECT ... WHERE occupied_at && requested_range → không có hàng
Transaction B: SELECT ... WHERE occupied_at && requested_range → không có hàng
Transaction A: INSERT requested_range
Transaction B: INSERT requested_range
```

Nếu không có cơ chế bảo vệ đồng thời ở database, cả hai giao dịch có thể kiểm tra khi chưa thấy dữ liệu của nhau rồi **đều chèn thành công**, gây đặt trùng.

Vì thế, `SELECT ... WHERE &&` rất hữu ích để **hiển thị lịch xung đột**, nhưng **không thay thế ràng buộc toàn vẹn dữ liệu** nếu nghiệp vụ yêu cầu không bao giờ trùng cùng phòng.

## 15. EXCLUDE USING gist: chống hai lịch chồng lấn cùng phòng

PostgreSQL hỗ trợ **exclusion constraint** với các toán tử được index hỗ trợ. Ta có thể diễn đạt:

> “Không được tồn tại hai hàng mà **room_id bằng nhau** và **occupied_at giao nhau**.”

### 15.1. Vì sao UNIQUE không đủ?

Ràng buộc:

```sql
UNIQUE (room_id, occupied_at)
```

chỉ cấm hai hàng có **room_id và khoảng occupied_at bằng nhau**. Nó vẫn cho phép hai lịch cùng phòng `[09:00,10:00)` và `[09:30,10:30)` vì hai range không bằng nhau.

Cần kiểm tra **giao** bằng `&&`, không phải chỉ kiểm tra **bằng** bằng `=`.

### 15.2. Cần btree_gist cho dấu bằng của room_id integer

Để dùng `room_id WITH =` cùng `occupied_at WITH &&` trong một GiST exclusion constraint, nhiều cài đặt PostgreSQL cần extension **`btree_gist`**, cung cấp GiST operator class cho kiểu dữ liệu scalar như `integer`.

```sql
-- Chạy ở môi trường kiểm soát, có quyền tạo extension.
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

Extension được cài **theo database** và có thể liên quan cấu hình/quyền vận hành, nên không chạy tùy tiện trên production nếu chưa được cho phép.

### 15.3. Thêm exclusion constraint

Với bảng lab chưa có hai lịch trùng cùng phòng:

```sql
ALTER TABLE range_lab.bookings
ADD CONSTRAINT no_room_overlap
EXCLUDE USING gist (
    room_id WITH =,
    occupied_at WITH &&
);
```

Ý nghĩa logic:

Với **bất kỳ hai hàng phân biệt**, không được để **cả hai biểu thức so sánh** sau đồng thời trả `true`:

```text
old.room_id = new.room_id
AND
old.occupied_at && new.occupied_at
```

Khi hai phòng khác nhau, `room_id = ...` là false nên không xung đột. Khi hai khoảng không giao, `&&` là false nên không xung đột. Khi cả phòng và thời gian đều trùng phạm vi, PostgreSQL bác bỏ thao tác ghi.

Đối với exclusion constraint, cột định danh phòng phải có **`NOT NULL`** nếu yêu cầu không cho một phòng “không biết ID” lọt qua so sánh ba giá trị. Ở đây bảng đã khai báo `room_id INTEGER NOT NULL`.

### 15.4. Hai lịch liền nhau được phép

Vì các khoảng dùng `[)`, `[09:00,10:00)` và `[10:00,11:00)` không giao, nên constraint cho phép hai lịch liền nhau của phòng 101.

Ví dụ một lượt khác ở khoảng 11–12 có thể thêm:

```sql
INSERT INTO range_lab.bookings
    (room_id, guest_name, occupied_at)
VALUES (
    101,
    'Quỳnh',
    tstzrange(
        TIMESTAMPTZ '2026-11-14 11:00+07',
        TIMESTAMPTZ '2026-11-14 12:00+07',
        '[)'
    )
);
```

### 15.5. Lệnh trùng sẽ lỗi

```sql
-- Chủ động để dưới dạng chú thích: sẽ vi phạm no_room_overlap.
-- INSERT INTO range_lab.bookings (room_id, guest_name, occupied_at)
-- VALUES (
--     101,
--     'Khách đặt chồng',
--     tstzrange(
--         TIMESTAMPTZ '2026-11-14 09:45+07',
--         TIMESTAMPTZ '2026-11-14 10:15+07',
--         '[)'
--     )
-- );
```

Lỗi điển hình là **SQLSTATE `23P01` – `exclusion_violation`**, khác `23505` của `unique_violation`.

### 15.6. Có thể loại một số trạng thái khỏi phạm vi constraint

Thực tế có thể cho phép lịch `cancelled` chồng lấn vì nó không còn chiếm phòng. Với bảng khác có cột `status`, exclusion constraint có thể có điều kiện `WHERE`:

```sql
-- Minh họa cú pháp trong một schema có status phù hợp:
-- ALTER TABLE reservation_table
-- ADD CONSTRAINT no_active_overlap
-- EXCLUDE USING gist (
--     room_id WITH =,
--     occupied_at WITH &&
-- )
-- WHERE (status IN ('confirmed', 'in_use'));
```

Lưu ý bảng lab `range_lab.bookings` hiện **không có cột `status`**, nên đây chỉ là ví dụ cho mô hình mở rộng. Phạm vi exclusion cần phản ánh đúng chính sách trạng thái, và khi chuyển từ `cancelled` sang `confirmed` thì PostgreSQL vẫn phải kiểm tra xung đột.

### 15.7. Tính đồng thời và giao dịch

Khác với một truy vấn kiểm tra `SELECT` độc lập, exclusion constraint được PostgreSQL thực thi khi ghi và xử lý cạnh tranh phù hợp ở mức ràng buộc. Nếu hai transaction cùng chèn lịch gây xung đột, PostgreSQL không cho phép cả hai hàng vi phạm cùng tồn tại như kết quả commit hợp lệ.

Ứng dụng cần:

- Bắt lỗi `23P01` và trả thông báo “thời gian phòng đã được đặt” phù hợp.
- Truy vấn lại các lịch xung đột nếu muốn gợi ý giờ khác.
- Xem xét việc constraint có `DEFERRABLE` hay không nếu quy trình cập nhật nhiều lịch trong một transaction.
- Không dựa duy nhất vào kết quả kiểm tra trước chèn để kết luận lịch chắc chắn còn trống.

**Không lẫn** exclusion constraint với khóa ngoại hay chỉ mục thông thường: nó là một quy tắc **ngăn hai hàng cùng thoả các phép so sánh bị cấm**.

## 16. Chỉ mục GiST và tối ưu truy vấn range

### 16.1. Tại sao index B-tree trên hai cột thời gian chưa đủ?

Truy vấn overlap với hai cột rời:

```sql
-- Ví dụ logic tương đương khi lịch đều [start_at,end_at):
-- WHERE start_at < :requested_end
--   AND end_at > :requested_start
```

Điều kiện có thể được hỗ trợ một phần bởi B-tree, nhưng không phải mọi index B-tree trên `start_at` hoặc `end_at` đều tìm overlap tốt trong mọi phân bố. Range và **GiST** cung cấp operator class chuyên dụng cho các quan hệ chứa/giao/kề.

### 16.2. Tạo GiST index cho một cột range

```sql
CREATE INDEX price_rules_valid_days_gist_idx
ON range_lab.price_rules
USING gist (valid_days);
```

Index có thể hỗ trợ truy vấn như:

```sql
SELECT *
FROM range_lab.price_rules
WHERE valid_days @> DATE '2026-02-10';

SELECT *
FROM range_lab.price_rules
WHERE valid_days &&
      daterange(DATE '2026-02-01', DATE '2026-03-01', '[)');
```

PostgreSQL có thể chọn GiST index tùy thống kê, kích thước bảng và chi phí; không phải cứ có index là mọi lần `SELECT` đều có Index Scan.

### 16.3. Exclusion constraint đã tạo index hỗ trợ

`EXCLUDE USING gist (...)` tạo index phục vụ kiểm tra exclusion. Vì vậy, khi bảng đã có exclusion constraint phù hợp, cần cân nhắc trước khi tạo thêm một GiST index gần như trùng mục đích.

Index bổ sung có thể hỗ trợ workload đọc khác, nhưng đồng thời tăng chi phí ghi, I/O và dung lượng. Dùng `EXPLAIN` và quan sát query thực trước khi quyết định.

### 16.4. GiST, SP-GiST và B-tree

- **GiST**: phổ biến cho toán tử range `&&`, `@>`, `<@` và các quan hệ vị trí; hỗ trợ exclusion constraint.
- **SP-GiST**: PostgreSQL có operator class cho một số range/operator phù hợp, có thể được cân nhắc theo kiểu truy vấn và phiên bản.
- **B-tree**: hỗ trợ sắp xếp/so sánh range theo quy tắc thứ tự của kiểu, nhưng **không thay thế GiST cho chiến lược tìm giao/bao chứa** trong đa số bài toán.

Không suy luận một index chuyên dụng cho overlap luôn tốt nhất trong mọi trường hợp; có thể cần thêm điều kiện scalar, tenant, trạng thái, thời gian và chi phí cập nhật.

### 16.5. EXPLAIN trên truy vấn overlap

```sql
EXPLAIN
SELECT rule_id, product_code, valid_days
FROM range_lab.price_rules
WHERE valid_days &&
      daterange(DATE '2026-01-15', DATE '2026-02-15', '[)');
```

Trên bảng lab vài hàng, PostgreSQL có thể chọn **Sequential Scan** vì rẻ hơn truy cập index. Điều đó không làm cú pháp `&&` hoặc index sai. Muốn đánh giá hiệu năng, cần dữ liệu đủ lớn, thống kê phù hợp và workload đại diện.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT rule_id
FROM range_lab.price_rules
WHERE valid_days @> DATE '2026-02-10';
```

`EXPLAIN ANALYZE` **thực thi câu truy vấn** để đo; với SELECT đọc nhỏ, phù hợp cho lab. Đối với lệnh ghi, cần kiểm soát vì nó thực thi tác động thật trước khi trả số liệu.

## 17. Ngày hiệu lực và dữ liệu lịch sử

Range rất hữu ích trong mô hình **effective dating**: một bản ghi áp dụng trong một khoảng thời gian.

### 17.1. Truy vấn giá tại một ngày

```sql
SELECT
    product_code,
    unit_price
FROM range_lab.price_rules
WHERE product_code = 'SKU-A'
  AND valid_days @> DATE '2026-02-05';
```

Kết quả đơn giá 135.

### 17.2. Phải phân biệt thời gian hiệu lực với thời gian ghi dữ liệu

Hai ý niệm khác nhau:

- **Valid time:** quy tắc giá có hiệu lực với giao dịch trong khoảng ngày nào?
- **System/record time:** hệ thống biết hoặc lưu quy tắc đó từ lúc nào?

`daterange` lưu khoảng **valid time** rất tự nhiên, nhưng **không tự tạo lịch sử thay đổi**. Nếu ai đó sửa hàng hiện tại, hệ thống có thể mất thông tin “trước đây từng tin rằng giá khác”. Bài toán temporal/audit có thể cần cột thời gian ghi, bảng lịch sử, sự kiện hoặc mô hình bitemporal.

### 17.3. Chặn hai giá của cùng SKU chồng hiệu lực

Trong một bảng giá, nếu một SKU không được có **hai giá đồng thời**, có thể thiết kế exclusion constraint:

```sql
-- Cần extension btree_gist để dùng = trên TEXT trong GiST.
-- CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Cú pháp minh họa: chỉ thực thi khi xác nhận dữ liệu hợp lệ
-- và muốn áp quy tắc một giá tại một ngày:
-- ALTER TABLE range_lab.price_rules
-- ADD CONSTRAINT no_overlapping_price_per_sku
-- EXCLUDE USING gist (
--     product_code WITH =,
--     valid_days WITH &&
-- );
```

Đây là cùng ý tưởng với phòng họp: khóa tài nguyên là `product_code`, khoảng thời gian là `valid_days`.

Nếu nghiệp vụ có nhiều **loại giá**, **đơn vị tiền tệ** hoặc **kênh bán** áp dụng song song, các cột đó cũng phải được xét trong khóa phạm vi exclusivity; nếu không, constraint có thể từ chối các bản ghi thực ra hợp lệ.

## 18. Múi giờ và ranh giới thời gian

### 18.1. Vì sao ưu tiên tstzrange cho lịch là thời điểm thực?

`tstzrange` chứa `timestamptz`. Hai timestamp có offset khác nhau nhưng biểu diễn cùng thời điểm sẽ được so sánh như cùng thời điểm.

```sql
SELECT
    TIMESTAMPTZ '2026-11-14 09:00:00+07'
        = TIMESTAMPTZ '2026-11-14 02:00:00+00'
        AS same_instant;
```

Kết quả `true`.

Nếu một khách đặt từ 09–10 theo giờ Việt Nam và đối tác gửi 02–03 UTC, đó là **cùng một khoảng thời gian thực** khi dùng `tstzrange` với các timestamp được gắn offset đúng.

### 18.2. tsrange không tự có timezone

`tsrange` chứa `timestamp without time zone`. Nó mô tả các giá trị đồng hồ địa phương **không gắn offset**. Điều đó có thể phù hợp cho một số lịch lặp theo giờ địa phương, nhưng không tự đủ để xác định đúng các thời điểm thực trên toàn cầu, đặc biệt khi có chuyển đổi daylight saving time.

Không đổi `tsrange` sang `tstzrange` chỉ bằng cast thiếu chính sách timezone rồi kỳ vọng mọi lịch lịch sử luôn đúng. Cần hiểu dữ liệu ban đầu được ghi theo múi giờ nào.

### 18.3. Quy ước [) tránh “23:59:59.999999”

Muốn lọc các đơn có thời điểm trong tháng 11/2026 theo múi giờ Việt Nam:

```sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-01 00:00:00+07',
        TIMESTAMPTZ '2026-12-01 00:00:00+07',
        '[)'
    ) AS november_period;
```

Không cần tự tính “giây cuối ngày 30/11” và đối mặt độ chính xác microsecond. Cận trên `2026-12-01 00:00` **không được bao gồm** nên khoảng dừng ngay trước thời điểm bắt đầu tháng 12.

### 18.4. Khoảng nửa đêm và đổi giờ DST

Ở vùng có chuyển đổi daylight saving time, một “ngày địa phương” có thể không dài đúng 24 giờ thực. Nếu nghiệp vụ yêu cầu tính theo **ngày lịch của một timezone**, cần dựng ranh giới từ **ngày địa phương** được chuyển thành `timestamptz` theo timezone đó; không mặc định cộng 24 giờ cho mọi ngày.

Ví dụ minh họa nguyên tắc với tên timezone:

```sql
SELECT
    tstzrange(
        TIMESTAMP '2026-03-01 00:00:00'
            AT TIME ZONE 'America/New_York',
        TIMESTAMP '2026-04-01 00:00:00'
            AT TIME ZONE 'America/New_York',
        '[)'
    ) AS march_local_calendar_period;
```

Hai cận được dựng theo **đồng hồ địa phương** tại đầu tháng, rồi chuyển thành các thời điểm thực. Thời lượng thực giữa hai cận có thể phản ánh sự thay đổi DST trong tháng.

## 19. NULL, empty, unbounded và missing record

Đây là bốn trạng thái rất dễ bị nhầm trong ứng dụng:

| Trạng thái | Ý nghĩa | Kiểm tra |
|---|---|---|
| Cột range là `NULL` | Không có giá trị range được cung cấp | `period IS NULL` |
| Range là `empty` | Một range xác định nhưng tập không có phần tử | `isempty(period)` |
| Range có cận không xác định | Khoảng kéo dài vô hạn theo một phía | `lower_inf(period)` / `upper_inf(period)` |
| Không có hàng nào trong bảng | Không có bản ghi để kiểm tra | `NOT EXISTS (...)` |

### 19.1. Ví dụ phân biệt NULL và empty

```sql
SELECT
    NULL::int4range IS NULL AS null_value,
    isempty('empty'::int4range) AS empty_range,
    isempty(NULL::int4range) AS empty_check_on_null;
```

Kết quả:

- `null_value=true`.
- `empty_range=true`.
- `empty_check_on_null=NULL` (không phải `true` hay `false`).

Khi đặt constraint:

```sql
period TSTZRANGE NOT NULL,
CHECK (NOT isempty(period))
```

hai điều kiện có vai trò khác nhau: `NOT NULL` chặn thiếu giá trị, `CHECK` chặn range rỗng.

### 19.2. Khi nào empty là hợp lệ?

Một số ứng dụng dùng range rỗng để biểu diễn “không còn hiệu lực” hoặc “không có phần tử phù hợp”. Nhưng với **đặt phòng**, một lượt có thời lượng bằng 0 thường không có ý nghĩa và nên bị chặn.

Đừng tự động cấm `empty` cho mọi cột range; đó là **lựa chọn nghiệp vụ**, không phải một quy tắc áp dụng toàn bộ PostgreSQL.

### 19.3. Toán tử và NULL

`NULL` trong SQL chịu ngữ nghĩa ba giá trị. Ví dụ:

```sql
SELECT
    NULL::int4range && int4range(1, 5) AS unknown_overlap;
```

Kết quả `NULL`, không phải `false`.

Trong `WHERE`, điều kiện trả NULL không được xem là true, nên hàng có range NULL sẽ không được lấy bởi `WHERE range_col && wanted_range`. Nếu nghiệp vụ muốn xử lý các hàng thiếu khoảng theo cách riêng, hãy ghi rõ điều kiện `IS NULL`.

## 20. Lọc, tổng hợp và tìm “khoảng trống”

Một bài toán thực tế là tìm **khoảng thời gian còn trống** trong một cửa sổ.

### 20.1. Gom thời gian đã đặt thành multirange

Với phòng 101 trong ngày 14/11/2026:

```sql
SELECT
    room_id,
    range_agg(occupied_at) AS all_busy_periods
FROM range_lab.bookings
WHERE room_id = 101
GROUP BY room_id;
```

Các khung 09–10 và 10–11 của phòng 101 được gộp thành **09–11**. Khung 11–12 được thêm sau khi tạo exclusion constraint cũng liền với chúng, vì vậy nếu đã chạy toàn bộ lab thì nhóm bị chiếm đầu ngày thành **09–12**. Khung 13–14 vẫn là một đoạn riêng.

### 20.2. Tìm khoảng trống trong cửa sổ bằng multirange subtraction

Giả sử cửa sổ quan tâm là **08:00–18:00**:

```sql
WITH requested AS (
    SELECT
        tstzmultirange(
            tstzrange(
                TIMESTAMPTZ '2026-11-14 08:00+07',
                TIMESTAMPTZ '2026-11-14 18:00+07',
                '[)'
            )
        ) AS full_window
),
busy AS (
    SELECT
        COALESCE(
            range_agg(occupied_at),
            '{}'::tstzmultirange
        ) AS occupied
    FROM range_lab.bookings
    WHERE room_id = 101
)
SELECT
    requested.full_window - busy.occupied
        AS available_segments
FROM requested
CROSS JOIN busy;
```

Nếu đã chạy toàn bộ phần đặt phòng, các khoảng bận của phòng 101 là **09–12** và **13–14**, nên các khoảng trống trong 08–18 là:

```text
[08:00,09:00)
[12:00,13:00)
[14:00,18:00)
```

Chú ý `COALESCE(range_agg(...), '{}'::tstzmultirange)`: nếu phòng không có booking, aggregate trả `NULL` nên ta thay bằng **multirange rỗng**. Khi đó full_window trừ tập rỗng trả chính full_window.

### 20.3. Vì sao không dùng range_merge của các lịch bận?

Nếu lấy `range_merge(range_agg(occupied_at))` cho hai giai đoạn bận 09–12 và 13–14, kết quả thành **09–14**, bao gồm cả khoảng 12–13 **thực ra trống**. Vì vậy, muốn tính availability phải giữ **multirange**, không biến nó thành một bounding range có lấp lỗ hổng.

### 20.4. Cần thêm bước lọc theo thời lượng tối thiểu

Một khoảng trống dài 5 phút có thể không đủ cho cuộc họp 45 phút. Sau khi có các đoạn trống, có thể tách chúng:

```sql
WITH window AS (
    SELECT tstzmultirange(
        tstzrange(
            TIMESTAMPTZ '2026-11-14 08:00+07',
            TIMESTAMPTZ '2026-11-14 18:00+07',
            '[)'
        )
    ) AS all_time
),
busy AS (
    SELECT COALESCE(
        range_agg(occupied_at),
        '{}'::tstzmultirange
    ) AS used_time
    FROM range_lab.bookings
    WHERE room_id = 101
),
free AS (
    SELECT all_time - used_time AS periods
    FROM window CROSS JOIN busy
)
SELECT part AS free_period,
       upper(part) - lower(part) AS duration
FROM free
CROSS JOIN LATERAL unnest(periods) AS p(part)
WHERE upper(part) - lower(part) >= INTERVAL '45 minutes'
ORDER BY lower(part);
```

Ở đây **`upper(tstzrange) - lower(tstzrange)`** trả một `interval` thể hiện thời lượng thực giữa hai timestamp. Truy vấn này áp dụng cho các đoạn trống có **cả hai cận hữu hạn**, như cửa sổ cố định 08–18 của lab.

## 21. Lưu range trong ứng dụng và API

### 21.1. Tại sao không tự nối chuỗi SQL?

Không nên tạo câu:

```text
"... WHERE occupied_at && '[" + start + "," + end + ")'::tstzrange"
```

từ dữ liệu client mà không kiểm soát. Dữ liệu ngày giờ cần parse, xác định timezone và bind parameter đúng cách để tránh lỗi cú pháp và SQL injection.

### 21.2. Prepared statement với cận timestamp

Trong PostgreSQL:

```sql
PREPARE find_conflicts(
    INTEGER, TIMESTAMPTZ, TIMESTAMPTZ
) AS
SELECT booking_id, room_id, occupied_at
FROM range_lab.bookings
WHERE room_id = $1
  AND occupied_at && tstzrange($2, $3, '[)')
ORDER BY lower(occupied_at);

EXECUTE find_conflicts(
    101,
    TIMESTAMPTZ '2026-11-14 09:45+07',
    TIMESTAMPTZ '2026-11-14 10:15+07'
);

DEALLOCATE find_conflicts;
```

`$1`, `$2`, `$3` là các tham số kiểu xác định. `tstzrange` được xây **ở SQL bằng constructor**, không phải nối các ký tự dấu ngoặc từ đầu vào.

### 21.3. Java/JDBC: gửi từng cận qua tham số

Ví dụ cách truyền `OffsetDateTime` qua JDBC 4.2+ và xây `tstzrange` ở phía SQL:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;

public final class BookingQueries {
    public boolean hasConflict(
            Connection connection,
            int roomId,
            OffsetDateTime start,
            OffsetDateTime end
    ) throws SQLException {
        if (start == null || end == null ||
                !start.toInstant().isBefore(end.toInstant())) {
            throw new IllegalArgumentException(
                "start phải sớm hơn end và không được null"
            );
        }

        String sql = """
            SELECT EXISTS (
                SELECT 1
                FROM range_lab.bookings
                WHERE room_id = ?
                  AND occupied_at &&
                      tstzrange(
                          CAST(? AS timestamptz),
                          CAST(? AS timestamptz),
                          '[)'
                      )
            )
            """;

        try (PreparedStatement stmt =
                 connection.prepareStatement(sql)) {
            stmt.setInt(1, roomId);
            stmt.setObject(2, start);
            stmt.setObject(3, end);

            try (ResultSet rs = stmt.executeQuery()) {
                rs.next();
                return rs.getBoolean(1);
            }
        }
    }
}
```

Ví dụ dùng Java text blocks (Java 15+) và driver PostgreSQL hỗ trợ bind `OffsetDateTime`. Lưu ý đầu vào ứng dụng phải được diễn giải đúng timezone/offset trước khi truyền; một chuỗi local datetime không có offset không tự biểu diễn một thời điểm duy nhất.

Hàm `hasConflict` hữu ích để **hiển thị cảnh báo trước**; khi ghi, **exclusion constraint** mới là lớp bảo vệ chống đặt trùng khi có nhiều giao dịch đồng thời.

### 21.4. API nên định nghĩa ranh giới rõ

Nếu API nhận:

```json
{
  "roomId": 101,
  "start": "2026-11-14T09:00:00+07:00",
  "end": "2026-11-14T10:00:00+07:00"
}
```

thì tài liệu API cần nói rõ:

- `start` **được bao gồm**.
- `end` **không được bao gồm**.
- Cả hai phải là timestamp có offset hoặc được diễn giải theo timezone cụ thể.
- `start < end` về mặt **thời điểm thực**.
- Hai booking cùng phòng không được chồng lấn, nhưng có thể liền kề.
- Thông báo lỗi nghiệp vụ map từ SQLSTATE `23P01` khi exclusion constraint bị vi phạm.

Khi chia sẻ hợp đồng này giữa frontend, backend và database, các ranh giới “đúng 10:00” không còn phụ thuộc suy đoán riêng của từng lớp.

## 22. Quản lý độ dài khoảng và số phần tử

### 22.1. Range không có một hàm length() chung cho mọi kiểu

Đừng giả định `length(anyrange)` trả “độ dài khoảng” cho tất cả các loại range. Độ dài có ý nghĩa khác nhau:

- Với số nguyên: số **phần tử nguyên** trong range hữu hạn.
- Với `numeric`: hiệu hai cận theo thước đo số, nếu phù hợp.
- Với ngày: số **ngày lịch** hoặc số bước ngày.
- Với thời gian: **thời lượng thực** giữa hai thời điểm.

Hãy chọn phép tính trên kiểu phần tử phù hợp, sau khi xác minh range không rỗng, có cả hai cận và quy tắc cận được diễn giải đúng.

### 22.2. int4range với dạng chuẩn [)

Với `int4range(3,8)` có các số 3,4,5,6,7: tổng số phần tử là `upper(r)-lower(r)=5`.

```sql
WITH demo AS (
    SELECT int4range(3, 8) AS r
)
SELECT
    r,
    upper(r) - lower(r) AS integer_count
FROM demo;
```

Đây chỉ đúng theo mô hình **số nguyên rời rạc và dạng cận đã chuẩn hóa** với cả hai cận hữu hạn; không dùng công thức này một cách mù quáng cho `numrange`, `tstzrange` hoặc khoảng unbounded.

### 22.3. Khoảng thời gian hữu hạn

```sql
WITH demo AS (
    SELECT tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00+07',
        TIMESTAMPTZ '2026-11-14 10:30+07',
        '[)'
    ) AS r
)
SELECT
    r,
    upper(r) - lower(r) AS duration
FROM demo;
```

Kết quả thời lượng là `01:30:00`. Đây là hiệu giữa **hai thời điểm thực**, khác với số ngày/tháng lịch mà người dùng có thể muốn trong các phép báo cáo tổng hợp.

## 23. Những lỗi thường gặp với range và multirange

**1. “`[a,b)` và `[a,b]` chỉ khác cách in.”** Sai. Chúng có thể khác tập phần tử ở cận trên.

**2. “Hai lịch có end = start luôn overlap.”** Không với quy ước `[)`: chúng thường **liền kề**, không giao nhau.

**3. “`UNIQUE (room_id, period)` ngăn mọi lịch đặt chồng.”** Sai. UNIQUE chỉ cấm giá trị khóa bằng nhau, không cấm hai range khác nhau nhưng giao nhau.

**4. “`EXCLUDE ... WITH &&` là một CHECK trên từng hàng.”** Không. Nó kiểm tra quan hệ bị cấm **giữa các hàng**.

**5. “SELECT tìm lịch trùng rồi INSERT sẽ an toàn khi nhiều người đặt cùng lúc.”** Không. Có race condition nếu thiếu bảo vệ đồng thời ở database.

**6. “`int4range(1,4,'[]')` luôn được in lại đúng `[1,4]`.”** Không. PostgreSQL có thể chuẩn hóa thành `[1,5)`.

**7. “`numrange` cũng có thể tự cộng 1 để chuẩn hóa giống int4range.”** Không. Numeric không có bước nguyên đơn giản.

**8. “`empty` là SQL `NULL`.”** Sai. Empty range là giá trị hợp lệ đại diện tập rỗng; `NULL` là không có giá trị range.

**9. “`upper_inf()` cho biết bound bằng literal infinity.”** Không. Nó kiểm tra cận unbounded.

**10. “`lower()` trả NULL tức range chắc chắn không có cận dưới.”** Không nhất thiết: range rỗng cũng không có cận có thể trả.

**11. “`&&` có nghĩa hai range bằng nhau.”** Sai. Chúng chỉ cần có phần tử chung.

**12. “`-|-` cũng đồng nghĩa `&&`.”** Không. Liền kề và giao nhau là hai quan hệ khác nhau.

**13. “Phép `+` range đơn hợp được hai đoạn rời.”** Không. Kết quả rời không biểu diễn được bằng một range đơn.

**14. “Phép `-` range đơn luôn trả một range.”** Không. Cắt đoạn ở giữa có thể cần multirange.

**15. “`range_merge(multirange)` giữ nguyên mọi lỗ hổng.”** Không. Nó tạo bounding range và có thể lấp lỗ hổng.

**16. “`range_agg` là tổng độ dài các khoảng.”** Sai. Nó trả hợp tập các khoảng dưới dạng multirange.

**17. “Multirange có ở mọi phiên bản PostgreSQL.”** Không. Cần PostgreSQL 14+.

**18. “Lưu tsrange với giờ không offset vẫn đủ biểu diễn một lịch quốc tế.”** Không tự đủ. Cần timezone rõ hoặc dùng `tstzrange`.

**19. “Một ngày lịch luôn dài đúng 24 giờ thực ở mọi timezone.”** Không ở các vùng có chuyển DST.

**20. “DATERANGE [01/01,31/01] và [01/01,01/02) có tập phần tử khác.”** Không. Với ngày rời rạc, chúng có thể được chuẩn hóa thành cùng một khoảng.

**21. “Có GiST index thì PostgreSQL luôn dùng Index Scan.”** Không. Planner chọn theo chi phí, thống kê và kích thước bảng.

**22. “btree_gist tự được cài khi tạo bảng có int room_id.”** Không. Extension có thể phải cài có chủ đích với quyền phù hợp nếu dùng scalar equality trong GiST.

**23. “room_id nullable không ảnh hưởng exclusion.”** Không. Nếu một phép so sánh cho NULL/unknown, constraint có thể không cấm cặp hàng; cần xác định NOT NULL.

**24. “Range rỗng của một booking luôn hợp lệ.”** Không nếu nghiệp vụ yêu cầu bắt đầu trước kết thúc; hãy dùng `CHECK (NOT isempty(...))` và validation.

**25. “Mọi giá trị datetime trong text sẽ được diễn giải theo múi giờ người dùng.”** Không. Cần xử lý kiểu, timezone/session settings và offset rõ ràng.

**26. “Tập lịch bận có nhiều đoạn có thể lưu bằng hai cột min/max mà không đổi ý nghĩa.”** Không. Min/max lấp các khoảng trống giữa những đoạn bận.

## 24. Bài tập thực hành có đáp án

### Bài 1 — Phân biệt bốn kiểu cận

**Câu hỏi:** Trong miền `numeric`, khoảng `[1,5)` có chứa 1 và 5 không?

**Đáp án:** Có chứa 1, không chứa 5.

```sql
SELECT
    numrange(1, 5, '[)') @> 1::numeric AS has_one,
    numrange(1, 5, '[)') @> 5::numeric AS has_five;
```

Kết quả `true` và `false`.

### Bài 2 — Chuẩn hóa int4range

**Câu hỏi:** `int4range(1,4,'[]')` và `int4range(1,5,'[)')` có cùng tập số nguyên không?

**Đáp án:** Có. Cả hai đều chứa 1,2,3,4.

```sql
SELECT
    int4range(1, 4, '[]') =
    int4range(1, 5, '[)') AS same_set;
```

### Bài 3 — Khoảng rỗng

**Yêu cầu:** xác định `int4range(7,7,'[)')` có rỗng không.

```sql
SELECT isempty(int4range(7, 7, '[)')) AS is_empty;
```

**Đáp án:** `true`.

### Bài 4 — Chứa một ngày

Một giai đoạn hiệu lực là `[2026-01-01,2026-02-01)`. Ngày 31/01 và ngày 01/02 có hợp lệ không?

**Đáp án:** 31/01 hợp lệ; 01/02 không nằm trong khoảng.

```sql
SELECT
    daterange(DATE '2026-01-01', DATE '2026-02-01')
        @> DATE '2026-01-31' AS jan31,
    daterange(DATE '2026-01-01', DATE '2026-02-01')
        @> DATE '2026-02-01' AS feb01;
```

### Bài 5 — Trùng hay liền?

Hai khoảng `[9,10)` và `[10,11)`.

**Đáp án:** `&&` là false, `-|-` là true.

```sql
SELECT
    int4range(9, 10) && int4range(10, 11) AS overlaps,
    int4range(9, 10) -|- int4range(10, 11) AS adjacent;
```

### Bài 6 — Tìm quy tắc giá tại ngày

**Yêu cầu:** lấy giá của SKU-A ngày 05/02/2026.

**Đáp án:**

```sql
SELECT unit_price
FROM range_lab.price_rules
WHERE product_code = 'SKU-A'
  AND valid_days @> DATE '2026-02-05';
```

Kết quả `135`.

### Bài 7 — Tìm lịch đặt trùng

**Yêu cầu:** tìm lịch phòng 101 giao với `[09:45,10:15)` ngày 14/11/2026 theo offset +07.

**Đáp án:**

```sql
SELECT booking_id, guest_name, occupied_at
FROM range_lab.bookings
WHERE room_id = 101
  AND occupied_at && tstzrange(
      TIMESTAMPTZ '2026-11-14 09:45+07',
      TIMESTAMPTZ '2026-11-14 10:15+07',
      '[)'
  )
ORDER BY lower(occupied_at);
```

Trả hai lịch Lan và Minh.

### Bài 8 — Chống race condition

**Câu hỏi:** Vì sao chỉ dùng `SELECT ... WHERE occupied_at && new_period` trước khi insert vẫn có thể tạo trùng?

**Đáp án:** Hai transaction đồng thời có thể cùng nhìn thấy “không có hàng xung đột” trước khi một trong hai commit. Sử dụng exclusion constraint `EXCLUDE USING gist (room_id WITH =, occupied_at WITH &&)` để database bảo vệ tính nhất quán của các thao tác ghi cạnh tranh.

### Bài 9 — Hợp hai khoảng kề nhau

```sql
SELECT int4range(1, 4) + int4range(4, 9) AS result;
```

**Đáp án:** `[1,9)`.

### Bài 10 — Phần giao

```sql
SELECT int4range(1, 8) * int4range(5, 12) AS result;
```

**Đáp án:** `[5,8)`.

### Bài 11 — Phần hiệu có hai mảnh

**Yêu cầu:** tính `[1,10) - [4,7)` mà không làm mất phần tử.

**Đáp án PostgreSQL 14+:**

```sql
SELECT
    int4multirange(int4range(1, 10))
    -
    int4multirange(int4range(4, 7))
    AS result;
```

Kết quả `{[1,4),[7,10)}`.

### Bài 12 — range_agg

**Câu hỏi:** Vì sao `range_agg` của `[1,5)`, `[4,7)` và `[9,10)` không phải `[1,10)`?

**Đáp án:** Hợp của ba khoảng chứa các phần tử `[1,7)` và `[9,10)`, nhưng **không có** phần tử thuộc khoảng trống `[7,9)`. Vì vậy kết quả multirange là `{[1,7),[9,10)}`.

```sql
WITH data(r) AS (
    VALUES
        (int4range(1,5)),
        (int4range(4,7)),
        (int4range(9,10))
)
SELECT range_agg(r) AS result
FROM data;
```

### Bài 13 — range_merge có lấp lỗ hổng không?

```sql
SELECT range_merge(
    '{[1,4),[7,10)}'::int4multirange
) AS result;
```

**Đáp án:** `[1,10)`, có lấp lỗ hổng 4–7. Chỉ dùng nếu mục tiêu là **bounding range**, không dùng làm tập lịch bận thực tế.

### Bài 14 — Một ngày hiệu lực chưa kết thúc

**Yêu cầu:** lưu khoảng hiệu lực bắt đầu 01/01/2026 và không có cận trên.

```sql
SELECT daterange(
    DATE '2026-01-01',
    NULL,
    '[)'
) AS open_ended;
```

**Đáp án:** Đây là khoảng từ đầu ngày 01/01/2026 trở đi, không có cận trên. `upper_inf(...)` trả `true`.

### Bài 15 — Thiết kế index cho overlap

**Yêu cầu:** thường xuyên tìm các quy tắc giá giao một khoảng ngày.

**Đáp án gợi ý:**

```sql
CREATE INDEX price_rules_window_lookup_idx
ON range_lab.price_rules
USING gist (valid_days);
```

Sau đó đo `EXPLAIN` trên dữ liệu thật. Bảng lab đã có index `price_rules_valid_days_gist_idx` phục vụ mục đích tương tự; **không cần tạo cả hai** trên cùng bảng nếu không có lý do rõ ràng. Lệnh ở đáp án chỉ minh họa cú pháp.

### Bài 16 — NULL hay empty?

```sql
SELECT
    NULL::daterange IS NULL AS a,
    isempty('empty'::daterange) AS b;
```

**Đáp án:** `a=true` và `b=true` nhưng biểu diễn hai trạng thái khác nhau. Hãy dùng `NOT NULL` cùng `CHECK (NOT isempty(...))` nếu nghiệp vụ yêu cầu cả một giá trị được cung cấp và khoảng đó phải có phần tử.

### Bài 17 — Múi giờ

**Câu hỏi:** Lịch bắt đầu lúc 09:00 +07 và lịch bắt đầu lúc 02:00 UTC cùng ngày có cùng thời điểm không?

**Đáp án:** Có. Hai cách biểu diễn cùng một instant. `tstzrange` là lựa chọn thích hợp khi cần so sánh các lịch theo thời điểm thực qua nhiều múi giờ.

### Bài 18 — Tìm khoảng trống

Một phòng bận trong `[09,11)` và `[13,14)`. Cửa sổ làm việc là `[08,18)`.

**Đáp án:** Các đoạn trống là `[08,09)`, `[11,13)` và `[14,18)`. Có thể tính bằng cách đổi hai bên thành multirange rồi dùng toán tử `-`.

Lưu ý tình huống này **khác** dữ liệu lab sau khi đã thêm lịch 11–12; với dữ liệu lab đầy đủ, đoạn trống giữa hai khung bận đầu và cuối là `[12,13)`.

## 25. Quy trình thiết kế khi dùng range ở dự án thực

1. **Xác định miền phần tử:** số nguyên, ngày, số thập phân hay thời điểm thực?
2. **Chọn kiểu:** `int4range`/`int8range`/`numrange`/`daterange`/`tsrange`/`tstzrange` phù hợp.
3. **Thống nhất cận:** `[)` cho lịch/hiệu lực nửa mở thường thuận tiện; ghi rõ trong API.
4. **Xác định giá trị trống:** `NULL`, `empty`, unbounded và các giá trị `infinity` có được phép hay không?
5. **Dùng toán tử đúng nghĩa:** `@>` cho chứa, `&&` cho giao, `-|-` cho kề; không dùng `=` thay cho overlap.
6. **Chọn range hay multirange:** một đoạn liên tục hay tập nhiều đoạn rời?
7. **Nếu hợp/hiệu nhiều đoạn:** đừng cố dùng `+`/`-` range đơn khi kết quả có thể rời; chọn multirange.
8. **Nếu cần gom các khoảng:** `range_agg` tạo hợp chính xác, còn `range_merge` chỉ tạo khoảng bao.
9. **Nếu cần cấm lịch chồng:** exclusion constraint đúng khóa tài nguyên và điều kiện trạng thái; đừng chỉ kiểm tra trước khi ghi.
10. **Chọn index:** GiST cho overlap/contains, `btree_gist` nếu cần scalar equality trong GiST; đo kế hoạch.
11. **Xác định timezone:** với lịch là các thời điểm thực, ưu tiên `tstzrange` và đầu vào có offset/timezone rõ.
12. **Xác định scope:** tenant, phòng, giá theo currency/kênh, trạng thái hoạt động và quyền truy cập.
13. **Thử các ranh giới:** hai đoạn chạm nhau, cận đóng, empty, unbounded, ngày cuối tháng, DST, phần hiệu tạo hai mảnh.
14. **Kiểm tra migration:** nếu đang có lịch giao nhau, thêm exclusion constraint có thể thất bại; cần xử lý dữ liệu cũ có chủ đích.
15. **Kiểm tra cạnh tranh ghi:** hai transaction đồng thời phải không thể commit hai hàng vi phạm quy tắc xung đột.
16. **Kiểm tra phiên bản:** multirange cần PostgreSQL 14+, extension/phân quyền phải phù hợp môi trường.
17. **Đặt giới hạn vận hành:** xem thời gian query, kích thước range tập hợp, bloat/index và chi phí duy trì khi ghi.

## 26. Tổng kết

**Range types** của PostgreSQL cho phép diễn đạt tập giá trị giữa hai cận bằng một giá trị có kiểu, với cú pháp rõ ràng về **cận mở/đóng**. Những phép so sánh dễ sai nếu viết tay trên hai cột start/end được biểu đạt trực tiếp:

- **`@>` và `<@`:** kiểm tra phần tử/khoảng nằm trong khoảng khác.
- **`&&`:** kiểm tra hai khoảng có giao nhau.
- **`-|-`:** kiểm tra hai khoảng liền kề.
- **`+`, `*`, `-`:** hợp, giao, hiệu với lưu ý range đơn không thể biểu diễn tập có nhiều mảnh rời.
- **`lower`, `upper`, `lower_inc`, `upper_inc`, `lower_inf`, `upper_inf`, `isempty`:** đọc cận và trạng thái khoảng.
- **Multirange** và **`range_agg`** cho phép biểu diễn/gom tập nhiều đoạn rời mà không vô tình lấp các khoảng trống; **`range_merge`** chỉ lấy một khoảng bao.
- **GiST** hỗ trợ truy vấn overlap/contains, còn **exclusion constraint** có thể bảo vệ quy tắc “cùng tài nguyên không được có hai khoảng giao nhau” an toàn ở tầng database.

Quy ước **`[start,end)`** đặc biệt hữu ích cho lịch đặt phòng và các giai đoạn hiệu lực: hai lượt nối tiếp ở cùng một thời điểm ranh giới **không giao nhau**. Nhưng quy ước đó phải được sử dụng nhất quán từ API đến SQL, cùng kiểu thời gian/múi giờ đúng.

**Nguyên tắc cuối cùng:** trước khi chọn toán tử, hãy trả lời **“đang lưu tập giá trị nào, ranh giới có được bao gồm không, có thể có nhiều đoạn rời không, và hai bản ghi giao nhau có bị cấm theo nghiệp vụ không?”**. Trả lời đúng các câu hỏi này là nền tảng để dùng range và multirange chính xác, dễ bảo trì và an toàn khi có ghi đồng thời.

### Tài liệu PostgreSQL chính thức

- [Range Types và Multirange Types](https://www.postgresql.org/docs/current/rangetypes.html).
- [Range/Multirange Functions and Operators](https://www.postgresql.org/docs/current/functions-range.html).
- [CREATE TABLE — EXCLUDE Constraint](https://www.postgresql.org/docs/current/sql-createtable.html).
- [Indexes, Operator Classes and GiST](https://www.postgresql.org/docs/current/indexes-types.html).
- [Date/Time Types và Time Zones](https://www.postgresql.org/docs/current/datatype-datetime.html).
