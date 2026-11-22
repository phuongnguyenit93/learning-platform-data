# Range, multirange và biểu diễn khoảng giá trị

Một ứng dụng thường phải lưu dữ liệu không phải là một giá trị đơn, mà là **một khoảng giá trị**: thời gian phòng họp đã được đặt, dải tuổi của chương trình ưu đãi, khoảng giá bán có hiệu lực, dải số lượng đặt hàng hoặc nhiều khung giờ rảnh của nhân viên. Nếu chỉ lưu hai cột `start` và `end`, lập trình viên phải liên tục viết điều kiện kiểm tra giao nhau, bao chứa, kề nhau và xử lý ranh giới. Những điều kiện tưởng đơn giản này dễ sai khi hai khoảng chỉ chạm đầu mút, có đầu mút vô hạn hoặc bị chia thành nhiều đoạn.

PostgreSQL có **range types** để biểu diễn **một khoảng có thứ tự trên một kiểu dữ liệu**, và **multirange types** để biểu diễn **một tập có chuẩn hóa gồm nhiều khoảng không rỗng, không giao nhau**. Range/multirange có các toán tử `@>` (bao chứa), `&&` (giao nhau), `-|-` (kề nhau), các phép hợp/giao/hiệu, chỉ mục GiST và ràng buộc `EXCLUDE`. Đây là công cụ quan trọng khi thiết kế dữ liệu với ràng buộc thời gian hoặc dải số.

Bài học đi từ khái niệm tới sử dụng thực tế: chọn loại range, quy ước biên `[)`, giá trị rỗng và không giới hạn, cách PostgreSQL chuẩn hóa khoảng rời rạc, chuyển đổi giữa range và multirange, truy vấn nhiều khoảng không liên tục, thiết kế lịch đặt phòng không chồng lấn và cách sử dụng chỉ mục/ràng buộc để bảo vệ dữ liệu trước ghi đồng thời.

> **Phạm vi:** Ví dụ SQL dành cho một PostgreSQL phiên bản hỗ trợ multirange (**PostgreSQL 14 trở lên**) trong database thử nghiệm. Một số tính năng hoặc tối ưu có thể thay đổi theo bản PostgreSQL; các thao tác `CREATE TABLE`, `ALTER TABLE` và tạo extension cần quyền phù hợp. Không triển khai quy tắc đặt chỗ hoặc chính sách giá vào production trước khi thống nhất rõ cách tính ranh giới và xử lý các giao dịch đồng thời.

## 1. Range khác hai cột begin/end như thế nào?

Giả sử hai cuộc họp diễn ra:

```text
Cuộc họp A: 09:00 ├───────────┤ 10:00
Cuộc họp B:                     10:00 ├───────────┤ 11:00
```

Hai cuộc họp **chạm nhau ở mốc 10:00** nhưng không chồng lên nhau nếu quy tắc nghiệp vụ là một cuộc họp kết thúc **trước khi** cuộc tiếp theo bắt đầu sử dụng phòng.

Với hai cột `start_at`/`end_at`, phải viết điều kiện cẩn thận:

```sql
-- Hai khoảng nửa mở [start_at, end_at) giao nhau khi:
a.start_at < b.end_at
AND b.start_at < a.end_at
```

Đây là một **biểu thức minh họa**, không phải câu SQL hoàn chỉnh. Nếu người viết đổi `<` thành `<=`, hai lịch chỉ chạm đầu mút sẽ bị coi là trùng. Nếu `end_at` có thể là `NULL` để biểu thị không giới hạn, biểu thức còn cần xử lý riêng.

Với range:

```sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        '[)'
    ) &&
    tstzrange(
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        TIMESTAMPTZ '2026-11-14 11:00:00+07',
        '[)'
    ) AS do_intervals_overlap;
-- false
```

Toán tử **`&&`** diễn đạt trực tiếp câu hỏi **“hai khoảng có điểm chung hay không?”**. PostgreSQL hiểu tính bao gồm/không bao gồm của từng đầu mút nên giảm nguy cơ tự viết sai điều kiện.

### Lợi ích của range

- **Ngữ nghĩa rõ:** một giá trị biểu diễn cả khoảng và các quy tắc biên.
- **Biểu thức gọn:** `during && requested_period`, `active_period @> timestamp`.
- **Ràng buộc ở database:** kết hợp `EXCLUDE USING gist` để không cho hai booking của một phòng giao nhau.
- **Chỉ mục chuyên dụng:** GiST và những operator class phù hợp để hỗ trợ tìm khoảng.
- **Biểu diễn vô hạn hoặc rỗng:** không phải tự đặt sentinel như `9999-12-31` cho mọi trường hợp.

Điều quan trọng: range **không tự chọn quy tắc nghiệp vụ**. Bạn phải quyết định một khoảng có bao gồm hai mốc biên hay không, có cho khoảng rỗng không và hai khoảng chỉ kề nhau có được coi là xung đột không.

## 2. Các range và multirange tích hợp sẵn

PostgreSQL cung cấp những cặp kiểu tương ứng:

| Kiểu range | Kiểu multirange | Kiểu phần tử (subtype) | Ví dụ sử dụng |
|---|---|---|---|
| `int4range` | `int4multirange` | `integer` (`int4`) | Dải số lượng, số thứ tự nhỏ. |
| `int8range` | `int8multirange` | `bigint` (`int8`) | Dải ID/số lớn. |
| `numrange` | `nummultirange` | `numeric` | Dải giá, dải số liên tục dạng chính xác thập phân. |
| `daterange` | `datemultirange` | `date` | Ngày nghỉ, khoảng ngày hiệu lực. |
| `tsrange` | `tsmultirange` | `timestamp without time zone` | Thời gian theo đồng hồ cục bộ, không phải instant có múi giờ. |
| `tstzrange` | `tstzmultirange` | `timestamp with time zone` (`timestamptz`) | Khoảng thời gian tuyệt đối, lịch booking theo instant. |

**Multirange xuất hiện từ PostgreSQL 14**. Nếu vận hành bản PostgreSQL cũ hơn, không thể giả định các tên kiểu `int4multirange`, `tstzmultirange` hoặc các thao tác multirange có sẵn.

### Chọn kiểu nào?

Với lịch phòng họp có người đặt ở nhiều múi giờ, ưu tiên **`tstzrange`** để lưu khoảng thời điểm tuyệt đối. Với lịch làm việc “09:00–17:00 vào mỗi thứ Hai ở Berlin”, còn cần **ngữ nghĩa lịch theo múi giờ**, không chỉ một `tstzrange` duy nhất: cần tạo ra các instant cụ thể từ lịch địa phương và IANA time zone.

Với dải số nguyên, dùng `int4range`/`int8range`; với số lượng thập phân hoặc giá trị đo liên tục, dùng `numrange`. Tránh ép những mức số thực tùy ý vào `int4range` chỉ vì cú pháp đơn giản.

## 3. Hiểu dấu ngoặc của khoảng

Một range có **lower bound** (đầu dưới) và **upper bound** (đầu trên). Dấu ngoặc cho biết biên có thuộc khoảng hay không.

| Dạng | Ý nghĩa | Ví dụ khoảng số thực |
|---|---|---|
| `[a,b]` | Bao gồm cả `a` và `b`. | \(a \le x \le b\) |
| `[a,b)` | Bao gồm `a`, loại `b`. | \(a \le x < b\) |
| `(a,b]` | Loại `a`, bao gồm `b`. | \(a < x \le b\) |
| `(a,b)` | Không bao gồm cả hai đầu. | \(a < x < b\) |

Trong lịch đặt phòng, **`[start, end)`** thường là quy ước thuận tiện:

```text
09:00                         10:00                    11:00
  [────────── Booking A ─────────) 
                                 [──────── Booking B ────────)

10:00 thuộc Booking B; không thuộc Booking A.
=> Hai booking kề nhau, không có thời lượng giao nhau.
```

**Không nên dùng mặc định khoảng đóng `[start,end]` cho các lịch nối tiếp** nếu nghiệp vụ cho phép ca tiếp theo bắt đầu đúng lúc ca trước kết thúc.

### Hai cách tạo một range

Dùng **literal** với ép kiểu:

```sql
SELECT '[1,10)'::int4range AS integer_period;

SELECT '[2026-11-14 09:00:00+07,2026-11-14 10:00:00+07)'::tstzrange
       AS meeting_period;
```

Hoặc dùng **constructor**:

```sql
SELECT int4range(1, 10, '[)') AS integer_period;

SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    TIMESTAMPTZ '2026-11-14 10:00:00+07',
    '[)'
) AS meeting_period;
```

Constructor nhận **lower**, **upper** và tham số biên tùy chọn; khi bỏ tham số biên, nhiều constructor dùng quy ước `[)`. Với thời gian, viết timestamp có offset rõ ràng giúp tránh phụ thuộc time zone của connection.

### Những câu hỏi phải được thống nhất trước

1. Mốc kết thúc có được tính là đã sử dụng tài nguyên không?
2. Hai booking `[09:00,10:00)` và `[10:00,11:00)` có hợp lệ cùng lúc không?
3. Đơn giá áp dụng đến đúng 00:00 ngày kế tiếp hay đến 23:59:59.999?
4. Giá trị dưới và trên có cho phép bằng nhau?
5. Khoảng được phép mở vô thời hạn hay phải có ngày hết hạn?

Range giúp thể hiện quy tắc này, nhưng đội nghiệp vụ phải chọn quy tắc trước.

## 4. Khoảng rời rạc và khoảng liên tục

Đây là một khác biệt nền tảng: PostgreSQL **không biểu diễn mọi subtype giống nhau**.

### 4.1. Discrete ranges

`int4range`, `int8range` và `daterange` có những **giá trị kế tiếp rời rạc** theo subtype. Ví dụ với số nguyên, không có số nguyên nào nằm giữa 2 và 3.

Vì vậy:

```sql
SELECT int4range(1, 4, '[)') AS p1,
       int4range(1, 3, '[]') AS p2,
       int4range(2, 5, '(]') AS p3;
```

Ý nghĩa:

- `[1,4)` chứa các số nguyên 1, 2, 3.
- `[1,3]` cũng chứa 1, 2, 3.
- `(2,5]` chứa 3, 4, 5.

PostgreSQL dùng **canonical form** cho nhiều discrete range types, thường chuẩn hóa về `[)`. Vì thế `[1,3]::int4range` được hiển thị tương đương `[1,4)`.

```sql
SELECT '[1,3]'::int4range = '[1,4)'::int4range
       AS equal_integer_sets;
-- true
```

### 4.2. Continuous ranges

Với `numrange` hoặc khoảng timestamp, giữa hai giá trị thường có những giá trị khác. Bởi vậy:

```sql
SELECT
    '[1,3]'::numrange = '[1,3)'::numrange
        AS equal_numeric_sets;
-- false
```

Số 3 **thuộc** khoảng đầu nhưng **không thuộc** khoảng sau, nên hai khoảng không bằng nhau. Không thể tự động biến dấu `]` thành `)` bằng cách tăng 1 như với số nguyên.

### 4.3. Ngày tháng cũng có canonicalization

`daterange` dùng giá trị `date` rời rạc theo ngày:

```sql
SELECT
    daterange(DATE '2026-11-01', DATE '2026-11-03', '[]')
        AS inclusive_dates;
```

Khoảng gồm ngày 01, 02, 03/11; dạng chuẩn hóa thường hiển thị **`[2026-11-01,2026-11-04)`**.

**Không áp dụng kiểu cộng một ngày để chuẩn hóa cho `tstzrange`.** Một instant không có “giá trị kế tiếp” như ngày nguyên, và một ngày theo lịch địa phương có thể dài 23/25 giờ ở vùng có DST.

## 5. Khoảng rỗng, không giới hạn và giá trị NULL

Ba khái niệm này rất dễ nhầm:

1. **Empty range:** có kiểu range nhưng không chứa phần tử nào.
2. **Unbounded range:** không có giới hạn phía dưới hoặc phía trên.
3. **SQL NULL:** không có giá trị range (unknown/missing), khác với range rỗng.

### 5.1. Empty range

```sql
SELECT 'empty'::int4range AS empty_period;

SELECT isempty('empty'::int4range) AS is_empty;
-- true

SELECT int4range(5, 5, '[)') AS zero_width;
-- empty
```

Một range `[5,5)` không chứa số 5, nên rỗng. Nhưng range số thực đóng `[5,5]` **chứa đúng một điểm** và không rỗng:

```sql
SELECT isempty('[5,5]'::numrange) AS numeric_single_point_empty;
-- false
```

Điểm này quan trọng nếu bạn dùng range để mô hình hóa **giá trị chính xác**. Không phải mọi khoảng có lower = upper đều rỗng; nó còn phụ thuộc loại ngoặc.

### 5.2. Unbounded range

```sql
-- Không giới hạn phía dưới.
SELECT int4range(NULL, 10, '()') AS before_ten;

-- Không giới hạn phía trên.
SELECT int4range(10, NULL, '[)') AS from_ten;

-- Không giới hạn cả hai phía.
SELECT '(,)'::numrange AS all_numeric_values;
```

Trong **constructor**, lower hoặc upper bằng SQL `NULL` biểu diễn **đầu không giới hạn**. Đây là ngữ nghĩa của hàm tạo range, khác việc lưu **cả cột range bằng SQL NULL**.

Ví dụ:

```sql
SELECT
    int4range(10, NULL, '[)') IS NULL AS range_is_sql_null,
    int4range(10, NULL, '[)') @> 100000 AS contains_large_number;
-- false, true
```

### 5.3. Infinity là giá trị khác unbounded

PostgreSQL có các giá trị đặc biệt `infinity` và `-infinity` cho những kiểu như `date`/`timestamp`. Nhưng **giới hạn vô cực là một giá trị subtype cụ thể**, không luôn giống **một bound hoàn toàn bị bỏ trống**.

Ví dụ:

```sql
SELECT
    upper_inf(tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        NULL,
        '[)'
    )) AS has_unbounded_upper;
-- true
```

Trong khi đó, khoảng có upper là `'infinity'::timestamptz` là khái niệm **bound tại giá trị đặc biệt infinity**, và cách kiểm tra `upper_inf` có thể khác. Đừng dùng literal `infinity` thay cho đầu **không giới hạn** khi muốn SQL không phải xét sự khác biệt này.

### 5.4. Cột range có thể NULL

```sql
CREATE TABLE range_null_examples (
    id INTEGER PRIMARY KEY,
    active_period TSTZRANGE
);

INSERT INTO range_null_examples VALUES
    (1, NULL),
    (2, 'empty'::tstzrange),
    (3, tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        NULL,
        '[)'
    ));
```

Với hàng 1, `active_period IS NULL` là true. Với hàng 2, `isempty(active_period)` là true. Với hàng 3, `upper_inf(active_period)` là true. **Đây là ba trạng thái khác nhau**.

## 6. Truy xuất các đầu mút và thuộc tính range

PostgreSQL có những hàm hữu ích:

| Hàm | Tác dụng |
|---|---|
| `lower(range)` | Giá trị đầu dưới, nếu có. |
| `upper(range)` | Giá trị đầu trên, nếu có. |
| `lower_inc(range)` | Bound dưới có được bao gồm hay không. |
| `upper_inc(range)` | Bound trên có được bao gồm hay không. |
| `lower_inf(range)` | Bound dưới có không giới hạn hay không. |
| `upper_inf(range)` | Bound trên có không giới hạn hay không. |
| `isempty(range)` | Range có rỗng hay không. |

Ví dụ:

```sql
SELECT
    lower('[2,8)'::int4range) AS min_value,
    upper('[2,8)'::int4range) AS max_bound,
    lower_inc('[2,8)'::int4range) AS include_min,
    upper_inc('[2,8)'::int4range) AS include_max,
    isempty('[2,8)'::int4range) AS empty;
```

Kết quả về ý nghĩa: lower = 2, upper = 8, lower included, upper excluded, range không rỗng.

**Chú ý:** `upper(range)` là **giá trị đầu mút**, không nhất thiết là **giá trị lớn nhất thuộc khoảng**. Với `int4range '[2,8)'`, upper = 8 nhưng số nguyên lớn nhất trong khoảng là 7.

### Vì sao upper_inf thay vì chỉ upper IS NULL?

`upper(range)` có thể trả SQL `NULL` khi đầu không giới hạn hoặc với range rỗng. Khi cần phân loại rõ, kiểm tra **`isempty`** và **`upper_inf`** theo thứ tự phù hợp, thay vì chỉ suy đoán từ `upper() IS NULL`.

```sql
SELECT
    isempty('empty'::int4range) AS is_empty,
    upper_inf(int4range(5, NULL, '[)')) AS no_upper_bound;
```

Để phân tích dữ liệu range từ nhiều nguồn, nên ghi rõ bất biến “cột không NULL”, “không empty”, “upper có thể unbounded hay không” trong schema.

## 7. Các toán tử range quan trọng

Với các range có subtype tương thích, PostgreSQL hỗ trợ các toán tử theo lý thuyết tập hợp và thứ tự:

| Toán tử | Ý nghĩa | Ví dụ ý tưởng |
|---|---|---|
| `@>` | Range **chứa** giá trị hoặc range khác. | `period @> timestamp` |
| `<@` | Giá trị/range **nằm trong** range. | `timestamp <@ period` |
| `&&` | Hai range **giao nhau**. | `booking_a && booking_b` |
| `-|-` | Hai range **kề nhau** (adjacent). | `[1,3) -|- [3,6)` |
| `<<` | Range thứ nhất nằm hoàn toàn **bên trái** range thứ hai. | `a << b` |
| `>>` | Range thứ nhất nằm hoàn toàn **bên phải** range thứ hai. | `a >> b` |
| `&<` | Range thứ nhất không vươn sang phải range thứ hai. | Cần hiểu thứ tự đầu mút. |
| `&>` | Range thứ nhất không vươn sang trái range thứ hai. | Cần hiểu thứ tự đầu mút. |
| `+` | **Hợp** của hai range khi có thể biểu diễn thành một range. | `[1,3) + [3,5)` |
| `*` | **Giao** của hai range. | `[1,5) * [3,8)` |
| `-` | **Hiệu** của hai range khi kết quả biểu diễn được bằng một range. | `[1,8) - [1,3)` |

Ví dụ SQL:

```sql
SELECT
    '[1,10)'::int4range @> 5 AS contains_five,
    '[1,10)'::int4range @> '[2,5)'::int4range
        AS contains_inner_range,
    '[1,5)'::int4range && '[4,8)'::int4range
        AS overlaps,
    '[1,5)'::int4range -|- '[5,8)'::int4range
        AS adjacent,
    '[1,5)'::int4range && '[5,8)'::int4range
        AS adjacent_but_not_overlapping;
```

Kết quả theo thứ tự: **true, true, true, true, false**.

### Hai khoảng kề nhau không đồng nghĩa giao nhau

```text
Range A:   [1,5)
Range B:        [5,8)
                    ▲
                điểm chạm 5

A -|- B  → true
A && B   → false
```

Đây là lý do ràng buộc booking thông thường dùng `&&` chứ không phải điều kiện “giao nhau **hoặc** kề nhau”: lịch B bắt đầu ngay lúc lịch A kết thúc vẫn hợp lệ khi quy ước `[)`.

### Kiểm tra range không có giao nhau

```sql
SELECT NOT (
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        '[)'
    ) &&
    tstzrange(
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        TIMESTAMPTZ '2026-11-14 11:00:00+07',
        '[)'
    )
) AS no_conflict;
-- true
```

Khi các cột là SQL `NULL`, kết quả boolean cũng có thể là `NULL` (unknown), **không phải true/false**. Do vậy, với lịch booking cần dữ liệu bắt buộc, đặt cột range **`NOT NULL`** và **không rỗng**.

## 8. Hợp, giao, hiệu: phép toán trên một range

Hãy coi range là tập các giá trị được chứa.

### 8.1. Phép hợp (+)

```sql
SELECT '[1,5)'::int4range + '[4,8)'::int4range
       AS union_overlapping;
-- [1,8)

SELECT '[1,5)'::int4range + '[5,8)'::int4range
       AS union_adjacent;
-- [1,8)
```

Hai range **giao nhau hoặc kề nhau** có thể tạo thành một range liên tục. Nhưng hai range cách nhau một đoạn không thể luôn gộp thành **một range** mà vẫn giữ đúng tập phần tử:

```sql
-- Với toán tử + của hai range:
-- '[1,3)'::int4range + '[6,8)'::int4range
-- có thể bị từ chối vì kết quả là hai đoạn rời nhau.
```

Muốn giữ hai đoạn, dùng **multirange**, không cố nới range thành `[1,8)` vì sẽ vô tình bao gồm 3, 4, 5.

### 8.2. Phép giao (*)

```sql
SELECT '[1,8)'::int4range * '[5,10)'::int4range
       AS intersection;
-- [5,8)

SELECT '[1,3)'::int4range * '[5,8)'::int4range
       AS empty_intersection;
-- empty
```

Phép giao trả về những phần tử thuộc **cả hai** range.

### 8.3. Phép hiệu (-)

```sql
SELECT '[1,8)'::int4range - '[1,3)'::int4range
       AS difference_contiguous;
-- [3,8)
```

Nhưng:

```text
[1,10) trừ [4,6) = [1,4) và [6,10)
                    └─ hai đoạn rời nhau
```

Kiểu **range đơn** không biểu diễn được hai đoạn này như một giá trị; phép hiệu range có thể báo lỗi khi kết quả sẽ bị tách thành hai phần. **Multirange giải quyết tình huống đó**.

## 9. Multirange: một tập gồm nhiều khoảng rời nhau

**Multirange** lưu một tập hữu hạn của những range **không rỗng, không giao nhau, được chuẩn hóa theo thứ tự**. Những khoảng giao nhau hoặc kề nhau được hợp nhất khi chúng tạo thành một khoảng liên tục cùng tập giá trị.

Ví dụ giờ làm việc một nhân viên:

```text
08:00        12:00      13:00           17:00
 [── ca sáng ───)        [── ca chiều ─────)
                └─ nghỉ trưa ─┘

Không thể biểu diễn chính xác bằng một tstzrange duy nhất
nếu cần giữ khoảng nghỉ trưa ở giữa.
```

Dạng SQL với số nguyên:

```sql
SELECT '{[1,4),[7,10)}'::int4multirange
       AS available_numbers;
```

Multirange ở đây chứa **1,2,3,7,8,9**, không chứa 4,5,6.

### 9.1. Tạo bằng constructor

```sql
SELECT int4multirange(
    int4range(1,4,'[)'),
    int4range(7,10,'[)')
) AS numbers_in_two_blocks;
```

### 9.2. Multirange rỗng

```sql
SELECT '{}'::int4multirange AS no_allowed_values;

SELECT int4multirange() AS no_allowed_values_from_constructor;
```

Một multirange rỗng nghĩa là **không có đoạn nào**, không phải SQL `NULL`. Cột multirange có thể là `NULL` nếu schema cho phép; cần phân biệt hai trường hợp giống như với range.

### 9.3. Tự chuẩn hóa khi tạo

```sql
SELECT int4multirange(
    int4range(7,10),
    int4range(1,4),
    int4range(4,7)
) AS merged_ranges;
-- {[1,10)}
```

Các đoạn `[1,4)`, `[4,7)`, `[7,10)` nằm kề nhau nên giá trị multirange chuẩn hóa về **một đoạn `[1,10)`**. Thứ tự input không quyết định thứ tự phần tử được lưu.

**Không dựa vào multirange để ghi lại “ba lịch đặt độc lập”.** Nếu cần lưu từng booking cùng actor, ID, trạng thái, hãy dùng **một hàng mỗi booking**. Multirange phù hợp để biểu diễn **tập khoảng đã hợp nhất** cho phép tính và hiển thị.

## 10. Phép toán trên multirange

Multirange hỗ trợ nhiều toán tử tương tự range, nhưng kết quả có thể có **nhiều đoạn**.

### 10.1. Hợp của hai tập rời nhau

```sql
SELECT
    '{[1,4)}'::int4multirange
    + '{[7,10)}'::int4multirange
    AS combined;
-- {[1,4),[7,10)}
```

Không phát sinh lỗi chỉ vì hai khoảng có gap.

### 10.2. Hiệu có thể tách một khoảng

```sql
SELECT
    int4multirange(int4range(1,10))
    - int4multirange(int4range(4,6))
    AS without_middle;
-- {[1,4),[6,10)}
```

Đây là ví dụ cốt lõi: phép trừ của **range đơn** không thể biểu diễn kết quả rời nhau, còn **multirange** giữ chính xác cả hai đoạn.

### 10.3. Giao

```sql
SELECT
    '{[1,5),[8,12)}'::int4multirange
    * '{[3,9)}'::int4multirange
    AS common_values;
-- {[3,5),[8,9)}
```

### 10.4. Kiểm tra bao chứa và giao nhau

```sql
SELECT
    '{[1,4),[7,10)}'::int4multirange @> 2
       AS contains_two,
    '{[1,4),[7,10)}'::int4multirange @> 5
       AS contains_five,
    '{[1,4),[7,10)}'::int4multirange
       && '[3,8)'::int4range
       AS overlaps_range;
```

Kết quả theo thứ tự: **true, false, true**. Lưu ý PostgreSQL có những biến thể toán tử hỗ trợ range/multirange ở các đối số; luôn đảm bảo kiểu dữ liệu tương thích.

## 11. Chuyển đổi giữa range và multirange

### Một range thành một multirange

```sql
SELECT int4multirange(int4range(10,20))
       AS a_single_segment_multirange;
-- {[10,20)}
```

### Multirange thành từng đoạn

`unnest(multirange)` trả các thành phần range:

```sql
SELECT segment
FROM unnest(
    '{[1,4),[7,10)}'::int4multirange
) AS t(segment);
```

Kết quả có **hai hàng**, lần lượt `[1,4)` và `[7,10)`. Điều này hữu ích để chuyển tập khoảng rảnh thành danh sách các ô thời gian cho UI.

### Lấy bao lồi: range_merge()

`range_merge(multirange)` tạo ra **range nhỏ nhất bao trùm toàn bộ các đoạn**:

```sql
SELECT range_merge(
    '{[1,4),[7,10)}'::int4multirange
) AS bounding_range;
-- [1,10)
```

**Rất quan trọng:** `range_merge` **không giữ các khoảng trống**. Kết quả `[1,10)` chứa cả 4,5,6, vốn **không thuộc** multirange ban đầu. Dùng hàm này khi cần **bounding interval**, không phải để trả lời “những giá trị nào được phép”.

### Aggregate các range thành multirange

`range_agg(range)` tổng hợp nhiều range thành một multirange:

```sql
WITH intervals(period) AS (
    VALUES
      ('[1,4)'::int4range),
      ('[3,6)'::int4range),
      ('[9,12)'::int4range)
)
SELECT range_agg(period) AS merged_periods
FROM intervals;
-- {[1,6),[9,12)}
```

Ứng dụng điển hình: tổng hợp các booking đã xác nhận thành một tập **thời gian bận** sau khi lọc theo phòng/ngày, rồi lấy hiệu khỏi khoảng thời gian có thể sử dụng.

## 12. Làm việc với khoảng thời gian và múi giờ

Khi thiết kế thời gian, cần phân biệt **giờ theo đồng hồ địa phương** với **thời điểm tuyệt đối**:

- `tsrange` chứa `timestamp without time zone`. Nó không tự biết một thời điểm là UTC+7 hay UTC+1.
- `tstzrange` chứa `timestamptz`. PostgreSQL biểu diễn những **instant** cụ thể và hiển thị theo time zone của session.
- `daterange` chứa **ngày theo lịch**, phù hợp với chính sách hiệu lực theo ngày.

### Hai khoảng cùng instant có thể hiển thị khác nhau

```sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    TIMESTAMPTZ '2026-11-14 10:00:00+07',
    '[)'
) AS vietnam_display;

SET TIME ZONE 'UTC';

SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 02:00:00+00',
    TIMESTAMPTZ '2026-11-14 03:00:00+00',
    '[)'
) AS utc_display;

RESET TIME ZONE;
```

Hai giá trị có cùng điểm đầu/cuối tuyệt đối; văn bản hiển thị có thể khác theo `TimeZone`.

### Một “ngày địa phương” không luôn là 24 giờ

Ở các vùng có Daylight Saving Time (DST), có ngày lịch dài 23 hoặc 25 giờ. Khi tạo khoảng cho một ngày địa phương ở một vùng, hãy **chuyển từng mốc nửa đêm sang instant**, không tự cộng cứng 24 giờ vào đầu ngày.

Ví dụ tạo khoảng ngày 14/11 theo lịch Việt Nam:

```sql
SELECT tstzrange(
    TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh',
    TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh',
    '[)'
) AS local_calendar_day;
```

Nếu bài toán chỉ liên quan ngày (ví dụ hợp đồng có hiệu lực từ ngày 01/11 đến hết ngày 14/11), `daterange` có thể rõ ràng hơn `tstzrange`:

```sql
SELECT daterange(
    DATE '2026-11-01',
    DATE '2026-11-15',
    '[)'
) AS effective_dates;
```

Khoảng trên bao gồm ngày 01 đến 14/11. Đừng tự đặt `23:59:59.999999` làm “cuối ngày” vì độ chính xác, kiểu dữ liệu và múi giờ có thể thay đổi.

## 13. Thiết kế bảng booking với tstzrange

Một hệ thống đặt phòng cần những bất biến:

1. Booking có khoảng thời gian **không rỗng**.
2. Hai booking `CONFIRMED` **của cùng phòng** không được chồng lấn.
3. Booking của **phòng khác nhau** có thể trùng thời gian.
4. Booking `CANCELLED` không chiếm chỗ.
5. Hai lịch của cùng phòng có thể **kề nhau** nếu thời điểm kết thúc được loại khỏi booking trước.

Schema:

```sql
CREATE TABLE meeting_rooms (
    room_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_code TEXT NOT NULL UNIQUE
);

CREATE TABLE room_bookings (
    booking_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id BIGINT NOT NULL REFERENCES meeting_rooms(room_id),
    booked_period TSTZRANGE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    booked_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_booking_nonempty
        CHECK (NOT isempty(booked_period)),

    CONSTRAINT chk_booking_bounded
        CHECK (
            NOT lower_inf(booked_period)
            AND NOT upper_inf(booked_period)
        ),

    CONSTRAINT chk_booking_half_open
        CHECK (
            lower_inc(booked_period)
            AND NOT upper_inc(booked_period)
        )
);
```

Ở ví dụ này, hệ thống **không chấp nhận booking vô thời hạn**, vì phòng họp cần giờ bắt đầu và kết thúc cụ thể. `lower_inf/upper_inf` giúp bác bỏ những đầu không giới hạn; quy tắc `[)` thể hiện booking kết thúc khi chạm mốc cuối.

**Lưu ý:** Một business khác như giá bán mở hiệu lực vô hạn **không nên dùng lại `chk_booking_bounded`**. Schema range tốt phải phản ánh bất biến của từng domain, không sao chép tất cả constraint cho mọi loại khoảng.

### Thêm hai phòng

```sql
INSERT INTO meeting_rooms(room_code)
VALUES ('A-101'), ('B-201')
RETURNING room_id, room_code;
```

Trong các ví dụ sau, giả định phòng `A-101` có `room_id = 1`; trong database đã có dữ liệu hoặc sequence đã được sử dụng, hãy lấy **ID thực từ RETURNING**.

### Thêm lịch đầu tiên

```sql
INSERT INTO room_bookings(
    room_id, booked_period, status, booked_by
)
VALUES (
    1,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        '[)'
    ),
    'CONFIRMED',
    'user-100'
);
```

Ở thời điểm này, schema bảo vệ range không rỗng và có biên, nhưng **chưa có constraint chống đặt trùng**. Phần tiếp theo thêm ràng buộc database-level.

## 14. EXCLUDE USING gist: ngăn khoảng booking chồng lấn

Chỉ viết câu `SELECT` kiểm tra lịch trùng trước `INSERT` **không đủ an toàn** khi có nhiều request đồng thời:

```text
Transaction A                     Transaction B
     │                                 │
     ▼                                 ▼
Kiểm tra phòng trống             Kiểm tra phòng trống
     │                                 │
Đều chưa thấy lịch mới          Đều chưa thấy lịch mới
     │                                 │
INSERT booking A                 INSERT booking B
     └─────────────┬───────────────────┘
                   ▼
          Có thể bị đặt chồng nhau
          nếu không có bảo vệ đồng thời
```

PostgreSQL có **exclusion constraint** để ngăn hai hàng cùng lúc thỏa các phép so sánh bị cấm.

### 14.1. btree_gist cho room_id

Để kết hợp `room_id WITH =` với khoảng `booked_period WITH &&` trong chỉ mục GiST, thường dùng extension:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

`btree_gist` cung cấp các lớp toán tử GiST cho nhiều kiểu scalar, giúp dùng phép `=` với `BIGINT` trong exclusion constraint. Cài extension yêu cầu quyền phù hợp, và hệ thống managed PostgreSQL có thể có chính sách extension riêng.

### 14.2. Tạo ràng buộc chống overlap

```sql
ALTER TABLE room_bookings
ADD CONSTRAINT ex_confirmed_room_time_no_overlap
EXCLUDE USING gist (
    room_id WITH =,
    booked_period WITH &&
)
WHERE (status = 'CONFIRMED');
```

Ý nghĩa:

- Hai hàng **cùng room_id** và **booked_period giao nhau** không được cùng thỏa `status = 'CONFIRMED'`.
- Hai hàng **khác room_id** được có cùng thời gian.
- Hai booking **kề nhau** không giao nhau khi đều dùng `[)`.
- Hai booking ở trạng thái `PENDING` hoặc `CANCELLED` không bị constraint partial này loại trừ theo cùng quy tắc.

Nếu thêm ràng buộc vào bảng đã có dữ liệu **đang vi phạm**, lệnh có thể thất bại. Trước khi triển khai cần kiểm tra dữ liệu lịch sử, đánh giá việc xây dựng GiST index và locking trong quá trình thay đổi schema.

### 14.3. Thử một booking bị từ chối

```sql
INSERT INTO room_bookings(
    room_id, booked_period, status, booked_by
)
VALUES (
    1,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:30:00+07',
        TIMESTAMPTZ '2026-11-14 10:30:00+07',
        '[)'
    ),
    'CONFIRMED',
    'user-101'
);
```

Nếu booking 09:00–10:00 đã có và ràng buộc hoạt động, PostgreSQL sẽ từ chối với **SQLSTATE `23P01` — `exclusion_violation`**.

Một ứng dụng Java có thể đọc `SQLException.getSQLState()` để phân loại lỗi này thành “Phòng đã được đặt trong khoảng thời gian yêu cầu”. Nhưng nếu database có nhiều exclusion constraints, cần đọc thêm **tên constraint** để ánh xạ đúng nghiệp vụ.

### 14.4. Thử một booking kề nhau

```sql
INSERT INTO room_bookings(
    room_id, booked_period, status, booked_by
)
VALUES (
    1,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        TIMESTAMPTZ '2026-11-14 11:00:00+07',
        '[)'
    ),
    'CONFIRMED',
    'user-102'
);
```

Booking mới bắt đầu đúng 10:00 nên **không giao** với 09:00–10:00. Nếu không có xung đột khác, nó được phép.

### 14.5. Cập nhật trạng thái cũng được bảo vệ

Nếu đã có một booking `PENDING` trùng lịch, việc đổi sang `CONFIRMED` cũng phải tuân thủ exclusion constraint. Đây là lợi thế quan trọng: **ràng buộc bảo vệ cả INSERT và UPDATE**, không chỉ đường API tạo mới.

### 14.6. Exclusion constraint không thay thế logic nghiệp vụ khác

Constraint không tự biết:

- Một phòng có nghỉ giữa hai lịch hay không.
- Nhân viên có cần 15 phút dọn phòng.
- Booking có bị khóa theo ca làm việc hay ngày lễ.
- Một người có thể đặt đồng thời hai phòng hay không.

Nếu phải có **buffer 15 phút**, có thể thiết kế khoảng chiếm chỗ riêng với buffer hoặc mở rộng biểu thức ràng buộc theo quy tắc xác định. Không tự đổi `&&` thành logic tùy ý khi chưa thống nhất cách tính buffer theo thời gian/múi giờ.

## 15. Truy vấn lịch trùng và đặt phòng an toàn

Để tìm các booking đã xác nhận giao với khoảng yêu cầu:

```sql
SELECT
    booking_id,
    room_id,
    booked_period,
    booked_by
FROM room_bookings
WHERE room_id = 1
  AND status = 'CONFIRMED'
  AND booked_period && tstzrange(
      TIMESTAMPTZ '2026-11-14 09:30:00+07',
      TIMESTAMPTZ '2026-11-14 10:30:00+07',
      '[)'
  );
```

Truy vấn giúp **hiển thị lý do booking xung đột**, nhưng application không được dựa vào “SELECT không trả hàng” như bảo đảm tuyệt đối rằng INSERT tiếp theo sẽ thành công.

### Workflow an toàn

1. Client gửi thời gian bắt đầu/kết thúc với offset hoặc time zone đã được chuẩn hóa.
2. Ứng dụng xác nhận `start < end`, quyền đặt phòng và các điều kiện nghiệp vụ.
3. Gửi `INSERT` tới PostgreSQL trong transaction phù hợp.
4. PostgreSQL áp dụng `EXCLUDE`; nếu có cạnh tranh, một giao dịch có thể phải chờ rồi bị từ chối.
5. Nếu nhận `23P01`, ứng dụng trả phản hồi lịch bị trùng, có thể cho người dùng xem booking liên quan.
6. Chỉ thông báo đặt phòng thành công sau khi transaction thực sự commit.

**Chú ý:** `ON CONFLICT DO UPDATE` không hỗ trợ sử dụng exclusion constraint làm arbiter theo cách tương tự unique constraint. Không nên giả định có thể giải quyết mọi xung đột lịch bằng một lệnh upsert đơn giản.

### Vì sao GiST phù hợp?

GiST (*Generalized Search Tree*) là framework chỉ mục hỗ trợ nhiều kiểu tìm kiếm, trong đó có operator class cho range. Ràng buộc `EXCLUDE USING gist` tận dụng khả năng tìm các khoảng có quan hệ `&&`, trong khi B-tree thông thường rất phù hợp với so sánh scalar nhưng không tự thay thế được mọi truy vấn giao nhau.

Khi có độ trễ truy vấn, quan sát kế hoạch:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT booking_id
FROM room_bookings
WHERE room_id = 1
  AND status = 'CONFIRMED'
  AND booked_period && tstzrange(
      TIMESTAMPTZ '2026-11-14 08:00:00+07',
      TIMESTAMPTZ '2026-11-14 12:00:00+07',
      '[)'
  );
```

`EXPLAIN ANALYZE` thực thi truy vấn thực; ví dụ `SELECT` là phép quan sát đọc, nhưng cần cân nhắc tác động khi áp dụng cho câu SQL ghi hoặc workload lớn. PostgreSQL có thể chọn sequential scan nếu dữ liệu nhỏ; đó không tự là bằng chứng chỉ mục sai.

## 16. Tập các khoảng bận và các khoảng rảnh bằng multirange

Một yêu cầu phổ biến: **“Trong cửa sổ 08:00–18:00, phòng còn rảnh những đoạn nào?”**

Giả sử có hai booking:

```text
08:00      09:00       10:00     11:00         13:00      18:00
 [──────────┬───────────┬─────────┬────────────┬───────────)
            [─ booking 1─)       [ booking 2 ─)

Khoảng rảnh = [08:00,09:00)
             + [10:00,11:00)
             + [13:00,18:00)
```

Trong SQL, tổng hợp các booking bằng **`range_agg`**, sau đó **trừ khỏi cửa sổ tìm kiếm**.

```sql
WITH requested AS (
    SELECT tstzrange(
        TIMESTAMPTZ '2026-11-14 08:00:00+07',
        TIMESTAMPTZ '2026-11-14 18:00:00+07',
        '[)'
    ) AS search_period
),
busy AS (
    SELECT COALESCE(
        range_agg(b.booked_period * r.search_period),
        '{}'::tstzmultirange
    ) AS occupied
    FROM requested AS r
    LEFT JOIN room_bookings AS b
      ON b.room_id = 1
     AND b.status = 'CONFIRMED'
     AND b.booked_period && r.search_period
)
SELECT
    tstzmultirange(r.search_period) - busy.occupied AS free_periods
FROM requested AS r
CROSS JOIN busy;
```

Giải thích:

1. `requested` xác định **một cửa sổ thời gian**.
2. `booked_period * search_period` lấy phần giao, không cần giữ phần booking nằm ngoài cửa sổ.
3. `range_agg` gộp các khoảng chiếm chỗ thành multirange chuẩn hóa.
4. `COALESCE(..., '{}'::tstzmultirange)` xử lý trường hợp không có booking.
5. `tstzmultirange(search_period) - occupied` trả tập các đoạn rảnh.

Lưu ý khi dùng `LEFT JOIN`: nếu không có booking, biểu thức `booked_period * search_period` nhận SQL `NULL`; aggregate bỏ qua input null và `COALESCE` tạo multirange rỗng.

### Chuyển kết quả thành từng hàng UI có thể hiển thị

```sql
WITH requested AS (
    SELECT tstzrange(
        TIMESTAMPTZ '2026-11-14 08:00:00+07',
        TIMESTAMPTZ '2026-11-14 18:00:00+07',
        '[)'
    ) AS search_period
),
busy AS (
    SELECT COALESCE(
        range_agg(b.booked_period * r.search_period),
        '{}'::tstzmultirange
    ) AS occupied
    FROM requested AS r
    LEFT JOIN room_bookings AS b
      ON b.room_id = 1
     AND b.status = 'CONFIRMED'
     AND b.booked_period && r.search_period
),
free AS (
    SELECT tstzmultirange(r.search_period) - b.occupied AS periods
    FROM requested AS r
    CROSS JOIN busy AS b
)
SELECT lower(slot) AS free_from,
       upper(slot) AS free_to
FROM free
CROSS JOIN LATERAL unnest(free.periods) AS t(slot)
ORDER BY free_from;
```

Ví dụ này minh họa tính toán lịch trống. Nếu nghiệp vụ yêu cầu **thời lượng tối thiểu 30 phút**, hãy bổ sung điều kiện lọc `upper(slot) - lower(slot) >= INTERVAL '30 minutes'`. Với booking có thay đổi đồng thời, kết quả đọc chỉ là **snapshot tại thời điểm truy vấn**; đặt phòng thành công vẫn phải dựa vào ràng buộc khi ghi.

## 17. Thiết kế khoảng hiệu lực giá bán

Range còn rất hữu ích cho lịch sử và chính sách giá. Giả sử một sản phẩm có nhiều giai đoạn giá:

```sql
CREATE TABLE product_prices (
    price_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    valid_period TSTZRANGE NOT NULL,
    CONSTRAINT chk_price_nonempty CHECK (NOT isempty(valid_period))
);
```

Đặt hai phiên bản:

```sql
INSERT INTO product_prices(product_id, price, valid_period)
VALUES
  (42, 100000, tstzrange(
      TIMESTAMPTZ '2026-11-01 00:00:00+07',
      TIMESTAMPTZ '2026-11-10 00:00:00+07',
      '[)'
  )),
  (42, 115000, tstzrange(
      TIMESTAMPTZ '2026-11-10 00:00:00+07',
      NULL,
      '[)'
  ));
```

Lấy giá có hiệu lực tại T:

```sql
SELECT product_id, price, valid_period
FROM product_prices
WHERE product_id = 42
  AND valid_period @>
      TIMESTAMPTZ '2026-11-12 09:00:00+07';
```

Mô hình không cho phép hai giá chồng lấn có thể thêm:

```sql
-- Chỉ dùng khi extension btree_gist đã sẵn sàng.
ALTER TABLE product_prices
ADD CONSTRAINT ex_price_no_overlap
EXCLUDE USING gist (
    product_id WITH =,
    valid_period WITH &&
);
```

Ở đây **không giới hạn trạng thái** như booking: mọi version giá cho cùng sản phẩm phải không chồng nhau. Nếu giá có thêm `currency`, `region` hoặc `channel`, khóa logic của ràng buộc có thể cần gồm thêm các chiều đó để **hai giá thuộc hai thị trường khác nhau không bị coi là xung đột**.

### Đóng khoảng cũ và mở khoảng mới

Khi cập nhật giá, chọn **một mốc T** và sử dụng nó trong transaction cho cả hai bước:

```sql
BEGIN;

-- Ứng dụng cần có giao thức khóa theo product_id
-- khi nhiều writer sửa cùng timeline.
UPDATE product_prices
SET valid_period = tstzrange(
    lower(valid_period),
    TIMESTAMPTZ '2026-11-15 09:00:00+07',
    '[)'
)
WHERE product_id = 42
  AND upper_inf(valid_period);

INSERT INTO product_prices(product_id, price, valid_period)
VALUES (
    42, 120000,
    tstzrange(
        TIMESTAMPTZ '2026-11-15 09:00:00+07',
        NULL,
        '[)'
    )
);

COMMIT;
```

**Ví dụ giả định** có đúng một phiên bản giá mở phía trên, không có phiên bản tương lai khác, và T nằm sau lower của phiên bản mở. Trong production, cần:

- Khóa theo `product_id` hoặc cơ chế serialization/optimistic concurrency phù hợp.
- Kiểm tra số hàng cập nhật; không vô tình chèn giá mới khi không có bản cũ cần đóng.
- Kiểm tra việc sửa hồi tố hoặc phiên bản đã lên lịch.
- Dựa vào `EXCLUDE` như lớp bảo vệ cuối cùng chống overlap.

Exclusion constraint ngăn **chồng lấn**, nhưng **không tự bảo đảm không có khoảng trống** giữa các phiên bản giá. Nếu nghiệp vụ yêu cầu tính liên tục, phải có kiểm tra bổ sung.

## 18. Tên cột range và schema cần diễn đạt đúng nghiệp vụ

Đừng đặt mọi cột là `range` hoặc `period` rồi để người đọc đoán ý nghĩa:

| Nhu cầu | Tên gợi ý | Kiểu phù hợp |
|---|---|---|
| Lịch đặt phòng | `booked_period` | `tstzrange` |
| Khoảng hiệu lực hợp đồng theo ngày | `effective_dates` | `daterange` |
| Dải giá trị giảm giá | `discount_amount_range` | `numrange` |
| Dải số lượng hàng | `quantity_range` | `int4range` hoặc `int8range` |
| Nhiều khung giờ rảnh | `available_periods` | `tstzmultirange` |
| Dải tuần tuổi được chấp nhận | `accepted_ages` | `int4multirange` |

Khi một multirange biểu diễn **các đoạn hiện còn được phép**, nên đặt tên `allowed_ranges`/`available_periods`; khi biểu diễn **các đoạn bị chặn**, dùng `blocked_ranges`/`occupied_periods`. Đặt tên rõ giúp tránh lỗi dấu trừ khi lấy phần bù.

### Cột range với generated expression

Nếu schema cũ đang có hai cột `valid_from` và `valid_to`, có thể tạo **expression index** trên `tstzrange(valid_from, valid_to, '[)')` thay vì bắt buộc chuyển ngay toàn bộ ứng dụng sang một cột range:

```sql
CREATE TABLE legacy_price_periods (
    price_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX ix_legacy_price_period_gist
ON legacy_price_periods
USING gist (
    tstzrange(valid_from, valid_to, '[)')
);
```

Truy vấn dùng cùng biểu thức range có thể tận dụng index phù hợp:

```sql
SELECT *
FROM legacy_price_periods
WHERE tstzrange(valid_from, valid_to, '[)')
      @> TIMESTAMPTZ '2026-11-14 10:00:00+07';
```

Thiết kế này cho phép **từng bước chuyển đổi**, nhưng nếu có nhiều ứng dụng ghi vào hai cột cũ, phải giữ quy tắc ranh giới nhất quán và vẫn cần ràng buộc chống overlap khi nghiệp vụ yêu cầu.

## 19. GiST, SP-GiST và cách đo hiệu năng

PostgreSQL có các access method khác nhau. Với range, **GiST** là lựa chọn quan trọng vì hỗ trợ nhiều toán tử quan hệ khoảng, đặc biệt cho `EXCLUDE`. Một số kiểu range và operator class còn hỗ trợ **SP-GiST** để tối ưu các truy vấn phù hợp. Đặc tính chính xác cần kiểm tra theo phiên bản/type đang dùng.

### GiST index cho truy vấn giao nhau

```sql
CREATE INDEX ix_product_prices_period
ON product_prices
USING gist(valid_period);
```

Truy vấn:

```sql
SELECT price_version_id, product_id, price
FROM product_prices
WHERE valid_period &&
      tstzrange(
          TIMESTAMPTZ '2026-11-01 00:00:00+07',
          TIMESTAMPTZ '2026-12-01 00:00:00+07',
          '[)'
      );
```

Với `EXCLUDE USING gist`, PostgreSQL cũng tạo chỉ mục gắn với constraint; **không tự động thêm một GiST index khác cùng cột** nếu nó chỉ lặp lại khả năng tìm kiếm, vì mỗi index tăng dung lượng, WAL và chi phí ghi.

### B-tree có còn hữu ích?

Có. Ví dụ truy vấn **theo sản phẩm** và **sắp theo lower(valid_period)** có thể cần B-tree hoặc expression index tương ứng, tùy workload. GiST tập trung vào toán tử quan hệ khoảng và không thay thế mọi bài toán sort/range scan của B-tree.

Một bảng có:

- GiST/exclusion index để ngăn overlap.
- B-tree theo `product_id` để join và các truy vấn theo ID.
- Index bổ sung theo `lower(valid_period)` khi truy vấn lịch sử thực sự đòi hỏi.

Nhưng chỉ nên thêm sau khi đo chi phí và selectivity.

### Đọc kế hoạch truy vấn

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT booking_id
FROM room_bookings
WHERE room_id = 1
  AND status = 'CONFIRMED'
  AND booked_period && tstzrange(
      TIMESTAMPTZ '2026-11-14 09:00:00+07',
      TIMESTAMPTZ '2026-11-14 12:00:00+07',
      '[)'
  );
```

Khi bảng rất nhỏ, PostgreSQL có thể ưu tiên sequential scan; không phải lỗi. Khi bảng tăng, cần xem actual row counts, buffer hits/reads, mức chọn lọc và hiệu năng ghi. `ANALYZE`/autovacuum thống kê giúp planner có cơ sở chọn kế hoạch.

## 20. Multirange và khoảng rảnh không phải lịch sử từng booking

Giả sử một nhân viên có những khoảng rảnh:

```sql
CREATE TABLE staff_availability (
    staff_id BIGINT PRIMARY KEY,
    free_periods TSTZMULTIRANGE NOT NULL
);
```

Một multirange có thể biểu diễn nhiều đoạn rảnh trong tuần. Tuy nhiên, khi một slot bị đặt:

```sql
UPDATE staff_availability
SET free_periods =
      free_periods
      - tstzmultirange(
          tstzrange(
              TIMESTAMPTZ '2026-11-14 09:00:00+07',
              TIMESTAMPTZ '2026-11-14 10:00:00+07',
              '[)'
          )
        )
WHERE staff_id = 101;
```

Một câu `UPDATE` như vậy có thể tạo ra hai đoạn rảnh còn lại khi slot cắt giữa một đoạn lớn. Nhưng **không đủ để ghi nhận** ai đặt, booking ID, trạng thái, số lần sửa hoặc lý do huỷ.

Đối với lịch đặt chỗ thực tế, thường nên:

1. Lưu **từng booking ở bảng riêng** với khóa và metadata.
2. Dùng constraint `EXCLUDE` trên booking để bảo vệ xung đột.
3. Tính multirange của thời gian bận/rảnh để phục vụ truy vấn, báo cáo và giao diện.
4. Nếu lưu multirange rảnh như cache/materialized state, xác định cơ chế đồng bộ với bảng booking trong cùng transaction hoặc qua một quy trình nhất quán.

**Multirange là biểu diễn tập hợp khoảng**, không tự thay thế mô hình sự kiện và quan hệ giữa booking với người đặt.

## 21. Xử lý đồng thời và transaction với dữ liệu khoảng

Range và multirange không loại bỏ nhu cầu quản lý **transaction concurrency**.

### Thử trước rồi ghi có thể bị race

Hai giao dịch ở mức `READ COMMITTED` cùng chạy `SELECT ... WHERE booked_period && requested` và đều chưa thấy booking đối thủ chưa commit. Nếu chỉ dùng check ở application, cả hai có thể ghi trùng.

Ràng buộc `EXCLUDE` trên PostgreSQL giúp đưa bất biến **không overlap** xuống database. Khi có xung đột, thao tác có thể đợi và cuối cùng bị từ chối.

### Làm gì khi gặp lỗi exclusion?

- Kiểm tra SQLSTATE **`23P01`**.
- Rollback transaction thất bại theo cơ chế JDBC/Spring.
- Có thể hiển thị slot trùng và đề nghị giờ khác.
- Không retry vô hạn cùng một slot nếu lịch đã được người khác xác nhận.
- Nếu nghiệp vụ thực sự cho phép nhiều booking ở một phòng theo capacity > 1, quy tắc `EXCLUDE room_id WITH =` có thể **quá chặt**; cần mô hình capacity khác.

### Transaction tạo/cập nhật lịch

Với thao tác gồm booking, hóa đơn, outbox message, hãy đặt các ghi database phải cùng thành công trong **một transaction**:

```text
BEGIN
  ├── INSERT booking (range)
  ├── INSERT payment intent / hold record
  ├── INSERT outbox event
COMMIT
```

Nếu booking bị `23P01`, tất cả ghi cùng transaction phải rollback để tránh tạo hóa đơn cho lịch không hợp lệ.

### Khi cần khóa bổ sung

`EXCLUDE` bảo vệ điều kiện overlap; nó **không tự quản lý** mọi quy tắc như giới hạn lượt đặt/ngày, số khách hoặc giá theo mốc. Có thể cần khóa theo phòng/tài nguyên hoặc optimistic locking để bảo vệ thêm các bất biến liên quan, song không nên giữ transaction trong lúc gọi network hay API bên ngoài lâu.

## 22. Định nghĩa custom range type

Ngoài các kiểu tích hợp, PostgreSQL cho phép định nghĩa **range type tùy chỉnh** trên một subtype có thứ tự phù hợp, bằng `CREATE TYPE ... AS RANGE`.

Một ví dụ khái niệm:

```sql
CREATE TYPE custom_numeric_range AS RANGE (
    subtype = numeric
);
```

Điều này tạo một range type trên `numeric`, nhưng trong hầu hết ứng dụng thông thường, **`numrange` tích hợp đã đủ**. Tạo custom range type nên có lý do rõ:

- Subtype đặc thù chưa có range tích hợp.
- Quy tắc so sánh và operator class B-tree phù hợp.
- Có thể cần canonicalization function, subtype difference function hoặc cấu hình collation/opclass để hỗ trợ hiệu quả.
- Tương thích giữa schema migrations, extension và ứng dụng cần được quản lý.

### Multirange cho custom range

Khi định nghĩa custom range type trong PostgreSQL hỗ trợ multirange, có cơ chế tạo tên/kiểu multirange liên quan. Nếu cần tích hợp nghiêm ngặt với hệ thống, kiểm tra cú pháp `multirange_type_name` và tên type thực đã được tạo trên đúng phiên bản PostgreSQL, tránh tự giả định tên ghép là hợp lệ.

### Canonical function quan trọng khi subtype rời rạc

Với kiểu rời rạc tùy chỉnh, hai cách viết khoảng khác dấu ngoặc có thể mô tả **cùng tập phần tử**. Một canonicalization function phù hợp giúp chuẩn hóa biểu diễn; việc thiết kế sai có thể gây nhầm lẫn khi so sánh hoặc gộp range.

Phần này thuộc chủ đề mở rộng kiểu dữ liệu PostgreSQL và cần hiểu sâu về subtype ordering; không nên tạo custom type chỉ để lưu một khoảng ngày hoặc số nguyên vốn đã có kiểu tích hợp.

## 23. Multirange không phải array của các range

Có thể lưu `int4range[]` là một **mảng các range**, nhưng nó **khác** `int4multirange`.

| Khía cạnh | `int4range[]` | `int4multirange` |
|---|---|---|
| Bản chất | Mảng lưu các phần tử range theo thứ tự phần tử của mảng. | Một tập khoảng được chuẩn hóa. |
| Khoảng giao nhau | Có thể tồn tại hai phần tử chồng lấn. | Được hợp nhất thành những đoạn không giao nhau. |
| Khoảng kề nhau | Có thể là hai phần tử riêng. | Có thể được gộp thành một đoạn. |
| Phép tập hợp | Thường phải tự xử lý từng phần tử. | Có toán tử multirange `+`, `*`, `-` và kiểm tra bao chứa/giao nhau. |
| Giữ metadata từng đoạn | Có thể giữ cấu trúc theo phần tử nhưng không trực tiếp lưu actor/ID. | Không giữ danh tính booking/nguồn của từng đoạn. |

Ví dụ:

```sql
SELECT ARRAY[
    '[1,5)'::int4range,
    '[4,8)'::int4range
] AS range_array;

SELECT int4multirange(
    '[1,5)'::int4range,
    '[4,8)'::int4range
) AS normalized_multirange;
-- {[1,8)}
```

Nếu cần **danh tính từng sự kiện**, hãy lưu hàng riêng trong bảng quan hệ; nếu cần **một tập giá trị được phủ bởi nhiều đoạn**, multirange là lựa chọn trực tiếp hơn.

## 24. NULL, empty và các quy tắc dữ liệu trong ứng dụng

Hãy thiết kế API rõ ràng cho những trường hợp:

- **Không được cung cấp khoảng:** SQL `NULL` → request thiếu thông tin hoặc chưa xác định.
- **Không có khoảng hợp lệ nào:** `empty` range hoặc `{}` multirange → tập rỗng thật.
- **Khoảng bắt đầu nhưng chưa biết khi nào kết thúc:** upper unbounded.
- **Khoảng một điểm duy nhất:** chỉ hợp lý với loại biên/subtype cụ thể, ví dụ `[5,5]::numrange`.
- **Khoảng kết thúc trước khi bắt đầu:** phải bị từ chối như input không hợp lệ.

Ví dụ constraint:

```sql
CREATE TABLE promotion_windows (
    promotion_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    active_period TSTZRANGE NOT NULL,
    CONSTRAINT chk_promotion_period_nonempty
        CHECK (NOT isempty(active_period)),
    CONSTRAINT chk_promotion_starts_at_a_real_instant
        CHECK (NOT lower_inf(active_period))
);
```

Mẫu cho phép **kết thúc không giới hạn** vì chương trình khuyến mãi có thể chưa có ngày kết thúc, nhưng bắt buộc phải có điểm bắt đầu.

### Check constraint có thể nhận UNKNOWN nếu cột NULL

Trong SQL, một `CHECK` thông thường coi **false** là vi phạm; kết quả **NULL/unknown** không nhất thiết vi phạm. Vì vậy `CHECK (NOT isempty(active_period))` **không thay thế** `active_period NOT NULL`.

Đây là lý do nên kết hợp:

```sql
active_period TSTZRANGE NOT NULL,
CHECK (NOT isempty(active_period))
```

Hai lớp bảo vệ diễn đạt hai bất biến khác nhau.

## 25. Những lỗi thường gặp

### 25.1. Nhầm `[)` với `[]` ở ngày kết thúc

Với khoảng `daterange('2026-11-01','2026-11-10','[)')`, **ngày 10/11 không nằm trong khoảng**. Nếu nghiệp vụ muốn bao gồm cả ngày 10, dùng mốc upper là **11/11** theo quy tắc nửa mở hoặc chọn cách biểu diễn và canonicalization phù hợp.

### 25.2. Tưởng upper() là giá trị cuối thực sự thuộc range

`upper('[1,4)'::int4range) = 4` nhưng range chỉ chứa 1,2,3. Không dùng upper làm “max included value” khi chưa xem `upper_inc` và subtype.

### 25.3. Gộp hai range rời nhau thành một range lớn

`[1,4)` và `[7,10)` không thể gộp chính xác thành `[1,10)`: giá trị 4,5,6 sẽ bị thêm. Dùng **multirange** để giữ gap.

### 25.4. Nhầm range rỗng với NULL

`'empty'::int4range` vẫn là một giá trị có kiểu; `NULL::int4range` là thiếu giá trị. Cần kiểm tra riêng `isempty` và `IS NULL`.

### 25.5. Nhầm `infinity` với bound không giới hạn

`'infinity'::timestamptz` là giá trị đặc biệt của subtype; upper **unbounded** qua constructor `NULL` là khái niệm không có bound. Khi logic cần nhận biết thiếu biên, dùng `upper_inf`.

### 25.6. Chỉ kiểm tra overlap bằng SELECT rồi INSERT

Hai transaction có thể cùng đọc “chưa có booking trùng” và cùng ghi. Dùng **`EXCLUDE USING gist`** để bảo vệ bất biến ở database, sau đó xử lý `23P01`.

### 25.7. Dùng range trên timestamp không múi giờ cho lịch toàn cầu

`tsrange` không tự mang thông tin time zone. Với lịch theo instant và nhiều khu vực, `tstzrange` thường thích hợp hơn, kèm thông tin vùng địa lý nếu nghiệp vụ cần lịch địa phương.

### 25.8. Lấy range_merge làm tập khoảng rảnh

`range_merge('{[1,4),[7,10)}'::int4multirange)` là `[1,10)`, chứa cả gap. Hàm trả **bao lồi**, không giữ tính rời rạc.

### 25.9. Tưởng exclusion constraint bảo đảm không có khoảng trống

Constraint `WITH &&` cấm giao nhau, nhưng **không bảo đảm continuity**. Nếu timeline giá bắt buộc phủ kín, cần thêm quy tắc ghi và kiểm tra gap.

### 25.10. Tưởng mỗi booking có thể thay bằng một multirange duy nhất

Multirange không chứa booking ID, actor, trạng thái và chi tiết sự kiện của từng đoạn. Dữ liệu giao dịch vẫn cần bảng booking với từng hàng.

### 25.11. Dùng quá nhiều index mà không đo workload

GiST/exclusion index và các B-tree/GIN/BRIN khác đều tăng chi phí ghi, WAL và dung lượng. Cần dùng `EXPLAIN`, metric và đường truy vấn thật để quyết định.

### 25.12. Không xét concurrency khi thay đổi giá

Nếu nhiều worker sửa các khoảng giá, hai bước “đóng bản cũ” và “mở bản mới” phải cùng transaction; cần khóa theo entity hoặc cơ chế đồng thời phù hợp, kết hợp `EXCLUDE`.

## 26. Bài tập thực hành

### Bài 1 — Đọc biên

Cho các khoảng:

```text
[1,5)
(1,5]
[1,5]
(1,5)
```

Hãy xác định với **`numrange`** liệu số 1 và số 5 có thuộc mỗi khoảng không. Sau đó giải thích vì sao `int4range(1,4,'[)')` và `int4range(1,3,'[]')` biểu diễn cùng tập số nguyên.

### Bài 2 — Empty, NULL và unbounded

Viết SQL để tạo:

1. Một `int4range` rỗng.
2. Một `int4range` từ 10 trở lên, không giới hạn phía trên.
3. Một giá trị SQL `NULL` có kiểu `int4range`.

Viết các phép kiểm tra `isempty`, `upper_inf` và `IS NULL` tương ứng, rồi giải thích vì sao chúng khác nhau.

### Bài 3 — Kiểm tra giao nhau và kề nhau

Cho `A=[1,4)`, `B=[4,7)`, `C=[3,5)` theo `int4range`. Dự đoán `A && B`, `A -|- B`, `A && C` và `A @> 3`. Kiểm tra bằng SQL.

### Bài 4 — Phép hiệu multirange

Tính bằng SQL:

```text
Allowed = [1,20)
Blocked = [4,7) ∪ [12,15)
Free = Allowed - Blocked
```

Giải thích tại sao `Free` cần **multirange** và cách dùng `unnest` để trả từng đoạn rảnh thành một hàng.

### Bài 5 — Canonicalization của daterange

Viết hai `daterange` tương đương cho các ngày từ 01 đến hết 07/12/2026, một dùng dạng `[]` và một dùng `[)`. So sánh bằng `=` và quan sát chuỗi range được PostgreSQL hiển thị.

### Bài 6 — Đặt phòng không chồng lấn

Tạo bảng `rooms`, `bookings` gồm `room_id` và `during tstzrange`. Thêm `btree_gist` và exclusion constraint chỉ áp dụng với booking trạng thái `CONFIRMED`. Chứng minh:

- Booking 09:00–10:00 và 10:00–11:00 được phép cùng tồn tại.
- Booking 09:30–10:30 cùng phòng bị từ chối với `23P01`.
- Hai booking trùng giờ nhưng **khác phòng** được phép.

### Bài 7 — Tính lịch rảnh

Trong khung 08:00–18:00, các booking là 09:00–10:00 và 11:00–13:00. Dùng `range_agg`, `tstzmultirange` và phép trừ để trả những khoảng rảnh. Dùng `unnest` trả danh sách từng slot, lọc chỉ slot dài ít nhất 45 phút.

### Bài 8 — Thiết kế giá theo thời gian

Sản phẩm A có giá 100 đến ngày 10/11 và 120 từ ngày 10/11. Thiết kế `valid_period tstzrange`, SQL truy vấn giá tại ngày 09/11 và đúng mốc chuyển giá; xác định cơ chế không cho hai giá giao nhau.

Nêu thêm cách giữ **lý do thay đổi** nếu cần audit, vì range tự nó không ghi lại ai đổi giá.

### Bài 9 — Chọn kiểu dữ liệu

Hãy chọn một trong `daterange`, `tsrange`, `tstzrange`, `int4range`, `numrange`, `tstzmultirange` cho:

- Phạm vi số lượng được chiết khấu.
- Mức cân nặng hợp lệ.
- Ngày hiệu lực hợp đồng theo lịch.
- Cuộc họp với người tham dự ở nhiều múi giờ.
- Tập ba khung giờ rảnh không liên tục.

Giải thích lựa chọn và quy tắc biên.

### Bài 10 — Race condition khi tạo booking

Hai request Java đồng thời kiểm tra một phòng còn trống rồi insert lịch giao nhau. Phân tích vì sao `SELECT` trước khi insert không đủ trong mức cô lập thông thường. Đề xuất transaction và `EXCLUDE`, cách bắt lỗi `23P01` và phản hồi người dùng.

### Bài 11 — Index và truy vấn

Với một bảng lịch có hàng triệu booking, thiết kế truy vấn lấy booking giao với một khung giờ và giải thích vai trò của GiST. Nêu lý do PostgreSQL vẫn có thể chọn sequential scan cho bảng rất nhỏ và vì sao không nên tạo thêm nhiều chỉ mục trùng chức năng với GiST của exclusion constraint.

### Bài 12 — Multirange hay nhiều hàng?

Một nhân viên có ba ca làm việc, mỗi ca được phê duyệt bởi người quản lý khác nhau. Hãy phân biệt cách dùng **nhiều hàng ca làm việc** để giữ metadata với cách dùng **multirange** để tính tổng những khoảng đã được phê duyệt. Nếu ca thứ hai bị hủy, làm thế nào cập nhật dữ liệu nguồn và tính lại tập thời gian làm việc?

## Kết luận

**Range** biểu diễn một khoảng có quy tắc đầu mút rõ ràng; **multirange** biểu diễn một tập nhiều khoảng đã được chuẩn hóa, giữ được những **khoảng trống** mà range đơn không thể giữ. Các kiểu tích hợp như `int4range`, `daterange`, `tstzrange` và các kiểu multirange tương ứng giúp thiết kế dải giá trị, thời gian hiệu lực, lịch đặt chỗ và khung giờ rảnh bằng những thao tác gọn, giàu ngữ nghĩa.

Khi thực hành, hãy ưu tiên hiểu chính xác **`[)`, biên rời rạc/liên tục, empty, SQL NULL và bound không giới hạn**. Dùng `@>` để kiểm tra bao chứa, `&&` cho giao nhau, `-|-` cho kề nhau, `range_agg` và `unnest` để tổng hợp/tách những đoạn rời nhau. **`range_merge`** chỉ cho bao lồi và có thể làm mất thông tin gap, vì vậy phải sử dụng đúng mục đích.

Trong thiết kế thực tế, một range column **không tự bảo vệ được xung đột đồng thời** nếu ứng dụng chỉ kiểm tra bằng `SELECT`. Kết hợp **`EXCLUDE USING gist`, transaction, ràng buộc không rỗng, chỉ mục phù hợp và xử lý SQLSTATE `23P01`** để giữ dữ liệu đúng dưới tải cạnh tranh. Sử dụng multirange như **biểu diễn tập khoảng**, đồng thời giữ các bảng quan hệ riêng khi cần danh tính, trạng thái và lịch sử từng booking hoặc sự kiện. Đó là cách đưa lý thuyết khoảng giá trị vào PostgreSQL một cách rõ ràng, có thể truy vấn hiệu quả và an toàn khi vận hành.
